"""
Talent OS — WS-E.2: e-mail verification + admin approval for client users.

Adds to `users`:
  - email_verified_at TIMESTAMPTZ     — when the e-mail was confirmed. Kept
    in lockstep with the existing `is_verified` boolean going forward (both
    are set together — see routers/auth.py verify_email/set_password); the
    boolean is the fast/cheap check used everywhere, this column is the
    "when" for audit/debugging.
  - verification_token_hash TEXT      — sha256 hex digest of the random
    verification / set-password token (secrets.token_urlsafe). The raw
    token is only ever in the e-mail; it is never written to the database,
    only its hash — see the code-review note on commit 72b4bcd's audit-log
    JSON-serialization bug for why "never store the raw thing" matters
    here too.
  - verification_sent_at TIMESTAMPTZ  — when the current token was issued;
    routers/auth.py enforces a 24h TTL measured from this column.
  - approved_by_admin_at TIMESTAMPTZ  — WS-E.2's client-approval gate.
    routers/client.py's _require_candidate_access requires this to be set
    (in addition to role='client') before a non-admin client user can
    reach any candidate-search/detail endpoint. Set by
    POST /api/v1/admin/clients/{user_id}/approve.
  - approved_by_admin_id INTEGER      — which admin approved (audit trail,
    also written to audit_log by the approve endpoint above).

Backfill — production already has real users with working sessions today,
and this migration must not lock any of them out the moment it runs:
  1. Every user with is_verified = TRUE gets email_verified_at = NOW().
     Their e-mail was already confirmed under the pre-WS-E.2 flow (the old
     plaintext-token /api/auth/verify endpoint), or they signed in via
     Google (routers/auth.py google_callback only creates an account after
     Google itself reports email_verified=true) — either way there is
     nothing left to re-verify.
  2. Every existing user with role = 'client' gets approved_by_admin_at =
     NOW(). WS-E.2 is the first time a client-approval gate exists at all
     (routers/client.py previously TODO'd this exact column); without this
     backfill, every client who already has a working account today would
     be locked out of candidate search/detail the instant this migration
     applies, with no admin having taken any action. New client signups
     from this point forward start unapproved and need an explicit
     POST /api/v1/admin/clients/{user_id}/approve before they can search
     or view candidates.

Idempotent: every ALTER is IF NOT EXISTS, the index is IF NOT EXISTS, and
both backfill UPDATEs are WHERE ... IS NULL-guarded — a second run touches
zero rows once the gaps are filled, same pattern as every other migration
in this directory (see migrations/004_reset_token_expiry.py).
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "017_email_verification"

MIGRATION_SQL = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_token_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_sent_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_by_admin_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_by_admin_id INTEGER REFERENCES users(id);
CREATE INDEX IF NOT EXISTS idx_users_verification_token_hash ON users(verification_token_hash) WHERE verification_token_hash IS NOT NULL;
UPDATE users SET email_verified_at = NOW() WHERE is_verified = TRUE AND email_verified_at IS NULL;
UPDATE users SET approved_by_admin_at = NOW() WHERE role = 'client' AND approved_by_admin_at IS NULL;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
