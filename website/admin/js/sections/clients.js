/* ============================================================
   GSP Recruitment — admin/js/sections/clients.js
   Opdrachtgevers: lijst en het detailpaneel met zes tabbladen (de tab
   Pipeline kwam er met §7.3.4 bij, op dezelfde gedeelde
   Admin.loadPipelineTab() als de kandidaatdrawer in candidates.js).

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern) en voor nav.js, dat de registry uitleest. Geen ES-module: de
   rest van de site gebruikt die ook niet.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  Object.assign(Admin, {
  /* ============================================================
     OPDRACHTGEVERS (WS-B.5 / WS-B.2 follow-up)

     GET /v1/admin/clients (routers/clients_admin.py) returns
     company_name/domain/erkend_referent/open_job_count/primary_contact
     for the whole page in one query (LEFT JOIN LATERAL, no N+1) -- this
     used to derive the roster from /users?role=client plus one detail
     fetch per row plus one open-jobs-count fetch per row; both are gone.
     ============================================================ */
  async loadClients(params = {}) {
    this._lastParams.clients = params;
    const qs = new URLSearchParams();
    if (params.search) qs.set('search', params.search);
    qs.set('limit', 200);

    this.setLoading('#section-clients table tbody', 6);
    try {
      const res = await Auth.fetch(`/v1/admin/clients?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.clients = data.items || [];
      this.renderClients(this._data.clients);
    } catch (err) {
      this.setLoadError('#section-clients table tbody', 6, () => this.loadClients(params));
    }
  },

  erkendReferentBadgeClass(value) {
    if (value === 'ja') return 'badge bg-green-lt';
    if (value === 'nee') return 'badge bg-red-lt';
    return 'badge bg-secondary-lt';
  },

  renderClients(clients) {
    const tbody = document.querySelector('#section-clients table tbody');
    if (!tbody) return;
    if (!clients.length) { this.setEmpty('#section-clients table tbody', 6, 'Nog geen opdrachtgevers met een portal-account.'); return; }
    mount(tbody, html`${clients.map(c => html`
      <tr data-action="open-client" data-id="${c.id}" class="a-clickable">
        <td class="a-cell-name">${c.company_name || 'Onbekend'}</td>
        <td class="a-soft">${c.domain || '—'}</td>
        <td class="text-center">${c.open_job_count ?? 0}</td>
        <td class="a-soft">${c.primary_contact?.full_name || c.primary_contact?.email || '—'}</td>
        <td><span class="${this.erkendReferentBadgeClass(c.erkend_referent)}">${this.erkendReferentLabel(c.erkend_referent)}</span></td>
        <td class="text-end"><i class="fa-solid fa-chevron-right text-secondary"></i></td>
      </tr>`)}`);
  },

  // De zes tabbladen van het detailpaneel. Sinds WS5 stap 3 is dit een
  // ui.drawer (Bootstrap Offcanvas) met ui.tabs in plaats van een brede
  // modal met een handgerolde tabstrip: de tabstrip krijgt daarmee
  // role="tablist" en aria-selected, en het paneel schuift in vanaf rechts
  // zoals een detailpaneel hoort. Het DOM-anker #clientDrawerTabContent
  // blijft hetzelfde, zodat elke tabloader ongewijzigd bleef.
  _clientTabs: [
    { key: 'info', label: 'Info' },
    { key: 'contacts', label: 'Contacten' },
    { key: 'jobs', label: 'Vacatures' },
    { key: 'pipeline', label: 'Pipeline' },
    { key: 'activity', label: 'Notities/Activiteit' },
    { key: 'prospects', label: 'Prospects' },
  ],

  openClientDrawer(clientId) {
    const client = (this._data.clients || []).find(c => c.id === clientId);
    this._clientDrawer = ui.drawer({
      id: 'clientDrawer',
      title: client?.company_name || 'Opdrachtgever',
      tabs: this._clientTabs,
      tabAction: 'client-tab',
      activeTab: 'info',
      dataset: { clientId },
      subtitle: client?.domain || '—',
      body: html`<div id="clientDrawerTabContent" class="a-tabpane"><i class="fa-solid fa-spinner fa-spin"></i></div>`,
      onClose: () => { this._clientDrawer = null; },
    });
    this.switchClientTab(clientId, 'info');
  },

  switchClientTab(clientId, tab) {
    if (this._clientDrawer) this._clientDrawer.selectTab(tab);
    const loaders = {
      info: () => this.loadClientInfoTab(clientId),
      contacts: () => this.loadClientContacts(clientId),
      jobs: () => this.loadClientJobsTab(clientId),
      pipeline: () => this.loadClientPipelineTab(clientId),
      activity: () => this.loadClientActivityTab(clientId),
      prospects: () => this.loadClientProspectsTab(clientId),
    };
    (loaders[tab] || loaders.info)();
  },

  /* ---- Info tab: erkend_referent + notes, PATCH /v1/admin/clients/{id} ---- */
  async loadClientInfoTab(clientId) {
    const el = document.getElementById('clientDrawerTabContent');
    if (!el) return;
    mount(el, html`<i class="fa-solid fa-spinner fa-spin"></i>`);
    try {
      const res = await Auth.fetch(`/v1/admin/clients/${clientId}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.clientDetail = this._data.clientDetail || {};
      this._data.clientDetail[clientId] = data;
      this.renderClientInfoTab(clientId);
    } catch {
      this.setContainerLoadError(el, () => this.loadClientInfoTab(clientId));
    }
  },

  renderClientInfoTab(clientId) {
    const el = document.getElementById('clientDrawerTabContent');
    if (!el) return;
    const client = (this._data.clientDetail && this._data.clientDetail[clientId]) || {};
    mount(el, html`
      <div class="form-group">
        <label>Erkend referent (IND)</label>
        <select id="clientInfoErkendReferent">
          <option value="onbekend" ${raw(client.erkend_referent === 'onbekend' || !client.erkend_referent ? 'selected' : '')}>Onbekend</option>
          <option value="ja" ${raw(client.erkend_referent === 'ja' ? 'selected' : '')}>Ja</option>
          <option value="nee" ${raw(client.erkend_referent === 'nee' ? 'selected' : '')}>Nee</option>
        </select>
      </div>
      <div class="form-group">
        <label>Notities</label>
        <textarea id="clientInfoNotes" rows="5" class="a-textarea">${client.notes || ''}</textarea>
      </div>
      <div class="a-actions">
        <button class="btn btn-primary" data-action="save-client-info" data-client-id="${clientId}">Opslaan</button>
      </div>
    `);
  },

  async saveClientInfo(clientId) {
    const payload = {
      erkend_referent: document.getElementById('clientInfoErkendReferent')?.value || 'onbekend',
      notes: document.getElementById('clientInfoNotes')?.value ?? '',
    };
    try {
      const res = await Auth.fetch(`/v1/admin/clients/${clientId}`, {
        method: 'PATCH', body: JSON.stringify(payload),
      });
      if (res?.ok) {
        Auth.toast('Opgeslagen', 'success');
        const updated = await res.json();
        this._data.clientDetail = this._data.clientDetail || {};
        this._data.clientDetail[clientId] = { ...(this._data.clientDetail[clientId] || {}), ...updated };
        // Keep the roster's badge in sync without a full reload.
        const rosterRow = (this._data.clients || []).find(c => c.id === clientId);
        if (rosterRow) {
          rosterRow.erkend_referent = updated.erkend_referent;
          this.renderClients(this._data.clients);
        }
      } else {
        const d = await res?.json().catch(() => null);
        Auth.toast(d?.detail || 'Opslaan mislukt', 'error');
      }
    } catch { Auth.toast('Netwerkfout', 'error'); }
  },

  /* ---- Contacts tab (WS-C.4 CRUD) ---- */
  async loadClientContacts(clientId) {
    const el = document.getElementById('clientDrawerTabContent');
    if (!el) return;
    mount(el, html`<i class="fa-solid fa-spinner fa-spin"></i>`);
    try {
      const res = await Auth.fetch(`/v1/admin/clients/${clientId}/contacts`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.clientContacts = this._data.clientContacts || {};
      this._data.clientContacts[clientId] = data.items || [];
      this.renderClientContacts(clientId);
    } catch {
      this.setContainerLoadError(el, () => this.loadClientContacts(clientId));
    }
  },

  renderClientContacts(clientId) {
    const el = document.getElementById('clientDrawerTabContent');
    if (!el) return;
    const items = (this._data.clientContacts && this._data.clientContacts[clientId]) || [];
    mount(el, html`
      <div class="d-flex justify-content-end mb-3">
        <button class="btn btn-sm btn-primary" data-action="client-contact-new" data-client-id="${clientId}">
          <i class="fa-solid fa-plus"></i> Nieuw contact
        </button>
      </div>
      <div id="clientContactForm"></div>
      ${items.length ? html`
        <div class="table-responsive">
          <table class="table table-vcenter card-table">
            <thead><tr><th>Naam</th><th>Rol</th><th>E-mail</th><th>Telefoon</th><th>Primair</th><th style="width:110px;">Acties</th></tr></thead>
            <tbody>${items.map(c => html`
              <tr>
                <td class="a-cell-strong">${c.full_name}</td>
                <td>${this.roleLabel(c.role)}</td>
                <td class="a-soft">${c.email || '—'}</td>
                <td class="a-soft">${c.phone || '—'}</td>
                <td>${c.is_primary ? html`<span class="badge bg-yellow-lt">Primair</span>` : html`
                  <button class="btn btn-sm btn-ghost-secondary" data-action="client-contact-make-primary" data-client-id="${clientId}" data-id="${c.id}">Maak primair</button>`}</td>
                <td>
                  <button class="btn btn-sm btn-ghost-secondary" data-action="client-contact-edit" data-client-id="${clientId}" data-id="${c.id}" title="Bewerken"><i class="fa-solid fa-pen"></i></button>
                  <button class="btn btn-sm btn-ghost-secondary text-danger-ink" data-action="client-contact-delete" data-client-id="${clientId}" data-id="${c.id}" title="Verwijderen"><i class="fa-solid fa-trash"></i></button>
                </td>
              </tr>`)}</tbody>
          </table>
        </div>` : html`<div class="a-state-block">Nog geen contacten voor deze opdrachtgever.</div>`}
    `);
  },

  openClientContactForm(clientId, contactId) {
    const contact = contactId
      ? ((this._data.clientContacts?.[clientId] || []).find(c => c.id === contactId))
      : null;
    const formEl = document.getElementById('clientContactForm');
    if (!formEl) return;
    mount(formEl, html`
      <div class="a-panel">
        <h4 class="a-cell-strong mb-3">${contact ? 'Contact bewerken' : 'Nieuw contact'}</h4>
        <div class="form-group"><label>Naam</label><input type="text" id="ccFullName" value="${contact?.full_name || ''}"></div>
        <div class="form-group"><label>E-mail</label><input type="email" id="ccEmail" value="${contact?.email || ''}"></div>
        <div class="form-group"><label>Telefoon</label><input type="text" id="ccPhone" value="${contact?.phone || ''}"></div>
        <div class="form-group">
          <label>Rol</label>
          <select id="ccRole">
            <option value="">—</option>
            ${['hiring_manager', 'finance', 'tekenbevoegd', 'overig'].map(r => html`
              <option value="${r}" ${raw(contact?.role === r ? 'selected' : '')}>${this.roleLabel(r)}</option>`)}
          </select>
        </div>
        <div class="form-group">
          <label><input type="checkbox" id="ccPrimary" ${raw(contact?.is_primary ? 'checked' : '')}> Primair contact</label>
        </div>
        <div class="d-flex gap-3 mt-3">
          <button class="btn btn-primary btn-sm" data-action="client-contact-save" data-client-id="${clientId}" data-id="${contactId || ''}">Opslaan</button>
          <button class="btn btn-ghost-secondary btn-sm" data-action="client-contact-cancel" data-client-id="${clientId}">Annuleren</button>
        </div>
      </div>
    `);
  },

  async saveClientContact(clientId, contactId) {
    const payload = {
      full_name: document.getElementById('ccFullName')?.value?.trim(),
      email: document.getElementById('ccEmail')?.value?.trim() || null,
      phone: document.getElementById('ccPhone')?.value?.trim() || null,
      role: document.getElementById('ccRole')?.value || null,
      is_primary: !!document.getElementById('ccPrimary')?.checked,
    };
    if (!payload.full_name) { Auth.toast('Naam is verplicht', 'error'); return; }
    try {
      const res = contactId
        ? await Auth.fetch(`/v1/admin/clients/${clientId}/contacts/${contactId}`, { method: 'PUT', body: JSON.stringify(payload) })
        : await Auth.fetch(`/v1/admin/clients/${clientId}/contacts`, { method: 'POST', body: JSON.stringify({ ...payload, lawful_basis: 'zakelijk_functioneel_adres' }) });
      if (res?.ok) {
        Auth.toast(contactId ? 'Contact bijgewerkt' : 'Contact toegevoegd', 'success');
        document.getElementById('clientContactForm') && mount(document.getElementById('clientContactForm'), '');
        await this.loadClientContacts(clientId);
      } else {
        const d = await res?.json().catch(() => null);
        Auth.toast(d?.detail || 'Opslaan mislukt', 'error');
      }
    } catch { Auth.toast('Netwerkfout', 'error'); }
  },

  async makeClientContactPrimary(clientId, contactId) {
    try {
      const res = await Auth.fetch(`/v1/admin/clients/${clientId}/contacts/${contactId}`, {
        method: 'PUT', body: JSON.stringify({ is_primary: true }),
      });
      if (res?.ok) { await this.loadClientContacts(clientId); }
      else { Auth.toast('Bijwerken mislukt', 'error'); }
    } catch { Auth.toast('Netwerkfout', 'error'); }
  },

  async deleteClientContact(clientId, contactId) {
    if (!confirm('Dit contact verwijderen?')) return;
    try {
      const res = await Auth.fetch(`/v1/admin/clients/${clientId}/contacts/${contactId}`, { method: 'DELETE' });
      if (res?.ok || res?.status === 204) {
        Auth.toast('Contact verwijderd', 'success');
        await this.loadClientContacts(clientId);
      } else { Auth.toast('Verwijderen mislukt', 'error'); }
    } catch { Auth.toast('Netwerkfout', 'error'); }
  },

  /* ---- Jobs tab (read-only, existing jobs endpoint filtered by client) ---- */
  async loadClientJobsTab(clientId) {
    const el = document.getElementById('clientDrawerTabContent');
    if (!el) return;
    mount(el, html`<i class="fa-solid fa-spinner fa-spin"></i>`);
    try {
      const res = await Auth.fetch(`/v1/admin/jobs?client_id=${clientId}&limit=50`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      const items = data.items || [];
      mount(el, items.length ? html`
        <div class="table-responsive">
          <table class="table table-vcenter card-table">
            <thead><tr><th>Titel</th><th>Type</th><th>Status</th><th>Sollicitaties</th></tr></thead>
            <tbody>${items.map(j => html`
              <tr>
                <td class="a-cell-strong">${j.title || 'Untitled'}</td>
                <td class="a-soft">${j.employment_type ? this.dienstlijnLabel(j.employment_type) : '—'}</td>
                <td><span class="${this.badge(j.status)}">${j.status || 'draft'}</span></td>
                <td class="text-center">${j.application_count ?? '—'}</td>
              </tr>`)}</tbody>
          </table>
        </div>` : html`<div class="a-state-block">Nog geen vacatures voor deze opdrachtgever.</div>`);
    } catch {
      this.setContainerLoadError(el, () => this.loadClientJobsTab(clientId));
    }
  },

  /* ---- Pipeline tab (§7.3.4): GET /admin/pipeline?client_id=, dezelfde
     tab-inhoud als de kandidaatdrawer (Admin.loadPipelineTab(), admin.js),
     met showCandidateName aan -- één client_id kan meerdere kandidaten
     dekken (elk over een eigen vacature), dus de kaart moet er hier bij
     zeggen om wie het gaat; de kandidaatdrawer laat dat weg omdat daar
     al maar één kandidaat in beeld is. ---- */
  loadClientPipelineTab(clientId) {
    this.loadPipelineTab('clientDrawerTabContent', 'client_id', clientId, { showCandidateName: true });
  },

  /* ---- Notities/Activiteit tab (WS-C.6) --
     GET /v1/admin/activities?subject_type=client&subject_id=.. landed on
     main after this feature was first built (migrations/028_activities.py,
     routers/activities.py) -- read-only here, matching the task spec. */
  async loadClientActivityTab(clientId) {
    const el = document.getElementById('clientDrawerTabContent');
    if (!el) return;
    mount(el, html`<i class="fa-solid fa-spinner fa-spin"></i>`);
    try {
      const res = await Auth.fetch(`/v1/admin/activities?subject_type=client&subject_id=${clientId}&limit=50`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      const items = data.items || [];
      mount(el, items.length ? html`
        <div class="table-responsive">
          <table class="table table-vcenter card-table">
            <thead><tr><th>Type</th><th>Notitie</th><th>Datum</th><th>Status</th></tr></thead>
            <tbody>${items.map(a => html`
              <tr>
                <td class="a-cell-strong">${this.activityTypeLabel(a.type)}</td>
                <td class="a-soft">${a.body || '—'}</td>
                <td class="a-soft">${this.formatDate(a.created_at)}</td>
                <td>${a.completed_at ? html`<span class="badge bg-secondary-lt">Afgerond</span>` : (a.due_at ? html`<span class="badge bg-blue-lt">Open</span>` : '—')}</td>
              </tr>`)}</tbody>
          </table>
        </div>` : html`<div class="a-state-block">Nog geen notities of activiteit voor deze opdrachtgever.</div>`);
    } catch {
      this.setContainerLoadError(el, () => this.loadClientActivityTab(clientId));
    }
  },

  /* ---- Prospects tab (existing global prospects router, best-effort
     matched to this client by company name -- client_prospects has no
     client_id FK to `clients`, so this is a name search, not a join). ---- */
  async loadClientProspectsTab(clientId) {
    const el = document.getElementById('clientDrawerTabContent');
    if (!el) return;
    mount(el, html`<i class="fa-solid fa-spinner fa-spin"></i>`);
    const client = (this._data.clients || []).find(c => c.id === clientId);
    const search = client?.company_name || '';
    try {
      const qs = new URLSearchParams({ limit: '50' });
      if (search) qs.set('search', search);
      const res = await Auth.fetch(`/v1/admin/prospects?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      const items = data.items || [];
      mount(el, html`
        <div class="a-meta mb-2">
          Gematcht op bedrijfsnaam (geen directe koppeling in de database).
        </div>
        ${items.length ? html`
          <div class="table-responsive">
            <table class="table table-vcenter card-table">
              <thead><tr><th>Bedrijf</th><th>Contact</th><th>Functie</th><th>Status</th></tr></thead>
              <tbody>${items.map(p => html`
                <tr>
                  <td class="a-cell-strong">${p.company_name || '—'}</td>
                  <td class="a-soft">${p.contact_name || '—'}</td>
                  <td class="a-soft">${p.contact_title || '—'}</td>
                  <td><span class="${this.badge(p.status)}">${p.status || '—'}</span></td>
                </tr>`)}</tbody>
            </table>
          </div>` : html`<div class="a-state-block">Geen prospects gevonden voor deze bedrijfsnaam.</div>`}
      `);
    } catch {
      this.setContainerLoadError(el, () => this.loadClientProspectsTab(clientId));
    }
  },
  });

  Admin.registerSection({
    id: 'clients',
    title: 'Opdrachtgevers',
    loader: () => Admin.loadClients(),
    filters: [],
    actions: {
      'open-client': (el) => Admin.openClientDrawer(Number(el.dataset.id)),
      'client-tab': (el) => Admin.switchClientTab(Number(el.dataset.clientId), el.dataset.tab),
      'save-client-info': (el) => Admin.saveClientInfo(Number(el.dataset.clientId)),
      'client-contact-new': (el) => Admin.openClientContactForm(Number(el.dataset.clientId), null),
      'client-contact-edit': (el) => Admin.openClientContactForm(Number(el.dataset.clientId), Number(el.dataset.id)),
      'client-contact-cancel': () => { const f = document.getElementById('clientContactForm'); if (f) mount(f, ''); },
      'client-contact-save': (el) => Admin.saveClientContact(Number(el.dataset.clientId), el.dataset.id ? Number(el.dataset.id) : null),
      'client-contact-make-primary': (el) => Admin.makeClientContactPrimary(Number(el.dataset.clientId), Number(el.dataset.id)),
      'client-contact-delete': (el) => Admin.deleteClientContact(Number(el.dataset.clientId), Number(el.dataset.id)),
    },
  });
})();
