"""
Talent OS — FastAPI async entry point.
ALL AI/LLM calls go through OpenRouter API. NO models hosted on VPS.

PostgreSQL via asyncpg connection pooling.
Celery workers for background tasks (Apollo sync, semantic matching).
API key authentication on all data endpoints.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from core.config import settings
from core.database import close_pool
from services.scheduler import start_scheduler, shutdown_scheduler


# ── Logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("talent_os")


# ── Lifespan ───────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Talent OS starting up...")
    logger.info(f"Database: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")
    logger.info(f"OpenRouter: {'configured' if settings.openrouter_api_key else 'NOT configured'}")
    logger.info(f"Apollo.io: {'configured' if settings.apollo_api_key else 'NOT configured'}")
    logger.info("ALL AI/LLM calls go through OpenRouter. NO models on VPS.")

    try:
        start_scheduler()
    except Exception:
        logger.exception("Failed to start sourcing/outreach scheduler — continuing without it")

    yield
    logger.info("Shutting down...")
    shutdown_scheduler()
    await close_pool()


# ── App ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Talent OS — Hermes Recruitment Engine",
    description="Multi-agent recruitment platform. PostgreSQL + asyncpg + Celery + Next.js.",
    version="1.0.0",
    lifespan=lifespan,
)

# Limiter — rate limiting across all endpoints
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — restricted to dashboard origins only (NOT wildcard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["X-API-Key", "Authorization", "X-Hermes-Signature", "Content-Type"],
)

# SlowAPI middleware (must be after CORS)
app.add_middleware(SlowAPIMiddleware)

# ── Routers ─────────────────────────────────────────────────────────────
from routers.health import router as health_router
from routers.auth import router as auth_router
from routers.candidates import router as candidates_router
from routers.jobs import router as jobs_router
from routers.jobs import public_jobs_router
from routers.matches import router as matches_router
from routers.apollo import router as apollo_router
from routers.webhook import router as webhook_router
from routers.candidate import router as candidate_portal_router
from routers.client import router as client_portal_router
from routers.admin import router as admin_portal_router
from routers.public import router as public_router
from routers.gdpr import router as gdpr_router
from routers.outreach import router as outreach_router

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(candidates_router)
app.include_router(jobs_router)
app.include_router(public_jobs_router)
app.include_router(matches_router)
app.include_router(apollo_router)
app.include_router(webhook_router)
app.include_router(candidate_portal_router)
app.include_router(client_portal_router)
app.include_router(admin_portal_router)
app.include_router(public_router)
app.include_router(gdpr_router)
app.include_router(outreach_router)


# ── Entry Point ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        workers=settings.backend_workers,
        log_level=settings.log_level.lower(),
    )