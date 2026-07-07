"""Tests for auth system primitives -- pure functions, no DB/network needed."""
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(__file__))

from core.config import settings
from core.security import hash_password, verify_password, create_access_token, decode_token


def test_config_loads():
    assert settings.jwt_algorithm
    assert isinstance(settings.cors_origin_list, list)


def test_password_hashing():
    h = hash_password("test1234!")
    assert verify_password("test1234!", h)
    assert not verify_password("wrong-password", h)


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
