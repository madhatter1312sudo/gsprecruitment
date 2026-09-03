"""
Talent OS — WS-E.4: per-account login lockout + password-change token
invalidation columns.

Adds to `users`:
  - failed_login_count INTEGER NOT NULL DEFAULT 0  — consecutive failed
    password checks against this account (routers/auth.py login()). Reset
    to 0 on a successful login, and by change-password / reset-password /
    set-password (a fresh password shouldn't inherit a stale failure
    streak). See routers/auth.py's _register_failed_login for the
    sliding-window logic that increments this.
  - last_failed_login_at TIMESTAMPTZ               — when the current
    failure streak's most recent attempt happened; _register_failed_login
    both reads it (to decide reset-vs-increment against the 15-minute
    window) and overwrites it with NOW() in the same UPDATE. Deliberately
    its own column, NOT the shared `updated_at` -- an unrelated write to
    the same user row (a profile edit, an admin PUT
    /api/v1/admin/users/{id}, a client approval, ...) must never nudge
    the lockout window. Cleared back to NULL alongside
    failed_login_count/locked_until on a successful login, an admin
    unlock, or any password change.
  - locked_until TIMESTAMPTZ                       — set once
    failed_login_count hits the threshold (10) within the window (15
    minutes); login() returns the same generic 401 as a wrong password
    while `locked_until > NOW()`, plus a Retry-After header, and never
    reveals whether the account exists or is merely locked. Admin can
    clear it early via POST /api/v1/admin/users/{id}/unlock
    (routers/admin.py).
  - password_changed_at TIMESTAMPTZ                — stamped by
    change-password, reset-password and set-password (routers/auth.py).
    core/deps.get_current_user compares a JWT's 'iat' claim against this
    and rejects the token if the token was issued before the password was
    last changed -- closes the "stolen token keeps working after a
    password reset" gap flagged in migrations/017_email_verification.py's
    docstring. NULL means "never changed since this column existed" --
    nothing to compare against, so no token is rejected on that basis
    alone (see core/deps._token_predates_password_change).

No backfill needed: all four columns default to an inert "not locked /
never failed / no known change time" state that is exactly correct for
every existing row -- there is nothing to compute from other columns
(unlike migration 017's is_verified/role-derived backfills).

Idempotent: every ALTER is IF NOT EXISTS, matching the pattern used by
every migration in this directory (see 004_reset_token_expiry.py,
017_email_verification.py) -- a second run touches zero rows.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "020_login_lockout"

MIGRATION_SQL = """
ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_failed_login_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_users_locked_until ON users(locked_until) WHERE locked_until IS NOT NULL;
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
