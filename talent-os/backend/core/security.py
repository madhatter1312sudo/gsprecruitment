"""
Talent OS — API Security: API key authentication + JWT + password hashing.
"""
from fastapi import Header, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from core.config import settings
import hashlib
import hmac
from typing import Optional
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import bcrypt as _bcrypt

# API Key via X-API-Key header
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# JWT Bearer token
bearer_scheme = HTTPBearer(auto_error=False)


# ── API Key Auth (existing) ────────────────────────────────────────────

async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """Dependency that validates the X-API-Key header on all data-access endpoints."""
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    if not hmac.compare_digest(api_key, settings.api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


def verify_webhook_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature for webhook payloads."""
    expected = hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ── Password Hashing (direct bcrypt, no passlib) ───────────────────────

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return _bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ── JWT Tokens ─────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token with expiration.

    python-jose requires 'sub' to be a string, so we convert it if needed.
    """
    to_encode = data.copy()
    if "sub" in to_encode and not isinstance(to_encode["sub"], str):
        to_encode["sub"] = str(to_encode["sub"])
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token. Returns payload dict or None."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        return None