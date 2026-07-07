"""
Talent OS — Schema migration: add expiry to password reset tokens.

The reset email has always claimed the link is "valid for 1 hour" but
there was no expiry column at all, so tokens were valid indefinitely
until used or replaced.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "004_reset_token_expiry"

MIGRATION_SQL = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires_at TIMESTAMPTZ;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
