"""
Integration test for FIX 1 (chief-of-staff, ai-pseudonimisering branch):
GET /api/matches/candidates-for-job/{job_id} must include a talentpool
opt-in candidate even though that row never gets a source_url (see
routers/public.py's confirm_talentpool_optin(), which only sets
lawful_basis='opt_in_talentpool'), and must still exclude a plain Apollo
row that has neither a source_url nor that lawful basis.

Real Postgres (via tests/integration/conftest.py's db_run), because the
existing stubbed-DB test (tests/test_matches_no_pii.py) only inspects the
SQL string, not what an actual filter clause does against real rows.

FIX 3 (chief-of-staff, ai-pseudonimisering branch): this test used to
insert its talentpool row with no consent_talentpool_until at all and
assert it was included -- which locked in exactly the bug FIX 3 closes
(the matching gate accepted lawful_basis='opt_in_talentpool' regardless of
whether that consent was still valid, wider than routers/outreach.py's
send-time gate, which refuses an expired-or-never-set
consent_talentpool_until outright). It now asserts the opposite for that
row, and adds a second talentpool row with a valid future
consent_talentpool_until to prove the intended behaviour: only a
currently-valid opt-in is matchable.
"""
import uuid

import pytest

pytestmark = pytest.mark.integration


def test_talentpool_optin_included_apollo_pool_excluded(db_run, api_key_headers, client):
    from core.database import execute, fetch_one

    client_row = db_run(
        fetch_one,
        "INSERT INTO clients (company_name, domain) VALUES ('Match Test Client', 'example.com') RETURNING id",
    )
    job = db_run(
        fetch_one,
        "INSERT INTO job_orders (client_id, title, description) VALUES ($1, 'Embedded Engineer', 'C++ FreeRTOS') RETURNING id",
        client_row["id"],
    )

    suffix = uuid.uuid4().hex[:10]

    # Talentpool opt-in with a still-valid consent_talentpool_until (12
    # months out, same as what the confirm flow itself writes) -- the only
    # one of the three rows below that should now be matchable.
    valid_email = f"talentpool-valid-{suffix}@example.com"
    talentpool_valid = db_run(
        fetch_one,
        """INSERT INTO candidates
             (full_name, email, current_title, lawful_basis, consent_talentpool_until, updated_at)
           VALUES ('Talentpool Opt-In Valid', $1, 'Embedded Software Engineer',
                   'opt_in_talentpool', NOW() + INTERVAL '12 months', NOW())
           RETURNING id""",
        valid_email,
    )

    # Talentpool opt-in with NO consent_talentpool_until -- e.g. a
    # pre-WS-C.17 row. FIX 3: this must now be excluded, not matched.
    no_consent_email = f"talentpool-noconsent-{suffix}@example.com"
    talentpool_no_consent = db_run(
        fetch_one,
        """INSERT INTO candidates
             (full_name, email, current_title, lawful_basis, updated_at)
           VALUES ('Talentpool Opt-In No Consent Date', $1, 'Embedded Software Engineer',
                   'opt_in_talentpool', NOW())
           RETURNING id""",
        no_consent_email,
    )

    # Talentpool opt-in with an EXPIRED consent_talentpool_until -- must
    # also stay excluded, same as outreach.py's send-time gate.
    expired_email = f"talentpool-expired-{suffix}@example.com"
    talentpool_expired = db_run(
        fetch_one,
        """INSERT INTO candidates
             (full_name, email, current_title, lawful_basis, consent_talentpool_until, updated_at)
           VALUES ('Talentpool Opt-In Expired', $1, 'Embedded Software Engineer',
                   'opt_in_talentpool', NOW() - INTERVAL '1 day', NOW())
           RETURNING id""",
        expired_email,
    )

    # Plain Apollo-bulk row: no source_url, no lawful_basis -- must stay excluded.
    apollo_email = f"apollo-{suffix}@example.com"
    apollo = db_run(
        fetch_one,
        """INSERT INTO candidates
             (full_name, email, current_title, source, updated_at)
           VALUES ('Apollo Pool Row', $1, 'Embedded Software Engineer', 'apollo_bulk', NOW())
           RETURNING id""",
        apollo_email,
    )

    all_ids = [
        talentpool_valid["id"], talentpool_no_consent["id"],
        talentpool_expired["id"], apollo["id"],
    ]

    resp = client.get(f"/api/matches/candidates-for-job/{job['id']}", headers=api_key_headers)
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}

    assert talentpool_valid["id"] in ids
    assert talentpool_no_consent["id"] not in ids
    assert talentpool_expired["id"] not in ids
    assert apollo["id"] not in ids

    db_run(execute, "DELETE FROM candidates WHERE id = ANY($1::int[])", all_ids)
    db_run(execute, "DELETE FROM job_orders WHERE id = $1", job["id"])
    db_run(execute, "DELETE FROM clients WHERE id = $1", client_row["id"])
