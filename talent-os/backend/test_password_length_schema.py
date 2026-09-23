"""Issue #177: the 72-UTF-8-byte password cap at the schema layer.

Pure pydantic model tests -- no DB, no network -- covering the four
password fields the issue names: UserRegister.password,
ChangePasswordRequest.new_password, ResetPasswordRequest.new_password,
SetPasswordRequest.new_password. See test_auth_primitives.py for the
corresponding core/security.py hash_password()/verify_password() tests.
"""
import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(__file__))

from models.schemas import (
    UserRegister, ChangePasswordRequest, ResetPasswordRequest, SetPasswordRequest,
)

_MODELS = [
    (UserRegister, "password", {"email": "a@example.com", "full_name": "A B", "role": "candidate"}),
    (ChangePasswordRequest, "new_password", {"current_password": "whatever"}),
    (ResetPasswordRequest, "new_password", {"token": "sometoken"}),
    (SetPasswordRequest, "new_password", {"token": "sometoken"}),
]


@pytest.mark.parametrize("model_cls,field,extra", _MODELS)
def test_password_field_accepts_exactly_72_bytes(model_cls, field, extra):
    password = "a" * 72
    assert len(password.encode("utf-8")) == 72
    instance = model_cls(**extra, **{field: password})
    assert getattr(instance, field) == password


@pytest.mark.parametrize("model_cls,field,extra", _MODELS)
def test_password_field_rejects_73_bytes(model_cls, field, extra):
    password = "a" * 73
    assert len(password.encode("utf-8")) == 73
    with pytest.raises(ValidationError) as exc_info:
        model_cls(**extra, **{field: password})
    # Dutch-first, house register: "Wachtwoord ... / Password ..."
    message = str(exc_info.value)
    assert "Wachtwoord" in message
    assert "72 bytes" in message


@pytest.mark.parametrize("model_cls,field,extra", _MODELS)
def test_password_field_rejects_multibyte_password_over_72_bytes(model_cls, field, extra):
    # 24 euro signs = 72 bytes exactly (accepted); 25 = 75 bytes (rejected)
    # -- a case a character-count max_length alone would miss.
    ok = "€" * 24
    assert len(ok.encode("utf-8")) == 72
    model_cls(**extra, **{field: ok})

    too_long = "€" * 25
    assert len(too_long.encode("utf-8")) == 75
    with pytest.raises(ValidationError):
        model_cls(**extra, **{field: too_long})
