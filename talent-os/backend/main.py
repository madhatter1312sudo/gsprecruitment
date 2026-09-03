"""
Talent OS — FastAPI async entry point.
ALL AI/LLM calls go through OpenRouter API. NO models hosted on VPS.

PostgreSQL via asyncpg connection pooling.
Background tasks (Apollo sync, semantic matching) run as plain asyncio jobs
in-process (services/scheduler.py, FastAPI BackgroundTasks) -- no Celery/Redis.
API key authentication on all data endpoints.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from core.config import settings
from core.database import close_pool
from core.deps import require_role
from core.ratelimit import limiter
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
        await start_scheduler()
    except Exception:
        logger.exception("Failed to start sourcing/outreach scheduler — continuing without it")

    yield
    logger.info("Shutting down...")
    await shutdown_scheduler()
    await close_pool()


# ── App ─────────────────────────────────────────────────────────────────
# /docs, /redoc and /openapi.json exposed the full route map (incl. the
# admin surface) to anyone, unauthenticated. Disable FastAPI's built-in
# public routes here and re-add them below gated behind an admin JWT.
app = FastAPI(
    title="Talent OS — Hermes Recruitment Engine",
    description="Multi-agent recruitment platform. PostgreSQL + asyncpg + FastAPI BackgroundTasks + Next.js.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Limiter — one shared instance (core/ratelimit.py) across the whole app;
# every router imports the same `limiter` object instead of building its
# own, and its key_func (WS-E.4) prefers CF-Connecting-IP, then the first
# X-Forwarded-For hop when the peer is a trusted proxy, else the raw
# socket address. See core/ratelimit.py's module docstring for the
# per-worker in-memory caveat (production runs 4 uvicorn workers).
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
from routers.mfa import router as mfa_router
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
from routers.gdpr import admin_router as gdpr_admin_router
from routers.gdpr import suppression_router
from routers.outreach import router as outreach_router
from routers.blog_admin import router as blog_admin_router
from routers.mobile import router as mobile_router
from routers.prospects import router as prospects_router

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(mfa_router)
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
app.include_router(gdpr_admin_router)
app.include_router(suppression_router)
app.include_router(outreach_router)
app.include_router(blog_admin_router)
app.include_router(mobile_router)
app.include_router(prospects_router)


# ── Admin-gated API docs ───────────────────────────────────────────────
# Same JSON check_api_contract.py and CI use offline (via `import main` +
# app.openapi()) -- this just serves that same document, and the two
# rendered UIs on top of it, only to an authenticated admin.

@app.get("/openapi.json", include_in_schema=False)
async def get_openapi_schema(_admin: dict = Depends(require_role("admin"))):
    return JSONResponse(app.openapi())


@app.get("/docs", include_in_schema=False)
async def get_docs(_admin: dict = Depends(require_role("admin"))):
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} — Swagger UI")


@app.get("/redoc", include_in_schema=False)
async def get_redoc(_admin: dict = Depends(require_role("admin"))):
    return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} — ReDoc")


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