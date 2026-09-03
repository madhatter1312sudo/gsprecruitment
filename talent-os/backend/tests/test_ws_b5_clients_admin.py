"""
Unit tests for WS-B.5 (admin clients list/detail endpoint follow-up).

No DB/network needed: core.database's fetch_one/fetch_all/fetch_val/execute
are monkeypatched per-test to a tiny in-memory fake, same style as
tests/test_ws_c4_c5_c10_crm.py / tests/test_gdpr_erasure.py.
"""
import asyncio
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from pydantic import ValidationError

from fastapi import HTTPException

from models.schemas import ClientAdminUpdate
import routers.clients_admin as clients_admin


ADMIN_USER = {"id": 1, "role": "admin"}


# ── ClientAdminUpdate: erkend_referent CHECK values ──────────────────────

def test_client_admin_update_accepts_each_allowed_erkend_referent():
    for value in ("ja", "nee", "onbekend"):
        u = ClientAdminUpdate(erkend_referent=value)
        assert u.erkend_referent == value


def test_client_admin_update_rejects_bad_erkend_referent():
    with pytest.raises(ValidationError):
        ClientAdminUpdate(erkend_referent="misschien")


def test_client_admin_update_all_fields_optional():
    u = ClientAdminUpdate()
    assert u.model_dump(exclude_unset=True) == {}


# ── _escape_like: search input can't smuggle wildcards ───────────────────

def test_escape_like_escapes_percent_and_underscore_and_backslash():
    assert clients_admin._escape_like("50%_off\\") == "50\\%\\_off\\\\"


def test_escape_like_leaves_plain_text_untouched():
    assert clients_admin._escape_like("Acme BV") == "Acme BV"


# ── list_clients: erkend_referent filter validated against the allow-list

def test_list_clients_rejects_invalid_erkend_referent_filter():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            clients_admin.list_clients(
                search=None, erkend_referent="maybe", page=1, limit=50,
                current_user=ADMIN_USER,
            )
        )
    assert exc_info.value.status_code == 400


# ── list_clients: one query, search parameterised + escaped, LATERAL joins
#    supply open_job_count/primary_contact with no per-row extra query ────

class _FakeListDB:
    def __init__(self, total=0, rows=None):
        self.total = total
        self.rows = rows or []
        self.fetch_val_calls = []
        self.fetch_all_calls = []

    async def fetch_val(self, sql, *args):
        self.fetch_val_calls.append((sql, args))
        return self.total

    async def fetch_all(self, sql, *args):
        self.fetch_all_calls.append((sql, args))
        return self.rows

    async def fetch_one(self, sql, *args):
        return None

    async def execute(self, sql, *args):
        return "OK"


def test_list_clients_search_is_parameterised_and_escaped(monkeypatch):
    db = _FakeListDB(total=0, rows=[])
    monkeypatch.setattr(clients_admin, "fetch_val", db.fetch_val)
    monkeypatch.setattr(clients_admin, "fetch_all", db.fetch_all)

    asyncio.run(
        clients_admin.list_clients(
            search="50%_acme", erkend_referent=None, page=1, limit=50,
            current_user=ADMIN_USER,
        )
    )

    # Search term must travel as a bound parameter (never string-interpolated
    # into the SQL text) and must be escaped so % / _ in the input can't act
    # as wildcards.
    count_sql, count_args = db.fetch_val_calls[0]
    assert "50%_acme" not in count_sql
    assert count_args == ("%50\\%\\_acme%",)
    assert "ESCAPE '\\'" in count_sql

    list_sql, list_args = db.fetch_all_calls[0]
    assert "LEFT JOIN LATERAL" in list_sql
    assert list_args[0] == "%50\\%\\_acme%"


def test_list_clients_uses_single_query_with_lateral_joins_no_n_plus_1(monkeypatch):
    rows = [
        {
            "id": 1, "company_name": "Acme BV", "domain": "acme.nl",
            "industry": "Manufacturing", "erkend_referent": "ja",
            "created_at": "2026-01-01T00:00:00Z", "open_job_count": 3,
            "full_name": "Jane Doe", "email": "jane@acme.nl", "role": "hiring_manager",
        },
        {
            "id": 2, "company_name": "Beta NV", "domain": None,
            "industry": None, "erkend_referent": "onbekend",
            "created_at": "2026-01-02T00:00:00Z", "open_job_count": 0,
            "full_name": None, "email": None, "role": None,
        },
    ]
    db = _FakeListDB(total=2, rows=rows)
    monkeypatch.setattr(clients_admin, "fetch_val", db.fetch_val)
    monkeypatch.setattr(clients_admin, "fetch_all", db.fetch_all)

    result = asyncio.run(
        clients_admin.list_clients(
            search=None, erkend_referent=None, page=1, limit=50,
            current_user=ADMIN_USER,
        )
    )

    # Exactly one fetch_all call fetched every row's data -- no per-row
    # follow-up query (the N+1 this endpoint replaces).
    assert len(db.fetch_all_calls) == 1
    assert result["total"] == 2
    assert result["items"][0]["primary_contact"] == {
        "full_name": "Jane Doe", "email": "jane@acme.nl", "role": "hiring_manager",
    }
    assert result["items"][1]["primary_contact"] is None
    assert result["items"][1]["open_job_count"] == 0


def test_list_clients_pagination_offset(monkeypatch):
    db = _FakeListDB(total=0, rows=[])
    monkeypatch.setattr(clients_admin, "fetch_val", db.fetch_val)
    monkeypatch.setattr(clients_admin, "fetch_all", db.fetch_all)

    asyncio.run(
        clients_admin.list_clients(
            search=None, erkend_referent=None, page=3, limit=20,
            current_user=ADMIN_USER,
        )
    )
    _, list_args = db.fetch_all_calls[0]
    # LIMIT, OFFSET are the trailing two bound params -- page 3 * limit 20
    # -> offset 40.
    assert list_args[-2:] == (20, 40)


# ── get_client_detail: 404 on missing/soft-deleted, contacts attached ────

class _FakeDetailDB:
    def __init__(self, client_row=None, contact_rows=None):
        self.client_row = client_row
        self.contact_rows = contact_rows or []

    async def fetch_one(self, sql, *args):
        return self.client_row

    async def fetch_all(self, sql, *args):
        return self.contact_rows

    async def execute(self, sql, *args):
        return "OK"


def test_get_client_detail_404_when_missing(monkeypatch):
    db = _FakeDetailDB(client_row=None)
    monkeypatch.setattr(clients_admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(clients_admin, "fetch_all", db.fetch_all)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(clients_admin.get_client_detail(client_id=999, current_user=ADMIN_USER))
    assert exc_info.value.status_code == 404


def test_get_client_detail_attaches_contacts(monkeypatch):
    db = _FakeDetailDB(
        client_row={
            "id": 1, "company_name": "Acme BV", "domain": "acme.nl",
            "industry": "Manufacturing", "location": "Eindhoven",
            "erkend_referent": "ja", "notes": "Key account",
            "created_at": "2026-01-01T00:00:00Z", "updated_at": None,
            "open_job_count": 2,
        },
        contact_rows=[{"id": 10, "client_id": 1, "full_name": "Jane Doe"}],
    )
    monkeypatch.setattr(clients_admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(clients_admin, "fetch_all", db.fetch_all)

    result = asyncio.run(clients_admin.get_client_detail(client_id=1, current_user=ADMIN_USER))
    assert result["contacts"] == [{"id": 10, "client_id": 1, "full_name": "Jane Doe"}]
    assert result["open_job_count"] == 2


# ── update_client: allow-listed fields, audit log JSON-serialised ────────

class _FakeUpdateDB:
    def __init__(self, exists=True, updated_row=None):
        self.exists = exists
        self.updated_row = updated_row
        self.audit_calls = []

    async def fetch_one(self, sql, *args):
        if sql.startswith("SELECT id FROM clients"):
            return {"id": args[0]} if self.exists else None
        if sql.startswith("UPDATE clients"):
            return self.updated_row
        return None

    async def fetch_all(self, sql, *args):
        return []

    async def execute(self, sql, *args):
        if "audit_log" in sql:
            self.audit_calls.append(args)
        return "OK"


def test_update_client_404_when_missing(monkeypatch):
    db = _FakeUpdateDB(exists=False)
    monkeypatch.setattr(clients_admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(clients_admin, "execute", db.execute)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            clients_admin.update_client(
                client_id=1, updates=ClientAdminUpdate(company_name="New Name"),
                current_user=ADMIN_USER,
            )
        )
    assert exc_info.value.status_code == 404


def test_update_client_400_when_no_fields(monkeypatch):
    db = _FakeUpdateDB(exists=True)
    monkeypatch.setattr(clients_admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(clients_admin, "execute", db.execute)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            clients_admin.update_client(
                client_id=1, updates=ClientAdminUpdate(), current_user=ADMIN_USER,
            )
        )
    assert exc_info.value.status_code == 400


def test_update_client_writes_json_serialised_audit_log(monkeypatch):
    updated_row = {
        "id": 1, "company_name": "Acme BV", "domain": "acme.nl",
        "industry": "Manufacturing", "erkend_referent": "ja",
        "notes": None, "updated_at": "2026-09-03T00:00:00Z",
    }
    db = _FakeUpdateDB(exists=True, updated_row=updated_row)
    monkeypatch.setattr(clients_admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(clients_admin, "execute", db.execute)

    result = asyncio.run(
        clients_admin.update_client(
            client_id=1,
            updates=ClientAdminUpdate(erkend_referent="ja"),
            current_user=ADMIN_USER,
        )
    )
    assert result == updated_row
    assert len(db.audit_calls) == 1
    action, actor_id, target_type, target_id, changes_json = db.audit_calls[0]
    assert action == "client_update"
    assert actor_id == ADMIN_USER["id"]
    assert target_type == "client"
    assert target_id == 1
    # Must be a JSON *string* (raw dicts have crashed the audit log before,
    # see commit 72b4bcd) -- json.loads must round-trip it.
    import json
    assert isinstance(changes_json, str)
    assert json.loads(changes_json) == {"erkend_referent": "ja"}


# ── Migration text: 031 idempotency + CHECK values ────────────────────────

def _load_migration(filename):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations", filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_031_clients_erkend_referent_migration_idempotent_and_checked():
    mod = _load_migration("031_clients_erkend_referent.py")
    sql = mod.MIGRATION_SQL
    assert "ALTER TABLE clients ADD COLUMN IF NOT EXISTS erkend_referent" in sql
    assert "ALTER TABLE clients ADD COLUMN IF NOT EXISTS notes" in sql
    for value in ("ja", "nee", "onbekend"):
        assert value in sql
    assert "DEFAULT 'onbekend'" in sql
    assert "DO $$" not in sql
    assert "CREATE UNIQUE INDEX" not in sql


def test_031_migration_version_matches_filename():
    mod = _load_migration("031_clients_erkend_referent.py")
    assert mod.VERSION == "031_clients_erkend_referent"
