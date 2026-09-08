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


# ── chief-of-staff second FIX FIRST (WS-E.8 retention-kolommen branch) ──
# blocking point 1: SOURCED_NO_RESPONSE_SQL and TALENTPOOL_EXPIRED_SQL used
# to carry a dead outreach_messages.replied_at guard (nothing ever writes
# that column) and an unreliable LOWER(email)=LOWER(email) portal-account
# join. Both are now CANDIDATE_NO_REACTION_GUARD_SQL: a sent
# outreach_drafts row, and the real candidate_profiles FK. Proven below
# against real rows, plus one end-to-end test that drives the real send
# path (routers/outreach.py approve_draft) instead of planting the
# outreach_drafts row directly.

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


def test_sourced_no_response_excludes_a_candidate_with_a_sent_outreach_draft(db_run):
    """The real replacement for the dead replied_at guard: a sent (not
    merely drafted) outreach_drafts row targeting this candidate."""
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
    assert cid not in [r["id"] for r in rows]


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


def test_talentpool_expired_excludes_a_candidate_with_a_sent_outreach_draft(db_run):
    suffix = uuid.uuid4().hex[:10]
    cid = _talentpool_candidate_id(db_run, suffix=suffix)
    db_run(
        execute,
        "INSERT INTO outreach_drafts (target_type, target_id, target_email, status) "
        "VALUES ('candidate', $1, $2, 'sent')",
        cid, f"talentpool-{suffix}@example.com",
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


def test_outreach_approve_candidate_draft_excludes_candidate_from_sourced_no_response(
    db_run, client, make_admin, monkeypatch,
):
    """End-to-end proof of the replacement guard's write path (same
    pattern as test_outreach_approve_draft_stamps_prospect_last_contacted_at
    above, candidate side): POST /api/v1/admin/outreach/drafts/{id}/approve
    (routers/outreach.py approve_draft) stamps outreach_drafts.status =
    'sent' for real -- the exact row SOURCED_NO_RESPONSE_SQL's replacement
    guard now reads. Before this round the guard read replied_at, a
    column nothing in this codebase writes; this shows the new guard
    reads a column a real endpoint does write."""
    import routers.outreach as outreach_router

    async def fake_send_email(**kwargs):
        return True

    monkeypatch.setattr(outreach_router.email_service, "send_email", fake_send_email)

    suffix = uuid.uuid4().hex[:10]
    admin = make_admin()
    # opt_in_talentpool: no Art.14 block or public source_url required to
    # pass approve_draft's refusal checks, and consent_talentpool_until
    # in the future so the talentpool-expiry check itself doesn't refuse.
    email = f"sourced-approve-{suffix}@example.com"
    candidate = db_run(
        fetch_one,
        """INSERT INTO candidates
             (full_name, email, status, lawful_basis, date_found, consent_talentpool_until, deleted_at)
           VALUES ($1, $2, 'sourced', 'opt_in_talentpool',
                   NOW() - INTERVAL '4 months', NOW() + INTERVAL '60 days', NULL)
           RETURNING id""",
        f"Sourced Approve Test {suffix}", email,
    )
    draft = db_run(
        fetch_one,
        """INSERT INTO outreach_drafts
             (target_type, target_id, target_email, target_name, subject, body, status)
           VALUES ('candidate', $1, $2, 'Approve Test', 'Hallo',
                    'Dit is een testbericht. U kunt zich afmelden door te antwoorden met STOP.', 'draft')
           RETURNING id""",
        candidate["id"], email,
    )

    # Before sending: a genuinely untouched sourced candidate is selected.
    rows = db_run(fetch_all, retention.SOURCED_NO_RESPONSE_SQL, "opt_in_talentpool")
    assert candidate["id"] in [r["id"] for r in rows]

    resp = client.post(
        f"/api/v1/admin/outreach/drafts/{draft['id']}/approve",
        headers=admin["headers"],
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "sent"

    rows = db_run(fetch_all, retention.SOURCED_NO_RESPONSE_SQL, "opt_in_talentpool")
    assert candidate["id"] not in [r["id"] for r in rows]

    # The mirror insert into outreach_messages now also carries
    # candidate_id for a candidate-targeted send (routers/outreach.py
    # approve_draft, same round) -- proves that write path too.
    mirror = db_run(
        fetch_one,
        "SELECT candidate_id FROM outreach_messages WHERE recipient_email = $1 ORDER BY id DESC LIMIT 1",
        email,
    )
    assert mirror is not None
    assert mirror["candidate_id"] == candidate["id"]


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
