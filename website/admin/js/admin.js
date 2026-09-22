/* ============================================================
   GSP Recruitment — admin.js  v2.0
   Full admin portal: all sections wired to real API, no stubs.
   ============================================================ */

// html`` auto-escapes every interpolated value (GSP.esc under the hood);
// raw() marks an already-safe fragment (or array of them) so html`` does
// not re-escape it; mount() is `el.innerHTML = result` with a null-safe
// guard. See website/admin/js/render.js (load order: gsp-util.js, then
// render.js, then this file).
const { html, raw, mount } = GSP;

const Admin = {
  _data: {},
  _currentPage: { users: 1, candidates: 1, audit: 1, outreach: 1, blog: 1, leads: 1, jobs: 1, retention: 1, placements: 1, gdpr: 1 },
  // Filters passed to the load*() call that produced the currently-rendered
  // page, keyed the same as _currentPage — a data-page click re-derives the
  // page from here instead of needing a fresh closure per render.
  // `clients` isn't in _currentPage/goToPage's loaders map -- the roster
  // fetches a single limit=200 page (see loadClients()), no data-page UI.
  _lastParams: { users: {}, candidates: {}, audit: {}, outreach: {}, blog: {}, leads: {}, jobs: {}, clients: {}, retention: {}, placements: {}, gdpr: {} },
  _pageSize: 20,

  /* ---- Init ---- */
  async init() {
    const user = Auth.requireAuth(['admin']);
    if (!user) return;

    const name = user.full_name || 'Admin';
    const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
    document.getElementById('sidebarName').textContent = name;
    document.getElementById('sidebarEmail').textContent = user.email || '';
    document.getElementById('sidebarAvatar').textContent = initials;

    // mfa hangt aan Admin via js/sections/settings.js, dat vóór dit
    // DOMContentLoaded-moment geladen is. De guard is er voor het geval
    // die sectie ooit niet meegeladen wordt.
    if (this.mfa) {
      this.mfa.bindUI();
      await this.mfa.loadStatus();
    }
    await this.loadDashboard();
  },

  /* ---- Utilities ---- */
  formatDate(d) {
    if (!d) return '—';
    const dt = new Date(d);
    return dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  },
  timeAgo(d) {
    if (!d) return '';
    const s = (Date.now() - new Date(d)) / 1000;
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    if (s < 604800) return `${Math.floor(s / 86400)}d ago`;
    return this.formatDate(d);
  },
  badge(status) {
    const map = { active: 'green', open: 'green', placed: 'green',
      pending: 'blue', suspended: 'red', closed: 'red',
      draft: 'blue', admin: 'red', candidate: 'gold', client: 'blue',
      sent: 'green', rejected: 'default', failed: 'red',
      published: 'green', archived: 'default',
      // Candidate pipeline statuses (WS2) — the raw values GET
      // /v1/admin/candidates actually returns, not the old active/
      // placed/inactive guess.
      sourced: 'default', new: 'gold', contacted: 'blue', screening: 'gold',
      inactive: 'default' };
    const colors = { green: 'bg-green-lt', blue: 'bg-blue-lt', gold: 'bg-yellow-lt', red: 'bg-red-lt', default: 'bg-secondary-lt' };
    return `badge ${colors[map[status?.toLowerCase()] || 'default']}`;
  },
  // esc()/safeUrl() delegate to the shared GSP.esc/GSP.safeUrl (gsp-util.js,
  // loaded before this file) so the public site and admin panel share one
  // escaping implementation. Kept as Admin.esc/Admin.safeUrl for every
  // existing call site in this file — do not remove.
  esc(s) {
    return GSP.esc(s);
  },
  // Eén normalisatie van een 4xx/5xx-`detail` (SITE-DESIGN-SPEC.md §7.2f
  // punt 4). Nieuwe endpoints geven `detail` als object met `code` en
  // `message`; oudere geven een gewone string, en die wordt hier een
  // `message` met een lege `code`. Elk aanroeppunt vertakt daarna op
  // `code` en valt terug op `message` -- nooit op de tekst zelf om te
  // vertakken. Neem het hele responsobject mee (of alleen de detail);
  // beide werken. Extra velden van het detailobject (`allowed`,
  // `candidate_id`) blijven onder `extra` beschikbaar.
  // De retentiesectie is de eerste afnemer; de andere secties migreren
  // hier later naartoe.
  errorDetail(payload) {
    const d = (payload && typeof payload === 'object' && 'detail' in payload) ? payload.detail : payload;
    if (typeof d === 'string') return { code: '', message: d, extra: {} };
    if (d && typeof d === 'object' && !Array.isArray(d)) {
      return { code: d.code || '', message: d.message || '', extra: d };
    }
    return { code: '', message: '', extra: {} };
  },
  safeUrl(s) {
    return GSP.safeUrl(s);
  },
  setLoading(tbodyId, cols) {
    const el = document.querySelector(tbodyId);
    mount(el, html`<tr><td colspan="${cols}" class="a-state-cell">
      <i class="fa-solid fa-spinner fa-spin"></i> Loading…</td></tr>`);
  },
  // msg is always a literal called by our own code (never API/user text),
  // so it is passed through raw() rather than escaped a second time.
  setEmpty(tbodyId, cols, msg = 'No results') {
    const el = document.querySelector(tbodyId);
    mount(el, html`<tr><td colspan="${cols}" class="a-state-cell">${raw(msg)}</td></tr>`);
  },
  // Table-row error state with a retry link — replaces an infinite spinner
  // when a fetch fails or times out.
  setLoadError(tbodyId, cols, retryFn) {
    const el = document.querySelector(tbodyId);
    if (!el) return;
    const id = '_retry_' + Math.random().toString(36).slice(2, 9);
    mount(el, html`<tr><td colspan="${cols}" class="a-state-cell">
      <i class="fa-solid fa-triangle-exclamation"></i> Kon niet laden, <a href="#" id="${id}">probeer opnieuw</a>
    </td></tr>`);
    document.getElementById(id)?.addEventListener('click', (e) => { e.preventDefault(); if (typeof retryFn === 'function') retryFn(); });
  },
  // Non-table container error state with a retry link.
  setContainerLoadError(el, retryFn) {
    if (!el) return;
    const id = '_retry_' + Math.random().toString(36).slice(2, 9);
    mount(el, html`<div class="a-state-block">
      <i class="fa-solid fa-triangle-exclamation"></i> Kon niet laden, <a href="#" id="${id}">probeer opnieuw</a>
    </div>`);
    document.getElementById(id)?.addEventListener('click', (e) => { e.preventDefault(); if (typeof retryFn === 'function') retryFn(); });
  },

  /* ============================================================
     DASHBOARD
     ============================================================ */
  async loadDashboard() {
    try {
      const [dashRes, recentRes, healthRes] = await Promise.all([
        Auth.fetch('/v1/admin/dashboard'),
        Auth.fetch('/v1/admin/audit-log?limit=8'),
        Auth.fetch('/v1/admin/health'),
      ]);

      if (healthRes?.ok) {
        this.renderHealthCard(await healthRes.json());
      } else {
        this.setContainerLoadError(document.getElementById('healthCardBody'), () => this.loadDashboard());
      }

      if (dashRes?.ok) {
        const d = await dashRes.json();
        document.getElementById('kpiTotalUsers').textContent = d.total_users ?? 0;
        document.getElementById('kpiActiveJobs').textContent = d.active_jobs ?? 0;
        document.getElementById('kpiCandidates').textContent = d.registered_candidates ?? 0;
        document.getElementById('kpiClients').textContent = d.active_clients ?? 0;
        document.getElementById('kpiPlacements').textContent = d.placements_this_week ?? 0;
        this._data.dashboard = d;
      }

      if (recentRes?.ok) {
        const auditData = await recentRes.json();
        this.renderRecentActivity(auditData.items || []);
      }

      // Load pending (unverified) users for the pending widget
      const pendingRes = await Auth.fetch('/v1/admin/users?status=unverified&limit=5');
      if (pendingRes?.ok) {
        const pd = await pendingRes.json();
        this.renderPendingRegistrations(pd.items || []);
      }

      // Newest self-registered candidates — the owner should see someone
      // like a same-day sign-up here without having to open the Candidates
      // tab and apply the kind filter themselves.
      const newRegRes = await Auth.fetch('/v1/admin/candidates?kind=self-registered&limit=5&offset=0');
      if (newRegRes?.ok) {
        const nd = await newRegRes.json();
        const items = (nd.items || []).slice().sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 5);
        this.renderNewRegistrations(items);
      } else {
        this.setContainerLoadError(document.getElementById('newRegistrationsList'), () => this.loadDashboard());
      }
    } catch (err) {
      console.error('Dashboard load error:', err);
      this.setContainerLoadError(document.getElementById('recentActivityList'), () => this.loadDashboard());
      this.setContainerLoadError(document.getElementById('pendingRegistrationsList'), () => this.loadDashboard());
      this.setContainerLoadError(document.getElementById('newRegistrationsList'), () => this.loadDashboard());
      this.setContainerLoadError(document.getElementById('healthCardBody'), () => this.loadDashboard());
    }
  },

  // WS5 §7.3.6(d): GET /api/v1/admin/health -> vier regels met statusstip.
  // duplicate_profile_links is de reden dat de kaart bestaat (hoort altijd
  // 0 te zijn); boven 0 wordt de hele kaart een inline-melding van het
  // type fout in plaats van de vierregelige lijst. candidates_count en
  // open_jobs uit dezelfde respons komen hier niet terug -- die staan al
  // in de KPI-rij (§7.3.6(d), laatste zin).
  renderHealthCard(h) {
    const el = document.getElementById('healthCardBody');
    if (!el) return;
    const dup = h.duplicate_profile_links;

    if (typeof dup === 'number' && dup > 0) {
      mount(el, html`
        <div class="alert alert-danger mb-0" role="alert">
          <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
          <span>${dup} dubbele profielkoppelingen. Dit hoort 0 te zijn.</span>
          <div class="mt-2">
            <button type="button" class="btn btn-sm btn-outline-secondary" data-action="navigate" data-section="candidates">Kandidaten openen</button>
          </div>
        </div>`);
      return;
    }

    const dot = (ok) => raw(`<span class="status-dot ${ok ? 'bg-success' : 'bg-danger'} me-2" aria-hidden="true"></span>`);
    const dbOk = h.database === 'connected';
    const orOk = h.openrouter === 'configured';
    const apOk = h.apollo === 'configured';
    const dupLine = dup === 0
      ? html`<span class="status-dot bg-success me-2" aria-hidden="true"></span><span><span class="a-num">0</span> dubbele profielkoppelingen</span>`
      : html`<span class="status-dot bg-secondary me-2" aria-hidden="true"></span><span class="a-soft">Onbekend</span>`;

    mount(el, html`
      <div class="d-flex align-items-center mb-2">${dot(dbOk)}<span>Database: ${raw(dbOk ? 'verbonden' : 'niet verbonden')}</span></div>
      <div class="d-flex align-items-center mb-2">${dot(orOk)}<span>OpenRouter: ${raw(orOk ? 'geconfigureerd' : 'niet geconfigureerd')}</span></div>
      <div class="d-flex align-items-center mb-2">${dot(apOk)}<span>Apollo: ${raw(apOk ? 'geconfigureerd' : 'niet geconfigureerd')}</span></div>
      <div class="d-flex align-items-center">${dupLine}</div>`);
  },

  renderNewRegistrations(items) {
    const el = document.getElementById('newRegistrationsList');
    const badge = document.getElementById('newRegBadge');
    if (badge) badge.textContent = items.length || '0';
    if (!el) return;
    if (!items.length) {
      mount(el, html`<div class="a-state-block">
        Nog geen zelf geregistreerde kandidaten. Nieuwe registraties via het kandidatenportaal verschijnen hier automatisch.
      </div>`);
      return;
    }
    mount(el, html`${items.map(c => html`
      <div class="activity-item">
        <div class="activity-icon activity-icon--positive"><i class="fa-solid fa-user-plus"></i></div>
        <div class="activity-content a-truncate-col">
          <div class="activity-text a-cell-strong fw-medium">
            ${c.full_name || c.email || 'Onbekend'}
            ${c.is_verified ? raw('<i class="fa-regular fa-circle-check ms-1 text-success-ink" title="Geverifieerd"></i>') : ''}
          </div>
          <div class="activity-text a-soft">${c.current_title || '—'}${c.location ? ' · ' + c.location : ''}</div>
          <div class="activity-time">${this.timeAgo(c.created_at)}</div>
        </div>
        <button class="btn btn-sm btn-ghost-secondary flex-shrink-0" data-action="view-candidate" data-kind="self-registered" data-id="${c.user_id ?? c.id}" title="Profiel bekijken">
          <i class="fa-regular fa-eye"></i>
        </button>
      </div>`)}`);
  },

  renderRecentActivity(items) {
    const el = document.getElementById('recentActivityList');
    if (!el) return;
    if (!items.length) { mount(el, html`<div class="a-state-block">Nog geen activiteit.</div>`); return; }
    const icons = { user_update: 'fa-user-pen', user_delete: 'fa-user-xmark', impersonate: 'fa-mask',
      job_update: 'fa-briefcase', content_update: 'fa-newspaper', settings_update: 'fa-gear',
      placement: 'fa-calendar-check' };
    mount(el, html`${items.map(e => {
      const changeKeys = (e.changes && typeof e.changes === 'object') ? Object.keys(e.changes).slice(0, 2) : [];
      return html`
      <div class="activity-item">
        <div class="activity-icon activity-icon--gold">
          <i class="fa-regular ${icons[e.action] || 'fa-circle-dot'}"></i>
        </div>
        <div class="activity-content flex-fill">
          <div class="activity-text">${e.action?.replace(/_/g, ' ')} <span class="a-soft">by ${e.actor_email || 'system'}</span>${changeKeys.length ? html` <span class="a-soft">(${changeKeys.join(', ')})</span>` : ''}</div>
          <div class="activity-time">${this.timeAgo(e.created_at)}</div>
        </div>
      </div>`;
    })}`);
  },

  renderPendingRegistrations(items) {
    const el = document.getElementById('pendingRegistrationsList');
    const badge = document.getElementById('pendingBadge');
    if (badge) badge.textContent = items.length || '0';
    if (!el) return;
    if (!items.length) { mount(el, html`<div class="a-state-block">Geen openstaande verificaties.</div>`); return; }
    mount(el, html`${items.map(u => html`
      <div class="activity-item">
        <div class="activity-icon activity-icon--gold"><i class="fa-solid fa-user-plus"></i></div>
        <div class="activity-content flex-fill">
          <div class="activity-text">${u.full_name || u.email} — <span class="a-accent">${u.role}</span></div>
          <div class="activity-time">${this.timeAgo(u.created_at)}</div>
        </div>
        <button class="btn btn-sm btn-primary flex-shrink-0" data-action="verify-user" data-id="${u.id}">Verify</button>
      </div>`)}`);
  },

  async verifyUser(userId, btn) {
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
      const res = await Auth.fetch(`/v1/admin/users/${userId}`, {
        method: 'PUT', body: JSON.stringify({ is_verified: true }),
      });
      if (res?.ok) {
        Auth.toast('User verified', 'success');
        await this.loadDashboard();
        if (document.getElementById('section-users').classList.contains('active')) {
          await this.loadUsers();
        }
      } else {
        const d = await res?.json();
        Auth.toast(d?.detail || 'Failed to verify', 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'Verify'; }
      }
    } catch { Auth.toast('Network error', 'error'); if (btn) { btn.disabled = false; btn.textContent = 'Verify'; } }
  },
  closeMenus() {
    document.querySelectorAll('.action-menu').forEach(m => m.style.display = 'none');
  },

  /* ============================================================
     SECTIEREGISTRY

     Elke sectiemodule (js/sections/*.js) roept registerSection() aan met:
       id            de hash en het id-achtervoegsel van <section id="section-X">
       title          de kop boven het paneel
       loader         () => Promise, wordt eenmalig aangeroepen bij het
                      eerste bezoek aan de sectie (nav.js cachet dat en
                      ontcachet weer als de promise afwijst)
       skeletonHtml   optioneel: () => html`` dat bij registratie in
                      <section id="section-X"> wordt gezet. Secties die hun
                      markup in index.html houden laten dit weg.
       filters        lijst van { selector, event, debounce?, handler(el, e) }
                      die nav.js precies één keer bindt -- filterbinding zat
                      hiervoor verspreid over nav.js en admin.js
       actions        map van data-action-waarde naar (el, e) => ..., voor de
                      ene gedelegeerde click-listener hieronder
     ============================================================ */
  _sections: {},
  _sectionOrder: [],
  _actions: {},

  registerSection(def) {
    if (!def || !def.id) return null;
    if (!this._sections[def.id]) this._sectionOrder.push(def.id);
    this._sections[def.id] = def;
    if (def.actions) this.registerActions(def.actions);
    if (typeof def.skeletonHtml === 'function') {
      mount(document.getElementById('section-' + def.id), def.skeletonHtml());
    }
    return def;
  },

  registerActions(map) {
    Object.assign(this._actions, map || {});
  },

  section(id) { return this._sections[id]; },
  sections() { return this._sectionOrder.map(id => this._sections[id]); },

  /* ============================================================
     PAGINATION
     ============================================================ */
  // `section` is one of the _currentPage/_lastParams keys (users, candidates,
  // outreach, blog, audit). Buttons carry data-action="page" + data-section +
  // data-page and go through the one delegated click listener in
  // handleDataAction() -> goToPage() -- no inline onclick=, no per-render
  // addEventListener closures.
  renderPagination(containerId, total, limit, current, section) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const pages = Math.ceil(total / limit);
    if (pages <= 1) { mount(el, ''); return; }

    const pageBtn = (label, page, opts = {}) => html`<button
        data-action="page" data-section="${section}" data-page="${page}"
        class="${opts.active ? 'active' : ''}"
        ${raw(opts.disabled ? 'disabled' : '')}>${opts.icon ? raw(label) : label}</button>`;

    mount(el, html`
      ${pageBtn('<i class="fa-solid fa-chevron-left"></i>', current - 1, { icon: true, disabled: current === 1 })}
      ${(function () {
        const nums = [];
        for (let i = 1; i <= Math.min(pages, 7); i++) nums.push(pageBtn(String(i), i, { active: i === current }));
        return nums;
      })()}
      ${pages > 7 ? html`<span class="pagination-ellipsis">…${pages}</span>` : ''}
      ${pageBtn('<i class="fa-solid fa-chevron-right"></i>', current + 1, { icon: true, disabled: current === pages })}
    `);
  },

  // Dispatch target for data-action="page" -- re-derives the page's params
  // from the last load*() call for that section (set in loadUsers() etc.)
  // rather than needing a fresh onPage closure per render.
  goToPage(section, page) {
    const loaders = {
      users: 'loadUsers', candidates: 'loadCandidates',
      outreach: 'loadOutreach', blog: 'loadBlog', audit: 'loadAuditLog',
      leads: 'loadLeads', jobs: 'loadJobs', retention: 'loadRetentionReview',
      placements: 'loadPlacements', gdpr: 'loadGdprSuppression',
    };
    const fn = loaders[section];
    if (!fn || !Number.isFinite(page) || page < 1) return;
    this._currentPage[section] = page;
    this[fn](this._lastParams[section] || {});
  },

  /* ============================================================
     MODAL
     ============================================================ */
  // De ad-hoc overlay die hier stond is vervangen door ui.modal (js/ui.js),
  // dat op de Bootstrap 5 Modal van Tabler draait: focustrap, Escape,
  // aria-modal/aria-labelledby en focus terug naar de opener zitten daar.
  // Deze twee methodes blijven bestaan omdat elke sectie ze aanroept;
  // `id` is historisch (een label, geen DOM-id) en wordt genegeerd: er is
  // één overlay, #adminModalOverlay. `opts.wide` verbreedt het paneel naar
  // 760px voor het opdrachtgeverspaneel met zijn tabbladen.
  openModal(id, bodyHtml, opts = {}) {
    this._modal = ui.modal({
      id: 'adminModalOverlay',
      // opts.title vult aria-labelledby met de echte kop van het paneel;
      // zonder titel valt ui.modal terug op een generiek aria-label.
      title: opts.title,
      body: bodyHtml,
      wide: !!opts.wide,
      ariaLabel: opts.ariaLabel || 'Detailpaneel',
      onClose: () => { this._modal = null; },
    });
    return this._modal;
  },

  // Sluit het bovenste open paneel: de modal, of de drawer van het
  // Opdrachtgevers-detailpaneel als die erboven ligt.
  closeModal() {
    ui.closeTop();
  },

  /* ============================================================
     GLOBALE BINDINGEN
     ============================================================ */
  bindGlobal() {
    document.addEventListener('click', () => this.closeMenus());

    // Eén gedelegeerde listener voor alle data-action-knoppen, één keer
    // gebonden. Elke sectie levert zijn eigen handlers via de registry;
    // user-afkomstige strings komen zo nooit in een JS-literal terecht.
    document.addEventListener('click', (e) => this.handleDataAction(e));
  },

  handleDataAction(e) {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    const fn = this._actions[el.dataset.action];
    if (typeof fn === 'function') fn.call(this, el, e);
  },
};

/* Paneelbrede acties die niet bij één sectie horen. */
Admin.registerActions({
  // navigateTo() is een page-level global uit admin/js/nav.js.
  navigate: (el) => { if (typeof navigateTo === 'function') navigateTo(el.dataset.section); },
  'close-modal': () => ui.closeTop(),
  page: (el) => Admin.goToPage(el.dataset.section, Number(el.dataset.page)),
  // §7.3.4: gedeeld tussen de tab Pipeline in de kandidaat- (candidates.js)
  // en de klantdrawer (clients.js), dus hier geregistreerd in plaats van
  // in een van beide sectiebestanden -- een tweede, identieke registratie
  // vanuit de andere sectie zou hetzelfde effect hebben (Admin._actions is
  // één globale kaart per data-action-waarde, geen per-sectie schil), maar
  // dan staat dezelfde functie op twee plekken gedefinieerd.
  'pipeline-change-stage': (el) => Admin.changePipelineStage(Number(el.dataset.entryId), el.closest('.a-tabpane')),
  'pipeline-history-show-all': (el) => Admin.renderPipelineHistory(Number(el.dataset.entryId), true, el.closest('.a-tabpane')),
});

/* ============================================================
   PIPELINE-TAB (§7.3.4): "Pipeline" in de kandidaat- en klantdrawer.
   Vervangt de tab Matches in de kandidaatdrawer (§7.3.2 afwijking 4), die
   dezelfde route (GET /admin/pipeline?candidate_id=) alleen liet zien; met
   deze tab is er nog maar één plek die pipeline-entries toont.

   Elke DOM-lookup hieronder gaat via een `root` (de `.a-tabpane` van de
   drawer die de aanroep deed), nooit via het kale `document`: de
   kandidaat- en de klantdrawer staan allebei permanent in de DOM (een
   dichte drawer wordt verborgen, niet verwijderd, §7.2b), en een
   pipeline-entry die in beide drawers voorkomt geeft dan twee elementen
   met hetzelfde id (`pipelineStage_604` bijvoorbeeld). `document.
   getElementById()` vindt dan de eerste, niet per se de zichtbare: na
   "klantdrawer > Pipeline > sluiten > kandidaatdrawer > Pipeline" werkte
   "Fase wijzigen" op de verborgen kopie in de klantdrawer, en de
   kandidaatdrawer bleef op zijn onopgeslagen select-waarde staan
   (code-reviewer, HIGH, claude/admin-pipeline). De twee panen zelf
   (`#candidateDrawerTabContent`, `#clientDrawerTabContent`) hebben wel
   allebei hun eigen, unieke id, dus `loadPipelineTab()`/`renderPipelineTab()`
   mogen die nog via `document.getElementById(containerId)` opzoeken; alles
   daaronder (`pipelineStage_<id>`, `pipelineHistoryWrap_<id>`,
   `pipelineEntryAlert_<id>`) niet meer.

   §7.6 besluit 2 / migratie 043 (BV8): de zeven canonieke fasen krijgen
   pas een gesloten CHECK-constraint nadat VALIDATE CONSTRAINT op productie
   is gedraaid. Migratie 043 zelf normaliseert echter al bij de deploy (elke
   bestaande rij krijgt daar een van de zeven waarden, met een vangnet naar
   'sourced'), en de CHECK staat vanaf diezelfde deploy als NOT VALID: dat
   slaat alleen de eenmalige tabelscan over, niet de handhaving zelf, dus
   elke INSERT en elke UPDATE op `stage` wordt al vanaf migratie 043
   geweigerd als de waarde buiten de zeven valt (zie het bestand zelf voor
   die redenering). Na migratie 043 kan `stage` op een bestaande rij dus
   normaal gesproken geen onbekende waarde meer dragen -- de
   "(bestaande waarde)"-klep in dit bestand is een vangnet, niet de
   verwachte hoofdroute: hij vangt `stage: null` op (de kolom heeft geen
   NOT NULL, dus een rij die nooit een schrijfactie via de geldige paden
   doorliep kan hem nog missen) en een rij die buiten de applicatie om is
   gewijzigd (een handmatige UPDATE, een toekomstige migratie die de
   constraint weer aanpast). PIPELINE_STAGE_VALIDATED is de vlag die dat
   vangnet aan of uit zet: false (nu) houdt de klep open, true (na
   VALIDATE CONSTRAINT, handmatig om te zetten -- zie het draaiboek
   onderaan migrations/043_pipeline_stage_check.py) sluit de select tot
   precies de zeven opties.
   ============================================================ */
const PIPELINE_STAGE_VALIDATED = false;

Object.assign(Admin, {
  // Ook op Admin gezet (niet alleen als losse const hierboven), zodat
  // scripts/admin_sections_check.py de klep voor een onbekende, niet-lege
  // fase kan testen alsof VALIDATE CONSTRAINT al gedraaid is: Admin.
  // PIPELINE_STAGE_VALIDATED = true; in een page.evaluate() zonder het
  // bestand zelf aan te raken. pipelineStageOptions() hieronder leest
  // altijd deze eigenschap, nooit de const rechtstreeks.
  PIPELINE_STAGE_VALIDATED,

  // filterKey is 'candidate_id' of 'client_id'; filterId het bijbehorende
  // id. opts.showCandidateName: de klantdrawer toont meerdere kandidaten
  // door elkaar (één client_id, veel candidate_id's), dus die zet dit aan;
  // de kandidaatdrawer laat het weg -- de kaart staat al in het dossier
  // van die ene kandidaat, dus de eigen naam nog eens tonen voegt niets
  // toe (§7.3.4 zelf noemt de naam alleen in de context van de
  // dataherkomst, niet als vast onderdeel van de kaart).
  async loadPipelineTab(containerId, filterKey, filterId, opts = {}) {
    const el = document.getElementById(containerId);
    if (!el) return;
    mount(el, html`${[0, 1, 2].map(() => html`<div class="a-skel-block"></div>`)}`);
    try {
      const qs = new URLSearchParams();
      qs.set(filterKey, filterId);
      qs.set('limit', 200);
      const res = await Auth.fetch(`/v1/admin/pipeline?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error();
      this.renderPipelineTab(containerId, data.items || [], opts);
    } catch {
      this.setContainerLoadError(el, () => this.loadPipelineTab(containerId, filterKey, filterId, opts));
    }
  },

  // De <select> biedt de zeven canonieke fasen aan, in spec-volgorde
  // (AdminLabels.pipelineStages). Een fase daarbuiten (mogelijk zolang
  // PIPELINE_STAGE_VALIDATED false is) komt er als achtste, geselecteerde
  // optie bij, met het achtervoegsel "(bestaande waarde)": de select
  // verbergt hem niet en kiest ook niet in zijn plaats een van de zeven.
  // security-auditor LOW op claude/admin-pipeline: currentStage null (de
  // kolom heeft geen NOT NULL) sloeg deze klep vroeger over, dus de
  // browser koos zelf stil de eerste optie ('sourced') en "Fase wijzigen"
  // zou zonder enige keuze een PATCH sturen. Een lege waarde krijgt nu
  // dezelfde klep, met "(leeg)" in plaats van de rauwe waarde als label.
  // code-reviewer LOW (herchecks op 3951578): dat geldt ook wanneer
  // PIPELINE_STAGE_VALIDATED ooit op true gaat -- de CHECK-constraint uit
  // migratie 043 laat NULL gewoon door (een CHECK slaat NULL altijd over,
  // dat is SQL-standaardgedrag), dus VALIDATE CONSTRAINT bewijst niets
  // over een lege `stage`. De klep voor een lege waarde blijft daarom
  // onvoorwaardelijk aan, los van de vlag; alleen de klep voor een
  // ONBEKENDE, niet-lege waarde vervalt na VALIDATE.
  pipelineStageOptions(currentStage) {
    const stages = AdminLabels.pipelineStages || [];
    const known = stages.includes(currentStage);
    const opts = stages.map(s => html`
      <option value="${s}" ${raw(s === currentStage ? 'selected' : '')}>${AdminLabels.label('pipelinefase', s)}</option>`);
    if (!known && (!this.PIPELINE_STAGE_VALIDATED || currentStage == null)) {
      const value = currentStage ?? '';
      const label = currentStage ?? '(leeg)';
      opts.push(html`<option value="${value}" selected>${label} (bestaande waarde)</option>`);
    }
    return opts;
  },

  renderPipelineTab(containerId, items, opts = {}) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!items.length) {
      mount(el, html`<div class="a-state-block">Nog geen pipeline-entries.</div>`);
      return;
    }
    // §7.3.4: "bij meer dan drie entries een accordeon met alleen de
    // nieuwste opengeklapt". GET /admin/pipeline sorteert al
    // ORDER BY pe.created_at DESC, pe.id DESC (routers/admin.py), dus
    // items[0] is de nieuwste zonder dat dit bestand opnieuw hoeft te
    // sorteren.
    const useAccordion = items.length > 3;
    mount(el, html`${items.map((entry, i) => {
      const jobLabel = entry.job_title
        ? html`${entry.job_title} <span class="a-soft">(#${entry.job_id})</span>`
        : html`Vacature #${entry.job_id}`;
      const heading = opts.showCandidateName
        ? html`${entry.full_name || 'Onbekende kandidaat'} <span class="a-soft">· ${jobLabel}</span>`
        : html`Vacature: ${jobLabel}`;
      const body = this.pipelineEntryBody(entry);
      if (useAccordion) {
        return html`<details class="card mb-3 a-disclosure" id="pipelineEntry_${entry.id}" ${raw(i === 0 ? 'open' : '')}>
          <summary>${heading}</summary>
          <div class="card-body">${body}</div>
        </details>`;
      }
      return html`<div class="a-panel mb-3" id="pipelineEntry_${entry.id}"><h4 class="a-cell-strong mb-2">${heading}</h4>${body}</div>`;
    })}`);
    if (useAccordion) {
      // code-reviewer LOW op claude/admin-pipeline: een dichtgeklapte kaart
      // hoeft zijn historie niet meteen op te halen. De nieuwste (open bij
      // render, i === 0 hierboven) laadt meteen; de rest pas op het eigen
      // toggle-event van zijn <details>, één keer (zoals
      // #retentionTableDetails in retention.js dat al doet).
      this.loadPipelineHistory(items[0].id, el);
      items.slice(1).forEach((entry) => {
        const node = el.querySelector(`#pipelineEntry_${entry.id}`);
        if (!node) return;
        node.addEventListener('toggle', () => {
          if (node.open && node.dataset.gspHistoryLoaded !== '1') {
            node.dataset.gspHistoryLoaded = '1';
            this.loadPipelineHistory(entry.id, el);
          }
        });
      });
    } else {
      items.forEach(entry => this.loadPipelineHistory(entry.id, el));
    }
  },

  // code-reviewer LOW op claude/admin-pipeline: de oude tab Matches toonde
  // `updated_at` ("Bijgewerkt"). De tab Pipeline haalt "Laatst gewijzigd"
  // in plaats daarvan uit de historie, en die kan ontbreken (geen historie,
  // of een historiefout) -- dan stond er nergens meer een datum bij een
  // kaart die er toch echt een heeft. `updated_at` staat er daarom altijd,
  // onafhankelijk van de historie.
  pipelineEntryBody(entry) {
    return html`
      <div id="pipelineEntryAlert_${entry.id}"></div>
      <div class="a-pipeline-controls">
        <div class="form-group mb-0">
          <label class="form-label" for="pipelineStage_${entry.id}">Huidige fase</label>
          <select class="form-select" id="pipelineStage_${entry.id}" data-original-stage="${entry.stage ?? ''}">${this.pipelineStageOptions(entry.stage)}</select>
        </div>
        <button type="button" class="btn btn-primary" data-action="pipeline-change-stage"
          data-entry-id="${entry.id}">Fase wijzigen</button>
      </div>
      <div class="a-meta mb-2">Bijgewerkt: ${this.retentionDate(entry.updated_at)}</div>
      <div id="pipelineHistoryWrap_${entry.id}">
        ${[0, 1, 2].map(() => html`<div class="a-skel-block"></div>`)}
      </div>
    `;
  },

  // §7.3.4 "Fase wijzigen": geen automatische opslag bij het wisselen van
  // de select (de <select> zelf toont de gekozen waarde al -- dat IS de
  // optimistische update), pas bij deze klik gaat de PATCH eruit. Bij een
  // 4xx/5xx draait dit de select terug naar de laatst bevestigde waarde
  // (data-original-stage) en toont een inline-melding boven de kaart; bij
  // succes wordt alleen de historie van deze entry opnieuw opgehaald, niet
  // lokaal aangevuld. `root` is de `.a-tabpane` van de drawer die de klik
  // deed (zie de moduledoc hierboven) -- nooit weglaten voor een geopende
  // drawer.
  async changePipelineStage(entryId, root) {
    const scope = root || document;
    const selectEl = scope.querySelector(`#pipelineStage_${entryId}`);
    const btnEl = scope.querySelector(`[data-action="pipeline-change-stage"][data-entry-id="${entryId}"]`);
    if (!selectEl || !btnEl || btnEl.disabled) return;
    this.pipelineEntryAlert(entryId, '', root);
    const newStage = selectEl.value;
    const stages = AdminLabels.pipelineStages || [];
    // De ontsnappingsklep-optie mag nooit verzonden worden, ook niet
    // wanneer ze toevallig de geselecteerde waarde is gebleven (§7.3.4:
    // "de UI schrijft nooit stilzwijgend een onbekende fase weg").
    if (!stages.includes(newStage)) {
      this.pipelineEntryAlert(entryId, 'Kies een van de zeven fasen om op te slaan; de huidige waarde is alleen ter informatie te zien.', root);
      return;
    }
    const originalStage = selectEl.dataset.originalStage;
    if (newStage === originalStage) return; // geen wijziging, niets te bewaren.

    btnEl.disabled = true;
    selectEl.disabled = true;
    const prevLabel = btnEl.innerHTML;
    mount(btnEl, html`<i class="fa-solid fa-spinner fa-spin"></i> Fase wijzigen`);
    try {
      const res = await Auth.fetch(`/v1/admin/pipeline/${entryId}/stage`, {
        method: 'PATCH', body: JSON.stringify({ stage: newStage }),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        selectEl.dataset.originalStage = newStage;
        Auth.toast('Fase bijgewerkt', 'success');
        await this.loadPipelineHistory(entryId, root);
        btnEl.disabled = false;
        selectEl.disabled = false;
        mount(btnEl, raw(prevLabel));
        return;
      }
      selectEl.value = originalStage;
      this.pipelineEntryAlert(entryId, this.pipelineStageErrorText(data, res && res.status), root);
    } catch {
      selectEl.value = originalStage;
      this.pipelineEntryAlert(entryId, 'Netwerkfout, probeer het opnieuw.', root);
    }
    btnEl.disabled = false;
    selectEl.disabled = false;
    mount(btnEl, raw(prevLabel));
  },

  pipelineStageErrorText(data, status) {
    if (status === 401 || status === 403) return 'Je hebt geen rechten voor deze handeling.';
    if (status === 404) return 'Deze pipeline-entry bestaat niet meer. Ververs de pagina.';
    if (status === 422) return 'Deze fase is ongeldig. Kies een van de zeven fasen.';
    const d = this.errorDetail(data);
    if (d.message) return d.message;
    return 'Er ging iets mis, probeer het opnieuw.';
  },

  pipelineEntryAlert(entryId, text, root) {
    const el = (root || document).querySelector(`#pipelineEntryAlert_${entryId}`);
    if (!el) return;
    if (!text) { mount(el, ''); return; }
    mount(el, html`
      <div class="alert alert-danger" role="alert">
        <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
        <span>${text}</span>
      </div>`);
  },

  // security-auditor LOW op claude/admin-pipeline (herchecks op 3951578):
  // twee aanroepen voor dezelfde entry kunnen overlappen (een trage
  // initiële GET terwijl een geslaagde PATCH meteen zijn eigen herlading
  // start), en zonder volgnummer wint welke respons dan ook het laatst
  // binnenkomt -- een trage eerste GET zou de verse herlading na de PATCH
  // zo kunnen overschrijven met de OUDE fase. `wrap._pipelineHistorySeq`
  // is het volgnummer van de laatst GESTARTE aanroep voor deze wrap; een
  // respons die niet meer de nieuwste aanroep is (seq komt niet meer
  // overeen) wordt genegeerd, in zowel het succes- als het foutpad.
  async loadPipelineHistory(entryId, root) {
    const wrap = (root || document).querySelector(`#pipelineHistoryWrap_${entryId}`);
    if (!wrap) return;
    const seq = wrap._pipelineHistorySeq = (wrap._pipelineHistorySeq || 0) + 1;
    mount(wrap, html`${[0, 1, 2].map(() => html`<div class="a-skel-block"></div>`)}`);
    try {
      const res = await Auth.fetch(`/v1/admin/pipeline/${entryId}/history`);
      if (!res) return;
      const data = await res.json();
      if (seq !== wrap._pipelineHistorySeq) return; // een nieuwere aanroep won al
      if (!res.ok) throw new Error();
      // §7.3.4: de route sorteert ORDER BY h.changed_at (oplopend, append-
      // only logboek); de tijdlijn toont nieuwste boven, dus hier
      // aflopend, met id als tiebreak bij een gelijke timestamp.
      wrap._pipelineHistoryItems = (data.items || []).slice().sort((a, b) => {
        const diff = new Date(b.changed_at) - new Date(a.changed_at);
        return diff !== 0 ? diff : (b.id || 0) - (a.id || 0);
      });
      this.renderPipelineHistory(entryId, false, root);
    } catch {
      if (seq !== wrap._pipelineHistorySeq) return;
      this.setContainerLoadError(wrap, () => this.loadPipelineHistory(entryId, root));
    }
  },

  pipelineActorLabel(item) {
    if (item.changed_by_name) return item.changed_by_name;
    if (item.changed_by != null) return `Gebruiker #${item.changed_by}`;
    return 'Onbekend';
  },

  // "<van> → <naar>" (§7.3.4): een rechterpijl (U+2192), geen streepje en
  // geen em-dash. from_stage: null toont als "(nieuw)"; elke waarde gaat
  // door dezelfde labelmap als de select, met de ruwe waarde als terugval.
  pipelineStageChangeLabel(item) {
    const from = item.from_stage == null
      ? '(nieuw)'
      : AdminLabels.label('pipelinefase', item.from_stage, item.from_stage);
    const to = AdminLabels.label('pipelinefase', item.to_stage, item.to_stage);
    return html`${from} → ${to}`;
  },

  pipelineDateTime(d) {
    if (!d) return '—';
    const dt = new Date(d);
    if (isNaN(dt.getTime())) return '—';
    const date = dt.toLocaleDateString('nl-NL', { day: 'numeric', month: 'short', year: 'numeric' });
    const time = dt.toLocaleTimeString('nl-NL', { hour: '2-digit', minute: '2-digit' });
    return `${date} ${time}`;
  },

  // showAll: true toont alle items (na een klik op "Toon alles"), anders
  // de eerste tien (§7.3.4: "Maximaal tien items zichtbaar, daarna 'Toon
  // alles'"). Leest wrap._pipelineHistoryItems, gezet door
  // loadPipelineHistory hierboven -- dat veld overleeft deze functie's
  // eigen mount() omdat die alleen de innerHTML van wrap vervangt, niet
  // wrap zelf.
  renderPipelineHistory(entryId, showAll, root) {
    const wrap = (root || document).querySelector(`#pipelineHistoryWrap_${entryId}`);
    if (!wrap) return;
    const sorted = wrap._pipelineHistoryItems || [];
    if (!sorted.length) {
      mount(wrap, html`<div class="a-state-block">Nog geen fasewijzigingen vastgelegd.</div>`);
      return;
    }
    const last = sorted[0];
    const MAX_VISIBLE = 10;
    const visible = showAll ? sorted : sorted.slice(0, MAX_VISIBLE);
    const hasMore = !showAll && sorted.length > MAX_VISIBLE;
    mount(wrap, html`
      <div class="a-meta mb-2">Laatst gewijzigd: ${this.retentionDate(last.changed_at)} door ${this.pipelineActorLabel(last)}</div>
      <ul class="a-timeline">
        ${visible.map((it, i) => html`
          <li class="a-timeline__item${raw(i === 0 ? ' a-timeline__item--newest' : '')}">
            <div class="a-num fs-xs">${this.pipelineDateTime(it.changed_at)}</div>
            <div>${this.pipelineStageChangeLabel(it)}</div>
            <div class="a-soft fs-xs">${this.pipelineActorLabel(it)}</div>
          </li>`)}
      </ul>
      ${hasMore ? html`<button type="button" class="btn btn-sm btn-ghost-secondary" data-action="pipeline-history-show-all" data-entry-id="${entryId}">Toon alles</button>` : ''}
    `);
  },
});

/* ============================================================
   ACTIVITEITENTAB (§7.3.6(b)): "Activiteit" in de kandidaat- (candidates.js,
   verving daar de eigen platte tabel) en de klantdrawer (clients.js,
   verving daar "Notities/Activiteit"). Eén gedeelde implementatie, net als
   de tab Pipeline hierboven: `loadActivityTab()`/`renderActivityTab()`
   lezen en schrijven altijd via `containerId`
   (`candidateDrawerTabContent` / `clientDrawerTabContent`), niet via een
   losstaand element-id, dus er is geen kans op de kruisdrawer-botsing die
   de Pipeline-tab wel kende (elke pipeline-entry kan in beide drawers
   voorkomen met hetzelfde id; een activiteit hoort altijd bij precies één
   subject, dus dat risico bestaat hier niet, maar de state leeft toch aan
   het containerelement zelf -- `el._activity*` -- in plaats van in een
   module-brede variabele, om twee gelijktijdig geopende drawers met
   allebei een open formulier niet met elkaar te laten overschrijven).

   GET/POST /api/v1/admin/activities geven geen naam bij `created_by`
   (alleen het user-id, anders dan BV7's `changed_by_name` voor de
   pipeline-historie): `activityActorLabel()` valt daarom terug op
   "Gebruiker #<id>", dezelfde vorm als `pipelineActorLabel()` zonder
   naam.
   ============================================================ */
Object.assign(Admin, {
  activityActorLabel(a) {
    if (a.created_by != null) return `Gebruiker #${a.created_by}`;
    return 'Onbekend';
  },

  async loadActivityTab(containerId, subjectType, subjectId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    mount(el, html`${[0, 1, 2].map(() => html`<div class="a-skel-block"></div>`)}`);
    try {
      const qs = new URLSearchParams({ subject_type: subjectType, subject_id: subjectId, limit: 50 });
      const res = await Auth.fetch(`/v1/admin/activities?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error();
      el._activitySubjectType = subjectType;
      el._activitySubjectId = subjectId;
      el._activityItems = (data.items || []).slice().sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      el._activityFormOpen = false;
      this.renderActivityTab(containerId);
    } catch {
      this.setContainerLoadError(el, () => this.loadActivityTab(containerId, subjectType, subjectId));
    }
  },

  toggleActivityForm(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el._activityFormOpen = !el._activityFormOpen;
    this.renderActivityTab(containerId);
  },

  renderActivityTab(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const items = el._activityItems || [];
    const formOpen = !!el._activityFormOpen;
    const subjectType = el._activitySubjectType;
    const subjectId = el._activitySubjectId;
    const types = Object.keys(AdminLabels.maps.activiteit);

    const list = items.length ? html`
      <ul class="a-timeline">
        ${items.map(a => html`
          <li class="a-timeline__item">
            <div class="d-flex align-items-center gap-2 flex-wrap">
              <span class="${this.badge(a.type)}">${this.activityTypeLabel(a.type)}</span>
              <span class="a-num fs-xs">${this.pipelineDateTime(a.created_at)}</span>
            </div>
            ${a.type === 'task' ? html`
              <label class="form-check mt-1 mb-0">
                <input class="form-check-input" type="checkbox" data-action="activity-toggle-task"
                  data-id="${a.id}" data-container="${containerId}" ${raw(a.completed_at ? 'checked' : '')}>
                <span class="form-check-label">${a.body || '—'}</span>
              </label>
            ` : html`<div class="mt-1">${a.body || '—'}</div>`}
            <div class="a-soft fs-xs mt-1">${this.activityActorLabel(a)}</div>
          </li>`)}
      </ul>` : html`<div class="a-state-block">Nog geen activiteiten vastgelegd.</div>`;

    mount(el, html`
      <div class="mb-3">
        <button type="button" class="btn btn-sm btn-ghost-secondary" data-action="activity-toggle-form" data-container="${containerId}">
          <i class="fa-solid fa-plus me-1" aria-hidden="true"></i>Activiteit toevoegen
        </button>
      </div>
      ${formOpen ? html`
        <div class="a-panel mb-3">
          <div class="form-group mb-2">
            <label class="form-label" for="${containerId}_activityType">Type</label>
            <select class="form-select" id="${containerId}_activityType">
              ${types.map(t => html`<option value="${t}">${AdminLabels.label('activiteit', t)}</option>`)}
            </select>
          </div>
          <div class="form-group mb-2">
            <label class="form-label" for="${containerId}_activityBody">Notitie</label>
            <textarea class="a-textarea" id="${containerId}_activityBody" rows="3"></textarea>
          </div>
          <div id="${containerId}_activityAlert"></div>
          <button type="button" class="btn btn-primary btn-sm" data-action="activity-submit"
            data-container="${containerId}" data-subject-type="${subjectType}" data-subject-id="${subjectId}">Vastleggen</button>
        </div>
      ` : ''}
      ${list}
    `);
  },

  activityAlert(elId, text) {
    const el = document.getElementById(elId);
    if (!el) return;
    if (!text) { mount(el, ''); return; }
    mount(el, html`
      <div class="alert alert-danger" role="alert">
        <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
        <span>${text}</span>
      </div>`);
  },

  async submitActivity(containerId, subjectType, subjectId) {
    const alertId = `${containerId}_activityAlert`;
    this.activityAlert(alertId, '');
    const typeEl = document.getElementById(`${containerId}_activityType`);
    const bodyEl = document.getElementById(`${containerId}_activityBody`);
    const type = typeEl?.value;
    if (!type) return;
    const body = (bodyEl?.value || '').trim();
    const btn = document.querySelector(`[data-action="activity-submit"][data-container="${containerId}"]`);
    if (btn) btn.disabled = true;
    try {
      const res = await Auth.fetch('/v1/admin/activities', {
        method: 'POST',
        body: JSON.stringify({ subject_type: subjectType, subject_id: Number(subjectId), type, body: body || null }),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        Auth.toast('Activiteit vastgelegd', 'success');
        await this.loadActivityTab(containerId, subjectType, Number(subjectId));
        return;
      }
      this.activityAlert(alertId, this.errorDetail(data).message || 'Vastleggen mislukt, probeer het opnieuw.');
    } catch {
      this.activityAlert(alertId, 'Netwerkfout, probeer het opnieuw.');
    }
    if (btn) btn.disabled = false;
  },

  // Optimistisch: de checkbox staat al om (het click-event vuurt na de
  // browsereigen toggle), dus alleen bij een mislukte PATCH draait dit
  // terug. Geen volledige herrender: dat zou een tegelijk openstaand
  // formulier of een andere aangevinkte taak resetten.
  async toggleActivityTask(containerId, activityId, nowChecked) {
    const el = document.getElementById(containerId);
    const checkboxEl = document.querySelector(
      `[data-action="activity-toggle-task"][data-id="${activityId}"][data-container="${containerId}"]`);
    try {
      const res = await Auth.fetch(`/v1/admin/activities/${activityId}`, {
        method: 'PATCH',
        body: JSON.stringify({ completed_at: nowChecked ? new Date().toISOString() : null }),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        const item = (el?._activityItems || []).find(a => a.id === activityId);
        if (item) item.completed_at = (data && 'completed_at' in data) ? data.completed_at : (nowChecked ? new Date().toISOString() : null);
        Auth.toast('Taak bijgewerkt', 'success');
        return;
      }
      if (checkboxEl) checkboxEl.checked = !nowChecked;
      Auth.toast('Bijwerken mislukt', 'error');
    } catch {
      if (checkboxEl) checkboxEl.checked = !nowChecked;
      Auth.toast('Netwerkfout', 'error');
    }
  },
});

Admin.registerActions({
  'activity-toggle-form': (el) => Admin.toggleActivityForm(el.dataset.container),
  'activity-submit': (el) => Admin.submitActivity(el.dataset.container, el.dataset.subjectType, el.dataset.subjectId),
  'activity-toggle-task': (el) => Admin.toggleActivityTask(el.dataset.container, Number(el.dataset.id), el.checked),
});

/* Het dashboard blijft in de kern (Admin.init() laadt het zelf al), maar
   staat wel in dezelfde registry zodat nav.js één bron heeft. */
Admin.registerSection({
  id: 'dashboard',
  title: 'Dashboard',
  loader: () => Admin.loadDashboard(),
  filters: [],
});

function debounce(fn, delay) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
}
Admin.debounce = debounce;

document.addEventListener('DOMContentLoaded', () => {
  Admin.init();
  Admin.bindGlobal();
});
