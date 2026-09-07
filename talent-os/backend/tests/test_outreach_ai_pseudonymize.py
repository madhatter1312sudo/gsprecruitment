"""
Unit tests for services/outreach_ai.py's name-placeholder scheme
(VERWERKINGSREGISTER.md §1.3, OpenRouter-rij): the recipient's real name
must never be sent to OpenRouter. draft_email() sends only NAME_PLACEHOLDER
in the prompt and fills in the real name itself, locally, after the model
has replied -- and a placeholder must never survive into the returned
draft.

No real network call: httpx.AsyncClient is monkeypatched to a tiny fake
that returns a canned chat-completion response and records the outgoing
payload, so we can assert on exactly what was (and wasn't) sent.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from services import outreach_ai


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Records the last request payload and returns a canned model reply.
    Swapped in for httpx.AsyncClient — draft_email() uses it as an async
    context manager and calls .post(path, json=payload)."""

    last_payload = None
    model_reply_body = '{"subject": "Interessante rol", "body": "placeholder"}'

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, path, json):
        type(self).last_payload = json
        return _FakeResponse({
            "choices": [{"message": {"content": type(self).model_reply_body}}],
        })


@pytest.fixture()
def fake_client(monkeypatch):
    monkeypatch.setattr(outreach_ai.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(outreach_ai.settings, "openrouter_chat_model", "test/model")
    monkeypatch.setattr(outreach_ai.settings, "openrouter_base_url", "https://example.invalid")
    monkeypatch.setattr(outreach_ai.settings, "openrouter_api_key", "test-key")
    return _FakeAsyncClient


def _set_model_reply(body_text: str):
    _FakeAsyncClient.model_reply_body = json.dumps({"subject": "Interessante rol", "body": body_text})


# ── the real name is never sent to OpenRouter ─────────────────────────────

def test_real_name_never_appears_in_the_outgoing_prompt(fake_client):
    _set_model_reply(f"Beste {outreach_ai.NAME_PLACEHOLDER}, ...")
    asyncio.run(outreach_ai.draft_email(
        target={"name": "Fatima Al-Sayed", "company": "ASML"},
        context={"job_title": "Embedded Engineer", "job_company": "NXP"},
        language="nl",
    ))
    sent = json.dumps(fake_client.last_payload)
    assert "Fatima" not in sent
    assert "Al-Sayed" not in sent
    assert outreach_ai.NAME_PLACEHOLDER in sent  # the placeholder itself IS sent


def test_full_name_field_also_never_sent(fake_client):
    _set_model_reply(f"Beste {outreach_ai.NAME_PLACEHOLDER}, ...")
    asyncio.run(outreach_ai.draft_email(
        target={"full_name": "Nguyễn Văn Minh", "company": "ASML"},
        context={},
        language="nl",
    ))
    sent = json.dumps(fake_client.last_payload)
    assert "Nguyễn" not in sent
    assert "Minh" not in sent


# ── the placeholder is always substituted before the draft is returned ────

def test_placeholder_is_replaced_with_the_real_name_in_body(fake_client):
    _set_model_reply(f"Beste {outreach_ai.NAME_PLACEHOLDER},\n\nWe hebben een rol...")
    draft = asyncio.run(outreach_ai.draft_email(
        target={"name": "Jan de Vries", "company": "ASML"},
        context={}, language="nl",
    ))
    assert "Jan de Vries" in draft["body"]
    assert outreach_ai.NAME_PLACEHOLDER not in draft["body"]


def test_placeholder_replaced_in_subject_too(fake_client):
    _FakeAsyncClient.model_reply_body = json.dumps({
        "subject": f"Hallo {outreach_ai.NAME_PLACEHOLDER}", "body": "Tekst zonder placeholder.",
    })
    draft = asyncio.run(outreach_ai.draft_email(
        target={"name": "Aisha Al-Farsi"}, context={}, language="nl",
    ))
    assert "Aisha Al-Farsi" in draft["subject"]
    assert outreach_ai.NAME_PLACEHOLDER not in draft["subject"]


def test_missing_name_falls_back_to_neutral_greeting_not_the_placeholder(fake_client):
    _set_model_reply(f"Beste {outreach_ai.NAME_PLACEHOLDER},")
    draft = asyncio.run(outreach_ai.draft_email(target={}, context={}, language="nl"))
    assert outreach_ai.NAME_PLACEHOLDER not in draft["body"]
    assert "daar" in draft["body"]


def test_missing_name_english_fallback(fake_client):
    _set_model_reply(f"Dear {outreach_ai.NAME_PLACEHOLDER},")
    draft = asyncio.run(outreach_ai.draft_email(target={}, context={}, language="en"))
    assert outreach_ai.NAME_PLACEHOLDER not in draft["body"]
    assert "there" in draft["body"]


# ── mangled/mixed-case placeholder variants also get caught ───────────────

def test_bracket_variant_placeholder_is_also_replaced(fake_client):
    _set_model_reply("Beste [RECIPIENT_NAME], welkom.")
    draft = asyncio.run(outreach_ai.draft_email(
        target={"name": "Jan de Vries"}, context={}, language="nl",
    ))
    assert "[RECIPIENT_NAME]" not in draft["body"]
    assert "Jan de Vries" in draft["body"]


def test_bare_word_placeholder_variant_is_also_replaced(fake_client):
    _set_model_reply("Beste recipient_name, welkom.")
    draft = asyncio.run(outreach_ai.draft_email(
        target={"name": "Jan de Vries"}, context={}, language="nl",
    ))
    assert "recipient_name" not in draft["body"].lower()


def test_mixed_case_braces_variant_is_also_replaced(fake_client):
    _set_model_reply("Beste {{ Recipient_Name }}, welkom.")
    draft = asyncio.run(outreach_ai.draft_email(
        target={"name": "Jan de Vries"}, context={}, language="nl",
    ))
    assert "recipient_name" not in draft["body"].lower()
    assert "Jan de Vries" in draft["body"]


# ── contains_placeholder_leak(): the storage/approval fail-closed check ───

def test_contains_placeholder_leak_true_for_exact_token():
    assert outreach_ai.contains_placeholder_leak("Beste {{RECIPIENT_NAME}},") is True


def test_contains_placeholder_leak_true_for_bare_word_any_case():
    assert outreach_ai.contains_placeholder_leak("Hello RECIPIENT_NAME") is True
    assert outreach_ai.contains_placeholder_leak("hello Recipient_Name") is True


def test_contains_placeholder_leak_false_for_a_normal_filled_draft():
    assert outreach_ai.contains_placeholder_leak("Beste Jan de Vries,", "We hebben een rol.") is False


def test_contains_placeholder_leak_checks_every_argument():
    assert outreach_ai.contains_placeholder_leak("clean subject", "body has {{RECIPIENT_NAME}}") is True


def test_contains_placeholder_leak_handles_none_args():
    assert outreach_ai.contains_placeholder_leak(None, "clean") is False
