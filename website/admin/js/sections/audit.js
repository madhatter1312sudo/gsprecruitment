/* ============================================================
   GSP Recruitment — admin/js/sections/audit.js
   Audit-log met actiefilter.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern) en voor nav.js, dat de registry uitleest. Geen ES-module: de
   rest van de site gebruikt die ook niet.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  Object.assign(Admin, {
  /* ============================================================
     AUDIT LOG
     ============================================================ */
  async loadAuditLog(params = {}) {
    this._lastParams.audit = params;
    const qs = new URLSearchParams();
    const limit = this._pageSize;
    const offset = ((this._currentPage.audit || 1) - 1) * limit;
    if (params.action) qs.set('action', params.action);
    qs.set('limit', limit);
    qs.set('offset', offset);

    this.setLoading('#section-audit table tbody', 5);
    try {
      const res = await Auth.fetch(`/v1/admin/audit-log?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.audit = data;
      this.renderAuditLog(data);
      this.renderPagination('auditPagination', data.total, limit, this._currentPage.audit, 'audit');
    } catch {
      this.setEmpty('#section-audit table tbody', 5, 'Failed to load audit log');
    }
  },

  // `changes` (models/schemas.py AuditLogEntry.changes) is a free-form
  // dict written by whichever admin action logged the entry -- a scalar
  // value renders as an escaped "key: value" line, an object/array value
  // is JSON.stringify'd and truncated at 300 chars inside a <details> so
  // one bulky diff never blows out the row height.
  auditChangesHtml(changes) {
    if (!changes || typeof changes !== 'object' || !Object.keys(changes).length) return raw('—');
    return html`<ul class="a-inline-list">${Object.entries(changes).map(([k, v]) => {
      if (v !== null && typeof v === 'object') {
        const str = JSON.stringify(v);
        const truncated = str.length > 300 ? str.slice(0, 300) + '…' : str;
        return html`<li><strong>${k}</strong>: <details><summary class="a-clickable a-soft">JSON</summary><pre class="a-scrollbox">${truncated}</pre></details></li>`;
      }
      return html`<li><strong>${k}</strong>: ${v}</li>`;
    })}</ul>`;
  },

  renderAuditLog(data) {
    const tbody = document.querySelector('#section-audit table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#section-audit table tbody', 5, 'Nog geen audit-log entries voor dit filter.'); return; }
    const colors = { user_delete: 'text-danger-ink', impersonate: 'text-warning-ink', settings_update: 'text-info-ink' };
    mount(tbody, html`${items.map(e => html`
      <tr>
        <td class="a-meta text-nowrap">${this.formatDate(e.created_at)}</td>
        <td><span class="${colors[e.action] || 'a-accent'}">${e.action?.replace(/_/g, ' ')}</span></td>
        <td class="a-meta">${e.actor_email || 'system'}</td>
        <td class="a-meta">${e.target_type ? e.target_type + ' #' + e.target_id : '—'}</td>
        <td class="a-meta">${this.auditChangesHtml(e.changes)}</td>
      </tr>`)}`);
  },
  });

  Admin.registerSection({
    id: 'audit',
    title: 'Audit Log',
    loader: () => Admin.loadAuditLog(),
    filters: [
      { selector: '#auditActionFilter', event: 'input', debounce: 500,
        handler(el) { Admin._currentPage.audit = 1; Admin.loadAuditLog({ action: el.value.trim() || undefined }); } },
    ],
  });
})();
