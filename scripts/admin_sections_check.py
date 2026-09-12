#!/usr/bin/env python3
"""
admin_sections_check.py -- WS-B.5 + WS-B.10 proof: de nieuwe adminsecties
(Opdrachtgevers, Leads, Rapportage en Bewaartermijnen) renderen van begin
tot eind in een echte browser tegen gestubde routes (example.com/
example.invalid, geen echte PII, geen echt netwerk).

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

  - Bewaartermijnen (SITE-DESIGN-SPEC.md §7.3.1): de samenvatting, de
    categorietabel en de lijst met gemengde statussen renderen; de
    heropende rij toont zijn eigen regel; er staat geen e-mailadres en
    geen ruwe enumwaarde in de lijst; rijselectie toont de bulkbalk;
    sorteren gaat server-side (sort/order in de querystring, aria-sort op
    de kop); "Lijst genereren" roept generate aan; goedkeuren blijft
    geblokkeerd tot APPROVE letterlijk getypt is en stuurt dan
    confirm="APPROVE"; afwijzen vraagt geen getypte bevestiging en stuurt
    de notitie mee; categoriebreed goedkeuren stuurt expected_count,
    houdt de modal open bij een 409 mismatch en slaagt na verversen; de
    twee droogloopkaarten vragen geen bevestiging; een 500 geeft de
    retrylink en herstelt daarna.

Exit 0 = alle secties slagen zonder console errors, 1 = mislukt.
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
         "status": "open", "application_count": 3, "company_name": "Example Engineering B.V."}],
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

# ---- Kandidaatdrawer: tab Toestemmingen + referral-intake (§7.3.2) -------
# Eén sourced kandidaat (candidates.id 1482, geen consent bij aanvang) is
# genoeg om alle drie de modals tegen echte gestubde routes te toetsen; de
# drie tabs Profiel/Matches/Activiteit hoeven voor dit doel alleen zonder
# console error te renderen, dus die leunen op de generieke lege-lijst-
# fallback onderaan route_admin_api.
CANDIDATE_RECORD = {
    "id": 1482, "full_name": "Voorbeeld Kandidaat", "email": "kandidaat@example.invalid",
    "current_title": "Embedded Engineer", "current_company": None, "years_experience": 5,
    "location": "Eindhoven", "source": "apollo", "status": "active",
    "lawful_basis": "gerechtvaardigd_belang",
    "consent_talentpool_at": None, "consent_talentpool_until": None, "consent_scope": None,
    "consent_source": None, "consent_withdrawn_at": None,
    "consent_spec_presentation_at": None, "consent_spec_presentation_job_id": None,
    "job_alert_optin_at": None, "job_alert_unsubscribed_at": None,
    "created_at": "2026-01-01T00:00:00Z",
}

CANDIDATE_STATE = {
    "talentpool_calls": [], "presentation_calls": [], "referral_calls": [],
    # "ok" | "suppressed" | "exists" | "unknown" -- welke uitkomst de
    # volgende POST /candidates/referral teruggeeft.
    "referral_mode": "ok",
}


def candidate_roster_item():
    r = CANDIDATE_RECORD
    return {
        "kind": "sourced", "id": r["id"], "candidate_id": None, "user_id": None,
        "full_name": r["full_name"], "email": r["email"], "current_title": r["current_title"],
        "years_experience": r["years_experience"], "match_count": 0, "placement_count": 0,
        "source": r["source"], "status": r["status"], "is_verified": True,
    }


def candidate_detail():
    d = dict(CANDIDATE_RECORD)
    d["skills"] = []
    d["languages"] = []
    d["tags"] = []
    d["match_count"] = 0
    d["placement_count"] = 0
    d["kind"] = "sourced"
    d["user_id"] = None
    d["is_verified"] = None
    return d


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


# ---- Bewaartermijnen (§7.3.1) ------------------------------------------
# retention_review_items zoals GET /api/v1/admin/retention/review ze
# teruggeeft, met gemengde statussen: drie 'pending' (waarvan één heropend
# na een eerdere afwijzing), één 'rejected' en één 'purged'. De adressen
# zijn example.invalid -- geen echte PII.
RETENTION_ITEMS = [
    {"id": 1, "category": "rejected_applicant", "subject_table": "candidates", "subject_id": 1482,
     "email": "kandidaat1@example.invalid", "action": "anonymise",
     "term_expired_at": "2026-08-12T00:00:00Z",
     "signal_missing_nl": "geen nieuwe match, pipeline-activiteit of plaatsing sinds de afwijzing",
     "status": "pending", "first_seen_at": "2026-09-01T00:00:00Z", "last_seen_at": "2026-09-03T00:00:00Z",
     "reappeared_after_rejection_at": None, "purged_at": None},
    {"id": 2, "category": "referral", "subject_table": "candidates", "subject_id": 903,
     "email": "kandidaat2@example.invalid", "action": "anonymise",
     "term_expired_at": "2026-07-01T00:00:00Z",
     "signal_missing_nl": "geen reactie en geen sollicitatie sinds de introductie",
     "status": "pending", "first_seen_at": "2026-06-01T00:00:00Z", "last_seen_at": "2026-09-03T00:00:00Z",
     "reappeared_after_rejection_at": "2026-08-04T00:00:00Z", "purged_at": None},
    {"id": 3, "category": "rejected_applicant", "subject_table": "candidates", "subject_id": 1490,
     "email": "kandidaat3@example.invalid", "action": "anonymise",
     "term_expired_at": "2026-08-20T00:00:00Z",
     "signal_missing_nl": "geen nieuwe match, pipeline-activiteit of plaatsing sinds de afwijzing",
     "status": "pending", "first_seen_at": "2026-09-01T00:00:00Z", "last_seen_at": "2026-09-03T00:00:00Z",
     "reappeared_after_rejection_at": None, "purged_at": None},
    {"id": 4, "category": "prospect_no_response", "subject_table": "client_prospects", "subject_id": 77,
     "email": None, "action": "hard_delete", "term_expired_at": "2026-05-05T00:00:00Z",
     "signal_missing_nl": "geen reactie op de benadering en geen bestaande relatie",
     "status": "rejected", "first_seen_at": "2026-06-01T00:00:00Z", "last_seen_at": "2026-09-03T00:00:00Z",
     "reappeared_after_rejection_at": None, "purged_at": None},
    {"id": 5, "category": "leads_quiz", "subject_table": "quiz_submissions", "subject_id": 12,
     "email": None, "action": "hard_delete", "term_expired_at": "2026-04-01T00:00:00Z",
     "signal_missing_nl": "ouder dan de bewaartermijn voor leads en quizinzendingen",
     "status": "purged", "first_seen_at": "2026-05-01T00:00:00Z", "last_seen_at": "2026-09-03T00:00:00Z",
     "reappeared_after_rejection_at": None, "purged_at": "2026-09-04T00:00:00Z"},
]

# Eén categorie met meer openstaande items dan de paginagrootte van de
# lijst (50). Zonder die categorie zijn "de hele categorie" en "de eerste
# pagina ervan" hetzelfde getal, en dan bewijst de assertie op
# expected_count niets: de modal moet juist ZONDER limit ophalen.
RETENTION_BIG_CATEGORY = "sourced_no_response"
RETENTION_BIG_COUNT = 60
RETENTION_ITEMS += [
    {"id": 100 + i, "category": RETENTION_BIG_CATEGORY, "subject_table": "candidates",
     "subject_id": 2000 + i, "email": None, "action": "anonymise",
     "term_expired_at": "2026-08-25T00:00:00Z",
     "signal_missing_nl": "geen reactie op de benadering en geen sollicitatie",
     "status": "pending", "first_seen_at": "2026-09-01T00:00:00Z",
     "last_seen_at": "2026-09-03T00:00:00Z",
     "reappeared_after_rejection_at": None, "purged_at": None}
    for i in range(RETENTION_BIG_COUNT)
]

RETENTION_PAGE_SIZE = 50

RETENTION_TABLE_ROWS = [
    {"key": "rejected_applicant", "categorie": "Afgewezen sollicitant", "bewaartermijn": "12 maanden",
     "bron_opmerking": "AVG art. 6 lid 1 sub f", "legal_basis_ref": "art. 6.1.f",
     "anchor_column": "rejected_at", "action": "anonymise", "schema_ready": True,
     "signal_missing_nl": "geen nieuwe match, pipeline-activiteit of plaatsing sinds de afwijzing"},
    {"key": "placed_candidate", "categorie": "Geplaatste kandidaat (contract- en factuurdata)",
     "bewaartermijn": "7 jaar", "bron_opmerking": "fiscale bewaarplicht", "legal_basis_ref": "art. 6.1.c",
     "anchor_column": "placed_at", "action": "retain", "schema_ready": False, "signal_missing_nl": ""},
    {"key": "logs", "categorie": "Logs", "bewaartermijn": "90 dagen", "bron_opmerking": "infrastructuur",
     "legal_basis_ref": "art. 6.1.f", "anchor_column": None, "action": "infra_only",
     "schema_ready": False, "signal_missing_nl": ""},
]

# mode: "ok" | "error" (500 op de lijst). generated/approved/rejected/bulk
# leggen vast wat de UI daadwerkelijk verstuurde, zodat de asserties op de
# aanroep kunnen controleren en niet alleen op de tekst op het scherm.
RETENTION_STATE = {
    "mode": "ok", "generated": 0, "approved": [], "rejected": [],
    "bulk_calls": [], "dry_run": 0, "apollo_dry_run": 0,
    # Per categorie precies één 409 op de categoriebrede goedkeuring, en
    # daarna 200. Deterministisch, dus de test hangt niet van een volgorde
    # of een timing af: de eerste aanroep voor een categorie is altijd de
    # mismatch die de UI moet afvangen, de tweede slaagt altijd.
    "bulk_mismatch_done": set(),
    # modal_error laat uitsluitend de ophaling ZONDER limit mislukken: dat
    # is de fetch van de categoriebrede bevestigingsmodal, niet de lijst.
    "modal_error": False,
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
        # Ongefilterd, geen client_id: as-built afwijking 3 (§7.3.2) --
        # de eenmalige, ongefilterde ophaling die de consenttab gebruikt
        # om een titel te vinden bij een vastgelegde presentatietoestemming.
        all_jobs = [j for c in JOBS_BY_CLIENT.values() for j in c]
        json_response({"items": all_jobs, "total": len(all_jobs)})
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

    # ---- Bewaartermijnen (§7.3.1) ----
    if path == "/api/v1/admin/retention/table" and method == "GET":
        json_response({"markdown": "| Categorie |\n|---|\n", "rows": RETENTION_TABLE_ROWS})
        return
    if path == "/api/v1/admin/retention/run" and method == "POST":
        body = json.loads(request.post_data or "{}")
        if not body.get("dry_run"):
            json_response({"detail": {"code": "retention_run_no_longer_purges",
                                       "message": "Dit endpoint wist niets meer."}}, status=410)
            return
        RETENTION_STATE["dry_run"] += 1
        json_response({"dry_run": True, "categories": [
            {"key": "rejected_applicant", "status": "counted", "count": 2},
            {"key": "placed_candidate", "status": "not_applicable", "count": None},
            {"key": "logs", "status": "schema_not_ready", "count": None},
        ]})
        return
    if path == "/api/v1/admin/apollo-pool/purge" and method == "POST":
        body = json.loads(request.post_data or "{}")
        if not body.get("dry_run"):
            json_response({"detail": {"code": "apollo_pool_purge_no_longer_deletes",
                                       "message": "Dit endpoint wist niets meer."}}, status=410)
            return
        RETENTION_STATE["apollo_dry_run"] += 1
        json_response({"dry_run": True, "total": 9, "would_anonymise": 6,
                        "would_hard_delete": 3, "skipped": 4})
        return
    if path == "/api/v1/admin/retention/review/summary" and method == "GET":
        buckets = {}
        for it in RETENTION_ITEMS:
            buckets[(it["category"], it["status"])] = buckets.get((it["category"], it["status"]), 0) + 1
        rows = [{"category": c, "status": s, "n": n} for (c, s), n in sorted(buckets.items())]
        pending = sum(r["n"] for r in rows if r["status"] == "pending")
        json_response({"pending_total": pending, "by_category": rows})
        return
    if path == "/api/v1/admin/retention/review/generate" and method == "POST":
        RETENTION_STATE["generated"] += 1
        json_response({"rejected_applicant": {"queued": 2}, "referral": {"queued": 1}})
        return
    if path == "/api/v1/admin/retention/review/bulk" and method == "POST":
        body = json.loads(request.post_data or "{}")
        RETENTION_STATE["bulk_calls"].append(body)
        if body.get("decision") == "approved" and body.get("confirm") != "APPROVE":
            json_response({"detail": {"code": "retention_review_approve_requires_confirm",
                                       "message": 'confirm: "APPROVE" is required.'}}, status=409)
            return
        if body.get("category") and body.get("decision") == "approved":
            pending = [i for i in RETENTION_ITEMS
                        if i["category"] == body["category"] and i["status"] == "pending"]
            # Eerst één mismatch per categorie, zodat de 409-afhandeling in
            # de UI echt geraakt wordt; elke volgende poging voor dezelfde
            # categorie slaagt.
            if body["category"] not in RETENTION_STATE["bulk_mismatch_done"]:
                RETENTION_STATE["bulk_mismatch_done"].add(body["category"])
                json_response({"detail": {
                    "code": "retention_review_bulk_expected_count_mismatch",
                    "message": f"expected_count={body.get('expected_count')} but the category has "
                               f"{len(pending)} pending item(s).",
                }}, status=409)
                return
            results = []
            for it in pending:
                it["status"] = "purged"
                it["email"] = None
                results.append({"id": it["id"], "status": "purged"})
            json_response({"results": results})
            return
        results = []
        for item_id in body.get("ids") or []:
            for it in RETENTION_ITEMS:
                if it["id"] == item_id:
                    it["status"] = "purged" if body.get("decision") == "approved" else "rejected"
                    it["email"] = None
                    results.append({"id": item_id, "status": it["status"]})
        json_response({"results": results})
        return
    m = re.match(r"^/api/v1/admin/retention/review/(\d+)/(approve|reject)$", path)
    if m and method == "POST":
        item_id, decision = int(m.group(1)), m.group(2)
        body = json.loads(request.post_data or "{}")
        item = next((i for i in RETENTION_ITEMS if i["id"] == item_id), None)
        if item is None:
            json_response({"detail": "Review item not found"}, status=404)
            return
        if decision == "approve":
            if body.get("confirm") != "APPROVE":
                json_response({"detail": {"code": "retention_review_approve_requires_confirm",
                                           "message": 'confirm: "APPROVE" is required.'}}, status=409)
                return
            RETENTION_STATE["approved"].append(body)
            item["status"] = "purged"
            item["email"] = None
            json_response({"id": item_id, "status": "purged"})
            return
        RETENTION_STATE["rejected"].append(body)
        item["status"] = "rejected"
        item["email"] = None
        json_response({"id": item_id, "status": "rejected"})
        return
    if path == "/api/v1/admin/retention/review" and method == "GET":
        if RETENTION_STATE["mode"] == "error":
            json_response({"detail": "Server error"}, status=500)
            return
        if RETENTION_STATE["modal_error"] and qs.get("limit", [None])[0] is None and qs.get("category"):
            json_response({"detail": "Server error"}, status=500)
            return
        status = qs.get("status", ["pending"])[0]
        category = qs.get("category", [None])[0]
        rows = list(RETENTION_ITEMS)
        if status != "all":
            rows = [r for r in rows if r["status"] == status]
        if category:
            rows = [r for r in rows if r["category"] == category]
        sort = qs.get("sort", [None])[0]
        if sort:
            order = qs.get("order", ["asc"])[0]
            rows = sorted(rows, key=lambda r: (r.get(sort) is None, r.get(sort)),
                           reverse=(order == "desc"))
        total = len(rows)
        limit = qs.get("limit", [None])[0]
        offset = qint(qs, "offset", 0)
        page = rows[offset:offset + int(limit)] if limit else rows[offset:]
        json_response({"items": page, "total": total,
                        "limit": int(limit) if limit else None, "offset": offset})
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
    if path == "/api/v1/admin/candidates" and method == "GET":
        json_response({"items": [candidate_roster_item()], "total": 1})
        return
    m = re.match(r"^/api/v1/admin/candidates/sourced/(\d+)$", path)
    if m and method == "GET":
        if int(m.group(1)) == CANDIDATE_RECORD["id"]:
            json_response(candidate_detail())
        else:
            json_response({"detail": "Not found"}, status=404)
        return
    m = re.match(r"^/api/v1/admin/candidates/(\d+)/talentpool-consent$", path)
    if m and method == "PATCH":
        body = json.loads(request.post_data or "{}")
        CANDIDATE_STATE["talentpool_calls"].append(body)
        if body.get("consent"):
            CANDIDATE_RECORD.update({
                "consent_talentpool_at": "2026-09-03T00:00:00Z",
                "consent_talentpool_until": "2027-09-03T00:00:00Z",
                "consent_scope": body.get("scope"),
                "consent_source": "admin",
            })
        else:
            CANDIDATE_RECORD.update({
                "consent_talentpool_at": None, "consent_talentpool_until": None,
                "consent_scope": None, "consent_source": None,
            })
        json_response({
            "id": CANDIDATE_RECORD["id"],
            "consent_talentpool_at": CANDIDATE_RECORD["consent_talentpool_at"],
            "consent_talentpool_until": CANDIDATE_RECORD["consent_talentpool_until"],
            "consent_scope": CANDIDATE_RECORD["consent_scope"],
            "consent_source": CANDIDATE_RECORD["consent_source"],
            "lawful_basis": CANDIDATE_RECORD["lawful_basis"],
        })
        return
    m = re.match(r"^/api/v1/admin/candidates/(\d+)/spec-presentation-consent$", path)
    if m and method == "PATCH":
        body = json.loads(request.post_data or "{}")
        CANDIDATE_STATE["presentation_calls"].append(body)
        if body.get("consent"):
            CANDIDATE_RECORD.update({
                "consent_spec_presentation_at": "2026-09-05T00:00:00Z",
                "consent_spec_presentation_job_id": body.get("job_id"),
            })
        else:
            CANDIDATE_RECORD.update({
                "consent_spec_presentation_at": None, "consent_spec_presentation_job_id": None,
            })
        json_response({
            "id": CANDIDATE_RECORD["id"],
            "consent_spec_presentation_at": CANDIDATE_RECORD["consent_spec_presentation_at"],
            "consent_spec_presentation_job_id": CANDIDATE_RECORD["consent_spec_presentation_job_id"],
        })
        return
    if path == "/api/v1/admin/candidates/referral" and method == "POST":
        body = json.loads(request.post_data or "{}")
        CANDIDATE_STATE["referral_calls"].append(body)
        mode = CANDIDATE_STATE["referral_mode"]
        if mode == "suppressed":
            json_response({"detail": {
                "code": "referral_email_suppressed",
                "message": "This e-mail address is on the suppression list.",
            }}, status=409)
            return
        if mode == "exists":
            json_response({"detail": {
                "code": "referral_candidate_exists", "candidate_id": CANDIDATE_RECORD["id"],
                "message": f"A candidate record already exists for this e-mail address (id {CANDIDATE_RECORD['id']}).",
            }}, status=409)
            return
        if mode == "unknown":
            json_response({"detail": {
                "code": "referral_something_else",
                "message": "Something else went wrong that this screen does not know a Dutch sentence for.",
            }}, status=409)
            return
        json_response({
            "id": 9001, "full_name": body.get("full_name"), "source": "referral",
            "lawful_basis": "toestemming_referral", "date_found": "2026-09-10",
            "referred_by": body.get("referred_by"), "confirmation_email_sent": True,
        }, status=201)
        return

    json_response({"items": [], "total": 0})


def click_or_fail(page, failures, selector, what):
    """Klikken zonder dat een ontbrekend element de hele run in een
    traceback laat eindigen: dan mist niet alleen deze assertie maar ook
    alles wat erna komt. Een gemiste knop hoort in de failure-lijst, net
    als de pagineerknop dat al deed."""
    if page.query_selector(selector) is None:
        failures.append(f"retention: {what} niet gevonden ({selector})")
        return False
    page.click(selector)
    return True


def text_of(page, selector):
    """Tekst van een element, of een lege string als het er niet is. Een
    ontbrekend element hoort een falende assertie op te leveren, geen
    traceback die de rest van de run overslaat."""
    el = page.query_selector(selector)
    return (el.text_content() or "") if el else ""


def is_disabled(page, selector, default=True):
    el = page.query_selector(selector)
    return default if el is None else bool(el.is_disabled())


def wait_until(page, predicate, timeout=6000, step=50):
    """Wacht op een voorwaarde in plaats van op een aantal milliseconden.
    Een vaste wait is in een suite die tien secties na elkaar draait geen
    garantie: dezelfde stap die geïsoleerd 26 van de 26 keer klopt, valt
    onder belasting soms net buiten het venster. Geeft True zodra de
    voorwaarde geldt, anders False na `timeout`; de aanroeper maakt er dan
    een regel in de failure-lijst van."""
    waited = 0
    while waited < timeout:
        try:
            if predicate():
                return True
        except Exception:
            pass
        page.wait_for_timeout(step)
        waited += step
    return False


def wait_for_text(page, selector, needle, timeout=6000):
    return wait_until(page, lambda: needle in text_of(page, selector), timeout)


def wait_for_enabled(page, selector, enabled=True, timeout=6000):
    return wait_until(page, lambda: (page.query_selector(selector) is not None)
                      and (is_disabled(page, selector) is not enabled), timeout)


def wait_for_calls(page, bucket, count, timeout=6000):
    """Wacht tot de stub `count` aanroepen heeft gezien; dat is het
    signaal dat het antwoord verwerkt is, niet een gok over hoe lang dat
    duurt."""
    return wait_until(page, lambda: len(bucket) >= count, timeout)


def fill_or_fail(page, failures, selector, value, what):
    if page.query_selector(selector) is None:
        failures.append(f"retention: {what} niet gevonden ({selector})")
        return False
    page.fill(selector, value)
    return True


def check_retention_category_labels():
    """D3: elke categorie uit core/retention.RETENTION_TABLE heeft een
    Nederlands label in js/labels.js. Zonder dat toont de droogloop of de
    bewaartabel de ruwe sleutel (placed_candidate, logs). Statisch, geen
    browser: de map is een tekstbestand en de tabel ook."""
    problems = []
    retention_py = (ROOT / "talent-os" / "backend" / "core" / "retention.py").read_text(encoding="utf-8")
    keys = re.findall(r'key="([a-z_]+)"', retention_py)
    labels_js = (WEBSITE / "admin" / "js" / "labels.js").read_text(encoding="utf-8")
    block = re.search(r"retentiecategorie:\s*\{(.*?)\n    \},", labels_js, re.S)
    if not block:
        return ["labels.js: de map retentiecategorie is niet gevonden"]
    mapped = set(re.findall(r"^\s*([a-z_]+):", block.group(1), re.M))
    for key in keys:
        if key not in mapped:
            problems.append(f"labels.js: RETENTION_TABLE-categorie {key!r} heeft geen Nederlands label")
    # apollo_pool_purge is geen RETENTION_TABLE-rij maar staat wel in de
    # beoordelingslijst; die moet er dus juist wel in staan.
    if "apollo_pool_purge" not in mapped:
        problems.append("labels.js: de UI-eigen categorie 'apollo_pool_purge' ontbreekt")
    return problems


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FAIL: playwright not installed")
        sys.exit(1)

    port = find_free_port()
    start_server(port)
    base = f"http://127.0.0.1:{port}/admin/"

    failures = check_retention_category_labels()

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

        # ---- Bewaartermijnen (§7.3.1) ----
        errors_before = len(console_errors)
        click_or_fail(page, failures, '.nav-link[data-section="retention"]', "het sidebar-item Bewaartermijnen")
        if not wait_until(page, lambda: page.eval_on_selector_all('#retentionBody tr', "els => els.length")
                          == RETENTION_PAGE_SIZE):
            failures.append("retention: de lijst vulde zich niet met een volle pagina")
        if not wait_for_text(page, '#retentionSummary', "Laatst gegenereerd"):
            failures.append("retention: de samenvatting vulde zich niet")

        summary_text = text_of(page, '#retentionSummary')
        if "Te beoordelen" not in summary_text or "3" not in summary_text:
            failures.append(f"retention: samenvatting toont de telling niet -- kreeg {summary_text[:160]!r}")
        if "Heropend na afwijzing" not in summary_text:
            failures.append("retention: de tegel voor heropende items ontbreekt terwijl er er één is")
        if "Laatst gegenereerd" not in summary_text:
            failures.append("retention: de tegel 'Laatst gegenereerd' ontbreekt")

        cat_text = text_of(page, '#retentionCategoryBody')
        for expect in ("Afgewezen sollicitant", "Referral"):
            if expect not in cat_text:
                failures.append(f"retention: categorietabel mist {expect!r} -- kreeg {cat_text[:160]!r}")
        if "rejected_applicant" in cat_text:
            failures.append("retention: de ruwe categoriesleutel lekte in de categorietabel")

        pending_total = len([i for i in RETENTION_ITEMS if i["status"] == "pending"])
        rows = page.eval_on_selector_all('#retentionBody tr', "els => els.length")
        if rows != RETENTION_PAGE_SIZE:
            failures.append(f"retention: lijst toonde {rows} rijen, verwacht {RETENTION_PAGE_SIZE} "
                            f"(de paginagrootte, niet de volle {pending_total})")
        footer = text_of(page, '#retentionCount')
        if f"van {pending_total}" not in footer:
            failures.append(f"retention: footer telt niet de volle set -- kreeg {footer.strip()!r}")
        if page.query_selector('#retentionPagination [data-action="page"][data-page="2"]') is None:
            failures.append("retention: geen pagineerknop terwijl er meer dan één pagina is")
        list_text = text_of(page, '#retentionBody')
        if "kandidaat #1482" not in list_text:
            failures.append(f"retention: onderwerp niet als 'kandidaat #1482' getoond -- kreeg {list_text[:200]!r}")
        if "Eerder afgewezen, opnieuw verschenen op" not in list_text:
            failures.append("retention: de heropende rij mist zijn eigen regel in de statuskolom")
        if "example.invalid" in list_text:
            failures.append("retention: een e-mailadres uit de respons stond in de lijst")
        if "anonymise" in list_text or "pending" in list_text:
            failures.append("retention: een ruwe enumwaarde lekte in de lijst")

        # Rijselectie en bulkbalk (§7.2a).
        click_or_fail(page, failures, '#retentionBody input[data-action="retention-select"]', "een selectievakje in de lijst")
        wait_for_text(page, '#retentionBulkbar', "geselecteerd")
        bulk_text = text_of(page, '#retentionBulkbar')
        if "1 geselecteerd" not in bulk_text:
            failures.append(f"retention: bulkbalk verscheen niet bij een selectie -- kreeg {bulk_text[:120]!r}")
        row_selected = page.eval_on_selector('#retentionBody tr', "el => el.classList.contains('a-row-selected')")
        if not row_selected:
            failures.append("retention: een geselecteerde rij kreeg geen zichtbare selectiestaat")
        click_or_fail(page, failures, '[data-action="retention-clear-selection"]', "de knop Selectie wissen")
        wait_until(page, lambda: page.eval_on_selector('#retentionBulkbar', "el => el.hidden") is True)
        if not page.eval_on_selector('#retentionBulkbar', "el => el.hidden"):
            failures.append("retention: bulkbalk bleef staan na 'Selectie wissen'")

        # Server-side sorteren (BV10): term_expired_at oplopend zet juli vóór augustus.
        click_or_fail(page, failures, '#retentionHead th[data-sort-key="term_expired_at"]', "de sorteerbare kop Termijn verlopen")
        if not wait_until(page, lambda: "903" in text_of(page, '#retentionBody tr td:nth-child(3)')):
            failures.append("retention: de lijst herlaadde niet na het sorteren")
        if page.get_attribute('#retentionHead th[data-sort-key="term_expired_at"]', "aria-sort") != "ascending":
            failures.append("retention: aria-sort kwam niet op 'ascending' te staan")
        first_subject = text_of(page, '#retentionBody tr td:nth-child(3)')
        if "903" not in first_subject:
            failures.append(f"retention: server-side sorteren gaf als eerste rij {first_subject.strip()!r}, verwacht kandidaat #903")

        # Lijst genereren.
        click_or_fail(page, failures, '#section-retention [data-action="retention-generate"]', "de knop Lijst genereren")
        if not wait_until(page, lambda: RETENTION_STATE["generated"] >= 1):
            failures.append("retention: 'Lijst genereren' riep generate niet aan")
        if RETENTION_STATE["generated"] != 1:
            failures.append(f"retention: 'Lijst genereren' riep generate {RETENTION_STATE['generated']}x aan, verwacht 1")

        # Goedkeuren: getypte bevestiging, fout en goed.
        click_or_fail(page, failures, '#retentionBody [data-action="retention-approve"][data-id="1"]', "de goedkeurknop van item 1")
        if not wait_until(page, lambda: page.query_selector('#retentionApproveModal input[type=text]') is not None):
            failures.append("retention: de goedkeurmodal ging niet open")
        modal_text = text_of(page, '#retentionApproveModal')
        if "k••••@example.invalid" not in modal_text:
            failures.append(f"retention: de goedkeurmodal toont het adres niet gemaskeerd -- kreeg {modal_text[:200]!r}")
        if "kandidaat1@example.invalid" in modal_text:
            failures.append("retention: het volledige e-mailadres stond in de goedkeurmodal")
        danger = "#retentionApproveModal .btn-outline-danger"
        if not is_disabled(page, danger):
            failures.append("retention: de goedkeurknop stond meteen aan zonder getypte bevestiging")
        fill_or_fail(page, failures, "#retentionApproveModal input[type=text]", "approve",
                     "het bevestigingsveld van de goedkeurmodal")
        # Niet 150ms afwachten maar de staat vasthouden: de knop moet uit
        # BLIJVEN, dus een korte stabiliteitscontrole in plaats van één meting.
        if wait_for_enabled(page, danger, True, timeout=400):
            failures.append("retention: de goedkeurknop ging aan bij een niet-kloppende bevestiging")
        fill_or_fail(page, failures, "#retentionApproveModal input[type=text]", "APPROVE",
                     "het bevestigingsveld van de goedkeurmodal")
        if not wait_for_enabled(page, danger, True):
            failures.append("retention: de goedkeurknop bleef uit terwijl APPROVE getypt was")
        click_or_fail(page, failures, danger, "de goedkeurknop in de modal")
        if not wait_for_calls(page, RETENTION_STATE["approved"], 1):
            failures.append("retention: er kwam geen approve-aanroep binnen")
        if not wait_until(page, lambda: "kandidaat #1482" not in text_of(page, '#retentionBody')):
            failures.append("retention: de lijst herlaadde niet na het goedkeuren")
        if not RETENTION_STATE["approved"] or RETENTION_STATE["approved"][0].get("confirm") != "APPROVE":
            failures.append(f"retention: approve-aanroep droeg niet confirm='APPROVE' -- {RETENTION_STATE['approved']!r}")
        after_approve = text_of(page, '#retentionBody')
        if "kandidaat #1482" in after_approve:
            failures.append("retention: het goedgekeurde item staat nog in de lijst na herladen")

        # Afwijzen: gewone modal met notitie, geen getypte bevestiging.
        click_or_fail(page, failures, '#retentionBody [data-action="retention-reject"][data-id="3"]', "de afwijsknop van item 3")
        if not wait_until(page, lambda: page.query_selector('#retentionRejectNote') is not None):
            failures.append("retention: de afwijsmodal ging niet open")
        if page.query_selector('#adminConfirmModal input[type=text]') is not None:
            failures.append("retention: afwijzen vroeg een getypte bevestiging; dat hoort alleen bij goedkeuren")
        fill_or_fail(page, failures, '#retentionRejectNote', 'Bewaren, loopt nog een gesprek.',
                     'het notitieveld van de afwijsmodal')
        click_or_fail(page, failures, '#adminConfirmModal .btn-primary', "de bevestigknop van de afwijsmodal")
        if not wait_for_calls(page, RETENTION_STATE["rejected"], 1):
            failures.append("retention: er kwam geen reject-aanroep binnen")
        if not RETENTION_STATE["rejected"]:
            failures.append("retention: afwijzen deed geen reject-aanroep")
        elif not (RETENTION_STATE["rejected"][0].get("note") or "").startswith("Bewaren"):
            failures.append(f"retention: de notitie ging niet mee in de reject-aanroep -- {RETENTION_STATE['rejected'][0]!r}")

        # Statusfilter 'Afgewezen (bewaard)'.
        page.select_option('#retentionStatusFilter', 'rejected')
        if not wait_for_text(page, '#retentionBody', "prospect #77"):
            failures.append(f"retention: filter 'Afgewezen (bewaard)' toont de bewaarde rijen niet -- "
                            f"kreeg {text_of(page, '#retentionBody')[:200]!r}")
        page.select_option('#retentionStatusFilter', 'pending')
        if not wait_for_text(page, '#retentionBody', "kandidaat #903"):
            failures.append("retention: de lijst kwam niet terug op het standaardfilter")

        # Categoriebreed goedkeuren op een categorie met MEER openstaande
        # items dan de paginagrootte: de modal haalt zonder limit op, dus
        # expected_count is de volle telling en niet de eerste pagina.
        click_or_fail(page, failures, f'[data-action="retention-category-approve"][data-category="{RETENTION_BIG_CATEGORY}"]', "Alles goedkeuren voor de grote categorie")
        # Wachten tot de rijen er staan, niet tot de klok afloopt.
        if not wait_until(page, lambda: page.eval_on_selector_all(
                '#retentionBulkModal .a-listrow', "els => els.length") == RETENTION_BIG_COUNT):
            failures.append("retention: de bulkmodal vulde zich niet met de rijen van de categorie")
        bulk_modal = text_of(page, '#retentionBulkModal')
        if "kandidaat #2000" not in bulk_modal:
            failures.append(f"retention: de bulkmodal toont de geraakte rijen niet -- kreeg {bulk_modal[:200]!r}")
        modal_rows = page.eval_on_selector_all('#retentionBulkModal .a-listrow', "els => els.length")
        if modal_rows != RETENTION_BIG_COUNT:
            failures.append(f"retention: de bulkmodal toonde {modal_rows} rijen, verwacht {RETENTION_BIG_COUNT} "
                            "(de hele categorie, dus zonder limit opgehaald)")
        fill_or_fail(page, failures, "#retentionBulkModal input[type=text]", "APPROVE",
                     "het bevestigingsveld van de bulkmodal")
        bulk_calls_before = len(RETENTION_STATE["bulk_calls"])
        if not wait_for_enabled(page, "#retentionBulkModal .btn-outline-danger", True):
            failures.append("retention: de bulkknop bleef uit terwijl APPROVE getypt was en de lijst geladen is")
        else:
            click_or_fail(page, failures, "#retentionBulkModal .btn-outline-danger", "de bulkknop")
        if not wait_for_calls(page, RETENTION_STATE["bulk_calls"], bulk_calls_before + 1):
            failures.append("retention: de categoriebrede goedkeuring stuurde geen aanroep")
        if not wait_for_text(page, '#retentionBulkAlert', "De lijst is veranderd"):
            failures.append("retention: 409 mismatch werd niet als inline-melding getoond -- "
                            f"kreeg {text_of(page, '#retentionBulkAlert')[:200]!r}")
        if not page.evaluate("() => document.getElementById('retentionBulkModal').classList.contains('show')"):
            failures.append("retention: de bulkmodal sloot bij een 409 mismatch; hij hoort open te blijven")
        last_bulk = RETENTION_STATE["bulk_calls"][-1] if RETENTION_STATE["bulk_calls"] else {}
        if last_bulk.get("expected_count") != RETENTION_BIG_COUNT or last_bulk.get("confirm") != "APPROVE":
            failures.append(f"retention: categoriebrede aanroep droeg niet de volle telling plus confirm -- {last_bulk!r}")
        # Na de 409 vervalt het oude aantal en gaat de knop op slot: een
        # tweede poging mag niet hetzelfde verouderde getal opnieuw sturen,
        # ook niet als iemand langs de disabled heen klikt.
        calls_before_retry = len(RETENTION_STATE["bulk_calls"])
        locked = page.eval_on_selector("#retentionBulkModal .btn-outline-danger",
                                        "el => ({disabled: el.disabled, lock: el.dataset.gspLock})")
        if not locked["disabled"] or locked["lock"] != "1":
            failures.append(f"retention: de bulkknop stond na de 409 niet uit en op slot -- {locked!r}")
        if wait_for_enabled(page, "#retentionBulkModal .btn-outline-danger", True, timeout=600):
            click_or_fail(page, failures, "#retentionBulkModal .btn-outline-danger", "de bulkknop")
            page.wait_for_timeout(500)
        # Geforceerde klik: een click() vanuit JS gaat langs de disabled
        # heen die de browser voor een muisklik afvangt. De handler zelf
        # hoort de handeling dan nog steeds te weigeren.
        page.evaluate("() => document.querySelector('#retentionBulkModal .btn-outline-danger').click()")
        page.wait_for_timeout(600)
        if len(RETENTION_STATE["bulk_calls"]) != calls_before_retry:
            failures.append("retention: een tweede klik na de 409 stuurde alsnog een bulkaanroep "
                            "zonder dat de telling ververst was")
        if not wait_until(page, lambda: page.query_selector('[data-action="retention-bulk-refresh"]') is not None):
            failures.append("retention: de knop Verversen verscheen niet na de 409")
        click_or_fail(page, failures, '[data-action="retention-bulk-refresh"]', "de knop Verversen")
        if not wait_for_enabled(page, "#retentionBulkModal .btn-outline-danger", True):
            failures.append("retention: na verversen bleef de bulkknop uit")
        elif page.eval_on_selector("#retentionBulkModal .btn-outline-danger",
                                    "el => el.dataset.gspLock") == "1":
            failures.append("retention: het slot bleef op de bulkknop staan na verversen")
        else:
            calls_before_ok = len(RETENTION_STATE["bulk_calls"])
            click_or_fail(page, failures, "#retentionBulkModal .btn-outline-danger", "de bulkknop")
            if not wait_for_calls(page, RETENTION_STATE["bulk_calls"], calls_before_ok + 1):
                failures.append("retention: de tweede categoriebrede goedkeuring stuurde geen aanroep")
        if not wait_for_text(page, '#retentionBulkModal', "Verwerkt"):
            failures.append("retention: de bulkuitkomst werd niet in dezelfde modal getoond -- "
                            f"kreeg {text_of(page, '#retentionBulkModal')[:200]!r}")
        result_text = text_of(page, '#retentionBulkModal')
        click_or_fail(page, failures, '#retentionBulkModal [data-action="close-modal"]', "de sluitknop van de bulkmodal")
        page.wait_for_timeout(300)
        # De opzettelijke 409 hierboven logt zijn eigen "Failed to load
        # resource": ruis van deze negatieve test, geen fout van het paneel.
        console_errors[:] = [e for e in console_errors if "409 (Conflict)" not in e]

        # Droogloop: read-only, zonder bevestiging. De twee kaarten staan
        # ingeklapt (<details>), dus eerst openen zoals een gebruiker dat doet.
        click_or_fail(page, failures, '#section-retention details:nth-of-type(1) > summary', "de kaart Droogloop")
        click_or_fail(page, failures, '#section-retention details:nth-of-type(2) > summary', "de kaart Apollo-bulkpool")
        page.wait_for_timeout(200)
        click_or_fail(page, failures, '[data-action="retention-dryrun"]', "de knop Uitvoeren van de droogloop")
        wait_for_text(page, '#retentionDryRun', "telt niet mee")
        dry_text = text_of(page, '#retentionDryRun')
        if "telt niet mee: bewaren" not in dry_text or "kolom bestaat nog niet" not in dry_text:
            failures.append(f"retention: droogloop toont de toelichting per status niet -- kreeg {dry_text[:200]!r}")
        click_or_fail(page, failures, '[data-action="retention-apollo-dryrun"]', "de knop Uitvoeren van de Apollo-droogloop")
        wait_for_text(page, '#retentionApolloDryRun', "Zou anonimiseren")
        apollo_text = text_of(page, '#retentionApolloDryRun')
        if "Zou anonimiseren" not in apollo_text or "Overgeslagen" not in apollo_text:
            failures.append(f"retention: de Apollo-droogloop toont de vier getallen niet -- kreeg {apollo_text[:200]!r}")

        # Bewaartabel: alleen laden als de kaart opengaat.
        page.evaluate("() => { document.getElementById('retentionTableDetails').open = true; }")
        wait_for_text(page, '#retentionTableCard', "Komt niet in de beoordelingslijst")
        table_text = text_of(page, '#retentionTableCard')
        if "Komt niet in de beoordelingslijst" not in table_text:
            failures.append(f"retention: de bewaartabel mist de badge bij retain/infra_only -- kreeg {table_text[:200]!r}")

        new_errors = console_errors[errors_before:]
        if new_errors:
            failures.append(f"retention: {len(new_errors)} console error(s): {new_errors[:3]}")

        # Een categoriemodal waarvan de verse telling mislukt, mag niets
        # goedkeuren: zonder de reset van dat aantal bleef het getal van de
        # vorige categorie staan en was de knop bruikbaar zodra APPROVE
        # getypt was.
        calls_before = len(RETENTION_STATE["bulk_calls"])
        click_or_fail(page, failures, '[data-action="retention-category-approve"][data-category="referral"]', "Alles goedkeuren voor referral")
        if not wait_until(page, lambda: page.eval_on_selector_all(
                '#retentionBulkModal .a-listrow', "els => els.length") == 1):
            failures.append("retention: de bulkmodal voor referral vulde zich niet")
        fill_or_fail(page, failures, "#retentionBulkModal input[type=text]", "APPROVE",
                     "het bevestigingsveld van de bulkmodal")
        wait_for_enabled(page, "#retentionBulkModal .btn-outline-danger", True)
        if is_disabled(page, "#retentionBulkModal .btn-outline-danger"):
            failures.append("retention: de bulkknop bleef uit bij een geslaagde categorieophaling")
        expected_after_ok = page.evaluate("() => Admin._retention.bulkExpected")
        if expected_after_ok != 1:
            failures.append(f"retention: expected_count na een geslaagde ophaling was {expected_after_ok!r}, verwacht 1")
        # Dezelfde modal opnieuw vullen terwijl de ophaling faalt (dat is wat
        # de knop Verversen doet): het aantal van zojuist mag niet blijven
        # staan, anders keurt een tweede klik een categorie goed die dit
        # scherm nooit heeft laten zien.
        RETENTION_STATE["modal_error"] = True
        page.evaluate("() => Admin.fillRetentionCategoryModal(Admin._retentionCategoryModal, 'referral')")
        if not wait_until(page, lambda: "Verversen" in text_of(page, '#retentionBulkModal')):
            failures.append("retention: de mislukte hervulling toonde geen melding")
        if page.evaluate("() => Admin._retention.bulkExpected") != 0:
            failures.append("retention: na een mislukte categorieophaling bleef het oude aantal staan")
        if not is_disabled(page, "#retentionBulkModal .btn-outline-danger"):
            failures.append("retention: de bulkknop bleef bruikbaar na een mislukte categorieophaling")
            click_or_fail(page, failures, "#retentionBulkModal .btn-outline-danger", "de bulkknop")
            page.wait_for_timeout(600)
        if len(RETENTION_STATE["bulk_calls"]) != calls_before:
            failures.append("retention: een categoriemodal met een mislukte telling keurde alsnog iets goed")
        fail_alert = text_of(page, '#retentionBulkModal')
        if "Verversen" not in fail_alert:
            failures.append(f"retention: mislukte modalophaling bood geen Verversen -- kreeg {fail_alert[:160]!r}")
        click_or_fail(page, failures, '#retentionBulkModal [data-action="close-modal"]', "de sluitknop van de bulkmodal")
        page.wait_for_timeout(300)
        RETENTION_STATE["modal_error"] = False
        console_errors[:] = [e for e in console_errors if "500 (Internal Server Error)" not in e]

        # 500 met retry. De opzettelijke 500 logt zijn eigen console error;
        # de grens gaat er daarom hierna overheen, zoals bij analytics.
        RETENTION_STATE["mode"] = "error"
        page.select_option('#retentionStatusFilter', 'all')
        wait_for_text(page, '#retentionBody', "probeer opnieuw")
        err_text = text_of(page, '#retentionBody')
        if "probeer opnieuw" not in err_text.lower():
            failures.append(f"retention: foutstaat mist de retrylink -- kreeg {err_text[:200]!r}")
        RETENTION_STATE["mode"] = "ok"
        errors_before = len(console_errors)
        retry = page.query_selector('#retentionBody a')
        if retry is None:
            failures.append("retention: geen retrylink gevonden om van de fout te herstellen")
        else:
            retry.click()
            wait_until(page, lambda: "probeer opnieuw" not in text_of(page, '#retentionBody').lower())
            recovered = text_of(page, '#retentionBody')
            if "Kon niet laden" in recovered or "probeer opnieuw" in recovered.lower():
                failures.append(f"retention: herstelde niet na de retry -- kreeg {recovered[:200]!r}")
        new_errors = console_errors[errors_before:]
        if new_errors:
            failures.append(f"retention (na retry): {len(new_errors)} console error(s): {new_errors[:3]}")

        # ---- Kandidaatdrawer: tab Toestemmingen + referral-intake (§7.3.2) ----
        errors_before = len(console_errors)
        page.click('.nav-link[data-section="candidates"]')
        wait_until(page, lambda: page.query_selector('#section-candidates table tbody tr [data-action="view-candidate"]') is not None)
        click_or_fail(page, failures, '#section-candidates table tbody tr [data-action="view-candidate"]',
                      "de bekijkknop van de kandidaatrij")
        if not wait_until(page, lambda: page.query_selector('#candidateDrawerTabContent') is not None):
            failures.append("candidates: de kandidaatdrawer ging niet open")
        click_or_fail(page, failures, '#candidateDrawer [data-tab="toestemmingen"]', "de tab Toestemmingen")
        if not wait_until(page, lambda: page.query_selector('[data-action="candidate-talentpool-edit"]') is not None):
            failures.append("candidates: de tab Toestemmingen rendeerde niet")

        # Talentpool vastleggen met lege evidence: inline fout, nul aanroepen.
        click_or_fail(page, failures, '[data-action="candidate-talentpool-edit"]', "de knop Wijzigen (talentpool)")
        if not wait_until(page, lambda: page.query_selector('#tpEvidence') is not None):
            failures.append("candidates: de talentpoolmodal ging niet open")
        click_or_fail(page, failures, '#candidateTalentpoolModal .btn-primary', "Opslaan (talentpool, leeg)")
        if not wait_until(page, lambda: "Vul kort in" in text_of(page, '#tpEvidenceError')):
            failures.append("candidates: lege evidence gaf geen inline fout in de talentpoolmodal")
        if CANDIDATE_STATE["talentpool_calls"]:
            failures.append("candidates: een talentpoolaanroep ging uit met lege evidence")

        # Vastleggen zonder omvang: nul aanroepen.
        page.fill('#tpEvidence', 'Ondertekend formulier van 2 september.')
        click_or_fail(page, failures, '#candidateTalentpoolModal .btn-primary', "Opslaan (talentpool, zonder omvang)")
        if not wait_until(page, lambda: text_of(page, '#tpScopeError').strip() != ''):
            failures.append("candidates: het ontbreken van een omvang gaf geen inline fout")
        if CANDIDATE_STATE["talentpool_calls"]:
            failures.append("candidates: een talentpoolaanroep ging uit zonder omvang")

        # Vastleggen met omvang: één aanroep, consent=True plus scope.
        page.select_option('#tpScope', 'matching_and_contact')
        click_or_fail(page, failures, '#candidateTalentpoolModal .btn-primary', "Opslaan (talentpool, vastleggen)")
        if not wait_for_calls(page, CANDIDATE_STATE["talentpool_calls"], 1):
            failures.append("candidates: het vastleggen van talentpooltoestemming stuurde geen aanroep")
        elif (CANDIDATE_STATE["talentpool_calls"][0].get("scope") != "matching_and_contact"
              or CANDIDATE_STATE["talentpool_calls"][0].get("consent") is not True):
            failures.append(f"candidates: talentpool-vastleggen stuurde de verkeerde payload -- {CANDIDATE_STATE['talentpool_calls'][0]!r}")
        wait_until(page, lambda: page.query_selector('#candidateTalentpoolModal.show') is None)

        # Intrekken: geen scope in de payload.
        click_or_fail(page, failures, '[data-action="candidate-talentpool-edit"]', "Wijzigen (talentpool, intrekken)")
        wait_until(page, lambda: page.query_selector('#tpConsentWithdraw') is not None)
        page.check('#tpConsentWithdraw')
        page.fill('#tpEvidence', 'Telefonisch ingetrokken op 4 september.')
        click_or_fail(page, failures, '#candidateTalentpoolModal .btn-primary', "Opslaan (talentpool, intrekken)")
        if not wait_for_calls(page, CANDIDATE_STATE["talentpool_calls"], 2):
            failures.append("candidates: het intrekken van talentpooltoestemming stuurde geen aanroep")
        else:
            second_tp = CANDIDATE_STATE["talentpool_calls"][1]
            if second_tp.get("consent") is not False or "scope" in second_tp:
                failures.append(f"candidates: intrekken stuurde toch een omvang mee -- {second_tp!r}")

        # Presentatie vastleggen: stuurt job_id; intrekken stuurt het niet.
        click_or_fail(page, failures, '[data-action="candidate-presentation-edit"]', "Vastleggen (presentatie)")
        if not wait_until(page, lambda: page.query_selector('#spJob') is not None and not is_disabled(page, '#spJob')):
            failures.append("candidates: de vacaturekiezer laadde niet, of bleef disabled, in de presentatiemodal")
        page.select_option('#spJob', '201')
        page.fill('#spEvidence', 'E-mail in het dossier van 5 september.')
        click_or_fail(page, failures, '#candidatePresentationModal .btn-primary', "Opslaan (presentatie, vastleggen)")
        if not wait_for_calls(page, CANDIDATE_STATE["presentation_calls"], 1):
            failures.append("candidates: het vastleggen van presentatietoestemming stuurde geen aanroep")
        elif CANDIDATE_STATE["presentation_calls"][0].get("job_id") != 201:
            failures.append(f"candidates: presentatie-vastleggen stuurde niet job_id=201 -- {CANDIDATE_STATE['presentation_calls'][0]!r}")
        wait_until(page, lambda: page.query_selector('#candidatePresentationModal.show') is None)

        click_or_fail(page, failures, '[data-action="candidate-presentation-edit"]', "Vastleggen (presentatie, intrekken)")
        wait_until(page, lambda: page.query_selector('#spConsentWithdraw') is not None)
        page.check('#spConsentWithdraw')
        page.fill('#spEvidence', 'Telefonisch ingetrokken op 6 september.')
        click_or_fail(page, failures, '#candidatePresentationModal .btn-primary', "Opslaan (presentatie, intrekken)")
        if not wait_for_calls(page, CANDIDATE_STATE["presentation_calls"], 2):
            failures.append("candidates: het intrekken van presentatietoestemming stuurde geen aanroep")
        else:
            second_sp = CANDIDATE_STATE["presentation_calls"][1]
            if second_sp.get("consent") is not False or "job_id" in second_sp:
                failures.append(f"candidates: intrekken van presentatie stuurde toch een job_id mee -- {second_sp!r}")

        # Referral: twee eigen 409's op detail.code, val terug op detail.message.
        click_or_fail(page, failures, '#candidateDrawer [data-action="close-modal"]', "sluitknop van de kandidaatdrawer")
        wait_until(page, lambda: page.query_selector('#candidateDrawer.show') is None)

        CANDIDATE_STATE["referral_mode"] = "suppressed"
        click_or_fail(page, failures, '[data-action="open-referral-modal"]', "de knop Referral vastleggen")
        if not wait_until(page, lambda: page.query_selector('#refFullName') is not None):
            failures.append("candidates: de referralmodal ging niet open")
        page.fill('#refFullName', 'Voorbeeld Referral')
        page.fill('#refEmail', 'referral@example.invalid')
        page.fill('#refReferredBy', 'Jan Voorbeeld')
        if "Jan Voorbeeld" not in text_of(page, '#referralInfoName'):
            failures.append("candidates: het informatieblok toont de naam uit Aangedragen door niet live")
        page.fill('#refEvidence', 'Mondeling bevestigd door Jan op 3 september.')
        click_or_fail(page, failures, '#candidateReferralModal .btn-primary', "Vastleggen (referral, suppressed)")
        if not wait_for_calls(page, CANDIDATE_STATE["referral_calls"], 1):
            failures.append("candidates: de referral-aanroep (suppressed) ging niet uit")
        if not wait_for_text(page, '#candidateReferralAlert', 'suppressielijst'):
            failures.append(f"candidates: de suppressielijst-melding verscheen niet -- kreeg {text_of(page, '#candidateReferralAlert')!r}")
        if page.query_selector('#candidateReferralAlert [data-action]') is not None:
            failures.append("candidates: de suppressielijst-melding toonde onterecht een knop")

        CANDIDATE_STATE["referral_mode"] = "exists"
        click_or_fail(page, failures, '#candidateReferralModal .btn-primary', "Vastleggen (referral, exists)")
        if not wait_for_calls(page, CANDIDATE_STATE["referral_calls"], 2):
            failures.append("candidates: de referral-aanroep (exists) ging niet uit")
        if not wait_until(page, lambda: page.query_selector('[data-action="candidate-referral-open-existing"]') is not None):
            failures.append("candidates: de knop Kandidaat openen verscheen niet bij referral_candidate_exists")
        else:
            click_or_fail(page, failures, '[data-action="candidate-referral-open-existing"]', "de knop Kandidaat openen")
            if not wait_until(page, lambda: page.query_selector('#candidateDrawerTabContent') is not None
                              and page.query_selector('#candidateReferralModal.show') is None):
                failures.append("candidates: 'Kandidaat openen' opende de drawer niet (of sloot de referralmodal niet)")

        CANDIDATE_STATE["referral_mode"] = "unknown"
        click_or_fail(page, failures, '#candidateDrawer [data-action="close-modal"]',
                      "sluitknop van de kandidaatdrawer (na Kandidaat openen)")
        wait_until(page, lambda: page.query_selector('#candidateDrawer.show') is None)
        click_or_fail(page, failures, '[data-action="open-referral-modal"]', "Referral vastleggen (opnieuw)")
        wait_until(page, lambda: page.query_selector('#refFullName') is not None)
        page.fill('#refFullName', 'Voorbeeld Referral Twee')
        page.fill('#refEmail', 'referral2@example.invalid')
        page.fill('#refReferredBy', 'Piet Voorbeeld')
        page.fill('#refEvidence', 'Mondeling bevestigd door Piet op 4 september.')
        click_or_fail(page, failures, '#candidateReferralModal .btn-primary', "Vastleggen (referral, onbekende code)")
        if not wait_for_calls(page, CANDIDATE_STATE["referral_calls"], 3):
            failures.append("candidates: de referral-aanroep (onbekende code) ging niet uit")
        if not wait_for_text(page, '#candidateReferralAlert', "does not know a Dutch sentence"):
            failures.append(f"candidates: de onbekende 409-code viel niet terug op detail.message -- kreeg {text_of(page, '#candidateReferralAlert')!r}")

        # De drie referral-409's zijn opzettelijk en al op tekst getoetst
        # hierboven; Chromium logt elke 409-respons zelf ook als console
        # error, zoals bij de opzettelijke 500 van Bewaartermijnen.
        new_errors = [e for e in console_errors[errors_before:] if "409 (Conflict)" not in e]
        if new_errors:
            failures.append(f"candidates: {len(new_errors)} console error(s): {new_errors[:3]}")

        browser.close()

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS: Opdrachtgevers (list + tabbed drawer), Leads (inbox + unread filter + PATCH), "
          "Rapportage, Bewaartermijnen (lijst, generate, goedkeuren met getypte bevestiging, "
          "afwijzen, categoriebrede bulk met 409-mismatch, droogloop en 500 met retry) en "
          "Toestemmingen/referral (§7.3.2: talentpool- en presentatiemodal met clientside-validatie "
          "en de juiste payload per richting, plus de drie referral-409-uitkomsten) "
          "renderden allemaal correct, zonder console errors.")
    sys.exit(0)


if __name__ == "__main__":
    main()
