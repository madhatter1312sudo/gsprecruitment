"""
Talent OS — Health check and status router.
"""
from fastapi import APIRouter, Depends
from core.database import fetch_val, get_pool
from core.config import settings
from models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Comprehensive health check — database, OpenRouter connectivity, etc."""
    db_status = "unknown"
    candidates_count = None
    open_jobs = None
    apollo_status = "unknown"
    openrouter_status = "unknown"

    # Check database connectivity
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        db_status = "connected"

        # Get quick counts
        candidates_count = await fetch_val("SELECT COUNT(*) FROM candidates")
        open_jobs = await fetch_val("SELECT COUNT(*) FROM job_orders WHERE status = 'open'")
    except Exception as e:
        db_status = f"error: {type(e).__name__}"

    # Check OpenRouter API key presence (actual call skipped in health)
    if settings.openrouter_api_key:
        openrouter_status = "configured"
    else:
        openrouter_status = "not configured"

    # Check Apollo.io API key presence
    if settings.apollo_api_key:
        apollo_status = "configured"
    else:
        apollo_status = "not configured"

    overall = "ok" if db_status == "connected" else "degraded"

    return HealthResponse(
        status=overall,
        database=db_status,
        openrouter=openrouter_status,
        apollo=apollo_status,
        candidates_count=candidates_count,
        open_jobs=open_jobs,
    )