/* ============================================================
   GSP Recruitment — admin/js/sections/users.js
   Gebruikersbeheer: lijst, rolwijziging, verifiëren, impersonatie, verwijderen.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern) en voor nav.js, dat de registry uitleest. Geen ES-module: de
   rest van de site gebruikt die ook niet.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  Object.assign(Admin, {
  /* ============================================================
     USERS
     ============================================================ */
  async loadUsers(params = {}) {
    this._lastParams.users = params;
    const qs = new URLSearchParams();
    const limit = this._pageSize;
    const offset = ((this._currentPage.users || 1) - 1) * limit;
    if (params.role) qs.set('role', params.role);
    if (params.status) qs.set('status', params.status);
    if (params.search) qs.set('search', params.search);
    qs.set('limit', limit);
    qs.set('offset', offset);

    this.setLoading('#section-users table tbody', 6);
    try {
      const res = await Auth.fetch(`/v1/admin/users?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.users = data;
      this.renderUsers(data);
      this.renderPagination('usersPagination', data.total, limit, this._currentPage.users, 'users');
    } catch (err) {
      this.setEmpty('#section-users table tbody', 6, 'Failed to load users');
      console.error(err);
    }
  },

  renderUsers(data) {
    const tbody = document.querySelector('#section-users table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#section-users table tbody', 6, 'Geen gebruikers gevonden voor deze filters.'); return; }
    mount(tbody, html`${items.map(u => html`
      <tr>
        <td class="a-cell-name">${u.full_name || '—'}</td>
        <td class="a-meta">${u.email}</td>
        <td><span class="${this.badge(u.role)}">${u.role}</span></td>
        <td><span class="${u.is_verified ? 'badge bg-green-lt' : 'badge bg-blue-lt'}">${u.is_verified ? 'Verified' : 'Pending'}</span></td>
        <td class="a-meta">${this.timeAgo(u.created_at)}</td>
        <td>
          <div class="action-menu-wrap">
            <button class="btn btn-sm btn-ghost-secondary" data-action="toggle-user-menu" data-id="${u.id}">
              <i class="fa-solid fa-ellipsis-vertical"></i>
            </button>
            <div class="action-menu" id="user-menu-${u.id}" style="display:none;">
              ${!u.is_verified ? html`<button data-action="verify-user" data-id="${u.id}"><i class="fa-regular fa-circle-check"></i> Verify</button>` : ''}
              <button data-action="edit-user" data-id="${u.id}"><i class="fa-solid fa-pen"></i> Edit Role</button>
              <button data-action="impersonate-user" data-id="${u.id}" data-email="${u.email}"><i class="fa-solid fa-mask"></i> Impersonate</button>
              <button data-action="delete-user" data-id="${u.id}" data-email="${u.email}" class="text-danger-ink"><i class="fa-solid fa-trash"></i> Delete</button>
            </div>
          </div>
        </td>
      </tr>`)}`);
  },

  toggleUserMenu(id) {
    // Fires from the delegated data-action click listener (bound after the
    // document-level closeMenus() listener in bindUI()), so closeMenus() has
    // already run for this same click by the time we get here -- no need
    // for stopPropagation() to race a separate document click handler the
    // way the old inline onclick= version did.
    this.closeMenus();
    const menu = document.getElementById(`user-menu-${id}`);
    if (menu) menu.style.display = 'block';
  },

  openEditUserModal(userId) {
    const user = (this._data.users?.items || []).find(u => u.id === userId);
    if (!user) return;
    this.openModal('editUserModal', html`
      <div class="form-group">
        <label>Full Name</label>
        <input type="text" id="editUserName" value="${user.full_name || ''}">
      </div>
      <div class="form-group">
        <label>Role</label>
        <select id="editUserRole">
          <option value="candidate" ${raw(user.role === 'candidate' ? 'selected' : '')}>Candidate</option>
          <option value="client" ${raw(user.role === 'client' ? 'selected' : '')}>Client</option>
          <option value="admin" ${raw(user.role === 'admin' ? 'selected' : '')}>Admin</option>
        </select>
      </div>
      <div class="form-group">
        <label>Verified</label>
        <select id="editUserVerified">
          <option value="true" ${raw(user.is_verified ? 'selected' : '')}>Yes</option>
          <option value="false" ${raw(!user.is_verified ? 'selected' : '')}>No</option>
        </select>
      </div>
      <div class="a-actions">
        <button class="btn btn-primary" data-action="save-user-edit" data-id="${userId}">Save Changes</button>
        <button class="btn btn-ghost-secondary" data-action="close-modal">Cancel</button>
      </div>
    `, { title: 'Edit User: ' + (user.full_name || user.email) });
  },

  async saveUserEdit(userId) {
    const name = document.getElementById('editUserName')?.value?.trim();
    const role = document.getElementById('editUserRole')?.value;
    const verified = document.getElementById('editUserVerified')?.value === 'true';
    const payload = {};
    if (name) payload.full_name = name;
    if (role) payload.role = role;
    payload.is_verified = verified;

    try {
      const res = await Auth.fetch(`/v1/admin/users/${userId}`, {
        method: 'PUT', body: JSON.stringify(payload),
      });
      if (res?.ok) {
        Auth.toast('User updated', 'success');
        this.closeModal();
        await this.loadUsers();
      } else {
        const d = await res?.json();
        Auth.toast(d?.detail || 'Update failed', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
  },

  async impersonateUser(userId, email) {
    if (!confirm(`Impersonate ${email}? You will get a 15-minute session token as this user.`)) return;
    try {
      const res = await Auth.fetch(`/v1/admin/users/${userId}/impersonate`, { method: 'POST' });
      if (!res?.ok) { Auth.toast('Impersonation failed', 'error'); return; }
      const data = await res.json();
      const user = data.user;
      // WS-B.2: park the admin's own token/user first so it's never left
      // sitting in the normal (impersonated-session) token slot -- see
      // Auth.startImpersonation() / restoreAdmin() in auth.js.
      Auth.startImpersonation(data.access_token, user);
      const dest = user.role === 'candidate' ? '/candidate/' : user.role === 'client' ? '/client/' : '/admin/';
      window.location.href = dest;
    } catch { Auth.toast('Network error', 'error'); }
  },

  confirmDeleteUser(userId, email) {
    if (!confirm(`Permanently delete ${email}? This cannot be undone.`)) return;
    this.deleteUser(userId, email);
  },

  async deleteUser(userId, email) {
    try {
      const res = await Auth.fetch(`/v1/admin/users/${userId}`, { method: 'DELETE' });
      if (res?.ok) {
        Auth.toast(`${email} deleted`, 'success');
        await this.loadUsers();
        await this.loadDashboard();
      } else {
        const d = await res?.json();
        Auth.toast(d?.detail || 'Delete failed', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
  },
  });

  Admin.registerSection({
    id: 'users',
    title: 'User Management',
    loader: () => Admin.loadUsers(),
    filters: [
      // #userSearch werd voor deze splitsing in nav.js gebonden en
      // #userRoleFilter/#userStatusFilter in admin.js. Nu op één plek.
      { selector: '#userSearch', event: 'input', debounce: 400,
        handler(el) { Admin._currentPage.users = 1; Admin.loadUsers({ search: el.value.trim() }); } },
      { selector: '#userRoleFilter', event: 'change',
        handler(el) {
          const v = el.value;
          Admin.loadUsers({ role: ['candidate', 'client', 'admin'].includes(v) ? v : '' });
        } },
      { selector: '#userStatusFilter', event: 'change',
        handler(el) {
          const v = el.value;
          Admin.loadUsers({ status: ['verified', 'unverified'].includes(v) ? v : '' });
        } },
    ],
    actions: {
      'verify-user': (el) => { Admin.verifyUser(Number(el.dataset.id), el); Admin.closeMenus(); },
      'toggle-user-menu': (el) => Admin.toggleUserMenu(Number(el.dataset.id)),
      'edit-user': (el) => { Admin.openEditUserModal(Number(el.dataset.id)); Admin.closeMenus(); },
      'save-user-edit': (el) => Admin.saveUserEdit(Number(el.dataset.id)),
      'impersonate-user': (el) => { Admin.impersonateUser(Number(el.dataset.id), el.dataset.email || ''); Admin.closeMenus(); },
      'delete-user': (el) => { Admin.confirmDeleteUser(Number(el.dataset.id), el.dataset.email || ''); Admin.closeMenus(); },
    },
  });
})();
