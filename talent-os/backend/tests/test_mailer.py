"""Tests for services/mailer.py -- no network, no DB.

Covers: template rendering (Dutch content, ctx interpolation, no stray
{{ }}), subject resolution (explicit arg vs. template {% block subject %}),
the fallback-chain decision logic (resolve_transport, a pure helper), and
the shape of the email_log row a send writes (via a stubbed core.database
execute).
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.config import settings
from services import mailer


# ── render_template ──────────────────────────────────────────────────────

def test_wachtwoord_reset_html_renders_dutch_content_and_ctx():
    html_body, text_body = mailer.render_template(
        "wachtwoord_reset",
        {"reset_url": "https://gsprecruitment.nl/reset-password?token=abc123", "expires_minutes": 60},
    )
    assert "Wachtwoordreset" in html_body or "wachtwoordreset" in html_body
    assert "https://gsprecruitment.nl/reset-password?token=abc123" in html_body
    assert "60" in html_body
    # No unrendered Jinja expressions leaked into the output.
    assert "{{" not in html_body and "}}" not in html_body
    assert text_body is not None
    assert "https://gsprecruitment.nl/reset-password?token=abc123" in text_body
    assert "{{" not in text_body and "}}" not in text_body


def test_welkom_kandidaat_interpolates_full_name():
    html_body, text_body = mailer.render_template("welkom_kandidaat", {"full_name": "Jan de Vries"})
    assert "Jan de Vries" in html_body
    assert "Jan de Vries" in text_body
    assert "{{" not in html_body and "{{" not in text_body


def test_render_template_missing_txt_fallback_returns_none():
    # base.html has no .txt sibling.
    html_body, text_body = mailer.render_template("base", {})
    assert html_body
    assert text_body is None


def test_render_template_unknown_template_raises():
    from jinja2 import TemplateNotFound
    with pytest.raises(TemplateNotFound):
        mailer.render_template("does_not_exist", {})


# ── resolve_subject ──────────────────────────────────────────────────────

def test_resolve_subject_explicit_arg_wins():
    subject = mailer.resolve_subject("wachtwoord_reset", {"reset_url": "x", "expires_minutes": 60}, "Custom subject")
    assert subject == "Custom subject"


def test_resolve_subject_falls_back_to_template_block():
    subject = mailer.resolve_subject("wachtwoord_reset", {"reset_url": "x", "expires_minutes": 60})
    assert "Wachtwoord" in subject
    assert "GSP Recruitment" in subject


def test_resolve_subject_welkom_kandidaat_block():
    subject = mailer.resolve_subject("welkom_kandidaat", {"full_name": "Jan"})
    assert "Welkom" in subject


# ── fallback-chain decision logic (resolve_transport) ────────────────────

def test_resolve_transport_prefers_smtp_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "info@gsprecruitment.nl")
    monkeypatch.setattr(settings, "smtp_pass", "app-password")
    monkeypatch.setattr(settings, "google_client_id", "x")
    monkeypatch.setattr(settings, "google_client_secret", "x")
    monkeypatch.setattr(settings, "google_refresh_token", "x")
    assert mailer.resolve_transport() == "smtp"


def test_resolve_transport_falls_back_to_gmail_api_when_smtp_unset(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_pass", "")
    monkeypatch.setattr(settings, "google_client_id", "x")
    monkeypatch.setattr(settings, "google_client_secret", "x")
    monkeypatch.setattr(settings, "google_refresh_token", "x")
    assert mailer.resolve_transport() == "gmail_api"


def test_resolve_transport_none_when_both_unset(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_pass", "")
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_client_secret", "")
    monkeypatch.setattr(settings, "google_refresh_token", "")
    assert mailer.resolve_transport() == "none"


def test_smtp_is_configured_requires_all_three(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "info@gsprecruitment.nl")
    monkeypatch.setattr(settings, "smtp_pass", "")
    assert mailer.smtp_is_configured() is False


# ── send() writes an email_log row, whatever the outcome ────────────────

class _FakeExecuteRecorder:
    """Stand-in for core.database.execute -- records every call's SQL/args
    instead of touching a real connection pool."""

    def __init__(self):
        self.calls = []

    async def __call__(self, sql, *args):
        self.calls.append((sql, args))


@pytest.fixture(autouse=True)
def _no_transport(monkeypatch):
    """Force resolve_transport() -> 'none' so send()/send_raw() take the
    no-transport-configured branch by default in these DB-shape tests --
    SMTP/Gmail transports themselves aren't exercised here (no network)."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_pass", "")
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_client_secret", "")
    monkeypatch.setattr(settings, "google_refresh_token", "")
    yield


def test_send_with_no_transport_writes_failed_email_log_row(monkeypatch):
    recorder = _FakeExecuteRecorder()
    monkeypatch.setattr(mailer, "execute", recorder)

    ok = asyncio.run(
        mailer.send(
            to="kandidaat@example.com",
            template="welkom_kandidaat",
            ctx={"full_name": "Jan de Vries"},
            related_user_id=42,
        )
    )
    assert ok is False
    assert len(recorder.calls) == 1
    sql, args = recorder.calls[0]
    assert "INSERT INTO email_log" in sql
    to_email, template, subject, provider, status, error, related_user_id = args
    assert to_email == "kandidaat@example.com"
    assert template == "welkom_kandidaat"
    assert "Welkom" in subject
    assert provider == "none"
    assert status == "failed"
    assert error  # non-empty explanation, never a credential
    assert "pass" not in error.lower() and "secret" not in error.lower()
    assert related_user_id == 42


def test_send_raw_with_no_transport_writes_failed_email_log_row(monkeypatch):
    recorder = _FakeExecuteRecorder()
    monkeypatch.setattr(mailer, "execute", recorder)

    ok = asyncio.run(
        mailer.send_raw(to="prospect@example.com", subject="Over jullie team", body="Beste,\n\n...")
    )
    assert ok is False
    assert len(recorder.calls) == 1
    sql, args = recorder.calls[0]
    assert "INSERT INTO email_log" in sql
    to_email, template, subject, provider, status, error, related_user_id = args
    assert to_email == "prospect@example.com"
    assert template == "outreach_raw"
    assert subject == "Over jullie team"
    assert status == "failed"
    assert related_user_id is None


def test_send_unknown_template_writes_failed_row_and_returns_false(monkeypatch):
    recorder = _FakeExecuteRecorder()
    monkeypatch.setattr(mailer, "execute", recorder)

    ok = asyncio.run(mailer.send(to="x@example.com", template="does_not_exist", ctx={}))
    assert ok is False
    assert len(recorder.calls) == 1
    sql, args = recorder.calls[0]
    status = args[4]
    error = args[5]
    assert status == "failed"
    assert "not found" in error.lower()


def test_email_log_insert_never_carries_smtp_credentials(monkeypatch):
    """Belt-and-braces: even if settings happened to be configured, the
    values passed to execute() must never include the SMTP password."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    monkeypatch.setattr(settings, "smtp_user", "info@gsprecruitment.nl")
    monkeypatch.setattr(settings, "smtp_pass", "super-secret-app-password")
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "google_client_secret", "")
    monkeypatch.setattr(settings, "google_refresh_token", "")

    async def _boom_smtp_send(msg, **kwargs):
        raise ConnectionRefusedError("smtp.gmail.com:587 unreachable in test sandbox")

    recorder = _FakeExecuteRecorder()
    monkeypatch.setattr(mailer, "execute", recorder)
    monkeypatch.setattr(mailer.aiosmtplib, "send", _boom_smtp_send)

    ok = asyncio.run(
        mailer.send(to="kandidaat@example.com", template="welkom_kandidaat", ctx={"full_name": "Jan"})
    )
    assert ok is False
    sql, args = recorder.calls[0]
    assert not any("super-secret-app-password" in str(a) for a in args)


def test_no_template_leaves_double_curly_braces_anywhere():
    """Sweep every shipped template for a stray unrendered {{ }} once
    rendered with representative context -- guards against a typo'd
    variable name silently shipping to a real inbox."""
    fixtures = {
        "wachtwoord_reset": {"reset_url": "https://gsprecruitment.nl/reset-password?token=abc", "expires_minutes": 60},
        "welkom_kandidaat": {"full_name": "Jan de Vries"},
    }
    for template, ctx in fixtures.items():
        html_body, text_body = mailer.render_template(template, ctx)
        assert not re.search(r"\{\{.*?\}\}", html_body), f"{template}.html has unrendered {{}}"
        if text_body:
            assert not re.search(r"\{\{.*?\}\}", text_body), f"{template}.txt has unrendered {{}}"
