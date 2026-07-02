"""
Talent OS — Candidate CRUD router (asyncpg, auth-protected).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from core.database import fetch_all, fetch_one, execute
from core.security import verify_api_key
from models.schemas import CandidateCreate, CandidateResponse
from typing import Optional, List

router = APIRouter(prefix="/api/candidates", tags=["candidates"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=List[CandidateResponse])
async def list_candidates(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List candidates with optional status filter and pagination."""
    if status:
        rows = await fetch_all(
            "SELECT * FROM candidates WHERE status = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            status, limit, offset,
        )
    else:
        rows = await fetch_all(
            "SELECT * FROM candidates ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
    return rows


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(candidate_id: int):
    """Get a single candidate by ID."""
    row = await fetch_one("SELECT * FROM candidates WHERE id = $1", candidate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return row


@router.post("", response_model=CandidateResponse, status_code=201)
async def create_candidate(candidate: CandidateCreate):
    """Create a new candidate record."""
    row = await fetch_one(
        """INSERT INTO candidates
           (full_name, email, phone, linkedin_url, github_url, portfolio_url,
            current_company, current_title, location, willing_to_relocate,
            salary_expectation_min, salary_expectation_max, notice_period_days,
            years_experience, skills, languages, education, cv_text,
            source, sourced_by_agent, strength_score, switch_readiness, tags)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23)
           RETURNING *""",
        candidate.full_name, candidate.email, candidate.phone,
        candidate.linkedin_url, candidate.github_url, candidate.portfolio_url,
        candidate.current_company, candidate.current_title, candidate.location,
        candidate.willing_to_relocate, candidate.salary_expectation_min,
        candidate.salary_expectation_max, candidate.notice_period_days,
        candidate.years_experience, candidate.skills, candidate.languages,
        candidate.education, candidate.cv_text, candidate.source,
        candidate.sourced_by_agent, candidate.strength_score,
        candidate.switch_readiness, candidate.tags,
    )
    return row


@router.patch("/{candidate_id}", response_model=CandidateResponse)
async def update_candidate(candidate_id: int, updates: dict):
    """Partial update of a candidate record."""
    # Build dynamic SET clause safely
    allowed_fields = {
        "status", "screening_score", "screening_notes", "quality_score",
        "screened_by_agent", "strength_score", "switch_readiness", "tags",
    }
    set_parts = []
    values = []
    idx = 1
    for key, val in updates.items():
        if key not in allowed_fields:
            continue
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    if not set_parts:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    set_parts.append(f"updated_at = NOW()")
    values.append(candidate_id)
    sql = f"UPDATE candidates SET {', '.join(set_parts)} WHERE id = ${idx} RETURNING *"
    row = await fetch_one(sql, *values)
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return row