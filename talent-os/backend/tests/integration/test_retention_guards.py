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
