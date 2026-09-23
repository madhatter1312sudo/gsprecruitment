"""
Talent OS — spec-presentatietoestemming, schrijfpad (§6 punt 10,
docs/VERWERKINGSREGISTER.md). Modelled directly on
tests/test_ws_c17_talentpool_consent.py's admin-endpoint section.

Two things this file exists to protect:
1. PATCH /api/v1/admin/candidates/{id}/spec-presentation-consent
   (routers/admin.py admin_update_spec_presentation_consent) behaves as
   designed: admin-only, mandatory `evidence`, mandatory `job_id` when
   granting, refuses a withdrawn/deleted candidate, writes a JSON-encoded
   audit_log row with redacted evidence, and supports withdrawal.
2. The structural brake this task explicitly asked for: `allowed_fields`
   in routers/candidates.py's PATCH /api/candidates/{id} (the endpoint
   behind the shared X-API-Key the external routines use) must never
   include `consent_spec_presentation_at` or
   `consent_spec_presentation_job_id`. That PATCH is reachable by any
   holder of the API key, not just a human admin -- if either column were
   ever added to that allow-list, a routine could record (or silently
   clear) spec-presentation consent on a candidate's behalf, with no
   evidence and no audit_log row. This is a regression test for a
   specific mistake, not a behavioural test of the endpoint, so it reads
   the source directly (ast) rather than calling the route.
"""
import ast
import asyncio
import json
import os

import pytest

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES_ROUTER_PATH = os.path.join(BACKEND_ROOT, "routers", "candidates.py")

_FORBIDDEN_FIELDS = {"consent_spec_presentation_at", "consent_spec_presentation_job_id"}


def _find_allowed_fields_literal(tree):
    """Find the `allowed_fields = {...}` set literal inside
    update_candidate() and return its string elements."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "allowed_fields"
            and isinstance(node.value, ast.Set)
        ):
            return {
                elt.value for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            }
    raise AssertionError(
        "routers/candidates.py: could not find an `allowed_fields = {...}` "
        "set literal to check -- did update_candidate() get rewritten?"
    )


def test_candidates_patch_allowed_fields_never_includes_spec_presentation_consent():
    """The structural brake this task requires: PATCH /api/candidates/{id}
    (shared X-API-Key, used by the external routines) must never be able
    to set or clear consent_spec_presentation_at /
    consent_spec_presentation_job_id -- only the admin-JWT-gated
    PATCH /api/v1/admin/candidates/{id}/spec-presentation-consent may."""
    with open(CANDIDATES_ROUTER_PATH, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=CANDIDATES_ROUTER_PATH)
    allowed = _find_allowed_fields_literal(tree)
    leaked = allowed & _FORBIDDEN_FIELDS
    assert not leaked, (
        f"routers/candidates.py's allowed_fields set must never include "
        f"{leaked} -- that field belongs only behind admin-JWT "
        f"PATCH /api/v1/admin/candidates/{{id}}/spec-presentation-consent "
        f"(routers/admin.py), never behind the shared X-API-Key."
    )


# ── Admin: PATCH /api/v1/admin/candidates/{id}/spec-presentation-consent ──

class _AdminDB:
    def __init__(self, candidate=None, job=None):
        self.candidate = candidate
        self.job = job
        self.updates = []
        self.audit = []

    async def fetch_one(self, sql, *args):
        stripped = sql.strip()
        if stripped.startswith("SELECT id, consent_withdrawn_at FROM candidates"):
            return self.candidate
        if stripped.startswith("SELECT id FROM job_orders"):
            return self.job
        if stripped.startswith("UPDATE candidates"):
            self.updates.append((sql, args))
            if "consent_spec_presentation_at = NULL" in sql:
                (candidate_id,) = args
                return {
                    "id": candidate_id, "consent_spec_presentation_at": None,
                    "consent_spec_presentation_job_id": None,
                }
            job_id, candidate_id = args
            return {
                "id": candidate_id, "consent_spec_presentation_at": "2026-09-08T00:00:00Z",
                "consent_spec_presentation_job_id": job_id,
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


def test_spec_presentation_consent_requires_evidence_field():
    from pydantic import ValidationError
    from models.schemas import AdminSpecPresentationConsentUpdate
    with pytest.raises(ValidationError):
        AdminSpecPresentationConsentUpdate(consent=True, job_id=1, evidence="")


def test_spec_presentation_consent_requires_job_id_when_granting():
    from pydantic import ValidationError
    from models.schemas import AdminSpecPresentationConsentUpdate
    with pytest.raises(ValidationError):
        AdminSpecPresentationConsentUpdate(consent=True, evidence="Signed form on file.")


def test_spec_presentation_consent_does_not_require_job_id_when_withdrawing():
    from models.schemas import AdminSpecPresentationConsentUpdate
    data = AdminSpecPresentationConsentUpdate(consent=False, evidence="Candidate withdrew consent by e-mail.")
    assert data.job_id is None


def test_admin_spec_presentation_consent_sets_columns_and_writes_evidence_to_audit_log(patch_admin_router):
    from models.schemas import AdminSpecPresentationConsentUpdate
    db = _AdminDB(candidate={"id": 10, "consent_withdrawn_at": None}, job={"id": 42})
    router = patch_admin_router(db)
    data = AdminSpecPresentationConsentUpdate(
        consent=True, job_id=42, evidence="Ondertekend formulier ontvangen, 2026-09-08.",
    )
    row = asyncio.run(router.admin_update_spec_presentation_consent(
        candidate_id=10, data=data, current_user={"id": 3, "role": "admin"},
    ))
    assert row["consent_spec_presentation_job_id"] == 42
    assert row["consent_spec_presentation_at"] is not None
    audit_sql, audit_args = db.audit[0]
    assert audit_args[0] == "admin_spec_presentation_consent_update"
    payload = json.loads(audit_args[4])
    assert payload["consent"] is True
    assert payload["job_id"] == 42
    assert payload["evidence"] == "Ondertekend formulier ontvangen, 2026-09-08."


def test_admin_spec_presentation_consent_evidence_is_redacted_before_audit_log(patch_admin_router):
    from models.schemas import AdminSpecPresentationConsentUpdate
    db = _AdminDB(candidate={"id": 13, "consent_withdrawn_at": None}, job={"id": 7})
    router = patch_admin_router(db)
    data = AdminSpecPresentationConsentUpdate(
        consent=True, job_id=7,
        evidence="Toestemming ontvangen van jane.doe@example.com op 2026-09-08.",
    )
    asyncio.run(router.admin_update_spec_presentation_consent(
        candidate_id=13, data=data, current_user={"id": 3, "role": "admin"},
    ))
    audit_sql, audit_args = db.audit[0]
    payload = json.loads(audit_args[4])
    assert "jane.doe@example.com" not in payload["evidence"]
    assert "[redacted:" in payload["evidence"]


def test_admin_spec_presentation_consent_404s_for_unknown_candidate(patch_admin_router):
    from fastapi import HTTPException
    from models.schemas import AdminSpecPresentationConsentUpdate
    db = _AdminDB(candidate=None, job={"id": 42})
    router = patch_admin_router(db)
    data = AdminSpecPresentationConsentUpdate(consent=True, job_id=42, evidence="x")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(router.admin_update_spec_presentation_consent(
            candidate_id=999, data=data, current_user={"id": 3, "role": "admin"},
        ))
    assert exc_info.value.status_code == 404


def test_admin_spec_presentation_consent_refuses_withdrawn_candidate(patch_admin_router):
    """The task's explicit requirement: refuse for a candidate with
    consent_withdrawn_at set."""
    from fastapi import HTTPException
    from models.schemas import AdminSpecPresentationConsentUpdate
    db = _AdminDB(candidate={"id": 14, "consent_withdrawn_at": "2026-08-01T00:00:00Z"}, job={"id": 42})
    router = patch_admin_router(db)
    data = AdminSpecPresentationConsentUpdate(consent=True, job_id=42, evidence="Signed form.")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(router.admin_update_spec_presentation_consent(
            candidate_id=14, data=data, current_user={"id": 3, "role": "admin"},
        ))
    assert exc_info.value.status_code == 409
    assert len(db.updates) == 0


def test_admin_spec_presentation_consent_refuses_unknown_job(patch_admin_router):
    from fastapi import HTTPException
    from models.schemas import AdminSpecPresentationConsentUpdate
    db = _AdminDB(candidate={"id": 15, "consent_withdrawn_at": None}, job=None)
    router = patch_admin_router(db)
    data = AdminSpecPresentationConsentUpdate(consent=True, job_id=999, evidence="Signed form.")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(router.admin_update_spec_presentation_consent(
            candidate_id=15, data=data, current_user={"id": 3, "role": "admin"},
        ))
    assert exc_info.value.status_code == 422
    assert len(db.updates) == 0


def test_admin_spec_presentation_consent_withdrawal_clears_both_columns(patch_admin_router):
    from models.schemas import AdminSpecPresentationConsentUpdate
    db = _AdminDB(candidate={"id": 16, "consent_withdrawn_at": None}, job=None)
    router = patch_admin_router(db)
    data = AdminSpecPresentationConsentUpdate(consent=False, evidence="Kandidaat trok toestemming in per e-mail.")
    row = asyncio.run(router.admin_update_spec_presentation_consent(
        candidate_id=16, data=data, current_user={"id": 3, "role": "admin"},
    ))
    assert row["consent_spec_presentation_at"] is None
    assert row["consent_spec_presentation_job_id"] is None
    update_sql, update_args = db.updates[0]
    assert "consent_spec_presentation_at = NULL" in update_sql
    assert "consent_spec_presentation_job_id = NULL" in update_sql
    audit_sql, audit_args = db.audit[0]
    payload = json.loads(audit_args[4])
    assert payload["consent"] is False
    assert payload["job_id"] is None
