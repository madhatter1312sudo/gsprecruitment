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
import json
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
    ActivityCreate, ActivityUpdate, ActivityResponse, ClientActivityCreate,
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


def test_activity_create_internal_defaults_true():
    a = ActivityCreate(subject_type="candidate", subject_id=1, type="note")
    assert a.internal is True


def test_activity_create_internal_can_opt_out():
    a = ActivityCreate(subject_type="candidate", subject_id=1, type="note", internal=False)
    assert a.internal is False


def test_activity_update_all_fields_optional():
    u = ActivityUpdate()
    assert u.model_dump(exclude_unset=True) == {}


def test_activity_update_can_set_internal():
    u = ActivityUpdate(internal=False)
    assert u.model_dump(exclude_unset=True) == {"internal": False}


def test_activity_update_cannot_set_subject_or_type():
    """ActivityUpdate deliberately has no subject_type/subject_id/type
    fields -- a row's identity is fixed at creation."""
    fields = ActivityUpdate.model_fields.keys()
    assert "subject_type" not in fields
    assert "subject_id" not in fields
    assert "type" not in fields


def test_activity_response_exposes_internal():
    fields = ActivityResponse.model_fields.keys()
    assert "internal" in fields


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


def test_client_activity_create_has_no_internal_field():
    """A client-portal caller can never set `internal` -- it's always
    forced to false server-side (routers/activities.py), never taken from
    the request body."""
    assert "internal" not in ClientActivityCreate.model_fields.keys()


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


def test_028_activities_migration_adds_internal_column_idempotently():
    """Code-review follow-up: `internal` is added via a separate ADD
    COLUMN IF NOT EXISTS (not inline on the CREATE TABLE), so an
    environment that already ran this migration's first cut converges on
    a re-run instead of erroring on a duplicate column."""
    mod = _load_migration("028_activities.py")
    sql = mod.MIGRATION_SQL
    assert "ALTER TABLE activities ADD COLUMN IF NOT EXISTS internal BOOLEAN NOT NULL DEFAULT true" in sql
    # It must come after the CREATE TABLE, not inline on it.
    assert sql.index("CREATE TABLE IF NOT EXISTS activities") < sql.index("ADD COLUMN IF NOT EXISTS internal")


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
            # Admin create passes `internal` as an 8th bound param ($8);
            # the client-portal create hardcodes `false` as a SQL literal
            # instead of binding it, so it only ever passes 7 args.
            internal = args[7] if "$8" in sql else False
            return {
                "id": 99, "subject_type": args[0], "subject_id": args[1],
                "type": args[2], "body": args[3], "due_at": args[4],
                "completed_at": args[5], "created_by": args[6],
                "internal": internal,
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


def test_client_list_activities_query_excludes_internal_and_scopes_ownership(test_client, monkeypatch):
    """Code-review follow-up: GET /api/v1/client/activities must filter
    `internal = false` in the SQL itself (not just in application code
    after the fact), on top of the existing job_orders/pipeline_entries
    ownership EXISTS clauses."""
    _override_as_client_user()
    db = _patch_db(monkeypatch, client_id=7)

    res = test_client.get("/api/v1/client/activities")
    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}

    select_stmts = [sql for sql, _ in db.statements if "FROM activities a WHERE" in sql]
    assert select_stmts, "expected at least one query against activities"
    for sql in select_stmts:
        assert "a.internal = false" in sql
        assert "a.subject_type = 'job' AND EXISTS" in sql
        assert "FROM job_orders jo WHERE jo.id = a.subject_id AND jo.client_id = $1" in sql
        assert "a.subject_type = 'candidate' AND EXISTS" in sql
        assert "FROM pipeline_entries pe WHERE pe.candidate_id = a.subject_id AND pe.client_id = $1" in sql


def test_client_list_activities_without_client_record_returns_empty_no_query(test_client, monkeypatch):
    _override_as_client_user()
    db = _patch_db(monkeypatch, client_id=None)

    res = test_client.get("/api/v1/client/activities")
    assert res.status_code == 200
    assert res.json()["items"] == []
    select_stmts = [sql for sql, _ in db.statements if "FROM activities a WHERE" in sql]
    assert select_stmts == []


def test_client_created_activity_is_always_internal_false(test_client, monkeypatch):
    _override_as_client_user()
    _patch_db(monkeypatch, client_id=7, owns_job=True)

    res = test_client.post(
        "/api/v1/client/activities",
        json={"subject_type": "job", "subject_id": 3, "type": "note", "body": "hi"},
    )
    assert res.status_code == 201
    assert res.json()["internal"] is False


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
    """Extends _StubDB with the admin-side UPDATE branches (soft-delete
    and PATCH both go through `UPDATE activities SET ... RETURNING *`).
    The returned row always carries a non-empty `body` so audit-payload
    tests can assert that text never reaches audit_log."""

    async def fetch_one(self, sql, *args):
        self.statements.append((sql, args))
        if sql.strip().startswith("UPDATE activities SET"):
            return {
                "id": 7, "subject_type": "candidate", "subject_id": 1,
                "type": "note", "body": "secret candidate note text",
                "due_at": None, "completed_at": None, "internal": True,
                "created_by": 1, "created_at": "2026-09-03T00:00:00Z",
                "updated_at": "2026-09-03T00:00:00Z",
            }
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


def _patch_admin_db(monkeypatch, **kwargs):
    db = _AdminStubDB(**kwargs)
    monkeypatch.setattr(activities_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(activities_router, "fetch_all", db.fetch_all)
    monkeypatch.setattr(activities_router, "fetch_val", db.fetch_val)
    monkeypatch.setattr(activities_router, "execute", db.execute)
    return db


# ── Code-review follow-up: audit payloads never carry the free-text body ──

def _audit_changes(db):
    audit_calls = [(sql, args) for sql, args in db.statements if "INSERT INTO audit_log" in sql]
    assert len(audit_calls) == 1
    _, args = audit_calls[0]
    return json.loads(args[-1])


def test_admin_create_activity_audit_payload_has_no_body(admin_test_client, monkeypatch):
    db = _patch_admin_db(monkeypatch)

    res = admin_test_client.post(
        "/api/v1/admin/activities",
        json={"subject_type": "candidate", "subject_id": 1, "type": "note", "body": "secret text"},
    )
    assert res.status_code == 201

    changes = _audit_changes(db)
    assert "body" not in changes
    assert changes == {
        "subject_type": "candidate", "subject_id": 1, "type": "note",
        "internal": True, "has_body": True,
    }


def test_admin_update_activity_audit_payload_has_no_body(admin_test_client, monkeypatch):
    db = _patch_admin_db(monkeypatch)

    res = admin_test_client.patch(
        "/api/v1/admin/activities/7",
        json={"body": "revised secret text"},
    )
    assert res.status_code == 200

    changes = _audit_changes(db)
    assert "body" not in changes
    assert changes["has_body"] is True


def test_admin_delete_activity_audit_payload_has_no_body(admin_test_client, monkeypatch):
    db = _patch_admin_db(monkeypatch)

    res = admin_test_client.delete("/api/v1/admin/activities/7")
    assert res.status_code == 204

    changes = _audit_changes(db)
    assert "body" not in changes
    assert set(changes.keys()) == {"subject_type", "subject_id", "type", "internal", "has_body"}


def test_client_create_activity_audit_payload_has_no_body(test_client, monkeypatch):
    _override_as_client_user()
    db = _patch_db(monkeypatch, client_id=7, owns_job=True)

    res = test_client.post(
        "/api/v1/client/activities",
        json={"subject_type": "job", "subject_id": 3, "type": "note", "body": "secret client text"},
    )
    assert res.status_code == 201

    changes = _audit_changes(db)
    assert "body" not in changes
    assert changes["internal"] is False
    assert changes["has_body"] is True


# ── PATCH /api/v1/admin/activities/{id} ────────────────────────────────

def test_admin_patch_activity_updates_body(admin_test_client, monkeypatch):
    db = _patch_admin_db(monkeypatch)

    res = admin_test_client.patch(
        "/api/v1/admin/activities/7",
        json={"body": "revised", "internal": False},
    )
    assert res.status_code == 200

    update_stmts = [(sql, args) for sql, args in db.statements if sql.strip().startswith("UPDATE activities SET")]
    assert len(update_stmts) == 1
    sql, args = update_stmts[0]
    assert "body = $1" in sql
    assert "internal = $2" in sql
    assert args[0] == "revised"
    assert args[1] is False


def test_admin_patch_activity_no_fields_is_400(admin_test_client, monkeypatch):
    _patch_admin_db(monkeypatch)

    res = admin_test_client.patch("/api/v1/admin/activities/7", json={})
    assert res.status_code == 400


def test_admin_patch_activity_not_found_is_404(admin_test_client, monkeypatch):
    class _NotFoundDB(_AdminStubDB):
        async def fetch_one(self, sql, *args):
            self.statements.append((sql, args))
            return None

    db = _NotFoundDB()
    monkeypatch.setattr(activities_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(activities_router, "fetch_all", db.fetch_all)
    monkeypatch.setattr(activities_router, "fetch_val", db.fetch_val)
    monkeypatch.setattr(activities_router, "execute", db.execute)

    res = admin_test_client.patch("/api/v1/admin/activities/404", json={"body": "x"})
    assert res.status_code == 404


# ── GET /api/v1/admin/activities/today ─────────────────────────────────

def test_admin_activities_today_query_shape(admin_test_client, monkeypatch):
    db = _patch_admin_db(monkeypatch)

    res = admin_test_client.get("/api/v1/admin/activities/today")
    assert res.status_code == 200
    assert res.json() == {"items": [], "total": 0}

    select_stmts = [sql for sql, _ in db.statements if "FROM activities" in sql and "WHERE" in sql]
    assert select_stmts, "expected the /today query to run"
    sql = select_stmts[0]
    assert "type = 'task'" in sql
    assert "completed_at IS NULL" in sql
    assert "due_at IS NOT NULL" in sql
    assert "deleted_at IS NULL" in sql


def test_admin_activities_today_route_precedes_id_route(admin_test_client, monkeypatch):
    """Regression guard: /today must resolve to the today handler, not be
    swallowed by /{activity_id} trying (and failing) to parse 'today' as
    an int -- that would 422, not 200."""
    _patch_admin_db(monkeypatch)
    res = admin_test_client.get("/api/v1/admin/activities/today")
    assert res.status_code == 200


# ── GET /api/v1/admin/activities list filters ──────────────────────────

def test_admin_list_activities_applies_subject_and_open_filters(admin_test_client, monkeypatch):
    db = _patch_admin_db(monkeypatch)

    res = admin_test_client.get(
        "/api/v1/admin/activities",
        params={"subject_type": "candidate", "subject_id": 5, "open": "true"},
    )
    assert res.status_code == 200

    select_stmts = [(sql, args) for sql, args in db.statements if "FROM activities WHERE" in sql]
    assert select_stmts, "expected a filtered SELECT against activities"
    sql, args = select_stmts[-1]
    assert "subject_type = $1" in sql
    assert "subject_id = $2" in sql
    assert "completed_at IS NULL" in sql
    assert args[0] == "candidate"
    assert args[1] == 5


def test_admin_list_activities_open_false_filters_completed(admin_test_client, monkeypatch):
    db = _patch_admin_db(monkeypatch)

    res = admin_test_client.get("/api/v1/admin/activities", params={"open": "false"})
    assert res.status_code == 200

    select_stmts = [sql for sql, _ in db.statements if "FROM activities WHERE" in sql]
    assert any("completed_at IS NOT NULL" in sql for sql in select_stmts)


def test_admin_list_activities_no_filters_still_scoped_to_not_deleted(admin_test_client, monkeypatch):
    db = _patch_admin_db(monkeypatch)

    res = admin_test_client.get("/api/v1/admin/activities")
    assert res.status_code == 200

    select_stmts = [sql for sql, _ in db.statements if "FROM activities WHERE" in sql]
    assert select_stmts
    assert all("deleted_at IS NULL" in sql for sql in select_stmts)
