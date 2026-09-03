"""
Talent OS — FastAPI Dependencies: get_current_user for auth-protected endpoints.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from core.security import bearer_scheme, decode_token
from core.database import fetch_one
from datetime import datetime, timezone
from typing import Optional


def _token_predates_password_change(payload: dict, user: dict) -> bool:
    """WS-E.4: True if this token's 'iat' is older than the account's
    users.password_changed_at -- i.e. it was issued before the most
    recent password change/reset/set-password and must be rejected (a
    token stolen before a reset must not keep working after it).

    A token with no 'iat' claim at all (issued before this check existed,
    or by any caller that doesn't stamp one) is NOT rejected here -- see
    core/security.create_access_token's docstring: it remains valid until
    its own 'exp' expiry. Same if the account has never had
    password_changed_at set (NULL -- nothing to compare against).

    Security-audit follow-up: JWT 'iat' is whole seconds (the JWT spec's
    NumericDate), but password_changed_at is a Postgres TIMESTAMPTZ with
    microsecond precision -- comparing them raw meant a login in the same
    second as a password change (e.g. set-password immediately followed
    by login) could have its brand-new token rejected because its
    truncated iat looked "older" than the sub-second changed_at. Truncate
    changed_at to whole seconds too before comparing (1-second tolerance,
    matching iat's own resolution) -- a token minted any time in the same
    second as the change is treated as no older than it.
    """
    iat = payload.get("iat")
    changed_at = user.get("password_changed_at")
    if iat is None or changed_at is None:
        return False
    if isinstance(iat, (int, float)):
        iat_dt = datetime.fromtimestamp(iat, tz=timezone.utc)
    else:
        iat_dt = iat
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=timezone.utc)
    changed_at = changed_at.replace(microsecond=0)
    return iat_dt < changed_at


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    """Dependency that extracts and validates the JWT, returning the user dict.

    Requires a Bearer token in the Authorization header.
    Returns the full user row (excluding password_hash).
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated — missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    user = await fetch_one(
        "SELECT id, email, full_name, role, is_verified, email_verified_at, "
        "approved_by_admin_at, password_changed_at, created_at, updated_at "
        "FROM users WHERE id = $1 AND deleted_at IS NULL",
        user_id,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    if _token_predates_password_change(payload, user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalidated by a password change — please sign in again",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_verified_user(current_user: dict = Depends(get_current_user)) -> dict:
    """Like get_current_user, but additionally requires a confirmed e-mail
    (WS-E.2). Use this instead of get_current_user for any candidate- or
    client-portal endpoint that reads/writes personal data or lazily
    creates the linked `candidates`/`clients` row -- an unverified user
    must never reach those, so e.g. routers/candidate.py's
    _get_candidate_id() never runs (and never creates a `candidates` row)
    before the owning account has confirmed its e-mail.

    /api/auth/me and /api/auth/resend-verification intentionally keep
    using get_current_user directly -- an unverified user still needs to
    read their own status and ask for a new verification link.
    """
    if not current_user.get("is_verified"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Please confirm your e-mail address before continuing. "
                "Check your inbox for the verification link, or request a "
                "new one via POST /api/auth/resend-verification."
            ),
        )
    return current_user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[dict]:
    """Like get_current_user but returns None instead of 401 if no token."""
    if not credentials:
        return None

    payload = decode_token(credentials.credentials)
    if payload is None:
        return None

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None
    if user_id is None:
        return None

    return await fetch_one(
        "SELECT id, email, full_name, role, is_verified, email_verified_at, "
        "approved_by_admin_at, created_at, updated_at "
        "FROM users WHERE id = $1 AND deleted_at IS NULL",
        user_id,
    )


def require_role(*allowed_roles: str):
    """Dependency factory: ensure the current user has one of the allowed roles.

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(user: dict = Depends(require_role("admin"))):
            ...

        @router.get("/staff")
        async def staff_endpoint(user: dict = Depends(require_role("admin", "client"))):
            ...
    """
    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user['role']}' not allowed. Requires one of: {', '.join(allowed_roles)}",
            )
        return current_user
    return role_checker


def require_verified_role(*allowed_roles: str):
    """Like require_role, but additionally requires a confirmed e-mail
    (WS-E.2) -- see get_verified_user. Used by the client-portal router
    (routers/client.py) so an unverified client account can never reach
    dashboard/jobs/candidates/pipeline/team endpoints, only /api/auth/me
    and /api/auth/resend-verification."""
    async def role_checker(current_user: dict = Depends(get_verified_user)) -> dict:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user['role']}' not allowed. Requires one of: {', '.join(allowed_roles)}",
            )
        return current_user
    return role_checker
