/* ============================================================
   GSP Recruitment -- admin/js/sections/placements.js
   Plaatsingen: SITE-DESIGN-SPEC.md §7.3.3. Lijst, drie-tabs drawer
   (Overzicht/Financieel/Marge), aanmaken/bewerken, statuswisseling en
   verwijderen.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern), ui.js, labels.js en jobs.js (Admin.fetchClientOptions), voor
   nav.js dat de registry uitleest. Geen ES-module: de rest van de site
   gebruikt die ook niet.

   Endpoints (talent-os/backend/routers/placements.py, nagelezen):
     GET    /v1/admin/placements?status=&candidate_id=&job_id=&client_id=
            &limit=&offset=&sort=&order=  -> { items, total }
     GET    /v1/admin/placements/{id}                 -> PlacementResponse
     POST   /v1/admin/placements                      -> PlacementResponse (201)
     PATCH  /v1/admin/placements/{id}                  -> PlacementResponse
     POST   /v1/admin/placements/{id}/status           -> PlacementResponse
     DELETE /v1/admin/placements/{id}                  -> 204 (soft delete)
     GET    /v1/admin/placements/{id}/margin?gross_monthly_salary=&annual_salary=

   Velden en grenzen komen uit models/schemas.py (_PLACEMENT_TYPES,
   _BILLING_BASES, _FEE_TYPES, _PLACEMENT_STATUSES, _money_field(),
   _eor_cost_factor_field(), _fee_percentage_field(),
   _expected_billable_hours_field(), OneOffCost) -- niet verzonnen.

   As-built afwijkingen van SITE-DESIGN-SPEC.md §7.3.3 (genummerd, zie ook
   de as-built-paragraaf in de spec zelf):

   1. De lijst heeft geen vrij zoekveld op de backend (list_placements
      kent alleen candidate_id als exacte match, geen ILIKE op naam). Het
      zoekveld "Kandidaat" lost daarom eerst op: een numerieke invoer gaat
      direct als candidate_id mee; een naam/e-mail wordt opgezocht via
      GET /v1/admin/candidates?search=... en alleen bij precies één
      treffer toegepast. Bij nul of meerdere treffers blijft de lijst
      ongefilterd op dat veld en verschijnt een toelichting onder het veld
      (resolvePlacementCandidateSearch()).
   2. De lijst toont "Kandidaat #<id>" (zoals de bewaartermijnenlijst
      §7.3.1 al doet voor kandidaten) in plaats van een naam: er is geen
      join op de lijstroute en er bestaat geen goedkope naamslijst om op
      te slaan. Opdrachtgever en vacature worden wel met naam getoond,
      via de al bestaande GET /v1/admin/clients en GET /v1/admin/jobs
      (limit=200, dezelfde aanpak als Admin.fetchClientOptions in jobs.js
      en de vacaturetitel-opzoeking in candidates.js §7.3.2 afwijking 5).
   3. Alleen de kandidaat heeft een eigen drawer (openCandidateDrawer,
      altijd met kind 'sourced': placements.candidate_id is een
      candidates.id, dezelfde tabel als kind 'sourced' bevraagt) en de
      opdrachtgever (openClientDrawer). Er bestaat geen vacaturedrawer in
      dit paneel; de vacature staat in de Overzichttab als platte tekst.
   4. PlacementUpdate (PATCH) draagt geen candidate_id/job_id/client_id/
      placement_type -- die drie relaties en het type zijn dus alleen bij
      aanmaken in te stellen. Het bewerkmodal toont ze bij bewerken als
      alleen-lezen samenvatting, niet als selects.
   5. ui.modal kent geen .modal-lg letterlijk; `wide: true` geeft
      dezelfde 760px breedte die het Opdrachtgevers-detailpaneel al
      gebruikt (a-modal--wide, admin.css). Functioneel hetzelfde
      component als de spec bedoelt.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  const PLACEMENT_TRANSITIONS = {
    concept: ['actief', 'geannuleerd'],
    actief: ['beeindigd', 'geannuleerd'],
    beeindigd: [],
    geannuleerd: [],
  };

  // Backend-grenzen, letterlijk uit models/schemas.py overgenomen
  // (_money_field, _eor_cost_factor_field, _fee_percentage_field,
  // _expected_billable_hours_field) -- niet verzonnen.
  const MONEY_MAX = 99999999.99;
  const EOR_FACTOR_MAX = 99.9999;
  const FEE_PERCENTAGE_MAX = 100;
  const HOURS_MAX = 9999.99;

  const WARNING_SENTENCE = 'Voorlopig. Deze berekening is nog niet door de eigenaar vastgesteld en mag niet naar buiten.';

  // Komma of punt als decimaalteken (spec §7.3.3); genormaliseerd naar een
  // punt en gevalideerd tegen precies de grens die de backend ook
  // toepast. Geen minteken toegestaan: alle plaatsingsbedragen zijn
  // niet-negatief (ge=0 op elk veld in models/schemas.py).
  function parsePlacementDecimal(input, opts = {}) {
    const decimals = opts.decimals == null ? 2 : opts.decimals;
    const max = opts.max;
    const str = String(input == null ? '' : input).trim();
    if (!str) return { ok: true, value: null };
    const sepCount = (str.match(/[.,]/g) || []).length;
    if (sepCount > 1) return { ok: false, error: 'Gebruik één decimaalteken.' };
    const normalized = str.replace(',', '.');
    const re = new RegExp(`^\\d+(\\.\\d{1,${decimals}})?$`);
    if (!re.test(normalized)) {
      return { ok: false, error: `Gebruik een positief getal met maximaal ${decimals} decimalen.` };
    }
    const value = Number(normalized);
    if (max !== undefined && value > max) {
      const maxDisplay = max.toLocaleString('nl-NL', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
      return { ok: false, error: `Dit veld mag maximaal ${maxDisplay} zijn.` };
    }
    return { ok: true, value };
  }

  Object.assign(Admin, {
  /* ============================================================
     OPTIEBRONNEN: kandidaat/opdrachtgever/vacature, gedeeld door de
     lijst, de drawer en het formulier.
     ============================================================ */
  async fetchPlacementClientOptions(force = false) {
    // fetchClientOptions komt uit jobs.js (Admin.fetchClientOptions,
    // GET /v1/admin/clients?limit=200) -- zelfde cache, geen tweede
    // aanroep nodig.
    const clients = await this.fetchClientOptions(force);
    this._data.placementClientMap = new Map(clients.map(c => [c.id, c.company_name]));
    return this._data.placementClientMap;
  },

  async fetchPlacementJobOptions(force = false) {
    if (!force && this._data.placementJobMap) return this._data.placementJobMap;
    try {
      const res = await Auth.fetch('/v1/admin/jobs?limit=200');
      const data = res && res.ok ? await res.json() : { items: [] };
      this._data.placementJobMap = new Map((data.items || []).map(j => [
        j.id, { title: j.title || `Vacature #${j.id}`, client_id: j.client_id, company_name: j.company_name || null },
      ]));
    } catch {
      this._data.placementJobMap = this._data.placementJobMap || new Map();
    }
    return this._data.placementJobMap;
  },

  // Alleen kandidaten met een candidate_id (de FK die placements.candidate_id
  // moet raken -- routers/placements.py._validate_references SELECTeert
  // rechtstreeks uit `candidates`). Een self-registered kandidaat zonder
  // gekoppelde candidates-rij kan geen plaatsing krijgen en staat hier dus
  // niet in.
  async fetchPlacementCandidateOptions(force = false) {
    if (!force && this._data.placementCandidateOptions) return this._data.placementCandidateOptions;
    try {
      const res = await Auth.fetch('/v1/admin/candidates?limit=200');
      const data = res && res.ok ? await res.json() : { items: [] };
      this._data.placementCandidateOptions = (data.items || [])
        .map(c => ({
          candidateId: c.candidate_id != null ? c.candidate_id : (c.kind === 'sourced' ? c.id : null),
          fullName: c.full_name || null,
          email: c.email || null,
        }))
        .filter(c => c.candidateId != null);
    } catch {
      this._data.placementCandidateOptions = this._data.placementCandidateOptions || [];
    }
    return this._data.placementCandidateOptions;
  },

  placementClientLabel(id) {
    const map = this._data.placementClientMap;
    return (map && map.get(id)) || `Opdrachtgever #${id}`;
  },
  placementJobLabel(id) {
    const map = this._data.placementJobMap;
    const j = map && map.get(id);
    return j ? j.title : `Vacature #${id}`;
  },

  fillPlacementClientFilter() {
    const sel = document.getElementById('placementClientFilter');
    if (!sel) return;
    const current = sel.value;
    const map = this._data.placementClientMap || new Map();
    const rows = Array.from(map.entries()).sort((a, b) => String(a[1]).localeCompare(String(b[1]), 'nl'));
    mount(sel, html`
      <option value="">Alle opdrachtgevers</option>
      ${rows.map(([id, name]) => html`<option value="${id}" ${raw(String(id) === current ? 'selected' : '')}>${name}</option>`)}`);
  },

  /* ============================================================
     LIJST
     ============================================================ */
  placementsTable() {
    if (this._placementsTable) return this._placementsTable;
    this._placementsTable = ui.table({
      tbody: '#placementsBody',
      thead: '#placementsHead',
      // serverSort: BV10 levert sort/order op deze route (candidate_id,
      // client_id, job_id, start_date, end_date, status, id, created_at,
      // updated_at -- _PLACEMENT_SORT_COLUMNS in routers/placements.py).
      serverSort: true,
      page: { container: 'placementsPagination', section: 'placements', size: this._pageSize },
      empty: () => this.placementEmptyHtml(),
      cols: [
        { key: 'candidate_id', sortable: true },
        { key: 'client_id', sortable: true },
        { key: 'job_id', sortable: true },
        { key: 'placement_type' },
        { key: 'start_date', sortable: true },
        { key: 'end_date', sortable: true },
        { key: 'status', sortable: true },
        { key: '_actions' },
      ],
      load: (state) => this.fetchPlacementsList(state),
      render: (item) => this.renderPlacementRow(item),
    });
    return this._placementsTable;
  },

  placementEmptyHtml() {
    return html`Nog geen plaatsingen vastgelegd.
      <div class="a-meta mt-2">
        <button type="button" class="btn btn-sm btn-outline-secondary" data-action="open-new-placement-modal">Nieuwe plaatsing</button>
      </div>`;
  },

  async fetchPlacementsList(state) {
    const p = this._lastParams.placements || {};
    const qs = new URLSearchParams();
    if (p.status) qs.set('status', p.status);
    if (p.client_id) qs.set('client_id', p.client_id);
    if (p.candidate_id) qs.set('candidate_id', p.candidate_id);
    qs.set('limit', String(this._pageSize));
    qs.set('offset', String(((this._currentPage.placements || 1) - 1) * this._pageSize));
    if (state.sortKey) {
      qs.set('sort', state.sortKey);
      qs.set('order', state.sortDir || 'asc');
    }
    const res = await Auth.fetch(`/v1/admin/placements?${qs}`);
    if (!res) throw new Error('geen respons');
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error(this.errorDetail(data).message || 'fout');
    return data;
  },

  renderPlacementRow(p) {
    const statusLabel = AdminLabels.label('plaatsingstatus', p.status);
    const statusCls = AdminLabels.badgeClass('plaatsingstatus', p.status);
    return html`
      <tr>
        <td data-label="Kandidaat" class="a-num">Kandidaat #${p.candidate_id}</td>
        <td data-label="Opdrachtgever">${this.placementClientLabel(p.client_id)}</td>
        <td data-label="Vacature" class="a-hide-cardlist">${this.placementJobLabel(p.job_id)}</td>
        <td data-label="Type">${AdminLabels.label('plaatsingstype', p.placement_type)}</td>
        <td data-label="Start" class="a-hide-cardlist a-num a-num--date">${this.retentionDate(p.start_date)}</td>
        <td data-label="Einde" class="a-hide-cardlist a-num a-num--date">${p.end_date ? this.retentionDate(p.end_date) : '—'}</td>
        <td data-label="Status"><span class="${statusCls}">${statusLabel}</span></td>
        <td class="a-col-actions">
          <button type="button" class="btn btn-sm btn-primary" data-action="open-placement-drawer" data-id="${p.id}">Openen</button>
          <button type="button" class="btn btn-sm btn-ghost-secondary text-danger-ink a-hide-cardlist"
            data-action="confirm-delete-placement" data-id="${p.id}" title="Verwijderen" aria-label="Plaatsing #${p.id} verwijderen">
            <i class="fa-solid fa-trash"></i>
          </button>
        </td>
      </tr>`;
  },

  async loadPlacements(params) {
    if (params) this._lastParams.placements = params;
    await Promise.all([this.fetchPlacementClientOptions(), this.fetchPlacementJobOptions()]);
    this.fillPlacementClientFilter();
    await this.placementsTable().reload();
  },

  applyPlacementFilters() {
    this._currentPage.placements = 1;
    this.loadPlacements({
      status: document.getElementById('placementStatusFilter')?.value || undefined,
      client_id: document.getElementById('placementClientFilter')?.value || undefined,
      candidate_id: this._placementCandidateFilterId || undefined,
    });
  },

  // As-built afwijking 1 (zie bestandskop): geen vrij zoekveld op de
  // backend, dus dit lost eerst op naar een candidate_id.
  async resolvePlacementCandidateSearch(term) {
    const hint = document.getElementById('placementCandidateSearchHint');
    const setHint = (text) => { if (hint) mount(hint, text || ''); };
    const raw_ = (term || '').trim();
    if (!raw_) {
      this._placementCandidateFilterId = null;
      setHint('');
      this.applyPlacementFilters();
      return;
    }
    if (/^\d+$/.test(raw_)) {
      this._placementCandidateFilterId = raw_;
      setHint('');
      this.applyPlacementFilters();
      return;
    }
    const options = await this.fetchPlacementCandidateOptions();
    const needle = raw_.toLowerCase();
    const matches = options.filter(c =>
      (c.fullName || '').toLowerCase().includes(needle) || (c.email || '').toLowerCase().includes(needle));
    if (matches.length === 1) {
      this._placementCandidateFilterId = matches[0].candidateId;
      setHint('');
    } else if (matches.length === 0) {
      // Een candidate_id die geen enkele plaatsing heeft: een deterministisch
      // lege lijst in plaats van een aparte "geen resultaten"-staat.
      this._placementCandidateFilterId = '0';
      setHint('Geen kandidaat gevonden met deze naam.');
    } else {
      this._placementCandidateFilterId = null;
      setHint('Meerdere kandidaten gevonden. Verfijn de zoekopdracht of gebruik het kandidaat-ID.');
    }
    this.applyPlacementFilters();
  },

  /* ============================================================
     FOUTAFHANDELING (§7.2f)
     ============================================================ */
  placementErrorText(payload, status) {
    if (status === 401 || status === 403) return 'Je hebt geen rechten voor deze handeling.';
    const d = this.errorDetail(payload);
    if (d.code) console.warn('placements: API-foutcode', d.code);
    if (d.message) return d.message;
    return 'Er ging iets mis, probeer het opnieuw.';
  },

  placementAlert(containerId, text) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!text) { mount(el, ''); return; }
    mount(el, html`
      <div class="alert alert-danger" role="alert">
        <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
        <span>${text}</span>
      </div>`);
    el.scrollIntoView({ block: 'start' });
  },

  /* ============================================================
     DRAWER: Overzicht / Financieel / Marge
     ============================================================ */
  _placementTabs: [
    { key: 'overzicht', label: 'Overzicht' },
    { key: 'financieel', label: 'Financieel' },
    { key: 'marge', label: 'Marge' },
  ],

  openPlacementDrawer(placementId) {
    this._data.placementDetail = this._data.placementDetail || {};
    delete this._data.placementDetail[placementId];
    this._placementMarginState = this._placementMarginState || {};
    delete this._placementMarginState[placementId];
    this._placementDrawer = ui.drawer({
      id: 'placementDrawer',
      title: `Plaatsing #${placementId}`,
      tabs: this._placementTabs,
      tabAction: 'placement-tab',
      activeTab: 'overzicht',
      dataset: { id: placementId },
      body: html`<div id="placementDrawerTabContent" class="a-tabpane"><i class="fa-solid fa-spinner fa-spin"></i></div>`,
      onClose: () => { this._placementDrawer = null; },
    });
    this.switchPlacementTab(placementId, 'overzicht');
  },

  switchPlacementTab(placementId, tab) {
    if (this._placementDrawer) this._placementDrawer.selectTab(tab);
    const loaders = {
      overzicht: () => this.loadPlacementOverviewTab(placementId),
      financieel: () => this.loadPlacementFinancialTab(placementId),
      marge: () => this.loadPlacementMarginTab(placementId),
    };
    (loaders[tab] || loaders.overzicht)();
  },

  async ensurePlacementDetail(placementId, { force = false } = {}) {
    this._data.placementDetail = this._data.placementDetail || {};
    if (!force && this._data.placementDetail[placementId]) return this._data.placementDetail[placementId];
    const res = await Auth.fetch(`/v1/admin/placements/${placementId}`);
    if (!res) throw new Error('network');
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error(this.errorDetail(data).message || 'error');
    this._data.placementDetail[placementId] = data;
    return data;
  },

  /* ---- Tab: Overzicht ---- */
  async loadPlacementOverviewTab(placementId) {
    const el = document.getElementById('placementDrawerTabContent');
    if (!el) return;
    mount(el, html`<div class="a-state-block"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>`);
    try {
      await Promise.all([this.fetchPlacementClientOptions(), this.fetchPlacementJobOptions()]);
      const p = await this.ensurePlacementDetail(placementId);
      this.renderPlacementOverviewTab(p);
    } catch {
      this.setContainerLoadError(el, () => this.loadPlacementOverviewTab(placementId));
    }
  },

  renderPlacementOverviewTab(p) {
    const el = document.getElementById('placementDrawerTabContent');
    if (!el) return;
    const nextStatuses = PLACEMENT_TRANSITIONS[p.status] || [];
    mount(el, html`
      <div id="placementStatusAlert"></div>
      <div class="detail-grid mb-4">
        <div><div class="a-field-label">Kandidaat</div>
          <button type="button" class="btn btn-link p-0 a-num" data-action="open-candidate-from-placement" data-id="${p.candidate_id}">Kandidaat #${p.candidate_id}</button>
        </div>
        <div><div class="a-field-label">Opdrachtgever</div>
          <button type="button" class="btn btn-link p-0" data-action="open-client-from-placement" data-id="${p.client_id}">${this.placementClientLabel(p.client_id)}</button>
        </div>
        <div><div class="a-field-label">Vacature</div><div>${this.placementJobLabel(p.job_id)}</div></div>
        <div><div class="a-field-label">Type</div><div>${AdminLabels.label('plaatsingstype', p.placement_type)}</div></div>
        <div><div class="a-field-label">Startdatum</div><div class="a-num a-num--date">${this.retentionDate(p.start_date)}</div></div>
        <div><div class="a-field-label">Einddatum</div><div class="a-num a-num--date">${p.end_date ? this.retentionDate(p.end_date) : '—'}</div></div>
      </div>
      <div class="a-panel mb-4">
        <div class="a-field-label">Status</div>
        <div class="d-flex flex-wrap align-items-center gap-3 mb-3">
          <span class="${AdminLabels.badgeClass('plaatsingstatus', p.status)}">${AdminLabels.label('plaatsingstatus', p.status)}</span>
        </div>
        ${nextStatuses.length ? html`
          <label class="form-label" for="placementStatusSelect">Status wijzigen</label>
          <select class="form-select" id="placementStatusSelect">
            <option value="">Kies een nieuwe status…</option>
            ${nextStatuses.map(s => html`<option value="${s}">${AdminLabels.label('plaatsingstatus', s)}</option>`)}
          </select>` : html`<div class="a-soft">Deze status is definitief; er is geen overgang meer mogelijk.</div>`}
      </div>
      <div class="a-field-label">Notities</div>
      <div class="a-panel a-notes">${p.notes ? p.notes : html`<span class="a-soft">n.v.t.</span>`}</div>
    `);
    const statusSelect = document.getElementById('placementStatusSelect');
    if (statusSelect) {
      statusSelect.addEventListener('change', () => {
        const newStatus = statusSelect.value;
        if (newStatus) this.openPlacementStatusConfirm(p, newStatus, statusSelect);
      });
    }
  },

  openPlacementStatusConfirm(placement, newStatus, selectEl) {
    const isCancel = newStatus === 'geannuleerd';
    const body = html`
      <div id="placementStatusConfirmAlert"></div>
      <div class="a-panel">
        <div class="a-metric-row"><span class="a-soft">Huidige status</span>
          <span class="${AdminLabels.badgeClass('plaatsingstatus', placement.status)}">${AdminLabels.label('plaatsingstatus', placement.status)}</span></div>
        <div class="a-metric-row"><span class="a-soft">Nieuwe status</span>
          <span class="${AdminLabels.badgeClass('plaatsingstatus', newStatus)}">${AdminLabels.label('plaatsingstatus', newStatus)}</span></div>
      </div>`;
    const action = { label: 'Bevestigen', keepOpen: true, onClick: () => { this.submitPlacementStatus(handle, placement.id, newStatus); } };
    const handle = ui.modal({
      id: 'placementStatusModal',
      title: 'Status wijzigen',
      body,
      secondary: { label: 'Annuleren', onClick: () => { if (selectEl) selectEl.value = ''; } },
      // Uitzondering (§7.3.3): naar geannuleerd is de destructieve
      // variant, zonder getypte bevestiging (een annulering is
      // administratief omkeerbaar, maar wel een rode primaire knop).
      danger: isCancel ? { label: action.label, keepOpen: true, onClick: action.onClick } : null,
      primary: isCancel ? null : action,
      onClose: () => { if (selectEl) selectEl.value = ''; },
    });
  },

  async submitPlacementStatus(handle, placementId, newStatus) {
    this.placementAlert('placementStatusConfirmAlert', '');
    handle.setBusy(true);
    try {
      const res = await Auth.fetch(`/v1/admin/placements/${placementId}/status`, {
        method: 'POST', body: JSON.stringify({ status: newStatus }),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        handle.close();
        Auth.toast('Status bijgewerkt', 'success');
        await this.ensurePlacementDetail(placementId, { force: true });
        this.switchPlacementTab(placementId, 'overzicht');
        await this.loadPlacements(this._lastParams.placements || {});
        return;
      }
      this.placementAlert('placementStatusConfirmAlert', this.placementErrorText(data, res && res.status));
    } catch {
      this.placementAlert('placementStatusConfirmAlert', 'Netwerkfout, probeer het opnieuw.');
    }
    handle.setBusy(false);
  },

  /* ---- Tab: Financieel ---- */
  async loadPlacementFinancialTab(placementId) {
    const el = document.getElementById('placementDrawerTabContent');
    if (!el) return;
    mount(el, html`<div class="a-state-block"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>`);
    try {
      const p = await this.ensurePlacementDetail(placementId);
      this.renderPlacementFinancialTab(p);
    } catch {
      this.setContainerLoadError(el, () => this.loadPlacementFinancialTab(placementId));
    }
  },

  placementMoney(value) {
    if (value === null || value === undefined || value === '') return 'n.v.t.';
    const n = Number(value);
    if (!Number.isFinite(n)) return 'n.v.t.';
    return '€ ' + n.toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  },
  placementNumber(value, decimals = 2) {
    if (value === null || value === undefined || value === '') return 'n.v.t.';
    const n = Number(value);
    if (!Number.isFinite(n)) return 'n.v.t.';
    return n.toLocaleString('nl-NL', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  },

  renderPlacementFinancialTab(p) {
    const el = document.getElementById('placementDrawerTabContent');
    if (!el) return;
    const costs = Array.isArray(p.one_off_costs) ? p.one_off_costs : [];
    const total = costs.reduce((sum, c) => sum + (Number(c.amount) || 0), 0);
    const moneyRow = (label, value) => html`<div class="a-metric-row"><span class="a-soft">${label}</span><span class="a-num a-num--tab">${value}</span></div>`;
    const textRow = (label, value) => html`<div class="a-metric-row"><span class="a-soft">${label}</span><span>${value}</span></div>`;
    mount(el, html`
      <div class="d-flex justify-content-between align-items-center mb-3">
        <div class="a-field-label mb-0">Financieel</div>
        <button type="button" class="btn btn-sm btn-outline-secondary" data-action="open-placement-edit-modal" data-id="${p.id}">Bewerken</button>
      </div>
      ${textRow('Afrekenbasis', AdminLabels.label('afrekenbasis', p.billing_basis, 'n.v.t.'))}
      ${moneyRow('Uurtarief', this.placementMoney(p.hourly_bill_rate))}
      ${moneyRow('Verwachte factureerbare uren', this.placementNumber(p.expected_billable_hours))}
      ${moneyRow('Maandelijkse inkoopprijs', this.placementMoney(p.monthly_purchase_price))}
      ${textRow('EOR-partner', p.eor_partner || 'n.v.t.')}
      ${moneyRow('EOR-kostenfactor', this.placementNumber(p.eor_cost_factor, 4))}
      ${textRow('Feetype', AdminLabels.label('kostentype', p.fee_type, 'n.v.t.'))}
      ${moneyRow('Feepercentage', p.fee_percentage != null ? `${this.placementNumber(p.fee_percentage)}%` : 'n.v.t.')}
      ${moneyRow('Feebedrag', this.placementMoney(p.fee_amount))}
      <div class="a-field-label mt-4">Eenmalige kosten</div>
      ${costs.length ? html`
        <div class="a-panel">
          ${costs.map(c => html`<div class="a-metric-row"><span>${c.label}</span><span class="a-num a-num--tab">${this.placementMoney(c.amount)}</span></div>`)}
          <div class="a-metric-row"><span class="a-cell-strong">Totaal</span><span class="a-num a-num--tab a-cell-strong">${this.placementMoney(total)}</span></div>
        </div>` : html`<div class="a-soft">n.v.t.</div>`}
    `);
  },

  /* ---- Tab: Marge ---- */
  async loadPlacementMarginTab(placementId) {
    const el = document.getElementById('placementDrawerTabContent');
    if (!el) return;
    mount(el, html`<div class="a-state-block"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>`);
    try {
      const p = await this.ensurePlacementDetail(placementId);
      this.renderPlacementMarginForm(p);
      await this.recalculatePlacementMargin(p.id, p.placement_type);
    } catch {
      this.setContainerLoadError(el, () => this.loadPlacementMarginTab(placementId));
    }
  },

  renderPlacementMarginForm(p) {
    const el = document.getElementById('placementDrawerTabContent');
    if (!el) return;
    this._placementMarginState = this._placementMarginState || {};
    const state = this._placementMarginState[p.id] || {};
    const isDetachering = p.placement_type === 'detachering';
    mount(el, html`
      <div class="alert alert-warning" role="alert">
        <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
        <span>${WARNING_SENTENCE}</span>
      </div>
      <div id="placementMarginAlert"></div>
      <div class="form-group">
        ${isDetachering ? html`
          <label class="form-label" for="placementMarginGross">Bruto maandsalaris</label>
          <input type="text" inputmode="decimal" class="form-control" id="placementMarginGross"
            value="${state.gross != null ? state.gross : ''}" placeholder="Bijv. 5200,00">
          <div class="invalid-feedback" id="placementMarginGrossError"></div>` : html`
          <label class="form-label" for="placementMarginAnnual">Jaarsalaris</label>
          <input type="text" inputmode="decimal" class="form-control" id="placementMarginAnnual"
            value="${state.annual != null ? state.annual : ''}" placeholder="Bijv. 65000,00">
          <div class="invalid-feedback" id="placementMarginAnnualError"></div>`}
      </div>
      <div class="a-actions">
        <button type="button" class="btn btn-outline-secondary" id="placementMarginRecalc">Herberekenen</button>
      </div>
      <div class="a-field-label mt-4">Uitkomst</div>
      <div class="a-panel" id="placementMarginResult"><span class="a-soft">Nog niet berekend.</span></div>
    `);
    const btn = document.getElementById('placementMarginRecalc');
    if (btn) btn.addEventListener('click', () => this.recalculatePlacementMargin(p.id, p.placement_type));
  },

  async recalculatePlacementMargin(placementId, placementType) {
    const isDetachering = placementType === 'detachering';
    const inputId = isDetachering ? 'placementMarginGross' : 'placementMarginAnnual';
    const errId = isDetachering ? 'placementMarginGrossError' : 'placementMarginAnnualError';
    const inputEl = document.getElementById(inputId);
    const btn = document.getElementById('placementMarginRecalc');
    this.placementAlert('placementMarginAlert', '');
    if (!inputEl) return;
    const parsed = parsePlacementDecimal(inputEl.value, { decimals: 2, max: MONEY_MAX });
    const errEl = document.getElementById(errId);
    if (!parsed.ok) {
      inputEl.classList.add('is-invalid');
      if (errEl) errEl.textContent = parsed.error;
      return;
    }
    inputEl.classList.remove('is-invalid');
    if (errEl) errEl.textContent = '';
    this._placementMarginState = this._placementMarginState || {};
    this._placementMarginState[placementId] = {
      gross: isDetachering ? parsed.value : undefined,
      annual: !isDetachering ? parsed.value : undefined,
    };
    let restoreLabel = null;
    if (btn) { restoreLabel = btn.innerHTML; btn.disabled = true; mount(btn, html`<i class="fa-solid fa-spinner fa-spin"></i> Herberekenen`); }
    try {
      const qs = new URLSearchParams();
      if (isDetachering && parsed.value != null) qs.set('gross_monthly_salary', String(parsed.value));
      if (!isDetachering && parsed.value != null) qs.set('annual_salary', String(parsed.value));
      const res = await Auth.fetch(`/v1/admin/placements/${placementId}/margin?${qs}`);
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok && data) {
        this.renderPlacementMarginResult(data);
      } else {
        this.placementAlert('placementMarginAlert', this.placementErrorText(data, res && res.status));
      }
    } catch {
      this.placementAlert('placementMarginAlert', 'Netwerkfout, probeer het opnieuw.');
    }
    if (btn) { btn.disabled = false; mount(btn, raw(restoreLabel)); }
  },

  // null is hier altijd "n.v.t. (invoer ontbreekt)", nooit 0 (§7.3.3).
  placementMarginValue(v, isPercent) {
    if (v === null || v === undefined) return 'n.v.t. (invoer ontbreekt)';
    const n = Number(v);
    if (!Number.isFinite(n)) return 'n.v.t. (invoer ontbreekt)';
    const formatted = n.toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return isPercent ? `${formatted}%` : `€ ${formatted}`;
  },

  renderPlacementMarginResult(data) {
    const resultEl = document.getElementById('placementMarginResult');
    if (!resultEl) return;
    const row = (label, value) => html`<div class="a-metric-row"><span class="a-soft">${label}</span><span class="a-num a-num--tab">${value}</span></div>`;
    // "provisional zichtbaar herhalen" (§7.3.3): de waarschuwing staat ook
    // in elke uitkomst, niet alleen boven de invoervelden.
    mount(resultEl, html`
      <div class="alert alert-warning mb-3" role="alert">
        <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
        <span>${WARNING_SENTENCE}</span>
      </div>
      ${row('Omzet', this.placementMarginValue(data.revenue))}
      ${row('Kosten', this.placementMarginValue(data.cost))}
      ${row('Marge', this.placementMarginValue(data.margin))}
      ${row('Marge %', this.placementMarginValue(data.margin_pct, true))}
      ${row('Fee', this.placementMarginValue(data.fee))}
    `);
  },

  /* ============================================================
     STATUSWISSELING VANUIT DE LIJST ZELF (link naar candidate/client)
     ============================================================ */
  openCandidateFromPlacement(candidateId) {
    // placements.candidate_id is een candidates.id (routers/placements.py
    // ._validate_references SELECTeert rechtstreeks uit `candidates`), dus
    // kind is altijd 'sourced' -- geen ambiguïteit zoals bij de
    // kandidatenlijst zelf (die ook self-registered kandidaten toont).
    this.openCandidateDrawer('sourced', candidateId);
  },

  /* ============================================================
     VERWIJDEREN (getypte bevestiging: het plaatsings-ID)
     ============================================================ */
  confirmDeletePlacement(placementId) {
    const handle = ui.modal({
      id: 'placementDeleteModal',
      title: 'Plaatsing verwijderen',
      subtitle: 'Dit haalt de plaatsing uit elk overzicht.',
      body: html`<div id="placementDeleteAlert"></div>`,
      confirmText: String(placementId),
      secondary: { label: 'Annuleren' },
      danger: {
        label: 'Verwijderen',
        keepOpen: true,
        onClick: () => { this.submitDeletePlacement(handle, placementId); },
      },
    });
  },

  async submitDeletePlacement(handle, placementId) {
    this.placementAlert('placementDeleteAlert', '');
    handle.setBusy(true);
    try {
      const res = await Auth.fetch(`/v1/admin/placements/${placementId}`, { method: 'DELETE' });
      if (res && (res.ok || res.status === 204)) {
        handle.close();
        Auth.toast('Plaatsing verwijderd', 'success');
        if (this._placementDrawer) this._placementDrawer.close();
        await this.loadPlacements(this._lastParams.placements || {});
        return;
      }
      const data = res ? await res.json().catch(() => null) : null;
      this.placementAlert('placementDeleteAlert', this.placementErrorText(data, res && res.status));
    } catch {
      this.placementAlert('placementDeleteAlert', 'Netwerkfout, probeer het opnieuw.');
    }
    handle.setBusy(false);
  },

  /* ============================================================
     AANMAKEN EN BEWERKEN (§7.2d, in een .a-modal--wide)
     ============================================================ */
  async openPlacementFormModal(existing) {
    const isEdit = !!existing;
    const [clients, jobMap, candidates] = await Promise.all([
      this.fetchClientOptions(),
      this.fetchPlacementJobOptions(),
      this.fetchPlacementCandidateOptions(),
    ]);
    await this.fetchPlacementClientOptions();
    const jobList = Array.from(jobMap.entries()).map(([id, j]) => ({ id, ...j }));
    const oneOffCosts = (isEdit && Array.isArray(existing.one_off_costs))
      ? existing.one_off_costs.map(c => ({ label: c.label || '', amount: c.amount != null ? String(c.amount) : '' }))
      : [];

    const handle = ui.modal({
      id: 'placementFormModal',
      wide: true,
      title: isEdit ? `Plaatsing #${existing.id} bewerken` : 'Nieuwe plaatsing',
      body: this.placementFormBody({ isEdit, existing, clients, candidates, jobList, oneOffCosts }),
      secondary: { label: 'Annuleren' },
      primary: {
        label: isEdit ? 'Opslaan' : 'Plaatsing aanmaken',
        keepOpen: true,
        onClick: () => { this.submitPlacementForm(handle, isEdit, existing, oneOffCosts); },
      },
    });
    this.wirePlacementFormModal(handle, isEdit, existing, oneOffCosts);
  },

  async openPlacementEditFromDrawer(placementId) {
    try {
      const p = await this.ensurePlacementDetail(placementId);
      this.openPlacementFormModal(p);
    } catch {
      Auth.toast('Kon plaatsing niet laden', 'error');
    }
  },

  placementFormBody(ctx) {
    const { isEdit, existing, clients, candidates, jobList, oneOffCosts } = ctx;
    const money = (id, label, value) => html`
      <div class="col-md-6">
        <div class="form-group">
          <label class="form-label" for="${id}">${label}</label>
          <input type="text" inputmode="decimal" class="form-control" id="${id}" value="${value != null ? value : ''}">
          <div class="invalid-feedback" id="${id}Error"></div>
        </div>
      </div>`;
    return html`
      <div id="placementFormAlert"></div>
      ${isEdit ? html`
        <div class="a-panel mb-4">
          <div class="a-metric-row"><span class="a-soft">Kandidaat</span><span>Kandidaat #${existing.candidate_id}</span></div>
          <div class="a-metric-row"><span class="a-soft">Opdrachtgever</span><span>${this.placementClientLabel(existing.client_id)}</span></div>
          <div class="a-metric-row"><span class="a-soft">Vacature</span><span>${this.placementJobLabel(existing.job_id)}</span></div>
          <div class="a-metric-row"><span class="a-soft">Type</span><span>${AdminLabels.label('plaatsingstype', existing.placement_type)}</span></div>
        </div>
        <p class="fs-xs a-soft">Kandidaat, opdrachtgever, vacature en type zijn na het aanmaken niet meer te wijzigen.</p>
      ` : html`
        <div class="row">
          <div class="col-md-4">
            <div class="form-group">
              <label class="form-label" for="placementFormCandidate">Kandidaat *</label>
              <select class="form-select" id="placementFormCandidate">
                <option value="">(kies een kandidaat)</option>
                ${candidates.map(c => html`<option value="${c.candidateId}">Kandidaat #${c.candidateId}${c.fullName ? ' · ' + c.fullName : ''}</option>`)}
              </select>
              <div class="invalid-feedback" id="placementFormCandidateError"></div>
            </div>
          </div>
          <div class="col-md-4">
            <div class="form-group">
              <label class="form-label" for="placementFormClient">Opdrachtgever *</label>
              <select class="form-select" id="placementFormClient">
                <option value="">(kies een opdrachtgever)</option>
                ${clients.map(c => html`<option value="${c.id}">${c.company_name}</option>`)}
              </select>
              <div class="invalid-feedback" id="placementFormClientError"></div>
            </div>
          </div>
          <div class="col-md-4">
            <div class="form-group">
              <label class="form-label" for="placementFormJob">Vacature *</label>
              <select class="form-select" id="placementFormJob">
                <option value="">(kies een vacature)</option>
                ${jobList.map(j => html`<option value="${j.id}" data-client-id="${j.client_id}">${j.title}${j.company_name ? ' · ' + j.company_name : ''} · #${j.id}</option>`)}
              </select>
              <div class="invalid-feedback" id="placementFormJobError"></div>
            </div>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label" for="placementFormType">Type plaatsing *</label>
          <select class="form-select" id="placementFormType">
            <option value="">(kies een type)</option>
            <option value="werving_selectie">Werving & selectie</option>
            <option value="detachering">Detachering</option>
          </select>
          <div class="invalid-feedback" id="placementFormTypeError"></div>
        </div>
      `}
      <div class="row">
        <div class="col-md-6">
          <div class="form-group">
            <label class="form-label" for="placementFormStart">Startdatum</label>
            <input type="date" class="form-control" id="placementFormStart" value="${existing && existing.start_date ? existing.start_date : ''}">
          </div>
        </div>
        <div class="col-md-6">
          <div class="form-group">
            <label class="form-label" for="placementFormEnd">Einddatum</label>
            <input type="date" class="form-control" id="placementFormEnd" value="${existing && existing.end_date ? existing.end_date : ''}">
          </div>
        </div>
      </div>
      <div class="form-group">
        <label class="form-label" for="placementFormBillingBasis">Afrekenbasis</label>
        <select class="form-select" id="placementFormBillingBasis">
          <option value="">(geen)</option>
          <option value="vast_maandbedrag" ${raw(existing && existing.billing_basis === 'vast_maandbedrag' ? 'selected' : '')}>Vast maandbedrag</option>
          <option value="per_uur" ${raw(existing && existing.billing_basis === 'per_uur' ? 'selected' : '')}>Per uur</option>
        </select>
      </div>
      <div class="row">
        ${money('placementFormHourlyRate', 'Uurtarief (EUR)', existing && existing.hourly_bill_rate)}
        ${money('placementFormHours', 'Verwachte factureerbare uren', existing && existing.expected_billable_hours)}
      </div>
      <div class="row">
        ${money('placementFormMonthlyPrice', 'Maandelijkse inkoopprijs (EUR)', existing && existing.monthly_purchase_price)}
        <div class="col-md-6">
          <div class="form-group">
            <label class="form-label" for="placementFormEorPartner">EOR-partner</label>
            <input type="text" class="form-control" id="placementFormEorPartner" value="${(existing && existing.eor_partner) || ''}">
          </div>
        </div>
      </div>
      <div class="row">
        ${money('placementFormEorFactor', 'EOR-kostenfactor', existing && existing.eor_cost_factor)}
        <div class="col-md-6">
          <div class="form-group">
            <label class="form-label" for="placementFormFeeType">Feetype</label>
            <select class="form-select" id="placementFormFeeType">
              <option value="">(geen)</option>
              <option value="percentage" ${raw(existing && existing.fee_type === 'percentage' ? 'selected' : '')}>Percentage</option>
              <option value="vast" ${raw(existing && existing.fee_type === 'vast' ? 'selected' : '')}>Vast bedrag</option>
            </select>
          </div>
        </div>
      </div>
      <div class="row">
        ${money('placementFormFeePercentage', 'Feepercentage', existing && existing.fee_percentage)}
        ${money('placementFormFeeAmount', 'Feebedrag (EUR)', existing && existing.fee_amount)}
      </div>
      <div class="a-field-label mt-2">Eenmalige kosten</div>
      <div id="placementFormOneOffList">${this.placementOneOffRowsHtml(oneOffCosts)}</div>
      <button type="button" class="btn btn-sm btn-outline-secondary mb-3" id="placementFormOneOffAdd">Regel toevoegen</button>
      <div class="form-group">
        <label class="form-label" for="placementFormNotes">Notities</label>
        <textarea class="a-textarea" id="placementFormNotes" rows="3">${(existing && existing.notes) || ''}</textarea>
      </div>
    `;
  },

  placementOneOffRowsHtml(rows) {
    if (!rows.length) return html`<div class="a-soft mb-2">Nog geen eenmalige kosten.</div>`;
    return html`${rows.map((r, i) => html`
      <div class="row g-2 mb-2 align-items-start">
        <div class="col-6">
          <input type="text" class="form-control" placeholder="Omschrijving" maxlength="120"
            data-oneoff-field="label" data-oneoff-index="${i}" value="${r.label || ''}">
          <div class="invalid-feedback" id="placementOneOffLabelError${i}"></div>
        </div>
        <div class="col-4">
          <input type="text" inputmode="decimal" class="form-control" placeholder="Bedrag"
            data-oneoff-field="amount" data-oneoff-index="${i}" value="${r.amount || ''}">
          <div class="invalid-feedback" id="placementOneOffAmountError${i}"></div>
        </div>
        <div class="col-2">
          <button type="button" class="btn btn-ghost-secondary text-danger-ink" data-oneoff-remove="${i}" aria-label="Regel ${i + 1} verwijderen"><i class="fa-solid fa-trash"></i></button>
        </div>
      </div>`)}`;
  },

  wirePlacementFormModal(handle, isEdit, existing, oneOffCosts) {
    const bindOneOffEvents = () => {
      const list = document.getElementById('placementFormOneOffList');
      if (!list) return;
      list.querySelectorAll('[data-oneoff-field]').forEach(inp => {
        inp.addEventListener('input', () => {
          const idx = Number(inp.dataset.oneoffIndex);
          const field = inp.dataset.oneoffField;
          if (oneOffCosts[idx]) oneOffCosts[idx][field] = inp.value;
        });
      });
      list.querySelectorAll('[data-oneoff-remove]').forEach(btn => {
        btn.addEventListener('click', () => {
          const idx = Number(btn.dataset.oneoffRemove);
          oneOffCosts.splice(idx, 1);
          rerenderOneOff();
        });
      });
    };
    const rerenderOneOff = () => {
      mount(document.getElementById('placementFormOneOffList'), this.placementOneOffRowsHtml(oneOffCosts));
      bindOneOffEvents();
    };
    bindOneOffEvents();
    const addBtn = document.getElementById('placementFormOneOffAdd');
    if (addBtn) addBtn.addEventListener('click', () => { oneOffCosts.push({ label: '', amount: '' }); rerenderOneOff(); });

    if (!isEdit) {
      const jobSel = document.getElementById('placementFormJob');
      const clientSel = document.getElementById('placementFormClient');
      if (jobSel && clientSel) {
        clientSel.addEventListener('change', () => {
          const cid = clientSel.value;
          Array.from(jobSel.options).forEach(opt => {
            if (!opt.value) return;
            opt.hidden = !!cid && opt.dataset.clientId !== cid;
          });
          if (jobSel.selectedOptions[0] && jobSel.selectedOptions[0].hidden) jobSel.value = '';
        });
      }
    }
  },

  async submitPlacementForm(handle, isEdit, existing, oneOffCosts) {
    this.placementAlert('placementFormAlert', '');
    let valid = true;
    const setFieldError = (id, msg) => {
      const el = document.getElementById(id);
      const errEl = document.getElementById(id + 'Error');
      if (el) el.classList.toggle('is-invalid', !!msg);
      if (errEl) errEl.textContent = msg || '';
      if (msg) valid = false;
    };

    let candidateId, jobId, clientId, placementType;
    if (!isEdit) {
      candidateId = document.getElementById('placementFormCandidate')?.value;
      clientId = document.getElementById('placementFormClient')?.value;
      jobId = document.getElementById('placementFormJob')?.value;
      placementType = document.getElementById('placementFormType')?.value;
      setFieldError('placementFormCandidate', candidateId ? '' : 'Kies een kandidaat.');
      setFieldError('placementFormClient', clientId ? '' : 'Kies een opdrachtgever.');
      setFieldError('placementFormJob', jobId ? '' : 'Kies een vacature.');
      setFieldError('placementFormType', placementType ? '' : 'Kies een type plaatsing.');
    }

    const moneyField = (id, opts) => {
      const el = document.getElementById(id);
      const parsed = parsePlacementDecimal(el ? el.value : '', opts);
      setFieldError(id, parsed.ok ? '' : parsed.error);
      return parsed.ok ? parsed.value : undefined;
    };
    const hourlyRate = moneyField('placementFormHourlyRate', { decimals: 2, max: MONEY_MAX });
    const hours = moneyField('placementFormHours', { decimals: 2, max: HOURS_MAX });
    const monthlyPrice = moneyField('placementFormMonthlyPrice', { decimals: 2, max: MONEY_MAX });
    const eorFactor = moneyField('placementFormEorFactor', { decimals: 4, max: EOR_FACTOR_MAX });
    const feePercentage = moneyField('placementFormFeePercentage', { decimals: 2, max: FEE_PERCENTAGE_MAX });
    const feeAmount = moneyField('placementFormFeeAmount', { decimals: 2, max: MONEY_MAX });

    const oneOffPayload = [];
    oneOffCosts.forEach((row, i) => {
      const label = (row.label || '').trim();
      const amountParsed = parsePlacementDecimal(row.amount, { decimals: 2 });
      let rowValid = true;
      const labelErrEl = document.getElementById(`placementOneOffLabelError${i}`);
      if (!label) { if (labelErrEl) labelErrEl.textContent = 'Omschrijving is verplicht.'; rowValid = false; }
      else if (label.length > 120) { if (labelErrEl) labelErrEl.textContent = 'Maximaal 120 tekens.'; rowValid = false; }
      else if (labelErrEl) labelErrEl.textContent = '';
      const amtErrEl = document.getElementById(`placementOneOffAmountError${i}`);
      if (!amountParsed.ok || amountParsed.value == null) {
        if (amtErrEl) amtErrEl.textContent = amountParsed.error || 'Bedrag is verplicht.';
        rowValid = false;
      } else if (amtErrEl) amtErrEl.textContent = '';
      if (!rowValid) valid = false;
      else oneOffPayload.push({ label, amount: amountParsed.value });
    });

    if (!valid) return;

    const payload = {
      start_date: document.getElementById('placementFormStart')?.value || null,
      end_date: document.getElementById('placementFormEnd')?.value || null,
      billing_basis: document.getElementById('placementFormBillingBasis')?.value || null,
      hourly_bill_rate: hourlyRate ?? null,
      expected_billable_hours: hours ?? null,
      monthly_purchase_price: monthlyPrice ?? null,
      eor_partner: document.getElementById('placementFormEorPartner')?.value?.trim() || null,
      eor_cost_factor: eorFactor ?? null,
      fee_type: document.getElementById('placementFormFeeType')?.value || null,
      fee_percentage: feePercentage ?? null,
      fee_amount: feeAmount ?? null,
      one_off_costs: oneOffPayload,
      notes: document.getElementById('placementFormNotes')?.value?.trim() || null,
    };
    if (!isEdit) {
      Object.assign(payload, {
        candidate_id: Number(candidateId),
        job_id: Number(jobId),
        client_id: Number(clientId),
        placement_type: placementType,
      });
    }

    handle.setBusy(true);
    try {
      const url = isEdit ? `/v1/admin/placements/${existing.id}` : '/v1/admin/placements';
      const res = await Auth.fetch(url, { method: isEdit ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        handle.close();
        Auth.toast(isEdit ? 'Plaatsing bijgewerkt' : 'Plaatsing aangemaakt', 'success');
        if (!isEdit) this._currentPage.placements = 1;
        await this.loadPlacements(this._lastParams.placements || {});
        if (isEdit) {
          await this.ensurePlacementDetail(existing.id, { force: true });
          if (this._placementDrawer) this.switchPlacementTab(existing.id, 'financieel');
        }
        return;
      }
      this.placementAlert('placementFormAlert', this.placementErrorText(data, res && res.status));
    } catch {
      this.placementAlert('placementFormAlert', 'Netwerkfout, probeer het opnieuw.');
    }
    handle.setBusy(false);
  },
  });

  Admin.registerSection({
    id: 'placements',
    title: 'Plaatsingen',
    loader: () => Admin.loadPlacements(),
    skeletonHtml: () => html`
      <div class="card mb-3">
        <div class="card-body border-bottom py-3">
          <div class="d-flex flex-wrap gap-3 align-items-end justify-content-between">
            <div class="d-flex flex-wrap gap-3">
              <div>
                <label class="form-label" for="placementStatusFilter">Status</label>
                <select class="form-select" id="placementStatusFilter">
                  <option value="">Alle</option>
                  <option value="concept">Concept</option>
                  <option value="actief">Actief</option>
                  <option value="beeindigd">Beëindigd</option>
                  <option value="geannuleerd">Geannuleerd</option>
                </select>
              </div>
              <div>
                <label class="form-label" for="placementClientFilter">Opdrachtgever</label>
                <select class="form-select" id="placementClientFilter"><option value="">Alle opdrachtgevers</option></select>
              </div>
              <div>
                <label class="form-label" for="placementCandidateSearch">Kandidaat</label>
                <input type="text" class="form-control" id="placementCandidateSearch" placeholder="Naam, e-mail of ID">
                <div class="a-meta mt-1" id="placementCandidateSearchHint"></div>
              </div>
            </div>
            <button type="button" class="btn btn-primary" data-action="open-new-placement-modal">
              <i class="fa-solid fa-plus me-1"></i>Nieuwe plaatsing
            </button>
          </div>
        </div>
        <div class="table-responsive">
          <table class="table table-vcenter card-table a-cardlist" aria-label="Plaatsingen">
            <thead id="placementsHead" tabindex="-1">
              <tr>
                <th scope="col" data-sort-key="candidate_id">Kandidaat</th>
                <th scope="col" data-sort-key="client_id">Opdrachtgever</th>
                <th scope="col" data-sort-key="job_id" class="a-hide-cardlist">Vacature</th>
                <th scope="col">Type</th>
                <th scope="col" data-sort-key="start_date" class="a-hide-cardlist">Start</th>
                <th scope="col" data-sort-key="end_date" class="a-hide-cardlist">Einde</th>
                <th scope="col" data-sort-key="status">Status</th>
                <th scope="col" class="a-col-actions"><span class="visually-hidden">Rijacties</span></th>
              </tr>
            </thead>
            <tbody id="placementsBody"></tbody>
          </table>
        </div>
        <div class="card-footer d-flex justify-content-center">
          <div class="pagination-wrap" id="placementsPagination"></div>
        </div>
      </div>`,
    filters: [
      { selector: '#placementStatusFilter', event: 'change', handler: () => Admin.applyPlacementFilters() },
      { selector: '#placementClientFilter', event: 'change', handler: () => Admin.applyPlacementFilters() },
      { selector: '#placementCandidateSearch', event: 'input', debounce: 400,
        handler: (el) => Admin.resolvePlacementCandidateSearch(el.value) },
    ],
    actions: {
      'open-new-placement-modal': () => Admin.openPlacementFormModal(null),
      'open-placement-edit-modal': (el) => Admin.openPlacementEditFromDrawer(Number(el.dataset.id)),
      'open-placement-drawer': (el) => Admin.openPlacementDrawer(Number(el.dataset.id)),
      'confirm-delete-placement': (el) => Admin.confirmDeletePlacement(Number(el.dataset.id)),
      'placement-tab': (el) => Admin.switchPlacementTab(Number(el.dataset.id), el.dataset.tab),
      'open-candidate-from-placement': (el) => Admin.openCandidateFromPlacement(Number(el.dataset.id)),
      'open-client-from-placement': (el) => Admin.openClientDrawer(Number(el.dataset.id)),
    },
  });
})();
