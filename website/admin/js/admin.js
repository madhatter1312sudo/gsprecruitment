/* ============================================================
   GSP Recruitment — admin.js
   Admin portal API integration with FastAPI backend
   Uses Auth.fetch() from ../auth.js for authenticated requests
   ============================================================ */

const Admin = {
  /* ---- Cache ---- */
  _data: {},

  /* ---- Init: load all sections ---- */
  async init() {
    const user = Auth.requireAuth(['admin']);
    if (!user) return;

    // Set user info in sidebar
    const name = user.full_name || 'Admin';
    const email = user.email || 'admin@gsptalent.com';
    const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
    document.getElementById('sidebarName').textContent = name;
    document.getElementById('sidebarEmail').textContent = email;
    document.getElementById('sidebarAvatar').textContent = initials;

    // Kick off data loads in parallel
    await Promise.all([
      this.loadDashboard(),
      this.loadUsers(),
      this.loadJobs(),
      this.loadCandidates(),
      this.loadAuditLog(),
    ]);
  },

  /* ---- Helpers ---- */

  formatDate(dateStr) {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
  },

  timeAgo(dateStr) {
    if (!dateStr) return '';
    const now = new Date();
    const d = new Date(dateStr);
    const diffMs = now - d;
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return this.formatDate(dateStr);
  },

  badge(status) {
    const map = {
      'active': 'badge-green',
      'open': 'badge-green',
      'placed': 'badge-blue',
      'pending': 'badge-blue',
      'suspended': 'badge-red',
      'closed': 'badge-red',
      'draft': 'badge',
      'verified': 'badge-green',
      'unverified': 'badge-blue',
    };
    return map[status?.toLowerCase()] || 'badge';
  },

  escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  },

  /* ============================================================
     DASHBOARD
     ============================================================ */
  async loadDashboard() {
    try {
      const res = await Auth.fetch('/v1/admin/dashboard');
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load dashboard');

      document.getElementById('kpiTotalUsers').textContent = data.total_users ?? '0';
      document.getElementById('kpiActiveJobs').textContent = data.active_jobs ?? '0';
      document.getElementById('kpiCandidates').textContent = data.registered_candidates ?? '0';
      document.getElementById('kpiClients').textContent = data.active_clients ?? '0';
      document.getElementById('kpiPlacements').textContent = data.placements_this_week ?? '0';

      this._data.dashboard = data;
    } catch (err) {
      console.error('Dashboard load error:', err);
    }
  },

  /* ============================================================
     USERS
     ============================================================ */
  async loadUsers(params = {}) {
    const qs = new URLSearchParams();
    if (params.role) qs.set('role', params.role);
    if (params.status) qs.set('status', params.status);
    if (params.search) qs.set('search', params.search);
    const query = qs.toString();

    try {
      const res = await Auth.fetch(`/v1/admin/users${query ? '?' + query : ''}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load users');

      this._data.users = data;
      this.renderUsers(data);
    } catch (err) {
      console.error('Users load error:', err);
    }
  },

  renderUsers(data) {
    const tbody = document.querySelector('#section-users table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--navy-300);padding:2rem;">No users found</td></tr>';
      return;
    }
    tbody.innerHTML = items.map(u => `
      <tr>
        <td style="font-weight:600;color:var(--white);">${this.escapeHtml(u.full_name || '—')}</td>
        <td style="color:var(--navy-200);">${this.escapeHtml(u.email)}</td>
        <td><span class="badge ${this.badge(u.role)}">${this.escapeHtml(u.role)}</span></td>
        <td><span class="badge ${this.badge(u.is_verified ? 'verified' : 'unverified')}">${u.is_verified ? 'Verified' : 'Unverified'}</span></td>
        <td style="font-size:var(--font-size-xs);color:var(--navy-300);">${this.timeAgo(u.created_at)}</td>
        <td>
          <button class="btn btn-sm btn-ghost" style="color:var(--navy-200);"
                  onclick="Admin.showUserActions(${u.id}, '${this.escapeHtml(u.full_name || '')}', '${u.email}', '${u.role}')">
            <i class="fa-regular fa-ellipsis-vertical"></i>
          </button>
        </td>
      </tr>
    `).join('');
  },

  showUserActions(id, name, email, role) {
    Auth.toast(`User: ${name} (${email}) — Role: ${role}`, 'warning');
  },

  /* ============================================================
     JOBS
     ============================================================ */
  async loadJobs(params = {}) {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    const query = qs.toString();

    try {
      const res = await Auth.fetch(`/v1/admin/jobs${query ? '?' + query : ''}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load jobs');

      this._data.jobs = data;
      this.renderJobs(data);
    } catch (err) {
      console.error('Jobs load error:', err);
    }
  },

  renderJobs(data) {
    const tbody = document.querySelector('#section-jobs table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--navy-300);padding:2rem;">No jobs found</td></tr>';
      return;
    }
    tbody.innerHTML = items.map(j => `
      <tr>
        <td style="font-weight:600;color:var(--white);">${this.escapeHtml(j.title || 'Untitled')}</td>
        <td>${this.escapeHtml(j.company_name || '—')}</td>
        <td>${j.application_count ?? '—'}</td>
        <td><span class="badge ${this.badge(j.status)}">${this.escapeHtml(j.status || 'draft')}</span></td>
        <td>
          <button class="btn btn-sm btn-outline" onclick="Admin.toggleFeatured(${j.id})" title="Toggle featured">
            <i class="fa-regular fa-star"></i>
          </button>
          <button class="btn btn-sm btn-ghost" onclick="Admin.showJobActions(${j.id})">
            <i class="fa-regular fa-ellipsis-vertical"></i>
          </button>
        </td>
      </tr>
    `).join('');
  },

  showJobActions(id) {
    Auth.toast(`Job #${id} — Actions: Edit, Approve, Close`, 'warning');
  },

  toggleFeatured(id) {
    Auth.toast(`Job #${id} featured toggled`, 'success');
  },

  /* ============================================================
     CANDIDATES
     ============================================================ */
  async loadCandidates(params = {}) {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.search) qs.set('search', params.search);
    const query = qs.toString();

    try {
      const res = await Auth.fetch(`/v1/admin/candidates${query ? '?' + query : ''}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load candidates');

      this._data.candidates = data;
      this.renderCandidates(data);
    } catch (err) {
      console.error('Candidates load error:', err);
    }
  },

  renderCandidates(data) {
    const tbody = document.querySelector('#section-candidates table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--navy-300);padding:2rem;">No candidates found</td></tr>';
      return;
    }
    tbody.innerHTML = items.map(c => `
      <tr>
        <td style="font-weight:600;color:var(--white);">${this.escapeHtml(c.full_name || '—')}</td>
        <td>${this.escapeHtml(c.email)}</td>
        <td>${this.escapeHtml(c.current_title || '—')}</td>
        <td>${c.years_experience ? c.years_experience + ' yrs' : '—'}</td>
        <td><span class="badge ${this.badge(c.status)}">${this.escapeHtml(c.status || 'active')}</span></td>
        <td>
          <button class="btn btn-sm btn-ghost" onclick="Admin.showCandidateActions(${c.id})">
            <i class="fa-regular fa-ellipsis-vertical"></i>
          </button>
        </td>
      </tr>
    `).join('');
  },

  showCandidateActions(id) {
    Auth.toast(`Candidate #${id} — Actions: View, Edit, Match`, 'warning');
  },

  /* ============================================================
     AUDIT LOG
     ============================================================ */
  async loadAuditLog() {
    try {
      const res = await Auth.fetch('/v1/admin/audit-log?limit=20');
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to load audit log');

      this._data.audit = data;
      this.renderAuditLog(data);
    } catch (err) {
      console.error('Audit log load error:', err);
    }
  },

  renderAuditLog(data) {
    const tbody = document.querySelector('#section-audit table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--navy-300);padding:2rem;">No audit entries found</td></tr>';
      return;
    }
    tbody.innerHTML = items.map(entry => `
      <tr>
        <td style="font-size:var(--font-size-xs);color:var(--navy-300);">${this.formatDate(entry.created_at)}</td>
        <td>${this.escapeHtml(entry.action || '—')}</td>
        <td>${this.escapeHtml(entry.actor_email || '—')}</td>
        <td>${this.escapeHtml(entry.target_type ? entry.target_type + ' #' + entry.target_id : '—')}</td>
      </tr>
    `).join('');
  },

  /* ============================================================
     SEARCH / FILTER BINDING
     ============================================================ */
  bindFilters() {
    // Users search
    const usersSearch = document.querySelector('#section-users .search-bar input');
    if (usersSearch) {
      usersSearch.addEventListener('input', debounce((e) => {
        this.loadUsers({ search: e.target.value });
      }, 400));
    }

    // Jobs search
    const jobsSearch = document.querySelector('#section-jobs .search-bar input');
    if (jobsSearch) {
      jobsSearch.addEventListener('input', debounce((e) => {
        // jobs endpoint uses status filter, no search in the admin/jobs endpoint
        // We'll use a simple client-side filter
      }, 400));
    }

    // Candidates search
    const candidatesSearch = document.querySelector('#section-candidates .search-bar input');
    if (candidatesSearch) {
      candidatesSearch.addEventListener('input', debounce((e) => {
        this.loadCandidates({ search: e.target.value });
      }, 400));
    }

    // Role filter on users
    const roleSelect = document.querySelector('#section-users select:first-of-type');
    if (roleSelect) {
      roleSelect.addEventListener('change', (e) => {
        const val = e.target.value;
        this.loadUsers({ role: val === 'All Roles' || val === 'Alle Rollen' ? '' : val.toLowerCase() });
      });
    }

    // Status filter on users
    const statusSelect = document.querySelector('#section-users select:last-of-type');
    if (statusSelect) {
      statusSelect.addEventListener('change', (e) => {
        const val = e.target.value;
        this.loadUsers({ status: val === 'All Status' || val === 'Alle Statussen' ? '' : val.toLowerCase() });
      });
    }
  },
};

/* ---- Debounce utility ---- */
function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

/* ============================================================
   DOM READY
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {
  Admin.init();
  Admin.bindFilters();
});
