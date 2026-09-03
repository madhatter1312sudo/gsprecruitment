"""
Unit tests for WS-E.7 GDPR erasure -- routers/gdpr.py erase_person(),
core/privacy.py hashing, and the suppression endpoint's hashing.

No DB/network needed: core.database's fetch_one/fetch_all/execute are
monkeypatched to a tiny in-memory recorder + canned-response fake so the
whole erase_person() coroutine runs for real (asyncio.run, no
pytest-asyncio dependency, matching tests/test_storage.py's style) and
every SQL statement it issues gets recorded for the table-coverage
assertion.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from core import privacy


# ── core/privacy.py -- pure, no DB ────────────────────────────────────────

def test_email_hash_is_case_and_whitespace_insensitive():
    assert privacy.email_hash("  Foo@Example.com ") == privacy.email_hash("foo@example.com")


def test_email_hash_is_sha256_hex():
    h = privacy.email_hash("foo@example.com")
    assert len(h) == 64
    int(h, 16)  # must be valid hex


def test_email_hash_differs_for_different_addresses():
    assert privacy.email_hash("a@example.com") != privacy.email_hash("b@example.com")


def test_email_domain_extracts_domain_lowercased():
    assert privacy.email_domain("Foo@Example.COM") == "example.com"


def test_email_domain_none_without_at_sign():
    assert privacy.email_domain("not-an-email") is None


# ── erase_person() -- stubbed DB, table coverage ──────────────────────────

class _FakeDB:
    """Records every SQL statement passed to fetch_one/fetch_all/execute
    and returns canned rows keyed by a substring of the SQL. Good enough
    to drive erase_person() end to end without a real database."""

    def __init__(self):
        self.statements = []  # [(sql, args)]

    def _record(self, sql, args):
        self.statements.append((sql, args))

    async def fetch_one(self, sql, *args):
        self._record(sql, args)
        if "FROM candidate_profiles WHERE user_id" in sql:
            return None  # no CV on file for this test person
        return None

    async def fetch_all(self, sql, *args):
        self._record(sql, args)
        if "SELECT id FROM users WHERE" in sql:
            return [{"id": 42}]
        if "SELECT cv_file_path FROM candidates WHERE" in sql:
            return []
        if "FROM audit_log WHERE changes" in sql:
            return []
        return []

    async def execute(self, sql, *args):
        self._record(sql, args)
        return "OK"


@pytest.fixture()
def fake_db(monkeypatch):
    import routers.gdpr as gdpr

    db = _FakeDB()
    monkeypatch.setattr(gdpr, "fetch_one", db.fetch_one)
    monkeypatch.setattr(gdpr, "fetch_all", db.fetch_all)
    monkeypatch.setattr(gdpr, "execute", db.execute)

    # storage.is_configured() would otherwise try to read live R2 env vars
    # -- force the "not configured, no R2 paths referenced" branch, which
    # for this test (no cv_file_path rows at all) is a clean no-op.
    from services import storage
    monkeypatch.setattr(storage, "is_configured", lambda: False)

    return db


# Every table the WS-E.7 task description requires erase_person() to
# touch. This is the regression guard: if a future edit drops one of
# these statements, this test fails loudly rather than silently leaving
# PII behind after "erasure".
EXPECTED_TABLES = [
    "candidates",
    "candidate_profiles",
    "users",
    "push_tokens",
    "quiz_submissions",
    "contact_submissions",
    "outreach_drafts",
    "outreach_messages",
    "audit_log",
    "data_subject_requests",
    "suppression_list",
]


def test_erase_person_touches_every_required_table(fake_db):
    import routers.gdpr as gdpr

    result = asyncio.run(
        gdpr.erase_person("Person@Example.com", actor_id=7, reason="unit-test")
    )

    assert result["status"] == "complete"
    assert result["cv_files_failed"] == []

    all_sql = "\n".join(sql for sql, _args in fake_db.statements)
    missing = [t for t in EXPECTED_TABLES if t not in all_sql]
    assert not missing, f"erase_person() never touched: {missing}\n\nSQL issued:\n{all_sql}"


def test_erase_person_never_writes_the_plaintext_email_to_audit_log(fake_db):
    """The final audit_log insert must carry the hash, not the address."""
    import routers.gdpr as gdpr

    asyncio.run(gdpr.erase_person("plain-text@example.com", actor_id=1, reason="unit-test"))

    audit_inserts = [
        args for sql, args in fake_db.statements
        if sql.strip().startswith("INSERT INTO audit_log") and args and args[0] == "gdpr_erasure"
    ]
    assert audit_inserts, "expected a gdpr_erasure audit_log insert"
    # changes is the 5th bound param (action, actor_id, target_type, target_id, changes)
    changes_json = audit_inserts[0][4]
    assert "plain-text@example.com" not in changes_json
    assert privacy.email_hash("plain-text@example.com") in changes_json


def test_erase_person_rejects_empty_email(fake_db):
    import routers.gdpr as gdpr
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(gdpr.erase_person("   ", actor_id=1))
    assert exc_info.value.status_code == 400


def test_redact_value_walks_nested_dicts_and_lists():
    import routers.gdpr as gdpr

    value = {
        "target_email": "Foo@Example.com",
        "nested": {"note": "contact Foo@example.com again"},
        "list": ["keep me", "foo@example.com present here too"],
        "unrelated": 42,
    }
    new_value, changed = gdpr._redact_value(value, "foo@example.com", "HASHED")
    assert changed is True
    assert new_value["target_email"] == "HASHED"
    assert new_value["nested"]["note"] == "HASHED"
    assert new_value["list"][0] == "keep me"
    assert new_value["list"][1] == "HASHED"
    assert new_value["unrelated"] == 42
