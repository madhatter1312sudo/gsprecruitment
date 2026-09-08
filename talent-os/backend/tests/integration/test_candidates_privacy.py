"""
Integration test for FIX 2 (chief-of-staff, ai-pseudonimisering branch):
GET /api/candidates and GET /api/candidates/{id} (X-API-Key, the same key
the external Claude routines use) must never return cv_text, and must
never return a soft-deleted row or a row with withdrawn consent.

Real Postgres, via tests/integration/conftest.py's db_run.
"""
import uuid

import pytest

pytestmark = pytest.mark.integration


def test_list_and_get_exclude_deleted_withdrawn_and_cv_text(db_run, api_key_headers, client):
    from core.database import execute, fetch_one

    suffix = uuid.uuid4().hex[:10]

    visible_email = f"visible-{suffix}@example.com"
    visible = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, cv_text, updated_at)
           VALUES ('Visible Candidate', $1, 'this is my cv text, should never leak', NOW())
           RETURNING id""",
        visible_email,
    )

    deleted_email = f"deleted-{suffix}@example.com"
    deleted = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, cv_text, deleted_at, updated_at)
           VALUES ('Deleted Candidate', $1, 'deleted cv text', NOW(), NOW())
           RETURNING id""",
        deleted_email,
    )

    withdrawn_email = f"withdrawn-{suffix}@example.com"
    withdrawn = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, cv_text, consent_withdrawn_at, updated_at)
           VALUES ('Withdrawn Candidate', $1, 'withdrawn cv text', NOW(), NOW())
           RETURNING id""",
        withdrawn_email,
    )

    try:
        # GET /api/candidates (list)
        resp = client.get("/api/candidates?limit=200", headers=api_key_headers)
        assert resp.status_code == 200
        body = resp.json()
        ids = {row["id"] for row in body}

        assert visible["id"] in ids
        assert deleted["id"] not in ids
        assert withdrawn["id"] not in ids
        for row in body:
            assert "cv_text" not in row

        # GET /api/candidates/{id} for the visible row
        resp = client.get(f"/api/candidates/{visible['id']}", headers=api_key_headers)
        assert resp.status_code == 200
        assert "cv_text" not in resp.json()

        # GET /api/candidates/{id} for the soft-deleted row: 404, not a leak
        resp = client.get(f"/api/candidates/{deleted['id']}", headers=api_key_headers)
        assert resp.status_code == 404

        # GET /api/candidates/{id} for the withdrawn-consent row: 404
        resp = client.get(f"/api/candidates/{withdrawn['id']}", headers=api_key_headers)
        assert resp.status_code == 404
    finally:
        db_run(
            execute,
            "DELETE FROM candidates WHERE id = ANY($1::int[])",
            [visible["id"], deleted["id"], withdrawn["id"]],
        )
