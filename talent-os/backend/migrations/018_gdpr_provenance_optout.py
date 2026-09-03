"""
Talent OS — WS-E.7 "GDPR: wissen, exporteren, herkomst, opt-out,
Telecommunicatiewet". Adds provenance/lawful_basis columns to candidates
and client_prospects, plus the suppression_list table.

Pattern of 014/015: idempotent (ADD COLUMN IF NOT EXISTS / CREATE TABLE IF
NOT EXISTS / CREATE INDEX IF NOT EXISTS), no `DO $$ ... END $$;` blocks
(migrations/_runner.py splits each migration's SQL on a literal ";", which
would mangle a DO block's internal semicolons — see 000_baseline.py's
docstring). Postgres has no `ADD CONSTRAINT IF NOT EXISTS` for CHECK
constraints, so the lawful_basis value-set check is attached inline on the
`ADD COLUMN IF NOT EXISTS ... CHECK (...)` statement instead of a separate
ALTER TABLE ... ADD CONSTRAINT — when the column already exists the whole
statement is a no-op (including the CHECK clause), so re-running this is
safe.

candidates.source_url and candidates.consent_withdrawn_at already exist
(000_baseline.py) — ADD COLUMN IF NOT EXISTS on those two is a deliberate
no-op, kept here so this migration is a complete, self-contained list of
every column the SOP (docs/SOURCING-SOP.md §2) and the Verwerkingsregister
(docs/VERWERKINGSREGISTER.md §1.1) require, not just the new ones.

outreach_drafts.presented_candidate_id (security-auditor follow-up, L2):
the candidate being anonymously presented to a client_prospect in a
spec/MPC-outreach draft (SOP §5) — previously routers/outreach.py's
_draft_refusal() overloaded job_id (always NULL on prospect drafts) for
this; a real column replaces that overload before this migration ships.

No NOT NULL constraints on source_url/lawful_basis yet — the existing
Apollo-sourced pool (14,687 rows, no source_url) has neither, and turning
that into a hard constraint before the Apollo-pool decision (WS-E.8,
owner's call) would break every existing row. Enforcement here is at the
API layer (models/schemas.py, routers/candidates.py, routers/webhook.py,
routers/candidate.py, routers/prospects.py), not the database.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "018_gdpr_provenance_optout"

MIGRATION_SQL = """
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS lawful_basis TEXT CHECK (lawful_basis IN ('gerechtvaardigd_belang','opt_in_talentpool','toestemming_referral','portal_registratie'));
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS date_found DATE;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS consent_withdrawn_at TIMESTAMPTZ;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS consent_spec_presentation_at TIMESTAMPTZ;
ALTER TABLE client_prospects ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE client_prospects ADD COLUMN IF NOT EXISTS lawful_basis TEXT CHECK (lawful_basis IN ('zakelijk_functioneel_adres','opt_in','bestaande_relatie'));
ALTER TABLE client_prospects ADD COLUMN IF NOT EXISTS consent_at TIMESTAMPTZ;
ALTER TABLE client_prospects ADD COLUMN IF NOT EXISTS opt_out_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS suppression_list (
    id              SERIAL PRIMARY KEY,
    email_hash      TEXT NOT NULL UNIQUE,
    email_domain    TEXT,
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      INTEGER REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_suppression_list_domain ON suppression_list(email_domain);
ALTER TABLE outreach_drafts ADD COLUMN IF NOT EXISTS presented_candidate_id INTEGER REFERENCES candidates(id);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
