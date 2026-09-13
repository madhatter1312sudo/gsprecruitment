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

  - Plaatsingen (SITE-DESIGN-SPEC.md §7.3.3): de lijst (60 rijen naast de
    paginagrootte van 20) toont vertaalde labels, geen ruwe enumwaarde;
    server-side sortering op kandidaat verplaatst de enige afwijkende rij
    naar het einde (oplopend) en het begin (aflopend) van de hele
    verzameling; status-, opdrachtgever- en kandidaatfilters (het laatste
    lost eerst op naar een candidate_id: numeriek direct, een naam via de
    kandidatenlijst, met een hint bij nul of meerdere treffers); de drawer
    (Overzicht/Financieel/Marge) toont bedragen met euroteken en
    tabular-nums; statuswisseling gebruikt de gewone bevestiging behalve
    naar geannuleerd (destructief, geen getypte bevestiging); marge toont
    de waarschuwingszin letterlijk, "n.v.t. (invoer ontbreekt)" bij null,
    blokkeert een ongeldig bedrag vóór de aanroep en normaliseert een
    komma-decimaal; aanmaken valideert bedragen tegen de backendgrenzen
    (nul aanroepen bij een ongeldig bedrag) en bewerken kan de vier
    onwijzigbare FK-velden niet meesturen; verwijderen vraagt de getypte
    plaatsings-ID, toont een 409 met detail.code zonder te sluiten en
    slaagt daarna; een 500 geeft de retrylink en herstelt daarna.

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

# Letterlijk dezelfde zin als WARNING_SENTENCE in js/sections/placements.js
# (§7.3.3) -- de marge-tab moet exact deze tekst tonen, niet een parafrase.
WARNING_SENTENCE_PY = (
    "Voorlopig. Deze berekening is nog niet door de eigenaar vastgesteld en mag niet naar buiten."
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
    # client_id staat er expliciet bij (routers/admin.py:400 SELECT j.*,
    # c.company_name -- job_orders.client_id komt dus altijd mee): de
    # plaatsingensectie gebruikt dat veld om de vacaturekiezer per
    # opdrachtgever te filteren (js/sections/placements.js).
    1: [{"id": 201, "client_id": 1, "title": "Embedded Software Engineer", "employment_type": "werving_selectie",
         "status": "open", "application_count": 3, "company_name": "Example Engineering B.V."}],
    2: [{"id": 202, "client_id": 2, "title": "Mechatronica Engineer", "employment_type": "detachering",
         "status": "open", "application_count": 1, "company_name": "Example Mechatronics B.V."}],
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
# Twee kandidaten. CANDIDATE_RECORD (kind sourced, candidates.id 1482, geen
# consent bij aanvang) is genoeg om alle drie de modals tegen echte
# gestubde routes te toetsen. SELF_REG_CANDIDATE_RECORD (kind
# self-registered, users.id 501, gekoppeld aan candidates.id 1483 met al
# actieve talentpool- en presentatietoestemming) bewijst de HIGH-1-
# reparatie: GET /candidates/self-registered/501 draagt geen enkele
# consentkolom (self_reg_detail() hieronder, een letterlijke kopie van wat
# routers/admin.py:861-906 teruggeeft), dus zonder de tweede aanroep op
# kind 'sourced' met candidate_id 1483 zou de tab altijd "Geen toestemming"
# en job-alerts "Nee" tonen. De drie tabs Profiel/Matches/Activiteit hoeven
# voor dit doel alleen zonder console error te renderen, dus die leunen op
# de generieke lege-lijst-fallback onderaan route_admin_api.
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

SELF_REG_USER_ID = 501
SELF_REG_CANDIDATE_ID = 1483
SELF_REG_CANDIDATE_RECORD = {
    "id": SELF_REG_CANDIDATE_ID, "full_name": "Zelf Geregistreerd Voorbeeld", "email": "zelf@example.invalid",
    "current_title": "Mechatronica Engineer", "current_company": None, "years_experience": 3,
    "location": "Veldhoven", "source": "portal_registration", "status": "active",
    "lawful_basis": "portal_registratie",
    "consent_talentpool_at": "2026-08-01T00:00:00Z", "consent_talentpool_until": "2027-08-01T00:00:00Z",
    "consent_scope": "matching_and_contact", "consent_source": "self", "consent_withdrawn_at": None,
    "consent_spec_presentation_at": "2026-08-05T00:00:00Z", "consent_spec_presentation_job_id": 201,
    "job_alert_optin_at": "2026-08-01T00:00:00Z", "job_alert_unsubscribed_at": None,
    "created_at": "2026-08-01T00:00:00Z",
}

# Eén dict op candidates.id, gebruikt door de PATCH-routes en de
# sourced-detailroute hieronder, zodat een PATCH op de ene kandidaat de
# andere niet raakt.
CANDIDATES_BY_ID = {
    CANDIDATE_RECORD["id"]: CANDIDATE_RECORD,
    SELF_REG_CANDIDATE_ID: SELF_REG_CANDIDATE_RECORD,
}

CANDIDATE_STATE = {
    "talentpool_calls": [], "presentation_calls": [], "referral_calls": [],
    # "ok" | "suppressed" | "exists" | "unknown" -- welke uitkomst de
    # volgende POST /candidates/referral teruggeeft.
    "referral_mode": "ok",
}

# ---- Pipeline (§7.3.4) --------------------------------------------------
# Vijf entries, dezelfde rijvorm als PIPELINE_ROW_SQL/project_pipeline_rows
# (core/pipeline.py): pe.* plus full_name/current_title/current_company/
# location/skills/job_title, de consentkolommen zijn er (net als op de
# echte admin-route, gate_name=False) al uit. In array-volgorde nieuwste
# eerst, zoals de echte route ORDER BY pe.created_at DESC, pe.id DESC
# teruggeeft -- deze stub sorteert zelf niet, dus de volgorde hieronder
# IS de teruggegeven volgorde.
#   604  candidate 1482, client 1, stage 'new'            -- hoofdpad: fase
#        wijzigen zonder eerdere mislukking, historie met alle drie de
#        actor-varianten op een andere entry (603) getest.
#   603  candidate 1482, client 1, stage 'sourced-legacy'  -- fase buiten de
#        zeven canonieke waarden: bewijst de "(bestaande waarde)"-optie EN
#        dat die nooit verstuurd wordt. Historie: from_stage null EN
#        changed_by/changed_by_name allebei leeg -> "(nieuw)" / "Onbekend".
#   602  candidate 1482, client 1, stage 'screening'       -- GET history
#        geeft hier altijd 500: bewijst dat de fasewisselaar bruikbaar
#        blijft terwijl alleen de historie een foutstaat toont.
#   601  candidate 1482, client 1, stage 'placed'          -- 422 dan 500
#        dan een geslaagde PATCH (PIPELINE_STATE.stage_fail_sequence), en
#        een historie van twaalf items (> 10) voor "Toon alles".
#   600  candidate 1483, client 1, stage 'interview'       -- alleen voor de
#        klantdrawer: candidate_id verschilt van de andere vier, dus
#        showCandidateName (§7.3.4 admin.js) heeft hier iets om te tonen.
PIPELINE_ENTRIES = [
    {"id": 604, "client_id": 1, "candidate_id": 1482, "job_id": 201, "stage": "new",
     "notes": None, "created_at": "2026-09-05T00:00:00Z", "updated_at": "2026-09-05T00:00:00Z",
     "full_name": "Voorbeeld Kandidaat", "current_title": "Embedded Engineer", "current_company": None,
     "location": "Eindhoven", "skills": [], "job_title": "Embedded Software Engineer"},
    {"id": 603, "client_id": 1, "candidate_id": 1482, "job_id": 205, "stage": "sourced-legacy",
     "notes": None, "created_at": "2026-09-04T00:00:00Z", "updated_at": "2026-09-04T00:00:00Z",
     "full_name": "Voorbeeld Kandidaat", "current_title": "Embedded Engineer", "current_company": None,
     "location": "Eindhoven", "skills": [], "job_title": "Legacy Systems Engineer"},
    {"id": 602, "client_id": 1, "candidate_id": 1482, "job_id": 202, "stage": "screening",
     "notes": None, "created_at": "2026-09-03T00:00:00Z", "updated_at": "2026-09-03T00:00:00Z",
     "full_name": "Voorbeeld Kandidaat", "current_title": "Embedded Engineer", "current_company": None,
     "location": "Eindhoven", "skills": [], "job_title": "Mechatronica Engineer"},
    {"id": 601, "client_id": 1, "candidate_id": 1482, "job_id": 207, "stage": "placed",
     "notes": None, "created_at": "2026-09-02T00:00:00Z", "updated_at": "2026-09-02T00:00:00Z",
     "full_name": "Voorbeeld Kandidaat", "current_title": "Embedded Engineer", "current_company": None,
     "location": "Eindhoven", "skills": [], "job_title": "Test Engineer"},
    {"id": 600, "client_id": 1, "candidate_id": 1483, "job_id": 206, "stage": "interview",
     "notes": None, "created_at": "2026-09-01T00:00:00Z", "updated_at": "2026-09-01T00:00:00Z",
     "full_name": "Zelf Geregistreerd Voorbeeld", "current_title": "Mechatronica Engineer", "current_company": None,
     "location": "Veldhoven", "skills": [], "job_title": "Mechatronica Stagiair"},
]
PIPELINE_ENTRIES_BY_ID = {e["id"]: e for e in PIPELINE_ENTRIES}

PIPELINE_HISTORY_BY_ENTRY = {
    # De drie actor-varianten (§7.3.4): een genoemde actor, "Gebruiker
    # #<id>" wanneer changed_by_name null is maar changed_by niet, en
    # "Onbekend" wanneer allebei leeg zijn (entry 603 hieronder).
    604: [
        {"id": 1, "pipeline_entry_id": 604, "from_stage": None, "to_stage": "sourced",
         "changed_by": 12, "changed_by_name": None, "changed_at": "2026-08-28T09:05:00Z"},
        {"id": 2, "pipeline_entry_id": 604, "from_stage": "sourced", "to_stage": "new",
         "changed_by": 1, "changed_by_name": "Sanne de Wit", "changed_at": "2026-09-03T14:20:00Z"},
    ],
    603: [
        {"id": 1, "pipeline_entry_id": 603, "from_stage": None, "to_stage": "sourced-legacy",
         "changed_by": None, "changed_by_name": None, "changed_at": "2026-08-01T00:00:00Z"},
    ],
    602: [
        {"id": 1, "pipeline_entry_id": 602, "from_stage": None, "to_stage": "screening",
         "changed_by": 1, "changed_by_name": "Sections Check", "changed_at": "2026-08-01T00:00:00Z"},
    ],
    # Twaalf items (> 10): bewijst "Maximaal tien items zichtbaar, daarna
    # 'Toon alles'" zonder op een latere PATCH te hoeven wachten.
    601: [
        {"id": i, "pipeline_entry_id": 601, "from_stage": None if i == 1 else "sourced",
         "to_stage": "sourced" if i == 1 else "placed", "changed_by": 1,
         "changed_by_name": f"Actor {i}", "changed_at": f"2026-08-{i:02d}T00:00:00Z"}
        for i in range(1, 13)
    ],
    600: [
        {"id": 1, "pipeline_entry_id": 600, "from_stage": None, "to_stage": "interview",
         "changed_by": 1, "changed_by_name": "Sections Check", "changed_at": "2026-08-01T00:00:00Z"},
    ],
}

PIPELINE_STATE = {
    "stage_calls": [],
    # Per entry_id een lijst geplande uitkomsten die de volgende PATCH-
    # aanroep(en) op die entry moet(en) teruggeven, in volgorde
    # weggehaald; leeg (of geen sleutel) betekent gewoon slagen.
    "stage_fail_sequence": {601: ["422", "500"]},
    # Entry-id's waarvan GET history altijd 500 teruggeeft.
    "history_error_entry_ids": {602},
}

# ---- Plaatsingen (§7.3.3) -----------------------------------------------
# Vier vaste plaatsingen met verschillende doelen: #1 (concept, volledig
# gevuld) voor de drawer/financieel/marge-weergave en een statuswissel naar
# 'actief'; #2 (actief) voor de destructieve annuleer-overgang; #3
# (beeindigd, alle geldvelden None) voor de "geen overgang meer mogelijk"-
# tekst en de "n.v.t. (invoer ontbreekt)"-marge; #4 (concept) puur om
# verwijderd te worden. Plus 56 extra rijen (in totaal 60, naast de
# paginagrootte van 20) om paginering en server-side sortering te bewijzen.
PLACEMENT_1 = {
    "id": 1, "candidate_id": 1482, "job_id": 201, "client_id": 1,
    "placement_type": "detachering", "start_date": "2026-10-01", "end_date": None,
    "hourly_bill_rate": "95.50", "monthly_purchase_price": None,
    "eor_partner": "Acme EOR", "eor_cost_factor": "1.3500",
    "billing_basis": "per_uur", "expected_billable_hours": "160.00",
    "fee_type": None, "fee_percentage": None, "fee_amount": None,
    "one_off_costs": [{"label": "Onboarding", "amount": "500.00"}],
    "status": "concept", "notes": "Eerste maand ingepland.",
}
PLACEMENT_2 = {
    "id": 2, "candidate_id": 1482, "job_id": 201, "client_id": 1,
    "placement_type": "werving_selectie", "start_date": "2026-06-01", "end_date": None,
    "hourly_bill_rate": None, "monthly_purchase_price": None,
    "eor_partner": None, "eor_cost_factor": None,
    "billing_basis": None, "expected_billable_hours": None,
    "fee_type": "percentage", "fee_percentage": "20.00", "fee_amount": None,
    "one_off_costs": [], "status": "actief", "notes": None,
}
PLACEMENT_3 = {
    "id": 3, "candidate_id": 1483, "job_id": 202, "client_id": 2,
    "placement_type": "werving_selectie", "start_date": "2026-01-15", "end_date": "2026-03-01",
    "hourly_bill_rate": None, "monthly_purchase_price": None,
    "eor_partner": None, "eor_cost_factor": None,
    "billing_basis": None, "expected_billable_hours": None,
    "fee_type": None, "fee_percentage": None, "fee_amount": None,
    "one_off_costs": [], "status": "beeindigd", "notes": None,
}
PLACEMENT_4 = {
    "id": 4, "candidate_id": 1482, "job_id": 201, "client_id": 1,
    "placement_type": "detachering", "start_date": "2026-11-01", "end_date": None,
    "hourly_bill_rate": "80.00", "monthly_purchase_price": None,
    "eor_partner": None, "eor_cost_factor": None,
    "billing_basis": "per_uur", "expected_billable_hours": "80.00",
    "fee_type": None, "fee_percentage": None, "fee_amount": None,
    "one_off_costs": [], "status": "concept", "notes": None,
}
PLACEMENTS_EXTRA_COUNT = 56
PLACEMENTS = [PLACEMENT_1, PLACEMENT_2, PLACEMENT_3, PLACEMENT_4] + [
    {
        "id": 100 + i, "candidate_id": 1482, "job_id": 201, "client_id": 1,
        "placement_type": "detachering" if i % 2 == 0 else "werving_selectie",
        "start_date": f"2026-01-{(i % 27) + 1:02d}", "end_date": None,
        "hourly_bill_rate": None, "monthly_purchase_price": None,
        "eor_partner": None, "eor_cost_factor": None,
        "billing_basis": None, "expected_billable_hours": None,
        "fee_type": None, "fee_percentage": None, "fee_amount": None,
        "one_off_costs": [], "status": "concept", "notes": None,
    }
    for i in range(PLACEMENTS_EXTRA_COUNT)
]
PLACEMENTS_BY_ID = {p["id"]: p for p in PLACEMENTS}

PLACEMENTS_STATE = {
    "mode": "ok",  # "ok" | "error" (500 op de lijst)
    "creates": [], "updates": [], "status_calls": [], "deletes": [],
    "margin_calls": [],
    # Eén geforceerde 409 met een gestructureerde detail (code + message),
    # om de generieke Admin.errorDetail()-vertakking te bewijzen ook al
    # geeft de echte routers/placements.py voor DELETE zelf geen
    # gestructureerde detail terug (alleen 404 met een platte string).
    "delete_conflict_once": True,
}


def candidate_roster_item():
    r = CANDIDATE_RECORD
    return {
        "kind": "sourced", "id": r["id"], "candidate_id": None, "user_id": None,
        "full_name": r["full_name"], "email": r["email"], "current_title": r["current_title"],
        "years_experience": r["years_experience"], "match_count": 0, "placement_count": 0,
        "source": r["source"], "status": r["status"], "is_verified": True,
    }


def self_registered_roster_item():
    r = SELF_REG_CANDIDATE_RECORD
    return {
        "kind": "self-registered", "id": SELF_REG_USER_ID, "candidate_id": SELF_REG_CANDIDATE_ID,
        "user_id": SELF_REG_USER_ID, "full_name": r["full_name"], "email": r["email"],
        "current_title": r["current_title"], "years_experience": r["years_experience"],
        "match_count": 0, "placement_count": 0, "source": r["source"], "status": r["status"],
        "is_verified": True,
    }


def build_candidate_detail(record):
    """GET /candidates/sourced/{id}: SELECT c.* plus wat de route er zelf
    bijzet. Dit is de ENIGE respons die consentvelden draagt, voor beide
    kandidaten (admin.py:813-859)."""
    d = dict(record)
    d["skills"] = []
    d["languages"] = []
    d["tags"] = []
    d["match_count"] = 0
    d["placement_count"] = 0
    d["kind"] = "sourced"
    d["user_id"] = None
    d["is_verified"] = None
    return d


def self_reg_detail():
    """GET /candidates/self-registered/501: routers/admin.py:861-906.
    Draagt full_name/email/candidate_id, maar bewust GEEN enkele
    consent_*/job_alert_*-kolom -- dat is precies de HIGH-1-bug die
    resolveConsentDetail() in candidates.js moet omzeilen."""
    r = SELF_REG_CANDIDATE_RECORD
    return {
        "id": SELF_REG_USER_ID, "email": r["email"], "full_name": r["full_name"],
        "role": "candidate", "is_verified": True, "created_at": r["created_at"], "updated_at": None,
        "profile": {
            "phone": None, "current_title": r["current_title"], "current_company": None,
            "location": r["location"], "skills": [], "languages": [],
            "years_experience": r["years_experience"], "cv_file_path": None,
        },
        "kind": "self-registered", "candidate_id": SELF_REG_CANDIDATE_ID,
        "candidate_status": r["status"], "candidate_source": r["source"], "match_count": 0,
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
        json_response({"items": [candidate_roster_item(), self_registered_roster_item()], "total": 2})
        return
    m = re.match(r"^/api/v1/admin/candidates/sourced/(\d+)$", path)
    if m and method == "GET":
        record = CANDIDATES_BY_ID.get(int(m.group(1)))
        if record is None:
            json_response({"detail": "Not found"}, status=404)
        else:
            json_response(build_candidate_detail(record))
        return
    m = re.match(r"^/api/v1/admin/candidates/self-registered/(\d+)$", path)
    if m and method == "GET":
        if int(m.group(1)) == SELF_REG_USER_ID:
            json_response(self_reg_detail())
        else:
            json_response({"detail": "Not found"}, status=404)
        return
    m = re.match(r"^/api/v1/admin/candidates/(\d+)/talentpool-consent$", path)
    if m and method == "PATCH":
        record = CANDIDATES_BY_ID.get(int(m.group(1)))
        if record is None:
            json_response({"detail": "Candidate not found"}, status=404)
            return
        body = json.loads(request.post_data or "{}")
        CANDIDATE_STATE["talentpool_calls"].append(body)
        if body.get("consent"):
            # admin.py:934-948 -- de vastleg-tak raakt consent_withdrawn_at
            # nooit, ook niet als die al gezet was door een eerdere
            # intrekking (MEDIUM-2-test hieronder: eenmaal ingetrokken
            # blijft dat na een nieuwe vastlegging op de backend staan).
            record.update({
                "consent_talentpool_at": "2026-09-03T00:00:00Z",
                "consent_talentpool_until": "2027-09-03T00:00:00Z",
                "consent_scope": body.get("scope"),
                "consent_source": "admin",
            })
        else:
            record.update({
                "consent_talentpool_at": None, "consent_talentpool_until": None,
                "consent_scope": None, "consent_source": None,
                "consent_withdrawn_at": "2026-09-04T00:00:00Z",
            })
        # De RETURNING-kolommen van de echte route (admin.py:945-946 en
        # 962-963) dragen consent_withdrawn_at nooit mee -- dat is precies
        # de MEDIUM-2-bug die dit scherm dwingt tot een verse GET in plaats
        # van deze respons te vertrouwen voor de kaart.
        json_response({
            "id": record["id"],
            "consent_talentpool_at": record["consent_talentpool_at"],
            "consent_talentpool_until": record["consent_talentpool_until"],
            "consent_scope": record["consent_scope"],
            "consent_source": record["consent_source"],
            "lawful_basis": record["lawful_basis"],
        })
        return
    m = re.match(r"^/api/v1/admin/candidates/(\d+)/spec-presentation-consent$", path)
    if m and method == "PATCH":
        record = CANDIDATES_BY_ID.get(int(m.group(1)))
        if record is None:
            json_response({"detail": "Candidate not found"}, status=404)
            return
        body = json.loads(request.post_data or "{}")
        CANDIDATE_STATE["presentation_calls"].append(body)
        if body.get("consent"):
            record.update({
                "consent_spec_presentation_at": "2026-09-05T00:00:00Z",
                "consent_spec_presentation_job_id": body.get("job_id"),
            })
        else:
            record.update({
                "consent_spec_presentation_at": None, "consent_spec_presentation_job_id": None,
            })
        json_response({
            "id": record["id"],
            "consent_spec_presentation_at": record["consent_spec_presentation_at"],
            "consent_spec_presentation_job_id": record["consent_spec_presentation_job_id"],
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

    # ---- Pipeline (§7.3.4, tab Pipeline in kandidaat- en klantdrawer) ----
    if path == "/api/v1/admin/pipeline" and method == "GET":
        candidate_id = qs.get("candidate_id", [None])[0]
        client_id = qs.get("client_id", [None])[0]
        rows = PIPELINE_ENTRIES
        if candidate_id is not None:
            rows = [r for r in rows if r["candidate_id"] == int(candidate_id)]
        if client_id is not None:
            rows = [r for r in rows if r["client_id"] == int(client_id)]
        json_response({"items": rows, "total": len(rows), "limit": qint(qs, "limit", 50), "offset": 0})
        return
    m = re.match(r"^/api/v1/admin/pipeline/(\d+)/stage$", path)
    if m and method == "PATCH":
        entry_id = int(m.group(1))
        entry = PIPELINE_ENTRIES_BY_ID.get(entry_id)
        if entry is None:
            json_response({"detail": "Pipeline entry not found"}, status=404)
            return
        body = json.loads(request.post_data or "{}")
        PIPELINE_STATE["stage_calls"].append({"entry_id": entry_id, "body": body})
        # Eerst de geplande mislukkingen voor deze entry (422, dan 500),
        # deterministisch en zonder volgorde-afhankelijkheid: elke
        # aanroep pop't de volgende uitkomst van de lijst, en zodra die
        # leeg is slaagt de aanroep gewoon.
        sequence = PIPELINE_STATE["stage_fail_sequence"].get(entry_id)
        if sequence:
            outcome = sequence.pop(0)
            if outcome == "422":
                json_response({"detail": {"code": "pipeline_stage_invalid",
                                           "message": "Deze fase is ongeldig."}}, status=422)
                return
            if outcome == "500":
                json_response({"detail": "Internal server error"}, status=500)
                return
        from_stage = entry["stage"]
        new_stage = body.get("stage")
        entry["stage"] = new_stage
        if from_stage != new_stage:
            history = PIPELINE_HISTORY_BY_ENTRY.setdefault(entry_id, [])
            history.append({
                "id": max([h["id"] for h in history], default=0) + 1,
                "pipeline_entry_id": entry_id, "from_stage": from_stage, "to_stage": new_stage,
                # De admin die is ingelogd in deze testrun (zie user hieronder
                # in main()): id 1, full_name "Sections Check".
                "changed_by": 1, "changed_by_name": "Sections Check",
                "changed_at": "2026-09-10T12:00:00Z",
            })
        json_response(entry)
        return
    m = re.match(r"^/api/v1/admin/pipeline/(\d+)/history$", path)
    if m and method == "GET":
        entry_id = int(m.group(1))
        if entry_id not in PIPELINE_ENTRIES_BY_ID:
            json_response({"detail": "Pipeline entry not found"}, status=404)
            return
        if entry_id in PIPELINE_STATE["history_error_entry_ids"]:
            json_response({"detail": "Internal server error"}, status=500)
            return
        items = PIPELINE_HISTORY_BY_ENTRY.get(entry_id, [])
        json_response({"items": items, "total": len(items)})
        return

    # ---- Plaatsingen (§7.3.3) ----
    if path == "/api/v1/admin/placements" and method == "GET":
        if PLACEMENTS_STATE["mode"] == "error":
            json_response({"detail": "Server error"}, status=500)
            return
        rows = [p for p in PLACEMENTS if p["id"] not in PLACEMENTS_STATE.get("deleted_ids", set())]
        status = qs.get("status", [None])[0]
        candidate_id = qs.get("candidate_id", [None])[0]
        job_id = qs.get("job_id", [None])[0]
        client_id = qs.get("client_id", [None])[0]
        if status:
            rows = [p for p in rows if p["status"] == status]
        if candidate_id is not None:
            rows = [p for p in rows if str(p["candidate_id"]) == str(candidate_id)]
        if job_id is not None:
            rows = [p for p in rows if str(p["job_id"]) == str(job_id)]
        if client_id is not None:
            rows = [p for p in rows if str(p["client_id"]) == str(client_id)]
        sort = qs.get("sort", [None])[0]
        if sort:
            order = qs.get("order", ["asc"])[0]
            rows = sorted(rows, key=lambda r: (r.get(sort) is None, r.get(sort)), reverse=(order == "desc"))
        total = len(rows)
        limit = qint(qs, "limit", 20)
        offset = qint(qs, "offset", 0)
        json_response({"items": rows[offset:offset + limit], "total": total})
        return
    if path == "/api/v1/admin/placements" and method == "POST":
        body = json.loads(request.post_data or "{}")
        PLACEMENTS_STATE["creates"].append(body)
        new_id = max(PLACEMENTS_BY_ID.keys()) + 1
        row = {
            "id": new_id, "candidate_id": body.get("candidate_id"), "job_id": body.get("job_id"),
            "client_id": body.get("client_id"), "placement_type": body.get("placement_type"),
            "start_date": body.get("start_date"), "end_date": body.get("end_date"),
            "hourly_bill_rate": body.get("hourly_bill_rate"), "monthly_purchase_price": body.get("monthly_purchase_price"),
            "eor_partner": body.get("eor_partner"), "eor_cost_factor": body.get("eor_cost_factor"),
            "billing_basis": body.get("billing_basis"), "expected_billable_hours": body.get("expected_billable_hours"),
            "fee_type": body.get("fee_type"), "fee_percentage": body.get("fee_percentage"),
            "fee_amount": body.get("fee_amount"), "one_off_costs": body.get("one_off_costs") or [],
            "status": "concept", "notes": body.get("notes"),
        }
        PLACEMENTS.append(row)
        PLACEMENTS_BY_ID[new_id] = row
        json_response(row, status=201)
        return
    m = re.match(r"^/api/v1/admin/placements/(\d+)/margin$", path)
    if m and method == "GET":
        p = PLACEMENTS_BY_ID.get(int(m.group(1)))
        if not p:
            json_response({"detail": "Placement not found"}, status=404)
            return
        gross = qs.get("gross_monthly_salary", [None])[0]
        annual = qs.get("annual_salary", [None])[0]
        PLACEMENTS_STATE["margin_calls"].append({"id": p["id"], "gross_monthly_salary": gross, "annual_salary": annual})
        json_response(compute_stub_margin(p, gross, annual))
        return
    m = re.match(r"^/api/v1/admin/placements/(\d+)/status$", path)
    if m and method == "POST":
        pid = int(m.group(1))
        p = PLACEMENTS_BY_ID.get(pid)
        if not p:
            json_response({"detail": "Placement not found"}, status=404)
            return
        body = json.loads(request.post_data or "{}")
        PLACEMENTS_STATE["status_calls"].append({"id": pid, "body": body})
        new_status = body.get("status")
        # Zelfde graaf als _ALLOWED_TRANSITIONS in routers/placements.py.
        allowed = {"concept": {"actief", "geannuleerd"}, "actief": {"beeindigd", "geannuleerd"},
                   "beeindigd": set(), "geannuleerd": set()}
        if new_status not in allowed.get(p["status"], set()):
            json_response({"detail": f"Invalid status transition: {p['status']} -> {new_status}."}, status=422)
            return
        p["status"] = new_status
        json_response(p)
        return
    m = re.match(r"^/api/v1/admin/placements/(\d+)$", path)
    if m and method == "GET":
        pid = int(m.group(1))
        p = PLACEMENTS_BY_ID.get(pid)
        if not p or pid in PLACEMENTS_STATE.get("deleted_ids", set()):
            json_response({"detail": "Placement not found"}, status=404)
            return
        json_response(p)
        return
    if m and method == "PATCH":
        pid = int(m.group(1))
        p = PLACEMENTS_BY_ID.get(pid)
        if not p:
            json_response({"detail": "Placement not found"}, status=404)
            return
        body = json.loads(request.post_data or "{}")
        PLACEMENTS_STATE["updates"].append({"id": pid, "body": body})
        p.update(body)
        json_response(p)
        return
    if m and method == "DELETE":
        pid = int(m.group(1))
        p = PLACEMENTS_BY_ID.get(pid)
        if not p:
            json_response({"detail": "Placement not found"}, status=404)
            return
        PLACEMENTS_STATE["deletes"].append(pid)
        # Eén geforceerde 409 met een gestructureerde detail (code +
        # message), voor plaatsing #4: bewijst dat het scherm
        # Admin.errorDetail() gebruikt (§7.2f) in plaats van op de
        # letterlijke tekst te vertakken, ook al geeft de echte
        # routers/placements.py voor DELETE zelf alleen 404 met een platte
        # string terug.
        if pid == 4 and PLACEMENTS_STATE["delete_conflict_once"]:
            PLACEMENTS_STATE["delete_conflict_once"] = False
            json_response({"detail": {"code": "placement_delete_conflict",
                                       "message": "Deze plaatsing kan op dit moment niet verwijderd worden."}}, status=409)
            return
        PLACEMENTS_STATE.setdefault("deleted_ids", set()).add(pid)
        route.fulfill(status=204, content_type="application/json", body="")
        return

    json_response({"items": [], "total": 0})


def compute_stub_margin(p, gross, annual):
    """Zelfde twee formules als core/margin.compute_margin(), met gewone
    floats in plaats van Decimal -- precies genoeg voor deze stub, en
    zonder de precisievoetangels waar de test toch niet op let."""
    def dec(v):
        return float(v) if v not in (None, "") else None
    hourly = dec(p.get("hourly_bill_rate"))
    hours = dec(p.get("expected_billable_hours"))
    monthly_price = dec(p.get("monthly_purchase_price"))
    eor_factor = dec(p.get("eor_cost_factor"))
    gross_v = dec(gross)
    annual_v = dec(annual)
    fee_type = p.get("fee_type")
    fee_pct = dec(p.get("fee_percentage"))
    fee_amt = dec(p.get("fee_amount"))
    result = {
        "provisional": True, "placement_type": p.get("placement_type"),
        "inputs": {
            "billing_basis": p.get("billing_basis"), "hourly_bill_rate": hourly,
            "expected_billable_hours": hours, "monthly_purchase_price": monthly_price,
            "eor_cost_factor": eor_factor, "gross_monthly_salary": gross_v,
            "annual_salary": annual_v, "fee_type": fee_type,
            "fee_percentage": fee_pct, "fee_amount": fee_amt,
        },
        "revenue": None, "cost": None, "margin": None, "margin_pct": None, "fee": None,
    }
    if p.get("placement_type") == "detachering":
        revenue = None
        if p.get("billing_basis") == "per_uur":
            if hourly is not None and hours is not None:
                revenue = hourly * hours
        else:
            revenue = hourly
        cost = monthly_price
        if cost is None and gross_v is not None and eor_factor is not None:
            cost = gross_v * eor_factor
        margin = None
        margin_pct = None
        if revenue is not None and cost is not None:
            margin = revenue - cost
            if revenue:
                margin_pct = (margin / revenue) * 100
        result.update({
            "revenue": round(revenue, 2) if revenue is not None else None,
            "cost": round(cost, 2) if cost is not None else None,
            "margin": round(margin, 2) if margin is not None else None,
            "margin_pct": round(margin_pct, 2) if margin_pct is not None else None,
        })
    elif p.get("placement_type") == "werving_selectie":
        fee = None
        if fee_type == "vast":
            fee = fee_amt
        elif fee_type == "percentage" and fee_pct is not None and annual_v is not None:
            fee = (fee_pct / 100) * annual_v
        result.update({
            "fee": round(fee, 2) if fee is not None else None,
            "revenue": round(fee, 2) if fee is not None else None,
            "margin": round(fee, 2) if fee is not None else None,
        })
    return result


def click_or_fail(page, failures, selector, what, timeout=6000):
    """Klikken zonder dat een ontbrekend of onklikbaar element de hele run
    in een traceback of een 30s-standaardtimeout laat eindigen: dan mist
    niet alleen deze assertie maar ook alles wat erna komt, en een
    mutatietest die zoiets veroorzaakt wordt pas na een halve minuut rood
    in plaats van meteen. Een gemiste of onklikbare knop hoort in de
    failure-lijst, net als de pagineerknop dat al deed. Geen "retention:"-
    prefix meer: deze helper wordt inmiddels door meerdere secties
    gebruikt, en `what` draagt zijn eigen context al."""
    if page.query_selector(selector) is None:
        failures.append(f"{what} niet gevonden ({selector})")
        return False
    try:
        page.click(selector, timeout=timeout)
    except Exception as exc:
        failures.append(f"{what}: klikken op {selector} lukte niet binnen {timeout}ms ({exc})")
        return False
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


def fill_or_fail(page, failures, selector, value, what, timeout=6000):
    if page.query_selector(selector) is None:
        failures.append(f"{what} niet gevonden ({selector})")
        return False
    try:
        page.fill(selector, value, timeout=timeout)
    except Exception as exc:
        failures.append(f"{what}: invullen van {selector} lukte niet binnen {timeout}ms ({exc})")
        return False
    return True


def select_or_fail(page, failures, selector, value, what, timeout=6000):
    """code-reviewer op 2e47403: een kale page.select_option hangt de volle
    30s als een mutant de modal voortijdig sluit, en de FAIL-regel die
    zou zeggen welke stap dat was verdwijnt dan in een traceback in
    plaats van in de failure-lijst te staan."""
    if page.query_selector(selector) is None:
        failures.append(f"{what} niet gevonden ({selector})")
        return False
    try:
        page.select_option(selector, value, timeout=timeout)
    except Exception as exc:
        failures.append(f"{what}: selecteren in {selector} lukte niet binnen {timeout}ms ({exc})")
        return False
    return True


def check_or_fail(page, failures, selector, what, timeout=6000):
    """Zelfde reden als select_or_fail hierboven, voor page.check()."""
    if page.query_selector(selector) is None:
        failures.append(f"{what} niet gevonden ({selector})")
        return False
    try:
        page.check(selector, timeout=timeout)
    except Exception as exc:
        failures.append(f"{what}: aanvinken van {selector} lukte niet binnen {timeout}ms ({exc})")
        return False
    return True


def element_from_point_is_self(page, selector):
    """design-reviewer op ece9d6d: bewijst dat een sticky voettekst niet
    over `selector` heen ligt. True wanneer het midden van het element
    zichzelf teruggeeft via document.elementFromPoint; false wanneer iets
    ervoor ligt (klik-hijack -- typisch de voettekst zelf)."""
    return bool(page.eval_on_selector(selector,
        "el => { const r = el.getBoundingClientRect(); "
        "const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); "
        "return hit === el; }"))


def fields_behind_sticky_footer(page, container_selector):
    """design-reviewer op ece9d6d: na scrollen naar onder mag geen enkel
    formulierveld in `container_selector` binnen de band van zijn eigen
    .a-sticky-footer liggen. Geeft de id's (of tagnamen) van de rest-
    gevallen terug; een lege lijst is de geslaagde staat."""
    return page.eval_on_selector(container_selector,
        "el => { const footer = el.querySelector('.a-sticky-footer'); "
        "if (!footer) return []; "
        "const fr = footer.getBoundingClientRect(); "
        "const fields = [...el.querySelectorAll('input, select, textarea, button')] "
        "  .filter(f => !footer.contains(f)); "
        "return fields.filter(f => { const r = f.getBoundingClientRect(); "
        "  return r.width > 0 && r.height > 0 && !(r.bottom <= fr.top || r.top >= fr.bottom); }) "
        "  .map(f => f.id || f.tagName); }") or []


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

            # ---- Tab Pipeline (§7.3.4): client_id=1 levert vijf entries
            # (604/603/602/601/600) -- accordeon, alleen de nieuwste open,
            # en showCandidateName=true zet de kandidaatnaam in de kop
            # zodat een client met meerdere kandidaten ze uit elkaar kan
            # houden (de kandidaatdrawer laat die naam juist weg). ----
            click_or_fail(page, failures, '[data-action="client-tab"][data-tab="pipeline"]', "clients: de tab Pipeline")
            if not wait_until(page, lambda: page.query_selector('#pipelineStage_604') is not None):
                failures.append("clients: de tab Pipeline rendeerde niet (entry 604)")
            details_ids = page.eval_on_selector_all(
                '#clientDrawerTabContent details.a-disclosure', "els => els.map(e => e.id)")
            if details_ids != ["pipelineEntry_604", "pipelineEntry_603", "pipelineEntry_602",
                                "pipelineEntry_601", "pipelineEntry_600"]:
                failures.append(f"clients: pipeline-accordeon toont niet de verwachte vijf entries in volgorde -- kreeg {details_ids!r}")
            open_ids = page.eval_on_selector_all(
                '#clientDrawerTabContent details.a-disclosure[open]', "els => els.map(e => e.id)")
            if open_ids != ["pipelineEntry_604"]:
                failures.append(f"clients: alleen de nieuwste entry hoort opengeklapt te zijn -- kreeg {open_ids!r}")
            summaries_text = page.eval_on_selector_all(
                '#clientDrawerTabContent details.a-disclosure summary', "els => els.map(e => e.textContent)")
            if not any("Voorbeeld Kandidaat" in t for t in summaries_text):
                failures.append(f"clients: pipeline-kaarten tonen niet de kandidaatnaam -- kreeg {summaries_text!r}")
            if not any("Zelf Geregistreerd Voorbeeld" in t for t in summaries_text):
                failures.append(f"clients: pipeline-kaarten tonen niet de afwijkende tweede kandidaatnaam (entry 600) -- kreeg {summaries_text!r}")

        page.click('#clientDrawer [data-action="close-modal"]')
        page.wait_for_timeout(300)
        # De tab Pipeline haalt ook de historie van entry 602 op, die
        # opzettelijk altijd 500 teruggeeft (§7.3.4-test); Chromium logt
        # dat zelf ook als console error, zoals elders in deze suite.
        new_errors = [e for e in console_errors[errors_before:] if "500 (Internal Server Error)" not in e]
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
                      "candidates: de bekijkknop van de kandidaatrij")
        if not wait_until(page, lambda: page.query_selector('#candidateDrawerTabContent') is not None):
            failures.append("candidates: de kandidaatdrawer ging niet open")
        # code-reviewer op b9d5b21: de drawerkop moet de echte naam tonen
        # zodra het profieldetail geladen is, niet alleen "Kandidaat".
        if not wait_for_text(page, '#candidateDrawer__title', CANDIDATE_RECORD["full_name"]):
            failures.append(f"candidates: de drawerkop toont niet de echte naam -- kreeg {text_of(page, '#candidateDrawer__title')!r}")

        # ---- Tab Pipeline (§7.3.4), vervangt Matches ----
        click_or_fail(page, failures, '#candidateDrawer [data-tab="pipeline"]', "candidates: de tab Pipeline")
        if not wait_until(page, lambda: page.query_selector('#pipelineStage_604') is not None):
            failures.append("candidates: de tab Pipeline rendeerde niet (entry 604)")

        # Vier entries voor candidate_id 1482 (604/603/602/601) -> accordeon,
        # alleen de nieuwste (604, eerst in de API-volgorde) opengeklapt.
        details_ids = page.eval_on_selector_all(
            '#candidateDrawerTabContent details.a-disclosure', "els => els.map(e => e.id)")
        if details_ids != ["pipelineEntry_604", "pipelineEntry_603", "pipelineEntry_602", "pipelineEntry_601"]:
            failures.append(f"candidates: pipeline-accordeon toont niet de verwachte vier entries in volgorde -- kreeg {details_ids!r}")
        open_ids = page.eval_on_selector_all(
            '#candidateDrawerTabContent details.a-disclosure[open]', "els => els.map(e => e.id)")
        if open_ids != ["pipelineEntry_604"]:
            failures.append(f"candidates: alleen de nieuwste entry hoort opengeklapt te zijn -- kreeg {open_ids!r}")

        # Select met precies de zeven canonieke fasen, in spec-volgorde,
        # Nederlandse labels, huidige fase (new) geselecteerd.
        options = page.eval_on_selector_all(
            '#pipelineStage_604 option', "els => els.map(e => ({value: e.value, text: e.textContent, selected: e.selected}))")
        expected_stages = [
            ("sourced", "Gesourced"), ("new", "Nieuw"), ("screening", "Screening"),
            ("interview", "Gesprek"), ("offer", "Aanbod"), ("placed", "Geplaatst"), ("rejected", "Afgewezen"),
        ]
        if [(o["value"], o["text"]) for o in options] != expected_stages:
            failures.append(f"candidates: select #pipelineStage_604 heeft niet precies de zeven fasen in spec-volgorde -- kreeg {options!r}")
        elif not any(o["value"] == "new" and o["selected"] for o in options):
            failures.append(f"candidates: select #pipelineStage_604 stond niet op de huidige fase 'new' -- kreeg {options!r}")

        # Historie van 604: "(nieuw) -> Gesourced" / "Gebruiker #12", dan
        # "Gesourced -> Nieuw" / "Sanne de Wit" -- de eerste twee van de
        # drie actor-varianten, en de rechterpijl (geen streepje).
        if not wait_for_text(page, '#pipelineHistoryWrap_604', "Sanne de Wit"):
            failures.append(f"candidates: historie van entry 604 toont niet de genoemde actor -- kreeg {text_of(page, '#pipelineHistoryWrap_604')!r}")
        hist_604 = text_of(page, '#pipelineHistoryWrap_604')
        if "(nieuw) → Gesourced" not in hist_604 or "Gebruiker #12" not in hist_604:
            failures.append(f"candidates: historie van entry 604 mist '(nieuw) → Gesourced' / 'Gebruiker #12' -- kreeg {hist_604!r}")
        if "Gesourced → Nieuw" not in hist_604:
            failures.append(f"candidates: historie van entry 604 mist 'Gesourced → Nieuw' (rechterpijl) -- kreeg {hist_604!r}")
        if "Laatst gewijzigd" not in hist_604 or "Sanne de Wit" not in hist_604:
            failures.append(f"candidates: 'Laatst gewijzigd' toont niet de laatste actor -- kreeg {hist_604!r}")

        # Fase wijzigen (604, hoofdpad): één PATCH met de juiste payload,
        # geen automatische opslag vóór de klik, na succes herlaadt alleen
        # de historie (niet lokaal aangevuld).
        stage_calls_before = len(PIPELINE_STATE["stage_calls"])
        select_or_fail(page, failures, '#pipelineStage_604', 'screening', "candidates: fase kiezen (entry 604)")
        if len(PIPELINE_STATE["stage_calls"]) != stage_calls_before:
            failures.append("candidates: het wisselen van de select alleen stuurde al een PATCH (geen automatische opslag verwacht)")
        click_or_fail(page, failures, '[data-action="pipeline-change-stage"][data-entry-id="604"]', "candidates: Fase wijzigen (entry 604)")
        if not wait_for_calls(page, PIPELINE_STATE["stage_calls"], stage_calls_before + 1):
            failures.append("candidates: Fase wijzigen (604) stuurde geen PATCH")
        elif PIPELINE_STATE["stage_calls"][-1] != {"entry_id": 604, "body": {"stage": "screening"}}:
            failures.append(f"candidates: PATCH-payload voor entry 604 klopt niet -- kreeg {PIPELINE_STATE['stage_calls'][-1]!r}")
        if not wait_for_text(page, '#pipelineHistoryWrap_604', "Sections Check"):
            failures.append("candidates: historie van 604 herlaadde niet na een geslaagde fasewijziging")
        toast_texts = page.eval_on_selector_all(".toast-container .toast span:last-child", "els => els.map(e => e.textContent)")
        if not any("Fase bijgewerkt" in t for t in toast_texts):
            failures.append(f"candidates: geen toast na een geslaagde fasewijziging -- kreeg {toast_texts!r}")

        # Ontsnappingsklep (603): fase buiten de zeven verschijnt als
        # geselecteerde, achtste optie met "(bestaande waarde)", en wordt
        # nooit verstuurd, ook niet bij een klik zonder eerst iets anders
        # te kiezen.
        click_or_fail(page, failures, '#pipelineEntry_603 summary', "candidates: entry 603 openklappen")
        if not wait_until(page, lambda: page.query_selector('#pipelineStage_603') is not None):
            failures.append("candidates: entry 603 klapte niet open")
        opts_603 = page.eval_on_selector_all(
            '#pipelineStage_603 option', "els => els.map(e => ({value: e.value, text: e.textContent, selected: e.selected}))")
        if len(opts_603) != 8:
            failures.append(f"candidates: select #pipelineStage_603 heeft geen acht opties (zeven plus ontsnappingsklep) -- kreeg {opts_603!r}")
        escape_opt = next((o for o in opts_603 if o["value"] == "sourced-legacy"), None)
        if not escape_opt or "(bestaande waarde)" not in escape_opt["text"] or not escape_opt["selected"]:
            failures.append(f"candidates: de ontsnappingsklep-optie ontbreekt, is niet geselecteerd, of mist het achtervoegsel -- kreeg {opts_603!r}")
        calls_603_before = len(PIPELINE_STATE["stage_calls"])
        click_or_fail(page, failures, '[data-action="pipeline-change-stage"][data-entry-id="603"]', "candidates: Fase wijzigen (entry 603, ontsnappingsklep)")
        page.wait_for_timeout(300)
        if len(PIPELINE_STATE["stage_calls"]) != calls_603_before:
            failures.append("candidates: de ontsnappingsklep-waarde 'sourced-legacy' werd toch verstuurd")
        if not wait_until(page, lambda: "Kies een van de zeven fasen" in text_of(page, '#pipelineEntryAlert_603')):
            failures.append(f"candidates: geen inline-melding bij een poging de ontsnappingsklep-waarde op te slaan -- kreeg {text_of(page, '#pipelineEntryAlert_603')!r}")
        hist_603 = text_of(page, '#pipelineHistoryWrap_603')
        if "(nieuw)" not in hist_603 or "sourced-legacy" not in hist_603 or "Onbekend" not in hist_603:
            failures.append(f"candidates: historie van entry 603 mist '(nieuw)'/ruwe waarde/'Onbekend' -- kreeg {hist_603!r}")

        # Historiefout (602): de fasewisselaar blijft bruikbaar.
        click_or_fail(page, failures, '#pipelineEntry_602 summary', "candidates: entry 602 openklappen")
        if not wait_until(page, lambda: "probeer opnieuw" in text_of(page, '#pipelineHistoryWrap_602').lower()):
            failures.append(f"candidates: historiefout (602) toonde geen foutstaat -- kreeg {text_of(page, '#pipelineHistoryWrap_602')!r}")
        if is_disabled(page, '#pipelineStage_602', default=True):
            failures.append("candidates: de fasewisselaar van entry 602 is uitgeschakeld door een historiefout")
        if is_disabled(page, '[data-action="pipeline-change-stage"][data-entry-id="602"]', default=True):
            failures.append("candidates: de knop Fase wijzigen van entry 602 is uitgeschakeld door een historiefout")

        # 422 dan 500 dan geslaagd (601), en meer dan tien historie-items
        # met "Toon alles".
        click_or_fail(page, failures, '#pipelineEntry_601 summary', "candidates: entry 601 openklappen")
        if not wait_until(page, lambda: page.query_selector('[data-action="pipeline-history-show-all"][data-entry-id="601"]') is not None):
            failures.append("candidates: entry 601 toonde geen 'Toon alles' bij twaalf historie-items")
        visible_before = page.eval_on_selector_all('#pipelineHistoryWrap_601 .a-timeline__item', "els => els.length")
        if visible_before != 10:
            failures.append(f"candidates: entry 601 toont niet precies tien items vóór 'Toon alles' -- kreeg {visible_before}")
        click_or_fail(page, failures, '[data-action="pipeline-history-show-all"][data-entry-id="601"]', "candidates: Toon alles (entry 601)")
        if not wait_until(page, lambda: page.eval_on_selector_all('#pipelineHistoryWrap_601 .a-timeline__item', "els => els.length") == 12):
            failures.append("candidates: 'Toon alles' (601) onthulde niet alle twaalf items")

        select_or_fail(page, failures, '#pipelineStage_601', 'rejected', "candidates: fase kiezen (entry 601, poging 1)")
        click_or_fail(page, failures, '[data-action="pipeline-change-stage"][data-entry-id="601"]', "candidates: Fase wijzigen (entry 601, poging 1, verwacht 422)")
        if not wait_until(page, lambda: text_of(page, '#pipelineEntryAlert_601').strip() != ''):
            failures.append("candidates: geen inline-melding na de 422 op entry 601")
        reverted = page.eval_on_selector('#pipelineStage_601', "el => el.value")
        if reverted != "placed":
            failures.append(f"candidates: select van entry 601 draaide niet terug naar 'placed' na de 422 -- kreeg {reverted!r}")

        select_or_fail(page, failures, '#pipelineStage_601', 'rejected', "candidates: fase kiezen (entry 601, poging 2)")
        click_or_fail(page, failures, '[data-action="pipeline-change-stage"][data-entry-id="601"]', "candidates: Fase wijzigen (entry 601, poging 2, verwacht 500)")
        if not wait_until(page, lambda: "Internal server error" in text_of(page, '#pipelineEntryAlert_601')):
            failures.append(f"candidates: geen inline-melding na de 500 op entry 601 -- kreeg {text_of(page, '#pipelineEntryAlert_601')!r}")
        reverted = page.eval_on_selector('#pipelineStage_601', "el => el.value")
        if reverted != "placed":
            failures.append(f"candidates: select van entry 601 draaide niet terug naar 'placed' na de 500 -- kreeg {reverted!r}")

        select_or_fail(page, failures, '#pipelineStage_601', 'rejected', "candidates: fase kiezen (entry 601, poging 3)")
        click_or_fail(page, failures, '[data-action="pipeline-change-stage"][data-entry-id="601"]', "candidates: Fase wijzigen (entry 601, poging 3, verwacht 200)")
        if not wait_until(page, lambda: page.eval_on_selector('#pipelineStage_601', "el => el.value") == "rejected"):
            failures.append("candidates: entry 601 slaagde niet op de derde poging")
        if PIPELINE_ENTRIES_BY_ID[601]["stage"] != "rejected":
            failures.append(f"candidates: de server-fixture van entry 601 bleef op {PIPELINE_ENTRIES_BY_ID[601]['stage']!r} na een geslaagde PATCH")

        click_or_fail(page, failures, '#candidateDrawer [data-tab="toestemmingen"]', "candidates: de tab Toestemmingen")
        if not wait_until(page, lambda: page.query_selector('[data-action="candidate-talentpool-edit"]') is not None):
            failures.append("candidates: de tab Toestemmingen rendeerde niet")

        # Talentpool vastleggen met lege evidence: inline fout, nul aanroepen.
        click_or_fail(page, failures, '[data-action="candidate-talentpool-edit"]', "candidates: de knop Wijzigen (talentpool)")
        if not wait_until(page, lambda: page.query_selector('#tpEvidence') is not None):
            failures.append("candidates: de talentpoolmodal ging niet open")
        # design-reviewer op b9d5b21, punt 1 (BLOKKEREND): de radiogroep
        # Vastleggen/Intrekken rendert vóór de CSS-reparatie als twee
        # liggende ellipsen van de volle modalbreedte. Een echte
        # radioknop is nooit breder dan een tekstregel.
        radio_width = page.eval_on_selector('#tpConsentGrant', "el => el.getBoundingClientRect().width")
        if radio_width is None or radio_width >= 32:
            failures.append(f"candidates: #tpConsentGrant is {radio_width}px breed op 1440, verwacht kleiner dan 32px")
        if len(CANDIDATE_STATE["talentpool_calls"]) != 0:
            failures.append("candidates: talentpool_calls stond al niet op nul vóór de eerste inzending")
        click_or_fail(page, failures, '#candidateTalentpoolModal .btn-primary', "candidates: Opslaan (talentpool, leeg)")
        if not wait_until(page, lambda: "Vul kort in" in text_of(page, '#tpEvidenceError')):
            failures.append("candidates: lege evidence gaf geen inline fout in de talentpoolmodal")
        if CANDIDATE_STATE["talentpool_calls"]:
            failures.append("candidates: een talentpoolaanroep ging uit met lege evidence")

        # Vastleggen zonder omvang: nul aanroepen. code-reviewer LOW 4 op
        # b9d5b21: eerst de assertie op talentpool_calls, dan pas verder
        # -- zo faalt een mutant die de omvangcontrole doorlaat meteen op
        # deze regel in plaats van pas via een timeout verderop.
        fill_or_fail(page, failures, '#tpEvidence', 'Ondertekend formulier van 2 september.',
                     "candidates: bewijsveld (talentpool, zonder omvang)")
        click_or_fail(page, failures, '#candidateTalentpoolModal .btn-primary', "candidates: Opslaan (talentpool, zonder omvang)")
        if not wait_until(page, lambda: text_of(page, '#tpScopeError').strip() != ''):
            failures.append("candidates: het ontbreken van een omvang gaf geen inline fout")
        if CANDIDATE_STATE["talentpool_calls"]:
            failures.append("candidates: een talentpoolaanroep ging uit zonder omvang")

        # Vastleggen met omvang: één aanroep, consent=True plus scope.
        select_or_fail(page, failures, '#tpScope', 'matching_and_contact', "candidates: omvang kiezen (talentpool, vastleggen)")
        click_or_fail(page, failures, '#candidateTalentpoolModal .btn-primary', "candidates: Opslaan (talentpool, vastleggen)")
        if not wait_for_calls(page, CANDIDATE_STATE["talentpool_calls"], 1):
            failures.append("candidates: het vastleggen van talentpooltoestemming stuurde geen aanroep")
        elif (CANDIDATE_STATE["talentpool_calls"][0].get("scope") != "matching_and_contact"
              or CANDIDATE_STATE["talentpool_calls"][0].get("consent") is not True):
            failures.append(f"candidates: talentpool-vastleggen stuurde de verkeerde payload -- {CANDIDATE_STATE['talentpool_calls'][0]!r}")
        wait_until(page, lambda: page.query_selector('#candidateTalentpoolModal.show') is None)

        # Presentatie vastleggen: stuurt job_id; intrekken stuurt het niet.
        # Vóór de talentpool-intrekking hieronder: die zet
        # consent_withdrawn_at, en dan hoort deze knop (security-auditor
        # LOW 4) juist disabled te zijn.
        click_or_fail(page, failures, '[data-action="candidate-presentation-edit"]', "candidates: Vastleggen (presentatie)")
        if not wait_until(page, lambda: page.query_selector('#spJob') is not None and not is_disabled(page, '#spJob')):
            failures.append("candidates: de vacaturekiezer laadde niet, of bleef disabled, in de presentatiemodal")
        select_or_fail(page, failures, '#spJob', '201', "candidates: vacature kiezen (presentatie, vastleggen)")
        fill_or_fail(page, failures, '#spEvidence', 'E-mail in het dossier van 5 september.',
                     "candidates: bewijsveld (presentatie, vastleggen)")
        click_or_fail(page, failures, '#candidatePresentationModal .btn-primary', "candidates: Opslaan (presentatie, vastleggen)")
        if not wait_for_calls(page, CANDIDATE_STATE["presentation_calls"], 1):
            failures.append("candidates: het vastleggen van presentatietoestemming stuurde geen aanroep")
        elif CANDIDATE_STATE["presentation_calls"][0].get("job_id") != 201:
            failures.append(f"candidates: presentatie-vastleggen stuurde niet job_id=201 -- {CANDIDATE_STATE['presentation_calls'][0]!r}")
        wait_until(page, lambda: page.query_selector('#candidatePresentationModal.show') is None)

        click_or_fail(page, failures, '[data-action="candidate-presentation-edit"]', "candidates: Vastleggen (presentatie, intrekken)")
        wait_until(page, lambda: page.query_selector('#spConsentWithdraw') is not None)
        check_or_fail(page, failures, '#spConsentWithdraw', "candidates: Intrekken kiezen (presentatie)")
        fill_or_fail(page, failures, '#spEvidence', 'Telefonisch ingetrokken op 6 september.',
                     "candidates: bewijsveld (presentatie, intrekken)")
        click_or_fail(page, failures, '#candidatePresentationModal .btn-primary', "candidates: Opslaan (presentatie, intrekken)")
        if not wait_for_calls(page, CANDIDATE_STATE["presentation_calls"], 2):
            failures.append("candidates: het intrekken van presentatietoestemming stuurde geen aanroep")
        else:
            second_sp = CANDIDATE_STATE["presentation_calls"][1]
            if second_sp.get("consent") is not False or "job_id" in second_sp:
                failures.append(f"candidates: intrekken van presentatie stuurde toch een job_id mee -- {second_sp!r}")
        wait_until(page, lambda: page.query_selector('#candidatePresentationModal.show') is None)

        # ---- design-reviewer op b9d5b21, punt 3: 44px-tikdoel op 390 ----
        # Vóór de talentpool-intrekking (die de presentatieknop disabled
        # maakt): op dit moment staan beide kaartknoppen nog gewoon aan.
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(150)
        for sel, label, minimum in (
            ('[data-action="candidate-talentpool-edit"]', "Wijzigen (talentpool, tab)", 44),
            ('[data-action="candidate-presentation-edit"]', "Vastleggen (presentatie, tab)", 44),
        ):
            h = page.eval_on_selector(sel, "el => el.getBoundingClientRect().height")
            if h is None or h < minimum:
                failures.append(f"candidates (390): knop {label} is {h}px hoog, verwacht minstens {minimum}px")
        click_or_fail(page, failures, '[data-action="candidate-talentpool-edit"]', "candidates (390): Wijzigen (talentpool)")
        wait_until(page, lambda: page.query_selector('#tpEvidence') is not None)
        # design-reviewer op 2e47403, restpunt 1: de ellips-bug verborg dat
        # de radiolabel zelf (.form-check-label, "Vastleggen"/"Intrekken")
        # geen 44px-tikdoel had. Het tikdoel zit op de hele .form-check-rij
        # (label plus radio), niet op de tekst alleen.
        form_check_h = page.eval_on_selector(
            '#tpConsentGrant', "el => el.closest('.form-check').getBoundingClientRect().height")
        if form_check_h is None or form_check_h < 44:
            failures.append(f"candidates (390): .form-check-rij (talentpool, Vastleggen) is {form_check_h}px hoog, verwacht minstens 44px")
        for sel, label in (
            ('#candidateTalentpoolModal .btn-primary', "Opslaan (talentpoolmodal)"),
        ):
            h = page.eval_on_selector(sel, "el => el.getBoundingClientRect().height")
            if h is None or h < 44:
                failures.append(f"candidates (390): knop {label} is {h}px hoog, verwacht minstens 44px")
        click_or_fail(page, failures, '#candidateTalentpoolModal .btn-ghost-secondary', "candidates (390): Annuleren (talentpoolmodal)")
        wait_until(page, lambda: page.query_selector('#candidateTalentpoolModal.show') is None)

        click_or_fail(page, failures, '[data-action="candidate-presentation-edit"]', "candidates (390): Vastleggen (presentatie)")
        if not wait_until(page, lambda: page.query_selector('#spJob') is not None and not is_disabled(page, '#spJob')):
            failures.append("candidates (390): de vacaturekiezer laadde niet in de presentatiemodal")
        for sel, label in (
            ('#spJob', "vacaturekiezer (presentatiemodal)"),
            ('#candidatePresentationModal .btn-primary', "Opslaan (presentatiemodal)"),
        ):
            h = page.eval_on_selector(sel, "el => el.getBoundingClientRect().height")
            if h is None or h < 44:
                failures.append(f"candidates (390): {label} is {h}px hoog, verwacht minstens 44px")
        click_or_fail(page, failures, '#candidatePresentationModal .btn-ghost-secondary', "candidates (390): Annuleren (presentatiemodal)")
        wait_until(page, lambda: page.query_selector('#candidatePresentationModal.show') is None)

        # Intrekken: geen scope in de payload. Blijft op 390 staan (de
        # modals zijn hier al gemeten); dit zet ook consent_withdrawn_at
        # voor de MEDIUM-2-test en de LOW-4-assertie hieronder.
        click_or_fail(page, failures, '[data-action="candidate-talentpool-edit"]', "candidates: Wijzigen (talentpool, intrekken)")
        wait_until(page, lambda: page.query_selector('#tpConsentWithdraw') is not None)
        check_or_fail(page, failures, '#tpConsentWithdraw', "candidates: Intrekken kiezen (talentpool)")
        fill_or_fail(page, failures, '#tpEvidence', 'Telefonisch ingetrokken op 4 september.',
                     "candidates: bewijsveld (talentpool, intrekken)")
        click_or_fail(page, failures, '#candidateTalentpoolModal .btn-primary', "candidates: Opslaan (talentpool, intrekken)")
        if not wait_for_calls(page, CANDIDATE_STATE["talentpool_calls"], 2):
            failures.append("candidates: het intrekken van talentpooltoestemming stuurde geen aanroep")
        else:
            second_tp = CANDIDATE_STATE["talentpool_calls"][1]
            if second_tp.get("consent") is not False or "scope" in second_tp:
                failures.append(f"candidates: intrekken stuurde toch een omvang mee -- {second_tp!r}")
        wait_until(page, lambda: page.query_selector('#candidateTalentpoolModal.show') is None)

        # security-auditor LOW 4: de backend geeft hier gegarandeerd een
        # 409 (admin.py:1171-1176) zodra consent_withdrawn_at staat; de
        # knop meldt dat vooraf in het Nederlands in plaats van de
        # aanroep te laten mislukken.
        if not wait_until(page, lambda: is_disabled(page, '[data-action="candidate-presentation-edit"]')):
            failures.append("candidates: de presentatieknop bleef aan nadat talentpool was ingetrokken")
        # code-reviewer op ece9d6d: is_disabled() geeft default=True terug
        # als het element ontbreekt, dus de wait_until hierboven kan
        # spuriously slagen op een re-render waarin de knop even weg is.
        # Een kale eval_on_selector daarna stierf dan met "Failed to find
        # element" in plaats van een failure-regel op te leveren.
        if page.query_selector('[data-action="candidate-presentation-edit"]') is None:
            failures.append("candidates: de presentatieknop is niet meer te vinden na het intrekken van talentpool")
        else:
            presentation_title = page.eval_on_selector(
                '[data-action="candidate-presentation-edit"]', "el => el.getAttribute('title') || ''")
            if "ingetrokken" not in (presentation_title or ""):
                failures.append(f"candidates: de disabled presentatieknop mist een Nederlandse reden -- kreeg {presentation_title!r}")
        # chief-of-staff op 3c8f690: dezelfde reden hoort ook zichtbaar te
        # staan, niet alleen als title (geen hover op 390), en de
        # talentpoolkaart hoort "Ingetrokken op <datum>" te tonen.
        tab_text_after_withdraw = text_of(page, '#candidateDrawerTabContent')
        if "toestemming ingetrokken; presentatie kan niet worden vastgelegd" not in tab_text_after_withdraw.lower():
            failures.append(
                "candidates: de zichtbare reden onder de presentatieknop ontbreekt na intrekken -- "
                f"kreeg {tab_text_after_withdraw[:400]!r}"
            )
        if "Ingetrokken op" not in tab_text_after_withdraw:
            failures.append(
                "candidates: de talentpoolkaart toont geen 'Ingetrokken op <datum>'-regel na intrekken -- "
                f"kreeg {tab_text_after_withdraw[:400]!r}"
            )

        # security-auditor MEDIUM 2: opnieuw vastleggen ná een intrekking
        # mag niet op de (nooit ververste) PATCH-respons vertrouwen. De
        # stub zet consent_withdrawn_at alleen in de volgende GET, nooit in
        # de PATCH-RETURNING -- precies het gat dat force:true dichtte. De
        # vorige modal sloot al bij het intrekken (handle.close() op
        # succes), dus opnieuw openen in plaats van hetzelfde paneel
        # hergebruiken.
        click_or_fail(page, failures, '[data-action="candidate-talentpool-edit"]', "candidates: Wijzigen (talentpool, opnieuw vastleggen)")
        wait_until(page, lambda: page.query_selector('#tpConsentGrant') is not None)
        check_or_fail(page, failures, '#tpConsentGrant', "candidates: Vastleggen kiezen (talentpool, opnieuw)")
        select_or_fail(page, failures, '#tpScope', 'matching_and_contact', "candidates: omvang kiezen (talentpool, opnieuw vastleggen)")
        fill_or_fail(page, failures, '#tpEvidence', 'Opnieuw ondertekend op 5 september.',
                     "candidates: bewijsveld (talentpool, opnieuw vastleggen)")
        click_or_fail(page, failures, '#candidateTalentpoolModal .btn-primary', "candidates: Opslaan (talentpool, opnieuw vastleggen)")
        if not wait_for_calls(page, CANDIDATE_STATE["talentpool_calls"], 3):
            failures.append("candidates: het opnieuw vastleggen van talentpooltoestemming stuurde geen aanroep")
        if not wait_until(page, lambda: "Toestemming actief" in text_of(page, '#candidateDrawerTabContent')):
            failures.append("candidates: de talentpoolkaart toont geen actieve toestemming na opnieuw vastleggen")
        if not wait_for_text(page, '#candidateDrawerTabContent', 'toestemming ingetrokken'):
            failures.append(
                "candidates: job-alerts volgde niet het verse detail na opnieuw vastleggen -- "
                f"kreeg {text_of(page, '#candidateDrawerTabContent')!r}"
            )
        eligible_row_after_regrant = page.eval_on_selector(
            '#candidateDrawerTabContent',
            "el => { const rows = [...el.querySelectorAll('.a-metric-row')]; "
            "const row = rows.find(r => r.textContent.includes('Komt in aanmerking')); "
            "return row ? row.textContent : null; }",
        )
        if not eligible_row_after_regrant or 'Nee' not in eligible_row_after_regrant:
            failures.append(
                "candidates: job-alerts toont geen Nee terwijl de backend consent_withdrawn_at nog draagt -- "
                f"kreeg {eligible_row_after_regrant!r}"
            )

        # ---- Referral: twee eigen 409's op detail.code, val terug op
        # detail.message. Blijft op 390 (design-reviewer punt 2). ----
        click_or_fail(page, failures, '#candidateDrawer [data-action="close-modal"]', "candidates: sluitknop van de kandidaatdrawer")
        wait_until(page, lambda: page.query_selector('#candidateDrawer.show') is None)

        CANDIDATE_STATE["referral_mode"] = "suppressed"
        click_or_fail(page, failures, '[data-action="open-referral-modal"]', "candidates: de knop Referral vastleggen")
        if not wait_until(page, lambda: page.query_selector('#refFullName') is not None):
            failures.append("candidates: de referralmodal ging niet open")
        fill_or_fail(page, failures, '#refFullName', 'Voorbeeld Referral', "candidates: volledige naam (referral, suppressed)")
        fill_or_fail(page, failures, '#refEmail', 'referral@example.invalid', "candidates: e-mailadres (referral, suppressed)")
        # code-reviewer op b9d5b21, punt 3: infoName wordt bijgewerkt via
        # textContent, niet innerHTML -- "<b>" moet dus als platte tekst
        # verschijnen, nooit als een echt <b>-element. design-reviewer op
        # 2e47403: een losse run zag deze twee asserties falen op een
        # kennelijke race (de input-listener van #refReferredBy is
        # synchroon, maar onder belasting bleek een directe lezing één
        # keer te vroeg); een conditiewacht in plaats van een directe
        # lezing lost dat op zonder een vaste sleep.
        fill_or_fail(page, failures, '#refReferredBy', 'Jan <b>Voorbeeld</b>', "candidates: aangedragen door (referral, suppressed)")
        if not wait_until(page, lambda: text_of(page, '#referralInfoName') == 'Jan <b>Voorbeeld</b>'):
            failures.append(f"candidates: het informatieblok toont de naam niet live/letterlijk -- kreeg {text_of(page, '#referralInfoName')!r}")
        elif page.query_selector('#referralInfoName b') is not None:
            failures.append("candidates: het informatieblok interpreteert <b> als markup (innerHTML in plaats van textContent)")
        fill_or_fail(page, failures, '#refEvidence', 'Mondeling bevestigd door Jan op 3 september.',
                     "candidates: bewijsveld (referral, suppressed)")
        click_or_fail(page, failures, '#candidateReferralModal .btn-primary', "candidates: Vastleggen (referral, suppressed)")
        if not wait_for_calls(page, CANDIDATE_STATE["referral_calls"], 1):
            failures.append("candidates: de referral-aanroep (suppressed) ging niet uit")
        if not wait_for_text(page, '#candidateReferralAlert', 'suppressielijst'):
            failures.append(f"candidates: de suppressielijst-melding verscheen niet -- kreeg {text_of(page, '#candidateReferralAlert')!r}")
        if page.query_selector('#candidateReferralAlert [data-action]') is not None:
            failures.append("candidates: de suppressielijst-melding toonde onterecht een knop")
        # design-reviewer op b9d5b21, punt 2 (BLOKKEREND op mobiel): zonder
        # scrollIntoView staat deze melding op 390 buiten beeld.
        alert_top = page.eval_on_selector('#candidateReferralAlert .alert', "el => el.getBoundingClientRect().top")
        if alert_top is None or alert_top < 0:
            failures.append(f"candidates (390): de 409-melding staat buiten beeld (top={alert_top})")

        CANDIDATE_STATE["referral_mode"] = "exists"
        click_or_fail(page, failures, '#candidateReferralModal .btn-primary', "candidates: Vastleggen (referral, exists)")
        if not wait_for_calls(page, CANDIDATE_STATE["referral_calls"], 2):
            failures.append("candidates: de referral-aanroep (exists) ging niet uit")
        if not wait_until(page, lambda: page.query_selector('[data-action="candidate-referral-open-existing"]') is not None):
            failures.append("candidates: de knop Kandidaat openen verscheen niet bij referral_candidate_exists")
        else:
            click_or_fail(page, failures, '[data-action="candidate-referral-open-existing"]', "candidates: de knop Kandidaat openen")
            if not wait_until(page, lambda: page.query_selector('#candidateDrawerTabContent') is not None
                              and page.query_selector('#candidateReferralModal.show') is None):
                failures.append("candidates: 'Kandidaat openen' opende de drawer niet (of sloot de referralmodal niet)")

        CANDIDATE_STATE["referral_mode"] = "unknown"
        click_or_fail(page, failures, '#candidateDrawer [data-action="close-modal"]',
                      "candidates: sluitknop van de kandidaatdrawer (na Kandidaat openen)")
        wait_until(page, lambda: page.query_selector('#candidateDrawer.show') is None)
        click_or_fail(page, failures, '[data-action="open-referral-modal"]', "candidates: Referral vastleggen (opnieuw)")
        wait_until(page, lambda: page.query_selector('#refFullName') is not None)
        fill_or_fail(page, failures, '#refFullName', 'Voorbeeld Referral Twee', "candidates: volledige naam (referral, onbekende code)")
        fill_or_fail(page, failures, '#refEmail', 'referral2@example.invalid', "candidates: e-mailadres (referral, onbekende code)")
        fill_or_fail(page, failures, '#refReferredBy', 'Piet Voorbeeld', "candidates: aangedragen door (referral, onbekende code)")
        fill_or_fail(page, failures, '#refEvidence', 'Mondeling bevestigd door Piet op 4 september.',
                     "candidates: bewijsveld (referral, onbekende code)")
        click_or_fail(page, failures, '#candidateReferralModal .btn-primary', "candidates: Vastleggen (referral, onbekende code)")
        if not wait_for_calls(page, CANDIDATE_STATE["referral_calls"], 3):
            failures.append("candidates: de referral-aanroep (onbekende code) ging niet uit")
        if not wait_for_text(page, '#candidateReferralAlert', "does not know a Dutch sentence"):
            failures.append(f"candidates: de onbekende 409-code viel niet terug op detail.message -- kreeg {text_of(page, '#candidateReferralAlert')!r}")
        click_or_fail(page, failures, '#candidateReferralModal [data-action="close-modal"]', "candidates: sluitknop van de referralmodal")
        wait_until(page, lambda: page.query_selector('#candidateReferralModal.show') is None)

        # Terug naar de werkbreedte voor eventuele volgende secties.
        page.set_viewport_size({"width": 1400, "height": 1000})
        page.wait_for_timeout(150)

        # ---- security-auditor HIGH 1: self-registered via de sourced-route ----
        click_or_fail(page, failures, '.nav-link[data-section="candidates"]', "candidates: terug naar de kandidatenlijst")
        if not wait_until(page, lambda: page.query_selector('#section-candidates table tbody [data-action="view-candidate"][data-kind="self-registered"]') is not None):
            failures.append("candidates: de self-registered rij (kind self-registered) ontbreekt in de lijst")
        else:
            click_or_fail(page, failures, '#section-candidates table tbody [data-action="view-candidate"][data-kind="self-registered"]',
                          "candidates: de bekijkknop van de self-registered rij")
            wait_until(page, lambda: page.query_selector('#candidateDrawerTabContent') is not None)
            click_or_fail(page, failures, '#candidateDrawer [data-tab="toestemmingen"]', "candidates: de tab Toestemmingen (self-registered)")
            if not wait_until(page, lambda: 'Toestemming actief' in text_of(page, '#candidateDrawerTabContent')):
                failures.append(
                    "candidates: self-registered kandidaat met een gekoppelde candidates-rij toont geen "
                    f"actieve toestemming -- kreeg {text_of(page, '#candidateDrawerTabContent')!r}. Dit is de "
                    "HIGH-1-regressie: GET /candidates/self-registered/{id} draagt geen consentkolommen, dus "
                    "de tab moet via kind sourced navragen."
                )
            self_reg_text = text_of(page, '#candidateDrawerTabContent')
            if self_reg_text.count('Toestemming actief') < 2:
                failures.append(
                    f"candidates: self-registered kandidaat toont niet beide kaarten als actief -- kreeg {self_reg_text[:400]!r}"
                )
            if not wait_for_text(page, '#candidateDrawerTabContent', 'Aangezet'):
                failures.append("candidates: de job-alerts-kaart rendeerde niet voor de self-registered kandidaat")
            eligible_row = page.eval_on_selector(
                '#candidateDrawerTabContent',
                "el => { const rows = [...el.querySelectorAll('.a-metric-row')]; "
                "const row = rows.find(r => r.textContent.includes('Komt in aanmerking')); "
                "return row ? row.textContent : null; }",
            )
            if not eligible_row or 'Ja' not in eligible_row:
                failures.append(f"candidates: job-alerts voor de self-registered kandidaat is niet Ja -- kreeg {eligible_row!r}")
            click_or_fail(page, failures, '#candidateDrawer [data-action="close-modal"]',
                          "candidates: sluitknop van de kandidaatdrawer (self-registered)")
            wait_until(page, lambda: page.query_selector('#candidateDrawer.show') is None)

        # De referral- en de talentpool-409's zijn opzettelijk en al op
        # tekst getoetst hierboven; Chromium logt elke 409-respons zelf ook
        # als console error, zoals bij de opzettelijke 500 van
        # Bewaartermijnen. Idem voor de opzettelijke 422/500 op de tab
        # Pipeline (entry 601) en de permanente 500 op de historie van
        # entry 602.
        new_errors = [e for e in console_errors[errors_before:]
                      if "409 (Conflict)" not in e and "422" not in e and "500 (Internal Server Error)" not in e]
        if new_errors:
            failures.append(f"candidates: {len(new_errors)} console error(s): {new_errors[:3]}")

        # ---- Plaatsingen (§7.3.3) ----
        errors_before = len(console_errors)
        page.click('.nav-link[data-section="placements"]')
        wait_until(page, lambda: len(page.query_selector_all('#placementsBody tr')) > 0)

        rows = page.query_selector_all('#placementsBody tr')
        if len(rows) != 20:
            failures.append(f"placements: lijst toonde {len(rows)} rijen, verwacht 20 (paginagrootte naast 60 rijen)")
        if page.query_selector('#placementsPagination button[data-page="2"]') is None:
            failures.append("placements: paginering met 60 rijen toonde geen pagina 2")
        first_row_text = text_of(page, '#placementsBody tr')
        if "Kandidaat #1482" not in first_row_text:
            failures.append(f"placements: eerste rij toont geen 'Kandidaat #1482' -- kreeg {first_row_text[:160]!r}")
        if "Example Engineering B.V." not in first_row_text:
            failures.append(f"placements: opdrachtgeverkolom toont geen naam -- kreeg {first_row_text[:160]!r}")
        if "Concept" not in first_row_text:
            failures.append(f"placements: statuskolom toont geen vertaald label -- kreeg {first_row_text[:160]!r}")
        if "concept" in first_row_text.replace("Concept", ""):
            failures.append("placements: de ruwe status 'concept' lekte naast het vertaalde label")

        # Server-side sortering: eerste klik op "Kandidaat" is ascending en
        # zet het aria-sort-attribuut; de enige rij met candidate_id 1483
        # (plaatsing #3) zakt dan naar het einde van de hele verzameling en
        # verdwijnt van pagina 1 (59 rijen met 1482 komen ervoor).
        click_or_fail(page, failures, '#placementsHead [data-sort-key="candidate_id"]', "de sorteerbare kolomkop Kandidaat")
        wait_until(page, lambda: page.get_attribute('#placementsHead [data-sort-key="candidate_id"]', 'aria-sort') == 'ascending')
        wait_until(page, lambda: "Kandidaat #1483" not in text_of(page, '#placementsBody'))
        if "Kandidaat #1483" in text_of(page, '#placementsBody'):
            failures.append("placements: oplopend sorteren op kandidaat zette #1483 niet achteraan de hele verzameling")
        click_or_fail(page, failures, '#placementsHead [data-sort-key="candidate_id"]', "de sorteerbare kolomkop Kandidaat (tweede klik)")
        wait_until(page, lambda: page.get_attribute('#placementsHead [data-sort-key="candidate_id"]', 'aria-sort') == 'descending')
        wait_until(page, lambda: "Kandidaat #1483" in text_of(page, '#placementsBody'))
        if "Kandidaat #1483" not in text_of(page, '#placementsBody'):
            failures.append("placements: aflopend sorteren op kandidaat zette #1483 niet vooraan")

        # Statusfilter.
        select_or_fail(page, failures, '#placementStatusFilter', 'actief', "placements: statusfilter")
        wait_until(page, lambda: len(page.query_selector_all('#placementsBody tr')) == 1)
        status_filtered = text_of(page, '#placementsBody')
        if "Actief" not in status_filtered:
            failures.append(f"placements: statusfilter 'actief' toonde geen actieve plaatsing -- kreeg {status_filtered[:160]!r}")
        select_or_fail(page, failures, '#placementStatusFilter', '', "placements: statusfilter terugzetten")
        wait_until(page, lambda: len(page.query_selector_all('#placementsBody tr')) > 1)

        # Opdrachtgeverfilter.
        select_or_fail(page, failures, '#placementClientFilter', '2', "placements: opdrachtgeverfilter")
        wait_until(page, lambda: len(page.query_selector_all('#placementsBody tr')) == 1)
        client_filtered = text_of(page, '#placementsBody')
        if "Example Mechatronics B.V." not in client_filtered or "Beëindigd" not in client_filtered:
            failures.append(f"placements: opdrachtgeverfilter toonde niet de juiste rij -- kreeg {client_filtered[:200]!r}")
        select_or_fail(page, failures, '#placementClientFilter', '', "placements: opdrachtgeverfilter terugzetten")
        wait_until(page, lambda: len(page.query_selector_all('#placementsBody tr')) > 1)

        # Kandidaatzoekveld (as-built afwijking 1): numeriek gaat direct als
        # candidate_id, een naam lost op via de kandidatenlijst, en bij
        # meerdere treffers blijft de lijst ongefilterd met een hint.
        fill_or_fail(page, failures, '#placementCandidateSearch', '1482', "placements: kandidaatzoekveld (numeriek)")
        page.wait_for_timeout(600)
        numeric_search_text = text_of(page, '#placementsBody')
        if "Kandidaat #1483" in numeric_search_text:
            failures.append("placements: numeriek kandidaat-ID filterde #1483 niet weg")
        fill_or_fail(page, failures, '#placementCandidateSearch', 'Voorbeeld', "placements: kandidaatzoekveld (ambigu)")
        page.wait_for_timeout(600)
        ambiguous_hint = text_of(page, '#placementCandidateSearchHint')
        if "Meerdere kandidaten gevonden" not in ambiguous_hint:
            failures.append(f"placements: ambigue kandidaatzoekopdracht toonde geen hint -- kreeg {ambiguous_hint!r}")
        fill_or_fail(page, failures, '#placementCandidateSearch', 'Zelf Geregistreerd', "placements: kandidaatzoekveld (uniek)")
        page.wait_for_timeout(600)
        wait_until(page, lambda: len(page.query_selector_all('#placementsBody tr')) == 1)
        unique_search_text = text_of(page, '#placementsBody')
        if "Kandidaat #1483" not in unique_search_text:
            failures.append(f"placements: unieke naamzoekopdracht vond de verkeerde kandidaat -- kreeg {unique_search_text[:160]!r}")
        fill_or_fail(page, failures, '#placementCandidateSearch', '', "placements: kandidaatzoekveld leegmaken")
        page.wait_for_timeout(600)
        wait_until(page, lambda: len(page.query_selector_all('#placementsBody tr')) > 1)

        # ---- Drawer: Overzicht, statuswisseling gewoon en naar geannuleerd ----
        click_or_fail(page, failures, '[data-action="open-placement-drawer"][data-id="1"]', "placements: 'Openen' op plaatsing #1")
        wait_until(page, lambda: page.query_selector('#placementDrawerTabContent') is not None
                   and "Kandidaat #1482" in text_of(page, '#placementDrawerTabContent'))
        overview_text = text_of(page, '#placementDrawerTabContent')
        for needle in ("Kandidaat #1482", "Example Engineering B.V.", "Embedded Software Engineer", "Detachering", "1 okt 2026"):
            if needle not in overview_text:
                failures.append(f"placements: overzichttab mist {needle!r} -- kreeg {overview_text[:300]!r}")
        if page.query_selector('#placementStatusSelect') is None:
            failures.append("placements: overzichttab toonde geen statuswisselaar voor een concept-plaatsing")

        select_or_fail(page, failures, '#placementStatusSelect', 'actief', "placements: status wijzigen naar actief")
        wait_until(page, lambda: page.query_selector('#placementStatusModal') is not None
                   and text_of(page, '#placementStatusModal').count('Concept') >= 1
                   and 'Actief' in text_of(page, '#placementStatusModal'))
        if page.query_selector('#placementStatusModal .btn-outline-danger') is not None:
            failures.append("placements: statuswissel naar actief gebruikte per ongeluk de destructieve knop")
        calls_before = len(PLACEMENTS_STATE["status_calls"])
        click_or_fail(page, failures, '#placementStatusModal .btn-primary', "placements: 'Bevestigen' (status naar actief)")
        if not wait_for_calls(page, PLACEMENTS_STATE["status_calls"], calls_before + 1):
            failures.append("placements: statuswissel naar actief riep de status-route niet aan")
        elif PLACEMENTS_STATE["status_calls"][-1]["body"].get("status") != "actief":
            failures.append(f"placements: statuswissel stuurde de verkeerde body -- kreeg {PLACEMENTS_STATE['status_calls'][-1]}")
        wait_until(page, lambda: page.query_selector('#placementStatusModal') is None)
        wait_until(page, lambda: "Actief" in text_of(page, '#placementDrawerTabContent'))

        select_or_fail(page, failures, '#placementStatusSelect', 'geannuleerd', "placements: status wijzigen naar geannuleerd")
        wait_until(page, lambda: page.query_selector('#placementStatusModal') is not None)
        if page.query_selector('#placementStatusModal .btn-outline-danger') is None:
            failures.append("placements: statuswissel naar geannuleerd gebruikte niet de destructieve knop")
        if page.query_selector('#placementStatusModal input[id^="confirm_"]') is not None:
            failures.append("placements: statuswissel naar geannuleerd vroeg per ongeluk een getypte bevestiging")
        calls_before = len(PLACEMENTS_STATE["status_calls"])
        click_or_fail(page, failures, '#placementStatusModal .btn-outline-danger', "placements: annuleerknop (status naar geannuleerd)")
        if not wait_for_calls(page, PLACEMENTS_STATE["status_calls"], calls_before + 1):
            failures.append("placements: statuswissel naar geannuleerd riep de status-route niet aan")
        wait_until(page, lambda: "Geannuleerd" in text_of(page, '#placementDrawerTabContent'))
        if "definitief" not in text_of(page, '#placementDrawerTabContent').lower():
            failures.append("placements: een terminale status toonde geen 'geen overgang meer mogelijk'-tekst")

        # ---- Drawer: Financieel ----
        click_or_fail(page, failures, '#placementDrawer [data-tab="financieel"]', "placements: tabblad Financieel")
        wait_until(page, lambda: "Uurtarief" in text_of(page, '#placementDrawerTabContent'))
        fin_text = text_of(page, '#placementDrawerTabContent')
        for needle in ("€ 95,50", "160,00", "n.v.t.", "Acme EOR", "1,3500", "Onboarding", "€ 500,00"):
            if needle not in fin_text:
                failures.append(f"placements: financieeltab mist {needle!r} -- kreeg {fin_text[:400]!r}")

        # ---- Drawer: Marge (null-invoer, herberekenen, ongeldig bedrag) ----
        click_or_fail(page, failures, '#placementDrawer [data-tab="marge"]', "placements: tabblad Marge")
        wait_until(page, lambda: "Voorlopig" in text_of(page, '#placementDrawerTabContent'))
        margin_text = text_of(page, '#placementDrawerTabContent')
        if WARNING_SENTENCE_PY not in margin_text:
            failures.append(f"placements: margewaarschuwing niet letterlijk -- kreeg {margin_text[:300]!r}")
        wait_until(page, lambda: "€ 15.280,00" in text_of(page, '#placementMarginResult'))
        null_result = text_of(page, '#placementMarginResult')
        if null_result.count('n.v.t. (invoer ontbreekt)') < 3:
            failures.append(f"placements: marge zonder invoer toonde geen 'n.v.t. (invoer ontbreekt)' -- kreeg {null_result[:300]!r}")

        margin_calls_before = len(PLACEMENTS_STATE["margin_calls"])
        fill_or_fail(page, failures, '#placementMarginGross', '12,34,56', "placements: bruto maandsalaris (ongeldig)")
        click_or_fail(page, failures, '#placementMarginRecalc', "placements: 'Herberekenen' (ongeldig bedrag)")
        page.wait_for_timeout(300)
        if len(PLACEMENTS_STATE["margin_calls"]) != margin_calls_before:
            failures.append("placements: een ongeldig margebedrag riep de margeroute toch aan")
        if not text_of(page, '#placementMarginGrossError').strip():
            failures.append("placements: een ongeldig margebedrag toonde geen inline fout")

        fill_or_fail(page, failures, '#placementMarginGross', '5200,00', "placements: bruto maandsalaris (komma-decimaal)")
        click_or_fail(page, failures, '#placementMarginRecalc', "placements: 'Herberekenen'")
        if not wait_for_calls(page, PLACEMENTS_STATE["margin_calls"], margin_calls_before + 1):
            failures.append("placements: herberekenen riep de margeroute niet aan")
        elif float(PLACEMENTS_STATE["margin_calls"][-1].get("gross_monthly_salary") or -1) != 5200:
            failures.append(f"placements: komma-decimaal werd niet genormaliseerd -- kreeg {PLACEMENTS_STATE['margin_calls'][-1]!r}")
        wait_until(page, lambda: "€ 7.020,00" in text_of(page, '#placementMarginResult'))
        recalculated = text_of(page, '#placementMarginResult')
        if "€ 8.260,00" not in recalculated:
            failures.append(f"placements: herberekende marge klopt niet -- kreeg {recalculated[:300]!r}")
        if recalculated.count('Voorlopig') < 1:
            failures.append("placements: de provisional-waarschuwing herhaalde niet in de uitkomst")

        click_or_fail(page, failures, '#placementDrawer [data-action="close-modal"]', "placements: sluitknop van de drawer")
        wait_until(page, lambda: page.query_selector('#placementDrawer.show') is None)

        # ---- Aanmaken: verplichte velden, ongeldig bedrag (nul aanroepen), komma-decimaal ----
        click_or_fail(page, failures, '[data-action="open-new-placement-modal"]', "placements: 'Nieuwe plaatsing'")
        wait_until(page, lambda: page.query_selector('#placementFormCandidate') is not None)
        candidate_option_text = page.eval_on_selector('#placementFormCandidate', "el => el.textContent")
        if "1482" not in candidate_option_text or "1483" not in candidate_option_text:
            failures.append(f"placements: kandidaatkiezer mist opties -- kreeg {candidate_option_text[:200]!r}")
        select_or_fail(page, failures, '#placementFormCandidate', '1482', "placements: kandidaat kiezen")
        select_or_fail(page, failures, '#placementFormClient', '1', "placements: opdrachtgever kiezen")
        select_or_fail(page, failures, '#placementFormJob', '201', "placements: vacature kiezen")
        select_or_fail(page, failures, '#placementFormType', 'werving_selectie', "placements: type kiezen")
        fill_or_fail(page, failures, '#placementFormFeePercentage', '150', "placements: feepercentage (ongeldig, > 100)")
        creates_before = len(PLACEMENTS_STATE["creates"])
        click_or_fail(page, failures, '#placementFormModal .btn-primary', "placements: 'Plaatsing aanmaken' (ongeldig bedrag)")
        page.wait_for_timeout(300)
        if len(PLACEMENTS_STATE["creates"]) != creates_before:
            failures.append("placements: een feepercentage boven 100 riep de aanmaakroute toch aan")
        if not text_of(page, '#placementFormFeePercentageError').strip():
            failures.append("placements: een feepercentage boven 100 toonde geen inline fout")

        fill_or_fail(page, failures, '#placementFormFeePercentage', '20,5', "placements: feepercentage (komma-decimaal)")
        click_or_fail(page, failures, '#placementFormOneOffAdd', "placements: 'Regel toevoegen' (eenmalige kosten)")
        wait_until(page, lambda: page.query_selector('[data-oneoff-field="label"][data-oneoff-index="0"]') is not None)
        fill_or_fail(page, failures, '[data-oneoff-field="label"][data-oneoff-index="0"]', "Search fee", "placements: omschrijving eenmalige kost")

        # design-reviewer op ece9d6d: de sticky voettekst mag geen enkel
        # veld overlappen (klik-hijack). 1440x1000: "Regel toevoegen" zit
        # vlak boven de footer in een lang formulier.
        if page.query_selector('#placementFormOneOffAdd') is None:
            failures.append("placements: 'Regel toevoegen' niet gevonden voor de klik-hijacktest")
        elif not element_from_point_is_self(page, '#placementFormOneOffAdd'):
            failures.append("placements (1440): de sticky voettekst overlapt 'Regel toevoegen' (klik-hijack)")
        page.eval_on_selector('#placementFormModal .modal-body', "el => { el.scrollTop = el.scrollHeight; }")
        page.wait_for_timeout(150)
        stuck_fields = fields_behind_sticky_footer(page, '#placementFormModal')
        if stuck_fields:
            failures.append(f"placements (1440): velden liggen na scrollen naar onder binnen de footerband -- {stuck_fields}")

        # Zelfde overlapcontrole op 390, waar de knoppen stapelen en de
        # footer dus hoger wordt: Afrekenbasis staat er vlak boven.
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(200)
        if page.query_selector('#placementFormBillingBasis') is None:
            failures.append("placements (390): #placementFormBillingBasis niet gevonden voor de klik-hijacktest")
        elif not element_from_point_is_self(page, '#placementFormBillingBasis'):
            failures.append("placements (390): de sticky voettekst overlapt Afrekenbasis (klik-hijack)")
        # Zelfde scroll-naar-onder-controle als bij 1440: op 390 stapelen de
        # knoppen (hogere footer), dus dit toetst een andere footerhoogte,
        # niet dezelfde aanname nogmaals.
        page.eval_on_selector('#placementFormModal .modal-body', "el => { el.scrollTop = el.scrollHeight; }")
        page.wait_for_timeout(150)
        stuck_fields_390 = fields_behind_sticky_footer(page, '#placementFormModal')
        if stuck_fields_390:
            failures.append(f"placements (390): velden liggen na scrollen naar onder binnen de footerband -- {stuck_fields_390}")
        page.set_viewport_size({"width": 1400, "height": 1000})
        page.wait_for_timeout(200)

        # security-auditor LOW-2 op 1212e07: een eenmalige kost boven het
        # geldplafond mag geen aanroep opleveren, net als elk ander bedrag.
        fill_or_fail(page, failures, '[data-oneoff-field="amount"][data-oneoff-index="0"]', "99999999999999999,99",
                     "placements: bedrag eenmalige kost (ongeldig, boven het plafond)")
        creates_before_overflow = len(PLACEMENTS_STATE["creates"])
        click_or_fail(page, failures, '#placementFormModal .btn-primary', "placements: 'Plaatsing aanmaken' (eenmalige kost boven het plafond)")
        page.wait_for_timeout(300)
        if len(PLACEMENTS_STATE["creates"]) != creates_before_overflow:
            failures.append("placements: een eenmalige kost boven het plafond riep de aanmaakroute toch aan")
        if not text_of(page, '#placementOneOffAmountError0').strip():
            failures.append("placements: een eenmalige kost boven het plafond toonde geen inline fout")

        fill_or_fail(page, failures, '[data-oneoff-field="amount"][data-oneoff-index="0"]', "1234,56", "placements: bedrag eenmalige kost")
        click_or_fail(page, failures, '#placementFormModal .btn-primary', "placements: 'Plaatsing aanmaken'")
        if not wait_for_calls(page, PLACEMENTS_STATE["creates"], creates_before + 1):
            failures.append("placements: aanmaken riep de POST-route niet aan")
        else:
            created_body = PLACEMENTS_STATE["creates"][-1]
            if created_body.get("fee_percentage") != 20.5:
                failures.append(f"placements: komma-decimaal in feepercentage werd niet genormaliseerd -- kreeg {created_body.get('fee_percentage')!r}")
            costs = created_body.get("one_off_costs") or []
            if not costs or costs[0].get("label") != "Search fee" or costs[0].get("amount") != 1234.56:
                failures.append(f"placements: eenmalige kosten kwamen niet correct mee -- kreeg {costs!r}")
            for key in ("candidate_id", "job_id", "client_id", "placement_type"):
                if key not in created_body:
                    failures.append(f"placements: aanmaken miste verplicht veld {key!r} in de payload")
        wait_until(page, lambda: page.query_selector('#placementFormModal.show') is None)

        # ---- Bewerken: PATCH bevat geen candidate_id/job_id/client_id/type ----
        # code-reviewer op 1212e07: submitPlacementForm sluit de modal vóór
        # await loadPlacements, en ui.table.reload zet de tbody eerst op de
        # laadrij -- zonder deze wachtregel klikt dit soms op een tbody die
        # nog aan het herladen is (1 op 3 rood).
        wait_until(page, lambda: page.query_selector('[data-action="open-placement-drawer"][data-id="2"]') is not None)
        click_or_fail(page, failures, '[data-action="open-placement-drawer"][data-id="2"]', "placements: 'Openen' op plaatsing #2")
        wait_until(page, lambda: "Kandidaat #1482" in text_of(page, '#placementDrawerTabContent'))
        click_or_fail(page, failures, '#placementDrawer [data-tab="financieel"]', "placements: tabblad Financieel (plaatsing #2)")
        # design-reviewer op 1212e07: "Bewerken" verhuisde van een losse
        # knop in de tab Financieel naar de sticky drawervoettekst
        # (ui.drawer's `footer`-optie, §7.2b), want het bewerkmodal
        # wijzigt ook Overzicht-velden (start-/einddatum, notities).
        wait_until(page, lambda: page.query_selector('#placementDrawer .a-sticky-footer .btn-primary') is not None)
        click_or_fail(page, failures, '#placementDrawer .a-sticky-footer .btn-primary', "placements: 'Bewerken' (drawervoettekst)")
        wait_until(page, lambda: page.query_selector('#placementFormNotes') is not None)
        if page.query_selector('#placementFormCandidate') is not None:
            failures.append("placements: het bewerkmodal toonde per ongeluk de kandidaatkiezer")
        summary_text = text_of(page, '#placementFormModal')
        if "Kandidaat #1482" not in summary_text or "Werving & selectie" not in summary_text:
            failures.append(f"placements: bewerkmodal toonde geen alleen-lezen samenvatting -- kreeg {summary_text[:300]!r}")
        fill_or_fail(page, failures, '#placementFormNotes', 'Bijgewerkt via test', "placements: notities bewerken")
        updates_before = len(PLACEMENTS_STATE["updates"])
        click_or_fail(page, failures, '#placementFormModal .btn-primary', "placements: 'Opslaan' (bewerken)")
        if not wait_for_calls(page, PLACEMENTS_STATE["updates"], updates_before + 1):
            failures.append("placements: bewerken riep de PATCH-route niet aan")
        else:
            update_body = PLACEMENTS_STATE["updates"][-1]["body"]
            for key in ("candidate_id", "job_id", "client_id", "placement_type"):
                if key in update_body:
                    failures.append(f"placements: PATCH bevatte het onwijzigbare veld {key!r}")
            if update_body.get("notes") != "Bijgewerkt via test":
                failures.append(f"placements: PATCH stuurde niet de gewijzigde notities -- kreeg {update_body!r}")
        wait_until(page, lambda: page.query_selector('#placementFormModal.show') is None)
        click_or_fail(page, failures, '#placementDrawer [data-tab="overzicht"]', "placements: tabblad Overzicht (na bewerken)")
        wait_until(page, lambda: "Bijgewerkt via test" in text_of(page, '#placementDrawerTabContent'))
        click_or_fail(page, failures, '#placementDrawer [data-action="close-modal"]', "placements: sluitknop van de drawer (na bewerken)")
        wait_until(page, lambda: page.query_selector('#placementDrawer.show') is None)

        # ---- Verwijderen: verkeerd ID, 409 met detail.code, daarna het juiste ID ----
        wait_until(page, lambda: page.query_selector('[data-action="confirm-delete-placement"][data-id="4"]') is not None)
        click_or_fail(page, failures, '[data-action="confirm-delete-placement"][data-id="4"]', "placements: verwijderknop op plaatsing #4")
        wait_until(page, lambda: page.query_selector('#placementDeleteModal') is not None)
        fill_or_fail(page, failures, '#placementDeleteModal input[id^="confirm_"]', "44", "placements: verkeerde getypte bevestiging")
        if is_disabled(page, '#placementDeleteModal .btn-outline-danger') is not True:
            failures.append("placements: verwijderknop stond aan bij een foutieve getypte bevestiging")
        fill_or_fail(page, failures, '#placementDeleteModal input[id^="confirm_"]', "4", "placements: juiste getypte bevestiging")
        if not wait_for_enabled(page, '#placementDeleteModal .btn-outline-danger', True):
            failures.append("placements: verwijderknop bleef uit na de juiste getypte bevestiging")
        deletes_before = len(PLACEMENTS_STATE["deletes"])
        click_or_fail(page, failures, '#placementDeleteModal .btn-outline-danger', "placements: 'Verwijderen' (eerste poging, 409)")
        if not wait_for_calls(page, PLACEMENTS_STATE["deletes"], deletes_before + 1):
            failures.append("placements: eerste verwijderpoging riep de DELETE-route niet aan")
        wait_for_text(page, '#placementDeleteAlert', 'kan op dit moment niet verwijderd worden')
        conflict_text = text_of(page, '#placementDeleteAlert')
        if "kan op dit moment niet verwijderd worden" not in conflict_text:
            failures.append(f"placements: de 409 op verwijderen toonde niet de detail.code-melding -- kreeg {conflict_text!r}")
        if page.query_selector('#placementDeleteModal.show') is None:
            failures.append("placements: de modal sloot na een 409 in plaats van open te blijven")
        click_or_fail(page, failures, '#placementDeleteModal .btn-outline-danger', "placements: 'Verwijderen' (tweede poging)")
        if not wait_for_calls(page, PLACEMENTS_STATE["deletes"], deletes_before + 2):
            failures.append("placements: tweede verwijderpoging riep de DELETE-route niet aan")
        wait_until(page, lambda: page.query_selector('#placementDeleteModal.show') is None)
        wait_until(page, lambda: page.query_selector('[data-action="confirm-delete-placement"][data-id="4"]') is None)

        # Elk paneel van de vorige stappen moet dicht zijn voordat de
        # 500-test begint: een mutant die een modal open laat, laat een
        # kaal retry.click() hieronder anders 30s hangen en gooit de
        # failure-lijst weg in plaats van de fout te melden (code-reviewer
        # op 1212e07).
        page.keyboard.press('Escape')
        wait_until(page, lambda: page.query_selector('.modal.show, .offcanvas.show') is None)

        # ---- 500 met retry ----
        PLACEMENTS_STATE["mode"] = "error"
        page.select_option('#placementStatusFilter', 'concept')
        wait_for_text(page, '#placementsBody', "probeer opnieuw")
        err_text = text_of(page, '#placementsBody')
        if "probeer opnieuw" not in err_text.lower():
            failures.append(f"placements: 500 toonde geen foutstaat met retrylink -- kreeg {err_text[:200]!r}")
        PLACEMENTS_STATE["mode"] = "ok"
        retry = page.query_selector('#placementsBody a')
        if retry is None:
            failures.append("placements: geen retrylink gevonden om van de 500 te herstellen")
        else:
            try:
                retry.click(timeout=6000)
            except Exception as exc:
                failures.append(f"placements: retrylink niet klikbaar binnen 6000ms ({exc})")
            else:
                wait_until(page, lambda: "probeer opnieuw" not in text_of(page, '#placementsBody').lower())
                recovered_placements = text_of(page, '#placementsBody')
                if "kon niet laden" in recovered_placements.lower() or "probeer opnieuw" in recovered_placements.lower():
                    failures.append(f"placements: herstelde niet na de retry -- kreeg {recovered_placements[:200]!r}")
        page.select_option('#placementStatusFilter', '')

        # 409/422/500 loggen zichzelf ook als console error; die grens gaat
        # er hierna overheen, zoals bij Bewaartermijnen en Toestemmingen.
        new_errors = [e for e in console_errors[errors_before:]
                      if "409 (Conflict)" not in e and "422" not in e and "500 (Internal Server Error)" not in e]
        if new_errors:
            failures.append(f"placements: {len(new_errors)} console error(s): {new_errors[:3]}")

        browser.close()

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS: Opdrachtgevers (list + tabbed drawer), Leads (inbox + unread filter + PATCH), "
          "Rapportage, Bewaartermijnen (lijst, generate, goedkeuren met getypte bevestiging, "
          "afwijzen, categoriebrede bulk met 409-mismatch, droogloop en 500 met retry), "
          "Toestemmingen/referral (§7.3.2: talentpool- en presentatiemodal met clientside-validatie "
          "en de juiste payload per richting, plus de drie referral-409-uitkomsten) en "
          "Plaatsingen (§7.3.3: lijst met 60 rijen naast de paginagrootte, server-side sortering en "
          "filters, drawer met Overzicht/Financieel/Marge, statuswissel gewoon en destructief naar "
          "geannuleerd, marge met null-invoer/herberekenen/ongeldig bedrag, aanmaken en bewerken met "
          "komma-decimalen en een onwijzigbare FK-set, verwijderen met een 409 en het juiste ID, en "
          "500 met retry) renderden allemaal correct, zonder console errors.")
    sys.exit(0)


if __name__ == "__main__":
    main()
