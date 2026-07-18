"""
Talent OS — Schema migration: outreach_drafts table for the automated
sourcing + AI outreach draft pipeline.

Drafts are always human-approved before sending — nothing here auto-sends.
Also seeds the system_settings feature flags the scheduler jobs check.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "010_outreach_drafts"

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS outreach_drafts (
    id              SERIAL PRIMARY KEY,
    target_type     VARCHAR(20) NOT NULL,
    target_id       INTEGER,
    target_email    VARCHAR(255),
    target_name     VARCHAR(255),
    company         VARCHAR(255),
    job_id          INTEGER,
    channel         VARCHAR(20) DEFAULT 'email',
    language        VARCHAR(5) DEFAULT 'nl',
    subject         VARCHAR(500),
    body            TEXT,
    ai_model        VARCHAR(100),
    status          VARCHAR(20) DEFAULT 'draft',
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    sent_at         TIMESTAMP,
    approved_by     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_outreach_drafts_status ON outreach_drafts(status);

INSERT INTO system_settings (key, value) VALUES
    ('apollo_sync_enabled', 'true'),
    ('outreach_drafting_enabled', 'true')
ON CONFLICT (key) DO NOTHING;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
