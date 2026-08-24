"""
Talent OS — Matches router (asyncpg, auth-protected).
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from core.database import fetch_all, fetch_one, execute
from core.security import verify_api_key
from services.matcher import EmbeddingMatcher
from models.schemas import MatchCreate
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


@router.post("", status_code=201)
async def create_match(payload: MatchCreate):
    """Create/upsert a match. Lets an external agent (e.g. a Claude cloud
    agent doing matching) write results directly, instead of the in-backend
    OpenRouter matcher in _run_matching_for_job. Same upsert semantics as
    that job. `rationale` is accepted but not persisted — no column for it
    yet."""
    candidate = await fetch_one(
        "SELECT id FROM candidates WHERE id = $1 AND deleted_at IS NULL", payload.candidate_id,
    )
    if not candidate:
        raise HTTPException(status_code=400, detail=f"Candidate {payload.candidate_id} not found")

    job = await fetch_one(
        "SELECT id FROM job_orders WHERE id = $1 AND deleted_at IS NULL", payload.job_id,
    )
    if not job:
        raise HTTPException(status_code=400, detail=f"Job {payload.job_id} not found")

    row = await fetch_one(
        """INSERT INTO matches (candidate_id, job_id, match_score, status)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT (candidate_id, job_id)
           DO UPDATE SET match_score = EXCLUDED.match_score, status = EXCLUDED.status
           WHERE matches.status = 'suggested'
           RETURNING *""",
        payload.candidate_id, payload.job_id, payload.match_score, payload.status,
    )
    return row


@router.get("/candidates-for-job/{job_id}")
async def candidates_for_job(job_id: int, limit: int = Query(30, ge=1, le=100)):
    """Cheap keyword-overlap prefilter — NO AI, NO OpenRouter. Ranks active
    candidates against a job's title/requirements so an external agent (e.g.
    a Claude cloud agent) can shortlist without pulling all candidates."""
    job = await fetch_one(
        "SELECT id, title, description, requirements FROM job_orders "
        "WHERE id = $1 AND deleted_at IS NULL", job_id,
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_text = f"{job['title'] or ''} {job['requirements'] or ''}"
    # Cheap tokenization for the skills-overlap bonus: distinct alphanumeric
    # words of length >= 3, lowercased.
    tokens = sorted(set(
        w for w in job_text.lower().replace("/", " ").replace(",", " ").split()
        if len(w) >= 3
    ))
    if not tokens:
        return []

    # Rank on the existing `cv_search` tsvector (GIN-indexed, dutch stemmed)
    # plus a bonus for skills[] overlap with the job's keyword tokens
    # (also GIN-indexed) — no AI/embeddings involved.
    rows = await fetch_all(
        """SELECT c.id, c.full_name, c.current_title, c.current_company, c.skills,
                  c.location, c.years_experience, c.cv_text,
                  ts_rank(c.cv_search, plainto_tsquery('dutch', $1)) AS cv_rank,
                  (SELECT COUNT(*) FROM unnest(c.skills) s WHERE lower(s) = ANY($2::text[])) AS skill_matches
           FROM candidates c
           WHERE c.deleted_at IS NULL AND c.consent_withdrawn_at IS NULL
           ORDER BY (ts_rank(c.cv_search, plainto_tsquery('dutch', $1)) + skill_matches * 0.05) DESC,
                    c.updated_at DESC NULLS LAST
           LIMIT $3""",
        job_text, tokens, limit,
    )

    return [
        {
            "id": r["id"],
            "full_name": r["full_name"],
            "current_title": r["current_title"],
            "current_company": r["current_company"],
            "skills": r["skills"],
            "location": r["location"],
            "years_experience": float(r["years_experience"]) if r["years_experience"] is not None else None,
            "cv_excerpt": (r["cv_text"] or "")[:500],
            "cv_rank": float(r["cv_rank"]),
            "skill_matches": r["skill_matches"],
        }
        for r in rows
    ]


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