/* ============================================================
   GSP Recruitment — admin/js/sections/retention.js
   Bewaartermijnen: de goedkeuringslijst uit SITE-DESIGN-SPEC.md §7.3.1.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern), ui.js en labels.js, en voor nav.js, dat de registry uitleest.
   Geen ES-module: de rest van de site gebruikt die ook niet.

   Wat dit scherm doet, en wat het bewust niet doet:
     - De lijst is de enige plek in dit systeem waar een beheerder een
       onomkeerbare verwerking in gang zet. Goedkeuren vraagt daarom de
       getypte bevestiging APPROVE, letterlijk de tekenreeks die
       REVIEW_APPROVE_CONFIRM in routers/retention_admin.py eist.
     - Afwijzen wist niets en is de veilige uitkomst: één bevestiging met
       een optionele notitie, geen getypte bevestiging.
     - De twee droogloopkaarten roepen uitsluitend dry_run:true aan. Die
       aanroepen zijn read-only en krijgen geen bevestiging (§7.6 besluit
       3): dezelfde drempel bij een telling leert alleen af dat de drempel
       iets betekent. dry_run:false bestaat aan de backendkant niet meer
       (410) en zit hier dus ook niet in.
     - Categoriebreed goedkeuren wordt onder 600px niet aangeboden
       (§7.6 besluit 1, .a-wide-only in admin.css).
     - Het e-mailadres uit de respons staat niet in de lijst en niet in de
       console: alleen in de bevestigingsmodal, gemaskeerd.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  // §7.3.1: de lijstweergave haalt pagina's van 50; de bevestigingsmodal
  // van een categoriebrede goedkeuring haalt juist zonder limit op, want
  // dat aantal gaat als expected_count mee.
  const PAGE_SIZE = 50;
  // routers/retention_admin.py MAX_BULK_REVIEW_ITEMS.
  const BULK_CAP = 200;
  const CONFIRM = 'APPROVE';

  // §7.2f punt 2: één eigen Nederlandse zin per code die dit scherm kent.
  // De codes komen uit routers/retention_admin.py; een code die hier niet
  // staat valt terug op detail.message (punt 3).
  const ERROR_TEXT = {
    retention_review_approve_requires_confirm:
      'De bevestiging klopte niet. Typ APPROVE en probeer het opnieuw.',
    retention_review_item_not_actionable:
      'Dit item heeft inmiddels een andere status en kan niet meer goedgekeurd worden.',
    retention_review_item_no_longer_eligible:
      'Dit item komt niet meer in aanmerking: er is sindsdien een beschermend signaal verschenen. Er is niets gewist.',
    retention_review_item_already_processing:
      'Dit item wordt al ergens anders verwerkt.',
    retention_review_item_already_purged:
      'Dit item is al verwerkt.',
    retention_review_subject_missing_email:
      'Het onderwerp heeft geen e-mailadres meer. Er is niets gewist.',
    retention_purge_blocked_unrelated_account:
      'Dit e-mailadres hoort ook bij een record dat niet bij deze bewaartermijn-rij hoort. Los dat adresconflict eerst handmatig op.',
    retention_review_bulk_expected_count_mismatch:
      'De lijst is veranderd sinds je hem bekeek. Ververs en probeer opnieuw.',
    retention_run_no_longer_purges:
      'Deze telling verandert niets. Verwijderen loopt uitsluitend via de beoordelingslijst hierboven.',
    apollo_pool_purge_no_longer_deletes:
      'Deze telling verandert niets. Verwijderen loopt uitsluitend via de beoordelingslijst hierboven.',
    invalid_sort_column: 'Sorteren op deze kolom kan niet.',
    invalid_order_direction: 'Deze sorteerrichting kan niet.',
  };

  const STATUS_OPTIONS = [
    ['pending', 'Te beoordelen'],
    ['rejected', AdminLabels.label('retentiestatus', 'rejected')],
    ['purging', 'Wordt verwerkt'],
    ['purged', 'Verwerkt'],
    ['no_longer_eligible', 'Niet meer van toepassing'],
    ['all', 'Alle statussen'],
  ];

  // Toelichting per status van POST /retention/run (dry_run).
  const DRYRUN_STATUS = {
    counted: 'geteld',
    not_applicable: 'telt niet mee: bewaren',
    schema_not_ready: 'kolom bestaat nog niet',
    error: 'kon niet tellen',
  };

  Object.assign(Admin, {
  _retention: {
    summary: null, lastGeneratedAt: null, lastGeneratedKnown: false,
    items: [], total: 0, reappeared: 0, selected: new Set(),
    lastStatus: null, bulkExpected: 0,
  },

  /* ---- Kleine formatters, Nederlands ---- */
  // Admin.formatDate() staat op en-GB voor de rest van het paneel; de
  // chrome van deze sectie is Nederlands, dus een eigen datum.
  retentionDate(d) {
    if (!d) return '—';
    const dt = new Date(d);
    return isNaN(dt.getTime())
      ? '—'
      : dt.toLocaleDateString('nl-NL', { day: 'numeric', month: 'short', year: 'numeric' });
  },
  retentionDaysExpired(d) {
    if (!d) return null;
    const ms = Date.now() - new Date(d).getTime();
    if (isNaN(ms)) return null;
    return Math.max(0, Math.floor(ms / 86400000));
  },
  // j••••@voorbeeld.nl -- het adres is alleen in de bevestigingsmodal
  // zichtbaar en ook daar niet voluit (§7.3.1).
  retentionMaskEmail(email) {
    if (!email) return '—';
    const s = String(email);
    const at = s.indexOf('@');
    if (at < 1) return '••••';
    return s.slice(0, 1) + '••••' + s.slice(at);
  },
  retentionCategoryLabel(key) {
    return AdminLabels.label('retentiecategorie', key);
  },
  retentionSubject(item) {
    const what = AdminLabels.label('retentieonderwerp', item.subject_table, item.subject_table || 'record');
    return `${what} #${item.subject_id}`;
  },

  // §7.2f: vertak op detail.code, val terug op detail.message. De code
  // zelf hoort in de console, niet op het scherm -- en er gaat nooit een
  // persoonsgegeven mee.
  // opts.rawFallback:false onderdrukt de terugval op detail.message. Dat
  // is er voor de uitkomstenlijst van een bulkaanroep: daar is `detail`
  // een interne markering ("unexpected_error"), geen zin die voor een
  // beheerder geschreven is.
  retentionErrorText(payload, status, opts = {}) {
    const d = this.errorDetail(payload);
    if (d.code) {
      // Alleen de code, nooit een persoonsgegeven, en nooit op het scherm.
      console.warn('retention: API-foutcode', d.code);
    }
    if (Array.isArray(d.extra && d.extra.allowed)) {
      console.warn('retention: toegestane kolommen', d.extra.allowed);
    }
    // Rechten gaan voor: een 401 of 403 is geen fout om opnieuw te
    // proberen, en de Engelse zin die de backend erbij levert helpt
    // niemand verder.
    if (status === 401 || status === 403) return 'Je hebt geen rechten voor deze handeling.';
    if (d.code && ERROR_TEXT[d.code]) return ERROR_TEXT[d.code];
    // §7.2f punt 3: liever een Engelse zin die klopt dan een Nederlandse
    // die raadt. De code staat al in de console.
    if (d.message && opts.rawFallback !== false) return d.message;
    if (d.code || d.message) {
      console.warn('retention: onbekende foutmelding', d.code || '', d.message || '');
    }
    return 'Er ging iets mis, probeer het opnieuw.';
  },

  retentionAnnounce(text) {
    const el = document.getElementById('retentionLive');
    if (el) el.textContent = text;
  },

  // Inline-melding (§7.2f) binnen het blok waar hij over gaat.
  retentionAlert(containerId, text, opts = {}) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!text) { mount(el, ''); return; }
    mount(el, html`
      <div class="alert alert-danger" role="alert">
        <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
        <span>${text}</span>
        ${opts.action ? html`
          <button type="button" class="btn btn-sm btn-outline-secondary ms-3"
            data-action="${opts.action}">${opts.actionLabel || 'Opnieuw proberen'}</button>` : ''}
      </div>`);
  },

  /* ============================================================
     SAMENVATTING
     ============================================================ */
  async loadRetentionSummary() {
    const el = document.getElementById('retentionSummary');
    if (el && !this._retention.summary) this.renderRetentionSummary(true);
    try {
      const [sumRes, lastRes] = await Promise.all([
        Auth.fetch('/v1/admin/retention/review/summary'),
        // "Laatst gegenereerd" is geen veld van de samenvatting. Het is wel
        // een veld van de lijst: elke generatierun zet last_seen_at op NOW()
        // (_upsert_review_item), dus de nieuwste last_seen_at over de hele
        // verzameling is precies dat moment. Server-side gesorteerd (BV10),
        // één rij, dus geen afleiding uit een pagina.
        Auth.fetch('/v1/admin/retention/review?status=all&sort=last_seen_at&order=desc&limit=1'),
      ]);
      if (sumRes && (sumRes.status === 401 || sumRes.status === 403)) {
        this.showRetentionNoRights();
        return;
      }
      if (!sumRes || !sumRes.ok) throw new Error('summary');
      this._retention.summary = await sumRes.json();
      // De rechten zijn er (weer): de knoppen die iets doen mogen terug aan.
      if (this._retention.noRights) this.clearRetentionNoRights();
      // Drie staten voor "Laatst gegenereerd": bekend, leeg (er staat nog
      // niets in de lijst) en mislukt. De derde is geen "n.v.t.": dat zou
      // een reden verzinnen voor iets wat gewoon niet geladen is.
      if (lastRes && lastRes.ok) {
        const last = await lastRes.json();
        this._retention.lastGeneratedAt = (last.items && last.items[0]) ? last.items[0].last_seen_at : null;
        this._retention.lastGeneratedKnown = true;
        this._retention.lastGeneratedFailed = false;
      } else {
        this._retention.lastGeneratedKnown = false;
        this._retention.lastGeneratedFailed = true;
      }
      this.renderRetentionSummary();
      this.renderRetentionCategories();
      this.fillRetentionCategoryFilter();
    } catch {
      this.setContainerLoadError(document.getElementById('retentionSummary'), () => this.loadRetentionSummary());
      this.setLoadError('#retentionCategoryBody', 5, () => this.loadRetentionSummary());
    }
  },

  // Geen rechten is geen fout om opnieuw te proberen: geen retrylink, en
  // de knoppen die iets zouden doen gaan uit.
  retentionActionButtons() {
    return document.querySelectorAll(
      '#section-retention [data-action="retention-generate"], '
      + '#section-retention [data-action="retention-dryrun"], '
      + '#section-retention [data-action="retention-apollo-dryrun"]');
  },

  clearRetentionNoRights() {
    this._retention.noRights = false;
    this.retentionActionButtons().forEach(btn => {
      btn.disabled = false;
      btn.removeAttribute('title');
    });
  },

  showRetentionNoRights() {
    this._retention.noRights = true;
    mount(document.getElementById('retentionSummary'), html`
      <div class="col-12"><div class="a-state-block">Je hebt geen rechten om de bewaartermijnen te bekijken.</div></div>`);
    this.setEmpty('#retentionCategoryBody', 5, 'Je hebt geen rechten om deze gegevens te bekijken.');
    this.retentionActionButtons().forEach(btn => {
      btn.disabled = true;
      btn.title = 'Je hebt geen rechten voor deze handeling';
    });
  },

  retentionCategoryCounts() {
    const rows = (this._retention.summary && this._retention.summary.by_category) || [];
    const byKey = new Map();
    rows.forEach(r => {
      const key = r.category;
      if (!byKey.has(key)) byKey.set(key, { key, pending: 0, rejected: 0, purged: 0, total: 0 });
      const bucket = byKey.get(key);
      const n = Number(r.n) || 0;
      if (bucket[r.status] !== undefined) bucket[r.status] += n;
      bucket.total += n;
    });
    return Array.from(byKey.values()).sort((a, b) => b.pending - a.pending || a.key.localeCompare(b.key));
  },

  // De waarde staat in .a-num--xl; een datum of "n.v.t." zakt daarbinnen
  // naar de leesmaat met .a-num--date (D10: een datum is geen KPI-cijfer).
  retentionTile(label, valueHtml, note) {
    return html`
      <div class="col-sm-6 col-lg">
        <div class="card card-sm h-100">
          <div class="card-body">
            <div class="a-eyebrow">${label}</div>
            <div class="a-num a-num--xl">${valueHtml}</div>
            ${note ? html`<div class="a-meta">${note}</div>` : ''}
          </div>
        </div>
      </div>`;
  },

  renderRetentionSummary(loading) {
    const el = document.getElementById('retentionSummary');
    if (!el) return;
    // Laadstaat (§7.2g): het label blijft staan, de waardepositie wordt een
    // vlak blok. Geen spinner en geen 0 die daarna verspringt.
    const block = raw('<span class="a-num--loading" aria-hidden="true"></span>');
    if (loading || !this._retention.summary) {
      mount(el, html`
        ${this.retentionTile('Te beoordelen', block)}
        ${this.retentionTile('Categorieën met items', block)}
        ${this.retentionTile('Laatst gegenereerd', block)}`);
      return;
    }
    const s = this._retention.summary;
    const cats = this.retentionCategoryCounts().filter(c => c.total > 0).length;
    mount(el, html`
      ${this.retentionTile('Te beoordelen', s.pending_total ?? 0)}
      ${this.retentionTile('Categorieën met items', cats)}
      ${this.retentionLastGeneratedTile()}
      ${this._retention.reappeared > 0
        ? this.retentionTile('Heropend na afwijzing', this._retention.reappeared,
            'geteld in de nu geladen lijst')
        : ''}`);
  },

  // Drie staten (§7.2g): een datum, "n.v.t." met de reden wanneer de lijst
  // leeg is, en een streepje met een retrylink wanneer de meting zelf niet
  // geladen kon worden.
  retentionLastGeneratedTile() {
    if (this._retention.lastGeneratedFailed) {
      return this.retentionTile('Laatst gegenereerd', html`<span class="a-soft">--</span>`,
        html`<a href="#" data-action="retention-refresh-summary">Kon niet laden, probeer opnieuw</a>`);
    }
    if (this._retention.lastGeneratedKnown && this._retention.lastGeneratedAt) {
      return this.retentionTile('Laatst gegenereerd',
        html`<span class="a-num--date">${this.retentionDate(this._retention.lastGeneratedAt)}</span>`);
    }
    return this.retentionTile('Laatst gegenereerd', html`<span class="a-soft a-num--date">n.v.t.</span>`,
      'er staat nog niets in de lijst');
  },

  renderRetentionCategories() {
    const rows = this.retentionCategoryCounts();
    if (!rows.length) {
      this.setEmpty('#retentionCategoryBody', 5, 'Nog geen categorieën met items.');
      return;
    }
    mount(document.getElementById('retentionCategoryBody'), html`${rows.map(c => html`
      <tr>
        <td data-label="Categorie" class="a-cell-name">${this.retentionCategoryLabel(c.key)}</td>
        <td data-label="Te beoordelen" class="a-num">${c.pending}</td>
        <td data-label="Afgewezen" class="a-num">${c.rejected}</td>
        <td data-label="Verwerkt" class="a-num">${c.purged}</td>
        <td class="text-end">
          <button type="button" class="btn btn-sm btn-ghost-secondary"
            data-action="retention-category-view" data-category="${c.key}">Bekijken</button>
          <button type="button" class="btn btn-sm btn-outline-danger a-wide-only"
            data-action="retention-category-approve" data-category="${c.key}"
            ${raw(c.pending ? '' : 'disabled title="Geen items om goed te keuren"')}>Alles goedkeuren</button>
        </td>
      </tr>`)}`);
  },

  fillRetentionCategoryFilter() {
    const sel = document.getElementById('retentionCategoryFilter');
    if (!sel) return;
    const current = sel.value;
    const rows = this.retentionCategoryCounts();
    mount(sel, html`
      <option value="">Alle categorieën</option>
      ${rows.map(c => html`<option value="${c.key}" ${raw(c.key === current ? 'selected' : '')}>${this.retentionCategoryLabel(c.key)}</option>`)}`);
  },

  /* ============================================================
     DE LIJST
     ============================================================ */
  retentionTable() {
    if (this._retentionTable) return this._retentionTable;
    this._retentionTable = ui.table({
      tbody: '#retentionBody',
      thead: '#retentionHead',
      // serverSort: BV10 levert sort/order op deze route, en §7.2a wil dat
      // er over de hele verzameling gesorteerd wordt, niet binnen één
      // pagina. Alleen kolommen uit de allowlist van de route zijn
      // sorteerbaar; de rest is een gewone <th>.
      serverSort: true,
      page: { container: 'retentionPagination', section: 'retention', size: PAGE_SIZE },
      // De lege staat hangt van het actieve filter af: "genereer de lijst"
      // klopt alleen voor de standaardweergave. Onder een statusfilter of
      // een categoriefilter is er simpelweg niets dat aan dat filter
      // voldoet, en dan is genereren niet de vervolgstap.
      empty: () => this.retentionEmptyHtml(),
      cols: [
        { key: '_check' },
        { key: 'category', sortable: true },
        { key: '_subject' },
        { key: 'term_expired_at', sortable: true },
        { key: 'signal_missing_nl' },
        { key: 'action', sortable: true },
        { key: 'status', sortable: true },
        { key: '_actions' },
      ],
      load: (state) => this.fetchRetentionReview(state),
      render: (item) => this.renderRetentionRow(item),
      // De foutstaat van ui.table is de retryregel; een 403 is geen fout
      // om opnieuw te proberen maar een ontbrekend recht, en krijgt daarom
      // zijn eigen regel op dezelfde plek.
      onError: () => {
        if (this._retention.lastStatus === 403) {
          this.setEmpty('#retentionBody', 8, 'Je hebt geen rechten om deze lijst te zien.');
        }
      },
    });
    return this._retentionTable;
  },

  retentionEmptyHtml() {
    const p = this._lastParams.retention || {};
    const status = p.status || 'pending';
    if (p.category || status !== 'pending') {
      return html`Geen items die aan dit filter voldoen.
        <div class="a-meta mt-2">Pas het status- of categoriefilter aan om meer te zien.</div>`;
    }
    // Eén affordance voor genereren op dit scherm: de knop in de kop van
    // de samenvatting. Hier staat alleen waar hij zit.
    return html`Er staat op dit moment niets te beoordelen.
      <div class="a-meta mt-2">De lijst wordt maandelijks automatisch aangevuld; met
        <span class="a-cell-strong">Lijst genereren</span> hierboven vul je hem nu aan.</div>`;
  },

  // Eén regel per geraakt item, met scheiding, in plaats van een lap
  // voorgevormde tekst: dit is een lijst die iemand naloopt.
  retentionBulkRowList(items) {
    return html`
      <div class="a-scrollbox a-scrollbox--rows">
        ${items.map(i => html`
          <div class="a-listrow">
            <span class="a-num a-truncate-col">${this.retentionSubject(i)}</span>
            <span class="a-soft text-nowrap">${this.retentionDate(i.term_expired_at)}</span>
            <span class="text-nowrap">${AdminLabels.label('retentieactie', i.action)}</span>
          </div>`)}
      </div>`;
  },

  async loadRetentionReview(params) {
    if (params) this._lastParams.retention = params;
    await this.retentionTable().reload();
  },

  async fetchRetentionReview(state) {
    const p = this._lastParams.retention || {};
    const qs = new URLSearchParams();
    qs.set('status', p.status || 'pending');
    if (p.category) qs.set('category', p.category);
    qs.set('limit', String(PAGE_SIZE));
    qs.set('offset', String(((this._currentPage.retention || 1) - 1) * PAGE_SIZE));
    if (state.sortKey) {
      qs.set('sort', state.sortKey);
      qs.set('order', state.sortDir || 'asc');
    }
    this._retention.lastStatus = null;
    const res = await Auth.fetch(`/v1/admin/retention/review?${qs}`);
    if (!res) throw new Error('geen respons');
    const data = await res.json().catch(() => null);
    this._retention.lastStatus = res.status;
    if (!res.ok) {
      // 422 op sort of order is een programmeerfout, geen gebruikersfout:
      // op het scherm de generieke foutregel met retry, in de console de
      // code en de toegestane kolommen (§7.2a).
      this.retentionErrorText(data, res.status);
      throw new Error('lijst kon niet geladen worden');
    }
    const items = (data && data.items) || [];
    this._retention.items = items;
    this._retention.total = (data && data.total) || items.length;
    // De heropende items worden client-side geteld: GET /review/summary
    // groepeert op category en status en kent dat onderscheid niet.
    this._retention.reappeared = items.filter(i => i.status === 'pending' && i.reappeared_after_rejection_at).length;
    // Een selectie van een rij die er niet meer staat, verdwijnt mee.
    const ids = new Set(items.map(i => i.id));
    Array.from(this._retention.selected).forEach(id => { if (!ids.has(id)) this._retention.selected.delete(id); });
    this.renderRetentionFooterCount();
    // Alleen hertekenen wanneer er een samenvatting IS: anders zou een
    // mislukte samenvatting (met zijn retrylink) door de laadstaat van
    // deze lijstlading overschreven worden en nooit meer terugkomen.
    if (this._retention.summary) this.renderRetentionSummary();
    // De bulkbalk hangt aan de selectie; die tekent na het schilderen van
    // de rijen opnieuw (zie renderRetentionBulkbar).
    setTimeout(() => {
      this.renderRetentionBulkbar();
      this.syncRetentionClamps();
    }, 0);
    return data || {};
  },

  renderRetentionFooterCount() {
    const el = document.getElementById('retentionCount');
    if (!el) return;
    const shown = this._retention.items.length;
    mount(el, shown
      ? html`${shown} van ${this._retention.total}`
      : html`0 van ${this._retention.total}`);
  },

  renderRetentionRow(item) {
    const days = this.retentionDaysExpired(item.term_expired_at);
    const reappeared = item.status === 'pending' && item.reappeared_after_rejection_at;
    const subject = this.retentionSubject(item);
    const canApprove = item.status === 'pending' || item.status === 'rejected';
    const canReject = item.status !== 'purged' && item.status !== 'purging';
    const busyReason = 'Dit item is al verwerkt of wordt verwerkt';
    return html`
      <tr class="${this._retention.selected.has(item.id) ? 'a-row-selected' : ''}" data-row-id="${item.id}">
        <td class="a-col-check">
          <label class="a-tap">
            <input class="form-check-input" type="checkbox" data-action="retention-select" data-id="${item.id}"
              aria-label="Selecteer ${subject}" ${raw(this._retention.selected.has(item.id) ? 'checked' : '')}
              ${raw(canApprove ? '' : 'disabled')}>
          </label>
        </td>
        <td data-label="Categorie" class="a-cell-name a-col-cat" title="${this.retentionCategoryLabel(item.category)}">
          ${reappeared ? raw('<i class="fa-solid fa-rotate-left me-1 text-warning-ink" aria-hidden="true"></i>') : ''}${this.retentionCategoryLabel(item.category)}
        </td>
        <td data-label="Onderwerp" class="a-num">${subject}</td>
        <td data-label="Termijn verlopen" class="text-nowrap">
          ${this.retentionDate(item.term_expired_at)}
          ${days === null ? '' : html`<span class="a-meta ms-1">(${days} d)</span>`}
        </td>
        <td data-label="Ontbrekend signaal">
          <div class="d-flex gap-2 align-items-start">
            <div class="a-clamp flex-fill" id="retSignal${item.id}">${item.signal_missing_nl || '—'}</div>
            <button type="button" class="btn btn-sm btn-ghost-secondary px-1 flex-shrink-0"
              data-action="retention-toggle-signal" data-id="${item.id}" aria-expanded="false"
              aria-controls="retSignal${item.id}" hidden>meer</button>
          </div>
        </td>
        <td data-label="Actie" class="text-nowrap">${AdminLabels.label('retentieactie', item.action)}</td>
        <td data-label="Status" class="a-col-status">
          <span class="${AdminLabels.badgeClass('retentiestatus', item.status)}">${AdminLabels.label('retentiestatus', item.status)}</span>
          ${reappeared ? html`<div class="a-meta">Eerder afgewezen, opnieuw verschenen op ${this.retentionDate(item.reappeared_after_rejection_at)}</div>` : ''}
        </td>
        <td class="a-col-actions">
          <button type="button" class="btn btn-sm btn-ghost-secondary"
            data-action="retention-approve" data-id="${item.id}"
            aria-label="Goedkeuren en verwerken: ${subject}"
            title="${canApprove ? 'Goedkeuren en verwerken' : busyReason}"
            ${raw(canApprove ? '' : 'disabled')}>
            <i class="fa-solid fa-check" aria-hidden="true"></i><span class="d-md-none ms-1">Goedkeuren</span>
          </button>
          <button type="button" class="btn btn-sm btn-ghost-secondary"
            data-action="retention-reject" data-id="${item.id}"
            aria-label="Afwijzen en bewaren: ${subject}"
            title="${canReject ? 'Afwijzen en bewaren' : busyReason}"
            ${raw(canReject ? '' : 'disabled')}>
            <i class="fa-solid fa-xmark" aria-hidden="true"></i><span class="d-md-none ms-1">Afwijzen</span>
          </button>
        </td>
      </tr>`;
  },

  // De uitklapknop hoort alleen te staan waar de tekst daadwerkelijk is
  // ingekort. Dat is pas na het schilderen te meten, want het hangt van de
  // kolombreedte af.
  syncRetentionClamps() {
    document.querySelectorAll('#retentionBody .a-clamp').forEach(el => {
      const btn = el.parentElement && el.parentElement.querySelector('[data-action="retention-toggle-signal"]');
      if (!btn) return;
      const clipped = el.scrollHeight > el.clientHeight + 1;
      btn.hidden = !clipped && !el.classList.contains('a-clamp--open');
    });
  },

  toggleRetentionSignal(id, btn) {
    const el = document.getElementById('retSignal' + id);
    if (!el) return;
    const open = el.classList.toggle('a-clamp--open');
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.textContent = open ? 'minder' : 'meer';
  },

  /* ---- Rijselectie en bulkbalk (§7.2a) ---- */
  toggleRetentionSelection(id, checked) {
    if (checked) this._retention.selected.add(id); else this._retention.selected.delete(id);
    const row = document.querySelector(`#retentionBody tr[data-row-id="${id}"]`);
    if (row) row.classList.toggle('a-row-selected', checked);
    this.renderRetentionBulkbar();
  },

  toggleRetentionSelectAll(checked) {
    this._retention.items.forEach(i => {
      if (i.status !== 'pending' && i.status !== 'rejected') return;
      if (checked) this._retention.selected.add(i.id); else this._retention.selected.delete(i.id);
    });
    document.querySelectorAll('#retentionBody input[data-action="retention-select"]').forEach(box => {
      if (box.disabled) return;
      box.checked = checked;
      const row = box.closest('tr');
      if (row) row.classList.toggle('a-row-selected', checked);
    });
    this.renderRetentionBulkbar();
  },

  clearRetentionSelection() {
    this._retention.selected.clear();
    document.querySelectorAll('#retentionBody input[data-action="retention-select"]').forEach(box => { box.checked = false; });
    document.querySelectorAll('#retentionBody tr.a-row-selected').forEach(row => row.classList.remove('a-row-selected'));
    this.renderRetentionBulkbar();
  },

  renderRetentionBulkbar() {
    const bar = document.getElementById('retentionBulkbar');
    if (!bar) return;
    const n = this._retention.selected.size;
    const selectable = this._retention.items.filter(i => i.status === 'pending' || i.status === 'rejected');
    const head = document.getElementById('retentionSelectAll');
    if (head) {
      head.checked = selectable.length > 0 && n >= selectable.length;
      head.indeterminate = n > 0 && n < selectable.length;
    }
    if (!n) {
      bar.hidden = true;
      mount(bar, '');
      this.publishBulkbarHeight(null);
      return;
    }
    const over = n > BULK_CAP;
    mount(bar, html`
      <div class="a-bulkbar" role="region" aria-label="Acties op de selectie">
        <span class="a-num" aria-live="polite">${n} geselecteerd</span>
        <button type="button" class="btn btn-sm btn-ghost-secondary" data-action="retention-clear-selection">Selectie wissen</button>
        <div class="ms-auto d-flex flex-wrap gap-3 align-items-center">
          ${over ? html`<span class="a-meta">Maximaal ${BULK_CAP} per keer</span>` : ''}
          <button type="button" class="btn btn-sm btn-outline-secondary" data-action="retention-bulk-reject">Afwijzen</button>
          <button type="button" class="btn btn-sm btn-outline-danger" data-action="retention-bulk-approve"
            ${raw(over ? `disabled title="Maximaal ${BULK_CAP} per keer"` : '')}>Goedkeuren…</button>
        </div>
      </div>`);
    bar.hidden = false;
    this.publishBulkbarHeight(bar);
  },

  // De hoogte komt van de balk zelf, niet van de wrapper: op een telefoon
  // staat .a-bulkbar fixed en is de wrapper daarom 0px hoog. Met die 0px
  // schoof de toast niet omhoog en lag hij onder de balk. Dezelfde waarde
  // houdt via padding-bottom op de sectie de laatste rij en de
  // pagineerfooter vrij van de vaste balk.
  publishBulkbarHeight(bar) {
    const inner = bar && (bar.firstElementChild || bar);
    const h = inner ? inner.offsetHeight : 0;
    document.documentElement.style.setProperty('--a-bulkbar-h', h + 'px');
  },

  /* ============================================================
     GOEDKEUREN EN AFWIJZEN, PER ITEM
     ============================================================ */
  retentionItemPanel(item) {
    return html`
      <div class="a-panel">
        <div class="a-metric-row"><span class="a-soft">Categorie</span><span>${this.retentionCategoryLabel(item.category)}</span></div>
        <div class="a-metric-row"><span class="a-soft">Onderwerp</span><span class="a-num">${this.retentionSubject(item)}</span></div>
        <div class="a-metric-row"><span class="a-soft text-nowrap">Termijn verlopen</span><span>${this.retentionDate(item.term_expired_at)}</span></div>
        <div class="a-metric-row"><span class="a-soft">Handeling</span><span>${AdminLabels.label('retentieactie', item.action)}</span></div>
        <div class="a-metric-row"><span class="a-soft text-nowrap">E-mailadres</span><span class="a-num">${this.retentionMaskEmail(item.email)}</span></div>
        <div class="mt-3">
          <div class="a-field-label">Ontbrekend signaal</div>
          <div>${item.signal_missing_nl || '—'}</div>
        </div>
      </div>`;
  },

  openRetentionApprove(id) {
    const item = (this._retention.items || []).find(i => i.id === id);
    if (!item) return;
    const handle = ui.modal({
      id: 'retentionApproveModal',
      title: 'Deze gegevens worden onomkeerbaar verwerkt',
      body: html`
        <div id="retentionApproveAlert"></div>
        ${this.retentionItemPanel(item)}
        <div class="form-group mb-0">
          <label for="retentionApproveNote">Notitie (optioneel)</label>
          <textarea id="retentionApproveNote" rows="2" class="a-textarea"></textarea>
        </div>`,
      confirmText: CONFIRM,
      secondary: { label: 'Annuleren' },
      danger: {
        label: 'Goedkeuren en verwerken',
        keepOpen: true,
        onClick: () => { this.submitRetentionApprove(id, handle); },
      },
    });
  },

  async submitRetentionApprove(id, handle) {
    const note = (document.getElementById('retentionApproveNote') || {}).value || null;
    this.retentionAlert('retentionApproveAlert', '');
    handle.setBusy(true);
    try {
      const res = await Auth.fetch(`/v1/admin/retention/review/${id}/approve`, {
        method: 'POST', body: JSON.stringify({ confirm: CONFIRM, note: note || null }),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        handle.close();
        Auth.toast('Item verwerkt', 'success');
        this.retentionAnnounce('Het item is verwerkt en staat niet meer in de lijst.');
        await this.refreshRetention();
        this.focusRetentionTable();
        return;
      }
      this.retentionShowItemError(handle, this.retentionErrorText(data, res && res.status));
    } catch {
      this.retentionShowItemError(handle, 'Netwerkfout, probeer het opnieuw.');
    }
    handle.setBusy(false);
  },

  retentionShowItemError(handle, text) {
    const open = handle && handle.el && handle.el.classList.contains('show');
    if (open) { this.retentionAlert('retentionApproveAlert', text); return; }
    Auth.toast(text, 'error');
  },

  async openRetentionReject(id) {
    const item = (this._retention.items || []).find(i => i.id === id);
    if (!item) return;
    let note = null;
    // ui.confirm met een eigen body: afwijzen wist niets, dus geen
    // destructieve modal en geen getypte bevestiging -- de backend eist
    // die daar ook niet.
    const ok = await ui.confirm(
      `Dit item blijft bewaard en verdwijnt uit de lijst met te beoordelen items: ${this.retentionSubject(item)}.`,
      {
        title: 'Afwijzen (bewaren)',
        confirmLabel: 'Afwijzen (bewaren)',
        danger: false,
        body: html`
          <div class="form-group mb-0">
            <label for="retentionRejectNote">Notitie (optioneel)</label>
            <textarea id="retentionRejectNote" rows="2" class="a-textarea"></textarea>
          </div>`,
        onConfirm: () => { note = (document.getElementById('retentionRejectNote') || {}).value || null; },
      });
    if (!ok) return;
    try {
      const res = await Auth.fetch(`/v1/admin/retention/review/${id}/reject`, {
        method: 'POST', body: JSON.stringify({ note: note || null }),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        Auth.toast('Item afgewezen en bewaard', 'success');
        this.retentionAnnounce('Het item is afgewezen en blijft bewaard.');
        await this.refreshRetention();
        this.focusRetentionTable();
        return;
      }
      Auth.toast(this.retentionErrorText(data, res && res.status), 'error');
    } catch {
      Auth.toast('Netwerkfout, probeer het opnieuw.', 'error');
    }
  },

  /* ============================================================
     BULK
     ============================================================ */
  // Expliciete selectie: goedkeuren gaat door de destructieve modal met
  // het aantal en de categorieën die in de selectie zitten.
  openRetentionBulkApprove() {
    const ids = Array.from(this._retention.selected);
    if (!ids.length) return;
    const items = this._retention.items.filter(i => ids.includes(i.id));
    const cats = Array.from(new Set(items.map(i => this.retentionCategoryLabel(i.category))));
    const handle = ui.modal({
      id: 'retentionBulkModal',
      title: 'Deze gegevens worden onomkeerbaar verwerkt',
      wide: true,
      body: html`
        <div id="retentionBulkAlert"></div>
        <div class="a-panel">
          <div class="a-metric-row"><span class="a-soft">Aantal items</span><span class="a-num">${ids.length}</span></div>
          <div class="a-metric-row"><span class="a-soft">Categorieën</span><span>${cats.join(', ')}</span></div>
        </div>
        ${this.retentionBulkRowList(items)}
        <div class="form-group mt-3 mb-0">
          <label for="retentionBulkNote">Notitie (optioneel)</label>
          <textarea id="retentionBulkNote" rows="2" class="a-textarea"></textarea>
        </div>`,
      confirmText: CONFIRM,
      secondary: { label: 'Annuleren' },
      danger: {
        label: `Goedkeuren en verwerken (${ids.length} items)`,
        keepOpen: true,
        onClick: () => { this.submitRetentionBulk(handle, { ids }); },
      },
    });
  },

  // §7.3.1: afwijzen van een selectie is één klik met een toast, geen
  // modal en geen getypte bevestiging. Er wordt niets vernietigd, dus er
  // is ook niets om ongedaan te maken; de rijen blijven bewaard en
  // verdwijnen alleen uit de te beoordelen lijst.
  async bulkRejectSelection(btn) {
    const ids = Array.from(this._retention.selected);
    if (!ids.length) return;
    if (btn) btn.disabled = true;
    try {
      const res = await Auth.fetch('/v1/admin/retention/review/bulk', {
        method: 'POST', body: JSON.stringify({ decision: 'rejected', ids }),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        const results = (data && data.results) || [];
        const failed = results.filter(r => r.status === 'error').length;
        Auth.toast(failed
          ? `${results.length - failed} afgewezen, ${failed} mislukt`
          : `${results.length} afgewezen en bewaard`, failed ? 'warning' : 'success');
        this.retentionAnnounce(`${results.length - failed} items afgewezen en bewaard.`);
        this._retention.selected.clear();
        await this.refreshRetention();
        return;
      }
      Auth.toast(this.retentionErrorText(data, res && res.status), 'error');
    } catch {
      Auth.toast('Netwerkfout, probeer het opnieuw.', 'error');
    }
    if (btn) btn.disabled = false;
  },

  // Categoriebreed: de modal haalt bij openen opnieuw op, zonder limit,
  // en toont de rijen die geraakt worden. Dat aantal gaat als
  // expected_count mee, zodat de waarde uit de meting komt die de
  // beheerder op dat moment ziet (§7.3.1).
  async openRetentionCategoryApprove(category) {
    const handle = ui.modal({
      id: 'retentionBulkModal',
      title: 'Deze gegevens worden onomkeerbaar verwerkt',
      wide: true,
      subtitle: this.retentionCategoryLabel(category),
      body: html`<div class="a-state-block"><i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> Laden…</div>`,
      confirmText: CONFIRM,
      secondary: { label: 'Annuleren' },
      danger: {
        label: 'Goedkeuren en verwerken',
        keepOpen: true,
        onClick: () => {
          // bulkExpected is alleen gevuld door een geslaagde, verse
          // ophaling van deze categorie (zie fillRetentionCategoryModal,
          // dat hem eerst op 0 zet). Nul betekent: dit scherm heeft niet
          // gezien wat het zou goedkeuren, dus er gaat niets weg.
          const expected = this._retention.bulkExpected;
          if (!expected) {
            this.retentionAlert('retentionBulkAlert',
              'De lijst voor deze categorie is niet geladen, dus er is niets om goed te keuren. '
              + 'Ververs en probeer opnieuw.',
              { action: 'retention-bulk-refresh', actionLabel: 'Verversen' });
            return false;
          }
          this.submitRetentionBulk(handle, { category, expected_count: expected });
          return true;
        },
      },
      onClose: () => {
        this._retentionCategoryModal = null;
        this._retention.bulkExpected = 0;
        if (this._retentionMobileWatch) {
          this._retentionMobileWatch.removeEventListener('change', this._retentionMobileClose);
          this._retentionMobileWatch = null;
        }
      },
    });
    this._retentionCategoryModal = handle;
    this._retentionCategoryModalCategory = category;
    // Besluit 1 uit §7.6 geldt niet alleen bij het openen: wordt het venster
    // tijdens deze modal smaller dan 600px, dan hoort deze handeling daar
    // niet meer thuis en sluit het paneel.
    if (typeof window.matchMedia === 'function') {
      this._retentionMobileWatch = window.matchMedia('(max-width: 600px)');
      this._retentionMobileClose = (e) => { if (e.matches) handle.close(); };
      this._retentionMobileWatch.addEventListener('change', this._retentionMobileClose);
      if (this._retentionMobileWatch.matches) { handle.close(); return; }
    }
    await this.fillRetentionCategoryModal(handle, category);
  },

  async fillRetentionCategoryModal(handle, category) {
    handle.setBody(html`<div id="retentionBulkAlert"></div>
      <div class="a-state-block"><i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> Laden…</div>`);
    // Zolang de verse telling er niet is, is er geen aantal om goed te
    // keuren: niet dat van de vorige categorie en niet dat van de vorige
    // poging (S1/S3).
    this._retention.bulkExpected = 0;
    const lockBtn = handle.button('danger');
    if (lockBtn) { lockBtn.disabled = true; lockBtn.dataset.gspLock = '1'; }
    try {
      // Bewust zonder limit: de volledige categorie, want dit getal wordt
      // expected_count.
      const res = await Auth.fetch(`/v1/admin/retention/review?status=pending&category=${encodeURIComponent(category)}`);
      const data = res ? await res.json().catch(() => null) : null;
      if (!res || !res.ok) {
        handle.setBody(html`<div id="retentionBulkAlert"></div>`);
        this.retentionAlert('retentionBulkAlert', this.retentionErrorText(data, res && res.status),
          { action: 'retention-bulk-refresh', actionLabel: 'Verversen' });
        return;
      }
      const items = (data && data.items) || [];
      const over = items.length > BULK_CAP;
      // Boven de cap of zonder items blijft het aantal 0: dan is er niets
      // dat deze modal in één keer mag goedkeuren.
      this._retention.bulkExpected = (over || !items.length) ? 0 : items.length;
      const dangerBtn = handle.button('danger');
      if (dangerBtn) {
        if (over || !items.length) {
          dangerBtn.disabled = true;
          // gspLock: de getypte bevestiging mag deze knop niet weer
          // aanzetten (ui.js slaat een vergrendelde knop over).
          dangerBtn.dataset.gspLock = '1';
          dangerBtn.title = over ? `Maximaal ${BULK_CAP} per keer` : 'Geen items om goed te keuren';
        } else {
          delete dangerBtn.dataset.gspLock;
          dangerBtn.removeAttribute('title');
          // Het slot is eraf; de getypte bevestiging bepaalt weer of de
          // knop aan mag. Zonder dit blijft hij uit na een verversing,
          // want er is intussen niets in het veld getypt.
          handle.syncGate();
        }
      }
      handle.setBody(html`
        <div id="retentionBulkAlert"></div>
        <div class="a-panel">
          <div class="a-metric-row"><span class="a-soft">Aantal items</span><span class="a-num">${items.length}</span></div>
          <div class="a-metric-row"><span class="a-soft">Handeling</span><span>${Array.from(new Set(items.map(i => AdminLabels.label('retentieactie', i.action)))).join(', ') || '—'}</span></div>
          ${over ? html`<div class="a-meta mt-2">Maximaal ${BULK_CAP} per keer; keur deze categorie in kleinere delen goed.</div>` : ''}
        </div>
        ${this.retentionBulkRowList(items)}
        <div class="form-group mt-3 mb-0">
          <label for="retentionBulkNote">Notitie (optioneel)</label>
          <textarea id="retentionBulkNote" rows="2" class="a-textarea"></textarea>
        </div>`);
    } catch {
      handle.setBody(html`<div id="retentionBulkAlert"></div>`);
      this.retentionAlert('retentionBulkAlert', 'Kon niet laden, probeer opnieuw.',
        { action: 'retention-bulk-refresh', actionLabel: 'Verversen' });
    }
  },

  async submitRetentionBulk(handle, payload) {
    const note = (document.getElementById('retentionBulkNote') || {}).value || null;
    this.retentionAlert('retentionBulkAlert', '');
    handle.setBusy(true);
    try {
      const res = await Auth.fetch('/v1/admin/retention/review/bulk', {
        method: 'POST',
        body: JSON.stringify({ decision: 'approved', confirm: CONFIRM, note: note || null, ...payload }),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        this.renderRetentionBulkResult(handle, (data && data.results) || []);
        this._retention.selected.clear();
        await this.refreshRetention();
        return;
      }
      const d = this.errorDetail(data);
      if (d.code === 'retention_review_bulk_expected_count_mismatch' && payload.category) {
        // Nooit stilzwijgend opnieuw proberen met het nieuwe getal: de
        // modal blijft staan en het oude aantal vervalt, zodat een tweede
        // klik niet hetzelfde verouderde getal opnieuw stuurt. Alleen
        // "Verversen" vult het weer.
        this._retention.bulkExpected = 0;
        // Ook de knop zelf uit en op slot: het lege aantal alleen is een
        // guard in de handler, het slot maakt de handeling ook onbereikbaar.
        // fillRetentionCategoryModal() haalt het slot er weer af zodra
        // "Verversen" een verse telling heeft opgehaald.
        const b = handle.button('danger');
        if (b) { b.disabled = true; b.dataset.gspLock = '1'; }
        this.retentionShowModalError(handle, ERROR_TEXT[d.code],
          { action: 'retention-bulk-refresh', actionLabel: 'Verversen' });
      } else {
        this.retentionShowModalError(handle, this.retentionErrorText(data, res && res.status));
      }
    } catch {
      this.retentionShowModalError(handle, 'Netwerkfout, probeer het opnieuw.');
    }
    handle.setBusy(false);
  },

  // Een melding die bij een paneel hoort, maar dat paneel kan intussen
  // gesloten zijn (iemand drukt Escape terwijl de POST loopt). Dan mag de
  // uitkomst niet in een onzichtbaar paneel belanden.
  retentionShowModalError(handle, text, opts) {
    const open = handle && handle.el && handle.el.classList.contains('show');
    if (open) { this.retentionAlert('retentionBulkAlert', text, opts); return; }
    Auth.toast(text, 'error');
  },

  renderRetentionBulkResult(handle, results) {
    const failed = results.filter(r => r.status === 'error');
    const done = results.length - failed.length;
    handle.setBody(html`
      <div class="a-panel">
        <div class="a-metric-row"><span class="a-soft">Verwerkt</span><span class="a-num">${done}</span></div>
        <div class="a-metric-row"><span class="a-soft">Mislukt</span><span class="a-num">${failed.length}</span></div>
      </div>
      ${failed.length ? html`
        <div class="a-field-label">Mislukte items</div>
        <ul class="a-inline-list">${failed.map(f => html`<li>#${f.id}: ${this.retentionErrorText(f.detail, null, { rawFallback: false })}</li>`)}</ul>
        <div class="a-actions">
          <button type="button" class="btn btn-outline-danger" data-action="retention-bulk-retry"
            data-ids="${failed.map(f => f.id).join(',')}">Mislukte items opnieuw proberen</button>
        </div>` : ''}`);
    const danger = handle.button('danger');
    if (danger) {
      danger.disabled = true;
      // Vergrendeld: de bevestiging staat er nog, maar deze bulk is klaar.
      danger.dataset.gspLock = '1';
      danger.title = 'Deze bulk is al verwerkt';
    }
    Auth.toast(failed.length ? `${done} verwerkt, ${failed.length} mislukt` : `${done} verwerkt`,
      failed.length ? 'warning' : 'success');
    this.retentionAnnounce(`${done} verwerkt, ${failed.length} mislukt.`);
  },

  async retryRetentionBulk(ids) {
    const handle = ui.modal({
      id: 'retentionBulkModal',
      title: 'Deze gegevens worden onomkeerbaar verwerkt',
      body: html`
        <div id="retentionBulkAlert"></div>
        <div class="a-panel">
          <div class="a-metric-row"><span class="a-soft">Aantal items</span><span class="a-num">${ids.length}</span></div>
        </div>
        <div class="form-group mb-0">
          <label for="retentionBulkNote">Notitie (optioneel)</label>
          <textarea id="retentionBulkNote" rows="2" class="a-textarea"></textarea>
        </div>`,
      confirmText: CONFIRM,
      secondary: { label: 'Annuleren' },
      danger: {
        label: `Goedkeuren en verwerken (${ids.length} items)`,
        keepOpen: true,
        onClick: () => { this.submitRetentionBulk(handle, { ids }); },
      },
    });
  },

  /* ============================================================
     GENEREREN, DROOGLOOP EN DE BEWAARTABEL
     ============================================================ */
  async generateRetentionList(btn) {
    if (btn) btn.disabled = true;
    try {
      const res = await Auth.fetch('/v1/admin/retention/review/generate', { method: 'POST' });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        const errored = Object.keys(data || {}).filter(k => data[k] && data[k].status === 'error');
        Auth.toast(errored.length
          ? `Lijst aangevuld; ${errored.length} categorie(ën) konden niet geteld worden`
          : 'Lijst aangevuld', errored.length ? 'warning' : 'success');
        await this.refreshRetention();
      } else {
        Auth.toast(this.retentionErrorText(data, res && res.status), 'error');
      }
    } catch {
      Auth.toast('Netwerkfout, probeer het opnieuw.', 'error');
    }
    if (btn) btn.disabled = false;
  },

  async runRetentionDryRun(btn) {
    const el = document.getElementById('retentionDryRun');
    if (btn) btn.disabled = true;
    mount(el, html`<div class="a-state-block"><i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> Laden…</div>`);
    try {
      const res = await Auth.fetch('/v1/admin/retention/run', {
        method: 'POST', body: JSON.stringify({ dry_run: true }),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (!res || !res.ok) {
        mount(el, html`<div class="a-state-block">${this.retentionErrorText(data, res && res.status)}</div>`);
      } else {
        const rows = (data && data.categories) || [];
        mount(el, html`
          <div class="table-responsive">
            <table class="table table-vcenter card-table a-cardlist a-cardlist--compact" aria-label="Droogloop per categorie">
              <thead><tr><th scope="col">Categorie</th><th scope="col">Telling</th><th scope="col">Toelichting</th></tr></thead>
              <tbody>${rows.map(r => html`
                <tr>
                  <td data-label="Categorie" class="a-cell-name">${this.retentionCategoryLabel(r.key)}</td>
                  <td data-label="Telling" class="a-num">${r.count === null || r.count === undefined ? '—' : r.count}</td>
                  <td data-label="Toelichting" class="a-soft">${DRYRUN_STATUS[r.status] || r.status}</td>
                </tr>`)}</tbody>
            </table>
          </div>`);
      }
    } catch {
      mount(el, html`<div class="a-state-block">Kon niet laden, probeer opnieuw.</div>`);
    }
    if (btn) btn.disabled = false;
  },

  async runApolloDryRun(btn) {
    const el = document.getElementById('retentionApolloDryRun');
    if (btn) btn.disabled = true;
    mount(el, html`<div class="a-state-block"><i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> Laden…</div>`);
    try {
      const res = await Auth.fetch('/v1/admin/apollo-pool/purge', {
        method: 'POST', body: JSON.stringify({ dry_run: true }),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (!res || !res.ok) {
        mount(el, html`<div class="a-state-block">${this.retentionErrorText(data, res && res.status)}</div>`);
      } else {
        mount(el, html`
          <div class="row row-cards">
            ${this.retentionTile('In de pool', data.total ?? 0)}
            ${this.retentionTile('Zou anonimiseren', data.would_anonymise ?? 0)}
            ${this.retentionTile('Zou hard verwijderen', data.would_hard_delete ?? 0)}
            ${this.retentionTile('Overgeslagen', data.skipped ?? 0)}
          </div>
          <p class="a-meta mt-3">Overgeslagen: rijen die een beschermend signaal hebben opgepikt en daarom buiten de selectie vallen.</p>`);
      }
    } catch {
      mount(el, html`<div class="a-state-block">Kon niet laden, probeer opnieuw.</div>`);
    }
    if (btn) btn.disabled = false;
  },

  async loadRetentionTable() {
    const el = document.getElementById('retentionTableCard');
    if (!el || el.dataset.loaded === '1') return;
    mount(el, html`<div class="a-state-block"><i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> Laden…</div>`);
    try {
      const res = await Auth.fetch('/v1/admin/retention/table');
      const data = res ? await res.json().catch(() => null) : null;
      if (!res || !res.ok) {
        this.setContainerLoadError(el, () => { el.dataset.loaded = ''; this.loadRetentionTable(); });
        return;
      }
      const rows = (data && data.rows) || [];
      el.dataset.loaded = '1';
      mount(el, html`
        <div class="table-responsive">
          <table class="table table-vcenter card-table a-cardlist" aria-label="Bewaartabel">
            <thead><tr>
              <th scope="col">Categorie</th><th scope="col">Bewaartermijn</th>
              <th scope="col">Bron of opmerking</th><th scope="col">Actie</th>
            </tr></thead>
            <tbody>${rows.map(r => html`
              <tr>
                <td data-label="Categorie" class="a-cell-name">${r.categorie}</td>
                <td data-label="Bewaartermijn">${r.bewaartermijn}</td>
                <td data-label="Bron of opmerking" class="a-soft">${r.bron_opmerking || '—'}</td>
                <td data-label="Actie">
                  ${AdminLabels.label('retentieactie', r.action)}
                  ${r.action === 'retain' || r.action === 'infra_only'
                    ? html`<div class="mt-1"><span class="badge bg-secondary-lt">Komt niet in de beoordelingslijst</span></div>`
                    : ''}
                </td>
              </tr>`)}</tbody>
          </table>
        </div>`);
    } catch {
      this.setContainerLoadError(el, () => { el.dataset.loaded = ''; this.loadRetentionTable(); });
    }
  },

  /* ============================================================
     LADEN EN VERVERSEN
     ============================================================ */
  async loadRetention() {
    await Promise.all([
      this.loadRetentionSummary(),
      this.loadRetentionReview(this._lastParams.retention || { status: 'pending' }),
    ]);
  },

  // Samenvatting en lijst falen los van elkaar, dus ze verversen ook los
  // van elkaar; allSettled zodat één fout de andere niet meesleept.
  async refreshRetention() {
    await Promise.allSettled([
      this.loadRetentionSummary(),
      this.loadRetentionReview(this._lastParams.retention || { status: 'pending' }),
    ]);
  },

  // §7.4 punt 3: is de record na een handeling weg, dan gaat de focus naar
  // de tabelkop en zegt de aria-live-regio wat er gebeurd is.
  focusRetentionTable() {
    const head = document.getElementById('retentionHead');
    if (head) head.focus();
  },

  applyRetentionFilters() {
    this._currentPage.retention = 1;
    this._retention.selected.clear();
    this.loadRetentionReview({
      status: document.getElementById('retentionStatusFilter')?.value || 'pending',
      category: document.getElementById('retentionCategoryFilter')?.value || undefined,
    });
  },
  });

  Admin.registerSection({
    id: 'retention',
    title: 'Bewaartermijnen',
    loader: () => Admin.loadRetention(),
    skeletonHtml: () => html`
      <div id="retentionLive" class="visually-hidden" role="status" aria-live="polite"></div>

      <div class="card mb-3">
        <div class="card-header d-flex flex-wrap align-items-center justify-content-between gap-3">
          <h3 class="card-title mb-0">Samenvatting</h3>
          <button type="button" class="btn btn-outline-secondary" data-action="retention-generate">Lijst genereren</button>
        </div>
        <div class="card-body">
          <div class="row row-cards" id="retentionSummary"></div>
        </div>
      </div>

      <div class="card mb-3">
        <div class="card-header"><h3 class="card-title mb-0">Per categorie</h3></div>
        <div class="table-responsive">
          <table class="table table-vcenter card-table a-cardlist a-cardlist--compact" aria-label="Bewaartermijnen per categorie">
            <thead>
              <tr>
                <th scope="col">Categorie</th>
                <th scope="col">Te beoordelen</th>
                <th scope="col">Afgewezen</th>
                <th scope="col">Verwerkt</th>
                <th scope="col"><span class="visually-hidden">Acties</span></th>
              </tr>
            </thead>
            <tbody id="retentionCategoryBody"></tbody>
          </table>
        </div>
      </div>

      <div class="card mb-3">
        <div class="card-body border-bottom py-3">
          <div class="d-flex flex-wrap gap-3">
            <div>
              <label class="form-label" for="retentionStatusFilter">Status</label>
              <select class="form-select" id="retentionStatusFilter">
                ${STATUS_OPTIONS.map(([v, l]) => html`<option value="${v}">${l}</option>`)}
              </select>
            </div>
            <div>
              <label class="form-label" for="retentionCategoryFilter">Categorie</label>
              <select class="form-select" id="retentionCategoryFilter">
                <option value="">Alle categorieën</option>
              </select>
            </div>
          </div>
        </div>
        <div id="retentionBulkbar" hidden></div>
        <div class="table-responsive">
          <table class="table table-vcenter card-table a-cardlist" aria-label="Goedkeuringslijst bewaartermijnen">
            <thead id="retentionHead" tabindex="-1">
              <tr>
                <th scope="col" class="a-col-check">
                  <label class="a-tap">
                    <input class="form-check-input" type="checkbox" id="retentionSelectAll"
                      data-action="retention-select-all" aria-label="Alles op deze pagina selecteren">
                  </label>
                </th>
                <th scope="col" data-sort-key="category">Categorie</th>
                <th scope="col">Onderwerp</th>
                <th scope="col" data-sort-key="term_expired_at">Termijn verlopen</th>
                <th scope="col">Ontbrekend signaal</th>
                <th scope="col" data-sort-key="action">Actie</th>
                <th scope="col" data-sort-key="status">Status</th>
                <th scope="col" class="a-col-actions"><span class="visually-hidden">Rijacties</span></th>
              </tr>
            </thead>
            <tbody id="retentionBody"></tbody>
          </table>
        </div>
        <div class="card-footer d-flex flex-wrap align-items-center justify-content-between gap-3">
          <div class="a-meta" id="retentionCount"></div>
          <div class="pagination-wrap" id="retentionPagination"></div>
        </div>
      </div>

      <details class="card mb-3 a-disclosure">
        <summary>Droogloop</summary>
        <div class="card-body">
          <p class="a-soft">Toont wat een volledige telling nu zou vinden. Deze aanroep telt alleen en verandert niets.</p>
          <button type="button" class="btn btn-outline-secondary" data-action="retention-dryrun">Uitvoeren</button>
          <div id="retentionDryRun" class="mt-4"></div>
        </div>
      </details>

      <details class="card mb-3 a-disclosure">
        <summary>Apollo-bulkpool</summary>
        <div class="card-body">
          <p class="a-soft">Telt de bulk-geharveste Apollo-rijen. Deze aanroep telt alleen en verandert niets.</p>
          <button type="button" class="btn btn-outline-secondary" data-action="retention-apollo-dryrun">Uitvoeren</button>
          <div id="retentionApolloDryRun" class="mt-4"></div>
          <p class="a-meta mt-3">Verwijderen gebeurt uitsluitend via de beoordelingslijst hierboven, categorie Apollo-bulkpool.</p>
        </div>
      </details>

      <details class="card a-disclosure" id="retentionTableDetails">
        <summary>Bewaartabel</summary>
        <div class="card-body" id="retentionTableCard"></div>
      </details>`,
    filters: [
      { selector: '#retentionStatusFilter', event: 'change', handler: () => Admin.applyRetentionFilters() },
      { selector: '#retentionCategoryFilter', event: 'change', handler: () => Admin.applyRetentionFilters() },
      { selector: '#retentionTableDetails', event: 'toggle', handler: (el) => { if (el.open) Admin.loadRetentionTable(); } },
    ],
    actions: {
      'retention-generate': (el) => Admin.generateRetentionList(el),
      'retention-refresh-summary': (el, e) => { e.preventDefault(); Admin.loadRetentionSummary(); },
      'retention-approve': (el) => Admin.openRetentionApprove(Number(el.dataset.id)),
      'retention-reject': (el) => Admin.openRetentionReject(Number(el.dataset.id)),
      'retention-select': (el) => Admin.toggleRetentionSelection(Number(el.dataset.id), el.checked),
      'retention-select-all': (el) => Admin.toggleRetentionSelectAll(el.checked),
      'retention-clear-selection': () => Admin.clearRetentionSelection(),
      'retention-bulk-approve': () => Admin.openRetentionBulkApprove(),
      'retention-bulk-reject': (el) => Admin.bulkRejectSelection(el),
      'retention-bulk-retry': (el) => Admin.retryRetentionBulk((el.dataset.ids || '').split(',').map(Number).filter(Boolean)),
      'retention-bulk-refresh': () => {
        if (Admin._retentionCategoryModal && Admin._retentionCategoryModalCategory) {
          Admin.fillRetentionCategoryModal(Admin._retentionCategoryModal, Admin._retentionCategoryModalCategory);
        }
      },
      'retention-category-view': (el) => {
        const sel = document.getElementById('retentionCategoryFilter');
        const status = document.getElementById('retentionStatusFilter');
        if (sel) sel.value = el.dataset.category;
        if (status) status.value = 'pending';
        Admin.applyRetentionFilters();
      },
      'retention-category-approve': (el) => Admin.openRetentionCategoryApprove(el.dataset.category),
      'retention-toggle-signal': (el) => Admin.toggleRetentionSignal(Number(el.dataset.id), el),
      'retention-dryrun': (el) => Admin.runRetentionDryRun(el),
      'retention-apollo-dryrun': (el) => Admin.runApolloDryRun(el),
    },
  });
})();
