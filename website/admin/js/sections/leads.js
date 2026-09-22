/* ============================================================
   GSP Recruitment — admin/js/sections/leads.js
   Leadsinbox over contact- en quizinzendingen heen.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern) en voor nav.js, dat de registry uitleest. Geen ES-module: de
   rest van de site gebruikt die ook niet.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  Object.assign(Admin, {
  /* ============================================================
     LEADS (WS-C.10) — unified inbox: GET /v1/admin/leads across
     contact_submissions + quiz_submissions, PATCH marks one row read.
     ============================================================ */
  async loadLeads(params = {}) {
    this._lastParams.leads = params;
    const qs = new URLSearchParams();
    const limit = this._pageSize;
    const offset = ((this._currentPage.leads || 1) - 1) * limit;
    if (params.type) qs.set('type', params.type);
    if (params.unread) qs.set('unread', 'true');
    qs.set('limit', limit);
    qs.set('offset', offset);

    this.setLoading('#leadsTable tbody', 7);
    try {
      const res = await Auth.fetch(`/v1/admin/leads?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.leads = data;
      this.renderLeads(data);
      this.renderPagination('leadsPagination', data.total, limit, this._currentPage.leads, 'leads');
    } catch {
      this.setLoadError('#leadsTable tbody', 7, () => this.loadLeads(params));
    }
  },

  // source_page + referrer_host (WS2, migrations/038_leads_origin.py) as
  // one compact column — a lead with neither renders "—" rather than an
  // empty cell.
  leadOriginText(l) {
    const parts = [];
    if (l.source_page) parts.push(l.source_page);
    if (l.referrer_host) parts.push(`via ${l.referrer_host}`);
    return parts.length ? parts.join(' · ') : '—';
  },

  renderLeads(data) {
    const tbody = document.querySelector('#leadsTable tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#leadsTable tbody', 7, 'Geen leads gevonden voor deze filters.'); return; }
    mount(tbody, html`${items.map(l => html`
      <tr data-action="view-lead" data-source="${l.source}" data-id="${l.id}"
        class="a-clickable${raw(l.is_read ? '' : ' a-row-unread')}">
        <td><span class="badge ${l.source === 'quiz_submissions' ? 'bg-yellow-lt' : 'bg-blue-lt'}">${l.source === 'quiz_submissions' ? 'Quiz' : 'Contact'}</span></td>
        <td class="a-cell-strong">${l.name || '—'}</td>
        <td class="a-soft">${l.email || '—'}</td>
        <td>${l.interest_type ? html`<span class="badge bg-secondary-lt">${this.leadInterestLabel(l.interest_type)}</span>` : '—'}</td>
        <td class="a-meta">${this.leadOriginText(l)}</td>
        <td class="a-soft">${this.formatDate(l.created_at)}</td>
        <td>${l.is_read
          ? html`<span class="badge bg-secondary-lt">Gelezen</span>`
          : html`<span class="badge bg-green-lt">Ongelezen</span>`}</td>
      </tr>`)}`);
  },

  /* ---- Lead detail modal (WS2) ---- */
  async viewLeadDetail(source, leadId) {
    this.openModal('leadDetailModal', html`
      <div class="a-state-cell">
        <i class="fa-solid fa-spinner fa-spin"></i> Laden…
      </div>`);
    try {
      const res = await Auth.fetch(`/v1/admin/leads/${source}/${leadId}`);
      if (!res?.ok) {
        const d = await res?.json().catch(() => null);
        this.openModal('leadDetailModal', html`
          <p class="a-soft">${d?.detail || 'Er ging iets mis bij het ophalen van deze lead.'}</p>
          <div class="a-actions">
            <button class="btn btn-primary btn-sm" data-action="view-lead" data-source="${source}" data-id="${leadId}">Opnieuw proberen</button>
            <button class="btn btn-ghost-secondary btn-sm" data-action="close-modal">Sluiten</button>
          </div>`, { title: 'Kon lead niet laden' });
        return;
      }
      const detail = await res.json();
      this._data.leadDetail = detail;
      this.renderLeadDetailModal(detail);
    } catch {
      this.openModal('leadDetailModal', html`
        <p class="a-soft">Kon geen verbinding maken met de server.</p>
        <div class="a-actions">
          <button class="btn btn-primary btn-sm" data-action="view-lead" data-source="${source}" data-id="${leadId}">Opnieuw proberen</button>
          <button class="btn btn-ghost-secondary btn-sm" data-action="close-modal">Sluiten</button>
        </div>`, { title: 'Netwerkfout' });
    }
  },

  // detail is the full row GET /v1/admin/leads/{source}/{id} returns --
  // contact_submissions rows carry message/company/phone/interest_type,
  // quiz_submissions rows carry score/max_score/tier/domain_scores instead
  // (neither table has both, see routers/admin.py's _leads_union_sql).
  renderLeadDetailModal(detail) {
    const isQuiz = detail.source === 'quiz_submissions';
    const field = (label, value) => html`
      <div class="mb-3">
        <div class="a-field-label">${label}</div>
        <div class="a-cell-strong">${value}</div>
      </div>`;
    const domainScores = (detail.domain_scores && typeof detail.domain_scores === 'object')
      ? html`<ul class="a-inline-list">${Object.entries(detail.domain_scores).map(([k, v]) => html`<li>${k}: ${v}</li>`)}</ul>`
      : raw('—');

    this.openModal('leadDetailModal', html`
      ${field('E-mail', detail.email || '—')}
      ${isQuiz ? html`
        ${field('Score', (detail.score != null && detail.max_score != null) ? `${detail.score} / ${detail.max_score}` : '—')}
        ${field('Tier', detail.tier || '—')}
        ${field('Domeinscores', domainScores)}
      ` : html`
        ${field('Bedrijf', detail.company || '—')}
        ${field('Telefoon', detail.phone || '—')}
        ${field('Categorie', detail.interest_type ? this.leadInterestLabel(detail.interest_type) : '—')}
        ${field('Bericht', detail.message || '—')}
      `}
      ${field('Herkomst', this.leadOriginText(detail))}
      ${field('Datum', this.formatDate(detail.created_at))}
      ${field('Status', detail.is_read
        ? html`<span class="badge bg-secondary-lt">Gelezen</span>`
        : html`<span class="badge bg-green-lt">Ongelezen</span>`)}
      <div class="a-actions">
        <button class="btn btn-sm ${detail.is_read ? 'btn-ghost-secondary' : 'btn-primary'}"
          data-action="toggle-lead-read" data-source="${detail.source}" data-id="${detail.id}" data-read="${detail.is_read ? '1' : '0'}">
          ${detail.is_read ? 'Markeer als ongelezen' : 'Markeer als gelezen'}
        </button>
        <button class="btn btn-ghost-secondary btn-sm" data-action="close-modal">Sluiten</button>
      </div>`, { title: isQuiz ? 'Quiz-inzending' : (detail.name || 'Lead') });
  },

  // Called from the explicit modal button only (never from a row click —
  // that accidental toggle-on-click was the WS2 defect). Updates the open
  // modal in place from the PATCH response, then refreshes the leads list
  // in the background so the row/unread badges/Rapportage counter stay in
  // sync without re-fetching the detail itself.
  async toggleLeadRead(source, leadId, currentlyRead) {
    try {
      const res = await Auth.fetch(`/v1/admin/leads/${source}/${leadId}`, {
        method: 'PATCH', body: JSON.stringify({ is_read: !currentlyRead }),
      });
      if (res?.ok) {
        const updated = await res.json().catch(() => null);
        if (this._data.leadDetail && this._data.leadDetail.source === source && this._data.leadDetail.id === leadId) {
          this._data.leadDetail.is_read = updated ? !!updated.is_read : !currentlyRead;
          this.renderLeadDetailModal(this._data.leadDetail);
        }
        this.loadLeads(this._lastParams.leads || {});
      } else {
        Auth.toast('Bijwerken mislukt', 'error');
      }
    } catch { Auth.toast('Netwerkfout', 'error'); }
  },

  /* ============================================================
     PROSPECTS (§7.3.6(c)) — bedrijfsprospects (client_prospects), zelfde
     sectie als de leads-inbox hierboven (SITE-DESIGN-SPEC.md §7.8: "Leads
     | Binnengekomen leads en prospects"). GET/PUT /v1/admin/prospects
     bestaan al (routers/prospects.py); de klantdrawer las de lijst al
     read-only (Admin.loadClientProspectsTab, clients.js). Hier komt de
     eerste bewerkactie bij: alleen de velden die daadwerkelijk gewijzigd
     zijn gaan mee (model_dump(exclude_none=True) aan de backendkant), en
     de <datalist> voor status bevat uitsluitend de waarden die in de
     geladen lijst voorkomen (de kolom kent geen CHECK en dit scherm
     verzint geen canonieke lijst).
     ============================================================ */
  async loadProspects() {
    this.setLoading('#prospectsTable tbody', 5);
    try {
      const res = await Auth.fetch('/v1/admin/prospects?limit=200');
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error();
      this._data.prospects = data.items || [];
      this.renderProspects(this._data.prospects);
    } catch {
      this.setLoadError('#prospectsTable tbody', 5, () => this.loadProspects());
    }
  },

  renderProspects(items) {
    const tbody = document.querySelector('#prospectsTable tbody');
    if (!tbody) return;
    if (!items.length) { this.setEmpty('#prospectsTable tbody', 5, 'Nog geen prospects.'); return; }
    mount(tbody, html`${items.map(p => html`
      <tr>
        <td class="a-cell-name">${p.company_name || '—'}</td>
        <td class="a-soft">${p.contact_name || '—'}</td>
        <td><span class="${this.badge(p.status)}">${p.status || '—'}</span></td>
        <td class="a-soft">${p.lawful_basis ? AdminLabels.label('grondslag', p.lawful_basis, p.lawful_basis) : '—'}</td>
        <td>
          <button type="button" class="btn btn-sm btn-ghost-secondary" data-action="edit-prospect" data-id="${p.id}">
            <i class="fa-solid fa-pen" aria-hidden="true"></i> <span class="visually-hidden">Bewerken</span>
          </button>
        </td>
      </tr>`)}`);
  },

  // Alleen de waarden die in de geladen lijst voorkomen -- er is geen
  // canonieke lijst om uit te putten en dit scherm verzint er geen
  // (§7.3.6(c), model/schemas.py client_prospects.status heeft geen CHECK).
  prospectStatusOptions() {
    const seen = new Set((this._data.prospects || []).map(p => p.status).filter(Boolean));
    return Array.from(seen).sort();
  },

  openEditProspectModal(prospectId) {
    const p = (this._data.prospects || []).find(x => x.id === prospectId);
    if (!p) return;
    const statusOptions = this.prospectStatusOptions();
    const lawfulBases = ['zakelijk_functioneel_adres', 'opt_in', 'bestaande_relatie'];
    this.openModal('editProspectModal', html`
      <div id="prospectFormAlert"></div>
      <div class="form-group">
        <label class="form-label" for="prospectStatus">Status</label>
        <input type="text" class="form-control" id="prospectStatus" list="prospectStatusList" value="${p.status || ''}">
        <datalist id="prospectStatusList">
          ${statusOptions.map(s => html`<option value="${s}"></option>`)}
        </datalist>
        <div class="fs-xs a-soft mt-1">
          Een statuswijziging legt vast dat er vandaag contact was. Dat verzet de bewaartermijn van dit contact met twaalf maanden.
        </div>
      </div>
      <div class="form-group">
        <label class="form-label" for="prospectNotes">Notities</label>
        <textarea class="a-textarea" id="prospectNotes" rows="3">${p.intent_signal || ''}</textarea>
      </div>
      <div class="form-group">
        <label class="form-label" for="prospectSourceUrl">Bron-URL</label>
        <input type="text" class="form-control" id="prospectSourceUrl" value="${p.source_url || ''}">
        <div class="fs-xs text-danger-ink mt-1" id="prospectSourceUrlError" style="display:none;">Vul een publieke http- of https-URL in</div>
      </div>
      <div class="form-group">
        <div class="fs-xs a-soft mb-1">Zonder vastgelegde grondslag mag er geen outreach naar dit contact (Telecommunicatiewet art. 11.7).</div>
        <label class="form-label" for="prospectLawfulBasis">Grondslag</label>
        <select class="form-select" id="prospectLawfulBasis">
          ${lawfulBases.map(v => html`<option value="${v}" ${raw(v === p.lawful_basis ? 'selected' : '')}>${AdminLabels.label('grondslag', v, v)}</option>`)}
        </select>
      </div>
      <div class="a-actions">
        <button class="btn btn-primary" data-action="save-prospect" data-id="${prospectId}">Opslaan</button>
        <button class="btn btn-ghost-secondary" data-action="close-modal">Annuleren</button>
      </div>
    `, { title: 'Prospect bewerken: ' + (p.company_name || '') });
  },

  // §7.3.6(c): alleen gewijzigde velden gaan mee (de backend doet
  // exclude_none=True en geeft 400 "No fields to update" bij een leeg
  // formulier -- een all-empty submit gebeurt hier al niet doordat er
  // altijd minstens de bestaande waarden in de velden staan, maar de diff
  // hieronder stuurt zelfs een ongewijzigd veld niet opnieuw mee).
  async saveProspect(prospectId) {
    const p = (this._data.prospects || []).find(x => x.id === prospectId);
    if (!p) return;
    this.prospectFormAlert('');

    const statusVal = document.getElementById('prospectStatus')?.value?.trim() || '';
    const notesVal = document.getElementById('prospectNotes')?.value?.trim() || '';
    const sourceUrlVal = document.getElementById('prospectSourceUrl')?.value?.trim() || '';
    const lawfulBasisVal = document.getElementById('prospectLawfulBasis')?.value || '';

    // Client-side, dezelfde eis als de backend (routers/prospects.py
    // ProspectUpdate._source_url_http_only): http:// of https:// verplicht
    // zodra het veld iets bevat.
    if (sourceUrlVal && !/^https?:\/\//i.test(sourceUrlVal)) {
      const err = document.getElementById('prospectSourceUrlError');
      if (err) err.style.display = '';
      return;
    }
    const err = document.getElementById('prospectSourceUrlError');
    if (err) err.style.display = 'none';

    // lawful_basis heeft geen lege optie in de select, dus dit blokkeert
    // alleen een select die op geen enkele manier tot stand kon komen --
    // vangnet, geen verwachte route.
    if (!lawfulBasisVal) {
      this.prospectFormAlert('Kies een grondslag.');
      return;
    }

    const payload = {};
    if (statusVal !== (p.status || '')) payload.status = statusVal;
    if (notesVal !== (p.intent_signal || '')) payload.notes = notesVal;
    if (sourceUrlVal !== (p.source_url || '')) payload.source_url = sourceUrlVal;
    if (lawfulBasisVal !== (p.lawful_basis || '')) payload.lawful_basis = lawfulBasisVal;

    if (!Object.keys(payload).length) { this.closeModal(); return; }

    try {
      const res = await Auth.fetch(`/v1/admin/prospects/${prospectId}`, {
        method: 'PUT', body: JSON.stringify(payload),
      });
      const data = await res?.json().catch(() => null);
      if (res?.ok) {
        Auth.toast('Prospect bijgewerkt', 'success');
        this.closeModal();
        await this.loadProspects();
      } else {
        this.prospectFormAlert(this.errorDetail(data).message || 'Opslaan mislukt, probeer het opnieuw.');
      }
    } catch {
      this.prospectFormAlert('Netwerkfout, probeer het opnieuw.');
    }
  },

  prospectFormAlert(text) {
    const el = document.getElementById('prospectFormAlert');
    if (!el) return;
    if (!text) { mount(el, ''); return; }
    mount(el, html`
      <div class="alert alert-danger" role="alert">
        <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
        <span>${text}</span>
      </div>`);
  },
  });

  Admin.registerSection({
    id: 'leads',
    title: 'Leads',
    loader: () => { Admin.loadLeads(); Admin.loadProspects(); },
    filters: [
      { selector: '#leadTypeFilter', event: 'change',
        handler(el) {
          Admin._currentPage.leads = 1;
          Admin.loadLeads({
            type: el.value || undefined,
            unread: document.getElementById('leadUnreadFilter')?.checked || undefined,
          });
        } },
      { selector: '#leadUnreadFilter', event: 'change',
        handler(el) {
          Admin._currentPage.leads = 1;
          Admin.loadLeads({
            type: document.getElementById('leadTypeFilter')?.value || undefined,
            unread: el.checked || undefined,
          });
        } },
    ],
    actions: {
      'view-lead': (el) => Admin.viewLeadDetail(el.dataset.source, Number(el.dataset.id)),
      'toggle-lead-read': (el) => Admin.toggleLeadRead(el.dataset.source, Number(el.dataset.id), el.dataset.read === '1'),
      'edit-prospect': (el) => Admin.openEditProspectModal(Number(el.dataset.id)),
      'save-prospect': (el) => Admin.saveProspect(Number(el.dataset.id)),
    },
  });
})();
