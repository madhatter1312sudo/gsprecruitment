"""
services/matcher.py must never send cv_text to OpenRouter (the embedding
input is built from structured fields only: current_title, education,
years_experience, skills). See VERWERKINGSREGISTER.md §2.6 measure A3 —
round two of the privacy audit found regex-cleaning free CV text cannot be
made reliably sound, so cv_text is dropped from the embedding input
entirely rather than pseudonymized first.

No real network call: EmbeddingMatcher.embed() is monkeypatched to record
the texts it was asked to embed and return dummy vectors.
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

from services.matcher import EmbeddingMatcher


CANDIDATES = [{
    "id": 1,
    "full_name": "Jan de Vries",
    "current_title": "Senior Embedded Software Engineer",
    "education": "MSc Electrical Engineering, TU Eindhoven",
    "years_experience": 10,
    "skills": ["C++", "FreeRTOS"],
    "cv_text": (
        "Jan de Vries\nKerkstraat 12, 5611 AB Eindhoven\n"
        "jan.devries@gmail.com | 06-12345678\n\nErvaren C++ engineer."
    ),
}]


@pytest.fixture()
def matcher(monkeypatch):
    m = EmbeddingMatcher()
    captured = {}

    async def fake_embed(texts):
        captured["texts"] = texts
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(m, "embed", fake_embed)
    return m, captured


def test_candidate_embedding_input_excludes_cv_text_and_name(matcher):
    m, captured = matcher
    asyncio.run(m.match_job_to_candidates("Embedded Engineer vacancy", CANDIDATES))

    # job text embedded first, then candidate texts in one batch
    cand_text = captured["texts"][0]

    assert "Kerkstraat" not in cand_text
    assert "5611 AB" not in cand_text
    assert "jan.devries@gmail.com" not in cand_text
    assert "06-12345678" not in cand_text
    assert "Jan de Vries" not in cand_text

    # structured signal survives
    assert "Senior Embedded Software Engineer" in cand_text
    assert "TU Eindhoven" in cand_text
    assert "C++" in cand_text
    assert "FreeRTOS" in cand_text
