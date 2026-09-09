"""
Unit tests for WS-4 "vacatures met anonieme opdrachtgever"
(migrations/037_pool_vacancies_consent_sources.py). Pure static/model
checks and monkeypatched-DB checks -- no real Postgres needed, same style
as tests/test_ws_c15_job_orders.py and tests/test_draft_refused_counter.py.
See tests/integration/test_ws4_anonymous_vacancies_integration.py for the
real-Postgres coverage of deleted_at filtering, anonymous_client, the
talentpool-apply match/applied_job flow, and analytics.
"""
import asyncio
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from pydantic import ValidationError

from models.schemas import AdminJobUpdate, JobOrderUpdate

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(BACKEND_ROOT, "migrations")


def _load_migration(fname):
    path = os.path.join(MIGRATIONS_DIR, fname)
    spec = importlib.util.spec_from_file_location(f"_migration_{fname}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, MIGRATIONS_DIR)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(MIGRATIONS_DIR)
    return mod


# ── Migration 037: text-level checks (real-DB idempotency is proven ─────
#    separately, see the PR description / manual verification) ──────────

def test_migration_037_is_idempotent_statement_shapes_only():
    """Every statement is ADD COLUMN IF NOT EXISTS / DROP CONSTRAINT IF
    EXISTS / CREATE INDEX IF NOT EXISTS / an idempotent UPDATE or a
    guarded INSERT ... WHERE NOT EXISTS -- no DO $$ ... END $$ block
    (migrations/_runner.py splits on a literal ';')."""
    mod = _load_migration("037_pool_vacancies_consent_sources.py")
    sql = mod.MIGRATION_SQL
    assert "DO $$" not in sql
    assert "ADD COLUMN IF NOT EXISTS is_internal" in sql
    assert "ADD COLUMN IF NOT EXISTS job_id" in sql
    assert "ADD COLUMN IF NOT EXISTS job_alerts" in sql
    assert "DROP CONSTRAINT IF EXISTS" in sql
    assert sql.count("DROP CONSTRAINT IF EXISTS") == 4  # 2 old-name + 2 new-name drops
    assert "WHERE NOT EXISTS" in sql  # second internal client row, guarded insert
    assert "CREATE INDEX IF NOT EXISTS" in sql


def test_migration_037_backfills_is_internal_on_gsp_talent_pool():
    mod = _load_migration("037_pool_vacancies_consent_sources.py")
    sql = mod.MIGRATION_SQL
    assert "UPDATE clients SET is_internal = true WHERE company_name = 'GSP Talent Pool'" in sql


def test_migration_037_creates_the_anonymous_client_row_guarded():
    mod = _load_migration("037_pool_vacancies_consent_sources.py")
    sql = mod.MIGRATION_SQL
    assert "GSP Recruitment (anonieme opdrachtgever)" in sql
    assert "gsprecruitment.nl" in sql


def test_migration_037_widens_both_consent_source_checks_with_vacancy_apply_and_referral():
    mod = _load_migration("037_pool_vacancies_consent_sources.py")
    sql = mod.MIGRATION_SQL
    assert "chk_candidates_consent_source" in sql
    assert "chk_talentpool_optin_requests_source" in sql
    assert "'vacancy_apply'" in sql
    assert "'referral'" in sql
    # explicit constraint names (never left auto-named)
    assert "ADD CONSTRAINT chk_candidates_consent_source" in sql
    assert "ADD CONSTRAINT chk_talentpool_optin_requests_source" in sql


def test_migration_037_never_creates_a_unique_index():
    mod = _load_migration("037_pool_vacancies_consent_sources.py")
    assert "CREATE UNIQUE INDEX" not in mod.MIGRATION_SQL.upper()


def test_migration_037_talentpool_job_id_fk_is_set_null_on_delete():
    """The opt-in request (the consent evidence) must survive the job
    order being deleted later -- same reasoning as migrations/029's
    nullable FKs."""
    mod = _load_migration("037_pool_vacancies_consent_sources.py")
    sql = mod.MIGRATION_SQL
    assert "REFERENCES job_orders(id) ON DELETE SET NULL" in sql


# ── routers/jobs.py: shared public projection ────────────────────────────

def test_public_job_where_filters_open_non_demo_non_deleted():
    from routers.jobs import PUBLIC_JOB_WHERE
    assert "j.status = 'open'" in PUBLIC_JOB_WHERE
    assert "j.is_demo = false" in PUBLIC_JOB_WHERE
    assert "j.deleted_at IS NULL" in PUBLIC_JOB_WHERE


def test_public_job_from_joins_clients_for_anonymous_client():
    from routers.jobs import PUBLIC_JOB_FROM
    assert "LEFT JOIN clients cl ON cl.id = j.client_id" in PUBLIC_JOB_FROM


def test_list_and_detail_share_the_same_where_and_column_projection():
    """The whole point of PUBLIC_JOB_COLUMNS/PUBLIC_JOB_WHERE/PUBLIC_JOB_FROM
    being shared module-level constants is that list_public_jobs and
    get_public_job can never drift apart on what a "job" looks like."""
    import inspect
    import routers.jobs as jobs_router
    list_src = inspect.getsource(jobs_router.list_public_jobs)
    detail_src = inspect.getsource(jobs_router.get_public_job)
    for token in ("PUBLIC_JOB_COLUMNS", "PUBLIC_JOB_FROM", "PUBLIC_JOB_WHERE"):
        assert token in list_src
        assert token in detail_src


def test_get_public_job_route_exists_under_the_public_jobs_router():
    from routers.jobs import public_jobs_router
    paths = {r.path for r in public_jobs_router.routes}
    assert "/api/public/jobs/{job_id}" in paths


# ── JobOrderStatus Literal (JobOrderUpdate + AdminJobUpdate) ─────────────

@pytest.mark.parametrize("value", ["draft", "open", "paused", "closed", "filled", "deleted"])
def test_job_order_update_accepts_each_known_status(value):
    assert JobOrderUpdate(status=value).status == value


@pytest.mark.parametrize("value", ["draft", "open", "paused", "closed", "filled", "deleted"])
def test_admin_job_update_accepts_each_known_status(value):
    assert AdminJobUpdate(status=value).status == value


def test_job_order_update_rejects_unknown_status():
    with pytest.raises(ValidationError):
        JobOrderUpdate(status="published")


def test_admin_job_update_rejects_unknown_status():
    with pytest.raises(ValidationError):
        AdminJobUpdate(status="published")


def test_job_order_update_status_defaults_to_none():
    assert JobOrderUpdate().status is None


# ── models/schemas.py: TalentpoolOptinRequest job_id / job_alerts ────────

def test_talentpool_optin_request_job_id_and_job_alerts_default():
    from models.schemas import TalentpoolOptinRequest
    req = TalentpoolOptinRequest(email="a@example.com", consent=True, scope="matching_only", source="blog_cta")
    assert req.job_id is None
    assert req.job_alerts is False


def test_talentpool_optin_request_accepts_job_id_and_job_alerts():
    from models.schemas import TalentpoolOptinRequest
    req = TalentpoolOptinRequest(
        email="a@example.com", consent=True, scope="matching_only", source="vacancy_apply",
        job_id=42, job_alerts=True,
    )
    assert req.job_id == 42
    assert req.job_alerts is True


# ── routers/clients_admin.py: is_internal projected ───────────────────────

def test_clients_admin_list_query_selects_is_internal():
    import inspect
    import routers.clients_admin as clients_admin
    src = inspect.getsource(clients_admin.list_clients)
    assert "c.is_internal" in src


def test_clients_admin_detail_query_selects_is_internal():
    import inspect
    import routers.clients_admin as clients_admin
    src = inspect.getsource(clients_admin.get_client_detail)
    assert "c.is_internal" in src


def test_clients_admin_row_to_list_item_includes_is_internal():
    from routers.clients_admin import _row_to_list_item
    row = {
        "id": 1, "company_name": "Acme", "erkend_referent": "ja",
        "open_job_count": 0, "created_at": "2026-01-01T00:00:00Z", "is_internal": True,
    }
    assert _row_to_list_item(row)["is_internal"] is True


# ── routers/admin.py analytics: excludes internal clients ────────────────

def test_admin_analytics_excludes_internal_clients_from_job_and_client_counts():
    import inspect
    import routers.admin as admin_router
    src = inspect.getsource(admin_router.get_platform_analytics)
    assert "cl.is_internal = false" in src
    assert "is_internal = false" in src  # the bare clients-table COUNT


# ── services/scheduler.py draft_outreach: anonymises internal-client jobs ─

def test_draft_outreach_anonymises_job_company_for_internal_client(monkeypatch):
    from services import scheduler

    row = {
        "candidate_id": 1, "job_id": 200, "match_score": 90,
        "full_name": "Jane Doe", "email": "jane@example.com",
        "current_company": "Acme", "job_title": "Embedded Engineer",
        "job_description": "C++ / FreeRTOS", "job_company": "GSP Recruitment (anonieme opdrachtgever)",
        "job_client_internal": True,
    }

    async def fake_flag_enabled(key):
        return True

    async def fake_fetch_all(query, *args, **kwargs):
        return [row]

    captured = {}

    async def fake_draft_email(target, context, language="nl"):
        captured.update(context)
        return {"subject": "Hallo", "body": "Beste, ..."}

    async def fake_execute(query, *args, **kwargs):
        pass

    monkeypatch.setattr(scheduler, "_flag_enabled", fake_flag_enabled)
    monkeypatch.setattr(scheduler, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(scheduler, "execute", fake_execute)
    monkeypatch.setattr(scheduler.outreach_ai, "draft_email", fake_draft_email)

    result = asyncio.run(scheduler.draft_outreach())

    assert result["drafted"] == 1
    assert captured["job_company"] == "anonieme opdrachtgever"
    assert captured["anonymous_client"] is True


def test_draft_outreach_leaves_a_named_client_untouched(monkeypatch):
    from services import scheduler

    row = {
        "candidate_id": 1, "job_id": 201, "match_score": 90,
        "full_name": "Jane Doe", "email": "jane@example.com",
        "current_company": "Acme", "job_title": "Embedded Engineer",
        "job_description": "C++ / FreeRTOS", "job_company": "Acme B.V.",
        "job_client_internal": False,
    }

    async def fake_flag_enabled(key):
        return True

    async def fake_fetch_all(query, *args, **kwargs):
        return [row]

    captured = {}

    async def fake_draft_email(target, context, language="nl"):
        captured.update(context)
        return {"subject": "Hallo", "body": "Beste, ..."}

    async def fake_execute(query, *args, **kwargs):
        pass

    monkeypatch.setattr(scheduler, "_flag_enabled", fake_flag_enabled)
    monkeypatch.setattr(scheduler, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(scheduler, "execute", fake_execute)
    monkeypatch.setattr(scheduler.outreach_ai, "draft_email", fake_draft_email)

    asyncio.run(scheduler.draft_outreach())

    assert captured["job_company"] == "Acme B.V."
    assert captured["anonymous_client"] is False


# ── services/outreach_ai.py: _build_user_prompt anonymity line ───────────

def test_build_user_prompt_adds_anonymity_instruction_when_flagged():
    from services.outreach_ai import _build_user_prompt
    prompt = _build_user_prompt(
        target={"name": "Jane", "company": "Acme"},
        context={"job_title": "Embedded Engineer", "job_company": "anonieme opdrachtgever",
                 "anonymous_client": True},
        language="nl",
    )
    assert "anonymous by design" in prompt
    assert "do not name it" in prompt.lower()


def test_build_user_prompt_omits_anonymity_instruction_when_not_flagged():
    from services.outreach_ai import _build_user_prompt
    prompt = _build_user_prompt(
        target={"name": "Jane", "company": "Acme"},
        context={"job_title": "Embedded Engineer", "job_company": "Acme B.V."},
        language="nl",
    )
    assert "anonymous by design" not in prompt


# ── scripts/seed_pool_vacancies.py: structural checks ─────────────────────

def _load_seed_script():
    path = os.path.join(BACKEND_ROOT, "scripts", "seed_pool_vacancies.py")
    spec = importlib.util.spec_from_file_location("_seed_pool_vacancies", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seed_script_targets_the_anonymous_internal_client():
    mod = _load_seed_script()
    assert mod.INTERNAL_CLIENT_NAME == "GSP Recruitment (anonieme opdrachtgever)"


def test_seed_script_job_fields_match_admin_job_create_public_facing_fields():
    """No client_id, no status, no slug -- those are supplied by the
    script (client_id/status) or don't exist on job_orders (slug)."""
    mod = _load_seed_script()
    assert "client_id" not in mod.JOB_FIELDS
    assert "status" not in mod.JOB_FIELDS
    assert "slug" not in mod.JOB_FIELDS
    for expected in ("title", "seniority", "employment_type", "sponsorship_possible", "company_display"):
        assert expected in mod.JOB_FIELDS


def test_seed_script_apply_flag_defaults_to_dry_run(monkeypatch):
    mod = _load_seed_script()
    captured = {}

    async def fake_run(apply):
        captured["apply"] = apply
        return 0

    monkeypatch.setattr(mod, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["seed_pool_vacancies.py"])
    mod.main()
    assert captured["apply"] is False


def test_seed_script_apply_flag_true_when_passed(monkeypatch):
    mod = _load_seed_script()
    captured = {}

    async def fake_run(apply):
        captured["apply"] = apply
        return 0

    monkeypatch.setattr(mod, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["seed_pool_vacancies.py", "--apply"])
    mod.main()
    assert captured["apply"] is True
