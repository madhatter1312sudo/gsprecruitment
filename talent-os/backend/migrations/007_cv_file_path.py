"""
Talent OS — Schema migration: add cv_file_path to candidate_profiles.

The CV upload endpoint writes candidate_profiles.cv_file_path, but the column
only ever existed on the candidates table — uploads failed in production with
UndefinedColumnError.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "007_cv_file_path"

MIGRATION_SQL = """
ALTER TABLE candidate_profiles ADD COLUMN IF NOT EXISTS cv_file_path VARCHAR(500);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
