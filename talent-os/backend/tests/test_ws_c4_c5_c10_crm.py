"""
Unit tests for WS-C.4 (client_contacts), WS-C.5 (pipeline_stage_history),
and WS-C.10 (leads/interest_type + Telegram notification).

No DB/network needed: core.database's fetch_one/fetch_all/execute are
monkeypatched per-test to a tiny in-memory fake, same style as
tests/test_gdpr_erasure.py and tests/test_ws_e7_gdpr_outreach.py. httpx is
never actually called (Telegram tests assert the no-op path only).
"""
import asyncio
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
    ClientContactCreate, ClientContactUpdate, PipelineStageUpdate,
    LeadSubmit, LeadReadUpdate, LEAD_INTEREST_TYPES,
)


# ── ClientContactCreate / Update: role + lawful_basis CHECK values ───────

def test_client_contact_create_accepts_each_allowed_role():
    for role in ("hiring_manager", "finance", "tekenbevoegd", "overig"):
        c = ClientContactCreate(full_name="A Person", role=role)
        assert c.role == role


def test_client_contact_create_rejects_bad_role():
    with pytest.raises(ValidationError):
        ClientContactCreate(full_name="A Person", role="ceo")


def test_client_contact_create_accepts_each_allowed_lawful_basis():
    for basis in ("zakelijk_functioneel_adres", "opt_in", "bestaande_relatie"):
        c = ClientContactCreate(full_name="A Person", lawful_basis=basis)
        assert c.lawful_basis == basis


def test_client_contact_create_rejects_bad_lawful_basis():
    with pytest.raises(ValidationError):
        ClientContactCreate(full_name="A Person", lawful_basis="verwerkersovereenkomst")


def test_client_contact_create_defaults():
    c = ClientContactCreate(full_name="A Person")
    assert c.is_primary is False
    assert c.role is None
    assert c.lawful_basis is None


def test_client_contact_update_rejects_bad_role():
    with pytest.raises(ValidationError):
        ClientContactUpdate(role="owner")


def test_client_contact_update_all_fields_optional():
    u = ClientContactUpdate()
    assert u.model_dump(exclude_unset=True) == {}


# ── PipelineStageUpdate ────────────────────────────────────────────────

def test_pipeline_stage_update_requires_nonempty_stage():
    with pytest.raises(ValidationError):
        PipelineStageUpdate(stage="")


def test_pipeline_stage_update_accepts_stage():
    assert PipelineStageUpdate(stage="interview").stage == "interview"


# ── LeadSubmit.interest_type normalisation (mirrors migrations/026's
#    DB-level normalisation at the API boundary) ─────────────────────────

@pytest.mark.parametrize("value", LEAD_INTEREST_TYPES)
def test_lead_submit_accepts_each_allowed_interest_type(value):
    lead = LeadSubmit(name="A", email="a@example.com", message="hi", interest_type=value)
    assert lead.interest_type == value


def test_lead_submit_interest_type_none_becomes_overig():
    lead = LeadSubmit(name="A", email="a@example.com", message="hi")
    assert lead.interest_type == "overig"


def test_lead_submit_unrecognised_interest_type_becomes_overig():
    lead = LeadSubmit(name="A", email="a@example.com", message="hi", interest_type="random junk")
    assert lead.interest_type == "overig"


def test_lead_submit_blank_interest_type_becomes_overig():
    lead = LeadSubmit(name="A", email="a@example.com", message="hi", interest_type="  ")
    assert lead.interest_type == "overig"


# ── Code-review follow-up: legacy interest_type values website/contact.html
#    and website/script.js actually sent (candidate|client|partner, plus
#    the WS-A.3 staffing options uitzenden|detacheren|zzp_bemiddeling)
#    before this PR's fix must remap to their nearest canonical value, not
#    fall through to the generic "unrecognised -> overig" bucket ─────────

@pytest.mark.parametrize("legacy_value,expected", [
    ("candidate", "kandidaat"),
    ("client", "werving_selectie"),
    ("partner", "overig"),
    ("uitzenden", "detachering_internationaal"),
    ("detacheren", "detachering_internationaal"),
    ("zzp_bemiddeling", "detachering_internationaal"),
])
def test_lead_submit_remaps_legacy_interest_type(legacy_value, expected):
    lead = LeadSubmit(name="A", email="a@example.com", message="hi", interest_type=legacy_value)
    assert lead.interest_type == expected


def test_lead_read_update_requires_bool():
    with pytest.raises(ValidationError):
        LeadReadUpdate(is_read=["not", "a", "bool"])  # type: ignore[arg-type]
    assert LeadReadUpdate(is_read=True).is_read is True


# ── Migration text: 024/025/026 idempotency + CHECK values ──────────────

import importlib.util


def _load_migration(filename):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations", filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_024_client_contacts_migration_idempotent_and_checked():
    mod = _load_migration("024_client_contacts.py")
    sql = mod.MIGRATION_SQL
    assert "CREATE TABLE IF NOT EXISTS client_contacts" in sql
    assert "REFERENCES clients(id) ON DELETE CASCADE" in sql
    for value in ("hiring_manager", "finance", "tekenbevoegd", "overig"):
        assert value in sql
    for value in ("zakelijk_functioneel_adres", "opt_in", "bestaande_relatie"):
        assert value in sql
    assert "DO $$" not in sql
    assert "CREATE UNIQUE INDEX" not in sql  # no unique index that could abort on existing data


def test_025_pipeline_stage_history_migration_idempotent():
    mod = _load_migration("025_pipeline_stage_history.py")
    sql = mod.MIGRATION_SQL
    assert "CREATE TABLE IF NOT EXISTS pipeline_stage_history" in sql
    assert "REFERENCES pipeline_entries(id) ON DELETE CASCADE" in sql
    assert "DO $$" not in sql
    assert "CREATE UNIQUE INDEX" not in sql


def test_026_leads_interest_type_migration_normalises_before_check():
    mod = _load_migration("026_leads_interest_type.py")
    sql = mod.MIGRATION_SQL
    normalize_idx = sql.index("UPDATE contact_submissions SET interest_type = 'kandidaat'")
    check_idx = sql.index("ADD CONSTRAINT chk_contact_submissions_interest_type")
    assert normalize_idx < check_idx, "existing rows must be normalised before the CHECK is added"
    assert "DROP CONSTRAINT IF EXISTS chk_contact_submissions_interest_type" in sql
    for value in LEAD_INTEREST_TYPES:
        assert value in sql
    assert "quiz_submissions ADD COLUMN IF NOT EXISTS is_read" in sql
    assert "contact_submissions ADD COLUMN IF NOT EXISTS is_read" in sql
    assert "DO $$" not in sql
    assert "CREATE UNIQUE INDEX" not in sql


def test_026_leads_interest_type_migration_remaps_legacy_values_before_catchall():
    """Code-review follow-up: website/contact.html sent candidate|client|
    partner, plus the WS-A.3 staffing options uitzenden|detacheren|
    zzp_bemiddeling, before this PR's fix -- the migration must remap all
    six to their nearest canonical value (not the generic 'overig'
    catch-all) for existing rows, and every remap must run before the
    catch-all UPDATE so it isn't clobbered."""
    mod = _load_migration("026_leads_interest_type.py")
    sql = mod.MIGRATION_SQL
    candidate_idx = sql.index("UPDATE contact_submissions SET interest_type = 'kandidaat' WHERE interest_type = 'candidate'")
    client_idx = sql.index("UPDATE contact_submissions SET interest_type = 'werving_selectie' WHERE interest_type = 'client'")
    staffing_idx = sql.index(
        "UPDATE contact_submissions SET interest_type = 'detachering_internationaal'\n"
        "WHERE interest_type IN ('uitzenden', 'detacheren', 'zzp_bemiddeling')"
    )
    catchall_idx = sql.index("WHERE interest_type = 'partner'")
    assert candidate_idx < catchall_idx
    assert client_idx < catchall_idx
    assert staffing_idx < catchall_idx


# ── services/telegram.py: no-op without env vars, never raises ──────────

def test_telegram_notify_lead_noops_without_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    from services import telegram

    assert telegram.is_configured() is False
    result = asyncio.run(telegram.notify_lead("kandidaat"))
    assert result is False


def test_telegram_message_never_carries_name_or_email(monkeypatch):
    """Regression guard: notify_lead's signature only accepts
    interest_type + a timestamp -- it has no name/email parameter to leak
    in the first place."""
    from services import telegram
    import inspect

    sig = inspect.signature(telegram.notify_lead)
    assert set(sig.parameters) == {"interest_type", "submitted_at"}


def test_telegram_send_posts_to_api_when_configured(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    from services import telegram

    calls = []

    class _FakeResponse:
        def raise_for_status(self):
            pass

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, data=None):
            calls.append((url, data))
            return _FakeResponse()

    monkeypatch.setattr(telegram.httpx, "AsyncClient", _FakeAsyncClient)

    result = asyncio.run(telegram.notify_lead("werving_selectie"))
    assert result is True
    assert len(calls) == 1
    url, data = calls[0]
    assert "test-token" in url
    assert data["chat_id"] == "12345"
    assert "werving_selectie" in data["text"]


# ── Scoping: client_contacts portal read is scoped to the caller's own
#    client (WS-C.4) ──────────────────────────────────────────────────────

class _FakeDB:
    def __init__(self, client_row=None, contact_rows=None):
        self.client_row = client_row
        self.contact_rows = contact_rows or []
        self.statements = []

    async def fetch_one(self, sql, *args):
        self.statements.append((sql, args))
        if "FROM clients c JOIN user_clients uc" in sql:
            return self.client_row
        return None

    async def fetch_all(self, sql, *args):
        self.statements.append((sql, args))
        if "FROM client_contacts" in sql:
            return self.contact_rows
        return []

    async def execute(self, sql, *args):
        self.statements.append((sql, args))
        return "OK"


def test_client_portal_contacts_scoped_to_own_client(monkeypatch):
    import routers.client_contacts as client_contacts

    db = _FakeDB(
        client_row={"id": 7},
        contact_rows=[{"id": 1, "client_id": 7, "full_name": "Jane"}],
    )
    monkeypatch.setattr(client_contacts, "fetch_one", db.fetch_one)
    monkeypatch.setattr(client_contacts, "fetch_all", db.fetch_all)

    result = asyncio.run(
        client_contacts.list_own_client_contacts(current_user={"id": 42, "role": "client"})
    )
    assert result["total"] == 1
    assert result["items"][0]["client_id"] == 7

    # Every fetch_all for contacts must have been scoped by the resolved
    # client id (7), taken from user_clients, never from request input.
    contact_calls = [args for sql, args in db.statements if "FROM client_contacts" in sql]
    assert contact_calls == [(7,)]


def test_client_portal_contacts_empty_when_no_client_profile(monkeypatch):
    """A client user with no linked clients row (e.g. never finished
    onboarding) gets an empty list, not another client's contacts and not
    a 500."""
    import routers.client_contacts as client_contacts

    db = _FakeDB(client_row=None)
    monkeypatch.setattr(client_contacts, "fetch_one", db.fetch_one)
    monkeypatch.setattr(client_contacts, "fetch_all", db.fetch_all)

    result = asyncio.run(
        client_contacts.list_own_client_contacts(current_user={"id": 99, "role": "client"})
    )
    assert result == {"items": [], "total": 0}


# ── Scoping: pipeline stage history/update — a client cannot reach
#    another client's pipeline entry (WS-C.5) ─────────────────────────────

class _FakePipelineDB:
    """entry_client_id models the pipeline_entries.client_id the entry
    actually belongs to; the client-portal endpoints must 404 (not leak
    the entry) whenever the caller's own resolved client id differs."""

    def __init__(self, caller_client_id, entry_client_id, entry_id=55, current_stage="sourced"):
        self.caller_client_id = caller_client_id
        self.entry_client_id = entry_client_id
        self.entry_id = entry_id
        self.current_stage = current_stage
        self.history_inserts = []

    async def fetch_one(self, sql, *args):
        if "FROM clients c" in sql and "user_clients uc" in sql:
            return {"id": self.caller_client_id} if self.caller_client_id else None
        if "FROM pipeline_entries WHERE id = $1 AND client_id = $2" in sql:
            entry_id, client_id = args
            if entry_id == self.entry_id and client_id == self.entry_client_id:
                return {"id": self.entry_id, "stage": self.current_stage}
            return None
        if sql.startswith("UPDATE pipeline_entries SET stage"):
            return {"id": self.entry_id, "stage": args[0]}
        return None

    async def fetch_all(self, sql, *args):
        return []

    async def execute(self, sql, *args):
        if "pipeline_stage_history" in sql:
            self.history_inserts.append(args)
        return "OK"


def test_client_cannot_read_another_clients_pipeline_history(monkeypatch):
    import routers.client as client_router
    from fastapi import HTTPException

    # Caller belongs to client 1, but the entry belongs to client 2.
    db = _FakePipelineDB(caller_client_id=1, entry_client_id=2)
    monkeypatch.setattr(client_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(client_router, "fetch_all", db.fetch_all)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            client_router.get_pipeline_stage_history(
                entry_id=55, current_user={"id": 1, "role": "client", "approved_by_admin_at": "2026-01-01"}
            )
        )
    assert exc_info.value.status_code == 404


def test_client_cannot_update_another_clients_pipeline_stage(monkeypatch):
    import routers.client as client_router
    from fastapi import HTTPException
    from models.schemas import PipelineStageUpdate

    db = _FakePipelineDB(caller_client_id=1, entry_client_id=2)
    monkeypatch.setattr(client_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(client_router, "execute", db.execute)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            client_router.update_pipeline_stage(
                entry_id=55,
                data=PipelineStageUpdate(stage="interview"),
                current_user={"id": 1, "role": "client", "approved_by_admin_at": "2026-01-01"},
            )
        )
    assert exc_info.value.status_code == 404
    assert db.history_inserts == []  # nothing recorded for a rejected update


def test_client_can_update_own_pipeline_stage_and_records_history(monkeypatch):
    import routers.client as client_router
    from models.schemas import PipelineStageUpdate

    db = _FakePipelineDB(caller_client_id=1, entry_client_id=1, current_stage="sourced")
    monkeypatch.setattr(client_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(client_router, "execute", db.execute)

    result = asyncio.run(
        client_router.update_pipeline_stage(
            entry_id=55,
            data=PipelineStageUpdate(stage="interview"),
            current_user={"id": 1, "role": "client", "approved_by_admin_at": "2026-01-01"},
        )
    )
    assert result["stage"] == "interview"
    assert len(db.history_inserts) == 1
    entry_id, from_stage, to_stage, changed_by = db.history_inserts[0]
    assert (entry_id, from_stage, to_stage, changed_by) == (55, "sourced", "interview", 1)


def test_no_history_row_recorded_when_stage_unchanged(monkeypatch):
    import routers.client as client_router
    from models.schemas import PipelineStageUpdate

    db = _FakePipelineDB(caller_client_id=1, entry_client_id=1, current_stage="interview")
    monkeypatch.setattr(client_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(client_router, "execute", db.execute)

    asyncio.run(
        client_router.update_pipeline_stage(
            entry_id=55,
            data=PipelineStageUpdate(stage="interview"),
            current_user={"id": 1, "role": "client", "approved_by_admin_at": "2026-01-01"},
        )
    )
    assert db.history_inserts == []


# ── admin.py leads endpoint: unknown source is rejected, never used to
#    build a table name past the allow-list ──────────────────────────────

def test_update_lead_read_state_rejects_unknown_source(monkeypatch):
    import routers.admin as admin_router
    from fastapi import HTTPException
    from models.schemas import LeadReadUpdate

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            admin_router.update_lead_read_state(
                source="users",  # not contact_submissions/quiz_submissions
                lead_id=1,
                data=LeadReadUpdate(is_read=True),
                current_user={"id": 1, "role": "admin"},
            )
        )
    assert exc_info.value.status_code == 404


def test_list_leads_rejects_invalid_type(monkeypatch):
    import routers.admin as admin_router
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            admin_router.list_leads(
                type="not_a_real_type", unread=None, limit=50, offset=0,
                current_user={"id": 1, "role": "admin"},
            )
        )
    assert exc_info.value.status_code == 400


# ── Client-portal contacts write side (issue #141): POST/PATCH/DELETE
#    /api/v1/client/contacts[/{contact_id}] -- TestClient + stubbed auth +
#    stubbed DB, same style as tests/test_ws_c6_activities.py's
#    client-portal scoping section. ──────────────────────────────────────

import main as _main_module  # noqa: E402
from core.deps import get_verified_user as _get_verified_user_dep  # noqa: E402
import routers.client_contacts as client_contacts_router  # noqa: E402

CONTACT_CLIENT_USER = {
    "id": 42,
    "email": "client@example.com",
    "full_name": "A Client User",
    "role": "client",
    "is_verified": True,
    "approved_by_admin_at": "2026-01-01T00:00:00Z",
}


@pytest.fixture
def contact_test_client():
    tc = TestClient(_main_module.app)
    yield tc
    _main_module.app.dependency_overrides.pop(_get_verified_user_dep, None)


def _override_as_contact_client_user():
    _main_module.app.dependency_overrides[_get_verified_user_dep] = lambda: CONTACT_CLIENT_USER


class _ContactStubDB:
    """Tiny in-memory stub for core.database's fetch_one/fetch_all/execute,
    keyed by a substring of the SQL -- same recording style as
    tests/test_gdpr_erasure.py's _FakeDB and test_ws_c6_activities.py's
    _StubDB. `own_contact_ids` models the contacts that really belong to
    `client_id`; any id outside that set 404s."""

    def __init__(self, client_id=7, own_contact_ids=(1,)):
        self.client_id = client_id
        self.own_contact_ids = set(own_contact_ids)
        self.statements = []
        self._next_id = 100

    async def fetch_one(self, sql, *args):
        self.statements.append((sql, args))
        if "FROM clients c JOIN user_clients uc" in sql:
            return {"id": self.client_id} if self.client_id is not None else None
        if sql.strip().startswith("SELECT id FROM client_contacts"):
            contact_id, client_id = args[0], args[1]
            if contact_id in self.own_contact_ids and client_id == self.client_id:
                return {"id": contact_id}
            return None
        if sql.strip().startswith("INSERT INTO client_contacts"):
            row_id = self._next_id
            self._next_id += 1
            self.own_contact_ids.add(row_id)
            return {
                "id": row_id, "client_id": args[0], "full_name": args[1],
                "email": args[2], "phone": args[3], "role": args[4],
                "is_primary": args[5], "lawful_basis": args[6],
                "created_at": "2026-09-22T00:00:00Z", "updated_at": None,
            }
        if sql.strip().startswith("UPDATE client_contacts SET") and "RETURNING *" in sql:
            *values, contact_id, client_id = args
            if contact_id not in self.own_contact_ids or client_id != self.client_id:
                return None
            return {
                "id": contact_id, "client_id": client_id, "full_name": "Updated Name",
                "email": None, "phone": None, "role": None, "is_primary": False,
                "lawful_basis": None, "created_at": "2026-09-22T00:00:00Z",
                "updated_at": "2026-09-22T01:00:00Z",
            }
        if "UPDATE client_contacts SET deleted_at" in sql:
            contact_id, client_id = args[0], args[1]
            if contact_id in self.own_contact_ids and client_id == self.client_id:
                self.own_contact_ids.discard(contact_id)
                return {"id": contact_id}
            return None
        return None

    async def fetch_all(self, sql, *args):
        self.statements.append((sql, args))
        return []

    async def execute(self, sql, *args):
        self.statements.append((sql, args))
        return "OK"


def _patch_contact_db(monkeypatch, **kwargs):
    db = _ContactStubDB(**kwargs)
    monkeypatch.setattr(client_contacts_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(client_contacts_router, "fetch_all", db.fetch_all)
    monkeypatch.setattr(client_contacts_router, "execute", db.execute)
    return db


def test_client_create_contact_succeeds_and_is_audited(contact_test_client, monkeypatch):
    _override_as_contact_client_user()
    db = _patch_contact_db(monkeypatch, client_id=7)

    res = contact_test_client.post(
        "/api/v1/client/contacts",
        json={"full_name": "Jane Doe", "role": "hiring_manager", "email": "jane@example.com"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["client_id"] == 7
    assert body["full_name"] == "Jane Doe"

    audit_calls = [args for sql, args in db.statements if sql.strip().startswith("INSERT INTO audit_log")]
    assert len(audit_calls) == 1
    assert audit_calls[0][2] == "client_contact"  # target_type
    assert audit_calls[0][0] == "client_contact_create"  # action
    # changes column must be a JSON string, never a raw dict (commit 72b4bcd).
    assert isinstance(audit_calls[0][4], str)


def test_client_create_contact_without_client_profile_is_404(contact_test_client, monkeypatch):
    _override_as_contact_client_user()
    _patch_contact_db(monkeypatch, client_id=None)

    res = contact_test_client.post(
        "/api/v1/client/contacts",
        json={"full_name": "Jane Doe"},
    )
    assert res.status_code == 404


def test_client_create_contact_rejects_bad_role_422(contact_test_client, monkeypatch):
    _override_as_contact_client_user()
    _patch_contact_db(monkeypatch, client_id=7)

    res = contact_test_client.post(
        "/api/v1/client/contacts",
        json={"full_name": "Jane Doe", "role": "ceo"},
    )
    assert res.status_code == 422


def test_client_create_contact_unauthenticated_is_401(contact_test_client):
    res = contact_test_client.post(
        "/api/v1/client/contacts",
        json={"full_name": "Jane Doe"},
    )
    assert res.status_code == 401


def test_client_edit_own_contact_succeeds_and_is_audited(contact_test_client, monkeypatch):
    _override_as_contact_client_user()
    db = _patch_contact_db(monkeypatch, client_id=7, own_contact_ids=(1,))

    res = contact_test_client.patch(
        "/api/v1/client/contacts/1",
        json={"full_name": "Updated Name"},
    )
    assert res.status_code == 200
    assert res.json()["full_name"] == "Updated Name"

    audit_calls = [args for sql, args in db.statements if sql.strip().startswith("INSERT INTO audit_log")]
    assert len(audit_calls) == 1
    assert audit_calls[0][0] == "client_contact_update"
    assert isinstance(audit_calls[0][4], str)


def test_client_edit_another_clients_contact_is_404_not_403(contact_test_client, monkeypatch):
    """A contact belonging to another client must 404, never a 403 that
    would confirm the contact exists (WS-C.4 scoping rule)."""
    _override_as_contact_client_user()
    _patch_contact_db(monkeypatch, client_id=7, own_contact_ids=(1,))

    res = contact_test_client.patch(
        "/api/v1/client/contacts/999",
        json={"full_name": "Someone Else"},
    )
    assert res.status_code == 404


def test_client_edit_contact_rejects_bad_role_422(contact_test_client, monkeypatch):
    _override_as_contact_client_user()
    _patch_contact_db(monkeypatch, client_id=7, own_contact_ids=(1,))

    res = contact_test_client.patch(
        "/api/v1/client/contacts/1",
        json={"role": "owner"},
    )
    assert res.status_code == 422


def test_client_edit_contact_unauthenticated_is_401(contact_test_client):
    res = contact_test_client.patch(
        "/api/v1/client/contacts/1",
        json={"full_name": "Someone"},
    )
    assert res.status_code == 401


def test_client_edit_contact_without_client_profile_is_404(contact_test_client, monkeypatch):
    _override_as_contact_client_user()
    _patch_contact_db(monkeypatch, client_id=None)

    res = contact_test_client.patch(
        "/api/v1/client/contacts/1",
        json={"full_name": "Someone"},
    )
    assert res.status_code == 404


def test_client_edit_contact_empty_body_is_400(contact_test_client, monkeypatch):
    _override_as_contact_client_user()
    _patch_contact_db(monkeypatch, client_id=7, own_contact_ids=(1,))

    res = contact_test_client.patch("/api/v1/client/contacts/1", json={})
    assert res.status_code == 400


def test_client_edit_contact_ignores_extra_client_id_field(contact_test_client, monkeypatch):
    """ClientContactUpdate has no client_id field -- an extra `client_id`
    key in the body is dropped by validation, never reaching the SQL
    UPDATE (the row stays scoped to the caller's own resolved client)."""
    _override_as_contact_client_user()
    db = _patch_contact_db(monkeypatch, client_id=7, own_contact_ids=(1,))

    res = contact_test_client.patch(
        "/api/v1/client/contacts/1",
        json={"full_name": "Updated Name", "client_id": 999},
    )
    assert res.status_code == 200

    update_calls = [args for sql, args in db.statements if sql.strip().startswith("UPDATE client_contacts SET") and "RETURNING *" in sql]
    assert len(update_calls) == 1
    # Only full_name (+ updated_at) was bound, client_id=999 never entered
    # the SET clause or the scoping WHERE.
    assert update_calls[0][0] == "Updated Name"
    assert update_calls[0][-1] == 7  # scoping client_id is still the caller's own (7)


def test_client_delete_own_contact_succeeds_and_is_audited(contact_test_client, monkeypatch):
    _override_as_contact_client_user()
    db = _patch_contact_db(monkeypatch, client_id=7, own_contact_ids=(1,))

    res = contact_test_client.delete("/api/v1/client/contacts/1")
    assert res.status_code == 204

    audit_calls = [args for sql, args in db.statements if sql.strip().startswith("INSERT INTO audit_log")]
    assert len(audit_calls) == 1
    assert audit_calls[0][0] == "client_contact_delete"
    assert isinstance(audit_calls[0][4], str)


def test_client_delete_another_clients_contact_is_404_not_403(contact_test_client, monkeypatch):
    _override_as_contact_client_user()
    _patch_contact_db(monkeypatch, client_id=7, own_contact_ids=(1,))

    res = contact_test_client.delete("/api/v1/client/contacts/999")
    assert res.status_code == 404


def test_client_delete_contact_without_client_profile_is_404(contact_test_client, monkeypatch):
    _override_as_contact_client_user()
    _patch_contact_db(monkeypatch, client_id=None)

    res = contact_test_client.delete("/api/v1/client/contacts/1")
    assert res.status_code == 404


def test_client_delete_contact_unauthenticated_is_401(contact_test_client):
    res = contact_test_client.delete("/api/v1/client/contacts/1")
    assert res.status_code == 401
