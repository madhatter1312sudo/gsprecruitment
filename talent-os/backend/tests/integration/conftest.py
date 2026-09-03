"""
WS-C.14 — integration tests: FastAPI TestClient against a REAL Postgres.

Unlike the rest of tests/ (which stub core.database with an in-memory
fake so no DB is needed), everything under tests/integration/ hits an
actual database through the app's normal asyncpg pool. Every test file
here sets `pytestmark = pytest.mark.integration`, and the backend-root
conftest.py skips anything carrying that marker when POSTGRES_HOST isn't
set -- the plain `python3 -m pytest -q talent-os/backend` (unit tests,
CI's existing job) stays green without a database.

Local setup (see also .github/workflows/ci.yml for the CI equivalent):
    # Postgres 16 running, role `mig`/`migtestpw`, then:
    createdb -h 127.0.0.1 -U mig gsp_it
    cd talent-os/backend/migrations
    for f in 0*.py; do
        POSTGRES_HOST=127.0.0.1 POSTGRES_DB=gsp_it POSTGRES_USER=mig \
        POSTGRES_PASSWORD=migtestpw python3 "$f"
    done
    cd ..
    POSTGRES_HOST=127.0.0.1 POSTGRES_DB=gsp_it POSTGRES_USER=mig \
    POSTGRES_PASSWORD=migtestpw JWT_SECRET=ci-test-secret-not-used-in-production-32chars \
    API_KEY=x WEBHOOK_SECRET=x python3 -m pytest -q -m integration

Every row this suite creates uses a random @example.com address (GDPR:
no real personal data) and is left in place afterwards -- fine for a
throwaway CI/local `gsp_it` database, never point this at anything real.

── Why db_run(func, *args, **kwargs) instead of a plain asyncio.run() ───
core/database.py's connection pool is a single module-global, created
lazily on whatever asyncio event loop first calls get_pool() and unusable
from any other loop after that (asyncpg pools are loop-bound). A bare
TestClient(app) call spins up a *brand new* event loop (anyio blocking
portal) for every single request when used outside a `with` block, and a
bare `asyncio.run(...)` per test-setup call does the same -- mixing
either of those with a live DB pool fails the second the pool outlives
the loop it was born on ("RuntimeError: Event loop is closed").
Using `with TestClient(main.app) as client:` keeps ONE portal (one
event loop, in one background thread) alive for the whole session, and
db_run() below runs every direct DB call through that same portal
(client.portal.call) instead of asyncio.run() -- so the pool is created
once, on that one loop, and both the app's own requests and this
fixture's setup/teardown queries share it for the life of the test run.
"""
import functools
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Same ci-test-* defaults main.py/tests use elsewhere (tests/test_ws_c3b_backend_fixes.py
# etc.) -- only applied if the caller hasn't already set real ones (the
# local/CI invocations documented above always do).
os.environ.setdefault("JWT_SECRET", "ci-test-secret-not-used-in-production-32chars")
os.environ.setdefault("API_KEY", "x")
os.environ.setdefault("WEBHOOK_SECRET", "x")
os.environ.setdefault("POSTGRES_PASSWORD", "x")

import pytest
from fastapi.testclient import TestClient

import main  # noqa: E402  (import after sys.path/env setup above)
from core.database import execute, fetch_one  # noqa: E402
from core.security import create_access_token, hash_password  # noqa: E402


def unique_email(prefix: str = "user") -> str:
    """A fresh @example.com address per call -- GDPR: no real personal
    data, and unique so parallel/repeated test runs never collide on
    users.email / candidates.email's unique constraints."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


@pytest.fixture(scope="session")
def client():
    """One TestClient, one persistent portal/event loop, for the whole
    integration session -- see the module docstring above for why this
    has to be a `with` block rather than a bare TestClient(main.app)."""
    with TestClient(main.app) as c:
        yield c


@pytest.fixture(scope="session")
def db_run(client):
    """db_run(func, *args, **kwargs) runs an async core.database (or
    routers.*) call on the exact same event loop the app's own requests
    run on, via the TestClient's portal -- see module docstring."""
    def _run(func, *args, **kwargs):
        if kwargs:
            func = functools.partial(func, **kwargs)
        return client.portal.call(func, *args)
    return _run


@pytest.fixture
def make_email():
    """Fresh @example.com address generator (see unique_email() above)."""
    return unique_email


async def _insert_user(
    email: str, role: str, *, is_verified: bool, approved: bool, totp_enabled: bool = False,
) -> dict:
    now = datetime.now(timezone.utc)
    return await fetch_one(
        """INSERT INTO users
             (email, password_hash, full_name, role, is_verified,
              email_verified_at, approved_by_admin_at, password_changed_at, totp_enabled_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
           RETURNING id, email, role, password_changed_at""",
        email, hash_password("Test-Password-123!"), f"{role.title()} Example", role,
        is_verified,
        now if is_verified else None,
        now if approved else None,
        now,
        now if totp_enabled else None,
    )


def _token_for(user: dict, **extra_claims) -> str:
    return create_access_token(data={"sub": user["id"], "role": user["role"], **extra_claims})


def _as_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def make_admin(db_run):
    """Returns a fresh verified admin: {id, email, token, headers}."""
    def _make(*, totp_enabled: bool = False):
        email = unique_email("admin")
        user = db_run(_insert_user, email, "admin", is_verified=True, approved=False, totp_enabled=totp_enabled)
        token = _token_for(user)
        return {"id": user["id"], "email": email, "token": token, "headers": _as_headers(token),
                "password_changed_at": user["password_changed_at"]}
    return _make


@pytest.fixture
def make_client_user(db_run):
    """Returns a fresh client-role user, linked to a fresh `clients` row.
    approved=True stamps users.approved_by_admin_at (WS-E.2 candidate-access gate)."""
    def _make(*, approved: bool = False, verified: bool = True):
        email = unique_email("client")
        user = db_run(_insert_user, email, "client", is_verified=verified, approved=approved)
        client_row = db_run(
            fetch_one,
            "INSERT INTO clients (company_name, domain) VALUES ($1, 'example.com') RETURNING id",
            f"Example Co {uuid.uuid4().hex[:8]}",
        )
        db_run(
            execute,
            "INSERT INTO user_clients (user_id, client_id) VALUES ($1, $2)",
            user["id"], client_row["id"],
        )
        token = _token_for(user)
        return {"id": user["id"], "email": email, "client_id": client_row["id"], "token": token,
                "headers": _as_headers(token)}
    return _make


@pytest.fixture
def make_candidate_user(db_run):
    """Returns a fresh candidate-role account (verified by default)."""
    def _make(*, verified: bool = True):
        email = unique_email("candidate")
        user = db_run(_insert_user, email, "candidate", is_verified=verified, approved=False)
        token = _token_for(user)
        return {"id": user["id"], "email": email, "token": token, "headers": _as_headers(token)}
    return _make


@pytest.fixture
def insert_raw_user(db_run):
    """Lower-level than make_admin/make_client_user/make_candidate_user:
    insert a users row with full control over role/verified/approved/
    totp_enabled and get back {id, email, role, password_changed_at,
    token, headers} -- e.g. for the refresh-token / MFA edge cases that
    need a token minted from a specific row without the make_* fixtures'
    extra (clients/user_clients) side effects."""
    def _make(role: str, *, verified: bool = True, approved: bool = False, totp_enabled: bool = False):
        email = unique_email(role)
        user = db_run(_insert_user, email, role, is_verified=verified, approved=approved, totp_enabled=totp_enabled)
        token = _token_for(user)
        return {"id": user["id"], "email": email, "role": role,
                "password_changed_at": user["password_changed_at"],
                "token": token, "headers": _as_headers(token)}
    return _make


@pytest.fixture
def token_for():
    """Mint an access token for an arbitrary user dict (id + role), with
    optional extra JWT claims -- see _token_for() above."""
    return _token_for


@pytest.fixture
def api_key_headers():
    """X-API-Key header matching whatever API_KEY the app actually booted
    with (core.config.settings), never a hardcoded guess."""
    from core.config import settings
    return {"X-API-Key": settings.api_key}
