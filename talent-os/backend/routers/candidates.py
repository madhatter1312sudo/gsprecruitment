"""
Talent OS — Candidate CRUD router (asyncpg, auth-protected).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from core.database import fetch_all, fetch_one, execute
from core.security import verify_api_key
from models.schemas import (
    CandidateCreate, CandidateResponse, CandidatePublicResponse,
    CandidateSourceCreate, CandidateAdminUpdate,
)
from typing import Optional, List

router = APIRouter(prefix="/api/candidates", tags=["candidates"], dependencies=[Depends(verify_api_key)])

# FIX 2 (chief-of-staff, ai-pseudonimisering branch): GET /api/candidates
# and GET /api/candidates/{id} sit behind the same X-API-Key the external
# Claude routines use, and used to run `SELECT *` -- returning cv_text
# (the branch's core claim is "no more CV text to external providers")
# plus every future column added to candidates with no review. Explicit
# column list, cv_text deliberately left out. Keep in sync with
# CandidateResponse (models/schemas.py) minus cv_text.
_CANDIDATE_PUBLIC_COLUMNS = """id, full_name, email, phone, linkedin_url, github_url, portfolio_url,
    current_company, current_title, location, willing_to_relocate,
    salary_expectation_min, salary_expectation_max, notice_period_days,
    years_experience, skills, languages, education,
    source, source_url, lawful_basis, date_found, sourced_by_agent,
    strength_score, switch_readiness, tags, status, is_passive,
    screening_score, screening_notes, quality_score, cv_file_path,
    created_at, updated_at"""


@router.get("", response_model=List[CandidatePublicResponse])
async def list_candidates(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List candidates with optional status filter and pagination.
    Soft-deleted rows and rows with withdrawn consent are excluded, and
    cv_text is never selected (FIX 2 -- see _CANDIDATE_PUBLIC_COLUMNS)."""
    if status:
        rows = await fetch_all(
            f"SELECT {_CANDIDATE_PUBLIC_COLUMNS} FROM candidates "
            "WHERE status = $1 AND deleted_at IS NULL AND consent_withdrawn_at IS NULL "
            "ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            status, limit, offset,
        )
    else:
        rows = await fetch_all(
            f"SELECT {_CANDIDATE_PUBLIC_COLUMNS} FROM candidates "
            "WHERE deleted_at IS NULL AND consent_withdrawn_at IS NULL "
            "ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
    return rows


@router.get("/{candidate_id}", response_model=CandidatePublicResponse)
async def get_candidate(candidate_id: int):
    """Get a single candidate by ID. Soft-deleted rows and rows with
    withdrawn consent are excluded, and cv_text is never selected
    (FIX 2 -- see _CANDIDATE_PUBLIC_COLUMNS)."""
    row = await fetch_one(
        f"SELECT {_CANDIDATE_PUBLIC_COLUMNS} FROM candidates "
        "WHERE id = $1 AND deleted_at IS NULL AND consent_withdrawn_at IS NULL",
        candidate_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return row


@router.post("", response_model=CandidateResponse, status_code=201, response_model_exclude={"cv_text"})
async def create_candidate(candidate: CandidateSourceCreate):
    """Create a new candidate record. WS-E.7: source_url (public http(s)
    URL) and lawful_basis are required — SOP §2 "geen bron-URL = geen
    contact"."""
    row = await fetch_one(
        """INSERT INTO candidates
           (full_name, email, phone, linkedin_url, github_url, portfolio_url,
            current_company, current_title, location, willing_to_relocate,
            salary_expectation_min, salary_expectation_max, notice_period_days,
            years_experience, skills, languages, education, cv_text,
            source, sourced_by_agent, strength_score, switch_readiness, tags,
            source_url, lawful_basis, date_found)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26)
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
        candidate.source_url, candidate.lawful_basis, candidate.date_found,
    )
    return row


@router.patch("/{candidate_id}", response_model=CandidatePublicResponse)
async def update_candidate(candidate_id: int, updates: CandidateAdminUpdate):
    """Partial update of a candidate record. Soft-deleted rows and rows
    with withdrawn consent are excluded (same guard as GET), and cv_text
    is never returned (FIX 2 follow-up, chief-of-staff ai-pseudonimisering
    branch): this endpoint used `RETURNING *` with only `WHERE id = $n`,
    so a PATCH (e.g. the status/screening_score update the external
    routines use) on a withdrawn-consent or soft-deleted row both
    mutated it and handed back full_name/email/phone/cv_text -- the exact
    leak GET was closed against, reachable via a different verb. cv_text
    is excluded here even though allowed_fields never includes it, because
    RETURNING * still selects the column regardless of what was written."""
    # Build dynamic SET clause safely
    allowed_fields = {
        "status", "screening_score", "screening_notes", "quality_score",
        "screened_by_agent", "strength_score", "switch_readiness", "tags",
    }
    set_parts = []
    values = []
    idx = 1
    for key, val in updates.model_dump(exclude_unset=True).items():
        if key not in allowed_fields:
            continue
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    if not set_parts:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    set_parts.append(f"updated_at = NOW()")
    values.append(candidate_id)
    sql = (
        f"UPDATE candidates SET {', '.join(set_parts)} "
        f"WHERE id = ${idx} AND deleted_at IS NULL AND consent_withdrawn_at IS NULL "
        f"RETURNING *"
    )
    row = await fetch_one(sql, *values)
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return row