"""
GET /api/matches/candidates-for-job/{job_id} must never leak a candidate's
name or CV text to the external agent that calls it, and must exclude the
Apollo pool (VERWERKINGSREGISTER.md rij 1, §2.6 measure A1: no http(s)
`source_url` on file = not usable for matching or drafting).

Round two of the privacy audit found that regex-cleaning free CV text
cannot be made reliably sound (addresses without a recognised street-type
suffix, foreign addresses, non-ISO dates all survived pseudonymize_cv_text()
in testing) -- so the fix here is "don't send it", not "clean it harder".
core/privacy.py's pseudonymize_cv_text() and its helpers are removed
entirely along with this change; grep the repo for that name to confirm.

Pure unit test: core.database's fetch_one/fetch_all are monkeypatched
directly on the routers.matches module (which imports them by name), so no
DB is needed.
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

from routers import matches


@pytest.fixture()
def fake_db(monkeypatch):
    captured = {}

    async def fake_fetch_one(query, *args, **kwargs):
        return {"id": args[0], "title": "Embedded Engineer", "description": "", "requirements": ""}

    async def fake_fetch_all(query, *args, **kwargs):
        captured["query"] = query
        return [{
            "id": 1,
            "current_title": "Embedded Software Engineer",
            "current_company": "ASML",
            "skills": ["C++", "FreeRTOS"],
            "location": "Eindhoven",
            "years_experience": 10,
            "updated_at": None,
            "cv_rank": 0.0,
            "skill_matches": 0,
        }]

    monkeypatch.setattr(matches, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(matches, "fetch_all", fake_fetch_all)
    return captured


def test_response_has_no_name_and_no_cv_text(fake_db):
    result = asyncio.run(matches.candidates_for_job(job_id=1))
    assert len(result) == 1
    row = result[0]

    assert "full_name" not in row
    assert "cv_excerpt" not in row
    assert "cv_text" not in row

    # Enough structured signal to shortlist and write back on candidate_id
    assert row["id"] == 1
    assert row["current_title"] == "Embedded Software Engineer"
    assert row["current_company"] == "ASML"
    assert row["skills"] == ["C++", "FreeRTOS"]
    assert row["location"] == "Eindhoven"


def test_candidates_query_excludes_apollo_pool_without_source_url(fake_db):
    asyncio.run(matches.candidates_for_job(job_id=1))
    query = fake_db["query"]
    assert "source_url" in query
    assert "https?://" in query


def test_pseudonymize_cv_text_removed_repo_wide():
    """The function this endpoint used to call is gone, not just unused
    here -- otherwise dead code left in core/privacy.py would misleadingly
    suggest cleaning still happens somewhere."""
    import core.privacy as privacy
    assert not hasattr(privacy, "pseudonymize_cv_text")
