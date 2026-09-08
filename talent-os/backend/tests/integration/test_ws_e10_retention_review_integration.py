"""
Integration tests for WS-E.10 (owner decision, retention-kolommen branch,
fifth round): the monthly retention review queue, end to end against a
real Postgres -- generation (services/scheduler.py
generate_retention_review()) actually writing retention_review_items rows,
and approval (routers/retention_admin.py approve_review_item()) actually
anonymising the real candidate row and recording a decision, per db_run()'s
pattern in tests/integration/conftest.py. Complements
tests/integration/test_retention_guards.py, which proves the *selectors*
this queue reads from are correct; this file proves the queue and the
approve/reject mechanism built on top of them.
"""
import uuid

import pytest

from core import retention
from core.database import execute, fetch_all, fetch_one

pytestmark = pytest.mark.integration


def _rejected_candidate(db_run, *, suffix):
    row = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, status, rejected_at, deleted_at)
           VALUES ($1, $2, 'rejected', NOW() - INTERVAL '5 weeks', NULL)
           RETURNING id""",
        f"Review Queue Candidate {suffix}", f"review-queue-{suffix}@example.com",
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


def test_approving_a_queued_item_actually_anonymises_the_candidate(db_run, client, api_key_headers):
    import services.scheduler as scheduler
    from routers import retention_admin

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
        retention_admin.approve_review_item, item["id"], payload, current_user={"id": 1, "role": "admin"},
    )
    assert result == {"id": item["id"], "status": "purged"}

    candidate = db_run(fetch_one, "SELECT full_name, email FROM candidates WHERE id = $1", cid)
    # erase_person() anonymises in place -- the row survives (FK
    # integrity) but the identifying fields are gone.
    assert candidate["email"] != f"review-queue-{suffix}@example.com"

    updated_item = db_run(fetch_one, "SELECT status, purged_at FROM retention_review_items WHERE id = $1", item["id"])
    assert updated_item["status"] == "purged"
    assert updated_item["purged_at"] is not None

    decisions = db_run(
        fetch_all, "SELECT decision, actor_id FROM retention_review_decisions WHERE review_item_id = $1", item["id"],
    )
    assert [dict(d) for d in decisions] == [{"decision": "approved", "actor_id": 1}]


def test_approving_refuses_when_a_protective_signal_appeared_after_queueing(db_run):
    """The exact scenario the re-verify-at-approve-time step exists for:
    a fresh match arrives for the candidate after the monthly list was
    generated but before an admin acts on it."""
    import services.scheduler as scheduler
    from routers import retention_admin
    from fastapi import HTTPException

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
        db_run(retention_admin.approve_review_item, item["id"], payload, current_user={"id": 1, "role": "admin"})
    assert exc_info.value.status_code == 409

    candidate = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", cid)
    assert candidate["email"] == f"review-queue-{suffix}@example.com"  # never touched

    updated_item = db_run(fetch_one, "SELECT status FROM retention_review_items WHERE id = $1", item["id"])
    assert updated_item["status"] == "no_longer_eligible"


def test_a_rejected_item_reappears_visibly_on_the_next_generation_run(db_run):
    """WS-E.10's explicit requirement: someone the owner rejected must not
    silently return to 'pending' without any trace of the earlier
    rejection."""
    import services.scheduler as scheduler
    from routers import retention_admin

    suffix = uuid.uuid4().hex[:10]
    cid = _rejected_candidate(db_run, suffix=suffix)
    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        cid,
    )

    payload = retention_admin.ReviewDecisionRequest(note="wacht nog even")
    db_run(retention_admin.reject_review_item, item["id"], payload, current_user={"id": 1, "role": "admin"})

    rejected = db_run(fetch_one, "SELECT status FROM retention_review_items WHERE id = $1", item["id"])
    assert rejected["status"] == "rejected"

    # Still due, still no protective signal -- the next monthly run
    # reopens the SAME row rather than inserting a second, indistinguishable one.
    db_run(scheduler.generate_retention_review)

    reopened = db_run(
        fetch_one,
        "SELECT id, status, reappeared_after_rejection_at FROM retention_review_items WHERE id = $1",
        item["id"],
    )
    assert reopened["id"] == item["id"]  # same row, not a duplicate
    assert reopened["status"] == "pending"
    assert reopened["reappeared_after_rejection_at"] is not None

    total_rows = db_run(
        fetch_all,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1",
        cid,
    )
    assert len(total_rows) == 1  # never duplicated


def test_apollo_pool_purge_candidate_is_queued_and_purgeable_via_review(db_run):
    """VERWERKINGSREGISTER.md §2.6/§5.7 -- since WS-E.10 the Apollo-pool
    cleanup shares this same queue instead of its own direct-delete
    endpoint."""
    import services.scheduler as scheduler
    from routers import retention_admin

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
        retention_admin.approve_review_item, item["id"], payload, current_user={"id": 1, "role": "admin"},
    )
    assert result == {"id": item["id"], "status": "purged"}

    candidate = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", cid)
    assert candidate["email"] != f"apollo-pool-{suffix}@example.com"
