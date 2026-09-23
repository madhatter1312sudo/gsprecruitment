"""
Unit tests for issue #178, part 1: main.py's RequestValidationError handler.

A 422 on a password field (register, change-password) must carry no
`input`; a 422 on a non-password field still does; pydantic's
"Value error, " prefix is stripped from `msg`. Every other field of
FastAPI's default {"detail": [...]} body is kept so the admin panel's
existing error path still reads it.

Same TestClient + dependency_overrides style as tests/test_ws_e12_mfa.py
and tests/test_admin_health_routines.py -- no DB/network needed since
these are all pure request-validation 422s.
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
from core.deps import get_current_user as _get_current_user_dep

client = TestClient(_main_module.app)


def test_register_short_password_422_has_no_input():
    r = client.post(
        "/api/auth/register",
        json={
            "email": "issue178-register@example.com",
            "password": "short1",  # < min_length=8
            "full_name": "Issue 178",
        },
    )
    assert r.status_code == 422
    body = r.json()
    password_errors = [e for e in body["detail"] if "password" in e["loc"]]
    assert password_errors, "expected a validation error on password"
    for err in password_errors:
        assert "input" not in err
        # every other field FastAPI normally sends is still present
        assert "loc" in err and "msg" in err and "type" in err


def test_change_password_short_new_password_422_has_no_input():
    _main_module.app.dependency_overrides[_get_current_user_dep] = lambda: {
        "id": 1,
        "role": "candidate",
        "email": "issue178-cp@example.com",
    }
    try:
        r = client.post(
            "/api/auth/change-password",
            json={"current_password": "whatever-current", "new_password": "short1"},
        )
    finally:
        _main_module.app.dependency_overrides.pop(_get_current_user_dep, None)

    assert r.status_code == 422
    body = r.json()
    password_errors = [
        e for e in body["detail"]
        if any(p in e["loc"] for p in ("new_password", "current_password"))
    ]
    assert password_errors, "expected a validation error on new_password"
    for err in password_errors:
        assert "input" not in err


def test_non_password_422_still_carries_input():
    r = client.post(
        "/api/auth/register",
        json={
            "email": "not-an-email",
            "password": "a-fine-password-123",
            "full_name": "Issue 178",
        },
    )
    assert r.status_code == 422
    body = r.json()
    email_errors = [e for e in body["detail"] if "email" in e["loc"]]
    assert email_errors, "expected a validation error on email"
    for err in email_errors:
        assert "input" in err


def test_value_error_prefix_is_stripped():
    """models/schemas.py's password-length field_validator raises a plain
    ValueError, which pydantic wraps as 'Value error, <message>' -- the
    handler must strip that prefix for a clean message."""
    # A password 73 UTF-8 bytes long trips _validate_password_max_bytes's
    # ValueError (bcrypt's 72-byte cap, issue #177), a msg built with
    # raise ValueError(...), not a Field(...) constraint.
    r = client.post(
        "/api/auth/register",
        json={
            "email": "issue178-toolong@example.com",
            "password": "x" * 73,
            "full_name": "Issue 178",
        },
    )
    assert r.status_code == 422
    body = r.json()
    password_errors = [e for e in body["detail"] if "password" in e["loc"]]
    assert password_errors
    for err in password_errors:
        assert "input" not in err
        assert not err["msg"].startswith("Value error, ")
