"""
Talent OS — GDPR/AVG endpoints (JWT-protected).
Art. 15/20 (access/portability), Art. 17 (erasure), Art. 7(3) (consent withdrawal).
Uses the existing consent columns on candidates/users and data_subject_requests.
"""
import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from core.database import fetch_one, fetch_all, execute
from core.deps import get_current_user
from services import storage

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
    email_log_rows = await fetch_all(
        """SELECT to_email, template, subject, status, created_at
           FROM email_log WHERE LOWER(to_email) = LOWER($1)
           ORDER BY created_at DESC""",
        email,
    )
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
        "email_log": [_clean(r) for r in email_log_rows],
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

    # Delete the CV file(s) before nulling the columns -- previously the
    # column was nulled but the underlying file (local or, now, R2) was
    # never removed, leaving personal data behind after "erasure". A
    # candidate can have more than one `candidates` row match by email (the
    # anonymising UPDATE below hits all of them), so this reads every one of
    # them, not just the first -- and case-insensitively, matching how the
    # rest of the codebase compares emails (see routers/admin.py).
    profile = await fetch_one(
        "SELECT cv_file_path FROM candidate_profiles WHERE user_id = $1", user_id,
    )
    candidates = await fetch_all(
        "SELECT cv_file_path FROM candidates WHERE LOWER(email) = LOWER($1)", email,
    )

    all_rows = ([profile] if profile else []) + list(candidates)
    legacy_paths = {
        row["cv_file_path"] for row in all_rows
        if row and row["cv_file_path"] and not storage.is_r2_key(row["cv_file_path"])
    }
    referenced_r2_paths = {
        row["cv_file_path"] for row in all_rows
        if row and row["cv_file_path"] and storage.is_r2_key(row["cv_file_path"])
    }

    deleted_paths = []
    failed_paths = []

    # R2: delete the whole cv/{user_id}/ prefix rather than just the single
    # key currently referenced in the DB -- a re-upload before the
    # delete-old-key fix could have left earlier objects orphaned under the
    # same prefix, and this sweeps those up too.
    r2_prefix = storage.cv_prefix(user_id)
    if storage.is_configured():
        try:
            deleted_paths.extend(await storage.delete_prefix(r2_prefix))
        except Exception:
            logger.exception(
                "GDPR erasure: failed to delete R2 prefix %s for user %s", r2_prefix, user_id,
            )
            failed_paths.append(r2_prefix)

        # A referenced R2 key doesn't necessarily live under this user's own
        # cv/{user_id}/ prefix -- e.g. a row migrated by migrate_cv_to_r2.py
        # under cv/orphan-{candidate_id}/ before a users row existed for it.
        # The prefix sweep above can't find those, so delete any such stray
        # keys individually.
        stray_r2_paths = {p for p in referenced_r2_paths if not p.startswith(r2_prefix)}
        for cv_path in stray_r2_paths:
            try:
                await storage.delete_object(cv_path)
                deleted_paths.append(cv_path)
            except Exception:
                logger.exception(
                    "GDPR erasure: failed to delete stray R2 object %s for user %s", cv_path, user_id,
                )
                failed_paths.append(cv_path)
    elif referenced_r2_paths:
        # R2 isn't configured (env vars unset/removed) yet the DB still
        # references R2 keys we have no way to reach right now -- don't let
        # this look like a fully-completed erasure just because the R2 branch
        # above was skipped entirely; record it as a failure instead.
        logger.warning(
            "GDPR erasure: R2 not configured but user %s has R2-style cv_file_path values "
            "(%s) -- could not delete them", user_id, sorted(referenced_r2_paths),
        )
        failed_paths.append(r2_prefix)

    # Legacy local-disk paths (pre-R2 uploads) -- best-effort unlink, file
    # may already be gone (ephemeral disk, prior deploy wiped it).
    for cv_path in legacy_paths:
        try:
            local_path = os.path.join("/app/uploads/cv", os.path.basename(cv_path))
            if os.path.isfile(local_path):
                os.remove(local_path)
            deleted_paths.append(cv_path)
        except Exception:
            # Never fail the whole erasure because a CV file couldn't be
            # removed (already gone, storage backend unreachable) -- the DB
            # columns below still get nulled either way, but the failure is
            # recorded in the audit log rather than silently swallowed, so
            # it doesn't just disappear as if erasure fully succeeded.
            logger.exception(
                "GDPR erasure: failed to delete legacy CV file %s for user %s", cv_path, user_id,
            )
            failed_paths.append(cv_path)

    await execute(
        """UPDATE candidates SET
             full_name = 'Erased', email = $2, phone = NULL, linkedin_url = NULL,
             github_url = NULL, portfolio_url = NULL, cv_text = NULL, cv_file_path = NULL,
             education = NULL, deleted_at = NOW(), consent_withdrawn_at = COALESCE(consent_withdrawn_at, NOW())
           WHERE LOWER(email) = LOWER($1)""",
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

    # email_log (migration 015) and outreach_messages both hold a plaintext
    # recipient address outside the candidates/users/candidate_profiles rows
    # anonymised above -- without this they'd keep the identifiable email
    # after "erasure" completes. Rows are kept (subject/audit value, and
    # email_log.status feeds the not-yet-built delivery-failure dashboard)
    # but the address itself is anonymised, matching the `anon` placeholder
    # used everywhere else in this function.
    #
    # NOTE: this only anonymises on erasure. A time-based 12-month
    # email_log retention sweep (drop/anonymise rows older than that
    # regardless of erasure) is Phase 0.3 ARQ-worker follow-up, not yet
    # built -- see the plan doc's Fase 0.3.
    await execute(
        "UPDATE email_log SET to_email = $2, subject = NULL WHERE LOWER(to_email) = LOWER($1)",
        email, anon,
    )
    try:
        columns = await fetch_all(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'outreach_messages'",
        )
        col_names = {c["column_name"] for c in columns}
        if "recipient_email" in col_names:
            await execute(
                "UPDATE outreach_messages SET recipient_email = $2 WHERE LOWER(recipient_email) = LOWER($1)",
                email, anon,
            )
    except Exception:
        # Best-effort, same defensive stance as the outreach_messages mirror
        # in routers/outreach.py -- schema can vary by deployment; erasure
        # of the rows this function IS certain about must not be blocked by
        # a missing/renamed column on this one.
        logger.exception("GDPR erasure: failed to anonymise outreach_messages for user %s", user_id)

    completion_status = "partial" if failed_paths else "complete"
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) VALUES ($1, $2, $3, $4, $5::jsonb)",
        "gdpr_erasure", user_id, "user", user_id,
        json.dumps({
            "reason": "self-service erasure",
            "status": completion_status,
            "r2_prefix": r2_prefix,
            "cv_files_deleted": deleted_paths,
            "cv_files_failed": failed_paths,
        }),
    )
    await _log_request(
        "erasure", email,
        "Self-service account erasure via portal"
        + ("" if not failed_paths else f" -- WARNING: {len(failed_paths)} CV file(s)/prefix could not be deleted, see audit_log"),
    )
    if failed_paths:
        logger.warning(
            "GDPR erasure PARTIALLY completed for user %s -- %d CV path(s) failed to delete: %s",
            user_id, len(failed_paths), failed_paths,
        )
    else:
        logger.info("GDPR erasure completed for user %s", user_id)

    return {
        "message": "Your account and personal data have been erased."
        if not failed_paths
        else "Your account and personal data have been erased. Some CV file(s) could not be "
             "removed from storage immediately -- this has been logged for manual follow-up.",
    }
