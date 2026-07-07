"""
Talent OS — Public API Router.
Unauthenticated endpoints for site content, salary benchmarks, and lead submission.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from core.database import fetch_all, fetch_one, execute
from core.config import settings
from models.schemas import SiteContentResponse, LeadSubmit, SalaryBenchmarkResponse
from typing import Optional, List

router = APIRouter(prefix="/api/v1/public", tags=["public"])

from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)


# ── Site Content ────────────────────────────────────────────────────────

@router.get("/site-content", response_model=SiteContentResponse)
@limiter.limit("30/minute")
async def get_site_content(request: Request, response: Response, section: str = Query(..., description="Content section (e.g. hero, features, about)")):
    """Get site content by section."""
    response.headers["Cache-Control"] = "public, max-age=300"
    rows = await fetch_all(
        "SELECT * FROM site_content WHERE section = $1 ORDER BY sort_order, key",
        section,
    )
    if not rows:
        # Return empty rather than 404 so the frontend can handle it
        return SiteContentResponse(section=section, items=[])

    items = []
    for row in rows:
        items.append({
            "id": row["id"],
            "key": row["key"],
            "value": row["value"],
            "label": row.get("label"),
            "sort_order": row.get("sort_order", 0),
        })

    return SiteContentResponse(section=section, items=items)


# ── Salary Data ─────────────────────────────────────────────────────────

@router.get("/salary-data", response_model=List[SalaryBenchmarkResponse])
@limiter.limit("30/minute")
async def get_public_salary_data(request: Request, response: Response,
    role_title: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    seniority: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Get salary benchmark data (public)."""
    response.headers["Cache-Control"] = "public, max-age=300"
    conditions = []
    params = []
    idx = 1

    if role_title:
        conditions.append(f"role_title ILIKE ${idx}")
        params.append(f"%{role_title}%")
        idx += 1
    if location:
        conditions.append(f"location ILIKE ${idx}")
        params.append(f"%{location}%")
        idx += 1
    if seniority:
        conditions.append(f"seniority = ${idx}")
        params.append(seniority)
        idx += 1

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(limit)

    rows = await fetch_all(
        f"SELECT * FROM salary_benchmarks {where} ORDER BY role_title LIMIT ${idx}",
        *params,
    )
    return rows


# ── Lead Submission ─────────────────────────────────────────────────────

@router.post("/lead", status_code=201)
@limiter.limit("10/minute")
async def submit_lead(request: Request, data: LeadSubmit):
    """Submit a lead or contact form entry."""
    # Store the lead submission
    lead = await fetch_one(
        """INSERT INTO contact_submissions
           (name, email, company, phone, message, interest_type)
           VALUES ($1, $2, $3, $4, $5, $6)
           RETURNING id, created_at""",
        data.name, data.email.lower().strip(), data.company,
        data.phone, data.message, data.interest_type,
    )
    if not lead:
        raise HTTPException(status_code=500, detail="Failed to submit lead")

    return {
        "message": "Thank you! We'll get back to you shortly.",
        "id": lead["id"],
        "created_at": lead["created_at"],
    }