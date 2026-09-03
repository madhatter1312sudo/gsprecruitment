"""
Talent OS — PROVISIONAL baseline schema.

PROVISIONAL — reconstructed from code on 2026-09-02; replace with the
owner's `pg_dump --schema-only` when delivered; every statement is
idempotent (CREATE TABLE/INDEX IF NOT EXISTS, ADD COLUMN IF NOT EXISTS —
no `DO $$ ... END $$;` blocks: migrations/_runner.py's run_migration()
splits each migration's SQL on a literal ";", which would mangle a DO
block's internal semicolons, so every idempotency check here has to be a
single statement) so re-running this on an existing production database
is a no-op.

Why this exists (WS-C.1, MASTERPLAN-2026.md §2 "Backend" / §3.C): migrations
001-014 ALTER or FK-reference `candidates`, `job_orders`, `clients`,
`matches`, `outreach_messages`, `salary_benchmarks`, `hiring_signals`,
`skill_gaps` and `data_subject_requests` without ever CREATE-ing them —
they were assumed to already exist via `talent-os/scripts/init_db.sql`,
which is `.gitignore`d (`*.sql`) and not in git. `system_settings`,
`audit_log`, `contact_submissions`, `site_content` (all migration 002),
and `quiz_questions`/`quiz_submissions`/`client_prospects`/`push_tokens`
(migration 012) and `blog_posts` (migration 011) DO already exist —
verified below, so this file does not touch them.

This migration runs BEFORE 001 (see VERSION "000_baseline", which sorts
and is applied before "001_users" — migrations/_runner.py keys off the
`version` string, and the deploy step now run in filename order, see
.github/workflows/deploy.yml). It reconstructs each table from every
place the code reads/writes it — router SQL (INSERT/UPDATE/SELECT column
lists), pydantic models in models/schemas.py, the UNION CTE in
routers/admin.py, services/harvest.py, services/scheduler.py, and the
ON CONFLICT targets in routers/matches.py and migrations/009 (which seeds
salary_benchmarks with `ON CONFLICT DO NOTHING` and only works if a
matching unique constraint exists). Each column below cites its evidence.

Known code-vs-code disagreements this baseline does NOT resolve (leaves
both, or picks the majority reading) — flagged here for reconciliation
against the owner's `pg_dump --schema-only`:

  1. job_orders fee column: routers/admin.py:291 (AdminJobUpdate allowed
     fields), models/schemas.py JobOrderResponse/AdminJobUpdate all use
     `fee_percentage` (the majority reading — kept as the canonical
     column, NUMERIC default 20.0, matching system_settings's
     'default_fee_percentage' seed in migration 002). But
     routers/client.py:513 reads `fee_value` in the cost-per-hire calc
     and nothing ever writes it. Both columns are created here (fee_value
     nullable, unpopulated) so neither code path breaks; MASTERPLAN-2026.md
     §2 flags this exact line for a psql `\\d job_orders` fix once the real dump
     arrives — the owner's dump decides which one is real and
     routers/client.py:513 should then be fixed to match (out of scope
     for this migration, which only makes the schema self-consistent).
  2. POSTGRES_USER: see the compose/deploy/`_runner.py` changes made in
     the same commit — not a schema disagreement, listed here for
     visibility since WS-C.1 covers both.

Table-by-table evidence (column: source):

candidates — routers/candidates.py (CandidateCreate INSERT: full_name,
  email, phone, linkedin_url, github_url, portfolio_url, current_company,
  current_title, location, willing_to_relocate, salary_expectation_min,
  salary_expectation_max, notice_period_days, years_experience, skills,
  languages, education, cv_text, source, sourced_by_agent, strength_score,
  switch_readiness, tags; PATCH allowed_fields adds status,
  screening_score, screening_notes, quality_score, screened_by_agent);
  models/schemas.py CandidateResponse (id, status, is_passive,
  screening_score, screening_notes, quality_score, cv_file_path,
  created_at, updated_at); routers/webhook.py (is_passive, skills, source,
  sourced_by_agent, strength_score, switch_readiness); services/harvest.py
  (source_url — Apollo person-id provenance, source='apollo_bulk');
  services/scheduler.py (source='apollo', ON CONFLICT (email) DO NOTHING
  → candidates.email needs a unique index for that to work, which
  migrations/013_email_nulls_distinct.py provides right after this
  baseline runs, as uq_candidates_email UNIQUE NULLS DISTINCT (email) —
  not duplicated here, see the comment above CREATE TABLE candidates);
  routers/gdpr.py (consent_withdrawn_at,
  cv_file_path nulled on erasure, deleted_at); routers/admin.py UNION CTE
  (deleted_at, created_at, updated_at all read).

job_orders — routers/jobs.py (client_id, title, department, seniority,
  location_type, salary_min, salary_max, description, requirements,
  urgency, status); models/schemas.py JobOrderCreate/Response (adds
  salary_currency, nice_to_have, fee_percentage); routers/admin.py:291
  (fee_percentage in the allowed-fields set); routers/client.py:472-473
  (filled_at, for time-to-hire); routers/client.py:513 (fee_value — see
  disagreement #1 above); migrations/002 (saved_jobs/pipeline_entries FK
  job_orders(id) — table must pre-exist); migrations/012 seed (client_id,
  title, department, seniority, location_type, salary_min, salary_max,
  salary_currency, description, requirements, nice_to_have, status).

clients — routers/auth.py (company_name, domain on client signup);
  routers/client.py:647 (industry, location, size_range on profile
  update, domain via the 'website' alias); migrations/012 seed
  (account_status); migrations/002 (user_clients/pipeline_entries FK
  clients(id)).

matches — routers/matches.py (candidate_id, job_id, match_score, status;
  `ON CONFLICT (candidate_id, job_id) DO UPDATE` → UNIQUE(candidate_id,
  job_id) required); tasks/screening.py:52 (matched_by_agent -- inactive
  Celery task, not deployed per docker-compose.yml, but still live code
  that must not reference a nonexistent column; its own ON CONFLICT
  target is (job_id, candidate_id) -- same column set, order doesn't
  matter for Postgres's unique-index inference); models/schemas.py
  MatchResponse (match_breakdown —
  never written per MASTERPLAN-2026.md §2, but the response model reads
  it so the column must exist or every /matches response 500s);
  routers/admin.py UNION CTE (status = 'placed' aggregation).

outreach_campaigns — routers/client.py:535,539,545 (id, job_id — only
  fields ever referenced, kept minimal).

outreach_messages — routers/outreach.py:196 (recipient_email, subject,
  body, channel, status); routers/candidate.py (candidate_id, opened_at,
  status != 'draft' checks); routers/client.py:535-545 (campaign_id);
  migrations/008 (adds subject + created_at — created directly here,
  migration 008's ADD COLUMN IF NOT EXISTS becomes a no-op).

salary_benchmarks — migrations/009 (role_title, seniority, location,
  currency, p25, p50, p75, p90, sample_size, source; `ON CONFLICT DO
  NOTHING` bare, with no explicit target — only actually dedupes rows once
  migrations/015_salary_benchmarks_natural_key.py's unique index exists;
  see that file for why the dedupe-then-index logic does not live here).

hiring_signals — routers/webhook.py:82 (company_name, domain,
  signal_type, signal_text, signal_date, confidence, source_url,
  detected_by_agent).

skill_gaps — routers/client.py:331,359 (candidate_id, gaps, strengths,
  created_at — read via `ORDER BY created_at DESC LIMIT 1`, i.e. history
  is kept, not upserted in place).

data_subject_requests — routers/gdpr.py:23 (request_type, request_email,
  status, completed_at, response_summary).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "000_baseline"

MIGRATION_SQL = """
-- ── clients ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clients (
    id              SERIAL PRIMARY KEY,
    company_name    VARCHAR(255) NOT NULL,
    domain          VARCHAR(255),
    industry        VARCHAR(255),
    location        VARCHAR(255),
    size_range      VARCHAR(50),
    account_status  VARCHAR(50) DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_clients_deleted_at ON clients(deleted_at);

-- ── candidates ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS candidates (
    id                      SERIAL PRIMARY KEY,
    full_name               VARCHAR(255) NOT NULL,
    email                   VARCHAR(255),
    phone                   VARCHAR(50),
    linkedin_url            TEXT,
    github_url              TEXT,
    portfolio_url           TEXT,
    current_company         VARCHAR(255),
    current_title           VARCHAR(255),
    location                VARCHAR(255),
    willing_to_relocate     BOOLEAN NOT NULL DEFAULT FALSE,
    salary_expectation_min  INTEGER,
    salary_expectation_max  INTEGER,
    notice_period_days      INTEGER,
    years_experience        NUMERIC(4,1),
    skills                  TEXT[] DEFAULT '{}',
    languages               TEXT[] DEFAULT '{}',
    education               TEXT,
    cv_text                 TEXT,
    cv_file_path            VARCHAR(500),
    source                  VARCHAR(50) DEFAULT 'apollo',
    source_url              TEXT,
    sourced_by_agent        VARCHAR(100),
    is_passive              BOOLEAN NOT NULL DEFAULT TRUE,
    status                  VARCHAR(50) NOT NULL DEFAULT 'sourced',
    screening_score         INTEGER,
    screening_notes         TEXT,
    screened_by_agent       VARCHAR(100),
    quality_score           NUMERIC,
    strength_score          NUMERIC(3,1),
    switch_readiness        VARCHAR(20),
    tags                    TEXT[] DEFAULT '{}',
    consent_withdrawn_at    TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ,
    deleted_at              TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
CREATE INDEX IF NOT EXISTS idx_candidates_source ON candidates(source);
CREATE INDEX IF NOT EXISTS idx_candidates_created ON candidates(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_candidates_deleted_at ON candidates(deleted_at);
CREATE INDEX IF NOT EXISTS idx_candidates_source_url ON candidates(source_url) WHERE source_url IS NOT NULL;

-- No unique index/constraint on candidates.email is created here on
-- purpose: migrations/013_email_nulls_distinct.py (which runs right
-- after this baseline in every deployment) is the sole owner of that --
-- it creates uq_candidates_email UNIQUE NULLS DISTINCT (email). Adding a
-- second one here would double the write cost of every candidate insert/
-- update forever, for no benefit (code review, WS-C.1 follow-up).

-- ── job_orders ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_orders (
    id              SERIAL PRIMARY KEY,
    client_id       INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    title           VARCHAR(255) NOT NULL,
    department      VARCHAR(255),
    seniority       VARCHAR(50),
    location_type   VARCHAR(50),
    salary_min      INTEGER,
    salary_max      INTEGER,
    salary_currency VARCHAR(10) DEFAULT 'EUR',
    description     TEXT,
    requirements    TEXT,
    nice_to_have    TEXT,
    urgency         VARCHAR(20) DEFAULT 'normal',
    status          VARCHAR(50) NOT NULL DEFAULT 'open',
    -- See disagreement #1 in the module docstring: fee_percentage is the
    -- canonical column (schemas.py, admin.py). fee_value is kept too,
    -- unpopulated, because routers/client.py:513 reads it and nothing
    -- must 500 until that line is fixed against the owner's dump.
    fee_percentage  NUMERIC(5,2) DEFAULT 20.0,
    fee_value       NUMERIC(10,2),
    filled_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_job_orders_client ON job_orders(client_id);
CREATE INDEX IF NOT EXISTS idx_job_orders_status ON job_orders(status);
CREATE INDEX IF NOT EXISTS idx_job_orders_created ON job_orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_orders_deleted_at ON job_orders(deleted_at);

-- ── matches ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS matches (
    id              SERIAL PRIMARY KEY,
    candidate_id    INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    job_id          INTEGER NOT NULL REFERENCES job_orders(id) ON DELETE CASCADE,
    match_score     NUMERIC(5,2),
    match_breakdown JSONB,
    matched_by_agent VARCHAR(100),
    status          VARCHAR(50) NOT NULL DEFAULT 'suggested',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ,
    UNIQUE (candidate_id, job_id)
);

-- No idx_matches_candidate here: migrations/006_drop_redundant_indexes.py
-- deliberately drops it in favor of migrations/005's composite
-- idx_matches_candidate_status(candidate_id, status), which is a strict
-- superset -- creating it in 000 would just have 006 delete it again on
-- every fresh deploy (code review, WS-C.1 follow-up).
CREATE INDEX IF NOT EXISTS idx_matches_job ON matches(job_id);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_matches_score ON matches(match_score DESC);

-- ── outreach_campaigns (minimal — only id/job_id are ever read) ─────────
CREATE TABLE IF NOT EXISTS outreach_campaigns (
    id              SERIAL PRIMARY KEY,
    job_id          INTEGER REFERENCES job_orders(id) ON DELETE CASCADE,
    name            VARCHAR(255),
    status          VARCHAR(50) DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outreach_campaigns_job ON outreach_campaigns(job_id);

-- ── outreach_messages ────────────────────────────────────────────────────
-- migrations/008_outreach_subject.py ADD COLUMN IF NOT EXISTS subject /
-- created_at against this table becomes a no-op once this baseline has
-- already created both columns.
CREATE TABLE IF NOT EXISTS outreach_messages (
    id              SERIAL PRIMARY KEY,
    candidate_id    INTEGER REFERENCES candidates(id) ON DELETE CASCADE,
    campaign_id     INTEGER REFERENCES outreach_campaigns(id) ON DELETE SET NULL,
    recipient_email VARCHAR(255),
    subject         VARCHAR(500),
    body            TEXT,
    channel         VARCHAR(20) DEFAULT 'email',
    status          VARCHAR(20) NOT NULL DEFAULT 'draft',
    opened_at       TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outreach_messages_candidate ON outreach_messages(candidate_id);
CREATE INDEX IF NOT EXISTS idx_outreach_messages_campaign ON outreach_messages(campaign_id);
CREATE INDEX IF NOT EXISTS idx_outreach_messages_status ON outreach_messages(status);

-- ── salary_benchmarks ────────────────────────────────────────────────────
-- Deliberately no unique index/constraint on the natural key here (code
-- review, WS-C.1 follow-up): this table already exists in production,
-- and migrations/009_salary_benchmarks_seed.py's bare `ON CONFLICT DO
-- NOTHING` has already been run there without one -- possibly more than
-- once -- so production may already hold duplicate rows on
-- (role_title, seniority, location). Adding a unique index here in 000
-- would fail outright on that duplicate data and abort every deploy.
-- migrations/015_salary_benchmarks_natural_key.py handles this properly:
-- it dedupes first, then creates the index, as two ordered top-level
-- statements running strictly after this table already exists.
CREATE TABLE IF NOT EXISTS salary_benchmarks (
    id              SERIAL PRIMARY KEY,
    role_title      VARCHAR(255) NOT NULL,
    seniority       VARCHAR(50),
    location        VARCHAR(255),
    currency        VARCHAR(10) DEFAULT 'EUR',
    p25             INTEGER,
    p50             INTEGER,
    p75             INTEGER,
    p90             INTEGER,
    sample_size     INTEGER,
    source          VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- No idx_salary_benchmarks_role here: migrations/006_drop_redundant_
-- indexes.py deliberately drops it as a duplicate of migrations/005's
-- idx_salary_benchmarks_role_title(role_title) -- creating it in 000
-- would just have 006 delete it again on every fresh deploy.

-- ── hiring_signals ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hiring_signals (
    id                  SERIAL PRIMARY KEY,
    company_name        VARCHAR(255),
    domain              VARCHAR(255),
    signal_type         VARCHAR(100),
    signal_text         TEXT,
    signal_date         DATE,
    confidence          NUMERIC(3,2) DEFAULT 0.5,
    source_url          TEXT,
    detected_by_agent   VARCHAR(100),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hiring_signals_company ON hiring_signals(company_name);
CREATE INDEX IF NOT EXISTS idx_hiring_signals_created ON hiring_signals(created_at DESC);

-- ── skill_gaps ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skill_gaps (
    id              SERIAL PRIMARY KEY,
    candidate_id    INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    gaps            JSONB,
    strengths       JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skill_gaps_candidate ON skill_gaps(candidate_id);

-- ── data_subject_requests ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS data_subject_requests (
    id                  SERIAL PRIMARY KEY,
    request_type        VARCHAR(50) NOT NULL,
    request_email       VARCHAR(255) NOT NULL,
    status              VARCHAR(50) NOT NULL DEFAULT 'pending',
    completed_at        TIMESTAMPTZ,
    response_summary    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_data_subject_requests_email ON data_subject_requests(request_email);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
