"""
FIX 2 / finding 8 follow-up (chief-of-staff, ai-pseudonimisering branch).

test_candidates_list_get_privacy.py calls routers.candidates.list_candidates()
/ get_candidate() directly -- a pure coroutine call that never goes through
FastAPI's response_model serialization. That is exactly the mechanism that
was supposed to strip cv_text (response_model_exclude, now replaced by a
dedicated CandidatePublicResponse model with no cv_text field at all): a
regression there -- reverting to response_model=CandidateResponse, or a
`{"cv_text"}` exclude spec, or cv_text sneaking back into the raw-SQL
column list -- would pass every test in that file untouched, because none
of them exercise real HTTP serialization.

This file closes that gap with fastapi.testclient.TestClient against the
real app (no live Postgres: core.database.fetch_all/fetch_one are
monkeypatched to return a stubbed row carrying cv_text, same as asyncpg
would if the column list ever regressed to `SELECT *`) and asserts the
JSON response actually sent over HTTP never carries cv_text.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "test-api-key-not-used-in-production")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

import pytest
from fastapi.testclient import TestClient

import main
from core.config import settings
from routers import candidates

client = TestClient(main.app)
HEADERS = {"X-API-Key": settings.api_key}

# Deliberately includes cv_text, the way a raw `SELECT *` row (or a
# from_attributes-populated CandidateResponse) would -- if any layer
# between the DB row and the HTTP response regresses, this is the value
# that would leak.
_STUB_ROW = {
    "id": 1, "full_name": "Test Candidate", "email": "test@example.com",
    "phone": None, "linkedin_url": None, "github_url": None, "portfolio_url": None,
    "current_company": None, "current_title": "Embedded Engineer", "location": None,
    "willing_to_relocate": False, "salary_expectation_min": None,
    "salary_expectation_max": None, "notice_period_days": None,
    "years_experience": None, "skills": None, "languages": None, "education": None,
    "cv_text": "SECRET CV TEXT THAT MUST NEVER REACH AN EXTERNAL CALLER",
    "source": "apollo", "source_url": None, "lawful_basis": None, "date_found": None,
    "sourced_by_agent": None, "strength_score": None, "switch_readiness": None,
    "tags": None, "status": "sourced", "is_passive": True, "screening_score": None,
    "screening_notes": None, "quality_score": None, "cv_file_path": None,
    "created_at": "2026-01-01T00:00:00+00:00", "updated_at": None,
    "deleted_at": None, "consent_withdrawn_at": None,
}


@pytest.fixture()
def stubbed_db(monkeypatch):
    async def fake_fetch_all(query, *args, **kwargs):
        return [_STUB_ROW]

    async def fake_fetch_one(query, *args, **kwargs):
        return _STUB_ROW

    monkeypatch.setattr(candidates, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(candidates, "fetch_one", fake_fetch_one)


def test_list_candidates_http_response_never_contains_cv_text(stubbed_db):
    resp = client.get("/api/candidates", headers=HEADERS)
    assert resp.status_code == 200
    assert "cv_text" not in resp.text
    body = resp.json()
    assert body and "cv_text" not in body[0]
    assert body[0]["full_name"] == "Test Candidate"


def test_get_candidate_http_response_never_contains_cv_text(stubbed_db):
    resp = client.get("/api/candidates/1", headers=HEADERS)
    assert resp.status_code == 200
    assert "cv_text" not in resp.text
    assert "cv_text" not in resp.json()


def test_patch_candidate_http_response_never_contains_cv_text(stubbed_db):
    resp = client.patch("/api/candidates/1", headers=HEADERS, json={"tags": ["x"]})
    assert resp.status_code == 200
    assert "cv_text" not in resp.text
    assert "cv_text" not in resp.json()
