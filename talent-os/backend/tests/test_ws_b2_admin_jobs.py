"""
Unit tests for WS-B.2 (admin job management: POST/DELETE/list filters on
routers/admin.py).

No DB/network needed: core.database's fetch_one/fetch_all/fetch_val/execute
are monkeypatched per-test to a tiny in-memory fake, same style as
tests/test_ws_c7_placements.py.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from models.schemas import AdminJobCreate


# ── AdminJobCreate model ───────────────────────────────────────────────

def test_admin_job_create_defaults_to_draft_status():
    job = AdminJobCreate(client_id=1, title="Embedded engineer")
    assert job.status == "draft"
    assert job.sponsorship_possible is False


def test_admin_job_create_rejects_bad_employment_type():
    with pytest.raises(ValidationError):
        AdminJobCreate(client_id=1, title="x", employment_type="freelance")


def test_admin_job_create_requires_title():
    with pytest.raises(ValidationError):
        AdminJobCreate(client_id=1, title="")


# ── Router: create/delete/list, monkeypatched DB ──────────────────────────

class _FakeDB:
    def __init__(self, job_row=None, client_exists=True, delete_row=None):
        self.job_row = job_row
        self.client_exists = client_exists
        self.delete_row = delete_row
        self.statements = []

    async def fetch_one(self, sql, *args):
        self.statements.append((sql, args))
        if sql.strip().startswith("SELECT id FROM clients WHERE"):
            return {"id": args[0]} if self.client_exists else None
        if "INSERT INTO job_orders" in sql:
            return self.job_row
        if sql.strip().startswith("UPDATE job_orders SET deleted_at"):
            return self.delete_row
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


def _job_row(**overrides):
    base = {
        "id": 10, "client_id": 1, "title": "Embedded engineer",
        "status": "draft", "created_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_create_job_for_client_writes_json_serialized_audit_log(monkeypatch):
    import routers.admin as admin

    db = _FakeDB(job_row=_job_row())
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(admin, "fetch_all", db.fetch_all)
    monkeypatch.setattr(admin, "execute", db.execute)

    payload = AdminJobCreate(client_id=1, title="Embedded engineer")
    result = asyncio.run(admin.create_job_for_client(payload, current_user={"id": 5, "role": "admin"}))

    assert result["id"] == 10
    audit_calls = [args for sql, args in db.statements if sql.strip().startswith("INSERT INTO audit_log")]
    assert audit_calls, "expected an audit_log insert"
    changes_arg = audit_calls[0][-1]
    assert isinstance(changes_arg, str)  # json.dumps()'d, never a raw dict
    assert json.loads(changes_arg)["status"] == "draft"


def test_create_job_for_client_validates_client_exists(monkeypatch):
    import routers.admin as admin

    db = _FakeDB(job_row=_job_row(), client_exists=False)
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(admin, "fetch_all", db.fetch_all)
    monkeypatch.setattr(admin, "execute", db.execute)

    payload = AdminJobCreate(client_id=999, title="Embedded engineer")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(admin.create_job_for_client(payload, current_user={"id": 5, "role": "admin"}))
    assert exc_info.value.status_code == 422
    assert "client_id" in exc_info.value.detail

    # never reaches the INSERT once client validation fails
    assert not any("INSERT INTO job_orders" in sql for sql, _ in db.statements)


def test_delete_job_soft_deletes_and_audit_logs(monkeypatch):
    import routers.admin as admin

    db = _FakeDB(delete_row={"id": 10, "title": "Embedded engineer"})
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(admin, "fetch_all", db.fetch_all)
    monkeypatch.setattr(admin, "execute", db.execute)

    result = asyncio.run(admin.delete_job(10, current_user={"id": 5, "role": "admin"}))
    assert "deleted" in result["message"]
    audit_calls = [args for sql, args in db.statements if sql.strip().startswith("INSERT INTO audit_log")]
    assert audit_calls
    assert json.loads(audit_calls[0][-1])["deleted"] is True


def test_delete_job_404_when_missing(monkeypatch):
    """A job that doesn't exist (or is already deleted) is a 404, never a
    silently-succeeding no-op -- the admin panel's delete button must be
    able to tell the difference (WS-B.2)."""
    import routers.admin as admin

    db = _FakeDB(delete_row=None)
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(admin, "fetch_all", db.fetch_all)
    monkeypatch.setattr(admin, "execute", db.execute)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(admin.delete_job(999, current_user={"id": 5, "role": "admin"}))
    assert exc_info.value.status_code == 404

    # no audit_log write on a failed delete
    assert not any(sql.strip().startswith("INSERT INTO audit_log") for sql, _ in db.statements)


def test_list_all_jobs_page_param_computes_offset(monkeypatch):
    """page=3&limit=20 must query offset=40, not fall back to offset=0."""
    import routers.admin as admin

    class _CountFakeDB(_FakeDB):
        async def fetch_val(self, sql, *args):
            self.statements.append((sql, args))
            return 137

    db = _CountFakeDB()
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(admin, "fetch_all", db.fetch_all)
    monkeypatch.setattr(admin, "fetch_val", db.fetch_val)
    monkeypatch.setattr(admin, "execute", db.execute)

    result = asyncio.run(admin.list_all_jobs(
        status=None, client_id=None, search=None, include_demo=False,
        limit=20, offset=0, page=3, current_user={"id": 5, "role": "admin"},
    ))
    assert result["offset"] == 40
    assert result["total"] == 137

    select_calls = [args for sql, args in db.statements if "FROM job_orders j" in sql and "SELECT j.*" in sql]
    assert select_calls
    # last two bound params are LIMIT, OFFSET
    assert select_calls[0][-2:] == (20, 40)


def test_list_all_jobs_search_filters_by_title_or_company(monkeypatch):
    import routers.admin as admin

    db = _FakeDB()
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(admin, "fetch_all", db.fetch_all)
    monkeypatch.setattr(admin, "fetch_val", db.fetch_val)
    monkeypatch.setattr(admin, "execute", db.execute)

    asyncio.run(admin.list_all_jobs(
        status=None, client_id=None, search="embedded", include_demo=False,
        limit=50, offset=0, page=None, current_user={"id": 5, "role": "admin"},
    ))

    count_calls = [args for sql, args in db.statements if sql.strip().startswith("SELECT COUNT(*)")]
    assert count_calls
    assert any("%embedded%" in str(a) for a in count_calls[0])
