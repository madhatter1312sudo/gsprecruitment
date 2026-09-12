/* ============================================================
   GSP Recruitment — admin/js/sections/blog.js
   Blogbeheer. Publiceren is een aparte, expliciete actie na opslaan.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern) en voor nav.js, dat de registry uitleest. Geen ES-module: de
   rest van de site gebruikt die ook niet.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  Object.assign(Admin, {
  /* ============================================================
     BLOG
     ============================================================ */
  async loadBlog(params = {}) {
    this._lastParams.blog = params;
    const qs = new URLSearchParams();
    const limit = this._pageSize;
    const offset = ((this._currentPage.blog || 1) - 1) * limit;
    const statusFilter = document.getElementById('blogStatusFilter');
    const status = params.status !== undefined ? params.status : statusFilter?.value;
    if (status) qs.set('status', status);
    qs.set('limit', limit);
    qs.set('offset', offset);

    this.setLoading('#section-blog table tbody', 6);
    try {
      const res = await Auth.fetch(`/v1/admin/blog/?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.blog = data;
      this.renderBlog(data);
      this.renderPagination('blogPagination', data.total, limit, this._currentPage.blog, 'blog');
    } catch (err) {
      this.setEmpty('#section-blog table tbody', 6, 'Failed to load blog posts');
      console.error(err);
    }
  },

  renderBlog(data) {
    const tbody = document.querySelector('#section-blog table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#section-blog table tbody', 6, 'Nog geen blogposts. Klik op "New post" of "Draft new post (AI)" hierboven om te beginnen.'); return; }
    mount(tbody, html`${items.map(p => {
      const tags = Array.isArray(p.tags) ? p.tags.join(', ') : (p.tags || '—');
      return html`
      <tr>
        <td class="a-cell-name">${p.title_nl || '—'}</td>
        <td class="a-meta">${p.slug}</td>
        <td class="a-meta">${tags}</td>
        <td><span class="${this.badge(p.status)}">${p.status}</span></td>
        <td class="a-meta">${p.published_at ? this.formatDate(p.published_at) : '—'}</td>
        <td>
          <button class="btn btn-sm btn-ghost-secondary" data-action="open-blog-modal" data-id="${p.id}" title="Edit">
            <i class="fa-solid fa-pen"></i>
          </button>
          ${p.status === 'draft' ? html`
            <button class="btn btn-sm btn-ghost-secondary a-positive" data-action="publish-blog-post" data-id="${p.id}" title="Publish">
              <i class="fa-regular fa-circle-check"></i>
            </button>` : ''}
          ${p.status === 'published' ? html`
            <button class="btn btn-sm btn-ghost-secondary a-danger" data-action="archive-blog-post" data-id="${p.id}" title="Archive">
              <i class="fa-solid fa-box-archive"></i>
            </button>` : ''}
        </td>
      </tr>`;
    })}`);
  },

  openBlogModal(id) {
    const p = id ? (this._data.blog?.items || []).find(x => x.id === id) : null;
    this.openModal('blogModal', html`
      <div class="form-group">
        <label>Slug</label>
        <input type="text" id="blogSlug" value="${p?.slug || ''}">
      </div>
      <div class="form-group">
        <label>Title (NL)</label>
        <input type="text" id="blogTitleNl" value="${p?.title_nl || ''}">
      </div>
      <div class="form-group">
        <label>Title (EN)</label>
        <input type="text" id="blogTitleEn" value="${p?.title_en || ''}">
      </div>
      <div class="form-group">
        <label>Excerpt (NL)</label>
        <textarea id="blogExcerptNl" rows="3" class="a-textarea">${p?.excerpt_nl || ''}</textarea>
      </div>
      <div class="form-group">
        <label>Excerpt (EN)</label>
        <textarea id="blogExcerptEn" rows="3" class="a-textarea">${p?.excerpt_en || ''}</textarea>
      </div>
      <div class="form-group">
        <label>Body HTML (NL)</label>
        <textarea id="blogBodyNl" rows="10" class="a-textarea">${p?.body_nl || ''}</textarea>
      </div>
      <div class="form-group">
        <label>Body HTML (EN)</label>
        <textarea id="blogBodyEn" rows="10" class="a-textarea">${p?.body_en || ''}</textarea>
      </div>
      <div class="form-group">
        <label>Tags (comma-separated)</label>
        <input type="text" id="blogTags" value="${Array.isArray(p?.tags) ? p.tags.join(', ') : (p?.tags || '')}">
      </div>
      <div class="form-group">
        <label>Read time (min)</label>
        <input type="number" id="blogReadTime" value="${p?.read_time_min ?? ''}">
      </div>
      <div class="a-actions">
        <button class="btn btn-primary" data-action="save-blog-post" data-id="${p ? p.id : ''}">Save</button>
        <button class="btn btn-ghost-secondary" data-action="close-modal">Cancel</button>
      </div>
    `, { title: p ? 'Edit Post' : 'New Post' });
  },

  async saveBlogPost(id) {
    const payload = {
      slug: document.getElementById('blogSlug')?.value?.trim(),
      title_nl: document.getElementById('blogTitleNl')?.value?.trim(),
      title_en: document.getElementById('blogTitleEn')?.value?.trim(),
      excerpt_nl: document.getElementById('blogExcerptNl')?.value,
      excerpt_en: document.getElementById('blogExcerptEn')?.value,
      body_nl: document.getElementById('blogBodyNl')?.value,
      body_en: document.getElementById('blogBodyEn')?.value,
      tags: (document.getElementById('blogTags')?.value || '').split(',').map(t => t.trim()).filter(Boolean),
      read_time_min: parseInt(document.getElementById('blogReadTime')?.value, 10) || null,
    };
    try {
      const res = id
        ? await Auth.fetch(`/v1/admin/blog/${id}`, { method: 'PUT', body: JSON.stringify(payload) })
        : await Auth.fetch(`/v1/admin/blog/`, { method: 'POST', body: JSON.stringify(payload) });
      if (res?.ok) {
        Auth.toast(id ? 'Post updated' : 'Post created', 'success');
        this.closeModal();
        await this.loadBlog();
      } else {
        const d = await res?.json();
        Auth.toast(d?.detail || 'Save failed', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
  },

  async publishBlogPost(id) {
    if (!confirm('Publish this post? It will become visible on the public blog.')) return;
    try {
      const res = await Auth.fetch(`/v1/admin/blog/${id}/publish`, { method: 'POST' });
      if (res?.ok) {
        Auth.toast('Post published', 'success');
        await this.loadBlog();
      } else {
        const d = await res?.json();
        Auth.toast(d?.detail || 'Publish failed', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
  },

  async archiveBlogPost(id) {
    if (!confirm('Archive this post? It will be removed from the public blog.')) return;
    try {
      const res = await Auth.fetch(`/v1/admin/blog/${id}/archive`, { method: 'POST' });
      if (res?.ok) {
        Auth.toast('Post archived', 'success');
        await this.loadBlog();
      } else {
        const d = await res?.json();
        Auth.toast(d?.detail || 'Archive failed', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
  },
  });

  Admin.registerSection({
    id: 'blog',
    title: 'Blog',
    loader: () => Admin.loadBlog(),
    filters: [
      { selector: '#blogStatusFilter', event: 'change',
        handler(el) { Admin._currentPage.blog = 1; Admin.loadBlog({ status: el.value || undefined }); } },
    ],
    actions: {
      'open-blog-modal': (el) => Admin.openBlogModal(el.dataset.id ? Number(el.dataset.id) : null),
      'publish-blog-post': (el) => Admin.publishBlogPost(Number(el.dataset.id)),
      'archive-blog-post': (el) => Admin.archiveBlogPost(Number(el.dataset.id)),
      'save-blog-post': (el) => Admin.saveBlogPost(el.dataset.id ? Number(el.dataset.id) : null),
    },
  });
})();
