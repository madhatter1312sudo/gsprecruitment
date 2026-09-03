"""
Talent OS — WS-C.17 "opt-in talentpool".

Adds the four consent columns to `candidates` (docs/SOURCING-SOP.md §1.5 /
§2, core/retention.py's `talentpool_consent` row) plus a small pending-token
table for the public (unauthenticated) opt-in/confirm flow.

Pattern of 014/015/018 (see 018_gdpr_provenance_optout.py's docstring for
the full rationale): idempotent (ADD COLUMN IF NOT EXISTS / CREATE TABLE IF
NOT EXISTS / CREATE INDEX IF NOT EXISTS), no `DO $$ ... END $$;` blocks
(migrations/_runner.py splits on a literal ";"). Postgres has no `ADD
CONSTRAINT IF NOT EXISTS` for a CHECK, so the value-set checks are attached
inline on the `ADD COLUMN IF NOT EXISTS ... CHECK (...)` statement — when
the column already exists the whole statement is a no-op, so re-running
this is safe.

candidates columns:
  - consent_talentpool_at TIMESTAMPTZ      — when the person ticked the box
    (portal profile, kandidaten.html form, or blog CTA) or an admin
    recorded evidence of consent.
  - consent_talentpool_until TIMESTAMPTZ   — 12 months from
    consent_talentpool_at, renewable; this is the anchor
    core/retention.py's `talentpool_consent` row now runs against
    (schema_ready flips to True in the same PR — see that module).
  - consent_scope TEXT                     — 'matching_only' or
    'matching_and_contact'; what the person agreed to.
  - consent_source TEXT                    — 'portal' (candidate portal
    profile toggle), 'kandidaten_page' (website/kandidaten.html
    checkbox), 'blog_cta' (website/blog/post.html CTA -> kandidaten
    anchor), or 'admin' (PATCH .../talentpool-consent with an `evidence`
    field, e.g. a signed form on file).

talentpool_optin_requests — the public POST /api/public/talentpool-optin ->
POST /api/public/talentpool-confirm flow (mirrors WS-E.2's hashed
verification-token pattern in routers/auth.py: only sha256(token) is ever
stored, never the raw token, which exists only in the outbound e-mail).
A person confirming here may not have a `candidates` row yet (this is
often their first-ever contact with GSP, via their own opt-in — SOP §1.5
"herkomst is de eigen site"), so the token is keyed on e-mail rather than
a candidate id; POST /talentpool-confirm creates the candidates row if
none exists, or updates the existing one by e-mail. `source` here is
deliberately narrower than candidates.consent_source's CHECK — only the
two public-form channels ('kandidaten_page', 'blog_cta') ever create a
pending request row; 'portal' and 'admin' consent is recorded directly
on `candidates`, never through this table.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _runner import run_migration  # noqa: E402

VERSION = "030_talentpool_consent"

MIGRATION_SQL = """
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS consent_talentpool_at TIMESTAMPTZ;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS consent_talentpool_until TIMESTAMPTZ;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS consent_scope TEXT CHECK (consent_scope IN ('matching_only','matching_and_contact'));
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS consent_source TEXT CHECK (consent_source IN ('portal','kandidaten_page','blog_cta','admin'));
CREATE INDEX IF NOT EXISTS idx_candidates_consent_talentpool_until ON candidates(consent_talentpool_until) WHERE consent_talentpool_until IS NOT NULL;
CREATE TABLE IF NOT EXISTS talentpool_optin_requests (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL,
    token_hash      TEXT NOT NULL UNIQUE,
    scope           TEXT NOT NULL CHECK (scope IN ('matching_only','matching_and_contact')),
    source          TEXT NOT NULL CHECK (source IN ('kandidaten_page','blog_cta')),
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_talentpool_optin_requests_token_hash ON talentpool_optin_requests(token_hash);
CREATE INDEX IF NOT EXISTS idx_talentpool_optin_requests_email ON talentpool_optin_requests(email);
"""

if __name__ == "__main__":
    asyncio.run(run_migration(VERSION, MIGRATION_SQL))
