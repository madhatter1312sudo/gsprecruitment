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
    HealthResponse,
)
from routers.health import get_health_detail
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
        # Also get the candidates record -- FK first (candidate_profiles.
        # candidate_id), e-mail match only as the fallback for a row
        # migrations/023's backfill hasn't linked yet.
        candidate = None
        if profile and profile.get("candidate_id"):
            candidate = await fetch_one(
                "SELECT id FROM candidates WHERE id = $1 AND deleted_at IS NULL", profile["candidate_id"],
            )
        if not candidate:
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
#     also the row created (and linked) once a self-registered user
#     verifies their e-mail -- routers/auth.py verify_email_hashed(), or
#     lazily on first matches/applications/saved-jobs/messages touch --
#     source='portal_registration' for that case).
#   - `candidate_profiles` (+ `users`): every self-registered candidate gets
#     one at POST /api/auth/register, regardless of whether a `candidates`
#     row was ever created for them (e.g. still unverified -- WS-E.2 keeps
#     unverified accounts from getting one at all).
#
# A self-registered candidate with no linked `candidates` row yet (still
# unverified, or verified but not yet backfilled) is otherwise invisible to
# GET /candidates, which reads `candidates` as its primary source. WS-C.16
# (migrations/023) replaced the e-mail-join dedupe this used to need with
# candidate_profiles.candidate_id -- the FK is now the single source of
# truth for "does this profile already have a candidates row". Two plain
# queries (below), combined here in Python rather than a single combined
# SQL statement: candidate_profiles.candidate_id IS NULL is exactly "not
# yet linked", so the second query needs no NOT EXISTS/email-join to avoid
# double-counting either. Results are merged and re-sorted in Python --
# read-only, no data copied between tables.

_MATCH_COUNTS_JOIN = """
    LEFT JOIN (
        SELECT candidate_id,
               COUNT(*) AS match_count,
               COUNT(*) FILTER (WHERE status = 'placed') AS placement_count
        FROM matches
        GROUP BY candidate_id
    ) m ON m.candidate_id = c.id
"""


def _unlinked_self_registered_applicable(status: Optional[str], source: Optional[str], kind: Optional[str]) -> bool:
    """The candidate_profiles-only branch (no linked candidates row) is
    always kind='self-registered', status='new', source='self_registered'
    -- if a filter rules any of those out, that branch can contribute zero
    rows and the query for it can be skipped entirely."""
    if status and status != "new":
        return False
    if source and source != "self_registered":
        return False
    if kind and kind != "self-registered":
        return False
    return True


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
    # ── Branch A: candidates table (sourced, plus already-linked self-registered) ──
    a_conditions = ["c.deleted_at IS NULL"]
    a_params = []
    idx = 1
    kind_sql = "CASE WHEN c.source = 'portal_registration' THEN 'self-registered' ELSE 'sourced' END"

    if status:
        a_conditions.append(f"c.status = ${idx}")
        a_params.append(status)
        idx += 1
    if source:
        a_conditions.append(f"c.source = ${idx}")
        a_params.append(source)
        idx += 1
    if kind:
        a_conditions.append(f"({kind_sql}) = ${idx}")
        a_params.append(kind)
        idx += 1
    if search:
        a_conditions.append(f"(c.full_name ILIKE ${idx} OR c.email ILIKE ${idx} OR c.current_title ILIKE ${idx})")
        a_params.append(f"%{search}%")
        idx += 1
    a_where = " AND ".join(a_conditions)

    fetch_cap = offset + limit  # enough rows from each branch to merge+slice correctly

    a_total = await fetch_val(f"SELECT COUNT(*) FROM candidates c WHERE {a_where}", *a_params) or 0
    a_rows = await fetch_all(
        f"""SELECT c.id AS candidate_id,
                   u.id AS user_id,
                   ({kind_sql}) AS kind,
                   c.full_name, c.email, c.phone, c.current_title, c.current_company, c.location,
                   COALESCE(c.skills, '{{}}') AS skills, COALESCE(c.languages, '{{}}') AS languages,
                   c.years_experience, c.status, c.source, c.cv_file_path,
                   u.is_verified, c.created_at, c.updated_at,
                   COALESCE(m.match_count, 0) AS match_count,
                   COALESCE(m.placement_count, 0) AS placement_count
            FROM candidates c
            LEFT JOIN candidate_profiles cp ON cp.candidate_id = c.id
            LEFT JOIN users u ON u.id = COALESCE(
                cp.user_id,
                (SELECT id FROM users WHERE LOWER(email) = LOWER(c.email) AND deleted_at IS NULL LIMIT 1)
            )
            {_MATCH_COUNTS_JOIN}
            WHERE {a_where}
            ORDER BY c.created_at DESC
            LIMIT ${idx}""",
        *a_params, fetch_cap,
    )

    # ── Branch B: candidate_profiles rows with no linked candidates row yet ──
    b_rows = []
    b_total = 0
    if _unlinked_self_registered_applicable(status, source, kind):
        b_conditions = ["u.role = 'candidate'", "u.deleted_at IS NULL", "cp.candidate_id IS NULL"]
        b_params = []
        bidx = 1
        if search:
            b_conditions.append(f"(u.full_name ILIKE ${bidx} OR u.email ILIKE ${bidx} OR cp.current_title ILIKE ${bidx})")
            b_params.append(f"%{search}%")
            bidx += 1
        b_where = " AND ".join(b_conditions)

        b_total = await fetch_val(
            f"SELECT COUNT(*) FROM candidate_profiles cp JOIN users u ON u.id = cp.user_id WHERE {b_where}",
            *b_params,
        ) or 0
        b_rows = await fetch_all(
            f"""SELECT NULL::int AS candidate_id,
                       u.id AS user_id,
                       'self-registered' AS kind,
                       u.full_name, u.email, cp.phone, cp.current_title, cp.current_company, cp.location,
                       COALESCE(cp.skills, '{{}}') AS skills, COALESCE(cp.languages, '{{}}') AS languages,
                       cp.years_experience, 'new'::varchar AS status, 'self_registered'::varchar AS source,
                       cp.cv_file_path, u.is_verified, cp.created_at, cp.updated_at,
                       0 AS match_count, 0 AS placement_count
                FROM candidate_profiles cp
                JOIN users u ON u.id = cp.user_id
                WHERE {b_where}
                ORDER BY cp.created_at DESC
                LIMIT ${bidx}""",
            *b_params, fetch_cap,
        )

    combined = sorted(list(a_rows) + list(b_rows), key=lambda r: r["created_at"], reverse=True)
    page = combined[offset:offset + limit]
    items = [
        {**dict(row), "id": row["candidate_id"] if row["candidate_id"] is not None else row["user_id"]}
        for row in page
    ]

    return {"items": items, "total": a_total + b_total, "limit": limit, "offset": offset}


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
        # FK first (candidate_profiles.candidate_id -> this candidate);
        # e-mail match is only the fallback for a row this migration's
        # backfill hasn't linked yet (see migrations/023).
        linked_profile = await fetch_one(
            "SELECT user_id FROM candidate_profiles WHERE candidate_id = $1", candidate["id"],
        )
        if linked_profile:
            user = await fetch_one(
                "SELECT id, is_verified FROM users WHERE id = $1 AND deleted_at IS NULL",
                linked_profile["user_id"],
            )
        else:
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
        # person (verify-time link, lazy _get_candidate_id(), or a separate
        # sourced entry that shares this email), surface it too --
        # read-only, no merge. FK first, e-mail fallback only for a row
        # this migration's backfill hasn't linked yet (migrations/023).
        candidate = None
        if profile and profile.get("candidate_id"):
            candidate = await fetch_one(
                "SELECT id, status, source FROM candidates WHERE id = $1 AND deleted_at IS NULL",
                profile["candidate_id"],
            )
        if not candidate:
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