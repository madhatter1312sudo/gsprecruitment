"""
Talent OS — Schema migration: users + candidate_profiles tables.
Run against the PostgreSQL database directly.
"""

MIGRATION_SQL = """
-- ── Users table ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'candidate'
                        CHECK (role IN ('candidate', 'client', 'admin')),
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    verification_token VARCHAR(255),
    reset_token     VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_verification_token ON users(verification_token) WHERE verification_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_reset_token ON users(reset_token) WHERE reset_token IS NOT NULL;

-- ── Candidate Profiles table (extended profile data linked to user) ─────
CREATE TABLE IF NOT EXISTS candidate_profiles (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    phone               VARCHAR(50),
    linkedin_url        TEXT,
    github_url          TEXT,
    portfolio_url       TEXT,
    current_company     VARCHAR(255),
    current_title       VARCHAR(255),
    location            VARCHAR(255),
    willing_to_relocate BOOLEAN NOT NULL DEFAULT FALSE,
    salary_expectation_min INTEGER,
    salary_expectation_max INTEGER,
    notice_period_days  INTEGER,
    years_experience    NUMERIC(4,1),
    skills              TEXT[] DEFAULT '{}',
    languages           TEXT[] DEFAULT '{}',
    education           TEXT,
    cv_text             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_candidate_profiles_user_id ON candidate_profiles(user_id);
"""

if __name__ == "__main__":
    import asyncio
    import asyncpg
    import sys
    import os

    # Load connection params from environment (fallback to defaults)
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "recruitment_db")
    user = os.getenv("POSTGRES_USER", "talentos_admin")
    password = os.getenv("POSTGRES_PASSWORD", "")

    async def run():
        conn = await asyncpg.connect(host=host, port=port, database=db, user=user, password=password)
        try:
            for statement in MIGRATION_SQL.split(";"):
                stmt = statement.strip()
                if stmt:
                    await conn.execute(stmt)
            print("Migration completed: users + candidate_profiles tables created.")
        finally:
            await conn.close()

    asyncio.run(run())
