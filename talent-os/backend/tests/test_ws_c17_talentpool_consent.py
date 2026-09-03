"""
Unit tests for WS-C.17 "opt-in talentpool": the three consent touchpoints
(candidate portal, public double-opt-in, admin-recorded) and their audit
logging. No DB/network needed -- fetch_one/fetch_all/execute are
monkeypatched to a tiny recorder/stub DB, same style as
tests/test_gdpr_erasure.py and tests/test_ws_e7_gdpr_outreach.py.
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from starlette.requests import Request

from core.security import hash_token


def _fake_request() -> Request:
    """Bare starlette Request -- slowapi's @limiter.limit decorator reads
    request.headers/request.client to key the limit, same helper as
    tests/test_ws_e4_ratelimit_lockout.py._make_request."""
    scope = {
        "type": "http", "headers": [], "client": ("9.9.9.9", 12345),
        "method": "POST", "path": "/",
    }
    return Request(scope)


# ── Candidate portal: POST /api/v1/candidate/talentpool-consent ──────────

class _CandidateDB:
    """Fakes the two queries update_talentpool_consent() issues: the
    SELECT lawful_basis lookup and the UPDATE ... RETURNING."""

    def __init__(self, lawful_basis):
        self.lawful_basis = lawful_basis
        self.updates = []
        self.audit = []

    async def fetch_one(self, sql, *args):
        if sql.strip().startswith("SELECT lawful_basis FROM candidates"):
            return {"lawful_basis": self.lawful_basis}
        if sql.strip().startswith("UPDATE candidates"):
            self.updates.append((sql, args))
            if "consent_talentpool_at = NULL" in sql:
                return {
                    "id": 42, "consent_talentpool_at": None, "consent_talentpool_until": None,
                    "consent_scope": None, "consent_source": None, "lawful_basis": self.lawful_basis,
                }
            now, until, scope, set_basis, candidate_id = args
            return {
                "id": candidate_id, "consent_talentpool_at": now, "consent_talentpool_until": until,
                "consent_scope": scope, "consent_source": "portal",
                "lawful_basis": "opt_in_talentpool" if set_basis else self.lawful_basis,
            }
        return None

    async def execute(self, sql, *args):
        self.audit.append((sql, args))
        return "OK"


@pytest.fixture()
def patch_candidate_router(monkeypatch):
    def _patch(db: _CandidateDB, candidate_id: int = 42):
        import routers.candidate as candidate_router
        monkeypatch.setattr(candidate_router, "fetch_one", db.fetch_one)
        monkeypatch.setattr(candidate_router, "execute", db.execute)

        async def _fake_candidate_id(user_id):
            return candidate_id
        monkeypatch.setattr(candidate_router, "_get_candidate_id", _fake_candidate_id)
        return candidate_router
    return _patch


def _user(role="candidate", uid=7):
    return {"id": uid, "role": role, "is_verified": True}


def test_portal_consent_sets_lawful_basis_for_portal_registratie_candidate(patch_candidate_router):
    from models.schemas import TalentpoolConsentUpdate
    db = _CandidateDB(lawful_basis="portal_registratie")
    router = patch_candidate_router(db)
    data = TalentpoolConsentUpdate(consent=True, scope="matching_and_contact")
    row = asyncio.run(router.update_talentpool_consent(data, current_user=_user()))
    assert row["lawful_basis"] == "opt_in_talentpool"
    assert row["consent_scope"] == "matching_and_contact"
    assert row["consent_talentpool_until"] is not None
    # audit_log written, JSON-serialized (never a raw dict -- commit 72b4bcd)
    audit_sql, audit_args = db.audit[0]
    assert audit_sql.strip().startswith("INSERT INTO audit_log")
    assert audit_args[0] == "talentpool_consent_update"
    payload = json.loads(audit_args[4])
    assert payload == {"consent": True, "scope": "matching_and_contact", "source": "portal"}


def test_portal_consent_never_silently_overwrites_a_different_lawful_basis(patch_candidate_router):
    """A candidate sourced via LinkedIn (gerechtvaardigd_belang) who ticks
    the portal talentpool box keeps that basis -- WS-C.17 task rule:
    lawful_basis only becomes opt_in_talentpool for a portal_registratie
    (or NULL) candidate, never silently for any other basis."""
    from models.schemas import TalentpoolConsentUpdate
    db = _CandidateDB(lawful_basis="gerechtvaardigd_belang")
    router = patch_candidate_router(db)
    data = TalentpoolConsentUpdate(consent=True, scope="matching_only")
    row = asyncio.run(router.update_talentpool_consent(data, current_user=_user()))
    assert row["lawful_basis"] == "gerechtvaardigd_belang"
    # the four consent columns are still recorded regardless
    assert row["consent_scope"] == "matching_only"
    assert row["consent_talentpool_until"] is not None


def test_portal_consent_false_clears_all_four_columns(patch_candidate_router):
    from models.schemas import TalentpoolConsentUpdate
    db = _CandidateDB(lawful_basis="opt_in_talentpool")
    router = patch_candidate_router(db)
    data = TalentpoolConsentUpdate(consent=False)
    row = asyncio.run(router.update_talentpool_consent(data, current_user=_user()))
    assert row["consent_talentpool_at"] is None
    assert row["consent_talentpool_until"] is None
    assert row["consent_scope"] is None
    assert row["consent_source"] is None


def test_portal_consent_requires_scope_when_consent_true(patch_candidate_router):
    from fastapi import HTTPException
    from models.schemas import TalentpoolConsentUpdate
    db = _CandidateDB(lawful_basis="portal_registratie")
    router = patch_candidate_router(db)
    data = TalentpoolConsentUpdate(consent=True, scope=None)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(router.update_talentpool_consent(data, current_user=_user()))
    assert exc_info.value.status_code == 422


def test_talentpool_consent_update_rejects_invalid_scope():
    from pydantic import ValidationError
    from models.schemas import TalentpoolConsentUpdate
    with pytest.raises(ValidationError):
        TalentpoolConsentUpdate(consent=True, scope="not_a_real_scope")


# ── Public: POST /api/public/talentpool-optin + /talentpool-confirm ──────

class _PublicDB:
    def __init__(self, pending_row=None, existing_candidate=None):
        self.pending_row = pending_row
        self.existing_candidate = existing_candidate
        self.executed = []
        self.inserted_token_hash = None

    async def fetch_one(self, sql, *args):
        if "FROM talentpool_optin_requests" in sql:
            return self.pending_row
        if "FROM candidates WHERE LOWER(email)" in sql:
            return self.existing_candidate
        if sql.strip().startswith("UPDATE candidates") or sql.strip().startswith("INSERT INTO candidates"):
            self.executed.append((sql, args))
            return {"id": 1, "lawful_basis": "opt_in_talentpool",
                     "consent_talentpool_at": args[-4] if "INSERT" in sql else args[0],
                     "consent_talentpool_until": args[-3] if "INSERT" in sql else args[1]}
        return None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        if "INSERT INTO talentpool_optin_requests" in sql:
            self.inserted_token_hash = args[1]
        return "OK"


@pytest.fixture()
def patch_public_router(monkeypatch):
    def _patch(db: _PublicDB, send_ok=True):
        import routers.public as public_router
        monkeypatch.setattr(public_router, "fetch_one", db.fetch_one)
        monkeypatch.setattr(public_router, "execute", db.execute)

        async def _fake_send_email(**kwargs):
            return send_ok
        monkeypatch.setattr(public_router.email_service, "send_email", _fake_send_email)
        return public_router
    return _patch


def test_talentpool_optin_with_consent_stores_only_the_token_hash(patch_public_router):
    from models.schemas import TalentpoolOptinRequest
    db = _PublicDB()
    router = patch_public_router(db)
    data = TalentpoolOptinRequest(
        email="jane@example.com", consent=True, scope="matching_only", source="kandidaten_page",
    )
    result = asyncio.run(router.talentpool_optin(request=_fake_request(), data=data))
    assert "message" in result
    insert_calls = [c for c in db.executed if "INSERT INTO talentpool_optin_requests" in c[0]]
    assert len(insert_calls) == 1
    _, args = insert_calls[0]
    email, token_hash, scope, source = args
    assert email == "jane@example.com"
    assert scope == "matching_only" and source == "kandidaten_page"
    # only a sha256 hex digest is stored, never a raw token
    assert len(token_hash) == 64
    assert all(c in "0123456789abcdef" for c in token_hash)


def test_talentpool_optin_without_consent_is_a_noop(patch_public_router):
    """No pending row, no e-mail -- consent=false has nothing to confirm."""
    from models.schemas import TalentpoolOptinRequest
    db = _PublicDB()
    router = patch_public_router(db)
    data = TalentpoolOptinRequest(
        email="jane@example.com", consent=False, scope="matching_only", source="kandidaten_page",
    )
    asyncio.run(router.talentpool_optin(request=_fake_request(), data=data))
    assert db.executed == []


def test_talentpool_confirm_rejects_invalid_or_expired_token(patch_public_router):
    from fastapi import HTTPException
    from models.schemas import TalentpoolConfirmRequest
    db = _PublicDB(pending_row=None)
    router = patch_public_router(db)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(router.talentpool_confirm(request=_fake_request(), data=TalentpoolConfirmRequest(token="bogus")))
    assert exc_info.value.status_code == 400


def test_talentpool_confirm_creates_new_candidate_with_no_source_url(patch_public_router):
    """SOP §1.5: the talentpool checkbox itself is the source -- no
    source_url required for candidates created via this channel."""
    from models.schemas import TalentpoolConfirmRequest
    pending = {"id": 1, "email": "new@example.com", "scope": "matching_and_contact", "source": "blog_cta"}
    db = _PublicDB(pending_row=pending, existing_candidate=None)
    router = patch_public_router(db)
    result = asyncio.run(router.talentpool_confirm(request=_fake_request(), data=TalentpoolConfirmRequest(token="tok")))
    assert result["consent_talentpool_until"] is not None
    insert_calls = [c for c in db.executed if c[0].strip().startswith("INSERT INTO candidates")]
    assert len(insert_calls) == 1
    sql, args = insert_calls[0]
    assert "'opt_in_talentpool'" in sql  # lawful_basis literal in the INSERT
    assert "'talentpool_optin'" in sql   # source literal
    assert "source_url" not in sql       # never set for this channel


def test_talentpool_confirm_updates_existing_candidate_preserving_other_basis(patch_public_router):
    """A candidate already sourced on a different basis who separately
    confirms the public talentpool opt-in keeps that basis (never
    silently overwritten) but still gets the consent columns recorded."""
    from models.schemas import TalentpoolConfirmRequest
    pending = {"id": 1, "email": "existing@example.com", "scope": "matching_only", "source": "kandidaten_page"}
    db = _PublicDB(
        pending_row=pending,
        existing_candidate={"id": 99, "lawful_basis": "gerechtvaardigd_belang"},
    )
    router = patch_public_router(db)
    asyncio.run(router.talentpool_confirm(request=_fake_request(), data=TalentpoolConfirmRequest(token="tok")))
    update_calls = [c for c in db.executed if c[0].strip().startswith("UPDATE candidates")]
    assert len(update_calls) == 1
    _, args = update_calls[0]
    # args: now, until, scope, source, set_lawful_basis, candidate_id
    assert args[4] is False  # set_lawful_basis=False -- existing basis untouched
    assert args[5] == 99


def test_talentpool_confirm_marks_the_pending_request_confirmed(patch_public_router):
    from models.schemas import TalentpoolConfirmRequest
    pending = {"id": 5, "email": "new2@example.com", "scope": "matching_only", "source": "kandidaten_page"}
    db = _PublicDB(pending_row=pending, existing_candidate=None)
    router = patch_public_router(db)
    asyncio.run(router.talentpool_confirm(request=_fake_request(), data=TalentpoolConfirmRequest(token="tok")))
    confirm_calls = [
        c for c in db.executed
        if c[0].strip().startswith("UPDATE talentpool_optin_requests SET confirmed_at")
    ]
    assert len(confirm_calls) == 1
    assert confirm_calls[0][1] == (5,)


# ── Admin: PATCH /api/v1/admin/candidates/{id}/talentpool-consent ────────

class _AdminDB:
    def __init__(self, candidate=None):
        self.candidate = candidate
        self.updates = []
        self.audit = []

    async def fetch_one(self, sql, *args):
        if sql.strip().startswith("SELECT id, lawful_basis FROM candidates"):
            return self.candidate
        if sql.strip().startswith("UPDATE candidates"):
            self.updates.append((sql, args))
            if "consent_talentpool_at = NULL" in sql:
                return {
                    "id": self.candidate["id"], "consent_talentpool_at": None,
                    "consent_talentpool_until": None, "consent_scope": None,
                    "consent_source": None, "lawful_basis": self.candidate["lawful_basis"],
                }
            now, until, scope, set_basis, candidate_id = args
            return {
                "id": candidate_id, "consent_talentpool_at": now, "consent_talentpool_until": until,
                "consent_scope": scope, "consent_source": "admin",
                "lawful_basis": "opt_in_talentpool" if set_basis else self.candidate["lawful_basis"],
            }
        return None

    async def execute(self, sql, *args):
        self.audit.append((sql, args))
        return "OK"


@pytest.fixture()
def patch_admin_router(monkeypatch):
    def _patch(db: _AdminDB):
        import routers.admin as admin_router
        monkeypatch.setattr(admin_router, "fetch_one", db.fetch_one)
        monkeypatch.setattr(admin_router, "execute", db.execute)
        return admin_router
    return _patch


def test_admin_talentpool_consent_requires_evidence_field():
    from pydantic import ValidationError
    from models.schemas import AdminTalentpoolConsentUpdate
    with pytest.raises(ValidationError):
        AdminTalentpoolConsentUpdate(consent=True, scope="matching_only", evidence="")


def test_admin_talentpool_consent_sets_columns_and_writes_evidence_to_audit_log(patch_admin_router):
    from models.schemas import AdminTalentpoolConsentUpdate
    db = _AdminDB(candidate={"id": 10, "lawful_basis": None})
    router = patch_admin_router(db)
    data = AdminTalentpoolConsentUpdate(
        consent=True, scope="matching_and_contact", evidence="Signed consent form on file, 2026-09-01.",
    )
    row = asyncio.run(router.admin_update_talentpool_consent(
        candidate_id=10, data=data, current_user={"id": 3, "role": "admin"},
    ))
    assert row["consent_source"] == "admin"
    assert row["lawful_basis"] == "opt_in_talentpool"
    audit_sql, audit_args = db.audit[0]
    assert audit_args[0] == "admin_talentpool_consent_update"
    payload = json.loads(audit_args[4])
    assert payload["evidence"] == "Signed consent form on file, 2026-09-01."


def test_admin_talentpool_consent_404s_for_unknown_candidate(patch_admin_router):
    from fastapi import HTTPException
    from models.schemas import AdminTalentpoolConsentUpdate
    db = _AdminDB(candidate=None)
    router = patch_admin_router(db)
    data = AdminTalentpoolConsentUpdate(consent=True, scope="matching_only", evidence="x")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(router.admin_update_talentpool_consent(
            candidate_id=999, data=data, current_user={"id": 3, "role": "admin"},
        ))
    assert exc_info.value.status_code == 404
