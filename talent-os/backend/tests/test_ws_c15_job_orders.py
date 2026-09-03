"""
Unit tests for WS-C.15 / WS-A.5 (job_orders: is_demo + public-facing
columns). Pure static/model checks -- no DB needed, matching
test_ws_c2_authz.py's style. See test_baseline_schema.py for the
migration-vs-code column self-consistency check that automatically picks
up migrations/016_job_orders_columns.py (it globs migrations/0*.py).
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from pydantic import ValidationError

from models.schemas import AdminJobUpdate
from routers.jobs import _public_job_row

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(BACKEND_ROOT, "migrations")


def _load_migration(fname):
    path = os.path.join(MIGRATIONS_DIR, fname)
    spec = importlib.util.spec_from_file_location(f"_migration_{fname}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, MIGRATIONS_DIR)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(MIGRATIONS_DIR)
    return mod


# ── Migration text ───────────────────────────────────────────────────────

def test_migration_016_adds_all_five_columns():
    mod = _load_migration("016_job_orders_columns.py")
    sql = mod.MIGRATION_SQL
    for col in (
        "is_demo boolean NOT NULL DEFAULT false",
        "city text",
        "company_display text",
        "employment_type text",
        "sponsorship_possible boolean NOT NULL DEFAULT false",
    ):
        assert col in sql, f"migration SQL missing: {col}"


def test_migration_016_columns_are_add_column_if_not_exists():
    """Idempotent (re-runnable), like every other migration here -- see
    migrations/_runner.py's docstring and 014/015's pattern."""
    mod = _load_migration("016_job_orders_columns.py")
    sql = mod.MIGRATION_SQL
    assert sql.count("ADD COLUMN IF NOT EXISTS") == 5


def test_migration_016_has_employment_type_check_constraint():
    mod = _load_migration("016_job_orders_columns.py")
    sql = mod.MIGRATION_SQL
    assert "CHECK (employment_type IS NULL OR employment_type IN ('vast', 'detachering', 'interim'))" in sql


def test_migration_016_backfills_is_demo_by_client_not_by_title():
    """Robust against seed job titles being edited later -- matches the 6
    migrations/012 seed jobs via the internal 'GSP Talent Pool' client,
    not a title/company string list."""
    mod = _load_migration("016_job_orders_columns.py")
    sql = mod.MIGRATION_SQL
    assert "UPDATE job_orders SET is_demo = true" in sql
    assert "GSP Talent Pool" in sql
    assert "gsprecruitment.nl" in sql


def test_migration_016_never_creates_a_unique_index():
    """Same rule test_baseline_schema.py enforces for 000_baseline.py --
    a unique index over data that might already violate it aborts the
    deploy outright (see migrations/015's docstring)."""
    mod = _load_migration("016_job_orders_columns.py")
    assert "CREATE UNIQUE INDEX" not in mod.MIGRATION_SQL.upper()


# ── Public projection ────────────────────────────────────────────────────

def test_public_job_row_defaults_null_company_display_to_confidential():
    row = {"id": 1, "title": "Senior Embedded C++ Engineer", "company_display": None}
    assert _public_job_row(row)["company_display"] == "confidential"


def test_public_job_row_keeps_a_real_company_display():
    row = {"id": 1, "title": "Senior Embedded C++ Engineer", "company_display": "Acme B.V."}
    assert _public_job_row(row)["company_display"] == "Acme B.V."


def test_public_job_row_does_not_mutate_the_input_row():
    row = {"id": 1, "company_display": None}
    _public_job_row(row)
    assert row["company_display"] is None


def test_public_job_columns_excludes_is_demo():
    """is_demo itself must never leak to the public API -- only used to
    filter the WHERE clause."""
    from routers.jobs import PUBLIC_JOB_COLUMNS
    cols = {c.strip() for c in PUBLIC_JOB_COLUMNS.split(",")}
    assert "is_demo" not in cols
    for expected in ("city", "company_display", "employment_type", "sponsorship_possible"):
        assert expected in cols


# ── AdminJobUpdate validation ────────────────────────────────────────────

def test_admin_job_update_accepts_the_new_fields():
    upd = AdminJobUpdate(
        city="Eindhoven",
        company_display="Acme B.V.",
        employment_type="detachering",
        sponsorship_possible=True,
    )
    assert upd.city == "Eindhoven"
    assert upd.company_display == "Acme B.V."
    assert upd.employment_type == "detachering"
    assert upd.sponsorship_possible is True


@pytest.mark.parametrize("value", ["vast", "detachering", "interim"])
def test_admin_job_update_accepts_each_allowed_employment_type(value):
    assert AdminJobUpdate(employment_type=value).employment_type == value


def test_admin_job_update_rejects_invalid_employment_type():
    with pytest.raises(ValidationError):
        AdminJobUpdate(employment_type="freelance")


def test_admin_job_update_employment_type_defaults_to_none():
    assert AdminJobUpdate().employment_type is None
