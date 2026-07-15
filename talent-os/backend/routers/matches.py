"""
Talent OS — Matches router (asyncpg, auth-protected).
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from core.database import fetch_all, fetch_one, execute
from core.security import verify_api_key
from services.matcher import EmbeddingMatcher
from typing import Optional

logger = logging.getLogger("talent_os.matches")

router = APIRouter(prefix="/api/matches", tags=["matches"], dependencies=[Depends(verify_api_key)])


async def _run_matching_for_job(job_id: int) -> None:
    """Embed the job against all active candidates and upsert match rows.
    Runs in a FastAPI background task — no Celery/Redis required."""
    matcher = EmbeddingMatcher()
    try:
        job = await fetch_one(
            "SELECT id, title, description, requirements FROM job_orders "
            "WHERE id = $1 AND deleted_at IS NULL",
            job_id,
        )
        if not job:
            logger.warning("matching: job %s not found", job_id)
            return

        candidates = await fetch_all(
            "SELECT id, full_name, current_title, cv_text, skills FROM candidates "
            "WHERE deleted_at IS NULL AND consent_withdrawn_at IS NULL",
        )
        if not candidates:
            logger.info("matching: no candidates to match for job %s", job_id)
            return

        job_text = f"{job['title']} {job['description'] or ''} {job['requirements'] or ''}"
        results = await matcher.match_job_to_candidates(
            job_text, [dict(c) for c in candidates], min_score=0.3,
        )

        for r in results:
            # match_score is stored on the 0–100 scale everywhere
            await execute(
                """INSERT INTO matches (candidate_id, job_id, match_score, status)
                   VALUES ($1, $2, $3, 'suggested')
                   ON CONFLICT (candidate_id, job_id)
                   DO UPDATE SET match_score = EXCLUDED.match_score
                   WHERE matches.status = 'suggested'""",
                r["candidate_id"], job_id, r["match_score"],
            )
        logger.info("matching: job %s matched against %s candidates, %s results",
                    job_id, len(candidates), len(results))
    except Exception:
        logger.exception("matching: failed for job %s", job_id)
    finally:
        await matcher.close()


@router.post("/run", status_code=202)
async def run_matching(
    background_tasks: BackgroundTasks,
    job_id: Optional[int] = Query(None, description="Match one job; omit to match all open jobs"),
):
    """Trigger semantic matching (OpenRouter embeddings) as a background task."""
    if job_id is not None:
        job = await fetch_one(
            "SELECT id FROM job_orders WHERE id = $1 AND deleted_at IS NULL", job_id,
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        background_tasks.add_task(_run_matching_for_job, job_id)
        return {"message": "Matching started", "job_ids": [job_id]}

    jobs = await fetch_all(
        "SELECT id FROM job_orders WHERE status = 'open' AND deleted_at IS NULL",
    )
    for j in jobs:
        background_tasks.add_task(_run_matching_for_job, j["id"])
    return {"message": "Matching started", "job_ids": [j["id"] for j in jobs]}


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