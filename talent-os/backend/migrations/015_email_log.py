"""
Talent OS — durable send log for the transactional mailer (services/mailer.py).

Every send attempt (SMTP or Gmail-API fallback) writes one row here, whether
it succeeds or fails — this is what makes "did the reset email actually go
out" answerable without grepping logs. Status starts 'queued' for symmetry
with a future async worker, but the synchronous mailer today writes
'sent'/'failed' directly.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "015_email_log"

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS email_log (
    id                     SERIAL PRIMARY KEY,
    to_email               TEXT NOT NULL,
    template               TEXT NOT NULL,
    subject                TEXT,
    provider               TEXT NOT NULL DEFAULT 'smtp',
    provider_message_id    TEXT,
    status                 TEXT NOT NULL DEFAULT 'queued'
                               CHECK (status IN ('queued', 'sent', 'failed', 'bounced', 'complained')),
    error                  TEXT,
    related_user_id        INT REFERENCES users(id) ON DELETE SET NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_email_log_to_email_created_at ON email_log(to_email, created_at DESC);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
