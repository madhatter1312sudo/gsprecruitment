"""
Talent OS — Schema migration: drop indexes made redundant by migration 005.

idx_salary_benchmarks_role duplicates idx_salary_benchmarks_role_title
(both btree(role_title)). idx_matches_candidate is a strict prefix of
idx_matches_candidate_status (candidate_id, status), so any query the
single-column index served, the composite index serves too.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "006_drop_redundant_indexes"

MIGRATION_SQL = """
DROP INDEX IF EXISTS idx_salary_benchmarks_role;
DROP INDEX IF EXISTS idx_matches_candidate;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
