"""
Unit tests for WS-C.16 "één kandidaatrecord" -- candidate_profiles.candidate_id
FK (migrations/023_candidate_profiles_candidate_id.py), the shared
resolve/create/link helper (services/candidate_link.py), routers/auth.py's
verify-email path creating/linking the candidates row once verified, and
the removal of every UNION CTE / candidates<->candidate_profiles e-mail
join from routers/ in favour of the FK.

Style matches tests/test_ws_c15_job_orders.py (migration text, no DB) and
tests/test_gdpr_erasure.py (a tiny in-memory fake DB monkeypatched over
core.database's fetch_one/fetch_all/execute so the real coroutines run
end to end without Postgres).
"""
import asyncio
import importlib.util
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

import pytest

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(BACKEND_ROOT, "migrations")
ROUTERS_DIR = os.path.join(BACKEND_ROOT, "routers")


def _load_migration(fname):
    path = os.path.join(MIGRATIONS_DIR, fname)
    spec = importlib.util.spec_from_file_location(f"_migration_{fname}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, MIGRATIONS_DIR)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(MIGRATIONS_DIR)
    return mod


# ── Migration 023 text checks ─────────────────────────────────────────────

def test_migration_023_adds_candidate_id_column():
    mod = _load_migration("023_candidate_profiles_candidate_id.py")
    sql = mod.MIGRATION_SQL
    assert "ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS candidate_id INTEGER" in sql


def test_migration_023_fk_is_named_and_on_delete_set_null():
    """The FK is added via a named constraint (DROP CONSTRAINT IF EXISTS
    / ADD CONSTRAINT), not inline on the column -- so re-running this on
    an environment that already has an earlier version of the FK
    converges to ON DELETE SET NULL instead of erroring on 'constraint
    already exists'."""
    mod = _load_migration("023_candidate_profiles_candidate_id.py")
    sql = mod.MIGRATION_SQL
    assert "DROP CONSTRAINT IF EXISTS candidate_profiles_candidate_id_fkey" in sql
    assert (
        "ADD CONSTRAINT candidate_profiles_candidate_id_fkey "
        "FOREIGN KEY (candidate_id) REFERENCES candidates(id) ON DELETE SET NULL" in sql
    )


def test_migration_023_column_is_nullable():
    """No NOT NULL -- an unverified self-registered person legitimately
    has no candidates row yet (WS-E.2)."""
    mod = _load_migration("023_candidate_profiles_candidate_id.py")
    sql = mod.MIGRATION_SQL
    m = re.search(r"ADD COLUMN IF NOT EXISTS candidate_id [^\n;]+", sql)
    assert m, "candidate_id column definition not found"
    assert "NOT NULL" not in m.group(0)


def test_migration_023_index_is_not_unique():
    """A unique index over data that might already violate it aborts the
    whole deploy (see migrations/015's docstring) -- this must stay a
    plain index, never CREATE UNIQUE INDEX."""
    mod = _load_migration("023_candidate_profiles_candidate_id.py")
    sql = mod.MIGRATION_SQL
    assert "CREATE INDEX IF NOT EXISTS idx_candidate_profiles_candidate_id ON candidate_profiles(candidate_id)" in sql
    assert "CREATE UNIQUE INDEX" not in sql


def test_migration_023_is_idempotent_guarded():
    mod = _load_migration("023_candidate_profiles_candidate_id.py")
    sql = mod.MIGRATION_SQL
    assert "ADD COLUMN IF NOT EXISTS" in sql
    assert "DROP CONSTRAINT IF EXISTS" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql
    # Both backfill UPDATEs must be guarded so a second run touches 0 rows.
    assert sql.count("candidate_id IS NULL") >= 2


def test_migration_023_backfill_and_version_insert_run_in_one_transaction():
    src_path = os.path.join(MIGRATIONS_DIR, "023_candidate_profiles_candidate_id.py")
    with open(src_path, encoding="utf-8") as fh:
        src = fh.read()
    assert "async with conn.transaction():" in src
    # The three backfill statements and the schema_migrations INSERT must
    # all sit inside that transaction block, not before it.
    tx_block = src[src.index("async with conn.transaction():"):]
    assert "LINK_EXISTING_SQL" in tx_block
    assert "CREATE_MISSING_SQL" in tx_block
    assert "LINK_CREATED_SQL" in tx_block
    assert "INSERT INTO schema_migrations (version) VALUES ($1)" in tx_block


def test_migration_023_backfill_matches_case_insensitively_lowest_id_wins():
    mod = _load_migration("023_candidate_profiles_candidate_id.py")
    sql = mod.LINK_EXISTING_SQL
    assert "LOWER(c.email) = LOWER(u.email)" in sql
    assert "DISTINCT ON (LOWER(u.email))" in sql
    assert "ORDER BY LOWER(u.email), c.id ASC" in sql


def test_migration_023_creates_missing_candidates_with_portal_provenance():
    mod = _load_migration("023_candidate_profiles_candidate_id.py")
    sql = mod.CREATE_MISSING_SQL
    assert "'portal_registration'" in sql
    assert "'portal_registratie'" in sql
    assert "'https://gsprecruitment.nl/candidate/'" in sql
    assert "cp.candidate_id IS NULL" in sql


def test_migration_023_log_output_never_contains_email_placeholder():
    """The migration log line must report counts only -- grep the actual
    print() call in the module source for anything that looks like it's
    interpolating an e-mail address or row content, not just numbers."""
    mod = _load_migration("023_candidate_profiles_candidate_id.py")
    src_path = os.path.join(MIGRATIONS_DIR, "023_candidate_profiles_candidate_id.py")
    with open(src_path, encoding="utf-8") as fh:
        src = fh.read()
    print_calls = re.findall(r'print\(\s*(?:f?"[^"]*"\s*)+\)', src, re.DOTALL) + \
        re.findall(r"print\(\s*(?:f?'[^']*'\s*)+\)", src, re.DOTALL)
    assert print_calls, "expected at least one print() in the migration"
    joined = "\n".join(print_calls)
    # A count *label* like "linked_by_email=" is fine -- an interpolated
    # e-mail value or address literal (an "@" character) is not.
    assert "@" not in joined


def test_migration_023_uses_schema_migrations_version_guard():
    mod = _load_migration("023_candidate_profiles_candidate_id.py")
    assert mod.VERSION == "023_candidate_profiles_candidate_id"
    src_path = os.path.join(MIGRATIONS_DIR, "023_candidate_profiles_candidate_id.py")
    with open(src_path, encoding="utf-8") as fh:
        src = fh.read()
    assert "SELECT 1 FROM schema_migrations WHERE version = $1" in src
    assert "INSERT INTO schema_migrations (version) VALUES ($1)" in src


# ── No remaining UNION anywhere in routers/ ────────────────────────────────

_SQL_UNION_RE = re.compile(r"\bUNION\s+(?:ALL|SELECT)\b")


def test_no_union_left_in_routers():
    """Matches the actual SQL keyword combination (`UNION ALL` / `UNION
    SELECT`), not just the bare word `UNION` -- a comment or docstring
    prose mentioning "not a SQL UNION" or similar must not trip this."""
    offenders = []
    for fname in os.listdir(ROUTERS_DIR):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(ROUTERS_DIR, fname)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if _SQL_UNION_RE.search(text):
            offenders.append(fname)
    assert not offenders, f"UNION still present in: {offenders}"


# ── services/candidate_link.py -- FK-first / legacy-fallback / create ─────

class _FakeCandidateLinkDB:
    """Records SQL + args; canned responses steer which branch of
    get_or_create_candidate_id() runs, exactly like tests/test_gdpr_erasure.py's
    _FakeDB does for erase_person()."""

    def __init__(self, profile_candidate_id=None, existing_candidate_id=None, new_candidate_id=None):
        self.profile_candidate_id = profile_candidate_id
        self.existing_candidate_id = existing_candidate_id
        self.new_candidate_id = new_candidate_id
        self.statements = []

    async def fetch_one(self, sql, *args):
        self.statements.append((sql, args))
        if "SELECT candidate_id FROM candidate_profiles WHERE user_id" in sql:
            if self.profile_candidate_id is not None:
                return {"candidate_id": self.profile_candidate_id}
            return {"candidate_id": None}
        if sql.strip().startswith("SELECT email, full_name FROM users"):
            return {"email": "person@example.com", "full_name": "Person Example"}
        if sql.strip().startswith("SELECT id FROM candidates WHERE LOWER(email)"):
            if self.existing_candidate_id is not None:
                return {"id": self.existing_candidate_id}
            return None
        if "FROM candidate_profiles WHERE user_id" in sql and "SELECT phone" in sql:
            return {
                "phone": None, "current_title": None, "current_company": None,
                "location": None, "skills": None, "years_experience": None,
            }
        if sql.strip().startswith("INSERT INTO candidates"):
            if self.new_candidate_id is not None:
                return {"id": self.new_candidate_id}
            return None
        return None

    async def execute(self, sql, *args):
        self.statements.append((sql, args))
        return "OK"


def test_get_or_create_candidate_id_returns_fk_directly_without_email_lookup():
    """FK already set -- must not touch the e-mail-fallback SELECT at all."""
    import services.candidate_link as candidate_link

    db = _FakeCandidateLinkDB(profile_candidate_id=42)

    async def fetch_one(sql, *args):
        db.statements.append((sql, args))
        if "SELECT candidate_id FROM candidate_profiles WHERE user_id" in sql:
            return {"candidate_id": 42}
        raise AssertionError(f"unexpected query when FK is already set: {sql}")

    async def execute(sql, *args):
        raise AssertionError(f"unexpected write when FK is already set: {sql}")

    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(candidate_link, "fetch_one", fetch_one)
        mp.setattr(candidate_link, "execute", execute)
        result = asyncio.run(candidate_link.get_or_create_candidate_id(7))

    assert result == 42


def test_get_or_create_candidate_id_falls_back_to_email_and_links():
    """No FK yet, but a candidates row matches by e-mail (legacy row) --
    must return it AND write the link back."""
    import services.candidate_link as candidate_link

    db = _FakeCandidateLinkDB(profile_candidate_id=None, existing_candidate_id=99)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(candidate_link, "fetch_one", db.fetch_one)
        mp.setattr(candidate_link, "execute", db.execute)
        result = asyncio.run(candidate_link.get_or_create_candidate_id(7))

    assert result == 99
    link_writes = [
        (sql, args) for sql, args in db.statements
        if sql.strip().startswith("UPDATE candidate_profiles SET candidate_id")
    ]
    assert link_writes, "expected candidate_profiles.candidate_id to be written back"
    assert link_writes[0][1] == (99, 7)


def test_get_or_create_candidate_id_creates_and_links_when_nothing_matches():
    """No FK, no e-mail match anywhere -- must INSERT a new candidates row
    (portal_registration provenance) and link it."""
    import services.candidate_link as candidate_link

    db = _FakeCandidateLinkDB(profile_candidate_id=None, existing_candidate_id=None, new_candidate_id=123)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(candidate_link, "fetch_one", db.fetch_one)
        mp.setattr(candidate_link, "execute", db.execute)
        result = asyncio.run(candidate_link.get_or_create_candidate_id(7))

    assert result == 123
    inserts = [sql for sql, _args in db.statements if sql.strip().startswith("INSERT INTO candidates")]
    assert inserts and "'portal_registration'" in inserts[0] and "'portal_registratie'" in inserts[0]
    link_writes = [
        (sql, args) for sql, args in db.statements
        if sql.strip().startswith("UPDATE candidate_profiles SET candidate_id")
    ]
    assert link_writes and link_writes[0][1] == (123, 7)


def test_candidate_router_get_candidate_id_delegates_to_shared_helper():
    """routers/candidate.py's _get_candidate_id must not have its own
    e-mail-join/insert logic any more -- it delegates to
    services/candidate_link.get_or_create_candidate_id()."""
    import inspect
    import routers.candidate as candidate_router

    src = inspect.getsource(candidate_router._get_candidate_id)
    assert "get_or_create_candidate_id" in src
    assert "INSERT INTO candidates" not in src


# ── routers/auth.py verify-email creates/links exactly one candidates row ──

def test_verify_email_hashed_links_candidate_for_candidate_role(monkeypatch):
    import routers.auth as auth_router

    calls = {"link": 0}

    async def fake_fetch_one(sql, *args):
        if "FROM users" in sql and "verification_token_hash" in sql:
            return {"id": 55, "role": "candidate"}
        return None

    async def fake_execute(sql, *args):
        return "OK"

    async def fake_get_or_create_candidate_id(user_id):
        calls["link"] += 1
        calls["user_id"] = user_id
        return 999

    monkeypatch.setattr(auth_router, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(auth_router, "execute", fake_execute)
    monkeypatch.setattr(auth_router, "get_or_create_candidate_id", fake_get_or_create_candidate_id)
    monkeypatch.setattr(auth_router, "hash_token", lambda t: "hashed-token")

    class _Req:
        pass

    class _Data:
        token = "raw-token"

    result = asyncio.run(auth_router.verify_email_hashed.__wrapped__(_Req(), _Data()))

    assert result == {"message": "Email verified successfully"}
    assert calls["link"] == 1, "expected exactly one candidates row created/linked"
    assert calls["user_id"] == 55


def test_verify_email_hashed_does_not_link_for_client_role(monkeypatch):
    """A client user must never get a candidates row through this path."""
    import routers.auth as auth_router

    calls = {"link": 0}

    async def fake_fetch_one(sql, *args):
        if "FROM users" in sql and "verification_token_hash" in sql:
            return {"id": 56, "role": "client"}
        return None

    async def fake_execute(sql, *args):
        return "OK"

    async def fake_get_or_create_candidate_id(user_id):
        calls["link"] += 1
        return 999

    monkeypatch.setattr(auth_router, "fetch_one", fake_fetch_one)
    monkeypatch.setattr(auth_router, "execute", fake_execute)
    monkeypatch.setattr(auth_router, "get_or_create_candidate_id", fake_get_or_create_candidate_id)
    monkeypatch.setattr(auth_router, "hash_token", lambda t: "hashed-token")

    class _Req:
        pass

    class _Data:
        token = "raw-token"

    asyncio.run(auth_router.verify_email_hashed.__wrapped__(_Req(), _Data()))
    assert calls["link"] == 0
