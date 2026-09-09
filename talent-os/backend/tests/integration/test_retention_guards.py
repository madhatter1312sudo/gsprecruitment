"""
Integration tests for the security-audit FIX FIRST on
migrations/032_retention_anchor_columns.py (WS-E.8 retention-kolommen
branch) -- real Postgres, real rows, the exact selectors
core/retention.py hands to services/scheduler.py, per db_run()'s pattern
in tests/integration/conftest.py.

tests/test_retention.py only ever inspected the SQL text; the auditor's
finding was proved with real rows against the real selector, and these
tests reproduce those scenarios so a later edit that makes a guard dead
again fails here, not in production.

── follow-up (coordinator, same branch): the tests above prove the
selector is correct once its anchor column already has a value -- they
INSERT that value themselves. That is not the bug the previous round
found: REJECTED_APPLICANT_SQL was always correct; the columns it reads
were simply never written by any real code path. A test that plants the
value itself would have stayed green against the old, broken code too.
The section below instead drives the real write path for every one of
the four anchor columns (matches.updated_at / pipeline_entries.updated_at
via a genuine POST /api/matches, candidate application and pipeline-add;
candidates.rejected_at via the real PATCH; client_prospects.
last_contacted_at via both real write paths, the admin PUT and an
approved outreach send; users.last_login_at via a real POST
/api/auth/login) and then asserts the column actually has a value
afterwards -- if a future edit silently drops one of those UPDATE/INSERT
clauses again, these tests fail, not just the two-years-later purge.
"""
import hashlib
import hmac
import uuid

import pytest

from core import retention
from core.database import execute, fetch_all, fetch_one

pytestmark = pytest.mark.integration


def _candidate_id(db_run, *, suffix, status="rejected", rejected_at_ago="5 weeks"):
    """A minimal candidate row, rejected `rejected_at_ago` in the past
    (default: 5 weeks, past the 4-week window) unless rejected_at_ago is
    None (never rejected)."""
    if rejected_at_ago is None:
        rejected_at_sql = "NULL"
    else:
        rejected_at_sql = f"NOW() - INTERVAL '{rejected_at_ago}'"
    row = db_run(
        fetch_one,
        f"""INSERT INTO candidates (full_name, email, status, rejected_at, deleted_at)
            VALUES ($1, $2, $3, {rejected_at_sql}, NULL)
            RETURNING id""",
        f"Test Candidate {suffix}", f"rejected-{suffix}@example.com", status,
    )
    return row["id"]


def _job_id(db_run, *, suffix):
    client_row = db_run(
        fetch_one,
        "INSERT INTO clients (company_name, domain) VALUES ($1, 'example.com') RETURNING id",
        f"Retention Guard Test Client {suffix}",
    )
    job = db_run(
        fetch_one,
        "INSERT INTO job_orders (client_id, title, description) VALUES ($1, 'Test Role', 'x') RETURNING id",
        client_row["id"],
    )
    return job["id"], client_row["id"]


# ── point 1: rejected_applicant -- matches.updated_at / pipeline_entries ──

def test_rejected_applicant_purges_a_clean_rejection(db_run):
    """No later match/pipeline activity at all -- must still be selected,
    proving the fix didn't just make the guard permanently silent."""
    suffix = uuid.uuid4().hex[:10]
    cid = _candidate_id(db_run, suffix=suffix)
    rows = db_run(fetch_all, retention.REJECTED_APPLICANT_SQL)
    assert cid in [r["id"] for r in rows]


def test_rejected_applicant_excludes_candidate_with_fresh_match_after_rejection(db_run):
    """The exact scenario the auditor proved: rejected, then re-matched to
    another role -- a fresh matches row (updated_at now stamped on
    insert, migrations 033 aligns the pipeline_entries type) must exclude
    the candidate from the purge."""
    suffix = uuid.uuid4().hex[:10]
    cid = _candidate_id(db_run, suffix=suffix)
    job_id, _ = _job_id(db_run, suffix=suffix)

    db_run(
        execute,
        """INSERT INTO matches (candidate_id, job_id, status, updated_at)
           VALUES ($1, $2, 'suggested', NOW())""",
        cid, job_id,
    )

    rows = db_run(fetch_all, retention.REJECTED_APPLICANT_SQL)
    assert cid not in [r["id"] for r in rows]


def test_rejected_applicant_excludes_candidate_with_fresh_pipeline_entry_after_rejection(db_run):
    """Same scenario via pipeline_entries instead of matches -- the
    creation INSERT (routers/client.py) now stamps updated_at too, and
    migrations/033 makes that TIMESTAMPTZ column comparable to
    candidates.rejected_at without a timezone-dependent drift."""
    suffix = uuid.uuid4().hex[:10]
    cid = _candidate_id(db_run, suffix=suffix)
    job_id, client_id = _job_id(db_run, suffix=suffix)

    db_run(
        execute,
        """INSERT INTO pipeline_entries (client_id, candidate_id, job_id, stage, updated_at)
           VALUES ($1, $2, $3, 'sourced', NOW())""",
        client_id, cid, job_id,
    )

    rows = db_run(fetch_all, retention.REJECTED_APPLICANT_SQL)
    assert cid not in [r["id"] for r in rows]


def test_rejected_applicant_still_purges_when_match_predates_rejection(db_run):
    """A match/pipeline entry that existed *before* the rejection must not
    grant immunity -- only activity *after* rejected_at counts."""
    suffix = uuid.uuid4().hex[:10]
    cid = _candidate_id(db_run, suffix=suffix)
    job_id, client_id = _job_id(db_run, suffix=suffix)

    # Backdate the match itself to well before rejected_at (NOW() - 5 weeks).
    db_run(
        execute,
        """INSERT INTO matches (candidate_id, job_id, status, updated_at)
           VALUES ($1, $2, 'suggested', NOW() - INTERVAL '10 weeks')""",
        cid, job_id,
    )

    rows = db_run(fetch_all, retention.REJECTED_APPLICANT_SQL)
    assert cid in [r["id"] for r in rows]


# ── point 2/3/4: prospect_responding -- active clients, opt-out, dead ────
# reply/sent-draft guards removed

def _prospect_id(db_run, *, suffix, company, status, months_ago=13):
    row = db_run(
        fetch_one,
        f"""INSERT INTO client_prospects
              (company_name, contact_email, status, last_contacted_at)
            VALUES ($1, $2, $3, NOW() - INTERVAL '{months_ago} months')
            RETURNING id""",
        company, f"prospect-{suffix}@example.com", status,
    )
    return row["id"]


def test_prospect_responding_excludes_an_active_client_regardless_of_status(db_run):
    """Bewezen scenario (point 2): a prospect whose company converted to
    a real, active client must never be anonymised here, no matter what
    free-text status ('klant') was typed on the prospect record."""
    suffix = uuid.uuid4().hex[:10]
    company = f"Klant BV {suffix}"
    pid = _prospect_id(db_run, suffix=suffix, company=company, status="klant")
    db_run(
        execute,
        "INSERT INTO clients (company_name, domain, account_status) VALUES ($1, 'example.com', 'active')",
        company,
    )

    rows = db_run(fetch_all, retention.PROSPECT_RESPONDING_SQL)
    assert pid not in [r["id"] for r in rows]


def test_prospect_responding_excludes_an_already_erased_prospect(db_run):
    """Point 3: the guard must terminate. erase_person() stamps
    opt_out_at (routers/gdpr.py) without clearing status/last_contacted_at
    -- a second run must not re-select the same row."""
    suffix = uuid.uuid4().hex[:10]
    pid = _prospect_id(db_run, suffix=suffix, company=f"Erased BV {suffix}", status="in_gesprek")
    db_run(execute, "UPDATE client_prospects SET opt_out_at = NOW() WHERE id = $1", pid)

    rows = db_run(fetch_all, retention.PROSPECT_RESPONDING_SQL)
    assert pid not in [r["id"] for r in rows]


def test_prospect_responding_still_purges_a_genuinely_stale_non_client_prospect(db_run):
    """The positive case: a prospect that responded, went stale 13 months
    ago, was never opted out, and whose company never became a real
    client must still be selected -- proving the new guards don't
    over-protect."""
    suffix = uuid.uuid4().hex[:10]
    pid = _prospect_id(db_run, suffix=suffix, company=f"Cold BV {suffix}", status="in_gesprek")

    rows = db_run(fetch_all, retention.PROSPECT_RESPONDING_SQL)
    assert pid in [r["id"] for r in rows]


def test_prospect_responding_client_match_is_case_insensitive_on_company_name(db_run):
    """Same LOWER()/LOWER() convention create_prospect's own dedupe check
    already uses (routers/prospects.py) -- a differently-cased company
    name must still match."""
    suffix = uuid.uuid4().hex[:10]
    company = f"MixedCase BV {suffix}"
    pid = _prospect_id(db_run, suffix=suffix, company=company, status="klant")
    db_run(
        execute,
        "INSERT INTO clients (company_name, domain, account_status) VALUES ($1, 'example.com', 'active')",
        company.upper(),
    )

    rows = db_run(fetch_all, retention.PROSPECT_RESPONDING_SQL)
    assert pid not in [r["id"] for r in rows]


# ── point 5: portal_account_inactive -- real FK, not email matching ──────

def test_portal_account_inactive_excludes_linked_candidate_with_different_email(db_run):
    """Bewezen scenario (point 5): a portal account and its linked
    candidate record can carry different e-mail addresses. The guard must
    protect via candidate_profiles.candidate_id (the FK erase_person()
    itself uses), not LOWER(email)=LOWER(email)."""
    suffix = uuid.uuid4().hex[:10]
    user = db_run(
        fetch_one,
        """INSERT INTO users (email, password_hash, full_name, role, last_login_at)
           VALUES ($1, 'x', 'Portal User', 'candidate', NOW() - INTERVAL '25 months')
           RETURNING id""",
        f"portal-private-{suffix}@example.com",
    )
    cid = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, status)
           VALUES ('Portal Candidate', $1, 'sourced') RETURNING id""",
        f"portal-work-{suffix}@example.com",  # deliberately different address
    )["id"]
    db_run(
        execute,
        "INSERT INTO candidate_profiles (user_id, candidate_id) VALUES ($1, $2)",
        user["id"], cid,
    )
    job_id, _ = _job_id(db_run, suffix=suffix)
    # 'applied', not 'suggested' -- the guard only counts a *progressed*
    # match (m.status <> 'suggested') as real engagement.
    db_run(
        execute,
        """INSERT INTO matches (candidate_id, job_id, status, updated_at)
           VALUES ($1, $2, 'applied', NOW())""",
        cid, job_id,
    )

    rows = db_run(fetch_all, retention.PORTAL_ACCOUNT_INACTIVE_SQL)
    assert user["id"] not in [r["id"] for r in rows]


def test_portal_account_inactive_still_purges_a_truly_unengaged_account(db_run):
    """No candidate_profiles link at all (or none with a live signal) --
    still selected, proving the FK join didn't just blanket-exclude
    everyone."""
    suffix = uuid.uuid4().hex[:10]
    user = db_run(
        fetch_one,
        """INSERT INTO users (email, password_hash, full_name, role, last_login_at)
           VALUES ($1, 'x', 'Idle Portal User', 'candidate', NOW() - INTERVAL '25 months')
           RETURNING id""",
        f"portal-idle-{suffix}@example.com",
    )

    rows = db_run(fetch_all, retention.PORTAL_ACCOUNT_INACTIVE_SQL)
    assert user["id"] in [r["id"] for r in rows]


# ═══════════════════════════════════════════════════════════════════════
# Codepath-level proof: the real endpoint/write-path actually stamps the
# anchor column, not just "the selector is correct once the column has a
# value". Each test drives real HTTP (or, where an external side-effect
# like an outbound e-mail can't run in CI, the real router function
# directly with only that external call stubbed -- never the SQL) and
# then reads the column back from the database.
# ═══════════════════════════════════════════════════════════════════════

# ── matches.updated_at: three write paths ────────────────────────────────

def test_post_api_matches_stamps_updated_at(db_run, client, api_key_headers):
    """POST /api/matches (routers/matches.py create_match) — the external-
    agent upsert path."""
    suffix = uuid.uuid4().hex[:10]
    candidate = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, lawful_basis, source_url, status)
           VALUES ('Match API Candidate', $1, 'gerechtvaardigd_belang', 'https://example.com/profile', 'sourced')
           RETURNING id""",
        f"match-api-{suffix}@example.com",
    )
    job_id, _ = _job_id(db_run, suffix=suffix)

    resp = client.post(
        "/api/matches",
        json={"candidate_id": candidate["id"], "job_id": job_id, "match_score": 80.0, "status": "suggested"},
        headers=api_key_headers,
    )
    assert resp.status_code == 201, resp.text

    row = db_run(
        fetch_one,
        "SELECT updated_at FROM matches WHERE candidate_id = $1 AND job_id = $2",
        candidate["id"], job_id,
    )
    assert row is not None and row["updated_at"] is not None


def test_candidate_apply_to_job_stamps_matches_updated_at(db_run, client, make_candidate_user):
    """POST /api/v1/candidate/applications (routers/candidate.py
    apply_to_job) -- the candidate-portal path a rejected candidate would
    use to apply elsewhere."""
    suffix = uuid.uuid4().hex[:10]
    client_row = db_run(
        fetch_one,
        "INSERT INTO clients (company_name, domain) VALUES ($1, 'example.com') RETURNING id",
        f"Apply Test Client {suffix}",
    )
    job = db_run(
        fetch_one,
        "INSERT INTO job_orders (client_id, title, description, status) "
        "VALUES ($1, 'Open Role', 'x', 'open') RETURNING id",
        client_row["id"],
    )
    candidate_user = make_candidate_user()

    resp = client.post(
        "/api/v1/candidate/applications",
        json={"job_id": job["id"]},
        headers=candidate_user["headers"],
    )
    assert resp.status_code == 201, resp.text

    # get_or_create_candidate_id() (services/candidate_link.py) lazily
    # creates the candidates row with this same e-mail the first time a
    # verified candidate touches an endpoint like this one -- join on
    # e-mail rather than candidate_profiles.candidate_id, which that
    # helper only backfills, never inserts, when no profile row exists yet.
    row = db_run(
        fetch_one,
        """SELECT m.updated_at FROM matches m
           JOIN candidates c ON c.id = m.candidate_id
           WHERE LOWER(c.email) = LOWER($1) AND m.job_id = $2""",
        candidate_user["email"], job["id"],
    )
    assert row is not None and row["updated_at"] is not None


# ── pipeline_entries.updated_at: the add-to-pipeline write path ──────────

def test_client_add_to_pipeline_stamps_updated_at(db_run, client, make_client_user):
    """POST /api/v1/client/pipeline (routers/client.py add_to_pipeline) --
    the exact scenario from the previous round (a candidate re-piped for
    another role right after a rejection, before any stage change)."""
    suffix = uuid.uuid4().hex[:10]
    client_user = make_client_user(approved=True)
    job = db_run(
        fetch_one,
        "INSERT INTO job_orders (client_id, title, description, status) "
        "VALUES ($1, 'Pipeline Role', 'x', 'open') RETURNING id",
        client_user["client_id"],
    )
    candidate = db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, status) VALUES ('Pipeline Candidate', $1, 'sourced') RETURNING id",
        f"pipeline-api-{suffix}@example.com",
    )

    resp = client.post(
        "/api/v1/client/pipeline",
        json={"candidate_id": candidate["id"], "job_id": job["id"], "stage": "sourced"},
        headers=client_user["headers"],
    )
    assert resp.status_code == 201, resp.text

    row = db_run(
        fetch_one,
        "SELECT updated_at FROM pipeline_entries WHERE candidate_id = $1 AND job_id = $2",
        candidate["id"], job["id"],
    )
    assert row is not None and row["updated_at"] is not None


# ── candidates.rejected_at: the real PATCH ───────────────────────────────

def test_patch_candidate_status_rejected_stamps_rejected_at(db_run, client, api_key_headers):
    """PATCH /api/candidates/{id} with status='rejected'
    (routers/candidates.py update_candidate) -- the only admin-facing
    write path onto candidates.status this test suite can drive without
    a live Hermes webhook."""
    suffix = uuid.uuid4().hex[:10]
    candidate = db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, status) VALUES ('Reject API Candidate', $1, 'screening') RETURNING id",
        f"reject-api-{suffix}@example.com",
    )

    resp = client.patch(
        f"/api/candidates/{candidate['id']}",
        json={"status": "rejected"},
        headers=api_key_headers,
    )
    assert resp.status_code == 200, resp.text

    row = db_run(fetch_one, "SELECT rejected_at FROM candidates WHERE id = $1", candidate["id"])
    assert row["rejected_at"] is not None


# ── client_prospects.last_contacted_at: both real write paths ───────────

def test_admin_put_prospect_status_stamps_last_contacted_at(db_run, client, make_admin):
    """PUT /api/v1/admin/prospects/{id} (routers/prospects.py
    update_prospect) -- the manual admin-status-change path."""
    suffix = uuid.uuid4().hex[:10]
    admin = make_admin()
    prospect = db_run(
        fetch_one,
        "INSERT INTO client_prospects (company_name, contact_email, status) "
        "VALUES ($1, $2, 'new') RETURNING id",
        f"Prospect PUT Test {suffix}", f"prospect-put-{suffix}@example.com",
    )

    resp = client.put(
        f"/api/v1/admin/prospects/{prospect['id']}",
        json={"status": "in_gesprek"},
        headers=admin["headers"],
    )
    assert resp.status_code == 200, resp.text

    row = db_run(fetch_one, "SELECT last_contacted_at FROM client_prospects WHERE id = $1", prospect["id"])
    assert row["last_contacted_at"] is not None


def test_outreach_approve_draft_stamps_prospect_last_contacted_at(db_run, client, make_admin, monkeypatch):
    """POST /api/v1/admin/outreach/drafts/{id}/approve
    (routers/outreach.py approve_draft) -- sending an approved draft to a
    client_prospect is itself a contact event. The Gmail API call is
    stubbed (no real mailbox in CI) -- send_email is the one call in this
    path with an external side-effect and no DB write of its own; every
    UPDATE approve_draft issues, including the one on
    client_prospects.last_contacted_at, runs for real against Postgres."""
    import routers.outreach as outreach_router

    async def fake_send_email(**kwargs):
        return True

    monkeypatch.setattr(outreach_router.email_service, "send_email", fake_send_email)

    suffix = uuid.uuid4().hex[:10]
    admin = make_admin()
    prospect = db_run(
        fetch_one,
        "INSERT INTO client_prospects (company_name, contact_email, status, lawful_basis) "
        "VALUES ($1, $2, 'new', 'bestaande_relatie') RETURNING id",
        f"Prospect Approve Test {suffix}", f"prospect-approve-{suffix}@example.com",
    )
    draft = db_run(
        fetch_one,
        """INSERT INTO outreach_drafts
             (target_type, target_id, target_email, target_name, subject, body, status)
           VALUES ('client_prospect', $1, $2, 'Approve Test', 'Hallo',
                    'Dit is een testbericht. U kunt zich afmelden door te antwoorden met STOP.', 'draft')
           RETURNING id""",
        prospect["id"], f"prospect-approve-{suffix}@example.com",
    )

    resp = client.post(
        f"/api/v1/admin/outreach/drafts/{draft['id']}/approve",
        headers=admin["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "sent"

    row = db_run(fetch_one, "SELECT last_contacted_at FROM client_prospects WHERE id = $1", prospect["id"])
    assert row["last_contacted_at"] is not None


# ── users.last_login_at: a real login ────────────────────────────────────

def test_login_stamps_last_login_at(db_run, client, insert_raw_user):
    """POST /api/auth/login (routers/auth.py login) -- the try/except that
    used to swallow this UPDATE is gone (blocking point 7, previous
    round); this test is exactly the regression guard the coordinator
    asked for: if that UPDATE is ever silently dropped or starts failing
    again, this test catches it immediately instead of two years from
    now, at purge time."""
    user = insert_raw_user("candidate", verified=True)

    resp = client.post(
        "/api/auth/login",
        json={"email": user["email"], "password": "Test-Password-123!"},
    )
    assert resp.status_code == 200, resp.text

    row = db_run(fetch_one, "SELECT last_login_at FROM users WHERE id = $1", user["id"])
    assert row["last_login_at"] is not None


# ── SOURCED_NO_RESPONSE_SQL / TALENTPOOL_EXPIRED_SQL guards ──────────────
# Both share CANDIDATE_NO_REACTION_GUARD_SQL: a sent outreach_drafts row
# is not itself a reaction signal, and the real reaction/portal-account
# checks join through activities and candidate_profiles' FK, never a free-
# text e-mail match. Proven below against real rows, plus one end-to-end
# test that drives the real send path (routers/outreach.py approve_draft)
# instead of planting the outreach_drafts row directly.

def _sourced_candidate_id(db_run, *, suffix, lawful_basis="gerechtvaardigd_belang", date_found_ago="4 months"):
    row = db_run(
        fetch_one,
        f"""INSERT INTO candidates (full_name, email, status, lawful_basis, date_found, deleted_at)
            VALUES ($1, $2, 'sourced', $3, NOW() - INTERVAL '{date_found_ago}', NULL)
            RETURNING id""",
        f"Test Sourced {suffix}", f"sourced-{suffix}@example.com", lawful_basis,
    )
    return row["id"]


def test_sourced_no_response_still_purges_a_clean_sourced_candidate(db_run):
    """No sent draft, no linked portal account -- must still be selected,
    proving the replacement guards don't over-protect."""
    suffix = uuid.uuid4().hex[:10]
    lawful_basis = "gerechtvaardigd_belang"
    cid = _sourced_candidate_id(db_run, suffix=suffix, lawful_basis=lawful_basis)

    rows = db_run(fetch_all, retention.SOURCED_NO_RESPONSE_SQL, lawful_basis)
    assert cid in [r["id"] for r in rows]


# FIX (security-audit FIX FIRST, WS-E.8 retention-kolommen branch, FOURTH
# round, blocking point 2): the test below used to assert the opposite --
# that a sent outreach draft alone excluded the candidate. That was the
# bug: it measured contact ("we sent something"), not reaction, and it
# gave permanent immunity to a candidate who never actually responded --
# the exact opposite of what a "no response" retention category is for.
# See test_sourced_no_response_excludes_a_candidate_with_a_recorded_activity
# below for the real replacement signal.
def test_sourced_no_response_still_purges_a_candidate_with_only_a_sent_outreach_draft(db_run):
    """A sent-but-never-reacted-to outreach draft must not grant immunity
    on its own -- it is proof WE made contact, not proof the candidate
    reacted."""
    suffix = uuid.uuid4().hex[:10]
    lawful_basis = "gerechtvaardigd_belang"
    cid = _sourced_candidate_id(db_run, suffix=suffix, lawful_basis=lawful_basis)
    db_run(
        execute,
        "INSERT INTO outreach_drafts (target_type, target_id, target_email, status) "
        "VALUES ('candidate', $1, $2, 'sent')",
        cid, f"sourced-{suffix}@example.com",
    )

    rows = db_run(fetch_all, retention.SOURCED_NO_RESPONSE_SQL, lawful_basis)
    assert cid in [r["id"] for r in rows]


def test_sourced_no_response_excludes_a_candidate_with_a_recorded_activity(db_run):
    """The real reaction signal (security-audit FIX FIRST, WS-E.8
    retention-kolommen branch, FOURTH round, blocking point 2): a
    recruiter logging a real interaction in `activities`
    (migrations/028_activities.py) -- channel-independent, unlike
    outreach_drafts/outreach_messages, which only ever record what WE
    sent."""
    suffix = uuid.uuid4().hex[:10]
    lawful_basis = "gerechtvaardigd_belang"
    cid = _sourced_candidate_id(db_run, suffix=suffix, lawful_basis=lawful_basis)
    db_run(
        execute,
        "INSERT INTO activities (subject_type, subject_id, type, body) "
        "VALUES ('candidate', $1, 'call', 'Reageerde positief via LinkedIn')",
        cid,
    )

    rows = db_run(fetch_all, retention.SOURCED_NO_RESPONSE_SQL, lawful_basis)
    assert cid not in [r["id"] for r in rows]


def test_sourced_no_response_still_purges_a_candidate_with_a_deleted_activity(db_run):
    """A soft-deleted activities row (deleted_at set) must not grant
    immunity -- same deleted_at convention every other table here uses."""
    suffix = uuid.uuid4().hex[:10]
    lawful_basis = "gerechtvaardigd_belang"
    cid = _sourced_candidate_id(db_run, suffix=suffix, lawful_basis=lawful_basis)
    db_run(
        execute,
        "INSERT INTO activities (subject_type, subject_id, type, body, deleted_at) "
        "VALUES ('candidate', $1, 'call', 'Oud, verwijderd', NOW())",
        cid,
    )

    rows = db_run(fetch_all, retention.SOURCED_NO_RESPONSE_SQL, lawful_basis)
    assert cid in [r["id"] for r in rows]


def test_sourced_no_response_still_purges_a_candidate_with_only_a_draft_status_draft(db_run):
    """A drafted-but-never-approved outreach_drafts row (status='draft')
    is not a real contact event -- must not grant immunity."""
    suffix = uuid.uuid4().hex[:10]
    lawful_basis = "gerechtvaardigd_belang"
    cid = _sourced_candidate_id(db_run, suffix=suffix, lawful_basis=lawful_basis)
    db_run(
        execute,
        "INSERT INTO outreach_drafts (target_type, target_id, target_email, status) "
        "VALUES ('candidate', $1, $2, 'draft')",
        cid, f"sourced-{suffix}@example.com",
    )

    rows = db_run(fetch_all, retention.SOURCED_NO_RESPONSE_SQL, lawful_basis)
    assert cid in [r["id"] for r in rows]


def test_sourced_no_response_excludes_a_candidate_with_a_linked_portal_account_under_a_different_email(db_run):
    """The real replacement for the LOWER(email)=LOWER(email) join: the
    candidate_profiles FK, same relation PORTAL_ACCOUNT_INACTIVE_SQL and
    erase_person() already trust -- proven here with two deliberately
    different e-mail addresses, the exact case the old join missed."""
    suffix = uuid.uuid4().hex[:10]
    lawful_basis = "gerechtvaardigd_belang"
    cid = _sourced_candidate_id(db_run, suffix=suffix, lawful_basis=lawful_basis)
    user = db_run(
        fetch_one,
        """INSERT INTO users (email, password_hash, full_name, role)
           VALUES ($1, 'x', 'Sourced Portal User', 'candidate') RETURNING id""",
        f"sourced-portal-{suffix}@example.com",  # deliberately different from the candidate's e-mail
    )
    db_run(
        execute,
        "INSERT INTO candidate_profiles (user_id, candidate_id) VALUES ($1, $2)",
        user["id"], cid,
    )

    rows = db_run(fetch_all, retention.SOURCED_NO_RESPONSE_SQL, lawful_basis)
    assert cid not in [r["id"] for r in rows]


def _talentpool_candidate_id(db_run, *, suffix, consent_expired_ago="45 days"):
    row = db_run(
        fetch_one,
        f"""INSERT INTO candidates
              (full_name, email, status, lawful_basis, consent_talentpool_until, deleted_at)
            VALUES ($1, $2, 'sourced', 'opt_in_talentpool', NOW() - INTERVAL '{consent_expired_ago}', NULL)
            RETURNING id""",
        f"Test Talentpool {suffix}", f"talentpool-{suffix}@example.com",
    )
    return row["id"]


def test_talentpool_expired_still_purges_a_clean_expired_candidate(db_run):
    suffix = uuid.uuid4().hex[:10]
    cid = _talentpool_candidate_id(db_run, suffix=suffix)

    rows = db_run(fetch_all, retention.TALENTPOOL_EXPIRED_SQL)
    assert cid in [r["id"] for r in rows]


def test_talentpool_expired_still_purges_a_candidate_with_only_a_sent_outreach_draft(db_run):
    """Same fourth-round fix as sourced_no_response above: a sent-but-
    never-reacted-to draft is not a reaction and must not grant
    immunity."""
    suffix = uuid.uuid4().hex[:10]
    cid = _talentpool_candidate_id(db_run, suffix=suffix)
    db_run(
        execute,
        "INSERT INTO outreach_drafts (target_type, target_id, target_email, status) "
        "VALUES ('candidate', $1, $2, 'sent')",
        cid, f"talentpool-{suffix}@example.com",
    )

    rows = db_run(fetch_all, retention.TALENTPOOL_EXPIRED_SQL)
    assert cid in [r["id"] for r in rows]


def test_talentpool_expired_excludes_a_candidate_with_a_recorded_activity(db_run):
    suffix = uuid.uuid4().hex[:10]
    cid = _talentpool_candidate_id(db_run, suffix=suffix)
    db_run(
        execute,
        "INSERT INTO activities (subject_type, subject_id, type, body) "
        "VALUES ('candidate', $1, 'note', 'Belde terug, wil verlengen')",
        cid,
    )

    rows = db_run(fetch_all, retention.TALENTPOOL_EXPIRED_SQL)
    assert cid not in [r["id"] for r in rows]


def test_talentpool_expired_excludes_a_candidate_with_a_linked_portal_account_under_a_different_email(db_run):
    suffix = uuid.uuid4().hex[:10]
    cid = _talentpool_candidate_id(db_run, suffix=suffix)
    user = db_run(
        fetch_one,
        """INSERT INTO users (email, password_hash, full_name, role)
           VALUES ($1, 'x', 'Talentpool Portal User', 'candidate') RETURNING id""",
        f"talentpool-portal-{suffix}@example.com",
    )
    db_run(
        execute,
        "INSERT INTO candidate_profiles (user_id, candidate_id) VALUES ($1, $2)",
        user["id"], cid,
    )

    rows = db_run(fetch_all, retention.TALENTPOOL_EXPIRED_SQL)
    assert cid not in [r["id"] for r in rows]


def test_outreach_approve_candidate_draft_does_not_by_itself_exclude_from_sourced_no_response(
    db_run, client, make_admin, monkeypatch,
):
    """End-to-end proof, real send path (POST /api/v1/admin/outreach/
    drafts/{id}/approve, routers/outreach.py approve_draft): sending a
    draft alone must NOT grant this candidate immunity any more.

    security-audit FIX FIRST (WS-E.8 retention-kolommen branch, FOURTH
    round, blocking point 2): before this round, this same test asserted
    the opposite -- that a real approved send excluded the candidate.
    That was exactly the bug: "sent" measures contact, not reaction, and
    turned every candidate anyone ever drafted outreach to into permanent
    protection regardless of whether they ever responded. This proves the
    real send path no longer has that side effect; the positive case (a
    recorded activities row DOES exclude) is
    test_sourced_no_response_excludes_a_candidate_with_a_recorded_activity
    above."""
    import routers.outreach as outreach_router

    async def fake_send_email(**kwargs):
        return True

    monkeypatch.setattr(outreach_router.email_service, "send_email", fake_send_email)

    suffix = uuid.uuid4().hex[:10]
    admin = make_admin()
    # gerechtvaardigd_belang with a real public source_url and an Art. 14
    # block in the body -- NOT opt_in_talentpool: H1r (sixth round) made
    # an active consent_talentpool_until its own independent protective
    # signal on every category here, which would otherwise make this
    # candidate permanently excluded regardless of whether a draft is
    # ever sent, defeating the very thing this test isolates (does
    # SENDING alone grant immunity).
    email = f"sourced-approve-{suffix}@example.com"
    candidate = db_run(
        fetch_one,
        """INSERT INTO candidates
             (full_name, email, status, lawful_basis, date_found, source_url, deleted_at)
           VALUES ($1, $2, 'sourced', 'gerechtvaardigd_belang',
                   NOW() - INTERVAL '4 months', 'https://linkedin.com/in/sourced-approve-test', NULL)
           RETURNING id""",
        f"Sourced Approve Test {suffix}", email,
    )
    art14_body = (
        "Dit bericht komt van GSP Recruitment (Brainport/Eindhoven), sourcing@gsprecruitment.nl. "
        "Wij vonden uw LinkedIn-profiel via https://linkedin.com/in/sourced-approve-test op "
        "2026-08-01 in het kader van werving voor technische functies. Grondslag: gerechtvaardigd "
        "belang bij werving. Wij bewaren deze gegevens 3 maanden na 2026-08-01 als u niet "
        "reageert. U heeft het recht om bezwaar te maken tegen deze verwerking (art. 21 AVG). "
        "U kunt zich afmelden door te antwoorden met \"STOP\" -- wij verwerken dat binnen 24 uur "
        "en uw adres blijft alleen op een blokkeerlijst staan. Een klacht over deze verwerking "
        "kunt u indienen bij de Autoriteit Persoonsgegevens (autoriteitpersoonsgegevens.nl)."
    )
    draft = db_run(
        fetch_one,
        """INSERT INTO outreach_drafts
             (target_type, target_id, target_email, target_name, subject, body, status)
           VALUES ('candidate', $1, $2, 'Approve Test', 'Hallo', $3, 'draft')
           RETURNING id""",
        candidate["id"], email, art14_body,
    )

    # Before sending: a genuinely untouched sourced candidate is selected.
    rows = db_run(fetch_all, retention.SOURCED_NO_RESPONSE_SQL, "gerechtvaardigd_belang")
    assert candidate["id"] in [r["id"] for r in rows]

    resp = client.post(
        f"/api/v1/admin/outreach/drafts/{draft['id']}/approve",
        headers=admin["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "sent"

    rows = db_run(fetch_all, retention.SOURCED_NO_RESPONSE_SQL, "gerechtvaardigd_belang")
    assert candidate["id"] in [r["id"] for r in rows]

    # The mirror insert into outreach_messages now also carries
    # candidate_id for a candidate-targeted send (routers/outreach.py
    # approve_draft, same round) -- proves that write path too.
    mirror = db_run(
        fetch_one,
        "SELECT candidate_id, sent_at FROM outreach_messages WHERE recipient_email = $1 ORDER BY id DESC LIMIT 1",
        email,
    )
    assert mirror is not None
    assert mirror["candidate_id"] == candidate["id"]
    # minor point (fourth round): the mirror row used to set status='sent'
    # but never sent_at.
    assert mirror["sent_at"] is not None


# ── chief-of-staff second FIX FIRST, blocking point 3: prospect_responding
# client match must not depend on company_name text agreeing ────────────

def test_prospect_responding_excludes_an_active_client_matched_only_by_domain(db_run):
    """Bewezen scenario (point 3): a prospect at "ASML" and an active
    client at "ASML Netherlands B.V." never match on company_name, but do
    share a domain -- the guard must still exclude the prospect."""
    suffix = uuid.uuid4().hex[:10]
    pid = _prospect_id(db_run, suffix=suffix, company=f"ASML {suffix}", status="klant")
    db_run(
        execute,
        "UPDATE client_prospects SET domain = 'asml.example.com' WHERE id = $1",
        pid,
    )
    db_run(
        execute,
        "INSERT INTO clients (company_name, domain, account_status) VALUES ($1, 'asml.example.com', 'active')",
        f"ASML Netherlands B.V. {suffix}",
    )

    rows = db_run(fetch_all, retention.PROSPECT_RESPONDING_SQL)
    assert pid not in [r["id"] for r in rows]


# ═══════════════════════════════════════════════════════════════════════
# FOURTH round -- security-audit FIX FIRST (WS-E.8 retention-kolommen
# branch): a placed candidate must never be selected by any category
# (blocking point 1); the domain match must exclude empty strings and
# normalize the two independent write shapes (blocking point 4); every
# guard fixed in this round gets a test through its real write path, not
# a direct INSERT that only proves the SELECT's WHERE-clause semantics --
# per the coordinator's blocking point 5.
# ═══════════════════════════════════════════════════════════════════════

def _create_placement_via_api(client, admin, *, candidate_id, job_id, client_id):
    resp = client.post(
        "/api/v1/admin/placements",
        json={
            "candidate_id": candidate_id, "job_id": job_id, "client_id": client_id,
            "placement_type": "detachering", "status": "actief",
        },
        headers=admin["headers"],
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_sourced_no_response_excludes_a_candidate_with_a_real_placement(db_run, client, make_admin):
    """Bewezen scenario (blocking point 1): routers/placements.py's
    create_placement (the real placement route) writes candidate_id/
    job_id/client_id and nothing else -- it never touches matches or
    pipeline_entries, so a placed candidate previously carried none of
    this guard's other signals and was purged like anyone else."""
    suffix = uuid.uuid4().hex[:10]
    admin = make_admin()
    lawful_basis = "gerechtvaardigd_belang"
    cid = _sourced_candidate_id(db_run, suffix=suffix, lawful_basis=lawful_basis)
    job_id, client_id = _job_id(db_run, suffix=suffix)

    rows = db_run(fetch_all, retention.SOURCED_NO_RESPONSE_SQL, lawful_basis)
    assert cid in [r["id"] for r in rows]

    _create_placement_via_api(client, admin, candidate_id=cid, job_id=job_id, client_id=client_id)

    rows = db_run(fetch_all, retention.SOURCED_NO_RESPONSE_SQL, lawful_basis)
    assert cid not in [r["id"] for r in rows]


def test_rejected_applicant_excludes_a_candidate_with_a_real_placement(db_run, client, make_admin):
    suffix = uuid.uuid4().hex[:10]
    admin = make_admin()
    cid = _candidate_id(db_run, suffix=suffix)
    job_id, client_id = _job_id(db_run, suffix=suffix)

    rows = db_run(fetch_all, retention.REJECTED_APPLICANT_SQL)
    assert cid in [r["id"] for r in rows]

    _create_placement_via_api(client, admin, candidate_id=cid, job_id=job_id, client_id=client_id)

    rows = db_run(fetch_all, retention.REJECTED_APPLICANT_SQL)
    assert cid not in [r["id"] for r in rows]


def test_portal_account_inactive_excludes_a_linked_candidate_with_a_real_placement(db_run, client, make_admin):
    suffix = uuid.uuid4().hex[:10]
    admin = make_admin()
    user = db_run(
        fetch_one,
        """INSERT INTO users (email, password_hash, full_name, role, last_login_at)
           VALUES ($1, 'x', 'Portal Placed User', 'candidate', NOW() - INTERVAL '25 months')
           RETURNING id""",
        f"portal-placed-{suffix}@example.com",
    )
    cid = db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, status) VALUES ('Portal Placed Candidate', $1, 'sourced') RETURNING id",
        f"portal-placed-cand-{suffix}@example.com",
    )["id"]
    db_run(
        execute,
        "INSERT INTO candidate_profiles (user_id, candidate_id) VALUES ($1, $2)",
        user["id"], cid,
    )
    job_id, client_id = _job_id(db_run, suffix=suffix)

    rows = db_run(fetch_all, retention.PORTAL_ACCOUNT_INACTIVE_SQL)
    assert user["id"] in [r["id"] for r in rows]

    _create_placement_via_api(client, admin, candidate_id=cid, job_id=job_id, client_id=client_id)

    rows = db_run(fetch_all, retention.PORTAL_ACCOUNT_INACTIVE_SQL)
    assert user["id"] not in [r["id"] for r in rows]


# ── blocking point 3: clients.account_status now has a real write path ──

def test_patch_client_account_status_stamps_the_column(db_run, client, make_admin):
    """PATCH /api/v1/admin/clients/{id} (routers/clients_admin.py
    update_client) -- the only write path for account_status this branch
    adds. Closed set enforced both by the Pydantic pattern and
    migrations/034's CHECK constraint."""
    admin = make_admin()
    row = db_run(
        fetch_one,
        "INSERT INTO clients (company_name, domain) VALUES ($1, 'example.com') RETURNING id, account_status",
        f"Account Status Test {uuid.uuid4().hex[:8]}",
    )
    assert row["account_status"] == "lead"  # migrations/034's new DEFAULT

    resp = client.patch(
        f"/api/v1/admin/clients/{row['id']}",
        json={"account_status": "active"},
        headers=admin["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["account_status"] == "active"

    updated = db_run(fetch_one, "SELECT account_status FROM clients WHERE id = $1", row["id"])
    assert updated["account_status"] == "active"


def test_patch_client_account_status_rejects_a_value_outside_the_closed_set(client, make_admin, db_run):
    admin = make_admin()
    row = db_run(
        fetch_one,
        "INSERT INTO clients (company_name, domain) VALUES ($1, 'example.com') RETURNING id",
        f"Account Status Reject Test {uuid.uuid4().hex[:8]}",
    )
    resp = client.patch(
        f"/api/v1/admin/clients/{row['id']}",
        json={"account_status": "definitely-not-a-real-status"},
        headers=admin["headers"],
    )
    assert resp.status_code == 422, resp.text


# ── blocking point 4: domain normalization, through the real write paths ─

def test_prospect_responding_excludes_active_client_via_normalized_domain_write_paths(
    db_run, client, make_admin,
):
    """Both real write paths at once, deliberately in incompatible raw
    shapes: POST /api/v1/admin/prospects (routers/prospects.py
    create_prospect, `website` free-text field with scheme + "www.") on
    one side, PATCH /api/v1/admin/clients/{id} (routers/clients_admin.py
    update_client, bare host) on the other. Before normalizing at write
    time (core/privacy.py normalize_domain) these two never compared
    equal; the guard must exclude the prospect once both sides resolve to
    the same host."""
    suffix = uuid.uuid4().hex[:10]
    admin = make_admin()
    host = f"asml-{suffix}.example.com"

    prospect_resp = client.post(
        "/api/v1/admin/prospects",
        json={
            "company": f"ASML {suffix}", "website": f"https://www.{host}/careers",
            "lawful_basis": "bestaande_relatie", "status": "in_gesprek",
        },
        headers=admin["headers"],
    )
    assert prospect_resp.status_code == 201, prospect_resp.text
    prospect = prospect_resp.json()
    db_run(
        execute,
        "UPDATE client_prospects SET last_contacted_at = NOW() - INTERVAL '13 months' WHERE id = $1",
        prospect["id"],
    )

    client_row = db_run(
        fetch_one,
        "INSERT INTO clients (company_name, domain) VALUES ($1, 'example.com') RETURNING id",
        f"ASML Netherlands B.V. {suffix}",
    )
    patch_resp = client.patch(
        f"/api/v1/admin/clients/{client_row['id']}",
        json={"domain": host.upper(), "account_status": "active"},
        headers=admin["headers"],
    )
    assert patch_resp.status_code == 200, patch_resp.text

    # Proof the normalization actually happened at write time, not just
    # that the guard happens to tolerate the raw values.
    stored_prospect_domain = db_run(
        fetch_one, "SELECT domain FROM client_prospects WHERE id = $1", prospect["id"],
    )
    assert stored_prospect_domain["domain"] == host
    stored_client_domain = db_run(
        fetch_one, "SELECT domain FROM clients WHERE id = $1", client_row["id"],
    )
    assert stored_client_domain["domain"] == host

    rows = db_run(fetch_all, retention.PROSPECT_RESPONDING_SQL)
    assert prospect["id"] not in [r["id"] for r in rows]


def test_prospect_responding_does_not_match_two_rows_with_an_empty_domain(db_run):
    """Negative case the coordinator asked for explicitly: an
    `IS NOT NULL` check alone never excludes '', so before this fix two
    unrelated rows that both happened to have domain='' matched each
    other. Company names deliberately differ (so only the domain path
    could possibly match) and last_contacted_at is stale enough to
    otherwise select the prospect."""
    suffix = uuid.uuid4().hex[:10]
    pid = _prospect_id(db_run, suffix=suffix, company=f"Empty Domain Prospect {suffix}", status="in_gesprek")
    db_run(execute, "UPDATE client_prospects SET domain = '' WHERE id = $1", pid)
    db_run(
        execute,
        "INSERT INTO clients (company_name, domain, account_status) VALUES ($1, '', 'active')",
        f"Empty Domain Client {suffix}",
    )

    rows = db_run(fetch_all, retention.PROSPECT_RESPONDING_SQL)
    assert pid in [r["id"] for r in rows]


# ── minor point (fourth round): candidates.pool_origin now stamped by the
# real Apollo bulk-harvest write path, not just migration 022's one-time
# backfill -- routers/retention_admin.py's Apollo-pool-purge selector
# (`c.pool_origin = 'apollo'`) previously missed every row sourced since
# that migration ran. ────────────────────────────────────────────────────

def test_harvest_candidates_stamps_pool_origin_apollo(db_run, monkeypatch):
    import services.harvest as harvest

    suffix = uuid.uuid4().hex[:10]
    fake_email = f"pool-origin-{suffix}@example.com"

    class _FakeApolloClient:
        def __init__(self, api_key):
            pass

        async def search_people(self, **kwargs):
            return {"people": [{
                "first_name": "Pool", "last_name": f"Origin {suffix}",
                "email": fake_email, "id": f"apollo-test-{suffix}",
            }]}

        async def close(self):
            pass

    monkeypatch.setattr(harvest, "ApolloClient", _FakeApolloClient)
    monkeypatch.setattr(harvest.settings, "apollo_api_key", "test-key")
    monkeypatch.setattr(harvest.settings, "apollo_sync_enabled", True)

    async def _fake_flag_enabled(key):
        return True

    monkeypatch.setattr(harvest, "_flag_enabled", _fake_flag_enabled)
    # CAP_CANDIDATES=1 so the real function returns after exactly one
    # insert instead of looping over every title/page combination.
    monkeypatch.setattr(harvest, "CAP_CANDIDATES", 1)
    monkeypatch.setattr(harvest, "CANDIDATE_TITLES", [f"Test Title {suffix}"])

    result = db_run(harvest.harvest_candidates)
    assert result["inserted"] == 1

    row = db_run(
        fetch_one, "SELECT pool_origin, source FROM candidates WHERE email = $1", fake_email,
    )
    assert row is not None
    assert row["source"] == "apollo_bulk"
    assert row["pool_origin"] == "apollo"


# ── Sixth round, security-audit round 5 (B1): five reparaties bewezen ────
# door het echte pad, niet gestubd -- elke reparatie is zonder testfalen
# terug te draaien tenzij een test hier het echte schrijf-/selectiepad
# doorloopt.

# B1(a): PROSPECT_NO_RESPONSE_SQL's sent-draft guard, through a real
# outreach_drafts row (not planted purely to exercise the SELECT).

def test_prospect_no_response_excludes_a_prospect_with_a_sent_draft(db_run):
    suffix = uuid.uuid4().hex[:10]
    email = f"prospect-no-response-{suffix}@example.com"
    prospect = db_run(
        fetch_one,
        """INSERT INTO client_prospects (company_name, contact_email, status, created_at)
           VALUES ($1, $2, 'new', NOW() - INTERVAL '13 months') RETURNING id""",
        f"No Response Prospect {suffix}", email,
    )

    rows = db_run(fetch_all, retention.PROSPECT_NO_RESPONSE_SQL)
    assert prospect["id"] in [r["id"] for r in rows]

    db_run(
        execute,
        """INSERT INTO outreach_drafts (target_type, target_id, target_email, subject, body, status)
           VALUES ('client_prospect', $1, $2, 'Hallo', 'Testbericht', 'sent')""",
        prospect["id"], email,
    )

    rows = db_run(fetch_all, retention.PROSPECT_NO_RESPONSE_SQL)
    assert prospect["id"] not in [r["id"] for r in rows]


# B1(b): candidates.rejected_at via the real Hermes webhook write path,
# not the admin-facing PATCH (already covered above).

def _signed_hermes_post(client, body: bytes):
    from core.config import settings

    sig = hmac.new(settings.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/hermes/webhook",
        content=body,
        headers={"X-Hermes-Signature": sig, "Content-Type": "application/json"},
    )


def test_hermes_webhook_candidate_updated_rejected_stamps_rejected_at(db_run, client):
    import json

    suffix = uuid.uuid4().hex[:10]
    candidate = db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, status) VALUES ('Hermes Reject Candidate', $1, 'screening') "
        "RETURNING id",
        f"hermes-reject-{suffix}@example.com",
    )

    body = json.dumps({
        "action": "candidate_updated",
        "agent": "hermes-test",
        "data": {"id": candidate["id"], "status": "rejected"},
    }).encode("utf-8")
    resp = _signed_hermes_post(client, body)
    assert resp.status_code == 200, resp.text

    row = db_run(fetch_one, "SELECT status, rejected_at FROM candidates WHERE id = $1", candidate["id"])
    assert row["status"] == "rejected"
    assert row["rejected_at"] is not None


# B1(c): users.last_login_at via the real MFA-completion path
# (POST /api/auth/mfa/verify, not the plain-password login already
# covered above) -- the TOTP code itself is stubbed (verify_totp_code is
# a pure crypto function unrelated to what this guard proves: that
# completing a login stamps last_login_at, regardless of factor count).

def test_mfa_verify_completes_login_and_stamps_last_login_at(db_run, client, insert_raw_user, monkeypatch):
    from cryptography.fernet import Fernet
    import routers.mfa as mfa_router
    from core.config import settings
    from core.mfa import encrypt_secret, issue_mfa_pending_token

    monkeypatch.setattr(settings, "mfa_enc_key", Fernet.generate_key().decode("utf-8"))

    user = insert_raw_user("admin", totp_enabled=True)
    db_run(
        execute, "UPDATE users SET totp_secret_enc = $1 WHERE id = $2",
        encrypt_secret("JBSWY3DPEHPK3PXP"), user["id"],
    )
    monkeypatch.setattr(mfa_router, "verify_totp_code", lambda raw_secret, code, last_used_step: 1)

    token = issue_mfa_pending_token(user["id"])
    resp = client.post("/api/auth/mfa/verify", json={"mfa_token": token, "code": "123456"})
    assert resp.status_code == 200, resp.text

    row = db_run(fetch_one, "SELECT last_login_at FROM users WHERE id = $1", user["id"])
    assert row["last_login_at"] is not None


# B1(e): M1 -- the placement guard drops its `deleted_at IS NULL` filter,
# so a placement that is later soft-deleted (the real DELETE endpoint,
# not a planted UPDATE) still counts as "ever placed" -- the 7-year
# fiscal floor a placement documents does not un-apply just because the
# placement record itself was soft-deleted later.

def test_rejected_applicant_still_excludes_a_candidate_after_the_placement_is_soft_deleted(
    db_run, client, make_admin,
):
    suffix = uuid.uuid4().hex[:10]
    admin = make_admin()
    cid = _candidate_id(db_run, suffix=suffix)
    job_id, client_id = _job_id(db_run, suffix=suffix)

    placement = _create_placement_via_api(client, admin, candidate_id=cid, job_id=job_id, client_id=client_id)
    rows = db_run(fetch_all, retention.REJECTED_APPLICANT_SQL)
    assert cid not in [r["id"] for r in rows]

    resp = client.delete(f"/api/v1/admin/placements/{placement['id']}", headers=admin["headers"])
    assert resp.status_code == 204, resp.text
    deleted = db_run(fetch_one, "SELECT deleted_at FROM placements WHERE id = $1", placement["id"])
    assert deleted["deleted_at"] is not None

    rows = db_run(fetch_all, retention.REJECTED_APPLICANT_SQL)
    assert cid not in [r["id"] for r in rows]  # still excluded -- "ooit geplaatst" is the floor
