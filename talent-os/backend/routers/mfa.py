"""
Talent OS — WS-E.12: MFA (TOTP) endpoints for admin accounts.

Deliberately its own router/prefix (/api/auth/mfa) so this stays out of
routers/auth.py, which WS-E.9's lockout/rate-limit work touches
concurrently -- routers/auth.py's login() only calls two small helpers
from core/mfa.py (mfa_required_for_user / issue_mfa_pending_token) via a
few-line hook, everything else MFA-specific lives here.

Auth model for these five endpoints:
  - POST /setup, /enable, /disable, GET /status: require a normal Bearer
    session token for an admin account (Depends(get_current_user), role
    checked manually below) -- NOT core.deps.require_role("admin"),
    because that dependency also enforces MFA_REQUIRED_FOR_ADMIN's
    grace-period gate (core/deps.py _enforce_admin_mfa_requirement). If
    these endpoints went through that gate too, an admin who hasn't set
    up MFA yet could never reach the very endpoint that lets them set it
    up once the grace period lapses -- a self-inflicted lockout the spec
    explicitly rules out ("must not lock out the only admin on deploy").
  - POST /verify, /recovery: take the short-lived mfa_pending token
    issued by routers/auth.py login() instead of a Bearer header -- the
    caller does not have a real session token yet, that's the whole
    point of the challenge/response flow.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import fetch_one, execute
from core.deps import get_current_user
from core.mfa import (
    build_otpauth_svg,
    build_otpauth_uri,
    current_step,
    decode_mfa_pending_token,
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    verify_totp_code,
)
from models.schemas import (
    MfaDisableRequest,
    MfaEnableRequest,
    MfaEnableResponse,
    MfaRecoveryRequest,
    MfaSetupResponse,
    MfaStatusResponse,
    MfaVerifyRequest,
)
from routers.auth import _build_token_response

logger = logging.getLogger("talent_os.mfa")

router = APIRouter(prefix="/api/auth/mfa", tags=["mfa"])


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Same 403 shape as core.deps.require_role, but WITHOUT the
    MFA_REQUIRED_FOR_ADMIN grace-period gate -- see module docstring."""
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user['role']}' not allowed. Requires one of: admin",
        )
    return current_user


async def _audit(action: str, actor_id: int, target_id: int, changes: dict) -> None:
    """Same JSON-serialized audit_log pattern as routers/admin.py -- raw
    dicts have crashed this insert before (commit 72b4bcd), always
    json.dumps() the jsonb column."""
    await execute(
        "INSERT INTO audit_log (action, actor_id, target_type, target_id, changes) VALUES ($1, $2, $3, $4, $5::jsonb)",
        action, actor_id, "user", target_id, json.dumps(changes),
    )


# ── Setup ──────────────────────────────────────────────────────────────

@router.post("/setup", response_model=MfaSetupResponse)
async def mfa_setup(current_user: dict = Depends(_require_admin)):
    """Generate a fresh TOTP secret, store it encrypted (unconfirmed --
    totp_enabled_at stays NULL until POST /enable verifies a code), and
    return the otpauth:// URI plus a scannable QR SVG. Safe to call again
    before /enable: it simply overwrites the pending secret."""
    raw_secret = generate_totp_secret()
    enc_secret = encrypt_secret(raw_secret)  # 503s here if MFA_ENC_KEY is unset

    await execute(
        "UPDATE users SET totp_secret_enc = $1 WHERE id = $2",
        enc_secret, current_user["id"],
    )
    await _audit("mfa_setup_started", current_user["id"], current_user["id"], {})

    otpauth_uri = build_otpauth_uri(raw_secret, current_user["email"])
    return MfaSetupResponse(
        otpauth_uri=otpauth_uri,
        qr_svg=build_otpauth_svg(otpauth_uri),
        secret=raw_secret,
    )


# ── Enable ─────────────────────────────────────────────────────────────

@router.post("/enable", response_model=MfaEnableResponse)
async def mfa_enable(data: MfaEnableRequest, current_user: dict = Depends(_require_admin)):
    """Confirm setup with a first live code. On success, marks MFA
    enabled and returns 10 recovery codes -- shown exactly once here,
    only their hashes are ever stored (see core/mfa.py)."""
    row = await fetch_one(
        "SELECT totp_secret_enc, mfa_last_used_step FROM users WHERE id = $1",
        current_user["id"],
    )
    if not row or not row["totp_secret_enc"]:
        raise HTTPException(status_code=400, detail="Run POST /api/auth/mfa/setup first")

    raw_secret = decrypt_secret(row["totp_secret_enc"])
    step = verify_totp_code(raw_secret, data.code, row["mfa_last_used_step"])
    if step is None:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    recovery_codes = generate_recovery_codes()
    hashes = [hash_recovery_code(c) for c in recovery_codes]

    await execute(
        """UPDATE users
           SET totp_enabled_at = NOW(), mfa_last_used_step = $1,
               mfa_recovery_codes_hash = $2
           WHERE id = $3""",
        step, hashes, current_user["id"],
    )
    await _audit("mfa_enabled", current_user["id"], current_user["id"], {})

    return MfaEnableResponse(
        message="Tweestapsverificatie is ingeschakeld. Bewaar de herstelcodes op een veilige plek.",
        recovery_codes=recovery_codes,
    )


# ── Disable ────────────────────────────────────────────────────────────

@router.post("/disable")
async def mfa_disable(data: MfaDisableRequest, current_user: dict = Depends(_require_admin)):
    """Requires a currently-valid code (not a recovery code) -- disabling
    MFA is itself a sensitive action and must not be reachable purely by
    knowing the session token, e.g. from a stolen/leaked Bearer token."""
    row = await fetch_one(
        "SELECT totp_secret_enc, mfa_last_used_step, totp_enabled_at FROM users WHERE id = $1",
        current_user["id"],
    )
    if not row or not row["totp_enabled_at"] or not row["totp_secret_enc"]:
        raise HTTPException(status_code=400, detail="MFA is not enabled")

    raw_secret = decrypt_secret(row["totp_secret_enc"])
    step = verify_totp_code(raw_secret, data.code, row["mfa_last_used_step"])
    if step is None:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    await execute(
        """UPDATE users
           SET totp_secret_enc = NULL, totp_enabled_at = NULL,
               mfa_recovery_codes_hash = NULL, mfa_last_used_step = NULL
           WHERE id = $1""",
        current_user["id"],
    )
    await _audit("mfa_disabled", current_user["id"], current_user["id"], {})

    return {"message": "Tweestapsverificatie is uitgeschakeld."}


# ── Status ─────────────────────────────────────────────────────────────

@router.get("/status", response_model=MfaStatusResponse)
async def mfa_status(current_user: dict = Depends(get_current_user)):
    """Any authenticated user can read their own MFA status -- the admin
    panel banner ("Zet tweestapsverificatie aan") uses this. Deliberately
    not gated behind _require_admin: a non-admin gets a meaningless-but-
    harmless mfa_enabled=false rather than a 403 that would complicate
    the panel's banner logic for no security benefit (this leaks nothing
    beyond what /api/auth/me already exposes about the caller's own
    account)."""
    row = await fetch_one("SELECT totp_enabled_at FROM users WHERE id = $1", current_user["id"])
    return MfaStatusResponse(mfa_enabled=bool(row and row["totp_enabled_at"]))


# ── Verify (exchange mfa_pending for real tokens) ───────────────────────

@router.post("/verify")
async def mfa_verify(data: MfaVerifyRequest):
    user_id = decode_mfa_pending_token(data.mfa_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired MFA challenge")

    row = await fetch_one(
        "SELECT * FROM users WHERE id = $1 AND deleted_at IS NULL",
        user_id,
    )
    if not row or not row["totp_enabled_at"] or not row["totp_secret_enc"]:
        raise HTTPException(status_code=401, detail="Invalid or expired MFA challenge")

    raw_secret = decrypt_secret(row["totp_secret_enc"])
    step = verify_totp_code(raw_secret, data.code, row["mfa_last_used_step"])
    if step is None:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    await execute("UPDATE users SET mfa_last_used_step = $1 WHERE id = $2", step, user_id)
    await _audit("mfa_login_verified", user_id, user_id, {})

    return _build_token_response(row)


# ── Recovery (single-use recovery code) ─────────────────────────────────

@router.post("/recovery")
async def mfa_recovery(data: MfaRecoveryRequest):
    user_id = decode_mfa_pending_token(data.mfa_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired MFA challenge")

    row = await fetch_one(
        "SELECT * FROM users WHERE id = $1 AND deleted_at IS NULL",
        user_id,
    )
    if not row or not row["totp_enabled_at"]:
        raise HTTPException(status_code=401, detail="Invalid or expired MFA challenge")

    # WS-E.12: NULL array columns must be coerced to [] on read.
    codes = row["mfa_recovery_codes_hash"] or []
    target_hash = hash_recovery_code(data.recovery_code)
    if target_hash not in codes:
        raise HTTPException(status_code=400, detail="Invalid or already-used recovery code")

    remaining = [h for h in codes if h != target_hash]
    await execute(
        "UPDATE users SET mfa_recovery_codes_hash = $1 WHERE id = $2",
        remaining, user_id,
    )
    await _audit("mfa_recovery_code_used", user_id, user_id, {"codes_remaining": len(remaining)})

    return _build_token_response(row)
