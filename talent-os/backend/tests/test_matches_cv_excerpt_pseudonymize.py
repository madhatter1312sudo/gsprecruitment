"""
Security-audit follow-up (finding 3): GET /api/matches/candidates-for-job/{id}
is a third pipe of raw cv_text to an external agent that the OpenRouter
pseudonymisation work (VERWERKINGSREGISTER.md §1.3) never covered.
cv_excerpt must now go through the same pseudonymize_cv_text() as
services/matcher.py's embedding input.

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


CV_TEXT = (
    "Jan de Vries\nSenior Embedded Software Engineer\n"
    "jan.devries@gmail.com | 06-12345678 | Kerkstraat 12, 5611 AB Eindhoven\n\n"
    "Profiel\nErvaren C++ engineer met 10 jaar ervaring."
)


@pytest.fixture()
def fake_db(monkeypatch):
    async def fake_fetch_one(query, *args, **kwargs):
        return {"id": args[0], "title": "Embedded Engineer", "description": "", "requirements": ""}

    async def fake_fetch_all(query, *args, **kwargs):
        return [{
            "id": 1,
            "full_name": "Jan de Vries",
            "current_title": "Embedded Software Engineer",
            "current_company": "ASML",
            "skills": ["C++", "FreeRTOS"],
            "location": "Eindhoven",
            "years_experience": 10,
            "cv_text": CV_TEXT,
            "updated_at": None,
            "cv_rank": 0.0,
            "skill_matches": 0,
        }]

    monkeypatch.setattr(matches, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(matches, "fetch_all", fake_fetch_all)


def test_cv_excerpt_is_pseudonymized(fake_db):
    result = asyncio.run(matches.candidates_for_job(job_id=1))
    assert len(result) == 1
    excerpt = result[0]["cv_excerpt"]

    # direct identifiers gone from the excerpt sent to the external agent
    assert "jan.devries@gmail.com" not in excerpt
    assert "06-12345678" not in excerpt
    assert "Kerkstraat 12" not in excerpt
    assert "5611 AB" not in excerpt
    assert "Jan de Vries" not in excerpt

    # semantic signal for shortlisting survives
    assert "Senior Embedded Software Engineer" in excerpt
    assert "Ervaren C++ engineer" in excerpt


def test_cv_excerpt_still_capped_at_500_chars_after_pseudonymizing(fake_db):
    result = asyncio.run(matches.candidates_for_job(job_id=1))
    assert len(result[0]["cv_excerpt"]) <= 500
