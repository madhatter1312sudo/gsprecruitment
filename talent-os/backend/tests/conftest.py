"""Shared pytest fixtures/setup for talent-os/backend tests.

core.config.Settings() is instantiated at import time and refuses to start
with placeholder secrets (see core/config.py's _reject_placeholder_secrets
validator) -- so the four dummy env vars below must be set BEFORE
`core.config` (or anything importing it) is ever imported. conftest.py is
collected by pytest before test modules, which is what makes `pytest` work
bare from this directory without a hand-set environment.
"""
import os

os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-characters-long-xx")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-password")
