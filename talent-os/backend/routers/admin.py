"""
Talent OS — Admin Portal Router (JWT-protected, role='admin').
Endpoints for platform administration: dashboard, users, jobs, candidates,
analytics, audit log, content management, system settings.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query, status
from core.database import fetch_one, fetch_all, execute, fetch_val
from core.deps import get_current_user, require_role
from core.security import create_access_token
from models.schemas import (
    AdminDashboard, AdminUserUpdate, AdminJobUpdate, AdminAnalytics,
    AuditLogEntry, ContentItem, ContentUpdate, SystemSettings, SystemSettingsUpdate,
    HealthResponse, PipelineStageUpdate, LeadReadUpdate, LEAD_INTEREST_TYPES,
)
from routers.health import get_health_detail
from routers.client import _record_stage_change
from typing import Optional, List
from datetime import timedelta
import asyncio

router = APIRouter(prefix="/api/v1/admin", tags=["admin-portal"])


# ── Health (detail) ─────────────────────────────────────────────────────
# GET /health stays public but minimal (status/version/database) for the
# uptime monitor; row counts and vendor/integration status live here,
# behind an admin JWT (WS-C.3a).

@router.get("/health", response_model=HealthResponse)
async def get_admin_health(current_user: dict = Depends(require_role("admin"))):
    """Detailed health: database, OpenRouter/Apollo config status, and live
    row counts (candidates_count, open_jobs). Read-only, so not audit-logged."""
    return await get_health_detail()


# ── Dashboard ───────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=AdminDashboard)
async def get_admin_dashboard(current_user: dict = Depends(require_role("admin"))):
    """Get platform-wide dashboard stats."""
    stats = AdminDashboard()
    total_users, active_jobs, registered_candidates, active_clients, placements_this_week = await asyncio.gather(
        fetch_val("SELECT COUNT(*) FROM users WHERE deleted_at IS NULL"),
        fetch_val("SELECT COUNT(*) FROM job_orders WHERE status = 'open' AND deleted_at IS NULL AND is_demo = false"),
        fetch_val("SELECT COUNT(*) FROM users WHERE role = 'candidate' AND deleted_at IS NULL"),
        fetch_val("SELECT COUNT(*) FROM clients WHERE deleted_at IS NULL"),
        fetch_val(
            """SELECT COUNT(*) FROM matches
               WHERE status = 'placed'
               AND created_at >= DATE_TRUNC('week', NOW())""",
        ),
    )
    stats.total_users = total_users or 0
    stats.active_jobs = active_jobs or 0
    stats.registered_candidates = registered_candidates or 0
    stats.active_clients = active_clients or 0
    stats.placements_this_week = placements_this_week or 0
    return stats


# ── User Management ─────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    role: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_role("admin")),
):
    """List all users with filters (role, status, search)."""
    conditions = ["deleted_at IS NULL"]
    params = []
    idx = 1

    if role:
        conditions.append(f"role = ${idx}")
        params.append(role)
        idx += 1
    if status_filter == "verified":
        conditions.append("is_verified = TRUE")
    elif status_filter == "unverified":
        conditions.append("is_verified = FALSE")
    if search:
        conditions.append(f"(full_name ILIKE ${idx} OR email ILIKE ${idx})")
        params.append(f"%{search}%")
        idx += 1

    where = " AND ".join(conditions)

    total = await fetch_val(f"SELECT COUNT(*) FROM users WHERE {where}", *params) or 0
    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"SELECT id, email, full_name, role, is_verified, created_at, updated_at FROM users WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
        *params_ext,
    )

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """Get detailed user info including profile data."""
    user = await fetch_one(
        "SELECT id, email, full_name, role, is_verified, created_at, updated_at FROM users WHERE id = $1 AND deleted_at IS NULL",
        user_id,
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get role-specific profile
    if user["role"] == "candidate":
        profile = await fetch_one(
            "SELECT * FROM candidate_profiles WHERE user_id = $1", user_id,
        )
        if profile:
            user["profile"] = profile
        # Also get the candidates record
        candidate = await fetch_one(
            "SELECT id FROM candidates WHERE LOWER(email) = LOWER($1) AND deleted_at IS NULL",
            user["email"],
        )
        if candidate:
            user["candidate_id"] = candidate["id"]
            match_count = await fetch_val(
                "SELECT COUNT(*) FROM matches WHERE candidate_id = $1", candidate["id"],
            )
            user["match_count"] = match_count or 0
    elif user["role"] == "client":
        client = await fetch_one(
            """SELECT c.* FROM clients c
               JOIN user_clients uc ON uc.client_id = c.id
               WHERE uc.user_id = $1""",
            user_id,
        )
        if client:
            user["client"] = client
            job_count = await fetch_val(
                "SELECT COUNT(*) FROM job_orders WHERE client_id = $1", client["id"],
            )
            user["job_count"] = job_count or 0

    return user


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    updates: AdminUserUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    """Update a user (verify, suspend, change role)."""
    # Prevent self-demotion
    if user_id == current_user["id"] and updates.role is not None and updates.role != "admin":
        raise HTTPException(status_code=400, detail="Cannot change your own admin role")

    set_parts = []
    values = []
    idx = 1
    allowed = {"full_name", "email", "role", "is_verified"}

    update_dict = updates.model_dump(exclude_none=True)
    for key, val in update_dict.items():
        if key not in allowed:
            continue
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_parts:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    values.append(user_id)
    row = await fetch_one(
        f"UPDATE users SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = ${idx} AND deleted_at IS NULL RETURNING id, email, full_name, role, is_verified, created_at, updated_at",
        *values,
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    # Audit log
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) VALUES ($1, $2, $3, $4, $5::jsonb)",
        "user_update", current_user["id"], "user", user_id, json.dumps(update_dict),
    )

    return row


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """Soft-delete a user account."""
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    row = await fetch_one(
        "UPDATE users SET deleted_at = NOW() WHERE id = $1 AND deleted_at IS NULL RETURNING id, email, full_name",
        user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    # Audit log
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) VALUES ($1, $2, $3, $4, $5::jsonb)",
        "user_delete", current_user["id"], "user", user_id, json.dumps({"deleted": True}),
    )

    return {"message": f"User '{row['email']}' deleted successfully"}


@router.post("/users/{user_id}/impersonate")
async def impersonate_user(
    user_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """Generate a token to impersonate a user (admin only)."""
    target = await fetch_one(
        "SELECT id, email, full_name, role, is_verified FROM users WHERE id = $1 AND deleted_at IS NULL",
        user_id,
    )
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Create a short-lived impersonation token
    token = create_access_token(
        data={"sub": target["id"], "role": target["role"], "impersonator": current_user["id"]},
        expires_delta=timedelta(minutes=15),
    )

    # Audit log
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) VALUES ($1, $2, $3, $4, $5::jsonb)",
        "impersonate", current_user["id"], "user", user_id, json.dumps({"impersonated_email": target["email"]}),
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": target,
        "impersonated": True,
    }


@router.post("/users/{user_id}/unlock")
async def unlock_user(
    user_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """WS-E.4: clear an account's login lockout (failed_login_count /
    locked_until) early -- e.g. a legitimate user got rate-limited by
    their own retries. Does not touch password_hash or
    password_changed_at, so any JWT already issued to this user stays
    valid (unlocking is not a password reset)."""
    row = await fetch_one(
        """UPDATE users
           SET failed_login_count = 0, locked_until = NULL, last_failed_login_at = NULL
           WHERE id = $1 AND deleted_at IS NULL
           RETURNING id, email, failed_login_count, locked_until""",
        user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    # Audit log
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) VALUES ($1, $2, $3, $4, $5::jsonb)",
        "user_unlock", current_user["id"], "user", user_id, json.dumps({"unlocked_email": row["email"]}),
    )

    return {"message": f"User '{row['email']}' unlocked successfully"}


# ── Job Management ──────────────────────────────────────────────────────

@router.get("/jobs")
async def list_all_jobs(
    status: Optional[str] = Query(None),
    client_id: Optional[int] = Query(None),
    include_demo: bool = Query(False, description="Include is_demo=true seed/placeholder jobs (default excludes them)."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_role("admin")),
):
    """List all jobs cross-client. Excludes is_demo jobs (migrations/012's
    6 seed vacancies) unless include_demo=true is explicitly passed."""
    conditions = ["j.deleted_at IS NULL"]
    params = []
    idx = 1

    if not include_demo:
        conditions.append("j.is_demo = false")
    if status:
        conditions.append(f"j.status = ${idx}")
        params.append(status)
        idx += 1
    if client_id:
        conditions.append(f"j.client_id = ${idx}")
        params.append(client_id)
        idx += 1

    where = " AND ".join(conditions)

    total = await fetch_val(f"SELECT COUNT(*) FROM job_orders j WHERE {where}", *params) or 0
    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"""SELECT j.*, c.company_name
            FROM job_orders j
            JOIN clients c ON c.id = j.client_id
            WHERE {where}
            ORDER BY j.created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}""",
        *params_ext,
    )

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.put("/jobs/{job_id}")
async def update_any_job(
    job_id: int,
    updates: AdminJobUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    """Update any job (approve, reject, feature, etc.)."""
    set_parts = []
    values = []
    idx = 1
    allowed = {
        "status", "title", "department", "seniority", "description",
        "requirements", "fee_percentage", "urgency",
        # WS-C.15 / WS-A.5 (migrations/016_job_orders_columns.py)
        "city", "company_display", "employment_type", "sponsorship_possible",
    }

    update_dict = updates.model_dump(exclude_none=True)
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
        f"UPDATE job_orders SET {', '.join(set_parts)} WHERE id = ${idx} AND deleted_at IS NULL RETURNING *",
        *values,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    # Audit log
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) VALUES ($1, $2, $3, $4, $5::jsonb)",
        "job_update", current_user["id"], "job", job_id, json.dumps(update_dict),
    )

    return row


# ── Candidate Management ────────────────────────────────────────────────
#
# Two independent origins feed the admin candidate list:
#   - `candidates`: the sourcing pipeline (Apollo pulls, manual entry, and
#     also the lazily-created row `candidate.py:_get_candidate_id()` inserts
#     the first time a self-registered user touches matches/applications
#     /saved-jobs/messages -- source='portal_registration' for that case).
#   - `candidate_profiles` (+ `users`): every self-registered candidate gets
#     one at POST /api/auth/register, regardless of whether a `candidates`
#     row was ever created for them.
#
# A self-registered candidate who never triggered the lazy-create only has a
# candidate_profiles row and was previously invisible to GET /candidates,
# which read `candidates` exclusively. The CTE below unions both origins,
# using NOT EXISTS (by email) to skip candidate_profiles rows that already
# have a matching candidates row so each real person appears exactly once.
# No data is copied between tables -- this is read-only.
_CANDIDATES_UNION_CTE = """
WITH combined AS (
    SELECT
        c.id AS candidate_id,
        u.id AS user_id,
        CASE WHEN c.source = 'portal_registration' THEN 'self-registered' ELSE 'sourced' END AS kind,
        c.full_name, c.email, c.phone, c.current_title, c.current_company, c.location,
        COALESCE(c.skills, '{}') AS skills, COALESCE(c.languages, '{}') AS languages,
        c.years_experience, c.status, c.source, c.cv_file_path,
        u.is_verified, c.created_at, c.updated_at
    FROM candidates c
    LEFT JOIN users u ON LOWER(u.email) = LOWER(c.email) AND u.deleted_at IS NULL
    WHERE c.deleted_at IS NULL

    UNION ALL

    SELECT
        NULL::int AS candidate_id,
        u.id AS user_id,
        'self-registered' AS kind,
        u.full_name, u.email, cp.phone, cp.current_title, cp.current_company, cp.location,
        COALESCE(cp.skills, '{}') AS skills, COALESCE(cp.languages, '{}') AS languages,
        cp.years_experience, 'new'::varchar AS status, 'self_registered'::varchar AS source, cp.cv_file_path,
        u.is_verified, cp.created_at, cp.updated_at
    FROM candidate_profiles cp
    JOIN users u ON u.id = cp.user_id AND u.deleted_at IS NULL
    WHERE u.role = 'candidate'
      AND NOT EXISTS (
          SELECT 1 FROM candidates c2 WHERE LOWER(c2.email) = LOWER(u.email) AND c2.deleted_at IS NULL
      )
)
"""


@router.get("/candidates")
async def list_all_candidates(
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    kind: Optional[str] = Query(None, description="'sourced' or 'self-registered'"),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_role("admin")),
):
    """List all candidates across the platform -- sourced (candidates table)
    and self-registered (candidate_profiles + users) in one consistent shape.

    Each item carries `kind` ('sourced' | 'self-registered') plus `candidate_id`
    and/or `user_id` (one may be null depending on origin) and a convenience
    `id` = candidate_id if present else user_id, for addressing the detail
    endpoint at GET /candidates/{kind}/{id}.
    """
    conditions = ["1=1"]
    params = []
    idx = 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if source:
        conditions.append(f"source = ${idx}")
        params.append(source)
        idx += 1
    if kind:
        conditions.append(f"kind = ${idx}")
        params.append(kind)
        idx += 1
    if search:
        conditions.append(f"(full_name ILIKE ${idx} OR email ILIKE ${idx} OR current_title ILIKE ${idx})")
        params.append(f"%{search}%")
        idx += 1

    where = " AND ".join(conditions)

    total = await fetch_val(
        f"{_CANDIDATES_UNION_CTE} SELECT COUNT(*) FROM combined WHERE {where}", *params,
    ) or 0
    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"""{_CANDIDATES_UNION_CTE}
            SELECT combined.*,
                   COALESCE(combined.candidate_id, combined.user_id) AS id,
                   COALESCE(m.match_count, 0) AS match_count,
                   COALESCE(m.placement_count, 0) AS placement_count
            FROM combined
            LEFT JOIN (
                SELECT candidate_id,
                       COUNT(*) AS match_count,
                       COUNT(*) FILTER (WHERE status = 'placed') AS placement_count
                FROM matches
                GROUP BY candidate_id
            ) m ON m.candidate_id = combined.candidate_id
            WHERE {where}
            ORDER BY combined.created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}""",
        *params_ext,
    )

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/candidates/{kind}/{item_id}")
async def get_candidate_detail(
    kind: str,
    item_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """Full detail for one candidate, addressed by the `kind`/`id` pair
    returned from GET /candidates.

    - kind='sourced': item_id is a `candidates.id`.
    - kind='self-registered': item_id is a `users.id` -- returns the full
      candidate_profiles row, the linked user's email/verification status,
      and (if the sourcing pipeline separately created one, e.g. via the
      lazy _get_candidate_id() path) the matching `candidates` row too.
    """
    if kind == "sourced":
        candidate = await fetch_one(
            """SELECT c.*, COALESCE(m.match_count, 0) AS match_count,
                      COALESCE(m.placement_count, 0) AS placement_count
               FROM candidates c
               LEFT JOIN (
                   SELECT candidate_id,
                          COUNT(*) AS match_count,
                          COUNT(*) FILTER (WHERE status = 'placed') AS placement_count
                   FROM matches
                   GROUP BY candidate_id
               ) m ON m.candidate_id = c.id
               WHERE c.id = $1 AND c.deleted_at IS NULL""",
            item_id,
        )
        if not candidate:
            raise HTTPException(status_code=404, detail="Candidate not found")
        candidate["skills"] = candidate["skills"] or []
        candidate["languages"] = candidate["languages"] or []
        candidate["tags"] = candidate["tags"] or []
        user = await fetch_one(
            "SELECT id, is_verified FROM users WHERE LOWER(email) = LOWER($1) AND deleted_at IS NULL",
            candidate["email"],
        )
        candidate["kind"] = "self-registered" if candidate["source"] == "portal_registration" else "sourced"
        candidate["user_id"] = user["id"] if user else None
        candidate["is_verified"] = user["is_verified"] if user else None
        return candidate

    if kind == "self-registered":
        user = await fetch_one(
            "SELECT id, email, full_name, role, is_verified, created_at, updated_at FROM users WHERE id = $1 AND deleted_at IS NULL",
            item_id,
        )
        if not user or user["role"] != "candidate":
            raise HTTPException(status_code=404, detail="Candidate not found")

        profile = await fetch_one(
            "SELECT * FROM candidate_profiles WHERE user_id = $1", item_id,
        )
        if profile:
            profile["skills"] = profile["skills"] or []
            profile["languages"] = profile["languages"] or []
        user["profile"] = profile
        user["kind"] = "self-registered"

        # If the sourcing pipeline also created a candidates row for this
        # person (lazy _get_candidate_id(), or a separate sourced entry that
        # shares this email), surface it too -- read-only, no merge.
        candidate = await fetch_one(
            "SELECT id, status, source FROM candidates WHERE LOWER(email) = LOWER($1) AND deleted_at IS NULL",
            user["email"],
        )
        if candidate:
            user["candidate_id"] = candidate["id"]
            user["candidate_status"] = candidate["status"]
            user["candidate_source"] = candidate["source"]
            match_count = await fetch_val(
                "SELECT COUNT(*) FROM matches WHERE candidate_id = $1", candidate["id"],
            )
            user["match_count"] = match_count or 0
        else:
            user["candidate_id"] = None
            user["match_count"] = 0

        return user

    raise HTTPException(status_code=400, detail="kind must be 'sourced' or 'self-registered'")


# ── Analytics ───────────────────────────────────────────────────────────

@router.get("/analytics", response_model=AdminAnalytics)
async def get_platform_analytics(current_user: dict = Depends(require_role("admin"))):
    """Get platform-wide analytics data."""
    analytics = AdminAnalytics()

    (
        user_growth_rows, total_jobs, filled_jobs, total_clients, repeat_clients,
    ) = await asyncio.gather(
        fetch_all(
            """SELECT DATE_TRUNC('month', created_at) AS month, COUNT(*) AS count
               FROM users WHERE deleted_at IS NULL AND created_at >= NOW() - INTERVAL '12 months'
               GROUP BY month ORDER BY month""",
        ),
        fetch_val("SELECT COUNT(*) FROM job_orders WHERE deleted_at IS NULL AND is_demo = false"),
        fetch_val("SELECT COUNT(*) FROM job_orders WHERE filled_at IS NOT NULL AND deleted_at IS NULL AND is_demo = false"),
        fetch_val("SELECT COUNT(*) FROM clients WHERE deleted_at IS NULL"),
        fetch_val(
            """SELECT COUNT(*) FROM (
                   SELECT client_id FROM job_orders
                   WHERE filled_at IS NOT NULL AND deleted_at IS NULL
                   GROUP BY client_id HAVING COUNT(*) > 1
               ) repeat_client_groups""",
        ),
    )

    analytics.user_growth = {str(r["month"]): r["count"] for r in user_growth_rows}

    total_jobs = total_jobs or 0
    filled_jobs = filled_jobs or 0
    analytics.job_fill_rate = round(filled_jobs / total_jobs * 100, 1) if total_jobs > 0 else 0

    total_clients = total_clients or 0
    repeat_clients = repeat_clients or 0
    analytics.client_retention_rate = round(repeat_clients / total_clients * 100, 1) if total_clients > 0 else 0

    # Candidate satisfaction (simplified: placement rate)
    total_candidates, placed = await asyncio.gather(
        fetch_val("SELECT COUNT(*) FROM candidates WHERE deleted_at IS NULL"),
        fetch_val("SELECT COUNT(*) FROM matches WHERE status = 'placed'"),
    )
    total_candidates = total_candidates or 0
    placed = placed or 0
    analytics.candidate_satisfaction = round(placed / total_candidates * 100, 1) if total_candidates > 0 else 0

    return analytics


# ── Audit Log ───────────────────────────────────────────────────────────

@router.get("/audit-log")
async def get_audit_log(
    action: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_role("admin")),
):
    """Get audit log entries with optional filters."""
    conditions = []
    params = []
    idx = 1

    if action:
        conditions.append(f"action = ${idx}")
        params.append(action)
        idx += 1
    if target_type:
        conditions.append(f"target_type = ${idx}")
        params.append(target_type)
        idx += 1

    where = " WHERE " + " AND ".join(conditions) if conditions else ""

    total = await fetch_val(f"SELECT COUNT(*) FROM audit_log{where}", *params) or 0
    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"""SELECT al.*, u.email AS actor_email
            FROM audit_log al
            LEFT JOIN users u ON u.id = al.actor_id
            {where}
            ORDER BY al.created_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}""",
        *params_ext,
    )

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


# ── Content Management ──────────────────────────────────────────────────

@router.get("/content")
async def list_content_items(
    section: Optional[str] = Query(None),
    current_user: dict = Depends(require_role("admin")),
):
    """List content items, optionally filtered by section."""
    if section:
        rows = await fetch_all(
            "SELECT * FROM site_content WHERE section = $1 ORDER BY key",
            section,
        )
    else:
        rows = await fetch_all(
            "SELECT * FROM site_content ORDER BY section, key",
        )
    return rows


@router.put("/content/{content_id}")
async def update_content_item(
    content_id: int,
    updates: ContentUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    """Update a content item's value."""
    row = await fetch_one(
        "UPDATE site_content SET value = $1, updated_at = NOW() WHERE id = $2 RETURNING *",
        updates.value, content_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Content item not found")

    # Audit log
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) VALUES ($1, $2, $3, $4, $5::jsonb)",
        "content_update", current_user["id"], "content", content_id, json.dumps({"value": updates.value}),
    )

    return row


# ── System Settings ─────────────────────────────────────────────────────

@router.get("/settings", response_model=List[SystemSettings])
async def get_system_settings(current_user: dict = Depends(require_role("admin"))):
    """Get all system settings."""
    rows = await fetch_all(
        "SELECT * FROM system_settings ORDER BY key",
    )
    return rows


@router.put("/settings")
async def update_system_settings(
    updates: SystemSettingsUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    """Update system settings (bulk upsert)."""
    updated = []
    for key, value in updates.settings.items():
        await execute(
            """INSERT INTO system_settings (key, value) VALUES ($1, $2)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()""",
            key, str(value),
        )
        updated.append(key)

    # Audit log
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, changes) VALUES ($1, $2, $3, $4::jsonb)",
        "settings_update", current_user["id"], "settings", json.dumps({"updated_keys": updated}),
    )

    return {"message": "Settings updated", "keys_updated": updated}


# ── Client Approval (WS-E.2) ─────────────────────────────────────────────
# routers/client.py's _require_candidate_access gate: a client user must be
# e-mail-verified (WS-E.2) *and* explicitly approved here before any
# candidate-search/detail endpoint lets them through.

@router.post("/clients/{user_id}/approve")
async def approve_client(
    user_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """Approve a client user for candidate search/detail access."""
    target = await fetch_one(
        "SELECT id, email, role FROM users WHERE id = $1 AND deleted_at IS NULL",
        user_id,
    )
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] != "client":
        raise HTTPException(
            status_code=400,
            detail="Only client-role users can be approved for candidate access",
        )

    row = await fetch_one(
        """UPDATE users
           SET approved_by_admin_at = NOW(), approved_by_admin_id = $1, updated_at = NOW()
           WHERE id = $2
           RETURNING id, email, full_name, role, approved_by_admin_at, approved_by_admin_id""",
        current_user["id"], user_id,
    )

    # Audit log
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) VALUES ($1, $2, $3, $4, $5::jsonb)",
        "client_approve", current_user["id"], "user", user_id, json.dumps({"approved_email": target["email"]}),
    )

    return row


# ── Pipeline Stage History (WS-C.5) ──────────────────────────────────────
# Admin equivalent of routers/client.py's stage-update/history endpoints,
# unscoped by client (an admin may act on any client's pipeline).

@router.patch("/pipeline/{entry_id}/stage")
async def admin_update_pipeline_stage(
    entry_id: int,
    data: PipelineStageUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    entry = await fetch_one("SELECT id, stage FROM pipeline_entries WHERE id = $1", entry_id)
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
            "admin_pipeline_stage_change", current_user["id"], "pipeline_entry", entry_id,
            json.dumps({"from_stage": from_stage, "to_stage": data.stage}),
        )

    return updated


@router.get("/pipeline/{entry_id}/history")
async def admin_get_pipeline_stage_history(
    entry_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    entry = await fetch_one("SELECT id FROM pipeline_entries WHERE id = $1", entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Pipeline entry not found")

    rows = await fetch_all(
        "SELECT * FROM pipeline_stage_history WHERE pipeline_entry_id = $1 ORDER BY changed_at",
        entry_id,
    )
    return {"items": rows, "total": len(rows)}


# ── Leads (WS-C.10) ───────────────────────────────────────────────────────
# Unified view over contact_submissions (the site contact/lead form) and
# quiz_submissions (the public skill quiz) -- two physically separate
# tables (migrations/002_portal_tables.py, migrations/012_mobile_growth.py)
# with no shared id space, so "source" + the table's own id together
# identify a row; PATCH takes both back. quiz_submissions has no
# name/interest_type columns at all (it's the skill-quiz table, not a lead
# form) -- NULL literals in its SELECT keep the unified query's column
# count/types aligned with contact_submissions.
#
# Only these two literal table names are ever interpolated into SQL below
# (never request input) -- ``source not in _LEAD_SOURCES`` gates every use.
_LEAD_SOURCES = ("contact_submissions", "quiz_submissions")


@router.get("/leads")
async def list_leads(
    type: Optional[str] = Query(None, alias="type"),
    unread: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_role("admin")),
):
    """Unified leads list across contact_submissions + quiz_submissions.
    `type` filters by interest_type (contact_submissions only -- quiz_submissions
    rows never match a type filter, since they have no interest_type column).
    `unread` filters by is_read on whichever table each row is from."""
    if type is not None and type not in LEAD_INTEREST_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid type. Must be one of: {', '.join(LEAD_INTEREST_TYPES)}")

    contact_conditions = []
    contact_params: list = []
    idx = 1
    if type is not None:
        contact_conditions.append(f"interest_type = ${idx}")
        contact_params.append(type)
        idx += 1
    if unread is not None:
        contact_conditions.append(f"is_read = ${idx}")
        contact_params.append(not unread)
        idx += 1
    contact_where = f"WHERE {' AND '.join(contact_conditions)}" if contact_conditions else ""

    contact_rows = await fetch_all(
        f"""SELECT id, 'contact_submissions'::text AS source, name, email,
                   interest_type, is_read, created_at
            FROM contact_submissions {contact_where}
            ORDER BY created_at DESC""",
        *contact_params,
    )

    quiz_rows = []
    if type is None:
        # quiz_submissions has no interest_type -- a type filter never
        # matches any quiz row, so skip the query entirely in that case.
        quiz_conditions = []
        quiz_params: list = []
        idx = 1
        if unread is not None:
            quiz_conditions.append(f"is_read = ${idx}")
            quiz_params.append(not unread)
            idx += 1
        quiz_where = f"WHERE {' AND '.join(quiz_conditions)}" if quiz_conditions else ""
        quiz_rows = await fetch_all(
            f"""SELECT id, 'quiz_submissions'::text AS source, NULL::text AS name, email,
                       NULL::text AS interest_type, is_read, created_at
                FROM quiz_submissions {quiz_where}
                ORDER BY created_at DESC""",
            *quiz_params,
        )

    items = sorted(contact_rows + quiz_rows, key=lambda r: r["created_at"], reverse=True)
    total = len(items)
    page = items[offset:offset + limit]

    return {"items": page, "total": total, "limit": limit, "offset": offset}


@router.patch("/leads/{source}/{lead_id}")
async def update_lead_read_state(
    source: str,
    lead_id: int,
    data: LeadReadUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    if source not in _LEAD_SOURCES:
        raise HTTPException(status_code=404, detail="Unknown lead source")

    row = await fetch_one(
        f"UPDATE {source} SET is_read = $1 WHERE id = $2 RETURNING id, is_read",
        data.is_read, lead_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        "lead_read_state_update", current_user["id"], source, lead_id,
        json.dumps({"is_read": data.is_read}),
    )

    return row