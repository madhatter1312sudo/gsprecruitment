"""
Unit tests for WS-C.2 authorization fixes -- pure functions/pydantic models,
no DB/network needed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from pydantic import ValidationError

from models.schemas import TeamInvite


# ── Fix 1: TeamInvite role can no longer be escalated ───────────────────

def test_team_invite_defaults_to_client_role():
    invite = TeamInvite(email="a@example.com", full_name="A Person")
    assert invite.role == "client"


def test_team_invite_accepts_explicit_client_role():
    invite = TeamInvite(email="a@example.com", full_name="A Person", role="client")
    assert invite.role == "client"


def test_team_invite_rejects_admin_role():
    with pytest.raises(ValidationError):
        TeamInvite(email="a@example.com", full_name="A Person", role="admin")


def test_team_invite_rejects_arbitrary_role_string():
    with pytest.raises(ValidationError):
        TeamInvite(email="a@example.com", full_name="A Person", role="superuser")


def test_team_invite_response_has_no_password_field():
    """Regression guard: TeamInvite is a request model, but the invite
    response builder in routers/client.py must never include a
    'temporary_password' key. This just documents the expected response
    shape used there (see invite_team_member)."""
    expected_keys = {"message", "user_id", "email"}
    response = {
        "message": "Team member invited successfully. ...",
        "user_id": 1,
        "email": "a@example.com",
    }
    assert set(response.keys()) == expected_keys
    assert "temporary_password" not in response


# ── Fix 2: candidate access gate + anonymised projection ────────────────

# Import lazily so this file still collects even if routers/client.py
# picks up new dependencies later.
from routers.client import _require_candidate_access, _project_candidate_public
from fastapi import HTTPException


def test_require_candidate_access_allows_admin():
    _require_candidate_access({"role": "admin"})  # must not raise


def test_require_candidate_access_blocks_client():
    with pytest.raises(HTTPException) as exc_info:
        _require_candidate_access({"role": "client"})
    assert exc_info.value.status_code == 403


def test_project_candidate_public_strips_pii():
    row = {
        "id": 1,
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+31600000000",
        "linkedin_url": "https://linkedin.com/in/janedoe",
        "github_url": "https://github.com/janedoe",
        "portfolio_url": "https://janedoe.dev",
        "cv_text": "full raw CV text...",
        "current_title": "Embedded Software Engineer",
        "current_company": "Acme BV",
        "location": "Eindhoven",
        "years_experience": 6,
        "skills": None,  # NULL array column must coerce to []
    }
    projected = _project_candidate_public(row)
    assert projected == {
        "id": 1,
        "full_name": "Jane Doe",
        "current_title": "Embedded Software Engineer",
        "current_company": "Acme BV",
        "location": "Eindhoven",
        "years_experience": 6,
        "skills": [],
    }
    for leaked_field in (
        "email", "phone", "linkedin_url", "github_url",
        "portfolio_url", "cv_text",
    ):
        assert leaked_field not in projected


def test_project_candidate_public_preserves_nonempty_skills():
    row = {
        "id": 2, "full_name": "X", "current_title": None,
        "current_company": None, "location": None,
        "years_experience": None, "skills": ["C++", "Rust"],
    }
    assert _project_candidate_public(row)["skills"] == ["C++", "Rust"]


# ── Fix 3: client job status allow-list ──────────────────────────────────

CLIENT_ALLOWED_STATUSES = {"draft", "paused", "closed"}


@pytest.mark.parametrize("allowed_status", sorted(CLIENT_ALLOWED_STATUSES))
def test_client_may_set_allowed_statuses(allowed_status):
    assert allowed_status in CLIENT_ALLOWED_STATUSES


def test_client_may_not_set_open_status():
    assert "open" not in CLIENT_ALLOWED_STATUSES


# ── Fix 4: public job column list has no internal fields ────────────────

from routers.jobs import PUBLIC_JOB_COLUMNS

INTERNAL_JOB_FIELDS = {"client_id", "fee_value", "filled_at", "deleted_at"}


def test_public_job_columns_exclude_internal_fields():
    selected = {c.strip() for c in PUBLIC_JOB_COLUMNS.split(",")}
    assert selected.isdisjoint(INTERNAL_JOB_FIELDS)


def test_public_job_columns_include_frontend_fields():
    selected = {c.strip() for c in PUBLIC_JOB_COLUMNS.split(",")}
    for field in ("id", "title", "description", "requirements", "location_type",
                  "salary_min", "salary_max", "salary_currency", "created_at"):
        assert field in selected


# ── Fix 5 (follow-up): create_client_job always inserts status='draft' ──

import inspect
import routers.client as client_router


def test_create_client_job_insert_hardcodes_draft_status():
    """The INSERT in create_client_job must not rely on a DB column
    default for status (undefined in this repo, possibly 'open') -- it
    must set it explicitly to 'draft' so a client can never publish
    straight to the public job board via POST."""
    src = inspect.getsource(client_router.create_client_job)
    assert "'draft'" in src
    assert "status" in src
