"""
Talent OS — WS-E.12: TOTP-based MFA for admin accounts.

Adds to `users`:
  - totp_secret_enc          text          — the TOTP shared secret,
    Fernet-encrypted at rest (core/mfa.py) with MFA_ENC_KEY. Never the raw
    base32 secret; NULL until POST /api/auth/mfa/setup is called.
  - totp_enabled_at          timestamptz   — set by POST /api/auth/mfa/enable
    once the first code has been verified. NULL means MFA is not enabled
    for this user — routers/auth.py login() only sends the mfa_pending
    challenge when this is set (and role = 'admin').
  - mfa_recovery_codes_hash  text[]        — sha256 hex digests of the 10
    one-time recovery codes generated at enable time (core/mfa.py). Raw
    codes are shown exactly once in the enable response body and never
    stored; a consumed code's hash is removed from the array (POST
    /api/auth/mfa/recovery), giving natural single-use semantics without a
    separate "used" flag.
  - mfa_last_used_step       bigint        — the TOTP time-step (unix time
    // 30) of the last code this account successfully verified with,
    across setup/enable/verify/disable. Replay protection: core/mfa.py
    rejects a step <= this value even if the code itself still hashes
    correctly, so the same 30s code (or an intercepted one) cannot be
    replayed within its validity window.

All four columns are nullable / defaultless additions to an existing
table with live rows — ADD COLUMN IF NOT EXISTS is instant on Postgres for
a nullable column with no default, and NULL is exactly "MFA not set up
yet" for every existing user, admin included. No backfill needed and no
account is locked out by this migration landing: the login hook in
routers/auth.py only branches into the mfa_pending challenge once
totp_enabled_at is actually set by a deliberate POST /api/auth/mfa/enable
call.

Idempotent: every ALTER is IF NOT EXISTS, safe to re-run, same pattern as
migrations/017_email_verification.py.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "021_admin_mfa"

MIGRATION_SQL = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret_enc text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_recovery_codes_hash text[];
ALTER TABLE users ADD COLUMN IF NOT EXISTS mfa_last_used_step bigint;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
