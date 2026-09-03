"""
Talent OS — dedupe salary_benchmarks, then add its natural-key unique index.

Code review follow-up on WS-C.1: 000_baseline.py originally tried to add
`CREATE UNIQUE INDEX idx_salary_benchmarks_natural_key ON
salary_benchmarks(role_title, seniority, location)` directly. That runs on
every deploy, including production where salary_benchmarks already exists
(it's created by migration 002/009's era, not by 000) and has been seeded
by migrations/009_salary_benchmarks_seed.py's bare `ON CONFLICT DO
NOTHING` — which only actually dedupes once a matching unique index
exists. Since 009 may have already run more than once before a unique
index existed, production can already hold duplicate rows on that natural
key, and creating a unique index straight over duplicates fails outright
(aborting the whole deploy). 000_baseline.py is kept strictly structural
now — no data-shape assumptions about existing rows.

This migration does the dedupe first (keep the lowest id per natural key,
NULLS treated as equal for seniority/location so two rows both missing a
seniority for the same role_title/location count as duplicates), then
creates the unique index. Two ordered top-level statements — each a
separate top-level entry after MIGRATION_SQL.split(";"), same as every
other migration here; this migration deliberately never needs a `DO $$`
block, so it doesn't run into the internal-semicolon splitting issue
000_baseline.py's docstring flags.

Idempotent: DELETE affects zero rows on a second run once the dupes are
gone, and CREATE UNIQUE INDEX IF NOT EXISTS is a no-op if already present.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "015_salary_benchmarks_natural_key"

MIGRATION_SQL = """
DELETE FROM salary_benchmarks a USING salary_benchmarks b WHERE a.id > b.id AND a.role_title = b.role_title AND a.seniority IS NOT DISTINCT FROM b.seniority AND a.location IS NOT DISTINCT FROM b.location;
CREATE UNIQUE INDEX IF NOT EXISTS idx_salary_benchmarks_natural_key ON salary_benchmarks(role_title, seniority, location);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
