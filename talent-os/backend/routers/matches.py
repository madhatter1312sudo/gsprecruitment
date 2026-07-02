"""
Talent OS — Matches router (asyncpg, auth-protected).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from core.database import fetch_all, fetch_one
from core.security import verify_api_key
from typing import Optional

router = APIRouter(prefix="/api/matches", tags=["matches"], dependencies=[Depends(verify_api_key)])


@router.get("")
async def list_matches(
    job_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
):
    """List matches with optional filters."""
    conditions = []
    params = []
    idx = 1

    if job_id is not None:
        conditions.append(f"job_id = ${idx}")
        params.append(job_id)
        idx += 1
    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if min_score is not None:
        conditions.append(f"match_score >= ${idx}")
        params.append(min_score)
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(limit)
    sql = f"SELECT * FROM matches {where} ORDER BY match_score DESC LIMIT ${idx}"

    rows = await fetch_all(sql, *params)
    return rows


@router.get("/{match_id}")
async def get_match(match_id: int):
    """Get a single match by ID."""
    row = await fetch_one("SELECT * FROM matches WHERE id = $1", match_id)
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    return row


@router.get("/job/{job_id}")
async def get_job_matches(job_id: int, min_score: float = Query(0, ge=0, le=100)):
    """Get all matches for a specific job, sorted by score."""
    rows = await fetch_all(
        "SELECT m.*, c.full_name, c.current_title, c.current_company "
        "FROM matches m JOIN candidates c ON m.candidate_id = c.id "
        "WHERE m.job_id = $1 AND m.match_score >= $2 "
        "ORDER BY m.match_score DESC",
        job_id, min_score,
    )
    return rows