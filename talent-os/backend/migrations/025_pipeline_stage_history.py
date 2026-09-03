"""
Talent OS — WS-C.5: pipeline_stage_history (audit trail of pipeline_entries.stage changes).

`pipeline_entries` (migrations/002_portal_tables.py) has always overwritten
`stage` in place -- nothing recorded *when* a candidate moved from
'sourced' to 'interview', or who moved them. This table is an append-only
log of every stage transition, written by routers/client.py's and
routers/admin.py's pipeline stage-update endpoints (never by the initial
add-to-pipeline INSERT's implicit default, except as a from_stage=NULL
row documenting the entry's starting stage).

Columns:
  - pipeline_entry_id  FK -> pipeline_entries(id), ON DELETE CASCADE --
    history has no meaning once the pipeline entry itself is gone.
  - from_stage         text, nullable -- NULL means this is the entry's
    first recorded stage (row created, or history introduced after the
    fact for a pre-existing entry).
  - to_stage           text, NOT NULL -- the stage moved to.
  - changed_by         integer, nullable -- users.id of the actor (client
    portal user or admin). No FK to `users` on purpose: a user account can
    be soft-deleted (users.deleted_at) long after they made a change here,
    and this history must not evaporate or block that deletion the way an
    ON DELETE CASCADE/RESTRICT FK would (same reasoning as audit_log.actor_id,
    which is also a plain integer, not a FK, in migrations/002_portal_tables.py).
  - changed_at         timestamptz, default NOW().

Pattern of 014/015: idempotent (CREATE TABLE IF NOT EXISTS / CREATE INDEX
IF NOT EXISTS), no unique indexes that could abort on existing data, no DO
$$ ... END $$ blocks.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "025_pipeline_stage_history"

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_stage_history (
    id                  SERIAL PRIMARY KEY,
    pipeline_entry_id   INTEGER NOT NULL REFERENCES pipeline_entries(id) ON DELETE CASCADE,
    from_stage          TEXT,
    to_stage            TEXT NOT NULL,
    changed_by          INTEGER,
    changed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_stage_history_entry ON pipeline_stage_history(pipeline_entry_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_stage_history_changed_at ON pipeline_stage_history(changed_at DESC);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
