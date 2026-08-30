"""
Talent OS — Transactional mailer.

Renders Jinja2 templates from templates/email/{template}.html (+ an optional
plain-text {template}.txt) and sends over the owner's Google Workspace SMTP
(aiosmtplib, async, STARTTLS on smtp.gmail.com:587). If SMTP isn't
configured yet, falls back to the existing Gmail-API EmailService so nothing
breaks before the owner sets SMTP creds. If neither is configured, logs and
returns False.

Every send attempt — success or failure, on either transport — writes one
row to email_log (migration 015). Never logs credentials or full message
bodies (house rule); only recipient, template, subject and a short error.

Outreach stays draft-only: send_raw() sends an already-composed, already
human-approved body verbatim. There is no path here that composes and sends
on its own initiative.
"""
import html
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, TemplateNotFound, select_autoescape

from core.config import settings
from core.database import execute
from services.email_service import email_service

logger = logging.getLogger("talent_os.mailer")

FROM_ADDRESS = "GSP Recruitment <info@gsprecruitment.nl>"

_TEMPLATE_DIR = __file__.rsplit("/services/mailer.py", 1)[0] + "/templates/email"

_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


# ── Pure helpers (unit-testable without network/DB) ─────────────────────

def has_header_injection(*values: Optional[str]) -> bool:
    """True if any value contains a CR or LF. `to`/`subject` land verbatim
    in MIMEMultipart headers (see _send_via_smtp) -- outreach drafts carry
    scraped, attacker-influenced target_email/subject, so a value like
    "x@a.com\\nBcc: victim@b.org" would otherwise inject extra headers.
    Pure/testable without touching SMTP."""
    return any(v is not None and ("\r" in v or "\n" in v) for v in values)


def smtp_is_configured() -> bool:
    """SMTP is usable once host/user/pass are all set (port always has a
    sane default)."""
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_pass)


def gmail_api_is_configured() -> bool:
    return bool(
        settings.google_client_id and settings.google_client_secret and settings.google_refresh_token
    )


def resolve_transport() -> str:
    """Which transport a send() call would use right now. Pure decision
    logic, factored out so the fallback chain is testable without touching
    SMTP or the Gmail API."""
    if smtp_is_configured():
        return "smtp"
    if gmail_api_is_configured():
        return "gmail_api"
    return "none"


def render_template(template: str, ctx: dict) -> tuple[str, Optional[str]]:
    """Render {template}.html and, if present, {template}.txt. Returns
    (html_body, text_body_or_None)."""
    html_tmpl = _env.get_template(f"{template}.html")
    html_body = html_tmpl.render(**ctx)

    text_body = None
    try:
        text_tmpl = _env.get_template(f"{template}.txt")
        text_body = text_tmpl.render(**ctx)
    except TemplateNotFound:
        pass

    return html_body, text_body


def resolve_subject(template: str, ctx: dict, explicit_subject: Optional[str] = None) -> str:
    """Explicit arg wins; otherwise render the template's `{% block subject
    %}` (defined on base.html, overridden per template) with the same
    context. Falls back to a generic subject if a template defines neither
    (shouldn't happen for our own templates, but send() must never crash
    over a missing subject)."""
    if explicit_subject:
        return explicit_subject

    tmpl = _env.get_template(f"{template}.html")
    block = tmpl.blocks.get("subject")
    if block is None:
        return "GSP Recruitment"
    ctx_obj = tmpl.new_context(ctx)
    return "".join(block(ctx_obj)).strip()


async def _log_attempt(
    to: str,
    template: str,
    subject: Optional[str],
    provider: str,
    status: str,
    error: Optional[str] = None,
    related_user_id: Optional[int] = None,
) -> None:
    try:
        await execute(
            """INSERT INTO email_log
               (to_email, template, subject, provider, status, error, related_user_id)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            to, template, subject, provider, status, error, related_user_id,
        )
    except Exception:
        # The send outcome itself must not be lost just because logging it
        # failed -- log locally and move on.
        logger.exception("mailer: failed to write email_log row (to=%s, template=%s)", to, template)


async def _send_via_smtp(to: str, subject: str, html_body: str, text_body: Optional[str]) -> None:
    msg = MIMEMultipart("alternative")
    msg["From"] = FROM_ADDRESS
    msg["To"] = to
    msg["Subject"] = subject
    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_pass,
        start_tls=True,
    )


async def _send_via_gmail_api(to: str, subject: str, text_body: Optional[str], html_body: str) -> bool:
    # EmailService only sends plain text; prefer the real text fallback,
    # otherwise fall back to the rendered HTML (better than nothing).
    body = text_body or html_body
    return await email_service.send_email(to_email=to, subject=subject, body_text=body)


async def send(
    to: str,
    template: str,
    ctx: dict,
    subject: Optional[str] = None,
    related_user_id: Optional[int] = None,
) -> bool:
    """Render `template` with `ctx` and send it to `to`. Returns True iff
    the message was actually handed off successfully. Always writes an
    email_log row, whatever the outcome."""
    if has_header_injection(to, subject):
        logger.warning("mailer: refusing send -- CR/LF in to or subject (possible header injection), to=%r", to)
        await _log_attempt(to, template, subject, "none", "failed", "rejected: CR/LF in to/subject (header injection)", related_user_id)
        return False

    try:
        html_body, text_body = render_template(template, ctx)
        resolved_subject = resolve_subject(template, ctx, subject)
    except TemplateNotFound as e:
        logger.error("mailer: template not found: %s", e)
        await _log_attempt(to, template, subject, "none", "failed", "template not found", related_user_id)
        return False
    except Exception as e:
        logger.exception("mailer: template render failed for %s", template)
        await _log_attempt(to, template, subject, "none", "failed", f"render error: {e}", related_user_id)
        return False

    if has_header_injection(resolved_subject):
        # Catches the rarer case where the subject came from a rendered
        # {% block subject %} fed by attacker-influenced ctx (e.g. a
        # candidate's own full_name) rather than the explicit arg checked
        # above.
        logger.warning("mailer: refusing send -- CR/LF in resolved subject (possible header injection)")
        await _log_attempt(to, template, resolved_subject, "none", "failed", "rejected: CR/LF in resolved subject (header injection)", related_user_id)
        return False

    transport = resolve_transport()

    if transport == "smtp":
        try:
            await _send_via_smtp(to, resolved_subject, html_body, text_body)
            await _log_attempt(to, template, resolved_subject, "smtp", "sent", None, related_user_id)
            return True
        except Exception as e:
            logger.error("mailer: SMTP send failed for %s: %s", to, e)
            await _log_attempt(to, template, resolved_subject, "smtp", "failed", str(e), related_user_id)
            return False

    if transport == "gmail_api":
        ok = await _send_via_gmail_api(to, resolved_subject, text_body, html_body)
        await _log_attempt(
            to, template, resolved_subject, "gmail_api", "sent" if ok else "failed",
            None if ok else "gmail api send_email returned False", related_user_id,
        )
        return ok

    logger.error("mailer: no email transport configured (SMTP and Gmail API both unset)")
    await _log_attempt(to, template, resolved_subject, "none", "failed", "no transport configured", related_user_id)
    return False


async def send_raw(
    to: str,
    subject: str,
    body: str,
    related_user_id: Optional[int] = None,
) -> bool:
    """Send an already-composed plain-text body verbatim — no template
    rendering. Used only for approved outreach sends, where a human has
    already written/edited the exact text and DRAFT-approval semantics must
    not add or alter a single character."""
    if has_header_injection(to, subject):
        # Outreach drafts carry scraped, attacker-influenced target_email
        # and subject -- a CRLF here would otherwise inject extra SMTP
        # headers (e.g. an extra Bcc:) when an admin approves the draft.
        logger.warning("mailer: refusing send_raw -- CR/LF in to or subject (possible header injection), to=%r", to)
        await _log_attempt(to, "outreach_raw", subject, "none", "failed", "rejected: CR/LF in to/subject (header injection)", related_user_id)
        return False

    transport = resolve_transport()

    if transport == "smtp":
        try:
            html_body = f"<pre style='font-family:inherit; white-space:pre-wrap'>{html.escape(body)}</pre>"
            await _send_via_smtp(to, subject, html_body, body)
            await _log_attempt(to, "outreach_raw", subject, "smtp", "sent", None, related_user_id)
            return True
        except Exception as e:
            logger.error("mailer: SMTP raw send failed for %s: %s", to, e)
            await _log_attempt(to, "outreach_raw", subject, "smtp", "failed", str(e), related_user_id)
            return False

    if transport == "gmail_api":
        ok = await email_service.send_email(to_email=to, subject=subject, body_text=body)
        await _log_attempt(
            to, "outreach_raw", subject, "gmail_api", "sent" if ok else "failed",
            None if ok else "gmail api send_email returned False", related_user_id,
        )
        return ok

    logger.error("mailer: no email transport configured (SMTP and Gmail API both unset)")
    await _log_attempt(to, "outreach_raw", subject, "none", "failed", "no transport configured", related_user_id)
    return False
