"""
Talent OS — WS-E.8 retention table.

Single source of truth for the bewaartabel (retention table) that
docs/VERWERKINGSREGISTER.md §1.4 and docs/SOURCING-SOP.md §6 both carry in
prose/Markdown, and that services/scheduler.py's run_retention_purge()
and routers/retention_admin.py execute against. Change the table here
first, then regenerate the Markdown in the two docs (render_markdown())
and website/privacy.html so the four stay identical — tests/test_retention.py
checks the register against this module; it does not check privacy.html or
the SOP copy automatically, so update those two by hand in the same PR.

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
database yet (rejected_at, consent_talentpool_until, a "last contact"/
"last login" column — none of these exist as of WS-E.7). The purge job
(services/scheduler.py) skips those categories entirely — it never issues
a query against a column that isn't there — and reports them as
"schema_not_ready" so an admin calling GET /api/v1/admin/retention/table
or POST .../retention/run can see exactly which rows are enforced today
and which need a follow-up migration (owner decision, not made in this
PR — see the WS-E.8 task notes).

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
          WHERE LOWER(od.target_email) = LOWER(cp.contact_email) AND od.target_type = 'prospect' AND od.status = 'sent'
      )
"""


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


RETENTION_TABLE: Tuple[RetentionRow, ...] = (
    RetentionRow(
        key="rejected_applicant",
        categorie="Afgewezen sollicitant",
        bewaartermijn="4 weken na `rejected_at`",
        bron_opmerking="bron: AP/Recruitee",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 1 / SOP §6 rij 1",
        anchor_column="candidates.rejected_at",
        action="anonymise",
        schema_ready=False,
        selector_sql=(
            "SELECT id, email FROM candidates "
            "WHERE rejected_at IS NOT NULL AND rejected_at <= NOW() - INTERVAL '4 weeks' "
            "AND deleted_at IS NULL -- schema_ready=False: candidates.rejected_at does not exist yet"
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
        schema_ready=False,
        selector_sql=(
            "SELECT id, email FROM candidates WHERE lawful_basis = 'opt_in_talentpool' "
            "AND consent_talentpool_until IS NOT NULL AND consent_talentpool_until <= NOW() "
            "AND deleted_at IS NULL -- schema_ready=False: candidates.consent_talentpool_until does not exist yet"
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
    ),
    RetentionRow(
        key="prospect_responding",
        categorie="Prospect die wel reageert (relatie)",
        bewaartermijn="zolang actief + 12 maanden na laatste contact",
        bron_opmerking="aanname",
        legal_basis_ref="VERWERKINGSREGISTER §1.4 rij 5 / SOP §6 rij 5",
        anchor_column="client_prospects.last_contacted_at",
        action="anonymise",
        schema_ready=False,
        selector_sql=(
            "SELECT id, contact_email FROM client_prospects WHERE status != 'new' "
            "AND last_contacted_at IS NOT NULL AND last_contacted_at <= (NOW() - INTERVAL '12 months') "
            "-- schema_ready=False: client_prospects.last_contacted_at does not exist yet"
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
        schema_ready=False,
        selector_sql=(
            "SELECT id, email FROM users WHERE role = 'candidate' AND deleted_at IS NULL "
            "AND last_login_at IS NOT NULL AND last_login_at <= (NOW() - INTERVAL '24 months') "
            "-- schema_ready=False: users.last_login_at does not exist yet"
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
            "this category. No dedicated invoice-date column exists yet either (schema_ready=False)."
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
    what tests/test_retention.py compares against the register's parsed
    rows."""
    return tuple((row.categorie, row.bewaartermijn, row.bron_opmerking) for row in rows)
