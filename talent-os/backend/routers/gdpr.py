"""
Talent OS — GDPR/AVG endpoints.
Art. 15/20 (access/portability), Art. 17 (erasure), Art. 7(3) (consent
withdrawal). WS-E.7 adds erase_person() as the single erasure routine used
both by the self-service portal (JWT) and the admin endpoint (Bearer
admin) for sourced persons who have no portal account at all, plus the
suppression list (docs/SOURCING-SOP.md §3.3).
"""
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr

from core.database import fetch_one, fetch_all, execute
from core.deps import get_current_user, require_role
from core import privacy
from services import storage

logger = logging.getLogger("talent_os.gdpr")

router = APIRouter(prefix="/api/v1/gdpr", tags=["gdpr"])
admin_router = APIRouter(prefix="/api/v1/admin/gdpr", tags=["gdpr-admin"])
suppression_router = APIRouter(prefix="/api/v1/admin/suppression", tags=["suppression"])


async def _log_request(request_type: str, email: str, summary: str) -> None:
    await execute(
        """INSERT INTO data_subject_requests (request_type, request_email, status, completed_at, response_summary)
           VALUES ($1, $2, 'completed', NOW(), $3)""",
        request_type, email, summary,
    )


@router.get("/export")
async def export_my_data(current_user: dict = Depends(get_current_user)):
    """Art. 15/20 — export all personal data we hold on the requesting user.

    Covers the same table set erase_person() erases: users,
    candidate_profiles, candidates, plus everything keyed off the resolved
    candidate id (matches/saved_jobs) and off the account itself
    (outreach addressed to this email, quiz/contact submissions, prior
    data_subject_requests)."""
    email = current_user["email"]
    user_id = current_user["id"]

    user = await fetch_one(
        "SELECT id, email, full_name, role, is_verified, created_at FROM users WHERE id = $1",
        user_id,
    )
    profile = await fetch_one(
        "SELECT * FROM candidate_profiles WHERE user_id = $1", user_id,
    )
    candidate = await fetch_one(
        "SELECT * FROM candidates WHERE LOWER(email) = LOWER($1) AND deleted_at IS NULL", email,
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

    outreach_drafts = await fetch_all(
        "SELECT subject, body, channel, status, created_at, sent_at FROM outreach_drafts WHERE LOWER(target_email) = LOWER($1)",
        email,
    )
    outreach_messages = await fetch_all(
        "SELECT subject, body, channel, status, created_at FROM outreach_messages WHERE LOWER(recipient_email) = LOWER($1)",
        email,
    )
    quiz = await fetch_all(
        "SELECT score, max_score, tier, domain_scores, created_at FROM quiz_submissions WHERE LOWER(email) = LOWER($1)",
        email,
    )
    contact = await fetch_all(
        "SELECT company, phone, message, interest_type, created_at FROM contact_submissions WHERE LOWER(email) = LOWER($1)",
        email,
    )
    push_tokens = await fetch_all(
        "SELECT platform, created_at FROM push_tokens WHERE user_id = $1", user_id,
    )
    prospect_contacts = await fetch_all(
        "SELECT company_name, contact_name, contact_title, location, industry, status, created_at "
        "FROM client_prospects WHERE LOWER(contact_email) = LOWER($1)",
        email,
    )
    prior_requests = await fetch_all(
        "SELECT request_type, status, created_at, completed_at, response_summary FROM data_subject_requests "
        "WHERE LOWER(request_email) = LOWER($1) ORDER BY created_at DESC",
        email,
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
        "outreach_drafts_received": [_clean(r) for r in outreach_drafts],
        "outreach_messages_received": [_clean(r) for r in outreach_messages],
        "quiz_submissions": [_clean(r) for r in quiz],
        "contact_submissions": [_clean(r) for r in contact],
        "push_tokens": [_clean(r) for r in push_tokens],
        "client_prospect_contacts": [_clean(r) for r in prospect_contacts],
        "prior_data_subject_requests": [_clean(r) for r in prior_requests],
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


# ── Erasure (Art. 17) — shared by self-service and the admin endpoint ────

async def _delete_cv_files(user_ids: list, cv_rows: list) -> tuple:
    """Delete CV files (R2 + legacy local disk) referenced by cv_rows
    (candidate_profiles/candidates rows with a cv_file_path), plus a full
    sweep of every linked user's cv/{user_id}/ R2 prefix (catches orphaned
    re-upload artifacts the DB no longer references — a re-upload before
    the delete-old-key fix could have left earlier objects behind under
    the same prefix). Returns (deleted_paths, failed_paths)."""
    legacy_paths = {
        row["cv_file_path"] for row in cv_rows
        if row and row.get("cv_file_path") and not storage.is_r2_key(row["cv_file_path"])
    }
    referenced_r2_paths = {
        row["cv_file_path"] for row in cv_rows
        if row and row.get("cv_file_path") and storage.is_r2_key(row["cv_file_path"])
    }

    deleted_paths: list = []
    failed_paths: list = []
    prefixes = [storage.cv_prefix(uid) for uid in user_ids]

    if storage.is_configured():
        for prefix in prefixes:
            try:
                deleted_paths.extend(await storage.delete_prefix(prefix))
            except Exception:
                logger.exception("GDPR erasure: failed to delete R2 prefix %s", prefix)
                failed_paths.append(prefix)

        # A referenced R2 key doesn't necessarily live under a linked user's
        # own cv/{user_id}/ prefix -- e.g. a row migrated by
        # migrate_cv_to_r2.py under cv/orphan-{candidate_id}/ before a
        # users row existed for it. The prefix sweep above can't find
        # those, so delete any such stray keys individually.
        stray_r2_paths = {p for p in referenced_r2_paths if not any(p.startswith(pfx) for pfx in prefixes)}
        for cv_path in stray_r2_paths:
            try:
                await storage.delete_object(cv_path)
                deleted_paths.append(cv_path)
            except Exception:
                logger.exception("GDPR erasure: failed to delete stray R2 object %s", cv_path)
                failed_paths.append(cv_path)
    elif referenced_r2_paths:
        # R2 isn't configured (env vars unset/removed) yet the DB still
        # references R2 keys we have no way to reach right now -- don't let
        # this look like a fully-completed erasure just because the R2
        # branch above was skipped entirely; record it as a failure instead.
        logger.warning(
            "GDPR erasure: R2 not configured but found R2-style cv_file_path values (%s) -- could not delete them",
            sorted(referenced_r2_paths),
        )
        failed_paths.extend(prefixes or ["<no linked user account>"])

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
            # removed -- the DB columns are still nulled either way, but
            # the failure is recorded rather than silently swallowed.
            logger.exception("GDPR erasure: failed to delete legacy CV file %s", cv_path)
            failed_paths.append(cv_path)

    return deleted_paths, failed_paths


def _redact_value(value, needle_lower: str, replacement: str):
    """Recursively walk a JSON-decoded audit_log.changes value, replacing
    any string containing needle_lower (case-insensitive) with replacement.
    Returns (new_value, changed). Operates on already-decoded Python
    objects (dict/list/str/...) -- see _redact_audit_log_email for the
    json.loads() done before calling this on a jsonb column value."""
    if isinstance(value, str):
        if needle_lower in value.lower():
            return replacement, True
        return value, False
    if isinstance(value, dict):
        out, changed = {}, False
        for k, v in value.items():
            nv, c = _redact_value(v, needle_lower, replacement)
            out[k] = nv
            changed = changed or c
        return out, changed
    if isinstance(value, list):
        out, changed = [], False
        for v in value:
            nv, c = _redact_value(v, needle_lower, replacement)
            out.append(nv)
            changed = changed or c
        return out, changed
    return value, False


async def _redact_audit_log_email(email: str, replacement: str) -> int:
    """audit_log.changes carries the real e-mail in a handful of actions
    (outreach_draft_approved/rejected's target_email, prospect_create's
    payload dump, ...) -- WS-E.7 requires those replaced with a hash, not
    left as plaintext after a person is erased. Rewritten via
    json.dumps(), never a raw dict (commit 72b4bcd).

    asyncpg has no jsonb codec registered on this connection, so
    audit_log.changes (a jsonb column) comes back here as a plain JSON
    string, not a dict/list. Decode it first -- otherwise _redact_value
    treats the whole row as one opaque string and, when it matches,
    replaces the entire changes payload with `replacement` instead of
    only the e-mail inside it, wiping out every other key (actor,
    target_type, ...). A row that somehow already comes back decoded
    (e.g. a future jsonb codec, or a dict passed in directly by a test)
    is passed through unchanged."""
    rows = await fetch_all(
        "SELECT id, changes FROM audit_log WHERE changes IS NOT NULL AND changes::text ILIKE $1",
        f"%{email}%",
    )
    redacted = 0
    for row in rows:
        changes = row["changes"]
        if isinstance(changes, str):
            try:
                changes = json.loads(changes)
            except (ValueError, TypeError):
                pass  # not valid JSON -- fall back to plain-string redaction below
        new_changes, changed = _redact_value(changes, email.lower(), replacement)
        if changed:
            await execute(
                "UPDATE audit_log SET changes = $2::jsonb WHERE id = $1",
                row["id"], json.dumps(new_changes),
            )
            redacted += 1
    return redacted


async def _anonymize_by_id(select_sql: str, update_sql: str, email_norm: str, email_hash: str) -> int:
    """Fetch matching row ids (select_sql, filtered to email_norm as $1,
    must return an 'id' column) and UPDATE each individually with its own
    id-suffixed placeholder address (update_sql takes id as $1, the
    placeholder as $2). Per-row placeholders -- rather than one shared
    address for every matched row -- avoid a duplicate-key violation on
    any column that carries a uniqueness constraint (candidates.email,
    users.email) when more than one row matches the same original
    address, and keep every anonymised row individually distinguishable
    even where no such constraint exists."""
    rows = await fetch_all(select_sql, email_norm)
    for row in rows:
        anon = f"erased-{email_hash[:16]}-{row['id']}@erased.invalid"
        await execute(update_sql, row["id"], anon)
    return len(rows)


async def erase_person(email: str, actor_id: Optional[int] = None, reason: str = "manual") -> dict:
    """Art. 17 erasure (WS-E.7). Anonymises/removes PII for `email` across
    every table in the Verwerkingsregister (docs/VERWERKINGSREGISTER.md
    §1.2) and adds its hash to suppression_list so the person is never
    re-sourced. Used by both DELETE /api/v1/gdpr/account (self-service)
    and POST /api/v1/admin/gdpr/erase (admin, for sourced persons with no
    portal account).

    Tables touched: candidates (full PII set), candidate_profiles (phone,
    linkedin_url, github_url, portfolio_url, current_company,
    current_title, location, education, salary fields, cv), users,
    push_tokens, quiz_submissions, contact_submissions, outreach_drafts,
    outreach_messages, client_prospects (as a contact, not just a
    candidate — contact_name/contact_email/contact_linkedin, plus
    opt_out_at), pipeline_entries (notes, keyed off the candidate id, not
    e-mail), audit_log (e-mail fields hashed, not deleted),
    data_subject_requests, suppression_list.

    Deliberately NOT touched: matches/saved_jobs keep their candidate_id
    FK (ids only, no PII of their own once the linked candidates row
    above is anonymised — placement/fiscal records need the id to
    survive); the Apollo bulk pool decision (WS-E.8) is the owner's, out
    of scope here.
    """
    email_norm = privacy.normalize_email(email)
    if not email_norm:
        raise HTTPException(status_code=400, detail="email is required")
    email_hash = privacy.email_hash(email_norm)
    email_domain = privacy.email_domain(email_norm)

    users_rows = await fetch_all("SELECT id FROM users WHERE LOWER(email) = $1", email_norm)
    user_ids = [u["id"] for u in users_rows]

    profile_rows = []
    for uid in user_ids:
        p = await fetch_one("SELECT cv_file_path FROM candidate_profiles WHERE user_id = $1", uid)
        if p:
            profile_rows.append(p)
    candidate_rows = await fetch_all(
        "SELECT id, cv_file_path FROM candidates WHERE LOWER(email) = $1", email_norm,
    )
    candidate_ids = [c["id"] for c in candidate_rows]

    deleted_paths, failed_paths = await _delete_cv_files(user_ids, profile_rows + list(candidate_rows))

    # candidates and users both carry a unique constraint on email
    # (uq_candidates_email, users.email UNIQUE) — per-row placeholders via
    # _anonymize_by_id avoid a duplicate-key violation if more than one
    # row happens to match.
    await _anonymize_by_id(
        "SELECT id FROM candidates WHERE LOWER(email) = $1",
        """UPDATE candidates SET
             full_name = 'Erased', email = $2, phone = NULL, linkedin_url = NULL,
             github_url = NULL, portfolio_url = NULL, cv_text = NULL, cv_file_path = NULL,
             education = NULL, deleted_at = NOW(), consent_withdrawn_at = COALESCE(consent_withdrawn_at, NOW())
           WHERE id = $1""",
        email_norm, email_hash,
    )
    for uid in user_ids:
        await execute(
            """UPDATE candidate_profiles SET
                 phone = NULL, linkedin_url = NULL, github_url = NULL, portfolio_url = NULL,
                 current_company = NULL, current_title = NULL, location = NULL, education = NULL,
                 salary_expectation_min = NULL, salary_expectation_max = NULL, notice_period_days = NULL,
                 cv_text = NULL, cv_file_path = NULL
               WHERE user_id = $1""",
            uid,
        )
        await execute("DELETE FROM push_tokens WHERE user_id = $1", uid)
    await _anonymize_by_id(
        "SELECT id FROM users WHERE LOWER(email) = $1",
        "UPDATE users SET full_name = 'Erased', email = $2, deleted_at = NOW() WHERE id = $1",
        email_norm, email_hash,
    )

    # pipeline_entries.notes is free text a client wrote about a specific
    # candidate (routers/client.py) -- keyed by candidate_id, not e-mail,
    # so it isn't reached by any of the LOWER(email)=... updates above.
    for cid in candidate_ids:
        await execute("UPDATE pipeline_entries SET notes = NULL WHERE candidate_id = $1", cid)

    await _anonymize_by_id(
        "SELECT id FROM quiz_submissions WHERE LOWER(email) = $1",
        "UPDATE quiz_submissions SET email = $2 WHERE id = $1",
        email_norm, email_hash,
    )
    await _anonymize_by_id(
        "SELECT id FROM contact_submissions WHERE LOWER(email) = $1",
        "UPDATE contact_submissions SET name = 'Erased', email = $2, phone = NULL WHERE id = $1",
        email_norm, email_hash,
    )
    await _anonymize_by_id(
        "SELECT id FROM outreach_drafts WHERE LOWER(target_email) = $1",
        "UPDATE outreach_drafts SET target_email = $2, target_name = 'Erased' WHERE id = $1",
        email_norm, email_hash,
    )
    await _anonymize_by_id(
        "SELECT id FROM outreach_messages WHERE LOWER(recipient_email) = $1",
        "UPDATE outreach_messages SET recipient_email = $2 WHERE id = $1",
        email_norm, email_hash,
    )
    # A prospect contact person can share the same address as a candidate
    # (or simply be the subject of their own erasure request) — anonymise
    # the contact identity and set opt_out_at, same as add_suppression().
    await _anonymize_by_id(
        "SELECT id FROM client_prospects WHERE LOWER(contact_email) = $1",
        "UPDATE client_prospects SET contact_name = 'Erased', contact_email = $2, contact_linkedin = NULL, "
        "opt_out_at = COALESCE(opt_out_at, NOW()) WHERE id = $1",
        email_norm, email_hash,
    )
    await _anonymize_by_id(
        "SELECT id FROM data_subject_requests WHERE LOWER(request_email) = $1",
        "UPDATE data_subject_requests SET request_email = $2 WHERE id = $1",
        email_norm, email_hash,
    )
    audit_redacted = await _redact_audit_log_email(email_norm, email_hash)

    await execute(
        """INSERT INTO suppression_list (email_hash, email_domain, reason, created_by)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT (email_hash) DO NOTHING""",
        email_hash, email_domain, "gdpr_erasure", actor_id,
    )

    completion_status = "partial" if failed_paths else "complete"
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) VALUES ($1, $2, $3, $4, $5::jsonb)",
        "gdpr_erasure", actor_id, "person", user_ids[0] if user_ids else None,
        json.dumps({
            "email_hash": email_hash,
            "reason": reason,
            "status": completion_status,
            "cv_files_deleted": deleted_paths,
            "cv_files_failed": failed_paths,
            "audit_log_rows_redacted": audit_redacted,
        }),
    )
    await _log_request(
        "erasure", f"erased-{email_hash[:16]}@erased.invalid",
        f"Erasure ({reason}) -- email_hash={email_hash}"
        + ("" if not failed_paths else f" -- WARNING: {len(failed_paths)} CV file(s)/prefix could not be deleted, see audit_log"),
    )

    if failed_paths:
        logger.warning(
            "GDPR erasure PARTIALLY completed for %s -- %d CV path(s) failed to delete: %s",
            email_hash, len(failed_paths), failed_paths,
        )
    else:
        logger.info("GDPR erasure completed for %s", email_hash)

    return {
        "status": completion_status,
        "email_hash": email_hash,
        "cv_files_deleted": deleted_paths,
        "cv_files_failed": failed_paths,
    }


@router.delete("/account")
async def erase_my_account(current_user: dict = Depends(get_current_user)):
    """Art. 17 — self-service erasure. Soft-deletes the user and candidate
    records and anonymises PII. Placement/financial records are retained
    where legally required (fiscal retention), but no longer linked to
    identifiable data."""
    result = await erase_person(
        current_user["email"], actor_id=current_user["id"], reason="self-service erasure via portal",
    )
    if result["cv_files_failed"]:
        return {
            "message": "Your account and personal data have been erased. Some CV file(s) could not be "
                        "removed from storage immediately -- this has been logged for manual follow-up.",
        }
    return {"message": "Your account and personal data have been erased."}


# ── Admin: erase a sourced person who never had a portal account ─────────

class AdminEraseRequest(BaseModel):
    email: EmailStr
    confirm: bool = False


@admin_router.post("/erase")
async def admin_erase_person(
    payload: AdminEraseRequest,
    current_user: dict = Depends(require_role("admin")),
):
    """Art. 17 for people who were only ever sourced (LinkedIn/GitHub/
    referral/meetup/Apollo), never registered a portal account. Same
    erase_person() routine as self-service erasure.

    Guard: erasing an admin account (any matching users row with
    role='admin'), or the calling admin's own account, through this
    endpoint would delete platform-admin access as a side effect of what
    looks like a routine PII-erasure request. Refuse unless the caller
    explicitly opts in with confirm=true."""
    email_norm = privacy.normalize_email(payload.email)
    matching_users = await fetch_all(
        "SELECT id, role FROM users WHERE LOWER(email) = $1", email_norm,
    )
    is_admin_or_self = any(
        u["role"] == "admin" or u["id"] == current_user["id"] for u in matching_users
    )
    if is_admin_or_self and not payload.confirm:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "erase_admin_or_self_requires_confirm",
                "message": "This e-mail matches an admin account or your own account. "
                            "Resend with confirm: true to proceed.",
            },
        )
    return await erase_person(payload.email, actor_id=current_user["id"], reason="admin request")


# ── Suppression list (SOP §3.3 STOP handling) ─────────────────────────────

class SuppressionCreate(BaseModel):
    email: EmailStr
    reason: str = "STOP"


@suppression_router.post("", status_code=201)
async def add_suppression(
    payload: SuppressionCreate,
    current_user: dict = Depends(require_role("admin")),
):
    """SOP §3.3 — a STOP reply (or equivalent) goes on the suppression
    list within 24h, and every active draft addressed to that person is
    withdrawn immediately (outreach_drafts stays draft-only either way —
    this only ever moves a draft to 'rejected', never sends)."""
    h = privacy.email_hash(payload.email)
    domain = privacy.email_domain(payload.email)
    row = await fetch_one(
        """INSERT INTO suppression_list (email_hash, email_domain, reason, created_by)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT (email_hash) DO UPDATE SET reason = EXCLUDED.reason
           RETURNING id, email_domain, reason, created_at""",
        h, domain, payload.reason, current_user["id"],
    )
    await execute(
        "UPDATE candidates SET consent_withdrawn_at = COALESCE(consent_withdrawn_at, NOW()) WHERE LOWER(email) = LOWER($1)",
        payload.email,
    )
    await execute(
        "UPDATE client_prospects SET opt_out_at = COALESCE(opt_out_at, NOW()) WHERE LOWER(contact_email) = LOWER($1)",
        payload.email,
    )
    await execute(
        "UPDATE outreach_drafts SET status = 'rejected', updated_at = NOW() "
        "WHERE LOWER(target_email) = LOWER($1) AND status = 'draft'",
        payload.email,
    )
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) VALUES ($1, $2, $3, $4, $5::jsonb)",
        "suppression_add", current_user["id"], "suppression_list", row["id"],
        json.dumps({"email_hash": h, "email_domain": domain, "reason": payload.reason}),
    )
    return row


@suppression_router.get("")
async def list_suppression(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_role("admin")),
):
    """Hashes + domains only — never plaintext e-mail addresses."""
    rows = await fetch_all(
        "SELECT id, email_hash, email_domain, reason, created_at FROM suppression_list "
        "ORDER BY created_at DESC LIMIT $1 OFFSET $2",
        limit, offset,
    )
    return {"items": rows}
