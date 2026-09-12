/* ============================================================
   GSP Recruitment — admin/js/sections/cms.js
   Content CMS: sleutel/waarde-items per sectie.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern) en voor nav.js, dat de registry uitleest. Geen ES-module: de
   rest van de site gebruikt die ook niet.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  Object.assign(Admin, {
  /* ============================================================
     CONTENT CMS
     ============================================================ */
  async loadContent() {
    try {
      const res = await Auth.fetch('/v1/admin/content');
      if (!res?.ok) return;
      const rows = await res.json();
      this._data.content = rows;
      this.renderContent(rows);
    } catch { console.error('Content load error'); }
  },

  renderContent(rows) {
    const el = document.getElementById('contentList');
    if (!el) return;
    if (!rows.length) { mount(el, html`<div class="a-state-block">Nog geen content-items. Voeg ze toe via de API of database.</div>`); return; }
    mount(el, html`${rows.map(item => html`
      <div class="a-listrow">
        <div class="flex-fill">
          <div class="a-meta">${item.section} / ${item.key}</div>
          <div class="a-soft mt-1">${(item.value || '').slice(0, 80)}${(item.value || '').length > 80 ? '…' : ''}</div>
        </div>
        <button class="btn btn-sm btn-ghost-secondary" data-action="edit-content" data-id="${item.id}" data-key="${item.key}" data-value="${item.value || ''}">
          <i class="fa-solid fa-pen"></i>
        </button>
      </div>`)}`);
  },

  editContent(id, key, value) {
    this.openModal('editContentModal', html`
      <div class="form-group">
        <label>Value</label>
        <textarea id="editContentValue" rows="5" class="a-textarea">${value}</textarea>
      </div>
      <div class="a-actions">
        <button class="btn btn-primary" data-action="save-content" data-id="${id}">Save</button>
        <button class="btn btn-ghost-secondary" data-action="close-modal">Cancel</button>
      </div>
    `, { title: 'Edit: ' + key });
  },

  async saveContent(id) {
    const value = document.getElementById('editContentValue')?.value;
    if (value == null) return;
    try {
      const res = await Auth.fetch(`/v1/admin/content/${id}`, {
        method: 'PUT', body: JSON.stringify({ value }),
      });
      if (res?.ok) {
        Auth.toast('Content updated', 'success');
        this.closeModal();
        await this.loadContent();
      } else { Auth.toast('Update failed', 'error'); }
    } catch { Auth.toast('Network error', 'error'); }
  },
  });

  Admin.registerSection({
    id: 'cms',
    title: 'Content CMS',
    loader: () => Admin.loadContent(),
    filters: [],
    actions: {
      'edit-content': (el) => Admin.editContent(Number(el.dataset.id), el.dataset.key || '', el.dataset.value || ''),
      'save-content': (el) => Admin.saveContent(Number(el.dataset.id)),
    },
  });
})();
