"""
Talent OS -- issue #147 follow-up: uq_candidates_email must not block a
referral for an address a soft-deleted candidates row still holds.

Context: routers/admin.py's referral duplicate check now filters its own
SELECT on `deleted_at IS NULL` (issue #147), so the application-level
lookup no longer treats a soft-deleted row as a conflict. But
uq_candidates_email (migrations/013_email_nulls_distinct.py) is a
table-wide `UNIQUE NULLS DISTINCT (email)` constraint with no such
filter: even after the application check is fixed, inserting a new
candidates row for an address a soft-deleted row still carries would
still fail at the database with a unique-violation, not the 201 the
issue's acceptance criteria call for.

In today's only code path that sets candidates.deleted_at
(routers/gdpr.py erase_person()), the row's `email` column is
overwritten with privacy.email_hash(email) in the same UPDATE that sets
deleted_at, so this exact collision cannot yet happen through erasure --
but the referral route's own duplicate-check fix (and this constraint)
must hold for ANY soft-deleted row, not only ones erase_person()
produces today, since nothing enforces that pairing at the database
level and a future soft-delete path (or a manually corrected row) could
easily produce one that doesn't anonymise the address.

Fix: replace the table-wide constraint with a partial unique index
scoped to live rows (`WHERE deleted_at IS NULL`), so:
  - two live (not soft-deleted) candidates can never share an email --
    identical behaviour to today for every row that isn't soft-deleted,
    which is the overwhelming majority of the table;
  - a soft-deleted row's email no longer blocks a new row for the same
    address, matching admin.py's referral duplicate check;
  - NULL emails remain unconstrained against each other, matching
    UNIQUE NULLS DISTINCT's behaviour (a plain b-tree index treats NULLs
    as distinct from one another by default, with no explicit option
    needed).

No data is migrated or rewritten -- this only replaces one constraint
with an equivalent-for-live-rows partial index. Postgres has no
"ALTER CONSTRAINT ... ADD WHERE"; dropping and recreating is the only
way to add the filter, same DROP-then-ADD pattern as 013 itself.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "044_candidates_email_unique_excludes_deleted"

MIGRATION_SQL = """
ALTER TABLE candidates DROP CONSTRAINT IF EXISTS uq_candidates_email;
DROP INDEX IF EXISTS uq_candidates_email;
CREATE UNIQUE INDEX IF NOT EXISTS uq_candidates_email
    ON candidates (email) WHERE deleted_at IS NULL;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
