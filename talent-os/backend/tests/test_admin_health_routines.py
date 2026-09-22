"""
Unit tests for issue #127 "Platform-side heartbeat endpoint for routine
health and credits alerting":

  1. services/scheduler.py's _tracked() wrapper + _record_routine_run()
     helper -- writes a routine_runs row on success and on failure (and
     re-raises the original exception unchanged), never on a dry-run skip.
  2. GET /api/v1/admin/health/routines and GET /api/v1/admin/health/scheduler
     -- Bearer-JWT-only (no override -> 401/403), response shape, and that
     neither response contains anything but routine names/timestamps/
     exception class names (no personal data).
  3. migrations/044_routine_runs.py -- idempotent SQL text, VERSION.

Same no-DB, no-network style as tests/test_ws_c6_activities.py: core.database's
fetch_one/fetch_all/execute/fetch_val monkeypatched to a tiny in-memory stub,
auth stubbed via app.dependency_overrides on core.deps.get_current_user.
"""
import importlib.util
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

import pytest
from fastapi.testclient import TestClient

import main as _main_module
import routers.admin as admin_router
import services.scheduler as scheduler_service
from core.deps import get_current_user as _get_current_user_dep

client = TestClient(_main_module.app)


# ── 1. services/scheduler.py: _tracked() / _record_routine_run() ────────

class _RecordingDB:
    """Records every execute() call; core.database.fetch_one/fetch_all
    are unused by _record_routine_run, so only execute needs a stub."""

    def __init__(self):
        self.calls = []

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return "INSERT 0 1"


def test_tracked_records_success_and_returns_result(monkeypatch):
    db = _RecordingDB()
    monkeypatch.setattr(scheduler_service, "execute", db.execute)

    async def ok_job():
        return {"status": "success", "drafted": 3}

    wrapped = scheduler_service._tracked("draft_outreach", ok_job)
    result = _run(wrapped())

    assert result == {"status": "success", "drafted": 3}
    assert len(db.calls) == 1
    sql, args = db.calls[0]
    assert "INSERT INTO routine_runs" in sql
    assert args == ("draft_outreach", "success", None)


def test_tracked_records_error_class_and_reraises(monkeypatch):
    db = _RecordingDB()
    monkeypatch.setattr(scheduler_service, "execute", db.execute)

    async def failing_job():
        raise ConnectionError("db unreachable")

    wrapped = scheduler_service._tracked("matching", failing_job)

    with pytest.raises(ConnectionError):
        _run(wrapped())

    assert len(db.calls) == 1
    sql, args = db.calls[0]
    assert "INSERT INTO routine_runs" in sql
    assert args == ("matching", "error", "ConnectionError")


def test_tracked_never_logs_the_exception_message_only_the_class(monkeypatch):
    """error_class must be type(exc).__name__ -- never str(exc), which
    could carry an interpolated candidate/client detail from deep inside
    a job (see migrations/044_routine_runs.py's module docstring)."""
    db = _RecordingDB()
    monkeypatch.setattr(scheduler_service, "execute", db.execute)

    async def failing_job():
        raise ValueError("candidate jane.doe@example.com had no email")

    wrapped = scheduler_service._tracked("job_alert", failing_job)
    with pytest.raises(ValueError):
        _run(wrapped())

    _, args = db.calls[0]
    assert args[2] == "ValueError"
    assert "jane.doe" not in str(args)


def test_record_routine_run_failure_does_not_raise(monkeypatch):
    """A broken DB write must never mask the job's own result -- the
    scheduler tick still has to complete."""
    async def boom(sql, *args):
        raise RuntimeError("db down")

    monkeypatch.setattr(scheduler_service, "execute", boom)

    async def ok_job():
        return {"status": "success"}

    wrapped = scheduler_service._tracked("blog_draft", ok_job)
    result = _run(wrapped())
    assert result == {"status": "success"}  # did not raise despite the DB failure


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_routine_names_cover_every_registered_job_id():
    """services/scheduler.ROUTINE_NAMES must list exactly the ids
    start_scheduler() passes to scheduler.add_job() -- read that source
    directly rather than duplicating the list a second time here."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                             "services", "scheduler.py")).read()
    start_fn = src.split("async def start_scheduler()", 1)[1]
    start_fn = start_fn.split("async def shutdown_scheduler()", 1)[0]
    import re
    ids_in_code = set(re.findall(r'id="([a-z_]+)", replace_existing=True', start_fn))
    assert ids_in_code == set(scheduler_service.ROUTINE_NAMES)


# ── 2. GET /api/v1/admin/health/routines + /health/scheduler ────────────

ADMIN_USER = {"id": 1, "email": "admin@example.com", "full_name": "Admin", "role": "admin"}


@pytest.fixture
def admin_client():
    tc = TestClient(_main_module.app)
    _main_module.app.dependency_overrides[_get_current_user_dep] = lambda: ADMIN_USER
    yield tc
    _main_module.app.dependency_overrides.pop(_get_current_user_dep, None)


def test_health_routines_requires_auth():
    res = client.get("/api/v1/admin/health/routines")
    assert res.status_code == 401


def test_health_scheduler_requires_auth():
    res = client.get("/api/v1/admin/health/scheduler")
    assert res.status_code == 401


class _RoutinesDB:
    """Two rows: one routine with a success, one with a later error, the
    rest with no rows at all (never run)."""

    async def fetch_all(self, sql, *args):
        if "status = 'success'" in sql:
            return [{"routine_name": "matching", "ran_at": datetime(2026, 9, 22, 7, 0, tzinfo=timezone.utc)}]
        if "status = 'error'" in sql:
            return [{
                "routine_name": "job_alert",
                "ran_at": datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc),
                "error_class": "ConnectionError",
            }]
        return []

    async def fetch_val(self, sql, *args):
        return True


def test_get_routine_health_lists_every_known_routine(admin_client, monkeypatch):
    db = _RoutinesDB()
    monkeypatch.setattr(admin_router, "fetch_all", db.fetch_all)

    res = admin_client.get("/api/v1/admin/health/routines")
    assert res.status_code == 200
    body = res.json()
    names = {r["name"] for r in body["routines"]}
    assert names == set(scheduler_service.ROUTINE_NAMES)

    by_name = {r["name"]: r for r in body["routines"]}
    assert by_name["matching"]["last_success_at"] is not None
    assert by_name["matching"]["last_error_at"] is None
    assert by_name["matching"]["last_error_class"] is None

    assert by_name["job_alert"]["last_error_class"] == "ConnectionError"
    assert by_name["job_alert"]["last_error_at"] is not None
    assert by_name["job_alert"]["last_success_at"] is None

    # a routine that never ran reports all-None, not an omission
    never_ran = by_name["draft_blog_post"]
    assert never_ran["last_success_at"] is None
    assert never_ran["last_error_at"] is None
    assert never_ran["last_error_class"] is None


def test_routine_health_response_has_no_personal_data_fields(admin_client, monkeypatch):
    db = _RoutinesDB()
    monkeypatch.setattr(admin_router, "fetch_all", db.fetch_all)

    res = admin_client.get("/api/v1/admin/health/routines")
    body = res.json()
    allowed_keys = {"name", "last_success_at", "last_error_at", "last_error_class"}
    for row in body["routines"]:
        assert set(row.keys()) == allowed_keys


def test_get_scheduler_health_reports_lock_and_routines(admin_client, monkeypatch):
    db = _RoutinesDB()
    monkeypatch.setattr(admin_router, "fetch_val", db.fetch_val)

    res = admin_client.get("/api/v1/admin/health/scheduler")
    assert res.status_code == 200
    body = res.json()
    assert body["running"] is True
    assert body["timezone"] == "Europe/Amsterdam"
    assert set(body["registered_routines"]) == set(scheduler_service.ROUTINE_NAMES)
    assert isinstance(body["apollo_jobs_enabled"], bool)


def test_get_scheduler_health_reports_not_running_when_lock_free(admin_client, monkeypatch):
    async def no_lock(sql, *args):
        return False

    monkeypatch.setattr(admin_router, "fetch_val", no_lock)

    res = admin_client.get("/api/v1/admin/health/scheduler")
    assert res.status_code == 200
    assert res.json()["running"] is False


# ── 3. migrations/044_routine_runs.py ────────────────────────────────────

def _load_migration(filename):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations", filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_044_version_matches_filename():
    mod = _load_migration("044_routine_runs.py")
    assert mod.VERSION == "044_routine_runs"


def test_migration_044_is_idempotent_and_has_no_destructive_statements():
    mod = _load_migration("044_routine_runs.py")
    sql = mod.MIGRATION_SQL
    assert "CREATE TABLE IF NOT EXISTS routine_runs" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql
    assert "DROP" not in sql.upper()
    assert "DELETE" not in sql.upper()
    assert "DO $$" not in sql


def test_migration_044_status_check_constraint():
    mod = _load_migration("044_routine_runs.py")
    assert "CHECK (status IN ('success', 'error'))" in mod.MIGRATION_SQL


def test_migration_044_carries_no_email_or_name_column():
    """The table must structurally hold no personal data -- checked
    against the migration text itself, not just the response shape."""
    mod = _load_migration("044_routine_runs.py")
    sql = mod.MIGRATION_SQL.lower()
    assert "email" not in sql
    assert "full_name" not in sql
