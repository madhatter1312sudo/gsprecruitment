"""
Talent OS — Schema migration: add subject column to outreach_messages,
and add a created_at column (missing from init_db.sql definition).
"""

MIGRATION_SQL = """
ALTER TABLE outreach_messages
    ADD COLUMN IF NOT EXISTS subject VARCHAR(500),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();
"""

if __name__ == "__main__":
    import asyncio
    import asyncpg
    import os

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "recruitment_db")
    user = os.getenv("POSTGRES_USER", "talentos_admin")
    password = os.getenv("POSTGRES_PASSWORD", "")

    async def run():
        conn = await asyncpg.connect(host=host, port=port, database=db, user=user, password=password)
        try:
            await conn.execute(MIGRATION_SQL)
            print("Migration 008 completed: outreach_messages.subject added.")
        finally:
            await conn.close()

    asyncio.run(run())
