"""
Talent OS — Mobile App Backend Router (JWT-protected).
Push notification tokens plus the candidate "matches" and "pipeline"
(applications) views consumed by the React Native mobile app.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from core.database import fetch_all, execute
from core.deps import get_current_user
from models.schemas import PushTokenCreate, PushTokenDelete
from routers.candidate import _get_candidate_id

logger = logging.getLogger("talent_os.mobile")

router = APIRouter(prefix="/api/v1/mobile", tags=["mobile"])


# ── Push Tokens ─────────────────────────────────────────────────────────

@router.post("/push-token", status_code=201)
async def upsert_push_token(
    data: PushTokenCreate,
    current_user: dict = Depends(get_current_user),
):
    """Register (or refresh the platform of) a push token for the current user."""
    await execute(
        """INSERT INTO push_tokens (user_id, token, platform)
           VALUES ($1, $2, $3)
           ON CONFLICT (user_id, token) DO UPDATE SET platform = EXCLUDED.platform""",
        current_user["id"], data.token, data.platform,
    )
    return {"message": "Push token registered"}


@router.delete("/push-token")
async def delete_push_token(
    data: PushTokenDelete,
    current_user: dict = Depends(get_current_user),
):
    """Remove a push token for the current user (e.g. on logout / uninstall)."""
    result = await execute(
        "DELETE FROM push_tokens WHERE user_id = $1 AND token = $2",
        current_user["id"], data.token,
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Push token not found")
    return {"message": "Push token removed"}


# ── Matches ─────────────────────────────────────────────────────────────

@router.get("/me/matches")
async def get_my_matches(current_user: dict = Depends(get_current_user)):
    """Matches for the current candidate, joined with job info, ordered by score."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can view their matches")

    candidate_id = await _get_candidate_id(current_user["id"])
    if not candidate_id:
        return {"items": []}

    rows = await fetch_all(
        """SELECT m.id AS match_id, m.match_score AS score, m.status,
                  j.id AS job_id, j.title, j.salary_min, j.salary_max, j.salary_currency,
                  j.location_type, j.status AS job_status, c.company_name
           FROM matches m
           JOIN job_orders j ON j.id = m.job_id
           JOIN clients c ON c.id = j.client_id
           WHERE m.candidate_id = $1
           ORDER BY m.match_score DESC NULLS LAST""",
        candidate_id,
    )
    return {"items": rows}


# ── Applications (pipeline view) ────────────────────────────────────────

@router.get("/me/applications")
async def get_my_applications(current_user: dict = Depends(get_current_user)):
    """Candidate's application/pipeline view: job info plus current stage/status."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can view their applications")

    candidate_id = await _get_candidate_id(current_user["id"])
    if not candidate_id:
        return {"items": []}

    rows = await fetch_all(
        """SELECT m.id AS application_id, m.status AS stage, m.match_score AS score,
                  m.created_at,
                  j.id AS job_id, j.title, j.salary_min, j.salary_max, j.salary_currency,
                  j.location_type, c.company_name
           FROM matches m
           JOIN job_orders j ON j.id = m.job_id
           JOIN clients c ON c.id = j.client_id
           WHERE m.candidate_id = $1
             AND m.status IN ('applied', 'interviewing', 'offered', 'placed', 'rejected')
           ORDER BY m.created_at DESC""",
        candidate_id,
    )
    return {"items": rows}
