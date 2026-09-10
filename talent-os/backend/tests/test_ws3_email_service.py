"""
WS3 -- services/email_service.py: provider abstraction (Gmail/SMTP),
retry + backoff, and the email_log write path.

Pure unit tests: core.database.execute is monkeypatched module-by-module
(no DB needed), smtplib.SMTP is replaced with an in-process fake, and
asyncio.sleep is patched to a no-op so the retry-backoff tests don't
actually wait 0.5s/2s/8s -- same "no real DB, no real sleep" style as
tests/test_draft_refused_counter.py and tests/test_retention.py.
"""
import asyncio
import os
import smtplib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

import pytest

from core import privacy
from core.config import settings
import services.email_service as es


def _no_sleep(monkeypatch):
    """Retry tests must not actually wait 0.5s/2s/8s -- patch the module's
    own asyncio.sleep, recording the requested delays for assertions."""
    calls = []

    async def _fake_sleep(seconds):
        calls.append(seconds)

    monkeypatch.setattr(es.asyncio, "sleep", _fake_sleep)
    return calls


def _no_op_log(monkeypatch):
    """Capture every email_log row _log_attempt() would have written,
    without touching a real database -- execute() is patched at the
    module level exactly like tests/test_draft_refused_counter.py patches
    services.scheduler.execute."""
    rows = []

    async def _fake_execute(sql, *args):
        rows.append(args)
        return "INSERT 0 1"

    monkeypatch.setattr(es, "execute", _fake_execute)
    return rows


# ── SmtpProvider ────────────────────────────────────────────────────────

class _FakeSMTP:
    """Stands in for smtplib.SMTP as a context manager. Records every
    call so a test can assert STARTTLS ran, login() ran only when
    SMTP_USER was set, and the envelope From/To/message are correct."""

    instances = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.starttls_called = False
        self.login_args = None
        self.sendmail_args = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.starttls_called = True

    def login(self, user, password):
        self.login_args = (user, password)

    def sendmail(self, from_addr, to_addrs, message):
        self.sendmail_args = (from_addr, to_addrs, message)


@pytest.fixture(autouse=True)
def _reset_fake_smtp():
    _FakeSMTP.instances = []
    yield
    _FakeSMTP.instances = []


@pytest.fixture()
def fake_smtp(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    return _FakeSMTP


def test_smtp_provider_starttls_is_always_called(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.internal")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "email_from", "GSP Recruitment <info@gsprecruitment.nl>")

    msg = es.EmailMessage(to="jane@example.com", subject="Hoi", text="Body")
    asyncio.run(es.SmtpProvider().send(msg))

    assert len(_FakeSMTP.instances) == 1
    assert _FakeSMTP.instances[0].starttls_called is True


def test_smtp_provider_skips_login_when_smtp_user_unset(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_pass", "")

    msg = es.EmailMessage(to="jane@example.com", subject="Hoi", text="Body")
    asyncio.run(es.SmtpProvider().send(msg))

    assert _FakeSMTP.instances[0].login_args is None


def test_smtp_provider_logs_in_when_smtp_user_is_set(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_user", "relay-user")
    monkeypatch.setattr(settings, "smtp_pass", "relay-pass")

    msg = es.EmailMessage(to="jane@example.com", subject="Hoi", text="Body")
    asyncio.run(es.SmtpProvider().send(msg))

    assert _FakeSMTP.instances[0].login_args == ("relay-user", "relay-pass")


def test_smtp_provider_sets_from_and_reply_to(fake_smtp, monkeypatch):
    monkeypatch.setattr(settings, "email_from", "GSP Recruitment <info@gsprecruitment.nl>")
    monkeypatch.setattr(settings, "smtp_user", "")

    msg = es.EmailMessage(to="jane@example.com", subject="Hoi", text="Body", reply_to="info@gsprecruitment.nl")
    asyncio.run(es.SmtpProvider().send(msg))

    from_addr, to_addrs, raw_message = _FakeSMTP.instances[0].sendmail_args
    assert from_addr == "GSP Recruitment <info@gsprecruitment.nl>"
    assert to_addrs == ["jane@example.com"]
    assert "From: GSP Recruitment <info@gsprecruitment.nl>" in raw_message
    assert "Reply-To: info@gsprecruitment.nl" in raw_message
    assert "To: jane@example.com" in raw_message


def test_smtp_provider_connection_error_is_retryable(monkeypatch):
    def _raise_connect(*a, **kw):
        raise smtplib.SMTPConnectError(421, "Cannot connect")
    monkeypatch.setattr(smtplib, "SMTP", _raise_connect)

    msg = es.EmailMessage(to="jane@example.com", subject="Hoi", text="Body")
    with pytest.raises(es.EmailSendError) as exc_info:
        asyncio.run(es.SmtpProvider().send(msg))
    assert exc_info.value.retryable is True


def test_smtp_provider_5xx_response_is_retryable(monkeypatch):
    def _raise_5xx(*a, **kw):
        raise smtplib.SMTPResponseException(554, "Transaction failed")
    monkeypatch.setattr(smtplib, "SMTP", _raise_5xx)

    msg = es.EmailMessage(to="jane@example.com", subject="Hoi", text="Body")
    with pytest.raises(es.EmailSendError) as exc_info:
        asyncio.run(es.SmtpProvider().send(msg))
    assert exc_info.value.retryable is True


def test_smtp_provider_4xx_response_is_not_retryable(monkeypatch):
    def _raise_4xx(*a, **kw):
        raise smtplib.SMTPResponseException(450, "Mailbox busy")
    monkeypatch.setattr(smtplib, "SMTP", _raise_4xx)

    msg = es.EmailMessage(to="jane@example.com", subject="Hoi", text="Body")
    with pytest.raises(es.EmailSendError) as exc_info:
        asyncio.run(es.SmtpProvider().send(msg))
    assert exc_info.value.retryable is False


def test_smtp_provider_error_never_contains_the_address(monkeypatch):
    def _raise(*a, **kw):
        raise smtplib.SMTPRecipientsRefused({"jane@example.com": (550, b"no such user")})
    monkeypatch.setattr(smtplib, "SMTP", _raise)

    msg = es.EmailMessage(to="jane@example.com", subject="Hoi", text="Body")
    with pytest.raises(es.EmailSendError) as exc_info:
        asyncio.run(es.SmtpProvider().send(msg))
    assert "jane@example.com" not in str(exc_info.value)


# ── GmailApiProvider: behaviourally unchanged ─────────────────────────────

def test_gmail_provider_raises_non_retryable_without_credentials(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_client_secret", "")
    monkeypatch.setattr(settings, "google_refresh_token", "")

    msg = es.EmailMessage(to="jane@example.com", subject="Hoi", text="Body")
    with pytest.raises(es.EmailSendError) as exc_info:
        asyncio.run(es.GmailApiProvider().send(msg))
    assert exc_info.value.retryable is False


class _FakeHttpxResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


class _FakeAsyncClient:
    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise = raise_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *a, **kw):
        if self._raise:
            raise self._raise
        return self._response


class _FakeCredentials:
    token = "fake-access-token"


def _stub_credentials(monkeypatch, provider):
    """GmailApiProvider._get_credentials() does a real, blocking
    creds.refresh() network call -- stub it out so send() reaches the
    Gmail-API httpx.post() call these tests actually exercise."""
    monkeypatch.setattr(provider, "_get_credentials", lambda: _FakeCredentials())


def test_gmail_provider_200_returns_message_id(monkeypatch):
    provider = es.GmailApiProvider()
    _stub_credentials(monkeypatch, provider)
    monkeypatch.setattr(
        es.httpx, "AsyncClient",
        lambda *a, **kw: _FakeAsyncClient(response=_FakeHttpxResponse(200, {"id": "msg-123"})),
    )
    msg = es.EmailMessage(to="jane@example.com", subject="Hoi", text="Body")
    result = asyncio.run(provider.send(msg))
    assert result == "msg-123"


def test_gmail_provider_5xx_is_retryable(monkeypatch):
    provider = es.GmailApiProvider()
    _stub_credentials(monkeypatch, provider)
    monkeypatch.setattr(
        es.httpx, "AsyncClient",
        lambda *a, **kw: _FakeAsyncClient(response=_FakeHttpxResponse(503, text="upstream down")),
    )
    msg = es.EmailMessage(to="jane@example.com", subject="Hoi", text="Body")
    with pytest.raises(es.EmailSendError) as exc_info:
        asyncio.run(provider.send(msg))
    assert exc_info.value.retryable is True


def test_gmail_provider_4xx_is_not_retryable(monkeypatch):
    provider = es.GmailApiProvider()
    _stub_credentials(monkeypatch, provider)
    monkeypatch.setattr(
        es.httpx, "AsyncClient",
        lambda *a, **kw: _FakeAsyncClient(response=_FakeHttpxResponse(400, text="bad request")),
    )
    msg = es.EmailMessage(to="jane@example.com", subject="Hoi", text="Body")
    with pytest.raises(es.EmailSendError) as exc_info:
        asyncio.run(provider.send(msg))
    assert exc_info.value.retryable is False


# ── Retry / backoff (EmailService._send_with_retry) ──────────────────────

class _FlakyProvider:
    """Fails `fail_times` times with a retryable error, then succeeds."""
    name = "fake"

    def __init__(self, fail_times, retryable=True, message="boom"):
        self.fail_times = fail_times
        self.retryable = retryable
        self.message = message
        self.calls = 0

    async def send(self, msg):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise es.EmailSendError(self.message, retryable=self.retryable)
        return "sent-id"


def test_retries_on_retryable_failure_then_succeeds(monkeypatch):
    sleeps = _no_sleep(monkeypatch)
    rows = _no_op_log(monkeypatch)
    provider = _FlakyProvider(fail_times=2, retryable=True)
    monkeypatch.setattr(es, "_get_provider", lambda: provider)

    ok = asyncio.run(es.EmailService().send_email("jane@example.com", "Hoi", "Body"))

    assert ok is True
    assert provider.calls == 3
    # backoff 0.5s, 2s before attempts 2 and 3 -- never more than the
    # spec'd three retries' worth of delays.
    assert sleeps == [0.5, 2.0]
    # One failed + one failed + one sent row.
    statuses = [row[2] for row in rows]
    assert statuses == ["failed", "failed", "sent"]


def test_never_retries_a_non_retryable_failure(monkeypatch):
    sleeps = _no_sleep(monkeypatch)
    rows = _no_op_log(monkeypatch)
    provider = _FlakyProvider(fail_times=99, retryable=False)
    monkeypatch.setattr(es, "_get_provider", lambda: provider)

    ok = asyncio.run(es.EmailService().send_email("jane@example.com", "Hoi", "Body"))

    assert ok is False
    assert provider.calls == 1
    assert sleeps == []
    assert len(rows) == 1
    assert rows[0][2] == "failed"


def test_gives_up_after_three_retries_all_retryable(monkeypatch):
    sleeps = _no_sleep(monkeypatch)
    rows = _no_op_log(monkeypatch)
    provider = _FlakyProvider(fail_times=99, retryable=True)
    monkeypatch.setattr(es, "_get_provider", lambda: provider)

    ok = asyncio.run(es.EmailService().send_email("jane@example.com", "Hoi", "Body"))

    assert ok is False
    # attempt 1 + 3 retries = 4 calls total, matching RETRY_BACKOFFS having 3 entries.
    assert provider.calls == 4
    assert sleeps == [0.5, 2.0, 8.0]
    assert len(rows) == 4
    assert all(row[2] == "failed" for row in rows)


def test_email_log_row_never_carries_the_raw_address(monkeypatch):
    rows = _no_op_log(monkeypatch)
    provider = _FlakyProvider(fail_times=0, retryable=True)
    monkeypatch.setattr(es, "_get_provider", lambda: provider)

    asyncio.run(es.EmailService().send_email("jane.doe@example.com", "Hoi", "Body"))

    assert len(rows) == 1
    template, to_hash, status, provider_name, provider_id, error = rows[0]
    assert to_hash == privacy.email_hash("jane.doe@example.com")
    assert "jane.doe@example.com" not in str(rows[0])
    assert status == "sent"
    assert provider_name == "fake"


def test_email_log_error_column_is_redacted(monkeypatch):
    rows = _no_op_log(monkeypatch)
    provider = _FlakyProvider(fail_times=99, retryable=False, message="SMTP error: rcpt to jane.doe@example.com refused")
    monkeypatch.setattr(es, "_get_provider", lambda: provider)

    asyncio.run(es.EmailService().send_email("jane.doe@example.com", "Hoi", "Body"))

    assert len(rows) == 1
    error_column = rows[0][5]
    assert "jane.doe@example.com" not in error_column
    assert "[redacted:" in error_column


def test_send_template_renders_and_sends(monkeypatch):
    rows = _no_op_log(monkeypatch)
    provider = _FlakyProvider(fail_times=0, retryable=True)
    monkeypatch.setattr(es, "_get_provider", lambda: provider)

    ok = asyncio.run(es.EmailService().send_template(
        "verify_email", "jane@example.com", {"full_name": "Jane", "link": "https://x/y", "ttl_hours": 1},
    ))

    assert ok is True
    assert rows[0][0] == "verify_email"  # template column


def test_send_email_signature_unchanged_for_existing_call_sites():
    """The six existing call sites (routers/auth.py, routers/client.py,
    routers/outreach.py, routers/public.py, services/scheduler.py) call
    send_email(to_email=..., subject=..., body_text=..., to_name=...) --
    this must keep working."""
    import inspect
    sig = inspect.signature(es.EmailService.send_email)
    params = list(sig.parameters)
    assert params[:4] == ["self", "to_email", "subject", "body_text"]
    assert "to_name" in sig.parameters


def test_provider_selection_defaults_to_gmail(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "gmail")
    assert isinstance(es._get_provider(), es.GmailApiProvider)


def test_provider_selection_smtp(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "smtp")
    assert isinstance(es._get_provider(), es.SmtpProvider)


# ── Logger calls never carry the recipient's address ──────────────────────

def test_gmail_credential_refresh_failure_is_not_logged_with_the_address(monkeypatch, caplog):
    """_get_credentials()'s own logger.error() call must never leak an
    e-mail address even though it only ever logs the OAuth error, not a
    recipient -- regression guard for the redact_emails() wrap added in
    this spoor."""
    class _BoomCreds:
        def refresh(self, request):
            raise Exception("token refresh failed for someuser@example.com")

    monkeypatch.setattr(settings, "google_client_id", "id")
    monkeypatch.setattr(settings, "google_client_secret", "secret")
    monkeypatch.setattr(settings, "google_refresh_token", "refresh")
    monkeypatch.setattr(es, "Credentials", lambda **kw: _BoomCreds())

    provider = es.GmailApiProvider()
    with caplog.at_level("ERROR", logger="talent_os.email"):
        result = provider._get_credentials()
    assert result is None
    assert "someuser@example.com" not in caplog.text
