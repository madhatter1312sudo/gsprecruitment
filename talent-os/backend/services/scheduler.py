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
                    # security-audit follow-up (WS-E.8 retention-kolommen
                    # branch, fourth round): stamp pool_origin='apollo' here
                    # too (see services/harvest.py's harvest_candidates for
                    # the fuller comment) -- routers/retention_admin.py's
                    # Apollo-pool-purge selector reads this column and
                    # otherwise never sees anything sourced after
                    # migrations/022_apollo_pool_flag.py's one-time backfill.
                    row = await fetch_one(
                        """INSERT INTO candidates
                           (full_name, email, current_company, current_title, location,
                            skills, source, sourced_by_agent, is_passive, pool_origin)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'apollo')
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
             AND c.deleted_at IS NULL
             AND c.consent_withdrawn_at IS NULL
             AND NOT EXISTS (
                 SELECT 1 FROM outreach_drafts d
                 WHERE d.target_email = c.email AND d.job_id = m.job_id
             )
           ORDER BY m.match_score DESC
           LIMIT $1""",
        DRAFT_OUTREACH_CAP,
    )

    drafted = 0
    # FIX 5 (chief-of-staff, ai-pseudonimisering branch): a row the model
    # structurally refuses (leaked placeholder, or draft_email() itself
    # raising DraftGenerationError) used to disappear into a log line with
    # no signal in the returned dict -- if the model started mangling the
    # placeholder on every row, drafted would silently drop to zero with
    # nothing distinguishing "nothing to draft" from "everything refused".
    refused = 0
    # FIX 5 follow-up (chief-of-staff, ai-pseudonimisering branch): the
    # generic `except Exception: continue` below swallowed everything that
    # was NOT a recognised model refusal -- an HTTP error, unparseable JSON
    # from the model, or a failing INSERT -- without incrementing anything.
    # That is the same blindness refused= was added to fix: if the model
    # started returning structurally broken JSON (a different failure mode
    # than the placeholder-leak/DraftGenerationError cases above),
    # drafted/refused would both stay flat while errors silently absorbed
    # every row. errors= makes that failure mode visible in the same dict.
    errors = 0
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
            if outreach_ai.contains_placeholder_leak(draft["subject"], draft["body"]):
                logger.error(
                    "draft_outreach: refusing to store draft with leaked name "
                    "placeholder for candidate %s / job %s", row["candidate_id"], row["job_id"],
                )
                refused += 1
                continue
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
        except outreach_ai.DraftGenerationError:
            logger.error(
                "draft_outreach: model refused to draft (placeholder used the "
                "wrong number of times) for candidate %s / job %s",
                row["candidate_id"], row["job_id"],
            )
            refused += 1
            continue
        except Exception:
            logger.exception("draft_outreach: failed for candidate %s / job %s",
                              row["candidate_id"], row["job_id"])
            errors += 1
            continue

    logger.info("draft_outreach: candidates_considered=%s drafted=%s refused=%s errors=%s",
                 len(candidates), drafted, refused, errors)
    return {
        "status": "success", "considered": len(candidates),
        "drafted": drafted, "refused": refused, "errors": errors,
    }


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


# ── Job 6: monthly (1st, 04:00) — retention review queue (WS-E.10) ──────
#
# Owner decision (retention-kolommen branch, fifth round): after four
# rounds of guard fixes it was clear every "no reaction" signal this table
# can check lives in a channel this backend does not reliably record (a
# phone call, a LinkedIn thread, a reply landing in someone's own
# mailbox). This job therefore never deletes or anonymises anything by
# itself any more, at any confidence level -- it only queues who
# core/retention.py's guarded selectors say is due into
# retention_review_items (migrations/036_retention_review_queue.py) for a
# human to approve or reject, once a month
# (GET/POST /api/v1/admin/retention/review*, routers/retention_admin.py).
# core/retention.py's selectors and guards (who ends up on the list) are
# entirely unchanged by this -- see that module for those.
#
# The _count_* functions below are unchanged from the old purge job (same
# guarded selectors, same "read the shared query, never a local copy"
# discipline) -- they are still what both this review job and
# GET /api/v1/admin/retention/table's summary read. What is gone is every
# _purge_* sibling that used to call erase_person()/execute() straight
# off of one of these counts -- see routers/retention_admin.py's module
# docstring for where an actual purge happens now (only from an approved
# retention_review_items row).

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


async def _count_talentpool_expired() -> list:
    # WS-C.17: mirrors _count_sourced_no_response -- reads the shared
    # selector from core/retention.py so the query this job runs and the
    # one that module documents can never drift apart.
    return await fetch_all(retention.TALENTPOOL_EXPIRED_SQL)


# ── rejected_applicant / prospect_responding / portal_account_inactive ──
# (WS-E.8 follow-up, migrations/032_retention_anchor_columns.py) -- same
# pattern as sourced_no_response/talentpool_expired above: the guarded
# selector lives once in core/retention.py, this module only counts
# against it.

async def _count_rejected_applicants() -> list:
    return await fetch_all(retention.REJECTED_APPLICANT_SQL)


async def _count_prospect_responding() -> list:
    return await fetch_all(retention.PROSPECT_RESPONDING_SQL)


async def _count_portal_account_inactive() -> list:
    return await fetch_all(retention.PORTAL_ACCOUNT_INACTIVE_SQL)


# ── Talentpool renewal reminder (WS-C.17, security-audit follow-up H3c) ──
#
# One e-mail, sent once per consent cycle, 30 days before
# consent_talentpool_until -- consent_reminder_sent_at (NULL again on any
# fresh consent write, see routers/candidate.py|public.py|admin.py) is
# what makes this idempotent per cycle: a candidate who renews immediately
# drops out of this selector (their consent_talentpool_until moves 12
# months out again, past the 30-day window) even if this job somehow ran
# twice on the same day.
TALENTPOOL_REMINDER_SQL = """
    SELECT id, email, full_name FROM candidates
    WHERE lawful_basis = 'opt_in_talentpool'
      AND consent_talentpool_until IS NOT NULL
      AND consent_talentpool_until > NOW()
      AND consent_talentpool_until <= (NOW() + INTERVAL '30 days')
      AND consent_reminder_sent_at IS NULL
      AND deleted_at IS NULL AND email IS NOT NULL
"""


def _talentpool_reminder_email_body(name: str) -> str:
    link = "https://gsprecruitment.nl/kandidaten#talentpoolOptin"
    greeting = name or ""
    return f"""Beste {greeting},

Je staat in de talentpool van GSP Recruitment. Over ongeveer een maand loopt je toestemming af (bewaartermijn 12 maanden). Wil je verlengd blijven staan, meld je dan hier opnieuw aan:
{link}

Doe je niets, dan verwijderen wij je gegevens uit de talentpool zodra de termijn is verstreken.

Met vriendelijke groet,
GSP Recruitment
info@gsprecruitment.nl

---

Dear {greeting},

You are in GSP Recruitment's talent pool. Your consent expires in about a month (12-month retention period). To stay in the pool, sign up again here:
{link}

If you do nothing, we will remove your data from the talent pool once the period has passed.

Kind regards,
GSP Recruitment
info@gsprecruitment.nl
"""


async def talentpool_reminder_job() -> dict:
    """Daily cron entry point (04:30). Sends one renewal e-mail per
    candidate whose talentpool consent is due to expire within 30 days
    and who hasn't already been reminded this cycle, then stamps
    consent_reminder_sent_at so the same person is never reminded twice
    for the same consent_talentpool_until."""
    from services.email_service import email_service

    rows = await fetch_all(TALENTPOOL_REMINDER_SQL)
    sent = 0
    for row in rows:
        ok = await email_service.send_email(
            to_email=row["email"],
            subject="Je talentpool-aanmelding loopt bijna af — GSP Recruitment",
            body_text=_talentpool_reminder_email_body(row.get("full_name") or ""),
        )
        if ok:
            await execute(
                "UPDATE candidates SET consent_reminder_sent_at = NOW() WHERE id = $1", row["id"],
            )
            sent += 1
        else:
            logger.warning("talentpool_reminder_job: failed to send reminder to candidate id=%s", row["id"])
    logger.info("talentpool_reminder_job: candidates_due=%s sent=%s", len(rows), sent)
    return {"candidates_due": len(rows), "sent": sent}


# ── talentpool_optin_requests retention (WS-C.17, security-audit M2) ─────
#
# This table (migrations/030_talentpool_consent.py) holds only e-mail +
# token hash for the public double-opt-in flow -- an internal, non-public
# table, not a candidate profile, so it does not get its own row in
# core/retention.RETENTION_TABLE (that table's ten rows are code-tested
# against docs/VERWERKINGSREGISTER.md §1.4 / SOURCING-SOP.md §6 /
# website/privacy.html 1:1 -- adding an eleventh row would mean rewriting
# all three by hand for a table that isn't itself a candidate record).
# Documented instead in VERWERKINGSREGISTER.md §1.2 row 3. Purged here,
# alongside the documented categories but reported under its own key in
# run_retention_purge()'s result -- confirmed or not, 7 days is plenty
# for someone to click the link, and an unconfirmed pending row carries
# no consent to act on anyway.
TALENTPOOL_OPTIN_REQUESTS_STALE_SQL = """
    SELECT id FROM talentpool_optin_requests WHERE requested_at <= (NOW() - INTERVAL '7 days')
"""


async def _count_stale_talentpool_optin_requests() -> list:
    return await fetch_all(TALENTPOOL_OPTIN_REQUESTS_STALE_SQL)


async def _purge_stale_talentpool_optin_requests() -> int:
    rows = await _count_stale_talentpool_optin_requests()
    ids = [r["id"] for r in rows]
    if ids:
        await execute("DELETE FROM talentpool_optin_requests WHERE id = ANY($1::int[])", ids)
    return len(rows)


async def _count_prospect_no_response() -> list:
    # security-auditor follow-up (LOW): no code path updates
    # client_prospects.status once a draft is sent or answered (routers/
    # outreach.py never writes back to client_prospects) -- status='new'
    # therefore does NOT by itself mean "no reaction" here either, same
    # gap as sourced_no_response above. client_prospects.status still
    # only ever moves by manual admin action (no automatic transition
    # exists anywhere in this codebase) -- the guard in
    # retention.PROSPECT_NO_RESPONSE_SQL compensates for that gap rather
    # than fixing it, via the one candidate-side event this codebase
    # actually records: a sent outreach_drafts row, so a prospect
    # mid-conversation isn't wiped out from under an in-flight thread.
    #
    # chief-of-staff second FIX FIRST (WS-E.8 retention-kolommen branch):
    # that guard used to also carry a reply check against
    # outreach_messages.replied_at -- dead code, since outreach is
    # draft-only and nothing ever writes that column (a human sends from
    # their own mailbox; any reply lands there, not in this DB). Removed;
    # the sent-draft guard is the real, working signal.
    return await fetch_all(retention.PROSPECT_NO_RESPONSE_SQL)


async def talentpool_optin_requests_cleanup_job() -> dict:
    """Daily cron entry point (04:00). Unlike the ten retention-table rows
    above, talentpool_optin_requests (migrations/030_talentpool_consent.py)
    is not part of this PR's WS-E.10 redesign: it holds only e-mail + a
    token hash for the public double-opt-in flow, is purged purely on age
    (7 days -- see the constant's own comment above), and does not depend
    on any of the "did anything real happen" guards that motivated moving
    the other ten categories to a human-approved monthly review (there is
    no guard here that could be wrong about a missed signal, because there
    is no signal to miss: an unconfirmed opt-in link is either confirmed
    within 7 days or it isn't). It therefore keeps running automatically,
    same as before this branch."""
    count = await _purge_stale_talentpool_optin_requests()
    if count:
        await execute(
            "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
            "VALUES ($1, NULL, $2, NULL, $3::jsonb)",
            "retention_purge", "talentpool_optin_requests",
            json.dumps({"category": "talentpool_optin_requests", "count": count, "action": "hard_delete"}),
        )
    logger.info("talentpool_optin_requests_cleanup_job: purged=%s", count)
    return {"status": "purged", "count": count}


# ── Per-category live rows for the monthly review queue ─────────────────
#
# Table-name/e-mail-column-name lookups for the seven RETENTION_TABLE
# categories that share the CANDIDATE_NO_REACTION_GUARD_SQL-style guarded
# selectors above -- leads_quiz (two tables, no guard) and
# apollo_pool_purge (not a RETENTION_TABLE row at all) are handled
# separately in generate_retention_review() below.
_REVIEW_SUBJECT_TABLE = {
    "sourced_no_response": "candidates", "referral": "candidates",
    "talentpool_consent": "candidates", "rejected_applicant": "candidates",
    "portal_account_inactive": "users",
    "prospect_responding": "client_prospects", "prospect_no_response": "client_prospects",
}
_REVIEW_EMAIL_FIELD = {
    "sourced_no_response": "email", "referral": "email",
    "talentpool_consent": "email", "rejected_applicant": "email",
    "portal_account_inactive": "email",
    "prospect_responding": "contact_email", "prospect_no_response": "contact_email",
}


async def _live_rows_for_category(row: "retention.RetentionRow") -> list:
    """The exact same guarded selector the old purge job used to act on
    directly -- now only read, never acted on here. Returns [] for a
    category with no handler (there are none among the seven this is
    called for; kept defensive rather than letting a future new category
    silently fall through to no rows queued without a signal)."""
    if row.key == "sourced_no_response":
        return await _count_sourced_no_response("gerechtvaardigd_belang")
    if row.key == "referral":
        return await _count_sourced_no_response("toestemming_referral")
    if row.key == "talentpool_consent":
        return await _count_talentpool_expired()
    if row.key == "rejected_applicant":
        return await _count_rejected_applicants()
    if row.key == "prospect_responding":
        return await _count_prospect_responding()
    if row.key == "portal_account_inactive":
        return await _count_portal_account_inactive()
    if row.key == "prospect_no_response":
        return await _count_prospect_no_response()
    logger.warning("_live_rows_for_category: no handler for category %s", row.key)
    return []


async def _upsert_review_item(
    category: str, subject_table: str, subject_id: int, email: Optional[str],
    action: str, term_expired_at, signal_missing_nl: str,
) -> None:
    """Insert a fresh 'pending' review item, or reopen an existing
    'rejected' one -- WS-E.10's "iemand die hij niet goedkeurt, moet niet
    volgende maand opnieuw op de lijst staan zonder dat zichtbaar is dat
    hij eerder is overgeslagen" requirement. A 'purged' item is left alone
    (the person is gone, nothing to reopen); a 'no_longer_eligible' item
    reopens the same way a 'rejected' one does -- both mean "not currently
    being acted on", and this run's live selector just proved the subject
    is due again. UNIQUE(category, subject_table, subject_id)
    (migrations/036_retention_review_queue.py) is what makes this a
    genuine upsert rather than ever inserting a second, indistinguishable
    row for the same person."""
    await execute(
        """INSERT INTO retention_review_items
             (category, subject_table, subject_id, email, action, term_expired_at, signal_missing_nl)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           ON CONFLICT (category, subject_table, subject_id) DO UPDATE SET
             email = EXCLUDED.email,
             action = EXCLUDED.action,
             term_expired_at = EXCLUDED.term_expired_at,
             signal_missing_nl = EXCLUDED.signal_missing_nl,
             last_seen_at = NOW(),
             status = CASE
                 WHEN retention_review_items.status IN ('rejected', 'no_longer_eligible') THEN 'pending'
                 ELSE retention_review_items.status
             END,
             reappeared_after_rejection_at = CASE
                 WHEN retention_review_items.status = 'rejected'
                 THEN COALESCE(retention_review_items.reappeared_after_rejection_at, NOW())
                 ELSE retention_review_items.reappeared_after_rejection_at
             END""",
        category, subject_table, subject_id, email, action, term_expired_at, signal_missing_nl,
    )


async def _retire_stale_pending(category: str, subject_table: str, live_ids: list) -> None:
    """Whatever was 'pending' for this category+table last run but isn't
    in this run's live selector any more picked up a protective signal in
    the meantime -- mark it 'no_longer_eligible' (kept, not deleted, for
    the same visibility reason a rejection is kept) rather than silently
    leaving a stale row an admin could still approve into a purge of
    someone who is no longer actually due."""
    await execute(
        """UPDATE retention_review_items SET status = 'no_longer_eligible', last_seen_at = NOW()
           WHERE category = $1 AND subject_table = $2 AND status = 'pending'
             AND NOT (subject_id = ANY($3::int[]))""",
        category, subject_table, live_ids,
    )


async def generate_retention_review() -> dict:
    """WS-E.10 monthly job. Walks core/retention.RETENTION_TABLE's seven
    guarded, schema_ready anonymise/hard_delete categories (retain/
    infra_only rows are never actionable at all; see core/retention.py),
    plus leads_quiz (two tables, age-only) and apollo_pool_purge
    (VERWERKINGSREGISTER.md §2.6/§5.7, folded into this same queue --
    see routers/retention_admin.py's module docstring for why that used
    to be its own direct-delete endpoint and no longer is), and queues
    every row each one's selector currently returns into
    retention_review_items. Never touches the GDPR erasure routine and
    never deletes a candidate/prospect/user row -- read-only against
    every table except retention_review_items itself."""
    summary: dict = {}

    for row in retention.RETENTION_TABLE:
        if row.action not in ("anonymise", "hard_delete") or not row.schema_ready:
            continue  # retain/infra_only, or schema_not_ready -- see core/retention.py
        if row.key == "leads_quiz":
            continue  # spans two subtables with no shared guard -- handled separately below
        subject_table = _REVIEW_SUBJECT_TABLE[row.key]
        email_field = _REVIEW_EMAIL_FIELD[row.key]
        live_rows = await _live_rows_for_category(row)
        live_ids = [r["id"] for r in live_rows]
        for r in live_rows:
            await _upsert_review_item(
                row.key, subject_table, r["id"], r.get(email_field),
                row.action, r.get("term_expired_op"), row.signal_missing_nl,
            )
        await _retire_stale_pending(row.key, subject_table, live_ids)
        summary[row.key] = {"queued": len(live_rows)}

    # leads_quiz: two unrelated tables, hard_delete, no protective guard --
    # purely an age cutoff, so there is no "signal_missing" beyond that.
    quiz_rows = await fetch_all(
        "SELECT id, created_at + INTERVAL '12 months' AS term_expired_op FROM quiz_submissions "
        "WHERE created_at <= (NOW() - INTERVAL '12 months')"
    )
    contact_rows = await fetch_all(
        "SELECT id, created_at + INTERVAL '12 months' AS term_expired_op FROM contact_submissions "
        "WHERE created_at <= (NOW() - INTERVAL '12 months')"
    )
    leads_quiz_row = retention.get_row("leads_quiz")
    for subject_table, rows_ in (("quiz_submissions", quiz_rows), ("contact_submissions", contact_rows)):
        for r in rows_:
            await _upsert_review_item(
                "leads_quiz", subject_table, r["id"], None, "hard_delete",
                r["term_expired_op"], leads_quiz_row.signal_missing_nl,
            )
        await _retire_stale_pending("leads_quiz", subject_table, [r["id"] for r in rows_])
    summary["leads_quiz"] = {"queued": len(quiz_rows) + len(contact_rows)}

    # apollo_pool_purge (VERWERKINGSREGISTER.md §2.6/§5.7) -- not a
    # RETENTION_TABLE row (a one-off historical pool, not an ongoing
    # category), folded into this same queue since WS-E.10 instead of its
    # own direct-delete endpoint. Action varies per row (anonymise with an
    # e-mail, hard_delete without), unlike every other category here.
    apollo_rows = await fetch_all(retention.APOLLO_POOL_TARGET_SQL)
    for r in apollo_rows:
        action = "anonymise" if r["email"] else "hard_delete"
        await _upsert_review_item(
            "apollo_pool_purge", "candidates", r["id"], r["email"], action,
            None, "n.v.t. -- eenmalige Apollo-poolopschoning, geen bewaartermijn-anker",
        )
    await _retire_stale_pending("apollo_pool_purge", "candidates", [r["id"] for r in apollo_rows])
    summary["apollo_pool_purge"] = {"queued": len(apollo_rows)}

    logger.info("generate_retention_review: summary=%s", summary)
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "categories": summary}


async def retention_review_job() -> dict:
    """Monthly cron entry point (1st of month, 04:00 Europe/Amsterdam).
    Unconditional -- no env flag gates it the way RETENTION_PURGE_ENABLED
    used to gate the old daily purge, because there is nothing left for a
    flag to gate: populating an internal, admin-JWT-only review queue
    deletes nothing (see generate_retention_review()'s own docstring)."""
    return await generate_retention_review()


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
        talentpool_optin_requests_cleanup_job, CronTrigger(hour=4, minute=0),
        id="talentpool_optin_requests_cleanup", replace_existing=True,
    )
    scheduler.add_job(
        talentpool_reminder_job, CronTrigger(hour=4, minute=30),
        id="talentpool_reminder", replace_existing=True,
    )
    # WS-E.10 (owner decision, retention-kolommen branch, fifth round):
    # monthly, not daily -- this job only ever queues people for human
    # review (generate_retention_review()'s own docstring), never purges,
    # so there is no HARD RULE left to re-check on every cron tick the way
    # the old daily purge job had to.
    scheduler.add_job(
        retention_review_job, CronTrigger(day=1, hour=4, minute=0),
        id="retention_review", replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "scheduler: started with %s daily jobs + 1 weekly job + 1 monthly job (Europe/Amsterdam)",
        4 + apollo_jobs_registered,
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
    "retention_review": retention_review_job,
    "talentpool_optin_cleanup": talentpool_optin_requests_cleanup_job,
    # Manual-trigger only — deliberately NOT added to start_scheduler()'s
    # cron jobs below. One-shot Apollo bulk-harvest (services/harvest.py)
    # and its outreach-draft catch-up, both run via routers/outreach.py's
    # POST /run/{job_name}.
    "harvest": harvest_service.harvest_all,
    "morningdrafts": harvest_service.morning_drafts,
    "enrichmatched": harvest_service.enrich_matched,
    "backfillids": harvest_service.backfill_prospect_ids,
}
