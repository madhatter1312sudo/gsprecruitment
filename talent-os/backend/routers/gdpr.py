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
    # FK first (candidate_profiles.candidate_id, WS-C.16/migrations/023);
    # e-mail match is the fallback for a row the backfill hasn't linked.
    candidate = None
    if profile and profile.get("candidate_id"):
        candidate = await fetch_one(
            "SELECT * FROM candidates WHERE id = $1 AND deleted_at IS NULL", profile["candidate_id"],
        )
    if not candidate:
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


async def _anonymize_by_id(
    select_sql: str, update_sql: str, select_param, email_hash: str,
) -> int:
    """Fetch matching row ids (select_sql, filtered to select_param as $1
    -- normally email_norm, but any value select_sql's $1 expects works,
    e.g. WS-C.16's FK-linked-candidates lookup below passes an id list
    for `id = ANY($1::int[])` -- must return an 'id' column) and UPDATE
    each individually with its own id-suffixed placeholder address
    (update_sql takes id as $1, the placeholder as $2). Per-row
    placeholders -- rather than one shared address for every matched row
    -- avoid a duplicate-key violation on any column that carries a
    uniqueness constraint (candidates.email, users.email) when more than
    one row matches the same original address, and keep every anonymised
    row individually distinguishable even where no such constraint
    exists.

    Retention-kolommen H1/H2/round-6 follow-up: erase_person()'s
    `scope_table`/`scope_id` used to narrow this via an extra `id_filter`
    param appended as `AND id = $2` onto an e-mail-based select_sql --
    dropped (round 6 re-check, security-auditor + code-reviewer): a
    scoped call now passes an id-only select_sql (`WHERE id = $1`,
    select_param=scope_id) directly, with no e-mail condition at all, so
    the subject row is matched regardless of any whitespace/case mismatch
    between the address this call was given and what that row actually
    has on file -- see erase_person()'s own call sites below."""
    rows = await fetch_all(select_sql, select_param)
    for row in rows:
        anon = f"erased-{email_hash[:16]}-{row['id']}@erased.invalid"
        await execute(update_sql, row["id"], anon)
    return len(rows)


async def erase_person(
    email: str,
    actor_id: Optional[int] = None,
    reason: str = "manual",
    *,
    scope_table: Optional[str] = None,
    scope_id: Optional[int] = None,
) -> dict:
    """Art. 17 erasure (WS-E.7). Anonymises/removes PII for `email` across
    every table in the Verwerkingsregister (docs/VERWERKINGSREGISTER.md
    §1.2) and adds its hash to suppression_list so the person is never
    re-sourced -- except when `reason` starts with
    "retention_purge:talentpool_consent" (a lapsed talentpool consent,
    purged via routers/retention_admin.py's review-approve endpoint once
    an admin approves the queued retention_review_items row -- WS-E.10):
    that erasure is not an opt-out, so it must not block the same person
    signing up again via the public talentpool form later (WS-C.17
    security-audit follow-up). Used by DELETE /api/v1/gdpr/account
    (self-service), POST /api/v1/admin/gdpr/erase (admin, for sourced
    persons with no portal account), and the retention review approval.

    Tables touched: candidates (full PII set, including the WS-C.7
    immigratiestatus columns -- nationality, needs_work_permit,
    kennismigrant_status, ruling_30pct_status, ind_case_number), candidate_profiles (phone,
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

    `scope_table`/`scope_id` (retention-kolommen H1/H2 follow-up, round 6
    security-audit/code-review, re-checked again round 6 after an
    address-padding bypass): when given, they name the exact
    retention_review_items subject (subject_table, subject_id) this call
    is erasing on behalf of. The matching *identity* row in that one
    table (candidates/users/client_prospects) is selected BY ID ALONE
    (`WHERE id = $1`, no e-mail condition whatsoever) -- not "the row(s)
    with id = scope_id AND this e-mail address", which is what the first
    round-6 fix did and which silently matched NOTHING (leaving the
    actual subject row completely untouched, while the other two -- still
    e-mail-wide -- tables below anonymised whoever ELSE genuinely had the
    clean address) the moment the subject's own stored address carried
    whitespace that `email` here (re-read fresh off the subject row by
    routers/retention_admin.py's `_approve_one()`, then normalised) no
    longer did. Selecting by id alone makes that mismatch structurally
    irrelevant: this row IS the subject, by definition of scope_id, full
    stop.

    The other two identity tables besides the one scope_table names are,
    for a scoped call, NOT touched at all here -- not e-mail-wide, not in
    any other way. The first round-6 fix left them e-mail-wide on the
    theory that routers/retention_admin.py's `_refuse_if_email_belongs_
    to_an_unrelated_account()` had, by this point, already confirmed no
    OTHER row on either table carries this address, making that guard a
    single point of failure for two live UPDATE statements: exactly the
    address-padding mismatch above defeated it. Skipping those two tables
    outright for a scoped call needs no such guarantee to hold, and also
    closes the small TOCTOU window between that guard's read and this
    call. Side-table cleanup below (outreach, quiz/contact submissions,
    audit_log redaction, suppression_list, ...) is unaffected by any of
    this -- those are traces of communication with an address, not a
    second identity row scope could misattribute erasure to, and stay
    e-mail-wide regardless of scope, same as before.

    The WS-C.16 extra_ids expansion below (a users row's
    candidate_profiles.candidate_id FK, followed regardless of that
    candidate's own e-mail address) is skipped entirely whenever
    scope_table is given, for the same reason -- that FK can point at a
    candidate row with a wholly different address than the one being
    erased, which no amount of e-mail-based conflict-checking would ever
    catch (round 6 code-review finding). Self-service/admin erasure never
    pass these (scope_table=None), preserving today's e-mail-wide
    behaviour, extra_ids included, exactly as before -- except that the
    three identity-table lookups now compare LOWER(TRIM(column)) rather
    than plain LOWER(column), so a padded address on some OTHER row no
    longer hides it from an otherwise-legitimate unscoped erasure either.
    """
    email_norm = privacy.normalize_email(email)
    if not email_norm:
        raise HTTPException(status_code=400, detail="email is required")
    email_hash = privacy.email_hash(email_norm)
    email_domain = privacy.email_domain(email_norm)

    # Round 6 re-check (security-auditor + code-reviewer, adversarial
    # address-padding probes): a scoped call's OWN identity row is now
    # selected by id ALONE -- never by e-mail at all -- so a subject whose
    # stored address carries whitespace the caller already stripped
    # before comparing (a real gap: POST /api/candidates and POST
    # /api/v1/admin/prospects both store `email` unstripped) is still the
    # exact row this call touches, regardless of any mismatch between
    # "the address we were told" and "the address this row actually has
    # on file". The other two identity tables are, for a scoped call, not
    # queried AT ALL here -- not even e-mail-wide -- rather than trusting
    # routers/retention_admin.py's guard as the only thing standing
    # between "no other row has this address" and an e-mail-wide UPDATE;
    # skipping them outright removes both the small TOCTOU window between
    # that guard's read and this call, and this exact normalisation
    # mismatch, as a structural matter rather than a matching detail. Only
    # the unscoped path (scope_table=None -- self-service/admin erasure)
    # still matches e-mail-wide, and now does so via LOWER(TRIM(column))
    # rather than plain LOWER(column), so a stray space on some OTHER
    # row's stored address doesn't hide it from an otherwise-legitimate
    # e-mail-wide erasure either.
    if scope_table == "users":
        users_rows = await fetch_all("SELECT id FROM users WHERE id = $1", scope_id)
    elif scope_table is None:
        users_rows = await fetch_all("SELECT id FROM users WHERE LOWER(TRIM(email)) = $1", email_norm)
    else:
        users_rows = []
    user_ids = [u["id"] for u in users_rows]

    profile_rows = []
    for uid in user_ids:
        p = await fetch_one("SELECT cv_file_path FROM candidate_profiles WHERE user_id = $1", uid)
        if p:
            profile_rows.append(p)
    if scope_table == "candidates":
        candidate_rows = await fetch_all(
            "SELECT id, cv_file_path FROM candidates WHERE id = $1", scope_id,
        )
    elif scope_table is None:
        candidate_rows = await fetch_all(
            "SELECT id, cv_file_path FROM candidates WHERE LOWER(TRIM(email)) = $1", email_norm,
        )
    else:
        candidate_rows = []
    candidate_ids = [c["id"] for c in candidate_rows]

    # WS-C.16 (migrations/023): also pick up any candidates row this
    # person's candidate_profiles.candidate_id points to but whose own
    # email column has since drifted from email_norm (e.g. edited
    # independently, or not yet touched by that backfill) -- an addition
    # to the e-mail-based lookup above, never a replacement for it, so
    # erasure still works purely on e-mail across both records even if
    # the FK is unset or points somewhere the email match wouldn't reach.
    #
    # round 6 (code-review, WS-E.10 approval queue): skipped entirely
    # when `scope_table` is given. A scoped call names ONE identity row
    # as its subject; this FK follows to whatever candidate a matching
    # users row happens to be linked to today, regardless of that
    # candidate's own e-mail address or of scope -- proven reachable via
    # routers/retention_admin.py's approval path (a users row sharing
    # the subject's address but linked to a wholly different,
    # different-e-mail candidate got swept in, unscoped, even though
    # _refuse_if_email_belongs_to_an_unrelated_account had already run).
    # Self-service/admin erasure (scope_table=None) is a real person
    # asking to be forgotten everywhere they can be found, so this stays
    # exactly as e-mail-wide as before for that case.
    extra_ids = []
    if user_ids and scope_table is None:
        linked_rows = await fetch_all(
            "SELECT candidate_id FROM candidate_profiles WHERE user_id = ANY($1::int[]) AND candidate_id IS NOT NULL",
            user_ids,
        )
        extra_ids = [r["candidate_id"] for r in linked_rows if r["candidate_id"] not in candidate_ids]
        if extra_ids:
            extra_candidates = await fetch_all(
                "SELECT id, cv_file_path FROM candidates WHERE id = ANY($1::int[])", extra_ids,
            )
            candidate_rows = list(candidate_rows) + list(extra_candidates)
            candidate_ids = candidate_ids + [c["id"] for c in extra_candidates]

    deleted_paths, failed_paths = await _delete_cv_files(user_ids, profile_rows + list(candidate_rows))

    # candidates and users both carry a unique constraint on email
    # (uq_candidates_email, users.email UNIQUE) — per-row placeholders via
    # _anonymize_by_id avoid a duplicate-key violation if more than one
    # row happens to match.
    # WS-C.7 (migrations/029_placements.py): nationality/needs_work_permit/
    # kennismigrant_status/ruling_30pct_status/ind_case_number fall under
    # the same 7-year "geplaatste kandidaat" retention floor as the rest of
    # a placed candidate's PII (core/retention.py) -- they exist only to
    # support a placement, so they're nulled here alongside every other
    # candidates.* PII column, not retained separately.
    _CANDIDATES_ANONYMIZE_UPDATE_SQL = """UPDATE candidates SET
             full_name = 'Erased', email = $2, phone = NULL, linkedin_url = NULL,
             github_url = NULL, portfolio_url = NULL, cv_text = NULL, cv_file_path = NULL,
             education = NULL, nationality = NULL, needs_work_permit = NULL,
             kennismigrant_status = NULL, ruling_30pct_status = NULL, ind_case_number = NULL,
             deleted_at = NOW(), consent_withdrawn_at = COALESCE(consent_withdrawn_at, NOW())
           WHERE id = $1"""
    # Round 6 re-check: id-only when this call is scoped to candidates,
    # e-mail-wide (TRIM'd) only when unscoped, untouched entirely when
    # scoped to a DIFFERENT identity table -- see the matching comment
    # above candidate_rows/user_ids for why.
    if scope_table == "candidates":
        await _anonymize_by_id(
            "SELECT id FROM candidates WHERE id = $1", _CANDIDATES_ANONYMIZE_UPDATE_SQL, scope_id, email_hash,
        )
    elif scope_table is None:
        await _anonymize_by_id(
            "SELECT id FROM candidates WHERE LOWER(TRIM(email)) = $1", _CANDIDATES_ANONYMIZE_UPDATE_SQL,
            email_norm, email_hash,
        )
    # WS-C.16 extra: anonymise the FK-linked candidates rows the e-mail
    # match above wouldn't have reached (see extra_ids above) -- reuses
    # _anonymize_by_id with an id list instead of an e-mail as the $1
    # filter, same per-row placeholder reasoning.
    if extra_ids:
        await _anonymize_by_id(
            "SELECT id FROM candidates WHERE id = ANY($1::int[])",
            """UPDATE candidates SET
                 full_name = 'Erased', email = $2, phone = NULL, linkedin_url = NULL,
                 github_url = NULL, portfolio_url = NULL, cv_text = NULL, cv_file_path = NULL,
                 education = NULL, nationality = NULL, needs_work_permit = NULL,
                 kennismigrant_status = NULL, ruling_30pct_status = NULL, ind_case_number = NULL,
                 deleted_at = NOW(), consent_withdrawn_at = COALESCE(consent_withdrawn_at, NOW())
               WHERE id = $1""",
            extra_ids, email_hash,
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
    _USERS_ANONYMIZE_UPDATE_SQL = "UPDATE users SET full_name = 'Erased', email = $2, deleted_at = NOW() WHERE id = $1"
    if scope_table == "users":
        await _anonymize_by_id("SELECT id FROM users WHERE id = $1", _USERS_ANONYMIZE_UPDATE_SQL, scope_id, email_hash)
    elif scope_table is None:
        await _anonymize_by_id(
            "SELECT id FROM users WHERE LOWER(TRIM(email)) = $1", _USERS_ANONYMIZE_UPDATE_SQL, email_norm, email_hash,
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
    _CLIENT_PROSPECTS_ANONYMIZE_UPDATE_SQL = (
        "UPDATE client_prospects SET contact_name = 'Erased', contact_email = $2, contact_linkedin = NULL, "
        "opt_out_at = COALESCE(opt_out_at, NOW()) WHERE id = $1"
    )
    if scope_table == "client_prospects":
        await _anonymize_by_id(
            "SELECT id FROM client_prospects WHERE id = $1",
            _CLIENT_PROSPECTS_ANONYMIZE_UPDATE_SQL, scope_id, email_hash,
        )
    elif scope_table is None:
        await _anonymize_by_id(
            "SELECT id FROM client_prospects WHERE LOWER(TRIM(contact_email)) = $1",
            _CLIENT_PROSPECTS_ANONYMIZE_UPDATE_SQL, email_norm, email_hash,
        )
    await _anonymize_by_id(
        "SELECT id FROM data_subject_requests WHERE LOWER(request_email) = $1",
        "UPDATE data_subject_requests SET request_email = $2 WHERE id = $1",
        email_norm, email_hash,
    )
    audit_redacted = await _redact_audit_log_email(email_norm, email_hash)

    # H3 (retention-kolommen, security-audit round 5): retention_review_items
    # carries a plaintext e-mail column of its own (migrations/
    # 036_retention_review_queue.py) -- an erasure (this call, from any of
    # the three callers) must scrub that too, including when it is
    # triggered by the person's OWN Art. 17 request via the self-service
    # portal, not only when the retention flow purges the row that
    # prompted it (routers/retention_admin.py's `_approve_one()` already
    # nulls the row it just acted on directly; this catches every OTHER
    # row -- a different category, or a stale one never approved -- that
    # still carries the same address).
    await execute(
        "UPDATE retention_review_items SET email = NULL WHERE LOWER(email) = $1", email_norm,
    )

    # WS-C.17 security-audit follow-up (LOW, post-APPROVED): a lapsed
    # talentpool consent is erased the same way as any other retention
    # purge (since WS-E.10, only via routers/retention_admin.py's
    # review-approve endpoint, once an admin approves the queued row),
    # but it is
    # NOT the same thing as an opt-out/STOP or an admin/self-service
    # erasure -- the person didn't ask to never be contacted again, their
    # 12-month consent just ran out after the renewal reminder went
    # unanswered. Adding them to suppression_list would silently block
    # the exact re-signup this flow's own reminder e-mail invites, so
    # this one reason is the sole exception to "every erasure adds a
    # suppression entry".
    if not reason.startswith("retention_purge:talentpool_consent"):
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
