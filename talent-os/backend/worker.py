"""
Talent OS — ARQ background worker (root docker-compose.yml `worker` service).

Runs against the `redis` service added alongside it. Two jobs today:

  - send_email_job: queue wrapper around services/mailer.send(). Existing
    call sites are NOT wired through this yet (mailer.send is called
    directly everywhere) -- queueing is opt-in and can be flipped on a
    call site at a time later without touching this file.
  - email_log_retention: daily cron (04:00 UTC) that deletes email_log rows
    older than 365 days (the M2 follow-up from the mailer PR).

DB pool lifecycle mirrors main.py's lifespan (core.database.get_pool /
close_pool) -- same pattern, separate process, separate pool.
"""
import logging
from datetime import datetime, timedelta, timezone

from arq import cron
from arq.connections import RedisSettings

from core.config import settings
from core.database import close_pool, execute, get_pool
from services import mailer

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("talent_os.worker")

EMAIL_LOG_RETENTION_DAYS = 365


# ── Jobs ──────────────────────────────────────────────────────────────────

async def send_email_job(
    ctx,
    to: str,
    template: str,
    mail_ctx: dict,
    subject: str = None,
    related_user_id: int = None,
) -> bool:
    """Render `template` with `mail_ctx` and send it to `to`, via the same
    services/mailer.send() that direct call sites use -- same logging,
    same fallback chain, same header-injection guard."""
    ok = await mailer.send(to, template, mail_ctx, subject=subject, related_user_id=related_user_id)
    if not ok:
        logger.warning("worker: send_email_job failed for to=%r template=%r", to, template)
    return ok


async def email_log_retention(ctx) -> int:
    """Delete email_log rows older than EMAIL_LOG_RETENTION_DAYS. Returns
    (and logs) the number of rows deleted."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=EMAIL_LOG_RETENTION_DAYS)
    result = await execute("DELETE FROM email_log WHERE created_at < $1", cutoff)
    # asyncpg's execute() returns a command tag like "DELETE 42".
    try:
        deleted = int(result.strip().split()[-1])
    except (ValueError, IndexError):
        deleted = 0
    logger.info(
        "worker: email_log_retention deleted %d row(s) older than %d days",
        deleted, EMAIL_LOG_RETENTION_DAYS,
    )
    return deleted


# ── Startup / shutdown ──────────────────────────────────────────────────────

async def startup(ctx):
    logger.info("Talent OS worker starting up...")
    await get_pool()


async def shutdown(ctx):
    logger.info("Talent OS worker shutting down...")
    await close_pool()


# ── ARQ settings ──────────────────────────────────────────────────────────

class WorkerSettings:
    functions = [send_email_job]
    cron_jobs = [
        cron(email_log_retention, hour=4, minute=0, run_at_startup=False),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    # Default is 3600s -- too infrequent for the compose healthcheck
    # (`arq --check`, which reads this key) to mean anything for the first
    # hour of a fresh container's life.
    health_check_interval = 60
