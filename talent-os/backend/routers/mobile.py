"""
Talent OS — Mobile App Backend Router (JWT-protected).
Push notification tokens for the React Native mobile app.

WS-C.3b (2026-09-03): the /me/matches and /me/applications aliases that
used to live here were removed -- app/lib/api.ts documents that the app
uses /v1/candidate/... for both (routers/candidate.py) and never calls the
/v1/mobile/me/... aliases (grepped app/ for "mobile/me": no hits outside
that comment). Candidate matches/applications now live only in
routers/candidate.py.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from core.database import execute
from core.deps import get_current_user
from models.schemas import PushTokenCreate, PushTokenDelete

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
