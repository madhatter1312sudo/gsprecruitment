"""
Talent OS — WS-C.16 "één kandidaatrecord": link candidate_profiles to
candidates via a real FK instead of joining/UNIONing the two tables by
e-mail everywhere.

Today a self-registered person exists as two independent rows: a
`users` + `candidate_profiles` row (created at POST /api/auth/register)
and, separately, a `candidates` row (created lazily the first time they
touch matches/applications/saved-jobs/messages —
routers/candidate.py:_get_candidate_id() — or pre-existing if they were
already in the sourcing pipeline under the same e-mail before they ever
registered). Several routers (admin.py's candidate list, gdpr.py's
export/erase) have had to re-derive that link by joining on
LOWER(email) every time, including a UNION CTE in admin.py. This
migration adds the FK so that join only has to happen once, here, as a
one-time backfill.

Adds `candidate_profiles.candidate_id INTEGER` (nullable — a
self-registered person who has never triggered candidates row creation,
e.g. an unverified signup per WS-E.2, legitimately has none yet), a
named FK constraint `candidate_profiles_candidate_id_fkey REFERENCES
candidates(id) ON DELETE SET NULL` (a `candidates` row being erased/
deleted must not fail or cascade-delete the person's own profile — see
routers/gdpr.py's erase_person, which already anonymises the candidates
row in place rather than deleting it, but ON DELETE SET NULL is the
correct behaviour regardless of how a candidates row disappears), plus a
plain (non-unique) index for the lookup. The FK constraint is added via
`DROP CONSTRAINT IF EXISTS ... ; ADD CONSTRAINT ...` under the fixed name
above rather than inline on the column, so re-running this on an
environment that already has an earlier (unnamed-equivalent, no ON
DELETE clause) version of this FK converges it to the current definition
instead of erroring on "constraint already exists".

Backfill, in order:
  1. Link every candidate_profiles row to an existing candidates row by
     case-insensitive e-mail match against users.email. When more than
     one candidates row shares the same e-mail (case-insensitive) —
     data debt from years of Apollo re-imports before
     migrations/013_email_nulls_distinct.py's UNIQUE NULLS DISTINCT
     constraint existed — the lowest candidates.id wins (DISTINCT ON
     ... ORDER BY c.id ASC), same tie-break rule as
     migrations/015_salary_benchmarks_natural_key.py's dedupe.
  2. For every profile still unlinked after step 1 (no candidates row
     shares that e-mail at all), insert one: source='portal_registration',
     lawful_basis='portal_registratie' (already a valid value per
     migrations/018_gdpr_provenance_optout.py's CHECK), source_url=
     'https://gsprecruitment.nl/candidate/' — the exact same shape
     routers/candidate.py:_get_candidate_id() already inserts for this
     case, just done once here for every existing row instead of lazily
     per-request. Restricted to role='candidate' profiles (the only kind
     candidate_profiles rows are ever created for) as a defensive filter.
  3. Link the rows step 2 just created (that INSERT doesn't itself know
     the new candidates.id to write back into candidate_profiles.candidate_id
     in one statement).

No unique index is created on candidate_id — a unique index here could
abort the whole migration outright if any data anomaly ever left two
candidate_profiles rows resolving to the same candidates row (e.g. two
user accounts sharing one e-mail through some historical account-merge
path); a plain index is enough for the lookups routers/*.py need
(candidate_profiles.candidate_id first, e-mail fallback only for legacy
rows this backfill somehow missed — see routers/candidate.py's
_get_candidate_id() and routers/admin.py's candidate list).

Pattern of 014/015: idempotent (ADD COLUMN IF NOT EXISTS / DROP+ADD
CONSTRAINT / CREATE INDEX IF NOT EXISTS, and both backfill UPDATEs are
WHERE candidate_id IS NULL-guarded so a second run touches zero rows),
no `DO $$ ... END $$;` blocks (migrations/_runner.py's run_migration()
splits on a literal ";", which would mangle one — see 000_baseline.py's
docstring). This migration doesn't use run_migration() directly, unlike
014/015, only because it needs the per-statement affected-row counts for
its log line (asyncpg's conn.execute() return tag, e.g. "UPDATE 5") — it
still uses the same schema_migrations version-guard
(ensure_schema_migrations_table / SELECT ... WHERE version = $1 /
INSERT INTO schema_migrations) so `python3 migrations/023_*.py` behaves
identically to every other migration script in this directory, and
still runs as part of the normal 000→NNN sequence.

The three backfill statements (LINK_EXISTING_SQL, CREATE_MISSING_SQL,
LINK_CREATED_SQL) plus the schema_migrations version insert run inside a
single `async with conn.transaction():` block — either the whole backfill
lands and is recorded as applied, or (on any error) none of it does,
rather than leaving candidate_profiles partially linked with the version
row not yet written (which a retry would then redo safely anyway thanks
to the IS NULL guards, but there is no reason to allow the partial state
to be observable in between).

The migration log reports counts only (rows linked / rows created) —
never any e-mail address or other PII, per the GSP house rule (secrets/
personal data never printed).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import ensure_schema_migrations_table  # noqa: E402

VERSION = "023_candidate_profiles_candidate_id"

SCHEMA_SQL = """
ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS candidate_id INTEGER;
ALTER TABLE candidate_profiles DROP CONSTRAINT IF EXISTS candidate_profiles_candidate_id_fkey;
ALTER TABLE candidate_profiles ADD CONSTRAINT candidate_profiles_candidate_id_fkey FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_candidate_profiles_candidate_id ON candidate_profiles(candidate_id);
"""

LINK_EXISTING_SQL = """
UPDATE candidate_profiles cp
SET candidate_id = m.candidate_id
FROM (
    SELECT DISTINCT ON (LOWER(u.email)) u.id AS user_id, c.id AS candidate_id
    FROM users u
    JOIN candidates c ON LOWER(c.email) = LOWER(u.email)
    WHERE u.deleted_at IS NULL AND c.deleted_at IS NULL
    ORDER BY LOWER(u.email), c.id ASC
) m
WHERE cp.user_id = m.user_id AND cp.candidate_id IS NULL
"""

CREATE_MISSING_SQL = """
INSERT INTO candidates (full_name, email, phone, current_title, current_company, location,
                         skills, years_experience, source, source_url, lawful_basis, date_found)
SELECT u.full_name, u.email, cp.phone, cp.current_title, cp.current_company, cp.location,
       cp.skills, cp.years_experience, 'portal_registration',
       'https://gsprecruitment.nl/candidate/', 'portal_registratie', CURRENT_DATE
FROM candidate_profiles cp
JOIN users u ON u.id = cp.user_id AND u.deleted_at IS NULL
WHERE cp.candidate_id IS NULL AND u.role = 'candidate'
ON CONFLICT DO NOTHING
"""

LINK_CREATED_SQL = """
UPDATE candidate_profiles cp
SET candidate_id = c.id
FROM users u, candidates c
WHERE cp.user_id = u.id AND LOWER(c.email) = LOWER(u.email)
  AND cp.candidate_id IS NULL AND c.deleted_at IS NULL
"""

# Kept as one combined string too, same shape as every other migration's
# module-level MIGRATION_SQL, so tooling/tests that just want to read the
# SQL text (e.g. a "no unique index" or "IF NOT EXISTS" grep check) don't
# need to know this migration runs its statements individually below.
MIGRATION_SQL = (
    SCHEMA_SQL.strip() + "\n"
    + LINK_EXISTING_SQL.strip() + ";\n"
    + CREATE_MISSING_SQL.strip() + ";\n"
    + LINK_CREATED_SQL.strip() + ";\n"
)


def _rowcount(tag: str) -> int:
    """asyncpg conn.execute() returns a command tag string, e.g.
    'UPDATE 5' or 'INSERT 0 5' — the row count is always the last
    whitespace-separated token."""
    try:
        return int(tag.strip().split()[-1])
    except (ValueError, IndexError):
        return 0


async def run():
    import asyncpg

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "recruitment_db")
    user = os.getenv("POSTGRES_USER", "talentos_write")
    password = os.getenv("POSTGRES_PASSWORD", "")

    conn = await asyncpg.connect(host=host, port=port, database=db, user=user, password=password)
    try:
        await ensure_schema_migrations_table(conn)
        already_applied = await conn.fetchval(
            "SELECT 1 FROM schema_migrations WHERE version = $1", VERSION
        )
        if already_applied:
            print(f"Migration {VERSION} already applied, skipping.")
            return

        for stmt in SCHEMA_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(stmt)

        async with conn.transaction():
            linked_existing = _rowcount(await conn.execute(LINK_EXISTING_SQL))
            created = _rowcount(await conn.execute(CREATE_MISSING_SQL))
            linked_created = _rowcount(await conn.execute(LINK_CREATED_SQL))
            await conn.execute(
                "INSERT INTO schema_migrations (version) VALUES ($1)", VERSION
            )
        # Counts only — never e-mails or other PII (GSP house rule).
        print(
            f"Migration {VERSION} applied and recorded. "
            f"linked_by_email={linked_existing} "
            f"candidates_created={created} "
            f"linked_after_create={linked_created}"
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
