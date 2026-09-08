"""
Talent OS — WS-E.8 follow-up: retention guard timezone fixes (security-
audit FIX FIRST and chief-of-staff second FIX FIRST, retention-kolommen
branch, blocking points on migrations/032_retention_anchor_columns.py's
guards).

core/retention.py's REJECTED_APPLICANT_SQL compares
`pipeline_entries.updated_at > candidates.rejected_at`. `rejected_at`
(added by migration 032) is TIMESTAMPTZ; `pipeline_entries.updated_at`
(migrations/002_portal_tables.py) has always been a plain
`TIMESTAMP` (no timezone). Comparing the two directly forces Postgres to
interpret the naive `updated_at` value in whatever timezone the
comparing session happens to be in, so the guard's 4-week exclusion
window silently shifts with the connection's session timezone instead of
being a fixed point in time.

Every timestamp this codebase writes with a bare `NOW()` (matches.
updated_at, candidates.rejected_at, client_prospects.last_contacted_at,
users.last_login_at, ...) is already stored as the session's instant in
UTC via a TIMESTAMPTZ column; pipeline_entries.updated_at was one
straggler still typed TIMESTAMP.

chief-of-staff second FIX FIRST (non-blocking point 4, folded into this
same migration rather than a new one since this is the exact round that
migration exists to fix): `client_prospects.created_at`
(migrations/012_mobile_growth.py) is the other straggler -- also a plain
`TIMESTAMP`, also compared against a bare `NOW()` in
PROSPECT_NO_RESPONSE_SQL ("cp.created_at <= (NOW() - INTERVAL '12
months')"), and that selector's action is `hard_delete` -- the one
category in this table with no anonymise fallback, so a session-timezone
drift on its comparison is the least forgiving place in this file to
leave it. This migration now converts both columns to TIMESTAMPTZ,
reinterpreting existing values as having been written in UTC (the same
assumption every TIMESTAMPTZ column here already makes about its own
NOW() writes -- this app has never run against a non-UTC Postgres
session, and nothing in core/config.py or docker-compose.yml sets a
different one) so both sides of each comparison are the same type going
forward.

Pattern of 019/024/030/031/032: no DO $$ ... END $$ blocks
(migrations/_runner.py splits on a literal ";", which a DO block's own
internal statements would break). Idempotency here comes from
run_migration()'s schema_migrations tracking (a version already recorded
is skipped outright, per migrations/_runner.py) rather than a per-
statement IF NOT EXISTS guard -- ALTER COLUMN ... TYPE has no such guard
to write, and re-running either exact ALTER against an already-TIMESTAMPTZ
column would double-apply the UTC reinterpretation, so this migration
must only ever run once per database, exactly what the tracking table
already guarantees.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "033_retention_guard_fixes"

MIGRATION_SQL = """
ALTER TABLE pipeline_entries
    ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING (updated_at AT TIME ZONE 'UTC');
ALTER TABLE client_prospects
    ALTER COLUMN created_at TYPE TIMESTAMPTZ USING (created_at AT TIME ZONE 'UTC');
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
