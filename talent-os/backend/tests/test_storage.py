"""Tests for services/storage.py (R2/S3 CV storage) -- no network needed.

put_object/presigned_get/delete_object/object_exists are exercised against a
botocore Stubber (ships with boto3 -- no moto/network required, and no
pytest-asyncio dependency needed since we just asyncio.run() each coroutine
directly) so the request shape and response handling are verified without
ever touching a real endpoint. The pure helpers (cv_key, is_r2_key) and the
legacy-path fallback branch logic get plain unit tests.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.config import settings
from services import storage


@pytest.fixture(autouse=True)
def _configured_r2(monkeypatch):
    """Point settings at fake-but-present R2 config so is_configured() is
    True and _get_client() builds a real (never-dialed) boto3 client for the
    Stubber to attach to. Also resets the module-level client cache so tests
    don't leak a stubbed client into each other."""
    monkeypatch.setattr(settings, "r2_endpoint", "https://example.r2.cloudflarestorage.com")
    monkeypatch.setattr(settings, "r2_access_key_id", "fake-key-id")
    monkeypatch.setattr(settings, "r2_secret_access_key", "fake-secret")
    monkeypatch.setattr(settings, "r2_bucket", "gsp")
    storage._client = None
    yield
    storage._client = None


def _stub_client():
    from botocore.stub import Stubber

    client = storage._get_client()
    return client, Stubber(client)


# ── is_configured ───────────────────────────────────────────────────────

def test_is_configured_true_when_all_four_set():
    assert storage.is_configured() is True


def test_is_configured_false_when_any_missing(monkeypatch):
    monkeypatch.setattr(settings, "r2_bucket", "")
    assert storage.is_configured() is False


# ── cv_key / is_r2_key (pure helpers) ───────────────────────────────────

def test_cv_key_format():
    assert storage.cv_key(42, ".pdf", "abc123") == "cv/42/abc123.pdf"


def test_cv_key_adds_missing_dot():
    assert storage.cv_key(1, "docx", "xyz") == "cv/1/xyz.docx"


def test_is_r2_key_true_for_new_style_path():
    assert storage.is_r2_key("cv/7/abc123.pdf") is True


def test_is_r2_key_false_for_legacy_local_path():
    assert storage.is_r2_key("/uploads/cv/oldfile.pdf") is False


def test_is_r2_key_false_for_none_or_empty():
    assert storage.is_r2_key(None) is False
    assert storage.is_r2_key("") is False


# ── put_object ───────────────────────────────────────────────────────────

def test_put_object_sends_expected_request():
    client, stubber = _stub_client()
    stubber.add_response(
        "put_object",
        {},
        {"Bucket": "gsp", "Key": "cv/1/abc.pdf", "Body": b"hello", "ContentType": "application/pdf"},
    )
    with stubber:
        asyncio.run(storage.put_object("cv/1/abc.pdf", b"hello", "application/pdf"))
    stubber.assert_no_pending_responses()


# ── presigned_get ────────────────────────────────────────────────────────

def test_presigned_get_returns_url_with_ttl_and_disposition():
    url = asyncio.run(storage.presigned_get("cv/1/abc.pdf", ttl=300, filename="cv.pdf"))
    assert url.startswith("https://")
    assert "cv%2F1%2Fabc.pdf" in url or "cv/1/abc.pdf" in url
    assert "X-Amz-Expires=300" in url
    assert "response-content-disposition" in url.lower()


def test_presigned_get_without_filename_omits_disposition():
    url = asyncio.run(storage.presigned_get("cv/1/abc.pdf"))
    assert "response-content-disposition" not in url.lower()


# ── delete_object (idempotency) ─────────────────────────────────────────

def test_delete_object_success():
    client, stubber = _stub_client()
    stubber.add_response("delete_object", {}, {"Bucket": "gsp", "Key": "cv/1/abc.pdf"})
    with stubber:
        asyncio.run(storage.delete_object("cv/1/abc.pdf"))
    stubber.assert_no_pending_responses()


def test_delete_object_missing_key_is_not_an_error():
    client, stubber = _stub_client()
    stubber.add_client_error(
        "delete_object",
        service_error_code="NoSuchKey",
        http_status_code=404,
        expected_params={"Bucket": "gsp", "Key": "cv/1/gone.pdf"},
    )
    with stubber:
        # Must not raise.
        asyncio.run(storage.delete_object("cv/1/gone.pdf"))
    stubber.assert_no_pending_responses()


# ── object_exists ────────────────────────────────────────────────────────

def test_object_exists_true():
    client, stubber = _stub_client()
    stubber.add_response("head_object", {}, {"Bucket": "gsp", "Key": "cv/1/abc.pdf"})
    with stubber:
        assert asyncio.run(storage.object_exists("cv/1/abc.pdf")) is True
    stubber.assert_no_pending_responses()


def test_object_exists_false_on_404():
    client, stubber = _stub_client()
    stubber.add_client_error(
        "head_object",
        service_error_code="404",
        http_status_code=404,
        expected_params={"Bucket": "gsp", "Key": "cv/1/missing.pdf"},
    )
    with stubber:
        assert asyncio.run(storage.object_exists("cv/1/missing.pdf")) is False
    stubber.assert_no_pending_responses()


# ── delete_prefix (GDPR erasure sweep) ──────────────────────────────────

def test_delete_prefix_empty_is_a_noop():
    """No objects under the prefix -- one list call, no delete_objects call,
    not an error."""
    client, stubber = _stub_client()
    stubber.add_response(
        "list_objects_v2",
        {"Contents": [], "IsTruncated": False},
        {"Bucket": "gsp", "Prefix": "cv/999/"},
    )
    with stubber:
        deleted = asyncio.run(storage.delete_prefix("cv/999/"))
    assert deleted == []
    stubber.assert_no_pending_responses()


def test_delete_prefix_deletes_every_object_single_page():
    client, stubber = _stub_client()
    stubber.add_response(
        "list_objects_v2",
        {
            "Contents": [{"Key": "cv/1/a.pdf"}, {"Key": "cv/1/b.pdf"}],
            "IsTruncated": False,
        },
        {"Bucket": "gsp", "Prefix": "cv/1/"},
    )
    stubber.add_response(
        "delete_objects",
        {},
        {
            "Bucket": "gsp",
            "Delete": {"Objects": [{"Key": "cv/1/a.pdf"}, {"Key": "cv/1/b.pdf"}], "Quiet": True},
        },
    )
    with stubber:
        deleted = asyncio.run(storage.delete_prefix("cv/1/"))
    assert sorted(deleted) == ["cv/1/a.pdf", "cv/1/b.pdf"]
    stubber.assert_no_pending_responses()


def test_delete_prefix_paginates_across_list_calls():
    """Covers the pre-existing-orphans case: a candidate who re-uploaded
    several times before the delete-old-key fix could have many objects
    under their prefix, spread across list_objects_v2 pages."""
    client, stubber = _stub_client()
    stubber.add_response(
        "list_objects_v2",
        {
            "Contents": [{"Key": "cv/1/a.pdf"}],
            "IsTruncated": True,
            "NextContinuationToken": "page-2",
        },
        {"Bucket": "gsp", "Prefix": "cv/1/"},
    )
    stubber.add_response(
        "delete_objects",
        {},
        {"Bucket": "gsp", "Delete": {"Objects": [{"Key": "cv/1/a.pdf"}], "Quiet": True}},
    )
    stubber.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": "cv/1/b.pdf"}], "IsTruncated": False},
        {"Bucket": "gsp", "Prefix": "cv/1/", "ContinuationToken": "page-2"},
    )
    stubber.add_response(
        "delete_objects",
        {},
        {"Bucket": "gsp", "Delete": {"Objects": [{"Key": "cv/1/b.pdf"}], "Quiet": True}},
    )
    with stubber:
        deleted = asyncio.run(storage.delete_prefix("cv/1/"))
    assert sorted(deleted) == ["cv/1/a.pdf", "cv/1/b.pdf"]
    stubber.assert_no_pending_responses()


def test_delete_prefix_raises_on_partial_delete_errors():
    """If R2 reports per-key errors from delete_objects, that's surfaced as
    a failure rather than silently claimed as deleted -- the caller (GDPR
    erasure) is responsible for catching this and recording it as a failed
    path rather than a deleted one."""
    client, stubber = _stub_client()
    stubber.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": "cv/1/a.pdf"}], "IsTruncated": False},
        {"Bucket": "gsp", "Prefix": "cv/1/"},
    )
    stubber.add_response(
        "delete_objects",
        {"Errors": [{"Key": "cv/1/a.pdf", "Code": "AccessDenied", "Message": "nope"}]},
        {"Bucket": "gsp", "Delete": {"Objects": [{"Key": "cv/1/a.pdf"}], "Quiet": True}},
    )
    with stubber:
        with pytest.raises(RuntimeError):
            asyncio.run(storage.delete_prefix("cv/1/"))


# ── cv_prefix / should_delete_old_key (pure helpers) ────────────────────

def test_cv_prefix_format():
    assert storage.cv_prefix(42) == "cv/42/"


def test_should_delete_old_key_true_for_different_r2_key():
    assert storage.should_delete_old_key("cv/1/old.pdf", "cv/1/new.pdf") is True


def test_should_delete_old_key_false_when_no_old_value():
    assert storage.should_delete_old_key(None, "cv/1/new.pdf") is False
    assert storage.should_delete_old_key("", "cv/1/new.pdf") is False


def test_should_delete_old_key_false_for_legacy_local_path():
    # Cleaning up a legacy local file is not this function's job -- it only
    # decides whether to fire an R2 delete_object call.
    assert storage.should_delete_old_key("/uploads/cv/old.pdf", "cv/1/new.pdf") is False


def test_should_delete_old_key_false_when_old_equals_new():
    # Guards a uuid4 collision from wiping the file that was just written.
    assert storage.should_delete_old_key("cv/1/same.pdf", "cv/1/same.pdf") is False


# ── legacy-path fallback branch logic (as used by candidate.py/gdpr.py) ──

def _resolve_download_branch(cv_file_path, r2_configured):
    """Mirrors the branch logic in candidate.py's download endpoint, pulled
    out as a pure function so it's testable without a running app/DB."""
    if r2_configured and storage.is_r2_key(cv_file_path):
        return "r2_presigned_redirect"
    return "legacy_local_file"


def test_branch_uses_r2_when_configured_and_key_is_r2_style():
    assert _resolve_download_branch("cv/1/abc.pdf", r2_configured=True) == "r2_presigned_redirect"


def test_branch_falls_back_to_legacy_when_path_is_not_r2_style():
    assert _resolve_download_branch("/uploads/cv/old.pdf", r2_configured=True) == "legacy_local_file"


def test_branch_falls_back_to_legacy_when_r2_not_configured_even_for_r2_style_key():
    # Defensive: even a "cv/..." path should fail safe to legacy handling if
    # R2 somehow isn't configured (should not happen once a cv/ key exists,
    # but the branch itself shouldn't assume it).
    assert _resolve_download_branch("cv/1/abc.pdf", r2_configured=False) == "legacy_local_file"
