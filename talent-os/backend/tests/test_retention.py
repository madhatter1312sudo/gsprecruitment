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
    assert rows == list(retention.public_rows("nl"))


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


def test_privacy_html_en_retention_table_matches_code():
    """Same check as the NL table, against the module's own EN public
    voice -- keeps the EN table tied to core/retention.py, not just to the
    NL table's category order (the check above)."""
    with open(PRIVACY_HTML_PATH, encoding="utf-8") as f:
        text = f.read()
    en_rows = _parse_html_retention_table(text, "retention-table-en")
    assert en_rows == list(retention.public_rows("en"))


def test_table_has_exactly_the_documented_ten_rows():
    assert len(retention.RETENTION_TABLE) == 10
    assert [r.key for r in retention.RETENTION_TABLE] == [
        "rejected_applicant", "talentpool_consent", "sourced_no_response",
        "prospect_no_response", "prospect_responding", "portal_account_inactive",
        "referral", "leads_quiz", "placed_candidate", "logs",
    ]


def test_three_aanname_rows_flagged():
    """T2 (owner decision, 2026-09-08, round 6): the three periods that
    used to carry "aanname" (sourced_no_response, prospect_responding,
    portal_account_inactive) are now confirmed by the owner -- none of
    the ten rows carries "aanname" any more, and VERWERKINGSREGISTER.md
    §6 punt 4 is closed accordingly (see docs/test_retention.py's own
    register/SOP-matching tests, which fail loudly if the register text
    itself still called one of these an assumption)."""
    aanname = [r.key for r in retention.RETENTION_TABLE if "aanname" in r.bron_opmerking]
    assert aanname == []
    # the three periods that used to carry "aanname" now cite the owner's
    # confirmation instead; referral cites the same date for its own
    # separate §1.3 consent point and is not one of the original three,
    # but was never an "aanname" row either -- included here so this test
    # documents the full, current set rather than only the historical three.
    confirmed = [
        r.key for r in retention.RETENTION_TABLE
        if "bevestigd door eigenaar 2026-09-08" in r.bron_opmerking
    ]
    assert confirmed == [
        "sourced_no_response", "prospect_responding", "portal_account_inactive", "referral",
    ]


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


# ── "no reaction" guards ──────────────────────────────────────────────
#
# outreach_messages.replied_at is dead code -- nothing in this codebase
# ever writes it (outreach is draft-only, a human sends from their own
# mailbox and any reply lands there, not in this DB) -- and a
# LOWER(email)=LOWER(email) join to users would be an unreliable match
# (PORTAL_ACCOUNT_INACTIVE_SQL's own comment explains why). Both guards
# below assert the real signals instead: a sent outreach_drafts row keyed
# on target_id (not free-text email), and the candidate_profiles FK join
# PORTAL_ACCOUNT_INACTIVE_SQL also uses. See
# tests/integration/test_retention_guards.py for the DB-backed proof.

def test_sourced_no_response_sql_guards_against_every_reaction_signal():
    sql = retention.SOURCED_NO_RESPONSE_SQL
    assert "status = 'sourced'" in sql
    assert "NOT EXISTS" in sql
    assert "FROM matches m" in sql and "m.status <> 'suggested'" in sql
    assert "FROM pipeline_entries p" in sql
    assert "FROM activities a" in sql
    assert "a.subject_type = 'candidate'" in sql and "a.subject_id = c.id" in sql
    assert "FROM candidate_profiles cpf" in sql
    assert "JOIN users u ON u.id = cpf.user_id" in sql and "u.deleted_at IS NULL" in sql
    assert "FROM placements pl" in sql and "pl.candidate_id = c.id" in sql
    # The dead/unreliable guards must actually be gone, not just unused.
    assert "replied_at" not in sql
    assert "LOWER(u.email) = LOWER(c.email)" not in sql
    # security-audit FIX FIRST (WS-E.8 retention-kolommen branch, FOURTH
    # round, blocking point 2): the sent-outreach-draft guard measured
    # contact, not reaction, and gave permanent immunity to anyone ever
    # sent a message regardless of whether they ever replied -- the exact
    # opposite of what "no response" is supposed to select. It must
    # actually be gone, not just unused by a regression that re-adds it.
    assert "outreach_drafts" not in sql


# WS3b split this in two. Until this spoor both rows literally shared
# SOURCED_NO_RESPONSE_SQL (only the lawful_basis $1 parameter differed);
# referral now has its own selector with one extra reaction signal on top
# of exactly the same period and guards. The two tests below say both
# halves of that out loud, so a later edit cannot quietly re-merge them or
# let the referral selector drift away from the shared period/guards.

def test_sourced_row_uses_the_shared_guarded_selector():
    sourced = retention.get_row("sourced_no_response")
    assert sourced.selector_sql is retention.SOURCED_NO_RESPONSE_SQL
    assert sourced.selector_params == ("gerechtvaardigd_belang",)


def test_referral_row_adds_the_confirmation_signal_to_the_same_guarded_selector():
    referral = retention.get_row("referral")
    assert referral.selector_sql is retention.REFERRAL_NO_RESPONSE_SQL
    assert referral.selector_params == ("toestemming_referral",)

    # The extra signal: a referral who clicked their own confirmation link
    # has reacted and must never reach the monthly review list.
    assert "referral_confirmed_at IS NULL" in retention.REFERRAL_NO_RESPONSE_SQL
    assert "referral_confirmed_at" not in retention.SOURCED_NO_RESPONSE_SQL

    # Same period and the same protective guards as the sourced row --
    # WS3b changes who counts as "no reaction", never how long we keep.
    assert "date_found + INTERVAL '3 months'" in retention.REFERRAL_NO_RESPONSE_SQL
    assert "date_found <= (CURRENT_DATE - INTERVAL '3 months')" in retention.REFERRAL_NO_RESPONSE_SQL
    assert retention.CANDIDATE_NO_REACTION_GUARD_SQL in retention.REFERRAL_NO_RESPONSE_SQL


def test_referral_and_sourced_keep_the_same_public_retention_period():
    """The four consumers of core/retention.py (register, privacy.html,
    the approval list, the tests) must keep showing identical periods --
    splitting the selector must not have moved the published term."""
    sourced = retention.get_row("sourced_no_response")
    referral = retention.get_row("referral")
    assert "3 maanden" in sourced.bewaartermijn
    assert "3 maanden" in referral.bewaartermijn
    assert "3 maanden" in referral.public_nl.bewaartermijn
    assert "3 months" in referral.public_en.bewaartermijn


def test_prospect_no_response_sql_guards_against_sent_drafts():
    """The replied_at guard this test used to also check for is gone --
    chief-of-staff second FIX FIRST (blocking point 1): nothing ever
    writes outreach_messages.replied_at, so it was dead code that could
    never exclude a prospect. The sent-draft guard is the real,
    already-working signal and stays."""
    sql = retention.PROSPECT_NO_RESPONSE_SQL
    assert "status = 'new'" in sql
    assert "FROM outreach_drafts od" in sql and "od.status = 'sent'" in sql
    assert "replied_at" not in sql
    assert retention.get_row("prospect_no_response").selector_sql is retention.PROSPECT_NO_RESPONSE_SQL


# ── WS-C.17: talentpool_consent is now schema_ready ───────────────────────

def test_talentpool_expired_sql_selects_expired_opt_in_talentpool_only():
    sql = retention.TALENTPOOL_EXPIRED_SQL
    assert "lawful_basis = 'opt_in_talentpool'" in sql
    assert "consent_talentpool_until" in sql
    assert "deleted_at IS NULL" in sql


def test_talentpool_expired_sql_has_a_30_day_grace_period_past_expiry():
    """Security-audit fix H3b: not just '<= NOW()' -- a 30-day grace past
    consent_talentpool_until, giving the reminder e-mail room to land and
    be acted on before this selector would purge the same row."""
    sql = retention.TALENTPOOL_EXPIRED_SQL
    assert "consent_talentpool_until <= (NOW() - INTERVAL '30 days')" in sql


def test_talentpool_expired_sql_guards_against_every_reaction_signal():
    """Security-audit fix H3b, guards refreshed by the chief-of-staff
    second FIX FIRST and the fourth-round FIX FIRST: same
    CANDIDATE_NO_REACTION_GUARD_SQL guards as SOURCED_NO_RESPONSE_SQL --
    status/lawful_basis alone is not proof a talentpool candidate never
    reacted, and the guard is the real activities/FK-join/placements
    version, not the dead replied_at/email one, nor the sent-draft one
    that measured contact instead of reaction."""
    sql = retention.TALENTPOOL_EXPIRED_SQL
    assert "NOT EXISTS" in sql
    assert "FROM matches m" in sql and "m.status <> 'suggested'" in sql
    assert "FROM pipeline_entries p" in sql
    assert "FROM activities a" in sql
    assert "a.subject_type = 'candidate'" in sql and "a.subject_id = c.id" in sql
    assert "FROM candidate_profiles cpf" in sql
    assert "JOIN users u ON u.id = cpf.user_id" in sql and "u.deleted_at IS NULL" in sql
    assert "FROM placements pl" in sql and "pl.candidate_id = c.id" in sql
    assert "replied_at" not in sql
    assert "LOWER(u.email) = LOWER(c.email)" not in sql
    assert "outreach_drafts" not in sql
    assert sql.endswith(retention.CANDIDATE_NO_REACTION_GUARD_SQL)


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


# ── WS-E.8 follow-up (migrations/032_retention_anchor_columns.py): the
# three anchor columns that made rejected_applicant/prospect_responding/
# portal_account_inactive schema_not_ready now exist ────────────────────

def test_rejected_applicant_row_is_schema_ready_with_shared_selector():
    row = retention.get_row("rejected_applicant")
    assert row.schema_ready is True
    assert row.action == "anonymise"
    assert row.anchor_column == "candidates.rejected_at"
    assert row.selector_sql is retention.REJECTED_APPLICANT_SQL


def test_rejected_applicant_sql_requires_status_rejected_and_guards_against_later_activity():
    """A candidate can be marked rejected and later picked back up for a
    different role -- status must still be 'rejected' and no match/
    pipeline_entries activity may have happened after rejected_at."""
    sql = retention.REJECTED_APPLICANT_SQL
    assert "status = 'rejected'" in sql
    assert "rejected_at" in sql and "INTERVAL '4 weeks'" in sql
    assert "FROM matches m" in sql and "m.updated_at > c.rejected_at" in sql
    assert "FROM pipeline_entries p" in sql and "p.updated_at > c.rejected_at" in sql
    # security-audit FIX FIRST (WS-E.8 retention-kolommen branch, FOURTH
    # round, blocking point 1): a placement never touches matches/
    # pipeline_entries (routers/placements.py create_placement), so it
    # needs its own guard here too.
    assert "FROM placements pl" in sql and "pl.candidate_id = c.id" in sql


def test_prospect_responding_row_is_schema_ready_with_shared_selector():
    row = retention.get_row("prospect_responding")
    assert row.schema_ready is True
    assert row.action == "anonymise"
    assert row.anchor_column == "client_prospects.last_contacted_at"
    assert row.selector_sql is retention.PROSPECT_RESPONDING_SQL


def test_prospect_responding_sql_guards_against_active_clients_and_opt_out():
    """Security-audit FIX FIRST (retention-kolommen branch, blocking
    points 2-4): status/last_contacted_at alone used to let this row
    anonymise a converted customer (any non-'new' status, including
    'klant') and never terminate (no opt_out_at guard, even though
    erase_person() sets it). The reply/sent-draft NOT EXISTS guards this
    row used to reuse from PROSPECT_NO_RESPONSE_SQL are gone -- replied_at
    is never written anywhere in this codebase (dead code) and the
    sent-draft check gave permanent immunity regardless of how stale
    last_contacted_at later became, which is already what last_contacted_at
    itself tests for. The real, working guards now are: opt_out_at (so an
    already-erased row drops out for good) and clients.account_status
    (so an active client relationship is never purged, matching this
    row's own "zolang actief" bewaartermijn).

    chief-of-staff second FIX FIRST (blocking point 3): company_name
    equality alone is two free-text fields ("ASML" vs. "ASML Netherlands
    B.V." never match) -- the guard now also matches on the domain column
    both tables carry, a harder key."""
    sql = retention.PROSPECT_RESPONDING_SQL
    assert "status != 'new'" in sql
    assert "last_contacted_at" in sql and "INTERVAL '12 months'" in sql
    assert "opt_out_at IS NULL" in sql
    assert "FROM clients cl" in sql and "cl.account_status = 'active'" in sql
    assert "cl.company_name" in sql and "cp.company_name" in sql
    assert "cl.domain" in sql and "cp.domain" in sql
    # The dead/contradictory outreach guards must actually be gone, not
    # just unused -- a regression that re-adds them re-creates the
    # permanent-immunity bug (point 4) even if a later edit also fixes
    # points 2/3.
    assert "outreach_messages" not in sql
    assert "outreach_drafts" not in sql


def test_portal_account_inactive_row_is_schema_ready_with_shared_selector():
    row = retention.get_row("portal_account_inactive")
    assert row.schema_ready is True
    assert row.action == "anonymise"
    assert row.anchor_column == "users.last_login_at"
    assert row.selector_sql is retention.PORTAL_ACCOUNT_INACTIVE_SQL


def test_portal_account_inactive_sql_guards_against_a_linked_candidate_with_real_signals():
    """'Actief portalaccount zonder sollicitatie' means no real engagement
    -- not merely no recent login. A candidate can be matched/piped
    without ever logging into the portal.

    Security-audit FIX FIRST (retention-kolommen branch, blocking point 5):
    this used to link users -> candidates via LOWER(email) = LOWER(email),
    which a portal account and its candidate record don't have to share
    (a private address on the account vs. a work address on the CV).
    routers/gdpr.py's erase_person() doesn't trust that match either --
    it links the two via candidate_profiles.candidate_id
    (migrations/023_candidate_profiles_candidate_id.py), the real FK, so
    the guard now joins through that same relation instead of email."""
    sql = retention.PORTAL_ACCOUNT_INACTIVE_SQL
    assert "role = 'candidate'" in sql
    assert "last_login_at" in sql and "INTERVAL '18 months'" in sql
    assert "FROM candidate_profiles cpf" in sql
    assert "JOIN candidates c ON c.id = cpf.candidate_id" in sql
    assert "cpf.user_id = u.id" in sql
    assert "FROM matches m" in sql and "m.status <> 'suggested'" in sql
    assert "FROM pipeline_entries p" in sql
    # security-audit FIX FIRST (WS-E.8 retention-kolommen branch, FOURTH
    # round, blocking point 1): a placement never touches matches/
    # pipeline_entries either.
    assert "FROM placements pl" in sql and "pl.candidate_id = c.id" in sql
    # The old email-based join must actually be gone -- a regression that
    # re-adds it alongside the FK join would silently widen the guard back
    # open for any row whose two addresses happen to match while still
    # passing a naive "does this string appear" check.
    assert "LOWER(c.email) = LOWER(u.email)" not in sql


def test_sourced_no_response_query_excludes_a_candidate_with_a_progressed_match(monkeypatch):
    """End-to-end guard check against a fake DB that actually applies the
    WHERE clause semantics, not just a substring check on the SQL text --
    a candidate with a non-'suggested' match, a pipeline entry, a
    recorded activity, a live portal account, or a placement must never
    come back. (See tests/integration/test_retention_guards.py for the
    real-Postgres, real-write-path proof this module only fakes.)"""
    import services.scheduler as scheduler

    candidates = {
        1: {"id": 1, "email": "clean@example.com"},        # no signals -- eligible
        2: {"id": 2, "email": "has-match@example.com"},     # progressed match
        3: {"id": 3, "email": "has-pipeline@example.com"},  # pipeline entry
        4: {"id": 4, "email": "has-activity@example.com"},  # recorded activity (a real reaction)
        5: {"id": 5, "email": "has-account@example.com"},   # live portal account
        6: {"id": 6, "email": "has-placement@example.com"},  # placed candidate
    }
    signals = {
        "matches": {2},
        "pipeline_entries": {3},
        "activities": {4},
        "candidate_profiles": {5},
        "placements": {6},
    }

    async def _fake_fetch_all(sql, *args):
        assert sql is retention.SOURCED_NO_RESPONSE_SQL
        assert args == ("gerechtvaardigd_belang",)
        return [
            c for cid, c in candidates.items()
            if cid not in signals["matches"] and cid not in signals["pipeline_entries"]
            and cid not in signals["activities"] and cid not in signals["candidate_profiles"]
            and cid not in signals["placements"]
        ]

    monkeypatch.setattr(scheduler, "fetch_all", _fake_fetch_all)
    rows = asyncio.run(scheduler._live_rows_for_category(retention.get_row("sourced_no_response")))
    assert [r["id"] for r in rows] == [1]


def test_live_rows_for_category_rejected_applicant_calls_the_shared_selector(monkeypatch):
    import services.scheduler as scheduler

    async def _fake_fetch_all(sql, *args):
        assert sql is retention.REJECTED_APPLICANT_SQL
        assert args == ()
        return [{"id": 1, "email": "rejected@example.com"}]

    monkeypatch.setattr(scheduler, "fetch_all", _fake_fetch_all)
    rows = asyncio.run(scheduler._live_rows_for_category(retention.get_row("rejected_applicant")))
    assert [r["id"] for r in rows] == [1]


def test_live_rows_for_category_prospect_responding_calls_the_shared_selector(monkeypatch):
    import services.scheduler as scheduler

    async def _fake_fetch_all(sql, *args):
        assert sql is retention.PROSPECT_RESPONDING_SQL
        assert args == ()
        return [{"id": 1, "contact_email": "prospect@example.com"}]

    monkeypatch.setattr(scheduler, "fetch_all", _fake_fetch_all)
    rows = asyncio.run(scheduler._live_rows_for_category(retention.get_row("prospect_responding")))
    assert [r["id"] for r in rows] == [1]


def test_live_rows_for_category_portal_account_inactive_calls_the_shared_selector(monkeypatch):
    import services.scheduler as scheduler

    async def _fake_fetch_all(sql, *args):
        assert sql is retention.PORTAL_ACCOUNT_INACTIVE_SQL
        assert args == ()
        return [{"id": 1, "email": "inactive@example.com"}]

    monkeypatch.setattr(scheduler, "fetch_all", _fake_fetch_all)
    rows = asyncio.run(scheduler._live_rows_for_category(retention.get_row("portal_account_inactive")))
    assert [r["id"] for r in rows] == [1]


def test_live_rows_for_category_prospect_no_response_calls_the_shared_selector(monkeypatch):
    """prospect_no_response used to be its own scheduler._count_* wrapper --
    now it runs through the same generic path as every other category,
    reading RetentionRow.subject_table/email_field/selector_params instead
    of a per-category lookup."""
    import services.scheduler as scheduler

    async def _fake_fetch_all(sql, *args):
        assert sql is retention.PROSPECT_NO_RESPONSE_SQL
        assert args == ()
        return [{"id": 1, "contact_email": "no-response@example.com"}]

    monkeypatch.setattr(scheduler, "fetch_all", _fake_fetch_all)
    rows = asyncio.run(scheduler._live_rows_for_category(retention.get_row("prospect_no_response")))
    assert [r["id"] for r in rows] == [1]


def test_live_rows_for_category_leads_quiz_runs_both_tables(monkeypatch):
    import services.scheduler as scheduler

    async def _fake_fetch_all(sql, *args):
        if sql is retention.LEADS_QUIZ_SQL:
            return [{"id": 1}]
        assert sql is retention.CONTACT_SUBMISSIONS_SQL
        return [{"id": 2}]

    monkeypatch.setattr(scheduler, "fetch_all", _fake_fetch_all)
    rows = asyncio.run(scheduler._live_rows_for_category(retention.get_row("leads_quiz")))
    assert sorted(r["id"] for r in rows) == [1, 2]


def test_live_rows_for_category_raises_for_a_row_missing_subject_table():
    """H2r/M2r follow-up: a category reaching this function without a
    subject_table/email_field must raise, not silently return [] -- an
    empty list here would make generate_retention_review()'s
    _retire_stale_pending() call mark every already-pending item in that
    category 'no_longer_eligible', as if a protective signal had appeared
    everywhere at once."""
    import dataclasses
    import services.scheduler as scheduler

    bogus = dataclasses.replace(
        retention.get_row("rejected_applicant"), key="bogus", subject_table="", email_field="",
    )
    with pytest.raises(ValueError):
        asyncio.run(scheduler._live_rows_for_category(bogus))


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


# ── WS-E.10 (owner decision, retention-kolommen branch, fifth round): ────
# run_retention_purge()/retention_purge_job()/_category_result() and every
# _purge_* helper are gone outright, not merely defaulted off -- see
# core/retention.py's and services/scheduler.py's own module docstrings,
# and tests/test_ws_e10_no_unapproved_purge_path.py for the structural
# guard that a later change cannot silently bring a direct-purge path
# back without a test failing. What is left below only ever counts or
# queues.

def test_run_retention_purge_and_friends_no_longer_exist():
    """The functions that used to purge directly are gone, not merely
    unused -- a regression that re-adds one of them under the old name
    would pass every other test in this file silently."""
    import services.scheduler as scheduler
    for name in (
        "run_retention_purge", "retention_purge_job", "_category_result",
        "_purge_sourced_no_response", "_purge_talentpool_expired",
        "_purge_rejected_applicants", "_purge_prospect_responding",
        "_purge_portal_account_inactive", "_purge_prospect_no_response",
        "_purge_leads_quiz",
    ):
        assert not hasattr(scheduler, name), f"scheduler.{name} must not exist any more"


def test_generate_retention_review_only_ever_counts_and_queues(patch_scheduler_db):
    """The monthly review job never calls erase_person() and never issues
    a DELETE/UPDATE against a candidate/prospect/user/quiz/contact row --
    the only execute() calls it makes are INSERT/UPDATE against
    retention_review_items itself."""
    rec = _Recorder()
    scheduler = patch_scheduler_db(rec)
    result = asyncio.run(scheduler.generate_retention_review())
    assert "categories" in result
    for sql, _args in rec.execute_calls:
        assert "retention_review_items" in sql, sql
        for forbidden_table in ("candidates", "client_prospects", "users", "quiz_submissions", "contact_submissions"):
            # the review_items UPDATE/INSERT text itself never names these
            # tables -- only the (unused-here) hard_delete/anonymise path
            # in routers/retention_admin.py ever does.
            assert f"FROM {forbidden_table}" not in sql and f"DELETE FROM {forbidden_table}" not in sql


def test_generate_retention_review_covers_every_actionable_category(patch_scheduler_db):
    rec = _Recorder()
    scheduler = patch_scheduler_db(rec)
    result = asyncio.run(scheduler.generate_retention_review())
    categories = result["categories"]
    assert set(categories) == {
        "sourced_no_response", "referral", "talentpool_consent", "rejected_applicant",
        "prospect_responding", "portal_account_inactive", "prospect_no_response",
        "leads_quiz", "apollo_pool_purge",
    }
    # placed_candidate (retain) and logs (infra_only) never reach the
    # queue -- same reasoning core/retention.py's docstring gives for why
    # they were never purged by the old job either.
    assert "placed_candidate" not in categories
    assert "logs" not in categories


def test_generate_retention_review_records_error_and_skips_retire_for_a_failing_category(monkeypatch):
    """H2r: a category whose selector raises (e.g. a foreign-key violation
    surfacing through a soft-deleted row) must not abort the whole run and
    must not be silently treated as an empty result -- an empty result
    would make _retire_stale_pending() mark every already-pending item in
    that one category 'no_longer_eligible', which means "a protective
    signal appeared", not "the query is broken"."""
    import services.scheduler as scheduler

    executed = []

    async def _fake_fetch_all(sql, *args):
        if sql is retention.REJECTED_APPLICANT_SQL:
            raise RuntimeError("simulated foreign-key violation")
        return []

    async def _fake_execute(sql, *args):
        executed.append((sql, args))
        return "OK"

    monkeypatch.setattr(scheduler, "fetch_all", _fake_fetch_all)
    monkeypatch.setattr(scheduler, "execute", _fake_execute)

    result = asyncio.run(scheduler.generate_retention_review())
    assert result["categories"]["rejected_applicant"] == {"status": "error"}
    # every other category still ran normally
    assert result["categories"]["sourced_no_response"] == {"queued": 0}
    # the failing category must never have been retired/upserted against
    touched_categories = {args[0] for _, args in executed if args}
    assert "rejected_applicant" not in touched_categories


def test_talentpool_optin_requests_cleanup_job_is_unaffected_by_ws_e10():
    """talentpool_optin_requests cleanup is not one of the ten guarded
    categories the owner moved to human review (see that job's own
    docstring for why) -- it must still exist as its own callable."""
    import services.scheduler as scheduler
    assert hasattr(scheduler, "talentpool_optin_requests_cleanup_job")


# ── Admin endpoints -- POST .../retention/run counts only, always ───────

def test_run_retention_endpoint_dry_run_default_returns_counts(monkeypatch, patch_scheduler_db):
    rec = _Recorder()
    patch_scheduler_db(rec)
    from routers import retention_admin

    payload = retention_admin.RetentionRunRequest()
    assert payload.dry_run is True
    result = asyncio.run(retention_admin.run_retention(payload, current_user={"id": 1, "role": "admin"}))
    assert result["dry_run"] is True
    assert rec.execute_calls == []


def test_run_retention_endpoint_dry_run_false_is_refused_regardless_of_confirm(patch_scheduler_db):
    """WS-E.10: dry_run=false is refused no matter what confirm carries --
    there is no confirm value that makes this endpoint purge any more."""
    rec = _Recorder()
    patch_scheduler_db(rec)
    from fastapi import HTTPException
    from routers import retention_admin

    for confirm in (None, "PURGE", "anything"):
        payload = retention_admin.RetentionRunRequest(dry_run=False, confirm=confirm)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(retention_admin.run_retention(payload, current_user={"id": 1, "role": "admin"}))
        assert exc_info.value.status_code == 410
    assert rec.execute_calls == []


def test_apollo_pool_purge_target_sql_carries_all_six_guards():
    """security-auditor follow-up (WS-E.8 HIGH #2): the same reaction
    signals as the retention job's sourced_no_response guard, plus the
    presented-candidate guard specific to this pool.

    chief-of-staff second FIX FIRST (blocking point 1): this file used to
    keep its own copy of the four shared guards, with the same dead
    replied_at/email bugs -- it now reuses
    core.retention.CANDIDATE_NO_REACTION_GUARD_SQL verbatim, so this test
    asserts that identity rather than re-checking the guard text a second
    time (that text is already covered by
    test_sourced_no_response_sql_guards_against_every_reaction_signal).

    security-audit FIX FIRST (WS-E.8 retention-kolommen branch, FOURTH
    round): the shared guard grew from four to five NOT EXISTS clauses
    (activities replaced the dead sent-draft one, and placements was
    added), so this pool's own guard count grows from five to six."""
    from core import retention
    from routers import retention_admin

    sql = retention.APOLLO_POOL_TARGET_SQL
    assert retention.CANDIDATE_NO_REACTION_GUARD_SQL in sql
    assert "replied_at" not in sql
    assert "LOWER(u.email) = LOWER(" not in sql
    assert "FROM outreach_drafts d" in sql and "d.presented_candidate_id" in sql
    assert sql.count("NOT EXISTS") == 6
    # the unguarded pool query is a strict prefix -- the guards are
    # additive filters on top of it, not a different candidate set
    assert sql.startswith(retention.APOLLO_POOL_ROWS_SQL)


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
        from core import retention as _retention
        if sql is _retention.APOLLO_POOL_ROWS_SQL:
            return [{"id": 1, "email": "a@example.com"}, {"id": 2, "email": "b@example.com"}]
        assert sql is _retention.APOLLO_POOL_TARGET_SQL
        return [{"id": 1, "email": "a@example.com"}]  # id=2 excluded by a guard

    monkeypatch.setattr(retention_admin, "fetch_all", _fake_fetch_all)
    payload = retention_admin.ApolloPoolPurgeRequest()
    result = asyncio.run(retention_admin.purge_apollo_pool(payload, current_user={"id": 1, "role": "admin"}))
    assert result == {
        "dry_run": True, "total": 1, "would_anonymise": 1, "would_hard_delete": 0, "skipped": 1,
    }


def test_apollo_pool_purge_real_run_is_refused_regardless_of_confirm(monkeypatch):
    """WS-E.10 (owner decision, fifth round): the dry_run=false branch
    that used to actually anonymise/delete here is gone outright -- not
    merely gated behind a stronger confirm string. A real deletion for
    this pool now only ever happens via the same review-queue approve
    endpoint every other category uses
    (category='apollo_pool_purge')."""
    rows = [{"id": 1, "email": "with-email@example.com"}, {"id": 2, "email": None}]
    executed = []

    async def _fake_fetch_all(sql, *args):
        return rows

    async def _fake_execute(sql, *args):
        executed.append((sql, args))
        return "OK"

    from fastapi import HTTPException
    from routers import retention_admin
    monkeypatch.setattr(retention_admin, "fetch_all", _fake_fetch_all)
    monkeypatch.setattr(retention_admin, "execute", _fake_execute)

    for confirm in (None, "DELETE APOLLO POOL", "anything"):
        payload = retention_admin.ApolloPoolPurgeRequest(dry_run=False, confirm=confirm)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(retention_admin.purge_apollo_pool(payload, current_user={"id": 7, "role": "admin"}))
        assert exc_info.value.status_code == 410
    assert executed == []  # never wrote anything, whatever confirm carried


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


# ── Migration 034 text (L2: backfill visibility) ──────────────────────────

def test_migration_034_logs_the_backfilled_client_ids_before_updating_them():
    """L2 (security-audit round 5): migration 034's account_status
    backfill silently reclassifies existing 'active' clients to 'lead' --
    the affected ids must be logged to audit_log (json.dumps'd via jsonb_
    build_object, never a raw dict) in a SELECT that runs strictly before
    the UPDATE that changes them, so the owner can see who was touched
    after deploying it."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "migrations"))
    import importlib
    mod = importlib.import_module("034_clients_account_status_lifecycle")
    sql = mod.MIGRATION_SQL
    assert mod.VERSION == "034_clients_account_status_lifecycle"
    audit_idx = sql.index("INSERT INTO audit_log")
    assert "retention_migration_034_backfill" in sql
    assert "jsonb_build_object" in sql and "jsonb_agg(id)" in sql
    update_idx = sql.index(
        "UPDATE clients SET account_status = 'lead'\n    WHERE account_status = 'active'"
    )
    assert audit_idx < update_idx
    assert "DELETE" not in sql.upper()
    assert "DO $$" not in sql


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
    assert "ADD COLUMN IF NOT EXISTS consent_reminder_sent_at TIMESTAMPTZ" in sql
    assert "CREATE TABLE IF NOT EXISTS talentpool_optin_requests" in sql
    assert "token_hash      TEXT NOT NULL UNIQUE" in sql
    assert "DO $$" not in sql  # _runner.py splits SQL on literal ";"
    assert "DELETE" not in sql.upper()
    assert "DROP" not in sql.upper()


# ── privacy.html: de notice van 30 dagen (reparatieronde) ────────────────
#
# De pagina zei "na dezelfde 18 maanden plus 30 dagen" voor de twee
# mailloze gevallen (blokkeerlijst en onbezorgbaar adres). Dat is te
# precies en daarmee onjuist: core/retention.py's
# _DORMANT_WARNING_WHERE_SQL kan de skip-stempel al vanaf 17 maanden
# zetten, en PORTAL_ACCOUNT_INACTIVE_SQL eist vervolgens 18 maanden
# inactiviteit EN een stempel van minstens 30 dagen oud. Wie op 17
# maanden wordt gestempeld, komt dus op 18 maanden op de lijst -- niet op
# 19. Wat wél voor iedereen klopt, en wat de pagina nu zegt: nooit eerder
# dan 18 maanden, en nooit eerder dan 30 dagen na die notitie.

def test_privacy_html_does_not_add_up_the_18_months_and_the_30_days():
    with open(PRIVACY_HTML_PATH, encoding="utf-8") as f:
        text = f.read()
    assert "plus 30 dagen" not in text
    assert "plus 30 days" not in text
    assert text.count("na dezelfde 18 maanden, en nooit eerder dan 30 dagen na die notitie") == 2
    assert text.count("after the same 18 months, and never sooner than 30 days after that note") == 2


def test_the_skip_stamp_can_be_set_before_18_months_which_is_why_the_wording_changed():
    """De reden dat de zin hierboven niet mag optellen, in code: de
    waarschuwing (en dus de skip-stempel) begint bij 17 maanden, terwijl
    de beoordelingslijst zelf 18 maanden eist."""
    assert "INTERVAL '17 months'" in retention.DORMANT_WARNING_SQL
    assert "INTERVAL '18 months'" in retention.PORTAL_ACCOUNT_INACTIVE_SQL
    assert "INTERVAL '30 days'" in retention.PORTAL_ACCOUNT_INACTIVE_SQL
