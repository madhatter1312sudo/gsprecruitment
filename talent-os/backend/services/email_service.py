"""
Talent OS -- Email Service (WS3).

Two providers behind one interface: GmailApiProvider (the pre-existing
OAuth/Gmail-API path, behaviour unchanged) and SmtpProvider (stdlib
smtplib, STARTTLS -- the SMTP_* settings in core/config.py were dead
before this spoor). EMAIL_PROVIDER (core/config.py, default "gmail")
picks between them; nothing else in the codebase needs to know which one
is active.

send_email(to_email, subject, body_text, ...) keeps its pre-existing
signature for the six call sites that already use it (routers/auth.py,
routers/client.py, routers/outreach.py, routers/public.py,
services/scheduler.py). send_template(name, to_email, ctx, lang) is new:
it renders through services/email_templates.py instead of an inline
f-string body.

Both go through the same retry + logging path: up to three retries with
backoff (0.5s, 2s, 8s) on a connection error or a 5xx response, never on
a 4xx (that will not succeed on a second try). Every attempt -- sent,
failed, or the final give-up -- writes one row to email_log with
`to_hash = core.privacy.email_hash(address)`; the address itself never
reaches that table, and never reaches a logger.warning/error call either
(core.privacy.redact_emails() strips anything e-mail-shaped out of every
error string before it is logged or stored).
"""
import asyncio
import base64
import logging
import smtplib
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.credentials import Credentials
from starlette.concurrency import run_in_threadpool

from core import privacy
from core.config import settings
from core.database import execute
from services import email_templates

logger = logging.getLogger("talent_os.email")

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# Seconds to wait before attempt 2, 3 and 4 respectively (attempt 1 runs
# immediately) -- "retry 3x" == 3 retries on top of the first attempt.
RETRY_BACKOFFS = (0.5, 2.0, 8.0)


class EmailSendError(Exception):
    """Raised by a provider's send(). retryable=True marks a connection
    error or a 5xx response (worth another attempt); False marks a 4xx
    or a local configuration problem (a retry would just repeat it)."""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class EmailMessage:
    to: str
    subject: str
    text: str
    html: Optional[str] = None
    reply_to: Optional[str] = None
    headers: dict = field(default_factory=dict)


def _build_mime(msg: EmailMessage, from_address: str):
    if msg.html:
        mime = MIMEMultipart("alternative")
        mime.attach(MIMEText(msg.text, "plain", "utf-8"))
        mime.attach(MIMEText(msg.html, "html", "utf-8"))
    else:
        mime = MIMEText(msg.text, "plain", "utf-8")
    mime["To"] = msg.to
    mime["From"] = from_address
    mime["Subject"] = msg.subject
    if msg.reply_to:
        mime["Reply-To"] = msg.reply_to
    for key, value in msg.headers.items():
        mime[key] = value
    return mime


class GmailApiProvider:
    """Sends via the Gmail API using the existing OAuth refresh-token
    credentials -- behaviourally identical to the pre-WS3 EmailService,
    only moved behind this Provider interface so EmailService can retry
    and log around it the same way as SmtpProvider."""

    name = "gmail"

    def _get_credentials(self) -> Optional[Credentials]:
        """Build credentials from the stored OAuth tokens. Blocking
        network I/O (creds.refresh()) -- always called via
        run_in_threadpool, never directly on the event loop."""
        if not settings.google_client_id or not settings.google_client_secret or not settings.google_refresh_token:
            return None
        try:
            creds = Credentials(
                token=None,
                refresh_token=settings.google_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.google_client_id,
                client_secret=settings.google_client_secret,
                scopes=SCOPES,
            )
            creds.refresh(GoogleRequest())
            return creds
        except Exception as e:
            logger.error(f"Failed to refresh Google OAuth token: {privacy.redact_emails(str(e))}")
            return None

    async def send(self, msg: EmailMessage) -> str:
        creds = await run_in_threadpool(self._get_credentials)
        if not creds:
            raise EmailSendError("Google OAuth credentials not configured", retryable=False)

        mime = _build_mime(msg, settings.email_from)
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                    headers={
                        "Authorization": f"Bearer {creds.token}",
                        "Content-Type": "application/json",
                    },
                    json={"raw": raw},
                )
        except httpx.HTTPError as e:
            raise EmailSendError(f"Gmail API connection error: {privacy.redact_emails(str(e))}", retryable=True) from e

        if response.status_code == 200:
            return response.json().get("id", "")

        retryable = response.status_code >= 500
        raise EmailSendError(
            f"Gmail API error {response.status_code}: {privacy.redact_emails(response.text)[:300]}",
            retryable=retryable,
        )


def _smtp_send_sync(msg: EmailMessage) -> None:
    """Blocking smtplib call -- always run via run_in_threadpool from
    SmtpProvider.send(), never directly on the event loop. STARTTLS is
    always attempted; login() only runs when SMTP_USER is set (an
    unauthenticated local/internal relay is a legitimate SMTP_HOST
    configuration and must not be forced to authenticate)."""
    mime = _build_mime(msg, settings.email_from)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_pass)
        smtp.sendmail(settings.email_from, [msg.to], mime.as_string())


class SmtpProvider:
    """stdlib smtplib, STARTTLS on port 587 -- makes the previously dead
    SMTP_HOST/PORT/USER/PASS settings (core/config.py) live whenever
    EMAIL_PROVIDER=smtp."""

    name = "smtp"

    async def send(self, msg: EmailMessage) -> str:
        # Order matters here: every smtplib exception (SMTPException and
        # all its subclasses, SMTPResponseException/SMTPConnectError
        # included) IS ALSO an OSError -- a bare `except OSError` placed
        # before these would swallow all of them as one generic
        # "connection error", including a clean 4xx permanent rejection,
        # and the retryable=False branches below would be dead code.
        # Most specific first; a bare (OSError, TimeoutError) catch-all
        # for a pure socket-level failure (refused connection, DNS
        # failure, timeout) comes last, once every smtplib-specific case
        # has already had a chance to classify itself.
        try:
            await run_in_threadpool(_smtp_send_sync, msg)
        except smtplib.SMTPConnectError as e:
            # Never got a usable connection at all -- worth a retry
            # regardless of whatever numeric code the peer sent.
            raise EmailSendError(f"SMTP connection error: {privacy.redact_emails(str(e))}", retryable=True) from e
        except smtplib.SMTPServerDisconnected as e:
            raise EmailSendError(f"SMTP connection error: {privacy.redact_emails(str(e))}", retryable=True) from e
        except smtplib.SMTPResponseException as e:
            retryable = 500 <= e.smtp_code < 600
            raise EmailSendError(
                f"SMTP error {e.smtp_code}: {privacy.redact_emails(str(e.smtp_error))}", retryable=retryable,
            ) from e
        except smtplib.SMTPException as e:
            # Any other smtplib failure (e.g. SMTPRecipientsRefused, which
            # carries no single smtp_code) -- a retry would just repeat
            # the same rejection.
            raise EmailSendError(f"SMTP error: {privacy.redact_emails(str(e))}", retryable=False) from e
        except (OSError, TimeoutError) as e:
            raise EmailSendError(f"SMTP connection error: {privacy.redact_emails(str(e))}", retryable=True) from e
        return ""


def _get_provider():
    if settings.email_provider == "smtp":
        return SmtpProvider()
    return GmailApiProvider()


async def _log_attempt(
    template: str, to_email: str, status: str,
    provider: Optional[str], provider_id: Optional[str], error: Optional[str],
) -> None:
    """One email_log row per attempt. to_hash only -- never the address
    itself -- and `error` always passes through redact_emails() first,
    same guarantee as the logger calls around it."""
    try:
        await execute(
            "INSERT INTO email_log (template, to_hash, status, provider, provider_id, error) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            template, privacy.email_hash(to_email), status, provider,
            provider_id or None, privacy.redact_emails(error) if error else None,
        )
    except Exception:
        # A logging failure must never take down (or even fail) the send
        # path itself -- log and move on.
        logger.exception("Failed to write email_log row")


class EmailService:
    """Selects a provider (EMAIL_PROVIDER), retries transient failures
    with backoff, and logs every attempt to email_log."""

    async def _send_with_retry(self, msg: EmailMessage, template: str) -> bool:
        provider = _get_provider()
        for backoff in (0.0,) + RETRY_BACKOFFS:
            if backoff:
                await asyncio.sleep(backoff)
            try:
                provider_id = await provider.send(msg)
            except EmailSendError as e:
                await _log_attempt(template, msg.to, "failed", provider.name, None, str(e))
                if not e.retryable:
                    return False
                continue
            except Exception as e:
                # Never let an unexpected provider bug escape send_email/
                # send_template -- log it as a (non-retryable) failure.
                await _log_attempt(template, msg.to, "failed", provider.name, None, str(e))
                return False
            else:
                await _log_attempt(template, msg.to, "sent", provider.name, provider_id or None, None)
                return True
        return False

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        to_name: Optional[str] = None,
        html: Optional[str] = None,
    ) -> bool:
        """Send a plain (optionally also HTML) e-mail. Signature unchanged
        for the six existing call sites -- `to_name` is accepted for
        backwards compatibility but, as before this spoor, not used in
        the message headers (only to_email is)."""
        msg = EmailMessage(to=to_email, subject=subject, text=body_text, html=html, reply_to=settings.email_reply_to)
        return await self._send_with_retry(msg, template="adhoc")

    async def send_template(self, name: str, to_email: str, ctx: dict, lang: str = "nl") -> bool:
        """Render `name` via services/email_templates.render() and send
        it through the same retry + email_log path as send_email()."""
        subject, text, html = email_templates.render(name, ctx, lang)
        msg = EmailMessage(to=to_email, subject=subject, text=text, html=html, reply_to=settings.email_reply_to)
        return await self._send_with_retry(msg, template=name)


email_service = EmailService()
