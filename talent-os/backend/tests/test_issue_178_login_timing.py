"""
Unit tests for issue #178, part 2: routers/auth.py login() timing for an
unknown e-mail.

An unknown address must still do one bcrypt check (against the fixed
module-level dummy hash), so it takes the same time as a known-but-wrong
password. The 401 detail stays exactly "Invalid email or password".

Same TestClient + monkeypatch style as tests/test_ws_e4_ratelimit_lockout.py
and tests/test_ws_e12_mfa.py -- no DB/network needed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

from fastapi.testclient import TestClient

import main as _main_module
import routers.auth as auth_router
from core.security import verify_password

client = TestClient(_main_module.app)


def test_unknown_email_calls_verify_password_once_against_dummy_hash(monkeypatch):
    async def fake_fetch_one(sql, *args):
        return None  # unknown user

    calls = []

    def spying_verify_password(plain, hashed):
        calls.append((plain, hashed))
        return verify_password(plain, hashed)

    monkeypatch.setattr(auth_router, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(auth_router, "verify_password", spying_verify_password)

    r = client.post(
        "/api/auth/login",
        json={"email": "nobody-issue178@example.com", "password": "whatever-they-typed"},
    )

    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"
    assert len(calls) == 1
    assert calls[0][0] == "whatever-they-typed"
    assert calls[0][1] == auth_router._DUMMY_PASSWORD_HASH


def test_dummy_password_hash_is_a_real_bcrypt_hash():
    assert auth_router._DUMMY_PASSWORD_HASH.startswith("$2b$")
    assert verify_password(
        "gsp-dummy-password-for-login-timing-safety",
        auth_router._DUMMY_PASSWORD_HASH,
    )
