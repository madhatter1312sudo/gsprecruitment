"""
Talent OS — repo-wide pytest config (WS-C.14).

Auto-skips anything marked `integration` when POSTGRES_HOST isn't set, so
the plain `python3 -m pytest -q talent-os/backend` (unit tests, no DB --
CI's "Run backend tests" step and every developer's default `pytest` run)
keeps passing unchanged. The Postgres-backed CI job (and a developer who
wants the real thing locally) sets POSTGRES_HOST and gets the integration
suite under tests/integration/ instead. See pytest.ini for the marker
registration.
"""
import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("POSTGRES_HOST"):
        return
    skip_integration = pytest.mark.skip(
        reason="POSTGRES_HOST not set -- integration tests need a real Postgres, see tests/integration/conftest.py"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
