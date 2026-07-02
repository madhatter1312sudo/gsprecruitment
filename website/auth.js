/* ============================================================
   GSP Recruitment — auth.js
   Shared authentication module for all portals
   ============================================================ */

const Auth = {
  /* ---- Storage Keys ---- */
  TOKEN_KEY: 'gsp_token',
  USER_KEY: 'gsp_user',

  /* ---- API Base (no trailing slash) ---- */
  API: 'https://api.gsprecruitment.nl/api',

  /* ---- Get stored token ---- */
  getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  },

  /* ---- Get stored user ---- */
  getUser() {
    try {
      const raw = localStorage.getItem(this.USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },

  /* ---- Set auth data ---- */
  setAuth(token, user) {
    localStorage.setItem(this.TOKEN_KEY, token);
    localStorage.setItem(this.USER_KEY, JSON.stringify(user));
  },

  /* ---- Clear auth data ---- */
  clearAuth() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
  },

  /* ---- Check if logged in ---- */
  isLoggedIn() {
    return !!this.getToken() && !!this.getUser();
  },

  /* ---- Authenticated Fetch ---- */
  async fetch(url, options = {}) {
    const token = this.getToken();
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const fullUrl = url.startsWith('http') ? url : `${this.API}${url}`;

    try {
      const response = await fetch(fullUrl, {
        ...options,
        headers
      });

      if (response.status === 401) {
        this.clearAuth();
        window.location.href = '/';
        return null;
      }

      return response;
    } catch (err) {
      console.error('Auth fetch error:', err);
      throw err;
    }
  },

  /* ---- Parse JWT payload ---- */
  parseJwt(token) {
    try {
      const base64Url = token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => {
        return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
      }).join(''));
      return JSON.parse(jsonPayload);
    } catch {
      return null;
    }
  },

  /* ---- Check token expiry ---- */
  isTokenExpired() {
    const token = this.getToken();
    if (!token) return true;
    const payload = this.parseJwt(token);
    if (!payload || !payload.exp) return true;
    return Date.now() >= payload.exp * 1000;
  },

  /* ---- Login ---- */
  async login(email, password) {
    const res = await this.fetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    if (!res) return { error: 'Network error' };
    const data = await res.json();
    if (!res.ok) return { error: data.detail || 'Login failed' };
    this.setAuth(data.access_token, data.user);
    return { user: data.user };
  },

  /* ---- Register ---- */
  async register(data) {
    const res = await this.fetch('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data)
    });
    if (!res) return { error: 'Network error' };
    const result = await res.json();
    if (!res.ok) return { error: result.detail || 'Registration failed' };
    this.setAuth(result.access_token, result.user);
    return { user: result.user };
  },

  /* ---- Logout ---- */
  logout() {
    this.clearAuth();
    window.location.href = '/';
  },

  /* ---- Get dashboard URL based on role ---- */
  getDashboardUrl(user) {
    if (!user) return '/';
    switch (user.role) {
      case 'candidate': return '/candidate/';
      case 'client': return '/client/';
      case 'admin': return '/admin/';
      default: return '/';
    }
  },

  /* ---- Require auth (call on portal pages) ---- */
  requireAuth(allowedRoles = null) {
    if (!this.isLoggedIn() || this.isTokenExpired()) {
      this.clearAuth();
      window.location.href = '/';
      return null;
    }
    const user = this.getUser();
    if (allowedRoles && !allowedRoles.includes(user.role)) {
      window.location.href = '/';
      return null;
    }
    return user;
  },

  /* ---- Show toast notification ---- */
  toast(message, type = 'success') {
    let container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }

    const icons = {
      success: 'fa-circle-check',
      error: 'fa-circle-xmark',
      warning: 'fa-triangle-exclamation'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <span class="toast-icon"><i class="fa-regular ${icons[type] || icons.success}"></i></span>
      <span>${message}</span>
    `;
    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('toast-removing');
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }
};
