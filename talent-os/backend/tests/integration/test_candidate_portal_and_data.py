"""
WS-C.14 integration tests:

- An unverified account cannot reach candidate-portal routes (get_verified_user, 403)
- NULL-array coercion on a candidate GET (skills NULL -> [])
- A jsonb audit_log write round-trips through Postgres unchanged
"""
import uuid

import pytest

pytestmark = pytest.mark.integration


# ── Unverified account vs candidate-portal routes ──────────────────────

def test_unverified_candidate_cannot_reach_profile(client, make_candidate_user):
    unverified = make_candidate_user(verified=False)
    resp = client.get("/api/v1/candidate/profile", headers=unverified["headers"])
    assert resp.status_code == 403, resp.text
    assert "confirm your e-mail" in resp.text.lower()


def test_unverified_candidate_cannot_reach_dashboard(client, make_candidate_user):
    unverified = make_candidate_user(verified=False)
    resp = client.get("/api/v1/candidate/dashboard", headers=unverified["headers"])
    assert resp.status_code == 403, resp.text


def test_verified_candidate_reaches_profile(client, make_candidate_user):
    verified = make_candidate_user(verified=True)
    resp = client.get("/api/v1/candidate/profile", headers=verified["headers"])
    assert resp.status_code == 200, resp.text


def test_unverified_candidate_can_still_read_me(client, make_candidate_user):
    """core/deps.py's docstring: /api/auth/me deliberately stays on
    get_current_user (not get_verified_user) so an unverified account can
    still see its own status."""
    unverified = make_candidate_user(verified=False)
    resp = client.get("/api/auth/me", headers=unverified["headers"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_verified"] is False


# ── NULL array coercion on read ─────────────────────────────────────────

def test_candidate_get_coerces_null_skills_to_empty_list(client, api_key_headers, db_run):
    """A row with skills/languages/tags left NULL (e.g. legacy/manually
    inserted, or the Apollo bulk pool per models/schemas.py's comment)
    must not 500 the GET -- models.schemas.CandidateCreate._none_to_empty_list
    coerces NULL -> [] before the response model validates it.

    updated_at is stamped explicitly here (NOW()) to isolate this test
    from a separate pre-existing bug (see this PR's description):
    CandidateResponse.updated_at is a required datetime, but nothing
    that inserts a candidates row (this INSERT's own columns, or
    routers/candidates.py's create_candidate) sets updated_at, so a
    freshly created row's NULL updated_at fails response-model
    validation with a 500 -- not what this test is checking."""
    from core.database import fetch_one

    row = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, skills, languages, tags, updated_at)
           VALUES ($1, $2, NULL, NULL, NULL, NOW())
           RETURNING id""",
        "Null Arrays Example", f"nullarrays-{uuid.uuid4().hex[:10]}@example.com",
    )

    resp = client.get(f"/api/candidates/{row['id']}", headers=api_key_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skills"] == []
    assert body["languages"] == []
    assert body["tags"] == []


# ── jsonb audit_log round trip ──────────────────────────────────────────

def test_audit_log_jsonb_write_round_trips(db_run):
    """core.database.py registers no jsonb codec on the asyncpg pool, so
    a jsonb column always comes back as the raw JSON text -- the
    established convention in this codebase (routers/public.py's
    json.loads(row["options"]) is the one other place that reads a jsonb
    column) is to json.loads() it yourself on read, matching CLAUDE.md's
    "jsonb columns need json.dumps" note on the write side. Round-trip
    here means json.dumps() in, json.loads() back out === the original,
    unicode and nested structure included -- not that fetch_one hands
    back a dict for free."""
    import json

    from core.database import fetch_one

    payload = {
        "note": "WS-C.14 jsonb round-trip check",
        "nested": {"a": 1, "b": [1, 2, 3], "c": None},
        "unicode": "café ë",
    }
    row = db_run(
        fetch_one,
        """INSERT INTO audit_log (action, target_type, changes)
           VALUES ('integration_test', 'unit_test', $1::jsonb)
           RETURNING id""",
        json.dumps(payload),
    )

    fetched = db_run(fetch_one, "SELECT changes FROM audit_log WHERE id = $1", row["id"])
    assert isinstance(fetched["changes"], str), "asyncpg returns jsonb as raw text (no codec registered)"
    assert json.loads(fetched["changes"]) == payload
