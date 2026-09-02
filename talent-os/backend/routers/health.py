"""
Talent OS — Health check and status router.

GET /health is public and deliberately minimal (status/version/database
only) so the uptime monitor keeps working without auth. The previous
version also returned live row counts (candidates_count, open_jobs) and
vendor/integration configuration status to anyone, unauthenticated -- that
detail now lives behind an admin JWT at GET /api/v1/admin/health (see
routers/admin.py, WS-C.3a).
"""
from fastapi import APIRouter
from core.database import fetch_val, get_pool
from core.config import settings
from models.schemas import HealthResponse, PublicHealthResponse

router = APIRouter(tags=["health"])


async def _check_database() -> str:
    """Ping the database. Returns 'connected' or 'error: <ExceptionType>'."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        return "connected"
    except Exception as e:
        return f"error: {type(e).__name__}"


async def get_health_detail() -> HealthResponse:
    """Full health payload (counts + vendor status). Called only from the
    admin-gated route in routers/admin.py -- never exposed publicly."""
    db_status = await _check_database()

    candidates_count = None
    open_jobs = None
    if db_status == "connected":
        candidates_count = await fetch_val("SELECT COUNT(*) FROM candidates")
        open_jobs = await fetch_val("SELECT COUNT(*) FROM job_orders WHERE status = 'open'")

    openrouter_status = "configured" if settings.openrouter_api_key else "not configured"
    apollo_status = "configured" if settings.apollo_api_key else "not configured"
    overall = "ok" if db_status == "connected" else "degraded"

    return HealthResponse(
        status=overall,
        database=db_status,
        openrouter=openrouter_status,
        apollo=apollo_status,
        candidates_count=candidates_count,
        open_jobs=open_jobs,
    )


@router.get("/health", response_model=PublicHealthResponse)
async def health_check():
    """Public health check for the uptime monitor -- status/version/database
    only. No auth, so nothing beyond liveness is returned here."""
    db_status = await _check_database()
    overall = "ok" if db_status == "connected" else "degraded"
    return PublicHealthResponse(status=overall, database=db_status)
