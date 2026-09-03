"""
Talent OS — WS-C.7 margin calculation. PROVISIONAL.

Pure function, no DB/network: compute_margin() takes a placement (a dict
or anything dict-like — an asyncpg Row-derived dict or a plain test
fixture both work via .get()) plus the two inputs that are not columns on
`placements` (migrations/029_placements.py) — a gross monthly salary
(detachering cost side, when monthly_purchase_price isn't given directly)
and an annual salary (werving_selectie fee-percentage base) — and returns
every input alongside the derived revenue/cost/margin/fee numbers.

Every result carries `"provisional": True`. The pricing/margin factors
this module implements (eor_cost_factor, fee_percentage, etc.) are owner
decisions that have not been finalised — this is a calculation aid for
routers/placements.py's GET /{id}/margin, not a number anyone should
treat as final without an owner sign-off. Nothing here is published to
the public site or the client portal.

Two formulas, per WS-C.7:

  detachering (secondment):
    revenue = hourly_bill_rate × expected_billable_hours   (billing_basis
      'per_uur' — the only revenue formula this schema's columns support;
      'vast_maandbedrag' has no separate fixed-monthly-bill column of its
      own, so hourly_bill_rate is read as the flat monthly bill amount in
      that case instead, and expected_billable_hours is not used for
      revenue.)
    cost = monthly_purchase_price if given, else
      gross_monthly_salary × eor_cost_factor
    margin = revenue − cost
    margin_pct = margin / revenue × 100 (None if revenue is falsy/None)

  werving_selectie (W&S, one-off placement fee):
    fee = fee_amount if fee_type == 'vast', else
      fee_percentage / 100 × annual_salary if fee_type == 'percentage'
    (fee is both "revenue" and "margin" here — this minimal schema tracks
    no W&S cost line item of its own.)

All arithmetic is done in Decimal to avoid float rounding drift, and
every returned number is rounded to 2 decimal places (ROUND_HALF_UP) and
converted to float for JSON-friendliness in the API response.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional


def _dec(value: Any) -> Optional[Decimal]:
    """Coerce a placement field / caller input to Decimal, or None if it
    isn't set. Accepts Decimal, int, float, numeric strings; raises
    ValueError on anything else so a bad input fails loudly rather than
    silently producing a wrong margin."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"cannot convert {value!r} to a Decimal") from exc


def _round2(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute_margin(
    placement: Any,
    gross_monthly_salary: Any = None,
    annual_salary: Any = None,
) -> dict:
    """Return a provisional margin breakdown for one placement.

    `placement` supplies: placement_type, billing_basis, hourly_bill_rate,
    expected_billable_hours, monthly_purchase_price, eor_cost_factor,
    fee_type, fee_percentage, fee_amount. `gross_monthly_salary` and
    `annual_salary` are not placement columns — pass them in explicitly
    (routers/placements.py resolves them from the linked job/candidate
    record before calling this)."""
    def get(key: str) -> Any:
        if isinstance(placement, dict):
            return placement.get(key)
        return getattr(placement, key, None)

    placement_type = get("placement_type")
    billing_basis = get("billing_basis")

    hourly_bill_rate = _dec(get("hourly_bill_rate"))
    expected_billable_hours = _dec(get("expected_billable_hours"))
    monthly_purchase_price = _dec(get("monthly_purchase_price"))
    eor_cost_factor = _dec(get("eor_cost_factor"))
    gross = _dec(gross_monthly_salary)
    annual = _dec(annual_salary)
    fee_type = get("fee_type")
    fee_percentage = _dec(get("fee_percentage"))
    fee_amount = _dec(get("fee_amount"))

    result: dict = {
        "provisional": True,
        "placement_type": placement_type,
        "inputs": {
            "billing_basis": billing_basis,
            "hourly_bill_rate": _round2(hourly_bill_rate),
            "expected_billable_hours": _round2(expected_billable_hours),
            "monthly_purchase_price": _round2(monthly_purchase_price),
            "eor_cost_factor": _round2(eor_cost_factor),
            "gross_monthly_salary": _round2(gross),
            "annual_salary": _round2(annual),
            "fee_type": fee_type,
            "fee_percentage": _round2(fee_percentage),
            "fee_amount": _round2(fee_amount),
        },
        "revenue": None,
        "cost": None,
        "margin": None,
        "margin_pct": None,
        "fee": None,
    }

    if placement_type == "detachering":
        revenue = None
        if billing_basis == "per_uur":
            if hourly_bill_rate is not None and expected_billable_hours is not None:
                revenue = hourly_bill_rate * expected_billable_hours
        else:
            # vast_maandbedrag (or unset): no dedicated fixed-monthly-bill
            # column exists on placements -- hourly_bill_rate stands in as
            # the flat monthly amount. See module docstring.
            revenue = hourly_bill_rate

        cost = monthly_purchase_price
        if cost is None and gross is not None and eor_cost_factor is not None:
            cost = gross * eor_cost_factor

        margin = None
        margin_pct = None
        if revenue is not None and cost is not None:
            margin = revenue - cost
            if revenue != 0:
                margin_pct = (margin / revenue) * Decimal(100)

        result["revenue"] = _round2(revenue)
        result["cost"] = _round2(cost)
        result["margin"] = _round2(margin)
        result["margin_pct"] = _round2(margin_pct)

    elif placement_type == "werving_selectie":
        fee = None
        if fee_type == "vast":
            fee = fee_amount
        elif fee_type == "percentage" and fee_percentage is not None and annual is not None:
            fee = (fee_percentage / Decimal(100)) * annual

        result["fee"] = _round2(fee)
        # No separate W&S cost line item in this minimal schema -- the fee
        # itself is both the revenue and the margin.
        result["revenue"] = _round2(fee)
        result["margin"] = _round2(fee)

    return result
