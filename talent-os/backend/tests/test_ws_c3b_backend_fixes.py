"""
Tests for WS-C.3b "overige backend-fixes".

Covers only paths that need no live Postgres: the blog HTML sanitizer
(pure function) and the Hermes webhook's payload validation, which now
rejects a bad body / an unsupported action before ever touching the DB.
"""
import hashlib
import hmac
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

from fastapi.testclient import TestClient

import main
from core.config import settings
from services.sanitize import sanitize_blog_html

client = TestClient(main.app)


# ── services/sanitize.py ──────────────────────────────────────────────

def test_sanitize_keeps_allowed_tags():
    raw = "<h2>Title</h2><p>Body <strong>bold</strong> <em>em</em></p><ul><li>one</li></ul>"
    assert sanitize_blog_html(raw) == raw


def test_sanitize_strips_script_tag_and_its_content():
    raw = "<p>hello</p><script>alert('xss')</script><p>world</p>"
    out = sanitize_blog_html(raw)
    assert "<script" not in out
    assert "alert" not in out
    assert out == "<p>hello</p><p>world</p>"


def test_sanitize_strips_style_tag_and_its_content():
    raw = "<style>body{display:none}</style><p>ok</p>"
    out = sanitize_blog_html(raw)
    assert "<style" not in out
    assert "display:none" not in out
    assert out == "<p>ok</p>"


def test_sanitize_unwraps_disallowed_tags_but_keeps_text():
    raw = "<div class='x'><p>kept</p><iframe src='evil'></iframe></div>"
    out = sanitize_blog_html(raw)
    assert "<div" not in out
    assert "<iframe" not in out
    assert "kept" in out


def test_sanitize_strips_on_attributes():
    raw = '<p onclick="alert(1)">click me</p>'
    out = sanitize_blog_html(raw)
    assert "onclick" not in out
    assert "click me" in out


def test_sanitize_keeps_https_href():
    raw = '<a href="https://gsprecruitment.nl">link</a>'
    assert sanitize_blog_html(raw) == raw


def test_sanitize_strips_javascript_href():
    raw = "<a href=\"javascript:alert(1)\">link</a>"
    out = sanitize_blog_html(raw)
    assert "javascript:" not in out
    assert out == "<a>link</a>"


def test_sanitize_strips_http_href_https_only():
    raw = '<a href="http://gsprecruitment.nl">link</a>'
    out = sanitize_blog_html(raw)
    assert "http://" not in out
    assert out == "<a>link</a>"


def test_sanitize_none_and_empty_passthrough():
    assert sanitize_blog_html(None) is None
    assert sanitize_blog_html("") == ""


def test_sanitize_drops_comments():
    raw = "<!-- leaked internal note --><p>visible</p>"
    out = sanitize_blog_html(raw)
    assert "leaked internal note" not in out
    assert out == "<p>visible</p>"


# ── routers/webhook.py ──────────────────────────────────────────────────

def _signed_post(payload_bytes: bytes):
    sig = hmac.new(settings.webhook_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return client.post(
        "/api/hermes/webhook",
        content=payload_bytes,
        headers={"X-Hermes-Signature": sig, "Content-Type": "application/json"},
    )


def test_webhook_rejects_placement_update_with_422():
    """No `placements` table exists yet -- placement_update must 422 with a
    clear detail, not be silently swallowed by the old catch-all branch."""
    r = _signed_post(b'{"action": "placement_update", "agent": "hermes-1", "data": {"candidate_id": 1}}')
    assert r.status_code == 422
    assert "placement" in r.json()["detail"].lower()


def test_webhook_rejects_unknown_action_with_422():
    r = _signed_post(b'{"action": "totally_unknown", "agent": "hermes-1", "data": {}}')
    assert r.status_code == 422


def test_webhook_rejects_missing_action_with_422():
    r = _signed_post(b'{"agent": "hermes-1", "data": {}}')
    assert r.status_code == 422


def test_webhook_rejects_bad_signature_before_validation():
    body = b'{"action": "placement_update", "data": {}}'
    r = client.post(
        "/api/hermes/webhook",
        content=body,
        headers={"X-Hermes-Signature": "not-a-real-signature", "Content-Type": "application/json"},
    )
    assert r.status_code == 401
