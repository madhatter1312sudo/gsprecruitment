"""
Talent OS — WS-E.8 "bewaartabel, purge en Apollo-pool". Numbered 022: 020
and 021 are taken by other in-flight branches at the time this was
written (not yet on main in this branch's history).

Adds candidates.pool_origin TEXT and backfills 'apollo' onto every
existing row Apollo put there, so routers/retention_admin.py's Apollo-pool
purge endpoint (POST /api/v1/admin/apollo-pool/purge) and any future
reporting can select the pool without re-deriving it from source/source_url
every time.

Backfill condition matches exactly how Apollo rows are marked today
(services/harvest.py, services/scheduler.py):
  - services/scheduler.py's apollo_search_and_sync() inserts with
    source = 'apollo' (candidates INSERT, "apollo", "scheduler-apollo-sync").
  - services/harvest.py's harvest_candidates() (bulk one-shot harvest)
    inserts with source = 'apollo_bulk' and source_url = 'apollo:{id}'
    when Apollo returned a person id (harvest.py:222/236/476) -- caught
    by the source_url LIKE 'apollo:%' clause below. But apollo_ref is
    None (source_url stays NULL) whenever Apollo's preview record has no
    id at all (harvest.py's `apollo_ref = f"apollo:{person.get('id')}" if
    person.get('id') else None`), so the source_url clause alone misses
    that subset. security-auditor follow-up (WS-E.8 MEDIUM): the backfill
    also matches source = 'apollo_bulk' directly, independent of
    source_url, so those NULL-source_url rows are still labelled
    pool_origin='apollo' (and, not incidentally, still land in
    routers/retention_admin.py's purge target set, since that endpoint
    already treats any pool_origin='apollo' row without an http(s)
    source_url as in-scope).

Pattern of 014/015/018: idempotent (ADD COLUMN IF NOT EXISTS, a plain
UPDATE ... WHERE that is safe to re-run since it only ever sets the same
value), no `DO $$ ... END $$;` blocks (migrations/_runner.py splits on a
literal ";" -- see 000_baseline.py's docstring).

This migration does NOT delete or anonymise any row -- it only adds and
backfills a label column. Per the WS-E.8 task's hard rule, no migration in
this PR deletes production data; the actual Apollo-pool wipe/keep decision
is the owner's (VERWERKINGSREGISTER.md §2.6, §5.7) and, once made, runs
through routers/retention_admin.py's purge endpoint (dry-run by default,
confirm="DELETE APOLLO POOL" required for a real run), never automatically.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "022_apollo_pool_flag"

MIGRATION_SQL = """
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS pool_origin TEXT;
UPDATE candidates SET pool_origin = 'apollo'
    WHERE pool_origin IS NULL
      AND (source = 'apollo' OR source = 'apollo_bulk' OR source_url LIKE 'apollo:%');
CREATE INDEX IF NOT EXISTS idx_candidates_pool_origin ON candidates(pool_origin) WHERE pool_origin IS NOT NULL;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
