"""
Unit tests for WS-E.2 (e-mail verification + admin approval) and WS-E.3
(team invite via set-password link, Google login token not in a query
string). Pure functions/static-source checks + a migration text check,
no DB/network needed -- same style as tests/test_ws_c2_authz.py and
tests/test_baseline_schema.py.
"""
import hashlib
import importlib.util
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi import HTTPException

from core.security import hash_token
import routers.auth as auth_router
import routers.client as client_router
from routers.client import _require_candidate_access


# ── Token hashing (core.security.hash_token) ─────────────────────────────

def test_hash_token_is_sha256_hex():
    token = "some-random-url-safe-token"
    assert hash_token(token) == hashlib.sha256(token.encode("utf-8")).hexdigest()


def test_hash_token_is_deterministic():
    token = "abc123"
    assert hash_token(token) == hash_token(token)


def test_hash_token_differs_per_token():
    assert hash_token("token-a") != hash_token("token-b")


def test_hash_token_never_returns_the_raw_token():
    token = "raw-secret-token-value"
    assert hash_token(token) != token


# ── _require_candidate_access: WS-E.2 client-approval gate ───────────────

def test_require_candidate_access_allows_admin():
    _require_candidate_access({"role": "admin"})  # must not raise


def test_require_candidate_access_blocks_client_without_approval():
    """A verified client user with no approved_by_admin_at is still
    blocked -- role='client' alone is not enough (regression guard for
    the WS-E.2 gate this test file adds on top of WS-C.2's)."""
    with pytest.raises(HTTPException) as exc_info:
        _require_candidate_access({"role": "client", "approved_by_admin_at": None})
    assert exc_info.value.status_code == 403


def test_require_candidate_access_blocks_client_missing_key_entirely():
    """Same as above, but the key is absent (e.g. get_optional_user()
    paths or a stale caller) rather than explicitly None -- .get() must
    handle that the same way."""
    with pytest.raises(HTTPException) as exc_info:
        _require_candidate_access({"role": "client"})
    assert exc_info.value.status_code == 403


def test_require_candidate_access_allows_approved_client():
    _require_candidate_access({
        "role": "client",
        "approved_by_admin_at": "2026-09-03T00:00:00+00:00",
    })  # must not raise


def test_require_candidate_access_blocks_other_roles():
    with pytest.raises(HTTPException) as exc_info:
        _require_candidate_access({"role": "candidate", "approved_by_admin_at": "2026-09-03T00:00:00+00:00"})
    assert exc_info.value.status_code == 403


# ── Portal routers require a verified user (WS-E.2) ───────────────────────

def test_candidate_router_never_uses_bare_get_current_user():
    """Every candidate-portal endpoint must depend on get_verified_user,
    not get_current_user directly -- otherwise an unverified account could
    reach personal-data endpoints and (via _get_candidate_id) get a
    `candidates` row created before confirming their e-mail."""
    import routers.candidate as candidate_router
    src = inspect.getsource(candidate_router)
    assert "Depends(get_current_user)" not in src
    assert "Depends(get_verified_user)" in src


def test_client_router_never_uses_bare_require_role():
    """Every client-portal endpoint must depend on require_verified_role,
    not the unverified require_role -- see core/deps.py."""
    src = inspect.getsource(client_router)
    assert 'require_role("client", "admin")' not in src
    assert 'require_verified_role("client", "admin")' in src


# ── Resend-verification: always 200, no user enumeration ─────────────────

def test_resend_verification_has_single_unconditional_return():
    """resend_verification() must always return the same 200 response
    regardless of whether the account exists or is already verified --
    no HTTPException, no branch-specific return, matching the existing
    forgot_password() no-enumeration pattern in this file."""
    src = inspect.getsource(auth_router.resend_verification)
    assert "raise HTTPException" not in src
    assert src.count("return {") == 1
    assert "If that email exists" in src


def test_resend_verification_rate_limited_3_per_hour():
    src = inspect.getsource(auth_router)
    # decorator immediately precedes the function definition
    idx = src.index("async def resend_verification")
    preceding = src[:idx]
    assert '@limiter.limit("3/hour")' in preceding[-200:]


# ── verify-email / set-password use the hashed-token mechanism ───────────

def test_verify_email_hashed_uses_hash_token_and_ttl():
    src = inspect.getsource(auth_router.verify_email_hashed)
    assert "hash_token(data.token)" in src
    assert "INTERVAL '24 hours'" in src
    assert "verification_token_hash = NULL" in src


def test_set_password_uses_hash_token_and_marks_verified():
    src = inspect.getsource(auth_router.set_password)
    assert "hash_token(data.token)" in src
    assert "is_verified = TRUE" in src
    assert "email_verified_at = NOW()" in src


# ── WS-E.3: team invite never returns/emails a password ──────────────────

def test_invite_team_member_never_returns_a_password_field():
    src = inspect.getsource(client_router.invite_team_member)
    assert "temporary_password" not in src
    assert "temp_password" not in src


def test_invite_team_member_uses_hashed_set_password_token():
    src = inspect.getsource(client_router.invite_team_member)
    assert "hash_token(set_password_token)" in src
    assert "set-password" in src
    # the invited user is created unverified -- FALSE for is_verified
    assert "FALSE" in src


def test_team_invite_response_has_no_password_field():
    expected_keys = {"message", "user_id", "email"}
    response = {
        "message": "Team member invited successfully. ...",
        "user_id": 1,
        "email": "a@example.com",
    }
    assert set(response.keys()) == expected_keys
    assert "temporary_password" not in response
    assert "password" not in response


# ── WS-E.3: Google login token is not a query-string parameter ───────────

def test_google_callback_puts_token_in_fragment_not_query_string():
    src = inspect.getsource(auth_router.google_callback)
    assert "#google_auth={token_response['access_token']}" in src
    assert "?google_auth={token_response['access_token']}" not in src


# ── Migration 017: idempotent, backfills without locking anyone out ──────

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations")


def _load_migration_017():
    path = os.path.join(MIGRATIONS_DIR, "017_email_verification.py")
    spec = importlib.util.spec_from_file_location("_migration_017", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, MIGRATIONS_DIR)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(MIGRATIONS_DIR)
    return mod


def test_migration_017_adds_all_five_columns():
    sql = _load_migration_017().MIGRATION_SQL
    for column in (
        "email_verified_at TIMESTAMPTZ",
        "verification_token_hash TEXT",
        "verification_sent_at TIMESTAMPTZ",
        "approved_by_admin_at TIMESTAMPTZ",
        "approved_by_admin_id INTEGER",
    ):
        assert column in sql, f"migration 017 must add {column}"
        assert f"ADD COLUMN IF NOT EXISTS {column.split()[0]}" in sql


def test_migration_017_backfills_email_verified_at_for_already_verified_users():
    sql = _load_migration_017().MIGRATION_SQL
    assert "UPDATE users SET email_verified_at = NOW() WHERE is_verified = TRUE" in sql


def test_migration_017_backfills_approval_for_existing_clients_only():
    """Must not lock out clients who already have a working account --
    see the migration's own docstring."""
    sql = _load_migration_017().MIGRATION_SQL
    assert "UPDATE users SET approved_by_admin_at = NOW() WHERE role = 'client'" in sql


def test_migration_017_is_idempotent_no_unguarded_backfill():
    sql = _load_migration_017().MIGRATION_SQL
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if stmt.upper().startswith("UPDATE"):
            assert "IS NULL" in stmt.upper(), f"unguarded UPDATE would re-run every deploy: {stmt}"


def test_migration_017_version_matches_filename():
    assert _load_migration_017().VERSION == "017_email_verification"
