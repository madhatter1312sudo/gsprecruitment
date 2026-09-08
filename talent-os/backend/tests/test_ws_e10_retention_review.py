"""
Unit tests for WS-E.10 (owner decision, retention-kolommen branch, fifth
round): the monthly retention review queue and its approve/reject
endpoints (routers/retention_admin.py). No DB/network needed -- a tiny
in-memory fake stands in for retention_review_items, same monkeypatch
style as tests/test_retention.py's _Recorder.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from fastapi import HTTPException


class _FakeItemsDB:
    """Backs exactly the handful of SQL shapes routers/retention_admin.py
    issues against retention_review_items/retention_review_decisions/
    audit_log -- not a general SQL engine, just enough to drive the
    approve/reject code paths end to end."""

    def __init__(self, items: dict):
        self.items = items  # id -> dict
        self.decisions = []
        self.audit_log = []

    async def fetch_one(self, sql, *args):
        if "FROM retention_review_items WHERE id" in sql:
            return dict(self.items[args[0]]) if args[0] in self.items else None
        raise AssertionError(f"unexpected fetch_one: {sql}")

    async def fetch_all(self, sql, *args):
        if "FROM retention_review_items WHERE category" in sql:
            category = args[0]
            return [
                {"id": i} for i, row in self.items.items()
                if row["category"] == category and row["status"] == "pending"
            ]
        raise AssertionError(f"unexpected fetch_all: {sql}")

    async def execute(self, sql, *args):
        if sql.strip().startswith("UPDATE retention_review_items SET status = 'purged'"):
            self.items[args[0]]["status"] = "purged"
            self.items[args[0]]["purged_at"] = "now"
        elif sql.strip().startswith("UPDATE retention_review_items SET status = 'rejected'"):
            self.items[args[0]]["status"] = "rejected"
        elif sql.strip().startswith("UPDATE retention_review_items SET status = 'no_longer_eligible'") and "WHERE id" in sql:
            self.items[args[0]]["status"] = "no_longer_eligible"
        elif sql.strip().startswith("INSERT INTO retention_review_decisions"):
            self.decisions.append({"review_item_id": args[0], "decision": args[1], "actor_id": args[2], "note": args[3]})
        elif sql.strip().startswith("INSERT INTO audit_log"):
            self.audit_log.append(args)
        elif sql.strip().startswith("DELETE FROM"):
            pass  # the hard_delete branch -- nothing to assert on the fake target table itself
        else:
            raise AssertionError(f"unexpected execute: {sql}")
        return "OK"


def _install(monkeypatch, db: _FakeItemsDB, eligible: bool = True):
    from routers import retention_admin

    monkeypatch.setattr(retention_admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(retention_admin, "fetch_all", db.fetch_all)
    monkeypatch.setattr(retention_admin, "execute", db.execute)

    async def _fake_eligible(item):
        return eligible

    monkeypatch.setattr(retention_admin, "_is_still_eligible", _fake_eligible)
    return retention_admin


def _pending_item(**overrides):
    item = {
        "id": 1, "category": "rejected_applicant", "subject_table": "candidates",
        "subject_id": 42, "email": "person@example.com", "action": "anonymise",
        "term_expired_at": None, "signal_missing_nl": "geen match", "status": "pending",
    }
    item.update(overrides)
    return item


# ── approve ───────────────────────────────────────────────────────────

def test_approve_requires_confirm(monkeypatch):
    retention_admin = _install(monkeypatch, _FakeItemsDB({1: _pending_item()}))
    payload = retention_admin.ReviewDecisionRequest(confirm=None)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 409


def test_approve_refuses_a_confirm_value_other_than_approve(monkeypatch):
    retention_admin = _install(monkeypatch, _FakeItemsDB({1: _pending_item()}))
    payload = retention_admin.ReviewDecisionRequest(confirm="yes please")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 409


def test_approve_unknown_item_is_404(monkeypatch):
    retention_admin = _install(monkeypatch, _FakeItemsDB({}))
    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 404


def test_approve_anonymises_and_records_decision_and_audit(monkeypatch):
    db = _FakeItemsDB({1: _pending_item()})
    retention_admin = _install(monkeypatch, db)

    erased = []

    async def _fake_erase_person(email, actor_id=None, reason="manual"):
        erased.append((email, actor_id, reason))
        return {"status": "complete"}

    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person)

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE", note="klopt")
    result = asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))

    assert result == {"id": 1, "status": "purged"}
    assert db.items[1]["status"] == "purged"
    assert erased == [("person@example.com", 9, "retention_purge:rejected_applicant")]
    assert db.decisions == [{"review_item_id": 1, "decision": "approved", "actor_id": 9, "note": "klopt"}]
    assert len(db.audit_log) == 1
    assert db.audit_log[0][0] == "retention_review_approve"
    changes = json.loads(db.audit_log[0][4])
    assert changes == {"category": "rejected_applicant", "action": "anonymise"}
    # never the e-mail address or any other PII, per commit 72b4bcd's rule
    assert "person@example.com" not in json.dumps(db.audit_log)


def test_approve_hard_deletes_when_action_is_hard_delete(monkeypatch):
    item = _pending_item(category="leads_quiz", subject_table="quiz_submissions", action="hard_delete", email=None)
    db = _FakeItemsDB({1: item})
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    result = asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))

    assert result == {"id": 1, "status": "purged"}
    assert db.items[1]["status"] == "purged"


def test_approve_refuses_and_marks_no_longer_eligible_when_a_protective_signal_appeared(monkeypatch):
    db = _FakeItemsDB({1: _pending_item()})
    retention_admin = _install(monkeypatch, db, eligible=False)

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 409
    assert db.items[1]["status"] == "no_longer_eligible"
    assert db.decisions == []  # never recorded as an actual decision -- nothing was approved


def test_approve_refuses_an_already_purged_item(monkeypatch):
    db = _FakeItemsDB({1: _pending_item(status="purged")})
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 409


def test_approve_can_act_on_a_previously_rejected_item(monkeypatch):
    """The owner changing their mind on a previously-rejected person is
    allowed -- 'rejected' is one of the statuses approve accepts, not
    only 'pending'."""
    db = _FakeItemsDB({1: _pending_item(status="rejected")})
    retention_admin = _install(monkeypatch, db)

    async def _fake_erase_person(email, actor_id=None, reason="manual"):
        return {"status": "complete"}

    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person)

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    result = asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))
    assert result == {"id": 1, "status": "purged"}


# ── reject ────────────────────────────────────────────────────────────

def test_reject_needs_no_confirm(monkeypatch):
    db = _FakeItemsDB({1: _pending_item()})
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewDecisionRequest(confirm=None, note="nog in gesprek")
    result = asyncio.run(retention_admin.reject_review_item(1, payload, current_user={"id": 9, "role": "admin"}))

    assert result == {"id": 1, "status": "rejected"}
    assert db.items[1]["status"] == "rejected"
    assert db.decisions == [{"review_item_id": 1, "decision": "rejected", "actor_id": 9, "note": "nog in gesprek"}]


def test_reject_refuses_an_already_purged_item(monkeypatch):
    db = _FakeItemsDB({1: _pending_item(status="purged")})
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewDecisionRequest()
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.reject_review_item(1, payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 409


# ── bulk ──────────────────────────────────────────────────────────────

def test_bulk_reject_by_category_needs_no_confirm(monkeypatch):
    db = _FakeItemsDB({
        1: _pending_item(id=1), 2: _pending_item(id=2, subject_id=43),
    })
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewBulkRequest(decision="rejected", category="rejected_applicant")
    result = asyncio.run(retention_admin.bulk_review_decision(payload, current_user={"id": 9, "role": "admin"}))

    assert {r["status"] for r in result["results"]} == {"rejected"}
    assert db.items[1]["status"] == "rejected"
    assert db.items[2]["status"] == "rejected"


def test_bulk_approve_requires_confirm(monkeypatch):
    db = _FakeItemsDB({1: _pending_item()})
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewBulkRequest(decision="approved", ids=[1])
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.bulk_review_decision(payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 409


def test_bulk_approve_by_ids_with_confirm(monkeypatch):
    db = _FakeItemsDB({1: _pending_item()})
    retention_admin = _install(monkeypatch, db)

    async def _fake_erase_person(email, actor_id=None, reason="manual"):
        return {"status": "complete"}

    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person)

    payload = retention_admin.ReviewBulkRequest(decision="approved", ids=[1], confirm="APPROVE")
    result = asyncio.run(retention_admin.bulk_review_decision(payload, current_user={"id": 9, "role": "admin"}))

    assert result["results"] == [{"id": 1, "status": "purged"}]
    assert db.items[1]["status"] == "purged"


def test_bulk_requires_either_ids_or_category(monkeypatch):
    db = _FakeItemsDB({})
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewBulkRequest(decision="rejected")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.bulk_review_decision(payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 422


# ── summary: counts only, no PII ─────────────────────────────────────

def test_review_summary_returns_counts_only_no_pii(monkeypatch):
    from routers import retention_admin

    async def _fake_fetch_all(sql, *args):
        assert "GROUP BY category, status" in sql
        return [
            {"category": "rejected_applicant", "status": "pending", "n": 3},
            {"category": "leads_quiz", "status": "purged", "n": 1},
        ]

    monkeypatch.setattr(retention_admin, "fetch_all", _fake_fetch_all)
    result = asyncio.run(retention_admin.review_summary(current_user={"id": 9, "role": "admin"}))
    assert result["pending_total"] == 3
    assert "@" not in json.dumps(result)  # no e-mail addresses ever appear here
