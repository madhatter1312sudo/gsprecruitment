"""
WS3a (e-mail en Google Sign-In) -- adversarial probes, written before the
builder's fix landed in this worktree. Same spirit as
tests/integration/test_ws_e10_round6_probes.py: run through the REAL
routers/services against a real Postgres, don't just confirm the
builder's own unit tests (tests/test_ws3_email_service.py,
tests/test_ws3_google_signin.py, tests/test_ws3_notify.py,
tests/test_email_templates.py), which this file deliberately never
imports from or relies on.

Every probe below stubs exactly one seam per concern: the outbound
network boundary (services.email_service's provider selection,
services.telegram's HTTP call, httpx/google-auth for the OAuth token
exchange and id_token verification). Everything else -- routing, request
validation, SQL, retry/logging -- runs for real.

Requires migrations 000 through 040 applied (see
tests/integration/conftest.py for local/CI setup). If 040_email_log has
not landed yet, every probe that needs the email_log table or
services/notify.py/services/email_templates.py is skipped with a reason
rather than weakened or silently passed.
"""
import importlib
import inspect
import logging
import pathlib
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from core import privacy
from core.config import settings
from core.database import execute, fetch_all, fetch_one
from core.security import decode_token, hash_token

pytestmark = pytest.mark.integration

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[2]  # tests/integration -> tests -> backend


def _migration_040_applied() -> bool:
    return (_BACKEND_ROOT / "migrations" / "040_email_log.py").exists()


_HAS_040 = _migration_040_applied()
_skip_no_040 = pytest.mark.skipif(
    not _HAS_040,
    reason="migrations/040_email_log.py not present yet in this worktree -- WS3a email_log/notify/templates "
    "probes need it; skipping rather than weakening the assertions below",
)

if _HAS_040:
    import services.email_service as email_service_module
    from services.email_service import EmailSendError
    from services import email_templates
    import routers.auth as auth_router
else:  # pragma: no cover -- only exercised while 040 is genuinely missing
    email_service_module = None
    EmailSendError = None
    email_templates = None
    auth_router = None


# ── shared helpers ─────────────────────────────────────────────────────────

_ip_counter = [0]


def _next_ip() -> str:
    """A fresh fake source IP per call. auth/public rate limits key on
    CF-Connecting-IP (core/ratelimit.py's first, unconditional branch) --
    a fixed IP would trip /lead's, /register's, /forgot-password's and
    /google/login's 3-10/minute limits well before this file finishes."""
    _ip_counter[0] += 1
    return f"203.0.{_ip_counter[0] // 256}.{_ip_counter[0] % 256}"


def _ip_header() -> dict:
    return {"CF-Connecting-IP": _next_ip()}


class _CapturingProvider:
    """Records every EmailMessage handed to it and always succeeds --
    stands in for services.email_service._get_provider() so no probe
    below ever makes a real Gmail/SMTP call."""

    name = "stub"

    def __init__(self):
        self.sent = []

    async def send(self, msg):
        self.sent.append(msg)
        return "stub-provider-id"


class _AlwaysFailProvider:
    """Fails every attempt with a RETRYABLE error whose message deliberately
    includes the raw recipient address -- the way a real bounce (SMTP 550,
    a Gmail API error body echoing the request) could. This is what
    actually exercises core.privacy.redact_emails() inside
    services.email_service._log_attempt(), not a synthetic message that
    was never going to contain an address in the first place."""

    name = "stub"

    def __init__(self):
        self.attempts = 0

    async def send(self, msg):
        self.attempts += 1
        raise EmailSendError(f"stub 503 rejecting recipient {msg.to}", retryable=True)


@pytest.fixture
def install_provider(monkeypatch):
    def _install(provider):
        monkeypatch.setattr(email_service_module, "_get_provider", lambda: provider)
        return provider

    return _install


@pytest.fixture(autouse=_HAS_040)
def _fast_retries(monkeypatch):
    """Zero out the real 0.5s/2s/8s backoff so the always-failing-provider
    probe doesn't cost 10+ wall-clock seconds. The retry *count* (4
    attempts: 1 initial + 3 retries) is what's under test, not the delay."""
    if email_service_module is not None:
        monkeypatch.setattr(email_service_module, "RETRY_BACKOFFS", (0.0, 0.0, 0.0))


@pytest.fixture
def capture_telegram(monkeypatch):
    """Replaces services.telegram._send (the one HTTP call every Telegram
    path funnels through) with a recorder -- no network, and lets a probe
    assert on exactly what text would have gone out."""
    import services.telegram as telegram_module

    calls = []

    async def _fake_send(text):
        calls.append(text)
        return True

    monkeypatch.setattr(telegram_module, "_send", _fake_send)
    return calls


def _email_log_rows(db_run, *, to_email=None, template=None, since=None):
    clauses, args = [], []
    if to_email is not None:
        args.append(privacy.email_hash(to_email))
        clauses.append(f"to_hash = ${len(args)}")
    if template is not None:
        args.append(template)
        clauses.append(f"template = ${len(args)}")
    if since is not None:
        args.append(since)
        clauses.append(f"created_at >= ${len(args)}")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return db_run(fetch_all, f"SELECT * FROM email_log {where} ORDER BY id", *args)


# ── 1. POST /api/v1/public/lead: email_log + no address leak ──────────────


@_skip_no_040
def test_lead_endpoint_ok_provider_logs_exactly_one_sent_row_no_address_leak(
    client, db_run, make_email, install_provider, monkeypatch, caplog,
):
    owner_email = make_email("owner-probe1-ok")
    lead_email = make_email("lead-probe1-ok")
    monkeypatch.setattr(settings, "owner_notify_email", owner_email)
    provider = install_provider(_CapturingProvider())
    caplog.set_level(logging.WARNING)

    resp = client.post(
        "/api/v1/public/lead",
        json={"name": "QA Probe Lead", "email": lead_email, "message": "Testbericht voor sonde."},
        headers=_ip_header(),
    )
    assert resp.status_code == 201, resp.text

    rows = _email_log_rows(db_run, to_email=owner_email)
    assert len(rows) == 1, f"expected exactly one email_log row for the owner mail, got {rows}"
    row = rows[0]
    assert row["status"] == "sent"
    assert row["error"] is None
    assert row["to_hash"] == privacy.email_hash(owner_email)

    assert len(provider.sent) == 1
    assert provider.sent[0].to == owner_email

    assert owner_email not in caplog.text


@_skip_no_040
def test_lead_endpoint_always_failing_provider_still_201_logs_failed_attempts_no_leak(
    client, db_run, make_email, install_provider, monkeypatch, caplog,
):
    """Best-effort contract: a notification that fails every retry must
    never fail the lead submission itself. Expectation on row count,
    documented because migrations/040_email_log.py's schema has no
    `attempts` column -- there is nowhere to fold multiple tries into one
    row, so the only structurally possible behaviour is one row per
    attempt: RETRY_BACKOFFS has 3 entries ("retry 3x"), so 1 initial +
    3 retries == 4 rows, all status='failed'."""
    owner_email = make_email("owner-probe1-fail")
    monkeypatch.setattr(settings, "owner_notify_email", owner_email)
    provider = install_provider(_AlwaysFailProvider())
    caplog.set_level(logging.WARNING)

    resp = client.post(
        "/api/v1/public/lead",
        json={"name": "QA Probe Lead Fail", "email": make_email("lead-probe1-fail"), "message": "Testbericht."},
        headers=_ip_header(),
    )
    assert resp.status_code == 201, resp.text

    rows = _email_log_rows(db_run, to_email=owner_email)
    assert len(rows) == 4, f"expected 4 attempt rows (1 initial + 3 retries), got {len(rows)}: {rows}"
    assert all(r["status"] == "failed" for r in rows)
    assert provider.attempts == 4

    for r in rows:
        assert owner_email not in (r["error"] or ""), f"raw address leaked into email_log.error: {r['error']!r}"
    assert owner_email not in caplog.text


# ── 2. POST /api/auth/register: owner_notify mail + PII-free Telegram ─────


@_skip_no_040
def test_register_with_owner_notify_email_sends_one_owner_mail_with_deeplink(
    client, db_run, make_email, install_provider, capture_telegram, monkeypatch,
):
    owner_email = make_email("owner-probe2")
    monkeypatch.setattr(settings, "owner_notify_email", owner_email)
    provider = install_provider(_CapturingProvider())
    candidate_email = make_email("register-probe2")

    resp = client.post(
        "/api/auth/register",
        json={"email": candidate_email, "password": "Str0ngPassw0rd!", "full_name": "QA Probe Kandidaat",
              "role": "candidate"},
        headers=_ip_header(),
    )
    assert resp.status_code == 201, resp.text

    owner_msgs = [m for m in provider.sent if m.to == owner_email]
    assert len(owner_msgs) == 1, f"expected exactly one mail to the owner, got {len(owner_msgs)}"
    deeplink = f"{settings.frontend_url}/admin/#candidates"
    assert deeplink in owner_msgs[0].text, owner_msgs[0].text

    # The pre-existing verify_email send must be unaffected by WS3.
    verify_msgs = [m for m in provider.sent if m.to == candidate_email]
    assert len(verify_msgs) == 1


@_skip_no_040
def test_register_without_owner_notify_email_sends_no_owner_mail_telegram_stays_pii_free(
    client, db_run, make_email, install_provider, capture_telegram, monkeypatch,
):
    monkeypatch.setattr(settings, "owner_notify_email", "")
    provider = install_provider(_CapturingProvider())
    full_name = "QA Probe Zonder Ownermail"
    candidate_email = make_email("register-probe2b")
    t0 = datetime.now(timezone.utc)

    resp = client.post(
        "/api/auth/register",
        json={"email": candidate_email, "password": "Str0ngPassw0rd!", "full_name": full_name, "role": "candidate"},
        headers=_ip_header(),
    )
    assert resp.status_code == 201, resp.text

    rows = _email_log_rows(db_run, template="owner_notify", since=t0)
    assert rows == [], f"owner_notify was sent despite OWNER_NOTIFY_EMAIL being unset: {rows}"
    assert not any(m.to == "" for m in provider.sent)

    assert len(capture_telegram) == 1, capture_telegram
    text = capture_telegram[0]
    assert full_name not in text, text
    assert candidate_email not in text, text


# ── 3. GET /api/auth/google/login ──────────────────────────────────────────


@_skip_no_040
def test_google_login_not_configured_redirects_no_json_503(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")

    resp = client.get("/api/auth/google/login", headers=_ip_header(), follow_redirects=False)

    assert resp.status_code != 503
    assert resp.status_code in (302, 307), resp.text
    assert resp.headers["location"] == f"{settings.frontend_url}/?google_auth_error=not_configured"


@_skip_no_040
def test_google_login_configured_redirects_to_google_with_configured_redirect_uri_and_state_jwt(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "qa-test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "qa-test-client-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "https://qa.example.invalid/api/auth/google/callback")

    resp = client.get(
        "/api/auth/google/login",
        params={"role": "client", "next": "/client/dashboard"},
        headers=_ip_header(),
        follow_redirects=False,
    )

    assert resp.status_code in (302, 307), resp.text
    location = resp.headers["location"]
    assert location.startswith("https://accounts.google.com/"), location
    qs = parse_qs(urlparse(location).query)
    assert qs["redirect_uri"][0] == "https://qa.example.invalid/api/auth/google/callback"

    payload = decode_token(qs["state"][0])
    assert payload is not None, "state must be a JWT this backend's own secret can decode"
    assert payload["role"] == "client"
    assert payload["next"] == "/client/dashboard"
    assert resp.cookies.get("google_oauth_state") == payload["nonce"]


@_skip_no_040
def test_google_login_protocol_relative_next_is_dropped_not_carried_in_state(client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "qa-test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "qa-test-client-secret")

    resp = client.get(
        "/api/auth/google/login",
        params={"role": "candidate", "next": "//evil.com"},
        headers=_ip_header(),
        follow_redirects=False,
    )

    qs = parse_qs(urlparse(resp.headers["location"]).query)
    payload = decode_token(qs["state"][0])
    assert not payload.get("next"), f"protocol-relative next leaked into state: {payload!r}"


# ── 4. GET /api/auth/google/callback ───────────────────────────────────────


class _FakeGoogleTokenResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient for the one call google_callback()
    makes with it (the token-exchange POST) -- id_token verification is
    stubbed separately (it never goes through httpx)."""

    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, data=None):
        return self._response


def _configure_google(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "qa-test-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "qa-test-client-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "https://api.gsprecruitment.nl/api/auth/google/callback")


def _stub_token_exchange_and_idinfo(monkeypatch, *, email, email_verified=True, name=None):
    monkeypatch.setattr(
        auth_router.httpx, "AsyncClient",
        lambda *a, **kw: _FakeAsyncClient(_FakeGoogleTokenResponse(200, {"id_token": "fake-id-token"})),
    )

    def _verify(id_token_str, request, client_id):
        return {"email": email, "email_verified": email_verified, "name": name or email.split("@")[0]}

    monkeypatch.setattr(auth_router.google_id_token, "verify_oauth2_token", _verify)


def _do_google_login(client, *, role="candidate", next_path=None):
    params = {"role": role}
    if next_path is not None:
        params["next"] = next_path
    resp = client.get("/api/auth/google/login", params=params, headers=_ip_header(), follow_redirects=False)
    assert resp.status_code in (302, 307), resp.text
    state = parse_qs(urlparse(resp.headers["location"]).query)["state"][0]
    nonce = resp.cookies.get("google_oauth_state")
    assert nonce, "google/login must set the google_oauth_state cookie"
    return state, nonce


def _do_google_callback(client, *, state, cookie_nonce, code="fake-code"):
    """Sets the cookie on the client instance itself rather than relying on
    TestClient's normal Set-Cookie-response persistence: google_login's
    cookie is `secure=True`, and httpx's jar (correctly) never replays a
    Secure cookie back over TestClient's plain http://testserver base_url,
    so a same-client follow-up request would silently carry no cookie at
    all regardless of what the login step actually set. Always clears
    first so a previous sub-test's cookie on this shared client can never
    bleed into this one. `cookie_nonce=None` sends no google_oauth_state
    cookie at all (the "browser never carried it back" case)."""
    client.cookies.clear()
    if cookie_nonce is not None:
        client.cookies.set("google_oauth_state", cookie_nonce)
    return client.get(
        "/api/auth/google/callback", params={"state": state, "code": code},
        headers=_ip_header(), follow_redirects=False,
    )


@_skip_no_040
def test_google_callback_state_cookie_mismatch_is_invalid_state(client, monkeypatch):
    _configure_google(monkeypatch)
    state, nonce = _do_google_login(client, role="candidate")

    resp = _do_google_callback(client, state=state, cookie_nonce="tampered-" + nonce)

    assert resp.headers["location"] == f"{settings.frontend_url}/?google_auth_error=invalid_state"


@_skip_no_040
def test_google_callback_missing_state_cookie_is_invalid_state(client, monkeypatch):
    _configure_google(monkeypatch)
    state, nonce = _do_google_login(client, role="candidate")

    resp = _do_google_callback(client, state=state, cookie_nonce=None)

    assert resp.headers["location"] == f"{settings.frontend_url}/?google_auth_error=invalid_state"


@_skip_no_040
def test_google_callback_new_user_role_client_creates_client_account_and_redirects_client_path(
    client, db_run, make_email, monkeypatch,
):
    _configure_google(monkeypatch)
    new_email = make_email("google-new-client")
    state, nonce = _do_google_login(client, role="client")
    _stub_token_exchange_and_idinfo(monkeypatch, email=new_email, email_verified=True, name="QA Google Client")

    resp = _do_google_callback(client, state=state, cookie_nonce=nonce)

    assert resp.status_code in (302, 307), resp.text
    assert resp.headers["location"].startswith(f"{settings.frontend_url}/client/#google_auth="), resp.headers["location"]

    user_row = db_run(fetch_one, "SELECT id, role FROM users WHERE email = $1", new_email)
    assert user_row is not None
    assert user_row["role"] == "client"
    link_row = db_run(fetch_one, "SELECT client_id FROM user_clients WHERE user_id = $1", user_row["id"])
    assert link_row is not None, "new client account must be linked via user_clients"


@_skip_no_040
def test_google_callback_existing_candidate_keeps_own_role_ignoring_requested_client_role(
    client, db_run, make_candidate_user, monkeypatch,
):
    _configure_google(monkeypatch)
    existing = make_candidate_user()
    state, nonce = _do_google_login(client, role="client")  # state requests role=client
    _stub_token_exchange_and_idinfo(monkeypatch, email=existing["email"], email_verified=True)

    resp = _do_google_callback(client, state=state, cookie_nonce=nonce)

    assert resp.status_code in (302, 307), resp.text
    assert resp.headers["location"].startswith(f"{settings.frontend_url}/#google_auth="), resp.headers["location"]

    role_row = db_run(fetch_one, "SELECT role FROM users WHERE id = $1", existing["id"])
    assert role_row["role"] == "candidate", "an existing account's role must never change via Google sign-in"


@_skip_no_040
def test_google_callback_email_not_verified_reports_error_code(client, make_email, monkeypatch):
    _configure_google(monkeypatch)
    state, nonce = _do_google_login(client, role="candidate")
    _stub_token_exchange_and_idinfo(monkeypatch, email=make_email("google-unverified"), email_verified=False)

    resp = _do_google_callback(client, state=state, cookie_nonce=nonce)

    assert resp.headers["location"] == f"{settings.frontend_url}/?google_auth_error=email_not_verified"


# ── 5. Forgot/reset password: hashed reset_token ──────────────────────────


@_skip_no_040
def test_forgot_password_stores_hashed_token_raw_token_works_stored_hash_does_not(
    client, db_run, make_candidate_user, install_provider,
):
    user = make_candidate_user()
    provider = install_provider(_CapturingProvider())

    resp = client.post("/api/auth/forgot-password", json={"email": user["email"]}, headers=_ip_header())
    assert resp.status_code == 200, resp.text

    reset_msgs = [m for m in provider.sent if m.to == user["email"]]
    assert len(reset_msgs) == 1
    match = re.search(r"token=([A-Za-z0-9_\-]+)", reset_msgs[0].text)
    assert match, f"no reset token found in the mail body: {reset_msgs[0].text!r}"
    raw_token = match.group(1)

    row = db_run(fetch_one, "SELECT reset_token FROM users WHERE id = $1", user["id"])
    stored = row["reset_token"]
    assert stored != raw_token, "users.reset_token must never store the raw token"
    assert stored == hash_token(raw_token)

    resp_with_hash = client.post(
        "/api/auth/reset-password", json={"token": stored, "new_password": "An0therStrongPassw0rd!"},
        headers=_ip_header(),
    )
    assert resp_with_hash.status_code == 400, resp_with_hash.text

    resp_with_raw = client.post(
        "/api/auth/reset-password", json={"token": raw_token, "new_password": "An0therStrongPassw0rd!"},
        headers=_ip_header(),
    )
    assert resp_with_raw.status_code == 200, resp_with_raw.text


# ── 6. services/email_templates.py ─────────────────────────────────────────

_GENERIC_CTX = {
    "full_name": "<b>Voorbeeld</b>",
    "link": "https://gsprecruitment.nl/voorbeeld?token=abc",
    "ttl_hours": 24,
    "job_title": 'Embedded Software Engineer <script>alert(1)</script>',
    "inviter_company": "Voorbeeld & Co",
    "event_label": "Testmelding",
    "detail": "Detail met <b>opmaak</b> & een teken",
    "deeplink": "https://gsprecruitment.nl/admin/#leads",
}


@_skip_no_040
def test_verify_email_template_escapes_html_in_full_name():
    ctx = {"full_name": "<b>x</b>", "link": "https://gsprecruitment.nl/verify?token=t", "ttl_hours": 24}
    subject, text, html = email_templates.render("verify_email", ctx, "nl")
    assert "&lt;b&gt;x&lt;/b&gt;" in html
    assert "<b>x</b>" not in html


@_skip_no_040
@pytest.mark.parametrize("lang", ["nl", "en"])
def test_every_template_has_nonempty_subject_kvk_footer_and_no_em_dash(lang):
    names = sorted(email_templates._RENDERERS.keys())
    assert names, "services/email_templates.py registers no templates at all"
    for name in names:
        subject, text, html = email_templates.render(name, dict(_GENERIC_CTX), lang)
        assert subject.strip(), f"{name}/{lang} has an empty subject"
        assert "KvK 75545586" in html, f"{name}/{lang} html is missing the shared footer"
        for label, value in (("subject", subject), ("text", text), ("html", html)):
            assert "\u2014" not in value, f"{name}/{lang} {label} contains an em dash (U+2014): {value!r}"


@_skip_no_040
def test_unknown_template_name_raises_rather_than_silently_producing_empty_mail():
    with pytest.raises(KeyError):
        email_templates.render("does_not_exist_ws3a", {}, "nl")


# ── 7. Draft-only guard: send_email/send_template call-site whitelist ──────

_SCAN_PACKAGES = ("routers", "services")
_NEEDLES = ("send_email(", "send_template(")

# Every function outside routers/outreach.py that may call
# send_email()/send_template() -- each sends to an address the recipient
# supplied themselves (registration, talentpool opt-in, forgot-password,
# an already-opted-in talentpool member, a team member the client itself
# invited) or to the operator's own OWNER_NOTIFY_EMAIL. None of them may
# ever address a candidates.email/client_prospects.contact_email row this
# backend itself sourced -- that path stays routers/outreach.py's alone,
# gated on a human's POST .../approve.
_ALLOWED_SEND_CALL_SITES = {
    ("routers.auth", "_send_verification_email"),
    ("routers.auth", "forgot_password"),
    ("routers.client", "invite_team_member"),
    ("routers.public", "_send_talentpool_confirm_email"),
    ("services.scheduler", "talentpool_reminder_job"),
    ("services.notify", "_notify_owner_email"),
    ("routers.outreach", "approve_draft"),
}


def _iter_backend_modules():
    for package in _SCAN_PACKAGES:
        pkg_dir = _BACKEND_ROOT / package
        if not pkg_dir.is_dir():
            continue
        for path in sorted(pkg_dir.glob("*.py")):
            if path.stem == "__init__":
                continue
            module_name = f"{package}.{path.stem}"
            yield module_name, importlib.import_module(module_name)


def test_send_email_and_send_template_called_only_from_the_allowed_sites():
    """Structural, source-level scan (style of
    tests/test_ws_e10_no_unapproved_purge_path.py's _functions_calling) --
    a future call site added anywhere under routers/ or services/ fails
    here even if no test happens to exercise the branch it's in."""
    hits = set()
    for module_name, module in _iter_backend_modules():
        for name, obj in vars(module).items():
            if not (inspect.isfunction(obj) and inspect.getmodule(obj) is module):
                continue
            try:
                src = inspect.getsource(obj)
            except (OSError, TypeError):
                continue
            if any(needle in src for needle in _NEEDLES):
                hits.add((module_name, name))

    unexpected = hits - _ALLOWED_SEND_CALL_SITES
    assert not unexpected, (
        f"send_email()/send_template() is called from an un-reviewed site: {sorted(unexpected)} -- "
        "add it to _ALLOWED_SEND_CALL_SITES only after confirming it never sends to a "
        "candidates.email or client_prospects.contact_email row without a human approval step"
    )

    missing = _ALLOWED_SEND_CALL_SITES - hits
    assert not missing, (
        f"expected call site(s) no longer call send_email()/send_template(): {sorted(missing)} -- "
        "update _ALLOWED_SEND_CALL_SITES if this removal is intentional"
    )

    for module_name, func_name in hits:
        if module_name == "routers.outreach":
            continue
        module = importlib.import_module(module_name)
        src = inspect.getsource(getattr(module, func_name))
        assert "client_prospects" not in src, (
            f"{module_name}.{func_name} calls send_email()/send_template() and also references "
            "client_prospects -- looks like a sourced-prospect send outside routers/outreach.py"
        )
