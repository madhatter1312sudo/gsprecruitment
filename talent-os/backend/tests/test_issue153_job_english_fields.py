"""
Unit tests for issue #153 (Pool vacancies: English text twin, defect B of
issue #109) -- job_orders.description_en / requirements_en /
nice_to_have_en: the schema fields, the migration, and the write/read
routes that carry them.

Pure static + monkeypatched-DB tests, no real database needed -- same
style as test_ws_c15_job_orders.py (migration text checks) and
test_ws_b2_admin_jobs.py (fake fetch_one/execute for the router tests).
"""
import asyncio
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi import HTTPException

from models.schemas import (
    AdminJobCreate,
    AdminJobUpdate,
    ClientJobCreate,
    ClientJobUpdate,
    JobOrderCreate,
    JobOrderUpdate,
)
from routers.jobs import PUBLIC_JOB_COLUMNS

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(BACKEND_ROOT, "migrations")

EN_FIELDS = ("description_en", "requirements_en", "nice_to_have_en")


def _load_migration(fname):
    path = os.path.join(MIGRATIONS_DIR, fname)
    spec = importlib.util.spec_from_file_location(f"_migration_{fname}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, MIGRATIONS_DIR)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(MIGRATIONS_DIR)
    return mod


# ── Migration 046 ─────────────────────────────────────────────────────────

def test_migration_046_adds_all_three_english_columns():
    mod = _load_migration("046_job_orders_english_fields.py")
    sql = mod.MIGRATION_SQL
    for col in (
        "description_en text",
        "requirements_en text",
        "nice_to_have_en text",
    ):
        assert col in sql, f"migration SQL missing: {col}"


def test_migration_046_columns_are_add_column_if_not_exists():
    """Idempotent (re-runnable) like every other migration -- see
    040_email_log.py's docstring, and test_migration_016_columns_are_add_
    column_if_not_exists for the same check on 016."""
    mod = _load_migration("046_job_orders_english_fields.py")
    sql = mod.MIGRATION_SQL
    assert sql.count("ADD COLUMN IF NOT EXISTS") == 3


def test_migration_046_columns_are_nullable():
    """Every one of the 27 existing pool vacancies (and every other job
    order already in production) must end up with these columns NULL, not
    blocked by a NOT NULL default -- see migration docstring."""
    mod = _load_migration("046_job_orders_english_fields.py")
    sql = mod.MIGRATION_SQL.upper()
    assert "NOT NULL" not in sql
    assert "DEFAULT" not in sql


def test_migration_046_never_creates_a_unique_index_or_drops_anything():
    mod = _load_migration("046_job_orders_english_fields.py")
    sql = mod.MIGRATION_SQL.upper()
    assert "CREATE UNIQUE INDEX" not in sql
    assert "DROP" not in sql
    assert "DELETE" not in sql


def test_migration_046_only_touches_job_orders():
    mod = _load_migration("046_job_orders_english_fields.py")
    sql = mod.MIGRATION_SQL
    for stmt in (s.strip() for s in sql.split(";") if s.strip()):
        assert stmt.startswith("ALTER TABLE job_orders "), stmt


def test_migration_046_version_matches_filename():
    mod = _load_migration("046_job_orders_english_fields.py")
    assert mod.VERSION == "046_job_orders_english_fields"


# ── Schema fields ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("model_cls", [JobOrderCreate, JobOrderUpdate, ClientJobCreate, ClientJobUpdate])
def test_job_and_client_schemas_carry_all_three_english_fields(model_cls):
    for f in EN_FIELDS:
        assert f in model_cls.model_fields, f"{model_cls.__name__} missing {f}"
        assert model_cls.model_fields[f].default is None, f"{model_cls.__name__}.{f} must default to None"


@pytest.mark.parametrize("model_cls", [AdminJobCreate, AdminJobUpdate])
def test_admin_schemas_carry_description_and_requirements_english_fields(model_cls):
    for f in ("description_en", "requirements_en", "nice_to_have_en"):
        assert f in model_cls.model_fields, f"{model_cls.__name__} missing {f}"
        assert model_cls.model_fields[f].default is None


def test_job_order_create_accepts_english_fields():
    job = JobOrderCreate(
        client_id=1, title="Embedded engineer",
        description="NL tekst", description_en="EN text",
        requirements="NL eisen", requirements_en="EN requirements",
        nice_to_have="NL pre", nice_to_have_en="EN nice to have",
    )
    assert job.description_en == "EN text"
    assert job.requirements_en == "EN requirements"
    assert job.nice_to_have_en == "EN nice to have"


def test_job_order_create_defaults_english_fields_to_none():
    job = JobOrderCreate(client_id=1, title="x", description="NL only")
    assert job.description_en is None
    assert job.requirements_en is None
    assert job.nice_to_have_en is None


def test_admin_job_create_accepts_nice_to_have_and_its_english_twin():
    job = AdminJobCreate(
        client_id=1, title="x",
        nice_to_have="NL pre", nice_to_have_en="EN plus",
    )
    assert job.nice_to_have == "NL pre"
    assert job.nice_to_have_en == "EN plus"


# ── Public projection (routers/jobs.py) ─────────────────────────────────

def test_public_job_columns_includes_the_three_english_columns():
    for expected in ("j.description_en", "j.requirements_en", "j.nice_to_have_en"):
        assert expected in PUBLIC_JOB_COLUMNS


def test_public_job_columns_still_includes_the_dutch_columns():
    for expected in ("j.description", "j.requirements", "j.nice_to_have"):
        assert expected in PUBLIC_JOB_COLUMNS


# ── Router: /api/jobs (routers/jobs.py, X-API-Key) ─────────────────────

class _FakeDB:
    def __init__(self, row=None):
        self.row = row
        self.statements = []

    async def fetch_one(self, sql, *args):
        self.statements.append((sql, args))
        return self.row

    async def fetch_all(self, sql, *args):
        self.statements.append((sql, args))
        return [self.row] if self.row else []

    async def execute(self, sql, *args):
        self.statements.append((sql, args))
        return "OK"


def test_create_job_inserts_english_fields(monkeypatch):
    import routers.jobs as jobs

    row = {"id": 1, "description_en": "EN text", "requirements_en": "EN reqs", "nice_to_have_en": "EN nth"}
    db = _FakeDB(row=row)
    monkeypatch.setattr(jobs, "fetch_one", db.fetch_one)

    data = JobOrderCreate(
        client_id=1, title="Embedded engineer",
        description="NL", description_en="EN text",
        requirements="NL eisen", requirements_en="EN reqs",
        nice_to_have="NL pre", nice_to_have_en="EN nth",
    )
    result = asyncio.run(jobs.create_job(data))
    assert result == row

    insert_sql, insert_args = next((s, a) for s, a in db.statements if "INSERT INTO job_orders" in s)
    assert "description_en" in insert_sql
    assert "requirements_en" in insert_sql
    assert "nice_to_have_en" in insert_sql
    assert "EN text" in insert_args
    assert "EN reqs" in insert_args
    assert "EN nth" in insert_args


def test_update_job_allows_patching_english_fields(monkeypatch):
    import routers.jobs as jobs

    db = _FakeDB(row={"id": 1, "description_en": "New EN text"})
    monkeypatch.setattr(jobs, "fetch_one", db.fetch_one)

    updates = JobOrderUpdate(description_en="New EN text")
    result = asyncio.run(jobs.update_job(1, updates))
    assert result["description_en"] == "New EN text"

    update_sql, update_args = next((s, a) for s, a in db.statements if s.strip().startswith("UPDATE job_orders"))
    assert "description_en = $1" in update_sql
    assert "New EN text" in update_args


# ── Router: /api/v1/client/jobs (routers/client.py) ─────────────────────

def test_create_client_job_inserts_english_fields(monkeypatch):
    import routers.client as client

    db = _FakeDB(row={"id": 1, "title": "x"})

    async def _get_client(_user_id):
        return {"id": 7}

    async def _notify(*_a, **_k):
        return None

    monkeypatch.setattr(client, "fetch_one", db.fetch_one)
    monkeypatch.setattr(client, "execute", db.execute)
    monkeypatch.setattr(client, "_get_client_by_user", _get_client)
    monkeypatch.setattr(client, "notify_owner", _notify)

    data = ClientJobCreate(
        title="Embedded engineer",
        description="NL", description_en="EN text",
        requirements="NL eisen", requirements_en="EN reqs",
        nice_to_have="NL pre", nice_to_have_en="EN nth",
    )
    asyncio.run(client.create_client_job(data, current_user={"id": 1, "role": "client"}))

    insert_sql, insert_args = next((s, a) for s, a in db.statements if "INSERT INTO job_orders" in s)
    assert "description_en" in insert_sql
    assert "requirements_en" in insert_sql
    assert "nice_to_have_en" in insert_sql
    assert "EN text" in insert_args
    assert "EN reqs" in insert_args
    assert "EN nth" in insert_args


def test_update_client_job_allow_list_includes_english_fields(monkeypatch):
    import routers.client as client

    db = _FakeDB(row={"id": 3, "description_en": "Updated EN"})

    async def _get_client(_user_id):
        return {"id": 7}

    monkeypatch.setattr(client, "fetch_one", db.fetch_one)
    monkeypatch.setattr(client, "execute", db.execute)
    monkeypatch.setattr(client, "_get_client_by_user", _get_client)

    updates = ClientJobUpdate(description_en="Updated EN")
    result = asyncio.run(client.update_client_job(3, updates, current_user={"id": 1, "role": "client"}))
    assert result["description_en"] == "Updated EN"

    update_sql, update_args = next((s, a) for s, a in db.statements if s.strip().startswith("UPDATE job_orders"))
    assert "description_en = $1" in update_sql
    assert "Updated EN" in update_args

    # jsonb audit log payload must always be json.dumps()'d, never a raw dict
    audit_calls = [args for sql, args in db.statements if sql.strip().startswith("INSERT INTO audit_log")]
    assert audit_calls
    changes_arg = audit_calls[0][-1]
    assert isinstance(changes_arg, str)
    assert json.loads(changes_arg)["description_en"] == "Updated EN"


# ── Router: /api/v1/admin/jobs (routers/admin.py) ────────────────────────

class _FakeAdminDB:
    def __init__(self, job_row=None, client_exists=True):
        self.job_row = job_row
        self.client_exists = client_exists
        self.statements = []

    async def fetch_one(self, sql, *args):
        self.statements.append((sql, args))
        if sql.strip().startswith("SELECT id FROM clients WHERE"):
            return {"id": args[0]} if self.client_exists else None
        return self.job_row

    async def fetch_all(self, sql, *args):
        self.statements.append((sql, args))
        return []

    async def execute(self, sql, *args):
        self.statements.append((sql, args))
        return "OK"


def test_create_job_for_client_inserts_english_fields(monkeypatch):
    import routers.admin as admin

    db = _FakeAdminDB(job_row={"id": 10, "title": "x", "status": "draft"})
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(admin, "execute", db.execute)

    data = AdminJobCreate(
        client_id=1, title="Embedded engineer",
        description="NL", description_en="EN text",
        requirements="NL eisen", requirements_en="EN reqs",
        nice_to_have="NL pre", nice_to_have_en="EN nth",
    )
    asyncio.run(admin.create_job_for_client(data, current_user={"id": 5, "role": "admin"}))

    insert_sql, insert_args = next((s, a) for s, a in db.statements if "INSERT INTO job_orders" in s)
    assert "description_en" in insert_sql
    assert "requirements_en" in insert_sql
    assert "nice_to_have_en" in insert_sql
    assert "EN text" in insert_args
    assert "EN reqs" in insert_args
    assert "EN nth" in insert_args


def test_update_any_job_allow_list_includes_english_fields(monkeypatch):
    import routers.admin as admin

    db = _FakeAdminDB(job_row={"id": 10, "description_en": "Updated EN"})
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(admin, "execute", db.execute)

    updates = AdminJobUpdate(description_en="Updated EN")
    result = asyncio.run(admin.update_any_job(10, updates, current_user={"id": 5, "role": "admin"}))
    assert result["description_en"] == "Updated EN"

    update_sql, update_args = next((s, a) for s, a in db.statements if s.strip().startswith("UPDATE job_orders"))
    assert "description_en = $1" in update_sql
    assert "Updated EN" in update_args


# ── seed_pool_vacancies.py ────────────────────────────────────────────────

def test_seed_script_job_fields_include_english_twins():
    import scripts.seed_pool_vacancies as seed
    for f in EN_FIELDS:
        assert f in seed.JOB_FIELDS


def test_seed_script_english_fields_have_no_required_default():
    """A row that omits the new keys (every row in pool_vacancies.json
    today, per issue #153 acceptance criterion 5) must not be required --
    vac.get(f, JOB_FIELD_DEFAULTS.get(f)) already falls back to None for
    any key not in JOB_FIELD_DEFAULTS."""
    import scripts.seed_pool_vacancies as seed
    for f in EN_FIELDS:
        assert f not in seed.JOB_FIELD_DEFAULTS


def test_pool_vacancies_json_unchanged_by_this_issue():
    """Acceptance criterion 5: the 27 rows in data/pool_vacancies.json are
    untouched -- none of them carry the new English keys yet."""
    data_path = os.path.join(BACKEND_ROOT, "data", "pool_vacancies.json")
    if not os.path.exists(data_path):
        pytest.skip("data/pool_vacancies.json does not exist in this worktree")
    with open(data_path, encoding="utf-8") as fh:
        vacancies = json.load(fh)
    for v in vacancies:
        for f in EN_FIELDS:
            assert f not in v, f"{v.get('slug')}: unexpected key {f} -- issue #153 writes no English copy"
