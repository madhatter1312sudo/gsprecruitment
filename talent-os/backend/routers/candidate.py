"""
Talent OS — Candidate Portal Router (JWT-protected).
Endpoints for candidate-facing features: profile, CV, matches, applications,
saved jobs, messages, salary benchmarks, dashboard.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from core.database import fetch_one, fetch_all, execute, fetch_val
from core.deps import get_verified_user, require_role
from models.schemas import (
    CandidatePortalProfile, CandidateProfileUpdate, CandidateMatchItem,
    ApplicationCreate, SavedJobCreate, CandidateDashboard,
    SalaryBenchmarkResponse, MessageListResponse, MessageResponse,
)
from typing import Optional, List
import asyncio
import os
import uuid
import logging

from services import storage
from services.candidate_link import get_or_create_candidate_id

logger = logging.getLogger("talent_os.candidate_portal")

router = APIRouter(prefix="/api/v1/candidate", tags=["candidate-portal"])

# CV files live in R2 (services/storage); this directory is only the legacy
# local-disk fallback for pre-R2 uploads. Creating it must never break import:
# the CI runner cannot write to /app and R2-only deployments never use it.
UPLOAD_DIR = "/app/uploads/cv"
try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
except OSError as exc:
    logger.warning("CV upload dir %s not writable (%s); legacy local CV storage unavailable", UPLOAD_DIR, exc)

MAX_CV_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


async def _get_candidate_id(user_id: int) -> Optional[int]:
    """Resolve the candidate record id linked to this user (WS-C.16:
    services/candidate_link.py does the actual FK-first / e-mail-fallback
    / create-and-link work — this is a thin alias kept so every existing
    call site in this router doesn't need touching)."""
    return await get_or_create_candidate_id(user_id)


# ── Profile ─────────────────────────────────────────────────────────────

@router.get("/profile", response_model=CandidatePortalProfile)
async def get_candidate_profile(current_user: dict = Depends(get_verified_user)):
    """Get full candidate profile (user + candidate_profiles)."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can access their profile")

    profile = await fetch_one(
        """SELECT cp.*, u.email, u.full_name
           FROM candidate_profiles cp
           JOIN users u ON u.id = cp.user_id
           WHERE cp.user_id = $1""",
        current_user["id"],
    )
    if not profile:
        # Auto-create profile if missing
        await execute(
            "INSERT INTO candidate_profiles (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
            current_user["id"],
        )
        profile = await fetch_one(
            """SELECT cp.*, u.email, u.full_name
               FROM candidate_profiles cp
               JOIN users u ON u.id = cp.user_id
               WHERE cp.user_id = $1""",
            current_user["id"],
        )

    return profile


@router.put("/profile", response_model=CandidatePortalProfile)
async def update_candidate_profile(
    updates: CandidateProfileUpdate,
    current_user: dict = Depends(get_verified_user),
):
    """Update candidate profile fields."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can update their profile")

    # Build dynamic SET clause
    set_parts = []
    values = []
    idx = 1
    allowed = {
        "phone", "linkedin_url", "github_url", "portfolio_url",
        "current_company", "current_title", "location",
        "willing_to_relocate", "salary_expectation_min", "salary_expectation_max",
        "notice_period_days", "years_experience", "skills", "languages",
        "education", "cv_text",
    }

    update_dict = updates.model_dump(exclude_none=True)
    for key, val in update_dict.items():
        if key not in allowed:
            continue
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_parts:
        # Just return current profile
        return await get_candidate_profile(current_user)

    values.append(current_user["id"])
    await execute(
        f"UPDATE candidate_profiles SET {', '.join(set_parts)}, updated_at = NOW() WHERE user_id = ${idx}",
        *values,
    )

    # Keep the sourcing-side candidates row in sync (same allowed columns exist there)
    candidate_id = await _get_candidate_id(current_user["id"])
    if candidate_id:
        set_parts_c = []
        values_c = []
        idx_c = 1
        for key, val in update_dict.items():
            if key not in allowed:
                continue
            set_parts_c.append(f"{key} = ${idx_c}")
            values_c.append(val)
            idx_c += 1
        if set_parts_c:
            values_c.append(candidate_id)
            await execute(
                f"UPDATE candidates SET {', '.join(set_parts_c)}, updated_at = NOW() WHERE id = ${idx_c}",
                *values_c,
            )

    return await get_candidate_profile(current_user)


# ── CV Upload ───────────────────────────────────────────────────────────

@router.post("/cv")
async def upload_cv(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_verified_user),
):
    """Upload a CV file and update the candidate profile."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can upload CVs")

    # Validate file type
    allowed_types = {".pdf", ".doc", ".docx", ".txt"}
    ext = os.path.splitext(file.filename or "cv.pdf")[1].lower()
    if ext not in allowed_types:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not allowed. Use: {', '.join(allowed_types)}")

    # Read with a hard size cap (bounded memory use, rejects oversized uploads)
    content = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        content.extend(chunk)
        if len(content) > MAX_CV_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="CV file too large (max 5 MB)")
    content = bytes(content)

    content_types = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
    }

    # Look up the CV this upload is about to replace, so we can clean up the
    # old R2 object after the new one is stored -- otherwise every re-upload
    # orphans the previous object in the bucket forever.
    existing = await fetch_one(
        "SELECT cv_file_path FROM candidate_profiles WHERE user_id = $1",
        current_user["id"],
    )
    old_cv_file_path = existing["cv_file_path"] if existing else None

    if storage.is_configured():
        key = storage.cv_key(current_user["id"], ext, uuid.uuid4().hex)
        await storage.put_object(key, content, content_types.get(ext, "application/octet-stream"))
        stored_path = key
    else:
        # Legacy local-disk fallback -- production must keep working before
        # the R2 env vars are set.
        filename = f"{uuid.uuid4().hex}{ext}"
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        file_path = os.path.join(UPLOAD_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(content)
        stored_path = f"/uploads/cv/{filename}"

    # Point candidate_profiles at the new file BEFORE touching the old
    # object -- doing the delete first would leave a window where the row
    # still references a key that's already gone if anything went wrong
    # in between.
    await execute(
        "UPDATE candidate_profiles SET cv_file_path = $1, updated_at = NOW() WHERE user_id = $2",
        stored_path, current_user["id"],
    )

    if storage.is_configured() and storage.should_delete_old_key(old_cv_file_path, stored_path):
        try:
            await storage.delete_object(old_cv_file_path)
        except Exception:
            # Best-effort: never fail the upload because the old object
            # couldn't be cleaned up (e.g. transient R2 issue) -- it's
            # still swept up later by GDPR erasure's prefix delete.
            logger.exception(
                "Failed to delete superseded CV object %s for user %s",
                old_cv_file_path, current_user["id"],
            )

    return {"message": "CV uploaded successfully", "file_path": stored_path, "size": len(content)}


@router.get("/cv")
async def download_own_cv(current_user: dict = Depends(get_verified_user)):
    """Download the candidate's own uploaded CV (auth-gated; CVs are never served publicly)."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can download their CV")

    profile = await fetch_one(
        "SELECT cv_file_path FROM candidate_profiles WHERE user_id = $1",
        current_user["id"],
    )
    if not profile or not profile["cv_file_path"]:
        raise HTTPException(status_code=404, detail="No CV uploaded")

    cv_file_path = profile["cv_file_path"]

    if storage.is_configured() and storage.is_r2_key(cv_file_path):
        ext = os.path.splitext(cv_file_path)[1]
        url = await storage.presigned_get(cv_file_path, ttl=300, filename=f"cv{ext}")
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url, status_code=302)

    # Legacy local-disk path (pre-R2 upload).
    filename = os.path.basename(cv_file_path)
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="CV file missing on server")

    from fastapi.responses import FileResponse
    return FileResponse(file_path, filename=f"cv{os.path.splitext(filename)[1]}")


# ── Matches ─────────────────────────────────────────────────────────────

@router.get("/matches")
async def get_candidate_matches(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_verified_user),
):
    """Get match list for the candidate with pagination."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can view their matches")

    # First get the candidate record linked to this user
    candidate_id = await _get_candidate_id(current_user["id"])
    if not candidate_id:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    total = await fetch_val(
        "SELECT COUNT(*) FROM matches WHERE candidate_id = $1",
        candidate_id,
    )
    rows = await fetch_all(
        """SELECT m.*, j.title AS job_title, c.company_name
           FROM matches m
           JOIN job_orders j ON j.id = m.job_id
           JOIN clients c ON c.id = j.client_id
           WHERE m.candidate_id = $1
           ORDER BY m.match_score DESC NULLS LAST
           LIMIT $2 OFFSET $3""",
        candidate_id, limit, offset,
    )

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


# ── Applications ────────────────────────────────────────────────────────

@router.get("/applications")
async def get_applications(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_verified_user),
):
    """Get application (match) history for the candidate."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can view their applications")

    candidate_id = await _get_candidate_id(current_user["id"])
    if not candidate_id:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    total = await fetch_val(
        "SELECT COUNT(*) FROM matches WHERE candidate_id = $1 AND status IN ('applied', 'interviewing', 'offered', 'placed', 'rejected')",
        candidate_id,
    )
    rows = await fetch_all(
        """SELECT m.*, j.title AS job_title, c.company_name
           FROM matches m
           JOIN job_orders j ON j.id = m.job_id
           JOIN clients c ON c.id = j.client_id
           WHERE m.candidate_id = $1 AND m.status IN ('applied', 'interviewing', 'offered', 'placed', 'rejected')
           ORDER BY m.created_at DESC
           LIMIT $2 OFFSET $3""",
        candidate_id, limit, offset,
    )

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.post("/applications", status_code=201)
async def apply_to_job(
    data: ApplicationCreate,
    current_user: dict = Depends(get_verified_user),
):
    """Apply to a job (creates a match record with status='applied')."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can apply to jobs")

    candidate_id = await _get_candidate_id(current_user["id"])
    if not candidate_id:
        raise HTTPException(status_code=400, detail="No candidate profile found. Contact support.")

    # Check the job exists and is open
    job = await fetch_one(
        "SELECT id, status FROM job_orders WHERE id = $1 AND deleted_at IS NULL",
        data.job_id,
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "open":
        raise HTTPException(status_code=400, detail="This job is no longer accepting applications")

    # Check if already applied
    existing = await fetch_one(
        "SELECT id FROM matches WHERE candidate_id = $1 AND job_id = $2",
        candidate_id, data.job_id,
    )
    if existing:
        raise HTTPException(status_code=409, detail="You have already applied to this job")

    match = await fetch_one(
        """INSERT INTO matches (candidate_id, job_id, status)
           VALUES ($1, $2, 'applied')
           RETURNING *""",
        candidate_id, data.job_id,
    )
    return match


# ── Saved Jobs ──────────────────────────────────────────────────────────

@router.get("/saved-jobs")
async def get_saved_jobs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_verified_user),
):
    """Get saved/favorited jobs for the candidate."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can view saved jobs")

    candidate_id = await _get_candidate_id(current_user["id"])
    if not candidate_id:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    total = await fetch_val(
        "SELECT COUNT(*) FROM saved_jobs WHERE candidate_id = $1",
        candidate_id,
    )
    rows = await fetch_all(
        """SELECT sj.*, j.title AS job_title, j.description, j.salary_min, j.salary_max,
                  j.salary_currency, j.location_type, c.company_name
           FROM saved_jobs sj
           JOIN job_orders j ON j.id = sj.job_id
           JOIN clients c ON c.id = j.client_id
           WHERE sj.candidate_id = $1
           ORDER BY sj.created_at DESC
           LIMIT $2 OFFSET $3""",
        candidate_id, limit, offset,
    )

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.post("/saved-jobs", status_code=201)
async def save_job(
    data: SavedJobCreate,
    current_user: dict = Depends(get_verified_user),
):
    """Save a job to the candidate's favorites."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can save jobs")

    candidate_id = await _get_candidate_id(current_user["id"])
    if not candidate_id:
        raise HTTPException(status_code=400, detail="No candidate profile found")

    # Verify job exists
    job = await fetch_one(
        "SELECT id FROM job_orders WHERE id = $1 AND deleted_at IS NULL",
        data.job_id,
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check if already saved
    existing = await fetch_one(
        "SELECT id FROM saved_jobs WHERE candidate_id = $1 AND job_id = $2",
        candidate_id, data.job_id,
    )
    if existing:
        return {"message": "Job already saved", "id": existing["id"]}

    saved = await fetch_one(
        "INSERT INTO saved_jobs (candidate_id, job_id) VALUES ($1, $2) RETURNING *",
        candidate_id, data.job_id,
    )
    return saved


@router.delete("/saved-jobs/{job_id}")
async def unsave_job(
    job_id: int,
    current_user: dict = Depends(get_verified_user),
):
    """Remove a job from saved favorites."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can unsave jobs")

    candidate_id = await _get_candidate_id(current_user["id"])
    if not candidate_id:
        raise HTTPException(status_code=400, detail="No candidate profile found")

    deleted = await execute(
        "DELETE FROM saved_jobs WHERE candidate_id = $1 AND job_id = $2",
        candidate_id, job_id,
    )
    if deleted == "DELETE 0":
        raise HTTPException(status_code=404, detail="Saved job not found")

    return {"message": "Job removed from saved"}


# ── Messages ────────────────────────────────────────────────────────────

@router.get("/messages", response_model=MessageListResponse)
async def get_candidate_messages(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_verified_user),
):
    """Get messages from GSP (sent to the candidate)."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can view their messages")

    candidate_id = await _get_candidate_id(current_user["id"])
    if not candidate_id:
        return MessageListResponse(messages=[], unread_count=0)

    unread, rows = await asyncio.gather(
        fetch_val(
            "SELECT COUNT(*) FROM outreach_messages WHERE candidate_id = $1 AND (opened_at IS NULL AND status != 'draft')",
            candidate_id,
        ),
        fetch_all(
            """SELECT om.*, c.full_name AS sender_name
               FROM outreach_messages om
               LEFT JOIN candidates c ON c.id = om.candidate_id
               WHERE om.candidate_id = $1
               ORDER BY om.created_at DESC
               LIMIT $2 OFFSET $3""",
            candidate_id, limit, offset,
        ),
    )

    # is_read is derived, not a DB column -- outreach_messages has no
    # is_read field, only opened_at (see models.schemas.MessageResponse).
    messages = [
        MessageResponse(**{**dict(r), "is_read": r["opened_at"] is not None})
        for r in rows
    ]
    return MessageListResponse(messages=messages, unread_count=unread or 0)


# ── Salary Benchmark ────────────────────────────────────────────────────

@router.get("/salary-benchmark", response_model=List[SalaryBenchmarkResponse])
async def get_salary_benchmark(
    role_title: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    seniority: Optional[str] = Query(None),
    current_user: dict = Depends(get_verified_user),
):
    """Get salary benchmark data for the candidate."""
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

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    rows = await fetch_all(
        f"SELECT * FROM salary_benchmarks {where} ORDER BY role_title LIMIT 50",
        *params,
    )
    return rows


# ── Dashboard ───────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=CandidateDashboard)
async def get_candidate_dashboard(current_user: dict = Depends(get_verified_user)):
    """Get dashboard stats: match count, profile views, unread messages, saved jobs."""
    if current_user["role"] != "candidate":
        raise HTTPException(status_code=403, detail="Only candidates can view their dashboard")

    candidate_id = await _get_candidate_id(current_user["id"])

    stats = CandidateDashboard()

    if candidate_id:
        match_count, saved_jobs_count, applications_count, unread_messages = await asyncio.gather(
            fetch_val(
                "SELECT COUNT(*) FROM matches WHERE candidate_id = $1 AND match_score >= 50", candidate_id,
            ),
            fetch_val(
                "SELECT COUNT(*) FROM saved_jobs WHERE candidate_id = $1", candidate_id,
            ),
            fetch_val(
                "SELECT COUNT(*) FROM matches WHERE candidate_id = $1 AND status IN ('applied', 'interviewing', 'offered', 'placed')", candidate_id,
            ),
            fetch_val(
                """SELECT COUNT(*) FROM outreach_messages
                   WHERE candidate_id = $1 AND (opened_at IS NULL AND status != 'draft')""", candidate_id,
            ),
        )
        stats.match_count = match_count or 0
        stats.saved_jobs_count = saved_jobs_count or 0
        stats.applications_count = applications_count or 0
        stats.unread_messages = unread_messages or 0

    # Profile views - from an audit-like log or placeholder
    stats.profile_views = 0

    return stats