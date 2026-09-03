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
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import settings
from core.database import fetch_all, fetch_one, fetch_val, execute
from core import retention
from services.apollo_client import ApolloClient
from services import outreach_ai
from services import harvest as harvest_service

logger = logging.getLogger("talent_os.scheduler")

TIMEZONE = "Europe/Amsterdam"

# uvicorn runs this app with --workers 4 (talent-os/Dockerfile), and each
# worker process starts its own AsyncIOScheduler — without this lock every
# job would run once per worker (3-4x/day instead of once). A Postgres
# session-level advisory lock, held on a dedicated connection for the app's
# lifetime, ensures only one worker actually starts the scheduler.
SCHEDULER_LOCK_KEY = 911911

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

# Held open for the app's lifetime if this worker wins the advisory lock —
# deliberately NOT a pooled connection, so it's never returned/reused and
# the lock stays held until the process closes it (or dies).
_lock_conn: Optional[asyncpg.Connection] = None


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
    # security-auditor follow-up (WS-E.8 MEDIUM): this cron job is also
    # reachable manually via POST /api/v1/admin/outreach/run/sourcing
    # (routers/outreach.py's JOBS_BY_NAME dispatch) -- checking only the
    # DB flag here (which defaults to *enabled* when unset) let an admin
    # trigger a live Apollo call even with the env-level master switch
    # (APOLLO_SYNC_ENABLED) left at its safe default. Reuse
    # harvest_service._apollo_sync_enabled(), which checks both.
    if not await harvest_service._apollo_sync_enabled():
        logger.info("apollo_search_and_sync: disabled (apollo_sync_enabled), skipping")
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
                    logger.exception(
                        "apollo_search_and_sync: insert failed for apollo person %s",
                        person.get("id"),
                    )
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
    # security-auditor follow-up (WS-E.8 MEDIUM) -- see apollo_search_and_sync
    # above: also reachable via POST /api/v1/admin/outreach/run/enrich.
    if not await harvest_service._apollo_sync_enabled():
        logger.info("apollo_enrich_batch: disabled (apollo_sync_enabled), skipping")
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

    if not await _flag_enabled("matching_enabled"):
        logger.info("matching: disabled via system_settings, skipping")
        return {"status": "skipped", "reason": "matching_enabled=false"}

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


# ── Job 5: Weekly (Mon 05:00) — Draft a blog post ───────────────────────

BLOG_TOPICS = [
    "Salaristrends embedded software Brainport",
    "Zo verloopt een technische screening bij GSP",
    "Hiring-tijdlijnen voor C++ engineers in Nederland",
    "Carrièreswitch naar mechatronica",
    "Cybersecurity-talent vinden in Brainport",
    "Interviewvoorbereiding voor embedded engineers",
]


async def draft_blog_post() -> dict:
    """Draft a new blog post from the next topic in BLOG_TOPICS (rotating,
    tracked via the system_settings 'blog_topic_index' key) and store it as
    status='draft'. NEVER publishes — a human must publish via
    routers/blog_admin.py before it appears on the public site."""
    if not await _flag_enabled("blog_drafting_enabled"):
        logger.info("draft_blog_post: disabled via system_settings, skipping")
        return {"status": "skipped", "reason": "blog_drafting_enabled=false"}

    raw_index = await fetch_val("SELECT value FROM system_settings WHERE key = $1", "blog_topic_index")
    try:
        index = int(raw_index) if raw_index is not None else 0
    except (TypeError, ValueError):
        index = 0
    index = index % len(BLOG_TOPICS)

    topic = BLOG_TOPICS[index]
    next_index = (index + 1) % len(BLOG_TOPICS)

    try:
        draft = await outreach_ai.draft_blog(topic)
    except Exception:
        logger.exception("draft_blog_post: draft_blog failed for topic=%s", topic)
        return {"status": "failed", "topic": topic}

    slug = draft["slug"]
    existing = await fetch_val("SELECT id FROM blog_posts WHERE slug = $1", slug)
    if existing:
        slug = f"{slug}-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

    await execute(
        """INSERT INTO blog_posts
           (slug, title_nl, title_en, excerpt_nl, excerpt_en, body_nl, body_en,
            tags, read_time_min, status, ai_model)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'draft',$10)""",
        slug, draft["title_nl"], draft["title_en"], draft["excerpt_nl"], draft["excerpt_en"],
        draft["body_nl"], draft["body_en"], draft["tags"], draft["read_time_min"],
        settings.openrouter_chat_model,
    )

    await execute(
        """INSERT INTO system_settings (key, value) VALUES ($1, $2)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
        "blog_topic_index", str(next_index),
    )

    logger.info("draft_blog_post: drafted slug=%s topic=%s", slug, topic)
    return {"status": "success", "slug": slug, "topic": topic}


# ── Job 6: daily 04:00 — retention purge (WS-E.8) ───────────────────────
#
# core/retention.py is the single source of truth for the table (rows,
# anchor columns, actions). This module only orchestrates: for each row
# that is schema_ready and has a category handler below, count matching
# rows and, when actually purging, act on them via the same
# erase_person()-style logic (anonymise) or a plain DELETE (hard_delete)
# the table calls for. A row that is not schema_ready or has no handler
# (retain/infra_only categories) is reported but never queried or touched
# — see core/retention.py's docstring for why each of those isn't
# actionable yet.
#
# HARD RULE (WS-E.8 task): this job must never delete/anonymise anything
# in dry_run=True mode — that mode issues reads only (fetch_all/fetch_one),
# never execute(). The daily cron always calls it with
# dry_run=not settings.retention_purge_enabled, so a fresh/staging deploy
# (RETENTION_PURGE_ENABLED unset/false) only ever logs counts.

async def _count_sourced_no_response(lawful_basis: str) -> list:
    # security-auditor follow-up (WS-E.8): status='sourced' alone isn't
    # proof of "no reaction" -- a candidate can pick up a match, a
    # pipeline entry, a reply, or a portal account without candidates.status
    # ever being written past 'sourced' by any current code path. The four
    # NOT EXISTS guards in retention.SOURCED_NO_RESPONSE_SQL make "no
    # reaction" check the actual signal tables instead of trusting one
    # column. That query lives in core/retention.py (not duplicated here)
    # so the selector this job runs and the one core/retention.py
    # documents/tests can never drift apart.
    return await fetch_all(retention.SOURCED_NO_RESPONSE_SQL, lawful_basis)


async def _purge_sourced_no_response(lawful_basis: str, reason: str) -> int:
    from routers.gdpr import erase_person

    rows = await _count_sourced_no_response(lawful_basis)
    for row in rows:
        if row["email"]:
            await erase_person(row["email"], actor_id=None, reason=reason)
    return len(rows)


async def _count_talentpool_expired() -> list:
    # WS-C.17: mirrors _count_sourced_no_response -- reads the shared
    # selector from core/retention.py so the query this job runs and the
    # one that module documents can never drift apart.
    return await fetch_all(retention.TALENTPOOL_EXPIRED_SQL)


async def _purge_talentpool_expired(reason: str) -> int:
    from routers.gdpr import erase_person

    rows = await _count_talentpool_expired()
    for row in rows:
        if row["email"]:
            await erase_person(row["email"], actor_id=None, reason=reason)
    return len(rows)


async def _count_prospect_no_response() -> list:
    # security-auditor follow-up (LOW): no code path updates
    # client_prospects.status once a draft is sent or answered (routers/
    # outreach.py never writes back to client_prospects) -- status='new'
    # therefore does NOT by itself mean "no reaction" here either, same
    # gap as sourced_no_response above. outreach_drafts has no replied_at
    # column of its own (only outreach_messages does, once a draft is
    # approved and actually sent), so the reply guard in
    # retention.PROSPECT_NO_RESPONSE_SQL runs against outreach_messages; a
    # sent-but-not-yet-replied draft is still caught by the second NOT
    # EXISTS so a prospect mid-conversation isn't wiped out from under an
    # in-flight thread. client_prospects.status still only ever moves by
    # manual admin action (no automatic transition exists anywhere in
    # this codebase) -- this guard compensates for that gap rather than
    # fixing it.
    return await fetch_all(retention.PROSPECT_NO_RESPONSE_SQL)


async def _purge_prospect_no_response() -> int:
    rows = await _count_prospect_no_response()
    ids = [r["id"] for r in rows]
    if ids:
        await execute("DELETE FROM client_prospects WHERE id = ANY($1::int[])", ids)
    return len(rows)


async def _count_leads_quiz() -> int:
    quiz = await fetch_all("SELECT id FROM quiz_submissions WHERE created_at <= (NOW() - INTERVAL '12 months')")
    contact = await fetch_all("SELECT id FROM contact_submissions WHERE created_at <= (NOW() - INTERVAL '12 months')")
    return len(quiz) + len(contact)


async def _purge_leads_quiz() -> int:
    quiz = await fetch_all("SELECT id FROM quiz_submissions WHERE created_at <= (NOW() - INTERVAL '12 months')")
    contact = await fetch_all("SELECT id FROM contact_submissions WHERE created_at <= (NOW() - INTERVAL '12 months')")
    if quiz:
        await execute("DELETE FROM quiz_submissions WHERE id = ANY($1::int[])", [r["id"] for r in quiz])
    if contact:
        await execute("DELETE FROM contact_submissions WHERE id = ANY($1::int[])", [r["id"] for r in contact])
    return len(quiz) + len(contact)


async def _category_result(row: "retention.RetentionRow", dry_run: bool) -> dict:
    """Count (dry_run) or count-then-act (not dry_run) for one retention
    table row. Never queries a column that doesn't exist yet
    (schema_ready=False short-circuits before any DB call) and never
    calls execute() when dry_run=True."""
    if row.action in ("retain", "infra_only"):
        return {"key": row.key, "status": "not_applicable", "count": None}
    if not row.schema_ready:
        return {"key": row.key, "status": "schema_not_ready", "count": None}

    try:
        if row.key == "sourced_no_response":
            if dry_run:
                count = len(await _count_sourced_no_response("gerechtvaardigd_belang"))
            else:
                count = await _purge_sourced_no_response(
                    "gerechtvaardigd_belang", f"retention_purge:{row.key}",
                )
        elif row.key == "referral":
            if dry_run:
                count = len(await _count_sourced_no_response("toestemming_referral"))
            else:
                count = await _purge_sourced_no_response(
                    "toestemming_referral", f"retention_purge:{row.key}",
                )
        elif row.key == "talentpool_consent":
            if dry_run:
                count = len(await _count_talentpool_expired())
            else:
                count = await _purge_talentpool_expired(f"retention_purge:{row.key}")
        elif row.key == "prospect_no_response":
            count = len(await _count_prospect_no_response()) if dry_run else await _purge_prospect_no_response()
        elif row.key == "leads_quiz":
            count = await _count_leads_quiz() if dry_run else await _purge_leads_quiz()
        else:
            return {"key": row.key, "status": "no_handler", "count": None}
    except Exception:
        logger.exception("run_retention_purge: category %s failed", row.key)
        return {"key": row.key, "status": "error", "count": None}

    return {"key": row.key, "status": "counted" if dry_run else "purged", "count": count}


async def run_retention_purge(dry_run: bool = True) -> dict:
    """WS-E.8. Walks core/retention.RETENTION_TABLE and, per category,
    either counts matching rows (dry_run=True — no writes at all, ever)
    or purges them (dry_run=False — anonymise via erase_person()-style
    logic or hard-delete, per the row's `action`) and writes one
    audit_log row per *purged* category with counts only — never an
    e-mail address or name (json.dumps, never a raw dict — commit
    72b4bcd)."""
    results = []
    for row in retention.RETENTION_TABLE:
        result = await _category_result(row, dry_run)
        results.append(result)
        if not dry_run and result["status"] == "purged":
            await execute(
                "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
                "VALUES ($1, NULL, $2, NULL, $3::jsonb)",
                "retention_purge", "retention_category",
                json.dumps({"category": row.key, "count": result["count"], "action": row.action}),
            )

    logger.info(
        "run_retention_purge: dry_run=%s results=%s",
        dry_run, {r["key"]: (r["status"], r["count"]) for r in results},
    )
    return {"dry_run": dry_run, "categories": results}


async def retention_purge_job() -> dict:
    """Cron entry point — always defers to the RETENTION_PURGE_ENABLED env
    flag (core/config.py), never runs a real purge just because the daily
    trigger fired. The admin endpoint (routers/retention_admin.py) is the
    only way to force a real run regardless of this flag, and even there
    only with confirm='PURGE'."""
    return await run_retention_purge(dry_run=not settings.retention_purge_enabled)


# ── Scheduler lifecycle ──────────────────────────────────────────────────

async def start_scheduler() -> None:
    """Acquire the cross-worker advisory lock and, if won, register the four
    daily jobs and start the scheduler. Safe to call once per worker at app
    startup (main.py lifespan) — only the worker that wins the lock actually
    starts APScheduler; the others skip it entirely so jobs run exactly
    once, not once per uvicorn worker."""
    global _lock_conn

    if scheduler.running:
        return

    _lock_conn = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )
    got_lock = await _lock_conn.fetchval("SELECT pg_try_advisory_lock($1)", SCHEDULER_LOCK_KEY)
    if not got_lock:
        logger.info("scheduler: another worker holds the lock, not starting")
        await _lock_conn.close()
        _lock_conn = None
        return

    # Apollo sourcing/enrichment jobs are off by default (settings.apollo_sync_enabled,
    # core/config.py) -- they are not even registered with APScheduler unless
    # explicitly enabled via env. The per-run system_settings.apollo_sync_enabled
    # DB flag (_flag_enabled, checked inside each job) is a secondary, admin-editable
    # switch on top of this, not a substitute for it.
    apollo_jobs_registered = 0
    if settings.apollo_sync_enabled:
        scheduler.add_job(
            apollo_search_and_sync, CronTrigger(hour=6, minute=0),
            id="apollo_search_and_sync", replace_existing=True,
        )
        scheduler.add_job(
            apollo_enrich_batch, CronTrigger(hour=6, minute=30),
            id="apollo_enrich_batch", replace_existing=True,
        )
        apollo_jobs_registered = 2
    else:
        logger.info("scheduler: apollo_sync_enabled=false, not registering Apollo jobs")

    scheduler.add_job(
        matching, CronTrigger(hour=7, minute=0),
        id="matching", replace_existing=True,
    )
    scheduler.add_job(
        draft_outreach, CronTrigger(hour=7, minute=30),
        id="draft_outreach", replace_existing=True,
    )
    scheduler.add_job(
        draft_blog_post, CronTrigger(day_of_week="mon", hour=5, minute=0),
        id="draft_blog_post", replace_existing=True,
    )
    scheduler.add_job(
        retention_purge_job, CronTrigger(hour=4, minute=0),
        id="retention_purge", replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "scheduler: started with %s daily jobs + 1 weekly job (Europe/Amsterdam)",
        3 + apollo_jobs_registered,
    )


async def shutdown_scheduler() -> None:
    """Stop the scheduler cleanly and release the advisory lock (if this
    worker held it) on app shutdown."""
    global _lock_conn

    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("scheduler: stopped")

    if _lock_conn is not None:
        try:
            await _lock_conn.execute("SELECT pg_advisory_unlock($1)", SCHEDULER_LOCK_KEY)
        except Exception:
            logger.exception("scheduler: failed to release advisory lock")
        finally:
            await _lock_conn.close()
            _lock_conn = None


JOBS_BY_NAME = {
    "sourcing": apollo_search_and_sync,
    "enrich": apollo_enrich_batch,
    "matching": matching,
    "drafting": draft_outreach,
    "blog": draft_blog_post,
    "retention_purge": retention_purge_job,
    # Manual-trigger only — deliberately NOT added to start_scheduler()'s
    # cron jobs below. One-shot Apollo bulk-harvest (services/harvest.py)
    # and its outreach-draft catch-up, both run via routers/outreach.py's
    # POST /run/{job_name}.
    "harvest": harvest_service.harvest_all,
    "morningdrafts": harvest_service.morning_drafts,
    "enrichmatched": harvest_service.enrich_matched,
    "backfillids": harvest_service.backfill_prospect_ids,
}
