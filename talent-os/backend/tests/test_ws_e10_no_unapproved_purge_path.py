"""
WS-E.10 (owner decision, retention-kolommen branch, fifth round) --
structural test, in the spirit of tests/test_retention.py's
test_scheduler_reuses_the_shared_retention_selectors_not_a_local_copy and
tests/integration/test_retention_guards.py's own docstring: don't just
check today's behaviour, make a later regression that reopens a direct
purge path fail here instead of in production.

The owner's decision was specific: retention no longer deletes/anonymises
anything by itself. This file asserts that structurally, from three
angles, so a regression on any of them fails loudly:

  1. The functions that used to purge directly (run_retention_purge's
     dry_run=False branch, retention_purge_job, every _purge_* helper)
     are gone from services/scheduler.py, not merely unused.
  2. Both admin endpoints that used to accept a `confirm` string and then
     purge (POST .../retention/run, POST .../apollo-pool/purge) refuse
     EVERY dry_run=false call, whatever the confirm/body carries -- there
     is no longer a magic string that makes either one write.
  3. erase_person() and a DELETE against a retention-table subject table
     are reachable from exactly one function in routers/retention_admin.py
     (_approve_one) -- a source-level check, so a future change that adds
     a second call site (even inside a differently-named function) fails
     here instead of only being caught by review.
"""
import ast
import asyncio
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi import HTTPException


def test_scheduler_has_no_direct_purge_functions_left():
    import services.scheduler as scheduler

    for name in (
        "run_retention_purge", "retention_purge_job", "_category_result",
        "_purge_sourced_no_response", "_purge_talentpool_expired",
        "_purge_rejected_applicants", "_purge_prospect_responding",
        "_purge_portal_account_inactive", "_purge_prospect_no_response",
        "_purge_leads_quiz",
    ):
        assert not hasattr(scheduler, name), (
            f"scheduler.{name} exists again -- this was the direct-purge path WS-E.10 removed"
        )


def test_generate_retention_review_source_never_calls_erase_person_or_deletes():
    """Source-level check, not just a monkeypatched-call assertion: the
    monthly queue-generation function's own source text must never
    mention erase_person or a DELETE against a subject table -- even one
    added behind a condition that today's tests don't happen to exercise."""
    import services.scheduler as scheduler

    src = inspect.getsource(scheduler.generate_retention_review)
    assert "erase_person" not in src
    assert "DELETE FROM" not in src


@pytest.mark.parametrize("confirm", [None, "PURGE", "APPROVE", "yes"])
def test_run_retention_endpoint_never_purges_whatever_confirm_carries(confirm, monkeypatch):
    from routers import retention_admin

    calls = []

    async def _fail_if_called(*args, **kwargs):
        calls.append(args)
        raise AssertionError("must never be reached")

    monkeypatch.setattr(retention_admin.scheduler_service, "_live_rows_for_category", _fail_if_called)
    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _fail_if_called)

    payload = retention_admin.RetentionRunRequest(dry_run=False, confirm=confirm)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.run_retention(payload, current_user={"id": 1, "role": "admin"}))
    assert exc_info.value.status_code == 410
    assert calls == []  # refused before touching the DB at all


@pytest.mark.parametrize("confirm", [None, "DELETE APOLLO POOL", "APPROVE", "yes"])
def test_apollo_pool_purge_endpoint_never_purges_whatever_confirm_carries(confirm, monkeypatch):
    from routers import retention_admin

    async def _fake_fetch_all(sql, *args):
        return []

    execute_calls = []

    async def _tracking_execute(sql, *args):
        execute_calls.append(sql)
        return "OK"

    monkeypatch.setattr(retention_admin, "fetch_all", _fake_fetch_all)
    monkeypatch.setattr(retention_admin, "execute", _tracking_execute)

    payload = retention_admin.ApolloPoolPurgeRequest(dry_run=False, confirm=confirm)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.purge_apollo_pool(payload, current_user={"id": 1, "role": "admin"}))
    assert exc_info.value.status_code == 410
    assert execute_calls == []


def _functions_calling(module, needle: str) -> set:
    """Every top-level function in `module` whose own source text contains
    `needle` -- a source scan, not an execution trace, so it also catches
    a call inside a branch no test happens to hit."""
    hits = set()
    for name, obj in vars(module).items():
        if inspect.isfunction(obj) and inspect.getmodule(obj) is module:
            try:
                src = inspect.getsource(obj)
            except (OSError, TypeError):
                continue
            if needle in src:
                hits.add(name)
    return hits


def test_erase_person_is_only_ever_called_from_the_one_approved_purge_path():
    """erase_person is imported locally (inside the function body, not at
    module level) everywhere it's used in this backend -- a source-text
    scan for the literal call therefore finds every real call site.
    routers/retention_admin.py must have exactly one: _approve_one()."""
    import routers.retention_admin as retention_admin

    hits = _functions_calling(retention_admin, "erase_person(")
    assert hits == {"_approve_one"}, (
        f"erase_person( is called from {hits} in routers/retention_admin.py -- expected only _approve_one"
    )


def test_delete_from_a_subject_table_is_only_ever_issued_from_the_one_approved_purge_path():
    """Same check for the hard_delete branch's DELETE statement -- must
    appear in exactly one function's source, and it must be an f-string
    against the closed _HARD_DELETE_TABLES whitelist, not a literal
    table name that could silently diverge from that whitelist."""
    import routers.retention_admin as retention_admin

    hits = _functions_calling(retention_admin, "DELETE FROM")
    assert hits == {"_approve_one"}, (
        f"a DELETE FROM is issued from {hits} in routers/retention_admin.py -- expected only _approve_one"
    )
    src = inspect.getsource(retention_admin._approve_one)
    assert "_HARD_DELETE_TABLES" in src


def test_apollo_pool_purge_module_source_has_no_reachable_delete_or_erase():
    """Belt-and-braces on top of the two checks above: the apollo-pool
    endpoint function itself, specifically, must not contain either call
    -- catches a regression that adds a *second*, differently-shaped
    delete path back into that one function instead of a new function."""
    import routers.retention_admin as retention_admin

    src = inspect.getsource(retention_admin.purge_apollo_pool)
    assert "erase_person" not in src
    assert "DELETE FROM" not in src
