"""
WS-C.14 integration tests: JWT/API-key auth boundaries against a real DB.

- Candidate JWT on an admin route -> 403
- X-API-Key enforced on /api/candidates and /api/jobs (401 without)
- POST /api/auth/refresh: 200 with a fresh token, 401 when the token's
  iat predates users.password_changed_at
- MFA mfa_pending token rejected on /api/auth/me
"""
import pytest

pytestmark = pytest.mark.integration


# ── Candidate JWT on an admin route ───────────────────────────────────

def test_candidate_jwt_on_admin_route_is_403(client, make_candidate_user):
    candidate = make_candidate_user()
    resp = client.get("/api/v1/admin/health", headers=candidate["headers"])
    assert resp.status_code == 403, resp.text


def test_admin_jwt_on_admin_route_is_200(client, make_admin):
    admin = make_admin()
    resp = client.get("/api/v1/admin/health", headers=admin["headers"])
    assert resp.status_code == 200, resp.text


# ── X-API-Key enforcement ─────────────────────────────────────────────

def test_candidates_endpoint_requires_api_key(client):
    resp = client.get("/api/candidates")
    assert resp.status_code == 401, resp.text
    assert "X-API-Key" in resp.text


def test_candidates_endpoint_accepts_valid_api_key(client, api_key_headers):
    resp = client.get("/api/candidates", headers=api_key_headers)
    assert resp.status_code == 200, resp.text


def test_candidates_endpoint_rejects_wrong_api_key(client):
    resp = client.get("/api/candidates", headers={"X-API-Key": "definitely-not-it"})
    assert resp.status_code == 403, resp.text


def test_jobs_endpoint_requires_api_key(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 401, resp.text


def test_jobs_endpoint_accepts_valid_api_key(client, api_key_headers):
    resp = client.get("/api/jobs", headers=api_key_headers)
    assert resp.status_code == 200, resp.text


# ── POST /api/auth/refresh ─────────────────────────────────────────────

def test_refresh_with_fresh_token_returns_200_and_new_token(client, make_candidate_user):
    """Note: create_access_token stamps 'iat'/'exp' to whole-second
    precision, so a refresh issued in the same wall-clock second as the
    original token can legitimately come back byte-identical -- assert
    on the response shape/identity, not string inequality."""
    candidate = make_candidate_user()
    resp = client.post("/api/auth/refresh", json={"access_token": candidate["token"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["id"] == candidate["id"]
    assert body["user"]["email"] == candidate["email"]


def test_refresh_rejects_token_issued_before_password_change(client, insert_raw_user, db_run):
    """A token minted, then the account's password_changed_at moved to
    the future relative to that token's iat, must be rejected -- same
    protection core/deps.py's get_current_user gives every other route
    (core/deps._token_predates_password_change)."""
    from core.database import execute

    user = insert_raw_user("candidate")

    # Simulate a password change that happened AFTER the token was issued.
    db_run(
        execute,
        "UPDATE users SET password_changed_at = password_changed_at + INTERVAL '1 hour' WHERE id = $1",
        user["id"],
    )

    resp = client.post("/api/auth/refresh", json={"access_token": user["token"]})
    assert resp.status_code == 401, resp.text


def test_refresh_without_token_is_400(client):
    resp = client.post("/api/auth/refresh", json={})
    assert resp.status_code == 400, resp.text


# ── MFA mfa_pending token ──────────────────────────────────────────────

def test_mfa_pending_token_rejected_on_me(client, make_admin):
    from core.mfa import issue_mfa_pending_token

    admin = make_admin()
    pending_token = issue_mfa_pending_token(admin["id"])

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {pending_token}"})
    assert resp.status_code == 401, resp.text
    assert "MFA verification required" in resp.text


def test_real_access_token_works_on_me(client, make_admin):
    admin = make_admin()
    resp = client.get("/api/auth/me", headers=admin["headers"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == admin["email"]
