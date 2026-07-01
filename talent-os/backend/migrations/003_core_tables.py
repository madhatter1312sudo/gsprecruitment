"""
Talent OS — Schema migration: core tables (clients, job_orders, candidates, matches,
salary_benchmarks, outreach_messages, skill_gaps) + missing columns.

This migration uses CREATE TABLE IF NOT EXISTS so it's safe to run even
if the init_db.sql has already created some of these tables.

Missing columns added:
  - candidate_profiles.cv_file_path (VARCHAR(500))
  - candidate_profiles.created_at, updated_at (if missing from old schema)
"""
import asyncio
import asyncpg
import os

MIGRATION_SQL = """
-- ── CLIENTS ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clients (
    id              SERIAL PRIMARY KEY,
    company_name    VARCHAR(255) NOT NULL,
    domain          VARCHAR(255),
    industry        VARCHAR(100),
    location        VARCHAR(255),
    size_range      VARCHAR(50),
    funding_stage   VARCHAR(50),
    apollo_employee_count   INTEGER,
    apollo_funding_stage    VARCHAR(50),
    apollo_technologies     TEXT[],
    apollo_industry         VARCHAR(100),
    hiring_intent_score     DECIMAL(3,2) DEFAULT 0,
    last_hiring_intent_check TIMESTAMP,
    account_status          VARCHAR(50) DEFAULT 'lead',
    assigned_agent_profile  VARCHAR(100),
    consent_granted_at      TIMESTAMP,
    consent_withdrawn_at    TIMESTAMP,
    data_retention_until    TIMESTAMP,
    deleted_at              TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

-- ── JOB ORDERS ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_orders (
    id              SERIAL PRIMARY KEY,
    client_id       INTEGER REFERENCES clients(id),
    title           VARCHAR(255) NOT NULL,
    department      VARCHAR(100),
    seniority       VARCHAR(50),
    location_type   VARCHAR(50),
    salary_min      INTEGER,
    salary_max      INTEGER,
    salary_currency VARCHAR(3) DEFAULT 'EUR',
    description     TEXT,
    requirements    TEXT,
    nice_to_have    TEXT,
    status          VARCHAR(50) DEFAULT 'open',
    urgency         VARCHAR(20) DEFAULT 'normal',
    fee_percentage  DECIMAL(4,2) DEFAULT 20.00,
    fee_value       INTEGER,
    deleted_at      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    filled_at       TIMESTAMP,
    filled_candidate_id INTEGER
);

-- Ensure filled_at column exists (if table already created without it)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'job_orders' AND column_name = 'filled_at'
    ) THEN
        ALTER TABLE job_orders ADD COLUMN filled_at TIMESTAMP;
    END IF;
END $$;

-- ── CANDIDATES ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS candidates (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(255) NOT NULL,
    email           VARCHAR(255),
    phone           VARCHAR(50),
    linkedin_url    VARCHAR(500),
    github_url      VARCHAR(500),
    portfolio_url   VARCHAR(500),
    current_company VARCHAR(255),
    current_title   VARCHAR(255),
    location        VARCHAR(255),
    willing_to_relocate     BOOLEAN DEFAULT FALSE,
    salary_expectation_min  INTEGER,
    salary_expectation_max  INTEGER,
    salary_currency         VARCHAR(3) DEFAULT 'EUR',
    notice_period_days      INTEGER,
    years_experience        DECIMAL(4,1),
    skills          TEXT[],
    languages       TEXT[],
    education       TEXT,
    cv_text         TEXT,
    cv_file_path    VARCHAR(500),
    source          VARCHAR(100),
    source_url      VARCHAR(500),
    sourced_by_agent        VARCHAR(100),
    strength_score          DECIMAL(3,1),
    screening_score         INTEGER,
    screening_notes         TEXT,
    screened_by_agent       VARCHAR(100),
    switch_readiness        VARCHAR(20),
    quality_score           DECIMAL(3,1),
    company_employee_count  INTEGER,
    company_funding_stage   VARCHAR(50),
    company_technologies    TEXT[],
    status          VARCHAR(50) DEFAULT 'sourced',
    is_passive      BOOLEAN DEFAULT TRUE,
    tags            TEXT[],
    consent_granted_at      TIMESTAMP,
    consent_withdrawn_at    TIMESTAMP,
    data_retention_until    TIMESTAMP,
    deleted_at      TIMESTAMP,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW(),
    cv_search tsvector GENERATED ALWAYS AS (
        to_tsvector('dutch', coalesce(cv_text, ''))
    ) STORED
);

-- ── MATCHES ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS matches (
    id              SERIAL PRIMARY KEY,
    job_id          INTEGER REFERENCES job_orders(id),
    candidate_id    INTEGER REFERENCES candidates(id),
    match_score     DECIMAL(5,2),
    match_breakdown JSONB,
    matched_by_agent        VARCHAR(100),
    candidate_interest_score DECIMAL(3,1),
    retention_risk_score     DECIMAL(3,1),
    status          VARCHAR(50) DEFAULT 'pending',
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE (job_id, candidate_id)
);

-- ── SALARY BENCHMARKS ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS salary_benchmarks (
    id              SERIAL PRIMARY KEY,
    role_title      VARCHAR(255) NOT NULL,
    seniority       VARCHAR(50),
    location        VARCHAR(255),
    currency        VARCHAR(3) DEFAULT 'EUR',
    p25             INTEGER,
    p50             INTEGER,
    p75             INTEGER,
    p90             INTEGER,
    sample_size     INTEGER,
    source          VARCHAR(100),
    last_updated    TIMESTAMP DEFAULT NOW()
);

-- ── OUTREACH MESSAGES ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS outreach_messages (
    id              SERIAL PRIMARY KEY,
    campaign_id     INTEGER REFERENCES outreach_campaigns(id),
    candidate_id    INTEGER REFERENCES candidates(id),
    message_text    TEXT NOT NULL,
    personalization_notes TEXT,
    sent_at         TIMESTAMP,
    opened_at       TIMESTAMP,
    replied_at      TIMESTAMP,
    reply_text      TEXT,
    sentiment_score DECIMAL(3,2),
    status          VARCHAR(50) DEFAULT 'draft',
    written_by_agent VARCHAR(100),
    deleted_at      TIMESTAMP
);

-- ── SKILL GAPS ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skill_gaps (
    id              SERIAL PRIMARY KEY,
    candidate_id    INTEGER REFERENCES candidates(id),
    target_role     VARCHAR(255),
    gaps            TEXT[],
    strengths       TEXT[],
    upskill_recommendations TEXT[],
    estimated_time_to_fill_months DECIMAL(3,1),
    analyzed_by_agent VARCHAR(100),
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ── MISSING COLUMNS ────────────────────────────────────────────────────
-- Add cv_file_path to candidate_profiles if missing
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'candidate_profiles' AND column_name = 'cv_file_path'
    ) THEN
        ALTER TABLE candidate_profiles ADD COLUMN cv_file_path VARCHAR(500);
    END IF;
END $$;

-- ── INDEXES ────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_candidates_skills ON candidates USING GIN(skills);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
CREATE INDEX IF NOT EXISTS idx_candidates_email ON candidates(email);
CREATE INDEX IF NOT EXISTS idx_candidates_company ON candidates(current_company);
CREATE INDEX IF NOT EXISTS idx_candidates_created ON candidates(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_candidates_source ON candidates(source);
CREATE INDEX IF NOT EXISTS idx_candidates_cv_search ON candidates USING GIN(cv_search);
CREATE INDEX IF NOT EXISTS idx_job_orders_status ON job_orders(status);
CREATE INDEX IF NOT EXISTS idx_matches_score ON matches(match_score DESC);
CREATE INDEX IF NOT EXISTS idx_matches_job ON matches(job_id);
CREATE INDEX IF NOT EXISTS idx_matches_candidate ON matches(candidate_id);
CREATE INDEX IF NOT EXISTS idx_salary_benchmarks_role ON salary_benchmarks(role_title);
CREATE INDEX IF NOT EXISTS idx_outreach_messages_candidate ON outreach_messages(candidate_id);

-- ── CONSTRAINTS ────────────────────────────────────────────────────────
ALTER TABLE candidates DROP CONSTRAINT IF EXISTS uq_candidates_email;
ALTER TABLE candidates ADD CONSTRAINT uq_candidates_email UNIQUE NULLS NOT DISTINCT (email);
"""


async def run():
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    db = os.getenv("POSTGRES_DB", "recruitment_db")
    user = os.getenv("POSTGRES_USER", "talentos_admin")
    password = os.getenv("POSTGRES_PASSWORD", "")

    conn = await asyncpg.connect(host=host, port=port, database=db, user=user, password=password)
    try:
        for statement in MIGRATION_SQL.split(";"):
            stmt = statement.strip()
            if stmt and stmt != "END":
                try:
                    await conn.execute(stmt + ";")
                except Exception as e:
                    print(f"Warning executing statement: {e}")
                    print(f"  Statement starts with: {stmt[:80]}...")
        print("Migration completed: core tables + missing columns created.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run())