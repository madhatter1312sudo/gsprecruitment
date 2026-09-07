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

    # Talentpool opt-in: no source_url, lawful_basis='opt_in_talentpool' --
    # exactly what routers/public.py's confirm_talentpool_optin() writes.
    talentpool_email = f"talentpool-{suffix}@example.com"
    talentpool = db_run(
        fetch_one,
        """INSERT INTO candidates
             (full_name, email, current_title, lawful_basis, updated_at)
           VALUES ('Talentpool Opt-In', $1, 'Embedded Software Engineer', 'opt_in_talentpool', NOW())
           RETURNING id""",
        talentpool_email,
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

    resp = client.get(f"/api/matches/candidates-for-job/{job['id']}", headers=api_key_headers)
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}

    assert talentpool["id"] in ids
    assert apollo["id"] not in ids

    db_run(execute, "DELETE FROM candidates WHERE id = ANY($1::int[])", [talentpool["id"], apollo["id"]])
    db_run(execute, "DELETE FROM job_orders WHERE id = $1", job["id"])
    db_run(execute, "DELETE FROM clients WHERE id = $1", client_row["id"])
