#!/usr/bin/env python3
"""
admin_ui_check.py — WS5 stap 3 proof: website/admin/js/ui.js doet wat het
belooft, in een echte browser tegen gestubde routes (example.com/
example.invalid, geen echte PII, geen echt netwerk).

Per paneelpad (Bootstrap uit de gevendorde tabler.min.js, én het vangnet
zonder Bootstrap) wordt hetzelfde gecontroleerd:
  1. ui.modal() opent, met role/aria-modal/aria-labelledby op de echte titel.
  2. De focus zit binnen het paneel.
  3. Focustrap: Tab vanaf het laatste element springt terug naar het eerste,
     Shift+Tab vanaf het eerste naar het laatste.
  4. Het paneel ligt boven zijn eigen backdrop (z-index).
  5. Escape sluit.
  6. Na sluiten staat de focus terug op het element dat het paneel opende.
  7. Klikken naast het paneel sluit het.
  8. confirmText blokkeert de destructieve knop tot de tekst letterlijk
     overgetypt is.
  9. ui.drawer() opent, ligt boven zijn backdrop, en sluit.

Daarnaast eenmalig:
  - ui.table() sorteert tekst, getallen en een numerieke string in de goede
    volgorde, en zet aria-sort op de juiste kolomkop.
  - ui.table({serverSort:true}) sorteert juist NIET zelf: een klik op de kop
    roept load() opnieuw aan met sortKey/sortDir en laat de volgorde van de
    route staan (§7.2a, BV10). Plus de lege staat en de foutstaat met retry.
  - ui.confirm() met een eigen body en onConfirm: de aanroeper leest zijn
    notitieveld uit terwijl het paneel nog staat.
  - handle.button(rol), handle.setBusy() en handle.syncGate(): spinner plus
    disabled op de handelende knop, daarna de oorspronkelijke tekst terug,
    en een bewust vergrendelde knop (data-gsp-lock) die door de getypte
    bevestiging noch door setBusy(false) weer aangaat.
  - De getypte bevestiging: focus gaat bij openen naar het veld, "Komt niet
    overeen" verschijnt met aria-live zodra er iets fout getypt is, en Enter
    voert de handeling alleen uit als de knop op dat moment aan staat.
  - Een controle op de focustrap-probe zelf: op een paneel zonder trap moet
    diezelfde probe "niet getrapt" melden. Zo faalt een kapotte trap met een
    duidelijke regel in plaats van met een timeout.
  - Integratie op het paneel zelf: de leaddetailmodal opent vanuit een
    rijklik en Escape brengt de focus terug naar die rij; het
    Opdrachtgevers-detailpaneel opent als Offcanvas met een tablist.
  - De computed tekstkleur van een tabelcel met .a-cell-name (wit) en met
    .a-soft/.a-meta (--navy-200). Tablers eigen celregel is specifieker dan
    een losse klasse en overschreef die twee stil; admin.css zet daarom ook
    --tblr-table-color. Deze twee asserties bewaken dat.

Waarom Python en geen scripts/test_admin_ui.mjs: in deze repo staat
Playwright alleen als Python-pakket (node heeft geen jsdom en geen
playwright), en de twee bestaande browsertests van het adminpaneel
(admin_sections_check.py, admin_pagination_check.py) zijn ook Python.

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


FOCUSABLE = ("a[href],button:not([disabled]),input:not([disabled]),"
             "select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex='-1'])")

# Zet de focus op het eerste of laatste focusbare element binnen `sel`.
FOCUS_EDGE = """([sel, which]) => {
  const el = document.querySelector(sel);
  const items = el.querySelectorAll(%s);
  (which === 'first' ? items[0] : items[items.length - 1]).focus();
  return items.length;
}""" % json.dumps(FOCUSABLE)

STACKING = """(sel) => {
  const el = document.querySelector(sel);
  const bd = document.querySelector('.modal-backdrop, .offcanvas-backdrop');
  const z = (n) => n ? parseInt(getComputedStyle(n).zIndex, 10) || 0 : null;
  return { panel: z(el), backdrop: z(bd) };
}"""

TABLE_FIXTURE = """() => {
  const host = document.createElement('div');
  host.id = 'uiTestTableHost';
  host.innerHTML =
    '<table id="uiTestTable"><thead id="uiTestHead"><tr>' +
    '<th data-sort-key="naam">Naam</th><th data-sort-key="score">Score</th>' +
    '</tr></thead><tbody id="uiTestBody"></tbody></table>';
  document.querySelector('.page-body').appendChild(host);
  const rows = [
    { naam: 'Charlie', score: 2 },
    { naam: 'Alfa', score: 10 },
    { naam: 'Bravo', score: 9 },
  ];
  window.__uiTable = ui.table({
    tbody: '#uiTestBody',
    thead: '#uiTestHead',
    cols: [
      { key: 'naam', label: 'Naam', sortable: true, type: 'text' },
      { key: 'score', label: 'Score', sortable: true, type: 'number', value: (r) => r.score },
    ],
    load: async () => ({ items: rows, total: rows.length }),
    render: (r) => GSP.html`<tr><td>${r.naam}</td><td>${r.score}</td></tr>`,
  });
  return window.__uiTable.reload().then(() => 'ready');
}"""

# Tweede tabel, met serverSort: de "server" geeft altijd dezelfde twee
# rijen terug, dus elke verandering in de volgorde zou client-side
# hersorteren zijn -- precies wat serverSort niet mag doen. __srvCalls legt
# vast wat load() als sorteerstaat meekreeg.
SERVER_SORT_FIXTURE = """() => {
  const host = document.createElement('div');
  host.id = 'uiSrvHost';
  host.innerHTML =
    '<table><thead id="uiSrvHead"><tr><th data-sort-key="naam">Naam</th></tr></thead>' +
    '<tbody id="uiSrvBody"></tbody></table>';
  document.querySelector('.page-body').appendChild(host);
  window.__srvCalls = [];
  window.__srvMode = 'ok';
  window.__srvTable = ui.table({
    tbody: '#uiSrvBody',
    thead: '#uiSrvHead',
    serverSort: true,
    empty: 'Nog geen rijen.',
    cols: [{ key: 'naam', label: 'Naam', sortable: true }],
    load: async (state) => {
      window.__srvCalls.push({ sortKey: state.sortKey, sortDir: state.sortDir });
      if (window.__srvMode === 'error') throw new Error('stuk');
      if (window.__srvMode === 'empty') return { items: [], total: 0 };
      return { items: [{ naam: 'van de server' }, { naam: 'in deze volgorde' }], total: 2 };
    },
    render: (r) => GSP.html`<tr><td>${r.naam}</td></tr>`,
  });
  return window.__srvTable.reload().then(() => 'ready');
}"""

# Een destructieve modal met een bewust vergrendelde knop, plus de
# getypte bevestiging: de combinatie waar S2 over ging.
LOCK_FIXTURE = """() => {
  window.__lockRan = false;
  window.__lock = ui.modal({
    id: 'uiLockModal',
    title: 'Wissen',
    body: GSP.html`<p>Dit kan niet ongedaan gemaakt worden.</p>`,
    confirmText: 'WIS',
    danger: { label: 'Wissen', keepOpen: true, onClick: () => { window.__lockRan = true; } },
  });
  const b = window.__lock.button('danger');
  b.disabled = true;
  b.dataset.gspLock = '1';
  return 'ready';
}"""

# Een paneel zonder focustrap, om te bewijzen dat de probe een ontbrekende
# trap ook echt ziet.
CONTROL_PANEL = """() => {
  const d = document.createElement('div');
  d.id = 'uiTestControlPanel';
  d.innerHTML = '<button>een</button><button>twee</button>';
  document.querySelector('.page-body').appendChild(d);
}"""


def wait_class(page, sel, cls, present=True, timeout=2000):
    """Wacht tot `sel` de klasse wel/niet heeft. Een Offcanvas schuift in en
    uit met een transitie, dus `show` staat er pas na afloop op."""
    step = 50
    waited = 0
    while waited < timeout:
        has = page.evaluate("([s, c]) => !!document.querySelector(s)?.classList.contains(c)", [sel, cls])
        if has == present:
            return True
        page.wait_for_timeout(step)
        waited += step
    return False


def trap_holds(page, sel, shift=False):
    """True als de focus binnen `sel` blijft na Tab vanaf de rand."""
    page.evaluate(FOCUS_EDGE, [sel, "first" if shift else "last"])
    page.keyboard.press("Shift+Tab" if shift else "Tab")
    page.wait_for_timeout(120)
    return page.evaluate(
        "(sel) => !!document.querySelector(sel)?.contains(document.activeElement)", sel)


def panel_assertions(page, failures, label, suffix):
    """De negen paneelasserties, uitgevoerd op één van de twee paden."""
    mid = "uiTestModal" + suffix
    did = "uiTestDrawer" + suffix
    cid = "uiTestConfirm" + suffix
    tag = f"[{label}] "

    page.evaluate("""([mid]) => {
      const opener = document.querySelector('.page-wrapper header a.btn');
      opener.id = 'uiTestOpener';
      opener.focus();
      window.__handle = ui.modal({
        id: mid,
        title: 'Testpaneel',
        body: GSP.html`<p>Inhoud</p><input id="uiTestInput" type="text">`,
        secondary: { label: 'Annuleren' },
        primary: { label: 'Opslaan' },
      });
    }""", [mid])
    page.wait_for_timeout(200)
    sel = "#" + mid

    if not page.evaluate("(s) => !!document.querySelector(s)?.classList.contains('show')", sel):
        failures.append(tag + "modal: opende niet")
    for attr, expected in (("role", "dialog"), ("aria-modal", "true")):
        got = page.get_attribute(sel, attr)
        if got != expected:
            failures.append(f"{tag}modal: {attr} is {got!r}, verwacht {expected!r}")
    if page.get_attribute(sel, "aria-label") is not None:
        failures.append(tag + "modal: aria-label bleef naast aria-labelledby staan")
    labelled = page.get_attribute(sel, "aria-labelledby")
    if not labelled or page.eval_on_selector(f"#{labelled}", "el => el.textContent") != "Testpaneel":
        failures.append(f"{tag}modal: aria-labelledby wijst niet naar de titel (kreeg {labelled!r})")
    if not page.evaluate("(s) => !!document.querySelector(s)?.contains(document.activeElement)", sel):
        failures.append(tag + "modal: focus staat niet binnen het paneel na openen")

    if not trap_holds(page, sel):
        failures.append(tag + "modal: Tab vanaf het laatste element verliet het paneel")
    if not trap_holds(page, sel, shift=True):
        failures.append(tag + "modal: Shift+Tab vanaf het eerste element verliet het paneel")

    z = page.evaluate(STACKING, sel)
    if z["backdrop"] is None:
        failures.append(tag + "modal: geen backdrop gevonden")
    elif not (z["panel"] > z["backdrop"]):
        failures.append(f"{tag}modal: paneel z-index {z['panel']} ligt niet boven backdrop {z['backdrop']}")

    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    if page.evaluate("(s) => document.querySelector(s).classList.contains('show')", sel):
        failures.append(tag + "modal: Escape sloot het paneel niet")
    if page.evaluate("() => document.activeElement && document.activeElement.id") != "uiTestOpener":
        failures.append(tag + "modal: focus keerde niet terug naar de opener")

    # Klik-buiten sluit.
    page.evaluate("""([mid]) => {
      document.querySelector('.page-wrapper header a.btn').focus();
      ui.modal({ id: mid, title: 'Klik buiten', body: GSP.html`<p>x</p>` });
    }""", [mid])
    page.wait_for_timeout(200)
    page.mouse.click(6, 6)
    page.wait_for_timeout(250)
    if page.evaluate("(s) => document.querySelector(s).classList.contains('show')", sel):
        failures.append(tag + "modal: klikken naast het paneel sloot het niet")

    # confirmText.
    page.evaluate("""([cid]) => {
      window.__confirmed = false;
      ui.modal({
        id: cid,
        title: 'Verwijderen',
        body: GSP.html`<p>Dit kan niet ongedaan gemaakt worden.</p>`,
        confirmText: 'VERWIJDER',
        danger: { label: 'Definitief verwijderen', onClick: () => { window.__confirmed = true; } },
      });
    }""", [cid])
    page.wait_for_timeout(200)
    danger = f"#{cid} .btn-outline-danger"
    if not page.eval_on_selector(danger, "el => el.disabled"):
        failures.append(tag + "confirmText: de destructieve knop stond meteen aan")
    if page.evaluate("(s) => document.activeElement === document.querySelector(s + ' input[type=text]')",
                     "#" + cid) is not True:
        failures.append(tag + "confirmText: de focus ging niet naar het bevestigingsveld bij openen")
    box = page.query_selector(f"#{cid} input[type=text]")
    box.fill("verwijder")
    page.wait_for_timeout(150)
    if not page.eval_on_selector(danger, "el => el.disabled"):
        failures.append(tag + "confirmText: knop ging aan bij een niet-kloppende tekst")
    box.fill("VERWIJDER")
    page.wait_for_timeout(150)
    if page.eval_on_selector(danger, "el => el.disabled"):
        failures.append(tag + "confirmText: knop bleef uit terwijl de tekst klopte")
    page.click(danger)
    page.wait_for_timeout(200)
    if not page.evaluate("() => window.__confirmed"):
        failures.append(tag + "confirmText: onClick van de destructieve knop liep niet")
    if page.evaluate("(s) => document.querySelector(s).classList.contains('show')", "#" + cid):
        failures.append(tag + "confirmText: paneel bleef open na bevestigen")

    # Drawer.
    page.evaluate("""([did]) => {
      window.__drawer = ui.drawer({
        id: did,
        title: 'Detailpaneel',
        tabs: [{ key: 'info', label: 'Info' }, { key: 'meer', label: 'Meer' }],
        body: GSP.html`<p>Drawerinhoud</p>`,
      });
    }""", [did])
    dsel = "#" + did
    if not wait_class(page, dsel, "show", True):
        failures.append(tag + "drawer: opende niet")
    if page.get_attribute(dsel, "aria-modal") != "true":
        failures.append(tag + "drawer: aria-modal ontbreekt")
    tabs_state = page.eval_on_selector_all(
        f"{dsel} [role=tab]", "els => els.map(e => e.getAttribute('aria-selected'))")
    if tabs_state != ["true", "false"]:
        failures.append(f"{tag}drawer: aria-selected was {tabs_state!r}, verwacht ['true','false']")
    dz = page.evaluate(STACKING, dsel)
    if dz["backdrop"] is None:
        failures.append(tag + "drawer: geen backdrop gevonden")
    elif not (dz["panel"] > dz["backdrop"]):
        failures.append(f"{tag}drawer: paneel z-index {dz['panel']} ligt niet boven backdrop {dz['backdrop']}")
    page.evaluate("() => window.__drawer.close()")
    if not wait_class(page, dsel, "show", False):
        failures.append(tag + "drawer: sloot niet")


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FAIL: playwright not installed")
        sys.exit(1)

    port = start_server()
    failures = []
    console_errors = []
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

        page = context.new_page()
        page.on("console", lambda m: console_errors.append(m.text)
                if m.type == "error" and "favicon" not in m.text.lower()
                and "net::ERR_FAILED" not in m.text else None)
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

        page.goto(f"http://127.0.0.1:{port}/admin/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1000)

        # Pad 1: Bootstrap uit de gevendorde tabler.min.js, doorgezet naar
        # window.bootstrap door js/vendor-fallback-tabler-js.js.
        if not page.evaluate("() => !!(window.bootstrap && window.bootstrap.Modal)"):
            failures.append("window.bootstrap ontbreekt; vendor-fallback-tabler-js.js zet de "
                            "bootstrap-namespace van window.tabler niet door")
        panel_assertions(page, failures, "bootstrap", "Bs")

        # Controle op de probe zelf: een paneel zonder trap moet als
        # "niet getrapt" gemeld worden, anders bewijst de trap-assertie niets.
        page.evaluate(CONTROL_PANEL)
        page.wait_for_timeout(150)
        if trap_holds(page, "#uiTestControlPanel"):
            failures.append("focustrap-probe: een paneel zonder trap werd toch als getrapt gezien; "
                            "de trap-asserties hierboven bewijzen dan niets")

        # ui.table.
        page.evaluate(TABLE_FIXTURE)
        page.wait_for_timeout(300)
        order0 = page.eval_on_selector_all("#uiTestBody tr td:first-child", "els => els.map(e => e.textContent)")
        if order0 != ["Charlie", "Alfa", "Bravo"]:
            failures.append(f"table: ongesorteerde volgorde was {order0!r}")
        if page.eval_on_selector_all("#uiTestHead th", "els => els.map(e => e.getAttribute('aria-sort'))") != ["none", "none"]:
            failures.append("table: aria-sort startte niet op 'none'")

        page.click('#uiTestHead th[data-sort-key="naam"]')
        page.wait_for_timeout(200)
        if page.eval_on_selector_all("#uiTestBody tr td:first-child", "els => els.map(e => e.textContent)") != ["Alfa", "Bravo", "Charlie"]:
            failures.append("table: oplopend sorteren op tekst klopte niet")
        if page.get_attribute('#uiTestHead th[data-sort-key="naam"]', "aria-sort") != "ascending":
            failures.append("table: aria-sort werd niet op 'ascending' gezet")

        page.click('#uiTestHead th[data-sort-key="naam"]')
        page.wait_for_timeout(200)
        if page.eval_on_selector_all("#uiTestBody tr td:first-child", "els => els.map(e => e.textContent)") != ["Charlie", "Bravo", "Alfa"]:
            failures.append("table: aflopend sorteren klopte niet")
        if page.get_attribute('#uiTestHead th[data-sort-key="naam"]', "aria-sort") != "descending":
            failures.append("table: aria-sort werd niet op 'descending' gezet")

        # 10 moet ná 9 komen, niet ervoor: numeriek, niet als tekst.
        page.click('#uiTestHead th[data-sort-key="score"]')
        page.wait_for_timeout(200)
        scores = page.eval_on_selector_all("#uiTestBody tr td:last-child", "els => els.map(e => e.textContent)")
        if scores != ["2", "9", "10"]:
            failures.append(f"table: numeriek sorteren gaf {scores!r}, verwacht ['2','9','10']")
        if page.get_attribute('#uiTestHead th[data-sort-key="naam"]', "aria-sort") != "none":
            failures.append("table: de vorige kolom hield zijn aria-sort vast")

        # ui.table met serverSort: een klik op de kolomkop sorteert niet
        # zelf maar vraagt de route opnieuw, met sort/order erin, en zet
        # aria-sort op de aangeklikte kop.
        page.evaluate(SERVER_SORT_FIXTURE)
        page.wait_for_timeout(300)
        page.click('#uiSrvHead th[data-sort-key="naam"]')
        page.wait_for_timeout(300)
        calls = page.evaluate("() => window.__srvCalls")
        if calls != [{"sortKey": None, "sortDir": None}, {"sortKey": "naam", "sortDir": "asc"}]:
            failures.append(f"table serverSort: load() kreeg {calls!r}, verwacht een tweede aanroep met naam/asc")
        srv_order = page.eval_on_selector_all("#uiSrvBody tr td", "els => els.map(e => e.textContent)")
        if srv_order != ["van de server", "in deze volgorde"]:
            failures.append(f"table serverSort: de rijen zijn client-side hersorteerd -- {srv_order!r}")
        if page.get_attribute('#uiSrvHead th[data-sort-key="naam"]', "aria-sort") != "ascending":
            failures.append("table serverSort: aria-sort werd niet gezet")

        # Lege staat en foutstaat van ui.table.
        page.evaluate("() => { window.__srvMode = 'empty'; return window.__srvTable.reload(); }")
        page.wait_for_timeout(300)
        empty_text = page.eval_on_selector("#uiSrvBody", "el => el.textContent") or ""
        if "Nog geen rijen" not in empty_text:
            failures.append(f"table: lege staat toonde {empty_text.strip()[:80]!r}, verwacht de meegegeven tekst")
        page.evaluate("() => { window.__srvMode = 'error'; return window.__srvTable.reload(); }")
        page.wait_for_timeout(300)
        err_text = page.eval_on_selector("#uiSrvBody", "el => el.textContent") or ""
        if "probeer opnieuw" not in err_text.lower():
            failures.append(f"table: foutstaat mist de retrylink -- {err_text.strip()[:80]!r}")
        page.evaluate("() => { window.__srvMode = 'ok'; }")
        page.click("#uiSrvBody a")
        page.wait_for_timeout(300)
        if "probeer opnieuw" in (page.eval_on_selector("#uiSrvBody", "el => el.textContent") or "").lower():
            failures.append("table: de retrylink herstelde de tabel niet")

        # ui.confirm met een eigen body en onConfirm: de aanroeper leest
        # zijn veld uit terwijl het paneel nog staat.
        page.evaluate("""() => {
          window.__confirmNote = null;
          window.__confirmAnswer = null;
          ui.confirm('Weet je het zeker?', {
            title: 'Afwijzen',
            danger: false,
            confirmLabel: 'Afwijzen',
            body: GSP.html`<textarea id="uiConfirmNote"></textarea>`,
            onConfirm: () => { window.__confirmNote = document.getElementById('uiConfirmNote').value; },
          }).then((ok) => { window.__confirmAnswer = ok; });
        }""")
        page.wait_for_timeout(250)
        page.fill("#uiConfirmNote", "een notitie")
        page.click("#adminConfirmModal .btn-primary")
        page.wait_for_timeout(300)
        if page.evaluate("() => window.__confirmNote") != "een notitie":
            failures.append("ui.confirm: onConfirm kon het eigen veld niet meer uitlezen")
        if page.evaluate("() => window.__confirmAnswer") is not True:
            failures.append("ui.confirm: de Promise loste niet op true op na bevestigen")

        # data-gsp-lock: een knop die de aanroeper bewust heeft
        # uitgeschakeld (cap overschreden, lijst niet geladen, bulk al
        # verwerkt) mag door de getypte bevestiging niet weer aangaan --
        # dat is het pad waarlangs een onomkeerbare handeling anders alsnog
        # bereikbaar wordt.
        page.evaluate(LOCK_FIXTURE)
        page.wait_for_timeout(200)
        page.fill("#uiLockModal input[type=text]", "WIS")
        page.wait_for_timeout(200)
        if not page.eval_on_selector("#uiLockModal .btn-outline-danger", "el => el.disabled"):
            failures.append("gspLock: de getypte bevestiging zette een vergrendelde knop weer aan")
        page.evaluate("() => window.__lock.setBusy(true)")
        page.evaluate("() => window.__lock.setBusy(false)")
        page.wait_for_timeout(200)
        if not page.eval_on_selector("#uiLockModal .btn-outline-danger", "el => el.disabled"):
            failures.append("gspLock: setBusy(false) hief het slot op")
        page.evaluate("() => { const b = window.__lock.button('danger');"
                      " delete b.dataset.gspLock; window.__lock.syncGate(); }")
        page.wait_for_timeout(200)
        if page.eval_on_selector("#uiLockModal .btn-outline-danger", "el => el.disabled"):
            failures.append("syncGate: de knop bleef uit terwijl het slot eraf was en de tekst klopte")

        # "Komt niet overeen" verschijnt pas bij een foute invoer.
        page.fill("#uiLockModal input[type=text]", "wis")
        page.wait_for_timeout(200)
        mismatch = page.eval_on_selector("#uiLockModal .a-confirm-mismatch", "el => el.textContent") or ""
        if "Komt niet overeen" not in mismatch:
            failures.append(f"bevestiging: geen 'Komt niet overeen'-regel bij foute invoer -- {mismatch!r}")
        if page.eval_on_selector("#uiLockModal .a-confirm-mismatch",
                                 "el => el.getAttribute('aria-live')") != "polite":
            failures.append("bevestiging: de mismatchregel heeft geen aria-live")

        # Enter in het veld voert de handeling alleen uit als de knop aan staat.
        page.focus("#uiLockModal input[type=text]")
        page.keyboard.press("Enter")
        page.wait_for_timeout(250)
        if page.evaluate("() => window.__lockRan"):
            failures.append("bevestiging: Enter voerde de handeling uit terwijl de knop uit stond")
        page.fill("#uiLockModal input[type=text]", "WIS")
        page.wait_for_timeout(150)
        page.focus("#uiLockModal input[type=text]")
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        if not page.evaluate("() => window.__lockRan"):
            failures.append("bevestiging: Enter voerde de handeling niet uit terwijl de knop aan stond")
        page.evaluate("() => window.__lock.close()")
        page.wait_for_timeout(250)

        # setBusy(): spinner en disabled op de handelende knop, en daarna
        # weer terug naar de oorspronkelijke tekst.
        page.evaluate("""() => {
          window.__busy = ui.modal({
            id: 'uiBusyModal', title: 'Bezig',
            body: GSP.html`<p>x</p>`,
            secondary: { label: 'Annuleren' },
            primary: { label: 'Opslaan', keepOpen: true },
          });
          window.__busy.setBusy(true);
        }""")
        page.wait_for_timeout(200)
        if not page.eval_on_selector("#uiBusyModal .btn-primary", "el => el.disabled"):
            failures.append("setBusy: de primaire knop ging niet op disabled")
        if page.query_selector("#uiBusyModal .btn-primary .fa-spinner") is None:
            failures.append("setBusy: er kwam geen spinner op de primaire knop")
        page.evaluate("() => window.__busy.setBusy(false)")
        page.wait_for_timeout(200)
        if page.eval_on_selector("#uiBusyModal .btn-primary", "el => el.disabled"):
            failures.append("setBusy(false): de knop bleef disabled")
        if (page.eval_on_selector("#uiBusyModal .btn-primary", "el => el.textContent") or "").strip() != "Opslaan":
            failures.append("setBusy(false): de oorspronkelijke knoptekst kwam niet terug")
        if page.evaluate("() => !window.__busy.button('primary')"):
            failures.append("handle.button('primary') gaf geen element terug")
        page.evaluate("() => window.__busy.close()")
        page.wait_for_timeout(200)

        # Integratie: de leaddetailmodal van het paneel zelf.
        page.click('.nav-link[data-section="leads"]')
        page.wait_for_timeout(800)
        page.evaluate("() => document.querySelector('#section-leads table tbody tr').id = 'uiTestLeadRow'")
        page.click("#uiTestLeadRow")
        page.wait_for_timeout(700)
        if not page.evaluate("() => document.getElementById('adminModalOverlay').classList.contains('show')"):
            failures.append("integratie: de leaddetailmodal opende niet via ui.modal")
        if not page.evaluate("() => document.getElementById('adminModalOverlay').contains(document.activeElement)"):
            failures.append("integratie: focus zat niet in de leaddetailmodal")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        if page.evaluate("() => document.getElementById('adminModalOverlay').classList.contains('show')"):
            failures.append("integratie: Escape sloot de leaddetailmodal niet")
        if page.evaluate("() => document.activeElement && document.activeElement.id") != "uiTestLeadRow":
            failures.append("integratie: focus keerde niet terug naar de aangeklikte rij")

        # Tabelcelkleuren. Tablers `.table > :not(caption) > * > *` (0,1,1)
        # wint van een losse klasse (0,1,0) en zette deze cellen terug op
        # --tblr-table-color (navy-100). Gemeten op de echte tabel, niet op
        # een losse div, want de specificiteit is nu juist het punt.
        rgb = lambda hexv: "rgb(%d, %d, %d)" % tuple(int(hexv[i:i + 2], 16) for i in (1, 3, 5))
        # De gedeelde route-stub geeft voor users en jobs een lege lijst, dus
        # de rijen komen hier uit de echte renderers met een vaste fixture.
        # Dat is precies dezelfde markup als in productie. De fixture gaat er
        # ná het navigeren in, want het eerste bezoek aan een sectie start de
        # loader die de tabel anders weer leegmaakt.
        FIXTURES = {
            "users": """() => Admin.renderUsers({ items: [{ id: 1,
                full_name: 'Celkleur Fixture', email: 'cel@example.invalid',
                role: 'admin', is_verified: true,
                created_at: '2026-01-01T00:00:00Z' }] })""",
            "jobs": """() => Admin.renderJobs({ items: [{ id: 1,
                title: 'Celkleur Fixture', company_name: 'Example Engineering B.V.',
                application_count: 0, status: 'open' }] })""",
        }
        for section, sel, expect_token, label in [
            ("users", "#section-users table tbody tr td.a-cell-name", "--white", "naamkolom"),
            ("users", "#section-users table tbody tr td.a-meta", "--navy-200", "tijdstempelkolom"),
            ("jobs", "#section-jobs table tbody tr td.a-cell-name", "--white", "titelkolom"),
            ("jobs", "#section-jobs table tbody tr td.a-soft", "--navy-200", "klantkolom"),
        ]:
            page.evaluate("(s) => navigateTo(s)", section)
            page.wait_for_timeout(700)
            page.evaluate(FIXTURES[section])
            page.wait_for_timeout(150)
            node = page.query_selector(sel)
            if node is None:
                failures.append(f"celkleur: geen {label} gevonden in #{section} ({sel})")
                continue
            got = page.eval_on_selector(sel, "el => getComputedStyle(el).color")
            want_hex = page.evaluate(
                "(tok) => getComputedStyle(document.documentElement).getPropertyValue(tok).trim()",
                expect_token)
            want = rgb(want_hex)
            if got != want:
                failures.append(
                    f"celkleur: {label} in #{section} is {got}, verwacht {want} ({expect_token}). "
                    "Waarschijnlijk wint Tablers celregel weer van de klasse; zet "
                    "--tblr-table-color mee in admin.css.")

        # Integratie: het Opdrachtgevers-detailpaneel is een Offcanvas met tablist.
        page.click('.nav-link[data-section="clients"]')
        page.wait_for_timeout(900)
        page.click("#section-clients table tbody tr")
        wait_class(page, "#clientDrawer", "show", True)
        page.wait_for_timeout(400)
        if not page.evaluate("() => document.getElementById('clientDrawer')?.classList.contains('offcanvas')"):
            failures.append("integratie: het Opdrachtgeversdetail is geen Offcanvas")
        # Zes sinds §7.3.4 (de tab Pipeline erbij, tussen Vacatures en
        # Notities/Activiteit).
        if page.eval_on_selector_all('#clientDrawer [role=tab]', "els => els.length") != 6:
            failures.append("integratie: de drawer heeft geen tablist met zes tabbladen")
        if page.eval_on_selector('#clientDrawer [role=tab][data-tab=info]', "el => el.getAttribute('aria-selected')") != "true":
            failures.append("integratie: het Info-tabblad staat niet op aria-selected=true")
        page.click('#clientDrawer [data-action="client-tab"][data-tab="contacts"]')
        page.wait_for_timeout(600)
        if page.eval_on_selector('#clientDrawer [role=tab][data-tab=contacts]', "el => el.getAttribute('aria-selected')") != "true":
            failures.append("integratie: aria-selected verhuisde niet mee met het gekozen tabblad")
        page.click('#clientDrawer [data-action="close-modal"]')
        page.wait_for_timeout(300)

        # Pad 2: hetzelfde zonder Bootstrap, zodat het vangnet in ui.js niet
        # ongemerkt kan verrotten. ui.js leest window.bootstrap pas op het
        # moment van openen, dus weghalen is genoeg.
        page.evaluate("() => { window.__bs = window.bootstrap; delete window.bootstrap; }")
        if page.evaluate("() => !!window.bootstrap"):
            failures.append("vangnetpad: window.bootstrap was niet weg te halen, het pad is niet getest")
        panel_assertions(page, failures, "vangnet", "Fb")
        page.evaluate("() => { window.bootstrap = window.__bs; }")

        browser.close()

    if console_errors:
        failures.append(f"{len(console_errors)} console error(s): {console_errors[:3]}")

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("PASS: modal, drawer en confirmText voldoen op beide paden (Bootstrap en vangnet) "
          "aan focus, focustrap, stapeling, Escape en klik-buiten; ui.table sorteert tekst en "
          "getallen met aria-sort, laat serverSort aan de route en heeft een lege en een "
          "foutstaat; ui.confirm draagt een eigen body met onConfirm; setBusy zet en herstelt "
          "de knoppen; de leadmodal en het Opdrachtgeversdetail van het paneel zelf gedragen "
          "zich hetzelfde.")
    sys.exit(0)


if __name__ == "__main__":
    main()
