"""
WS-C.14 integration tests: client-portal boundaries against a real DB.

- Client cannot create an admin via team invite (role forced to 'client')
- Client sees no candidates without approved_by_admin_at (403)
- Approved client sees only the anonymised public columns
- GET /api/v1/client/analytics -> 200
"""
import uuid

import pytest

pytestmark = pytest.mark.integration


def _insert_candidate(db_run, **overrides):
    from core.database import fetch_one

    full_name = overrides.get("full_name", "Jane Example")
    email = overrides.get("email", f"candidate-{uuid.uuid4().hex[:10]}@example.com")
    phone = overrides.get("phone", "+31 6 00000000")
    # updated_at is stamped explicitly (NOW()) to sidestep a separate
    # pre-existing bug: CandidateResponse/the candidates list serializer
    # requires a non-null updated_at, but nothing that inserts a
    # candidates row sets it -- see this PR's description. Not what this
    # helper is testing, and other tests' GET /api/candidates calls would
    # otherwise 500 on this row too (that endpoint lists every candidate
    # in the DB, not just this test's own).
    return db_run(
        fetch_one,
        """INSERT INTO candidates
             (full_name, email, phone, current_title, current_company, location,
              years_experience, skills, linkedin_url, updated_at)
           VALUES ($1, $2, $3, 'Embedded Software Engineer', 'Acme BV', 'Eindhoven',
                   5, ARRAY['C++', 'RTOS'], 'https://linkedin.com/in/jane-example', NOW())
           RETURNING *""",
        full_name, email, phone,
    )


# ── Team invite: role forced to 'client' ──────────────────────────────

def test_team_invite_role_is_forced_to_client_even_if_admin_requested(client, make_client_user):
    """TeamInvite.role is a Literal["client"] (models/schemas.py) -- a
    request body claiming role='admin' fails pydantic validation before
    it ever reaches the handler, and even so the INSERT hardcodes
    'client' regardless (routers/client.py invite_team_member, WS-C.2
    privilege-escalation fix). Assert the request is rejected outright."""
    inviter = make_client_user()
    resp = client.post(
        "/api/v1/client/team",
        headers=inviter["headers"],
        json={"email": f"invitee-{uuid.uuid4().hex[:8]}@example.com", "full_name": "Would-Be Admin", "role": "admin"},
    )
    assert resp.status_code == 422, resp.text


def test_team_invite_creates_a_client_role_user_not_admin(client, make_client_user, db_run):
    """A legitimate invite (role omitted -> defaults to 'client') must
    actually land as role='client' in the users table, not just be
    accepted by the schema."""
    from core.database import fetch_one

    inviter = make_client_user()
    invitee_email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/client/team",
        headers=inviter["headers"],
        json={"email": invitee_email, "full_name": "New Teammate"},
    )
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["user_id"]

    row = db_run(fetch_one, "SELECT role FROM users WHERE id = $1", user_id)
    assert row["role"] == "client"


# ── Candidate access gate (WS-E.2 approval) ─────────────────────────────

def test_unapproved_client_cannot_search_candidates(client, make_client_user):
    unapproved = make_client_user(approved=False)
    resp = client.get("/api/v1/client/candidates", headers=unapproved["headers"])
    assert resp.status_code == 403, resp.text
    assert "pending admin approval" in resp.text


def test_approved_client_sees_only_public_columns(client, make_client_user, db_run):
    approved = make_client_user(approved=True)
    candidate = _insert_candidate(db_run)

    resp = client.get("/api/v1/client/candidates", headers=approved["headers"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1

    items_by_id = {item["id"]: item for item in body["items"]}
    assert candidate["id"] in items_by_id
    item = items_by_id[candidate["id"]]

    # Anonymised projection: no direct identifiers/contact channels.
    for forbidden in ("email", "phone", "linkedin_url", "github_url", "portfolio_url", "cv_text"):
        assert forbidden not in item, f"client-facing candidate payload leaked {forbidden!r}: {item}"

    for allowed in ("id", "full_name", "current_title", "current_company", "location", "years_experience", "skills"):
        assert allowed in item


# ── Analytics ───────────────────────────────────────────────────────────

def test_client_analytics_returns_200(client, make_client_user):
    approved = make_client_user(approved=True)
    resp = client.get("/api/v1/client/analytics", headers=approved["headers"])
    assert resp.status_code == 200, resp.text
