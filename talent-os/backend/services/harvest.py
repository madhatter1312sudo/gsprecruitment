"""
Talent OS — One-shot Apollo bulk-harvest job (manual trigger only).

Two goals, kept deliberately separate from the daily scheduler.py pipeline:

  1. harvest_candidates(): bulk-populate `candidates` from Apollo's people
     search across our core target titles, WITHOUT spending enrichment
     credits (no /people/match calls). Most rows will therefore have no
     email — that's fine, this is a sourcing-volume job, not an outreach job.
  2. harvest_prospects(): bulk-populate `client_prospects` (BD leads —
     hiring managers/CTOs at Brainport high-tech companies) the same way.

harvest_all() runs both and writes a single audit_log row.

Resumability: candidates.email carries a UNIQUE NULLS NOT DISTINCT
constraint (see talent-os/scripts/init_db.sql), so ON CONFLICT (email)
would only ever let ONE null-email row exist in the whole table — useless
here since bulk (non-enriched) Apollo rows are almost always email-less.
Same problem for client_prospects' UNIQUE (company_name, contact_email):
plain Postgres UNIQUE treats NULL <> NULL, so it would never actually
catch duplicate email-less prospects. Both inserts therefore use an
INSERT ... SELECT ... WHERE NOT EXISTS guard on a natural key instead
(full_name+current_company for candidates, company_name+contact_name for
prospects) so re-running the job is safe and simply skips rows already
inserted by a prior run.

NEVER sends anything and NEVER calls enrich_person — Apollo credits are
only spent on the cheaper mixed_people/search endpoint.
"""
import json
import logging
import time
from typing import Any, Dict, Optional

import asyncio

from core.config import settings
from core.database import execute, fetch_all, fetch_one, fetch_val
from services.apollo_client import ApolloClient
from services import outreach_ai

logger = logging.getLogger("talent_os.harvest")

# ── Candidate sourcing ───────────────────────────────────────────────────

CANDIDATE_TITLES = [
    "Embedded Software Engineer",
    "C++ Developer",
    "C++ Software Engineer",
    "Mechatronics Engineer",
    "Cybersecurity Engineer",
    "Embedded Linux Engineer",
]
SOURCE_LOCATIONS = ["Eindhoven, Netherlands", "Netherlands"]

CAP_CANDIDATES = 2500
MAX_PAGES_PER_TITLE = 25
PER_PAGE = 100

# ── Client-prospect (BD lead) sourcing ───────────────────────────────────

PROSPECT_TITLES = [
    "Engineering Manager",
    "CTO",
    "Head of Engineering",
    "R&D Manager",
    "Hiring Manager",
    "VP Engineering",
]
PROSPECT_KEYWORDS = "high-tech OR semiconductor OR embedded OR mechatronics"

CAP_PROSPECTS = 500
MAX_PAGES_PROSPECTS = 25

# ── Apollo rate limiting ─────────────────────────────────────────────────

RATE_LIMIT_SLEEP_S = 1.2

# ── One-shot outreach catch-up (morningdrafts job) ──────────────────────

DRAFT_CANDIDATE_CAP = 25
DRAFT_PROSPECT_CAP = 15


async def _flag_enabled(key: str) -> bool:
    """Read a system_settings boolean flag. Missing key == enabled.
    Duplicated from services/scheduler.py to keep this module import-
    independent of the scheduler (avoids a circular import risk since
    scheduler.py will import JOBS_BY_NAME entries from here)."""
    value = await fetch_val("SELECT value FROM system_settings WHERE key = $1", key)
    if value is None:
        return True
    return str(value).strip().lower() == "true"


def _clean_email(raw: Optional[str]) -> Optional[str]:
    """Apollo returns sentinel strings like 'email_not_unlocked@domain.com'
    for people that would require a paid /people/match enrichment call to
    reveal. Treat those (and blanks) as no email at all."""
    if not raw:
        return None
    value = raw.strip()
    if not value or "not_unlocked" in value.lower():
        return None
    return value


def _person_name(person: Dict[str, Any]) -> str:
    # api_search returns preview records: full last names are obfuscated
    # (last_name_obfuscated, e.g. "V."). Full name + email require a paid
    # people/match reveal, done later for a targeted subset only.
    last = person.get("last_name") or person.get("last_name_obfuscated") or ""
    return f"{person.get('first_name', '')} {last}".strip()


def _person_company(person: Dict[str, Any]) -> str:
    org = person.get("organization") or {}
    if org.get("name"):
        return org["name"]
    history = person.get("employment_history") or []
    if history:
        return history[0].get("company_name", "") or ""
    return ""


def _person_location(person: Dict[str, Any]) -> str:
    return person.get("city") or person.get("location") or "Netherlands"


# ── Job 1a: harvest_candidates ───────────────────────────────────────────

async def harvest_candidates() -> dict:
    """Bulk-source candidates from Apollo across CANDIDATE_TITLES x
    SOURCE_LOCATIONS. NO enrichment calls — saves Apollo credits. Stops
    early per title once a page returns fewer than PER_PAGE results, and
    stops entirely once CAP_CANDIDATES total inserts is reached."""
    if not await _flag_enabled("apollo_sync_enabled"):
        logger.info("harvest_candidates: disabled via system_settings, skipping")
        return {"status": "skipped", "reason": "apollo_sync_enabled=false", "api_calls": 0, "profiles_seen": 0, "inserted": 0}

    if not settings.apollo_api_key:
        logger.warning("harvest_candidates: Apollo API key not configured, skipping")
        return {"status": "skipped", "reason": "Apollo API key not configured", "api_calls": 0, "profiles_seen": 0, "inserted": 0}

    client = ApolloClient(api_key=settings.apollo_api_key)
    api_calls = 0
    profiles_seen = 0
    inserted = 0
    try:
        for title in CANDIDATE_TITLES:
            if inserted >= CAP_CANDIDATES:
                break

            for page in range(1, MAX_PAGES_PER_TITLE + 1):
                if inserted >= CAP_CANDIDATES:
                    break

                try:
                    result = await client.search_people(
                        titles=[title],
                        locations=SOURCE_LOCATIONS,
                        limit=PER_PAGE,
                        page=page,
                    )
                except Exception:
                    logger.exception(
                        "harvest_candidates: search failed title=%s page=%s", title, page
                    )
                    break
                finally:
                    api_calls += 1
                    await asyncio.sleep(RATE_LIMIT_SLEEP_S)

                people = result.get("people") or result.get("data") or []
                profiles_seen += len(people)

                for person in people:
                    if inserted >= CAP_CANDIDATES:
                        break

                    full_name = _person_name(person)
                    if not full_name:
                        continue

                    company = _person_company(person)
                    email = _clean_email(person.get("email") or person.get("personal_email"))
                    row_title = person.get("title") or title
                    location = _person_location(person)
                    linkedin_url = person.get("linkedin_url") or ""
                    skills = [s.get("name", "") for s in (person.get("skills") or []) if s.get("name")]

                    # Preview records carry the Apollo person id — keep it so a
                    # later people/match reveal can enrich without re-searching.
                    apollo_ref = f"apollo:{person.get('id')}" if person.get("id") else None

                    try:
                        row = await fetch_one(
                            """INSERT INTO candidates
                               (full_name, email, current_company, current_title, location,
                                linkedin_url, skills, source, source_url, sourced_by_agent, is_passive)
                               SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11
                               WHERE NOT EXISTS (
                                   SELECT 1 FROM candidates
                                   WHERE full_name = $1
                                     AND COALESCE(current_company, '') = COALESCE($3, '')
                               )
                               RETURNING id""",
                            full_name, email, company, row_title, location,
                            linkedin_url, skills, "apollo_bulk", apollo_ref, "harvest-apollo-bulk", True,
                        )
                    except Exception:
                        logger.exception("harvest_candidates: insert failed for %s", full_name)
                        continue

                    if row:
                        inserted += 1

                if page % 5 == 0:
                    logger.info(
                        "harvest_candidates: progress title=%r page=%s api_calls=%s "
                        "profiles_seen=%s inserted=%s",
                        title, page, api_calls, profiles_seen, inserted,
                    )

                if len(people) < PER_PAGE:
                    # Exhausted results for this title — move to the next one.
                    break

        logger.info(
            "harvest_candidates: done api_calls=%s profiles_seen=%s inserted=%s",
            api_calls, profiles_seen, inserted,
        )
        return {"status": "success", "api_calls": api_calls, "profiles_seen": profiles_seen, "inserted": inserted}
    finally:
        await client.close()


# ── Job 1b: harvest_prospects ────────────────────────────────────────────

async def harvest_prospects() -> dict:
    """Bulk-source client (BD) prospects — hiring managers/CTOs at
    Brainport high-tech companies — from Apollo. NO enrichment calls."""
    if not await _flag_enabled("apollo_sync_enabled"):
        logger.info("harvest_prospects: disabled via system_settings, skipping")
        return {"status": "skipped", "reason": "apollo_sync_enabled=false", "api_calls": 0, "profiles_seen": 0, "inserted": 0}

    if not settings.apollo_api_key:
        logger.warning("harvest_prospects: Apollo API key not configured, skipping")
        return {"status": "skipped", "reason": "Apollo API key not configured", "api_calls": 0, "profiles_seen": 0, "inserted": 0}

    client = ApolloClient(api_key=settings.apollo_api_key)
    api_calls = 0
    profiles_seen = 0
    inserted = 0
    try:
        for page in range(1, MAX_PAGES_PROSPECTS + 1):
            if inserted >= CAP_PROSPECTS:
                break

            try:
                result = await client.search_people(
                    q=PROSPECT_KEYWORDS,
                    titles=PROSPECT_TITLES,
                    locations=SOURCE_LOCATIONS,
                    limit=PER_PAGE,
                    page=page,
                )
            except Exception:
                logger.exception("harvest_prospects: search failed page=%s", page)
                break
            finally:
                api_calls += 1
                await asyncio.sleep(RATE_LIMIT_SLEEP_S)

            people = result.get("people") or result.get("data") or []
            profiles_seen += len(people)

            for person in people:
                if inserted >= CAP_PROSPECTS:
                    break

                contact_name = _person_name(person)
                if not contact_name:
                    continue

                org = person.get("organization") or {}
                company_name = org.get("name") or _person_company(person)
                if not company_name:
                    continue

                domain = org.get("primary_domain") or org.get("website_url") or ""
                contact_title = person.get("title") or ""
                contact_email = _clean_email(person.get("email") or person.get("personal_email"))
                contact_linkedin = person.get("linkedin_url") or ""
                location = _person_location(person)
                industry = org.get("industry") or ""

                try:
                    row = await fetch_one(
                        """INSERT INTO client_prospects
                           (company_name, domain, contact_name, contact_title, contact_email,
                            contact_linkedin, location, industry, source, status)
                           SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,'new'
                           WHERE NOT EXISTS (
                               SELECT 1 FROM client_prospects
                               WHERE company_name = $1 AND contact_name = $3
                           )
                           RETURNING id""",
                        company_name, domain, contact_name, contact_title, contact_email,
                        contact_linkedin, location, industry, "apollo_bulk",
                    )
                except Exception:
                    logger.exception(
                        "harvest_prospects: insert failed for %s @ %s", contact_name, company_name
                    )
                    continue

                if row:
                    inserted += 1

            if page % 5 == 0:
                logger.info(
                    "harvest_prospects: progress page=%s api_calls=%s profiles_seen=%s inserted=%s",
                    page, api_calls, profiles_seen, inserted,
                )

            if len(people) < PER_PAGE:
                break

        logger.info(
            "harvest_prospects: done api_calls=%s profiles_seen=%s inserted=%s",
            api_calls, profiles_seen, inserted,
        )
        return {"status": "success", "api_calls": api_calls, "profiles_seen": profiles_seen, "inserted": inserted}
    finally:
        await client.close()


# ── Job 1: harvest_all (registered as scheduler job 'harvest') ─────────

async def harvest_all() -> dict:
    """Run harvest_candidates() then harvest_prospects() and record one
    audit_log row summarizing the run. Manual trigger only — see
    services/scheduler.py JOBS_BY_NAME and routers/outreach.py run/{job_name}."""
    start = time.monotonic()

    candidates_result = await harvest_candidates()
    prospects_result = await harvest_prospects()

    duration_s = round(time.monotonic() - start, 1)
    candidates_inserted = candidates_result.get("inserted", 0)
    prospects_inserted = prospects_result.get("inserted", 0)
    api_calls = candidates_result.get("api_calls", 0) + prospects_result.get("api_calls", 0)

    changes = {
        "candidates_inserted": candidates_inserted,
        "prospects_inserted": prospects_inserted,
        "api_calls": api_calls,
        "duration_s": duration_s,
    }

    try:
        await execute(
            "INSERT INTO audit_log (action, changes) VALUES ($1, $2::jsonb)",
            "apollo_harvest", json.dumps(changes),
        )
    except Exception:
        logger.exception("harvest_all: failed to write audit_log row")

    logger.info("harvest_all: %s", changes)
    return {
        "status": "success",
        "candidates": candidates_result,
        "prospects": prospects_result,
        **changes,
    }


# ── Job 2: morning_drafts (registered as scheduler job 'morningdrafts') ──

async def _draft_candidate_outreach() -> Dict[str, int]:
    """Up to DRAFT_CANDIDATE_CAP drafts for candidates with an email,
    matched to an open job, without an existing draft for that job.
    Mirrors services/scheduler.py's draft_outreach() but with no 24h
    recency window (this is a one-shot catch-up job) and a higher cap."""
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
             AND c.email IS NOT NULL
             AND NOT EXISTS (
                 SELECT 1 FROM outreach_drafts d
                 WHERE d.target_type = 'candidate'
                   AND d.target_email = c.email
                   AND d.job_id = m.job_id
             )
           ORDER BY m.match_score DESC
           LIMIT $1""",
        DRAFT_CANDIDATE_CAP,
    )

    drafted = 0
    for row in candidates:
        try:
            draft = await outreach_ai.draft_email(
                target={"name": row["full_name"], "company": row["current_company"]},
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
            logger.exception(
                "morning_drafts: candidate draft failed for candidate=%s job=%s",
                row["candidate_id"], row["job_id"],
            )
            continue

    return {"considered": len(candidates), "drafted": drafted}


async def _draft_prospect_outreach() -> Dict[str, int]:
    """Up to DRAFT_PROSPECT_CAP drafts for freshly-harvested client
    prospects. Bulk harvest never enriches emails, so most prospects have
    contact_email=NULL — those still get a draft with target_email=NULL
    and a body footer pointing at their LinkedIn URL, so a human can
    manually send via LinkedIn instead of email. target_type is
    'client_prospect' so routers/outreach.py's approve endpoint can tell
    these apart from candidate outreach and refuse to email-send them."""
    prospects = await fetch_all(
        """SELECT cp.id, cp.company_name, cp.contact_name, cp.contact_title,
                  cp.contact_email, cp.contact_linkedin, cp.industry
           FROM client_prospects cp
           WHERE cp.status = 'new'
             AND cp.contact_name IS NOT NULL
             AND NOT EXISTS (
                 SELECT 1 FROM outreach_drafts d
                 WHERE d.target_type = 'client_prospect' AND d.target_id = cp.id
             )
           ORDER BY cp.created_at ASC
           LIMIT $1""",
        DRAFT_PROSPECT_CAP,
    )

    drafted = 0
    for row in prospects:
        try:
            role_label = row["contact_title"] or "engineering leadership"
            industry_clause = f", in the {row['industry']} industry" if row["industry"] else ""
            notes = (
                f"This is business development outreach to a potential hiring "
                f"manager/CTO ({role_label}) at their company{industry_clause}. "
                "Introduce GSP Recruitment's specialized embedded software / "
                "mechatronics / cybersecurity talent pool in the Brainport "
                "Eindhoven region and offer to discuss their current hiring "
                "needs. Do not reference any specific job title or hiring "
                "company context — write this as general B2B outreach."
            )
            draft = await outreach_ai.draft_email(
                target={"name": row["contact_name"], "company": row["company_name"]},
                context={"notes": notes},
                language="nl",
            )

            subject = draft["subject"]
            body = draft["body"]
            if not row["contact_email"] and row["contact_linkedin"]:
                body = f"{body}\n\n[LinkedIn] contact via {row['contact_linkedin']}"

            await execute(
                """INSERT INTO outreach_drafts
                   (target_type, target_id, target_email, target_name, company,
                    job_id, channel, language, subject, body, ai_model, status)
                   VALUES ($1,$2,$3,$4,$5,NULL,'email','nl',$6,$7,$8,'draft')""",
                "client_prospect", row["id"], row["contact_email"], row["contact_name"],
                row["company_name"], subject, body, settings.openrouter_chat_model,
            )
            drafted += 1
        except Exception:
            logger.exception("morning_drafts: prospect draft failed for prospect=%s", row["id"])
            continue

    return {"considered": len(prospects), "drafted": drafted}


async def morning_drafts() -> dict:
    """One-shot catch-up draft job: up to DRAFT_CANDIDATE_CAP candidate
    outreach drafts + up to DRAFT_PROSPECT_CAP client-prospect outreach
    drafts. NEVER sends anything — status is always 'draft', same as the
    daily draft_outreach() job. Manual trigger only."""
    if not await _flag_enabled("outreach_drafting_enabled"):
        logger.info("morning_drafts: disabled via system_settings, skipping")
        return {"status": "skipped", "reason": "outreach_drafting_enabled=false"}

    candidate_result = await _draft_candidate_outreach()
    prospect_result = await _draft_prospect_outreach()

    logger.info(
        "morning_drafts: candidates=%s prospects=%s", candidate_result, prospect_result
    )
    return {
        "status": "success",
        "candidates": candidate_result,
        "prospects": prospect_result,
    }
