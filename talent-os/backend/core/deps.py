"""
Talent OS — FastAPI Dependencies: get_current_user for auth-protected endpoints.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from core.security import bearer_scheme, decode_token
from core.database import fetch_one
from typing import Optional


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
        "SELECT id, email, full_name, role, is_verified, created_at, updated_at "
        "FROM users WHERE id = $1 AND deleted_at IS NULL",
        user_id,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    return user


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
        "SELECT id, email, full_name, role, is_verified, created_at, updated_at "
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
