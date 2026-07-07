"""
Talent OS — Schema migration: missing indexes found by performance audit.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "005_performance_indexes"

MIGRATION_SQL = """
CREATE INDEX IF NOT EXISTS idx_job_orders_client_id ON job_orders(client_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_matches_candidate_status ON matches(candidate_id, status);
CREATE INDEX IF NOT EXISTS idx_salary_benchmarks_role_title ON salary_benchmarks(role_title);
CREATE INDEX IF NOT EXISTS idx_outreach_messages_campaign_id ON outreach_messages(campaign_id);
CREATE INDEX IF NOT EXISTS idx_job_orders_created_at ON job_orders(created_at);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
