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

  /* ---- Cookie Consent Check ---- */
  hasCookieConsent() {
    return localStorage.getItem('gsp_cookie_consent') === 'true';
  },

  /* ---- Modal focus trap: keyboard-only users can't tab out, Escape closes ---- */
  trapFocus(modalEl, triggerEl) {
    if (!modalEl) return;
    const focusables = modalEl.querySelectorAll(
      'input:not([disabled]), button:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]'
    );
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    first.focus();

    const handleKey = (e) => {
      if (e.key === 'Escape') {
        modalEl.classList.remove('active');
        this.releaseFocusTrap(modalEl, triggerEl);
        return;
      }
      if (e.key !== 'Tab') return;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    modalEl.addEventListener('keydown', handleKey);
    modalEl._focusTrapHandler = handleKey;
    modalEl._focusTrapTrigger = triggerEl;
  },

  releaseFocusTrap(modalEl, triggerEl) {
    if (!modalEl) return;
    if (modalEl._focusTrapHandler) {
      modalEl.removeEventListener('keydown', modalEl._focusTrapHandler);
      modalEl._focusTrapHandler = null;
    }
    const returnTo = triggerEl || modalEl._focusTrapTrigger;
    if (returnTo && typeof returnTo.focus === 'function') returnTo.focus();
  },

  /* ---- Get stored token ---- */
  getToken() {
    if (!this.hasCookieConsent()) return null;
    return localStorage.getItem(this.TOKEN_KEY);
  },

  /* ---- Get stored user ---- */
  getUser() {
    if (!this.hasCookieConsent()) return null;
    try {
      const raw = localStorage.getItem(this.USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },

  /* ---- Set auth data (with cookie consent check) ---- */
  setAuth(token, user) {
    if (!this.hasCookieConsent()) {
      this.toast('Please accept cookies to use authentication.', 'warning');
      return false;
    }
    localStorage.setItem(this.TOKEN_KEY, token);
    localStorage.setItem(this.USER_KEY, JSON.stringify(user));
    return true;
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

    // Fix double-slash: ensure no double slashes between API base and url
    const cleanUrl = url.startsWith('/') ? url : '/' + url;
    const fullUrl = url.startsWith('http') ? url : `${this.API}${cleanUrl}`;

    try {
      const response = await fetch(fullUrl, {
        ...options,
        headers
      });

      if (response.status === 401 && token) {
        // Only treat 401 as "session expired" when we actually sent a token.
        // Unauthenticated calls (login/register/forgot-password) return 401
        // for bad credentials and must be handled by the caller, not redirected.
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

  /* ---- Form Validation ---- */
  validateEmail(email) {
    if (!email || !email.trim()) return 'Email is required.';
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!re.test(email.trim())) return 'Please enter a valid email address.';
    return '';
  },

  validatePassword(password) {
    if (!password) return 'Password is required.';
    if (password.length < 8) return 'Password must be at least 8 characters.';
    if (!/[A-Z]/.test(password)) return 'Password must contain an uppercase letter.';
    if (!/[a-z]/.test(password)) return 'Password must contain a lowercase letter.';
    if (!/[0-9]/.test(password)) return 'Password must contain a number.';
    return '';
  },

  validateName(name) {
    if (!name || !name.trim()) return 'Name is required.';
    if (name.trim().length < 2) return 'Name must be at least 2 characters.';
    return '';
  },

  /* ---- Password Strength Indicator ---- */
  getPasswordStrength(password) {
    if (!password) return { score: 0, label: '', class: '' };
    let score = 0;
    if (password.length >= 8) score += 20;
    if (password.length >= 12) score += 10;
    if (/[A-Z]/.test(password)) score += 20;
    if (/[a-z]/.test(password)) score += 10;
    if (/[0-9]/.test(password)) score += 15;
    if (/[^A-Za-z0-9]/.test(password)) score += 15;
    if (password.length >= 16) score += 10;

    let label, cls;
    if (score >= 90) { label = 'Very Strong'; cls = 'strength-very-strong'; }
    else if (score >= 70) { label = 'Strong'; cls = 'strength-strong'; }
    else if (score >= 50) { label = 'Fair'; cls = 'strength-fair'; }
    else if (score >= 30) { label = 'Weak'; cls = 'strength-weak'; }
    else { label = 'Very Weak'; cls = 'strength-very-weak'; }

    return { score, label, class: cls };
  },

  /* ---- Login ---- */
  async login(email, password) {
    const emailErr = this.validateEmail(email);
    if (emailErr) return { error: emailErr };
    const pwErr = this.validatePassword(password);
    if (pwErr) return { error: pwErr };

    const res = await this.fetch('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email: email.trim(), password })
    });
    if (!res) return { error: 'Network error. Please try again.' };
    const data = await res.json();
    if (!res.ok) return { error: data.detail || 'Login failed. Check your credentials.' };
    const saved = this.setAuth(data.access_token, data.user);
    if (!saved) return { error: 'Cookie consent required.' };
    return { user: data.user };
  },

  /* ---- Register ---- */
  async register(data) {
    const nameErr = this.validateName(data.full_name);
    if (nameErr) return { error: nameErr };
    const emailErr = this.validateEmail(data.email);
    if (emailErr) return { error: emailErr };
    const pwErr = this.validatePassword(data.password);
    if (pwErr) return { error: pwErr };
    if (!data.avg_consent) return { error: 'You must accept the AVG privacy policy.' };

    const res = await this.fetch('/auth/register', {
      method: 'POST',
      body: JSON.stringify({
        email: data.email.trim(),
        password: data.password,
        full_name: data.full_name.trim(),
        role: data.role || 'candidate'
      })
    });
    if (!res) return { error: 'Network error. Please try again.' };
    const result = await res.json();
    if (!res.ok) return { error: result.detail || 'Registration failed. Please try again.' };
    const saved = this.setAuth(result.access_token, result.user);
    if (!saved) return { error: 'Cookie consent required.' };
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

  /* ---- OAuth Handlers ---- */
  handleOAuthLogin(provider) {
    if (String(provider).toLowerCase().includes('google')) {
      window.location.href = `${this.API}/auth/google/login`;
      return;
    }
    this.toast(`${provider} login is not available`, 'info');
  },

  /* ---- Show toast notification ---- */
  toast(message, type = 'success') {
    let container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      container.setAttribute('aria-live', 'polite');
      container.setAttribute('aria-label', 'Notifications');
      document.body.appendChild(container);
    }

    const icons = {
      success: 'fa-circle-check',
      error: 'fa-circle-xmark',
      warning: 'fa-triangle-exclamation',
      info: 'fa-circle-info'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
      <span class="toast-icon"><i class="fa-regular ${icons[type] || icons.success}"></i></span>
      <span>${message}</span>
    `;
    container.appendChild(toast);

    // Trigger entrance animation
    requestAnimationFrame(() => {
      toast.classList.add('toast-visible');
    });

    setTimeout(() => {
      toast.classList.remove('toast-visible');
      toast.classList.add('toast-removing');
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  },

  /* ---- Show Forgot Password Modal ---- */
  showForgotPassword() {
    const modal = document.getElementById('forgotPasswordModal');
    const authModal = document.getElementById('authModal');
    if (!modal) {
      this.toast('Forgot password feature coming soon!', 'info');
      return;
    }
    if (authModal) authModal.classList.remove('active');
    modal.classList.add('active');

    const closeBtn = document.getElementById('forgotPwClose');
    const form = document.getElementById('forgotPwForm');
    const email = document.getElementById('forgotPwEmail');
    const errEl = document.getElementById('forgotPwError');
    const successEl = document.getElementById('forgotPwSuccess');
    const triggerEl = document.getElementById('forgotPwLink');

    if (errEl) errEl.textContent = '';
    if (errEl) errEl.style.display = 'none';
    if (successEl) successEl.textContent = '';
    if (successEl) successEl.style.display = 'none';

    const closeHandler = () => {
      modal.classList.remove('active');
      this.releaseFocusTrap(modal, triggerEl);
    };
    const overlayHandler = (e) => { if (e.target === modal) closeHandler(); };
    this.trapFocus(modal, triggerEl);

    // Clean up old listeners by cloning
    const newCloseBtn = closeBtn.cloneNode(true);
    if (closeBtn && closeBtn.parentNode) {
      closeBtn.parentNode.replaceChild(newCloseBtn, closeBtn);
    }
    newCloseBtn.addEventListener('click', closeHandler);
    modal.addEventListener('click', overlayHandler);

    const submitHandler = async (e) => {
      e.preventDefault();
      const val = email?.value?.trim();
      if (!val || !val.includes('@')) {
        if (errEl) {
          errEl.textContent = 'Please enter a valid email address.';
          errEl.style.display = 'block';
        }
        return;
      }
      if (errEl) errEl.style.display = 'none';
      if (successEl) successEl.style.display = 'none';

      // Show loading
      const submitBtn = form?.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-sm"></span> Sending...';
      }

      try {
        // Use the Auth fetch method (avoids double-slash issues)
        const res = await fetch(`${this.API}/auth/forgot-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: val }),
        });
        if (res.ok) {
          if (successEl) {
            successEl.textContent = 'If that email exists, a reset link has been sent.';
            successEl.style.display = 'block';
          }
          this.toast('Reset link sent if the email exists.', 'success');
          setTimeout(closeHandler, 2500);
        } else {
          const d = await res.json();
          if (errEl) {
            errEl.textContent = d.detail || 'Error sending reset link.';
            errEl.style.display = 'block';
          }
        }
      } catch (err) {
        if (errEl) {
          errEl.textContent = 'Network error. Please try again.';
          errEl.style.display = 'block';
        }
        this.toast('Network error. Please try again.', 'error');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = 'Send Reset Link';
        }
      }
    };

    // Replace form to avoid duplicate listeners
    const newForm = form.cloneNode(true);
    if (form && form.parentNode) {
      form.parentNode.replaceChild(newForm, form);
    }
    newForm.addEventListener('submit', submitHandler);
  }
};