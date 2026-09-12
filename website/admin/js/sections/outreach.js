/* ============================================================
   GSP Recruitment — admin/js/sections/outreach.js
   Outreach-concepten: beoordelen, opslaan, goedkeuren of afwijzen.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern) en voor nav.js, dat de registry uitleest. Geen ES-module: de
   rest van de site gebruikt die ook niet.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  Object.assign(Admin, {
  /* ============================================================
     OUTREACH
     ============================================================ */
  async loadOutreach(params = {}) {
    this._lastParams.outreach = params;
    const qs = new URLSearchParams();
    const limit = this._pageSize;
    const offset = ((this._currentPage.outreach || 1) - 1) * limit;
    const statusFilter = document.getElementById('outreachStatusFilter');
    const status = params.status !== undefined ? params.status : statusFilter?.value;
    if (status) qs.set('status', status);
    qs.set('limit', limit);
    qs.set('offset', offset);

    this.setLoading('#section-outreach table tbody', 8);
    try {
      const res = await Auth.fetch(`/v1/admin/outreach/drafts?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.outreach = data;
      this.renderOutreach(data);
      this.renderPagination('outreachPagination', data.total, limit, this._currentPage.outreach, 'outreach');
    } catch (err) {
      this.setEmpty('#section-outreach table tbody', 8, 'Failed to load outreach drafts');
      console.error(err);
    }
  },

  renderOutreach(data) {
    const tbody = document.querySelector('#section-outreach table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#section-outreach table tbody', 8, 'Nog geen outreach-concepten. Start een sourcing- of drafting-run hierboven om concepten te genereren.'); return; }
    mount(tbody, html`${items.map(d => html`
      <tr>
        <td class="a-meta">${d.target_name || d.target_email || '—'}</td>
        <td class="a-soft">${d.company || '—'}</td>
        <td class="a-cell-strong">${d.subject || '—'}</td>
        <td><span class="${this.badge(d.target_type)}">${d.target_type}</span></td>
        <td class="a-meta">${d.ai_model || '—'}</td>
        <td class="a-meta">${this.timeAgo(d.created_at)}</td>
        <td><span class="${this.badge(d.status)}">${d.status}</span></td>
        <td>
          <button class="btn btn-sm btn-ghost-secondary" data-action="open-draft-modal" data-id="${d.id}" title="Review">
            <i class="fa-regular fa-eye"></i>
          </button>
          ${d.status === 'draft' ? html`
            <button class="btn btn-sm btn-ghost-secondary text-success-ink" data-action="approve-draft" data-id="${d.id}" title="Approve &amp; send">
              <i class="fa-regular fa-paper-plane"></i>
            </button>
            <button class="btn btn-sm btn-ghost-secondary text-danger-ink" data-action="reject-draft" data-id="${d.id}" title="Reject">
              <i class="fa-solid fa-xmark"></i>
            </button>` : ''}
        </td>
      </tr>`)}`);
  },

  openDraftModal(id) {
    const d = (this._data.outreach?.items || []).find(x => x.id === id);
    if (!d) return;
    const editable = d.status === 'draft';
    this.openModal('outreachDraftModal', html`
      <div class="detail-grid">
        <div><div class="a-field-label">To</div><div>${d.target_name || '—'} &lt;${d.target_email || ''}&gt;</div></div>
        <div><div class="a-field-label">Company</div><div>${d.company || '—'}</div></div>
        <div><div class="a-field-label">Type</div><div><span class="${this.badge(d.target_type)}">${d.target_type}</span></div></div>
        <div><div class="a-field-label">Status</div><div><span class="${this.badge(d.status)}">${d.status}</span></div></div>
        <div><div class="a-field-label">Channel</div><div>${d.channel || '—'}</div></div>
        <div><div class="a-field-label">Language</div><div>${d.language || '—'}</div></div>
        <div><div class="a-field-label">AI Model</div><div>${d.ai_model || '—'}</div></div>
        <div><div class="a-field-label">Created</div><div>${this.formatDate(d.created_at)}</div></div>
      </div>
      <div class="form-group">
        <label>Subject</label>
        <input type="text" id="draftSubject" value="${d.subject || ''}" ${raw(editable ? '' : 'disabled')}>
      </div>
      <div class="form-group">
        <label>Body</label>
        <textarea id="draftBody" rows="10" class="a-textarea" ${raw(editable ? '' : 'disabled')}>${d.body || ''}</textarea>
      </div>
      <div class="a-actions">
        ${editable ? html`
          <button class="btn btn-ghost-secondary" data-action="save-draft" data-id="${d.id}"><i class="fa-regular fa-floppy-disk"></i> Save</button>
          <button class="btn btn-primary" data-action="approve-draft" data-id="${d.id}"><i class="fa-regular fa-paper-plane"></i> Approve &amp; Send</button>
          <button class="btn btn-ghost-secondary text-danger-ink" data-action="reject-draft" data-id="${d.id}"><i class="fa-solid fa-xmark"></i> Reject</button>` : ''}
        <button class="btn btn-ghost-secondary" data-action="close-modal">Close</button>
      </div>
    `, { title: 'Outreach Draft' });
  },

  async saveDraft(id) {
    const subject = document.getElementById('draftSubject')?.value;
    const body = document.getElementById('draftBody')?.value;
    try {
      const res = await Auth.fetch(`/v1/admin/outreach/drafts/${id}`, {
        method: 'PUT', body: JSON.stringify({ subject, body }),
      });
      if (res?.ok) {
        Auth.toast('Draft saved', 'success');
        this.closeModal();
        await this.loadOutreach();
      } else {
        const d = await res?.json();
        Auth.toast(d?.detail || 'Save failed', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
  },

  async approveDraft(id) {
    const d = (this._data.outreach?.items || []).find(x => x.id === id);
    const who = d?.target_email || 'this recipient';
    if (!confirm(`Send this email to ${who}?`)) return;
    try {
      const res = await Auth.fetch(`/v1/admin/outreach/drafts/${id}/approve`, { method: 'POST' });
      if (res?.ok) {
        Auth.toast('Email sent', 'success');
        this.closeModal();
        await this.loadOutreach();
      } else {
        const data = await res?.json();
        Auth.toast(data?.detail || 'Failed to send', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
  },

  async rejectDraft(id) {
    if (!confirm('Reject this draft?')) return;
    try {
      const res = await Auth.fetch(`/v1/admin/outreach/drafts/${id}/reject`, { method: 'POST' });
      if (res?.ok) {
        Auth.toast('Draft rejected', 'success');
        this.closeModal();
        await this.loadOutreach();
      } else {
        const data = await res?.json();
        Auth.toast(data?.detail || 'Reject failed', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
  },

  async runOutreachJob(name, btn) {
    if (btn) { btn.disabled = true; btn.dataset.origText = btn.innerHTML; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>'; }
    try {
      const res = await Auth.fetch(`/v1/admin/outreach/run/${name}`, { method: 'POST' });
      if (res?.ok || res?.status === 202) {
        Auth.toast('Job started — refresh in a minute', 'success');
      } else {
        const data = await res?.json();
        Auth.toast(data?.detail || 'Failed to start job', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
    finally { if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.origText || btn.innerHTML; } }
  },
  });

  Admin.registerSection({
    id: 'outreach',
    title: 'Outreach',
    loader: () => Admin.loadOutreach(),
    filters: [
      { selector: '#outreachStatusFilter', event: 'change',
        handler(el) { Admin._currentPage.outreach = 1; Admin.loadOutreach({ status: el.value || undefined }); } },
    ],
    actions: {
      'open-draft-modal': (el) => Admin.openDraftModal(Number(el.dataset.id)),
      'approve-draft': (el) => Admin.approveDraft(Number(el.dataset.id)),
      'reject-draft': (el) => Admin.rejectDraft(Number(el.dataset.id)),
      'save-draft': (el) => Admin.saveDraft(Number(el.dataset.id)),
      // Ook de knop "Draft new post (AI)" in de blogsectie gebruikt deze.
      'run-outreach-job': (el) => Admin.runOutreachJob(el.dataset.jobName, el),
    },
  });
})();
