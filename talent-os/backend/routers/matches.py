"""
Talent OS — Matches router (asyncpg, auth-protected).
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from core.database import fetch_all, fetch_one, execute
from core.security import verify_api_key
from services.matcher import EmbeddingMatcher
from models.schemas import MatchCreate
from typing import Optional

logger = logging.getLogger("talent_os.matches")

router = APIRouter(prefix="/api/matches", tags=["matches"], dependencies=[Depends(verify_api_key)])


# ── De matchscore-schaal, op één plek ───────────────────────────────────
#
# `matches.match_score` staat overal op de 0-100-schaal, terwijl
# services/matcher.py intern met cosinusgelijkenis op 0-1 rekent en bij
# het opslaan vermenigvuldigt (`round(score * 100, 2)`, zie
# _run_matching_for_job hieronder). Die twee getallen stonden tot WS3c
# als losse literals in deze module; iedere andere lezer van
# `match_score` moest de omrekening zelf raden.
#
# MATCH_SUGGESTION_MIN_SCORE is de drempel waaronder de matcher een
# kandidaat helemaal niet als 'suggested' wegschrijft;
# MATCH_SUGGESTION_MIN_STORED_SCORE is diezelfde drempel op de schaal
# zoals hij in de kolom staat. services/scheduler.py's job_alert_job
# leest die tweede: een kandidaat krijgt alleen een alert over matches
# die minstens zo goed zijn als wat deze codebase zelf een suggestie
# durft te noemen -- geen apart, verzonnen getal.
#
# Wat die ondergrens NIET is, want het commentaar hier suggereerde dat
# eerder wel (CR R5): hij is geen poort op wat er in de kolom komt. POST
# /api/matches (een externe routine achter dezelfde X-API-Key) schrijft
# nog steeds elke `match_score` weg die de aanroeper meestuurt, ook 1.0,
# en niets in dit bestand weigert dat. De ondergrens zit uitsluitend aan
# de LEESKANT, in services/scheduler.py's JOB_ALERT_MATCHES_SQL: zo'n rij
# bestaat, is zichtbaar in het admin-paneel, en telt alleen niet mee voor
# een alert. Wie wil dat hij ook niet wordt opgeslagen, moet dat in
# create_match afdwingen -- dat is een aparte keuze en die is hier niet
# gemaakt.
MATCH_SCORE_SCALE = 100
MATCH_SUGGESTION_MIN_SCORE = 0.3
MATCH_SUGGESTION_MIN_STORED_SCORE = MATCH_SUGGESTION_MIN_SCORE * MATCH_SCORE_SCALE


def _consent_gate_sql(prefix: str = "") -> str:
    """FIX 3 (chief-of-staff, ai-pseudonimisering branch): the matching gate
    used to accept `source_url OR lawful_basis = 'opt_in_talentpool'`
    without checking whether that talentpool consent was still valid --
    routers/outreach.py's send-time gate (_draft_refusal) already refuses
    an expired/never-set consent_talentpool_until outright (WS-C.17,
    SOP §1.5), so matching was strictly wider than sending: someone whose
    consent had lapsed stayed matchable (and, via POST /api/matches,
    readable back by name through GET /api/matches/job/{job_id}).
    This mirrors outreach.py's gate exactly (minus the Art.14-notice check,
    which only applies to a drafted message body, not to matching):
    opt_in_talentpool requires a still-valid consent_talentpool_until;
    every other basis requires a public http(s) source_url on file."""
    p = prefix
    return (
        f"({p}lawful_basis = 'opt_in_talentpool' AND {p}consent_talentpool_until IS NOT NULL "
        f"AND {p}consent_talentpool_until > NOW()) "
        f"OR ({p}lawful_basis IS NOT NULL AND {p}lawful_basis != 'opt_in_talentpool' "
        f"AND {p}source_url ~* '^https?://')"
    )


async def _run_matching_for_job(job_id: int) -> None:
    """Embed the job against all active candidates and upsert match rows.
    Runs in a FastAPI background task — no Celery/Redis required."""
    matcher = EmbeddingMatcher()
    try:
        job = await fetch_one(
            "SELECT id, title, description, requirements FROM job_orders "
            "WHERE id = $1 AND deleted_at IS NULL",
            job_id,
        )
        if not job:
            logger.warning("matching: job %s not found", job_id)
            return

        # See the FIX 1 note in candidates_for_job() below for why
        # talentpool opt-ins (no source_url, lawful_basis=
        # 'opt_in_talentpool') get the same exception here, and the FIX 3
        # note on _consent_gate_sql() for why that exception now also
        # requires a still-valid consent_talentpool_until.
        candidates = await fetch_all(
            f"SELECT id, full_name, current_title, education, years_experience, skills "
            f"FROM candidates "
            f"WHERE deleted_at IS NULL AND consent_withdrawn_at IS NULL "
            f"AND ({_consent_gate_sql()})",
        )
        if not candidates:
            logger.info("matching: no candidates to match for job %s", job_id)
            return

        job_text = f"{job['title']} {job['description'] or ''} {job['requirements'] or ''}"
        results = await matcher.match_job_to_candidates(
            job_text, [dict(c) for c in candidates], min_score=MATCH_SUGGESTION_MIN_SCORE,
        )

        for r in results:
            # match_score is stored on the 0–100 scale everywhere.
            # WS-E.8 follow-up (security-audit FIX FIRST, retention-kolommen
            # branch, blocking point 1): updated_at is the anchor
            # core/retention.py's rejected_applicant guard checks (a fresh
            # match after a rejection must block the purge) -- it must be
            # stamped on both the initial insert and every re-score, or the
            # guard stays permanently NULL/dead.
            await execute(
                """INSERT INTO matches (candidate_id, job_id, match_score, status, updated_at)
                   VALUES ($1, $2, $3, 'suggested', NOW())
                   ON CONFLICT (candidate_id, job_id)
                   DO UPDATE SET match_score = EXCLUDED.match_score, updated_at = NOW()
                   WHERE matches.status = 'suggested'""",
                r["candidate_id"], job_id, r["match_score"],
            )
        logger.info("matching: job %s matched against %s candidates, %s results",
                    job_id, len(candidates), len(results))
    except Exception:
        logger.exception("matching: failed for job %s", job_id)
    finally:
        await matcher.close()


@router.post("/run", status_code=202)
async def run_matching(
    background_tasks: BackgroundTasks,
    job_id: Optional[int] = Query(None, description="Match one job; omit to match all open jobs"),
):
    """Trigger semantic matching (OpenRouter embeddings) as a background task."""
    if job_id is not None:
        job = await fetch_one(
            "SELECT id FROM job_orders WHERE id = $1 AND deleted_at IS NULL", job_id,
        )
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        background_tasks.add_task(_run_matching_for_job, job_id)
        return {"message": "Matching started", "job_ids": [job_id]}

    jobs = await fetch_all(
        "SELECT id FROM job_orders WHERE status = 'open' AND deleted_at IS NULL AND is_demo = false",
    )
    for j in jobs:
        background_tasks.add_task(_run_matching_for_job, j["id"])
    return {"message": "Matching started", "job_ids": [j["id"] for j in jobs]}


@router.post("", status_code=201)
async def create_match(payload: MatchCreate):
    """Create/upsert a match. Lets an external agent (e.g. a Claude cloud
    agent doing matching) write results directly, instead of the in-backend
    OpenRouter matcher in _run_matching_for_job. Same upsert semantics as
    that job. `rationale` is accepted but not persisted — no column for it
    yet.

    FIX 1 (chief-of-staff, ai-pseudonimisering branch): this endpoint used
    to only check `deleted_at IS NULL` on the candidate, so any caller with
    the shared X-API-Key could create a match for an arbitrary
    candidate_id -- including withdrawn-consent rows and the purchased
    Apollo pool -- and then read the name back via
    GET /api/matches/job/{job_id}. Give it the same eligibility check as
    _run_matching_for_job / candidates_for_job."""
    candidate = await fetch_one(
        f"SELECT id FROM candidates WHERE id = $1 AND deleted_at IS NULL "
        f"AND consent_withdrawn_at IS NULL AND ({_consent_gate_sql()})",
        payload.candidate_id,
    )
    if not candidate:
        raise HTTPException(status_code=400, detail=f"Candidate {payload.candidate_id} not found")

    job = await fetch_one(
        "SELECT id FROM job_orders WHERE id = $1 AND deleted_at IS NULL", payload.job_id,
    )
    if not job:
        raise HTTPException(status_code=400, detail=f"Job {payload.job_id} not found")

    # WS-E.8 follow-up (security-audit FIX FIRST, retention-kolommen branch,
    # blocking point 1): same updated_at stamp as _run_matching_for_job --
    # this is the endpoint an external agent uses to progress a match's
    # status (e.g. off 'suggested'), which is exactly the activity
    # core/retention.py's rejected_applicant guard needs to see.
    row = await fetch_one(
        """INSERT INTO matches (candidate_id, job_id, match_score, status, updated_at)
           VALUES ($1, $2, $3, $4, NOW())
           ON CONFLICT (candidate_id, job_id)
           DO UPDATE SET match_score = EXCLUDED.match_score, status = EXCLUDED.status, updated_at = NOW()
           WHERE matches.status = 'suggested'
           RETURNING *""",
        payload.candidate_id, payload.job_id, payload.match_score, payload.status,
    )
    return row


@router.get("/candidates-for-job/{job_id}")
async def candidates_for_job(job_id: int, limit: int = Query(30, ge=1, le=100)):
    """Cheap keyword-overlap prefilter — NO AI, NO OpenRouter. Ranks active
    candidates against a job's title/requirements so an external agent (e.g.
    a Claude cloud agent) can shortlist without pulling all candidates.

    Deliberately returns no name and no CV text (VERWERKINGSREGISTER.md
    §2.6 measure A3): round two of the privacy audit found that
    regex-cleaning free CV text cannot be made reliably sound (addresses
    without a recognised street-type suffix, foreign addresses, non-ISO
    dates all survived), so the fix is not sending it at all rather than
    cleaning it harder. `id` (the candidate's id, i.e. `candidate_id`),
    `current_title`, `skills`, `location` and `current_company` are enough
    for an external agent to shortlist and write matches back with
    `POST /api/matches` keyed on `candidate_id` — it never needs the
    person's name or CV prose to do that."""
    job = await fetch_one(
        "SELECT id, title, description, requirements FROM job_orders "
        "WHERE id = $1 AND deleted_at IS NULL", job_id,
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_text = f"{job['title'] or ''} {job['requirements'] or ''}"
    # Cheap tokenization for the skills-overlap bonus: distinct alphanumeric
    # words of length >= 3, lowercased.
    tokens = sorted(set(
        w for w in job_text.lower().replace("/", " ").replace(",", " ").split()
        if len(w) >= 3
    ))
    if not tokens:
        return []

    # Rank on the existing `cv_search` tsvector (GIN-indexed, dutch stemmed)
    # plus a bonus for skills[] overlap with the job's keyword tokens
    # (also GIN-indexed) — no AI/embeddings involved. cv_search still feeds
    # the ranking score (cv_rank) even though cv_text itself is never
    # returned below.
    # NOTE: the source_url filter below (VERWERKINGSREGISTER.md rij 1, §2.6
    # measure A1) excludes the whole Apollo-bulk pool, which is also most of
    # where empty skills[]/cv_text rows lived — the remaining pool is mostly
    # rows with real profile text, but current_title is still ranked
    # primarily since it's the one field guaranteed to be populated.
    # FIX (chief-of-staff, ai-pseudonimisering FIX 1): a talentpool opt-in
    # row never gets a source_url (routers/public.py's confirm_talentpool_
    # optin() only sets lawful_basis='opt_in_talentpool') so the bare
    # source_url check silently dropped exactly the group with the
    # strongest legal basis. `pool_origin` (migration 022) was considered
    # instead but not used here -- services/harvest.py and
    # services/scheduler.py's Apollo INSERTs do stamp pool_origin =
    # 'apollo' going forward (routers/retention_admin.py's Apollo-pool-
    # purge selector needs that), but a pre-existing row sourced between
    # migration 022's one-time backfill and that fix would still read
    # NULL, and `pool_origin IS DISTINCT FROM 'apollo'` would silently let
    # such a row straight into matching. source_url stays the Apollo-pool
    # signal here for that reason; we widen it with the same
    # opt_in_talentpool exception routers/outreach.py's _draft_refusal()
    # already relies on (WS-C.17 / SOP §1.5).
    rows = await fetch_all(
        f"""SELECT * FROM (
               SELECT c.id, c.current_title, c.current_company, c.skills,
                      c.location, c.years_experience, c.updated_at,
                      ts_rank(to_tsvector('dutch', coalesce(c.current_title, '')),
                              plainto_tsquery('dutch', $1)) AS title_rank,
                      ts_rank(c.cv_search, plainto_tsquery('dutch', $1)) AS cv_rank,
                      (SELECT COUNT(*) FROM unnest(c.skills) s WHERE lower(s) = ANY($2::text[])) AS skill_matches
               FROM candidates c
               WHERE c.deleted_at IS NULL AND c.consent_withdrawn_at IS NULL
                 AND ({_consent_gate_sql("c.")})
           ) ranked
           ORDER BY (title_rank + cv_rank + skill_matches * 0.05) DESC, updated_at DESC NULLS LAST
           LIMIT $3""",
        job_text, tokens, limit,
    )

    return [
        {
            "id": r["id"],
            "current_title": r["current_title"],
            "current_company": r["current_company"],
            "skills": r["skills"] or [],
            "location": r["location"],
            "years_experience": float(r["years_experience"]) if r["years_experience"] is not None else None,
            "cv_rank": float(r["cv_rank"]),
            "skill_matches": r["skill_matches"],
        }
        for r in rows
    ]


@router.get("")
async def list_matches(
    job_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    limit: int = Query(50, ge=1, le=200),
):
    """List matches with optional filters."""
    conditions = []
    params = []
    idx = 1

    if job_id is not None:
        conditions.append(f"job_id = ${idx}")
        params.append(job_id)
        idx += 1
    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if min_score is not None:
        conditions.append(f"match_score >= ${idx}")
        params.append(min_score)
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(limit)
    sql = f"SELECT * FROM matches {where} ORDER BY match_score DESC LIMIT ${idx}"

    rows = await fetch_all(sql, *params)
    return rows


@router.get("/{match_id}")
async def get_match(match_id: int):
    """Get a single match by ID."""
    row = await fetch_one("SELECT * FROM matches WHERE id = $1", match_id)
    if not row:
        raise HTTPException(status_code=404, detail="Match not found")
    return row


@router.get("/job/{job_id}")
async def get_job_matches(job_id: int, min_score: float = Query(0, ge=0, le=100)):
    """Get all matches for a specific job, sorted by score.

    FIX 2 (chief-of-staff, ai-pseudonimisering branch, ronde 5): this
    endpoint sits behind X-API-Key, not a client/admin JWT, so its only
    real caller can be an external routine, not a human recruiter --
    the earlier docstring's "a human recruiter created or confirmed [a
    match] in order to decide who to draft outreach for" was an
    unverified assumption. A repo-wide grep of website/ (incl.
    website/admin/), app/, scripts/ and docs/ turns up zero call sites
    for /api/matches (any sub-path); VERWERKINGSREGISTER.md rij 4 already
    documents the actual consumer as the external matching routine, keyed
    on candidate_id via candidates-for-job / POST /api/matches, which
    never needed a name. So this endpoint gets the same treatment as
    candidates-for-job: no full_name. A caller that needs the name for a
    specific candidate_id it already holds can still look it up through
    an endpoint that carries its own justification (e.g. the admin panel,
    behind the JWT). Gate it exactly like matching itself
    (_consent_gate_sql) -- unchanged from the previous fix: no match (or
    anything behind it) for a candidate who was soft-deleted, withdrew
    consent, or never had a valid lawful basis in the first place."""
    rows = await fetch_all(
        f"SELECT m.*, c.current_title, c.current_company "
        f"FROM matches m JOIN candidates c ON m.candidate_id = c.id "
        f"WHERE m.job_id = $1 AND m.match_score >= $2 "
        f"AND c.deleted_at IS NULL AND c.consent_withdrawn_at IS NULL "
        f"AND ({_consent_gate_sql('c.')}) "
        f"ORDER BY m.match_score DESC",
        job_id, min_score,
    )
    return rows