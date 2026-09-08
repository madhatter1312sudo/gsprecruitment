"""
Talent OS — WS-E.8 retention table.

Single source of truth for the bewaartabel (retention table), with TWO
rendered voices per row rather than one:

  - the INTERNAL voice (`categorie`, `bewaartermijn`, `bron_opmerking`,
    plus `legal_basis_ref`/`anchor_column`/`schema_ready`/`selector_sql`)
    — accountability text for docs/VERWERKINGSREGISTER.md §1.4 and
    docs/SOURCING-SOP.md §6. It names the anchor column (`date_found`,
    `rejected_at`), cites WS-ticket numbers and §-cross-references, and
    marks which periods are still an "aanname" pending the owner's
    confirmation (§6 punt 4 of the register hangs off this field — don't
    reword or drop "aanname" from a row's `bron_opmerking` without also
    updating that punt).
  - the PUBLIC voice (`public_nl` / `public_en`, a `PublicRetentionText`
    each) — the plain-language wording for website/privacy.html's two
    retention tables (`retention-table-nl` / `retention-table-en`). It is
    written for a candidate or a regulator, not a developer: no column
    names, no ticket numbers, no internal cross-references. It is NOT a
    translation of `bron_opmerking` — the two serve different readers and
    are allowed to say different things about the same period (e.g. "3
    maanden na `date_found`" internally vs. "3 maanden na de datum waarop
    wij u vonden" publicly).

Both voices live on the same `RetentionRow`, so there is exactly one place
to change a period: edit the row here, then regenerate the two Markdown
docs with `render_markdown()` (register_rows()) and update
website/privacy.html's two <tbody>s to match `public_rows("nl")` /
`public_rows("en")` (categorie, bewaartermijn, toelichting tuples, in
table order). tests/test_retention.py checks all four consumers against
this module — the register and SOP against `register_rows()`, and each
privacy.html table against its own `public_rows(lang)` — so a row changed
here without updating a consumer fails loudly instead of drifting silently.

Ten rows, matching VERWERKINGSREGISTER.md §1.4 exactly, in table order:
afgewezen sollicitant, talentpool met toestemming, gesourcete persoon
zonder reactie, prospect zonder reactie, prospect die wel reageert,
actief portalaccount zonder sollicitatie, referral, leads/quiz, geplaatste
kandidaat, logs. Three of these carry "aanname" in their Bron/opmerking
column (gesourcete persoon zonder reactie, prospect die wel reageert,
actief portalaccount zonder sollicitatie) — the register flags these as
assumptions from the SOP pending the owner's confirmation (§6.4); the
other seven are settled.

`schema_ready=False` marks a row whose anchor column does not exist in the
database yet. The purge job (services/scheduler.py) skips those
categories entirely — it never issues a query against a column that isn't
there — and reports them as "schema_not_ready" so an admin calling
GET /api/v1/admin/retention/table or POST .../retention/run can see
exactly which rows are enforced today and which need a follow-up
migration.
`consent_talentpool_until` (talentpool_consent row) is schema_ready=True as
of WS-C.17 (migrations/030_talentpool_consent.py) — see that migration and
TALENTPOOL_EXPIRED_SQL below.
`rejected_at` (candidates), `last_contacted_at` (client_prospects) and
`last_login_at` (users) are schema_ready=True as of
migrations/032_retention_anchor_columns.py — see REJECTED_APPLICANT_SQL,
PROSPECT_RESPONDING_SQL and PORTAL_ACCOUNT_INACTIVE_SQL below for the
guarded selectors and their write paths. `schema_ready=True` here means
"the column exists and a real code path fills it going forward" — it does
NOT mean every existing row is retroactively covered. Migration 032 is a
plain `ADD COLUMN`, so every row that already existed when it ran got
NULL in all three columns, and all three selectors below require
`IS NOT NULL` on their anchor column; there is deliberately no backfill
(guessing a historical `rejected_at`/`last_contacted_at` from a generic
`updated_at`, or inventing a `last_login_at` no column ever recorded,
would fabricate a date nobody actually observed). A pre-existing
candidate/prospect/user only becomes purgeable once it next goes through
the write path that stamps its column (see VERWERKINGSREGISTER.md §1.4's
paragraph under this table for the same caveat, kept in sync by hand
since it's prose, not a table cell test_retention.py parses).
`placed_candidate` stays
schema_ready=False: its `action` is "retain", so services/scheduler.py's
_category_result() reports it "not_applicable" before it ever looks at
schema_ready — this job never purges 7-year fiscal data, so schema_ready
is moot for it either way (see that row's own selector_sql comment below
for what its anchor is and why). `logs` also stays schema_ready=False
(action="infra_only", no DB column by design).

security-audit FIX FIRST (WS-E.8 retention-kolommen branch, FOURTH
round, blocking point 1): `placed_candidate`'s anchor used to be
`matches.status = 'placed'` -- a value nothing in this backend ever
writes (grep the routers: every `status = 'placed'` reference is a
SELECT/COUNT, never an UPDATE/INSERT). The real, authoritative record of
a placement is `placements` (migrations/029_placements.py,
routers/placements.py), written by the actual placement route -- the
anchor below now points there instead. This is a documentation-only
change for this row (action="retain" means its selector_sql is never
run), but it matters everywhere else in this module: every other
candidate-purging selector (CANDIDATE_NO_REACTION_GUARD_SQL,
REJECTED_APPLICANT_SQL, PORTAL_ACCOUNT_INACTIVE_SQL) now also excludes
any candidate with a `placements` row, so the 7-year floor this row
documents is never silently defeated by one of the other nine categories
anonymising the same candidate first.

`action` is one of:
  - "anonymise": run via erase_person()-style logic (routers/gdpr.py) —
    keeps the row's id (FK integrity, audit trail) but nulls PII and adds
    the person to suppression_list.
  - "hard_delete": DELETE the row outright — used only where nothing else
    references the row (a lead-only client_prospects row, a quiz/contact
    submission) and there is no suppression benefit (no repeat-contact
    risk once the row and its email are simply gone).
  - "retain": never purged by this job — the 7-year fiscal retention on
    placed candidates/invoices is a floor, not a ceiling to purge past;
    included here for documentation/visibility only.
  - "infra_only": not a database category at all (log rotation) — no
    selector runs; the row exists purely so the table is complete.
"""
from dataclasses import dataclass
from typing import Optional, Tuple


# Shared SQL, imported by services/scheduler.py (and, for the candidate
# no-reaction guards specifically, by routers/retention_admin.py's Apollo
# pool purge too) rather than duplicated there -- security-auditor
# follow-up (WS-E.8 FIX FIRST): the selectors below and the ones the
# purge job actually runs must never drift apart, so this module owns the
# one copy of each and the callers import it. CANDIDATE_NO_REACTION_GUARD_SQL
# below is that one copy for the candidate-side "did anything real happen
# since" checks -- chief-of-staff second FIX FIRST caught
# routers/retention_admin.py keeping its own independently-maintained
# near-copy of these guards (with the same dead replied_at/email bugs
# fixed here) despite this module's own claim of exactly one copy; it now
# imports and reuses this constant instead.
#
# "status = 'sourced'" alone is not proof nobody has reacted: nothing in
# this codebase moves candidates.status off 'sourced' when a match
# progresses, a client pipeline entry is created, a recruiter logs a real
# reaction, the person registers a portal account, or the person is
# placed. The five NOT EXISTS guards below check those signal tables
# directly instead of trusting one column that nothing keeps in sync.
#
# FIX (chief-of-staff second FIX FIRST, WS-E.8 retention-kolommen branch,
# blocking point 1): the first version of this guard block (still visible
# in git history) closed with two guards that were dead on arrival:
#   - `outreach_messages o WHERE o.replied_at IS NOT NULL` -- nothing in
#     this codebase ever writes replied_at (outreach is draft-only, a
#     human sends from their own mailbox and any reply lands there, not
#     in this DB -- see the comment on PROSPECT_NO_RESPONSE_SQL below,
#     first found on this same column). For candidates it was doubly dead:
#     the one INSERT into outreach_messages (routers/outreach.py
#     approve_draft) wrote neither candidate_id nor replied_at, so the
#     `o.candidate_id = c.id` half of the join could never match either.
#   - `users u WHERE LOWER(u.email) = LOWER(c.email)` -- the same
#     unreliable email-matching PORTAL_ACCOUNT_INACTIVE_SQL's own comment
#     below rejects for exactly this reason (a portal account and its
#     candidate record can carry different addresses). Fixed here the
#     same way that selector already was: via candidate_profiles, the
#     real FK erase_person() (routers/gdpr.py) trusts.
# FIX (security-audit FIX FIRST, WS-E.8 retention-kolommen branch, FOURTH
# round, blocking point 2): the sent-outreach-draft guard that used to sit
# here measured contact, not reaction -- it recorded something WE did (an
# admin clicked approve), not anything the candidate did. That inverted
# the very category this guard protects: SOURCED_NO_RESPONSE_SQL exists
# specifically to purge people who were contacted and never responded, so
# treating "we sent them a message" as permanent immunity meant nobody who
# actually belongs in "no response" could ever be purged, while a
# candidate approached over a channel approve_draft cannot complete for
# (LinkedIn: DraftCreate.target_email is a required field, but a channel=
# 'linkedin' draft still has to pass one -- an admin can only submit "",
# and approve_draft's own `if not draft["target_email"]` refusal then
# means that draft can never reach status='sent' at all) never got this
# protection in the first place, real reply or not. Both directions were
# wrong for the same reason: "sent" is not "reacted".
#
# Replaced with the one place a real reaction actually gets written down
# regardless of channel: `activities` (migrations/028_activities.py), the
# general-purpose CRM log a recruiter writes to directly whenever a
# candidate calls back, replies on LinkedIn, or otherwise engages --
# channel-independent, unlike outreach_drafts/outreach_messages, which
# only ever records what WE sent. This is deliberately unbounded (like
# the matches/pipeline_entries guards beside it) rather than
# recency-windowed against outreach_drafts.sent_at/created_at -- both
# still plain TIMESTAMP columns (migrations/010_outreach_drafts.py) -- so
# no new NOW()-comparison against those columns is introduced here (see
# migrations/033_retention_guard_fixes.py's own docstring on why that
# comparison would need a timezone fix first if one were ever added).
#
# security-audit FIX FIRST (blocking point 1, same round): also excludes
# any candidate with a real placement (migrations/029_placements.py) --
# routers/placements.py's create_placement writes candidate_id/job_id/
# client_id directly and touches neither `matches` nor `pipeline_entries`,
# so an actively placed candidate previously carried none of this guard's
# other four signals and was purgeable like anyone else. See
# tests/integration/test_retention_guards.py for the DB-backed proof: a
# candidate with an activities row, or an active placement, or a live
# portal account linked via candidate_profiles under a *different*
# e-mail address, is excluded; a candidate with none of those is still
# selected; a merely-sent (never reacted-to) outreach draft no longer
# grants immunity on its own.
CANDIDATE_NO_REACTION_GUARD_SQL = """
      AND NOT EXISTS (SELECT 1 FROM matches m WHERE m.candidate_id = c.id AND m.status <> 'suggested')
      AND NOT EXISTS (SELECT 1 FROM pipeline_entries p WHERE p.candidate_id = c.id)
      AND NOT EXISTS (
          SELECT 1 FROM activities a
          WHERE a.subject_type = 'candidate' AND a.subject_id = c.id AND a.deleted_at IS NULL
      )
      AND NOT EXISTS (
          SELECT 1 FROM candidate_profiles cpf
          JOIN users u ON u.id = cpf.user_id
          WHERE cpf.candidate_id = c.id AND u.deleted_at IS NULL
      )
      AND NOT EXISTS (SELECT 1 FROM placements pl WHERE pl.candidate_id = c.id AND pl.deleted_at IS NULL)
"""

SOURCED_NO_RESPONSE_SQL = """
    SELECT c.id, c.email FROM candidates c WHERE c.lawful_basis = $1
      AND c.status = 'sourced' AND c.date_found IS NOT NULL
      AND c.date_found <= (CURRENT_DATE - INTERVAL '3 months')
      AND c.consent_withdrawn_at IS NULL AND c.deleted_at IS NULL AND c.email IS NOT NULL
""" + CANDIDATE_NO_REACTION_GUARD_SQL

# Same "the status column isn't kept in sync" problem on the prospect
# side: routers/outreach.py never writes back to client_prospects.status
# once a draft is approved and sent, or once a reply comes in -- see
# _count_prospect_no_response()'s docstring (services/scheduler.py).
#
# FIX (chief-of-staff second FIX FIRST, WS-E.8 retention-kolommen branch,
# blocking point 1): this guard used to carry a second NOT EXISTS against
# `outreach_messages om ... om.replied_at IS NOT NULL`. Outreach is
# draft-only by design (a human sends from their own mailbox; any reply
# lands there, not in this DB), so nothing in this codebase has ever
# written replied_at -- that guard was dead code that could never exclude
# anyone. Dropped outright: the sent-draft guard below is the real signal
# ("we approached this prospect and it's still an open thread") and is
# already the same pattern used elsewhere in this module.
PROSPECT_NO_RESPONSE_SQL = """
    SELECT cp.id FROM client_prospects cp WHERE cp.status = 'new'
      AND cp.created_at <= (NOW() - INTERVAL '12 months') AND cp.opt_out_at IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM outreach_drafts od
          WHERE LOWER(od.target_email) = LOWER(cp.contact_email) AND od.target_type = 'client_prospect' AND od.status = 'sent'
      )
"""
# FIX (security-audit follow-up, WS-E.8 retention-kolommen branch, non-
# blocking pre-existing bug flagged alongside the blocking ones): the
# sent-draft guard above used to compare against
# od.target_type = 'prospect', a value nothing in this codebase ever
# writes -- routers/outreach.py's DraftCreate/create_draft and
# services/scheduler.py's draft_outreach job both write
# target_type = 'client_prospect' for this table (see
# PROSPECT_RESPONDING_SQL's own sent-draft guard below, which already
# had the right string). The guard above therefore never matched a real
# row and could never protect a prospect who had a draft sent but never
# replied -- corrected to 'client_prospect' so it actually fires.

# WS-C.17 — migrations/030_talentpool_consent.py adds
# candidates.consent_talentpool_until, so the talentpool_consent row below
# is schema_ready=True as of this PR. A candidate whose talentpool consent
# has lapsed (12 months, renewable -- SOP §1.5/§6 row 2) and was never
# renewed is purged the same way sourced_no_response/referral are: via
# erase_person() (services/scheduler.py._purge_talentpool_expired), which
# also drops them from suppression risk (they simply stop being contacted
# on this basis; SOP §1.5 "verlopen of ingetrokken toestemming = direct
# geen contact meer op deze grondslag").
#
# Security-audit follow-up (H3b): same "status alone isn't proof of no
# reaction" problem SOURCED_NO_RESPONSE_SQL guards against applies here --
# a talentpool candidate can pick up a real match, a pipeline entry, a
# sent outreach draft, or a live portal account without any of that ever
# clearing lawful_basis/consent_talentpool_until. The same
# CANDIDATE_NO_REACTION_GUARD_SQL guards apply (see that block's own
# comment above for the chief-of-staff second FIX FIRST that replaced the
# dead replied_at guard and the unreliable email join here too). A 30-day
# grace period on top of consent_talentpool_until (not just "<= NOW()")
# gives the reminder e-mail (services/scheduler.py's talentpool_reminder
# job, sent 30 days *before* expiry) room to land and be acted on before
# this selector would otherwise purge the same row -- renewing
# (re-ticking the consent) always pushes consent_talentpool_until back
# out, removing the candidate from this selector immediately.
TALENTPOOL_EXPIRED_SQL = """
    SELECT c.id, c.email FROM candidates c WHERE c.lawful_basis = 'opt_in_talentpool'
      AND c.consent_talentpool_until IS NOT NULL
      AND c.consent_talentpool_until <= (NOW() - INTERVAL '30 days')
      AND c.deleted_at IS NULL AND c.email IS NOT NULL
""" + CANDIDATE_NO_REACTION_GUARD_SQL

# migrations/032_retention_anchor_columns.py adds candidates.rejected_at,
# stamped by the only two write paths onto candidates.status
# (routers/candidates.py PATCH /api/candidates/{id} and
# routers/webhook.py's candidate_updated Hermes action) whenever status is
# set to 'rejected'. rejected_at itself is a deliberate, explicit action
# (not a default value nothing ever advances, unlike status='sourced' in
# SOURCED_NO_RESPONSE_SQL above), but a rejected candidate can still be
# reconsidered later without rejected_at being cleared -- `status =
# 'rejected'` must still hold (a later status change away from 'rejected'
# drops the row out of this selector even if rejected_at is stale), and
# the two NOT EXISTS guards additionally exclude anyone whose matches or
# pipeline_entries were touched *after* rejected_at (picked back up for
# another role since being rejected).
#
# FIX (security-audit FIX FIRST, WS-E.8 retention-kolommen branch, blocking
# point 1): both guards used to be dead code. matches.updated_at
# (migrations/019_prod_schema_alignment.py) was nullable with no default
# and no write path ever touched it -- the three places that write
# matches rows (routers/matches.py's _run_matching_for_job INSERT and
# create_match's upsert, routers/candidate.py's apply-to-job INSERT) never
# named the column, so `m.updated_at > c.rejected_at` was always NULL
# (never true) and this guard could never exclude anyone. Fixed at the
# source: all three write paths now stamp updated_at = NOW() on
# insert/upsert (see those routers), so a fresh match created after a
# rejection is now visible here. pipeline_entries.updated_at was only
# half-dead -- routers/client.py's and routers/admin.py's stage-update
# endpoints already stamped it, but the initial add-to-pipeline INSERT
# (routers/client.py) did not, so a candidate re-piped for another role
# right after rejection (before any stage change) still wasn't caught;
# that INSERT now stamps updated_at = NOW() too. Separately,
# pipeline_entries.updated_at was `TIMESTAMP` (no timezone,
# migrations/002_portal_tables.py) while candidates.rejected_at is
# `TIMESTAMPTZ` -- comparing them directly let the exclusion window drift
# with the connection's session timezone. migrations/033_retention_guard_
# fixes.py converts the column to TIMESTAMPTZ (assuming existing values
# were written in UTC, same assumption every other NOW()-stamped column
# here makes) so both sides of `p.updated_at > c.rejected_at` are the same
# type. See tests/integration/test_retention_guards.py for the DB-backed
# proof (a fresh match / a fresh pipeline entry created after rejection
# now excludes the candidate; a rejection with neither still purges).
# FIX (security-audit FIX FIRST, WS-E.8 retention-kolommen branch, FOURTH
# round, blocking point 1): a placements guard, same as
# CANDIDATE_NO_REACTION_GUARD_SQL's -- a rejected candidate later placed
# through a different job would carry a matches/pipeline_entries row only
# if that placement happened to go through the matching/pipeline flow;
# routers/placements.py's create_placement (WS-C.7) never touches either
# table, so a placement created independently of both left this row with
# no signal at all. See tests/integration/test_retention_guards.py.
REJECTED_APPLICANT_SQL = """
    SELECT id, email FROM candidates c WHERE c.status = 'rejected'
      AND c.rejected_at IS NOT NULL AND c.rejected_at <= (NOW() - INTERVAL '4 weeks')
      AND c.deleted_at IS NULL AND c.email IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM matches m WHERE m.candidate_id = c.id
            AND m.status NOT IN ('rejected') AND m.updated_at > c.rejected_at
      )
      AND NOT EXISTS (
          SELECT 1 FROM pipeline_entries p WHERE p.candidate_id = c.id AND p.updated_at > c.rejected_at
      )
      AND NOT EXISTS (SELECT 1 FROM placements pl WHERE pl.candidate_id = c.id AND pl.deleted_at IS NULL)
"""

# migrations/032_retention_anchor_columns.py adds
# client_prospects.last_contacted_at, stamped whenever an admin changes a
# prospect's status (routers/prospects.py PUT /api/v1/admin/prospects/{id}
# -- per that router's own docstring, client_prospects.status only ever
# moves by manual admin action, so a status change is the one place "we
# had contact" is recorded today) and whenever an outreach draft targeting
# this prospect is approved/sent (routers/outreach.py approve_draft).
#
# FIX (security-audit FIX FIRST, WS-E.8 retention-kolommen branch, blocking
# points 2-4): the original guard here (`cp.status != 'new'` plus the two
# NOT EXISTS reuse of PROSPECT_NO_RESPONSE_SQL's reply/sent-draft checks)
# had three separate problems, proven against real rows:
#
#   1. `status != 'new'` is not "this lead went nowhere" -- it is true for
#      every status an admin has ever typed into ProspectUpdate.status
#      (a free Optional[str], no enum), including a converted customer
#      ('klant', 'gewonnen', ...). This row's own bewaartermijn says
#      "zolang actief + 12 maanden na laatste contact" -- an active
#      customer is exactly who must never be swept up here. Rather than
#      guess at a closed vocabulary of "dead lead" status strings this
#      codebase has never defined, the guard now checks the one real,
#      already-existing signal for "this company is a live client":
#      clients.account_status (migrations/000_baseline.py, DEFAULT
#      'active'). A prospect whose company has an active clients row is
#      excluded regardless of what free-text status was typed on the
#      prospect record.
#   2. The reply guard (`outreach_messages.replied_at IS NOT NULL`) was
#      dead code -- nothing in this codebase ever writes replied_at, so
#      it could never exclude anyone (see PROSPECT_NO_RESPONSE_SQL's own
#      comment above, same column). The sent-draft guard
#      (`outreach_drafts...status = 'sent'`) was not dead but wrong in
#      the opposite direction: it checks *ever*, not *recently*, so
#      anyone ever sent an approved draft became permanently immune here
#      no matter how stale last_contacted_at later became -- while the
#      same send also re-stamps last_contacted_at (see the migration's
#      docstring above), so "recently contacted via outreach" is already
#      exactly what last_contacted_at <= NOW() - 12 months tests for.
#      Both guards are dropped: the outreach-recency protection they were
#      trying to add is already provided by last_contacted_at itself, and
#      neither guard was catching the thing it was supposed to catch
#      (a reply / an active in-flight thread) without also either never
#      firing or firing forever.
#   3. The guard never terminated -- client_prospects has no deleted_at,
#      and erase_person() (routers/gdpr.py) leaves this row's `status`
#      and `last_contacted_at` in place after anonymising it, only
#      stamping `opt_out_at`. Every daily run would therefore re-select
#      and re-erase the same already-anonymised row. Added
#      `cp.opt_out_at IS NULL`, the same guard PROSPECT_NO_RESPONSE_SQL
#      already carries and the one erase_person() actually sets.
#
# See tests/integration/test_retention_guards.py for the DB-backed proof:
# an active client's contact is excluded even at 'status=klant' and 13
# months stale; an already-erased prospect (opt_out_at set) is excluded on
# a second run; a genuinely stale, non-client, non-opted-out prospect is
# still selected.
#
# FIX (chief-of-staff second FIX FIRST, WS-E.8 retention-kolommen branch,
# blocking point 3): the client match above used to be `LOWER(company_name)
# = LOWER(company_name)` alone -- two free-text fields, filled in
# independently by whoever created the client vs. whoever created the
# prospect ("ASML Netherlands B.V." vs. "ASML" never match). Both
# `clients` and `client_prospects` also carry a `domain` column
# (migrations/000_baseline.py, migrations/012_mobile_growth.py) -- a
# harder key that does not depend on two humans having typed the company
# name identically. The guard below keeps the name match (still valid
# when it happens to agree) and adds an OR on domain, so a differently
# worded but same-domain active client is excluded too. See
# tests/integration/test_retention_guards.py for the DB-backed proof: a
# prospect at "ASML" with an active client at "ASML Netherlands B.V." but
# the same domain is excluded even though the names never match.
#
# FIX (security-audit FIX FIRST, WS-E.8 retention-kolommen branch, FOURTH
# round, blocking point 4): that domain match was itself not a hard key --
# `clients.domain` and `client_prospects.domain` are filled by independent
# code paths in incompatible shapes (an e-mail's domain part vs. a
# free-text website field that may carry "https://www." and a path, vs.
# "" from services/harvest.py when Apollo returns neither), and a bare
# `IS NOT NULL` never excludes "". Once any one client row had domain=''
# (or two differently-formatted URLs for the same real domain), the OR
# above either silently protected every empty-domain prospect or missed a
# same-company match it should have caught. Both sides are now run
# through the same normalisation core/privacy.py's normalize_domain()
# applies at write time (lower-case, strip scheme/"www.", strip
# path/query/fragment) and NULLIF'd back to NULL on '', so `IS NOT NULL`
# actually means "has a domain" again. See
# tests/integration/test_retention_guards.py for the DB-backed proof: two
# differently-formatted URLs for the same host still match, and two rows
# that both carry an empty domain no longer match each other.
#
# FIX (security-audit FIX FIRST, WS-E.8 retention-kolommen branch, FOURTH
# round, blocking point 3): `clients.account_status` now has a real write
# path (migrations/034_clients_account_status_lifecycle.py,
# routers/clients_admin.py update_client, closed set lead|active|
# inactive) instead of being read-only everywhere -- 'active' means an
# admin has confirmed the relationship, not merely that a `clients` row
# exists (every client-portal registration auto-creates one, with the
# user's own name as company_name, and that stub used to inherit the same
# DEFAULT 'active' this guard trusted).
_NORMALIZED_DOMAIN_SQL = (
    "NULLIF(LOWER(REGEXP_REPLACE(REGEXP_REPLACE(TRIM(BOTH FROM {col}), "
    "'^https?://', ''), '^www\\.', '')), '')"
)


def _domain_match_sql(left: str, right: str) -> str:
    l_norm = _NORMALIZED_DOMAIN_SQL.format(col=left)
    r_norm = _NORMALIZED_DOMAIN_SQL.format(col=right)
    return f"({l_norm} IS NOT NULL AND {l_norm} = {r_norm})"


PROSPECT_RESPONDING_SQL = f"""
    SELECT id, contact_email FROM client_prospects cp WHERE cp.status != 'new'
      AND cp.last_contacted_at IS NOT NULL AND cp.last_contacted_at <= (NOW() - INTERVAL '12 months')
      AND cp.opt_out_at IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM clients cl
          WHERE cl.account_status = 'active'
            AND (
                LOWER(cl.company_name) = LOWER(cp.company_name)
                OR {_domain_match_sql("cl.domain", "cp.domain")}
            )
      )
"""

# migrations/032_retention_anchor_columns.py adds users.last_login_at,
# stamped on every successful authentication that returns a real token
# (routers/auth.py login()/google_signin(), routers/mfa.py mfa_verify()/
# mfa_recovery()) -- never on /register or /refresh (see that migration's
# docstring). "Actief portalaccount zonder sollicitatie" means exactly
# that: an account with no real engagement, not merely one that hasn't
# logged in recently -- a candidate can be actively matched/piped/
# contacted by a recruiter without ever touching the portal, so the guard
# below excludes any user whose linked candidates row has a progressed
# match or a pipeline entry, on top of the shared reply/live-account
# guards the other selectors use.
#
# FIX (security-audit FIX FIRST, WS-E.8 retention-kolommen branch, blocking
# point 5): the guard used to link users -> candidates via
# `LOWER(c.email) = LOWER(u.email)`. A portal account and its candidate
# record can legitimately carry different addresses (a private address on
# the account, a work address on the CV, or either edited independently
# after the fact) -- routers/gdpr.py's erase_person() does not trust this
# email match either; it links the two via
# candidate_profiles.candidate_id (migrations/023_candidate_profiles_
# candidate_id.py), the FK actually written whenever a portal account is
# created/backfilled. The guard below uses that same real relation, so a
# user whose linked candidate has an active match/pipeline entry is
# protected even when the two email addresses differ.
#
# FIX (security-audit FIX FIRST, WS-E.8 retention-kolommen branch, FOURTH
# round, blocking point 1): also excludes a linked candidate with a real
# placement -- routers/placements.py's create_placement never touches
# matches/pipeline_entries (see CANDIDATE_NO_REACTION_GUARD_SQL's own
# comment above for the fuller reasoning), so an idle portal account
# belonging to an actively placed candidate previously carried none of
# this guard's two existing signals either.
PORTAL_ACCOUNT_INACTIVE_SQL = """
    SELECT id, email FROM users u WHERE u.role = 'candidate' AND u.deleted_at IS NULL
      AND u.last_login_at IS NOT NULL AND u.last_login_at <= (NOW() - INTERVAL '24 months')
      AND NOT EXISTS (
          SELECT 1 FROM candidate_profiles cpf
          JOIN candidates c ON c.id = cpf.candidate_id
          WHERE cpf.user_id = u.id
            AND (
                EXISTS (SELECT 1 FROM matches m WHERE m.candidate_id = c.id AND m.status <> 'suggested')
                OR EXISTS (SELECT 1 FROM pipeline_entries p WHERE p.candidate_id = c.id)
                OR EXISTS (SELECT 1 FROM placements pl WHERE pl.candidate_id = c.id AND pl.deleted_at IS NULL)
            )
      )
"""


@dataclass(frozen=True)
class PublicRetentionText:
    """One row's public-facing wording, as published on
    website/privacy.html — plain language for a candidate or a regulator.
    `categorie` may differ from RetentionRow.categorie only by language
    (the NL public categorie is always identical to the internal one;
    `public_en` carries the English name). `toelichting` is the public
    third column ("Toelichting"/"Note") and may be "" when the categorie
    and bewaartermijn are already self-explanatory — it is a distinct
    field from `bron_opmerking`, not a translation of it."""
    categorie: str
    bewaartermijn: str
    toelichting: str


@dataclass(frozen=True)
class RetentionRow:
    key: str
    categorie: str          # register's "Categorie" column, verbatim
    bewaartermijn: str       # register's "Bewaartermijn" column, verbatim
    bron_opmerking: str      # register's "Bron/opmerking" column, verbatim (may be "")
    legal_basis_ref: str     # citation for the period/action (register/SOP paragraph)
    anchor_column: str       # table.column the period is measured from
    action: str              # "anonymise" | "hard_delete" | "retain" | "infra_only"
    schema_ready: bool       # False == anchor_column doesn't exist in the DB yet
    selector_sql: str        # documents the intended selector; always mentions anchor_column
    public_nl: PublicRetentionText  # website/privacy.html #retention-table-nl, this row
    public_en: PublicRetentionText  # website/privacy.html #retention-table-en, this row


RETENTION_TABLE: Tuple[RetentionRow, ...] = (
    RetentionRow(
        key="rejected_applicant",
        categorie="Afgewezen sollicitant",
        bewaartermijn="4 weken na `rejected_at`",
        bron_opmerking="bron: AP/Recruitee",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 1 / SOP §6 rij 1",
        anchor_column="candidates.rejected_at",
        action="anonymise",
        schema_ready=True,
        selector_sql=REJECTED_APPLICANT_SQL,
        public_nl=PublicRetentionText(
            categorie="Afgewezen sollicitant",
            bewaartermijn="4 weken na de afwijzingsdatum",
            toelichting="",
        ),
        public_en=PublicRetentionText(
            categorie="Rejected applicant",
            bewaartermijn="4 weeks after rejection date",
            toelichting="",
        ),
    ),
    RetentionRow(
        key="talentpool_consent",
        categorie="Talentpool met expliciete toestemming",
        bewaartermijn="12 maanden, verlengbaar",
        bron_opmerking="WS-C.17",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 2 / SOP §6 rij 2",
        anchor_column="candidates.consent_talentpool_until",
        action="anonymise",
        schema_ready=True,
        selector_sql=TALENTPOOL_EXPIRED_SQL,
        public_nl=PublicRetentionText(
            categorie="Talentpool met expliciete toestemming",
            bewaartermijn="12 maanden, verlengbaar",
            toelichting="",
        ),
        public_en=PublicRetentionText(
            categorie="Talent pool with explicit consent",
            bewaartermijn="12 months, renewable",
            toelichting="",
        ),
    ),
    RetentionRow(
        key="sourced_no_response",
        categorie="Gesourcete persoon zonder reactie",
        bewaartermijn="3 maanden na `date_found` zonder reactie",
        bron_opmerking="aanname, strenger dan de 2 jaar in privacy.html",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 3 / SOP §6 rij 3, §2.4.4",
        anchor_column="candidates.date_found",
        action="anonymise",
        schema_ready=True,
        selector_sql=SOURCED_NO_RESPONSE_SQL,
        public_nl=PublicRetentionText(
            categorie="Gesourcete persoon zonder reactie",
            bewaartermijn="3 maanden na de datum waarop wij u vonden, zonder reactie",
            toelichting=(
                "Geldt voor kandidaten die wij zelf via openbare bronnen benaderen "
                "(zie §3) en die niet op ons eerste bericht reageren"
            ),
        ),
        public_en=PublicRetentionText(
            categorie="Sourced person, no response",
            bewaartermijn="3 months after the date found, if no response",
            toelichting=(
                "Applies to candidates we approach ourselves through public sources "
                "(§3) who do not respond to our first message"
            ),
        ),
    ),
    RetentionRow(
        key="prospect_no_response",
        categorie="Prospect zonder reactie",
        bewaartermijn="12 maanden",
        bron_opmerking="",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 4 / SOP §6 rij 4",
        anchor_column="client_prospects.created_at",
        action="hard_delete",
        schema_ready=True,
        selector_sql=PROSPECT_NO_RESPONSE_SQL,
        public_nl=PublicRetentionText(
            categorie="Prospect zonder reactie", bewaartermijn="12 maanden", toelichting="",
        ),
        public_en=PublicRetentionText(
            categorie="Prospect, no response", bewaartermijn="12 months", toelichting="",
        ),
    ),
    RetentionRow(
        key="prospect_responding",
        categorie="Prospect die wel reageert (relatie)",
        bewaartermijn="zolang actief + 12 maanden na laatste contact",
        bron_opmerking="aanname",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 5 / SOP §6 rij 5",
        anchor_column="client_prospects.last_contacted_at",
        action="anonymise",
        schema_ready=True,
        selector_sql=PROSPECT_RESPONDING_SQL,
        public_nl=PublicRetentionText(
            categorie="Prospect die wel reageert (relatie)",
            bewaartermijn="zolang actief + 12 maanden na laatste contact",
            toelichting="",
        ),
        public_en=PublicRetentionText(
            categorie="Prospect who responds (relationship)",
            bewaartermijn="as long as active + 12 months after last contact",
            toelichting="",
        ),
    ),
    RetentionRow(
        key="portal_account_inactive",
        categorie="Actief portalaccount zonder sollicitatie",
        bewaartermijn="zolang account actief; 24 maanden inactiviteit → verwijderen",
        bron_opmerking="aanname",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 6 / SOP §6 rij 6",
        anchor_column="users.last_login_at",
        action="anonymise",
        schema_ready=True,
        selector_sql=PORTAL_ACCOUNT_INACTIVE_SQL,
        public_nl=PublicRetentionText(
            categorie="Actief portalaccount zonder sollicitatie",
            bewaartermijn="zolang account actief; 24 maanden inactiviteit → verwijderen",
            toelichting="",
        ),
        public_en=PublicRetentionText(
            categorie="Active portal account without application",
            bewaartermijn="as long as active; 24 months inactive → deleted",
            toelichting="",
        ),
    ),
    RetentionRow(
        key="referral",
        categorie="Referral",
        bewaartermijn="zoals gesourcet (3 maanden na `date_found` zonder reactie); herkomst = referrer",
        bron_opmerking="zie §1.3",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 7 / SOP §6 rij 7, §1.3",
        anchor_column="candidates.date_found",
        action="anonymise",
        schema_ready=True,
        selector_sql=SOURCED_NO_RESPONSE_SQL,  # same guarded query; lawful_basis is the $1 parameter
        public_nl=PublicRetentionText(
            categorie="Referral",
            bewaartermijn=(
                "zoals bij sourcing (3 maanden na de datum waarop wij u vonden, "
                "zonder reactie); herkomst = referrer"
            ),
            toelichting="Aangedragen met uw toestemming vóór het eerste contact, zie §3",
        ),
        public_en=PublicRetentionText(
            categorie="Referral",
            bewaartermijn=(
                "as sourced (3 months after the date found, if no response); "
                "source = referrer"
            ),
            toelichting="Introduced with your consent before first contact, see §3",
        ),
    ),
    RetentionRow(
        key="leads_quiz",
        categorie="Leads/quiz",
        bewaartermijn="12 maanden",
        bron_opmerking="",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 8 / SOP §6 rij 8",
        anchor_column="quiz_submissions.created_at, contact_submissions.created_at",
        action="hard_delete",
        schema_ready=True,
        selector_sql=(
            "SELECT id FROM quiz_submissions WHERE created_at <= (NOW() - INTERVAL '12 months'); "
            "SELECT id FROM contact_submissions WHERE created_at <= (NOW() - INTERVAL '12 months')"
        ),
        public_nl=PublicRetentionText(
            categorie="Leads/quiz", bewaartermijn="12 maanden", toelichting="",
        ),
        public_en=PublicRetentionText(
            categorie="Leads/quiz", bewaartermijn="12 months", toelichting="",
        ),
    ),
    RetentionRow(
        key="placed_candidate",
        categorie="Geplaatste kandidaat (contract- en factuurdata)",
        bewaartermijn="7 jaar",
        bron_opmerking="fiscale bewaarplicht",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 9 / SOP §6 rij 9",
        # security-audit FIX FIRST (WS-E.8 retention-kolommen branch, FOURTH
        # round, blocking point 1): moved off `matches.status = 'placed'`,
        # a value nothing in this backend ever writes -- every occurrence
        # of that string is a SELECT/COUNT, never an UPDATE/INSERT, so the
        # anchor previously hung off a column with no real write path at
        # all. `placements.start_date` (migrations/029_placements.py) is
        # the real one: routers/placements.py's create_placement writes it
        # on every placement, and `placements` -- not `matches` -- is the
        # authoritative table for "this is a placement" (its own `status`
        # lifecycle concept|actief|beeindigd|geannuleerd, margin/billing
        # fields). Chosen over teaching the placement route to also flip a
        # `matches` row to status='placed' because a placement need not
        # have a corresponding `matches` row at all (it can be created
        # directly against a candidate_id/job_id/client_id with no prior
        # match ever having existed), so anchoring on `matches` would still
        # miss placements created that way.
        anchor_column="placements.start_date",
        action="retain",
        schema_ready=False,
        selector_sql=(
            "SELECT id FROM placements WHERE status IN ('actief', 'beeindigd') "
            "AND COALESCE(end_date, start_date) <= (CURRENT_DATE - INTERVAL '7 years') "
            "-- action=retain: 7 years is a floor, not a purge trigger; this job never deletes/anonymises "
            "this category (schema_ready=False is moot for a 'retain' row -- "
            "services/scheduler.py._category_result() reports 'not_applicable' before ever checking it). "
            "WS-C.7 (migrations/029_placements.py) added `placements` and, on candidates, the "
            "immigratiestatus columns (nationality, needs_work_permit, kennismigrant_status, "
            "ruling_30pct_status, ind_case_number) -- both fall under this same 7-year floor and are "
            "erased (not merely retained past it) by routers/gdpr.py's erase_person() alongside the "
            "rest of a placed candidate's PII once the retention floor has passed and erasure runs. "
            "A candidate with any non-deleted `placements` row is, separately, excluded outright from "
            "every anonymising selector in this module (CANDIDATE_NO_REACTION_GUARD_SQL, "
            "REJECTED_APPLICANT_SQL, PORTAL_ACCOUNT_INACTIVE_SQL) regardless of this row's own action."
        ),
        public_nl=PublicRetentionText(
            categorie="Geplaatste kandidaat (contract- en factuurdata)",
            bewaartermijn="7 jaar",
            toelichting="Fiscale bewaarplicht",
        ),
        public_en=PublicRetentionText(
            categorie="Placed candidate (contract/invoice data)",
            bewaartermijn="7 years",
            toelichting="Statutory tax retention",
        ),
    ),
    RetentionRow(
        key="logs",
        categorie="Logs",
        bewaartermijn="30 dagen (doel)",
        bron_opmerking=(
            "vandaag: max 5×20 MB per container, rotatie, geen vaste tijd "
            "(Docker json-file `max-size`/`max-file`, WS-E.6)"
        ),
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 10 / SOP §6 rij 10, B13",
        anchor_column="n.v.t. (Docker json-file log rotation, not a DB table)",
        action="infra_only",
        schema_ready=False,
        selector_sql="-- infra_only: no DB selector; enforced by Docker/Caddy log rotation, not this job",
        public_nl=PublicRetentionText(
            categorie="Logs",
            bewaartermijn=(
                "30 dagen (streeftermijn; vandaag afgedwongen via omvangsrotatie, "
                "niet via een vaste termijn)"
            ),
            toelichting="Technische logs voor beveiliging en foutopsporing",
        ),
        public_en=PublicRetentionText(
            categorie="Logs",
            bewaartermijn=(
                "30 days (target; today enforced through size-based rotation, "
                "not a fixed time limit)"
            ),
            toelichting="Technical logs for security and troubleshooting",
        ),
    ),
)

def get_row(key: str) -> Optional[RetentionRow]:
    for row in RETENTION_TABLE:
        if row.key == key:
            return row
    return None


def render_markdown(rows: Tuple[RetentionRow, ...] = RETENTION_TABLE) -> str:
    """Render the register's exact 3-column Markdown table (Categorie |
    Bewaartermijn | Bron/opmerking) so docs/VERWERKINGSREGISTER.md §1.4 and
    docs/SOURCING-SOP.md §6 can be regenerated/compared against code."""
    lines = ["| Categorie | Bewaartermijn | Bron/opmerking |", "|---|---|---|"]
    for row in rows:
        lines.append(f"| {row.categorie} | {row.bewaartermijn} | {row.bron_opmerking} |")
    return "\n".join(lines)


def register_rows(rows: Tuple[RetentionRow, ...] = RETENTION_TABLE):
    """(categorie, bewaartermijn, bron_opmerking) tuples, in table order —
    the INTERNAL voice; what tests/test_retention.py compares against the
    register's and the SOP's parsed rows."""
    return tuple((row.categorie, row.bewaartermijn, row.bron_opmerking) for row in rows)


def public_rows(lang: str, rows: Tuple[RetentionRow, ...] = RETENTION_TABLE):
    """(categorie, bewaartermijn, toelichting) tuples, in table order, in
    the PUBLIC voice for `lang` ("nl" or "en") — what
    tests/test_retention.py compares against website/privacy.html's
    #retention-table-nl / #retention-table-en. Not the same tuples as
    register_rows(): the public wording is plain-language and does not
    carry internal anchors, ticket numbers, or §-cross-references."""
    if lang not in ("nl", "en"):
        raise ValueError(f"public_rows: unknown lang {lang!r}, expected 'nl' or 'en'")
    attr = f"public_{lang}"
    return tuple(
        (getattr(row, attr).categorie, getattr(row, attr).bewaartermijn, getattr(row, attr).toelichting)
        for row in rows
    )
