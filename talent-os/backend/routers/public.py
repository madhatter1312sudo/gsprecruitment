"""
Talent OS — Public API Router.
Unauthenticated endpoints for site content, salary benchmarks, and lead submission.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from core.database import fetch_all, fetch_one, execute
from core.config import settings
from core.deps import get_optional_user
from models.schemas import SiteContentResponse, LeadSubmit, SalaryBenchmarkResponse, QuizSubmitRequest
from typing import Optional, List
import json
import random

router = APIRouter(prefix="/api/v1/public", tags=["public"])

from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)


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
        """INSERT INTO quiz_submissions (email, user_id, answers, score, max_score, tier, domain_scores)
           VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7::jsonb)""",
        email, user_id,
        json.dumps([a.model_dump() for a in data.answers]),
        score, max_score, tier,
        json.dumps(domain_scores),
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
           (name, email, company, phone, message, interest_type)
           VALUES ($1, $2, $3, $4, $5, $6)
           RETURNING id, created_at""",
        data.name, data.email.lower().strip(), data.company,
        data.phone, data.message, data.interest_type,
    )
    if not lead:
        raise HTTPException(status_code=500, detail="Failed to submit lead")

    return {
        "message": "Thank you! We'll get back to you shortly.",
        "id": lead["id"],
        "created_at": lead["created_at"],
    }