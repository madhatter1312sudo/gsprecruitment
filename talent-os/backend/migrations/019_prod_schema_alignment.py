"""
Talent OS — align production schema with what migrations 000-016 expect,
and vice versa (WS-C.1 follow-up, "align migrations with the real
production schema").

Compared production's `pg_dump --schema-only` against a fresh 000-016
chain (diff.md, 2026-09-03). Two kinds of drift, both handled here:

1. Columns migrations define that production is missing (migrations-only
   in diff.md): job_orders.updated_at, matches.updated_at,
   outreach_messages.body/channel/recipient_email,
   salary_benchmarks.created_at. Added with the exact types/defaults
   000_baseline.py uses, via ADD COLUMN IF NOT EXISTS.

2. Columns/tables production has that migrations never created
   (prod-only in diff.md): repeated here as ADD COLUMN IF NOT EXISTS /
   CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS, matching what
   000_baseline.py now also creates for brand-new environments (see that
   file's history for the same changes with per-table commentary). Doing
   it again here is what makes an environment created from the *old*
   000_baseline.py (before this change) converge too, once it runs this
   migration: both a fresh DB and an already-deployed one end up with the
   same column/table/index sets. All idempotent, no unique indexes, no
   assumptions about existing row data other than the one backfill below.

outreach_messages.body vs prod's message_text: routers/outreach.py reads
and writes `body` exclusively (create_draft's INSERT, update_draft's
SELECT/UPDATE, and the sender's INSERT INTO outreach_messages(...,
body, ...) at line ~196) -- it never touches `message_text`. Production
rows written before this alignment may have their content in
`message_text` only (prod's column was NOT NULL, so every prod row has
one) with body left NULL going forward. This migration backfills body
from message_text once, without overwriting anything the app already
wrote to body:

    UPDATE outreach_messages SET body = message_text
    WHERE body IS NULL AND message_text IS NOT NULL;

Idempotent (a second run finds no more body IS NULL rows to touch) and
purely additive -- it never clears or overwrites message_text.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "019_prod_schema_alignment"

MIGRATION_SQL = """
-- ── 1. migrations-only columns production is missing ────────────────────
ALTER TABLE job_orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS body TEXT;
ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS channel VARCHAR(20) DEFAULT 'email';
ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS recipient_email VARCHAR(255);
ALTER TABLE salary_benchmarks ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- One-time backfill: routers/outreach.py only ever reads/writes `body`,
-- never `message_text` -- see module docstring.
UPDATE outreach_messages SET body = message_text WHERE body IS NULL AND message_text IS NOT NULL;

-- ── 2. prod-only columns/tables migrations never created (converges an
--      environment built from the OLD 000_baseline.py too) ─────────────
ALTER TABLE clients ADD COLUMN IF NOT EXISTS funding_stage VARCHAR(50);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS apollo_employee_count INTEGER;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS apollo_funding_stage VARCHAR(50);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS apollo_technologies TEXT[] DEFAULT '{}';
ALTER TABLE clients ADD COLUMN IF NOT EXISTS apollo_industry VARCHAR(100);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS hiring_intent_score NUMERIC(3,2) DEFAULT 0;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS last_hiring_intent_check TIMESTAMPTZ;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS assigned_agent_profile VARCHAR(100);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS consent_granted_at TIMESTAMPTZ;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS consent_withdrawn_at TIMESTAMPTZ;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS data_retention_until TIMESTAMPTZ;

ALTER TABLE candidates ADD COLUMN IF NOT EXISTS company_employee_count INTEGER;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS company_funding_stage VARCHAR(50);
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS company_technologies TEXT[] DEFAULT '{}';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS consent_granted_at TIMESTAMPTZ;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS data_retention_until TIMESTAMPTZ;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS salary_currency VARCHAR(10) DEFAULT 'EUR';
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS cv_search TSVECTOR GENERATED ALWAYS AS (to_tsvector('dutch', COALESCE(cv_text, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_candidates_company ON candidates(current_company);
CREATE INDEX IF NOT EXISTS idx_candidates_cv_search ON candidates USING gin(cv_search);
CREATE INDEX IF NOT EXISTS idx_candidates_skills ON candidates USING gin(skills);
CREATE INDEX IF NOT EXISTS idx_candidates_email ON candidates(email);

ALTER TABLE job_orders ADD COLUMN IF NOT EXISTS filled_candidate_id INTEGER;

ALTER TABLE matches ADD COLUMN IF NOT EXISTS candidate_interest_score NUMERIC(3,1);
ALTER TABLE matches ADD COLUMN IF NOT EXISTS retention_risk_score NUMERIC(3,1);

ALTER TABLE outreach_campaigns ADD COLUMN IF NOT EXISTS channel VARCHAR(50);
ALTER TABLE outreach_campaigns ADD COLUMN IF NOT EXISTS created_by_agent VARCHAR(100);
ALTER TABLE outreach_campaigns ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE outreach_campaigns ADD COLUMN IF NOT EXISTS template_id INTEGER;
ALTER TABLE outreach_campaigns ADD COLUMN IF NOT EXISTS total_converted INTEGER DEFAULT 0;
ALTER TABLE outreach_campaigns ADD COLUMN IF NOT EXISTS total_opened INTEGER DEFAULT 0;
ALTER TABLE outreach_campaigns ADD COLUMN IF NOT EXISTS total_replied INTEGER DEFAULT 0;
ALTER TABLE outreach_campaigns ADD COLUMN IF NOT EXISTS total_sent INTEGER DEFAULT 0;

ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS message_text TEXT;
ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS personalization_notes TEXT;
ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS replied_at TIMESTAMPTZ;
ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS reply_text TEXT;
ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS sentiment_score NUMERIC(3,2);
ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS written_by_agent VARCHAR(100);
ALTER TABLE outreach_messages ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

ALTER TABLE salary_benchmarks ADD COLUMN IF NOT EXISTS last_updated TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE skill_gaps ADD COLUMN IF NOT EXISTS target_role VARCHAR(255);
ALTER TABLE skill_gaps ADD COLUMN IF NOT EXISTS upskill_recommendations TEXT[] DEFAULT '{}';
ALTER TABLE skill_gaps ADD COLUMN IF NOT EXISTS estimated_time_to_fill_months NUMERIC(3,1);
ALTER TABLE skill_gaps ADD COLUMN IF NOT EXISTS analyzed_by_agent VARCHAR(100);

ALTER TABLE data_subject_requests ADD COLUMN IF NOT EXISTS request_data JSONB;

CREATE TABLE IF NOT EXISTS consent_records (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER,
    visitor_id          VARCHAR(255),
    consent_type        VARCHAR(50) NOT NULL,
    granted             BOOLEAN NOT NULL DEFAULT TRUE,
    ip_address          VARCHAR(45),
    user_agent          TEXT,
    consent_version     VARCHAR(20),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_consent_records_created ON consent_records(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_consent_records_type ON consent_records(consent_type);
CREATE INDEX IF NOT EXISTS idx_consent_records_user ON consent_records(user_id);
CREATE INDEX IF NOT EXISTS idx_consent_records_visitor ON consent_records(visitor_id);

CREATE TABLE IF NOT EXISTS model_feedback (
    id                  SERIAL PRIMARY KEY,
    prediction_id       UUID,
    model_name          VARCHAR(100),
    model_version       VARCHAR(50),
    predicted_score     NUMERIC(5,2),
    outreach_sent       BOOLEAN DEFAULT FALSE,
    candidate_replied   BOOLEAN DEFAULT FALSE,
    interview_occurred  BOOLEAN DEFAULT FALSE,
    offer_made          BOOLEAN DEFAULT FALSE,
    candidate_accepted  BOOLEAN DEFAULT FALSE,
    retained_6months    BOOLEAN DEFAULT FALSE,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS privacy_notice_acceptance (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER,
    visitor_id          VARCHAR(255),
    notice_version      VARCHAR(20) NOT NULL,
    accepted            BOOLEAN NOT NULL DEFAULT TRUE,
    accepted_at         TIMESTAMPTZ DEFAULT NOW(),
    ip_address          VARCHAR(45),
    user_agent          TEXT
);

CREATE INDEX IF NOT EXISTS idx_privacy_notice_user ON privacy_notice_acceptance(user_id);
CREATE INDEX IF NOT EXISTS idx_privacy_notice_version ON privacy_notice_acceptance(notice_version);
CREATE INDEX IF NOT EXISTS idx_privacy_notice_visitor ON privacy_notice_acceptance(visitor_id);

CREATE TABLE IF NOT EXISTS referral_graph (
    id                  SERIAL PRIMARY KEY,
    person_a            VARCHAR(255) NOT NULL,
    person_b            VARCHAR(255) NOT NULL,
    connection_type     VARCHAR(50),
    strength            NUMERIC(3,2),
    source_evidence     TEXT,
    detected_by_agent   VARCHAR(100),
    deleted_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_referral_person_a ON referral_graph(person_a);
CREATE INDEX IF NOT EXISTS idx_referral_person_b ON referral_graph(person_b);
CREATE INDEX IF NOT EXISTS idx_referral_type ON referral_graph(connection_type);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
