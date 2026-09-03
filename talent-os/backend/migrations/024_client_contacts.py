"""
Talent OS — WS-C.4: client_contacts (multiple named contacts per client).

`clients` (migrations/000_baseline.py) has no room for more than one named
person per company -- routers/client.py's `_get_client_id`/team-invite flow
is about *portal users*, not the hiring-manager/finance/tekenbevoegd
contacts a recruiter needs on file for a client relationship. This table
adds those, independent of whether the contact ever gets a portal login.

Columns:
  - client_id      FK -> clients(id), ON DELETE CASCADE (a contact has no
    meaning once its client is gone -- same cascade as pipeline_entries.client_id).
  - full_name, email, phone -- plain contact details.
  - role           CHECK'd to hiring_manager | finance | tekenbevoegd | overig.
  - is_primary     boolean, default false -- no partial-unique-index making
    "one primary per client" a hard DB constraint (WS-C.4 spec calls for no
    unique indexes that could abort on existing data); enforced at the API
    layer instead (routers/client_contacts.py demotes any other primary
    contact for the same client when a new one is set primary).
  - lawful_basis   same three GDPR values as client_prospects.lawful_basis
    (migrations/018_gdpr_provenance_optout.py) -- a contact is a business
    person, not a consumer, so the same Telecommunicatiewet-driven set applies.
  - created_at / updated_at / deleted_at -- soft delete, same pattern as
    `clients`/`candidates`.

Pattern of 014/015: idempotent (CREATE TABLE IF NOT EXISTS / CREATE INDEX
IF NOT EXISTS), no unique indexes that could abort on existing data, no DO
$$ ... END $$ blocks (migrations/_runner.py splits on a literal ";").
CHECK constraints are declared inline on the CREATE TABLE (not a separate
ADD CONSTRAINT) so re-running this against an already-created table is a
no-op via the outer CREATE TABLE IF NOT EXISTS, matching 018's reasoning
for why inline CHECKs here don't need the DROP/ADD CONSTRAINT dance that a
later ALTER-on-an-existing-table would (see 016/018's docstrings for that
case).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "024_client_contacts"

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS client_contacts (
    id              SERIAL PRIMARY KEY,
    client_id       INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    full_name       TEXT NOT NULL,
    email           TEXT,
    phone           TEXT,
    role            TEXT CHECK (role IS NULL OR role IN ('hiring_manager','finance','tekenbevoegd','overig')),
    is_primary      BOOLEAN NOT NULL DEFAULT false,
    lawful_basis    TEXT CHECK (lawful_basis IS NULL OR lawful_basis IN ('zakelijk_functioneel_adres','opt_in','bestaande_relatie')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_client_contacts_client ON client_contacts(client_id);
CREATE INDEX IF NOT EXISTS idx_client_contacts_deleted_at ON client_contacts(deleted_at);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
