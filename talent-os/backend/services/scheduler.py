"""
Talent OS — APScheduler-driven sourcing + outreach draft pipeline.

Replaces the Celery-beat-based tasks/sourcing.py with plain async jobs run
in-process via AsyncIOScheduler, matching the "no Celery/Redis required"
pattern already used by routers/matches.py's background-task matching.

Every job is gated by a system_settings flag it checks first — a missing
flag is treated as enabled ('true'). Jobs never send anything: outreach
drafting only ever writes rows to outreach_drafts with status='draft'.
A human must approve a draft via routers/outreach.py before it is sent.
"""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import settings
from core.database import fetch_all, fetch_one, fetch_val, execute
from services.apollo_client import ApolloClient
from services import outreach_ai

logger = logging.getLogger("talent_os.scheduler")

TIMEZONE = "Europe/Amsterdam"

SOURCING_TITLES = [
    "Embedded Software Engineer",
    "C++ Developer",
    "Mechatronics Engineer",
    "Cybersecurity Engineer",
]
SOURCING_LOCATION = "Eindhoven, Netherlands"

APOLLO_SEARCH_CAP = 25
APOLLO_ENRICH_CAP = 10
DRAFT_OUTREACH_CAP = 10

scheduler = AsyncIOScheduler(timezone=TIMEZONE)


async def _flag_enabled(key: str) -> bool:
    """Read a system_settings boolean flag. Missing key == enabled."""
    value = await fetch_val("SELECT value FROM system_settings WHERE key = $1", key)
    if value is None:
        return True
    return str(value).strip().lower() == "true"


# ── Job 1: 06:00 — Apollo search + sync ─────────────────────────────────

async def apollo_search_and_sync() -> dict:
    """Search Apollo.io for candidates matching our target titles/region and
    upsert new ones into candidates. Skips duplicates by email. Capped at
    APOLLO_SEARCH_CAP inserts per run."""
    if not await _flag_enabled("apollo_sync_enabled"):
        logger.info("apollo_search_and_sync: disabled via system_settings, skipping")
        return {"status": "skipped", "reason": "apollo_sync_enabled=false"}

    if not settings.apollo_api_key:
        logger.warning("apollo_search_and_sync: Apollo API key not configured, skipping")
        return {"status": "skipped", "reason": "Apollo API key not configured"}

    client = ApolloClient(api_key=settings.apollo_api_key)
    inserted = 0
    searched = 0
    try:
        for title in SOURCING_TITLES:
            if inserted >= APOLLO_SEARCH_CAP:
                break
            try:
                result = await client.search_people(
                    title=title, location=SOURCING_LOCATION,
                    limit=min(25, APOLLO_SEARCH_CAP - inserted),
                )
            except Exception:
                logger.exception("apollo_search_and_sync: search failed for title=%s", title)
                continue

            people = result.get("people", []) or result.get("data", []) or []
            searched += len(people)

            for person in people:
                if inserted >= APOLLO_SEARCH_CAP:
                    break

                name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
                email = person.get("email") or person.get("personal_email") or ""
                if not name or not email:
                    continue

                company = ""
                if person.get("employment_history"):
                    company = person["employment_history"][0].get("company_name", "")

                try:
                    row = await fetch_one(
                        """INSERT INTO candidates
                           (full_name, email, current_company, current_title, location,
                            skills, source, sourced_by_agent, is_passive)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                           ON CONFLICT (email) DO NOTHING
                           RETURNING id""",
                        name, email, company,
                        person.get("title", title),
                        person.get("city", person.get("location", SOURCING_LOCATION)),
                        [s.get("name", "") for s in person.get("skills", [])],
                        "apollo", "scheduler-apollo-sync", True,
                    )
                except Exception:
                    logger.exception("apollo_search_and_sync: insert failed for %s", email)
                    continue

                if row:
                    inserted += 1

        logger.info("apollo_search_and_sync: searched=%s inserted=%s", searched, inserted)
        return {"status": "success", "searched": searched, "inserted": inserted}
    finally:
        await client.close()


# ── Job 2: 06:30 — Apollo enrichment ────────────────────────────────────

async def apollo_enrich_batch() -> dict:
    """Enrich candidates that have a linkedin_url but no email yet, capped
    at APOLLO_ENRICH_CAP per run."""
    if not await _flag_enabled("apollo_sync_enabled"):
        logger.info("apollo_enrich_batch: disabled via system_settings, skipping")
        return {"status": "skipped", "reason": "apollo_sync_enabled=false"}

    if not settings.apollo_api_key:
        logger.warning("apollo_enrich_batch: Apollo API key not configured, skipping")
        return {"status": "skipped", "reason": "Apollo API key not configured"}

    rows = await fetch_all(
        "SELECT id, linkedin_url FROM candidates "
        "WHERE email IS NULL AND linkedin_url IS NOT NULL LIMIT $1",
        APOLLO_ENRICH_CAP,
    )

    client = ApolloClient(api_key=settings.apollo_api_key)
    enriched = 0
    try:
        for row in rows:
            try:
                result = await client.enrich_person(linkedin_url=row["linkedin_url"])
                person = result.get("person", result.get("data", {})) or {}
                email = person.get("email") or person.get("personal_email") or ""
                if email:
                    await execute(
                        "UPDATE candidates SET email = $1, updated_at = NOW() WHERE id = $2",
                        email, row["id"],
                    )
                    enriched += 1
            except Exception:
                logger.exception("apollo_enrich_batch: enrich failed for candidate %s", row["id"])
                continue

        logger.info("apollo_enrich_batch: processed=%s enriched=%s", len(rows), enriched)
        return {"status": "success", "processed": len(rows), "enriched": enriched}
    finally:
        await client.close()


# ── Job 3: 07:00 — Matching for all open jobs ───────────────────────────

async def matching() -> dict:
    """Run semantic matching for every open job order."""
    from routers.matches import _run_matching_for_job

    jobs = await fetch_all(
        "SELECT id FROM job_orders WHERE status = 'open' AND deleted_at IS NULL",
    )
    for j in jobs:
        try:
            await _run_matching_for_job(j["id"])
        except Exception:
            logger.exception("matching: failed for job %s", j["id"])

    logger.info("matching: ran for %s open jobs", len(jobs))
    return {"status": "success", "job_count": len(jobs)}


# ── Job 4: 07:30 — Draft outreach ───────────────────────────────────────

async def draft_outreach() -> dict:
    """For candidates matched to open jobs in the last 24h without an
    existing draft, generate an AI draft outreach email and store it as
    status='draft'. NEVER sends — approval happens via routers/outreach.py.
    Capped at DRAFT_OUTREACH_CAP drafts per run."""
    if not await _flag_enabled("outreach_drafting_enabled"):
        logger.info("draft_outreach: disabled via system_settings, skipping")
        return {"status": "skipped", "reason": "outreach_drafting_enabled=false"}

    candidates = await fetch_all(
        """SELECT m.candidate_id, m.job_id, m.match_score,
                  c.full_name, c.email, c.current_company,
                  j.title AS job_title, j.description AS job_description,
                  cl.company_name AS job_company
           FROM matches m
           JOIN candidates c ON c.id = m.candidate_id
           JOIN job_orders j ON j.id = m.job_id
           LEFT JOIN clients cl ON cl.id = j.client_id
           WHERE m.status = 'suggested'
             AND j.status = 'open'
             AND j.deleted_at IS NULL
             AND m.created_at >= NOW() - INTERVAL '24 hours'
             AND c.email IS NOT NULL
             AND NOT EXISTS (
                 SELECT 1 FROM outreach_drafts d
                 WHERE d.target_email = c.email AND d.job_id = m.job_id
             )
           ORDER BY m.match_score DESC
           LIMIT $1""",
        DRAFT_OUTREACH_CAP,
    )

    drafted = 0
    for row in candidates:
        try:
            draft = await outreach_ai.draft_email(
                target={
                    "name": row["full_name"],
                    "company": row["current_company"],
                },
                context={
                    "job_title": row["job_title"],
                    "job_company": row["job_company"],
                    "job_description": row["job_description"],
                },
                language="nl",
            )
            await execute(
                """INSERT INTO outreach_drafts
                   (target_type, target_id, target_email, target_name, company,
                    job_id, channel, language, subject, body, ai_model, status)
                   VALUES ($1,$2,$3,$4,$5,$6,'email','nl',$7,$8,$9,'draft')""",
                "candidate", row["candidate_id"], row["email"], row["full_name"],
                row["current_company"], row["job_id"],
                draft["subject"], draft["body"], settings.openrouter_chat_model,
            )
            drafted += 1
        except Exception:
            logger.exception("draft_outreach: failed for candidate %s / job %s",
                              row["candidate_id"], row["job_id"])
            continue

    logger.info("draft_outreach: candidates_considered=%s drafted=%s", len(candidates), drafted)
    return {"status": "success", "considered": len(candidates), "drafted": drafted}


# ── Scheduler lifecycle ──────────────────────────────────────────────────

def start_scheduler() -> None:
    """Register the four daily jobs and start the scheduler. Safe to call
    once at app startup (main.py lifespan)."""
    if scheduler.running:
        return

    scheduler.add_job(
        apollo_search_and_sync, CronTrigger(hour=6, minute=0),
        id="apollo_search_and_sync", replace_existing=True,
    )
    scheduler.add_job(
        apollo_enrich_batch, CronTrigger(hour=6, minute=30),
        id="apollo_enrich_batch", replace_existing=True,
    )
    scheduler.add_job(
        matching, CronTrigger(hour=7, minute=0),
        id="matching", replace_existing=True,
    )
    scheduler.add_job(
        draft_outreach, CronTrigger(hour=7, minute=30),
        id="draft_outreach", replace_existing=True,
    )

    scheduler.start()
    logger.info("scheduler: started with 4 daily jobs (Europe/Amsterdam)")


def shutdown_scheduler() -> None:
    """Stop the scheduler cleanly on app shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler: stopped")


JOBS_BY_NAME = {
    "sourcing": apollo_search_and_sync,
    "enrich": apollo_enrich_batch,
    "matching": matching,
    "drafting": draft_outreach,
}
