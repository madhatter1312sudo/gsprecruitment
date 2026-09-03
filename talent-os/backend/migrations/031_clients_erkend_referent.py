"""
Talent OS — WS-B.5 follow-up: clients.erkend_referent + clients.notes.

The admin "Opdrachtgevers" (clients) list UI had to derive the client
roster from GET /api/v1/admin/users?role=client with an N+1 call per row
(no list endpoint over `clients` existed). This migration adds the one
piece of client data that endpoint needs but the `clients` table
(migrations/000_baseline.py) doesn't yet have: an ICP filter for "erkend
referent in het IND-register" (recognised sponsor in the IND register --
see this repo's CLAUDE.md: GSP itself is not one; this column tracks
whether a *client* company is, for hiring-kennismigrant matching).

Columns:
  - erkend_referent  TEXT CHECK'd to ja|nee|onbekend, DEFAULT 'onbekend'
    -- three-valued rather than boolean because it's usually unknown at
    intake time (same shape reasoning as client_contacts.role/lawful_basis
    in migrations/024, which use TEXT CHECK sets rather than boolean/enum).
  - notes            TEXT, freeform recruiter notes -- added
    "IF NOT EXISTS" defensively in case a parallel branch already added it
    (028-030 are taken by parallel branches per the task); harmless no-op
    otherwise.

Pattern of 014/015/024: idempotent (ALTER ... ADD COLUMN IF NOT EXISTS,
CREATE INDEX IF NOT EXISTS), no DO $$ ... END $$ blocks
(migrations/_runner.py splits on a literal ";"), no unique indexes that
could abort on existing data. The CHECK constraint is declared inline on
the ADD COLUMN (Postgres supports `ADD COLUMN ... CHECK (...)` in one
statement), so it never needs the DROP/ADD CONSTRAINT dance
016/018/026 use for a CHECK added onto an *existing* column with
possibly-nonconforming data -- erkend_referent is brand new here with a
DEFAULT that already satisfies its own CHECK, so every existing row (and
the column's own default) is valid the moment it's added.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "031_clients_erkend_referent"

MIGRATION_SQL = """
ALTER TABLE clients ADD COLUMN IF NOT EXISTS erkend_referent TEXT NOT NULL DEFAULT 'onbekend' CHECK (erkend_referent IN ('ja', 'nee', 'onbekend'));
ALTER TABLE clients ADD COLUMN IF NOT EXISTS notes TEXT;
CREATE INDEX IF NOT EXISTS idx_clients_erkend_referent ON clients(erkend_referent);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
