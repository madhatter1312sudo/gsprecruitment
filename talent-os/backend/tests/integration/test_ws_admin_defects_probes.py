"""
WS2 "vier admin-defecten" -- SONDE-OPDRACHT probes, against a real Postgres.

These tests were written WITHOUT looking at any specific fix: they encode
the *expected* behaviour from the ticket/contract only, against the real
endpoints (GET/POST /api/v1/admin/leads, /api/v1/admin/candidates,
/api/v1/admin/analytics, POST /api/v1/public/lead). They are meant to be
run, unmodified, against whatever implementation lands (this worktree's
current code today, a colleague's branch tomorrow) and to go green only
once the real defect is actually fixed -- a red result here is reporting
data, not a test-writing mistake to "fix" by loosening the assertion.

Run in isolation (this file only) against a *fresh*, uniquely-named
database migrated with migrations/000_baseline.py .. 035 plus the new
038_leads_origin.py -- see the orchestration shown in the QA report this
file shipped with. Uses only the public fixtures in
tests/integration/conftest.py (client, db_run, make_admin,
make_candidate_user, api_key_headers) -- no other file is touched.

Five probes, matching the ticket's five numbered items:

  1. GET /api/v1/admin/leads pagination + total + unread filter + a real
     cross-table (contact_submissions UNION quiz_submissions) DESC sort
     on created_at.
  2. GET /api/v1/admin/leads/{source}/{id} detail shape per source, and
     404 for an unknown source.
  3. GET /api/v1/admin/candidates: kind derivation + no double-listing.
  4. POST /api/v1/public/lead: source_page/referrer_host accept + persist
     + reject shapes, including the "stray querystring key" question the
     ticket asks us to take a documented position on (see the comment on
     that test below).
  5. GET /api/v1/admin/analytics: 200, user_growth as an object, three
     percentages present.

Migration 038 is optional at collection time: if `contact_submissions`
has no `source_page` column when this module loads, exactly one
assertion (the "it round-trips into the DB" check in probe 4) is
skipped with a clear reason -- everything else in probe 4 (the pydantic-
level accept/reject validation, which does not depend on the column
existing) still runs and still enforces the full contract.
"""
import uuid
from datetime import datetime, timedelta

import pytest

pytestmark = pytest.mark.integration


# ── shared: does migration 038 exist on this DB yet? ───────────────────────

@pytest.fixture(scope="session")
def lead_origin_columns_present(db_run):
    from core.database import fetch_val

    return bool(
        db_run(
            fetch_val,
            """SELECT 1 FROM information_schema.columns
               WHERE table_name = 'contact_submissions' AND column_name = 'source_page'""",
        )
    )


# ── Probe 1: GET /api/v1/admin/leads -- pagination, total, unread, sort ───
# Deliberately independent of whether the leads tables are actually empty
# before this runs (a genuinely fresh migrated DB has zero rows here, but
# this must not silently start asserting nonsense the moment that stops
# being true -- e.g. this file re-run against an already-used DB, or a
# future test added ahead of this one): every row this test creates gets
# a created_at far in the future (2099), strictly newer than anything a
# normal test run could otherwise insert, so "first N by created_at DESC"
# always means "N of mine" regardless of what else is in the table --
# and the two `total` counts are asserted as a delta over a baseline
# fetched before insertion, not as a hardcoded absolute.

def test_probe1_leads_pagination_total_unread_and_cross_table_sort(client, make_admin, db_run):
    from core.database import execute

    admin = make_admin()

    baseline_total = client.get(
        "/api/v1/admin/leads", params={"limit": 1, "offset": 0}, headers=admin["headers"],
    ).json()["total"]
    baseline_unread = client.get(
        "/api/v1/admin/leads", params={"unread": "true", "limit": 1, "offset": 0}, headers=admin["headers"],
    ).json()["total"]

    # 60 rows total: 35 contact_submissions + 25 quiz_submissions, 20 of
    # the 60 unread (12 contact + 8 quiz) -- spread in blocks of
    # (7 contact, 5 quiz) so the combined sort actually interleaves
    # sources rather than "all of one table, then all of the other".
    # created_at is set explicitly and strictly decreasing by index, so
    # index 0 is the newest row and index 59 the oldest -- this is what
    # the DESC-sort assertions below are checked against.
    base = datetime(2099, 1, 1, 12, 0, 0)
    contact_unread_left = 12
    quiz_unread_left = 8
    rows = []  # (source, created_at, is_read) in insertion/index order
    idx = 0
    for _block in range(5):
        for _ in range(7):
            ts = base - timedelta(seconds=idx)
            unread = contact_unread_left > 0
            if unread:
                contact_unread_left -= 1
            rows.append(("contact", ts, not unread))
            idx += 1
        for _ in range(5):
            ts = base - timedelta(seconds=idx)
            unread = quiz_unread_left > 0
            if unread:
                quiz_unread_left -= 1
            rows.append(("quiz", ts, not unread))
            idx += 1

    assert len(rows) == 60
    assert sum(1 for r in rows if r[0] == "contact") == 35
    assert sum(1 for r in rows if r[0] == "quiz") == 25
    assert sum(1 for r in rows if r[2] is False) == 20  # is_read=False == unread

    suffix = uuid.uuid4().hex[:8]
    for i, (source, ts, is_read) in enumerate(rows):
        if source == "contact":
            db_run(
                execute,
                """INSERT INTO contact_submissions (name, email, message, is_read, created_at)
                   VALUES ($1, $2, 'probe1 lead', $3, $4)""",
                f"Probe1 Contact {suffix}-{i}", f"probe1-contact-{suffix}-{i}@example.com", is_read, ts,
            )
        else:
            db_run(
                execute,
                """INSERT INTO quiz_submissions (email, answers, score, max_score, tier, is_read, created_at)
                   VALUES ($1, '[{"question_id": 1, "answer_index": 0}]'::jsonb, 5, 10, 'starter', $2, $3)""",
                f"probe1-quiz-{suffix}-{i}@example.com", is_read, ts,
            )

    # -- total (as a delta over the pre-insert baseline) + page 1 (20 items,
    # all mine -- 2099 sorts before anything else) --
    r1 = client.get("/api/v1/admin/leads", params={"limit": 20, "offset": 0}, headers=admin["headers"])
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["total"] == baseline_total + 60, body1
    assert len(body1["items"]) == 20, body1

    # -- page 3 (offset 40) also has 20 items -- still entirely mine
    # (indices 40..59), regardless of baseline --
    r3 = client.get("/api/v1/admin/leads", params={"limit": 20, "offset": 40}, headers=admin["headers"])
    assert r3.status_code == 200, r3.text
    body3 = r3.json()
    assert body3["total"] == baseline_total + 60, body3
    assert len(body3["items"]) == 20, body3

    # -- unread=true: total grows by exactly 20, every item is is_read=false --
    r_unread = client.get(
        "/api/v1/admin/leads", params={"unread": "true", "limit": 20, "offset": 0}, headers=admin["headers"],
    )
    assert r_unread.status_code == 200, r_unread.text
    body_unread = r_unread.json()
    assert body_unread["total"] == baseline_unread + 20, body_unread
    assert all(item["is_read"] is False for item in body_unread["items"]), body_unread["items"]

    # -- sort is created_at DESC over BOTH sources combined, not sorted
    # per-table then concatenated: pull all 60 (one page) and check (a)
    # created_at is monotonically non-increasing across the whole
    # sequence, and (b) both sources actually appear in the first page,
    # proving the union -- not just one table -- was sorted.
    r_all = client.get("/api/v1/admin/leads", params={"limit": 60, "offset": 0}, headers=admin["headers"])
    assert r_all.status_code == 200, r_all.text
    items_all = r_all.json()["items"]
    assert len(items_all) == 60
    created_ats = [item["created_at"] for item in items_all]
    assert created_ats == sorted(created_ats, reverse=True), "leads are not sorted by created_at DESC across both tables"
    sources_in_page1 = {item["source"] for item in items_all[:20]}
    assert sources_in_page1 == {"contact_submissions", "quiz_submissions"}, (
        f"expected both sources interleaved in page 1, got only {sources_in_page1} "
        "-- looks like the union is sorted per-table and concatenated, not sorted as one sequence"
    )


# ── Probe 2: lead detail shape per source + 404 for unknown source ────────

def test_probe2_contact_lead_detail_has_message_company_phone(client, make_admin, db_run):
    from core.database import fetch_one, execute

    admin = make_admin()
    suffix = uuid.uuid4().hex[:8]
    email = f"probe2-contact-{suffix}@example.com"
    db_run(
        execute,
        """INSERT INTO contact_submissions (name, email, company, phone, message, interest_type)
           VALUES ($1, $2, 'Voorbeeld BV', '+31612345678', 'Interesse in samenwerking', 'werving_selectie')""",
        f"Probe2 Contact {suffix}", email,
    )
    lead = db_run(fetch_one, "SELECT id FROM contact_submissions WHERE email = $1", email)

    r = client.get(f"/api/v1/admin/leads/contact_submissions/{lead['id']}", headers=admin["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["message"] == "Interesse in samenwerking"
    assert body["company"] == "Voorbeeld BV"
    assert body["phone"] == "+31612345678"


def test_probe2_quiz_lead_detail_has_score_max_score_tier_answers_domain_scores(client, make_admin, db_run):
    from core.database import fetch_one, execute

    admin = make_admin()
    suffix = uuid.uuid4().hex[:8]
    email = f"probe2-quiz-{suffix}@example.com"
    db_run(
        execute,
        """INSERT INTO quiz_submissions (email, answers, score, max_score, tier, domain_scores)
           VALUES ($1, '[{"question_id": 1, "answer_index": 2}, {"question_id": 2, "answer_index": 0}]'::jsonb,
                   7, 10, 'gevorderd', '{"embedded": 80, "cyber": 60}'::jsonb)""",
        email,
    )
    lead = db_run(fetch_one, "SELECT id FROM quiz_submissions WHERE email = $1", email)

    r = client.get(f"/api/v1/admin/leads/quiz_submissions/{lead['id']}", headers=admin["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["score"] == 7
    assert body["max_score"] == 10
    assert body["tier"] == "gevorderd"
    assert body["answers"] == [{"question_id": 1, "answer_index": 2}, {"question_id": 2, "answer_index": 0}]
    assert body["domain_scores"] == {"embedded": 80, "cyber": 60}


def test_probe2_unknown_lead_source_is_404(client, make_admin):
    admin = make_admin()
    r = client.get("/api/v1/admin/leads/not_a_real_table/1", headers=admin["headers"])
    assert r.status_code == 404, r.text


# ── Probe 3: candidates list -- kind derivation + no double-listing ───────

def test_probe3_linked_profile_via_candidate_id_is_self_registered(client, make_admin, make_candidate_user, db_run):
    from core.database import execute, fetch_one

    admin = make_admin()
    tag = uuid.uuid4().hex[:10]
    email = f"probe3-linked-{tag}@example.com"

    candidate_row = db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, source) VALUES ($1, $2, 'apollo') RETURNING id",
        f"Probe3 Linked {tag}", email,
    )
    user = make_candidate_user()
    db_run(execute, "UPDATE users SET email = $1 WHERE id = $2", email, user["id"])
    db_run(
        execute,
        "INSERT INTO candidate_profiles (user_id, candidate_id) VALUES ($1, $2)",
        user["id"], candidate_row["id"],
    )

    r = client.get(
        "/api/v1/admin/candidates", params={"search": tag, "limit": 200, "offset": 0}, headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    items = [it for it in r.json()["items"] if it.get("email") == email]
    assert len(items) == 1, items
    assert items[0]["kind"] == "self-registered", items[0]
    assert items[0]["source"] == "apollo"  # provenance stays untouched


def test_probe3_unlinked_profile_with_matching_candidates_email_listed_once(
    client, make_admin, make_candidate_user, db_run,
):
    """cp.candidate_id stays NULL (never linked), but the person's e-mail
    already has its own `candidates` row (e.g. sourced by Apollo under
    the same address, independently of the portal account). Must appear
    exactly once in the list -- not zero times, not twice (once from the
    candidates row's e-mail fallback, once from the unlinked-profile
    branch)."""
    from core.database import execute, fetch_one

    admin = make_admin()
    tag = uuid.uuid4().hex[:10]
    email = f"probe3-unlinked-{tag}@example.com"

    db_run(
        fetch_one,
        "INSERT INTO candidates (full_name, email, source) VALUES ($1, $2, 'apollo') RETURNING id",
        f"Probe3 UnlinkedMatch {tag}", email,
    )
    user = make_candidate_user()
    db_run(execute, "UPDATE users SET email = $1 WHERE id = $2", email, user["id"])
    db_run(execute, "INSERT INTO candidate_profiles (user_id) VALUES ($1)", user["id"])  # candidate_id left NULL

    r = client.get(
        "/api/v1/admin/candidates", params={"search": tag, "limit": 200, "offset": 0}, headers=admin["headers"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    items = [it for it in body["items"] if it.get("email") == email]
    assert len(items) == 1, f"expected exactly one row for {email}, got {items}"

    # total must match the number of rendered rows for this scoped
    # search (2 people from the two tests above share this file's DB by
    # the time this runs, but each test scopes its own unique `tag`, so
    # this query only ever matches its own 1 row).
    assert body["total"] == len(body["items"]) == 1, body


# ── Probe 4: POST /api/v1/public/lead -- source_page / referrer_host ──────

def _valid_lead_payload(**overrides):
    payload = {
        "name": "Probe4 Tester",
        "email": f"probe4-{uuid.uuid4().hex[:10]}@example.com",
        "message": "Testbericht voor WS2 sonde.",
    }
    payload.update(overrides)
    return payload


def test_probe4_lead_accepts_source_page_and_referrer_host(client):
    payload = _valid_lead_payload(
        source_page="/werkgevers.html?type=detachering",
        referrer_host="www.google.com",
    )
    r = client.post("/api/v1/public/lead", json=payload)
    assert r.status_code == 201, r.text


def test_probe4_lead_source_page_and_referrer_host_are_persisted(
    client, db_run, lead_origin_columns_present,
):
    if not lead_origin_columns_present:
        pytest.skip(
            "migratie 038_leads_origin (source_page/referrer_host kolommen op "
            "contact_submissions) is nog niet aanwezig op deze database -- alleen "
            "deze ene assertie (round-trip in de DB) wordt overgeslagen; de "
            "accept/reject-validatie in de andere probe4-tests hangt niet van "
            "deze migratie af en blijft volledig getest."
        )
    from core.database import fetch_one

    payload = _valid_lead_payload(
        source_page="/werkgevers.html?type=detachering",
        referrer_host="www.google.com",
    )
    r = client.post("/api/v1/public/lead", json=payload)
    assert r.status_code == 201, r.text

    row = db_run(
        fetch_one,
        "SELECT source_page, referrer_host FROM contact_submissions WHERE email = $1",
        payload["email"],
    )
    assert row is not None
    assert row["source_page"] == "/werkgevers.html?type=detachering"
    assert row["referrer_host"] == "www.google.com"


def test_probe4_lead_rejects_source_page_without_leading_slash(client):
    payload = _valid_lead_payload(source_page="werkgevers.html")
    r = client.post("/api/v1/public/lead", json=payload)
    assert r.status_code == 422, r.text


def test_probe4_lead_rejects_source_page_over_200_chars(client):
    payload = _valid_lead_payload(source_page="/" + "a" * 205)
    r = client.post("/api/v1/public/lead", json=payload)
    assert r.status_code == 422, r.text


def test_probe4_lead_rejects_unexpected_source_page_query_key(client):
    """Documented expectation: REJECT (422), not silently ignore.

    source_page is a same-site path the *site itself* appended
    (?type=... on the job-board filter, ?job=... on a vacature page) --
    never arbitrary caller-supplied data, so it can never carry an
    open-redirect-shaped or otherwise attacker-controlled value into the
    DB and back out into an admin's browser. An unrecognised query key
    (e.g. `?evil=<script>`) is exactly the "arbitrary caller-supplied"
    case the field is designed to exclude, so the boundary must be a
    hard reject at submission time, not a silent drop of the value it
    doesn't like -- a silent ignore would still store (and have already
    accepted, with a 2xx) a request whose shape violates the contract,
    which is worse for an admin-facing field like this than telling the
    caller immediately that the request was malformed.
    """
    payload = _valid_lead_payload(source_page="/vacatures/123?evil=xss")
    r = client.post("/api/v1/public/lead", json=payload)
    assert r.status_code == 422, r.text


# ── Probe 5: GET /api/v1/admin/analytics ───────────────────────────────────

def test_probe5_analytics_returns_user_growth_object_and_three_percentages(client, make_admin):
    admin = make_admin()
    r = client.get("/api/v1/admin/analytics", headers=admin["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body.get("user_growth"), dict), body
    for key in ("job_fill_rate", "client_retention_rate", "candidate_satisfaction"):
        assert key in body, body
        assert isinstance(body[key], (int, float)), (key, body[key])
