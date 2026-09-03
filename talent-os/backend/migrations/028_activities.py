"""
Talent OS — WS-C.6: activities (unified activity/task log).

A single cross-domain log of notes/calls/emails/meetings/tasks/status
changes, each attached to one "subject" -- a candidate, client, job,
prospect, placement, or lead. This is deliberately separate from
pipeline_stage_history (migrations/025_pipeline_stage_history.py), which
is an append-only audit trail of one specific field transition
(pipeline_entries.stage); activities is the general-purpose CRM log a
recruiter writes to directly (routers/activities.py), including
open/due-dated tasks that WS-B.10 reporting reads via the /today
endpoint.

Columns:
  - subject_type/subject_id -- polymorphic reference (no FK: the six
    subject_type values span six different tables with no shared PK
    space, so referential integrity here is enforced at the API layer,
    same tradeoff client_prospects.company_name/pipeline_entries make
    elsewhere in this schema for cross-table references that don't fit a
    single FK).
  - type            CHECK'd to note|call|email|meeting|task|status_change.
  - body            free text (the note/call summary/task description).
  - due_at          set for type='task' rows that need a deadline; NULL
    for anything else. Indexed on its own (not composite) because the
    /today endpoint scans across all subjects by due_at, not per-subject.
  - completed_at    NULL = open/pending; set = done. A task's "open"
    filter (routers/activities.py's ?open= param and /today) is
    completed_at IS NULL, not a separate status column -- one less
    place for the two to drift out of sync.
  - created_by      FK -> users(id) -- the staff member (or client-portal
    user, for client-portal-authored activities) who wrote the row.
  - created_at/updated_at/deleted_at -- same soft-delete pattern as
    client_contacts (migrations/024_client_contacts.py) and clients/
    candidates: never a real DELETE, GDPR provenance/audit-trail parity.

Pattern of 014/015 (see 024's docstring for the fuller rationale this
repeats): idempotent (CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT
EXISTS), CHECK constraints declared inline on the CREATE TABLE (so
re-running against an already-created table is a no-op via the outer IF
NOT EXISTS, no DROP/ADD CONSTRAINT dance needed), no unique indexes, no
DO $$ ... END $$ blocks (migrations/_runner.py splits on a literal ";").

Indexes: (subject_type, subject_id) for "all activities on this record"
lookups (the router's primary list query), and due_at on its own for the
/today cross-subject scan.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "028_activities"

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS activities (
    id              SERIAL PRIMARY KEY,
    subject_type    TEXT NOT NULL CHECK (subject_type IN ('candidate','client','job','prospect','placement','lead')),
    subject_id      INTEGER NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('note','call','email','meeting','task','status_change')),
    body            TEXT,
    due_at          TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_by      INTEGER REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_activities_subject ON activities(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_activities_due_at ON activities(due_at);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
