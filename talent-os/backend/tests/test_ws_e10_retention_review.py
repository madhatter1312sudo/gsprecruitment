"""
Unit tests for WS-E.10 (owner decision): the monthly retention review
queue and its approve/reject endpoints (routers/retention_admin.py). No
DB/network needed -- a tiny in-memory fake stands in for
retention_review_items/retention_review_decisions/audit_log, plus a fake
pool/connection for the transactional final write, same monkeypatch style
as tests/test_retention.py's _Recorder.
"""
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from fastapi import HTTPException


class _FakeConn:
    """Stands in for the asyncpg connection _approve_one() holds for its
    final transactional write -- routes execute() back through the same
    fake DB every other call in this file goes through, so both paths
    (module-level execute() and conn.execute()) mutate the same state."""

    def __init__(self, db):
        self.db = db

    async def execute(self, sql, *args):
        return await self.db.execute(sql, *args)

    def transaction(self):
        return _FakeTransaction()


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False  # never swallow an exception


class _FakeAcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, db):
        self.db = db

    def acquire(self):
        return _FakeAcquireCtx(_FakeConn(self.db))


_EMAIL_COL_RE = re.compile(r"SELECT (\w+) AS email FROM (\w+) WHERE id = \$1")


class _FakeItemsDB:
    """Backs exactly the handful of SQL shapes routers/retention_admin.py
    issues against retention_review_items/retention_review_decisions/
    audit_log/candidates/users -- not a general SQL engine, just enough to
    drive the approve/reject code paths end to end.

    subject_emails: {(subject_table, subject_id): current_email} -- what
    _current_subject_email() reads "fresh off the source row". Defaults to
    each seeded item's own (subject_table, subject_id, email) so existing
    behaviour needs no extra setup; a test proving H1 (stale snapshot)
    overrides one entry to something other than the item's own `email`.

    conflicting_users: rows _refuse_if_email_belongs_to_an_unrelated_
    account()'s query should return -- empty by default (no conflict)."""

    def __init__(self, items: dict, subject_emails: dict = None, conflicting_users: list = None):
        self.items = items  # id -> dict
        self.subject_emails = subject_emails if subject_emails is not None else {
            (row["subject_table"], row["subject_id"]): row["email"] for row in items.values()
        }
        self.conflicting_users = conflicting_users if conflicting_users is not None else []
        self.decisions = []
        self.audit_log = []

    async def fetch_one(self, sql, *args):
        if "FROM retention_review_items WHERE id" in sql and "SET status = 'purging'" not in sql:
            return dict(self.items[args[0]]) if args[0] in self.items else None
        if "SET status = 'purging'" in sql:
            item = self.items.get(args[0])
            if item is None or item["status"] not in ("pending", "rejected"):
                return None
            item["status"] = "purging"
            return {"id": args[0]}
        m = _EMAIL_COL_RE.search(sql)
        if m:
            table = m.group(2)
            return {"email": self.subject_emails.get((table, args[0]))}
        raise AssertionError(f"unexpected fetch_one: {sql}")

    async def fetch_all(self, sql, *args):
        if "FROM retention_review_items WHERE category" in sql:
            category = args[0]
            return [
                {"id": i} for i, row in self.items.items()
                if row["category"] == category and row["status"] == "pending"
            ]
        if "SELECT id, role FROM users WHERE LOWER(email)" in sql:
            return list(self.conflicting_users)
        raise AssertionError(f"unexpected fetch_all: {sql}")

    async def execute(self, sql, *args):
        stripped = sql.strip()
        if stripped.startswith("UPDATE retention_review_items SET status = 'purged'"):
            self.items[args[0]]["status"] = "purged"
            self.items[args[0]]["purged_at"] = "now"
            self.items[args[0]]["email"] = None
        elif stripped.startswith("UPDATE retention_review_items SET status = 'rejected'"):
            self.items[args[0]]["status"] = "rejected"
            self.items[args[0]]["email"] = None
        elif stripped.startswith("UPDATE retention_review_items SET status = 'no_longer_eligible'"):
            self.items[args[0]]["status"] = "no_longer_eligible"
            self.items[args[0]]["email"] = None
        elif stripped.startswith("UPDATE retention_review_items SET status = $2"):
            # the M1/M2 unclaim-on-failure path: status is a bound param, not literal
            self.items[args[0]]["status"] = args[1]
        elif stripped.startswith("INSERT INTO retention_review_decisions"):
            self.decisions.append({"review_item_id": args[0], "decision": args[1], "actor_id": args[2], "note": args[3]})
        elif stripped.startswith("INSERT INTO audit_log"):
            self.audit_log.append(args)
        elif stripped.startswith("DELETE FROM"):
            pass  # the hard_delete branch -- nothing to assert on the fake target table itself
        else:
            raise AssertionError(f"unexpected execute: {sql}")
        return "OK"


def _install(monkeypatch, db: _FakeItemsDB, eligible: bool = True):
    from routers import retention_admin

    monkeypatch.setattr(retention_admin, "fetch_one", db.fetch_one)
    monkeypatch.setattr(retention_admin, "fetch_all", db.fetch_all)
    monkeypatch.setattr(retention_admin, "execute", db.execute)

    async def _fake_get_pool():
        return _FakePool(db)

    monkeypatch.setattr(retention_admin, "get_pool", _fake_get_pool)

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


def _fake_erase_person_recorder(erased: list):
    async def _fake_erase_person(email, actor_id=None, reason="manual", scope_table=None, scope_id=None):
        erased.append((email, actor_id, reason, scope_table, scope_id))
        return {"status": "complete"}
    return _fake_erase_person


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
    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person_recorder(erased))

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE", note="klopt")
    result = asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))

    assert result == {"id": 1, "status": "purged"}
    assert db.items[1]["status"] == "purged"
    # H1/H2: erase_person() receives the freshly re-read address and is
    # scoped to this exact subject row -- not merely "whoever has this
    # e-mail today".
    assert erased == [("person@example.com", 9, "retention_purge:rejected_applicant", "candidates", 42)]
    assert db.decisions == [{"review_item_id": 1, "decision": "approved", "actor_id": 9, "note": "klopt"}]
    assert len(db.audit_log) == 1
    assert db.audit_log[0][0] == "retention_review_approve"
    changes = json.loads(db.audit_log[0][4])
    assert changes == {"category": "rejected_applicant", "action": "anonymise"}
    # never the e-mail address or any other PII, per commit 72b4bcd's rule
    assert "person@example.com" not in json.dumps(db.audit_log)
    # H3: the review item's own email column is nulled once handled
    assert db.items[1]["email"] is None


def test_approve_uses_the_freshly_read_address_not_the_stale_snapshot(monkeypatch):
    """H1 (security-audit round 5): the review item's own `email` column
    can be stale (the subject's address changed after the monthly list
    was generated) -- erase_person() must be called with whatever
    `_current_subject_email()` reads off the source row right now, never
    `item["email"]`."""
    item = _pending_item(email="stale-snapshot@example.com")
    db = _FakeItemsDB(
        {1: item},
        subject_emails={("candidates", 42): "changed-since@example.com"},
    )
    retention_admin = _install(monkeypatch, db)

    erased = []
    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person_recorder(erased))

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))

    assert erased[0][0] == "changed-since@example.com"


def test_approve_refuses_when_address_belongs_to_an_unrelated_admin_account(monkeypatch):
    """H2 (security-audit round 5, BLOCKING)."""
    db = _FakeItemsDB(
        {1: _pending_item()},
        conflicting_users=[{"id": 999, "role": "admin"}],
    )
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "retention_purge_blocked_unrelated_account"
    # never claimed, never decided -- the refusal happens before either
    assert db.items[1]["status"] == "pending"
    assert db.decisions == []


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

    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person_recorder([]))

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    result = asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))
    assert result == {"id": 1, "status": "purged"}


def test_approve_refuses_a_no_longer_eligible_item_without_reverifying(monkeypatch):
    """M2 follow-up: only 'pending'/'rejected' are ever directly
    approvable -- 'no_longer_eligible' must go through a fresh monthly
    generation run (which reopens it to 'pending' if still due) rather
    than being re-approved straight from that state, now that the claim
    step's own WHERE clause is the single source of truth for which
    states are actionable."""
    db = _FakeItemsDB({1: _pending_item(status="no_longer_eligible")})
    retention_admin = _install(monkeypatch, db)

    async def _never_called(item):
        raise AssertionError("must not reach eligibility re-check for a non-actionable status")

    monkeypatch.setattr(retention_admin, "_is_still_eligible", _never_called)

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "retention_review_item_not_actionable"


def test_approve_unclaims_the_item_when_the_action_itself_fails(monkeypatch):
    """M1/M2 follow-up: a failure inside the action (e.g. a foreign-key
    violation) must not leave the item stuck at 'purging' forever --
    it is unclaimed back to its pre-claim status so a retry can act on it."""
    db = _FakeItemsDB({1: _pending_item(status="rejected")})
    retention_admin = _install(monkeypatch, db)

    async def _boom(email, actor_id=None, reason="manual", scope_table=None, scope_id=None):
        raise RuntimeError("simulated foreign-key violation")

    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _boom)

    payload = retention_admin.ReviewDecisionRequest(confirm="APPROVE")
    with pytest.raises(RuntimeError):
        asyncio.run(retention_admin.approve_review_item(1, payload, current_user={"id": 9, "role": "admin"}))

    assert db.items[1]["status"] == "rejected"  # unclaimed back, not stuck at 'purging'
    # the decision row written before the (failed) action is left in place
    assert db.decisions == [{"review_item_id": 1, "decision": "approved", "actor_id": 9, "note": None}]


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


def test_reject_redacts_an_email_address_out_of_the_note(monkeypatch):
    """M4: a free-text note can carry the subject's own address -- redact
    it the same way admin.py's consent evidence field already does."""
    db = _FakeItemsDB({1: _pending_item()})
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewDecisionRequest(note="al gebeld op person@example.com, nog geen reactie")
    asyncio.run(retention_admin.reject_review_item(1, payload, current_user={"id": 9, "role": "admin"}))

    assert "person@example.com" not in db.decisions[0]["note"]
    assert "redacted" in db.decisions[0]["note"]


# ── bulk ──────────────────────────────────────────────────────────────

def test_bulk_reject_by_category_needs_no_confirm_or_expected_count(monkeypatch):
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

    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person_recorder([]))

    payload = retention_admin.ReviewBulkRequest(decision="approved", ids=[1], confirm="APPROVE")
    result = asyncio.run(retention_admin.bulk_review_decision(payload, current_user={"id": 9, "role": "admin"}))

    assert result["results"] == [{"id": 1, "status": "purged"}]
    assert db.items[1]["status"] == "purged"


def test_bulk_approve_by_ids_never_needs_expected_count(monkeypatch):
    """expected_count is only required for a category-wide approve --
    an explicit `ids` list is already the admin's exact selection."""
    db = _FakeItemsDB({1: _pending_item()})
    retention_admin = _install(monkeypatch, db)
    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person_recorder([]))

    payload = retention_admin.ReviewBulkRequest(decision="approved", ids=[1], confirm="APPROVE", expected_count=None)
    result = asyncio.run(retention_admin.bulk_review_decision(payload, current_user={"id": 9, "role": "admin"}))
    assert result["results"] == [{"id": 1, "status": "purged"}]


def test_bulk_approve_by_category_requires_expected_count(monkeypatch):
    """L1 (security-audit round 5, BLOCKING)."""
    db = _FakeItemsDB({1: _pending_item()})
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewBulkRequest(decision="approved", category="rejected_applicant", confirm="APPROVE")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.bulk_review_decision(payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 422


def test_bulk_approve_by_category_refuses_a_mismatched_expected_count(monkeypatch):
    """L1: the pending count at approval time must match what the admin
    actually reviewed -- a mismatch (someone else's approve/reject, or a
    fresh monthly generation run, landed in between) is refused outright
    rather than silently acting on however many rows now match."""
    db = _FakeItemsDB({
        1: _pending_item(id=1), 2: _pending_item(id=2, subject_id=43),
    })
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewBulkRequest(
        decision="approved", category="rejected_applicant", confirm="APPROVE", expected_count=1,
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.bulk_review_decision(payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "retention_review_bulk_expected_count_mismatch"
    # nothing was touched
    assert db.items[1]["status"] == "pending"
    assert db.items[2]["status"] == "pending"


def test_bulk_approve_by_category_with_a_correct_expected_count(monkeypatch):
    db = _FakeItemsDB({
        1: _pending_item(id=1), 2: _pending_item(id=2, subject_id=43),
    })
    retention_admin = _install(monkeypatch, db)
    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _fake_erase_person_recorder([]))

    payload = retention_admin.ReviewBulkRequest(
        decision="approved", category="rejected_applicant", confirm="APPROVE", expected_count=2,
    )
    result = asyncio.run(retention_admin.bulk_review_decision(payload, current_user={"id": 9, "role": "admin"}))
    assert {r["status"] for r in result["results"]} == {"purged"}


def test_bulk_ids_over_the_cap_are_refused(monkeypatch):
    db = _FakeItemsDB({})
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewBulkRequest(
        decision="rejected", ids=list(range(1, retention_admin.MAX_BULK_REVIEW_ITEMS + 2)),
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.bulk_review_decision(payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 422


def test_bulk_requires_either_ids_or_category(monkeypatch):
    db = _FakeItemsDB({})
    retention_admin = _install(monkeypatch, db)

    payload = retention_admin.ReviewBulkRequest(decision="rejected")
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(retention_admin.bulk_review_decision(payload, current_user={"id": 9, "role": "admin"}))
    assert exc_info.value.status_code == 422


def test_bulk_catches_a_bare_exception_without_losing_the_rest_of_the_batch(monkeypatch):
    """M1 (security-audit round 5, BLOCKING): an unexpected exception for
    one item (e.g. a ForeignKeyViolation) must not abort the whole loop --
    every other item's own outcome is independent."""
    db = _FakeItemsDB({
        1: _pending_item(id=1, subject_id=42),
        2: _pending_item(id=2, subject_id=43),
    })
    retention_admin = _install(monkeypatch, db)

    async def _flaky_erase_person(email, actor_id=None, reason="manual", scope_table=None, scope_id=None):
        if scope_id == 42:
            raise RuntimeError("simulated foreign-key violation")
        return {"status": "complete"}

    import routers.gdpr as gdpr
    monkeypatch.setattr(gdpr, "erase_person", _flaky_erase_person)

    payload = retention_admin.ReviewBulkRequest(decision="approved", ids=[1, 2], confirm="APPROVE")
    result = asyncio.run(retention_admin.bulk_review_decision(payload, current_user={"id": 9, "role": "admin"}))

    by_id = {r["id"]: r["status"] for r in result["results"]}
    assert by_id == {1: "error", 2: "purged"}
    # the exception text itself is never put in the response (no PII leak)
    assert "RuntimeError" not in json.dumps(result) and "foreign-key" not in json.dumps(result)
    # item 1 was unclaimed back to 'pending', not stuck at 'purging'
    assert db.items[1]["status"] == "pending"


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
