"""
WS3 -- Google Sign-In (routers/auth.py google_login/google_callback) and
the reset-token-as-hash change.

Pure unit tests: core.database.fetch_one/execute are monkeypatched
directly on routers.auth (which imports them by name, same pattern as
tests/test_matches_no_pii.py); httpx.AsyncClient and
google_id_token.verify_oauth2_token are replaced with fakes; no DB, no
network, no real sleep.
"""
import asyncio
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

import pytest
from starlette.requests import Request

import routers.auth as auth_router
from core.config import settings
from core.security import hash_token, decode_token


_ip_counter = [0]


def _make_request(cookies=None, query_string=b"", ip=None):
    """Each call gets its own fake client IP by default -- forgot_password/
    reset_password/google_callback are all rate-limited (per-IP, shared
    in-memory slowapi state that persists across tests in this process),
    and this file calls them far more than 3-10 times per minute. A
    fixed IP would trip the real limiter (429) well before any test gets
    to assert on the actual behaviour under test."""
    if ip is None:
        _ip_counter[0] += 1
        ip = f"127.0.{_ip_counter[0] // 256}.{_ip_counter[0] % 256}"
    headers = []
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers.append((b"cookie", cookie_header.encode()))
    scope = {
        "type": "http", "method": "GET", "path": "/api/auth/google/callback",
        "headers": headers, "query_string": query_string, "client": (ip, 12345),
    }
    return Request(scope)


def _location(response) -> str:
    return response.headers["location"]


def _error_code(location: str) -> str:
    assert "google_auth_error=" in location
    return location.split("google_auth_error=")[1].split("&")[0]


@pytest.fixture(autouse=True)
def _google_configured(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "test-client-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "https://api.gsprecruitment.nl/api/auth/google/callback")
    monkeypatch.setattr(settings, "frontend_url", "https://gsprecruitment.nl")


# ── _validate_next_path / _default_next_for_role / _next_matches_role ────

@pytest.mark.parametrize("value,expected", [
    (None, None),
    ("", None),
    ("/kandidaten", "/kandidaten"),
    ("/client/dashboard", "/client/dashboard"),
    ("//evil.com", None),  # protocol-relative -- would send the browser off-site
    ("relative/path", None),  # no leading slash
    ("http://evil.com", None),
    ("/" + "x" * 200, None),  # 201 chars, over the 200-char limit
    ("/" + "x" * 199, "/" + "x" * 199),  # exactly 200 chars, still OK
])
def test_validate_next_path(value, expected):
    assert auth_router._validate_next_path(value) == expected


def test_default_next_for_role():
    assert auth_router._default_next_for_role("client") == "/client/"
    assert auth_router._default_next_for_role("candidate") == "/"


def test_next_matches_role():
    assert auth_router._next_matches_role("/client/dashboard", "client") is True
    assert auth_router._next_matches_role("/kandidaten", "client") is False
    assert auth_router._next_matches_role("/kandidaten", "candidate") is True
    assert auth_router._next_matches_role("/client/dashboard", "candidate") is False


# ── google_login ───────────────────────────────────────────────────────

def test_google_login_not_configured_redirects_with_302_not_json_503(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    response = asyncio.run(auth_router.google_login(_make_request()))
    assert response.status_code in (302, 307)
    assert _error_code(_location(response)) == "not_configured"


def test_google_login_sets_cookie_nonce_matching_state_jwt_nonce():
    response = asyncio.run(auth_router.google_login(_make_request(), role="candidate", next=None))
    cookie_header = response.headers["set-cookie"]
    assert "google_oauth_state=" in cookie_header
    nonce = cookie_header.split("google_oauth_state=")[1].split(";")[0]

    location = _location(response)
    state_jwt = location.split("state=")[1].split("&")[0]
    from urllib.parse import unquote
    payload = decode_token(unquote(state_jwt))
    assert payload is not None
    assert payload["nonce"] == nonce
    assert payload["role"] == "candidate"


def test_google_login_invalid_role_defaults_to_candidate():
    response = asyncio.run(auth_router.google_login(_make_request(), role="admin", next=None))
    location = _location(response)
    state_jwt = location.split("state=")[1].split("&")[0]
    from urllib.parse import unquote
    payload = decode_token(unquote(state_jwt))
    assert payload["role"] == "candidate"


def test_google_login_embeds_validated_next_in_state():
    response = asyncio.run(auth_router.google_login(_make_request(), role="client", next="//evil.com"))
    location = _location(response)
    state_jwt = location.split("state=")[1].split("&")[0]
    from urllib.parse import unquote
    payload = decode_token(unquote(state_jwt))
    assert payload["next"] is None  # dropped, never reaches the state JWT


# ── google_callback: fake DB + fake Google endpoints ──────────────────────

class _FakeAuthDB:
    def __init__(self, existing_user=None):
        self.existing_user = existing_user
        self.inserted_users = []
        self.inserted_clients = []
        self.executed = []

    async def fetch_one(self, sql, *args):
        if "SELECT id, email, full_name, role, is_verified, deleted_at FROM users" in sql:
            return self.existing_user
        if "INSERT INTO users" in sql:
            email, password_hash, full_name, role = args
            row = {"id": 999, "email": email, "full_name": full_name, "role": role, "is_verified": True}
            self.inserted_users.append(row)
            return row
        if "INSERT INTO clients" in sql:
            company_name, domain = args
            row = {"id": 42}
            self.inserted_clients.append({"company_name": company_name, "domain": domain})
            return row
        raise AssertionError(f"unexpected fetch_one: {sql}")

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "OK"


class _FakeHttpxResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


class _FakeAsyncClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, *a, **kw):
        return self._response


def _state_for(monkeypatch, role="candidate", next_path=None, nonce="test-nonce-123"):
    """Build a real state JWT the way google_login() would, and a
    matching cookie -- shared setup for every google_callback test."""
    state_jwt = auth_router.create_access_token(
        {"sub": "google_oauth_state", "nonce": nonce, "role": role, "next": next_path},
        expires_delta=__import__("datetime").timedelta(minutes=10),
    )
    return state_jwt, nonce


def _patch_db(monkeypatch, db: _FakeAuthDB):
    monkeypatch.setattr(auth_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(auth_router, "execute", db.execute)


def _patch_token_exchange(monkeypatch, token_response, id_token_str="fake-id-token"):
    json_data = {"id_token": id_token_str} if id_token_str else {}
    monkeypatch.setattr(
        auth_router.httpx, "AsyncClient",
        lambda *a, **kw: _FakeAsyncClient(_FakeHttpxResponse(token_response, json_data=json_data)),
    )


def _patch_id_token_verify(monkeypatch, idinfo=None, raise_exc=None):
    def _verify(id_token_str, request, client_id):
        if raise_exc:
            raise raise_exc
        return idinfo
    monkeypatch.setattr(auth_router.google_id_token, "verify_oauth2_token", _verify)


@pytest.fixture()
def fake_notify(monkeypatch):
    calls = []

    async def _fake(event, fields=None):
        calls.append((event, fields or {}))

    monkeypatch.setattr(auth_router, "notify_owner", _fake)
    return calls


def test_callback_google_error_passed_through(fake_notify):
    request = _make_request()
    response = asyncio.run(auth_router.google_callback(request, error="access_denied"))
    assert _error_code(_location(response)) == "access_denied"


def test_callback_missing_cookie_is_invalid_state(monkeypatch, fake_notify):
    state_jwt, _nonce = _state_for(monkeypatch)
    request = _make_request(cookies=None)
    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))
    assert _error_code(_location(response)) == "invalid_state"


def test_callback_tampered_state_is_invalid_state(fake_notify):
    request = _make_request(cookies={"google_oauth_state": "whatever"})
    response = asyncio.run(auth_router.google_callback(request, code="abc", state="not-a-real-jwt"))
    assert _error_code(_location(response)) == "invalid_state"


def test_callback_nonce_mismatch_is_invalid_state(monkeypatch, fake_notify):
    state_jwt, _nonce = _state_for(monkeypatch, nonce="nonce-A")
    request = _make_request(cookies={"google_oauth_state": "nonce-B"})
    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))
    assert _error_code(_location(response)) == "invalid_state"


def test_callback_missing_code_is_missing_code(monkeypatch, fake_notify):
    state_jwt, nonce = _state_for(monkeypatch)
    request = _make_request(cookies={"google_oauth_state": nonce})
    response = asyncio.run(auth_router.google_callback(request, code=None, state=state_jwt))
    assert _error_code(_location(response)) == "missing_code"


def test_callback_token_exchange_non_200_is_token_exchange_failed(monkeypatch, fake_notify):
    state_jwt, nonce = _state_for(monkeypatch)
    request = _make_request(cookies={"google_oauth_state": nonce})
    _patch_token_exchange(monkeypatch, 400)
    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))
    assert _error_code(_location(response)) == "token_exchange_failed"


def test_callback_missing_id_token_is_token_exchange_failed(monkeypatch, fake_notify):
    state_jwt, nonce = _state_for(monkeypatch)
    request = _make_request(cookies={"google_oauth_state": nonce})
    _patch_token_exchange(monkeypatch, 200, id_token_str=None)
    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))
    assert _error_code(_location(response)) == "token_exchange_failed"


def test_callback_id_token_verify_raises_is_server_error(monkeypatch, fake_notify):
    state_jwt, nonce = _state_for(monkeypatch)
    request = _make_request(cookies={"google_oauth_state": nonce})
    _patch_token_exchange(monkeypatch, 200)
    _patch_id_token_verify(monkeypatch, raise_exc=ValueError("bad signature"))
    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))
    assert _error_code(_location(response)) == "server_error"


def test_callback_email_not_verified(monkeypatch, fake_notify):
    state_jwt, nonce = _state_for(monkeypatch)
    request = _make_request(cookies={"google_oauth_state": nonce})
    _patch_token_exchange(monkeypatch, 200)
    _patch_id_token_verify(monkeypatch, idinfo={"email": "jane@example.com", "email_verified": False, "name": "Jane"})
    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))
    assert _error_code(_location(response)) == "email_not_verified"


def test_callback_account_disabled_for_soft_deleted_user(monkeypatch, fake_notify):
    state_jwt, nonce = _state_for(monkeypatch)
    request = _make_request(cookies={"google_oauth_state": nonce})
    _patch_token_exchange(monkeypatch, 200)
    _patch_id_token_verify(monkeypatch, idinfo={"email": "jane@example.com", "email_verified": True, "name": "Jane"})
    db = _FakeAuthDB(existing_user={
        "id": 1, "email": "jane@example.com", "full_name": "Jane", "role": "candidate",
        "is_verified": True, "deleted_at": "2026-01-01T00:00:00+00:00",
    })
    _patch_db(monkeypatch, db)
    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))
    assert _error_code(_location(response)) == "account_disabled"


def test_callback_admin_account_is_rejected_password_only(monkeypatch, fake_notify):
    """Security-auditor HIGH finding: an admin account must never get a
    token via Google Sign-In. login() checks mfa_required_for_user() and
    stops at an mfa_required challenge for an admin with TOTP enabled;
    this callback had no equivalent check at all, so the same account
    reached through here got a full admin JWT with no second factor.
    core.deps's admin-MFA enforcement only checks that totp_enabled_at is
    set, not that this particular sign-in passed one, so that token
    worked on every admin route. Admins keep using password + TOTP."""
    state_jwt, nonce = _state_for(monkeypatch)
    request = _make_request(cookies={"google_oauth_state": nonce})
    _patch_token_exchange(monkeypatch, 200)
    _patch_id_token_verify(monkeypatch, idinfo={"email": "boss@example.com", "email_verified": True, "name": "Boss"})
    db = _FakeAuthDB(existing_user={
        "id": 1, "email": "boss@example.com", "full_name": "Boss", "role": "admin",
        "is_verified": True, "deleted_at": None,
    })
    _patch_db(monkeypatch, db)

    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))

    assert _error_code(_location(response)) == "admin_use_password"
    assert len(db.inserted_users) == 0
    # No last_login_at update, no token issuance -- the callback must
    # return before reaching any of that for an admin account.
    assert db.executed == []
    events = [e for e, _ in fake_notify]
    assert events == []


def test_callback_new_user_role_client_creates_client_row(monkeypatch, fake_notify):
    state_jwt, nonce = _state_for(monkeypatch, role="client")
    request = _make_request(cookies={"google_oauth_state": nonce})
    _patch_token_exchange(monkeypatch, 200)
    _patch_id_token_verify(monkeypatch, idinfo={"email": "newclient@example.com", "email_verified": True, "name": "New Client"})
    db = _FakeAuthDB(existing_user=None)
    _patch_db(monkeypatch, db)

    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))

    assert response.status_code in (302, 307)
    assert "google_auth_error" not in _location(response)
    assert len(db.inserted_users) == 1
    assert db.inserted_users[0]["role"] == "client"
    assert len(db.inserted_clients) == 1
    # New account -- notify_owner("google_signup", ...) must have fired.
    events = [e for e, _ in fake_notify]
    assert "google_signup" in events
    # New client with no explicit next -- lands on /client/.
    assert "/client/#google_auth=" in _location(response)


def test_callback_new_user_default_role_candidate_gets_candidate_profile(monkeypatch, fake_notify):
    state_jwt, nonce = _state_for(monkeypatch, role="candidate")
    request = _make_request(cookies={"google_oauth_state": nonce})
    _patch_token_exchange(monkeypatch, 200)
    _patch_id_token_verify(monkeypatch, idinfo={"email": "newcandidate@example.com", "email_verified": True, "name": "New Candidate"})
    db = _FakeAuthDB(existing_user=None)
    _patch_db(monkeypatch, db)

    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))

    assert db.inserted_users[0]["role"] == "candidate"
    assert len(db.inserted_clients) == 0
    candidate_profile_inserts = [c for c in db.executed if "candidate_profiles" in c[0]]
    assert len(candidate_profile_inserts) == 1


def test_callback_existing_candidate_requesting_client_role_stays_candidate(monkeypatch, fake_notify):
    """The role requested in the login attempt is ignored for an
    account that already exists -- it keeps its own stored role."""
    state_jwt, nonce = _state_for(monkeypatch, role="client")  # attacker/confused client asks for role=client
    request = _make_request(cookies={"google_oauth_state": nonce})
    _patch_token_exchange(monkeypatch, 200)
    _patch_id_token_verify(monkeypatch, idinfo={"email": "existing@example.com", "email_verified": True, "name": "Existing"})
    db = _FakeAuthDB(existing_user={
        "id": 5, "email": "existing@example.com", "full_name": "Existing", "role": "candidate",
        "is_verified": True, "deleted_at": None,
    })
    _patch_db(monkeypatch, db)

    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))

    assert len(db.inserted_users) == 0  # no new account created
    location = _location(response)
    assert "/#google_auth=" in location  # lands on / (candidate default), not /client/
    assert "/client/" not in location
    events = [e for e, _ in fake_notify]
    assert "google_signup" not in events  # not a new signup


def test_callback_next_used_when_it_matches_role(monkeypatch, fake_notify):
    state_jwt, nonce = _state_for(monkeypatch, role="client", next_path="/client/vacatures")
    request = _make_request(cookies={"google_oauth_state": nonce})
    _patch_token_exchange(monkeypatch, 200)
    _patch_id_token_verify(monkeypatch, idinfo={"email": "client2@example.com", "email_verified": True, "name": "Client Two"})
    db = _FakeAuthDB(existing_user=None)
    _patch_db(monkeypatch, db)

    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))
    assert "/client/vacatures#google_auth=" in _location(response)


def test_callback_next_ignored_when_it_does_not_match_role(monkeypatch, fake_notify):
    """A candidate account can never be sent to a /client/ next path,
    even if one somehow made it into the state -- falls back to /."""
    state_jwt, nonce = _state_for(monkeypatch, role="candidate", next_path="/client/dashboard")
    request = _make_request(cookies={"google_oauth_state": nonce})
    _patch_token_exchange(monkeypatch, 200)
    _patch_id_token_verify(monkeypatch, idinfo={"email": "candidate2@example.com", "email_verified": True, "name": "Candidate Two"})
    db = _FakeAuthDB(existing_user=None)
    _patch_db(monkeypatch, db)

    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))
    assert "/#google_auth=" in _location(response)
    assert "/client/" not in _location(response)


def test_callback_token_never_in_query_string_only_fragment(monkeypatch, fake_notify):
    state_jwt, nonce = _state_for(monkeypatch)
    request = _make_request(cookies={"google_oauth_state": nonce})
    _patch_token_exchange(monkeypatch, 200)
    _patch_id_token_verify(monkeypatch, idinfo={"email": "frag@example.com", "email_verified": True, "name": "Frag"})
    db = _FakeAuthDB(existing_user=None)
    _patch_db(monkeypatch, db)

    response = asyncio.run(auth_router.google_callback(request, code="abc", state=state_jwt))
    location = _location(response)
    assert "#google_auth=" in location
    assert "?google_auth=" not in location


# ── Reset token stored as a hash (core.security.hash_token) ──────────────

class _FakeResetDB:
    def __init__(self, user=None, stored_hash=None, expired=False):
        self.user = user
        self.stored_hash = stored_hash
        self.expired = expired
        self.executed = []

    async def fetch_one(self, sql, *args):
        if "FROM users WHERE email" in sql:
            return self.user
        if "FROM users WHERE reset_token" in sql:
            (candidate_hash,) = args
            if self.expired:
                return None
            if self.stored_hash and candidate_hash == self.stored_hash:
                return {"id": self.user["id"]}
            return None
        raise AssertionError(f"unexpected fetch_one: {sql}")

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        if "SET reset_token" in sql:
            self.stored_hash = args[0]
        return "OK"


@pytest.fixture()
def fake_email(monkeypatch):
    async def _fake_send_template(name, to_email, ctx, lang="nl"):
        return True
    monkeypatch.setattr(auth_router.email_service, "send_template", _fake_send_template)


def test_forgot_password_stores_a_hash_not_the_raw_token(monkeypatch, fake_email):
    from models.schemas import ForgotPasswordRequest
    db = _FakeResetDB(user={"id": 1, "email": "jane@example.com", "full_name": "Jane"})
    monkeypatch.setattr(auth_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(auth_router, "_get_user_by_email", lambda email: db.fetch_one("FROM users WHERE email", email))
    monkeypatch.setattr(auth_router, "execute", db.execute)

    asyncio.run(auth_router.forgot_password(_make_request(), ForgotPasswordRequest(email="jane@example.com")))

    assert db.stored_hash is not None
    assert len(db.stored_hash) == 64  # sha256 hex digest, never the raw urlsafe token
    assert all(c in "0123456789abcdef" for c in db.stored_hash)


def test_reset_password_succeeds_with_the_raw_token(monkeypatch):
    from models.schemas import ResetPasswordRequest
    raw_token = secrets.token_urlsafe(32)
    db = _FakeResetDB(user={"id": 1}, stored_hash=hash_token(raw_token))
    monkeypatch.setattr(auth_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(auth_router, "execute", db.execute)

    result = asyncio.run(auth_router.reset_password(_make_request(), ResetPasswordRequest(token=raw_token, new_password="NewPass123!")))
    assert result == {"message": "Password reset successfully"}


def test_reset_password_fails_with_the_hash_itself(monkeypatch):
    """Someone who somehow obtains the stored hash (not the raw token)
    must not be able to use it as if it were the token."""
    from fastapi import HTTPException
    from models.schemas import ResetPasswordRequest
    raw_token = secrets.token_urlsafe(32)
    stored_hash = hash_token(raw_token)
    db = _FakeResetDB(user={"id": 1}, stored_hash=stored_hash)
    monkeypatch.setattr(auth_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(auth_router, "execute", db.execute)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth_router.reset_password(_make_request(), ResetPasswordRequest(token=stored_hash, new_password="NewPass123!")))
    assert exc_info.value.status_code == 400


def test_reset_password_fails_when_expired(monkeypatch):
    from fastapi import HTTPException
    from models.schemas import ResetPasswordRequest
    raw_token = secrets.token_urlsafe(32)
    db = _FakeResetDB(user={"id": 1}, stored_hash=hash_token(raw_token), expired=True)
    monkeypatch.setattr(auth_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(auth_router, "execute", db.execute)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth_router.reset_password(_make_request(), ResetPasswordRequest(token=raw_token, new_password="NewPass123!")))
    assert exc_info.value.status_code == 400


# ── Logging never carries the recipient's e-mail address ──────────────────

def test_forgot_password_failure_log_has_no_email_address(monkeypatch, caplog):
    from models.schemas import ForgotPasswordRequest

    async def _fake_send_template_fails(name, to_email, ctx, lang="nl"):
        return False
    monkeypatch.setattr(auth_router.email_service, "send_template", _fake_send_template_fails)

    db = _FakeResetDB(user={"id": 7, "email": "leak-me@example.com", "full_name": "Leak Me"})
    monkeypatch.setattr(auth_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(auth_router, "_get_user_by_email", lambda email: db.fetch_one("FROM users WHERE email", email))
    monkeypatch.setattr(auth_router, "execute", db.execute)

    with caplog.at_level("WARNING"):
        asyncio.run(auth_router.forgot_password(_make_request(), ForgotPasswordRequest(email="leak-me@example.com")))

    assert "leak-me@example.com" not in caplog.text
