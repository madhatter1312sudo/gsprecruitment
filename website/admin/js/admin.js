/* ============================================================
   GSP Recruitment — admin.js  v2.0
   Full admin portal: all sections wired to real API, no stubs.
   ============================================================ */

const Admin = {
  _data: {},
  _currentPage: { users: 1, candidates: 1, audit: 1, outreach: 1, blog: 1 },
  _pageSize: 20,

  /* ---- Init ---- */
  async init() {
    const user = Auth.requireAuth(['admin']);
    if (!user) return;

    const name = user.full_name || 'Admin';
    const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
    document.getElementById('sidebarName').textContent = name;
    document.getElementById('sidebarEmail').textContent = user.email || '';
    document.getElementById('sidebarAvatar').textContent = initials;

    await this.loadDashboard();
  },

  /* ---- Utilities ---- */
  formatDate(d) {
    if (!d) return '—';
    const dt = new Date(d);
    return dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  },
  timeAgo(d) {
    if (!d) return '';
    const s = (Date.now() - new Date(d)) / 1000;
    if (s < 60) return 'just now';
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    if (s < 604800) return `${Math.floor(s / 86400)}d ago`;
    return this.formatDate(d);
  },
  badge(status) {
    const map = { active: 'green', open: 'green', placed: 'blue',
      pending: 'blue', suspended: 'red', closed: 'red',
      draft: 'blue', admin: 'red', candidate: 'gold', client: 'blue',
      sent: 'green', rejected: 'default', failed: 'red',
      published: 'green', archived: 'default' };
    const colors = { green: 'bg-green-lt', blue: 'bg-blue-lt', gold: 'bg-yellow-lt', red: 'bg-red-lt', default: 'bg-secondary-lt' };
    return `badge ${colors[map[status?.toLowerCase()] || 'default']}`;
  },
  esc(s) {
    if (s == null) return '';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  },
  setLoading(tbodyId, cols) {
    const el = document.querySelector(tbodyId);
    if (el) el.innerHTML = `<tr><td colspan="${cols}" style="text-align:center;padding:2rem;color:var(--navy-300);">
      <i class="fa-regular fa-spinner fa-spin"></i> Loading…</td></tr>`;
  },
  setEmpty(tbodyId, cols, msg = 'No results') {
    const el = document.querySelector(tbodyId);
    if (el) el.innerHTML = `<tr><td colspan="${cols}" style="text-align:center;padding:2rem;color:var(--navy-300);">${msg}</td></tr>`;
  },

  /* ============================================================
     DASHBOARD
     ============================================================ */
  async loadDashboard() {
    try {
      const [dashRes, recentRes] = await Promise.all([
        Auth.fetch('/v1/admin/dashboard'),
        Auth.fetch('/v1/admin/audit-log?limit=8'),
      ]);

      if (dashRes?.ok) {
        const d = await dashRes.json();
        document.getElementById('kpiTotalUsers').textContent = d.total_users ?? 0;
        document.getElementById('kpiActiveJobs').textContent = d.active_jobs ?? 0;
        document.getElementById('kpiCandidates').textContent = d.registered_candidates ?? 0;
        document.getElementById('kpiClients').textContent = d.active_clients ?? 0;
        document.getElementById('kpiPlacements').textContent = d.placements_this_week ?? 0;
        this._data.dashboard = d;
      }

      if (recentRes?.ok) {
        const auditData = await recentRes.json();
        this.renderRecentActivity(auditData.items || []);
      }

      // Load pending (unverified) users for the pending widget
      const pendingRes = await Auth.fetch('/v1/admin/users?status=unverified&limit=5');
      if (pendingRes?.ok) {
        const pd = await pendingRes.json();
        this.renderPendingRegistrations(pd.items || []);
      }
    } catch (err) {
      console.error('Dashboard load error:', err);
    }
  },

  renderRecentActivity(items) {
    const el = document.getElementById('recentActivityList');
    if (!el) return;
    if (!items.length) { el.innerHTML = '<div style="color:var(--navy-300);font-size:var(--font-size-sm);padding:1rem 0;">No recent activity</div>'; return; }
    const icons = { user_update: 'fa-user-pen', user_delete: 'fa-user-xmark', impersonate: 'fa-mask',
      job_update: 'fa-briefcase', content_update: 'fa-newspaper', settings_update: 'fa-gear',
      placement: 'fa-calendar-check' };
    el.innerHTML = items.map(e => `
      <div class="activity-item">
        <div class="activity-icon" style="background:rgba(250,200,0,0.1);color:var(--gold-400);">
          <i class="fa-regular ${icons[e.action] || 'fa-circle-dot'}"></i>
        </div>
        <div class="activity-content" style="flex:1;">
          <div class="activity-text">${this.esc(e.action?.replace(/_/g, ' '))} <span style="color:var(--navy-300);">by ${this.esc(e.actor_email || 'system')}</span></div>
          <div class="activity-time">${this.timeAgo(e.created_at)}</div>
        </div>
      </div>`).join('');
  },

  renderPendingRegistrations(items) {
    const el = document.getElementById('pendingRegistrationsList');
    const badge = document.getElementById('pendingBadge');
    if (badge) badge.textContent = items.length || '0';
    if (!el) return;
    if (!items.length) { el.innerHTML = '<div style="color:var(--navy-300);font-size:var(--font-size-sm);padding:0.5rem 0;">No pending registrations</div>'; return; }
    el.innerHTML = items.map(u => `
      <div class="activity-item">
        <div class="activity-icon" style="background:rgba(250,200,0,0.1);color:var(--gold-500);"><i class="fa-regular fa-user-plus"></i></div>
        <div class="activity-content" style="flex:1;">
          <div class="activity-text">${this.esc(u.full_name || u.email)} — <span style="color:var(--gold-400);">${this.esc(u.role)}</span></div>
          <div class="activity-time">${this.timeAgo(u.created_at)}</div>
        </div>
        <button class="btn btn-sm btn-primary" onclick="Admin.verifyUser(${u.id}, this)" style="flex-shrink:0;">Verify</button>
      </div>`).join('');
  },

  async verifyUser(userId, btn) {
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
      const res = await Auth.fetch(`/v1/admin/users/${userId}`, {
        method: 'PUT', body: JSON.stringify({ is_verified: true }),
      });
      if (res?.ok) {
        Auth.toast('User verified', 'success');
        await this.loadDashboard();
        if (document.getElementById('section-users').classList.contains('active')) {
          await this.loadUsers();
        }
      } else {
        const d = await res?.json();
        Auth.toast(d?.detail || 'Failed to verify', 'error');
        if (btn) { btn.disabled = false; btn.textContent = 'Verify'; }
      }
    } catch { Auth.toast('Network error', 'error'); if (btn) { btn.disabled = false; btn.textContent = 'Verify'; } }
  },

  /* ============================================================
     USERS
     ============================================================ */
  async loadUsers(params = {}) {
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
      this.renderPagination('usersPagination', data.total, limit, this._currentPage.users, (p) => {
        this._currentPage.users = p;
        this.loadUsers(params);
      });
    } catch (err) {
      this.setEmpty('#section-users table tbody', 6, 'Failed to load users');
      console.error(err);
    }
  },

  renderUsers(data) {
    const tbody = document.querySelector('#section-users table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#section-users table tbody', 6, 'No users found'); return; }
    tbody.innerHTML = items.map(u => `
      <tr>
        <td style="font-weight:600;color:var(--white);">${this.esc(u.full_name || '—')}</td>
        <td style="color:var(--navy-200);font-size:var(--font-size-xs);">${this.esc(u.email)}</td>
        <td><span class="${this.badge(u.role)}">${this.esc(u.role)}</span></td>
        <td><span class="${u.is_verified ? 'badge bg-green-lt' : 'badge bg-blue-lt'}">${u.is_verified ? 'Verified' : 'Pending'}</span></td>
        <td style="font-size:var(--font-size-xs);color:var(--navy-300);">${this.timeAgo(u.created_at)}</td>
        <td>
          <div class="action-menu-wrap" style="position:relative;">
            <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.toggleUserMenu(${u.id}, event)">
              <i class="fa-regular fa-ellipsis-vertical"></i>
            </button>
            <div class="action-menu" id="user-menu-${u.id}" style="display:none;">
              ${!u.is_verified ? `<button onclick="Admin.verifyUser(${u.id});Admin.closeMenus()"><i class="fa-regular fa-circle-check"></i> Verify</button>` : ''}
              <button onclick="Admin.openEditUserModal(${u.id});Admin.closeMenus()"><i class="fa-regular fa-pen"></i> Edit Role</button>
              <button onclick="Admin.impersonateUser(${u.id}, '${this.esc(u.email)}');Admin.closeMenus()"><i class="fa-regular fa-mask"></i> Impersonate</button>
              <button onclick="Admin.confirmDeleteUser(${u.id}, '${this.esc(u.email)}');Admin.closeMenus()" style="color:#f87171;"><i class="fa-regular fa-trash"></i> Delete</button>
            </div>
          </div>
        </td>
      </tr>`).join('');
  },

  toggleUserMenu(id, e) {
    e.stopPropagation();
    this.closeMenus();
    const menu = document.getElementById(`user-menu-${id}`);
    if (menu) menu.style.display = 'block';
  },
  closeMenus() {
    document.querySelectorAll('.action-menu').forEach(m => m.style.display = 'none');
  },

  openEditUserModal(userId) {
    const user = (this._data.users?.items || []).find(u => u.id === userId);
    if (!user) return;
    this.openModal('editUserModal', `
      <h3 style="color:var(--white);margin-bottom:var(--space-lg);">Edit User: ${this.esc(user.full_name || user.email)}</h3>
      <div class="form-group">
        <label>Full Name</label>
        <input type="text" id="editUserName" value="${this.esc(user.full_name || '')}">
      </div>
      <div class="form-group">
        <label>Role</label>
        <select id="editUserRole">
          <option value="candidate" ${user.role === 'candidate' ? 'selected' : ''}>Candidate</option>
          <option value="client" ${user.role === 'client' ? 'selected' : ''}>Client</option>
          <option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Admin</option>
        </select>
      </div>
      <div class="form-group">
        <label>Verified</label>
        <select id="editUserVerified">
          <option value="true" ${user.is_verified ? 'selected' : ''}>Yes</option>
          <option value="false" ${!user.is_verified ? 'selected' : ''}>No</option>
        </select>
      </div>
      <div style="display:flex;gap:var(--space-md);margin-top:var(--space-lg);">
        <button class="btn btn-primary" onclick="Admin.saveUserEdit(${userId})">Save Changes</button>
        <button class="btn btn-ghost-secondary" onclick="Admin.closeModal()">Cancel</button>
      </div>
    `);
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
      Auth.setAuth(data.access_token, user);
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

  /* ============================================================
     JOBS
     ============================================================ */
  async loadJobs(params = {}) {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    qs.set('limit', 50);

    this.setLoading('#section-jobs table tbody', 5);
    try {
      const res = await Auth.fetch(`/v1/admin/jobs?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.jobs = data;
      this.renderJobs(data);
    } catch (err) {
      this.setEmpty('#section-jobs table tbody', 5, 'Failed to load jobs');
    }
  },

  renderJobs(data) {
    const tbody = document.querySelector('#section-jobs table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#section-jobs table tbody', 5, 'No jobs found'); return; }
    tbody.innerHTML = items.map(j => `
      <tr>
        <td style="font-weight:600;color:var(--white);">${this.esc(j.title || 'Untitled')}</td>
        <td style="color:var(--navy-200);">${this.esc(j.company_name || '—')}</td>
        <td style="text-align:center;">${j.application_count ?? '—'}</td>
        <td><span class="${this.badge(j.status)}">${this.esc(j.status || 'draft')}</span></td>
        <td>
          ${j.status === 'draft' || j.status === 'pending' ? `
            <button class="btn btn-sm btn-primary" onclick="Admin.setJobStatus(${j.id}, 'open')" title="Approve">
              <i class="fa-regular fa-circle-check"></i> Approve
            </button>` : ''}
          ${j.status === 'open' ? `
            <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.setJobStatus(${j.id}, 'closed')" title="Close" style="color:#f87171;">
              <i class="fa-regular fa-xmark"></i> Close
            </button>` : ''}
          <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.triggerMatching(${j.id})" title="Run AI matching">
            <i class="fa-regular fa-wand-magic-sparkles"></i>
          </button>
          <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.confirmDeleteJob(${j.id})" title="Delete" style="color:#f87171;">
            <i class="fa-regular fa-trash"></i>
          </button>
        </td>
      </tr>`).join('');
  },

  async setJobStatus(jobId, status) {
    try {
      const res = await Auth.fetch(`/v1/admin/jobs/${jobId}`, {
        method: 'PUT', body: JSON.stringify({ status }),
      });
      if (res?.ok) {
        Auth.toast(`Job ${status === 'open' ? 'approved' : 'closed'}`, 'success');
        await this.loadJobs();
      } else {
        const d = await res?.json();
        Auth.toast(d?.detail || 'Update failed', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
  },

  async triggerMatching(jobId) {
    Auth.toast('Running AI matching…', 'info');
    try {
      const res = await Auth.fetch(`/v1/matches/run?job_id=${jobId}`, { method: 'POST' });
      if (res?.ok) Auth.toast('Matching queued — results will appear shortly', 'success');
      else Auth.toast('Failed to start matching', 'error');
    } catch { Auth.toast('Network error', 'error'); }
  },

  confirmDeleteJob(jobId) {
    if (!confirm('Delete this job? This action cannot be undone.')) return;
    this.deleteJob(jobId);
  },

  async deleteJob(jobId) {
    try {
      const res = await Auth.fetch(`/v1/admin/jobs/${jobId}`, { method: 'DELETE' });
      if (res?.ok || res?.status === 404) {
        Auth.toast('Job deleted', 'success');
        await this.loadJobs();
      } else {
        Auth.toast('Delete failed', 'error');
      }
    } catch { Auth.toast('Network error', 'error'); }
  },

  /* ============================================================
     CANDIDATES
     ============================================================ */
  async loadCandidates(params = {}) {
    const qs = new URLSearchParams();
    const limit = this._pageSize;
    const offset = ((this._currentPage.candidates || 1) - 1) * limit;
    if (params.search) qs.set('search', params.search);
    if (params.status) qs.set('status', params.status);
    qs.set('limit', limit);
    qs.set('offset', offset);

    this.setLoading('#section-candidates table tbody', 6);
    try {
      const res = await Auth.fetch(`/v1/admin/candidates?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.candidates = data;
      this.renderCandidates(data);
      this.renderPagination('candidatesPagination', data.total, limit, this._currentPage.candidates, (p) => {
        this._currentPage.candidates = p;
        this.loadCandidates(params);
      });
    } catch (err) {
      this.setEmpty('#section-candidates table tbody', 6, 'Failed to load candidates');
    }
  },

  renderCandidates(data) {
    const tbody = document.querySelector('#section-candidates table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#section-candidates table tbody', 6, 'No candidates found'); return; }
    tbody.innerHTML = items.map(c => `
      <tr>
        <td style="font-weight:600;color:var(--white);">${this.esc(c.full_name || '—')}</td>
        <td style="color:var(--navy-200);font-size:var(--font-size-xs);">${this.esc(c.email)}</td>
        <td>${this.esc(c.current_title || '—')}</td>
        <td style="text-align:center;">${c.years_experience ? c.years_experience + ' yrs' : '—'}</td>
        <td style="text-align:center;">
          <span title="Matches">${c.match_count ?? 0}</span>
          ${c.placement_count ? ` / <span style="color:#4ade80;" title="Placed">${c.placement_count} placed</span>` : ''}
        </td>
        <td>
          <span class="${this.badge(c.status || 'active')}">${this.esc(c.status || 'active')}</span>
        </td>
        <td>
          <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.viewCandidate(${c.id})" title="View profile">
            <i class="fa-regular fa-eye"></i>
          </button>
          <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.triggerCandidateMatch(${c.id})" title="Run matching">
            <i class="fa-regular fa-wand-magic-sparkles"></i>
          </button>
        </td>
      </tr>`).join('');
  },

  viewCandidate(candidateId) {
    const c = (this._data.candidates?.items || []).find(x => x.id === candidateId);
    if (!c) return;
    const skills = Array.isArray(c.skills) ? c.skills.join(', ') : (c.skills || '—');
    this.openModal('viewCandidateModal', `
      <h3 style="color:var(--white);margin-bottom:var(--space-lg);">${this.esc(c.full_name)}</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-md);margin-bottom:var(--space-lg);">
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Email</div><div>${this.esc(c.email)}</div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Phone</div><div>${this.esc(c.phone || '—')}</div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Current Title</div><div>${this.esc(c.current_title || '—')}</div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Company</div><div>${this.esc(c.current_company || '—')}</div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Experience</div><div>${c.years_experience ? c.years_experience + ' years' : '—'}</div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Location</div><div>${this.esc(c.location || '—')}</div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Source</div><div>${this.esc(c.source || '—')}</div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Status</div><div><span class="${this.badge(c.status)}">${this.esc(c.status || 'active')}</span></div></div>
      </div>
      <div style="margin-bottom:var(--space-md);">
        <div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Skills</div>
        <div>${this.esc(skills)}</div>
      </div>
      <div style="display:flex;gap:var(--space-md);flex-wrap:wrap;margin-top:var(--space-lg);">
        <div style="background:rgba(74,111,159,0.1);border:1px solid rgba(74,111,159,0.2);border-radius:var(--radius-md);padding:var(--space-md) var(--space-lg);text-align:center;flex:1;">
          <div style="font-size:var(--font-size-xl);font-weight:700;color:var(--gold-500);">${c.match_count ?? 0}</div>
          <div style="font-size:var(--font-size-xs);color:var(--navy-300);">Matches</div>
        </div>
        <div style="background:rgba(74,111,159,0.1);border:1px solid rgba(74,111,159,0.2);border-radius:var(--radius-md);padding:var(--space-md) var(--space-lg);text-align:center;flex:1;">
          <div style="font-size:var(--font-size-xl);font-weight:700;color:#4ade80;">${c.placement_count ?? 0}</div>
          <div style="font-size:var(--font-size-xs);color:var(--navy-300);">Placed</div>
        </div>
      </div>
      <div style="margin-top:var(--space-lg);display:flex;gap:var(--space-md);">
        <button class="btn btn-primary btn-sm" onclick="Admin.triggerCandidateMatch(${c.id});Admin.closeModal()">
          <i class="fa-regular fa-wand-magic-sparkles"></i> Run Matching
        </button>
        <button class="btn btn-ghost-secondary btn-sm" onclick="Admin.closeModal()">Close</button>
      </div>
    `);
  },

  async triggerCandidateMatch(candidateId) {
    Auth.toast('Running AI matching for candidate…', 'info');
    try {
      const res = await Auth.fetch(`/v1/matches/run`, { method: 'POST' });
      if (res?.ok) Auth.toast('Matching queued', 'success');
      else Auth.toast('Failed to start matching', 'error');
    } catch { Auth.toast('Network error', 'error'); }
  },

  /* ============================================================
     OUTREACH
     ============================================================ */
  async loadOutreach(params = {}) {
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
      this.renderPagination('outreachPagination', data.total, limit, this._currentPage.outreach, (p) => {
        this._currentPage.outreach = p;
        this.loadOutreach(params);
      });
    } catch (err) {
      this.setEmpty('#section-outreach table tbody', 8, 'Failed to load outreach drafts');
      console.error(err);
    }
  },

  renderOutreach(data) {
    const tbody = document.querySelector('#section-outreach table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#section-outreach table tbody', 8, 'No outreach drafts found'); return; }
    tbody.innerHTML = items.map(d => `
      <tr>
        <td style="color:var(--navy-200);font-size:var(--font-size-xs);">${this.esc(d.target_name || d.target_email || '—')}</td>
        <td style="color:var(--navy-200);">${this.esc(d.company || '—')}</td>
        <td style="color:var(--white);">${this.esc(d.subject || '—')}</td>
        <td><span class="${this.badge(d.target_type)}">${this.esc(d.target_type)}</span></td>
        <td style="font-size:var(--font-size-xs);color:var(--navy-300);">${this.esc(d.ai_model || '—')}</td>
        <td style="font-size:var(--font-size-xs);color:var(--navy-300);">${this.timeAgo(d.created_at)}</td>
        <td><span class="${this.badge(d.status)}">${this.esc(d.status)}</span></td>
        <td>
          <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.openDraftModal(${d.id})" title="Review">
            <i class="fa-regular fa-eye"></i>
          </button>
          ${d.status === 'draft' ? `
            <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.approveDraft(${d.id})" title="Approve &amp; send" style="color:#4ade80;">
              <i class="fa-regular fa-paper-plane"></i>
            </button>
            <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.rejectDraft(${d.id})" title="Reject" style="color:#f87171;">
              <i class="fa-regular fa-xmark"></i>
            </button>` : ''}
        </td>
      </tr>`).join('');
  },

  openDraftModal(id) {
    const d = (this._data.outreach?.items || []).find(x => x.id === id);
    if (!d) return;
    const editable = d.status === 'draft';
    this.openModal('outreachDraftModal', `
      <h3 style="color:var(--white);margin-bottom:var(--space-lg);">Outreach Draft</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-md);margin-bottom:var(--space-lg);">
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">To</div><div>${this.esc(d.target_name || '—')} &lt;${this.esc(d.target_email || '')}&gt;</div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Company</div><div>${this.esc(d.company || '—')}</div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Type</div><div><span class="${this.badge(d.target_type)}">${this.esc(d.target_type)}</span></div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Status</div><div><span class="${this.badge(d.status)}">${this.esc(d.status)}</span></div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Channel</div><div>${this.esc(d.channel || '—')}</div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Language</div><div>${this.esc(d.language || '—')}</div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">AI Model</div><div>${this.esc(d.ai_model || '—')}</div></div>
        <div><div style="font-size:var(--font-size-xs);color:var(--navy-300);margin-bottom:4px;">Created</div><div>${this.formatDate(d.created_at)}</div></div>
      </div>
      <div class="form-group">
        <label>Subject</label>
        <input type="text" id="draftSubject" value="${this.esc(d.subject || '')}" ${editable ? '' : 'disabled'}>
      </div>
      <div class="form-group">
        <label>Body</label>
        <textarea id="draftBody" rows="10" style="width:100%;background:rgba(6,13,26,0.6);border:1px solid rgba(74,111,159,0.3);border-radius:var(--radius-md);color:var(--white);padding:0.75rem;font-family:var(--font-primary);font-size:var(--font-size-sm);resize:vertical;box-sizing:border-box;" ${editable ? '' : 'disabled'}>${this.esc(d.body || '')}</textarea>
      </div>
      <div style="display:flex;gap:var(--space-md);margin-top:var(--space-lg);flex-wrap:wrap;">
        ${editable ? `
          <button class="btn btn-ghost-secondary" onclick="Admin.saveDraft(${d.id})"><i class="fa-regular fa-floppy-disk"></i> Save</button>
          <button class="btn btn-primary" onclick="Admin.approveDraft(${d.id})"><i class="fa-regular fa-paper-plane"></i> Approve &amp; Send</button>
          <button class="btn btn-ghost-secondary" onclick="Admin.rejectDraft(${d.id})" style="color:#f87171;"><i class="fa-regular fa-xmark"></i> Reject</button>` : ''}
        <button class="btn btn-ghost-secondary" onclick="Admin.closeModal()">Close</button>
      </div>
    `);
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
    if (btn) { btn.disabled = true; btn.dataset.origText = btn.innerHTML; btn.innerHTML = '<i class="fa-regular fa-spinner fa-spin"></i>'; }
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

  /* ============================================================
     BLOG
     ============================================================ */
  async loadBlog(params = {}) {
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
      this.renderPagination('blogPagination', data.total, limit, this._currentPage.blog, (p) => {
        this._currentPage.blog = p;
        this.loadBlog(params);
      });
    } catch (err) {
      this.setEmpty('#section-blog table tbody', 6, 'Failed to load blog posts');
      console.error(err);
    }
  },

  renderBlog(data) {
    const tbody = document.querySelector('#section-blog table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#section-blog table tbody', 6, 'No blog posts found'); return; }
    tbody.innerHTML = items.map(p => {
      const tags = Array.isArray(p.tags) ? p.tags.join(', ') : (p.tags || '—');
      return `
      <tr>
        <td style="font-weight:600;color:var(--white);">${this.esc(p.title_nl || '—')}</td>
        <td style="color:var(--navy-200);font-size:var(--font-size-xs);">${this.esc(p.slug)}</td>
        <td style="color:var(--navy-200);font-size:var(--font-size-xs);">${this.esc(tags)}</td>
        <td><span class="${this.badge(p.status)}">${this.esc(p.status)}</span></td>
        <td style="font-size:var(--font-size-xs);color:var(--navy-300);">${p.published_at ? this.formatDate(p.published_at) : '—'}</td>
        <td>
          <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.openBlogModal(${p.id})" title="Edit">
            <i class="fa-regular fa-pen"></i>
          </button>
          ${p.status === 'draft' ? `
            <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.publishBlogPost(${p.id})" title="Publish" style="color:#4ade80;">
              <i class="fa-regular fa-circle-check"></i>
            </button>` : ''}
          ${p.status === 'published' ? `
            <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.archiveBlogPost(${p.id})" title="Archive" style="color:#f87171;">
              <i class="fa-regular fa-box-archive"></i>
            </button>` : ''}
        </td>
      </tr>`;
    }).join('');
  },

  openBlogModal(id) {
    const p = id ? (this._data.blog?.items || []).find(x => x.id === id) : null;
    this.openModal('blogModal', `
      <h3 style="color:var(--white);margin-bottom:var(--space-lg);">${p ? 'Edit Post' : 'New Post'}</h3>
      <div class="form-group">
        <label>Slug</label>
        <input type="text" id="blogSlug" value="${this.esc(p?.slug || '')}">
      </div>
      <div class="form-group">
        <label>Title (NL)</label>
        <input type="text" id="blogTitleNl" value="${this.esc(p?.title_nl || '')}">
      </div>
      <div class="form-group">
        <label>Title (EN)</label>
        <input type="text" id="blogTitleEn" value="${this.esc(p?.title_en || '')}">
      </div>
      <div class="form-group">
        <label>Excerpt (NL)</label>
        <textarea id="blogExcerptNl" rows="3" style="width:100%;background:rgba(6,13,26,0.6);border:1px solid rgba(74,111,159,0.3);border-radius:var(--radius-md);color:var(--white);padding:0.75rem;font-family:var(--font-primary);font-size:var(--font-size-sm);resize:vertical;box-sizing:border-box;">${this.esc(p?.excerpt_nl || '')}</textarea>
      </div>
      <div class="form-group">
        <label>Excerpt (EN)</label>
        <textarea id="blogExcerptEn" rows="3" style="width:100%;background:rgba(6,13,26,0.6);border:1px solid rgba(74,111,159,0.3);border-radius:var(--radius-md);color:var(--white);padding:0.75rem;font-family:var(--font-primary);font-size:var(--font-size-sm);resize:vertical;box-sizing:border-box;">${this.esc(p?.excerpt_en || '')}</textarea>
      </div>
      <div class="form-group">
        <label>Body HTML (NL)</label>
        <textarea id="blogBodyNl" rows="10" style="width:100%;background:rgba(6,13,26,0.6);border:1px solid rgba(74,111,159,0.3);border-radius:var(--radius-md);color:var(--white);padding:0.75rem;font-family:var(--font-primary);font-size:var(--font-size-sm);resize:vertical;box-sizing:border-box;">${this.esc(p?.body_nl || '')}</textarea>
      </div>
      <div class="form-group">
        <label>Body HTML (EN)</label>
        <textarea id="blogBodyEn" rows="10" style="width:100%;background:rgba(6,13,26,0.6);border:1px solid rgba(74,111,159,0.3);border-radius:var(--radius-md);color:var(--white);padding:0.75rem;font-family:var(--font-primary);font-size:var(--font-size-sm);resize:vertical;box-sizing:border-box;">${this.esc(p?.body_en || '')}</textarea>
      </div>
      <div class="form-group">
        <label>Tags (comma-separated)</label>
        <input type="text" id="blogTags" value="${this.esc(Array.isArray(p?.tags) ? p.tags.join(', ') : (p?.tags || ''))}">
      </div>
      <div class="form-group">
        <label>Read time (min)</label>
        <input type="number" id="blogReadTime" value="${p?.read_time_min ?? ''}">
      </div>
      <div style="display:flex;gap:var(--space-md);margin-top:var(--space-lg);">
        <button class="btn btn-primary" onclick="Admin.saveBlogPost(${p ? p.id : 'null'})">Save</button>
        <button class="btn btn-ghost-secondary" onclick="Admin.closeModal()">Cancel</button>
      </div>
    `);
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

  /* ============================================================
     ANALYTICS
     ============================================================ */
  async loadAnalytics() {
    const container = document.getElementById('analyticsContent');
    if (container) container.innerHTML = '<div style="text-align:center;padding:3rem;color:var(--navy-300);"><i class="fa-regular fa-spinner fa-spin"></i> Loading analytics…</div>';
    try {
      const res = await Auth.fetch('/v1/admin/analytics');
      if (!res?.ok) throw new Error('Failed');
      const data = await res.json();
      this._data.analytics = data;
      this.renderAnalytics(data);
    } catch {
      if (container) container.innerHTML = '<div style="text-align:center;padding:3rem;color:#f87171;">Failed to load analytics</div>';
    }
  },

  renderAnalytics(data) {
    document.getElementById('kpiJobFillRate').textContent = (data.job_fill_rate ?? 0) + '%';
    document.getElementById('kpiClientRetention').textContent = (data.client_retention_rate ?? 0) + '%';
    document.getElementById('kpiCandidatePlacement').textContent = (data.candidate_satisfaction ?? 0) + '%';

    const growthEl = document.getElementById('userGrowthChart');
    if (growthEl && data.user_growth) {
      const entries = Object.entries(data.user_growth).sort(([a], [b]) => a.localeCompare(b));
      if (!entries.length) { growthEl.innerHTML = '<div style="color:var(--navy-300);font-size:var(--font-size-sm);">No data yet</div>'; return; }

      if (window.ApexCharts) {
        growthEl.innerHTML = '';
        growthEl.style.display = '';
        const labels = entries.map(([month]) => new Date(month).toLocaleDateString('en-GB', { month: 'short' }));
        const values = entries.map(([, count]) => count);
        if (this._growthChart) { this._growthChart.destroy(); this._growthChart = null; }
        this._growthChart = new ApexCharts(growthEl, {
          chart: { type: 'bar', height: 200, background: 'transparent', toolbar: { show: false } },
          series: [{ name: 'Users', data: values }],
          xaxis: { categories: labels, axisBorder: { show: false }, axisTicks: { show: false } },
          colors: ['#E8B400'],
          plotOptions: { bar: { borderRadius: 4, columnWidth: '55%' } },
          dataLabels: { enabled: false },
          grid: { borderColor: 'rgba(255,255,255,0.06)' },
          theme: { mode: 'dark' },
        });
        this._growthChart.render();
      } else {
        const max = Math.max(...entries.map(([, v]) => v), 1);
        growthEl.innerHTML = `<div style="display:flex;align-items:flex-end;gap:6px;height:120px;width:100%;">
          ${entries.map(([month, count]) => {
            const h = Math.round((count / max) * 110);
            const label = new Date(month).toLocaleDateString('en-GB', { month: 'short' });
            return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;">
              <div style="font-size:9px;color:var(--navy-300);">${count}</div>
              <div style="width:100%;border-radius:4px 4px 0 0;background:var(--gold-gradient);height:${h}px;"></div>
              <div style="font-size:9px;color:var(--navy-300);">${label}</div>
            </div>`;
          }).join('')}
        </div>`;
      }
    }
  },

  /* ============================================================
     AUDIT LOG
     ============================================================ */
  async loadAuditLog(params = {}) {
    const qs = new URLSearchParams();
    const limit = this._pageSize;
    const offset = ((this._currentPage.audit || 1) - 1) * limit;
    if (params.action) qs.set('action', params.action);
    qs.set('limit', limit);
    qs.set('offset', offset);

    this.setLoading('#section-audit table tbody', 4);
    try {
      const res = await Auth.fetch(`/v1/admin/audit-log?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.audit = data;
      this.renderAuditLog(data);
      this.renderPagination('auditPagination', data.total, limit, this._currentPage.audit, (p) => {
        this._currentPage.audit = p;
        this.loadAuditLog(params);
      });
    } catch {
      this.setEmpty('#section-audit table tbody', 4, 'Failed to load audit log');
    }
  },

  renderAuditLog(data) {
    const tbody = document.querySelector('#section-audit table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) { this.setEmpty('#section-audit table tbody', 4, 'No audit entries'); return; }
    const colors = { user_delete: '#f87171', impersonate: '#fb923c', settings_update: '#a78bfa' };
    tbody.innerHTML = items.map(e => `
      <tr>
        <td style="font-size:var(--font-size-xs);color:var(--navy-300);white-space:nowrap;">${this.formatDate(e.created_at)}</td>
        <td><span style="color:${colors[e.action] || 'var(--gold-400)'};">${this.esc(e.action?.replace(/_/g, ' '))}</span></td>
        <td style="font-size:var(--font-size-xs);color:var(--navy-200);">${this.esc(e.actor_email || 'system')}</td>
        <td style="font-size:var(--font-size-xs);color:var(--navy-300);">${this.esc(e.target_type ? e.target_type + ' #' + e.target_id : '—')}</td>
      </tr>`).join('');
  },

  /* ============================================================
     SETTINGS
     ============================================================ */
  async loadSettings() {
    try {
      const res = await Auth.fetch('/v1/admin/settings');
      if (!res?.ok) return;
      const rows = await res.json();
      this._data.settings = rows;
      rows.forEach(s => {
        const el = document.getElementById(`setting_${s.key}`);
        if (el) {
          if (el.type === 'checkbox') el.checked = s.value === 'true';
          else el.value = s.value || '';
        }
      });
    } catch { console.error('Settings load error'); }
  },

  async saveSettings() {
    const btn = document.getElementById('saveSettingsBtn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-regular fa-spinner fa-spin"></i> Saving…'; }
    const settings = {};
    document.querySelectorAll('[data-setting-key]').forEach(el => {
      settings[el.dataset.settingKey] = el.type === 'checkbox' ? String(el.checked) : el.value;
    });
    try {
      const res = await Auth.fetch('/v1/admin/settings', {
        method: 'PUT', body: JSON.stringify({ settings }),
      });
      if (res?.ok) Auth.toast('Settings saved', 'success');
      else Auth.toast('Failed to save settings', 'error');
    } catch { Auth.toast('Network error', 'error'); }
    finally { if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-regular fa-floppy-disk"></i> Save Settings'; } }
  },

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
    if (!rows.length) { el.innerHTML = '<div style="color:var(--navy-300);padding:1rem;">No content items found</div>'; return; }
    el.innerHTML = rows.map(item => `
      <div style="display:flex;align-items:center;gap:var(--space-md);padding:var(--space-md) 0;border-bottom:1px solid rgba(74,111,159,0.08);">
        <div style="flex:1;">
          <div style="font-size:var(--font-size-xs);color:var(--navy-300);">${this.esc(item.section)} / ${this.esc(item.key)}</div>
          <div style="color:var(--navy-100);margin-top:2px;font-size:var(--font-size-sm);">${this.esc((item.value || '').slice(0, 80))}${(item.value || '').length > 80 ? '…' : ''}</div>
        </div>
        <button class="btn btn-sm btn-ghost-secondary" onclick="Admin.editContent(${item.id}, '${this.esc(item.key)}', \`${this.esc(item.value || '')}\`)">
          <i class="fa-regular fa-pen"></i>
        </button>
      </div>`).join('');
  },

  editContent(id, key, value) {
    this.openModal('editContentModal', `
      <h3 style="color:var(--white);margin-bottom:var(--space-lg);">Edit: ${this.esc(key)}</h3>
      <div class="form-group">
        <label>Value</label>
        <textarea id="editContentValue" rows="5" style="width:100%;background:rgba(6,13,26,0.6);border:1px solid rgba(74,111,159,0.3);border-radius:var(--radius-md);color:var(--white);padding:0.75rem;font-family:var(--font-primary);font-size:var(--font-size-sm);resize:vertical;">${this.esc(value)}</textarea>
      </div>
      <div style="display:flex;gap:var(--space-md);margin-top:var(--space-lg);">
        <button class="btn btn-primary" onclick="Admin.saveContent(${id})">Save</button>
        <button class="btn btn-ghost-secondary" onclick="Admin.closeModal()">Cancel</button>
      </div>
    `);
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

  /* ============================================================
     PAGINATION
     ============================================================ */
  renderPagination(containerId, total, limit, current, onPage) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const pages = Math.ceil(total / limit);
    if (pages <= 1) { el.innerHTML = ''; return; }

    const buttons = [];
    buttons.push(`<button ${current === 1 ? 'disabled' : ''} onclick="(${onPage.toString()})(${current - 1})"><i class="fa-regular fa-chevron-left"></i></button>`);
    for (let i = 1; i <= Math.min(pages, 7); i++) {
      buttons.push(`<button class="${i === current ? 'active' : ''}" onclick="(${onPage.toString()})(${i})">${i}</button>`);
    }
    if (pages > 7) buttons.push(`<span style="color:var(--navy-300);padding:0 4px;">…${pages}</span>`);
    buttons.push(`<button ${current === pages ? 'disabled' : ''} onclick="(${onPage.toString()})(${current + 1})"><i class="fa-regular fa-chevron-right"></i></button>`);
    el.innerHTML = buttons.join('');
  },

  /* ============================================================
     MODAL
     ============================================================ */
  openModal(id, html) {
    let overlay = document.getElementById('adminModalOverlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'adminModalOverlay';
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:999;display:flex;align-items:center;justify-content:center;padding:1rem;backdrop-filter:blur(4px);';
      overlay.addEventListener('click', e => { if (e.target === overlay) this.closeModal(); });
      document.body.appendChild(overlay);
    }
    overlay.innerHTML = `
      <div style="background:var(--navy-900);border:1px solid rgba(74,111,159,0.2);border-radius:var(--radius-xl);padding:var(--space-2xl);max-width:520px;width:100%;max-height:80vh;overflow-y:auto;position:relative;">
        <button onclick="Admin.closeModal()" style="position:absolute;top:1rem;right:1rem;background:none;border:none;color:var(--navy-200);cursor:pointer;font-size:1.2rem;">
          <i class="fa-regular fa-xmark"></i>
        </button>
        ${html}
      </div>`;
    overlay.style.display = 'flex';
  },

  closeModal() {
    const overlay = document.getElementById('adminModalOverlay');
    if (overlay) overlay.style.display = 'none';
  },

  /* ============================================================
     SECTION FILTER BINDING
     ============================================================ */
  bindFilters() {
    const debouncedUsers = debounce(val => this.loadUsers({ search: val }), 400);
    document.querySelectorAll('#section-users .search-bar input').forEach(el => {
      el.addEventListener('input', e => debouncedUsers(e.target.value));
    });

    const roleSelect = document.getElementById('userRoleFilter');
    if (roleSelect) roleSelect.addEventListener('change', e => {
      const v = e.target.value;
      this.loadUsers({ role: ['candidate','client','admin'].includes(v) ? v : '' });
    });

    const statusSelect = document.getElementById('userStatusFilter');
    if (statusSelect) statusSelect.addEventListener('change', e => {
      const v = e.target.value;
      this.loadUsers({ status: ['verified','unverified'].includes(v) ? v : '' });
    });

    const debouncedCandidates = debounce(val => this.loadCandidates({ search: val }), 400);
    document.querySelectorAll('#section-candidates .search-bar input').forEach(el => {
      el.addEventListener('input', e => debouncedCandidates(e.target.value));
    });

    const jobStatusFilter = document.getElementById('jobStatusFilter');
    if (jobStatusFilter) jobStatusFilter.addEventListener('change', e => {
      const v = e.target.value;
      this.loadJobs({ status: ['open','closed','draft'].includes(v) ? v : '' });
    });

    document.addEventListener('click', () => this.closeMenus());
  },
};

function debounce(fn, delay) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
}

document.addEventListener('DOMContentLoaded', () => {
  Admin.init();
  Admin.bindFilters();
});
