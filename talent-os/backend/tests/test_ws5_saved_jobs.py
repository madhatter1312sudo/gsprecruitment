"""
Unit tests for WS5 issue #137 (candidate-portal saved-vacancies list):
GET/POST/DELETE /api/v1/candidate/saved-jobs. No DB/network needed --
fetch_one/fetch_all/fetch_val/execute are monkeypatched on
routers.candidate, same style as test_ws_c17_talentpool_consent.py and
test_ws3bc_referral_alerts.py's job-alerts tests.

The anonymous-client rule (SITE-DESIGN-SPEC.md §3.7 -- "no client name
where the vacancy is anonymous") is enforced client-side off a flag the
SELECT computes from `clients.is_internal`, the same source column
routers/jobs.py's public-jobs anonymous_client projection already uses
(see test_ws4_anonymous_vacancies.py / test_ws_c15_job_orders.py, which
assert on that module's PUBLIC_JOB_COLUMNS constant the same way this
file asserts on the saved-jobs query text below -- the SELECT is inline
here rather than a shared module constant, so the assertions capture the
SQL the fake DB actually received instead of importing a constant).
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest


def _user(role="candidate", uid=7):
    return {"id": uid, "role": role, "is_verified": True}


class _SavedJobsDB:
    """Fakes fetch_val (COUNT) + fetch_all (the saved-jobs SELECT) +
    fetch_one (job-exists / already-saved checks) + execute (DELETE) that
    routers.candidate's saved-jobs endpoints issue."""

    def __init__(self, rows=None, total=0, job_exists=True, already_saved=None):
        self.rows = rows or []
        self.total = total
        self.job_exists = job_exists
        self.already_saved = already_saved  # None, or {"id": ...}
        self.calls = []
        self.deleted = []

    async def fetch_val(self, sql, *args):
        self.calls.append((sql, args))
        return self.total

    async def fetch_all(self, sql, *args):
        self.calls.append((sql, args))
        return self.rows

    async def fetch_one(self, sql, *args):
        self.calls.append((sql, args))
        if sql.strip().startswith("SELECT id FROM job_orders"):
            return {"id": args[0]} if self.job_exists else None
        if sql.strip().startswith("SELECT id FROM saved_jobs"):
            return self.already_saved
        if sql.strip().startswith("INSERT INTO saved_jobs"):
            return {"id": 501, "candidate_id": args[0], "job_id": args[1]}
        return None

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        if sql.strip().startswith("DELETE FROM saved_jobs"):
            self.deleted.append(args)
            return "DELETE 1" if self.rows or self.total else "DELETE 0"
        return "OK"


@pytest.fixture()
def patch_saved_jobs_router(monkeypatch):
    def _patch(db: _SavedJobsDB, candidate_id=42):
        import routers.candidate as candidate_router
        monkeypatch.setattr(candidate_router, "fetch_val", db.fetch_val)
        monkeypatch.setattr(candidate_router, "fetch_all", db.fetch_all)
        monkeypatch.setattr(candidate_router, "fetch_one", db.fetch_one)
        monkeypatch.setattr(candidate_router, "execute", db.execute)

        async def _fake_candidate_id(user_id):
            return candidate_id
        monkeypatch.setattr(candidate_router, "_get_candidate_id", _fake_candidate_id)
        return candidate_router
    return _patch


def _saved_job_row(**overrides):
    base = {
        "id": 1, "candidate_id": 42, "job_id": 101,
        "created_at": datetime(2026, 9, 10, tzinfo=timezone.utc),
        "job_title": "Senior C++ Engineer", "description": "", "salary_min": 70000,
        "salary_max": 95000, "salary_currency": "EUR", "location_type": "Hybrid",
        "city": "Eindhoven", "company_name": "Brainport Systems B.V.",
        "anonymous_client": False,
    }
    base.update(overrides)
    return base


# ── GET /v1/candidate/saved-jobs ──────────────────────────────────────────

def test_get_saved_jobs_refuses_a_non_candidate_role():
    from fastapi import HTTPException
    import routers.candidate as candidate_router
    with pytest.raises(HTTPException) as exc:
        asyncio.run(candidate_router.get_saved_jobs(current_user=_user(role="client")))
    assert exc.value.status_code == 403


def test_get_saved_jobs_select_projects_city_and_anonymous_client(patch_saved_jobs_router):
    """The SELECT must carry `j.city` (location) and
    `COALESCE(c.is_internal, false) AS anonymous_client` -- without
    them the frontend has no way to show a location or honor the
    anonymous-client rule at all (both were missing before WS5 #137)."""
    db = _SavedJobsDB(rows=[_saved_job_row()], total=1)
    router = patch_saved_jobs_router(db)
    asyncio.run(router.get_saved_jobs(limit=20, offset=0, current_user=_user()))

    select_calls = [c for c in db.calls if "FROM saved_jobs sj" in c[0]]
    assert len(select_calls) == 1
    sql, args = select_calls[0]
    assert "j.city" in sql
    assert "COALESCE(c.is_internal, false) AS anonymous_client" in sql
    # sourced from the JOIN'd clients row, same source column the public
    # jobs endpoint already keys its anonymous_client flag off of
    # (routers/jobs.py PUBLIC_JOB_COLUMNS).
    assert "JOIN clients c ON c.id = j.client_id" in sql
    assert args == (42, 20, 0)  # candidate_id, default limit, default offset


def test_get_saved_jobs_returns_items_total_limit_offset(patch_saved_jobs_router):
    db = _SavedJobsDB(rows=[_saved_job_row()], total=1)
    router = patch_saved_jobs_router(db)
    result = asyncio.run(router.get_saved_jobs(limit=20, offset=0, current_user=_user()))
    assert result["items"] == [_saved_job_row()]
    assert result["total"] == 1
    assert result["limit"] == 20
    assert result["offset"] == 0


def test_get_saved_jobs_marks_anonymous_client_true_only_for_the_internal_client(patch_saved_jobs_router):
    """Postgres computes the boolean (COALESCE(c.is_internal, false)),
    not this endpoint -- this proves the endpoint passes whatever the
    row says straight through for both a named and an anonymous
    (is_internal=true) client, never remapping or dropping the field."""
    rows = [
        _saved_job_row(id=1, job_id=101, anonymous_client=False, company_name="Brainport Systems B.V."),
        _saved_job_row(id=2, job_id=102, anonymous_client=True, company_name="GSP Talent Pool", city="Veldhoven"),
    ]
    db = _SavedJobsDB(rows=rows, total=2)
    router = patch_saved_jobs_router(db)
    result = asyncio.run(router.get_saved_jobs(limit=20, offset=0, current_user=_user()))
    by_job = {r["job_id"]: r for r in result["items"]}
    assert by_job[101]["anonymous_client"] is False
    assert by_job[102]["anonymous_client"] is True


def test_get_saved_jobs_returns_empty_list_when_no_candidate_row_exists(patch_saved_jobs_router):
    db = _SavedJobsDB(rows=[_saved_job_row()], total=1)
    router = patch_saved_jobs_router(db, candidate_id=None)
    result = asyncio.run(router.get_saved_jobs(limit=20, offset=0, current_user=_user()))
    assert result == {"items": [], "total": 0, "limit": 20, "offset": 0}


# ── POST /v1/candidate/saved-jobs ─────────────────────────────────────────

def test_save_job_refuses_a_non_candidate_role():
    from fastapi import HTTPException
    from models.schemas import SavedJobCreate
    import routers.candidate as candidate_router
    with pytest.raises(HTTPException) as exc:
        asyncio.run(candidate_router.save_job(
            SavedJobCreate(job_id=1), current_user=_user(role="client"),
        ))
    assert exc.value.status_code == 403


def test_save_job_404s_for_a_deleted_or_unknown_job(patch_saved_jobs_router):
    from fastapi import HTTPException
    from models.schemas import SavedJobCreate
    db = _SavedJobsDB(job_exists=False)
    router = patch_saved_jobs_router(db)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(router.save_job(SavedJobCreate(job_id=999), current_user=_user()))
    assert exc.value.status_code == 404


def test_save_job_is_idempotent_when_already_saved(patch_saved_jobs_router):
    from models.schemas import SavedJobCreate
    db = _SavedJobsDB(job_exists=True, already_saved={"id": 77})
    router = patch_saved_jobs_router(db)
    result = asyncio.run(router.save_job(SavedJobCreate(job_id=101), current_user=_user()))
    assert result == {"message": "Job already saved", "id": 77}
    insert_calls = [c for c in db.calls if c[0].strip().startswith("INSERT INTO saved_jobs")]
    assert insert_calls == []


def test_save_job_inserts_a_new_row(patch_saved_jobs_router):
    from models.schemas import SavedJobCreate
    db = _SavedJobsDB(job_exists=True, already_saved=None)
    router = patch_saved_jobs_router(db)
    result = asyncio.run(router.save_job(SavedJobCreate(job_id=101), current_user=_user()))
    assert result == {"id": 501, "candidate_id": 42, "job_id": 101}


# ── DELETE /v1/candidate/saved-jobs/{job_id} ──────────────────────────────

def test_unsave_job_refuses_a_non_candidate_role():
    from fastapi import HTTPException
    import routers.candidate as candidate_router
    with pytest.raises(HTTPException) as exc:
        asyncio.run(candidate_router.unsave_job(job_id=101, current_user=_user(role="client")))
    assert exc.value.status_code == 403


def test_unsave_job_deletes_the_row(patch_saved_jobs_router):
    db = _SavedJobsDB(rows=[_saved_job_row()], total=1)
    router = patch_saved_jobs_router(db)
    result = asyncio.run(router.unsave_job(job_id=101, current_user=_user()))
    assert result == {"message": "Job removed from saved"}
    assert db.deleted == [(42, 101)]


def test_unsave_job_404s_when_nothing_was_deleted(patch_saved_jobs_router):
    from fastapi import HTTPException
    db = _SavedJobsDB(rows=[], total=0)
    router = patch_saved_jobs_router(db)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(router.unsave_job(job_id=999, current_user=_user()))
    assert exc.value.status_code == 404
