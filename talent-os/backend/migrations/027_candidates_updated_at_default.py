"""
Talent OS — fix candidates.updated_at coming back NULL.

No INSERT into candidates (routers/candidates.py create_candidate,
routers/webhook.py, routers/candidate.py portal registration,
services/harvest.py, services/scheduler.py) ever sets updated_at, and the
column had no DEFAULT, so every never-updated row read back NULL there.
models/schemas.py's CandidateResponse.updated_at was `datetime` (required),
so GET /api/candidates and GET /api/candidates/{id} raised
ResponseValidationError on any such row (fixed alongside this migration by
making that field Optional -- belt and braces, since old rows created
before this migration runs must still read fine even without it).

This migration:
  1. Sets a column DEFAULT so every future INSERT that omits updated_at
     gets NOW() instead of NULL.
  2. Backfills existing NULL rows from created_at (best available
     approximation -- these rows have in fact never been updated since
     creation).

Pattern of 014/015/018/022: idempotent (ALTER COLUMN SET DEFAULT is safe
to re-run, and the UPDATE only touches rows still NULL), no `DO $$ ... END
$$;` blocks (migrations/_runner.py splits on a literal ";" -- see
000_baseline.py's docstring).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "027_candidates_updated_at_default"

MIGRATION_SQL = """
ALTER TABLE candidates ALTER COLUMN updated_at SET DEFAULT NOW();
UPDATE candidates SET updated_at = created_at WHERE updated_at IS NULL;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
