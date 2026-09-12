/* ============================================================
   GSP Recruitment — admin/js/ui.js
   Dunne ui-laag bovenop de Bootstrap 5-componenten die Tabler 1.4
   meelevert. Geen eigen componentbibliotheek: modal en drawer zijn een
   Bootstrap Modal respectievelijk Offcanvas, met de merkopmaak uit
   admin.css en de toegankelijkheidsafspraken op één plek.

   Bootstrap komt uit de gevendorde tabler.min.js: die UMD exporteert
   window.tabler met daarin de volledige bootstrap-namespace.
   js/vendor-fallback-tabler-js.js zet die na het laden door naar
   window.bootstrap. Ontbreekt de bundel toch, dan valt ui.js terug op
   dezelfde markup en klassen met een eigen backdrop; dat vangnet wordt
   in scripts/admin_ui_check.py apart getest.

   API
     ui.modal({ id, title, subtitle, body, primary, secondary, danger,
                confirmText, wide, closeLabel, onClose }) -> handle
       primary/secondary/danger: { label, onClick, keepOpen } of weggelaten.
       confirmText: de gebruiker moet die tekst letterlijk overtypen
       voordat de primaire of destructieve knop actief wordt.
       handle: { el, close(), setBody(html), selectTab(key),
                 button(role), setBusy(on) }
       button('primary'|'secondary'|'danger') geeft het knopelement, en
       setBusy(true) zet alle knoppen op disabled met een spinner op de
       handelende knop (§7.2c: laden houdt het paneel staan).

     ui.drawer({ id, title, subtitle, tabs, tabAction, activeTab, dataset,
                 body, onSelect, onClose }) -> handle
       Offcanvas aan de rechterkant voor detailpanelen. Afnemer: het
       Opdrachtgevers-detailpaneel (js/sections/clients.js).

     ui.tabs({ tabs, active, action, dataset }) -> RawHtml
       Tabstrip met role="tablist" en aria-selected. tabs is
       [{ key, label }]. dataset zet extra data-attributen op elke knop.

     ui.table({ tbody, thead, cols, load, render, page, sortable,
                serverSort, empty })
       Dun laagje over het bestaande renderPagination-patroon. Zet
       aria-sort op de kolomkop en tekent de laad-, lege- en foutstaat via
       Admin.setLoading/setEmpty/setLoadError. Per kolom kan `type` op
       'text' | 'number' | 'date'.
       Standaard sorteert het client-side binnen de opgehaalde pagina.
       serverSort: true laat het sorteren aan de route over (WS5 BV10:
       elke lijstroute neemt `sort` en `order`): een klik op een kolomkop
       zet state.sortKey/sortDir, springt terug naar pagina 1 en roept
       load(state) opnieuw aan, zodat er over de hele verzameling
       gesorteerd wordt en niet binnen één pagina.
       empty: de tekst voor de lege staat (html`` of string).

     ui.confirm(text, opts) -> Promise<boolean>
       opts: { title, confirmLabel, cancelLabel, confirmText, danger,
               body, onConfirm }
       body is extra inhoud onder de vraag (bijvoorbeeld een optioneel
       notitieveld); onConfirm() draait bij het bevestigen terwijl het
       paneel nog staat, zodat de aanroeper de waarde van dat veld nog
       kan uitlezen voordat de DOM verdwijnt.

     ui.closeTop() sluit het bovenste open paneel.

   ui.table en ui.confirm zijn sinds js/sections/retention.js in gebruik
   (§7.3.1, de goedkeuringslijst bewaartermijnen): een server-gesorteerde
   lijst met bewaartermijnen, en een getypte bevestiging voor het
   onomkeerbaar verwerken van persoonsgegevens. serverSort, `empty`, de
   foutstaat, `button()`/`setBusy()` en de twee ui.confirm-opties
   hierboven zijn met die eerste afnemer meegegroeid. De acht bestaande
   native confirm()-aanroepen elders in het paneel blijven ongemoeid.

   Toegankelijkheid, in alle gevallen:
     - role="dialog" + aria-modal="true" + aria-labelledby (of aria-label)
     - focus gaat bij openen naar het paneel, blijft erbinnen, en keert bij
       sluiten terug naar het element dat het paneel opende
     - Escape sluit het bovenste open paneel, ook als de focus intussen
       buiten het paneel is beland
     - klikken naast het paneel sluit het
     - geen fade-klasse: het paneel verschijnt en verdwijnt direct. Dat
       scheelt een race tussen een sluitende backdrop en de volgende klik,
       en het respecteert prefers-reduced-motion zonder uitzondering.
   ============================================================ */
(function (root) {
  'use strict';

  const { html, raw, mount } = root.GSP;

  const FOCUSABLE = [
    'a[href]', 'button:not([disabled])', 'input:not([disabled]):not([type="hidden"])',
    'select:not([disabled])', 'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
  ].join(',');

  let seq = 0;
  const uid = (prefix) => `${prefix}_${(++seq).toString(36)}${Date.now().toString(36).slice(-4)}`;

  function bs(name) {
    return root.bootstrap && root.bootstrap[name] ? root.bootstrap[name] : null;
  }

  function focusables(el) {
    return Array.prototype.filter.call(
      el.querySelectorAll(FOCUSABLE),
      (n) => n.offsetParent !== null || n === document.activeElement
    );
  }

  /* Veel panelen worden geopend vanaf een <tr> of een <div> die zelf geen
     focus kan krijgen; dan is document.activeElement bij het openen gewoon
     <body> en zou de focus na sluiten in het niets belanden. Daarom houden
     we bij wat er als laatste is aangewezen, en maken we dat element zo
     nodig programmatisch focusbaar (tabindex="-1", dus niet in de
     tabvolgorde). Dat rijen zelf geen toetsenbordingang zijn blijft een
     sectiepunt voor componentspec §7. */
  let lastPointerTarget = null;
  document.addEventListener('pointerdown', (e) => {
    lastPointerTarget = e.target && e.target.closest
      ? e.target.closest('[data-action],a,button') || e.target
      : e.target;
  }, true);

  const NATIVELY_FOCUSABLE = /^(a|button|input|select|textarea|summary)$/i;

  function makeFocusable(el) {
    if (!el || el.nodeType !== 1) return el;
    if (!NATIVELY_FOCUSABLE.test(el.tagName) && !el.hasAttribute('tabindex')) {
      el.setAttribute('tabindex', '-1');
    }
    return el;
  }

  function firstFocus(el) {
    const items = focusables(el);
    (items[0] || el).focus();
  }

  /* Alleen de focustrap. Het teruggeven van de focus is bewust een aparte
     stap: bij het hervullen van hetzelfde paneel moet de trap er wel af,
     maar mag de focus niet naar de opener springen. */
  function attachFocusTrap(el) {
    function onKeydown(e) {
      if (e.key !== 'Tab') return;
      const items = focusables(el);
      if (!items.length) { e.preventDefault(); el.focus(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === el)) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    }
    el.addEventListener('keydown', onKeydown);
    return () => el.removeEventListener('keydown', onKeydown);
  }

  /* ---- Backdrop en zichtbaarheid, met of zonder Bootstrap ---- */
  function fallbackShow(el, backdropClass) {
    el.classList.add('show');
    el.style.display = 'block';
    el.removeAttribute('aria-hidden');
    let backdrop = document.getElementById(el.id + '__backdrop');
    if (!backdrop) {
      backdrop = document.createElement('div');
      backdrop.id = el.id + '__backdrop';
      backdrop.className = backdropClass + ' show a-backdrop';
      document.body.appendChild(backdrop);
    }
    document.body.classList.add('modal-open');
  }

  function fallbackHide(el) {
    el.classList.remove('show');
    el.style.display = 'none';
    el.setAttribute('aria-hidden', 'true');
    const backdrop = document.getElementById(el.id + '__backdrop');
    if (backdrop) backdrop.remove();
    if (!document.querySelector('.modal.show, .offcanvas.show')) {
      document.body.classList.remove('modal-open');
    }
  }

  /* ---- Paneelstapel: Escape en klik-buiten gaan over het bovenste ---- */
  const openPanels = [];

  function topPanel() {
    for (let i = openPanels.length - 1; i >= 0; i--) {
      if (openPanels[i].el.classList.contains('show')) return openPanels[i];
    }
    return null;
  }

  function closeTop() {
    const p = topPanel();
    if (p) p.close();
    return !!p;
  }

  // Eén document-listener voor het hele paneel, niet één per geopend
  // paneel: Escape moet ook werken als de focus intussen buiten het
  // paneel is beland (na een toast, na een geherrenderde knop).
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeTop();
  });

  // Klikken naast het paneel sluit het, zoals de oude overlay deed.
  // Op een Offcanvas ligt de backdrop naast het paneel; op een Modal
  // vult .modal het scherm en is alles buiten .modal-content "naast".
  const BACKDROP_CLASSES = ['a-backdrop', 'modal-backdrop', 'offcanvas-backdrop'];
  document.addEventListener('mousedown', (e) => {
    const p = topPanel();
    if (!p) return;
    const content = p.el.querySelector('.modal-content, .offcanvas-body');
    if (content && content.contains(e.target)) return;
    const onBackdrop = e.target.classList
      && BACKDROP_CLASSES.some(c => e.target.classList.contains(c));
    if (p.el.contains(e.target) || onBackdrop) p.close();
  });

  // Een element binnen een paneel dat we net gaan hervullen is geen
  // bruikbare opener: dat verdwijnt zo meteen.
  function isUsableOpener(node) {
    return node.closest && !node.closest('.a-modal, .a-drawer');
  }

  /* ---- Gedeelde paneelmotor voor modal en drawer ---------------------- */
  function panel(opts, kind) {
    const isDrawer = kind === 'drawer';
    const id = opts.id || (isDrawer ? 'adminDrawer' : 'adminModalOverlay');
    const titleId = id + '__title';
    const Ctor = bs(isDrawer ? 'Offcanvas' : 'Modal');
    const active = document.activeElement;
    const fresh = (active && active !== document.body && isUsableOpener(active))
      ? active : lastPointerTarget;

    let el = document.getElementById(id);
    if (!el) {
      el = document.createElement('div');
      el.id = id;
      document.body.appendChild(el);
    } else if (typeof el._gspDetach === 'function') {
      // Hetzelfde paneel opnieuw vullen (spinner -> inhoud) mag geen tweede
      // set listeners opleveren; dat is het dubbele-bind patroon uit commit
      // d0917af. De vorige set gaat er eerst af, zonder de focus te
      // verplaatsen en zonder het paneel te verbergen.
      el._gspDetach();
    }
    // Bij hervullen blijft het element dat het paneel oorspronkelijk opende
    // de plek waar de focus straks naartoe terugkeert.
    const returnTo = (el._gspOpener && document.contains(el._gspOpener) && el.classList.contains('show'))
      ? el._gspOpener : fresh;
    el._gspOpener = returnTo;

    // Bij hervullen staat het paneel al open. className opnieuw zetten wist
    // dan de show-klasse die Bootstrap erop heeft gezet, terwijl een tweede
    // show() niets meer doet (het paneel is in zijn eigen boekhouding al
    // open). De klasse gaat er daarom meteen weer op.
    const wasShown = el.classList.contains('show');
    el.className = isDrawer
      ? 'offcanvas offcanvas-end a-drawer'
      : 'modal a-modal' + (opts.wide ? ' a-modal--wide' : '');
    if (wasShown) el.classList.add('show');
    el.tabIndex = -1;
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-modal', 'true');
    // Precies één van de twee, anders blijft er een label van een vorige
    // vulling hangen naast de nieuwe titel.
    if (opts.title) {
      el.setAttribute('aria-labelledby', titleId);
      el.removeAttribute('aria-label');
    } else {
      el.setAttribute('aria-label', opts.ariaLabel || 'Paneel');
      el.removeAttribute('aria-labelledby');
    }

    const confirmId = opts.confirmText ? uid('confirm') : null;
    const hintId = confirmId ? confirmId + '_hint' : null;
    const buttons = [];
    if (opts.secondary) buttons.push({ ...opts.secondary, cls: 'btn btn-ghost-secondary', role: 'secondary' });
    if (opts.danger) buttons.push({ ...opts.danger, cls: 'btn btn-outline-danger', role: 'danger' });
    if (opts.primary) buttons.push({ ...opts.primary, cls: 'btn btn-primary', role: 'primary' });
    const gated = (b) => confirmId && (b.role === 'primary' || b.role === 'danger');
    const btnIds = buttons.map(() => uid('btn'));

    const titleHtml = opts.title
      ? html`<h3 class="a-modal__title" id="${titleId}">${opts.title}</h3>`
      : '';
    // Onderschrift hoort bij de kop en gaat dus vóór de tabstrip staan.
    const subtitleHtml = opts.subtitle
      ? html`<div class="a-soft a-modal__subtitle">${opts.subtitle}</div>`
      : '';
    const confirmHtml = opts.confirmText
      ? html`
        <div class="a-panel">
          <p class="a-confirm-hint" id="${hintId}">Typ <code>${opts.confirmText}</code> om te bevestigen.</p>
          <div class="form-group mb-0">
            <label for="${confirmId}">Bevestiging</label>
            <input type="text" id="${confirmId}" autocomplete="off" aria-describedby="${hintId}"
              inputmode="text" autocapitalize="off" spellcheck="false">
          </div>
        </div>`
      : '';
    const buttonsHtml = buttons.length
      ? html`<div class="a-actions">${buttons.map((b, i) => html`
          <button type="button" class="${b.cls}" id="${btnIds[i]}" ${raw(gated(b) ? 'disabled' : '')}>${b.label}</button>`)}
        </div>`
      : '';
    const tabsHtml = opts.tabs
      ? tabs({ tabs: opts.tabs, active: opts.activeTab, action: opts.tabAction, dataset: opts.dataset })
      : '';
    const bodyId = id + '__body';

    const inner = html`
      <button type="button" class="a-modal__close" data-action="close-modal"
        aria-label="${opts.closeLabel || 'Sluiten'}"><i class="fa-solid fa-xmark"></i></button>
      ${titleHtml}
      ${subtitleHtml}
      ${tabsHtml}
      <div id="${bodyId}">${opts.body || ''}</div>
      ${confirmHtml}
      ${buttonsHtml}`;

    mount(el, isDrawer
      ? html`<div class="offcanvas-body">${inner}</div>`
      // modal-fullscreen-sm-down: op een telefoon vult het paneel het scherm
      // (§7.2c). Tabler levert die klasse; hij doet boven 576px niets.
      : html`<div class="modal-dialog modal-dialog-centered modal-dialog-scrollable modal-fullscreen-sm-down">
               <div class="modal-content"><div class="modal-body">${inner}</div></div>
             </div>`);

    let instance = null;
    let closed = false;
    let releaseTrap = null;

    function unwire() {
      if (releaseTrap) { releaseTrap(); releaseTrap = null; }
      el.removeEventListener(hiddenEvent, onHidden);
      const i = openPanels.indexOf(handle);
      if (i !== -1) openPanels.splice(i, 1);
    }

    // Hervullen: listeners eraf, en de onClose van de vorige vulling nog
    // netjes afvuren, zodat een ui.confirm-Promise nooit onopgelost blijft.
    function detach() {
      if (closed) { el._gspDetach = null; return; }
      closed = true;
      unwire();
      el._gspDetach = null;
      if (typeof opts.onClose === 'function') opts.onClose();
    }

    function close() {
      if (closed) return;
      closed = true;
      unwire();
      el._gspDetach = null;
      if (instance) instance.hide(); else fallbackHide(el);
      if (returnTo && typeof returnTo.focus === 'function' && document.contains(returnTo)) {
        makeFocusable(returnTo).focus();
      }
      if (typeof opts.onClose === 'function') opts.onClose();
    }

    const hiddenEvent = isDrawer ? 'hidden.bs.offcanvas' : 'hidden.bs.modal';
    const onHidden = () => close();
    el.addEventListener(hiddenEvent, onHidden);

    // Knoppen per rol, zodat een aanroeper met een asynchrone actie zijn
    // eigen laadstaat kan zetten zonder een id te hoeven kennen.
    const byRole = {};
    buttons.forEach((b, i) => { byRole[b.role] = btnIds[i]; });

    const handle = {
      el,
      close,
      button(role) {
        return byRole[role] ? document.getElementById(byRole[role]) : null;
      },
      // §7.2c, staat "laden": de handelende knop krijgt een spinner en
      // disabled, de rest gaat uit, en het paneel blijft staan.
      setBusy(on) {
        buttons.forEach((b, i) => {
          const node = document.getElementById(btnIds[i]);
          if (!node) return;
          if (on) {
            if (node.dataset.gspLabel === undefined) node.dataset.gspLabel = node.innerHTML;
            node.disabled = true;
            if (b.role !== 'secondary') {
              mount(node, html`<i class="fa-solid fa-spinner fa-spin"></i> ${b.label}`);
            }
          } else {
            if (node.dataset.gspLabel !== undefined) {
              // raw(): dit is de eigen, al gerenderde knoptekst van hierboven,
              // niet iets uit een respons.
              mount(node, raw(node.dataset.gspLabel));
              delete node.dataset.gspLabel;
            }
            node.disabled = !!(confirmId && gated(b) && confirmInput
              && confirmInput.value.trim() !== opts.confirmText);
          }
        });
      },
      setBody(newBody) { mount(document.getElementById(bodyId), newBody); },
      selectTab(key) {
        el.querySelectorAll('[role="tab"]').forEach(t => {
          const on = t.dataset.tab === key;
          t.setAttribute('aria-selected', on ? 'true' : 'false');
          t.classList.toggle('btn-primary', on);
          t.classList.toggle('btn-ghost-secondary', !on);
        });
        if (typeof opts.onSelect === 'function') opts.onSelect(key);
      },
    };
    openPanels.push(handle);
    el._gspDetach = detach;

    if (Ctor) {
      instance = Ctor.getOrCreateInstance(el, { backdrop: true, keyboard: true, focus: false });
      instance.show();
    } else {
      fallbackShow(el, isDrawer ? 'offcanvas-backdrop' : 'modal-backdrop');
    }
    releaseTrap = attachFocusTrap(el);
    firstFocus(el);

    // Knoppen en de getypte bevestiging.
    const confirmInput = confirmId ? document.getElementById(confirmId) : null;
    const gatedButtons = buttons
      .map((b, i) => ({ b, node: document.getElementById(btnIds[i]) }))
      .filter(({ b }) => gated(b));
    if (confirmInput) {
      confirmInput.addEventListener('input', () => {
        const ok = confirmInput.value.trim() === opts.confirmText;
        gatedButtons.forEach(({ node }) => { node.disabled = !ok; });
      });
    }
    buttons.forEach((b, i) => {
      const node = document.getElementById(btnIds[i]);
      if (!node) return;
      node.addEventListener('click', () => {
        if (typeof b.onClick === 'function' && b.onClick() === false) return;
        if (b.keepOpen !== true) close();
      });
    });

    return handle;
  }

  function modal(opts) { return panel(opts || {}, 'modal'); }
  function drawer(opts) { return panel(opts || {}, 'drawer'); }

  function tabs(opts) {
    const items = (opts && opts.tabs) || [];
    const active = opts.active || (items[0] && items[0].key);
    const extra = opts.dataset || {};
    // data-foo-bar uit { fooBar: ... }, zoals dataset dat ook doet.
    const attrs = Object.keys(extra).map(k =>
      ` data-${k.replace(/[A-Z]/g, m => '-' + m.toLowerCase())}="${root.GSP.esc(extra[k])}"`).join('');
    return html`<div class="a-tabbar" role="tablist">${items.map(t => html`
      <button type="button" role="tab" class="btn btn-sm ${t.key === active ? 'btn-primary' : 'btn-ghost-secondary'}"
        aria-selected="${t.key === active ? 'true' : 'false'}"
        data-tab="${t.key}"${raw(opts.action ? ` data-action="${root.GSP.esc(opts.action)}"` : '')}${raw(attrs)}>${t.label}</button>`)}
    </div>`;
  }

  /* ---- ui.table ---- */
  function table(opts) {
    const state = { sortKey: null, sortDir: null, items: [], total: 0 };
    const tbodyEl = () => document.querySelector(opts.tbody);
    const theadEl = () => (opts.thead ? document.querySelector(opts.thead) : null);
    const cols = opts.cols || [];
    const serverSort = opts.serverSort === true;

    function markHeaders() {
      const head = theadEl();
      if (!head) return;
      head.querySelectorAll('[data-sort-key]').forEach(th => {
        const key = th.dataset.sortKey;
        th.setAttribute('aria-sort',
          state.sortKey === key ? (state.sortDir === 'asc' ? 'ascending' : 'descending') : 'none');
      });
    }

    // Vergelijken per kolomtype. 'text' is de standaard; zonder type wordt
    // een kolom waarvan beide waarden numeriek zijn numeriek vergeleken,
    // zodat "10" niet achter "9" belandt.
    function compare(av, bv, type) {
      if (type === 'number') return Number(av) - Number(bv);
      if (type === 'date') return new Date(av) - new Date(bv);
      if (!type) {
        const an = Number(av), bn = Number(bv);
        const numeric = av !== '' && bv !== '' && Number.isFinite(an) && Number.isFinite(bn);
        if (numeric) return an - bn;
      }
      return String(av).localeCompare(String(bv), 'nl', { numeric: true, sensitivity: 'base' });
    }

    function sorted(items) {
      // Bij serverSort is de volgorde die de route teruggaf de volgorde:
      // client-side hersorteren zou de eerste pagina van een verzameling
      // anders rangschikken dan de verzameling zelf.
      if (serverSort || !state.sortKey) return items;
      const col = cols.find(c => c.key === state.sortKey) || {};
      const value = col.value || ((row) => row[state.sortKey]);
      const dir = state.sortDir === 'desc' ? -1 : 1;
      return items.slice().sort((a, b) => {
        const av = value(a), bv = value(b);
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return compare(av, bv, col.type) * dir;
      });
    }

    function paint() {
      if (!state.items.length && opts.empty !== undefined && typeof Admin !== 'undefined') {
        Admin.setEmpty(opts.tbody, cols.length, opts.empty);
      } else {
        mount(tbodyEl(), html`${sorted(state.items).map(opts.render)}`);
      }
      markHeaders();
    }

    function sortBy(key) {
      if (state.sortKey === key) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      else { state.sortKey = key; state.sortDir = 'asc'; }
      if (!serverSort) { paint(); return; }
      // Server-side sorteren geldt over de hele verzameling, dus de pager
      // begint weer bij pagina 1 met dezelfde filters (§7.2a).
      const page = opts.page || {};
      if (page.section && typeof Admin !== 'undefined') Admin._currentPage[page.section] = 1;
      reload();
    }

    function bindHeaders() {
      const head = theadEl();
      if (!head || opts.sortable === false) return;
      cols.filter(c => c.sortable).forEach(c => {
        const th = head.querySelector(`[data-sort-key="${c.key}"]`);
        if (!th || th.dataset.gspSortBound === '1') return;
        th.dataset.gspSortBound = '1';
        th.classList.add('a-sortable');
        th.tabIndex = 0;
        th.setAttribute('role', 'columnheader');
        th.setAttribute('aria-sort', 'none');
        th.addEventListener('click', () => sortBy(c.key));
        th.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sortBy(c.key); }
        });
      });
    }

    async function reload() {
      const page = opts.page || {};
      if (typeof Admin !== 'undefined' && cols.length) {
        Admin.setLoading(opts.tbody, cols.length);
      }
      let data;
      try {
        data = (await opts.load(state)) || {};
      } catch (err) {
        // Foutstaat op dezelfde plek als de laadstaat; de retry roept
        // exact dezelfde loader met dezelfde filters aan (§7.2a).
        if (typeof Admin !== 'undefined' && cols.length) {
          Admin.setLoadError(opts.tbody, cols.length, reload);
        }
        if (typeof opts.onError === 'function') opts.onError(err);
        return;
      }
      state.items = data.items || [];
      state.total = data.total || state.items.length;
      paint();
      if (page.container && typeof Admin !== 'undefined') {
        Admin.renderPagination(page.container, state.total, page.size || Admin._pageSize,
          Admin._currentPage[page.section] || 1, page.section);
      }
    }

    bindHeaders();
    return { state, reload, sortBy, paint };
  }

  function confirmDialog(text, opts) {
    const o = opts || {};
    return new Promise((resolve) => {
      let answer = false;
      const action = {
        label: o.confirmLabel || 'Bevestigen',
        // onConfirm draait terwijl het paneel nog staat, zodat de
        // aanroeper een veld uit `body` nog kan uitlezen.
        onClick: () => { answer = true; if (typeof o.onConfirm === 'function') o.onConfirm(); },
      };
      modal({
        id: 'adminConfirmModal',
        title: o.title || 'Bevestigen',
        body: html`<p class="a-soft">${text}</p>${o.body || ''}`,
        confirmText: o.confirmText,
        secondary: { label: o.cancelLabel || 'Annuleren', onClick: () => { answer = false; } },
        danger: o.danger === false ? null : action,
        primary: o.danger === false ? action : null,
        onClose: () => resolve(answer),
      });
    });
  }

  root.ui = { modal, drawer, tabs, table, confirm: confirmDialog, closeTop };
})(typeof window !== 'undefined' ? window : globalThis);
