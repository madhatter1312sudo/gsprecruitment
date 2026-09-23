"""
Talent OS -- Issue #127 (platform-side heartbeat for routine health and
credits alerting): routine_runs.

No table recorded when services/scheduler.py's jobs ran or whether they
succeeded before this migration -- start_scheduler() registered nine daily/
weekly/monthly cron jobs (services/scheduler.py) but nothing wrote their
outcome anywhere durable, so GET /api/v1/admin/health/routines
(routers/admin.py) had no data source. This is the smallest correct
design: one row per job run, written by services/scheduler.py's
_record_routine_run() helper (called from the _tracked() wrapper around
every scheduler.add_job() registration) on both success and failure --
never on a dry run that a system_settings flag skipped, since a skip is
not an attempt.

`routine_name` matches the `id=` string each scheduler.add_job() call uses
(e.g. "matching", "draft_outreach") -- the same identifier
routers/outreach.py's POST /run/{job_name} and JOBS_BY_NAME already use,
so a human reading either surface sees the same name. `error_class` is
`type(exc).__name__` only (e.g. "ConnectionDoesNotExistError"), never the
exception message or a traceback -- messages can carry a candidate/
prospect name or e-mail address interpolated by the raising code, and this
table (like every admin health endpoint) must never carry personal data.
No email/name/id-of-a-person column exists here at all, by construction.

Purely an operational log, same shape as email_log (migrations/040): no
retention job of its own in this migration -- infrastructure log cleanup,
not a WS-E.10 retention category (nothing here is personal data).

Pattern van 030/032/033/034/036/039/040: idempotent (CREATE TABLE IF NOT
EXISTS, CREATE INDEX IF NOT EXISTS), geen DO $$ ... END $$ blokken
(migrations/_runner.py splitst op een letterlijke ";"), geen DELETE/DROP.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "044_routine_runs"

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS routine_runs (
    id           SERIAL PRIMARY KEY,
    routine_name TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('success', 'error')),
    error_class  TEXT,
    ran_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_routine_runs_name_ran_at ON routine_runs(routine_name, ran_at DESC);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
