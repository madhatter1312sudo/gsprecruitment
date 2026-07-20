"""
Talent OS — Outreach Drafts Admin Router (JWT-protected, role='admin').

AI drafts outreach emails (services/outreach_ai.py, services/scheduler.py)
but a human ALWAYS reviews/edits and explicitly approves before anything is
sent. There is no auto-send path anywhere in this router.
"""
import logging
from typing import Optional

import json
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from core.database import fetch_one, fetch_all, fetch_val, execute
from core.deps import require_role
from services.email_service import email_service
from services import scheduler as scheduler_service

logger = logging.getLogger("talent_os.outreach")

router = APIRouter(prefix="/api/v1/admin/outreach", tags=["outreach"])


class DraftUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


# ── Drafts ───────────────────────────────────────────────────────────────

@router.get("/drafts")
async def list_drafts(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_role("admin")),
):
    """List outreach drafts, optionally filtered by status."""
    conditions = []
    params = []
    idx = 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    total = await fetch_val(f"SELECT COUNT(*) FROM outreach_drafts {where}", *params) or 0
    params_ext = params + [limit, offset]
    rows = await fetch_all(
        f"""SELECT * FROM outreach_drafts {where}
            ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}""",
        *params_ext,
    )

    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.put("/drafts/{draft_id}")
async def update_draft(
    draft_id: int,
    updates: DraftUpdate,
    current_user: dict = Depends(require_role("admin")),
):
    """Edit a draft's subject/body. Only allowed while status='draft'."""
    existing = await fetch_one("SELECT * FROM outreach_drafts WHERE id = $1", draft_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Draft not found")
    if existing["status"] != "draft":
        raise HTTPException(status_code=400, detail=f"Cannot edit a draft with status '{existing['status']}'")

    update_dict = updates.model_dump(exclude_none=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_parts = []
    values = []
    idx = 1
    for key, val in update_dict.items():
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    values.append(draft_id)
    row = await fetch_one(
        f"UPDATE outreach_drafts SET {', '.join(set_parts)}, updated_at = NOW() "
        f"WHERE id = ${idx} RETURNING *",
        *values,
    )
    return row


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(
    draft_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """Approve a draft and send it. This is the ONLY path that sends an
    outreach email — it always requires an explicit human action."""
    draft = await fetch_one("SELECT * FROM outreach_drafts WHERE id = $1", draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["status"] != "draft":
        raise HTTPException(status_code=400, detail=f"Draft already '{draft['status']}'")
    if not draft["target_email"]:
        raise HTTPException(
            status_code=400,
            detail="No email — use LinkedIn URL in draft",
        )

    sent_ok = await email_service.send_email(
        to_email=draft["target_email"],
        subject=draft["subject"] or "",
        body_text=draft["body"] or "",
        to_name=draft["target_name"],
    )

    if sent_ok:
        row = await fetch_one(
            """UPDATE outreach_drafts
               SET status = 'sent', sent_at = NOW(), approved_by = $1, updated_at = NOW()
               WHERE id = $2 RETURNING *""",
            current_user["id"], draft_id,
        )

        # Best-effort mirror into outreach_messages, if the schema allows it
        # (some deployments have campaign_id NOT NULL there — skip gracefully).
        try:
            columns = await fetch_all(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'outreach_messages'",
            )
            col_names = {c["column_name"] for c in columns}
            required_missing = any(
                c["is_nullable"] == "NO" and c["column_name"] not in
                {"id", "created_at", "recipient_email", "subject", "body", "channel", "status"}
                for c in columns
            )
            if col_names and "recipient_email" in col_names and not required_missing:
                await execute(
                    """INSERT INTO outreach_messages (recipient_email, subject, body, channel, status)
                       VALUES ($1, $2, $3, 'email', 'sent')""",
                    draft["target_email"], draft["subject"], draft["body"],
                )
        except Exception:
            logger.info("outreach: skipping outreach_messages mirror (schema mismatch)")

        await execute(
            "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
            "VALUES ($1, $2, $3, $4, $5)",
            "outreach_draft_approved", current_user["id"], "outreach_draft", draft_id,
            json.dumps({"target_email": draft["target_email"], "sent": True}),
        )
        return row
    else:
        row = await fetch_one(
            "UPDATE outreach_drafts SET status = 'failed', updated_at = NOW() WHERE id = $1 RETURNING *",
            draft_id,
        )
        await execute(
            "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
            "VALUES ($1, $2, $3, $4, $5)",
            "outreach_draft_send_failed", current_user["id"], "outreach_draft", draft_id,
            json.dumps({"target_email": draft["target_email"], "sent": False}),
        )
        return row


@router.post("/drafts/{draft_id}/reject")
async def reject_draft(
    draft_id: int,
    current_user: dict = Depends(require_role("admin")),
):
    """Reject a draft — it will never be sent."""
    row = await fetch_one(
        "UPDATE outreach_drafts SET status = 'rejected', updated_at = NOW() WHERE id = $1 RETURNING *",
        draft_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found")

    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) "
        "VALUES ($1, $2, $3, $4, $5)",
        "outreach_draft_rejected", current_user["id"], "outreach_draft", draft_id, json.dumps({}),
    )
    return row


# ── Manual job triggers (testing) ───────────────────────────────────────

@router.post("/run/{job_name}", status_code=202)
async def run_job(
    job_name: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_role("admin")),
):
    """Manually trigger one of the scheduled pipeline jobs once, for testing."""
    job_fn = scheduler_service.JOBS_BY_NAME.get(job_name)
    if not job_fn:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown job '{job_name}'. Valid: {', '.join(scheduler_service.JOBS_BY_NAME)}",
        )

    background_tasks.add_task(job_fn)
    return {"message": f"Job '{job_name}' triggered"}
