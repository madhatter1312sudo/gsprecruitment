"""
Talent OS — Client Portal Router (JWT-protected, role='client').
Endpoints for client-facing features: dashboard, jobs, candidate search,
pipeline, analytics, messages, team management.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from core.database import fetch_one, fetch_all, execute, fetch_val
from core.deps import require_verified_role
from core.security import hash_password, hash_token
from models.schemas import (
    ClientDashboard, ClientJobCreate, ClientJobUpdate, JobOrderResponse,
    CandidateSearchParams, PipelineAdd, ClientAnalytics, TeamInvite,
    MessageListResponse, MessageResponse, PipelineStageUpdate,
)
from services.email_service import email_service
from typing import Optional, List
from pydantic import BaseModel
import asyncio
import json
import logging
import secrets

logger = logging.getLogger("talent_os.client_portal")


class ClientProfileUpdate(BaseModel):
    company_name: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    location: Optional[str] = None
    size_range: Optional[str] = None

router = APIRouter(prefix="/api/v1/client", tags=["client-portal"])


# ── Helper ──────────────────────────────────────────────────────────────

async def _get_client_id(user_id: int) -> int:
    """Get the client record id associated with the user."""
    client = await fetch_one(
        "SELECT id FROM clients WHERE id = (SELECT client_id FROM user_clients WHERE user_id = $1)",
        user_id,
    )
    if not client:
        # Try to find or create a client record
        user = await fetch_one("SELECT id, email, full_name FROM users WHERE id = $1", user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        client = await fetch_one(
            "INSERT INTO clients (company_name, domain) VALUES ($1, $2) RETURNING id",
            user["full_name"], user["email"].split("@")[1] if "@" in user["email"] else "",
        )
        await execute(
            "INSERT INTO user_clients (user_id, client_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            user_id, client["id"],
        )
    return client["id"]


async def _get_client_by_user(user_id: int) -> Optional[dict]:
    """Get the client record for a given user."""
    return await fetch_one(
        """SELECT c.* FROM clients c
           JOIN user_clients uc ON uc.client_id = c.id
           WHERE uc.user_id = $1""",
        user_id,
    )


async def _record_stage_change(
    pipeline_entry_id: int, from_stage: Optional[str], to_stage: str, changed_by: Optional[int],
) -> None:
    """WS-C.5: append-only log of every pipeline_entries.stage transition
    (migrations/025_pipeline_stage_history.py). Shared by both the client
    portal's and the admin panel's stage-update endpoints (routers/admin.py
    imports this rather than duplicating the INSERT)."""
    await execute(
        "INSERT INTO pipeline_stage_history (pipeline_entry_id, from_stage, to_stage, changed_by) "
        "VALUES ($1, $2, $3, $4)",
        pipeline_entry_id, from_stage, to_stage, changed_by,
    )


# Candidate data dump fix (WS-C.2): candidates carry personal data (email,
# phone, social/portfolio URLs, raw CV text) that clients must never receive
# in bulk. `_require_candidate_access` is the single gate for the client
# portal's candidate endpoints — relax it in exactly this one place.
#
# WS-E.2: the blanket "admin-only" block is replaced with an explicit
# per-client approval gate on `users.approved_by_admin_at` (set by
# POST /api/v1/admin/clients/{user_id}/approve). A client user is not
# enough on its own -- role='client' alone no longer grants candidate
# access, an admin must additionally have approved that specific account.
# This runs on top of require_verified_role("client", "admin"), so
# current_user here is always e-mail-verified already; this only adds the
# admin-approval check. (The router's TODO originally imagined a
# per-*candidate* approval column instead of a per-*client* one -- the
# per-client gate is what was actually specified and built for WS-E.2;
# a finer per-candidate grant can still be layered on top later without
# touching this function's signature.)
def _require_candidate_access(current_user: dict) -> None:
    if current_user["role"] == "admin":
        return
    if current_user["role"] != "client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Candidate search/detail is available to client and admin accounts only.",
        )
    if not current_user.get("approved_by_admin_at"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Your company account is pending admin approval. Candidate "
                "search/detail unlocks once GSP Recruitment approves your "
                "account -- contact info@gsprecruitment.nl if this is "
                "taking longer than expected."
            ),
        )


# Anonymised projection for the client-facing candidate endpoints: no email,
# phone, linkedin/github/portfolio URLs, cv_text, or any other direct
# identifier/contact channel. Field names match the `candidates` table.
def _project_candidate_public(row: dict) -> dict:
    """Defense in depth: even if a query selects extra columns, strip down
    to the anonymised field set before it ever reaches a response body."""
    projected = {k: row.get(k) for k in (
        "id", "full_name", "current_title", "current_company",
        "location", "years_experience",
    )}
    # NULL array columns must be coerced to [] on read (commit 6ded1db).
    projected["skills"] = row.get("skills") or []
    return projected


# ── Dashboard ───────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=ClientDashboard)
async def get_client_dashboard(current_user: dict = Depends(require_verified_role("client", "admin"))):
    """Get client dashboard stats."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        return ClientDashboard()

    cid = client["id"]
    stats = ClientDashboard()
    active_jobs, total_matched, in_pipeline, placements = await asyncio.gather(
        fetch_val(
            "SELECT COUNT(*) FROM job_orders WHERE client_id = $1 AND status = 'open' AND deleted_at IS NULL", cid,
        ),
        fetch_val(
            """SELECT COUNT(*) FROM matches m
               JOIN job_orders j ON j.id = m.job_id
               WHERE j.client_id = $1""", cid,
        ),
        fetch_val(
            """SELECT COUNT(*) FROM pipeline_entries pe
               JOIN job_orders j ON j.id = pe.job_id
               WHERE j.client_id = $1""", cid,
        ),
        fetch_val(
            """SELECT COUNT(*) FROM matches m
               JOIN job_orders j ON j.id = m.job_id
               WHERE j.client_id = $1 AND m.status = 'placed'""", cid,
        ),
    )
    stats.active_jobs = active_jobs or 0
    stats.total_candidates_matched = total_matched or 0
    stats.candidates_in_pipeline = in_pipeline or 0
    stats.placements = placements or 0
    stats.unread_messages = 0  # Placeholder
    return stats


# ── Jobs ────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def list_client_jobs(
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """List jobs for this client with optional filters."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    cid = client["id"]
    conditions = ["client_id = $1"]
    params = [cid]
    idx = 2

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if date_from:
        conditions.append(f"created_at >= ${idx}::timestamp")
        params.append(date_from)
        idx += 1
    if date_to:
        conditions.append(f"created_at <= ${idx}::timestamp")
        params.append(date_to)
        idx += 1

    conditions.append("deleted_at IS NULL")
    where = " AND ".join(conditions)

    total = await fetch_val(f"SELECT COUNT(*) FROM job_orders WHERE {where}", *params) or 0
    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"SELECT * FROM job_orders WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
        *params_ext,
    )

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.post("/jobs", status_code=201)
async def create_client_job(
    data: ClientJobCreate,
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """Create a job posting for this client."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        raise HTTPException(status_code=400, detail="Client profile not found. Contact support.")

    # Unauthorized-publish fix (WS-C.2 follow-up): status is not settable
    # from ClientJobCreate at all, and is hardcoded to 'draft' here rather
    # than left to whatever the job_orders column default happens to be
    # (which is not defined in this repo and may be 'open') -- otherwise a
    # client could publish client-authored HTML straight to the public job
    # board via POST without ever touching the status allow-list in
    # update_client_job.
    job = await fetch_one(
        """INSERT INTO job_orders
           (client_id, title, department, seniority, location_type,
            salary_min, salary_max, salary_currency, description, requirements, nice_to_have, urgency, status)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'draft')
           RETURNING *""",
        client["id"], data.title, data.department, data.seniority,
        data.location_type, data.salary_min, data.salary_max,
        data.salary_currency, data.description, data.requirements,
        data.nice_to_have, data.urgency,
    )

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        "client_job_create", current_user["id"], "job", job["id"],
        json.dumps({"client_id": client["id"], "title": data.title}),
    )
    return job


@router.get("/jobs/{job_id}")
async def get_client_job(
    job_id: int,
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """Get job detail for a client-owned job."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    job = await fetch_one(
        "SELECT * FROM job_orders WHERE id = $1 AND client_id = $2 AND deleted_at IS NULL",
        job_id, client["id"],
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.put("/jobs/{job_id}")
async def update_client_job(
    job_id: int,
    updates: ClientJobUpdate,
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """Update a job posting."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Verify ownership
    existing = await fetch_one(
        "SELECT id FROM job_orders WHERE id = $1 AND client_id = $2 AND deleted_at IS NULL",
        job_id, client["id"],
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found or not owned by you")

    set_parts = []
    values = []
    idx = 1
    allowed = {
        "title", "department", "seniority", "location_type",
        "salary_min", "salary_max", "salary_currency",
        "description", "requirements", "nice_to_have", "status", "urgency",
    }
    # Stored-XSS / unauthorized-publish fix (WS-C.2): a client may move their
    # own job between draft/paused/closed, but publishing to the public job
    # board ('open') is admin-only — client-authored HTML must pass through
    # admin review before it is rendered on the public site. Admin routes
    # (routers/admin.py) are untouched and keep full status control.
    CLIENT_ALLOWED_STATUSES = {"draft", "paused", "closed"}

    update_dict = updates.model_dump(exclude_none=True)
    if (
        "status" in update_dict
        and current_user["role"] != "admin"
        and update_dict["status"] not in CLIENT_ALLOWED_STATUSES
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Clients may only set status to one of "
                f"{sorted(CLIENT_ALLOWED_STATUSES)}. Publishing ('open') "
                "requires admin review."
            ),
        )
    for key, val in update_dict.items():
        if key not in allowed:
            continue
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_parts:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    values.append(job_id)
    row = await fetch_one(
        f"UPDATE job_orders SET {', '.join(set_parts)} WHERE id = ${idx} RETURNING *",
        *values,
    )

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        "client_job_update", current_user["id"], "job", job_id,
        json.dumps(update_dict),
    )
    return row


@router.delete("/jobs/{job_id}")
async def delete_client_job(
    job_id: int,
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """Soft-delete (draft) a job posting."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    existing = await fetch_one(
        "SELECT id FROM job_orders WHERE id = $1 AND client_id = $2 AND deleted_at IS NULL",
        job_id, client["id"],
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found or not owned by you")

    await execute(
        "UPDATE job_orders SET deleted_at = NOW(), status = 'deleted' WHERE id = $1",
        job_id,
    )

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        "client_job_delete", current_user["id"], "job", job_id,
        json.dumps({"deleted": True}),
    )
    return {"message": "Job deleted successfully"}


# ── Candidate Search ────────────────────────────────────────────────────

@router.get("/candidates")
async def search_candidates(
    specialisation: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    salary_min: Optional[int] = Query(None),
    salary_max: Optional[int] = Query(None),
    availability: Optional[str] = Query(None),
    years_experience_min: Optional[float] = Query(None),
    years_experience_max: Optional[float] = Query(None),
    skills: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """Search candidates with filters."""
    _require_candidate_access(current_user)

    conditions = ["c.deleted_at IS NULL"]
    params = []
    idx = 1

    if specialisation:
        conditions.append(f"c.current_title ILIKE ${idx}")
        params.append(f"%{specialisation}%")
        idx += 1
    if level:
        conditions.append(f"c.current_title ILIKE ${idx}")
        params.append(f"%{level}%")
        idx += 1
    if location:
        conditions.append(f"c.location ILIKE ${idx}")
        params.append(f"%{location}%")
        idx += 1
    if salary_min is not None:
        conditions.append(f"c.salary_expectation_max >= ${idx}")
        params.append(salary_min)
        idx += 1
    if salary_max is not None:
        conditions.append(f"c.salary_expectation_min <= ${idx}")
        params.append(salary_max)
        idx += 1
    if years_experience_min is not None:
        conditions.append(f"c.years_experience >= ${idx}")
        params.append(years_experience_min)
        idx += 1
    if years_experience_max is not None:
        conditions.append(f"c.years_experience <= ${idx}")
        params.append(years_experience_max)
        idx += 1
    if skills:
        skill_list = [s.strip() for s in skills.split(",") if s.strip()]
        for skill in skill_list:
            conditions.append(f"${idx} = ANY(c.skills)")
            params.append(skill)
            idx += 1

    where = " AND ".join(conditions)

    total = await fetch_val(f"SELECT COUNT(*) FROM candidates c WHERE {where}", *params) or 0

    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"""SELECT c.id, c.full_name, c.current_title, c.current_company,
                   c.location, c.skills, c.years_experience
            FROM candidates c
            WHERE {where}
            ORDER BY c.created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}""",
        *params_ext,
    )

    items = [_project_candidate_public(dict(r)) for r in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/candidates/{candidate_id}")
async def view_candidate_profile(
    candidate_id: int,
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """View a candidate's anonymised profile.

    Admin: unrestricted. Non-admin client: gated on WS-E.2's
    _require_candidate_access (verified + approved_by_admin_at) and then,
    below, on the candidate actually being in that client's own pipeline
    (job_orders/pipeline_entries) — an approved client still can't browse
    candidates outside their own pipeline via this endpoint.
    """
    _require_candidate_access(current_user)

    candidate = await fetch_one(
        """SELECT id, full_name, current_title, current_company,
                  location, skills, years_experience
           FROM candidates WHERE id = $1 AND deleted_at IS NULL""",
        candidate_id,
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if current_user["role"] != "admin":
        client = await _get_client_by_user(current_user["id"])
        in_pipeline = client and await fetch_one(
            "SELECT id FROM pipeline_entries WHERE client_id = $1 AND candidate_id = $2",
            client["id"], candidate_id,
        )
        if not in_pipeline:
            raise HTTPException(
                status_code=404, detail="Candidate not found",
            )

    return _project_candidate_public(dict(candidate))


# ── Pipeline ────────────────────────────────────────────────────────────

@router.post("/pipeline", status_code=201)
async def add_to_pipeline(
    data: PipelineAdd,
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """Add a candidate to the client's pipeline."""
    _require_candidate_access(current_user)

    client = await _get_client_by_user(current_user["id"])
    if not client:
        raise HTTPException(status_code=400, detail="Client profile not found")

    # Verify job belongs to client
    job = await fetch_one(
        "SELECT id FROM job_orders WHERE id = $1 AND client_id = $2 AND deleted_at IS NULL",
        data.job_id, client["id"],
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or not owned by you")

    # Verify candidate exists
    candidate = await fetch_one(
        "SELECT id FROM candidates WHERE id = $1 AND deleted_at IS NULL",
        data.candidate_id,
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Check if already in pipeline
    existing = await fetch_one(
        "SELECT id FROM pipeline_entries WHERE client_id = $1 AND candidate_id = $2 AND job_id = $3",
        client["id"], data.candidate_id, data.job_id,
    )
    if existing:
        raise HTTPException(status_code=409, detail="Candidate already in pipeline")

    entry = await fetch_one(
        """INSERT INTO pipeline_entries (client_id, candidate_id, job_id, stage, notes)
           VALUES ($1, $2, $3, $4, $5)
           RETURNING *""",
        client["id"], data.candidate_id, data.job_id, data.stage, data.notes,
    )

    # WS-C.5: the entry's starting stage is itself a history row
    # (from_stage=NULL), so a full pipeline_stage_history query for an
    # entry always has at least one row.
    await _record_stage_change(entry["id"], None, data.stage, current_user["id"])

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        "client_pipeline_add", current_user["id"], "pipeline_entry", entry["id"],
        json.dumps({"candidate_id": data.candidate_id, "job_id": data.job_id, "stage": data.stage}),
    )
    return entry


@router.get("/pipeline")
async def get_pipeline(
    job_id: Optional[int] = Query(None),
    stage: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """Get pipeline entries for the client."""
    _require_candidate_access(current_user)

    client = await _get_client_by_user(current_user["id"])
    if not client:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    conditions = ["pe.client_id = $1"]
    params = [client["id"]]
    idx = 2

    if job_id:
        conditions.append(f"pe.job_id = ${idx}")
        params.append(job_id)
        idx += 1
    if stage:
        conditions.append(f"pe.stage = ${idx}")
        params.append(stage)
        idx += 1

    where = " AND ".join(conditions)

    total = await fetch_val(f"SELECT COUNT(*) FROM pipeline_entries pe WHERE {where}", *params) or 0
    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"""SELECT pe.*, c.full_name, c.current_title, c.current_company,
                   c.location, c.skills, j.title AS job_title
            FROM pipeline_entries pe
            JOIN candidates c ON c.id = pe.candidate_id
            JOIN job_orders j ON j.id = pe.job_id
            WHERE {where}
            ORDER BY pe.created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}""",
        *params_ext,
    )

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.patch("/pipeline/{entry_id}/stage")
async def update_pipeline_stage(
    entry_id: int,
    data: PipelineStageUpdate,
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """Move a pipeline entry to a new stage. Scoped to the client's own
    pipeline -- an entry belonging to another client 404s, same pattern as
    every other client-portal lookup in this router."""
    _require_candidate_access(current_user)

    client = await _get_client_by_user(current_user["id"])
    if not client:
        raise HTTPException(status_code=400, detail="Client profile not found")

    entry = await fetch_one(
        "SELECT id, stage FROM pipeline_entries WHERE id = $1 AND client_id = $2",
        entry_id, client["id"],
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Pipeline entry not found")

    from_stage = entry["stage"]
    updated = await fetch_one(
        "UPDATE pipeline_entries SET stage = $1, updated_at = NOW() WHERE id = $2 RETURNING *",
        data.stage, entry_id,
    )

    if from_stage != data.stage:
        await _record_stage_change(entry_id, from_stage, data.stage, current_user["id"])
        await execute(
            "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
            "VALUES ($1, $2, $3, $4, $5::jsonb)",
            "client_pipeline_stage_change", current_user["id"], "pipeline_entry", entry_id,
            json.dumps({"from_stage": from_stage, "to_stage": data.stage}),
        )

    return updated


@router.get("/pipeline/{entry_id}/history")
async def get_pipeline_stage_history(
    entry_id: int,
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """Stage-change history for one pipeline entry -- scoped to the
    client's own entries only."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        raise HTTPException(status_code=400, detail="Client profile not found")

    entry = await fetch_one(
        "SELECT id FROM pipeline_entries WHERE id = $1 AND client_id = $2",
        entry_id, client["id"],
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Pipeline entry not found")

    rows = await fetch_all(
        "SELECT * FROM pipeline_stage_history WHERE pipeline_entry_id = $1 ORDER BY changed_at",
        entry_id,
    )
    return {"items": rows, "total": len(rows)}


# ── Analytics ───────────────────────────────────────────────────────────

@router.get("/analytics", response_model=ClientAnalytics)
async def get_client_analytics(current_user: dict = Depends(require_verified_role("client", "admin"))):
    """Get client analytics data."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        return ClientAnalytics()

    cid = client["id"]
    analytics = ClientAnalytics()

    # Time-to-hire: average days from job creation to being filled
    avg_ttd = await fetch_val(
        """SELECT AVG(EXTRACT(EPOCH FROM (j.filled_at - j.created_at)) / 86400)
           FROM job_orders j WHERE j.client_id = $1 AND j.filled_at IS NOT NULL""",
        cid,
    )
    analytics.time_to_hire_avg_days = round(float(avg_ttd), 1) if avg_ttd else None

    # Pipeline funnel counts
    analytics.pipeline_funnel = {}
    stages = await fetch_all(
        """SELECT stage, COUNT(*) as count FROM pipeline_entries
           WHERE client_id = $1 GROUP BY stage""",
        cid,
    )
    for s in stages:
        analytics.pipeline_funnel[s["stage"]] = s["count"]

    # Source breakdown
    analytics.source_breakdown = {}
    sources = await fetch_all(
        """SELECT c.source, COUNT(*) as count FROM matches m
           JOIN job_orders j ON j.id = m.job_id
           JOIN candidates c ON c.id = m.candidate_id
           WHERE j.client_id = $1 GROUP BY c.source""",
        cid,
    )
    for s in sources:
        analytics.source_breakdown[s["source"]] = s["count"]

    # Offer rate
    total_applied = await fetch_val(
        "SELECT COUNT(*) FROM matches m JOIN job_orders j ON j.id = m.job_id WHERE j.client_id = $1",
        cid,
    ) or 0
    total_offered = await fetch_val(
        "SELECT COUNT(*) FROM matches m JOIN job_orders j ON j.id = m.job_id WHERE j.client_id = $1 AND m.status = 'offered'",
        cid,
    ) or 0
    analytics.offer_rate = round(total_offered / total_applied * 100, 1) if total_applied > 0 else 0

    # Cost-per-hire (placeholder - uses fee_value from job_orders)
    avg_cost = await fetch_val(
        "SELECT AVG(fee_value) FROM job_orders WHERE client_id = $1 AND filled_at IS NOT NULL",
        cid,
    )
    analytics.cost_per_hire_avg = round(float(avg_cost), 2) if avg_cost else None

    return analytics


# ── Messages ────────────────────────────────────────────────────────────

@router.get("/messages", response_model=MessageListResponse)
async def get_client_messages(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """Get messages for this client."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        return MessageListResponse(messages=[], unread_count=0)

    total = await fetch_val(
        "SELECT COUNT(*) FROM outreach_messages WHERE campaign_id IN (SELECT id FROM outreach_campaigns WHERE job_id IN (SELECT id FROM job_orders WHERE client_id = $1))",
        client["id"],
    ) or 0
    unread = await fetch_val(
        "SELECT COUNT(*) FROM outreach_messages WHERE campaign_id IN (SELECT id FROM outreach_campaigns WHERE job_id IN (SELECT id FROM job_orders WHERE client_id = $1)) AND (opened_at IS NULL AND status != 'draft')",
        client["id"],
    ) or 0

    rows = await fetch_all(
        """SELECT om.* FROM outreach_messages om
           WHERE om.campaign_id IN (SELECT id FROM outreach_campaigns WHERE job_id IN (SELECT id FROM job_orders WHERE client_id = $1))
           ORDER BY om.created_at DESC LIMIT $2 OFFSET $3""",
        client["id"], limit, offset,
    )

    # is_read is derived, not a DB column -- outreach_messages has no
    # is_read field, only opened_at (see models.schemas.MessageResponse).
    messages = [
        MessageResponse(**{**dict(r), "is_read": r["opened_at"] is not None})
        for r in rows
    ]
    return MessageListResponse(messages=messages, unread_count=unread)


# ── Team ────────────────────────────────────────────────────────────────

@router.get("/team")
async def get_team_members(current_user: dict = Depends(require_verified_role("client", "admin"))):
    """Get team members for this client."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        return []

    members = await fetch_all(
        """SELECT u.id, u.email, u.full_name, u.role, u.is_verified, u.created_at
           FROM users u
           JOIN user_clients uc ON uc.user_id = u.id
           WHERE uc.client_id = $1 AND u.deleted_at IS NULL""",
        client["id"],
    )
    return members


@router.post("/team", status_code=201)
async def invite_team_member(
    data: TeamInvite,
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """Invite a team member (create user + link to client)."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        raise HTTPException(status_code=400, detail="Client profile not found")

    # Check if user already exists
    existing_user = await fetch_one(
        "SELECT id FROM users WHERE email = $1 AND deleted_at IS NULL",
        data.email.lower().strip(),
    )

    if existing_user:
        # Link existing user to client
        await execute(
            "INSERT INTO user_clients (user_id, client_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            existing_user["id"], client["id"],
        )
        await execute(
            "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
            "VALUES ($1, $2, $3, $4, $5::jsonb)",
            "client_team_invite", current_user["id"], "user", existing_user["id"],
            json.dumps({"client_id": client["id"], "existing_user": True}),
        )
        return {"message": "User added to team", "user_id": existing_user["id"]}

    # WS-E.3: no more server-generated password (temporary or otherwise) --
    # the account is created unverified, with an unusable random password
    # hash (same pattern as routers/auth.py google_callback's Google-only
    # accounts), and a one-time set-password token is e-mailed to the
    # invitee. POST /api/auth/set-password consumes that token, lets them
    # choose their own password, and marks the e-mail verified in the same
    # step -- there is never a plaintext password or a password-bearing
    # link in the API response, logs, or audit trail.
    unusable_password_hash = hash_password(secrets.token_urlsafe(32))
    set_password_token = secrets.token_urlsafe(32)
    token_hash = hash_token(set_password_token)

    # Privilege-escalation fix (WS-C.2): role is hardcoded to 'client' here
    # regardless of what the request body claims — TeamInvite.role is now a
    # Literal["client"] too, but the INSERT does not trust it either way.
    user = await fetch_one(
        """INSERT INTO users
           (email, password_hash, full_name, role, is_verified,
            verification_token_hash, verification_sent_at)
           VALUES ($1, $2, $3, 'client', FALSE, $4, NOW())
           RETURNING id, email, full_name, role""",
        data.email.lower().strip(), unusable_password_hash, data.full_name, token_hash,
    )
    if not user:
        raise HTTPException(status_code=500, detail="Failed to create user")

    # Link to client
    await execute(
        "INSERT INTO user_clients (user_id, client_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        user["id"], client["id"],
    )

    set_password_link = f"https://gsprecruitment.nl/verify?token={set_password_token}&mode=set-password"
    inviter_company = client.get("company_name") or "GSP Recruitment"
    email_sent = await email_service.send_email(
        to_email=user["email"],
        subject="Uitnodiging teamlid — GSP Recruitment",
        body_text=f"""Beste {user['full_name']},

Je bent uitgenodigd om je aan te sluiten bij het team van {inviter_company} op GSP Recruitment. Stel je wachtwoord in via onderstaande link om je account te activeren:
{set_password_link}

Deze link is 24 uur geldig.

Als je deze uitnodiging niet verwachtte, kun je dit bericht negeren.

Met vriendelijke groet,
GSP Recruitment
info@gsprecruitment.nl

---

Dear {user['full_name']},

You have been invited to join {inviter_company}'s team on GSP Recruitment. Set your password via the link below to activate your account:
{set_password_link}

This link is valid for 24 hours.

If you did not expect this invitation, you can ignore this message.

Kind regards,
GSP Recruitment
info@gsprecruitment.nl
""",
    )
    if not email_sent:
        logger.warning("Failed to send team-invite set-password e-mail to user_id=%s", user["id"])

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        "client_team_invite", current_user["id"], "user", user["id"],
        json.dumps({"client_id": client["id"], "existing_user": False}),
    )

    return {
        "message": "Team member invited successfully. A set-password link "
                    "was e-mailed to them; the account activates once they "
                    "use it.",
        "user_id": user["id"],
        "email": user["email"],
    }


# ── Client Profile ──────────────────────────────────────────────────────

@router.get("/profile")
async def get_client_profile(current_user: dict = Depends(require_verified_role("client", "admin"))):
    """Get this client's company profile."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        return {}
    return dict(client)


@router.patch("/profile")
async def update_client_profile(
    updates: ClientProfileUpdate,
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """Update this client's company profile."""
    client = await _get_client_by_user(current_user["id"])
    if not client:
        raise HTTPException(status_code=404, detail="Client profile not found")

    set_parts = []
    values = []
    idx = 1
    allowed = {"company_name", "industry", "location", "size_range"}
    update_dict = updates.model_dump(exclude_none=True)

    # Map 'website' to 'domain' column
    if "website" in update_dict:
        set_parts.append(f"domain = ${idx}")
        values.append(update_dict.pop("website"))
        idx += 1

    for key, val in update_dict.items():
        if key not in allowed:
            continue
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_parts:
        return dict(client)

    values.append(client["id"])
    updated = await fetch_one(
        f"UPDATE clients SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = ${idx} RETURNING *",
        *values,
    )
    return dict(updated)