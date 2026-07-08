"""
Talent OS — Auth Router: register, login, JWT refresh, email verification,
password reset, profile read/update. Rate-limited.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from core.database import fetch_one, fetch_all, execute
from core.security import hash_password, verify_password, create_access_token, decode_token
from core.deps import get_current_user, get_optional_user, require_role
from core.config import settings
from models.schemas import (
    UserRegister, UserLogin, TokenResponse, UserResponse, UserUpdate,
    ForgotPasswordRequest, ResetPasswordRequest, VerifyEmailRequest,
)
from services.email_service import email_service
from typing import Optional
from urllib.parse import urlencode, quote
import secrets
from datetime import timedelta
import logging
import httpx
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_auth_requests

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("talent_os.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


# ── Helper ──────────────────────────────────────────────────────────────

async def _get_user_by_email(email: str) -> Optional[dict]:
    """Fetch a user by email (including password_hash for login checks)."""
    return await fetch_one(
        "SELECT * FROM users WHERE email = $1 AND deleted_at IS NULL",
        email.lower().strip(),
    )


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

    verification_token = secrets.token_urlsafe(32)
    password_hash = hash_password(data.password)

    user = await fetch_one(
        """INSERT INTO users
           (email, password_hash, full_name, role, verification_token)
           VALUES ($1, $2, $3, $4, $5)
           RETURNING id, email, full_name, role, is_verified, created_at, updated_at""",
        email, password_hash, data.full_name, data.role, verification_token,
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

    return _build_token_response(user)


# ── Login ───────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, data: UserLogin):
    """Authenticate a user and return a JWT token."""
    email = data.email.lower().strip()
    user = await _get_user_by_email(email)

    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return _build_token_response(user)


# ── Refresh ─────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: dict):
    """Issue a new access token using an existing valid token."""
    token = data.get("refresh_token") or data.get("access_token")
    if not token:
        raise HTTPException(status_code=400, detail="No token provided")

    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("sub")
    user = await fetch_one(
        "SELECT id, email, full_name, role, is_verified FROM users WHERE id = $1 AND deleted_at IS NULL",
        user_id,
    )
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return _build_token_response(user)


# ── Verify Email ────────────────────────────────────────────────────────

@router.post("/verify")
async def verify_email(data: VerifyEmailRequest):
    """Verify a user's email address using their verification token."""
    user = await fetch_one(
        "SELECT id FROM users WHERE verification_token = $1 AND is_verified = FALSE AND deleted_at IS NULL",
        data.token,
    )
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    await execute(
        "UPDATE users SET is_verified = TRUE, verification_token = NULL WHERE id = $1",
        user["id"],
    )
    return {"message": "Email verified successfully"}


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
        logger.warning(f"Failed to send password reset email to {email}")

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
        "UPDATE users SET password_hash = $1, reset_token = NULL, reset_token_expires_at = NULL, updated_at = NOW() WHERE id = $2",
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


# ── Google Sign-In ────────────────────────────────────────────────────────
# Reuses the same Google Cloud OAuth client already configured for sending
# transactional email (GOOGLE_CLIENT_ID/SECRET) -- it just needs this
# callback URL added as an additional authorized redirect URI in Google
# Cloud Console. Uses the standard Authorization Code flow with a
# short-lived signed cookie for CSRF (`state`) protection, since there's no
# server-side session store to keep state in otherwise.

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
    response = RedirectResponse(f"{FRONTEND_URL}/?google_auth={token_response['access_token']}")
    response.delete_cookie("google_oauth_state")
    return response