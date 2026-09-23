"""Tests for auth system primitives -- pure functions, no DB/network needed."""
import os
import sys
from datetime import timedelta

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from core.config import settings
from core.security import (
    hash_password, verify_password, create_access_token, decode_token,
    PasswordTooLongError,
)


def test_config_loads():
    assert settings.jwt_algorithm
    assert isinstance(settings.cors_origin_list, list)


def test_password_hashing():
    h = hash_password("test1234!")
    assert verify_password("test1234!", h)
    assert not verify_password("wrong-password", h)


# ── Issue #177: 72-UTF-8-byte cap ahead of the bcrypt 5 bump ────────────
# bcrypt only ever hashes the first 72 bytes of a password. Under bcrypt 4
# that was a silent truncation; bcrypt 5 raises ValueError instead.
# hash_password()/verify_password() are the second gate (after
# models/schemas.py's field validator) -- these exercise them directly,
# independent of that schema layer.

def test_hash_password_accepts_exactly_72_bytes():
    password = "a" * 72
    assert len(password.encode("utf-8")) == 72
    h = hash_password(password)
    assert verify_password(password, h)


def test_hash_password_rejects_73_bytes():
    password = "a" * 73
    assert len(password.encode("utf-8")) == 73
    with pytest.raises(PasswordTooLongError):
        hash_password(password)


def test_hash_password_rejects_multibyte_password_over_72_bytes():
    # '€' is 3 UTF-8 bytes: 24 of them is 72 characters but 72 bytes only
    # up to 24; 25 pushes the encoding to 75 bytes while staying a
    # plausible-looking password length-wise, which is exactly the shape
    # a character-count max_length (schemas.py's max_length=128) misses.
    password = "€" * 24
    assert len(password.encode("utf-8")) == 72
    h = hash_password(password)
    assert verify_password(password, h)

    over_limit = "€" * 25
    assert len(over_limit.encode("utf-8")) == 75
    with pytest.raises(PasswordTooLongError):
        hash_password(over_limit)


def test_verify_password_returns_false_not_raises_for_over_72_bytes():
    # login's password field has no schema-level length cap, so
    # verify_password() is the only gate on that path -- it must return
    # False (wrong password), not raise, or a long password would 500 a
    # login attempt instead of just failing it.
    h = hash_password("normal-password")
    too_long = "b" * 73
    assert verify_password(too_long, h) is False


def test_bcrypt4_hash_still_verifies_under_bcrypt5():
    # Fixed hash produced by bcrypt 4.3.0 (bcrypt.hashpw with gensalt(rounds=4))
    # for the password below -- proves existing stored hashes keep working
    # once bcrypt is bumped to >=5.0.0.
    fixed_hash = "$2b$04$NE99WWJMRr362J04oRmyteetW/XtL5L4J/5iBDYkzXHh8nDHOh7Wq"
    assert verify_password("gsp-bcrypt4-fixture-pw", fixed_hash) is True
    assert verify_password("wrong-password", fixed_hash) is False


def test_jwt_roundtrip():
    # python-jose requires 'sub' to be a string; create_access_token stringifies
    # it for us, so it always round-trips as a string even if given an int.
    token = create_access_token({"sub": 1, "role": "admin"})
    payload = decode_token(token)
    assert payload["sub"] == "1"
    assert payload["role"] == "admin"


def test_jwt_custom_expiry():
    token = create_access_token({"sub": 2}, expires_delta=timedelta(hours=1))
    payload = decode_token(token)
    assert payload["sub"] == "2"


def test_jwt_rejects_tampered_token():
    token = create_access_token({"sub": 3})
    tampered = token[:-4] + "abcd"
    assert decode_token(tampered) is None
