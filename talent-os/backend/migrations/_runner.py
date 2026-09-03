"""
Talent OS — Shared migration runner.

Tracks applied migrations in a `schema_migrations` table so scripts can be
re-run safely and it's always clear what's already been applied. Each
numbered migration module should define VERSION and MIGRATION_SQL and call
run_migration() from its __main__ block.
"""
import os


async def ensure_schema_migrations_table(conn):
    await conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            version     TEXT PRIMARY KEY,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )


async def run_migration(version: str, sql: str):
    import asyncpg

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "recruitment_db")
    # Matches core/config.py's Settings.postgres_user default and
    # talent-os/.env.example (WS-C.1) -- this used to default to
    # "talentos_admin" here while the app itself (core/config.py) and the
    # env template both default to "talentos_write", a literal divergence
    # that only mattered if POSTGRES_USER was ever left unset when a
    # migration ran directly. Production always sets POSTGRES_USER
    # explicitly (talent-os/.env via env_file), so this default is a
    # fallback only -- changing it does not change what production runs.
    user = os.getenv("POSTGRES_USER", "talentos_write")
    password = os.getenv("POSTGRES_PASSWORD", "")

    conn = await asyncpg.connect(host=host, port=port, database=db, user=user, password=password)
    try:
        await ensure_schema_migrations_table(conn)
        already_applied = await conn.fetchval(
            "SELECT 1 FROM schema_migrations WHERE version = $1", version
        )
        if already_applied:
            print(f"Migration {version} already applied, skipping.")
            return

        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt:
                await conn.execute(stmt)

        await conn.execute(
            "INSERT INTO schema_migrations (version) VALUES ($1)", version
        )
        print(f"Migration {version} applied and recorded.")
    finally:
        await conn.close()
