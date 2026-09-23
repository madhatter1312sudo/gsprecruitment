"""
Talent OS — WS-E.8 retention-kolommen: users.dormant_warning_sent_at.

Owner decision (2026-09-08): core/retention.py's `portal_account_inactive`
row (PORTAL_ACCOUNT_INACTIVE_SQL) moves from 24 to 18 months of portal
inactivity, with a 30-day advance warning e-mail before that cutoff. The
warning job itself is a separate track and is NOT added by this
migration -- this only adds the column that job will need to stay
idempotent per warning cycle (the same `..._reminder_sent_at` shape
services/scheduler.py's talentpool_reminder_job already uses against
candidates.consent_reminder_sent_at, so a future dormant-account warning
job can be written the same way: select who is due, send, stamp this
column, never re-send within the same cycle).

chief-of-staff FIX FIRST (retention-kolommen branch, finding 2, after this
migration first landed): PORTAL_ACCOUNT_INACTIVE_SQL now DOES read this
column -- an account only qualifies for the monthly review list once
`dormant_warning_sent_at` is set and at least 30 days old, so the
public "waarschuwing 30 dagen vooraf" promise (VERWERKINGSREGISTER §1.4,
privacy.html, privacy-kandidaten.html, SOURCING-SOP) holds by
construction instead of silently. This migration still only adds the
column -- nothing yet WRITES it (the warning job itself, same shape as
talentpool_reminder_job in services/scheduler.py, is a separate,
not-yet-built track) -- so until that job ships, no account can ever
satisfy the new condition and none reaches the list, which is the
correct fail-closed behaviour for a promise nothing yet fulfils.

Pattern of 030/032/033/034/036: idempotent (ADD COLUMN IF NOT EXISTS,
CREATE INDEX IF NOT EXISTS), no DO $$ ... END $$ blocks
(migrations/_runner.py splits on a literal ";"), no DELETE/DROP.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "039_users_dormant_warning"

MIGRATION_SQL = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS dormant_warning_sent_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_users_dormant_warning_sent_at ON users(dormant_warning_sent_at)
    WHERE dormant_warning_sent_at IS NOT NULL;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
