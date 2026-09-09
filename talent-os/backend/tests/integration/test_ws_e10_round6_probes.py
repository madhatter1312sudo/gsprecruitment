"""
Adversarial probes for the sixth retention-review repair round (WS-E.10,
retention-kolommen branch) -- written to try to BREAK the round-6 fixes,
not to confirm the builder's own summary. Runs through the real routers/
services against a real Postgres, exactly like
tests/integration/test_ws_e10_retention_review_integration.py, which this
file deliberately does not touch.

Note up front (probe 1): the task brief that produced this file assumed
"wijzig A's e-mail via PATCH /api/candidates/{id}" as the reproduction
step for H1. That endpoint's CandidateAdminUpdate schema
(models/schemas.py) does not carry an `email` field at all, and no other
real write path in this backend ever changes an *existing*
candidates.email to a different value -- services/scheduler.py's
apollo_enrich_batch() and services/harvest.py's enrich_matched() both
filter their own SELECTs on "email IS NULL" (fill-once, never overwrite),
and routers/webhook.py's candidate_updated action does not accept `email`
either. So the exact scenario as specified is unreachable via any real
path for the `candidates` table. The one real endpoint in this codebase
that changes an *existing* row's e-mail is PUT /api/v1/admin/users/{id}
(routers/admin.py update_user, `email` is in its own `allowed` set) --
which is exactly the anchor `portal_account_inactive` (subject_table=
'users') uses. Probe 1 below therefore exercises H1 through that real
path instead, on a portal_account_inactive item, and the discrepancy is
reported here rather than silently swapped out from under the reader.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from core import privacy
from core.database import execute, fetch_all, fetch_one

pytestmark = pytest.mark.integration


def _suffix():
    return uuid.uuid4().hex[:10]


def _rejected_candidate(db_run, *, suffix, email=None, weeks_ago=5):
    row = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, status, rejected_at, deleted_at)
           VALUES ($1, $2, 'rejected', NOW() - ($3 || ' weeks')::interval, NULL)
           RETURNING id""",
        f"Round6 Probe Candidate {suffix}", email or f"round6-probe-{suffix}@example.com", str(weeks_ago),
    )
    return row["id"]


async def _insert_portal_candidate(email: str, *, last_login_at, consent_talentpool_until=None):
    """A real candidate row + a linked users/candidate_profiles portal
    account -- the exact shape PORTAL_ACCOUNT_INACTIVE_SQL selects
    against (candidate_profiles -> users, joined, never by e-mail)."""
    cand = await fetch_one(
        """INSERT INTO candidates (full_name, email, status, consent_talentpool_until)
           VALUES ($1, $2, 'sourced', $3) RETURNING id""",
        f"Portal Candidate {uuid.uuid4().hex[:8]}", f"cand-{uuid.uuid4().hex[:10]}@example.com",
        consent_talentpool_until,
    )
    user = await fetch_one(
        """INSERT INTO users (email, password_hash, full_name, role, is_verified, last_login_at)
           VALUES ($1, 'x', 'Portal User', 'candidate', TRUE, $2) RETURNING id""",
        email, last_login_at,
    )
    await execute(
        "INSERT INTO candidate_profiles (user_id, candidate_id) VALUES ($1, $2)",
        user["id"], cand["id"],
    )
    return {"user_id": user["id"], "candidate_id": cand["id"]}


# ── Probe 1: e-mail change between generation and approval ──────────────

def test_probe1_email_change_between_generation_and_approval_never_touches_the_new_owner(
    db_run, make_admin,
):
    """H1's real-world anchor: portal_account_inactive, e-mail changed via
    the one real endpoint that can change an existing users.email (PUT
    /api/v1/admin/users/{id}). Person A's item must act on A's CURRENT
    address; person B, who has since taken A's OLD address, must be
    completely untouched -- not anonymised, not suppression-listed."""
    import services.scheduler as scheduler
    from routers import retention_admin, admin as admin_router
    from models.schemas import AdminUserUpdate

    admin = make_admin()
    old_email = f"round6-a-old-{_suffix()}@example.com"
    new_email = f"round6-a-new-{_suffix()}@example.com"
    b_email = old_email  # B will claim A's old address after A moves off it

    a = db_run(_insert_portal_candidate, old_email, last_login_at=datetime.now(timezone.utc) - timedelta(days=19 * 30))

    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id, email FROM retention_review_items WHERE category = 'portal_account_inactive' AND subject_id = $1",
        a["user_id"],
    )
    assert item is not None, "setup did not queue the portal account -- probe cannot proceed"
    assert item["email"] == old_email

    # Admin changes A's e-mail via the real endpoint, between generation and approval.
    db_run(
        admin_router.update_user, a["user_id"], AdminUserUpdate(email=new_email),
        current_user={"id": admin["id"], "role": "admin"},
    )

    # B now takes A's old address -- a distinct, unrelated candidate record.
    b_candidate = db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, status) VALUES ($1, $2, 'sourced') RETURNING id",
        f"Round6 Probe B {_suffix()}", b_email,
    )

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    result = db_run(
        retention_admin.approve_review_item, item["id"], payload,
        current_user={"id": admin["id"], "role": "admin"},
    )
    assert result == {"id": item["id"], "status": "purged"}

    # A: anonymised, and reachable now only under the NEW address's identity being gone.
    a_user = db_run(fetch_one, "SELECT email FROM users WHERE id = $1", a["user_id"])
    assert a_user["email"] != new_email, f"A's users row still carries the new address: {a_user['email']!r}"
    assert a_user["email"] != old_email

    # B: completely untouched.
    b_row = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", b_candidate["id"])
    assert b_row["email"] == b_email, f"B's row was touched by A's purge: {b_row}"

    b_hash = privacy.email_hash(privacy.normalize_email(b_email))
    suppressed = db_run(fetch_one, "SELECT 1 FROM suppression_list WHERE email_hash = $1", b_hash)
    assert suppressed is None, "B's (A's old) address ended up on the suppression list"


# ── Probe 2: shared address with an admin/client account blocks approval ─

def test_probe2_shared_address_with_client_account_refuses_409_and_changes_nothing(db_run, make_admin, make_client_user):
    import services.scheduler as scheduler
    from routers import retention_admin
    from fastapi import HTTPException

    admin = make_admin()
    suffix = _suffix()
    shared_email = f"round6-shared-{suffix}@example.com"

    cid = _rejected_candidate(db_run, suffix=suffix, email=shared_email)
    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1", cid,
    )
    assert item is not None

    # A client-role user account happens to carry the exact same address.
    db_run(execute, "UPDATE users SET email = $1 WHERE id = $2", shared_email, make_client_user()["id"])

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    with pytest.raises(HTTPException) as exc_info:
        db_run(
            retention_admin.approve_review_item, item["id"], payload,
            current_user={"id": admin["id"], "role": "admin"},
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "retention_purge_blocked_unrelated_account"

    # Nothing changed: candidate untouched, item still pending, no decision row.
    candidate = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", cid)
    assert candidate["email"] == shared_email

    still_item = db_run(fetch_one, "SELECT status, email FROM retention_review_items WHERE id = $1", item["id"])
    assert still_item["status"] == "pending"
    assert still_item["email"] == shared_email

    decisions = db_run(
        fetch_all, "SELECT * FROM retention_review_decisions WHERE review_item_id = $1", item["id"],
    )
    assert decisions == []


# ── Probe 3: email is scrubbed everywhere, including via self-service erasure ─

def test_probe3_email_nulled_on_approval_and_scrubbed_everywhere_by_erase_person(db_run, make_admin):
    import services.scheduler as scheduler
    from routers import retention_admin, gdpr as gdpr_router

    admin = make_admin()
    suffix = _suffix()
    email = f"round6-scrub-{suffix}@example.com"
    cid = _rejected_candidate(db_run, suffix=suffix, email=email)
    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1", cid,
    )

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    db_run(
        retention_admin.approve_review_item, item["id"], payload,
        current_user={"id": admin["id"], "role": "admin"},
    )
    purged_item = db_run(fetch_one, "SELECT email FROM retention_review_items WHERE id = $1", item["id"])
    assert purged_item["email"] is None

    # A SEPARATE row (a different category/table) still carries the exact
    # same (now-orphaned) address -- e.g. a stale leads_quiz row that was
    # never approved. A later self-service erasure of that same address
    # (erase_person(), the real DELETE /api/v1/gdpr/account path) must
    # scrub it too, per H3's own stated scope ("every OTHER row").
    quiz = db_run(
        fetch_one,
        "INSERT INTO quiz_submissions (email, answers) VALUES ($1, '{}'::jsonb) RETURNING id", email,
    )
    stale_item = db_run(
        fetch_one,
        """INSERT INTO retention_review_items
             (category, subject_table, subject_id, email, action, signal_missing_nl)
           VALUES ('leads_quiz', 'quiz_submissions', $1, $2, 'hard_delete', '')
           RETURNING id""",
        quiz["id"], email,
    )
    assert stale_item is not None

    db_run(gdpr_router.erase_person, email, actor_id=admin["id"], reason="self_service")

    row_after = db_run(
        fetch_one, "SELECT email FROM retention_review_items WHERE LOWER(email) = LOWER($1)", email,
    )
    assert row_after is None, f"erase_person() left retention_review_items.email == {email!r} somewhere"


# ── Probe 4: two concurrent approvals on the same item ───────────────────

def test_probe4_concurrent_approvals_on_the_same_item_produce_exactly_one_decision_and_one_purge(
    db_run, make_admin,
):
    import services.scheduler as scheduler
    from routers import retention_admin

    admin = make_admin()
    suffix = _suffix()
    cid = _rejected_candidate(db_run, suffix=suffix)
    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1", cid,
    )

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")

    async def _race():
        return await asyncio.gather(
            retention_admin.approve_review_item(item["id"], payload, current_user={"id": admin["id"], "role": "admin"}),
            retention_admin.approve_review_item(item["id"], payload, current_user={"id": admin["id"], "role": "admin"}),
            return_exceptions=True,
        )

    results = db_run(_race)

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(successes) == 1, f"expected exactly one winner, got {results!r}"
    assert len(failures) == 1
    from fastapi import HTTPException
    assert isinstance(failures[0], HTTPException)
    assert failures[0].status_code == 409

    decisions = db_run(
        fetch_all,
        "SELECT decision FROM retention_review_decisions WHERE review_item_id = $1", item["id"],
    )
    assert len(decisions) == 1, f"expected exactly one decisions row, got {decisions!r}"
    assert decisions[0]["decision"] == "approved"

    final_item = db_run(fetch_one, "SELECT status FROM retention_review_items WHERE id = $1", item["id"])
    assert final_item["status"] == "purged"

    candidate = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", cid)
    assert candidate["email"] != f"round6-probe-{suffix}@example.com"


# ── Probe 5: bulk approval with one item that hits a real FK violation ───

def test_probe5_bulk_survives_a_real_foreign_key_violation_on_one_item(db_run, make_admin):
    """A crafted (not naturally-occurring) item forces routers/
    retention_admin.py's hard_delete branch to hit a genuine asyncpg
    ForeignKeyViolationError (outreach_drafts.presented_candidate_id ->
    candidates(id), no ON DELETE clause) -- proving M1's bare-`Exception`
    catch in bulk_review_decision actually survives a real DB error, not
    only a hand-thrown HTTPException, and that the OTHER item in the same
    batch still gets processed with its own status in the result."""
    import services.scheduler as scheduler
    from routers import retention_admin

    admin = make_admin()

    # Good item: an ordinary, genuinely-due rejected applicant.
    good_suffix = _suffix()
    good_cid = _rejected_candidate(db_run, suffix=good_suffix)

    # Broken item: also a genuinely-due rejected applicant (so
    # _is_still_eligible passes) but with an outreach_drafts row
    # referencing it, and its review-item row's `action` forced to
    # 'hard_delete' (never true for a real rejected_applicant row, but a
    # value _HARD_DELETE_TABLES/the DB CHECK both already allow) so the
    # DELETE branch actually runs and hits the FK constraint.
    bad_suffix = _suffix()
    bad_cid = _rejected_candidate(db_run, suffix=bad_suffix)
    db_run(
        execute,
        "INSERT INTO outreach_drafts (target_type, target_email, target_name, subject, body, status, presented_candidate_id) "
        "VALUES ('client_prospect', $1, 'x', 'x', 'x', 'draft', $2)",
        f"outreach-{bad_suffix}@example.com", bad_cid,
    )

    db_run(scheduler.generate_retention_review)
    good_item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1", good_cid,
    )
    bad_item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1", bad_cid,
    )
    assert good_item is not None and bad_item is not None
    # Force the bad item's action to hard_delete so the DELETE branch runs.
    db_run(execute, "UPDATE retention_review_items SET action = 'hard_delete' WHERE id = $1", bad_item["id"])

    from routers.retention_admin import ReviewBulkRequest
    payload = ReviewBulkRequest(decision="approved", ids=[good_item["id"], bad_item["id"]], confirm="APPROVE")
    result = db_run(
        retention_admin.bulk_review_decision, payload, current_user={"id": admin["id"], "role": "admin"},
    )

    by_id = {r["id"]: r for r in result["results"]}
    assert by_id[good_item["id"]].get("status") == "purged", by_id[good_item["id"]]
    assert by_id[bad_item["id"]].get("status") == "error", by_id[bad_item["id"]]

    good_candidate = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", good_cid)
    assert good_candidate["email"] != f"round6-probe-{good_suffix}@example.com"

    bad_candidate = db_run(fetch_one, "SELECT status FROM candidates WHERE id = $1", bad_cid)
    assert bad_candidate is not None  # never deleted -- the FK violation rolled it back

    bad_item_after = db_run(fetch_one, "SELECT status FROM retention_review_items WHERE id = $1", bad_item["id"])
    assert bad_item_after["status"] == "pending", (
        "M2's unclaim-on-failure should have put the item back to 'pending', "
        f"got {bad_item_after['status']!r}"
    )
    # M2: the decision row for the failed attempt is still written (a real
    # approval attempt happened, even though the action itself failed).
    bad_decisions = db_run(
        fetch_all, "SELECT decision FROM retention_review_decisions WHERE review_item_id = $1", bad_item["id"],
    )
    assert len(bad_decisions) == 1
    assert bad_decisions[0]["decision"] == "approved"


# ── Probe 6: the 18-month boundary, and talentpool-consent immunity ──────

def test_probe6_eighteen_month_boundary_is_exact(db_run):
    import services.scheduler as scheduler

    just_under = db_run(
        _insert_portal_candidate,
        f"round6-under-{_suffix()}@example.com",
        last_login_at=datetime.now(timezone.utc) - timedelta(days=18 * 30 - 1),
    )
    just_over = db_run(
        _insert_portal_candidate,
        f"round6-over-{_suffix()}@example.com",
        last_login_at=datetime.now(timezone.utc) - timedelta(days=18 * 30 + 1),
    )
    # NB: PORTAL_ACCOUNT_INACTIVE_SQL's cutoff is 18 *calendar* months via
    # `last_login_at + INTERVAL '18 months'`, not 18*30 days -- use exact
    # calendar arithmetic via SQL directly for the true boundary instead
    # of approximating in Python, so this probe cannot drift from what the
    # selector actually enforces.
    exact_under = db_run(
        fetch_one,
        "SELECT (NOW() - INTERVAL '18 months' + INTERVAL '1 day') AS ts",
    )["ts"]
    exact_over = db_run(
        fetch_one,
        "SELECT (NOW() - INTERVAL '18 months' - INTERVAL '1 day') AS ts",
    )["ts"]
    under = db_run(_insert_portal_candidate, f"round6-exactunder-{_suffix()}@example.com", last_login_at=exact_under)
    over = db_run(_insert_portal_candidate, f"round6-exactover-{_suffix()}@example.com", last_login_at=exact_over)

    db_run(scheduler.generate_retention_review)

    def _status_for(user_id):
        row = db_run(
            fetch_one,
            "SELECT 1 FROM retention_review_items WHERE category = 'portal_account_inactive' AND subject_id = $1",
            user_id,
        )
        return row is not None

    assert _status_for(under["user_id"]) is False, "18 months minus a day must NOT be queued"
    assert _status_for(over["user_id"]) is True, "18 months plus a day MUST be queued"


def test_probe6_linked_candidate_with_valid_talentpool_consent_is_never_queued(db_run):
    """Even wildly overdue on last_login_at, a portal account whose
    linked candidate carries a currently-valid talentpool consent must
    never appear -- _CANDIDATE_ENGAGEMENT_SIGNALS_SQL's own consent
    clause, reused by PORTAL_ACCOUNT_INACTIVE_SQL."""
    import services.scheduler as scheduler

    protected = db_run(
        _insert_portal_candidate,
        f"round6-protected-{_suffix()}@example.com",
        last_login_at=datetime.now(timezone.utc) - timedelta(days=5 * 365),
        consent_talentpool_until=datetime.now(timezone.utc) + timedelta(days=30),
    )

    db_run(scheduler.generate_retention_review)

    row = db_run(
        fetch_one,
        "SELECT 1 FROM retention_review_items WHERE category = 'portal_account_inactive' AND subject_id = $1",
        protected["user_id"],
    )
    assert row is None, "a linked candidate with valid talentpool consent must never be queued"


# ── Probe 7: reappearance after rejection, and survival of a partial failure ─

def test_probe7_rejected_item_reappearance_is_recorded_and_survives_a_failed_reapproval(
    db_run, make_admin,
):
    """Two parts, both against the real approve/reject/generate path:
      1. a rejected item that becomes due again is visibly marked
         (reappeared_after_rejection_at), not silently reopened.
      2. once reopened, a re-approval attempt that itself FAILS (a real
         FK violation, same mechanism as probe 5) must not wipe that
         reappearance marker -- `_approve_one`'s unclaim-on-failure path
         only ever touches `status`/`last_seen_at`
         (routers/retention_admin.py), so the "this was rejected before"
         history must still be visible afterwards."""
    import services.scheduler as scheduler
    from routers import retention_admin

    admin = make_admin()
    suffix = _suffix()
    cid = _rejected_candidate(db_run, suffix=suffix)
    db_run(scheduler.generate_retention_review)
    item = db_run(
        fetch_one,
        "SELECT id FROM retention_review_items WHERE category = 'rejected_applicant' AND subject_id = $1", cid,
    )
    db_run(
        retention_admin.reject_review_item, item["id"],
        retention_admin.ReviewDecisionRequest(note="wacht nog"),
        current_user={"id": admin["id"], "role": "admin"},
    )
    rejected = db_run(fetch_one, "SELECT status, reappeared_after_rejection_at FROM retention_review_items WHERE id = $1", item["id"])
    assert rejected["status"] == "rejected"
    assert rejected["reappeared_after_rejection_at"] is None  # not yet reappeared

    # The candidate was never actually protected -- still genuinely due,
    # so the very next monthly run reopens the SAME row (WS-E.10's
    # explicit "must not silently return to pending" requirement).
    db_run(scheduler.generate_retention_review)
    reopened = db_run(
        fetch_one,
        "SELECT id, status, reappeared_after_rejection_at FROM retention_review_items WHERE id = $1", item["id"],
    )
    assert reopened["id"] == item["id"]  # same row, not a duplicate
    assert reopened["status"] == "pending"
    assert reopened["reappeared_after_rejection_at"] is not None
    reappeared_at = reopened["reappeared_after_rejection_at"]

    # Force a genuine, unrelated failure on the re-approval attempt: an
    # outreach_drafts row FK-references this same candidate, and the
    # item's action is forced to 'hard_delete' so the DELETE branch hits
    # that FK violation (identical mechanism to probe 5).
    db_run(
        execute,
        "INSERT INTO outreach_drafts (target_type, target_email, target_name, subject, body, status, presented_candidate_id) "
        "VALUES ('client_prospect', $1, 'x', 'x', 'x', 'draft', $2)",
        f"outreach-reapprove-{suffix}@example.com", cid,
    )
    db_run(execute, "UPDATE retention_review_items SET action = 'hard_delete' WHERE id = $1", item["id"])

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    with pytest.raises(Exception):
        db_run(
            retention_admin.approve_review_item, item["id"], payload,
            current_user={"id": admin["id"], "role": "admin"},
        )

    after_failed_reapprove = db_run(
        fetch_one,
        "SELECT status, reappeared_after_rejection_at FROM retention_review_items WHERE id = $1", item["id"],
    )
    assert after_failed_reapprove["status"] == "pending", (
        "M2's unclaim-on-failure should restore the pre-claim status ('pending'), "
        f"got {after_failed_reapprove['status']!r}"
    )
    assert after_failed_reapprove["reappeared_after_rejection_at"] == reappeared_at, (
        "a failed re-approval attempt wiped/changed reappeared_after_rejection_at -- "
        "the visible 'this was rejected before' history must survive a failed action"
    )

    candidate_row = db_run(fetch_one, "SELECT id FROM candidates WHERE id = $1", cid)
    assert candidate_row is not None  # never actually deleted -- the FK violation rolled it back
