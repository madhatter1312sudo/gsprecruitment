#!/usr/bin/env python3
"""
admin_ui_check.py — WS5 stap 3 proof: website/admin/js/ui.js doet wat het
belooft, in een echte browser tegen gestubde routes (example.com/
example.invalid, geen echte PII, geen echt netwerk).

Zeven asserties:
  1. ui.modal() opent en de focus zit binnen het paneel.
  2. Tab blijft binnen het paneel (focustrap): vanaf het laatste element
     springt Tab terug naar het eerste.
  3. Escape sluit het paneel.
  4. Na sluiten staat de focus terug op het element dat het paneel opende.
  5. confirmText blokkeert de destructieve knop tot de tekst letterlijk
     overgetypt is.
  6. ui.drawer() opent en sluit.
  7. ui.table() sorteert op een kolom en zet aria-sort op de kolomkop
     (ascending -> descending bij een tweede klik).

Plus een integratiecontrole op een echt paneel uit het adminpaneel zelf:
de leaddetailmodal opent vanuit een rijklik, en Escape brengt de focus
terug naar die rij.

Waarom Python en geen scripts/test_admin_ui.mjs: in deze repo staat
Playwright alleen als Python-pakket (node heeft geen jsdom en geen
playwright), en de twee bestaande browsertests van het adminpaneel
(admin_sections_check.py, admin_pagination_check.py) zijn ook Python. De
naam volgt die twee.

Exit 0 = alles goed, 1 = ten minste één assertie faalde.
"""
import importlib.util
import json
import re
import socket
import http.server
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBSITE = ROOT / "website"
CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH") or (
    "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
)

# De route-stub en het neppe JWT komen uit admin_sections_check.py, zodat er
# maar één set testdata is.
_spec = importlib.util.spec_from_file_location(
    "admin_sections_check", ROOT / "scripts" / "admin_sections_check.py")
_sections = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sections)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass


def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    httpd = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), lambda *a, **kw: _QuietHandler(*a, directory=str(WEBSITE), **kw))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return port


# Een tabel die alleen deze test gebruikt, met twee sorteerbare kolommen.
TABLE_FIXTURE = """
() => {
  const host = document.createElement('div');
  host.id = 'uiTestTableHost';
  host.innerHTML =
    '<table id="uiTestTable"><thead id="uiTestHead"><tr>' +
    '<th data-sort-key="naam">Naam</th><th data-sort-key="score">Score</th>' +
    '</tr></thead><tbody id="uiTestBody"></tbody></table>';
  document.querySelector('.page-body').appendChild(host);
  const rows = [
    { naam: 'Charlie', score: 2 },
    { naam: 'Alfa', score: 9 },
    { naam: 'Bravo', score: 5 },
  ];
  window.__uiTable = ui.table({
    tbody: '#uiTestBody',
    thead: '#uiTestHead',
    cols: [
      { key: 'naam', label: 'Naam', sortable: true },
      { key: 'score', label: 'Score', sortable: true, value: (r) => r.score },
    ],
    load: async () => ({ items: rows, total: rows.length }),
    render: (r) => GSP.html`<tr><td>${r.naam}</td><td>${r.score}</td></tr>`,
  });
  return window.__uiTable.reload().then(() => 'ready');
}
"""


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FAIL: playwright not installed")
        sys.exit(1)

    port = start_server()
    failures = []
    user = {"id": 1, "role": "admin", "email": "ui-check@example.invalid",
            "full_name": "UI Check", "is_verified": True}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM_PATH or None, headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_init_script(
            "try{localStorage.setItem('gsp_cookie_consent','true');"
            f"localStorage.setItem('gsp_token',{json.dumps(_sections.FAKE_JWT)});"
            f"localStorage.setItem('gsp_user',{json.dumps(json.dumps(user))});}}catch(e){{}}")
        context.route(re.compile(r"^https://api\.gsprecruitment\.nl/api/"), _sections.route_admin_api)
        context.route(
            re.compile(r"^https://(fonts\.googleapis\.com|fonts\.gstatic\.com|cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net)/"),
            lambda route, request: route.abort())

        console_errors = []
        page = context.new_page()
        page.on("console", lambda m: console_errors.append(m.text)
                if m.type == "error" and "favicon" not in m.text.lower()
                and "net::ERR_FAILED" not in m.text else None)
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

        page.goto(f"http://127.0.0.1:{port}/admin/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(900)

        # ---- 1..4: modal, focustrap, Escape, focus terug -----------------
        # De knop "View Site" in de header is de opener; die bestaat al en
        # blijft bestaan, dus de focus hoort er na sluiten op terug te staan.
        page.evaluate("""() => {
          const opener = document.querySelector('.page-wrapper header a.btn');
          opener.id = 'uiTestOpener';
          opener.focus();
          window.__handle = ui.modal({
            title: 'Testpaneel',
            body: GSP.html`<p>Inhoud</p><input id="uiTestInput" type="text">`,
            secondary: { label: 'Annuleren' },
            primary: { label: 'Opslaan' },
          });
        }""")
        page.wait_for_timeout(200)

        inside = page.evaluate(
            "() => !!document.getElementById('adminModalOverlay')?.contains(document.activeElement)")
        if not inside:
            failures.append("modal: focus staat niet binnen het paneel na openen")

        for attr, expected in (("role", "dialog"), ("aria-modal", "true")):
            got = page.get_attribute("#adminModalOverlay", attr)
            if got != expected:
                failures.append(f"modal: {attr} is {got!r}, verwacht {expected!r}")
        labelled = page.get_attribute("#adminModalOverlay", "aria-labelledby")
        if not labelled or page.eval_on_selector(f"#{labelled}", "el => el.textContent") != "Testpaneel":
            failures.append(f"modal: aria-labelledby wijst niet naar de titel (kreeg {labelled!r})")

        # Focustrap: vanaf het laatste element springt Tab naar het eerste.
        page.evaluate("""() => {
          const el = document.getElementById('adminModalOverlay');
          const items = el.querySelectorAll('a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex="-1"])');
          items[items.length - 1].focus();
        }""")
        page.keyboard.press("Tab")
        page.wait_for_timeout(150)
        still_inside = page.evaluate(
            "() => !!document.getElementById('adminModalOverlay')?.contains(document.activeElement)")
        if not still_inside:
            failures.append("modal: Tab vanaf het laatste element verliet het paneel (geen focustrap)")

        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
        if page.evaluate("() => document.getElementById('adminModalOverlay').classList.contains('show')"):
            failures.append("modal: Escape sloot het paneel niet")
        back = page.evaluate("() => document.activeElement && document.activeElement.id")
        if back != "uiTestOpener":
            failures.append(f"modal: focus keerde niet terug naar de opener (activeElement id={back!r})")

        # ---- 5: confirmText ---------------------------------------------
        page.evaluate("""() => {
          window.__confirmed = false;
          ui.modal({
            id: 'uiTestConfirmModal',
            title: 'Verwijderen',
            body: GSP.html`<p>Dit kan niet ongedaan gemaakt worden.</p>`,
            confirmText: 'VERWIJDER',
            danger: { label: 'Definitief verwijderen', onClick: () => { window.__confirmed = true; } },
          });
        }""")
        page.wait_for_timeout(200)
        danger = "#uiTestConfirmModal .btn-outline-danger"
        if not page.eval_on_selector(danger, "el => el.disabled"):
            failures.append("confirmText: de destructieve knop stond meteen aan")
        confirm_input = page.query_selector("#uiTestConfirmModal input[type=text]")
        confirm_input.fill("verwijder")
        page.wait_for_timeout(150)
        if not page.eval_on_selector(danger, "el => el.disabled"):
            failures.append("confirmText: knop ging aan bij een niet-kloppende tekst")
        confirm_input.fill("VERWIJDER")
        page.wait_for_timeout(150)
        if page.eval_on_selector(danger, "el => el.disabled"):
            failures.append("confirmText: knop bleef uit terwijl de tekst klopte")
        page.click(danger)
        page.wait_for_timeout(200)
        if not page.evaluate("() => window.__confirmed"):
            failures.append("confirmText: onClick van de destructieve knop liep niet")
        if page.evaluate("() => document.getElementById('uiTestConfirmModal').classList.contains('show')"):
            failures.append("confirmText: paneel bleef open na bevestigen")

        # ---- 6: drawer ---------------------------------------------------
        page.evaluate("""() => {
          window.__drawer = ui.drawer({
            id: 'uiTestDrawer',
            title: 'Detailpaneel',
            tabs: [{ key: 'info', label: 'Info' }, { key: 'meer', label: 'Meer' }],
            body: GSP.html`<p>Drawerinhoud</p>`,
          });
        }""")
        page.wait_for_timeout(250)
        if not page.evaluate("() => document.getElementById('uiTestDrawer').classList.contains('show')"):
            failures.append("drawer: opende niet")
        if page.get_attribute("#uiTestDrawer", "aria-modal") != "true":
            failures.append("drawer: aria-modal ontbreekt")
        tabs_ok = page.eval_on_selector_all(
            "#uiTestDrawer [role=tab]", "els => els.map(e => e.getAttribute('aria-selected'))")
        if tabs_ok != ["true", "false"]:
            failures.append(f"drawer: aria-selected op de tabs was {tabs_ok!r}, verwacht ['true','false']")
        page.evaluate("() => window.__drawer.close()")
        page.wait_for_timeout(250)
        if page.evaluate("() => document.getElementById('uiTestDrawer').classList.contains('show')"):
            failures.append("drawer: sloot niet")

        # ---- 7: ui.table sorteert en zet aria-sort -----------------------
        page.evaluate(TABLE_FIXTURE)
        page.wait_for_timeout(300)
        order0 = page.eval_on_selector_all("#uiTestBody tr td:first-child", "els => els.map(e => e.textContent)")
        if order0 != ["Charlie", "Alfa", "Bravo"]:
            failures.append(f"table: ongesorteerde volgorde was {order0!r}")
        sorts0 = page.eval_on_selector_all("#uiTestHead th", "els => els.map(e => e.getAttribute('aria-sort'))")
        if sorts0 != ["none", "none"]:
            failures.append(f"table: aria-sort startte op {sorts0!r}, verwacht ['none','none']")

        page.click('#uiTestHead th[data-sort-key="naam"]')
        page.wait_for_timeout(200)
        order1 = page.eval_on_selector_all("#uiTestBody tr td:first-child", "els => els.map(e => e.textContent)")
        if order1 != ["Alfa", "Bravo", "Charlie"]:
            failures.append(f"table: oplopend sorteren gaf {order1!r}")
        if page.get_attribute('#uiTestHead th[data-sort-key="naam"]', "aria-sort") != "ascending":
            failures.append("table: aria-sort werd niet op 'ascending' gezet")

        page.click('#uiTestHead th[data-sort-key="naam"]')
        page.wait_for_timeout(200)
        order2 = page.eval_on_selector_all("#uiTestBody tr td:first-child", "els => els.map(e => e.textContent)")
        if order2 != ["Charlie", "Bravo", "Alfa"]:
            failures.append(f"table: aflopend sorteren gaf {order2!r}")
        if page.get_attribute('#uiTestHead th[data-sort-key="naam"]', "aria-sort") != "descending":
            failures.append("table: aria-sort werd niet op 'descending' gezet")

        # Numerieke kolom moet numeriek sorteren, niet als tekst.
        page.click('#uiTestHead th[data-sort-key="score"]')
        page.wait_for_timeout(200)
        scores = page.eval_on_selector_all("#uiTestBody tr td:last-child", "els => els.map(e => e.textContent)")
        if scores != ["2", "5", "9"]:
            failures.append(f"table: numeriek sorteren gaf {scores!r}")
        if page.get_attribute('#uiTestHead th[data-sort-key="naam"]', "aria-sort") != "none":
            failures.append("table: de vorige kolom hield zijn aria-sort vast")

        # ---- Integratie: een echt paneel uit het adminpaneel -------------
        page.click('.nav-link[data-section="leads"]')
        page.wait_for_timeout(800)
        page.evaluate("() => document.querySelector('#section-leads table tbody tr').id = 'uiTestLeadRow'")
        page.click("#uiTestLeadRow")
        page.wait_for_timeout(700)
        if not page.evaluate("() => document.getElementById('adminModalOverlay').classList.contains('show')"):
            failures.append("integratie: de leaddetailmodal opende niet via ui.modal")
        if not page.evaluate(
                "() => document.getElementById('adminModalOverlay').contains(document.activeElement)"):
            failures.append("integratie: focus zat niet in de leaddetailmodal")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        if page.evaluate("() => document.getElementById('adminModalOverlay').classList.contains('show')"):
            failures.append("integratie: Escape sloot de leaddetailmodal niet")
        if page.evaluate("() => document.activeElement && document.activeElement.id") != "uiTestLeadRow":
            failures.append("integratie: focus keerde niet terug naar de aangeklikte rij")

        browser.close()

    if console_errors:
        failures.append(f"{len(console_errors)} console error(s): {console_errors[:3]}")

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS: ui.modal (focus binnen, trap, Escape, focus terug), confirmText, "
          "ui.drawer en ui.table (sorteren + aria-sort) werken, en de leaddetailmodal "
          "van het paneel zelf ook.")
    sys.exit(0)


if __name__ == "__main__":
    main()
