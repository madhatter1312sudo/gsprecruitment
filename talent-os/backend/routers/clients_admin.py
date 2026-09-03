"""
Talent OS — Admin Clients list/detail (WS-B.5 follow-up).

The admin "Opdrachtgevers" (clients) UI had to derive its roster from
GET /api/v1/admin/users?role=client with one extra call per row (no list
endpoint existed over `clients` itself). This router adds that endpoint,
plus a detail view and a PATCH, all under the same
/api/v1/admin/clients prefix routers/client_contacts.py already uses for
its /{client_id}/contacts sub-routes (no path collision -- those all have
a trailing /contacts segment).

erkend_referent / notes are migrations/031_clients_erkend_referent.py.
open_job_count and primary_contact are both computed with LEFT JOIN
LATERAL subqueries -- one query for the whole page, no N+1 per row (the
thing this endpoint exists to fix).
"""
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.database import fetch_one, fetch_all, fetch_val, execute
from core.deps import require_role
from models.schemas import ClientAdminUpdate

router = APIRouter(prefix="/api/v1/admin/clients", tags=["clients-admin"])

ERKEND_REFERENT_VALUES = {"ja", "nee", "onbekend"}

# Fields PATCH is allowed to touch, mapped 1:1 to clients columns.
_UPDATABLE_FIELDS = {"company_name", "domain", "industry", "erkend_referent", "notes"}

_LATERAL_JOINS = """
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS open_job_count
    FROM job_orders j
    WHERE j.client_id = c.id
      AND j.status = 'open'
      AND j.deleted_at IS NULL
      AND j.is_demo = false
) oj ON true
LEFT JOIN LATERAL (
    SELECT cc.full_name, cc.email, cc.role
    FROM client_contacts cc
    WHERE cc.client_id = c.id
      AND cc.is_primary = true
      AND cc.deleted_at IS NULL
    ORDER BY cc.created_at
    LIMIT 1
) pc ON true
"""


def _escape_like(term: str) -> str:
    """Escape a user-supplied ILIKE search term so literal % / _ / \\ in the
    input can't be used as wildcards. Paired with `ESCAPE '\\'` in the SQL."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row_to_list_item(row: dict) -> dict:
    primary_contact = None
    if row.get("full_name"):
        primary_contact = {
            "full_name": row["full_name"],
            "email": row.get("email"),
            "role": row.get("role"),
        }
    return {
        "id": row["id"],
        "company_name": row["company_name"],
        "domain": row.get("domain"),
        "industry": row.get("industry"),
        "erkend_referent": row["erkend_referent"],
        "open_job_count": row["open_job_count"] or 0,
        "primary_contact": primary_contact,
        "created_at": row["created_at"],
    }


@router.get("")
async def list_clients(
    search: Optional[str] = Query(None),
    erkend_referent: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_role("admin")),
):
    """List clients with company/domain search, erkend_referent filter,
    each row's open job count and primary contact -- one query, no N+1."""
    if erkend_referent is not None and erkend_referent not in ERKEND_REFERENT_VALUES:
        raise HTTPException(
            status_code=400,
            detail=f"erkend_referent must be one of {sorted(ERKEND_REFERENT_VALUES)}",
        )

    conditions = ["c.deleted_at IS NULL"]
    params = []
    idx = 1

    if search:
        conditions.append(f"(c.company_name ILIKE ${idx} ESCAPE '\\' OR c.domain ILIKE ${idx} ESCAPE '\\')")
        params.append(f"%{_escape_like(search)}%")
        idx += 1
    if erkend_referent:
        conditions.append(f"c.erkend_referent = ${idx}")
        params.append(erkend_referent)
        idx += 1

    where = " AND ".join(conditions)

    total = await fetch_val(f"SELECT COUNT(*) FROM clients c WHERE {where}", *params) or 0

    offset = (page - 1) * limit
    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"""SELECT c.id, c.company_name, c.domain, c.industry, c.erkend_referent, c.created_at,
                   COALESCE(oj.open_job_count, 0) AS open_job_count,
                   pc.full_name, pc.email, pc.role
            FROM clients c
            {_LATERAL_JOINS}
            WHERE {where}
            ORDER BY c.company_name
            LIMIT ${idx} OFFSET ${idx + 1}""",
        *params_ext,
    )

    return {
        "items": [_row_to_list_item(dict(r)) for r in rows],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/{client_id}")
async def get_client_detail(
    client_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    row = await fetch_one(
        f"""SELECT c.id, c.company_name, c.domain, c.industry, c.location,
                   c.erkend_referent, c.notes, c.created_at, c.updated_at,
                   COALESCE(oj.open_job_count, 0) AS open_job_count
            FROM clients c
            {_LATERAL_JOINS}
            WHERE c.id = $1 AND c.deleted_at IS NULL""",
        client_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Client not found")

    contacts = await fetch_all(
        """SELECT * FROM client_contacts
           WHERE client_id = $1 AND deleted_at IS NULL
           ORDER BY is_primary DESC, created_at""",
        client_id,
    )

    result = dict(row)
    result["contacts"] = contacts
    return result


@router.patch("/{client_id}")
async def update_client(
    client_id: int,
    updates: ClientAdminUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    existing = await fetch_one(
        "SELECT id FROM clients WHERE id = $1 AND deleted_at IS NULL", client_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Client not found")

    update_dict = updates.model_dump(exclude_unset=True)
    update_dict = {k: v for k, v in update_dict.items() if k in _UPDATABLE_FIELDS}
    if not update_dict:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    set_parts = []
    values = []
    idx = 1
    for key, val in update_dict.items():
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    values.append(client_id)
    row = await fetch_one(
        f"""UPDATE clients SET {', '.join(set_parts)}, updated_at = NOW()
            WHERE id = ${idx} AND deleted_at IS NULL
            RETURNING id, company_name, domain, industry, erkend_referent, notes, updated_at""",
        *values,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Client not found")

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        "client_update", current_user["id"], "client", client_id, json.dumps(update_dict),
    )

    return row
