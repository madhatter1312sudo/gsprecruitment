"""
Unit tests for WS-E.4 "rate limiting en lockout (minimaal)".

Covers, in this order:
  1. core/ratelimit.py's get_client_ip key function -- CF-Connecting-IP,
     trusted/untrusted X-Forwarded-For, and the raw-socket fallback.
  2. Per-account lockout counter logic (routers.auth._register_failed_login
     and login()'s locked-account branch) against a stubbed DB, same
     asyncio.run()-direct style as tests/test_storage.py (no DB/network,
     no pytest-asyncio dependency).
  3. JWT 'iat' vs users.password_changed_at (core.security.create_access_token
     + core.deps._token_predates_password_change).
  4. Migration 020 text: idempotent, adds all three columns.
"""
import asyncio
import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import core.ratelimit as ratelimit
import routers.auth as auth_router
from core.deps import _token_predates_password_change
from core.security import create_access_token, decode_token


# ── 1. core/ratelimit.py: get_client_ip precedence ───────────────────────

def _make_request(headers: dict, client_host: str = "9.9.9.9") -> Request:
    """Build a bare starlette Request with just the headers/client we need
    -- get_client_ip only ever reads request.headers and request.client,
    so no real ASGI receive channel is needed."""
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "headers": raw_headers,
        "client": (client_host, 12345),
        "method": "GET",
        "path": "/",
    }
    return Request(scope)


def test_get_client_ip_prefers_cf_connecting_ip():
    req = _make_request({"CF-Connecting-IP": "203.0.113.5", "X-Forwarded-For": "198.51.100.1"})
    assert ratelimit.get_client_ip(req) == "203.0.113.5"


def test_get_client_ip_uses_first_xff_hop_from_trusted_proxy():
    # 173.245.48.1 is inside Cloudflare's published 173.245.48.0/20 range,
    # the default trusted-proxy CIDR list.
    req = _make_request(
        {"X-Forwarded-For": "198.51.100.1, 10.0.0.2"},
        client_host="173.245.48.1",
    )
    assert ratelimit.get_client_ip(req) == "198.51.100.1"


def test_get_client_ip_ignores_xff_from_untrusted_peer():
    """The immediate peer is NOT in the trusted-proxy list -- X-Forwarded-For
    is attacker-controlled here and must be ignored, falling back to the
    raw socket address instead (never spoofable via headers)."""
    req = _make_request(
        {"X-Forwarded-For": "198.51.100.1"},
        client_host="1.2.3.4",
    )
    assert ratelimit.get_client_ip(req) == "1.2.3.4"


def test_get_client_ip_falls_back_to_socket_address_with_no_headers():
    req = _make_request({}, client_host="5.6.7.8")
    assert ratelimit.get_client_ip(req) == "5.6.7.8"


def test_get_client_ip_trusted_proxy_env_override(monkeypatch):
    """TRUSTED_PROXY_CIDRS overrides the Cloudflare default list entirely."""
    import ipaddress
    monkeypatch.setattr(ratelimit, "_TRUSTED_PROXY_NETWORKS", [ipaddress.ip_network("10.0.0.0/8")])
    req = _make_request({"X-Forwarded-For": "198.51.100.1"}, client_host="10.1.2.3")
    assert ratelimit.get_client_ip(req) == "198.51.100.1"
    # A peer outside the overridden range is untrusted even though it was
    # inside the (now-replaced) Cloudflare default range.
    req2 = _make_request({"X-Forwarded-For": "198.51.100.1"}, client_host="173.245.48.1")
    assert ratelimit.get_client_ip(req2) == "173.245.48.1"


def test_shared_limiter_used_by_every_router():
    """Regression guard for the 'one shared Limiter instance' requirement
    -- main.py, routers/auth.py and routers/public.py must all import the
    same object from core/ratelimit.py rather than building their own
    Limiter(...) (three independent in-memory counters that never see
    each other's requests)."""
    import main
    import routers.public as public_router

    assert main.limiter is ratelimit.limiter
    assert auth_router.limiter is ratelimit.limiter
    assert public_router.limiter is ratelimit.limiter


# ── 2. Lockout counter logic, against a stubbed DB ───────────────────────

class _FakeUsersDB:
    """Minimal in-memory stand-in for the one `users` row routers.auth's
    fetch_one/execute calls touch during login(). Only understands the
    handful of statements login()/_register_failed_login() actually
    issue -- matched by substring, same spirit as a real integration test
    without needing Postgres."""

    def __init__(self, **row):
        row.setdefault("failed_login_count", 0)
        row.setdefault("locked_until", None)
        row.setdefault("last_failed_login_at", None)
        self.row = row

    async def fetch_one(self, sql, *args):
        sql_u = sql.upper()
        if "UPDATE USERS" in sql_u and "FAILED_LOGIN_COUNT = CASE" in sql_u:
            assert "LAST_FAILED_LOGIN_AT" in sql_u, "window must key off last_failed_login_at, not updated_at"
            assert "UPDATED_AT" not in sql_u, "lockout window must not touch/depend on updated_at"
            window_ok = (
                self.row["last_failed_login_at"] is not None
                and self.row["last_failed_login_at"] >= datetime.now(timezone.utc) - timedelta(minutes=15)
            )
            self.row["failed_login_count"] = (
                self.row["failed_login_count"] + 1 if window_ok else 1
            )
            self.row["last_failed_login_at"] = datetime.now(timezone.utc)
            return {"failed_login_count": self.row["failed_login_count"]}
        raise AssertionError(f"unexpected fetch_one in test stub: {sql}")

    async def execute(self, sql, *args):
        sql_u = sql.upper()
        if "SET LOCKED_UNTIL = NOW() + INTERVAL '15 MINUTES'" in sql_u:
            self.row["locked_until"] = datetime.now(timezone.utc) + timedelta(minutes=15)
        elif "FAILED_LOGIN_COUNT = 0" in sql_u and "LOCKED_UNTIL = NULL" in sql_u:
            self.row["failed_login_count"] = 0
            self.row["locked_until"] = None
            self.row["last_failed_login_at"] = None
        else:
            raise AssertionError(f"unexpected execute in test stub: {sql}")
        return "UPDATE 1"


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeUsersDB(id=1)

    async def fake_fetch_one(sql, *args):
        return await db.fetch_one(sql, *args)

    async def fake_execute(sql, *args):
        return await db.execute(sql, *args)

    monkeypatch.setattr(auth_router, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(auth_router, "execute", fake_execute)
    return db


def test_register_failed_login_increments_counter(fake_db):
    asyncio.run(auth_router._register_failed_login(fake_db.row))
    assert fake_db.row["failed_login_count"] == 1
    assert fake_db.row["locked_until"] is None


def test_register_failed_login_locks_after_threshold(fake_db):
    for _ in range(auth_router.FAILED_LOGIN_LOCKOUT_THRESHOLD):
        asyncio.run(auth_router._register_failed_login(fake_db.row))
    assert fake_db.row["failed_login_count"] == auth_router.FAILED_LOGIN_LOCKOUT_THRESHOLD
    assert fake_db.row["locked_until"] is not None
    assert fake_db.row["locked_until"] > datetime.now(timezone.utc)


def test_register_failed_login_resets_streak_outside_window(fake_db):
    fake_db.row["failed_login_count"] = 9
    fake_db.row["last_failed_login_at"] = datetime.now(timezone.utc) - timedelta(minutes=20)
    asyncio.run(auth_router._register_failed_login(fake_db.row))
    # The previous streak is outside the 15-minute window, so this failure
    # restarts the counter at 1 rather than reaching 10 and locking.
    assert fake_db.row["failed_login_count"] == 1
    assert fake_db.row["locked_until"] is None


def test_register_failed_login_continues_streak_inside_window(fake_db):
    fake_db.row["failed_login_count"] = 9
    fake_db.row["last_failed_login_at"] = datetime.now(timezone.utc) - timedelta(minutes=5)
    asyncio.run(auth_router._register_failed_login(fake_db.row))
    assert fake_db.row["failed_login_count"] == 10
    assert fake_db.row["locked_until"] is not None


def test_register_failed_login_window_not_keyed_to_updated_at(fake_db):
    """Regression guard: an unrelated write to the row (a profile edit, an
    admin update, ...) refreshes updated_at but must never affect the
    lockout window -- only last_failed_login_at does."""
    fake_db.row["failed_login_count"] = 9
    fake_db.row["last_failed_login_at"] = datetime.now(timezone.utc) - timedelta(minutes=20)
    fake_db.row["updated_at"] = datetime.now(timezone.utc)  # fresh, but irrelevant
    asyncio.run(auth_router._register_failed_login(fake_db.row))
    assert fake_db.row["failed_login_count"] == 1
    assert fake_db.row["locked_until"] is None


def test_login_threshold_and_window_constants():
    """Regression guard for the masterplan's exact numbers."""
    assert auth_router.FAILED_LOGIN_LOCKOUT_THRESHOLD == 10
    assert auth_router.FAILED_LOGIN_WINDOW_MINUTES == 15
    assert auth_router.LOCKOUT_DURATION_MINUTES == 15


def test_login_locked_branch_is_generic_and_sets_retry_after():
    """login()'s already-locked branch must raise the exact same detail
    string as a wrong password, and only add Retry-After -- never a
    distinguishing message that would reveal the account exists/is
    locked. Checked at the source level since driving login() itself
    needs the full FastAPI/slowapi request plumbing (see main.py's
    Limiter), which is out of scope for these pure/stubbed-DB tests."""
    import inspect

    src = inspect.getsource(auth_router.login)
    assert src.count('"Invalid email or password"') == 2  # locked branch + wrong-password branch
    assert "headers={\"Retry-After\"" in src
    # The locked branch's HTTPException call must not carry any other
    # distinguishing detail text.
    assert "account is locked" not in src.lower()
    assert "too many attempts" not in src.lower()


def test_login_resets_counter_on_success_source_check():
    import inspect

    src = inspect.getsource(auth_router.login)
    assert "failed_login_count = 0, locked_until = NULL" in src


# ── 3. iat vs password_changed_at ─────────────────────────────────────────

def test_create_access_token_stamps_iat():
    token = create_access_token(data={"sub": 1, "role": "candidate"})
    payload = decode_token(token)
    assert "iat" in payload
    assert "exp" in payload


def test_create_access_token_does_not_overwrite_caller_supplied_iat():
    fixed_iat = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
    token = create_access_token(data={"sub": 1, "role": "candidate", "iat": fixed_iat})
    payload = decode_token(token)
    assert payload["iat"] == fixed_iat


def test_token_predates_password_change_rejects_older_iat():
    now = datetime.now(timezone.utc)
    payload = {"iat": int((now - timedelta(hours=2)).timestamp())}
    user = {"password_changed_at": now - timedelta(hours=1)}
    assert _token_predates_password_change(payload, user) is True


def test_token_predates_password_change_accepts_newer_iat():
    now = datetime.now(timezone.utc)
    payload = {"iat": int(now.timestamp())}
    user = {"password_changed_at": now - timedelta(hours=1)}
    assert _token_predates_password_change(payload, user) is False


def test_token_predates_password_change_none_when_no_iat():
    """A token minted before this feature existed carries no 'iat' at all
    -- it must NOT be rejected on that basis (stays valid until its own
    'exp'), per core/security.create_access_token's docstring."""
    payload = {}
    user = {"password_changed_at": datetime.now(timezone.utc)}
    assert _token_predates_password_change(payload, user) is False


def test_token_predates_password_change_none_when_never_changed():
    payload = {"iat": int(datetime.now(timezone.utc).timestamp())}
    user = {"password_changed_at": None}
    assert _token_predates_password_change(payload, user) is False


def test_get_current_user_checks_password_changed_at_source():
    import inspect
    import core.deps as deps

    src = inspect.getsource(deps.get_current_user)
    assert "_token_predates_password_change" in src
    assert "password_changed_at" in inspect.getsource(deps)


# ── 4. Migration 020 ──────────────────────────────────────────────────────

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations")


def _load_migration_020():
    path = os.path.join(MIGRATIONS_DIR, "020_login_lockout.py")
    spec = importlib.util.spec_from_file_location("_migration_020", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, MIGRATIONS_DIR)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(MIGRATIONS_DIR)
    return mod


def test_migration_020_adds_all_four_columns():
    sql = _load_migration_020().MIGRATION_SQL
    for column in (
        "failed_login_count INTEGER NOT NULL DEFAULT 0",
        "last_failed_login_at TIMESTAMPTZ",
        "locked_until TIMESTAMPTZ",
        "password_changed_at TIMESTAMPTZ",
    ):
        assert column in sql, f"migration 020 must add {column}"
        assert f"ADD COLUMN IF NOT EXISTS {column.split()[0]}" in sql


def test_migration_020_lockout_window_column_is_dedicated_not_updated_at():
    """Regression guard: the lockout window must be its own column, not
    an ALTER/backfill that repurposes the shared updated_at column."""
    sql = _load_migration_020().MIGRATION_SQL
    assert "last_failed_login_at" in sql
    assert "updated_at" not in sql


def test_migration_020_is_idempotent():
    sql = _load_migration_020().MIGRATION_SQL
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if not stmt:
            continue
        upper = stmt.upper()
        if upper.startswith("ALTER TABLE"):
            assert "IF NOT EXISTS" in upper
        if upper.startswith("CREATE INDEX"):
            assert "IF NOT EXISTS" in upper
        if upper.startswith("UPDATE"):
            assert "IS NULL" in upper, f"unguarded UPDATE would re-run every deploy: {stmt}"


def test_migration_020_version_matches_filename():
    assert _load_migration_020().VERSION == "020_login_lockout"


# ── Rate limits on the specified endpoints ────────────────────────────────

def test_endpoint_rate_limits_match_masterplan():
    import inspect

    assert '@limiter.limit("5/minute")' in inspect.getsource(auth_router.login)
    assert '@limiter.limit("30/minute")' in inspect.getsource(auth_router.refresh_token)
    assert '@limiter.limit("20/minute")' in inspect.getsource(auth_router.verify_email_hashed)
    assert '@limiter.limit("10/minute")' in inspect.getsource(auth_router.set_password)
    assert '@limiter.limit("10/minute")' in inspect.getsource(auth_router.change_password)
    assert '@limiter.limit("3/minute")' in inspect.getsource(auth_router.forgot_password)
    assert '@limiter.limit("3/minute")' in inspect.getsource(auth_router.reset_password)


def test_unlock_endpoint_exists_and_writes_audit_log():
    import inspect
    import routers.admin as admin_router

    assert hasattr(admin_router, "unlock_user")
    src = inspect.getsource(admin_router.unlock_user)
    assert "audit_log" in src
    assert "json.dumps" in src
