"""Tests for POST /api/auth/refresh -- WS-C.3a.

Covers only the paths that reject before touching the database (bad/missing
token, non-numeric `sub`, impersonation tokens), since this test file has
no Postgres available. The happy path (valid token -> new TokenResponse) is
covered by WS-C.14's integration suite, which runs against a real DB.
"""
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient
from core.security import create_access_token
import main

client = TestClient(main.app)


def _refresh(token: str):
    return client.post("/api/auth/refresh", json={"refresh_token": token})


def test_refresh_rejects_missing_token():
    r = client.post("/api/auth/refresh", json={})
    assert r.status_code == 400


def test_refresh_rejects_invalid_token():
    r = _refresh("not-a-real-jwt")
    assert r.status_code == 401


def test_refresh_rejects_non_numeric_sub():
    # decode_token round-trips whatever string is in 'sub'; a token minted
    # (hypothetically, or by a bug elsewhere) with a non-numeric sub must
    # 401, not 500 -- this is the exact bug this item fixes (int(sub) on an
    # integer column, previously uncaught).
    token = create_access_token({"sub": "not-an-id", "role": "candidate"})
    r = _refresh(token)
    assert r.status_code == 401


def test_refresh_rejects_impersonation_token():
    # Mirrors routers/admin.py impersonate_user's token shape exactly.
    token = create_access_token({"sub": 1, "role": "candidate", "impersonator": 99})
    r = _refresh(token)
    assert r.status_code == 401
    assert "impersonat" in r.json()["detail"].lower()


def test_refresh_rejects_expired_token():
    token = create_access_token({"sub": 1, "role": "candidate"}, expires_delta=timedelta(seconds=-1))
    r = _refresh(token)
    assert r.status_code == 401
