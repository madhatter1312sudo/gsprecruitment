"""
Talent OS — WS-E.8 follow-up: retention anchor columns.

core/retention.py's bewaartabel names three anchor columns that don't
exist yet on `main`: `candidates.rejected_at`, a "last contact" column on
`client_prospects`, and a "last login" column on `users`. Their rows
(`rejected_applicant`, `prospect_responding`, `portal_account_inactive`)
carry `schema_ready=False` and the daily purge job
(services/scheduler.py `run_retention_purge()`) skips them outright --
`_category_result()` never issues a query against a column that isn't
there. This migration adds the three columns so those categories can run.

Columns:
  - candidates.rejected_at TIMESTAMPTZ — stamped the moment
    candidates.status is set to 'rejected' (routers/candidates.py's
    `PATCH /api/candidates/{id}`, and routers/webhook.py's
    `candidate_updated` Hermes action — the only two write paths onto
    candidates.status). core/retention.py's `rejected_applicant` selector
    now also requires status = 'rejected' still holding and no matches/
    pipeline_entries activity *after* rejected_at, so a candidate who was
    marked rejected and then picked back up for another role is not
    purged out from under that.
  - client_prospects.last_contacted_at TIMESTAMPTZ — stamped whenever an
    admin changes a prospect's `status` via `PATCH /api/v1/admin/
    prospects/{id}` (routers/prospects.py -- per that router's own
    docstring, `client_prospects.status` only ever moves by manual admin
    action, so a status change is the one place "we had contact with
    this prospect" is recorded today) and whenever an outreach draft
    targeting a `client_prospect` is approved/sent
    (routers/outreach.py `approve_draft`).
  - users.last_login_at TIMESTAMPTZ — stamped on every successful
    authentication that returns a real (non-MFA-pending) token:
    routers/auth.py `login()` and `google_signin()`, and routers/mfa.py
    `mfa_verify()` / `mfa_recovery()`. Not stamped on `/register` (a new
    account, not yet a login) or `/refresh` (reuses an existing session,
    not a fresh authentication).

Pattern of 024/030/031: idempotent (ADD COLUMN IF NOT EXISTS, CREATE
INDEX IF NOT EXISTS), no DO $$ ... END $$ blocks (migrations/_runner.py
splits on a literal ";").

Not in scope: `matches.updated_at`-adjacent invoice-date column the
`placed_candidate` row's docstring also flags as missing. That row's
`action` is "retain" -- services/scheduler.py's `_category_result()`
returns `not_applicable` for every "retain"/"infra_only" row *before* it
ever looks at `schema_ready`, so the purge job would never query a
dedicated invoice-date column even if one existed (7 years is a floor on
data this job never purges, not a purge trigger). Adding a column nothing
would ever write to or query defeats the point of this PR (see the task
note: a column that never gets filled is worse than no column, since
schema_ready would then claim executability the job still can't act on)
-- so `placed_candidate` keeps schema_ready=False and no column is added
here. Same reasoning for `logs` (action="infra_only", no DB column by
design, enforced by Docker/Caddy log rotation instead).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "032_retention_anchor_columns"

MIGRATION_SQL = """
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_candidates_rejected_at ON candidates(rejected_at) WHERE rejected_at IS NOT NULL;
ALTER TABLE client_prospects ADD COLUMN IF NOT EXISTS last_contacted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_client_prospects_last_contacted_at ON client_prospects(last_contacted_at) WHERE last_contacted_at IS NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_users_last_login_at ON users(last_login_at) WHERE last_login_at IS NOT NULL;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
