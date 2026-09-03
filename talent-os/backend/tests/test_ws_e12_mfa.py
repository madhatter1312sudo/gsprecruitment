"""
Unit tests for WS-E.12 (TOTP MFA for admin accounts).

Pure functions/pydantic models + a couple of TestClient-driven flows that
stub the DB via monkeypatch (same pattern as tests/test_ws_e2_e3_verification.py
and tests/test_ws_c2_authz.py) -- no live Postgres needed.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

import pyotp
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient

import core.mfa as mfa
from core.config import settings

import main
import routers.auth as auth_router
import routers.mfa as mfa_router

client = TestClient(main.app)


# ── Fernet round trip (secret at rest) ───────────────────────────────────

def test_encrypt_decrypt_round_trip(monkeypatch):
    monkeypatch.setattr(settings, "mfa_enc_key", Fernet.generate_key().decode("utf-8"))
    raw = pyotp.random_base32()
    enc = mfa.encrypt_secret(raw)
    assert enc != raw
    assert mfa.decrypt_secret(enc) == raw


def test_encrypt_without_key_raises_503(monkeypatch):
    monkeypatch.setattr(settings, "mfa_enc_key", "")
    with pytest.raises(HTTPException) as exc_info:
        mfa.encrypt_secret("whatever")
    assert exc_info.value.status_code == 503


def test_decrypt_with_wrong_key_raises_503(monkeypatch):
    monkeypatch.setattr(settings, "mfa_enc_key", Fernet.generate_key().decode("utf-8"))
    enc = mfa.encrypt_secret("some-secret")
    monkeypatch.setattr(settings, "mfa_enc_key", Fernet.generate_key().decode("utf-8"))
    with pytest.raises(HTTPException) as exc_info:
        mfa.decrypt_secret(enc)
    assert exc_info.value.status_code == 503


# ── TOTP verify + replay rejection ───────────────────────────────────────

def test_verify_totp_code_accepts_correct_code():
    secret = pyotp.random_base32()
    code = pyotp.TOTP(secret).now()
    step = mfa.verify_totp_code(secret, code, last_used_step=None)
    assert step is not None
    assert step == mfa.current_step()


def test_verify_totp_code_rejects_wrong_code():
    secret = pyotp.random_base32()
    assert mfa.verify_totp_code(secret, "000000", last_used_step=None) is None


def test_verify_totp_code_rejects_non_digit_code():
    secret = pyotp.random_base32()
    assert mfa.verify_totp_code(secret, "abcdef", last_used_step=None) is None
    assert mfa.verify_totp_code(secret, "", last_used_step=None) is None


def test_verify_totp_code_rejects_replay():
    """The same correct code cannot be accepted twice -- the second call
    passes the step it was last accepted at as last_used_step."""
    secret = pyotp.random_base32()
    code = pyotp.TOTP(secret).now()
    first = mfa.verify_totp_code(secret, code, last_used_step=None)
    assert first is not None
    second = mfa.verify_totp_code(secret, code, last_used_step=first)
    assert second is None


def test_verify_totp_code_rejects_step_older_than_last_used():
    secret = pyotp.random_base32()
    code = pyotp.TOTP(secret).now()
    step = mfa.current_step()
    # Pretend a later step was already consumed.
    assert mfa.verify_totp_code(secret, code, last_used_step=step + 10) is None


# ── Recovery codes: generation + hashing + single use ────────────────────

def test_generate_recovery_codes_count_and_length():
    codes = mfa.generate_recovery_codes()
    assert len(codes) == mfa.RECOVERY_CODE_COUNT
    assert len(set(codes)) == mfa.RECOVERY_CODE_COUNT  # no duplicates
    for c in codes:
        assert len(c) == mfa.RECOVERY_CODE_LENGTH


def test_hash_recovery_code_deterministic_and_normalized():
    assert mfa.hash_recovery_code("abcd1234ef") == mfa.hash_recovery_code("ABCD1234EF")
    assert mfa.hash_recovery_code(" ABCD1234EF ") == mfa.hash_recovery_code("abcd1234ef")


def test_hash_recovery_code_never_equals_raw_code():
    code = "ABCD1234EF"
    assert mfa.hash_recovery_code(code) != code


def test_recovery_code_single_use_removed_from_stored_list(monkeypatch):
    """Mirrors routers/mfa.py mfa_recovery(): a consumed hash is removed
    from the stored array so it can never be matched again."""
    codes = mfa.generate_recovery_codes()
    hashes = [mfa.hash_recovery_code(c) for c in codes]
    target = codes[3]
    target_hash = mfa.hash_recovery_code(target)
    assert target_hash in hashes
    remaining = [h for h in hashes if h != target_hash]
    assert target_hash not in remaining
    assert len(remaining) == len(hashes) - 1
    # A second attempt with the same code no longer matches.
    assert mfa.hash_recovery_code(target) not in remaining


# ── mfa_pending scope: issued/decoded correctly, rejected by admin deps ──

def test_issue_and_decode_mfa_pending_token_round_trip():
    token = mfa.issue_mfa_pending_token(42)
    assert mfa.decode_mfa_pending_token(token) == 42


def test_decode_mfa_pending_token_rejects_normal_access_token():
    """A regular session token (no scope=mfa_pending claim) must not be
    usable at /api/auth/mfa/verify or /recovery."""
    from core.security import create_access_token
    normal_token = create_access_token(data={"sub": 1, "role": "admin"})
    assert mfa.decode_mfa_pending_token(normal_token) is None


def test_get_current_user_rejects_mfa_pending_scope_token(monkeypatch):
    """core/deps.py's get_current_user must 401 an mfa_pending token before
    it ever reaches the DB lookup or any admin-gated route."""
    import asyncio
    from fastapi.security import HTTPAuthorizationCredentials
    from core.deps import get_current_user

    async def _boom(*a, **kw):
        raise AssertionError("must not query the DB for an mfa_pending token")

    monkeypatch.setattr("core.deps.fetch_one", _boom)

    token = mfa.issue_mfa_pending_token(7)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(credentials=creds))
    assert exc_info.value.status_code == 401


def test_mfa_pending_token_rejected_by_refresh(monkeypatch):
    """routers/auth.py refresh_token() decodes the raw token itself (not
    via get_current_user) -- it must independently reject scope=mfa_pending
    so the challenge token can never be laundered into a real session via
    POST /api/auth/refresh."""
    token = mfa.issue_mfa_pending_token(9)
    r = client.post("/api/auth/refresh", json={"refresh_token": token})
    assert r.status_code == 401


# ── Login returns mfa_required for an enabled admin ──────────────────────

def test_login_returns_mfa_required_for_admin_with_mfa_enabled(monkeypatch):
    from core.security import hash_password

    async def fake_get_user_by_email(email):
        return {
            "id": 1,
            "email": "admin@gsprecruitment.nl",
            "full_name": "Admin",
            "role": "admin",
            "password_hash": hash_password("correct horse battery staple"),
            "is_verified": True,
            "locked_until": None,
            "failed_login_count": 0,
            "last_failed_login_at": None,
            "password_changed_at": None,
            "totp_enabled_at": "2026-01-01T00:00:00+00:00",
        }

    monkeypatch.setattr(auth_router, "_get_user_by_email", fake_get_user_by_email)

    r = client.post("/api/auth/login", json={
        "email": "admin@gsprecruitment.nl",
        "password": "correct horse battery staple",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_required"] is True
    assert "mfa_token" in body
    assert "access_token" not in body
    assert mfa.decode_mfa_pending_token(body["mfa_token"]) == 1


def test_login_issues_normal_tokens_for_admin_without_mfa(monkeypatch):
    from core.security import hash_password

    async def fake_get_user_by_email(email):
        return {
            "id": 2,
            "email": "admin2@gsprecruitment.nl",
            "full_name": "Admin Two",
            "role": "admin",
            "password_hash": hash_password("correct horse battery staple"),
            "is_verified": True,
            "locked_until": None,
            "failed_login_count": 0,
            "last_failed_login_at": None,
            "password_changed_at": None,
            "totp_enabled_at": None,
        }

    monkeypatch.setattr(auth_router, "_get_user_by_email", fake_get_user_by_email)

    r = client.post("/api/auth/login", json={
        "email": "admin2@gsprecruitment.nl",
        "password": "correct horse battery staple",
    })
    assert r.status_code == 200
    body = r.json()
    assert "mfa_required" not in body
    assert "access_token" in body


# ── mfa_required_for_user helper ──────────────────────────────────────────

def test_mfa_required_for_user_true_only_for_enabled_admin():
    assert mfa.mfa_required_for_user({"role": "admin", "totp_enabled_at": "2026-01-01"}) is True
    assert mfa.mfa_required_for_user({"role": "admin", "totp_enabled_at": None}) is False
    assert mfa.mfa_required_for_user({"role": "client", "totp_enabled_at": "2026-01-01"}) is False
    assert mfa.mfa_required_for_user({"role": "admin"}) is False


# ── Migration text (idempotency, same style as other migration tests) ────

def test_migration_021_adds_expected_columns_idempotently():
    text = open(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations", "021_admin_mfa.py")
    ).read()
    for col in (
        "totp_secret_enc text",
        "totp_enabled_at timestamptz",
        "mfa_recovery_codes_hash text[]",
        "mfa_last_used_step bigint",
    ):
        assert col in text
        assert f"ADD COLUMN IF NOT EXISTS {col.split()[0]}" in text


# ══════════════════════════════════════════════════════════════════════
# Security-audit follow-up (chief-of-staff FIX FIRST on commit 8201c40)
# ══════════════════════════════════════════════════════════════════════

# ── 1. HIGH: /setup and /enable 409 once MFA is already enabled ─────────

from core.deps import get_current_user as _get_current_user_dep

ADMIN_USER = {
    "id": 5,
    "email": "admin5@gsprecruitment.nl",
    "full_name": "Admin Five",
    "role": "admin",
    "is_verified": True,
}


@pytest.fixture
def admin_client():
    main.app.dependency_overrides[_get_current_user_dep] = lambda: ADMIN_USER
    yield TestClient(main.app)
    main.app.dependency_overrides.pop(_get_current_user_dep, None)


def test_mfa_setup_409_when_already_enabled(admin_client, monkeypatch):
    async def fake_fetch_one(sql, *args):
        return {"totp_enabled_at": "2026-01-01T00:00:00+00:00"}

    monkeypatch.setattr(mfa_router, "fetch_one", fake_fetch_one)
    r = admin_client.post("/api/auth/mfa/setup")
    assert r.status_code == 409


def test_mfa_setup_allowed_when_not_enabled(admin_client, monkeypatch):
    monkeypatch.setattr(settings, "mfa_enc_key", Fernet.generate_key().decode("utf-8"))

    async def fake_fetch_one(sql, *args):
        return {"totp_enabled_at": None}

    async def fake_execute(sql, *args):
        return "UPDATE 1"

    monkeypatch.setattr(mfa_router, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(mfa_router, "execute", fake_execute)
    r = admin_client.post("/api/auth/mfa/setup")
    assert r.status_code == 200
    body = r.json()
    assert "otpauth_uri" in body and "qr_svg" in body and "secret" in body


def test_mfa_enable_409_when_already_enabled(admin_client, monkeypatch):
    async def fake_fetch_one(sql, *args):
        return {
            "totp_secret_enc": "whatever",
            "mfa_last_used_step": None,
            "totp_enabled_at": "2026-01-01T00:00:00+00:00",
        }

    monkeypatch.setattr(mfa_router, "fetch_one", fake_fetch_one)
    r = admin_client.post("/api/auth/mfa/enable", json={"code": "123456"})
    assert r.status_code == 409


# ── 2. HIGH: /verify and /recovery are rate-limited + per-challenge counter ──

def test_mfa_verify_and_recovery_are_rate_limited():
    """Both endpoints must carry slowapi's 5/minute decorator (same
    mechanism routers/auth.py's login/register/etc already rely on)."""
    import inspect
    src = inspect.getsource(mfa_router)
    verify_block = src[src.index("async def mfa_verify") - 200 : src.index("async def mfa_verify")]
    recovery_block = src[src.index("async def mfa_recovery") - 200 : src.index("async def mfa_recovery")]
    assert '@limiter.limit("5/minute")' in verify_block
    assert '@limiter.limit("5/minute")' in recovery_block


def test_mfa_verify_ip_rate_limit_returns_429_after_five():
    client = TestClient(main.app)
    last = None
    for _ in range(6):
        last = client.post("/api/auth/mfa/verify", json={"mfa_token": "garbage", "code": "000000"})
    assert last.status_code == 429


def test_pending_failures_exceeded_false_initially():
    now = int(time.time())
    assert mfa.pending_failures_exceeded(999001, now) is False


def test_pending_failures_lock_out_after_max():
    # _prune_pending_failures() drops any (user_id, iat) whose iat looks
    # older than the pending-token TTL -- iat must be a realistic "now"
    # unix timestamp, not a small counter, or the entry is pruned the
    # instant it's recorded.
    user_id, iat = 999002, int(time.time())
    mfa.clear_pending_failures(user_id, iat)
    for _ in range(mfa.MAX_PENDING_FAILURES):
        mfa.record_pending_failure(user_id, iat)
    assert mfa.pending_failures_exceeded(user_id, iat) is True
    mfa.clear_pending_failures(user_id, iat)


def test_pending_failures_scoped_per_challenge_not_per_user():
    """Two different login attempts (different iat) by the same admin
    must not share one lockout counter."""
    user_id = 999003
    now = int(time.time())
    iat_a, iat_b = now, now + 1
    mfa.clear_pending_failures(user_id, iat_a)
    mfa.clear_pending_failures(user_id, iat_b)
    for _ in range(mfa.MAX_PENDING_FAILURES):
        mfa.record_pending_failure(user_id, iat_a)
    assert mfa.pending_failures_exceeded(user_id, iat_a) is True
    assert mfa.pending_failures_exceeded(user_id, iat_b) is False
    mfa.clear_pending_failures(user_id, iat_a)
    mfa.clear_pending_failures(user_id, iat_b)


def test_clear_pending_failures_resets_counter():
    user_id, iat = 999004, int(time.time())
    mfa.record_pending_failure(user_id, iat)
    mfa.clear_pending_failures(user_id, iat)
    assert mfa.pending_failures_exceeded(user_id, iat) is False


# ── 3. LOW: get_optional_user rejects scope=mfa_pending ──────────────────

def test_get_optional_user_returns_none_for_mfa_pending_token(monkeypatch):
    import asyncio
    from fastapi.security import HTTPAuthorizationCredentials
    from core.deps import get_optional_user

    async def _boom(*a, **kw):
        raise AssertionError("must not query the DB for an mfa_pending token")

    monkeypatch.setattr("core.deps.fetch_one", _boom)

    token = mfa.issue_mfa_pending_token(11)
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    result = asyncio.run(get_optional_user(credentials=creds))
    assert result is None


# ── 4. LOW: atomic replay / recovery-code consumption ─────────────────────

def test_commit_totp_step_success_when_no_prior_step():
    import asyncio

    calls = {}

    async def fake_execute(sql, *args):
        calls["sql"] = sql
        calls["args"] = args
        return "UPDATE 1"

    import core.mfa as mfa_mod
    orig = mfa_mod.execute
    mfa_mod.execute = fake_execute
    try:
        ok = asyncio.run(mfa_mod.commit_totp_step(1, 100))
    finally:
        mfa_mod.execute = orig
    assert ok is True
    assert calls["args"] == (100, 1)
    assert "mfa_last_used_step IS NULL OR mfa_last_used_step < $1" in calls["sql"]


def test_commit_totp_step_loses_race_returns_false():
    import asyncio
    import core.mfa as mfa_mod

    async def fake_execute(sql, *args):
        return "UPDATE 0"  # a concurrent request already advanced the step

    orig = mfa_mod.execute
    mfa_mod.execute = fake_execute
    try:
        ok = asyncio.run(mfa_mod.commit_totp_step(1, 100))
    finally:
        mfa_mod.execute = orig
    assert ok is False


def test_consume_recovery_code_success():
    import asyncio
    import core.mfa as mfa_mod

    calls = {}

    async def fake_execute(sql, *args):
        calls["sql"] = sql
        calls["args"] = args
        return "UPDATE 1"

    orig = mfa_mod.execute
    mfa_mod.execute = fake_execute
    try:
        ok = asyncio.run(mfa_mod.consume_recovery_code(1, "somehash"))
    finally:
        mfa_mod.execute = orig
    assert ok is True
    assert calls["args"] == ("somehash", 1)
    assert "array_remove(mfa_recovery_codes_hash, $1)" in calls["sql"]
    assert "$1 = ANY(mfa_recovery_codes_hash)" in calls["sql"]


def test_consume_recovery_code_already_used_returns_false():
    import asyncio
    import core.mfa as mfa_mod

    async def fake_execute(sql, *args):
        return "UPDATE 0"

    orig = mfa_mod.execute
    mfa_mod.execute = fake_execute
    try:
        ok = asyncio.run(mfa_mod.consume_recovery_code(1, "somehash"))
    finally:
        mfa_mod.execute = orig
    assert ok is False


def test_rows_affected_parses_command_tag():
    assert mfa._rows_affected("UPDATE 1") == 1
    assert mfa._rows_affected("UPDATE 0") == 0
    assert mfa._rows_affected(None) == 0
    assert mfa._rows_affected("") == 0


# ── 5. Tokens minted at /verify and /recovery carry 'iat' ─────────────────

def test_create_access_token_carries_iat():
    from core.security import create_access_token, decode_token
    token = create_access_token(data={"sub": "1", "role": "admin"})
    payload = decode_token(token)
    assert "iat" in payload
    assert isinstance(payload["iat"], int)
    assert payload["iat"] <= payload["exp"]


def test_build_token_response_access_token_carries_iat():
    payload_user = {"id": 1, "email": "a@b.com", "full_name": "A", "role": "admin", "is_verified": True}
    resp = auth_router._build_token_response(payload_user)
    from core.security import decode_token
    payload = decode_token(resp["access_token"])
    assert "iat" in payload


def test_mfa_pending_token_carries_iat_and_claims_roundtrip():
    token = mfa.issue_mfa_pending_token(77)
    claims = mfa.decode_mfa_pending_claims(token)
    assert claims is not None
    user_id, iat = claims
    assert user_id == 77
    assert isinstance(iat, int)
    assert iat > 0
