"""
FIX 5 (chief-of-staff, ai-pseudonimisering branch): a row a draft job
refuses -- either draft_email() itself raising DraftGenerationError, or
the stored fail-closed contains_placeholder_leak() check -- used to
vanish into a log line with no signal in the returned dict. If the model
started mangling the placeholder structurally, drafted output would drop
to zero with nothing distinguishing "nothing to draft" from "everything
refused". This asserts the new `refused` counter actually counts both
refusal paths, in services/scheduler.py's draft_outreach() and
services/harvest.py's morning_drafts().

Pure unit tests: core.database is monkeypatched module-by-module (no DB
needed), same pattern as tests/test_matches_no_pii.py.
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

from services import outreach_ai


def _candidate_row(i):
    return {
        "candidate_id": i, "job_id": 100, "match_score": 80,
        "full_name": f"Candidate {i}", "email": f"candidate{i}@example.com",
        "current_company": "Acme", "job_title": "Embedded Engineer",
        "job_description": "C++ / FreeRTOS", "job_company": "Acme",
        # WS-4 (migrations/037): draft_outreach() now reads this to decide
        # whether to anonymise job_company -- False here, same as any
        # ordinary, named client.
        "job_client_internal": False,
    }


@pytest.fixture()
def three_candidates():
    return [_candidate_row(1), _candidate_row(2), _candidate_row(3)]


def test_scheduler_draft_outreach_counts_refused(monkeypatch, three_candidates):
    from services import scheduler

    async def fake_flag_enabled(key):
        return True

    async def fake_fetch_all(query, *args, **kwargs):
        return three_candidates

    executed = []

    async def fake_execute(query, *args, **kwargs):
        executed.append(args)

    call_state = {"n": 0}

    async def fake_draft_email(target, context, language="nl"):
        call_state["n"] += 1
        n = call_state["n"]
        if n == 1:
            # A clean draft: stores fine.
            return {"subject": "Hallo", "body": "Beste Candidate, ..."}
        if n == 2:
            # draft_email() itself refuses (placeholder used wrong number
            # of times) -- the DraftGenerationError path.
            raise outreach_ai.DraftGenerationError("wrong placeholder count")
        # A draft that slipped a template token past draft_email() --
        # the contains_placeholder_leak() fail-closed path.
        return {"subject": "Hallo {{RECIPIENT_NAME}}", "body": "Beste, ..."}

    monkeypatch.setattr(scheduler, "_flag_enabled", fake_flag_enabled)
    monkeypatch.setattr(scheduler, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(scheduler, "execute", fake_execute)
    monkeypatch.setattr(scheduler.outreach_ai, "draft_email", fake_draft_email)

    result = asyncio.run(scheduler.draft_outreach())

    assert result["considered"] == 3
    assert result["drafted"] == 1
    assert result["refused"] == 2
    assert len(executed) == 1


def test_harvest_morning_drafts_counts_and_sums_refused(monkeypatch, three_candidates):
    from services import harvest

    async def fake_flag_enabled(key):
        return True

    async def fake_fetch_all_candidates(query, *args, **kwargs):
        return three_candidates

    async def fake_fetch_all_prospects(query, *args, **kwargs):
        return [
            {"id": 1, "company_name": "Acme", "contact_name": "Prospect 1",
             "contact_title": "CTO", "contact_email": "p1@example.com",
             "contact_linkedin": None, "industry": "semiconductors"},
        ]

    async def fake_execute(query, *args, **kwargs):
        pass

    call_state = {"n": 0}

    async def fake_draft_email(target, context, language="nl"):
        call_state["n"] += 1
        n = call_state["n"]
        if n <= 2:
            raise outreach_ai.DraftGenerationError("wrong placeholder count")
        return {"subject": "Hallo", "body": "Beste, ..."}

    monkeypatch.setattr(harvest, "_flag_enabled", fake_flag_enabled)
    monkeypatch.setattr(harvest, "execute", fake_execute)
    monkeypatch.setattr(harvest.outreach_ai, "draft_email", fake_draft_email)

    # candidates query and prospects query are both fetch_all -- swap by
    # call order via a small dispatcher.
    calls = {"n": 0}

    async def fake_fetch_all(query, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return await fake_fetch_all_candidates(query, *args, **kwargs)
        return await fake_fetch_all_prospects(query, *args, **kwargs)

    monkeypatch.setattr(harvest, "fetch_all", fake_fetch_all)

    result = asyncio.run(harvest.morning_drafts())

    assert result["candidates"]["considered"] == 3
    assert result["candidates"]["refused"] == 2
    assert result["candidates"]["drafted"] == 1
    assert result["prospects"]["considered"] == 1
    assert result["prospects"]["drafted"] == 1
    assert result["prospects"]["refused"] == 0
    assert result["refused"] == 2


def test_contains_placeholder_leak_row_also_counted_as_refused(monkeypatch, three_candidates):
    """Distinct from the DraftGenerationError path: draft_email() returns
    normally but the returned text still carries a template token (e.g. a
    mangled/translated placeholder) -- the storage-time fail-closed check
    must also increment `refused`, not just skip silently."""
    from services import scheduler

    async def fake_flag_enabled(key):
        return True

    async def fake_fetch_all(query, *args, **kwargs):
        return three_candidates[:1]

    async def fake_execute(query, *args, **kwargs):
        raise AssertionError("must not store a draft with a leaked placeholder")

    async def fake_draft_email(target, context, language="nl"):
        return {"subject": "Hallo {{ONTVANGER_NAAM}}", "body": "Beste, ..."}

    monkeypatch.setattr(scheduler, "_flag_enabled", fake_flag_enabled)
    monkeypatch.setattr(scheduler, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(scheduler, "execute", fake_execute)
    monkeypatch.setattr(scheduler.outreach_ai, "draft_email", fake_draft_email)

    result = asyncio.run(scheduler.draft_outreach())

    assert result["drafted"] == 0
    assert result["refused"] == 1
