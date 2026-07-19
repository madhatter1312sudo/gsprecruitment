"""
Talent OS — Schema migration: allow many null-email candidates.

uq_candidates_email was created UNIQUE NULLS NOT DISTINCT, limiting the whole
table to a single email-less row. Apollo api_search preview records (bulk
harvest) intentionally have no email until selectively enriched, so NULLs must
be distinct. Real emails remain unique.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "013_email_nulls_distinct"

MIGRATION_SQL = """
ALTER TABLE candidates DROP CONSTRAINT IF EXISTS uq_candidates_email;
ALTER TABLE candidates ADD CONSTRAINT uq_candidates_email UNIQUE NULLS DISTINCT (email);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
