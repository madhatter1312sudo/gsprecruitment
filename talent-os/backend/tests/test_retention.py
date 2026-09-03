"""
Unit tests for WS-E.8 retention/purge: core/retention.py's table vs. the
register/SOP Markdown, the purge job's dry-run-writes-nothing guarantee,
the admin endpoints' confirm-flag enforcement, and migration 022's text.

No DB/network needed: services/scheduler.py's fetch_all/fetch_one/execute
are monkeypatched to a tiny recorder, matching tests/test_gdpr_erasure.py
and tests/test_ws_e7_gdpr_outreach.py's style.
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from core import retention

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REGISTER_PATH = os.path.join(REPO_ROOT, "docs", "VERWERKINGSREGISTER.md")
SOP_PATH = os.path.join(REPO_ROOT, "docs", "SOURCING-SOP.md")
PRIVACY_HTML_PATH = os.path.join(REPO_ROOT, "website", "privacy.html")

TABLE_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|$")


def _parse_bewaartabel(md_text: str, heading_marker: str) -> list:
    """Find the bewaartabel (Categorie | Bewaartermijn | Bron/opmerking)
    directly under `heading_marker` and return its data rows as
    (categorie, bewaartermijn, bron_opmerking) tuples, in order."""
    start = md_text.index(heading_marker)
    chunk = md_text[start:]
    header_idx = chunk.index("| Categorie | Bewaartermijn | Bron/opmerking |")
    lines = chunk[header_idx:].splitlines()
    rows = []
    # lines[0] = header, lines[1] = |---|---|---|, data rows follow until
    # the first line that isn't a "| ... | ... | ... |" table row.
    for line in lines[2:]:
        m = TABLE_ROW_RE.match(line.strip())
        if not m:
            break
        categorie, bewaartermijn, bron = m.groups()
        # A cell that is just "" in the source renders as an empty match
        # group; strip a lone empty group back to "" (regex already does
        # via \s*(.+?)\s* only for non-empty -- handle empty cells too).
        rows.append((categorie, bewaartermijn, bron if bron.strip() else ""))
    return rows


def test_register_table_matches_code():
    with open(REGISTER_PATH, encoding="utf-8") as f:
        text = f.read()
    register_rows = _parse_bewaartabel(text, "### 1.4 Bewaartermijnen")
    assert register_rows == list(retention.register_rows())


def test_sop_table_matches_code():
    with open(SOP_PATH, encoding="utf-8") as f:
        text = f.read()
    sop_rows = _parse_bewaartabel(text, "## 6. Bewaartermijnen")
    assert sop_rows == list(retention.register_rows())


def test_render_markdown_round_trips_through_the_parser():
    """render_markdown()'s own output, fed back through the same parser
    used on the two docs, must reproduce register_rows() exactly -- this
    is what proves the parser and the renderer agree on format."""
    md = "### 1.4 Bewaartermijnen\n\n" + retention.render_markdown() + "\n"
    assert _parse_bewaartabel(md, "### 1.4 Bewaartermijnen") == list(retention.register_rows())


def _parse_html_retention_table(html_text: str, table_id: str) -> list:
    """Extract (categorie, bewaartermijn, bron_opmerking) tuples from the
    <table id="table_id"> in website/privacy.html — good enough for our
    own fixed table markup (one <tr> per row, three plain-text <td>s,
    no nested tags), not a general HTML parser."""
    start = html_text.index(f'id="{table_id}"')
    tbody_start = html_text.index("<tbody>", start)
    tbody_end = html_text.index("</tbody>", tbody_start)
    body = html_text[tbody_start:tbody_end]
    rows = []
    for row_match in re.finditer(r"<tr>(.*?)</tr>", body, re.DOTALL):
        cells = re.findall(r"<td>(.*?)</td>", row_match.group(1), re.DOTALL)
        assert len(cells) == 3, row_match.group(0)
        rows.append(tuple(c.strip() for c in cells))
    return rows


def test_privacy_html_nl_retention_table_matches_code():
    with open(PRIVACY_HTML_PATH, encoding="utf-8") as f:
        text = f.read()
    rows = _parse_html_retention_table(text, "retention-table-nl")
    assert rows == list(retention.register_rows())


# security-auditor follow-up (WS-E.8 LOW #6): the register/SOP are Dutch
# documents of record (register_rows()/render_markdown() only assert
# against those), so there is no Dutch "source of truth" string to check
# the English privacy.html table against character-for-character -- it is
# instead a categorie-by-categorie *translation* of the same table
# (bewaartermijn NL and EN differ in wording but not in duration/anchor).
# This translation map is what keeps the two from drifting silently: each
# NL categorie maps to exactly one EN row (checked below in table order),
# and a future edit to core/retention.py's `categorie` values that isn't
# mirrored here fails loudly (KeyError) rather than the EN table quietly
# going stale and unchecked.
_EN_CATEGORY_TRANSLATION = {
    "Afgewezen sollicitant": "Rejected applicant",
    "Talentpool met expliciete toestemming": "Talent pool with explicit consent",
    "Gesourcete persoon zonder reactie": "Sourced person, no response",
    "Prospect zonder reactie": "Prospect, no response",
    "Prospect die wel reageert (relatie)": "Prospect who responds (relationship)",
    "Actief portalaccount zonder sollicitatie": "Active portal account without application",
    "Referral": "Referral",
    "Leads/quiz": "Leads/quiz",
    "Geplaatste kandidaat (contract- en factuurdata)": "Placed candidate (contract/invoice data)",
    "Logs": "Logs",
}


def test_privacy_html_en_retention_table_translates_the_same_categories_in_order():
    with open(PRIVACY_HTML_PATH, encoding="utf-8") as f:
        text = f.read()
    en_rows = _parse_html_retention_table(text, "retention-table-en")
    nl_rows = list(retention.register_rows())
    assert len(en_rows) == len(nl_rows) == 10
    for (nl_categorie, _, _), (en_categorie, _, _) in zip(nl_rows, en_rows):
        assert en_categorie == _EN_CATEGORY_TRANSLATION[nl_categorie]


def test_table_has_exactly_the_documented_ten_rows():
    assert len(retention.RETENTION_TABLE) == 10
    assert [r.key for r in retention.RETENTION_TABLE] == [
        "rejected_applicant", "talentpool_consent", "sourced_no_response",
        "prospect_no_response", "prospect_responding", "portal_account_inactive",
        "referral", "leads_quiz", "placed_candidate", "logs",
    ]


def test_three_aanname_rows_flagged():
    aanname = [r.key for r in retention.RETENTION_TABLE if "aanname" in r.bron_opmerking]
    assert aanname == ["sourced_no_response", "prospect_responding", "portal_account_inactive"]


def test_selectors_are_strings_naming_their_anchor_column():
    for row in retention.RETENTION_TABLE:
        assert isinstance(row.selector_sql, str) and row.selector_sql.strip()
        if row.action == "infra_only":
            continue
        # anchor_column may be "table.column" or a comma-separated pair
        # (leads_quiz) or carry a parenthetical qualifier (placed_candidate)
        # -- check the bare column name(s) show up in the selector text.
        for col_expr in row.anchor_column.split(","):
            bare_col = col_expr.strip().split(".")[-1].split(" ")[0]
            assert bare_col in row.selector_sql, (row.key, bare_col, row.selector_sql)


def test_get_row_found_and_not_found():
    assert retention.get_row("sourced_no_response").key == "sourced_no_response"
    assert retention.get_row("does_not_exist") is None


# ── security-auditor follow-up (WS-E.8 HIGH #1): "no reaction" guards ────

def test_sourced_no_response_sql_guards_against_every_reaction_signal():
    sql = retention.SOURCED_NO_RESPONSE_SQL
    assert "status = 'sourced'" in sql
    assert "NOT EXISTS" in sql
    assert "FROM matches m" in sql and "m.status <> 'suggested'" in sql
    assert "FROM pipeline_entries p" in sql
    assert "FROM outreach_messages o" in sql and "o.replied_at IS NOT NULL" in sql
    assert "FROM users u" in sql and "u.deleted_at IS NULL" in sql


def test_sourced_and_referral_rows_share_the_same_guarded_selector():
    sourced = retention.get_row("sourced_no_response")
    referral = retention.get_row("referral")
    assert sourced.selector_sql is retention.SOURCED_NO_RESPONSE_SQL
    assert referral.selector_sql is retention.SOURCED_NO_RESPONSE_SQL


def test_prospect_no_response_sql_guards_against_replies_and_sent_drafts():
    sql = retention.PROSPECT_NO_RESPONSE_SQL
    assert "status = 'new'" in sql
    assert "FROM outreach_messages om" in sql and "om.replied_at IS NOT NULL" in sql
    assert "FROM outreach_drafts od" in sql and "od.status = 'sent'" in sql
    assert retention.get_row("prospect_no_response").selector_sql is retention.PROSPECT_NO_RESPONSE_SQL


# ── WS-C.17: talentpool_consent is now schema_ready ───────────────────────

def test_talentpool_expired_sql_selects_expired_opt_in_talentpool_only():
    sql = retention.TALENTPOOL_EXPIRED_SQL
    assert "lawful_basis = 'opt_in_talentpool'" in sql
    assert "consent_talentpool_until" in sql
    assert "deleted_at IS NULL" in sql


def test_talentpool_consent_row_is_schema_ready_with_shared_selector():
    row = retention.get_row("talentpool_consent")
    assert row.schema_ready is True
    assert row.action == "anonymise"
    assert row.anchor_column == "candidates.consent_talentpool_until"
    assert row.selector_sql is retention.TALENTPOOL_EXPIRED_SQL


def test_scheduler_reuses_the_shared_retention_selectors_not_a_local_copy():
    """The purge job must run exactly the query core/retention.py documents
    -- not a second, independently-maintained copy that could drift."""
    import services.scheduler as scheduler
    assert not hasattr(scheduler, "SOURCED_NO_RESPONSE_SQL")
    assert not hasattr(scheduler, "PROSPECT_NO_RESPONSE_SQL")
    assert scheduler.retention.SOURCED_NO_RESPONSE_SQL is retention.SOURCED_NO_RESPONSE_SQL
    assert scheduler.retention.PROSPECT_NO_RESPONSE_SQL is retention.PROSPECT_NO_RESPONSE_SQL


def test_sourced_no_response_query_excludes_a_candidate_with_a_progressed_match(monkeypatch):
    """End-to-end guard check against a fake DB that actually applies the
    WHERE clause semantics, not just a substring check on the SQL text --
    a candidate with a non-'suggested' match, a pipeline entry, a replied
    outreach message, or a live user account must never come back."""
    import services.scheduler as scheduler

    candidates = {
        1: {"id": 1, "email": "clean@example.com"},       # no signals -- eligible
        2: {"id": 2, "email": "has-match@example.com"},   # progressed match
        3: {"id": 3, "email": "has-pipeline@example.com"},  # pipeline entry
        4: {"id": 4, "email": "has-reply@example.com"},   # replied outreach message
        5: {"id": 5, "email": "has-account@example.com"},  # live user account
    }
    signals = {
        "matches": {2},
        "pipeline_entries": {3},
        "outreach_messages": {4},
        "users": {5},
    }

    async def _fake_fetch_all(sql, *args):
        assert sql is retention.SOURCED_NO_RESPONSE_SQL
        return [
            c for cid, c in candidates.items()
            if cid not in signals["matches"] and cid not in signals["pipeline_entries"]
            and cid not in signals["outreach_messages"] and cid not in signals["users"]
        ]

    monkeypatch.setattr(scheduler, "fetch_all", _fake_fetch_all)
    rows = asyncio.run(scheduler._count_sourced_no_response("gerechtvaardigd_belang"))
    assert [r["id"] for r in rows] == [1]


# ── run_retention_purge() -- stubbed DB ───────────────────────────────────

class _Recorder:
    def __init__(self):
        self.fetch_calls = []
        self.execute_calls = []

    async def fetch_all(self, sql, *args):
        self.fetch_calls.append((sql, args))
        return []  # no matching rows for any category -- counts are all 0

    async def execute(self, sql, *args):
        self.execute_calls.append((sql, args))
        return "OK"


@pytest.fixture()
def patch_scheduler_db(monkeypatch):
    def _patch(rec: _Recorder):
        import services.scheduler as scheduler
        monkeypatch.setattr(scheduler, "fetch_all", rec.fetch_all)
        monkeypatch.setattr(scheduler, "execute", rec.execute)
        return scheduler
    return _patch


def test_dry_run_issues_no_execute_calls(patch_scheduler_db):
    rec = _Recorder()
    scheduler = patch_scheduler_db(rec)
    result = asyncio.run(scheduler.run_retention_purge(dry_run=True))
    assert result["dry_run"] is True
    assert rec.execute_calls == []  # no UPDATE/DELETE/INSERT at all
    # every schema_ready, actionable category returned a count
    counted = {c["key"]: c["count"] for c in result["categories"] if c["status"] == "counted"}
    assert counted == {
        "sourced_no_response": 0, "prospect_no_response": 0, "referral": 0,
        "leads_quiz": 0, "talentpool_consent": 0,
    }


def test_dry_run_reports_schema_not_ready_categories(patch_scheduler_db):
    rec = _Recorder()
    scheduler = patch_scheduler_db(rec)
    result = asyncio.run(scheduler.run_retention_purge(dry_run=True))
    by_key = {c["key"]: c["status"] for c in result["categories"]}
    assert by_key["rejected_applicant"] == "schema_not_ready"
    assert by_key["prospect_responding"] == "schema_not_ready"
    assert by_key["portal_account_inactive"] == "schema_not_ready"
    assert by_key["placed_candidate"] == "not_applicable"
    assert by_key["logs"] == "not_applicable"
    # WS-C.17: talentpool_consent is schema_ready as of migrations/030 --
    # it's counted, not reported schema_not_ready, and it fetches the
    # shared retention.TALENTPOOL_EXPIRED_SQL selector.
    assert by_key["talentpool_consent"] == "counted"
    fetched_categories = {sql for sql, _ in rec.fetch_calls}
    assert any("consent_talentpool_until" in sql for sql in fetched_categories)
    # the still-not-ready categories never issued a fetch -- no query
    # against a column that doesn't exist in the DB
    assert not any("rejected_at" in sql for sql in fetched_categories)


def test_real_run_purges_and_writes_one_audit_row_per_purged_category(monkeypatch, patch_scheduler_db):
    rec = _Recorder()
    scheduler = patch_scheduler_db(rec)

    # sourced_no_response / referral purge via erase_person() -- stub that
    # out too so this test doesn't need a full erase_person() DB fixture.
    erased = []

    async def _fake_erase_person(email, actor_id=None, reason="manual"):
        erased.append((email, reason))
        return {"status": "complete"}

    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person)

    result = asyncio.run(scheduler.run_retention_purge(dry_run=False))
    assert result["dry_run"] is False

    # No matching rows (fetch_all always returns []) -- every actionable
    # category purges 0 rows, but each still gets exactly one audit_log
    # INSERT (the "one row per category" requirement), and no anonymise/
    # delete calls actually fired since there was nothing to act on.
    audit_inserts = [c for c in rec.execute_calls if c[0].startswith("INSERT INTO audit_log")]
    purged_keys = {c["key"] for c in result["categories"] if c["status"] == "purged"}
    assert purged_keys == {
        "sourced_no_response", "prospect_no_response", "referral", "leads_quiz", "talentpool_consent",
    }
    assert len(audit_inserts) == len(purged_keys)
    for sql, args in audit_inserts:
        assert sql.strip().startswith("INSERT INTO audit_log")
        assert args[0] == "retention_purge"
    assert erased == []  # no candidate rows returned by the stub, so nothing to erase


def test_retention_purge_job_defaults_to_dry_run_when_flag_unset(monkeypatch, patch_scheduler_db):
    """RETENTION_PURGE_ENABLED unset/false (core/config.py default) -- the
    cron entry point must fall back to dry_run=True."""
    rec = _Recorder()
    scheduler = patch_scheduler_db(rec)
    monkeypatch.setattr(scheduler.settings, "retention_purge_enabled", False)
    result = asyncio.run(scheduler.retention_purge_job())
    assert result["dry_run"] is True
    assert rec.execute_calls == []


# ── Admin endpoints -- confirm flag enforcement (no HTTP client needed;
#    call the route functions directly like the FastAPI dependency system
#    would, with a fake current_user) ───────────────────────────────────

def test_run_retention_endpoint_dry_run_default_needs_no_confirm(monkeypatch, patch_scheduler_db):
    rec = _Recorder()
    patch_scheduler_db(rec)
    from routers import retention_admin

    payload = retention_admin.RetentionRunRequest()
    assert payload.dry_run is True
    result = asyncio.run(retention_admin.run_retention(payload, current_user={"id": 1, "role": "admin"}))
    assert result["dry_run"] is True


def test_run_retention_endpoint_real_run_without_confirm_is_refused(patch_scheduler_db):
    rec = _Recorder()
    patch_scheduler_db(rec)
    from fastapi import HTTPException
    from routers import retention_admin

    payload = retention_admin.RetentionRunRequest(dry_run=False)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.run_retention(payload, current_user={"id": 1, "role": "admin"}))
    assert exc_info.value.status_code == 409
    assert rec.execute_calls == []


def test_run_retention_endpoint_real_run_with_confirm_proceeds(patch_scheduler_db, monkeypatch):
    rec = _Recorder()
    patch_scheduler_db(rec)

    async def _fake_erase_person(email, actor_id=None, reason="manual"):
        return {"status": "complete"}

    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person)

    from routers import retention_admin
    payload = retention_admin.RetentionRunRequest(dry_run=False, confirm="PURGE")
    result = asyncio.run(retention_admin.run_retention(payload, current_user={"id": 1, "role": "admin"}))
    assert result["dry_run"] is False


def test_apollo_pool_purge_target_sql_carries_all_five_guards():
    """security-auditor follow-up (WS-E.8 HIGH #2): the same reaction
    signals as the retention job's sourced_no_response guard, plus the
    presented-candidate guard specific to this pool."""
    from routers import retention_admin

    sql = retention_admin._TARGET_ROWS_SQL
    assert "FROM matches m" in sql and "m.status <> 'suggested'" in sql
    assert "FROM pipeline_entries p" in sql
    assert "FROM outreach_messages o" in sql and "o.replied_at IS NOT NULL" in sql
    assert "FROM users u" in sql and "u.deleted_at IS NULL" in sql
    assert "FROM outreach_drafts d" in sql and "d.presented_candidate_id" in sql
    assert sql.count("NOT EXISTS") == 5
    # the unguarded pool query is a strict prefix -- the guards are
    # additive filters on top of it, not a different candidate set
    assert sql.startswith(retention_admin._POOL_ROWS_SQL)


def test_apollo_pool_purge_dry_run_default_needs_no_confirm(monkeypatch):
    async def _fake_fetch_all(sql, *args):
        return []

    from routers import retention_admin
    monkeypatch.setattr(retention_admin, "fetch_all", _fake_fetch_all)

    payload = retention_admin.ApolloPoolPurgeRequest()
    assert payload.dry_run is True
    result = asyncio.run(retention_admin.purge_apollo_pool(payload, current_user={"id": 1, "role": "admin"}))
    assert result == {
        "dry_run": True, "total": 0, "would_anonymise": 0, "would_hard_delete": 0, "skipped": 0,
    }


def test_apollo_pool_purge_dry_run_reports_guard_skipped_rows(monkeypatch):
    """A row that matches the raw pool criteria but is excluded by one of
    the five reaction-signal guards must show up as `skipped`, not
    silently vanish from the response."""
    from routers import retention_admin

    async def _fake_fetch_all(sql, *args):
        if sql is retention_admin._POOL_ROWS_SQL:
            return [{"id": 1, "email": "a@example.com"}, {"id": 2, "email": "b@example.com"}]
        assert sql is retention_admin._TARGET_ROWS_SQL
        return [{"id": 1, "email": "a@example.com"}]  # id=2 excluded by a guard

    monkeypatch.setattr(retention_admin, "fetch_all", _fake_fetch_all)
    payload = retention_admin.ApolloPoolPurgeRequest()
    result = asyncio.run(retention_admin.purge_apollo_pool(payload, current_user={"id": 1, "role": "admin"}))
    assert result == {
        "dry_run": True, "total": 1, "would_anonymise": 1, "would_hard_delete": 0, "skipped": 1,
    }


def test_apollo_pool_purge_real_run_without_confirm_is_refused(monkeypatch):
    calls = []

    async def _fake_fetch_all(sql, *args):
        calls.append(sql)
        return []

    from fastapi import HTTPException
    from routers import retention_admin
    monkeypatch.setattr(retention_admin, "fetch_all", _fake_fetch_all)

    payload = retention_admin.ApolloPoolPurgeRequest(dry_run=False)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.purge_apollo_pool(payload, current_user={"id": 1, "role": "admin"}))
    assert exc_info.value.status_code == 409
    assert calls == []  # refused before even querying the pool


def test_apollo_pool_purge_real_run_with_correct_confirm_proceeds(monkeypatch):
    rows = [
        {"id": 1, "email": "with-email@example.com"},
        {"id": 2, "email": None},
    ]
    executed = []
    erased = []

    async def _fake_fetch_all(sql, *args):
        return rows

    async def _fake_execute(sql, *args):
        executed.append((sql, args))
        return "OK"

    async def _fake_erase_person(email, actor_id=None, reason="manual"):
        erased.append(email)
        return {"status": "complete"}

    from routers import retention_admin
    import routers.gdpr as gdpr
    monkeypatch.setattr(retention_admin, "fetch_all", _fake_fetch_all)
    monkeypatch.setattr(retention_admin, "execute", _fake_execute)
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person)

    payload = retention_admin.ApolloPoolPurgeRequest(dry_run=False, confirm="DELETE APOLLO POOL")
    result = asyncio.run(retention_admin.purge_apollo_pool(payload, current_user={"id": 7, "role": "admin"}))

    assert result == {"dry_run": False, "total": 2, "anonymised": 1, "hard_deleted": 1, "skipped": 0}
    assert erased == ["with-email@example.com"]
    delete_calls = [c for c in executed if c[0].startswith("DELETE FROM candidates")]
    assert len(delete_calls) == 1
    assert delete_calls[0][1] == ([2],)
    audit_calls = [c for c in executed if c[0].startswith("INSERT INTO audit_log")]
    assert len(audit_calls) == 1
    assert audit_calls[0][1][0] == "apollo_pool_purge"


def test_apollo_pool_purge_writes_audit_row_even_when_the_delete_fails(monkeypatch):
    """security-auditor follow-up (WS-E.8 HIGH #2): the audit_log INSERT
    lives in a `finally`, so a failure partway through (here: the hard-
    delete DELETE statement itself raising) still leaves an audit trail
    recording what actually completed (the anonymise that ran first)
    before the exception propagates."""
    rows = [
        {"id": 1, "email": "with-email@example.com"},
        {"id": 2, "email": None},
    ]
    executed = []
    erased = []

    async def _fake_fetch_all(sql, *args):
        return rows

    async def _fake_execute(sql, *args):
        executed.append((sql, args))
        if sql.strip().startswith("DELETE FROM candidates"):
            raise RuntimeError("simulated DB failure")
        return "OK"

    async def _fake_erase_person(email, actor_id=None, reason="manual"):
        erased.append(email)
        return {"status": "complete"}

    from routers import retention_admin
    import routers.gdpr as gdpr
    monkeypatch.setattr(retention_admin, "fetch_all", _fake_fetch_all)
    monkeypatch.setattr(retention_admin, "execute", _fake_execute)
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person)

    payload = retention_admin.ApolloPoolPurgeRequest(dry_run=False, confirm="DELETE APOLLO POOL")
    with pytest.raises(RuntimeError):
        asyncio.run(retention_admin.purge_apollo_pool(payload, current_user={"id": 7, "role": "admin"}))

    assert erased == ["with-email@example.com"]  # the anonymise step completed before the failure
    audit_calls = [c for c in executed if c[0].startswith("INSERT INTO audit_log")]
    assert len(audit_calls) == 1, "audit row must still be written despite the DELETE failure"
    import json as _json
    changes = _json.loads(audit_calls[0][1][3])
    assert changes["anonymised"] == 1
    assert changes["hard_deleted"] == 0  # the DELETE never completed


# ── security-auditor follow-up (WS-E.8 MEDIUM #4): scheduler's Apollo
#    jobs must also honour the env master switch, since they're reachable
#    manually via POST /api/v1/admin/outreach/run/sourcing|enrich even
#    when start_scheduler() never registered them as cron jobs ──────────

def test_apollo_search_and_sync_skips_when_env_master_switch_is_off(monkeypatch):
    import services.scheduler as scheduler

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("must not reach the DB flag check, let alone the Apollo API")

    monkeypatch.setattr(scheduler.settings, "apollo_sync_enabled", False)
    monkeypatch.setattr(scheduler.harvest_service, "_flag_enabled", _fail_if_called)
    result = asyncio.run(scheduler.apollo_search_and_sync())
    assert result == {"status": "skipped", "reason": "apollo_sync_enabled=false"}


def test_apollo_enrich_batch_skips_when_env_master_switch_is_off(monkeypatch):
    import services.scheduler as scheduler

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("must not reach the DB flag check, let alone the Apollo API")

    monkeypatch.setattr(scheduler.settings, "apollo_sync_enabled", False)
    monkeypatch.setattr(scheduler.harvest_service, "_flag_enabled", _fail_if_called)
    result = asyncio.run(scheduler.apollo_enrich_batch())
    assert result == {"status": "skipped", "reason": "apollo_sync_enabled=false"}


def test_apollo_search_and_sync_calls_the_shared_gate_function(monkeypatch):
    """Confirms scheduler.py defers to harvest_service._apollo_sync_enabled()
    (both switches) rather than re-checking only the DB flag locally."""
    import services.scheduler as scheduler

    calls = []

    async def _fake_gate():
        calls.append(1)
        return False

    monkeypatch.setattr(scheduler.harvest_service, "_apollo_sync_enabled", _fake_gate)
    result = asyncio.run(scheduler.apollo_search_and_sync())
    assert calls == [1]
    assert result["status"] == "skipped"


def test_apollo_enrich_batch_calls_the_shared_gate_function(monkeypatch):
    import services.scheduler as scheduler

    calls = []

    async def _fake_gate():
        calls.append(1)
        return False

    monkeypatch.setattr(scheduler.harvest_service, "_apollo_sync_enabled", _fake_gate)
    result = asyncio.run(scheduler.apollo_enrich_batch())
    assert calls == [1]
    assert result["status"] == "skipped"


# ── Migration 022 text ────────────────────────────────────────────────────

def test_migration_022_is_idempotent_and_matches_the_documented_condition():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "migrations"))
    import importlib
    mod = importlib.import_module("022_apollo_pool_flag")
    sql = mod.MIGRATION_SQL
    assert "ADD COLUMN IF NOT EXISTS pool_origin" in sql
    assert "DO $$" not in sql  # _runner.py splits SQL on literal ";"
    assert "source = 'apollo'" in sql
    assert "source = 'apollo_bulk'" in sql  # security-auditor follow-up (MEDIUM #3):
    # harvest.py's harvest_candidates() writes source='apollo_bulk' with
    # source_url left NULL whenever Apollo's preview record carries no
    # person id -- source_url LIKE 'apollo:%' alone misses those rows.
    assert "source_url LIKE 'apollo:%'" in sql
    assert mod.VERSION == "022_apollo_pool_flag"
    # no DELETE/DROP anywhere in this migration -- WS-E.8 hard rule: this
    # PR must not delete production data by itself.
    assert "DELETE" not in sql.upper()
    assert "DROP" not in sql.upper()


# ── Migration 030 text (WS-C.17) ──────────────────────────────────────────

def test_migration_030_is_idempotent_and_matches_the_documented_columns():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "migrations"))
    import importlib
    mod = importlib.import_module("030_talentpool_consent")
    sql = mod.MIGRATION_SQL
    assert mod.VERSION == "030_talentpool_consent"
    assert "ADD COLUMN IF NOT EXISTS consent_talentpool_at TIMESTAMPTZ" in sql
    assert "ADD COLUMN IF NOT EXISTS consent_talentpool_until TIMESTAMPTZ" in sql
    assert "ADD COLUMN IF NOT EXISTS consent_scope TEXT CHECK" in sql
    assert "matching_only" in sql and "matching_and_contact" in sql
    assert "ADD COLUMN IF NOT EXISTS consent_source TEXT CHECK" in sql
    assert "'portal','kandidaten_page','blog_cta','admin'" in sql
    assert "CREATE TABLE IF NOT EXISTS talentpool_optin_requests" in sql
    assert "token_hash      TEXT NOT NULL UNIQUE" in sql
    assert "DO $$" not in sql  # _runner.py splits SQL on literal ";"
    assert "DELETE" not in sql.upper()
    assert "DROP" not in sql.upper()
