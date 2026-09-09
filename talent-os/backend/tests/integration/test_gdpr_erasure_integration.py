"""
WS-C.14 integration test: erase_person() (routers/gdpr.py) against a real
DB -- inserts one row per table in tests/test_gdpr_erasure.py's
EXPECTED_TABLES (the Verwerkingsregister's table-coverage list, kept as
the single source of truth for "every table that must be touched"),
runs the actual erasure, and asserts no PII survives anywhere.

tests/test_gdpr_erasure.py already covers erase_person() thoroughly with
a stubbed DB (every SQL statement fired, column-level checks); this test
is the end-to-end companion -- real Postgres, real constraints, real
round-trip -- rather than a duplicate of that unit coverage.
"""
import json
import uuid

import pytest

from tests.test_gdpr_erasure import EXPECTED_TABLES

pytestmark = pytest.mark.integration


def test_erase_person_scrubs_pii_from_every_registered_table(db_run):
    from core import privacy
    from core.database import execute, fetch_all, fetch_one
    from routers.gdpr import erase_person

    email = f"erasure-target-{uuid.uuid4().hex[:10]}@example.com"

    # users -> candidate_profiles (user_id FK) + push_tokens (user_id FK)
    user = db_run(
        fetch_one,
        """INSERT INTO users (email, password_hash, full_name, role, is_verified, password_changed_at)
           VALUES ($1, 'x', 'Erase Me', 'candidate', TRUE, NOW())
           RETURNING id""",
        email,
    )
    db_run(
        execute,
        "INSERT INTO candidate_profiles (user_id, phone, linkedin_url) VALUES ($1, '+31600000000', $2)",
        user["id"], "https://linkedin.com/in/erase-me",
    )
    db_run(
        execute,
        "INSERT INTO push_tokens (user_id, token, platform) VALUES ($1, $2, 'ios')",
        user["id"], f"tok-{uuid.uuid4().hex}",
    )

    # candidates (own email column, independent row) -> pipeline_entries (candidate_id FK)
    # updated_at set explicitly -- see test_client_portal.py's
    # _insert_candidate for why (a separate pre-existing bug, unrelated
    # to erasure, that this test isn't exercising).
    candidate = db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, phone, updated_at) VALUES ('Erase Me', $1, '+31600000001', NOW()) RETURNING id",
        email,
    )
    client_row = db_run(
        fetch_one,
        "INSERT INTO clients (company_name, domain) VALUES ('Erasure Test Client', 'example.com') RETURNING id",
    )
    job = db_run(
        fetch_one,
        "INSERT INTO job_orders (client_id, title) VALUES ($1, 'Embedded Engineer') RETURNING id",
        client_row["id"],
    )
    db_run(
        execute,
        "INSERT INTO pipeline_entries (client_id, candidate_id, job_id, notes) VALUES ($1, $2, $3, $4)",
        client_row["id"], candidate["id"], job["id"], f"Notes mentioning {email} directly",
    )

    # source_page/referrer_host (migrations/038_leads_origin.py) -- a lead
    # submitted with a referrer must have that origin scrubbed on erasure
    # too, not just the obviously-PII columns (security-auditor WS2 finding).
    db_run(
        execute,
        "INSERT INTO quiz_submissions (email, answers, source_page, referrer_host) "
        "VALUES ($1, '{}'::jsonb, '/vacatures?job=7', 'intranet.some-employer.example')",
        email,
    )
    db_run(
        execute,
        "INSERT INTO contact_submissions (name, email, message, source_page, referrer_host) "
        "VALUES ('Erase Me', $1, 'hello', '/vacatures?job=7', 'intranet.some-employer.example')",
        email,
    )
    db_run(
        execute,
        "INSERT INTO outreach_drafts (target_type, target_email, target_name) VALUES ('candidate', $1, 'Erase Me')",
        email,
    )
    db_run(
        execute,
        "INSERT INTO outreach_messages (recipient_email, subject, body) VALUES ($1, 'hi', 'body')",
        email,
    )
    db_run(
        execute,
        "INSERT INTO client_prospects (company_name, contact_name, contact_email) VALUES ($1, 'Erase Me', $2)",
        f"Erasure Prospect Co {uuid.uuid4().hex[:6]}", email,
    )
    db_run(
        execute,
        "INSERT INTO data_subject_requests (request_type, request_email) VALUES ('access', $1)",
        email,
    )
    db_run(
        execute,
        "INSERT INTO audit_log (action, target_type, changes) VALUES ('unit_test_seed', 'person', $1::jsonb)",
        json.dumps({"target_email": email}),
    )

    result = db_run(erase_person, email, None, "WS-C.14 integration test")
    assert result["status"] == "complete", result

    email_hash = privacy.email_hash(email)

    # Sanity: this test's coverage must not silently drift from the
    # Verwerkingsregister's own table-coverage list.
    covered = {
        "candidates", "candidate_profiles", "users", "push_tokens",
        "quiz_submissions", "contact_submissions", "outreach_drafts",
        "outreach_messages", "client_prospects", "pipeline_entries",
        "audit_log", "data_subject_requests", "suppression_list",
    }
    missing = [t for t in EXPECTED_TABLES if t not in covered]
    assert not missing, f"this test doesn't cover: {missing} -- update it alongside EXPECTED_TABLES"

    row = db_run(fetch_one, "SELECT full_name, email, phone FROM candidates WHERE id = $1", candidate["id"])
    assert email.lower() not in (row["email"] or "").lower()
    assert row["full_name"] == "Erased"
    assert row["phone"] is None

    profile = db_run(fetch_one, "SELECT phone, linkedin_url FROM candidate_profiles WHERE user_id = $1", user["id"])
    assert profile["phone"] is None
    assert profile["linkedin_url"] is None

    user_row = db_run(fetch_one, "SELECT full_name, email FROM users WHERE id = $1", user["id"])
    assert email.lower() not in (user_row["email"] or "").lower()
    assert user_row["full_name"] == "Erased"

    tokens = db_run(fetch_all, "SELECT id FROM push_tokens WHERE user_id = $1", user["id"])
    assert tokens == []

    pipeline = db_run(fetch_one, "SELECT notes FROM pipeline_entries WHERE candidate_id = $1", candidate["id"])
    assert pipeline["notes"] is None

    quiz = db_run(fetch_one, "SELECT email FROM quiz_submissions WHERE email ILIKE $1", f"%{email}%")
    assert quiz is None

    contact = db_run(fetch_one, "SELECT name, email FROM contact_submissions WHERE email ILIKE $1", f"%{email}%")
    assert contact is None

    # The rows survive erasure (pseudonymised to erased-<hash prefix>-<id>@
    # erased.invalid, not deleted, see _anonymize_by_id) -- referrer_host
    # must be scrubbed off them too, since it can carry a person's current
    # employer's intranet hostname.
    erased_pattern = f"erased-{email_hash[:16]}-%"
    quiz_row = db_run(fetch_one, "SELECT email, referrer_host FROM quiz_submissions WHERE email ILIKE $1", erased_pattern)
    assert quiz_row is not None, "quiz_submissions row should survive erasure, pseudonymised"
    assert quiz_row["referrer_host"] is None

    contact_row = db_run(fetch_one, "SELECT email, referrer_host FROM contact_submissions WHERE email ILIKE $1", erased_pattern)
    assert contact_row is not None, "contact_submissions row should survive erasure, pseudonymised"
    assert contact_row["referrer_host"] is None

    draft = db_run(fetch_one, "SELECT target_email, target_name FROM outreach_drafts WHERE target_email ILIKE $1", f"%{email}%")
    assert draft is None

    message = db_run(fetch_one, "SELECT recipient_email FROM outreach_messages WHERE recipient_email ILIKE $1", f"%{email}%")
    assert message is None

    prospect = db_run(fetch_one, "SELECT contact_name, contact_email FROM client_prospects WHERE contact_email ILIKE $1", f"%{email}%")
    assert prospect is None

    dsr = db_run(fetch_one, "SELECT request_email FROM data_subject_requests WHERE request_email ILIKE $1", f"%{email}%")
    assert dsr is None

    audit_rows = db_run(fetch_all, "SELECT changes FROM audit_log WHERE changes::text ILIKE $1", f"%{email}%")
    assert audit_rows == [], f"e-mail still present in audit_log after redaction: {audit_rows}"

    suppression = db_run(fetch_one, "SELECT email_hash FROM suppression_list WHERE email_hash = $1", email_hash)
    assert suppression is not None, "erase_person() must add the person to suppression_list"


def test_scoped_erasure_does_not_follow_a_users_row_to_an_unrelated_fk_linked_candidate(db_run):
    """Retention-kolommen round 6 (code-review, WS-E.10 approval queue):
    proves erase_person()'s own scope_table/scope_id narrowing directly,
    bypassing routers/retention_admin.py's guard entirely -- so this
    fails if a future change lets `scope_table` stop actually
    constraining the WS-C.16 extra_ids expansion (the round-6 "R7"
    finding: no test covered this, and forcing scope_table to None in
    routers/retention_admin.py's own call site left the whole suite
    green).

    A `users` row shares its address with the SCOPED subject candidate,
    but its own candidate_profiles.candidate_id FK points at a
    completely different, different-address candidate with an active
    placement (the 7-year fiscal floor). A scoped call
    (scope_table='candidates', scope_id=subject's id) must anonymise
    only the subject candidate -- never follow that FK."""
    from core.database import execute, fetch_one
    from routers.gdpr import erase_person

    subject_email = f"scope-erase-subject-{uuid.uuid4().hex[:10]}@example.com"
    linked_email = f"scope-erase-linked-{uuid.uuid4().hex[:10]}@example.com"

    subject_candidate = db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, deleted_at) VALUES ($1, $2, NULL) RETURNING id",
        "Scope Erase Subject", subject_email,
    )
    linked_candidate = db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, deleted_at) VALUES ($1, $2, NULL) RETURNING id",
        "Scope Erase Linked (unrelated)", linked_email,
    )
    client_row = db_run(
        fetch_one,
        "INSERT INTO clients (company_name, domain, account_status) VALUES ($1, 'example.com', 'active') RETURNING id",
        f"Scope Erase Client {uuid.uuid4().hex[:8]}",
    )
    job = db_run(
        fetch_one, "INSERT INTO job_orders (client_id, title) VALUES ($1, 'Embedded Engineer') RETURNING id",
        client_row["id"],
    )
    db_run(
        execute,
        "INSERT INTO placements (candidate_id, job_id, client_id, placement_type, status) "
        "VALUES ($1, $2, $3, 'werving_selectie', 'actief')",
        linked_candidate["id"], job["id"], client_row["id"],
    )
    portal_user = db_run(
        fetch_one,
        """INSERT INTO users (email, password_hash, full_name, role, is_verified, password_changed_at)
           VALUES ($1, 'x', 'Scope Erase Portal', 'candidate', TRUE, NOW()) RETURNING id""",
        subject_email,
    )
    db_run(
        execute,
        "INSERT INTO candidate_profiles (user_id, candidate_id) VALUES ($1, $2)",
        portal_user["id"], linked_candidate["id"],
    )

    result = db_run(
        erase_person, subject_email, None, "test: scoped erasure R7",
        scope_table="candidates", scope_id=subject_candidate["id"],
    )
    assert result["status"] == "complete"

    subject_row = db_run(fetch_one, "SELECT email, deleted_at FROM candidates WHERE id = $1", subject_candidate["id"])
    assert subject_row["email"] != subject_email  # the scoped subject IS erased
    assert subject_row["deleted_at"] is not None

    linked_row = db_run(fetch_one, "SELECT email, deleted_at FROM candidates WHERE id = $1", linked_candidate["id"])
    assert linked_row["email"] == linked_email  # the FK-linked, unrelated candidate is NOT touched
    assert linked_row["deleted_at"] is None


def test_scoped_erasure_erases_the_subject_despite_a_padded_stored_address(db_run):
    """Round 6 re-check (security-auditor + code-reviewer, WS-E.10
    approval queue): the subject row's own stored address can carry
    whitespace a caller already stripped before comparing (a real gap --
    POST /api/candidates' CandidateCreate.email and POST /api/v1/admin/
    prospects' ProspectCreate.email neither strip nor validate the
    address). A scoped call (scope_table='candidates', scope_id=this
    row's id) must still anonymise THIS row, selected by id alone --
    never by re-deriving "the row with this e-mail" from an address that
    no longer matches what's actually stored, which is exactly how a
    prior round-6 fix (`... AND id = $2` on an e-mail-filtered SELECT)
    silently matched nothing and left the subject untouched."""
    from core.database import execute, fetch_one
    from routers.gdpr import erase_person

    padded_email = f"  scope-erase-padded-{uuid.uuid4().hex[:10]}@example.com  "  # leading AND trailing space
    normalized_email = padded_email.strip().lower()

    subject_candidate = db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, deleted_at) VALUES ($1, $2, NULL) RETURNING id",
        "Scope Erase Padded Subject", padded_email,
    )
    stored = db_run(fetch_one, "SELECT email FROM candidates WHERE id = $1", subject_candidate["id"])
    assert stored["email"] == padded_email, "the padded address must actually be what's stored"

    # erase_person() is called with the NORMALISED address -- exactly what
    # routers/retention_admin.py's _approve_one() now does (privacy.
    # normalize_email() applied before the call) -- never the raw,
    # padded one this row happens to carry.
    result = db_run(
        erase_person, normalized_email, None, "test: scoped erasure despite padded address",
        scope_table="candidates", scope_id=subject_candidate["id"],
    )
    assert result["status"] == "complete"

    subject_row = db_run(fetch_one, "SELECT email, deleted_at FROM candidates WHERE id = $1", subject_candidate["id"])
    assert subject_row["email"] != padded_email  # the scoped subject IS erased, id-only match
    assert subject_row["deleted_at"] is not None
