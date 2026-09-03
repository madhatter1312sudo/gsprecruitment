"""
Talent OS — Outreach Drafts Admin Router (JWT-protected, role='admin').

AI drafts outreach emails (services/outreach_ai.py, services/scheduler.py)
but a human ALWAYS reviews/edits and explicitly approves before anything is
sent. There is no auto-send path anywhere in this router.
"""
import logging
import re
from typing import Optional

import json
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from core.database import fetch_one, fetch_all, fetch_val, execute
from core.deps import require_role
from core import privacy
from services.email_service import email_service
from services import scheduler as scheduler_service

logger = logging.getLogger("talent_os.outreach")

router = APIRouter(prefix="/api/v1/admin/outreach", tags=["outreach"])


# ── WS-E.7 draft-compliance checks (docs/SOURCING-SOP.md §3.2/§3.3, §7.1) ──
#
# Pure text checks first (no DB — testable in isolation), then a DB-backed
# refusal function approve_draft() calls. Nothing here sends anything;
# outreach stays draft-only, this only decides whether approve_draft() is
# allowed to proceed to the existing send.

_STOP_NL_RE = re.compile(r'antwoorden met\s*"?stop"?', re.IGNORECASE)
_STOP_EN_RE = re.compile(r'replying\s*"?stop"?', re.IGNORECASE)


def _has_optout_line(body: str) -> bool:
    """SOP §3.3 — every first message must contain the STOP opt-out
    sentence (NL: '...antwoorden met "STOP"' / EN: '...replying "STOP"')."""
    text = body or ""
    return bool(_STOP_NL_RE.search(text) or _STOP_EN_RE.search(text))


# The fixed Art. 14 text block (SOP §3.2) must carry: a functional sender
# address, the source description, the retention period ("3 maanden na" /
# "3 months after"), the right to object (Art. 21), the suppression-list
# sentence, and the complaint right to the Autoriteit Persoonsgegevens /
# Dutch DPA. Checked as markers rather than the full fixed string so minor
# whitespace/formatting differences in an LLM- or human-edited draft don't
# false-positive a refusal.
_ART14_MARKERS_NL = ("art. 21", "autoriteit persoonsgegevens", "blokkeerlijst", "3 maanden na")
_ART14_MARKERS_EN = ("art. 21", "data protection authority", "suppression list", "3 months after")


def _has_art14_block(body: str, language: Optional[str]) -> bool:
    text = (body or "").lower()
    markers = _ART14_MARKERS_EN if (language or "nl").lower().startswith("en") else _ART14_MARKERS_NL
    return all(marker in text for marker in markers)


# (status_code, code) — code is the stable machine-readable detail['code']
# reported back to callers and quoted in the PR report.
REFUSAL_MISSING_OPTOUT = (422, "missing_optout_line")
REFUSAL_MISSING_ART14 = (422, "missing_art14_block")
REFUSAL_RECIPIENT_OPTED_OUT = (409, "recipient_opted_out")
REFUSAL_RECIPIENT_SUPPRESSED = (409, "recipient_suppressed")
REFUSAL_PROSPECT_NO_LAWFUL_BASIS = (409, "prospect_missing_lawful_basis")
REFUSAL_CANDIDATE_NO_SPEC_CONSENT = (409, "candidate_missing_spec_consent")


async def _draft_refusal(draft: dict):
    """Returns (status_code, code, detail) if the draft must be refused, or
    None if it may proceed to approve_draft()'s existing send. DB-backed —
    see routers/gdpr.py / core/privacy.py for the suppression-list hash."""
    body = draft.get("body") or ""
    language = draft.get("language")

    if not _has_optout_line(body):
        status_code, code = REFUSAL_MISSING_OPTOUT
        return status_code, code, "Draft body is missing the required opt-out/STOP sentence (SOP §3.3)."

    target_email = draft.get("target_email")
    if target_email:
        suppressed = await fetch_one(
            "SELECT 1 FROM suppression_list WHERE email_hash = $1", privacy.email_hash(target_email),
        )
        if suppressed:
            status_code, code = REFUSAL_RECIPIENT_SUPPRESSED
            return status_code, code, "Recipient is on the suppression list (STOP received) — refusing to send."

    if draft.get("target_type") == "candidate":
        candidate = await fetch_one(
            "SELECT lawful_basis, consent_withdrawn_at, consent_spec_presentation_at "
            "FROM candidates WHERE id = $1",
            draft.get("target_id"),
        )
        if candidate:
            if candidate["consent_withdrawn_at"]:
                status_code, code = REFUSAL_RECIPIENT_OPTED_OUT
                return status_code, code, "Candidate has withdrawn consent (consent_withdrawn_at set) — refusing to send."
            if candidate["lawful_basis"] in ("gerechtvaardigd_belang", "toestemming_referral"):
                if not _has_art14_block(body, language):
                    status_code, code = REFUSAL_MISSING_ART14
                    return status_code, code, "Draft body is missing the Art. 14 notice block required for this lawful_basis (SOP §3.2)."

    elif draft.get("target_type") == "client_prospect":
        prospect = await fetch_one(
            "SELECT lawful_basis FROM client_prospects WHERE id = $1", draft.get("target_id"),
        )
        if prospect and not prospect["lawful_basis"]:
            status_code, code = REFUSAL_PROSPECT_NO_LAWFUL_BASIS
            return status_code, code, "Prospect has no lawful_basis recorded (Telecommunicatiewet art. 11.7, SOP §4) — refusing to send."

        # Spec-candidate / MPC presentation: a candidate being anonymously
        # presented to a client prospect (SOP §5). outreach_drafts has no
        # dedicated "candidate being presented" column for client_prospect
        # rows — job_id is reused as that reference here (it is otherwise
        # always NULL for prospect drafts, see services/harvest.py's
        # _draft_prospect_outreach). Flagged as an open question for the
        # owner in the PR report; a follow-up migration should give this
        # its own column if spec-presentation drafting is built out.
        presented_candidate_id = draft.get("job_id")
        if presented_candidate_id is not None:
            candidate = await fetch_one(
                "SELECT consent_spec_presentation_at FROM candidates WHERE id = $1", presented_candidate_id,
            )
            if not candidate or not candidate["consent_spec_presentation_at"]:
                status_code, code = REFUSAL_CANDIDATE_NO_SPEC_CONSENT
                return status_code, code, "Referenced candidate has no consent_spec_presentation_at — cannot present an anonymised profile to a client (SOP §5)."

    return None


class DraftUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None


class DraftCreate(BaseModel):
    """Create an outreach draft — used by external agents (e.g. a Claude
    cloud agent doing outreach drafting) instead of the in-backend
    OpenRouter drafting job (services/scheduler.py draft_outreach)."""
    target_type: str
    target_id: int
    target_email: str
    target_name: str
    company: Optional[str] = None
    job_id: Optional[int] = None
    channel: str = "email"
    language: str = "nl"
    subject: str
    body: str
    ai_model: str = "claude"


# ── Drafts ───────────────────────────────────────────────────────────────

@router.post("/drafts", status_code=201)
async def create_draft(
    payload: DraftCreate,
    current_user: dict = Depends(require_role("admin")),
):
    """Create a new outreach draft with status='draft'. Never sends —
    approval happens via POST /drafts/{id}/approve. Rejects (409) if a
    draft already exists for the same (target_type, target_id, job_id)
    with status='draft', mirroring the dedupe in services/scheduler.py's
    draft_outreach job."""
    existing = await fetch_one(
        """SELECT id FROM outreach_drafts
           WHERE target_type = $1 AND target_id = $2 AND job_id IS NOT DISTINCT FROM $3
             AND status = 'draft'""",
        payload.target_type, payload.target_id, payload.job_id,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A draft already exists for this target/job (id={existing['id']})",
        )

    row = await fetch_one(
        """INSERT INTO outreach_drafts
           (target_type, target_id, target_email, target_name, company,
            job_id, channel, language, subject, body, ai_model, status)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'draft')
           RETURNING *""",
        payload.target_type, payload.target_id, payload.target_email, payload.target_name,
        payload.company, payload.job_id, payload.channel, payload.language,
        payload.subject, payload.body, payload.ai_model,
    )
    return row


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

    refusal = await _draft_refusal(draft)
    if refusal:
        status_code, code, message = refusal
        raise HTTPException(status_code=status_code, detail={"code": code, "message": message})

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
            "VALUES ($1, $2, $3, $4, $5::jsonb)",
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
            "VALUES ($1, $2, $3, $4, $5::jsonb)",
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
        "VALUES ($1, $2, $3, $4, $5::jsonb)",
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
