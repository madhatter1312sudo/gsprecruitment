"""
Unit tests for WS-C.7 (placements, minimal, + immigratiestatus).
PROVISIONAL -- see core/margin.py and migrations/029_placements.py.

Pure static/model checks + a monkeypatched-DB router test, no live
Postgres needed -- same style as tests/test_ws_c4_c5_c10_crm.py and
tests/test_baseline_schema.py. See tests/test_baseline_schema.py itself
for the migration-vs-code column self-consistency check, which
automatically picks up migrations/029_placements.py (it globs
migrations/0*.py) and would fail if routers/placements.py's literal
INSERT INTO placements (...) column list ever drifted from the migration.
"""
import asyncio
import importlib.util
import os
import sys
from decimal import Decimal, ROUND_HALF_UP

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from pydantic import ValidationError

from core.margin import compute_margin
from models.schemas import PlacementCreate, PlacementUpdate, PlacementStatusUpdate
from routers.placements import validate_status_transition
from fastapi import HTTPException

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(BACKEND_ROOT, "migrations")


def _load_migration_sql(fname: str) -> str:
    path = os.path.join(MIGRATIONS_DIR, fname)
    spec = importlib.util.spec_from_file_location(f"_migration_{fname}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, MIGRATIONS_DIR)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(MIGRATIONS_DIR)
    return mod.MIGRATION_SQL


# ── core/margin.py: the two WS-C.7 plan test vectors ──────────────────────
#
# (a) gross EUR 5,400/month, eor_cost_factor 1.575 -> purchase price
#     5400 * 1.575 = 8505.00 exactly. bill EUR 80/h * 147.33h = 11786.40.
#     margin = 11786.40 - 8505.00 = 3281.40.
# (b) same factor/hours, gross EUR 5,942 -> purchase price
#     5942 * 1.575 = 9358.65 exactly. margin = 11786.40 - 9358.65 = 2427.75
#     (the masterplan's "~EUR 2,428" is a rounded approximation of this
#     exact formula result -- this test asserts the precise value, not the
#     rounded-to-euro approximation).

def _expected_purchase_price(gross: str, factor: str) -> float:
    return float(
        (Decimal(gross) * Decimal(factor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def _expected_revenue(rate: str, hours: str) -> float:
    return float(
        (Decimal(rate) * Decimal(hours)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def _detachering_placement():
    return {
        "placement_type": "detachering",
        "billing_basis": "per_uur",
        "hourly_bill_rate": "80",
        "expected_billable_hours": "147.33",
        "eor_cost_factor": "1.575",
    }


def test_margin_vector_a_gross_5400():
    result = compute_margin(_detachering_placement(), gross_monthly_salary="5400")
    assert result["provisional"] is True
    expected_cost = _expected_purchase_price("5400", "1.575")
    expected_revenue = _expected_revenue("80", "147.33")
    expected_margin = round(expected_revenue - expected_cost, 2)
    assert result["cost"] == expected_cost == 8505.0
    assert result["revenue"] == expected_revenue
    assert result["margin"] == expected_margin == 3281.4


def test_margin_vector_b_gross_5942():
    result = compute_margin(_detachering_placement(), gross_monthly_salary="5942")
    expected_cost = _expected_purchase_price("5942", "1.575")
    expected_revenue = _expected_revenue("80", "147.33")
    expected_margin = round(expected_revenue - expected_cost, 2)
    assert result["cost"] == expected_cost == 9358.65
    assert result["revenue"] == expected_revenue
    assert result["margin"] == expected_margin == 2427.75


def test_margin_uses_monthly_purchase_price_directly_when_given():
    """monthly_purchase_price, when set, wins over gross * eor_cost_factor
    -- the parenthetical fallback in the WS-C.7 spec only applies when
    monthly_purchase_price is absent."""
    placement = dict(_detachering_placement())
    placement["monthly_purchase_price"] = "9999.99"
    result = compute_margin(placement, gross_monthly_salary="5400")
    assert result["cost"] == 9999.99


def test_margin_werving_selectie_fee_type_vast():
    result = compute_margin({"placement_type": "werving_selectie", "fee_type": "vast", "fee_amount": "9500.00"})
    assert result["fee"] == 9500.0
    assert result["provisional"] is True


def test_margin_werving_selectie_fee_type_percentage():
    result = compute_margin(
        {"placement_type": "werving_selectie", "fee_type": "percentage", "fee_percentage": "20"},
        annual_salary="65000",
    )
    assert result["fee"] == 13000.0  # 20% of 65000


def test_margin_returns_provisional_flag_always():
    assert compute_margin({"placement_type": "detachering"})["provisional"] is True
    assert compute_margin({"placement_type": "werving_selectie"})["provisional"] is True


def test_margin_missing_inputs_yield_none_not_a_crash():
    result = compute_margin({"placement_type": "detachering", "billing_basis": "per_uur"})
    assert result["revenue"] is None
    assert result["margin"] is None


# ── Status transitions ─────────────────────────────────────────────────

def test_valid_transitions_pass():
    validate_status_transition("concept", "actief")
    validate_status_transition("actief", "beeindigd")
    validate_status_transition("concept", "geannuleerd")
    validate_status_transition("actief", "geannuleerd")


@pytest.mark.parametrize("frm,to", [
    ("concept", "beeindigd"),      # must go through actief
    ("beeindigd", "actief"),       # terminal
    ("geannuleerd", "actief"),     # terminal
    ("actief", "concept"),         # no going backwards
    ("concept", "concept"),        # no-op not allowed
    ("beeindigd", "geannuleerd"),  # terminal
])
def test_invalid_transitions_raise_422(frm, to):
    with pytest.raises(HTTPException) as exc_info:
        validate_status_transition(frm, to)
    assert exc_info.value.status_code == 422


# ── Pydantic models: CHECK-matching patterns ──────────────────────────────

def test_placement_create_accepts_each_placement_type():
    for pt in ("werving_selectie", "detachering"):
        p = PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type=pt)
        assert p.placement_type == pt


def test_placement_create_rejects_bad_placement_type():
    with pytest.raises(ValidationError):
        PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="freelance")


def test_placement_create_accepts_each_billing_basis():
    for basis in ("vast_maandbedrag", "per_uur"):
        p = PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="detachering", billing_basis=basis)
        assert p.billing_basis == basis


def test_placement_create_rejects_bad_billing_basis():
    with pytest.raises(ValidationError):
        PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="detachering", billing_basis="weekly")


def test_placement_create_accepts_each_fee_type():
    for ft in ("percentage", "vast"):
        p = PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="werving_selectie", fee_type=ft)
        assert p.fee_type == ft


def test_placement_create_rejects_bad_fee_type():
    with pytest.raises(ValidationError):
        PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="werving_selectie", fee_type="fixed")


def test_placement_create_defaults_to_concept_status():
    p = PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="detachering")
    assert p.status == "concept"


def test_placement_create_rejects_bad_status():
    with pytest.raises(ValidationError):
        PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="detachering", status="live")


def test_placement_status_update_accepts_each_allowed_status():
    for s in ("concept", "actief", "beeindigd", "geannuleerd"):
        assert PlacementStatusUpdate(status=s).status == s


def test_placement_status_update_rejects_bad_status():
    with pytest.raises(ValidationError):
        PlacementStatusUpdate(status="cancelled")


# ── Migration text: 029_placements.py ──────────────────────────────────

def test_placements_migration_is_idempotent_style():
    sql = _load_migration_sql("029_placements.py")
    assert "CREATE TABLE IF NOT EXISTS placements" in sql
    assert "ADD COLUMN IF NOT EXISTS" in sql
    assert "CREATE INDEX IF NOT EXISTS" in sql


def test_placements_migration_creates_no_unique_index():
    sql = _load_migration_sql("029_placements.py")
    assert "CREATE UNIQUE INDEX" not in sql.upper()


def test_placements_migration_check_sets():
    sql = _load_migration_sql("029_placements.py")
    assert "IN ('werving_selectie','detachering')" in sql
    assert "IN ('vast_maandbedrag','per_uur')" in sql
    assert "IN ('percentage','vast')" in sql
    assert "IN ('concept','actief','beeindigd','geannuleerd')" in sql
    assert "IN ('nvt','aangevraagd','toegekend','afgewezen')" in sql


def test_placements_migration_adds_five_immigration_columns_to_candidates():
    sql = _load_migration_sql("029_placements.py")
    for col in ("nationality", "needs_work_permit", "kennismigrant_status",
                "ruling_30pct_status", "ind_case_number"):
        assert f"ALTER TABLE candidates ADD COLUMN IF NOT EXISTS {col}" in sql


def test_placements_migration_declares_the_three_fks():
    sql = _load_migration_sql("029_placements.py")
    assert "REFERENCES candidates(id)" in sql
    assert "REFERENCES job_orders(id)" in sql
    assert "REFERENCES clients(id)" in sql


def test_placements_migration_one_off_costs_defaults_to_empty_jsonb_array():
    sql = _load_migration_sql("029_placements.py")
    assert "one_off_costs" in sql
    assert "JSONB NOT NULL DEFAULT '[]'" in sql


# ── Router: audit_log + one_off_costs jsonb coercion ──────────────────────

class _FakeDB:
    def __init__(self, placement_row=None):
        self.placement_row = placement_row
        self.statements = []

    async def fetch_one(self, sql, *args):
        self.statements.append((sql, args))
        if "INSERT INTO placements" in sql or "UPDATE placements SET" in sql or "FROM placements WHERE id" in sql:
            return self.placement_row
        return None

    async def fetch_all(self, sql, *args):
        self.statements.append((sql, args))
        return []

    async def execute(self, sql, *args):
        self.statements.append((sql, args))
        return "OK"


def _row(**overrides):
    base = {
        "id": 1, "candidate_id": 1, "job_id": 1, "client_id": 1,
        "placement_type": "detachering", "status": "concept",
        "one_off_costs": None, "created_by": 5, "created_at": "2026-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_create_placement_writes_json_serialized_audit_log(monkeypatch):
    import routers.placements as placements
    import json

    db = _FakeDB(placement_row=_row())
    monkeypatch.setattr(placements, "fetch_one", db.fetch_one)
    monkeypatch.setattr(placements, "fetch_all", db.fetch_all)
    monkeypatch.setattr(placements, "execute", db.execute)

    payload = PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="detachering")
    result = asyncio.run(placements.create_placement(payload, current_user={"id": 5, "role": "admin"}))

    # one_off_costs NULL from the DB must come back coerced to []
    assert result["one_off_costs"] == []

    audit_calls = [args for sql, args in db.statements if sql.strip().startswith("INSERT INTO audit_log")]
    assert audit_calls, "expected an audit_log insert"
    changes_arg = audit_calls[0][-1]
    assert isinstance(changes_arg, str)  # json.dumps()'d, never a raw dict (commit 72b4bcd)
    json.loads(changes_arg)  # must round-trip


def test_status_change_endpoint_rejects_invalid_transition(monkeypatch):
    import routers.placements as placements

    db = _FakeDB(placement_row=_row(status="concept"))
    monkeypatch.setattr(placements, "fetch_one", db.fetch_one)
    monkeypatch.setattr(placements, "fetch_all", db.fetch_all)
    monkeypatch.setattr(placements, "execute", db.execute)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(placements.update_placement_status(
            1, PlacementStatusUpdate(status="beeindigd"), current_user={"id": 5, "role": "admin"},
        ))
    assert exc_info.value.status_code == 422
