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


# ── security-audit follow-up (finding 4): a mangled/translated token is no
# longer "repaired" by a loose pattern match -- draft_email() now requires
# the *exact* placeholder exactly once, and refuses (raises) otherwise.
# These three tests used to assert that a bracket/bare-word/mixed-case
# variant got silently substituted; that leniency is exactly what let a
# model-mangled token (e.g. a translated "{{ONTVANGER_NAAM}}") slip through
# undetected. Inverted per the audit: any of these must now fail closed.

def test_bracket_variant_placeholder_is_refused_not_repaired(fake_client):
    _set_model_reply("Beste [RECIPIENT_NAME], welkom.")
    with pytest.raises(outreach_ai.DraftGenerationError):
        asyncio.run(outreach_ai.draft_email(
            target={"name": "Jan de Vries"}, context={}, language="nl",
        ))


def test_bare_word_placeholder_variant_is_refused_not_repaired(fake_client):
    _set_model_reply("Beste recipient_name, welkom.")
    with pytest.raises(outreach_ai.DraftGenerationError):
        asyncio.run(outreach_ai.draft_email(
            target={"name": "Jan de Vries"}, context={}, language="nl",
        ))


def test_mixed_case_braces_variant_is_refused_not_repaired(fake_client):
    _set_model_reply("Beste {{ Recipient_Name }}, welkom.")
    with pytest.raises(outreach_ai.DraftGenerationError):
        asyncio.run(outreach_ai.draft_email(
            target={"name": "Jan de Vries"}, context={}, language="nl",
        ))


def test_translated_token_is_refused(fake_client):
    # The concrete scenario finding 4 names: the model translates the token
    # into something _PLACEHOLDER_LEAK_RE's literal "recipient_name" match
    # would never recognise. The exact-count check in draft_email() catches
    # this regardless -- zero occurrences of the real token is still "not
    # exactly one".
    _set_model_reply("Beste {{ONTVANGER_NAAM}}, welkom.")
    with pytest.raises(outreach_ai.DraftGenerationError):
        asyncio.run(outreach_ai.draft_email(
            target={"name": "Jan de Vries"}, context={}, language="nl",
        ))


def test_missing_placeholder_entirely_is_refused(fake_client):
    _set_model_reply("Beste, welkom bij GSP Recruitment.")
    with pytest.raises(outreach_ai.DraftGenerationError):
        asyncio.run(outreach_ai.draft_email(
            target={"name": "Jan de Vries"}, context={}, language="nl",
        ))


def test_placeholder_used_twice_is_refused(fake_client):
    _set_model_reply(
        f"Beste {outreach_ai.NAME_PLACEHOLDER}, nogmaals {outreach_ai.NAME_PLACEHOLDER}."
    )
    with pytest.raises(outreach_ai.DraftGenerationError):
        asyncio.run(outreach_ai.draft_email(
            target={"name": "Jan de Vries"}, context={}, language="nl",
        ))


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


def test_contains_placeholder_leak_true_for_a_translated_or_mangled_token():
    # security-audit follow-up (finding 4): a generic {{...}} shape is
    # caught even when its contents don't spell "recipient_name" at all.
    assert outreach_ai.contains_placeholder_leak("Beste {{ONTVANGER_NAAM}},") is True
    assert outreach_ai.contains_placeholder_leak("Dear {{ RECIPIENT NAME }},") is True


# ── security-audit follow-up (finding 9): a name with a backslash must
# never trip re.sub's backreference syntax ─────────────────────────────────

def test_fill_recipient_name_handles_a_backslash_in_the_name():
    text = f"Beste {outreach_ai.NAME_PLACEHOLDER},"
    # re.sub(pattern, name, text) would raise re.error on the "\1" below
    # (interpreted as a backreference); the lambda-based substitution must
    # not raise, and must insert the name literally.
    out = outreach_ai._fill_recipient_name(text, r"Jan \1 de Vries")
    assert out == "Beste Jan \\1 de Vries,"
