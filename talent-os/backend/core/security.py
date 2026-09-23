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


def hash_token(token: str) -> str:
    """sha256 hex digest of a random one-time token (e-mail verification /
    set-password links, WS-E.2 + WS-E.3). Only this hash is ever written
    to the database (users.verification_token_hash) -- the raw token
    exists only in the outbound e-mail and the URL the recipient clicks,
    same principle as password hashing above, just a fast digest since
    this is a high-entropy random value, not a low-entropy user secret.

    `errors="ignore"` is not cosmetic. Every token this function ever
    hashes is a `secrets.token_urlsafe()` value, so pure ASCII -- but the
    string reaching it can come straight out of a public JSON body
    (routers/public.py's unsubscribe endpoint), and a JSON body may carry
    a lone surrogate (\\udcff), which a plain .encode("utf-8") raises
    UnicodeEncodeError on. In that endpoint the whole point is that every
    caller gets the same generic 200: a 500 on one specific body shape is
    the single answer that differs, and therefore an oracle. Dropping the
    unencodable code points cannot change the digest of any string that
    could be encoded before, so no existing token hashes differently; it
    only turns "crash" into "hash of something that will simply not
    match"."""
    return hashlib.sha256(token.encode("utf-8", "ignore")).hexdigest()


def verify_webhook_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature for webhook payloads."""
    expected = hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ── Password Hashing (direct bcrypt, no passlib) ───────────────────────

# bcrypt only ever looks at the first 72 bytes of the input. Under the
# pinned bcrypt 4 anything past that was silently truncated; bcrypt 5
# raises a bare ValueError from hashpw()/checkpw() instead (issue #177,
# PR #87). models/schemas.py already rejects a >72-byte password at the
# API boundary with a 422, so in the normal request path neither function
# below should ever see one -- this is the second gate for any caller
# that builds a UserRegister/ChangePasswordRequest/etc. by hand (a script,
# a future router) and skips pydantic validation.
BCRYPT_MAX_PASSWORD_BYTES = 72


class PasswordTooLongError(Exception):
    """Raised by hash_password() when the UTF-8 encoding of the password
    exceeds BCRYPT_MAX_PASSWORD_BYTES -- our own type, not bcrypt's
    ValueError, so a caller can catch it specifically (routers/auth.py
    turns it into a 422) without also swallowing an unrelated ValueError
    bcrypt might raise for some other reason."""


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt.

    Raises PasswordTooLongError instead of letting bcrypt 5's ValueError
    through when the password is more than 72 UTF-8 bytes.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(
            f"password is {len(encoded)} UTF-8 bytes, bcrypt allows at most {BCRYPT_MAX_PASSWORD_BYTES}"
        )
    return _bcrypt.hashpw(encoded, _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    A plaintext password over 72 UTF-8 bytes can never be the one that was
    hashed (hash_password() refuses to hash it), so this returns False
    rather than raising -- login/change-password callers already treat a
    False return as "wrong password" (4xx), and login's password field has
    no schema-level length cap, so this is the only gate on that path.
    """
    encoded = plain_password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        return False
    return _bcrypt.checkpw(
        encoded,
        hashed_password.encode("utf-8"),
    )


# ── JWT Tokens ─────────────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token with expiration.

    python-jose requires 'sub' to be a string, so we convert it if needed.

    WS-E.4: always stamps 'iat' (issued-at) unless the caller already
    supplied one -- core/deps.get_current_user compares this against
    users.password_changed_at to reject a token issued before the
    account's most recent password change/reset/set-password (e.g. a
    token stolen before a reset). A token minted before this change (or
    by any code path that doesn't go through here) carries no 'iat' at
    all; get_current_user treats that as "nothing to compare against" and
    lets it through until its own 'exp' expiry -- it is NOT retroactively
    invalidated by a later password change. That's an accepted gap for
    already-issued tokens, not a bug in new ones.
    """
    to_encode = data.copy()
    if "sub" in to_encode and not isinstance(to_encode["sub"], str):
        to_encode["sub"] = str(to_encode["sub"])
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.setdefault("iat", now)
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