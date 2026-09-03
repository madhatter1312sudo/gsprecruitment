"""
Talent OS — Auth Router: register, login, JWT refresh, email verification,
password reset, profile read/update. Rate-limited.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from core.database import fetch_one, fetch_all, execute
from core.security import hash_password, verify_password, create_access_token, decode_token, hash_token
from core.deps import get_current_user, get_optional_user, require_role, _token_predates_password_change
from core.mfa import mfa_required_for_user, issue_mfa_pending_token
from core.config import settings
from models.schemas import (
    UserRegister, UserLogin, TokenResponse, UserResponse, UserUpdate,
    ForgotPasswordRequest, ResetPasswordRequest, VerifyEmailRequest,
    ResendVerificationRequest, SetPasswordRequest, ChangePasswordRequest,
)
from services.email_service import email_service
from services.candidate_link import get_or_create_candidate_id
from typing import Optional
from urllib.parse import urlencode, quote
import secrets
from datetime import datetime, timedelta, timezone
import logging
import httpx
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_auth_requests

from core.ratelimit import limiter

logger = logging.getLogger("talent_os.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Helper ──────────────────────────────────────────────────────────────

async def _get_user_by_email(email: str) -> Optional[dict]:
    """Fetch a user by email (including password_hash for login checks)."""
    return await fetch_one(
        "SELECT * FROM users WHERE email = $1 AND deleted_at IS NULL",
        email.lower().strip(),
    )


# WS-E.2: verification / set-password tokens (secrets.token_urlsafe, only
# their sha256 hash ever stored -- see core.security.hash_token) are valid
# for this long from users.verification_sent_at.
VERIFICATION_TOKEN_TTL_HOURS = 24


async def _issue_verification_token(user_id: int) -> str:
    """Generate a fresh one-time token, store only its hash + issue time,
    and return the raw token for the caller to put in an outbound e-mail.
    Used by register, resend-verification, and (indirectly, via the same
    column) WS-E.3's team-invite set-password flow in routers/client.py."""
    token = secrets.token_urlsafe(32)
    await execute(
        "UPDATE users SET verification_token_hash = $1, verification_sent_at = NOW() WHERE id = $2",
        hash_token(token), user_id,
    )
    return token


async def _send_verification_email(user: dict, token: str) -> None:
    link = f"https://gsprecruitment.nl/verify?token={token}"
    body = f"""Beste {user['full_name']},

Bedankt voor je registratie bij GSP Recruitment. Bevestig je e-mailadres via onderstaande link:
{link}

Deze link is {VERIFICATION_TOKEN_TTL_HOURS} uur geldig.

Heb je dit account niet aangemaakt? Dan kun je dit bericht negeren.

Met vriendelijke groet,
GSP Recruitment
info@gsprecruitment.nl

---

Dear {user['full_name']},

Thank you for registering with GSP Recruitment. Please confirm your e-mail address via the link below:
{link}

This link is valid for {VERIFICATION_TOKEN_TTL_HOURS} hours.

Didn't create this account? You can ignore this message.

Kind regards,
GSP Recruitment
info@gsprecruitment.nl
"""
    sent = await email_service.send_email(
        to_email=user["email"],
        subject="Bevestig je e-mailadres — GSP Recruitment",
        body_text=body,
    )
    if not sent:
        logger.warning(f"Failed to send verification email to {user['email']}")


def _build_token_response(user: dict) -> dict:
    """Build a JWT token response from a user dict."""
    access_token = create_access_token(
        data={"sub": user["id"], "role": user["role"]},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            "is_verified": user["is_verified"],
        },
    }


# ── Register ────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, data: UserRegister):
    """Register a new user account."""
    email = data.email.lower().strip()

    # Check email uniqueness
    existing = await _get_user_by_email(email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    password_hash = hash_password(data.password)

    # WS-E.2: created unverified (is_verified defaults to FALSE on the
    # table); the verification token is issued and hashed via
    # _issue_verification_token right after insert, once we have the id.
    user = await fetch_one(
        """INSERT INTO users
           (email, password_hash, full_name, role)
           VALUES ($1, $2, $3, $4)
           RETURNING id, email, full_name, role, is_verified, created_at, updated_at""",
        email, password_hash, data.full_name, data.role,
    )
    if not user:
        raise HTTPException(status_code=500, detail="Failed to create user")

    # If role is 'candidate', optionally create a candidate_profiles record
    if data.role == "candidate":
        await execute(
            "INSERT INTO candidate_profiles (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
            user["id"],
        )
    elif data.role == "client":
        # Without this, the client portal's _get_client_by_user() lookup
        # never finds a row and every endpoint silently no-ops (blank
        # dashboard, empty everything) -- there was no other code path that
        # ever created this linkage for a client signup.
        client = await fetch_one(
            "INSERT INTO clients (company_name, domain) VALUES ($1, $2) RETURNING id",
            user["full_name"], email.split("@")[1] if "@" in email else "",
        )
        if client:
            await execute(
                "INSERT INTO user_clients (user_id, client_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                user["id"], client["id"],
            )

    verification_token = await _issue_verification_token(user["id"])
    await _send_verification_email(user, verification_token)

    return _build_token_response(user)


# ── Login ───────────────────────────────────────────────────────────────
# WS-E.4: per-account lockout, on top of the per-IP @limiter.limit above.
# The IP limit alone doesn't stop credential stuffing spread across many
# source IPs at a single account; this closes that gap. Columns come from
# migrations/020_login_lockout.py.

FAILED_LOGIN_LOCKOUT_THRESHOLD = 10
FAILED_LOGIN_WINDOW_MINUTES = 15
LOCKOUT_DURATION_MINUTES = 15


async def _register_failed_login(user: dict) -> None:
    """Bump users.failed_login_count for a failed password check, and lock
    the account for LOCKOUT_DURATION_MINUTES once it hits the threshold
    within the FAILED_LOGIN_WINDOW_MINUTES window.

    The sliding window is tracked off its own dedicated
    `last_failed_login_at` column (migrations/020_login_lockout.py), not
    the shared `updated_at` column -- an unrelated write to the same user
    row (a profile edit, an admin PUT /api/v1/admin/users/{id}, an
    approval, ...) must never nudge the lockout window. This UPDATE both
    reads the previous `last_failed_login_at` (to decide reset-vs-
    increment) and immediately overwrites it with NOW() in one statement.
    """
    row = await fetch_one(
        """UPDATE users
           SET failed_login_count = CASE
                   WHEN last_failed_login_at IS NULL
                        OR last_failed_login_at < NOW() - INTERVAL '15 minutes'
                       THEN 1
                       ELSE failed_login_count + 1
               END,
               last_failed_login_at = NOW()
           WHERE id = $1
           RETURNING failed_login_count""",
        user["id"],
    )
    if row and row["failed_login_count"] >= FAILED_LOGIN_LOCKOUT_THRESHOLD:
        await execute(
            "UPDATE users SET locked_until = NOW() + INTERVAL '15 minutes' WHERE id = $1",
            user["id"],
        )


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, data: UserLogin):
    """Authenticate a user and return a JWT token (or, for an admin with
    MFA enabled, an mfa_required challenge -- WS-E.12, see core/mfa.py).

    Locked-out and wrong-password both return the exact same generic 401
    -- a locked account must never be distinguishable from a bad password
    (which itself must never be distinguishable from "no such account",
    see _get_user_by_email's callers) -- the only extra signal is a
    Retry-After header, and only while actually locked.
    """
    email = data.email.lower().strip()
    user = await _get_user_by_email(email)

    if user and user["locked_until"] and user["locked_until"] > datetime.now(timezone.utc):
        retry_after = max(1, int((user["locked_until"] - datetime.now(timezone.utc)).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"Retry-After": str(retry_after)},
        )

    if not user or not verify_password(data.password, user["password_hash"]):
        if user:
            await _register_failed_login(user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user["failed_login_count"] or user["locked_until"]:
        await execute(
            "UPDATE users SET failed_login_count = 0, locked_until = NULL, last_failed_login_at = NULL WHERE id = $1",
            user["id"],
        )

    if mfa_required_for_user(user):
        return {"mfa_required": True, "mfa_token": issue_mfa_pending_token(user["id"])}

    return _build_token_response(user)


# ── Refresh ─────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh_token(request: Request, data: dict):
    """Issue a new access token using an existing valid token.

    Rejects tokens carrying an `impersonator` claim -- an admin
    impersonation token must stay short-lived and never be silently
    extended into a fresh, long-lived session (see routers/admin.py
    impersonate_user).

    Security-audit follow-up on WS-E.4: this endpoint decodes the token
    itself (get_current_user is not in its dependency chain), so it must
    run the same iat-vs-password_changed_at check get_current_user does
    -- otherwise a token stolen before a password reset could be
    "laundered" into a fresh one here even though it would be rejected
    everywhere else.
    """
    token = data.get("refresh_token") or data.get("access_token")
    if not token:
        raise HTTPException(status_code=400, detail="No token provided")

    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if payload.get("impersonator"):
        raise HTTPException(status_code=401, detail="Impersonation tokens cannot be refreshed")

    # WS-E.12: an mfa_pending challenge token must never be refreshable
    # into a real session token -- it has to go through
    # POST /api/auth/mfa/verify or /recovery like core/deps.py's
    # get_current_user already enforces for every other route.
    if payload.get("scope") == "mfa_pending":
        raise HTTPException(status_code=401, detail="MFA verification required before this token can be used")

    # python-jose forces 'sub' to a string on encode (see
    # create_access_token); the users.id column is an integer, so this must
    # be cast back before querying or asyncpg raises (was a bare 500).
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await fetch_one(
        "SELECT id, email, full_name, role, is_verified, password_changed_at "
        "FROM users WHERE id = $1 AND deleted_at IS NULL",
        user_id,
    )
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if _token_predates_password_change(payload, user):
        raise HTTPException(
            status_code=401,
            detail="Token invalidated by a password change — please sign in again",
        )

    return _build_token_response(user)


# ── Verify Email (legacy) ──────────────────────────────────────────────
# Pre-WS-E.2 flow: a plaintext token in the users.verification_token
# column. WS-E.2's register() no longer writes that column (only the
# hashed users.verification_token_hash below), so this route is dead in
# practice going forward -- kept, unmodified, only so an already-issued
# pre-WS-E.2 link (if any is still outstanding) keeps working rather than
# being pulled out from under someone mid-flight. New code should use
# POST /api/auth/verify-email instead.

@router.post("/verify")
async def verify_email(data: VerifyEmailRequest):
    """Verify a user's email address using their (legacy, plaintext) verification token."""
    user = await fetch_one(
        "SELECT id FROM users WHERE verification_token = $1 AND is_verified = FALSE AND deleted_at IS NULL",
        data.token,
    )
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    await execute(
        "UPDATE users SET is_verified = TRUE, email_verified_at = NOW(), verification_token = NULL WHERE id = $1",
        user["id"],
    )
    return {"message": "Email verified successfully"}


# ── Verify Email (WS-E.2) ───────────────────────────────────────────────
# Hashed-token flow: register()/resend-verification() only ever store
# sha256(token) in verification_token_hash, so this looks up by that hash
# and additionally enforces the 24h TTL from verification_sent_at.

@router.post("/verify-email")
@limiter.limit("20/minute")
async def verify_email_hashed(request: Request, data: VerifyEmailRequest):
    """Verify a user's email address using their WS-E.2 (hashed) verification token."""
    user = await fetch_one(
        """SELECT id, role FROM users
           WHERE verification_token_hash = $1
             AND verification_sent_at > NOW() - INTERVAL '24 hours'
             AND deleted_at IS NULL""",
        hash_token(data.token),
    )
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    await execute(
        """UPDATE users
           SET is_verified = TRUE, email_verified_at = NOW(),
               verification_token_hash = NULL, verification_sent_at = NULL
           WHERE id = $1""",
        user["id"],
    )
    if user["role"] == "candidate":
        # WS-C.16: the candidates row (or its link, if one already exists
        # under this e-mail) is created here, once, right after
        # verification -- not before (WS-E.2: an unverified account must
        # never get a candidates row) and not left purely to the lazy
        # per-request path in routers/candidate.py, so a freshly-verified
        # candidate's matches/applications/saved-jobs work on their very
        # first request too.
        await get_or_create_candidate_id(user["id"])
    return {"message": "Email verified successfully"}


# ── Resend Verification (WS-E.2) ────────────────────────────────────────

@router.post("/resend-verification")
@limiter.limit("3/hour")
async def resend_verification(request: Request, data: ResendVerificationRequest):
    """Re-issue a verification token and e-mail it.

    Always returns 200 with the same generic message regardless of
    whether the e-mail exists or is already verified -- same
    no-enumeration pattern as forgot_password() below.
    """
    email = data.email.lower().strip()
    user = await fetch_one(
        "SELECT id, email, full_name, is_verified FROM users WHERE email = $1 AND deleted_at IS NULL",
        email,
    )
    if user and not user["is_verified"]:
        token = await _issue_verification_token(user["id"])
        await _send_verification_email(user, token)

    return {"message": "If that email exists and is not yet verified, a new verification link has been sent"}


# ── Set Password (WS-E.3 team invite) ───────────────────────────────────

@router.post("/set-password")
@limiter.limit("10/minute")
async def set_password(request: Request, data: SetPasswordRequest):
    """Consume a one-time set-password token (team invite, WS-E.3): sets
    the invitee's own password and marks the e-mail verified in the same
    step -- the invite never contained a password, only this link."""
    user = await fetch_one(
        """SELECT id FROM users
           WHERE verification_token_hash = $1
             AND verification_sent_at > NOW() - INTERVAL '24 hours'
             AND deleted_at IS NULL""",
        hash_token(data.token),
    )
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired set-password link")

    new_hash = hash_password(data.new_password)
    await execute(
        """UPDATE users
           SET password_hash = $1, is_verified = TRUE, email_verified_at = NOW(),
               verification_token_hash = NULL, verification_sent_at = NULL,
               password_changed_at = NOW(), failed_login_count = 0, locked_until = NULL,
               last_failed_login_at = NULL, updated_at = NOW()
           WHERE id = $2""",
        new_hash, user["id"],
    )
    return {"message": "Password set successfully. You can now sign in."}


# ── Forgot Password ─────────────────────────────────────────────────────

@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest):
    """Generate a password reset token and return it (placeholder for email sending)."""
    email = data.email.lower().strip()
    user = await _get_user_by_email(email)
    if not user:
        # Don't reveal whether the email exists
        return {"message": "If that email exists, a reset link has been sent"}

    reset_token = secrets.token_urlsafe(32)
    await execute(
        "UPDATE users SET reset_token = $1, reset_token_expires_at = NOW() + INTERVAL '1 hour' WHERE id = $2",
        reset_token, user["id"],
    )

    # Send reset email via Gmail API
    email_sent = await email_service.send_email(
        to_email=email,
        subject="Wachtwoord resetten - GSP Recruitment",
        body_text=f"""Beste {user['full_name']},

Je hebt een wachtwoord reset aangevraagd voor je GSP Recruitment account.

Klik op de volgende link om je wachtwoord te resetten:
https://gsprecruitment.nl/reset-password?token={reset_token}

Deze link is 1 uur geldig.

Als je geen wachtwoord reset hebt aangevraagd, kun je dit bericht negeren.

Met vriendelijke groet,
GSP Recruitment
info@gsprecruitment.nl
""",
    )
    if not email_sent:
        logger.warning(f"Failed to send password reset email for user_id={user['id']}")

    return {"message": "If that email exists, a reset link has been sent"}


# ── Reset Password ──────────────────────────────────────────────────────

@router.post("/reset-password")
@limiter.limit("3/minute")
async def reset_password(request: Request, data: ResetPasswordRequest):
    """Reset a user's password using a valid, unexpired reset token."""
    user = await fetch_one(
        "SELECT id FROM users WHERE reset_token = $1 AND reset_token_expires_at > NOW() AND deleted_at IS NULL",
        data.token,
    )
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    new_hash = hash_password(data.new_password)
    await execute(
        """UPDATE users
           SET password_hash = $1, reset_token = NULL, reset_token_expires_at = NULL,
               password_changed_at = NOW(), failed_login_count = 0, locked_until = NULL,
               last_failed_login_at = NULL, updated_at = NOW()
           WHERE id = $2""",
        new_hash, user["id"],
    )
    return {"message": "Password reset successfully"}


# ── Get Current User ────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return current_user


# ── Update Current User ─────────────────────────────────────────────────

@router.patch("/me", response_model=UserResponse)
async def update_me(
    updates: UserUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update the authenticated user's profile."""
    set_parts = []
    values = []
    idx = 1

    if updates.full_name is not None:
        set_parts.append(f"full_name = ${idx}")
        values.append(updates.full_name)
        idx += 1
    if updates.email is not None:
        # Check email uniqueness
        email = updates.email.lower().strip()
        existing = await fetch_one(
            "SELECT id FROM users WHERE email = $1 AND id != $2 AND deleted_at IS NULL",
            email, current_user["id"],
        )
        if existing:
            raise HTTPException(status_code=409, detail="Email already in use")
        set_parts.append(f"email = ${idx}")
        values.append(email)
        idx += 1

    if not set_parts:
        return current_user

    values.append(current_user["id"])
    updated = await fetch_one(
        f"UPDATE users SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = ${idx} "
        f"RETURNING id, email, full_name, role, is_verified, created_at, updated_at",
        *values,
    )
    return updated


# ── Change Password ─────────────────────────────────────────────────────

@router.post("/change-password")
@limiter.limit("10/minute")
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
):
    """Change the authenticated user's password (requires current password)."""
    user = await fetch_one(
        "SELECT id, password_hash FROM users WHERE id = $1 AND deleted_at IS NULL",
        current_user["id"],
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(data.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    new_hash = hash_password(data.new_password)
    await execute(
        """UPDATE users
           SET password_hash = $1, password_changed_at = NOW(),
               failed_login_count = 0, locked_until = NULL, last_failed_login_at = NULL,
               updated_at = NOW()
           WHERE id = $2""",
        new_hash, current_user["id"],
    )
    return {"message": "Password changed successfully"}


# ── Google Sign-In ────────────────────────────────────────────────────────
# Reuses the same Google Cloud OAuth client already configured for sending
# transactional email (GOOGLE_CLIENT_ID/SECRET) -- it just needs this
# callback URL added as an additional authorized redirect URI in Google
# Cloud Console. Uses the standard Authorization Code flow with a
# short-lived signed cookie for CSRF (`state`) protection, since there's no
# server-side session store to keep state in otherwise.
#
# WS-E.3 finding: the successful branch used to redirect with the freshly
# issued JWT as a `?google_auth=<jwt>` QUERY-STRING parameter. A query
# string is sent to the server in the request line (nginx/access logs,
# any CDN/WAF logging, browser history) and in the Referer header of the
# very next request the page makes -- so that access token was leaking to
# every one of those. Error codes (`?google_auth_error=...`) are not
# secret and stay in the query string unchanged. The token itself now
# goes in the URL FRAGMENT (`#google_auth=<jwt>`) instead: fragments are
# never sent to the server by the browser (not in the request line, not
# in Referer), so this closes that leak with no extra round trip. An
# alternative (a one-time code exchanged via POST) would remove the token
# from the URL bar entirely too, but needs a new short-lived code table +
# exchange endpoint; the fragment fix is the minimal change that actually
# stops the leak website/script.js's own comment on this flow already
# flagged. website/script.js's handleGoogleAuthCallback() reads
# window.location.hash instead of .search for this one param accordingly.

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REDIRECT_URI = "https://api.gsprecruitment.nl/api/auth/google/callback"
FRONTEND_URL = "https://gsprecruitment.nl"


@router.get("/google/login")
@limiter.limit("10/minute")
async def google_login(request: Request):
    """Redirect the browser to Google's OAuth consent screen."""
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")

    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    }
    response = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")
    response.set_cookie(
        "google_oauth_state", state,
        max_age=600, httponly=True, secure=True, samesite="lax",
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Handle Google's redirect back: exchange code, find-or-create user, issue our JWT."""
    if error:
        return RedirectResponse(f"{FRONTEND_URL}/?google_auth_error={quote(error)}")

    cookie_state = request.cookies.get("google_oauth_state")
    if not state or not cookie_state or state != cookie_state:
        return RedirectResponse(f"{FRONTEND_URL}/?google_auth_error=invalid_state")

    if not code:
        return RedirectResponse(f"{FRONTEND_URL}/?google_auth_error=missing_code")

    try:
        async with httpx.AsyncClient() as client:
            token_res = await client.post(GOOGLE_TOKEN_URL, data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            })
        if token_res.status_code != 200:
            logger.warning(f"Google token exchange failed: {token_res.text}")
            return RedirectResponse(f"{FRONTEND_URL}/?google_auth_error=token_exchange_failed")

        id_token_str = token_res.json().get("id_token")
        if not id_token_str:
            return RedirectResponse(f"{FRONTEND_URL}/?google_auth_error=no_id_token")

        idinfo = google_id_token.verify_oauth2_token(
            id_token_str, google_auth_requests.Request(), settings.google_client_id,
        )
    except Exception as e:
        logger.warning(f"Google sign-in failed: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/?google_auth_error=verification_failed")

    if not idinfo.get("email_verified"):
        return RedirectResponse(f"{FRONTEND_URL}/?google_auth_error=email_not_verified")

    email = idinfo["email"].lower().strip()
    full_name = idinfo.get("name") or email.split("@")[0]

    user = await fetch_one(
        "SELECT id, email, full_name, role, is_verified FROM users WHERE email = $1 AND deleted_at IS NULL",
        email,
    )
    if not user:
        # New account via Google -- default role candidate (matches public
        # self-registration's default), pre-verified since Google already
        # confirmed the email, unusable random password (Google-only login).
        random_password_hash = hash_password(secrets.token_urlsafe(32))
        user = await fetch_one(
            """INSERT INTO users (email, password_hash, full_name, role, is_verified)
               VALUES ($1, $2, $3, 'candidate', TRUE)
               RETURNING id, email, full_name, role, is_verified""",
            email, random_password_hash, full_name,
        )
        await execute(
            "INSERT INTO candidate_profiles (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
            user["id"],
        )

    token_response = _build_token_response(user)
    # Fragment, not query string -- see the module-level comment above.
    response = RedirectResponse(f"{FRONTEND_URL}/#google_auth={token_response['access_token']}")
    response.delete_cookie("google_oauth_state")
    return response