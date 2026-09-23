"""
Talent OS — WS-E.10: retention review queue (owner decision, retention-
kolommen branch, fifth round).

Replaces the automatic daily retention purge with a monthly human-approved
one. core/retention.py's guarded selectors (unchanged by this migration)
still decide exactly who is due; what changes is that reaching that state
now only queues the person for review instead of triggering
erase_person()/DELETE by itself. See core/retention.py's module docstring
and routers/retention_admin.py's module docstring for the full mechanism.

Two tables:

  - retention_review_items: one row per (category, subject_table,
    subject_id) — the person/row currently or previously on the monthly
    list. Kept indefinitely (never DELETEd) so a rejection is never
    silently forgotten: if the same subject reappears on a later monthly
    run, the existing row is reopened (status back to 'pending') with
    `reappeared_after_rejection_at` stamped to the first rejection's
    timestamp, rather than a fresh, indistinguishable row being inserted
    -- the "iemand die hij niet goedkeurt, moet niet volgende maand
    opnieuw op de lijst staan zonder dat zichtbaar is dat hij eerder is
    overgeslagen" requirement. UNIQUE(category, subject_table, subject_id)
    is what makes that upsert possible -- subject_table, not just
    subject_id, because "leads_quiz" alone spans two unrelated tables
    (quiz_submissions and contact_submissions) whose ids are not
    comparable to each other.
    `status`: pending | rejected | purging | purged | no_longer_eligible.
    'no_longer_eligible' is set when a 'pending' item drops out of the
    live selector on a later run (the person picked up a protective
    signal since being queued) -- kept for visibility, not deleted,
    same reasoning as a rejection. 'purging' (round 5, M2) is a short-
    lived claim state: `routers/retention_admin.py`'s `_approve_one()`
    moves a 'pending'/'rejected' item there via an atomic
    `UPDATE ... WHERE status IN ('pending','rejected') RETURNING id`
    before acting, so a second concurrent approve on the same item finds
    no row to claim and stops instead of racing the first one's
    erase_person()/DELETE. Once handled, the row's `email` column is
    nulled (routers/retention_admin.py, routers/gdpr.py's erase_person())
    for every status except 'pending' -- see VERWERKINGSREGISTER.md §1.2
    for the row-level retention that column-level nulling is part of.
    This table itself holds personal data (email, a category, a reason
    a person is due for deletion) -- it is therefore covered by the same
    admin-JWT auth as every other admin endpoint (require_role("admin"),
    routers/retention_admin.py) and never surfaced anywhere unauthenticated
    (see that router's own docstring on why the Telegram-facing summary
    endpoint carries counts only, never rows).
    `action` (anonymise|hard_delete) is stored per item, not only derived
    from `category`: the Apollo-pool cleanup (VERWERKINGSREGISTER.md
    §2.6/§5.7, previously its own direct-delete endpoint,
    POST /api/v1/admin/apollo-pool/purge) is folded into this same queue
    as category='apollo_pool_purge' -- unlike every other category, its
    action varies row by row (anonymise when the row has an e-mail
    address, hard_delete when it doesn't, per routers/gdpr.py's
    suppression_list reasoning), so the review item is the one place that
    per-row choice is recorded.

  - retention_review_decisions: append-only audit trail of who approved
    or rejected which item and when, in the same spirit as the audit_log
    rows the consent endpoints already write (routers/admin.py
    admin_update_talentpool_consent). Deliberately a *dedicated* table
    rather than only an audit_log row: retention_review_items.status
    needs to look up "was this ever rejected before" cheaply and the
    decisions table is that lookup, while the existing audit_log INSERT
    (routers/retention_admin.py approve_review_item(), json.dumps'd,
    counts/keys only per commit 72b4bcd) still records the actual purge
    action for the register/security-audit trail every other admin
    mutation uses.

    security-audit follow-up (M4, round 5): "append-only" used to be only
    a comment, not something the database enforced -- any code with
    write access could UPDATE or DELETE a decision row and there would be
    no trace. Migration 037 is reserved for another track, so this fixes
    it here, in 036 itself (not yet applied to production): two rules
    make UPDATE and DELETE against retention_review_decisions silent
    no-ops at the database level, regardless of which application code
    (or a future bug in it) attempts one. `CREATE OR REPLACE RULE` is
    itself idempotent, matching the CREATE TABLE IF NOT EXISTS/ADD COLUMN
    IF NOT EXISTS pattern the rest of this file follows.

Pattern of 030/032/033/034: idempotent (CREATE TABLE IF NOT EXISTS, ADD
COLUMN IF NOT EXISTS, CREATE INDEX IF NOT EXISTS, CREATE OR REPLACE RULE),
no DO $$ ... END $$ blocks (migrations/_runner.py splits on a literal
";"), no DELETE/DROP.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "036_retention_review_queue"

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS retention_review_items (
    id                              SERIAL PRIMARY KEY,
    category                        TEXT NOT NULL,
    subject_table                   TEXT NOT NULL,
    subject_id                      INTEGER NOT NULL,
    email                           TEXT,
    action                          TEXT NOT NULL CHECK (action IN ('anonymise', 'hard_delete')),
    term_expired_at                 TIMESTAMPTZ,
    signal_missing_nl               TEXT NOT NULL DEFAULT '',
    status                          TEXT NOT NULL DEFAULT 'pending'
                                      CHECK (status IN ('pending', 'rejected', 'purging', 'purged', 'no_longer_eligible')),
    first_seen_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reappeared_after_rejection_at   TIMESTAMPTZ,
    purged_at                       TIMESTAMPTZ,
    UNIQUE (category, subject_table, subject_id)
);
CREATE INDEX IF NOT EXISTS idx_retention_review_items_status ON retention_review_items(status);
CREATE INDEX IF NOT EXISTS idx_retention_review_items_category ON retention_review_items(category);

CREATE TABLE IF NOT EXISTS retention_review_decisions (
    id               SERIAL PRIMARY KEY,
    review_item_id   INTEGER NOT NULL REFERENCES retention_review_items(id),
    decision         TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    actor_id         INTEGER REFERENCES users(id),
    decided_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    note             TEXT
);
CREATE INDEX IF NOT EXISTS idx_retention_review_decisions_item ON retention_review_decisions(review_item_id);

CREATE OR REPLACE RULE retention_review_decisions_no_update AS
    ON UPDATE TO retention_review_decisions DO INSTEAD NOTHING;
CREATE OR REPLACE RULE retention_review_decisions_no_delete AS
    ON DELETE TO retention_review_decisions DO INSTEAD NOTHING;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
