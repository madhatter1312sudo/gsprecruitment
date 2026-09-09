"""
Integration tests for WS2 (vier admin-defecten), against a real Postgres:

  1. GET /api/v1/admin/leads is a real SQL UNION ALL over
     contact_submissions + quiz_submissions -- ORDER BY/LIMIT/OFFSET
     applied to the union as a whole, so pagination across both tables
     actually is exact (tests/test_ws2_admin_defecten.py already covers
     the SQL-shape/pagination-math unit-level; this exercises it against
     real rows in both tables at once).
  2. GET /api/v1/admin/leads/{source}/{lead_id} returns full detail,
     including the jsonb quiz columns actually round-tripping through
     Postgres (not just a mocked fetch_one).
  3. source_page/referrer_host actually persist end to end through
     POST /api/leads and POST /api/quiz/submit.
  4. GET /api/v1/admin/candidates: a sourced candidate later linked to a
     self-registered portal account (candidate_profiles.candidate_id) is
     listed exactly once, as kind='self-registered' -- not twice, and not
     still 'sourced'.

Real DB because the bug this guards against (WS-C.16 email-join
double-listing, and the earlier Python-side union/pagination) only shows
up against actual overlapping rows -- a stubbed fetch_all can't catch a
real SQL UNION ALL or a real e-mail-collation mismatch.
"""
import uuid

import pytest

pytestmark = pytest.mark.integration


# ── 1 + 2: leads union + detail ────────────────────────────────────────────

def test_leads_union_paginates_across_both_tables_and_totals_exactly(client, make_admin, api_key_headers, db_run):
    from core.database import execute

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]

    # 3 contact_submissions + 2 quiz_submissions, all unread, all with a
    # distinguishable interest/tier so we can tell rows apart in the page.
    for i in range(3):
        db_run(
            execute,
            """INSERT INTO contact_submissions (name, email, message, interest_type)
               VALUES ($1, $2, 'test lead', 'kandidaat')""",
            f"WS2 Contact {suffix}-{i}", f"contact-{suffix}-{i}@example.com",
        )
    for i in range(2):
        db_run(
            execute,
            """INSERT INTO quiz_submissions (email, answers, score, max_score, tier)
               VALUES ($1, '[{"question_id": 1, "answer_index": 0}]'::jsonb, 5, 10, 'starter')""",
            f"quiz-{suffix}-{i}@example.com",
        )

    # unread=true must count all 5 (contact + quiz), and a page of 3
    # must include rows from at least one of the two tables, sliced from
    # one single ordered sequence -- not "first all of A, then all of B".
    r_all = client.get(
        "/api/v1/admin/leads", params={"unread": "true", "limit": 200, "offset": 0},
        headers=admin["headers"],
    )
    assert r_all.status_code == 200
    body_all = r_all.json()
    our_ids = {(it["source"], it["id"]) for it in body_all["items"]
               if suffix in (it.get("email") or "")}
    assert len(our_ids) == 5

    r_page1 = client.get(
        "/api/v1/admin/leads", params={"unread": "true", "limit": 2, "offset": 0},
        headers=admin["headers"],
    )
    r_page2 = client.get(
        "/api/v1/admin/leads", params={"unread": "true", "limit": 2, "offset": 2},
        headers=admin["headers"],
    )
    assert r_page1.status_code == 200 and r_page2.status_code == 200
    assert r_page1.json()["total"] == r_page2.json()["total"] == r_all.json()["total"]
    page1_keys = {(it["source"], it["id"]) for it in r_page1.json()["items"]}
    page2_keys = {(it["source"], it["id"]) for it in r_page2.json()["items"]}
    assert not (page1_keys & page2_keys)  # no overlap between consecutive pages


def test_leads_type_filter_only_matches_contact_submissions(client, make_admin, db_run):
    from core.database import execute

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]

    db_run(
        execute,
        """INSERT INTO contact_submissions (name, email, message, interest_type)
           VALUES ($1, $2, 'test', 'werving_selectie')""",
        f"WS2 Typed {suffix}", f"typed-{suffix}@example.com",
    )
    db_run(
        execute,
        """INSERT INTO quiz_submissions (email, answers, score, max_score, tier)
           VALUES ($1, '[{"question_id": 1, "answer_index": 0}]'::jsonb, 5, 10, 'starter')""",
        f"quiz-typed-{suffix}@example.com",
    )

    r = client.get(
        "/api/v1/admin/leads", params={"type": "werving_selectie", "limit": 200, "offset": 0},
        headers=admin["headers"],
    )
    assert r.status_code == 200
    emails = {it["email"] for it in r.json()["items"]}
    assert f"typed-{suffix}@example.com" in emails
    assert f"quiz-typed-{suffix}@example.com" not in emails
    assert all(it["source"] == "contact_submissions" for it in r.json()["items"]
               if it["email"] == f"typed-{suffix}@example.com")


def test_lead_detail_contact_and_quiz(client, make_admin, db_run):
    from core.database import execute, fetch_one

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]

    contact_row = db_run(
        fetch_one,
        """INSERT INTO contact_submissions (name, email, company, phone, message, interest_type, source_page, referrer_host)
           VALUES ($1, $2, 'Acme BV', '+31600000000', 'hallo daar', 'kandidaat', '/vacatures/1', 'google.com')
           RETURNING id""",
        f"WS2 Detail {suffix}", f"detail-{suffix}@example.com",
    )
    r = client.get(f"/api/v1/admin/leads/contact_submissions/{contact_row['id']}", headers=admin["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "contact_submissions"
    assert body["company"] == "Acme BV"
    assert body["source_page"] == "/vacatures/1"
    assert body["referrer_host"] == "google.com"

    quiz_row = db_run(
        fetch_one,
        """INSERT INTO quiz_submissions (email, answers, score, max_score, tier, domain_scores, source_page, referrer_host)
           VALUES ($1, '[{"question_id": 1, "answer_index": 2}]'::jsonb, 7, 10, 'gevorderd',
                   '{"embedded": 7}'::jsonb, '/quiz', 'linkedin.com')
           RETURNING id""",
        f"quiz-detail-{suffix}@example.com",
    )
    r2 = client.get(f"/api/v1/admin/leads/quiz_submissions/{quiz_row['id']}", headers=admin["headers"])
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["source"] == "quiz_submissions"
    assert body2["answers"] == [{"question_id": 1, "answer_index": 2}]
    assert body2["domain_scores"] == {"embedded": 7}
    assert body2["source_page"] == "/quiz"

    r404 = client.get("/api/v1/admin/leads/quiz_submissions/999999999", headers=admin["headers"])
    assert r404.status_code == 404

    r_bad_source = client.get("/api/v1/admin/leads/candidates/1", headers=admin["headers"])
    assert r_bad_source.status_code == 404


# ── 3: source_page/referrer_host actually persist ─────────────────────────

def test_public_lead_submit_persists_source_page_and_referrer_host(client, make_admin, db_run):
    from core.database import fetch_one

    suffix = uuid.uuid4().hex[:10]
    email = f"public-lead-{suffix}@example.com"
    r = client.post(
        "/api/v1/public/lead",
        json={
            "name": "WS2 Public Lead", "email": email, "message": "interesse",
            "interest_type": "kandidaat",
            "source_page": "/vacatures/42?job=42",
            "referrer_host": "www.linkedin.com",
        },
    )
    assert r.status_code == 201, r.text

    row = db_run(fetch_one, "SELECT source_page, referrer_host FROM contact_submissions WHERE email = $1", email)
    assert row["source_page"] == "/vacatures/42?job=42"
    assert row["referrer_host"] == "www.linkedin.com"


def test_public_lead_submit_rejects_bad_source_page(client):
    suffix = uuid.uuid4().hex[:10]
    r = client.post(
        "/api/v1/public/lead",
        json={
            "name": "WS2 Bad Lead", "email": f"badlead-{suffix}@example.com", "message": "interesse",
            "source_page": "not-a-path",
        },
    )
    assert r.status_code == 422


def test_public_quiz_submit_persists_source_page_and_referrer_host(client, db_run):
    from core.database import fetch_one

    suffix = uuid.uuid4().hex[:10]
    email = f"quiz-public-{suffix}@example.com"
    r = client.post(
        "/api/v1/public/quiz/submit",
        json={
            "email": email,
            "answers": [{"question_id": 1, "answer_index": 0}],
            "source_page": "/quiz?type=kandidaat",
            "referrer_host": "gsprecruitment.nl",
        },
    )
    assert r.status_code == 200, r.text

    row = db_run(fetch_one, "SELECT source_page, referrer_host FROM quiz_submissions WHERE email = $1", email)
    assert row["source_page"] == "/quiz?type=kandidaat"
    assert row["referrer_host"] == "gsprecruitment.nl"


# ── 4: a linked profile is listed once, as self-registered ────────────────

def test_sourced_candidate_later_linked_shows_once_as_self_registered(client, make_admin, make_candidate_user, db_run):
    """A candidate is first sourced via Apollo (candidates row, c.source =
    'apollo'). They later create a portal account and get linked via
    candidate_profiles.candidate_id (WS-C.16 candidate_link.py's normal
    outcome for a matching e-mail). GET /candidates must show exactly one
    row for this person, and it must be kind='self-registered' -- not
    'sourced' (c.source is unchanged) and not listed twice (once from the
    candidates row, once from the unlinked-profile branch)."""
    from core.database import execute, fetch_one

    admin = make_admin()
    suffix = uuid.uuid4().hex[:10]
    email = f"linked-{suffix}@example.com"

    candidate_row = db_run(
        fetch_one,
        """INSERT INTO candidates (full_name, email, current_title, source, updated_at)
           VALUES ('Linked Person', $1, 'Embedded Software Engineer', 'apollo', NOW())
           RETURNING id""",
        email,
    )

    portal_user = make_candidate_user()
    # Force the portal account's e-mail to match the sourced candidate's
    # e-mail (make_candidate_user() mints its own random address) --
    # exactly the scenario candidate_link.py links on.
    db_run(execute, "UPDATE users SET email = $1 WHERE id = $2", email, portal_user["id"])
    db_run(
        execute,
        "INSERT INTO candidate_profiles (user_id, candidate_id) VALUES ($1, $2)",
        portal_user["id"], candidate_row["id"],
    )

    r = client.get(
        "/api/v1/admin/candidates", params={"search": suffix, "limit": 200, "offset": 0},
        headers=admin["headers"],
    )
    assert r.status_code == 200
    items = [it for it in r.json()["items"] if it.get("email") == email]
    assert len(items) == 1, f"expected exactly one row for {email}, got {items}"
    assert items[0]["kind"] == "self-registered"
    assert items[0]["source"] == "apollo"  # provenance untouched
    assert items[0]["candidate_id"] == candidate_row["id"]

    # The detail route (addressed the way the list itself said to --
    # kind='self-registered', item_id=user_id) must not disagree.
    r_detail = client.get(
        f"/api/v1/admin/candidates/self-registered/{portal_user['id']}", headers=admin["headers"],
    )
    assert r_detail.status_code == 200
    assert r_detail.json()["candidate_id"] == candidate_row["id"]

    # And the sourced-detail route (addressed by candidates.id, same
    # person) must report the same kind as the list, not disagree with it.
    r_sourced_detail = client.get(
        f"/api/v1/admin/candidates/sourced/{candidate_row['id']}", headers=admin["headers"],
    )
    assert r_sourced_detail.status_code == 200
    assert r_sourced_detail.json()["kind"] == "self-registered"
    assert r_sourced_detail.json()["source"] == "apollo"


def test_unlinked_self_registered_still_listed_once(client, make_admin, make_candidate_user, db_run):
    """No sourced candidates row at all -- the ordinary unlinked
    self-registered branch (B, a candidate_profiles row with
    candidate_id still NULL) must still surface the person exactly once,
    unaffected by the new NOT EXISTS dedup guard."""
    from core.database import execute

    admin = make_admin()
    portal_user = make_candidate_user()
    db_run(execute, "INSERT INTO candidate_profiles (user_id) VALUES ($1)", portal_user["id"])

    r = client.get(
        "/api/v1/admin/candidates", params={"search": portal_user["email"].split("@")[0], "limit": 200, "offset": 0},
        headers=admin["headers"],
    )
    assert r.status_code == 200
    items = [it for it in r.json()["items"] if it.get("email") == portal_user["email"]]
    assert len(items) == 1
    assert items[0]["kind"] == "self-registered"
    assert items[0]["candidate_id"] is None
    assert items[0]["user_id"] == portal_user["id"]


# ── item 4/5 sanity: analytics + health stay valid on a fresh-migrated DB ──

def test_admin_analytics_returns_expected_keys(client, make_admin):
    admin = make_admin()
    r = client.get("/api/v1/admin/analytics", headers=admin["headers"])
    assert r.status_code == 200
    body = r.json()
    for key in ("user_growth", "job_fill_rate", "client_retention_rate", "candidate_satisfaction"):
        assert key in body


def test_admin_health_reports_duplicate_profile_links(client, make_admin):
    admin = make_admin()
    r = client.get("/api/v1/admin/health", headers=admin["headers"])
    assert r.status_code == 200
    body = r.json()
    assert "duplicate_profile_links" in body
    assert isinstance(body["duplicate_profile_links"], int)
