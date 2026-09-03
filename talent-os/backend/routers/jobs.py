"""
Talent OS — Job Orders router (asyncpg, auth-protected).
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from core.database import fetch_all, fetch_one, execute
from core.security import verify_api_key
from models.schemas import JobOrderCreate, JobOrderUpdate
from typing import Optional, List

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(verify_api_key)])


@router.get("")
async def list_jobs(status: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200)):
    """List job orders with optional status filter."""
    if status:
        rows = await fetch_all(
            "SELECT * FROM job_orders WHERE status = $1 ORDER BY created_at DESC LIMIT $2",
            status, limit,
        )
    else:
        rows = await fetch_all(
            "SELECT * FROM job_orders ORDER BY created_at DESC LIMIT $1", limit,
        )
    return rows


@router.get("/{job_id}")
async def get_job(job_id: int):
    """Get a single job order by ID."""
    row = await fetch_one("SELECT * FROM job_orders WHERE id = $1", job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return row


@router.post("", status_code=201)
async def create_job(data: JobOrderCreate):
    """Create a new job order."""
    row = await fetch_one(
        """INSERT INTO job_orders
           (client_id, title, department, seniority, location_type,
            salary_min, salary_max, salary_currency, description, requirements,
            nice_to_have, urgency)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
           RETURNING *""",
        data.client_id, data.title, data.department, data.seniority,
        data.location_type, data.salary_min, data.salary_max,
        data.salary_currency, data.description, data.requirements,
        data.nice_to_have, data.urgency,
    )
    return row


@router.patch("/{job_id}")
async def update_job(job_id: int, updates: JobOrderUpdate):
    """Partial update of a job order."""
    allowed = {"status", "title", "department", "seniority", "location_type",
               "salary_min", "salary_max", "salary_currency", "description",
               "requirements", "nice_to_have", "urgency"}
    set_parts = []
    values = []
    idx = 1
    for key, val in updates.model_dump(exclude_none=True).items():
        if key not in allowed:
            continue
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    if not set_parts:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    values.append(job_id)
    sql = f"UPDATE job_orders SET {', '.join(set_parts)} WHERE id = ${idx} RETURNING *"
    row = await fetch_one(sql, *values)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return row
# Public jobs endpoint (no API key required - for the public job board)
public_jobs_router = APIRouter(prefix="/api/public/jobs", tags=["public-jobs"])

# Explicit public-safe column list (WS-C.2): `SELECT *` was leaking internal
# columns (client_id, fee_value, filled_at, deleted_at, ...) to the anonymous
# public job board. Only fields the public site/app actually render belong
# here — see website/vacatures.html, website/vacature.html, and app/ for the
# fields the frontends read. Field names are unchanged, nothing is renamed.
PUBLIC_JOB_COLUMNS = (
    "id, title, department, seniority, location_type, "
    "salary_min, salary_max, salary_currency, "
    "description, requirements, nice_to_have, status, urgency, created_at"
)


@public_jobs_router.get("")
async def list_public_jobs(request: Request):
    """List open job orders for the public job board."""
    rows = await fetch_all(
        f"SELECT {PUBLIC_JOB_COLUMNS} FROM job_orders "
        "WHERE status = 'open' ORDER BY created_at DESC LIMIT 50",
    )
    return rows
