/* ============================================================
   GSP Recruitment — admin/js/sections/jobs.js
   Vacatures over alle opdrachtgevers heen, plus de modal Nieuwe vacature.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern) en voor nav.js, dat de registry uitleest. Geen ES-module: de
   rest van de site gebruikt die ook niet.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  Object.assign(Admin, {
  /* ============================================================
     JOBS
     ============================================================ */
  async loadJobs(params = {}) {
    this._lastParams.jobs = params;
    const qs = new URLSearchParams();
    const limit = this._pageSize;
    const offset = ((this._currentPage.jobs || 1) - 1) * limit;
    if (params.status) qs.set('status', params.status);
    if (params.search) qs.set('search', params.search);
    qs.set('limit', limit);
    qs.set('offset', offset);

    this.setLoading('#section-jobs table tbody', 5);
    try {
      const res = await Auth.fetch(`/v1/admin/jobs?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.jobs = data;
      this.renderJobs(data);
      this.renderPagination('jobsPagination', data.total, limit, this._currentPage.jobs, 'jobs');
    } catch (err) {
      this.setEmpty('#section-jobs table tbody', 5, 'Failed to load jobs');
    }
  },

  renderJobs(data) {
    const tbody = document.querySelector('#section-jobs table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#section-jobs table tbody', 5, 'Nog geen vacatures. Vacatures die klanten aanleveren verschijnen hier voor goedkeuring.'); return; }
    mount(tbody, html`${items.map(j => html`
      <tr>
        <td class="a-cell-name">${j.title || 'Untitled'}</td>
        <td class="a-soft">${j.company_name || '—'}</td>
        <td class="text-center">${j.application_count ?? '—'}</td>
        <td><span class="${this.badge(j.status)}">${j.status || 'draft'}</span></td>
        <td>
          ${(j.status === 'draft' || j.status === 'pending') ? html`
            <button class="btn btn-sm btn-primary" data-action="set-job-status" data-id="${j.id}" data-status="open" title="Approve">
              <i class="fa-regular fa-circle-check"></i> Approve
            </button>` : ''}
          ${j.status === 'open' ? html`
            <button class="btn btn-sm btn-ghost-secondary a-danger" data-action="set-job-status" data-id="${j.id}" data-status="closed" title="Close">
              <i class="fa-solid fa-xmark"></i> Close
            </button>` : ''}
          <button class="btn btn-sm btn-ghost-secondary a-danger" data-action="confirm-delete-job" data-id="${j.id}" title="Delete">
            <i class="fa-solid fa-trash"></i>
          </button>
        </td>
      </tr>`)}`);
  },

  async setJobStatus(jobId, status) {
    try {
      const res = await Auth.fetch(`/v1/admin/jobs/${jobId}`, {
        method: 'PUT', body: JSON.stringify({ status }),
      });
      if (res?.ok) {
        Auth.toast(`Job ${status === 'open' ? 'approved' : 'closed'}`, 'success');
        await this.loadJobs(this._lastParams.jobs || {});
      } else {
        const d = await res?.json();
        Auth.toast(d?.detail || 'Update failed', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
  },

  confirmDeleteJob(jobId) {
    if (!confirm('Delete this job? This action cannot be undone.')) return;
    this.deleteJob(jobId);
  },

  async deleteJob(jobId) {
    try {
      const res = await Auth.fetch(`/v1/admin/jobs/${jobId}`, { method: 'DELETE' });
      // Only a real 2xx counts as success -- a 404 (job already gone, or
      // never existed) is an error the operator needs to see, not a
      // silent success (this used to also accept status===404 as OK).
      if (res?.ok) {
        Auth.toast('Job deleted', 'success');
        await this.loadJobs(this._lastParams.jobs || {});
      } else {
        const d = await res?.json().catch(() => null);
        Auth.toast(d?.detail || 'Delete failed', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
  },

  /* ---- "Nieuwe vacature" (WS-B.2) ----
     Lets an admin record a job on a client's behalf -- e.g. a telephone
     assignment -- without the client needing a portal login. The client
     picker reads GET /v1/admin/clients (routers/clients_admin.py) --
     every client row, one call, not scoped to accounts with a portal
     login the way /users?role=client was. Cached in
     this._data.clientOptions so reopening the modal doesn't re-fetch. */
  async fetchClientOptions(force = false) {
    if (!force && this._data.clientOptions) return this._data.clientOptions;
    try {
      const res = await Auth.fetch('/v1/admin/clients?limit=200');
      if (!res?.ok) return this._data.clientOptions || [];
      const data = await res.json();
      this._data.clientOptions = (data.items || []).map(c => ({ id: c.id, company_name: c.company_name || 'Onbekend', is_internal: !!c.is_internal }));
    } catch {
      this._data.clientOptions = this._data.clientOptions || [];
    }
    return this._data.clientOptions;
  },

  async openNewJobModal() {
    const clients = await this.fetchClientOptions();
    this.openModal('newJobModal', html`
      ${!clients.length ? html`
        <div class="alert alert-warning" role="alert">Nog geen opdrachtgevers met een portal-account gevonden.</div>
      ` : ''}
      <div class="form-group">
        <label>Opdrachtgever</label>
        <select id="newJobClient" ${raw(!clients.length ? 'disabled' : '')}>
          ${clients.map(c => html`<option value="${c.id}">${c.company_name}${c.is_internal ? ' (intern)' : ''}</option>`)}
        </select>
      </div>
      <div class="form-group">
        <label>Functietitel</label>
        <input type="text" id="newJobTitle" placeholder="Bijv. Embedded software engineer">
      </div>
      <div class="form-group">
        <label>Afdeling</label>
        <input type="text" id="newJobDepartment">
      </div>
      <div class="form-group">
        <label>Senioriteit</label>
        <input type="text" id="newJobSeniority" placeholder="Bijv. medior">
      </div>
      <div class="form-group">
        <label>Standplaats</label>
        <input type="text" id="newJobCity">
      </div>
      <div class="form-group">
        <label>Dienstverband</label>
        <select id="newJobEmploymentType">
          <option value="">— Kies —</option>
          <option value="vast">Vast (werving en selectie)</option>
          <option value="detachering">Detachering</option>
          <option value="interim">Interim</option>
        </select>
      </div>
      <div class="d-flex gap-3">
        <div class="form-group flex-fill">
          <label>Salaris min (EUR/mnd)</label>
          <input type="number" id="newJobSalaryMin">
        </div>
        <div class="form-group flex-fill">
          <label>Salaris max (EUR/mnd)</label>
          <input type="number" id="newJobSalaryMax">
        </div>
      </div>
      <div class="form-group">
        <label>Omschrijving</label>
        <textarea id="newJobDescription" rows="4" class="a-textarea"></textarea>
      </div>
      <div class="form-group">
        <label>Eisen</label>
        <textarea id="newJobRequirements" rows="3" class="a-textarea"></textarea>
      </div>
      <div class="form-group">
        <label class="d-flex align-items-center gap-2 fw-normal">
          <input type="checkbox" id="newJobSponsorship"> Sponsoring kennismigrant mogelijk
        </label>
      </div>
      <div class="a-actions">
        <button class="btn btn-primary" data-action="save-new-job" ${raw(!clients.length ? 'disabled' : '')}>Vacature aanmaken</button>
        <button class="btn btn-ghost-secondary" data-action="close-modal">Annuleren</button>
      </div>
    `, { title: 'Nieuwe vacature' });
  },

  async saveNewJob() {
    const clientId = Number(document.getElementById('newJobClient')?.value);
    const title = document.getElementById('newJobTitle')?.value?.trim();
    if (!clientId) { Auth.toast('Kies een opdrachtgever', 'error'); return; }
    if (!title) { Auth.toast('Functietitel is verplicht', 'error'); return; }

    const salaryMin = document.getElementById('newJobSalaryMin')?.value;
    const salaryMax = document.getElementById('newJobSalaryMax')?.value;
    const employmentType = document.getElementById('newJobEmploymentType')?.value;

    const payload = {
      client_id: clientId,
      title,
      department: document.getElementById('newJobDepartment')?.value?.trim() || null,
      seniority: document.getElementById('newJobSeniority')?.value?.trim() || null,
      city: document.getElementById('newJobCity')?.value?.trim() || null,
      employment_type: employmentType || null,
      salary_min: salaryMin ? Number(salaryMin) : null,
      salary_max: salaryMax ? Number(salaryMax) : null,
      description: document.getElementById('newJobDescription')?.value?.trim() || null,
      requirements: document.getElementById('newJobRequirements')?.value?.trim() || null,
      sponsorship_possible: !!document.getElementById('newJobSponsorship')?.checked,
    };

    try {
      const res = await Auth.fetch('/v1/admin/jobs', { method: 'POST', body: JSON.stringify(payload) });
      if (res?.ok) {
        Auth.toast('Vacature aangemaakt', 'success');
        this.closeModal();
        this._currentPage.jobs = 1;
        await this.loadJobs(this._lastParams.jobs || {});
      } else {
        const d = await res?.json().catch(() => null);
        Auth.toast(d?.detail || 'Aanmaken mislukt', 'error');
      }
    } catch { Auth.toast('Netwerkfout', 'error'); }
  },
  });

  Admin.registerSection({
    id: 'jobs',
    title: 'All Jobs',
    loader: () => Admin.loadJobs(),
    filters: [
      { selector: '#jobStatusFilter', event: 'change',
        handler(el) {
          const v = el.value;
          Admin._currentPage.jobs = 1;
          Admin.loadJobs({
            status: ['open', 'closed', 'draft'].includes(v) ? v : '',
            search: document.getElementById('jobSearch')?.value?.trim() || undefined,
          });
        } },
      // Zoeken gaat server-side (WS-B.2); #jobSearch was daarvoor inert.
      { selector: '#jobSearch', event: 'input', debounce: 400,
        handler(el) {
          Admin._currentPage.jobs = 1;
          Admin.loadJobs({
            status: document.getElementById('jobStatusFilter')?.value || undefined,
            search: el.value || undefined,
          });
        } },
    ],
    actions: {
      'set-job-status': (el) => Admin.setJobStatus(Number(el.dataset.id), el.dataset.status),
      'confirm-delete-job': (el) => Admin.confirmDeleteJob(Number(el.dataset.id)),
      'open-new-job-modal': () => Admin.openNewJobModal(),
      'save-new-job': () => Admin.saveNewJob(),
    },
  });
})();
