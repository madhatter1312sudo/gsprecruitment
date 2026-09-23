"""
Talent OS -- issue #153 (Pool vacancies: English text twin, defect B of
issue #109). job_orders gains three nullable English-text columns:
description_en, requirements_en, nice_to_have_en, mirroring the existing
Dutch description/requirements/nice_to_have columns
(migrations/000_baseline.py / 016_job_orders_columns.py).

Decision recorded before this issue was written (product-owner,
22-09-2026): STANDARDS.md "Vacancy text" (lines 124-129) requires "Dutch
and English versions"; today all 27 pool vacancies
(data/pool_vacancies.json) carry Dutch text only. The model gains
nullable English fields so the standard can be met without blocking the
existing seed -- the columns default to NULL and no existing row is
touched by this migration. The English copy itself is a separate,
editor-owned follow-up (out of scope here); this migration only adds
somewhere for that text to live.

Nullable, no DEFAULT, no backfill, no CHECK constraint -- every existing
job_orders row (including the 27 pool vacancies and every other job
order already in production) gets description_en = requirements_en =
nice_to_have_en = NULL, which is exactly today's "no English text"
state made representable instead of implicit.

Pattern of 016/030/032/033/034/036/039/040 (see 040_email_log.py's
docstring): idempotent (ADD COLUMN IF NOT EXISTS), no DO $$ ... END $$
blocks (migrations/_runner.py splits on a literal ";"), no DELETE/DROP.
Reverts cleanly on a copy via:
    ALTER TABLE job_orders DROP COLUMN IF EXISTS description_en;
    ALTER TABLE job_orders DROP COLUMN IF EXISTS requirements_en;
    ALTER TABLE job_orders DROP COLUMN IF EXISTS nice_to_have_en;
(no other column or row is touched, so the revert is lossless for
everything except the English text itself, which is the whole point --
issue #153 is additive-only).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "046_job_orders_english_fields"

MIGRATION_SQL = """
ALTER TABLE job_orders ADD COLUMN IF NOT EXISTS description_en text;
ALTER TABLE job_orders ADD COLUMN IF NOT EXISTS requirements_en text;
ALTER TABLE job_orders ADD COLUMN IF NOT EXISTS nice_to_have_en text;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
