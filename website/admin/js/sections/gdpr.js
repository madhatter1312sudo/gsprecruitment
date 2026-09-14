/* ============================================================
   GSP Recruitment -- admin/js/sections/gdpr.js
   AVG: wissen en suppressielijst, SITE-DESIGN-SPEC.md §7.3.5.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern), ui.js, labels.js en candidates.js (Admin._wireBlurValidate/
   Admin._validateEmail, §7.2d), voor nav.js dat de registry uitleest.
   Geen ES-module: de rest van de site gebruikt die ook niet.

   Endpoints (talent-os/backend/routers/gdpr.py, regels 771-923, nagelezen):
     POST /api/v1/admin/gdpr/erase        AdminEraseRequest { email, confirm,
                                           confirm_admin_or_self } -> erase_person()
     POST /api/v1/admin/suppression       SuppressionCreate { email, reason }
     GET  /api/v1/admin/suppression?limit=&offset=  -> { items, total, limit, offset }

   Wat dit bestand doet, en wat het bewust niet doet:
     - Het ingevoerde adres gaat nooit naar localStorage, de URL of de
       console -- ook niet bij een fout. Een foutmelding toont alleen de
       vaste Nederlandse zin; de foutcode zelf mag naar de console (§7.2f),
       een e-mailadres nooit.
     - `confirm` is wat er in het bevestigingsveld van de modal getypt is
       (handle.confirmValue()), niet het buitenste e-mailveld van de kaart:
       dat zijn twee losse velden, en de backend vergelijkt ze zelf ook pas
       na normalisatie (privacy.normalize_email, strip + lower).
     - confirm_admin_or_self gaat nooit standaard mee. Eerst een aanroep
       zonder; alleen een 409 met erase_admin_or_self_requires_confirm
       ontgrendelt de tweede stap (waarschuwing plus checkbox), en pas
       daarna gaat de tweede knop aan.
     - De suppressielijst kent geen domeinfilter op de backend (GET
       /admin/suppression neemt alleen limit/offset): het zoekveld filtert
       daarom uitsluitend binnen de al geladen pagina, niet de hele
       verzameling.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  const SUPPRESSION_PAGE_SIZE = 100;

  // §7.2f punt 2: één eigen Nederlandse zin per code die dit scherm kent.
  const ERROR_TEXT = {
    erase_confirm_must_match_email:
      'De bevestiging komt niet overeen met het e-mailadres. Typ het adres opnieuw, precies zoals hierboven.',
    erase_admin_or_self_requires_confirm:
      'Dit adres hoort bij een beheerdersaccount of bij je eigen account. Wissen verwijdert die toegang.',
  };

  // §7.3.5: de opsomming in de destructieve modal, letterlijk gelezen uit
  // erase_person() (talent-os/backend/routers/gdpr.py regels 340-749) --
  // niet verzonnen. Elke rij noemt de tabel(len) en of het gaat om
  // anonimiseren dan wel (hard) verwijderen.
  const ERASE_EFFECTS = [
    ['Kandidaatgegevens (naam, contactgegevens, opleiding, immigratiestatus)', 'Geanonimiseerd'],
    ['CV-tekst en CV-bestand in de opslag', 'Verwijderd'],
    ['Portalaccount (indien aanwezig)', 'Geanonimiseerd'],
    ['Pushmeldingen op het portalaccount', 'Verwijderd'],
    ['Notities bij pipeline-stappen', 'Verwijderd (leeggemaakt)'],
    ['Verzendingen van vacature-alerts', 'Verwijderd'],
    ['Prospectgegevens (als contactpersoon bij een opdrachtgever)', 'Geanonimiseerd'],
    ['Outreach-concepten en verzonden berichten', 'Geanonimiseerd'],
    ['Quiz- en contactformulieren', 'Geanonimiseerd'],
    ['Eerdere AVG-verzoeken over dit adres', 'Geanonimiseerd'],
    ['Auditlogregels die dit adres noemen', 'Adres vervangen door een hash'],
    ['Suppressielijst', 'Adres toegevoegd, zodat het niet opnieuw wordt benaderd'],
  ];

  Object.assign(Admin, {
  _gdpr: {
    erase: { needsAdminConfirm: false, adminConfirmChecked: false, submitting: false, done: false },
    suppression: { items: [], total: 0, filter: '' },
  },

  gdprDate(d) {
    if (!d) return '—';
    const dt = new Date(d);
    return isNaN(dt.getTime())
      ? '—'
      : dt.toLocaleDateString('nl-NL', { day: 'numeric', month: 'short', year: 'numeric' });
  },

  // Eerste vier en laatste drie tekens van de hash, met de volledige hash
  // in title= (§7.3.5). Nooit het adres zelf: de API geeft dat niet terug.
  gdprShortHash(hash) {
    const h = String(hash || '');
    if (h.length <= 8) return h;
    return `${h.slice(0, 4)}…${h.slice(-3)}`;
  },

  gdprErrorText(payload, status) {
    const d = this.errorDetail(payload);
    if (d.code) console.warn('gdpr: API-foutcode', d.code);
    if (status === 401 || status === 403) return 'Je hebt geen rechten voor deze handeling.';
    if (d.code && ERROR_TEXT[d.code]) return ERROR_TEXT[d.code];
    if (d.message) return d.message;
    return 'Er ging iets mis, probeer het opnieuw.';
  },

  gdprAlert(containerId, text, opts = {}) {
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

  // §7.2f punt 2, waarschuwingstoon (geen fout): voor de tweede-stap-melding.
  gdprWarning(containerId, text) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!text) { mount(el, ''); return; }
    mount(el, html`
      <div class="alert alert-warning" role="alert">
        <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
        <span>${text}</span>
      </div>`);
  },

  /* ============================================================
     WISSEN (art. 17)
     ============================================================ */
  gdprValidateEraseEmail() {
    const el = document.getElementById('gdprEraseEmail');
    if (!el) return false;
    return this._validateEmail(el, 'gdprEraseEmailError');
  },

  openGdprErase() {
    const ok = this.gdprValidateEraseEmail();
    if (!ok) return;
    const email = document.getElementById('gdprEraseEmail').value.trim();
    this._gdpr.erase = { needsAdminConfirm: false, adminConfirmChecked: false, submitting: false, done: false, email };

    const handle = ui.modal({
      id: 'gdprEraseModal',
      title: 'Deze gegevens worden onomkeerbaar gewist',
      body: this.gdprEraseBody(email),
      confirmText: email,
      confirmCaseInsensitive: true,
      confirmInputType: 'email',
      secondary: { label: 'Annuleren' },
      danger: {
        label: 'Wissen (definitief)',
        keepOpen: true,
        onClick: () => { this.submitGdprErase(handle, false); },
      },
      primary: {
        label: 'Wissen en beheerderstoegang verwijderen',
        keepOpen: true,
        onClick: () => { this.submitGdprErase(handle, true); },
      },
    });
    this._gdprEraseHandle = handle;
    // De tweede knop bestaat pas na een 409: verborgen en op slot tot dat
    // moment, en de getypte bevestiging mag hem tot dan niet aanzetten.
    const primaryBtn = handle.button('primary');
    if (primaryBtn) { primaryBtn.hidden = true; primaryBtn.dataset.gspLock = '1'; }
  },

  gdprEraseBody(email) {
    return html`
      <div id="gdprEraseAlert"></div>
      <p>Adres: <span class="a-num a-cell-strong">${email}</span></p>
      <div class="a-panel">
        <p class="a-field-label mb-2">Wat er gebeurt</p>
        ${ERASE_EFFECTS.map(([what, action]) => html`
          <div class="a-metric-row"><span class="a-soft">${what}</span><span>${action}</span></div>`)}
      </div>
      <div id="gdprEraseSecondStep"></div>
      <div id="gdprEraseResult"></div>`;
  },

  gdprShowSecondStep(handle) {
    const el = document.getElementById('gdprEraseSecondStep');
    if (!el) return;
    mount(el, html`
      <div class="alert alert-warning" role="alert">
        <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
        <span>Dit adres hoort bij een beheerdersaccount of bij je eigen account. Wissen verwijdert die toegang.</span>
      </div>
      <div class="form-check mb-0">
        <input class="form-check-input" type="checkbox" id="gdprEraseAdminConfirm">
        <label class="form-check-label" for="gdprEraseAdminConfirm">Ik begrijp dat hiermee beheerderstoegang verdwijnt</label>
      </div>`);
    const cb = document.getElementById('gdprEraseAdminConfirm');
    const primaryBtn = handle.button('primary');
    if (primaryBtn) {
      primaryBtn.hidden = false;
      // Dit is de tweede, destructieve stap (beheerderstoegang gaat mee weg):
      // rood, niet goud. ui.modal kent maar één rode rol (danger) per modal,
      // en die is hier al bezet door de eerste knop -- de klassen op deze
      // node worden daarom hier omgezet, in plaats van via een tweede
      // opts.danger, wat ui.modal niet aanbiedt.
      primaryBtn.classList.remove('btn-primary');
      primaryBtn.classList.add('btn-outline-danger');
    }
    // security-auditor op a2ec6ed: het bevestigingsveld bleef na de 409
    // bewerkbaar, dus confirm kon bij de tweede aanroep (confirm_admin_or_self:
    // true) een andere tekenreeks dragen dan bij de eerste. Op slot, zodat
    // een tweede klik onmogelijk een ander adres bevestigt dan de eerste
    // aanroep al deed; submitGdprErase() leest de waarde bovendien maar
    // eenmaal in (state.confirmSent), niet opnieuw per aanroep.
    const confirmField = document.querySelector('#gdprEraseModal input[type="email"]');
    if (confirmField) confirmField.disabled = true;
    if (cb) {
      cb.addEventListener('change', () => {
        this._gdpr.erase.adminConfirmChecked = cb.checked;
        if (!primaryBtn) return;
        if (cb.checked) {
          delete primaryBtn.dataset.gspLock;
          handle.syncGate();
        } else {
          primaryBtn.dataset.gspLock = '1';
          primaryBtn.disabled = true;
        }
      });
    }
  },

  async submitGdprErase(handle, confirmAdminOrSelf) {
    const state = this._gdpr.erase;
    // Dubbele verzending (dubbelklik, Enter na een klik) uitsluiten: één
    // aanroep per klik op een niet-vergrendelde knop, en de knoppen gaan
    // met setBusy(true) meteen op disabled.
    if (state.submitting || state.done) return;
    if (confirmAdminOrSelf && !state.adminConfirmChecked) return;
    state.submitting = true;
    this.gdprAlert('gdprEraseAlert', '');
    handle.setBusy(true);
    // security-auditor op a2ec6ed: ingelezen bij de EERSTE aanroep en
    // daarna hergebruikt, niet bij elke aanroep opnieuw van het (na de 409
    // toch al vergrendelde) veld gelezen -- zo dragen de eerste aanroep
    // (confirm_admin_or_self weggelaten) en de tweede (na de checkbox)
    // gegarandeerd hetzelfde `confirm`, ongeacht of het veld op enig moment
    // toch nog bewerkbaar zou zijn.
    if (state.confirmSent === undefined) state.confirmSent = handle.confirmValue();
    const payload = {
      email: state.email,
      confirm: state.confirmSent,
      confirm_admin_or_self: !!confirmAdminOrSelf,
    };
    try {
      const res = await Auth.fetch('/v1/admin/gdpr/erase', { method: 'POST', body: JSON.stringify(payload) });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        state.done = true;
        this.gdprRenderEraseResult(handle, data);
        Auth.toast('Persoon gewist', 'success');
        document.getElementById('gdprEraseEmail').value = '';
        return;
      }
      const d = this.errorDetail(data);
      if (res && res.status === 409 && d.code === 'erase_admin_or_self_requires_confirm' && !confirmAdminOrSelf) {
        state.needsAdminConfirm = true;
        state.submitting = false;
        this.gdprShowSecondStep(handle);
        handle.setBusy(false);
        // De eerste knop heeft zijn antwoord al gehad (409): verder klikken
        // herhaalt alleen dezelfde weigering. Op slot tot deze modal opnieuw
        // wordt geopend; de tweede knop draagt de verdere handeling.
        const dangerBtn = handle.button('danger');
        if (dangerBtn) { dangerBtn.disabled = true; dangerBtn.dataset.gspLock = '1'; }
        return;
      }
      this.gdprAlert('gdprEraseAlert', this.gdprErrorText(data, res && res.status));
    } catch {
      this.gdprAlert('gdprEraseAlert', 'Netwerkfout, probeer het opnieuw.');
    }
    state.submitting = false;
    handle.setBusy(false);
  },

  gdprRenderEraseResult(handle, data) {
    const d = data || {};
    const cvFailed = Array.isArray(d.cv_files_failed) ? d.cv_files_failed.length : 0;
    handle.setBody(html`
      <div class="a-panel">
        <div class="a-metric-row"><span class="a-soft">Status</span><span>${d.status === 'partial' ? 'Gedeeltelijk verwerkt' : 'Volledig verwerkt'}</span></div>
        <div class="a-metric-row"><span class="a-soft">CV-bestanden verwijderd</span><span class="a-num">${Array.isArray(d.cv_files_deleted) ? d.cv_files_deleted.length : 0}</span></div>
        <div class="a-metric-row"><span class="a-soft">CV-bestanden mislukt</span><span class="a-num">${cvFailed}</span></div>
      </div>
      ${cvFailed ? html`<p class="a-soft">Een of meer CV-bestanden konden niet worden verwijderd; dat staat gelogd voor handmatige opvolging.</p>` : ''}`);
    // Op slot: dubbele verzending is nu onmogelijk, ook via Enter of een
    // tweede klik op wat er nog van de knoppen staat.
    ['primary', 'danger', 'secondary'].forEach((role) => {
      const btn = handle.button(role);
      if (btn) { btn.disabled = true; btn.dataset.gspLock = '1'; }
    });
  },

  /* ============================================================
     SUPPRESSIELIJST
     ============================================================ */
  async loadGdprSuppression() {
    const container = document.getElementById('gdprSuppressionBody');
    if (container) this.setLoading('#gdprSuppressionBody', 4);
    try {
      const offset = ((this._currentPage.gdpr || 1) - 1) * SUPPRESSION_PAGE_SIZE;
      const res = await Auth.fetch(`/v1/admin/suppression?limit=${SUPPRESSION_PAGE_SIZE}&offset=${offset}`);
      if (!res) throw new Error('geen respons');
      const data = await res.json().catch(() => null);
      if (!res.ok) throw new Error('fout');
      this._gdpr.suppression.items = (data && data.items) || [];
      this._gdpr.suppression.total = (data && data.total) || 0;
      this.renderGdprSuppression();
      this.renderPagination('gdprSuppressionPagination', this._gdpr.suppression.total,
        SUPPRESSION_PAGE_SIZE, this._currentPage.gdpr || 1, 'gdpr');
    } catch {
      this.setLoadError('#gdprSuppressionBody', 4, () => this.loadGdprSuppression());
      mount(document.getElementById('gdprSuppressionCount'), '');
    }
  },

  renderGdprSuppression() {
    const all = this._gdpr.suppression.items;
    const needle = (this._gdpr.suppression.filter || '').trim().toLowerCase();
    const rows = needle ? all.filter(r => (r.email_domain || '').toLowerCase().includes(needle)) : all;

    const countEl = document.getElementById('gdprSuppressionCount');
    if (countEl) {
      mount(countEl, needle
        ? html`${rows.length} van ${all.length} op deze pagina`
        : html`${all.length} van ${this._gdpr.suppression.total}`);
    }

    if (!all.length) {
      this.setEmpty('#gdprSuppressionBody', 4, 'Nog geen adressen op de suppressielijst.');
      return;
    }
    if (!rows.length) {
      this.setEmpty('#gdprSuppressionBody', 4,
        'Geen adressen op deze pagina met dit domein. De suppressielijst kent geen zoekopdracht over de hele lijst.');
      return;
    }
    mount(document.querySelector('#gdprSuppressionBody'), html`${rows.map(r => this.renderGdprSuppressionRow(r))}`);
  },

  renderGdprSuppressionRow(r) {
    const shortHash = this.gdprShortHash(r.email_hash);
    const copyId = `gdprHashCopy${r.id}`;
    return html`
      <tr>
        <td data-label="Domein" class="a-cell-name">${r.email_domain || '—'}</td>
        <td data-label="Reden">${r.reason || '—'}</td>
        <td data-label="Toegevoegd op" class="a-num a-num--date">${this.gdprDate(r.created_at)}</td>
        <td data-label="Hash">
          <span class="a-num a-soft" title="${r.email_hash || ''}">${shortHash}</span>
          <button type="button" class="btn btn-sm btn-ghost-secondary" id="${copyId}"
            data-action="gdpr-copy-hash" data-hash="${r.email_hash || ''}"
            aria-label="Volledige hash kopiëren">
            <i class="fa-regular fa-copy"></i>
          </button>
        </td>
      </tr>`;
  },

  applyGdprSuppressionFilter(term) {
    this._gdpr.suppression.filter = term || '';
    this.renderGdprSuppression();
  },

  async copyGdprHash(hash) {
    if (!hash) return;
    try {
      await navigator.clipboard.writeText(hash);
      Auth.toast('Hash gekopieerd', 'success');
    } catch {
      Auth.toast('Kopiëren mislukt, selecteer en kopieer de hash handmatig', 'warning');
    }
  },

  gdprValidateSuppressionEmail() {
    const el = document.getElementById('gdprSuppressionEmail');
    if (!el) return false;
    return this._validateEmail(el, 'gdprSuppressionEmailError');
  },

  openGdprSuppressionAdd() {
    const handle = ui.modal({
      id: 'gdprSuppressionModal',
      title: 'Adres toevoegen aan de suppressielijst',
      body: html`
        <div id="gdprSuppressionFormAlert"></div>
        <div class="form-group">
          <label class="form-label" for="gdprSuppressionEmail">E-mailadres *</label>
          <input type="email" class="form-control" id="gdprSuppressionEmail" autocomplete="off">
          <div class="invalid-feedback" id="gdprSuppressionEmailError"></div>
        </div>
        <div class="form-group mb-0">
          <label class="form-label" for="gdprSuppressionReason">Reden</label>
          <input type="text" class="form-control" id="gdprSuppressionReason" value="STOP" maxlength="200">
        </div>
        <div class="a-panel mt-3">
          <p class="a-field-label mb-2">Wat er verder gebeurt</p>
          <div class="a-metric-row"><span class="a-soft">Openstaande concept-outreach naar dit adres</span><span>Afgekeurd</span></div>
          <div class="a-metric-row"><span class="a-soft">Kandidaatrij (indien aanwezig)</span><span>Toestemming ingetrokken</span></div>
          <div class="a-metric-row"><span class="a-soft">Prospectrij (indien aanwezig)</span><span>Afgemeld</span></div>
        </div>`,
      secondary: { label: 'Annuleren' },
      primary: {
        label: 'Toevoegen',
        keepOpen: true,
        onClick: () => { this.submitGdprSuppressionAdd(handle); },
      },
    });
    const el = document.getElementById('gdprSuppressionEmail');
    this._wireBlurValidate(el, () => this.gdprValidateSuppressionEmail());
  },

  async submitGdprSuppressionAdd(handle) {
    const ok = this.gdprValidateSuppressionEmail();
    if (!ok) return;
    const email = document.getElementById('gdprSuppressionEmail').value.trim();
    const reason = document.getElementById('gdprSuppressionReason').value.trim() || 'STOP';
    this.gdprAlert('gdprSuppressionFormAlert', '');
    handle.setBusy(true);
    try {
      const res = await Auth.fetch('/v1/admin/suppression', {
        method: 'POST', body: JSON.stringify({ email, reason }),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        handle.close();
        Auth.toast('Adres toegevoegd', 'success');
        this._currentPage.gdpr = 1;
        await this.loadGdprSuppression();
        return;
      }
      this.gdprAlert('gdprSuppressionFormAlert', this.gdprErrorText(data, res && res.status));
    } catch {
      this.gdprAlert('gdprSuppressionFormAlert', 'Netwerkfout, probeer het opnieuw.');
    }
    handle.setBusy(false);
  },
  });

  Admin.registerSection({
    id: 'gdpr',
    title: 'AVG',
    loader: () => Admin.loadGdprSuppression(),
    skeletonHtml: () => html`
      <div class="card mb-3">
        <div class="card-header"><h3 class="card-title mb-0">Persoon wissen (art. 17)</h3></div>
        <div class="card-body">
          <div class="alert alert-warning" role="alert">
            <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
            <span>Dit wist alle persoonsgegevens van dit adres uit alle tabellen. Dit is niet ongedaan te maken.</span>
          </div>
          <div class="form-group mb-0">
            <label class="form-label" for="gdprEraseEmail">E-mailadres</label>
            <input type="email" class="form-control" id="gdprEraseEmail" autocomplete="off">
            <div class="invalid-feedback" id="gdprEraseEmailError"></div>
          </div>
          <div class="a-actions mt-3">
            <button type="button" class="btn btn-outline-danger" data-action="gdpr-open-erase">Zoeken en wissen</button>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header d-flex flex-wrap align-items-center justify-content-between gap-3">
          <h3 class="card-title mb-0">Suppressielijst</h3>
          <button type="button" class="btn btn-primary" data-action="gdpr-open-suppression-add">
            <i class="fa-solid fa-plus me-1"></i>Adres toevoegen
          </button>
        </div>
        <div class="card-body border-bottom py-3">
          <p class="a-soft mb-3">Deze lijst bewaart geen volledige e-mailadressen; alleen een onomkeerbare hash en het domein.</p>
          <div>
            <label class="form-label" for="gdprSuppressionSearch">Domein</label>
            <input type="text" class="form-control" id="gdprSuppressionSearch" placeholder="bijvoorbeeld voorbeeld.nl">
          </div>
        </div>
        <div class="card-body border-bottom py-2">
          <div class="a-meta" id="gdprSuppressionCount"></div>
        </div>
        <div class="table-responsive">
          <table class="table table-vcenter card-table a-cardlist" aria-label="Suppressielijst">
            <thead>
              <tr>
                <th scope="col">Domein</th>
                <th scope="col">Reden</th>
                <th scope="col">Toegevoegd op</th>
                <th scope="col">Hash</th>
              </tr>
            </thead>
            <tbody id="gdprSuppressionBody"></tbody>
          </table>
        </div>
        <div class="card-footer d-flex justify-content-center">
          <div class="pagination-wrap" id="gdprSuppressionPagination"></div>
        </div>
      </div>`,
    filters: [
      { selector: '#gdprSuppressionSearch', event: 'input', debounce: 200,
        handler: (el) => Admin.applyGdprSuppressionFilter(el.value) },
    ],
    actions: {
      'gdpr-open-erase': () => Admin.openGdprErase(),
      'gdpr-open-suppression-add': () => Admin.openGdprSuppressionAdd(),
      'gdpr-copy-hash': (el) => Admin.copyGdprHash(el.dataset.hash),
    },
  });
  Admin._currentPage.gdpr = Admin._currentPage.gdpr || 1;
  // §7.2d: op blur, en pas erna ook op elke input (nooit tijdens het eerste
  // typen). skeletonHtml() hierboven is al in de DOM gezet door
  // registerSection(), dus het veld bestaat op dit moment al.
  Admin._wireBlurValidate(document.getElementById('gdprEraseEmail'), () => Admin.gdprValidateEraseEmail());
})();
