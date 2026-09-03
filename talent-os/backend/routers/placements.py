"""
Talent OS — Placements (WS-C.7, minimal). PROVISIONAL.

Admin-only (Bearer admin JWT) CRUD over `placements`
(migrations/029_placements.py) plus GET /{id}/margin, a thin wrapper
around core/margin.py's compute_margin(). Every margin figure this
returns is provisional -- the pricing/margin factors (eor_cost_factor,
fee_percentage, etc.) are owner decisions not yet finalised. No
client-portal router exists for placements in this PR -- nothing here is
exposed to clients or the public site.

Status transitions are validated against a fixed graph before any write:
  concept -> actief -> beeindigd
  concept -> geannuleerd
  actief  -> geannuleerd
Any other transition (including no-op same-status "changes" and leaving
a terminal state) is rejected with 422. Every create/update/status-change/
soft-delete writes to audit_log, JSON-serialized (json.dumps + ::jsonb --
see commit 72b4bcd on why a raw dict crashes it).
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.database import fetch_one, fetch_all, execute
from core.deps import require_role
from core.margin import compute_margin
from models.schemas import PlacementCreate, PlacementUpdate, PlacementStatusUpdate

logger = logging.getLogger("talent_os.placements")

router = APIRouter(prefix="/api/v1/admin/placements", tags=["placements-admin"])

# Allowed status transitions (WS-C.7 spec): concept -> actief -> beeindigd,
# and geannuleerd reachable from concept or actief. No other edge exists --
# beeindigd/geannuleerd are terminal, and concept cannot jump straight to
# beeindigd.
_ALLOWED_TRANSITIONS = {
    "concept": {"actief", "geannuleerd"},
    "actief": {"beeindigd", "geannuleerd"},
    "beeindigd": set(),
    "geannuleerd": set(),
}


def validate_status_transition(from_status: str, to_status: str) -> None:
    """Raise HTTPException(422) unless from_status -> to_status is an
    allowed edge in _ALLOWED_TRANSITIONS. A pure function (no DB) so it's
    unit-testable directly."""
    allowed = _ALLOWED_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid status transition: {from_status} -> {to_status}. "
                f"Allowed from {from_status}: {sorted(allowed) or 'none (terminal)'}"
            ),
        )


def _coerce_one_off_costs(row: dict) -> dict:
    """asyncpg has no jsonb codec registered on this connection, so
    placements.one_off_costs (jsonb) comes back as a JSON string, and a
    NULL value must read back as [] (never null) same as every other
    array-shaped column in this codebase."""
    val = row.get("one_off_costs")
    if val is None:
        row["one_off_costs"] = []
    elif isinstance(val, str):
        row["one_off_costs"] = json.loads(val)
    return row


async def _audit(action: str, actor_id: int, target_id: Optional[int], changes: dict) -> None:
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        action, actor_id, "placement", target_id, json.dumps(changes),
    )


async def _get_placement_or_404(placement_id: int) -> dict:
    row = await fetch_one(
        "SELECT * FROM placements WHERE id = $1 AND deleted_at IS NULL",
        placement_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Placement not found")
    return _coerce_one_off_costs(row)


# ── CRUD ───────────────────────────────────────────────────────────────

@router.get("")
async def list_placements(
    status: Optional[str] = Query(None),
    candidate_id: Optional[int] = Query(None),
    job_id: Optional[int] = Query(None),
    client_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_role("admin")),
):
    conditions = ["deleted_at IS NULL"]
    args = []
    for col, val in (("status", status), ("candidate_id", candidate_id),
                      ("job_id", job_id), ("client_id", client_id)):
        if val is not None:
            args.append(val)
            conditions.append(f"{col} = ${len(args)}")
    args.extend([limit, offset])
    rows = await fetch_all(
        f"""SELECT * FROM placements WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC LIMIT ${len(args) - 1} OFFSET ${len(args)}""",
        *args,
    )
    return {"items": [_coerce_one_off_costs(r) for r in rows], "total": len(rows)}


@router.get("/{placement_id}")
async def get_placement(
    placement_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    return await _get_placement_or_404(placement_id)


@router.post("", status_code=201)
async def create_placement(
    payload: PlacementCreate,
    current_user: dict = Depends(require_role("admin")),
):
    row = await fetch_one(
        """INSERT INTO placements
           (candidate_id, job_id, client_id, placement_type, start_date, end_date,
            hourly_bill_rate, monthly_purchase_price, eor_partner, eor_cost_factor,
            billing_basis, expected_billable_hours, fee_type, fee_percentage,
            fee_amount, one_off_costs, status, notes, created_by)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                   $15, $16::jsonb, $17, $18, $19)
           RETURNING *""",
        payload.candidate_id, payload.job_id, payload.client_id, payload.placement_type,
        payload.start_date, payload.end_date, payload.hourly_bill_rate,
        payload.monthly_purchase_price, payload.eor_partner, payload.eor_cost_factor,
        payload.billing_basis, payload.expected_billable_hours, payload.fee_type,
        payload.fee_percentage, payload.fee_amount, json.dumps(payload.one_off_costs),
        payload.status, payload.notes, current_user["id"],
    )

    await _audit("placement_create", current_user["id"], row["id"], payload.model_dump(mode="json"))
    return _coerce_one_off_costs(row)


@router.patch("/{placement_id}")
async def update_placement(
    placement_id: int,
    updates: PlacementUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    await _get_placement_or_404(placement_id)

    update_dict = updates.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "one_off_costs" in update_dict:
        update_dict["one_off_costs"] = json.dumps(update_dict["one_off_costs"])

    set_parts = []
    values = []
    idx = 1
    for key, val in update_dict.items():
        if key == "one_off_costs":
            set_parts.append(f"{key} = ${idx}::jsonb")
        else:
            set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    set_parts.append("updated_at = NOW()")

    values.append(placement_id)
    row = await fetch_one(
        f"""UPDATE placements SET {', '.join(set_parts)}
            WHERE id = ${idx} AND deleted_at IS NULL
            RETURNING *""",
        *values,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Placement not found")

    await _audit(
        "placement_update", current_user["id"], placement_id,
        updates.model_dump(exclude_unset=True, mode="json"),
    )
    return _coerce_one_off_costs(row)


@router.post("/{placement_id}/status")
async def update_placement_status(
    placement_id: int,
    payload: PlacementStatusUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    """Transition a placement's status. Validated against the fixed
    concept -> actief -> beeindigd (+ geannuleerd from concept/actief)
    graph before the write; see validate_status_transition()."""
    existing = await _get_placement_or_404(placement_id)
    validate_status_transition(existing["status"], payload.status)

    row = await fetch_one(
        """UPDATE placements SET status = $2, updated_at = NOW()
           WHERE id = $1 AND deleted_at IS NULL
           RETURNING *""",
        placement_id, payload.status,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Placement not found")

    await _audit(
        "placement_status_change", current_user["id"], placement_id,
        {"from": existing["status"], "to": payload.status},
    )
    return _coerce_one_off_costs(row)


@router.delete("/{placement_id}", status_code=204)
async def delete_placement(
    placement_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """Soft delete -- sets deleted_at, never a real DELETE (placements are
    fiscal/GDPR-retained records, same as every other soft-deletable table
    here)."""
    row = await fetch_one(
        """UPDATE placements SET deleted_at = NOW(), updated_at = NOW()
           WHERE id = $1 AND deleted_at IS NULL
           RETURNING id""",
        placement_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Placement not found")

    await _audit("placement_delete", current_user["id"], placement_id, {})
    return None


# ── Margin ─────────────────────────────────────────────────────────────

@router.get("/{placement_id}/margin")
async def get_placement_margin(
    placement_id: int,
    gross_monthly_salary: Optional[float] = Query(
        None, description="Detachering cost input: gross monthly salary, used with "
                           "eor_cost_factor when monthly_purchase_price isn't set directly."),
    annual_salary: Optional[float] = Query(
        None, description="Werving & selectie fee input: annual salary the "
                           "fee_percentage is applied to."),
    current_user: dict = Depends(require_role("admin")),
):
    """PROVISIONAL -- see core/margin.py. Not published anywhere; owner
    sign-off required before any figure this returns is treated as final."""
    placement = await _get_placement_or_404(placement_id)
    return compute_margin(
        placement,
        gross_monthly_salary=gross_monthly_salary,
        annual_salary=annual_salary,
    )
