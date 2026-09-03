"""
Unit tests for WS-C.6 (activities -- unified activity/task log,
migrations/028_activities.py, routers/activities.py).

Pydantic-model + migration-text checks need no DB (same style as
tests/test_ws_c4_c5_c10_crm.py). The client-portal scoping tests drive
the real FastAPI app through fastapi.testclient.TestClient, stubbing the
auth dependency via app.dependency_overrides and core.database's
fetch_one/fetch_all/execute via monkeypatch (same style as
tests/test_ws_e2_e3_verification.py's pipeline-gate section and
tests/test_gdpr_erasure.py's _FakeDB) -- no live Postgres needed.
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from models.schemas import (
    ACTIVITY_SUBJECT_TYPES, ACTIVITY_TYPES,
    ActivityCreate, ActivityUpdate, ClientActivityCreate,
)


# ── ActivityCreate: subject_type / type CHECK values ─────────────────────

@pytest.mark.parametrize("subject_type", ACTIVITY_SUBJECT_TYPES)
def test_activity_create_accepts_each_allowed_subject_type(subject_type):
    a = ActivityCreate(subject_type=subject_type, subject_id=1, type="note")
    assert a.subject_type == subject_type


def test_activity_create_rejects_bad_subject_type():
    with pytest.raises(ValidationError):
        ActivityCreate(subject_type="deal", subject_id=1, type="note")


@pytest.mark.parametrize("activity_type", ACTIVITY_TYPES)
def test_activity_create_accepts_each_allowed_type(activity_type):
    a = ActivityCreate(subject_type="candidate", subject_id=1, type=activity_type)
    assert a.type == activity_type


def test_activity_create_rejects_bad_type():
    with pytest.raises(ValidationError):
        ActivityCreate(subject_type="candidate", subject_id=1, type="sms")


def test_activity_create_body_and_dates_optional():
    a = ActivityCreate(subject_type="job", subject_id=5, type="task")
    assert a.body is None
    assert a.due_at is None
    assert a.completed_at is None


def test_activity_update_all_fields_optional():
    u = ActivityUpdate()
    assert u.model_dump(exclude_unset=True) == {}


def test_activity_update_cannot_set_subject_or_type():
    """ActivityUpdate deliberately has no subject_type/subject_id/type
    fields -- a row's identity is fixed at creation."""
    fields = ActivityUpdate.model_fields.keys()
    assert "subject_type" not in fields
    assert "subject_id" not in fields
    assert "type" not in fields


# ── ClientActivityCreate: subject_type restricted to job|candidate ───────

@pytest.mark.parametrize("subject_type", ["job", "candidate"])
def test_client_activity_create_accepts_job_and_candidate(subject_type):
    c = ClientActivityCreate(subject_type=subject_type, subject_id=1, type="note")
    assert c.subject_type == subject_type


@pytest.mark.parametrize("subject_type", ["client", "prospect", "placement", "lead"])
def test_client_activity_create_rejects_other_subject_types(subject_type):
    """A client-portal caller may only ever write activities against a job
    or a candidate -- every other subject_type is admin-only."""
    with pytest.raises(ValidationError):
        ClientActivityCreate(subject_type=subject_type, subject_id=1, type="note")


# ── Migration text: idempotent, CHECK values, no unique index ────────────

def _load_migration(filename):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations", filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_028_activities_migration_idempotent_and_checked():
    mod = _load_migration("028_activities.py")
    sql = mod.MIGRATION_SQL
    assert "CREATE TABLE IF NOT EXISTS activities" in sql
    for value in ACTIVITY_SUBJECT_TYPES:
        assert value in sql
    for value in ACTIVITY_TYPES:
        assert value in sql
    assert "REFERENCES users(id)" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_activities_subject ON activities(subject_type, subject_id)" in sql
    assert "CREATE INDEX IF NOT EXISTS idx_activities_due_at ON activities(due_at)" in sql
    assert "DO $$" not in sql
    assert "CREATE UNIQUE INDEX" not in sql


def test_migration_028_version_matches_filename():
    mod = _load_migration("028_activities.py")
    assert mod.VERSION == "028_activities"


# ── Client-portal scoping: TestClient + stubbed auth + stubbed DB ────────

import main as _main_module  # noqa: E402
from core.deps import get_verified_user as _get_verified_user_dep  # noqa: E402
import routers.activities as activities_router  # noqa: E402

CLIENT_USER = {
    "id": 42,
    "email": "client@example.com",
    "full_name": "A Client User",
    "role": "client",
    "is_verified": True,
    "approved_by_admin_at": "2026-01-01T00:00:00Z",
}


@pytest.fixture
def test_client():
    tc = TestClient(_main_module.app)
    yield tc
    _main_module.app.dependency_overrides.pop(_get_verified_user_dep, None)


def _override_as_client_user():
    _main_module.app.dependency_overrides[_get_verified_user_dep] = lambda: CLIENT_USER


class _StubDB:
    """Tiny in-memory stub for core.database's fetch_one/fetch_all/
    fetch_val/execute, keyed by a substring of the SQL -- same recording
    style as tests/test_gdpr_erasure.py's _FakeDB."""

    def __init__(self, client_id=7, owns_job=False, owns_candidate=False):
        self.client_id = client_id
        self.owns_job = owns_job
        self.owns_candidate = owns_candidate
        self.statements = []

    async def fetch_one(self, sql, *args):
        self.statements.append((sql, args))
        if "FROM clients c JOIN user_clients uc" in sql:
            return {"id": self.client_id} if self.client_id is not None else None
        if "FROM job_orders WHERE id = $1 AND client_id = $2" in sql:
            return {"id": args[0]} if self.owns_job else None
        if "FROM pipeline_entries WHERE client_id = $1 AND candidate_id = $2" in sql:
            return {"id": 1} if self.owns_candidate else None
        if sql.strip().startswith("INSERT INTO activities"):
            return {
                "id": 99, "subject_type": args[0], "subject_id": args[1],
                "type": args[2], "body": args[3], "due_at": args[4],
                "completed_at": args[5], "created_by": args[6],
                "created_at": "2026-09-03T00:00:00Z", "updated_at": None,
            }
        return None

    async def fetch_all(self, sql, *args):
        self.statements.append((sql, args))
        return []

    async def fetch_val(self, sql, *args):
        self.statements.append((sql, args))
        return 0

    async def execute(self, sql, *args):
        self.statements.append((sql, args))
        return "OK"


def _patch_db(monkeypatch, **kwargs):
    db = _StubDB(**kwargs)
    monkeypatch.setattr(activities_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(activities_router, "fetch_all", db.fetch_all)
    monkeypatch.setattr(activities_router, "fetch_val", db.fetch_val)
    monkeypatch.setattr(activities_router, "execute", db.execute)
    return db


def test_client_create_activity_on_owned_job_succeeds(test_client, monkeypatch):
    _override_as_client_user()
    _patch_db(monkeypatch, client_id=7, owns_job=True)

    res = test_client.post(
        "/api/v1/client/activities",
        json={"subject_type": "job", "subject_id": 3, "type": "note", "body": "hi"},
    )
    assert res.status_code == 201
    assert res.json()["id"] == 99


def test_client_create_activity_on_unowned_job_is_403(test_client, monkeypatch):
    """Regression guard for WS-C.6: a client must never be able to attach
    an activity to a job it doesn't own by simply naming its id."""
    _override_as_client_user()
    _patch_db(monkeypatch, client_id=7, owns_job=False)

    res = test_client.post(
        "/api/v1/client/activities",
        json={"subject_type": "job", "subject_id": 999, "type": "note", "body": "hi"},
    )
    assert res.status_code == 403


def test_client_create_activity_on_candidate_not_in_pipeline_is_403(test_client, monkeypatch):
    _override_as_client_user()
    _patch_db(monkeypatch, client_id=7, owns_candidate=False)

    res = test_client.post(
        "/api/v1/client/activities",
        json={"subject_type": "candidate", "subject_id": 55, "type": "call", "body": "hi"},
    )
    assert res.status_code == 403


def test_client_create_activity_on_candidate_in_own_pipeline_succeeds(test_client, monkeypatch):
    _override_as_client_user()
    _patch_db(monkeypatch, client_id=7, owns_candidate=True)

    res = test_client.post(
        "/api/v1/client/activities",
        json={"subject_type": "candidate", "subject_id": 55, "type": "call", "body": "hi"},
    )
    assert res.status_code == 201


def test_client_without_client_record_gets_403_not_500(test_client, monkeypatch):
    _override_as_client_user()
    _patch_db(monkeypatch, client_id=None)

    res = test_client.post(
        "/api/v1/client/activities",
        json={"subject_type": "job", "subject_id": 1, "type": "note", "body": "hi"},
    )
    assert res.status_code == 403


def test_client_activity_create_rejects_non_job_candidate_subject_type_at_body_validation(test_client, monkeypatch):
    """Even before any DB lookup runs, the client-portal body schema
    itself refuses subject_type values other than job|candidate (422),
    e.g. an attempt to write a 'client' or 'prospect' activity."""
    _override_as_client_user()
    _patch_db(monkeypatch, client_id=7, owns_job=True)

    res = test_client.post(
        "/api/v1/client/activities",
        json={"subject_type": "client", "subject_id": 1, "type": "note", "body": "hi"},
    )
    assert res.status_code == 422


# ── Admin CRUD: soft delete never issues a real DELETE ────────────────────

from core.deps import get_current_user as _get_current_user_dep  # noqa: E402

ADMIN_USER = {"id": 1, "email": "admin@example.com", "full_name": "Admin", "role": "admin"}


@pytest.fixture
def admin_test_client():
    tc = TestClient(_main_module.app)
    _main_module.app.dependency_overrides[_get_current_user_dep] = lambda: ADMIN_USER
    yield tc
    _main_module.app.dependency_overrides.pop(_get_current_user_dep, None)


class _AdminStubDB(_StubDB):
    async def fetch_one(self, sql, *args):
        self.statements.append((sql, args))
        if sql.strip().startswith("UPDATE activities SET deleted_at"):
            return {"id": args[0]}
        if sql.strip().startswith("INSERT INTO activities"):
            return await super().fetch_one(sql, *args)
        return None


def test_admin_delete_activity_soft_deletes(admin_test_client, monkeypatch):
    db = _AdminStubDB()
    monkeypatch.setattr(activities_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(activities_router, "fetch_all", db.fetch_all)
    monkeypatch.setattr(activities_router, "fetch_val", db.fetch_val)
    monkeypatch.setattr(activities_router, "execute", db.execute)

    res = admin_test_client.delete("/api/v1/admin/activities/7")
    assert res.status_code == 204

    delete_stmts = [sql for sql, _ in db.statements if sql.strip().upper().startswith("DELETE")]
    assert delete_stmts == [], "soft delete must never issue a real DELETE statement"
    update_stmts = [sql for sql, _ in db.statements if "SET deleted_at = NOW()" in sql]
    assert len(update_stmts) == 1


def test_admin_delete_activity_writes_audit_log_json(admin_test_client, monkeypatch):
    db = _AdminStubDB()
    monkeypatch.setattr(activities_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(activities_router, "fetch_all", db.fetch_all)
    monkeypatch.setattr(activities_router, "fetch_val", db.fetch_val)
    monkeypatch.setattr(activities_router, "execute", db.execute)

    res = admin_test_client.delete("/api/v1/admin/activities/7")
    assert res.status_code == 204

    audit_calls = [(sql, args) for sql, args in db.statements if "INSERT INTO audit_log" in sql]
    assert len(audit_calls) == 1
    _, args = audit_calls[0]
    # changes is json.dumps'd (a str), never a raw dict (commit 72b4bcd)
    changes_arg = args[-1]
    assert isinstance(changes_arg, str)


def test_admin_create_activity_writes_audit_log_json(admin_test_client, monkeypatch):
    db = _AdminStubDB()
    monkeypatch.setattr(activities_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(activities_router, "fetch_all", db.fetch_all)
    monkeypatch.setattr(activities_router, "fetch_val", db.fetch_val)
    monkeypatch.setattr(activities_router, "execute", db.execute)

    res = admin_test_client.post(
        "/api/v1/admin/activities",
        json={"subject_type": "candidate", "subject_id": 1, "type": "note", "body": "hi"},
    )
    assert res.status_code == 201

    audit_calls = [(sql, args) for sql, args in db.statements if "INSERT INTO audit_log" in sql]
    assert len(audit_calls) == 1
    _, args = audit_calls[0]
    assert isinstance(args[-1], str)
