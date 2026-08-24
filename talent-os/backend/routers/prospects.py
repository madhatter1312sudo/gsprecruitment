"""
Talent OS — Client Prospects Admin Router (JWT-protected, role='admin').

Read/write API for `client_prospects` (BD leads — hiring managers/CTOs at
target companies). Existing writers are services/harvest.py (bulk Apollo
sourcing) and services/apollo_client.py (enrichment); this router adds the
first API surface so an external agent (e.g. a Claude cloud agent doing
public vacancy monitoring) can log leads it finds by hand.

Column names follow the client_prospects schema in
migrations/012_mobile_growth.py:
  id, company_name, domain, contact_name, contact_title, contact_email,
  contact_linkedin, location, industry, source, intent_signal, status,
  created_at.
There is no phone or size column, and no dedicated notes column — notes
are stored in intent_signal (free-text), same slot harvest.py otherwise
uses for the Apollo person-id reference on bulk-sourced rows.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.database import fetch_one, fetch_all, fetch_val, execute
from core.deps import require_role

logger = logging.getLogger("talent_os.prospects")

router = APIRouter(prefix="/api/v1/admin/prospects", tags=["prospects"])


class ProspectCreate(BaseModel):
    """Create a client prospect — used by external agents (e.g. a Claude
    cloud agent monitoring public vacancy postings) to log a company lead."""
    company: str
    contact_name: Optional[str] = None
    contact_title: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    website: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    source: str = "claude-leadgen"
    notes: Optional[str] = None
    status: Optional[str] = None


class ProspectUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


# ── Prospects ───────────────────────────────────────────────────────────

@router.get("")
async def list_prospects(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_role("admin")),
):
    """List client prospects, optionally filtered by company search
    (ILIKE) and status."""
    conditions = []
    params = []
    idx = 1

    if search:
        conditions.append(f"company_name ILIKE ${idx}")
        params.append(f"%{search}%")
        idx += 1
    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    total = await fetch_val(f"SELECT COUNT(*) FROM client_prospects {where}", *params) or 0
    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"""SELECT * FROM client_prospects {where}
            ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}""",
        *params_ext,
    )

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.post("", status_code=201)
async def create_prospect(
    payload: ProspectCreate,
    current_user: dict = Depends(require_role("admin")),
):
    """Create a new client prospect. Rejects (409) if a prospect with the
    same company name (case-insensitive) already exists."""
    existing = await fetch_one(
        "SELECT id FROM client_prospects WHERE LOWER(company_name) = LOWER($1)",
        payload.company,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A prospect for company '{payload.company}' already exists (id={existing['id']})",
        )

    row = await fetch_one(
        """INSERT INTO client_prospects
           (company_name, domain, contact_name, contact_title, contact_email,
            contact_linkedin, location, industry, source, intent_signal, status)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,COALESCE($11,'new'))
           RETURNING *""",
        payload.company, payload.website, payload.contact_name, payload.contact_title,
        payload.email, payload.linkedin_url, payload.location, payload.industry,
        payload.source, payload.notes, payload.status,
    )

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        "prospect_create", current_user["id"], "client_prospect", row["id"],
        payload.model_dump_json(),
    )

    return row


@router.put("/{prospect_id}")
async def update_prospect(
    prospect_id: int,
    updates: ProspectUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    """Update a prospect's pipeline status/notes."""
    update_dict = updates.model_dump(exclude_none=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_parts = []
    values = []
    idx = 1
    # notes -> intent_signal (see module docstring: no dedicated notes column)
    column_map = {"status": "status", "notes": "intent_signal"}
    for key, val in update_dict.items():
        set_parts.append(f"{column_map[key]} = ${idx}")
        values.append(val)
        idx += 1

    values.append(prospect_id)
    row = await fetch_one(
        f"UPDATE client_prospects SET {', '.join(set_parts)} WHERE id = ${idx} RETURNING *",
        *values,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Prospect not found")

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        "prospect_update", current_user["id"], "client_prospect", prospect_id,
        json.dumps(update_dict),
    )

    return row
