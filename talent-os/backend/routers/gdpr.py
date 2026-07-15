"""
Talent OS — GDPR/AVG endpoints (JWT-protected).
Art. 15/20 (access/portability), Art. 17 (erasure), Art. 7(3) (consent withdrawal).
Uses the existing consent columns on candidates/users and data_subject_requests.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException

from core.database import fetch_one, fetch_all, execute
from core.deps import get_current_user

logger = logging.getLogger("talent_os.gdpr")

router = APIRouter(prefix="/api/v1/gdpr", tags=["gdpr"])


async def _log_request(request_type: str, email: str, summary: str) -> None:
    await execute(
        """INSERT INTO data_subject_requests (request_type, request_email, status, completed_at, response_summary)
           VALUES ($1, $2, 'completed', NOW(), $3)""",
        request_type, email, summary,
    )


@router.get("/export")
async def export_my_data(current_user: dict = Depends(get_current_user)):
    """Art. 15/20 — export all personal data we hold on the requesting user."""
    email = current_user["email"]

    user = await fetch_one(
        "SELECT id, email, full_name, role, is_verified, created_at FROM users WHERE id = $1",
        current_user["id"],
    )
    profile = await fetch_one(
        "SELECT * FROM candidate_profiles WHERE user_id = $1", current_user["id"],
    )
    candidate = await fetch_one(
        "SELECT * FROM candidates WHERE email = $1 AND deleted_at IS NULL", email,
    )
    applications = []
    saved = []
    if candidate:
        applications = await fetch_all(
            """SELECT m.status, m.match_score, m.created_at, j.title AS job_title
               FROM matches m JOIN job_orders j ON j.id = m.job_id
               WHERE m.candidate_id = $1""",
            candidate["id"],
        )
        saved = await fetch_all(
            """SELECT sj.created_at, j.title AS job_title
               FROM saved_jobs sj JOIN job_orders j ON j.id = sj.job_id
               WHERE sj.candidate_id = $1""",
            candidate["id"],
        )

    await _log_request("export", email, "Self-service data export via portal")

    def _clean(row):
        if row is None:
            return None
        d = dict(row)
        d.pop("password_hash", None)
        return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in d.items()}

    return {
        "user": _clean(user),
        "candidate_profile": _clean(profile),
        "candidate_record": _clean(candidate),
        "applications": [_clean(r) for r in applications],
        "saved_jobs": [_clean(r) for r in saved],
    }


@router.post("/withdraw-consent")
async def withdraw_consent(current_user: dict = Depends(get_current_user)):
    """Art. 7(3) — withdraw consent for data processing. Keeps the account but
    stops all sourcing/matching (matching excludes consent_withdrawn candidates)."""
    email = current_user["email"]
    await execute(
        "UPDATE candidates SET consent_withdrawn_at = NOW() WHERE email = $1 AND consent_withdrawn_at IS NULL",
        email,
    )
    await _log_request("consent_withdrawal", email, "Consent withdrawn via portal")
    return {"message": "Consent withdrawn. Your data will no longer be used for matching or outreach."}


@router.delete("/account")
async def erase_my_account(current_user: dict = Depends(get_current_user)):
    """Art. 17 — erasure. Soft-deletes the user and candidate records and
    anonymises PII. Placement/financial records are retained where legally
    required (fiscal retention), but no longer linked to identifiable data."""
    email = current_user["email"]
    user_id = current_user["id"]

    anon = f"deleted-user-{user_id}@erased.invalid"

    await execute(
        """UPDATE candidates SET
             full_name = 'Erased', email = $2, phone = NULL, linkedin_url = NULL,
             github_url = NULL, portfolio_url = NULL, cv_text = NULL, cv_file_path = NULL,
             education = NULL, deleted_at = NOW(), consent_withdrawn_at = COALESCE(consent_withdrawn_at, NOW())
           WHERE email = $1""",
        email, anon,
    )
    await execute(
        "UPDATE candidate_profiles SET cv_text = NULL, cv_file_path = NULL WHERE user_id = $1",
        user_id,
    )
    await execute(
        """UPDATE users SET full_name = 'Erased', email = $2, deleted_at = NOW()
           WHERE id = $1""",
        user_id, anon,
    )
    await _log_request("erasure", email, "Self-service account erasure via portal")
    logger.info("GDPR erasure completed for user %s", user_id)
    return {"message": "Your account and personal data have been erased."}
