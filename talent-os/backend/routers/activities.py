"""
Talent OS — Activities (WS-C.6): unified activity/task log.

Admin CRUD over `activities` (migrations/028_activities.py) -- notes,
calls, emails, meetings, tasks, and status-change entries attached to a
candidate/client/job/prospect/placement/lead. Distinct from
pipeline_stage_history (migrations/025, routers/client.py/admin.py),
which is an append-only log of one specific field transition
(pipeline_entries.stage) -- activities is the general-purpose log a
recruiter writes to directly.

Two routers:
  - `router` (admin, Bearer JWT): full CRUD under
    /api/v1/admin/activities, plus /api/v1/admin/activities/today for
    WS-B.10 reporting (open tasks due today or overdue).
  - `client_router` (client portal, Bearer JWT, role='client'/'admin'):
    create + list under /api/v1/client/activities, strictly scoped to
    the caller's own client -- subject_type is restricted to job (owned
    by the client) or candidate (in the client's own pipeline), and
    subject ownership is always resolved server-side via user_clients,
    never taken from the request body.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from core.database import fetch_one, fetch_all, fetch_val, execute
from core.deps import require_role, require_verified_role
from models.schemas import ActivityCreate, ActivityUpdate, ClientActivityCreate

logger = logging.getLogger("talent_os.activities")

router = APIRouter(prefix="/api/v1/admin/activities", tags=["activities-admin"])
client_router = APIRouter(prefix="/api/v1/client/activities", tags=["activities-portal"])


async def _audit_activity(action: str, actor_id: int, target_id: int, row: dict) -> None:
    """Code-review follow-up: the free-text `body` of an activity must
    never land in audit_log -- it can carry candidate/client personal
    data far beyond what an audit trail needs. Log only the shape of the
    change: {subject_type, subject_id, type, internal, has_body}."""
    changes = {
        "subject_type": row.get("subject_type"),
        "subject_id": row.get("subject_id"),
        "type": row.get("type"),
        "internal": row.get("internal"),
        "has_body": bool(row.get("body")),
    }
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
        action, actor_id, "activity", target_id, json.dumps(changes),
    )


async def _get_client_id(user_id: int) -> Optional[int]:
    client = await fetch_one(
        "SELECT c.id FROM clients c JOIN user_clients uc ON uc.client_id = c.id "
        "WHERE uc.user_id = $1",
        user_id,
    )
    return client["id"] if client else None


async def _client_owns_job(client_id: int, job_id: int) -> bool:
    row = await fetch_one(
        "SELECT id FROM job_orders WHERE id = $1 AND client_id = $2",
        job_id, client_id,
    )
    return row is not None


async def _client_owns_candidate(client_id: int, candidate_id: int) -> bool:
    """A candidate is 'the client's own' if it's in that client's pipeline
    (pipeline_entries) -- there is no direct client<->candidate ownership
    otherwise."""
    row = await fetch_one(
        "SELECT id FROM pipeline_entries WHERE client_id = $1 AND candidate_id = $2",
        client_id, candidate_id,
    )
    return row is not None


# ── Admin CRUD ────────────────────────────────────────────────────────────

@router.get("/today")
async def admin_activities_today(
    current_user: dict = Depends(require_role("admin")),
):
    """WS-B.10 reporting: open tasks (type='task', completed_at IS NULL)
    due today or overdue. Must be declared before /{activity_id} so
    FastAPI doesn't try to parse 'today' as an int path param."""
    rows = await fetch_all(
        """SELECT * FROM activities
           WHERE deleted_at IS NULL AND type = 'task' AND completed_at IS NULL
             AND due_at IS NOT NULL AND due_at <= (NOW() AT TIME ZONE 'UTC')::date + INTERVAL '1 day'
           ORDER BY due_at"""
    )
    return {"items": rows, "total": len(rows)}


@router.get("")
async def list_activities(
    subject_type: Optional[str] = Query(None),
    subject_id: Optional[int] = Query(None),
    open: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_role("admin")),
):
    conditions = ["deleted_at IS NULL"]
    params = []
    idx = 1

    if subject_type:
        conditions.append(f"subject_type = ${idx}")
        params.append(subject_type)
        idx += 1
    if subject_id is not None:
        conditions.append(f"subject_id = ${idx}")
        params.append(subject_id)
        idx += 1
    if open is not None:
        conditions.append("completed_at IS NULL" if open else "completed_at IS NOT NULL")

    where = " AND ".join(conditions)

    total = await fetch_val(f"SELECT COUNT(*) FROM activities WHERE {where}", *params) or 0
    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"""SELECT * FROM activities WHERE {where}
            ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}""",
        *params_ext,
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.post("", status_code=201)
async def create_activity(
    payload: ActivityCreate,
    current_user: dict = Depends(require_role("admin")),
):
    row = await fetch_one(
        """INSERT INTO activities
           (subject_type, subject_id, type, body, due_at, completed_at, created_by, internal)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
           RETURNING *""",
        payload.subject_type, payload.subject_id, payload.type, payload.body,
        payload.due_at, payload.completed_at, current_user["id"], payload.internal,
    )
    await _audit_activity("activity_create", current_user["id"], row["id"], row)
    return row


@router.patch("/{activity_id}")
async def update_activity(
    activity_id: int,
    updates: ActivityUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    update_dict = updates.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_parts = []
    values = []
    idx = 1
    for key, val in update_dict.items():
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    set_parts.append("updated_at = NOW()")

    values.append(activity_id)
    row = await fetch_one(
        f"""UPDATE activities SET {', '.join(set_parts)}
            WHERE id = ${idx} AND deleted_at IS NULL
            RETURNING *""",
        *values,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Activity not found")

    await _audit_activity("activity_update", current_user["id"], activity_id, row)
    return row


@router.delete("/{activity_id}", status_code=204)
async def delete_activity(
    activity_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """Soft delete -- sets deleted_at, never a real DELETE (same
    GDPR provenance/audit-trail pattern as client_contacts/clients)."""
    row = await fetch_one(
        """UPDATE activities SET deleted_at = NOW(), updated_at = NOW()
           WHERE id = $1 AND deleted_at IS NULL
           RETURNING *""",
        activity_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Activity not found")

    await _audit_activity("activity_delete", current_user["id"], activity_id, row)
    return None


# ── Client portal: create/list own activities only ────────────────────────

@client_router.get("")
async def list_own_client_activities(
    subject_type: Optional[str] = Query(None),
    subject_id: Optional[int] = Query(None),
    open: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    """A client sees only activities on subjects it owns -- job rows it
    posted, or candidates in its own pipeline. Enforced by joining on
    job_orders/pipeline_entries scoped to the caller's client_id, not by
    trusting subject_type/subject_id filters alone."""
    client_id = await _get_client_id(current_user["id"])
    if client_id is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    conditions = [
        "a.deleted_at IS NULL",
        # Code-review follow-up: a client must never see an internal
        # (recruiter-only) row, even on a subject it owns.
        "a.internal = false",
        "((a.subject_type = 'job' AND EXISTS "
        "(SELECT 1 FROM job_orders jo WHERE jo.id = a.subject_id AND jo.client_id = $1)) "
        "OR (a.subject_type = 'candidate' AND EXISTS "
        "(SELECT 1 FROM pipeline_entries pe WHERE pe.candidate_id = a.subject_id AND pe.client_id = $1)))",
    ]
    params = [client_id]
    idx = 2

    if subject_type:
        conditions.append(f"a.subject_type = ${idx}")
        params.append(subject_type)
        idx += 1
    if subject_id is not None:
        conditions.append(f"a.subject_id = ${idx}")
        params.append(subject_id)
        idx += 1
    if open is not None:
        conditions.append("a.completed_at IS NULL" if open else "a.completed_at IS NOT NULL")

    where = " AND ".join(conditions)

    total = await fetch_val(f"SELECT COUNT(*) FROM activities a WHERE {where}", *params) or 0
    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"""SELECT a.* FROM activities a WHERE {where}
            ORDER BY a.created_at DESC LIMIT ${idx} OFFSET ${idx + 1}""",
        *params_ext,
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@client_router.post("", status_code=201)
async def create_own_client_activity(
    payload: ClientActivityCreate,
    current_user: dict = Depends(require_verified_role("client", "admin")),
):
    client_id = await _get_client_id(current_user["id"])
    if client_id is None:
        raise HTTPException(status_code=403, detail="No client account for this user")

    if payload.subject_type == "job":
        owns = await _client_owns_job(client_id, payload.subject_id)
    else:  # 'candidate' -- ClientActivityCreate.subject_type only allows job|candidate
        owns = await _client_owns_candidate(client_id, payload.subject_id)

    if not owns:
        raise HTTPException(status_code=403, detail="Subject not owned by this client")

    row = await fetch_one(
        """INSERT INTO activities
           (subject_type, subject_id, type, body, due_at, completed_at, created_by, internal)
           VALUES ($1, $2, $3, $4, $5, $6, $7, false)
           RETURNING *""",
        payload.subject_type, payload.subject_id, payload.type, payload.body,
        payload.due_at, payload.completed_at, current_user["id"],
    )
    await _audit_activity("activity_create_client", current_user["id"], row["id"], row)
    return row
