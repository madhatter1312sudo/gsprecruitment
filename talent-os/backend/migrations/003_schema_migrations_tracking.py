"""
Talent OS — Bootstrap schema_migrations tracking, and back-register
001/002 (already applied by hand before this tracking existed).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import ensure_schema_migrations_table  # noqa: E402


async def run():
    import asyncpg

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "recruitment_db")
    user = os.getenv("POSTGRES_USER", "talentos_admin")
    password = os.getenv("POSTGRES_PASSWORD", "")

    conn = await asyncpg.connect(host=host, port=port, database=db, user=user, password=password)
    try:
        await ensure_schema_migrations_table(conn)
        for version in ("001_users", "002_portal_tables"):
            await conn.execute(
                "INSERT INTO schema_migrations (version) VALUES ($1) ON CONFLICT DO NOTHING",
                version,
            )
        print("schema_migrations bootstrapped; 001/002 back-registered.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
