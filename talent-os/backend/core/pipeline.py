"""
Talent OS -- the one definition of what a pipeline-entry row looks like on
the way out, shared by the client portal and the admin panel.

Two routes list `pipeline_entries`: GET /api/v1/client/pipeline (scoped to
the client behind the JWT) and GET /api/v1/admin/pipeline (WS5 BV1,
unscoped, admin JWT). They differ in exactly one thing, their WHERE
clause. Everything else -- which columns are selected, and the
presentation-consent gate applied to `full_name` afterwards -- has to be
identical, and until this module it was identical by having been copied.

That copy is the failure mode worth spending a module on: the gate is the
reason a candidate who never consented to being named is not named, and a
fix or a tightening applied to one copy and not the other would leave one
route quietly handing out a name the other withholds. There is now one
SELECT list and one projection function; a route chooses rows, not shape.

The consent columns are deliberately IN the SELECT and OUT of the output:
the gate needs them, the caller must never see them.

Note for tests/test_consent_gate_coverage.py: that test AST-scans
routers/ only, so the SQL text living here is invisible to it and neither
route needs an allowlist entry any more. The gate itself is covered by
the integration tests named in that file's comment.
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


def project_pipeline_rows(rows) -> List[dict]:
    """Apply the presentation-consent gate and hand back plain dicts.

    FIX 1 (chief-of-staff, ai-pseudonimisering branch, ronde 5): the same
    gate as routers/client.py's _project_candidate_public -- a pipeline
    entry existing at all does not mean the candidate ever consented to
    be named. Every pe.*/job_title field is kept (this is a pipeline the
    viewer already works with, not a fresh anonymised listing); only
    `full_name` is conditional, and the two consent columns are dropped
    either way.

    `skills` is coerced from NULL to [] here, the house rule for every
    array column on the way out.
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
        if not eligible:
            item.pop("full_name", None)
        item["skills"] = item.get("skills") or []
        items.append(item)
    return items
