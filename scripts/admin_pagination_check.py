#!/usr/bin/env python3
"""
admin_pagination_check.py — WS-B.1 proof: html``-rendered admin tables and
their data-page pagination actually work end to end in a real browser.

Serves website/ with python3 -m http.server, seeds a fake admin JWT into
localStorage (same shape Auth.requireAuth() expects — see
scripts/csp_violation_check.py's seed_auth()), and stubs every
/api/v1/admin/* (and /api/auth/mfa/status) call via page.route with 60
deterministic fake rows (example.com/example.invalid data — no real PII)
per list endpoint. For Users, Candidates, Outreach, Blog and Audit it then:
  1. navigates to the section (clicks its sidebar nav-link),
  2. asserts page 1 rendered 20 rows with no console errors,
  3. clicks the page-2 pagination button (data-action="page" data-page="2"),
  4. asserts page 2 rendered 20 *different* rows with no console errors.

Deterministic: fixed fake data, fixed viewport, no real network calls, no
repo writes. Exit 0 = all five sections' page 2 render cleanly, 1 = a
mismatch or a console error was seen.

Usage: node scripts/test_render_js.mjs   (render.js unit tests — separate)
       python3 scripts/admin_pagination_check.py
"""
import http.server
import json
import re
import socket
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "website"
CHROMIUM_PATH = "/opt/pw-browsers/chromium"
PAGE_SIZE = 20
TOTAL_ROWS = 60

FAKE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxIiwicm9sZSI6ImFkbWluIiwiZXhwIjo0ODk1MTY4MDAwfQ."
    "fake-signature-for-local-pagination-check-only"
)


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass


def start_server(port):
    handler = lambda *a, **kw: _QuietHandler(*a, directory=str(WEBSITE), **kw)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


# ---- Fake row generators (60 each, example.com/example.invalid) ----------

def make_users(n=TOTAL_ROWS):
    roles = ["candidate", "client", "admin"]
    return [{
        "id": i,
        "full_name": f"Test User {i}",
        "email": f"user{i}@example.com",
        "role": roles[i % 3],
        "is_verified": i % 2 == 0,
        "created_at": "2026-01-01T00:00:00Z",
    } for i in range(1, n + 1)]


def make_candidates(n=TOTAL_ROWS):
    return [{
        "id": i,
        "candidate_id": i,
        "user_id": i if i % 2 == 0 else None,
        "full_name": f"Test Candidate {i}",
        "email": f"candidate{i}@example.com",
        "current_title": "Embedded Software Engineer",
        "years_experience": (i % 15) + 1,
        "kind": "self-registered" if i % 2 == 0 else "sourced",
        "source": "referral",
        "match_count": i % 5,
        "placement_count": 1 if i % 10 == 0 else 0,
        "status": "active",
        "is_verified": i % 3 == 0,
    } for i in range(1, n + 1)]


def make_outreach(n=TOTAL_ROWS):
    types = ["candidate", "client"]
    statuses = ["draft", "sent", "rejected"]
    return [{
        "id": i,
        "target_name": f"Target {i}",
        "target_email": f"target{i}@example.com",
        "company": f"Example Corp {i}",
        "subject": f"Outreach subject {i}",
        "target_type": types[i % 2],
        "ai_model": "test-model",
        "created_at": "2026-01-01T00:00:00Z",
        "status": statuses[i % 3],
        "body": f"Test body {i}",
        "channel": "email",
        "language": "nl",
    } for i in range(1, n + 1)]


def make_blog(n=TOTAL_ROWS):
    statuses = ["draft", "published", "archived"]
    return [{
        "id": i,
        "title_nl": f"Testartikel {i}",
        "slug": f"testartikel-{i}",
        "tags": ["embedded", "test"],
        "status": statuses[i % 3],
        "published_at": "2026-01-01T00:00:00Z" if i % 3 == 1 else None,
    } for i in range(1, n + 1)]


def make_audit(n=TOTAL_ROWS):
    actions = ["user_update", "job_update", "content_update"]
    return [{
        "id": i,
        "created_at": "2026-01-01T00:00:00Z",
        "action": actions[i % 3],
        "actor_email": "admin@example.com",
        "target_type": "user",
        "target_id": i,
    } for i in range(1, n + 1)]


LIST_DATA = {
    "users": make_users(),
    "candidates": make_candidates(),
    "outreach": make_outreach(),
    "blog": make_blog(),
    "audit": make_audit(),
}


def paginate(items, qs):
    limit = int(qs.get("limit", [str(PAGE_SIZE)])[0])
    offset = int(qs.get("offset", ["0"])[0])
    return {"items": items[offset:offset + limit], "total": len(items)}


def route_admin_api(route, request):
    url = request.url
    parsed = urlparse(url)
    path = parsed.path
    qs = parse_qs(parsed.query)

    def json_response(obj, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(obj))

    if path == "/api/auth/mfa/status":
        json_response({"mfa_enabled": False})
        return
    if path == "/api/v1/admin/dashboard":
        json_response({"total_users": TOTAL_ROWS, "active_jobs": 0, "registered_candidates": TOTAL_ROWS,
                        "active_clients": 0, "placements_this_week": 0})
        return
    if path == "/api/v1/admin/audit-log":
        json_response(paginate(LIST_DATA["audit"], qs))
        return
    if path == "/api/v1/admin/users":
        json_response(paginate(LIST_DATA["users"], qs))
        return
    if path == "/api/v1/admin/candidates":
        json_response(paginate(LIST_DATA["candidates"], qs))
        return
    if path == "/api/v1/admin/outreach/drafts":
        json_response(paginate(LIST_DATA["outreach"], qs))
        return
    if path == "/api/v1/admin/blog/" or path == "/api/v1/admin/blog":
        json_response(paginate(LIST_DATA["blog"], qs))
        return
    if path == "/api/v1/admin/jobs":
        json_response({"items": [], "total": 0})
        return
    if path == "/api/v1/admin/analytics":
        json_response({"job_fill_rate": 0, "client_retention_rate": 0, "candidate_satisfaction": 0, "user_growth": {}})
        return
    if path == "/api/v1/admin/settings":
        json_response([])
        return
    if path == "/api/v1/admin/content":
        json_response([])
        return
    # Anything else under the admin API we didn't anticipate — fulfil with
    # an empty-but-valid body rather than letting it hit the real network
    # (unreachable from this sandbox anyway) or hang.
    json_response({"items": [], "total": 0})


SECTIONS = [
    ("users", "#section-users table tbody tr", "usersPagination"),
    ("candidates", "#section-candidates table tbody tr", "candidatesPagination"),
    ("outreach", "#section-outreach table tbody tr", "outreachPagination"),
    ("blog", "#section-blog table tbody tr", "blogPagination"),
    ("audit", "#section-audit table tbody tr", "auditPagination"),
]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FAIL: playwright not installed")
        sys.exit(1)

    port = find_free_port()
    start_server(port)
    base = f"http://127.0.0.1:{port}/admin/"

    failures = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM_PATH, headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 1000})

        user = {"id": 1, "role": "admin", "email": "pagination-check@example.invalid",
                "full_name": "Pagination Check", "is_verified": True}
        context.add_init_script(
            f"""
            try {{
              // Auth.getToken()/getUser() both read as logged-out unless
              // cookie consent is recorded first (see website/auth.js) —
              // easy to miss when hand-seeding a session for a test.
              localStorage.setItem('gsp_cookie_consent', 'true');
              localStorage.setItem('gsp_token', {json.dumps(FAKE_JWT)});
              localStorage.setItem('gsp_user', {json.dumps(json.dumps(user))});
            }} catch (e) {{}}
            """
        )

        context.route(re.compile(r"^https://api\.gsprecruitment\.nl/api/"), route_admin_api)
        # Anything else external (fonts, cdnjs) — abort instead of letting
        # this sandbox's network stall the run; irrelevant to the check.
        context.route(re.compile(r"^https://(fonts\.googleapis\.com|fonts\.gstatic\.com|cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net)/"),
                       lambda route, request: route.abort())

        console_errors = []

        def on_console(msg):
            if msg.type == "error":
                text = msg.text
                if "favicon" in text.lower() or "net::ERR_FAILED" in text:
                    return
                console_errors.append(text)

        def on_pageerror(exc):
            console_errors.append(f"pageerror: {exc}")

        page = context.new_page()
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        page.goto(base, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(800)

        for section, row_selector, pagination_id in SECTIONS:
            errors_before = len(console_errors)

            page.click(f'.nav-link[data-section="{section}"]')
            page.wait_for_timeout(600)

            rows_p1 = page.eval_on_selector_all(row_selector, "els => els.length")
            texts_p1 = page.eval_on_selector_all(row_selector, "els => els.map(e => e.textContent.trim())")
            if rows_p1 != PAGE_SIZE:
                failures.append(f"{section}: page 1 rendered {rows_p1} rows, expected {PAGE_SIZE}")

            page_btn = f'#{pagination_id} [data-action="page"][data-page="2"]'
            if page.query_selector(page_btn) is None:
                failures.append(f"{section}: no page-2 pagination button found")
                continue
            page.click(page_btn)
            page.wait_for_timeout(600)

            rows_p2 = page.eval_on_selector_all(row_selector, "els => els.length")
            texts_p2 = page.eval_on_selector_all(row_selector, "els => els.map(e => e.textContent.trim())")
            if rows_p2 != PAGE_SIZE:
                failures.append(f"{section}: page 2 rendered {rows_p2} rows, expected {PAGE_SIZE}")
            if texts_p1 and texts_p2 and texts_p1 == texts_p2:
                failures.append(f"{section}: page 2 rendered identical content to page 1 (pagination did not advance)")

            new_errors = console_errors[errors_before:]
            if new_errors:
                failures.append(f"{section}: {len(new_errors)} console error(s): {new_errors[:3]}")

        browser.close()

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print(f"PASS: page 2 rendered {PAGE_SIZE} rows with no console errors on all "
          f"{len(SECTIONS)} sections ({', '.join(s for s, _, _ in SECTIONS)}).")
    sys.exit(0)


if __name__ == "__main__":
    main()
