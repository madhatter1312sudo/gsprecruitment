"""
Talent OS -- the one definition of what a pipeline-entry row looks like on
the way out, shared by the client portal and the admin panel.

Two routes list `pipeline_entries`: GET /api/v1/client/pipeline (scoped to
the client behind the JWT) and GET /api/v1/admin/pipeline (WS5 BV1,
unscoped, admin JWT). They select the same columns and shape their rows
the same way; until this module they did so by carrying verbatim copies
of each other's SELECT and projection, which is the failure mode worth a
module: a fix applied to one copy and not the other leaves the two routes
disagreeing about what a pipeline row is.

They differ in two things, both explicit: their WHERE clause, and whether
the presentation-consent gate applies to `full_name`.

On that gate (chief-of-staff product decision, WS5 BV1). It is a
disclosure control aimed at the CLIENT: `consent_spec_presentation_at`
(migrations/018) records that a candidate agreed to be named to an
employer for a specific role, and routers/outreach.py refuses a spec
draft without it. It was never an internal access control. An admin
already reads `full_name` unconditionally from GET /api/v1/admin/
candidates and GET /api/v1/admin/candidates/{kind}/{id} -- the same
mandate, the same person, one click away -- so gating the admin pipeline
list withheld nothing from anyone and only left the panel's pipeline tab
showing blanks where a name belongs. Gate on for the client route, off
for the admin route; `gate_name` says which, per call, with no default so
a new call site has to decide rather than inherit.

The consent columns are IN the SELECT and OUT of the output either way:
the gate needs them on one route, and neither caller may see them.

Note for tests/test_consent_gate_coverage.py: that test AST-scans
routers/ only, so the SQL text living here is invisible to it and neither
route needs an allowlist entry. Both behaviours are covered at runtime --
see the comment in that file for which tests.
"""
from typing import List

# Selected by both routes. `pe.*` already carries id, client_id,
# candidate_id, job_id, stage, notes and the timestamps -- there is no
# separate client_id projection to add on the admin side.
PIPELINE_ROW_SQL = """SELECT pe.*, c.full_name, c.current_title, c.current_company,
                   c.location, c.skills, j.title AS job_title,
                   c.consent_spec_presentation_at, c.consent_withdrawn_at
            FROM pipeline_entries pe
            JOIN candidates c ON c.id = pe.candidate_id
            JOIN job_orders j ON j.id = pe.job_id"""

# The two columns the gate reads and the caller never gets.
_CONSENT_COLUMNS = ("consent_spec_presentation_at", "consent_withdrawn_at")


def project_pipeline_rows(rows, *, gate_name: bool) -> List[dict]:
    """Turn pipeline rows into response dicts, optionally gating the name.

    `gate_name=True` (the client portal): FIX 1 (chief-of-staff,
    ai-pseudonimisering branch, ronde 5) -- the same rule as
    routers/client.py's _project_candidate_public. A pipeline entry
    existing at all does not mean the candidate ever consented to be
    named to this client, so `full_name` is dropped unless
    consent_spec_presentation_at is set and consent has not since been
    withdrawn.

    `gate_name=False` (the admin panel): the name is always returned.
    See the module docstring for why -- this is a client-disclosure
    control, and the admin reading it already has the name from
    GET /api/v1/admin/candidates.

    Either way every pe.*/job_title field is kept (this is a pipeline the
    viewer already works with, not a fresh anonymised listing), the two
    consent columns are dropped before the row leaves, and `skills` is
    coerced from NULL to [] -- the house rule for every array column on
    the way out.

    Keyword-only and without a default on purpose: a future third caller
    must state which side of that decision it is on.
    """
    items = []
    for row in rows:
        item = dict(row)
        eligible = (
            item.get("consent_spec_presentation_at")
            and not item.get("consent_withdrawn_at")
        )
        for column in _CONSENT_COLUMNS:
            item.pop(column, None)
        if gate_name and not eligible:
            item.pop("full_name", None)
        item["skills"] = item.get("skills") or []
        items.append(item)
    return items
