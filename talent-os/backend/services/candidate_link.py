"""
Talent OS — WS-C.16 "één kandidaatrecord": the single place that resolves
the `candidates` row for a self-registered `users`/`candidate_profiles`
account, and links the two via `candidate_profiles.candidate_id` (see
migrations/023_candidate_profiles_candidate_id.py).

Both routers/auth.py (once a candidate confirms their e-mail — WS-E.2)
and routers/candidate.py (lazily, the first time a verified candidate
touches matches/applications/saved-jobs/messages/profile) need this same
resolve-or-create-and-link behaviour; this module is the one
implementation both call into, so the FK stays the single source of
truth for "does this person already have a candidates row" instead of
each router re-deriving it by its own e-mail join.

Resolution order:
  1. candidate_profiles.candidate_id, if already set (the FK — the fast
     path for every account this migrated once).
  2. Case-insensitive e-mail match against an existing candidates row
     (legacy: rows migrations/023 hasn't backfilled, or a candidates row
     that was sourced after this profile last resolved) — and, when
     found, the FK is written back so this fallback isn't needed again.
  3. Create a new candidates row (source='portal_registration',
     lawful_basis='portal_registratie') and link it — same shape
     migrations/023's one-time backfill uses for the same case.

Never called for an unverified account — callers are responsible for
that gate (routers/candidate.py's endpoints all sit behind
core.deps.get_verified_user; routers/auth.py only calls this after
marking the account verified in the same request) per WS-E.2: an
unverified self-registered person must not get a candidates row.
"""
from typing import Optional

from core.database import fetch_one, execute

# WS-E.7, SOP §1.4: self-registered candidates don't need a sourcing
# source_url (they made first contact themselves), but every candidates
# row records where it came from for consistency — this is that URL.
# Kept in sync with routers/candidate.py's own constant of the same name.
PORTAL_REGISTRATION_SOURCE_URL = "https://gsprecruitment.nl/candidate/"


async def get_or_create_candidate_id(user_id: int) -> Optional[int]:
    """Resolve (creating/linking if needed) the candidates.id for this
    users.id. Returns None only if the user itself doesn't exist."""
    profile = await fetch_one(
        "SELECT candidate_id FROM candidate_profiles WHERE user_id = $1", user_id,
    )
    if profile and profile["candidate_id"]:
        return profile["candidate_id"]

    user = await fetch_one(
        "SELECT email, full_name FROM users WHERE id = $1 AND deleted_at IS NULL", user_id,
    )
    if not user:
        return None

    # Legacy fallback: a candidates row already exists under this e-mail
    # (case-insensitive) but candidate_profiles.candidate_id was never
    # backfilled to it — link it now instead of creating a duplicate.
    # Lowest id wins if more than one candidates row shares the address,
    # same tie-break migrations/023's backfill uses.
    existing = await fetch_one(
        "SELECT id FROM candidates WHERE LOWER(email) = LOWER($1) AND deleted_at IS NULL "
        "ORDER BY id ASC LIMIT 1",
        user["email"],
    )
    if existing:
        await execute(
            "UPDATE candidate_profiles SET candidate_id = $1 WHERE user_id = $2 AND candidate_id IS NULL",
            existing["id"], user_id,
        )
        return existing["id"]

    profile_row = await fetch_one(
        "SELECT phone, current_title, current_company, location, skills, years_experience "
        "FROM candidate_profiles WHERE user_id = $1",
        user_id,
    )
    created = await fetch_one(
        """INSERT INTO candidates (full_name, email, phone, current_title, current_company,
                                   location, skills, years_experience, source,
                                   source_url, lawful_basis, date_found)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'portal_registration',
                   $9, 'portal_registratie', CURRENT_DATE)
           ON CONFLICT DO NOTHING
           RETURNING id""",
        user["full_name"] or user["email"],
        user["email"],
        profile_row["phone"] if profile_row else None,
        profile_row["current_title"] if profile_row else None,
        profile_row["current_company"] if profile_row else None,
        profile_row["location"] if profile_row else None,
        profile_row["skills"] if profile_row else None,
        profile_row["years_experience"] if profile_row else None,
        PORTAL_REGISTRATION_SOURCE_URL,
    )
    if not created:
        # Race: another request created it (e.g. its own ON CONFLICT DO
        # NOTHING landed first on the unique e-mail constraint) between
        # our SELECT above and this INSERT — pick up what won.
        created = await fetch_one(
            "SELECT id FROM candidates WHERE LOWER(email) = LOWER($1) AND deleted_at IS NULL "
            "ORDER BY id ASC LIMIT 1",
            user["email"],
        )
    if not created:
        return None

    await execute(
        "UPDATE candidate_profiles SET candidate_id = $1 WHERE user_id = $2 AND candidate_id IS NULL",
        created["id"], user_id,
    )
    return created["id"]
