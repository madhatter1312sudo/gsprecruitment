"""
Talent OS — WS2: lead origin tracking (source_page + referrer_host) on
contact_submissions and quiz_submissions (WS-C.10's two unified lead
tables, see routers/admin.py's GET /v1/admin/leads).

Adds, to both tables:
  - source_page     TEXT, nullable -- the site path the form was
    submitted from (e.g. '/vacatures/123?job=456'), validated at the API
    boundary (models/schemas.py's LeadSubmit / QuizSubmitRequest: must
    start with '/', <=200 chars, querystring limited to the keys
    'type'/'job').
  - referrer_host    TEXT, nullable -- the bare hostname (no scheme, no
    path) of document.referrer at submission time, same 100-char cap
    validated at the API boundary.

Both columns are purely additive and nullable -- no backfill for existing
rows, no CHECK constraint. Validation lives entirely in models/schemas.py
here (unlike 026_leads_interest_type.py's CHECK-plus-Pydantic-validator
pair): these are free-form paths/hostnames, so a DB-level CHECK would
just duplicate the same regex in SQL with no real safety gain, and (unlike
interest_type) nothing else ever writes these columns directly that would
need the DB itself to enforce the shape.

Idempotent (ADD COLUMN IF NOT EXISTS), style of 016/026: no DO $$ blocks
(migrations/_runner.py splits on a literal ";"), no unique index.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "038_leads_origin"

MIGRATION_SQL = """
ALTER TABLE contact_submissions ADD COLUMN IF NOT EXISTS source_page TEXT;
ALTER TABLE contact_submissions ADD COLUMN IF NOT EXISTS referrer_host TEXT;
ALTER TABLE quiz_submissions ADD COLUMN IF NOT EXISTS source_page TEXT;
ALTER TABLE quiz_submissions ADD COLUMN IF NOT EXISTS referrer_host TEXT;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
