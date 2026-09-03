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
    to drive erase_person() end to end without a real database.

    Every `SELECT id [, ...] FROM <table> WHERE LOWER(<col>) = $1` that
    erase_person()/_anonymize_by_id() issues gets exactly one canned row
    (id=99) back, so every anonymising UPDATE branch actually runs (and
    gets recorded) rather than short-circuiting on an empty result --
    that's what lets the table-coverage assertion below be meaningful for
    tables reached only via _anonymize_by_id (quiz_submissions,
    contact_submissions, outreach_drafts, outreach_messages,
    client_prospects, data_subject_requests, and candidates/users
    themselves)."""

    _ONE_ROW_SELECTS = (
        "SELECT id FROM candidates WHERE LOWER(email)",
        "SELECT id FROM quiz_submissions WHERE LOWER(email)",
        "SELECT id FROM contact_submissions WHERE LOWER(email)",
        "SELECT id FROM outreach_drafts WHERE LOWER(target_email)",
        "SELECT id FROM outreach_messages WHERE LOWER(recipient_email)",
        "SELECT id FROM client_prospects WHERE LOWER(contact_email)",
        "SELECT id FROM data_subject_requests WHERE LOWER(request_email)",
    )

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
        if sql.strip().startswith("SELECT id FROM users WHERE LOWER(email)"):
            return [{"id": 42}]
        if "SELECT id, cv_file_path FROM candidates WHERE" in sql:
            return [{"id": 99, "cv_file_path": None}]
        if "FROM audit_log WHERE changes" in sql:
            return []
        for prefix in self._ONE_ROW_SELECTS:
            if sql.strip().startswith(prefix):
                return [{"id": 99}]
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
    "client_prospects",
    "pipeline_entries",
    "audit_log",
    "data_subject_requests",
    "suppression_list",
]

# security-auditor follow-up (H1): table-level coverage isn't enough on
# its own -- candidate_profiles carries far more PII than just the CV
# columns, and a prior version of erase_person() only cleared cv_text/
# cv_file_path there. Assert the actual column names show up in the
# UPDATE, not just that "candidate_profiles" appears somewhere in the SQL.
EXPECTED_CANDIDATE_PROFILE_COLUMNS = [
    "phone", "linkedin_url", "github_url", "portfolio_url",
    "current_company", "current_title", "location", "education",
    "salary_expectation_min", "salary_expectation_max",
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

    profile_updates = [
        sql for sql, _args in fake_db.statements
        if sql.strip().startswith("UPDATE candidate_profiles")
    ]
    assert profile_updates, "expected an UPDATE candidate_profiles statement"
    profile_sql = "\n".join(profile_updates)
    missing_cols = [c for c in EXPECTED_CANDIDATE_PROFILE_COLUMNS if c not in profile_sql]
    assert not missing_cols, (
        f"UPDATE candidate_profiles never clears: {missing_cols}\n\nSQL:\n{profile_sql}"
    )


def test_erase_person_clears_pipeline_entries_notes_for_the_candidate(fake_db):
    """pipeline_entries.notes is keyed by candidate_id, not e-mail --
    dedicated regression guard since the table-substring check above
    can't tell 'referenced' from 'actually filtered by the right id'."""
    import routers.gdpr as gdpr

    asyncio.run(gdpr.erase_person("Person@Example.com", actor_id=7, reason="unit-test"))

    pipeline_updates = [
        (sql, args) for sql, args in fake_db.statements
        if sql.strip().startswith("UPDATE pipeline_entries")
    ]
    assert pipeline_updates, "expected an UPDATE pipeline_entries statement"
    sql, args = pipeline_updates[0]
    assert "notes = NULL" in sql
    assert "candidate_id = $1" in sql
    assert args == (99,)  # the fake candidate id from _FakeDB


def test_erase_person_sets_client_prospects_opt_out_at(fake_db):
    import routers.gdpr as gdpr

    asyncio.run(gdpr.erase_person("Person@Example.com", actor_id=7, reason="unit-test"))

    prospect_updates = [
        sql for sql, _args in fake_db.statements
        if sql.strip().startswith("UPDATE client_prospects")
    ]
    assert prospect_updates, "expected an UPDATE client_prospects statement"
    assert "opt_out_at" in prospect_updates[0]
    assert "contact_name" in prospect_updates[0]
    assert "contact_linkedin" in prospect_updates[0]


def test_anonymize_by_id_generates_a_distinct_placeholder_per_row(monkeypatch):
    """L4: two rows matching the same original e-mail (e.g. a data
    anomaly, or simply several rows in the same table sharing an address)
    must not be anonymised to the exact same placeholder -- that would
    trip a real unique constraint (candidates.email, users.email)."""
    import routers.gdpr as gdpr

    captured = []

    async def fake_fetch_all(sql, *args):
        return [{"id": 1}, {"id": 2}, {"id": 3}]

    async def fake_execute(sql, *args):
        captured.append(args)
        return "OK"

    monkeypatch.setattr(gdpr, "fetch_all", fake_fetch_all)
    monkeypatch.setattr(gdpr, "execute", fake_execute)

    count = asyncio.run(gdpr._anonymize_by_id(
        "SELECT id FROM candidates WHERE LOWER(email) = $1",
        "UPDATE candidates SET email = $2 WHERE id = $1",
        "person@example.com",
        "abcdefabcdefabcd",
    ))

    assert count == 3
    placeholders = [args[1] for args in captured]
    assert len(set(placeholders)) == 3, f"expected 3 distinct placeholders, got {placeholders}"
    for row_id, placeholder in zip((1, 2, 3), placeholders):
        assert placeholder == f"erased-abcdefabcdefabcd-{row_id}@erased.invalid"


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


# ── admin_erase_person() -- M2: confirm gate on admin/self erasure ───────

@pytest.fixture()
def patch_users_lookup(monkeypatch):
    """Stubs gdpr.fetch_all (the users role/id lookup) and gdpr.erase_person
    (never actually run for these tests -- only whether the confirm gate
    lets the call through matters here)."""
    def _patch(matching_users):
        import routers.gdpr as gdpr

        async def fake_fetch_all(sql, *args):
            return matching_users

        calls = []

        async def fake_erase_person(email, actor_id=None, reason="manual"):
            calls.append((email, actor_id, reason))
            return {"status": "complete", "email_hash": "x", "cv_files_deleted": [], "cv_files_failed": []}

        monkeypatch.setattr(gdpr, "fetch_all", fake_fetch_all)
        monkeypatch.setattr(gdpr, "erase_person", fake_erase_person)
        return gdpr, calls
    return _patch


def test_admin_erase_refuses_admin_target_without_confirm(patch_users_lookup):
    gdpr, calls = patch_users_lookup([{"id": 5, "role": "admin"}])
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(gdpr.admin_erase_person(
            gdpr.AdminEraseRequest(email="target-admin@example.com", confirm=False),
            current_user={"id": 1, "role": "admin"},
        ))
    assert exc_info.value.status_code == 409
    assert calls == []  # erase_person must never have been called


def test_admin_erase_refuses_self_target_without_confirm(patch_users_lookup):
    gdpr, calls = patch_users_lookup([{"id": 1, "role": "admin"}])
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(gdpr.admin_erase_person(
            gdpr.AdminEraseRequest(email="me@example.com", confirm=False),
            current_user={"id": 1, "role": "admin"},
        ))
    assert exc_info.value.status_code == 409
    assert calls == []


def test_admin_erase_allows_admin_target_with_confirm(patch_users_lookup):
    gdpr, calls = patch_users_lookup([{"id": 5, "role": "admin"}])
    result = asyncio.run(gdpr.admin_erase_person(
        gdpr.AdminEraseRequest(email="target-admin@example.com", confirm=True),
        current_user={"id": 1, "role": "admin"},
    ))
    assert result["status"] == "complete"
    assert len(calls) == 1


def test_admin_erase_allows_ordinary_sourced_person_without_confirm(patch_users_lookup):
    """No matching users row at all (a purely sourced candidate, never
    registered) -- the confirm gate must not block the common case."""
    gdpr, calls = patch_users_lookup([])
    result = asyncio.run(gdpr.admin_erase_person(
        gdpr.AdminEraseRequest(email="sourced-only@example.com", confirm=False),
        current_user={"id": 1, "role": "admin"},
    ))
    assert result["status"] == "complete"
    assert len(calls) == 1
