"""
Talent OS — canonical `candidates.source` literals + family grouping.

candidates.source (migrations/000_baseline.py) is a free-text VARCHAR(50)
written by several different code paths. This module is the single list
of the literals this codebase itself ever writes, plus SOURCE_FAMILY,
which groups near-duplicate machine sources for reporting (routers/
client.py's source_breakdown) without losing the underlying literal
anywhere it's stored.

The six literals:
  - PORTAL_REGISTRATION ("portal_registration"): services/candidate_link.py
    -- a candidate who registered on the portal themselves and was
    auto-linked to a candidates row (WS-C.16 "één kandidaatrecord").
  - TALENTPOOL_OPTIN ("talentpool_optin"): routers/public.py's talentpool
    double opt-in flow (SOP §1.5) -- no source_url, consent is the site
    itself.
  - APOLLO ("apollo"): services/scheduler.py's live Apollo sync (one row
    at a time).
  - APOLLO_BULK ("apollo_bulk"): services/harvest.py's bulk Apollo
    harvest job -- a separate write path for the same vendor as APOLLO.
  - AGENT ("agent"): routers/webhook.py's default when an external
    sourcing agent/integration posts a candidate in without specifying
    one.
  - caller-supplied: not a literal GSP ever writes itself -- an
    authenticated API caller may set CandidateCreate.source
    (models/schemas.py) freely. Not listed in KNOWN_SOURCES; SOURCE_FAMILY
    has no special case for it, so source_family() returns it unchanged
    (its own, one-member family).

routers/admin.py's kind_sql (GET /v1/admin/candidates) still checks
`c.source = PORTAL_REGISTRATION` -- source keeps its original sourcing
-provenance meaning there, it is just no longer the *only* signal for
"self-registered" once a candidate_profiles link exists (a linked profile
is the stronger truth, see routers/admin.py). services/candidate_link.py
itself is deliberately left unchanged: it already writes the same literal.
"""
from typing import Optional

PORTAL_REGISTRATION = "portal_registration"
TALENTPOOL_OPTIN = "talentpool_optin"
APOLLO = "apollo"
APOLLO_BULK = "apollo_bulk"
AGENT = "agent"

KNOWN_SOURCES = (PORTAL_REGISTRATION, TALENTPOOL_OPTIN, APOLLO, APOLLO_BULK, AGENT)

# Only near-duplicate machine sources are grouped -- everything else
# (including a caller-supplied value never seen here) is its own family.
SOURCE_FAMILY = {
    APOLLO: "apollo",
    APOLLO_BULK: "apollo",
}


def source_family(source: Optional[str]) -> str:
    """The reporting family for a candidates.source value. A source not
    in SOURCE_FAMILY (including None/caller-supplied/unknown) is its own
    family -- None becomes the literal string "unknown" so it groups
    sensibly in a breakdown dict instead of colliding under a Python
    None key."""
    if not source:
        return "unknown"
    return SOURCE_FAMILY.get(source, source)
