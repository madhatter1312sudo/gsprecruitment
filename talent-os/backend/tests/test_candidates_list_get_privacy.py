"""
FIX 2 (chief-of-staff, ai-pseudonimisering branch): GET /api/candidates and
GET /api/candidates/{id} sit behind the same X-API-Key the external Claude
routines use. They used to run `SELECT *`, which returned cv_text and did
not filter out soft-deleted rows or rows with withdrawn consent.

Pure unit test: core.database's fetch_one/fetch_all are monkeypatched
directly on the routers.candidates module (no DB needed) -- asserts the
SQL sent actually carries the two required guards and never selects
cv_text. tests/integration/test_candidates_privacy.py is the real-DB
companion that proves the guards actually filter rows.
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

from routers import candidates


def _row(**overrides):
    base = {
        "id": 1, "full_name": "Test Candidate", "email": "test@example.com",
        "phone": None, "linkedin_url": None, "github_url": None, "portfolio_url": None,
        "current_company": None, "current_title": "Embedded Engineer", "location": None,
        "willing_to_relocate": False, "salary_expectation_min": None,
        "salary_expectation_max": None, "notice_period_days": None,
        "years_experience": None, "skills": None, "languages": None, "education": None,
        "source": "apollo", "source_url": None, "lawful_basis": None, "date_found": None,
        "sourced_by_agent": None, "strength_score": None, "switch_readiness": None,
        "tags": None, "status": "sourced", "is_passive": True, "screening_score": None,
        "screening_notes": None, "quality_score": None, "cv_file_path": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": None,
    }
    base.update(overrides)
    return base


@pytest.fixture()
def fake_db(monkeypatch):
    captured = {}

    async def fake_fetch_all(query, *args, **kwargs):
        captured["list_query"] = query
        captured["list_args"] = args
        return [_row()]

    async def fake_fetch_one(query, *args, **kwargs):
        captured["get_query"] = query
        captured["get_args"] = args
        return _row()

    monkeypatch.setattr(candidates, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(candidates, "fetch_one", fake_fetch_one)
    return captured


def test_list_candidates_query_excludes_deleted_and_withdrawn_no_cv_text(fake_db):
    asyncio.run(candidates.list_candidates())
    query = fake_db["list_query"]
    assert "deleted_at IS NULL" in query
    assert "consent_withdrawn_at IS NULL" in query
    assert "cv_text" not in query
    assert "SELECT *" not in query


def test_list_candidates_with_status_filter_still_excludes_deleted_and_withdrawn(fake_db):
    asyncio.run(candidates.list_candidates(status="sourced"))
    query = fake_db["list_query"]
    assert "deleted_at IS NULL" in query
    assert "consent_withdrawn_at IS NULL" in query
    assert "status = $1" in query
    assert "cv_text" not in query


def test_get_candidate_query_excludes_deleted_and_withdrawn_no_cv_text(fake_db):
    asyncio.run(candidates.get_candidate(candidate_id=1))
    query = fake_db["get_query"]
    assert "deleted_at IS NULL" in query
    assert "consent_withdrawn_at IS NULL" in query
    assert "cv_text" not in query
    assert "SELECT *" not in query

