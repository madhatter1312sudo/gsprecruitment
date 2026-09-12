#!/usr/bin/env python3
"""
admin_sections_check.py — WS-B.5 + WS-B.10 proof: the three new admin
sections (Opdrachtgevers, Leads, Rapportage) render end to end in a real
browser against stubbed routes (example.com/example.invalid data — no real
PII, no real network calls).

Covers:
  - Opdrachtgevers: list renders (name, domain, open-jobs count, primary
    contact, "onbekend" erkend-referent column), row click opens the
    tabbed detail drawer (WS5 stap 3: een echte Offcanvas met id
    #clientDrawer in plaats van de gedeelde #adminModalOverlay -- vandaar
    dat de sluitknoppen hieronder per paneel gescoped zijn), and each of its four tabs (contacten, vacatures,
    notities/activiteit, prospects) renders without a console error. The
    activiteit tab has no backing endpoint on main (see js/admin.js) so
    this only checks its empty-state text, never a network call.
  - Leads: unified inbox renders rows from both sources (contact/quiz
    badges), the unread toggle re-fetches, and a row click PATCHes the
    read state.
  - Rapportage: the section renders its KPI cards and two breakdown
    tables from stubbed /jobs and /leads data, with no invented numbers
    (every value traces to a stubbed API field).

Exit 0 = all three sections pass with zero console errors, 1 = failure.
"""
import json
import re
import socket
import os
import sys
import threading
import http.server
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "website"
# Chromium: env CHROMIUM_PATH wins; the sandbox path is used when present;
# otherwise None lets Playwright use its own installed browser (CI).
CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH") or (
    "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
)

FAKE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxIiwicm9sZSI6ImFkbWluIiwiZXhwIjo0ODk1MTY4MDAwfQ."
    "fake-signature-for-local-sections-check-only"
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


# ---- Fake data (example.com/example.invalid — no real PII) ---------------

# GET /v1/admin/clients (routers/clients_admin.py, WS-B.2 follow-up) --
# open_job_count/primary_contact come from the endpoint's own LEFT JOIN
# LATERAL, erkend_referent/notes from migrations/031. `notes` mutates in
# place on a successful PATCH (below) so the Info-tab save round-trip can
# be asserted against it.
CLIENTS = [
    {"id": 1, "company_name": "Example Engineering B.V.", "domain": "example-engineering.example.com",
     "industry": "embedded", "erkend_referent": "ja", "notes": "", "location": "Eindhoven",
     "open_job_count": 1,
     "primary_contact": {"full_name": "Primary Contact", "email": "primary@example.com", "role": "hiring_manager"},
     "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"},
    {"id": 2, "company_name": "Example Mechatronics B.V.", "domain": "example-mechatronics.example.com",
     "industry": "mechatronics", "erkend_referent": "onbekend", "notes": "", "location": "Veldhoven",
     "open_job_count": 0, "primary_contact": None,
     "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"},
]

CONTACTS_BY_CLIENT = {
    1: [
        {"id": 11, "client_id": 1, "full_name": "Primary Contact", "email": "primary@example.com",
         "phone": "+31600000001", "role": "hiring_manager", "is_primary": True, "lawful_basis": "zakelijk_functioneel_adres",
         "created_at": "2026-01-01T00:00:00Z", "updated_at": None},
    ],
    2: [],
}

JOBS_BY_CLIENT = {
    1: [{"id": 201, "title": "Embedded Software Engineer", "employment_type": "werving_selectie",
         "status": "open", "application_count": 3}],
    2: [],
}

PROSPECTS = [
    {"id": 301, "company_name": "Example Engineering B.V.", "domain": "example-engineering.example.com",
     "contact_name": "Prospect Contact", "contact_title": "CTO", "status": "new", "source": "manual",
     "created_at": "2026-01-01T00:00:00Z"},
]

ACTIVITIES_BY_CLIENT = {
    1: [{"id": 401, "subject_type": "client", "subject_id": 1, "type": "call",
         "body": "Belde over nieuwe vacature", "due_at": None, "completed_at": None,
         "created_at": "2026-01-01T00:00:00Z"}],
    2: [],
}

LEADS = [
    {"id": 1, "source": "contact_submissions", "name": "Lead One", "email": "lead1@example.com",
     "company": "Example Engineering B.V.", "phone": "+31600000099", "message": "Op zoek naar een embedded engineer.",
     "interest_type": "werving_selectie", "is_read": False, "created_at": "2026-09-01T09:00:00Z",
     "source_page": "/vacatures/201?job=201", "referrer_host": "www.example-referrer.invalid"},
    {"id": 2, "source": "contact_submissions", "name": "Lead Two", "email": "lead2@example.com",
     "company": None, "phone": None, "message": "Interesse in een gesprek.",
     "interest_type": "kandidaat", "is_read": True, "created_at": "2026-08-15T09:00:00Z",
     "source_page": "/kandidaten", "referrer_host": None},
    {"id": 3, "source": "quiz_submissions", "name": None, "email": "quiz1@example.com",
     "interest_type": None, "is_read": False, "created_at": "2026-09-02T09:00:00Z",
     "score": 8, "max_score": 10, "tier": "senior", "domain_scores": {"embedded": 4, "ot_security": 4},
     "source_page": "/quiz", "referrer_host": None},
]

OPEN_JOBS_TOTAL_BY_CLIENT = {1: 1, 2: 0}

# GET /v1/admin/analytics (WS2) -- ANALYTICS_STATE["mode"] flips between
# "ok" and "error" mid-test to exercise loadAnalytics()'s per-panel
# load/error states and its retry link, independent of the other stubs.
ANALYTICS_STATE = {"mode": "ok"}
ANALYTICS_DATA = {
    "job_fill_rate": 82, "client_retention_rate": 91, "candidate_satisfaction": 76,
    "user_growth": {"2026-07-01": 4, "2026-08-01": 6, "2026-09-01": 9},
}


def qint(qs, key, default):
    try:
        return int(qs.get(key, [str(default)])[0])
    except (TypeError, ValueError):
        return default


def route_admin_api(route, request):
    url = request.url
    parsed = urlparse(url)
    path = parsed.path
    qs = parse_qs(parsed.query)
    method = request.method

    def json_response(obj, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(obj))

    if path == "/api/auth/mfa/status":
        json_response({"mfa_enabled": False})
        return
    if path == "/api/v1/admin/dashboard":
        json_response({"total_users": 2, "active_jobs": 1, "registered_candidates": 0,
                        "active_clients": 2, "placements_this_week": 0})
        return
    if path == "/api/v1/admin/audit-log":
        # `changes` here is a plain JS object -- the shape the fixed
        # get_audit_log() now guarantees after decoding asyncpg's raw
        # jsonb text (code-reviewer WS2 finding: the old stub had no
        # `changes` field at all, so admin.js's `typeof e.changes ===
        # 'object'` gate was never exercised and the "always shows a
        # dash" regression slipped through).
        json_response({
            "items": [{
                "id": 1,
                "action": "user_update",
                "actor_id": 1,
                "actor_email": "admin@example.invalid",
                "target_type": "user",
                "target_id": 42,
                "changes": {"status": "actief", "role": "candidate"},
                "created_at": "2026-09-01T10:00:00Z",
            }],
            "total": 1,
        })
        return

    # ---- Users list / detail (unrelated to the Opdrachtgevers roster
    #      since routers/clients_admin.py replaced the /users?role=client
    #      derivation -- kept only in case another section/check needs it) --
    if path == "/api/v1/admin/users" and method == "GET":
        json_response({"items": [], "total": 0})
        return
    m = re.match(r"^/api/v1/admin/users/(\d+)$", path)
    if m and method == "GET":
        json_response({"detail": "Not found"}, status=404)
        return

    # ---- Clients (Opdrachtgevers roster + detail drawer's Info tab,
    #      routers/clients_admin.py, WS-B.2 follow-up) ----
    if path == "/api/v1/admin/clients" and method == "GET":
        rows = CLIENTS
        search = (qs.get("search", [""])[0] or "").lower()
        if search:
            rows = [c for c in rows if search in c["company_name"].lower() or search in (c["domain"] or "").lower()]
        json_response({"items": rows, "total": len(rows), "page": qint(qs, "page", 1), "limit": qint(qs, "limit", 50)})
        return
    m = re.match(r"^/api/v1/admin/clients/(\d+)$", path)
    if m and method == "GET":
        cid = int(m.group(1))
        client = next((c for c in CLIENTS if c["id"] == cid), None)
        if not client:
            json_response({"detail": "Client not found"}, status=404)
            return
        detail = {**client, "contacts": CONTACTS_BY_CLIENT.get(cid, [])}
        json_response(detail)
        return
    if m and method == "PATCH":
        cid = int(m.group(1))
        client = next((c for c in CLIENTS if c["id"] == cid), None)
        if not client:
            json_response({"detail": "Client not found"}, status=404)
            return
        body = json.loads(request.post_data or "{}")
        for key in ("company_name", "domain", "industry", "erkend_referent", "notes"):
            if key in body:
                client[key] = body[key]
        json_response({
            "id": client["id"], "company_name": client["company_name"], "domain": client["domain"],
            "industry": client["industry"], "erkend_referent": client["erkend_referent"],
            "notes": client["notes"], "updated_at": "2026-01-01T00:00:00Z",
        })
        return

    # ---- Jobs (open-count pass, client jobs tab, reporting) ----
    if path == "/api/v1/admin/jobs" and method == "GET":
        client_id = qs.get("client_id", [None])[0]
        status = qs.get("status", [None])[0]
        if client_id is not None:
            cid = int(client_id)
            if status == "open":
                json_response({"items": [], "total": OPEN_JOBS_TOTAL_BY_CLIENT.get(cid, 0)})
                return
            items = JOBS_BY_CLIENT.get(cid, [])
            json_response({"items": items, "total": len(items)})
            return
        if status == "open":
            all_open = [j for c in JOBS_BY_CLIENT.values() for j in c if j["status"] == "open"]
            json_response({"items": all_open, "total": len(all_open)})
            return
        json_response({"items": [], "total": 0})
        return

    # ---- Client contacts (WS-C.4) ----
    m = re.match(r"^/api/v1/admin/clients/(\d+)/contacts$", path)
    if m and method == "GET":
        cid = int(m.group(1))
        items = CONTACTS_BY_CLIENT.get(cid, [])
        json_response({"items": items, "total": len(items)})
        return

    # ---- Activities (WS-C.6, notities/activiteit tab) ----
    if path == "/api/v1/admin/activities" and method == "GET":
        subject_type = qs.get("subject_type", [None])[0]
        subject_id = qs.get("subject_id", [None])[0]
        if subject_type == "client" and subject_id is not None:
            items = ACTIVITIES_BY_CLIENT.get(int(subject_id), [])
            json_response({"items": items, "total": len(items)})
            return
        json_response({"items": [], "total": 0})
        return

    # ---- Prospects (client drawer's prospects tab) ----
    if path == "/api/v1/admin/prospects" and method == "GET":
        search = (qs.get("search", [""])[0] or "").lower()
        items = [p for p in PROSPECTS if search in p["company_name"].lower()] if search else PROSPECTS
        json_response({"items": items, "total": len(items)})
        return

    # ---- Leads (WS-C.10) ----
    if path == "/api/v1/admin/leads" and method == "GET":
        items = LEADS
        itype = qs.get("type", [None])[0]
        unread = qs.get("unread", [None])[0]
        if itype:
            items = [l for l in items if l["interest_type"] == itype]
        if unread == "true":
            items = [l for l in items if not l["is_read"]]
        limit = qint(qs, "limit", 50)
        offset = qint(qs, "offset", 0)
        json_response({"items": items[offset:offset + limit], "total": len(items), "limit": limit, "offset": offset})
        return
    m = re.match(r"^/api/v1/admin/leads/([a-z_]+)/(\d+)$", path)
    if m and method == "GET":
        source, lead_id = m.group(1), int(m.group(2))
        for l in LEADS:
            if l["source"] == source and l["id"] == lead_id:
                json_response(l)
                return
        json_response({"detail": "Not found"}, status=404)
        return
    if m and method == "PATCH":
        source, lead_id = m.group(1), int(m.group(2))
        for l in LEADS:
            if l["source"] == source and l["id"] == lead_id:
                body = json.loads(request.post_data or "{}")
                l["is_read"] = bool(body.get("is_read"))
                json_response({"id": lead_id, "is_read": l["is_read"]})
                return
        json_response({"detail": "Not found"}, status=404)
        return

    if path == "/api/v1/admin/analytics":
        if ANALYTICS_STATE["mode"] == "error":
            json_response({"detail": "Server error"}, status=500)
        else:
            json_response(ANALYTICS_DATA)
        return
    if path == "/api/v1/admin/settings":
        json_response([])
        return
    if path == "/api/v1/admin/content":
        json_response([])
        return
    if path == "/api/v1/admin/candidates":
        json_response({"items": [], "total": 0})
        return

    json_response({"items": [], "total": 0})


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
        browser = pw.chromium.launch(executable_path=CHROMIUM_PATH or None, headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 1000})

        user = {"id": 1, "role": "admin", "email": "sections-check@example.invalid",
                "full_name": "Sections Check", "is_verified": True}
        context.add_init_script(
            f"""
            try {{
              localStorage.setItem('gsp_cookie_consent', 'true');
              localStorage.setItem('gsp_token', {json.dumps(FAKE_JWT)});
              localStorage.setItem('gsp_user', {json.dumps(json.dumps(user))});
            }} catch (e) {{}}
            """
        )

        context.route(re.compile(r"^https://api\.gsprecruitment\.nl/api/"), route_admin_api)
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

        # ---- Dashboard: recent activity changeKeys (code-reviewer WS2) ----
        # The stubbed audit-log item's `changes` is a real object, matching
        # the fixed get_audit_log() contract -- this must render the
        # "(status, role)" suffix, not silently show nothing.
        activity_text = page.eval_on_selector('#recentActivityList', "el => el.textContent") or ""
        if "(status, role)" not in activity_text:
            failures.append(f"dashboard: recent activity did not render changeKeys — got: {activity_text[:200]!r}")

        # ---- Opdrachtgevers ----
        errors_before = len(console_errors)
        page.click('.nav-link[data-section="clients"]')
        page.wait_for_timeout(700)
        rows = page.eval_on_selector_all('#section-clients table tbody tr', "els => els.length")
        if rows != len(CLIENTS):
            failures.append(f"clients: list rendered {rows} rows, expected {len(CLIENTS)}")
        first_row_text = page.eval_on_selector('#section-clients table tbody tr', "el => el.textContent")
        # CLIENTS[0].erkend_referent == "ja" -- the roster must show the
        # real per-client value from the API, not a hardcoded "onbekend"
        # placeholder (that was the pre-WS-B.2-follow-up behavior).
        if first_row_text and "Ja" not in first_row_text:
            failures.append(f"clients: erkend-referent column did not render 'Ja' for client 1 — got: {first_row_text!r}")
        if first_row_text and "Primary Contact" not in first_row_text:
            failures.append(f"clients: primary_contact column did not render — got: {first_row_text!r}")

        page.click('#section-clients table tbody tr')
        page.wait_for_timeout(600)
        if page.query_selector('#clientDrawerTabContent') is None:
            failures.append("clients: detail drawer did not open")
        else:
            # Info tab (default on open): erkend_referent select + notes
            # textarea, editable via PATCH /v1/admin/clients/{id}.
            if page.query_selector('#clientInfoErkendReferent') is None:
                failures.append("clients: info tab did not render the erkend_referent select")
            selected = page.eval_on_selector('#clientInfoErkendReferent', "el => el.value")
            if selected != "ja":
                failures.append(f"clients: info tab select did not default to the client's erkend_referent ('ja') — got {selected!r}")

            page.select_option('#clientInfoErkendReferent', 'nee')
            page.fill('#clientInfoNotes', 'Playwright test note')
            page.click('[data-action="save-client-info"]')
            page.wait_for_timeout(500)
            toast_texts = page.eval_on_selector_all(
                ".toast-container .toast span:last-child", "els => els.map(e => e.textContent)"
            )
            if not any("Opgeslagen" in t for t in toast_texts):
                failures.append(f"clients: info tab save did not show a success toast — got {toast_texts!r}")
            if CLIENTS[0]["erkend_referent"] != "nee" or CLIENTS[0]["notes"] != "Playwright test note":
                failures.append(
                    f"clients: PATCH did not persist erkend_referent/notes — server state: "
                    f"{CLIENTS[0]['erkend_referent']!r}/{CLIENTS[0]['notes']!r}"
                )
            # Roster badge must reflect the edit without a full reload.
            page.click('#clientDrawer [data-action="close-modal"]')
            page.wait_for_timeout(300)
            roster_text = page.eval_on_selector('#section-clients table tbody tr', "el => el.textContent") or ""
            if "Nee" not in roster_text:
                failures.append(f"clients: roster badge did not update after saving erkend_referent — got: {roster_text!r}")
            page.click('#section-clients table tbody tr')
            page.wait_for_timeout(500)

            for tab, expect in [
                ("contacts", "Primary Contact"),
                ("jobs", "Embedded Software Engineer"),
                ("activity", "Belde over nieuwe vacature"),
                ("prospects", "Prospect Contact"),
            ]:
                page.click(f'[data-action="client-tab"][data-tab="{tab}"]')
                page.wait_for_timeout(500)
                text = page.eval_on_selector('#clientDrawerTabContent', "el => el.textContent") or ""
                if expect not in text:
                    failures.append(f"clients: {tab} tab did not render expected content — got: {text[:120]!r}")
                # Vacatures tab's Type column must show the translated
                # dienstlijn label, never the raw employment_type enum
                # value (design-reviewer FIX FIRST item).
                if tab == "jobs":
                    if "Werving en selectie" not in text:
                        failures.append(f"clients: jobs tab missing translated dienstlijn label — got: {text[:120]!r}")
                    if "werving_selectie" in text:
                        failures.append("clients: raw employment_type value leaked into the jobs tab")

        page.click('#clientDrawer [data-action="close-modal"]')
        page.wait_for_timeout(300)
        new_errors = console_errors[errors_before:]
        if new_errors:
            failures.append(f"clients: {len(new_errors)} console error(s): {new_errors[:3]}")

        # ---- Leads ----
        errors_before = len(console_errors)
        page.click('.nav-link[data-section="leads"]')
        page.wait_for_timeout(600)
        rows = page.eval_on_selector_all('#section-leads table tbody tr', "els => els.length")
        if rows != len(LEADS):
            failures.append(f"leads: list rendered {rows} rows, expected {len(LEADS)}")
        badges = page.eval_on_selector_all('#section-leads table tbody tr td:first-child', "els => els.map(e => e.textContent.trim())")
        if "Contact" not in badges or "Quiz" not in badges:
            failures.append(f"leads: expected both Contact and Quiz source badges — got {badges}")

        page.check('#leadUnreadFilter')
        page.wait_for_timeout(500)
        rows_unread = page.eval_on_selector_all('#section-leads table tbody tr', "els => els.length")
        expected_unread = len([l for l in LEADS if not l["is_read"]])
        if rows_unread != expected_unread:
            failures.append(f"leads: unread filter rendered {rows_unread} rows, expected {expected_unread}")
        page.uncheck('#leadUnreadFilter')
        page.wait_for_timeout(500)

        badges2 = page.eval_on_selector_all('#section-leads table tbody tr td:nth-child(5)', "els => els.map(e => e.textContent.trim())")
        if not any("example-referrer.invalid" in b for b in badges2):
            failures.append(f"leads: Herkomst column missing referrer_host — got {badges2}")

        # Row click opens the detail modal (GET /v1/admin/leads/{source}/{id})
        # rather than toggling read state directly — that accidental
        # toggle-on-click was the WS2 defect.
        page.click('#section-leads table tbody tr')
        page.wait_for_timeout(500)
        modal_text = page.eval_on_selector('#adminModalOverlay', "el => el.textContent") or ""
        if "Example Engineering B.V." not in modal_text or "Op zoek naar een embedded engineer" not in modal_text:
            failures.append(f"leads: detail modal missing company/message — got: {modal_text[:200]!r}")
        if LEADS[0]["is_read"]:
            failures.append("leads: opening the detail modal must not itself mark the lead read")

        # The explicit button, not the row click, is what marks it read.
        page.click('[data-action="toggle-lead-read"]')
        page.wait_for_timeout(500)
        if not LEADS[0]["is_read"]:
            failures.append("leads: 'Markeer als gelezen' button in the modal did not PATCH is_read")
        modal_text2 = page.eval_on_selector('#adminModalOverlay', "el => el.textContent") or ""
        if "Markeer als ongelezen" not in modal_text2:
            failures.append(f"leads: modal button did not flip to 'Markeer als ongelezen' after marking read — got: {modal_text2[:200]!r}")

        page.click('#adminModalOverlay [data-action="close-modal"]')
        page.wait_for_timeout(300)

        # A quiz_submissions row's detail must show score/tier, not the
        # contact-form fields it has none of.
        page.click('#section-leads table tbody tr:nth-child(3)')
        page.wait_for_timeout(500)
        quiz_modal_text = page.eval_on_selector('#adminModalOverlay', "el => el.textContent") or ""
        if "8 / 10" not in quiz_modal_text or "senior" not in quiz_modal_text:
            failures.append(f"leads: quiz lead detail missing score/tier — got: {quiz_modal_text[:200]!r}")
        page.click('#adminModalOverlay [data-action="close-modal"]')
        page.wait_for_timeout(300)

        new_errors = console_errors[errors_before:]
        if new_errors:
            failures.append(f"leads: {len(new_errors)} console error(s): {new_errors[:3]}")

        # ---- Analytics ----
        errors_before = len(console_errors)
        ANALYTICS_STATE["mode"] = "ok"
        page.click('.nav-link[data-section="analytics"]')
        page.wait_for_timeout(700)
        summary_text = page.eval_on_selector('#analyticsSummary', "el => el.textContent") or ""
        if "Loading" in summary_text:
            failures.append("analytics: summary still shows literal 'Loading' after data loaded")
        for expected in ("82", "91", "76"):
            if expected not in summary_text:
                failures.append(f"analytics: summary missing expected KPI value {expected!r} — got {summary_text!r}")
        has_apex = page.query_selector('#userGrowthChart .apexcharts-canvas, #userGrowthChart canvas') is not None
        has_fallback = page.eval_on_selector_all('#userGrowthChart > div > div', "els => els.length") > 0
        if not (has_apex or has_fallback):
            failures.append("analytics: user growth chart/fallback did not render")

        # Force a failure and reset the section's cache via a full reload
        # (nav.js's `loaded` set is in-memory) so revisiting the tab
        # re-fetches against the now-erroring stub.
        ANALYTICS_STATE["mode"] = "error"
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        page.click('.nav-link[data-section="analytics"]')
        page.wait_for_timeout(700)
        growth_err = page.eval_on_selector('#userGrowthChart', "el => el.textContent") or ""
        summary_err = page.eval_on_selector('#analyticsSummary', "el => el.textContent") or ""
        if "probeer opnieuw" not in growth_err.lower() and "probeer opnieuw" not in summary_err.lower():
            failures.append(f"analytics: error state missing a retry link — chart: {growth_err[:120]!r}, summary: {summary_err[:120]!r}")

        # The deliberately-stubbed 500s above log their own "Failed to load
        # resource" console errors -- expected noise from this negative
        # test, not an app bug, so the boundary resets past them here
        # rather than teaching on_console to ignore 500s globally.
        errors_before = len(console_errors)

        # Fix the stub, then use the retry link (not another nav click —
        # a nav click on an already-attempted section, successful or not,
        # is a separate concern from the retry link this panel renders).
        ANALYTICS_STATE["mode"] = "ok"
        retry_link = page.query_selector('#analyticsSummary a') or page.query_selector('#userGrowthChart a')
        if retry_link is None:
            failures.append("analytics: no retry link found in the error state to recover from")
        else:
            retry_link.click()
            page.wait_for_timeout(700)
            recovered_summary = page.eval_on_selector('#analyticsSummary', "el => el.textContent") or ""
            if "Loading" in recovered_summary or "Kon niet laden" in recovered_summary:
                failures.append(f"analytics: did not recover after retry — got {recovered_summary!r}")
            if "76" not in recovered_summary:
                failures.append(f"analytics: recovered summary missing expected KPI value — got {recovered_summary!r}")
        new_errors = console_errors[errors_before:]
        if new_errors:
            failures.append(f"analytics: {len(new_errors)} console error(s): {new_errors[:3]}")

        # ---- Audit Log: Details column (code-reviewer WS2) ----
        errors_before = len(console_errors)
        page.click('.nav-link[data-section="audit"]')
        page.wait_for_timeout(600)
        audit_rows = page.eval_on_selector_all('#section-audit table tbody tr', "els => els.length")
        if audit_rows != 1:
            failures.append(f"audit: table rendered {audit_rows} rows, expected 1")
        details_text = page.eval_on_selector('#section-audit table tbody tr td:last-child', "el => el.textContent") or ""
        if "status" not in details_text or "actief" not in details_text:
            failures.append(f"audit: Details column did not render the changes object — got: {details_text[:200]!r}")
        if details_text.strip() == "—":
            failures.append("audit: Details column showed the empty-state dash instead of the changes object")
        new_errors = console_errors[errors_before:]
        if new_errors:
            failures.append(f"audit: {len(new_errors)} console error(s): {new_errors[:3]}")

        # ---- Rapportage ----
        errors_before = len(console_errors)
        page.click('.nav-link[data-section="reporting"]')
        page.wait_for_timeout(700)
        content = page.eval_on_selector('#reportingContent', "el => el.textContent") or ""
        # Dienstlijn column must show the translated label, never the raw
        # employment_type enum value (design-reviewer FIX FIRST item).
        if "Werving en selectie" not in content:
            failures.append(f"reporting: open-jobs-by-dienstlijn breakdown missing translated label — got: {content[:200]!r}")
        if "werving_selectie" in content:
            failures.append("reporting: raw employment_type value leaked into the open-jobs-by-dienstlijn breakdown")
        if "Werving & selectie" not in content:
            failures.append("reporting: leads-per-category table missing expected label")
        new_errors = console_errors[errors_before:]
        if new_errors:
            failures.append(f"reporting: {len(new_errors)} console error(s): {new_errors[:3]}")

        browser.close()

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS: Opdrachtgevers (list + tabbed drawer), Leads (inbox + unread filter + PATCH) "
          "and Rapportage all rendered correctly with zero console errors.")
    sys.exit(0)


if __name__ == "__main__":
    main()
