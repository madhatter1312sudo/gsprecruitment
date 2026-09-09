"""
Integration tests for WS-E.10: the monthly retention review queue, end to
end against a real Postgres -- generation (services/scheduler.py
generate_retention_review()) actually writing retention_review_items rows,
and approval (routers/retention_admin.py approve_review_item()) actually
anonymising the real candidate row and recording a decision, per db_run()'s
pattern in tests/integration/conftest.py. Complements
tests/integration/test_retention_guards.py, which proves the *selectors*
this queue reads from are correct; this file proves the queue and the
approve/reject mechanism built on top of them.

B3 (security-audit round 5, codereview): every test below authenticates as
a real admin row via the `make_admin` fixture (tests/integration/
conftest.py) rather than a bare `{"id": 1}` current_user dict -- actor_id
on retention_review_decisions/audit_log is a real FK to `users`, and H2's
own guard queries `users` directly, so a fabricated id could silently miss
what it's meant to catch.
"""
import uuid

import pytest

from core import retention
from core.database import execute, fetch_all, fetch_one

pytestmark = pytest.mark.integration


def _rejected_candidate(db_run, *, suffix, email=None):
    row = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, status, rejected_at, deleted_at)
           VALUES ($1, $2, 'rejected', NOW() - INTERVAL '5 weeks', NULL)
           RETURNING id""",
        f"Review Queue Candidate {suffix}", email or f"review-queue-{suffix}@example.com",
    )
    return row["id"]


def test_generate_retention_review_queues_a_genuinely_due_rejected_applicant(db_run):
    import services.scheduler as scheduler

    suffix = uuid.uuid4().hex[:10]
    cid = _rejected_candidate(db_run, suffix=suffix)

    db_run(scheduler.generate_retention_review)

    item = db_run(
        fetch_one,
        "SELECT * FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        cid,
    )
    assert item is not None
    assert item["status"] == "pending"
    assert item["action"] == "anonymise"
    assert item["email"] == f"review-queue-{suffix}@example.com"
    assert item["term_expired_at"] is not None
    assert "afwijzing" in item["signal_missing_nl"]


def test_approving_a_queued_item_actually_anonymises_the_candidate(db_run, client, api_key_headers, make_admin):
    import services.scheduler as scheduler
    from routers import retention_admin

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    cid = _rejected_candidate(db_run, suffix=suffix)
    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        cid,
    )

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    result = db_run(
        retention_admin.approve_review_item, item["id"], payload,
        current_user={"id": admin["id"], "role": "admin"},
    )
    assert result == {"id": item["id"], "status": "purged"}

    candidate = db_run(fetch_one, "SELECT full_name, email FROM candidates WHERE id = $1", cid)
    # erase_person() anonymises in place -- the row survives (FK
    # integrity) but the identifying fields are gone.
    assert candidate["email"] != f"review-queue-{suffix}@example.com"

    updated_item = db_run(
        fetch_one, "SELECT status, purged_at, email FROM retention_review_items WHERE id = $1", item["id"],
    )
    assert updated_item["status"] == "purged"
    assert updated_item["purged_at"] is not None
    # H3: the review item's own email column is nulled once handled.
    assert updated_item["email"] is None

    decisions = db_run(
        fetch_all, "SELECT decision, actor_id FROM retention_review_decisions WHERE review_item_id = $1", item["id"],
    )
    assert [dict(d) for d in decisions] == [{"decision": "approved", "actor_id": admin["id"]}]


def test_approving_refuses_when_a_protective_signal_appeared_after_queueing(db_run, make_admin):
    """The exact scenario the re-verify-at-approve-time step exists for:
    a fresh match arrives for the candidate after the monthly list was
    generated but before an admin acts on it."""
    import services.scheduler as scheduler
    from routers import retention_admin
    from fastapi import HTTPException

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    cid = _rejected_candidate(db_run, suffix=suffix)
    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        cid,
    )

    client_row = db_run(
        fetch_one, "INSERT INTO clients (company_name, domain) VALUES ($1, 'example.com') RETURNING id",
        f"Review Queue Client {suffix}",
    )
    job = db_run(
        fetch_one,
        "INSERT INTO job_orders (client_id, title, description) VALUES ($1, 'Test Role', 'x') RETURNING id",
        client_row["id"],
    )
    db_run(
        execute,
        "INSERT INTO matches (candidate_id, job_id, status, updated_at) VALUES ($1, $2, 'suggested', NOW())",
        cid, job["id"],
    )

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    with pytest.raises(HTTPException) as exc_info:
        db_run(
            retention_admin.approve_review_item, item["id"], payload,
            current_user={"id": admin["id"], "role": "admin"},
        )
    assert exc_info.value.status_code == 409

    candidate = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", cid)
    assert candidate["email"] == f"review-queue-{suffix}@example.com"  # never touched

    updated_item = db_run(fetch_one, "SELECT status FROM retention_review_items WHERE id = $1", item["id"])
    assert updated_item["status"] == "no_longer_eligible"


def test_a_rejected_item_reappears_visibly_on_the_next_generation_run(db_run, make_admin):
    """WS-E.10's explicit requirement: someone the owner rejected must not
    silently return to 'pending' without any trace of the earlier
    rejection."""
    import services.scheduler as scheduler
    from routers import retention_admin

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    cid = _rejected_candidate(db_run, suffix=suffix)
    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        cid,
    )

    payload = retention_admin.ReviewDecisionRequest(note="wacht nog even")
    db_run(
        retention_admin.reject_review_item, item["id"], payload,
        current_user={"id": admin["id"], "role": "admin"},
    )

    rejected = db_run(fetch_one, "SELECT status, email FROM retention_review_items WHERE id = $1", item["id"])
    assert rejected["status"] == "rejected"
    assert rejected["email"] is None  # H3: nulled the moment it left 'pending'

    # Still due, still no protective signal -- the next monthly run
    # reopens the SAME row rather than inserting a second, indistinguishable one.
    db_run(scheduler.generate_retention_review)

    reopened = db_run(
        fetch_one,
        "SELECT id, status, email, reappeared_after_rejection_at FROM retention_review_items WHERE id = $1",
        item["id"],
    )
    assert reopened["id"] == item["id"]  # same row, not a duplicate
    assert reopened["status"] == "pending"
    assert reopened["email"] == f"review-queue-{suffix}@example.com"  # re-supplied by the fresh run
    assert reopened["reappeared_after_rejection_at"] is not None

    total_rows = db_run(
        fetch_all,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        cid,
    )
    assert len(total_rows) == 1  # never duplicated


def test_apollo_pool_purge_candidate_is_queued_and_purgeable_via_review(db_run, make_admin):
    """VERWERKINGSREGISTER.md §2.6/§5.7 -- since WS-E.10 the Apollo-pool
    cleanup shares this same queue instead of its own direct-delete
    endpoint."""
    import services.scheduler as scheduler
    from routers import retention_admin

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    cid = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, pool_origin, source_url, status)
           VALUES ($1, $2, 'apollo', NULL, 'sourced') RETURNING id""",
        f"Apollo Pool Candidate {suffix}", f"apollo-pool-{suffix}@example.com",
    )["id"]

    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT * FROM retention_review_items WHERE category = 'apollo_pool_purge' AND subject_id = $1", cid,
    )
    assert item is not None
    assert item["action"] == "anonymise"  # has an e-mail address

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    result = db_run(
        retention_admin.approve_review_item, item["id"], payload,
        current_user={"id": admin["id"], "role": "admin"},
    )
    assert result == {"id": item["id"], "status": "purged"}

    candidate = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", cid)
    assert candidate["email"] != f"apollo-pool-{suffix}@example.com"


# ── B1(d): generate, give the candidate a match, generate again -- item
#    reports no_longer_eligible instead of staying (falsely) pending. ────

def test_generate_twice_after_a_match_arrives_marks_the_item_no_longer_eligible(db_run):
    import services.scheduler as scheduler

    suffix = uuid.uuid4().hex[:10]
    cid = _rejected_candidate(db_run, suffix=suffix)

    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id, status FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        cid,
    )
    assert item["status"] == "pending"

    client_row = db_run(
        fetch_one, "INSERT INTO clients (company_name, domain) VALUES ($1, 'example.com') RETURNING id",
        f"No Longer Eligible Client {suffix}",
    )
    job = db_run(
        fetch_one,
        "INSERT INTO job_orders (client_id, title, description) VALUES ($1, 'Test Role', 'x') RETURNING id",
        client_row["id"],
    )
    db_run(
        execute,
        "INSERT INTO matches (candidate_id, job_id, status, updated_at) VALUES ($1, $2, 'suggested', NOW())",
        cid, job["id"],
    )

    db_run(scheduler.generate_retention_review)

    updated = db_run(
        fetch_one, "SELECT status, email FROM retention_review_items WHERE id = $1", item["id"],
    )
    assert updated["status"] == "no_longer_eligible"
    assert updated["email"] is None  # H3: nulled once it left 'pending'


# ── H1 (security-audit round 5, BLOCKING): the address used for the real
#    erasure is read fresh from the source row, never the (possibly
#    stale) retention_review_items.email snapshot. ───────────────────────

def test_approve_uses_the_candidates_current_email_not_the_queued_snapshot(db_run, make_admin):
    """H1: PATCH /api/candidates/{id} does not expose `email` in its own
    allowed_fields (there is no dedicated candidate-facing endpoint for
    it), so the drift this guards against -- the address on the source
    row moving after the monthly list was generated -- is reproduced
    directly at the column, the same class of change a future write path
    (a dedup/merge job, a manual data fix) could make."""
    import services.scheduler as scheduler
    from routers import retention_admin

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    original_email = f"review-queue-{suffix}@example.com"
    changed_email = f"review-queue-{suffix}-changed@example.com"
    cid = _rejected_candidate(db_run, suffix=suffix, email=original_email)
    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        cid,
    )
    queued = db_run(fetch_one, "SELECT email FROM retention_review_items WHERE id = $1", item["id"])
    assert queued["email"] == original_email

    # The address changes after generation but before an admin acts.
    db_run(execute, "UPDATE candidates SET email = $1 WHERE id = $2", changed_email, cid)

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    db_run(
        retention_admin.approve_review_item, item["id"], payload,
        current_user={"id": admin["id"], "role": "admin"},
    )

    candidate = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", cid)
    # If H1 were broken, erase_person() would have been called with
    # original_email, which no longer belongs to any candidates row --
    # this candidate (now on changed_email) would come back untouched.
    assert candidate["email"] != changed_email
    assert candidate["email"] != original_email


# ── H2 (security-audit round 5, BLOCKING): refuse rather than anonymise
#    an unrelated admin/client account sharing the subject's address. ────

def test_approve_refuses_when_the_address_also_belongs_to_an_admin_account(db_run, make_admin):
    import services.scheduler as scheduler
    from routers import retention_admin
    from fastapi import HTTPException

    admin = make_admin()
    other_admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    # The candidate's address happens to collide with an unrelated admin
    # account's login address -- not linked via any FK, purely the same
    # string.
    shared_email = other_admin["email"]
    cid = _rejected_candidate(db_run, suffix=suffix, email=shared_email)
    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        cid,
    )

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    with pytest.raises(HTTPException) as exc_info:
        db_run(
            retention_admin.approve_review_item, item["id"], payload,
            current_user={"id": admin["id"], "role": "admin"},
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "retention_purge_blocked_unrelated_account"

    # Neither the candidate nor the admin account was touched.
    candidate = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", cid)
    assert candidate["email"] == shared_email
    admin_row = db_run(fetch_one, "SELECT email, deleted_at FROM users WHERE id = $1", other_admin["id"])
    assert admin_row["email"] == shared_email
    assert admin_row["deleted_at"] is None
    still_pending = db_run(fetch_one, "SELECT status FROM retention_review_items WHERE id = $1", item["id"])
    assert still_pending["status"] == "pending"  # never claimed


# ── M2 (security-audit round 5, BLOCKING): the atomic claim -- a second
#    approve on an already-purged item is refused, never double-processed. ─

def test_a_second_approve_on_an_already_purged_item_is_refused(db_run, make_admin):
    import services.scheduler as scheduler
    from routers import retention_admin
    from fastapi import HTTPException

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    cid = _rejected_candidate(db_run, suffix=suffix)
    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        cid,
    )

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    first = db_run(
        retention_admin.approve_review_item, item["id"], payload,
        current_user={"id": admin["id"], "role": "admin"},
    )
    assert first == {"id": item["id"], "status": "purged"}

    with pytest.raises(HTTPException) as exc_info:
        db_run(
            retention_admin.approve_review_item, item["id"], payload,
            current_user={"id": admin["id"], "role": "admin"},
        )
    assert exc_info.value.status_code == 409

    decisions = db_run(
        fetch_all, "SELECT decision FROM retention_review_decisions WHERE review_item_id = $1", item["id"],
    )
    assert len(decisions) == 1  # the second attempt never wrote a second decision row
