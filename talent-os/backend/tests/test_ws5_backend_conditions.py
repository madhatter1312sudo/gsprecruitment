"""
WS5 backendvoorwaarden BV1 t/m BV10 (SITE-DESIGN-SPEC.md §7.7) -- de
delen die zonder database te testen zijn: de sorteerhelper, de twee
pydantic-modellen die strenger werden, de kolomlijsten en de tekst van
migratie 043. Het gedrag over een echte Postgres staat in
tests/integration/test_ws5_backend_conditions_integration.py.
"""
import asyncio
import importlib.util
import os

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from core.listing import resolve_order_by, sort_key_for
from models.schemas import (
    PIPELINE_STAGES, CandidatePortalProfile, PipelineAdd, PipelineStageUpdate,
)


@pytest.fixture
def patch_erase_lookup(monkeypatch):
    """routers.gdpr with its users lookup and erase_person() stubbed --
    same shape as tests/test_gdpr_erasure.py's patch_users_lookup, kept
    local so this file stands on its own."""
    def _patch(users_rows):
        import routers.gdpr as gdpr

        calls = []

        async def fake_fetch_all(sql, *args):
            return users_rows

        async def fake_erase_person(email, actor_id=None, reason="manual"):
            calls.append((email, actor_id, reason))
            return {"status": "complete", "email_hash": "x", "cv_files_deleted": [], "cv_files_failed": []}

        monkeypatch.setattr(gdpr, "fetch_all", fake_fetch_all)
        monkeypatch.setattr(gdpr, "erase_person", fake_erase_person)
        return gdpr, calls
    return _patch


def _load_migration(filename):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations", filename)
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── BV10: resolve_order_by ───────────────────────────────────────────────

_ALLOWED = {"created_at": "u.created_at", "full_name": "u.full_name"}


def test_no_sort_reproduces_the_route_default_exactly():
    """The whole backwards-compatibility claim of BV10 rests on this: a
    caller that passes neither parameter gets the byte-identical ORDER BY
    the route had before."""
    assert resolve_order_by(None, None, allowed=_ALLOWED, default="created_at DESC") == "created_at DESC"


def test_order_without_sort_leaves_the_default_alone():
    assert resolve_order_by(None, "asc", allowed=_ALLOWED, default="created_at DESC") == "created_at DESC"


def test_allowed_column_maps_to_its_sql_fragment_never_to_the_input():
    assert resolve_order_by("full_name", "asc", allowed=_ALLOWED, default="x") == "u.full_name ASC"
    assert resolve_order_by("full_name", "desc", allowed=_ALLOWED, default="x") == "u.full_name DESC"


def test_sort_defaults_to_ascending_when_order_is_omitted():
    assert resolve_order_by("full_name", None, allowed=_ALLOWED, default="x") == "u.full_name ASC"


def test_tiebreaker_is_appended_after_an_explicit_sort_only():
    assert resolve_order_by(
        "full_name", "asc", allowed=_ALLOWED, default="created_at DESC", tiebreaker="u.id DESC",
    ) == "u.full_name ASC, u.id DESC"
    assert resolve_order_by(
        None, None, allowed=_ALLOWED, default="created_at DESC", tiebreaker="u.id DESC",
    ) == "created_at DESC"


def test_tiebreaker_is_skipped_when_it_is_the_sort_column_itself():
    """security-audit LOW #3: "id ASC, id DESC" is a contradiction the
    second key can never be reached through -- it must not be emitted."""
    allowed = {"id": "id", "full_name": "u.full_name"}
    assert resolve_order_by("id", "asc", allowed=allowed, default="x", tiebreaker="id DESC") == "id ASC"
    assert resolve_order_by("id", "desc", allowed=allowed, default="x", tiebreaker="id DESC") == "id DESC"
    # a different column still gets it
    assert resolve_order_by(
        "full_name", "asc", allowed=allowed, default="x", tiebreaker="id DESC",
    ) == "u.full_name ASC, id DESC"


def test_route_tiebreakers_are_never_emitted_twice():
    """Every route allowlist that contains its own tiebreaker column must
    survive being sorted on exactly that column."""
    from routers.admin import _JOB_SORT_COLUMNS, _USER_SORT_COLUMNS
    from routers.placements import _PLACEMENT_SORT_COLUMNS

    for allowed, default, tiebreaker in (
        (_USER_SORT_COLUMNS, "created_at DESC", "id DESC"),
        (_JOB_SORT_COLUMNS, "j.created_at DESC", "j.id DESC"),
        (_PLACEMENT_SORT_COLUMNS, "created_at DESC", "id DESC"),
    ):
        clause = resolve_order_by("id", "asc", allowed=allowed, default=default, tiebreaker=tiebreaker)
        assert clause.count("id") == 1, clause


def test_column_outside_the_allowlist_is_422_and_never_reaches_sql():
    with pytest.raises(HTTPException) as exc:
        resolve_order_by("password_hash", None, allowed=_ALLOWED, default="x")
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "invalid_sort_column"
    assert exc.value.detail["allowed"] == ["created_at", "full_name"]


def test_a_sql_injection_shaped_sort_is_refused_like_any_other_unknown_column():
    with pytest.raises(HTTPException) as exc:
        resolve_order_by("created_at, (SELECT 1)", "asc", allowed=_ALLOWED, default="x")
    assert exc.value.status_code == 422


def test_order_outside_asc_desc_is_422():
    with pytest.raises(HTTPException) as exc:
        resolve_order_by("full_name", "sideways", allowed=_ALLOWED, default="x")
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "invalid_order_direction"


def test_order_direction_is_checked_even_without_a_sort_column():
    with pytest.raises(HTTPException):
        resolve_order_by(None, "sideways", allowed=_ALLOWED, default="x")


def test_sort_key_for_returns_the_row_key_not_sql():
    assert sort_key_for(None, allowed=_ALLOWED, default_key="created_at") == "created_at"
    assert sort_key_for("full_name", allowed=_ALLOWED, default_key="created_at") == "full_name"


def test_route_allowlists_are_closed_sets_of_plain_identifiers():
    """Every allowlist value is interpolated into SQL, so none of them may
    carry anything but an optionally-qualified column name."""
    import re

    from routers.admin import _CANDIDATE_SORT_COLUMNS, _JOB_SORT_COLUMNS, _USER_SORT_COLUMNS
    from routers.placements import _PLACEMENT_SORT_COLUMNS
    from routers.retention_admin import _REVIEW_SORT_COLUMNS

    identifier = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$")
    for allowlist in (_USER_SORT_COLUMNS, _JOB_SORT_COLUMNS, _CANDIDATE_SORT_COLUMNS,
                      _PLACEMENT_SORT_COLUMNS, _REVIEW_SORT_COLUMNS):
        assert allowlist, "an empty allowlist would make sort silently unusable"
        for key, sql in allowlist.items():
            assert identifier.match(sql), f"{key} -> {sql} is not a plain column reference"


def test_candidate_sort_columns_exist_in_both_merge_branches():
    """GET /candidates merges two SELECTs in Python; a sortable column
    that only one branch produces would sort one half against a missing
    key. Both branch SELECTs live in the same function source."""
    import inspect

    from routers import admin

    source = inspect.getsource(admin.list_all_candidates)
    branch_a, branch_b = source.split("Branch B", 1)
    for column in admin._CANDIDATE_SORT_COLUMNS:
        assert column in branch_a, f"{column} is not selected by branch A"
        assert column in branch_b, f"{column} is not selected by branch B"


def test_candidates_merge_uses_a_tiebreaker_both_branches_produce():
    """security-audit LOW #4: without one, two branches each cut their own
    offset+limit on an arbitrary tie order and a row can fall out of the
    page. The tiebreaker has to exist in both SELECTs."""
    import inspect

    from routers import admin

    assert admin._CANDIDATE_TIEBREAKER in admin._CANDIDATE_SORT_COLUMNS
    source = inspect.getsource(admin.list_all_candidates)
    branch_a, branch_b = source.split("Branch B", 1)
    assert admin._CANDIDATE_TIEBREAKER in branch_a
    assert admin._CANDIDATE_TIEBREAKER in branch_b


def test_merge_sort_key_orders_on_the_tiebreaker_within_a_tie():
    from routers.admin import _merge_sort_key

    rows = [
        {"full_name": "Same", "created_at": "2026-01-02"},
        {"full_name": "Same", "created_at": "2026-01-01"},
        {"full_name": "Other", "created_at": "2026-01-03"},
    ]
    ordered = sorted(rows, key=lambda r: _merge_sort_key(r, ("full_name", "created_at")))
    assert [r["created_at"] for r in ordered] == ["2026-01-03", "2026-01-01", "2026-01-02"]


def test_merge_sort_key_keeps_nulls_last_on_every_key():
    from routers.admin import _merge_sort_key

    rows = [
        {"full_name": None, "created_at": "2026-01-01"},
        {"full_name": "A", "created_at": None},
        {"full_name": "A", "created_at": "2026-01-01"},
    ]
    ordered = sorted(rows, key=lambda r: _merge_sort_key(r, ("full_name", "created_at")))
    assert ordered[0]["full_name"] == "A" and ordered[0]["created_at"] == "2026-01-01"
    assert ordered[-1]["full_name"] is None


# ── BV2: lockout columns on the user routes ──────────────────────────────

def test_user_select_carries_the_two_lockout_columns():
    from routers.admin import _USER_COLUMNS

    assert "failed_login_count" in _USER_COLUMNS
    assert "locked_until" in _USER_COLUMNS
    # and the pre-existing columns are untouched (additive, BV-wide rule)
    for column in ("id", "email", "full_name", "role", "is_verified", "created_at", "updated_at"):
        assert column in _USER_COLUMNS


def test_both_user_routes_read_the_same_column_list():
    import inspect

    from routers import admin

    for func in (admin.list_users, admin.get_user_detail):
        assert "_USER_COLUMNS" in inspect.getsource(func)


# ── BV4: consent fields on the candidate portal profile ──────────────────

def test_candidate_portal_profile_exposes_withdrawal_and_lawful_basis():
    fields = CandidatePortalProfile.model_fields
    assert "consent_withdrawn_at" in fields
    assert "lawful_basis" in fields
    # Optional with a None default -- a profile with no candidates row yet
    # must still validate.
    assert fields["consent_withdrawn_at"].default is None
    assert fields["lawful_basis"].default is None
    # The four WS-C.17 fields stay, unchanged.
    for field in ("consent_talentpool_at", "consent_talentpool_until", "consent_scope", "consent_source"):
        assert field in fields


def test_attach_talentpool_consent_seeds_and_reads_both_new_columns():
    import inspect

    from routers import candidate

    source = inspect.getsource(candidate._attach_talentpool_consent)
    assert 'profile["consent_withdrawn_at"] = None' in source
    assert 'profile["lawful_basis"] = None' in source
    assert "consent_withdrawn_at, lawful_basis" in source


# ── BV8: the canonical stage list at the API boundary ────────────────────

def test_the_seven_canonical_stages_in_spec_order():
    assert PIPELINE_STAGES == (
        "sourced", "new", "screening", "interview", "offer", "placed", "rejected",
    )


@pytest.mark.parametrize("stage", PIPELINE_STAGES)
def test_every_canonical_stage_is_accepted(stage):
    assert PipelineStageUpdate(stage=stage).stage == stage
    assert PipelineAdd(candidate_id=1, job_id=1, stage=stage).stage == stage


@pytest.mark.parametrize("stage", ["", "Screening", " interview", "interviewing", "contacted", "onbekend"])
def test_a_stage_outside_the_seven_is_refused(stage):
    with pytest.raises(ValidationError):
        PipelineStageUpdate(stage=stage)
    with pytest.raises(ValidationError):
        PipelineAdd(candidate_id=1, job_id=1, stage=stage)


def test_pipeline_add_still_defaults_to_sourced():
    assert PipelineAdd(candidate_id=1, job_id=1).stage == "sourced"


# ── BV8: migration 043's text ────────────────────────────────────────────

def test_043_normalises_before_it_constrains():
    mod = _load_migration("043_pipeline_stage_check.py")
    sql = mod.MIGRATION_SQL
    first_update = sql.index("UPDATE pipeline_entries")
    add_constraint = sql.index("ADD CONSTRAINT pipeline_entries_stage_check")
    assert first_update < add_constraint, "afwijkende waarden moeten vóór de CHECK genormaliseerd zijn"


def test_043_adds_the_constraint_as_not_valid_in_one_statement():
    mod = _load_migration("043_pipeline_stage_check.py")
    sql = mod.MIGRATION_SQL
    add_statements = [s for s in sql.split(";") if "ADD CONSTRAINT pipeline_entries_stage_check" in s]
    assert len(add_statements) == 1
    assert "NOT VALID" in add_statements[0]
    # VALIDATE is an owner step in the runbook, never part of the deploy.
    assert "VALIDATE CONSTRAINT" not in sql
    assert "VALIDATE CONSTRAINT" in mod.__doc__


def test_043_is_re_runnable_and_deletes_nothing():
    mod = _load_migration("043_pipeline_stage_check.py")
    sql = mod.MIGRATION_SQL
    assert "DROP CONSTRAINT IF EXISTS pipeline_entries_stage_check" in sql
    assert "DO $$" not in sql, "de runner splitst op ';' en kent geen DO-blok"
    assert "DELETE FROM" not in sql.upper()
    assert "DROP TABLE" not in sql.upper()
    assert "DROP COLUMN" not in sql.upper()


def test_043_constrains_exactly_the_seven_canonical_stages():
    mod = _load_migration("043_pipeline_stage_check.py")
    check = [s for s in mod.MIGRATION_SQL.split(";") if "ADD CONSTRAINT" in s][0]
    for stage in PIPELINE_STAGES:
        assert f"'{stage}'" in check
    assert check.count("'") == 2 * len(PIPELINE_STAGES)


def test_043_leaves_no_row_the_constraint_would_make_unwritable():
    """security-audit HIGH: a NOT VALID CHECK skips only the initial scan
    -- it still applies to every later INSERT and UPDATE, including one
    that does not touch `stage` at all (erase_person()'s
    `UPDATE pipeline_entries SET notes = NULL`). So the normalisation
    must leave nothing outside the seven."""
    mod = _load_migration("043_pipeline_stage_check.py")
    statements = [s.strip() for s in mod.MIGRATION_SQL.split(";") if s.strip()]
    catch_all = [s for s in statements if "SET stage = 'sourced'" in s and "NOT IN" in s]
    assert len(catch_all) == 1, "expected exactly one catch-all normalisation"
    for stage in PIPELINE_STAGES:
        assert f"'{stage}'" in catch_all[0], "the catch-all must spare every canonical value"
    assert "stage IS NOT NULL" in catch_all[0], "NULL satisfies the CHECK and must stay NULL"

    catch_all_idx = statements.index(catch_all[0])
    add_idx = next(i for i, s in enumerate(statements) if "ADD CONSTRAINT" in s)
    assert catch_all_idx < add_idx, "the catch-all must run before the constraint"
    specific = [i for i, s in enumerate(statements)
                if s.startswith("UPDATE") and "NOT IN" not in s and "TRIM(LOWER" not in s]
    assert specific and max(specific) < catch_all_idx, (
        "the specific mappings must run first, otherwise the catch-all flattens the progress they preserve"
    )


def test_043_explains_why_the_catch_all_writes_sourced():
    mod = _load_migration("043_pipeline_stage_check.py")
    assert "erase_person" in mod.__doc__, "the failure mode that forced the catch-all belongs in the file"
    assert "onschrijfbaar" in mod.__doc__


def test_043_documents_every_mapping_it_performs():
    """Each semantic UPDATE must name its source value in the docstring's
    mapping table -- the migration is the only place that rewrite is
    recorded, so an undocumented one would be invisible afterwards."""
    mod = _load_migration("043_pipeline_stage_check.py")
    for value in ("applied", "contacted", "active", "suggested", "interviewing",
                  "offered", "hired", "declined", "afgewezen"):
        assert f"'{value}'" in mod.MIGRATION_SQL, f"{value} is not mapped"
        assert value in mod.__doc__, f"{value} is mapped but not documented"
    # And the two deliberately-unmapped values are named as such.
    assert "inactive" in mod.__doc__


def test_043_never_maps_a_canonical_stage_onto_another_one():
    """A mapping that rewrites one of the seven would silently move real
    pipeline entries between stages."""
    mod = _load_migration("043_pipeline_stage_check.py")
    for statement in mod.MIGRATION_SQL.split(";"):
        if not statement.strip().startswith("UPDATE") or "TRIM(LOWER" in statement:
            continue
        if "NOT IN" in statement:
            # The catch-all names all seven precisely to exclude them --
            # covered by its own test above.
            continue
        where = statement.split("WHERE", 1)[1]
        for stage in PIPELINE_STAGES:
            assert f"'{stage}'" not in where, f"{stage} is a canonical value and must never be rewritten"


# ── BV9: the erase confirmation is the address ───────────────────────────

def test_erase_confirm_defaults_to_a_value_that_can_never_confirm():
    """security-audit MEDIUM: `confirm` must not be a required field --
    FastAPI's own 422 for a missing one echoes the whole request body,
    e-mail address included. The default has to be something no address
    can equal, so the route's own check still refuses it."""
    import routers.gdpr as gdpr

    assert gdpr.AdminEraseRequest.model_fields["confirm"].default == ""


def test_erase_refuses_an_omitted_confirmation(patch_erase_lookup):
    gdpr, calls = patch_erase_lookup([])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(gdpr.admin_erase_person(
            gdpr.AdminEraseRequest(email="target@example.com"),
            current_user={"id": 1, "role": "admin"},
        ))
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "erase_confirm_must_match_email"
    assert calls == []


def test_erase_refuses_a_confirm_that_is_not_the_address(patch_erase_lookup):
    gdpr, calls = patch_erase_lookup([])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(gdpr.admin_erase_person(
            gdpr.AdminEraseRequest(email="target@example.com", confirm="typo@example.com"),
            current_user={"id": 1, "role": "admin"},
        ))
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "erase_confirm_must_match_email"
    assert calls == [], "erase_person must never run on a mismatched confirmation"


def test_erase_refusal_echoes_neither_address(patch_erase_lookup):
    """A 422 body and whatever logs it travels through must not become a
    second copy of the address a mistyping admin just entered."""
    gdpr, _ = patch_erase_lookup([])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(gdpr.admin_erase_person(
            gdpr.AdminEraseRequest(email="target@example.com", confirm="typo@example.com"),
            current_user={"id": 1, "role": "admin"},
        ))
    rendered = str(exc.value.detail)
    assert "typo@example.com" not in rendered
    assert "target@example.com" not in rendered


def test_erase_accepts_the_address_case_and_space_insensitively(patch_erase_lookup):
    gdpr, calls = patch_erase_lookup([])
    result = asyncio.run(gdpr.admin_erase_person(
        gdpr.AdminEraseRequest(email="target@example.com", confirm="  TARGET@Example.com "),
        current_user={"id": 1, "role": "admin"},
    ))
    assert result["status"] == "complete"
    assert len(calls) == 1


def test_erase_confirmation_is_checked_before_any_lookup(patch_erase_lookup):
    """Refusing first means a wrong confirmation cannot be used to probe
    whether an address belongs to an account."""
    gdpr, _ = patch_erase_lookup([{"id": 5, "role": "admin"}])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(gdpr.admin_erase_person(
            gdpr.AdminEraseRequest(email="target@example.com", confirm="other@example.com"),
            current_user={"id": 1, "role": "admin"},
        ))
    assert exc.value.status_code == 422, "the admin/self 409 must not preempt the confirmation check"


def test_admin_self_confirmation_is_its_own_field():
    import routers.gdpr as gdpr

    fields = gdpr.AdminEraseRequest.model_fields
    assert "confirm_admin_or_self" in fields
    assert fields["confirm_admin_or_self"].default is False
    assert fields["confirm"].annotation is str


# ── BV1/BV5/BV6: response shapes that a pager depends on ─────────────────

def test_admin_pipeline_route_is_admin_only_and_returns_a_total():
    import inspect

    from routers import admin

    source = inspect.getsource(admin.admin_list_pipeline)
    assert 'require_role("admin")' in source
    assert '"total": total' in source
    assert '"client_id"' not in source, "client_id comes from pe.* -- no separate projection needed"
    # The same consent gate as the client route, applied in Python.
    assert "consent_spec_presentation_at" in source
    assert 'item.pop("full_name", None)' in source
    assert 'item["skills"] = item.get("skills") or []' in source


def test_suppression_list_returns_total_next_to_items():
    import inspect

    from routers import gdpr

    source = inspect.getsource(gdpr.list_suppression)
    assert "SELECT COUNT(*) FROM suppression_list" in source
    assert '"total": total' in source
    # Still hashes and domains only.
    assert "email_hash, email_domain, reason, created_at" in source


def test_retention_review_limit_has_no_default_so_the_bulk_flow_keeps_its_full_set():
    import inspect

    from routers import retention_admin

    signature = inspect.signature(retention_admin.list_review_items)
    limit_default = signature.parameters["limit"].default
    assert limit_default.default is None, "a default page size would silently truncate the bulk flow's set"
    source = inspect.getsource(retention_admin.list_review_items)
    assert "expected_count" in source, "the reason for the None default belongs in the docstring"


def test_pipeline_history_joins_the_actor_name_without_dropping_rows():
    import inspect

    from routers import admin

    source = inspect.getsource(admin.admin_get_pipeline_stage_history)
    assert "changed_by_name" in source
    assert "LEFT JOIN users" in source, "an inner join would hide history written by a deleted account"
    assert "u.email" not in source


def test_referral_conflicts_carry_a_machine_readable_code():
    import inspect

    from routers import admin

    source = inspect.getsource(admin.admin_create_referral)
    assert '"referral_email_suppressed"' in source
    assert '"referral_candidate_exists"' in source
    assert '"candidate_id": existing["id"]' in source
