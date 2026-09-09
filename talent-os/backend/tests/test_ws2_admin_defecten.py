"""
Unit tests for WS2 (vier admin-defecten):

  1. Leads: the contact_submissions + quiz_submissions UNION ALL
     (routers/admin.py's _leads_union_sql / GET /leads / GET /leads/{source}/{id}).
  2. Herkomst: source_page / referrer_host validation (models/schemas.py)
     and their round-trip through routers/public.py's inserts.
  3. Dubbele "sourced": kind_sql (linked profile is the stronger truth)
     and branch B's NOT EXISTS dedup guard (routers/admin.py GET /candidates).
  4. GET /v1/admin/health's duplicate_profile_links signal.

No DB/network needed: core.database's fetch_one/fetch_all/execute/fetch_val
are monkeypatched per-test to a tiny in-memory fake, same style as
tests/test_ws_c4_c5_c10_crm.py. Real-Postgres coverage for the union,
the CASE/JOIN SQL actually evaluating as intended, and the dedup guard
against real overlapping rows lives in
tests/integration/test_ws2_admin_defecten_integration.py.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from pydantic import ValidationError

from models.schemas import LeadSubmit, QuizAnswerItem, QuizSubmitRequest
from core.sources import (
    PORTAL_REGISTRATION, TALENTPOOL_OPTIN, APOLLO, APOLLO_BULK, AGENT,
    KNOWN_SOURCES, SOURCE_FAMILY, source_family,
)


# ── 1a. _leads_union_sql: shape + params ──────────────────────────────────

def test_leads_union_sql_no_filters_unions_both_tables():
    import routers.admin as admin

    sql, params = admin._leads_union_sql(type=None, unread=None)
    assert "FROM contact_submissions" in sql
    assert "FROM quiz_submissions" in sql
    assert "UNION ALL" in sql
    assert params == []
    # Column lists must line up (same names, typed NULLs on the side that
    # lacks a real column) or Postgres would reject the UNION outright.
    assert "score" in sql and "NULL::int AS score" in sql
    assert "NULL::text AS name" in sql  # quiz side has no `name` column
    assert "source_page" in sql and "referrer_host" in sql


def test_leads_union_sql_type_filter_drops_quiz_branch_entirely():
    """quiz_submissions has no interest_type column -- a `type` filter can
    never match a quiz row, so that branch (and the UNION) must be
    skipped outright rather than emitted as a query that can never
    return anything from it."""
    import routers.admin as admin

    sql, params = admin._leads_union_sql(type="kandidaat", unread=None)
    assert "quiz_submissions" not in sql
    assert "UNION ALL" not in sql
    assert "interest_type = $1" in sql
    assert params == ["kandidaat"]


def test_leads_union_sql_unread_filters_both_branches_independently():
    import routers.admin as admin

    sql, params = admin._leads_union_sql(type=None, unread=True)
    # unread=True means is_read = false, on both sides, each with its own
    # placeholder (params are never shared across the two SELECTs).
    assert sql.count("is_read = $") == 2
    assert params == [False, False]


def test_leads_union_sql_unread_false_means_is_read_true():
    import routers.admin as admin

    _, params = admin._leads_union_sql(type=None, unread=False)
    assert params == [True, True]


def test_leads_union_sql_type_and_unread_together():
    import routers.admin as admin

    sql, params = admin._leads_union_sql(type="overig", unread=True)
    assert "quiz_submissions" not in sql
    assert params == ["overig", False]


# ── 1b. GET /leads: pagination is applied to the union as a whole ────────

class _FakeLeadsDB:
    """Records every fetch_val/fetch_all call; fetch_val answers with
    `total`, fetch_all with a slice of `all_items` honouring the trailing
    LIMIT/OFFSET params -- close enough to real Postgres semantics to
    exercise the handler's own param-index bookkeeping without a real
    UNION ALL running underneath."""

    def __init__(self, total, all_items):
        self.total = total
        self.all_items = all_items
        self.calls = []

    async def fetch_val(self, sql, *params):
        self.calls.append(("fetch_val", sql, params))
        return self.total

    async def fetch_all(self, sql, *params):
        self.calls.append(("fetch_all", sql, params))
        limit, offset = params[-2], params[-1]
        return self.all_items[offset:offset + limit]


def test_list_leads_paginates_the_union_not_python_lists(monkeypatch):
    import routers.admin as admin

    items = [{"id": i, "created_at": i} for i in range(5)]
    db = _FakeLeadsDB(total=5, all_items=items)
    monkeypatch.setattr(admin, "fetch_val", db.fetch_val)
    monkeypatch.setattr(admin, "fetch_all", db.fetch_all)

    result = asyncio.run(
        admin.list_leads(type=None, unread=None, limit=2, offset=2, current_user={"id": 1, "role": "admin"})
    )
    assert result["total"] == 5
    assert result["items"] == items[2:4]
    assert result["limit"] == 2 and result["offset"] == 2

    # LIMIT/OFFSET must be the final positional params passed to fetch_all,
    # after any filter params.
    _, sql, params = db.calls[-1]
    assert params[-2:] == (2, 2)


def test_list_leads_rejects_unknown_type(monkeypatch):
    import routers.admin as admin
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            admin.list_leads(type="not-a-real-type", unread=None, limit=50, offset=0,
                              current_user={"id": 1, "role": "admin"})
        )
    assert exc.value.status_code == 400


# ── 1c. GET /leads/{source}/{lead_id}: detail route ───────────────────────

class _FakeDetailDB:
    def __init__(self, row):
        self.row = row

    async def fetch_one(self, sql, *params):
        return dict(self.row) if self.row is not None else None


def test_get_lead_detail_unknown_source_404(monkeypatch):
    import routers.admin as admin
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            admin.get_lead_detail(source="leads", lead_id=1, current_user={"id": 1, "role": "admin"})
        )
    assert exc.value.status_code == 404


def test_get_lead_detail_not_found_404(monkeypatch):
    import routers.admin as admin
    from fastapi import HTTPException

    db = _FakeDetailDB(row=None)
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            admin.get_lead_detail(source="contact_submissions", lead_id=99,
                                   current_user={"id": 1, "role": "admin"})
        )
    assert exc.value.status_code == 404


def test_get_lead_detail_contact_row_passthrough(monkeypatch):
    import routers.admin as admin

    row = {"id": 1, "name": "Jane", "email": "jane@example.com", "message": "hoi",
           "company": None, "phone": None, "interest_type": "kandidaat",
           "is_read": False, "source_page": "/vacatures/1", "referrer_host": "google.com"}
    db = _FakeDetailDB(row=row)
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)

    result = asyncio.run(
        admin.get_lead_detail(source="contact_submissions", lead_id=1, current_user={"id": 1, "role": "admin"})
    )
    assert result["source"] == "contact_submissions"
    assert result["name"] == "Jane"
    assert result["source_page"] == "/vacatures/1"


def test_get_lead_detail_quiz_row_decodes_jsonb_text(monkeypatch):
    """asyncpg returns jsonb as raw JSON text on this connection (no
    codec registered) -- the detail route must json.loads() answers/
    domain_scores rather than handing the caller a JSON *string*."""
    import routers.admin as admin

    row = {
        "id": 7, "email": "a@example.com", "user_id": None,
        "answers": json.dumps([{"question_id": 1, "selected_index": 2}]),
        "score": 8, "max_score": 10, "tier": "gevorderd",
        "domain_scores": json.dumps({"embedded": 8}),
        "is_read": False, "source_page": None, "referrer_host": None,
    }
    db = _FakeDetailDB(row=row)
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)

    result = asyncio.run(
        admin.get_lead_detail(source="quiz_submissions", lead_id=7, current_user={"id": 1, "role": "admin"})
    )
    assert result["answers"] == [{"question_id": 1, "selected_index": 2}]
    assert result["domain_scores"] == {"embedded": 8}
    assert result["source"] == "quiz_submissions"


# ── 2. source_page / referrer_host validation (LeadSubmit + QuizSubmitRequest) ──

_LEAD_KWARGS = dict(name="Jane", email="jane@example.com", message="hoi")


@pytest.mark.parametrize("source_page", ["/vacatures/123", "/", "/vacatures/1?job=42", "/x?type=kandidaat&job=1"])
def test_lead_submit_accepts_valid_source_page(source_page):
    lead = LeadSubmit(**_LEAD_KWARGS, source_page=source_page)
    assert lead.source_page == source_page


@pytest.mark.parametrize("source_page", [
    "vacatures/123",           # no leading '/'
    "https://gsprecruitment.nl/x",  # full URL, not a same-site path
    "/" + "a" * 200,           # too long (> 200)
    "/x?utm_source=evil",      # disallowed querystring key
    "/x?job=1&ref=other",      # one allowed key + one disallowed key
])
def test_lead_submit_rejects_invalid_source_page(source_page):
    with pytest.raises(ValidationError):
        LeadSubmit(**_LEAD_KWARGS, source_page=source_page)


def test_lead_submit_source_page_none_by_default():
    lead = LeadSubmit(**_LEAD_KWARGS)
    assert lead.source_page is None
    assert lead.referrer_host is None


@pytest.mark.parametrize("host", ["google.com", "www.linkedin.com", "localhost", "a.b.c.example.co.uk"])
def test_lead_submit_accepts_valid_referrer_host(host):
    lead = LeadSubmit(**_LEAD_KWARGS, referrer_host=host)
    assert lead.referrer_host == host


@pytest.mark.parametrize("host", [
    "https://google.com",      # scheme not allowed
    "google.com/search",       # path not allowed
    "google.com:443",          # port not allowed
    "a" * 101,                 # too long
    "-badstart.com",           # label can't start with '-'
])
def test_lead_submit_rejects_invalid_referrer_host(host):
    with pytest.raises(ValidationError):
        LeadSubmit(**_LEAD_KWARGS, referrer_host=host)


def _quiz_kwargs():
    return dict(email="a@example.com", answers=[QuizAnswerItem(question_id=1, answer_index=0)])


def test_quiz_submit_accepts_valid_source_page_and_referrer_host():
    q = QuizSubmitRequest(**_quiz_kwargs(), source_page="/quiz?type=kandidaat", referrer_host="gsprecruitment.nl")
    assert q.source_page == "/quiz?type=kandidaat"
    assert q.referrer_host == "gsprecruitment.nl"


def test_quiz_submit_rejects_bad_source_page():
    with pytest.raises(ValidationError):
        QuizSubmitRequest(**_quiz_kwargs(), source_page="not-a-path")


def test_quiz_submit_rejects_bad_referrer_host():
    with pytest.raises(ValidationError):
        QuizSubmitRequest(**_quiz_kwargs(), referrer_host="http://evil.example.com")


# ── 3a. kind_sql: a linked candidate_profiles row is the stronger truth ──

class _FakeCandidatesDB:
    """Mirrors just enough of GET /candidates' four possible fetch calls
    (a_total, a_rows, and -- only when applicable -- b_total, b_rows) to
    let the handler run end to end, while recording every SQL string so
    tests can assert on the exact CASE/JOIN/WHERE fragments involved."""

    def __init__(self, a_total=0, a_rows=None, b_total=0, b_rows=None):
        self.a_total = a_total
        self.a_rows = a_rows or []
        self.b_total = b_total
        self.b_rows = b_rows or []
        self.calls = []

    async def fetch_val(self, sql, *params):
        self.calls.append((sql, params))
        if "FROM candidate_profiles cp JOIN users u ON u.id = cp.user_id" in sql:
            return self.b_total
        return self.a_total

    async def fetch_all(self, sql, *params):
        self.calls.append((sql, params))
        if "SELECT NULL::int AS candidate_id" in sql:
            return self.b_rows
        return self.a_rows


def test_kind_sql_treats_linked_profile_as_self_registered_even_if_sourced(monkeypatch):
    """A candidate originally sourced (c.source = 'apollo') who later
    creates a portal account that candidate_link.py links via
    candidate_profiles.candidate_id must show as kind='self-registered'
    -- the linked profile is the stronger truth, c.source keeps its own
    original-provenance meaning (core/sources.py) and is deliberately
    left unchanged."""
    import routers.admin as admin

    db = _FakeCandidatesDB()
    monkeypatch.setattr(admin, "fetch_val", db.fetch_val)
    monkeypatch.setattr(admin, "fetch_all", db.fetch_all)

    asyncio.run(admin.list_all_candidates(
        status=None, source=None, kind=None, search=None, limit=50, offset=0,
        current_user={"id": 1, "role": "admin"},
    ))

    a_rows_calls = [sql for sql, params in db.calls if "SELECT c.id AS candidate_id" in sql]
    assert a_rows_calls, "expected the branch-A row query to run"
    kind_sql_fragment = (
        "CASE WHEN cp.user_id IS NOT NULL OR c.source = 'portal_registration' "
        "OR EXISTS (SELECT 1 FROM users ux WHERE LOWER(ux.email) = LOWER(c.email) "
        "AND ux.role = 'candidate' AND ux.deleted_at IS NULL) "
        "THEN 'self-registered' ELSE 'sourced' END"
    )
    for sql in a_rows_calls:
        assert kind_sql_fragment in sql

    # The count query must join candidate_profiles too (kind_sql references
    # cp.user_id, so a `kind` filter -- or just this expression appearing
    # in a_where -- would otherwise reference an unjoined alias).
    a_total_calls = [sql for sql, params in db.calls
                     if sql.strip().startswith("SELECT COUNT(*) FROM candidates c\n")]
    assert a_total_calls
    for sql in a_total_calls:
        assert "LEFT JOIN candidate_profiles cp ON cp.candidate_id = c.id" in sql


# ── 3a-detail. GET /candidates/sourced/{id}: kind must not disagree with the list ──

class _FakeCandidateDetailDB:
    """candidate: the candidates.* row (source, id, email, ...).
    linked_profile: the candidate_profiles row for this candidate.id, or
    None -- mirrors the FK-first lookup get_candidate_detail() itself
    does before ever computing `kind`."""

    def __init__(self, candidate, linked_profile=None, user=None):
        self.candidate = dict(candidate)
        self.linked_profile = linked_profile
        self.user = user

    async def fetch_one(self, sql, *params):
        if "FROM candidates c" in sql and "LEFT JOIN (" in sql:
            return dict(self.candidate)
        if "FROM candidate_profiles WHERE candidate_id" in sql:
            return dict(self.linked_profile) if self.linked_profile else None
        if "FROM users WHERE" in sql:
            return dict(self.user) if self.user else None
        return None


def test_sourced_detail_kind_matches_list_for_linked_but_differently_sourced_candidate(monkeypatch):
    """Same scenario as the list-level test above (apollo-sourced, later
    linked via candidate_profiles) but addressed through the *detail*
    route -- must also report kind='self-registered', not 'sourced',
    or the detail view would flatly contradict what GET /candidates just
    showed the admin for this exact person."""
    import routers.admin as admin

    candidate = {
        "id": 42, "email": "linked@example.com", "source": "apollo",
        "skills": None, "languages": None, "tags": None,
    }
    db = _FakeCandidateDetailDB(
        candidate=candidate,
        linked_profile={"user_id": 7},
        user={"id": 7, "is_verified": True},
    )
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)

    result = asyncio.run(
        admin.get_candidate_detail(kind="sourced", item_id=42, current_user={"id": 1, "role": "admin"})
    )
    assert result["kind"] == "self-registered"
    assert result["source"] == "apollo"  # provenance untouched
    assert result["user_id"] == 7


def test_sourced_detail_kind_stays_sourced_when_unlinked(monkeypatch):
    import routers.admin as admin

    candidate = {
        "id": 43, "email": "unlinked@example.com", "source": "apollo",
        "skills": None, "languages": None, "tags": None,
    }
    db = _FakeCandidateDetailDB(candidate=candidate, linked_profile=None, user=None)
    monkeypatch.setattr(admin, "fetch_one", db.fetch_one)

    result = asyncio.run(
        admin.get_candidate_detail(kind="sourced", item_id=43, current_user={"id": 1, "role": "admin"})
    )
    assert result["kind"] == "sourced"
    assert result["user_id"] is None


# ── 3b. Branch B dedup: NOT EXISTS guards against listing the same person twice ──

def test_branch_b_excludes_profiles_whose_email_already_has_a_candidates_row(monkeypatch):
    """cp.candidate_id IS NULL only means *this* candidate_profiles row
    has no FK link yet -- not that no candidates row exists for the same
    person. Branch A's e-mail-fallback JOIN already surfaces such a
    person, so branch B must NOT EXISTS-guard against the same e-mail or
    they would be listed twice."""
    import routers.admin as admin

    db = _FakeCandidatesDB()
    monkeypatch.setattr(admin, "fetch_val", db.fetch_val)
    monkeypatch.setattr(admin, "fetch_all", db.fetch_all)

    asyncio.run(admin.list_all_candidates(
        status=None, source=None, kind=None, search=None, limit=50, offset=0,
        current_user={"id": 1, "role": "admin"},
    ))

    b_rows_calls = [sql for sql, params in db.calls if "SELECT NULL::int AS candidate_id" in sql]
    assert b_rows_calls, "expected branch B to run when no status/source/kind filter excludes it"
    not_exists_fragment = "NOT EXISTS (SELECT 1 FROM candidates c2 WHERE LOWER(c2.email) = LOWER(u.email) AND c2.deleted_at IS NULL)"
    for sql in b_rows_calls:
        assert not_exists_fragment in sql

    b_total_calls = [sql for sql, params in db.calls
                     if "FROM candidate_profiles cp JOIN users u ON u.id = cp.user_id" in sql]
    assert b_total_calls
    for sql in b_total_calls:
        assert not_exists_fragment in sql


def test_branch_b_skipped_entirely_when_filters_rule_it_out(monkeypatch):
    """kind='sourced' can never match branch B's hardcoded
    kind='self-registered' rows -- the whole query must be skipped, not
    just filtered down to zero rows over the wire."""
    import routers.admin as admin

    db = _FakeCandidatesDB()
    monkeypatch.setattr(admin, "fetch_val", db.fetch_val)
    monkeypatch.setattr(admin, "fetch_all", db.fetch_all)

    asyncio.run(admin.list_all_candidates(
        status=None, source=None, kind="sourced", search=None, limit=50, offset=0,
        current_user={"id": 1, "role": "admin"},
    ))

    b_rows_calls = [sql for sql, params in db.calls if "SELECT NULL::int AS candidate_id" in sql]
    assert not b_rows_calls


# ── 3c. core/sources.py: literals + family grouping ───────────────────────

def test_known_sources_contains_the_six_literals():
    assert set(KNOWN_SOURCES) == {PORTAL_REGISTRATION, TALENTPOOL_OPTIN, APOLLO, APOLLO_BULK, AGENT}


def test_apollo_and_apollo_bulk_share_a_family():
    assert source_family(APOLLO) == "apollo"
    assert source_family(APOLLO_BULK) == "apollo"
    assert SOURCE_FAMILY[APOLLO] == SOURCE_FAMILY[APOLLO_BULK]


def test_source_family_leaves_other_sources_alone():
    assert source_family(PORTAL_REGISTRATION) == PORTAL_REGISTRATION
    assert source_family(TALENTPOOL_OPTIN) == TALENTPOOL_OPTIN
    assert source_family(AGENT) == AGENT


def test_source_family_caller_supplied_value_is_its_own_family():
    assert source_family("some_custom_agent_value") == "some_custom_agent_value"


def test_source_family_none_becomes_unknown():
    assert source_family(None) == "unknown"
    assert source_family("") == "unknown"


def test_client_analytics_groups_source_breakdown_by_family(monkeypatch):
    """routers/client.py:700-710 -- two matches sourced via 'apollo' and
    one via 'apollo_bulk' must report as one 'apollo' bucket of 3, not
    two separate buckets each smaller than the true total."""
    import routers.client as client_router

    class _FakeAnalyticsDB:
        async def fetch_one(self, sql, *params):
            return {"id": 1}

        async def fetch_all(self, sql, *params):
            if "GROUP BY c.source" in sql or "c.source, COUNT(*)" in sql:
                return [
                    {"source": "apollo", "count": 2},
                    {"source": "apollo_bulk", "count": 1},
                    {"source": "portal_registration", "count": 5},
                ]
            if "stage" in sql:
                return []
            return []

        async def fetch_val(self, sql, *params):
            return 0

    db = _FakeAnalyticsDB()
    monkeypatch.setattr(client_router, "fetch_one", db.fetch_one)
    monkeypatch.setattr(client_router, "fetch_all", db.fetch_all)
    monkeypatch.setattr(client_router, "fetch_val", db.fetch_val)

    result = asyncio.run(client_router.get_client_analytics(current_user={"id": 1, "role": "client"}))
    assert result.source_breakdown["apollo"] == 3
    assert result.source_breakdown["portal_registration"] == 5
    assert "apollo_bulk" not in result.source_breakdown


# ── 4. GET /v1/admin/health: duplicate_profile_links ──────────────────────

def test_health_detail_reports_duplicate_profile_links(monkeypatch):
    import routers.health as health

    calls = []

    async def fake_check_database():
        return "connected"

    async def fake_fetch_val(sql, *params):
        calls.append(sql)
        if "GROUP BY candidate_id HAVING COUNT(*) > 1" in sql:
            return 2
        return 0

    monkeypatch.setattr(health, "_check_database", fake_check_database)
    monkeypatch.setattr(health, "fetch_val", fake_fetch_val)

    result = asyncio.run(health.get_health_detail())
    assert result.duplicate_profile_links == 2
    assert any("candidate_profiles" in sql for sql in calls)


def test_health_detail_duplicate_profile_links_none_when_db_down(monkeypatch):
    import routers.health as health

    async def fake_check_database():
        return "error: ConnectionError"

    monkeypatch.setattr(health, "_check_database", fake_check_database)

    result = asyncio.run(health.get_health_detail())
    assert result.duplicate_profile_links is None


# ── 5. GDPR self-export covers source_page/referrer_host ─────────────────
# migrations/038_leads_origin.py adds source_page/referrer_host to
# contact_submissions and quiz_submissions -- routers/gdpr.py's
# export_my_data() selects an explicit column list from both (unlike the
# candidates SELECT *, see tests/test_ws_c7_placements.py), so a new
# personal-data column there needs its own regression guard or it goes
# missing from a person's Art. 15/20 export silently (security-auditor
# WS2 finding).

def test_gdpr_export_selects_source_page_and_referrer_host_from_quiz_and_contact():
    import inspect
    import routers.gdpr as gdpr

    source = inspect.getsource(gdpr.export_my_data)
    full_quiz_stmt = source[source.index("quiz = await fetch_all("):source.index("contact = await fetch_all(")]
    full_contact_stmt = source[source.index("contact = await fetch_all("):source.index("push_tokens = await fetch_all(")]
    assert "source_page" in full_quiz_stmt and "referrer_host" in full_quiz_stmt, (
        "quiz_submissions export is missing source_page/referrer_host"
    )
    assert "source_page" in full_contact_stmt and "referrer_host" in full_contact_stmt, (
        "contact_submissions export is missing source_page/referrer_host"
    )
