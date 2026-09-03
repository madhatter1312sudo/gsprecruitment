"""
Talent OS — WS-E.12: MFA (TOTP) core logic.

Everything MFA-specific lives here and in routers/mfa.py, deliberately
kept out of core/security.py, core/deps.py's login-adjacent helpers, and
routers/auth.py -- WS-E.9's lockout/rate-limit work touches routers/auth.py
concurrently, so this module only exposes a couple of small helpers for
routers/auth.py's login() to call (see mfa_required_for_user /
issue_mfa_pending_token below) rather than importing anything from there.

Secret-at-rest: the TOTP shared secret is Fernet-encrypted with
MFA_ENC_KEY (a 32-byte urlsafe-base64 key) before it's written to
users.totp_secret_enc -- never the raw base32 secret. If MFA_ENC_KEY is
unset the app still boots (Settings has no validator for it, unlike
jwt_secret/api_key/webhook_secret/postgres_password), but any endpoint
that would encrypt or decrypt a secret raises a 503 with a clear detail
instead of silently no-op'ing or crashing with a KeyError deep in
cryptography.fernet.

Recovery codes: 10 codes of 10 [A-Z2-9] chars (Crockford-ish alphabet,
excludes 0/O/1/I to avoid transcription mistakes), generated once at
enable time, returned raw exactly once in the enable response body, and
only their sha256 hex digests ever stored (users.mfa_recovery_codes_hash
text[]) -- same "never store the raw thing" principle as
core/security.hash_token. Consuming one removes its hash from the array,
so a used code can never be replayed.

Replay protection: users.mfa_last_used_step holds the TOTP time-step
(unix time // 30) of the last code that verified successfully. A
would-be-valid code whose step is <= that value is rejected even though
pyotp would otherwise accept it (its 30s window may still be open) --
this is what stops a captured code from being replayed a second time
within its own validity window.
"""
import hashlib
import secrets
import string
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from jose import JWTError, jwt

from core.config import settings
from core.database import execute

MFA_ISSUER = "GSP Recruitment"
MFA_PENDING_SCOPE = "mfa_pending"
MFA_PENDING_TTL_MINUTES = 5
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 10
# Excludes 0/O/1/I -- see module docstring.
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


# ── Fernet (secret-at-rest encryption) ──────────────────────────────────

def get_fernet() -> Fernet:
    """Return a Fernet instance from MFA_ENC_KEY, or raise a 503 if it's
    unset/malformed. Called lazily (never at import time / app startup)
    so a deploy with no MFA_ENC_KEY set still boots -- only an actual
    attempt to set up or verify MFA needs this."""
    if not settings.mfa_enc_key:
        raise HTTPException(
            status_code=503,
            detail="MFA is not configured on this server (MFA_ENC_KEY is unset). "
                   "Ask an operator to set it before enabling two-factor authentication.",
        )
    try:
        return Fernet(settings.mfa_enc_key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=503,
            detail="MFA is misconfigured on this server (MFA_ENC_KEY is not a valid Fernet key).",
        ) from exc


def encrypt_secret(raw_secret: str) -> str:
    return get_fernet().encrypt(raw_secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(enc_secret: str) -> str:
    try:
        return get_fernet().decrypt(enc_secret.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        # MFA_ENC_KEY rotated or the ciphertext is corrupt -- never treat
        # this as "no MFA secret", always fail closed and loud.
        raise HTTPException(
            status_code=503,
            detail="Could not decrypt the stored MFA secret. Contact an operator.",
        ) from exc


# ── TOTP ─────────────────────────────────────────────────────────────────

def generate_totp_secret() -> str:
    """A fresh random base32 TOTP secret (pyotp default: 160 bits)."""
    return pyotp.random_base32()


def build_otpauth_uri(raw_secret: str, email: str) -> str:
    totp = pyotp.TOTP(raw_secret)
    return totp.provisioning_uri(name=email, issuer_name=MFA_ISSUER)


def current_step() -> int:
    return int(datetime.now(timezone.utc).timestamp()) // 30


def verify_totp_code(raw_secret: str, code: str, last_used_step: Optional[int]) -> Optional[int]:
    """Verify a 6-digit TOTP code against raw_secret, honoring one step of
    clock drift either side (pyotp valid_window=1). Returns the time-step
    the code was valid for on success (so the caller can persist it to
    mfa_last_used_step), or None if the code is wrong/expired/replayed.

    Replay: if verification succeeds but the resolved step is <=
    last_used_step, this returns None -- the code is cryptographically
    correct but was already used (or is older than the last accepted
    one), so it must not be accepted a second time.
    """
    if not code or not code.strip().isdigit():
        return None
    totp = pyotp.TOTP(raw_secret)
    step = current_step()
    # valid_window=1 checks step-1, step, step+1; find which one (if any)
    # actually matches so we can compare it against last_used_step.
    for candidate in (step - 1, step, step + 1):
        if totp.verify(code, for_time=candidate * 30, valid_window=0):
            if last_used_step is not None and candidate <= last_used_step:
                return None
            return candidate
    return None


# ── Recovery codes ───────────────────────────────────────────────────────

def generate_recovery_codes() -> list[str]:
    return [
        "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
        for _ in range(RECOVERY_CODE_COUNT)
    ]


def hash_recovery_code(code: str) -> str:
    """sha256 hex digest -- same rationale as core.security.hash_token:
    these are high-entropy random codes, not low-entropy user secrets, so
    a fast digest (not bcrypt) is appropriate, and a normalized
    (uppercased, whitespace-stripped) form is hashed so a copy/paste with
    stray case/whitespace still matches."""
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


# ── QR code (inline SVG) ──────────────────────────────────────────────
# WS-E.12 asks for "a QR as data-URI PNG generated server-side with
# qrcode lib or an inline SVG without extra deps: prefer SVG to avoid a
# new dependency". A correct QR encoder (Reed-Solomon ECC, mask
# selection, version sizing) from scratch is a lot of subtle surface to
# get right and re-review for something that only ever renders a URI a
# user scans once at setup time, so this uses the `qrcode` package
# (pinned in requirements.txt) purely for its matrix builder -- no PIL,
# no PNG, no image backend: get_matrix() is consumed directly into an
# inline SVG below, so the only new dependency is `qrcode` itself.

def build_otpauth_svg(otpauth_uri: str) -> str:
    """Render the otpauth:// URI as a scannable inline QR-code SVG."""
    import qrcode

    qr = qrcode.QRCode(border=2)
    qr.add_data(otpauth_uri)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    size = len(matrix)
    scale = 6
    px = size * scale
    cells = []
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                cells.append(f'<rect x="{x * scale}" y="{y * scale}" width="{scale}" height="{scale}"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {px} {px}" '
        f'width="{px}" height="{px}" shape-rendering="crispEdges">'
        f'<rect width="{px}" height="{px}" fill="#ffffff"/>'
        f'<g fill="#000000">{"".join(cells)}</g>'
        f'</svg>'
    )


# ── mfa_pending JWT (short-lived, distinct scope) ────────────────────────

def issue_mfa_pending_token(user_id: int) -> str:
    """A short-lived (5 min) JWT carrying scope='mfa_pending' -- this is
    NOT a normal access token: core/deps.py's get_current_user rejects
    any token with this scope outright, so it can only ever be exchanged
    via POST /api/auth/mfa/verify or /recovery, never used to call any
    other authenticated endpoint.

    Carries its own 'iat' (distinct from the eventual real access
    token's) -- (sub, iat) together identify one specific login
    challenge, which routers/mfa.py's per-challenge failure counter
    (record_pending_failure/pending_failures_exceeded below) keys on so
    two different login attempts by the same admin never share a
    lockout counter."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    to_encode = {
        "sub": str(user_id),
        "scope": MFA_PENDING_SCOPE,
        "iat": now,
        "exp": now + timedelta(minutes=MFA_PENDING_TTL_MINUTES),
    }
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_mfa_pending_token(token: str) -> Optional[int]:
    """Decode an mfa_pending token and return the user id, or None if it's
    invalid/expired/wrong-scope. Kept for callers that only need the
    identity (e.g. tests) -- routers/mfa.py uses
    decode_mfa_pending_claims() below when it also needs 'iat' for the
    failure counter."""
    claims = decode_mfa_pending_claims(token)
    return claims[0] if claims else None


def decode_mfa_pending_claims(token: str) -> Optional[tuple[int, int]]:
    """Like decode_mfa_pending_token, but returns (user_id, iat) so the
    caller can key the per-challenge failure counter. None on any
    invalid/expired/wrong-scope/missing-iat token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("scope") != MFA_PENDING_SCOPE:
        return None
    try:
        user_id = int(payload.get("sub"))
        iat = int(payload.get("iat"))
    except (TypeError, ValueError):
        return None
    return user_id, iat


# ── Per-challenge failed-attempt counter (used by routers/mfa.py) ───────
# In-memory, per-process dict keyed by (user_id, iat) -- iat uniquely
# identifies one mfa_pending challenge (see issue_mfa_pending_token).
# CAVEAT: this is per-worker state, not shared across uvicorn/gunicorn
# worker processes or app instances behind a load balancer -- with N
# workers an attacker can get up to N*MAX_PENDING_FAILURES guesses
# against one challenge before every worker independently locks it out,
# not a single global ceiling. That's an accepted tradeoff for a 5-minute-
# lived, single-use, 6-digit-code challenge with a 5/minute rate limit on
# top (routers/mfa.py) -- a real cross-worker counter would need Redis or
# equivalent shared storage, which this codebase doesn't otherwise depend
# on for anything auth-related today.
MAX_PENDING_FAILURES = 10
_pending_failures: dict[tuple[int, int], int] = {}


def _prune_pending_failures() -> None:
    """Lazy GC: drop counters for challenges whose token has definitely
    expired by now (iat older than the pending-token TTL), so a
    long-running worker doesn't accumulate entries forever."""
    cutoff = int(datetime.now(timezone.utc).timestamp()) - (MFA_PENDING_TTL_MINUTES * 60) - 60
    for key in [k for k in _pending_failures if k[1] < cutoff]:
        _pending_failures.pop(key, None)


def pending_failures_exceeded(user_id: int, iat: int) -> bool:
    return _pending_failures.get((user_id, iat), 0) >= MAX_PENDING_FAILURES


def record_pending_failure(user_id: int, iat: int) -> int:
    key = (user_id, iat)
    count = _pending_failures.get(key, 0) + 1
    _pending_failures[key] = count
    _prune_pending_failures()
    return count


def clear_pending_failures(user_id: int, iat: int) -> None:
    _pending_failures.pop((user_id, iat), None)


# ── Atomic step/recovery-code consumption (security-audit follow-up) ────
# verify_totp_code()'s last_used_step check above reads that column
# earlier in the request, non-atomically -- two concurrent requests
# racing the same valid code could both pass that in-app check before
# either write lands. These two helpers do the actual write as a single
# conditional UPDATE (compare-and-set at the row level), so only one
# concurrent request can ever win; the other sees zero affected rows and
# must treat that as an invalid/already-used code, not fall back to
# trusting its own earlier read.

def _rows_affected(status: str) -> int:
    """asyncpg's execute() returns a command tag like 'UPDATE 1' -- pull
    the row count off the end of it."""
    try:
        return int(status.rsplit(" ", 1)[-1])
    except (ValueError, AttributeError):
        return 0


async def commit_totp_step(user_id: int, step: int) -> bool:
    """Atomically advance users.mfa_last_used_step to `step`, but only if
    it's still NULL or behind `step`. Returns False (commit lost the
    race / step already consumed) if it affected zero rows -- callers
    must treat that exactly like a failed code, not proceed."""
    status = await execute(
        """UPDATE users SET mfa_last_used_step = $1
           WHERE id = $2 AND (mfa_last_used_step IS NULL OR mfa_last_used_step < $1)""",
        step, user_id,
    )
    return _rows_affected(status) > 0


async def consume_recovery_code(user_id: int, code_hash: str) -> bool:
    """Atomically remove one recovery-code hash from
    users.mfa_recovery_codes_hash, but only if it's still present.
    Returns False if it affected zero rows -- the code was invalid or
    already used by a concurrent request, and callers must treat that as
    such."""
    status = await execute(
        """UPDATE users SET mfa_recovery_codes_hash = array_remove(mfa_recovery_codes_hash, $1)
           WHERE id = $2 AND $1 = ANY(mfa_recovery_codes_hash)""",
        code_hash, user_id,
    )
    return _rows_affected(status) > 0


# ── Login-hook helpers (called from routers/auth.py login()) ────────────

def mfa_required_for_user(user: dict) -> bool:
    """True when login() must challenge for MFA instead of issuing real
    tokens: an admin account with MFA enabled. Anything else (non-admin,
    or an admin who hasn't run /enable yet) logs in normally -- MFA
    enrollment itself is never gated behind MFA."""
    return user.get("role") == "admin" and bool(user.get("totp_enabled_at"))


# ── Grace-period gate (used by core/deps.py's admin dependency) ─────────

def admin_mfa_grace_expired() -> bool:
    """True once MFA_GRACE_UNTIL has passed (or was never set). Only
    meaningful when settings.mfa_required_for_admin is true -- callers
    must check that first."""
    if not settings.mfa_grace_until:
        return True
    try:
        grace_until = datetime.fromisoformat(settings.mfa_grace_until)
    except ValueError:
        return True
    if grace_until.tzinfo is None:
        grace_until = grace_until.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= grace_until
