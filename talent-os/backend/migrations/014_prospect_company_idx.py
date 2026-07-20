"""
Talent OS — index client_prospects.company_name.

_enrich_top_prospects orders by a per-company COUNT(*) correlated subquery;
without this index that scan is O(n^2)-ish as the prospects table grows.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "014_prospect_company_idx"

MIGRATION_SQL = """
CREATE INDEX IF NOT EXISTS idx_client_prospects_company ON client_prospects(company_name);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
