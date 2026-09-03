#!/usr/bin/env python3
"""
WS-A.9b (M1) verification: serve website/ locally, inject the enforced
Content-Security-Policy from website/_headers as a <meta http-equiv> tag
(Cloudflare Workers Static Assets applies the real header in production;
python3 -m http.server can't send custom headers, so a meta tag is the
closest local equivalent -- it enforces the same script-src/style-src/etc.
restrictions in the browser), open every page under website/ in Chromium,
and fail if any `securitypolicyviolation` event or console error fires.

For the candidate/client/admin portals, a fake JWT is seeded into
localStorage first so Auth.requireAuth() lets the page's real JS run
instead of immediately redirecting to the public site.

Usage: python3 scripts/csp_violation_check.py
Exits non-zero if any page reports a CSP violation or a page/console error.

Known sandbox limitation: cdnjs.cloudflare.com can be blocked from this
environment's outbound network. A failed *network request* to an allowed
CDN host (cdn.jsdelivr.net, cdnjs.cloudflare.com, fonts.gstatic.com,
fonts.googleapis.com) is NOT a CSP violation -- CSP only blocks otherwise
per policy, it doesn't guarantee the request succeeds -- so those are
logged as warnings, not failures. Only actual `securitypolicyviolation`
events and unrelated console errors fail the run.
"""
import http.server
import pathlib
import json
import re
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "website"
HEADERS_FILE = WEBSITE / "_headers"
CHROMIUM_PATH = "/opt/pw-browsers/chromium"

ALLOWED_CDN_HOSTS = {
    "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
}


def extract_csp():
    text = HEADERS_FILE.read_text()
    m = re.search(r"^\s*Content-Security-Policy:\s*(.+)$", text, re.M)
    if not m:
        print("FAIL: no enforced Content-Security-Policy line found in website/_headers")
        sys.exit(1)
    return m.group(1).strip()


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_served_copy(csp: str):
    """Copy website/ to a temp dir with the enforced CSP injected as a
    <meta http-equiv> into every .html file. Serving a pre-built copy
    avoids intercepting document requests inside a Playwright route
    handler (route.fetch() from the handler stalled the crawl)."""
    import shutil, tempfile
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="gsp-csp-"))
    shutil.copytree(WEBSITE, tmp / "site", dirs_exist_ok=True)
    for f in (tmp / "site").rglob("*.html"):
        f.write_text(inject_csp_meta(f.read_text(encoding="utf-8"), csp), encoding="utf-8")
    return tmp / "site"


def start_server(port, serve_dir=None):
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(
        *a, directory=str(serve_dir or WEBSITE), **kw
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def inject_csp_meta(html: str, csp: str) -> str:
    meta = f'<meta http-equiv="Content-Security-Policy" content="{csp}">'
    if "<head>" in html:
        return html.replace("<head>", "<head>\n" + meta, 1)
    return meta + html


FAKE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxIiwicm9sZSI6ImNhbmRpZGF0ZSIsImV4cCI6NDg5NTE2ODAwMH0."
    "fake-signature-for-local-csp-check-only"
)


def seed_auth(page, role):
    # Matches the shape auth.js expects (see website/auth.js) closely enough
    # to get past requireAuth()'s redirect so the portal's real JS runs.
    user = {"id": 1, "role": role, "email": f"csp-check-{role}@example.invalid",
            "full_name": "CSP Check", "is_verified": True}
    page.add_init_script(
        f"""
        try {{
          localStorage.setItem('gsp_token', {json.dumps(FAKE_JWT)});
          localStorage.setItem('gsp_user', {json.dumps(json.dumps(user))});
        }} catch (e) {{}}
        """
    )


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FAIL: playwright not installed")
        sys.exit(1)

    csp = extract_csp()
    print(f"Enforced CSP under test:\n  {csp}\n")

    port = find_free_port()
    httpd = start_server(port, build_served_copy(csp))
    base = f"http://127.0.0.1:{port}"

    html_files = sorted(WEBSITE.rglob("*.html"))
    pages = []
    for f in html_files:
        rel = f.relative_to(WEBSITE).as_posix()
        role = None
        if rel.startswith("candidate/"):
            role = "candidate"
        elif rel.startswith("client/"):
            role = "client"
        elif rel.startswith("admin/"):
            role = "admin"
        pages.append((rel, role))

    violations = []  # (page, message)
    console_errors = []  # (page, message)
    network_warnings = []  # (page, url)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM_PATH, headless=True)
        for rel, role in pages:
            context = browser.new_context()

            # 1) Inject the enforced CSP as a <meta http-equiv> into every
            #    local .html response -- python -m http.server can't send
            #    custom headers, so this is the closest local equivalent
            #    and enforces the same script-src/style-src/etc.
            #    restrictions in the browser (the earlier version of this
            #    script defined inject_csp_meta() but never called it,
            #    which meant CSP wasn't actually being enforced during the
            #    crawl -- fixed here).
            # 2) Short-circuit every external request instead of letting it
            #    hit the real network: this sandbox's browser network stack
            #    can hang for a long time reaching cdn.jsdelivr.net /
            #    cdnjs.cloudflare.com / fonts.googleapis.com, and a classic
            #    (non-async/defer) <script> that follows a pending
            #    stylesheet in the DOM blocks execution -- and so blocks
            #    domcontentloaded -- until that stylesheet settles. CSP
            #    allow/deny is decided before the request is ever
            #    dispatched, so aborting it here doesn't affect whether a
            #    securitypolicyviolation event fires; it only stops the
            #    hang.
            def route_handler(route, request, rel=rel):
                url = request.url
                host = urlparse(url).netloc
                if host.startswith("127.0.0.1"):
                    route.continue_()
                    return
                route.abort()

            context.route("**/*", route_handler)

            page = context.new_page()
            if role:
                seed_auth(page, role)

            page_violations = []
            page_console_errors = []

            def on_console(msg, rel=rel):
                if msg.type == "error":
                    text = msg.text
                    # Benign in a bare `python -m http.server` sandbox: no
                    # favicon route, and any real backend call to
                    # api.gsprecruitment.nl can't succeed from here. Neither
                    # is a CSP violation.
                    if "favicon" in text.lower():
                        return
                    # frame-ancestors can only be delivered via the real HTTP
                    # header, never via <meta> (browsers ignore it there and
                    # log a warning) -- expected side effect of this script's
                    # local meta-tag CSP injection, not a real gap: the
                    # actual header set by website/_headers does carry
                    # frame-ancestors 'none' in production.
                    if "frame-ancestors" in text and "<meta>" in text:
                        return
                    # net::ERR_FAILED here is this script's own route_handler
                    # deliberately aborting every external request so the
                    # crawl doesn't hang on this sandbox's network reaching
                    # cdn.jsdelivr.net/cdnjs.cloudflare.com/fonts.*.com --
                    # already surfaced separately as a network_warnings
                    # entry, not a CSP violation.
                    if "net::ERR_FAILED" in text:
                        return
                    # website/blog/00N-*.html are pre-existing static
                    # redirect stubs: <meta http-equiv="refresh" ...
                    # url=post?slug=...">, which the production Cloudflare
                    # Worker rewrites but `python3 -m http.server` has no
                    # routing for, so it 404s here (Chrome's "Failed to load
                    # resource" console message doesn't include the URL, so
                    # this is matched by page rather than message text). Not
                    # a CSP issue and not introduced by WS-A.9b.
                    if rel.startswith("blog/0") and "404" in text:
                        return
                    page_console_errors.append(text)

            def on_pageerror(exc, rel=rel):
                page_console_errors.append(f"pageerror: {exc}")

            def on_requestfailed(request, rel=rel):
                url = request.url
                host = urlparse(url).netloc
                if host in ALLOWED_CDN_HOSTS or host == "api.gsprecruitment.nl":
                    network_warnings.append((rel, url))

            page.on("console", on_console)
            page.on("pageerror", on_pageerror)
            page.on("requestfailed", on_requestfailed)

            # Collect securitypolicyviolation events fired in-page (the meta
            # tag enforces CSP but doesn't send violation reports anywhere
            # by itself -- listen for the DOM event instead).
            page.add_init_script(
                """
                window.__cspViolations = [];
                document.addEventListener('securitypolicyviolation', (e) => {
                  window.__cspViolations.push(
                    e.violatedDirective + ' blocked ' + e.blockedURI + ' on ' + location.pathname
                  );
                });
                """
            )

            try:
                # "domcontentloaded" rather than "load"/"networkidle": every
                # page pulls the Google Fonts stylesheet
                # (fonts.googleapis.com), which this sandbox's network can
                # be slow enough to reach that "load" never fires inside a
                # reasonable timeout, and several portal pages
                # (candidate/client/admin) poll or keep background requests
                # open so "networkidle" never settles either. All the
                # inline-script/onclick= work under test here has already
                # run by DOMContentLoaded; the settle wait below covers
                # async fetch()-driven rendering on top of that.
                page.goto(f"{base}/{rel}", wait_until="domcontentloaded", timeout=10000)
            except Exception as e:
                page_console_errors.append(f"navigation error: {e}")

            # Give any async post-load JS (fetch()-driven rendering, etc.)
            # a moment to run and potentially trip a violation.
            page.wait_for_timeout(1500)

            found = page.evaluate("window.__cspViolations || []")
            for v in found:
                page_violations.append(v)

            for v in page_violations:
                violations.append((rel, v))
            for e in page_console_errors:
                console_errors.append((rel, e))

            status = "OK" if not page_violations and not page_console_errors else "ISSUES"
            print(f"  [{status:6}] {rel}" + (f"  (role={role})" if role else ""))
            for v in page_violations:
                print(f"           CSP VIOLATION: {v}")
            for e in page_console_errors:
                print(f"           CONSOLE ERROR: {e}")

            context.close()
        browser.close()

    httpd.shutdown()

    print(f"\nPages checked: {len(pages)}")
    print(f"CSP violations: {len(violations)}")
    print(f"Console/page errors: {len(console_errors)}")
    if network_warnings:
        print(f"Non-violation network failures to allowed CDN hosts (sandbox network, not a CSP problem): {len(network_warnings)}")
        for rel, url in network_warnings:
            print(f"  {rel}: {url}")

    if violations or console_errors:
        print("\nFAIL: CSP violations and/or console errors found.")
        sys.exit(1)

    print("\nPASS: zero CSP violations and zero console/page errors across all pages.")


if __name__ == "__main__":
    main()
