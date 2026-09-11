"""
Talent OS — WS-E.8/WS-E.10 retention table.

Single source of truth for the bewaartabel (retention table), with TWO
rendered voices per row:

  - the INTERNAL voice (`categorie`, `bewaartermijn`, `bron_opmerking`,
    plus `legal_basis_ref`/`anchor_column`/`schema_ready`/`selector_sql`)
    — accountability text for docs/VERWERKINGSREGISTER.md §1.4 and
    docs/SOURCING-SOP.md §6. It names the anchor column (`date_found`,
    `rejected_at`) and cites WS-ticket numbers and §-cross-references.
  - the PUBLIC voice (`public_nl` / `public_en`, a `PublicRetentionText`
    each) — the plain-language wording for website/privacy.html's two
    retention tables (`retention-table-nl` / `retention-table-en`). It is
    written for a candidate or a regulator, not a developer: no column
    names, no ticket numbers, no internal cross-references. It is NOT a
    translation of `bron_opmerking` — the two serve different readers and
    are allowed to say different things about the same period.

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
kandidaat, logs. All ten periods are confirmed by the owner (2026-09-08)
— none carries "aanname"; VERWERKINGSREGISTER.md §6 punt 4 is closed
accordingly.

`schema_ready=False` marks a row whose anchor column does not exist in the
database yet (`placed_candidate`, action="retain"; `logs`,
action="infra_only" — neither is ever queued, so a missing column is
moot for both). Every other row is schema_ready=True: `rejected_at`
(candidates), `last_contacted_at` (client_prospects) and `last_login_at`
(users) exist since migrations/032_retention_anchor_columns.py;
`consent_talentpool_until` (candidates) since
migrations/030_talentpool_consent.py. `schema_ready=True` means "the
column exists and a real write path fills it going forward" — it does
NOT mean every pre-existing row is retroactively covered: migration 032
was a plain `ADD COLUMN`, so a row that already existed when it ran has
NULL there, and every selector below requires `IS NOT NULL` on its own
anchor column. Such a row only becomes eligible once it next goes through
the write path that stamps its column (no backfill — inventing a
historical `rejected_at`/`last_contacted_at`/`last_login_at` would
fabricate a date nobody observed).

`action` is one of:
  - "anonymise": run via erase_person() (routers/gdpr.py) — keeps the
    row's id (FK integrity, audit trail) but nulls PII and adds the
    person to suppression_list (except the talentpool_consent category,
    which is not an opt-out — see erase_person()'s own docstring).
  - "hard_delete": DELETE the row outright — used only where nothing else
    references the row and there is no suppression benefit.
  - "retain": never purged by this job — a floor, not a ceiling to purge
    past (placed_candidate's 7-year fiscal retention); included here for
    documentation/visibility only.
  - "infra_only": not a database category at all (log rotation) — no
    selector runs; the row exists purely so the table is complete.

Owner decision (WS-E.10): reaching "due" per the guarded selectors below
never deletes or anonymises anything by itself. It only
queues the subject for a human's monthly sign-off
(services/scheduler.py generate_retention_review(),
retention_review_items via migrations/036_retention_review_queue.py) via
GET/POST /api/v1/admin/retention/review* (routers/retention_admin.py).
Actual anonymise/hard_delete happens only from the per-item/per-category
approve endpoint, after that queue row exists and an admin explicitly
approves it — see routers/retention_admin.py's module docstring and
tests/test_ws_e10_no_unapproved_purge_path.py for the structural test
that a later change cannot silently reopen a direct purge path. The
guards, selectors and anchor columns below are what decides who is ON
that monthly list; nothing here acts on that list by itself.

`RetentionRow.subject_table`/`email_field`/`selector_params` are what
services/scheduler.py's `_live_rows_for_category()` needs to run
`selector_sql` generically (`fetch_all(row.selector_sql, *row.selector_params)`)
and file the result under the right (subject_table, email column) for
retention_review_items — one definition per category, read by both the
queue-generation job and the re-verify-at-approve-time check
(routers/retention_admin.py's `_is_still_eligible()`), instead of a
per-category lookup table plus a same-shaped wrapper function for each one.
"""
from dataclasses import dataclass, field
from typing import Optional, Tuple


# ── Candidate-side "did anything real happen since" guards ───────────────
#
# Shared SQL, imported by services/scheduler.py and by this module's own
# APOLLO_POOL_TARGET_SQL rather than duplicated — the selectors below and
# the ones the review-generation job actually runs must never drift
# apart, so this module owns the one copy of each and callers import it.
#
# "status = 'sourced'" (or 'new', or a stale last_login_at, ...) alone is
# never proof nobody has reacted: nothing in this codebase moves
# candidates.status off 'sourced' when a match progresses, a client
# pipeline entry is created, a recruiter logs a real reaction, the person
# registers a portal account, or the person is placed. The guards below
# check those signal tables directly instead of trusting one column nothing
# keeps in sync.
#
# `_CANDIDATE_ENGAGEMENT_SIGNALS_SQL` is every such signal EXCEPT "has a
# live portal account", split out on its own so PORTAL_ACCOUNT_INACTIVE_SQL
# below can reuse it: that selector evaluates the exact portal account a
# "live account" check would find (it always finds at least itself), so
# folding it in there would make every linked account permanently
# immune, defeating the category. Every other selector in this module
# reuses the full `CANDIDATE_NO_REACTION_GUARD_SQL` (engagement signals
# + the live-account check), where that self-reference does not apply.
#
# A placement (migrations/029_placements.py) never touches matches or
# pipeline_entries (routers/placements.py's create_placement writes
# candidate_id/job_id/client_id directly), so it needs its own guard —
# including one that was later soft-deleted: "ooit geplaatst" is still
# the 7-year fiscal floor placed_candidate documents, so this guard does
# NOT filter on `deleted_at`.
#
# A candidate with currently-valid talentpool consent
# (`consent_talentpool_until > NOW()`) is protected from every category
# here, not only from TALENTPOOL_EXPIRED_SQL's own selector — an active,
# separate consent relationship is itself an engagement signal.
_CANDIDATE_ENGAGEMENT_SIGNALS_SQL = """
      AND NOT EXISTS (SELECT 1 FROM matches m WHERE m.candidate_id = c.id AND m.status <> 'suggested')
      AND NOT EXISTS (SELECT 1 FROM pipeline_entries p WHERE p.candidate_id = c.id)
      AND NOT EXISTS (
          SELECT 1 FROM activities a
          WHERE a.subject_type = 'candidate' AND a.subject_id = c.id AND a.deleted_at IS NULL
      )
      AND NOT EXISTS (SELECT 1 FROM placements pl WHERE pl.candidate_id = c.id)
      AND (c.consent_talentpool_until IS NULL OR c.consent_talentpool_until <= NOW())
"""

# "Has a live portal account at all" -- a real FK via candidate_profiles
# (migrations/023_candidate_profiles_candidate_id.py), never an e-mail
# match (a portal account and its candidate record can carry different
# addresses; erase_person(), routers/gdpr.py, does not trust an e-mail
# join here either). Appended to _CANDIDATE_ENGAGEMENT_SIGNALS_SQL to
# form CANDIDATE_NO_REACTION_GUARD_SQL below -- kept separate only so
# PORTAL_ACCOUNT_INACTIVE_SQL can reuse the rest without this
# self-referential clause (see the comment above).
_CANDIDATE_LIVE_PORTAL_ACCOUNT_GUARD_SQL = """
      AND NOT EXISTS (
          SELECT 1 FROM candidate_profiles cpf
          JOIN users u ON u.id = cpf.user_id
          WHERE cpf.candidate_id = c.id AND u.deleted_at IS NULL
      )
"""

CANDIDATE_NO_REACTION_GUARD_SQL = _CANDIDATE_ENGAGEMENT_SIGNALS_SQL + _CANDIDATE_LIVE_PORTAL_ACCOUNT_GUARD_SQL

# `term_expired_op` (anchor value + the row's own period, i.e. the fixed
# calendar date the term became due) rides alongside id/email in every
# selector below -- WS-E.10's monthly review list
# (services/scheduler.py generate_retention_review()) reads this to show
# "verstreken sinds" per person without recomputing the period in Python
# and risking it drifting from the WHERE clause that actually enforces it.
_SOURCED_NO_RESPONSE_BASE_SQL = """
    SELECT c.id, c.email, c.date_found + INTERVAL '3 months' AS term_expired_op
      FROM candidates c WHERE c.lawful_basis = $1
      AND c.status = 'sourced' AND c.date_found IS NOT NULL
      AND c.date_found <= (CURRENT_DATE - INTERVAL '3 months')
      AND c.consent_withdrawn_at IS NULL AND c.deleted_at IS NULL AND c.email IS NOT NULL
"""

SOURCED_NO_RESPONSE_SQL = _SOURCED_NO_RESPONSE_BASE_SQL + CANDIDATE_NO_REACTION_GUARD_SQL

# WS3b: referral had, tot dit spoor, letterlijk SOURCED_NO_RESPONSE_SQL als
# selector -- alleen de `lawful_basis`-parameter ('toestemming_referral' in
# plaats van 'gerechtvaardigd_belang') verschilde. Dezelfde bewaartermijn
# (3 maanden na `date_found`, VERWERKINGSREGISTER §1.4 rij 7 / SOP §6 rij 7)
# is ook precies wat blijft; wat verandert is wie er als "geen reactie"
# telt.
#
# Een referral krijgt sinds WS3b een eigen bevestigingsmail met het Art.
# 14-blok in de referral-variant (services/email_templates.py
# `referral_confirm`, aangemaakt door POST /api/v1/admin/candidates/
# referral). Klikt die persoon zelf op de bevestigingslink, dan stempelt
# routers/public.py's talentpool_confirm() `referral_confirmed_at`. Dat is
# per definitie een reactie van de betrokkene zelf: het is de enige
# handeling die deze flow van hem vraagt, en de meest expliciete die er
# bestaat. Zonder de regel hieronder zou zo iemand drie maanden na
# `date_found` gewoon op de maandelijkse beoordelingslijst belanden terwijl
# hij nota bene toestemming had bevestigd -- exact de fout die
# CANDIDATE_NO_REACTION_GUARD_SQL's eigen commentaar hierboven beschrijft
# ("status = 'sourced' alleen is nooit bewijs dat niemand heeft
# gereageerd"), alleen voor een signaal dat vóór WS3b nog niet bestond.
#
# Bewust alleen op de referral-rij en niet in de gedeelde guard: de kolom
# wordt uitsluitend door de referral-flow geschreven, dus voor elke andere
# categorie zou hij altijd NULL zijn (geen effect) of, erger, per ongeluk
# betekenis krijgen als een ander pad hem ooit gaat vullen.
REFERRAL_NO_RESPONSE_SQL = (
    _SOURCED_NO_RESPONSE_BASE_SQL
    + "      AND c.referral_confirmed_at IS NULL\n"
    + CANDIDATE_NO_REACTION_GUARD_SQL
)

# Same "the status column isn't kept in sync" problem on the prospect
# side: routers/outreach.py never writes back to client_prospects.status
# once a draft is approved and sent, or once a reply comes in (see
# routers/prospects.py's own docstring). The guard is the one real
# candidate-side event this codebase records for a prospect: a sent
# outreach_drafts row, so a prospect mid-conversation isn't purged out
# from under an in-flight thread. `replied_at` never appears here or
# anywhere else in this module -- outreach is draft-only by design (a
# human sends from their own mailbox; any reply lands there, not in this
# DB), so no code path has ever written it.
PROSPECT_NO_RESPONSE_SQL = """
    SELECT cp.id, cp.contact_email, cp.created_at + INTERVAL '12 months' AS term_expired_op
      FROM client_prospects cp WHERE cp.status = 'new'
      AND cp.created_at <= (NOW() - INTERVAL '12 months') AND cp.opt_out_at IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM outreach_drafts od
          WHERE LOWER(od.target_email) = LOWER(cp.contact_email) AND od.target_type = 'client_prospect' AND od.status = 'sent'
      )
"""

# migrations/030_talentpool_consent.py adds candidates.consent_talentpool_
# until. A candidate whose talentpool consent has lapsed (12 months,
# renewable -- SOP §1.5/§6 row 2) and was never renewed is queued the
# same way sourced_no_response/referral are, via the guarded selector
# below; approving the review item runs erase_person() with
# reason="retention_purge:talentpool_consent", which also skips the usual
# suppression-list entry (see erase_person()'s own docstring — a lapsed
# consent is not an opt-out). The 30-day grace period on top of
# consent_talentpool_until (not just "<= NOW()") gives the renewal
# reminder e-mail (services/scheduler.py's talentpool_reminder_job, sent
# 30 days *before* expiry) room to land and be acted on first.
TALENTPOOL_EXPIRED_SQL = """
    SELECT c.id, c.email, c.consent_talentpool_until + INTERVAL '30 days' AS term_expired_op
      FROM candidates c WHERE c.lawful_basis = 'opt_in_talentpool'
      AND c.consent_talentpool_until IS NOT NULL
      AND c.consent_talentpool_until <= (NOW() - INTERVAL '30 days')
      AND c.deleted_at IS NULL AND c.email IS NOT NULL
""" + CANDIDATE_NO_REACTION_GUARD_SQL

# migrations/032_retention_anchor_columns.py adds candidates.rejected_at,
# stamped by the only two write paths onto candidates.status
# (routers/candidates.py PATCH /api/candidates/{id} and
# routers/webhook.py's candidate_updated Hermes action) whenever status is
# set to 'rejected'. A rejected candidate can still be reconsidered later
# without rejected_at being cleared, so `status = 'rejected'` must still
# hold (a later status change away from 'rejected' drops the row out of
# this selector even if rejected_at is stale) and the guards below
# additionally exclude anyone whose matches/pipeline_entries were touched
# *after* rejected_at (picked back up for another role since being
# rejected) -- both matches.updated_at and pipeline_entries.updated_at
# (the latter TIMESTAMPTZ since migrations/033_retention_guard_fixes.py,
# matching candidates.rejected_at's type) are stamped on every write path
# that creates or advances one of these rows. A placement never touches
# either table (routers/placements.py's create_placement), hence its own
# guard, and -- per the shared engagement-signals guard's own comment
# above -- it does not filter on `deleted_at`.
REJECTED_APPLICANT_SQL = """
    SELECT id, email, rejected_at + INTERVAL '4 weeks' AS term_expired_op
      FROM candidates c WHERE c.status = 'rejected'
      AND c.rejected_at IS NOT NULL AND c.rejected_at <= (NOW() - INTERVAL '4 weeks')
      AND c.deleted_at IS NULL AND c.email IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM matches m WHERE m.candidate_id = c.id
            AND m.status NOT IN ('rejected') AND m.updated_at > c.rejected_at
      )
      AND NOT EXISTS (
          SELECT 1 FROM pipeline_entries p WHERE p.candidate_id = c.id AND p.updated_at > c.rejected_at
      )
      AND NOT EXISTS (SELECT 1 FROM placements pl WHERE pl.candidate_id = c.id)
"""

# migrations/032_retention_anchor_columns.py adds
# client_prospects.last_contacted_at, stamped whenever an admin changes a
# prospect's status (routers/prospects.py PUT /api/v1/admin/prospects/{id})
# and whenever an outreach draft targeting a client_prospect is
# approved/sent (routers/outreach.py approve_draft). `status != 'new'`
# alone is not "this lead went nowhere" (a free Optional[str] admins can
# set to anything, including a converted customer) -- the real signal for
# "this company is a live client" is clients.account_status (`active`,
# only ever set explicitly via PATCH /api/v1/admin/clients/{id},
# migrations/034_clients_account_status_lifecycle.py). `cp.opt_out_at IS
# NULL` (the same flag erase_person() sets) keeps an already-anonymised
# row from being re-selected on a later run. The client match runs both
# company_name and the normalised domain column both tables carry
# (core/privacy.py normalize_domain(), so two differently-formatted URLs
# for the same host still match, and two empty domains never match each
# other) -- a harder key than free-text company_name alone.
_NORMALIZED_DOMAIN_SQL = (
    "NULLIF(LOWER(REGEXP_REPLACE(REGEXP_REPLACE(TRIM(BOTH FROM {col}), "
    "'^https?://', ''), '^www\\.', '')), '')"
)


def _domain_match_sql(left: str, right: str) -> str:
    l_norm = _NORMALIZED_DOMAIN_SQL.format(col=left)
    r_norm = _NORMALIZED_DOMAIN_SQL.format(col=right)
    return f"({l_norm} IS NOT NULL AND {l_norm} = {r_norm})"


PROSPECT_RESPONDING_SQL = f"""
    SELECT id, contact_email, last_contacted_at + INTERVAL '12 months' AS term_expired_op
      FROM client_prospects cp WHERE cp.status != 'new'
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
# mfa_recovery()) -- never on /register or /refresh. "Actief
# portalaccount zonder sollicitatie" means no real engagement, not merely
# no recent login -- a candidate can be actively matched/piped/contacted
# without ever touching the portal. The account is anonymised via the
# same erase_person() that anonymises its linked candidate row, so the
# guard reuses `_CANDIDATE_ENGAGEMENT_SIGNALS_SQL`
# against the linked candidate (via candidate_profiles.candidate_id, the
# real FK, never an e-mail match) rather than only the matches/
# pipeline_entries/placements subset it used to check on its own --
# activities and an unexpired talentpool consent on the linked candidate
# now protect the account too. It deliberately does NOT also reuse
# `_CANDIDATE_LIVE_PORTAL_ACCOUNT_GUARD_SQL` (see that constant's own
# comment: it would always find the very account being evaluated).
#
# Owner decision (2026-09-08): 24 months becomes 18, with a 30-day
# advance warning e-mail before the cutoff (VERWERKINGSREGISTER §1.4,
# privacy.html, privacy-kandidaten.html, SOURCING-SOP all promise this).
#
# chief-of-staff FIX FIRST (retention-kolommen branch, finding 2): that
# public promise needs a warning to actually have gone out before this
# selector treats an account as due -- migrations/039_users_dormant_
# warning.py added `users.dormant_warning_sent_at` for exactly that
# purpose but this selector never read it, so a 5-year-dormant account
# with no warning ever sent would already have landed on the monthly
# review list, half the promised 18-months-plus-30-days notice quietly
# gone. This selector is now the one place that promise is enforced: an
# account only qualifies once `dormant_warning_sent_at` is set AND at
# least 30 days old, which is also, deliberately, the ONLY thing this
# column does today -- gate this selector. A warning job that stamps it
# (same shape as talentpool_reminder_job in services/scheduler.py) is
# still a separate, not-yet-built track; until it exists, no row can ever
# satisfy this condition, so no account (dormant however long) reaches
# the review list without one -- the selector fails closed rather than
# silently keeping the pre-fix behaviour of ignoring the warning.
PORTAL_ACCOUNT_INACTIVE_SQL = f"""
    SELECT id, email, last_login_at + INTERVAL '18 months' AS term_expired_op
      FROM users u WHERE u.role = 'candidate' AND u.deleted_at IS NULL
      AND u.last_login_at IS NOT NULL AND u.last_login_at <= (NOW() - INTERVAL '18 months')
      AND u.dormant_warning_sent_at IS NOT NULL
      AND u.dormant_warning_sent_at < (NOW() - INTERVAL '30 days')
      AND NOT EXISTS (
          SELECT 1 FROM candidate_profiles cpf
          JOIN candidates c ON c.id = cpf.candidate_id
          WHERE cpf.user_id = u.id
            AND NOT (TRUE{_CANDIDATE_ENGAGEMENT_SIGNALS_SQL})
      )
"""

# ── Waarschuwing vooraf bij een slapend account (WS3b) ───────────────────
#
# De andere helft van PORTAL_ACCOUNT_INACTIVE_SQL hierboven, en daarom
# staat hij hier ernaast en niet in services/scheduler.py (CR R7): die
# module haalde hier een private constante (_CANDIDATE_ENGAGEMENT_
# SIGNALS_SQL) vandaan om er zijn eigen selector mee te bouwen, waarmee
# de twee helften van dezelfde belofte in twee bestanden stonden en
# alleen de een een reden had om mee te veranderen.
#
# `dormant_warning_sent_at` gates die selector: een account komt pas op
# de maandelijkse beoordelingslijst als de waarschuwing hieronder
# daadwerkelijk is verstuurd en 30 dagen oud is. services/scheduler.py's
# dormant_account_warning_job is wat die kolom stempelt.
#
# Ondergrens 17 maanden, GEEN bovengrens (besluit van de eigenaar, B3).
# De eerste versie had `AND last_login_at > NOW() - INTERVAL '18 months'`
# erbij, zodat het venster precies één maand breed was. Dat leek netjes
# maar liet iedereen die op de dag van invoering al langer dan 18 maanden
# sliep permanent boven het venster vallen: nooit gewaarschuwd, dus nooit
# beoordeeld, dus de publiek beloofde 18 maanden werd voor precies die
# achterstand nooit gehaald. Zonder bovengrens loopt die achterstand in
# één ronde mee, met dezelfde 30 dagen notice als iedereen.
#
# Twee keer waarschuwen kan daardoor niet: `dormant_warning_sent_at IS
# NULL OR < last_login_at` betekent "nog nooit gewaarschuwd in deze
# inactiviteitscyclus" -- logt iemand in, dan schuift last_login_at
# vooruit en begint een nieuwe cyclus; doet hij niets, dan blijft de
# stempel nieuwer dan zijn laatste login en valt hij hier morgen niet
# opnieuw uit. De LIMIT is dus een dagplafond op een aflopende
# achterstand, geen filter dat iemand structureel overslaat.
_DORMANT_WARNING_WHERE_SQL = f"""
       u.role = 'candidate' AND u.deleted_at IS NULL AND u.email IS NOT NULL
       AND u.last_login_at IS NOT NULL
       AND u.last_login_at <= (NOW() - INTERVAL '17 months')
       AND (u.dormant_warning_sent_at IS NULL OR u.dormant_warning_sent_at < u.last_login_at)
       AND NOT EXISTS (
           SELECT 1 FROM candidate_profiles cpf
           JOIN candidates c ON c.id = cpf.candidate_id
           WHERE cpf.user_id = u.id
             AND NOT (TRUE{_CANDIDATE_ENGAGEMENT_SIGNALS_SQL})
       )
"""

# $1 = dagplafond. Oudste eerst: wie het langst slaapt, is het langst
# over tijd en gaat voor.
DORMANT_WARNING_SQL = f"""
    SELECT u.id, u.email, u.full_name, u.last_login_at
      FROM users u
     WHERE {_DORMANT_WARNING_WHERE_SQL}
     ORDER BY u.last_login_at ASC
     LIMIT $1
"""

# Hetzelfde WHERE, zonder plafond: het aantal dat vandaag aan de beurt is.
# Zonder dit telde een droogloop alleen wat na het knippen overbleef en
# rapporteerde een achterstand van 5000 accounts als "200" -- precies het
# getal dat niets zegt (CR L2).
DORMANT_WARNING_COUNT_SQL = f"""
    SELECT COUNT(*) AS due
      FROM users u
     WHERE {_DORMANT_WARNING_WHERE_SQL}
"""


# ── Apollo bulk-pool cleanup (VERWERKINGSREGISTER.md §2.6, §5.7) ─────────
#
# Not one of RETENTION_TABLE's ten §1.4 rows (a one-off historical
# bulk-harvest pool, not an ongoing category), but it feeds the same
# retention_review_items queue as every other category, under
# category='apollo_pool_purge', and reuses the same
# CANDIDATE_NO_REACTION_GUARD_SQL guards. Rows without an http(s)
# source_url never passed the LIA (§2.6) -- those are the pool this
# category considers; a row that later gained a real public source_url is
# left alone entirely, at both queries below.
APOLLO_POOL_ROWS_SQL = """
    SELECT c.id, c.email FROM candidates c
    WHERE c.pool_origin = 'apollo'
      AND c.deleted_at IS NULL
      AND (c.source_url IS NULL OR c.source_url !~* '^https?://')
"""

# pool_origin='apollo' plus a missing source_url is not by itself proof a
# row is inert bulk-harvest noise -- an Apollo-sourced candidate can still
# have picked up a real match, a client pipeline entry, a recorded
# activity, a portal account, a placement, or be the (anonymised) subject
# of a presented-candidate outreach draft to a client_prospect. Applied to
# both the anonymise and the hard-delete branches. See
# tests/test_retention.py's test_apollo_pool_purge_target_sql_carries_all_six_guards.
APOLLO_POOL_TARGET_SQL = APOLLO_POOL_ROWS_SQL + CANDIDATE_NO_REACTION_GUARD_SQL + """
      AND NOT EXISTS (SELECT 1 FROM outreach_drafts d WHERE d.presented_candidate_id = c.id)
"""


# ── leads_quiz: two unrelated tables, age-only, no protective guard ──────
#
# Shared here instead of as four separately-typed
# `INTERVAL '12 months'` literals split across this row's own
# documentation-only `selector_sql` and services/scheduler.py's actual
# runtime queries -- one definition each, read by both.
LEADS_QUIZ_SQL = """
    SELECT id, created_at + INTERVAL '12 months' AS term_expired_op
      FROM quiz_submissions WHERE created_at <= (NOW() - INTERVAL '12 months')
"""
CONTACT_SUBMISSIONS_SQL = """
    SELECT id, created_at + INTERVAL '12 months' AS term_expired_op
      FROM contact_submissions WHERE created_at <= (NOW() - INTERVAL '12 months')
"""

# The three rows below share one long clause identifying the same set of
# candidate-side engagement signals, instead of being repeated almost
# verbatim in each row's own field.
_SIGNAL_MISSING_ENGAGEMENT_PREFIX_NL = (
    "geen match, pipeline-activiteit, vastgelegde reactie, portalaccount of plaatsing sinds "
)


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
    # Plain-language NL description of which protective signal(s) this
    # row's selector checks for and found absent -- every anonymise/
    # hard_delete selector above is a conjunction of NOT EXISTS guards, so
    # a row it returns has ALL of these absent simultaneously (there is no
    # finer-grained "which one specifically" to report; the guards are
    # ANDed, not scored). Read into retention_review_items.signal_missing_nl
    # by services/scheduler.py's generate_retention_review() for the
    # monthly human-approval list. "" only for retain/infra_only rows,
    # which never reach the review queue at all.
    signal_missing_nl: str
    # The three fields below let
    # services/scheduler.py's `_live_rows_for_category()` run this row
    # generically (`fetch_all(row.selector_sql, *row.selector_params)`)
    # and file each result under the right subject table/e-mail column in
    # retention_review_items, instead of a per-category lookup table plus
    # a same-shaped `_count_*()` wrapper function per category. Left at
    # their "" / () defaults for leads_quiz (spans two tables, handled
    # directly in generate_retention_review()), apollo_pool_purge (not a
    # RETENTION_TABLE row), and the retain/infra_only rows (never queued).
    subject_table: str = ""       # table subject_id refers to
    email_field: str = ""         # selector_sql's e-mail column name
    selector_params: tuple = field(default_factory=tuple)  # positional args for selector_sql


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
        signal_missing_nl=(
            "geen nieuwe match, pipeline-activiteit of plaatsing sinds de afwijzing"
        ),
        subject_table="candidates", email_field="email", selector_params=(),
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
        signal_missing_nl=_SIGNAL_MISSING_ENGAGEMENT_PREFIX_NL + "het verlopen van de toestemming",
        subject_table="candidates", email_field="email", selector_params=(),
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
        bron_opmerking="bevestigd door eigenaar 2026-09-08; strenger dan de 2 jaar in privacy.html",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 3 / SOP §6 rij 3, §2.4.4",
        anchor_column="candidates.date_found",
        action="anonymise",
        schema_ready=True,
        selector_sql=SOURCED_NO_RESPONSE_SQL,
        signal_missing_nl=_SIGNAL_MISSING_ENGAGEMENT_PREFIX_NL + "het vinden van de persoon",
        subject_table="candidates", email_field="email", selector_params=("gerechtvaardigd_belang",),
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
        signal_missing_nl="geen verzonden outreach-draft naar dit contact",
        subject_table="client_prospects", email_field="contact_email", selector_params=(),
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
        bron_opmerking="bevestigd door eigenaar 2026-09-08",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 5 / SOP §6 rij 5",
        anchor_column="client_prospects.last_contacted_at",
        action="anonymise",
        schema_ready=True,
        selector_sql=PROSPECT_RESPONDING_SQL,
        signal_missing_nl="geen actieve klantrelatie (op bedrijfsnaam of domein) bij dit bedrijf",
        subject_table="client_prospects", email_field="contact_email", selector_params=(),
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
        bewaartermijn="zolang account actief; 18 maanden inactiviteit → verwijderen, waarschuwing 30 dagen vooraf",
        bron_opmerking="bevestigd door eigenaar 2026-09-08",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 6 / SOP §6 rij 6",
        anchor_column="users.last_login_at",
        action="anonymise",
        schema_ready=True,
        selector_sql=PORTAL_ACCOUNT_INACTIVE_SQL,
        signal_missing_nl=(
            "geen match, pipeline-activiteit, vastgelegde reactie of plaatsing bij de gekoppelde "
            "kandidaat, en geen lopende talentpool-toestemming"
        ),
        subject_table="users", email_field="email", selector_params=(),
        public_nl=PublicRetentionText(
            categorie="Actief portalaccount zonder sollicitatie",
            bewaartermijn="zolang account actief; 18 maanden inactiviteit → verwijderen, waarschuwing 30 dagen vooraf",
            toelichting="",
        ),
        public_en=PublicRetentionText(
            categorie="Active portal account without application",
            bewaartermijn="as long as active; 18 months inactive → deleted, 30-day advance warning",
            toelichting="",
        ),
    ),
    RetentionRow(
        key="referral",
        categorie="Referral",
        bewaartermijn="zoals gesourcet (3 maanden na `date_found` zonder reactie); herkomst = referrer",
        bron_opmerking="bevestigd door eigenaar 2026-09-08; zie §1.3",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 7 / SOP §6 rij 7, §1.3",
        anchor_column="candidates.date_found",
        action="anonymise",
        schema_ready=True,
        # WS3b: not SOURCED_NO_RESPONSE_SQL any more -- same period and
        # the same guards, plus `referral_confirmed_at IS NULL` as this
        # category's own reaction signal (see REFERRAL_NO_RESPONSE_SQL).
        # lawful_basis is still the $1 parameter.
        selector_sql=REFERRAL_NO_RESPONSE_SQL,
        signal_missing_nl=(
            _SIGNAL_MISSING_ENGAGEMENT_PREFIX_NL
            + "het vinden van de persoon, en de referral-bevestigingslink is nooit aangeklikt"
        ),
        subject_table="candidates", email_field="email", selector_params=("toestemming_referral",),
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
        selector_sql=LEADS_QUIZ_SQL + "; " + CONTACT_SUBMISSIONS_SQL,
        signal_missing_nl="n.v.t. -- deze categorie kent geen beschermingssignaal, alleen leeftijd",
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
        # The anchor is `placements.start_date` (migrations/029_placements.py),
        # written by every placement (routers/placements.py's
        # create_placement) -- not `matches.status`, a value nothing in
        # this backend ever writes. This is documentation-only for this
        # row (action="retain" means its selector_sql is never run), but
        # it matters everywhere else: every candidate-purging selector in
        # this module excludes any candidate with a `placements` row (see
        # `_CANDIDATE_ENGAGEMENT_SIGNALS_SQL` and REJECTED_APPLICANT_SQL
        # above), so the 7-year floor this row documents is never
        # silently defeated by one of the other nine categories
        # anonymising the same candidate first.
        anchor_column="placements.start_date",
        action="retain",
        schema_ready=False,
        selector_sql=(
            "SELECT id FROM placements WHERE status IN ('actief', 'beeindigd') "
            "AND COALESCE(end_date, start_date) <= (CURRENT_DATE - INTERVAL '7 years') "
            "-- action=retain: 7 years is a floor, not a purge trigger; this job never deletes/anonymises "
            "this category (schema_ready=False is moot for a 'retain' row -- "
            "services/scheduler.py's generate_retention_review() skips it outright before ever checking it). "
            "WS-C.7 (migrations/029_placements.py) added `placements` and, on candidates, the "
            "immigratiestatus columns (nationality, needs_work_permit, kennismigrant_status, "
            "ruling_30pct_status, ind_case_number) -- both fall under this same 7-year floor and are "
            "erased (not merely retained past it) by routers/gdpr.py's erase_person() alongside the "
            "rest of a placed candidate's PII once the retention floor has passed and erasure runs."
        ),
        signal_missing_nl="",  # action=retain: never reaches the review queue
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
        signal_missing_nl="",  # action=infra_only: never reaches the review queue
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
