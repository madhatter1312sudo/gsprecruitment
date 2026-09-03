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
    assert counted == {"sourced_no_response": 0, "prospect_no_response": 0, "referral": 0, "leads_quiz": 0}


def test_dry_run_reports_schema_not_ready_categories(patch_scheduler_db):
    rec = _Recorder()
    scheduler = patch_scheduler_db(rec)
    result = asyncio.run(scheduler.run_retention_purge(dry_run=True))
    by_key = {c["key"]: c["status"] for c in result["categories"]}
    assert by_key["rejected_applicant"] == "schema_not_ready"
    assert by_key["talentpool_consent"] == "schema_not_ready"
    assert by_key["prospect_responding"] == "schema_not_ready"
    assert by_key["portal_account_inactive"] == "schema_not_ready"
    assert by_key["placed_candidate"] == "not_applicable"
    assert by_key["logs"] == "not_applicable"
    # none of these ever issued a fetch either -- no query against a
    # column that doesn't exist in the DB
    fetched_categories = {sql for sql, _ in rec.fetch_calls}
    assert not any("rejected_at" in sql for sql in fetched_categories)
    assert not any("consent_talentpool_until" in sql for sql in fetched_categories)


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
    assert purged_keys == {"sourced_no_response", "prospect_no_response", "referral", "leads_quiz"}
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


def test_apollo_pool_purge_dry_run_default_needs_no_confirm(monkeypatch):
    async def _fake_fetch_all(sql, *args):
        return []

    from routers import retention_admin
    monkeypatch.setattr(retention_admin, "fetch_all", _fake_fetch_all)

    payload = retention_admin.ApolloPoolPurgeRequest()
    assert payload.dry_run is True
    result = asyncio.run(retention_admin.purge_apollo_pool(payload, current_user={"id": 1, "role": "admin"}))
    assert result == {"dry_run": True, "total": 0, "would_anonymise": 0, "would_hard_delete": 0}


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

    assert result == {"dry_run": False, "total": 2, "anonymised": 1, "hard_deleted": 1}
    assert erased == ["with-email@example.com"]
    delete_calls = [c for c in executed if c[0].startswith("DELETE FROM candidates")]
    assert len(delete_calls) == 1
    assert delete_calls[0][1] == ([2],)
    audit_calls = [c for c in executed if c[0].startswith("INSERT INTO audit_log")]
    assert len(audit_calls) == 1
    assert audit_calls[0][1][0] == "apollo_pool_purge"


# ── Migration 022 text ────────────────────────────────────────────────────

def test_migration_022_is_idempotent_and_matches_the_documented_condition():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "migrations"))
    import importlib
    mod = importlib.import_module("022_apollo_pool_flag")
    sql = mod.MIGRATION_SQL
    assert "ADD COLUMN IF NOT EXISTS pool_origin" in sql
    assert "DO $$" not in sql  # _runner.py splits SQL on literal ";"
    assert "source = 'apollo'" in sql
    assert "source_url LIKE 'apollo:%'" in sql
    assert mod.VERSION == "022_apollo_pool_flag"
    # no DELETE/DROP anywhere in this migration -- WS-E.8 hard rule: this
    # PR must not delete production data by itself.
    assert "DELETE" not in sql.upper()
    assert "DROP" not in sql.upper()
