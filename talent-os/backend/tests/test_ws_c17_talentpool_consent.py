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


def _fake_request(ip: str = "9.9.9.9") -> Request:
    """Bare starlette Request -- slowapi's @limiter.limit decorator reads
    request.headers/request.client to key the limit, same helper as
    tests/test_ws_e4_ratelimit_lockout.py._make_request. `ip` is
    overridable (WS-4 tests use their own) so every module-level test
    sharing the default "9.9.9.9" doesn't collide against
    talentpool_optin's 5/minute limit purely from test-suite volume."""
    scope = {
        "type": "http", "headers": [], "client": (ip, 12345),
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
                withdraw, candidate_id = args
                return {
                    "id": candidate_id, "consent_talentpool_at": None, "consent_talentpool_until": None,
                    "consent_scope": None, "consent_source": None, "lawful_basis": self.lawful_basis,
                    "consent_withdrawn_at": "2026-09-04T00:00:00Z" if withdraw else None,
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


def test_portal_consent_never_flips_portal_registratie_lawful_basis(patch_candidate_router):
    """Security-audit fix H3a: a portal_registratie candidate's basis is
    their own portal registration (Art. 13) -- ticking the talentpool
    checkbox NEVER flips it to opt_in_talentpool, it just adds the four
    consent columns alongside the unchanged basis."""
    from models.schemas import TalentpoolConsentUpdate
    db = _CandidateDB(lawful_basis="portal_registratie")
    router = patch_candidate_router(db)
    data = TalentpoolConsentUpdate(consent=True, scope="matching_and_contact")
    row = asyncio.run(router.update_talentpool_consent(data, current_user=_user()))
    assert row["lawful_basis"] == "portal_registratie"
    assert row["consent_scope"] == "matching_and_contact"
    assert row["consent_talentpool_until"] is not None
    # audit_log written, JSON-serialized (never a raw dict -- commit 72b4bcd)
    audit_sql, audit_args = db.audit[0]
    assert audit_sql.strip().startswith("INSERT INTO audit_log")
    assert audit_args[0] == "talentpool_consent_update"
    payload = json.loads(audit_args[4])
    assert payload == {"consent": True, "scope": "matching_and_contact", "source": "portal"}


def test_portal_consent_sets_lawful_basis_when_currently_null(patch_candidate_router):
    """The shared should_set_talentpool_lawful_basis() rule still flips a
    NULL basis -- this is the one case besides an already-opt_in_talentpool
    candidate where the flip happens."""
    from models.schemas import TalentpoolConsentUpdate
    db = _CandidateDB(lawful_basis=None)
    router = patch_candidate_router(db)
    data = TalentpoolConsentUpdate(consent=True, scope="matching_only")
    row = asyncio.run(router.update_talentpool_consent(data, current_user=_user()))
    assert row["lawful_basis"] == "opt_in_talentpool"


def test_portal_consent_never_silently_overwrites_a_different_lawful_basis(patch_candidate_router):
    """A candidate sourced via LinkedIn (gerechtvaardigd_belang) who ticks
    the portal talentpool box keeps that basis -- the flip only ever
    happens from NULL or an already-opt_in_talentpool basis."""
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


def test_portal_consent_false_stamps_withdrawn_at_when_basis_was_talentpool_only(patch_candidate_router):
    """M1: withdrawing consent that WAS the candidate's only lawful_basis
    also stamps consent_withdrawn_at -- the permanent "never contact
    again" signal, stronger than a merely-NULL consent_talentpool_until."""
    from models.schemas import TalentpoolConsentUpdate
    db = _CandidateDB(lawful_basis="opt_in_talentpool")
    router = patch_candidate_router(db)
    data = TalentpoolConsentUpdate(consent=False)
    asyncio.run(router.update_talentpool_consent(data, current_user=_user()))
    update_sql, update_args = db.updates[0]
    assert "consent_withdrawn_at" in update_sql
    withdraw_flag, candidate_id = update_args
    assert withdraw_flag is True


def test_portal_consent_false_does_not_stamp_withdrawn_at_for_portal_registratie(patch_candidate_router):
    """A portal_registratie candidate withdrawing their talentpool
    preference keeps using the portal on their existing basis --
    consent_withdrawn_at (a much stronger, permanent signal) is not
    stamped just because they un-ticked one checkbox."""
    from models.schemas import TalentpoolConsentUpdate
    db = _CandidateDB(lawful_basis="portal_registratie")
    router = patch_candidate_router(db)
    data = TalentpoolConsentUpdate(consent=False)
    asyncio.run(router.update_talentpool_consent(data, current_user=_user()))
    update_sql, update_args = db.updates[0]
    withdraw_flag, candidate_id = update_args
    assert withdraw_flag is False


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


# ── Candidate portal: GET /api/v1/candidate/profile carries consent ──────
# follow-up: the profile GET (candidate_profiles + users) now also merges
# in the four consent_talentpool_* columns from the linked `candidates`
# row (_attach_talentpool_consent), so the portal checkbox can reflect
# current state on load instead of always starting unchecked.

class _ProfileDB:
    def __init__(self, profile_row, candidate_id, consent_row):
        self.profile_row = profile_row
        self.candidate_id = candidate_id
        self.consent_row = consent_row

    async def fetch_one(self, sql, *args):
        if "FROM candidate_profiles cp" in sql:
            return dict(self.profile_row)
        if sql.strip().startswith("SELECT consent_talentpool_at"):
            assert args == (self.candidate_id,)
            return dict(self.consent_row) if self.consent_row else None
        return None

    async def execute(self, sql, *args):
        return "OK"


@pytest.fixture()
def patch_profile_router(monkeypatch):
    def _patch(db: _ProfileDB):
        import routers.candidate as candidate_router
        monkeypatch.setattr(candidate_router, "fetch_one", db.fetch_one)
        monkeypatch.setattr(candidate_router, "execute", db.execute)

        async def _fake_candidate_id(user_id):
            return db.candidate_id
        monkeypatch.setattr(candidate_router, "_get_candidate_id", _fake_candidate_id)
        return candidate_router
    return _patch


def _profile_row(**overrides):
    base = {
        "id": 1, "user_id": 7, "email": "jane@example.com", "full_name": "Jane Doe",
        "phone": None, "linkedin_url": None, "github_url": None, "portfolio_url": None,
        "current_company": None, "current_title": None, "location": None,
        "willing_to_relocate": False, "salary_expectation_min": None, "salary_expectation_max": None,
        "notice_period_days": None, "years_experience": None, "skills": [], "languages": [],
        "education": None, "cv_text": None, "cv_file_path": None,
        "created_at": datetime.now(timezone.utc), "updated_at": None,
    }
    base.update(overrides)
    return base


def test_profile_get_reflects_active_talentpool_consent(patch_profile_router):
    until = datetime.now(timezone.utc) + timedelta(days=30)
    db = _ProfileDB(
        profile_row=_profile_row(), candidate_id=42,
        consent_row={
            "consent_talentpool_at": datetime.now(timezone.utc) - timedelta(days=1),
            "consent_talentpool_until": until, "consent_scope": "matching_and_contact",
            "consent_source": "portal",
        },
    )
    router = patch_profile_router(db)
    result = asyncio.run(router.get_candidate_profile(current_user=_user()))
    assert result["consent_talentpool_until"] == until
    assert result["consent_scope"] == "matching_and_contact"
    assert result["consent_source"] == "portal"


def test_profile_get_has_no_consent_when_no_candidates_row_exists(patch_profile_router):
    db = _ProfileDB(profile_row=_profile_row(), candidate_id=None, consent_row=None)
    router = patch_profile_router(db)
    result = asyncio.run(router.get_candidate_profile(current_user=_user()))
    assert result["consent_talentpool_at"] is None
    assert result["consent_talentpool_until"] is None
    assert result["consent_scope"] is None
    assert result["consent_source"] is None


def test_profile_get_has_no_consent_when_never_recorded(patch_profile_router):
    db = _ProfileDB(profile_row=_profile_row(), candidate_id=42, consent_row=None)
    router = patch_profile_router(db)
    result = asyncio.run(router.get_candidate_profile(current_user=_user()))
    assert result["consent_talentpool_until"] is None


# ── Public: POST /api/public/talentpool-optin + /talentpool-confirm ──────

class _PublicDB:
    def __init__(self, pending_row=None, existing_candidate=None, suppressed=False,
                 recent_pending=False, job_row=None):
        self.pending_row = pending_row
        self.existing_candidate = existing_candidate
        self.suppressed = suppressed
        self.recent_pending = recent_pending
        # WS-4 (migrations/037): the job_orders lookup used both by
        # talentpool_optin() (validating an incoming job_id) and
        # talentpool_confirm() (re-checking it's still open at confirm
        # time) -- a dict with at least {"id", "title"}, or None to
        # simulate "no such open/non-demo/non-deleted job".
        self.job_row = job_row
        self.executed = []
        self.inserted_token_hash = None

    async def fetch_one(self, sql, *args):
        if "FROM suppression_list" in sql:
            return {"1": 1} if self.suppressed else None
        if "FROM talentpool_optin_requests" in sql and "LOWER(email)" in sql:
            # L1 recent-unconfirmed-request guard (talentpool_optin())
            return {"id": 999} if self.recent_pending else None
        if "FROM talentpool_optin_requests" in sql:
            # talentpool_confirm()'s token lookup
            return self.pending_row
        if "FROM job_orders" in sql:
            # WS-4: job_id validation (optin) / re-check (confirm)
            return self.job_row
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
    email, token_hash, scope, source, job_id, job_alerts = args
    assert email == "jane@example.com"
    assert scope == "matching_only" and source == "kandidaten_page"
    # no job_id/job_alerts given -- WS-4 fields default to "not linked"
    assert job_id is None
    assert job_alerts is False
    # only a sha256 hex digest is stored, never a raw token
    assert len(token_hash) == 64
    assert all(c in "0123456789abcdef" for c in token_hash)


# ── WS-4 (migrations/037): job_id / job_alerts on the talentpool opt-in ──

def test_talentpool_optin_with_valid_job_id_stores_it_and_names_the_job_in_the_email(monkeypatch):
    from models.schemas import TalentpoolOptinRequest
    import routers.public as public_router

    db = _PublicDB(job_row={"id": 55, "title": "Senior Embedded C++ Engineer"})
    monkeypatch.setattr(public_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(public_router, "execute", db.execute)

    sent = []

    async def _fake_send_email(**kwargs):
        sent.append(kwargs)
        return True
    monkeypatch.setattr(public_router.email_service, "send_email", _fake_send_email)

    data = TalentpoolOptinRequest(
        email="applicant@example.com", consent=True, scope="matching_only",
        source="vacancy_apply", job_id=55, job_alerts=True,
    )
    asyncio.run(public_router.talentpool_optin(request=_fake_request(ip="9.9.9.10"), data=data))
    insert_calls = [c for c in db.executed if "INSERT INTO talentpool_optin_requests" in c[0]]
    _, args = insert_calls[0]
    email, token_hash, scope, source, job_id, job_alerts = args
    assert job_id == 55
    assert job_alerts is True
    assert source == "vacancy_apply"
    assert len(sent) == 1
    assert "Senior Embedded C++ Engineer" in sent[0]["body_text"]


def test_talentpool_optin_with_unknown_job_id_stores_no_job_id(patch_public_router):
    """An id that doesn't resolve to an open/non-demo/non-deleted job is
    silently ignored -- the row is still created, just without a job_id,
    same no-enumeration posture as the rest of this endpoint."""
    from models.schemas import TalentpoolOptinRequest
    db = _PublicDB(job_row=None)  # simulates closed/demo/deleted/unknown job_id
    router = patch_public_router(db)
    data = TalentpoolOptinRequest(
        email="applicant@example.com", consent=True, scope="matching_only",
        source="vacancy_apply", job_id=999999,
    )
    result = asyncio.run(router.talentpool_optin(request=_fake_request(ip="9.9.9.11"), data=data))
    assert "message" in result  # same generic 202 body
    insert_calls = [c for c in db.executed if "INSERT INTO talentpool_optin_requests" in c[0]]
    _, args = insert_calls[0]
    email, token_hash, scope, source, job_id, job_alerts = args
    assert job_id is None


def test_talentpool_optin_source_accepts_vacancy_apply():
    from models.schemas import TalentpoolOptinRequest
    req = TalentpoolOptinRequest(
        email="a@example.com", consent=True, scope="matching_only", source="vacancy_apply",
    )
    assert req.source == "vacancy_apply"


def test_talentpool_optin_source_still_rejects_an_unknown_value():
    from pydantic import ValidationError
    from models.schemas import TalentpoolOptinRequest
    with pytest.raises(ValidationError):
        TalentpoolOptinRequest(
            email="a@example.com", consent=True, scope="matching_only", source="not_a_real_source",
        )


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


def test_talentpool_optin_skips_sending_when_email_is_suppressed(patch_public_router):
    """L1: an address on suppression_list (STOP received) never gets a
    fresh confirmation e-mail on any basis -- but the response is
    unchanged (202, same generic message) so this can't be used to probe
    who is suppressed."""
    from models.schemas import TalentpoolOptinRequest
    db = _PublicDB(suppressed=True)
    router = patch_public_router(db)
    data = TalentpoolOptinRequest(
        email="stopped@example.com", consent=True, scope="matching_only", source="kandidaten_page",
    )
    result = asyncio.run(router.talentpool_optin(request=_fake_request(), data=data))
    assert "message" in result
    assert db.executed == []


def test_talentpool_optin_skips_sending_when_a_recent_unconfirmed_request_exists(patch_public_router):
    """L1: repeated submits within 10 minutes don't each mint a fresh
    token + e-mail -- still returns the same 202/message."""
    from models.schemas import TalentpoolOptinRequest
    db = _PublicDB(recent_pending=True)
    router = patch_public_router(db)
    data = TalentpoolOptinRequest(
        email="jane@example.com", consent=True, scope="matching_only", source="kandidaten_page",
    )
    result = asyncio.run(router.talentpool_optin(request=_fake_request(), data=data))
    assert "message" in result
    assert db.executed == []


class _StatefulOptinDB:
    """Chief-of-staff FIX FIRST regression: unlike _PublicDB's canned
    `recent_pending` flag, this fake actually implements the guard's SQL
    semantics (a per-(email, job_id) lookup against previously inserted
    rows) so the (email, job_id) key change can be proven end to end
    instead of just exercised query-string-first."""

    def __init__(self, job_rows=None):
        self.job_rows = job_rows or {}  # job_id -> {"id", "title"}
        self.rows = []  # inserted talentpool_optin_requests rows

    async def fetch_one(self, sql, *args):
        if "FROM suppression_list" in sql:
            return None
        if "FROM job_orders" in sql:
            return self.job_rows.get(args[0])
        if "FROM talentpool_optin_requests" in sql and "LOWER(email)" in sql:
            email, job_id = args
            for row in self.rows:
                if row["email"] == email and row["job_id"] == job_id and not row["confirmed"]:
                    return {"id": row["id"]}
            return None
        return None

    async def execute(self, sql, *args):
        if "INSERT INTO talentpool_optin_requests" in sql:
            email, token_hash, scope, source, job_id, job_alerts = args
            self.rows.append({"id": len(self.rows) + 1, "email": email, "job_id": job_id, "confirmed": False})
        return "OK"


def test_talentpool_optin_second_role_within_ten_minutes_gets_its_own_row(monkeypatch):
    """Chief-of-staff FIX FIRST: the repeated-click guard used to key
    only on e-mail, so a candidate applying to a second role shortly
    after the first (e.g. the junior/medior/senior variants of the same
    title) got the same generic 202 back but no second row, no second
    job_id and no confirmation e-mail -- the application looked accepted
    and silently wasn't. The guard now keys on (email, job_id): a
    different job_id is a different application and gets its own row and
    e-mail, while a genuine repeat click on the SAME job is still
    deduped."""
    from models.schemas import TalentpoolOptinRequest
    import routers.public as public_router

    db = _StatefulOptinDB(job_rows={
        55: {"id": 55, "title": "RTOS-software engineer (junior)"},
        56: {"id": 56, "title": "RTOS-software engineer (medior)"},
    })
    monkeypatch.setattr(public_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(public_router, "execute", db.execute)

    sent = []

    async def _fake_send_email(**kwargs):
        sent.append(kwargs)
        return True
    monkeypatch.setattr(public_router.email_service, "send_email", _fake_send_email)

    data1 = TalentpoolOptinRequest(
        email="dubbel@example.com", consent=True, scope="matching_only",
        source="vacancy_apply", job_id=55,
    )
    data2 = TalentpoolOptinRequest(
        email="dubbel@example.com", consent=True, scope="matching_only",
        source="vacancy_apply", job_id=56,
    )
    asyncio.run(public_router.talentpool_optin(request=_fake_request(ip="9.9.9.20"), data=data1))
    asyncio.run(public_router.talentpool_optin(request=_fake_request(ip="9.9.9.20"), data=data2))

    assert len(db.rows) == 2
    assert {r["job_id"] for r in db.rows} == {55, 56}
    assert len(sent) == 2

    # A genuine repeat submit for the SAME job within ten minutes is
    # still deduped -- the guard isn't disabled, only correctly scoped.
    data3 = TalentpoolOptinRequest(
        email="dubbel@example.com", consent=True, scope="matching_only",
        source="vacancy_apply", job_id=55,
    )
    asyncio.run(public_router.talentpool_optin(request=_fake_request(ip="9.9.9.20"), data=data3))
    assert len(db.rows) == 2
    assert len(sent) == 2


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
    pending = {"id": 1, "email": "new@example.com", "scope": "matching_and_contact",
               "source": "blog_cta", "job_id": None}
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
    pending = {"id": 1, "email": "existing@example.com", "scope": "matching_only",
               "source": "kandidaten_page", "job_id": None}
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


def test_talentpool_confirm_never_flips_portal_registratie_lawful_basis(patch_public_router):
    """H3a via the shared helper: a portal_registratie candidate who
    separately confirms the public talentpool opt-in keeps that basis --
    same rule as the portal endpoint, not just 'any other basis'."""
    from models.schemas import TalentpoolConfirmRequest
    pending = {"id": 2, "email": "portal@example.com", "scope": "matching_only",
               "source": "kandidaten_page", "job_id": None}
    db = _PublicDB(
        pending_row=pending,
        existing_candidate={"id": 100, "lawful_basis": "portal_registratie"},
    )
    router = patch_public_router(db)
    asyncio.run(router.talentpool_confirm(request=_fake_request(), data=TalentpoolConfirmRequest(token="tok")))
    update_calls = [c for c in db.executed if c[0].strip().startswith("UPDATE candidates")]
    assert len(update_calls) == 1
    _, args = update_calls[0]
    assert args[4] is False  # set_lawful_basis=False -- portal_registratie untouched


def test_talentpool_confirm_marks_the_pending_request_confirmed(patch_public_router):
    from models.schemas import TalentpoolConfirmRequest
    pending = {"id": 5, "email": "new2@example.com", "scope": "matching_only",
               "source": "kandidaten_page", "job_id": None}
    db = _PublicDB(pending_row=pending, existing_candidate=None)
    router = patch_public_router(db)
    asyncio.run(router.talentpool_confirm(request=_fake_request(), data=TalentpoolConfirmRequest(token="tok")))
    confirm_calls = [
        c for c in db.executed
        if c[0].strip().startswith("UPDATE talentpool_optin_requests SET confirmed_at")
    ]
    assert len(confirm_calls) == 1
    assert confirm_calls[0][1] == (5,)


# ── WS-4 (migrations/037): talentpool-confirm records the application ────

def test_talentpool_confirm_with_still_open_job_creates_match_and_returns_applied_job(patch_public_router):
    from models.schemas import TalentpoolConfirmRequest
    pending = {"id": 6, "email": "applicant@example.com", "scope": "matching_only",
               "source": "vacancy_apply", "job_id": 55}
    db = _PublicDB(
        pending_row=pending, existing_candidate=None,
        job_row={"id": 55, "title": "Senior Embedded C++ Engineer"},
    )
    router = patch_public_router(db)
    result = asyncio.run(
        router.talentpool_confirm(request=_fake_request(), data=TalentpoolConfirmRequest(token="tok"))
    )
    assert result["applied_job"] == {"id": 55, "title": "Senior Embedded C++ Engineer"}
    match_calls = [c for c in db.executed if c[0].strip().startswith("INSERT INTO matches")]
    assert len(match_calls) == 1
    match_sql, match_args = match_calls[0]
    assert "ON CONFLICT (candidate_id, job_id)" in match_sql
    assert "'applied'" in match_sql
    assert match_args == (1, 55)  # candidate_id from the INSERT INTO candidates RETURNING id


def test_talentpool_confirm_with_no_job_id_returns_applied_job_none(patch_public_router):
    from models.schemas import TalentpoolConfirmRequest
    pending = {"id": 7, "email": "plain@example.com", "scope": "matching_only",
               "source": "kandidaten_page", "job_id": None}
    db = _PublicDB(pending_row=pending, existing_candidate=None)
    router = patch_public_router(db)
    result = asyncio.run(
        router.talentpool_confirm(request=_fake_request(), data=TalentpoolConfirmRequest(token="tok"))
    )
    assert result["applied_job"] is None
    match_calls = [c for c in db.executed if c[0].strip().startswith("INSERT INTO matches")]
    assert match_calls == []


def test_talentpool_confirm_with_job_closed_since_optin_returns_applied_job_none(patch_public_router):
    """The job was open when the applicant opted in, but has since closed
    -- confirm must not create a match for a job that is no longer
    eligible, and must say so via applied_job=None rather than an error."""
    from models.schemas import TalentpoolConfirmRequest
    pending = {"id": 8, "email": "late@example.com", "scope": "matching_only",
               "source": "vacancy_apply", "job_id": 55}
    db = _PublicDB(pending_row=pending, existing_candidate=None, job_row=None)
    router = patch_public_router(db)
    result = asyncio.run(
        router.talentpool_confirm(request=_fake_request(), data=TalentpoolConfirmRequest(token="tok"))
    )
    assert result["applied_job"] is None
    match_calls = [c for c in db.executed if c[0].strip().startswith("INSERT INTO matches")]
    assert match_calls == []


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
                withdraw, candidate_id = args
                return {
                    "id": candidate_id, "consent_talentpool_at": None,
                    "consent_talentpool_until": None, "consent_scope": None,
                    "consent_source": None, "lawful_basis": self.candidate["lawful_basis"],
                    "consent_withdrawn_at": "2026-09-04T00:00:00Z" if withdraw else None,
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


def test_admin_talentpool_consent_never_flips_portal_registratie(patch_admin_router):
    """H3a via the shared helper: an admin recording talentpool consent
    for a portal_registratie candidate never flips their lawful_basis
    either -- same rule as the portal and public-confirm endpoints."""
    from models.schemas import AdminTalentpoolConsentUpdate
    db = _AdminDB(candidate={"id": 11, "lawful_basis": "portal_registratie"})
    router = patch_admin_router(db)
    data = AdminTalentpoolConsentUpdate(consent=True, scope="matching_only", evidence="Signed form.")
    row = asyncio.run(router.admin_update_talentpool_consent(
        candidate_id=11, data=data, current_user={"id": 3, "role": "admin"},
    ))
    assert row["lawful_basis"] == "portal_registratie"


def test_admin_talentpool_consent_withdrawal_stamps_withdrawn_at_for_talentpool_only_basis(patch_admin_router):
    """M1, admin path: same withdrawal rule as the portal endpoint."""
    from models.schemas import AdminTalentpoolConsentUpdate
    db = _AdminDB(candidate={"id": 12, "lawful_basis": "opt_in_talentpool"})
    router = patch_admin_router(db)
    data = AdminTalentpoolConsentUpdate(consent=False, evidence="Candidate e-mailed asking to be removed.")
    asyncio.run(router.admin_update_talentpool_consent(
        candidate_id=12, data=data, current_user={"id": 3, "role": "admin"},
    ))
    update_sql, update_args = db.updates[0]
    assert "consent_withdrawn_at" in update_sql
    withdraw_flag, candidate_id = update_args
    assert withdraw_flag is True


def test_admin_talentpool_consent_evidence_is_redacted_before_audit_log(patch_admin_router):
    """L2: any e-mail-looking substring in the free-text `evidence` field
    is replaced with a hash marker before it ever reaches audit_log."""
    from models.schemas import AdminTalentpoolConsentUpdate
    db = _AdminDB(candidate={"id": 13, "lawful_basis": None})
    router = patch_admin_router(db)
    data = AdminTalentpoolConsentUpdate(
        consent=True, scope="matching_only",
        evidence="Signed form received from jane.doe@example.com on 2026-09-01.",
    )
    asyncio.run(router.admin_update_talentpool_consent(
        candidate_id=13, data=data, current_user={"id": 3, "role": "admin"},
    ))
    audit_sql, audit_args = db.audit[0]
    payload = json.loads(audit_args[4])
    assert "jane.doe@example.com" not in payload["evidence"]
    assert "[redacted:" in payload["evidence"]
    assert "Signed form received from" in payload["evidence"]


# ── core/privacy.py shared helpers ────────────────────────────────────────

def test_should_set_talentpool_lawful_basis_only_null_or_already_talentpool():
    from core import privacy
    assert privacy.should_set_talentpool_lawful_basis(None) is True
    assert privacy.should_set_talentpool_lawful_basis("opt_in_talentpool") is True
    assert privacy.should_set_talentpool_lawful_basis("portal_registratie") is False
    assert privacy.should_set_talentpool_lawful_basis("gerechtvaardigd_belang") is False
    assert privacy.should_set_talentpool_lawful_basis("toestemming_referral") is False


def test_redact_emails_replaces_email_like_substrings_only():
    from core import privacy
    text = "Contact via jane.doe@example.com or +31 6 12345678, ref 2026-09-01."
    out = privacy.redact_emails(text)
    assert "jane.doe@example.com" not in out
    assert "[redacted:" in out
    assert "+31 6 12345678" in out  # non-email text untouched
    assert "ref 2026-09-01" in out


def test_redact_emails_is_a_noop_on_text_without_an_email():
    from core import privacy
    assert privacy.redact_emails("No e-mail here, just a note.") == "No e-mail here, just a note."


def test_redact_emails_passes_through_none_and_empty():
    from core import privacy
    assert privacy.redact_emails(None) is None
    assert privacy.redact_emails("") == ""


# ── services/scheduler.py talentpool_reminder_job (H3c) ──────────────────

class _ReminderDB:
    def __init__(self, due_rows):
        self.due_rows = due_rows
        self.executed = []

    async def fetch_all(self, sql, *args):
        import services.scheduler as scheduler
        assert sql is scheduler.TALENTPOOL_REMINDER_SQL
        return self.due_rows

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "OK"


def test_talentpool_reminder_job_sends_one_email_and_stamps_reminder_sent_at(monkeypatch):
    import services.scheduler as scheduler

    db = _ReminderDB([{"id": 1, "email": "due@example.com", "full_name": "Jane Doe"}])
    monkeypatch.setattr(scheduler, "fetch_all", db.fetch_all)
    monkeypatch.setattr(scheduler, "execute", db.execute)

    sent_calls = []

    async def _fake_send_email(**kwargs):
        sent_calls.append(kwargs)
        return True

    import services.email_service as email_service_module
    monkeypatch.setattr(email_service_module.email_service, "send_email", _fake_send_email)

    result = asyncio.run(scheduler.talentpool_reminder_job())
    assert result == {"candidates_due": 1, "sent": 1}
    assert len(sent_calls) == 1
    assert sent_calls[0]["to_email"] == "due@example.com"
    stamp_calls = [c for c in db.executed if "consent_reminder_sent_at = NOW()" in c[0]]
    assert len(stamp_calls) == 1
    assert stamp_calls[0][1] == (1,)


def test_talentpool_reminder_job_does_not_stamp_when_send_fails(monkeypatch):
    import services.scheduler as scheduler

    db = _ReminderDB([{"id": 2, "email": "fails@example.com", "full_name": None}])
    monkeypatch.setattr(scheduler, "fetch_all", db.fetch_all)
    monkeypatch.setattr(scheduler, "execute", db.execute)

    async def _fake_send_email(**kwargs):
        return False

    import services.email_service as email_service_module
    monkeypatch.setattr(email_service_module.email_service, "send_email", _fake_send_email)

    result = asyncio.run(scheduler.talentpool_reminder_job())
    assert result == {"candidates_due": 1, "sent": 0}
    assert db.executed == []


def test_talentpool_reminder_sql_excludes_already_reminded_and_far_out_expiries():
    import services.scheduler as scheduler
    sql = scheduler.TALENTPOOL_REMINDER_SQL
    assert "consent_reminder_sent_at IS NULL" in sql
    assert "INTERVAL '30 days'" in sql
    assert "lawful_basis = 'opt_in_talentpool'" in sql


# ── services/scheduler.py talentpool_optin_requests retention (M2) ───────

class _OptinRetentionRecorder:
    def __init__(self, stale_rows):
        self.stale_rows = stale_rows
        self.fetch_calls = []
        self.execute_calls = []

    async def fetch_all(self, sql, *args):
        self.fetch_calls.append((sql, args))
        if sql is __import__("services.scheduler", fromlist=["x"]).TALENTPOOL_OPTIN_REQUESTS_STALE_SQL:
            return self.stale_rows
        return []

    async def execute(self, sql, *args):
        self.execute_calls.append((sql, args))
        return "OK"


def test_talentpool_optin_requests_cleanup_job_deletes_stale_rows_and_audits(monkeypatch):
    """WS-E.10 (retention-kolommen branch, fifth round): the old
    run_retention_purge(dry_run=...) single entry point is gone --
    talentpool_optin_requests cleanup (not one of the ten guarded
    RETENTION_TABLE categories the owner moved to monthly human review;
    see services/scheduler.py's own docstring on that job) now has its
    own small, unconditional daily job."""
    import services.scheduler as scheduler
    rec = _OptinRetentionRecorder(stale_rows=[{"id": 5}])
    monkeypatch.setattr(scheduler, "fetch_all", rec.fetch_all)
    monkeypatch.setattr(scheduler, "execute", rec.execute)

    result = asyncio.run(scheduler.talentpool_optin_requests_cleanup_job())
    assert result == {"status": "purged", "count": 1}
    delete_calls = [c for c in rec.execute_calls if c[0].strip().startswith("DELETE FROM talentpool_optin_requests")]
    assert len(delete_calls) == 1
    assert delete_calls[0][1] == ([5],)
    audit_calls = [
        c for c in rec.execute_calls
        if c[0].startswith("INSERT INTO audit_log") and c[1][1] == "talentpool_optin_requests"
    ]
    assert len(audit_calls) == 1


def test_talentpool_optin_requests_cleanup_job_writes_no_audit_row_when_nothing_is_stale(monkeypatch):
    import services.scheduler as scheduler
    rec = _OptinRetentionRecorder(stale_rows=[])
    monkeypatch.setattr(scheduler, "fetch_all", rec.fetch_all)
    monkeypatch.setattr(scheduler, "execute", rec.execute)

    result = asyncio.run(scheduler.talentpool_optin_requests_cleanup_job())
    assert result == {"status": "purged", "count": 0}
    assert rec.execute_calls == []


def test_talentpool_optin_requests_stale_sql_uses_a_7_day_window():
    import services.scheduler as scheduler
    assert "INTERVAL '7 days'" in scheduler.TALENTPOOL_OPTIN_REQUESTS_STALE_SQL
