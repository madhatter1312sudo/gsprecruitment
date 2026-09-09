"""
Talent OS — WS-E.8 retention-kolommen: give clients.account_status a real
write path and a closed value set.

security-auditor FIX FIRST (blocking point 3): `clients.account_status`
(migrations/000_baseline.py, DEFAULT 'active') is read by
core/retention.py's PROSPECT_RESPONDING_SQL guard ("this prospect's
company is an active client -- never purge it") but had NO write path
anywhere in the backend: no router or service ever set it, for any
value. In practice the column meant "a row exists in `clients`", not
"this is a live client relationship" -- and every client-portal
registration (routers/auth.py register(), routers/client.py
_get_client_id()) auto-creates a `clients` stub row, with the *user's own
full name* as company_name, that inherits the same DEFAULT 'active'.
A cancelled/never-real client was therefore protected forever, and the
comment on that guard's own line claimed the opposite of what the code
did.

This migration:

  1. Adds a CHECK constraint closing the value set to
     lead | active | inactive:
       - 'lead'     -- a stub or prospect-stage row, no confirmed
                       business relationship yet (the new DEFAULT, see
                       #2 below). Not a "live client" for
                       PROSPECT_RESPONDING_SQL's purposes.
       - 'active'   -- a real, ongoing client relationship. Only ever
                       set explicitly now, via
                       PATCH /api/v1/admin/clients/{id}
                       (routers/clients_admin.py update_client, this
                       same PR) -- an admin action, audit-logged like
                       every other field that endpoint touches.
       - 'inactive' -- a former client (churned/ended), set the same
                       way. Explicitly NOT "protected" by
                       PROSPECT_RESPONDING_SQL's guard, matching that
                       row's own "zolang actief" (as long as active)
                       bewaartermijn -- a client that stopped being
                       active is exactly who that clause stops
                       protecting.
     Existing rows are normalised first (any value outside the three
     above becomes 'lead') so the ALTER never aborts on legacy data --
     migrations/000_baseline.py's DEFAULT 'active' is the only value
     this backend has ever written, so in practice this is a no-op.

  2. Flips the column's DEFAULT from 'active' to 'lead'. Registration's
     stub-client INSERTs (routers/auth.py, routers/client.py) never name
     this column, so every *future* stub row starts as 'lead' -- not
     silently protected until an admin confirms the relationship is
     real by moving it to 'active' via the PATCH above.

  3. One bounded backfill for *existing* rows: any 'active' client with
     zero job_orders ever created for it moves to 'lead'. This does not
     fabricate a fact -- job_orders is a real, already-existing signal
     of "this company has actually been engaged as a client" (the
     admin-facing "Opdrachtgevers" list itself is keyed off exactly this
     relationship, routers/clients_admin.py's open_job_count) -- it only
     corrects the *meaning* of a flag that every stub row received by
     accident. A stub row that DOES have a job_orders row (a real deal
     already exists) is deliberately left 'active': that is a real
     signal this migration has no reason to override, unlike the DEFAULT
     every stub row got with no signal behind it at all.

     security-audit follow-up (L2, round 5): the backfill in #3 changes
     `account_status` on existing rows without a human clicking anything --
     the one bulk write in this whole migration set that silently
     reclassifies live data. The affected client ids are therefore logged
     to `audit_log` (action='retention_migration_034_backfill',
     json.dumps'd via jsonb_build_object/jsonb_agg — never a raw dict,
     commit 72b4bcd) in a SELECT run immediately before the UPDATE, so the
     owner can see exactly who was moved to 'lead' by this migration
     after deploying it, via the same audit trail every other admin
     mutation uses (actor_id NULL — a migration, not an admin action).
     After this migration, `account_status` is only ever set again via
     `PATCH /api/v1/admin/clients/{id}` (routers/clients_admin.py
     update_client) — an admin action, audit-logged the normal way.

Pattern of 026 (interest_type): normalise data first (idempotent,
`WHERE` narrows it to rows the CHECK would otherwise reject or the
backfill targets, so a re-run is a no-op), then ALTER COLUMN SET
DEFAULT, then the DROP CONSTRAINT IF EXISTS + ADD CONSTRAINT dance
(Postgres has no ADD CONSTRAINT IF NOT EXISTS). No DO $$ ... END $$
blocks (migrations/_runner.py splits on a literal ";").
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "034_clients_account_status_lifecycle"

MIGRATION_SQL = """
UPDATE clients SET account_status = 'lead'
    WHERE account_status IS NULL
       OR account_status NOT IN ('lead', 'active', 'inactive');

INSERT INTO audit_log (action, actor_id, target_type, target_id, changes)
    SELECT 'retention_migration_034_backfill', NULL, 'client', NULL,
           jsonb_build_object('degraded_to_lead_client_ids', COALESCE(jsonb_agg(id), '[]'::jsonb))
      FROM clients
     WHERE account_status = 'active'
       AND NOT EXISTS (SELECT 1 FROM job_orders j WHERE j.client_id = clients.id);

UPDATE clients SET account_status = 'lead'
    WHERE account_status = 'active'
      AND NOT EXISTS (SELECT 1 FROM job_orders j WHERE j.client_id = clients.id);

ALTER TABLE clients ALTER COLUMN account_status SET DEFAULT 'lead';

ALTER TABLE clients DROP CONSTRAINT IF EXISTS chk_clients_account_status;
ALTER TABLE clients ADD CONSTRAINT chk_clients_account_status
    CHECK (account_status IN ('lead', 'active', 'inactive'));
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
