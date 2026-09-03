"""
Talent OS — job_orders: demo flag + public-facing fields (WS-C.15 / WS-A.5).

Adds to job_orders:
  - is_demo               boolean NOT NULL DEFAULT false -- marks the 6
    placeholder vacancies migrations/012_mobile_growth.py seeded under the
    internal "GSP Talent Pool" client so the mobile app / public board had
    data before real client job orders existed. Real jobs must never be
    created with is_demo = true; the API defaults new jobs to false and
    nothing sets it true except this migration's one-time backfill below.
  - city                   text, nullable.
  - company_display        text, nullable -- the client-facing company
    name shown on the public job board. NULL means the API returns
    "confidential" (GSP is faceless / anonymous-opdrachtgever by design,
    see routers/jobs.py PUBLIC_JOB_COLUMNS and CLAUDE.md); this column
    lets a specific job opt into showing a real company name later
    without touching `clients`.
  - employment_type        text, nullable -- 'vast' | 'detachering' |
    'interim'. Enforced with a CHECK constraint here (belt) and Pydantic
    validation in models/schemas.py (suspenders), same pattern as
    quiz_questions.domain in migrations/012.
  - sponsorship_possible   boolean NOT NULL DEFAULT false.

Then backfills is_demo = true on the 6 seed jobs from migrations/012. They
are identified by client, not by title string-matching: 012 created (or
reused) exactly one client row with company_name = 'GSP Talent Pool' /
domain = 'gsprecruitment.nl' for this sole purpose, and every job_orders
row under that client_id is one of the 6 seed vacancies (or a future demo
job intentionally added under the same internal client) -- matching on
client_id is robust against the seed titles being edited later, whereas
matching on title text would silently stop working the moment someone
tweaks a seed job's title. All ADD COLUMN / UPDATE statements are
idempotent (IF NOT EXISTS / re-running the UPDATE is a no-op once already
true), safe to re-run like every other migration here.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "016_job_orders_columns"

MIGRATION_SQL = """
ALTER TABLE job_orders ADD COLUMN IF NOT EXISTS is_demo boolean NOT NULL DEFAULT false;
ALTER TABLE job_orders ADD COLUMN IF NOT EXISTS city text;
ALTER TABLE job_orders ADD COLUMN IF NOT EXISTS company_display text;
ALTER TABLE job_orders ADD COLUMN IF NOT EXISTS employment_type text;
ALTER TABLE job_orders ADD COLUMN IF NOT EXISTS sponsorship_possible boolean NOT NULL DEFAULT false;

ALTER TABLE job_orders DROP CONSTRAINT IF EXISTS chk_job_orders_employment_type;
ALTER TABLE job_orders ADD CONSTRAINT chk_job_orders_employment_type
    CHECK (employment_type IS NULL OR employment_type IN ('vast', 'detachering', 'interim'));

CREATE INDEX IF NOT EXISTS idx_job_orders_is_demo ON job_orders(is_demo);

UPDATE job_orders SET is_demo = true
WHERE client_id IN (
    SELECT id FROM clients
    WHERE company_name = 'GSP Talent Pool' AND domain = 'gsprecruitment.nl'
) AND is_demo = false;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
