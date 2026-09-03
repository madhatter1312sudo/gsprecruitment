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

import pytest
from pydantic import ValidationError

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
