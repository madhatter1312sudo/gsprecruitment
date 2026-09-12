"""
FIX 3 (chief-of-staff, ai-pseudonimisering branch, ronde 5): a structural
brake so a *new* endpoint that reads a candidate's `full_name`/`email` (or
`SELECT *`/`c.*`) via `FROM candidates` or `JOIN candidates` gets caught by
CI instead of relying on a human reviewer noticing four rounds in a row
(client.py, matches.py and candidates.py each shipped an un-gated read
before being caught by hand -- `grep -rn "_consent_gate_sql" tests/` used
to return nothing).

Design, so this actually fails on a new offender instead of just recording
today's rules:

- Parsed with `ast`, not grepped as raw text. An f-string's literal
  segments are concatenated from their Constant parts (FormattedValue
  nodes -- the `{...}` interpolations -- are dropped), which is exactly
  where the guard phrases live in every query in this codebase (e.g.
  `f"... WHERE c.deleted_at IS NULL AND c.consent_withdrawn_at IS NULL "
  f"AND ({_consent_gate_sql('c.')})"` puts both literal phrases in the
  string parts, not inside the interpolation). This survives reformatting
  that would break a naive single-line regex over the source text.
- Triggers only on a query that both touches the `candidates` table via
  FROM/JOIN (a *read*, not a bare INSERT/UPDATE/DELETE) and actually
  selects an identifying column (`full_name`, `email`, `SELECT *`, or an
  aliased `<alias>.*`) -- `SELECT id ...` or `SELECT COUNT(*) ...` from
  candidates isn't a name/e-mail leak and would otherwise force an
  allowlist entry for every innocuous existence check in the codebase,
  which would bury the signal this test exists to give.
- Requires both `deleted_at IS NULL` and `consent_withdrawn_at IS NULL` to
  appear, as text, in the same query literal (regex, case- and
  whitespace-tolerant) -- reordering the clauses or renaming a bound
  parameter doesn't get you past it, because the actual property being
  checked is "the words are in the SQL", not a specific AST shape.
- A query that legitimately has neither (an admin-only endpoint where
  `require_role("admin")` already grants unrestricted access, a GDPR
  self-service export/erasure that must reach a candidate's own row even
  after they withdrew consent, an Apollo-pool purge job that never
  returns the email it reads back to a caller, ...) must be added to
  `_ALLOWLIST` below with a one-line reason -- a deliberate, reviewable
  decision that shows up in the diff, not a silent pass. Anything else
  that reads an identifying candidates column without both guard phrases
  and without a matching allowlist entry fails this test, with a message
  that tells the next developer exactly what to do.
"""
import ast
import os
import re

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTERS_DIR = os.path.join(BACKEND_ROOT, "routers")

_TABLE_READ_RE = re.compile(r"\b(from|join)\s+candidates\b", re.IGNORECASE)
_SELECT_RE = re.compile(r"\bselect\b", re.IGNORECASE)
_WILDCARD_RE = re.compile(r"select\s+(\*|[a-zA-Z_][a-zA-Z0-9_]*\.\*)", re.IGNORECASE)
_FULL_NAME_RE = re.compile(r"\bfull_name\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\bemail\b", re.IGNORECASE)
_DELETED_GATE_RE = re.compile(r"deleted_at\s+IS\s+NULL", re.IGNORECASE)
_CONSENT_GATE_RE = re.compile(r"consent_withdrawn_at\s+IS\s+NULL", re.IGNORECASE)

# (filename, a short substring unique enough to identify the query in that
# file) -> why it is legitimately exempt. Keep the substring short so a
# query rewritten for an unrelated reason doesn't silently keep matching
# an entry whose reasoning no longer applies -- the staleness check below
# forces a look whenever that happens.
_ALLOWLIST = {
    ("admin.py", "c.full_name, c.email, c.phone, c.current_title, c.current_company, c.location,"):
        "GET /api/v1/admin/candidates -- admin JWT only (require_role('admin')), "
        "the platform-wide candidate list an admin needs to administer every "
        "row including soft-deleted/withdrawn ones (VERWERKINGSREGISTER.md B4).",
    ("admin.py", "SELECT c.*, COALESCE(m.match_count, 0) AS match_count,"):
        "GET /api/v1/admin/candidates/{kind}/{item_id} -- admin JWT only, "
        "unrestricted candidate detail by design; this is the path "
        "VERWERKINGSREGISTER.md rij 58/§6.6 documents as exposing cv_text, "
        "nationality and IND-status alongside full_name/email to an admin.",
    ("candidate.py", "c.full_name AS sender_name"):
        "GET /api/v1/candidate/messages -- the candidate viewing their own "
        "inbox; the JOIN's WHERE already scopes om.candidate_id to the "
        "authenticated user's own candidate_id, so c.full_name is always "
        "the viewer's own name, never another candidate's.",
    ("public.py", "SELECT id, email FROM candidates WHERE id = $1::int"):
        "POST /api/public/unsubscribe (WS3c) -- the one-click unsubscribe "
        "must keep working for exactly the people these two guards exclude: "
        "someone who already withdrew consent and clicks a second time, and "
        "someone whose row was soft-deleted between the send and the click. "
        "Adding the guards would make an unsubscribe silently do nothing for "
        "them, which is the wrong direction for an opt-out. The row is "
        "reached only by presenting a valid, unused, per-send token "
        "(job_alert_sends.token_hash), never by id or address, and the "
        "address is used solely to compute privacy.email_hash() for the "
        "suppression list -- it is never returned to the caller and never "
        "logged (VERWERKINGSREGISTER.md rij 20).",
    ("gdpr.py", "SELECT * FROM candidates WHERE id = $1 AND deleted_at IS NULL"):
        "GET /api/v1/gdpr/export self-service export -- must reach the "
        "requester's own row (matched via their own candidate_profiles "
        "link) even after they withdrew consent for outreach; consent "
        "withdrawal does not remove their Art. 15/20 access to their own data.",
    ("gdpr.py", "SELECT * FROM candidates WHERE LOWER(email) = LOWER($1) AND deleted_at IS NULL"):
        "GET /api/v1/gdpr/export self-service export, e-mail-fallback "
        "branch -- same reasoning as the FK-first branch above: a "
        "requester's own row, consent_withdrawn_at does not apply to "
        "self-access.",
    # WS-E.10 (owner decision, retention-kolommen branch, fifth round):
    # the Apollo-pool query text that used to live here as a
    # retention_admin.py literal (and needed the allowlist entry this
    # comment replaces) moved to core/retention.py as APOLLO_POOL_ROWS_SQL/
    # APOLLO_POOL_TARGET_SQL, so both routers/retention_admin.py's dry-run
    # preview and services/scheduler.py's generate_retention_review() read
    # the exact same guarded selector -- this file's AST scan (ROUTERS_DIR
    # only) no longer sees the raw SQL text in retention_admin.py at all
    # (just a name reference to the core.retention constant), so there is
    # nothing left here to allowlist. The guards themselves are unchanged
    # and still covered by tests/test_retention.py's
    # test_apollo_pool_purge_target_sql_carries_all_six_guards and
    # tests/test_ws_e10_no_unapproved_purge_path.py.
    ("client.py", "SELECT c.id, c.full_name, c.current_title, c.current_company,"):
        "GET /api/v1/client/candidates (search_candidates) -- deleted_at "
        "IS NULL and consent_withdrawn_at IS NULL ARE both required here "
        "(FIX 1, chief-of-staff ai-pseudonimisering branch ronde 5), but "
        "as part of a `conditions` list joined into a `where` variable "
        "interpolated into the f-string (f\"...WHERE {where}...\") -- "
        "invisible to this test's literal-text scan, which only sees the "
        "f-string's own Constant parts. Verified at runtime instead by "
        "tests/integration/test_client_portal.py "
        "(test_withdrawn_consent_overrides_spec_presentation_consent).",
    # WS5 (code-review F3): GET /api/v1/client/pipeline and
    # GET /api/v1/admin/pipeline used to each carry a verbatim copy of the
    # same SELECT and the same Python-side consent gate, and each needed
    # an allowlist entry here. Both now read core/pipeline.py's
    # PIPELINE_ROW_SQL and project_pipeline_rows() -- one SELECT list, one
    # projection. This file's AST scan covers ROUTERS_DIR only, so that
    # SQL text is no longer visible to it and there is nothing left for
    # either route to allowlist. Do not add an entry back for them: an
    # entry that matches nothing trips the staleness assert below.
    #
    # Neither route is gated on consent_withdrawn_at in SQL, deliberately:
    # an ongoing engagement must not vanish from the list when a candidate
    # withdraws consent. What happens to `full_name` afterwards is now a
    # per-route decision, and both halves are covered at runtime:
    #
    #   - client route, gate ON -- the name is withheld without
    #     presentation consent and taken away again on withdrawal.
    #     tests/integration/test_ws5_backend_conditions_integration.py
    #     (test_client_pipeline_still_withholds_the_name_without_consent).
    #     Note that test_client_portal.py's
    #     test_withdrawn_consent_overrides_spec_presentation_consent
    #     covers the sibling /client/candidates search route, not this
    #     one -- the pipeline route has its own test for a reason.
    #   - admin route, gate OFF by product decision of the chief-of-staff
    #     (see core/pipeline.py for the reasoning: it is a client-
    #     disclosure control, and GET /admin/candidates already hands the
    #     same admin the same name).
    #     test_ws5_backend_conditions_integration.py
    #     (test_bv1_admin_always_sees_the_name).
    #
    # That admin exposure needs no allowlist entry for a second reason
    # too: it is not a new one. GET /api/v1/admin/candidates and
    # GET /api/v1/admin/candidates/{kind}/{item_id} are allowlisted above
    # for handing an admin JWT exactly this field on exactly these rows.
}


def _iter_string_literals(tree):
    """Yield (reconstructed_text, lineno) for every string/f-string literal
    in the module, f-strings reconstructed from their literal Constant
    parts only (interpolations dropped)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            parts = [
                v.value for v in node.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            ]
            yield "".join(parts), node.lineno
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value, node.lineno


def _router_files():
    for name in sorted(os.listdir(ROUTERS_DIR)):
        if name.endswith(".py") and not name.startswith("__"):
            yield os.path.join(ROUTERS_DIR, name)


def _select_head(text):
    """Everything up to (not including) the first standalone WHERE --
    i.e. the SELECT column list plus FROM/JOIN clauses. Column-identifying
    checks run against this, not the full query, so a WHERE-clause filter
    like `LOWER(email) = $1` (id-only lookups all over this codebase)
    doesn't get mistaken for the query *selecting* email back to the
    caller."""
    m = re.search(r"\bwhere\b", text, re.IGNORECASE)
    return text[: m.start()] if m else text


def _is_identifying_read(text):
    if not _TABLE_READ_RE.search(text):
        return False
    head = _select_head(text)
    if not _SELECT_RE.search(head):
        return False
    return bool(_WILDCARD_RE.search(head) or _FULL_NAME_RE.search(head) or _EMAIL_RE.search(head))


def _is_gated(text):
    return bool(_DELETED_GATE_RE.search(text) and _CONSENT_GATE_RE.search(text))


def test_every_identifying_candidates_read_is_gated_or_allowlisted():
    failures = []
    matched_keys = set()
    router_files = list(_router_files())
    assert router_files, "no router files found -- ROUTERS_DIR is misconfigured"

    for path in router_files:
        fname = os.path.basename(path)
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=path)
        for text, lineno in _iter_string_literals(tree):
            if not _is_identifying_read(text):
                continue
            if _is_gated(text):
                continue
            key = None
            for afile, substr in _ALLOWLIST:
                if afile == fname and substr in text:
                    key = (afile, substr)
                    break
            if key is not None:
                matched_keys.add(key)
                continue
            failures.append(
                f"{fname}:{lineno} reads an identifying candidates column "
                f"(full_name/email/SELECT *) via FROM/JOIN candidates "
                f"without both 'deleted_at IS NULL' and "
                f"'consent_withdrawn_at IS NULL' in the same query, and is "
                f"not in _ALLOWLIST (tests/test_consent_gate_coverage.py). "
                f"Either add both guard conditions to the query (see "
                f"routers/matches.py's _consent_gate_sql for the fuller "
                f"lawful-basis gate used for external-facing matching "
                f"reads), or -- only if there is a genuine reason this "
                f"endpoint must see soft-deleted or consent-withdrawn "
                f"candidates by name/e-mail (e.g. an admin-only endpoint, "
                f"or a GDPR self-service path) -- add an entry to "
                f"_ALLOWLIST with that reason, and document the exposure "
                f"in docs/VERWERKINGSREGISTER.md."
            )

    assert not failures, "Un-gated identifying candidates read(s) found:\n" + "\n".join(failures)

    stale = set(_ALLOWLIST) - matched_keys
    assert not stale, (
        "These _ALLOWLIST entries no longer match any query in their file "
        f"(the query was changed or removed -- update or delete the entry): {stale}"
    )


def test_meta_test_actually_fails_on_a_fresh_unfiltered_read():
    """Guards the guard: prove _is_identifying_read/_is_gated would catch
    exactly the shape of bug this test exists to prevent (a brand-new
    endpoint added tomorrow that joins candidates and selects full_name
    with no consent guard at all), and does NOT false-positive on an
    innocuous id-only existence check."""
    leaky = 'f"SELECT c.id, c.full_name, c.email FROM candidates c WHERE c.id = $1"'
    assert _is_identifying_read(leaky) and not _is_gated(leaky)

    gated = (
        'f"SELECT c.id, c.full_name FROM candidates c '
        'WHERE c.deleted_at IS NULL AND c.consent_withdrawn_at IS NULL"'
    )
    assert _is_identifying_read(gated) and _is_gated(gated)

    id_only = 'f"SELECT id FROM candidates WHERE id = $1"'
    assert not _is_identifying_read(id_only)

    count_only = '"SELECT COUNT(*) FROM candidates WHERE deleted_at IS NULL"'
    assert not _is_identifying_read(count_only)
