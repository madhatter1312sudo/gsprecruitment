"""
Talent OS — Webhook router for Hermes agent submissions.
Accepts authenticated, HMAC-signed payloads from Hermes agents.
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from core.database import fetch_one
from core.config import settings
from models.schemas import WebhookPayload
import hashlib
import hmac

router = APIRouter(prefix="/api/hermes", tags=["webhook"])


def verify_hermes_signature(request: Request, payload_body: bytes) -> bool:
    """Verify the X-Hermes-Signature header."""
    signature = request.headers.get("X-Hermes-Signature", "")
    if not signature:
        return False
    expected = hmac.new(
        settings.webhook_secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def hermes_webhook(request: Request):
    """
    Endpoint for Hermes agents to submit candidates, updates, and signals.
    Requires X-Hermes-Signature header (HMAC-SHA256 of the raw body).
    """
    # Read raw body for signature verification
    body = await request.body()
    if not verify_hermes_signature(request, body):
        raise HTTPException(status_code=401, detail="Invalid or missing HMAC signature")

    payload = await request.json()
    action = payload.get("action", "")
    data = payload.get("data", {})
    agent = payload.get("agent", "unknown")

    if action == "candidate_found":
        row = await fetch_one(
            """INSERT INTO candidates
               (full_name, email, current_company, current_title, skills, source,
                sourced_by_agent, strength_score, switch_readiness, is_passive)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
               RETURNING id""",
            data.get("name"), data.get("email"), data.get("company"),
            data.get("title"), data.get("skills", []), data.get("source", "agent"),
            agent, data.get("strength_score", 0),
            data.get("switch_readiness", "UNKNOWN"),
            data.get("is_passive", True),
        )
        return {"received": True, "action": action, "candidate_id": row["id"] if row else None}

    elif action == "candidate_updated":
        candidate_id = data.get("id")
        if not candidate_id:
            raise HTTPException(status_code=400, detail="Missing candidate id in data")
        fields = []
        values = []
        idx = 1
        for key in ("screening_score", "screening_notes", "quality_score", "strength_score", "switch_readiness", "status"):
            if key in data:
                fields.append(f"{key} = ${idx}")
                values.append(data[key])
                idx += 1
        if not fields:
            return {"received": True, "action": action, "updated": False}
        values.append(candidate_id)
        await fetch_one(
            f"UPDATE candidates SET {', '.join(fields)}, updated_at = NOW() WHERE id = ${idx} RETURNING id",
            *values,
        )
        return {"received": True, "action": action, "updated": True}

    elif action == "signal_detected":
        row = await fetch_one(
            """INSERT INTO hiring_signals
               (company_name, domain, signal_type, signal_text, signal_date, confidence, source_url, detected_by_agent)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
               RETURNING id""",
            data.get("company_name"), data.get("domain"), data.get("signal_type"),
            data.get("signal_text"), data.get("signal_date"), data.get("confidence", 0.5),
            data.get("source_url"), agent,
        )
        return {"received": True, "action": action, "signal_id": row["id"] if row else None}

    else:
        return {"received": True, "action": action, "note": "Unknown action, data stored in payload log"}