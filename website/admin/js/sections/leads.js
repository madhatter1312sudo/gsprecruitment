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

    this.setLoading('#section-leads table tbody', 7);
    try {
      const res = await Auth.fetch(`/v1/admin/leads?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.leads = data;
      this.renderLeads(data);
      this.renderPagination('leadsPagination', data.total, limit, this._currentPage.leads, 'leads');
    } catch {
      this.setLoadError('#section-leads table tbody', 7, () => this.loadLeads(params));
    }
  },

  leadInterestLabel(type) {
    const map = {
      werving_selectie: 'Werving & selectie', detachering_internationaal: 'Detachering (internationaal)',
      kandidaat: 'Kandidaat', overig: 'Overig',
    };
    return map[type] || '—';
  },

  // Dienstlijn label for a job's raw `employment_type` value -- used by the
  // client drawer's Vacatures tab and the Rapportage breakdown so a raw
  // enum string (or an unrecognised one) never renders straight into the
  // UI. Unknown values fall back to the raw value itself (still escaped by
  // html``, never raw()) rather than a silent "—", so a value this map
  // hasn't caught up with is still visible instead of hidden.
  dienstlijnLabel(type) {
    const map = {
      vast: 'Vast (werving en selectie)',
      detachering: 'Detachering',
      interim: 'Interim',
      werving_selectie: 'Werving en selectie',
      detachering_internationaal: 'Detachering (internationaal)',
    };
    return map[type] || type || 'onbekend';
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
    const tbody = document.querySelector('#section-leads table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#section-leads table tbody', 7, 'Geen leads gevonden voor deze filters.'); return; }
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
          <h3 class="a-modal__title">Kon lead niet laden</h3>
          <p class="a-soft">${d?.detail || 'Er ging iets mis bij het ophalen van deze lead.'}</p>
          <div class="a-actions">
            <button class="btn btn-primary btn-sm" data-action="view-lead" data-source="${source}" data-id="${leadId}">Opnieuw proberen</button>
            <button class="btn btn-ghost-secondary btn-sm" data-action="close-modal">Sluiten</button>
          </div>`);
        return;
      }
      const detail = await res.json();
      this._data.leadDetail = detail;
      this.renderLeadDetailModal(detail);
    } catch {
      this.openModal('leadDetailModal', html`
        <h3 class="a-modal__title">Netwerkfout</h3>
        <p class="a-soft">Kon geen verbinding maken met de server.</p>
        <div class="a-actions">
          <button class="btn btn-primary btn-sm" data-action="view-lead" data-source="${source}" data-id="${leadId}">Opnieuw proberen</button>
          <button class="btn btn-ghost-secondary btn-sm" data-action="close-modal">Sluiten</button>
        </div>`);
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
      <h3 class="a-modal__title">${isQuiz ? 'Quiz-inzending' : (detail.name || 'Lead')}</h3>
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
      </div>`);
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
  });

  Admin.registerSection({
    id: 'leads',
    title: 'Leads',
    loader: () => Admin.loadLeads(),
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
    },
  });
})();
