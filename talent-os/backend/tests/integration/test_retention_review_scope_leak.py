"""
Retention-kolommen round 6 (security-auditor + code-reviewer, WS-E.10
approval queue): three reproduced scenarios (P1/P2/P3, security-audit)
plus the code-reviewer's FK-linked scenario (CR) -- each one an approved
retention_review_items item that used to anonymise/deactivate a SECOND,
unrelated person/row sharing the subject's address, without that second
row ever being on the wachtlijst or approved on its own.

routers/retention_admin.py's `_refuse_if_email_belongs_to_an_unrelated_
account()` now checks all three identity tables erase_person() touches
(candidates/users/client_prospects), any role on `users` -- not just
admin/client -- so every scenario below must now refuse (409) instead of
purging, and leave BOTH rows exactly as they were. Complements
tests/integration/test_ws_e10_retention_review_integration.py's own H2
test (an unrelated admin account), which this file doesn't repeat.
"""
import uuid

import pytest

pytestmark = pytest.mark.integration


def _client_and_job(db_run, *, suffix, account_status="lead"):
    from core.database import execute, fetch_one

    client_row = db_run(
        fetch_one,
        "INSERT INTO clients (company_name, domain, account_status) VALUES ($1, $2, $3) RETURNING id",
        f"Scope Leak Client {suffix}", f"scope-leak-{suffix}.example.com", account_status,
    )
    job = db_run(
        fetch_one,
        "INSERT INTO job_orders (client_id, title) VALUES ($1, 'Embedded Engineer') RETURNING id",
        client_row["id"],
    )
    return client_row["id"], job["id"]


def _placed_candidate(db_run, *, suffix, email):
    """A candidate with an ACTIVE placement -- the 7-year fiscal floor
    core/retention.py's placed_candidate row documents, and which no
    approval anywhere in this backend may ever anonymise as a side
    effect."""
    from core.database import execute, fetch_one

    candidate = db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, status, deleted_at) VALUES ($1, $2, 'placed', NULL) RETURNING id",
        f"Placed Candidate {suffix}", email,
    )
    client_id, job_id = _client_and_job(db_run, suffix=f"{suffix}-placement", account_status="active")
    db_run(
        execute,
        "INSERT INTO placements (candidate_id, job_id, client_id, placement_type, status) "
        "VALUES ($1, $2, $3, 'werving_selectie', 'actief')",
        candidate["id"], job_id, client_id,
    )
    return candidate["id"]


def _live_candidate_portal_account(db_run, *, suffix, email):
    """A `users` row, role='candidate', logged in today -- a live login,
    never linked via candidate_profiles.candidate_id to anything."""
    from core.database import execute, fetch_one

    user = db_run(
        fetch_one,
        """INSERT INTO users (email, password_hash, full_name, role, is_verified, password_changed_at, last_login_at)
           VALUES ($1, 'x', $2, 'candidate', TRUE, NOW(), NOW())
           RETURNING id""",
        email, f"Live Portal Account {suffix}",
    )
    return user["id"]


def _approve(db_run, admin, item_id):
    from routers import retention_admin

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    return db_run(
        retention_admin.approve_review_item, item_id, payload,
        current_user={"id": admin["id"], "role": "admin"},
    )


# ── P1: approving a prospect_responding item (client_prospects) must not
#    touch a placed candidate or a live candidate-role login sharing the
#    contact's address. ────────────────────────────────────────────────

def test_approving_a_prospect_does_not_purge_a_placed_candidate_or_live_login(db_run, make_admin):
    import services.scheduler as scheduler
    from fastapi import HTTPException
    from core.database import execute, fetch_one

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    shared_email = f"scope-leak-p1-{suffix}@example.com"

    # The prospect itself: genuinely due (status != 'new', contacted
    # >12mo ago, not opted out, and its OWN client relationship is not
    # 'active' -- see PROSPECT_RESPONDING_SQL).
    prospect_client_id, _ = _client_and_job(db_run, suffix=f"{suffix}-prospect-own", account_status="lead")
    prospect = db_run(
        fetch_one,
        """INSERT INTO client_prospects (company_name, contact_name, contact_email, status, last_contacted_at)
           VALUES ($1, 'Prospect Contact', $2, 'contacted', NOW() - INTERVAL '13 months')
           RETURNING id""",
        f"Scope Leak Prospect Co {suffix}", shared_email,
    )

    placed_candidate_id = _placed_candidate(db_run, suffix=suffix, email=shared_email)
    live_user_id = _live_candidate_portal_account(db_run, suffix=suffix, email=shared_email)

    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'prospect_responding' AND subject_id = $1",
        prospect["id"],
    )
    assert item is not None, "prospect must actually be queued for this test to be meaningful"

    with pytest.raises(HTTPException) as exc_info:
        _approve(db_run, admin, item["id"])
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "retention_purge_blocked_unrelated_account"

    # Neither the prospect, the placed candidate, nor the live login was touched.
    prospect_row = db_run(fetch_one, "SELECT contact_email, opt_out_at FROM client_prospects WHERE id = $1", prospect["id"])
    assert prospect_row["contact_email"] == shared_email
    assert prospect_row["opt_out_at"] is None

    candidate_row = db_run(fetch_one, "SELECT email, deleted_at FROM candidates WHERE id = $1", placed_candidate_id)
    assert candidate_row["email"] == shared_email
    assert candidate_row["deleted_at"] is None

    placement_row = db_run(fetch_one, "SELECT id FROM placements WHERE candidate_id = $1", placed_candidate_id)
    assert placement_row is not None  # still exists, untouched

    user_row = db_run(fetch_one, "SELECT email, deleted_at FROM users WHERE id = $1", live_user_id)
    assert user_row["email"] == shared_email
    assert user_row["deleted_at"] is None

    still_pending = db_run(fetch_one, "SELECT status FROM retention_review_items WHERE id = $1", item["id"])
    assert still_pending["status"] == "pending"


# ── P2: approving a sourced_no_response candidate must not opt out an
#    unrelated, still-live client_prospects contact sharing its address. ─

def test_approving_a_sourced_candidate_does_not_opt_out_an_unrelated_prospect_contact(db_run, make_admin):
    import services.scheduler as scheduler
    from fastapi import HTTPException
    from core.database import execute, fetch_one

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    shared_email = f"scope-leak-p2-{suffix}@example.com"

    candidate = db_run(
        fetch_one,
        """INSERT INTO candidates
             (full_name, email, status, lawful_basis, date_found, consent_withdrawn_at, deleted_at)
           VALUES ($1, $2, 'sourced', 'gerechtvaardigd_belang', CURRENT_DATE - INTERVAL '4 months', NULL, NULL)
           RETURNING id""",
        f"Sourced Candidate {suffix}", shared_email,
    )

    active_client_id, _ = _client_and_job(db_run, suffix=f"{suffix}-p2-client", account_status="active")
    prospect = db_run(
        fetch_one,
        """INSERT INTO client_prospects (company_name, contact_name, contact_email, status)
           VALUES ($1, 'Active Client Contact', $2, 'new') RETURNING id""",
        f"Scope Leak Active Client Co {suffix}", shared_email,
    )

    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'sourced_no_response' AND subject_id = $1",
        candidate["id"],
    )
    assert item is not None, "candidate must actually be queued for this test to be meaningful"

    with pytest.raises(HTTPException) as exc_info:
        _approve(db_run, admin, item["id"])
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "retention_purge_blocked_unrelated_account"

    candidate_row = db_run(fetch_one, "SELECT email, deleted_at FROM candidates WHERE id = $1", candidate["id"])
    assert candidate_row["email"] == shared_email
    assert candidate_row["deleted_at"] is None

    prospect_row = db_run(fetch_one, "SELECT contact_email, opt_out_at FROM client_prospects WHERE id = $1", prospect["id"])
    assert prospect_row["contact_email"] == shared_email
    assert prospect_row["opt_out_at"] is None


# ── P3: approving a dormant, UNLINKED portal account must not purge a
#    placed candidate that merely happens to share its address. ─────────

def test_approving_a_dormant_portal_account_does_not_purge_an_unlinked_placed_candidate(db_run, make_admin):
    import services.scheduler as scheduler
    from fastapi import HTTPException
    from core.database import execute, fetch_one

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    shared_email = f"scope-leak-p3-{suffix}@example.com"

    dormant_user = db_run(
        fetch_one,
        """INSERT INTO users (email, password_hash, full_name, role, is_verified, password_changed_at,
                              last_login_at, dormant_warning_sent_at)
           VALUES ($1, 'x', $2, 'candidate', TRUE, NOW(), NOW() - INTERVAL '19 months', NOW() - INTERVAL '2 months')
           RETURNING id""",
        shared_email, f"Dormant Portal Account {suffix}",
    )
    # Deliberately no candidate_profiles row at all -- P3's "niet via
    # candidate_profiles.candidate_id gekoppeld".
    placed_candidate_id = _placed_candidate(db_run, suffix=suffix, email=shared_email)

    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'portal_account_inactive' AND subject_id = $1",
        dormant_user["id"],
    )
    assert item is not None, "dormant account must actually be queued for this test to be meaningful"

    with pytest.raises(HTTPException) as exc_info:
        _approve(db_run, admin, item["id"])
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "retention_purge_blocked_unrelated_account"

    user_row = db_run(fetch_one, "SELECT email, deleted_at FROM users WHERE id = $1", dormant_user["id"])
    assert user_row["email"] == shared_email
    assert user_row["deleted_at"] is None

    candidate_row = db_run(fetch_one, "SELECT email, deleted_at FROM candidates WHERE id = $1", placed_candidate_id)
    assert candidate_row["email"] == shared_email
    assert candidate_row["deleted_at"] is None

    placement_row = db_run(fetch_one, "SELECT id FROM placements WHERE candidate_id = $1", placed_candidate_id)
    assert placement_row is not None


# ── CR (code-reviewer): a genuinely-due rejected candidate must not,
#    through a portal account merely sharing its address, drag in a
#    placed candidate that account is FK-linked to under a DIFFERENT
#    address. ──────────────────────────────────────────────────────────

def test_approving_a_rejected_candidate_does_not_follow_an_fk_linked_unrelated_placement(db_run, make_admin):
    import services.scheduler as scheduler
    from fastapi import HTTPException
    from core.database import execute, fetch_one

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    subject_email = f"scope-leak-cr-subject-{suffix}@example.com"
    linked_email = f"scope-leak-cr-linked-{suffix}@example.com"

    subject_candidate = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, status, rejected_at, deleted_at)
           VALUES ($1, $2, 'rejected', NOW() - INTERVAL '5 weeks', NULL) RETURNING id""",
        f"CR Subject Candidate {suffix}", subject_email,
    )
    # A DIFFERENT candidate, a DIFFERENT address, with an active placement.
    linked_candidate_id = _placed_candidate(db_run, suffix=f"{suffix}-cr-linked", email=linked_email)

    # The portal account shares the SUBJECT's address, but its FK points
    # at the OTHER (placed) candidate -- exactly the round-6 code-review
    # scenario.
    portal_user = db_run(
        fetch_one,
        """INSERT INTO users (email, password_hash, full_name, role, is_verified, password_changed_at, last_login_at)
           VALUES ($1, 'x', $2, 'candidate', TRUE, NOW(), NOW()) RETURNING id""",
        subject_email, f"CR Portal Account {suffix}",
    )
    db_run(
        execute,
        "INSERT INTO candidate_profiles (user_id, candidate_id) VALUES ($1, $2)",
        portal_user["id"], linked_candidate_id,
    )

    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        subject_candidate["id"],
    )
    assert item is not None, "subject candidate must actually be queued for this test to be meaningful"

    with pytest.raises(HTTPException) as exc_info:
        _approve(db_run, admin, item["id"])
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "retention_purge_blocked_unrelated_account"

    subject_row = db_run(fetch_one, "SELECT email, deleted_at FROM candidates WHERE id = $1", subject_candidate["id"])
    assert subject_row["email"] == subject_email
    assert subject_row["deleted_at"] is None

    linked_row = db_run(fetch_one, "SELECT email, deleted_at FROM candidates WHERE id = $1", linked_candidate_id)
    assert linked_row["email"] == linked_email
    assert linked_row["deleted_at"] is None

    portal_row = db_run(fetch_one, "SELECT email, deleted_at FROM users WHERE id = $1", portal_user["id"])
    assert portal_row["email"] == subject_email
    assert portal_row["deleted_at"] is None


# ── Round 6 re-check (security-auditor + code-reviewer): the guard used to
#    compare the RAW subject address (LOWER(email) = LOWER($1)) while
#    erase_person() compared the NORMALISED one (strip+lower) -- a subject
#    whose own stored address carries whitespace made the guard blind to a
#    real conflict elsewhere.
#
#    chief-of-staff FIX FIRST (retention-kolommen branch, finding 3):
#    ProspectCreate.email and CandidateCreate.email now strip on input
#    (models/schemas.py, routers/prospects.py), so POST /api/candidates
#    and POST /api/v1/admin/prospects can no longer be used to store a
#    padded address themselves -- both scenarios below instead write the
#    padding directly via SQL, right after creation, to reproduce the one
#    remaining way a stored address still ends up padded: a row written
#    before this fix, or by a path that bypasses these pydantic models
#    entirely (a raw INSERT, e.g. services/harvest.py). The guard itself
#    (LOWER(TRIM(...)) throughout routers/gdpr.py and
#    routers/retention_admin.py) still has to catch that row regardless of
#    how it got padded -- that is what these two tests prove. ────────────

def test_approving_a_padded_prospect_subject_still_detects_a_real_conflict(db_run, make_admin, client, api_key_headers):
    import services.scheduler as scheduler
    from fastapi import HTTPException
    from core.database import execute, fetch_one

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    clean_email = f"scope-leak-pad-a-{suffix}@example.com"
    padded_email = clean_email + " "  # trailing space

    resp = client.post(
        "/api/v1/admin/prospects",
        headers=admin["headers"],
        json={
            "company": f"Padded Prospect Co {suffix}",
            "contact_name": "Padded Prospect Contact",
            "email": padded_email,
            "status": "contacted",
            "lawful_basis": "zakelijk_functioneel_adres",
        },
    )
    assert resp.status_code == 201, resp.text
    prospect_id = resp.json()["id"]
    created_row = db_run(fetch_one, "SELECT contact_email FROM client_prospects WHERE id = $1", prospect_id)
    assert created_row["contact_email"] == clean_email, (
        "ProspectCreate.email should have stripped the padding at the door"
    )
    # Simulate a row that still carries a padded address regardless (a
    # pre-fix row, or a write path that bypasses ProspectCreate) -- this
    # is the scenario the guard itself must still cover.
    db_run(execute, "UPDATE client_prospects SET contact_email = $2 WHERE id = $1", prospect_id, padded_email)
    # last_contacted_at has no create-time field (routers/prospects.py) --
    # only PUT status changes / an approved outreach draft stamp it --
    # backdate it directly so PROSPECT_RESPONDING_SQL sees it as due.
    db_run(execute, "UPDATE client_prospects SET last_contacted_at = NOW() - INTERVAL '13 months' WHERE id = $1", prospect_id)
    prospect_before = db_run(fetch_one, "SELECT contact_email FROM client_prospects WHERE id = $1", prospect_id)
    assert prospect_before["contact_email"] == padded_email, "the padded address must actually be what's stored"

    # A genuine conflict sharing the CLEAN address: a placed candidate
    # (7-year fiscal floor) and a live candidate-role portal login.
    placed_candidate_id = _placed_candidate(db_run, suffix=f"{suffix}-pad-a", email=clean_email)
    live_user_id = _live_candidate_portal_account(db_run, suffix=f"{suffix}-pad-a", email=clean_email)

    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'prospect_responding' AND subject_id = $1",
        prospect_id,
    )
    assert item is not None, "prospect must actually be queued for this test to be meaningful"

    with pytest.raises(HTTPException) as exc_info:
        _approve(db_run, admin, item["id"])
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "retention_purge_blocked_unrelated_account"

    prospect_row = db_run(fetch_one, "SELECT contact_email, opt_out_at FROM client_prospects WHERE id = $1", prospect_id)
    assert prospect_row["contact_email"] == padded_email  # untouched -- still padded, not "purged"
    assert prospect_row["opt_out_at"] is None

    candidate_row = db_run(fetch_one, "SELECT email, deleted_at FROM candidates WHERE id = $1", placed_candidate_id)
    assert candidate_row["email"] == clean_email
    assert candidate_row["deleted_at"] is None

    user_row = db_run(fetch_one, "SELECT email, deleted_at FROM users WHERE id = $1", live_user_id)
    assert user_row["email"] == clean_email
    assert user_row["deleted_at"] is None

    still_pending = db_run(fetch_one, "SELECT status FROM retention_review_items WHERE id = $1", item["id"])
    assert still_pending["status"] == "pending"


def test_approving_a_padded_candidate_subject_still_detects_a_real_conflict(db_run, make_admin, client, api_key_headers):
    import services.scheduler as scheduler
    from fastapi import HTTPException
    from core.database import execute, fetch_one

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    clean_email = f"scope-leak-pad-b-{suffix}@example.com"
    padded_email = " " + clean_email  # leading space

    resp = client.post(
        "/api/candidates",
        headers=api_key_headers,
        json={
            "full_name": f"Padded Candidate {suffix}",
            "email": padded_email,
            "source_url": "https://example.com/profile",
            "lawful_basis": "gerechtvaardigd_belang",
        },
    )
    assert resp.status_code == 201, resp.text
    subject_id = resp.json()["id"]
    created_row = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", subject_id)
    assert created_row["email"] == clean_email, (
        "CandidateCreate.email should have stripped the padding at the door"
    )
    # Simulate a row that still carries a padded address regardless (a
    # pre-fix row, or a write path that bypasses CandidateCreate, e.g.
    # services/harvest.py's raw INSERTs) -- this is the scenario the
    # guard itself must still cover.
    db_run(execute, "UPDATE candidates SET email = $2 WHERE id = $1", subject_id, padded_email)
    # rejected_at/status have no create-time field on this endpoint either
    # -- backdate directly so REJECTED_APPLICANT_SQL sees it as due.
    db_run(
        execute,
        "UPDATE candidates SET status = 'rejected', rejected_at = NOW() - INTERVAL '5 weeks' WHERE id = $1",
        subject_id,
    )
    subject_before = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", subject_id)
    assert subject_before["email"] == padded_email, "the padded address must actually be what's stored"

    # A genuine conflict sharing the CLEAN address: a live candidate-role
    # portal login (any role on `users` is a conflict for a candidates-
    # table subject, round 6).
    live_user_id = _live_candidate_portal_account(db_run, suffix=f"{suffix}-pad-b", email=clean_email)

    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        subject_id,
    )
    assert item is not None, "candidate must actually be queued for this test to be meaningful"

    with pytest.raises(HTTPException) as exc_info:
        _approve(db_run, admin, item["id"])
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "retention_purge_blocked_unrelated_account"

    subject_row = db_run(fetch_one, "SELECT email, deleted_at FROM candidates WHERE id = $1", subject_id)
    assert subject_row["email"] == padded_email  # untouched -- still padded, not "purged"
    assert subject_row["deleted_at"] is None

    user_row = db_run(fetch_one, "SELECT email, deleted_at FROM users WHERE id = $1", live_user_id)
    assert user_row["email"] == clean_email
    assert user_row["deleted_at"] is None

    still_pending = db_run(fetch_one, "SELECT status FROM retention_review_items WHERE id = $1", item["id"])
    assert still_pending["status"] == "pending"
