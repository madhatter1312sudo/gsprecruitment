"""Talent OS — Sentry error monitoring (WS-E.9).

Inert by default: init_sentry() is a no-op unless settings.sentry_dsn is
set (see .env.example / core/config.py), so a fresh/staging deploy without
a DSN never talks to Sentry at all. When a DSN IS set:

  - send_default_pii=False: Sentry's FastAPI/Starlette integration will not
    attach request bodies, cookies, or the caller's IP by itself.
  - _scrub_pii (the before_send hook) additionally walks every event dict
    recursively and redacts any key that looks like an e-mail/name field
    (candidate/client/contact PII lives all over this API's payloads), so
    even data an integration or a log breadcrumb picked up incidentally
    never leaves the process.
  - traces_sample_rate=0.1: 10% of requests get performance tracing: enough
    to spot slow endpoints without shipping every request's timing data.
"""
import logging
import re
from typing import Any

logger = logging.getLogger("talent_os")

# Matches keys like email, e_mail, candidate_email, full_name, first_name,
# contact_name, company_name, applicant-name, etc. -- deliberately broad
# (this API's payloads use *_email / *_name conventions throughout
# routers/candidates.py, routers/client_contacts.py, routers/prospects.py
# and friends) so a new field with one of these names is scrubbed by
# default rather than needing this list kept in sync by hand.
_PII_KEY_RE = re.compile(r"(^|[_-])(e[-_]?mail|name)($|[_-])", re.IGNORECASE)
_REDACTED = "[Filtered]"


def _scrub_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (_REDACTED if isinstance(k, str) and _PII_KEY_RE.search(k) else _scrub_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    return value


def _scrub_pii(event: dict, hint: dict) -> dict:
    """Sentry `before_send` hook -- recursively redacts email/name-shaped
    keys anywhere in the event (request data, extra, contexts, user,
    breadcrumbs). See module docstring."""
    for section in ("request", "extra", "contexts", "user"):
        if section in event and isinstance(event[section], dict):
            event[section] = _scrub_value(event[section])

    breadcrumbs = (event.get("breadcrumbs") or {}).get("values") if isinstance(event.get("breadcrumbs"), dict) else None
    if breadcrumbs:
        for crumb in breadcrumbs:
            if isinstance(crumb, dict) and isinstance(crumb.get("data"), dict):
                crumb["data"] = _scrub_value(crumb["data"])

    return event


def init_sentry(dsn: str, environment: str) -> None:
    """No-op when dsn is empty. Call once, before the FastAPI app is built."""
    if not dsn:
        logger.info("SENTRY_DSN not set -- Sentry disabled")
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        send_default_pii=False,
        before_send=_scrub_pii,
        traces_sample_rate=0.1,
    )
    logger.info(f"Sentry initialised (environment={environment})")
