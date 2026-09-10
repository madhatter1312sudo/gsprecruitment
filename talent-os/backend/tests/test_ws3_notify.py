"""
WS3 -- services/notify.py: notify_owner() best-effort fan-out to Telegram
(never PII) and an optional owner e-mail (OWNER_NOTIFY_EMAIL).

Pure unit tests: services.telegram._send and services.email_service.
email_service.send_template are monkeypatched directly, no DB/network.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

import pytest

from core.config import settings
import services.notify as notify_module
from services import telegram


@pytest.fixture()
def fake_telegram(monkeypatch):
    calls = []

    async def _fake_send(text):
        calls.append(text)
        return True

    monkeypatch.setattr(telegram, "_send", _fake_send)
    return calls


@pytest.fixture()
def fake_send_template(monkeypatch):
    calls = []

    async def _fake(name, to_email, ctx, lang="nl"):
        calls.append({"name": name, "to_email": to_email, "ctx": ctx})
        return True

    monkeypatch.setattr(notify_module.email_service, "send_template", _fake)
    return calls


def test_lead_event_calls_notify_lead_unchanged(fake_telegram, fake_send_template, monkeypatch):
    """The "lead" event must produce the exact same Telegram text
    telegram.notify_lead() always has -- routers/public.py's call moved
    into notify_owner(), but the wire text must not change."""
    monkeypatch.setattr(settings, "owner_notify_email", "")
    from datetime import datetime, timezone
    when = datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)

    asyncio.run(notify_module.notify_owner("lead", {
        "interest_type": "embedded_vacature", "submitted_at": when,
        "full_name": "Jane Doe", "email": "jane@example.com",
    }))

    assert len(fake_telegram) == 1
    assert fake_telegram[0] == "New lead (embedded_vacature) at 2026-01-15 10:30 UTC"
    # No name/e-mail anywhere in the Telegram text.
    assert "Jane" not in fake_telegram[0]
    assert "example.com" not in fake_telegram[0]


@pytest.mark.parametrize("event", [
    "candidate_registered", "client_registered", "google_signup", "talentpool_confirmed", "client_job_created",
])
def test_telegram_never_carries_name_or_email(event, fake_telegram, fake_send_template, monkeypatch):
    monkeypatch.setattr(settings, "owner_notify_email", "")
    asyncio.run(notify_module.notify_owner(event, {
        "full_name": "Jane Doe", "email": "jane.doe@example.com", "job_title": "Senior Embedded Engineer",
        "company": "Acme B.V.",
    }))
    assert len(fake_telegram) == 1
    text = fake_telegram[0]
    assert "Jane" not in text
    assert "jane.doe@example.com" not in text
    assert "Senior Embedded Engineer" not in text
    assert "Acme" not in text


def test_no_owner_email_without_owner_notify_email_setting(fake_telegram, fake_send_template, monkeypatch):
    monkeypatch.setattr(settings, "owner_notify_email", "")
    asyncio.run(notify_module.notify_owner("lead", {"interest_type": "x", "full_name": "Jane"}))
    assert len(fake_telegram) == 1
    assert len(fake_send_template) == 0


def test_owner_email_sent_when_configured(fake_telegram, fake_send_template, monkeypatch):
    monkeypatch.setattr(settings, "owner_notify_email", "owner@gsprecruitment.nl")
    monkeypatch.setattr(settings, "frontend_url", "https://gsprecruitment.nl")
    asyncio.run(notify_module.notify_owner("lead", {
        "interest_type": "embedded_vacature", "full_name": "Jane Doe", "email": "jane@example.com", "anchor": "leads",
    }))
    assert len(fake_send_template) == 1
    call = fake_send_template[0]
    assert call["name"] == "owner_notify"
    assert call["to_email"] == "owner@gsprecruitment.nl"
    # Unlike Telegram, the owner e-mail MAY carry name/interest -- it's an
    # internal notification to the owner, not a message about them sent
    # to someone else.
    assert "Jane Doe" in call["ctx"]["detail"]
    assert call["ctx"]["deeplink"] == "https://gsprecruitment.nl/admin/#leads"


def test_owner_email_never_carries_the_address_or_company(fake_telegram, fake_send_template, monkeypatch):
    """Security-auditor MEDIUM (GDPR data minimisation): the owner e-mail
    may carry a name, interest or vacancy title plus the deeplink, never
    the e-mail address or a company name -- the deeplink already opens
    the record in the admin panel, and a copy of the address in the
    owner's mailbox (at Google or elsewhere) is a second, unmanaged copy
    that a GDPR erasure request in the admin panel never reaches."""
    monkeypatch.setattr(settings, "owner_notify_email", "owner@gsprecruitment.nl")
    asyncio.run(notify_module.notify_owner("lead", {
        "interest_type": "embedded_vacature",
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "company": "Acme BV",
        "anchor": "leads",
    }))
    detail = fake_send_template[0]["ctx"]["detail"]
    assert "Jane Doe" in detail
    assert "jane@example.com" not in detail
    assert "Acme BV" not in detail
    assert "E-mail" not in detail
    assert "Bedrijf" not in detail


def test_owner_email_uses_candidates_anchor_when_given(fake_telegram, fake_send_template, monkeypatch):
    monkeypatch.setattr(settings, "owner_notify_email", "owner@gsprecruitment.nl")
    asyncio.run(notify_module.notify_owner("talentpool_confirmed", {"job_title": "Firmware Engineer", "anchor": "candidates"}))
    assert fake_send_template[0]["ctx"]["deeplink"].endswith("#candidates")


def test_notify_owner_never_raises_when_telegram_fails(fake_send_template, monkeypatch):
    monkeypatch.setattr(settings, "owner_notify_email", "")

    async def _boom(text):
        raise RuntimeError("Telegram is down")
    monkeypatch.setattr(telegram, "_send", _boom)

    # Must not raise -- a failing Telegram call can never fail the
    # lead/register/confirm endpoint that called notify_owner().
    asyncio.run(notify_module.notify_owner("lead", {"interest_type": "x"}))


def test_notify_owner_never_raises_when_owner_email_fails(fake_telegram, monkeypatch):
    monkeypatch.setattr(settings, "owner_notify_email", "owner@gsprecruitment.nl")

    async def _boom(name, to_email, ctx, lang="nl"):
        raise RuntimeError("Gmail API is down")
    monkeypatch.setattr(notify_module.email_service, "send_template", _boom)

    asyncio.run(notify_module.notify_owner("lead", {"interest_type": "x"}))
    # Telegram side must still have run despite the e-mail side failing.
    assert len(fake_telegram) == 1


def test_notify_owner_with_no_fields_still_sends_telegram(fake_telegram, fake_send_template, monkeypatch):
    monkeypatch.setattr(settings, "owner_notify_email", "")
    asyncio.run(notify_module.notify_owner("client_job_created"))
    assert len(fake_telegram) == 1


def test_unknown_event_falls_back_to_its_own_key_as_label(fake_telegram, fake_send_template, monkeypatch):
    monkeypatch.setattr(settings, "owner_notify_email", "")
    asyncio.run(notify_module.notify_owner("some_future_event", {}))
    assert "some_future_event" in fake_telegram[0]
