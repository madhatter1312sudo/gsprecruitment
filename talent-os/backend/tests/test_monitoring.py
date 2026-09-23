"""Unit tests for core/monitoring.py (WS-E.9).

init_sentry() must never ship local variables to Sentry -- an exception
raised inside a handler that holds e.g. a plaintext e-mail address in a
local variable would otherwise leak it via stack-frame locals even though
_scrub_pii redacts request/extra/contexts/user/breadcrumbs. See #159.
"""
from unittest.mock import MagicMock, patch

from core.monitoring import init_sentry


def test_init_sentry_disables_local_variable_capture():
    """sentry_sdk.init() must be called with include_local_variables=False."""
    with patch("sentry_sdk.init") as mock_init:
        init_sentry(dsn="https://example@sentry.io/1", environment="test")

    mock_init.assert_called_once()
    _, kwargs = mock_init.call_args
    assert kwargs.get("include_local_variables") is False


def test_init_sentry_noop_without_dsn():
    """No DSN -- init_sentry() must not touch sentry_sdk at all."""
    with patch("sentry_sdk.init") as mock_init:
        init_sentry(dsn="", environment="test")

    mock_init.assert_not_called()


def test_init_sentry_keeps_existing_pii_settings():
    """Regression guard: send_default_pii and before_send must stay as-is."""
    with patch("sentry_sdk.init") as mock_init:
        init_sentry(dsn="https://example@sentry.io/1", environment="staging")

    _, kwargs = mock_init.call_args
    assert kwargs.get("send_default_pii") is False
    assert callable(kwargs.get("before_send"))
