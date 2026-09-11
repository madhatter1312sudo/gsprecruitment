"""
Talent OS — Public API Router.
Unauthenticated endpoints for site content, salary benchmarks, and lead submission.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from core.database import fetch_all, fetch_one, execute
from core.config import settings
from core.deps import get_optional_user
from core.security import hash_token
from core import privacy
from models.schemas import (
    SiteContentResponse, LeadSubmit, SalaryBenchmarkResponse, QuizSubmitRequest,
    TalentpoolOptinRequest, TalentpoolConfirmRequest, UnsubscribeRequest,
    UNSUBSCRIBE_SCOPES,
)
from services.notify import notify_owner
from services.email_service import email_service
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import json
import logging
import random
import secrets

logger = logging.getLogger("talent_os.public")

router = APIRouter(prefix="/api/v1/public", tags=["public"])

from core.ratelimit import limiter

# ── Talentpool opt-in (WS-C.17) ─────────────────────────────────────────
# Separate router: this and the public jobs router (routers/jobs.py
# public_jobs_router) are the only /api/public/* (no /v1) endpoints --
# see CLAUDE.md "Public: /api/public/jobs, /api/v1/public/blog".
talentpool_public_router = APIRouter(prefix="/api/public", tags=["public-talentpool"])

TALENTPOOL_OPTIN_TOKEN_TTL_HOURS = 24


# ── Site Content ────────────────────────────────────────────────────────

@router.get("/site-content", response_model=SiteContentResponse)
@limiter.limit("30/minute")
async def get_site_content(request: Request, response: Response, section: str = Query(..., description="Content section (e.g. hero, features, about)")):
    """Get site content by section."""
    response.headers["Cache-Control"] = "public, max-age=300"
    rows = await fetch_all(
        "SELECT * FROM site_content WHERE section = $1 ORDER BY sort_order, key",
        section,
    )
    if not rows:
        # Return empty rather than 404 so the frontend can handle it
        return SiteContentResponse(section=section, items=[])

    items = []
    for row in rows:
        items.append({
            "id": row["id"],
            "key": row["key"],
            "value": row["value"],
            "label": row.get("label"),
            "sort_order": row.get("sort_order", 0),
        })

    return SiteContentResponse(section=section, items=items)


# ── Salary Data ─────────────────────────────────────────────────────────

@router.get("/salary-data", response_model=List[SalaryBenchmarkResponse])
@limiter.limit("30/minute")
async def get_public_salary_data(request: Request, response: Response,
    role_title: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    seniority: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Get salary benchmark data (public)."""
    response.headers["Cache-Control"] = "public, max-age=300"
    conditions = []
    params = []
    idx = 1

    if role_title:
        conditions.append(f"role_title ILIKE ${idx}")
        params.append(f"%{role_title}%")
        idx += 1
    if location:
        conditions.append(f"location ILIKE ${idx}")
        params.append(f"%{location}%")
        idx += 1
    if seniority:
        conditions.append(f"seniority = ${idx}")
        params.append(seniority)
        idx += 1

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    params.append(limit)

    rows = await fetch_all(
        f"SELECT * FROM salary_benchmarks {where} ORDER BY role_title LIMIT ${idx}",
        *params,
    )
    return rows


# ── Lead Submission ─────────────────────────────────────────────────────

@router.get("/blog")
@limiter.limit("30/minute")
async def list_blog_posts(request: Request, response: Response):
    """List published blog posts, newest first."""
    response.headers["Cache-Control"] = "public, max-age=300"
    rows = await fetch_all(
        """SELECT slug, title_nl, title_en, excerpt_nl, excerpt_en, tags,
                  read_time_min, published_at
           FROM blog_posts
           WHERE status = 'published'
           ORDER BY published_at DESC""",
    )
    return rows


@router.get("/blog/{slug}")
@limiter.limit("30/minute")
async def get_blog_post(request: Request, response: Response, slug: str):
    """Get a single published blog post by slug, including full bodies."""
    response.headers["Cache-Control"] = "public, max-age=300"
    row = await fetch_one(
        "SELECT * FROM blog_posts WHERE slug = $1 AND status = 'published'",
        slug,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return row


QUIZ_DOMAINS = ["embedded_cpp", "general_swe", "cloud_devops", "security"]
QUIZ_PER_DOMAIN = 3


@router.get("/quiz")
@limiter.limit("30/minute")
async def get_quiz(request: Request, response: Response, lang: str = Query("nl", pattern="^(nl|en)$")):
    """Get 12 random active quiz questions, balanced 3 per domain (mixed
    difficulty). Never includes correct_index or explanations — those are
    only returned by /quiz/submit, after grading."""
    response.headers["Cache-Control"] = "no-store"
    question_col = "question_nl" if lang == "nl" else "question_en"
    options_col = "options_nl" if lang == "nl" else "options_en"

    items = []
    for domain in QUIZ_DOMAINS:
        rows = await fetch_all(
            f"""SELECT id, domain, difficulty, {question_col} AS question, {options_col} AS options
                FROM quiz_questions
                WHERE domain = $1 AND active = TRUE
                ORDER BY RANDOM()
                LIMIT {QUIZ_PER_DOMAIN}""",
            domain,
        )
        for row in rows:
            # asyncpg returns JSONB columns as raw JSON text (no codec registered)
            if isinstance(row["options"], str):
                row["options"] = json.loads(row["options"])
        items.extend(rows)

    random.shuffle(items)
    return {"lang": lang, "items": items}


@router.post("/quiz/submit")
@limiter.limit("10/minute")
async def submit_quiz(
    request: Request,
    data: QuizSubmitRequest,
    lang: str = Query("nl", pattern="^(nl|en)$"),
    current_user: Optional[dict] = Depends(get_optional_user),
):
    """Grade a quiz submission server-side and store it. Correct answers and
    explanations are only ever exposed here, after submission — never by
    GET /quiz."""
    question_ids = [a.question_id for a in data.answers]

    explanation_col = "explanation_nl" if lang == "nl" else "explanation_en"
    rows = await fetch_all(
        f"""SELECT id, domain, correct_index, {explanation_col} AS explanation
            FROM quiz_questions
            WHERE id = ANY($1::int[]) AND active = TRUE""",
        question_ids,
    )
    questions_by_id = {r["id"]: r for r in rows}

    score = 0
    max_score = 0
    domain_scores: dict = {}
    feedback = []

    for answer in data.answers:
        q = questions_by_id.get(answer.question_id)
        if not q:
            continue
        max_score += 1
        bucket = domain_scores.setdefault(q["domain"], {"correct": 0, "total": 0})
        bucket["total"] += 1
        is_correct = answer.answer_index == q["correct_index"]
        if is_correct:
            score += 1
            bucket["correct"] += 1
        feedback.append({
            "question_id": answer.question_id,
            "correct": is_correct,
            "correct_index": q["correct_index"],
            "explanation": q["explanation"],
        })

    if max_score == 0:
        raise HTTPException(status_code=400, detail="None of the submitted question IDs are valid/active")

    pct = (score / max_score) * 100
    if pct < 40:
        tier = "Junior-indicatie"
    elif pct <= 70:
        tier = "Medior-indicatie"
    else:
        tier = "Senior-indicatie"

    user_id = current_user["id"] if current_user else None
    email = data.email.lower().strip() if data.email else None

    await execute(
        """INSERT INTO quiz_submissions
           (email, user_id, answers, score, max_score, tier, domain_scores, source_page, referrer_host)
           VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7::jsonb, $8, $9)""",
        email, user_id,
        json.dumps([a.model_dump() for a in data.answers]),
        score, max_score, tier,
        json.dumps(domain_scores),
        data.source_page, data.referrer_host,
    )

    return {
        "score": score,
        "max_score": max_score,
        "tier": tier,
        "domain_scores": domain_scores,
        "feedback": feedback,
    }


@router.post("/lead", status_code=201)
@limiter.limit("10/minute")
async def submit_lead(request: Request, data: LeadSubmit):
    """Submit a lead or contact form entry."""
    # Store the lead submission
    lead = await fetch_one(
        """INSERT INTO contact_submissions
           (name, email, company, phone, message, interest_type, source_page, referrer_host)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
           RETURNING id, created_at""",
        data.name, data.email.lower().strip(), data.company,
        data.phone, data.message, data.interest_type,
        data.source_page, data.referrer_host,
    )
    if not lead:
        raise HTTPException(status_code=500, detail="Failed to submit lead")

    # WS-C.10 + WS3: best-effort ops notification via notify_owner() --
    # Telegram side is unchanged (no-ops without TELEGRAM_BOT_TOKEN/
    # TELEGRAM_CHAT_ID, never carries the submitter's name or e-mail,
    # services/telegram.py docstring); an OWNER_NOTIFY_EMAIL, if set, may
    # additionally get name/interest (services/notify.py) -- never the
    # e-mail address or company, the deeplink already opens the lead in
    # the admin panel. Must never fail the submission itself --
    # notify_owner() is itself best-effort and never raises.
    await notify_owner("lead", {
        "interest_type": data.interest_type,
        "submitted_at": lead["created_at"],
        "full_name": data.name,
        "anchor": "leads",
    })

    return {
        "message": "Thank you! We'll get back to you shortly.",
        "id": lead["id"],
        "created_at": lead["created_at"],
    }


# ── Talentpool opt-in / confirm (WS-C.17) ───────────────────────────────
# docs/SOURCING-SOP.md §1.5: consent's own touchpoint is the site itself,
# so no source_url is required or stored for candidates created this way.
# Two-step, double-opt-in flow (mirrors WS-E.2's e-mail verification,
# routers/auth.py) so a mistyped or someone-else's e-mail address can
# never be enrolled from a single form submission -- consent only becomes
# effective once POST /talentpool-confirm consumes the token. Only the
# token's sha256 hash is ever stored (core.security.hash_token); the raw
# token exists only in the outbound e-mail.

async def _send_talentpool_confirm_email(email: str, token: str, job_title: Optional[str] = None) -> None:
    # Security-audit fix (H1): the token goes in the URL *fragment*
    # (#token=), never a ?token= query param -- a fragment is never sent
    # to the server in the request line and never appears in access logs
    # or a Referer header. website/talentpool-confirm.html/.js reads it
    # from window.location.hash to match.
    link = f"https://gsprecruitment.nl/talentpool-confirm#token={token}"
    # WS3: content moved into services/email_templates.py's
    # "talentpool_confirm" template (same link, same promise, same
    # optional job_title line as before) -- this function only builds the
    # link and hands off to send_template(). Never logs job_title or the
    # recipient's e-mail address -- see the plain logger.warning() below.
    sent = await email_service.send_template(
        "talentpool_confirm", email,
        {"link": link, "ttl_hours": TALENTPOOL_OPTIN_TOKEN_TTL_HOURS, "job_title": job_title},
    )
    if not sent:
        logger.warning("Failed to send talentpool opt-in confirmation email")


@talentpool_public_router.post("/talentpool-optin", status_code=202)
@limiter.limit("5/minute")
async def talentpool_optin(request: Request, data: TalentpoolOptinRequest):
    """Step 1: e-mail + consent tick from website/kandidaten.html or the
    blog CTA. Never touches `candidates` directly -- only issues a
    confirmation e-mail with a one-time token. Always returns the same
    generic message and status code regardless of consent value, whether
    the e-mail is already known, whether it's suppressed, or whether a
    request was just sent -- this endpoint must never be usable to
    enumerate e-mails or probe existing candidates/suppression state
    (same no-enumeration pattern as routers/auth.py resend_verification).

    Security-audit fix (L1): skips actually sending (no row inserted, no
    e-mail sent -- but still returns 202 with the same message) when
    either holds:
      - the address is on suppression_list (STOP received -- never
        e-mail it again, on any basis);
      - an unconfirmed request for this same (e-mail, job_id) pair was
        already made in the last 10 minutes (double-submit / repeated-
        click guard -- avoids sending a fresh token + e-mail for every
        click on the same apply button).

    WS-4 (migrations/037): job_id, when given, is only ever stored after
    it resolves to a currently open, non-demo, non-deleted job order --
    the same eligibility PUBLIC_JOB_WHERE (routers/jobs.py) uses for what
    the public board itself shows. An unknown, closed, demo, or deleted
    job_id is silently dropped (the row is still created without one) so
    this endpoint keeps its no-enumeration posture for job existence too.

    Chief-of-staff FIX FIRST: the repeated-click guard used to key only
    on e-mail, so a candidate applying to a second vacancy within ten
    minutes of the first (e.g. the junior/medior/senior variants of the
    same title) got the same generic 202 back but no second row, no
    second job_id and no confirmation e-mail for that second role -- the
    application looked accepted and silently wasn't. The guard now keys
    on (e-mail, resolved job_id) instead, with `IS NOT DISTINCT FROM` so
    NULL job_id (a general, not-tied-to-one-vacancy signup) still
    dedupes against NULL job_id the same as before; a different job_id
    is a different application and gets its own row and e-mail."""
    email = data.email.lower().strip()
    if data.consent:
        suppressed = await fetch_one(
            "SELECT 1 FROM suppression_list WHERE email_hash = $1", privacy.email_hash(email),
        )
        if not suppressed:
            job = None
            if data.job_id is not None:
                job = await fetch_one(
                    "SELECT id, title FROM job_orders "
                    "WHERE id = $1 AND status = 'open' AND is_demo = false AND deleted_at IS NULL",
                    data.job_id,
                )
            job_id = job["id"] if job else None

            recent_pending = await fetch_one(
                """SELECT id FROM talentpool_optin_requests
                   WHERE LOWER(email) = $1 AND job_id IS NOT DISTINCT FROM $2
                     AND confirmed_at IS NULL
                     AND requested_at > NOW() - INTERVAL '10 minutes'""",
                email, job_id,
            )
            if not recent_pending:
                token = secrets.token_urlsafe(32)
                await execute(
                    """INSERT INTO talentpool_optin_requests
                         (email, token_hash, scope, source, job_id, job_alerts)
                       VALUES ($1, $2, $3, $4, $5, $6)""",
                    email, hash_token(token), data.scope, data.source, job_id, data.job_alerts,
                )
                await _send_talentpool_confirm_email(email, token, job_title=job["title"] if job else None)

    return {
        "message": "If you ticked the consent box, we've sent a confirmation link to that e-mail address.",
    }


@talentpool_public_router.post("/talentpool-confirm")
@limiter.limit("10/minute")
async def talentpool_confirm(request: Request, data: TalentpoolConfirmRequest):
    """Step 2: consumes the one-time token from the confirmation e-mail.
    Only here does consent become effective on the candidates row --
    creating it (source='talentpool_optin', no source_url — SOP §1.5) if
    this e-mail has no existing candidates row, or updating it in place
    otherwise. lawful_basis is set to 'opt_in_talentpool' only via the
    shared privacy.should_set_talentpool_lawful_basis() rule (H3a) --
    never silently overwriting a different lawful_basis already on file
    (portal_registratie included -- same rule as the portal endpoint).

    WS-4 (migrations/037): if the original request carried a job_id, and
    that job is still open/non-demo/non-deleted at confirm time (it may
    have closed between opt-in and confirm), this also records the
    application as a matches row with status='applied' -- upsert pattern
    mirrors routers/matches.py's ON CONFLICT (candidate_id, job_id) DO
    UPDATE ... WHERE matches.status = 'suggested', so an existing
    'suggested' match becomes 'applied' rather than being duplicated, and
    a match already past 'suggested' (e.g. already 'applied') is left
    alone. Calling this endpoint twice with the same token 400s on the
    second call (confirmed_at is no longer NULL), so the match/candidate
    side effects only ever happen once per token."""
    token_hash = hash_token(data.token)
    pending = await fetch_one(
        """SELECT id, email, scope, source, job_id, job_alerts FROM talentpool_optin_requests
           WHERE token_hash = $1 AND confirmed_at IS NULL
             AND requested_at > NOW() - INTERVAL '24 hours'""",
        token_hash,
    )
    if not pending:
        raise HTTPException(status_code=400, detail="Invalid or expired confirmation token")

    await execute(
        "UPDATE talentpool_optin_requests SET confirmed_at = NOW() WHERE id = $1", pending["id"],
    )

    now = datetime.now(timezone.utc)
    until = now + timedelta(days=365)  # 12 months, renewable

    # WS3b: a request created by POST /api/v1/admin/candidates/referral
    # carries source='referral'. Clicking that link is the referred
    # person's own, first and only act in this flow, so it stamps
    # candidates.referral_confirmed_at -- core/retention.py's
    # REFERRAL_NO_RESPONSE_SQL reads exactly that column as this
    # category's reaction signal (see its comment there).
    is_referral = pending["source"] == "referral"

    # WS3c: the job_alerts tick from migrations/037 lives on
    # talentpool_optin_requests until here; confirming carries it over to
    # candidates.job_alert_optin_at, which is what services/scheduler.py's
    # job_alert_job selects on. Only ever set, never cleared, and only on
    # a tick: an unticked box must not silently revoke an opt-in this
    # person made earlier through the portal switch. Someone who
    # unsubscribed before (job_alert_unsubscribed_at set) does NOT get
    # re-enrolled by a later talentpool confirm -- an unsubscribe is a
    # withdrawal and only the person's own, explicit re-opt-in through
    # PUT /api/v1/candidate/job-alerts clears it.
    #
    # R5: het vinkje telt alleen bij `scope = 'matching_and_contact'`.
    # `matching_only` betekent letterlijk "wel matchen, geen contact", en
    # core/retention.py's JOB_ALERT_ELIGIBILITY_SQL eist dan ook precies
    # die scope -- een `matching_only`-rij wordt door de alertselector
    # nooit opgepikt. Toch `job_alert_optin_at` stempelen levert een kolom
    # op die zegt dat deze persoon alerts wil terwijl hij er nooit een
    # krijgt: het portaal toont "aan", de export toont een opt-in die er
    # niet is, en zet hij later zijn scope om, dan begint de mail te lopen
    # zonder dat hij daar op dat moment iets over heeft gezegd. Het
    # vinkje wordt dus genegeerd, niet stilzwijgend bewaard.
    wants_alerts = bool(pending["job_alerts"]) and pending["scope"] == "matching_and_contact"

    existing = await fetch_one(
        "SELECT id, lawful_basis FROM candidates WHERE LOWER(email) = $1", pending["email"],
    )
    if existing:
        # Security-audit B1. `should_set_talentpool_lawful_basis()` only
        # says yes for NULL or an existing 'opt_in_talentpool', so a
        # referral that confirms here kept `lawful_basis =
        # 'toestemming_referral'` -- and then fell out of EVERY retention
        # row at once: core/retention.py's REFERRAL_NO_RESPONSE_SQL
        # excludes him the moment `referral_confirmed_at` is stamped,
        # while TALENTPOOL_EXPIRED_SQL only ever looks at
        # 'opt_in_talentpool'. The same mismatch kept him out of
        # routers/matches.py's `_consent_gate_sql()` and out of
        # routers/outreach.py's `_draft_refusal()`: consent confirmed, and
        # unusable and unbounded at the same time.
        #
        # Confirming here IS the talentpool opt-in (this is the same
        # double-opt-in token flow, and the UPDATE below writes all four
        # consent_talentpool_* columns regardless), so the basis becomes
        # the one that describes what actually happened. That is not the
        # thing H3a guards against: H3a forbids overwriting a DIFFERENT,
        # stronger basis (portal_registratie, gerechtvaardigd_belang)
        # behind the person's back. 'toestemming_referral' is the same
        # kind of basis -- consent -- for the same person, upgraded by
        # that person's own click, and only for the request this referral
        # created. From here he falls under exactly one retention row:
        # talentpool_consent, 12 months plus the 30-day grace.
        set_lawful_basis = privacy.should_set_talentpool_lawful_basis(existing["lawful_basis"]) or (
            is_referral and existing["lawful_basis"] == "toestemming_referral"
        )
        row = await fetch_one(
            """UPDATE candidates
               SET consent_talentpool_at = $1, consent_talentpool_until = $2,
                   consent_scope = $3, consent_source = $4, consent_reminder_sent_at = NULL,
                   lawful_basis = CASE WHEN $5 THEN 'opt_in_talentpool' ELSE lawful_basis END,
                   referral_confirmed_at = CASE WHEN $6 THEN COALESCE(referral_confirmed_at, NOW())
                                                ELSE referral_confirmed_at END,
                   job_alert_optin_at = CASE
                       WHEN $7 AND job_alert_unsubscribed_at IS NULL
                       THEN COALESCE(job_alert_optin_at, NOW())
                       ELSE job_alert_optin_at END,
                   updated_at = NOW()
               WHERE id = $8
               RETURNING id, lawful_basis, consent_talentpool_at, consent_talentpool_until""",
            now, until, pending["scope"], pending["source"], set_lawful_basis,
            is_referral, wants_alerts, existing["id"],
        )
    else:
        row = await fetch_one(
            """INSERT INTO candidates
               (full_name, email, source, lawful_basis, date_found,
                consent_talentpool_at, consent_talentpool_until, consent_scope, consent_source,
                referral_confirmed_at, job_alert_optin_at)
               VALUES ($1, $2, 'talentpool_optin', 'opt_in_talentpool', CURRENT_DATE, $3, $4, $5, $6,
                       CASE WHEN $7 THEN NOW() ELSE NULL END,
                       CASE WHEN $8 THEN NOW() ELSE NULL END)
               RETURNING id, lawful_basis, consent_talentpool_at, consent_talentpool_until""",
            pending["email"], pending["email"], now, until, pending["scope"], pending["source"],
            is_referral, wants_alerts,
        )

    applied_job = None
    if pending["job_id"] is not None:
        job = await fetch_one(
            "SELECT id, title FROM job_orders "
            "WHERE id = $1 AND status = 'open' AND is_demo = false AND deleted_at IS NULL",
            pending["job_id"],
        )
        if job:
            await execute(
                """INSERT INTO matches (candidate_id, job_id, status)
                   VALUES ($1, $2, 'applied')
                   ON CONFLICT (candidate_id, job_id)
                   DO UPDATE SET status = 'applied'
                   WHERE matches.status = 'suggested'""",
                row["id"], job["id"],
            )
            applied_job = {"id": job["id"], "title": job["title"]}

    # WS3: best-effort owner notification -- Telegram gets only the event
    # and a timestamp (services/notify.py), the optional owner e-mail may
    # also carry the vacancy title (applied_job), never carries this
    # person's name or e-mail address (this flow never had a name to
    # begin with -- talentpool opt-in only ever collects an e-mail).
    await notify_owner("talentpool_confirmed", {
        "job_title": applied_job["title"] if applied_job else None,
        "anchor": "candidates",
    })

    return {
        "message": "Talentpool consent confirmed.",
        "consent_talentpool_until": row["consent_talentpool_until"],
        "applied_job": applied_job,
    }

# ── Een-klik-afmelden voor vacature-alerts (WS3c) ────────────────────────
#
# Eén endpoint voor twee soorten aanroepers, met precies hetzelfde
# antwoord voor allebei:
#
#   (a) een mens die in de voettekst van een job-alert op de afmeldlink
#       klikt (website/unsubscribe.html, token in het URL-fragment) en
#       daar kiest tussen "geen alerts meer" en "helemaal geen contact
#       meer";
#   (b) een mailclient die de List-Unsubscribe-header volgt (RFC 8058
#       one-click): die POST komt rechtstreeks hierheen met ?token=...&
#       scope=alerts in de querystring, zonder tussenpagina.
#
# Waarom het token voor (b) wél in de querystring staat en voor (a) in
# het fragment: RFC 8058 schrijft een POST-bare https-URL voor, en een
# fragment bereikt de server nooit -- een one-click-header met #token=
# zou dus simpelweg niet werken. Voor de menselijke route geldt de
# bestaande regel uit WS-C.17 (security-audit H1) onverkort: fragment,
# geen querystring, zodat het token niet in access logs of een
# Referer-header belandt. Zie de restrisico-notitie hierover in
# docs/VERWERKINGSREGISTER.md §1.2.
#
# TWEE TOKENS PER VERZENDING, en dat is de kern van dit endpoint.
# `job_alert_sends` draagt twee losse hashes:
#
#   - `token_hash`, het token uit het URL-FRAGMENT van de voettekstlink.
#     Dit is de enige weg naar `scope=all` (toestemming intrekken plus
#     blokkeerlijst, onomkeerbaar). Een fragment bereikt geen enkele
#     server- of edge-log, dus dit token staat nergens dan in de mailbox
#     van de ontvanger.
#   - `oneclick_token_hash`, het token uit de querystring van de
#     List-Unsubscribe-URL. Dat token staat per definitie in elke access-,
#     proxy- en edge-logregel die het verzoek passeerde, en levert daarom
#     ALTIJD `alerts` op -- wat de body, de querystring of de opgegeven
#     scope ook zegt.
#
# Waarom dat een tweede kolom nodig had en niet met één token kon: zolang
# beide URL's hetzelfde token droegen, kon wie een one-click-URL uit een
# log haalde datzelfde token in de BODY plakken en langs de
# body-is-toegestaan-regel `scope=all` bereiken. Een regel die kijkt naar
# de PLEK van het token in dit verzoek beschrijft het verzoek, niet het
# token; de tweede hash maakt er een eigenschap van het token zelf van.
# Die plek-regel staat er nog (hieronder, bij `body_token is None`), maar
# als extra laag, niet als het bewijs.
#
# Geen enumeratie-orakel. Het antwoord is altijd hetzelfde bericht met
# dezelfde statuscode: voor een geldig token, een al verbruikt token, een
# verzonnen token en een ontbrekend token. Om ook het *werk* niet te
# laten verschillen (een meetbaar tijdsverschil is net zo goed een
# orakel) voert elke tak exact dezelfde statements uit; bij een onbekend
# token is `candidate_id` simpelweg NULL en raken die statements nul
# rijen. Er wordt dus nooit "eerst gekeken of het token bestaat en dan
# pas iets gedaan".
#
# Het token is eenmalig: de eerste geslaagde aanroep stempelt
# `used_at`, waarna hergebruik langs dezelfde weg als een onbekend token
# loopt (en dus ook niets meer doet). Daarom stuurt
# website/unsubscribe.js niet automatisch bij het laden, maar pas als de
# bezoeker zelf een van de twee knoppen kiest -- anders zou het token op
# de "alerts"-keuze verbruikt zijn voordat hij "alles" had kunnen kiezen.

_UNSUBSCRIBE_MESSAGE = (
    "If this unsubscribe link was valid, your preference has been processed. "
    "You will not receive further job alerts."
)


async def _unsubscribe_body(request: Request) -> dict:
    """Leest de body van een afmeldverzoek zonder ooit te struikelen over
    de vorm ervan.

    Bewust géén gedeclareerd Pydantic-body-model op het endpoint: een RFC
    8058 one-click-POST van een mailclient stuurt
    `Content-Type: application/x-www-form-urlencoded` met de body
    `List-Unsubscribe=One-Click` -- geen JSON. Een JSON-body-model zou
    daar 422 op geven, precies voor de aanroeper die deze header juist
    bedoeld is te bedienen, én zou dat antwoord laten verschillen van het
    generieke antwoord dat elke andere aanroeper krijgt. Een lege body,
    losse tekst of ongeldige JSON leveren hier dus gewoon {} op en het
    verzoek valt terug op de querystring."""
    try:
        raw = await request.body()
    except Exception:
        return {}
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _unsubscribe_field(field: str, value):
    """Valideert één veld van de afmeldbody tegen models.schemas.
    UnsubscribeRequest en levert None als het niet door de beugel kan.

    Per veld en niet als heel model, want de velden zijn onafhankelijk:
    een scope die niet bestaat zegt niets over het token dat ernaast
    staat, en mag dat token niet meeslepen (R1). UnsubscribeRequest
    blijft wel de enige plek die definieert wat geldig is -- dit is een
    andere manier om dat model te bevragen, geen tweede, met de hand
    nagebouwde validatie ernaast."""
    if value is None:
        return None
    try:
        return getattr(UnsubscribeRequest(**{field: value}), field)
    except (TypeError, ValueError):
        return None


@talentpool_public_router.post("/unsubscribe")
# 60/minuut en niet de 10 van de andere publieke endpoints (R4): een
# one-click-POST komt van de mailprovider, niet van de ontvanger, en dus
# vanaf een handvol gedeelde uitgaande IP-adressen -- bij een digest naar
# veel ontvangers lopen die binnen dezelfde minuut op. Een provider
# probeert zo'n POST bovendien niet opnieuw: wie hier een 429 krijgt, is
# simpelweg niet afgemeld terwijl zijn mailclient zegt van wel. De limiet
# blijft bestaan tegen bruteforce op het token, maar dat is hier de
# zwakste van de twee beschermingen: het token is 32 random bytes en
# eenmalig.
@limiter.limit("60/minute")
async def unsubscribe(
    request: Request,
    token: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
):
    """Meld af voor vacature-alerts (`scope='alerts'`) of voor elk contact
    (`scope='all'`). Zie het blok hierboven voor de twee aanroepers en
    voor waarom het antwoord altijd identiek is.

    Body (optioneel, JSON): `{"token": "...", "scope": "alerts"|"all"}` --
    zie models.schemas.UnsubscribeRequest voor de vorm. Beide velden
    mogen ook als queryparameter (`?token=...&scope=...`), voor de
    one-click-header.

    Eén asymmetrie tussen die twee wegen, met opzet: `scope='all'` is
    alleen bereikbaar met het token uit het URL-FRAGMENT van de
    voettekstlink, in de body. Het token uit de List-Unsubscribe-URL
    levert altijd `alerts`, ongeacht body, querystring of opgegeven
    scope -- zie het blok hierboven voor waarom dat aan het token hangt en
    niet aan de plek in het verzoek."""
    raw_body = await _unsubscribe_body(request)
    # UnsubscribeRequest is het gedocumenteerde bodycontract, maar het
    # wordt hier PER VELD toegepast en niet als één model (R1). Als één
    # model viel een body als {"token": "...", "scope": "bogus"} in zijn
    # geheel om: de ValueError van de scope-validator wierp ook het
    # geldige token weg, waarna het verzoek stilletjes een no-op werd --
    # dezelfde 200, hetzelfde bericht, maar niemand afgemeld. Een body
    # die niet aan het contract voldoet mag hier nooit een 422 worden
    # (dat zou het enige antwoord zijn dat wél iets verklapt), en een
    # onbruikbare scope mag nooit een bruikbaar token meeslepen.
    body_token = _unsubscribe_field("token", raw_body.get("token"))
    body_scope = _unsubscribe_field("scope", raw_body.get("scope"))

    raw_token = body_token or token

    # Querystring wint alleen als de body niets zei; een onbekende of
    # ontbrekende scope valt terug op de smalste betekenis ('alerts'),
    # nooit op de ingrijpendste. Een afmelding moet nooit méér intrekken
    # dan de betrokkene bedoelde.
    raw_scope = body_scope or scope or "alerts"
    if raw_scope not in UNSUBSCRIBE_SCOPES:
        raw_scope = "alerts"

    # Extra laag bovenop de tokenbinding hieronder, niet het bewijs zelf:
    # komt het token uit de QUERYSTRING, dan staat het in elke access-,
    # proxy- en edge-logregel die het verzoek passeerde, en `scope='all'`
    # is onomkeerbaar (toestemming ingetrokken, adres op de
    # suppressielijst, geen API om zo'n rij weer weg te halen). Deze regel
    # beschrijft het verzoek; de tweede hash hieronder beschrijft het
    # token, en die twee vangen elkaars gaten op.
    if body_token is None and token is not None:
        raw_scope = "alerts"

    token_hash = hash_token(raw_token) if raw_token else None

    # Twee lookups, en ALLEBEI draaien ze altijd -- ook als de eerste al
    # raak was. Het antwoord van dit endpoint is met opzet voor elk token
    # identiek, en een meetbaar tijdsverschil is net zo goed een orakel
    # als een ander antwoord: "eerst kijken of het bestaat en dan pas iets
    # doen" is precies wat hier niet gebeurt. Bij een onbekend token raken
    # beide statements nul rijen en blijft candidate_id NULL.
    #
    # `used_at IS NULL` maakt hergebruik onmogelijk zonder een aparte
    # check die zelf weer een tak zou zijn. Elke parameter krijgt een
    # expliciete cast: asyncpg leidt het type van een placeholder af uit
    # de kolom waarmee hij wordt vergeleken, en juist in dit endpoint
    # staan er placeholders op plekken zonder kolom om van te leren
    # (SELECT $1 ... WHERE $1 IS NOT NULL) -- zonder cast is dat een
    # AmbiguousParameterError, en dat zou een 500 zijn: het enige antwoord
    # dat van het generieke antwoord afwijkt.
    #
    # `sent_at > NOW() - INTERVAL '90 days'` voor allebei: een afmeldtoken
    # hoort bij één verzonden bericht. Zonder houdbaarheid werkt een token
    # uit een mail van twee jaar geleden (of uit een access log van toen)
    # vandaag nog. 90 dagen is ruim voor het doel -- een mens die deze
    # mail terugzoekt -- en gelijk aan de bewaartermijn van email_log
    # (migrations/040) en van job_alert_sends zelf
    # (services/scheduler.py job_alert_sends_cleanup_job). Verlopen loopt
    # langs precies dezelfde weg als een onbekend token.
    #
    # Eerst het one-click-token (B1). Een treffer hier betekent: dit token
    # kwam uit de List-Unsubscribe-URL, stond dus in onze logs, en kan
    # daarom nooit meer dan `alerts` -- wat de body, de querystring of de
    # opgegeven scope ook zegt.
    consumed_oneclick = await fetch_one(
        """UPDATE job_alert_sends SET used_at = NOW()
           WHERE oneclick_token_hash = $1::text AND used_at IS NULL
             AND sent_at > NOW() - INTERVAL '90 days'
           RETURNING candidate_id""",
        token_hash,
    )
    # Daarna het fragmenttoken, de gewone weg. Dit is het enige token
    # waarmee `scope='all'` bereikbaar is.
    consumed_fragment = await fetch_one(
        """UPDATE job_alert_sends SET used_at = NOW()
           WHERE token_hash = $1::text AND used_at IS NULL
             AND sent_at > NOW() - INTERVAL '90 days'
           RETURNING candidate_id""",
        token_hash,
    )

    if consumed_oneclick is not None:
        candidate_id = consumed_oneclick["candidate_id"]
        raw_scope = "alerts"
    elif consumed_fragment is not None:
        candidate_id = consumed_fragment["candidate_id"]
    else:
        candidate_id = None

    # Vanaf hier draait elk statement altijd, met candidate_id = NULL bij
    # een onbekend/verbruikt/ontbrekend token: `WHERE id = NULL` matcht
    # niets, zonder aparte if-tak.
    candidate = await fetch_one(
        "SELECT id, email FROM candidates WHERE id = $1::int", candidate_id,
    )
    email = candidate["email"] if candidate else None

    # B6: op id ÉN op adres, net als de drie statements hieronder. Dit
    # stond alleen op `id = $1` terwijl `uq_candidates_email` hoofdletter-
    # gevoelig is en POST /api/candidates het adres niet normaliseert:
    # `A@example.com` en `a@example.com` kunnen naast elkaar bestaan, en
    # de alertselector (core/retention.py JOB_ALERT_ELIGIBILITY_SQL) pikt
    # ze allebei op. Wie zich op de ene rij afmeldde, kreeg morgen zijn
    # digest van de andere -- dezelfde persoon, hetzelfde adres, een
    # afmelding die niets leek te doen. Dat is precies het gat dat voor
    # `scope='all'` al was gedicht.
    await execute(
        """UPDATE candidates
           SET job_alert_unsubscribed_at = COALESCE(job_alert_unsubscribed_at, NOW()),
               updated_at = NOW()
           WHERE id = $1::int
              OR ($2::text IS NOT NULL AND LOWER(email) = LOWER($2::text))""",
        candidate_id, email,
    )

    withdraw_all = raw_scope == "all"

    # scope='all' is een intrekking in de zin van SOP §3.3: geen contact
    # meer, op geen enkele grondslag. Dat is precies wat
    # routers/gdpr.py's add_suppression() met de hand doet -- zelfde drie
    # effecten (consent_withdrawn_at, suppressielijst, lopende drafts
    # ingetrokken), hier zonder beheerder omdat de betrokkene het zelf
    # vraagt. `created_by` blijft NULL: er is geen actor, de persoon zelf
    # deed dit.
    #
    # Op id ÉN op adres, net als add_suppression(): dit is dezelfde
    # intrekking, alleen door de betrokkene zelf in plaats van door een
    # beheerder, dus het effect hoort hetzelfde te zijn. Eén adres kan
    # meer dan één candidates-rij hebben (een gesourcete rij en een
    # portaalrij die WS-C.16's FK nooit heeft samengevoegd), en het adres
    # komt straks op de suppressielijst te staan: dan moet elke rij met
    # dat adres de intrekking dragen, anders blijft er een rij achter die
    # voor elke selector nog "toestemming intact" zegt.
    await execute(
        """UPDATE candidates
           SET consent_withdrawn_at = CASE WHEN $2::boolean THEN COALESCE(consent_withdrawn_at, NOW())
                                           ELSE consent_withdrawn_at END,
               updated_at = NOW()
           WHERE id = $1::int
              OR ($2::boolean AND $3::text IS NOT NULL AND LOWER(email) = LOWER($3::text))""",
        candidate_id, withdraw_all, email,
    )
    await execute(
        """INSERT INTO suppression_list (email_hash, email_domain, reason, created_by)
           SELECT $1::text, $2::text, 'unsubscribe_all', NULL
           WHERE $1::text IS NOT NULL AND $3::boolean
           ON CONFLICT (email_hash) DO NOTHING""",
        privacy.email_hash(email) if email else None,
        privacy.email_domain(email) if email else None,
        withdraw_all,
    )
    # Zelfde twee criteria, andere tabel. add_suppression() trekt drafts
    # in op `LOWER(target_email)`; alleen op `target_id` vindt dat niet
    # dezelfde rijen. Een outreach-draft die voor deze persoon is
    # geschreven maar aan een andere candidates-rij met hetzelfde adres
    # hangt (of waarvan target_id nooit is gezet) blijft dan op 'draft'
    # staan en kan morgen alsnog door een mens worden verstuurd, aan
    # iemand die zojuist "geen contact meer" koos.
    await execute(
        """UPDATE outreach_drafts SET status = 'rejected', updated_at = NOW()
           WHERE target_type = 'candidate' AND status = 'draft' AND $2::boolean
             AND (target_id = $1::int
                  OR ($3::text IS NOT NULL AND LOWER(target_email) = LOWER($3::text)))""",
        candidate_id, withdraw_all, email,
    )

    # Audit-regel, alleen als er echt iets is gebeurd (een onbekend token
    # is geen gebeurtenis om vast te leggen, en zou de audit-log vullen
    # met ruis die een aanvaller zelf kan produceren). Nooit het adres:
    # alleen de sha256-hash, net als elders. json.dumps, nooit een ruwe
    # dict (commit 72b4bcd).
    await execute(
        """INSERT INTO audit_log (action, actor_id, target_type, target_id, changes)
           SELECT 'job_alert_unsubscribe', NULL::int, 'candidate', $1::int, $2::jsonb
           WHERE $1::int IS NOT NULL""",
        candidate_id,
        json.dumps({
            "scope": raw_scope,
            "email_hash": privacy.email_hash(email) if email else None,
            # Welk van de twee tokens is gebruikt. Zonder dat onderscheid
            # zegt deze regel niet waar de afmelding vandaan kwam, en is
            # bij een vermoed gelekt token achteraf niet na te gaan of
            # het een one-click-URL uit een log betrof.
            "via": "one_click_token" if consumed_oneclick is not None else "footer_token",
        }),
    )

    if candidate_id is not None:
        # Alleen een id, nooit het adres (core.privacy.email_hash is de
        # regel voor als er toch iets identificeerbaars in een logregel
        # moet -- hier is het id al genoeg).
        logger.info("unsubscribe: processed scope=%s for candidate id=%s", raw_scope, candidate_id)

    return {"message": _UNSUBSCRIBE_MESSAGE}
