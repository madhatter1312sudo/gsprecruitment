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
schema_ready — this job never purges 7-year fiscal data, so a dedicated
invoice-date column would never be queried or written to by anything and
is deliberately not added here (see that migration's docstring). `logs`
also stays schema_ready=False (action="infra_only", no DB column by
design).

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


# Shared SQL, imported by services/scheduler.py rather than duplicated
# there -- security-auditor follow-up (WS-E.8 FIX FIRST): the selectors
# below and the ones the purge job actually runs must never drift apart,
# so this module owns the one copy of each and the job imports it.
#
# "status = 'sourced'" alone is not proof nobody has reacted: nothing in
# this codebase moves candidates.status off 'sourced' when a match
# progresses, a client pipeline entry is created, an outreach reply comes
# in, or the person registers a portal account. The four NOT EXISTS
# guards check those signal tables directly instead of trusting one
# column that nothing keeps in sync.
SOURCED_NO_RESPONSE_SQL = """
    SELECT c.id, c.email FROM candidates c WHERE c.lawful_basis = $1
      AND c.status = 'sourced' AND c.date_found IS NOT NULL
      AND c.date_found <= (CURRENT_DATE - INTERVAL '3 months')
      AND c.consent_withdrawn_at IS NULL AND c.deleted_at IS NULL AND c.email IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM matches m WHERE m.candidate_id = c.id AND m.status <> 'suggested')
      AND NOT EXISTS (SELECT 1 FROM pipeline_entries p WHERE p.candidate_id = c.id)
      AND NOT EXISTS (SELECT 1 FROM outreach_messages o WHERE o.candidate_id = c.id AND o.replied_at IS NOT NULL)
      AND NOT EXISTS (SELECT 1 FROM users u WHERE LOWER(u.email) = LOWER(c.email) AND u.deleted_at IS NULL)
"""

# Same "the status column isn't kept in sync" problem on the prospect
# side: routers/outreach.py never writes back to client_prospects.status
# once a draft is approved and sent, or once a reply comes in -- see
# _count_prospect_no_response()'s docstring (services/scheduler.py).
# outreach_drafts has no reply column of its own (only outreach_messages
# does, once a draft becomes an actually-sent message), so the reply
# guard runs against outreach_messages; a sent-but-not-yet-replied draft
# is still caught by the second NOT EXISTS.
PROSPECT_NO_RESPONSE_SQL = """
    SELECT cp.id FROM client_prospects cp WHERE cp.status = 'new'
      AND cp.created_at <= (NOW() - INTERVAL '12 months') AND cp.opt_out_at IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM outreach_messages om
          WHERE LOWER(om.recipient_email) = LOWER(cp.contact_email) AND om.replied_at IS NOT NULL
      )
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
# reply, or a live portal account without any of that ever clearing
# lawful_basis/consent_talentpool_until. The same four NOT EXISTS guards
# apply. A 30-day grace period on top of consent_talentpool_until (not
# just "<= NOW()") gives the reminder e-mail (services/scheduler.py's
# talentpool_reminder job, sent 30 days *before* expiry) room to land and
# be acted on before this selector would otherwise purge the same row --
# renewing (re-ticking the consent) always pushes consent_talentpool_until
# back out, removing the candidate from this selector immediately.
TALENTPOOL_EXPIRED_SQL = """
    SELECT c.id, c.email FROM candidates c WHERE c.lawful_basis = 'opt_in_talentpool'
      AND c.consent_talentpool_until IS NOT NULL
      AND c.consent_talentpool_until <= (NOW() - INTERVAL '30 days')
      AND c.deleted_at IS NULL AND c.email IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM matches m WHERE m.candidate_id = c.id AND m.status <> 'suggested')
      AND NOT EXISTS (SELECT 1 FROM pipeline_entries p WHERE p.candidate_id = c.id)
      AND NOT EXISTS (SELECT 1 FROM outreach_messages o WHERE o.candidate_id = c.id AND o.replied_at IS NOT NULL)
      AND NOT EXISTS (SELECT 1 FROM users u WHERE LOWER(u.email) = LOWER(c.email) AND u.deleted_at IS NULL)
"""

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
PROSPECT_RESPONDING_SQL = """
    SELECT id, contact_email FROM client_prospects cp WHERE cp.status != 'new'
      AND cp.last_contacted_at IS NOT NULL AND cp.last_contacted_at <= (NOW() - INTERVAL '12 months')
      AND cp.opt_out_at IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM clients cl
          WHERE LOWER(cl.company_name) = LOWER(cp.company_name) AND cl.account_status = 'active'
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
        anchor_column="matches.updated_at (status='placed')",
        action="retain",
        schema_ready=False,
        selector_sql=(
            "SELECT id FROM matches WHERE status = 'placed' "
            "AND updated_at <= (NOW() - INTERVAL '7 years') "
            "-- action=retain: 7 years is a floor, not a purge trigger; this job never deletes/anonymises "
            "this category. No dedicated invoice-date column exists yet either (schema_ready=False). "
            "WS-C.7 (migrations/029_placements.py) added `placements` and, on candidates, the "
            "immigratiestatus columns (nationality, needs_work_permit, kennismigrant_status, "
            "ruling_30pct_status, ind_case_number) -- both fall under this same 7-year floor and are "
            "erased (not merely retained past it) by routers/gdpr.py's erase_person() alongside the "
            "rest of a placed candidate's PII once the retention floor has passed and erasure runs."
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
