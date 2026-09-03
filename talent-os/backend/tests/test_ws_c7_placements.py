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
from models.schemas import PlacementCreate, PlacementUpdate, PlacementStatusUpdate, OneOffCost
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
    def __init__(self, placement_row=None, candidate_exists=True, client_exists=True, job_row=(1, 1)):
        self.placement_row = placement_row
        # job_row = (job_id, job's client_id), or None if the job doesn't exist
        self.job_row = job_row
        self.candidate_exists = candidate_exists
        self.client_exists = client_exists
        self.statements = []

    async def fetch_one(self, sql, *args):
        self.statements.append((sql, args))
        if "INSERT INTO placements" in sql or "UPDATE placements SET" in sql or "FROM placements WHERE id" in sql:
            return self.placement_row
        if sql.strip().startswith("SELECT id FROM candidates WHERE"):
            return {"id": args[0]} if self.candidate_exists else None
        if sql.strip().startswith("SELECT id FROM clients WHERE"):
            return {"id": args[0]} if self.client_exists else None
        if sql.strip().startswith("SELECT id, client_id FROM job_orders WHERE"):
            if self.job_row is None:
                return None
            return {"id": self.job_row[0], "client_id": self.job_row[1]}
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


def test_create_placement_validates_candidate_exists(monkeypatch):
    import routers.placements as placements

    db = _FakeDB(placement_row=_row(), candidate_exists=False)
    monkeypatch.setattr(placements, "fetch_one", db.fetch_one)
    monkeypatch.setattr(placements, "fetch_all", db.fetch_all)
    monkeypatch.setattr(placements, "execute", db.execute)

    payload = PlacementCreate(candidate_id=999, job_id=1, client_id=1, placement_type="detachering")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(placements.create_placement(payload, current_user={"id": 5, "role": "admin"}))
    assert exc_info.value.status_code == 422
    assert "candidate_id" in exc_info.value.detail


def test_create_placement_validates_client_exists(monkeypatch):
    import routers.placements as placements

    db = _FakeDB(placement_row=_row(), client_exists=False)
    monkeypatch.setattr(placements, "fetch_one", db.fetch_one)
    monkeypatch.setattr(placements, "fetch_all", db.fetch_all)
    monkeypatch.setattr(placements, "execute", db.execute)

    payload = PlacementCreate(candidate_id=1, job_id=1, client_id=999, placement_type="detachering")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(placements.create_placement(payload, current_user={"id": 5, "role": "admin"}))
    assert exc_info.value.status_code == 422
    assert "client_id" in exc_info.value.detail


def test_create_placement_validates_job_exists(monkeypatch):
    import routers.placements as placements

    db = _FakeDB(placement_row=_row(), job_row=None)
    monkeypatch.setattr(placements, "fetch_one", db.fetch_one)
    monkeypatch.setattr(placements, "fetch_all", db.fetch_all)
    monkeypatch.setattr(placements, "execute", db.execute)

    payload = PlacementCreate(candidate_id=1, job_id=999, client_id=1, placement_type="detachering")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(placements.create_placement(payload, current_user={"id": 5, "role": "admin"}))
    assert exc_info.value.status_code == 422
    assert "job_id" in exc_info.value.detail


def test_create_placement_validates_job_belongs_to_client(monkeypatch):
    """job_id exists but is attached to a different client -- must be a
    422, not a bare 500 from the FK constraint at INSERT time."""
    import routers.placements as placements

    db = _FakeDB(placement_row=_row(), job_row=(1, 42))  # job's real client_id is 42
    monkeypatch.setattr(placements, "fetch_one", db.fetch_one)
    monkeypatch.setattr(placements, "fetch_all", db.fetch_all)
    monkeypatch.setattr(placements, "execute", db.execute)

    payload = PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="detachering")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(placements.create_placement(payload, current_user={"id": 5, "role": "admin"}))
    assert exc_info.value.status_code == 422
    assert "job_id" in exc_info.value.detail


def test_list_placements_total_is_a_real_count_not_page_length(monkeypatch):
    """total must reflect COUNT(*) over the whole filtered set, not just
    the length of the one page of rows returned -- these only coincide
    when the filtered set fits inside a single page."""
    import routers.placements as placements

    class _CountFakeDB(_FakeDB):
        async def fetch_val(self, sql, *args):
            self.statements.append((sql, args))
            return 137  # far more rows than the page below

        async def fetch_all(self, sql, *args):
            self.statements.append((sql, args))
            if "FROM placements WHERE" in sql:
                return [_row(id=1), _row(id=2)]
            return []

    db = _CountFakeDB()
    monkeypatch.setattr(placements, "fetch_one", db.fetch_one)
    monkeypatch.setattr(placements, "fetch_all", db.fetch_all)
    monkeypatch.setattr(placements, "fetch_val", db.fetch_val)
    monkeypatch.setattr(placements, "execute", db.execute)

    result = asyncio.run(placements.list_placements(
        status=None, candidate_id=None, job_id=None, client_id=None,
        limit=2, offset=0, current_user={"id": 5, "role": "admin"},
    ))
    assert result["total"] == 137
    assert len(result["items"]) == 2


# ── Money-field validation: NaN/inf/negative/over-precision -> 422 ────────

@pytest.mark.parametrize("field,bad_value", [
    ("hourly_bill_rate", "nan"),
    ("hourly_bill_rate", "inf"),
    ("hourly_bill_rate", "-1"),
    ("monthly_purchase_price", "nan"),
    ("monthly_purchase_price", "-5.00"),
    ("fee_amount", "Infinity"),
    ("fee_amount", "-0.01"),
])
def test_placement_create_rejects_bad_money_values(field, bad_value):
    kwargs = dict(candidate_id=1, job_id=1, client_id=1, placement_type="detachering")
    kwargs[field] = bad_value
    with pytest.raises(ValidationError):
        PlacementCreate(**kwargs)


def test_placement_create_rejects_money_value_over_the_column_cap():
    with pytest.raises(ValidationError):
        PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="detachering",
                         hourly_bill_rate="100000000.00")


def test_placement_create_accepts_money_value_at_the_column_cap():
    p = PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="detachering",
                         hourly_bill_rate="99999999.99")
    assert p.hourly_bill_rate == Decimal("99999999.99")


@pytest.mark.parametrize("bad_value", ["nan", "-1", "100.0001"])
def test_placement_create_rejects_bad_eor_cost_factor(bad_value):
    with pytest.raises(ValidationError):
        PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="detachering",
                         eor_cost_factor=bad_value)


def test_placement_create_accepts_eor_cost_factor_at_the_cap():
    p = PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="detachering",
                         eor_cost_factor="99.9999")
    assert p.eor_cost_factor == Decimal("99.9999")


@pytest.mark.parametrize("bad_value", ["nan", "-1", "100.01", "101"])
def test_placement_create_rejects_fee_percentage_over_100(bad_value):
    with pytest.raises(ValidationError):
        PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="werving_selectie",
                         fee_percentage=bad_value)


def test_placement_create_accepts_fee_percentage_at_100():
    p = PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="werving_selectie",
                         fee_percentage="100")
    assert p.fee_percentage == Decimal("100")


@pytest.mark.parametrize("bad_value", ["nan", "-1", "10000.00"])
def test_placement_create_rejects_bad_expected_billable_hours(bad_value):
    with pytest.raises(ValidationError):
        PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="detachering",
                         expected_billable_hours=bad_value)


def test_placement_create_accepts_expected_billable_hours_at_the_cap():
    p = PlacementCreate(candidate_id=1, job_id=1, client_id=1, placement_type="detachering",
                         expected_billable_hours="9999.99")
    assert p.expected_billable_hours == Decimal("9999.99")


# ── OneOffCost: extra="forbid" ─────────────────────────────────────────

def test_one_off_cost_accepts_label_and_amount():
    c = OneOffCost(label="Relocation", amount="1500.00")
    assert c.label == "Relocation"
    assert c.amount == Decimal("1500.00")


def test_one_off_cost_rejects_arbitrary_extra_keys():
    with pytest.raises(ValidationError):
        OneOffCost(label="Relocation", amount="1500.00", currency="EUR")


def test_one_off_cost_rejects_negative_amount():
    with pytest.raises(ValidationError):
        OneOffCost(label="Relocation", amount="-1")


def test_one_off_cost_rejects_nan_amount():
    with pytest.raises(ValidationError):
        OneOffCost(label="Relocation", amount="nan")


def test_one_off_cost_rejects_empty_label():
    with pytest.raises(ValidationError):
        OneOffCost(label="", amount="1")


def test_placement_create_rejects_one_off_cost_with_extra_key():
    with pytest.raises(ValidationError):
        PlacementCreate(
            candidate_id=1, job_id=1, client_id=1, placement_type="detachering",
            one_off_costs=[{"label": "Visa fee", "amount": "350.00", "vendor": "IND"}],
        )


def test_placement_create_accepts_valid_one_off_costs():
    p = PlacementCreate(
        candidate_id=1, job_id=1, client_id=1, placement_type="detachering",
        one_off_costs=[{"label": "Visa fee", "amount": "350.00"}],
    )
    assert p.one_off_costs == [OneOffCost(label="Visa fee", amount="350.00")]


# ── Every placements route requires admin (require_role dependency) ──────

def test_every_placements_route_requires_admin():
    import inspect
    import routers.placements as placements

    for route in placements.router.routes:
        params = inspect.signature(route.endpoint).parameters
        assert "current_user" in params, f"{route.path} has no current_user dependency"
        default = params["current_user"].default
        # Depends(require_role("admin")) -- inspect the wrapped dependency
        # callable's closure for the role tuple require_role() curries in.
        dep_callable = default.dependency
        closure_cells = dep_callable.__closure__ or ()
        role_args = [c.cell_contents for c in closure_cells if c.cell_contents == ("admin",)]
        assert role_args, (
            f"{route.path} current_user dependency is not require_role('admin') only: "
            f"closure contents were {[c.cell_contents for c in closure_cells]}"
        )


# ── GDPR self-export covers the five immigration columns ─────────────────

def test_self_export_candidate_query_is_select_star_so_it_carries_new_columns():
    """routers/gdpr.py's export_my_data() reads the candidate row with a
    bare `SELECT *`, not an explicit column list -- regression guard that
    this stays true, since an explicit list would silently drop the five
    WS-C.7 immigratiestatus columns (nationality, needs_work_permit,
    kennismigrant_status, ruling_30pct_status, ind_case_number) from a
    person's Art. 15/20 export without any test noticing."""
    import inspect
    import routers.gdpr as gdpr

    source = inspect.getsource(gdpr.export_my_data)
    assert 'SELECT * FROM candidates WHERE id = $1 AND deleted_at IS NULL' in source
    assert 'SELECT * FROM candidates WHERE LOWER(email) = LOWER($1) AND deleted_at IS NULL' in source
