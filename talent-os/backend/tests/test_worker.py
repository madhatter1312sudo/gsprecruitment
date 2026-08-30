"""Tests for worker.py -- no network, no Redis, no real DB.

Covers: WorkerSettings shape (cron entry present, functions list), the
email_log_retention SQL via a stubbed core.database.execute, and the
redis_url config default.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import settings
import worker


# ── WorkerSettings shape ─────────────────────────────────────────────────

def test_worker_settings_functions_include_send_email_job():
    assert worker.send_email_job in worker.WorkerSettings.functions


def test_worker_settings_has_one_cron_job_for_email_log_retention():
    cron_jobs = worker.WorkerSettings.cron_jobs
    assert len(cron_jobs) == 1
    # arq's cron() wraps the coroutine in a CronJob whose .coroutine is the
    # original function -- confirm it points at email_log_retention and not
    # some other job.
    (job,) = cron_jobs
    assert job.coroutine is worker.email_log_retention


def test_worker_settings_cron_runs_daily_at_04_00_utc():
    (job,) = worker.WorkerSettings.cron_jobs
    assert job.hour == 4
    assert job.minute == 0


def test_worker_settings_has_startup_and_shutdown_hooks():
    assert worker.WorkerSettings.on_startup is worker.startup
    assert worker.WorkerSettings.on_shutdown is worker.shutdown


def test_worker_settings_uses_configured_redis_url():
    # RedisSettings doesn't round-trip back to a DSN, so just confirm it
    # was built (host/port present) rather than left as a default object.
    rs = worker.WorkerSettings.redis_settings
    assert rs.host is not None
    assert rs.port == 6379


# ── redis_url config default ─────────────────────────────────────────────

def test_redis_url_defaults_to_compose_service_name(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    from core.config import Settings

    s = Settings()
    assert s.redis_url == "redis://redis:6379/0"


# ── email_log_retention ──────────────────────────────────────────────────

class _FakeExecuteRecorder:
    """Stand-in for core.database.execute -- records the call instead of
    touching a real connection pool, and returns an asyncpg-style command
    tag so the row count is exercised too."""

    def __init__(self, tag: str = "DELETE 3"):
        self.calls = []
        self.tag = tag

    async def __call__(self, sql, *args):
        self.calls.append((sql, args))
        return self.tag


def test_email_log_retention_deletes_rows_older_than_365_days(monkeypatch):
    recorder = _FakeExecuteRecorder("DELETE 7")
    monkeypatch.setattr(worker, "execute", recorder)

    deleted = asyncio.run(worker.email_log_retention(ctx={}))

    assert deleted == 7
    assert len(recorder.calls) == 1
    sql, args = recorder.calls[0]
    assert "DELETE FROM email_log" in sql
    assert "created_at" in sql
    assert len(args) == 1  # the cutoff timestamp


def test_email_log_retention_handles_zero_rows(monkeypatch):
    recorder = _FakeExecuteRecorder("DELETE 0")
    monkeypatch.setattr(worker, "execute", recorder)

    deleted = asyncio.run(worker.email_log_retention(ctx={}))

    assert deleted == 0


def test_email_log_retention_tolerates_unexpected_command_tag(monkeypatch):
    """Never crash the cron job just because the tag couldn't be parsed."""
    recorder = _FakeExecuteRecorder("")
    monkeypatch.setattr(worker, "execute", recorder)

    deleted = asyncio.run(worker.email_log_retention(ctx={}))

    assert deleted == 0


# ── send_email_job ───────────────────────────────────────────────────────

def test_send_email_job_calls_mailer_send_with_all_args(monkeypatch):
    calls = []

    async def _fake_send(to, template, ctx, subject=None, related_user_id=None):
        calls.append((to, template, ctx, subject, related_user_id))
        return True

    monkeypatch.setattr(worker.mailer, "send", _fake_send)

    ok = asyncio.run(
        worker.send_email_job(
            {}, "kandidaat@example.com", "welkom_kandidaat", {"full_name": "Jan"},
            subject="Welkom", related_user_id=42,
        )
    )

    assert ok is True
    assert calls == [
        ("kandidaat@example.com", "welkom_kandidaat", {"full_name": "Jan"}, "Welkom", 42)
    ]


def test_send_email_job_returns_false_on_mailer_failure(monkeypatch):
    async def _fake_send(*a, **kw):
        return False

    monkeypatch.setattr(worker.mailer, "send", _fake_send)

    ok = asyncio.run(worker.send_email_job({}, "x@example.com", "welkom_kandidaat", {}))

    assert ok is False
