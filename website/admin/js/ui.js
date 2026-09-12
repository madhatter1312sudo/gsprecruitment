/* ============================================================
   GSP Recruitment — admin/js/ui.js
   Dunne ui-laag bovenop de Bootstrap 5-componenten die Tabler 1.4 al
   meelevert. Geen eigen componentbibliotheek: modal en drawer zijn een
   Bootstrap Modal respectievelijk Offcanvas, met de merkopmaak uit
   admin.css en de toegankelijkheidsafspraken op één plek.

   API
     ui.modal({ id, title, body, primary, secondary, danger,
                confirmText, wide, closeLabel, onClose }) -> handle
       primary/secondary/danger: { label, onClick } of weggelaten.
       confirmText: de gebruiker moet die tekst letterlijk overtypen
       voordat de primaire of destructieve knop actief wordt.
       handle: { el, close(), setBody(html) }

     ui.drawer({ id, title, tabs, body, onSelect, onClose }) -> handle
       Offcanvas aan de rechterkant voor detailpanelen. tabs is dezelfde
       vorm als ui.tabs; handle krijgt er selectTab(key) en setBody(html)
       bij.

     ui.tabs({ tabs, active, action, dataset }) -> RawHtml
       Een tabstrip met role="tablist" en aria-selected. tabs is
       [{ key, label }]. De knoppen dragen data-action=<action>, zodat de
       bestaande gedelegeerde click-listener ze afhandelt.

     ui.table({ tbody, cols, load, render, page, sortable }) -> handle
       Dun laagje over het bestaande renderPagination-patroon.
       Sorteren gebeurt client-side binnen de opgehaalde pagina, want de
       adminendpoints kennen geen sort-parameter; de actieve kolom krijgt
       aria-sort. handle: { reload(), state }.

     ui.confirm(text, opts) -> Promise<boolean>

   Toegankelijkheid, in alle gevallen:
     - role="dialog" + aria-modal="true" + aria-labelledby (of aria-label)
     - focus gaat bij openen naar het paneel, blijft erbinnen, en keert bij
       sluiten terug naar het element dat het paneel opende
     - Escape sluit
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

  /* Focusbeheer dat we zelf doen, ook als Bootstrap aanwezig is: Bootstrap
     zet de focus terug op de trigger alleen bij een data-bs-toggle-knop, en
     onze panelen worden vanuit JS geopend. */
  function attachFocusBehaviour(el, opener) {
    function onKeydown(e) {
      if (e.key === 'Tab') {
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
    }
    el.addEventListener('keydown', onKeydown);
    return function restore() {
      el.removeEventListener('keydown', onKeydown);
      if (opener && typeof opener.focus === 'function' && document.contains(opener)) {
        makeFocusable(opener).focus();
      }
    };
  }

  /* Veel panelen worden geopend vanaf een <tr> of een <div> die zelf geen
     focus kan krijgen; dan is document.activeElement bij het openen gewoon
     <body> en zou de focus na sluiten in het niets belanden. Daarom houden
     we bij wat er als laatste is aangewezen, en maken we dat element zo
     nodig programmatisch focusbaar (tabindex="-1", dus niet in de tabvolgorde).
     Dat rijen zelf geen toetsenbordingang zijn blijft een sectiepunt voor
     componentspec §7; dit lost alleen het teruggeven van de focus op. */
  let lastPointerTarget = null;
  document.addEventListener('pointerdown', (e) => {
    lastPointerTarget = e.target && e.target.closest ? e.target.closest('[data-action],a,button') || e.target : e.target;
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

  /* ---- Backdrop en zichtbaarheid, met of zonder Bootstrap -------------
     Bootstrap Modal/Offcanvas doen dit netter (body-scrolllock, backdrop,
     stacking). Zonder Bootstrap -- de gevendorde tabler.min.js wordt
     dynamisch ingeladen en kan in theorie ontbreken -- valt ui.js terug op
     dezelfde klassen zonder de component. */
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
    document.getElementById(el.id + '__backdrop')?.remove();
    if (!document.querySelector('.modal.show, .offcanvas.show')) {
      document.body.classList.remove('modal-open');
    }
  }

  // Een element binnen een paneel dat we net gaan hervullen is geen
  // bruikbare opener: dat verdwijnt zo meteen.
  function isUsableOpener(node) {
    return !node.closest('.a-modal, .a-drawer');
  }

  /* ---- Gedeelde paneelmotor voor modal en drawer ---------------------- */
  function panel(opts, kind) {
    const isDrawer = kind === 'drawer';
    const id = opts.id || (isDrawer ? 'adminDrawer' : 'adminModalOverlay');
    const titleId = id + '__title';
    const Ctor = bs(isDrawer ? 'Offcanvas' : 'Modal');
    const active = document.activeElement;
    const opener = (active && active !== document.body && isUsableOpener(active)) ? active : lastPointerTarget;

    let el = document.getElementById(id);
    if (!el) {
      el = document.createElement('div');
      el.id = id;
      document.body.appendChild(el);
    } else if (typeof el._gspDetach === 'function') {
      // Hetzelfde paneel opnieuw vullen (bijv. spinner -> inhoud) mag geen
      // tweede set listeners opleveren -- dat is precies het dubbele-bind
      // patroon uit commit d0917af. De vorige set gaat er eerst af.
      el._gspDetach();
    }
    // Bij hervullen blijft het element dat het paneel oorspronkelijk opende
    // de plek waar de focus straks naartoe terugkeert.
    const returnTo = el._gspOpener && document.contains(el._gspOpener) && el.classList.contains('show')
      ? el._gspOpener : opener;
    el._gspOpener = returnTo;
    el.className = isDrawer
      ? 'offcanvas offcanvas-end a-drawer'
      : 'modal a-modal' + (opts.wide ? ' a-modal--wide' : '');
    el.tabIndex = -1;
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-modal', 'true');
    if (opts.title) el.setAttribute('aria-labelledby', titleId);
    else el.setAttribute('aria-label', opts.ariaLabel || 'Paneel');

    const confirmId = opts.confirmText ? uid('confirm') : null;
    const buttons = [];
    if (opts.secondary) buttons.push({ ...opts.secondary, cls: 'btn btn-ghost-secondary', role: 'secondary' });
    if (opts.danger) buttons.push({ ...opts.danger, cls: 'btn btn-outline-danger', role: 'danger' });
    if (opts.primary) buttons.push({ ...opts.primary, cls: 'btn btn-primary', role: 'primary' });
    const gated = (b) => confirmId && (b.role === 'primary' || b.role === 'danger');
    const btnIds = buttons.map(() => uid('btn'));

    const titleHtml = opts.title
      ? html`<h3 class="a-modal__title" id="${titleId}">${opts.title}</h3>`
      : '';
    const confirmHtml = opts.confirmText
      ? html`
        <div class="a-panel">
          <p class="a-confirm-hint">Typ <code>${opts.confirmText}</code> om te bevestigen.</p>
          <div class="form-group mb-0">
            <label for="${confirmId}">Bevestiging</label>
            <input type="text" id="${confirmId}" autocomplete="off" aria-describedby="${confirmId}_hint">
          </div>
        </div>`
      : '';
    const buttonsHtml = buttons.length
      ? html`<div class="a-actions">${buttons.map((b, i) => html`
          <button type="button" class="${b.cls}" id="${btnIds[i]}" ${raw(gated(b) ? 'disabled' : '')}>${b.label}</button>`)}
        </div>`
      : '';
    const tabsHtml = opts.tabs ? tabs({ tabs: opts.tabs, active: opts.activeTab, action: opts.tabAction }) : '';
    const bodyId = id + '__body';

    const inner = html`
      <button type="button" class="a-modal__close" data-action="close-modal"
        aria-label="${opts.closeLabel || 'Sluiten'}"><i class="fa-solid fa-xmark"></i></button>
      ${titleHtml}
      ${tabsHtml}
      <div id="${bodyId}">${opts.body || ''}</div>
      ${confirmHtml}
      ${buttonsHtml}`;

    mount(el, isDrawer
      ? html`<div class="offcanvas-body">${inner}</div>`
      : html`<div class="modal-dialog modal-dialog-centered modal-dialog-scrollable">
               <div class="modal-content"><div class="modal-body">${inner}</div></div>
             </div>`);

    let restoreFocus = null;
    let instance = null;
    let closed = false;

    function close() {
      if (closed) return;
      closed = true;
      if (instance) instance.hide(); else fallbackHide(el);
      if (restoreFocus) { restoreFocus(); restoreFocus = null; }
      if (typeof opts.onClose === 'function') opts.onClose();
    }

    // Escape sluit ook als Bootstrap ontbreekt; met Bootstrap sluit die het
    // paneel en loopt onze close() daarna nog eenmaal door de guard heen.
    const onEsc = (e) => { if (e.key === 'Escape') close(); };
    const hiddenEvent = isDrawer ? 'hidden.bs.offcanvas' : 'hidden.bs.modal';
    const onHidden = () => close();
    el.addEventListener('keydown', onEsc);
    el.addEventListener(hiddenEvent, onHidden);

    if (Ctor) {
      instance = Ctor.getOrCreateInstance(el, { backdrop: true, keyboard: true, focus: false });
      instance.show();
    } else {
      fallbackShow(el, isDrawer ? 'offcanvas-backdrop' : 'modal-backdrop');
    }
    restoreFocus = attachFocusBehaviour(el, returnTo);
    firstFocus(el);

    el._gspDetach = function detach() {
      el.removeEventListener('keydown', onEsc);
      el.removeEventListener(hiddenEvent, onHidden);
      if (restoreFocus) { restoreFocus = null; }
      closed = true;
      el._gspDetach = null;
    };

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

    return {
      el,
      close,
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
  }

  function modal(opts) { return panel(opts || {}, 'modal'); }
  function drawer(opts) { return panel(opts || {}, 'drawer'); }

  function tabs(opts) {
    const items = (opts && opts.tabs) || [];
    const active = opts.active || (items[0] && items[0].key);
    return html`<div class="a-tabbar" role="tablist">${items.map(t => html`
      <button type="button" role="tab" class="btn btn-sm ${t.key === active ? 'btn-primary' : 'btn-ghost-secondary'}"
        aria-selected="${t.key === active ? 'true' : 'false'}"
        data-tab="${t.key}"${raw(opts.action ? ` data-action="${opts.action}"` : '')}>${t.label}</button>`)}
    </div>`;
  }

  /* ---- ui.table -------------------------------------------------------
     Bewust dun: het haalt een pagina op via load(), rendert de rijen met
     render(), en laat de paginering aan Admin.renderPagination over. De
     adminendpoints kennen geen sort-parameter, dus sorteren gebeurt
     client-side binnen de opgehaalde pagina. Dat staat als zodanig in de
     kolomkop (aria-sort) en verandert niets aan de opgehaalde data. */
  function table(opts) {
    const state = { sortKey: null, sortDir: null, items: [], total: 0 };
    const tbodyEl = () => document.querySelector(opts.tbody);
    const theadEl = () => (opts.thead ? document.querySelector(opts.thead) : null);
    const cols = opts.cols || [];

    function markHeaders() {
      const head = theadEl();
      if (!head) return;
      head.querySelectorAll('[data-sort-key]').forEach(th => {
        const key = th.dataset.sortKey;
        th.setAttribute('aria-sort',
          state.sortKey === key ? (state.sortDir === 'asc' ? 'ascending' : 'descending') : 'none');
      });
    }

    function sorted(items) {
      if (!state.sortKey) return items;
      const col = cols.find(c => c.key === state.sortKey);
      const value = (col && col.value) || ((row) => row[state.sortKey]);
      const dir = state.sortDir === 'desc' ? -1 : 1;
      return items.slice().sort((a, b) => {
        const av = value(a), bv = value(b);
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
        return String(av).localeCompare(String(bv), 'nl') * dir;
      });
    }

    function paint() {
      mount(tbodyEl(), html`${sorted(state.items).map(opts.render)}`);
      markHeaders();
    }

    function sortBy(key) {
      if (state.sortKey === key) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      else { state.sortKey = key; state.sortDir = 'asc'; }
      paint();
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
      if (typeof Admin !== 'undefined' && opts.cols.length) {
        Admin.setLoading(opts.tbody, cols.length);
      }
      const data = (await opts.load(state)) || {};
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
      modal({
        id: 'adminConfirmModal',
        title: o.title || 'Bevestigen',
        body: html`<p class="a-soft">${text}</p>`,
        confirmText: o.confirmText,
        secondary: { label: o.cancelLabel || 'Annuleren', onClick: () => { answer = false; } },
        danger: o.danger === false ? null : { label: o.confirmLabel || 'Bevestigen', onClick: () => { answer = true; } },
        primary: o.danger === false ? { label: o.confirmLabel || 'Bevestigen', onClick: () => { answer = true; } } : null,
        onClose: () => resolve(answer),
      });
    });
  }

  root.ui = { modal, drawer, tabs, table, confirm: confirmDialog };
})(typeof window !== 'undefined' ? window : globalThis);
