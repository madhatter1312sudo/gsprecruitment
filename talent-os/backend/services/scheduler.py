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
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import settings
from core.database import fetch_all, fetch_one, fetch_val, execute
from core.matching import MATCH_SUGGESTION_MIN_STORED_SCORE
from core.security import hash_token
from core import privacy
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
                    # Stamp pool_origin='apollo' here too (see
                    # services/harvest.py's harvest_candidates for the
                    # fuller comment) -- routers/retention_admin.py's
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
                  cl.company_name AS job_company,
                  COALESCE(cl.is_internal, false) AS job_client_internal
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
            # WS-4 (migrations/037): the client for this job is one of
            # GSP's own internal rows (demo client or the anonymous-
            # opdrachtgever pool client) -- never draft outreach that
            # names or implies a real hiring company for it. job_company
            # becomes the literal 'anonieme opdrachtgever', and the
            # prompt itself (outreach_ai._build_user_prompt) is told the
            # client is anonymous so it won't invent or guess a name.
            job_company = (
                "anonieme opdrachtgever" if row["job_client_internal"] else row["job_company"]
            )
            draft = await outreach_ai.draft_email(
                target={
                    "name": row["full_name"],
                    "company": row["current_company"],
                },
                context={
                    "job_title": row["job_title"],
                    "job_company": job_company,
                    "job_description": row["job_description"],
                    "anonymous_client": row["job_client_internal"],
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
# Owner decision (WS-E.10): every "no reaction" signal this table can
# check lives in a channel this backend does not reliably record (a phone
# call, a LinkedIn thread, a reply landing in someone's own mailbox). This
# job therefore never deletes or anonymises anything by itself -- it only
# queues who core/retention.py's guarded selectors say is due into
# retention_review_items (migrations/036_retention_review_queue.py) for a
# human to approve or reject, once a month
# (GET/POST /api/v1/admin/retention/review*, routers/retention_admin.py).
# core/retention.py's selectors and guards (who ends up on the list) are
# read here, never duplicated -- see that module for those. An actual
# purge only ever happens from an approved retention_review_items row --
# see routers/retention_admin.py's module docstring.

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


_TALENTPOOL_REMINDER_LINK = "https://gsprecruitment.nl/kandidaten#talentpoolOptin"


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
        ok = await email_service.send_template(
            "talentpool_reminder", row["email"],
            {"full_name": row.get("full_name") or "", "link": _TALENTPOOL_REMINDER_LINK},
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


# ── Slapend account: waarschuwing vooraf (WS3b) ─────────────────────────
#
# core/retention.py's PORTAL_ACCOUNT_INACTIVE_SQL zet een kandidaataccount
# pas op de maandelijkse beoordelingslijst als het 18 maanden ongebruikt
# is EN `users.dormant_warning_sent_at` minstens 30 dagen oud is. Die
# kolom bestaat sinds migrations/039, maar tot dit spoor schreef niets
# hem: de selector kon dus per definitie nooit iemand opleveren
# (bewust fail-closed -- "geen verwijderlijst zonder verstuurde
# waarschuwing"). Deze job is de ontbrekende helft.
#
# Vorm exact die van talentpool_reminder_job hierboven: selecteer wie aan
# de beurt is, verstuur, stempel de kolom pas als de verzending lukte, en
# nooit twee keer binnen dezelfde cyclus.
#
# De selector zelf staat in core/retention.py, naast
# PORTAL_ACCOUNT_INACTIVE_SQL: het zijn twee helften van één belofte en ze
# horen niet in twee bestanden te staan. Zie daar ook waarom het venster
# geen bovengrens heeft en waarom twee keer waarschuwen desondanks niet
# kan.

# Tussen de waarschuwing en de beoordelingslijst zitten 30 dagen
# (PORTAL_ACCOUNT_INACTIVE_SQL: `dormant_warning_sent_at < NOW() - 30
# days`). De datum in de mail is verzenddatum + deze 30 dagen, niet een
# los getal in de templatetekst.
DORMANT_WARNING_GRACE_DAYS = 30
DORMANT_WARNING_CAP = 200

# Het kandidaatportaal is één pagina met een inlogmodal
# (website/candidate/index.html plus website/candidate/script.js); er is
# geen login.html. Een waarschuwingsmail die zegt "log in om je account te
# houden" en dan naar een 404 wijst, is erger dan geen mail. Via
# settings.frontend_url en niet als letterlijke host, zoals elke andere
# link die deze module verstuurt.
_DORMANT_WARNING_PATH = "/candidate/"


def _dormant_warning_link() -> str:
    return f"{settings.frontend_url}{_DORMANT_WARNING_PATH}"


async def dormant_account_warning_job() -> dict:
    """Dagelijks (04:45). Waarschuwt kandidaataccounts die minstens 17
    maanden niet zijn gebruikt dat ze na 18 maanden op de maandelijkse
    verwijderlijst komen, en stempelt `users.dormant_warning_sent_at`
    zodat dezelfde persoon per inactiviteitscyclus één keer wordt
    gewaarschuwd.

    `accounts_due` is het aantal dat vandaag aan de beurt is, geteld vóór
    het dagplafond DORMANT_WARNING_CAP (CR L2) -- anders zou een
    droogloop bij een achterstand van duizenden accounts netjes "200"
    melden en precies het getal verbergen waar de eigenaar naar kijkt.

    Droogloop is de default: met DORMANT_WARNING_ENABLED uit
    (core/config.py) selecteert en telt deze job wel, maar verstuurt hij
    niets en stempelt hij niets. Dat laatste is essentieel en geen
    detail: zou hij in droogloop wél stempelen, dan zou
    PORTAL_ACCOUNT_INACTIVE_SQL 30 dagen later accounts op de
    verwijderlijst zetten waar nooit iemand een waarschuwing over heeft
    gekregen."""
    from services.email_service import email_service

    due_row = await fetch_one(retention.DORMANT_WARNING_COUNT_SQL)
    accounts_due = due_row["due"] if due_row else 0
    rows = await fetch_all(retention.DORMANT_WARNING_SQL, DORMANT_WARNING_CAP)

    # Dezelfde blokkeerlijstcontrole als job_alert_job
    # (_job_alert_suppressed_ids), en om dezelfde reden: wie STOP heeft
    # gestuurd, krijgt geen bericht meer, op geen enkele grondslag -- ook
    # geen waarschuwing over zijn eigen account.
    #
    # B3: zo'n rij wordt NIET uit deze lijst gefilterd maar mailloos
    # afgehandeld. Wegfilteren gebeurde ná de LIMIT van de selector, dus
    # de rij werd nooit gestempeld, bleef onder `ORDER BY last_login_at
    # ASC` vooraan staan en verbruikte morgen weer een plek onder het
    # dagplafond; bij een paar honderd geblokkeerde accounts bereikte de
    # job niemand anders meer. En een STOP is een verbod op berichten,
    # geen toestemming om de gegevens onbeperkt te bewaren: zonder stempel
    # kwam zo'n account ook nooit op de maandelijkse beoordelingslijst.
    # `dormant_warning_skipped_at` zegt "aan de beurt geweest, geen mail
    # verstuurd" en telt in PORTAL_ACCOUNT_INACTIVE_SQL gelijk met
    # `dormant_warning_sent_at`, met dezelfde 30 dagen ertussen.
    suppressed_ids = await _job_alert_suppressed_ids(rows)
    to_warn = [r for r in rows if r["id"] not in suppressed_ids]
    to_skip = [r for r in rows if r["id"] in suppressed_ids]

    if not settings.dormant_warning_enabled:
        # Een droogloop stempelt niets, ook `dormant_warning_skipped_at`
        # niet: die stempel start dezelfde klok van 30 dagen als een
        # verstuurde waarschuwing, en een droogloop mag geen enkele klok
        # starten.
        logger.info(
            "dormant_account_warning_job: DORMANT_WARNING_ENABLED=false, dry run -- "
            "accounts_due=%s, selected=%s, suppressed=%s, nothing sent or stamped",
            accounts_due, len(rows), len(to_skip),
        )
        return {
            "status": "dry_run", "accounts_due": accounts_due, "selected": len(rows),
            "sent": 0, "suppressed": len(to_skip), "failed": 0,
        }

    suppressed = 0
    for row in to_skip:
        await execute(
            "UPDATE users SET dormant_warning_skipped_at = NOW() WHERE id = $1", row["id"],
        )
        # Nooit het adres, alleen de sha256 (core/privacy.py), zoals elke
        # andere audit-regel die een adres aanraakt. json.dumps, nooit een
        # ruwe dict (commit 72b4bcd).
        await execute(
            "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
            "VALUES ($1, NULL, $2, $3, $4::jsonb)",
            "dormant_warning_suppressed", "user", row["id"],
            json.dumps({
                "reason": "suppression_list",
                "email_hash": privacy.email_hash(row["email"]) if row["email"] else None,
            }),
        )
        suppressed += 1

    deadline = (datetime.now(timezone.utc) + timedelta(days=DORMANT_WARNING_GRACE_DAYS)).date().isoformat()
    link = _dormant_warning_link()
    sent = 0
    failed = 0
    for row in to_warn:
        ok = await email_service.send_template(
            "dormant_warning", row["email"],
            {
                "full_name": row.get("full_name") or "",
                "link": link,
                "deadline": deadline,
                # R4: de datum van de laatste login, niet een maandental.
                # Met een ondergrens van 17 maanden en geen bovengrens is
                # elk getal in de tekst voor een deel van de ontvangers
                # onwaar; deze datum klopt voor iedereen en is bovendien
                # het enige waaraan de ontvanger kan herkennen over welk
                # account dit gaat.
                "last_login": row["last_login_at"].date().isoformat() if row["last_login_at"] else "",
            },
        )
        if ok:
            await execute(
                "UPDATE users SET dormant_warning_sent_at = NOW() WHERE id = $1", row["id"],
            )
            sent += 1
        else:
            # B4: de teller ophogen, niet de verzendstempel zetten. Zonder
            # teller kwam een structureel onbezorgbaar adres elke dag
            # terug op dezelfde plek onder het dagplafond en schoof het de
            # hele achterstand voor zich uit;
            # _DORMANT_WARNING_WHERE_SQL laat de rij na drie pogingen
            # vallen, en elke login zet de teller terug op 0.
            await execute(
                "UPDATE users SET dormant_warning_attempts = dormant_warning_attempts + 1 "
                "WHERE id = $1", row["id"],
            )
            failed += 1
            # Nooit het adres in een logregel -- het id is genoeg, en
            # services/email_service.py schreef zelf al een email_log-rij
            # op core.privacy.email_hash().
            logger.warning("dormant_account_warning_job: failed to send warning to user id=%s", row["id"])

    logger.info(
        "dormant_account_warning_job: accounts_due=%s selected=%s sent=%s suppressed=%s failed=%s",
        accounts_due, len(rows), sent, suppressed, failed,
    )
    return {
        "status": "success", "accounts_due": accounts_due, "selected": len(rows),
        "sent": sent, "suppressed": suppressed, "failed": failed,
    }


# ── Vacature-alerts (WS3c) ──────────────────────────────────────────────
#
# HARDE GRENS, en de reden dat dit blok zo uitgebreid is: outreach blijft
# draft-only. Deze job is geen uitzondering daarop maar valt buiten die
# categorie, en het verschil zit in de selectie hieronder, niet in een
# belofte in een commentaarregel.
#
#   - Outreach (draft_outreach hierboven) richt zich op een GESOURCETE
#     persoon: iemand die niets heeft gedaan, wiens gegevens wij hebben
#     gevonden. Daar mag nooit automatisch een bericht naartoe; er wordt
#     een `outreach_drafts`-rij met status='draft' geschreven en een mens
#     verstuurt hem na goedkeuring (routers/outreach.py).
#   - Deze job richt zich uitsluitend op iemand die ZELF heeft gezegd dat
#     hij deze mail wil: `candidates.job_alert_optin_at` is gezet, en er
#     zijn precies twee paden die dat doen, allebei een eigen handeling
#     van de betrokkene (PUT /api/v1/candidate/job-alerts in zijn eigen
#     portaal, of het `job_alerts`-vinkje dat hij bij zijn dubbele
#     opt-in aanvinkte en daarna per e-mail bevestigde). Geen sourcing-
#     pad, geen import, geen beheerder en geen routine kan die kolom
#     vullen.
#
# Daarom draagt elke alert ook een een-klik-afmeldlink en de
# List-Unsubscribe-headers, en outreach-drafts niet: dit is het enige
# terugkerende bericht dat deze codebase verstuurt.
#
# De selectie hieronder maakt dat waar in plaats van te beloven:
#   job_alert_optin_at IS NOT NULL          -- eigen aanmelding, zie boven
#   job_alert_unsubscribed_at IS NULL       -- niet afgemeld
#   consent_withdrawn_at IS NULL            -- toestemming niet ingetrokken
#   deleted_at IS NULL                      -- niet (zacht) verwijderd
#   consent_scope='matching_and_contact'    -- toestemming die contact dekt
#     OF lawful_basis='portal_registratie'  -- eigen portaalaccount (art. 13)
#   toestemming nog geldig                  -- consent_talentpool_until in de
#                                              toekomst, tenzij portaalaccount
#   niet op de suppressielijst              -- STOP ontvangen, in Python
#                                              gehasht via core/privacy.py
#
# Die voorlaatste regel is de toestemmingsgeldigheid, en hij staat samen
# met de rest van de geschiktheidsvoorwaarden in core/retention.py als
# JOB_ALERT_ELIGIBILITY_SQL -- naast TALENTPOOL_EXPIRED_SQL, waarmee hij
# zijn belangrijkste clausule deelt, en bereikbaar voor de tweede lezer
# (routers/candidate.py's portaalschakelaar) zonder dat die deze hele
# module hoeft te importeren. Zie daar wat elke regel doet.

JOB_ALERT_CANDIDATE_SQL = f"""
    SELECT c.id, c.email, c.full_name, c.job_alert_last_sent_at
      FROM candidates c
     WHERE c.job_alert_optin_at IS NOT NULL
       AND c.job_alert_unsubscribed_at IS NULL
       AND {retention.JOB_ALERT_ELIGIBILITY_SQL}
     ORDER BY c.job_alert_last_sent_at ASC NULLS FIRST, c.id ASC
     LIMIT $1
"""

# Matches die nieuw genoeg zijn om te melden: sinds de vorige digest van
# deze kandidaat, of -- als die er nooit was -- de laatste 7 dagen, zodat
# een verse aanmelder geen jaar aan oude matches in één mail krijgt.
# `j.city` is de locatiekolom (migrations/016); job_orders heeft geen
# slug, de publieke vacaturepagina werkt op id (website/script.js,
# website/vacature.js). De geschiktheidsfilter is letterlijk
# routers/jobs.py's PUBLIC_JOB_WHERE -- een alert mag nooit naar een
# vacature wijzen die het publieke bord zelf niet toont.
JOB_ALERT_MATCHES_SQL = """
    SELECT j.id, j.title, j.city, m.match_score
      FROM matches m
      JOIN job_orders j ON j.id = m.job_id
     WHERE m.candidate_id = $1
       AND m.status = 'suggested'
       AND m.match_score >= $2
       AND m.created_at > COALESCE($3, NOW() - INTERVAL '7 days')
       AND {public_job_where}
     ORDER BY m.match_score DESC
     LIMIT $4
"""

JOB_ALERT_RUN_CAP = 200
JOB_ALERT_MAX_JOBS = 5


def job_alert_matches_sql() -> str:
    """JOB_ALERT_MATCHES_SQL met routers/jobs.py's eigen PUBLIC_JOB_WHERE
    ingevuld. Lazy import, net als `from routers.matches import ...` in
    matching() hierboven: routers/* importeren bij het laden van deze
    module zou een importcyclus opleveren (routers importeren services)."""
    from routers.jobs import PUBLIC_JOB_WHERE

    return JOB_ALERT_MATCHES_SQL.format(public_job_where=PUBLIC_JOB_WHERE)


def _job_alert_unsubscribe_links(token: str, oneclick_token: str) -> tuple:
    """(voettekstlink voor een mens, one-click-URL voor de
    List-Unsubscribe-header).

    Twee URL's met TWEE VERSCHILLENDE tokens (B1), en dat verschil is de
    hele beveiliging:

      - de voettekstlink draagt `token` in het URL-FRAGMENT, precies zoals
        de talentpool-bevestigingslink sinds de WS-C.17 security-audit
        (H1) doet -- een fragment bereikt de server nooit en staat dus
        niet in een access log of een Referer-header. Dit is het enige
        token waarmee `scope=all` bereikbaar is: toestemming intrekken en
        het adres op de blokkeerlijst, onomkeerbaar;
      - de List-Unsubscribe-URL kan geen fragment gebruiken: RFC 8058
        schrijft een POST-bare https-URL voor en een fragment zou daar
        simpelweg verdwijnen. Daar staat `oneclick_token` dus in de
        querystring, en belandt daarmee in elke access-, proxy- en
        edge-logregel die het verzoek passeert.

    Zolang dat één en hetzelfde token was, kon wie een one-click-URL uit
    een log haalde datzelfde token in de body plakken en `scope=all`
    bereiken. Nu draagt `job_alert_sends` beide hashes apart en dwingt
    routers/public.py's unsubscribe() voor een treffer op
    `oneclick_token_hash` altijd `alerts` af, wat de body, de querystring
    of de opgegeven scope ook zegt. Een gelekt one-click-token kan daarmee
    niet méér dan waarvoor het is uitgegeven. Dat restrisico -- en wat
    ervan overblijft -- staat in docs/VERWERKINGSREGISTER.md §1.2.
    """
    footer = f"{settings.frontend_url}/unsubscribe#token={token}"
    one_click = f"{settings.api_base_url}/api/public/unsubscribe?token={oneclick_token}&scope=alerts"
    return footer, one_click


async def _job_alert_suppressed_ids(rows: list) -> set:
    """Welke van deze kandidaten op de suppressielijst staan.

    Bewust in Python en niet in SQL: core/privacy.py is de enige plek die
    bepaalt hoe een adres tot een suppression_list-hash wordt (trim,
    lower, sha256). Een tweede, met de hand nagebouwde sha256-expressie
    in SQL zou stilletjes uit de pas kunnen lopen met die definitie, en
    de fout zou eruitzien als "deze persoon staat er niet op" -- precies
    de kant op die een mail stuurt naar iemand die STOP heeft gezegd.

    Security-audit B8: de map gaat van id naar hash en niet andersom.
    Als `{hash: id}` verloor hij stilletjes rijen zodra twee kandidaten
    hetzelfde adres droegen (een gesourcete rij en een portaalrij die
    WS-C.16's FK nooit heeft samengevoegd -- deze codebase heeft daar een
    hele migratie aan besteed, dus het is geen theoretisch geval): de
    tweede overschreef de eerste, en de overschreven rij kreeg zijn mail
    gewoon. Precies dezelfde fout die dit hele hulpje moet voorkomen,
    alleen in Python in plaats van in SQL."""
    by_id = {r["id"]: privacy.email_hash(r["email"]) for r in rows if r["email"]}
    if not by_id:
        return set()
    hits = await fetch_all(
        "SELECT email_hash FROM suppression_list WHERE email_hash = ANY($1::text[])",
        list(set(by_id.values())),
    )
    suppressed_hashes = {h["email_hash"] for h in hits}
    return {cid for cid, h in by_id.items() if h in suppressed_hashes}


async def job_alert_job() -> dict:
    """Dagelijks (08:00, ná de matching van 07:00). Eén digest per
    kandidaat met maximaal JOB_ALERT_MAX_JOBS vacatures, maximaal
    JOB_ALERT_RUN_CAP kandidaten per run.

    Twee schakelaars, allebei droog by default: de env-master
    JOB_ALERTS_ENABLED (core/config.py) en de admin-bewerkbare DB-vlag
    system_settings.job_alerts_enabled. Staat er één uit, dan selecteert
    en telt deze job wel maar verstuurt hij niets, schrijft hij geen
    job_alert_sends-rij en stempelt hij geen job_alert_last_sent_at --
    een droogloop mag geen enkel spoor achterlaten dat een echte
    verzending suggereert."""
    from services.email_service import email_service

    env_enabled = settings.job_alerts_enabled
    db_enabled = await _flag_enabled("job_alerts_enabled")
    enabled = env_enabled and db_enabled

    candidates = await fetch_all(JOB_ALERT_CANDIDATE_SQL, JOB_ALERT_RUN_CAP)
    suppressed_ids = await _job_alert_suppressed_ids(candidates)
    matches_sql = job_alert_matches_sql()

    considered = 0
    sent = 0
    suppressed = 0
    for row in candidates:
        if row["id"] in suppressed_ids:
            # B5: overslaan is niet genoeg. `ORDER BY
            # job_alert_last_sent_at ASC NULLS FIRST` zet een kandidaat
            # die nog nooit een digest kreeg vooraan, en een geblokkeerde
            # kandidaat krijgt er ook nooit een -- dus stond hij morgen
            # weer vooraan en verbruikte hij permanent een plek onder
            # JOB_ALERT_RUN_CAP. Een STOP IS een afmelding: de kolom mag
            # dat gewoon zeggen, en dan verlaat de rij de selector.
            # COALESCE zodat een eerdere, eigen afmelding zijn oudere
            # tijdstip houdt.
            await execute(
                """UPDATE candidates
                   SET job_alert_unsubscribed_at = COALESCE(job_alert_unsubscribed_at, NOW()),
                       updated_at = NOW()
                   WHERE id = $1""",
                row["id"],
            )
            # Nooit het adres, alleen de sha256 (core/privacy.py).
            # json.dumps, nooit een ruwe dict (commit 72b4bcd).
            await execute(
                "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
                "VALUES ($1, NULL, $2, $3, $4::jsonb)",
                "job_alert_suppressed", "candidate", row["id"],
                json.dumps({
                    "reason": "suppression_list",
                    "email_hash": privacy.email_hash(row["email"]) if row["email"] else None,
                }),
            )
            suppressed += 1
            continue

        jobs = await fetch_all(
            matches_sql,
            row["id"], MATCH_SUGGESTION_MIN_STORED_SCORE,
            row["job_alert_last_sent_at"], JOB_ALERT_MAX_JOBS,
        )
        if not jobs:
            continue
        considered += 1

        if not enabled:
            continue

        # Twee losse tokens per verzending (B1): het fragmenttoken voor de
        # voettekstlink (de enige weg naar `scope=all`) en het
        # one-click-token voor de List-Unsubscribe-header (altijd
        # `alerts`, wat de aanroeper ook meestuurt). Zie
        # _job_alert_unsubscribe_links hierboven.
        token = secrets.token_urlsafe(32)
        oneclick_token = secrets.token_urlsafe(32)
        footer_link, one_click_url = _job_alert_unsubscribe_links(token, oneclick_token)

        # Security-audit B7: eerst de tokenrij, dan pas verzenden. De
        # omgekeerde volgorde leek voorzichtiger ("geen geldig token voor
        # een mail die nooit aankwam") maar faalt de verkeerde kant op:
        # deze twee statements zitten niet in één transactie met de
        # verzending, dus als de INSERT struikelde nádat de mail de deur
        # uit was, had de ontvanger een afmeldlink die niets doet -- en
        # het endpoint antwoordt met opzet altijd hetzelfde, dus hij ziet
        # precies niets van dat verschil. Bovendien bleef
        # `job_alert_last_sent_at` dan ongestempeld en kreeg hij morgen
        # dezelfde digest opnieuw.
        #
        # Andersom is elke uitkomst hanteerbaar: mislukt de INSERT, dan
        # gaat er geen mail uit (we slaan deze kandidaat over); mislukt de
        # verzending, dan halen we de rij weer weg en is er geen token
        # zonder bericht. Blijft één restgeval: crasht het proces tussen
        # de verzending en de DELETE, dan staat er een tokenrij voor een
        # mail die niet aankwam. Dat token is dan hoogstens ongebruikt --
        # niemand heeft hem ooit gezien -- en verloopt na 90 dagen
        # (routers/public.py).
        send_row = await fetch_one(
            "INSERT INTO job_alert_sends (candidate_id, job_ids, token_hash, oneclick_token_hash) "
            "VALUES ($1, $2::int[], $3, $4) RETURNING id",
            row["id"], [j["id"] for j in jobs], hash_token(token), hash_token(oneclick_token),
        )
        if not send_row:
            logger.warning("job_alert_job: could not record the unsubscribe token for candidate id=%s", row["id"])
            continue

        ok = await email_service.send_template(
            "job_alert", row["email"],
            {
                "full_name": row.get("full_name") or "",
                "jobs": [
                    {
                        "title": j["title"],
                        "location": j["city"],
                        "url": f"{settings.frontend_url}/vacature.html?id={j['id']}",
                    }
                    for j in jobs
                ],
                "unsubscribe_link": footer_link,
            },
            headers={
                # RFC 8058: beide headers moeten aanwezig zijn wil een
                # mailclient de one-click-knop tonen; alleen
                # List-Unsubscribe zonder -Post levert een "weet je het
                # zeker"-omweg op, of niets.
                "List-Unsubscribe": f"<{one_click_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        )
        if not ok:
            # De rij weer weg: geen afmeldtoken voor een bericht dat niet
            # is aangekomen.
            await execute("DELETE FROM job_alert_sends WHERE id = $1", send_row["id"])
            logger.warning("job_alert_job: failed to send digest to candidate id=%s", row["id"])
            continue

        # Pas ná een geslaagde verzending de stempel: anders zou
        # job_alert_last_sent_at het venster van de volgende run
        # dichtschuiven over matches die deze persoon nooit heeft gezien.
        await execute(
            "UPDATE candidates SET job_alert_last_sent_at = NOW() WHERE id = $1", row["id"],
        )
        sent += 1

    status = "success" if enabled else "dry_run"
    logger.info(
        "job_alert_job: status=%s candidates_selected=%s with_matches=%s sent=%s suppressed=%s (env=%s db=%s)",
        status, len(candidates), considered, sent, suppressed, env_enabled, db_enabled,
    )
    return {
        "status": status,
        "candidates_selected": len(candidates),
        "with_matches": considered,
        "sent": sent,
        "suppressed": suppressed,
    }


# ── Bewaartermijn van het verzendlogboek (R1) ───────────────────────────
#
# `job_alert_sends` is een verzendlogboek met een kandidaat-id en een
# tokenhash per verzonden digest, en had geen eigen bewaartermijn. "Volgt
# de kandidaatrij" was daarvoor geen antwoord: `routers/gdpr.py`'s
# erase_person() ANONIMISEERT een kandidaat (de rij blijft bestaan, het
# adres verdwijnt), dus de `ON DELETE CASCADE` op `candidate_id` treedt
# op het gewone wispad helemaal niet in werking en zou het logboek
# onbeperkt laten groeien.
#
# 90 dagen, en dat getal is geen keuze maar een gevolg: het afmeldtoken
# werkt precies zo lang (`routers/public.py unsubscribe()`), dus een
# oudere rij kan niets meer doen wat een nieuwere niet doet. Gelijk aan de
# bewaartermijn van email_log (migrations/040), dat over dezelfde
# verzendingen gaat.
JOB_ALERT_SENDS_RETENTION_DAYS = 90


async def job_alert_sends_cleanup_job() -> dict:
    """Dagelijks (04:20). Verwijdert `job_alert_sends`-rijen ouder dan
    JOB_ALERT_SENDS_RETENTION_DAYS dagen.

    Harde verwijdering en geen beoordelingslijst, om dezelfde reden als
    talentpool_optin_requests_cleanup_job hierboven: er valt geen signaal
    te missen. Zo'n rij is een verzendlogregel met een verlopen token; hij
    draagt geen adres en geen ander gegeven waarover iemand een besluit
    zou moeten nemen."""
    # De termijn als parameter en niet als string in de SQL: dit is een
    # DELETE, en de enige reden dat een getal hier veilig zou zijn is dat
    # het vandaag een constante is. `DELETE ... RETURNING` en tellen in
    # Python, dezelfde vorm als _purge_stale_talentpool_optin_requests
    # hierboven -- geen CTE, want dan leest deze query als een verwijzing
    # naar een tabel die geen enkele migratie aanmaakt
    # (tests/test_baseline_schema.py).
    purged = await fetch_all(
        "DELETE FROM job_alert_sends WHERE sent_at < NOW() - ($1::int * INTERVAL '1 day') "
        "RETURNING id",
        JOB_ALERT_SENDS_RETENTION_DAYS,
    )
    count = len(purged)
    if count:
        await execute(
            "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
            "VALUES ($1, NULL, $2, NULL, $3::jsonb)",
            "retention_purge", "job_alert_sends",
            json.dumps({
                "category": "job_alert_sends", "count": count, "action": "hard_delete",
                "older_than_days": JOB_ALERT_SENDS_RETENTION_DAYS,
            }),
        )
    logger.info("job_alert_sends_cleanup_job: purged=%s", count)
    return {"status": "purged", "count": count}


# ── Per-category live rows for the monthly review queue ─────────────────

async def _live_rows_for_category(row: "retention.RetentionRow") -> list:
    """Runs `row.selector_sql` generically against `row.selector_params` --
    core/retention.py's RetentionRow already carries subject_table/
    email_field (where to file the result in retention_review_items) and
    selector_params (the query's own positional placeholders), so this is
    the one place, per category, that reads who is due -- not a second,
    independently-maintained copy of that lookup here.

    leads_quiz is the one RETENTION_TABLE row this does NOT run this way:
    its selector_sql documents two unrelated tables (quiz_submissions,
    contact_submissions) joined with a literal "; " for display purposes
    only, which asyncpg's single-statement fetch() cannot execute -- so it
    runs each constant separately and returns the concatenation (used only
    for a count here; generate_retention_review() below queues the two
    tables separately so each row lands under its own subject_table).

    Any other row reaching this function without a subject_table/
    email_field (a RETENTION_TABLE addition that forgot to set them, or a
    caller passing something malformed) raises rather than returning [] --
    returning [] here would make generate_retention_review()'s
    _retire_stale_pending() call for that category mark every currently-
    pending item 'no_longer_eligible', which means "a protective signal
    appeared", not "the query is broken"."""
    if row.key == "leads_quiz":
        quiz = await fetch_all(retention.LEADS_QUIZ_SQL)
        contact = await fetch_all(retention.CONTACT_SUBMISSIONS_SQL)
        return quiz + contact
    if not row.subject_table or not row.email_field:
        raise ValueError(
            f"_live_rows_for_category: category {row.key!r} carries no subject_table/email_field"
        )
    return await fetch_all(row.selector_sql, *row.selector_params)


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
    someone who is no longer actually due. H3 (security-audit round 5):
    the e-mail column is nulled the moment a row leaves 'pending' -- data
    minimisation for a row that no longer needs the address to be
    actionable; a later run re-supplies it via _upsert_review_item()'s
    ON CONFLICT DO UPDATE if the subject becomes due again."""
    await execute(
        """UPDATE retention_review_items SET status = 'no_longer_eligible', last_seen_at = NOW(), email = NULL
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
    every table except retention_review_items itself.

    Each category runs inside its own try/except: a selector that raises
    (a bad join, a locked table, a soft-deleted FK target, ...) is recorded
    as {"status": "error"} for that category in the returned summary and
    its own _retire_stale_pending() call is skipped for this run, rather
    than the whole job aborting halfway (losing every category that hadn't
    run yet) or the exception being swallowed into an empty result that
    would make _retire_stale_pending() mark every already-pending item in
    that one category 'no_longer_eligible' -- a query failure must never
    look like "everyone picked up a protective signal"."""
    summary: dict = {}

    for row in retention.RETENTION_TABLE:
        if row.action not in ("anonymise", "hard_delete") or not row.schema_ready:
            continue  # retain/infra_only, or schema_not_ready -- see core/retention.py
        if row.key == "leads_quiz":
            continue  # spans two subtables with no shared guard -- handled separately below
        try:
            live_rows = await _live_rows_for_category(row)
            live_ids = [r["id"] for r in live_rows]
            for r in live_rows:
                await _upsert_review_item(
                    row.key, row.subject_table, r["id"], r.get(row.email_field),
                    row.action, r.get("term_expired_op"), row.signal_missing_nl,
                )
            await _retire_stale_pending(row.key, row.subject_table, live_ids)
            summary[row.key] = {"queued": len(live_rows)}
        except Exception:
            logger.exception("generate_retention_review: category %s failed", row.key)
            summary[row.key] = {"status": "error"}

    # leads_quiz: two unrelated tables, hard_delete, no protective guard --
    # purely an age cutoff, so there is no "signal_missing" beyond that.
    try:
        quiz_rows = await fetch_all(retention.LEADS_QUIZ_SQL)
        contact_rows = await fetch_all(retention.CONTACT_SUBMISSIONS_SQL)
        leads_quiz_row = retention.get_row("leads_quiz")
        for subject_table, rows_ in (("quiz_submissions", quiz_rows), ("contact_submissions", contact_rows)):
            for r in rows_:
                await _upsert_review_item(
                    "leads_quiz", subject_table, r["id"], None, "hard_delete",
                    r["term_expired_op"], leads_quiz_row.signal_missing_nl,
                )
            await _retire_stale_pending("leads_quiz", subject_table, [r["id"] for r in rows_])
        summary["leads_quiz"] = {"queued": len(quiz_rows) + len(contact_rows)}
    except Exception:
        logger.exception("generate_retention_review: category leads_quiz failed")
        summary["leads_quiz"] = {"status": "error"}

    # apollo_pool_purge (VERWERKINGSREGISTER.md §2.6/§5.7) -- not a
    # RETENTION_TABLE row (a one-off historical pool, not an ongoing
    # category), folded into this same queue since WS-E.10 instead of its
    # own direct-delete endpoint. Action varies per row (anonymise with an
    # e-mail, hard_delete without), unlike every other category here.
    try:
        apollo_rows = await fetch_all(retention.APOLLO_POOL_TARGET_SQL)
        for r in apollo_rows:
            action = "anonymise" if r["email"] else "hard_delete"
            await _upsert_review_item(
                "apollo_pool_purge", "candidates", r["id"], r["email"], action,
                None, "n.v.t. -- eenmalige Apollo-poolopschoning, geen bewaartermijn-anker",
            )
        await _retire_stale_pending("apollo_pool_purge", "candidates", [r["id"] for r in apollo_rows])
        summary["apollo_pool_purge"] = {"queued": len(apollo_rows)}
    except Exception:
        logger.exception("generate_retention_review: category apollo_pool_purge failed")
        summary["apollo_pool_purge"] = {"status": "error"}

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
        job_alert_sends_cleanup_job, CronTrigger(hour=4, minute=20),
        id="job_alert_sends_cleanup", replace_existing=True,
    )
    scheduler.add_job(
        talentpool_reminder_job, CronTrigger(hour=4, minute=30),
        id="talentpool_reminder", replace_existing=True,
    )
    # WS3b/WS3c. Beide worden ALTIJD geregistreerd, ook met hun
    # schakelaar uit -- anders dan de Apollo-jobs hierboven, die pas
    # bestaan als APOLLO_SYNC_ENABLED aan staat. Het verschil is bewust:
    # met de schakelaar uit verstuurt geen van deze twee jobs iets en
    # schrijft geen van beide iets weg (zie hun docstrings), ze tellen
    # alleen wie er aan de beurt zou zijn. Die droogloop in de logs is
    # precies wat je wilt kunnen zien voordat je de schakelaar omzet, en
    # is zelf geen verwerking richting een betrokkene.
    #
    # 04:45 zit na talentpool_reminder (04:30) en voor de matching;
    # 08:00 zit na de matching van 07:00, zodat de digest van vandaag de
    # matches van vanochtend meeneemt in plaats van die van gisteren.
    scheduler.add_job(
        dormant_account_warning_job, CronTrigger(hour=4, minute=45),
        id="dormant_account_warning", replace_existing=True,
    )
    scheduler.add_job(
        job_alert_job, CronTrigger(hour=8, minute=0),
        id="job_alert", replace_existing=True,
    )
    # WS-E.10 (owner decision): monthly, not daily -- this job only ever
    # queues people for human review (generate_retention_review()'s own
    # docstring), never purges, so there is no HARD RULE left to re-check
    # on every cron tick the way a daily purge job would have to.
    scheduler.add_job(
        retention_review_job, CronTrigger(day=1, hour=4, minute=0),
        id="retention_review", replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "scheduler: started with %s daily jobs + 1 weekly job + 1 monthly job (Europe/Amsterdam)",
        6 + apollo_jobs_registered,
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
    # WS3b/WS3c: handmatig te draaien via POST /api/v1/admin/outreach/run/
    # {job_name}, net als de andere jobs hier. Handmatig draaien omzeilt
    # géén schakelaar: allebei lezen ze settings (en job_alert ook de
    # DB-vlag) binnenin, dus een admin die dit aanroept met de
    # schakelaars uit krijgt dezelfde droogloop als de cron -- dezelfde
    # les als de security-audit-opmerking bij apollo_search_and_sync.
    "dormant_warning": dormant_account_warning_job,
    "job_alerts": job_alert_job,
    "job_alert_sends_cleanup": job_alert_sends_cleanup_job,
    # Manual-trigger only — deliberately NOT added to start_scheduler()'s
    # cron jobs below. One-shot Apollo bulk-harvest (services/harvest.py)
    # and its outreach-draft catch-up, both run via routers/outreach.py's
    # POST /run/{job_name}.
    "harvest": harvest_service.harvest_all,
    "morningdrafts": harvest_service.morning_drafts,
    "enrichmatched": harvest_service.enrich_matched,
    "backfillids": harvest_service.backfill_prospect_ids,
}
