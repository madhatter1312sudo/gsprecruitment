#!/usr/bin/env python3
"""
WS3 regression check (security-auditor HIGH + code-reviewer finding):
routers/auth.py's google_callback() redirects a successful Google
Sign-In straight to https://gsprecruitment.nl/candidate/#google_auth=<jwt>
or /client/#google_auth=<jwt>. Those two pages load only gsp-util.js,
auth.js and app.js -- handleGoogleAuthCallback() used to live only in
website/script.js, so it never ran there, and Auth.requireAuth() (which
runs first, before any real content) saw no stored token yet and bounced
the browser back to '/', throwing the fragment (and the JWT in it) away
with it. Net result: Google Sign-In never actually logged anyone in from
the site's own button, and a 60-minute-JWT sat in the browser history at
the portal URL.

The fix moved a version of that fragment consumption into auth.js itself
(Auth.consumeGoogleAuthRedirect(), called at the top of requireAuth()) so
/candidate/ and /client/ handle it directly. This script drives Chromium
against the real static site and proves, for both roles, that landing on
the portal URL with a #google_auth=<jwt> fragment ends with the token
actually stored in localStorage and the fragment stripped from the URL --
not a bounce back to '/' with an empty gsp_token.

Usage: python3 scripts/google_auth_fragment_check.py
"""
import http.server
import json
import socket
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "website"

import os

CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH") or (
    "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
)

# Not a real JWT signature -- consumeGoogleAuthRedirect() never verifies
# the token itself, it only forwards it to /auth/me (mocked below) and
# stores whatever comes back. exp is 2125 so isTokenExpired() (which does
# parse the payload locally) accepts it on the post-reload pass.
FAKE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxIiwicm9sZSI6ImNhbmRpZGF0ZSIsImV4cCI6NDg5NTE2ODAwMH0."
    "fake-signature-for-local-check-only"
)


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port):
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(WEBSITE), **kw)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def check_role(pw, base, role):
    user = {
        "id": 1, "role": role, "email": f"fragment-check-{role}@example.invalid",
        "full_name": "Fragment Check", "is_verified": True,
    }
    browser = pw.chromium.launch(executable_path=CHROMIUM_PATH or None, headless=True)
    context = browser.new_context()
    page = context.new_page()

    # Cookie consent must be granted for setAuth() to actually persist
    # anything (see auth.js getToken()/getUser()'s own test-trap note) --
    # otherwise a real first-time visitor's toast-and-refuse path would be
    # indistinguishable from this bug in the token-loss check below.
    page.add_init_script("try { localStorage.setItem('gsp_cookie_consent', 'true'); } catch (e) {}")

    # One handler for every request: serve auth/me from the fake user
    # above, let 127.0.0.1 (the static site itself) through, and abort
    # everything else. This sandbox's network can hang for a long time
    # reaching the real API, Google Fonts or a CDN, and a blocking
    # stylesheet <link> would stall domcontentloaded itself -- same
    # reasoning as scripts/csp_violation_check.py's own route_handler.
    def route_handler(route, request):
        from urllib.parse import urlparse
        if request.url.startswith("https://api.gsprecruitment.nl/api/auth/me"):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(user))
            return
        if urlparse(request.url).netloc.startswith("127.0.0.1"):
            route.continue_()
            return
        route.abort()

    page.route("**/*", route_handler)

    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    page.goto(f"{base}/{role}/#google_auth={FAKE_JWT}", wait_until="domcontentloaded", timeout=10000)
    try:
        page.wait_for_function("() => localStorage.getItem('gsp_token') !== null", timeout=5000)
    except Exception:
        pass  # evaluated below regardless, for a clear failure message

    token = page.evaluate("() => localStorage.getItem('gsp_token')")
    stored_user_raw = page.evaluate("() => localStorage.getItem('gsp_user')")
    final_hash = page.evaluate("() => window.location.hash")
    final_url = page.url

    context.close()
    browser.close()

    problems = []
    if token != FAKE_JWT:
        problems.append(f"gsp_token after landing on /{role}/#google_auth=... is {token!r}, expected the JWT to be stored")
    if not stored_user_raw:
        problems.append("gsp_user was never stored")
    if final_hash:
        problems.append(f"URL fragment was not stripped: {final_hash!r}")
    if f"/{role}/" not in final_url:
        problems.append(f"page did not stay on the portal path, ended on {final_url!r}")
    return problems


def check_no_consent(pw, base):
    """Chief-of-staff FIX FIRST 1: a visitor who has not accepted the cookie
    banner is the ordinary first-time case, not an edge case -- the Google
    button is right there on the same page as the still-open banner.
    consumeGoogleAuthRedirect() used to call setAuth() and reload()
    unconditionally; setAuth() silently refuses to write to localStorage
    without consent, so the reload landed back on requireAuth()'s "no
    token" branch and bounced the visitor to '/' with no toast and no
    error code -- a login that fails with no visible sign it failed. This
    seeds no consent at all (unlike check_role() above) and asserts the
    fixed behaviour instead: no token is ever stored, and the visitor ends
    up on '/' with ?google_auth_error=cookie_consent so script.js can show
    a toast."""
    browser = pw.chromium.launch(executable_path=CHROMIUM_PATH or None, headless=True)
    context = browser.new_context()
    page = context.new_page()

    def route_handler(route, request):
        from urllib.parse import urlparse
        if request.url.startswith("https://api.gsprecruitment.nl/api/auth/me"):
            route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({
                    "id": 1, "role": "candidate", "email": "fragment-check-noconsent@example.invalid",
                    "full_name": "Fragment Check", "is_verified": True,
                }),
            )
            return
        if urlparse(request.url).netloc.startswith("127.0.0.1"):
            route.continue_()
            return
        route.abort()

    page.route("**/*", route_handler)

    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    page.goto(f"{base}/candidate/#google_auth={FAKE_JWT}", wait_until="domcontentloaded", timeout=10000)
    try:
        # requireAuth() -> consumeGoogleAuthRedirect() lands here via
        # `window.location.href = '/?google_auth_error=cookie_consent'`;
        # the / page's own script.js (handleGoogleAuthCallback) then
        # strips that query string with replaceState() as soon as it
        # reads it (same "don't repeat the toast on refresh" behaviour
        # documented for every other google_auth_error code) and shows
        # the toast instead -- so the toast, not the URL, is the durable
        # evidence the error code actually arrived.
        page.wait_for_selector(".toast-error", timeout=5000)
    except Exception:
        pass  # evaluated below regardless, for a clear failure message

    token = page.evaluate("() => localStorage.getItem('gsp_token')")
    final_path = page.evaluate("() => window.location.pathname")
    toast_text = page.evaluate(
        "() => document.querySelector('.toast-error span:last-child')?.textContent || null"
    )

    context.close()
    browser.close()

    problems = []
    if token is not None:
        problems.append(f"gsp_token was stored ({token!r}) even though cookie consent was never granted")
    if final_path != "/":
        problems.append(f"page did not land on '/': {final_path!r}")
    if not toast_text:
        problems.append("no error toast was shown -- the failure is silent, exactly the bug this guards against")
    return problems


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FAIL: playwright not installed")
        sys.exit(1)

    port = find_free_port()
    httpd = start_server(port)
    base = f"http://127.0.0.1:{port}"

    failures = {}
    with sync_playwright() as pw:
        for role in ("candidate", "client"):
            problems = check_role(pw, base, role)
            status = "OK" if not problems else "FAIL"
            print(f"  [{status}] /{role}/#google_auth=<jwt>")
            for p in problems:
                print(f"         {p}")
            if problems:
                failures[role] = problems

        no_consent_problems = check_no_consent(pw, base)
        status = "OK" if not no_consent_problems else "FAIL"
        print(f"  [{status}] /candidate/#google_auth=<jwt> without cookie consent")
        for p in no_consent_problems:
            print(f"         {p}")
        if no_consent_problems:
            failures["no_consent"] = no_consent_problems

    httpd.shutdown()

    if failures:
        print("\nFAIL: Google Sign-In redirect landing on the portal path did not store a session.")
        sys.exit(1)

    print("\nPASS: both /candidate/ and /client/ consume #google_auth=<jwt> and end up with a stored session,")
    print("      and a visit without cookie consent fails visibly instead of silently.")


if __name__ == "__main__":
    main()
