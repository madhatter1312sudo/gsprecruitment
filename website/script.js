// WhatsApp number in E.164 format, digits only (no +), e.g. '31612345678'.
// Leave empty to keep the floating WhatsApp button hidden site-wide.
const GSP_WHATSAPP = '31617913965';

/* ==========================================================================
   GSP Recruitment — Main Application Script
   All features: preloader, lang toggle, hamburger, scroll animations, FAQ,
   auth modal, job board, salary calculator, match quiz, contact form, live stats,
   testimonials carousel, cookie consent, back-to-top
   ========================================================================== */
(() => {
  'use strict';

  const API = 'https://api.gsprecruitment.nl';

  // ── DOM helpers ────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const qs = (sel, ctx) => (ctx || document).querySelector(sel);
  const qsa = (sel, ctx) => (ctx || document).querySelectorAll(sel);

  // ── Language Toggle ────────────────────────────────────
  function initLang() {
    let currentLang = localStorage.getItem('gsp_lang') || 'nl';

    const H1_TEXTS = {
      en: 'We find the engineers that build the future.',
      nl: 'Wij vinden de engineers die de toekomst bouwen.'
    };

    function setLang(lang) {
      currentLang = lang;
      localStorage.setItem('gsp_lang', lang);
      document.documentElement.setAttribute('data-lang', lang);
      document.documentElement.setAttribute('lang', lang);

      document.querySelectorAll('.lang-en, .lang-nl').forEach(el => {
        el.style.display = el.classList.contains('lang-' + lang) ? '' : 'none';
      });

      const heroTitle = $('heroTitle');
      if (heroTitle && H1_TEXTS[lang]) {
        heroTitle.textContent = H1_TEXTS[lang];
      }

      document.querySelectorAll('[data-lang-' + lang + ']').forEach(el => {
        const placeholder = el.getAttribute('data-lang-' + lang);
        if (placeholder && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')) {
          el.setAttribute('placeholder', placeholder);
          // Placeholder text is the only visible label on these compact forms;
          // mirror it into aria-label so it survives once the field has a value.
          el.setAttribute('aria-label', placeholder);
        }
      });

      document.querySelectorAll('.lang-btn').forEach(btn => {
        btn.classList.toggle('active', btn.id === 'lang' + lang.charAt(0).toUpperCase() + lang.slice(1));
      });

      document.querySelectorAll('option[data-lang-' + lang + ']').forEach(opt => {
        opt.textContent = opt.getAttribute('data-lang-' + lang);
      });
    }

    $('langEn')?.addEventListener('click', () => setLang('en'));
    $('langNl')?.addEventListener('click', () => setLang('nl'));
    setLang(currentLang);
  }

  // ── Preloader ──────────────────────────────────────────
  function initPreloader() {
    const preloader = $('preloader');
    const fill = $('preloaderFill');
    if (!preloader) return;

    let progress = 0;
    let interval = setInterval(() => {
      progress += Math.random() * 8 + 2;
      if (progress >= 95) {
        progress = 95;
        clearInterval(interval);
      }
      if (fill) fill.style.width = progress + '%';
    }, 120);

    window.addEventListener('load', () => {
      clearInterval(interval);
      const finish = () => {
        if (fill) fill.style.width = '100%';
        setTimeout(() => preloader.classList.add('hidden'), 300);
      };
      if (progress >= 90) {
        finish();
      } else {
        const finInterval = setInterval(() => {
          progress += Math.random() * 5 + 2;
          if (progress >= 100) {
            clearInterval(finInterval);
            finish();
          }
          if (fill) fill.style.width = progress + '%';
        }, 80);
      }
    });

    setTimeout(() => {
      clearInterval(interval);
      if (!preloader.classList.contains('hidden')) {
        if (fill) fill.style.width = '100%';
        setTimeout(() => preloader.classList.add('hidden'), 200);
      }
    }, 5000);
  }

  // ── Hamburger Menu ─────────────────────────────────────
  function initHamburger() {
    const hamburger = $('hamburger');
    const nav = $('nav');
    if (!hamburger || !nav) return;

    hamburger.addEventListener('click', () => {
      hamburger.classList.toggle('active');
      nav.classList.toggle('active');
    });

    nav.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', () => {
        hamburger.classList.remove('active');
        nav.classList.remove('active');
      });
    });
  }

  // ── Header Scroll Effect ───────────────────────────────
  function initHeaderScroll() {
    const header = $('header');
    if (!header) return;

    const checkScroll = () => {
      header.classList.toggle('scrolled', window.scrollY > 60);
    };

    window.addEventListener('scroll', checkScroll, { passive: true });
    checkScroll();
  }

  // ── Scroll Animations ──────────────────────────────────
  function initScrollAnimations() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

    document.querySelectorAll('.fade-in, .fade-in-left, .fade-in-right').forEach(el => {
      observer.observe(el);
    });
  }

  // ── FAQ Accordion ──────────────────────────────────────
  function initFAQ() {
    qsa('.faq-question').forEach(btn => {
      btn.addEventListener('click', () => {
        const item = btn.closest('.faq-item');
        const isActive = item.classList.contains('active');
        qsa('.faq-item.active').forEach(i => {
          i.classList.remove('active');
          i.querySelector('.faq-question')?.setAttribute('aria-expanded', 'false');
        });
        if (!isActive) {
          item.classList.add('active');
          btn.setAttribute('aria-expanded', 'true');
        }
      });
    });
  }

  // ── Auth Modal ─────────────────────────────────────────
  function initAuth() {
    const modal = $('authModal');
    const loginBtn = $('loginBtn');
    const registerBtn = $('registerBtn');
    const closeBtn = $('authClose');
    const tabs = qsa('.modal-tab');
    const loginForm = $('loginForm');
    const registerForm = $('registerForm');
    const errEl = $('authError');
    const successEl = $('authSuccess');

    function openModal(tab, triggerEl) {
      if (!modal) return;
      modal.classList.add('active');
      tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
      if (loginForm) loginForm.style.display = tab === 'login' ? 'flex' : 'none';
      if (registerForm) registerForm.style.display = tab === 'register' ? 'flex' : 'none';
      if (errEl) errEl.style.display = 'none';
      if (successEl) successEl.style.display = 'none';
      Auth.trapFocus(modal, triggerEl || document.activeElement);
    }

    function closeAuthModal() {
      modal?.classList.remove('active');
      Auth.releaseFocusTrap(modal);
    }

    // Check logged-in state using Auth module
    if (Auth.isLoggedIn()) {
      const u = Auth.getUser();
      if (loginBtn) {
        const url = Auth.getDashboardUrl(u);
        loginBtn.innerHTML = `<i class="fas fa-columns"></i> <span class="lang-en">Dashboard</span><span class="lang-nl">Dashboard</span>`;
        loginBtn.addEventListener('click', (e) => {
          e.preventDefault();
          window.location.href = url;
        });
      }
    } else {
      loginBtn?.addEventListener('click', (e) => openModal('login', e.currentTarget));
    }

    registerBtn?.addEventListener('click', (e) => openModal('register', e.currentTarget));
    closeBtn?.addEventListener('click', closeAuthModal);
    modal?.addEventListener('click', (e) => { if (e.target === modal) closeAuthModal(); });
    tabs.forEach(tab => tab.addEventListener('click', () => openModal(tab.dataset.tab)));

    // Wire up social login buttons
    const socialBtns = qsa('.social-btns button');
    socialBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        if (btn.querySelector('.fa-google')) {
          window.location.href = `${Auth.API}/auth/google/login`;
          return;
        }
        const provider = btn.textContent.trim() || 'Social';
        Auth.toast(`${provider} login coming soon!`, 'info');
      });
    });

    // Add "Forgot password?" link to login form
    const forgotLink = document.createElement('div');
    forgotLink.style.cssText = 'text-align:right;margin:-8px 0 10px';
    forgotLink.innerHTML = '<a href="#" id="forgotPwLink" style="font-size:0.85rem;color:var(--gold);text-decoration:none"><span class="lang-en">Forgot password?</span><span class="lang-nl">Wachtwoord vergeten?</span></a>';
    const loginSubmitBtn = loginForm?.querySelector('button[type="submit"]');
    if (loginForm && loginSubmitBtn) {
      loginForm.insertBefore(forgotLink, loginSubmitBtn.nextSibling);
    }
    $('forgotPwLink')?.addEventListener('click', (e) => {
      e.preventDefault();
      Auth.showForgotPassword();
    });

    // Login submit — use Auth.login()
    loginForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (errEl) errEl.style.display = 'none';
      if (successEl) successEl.style.display = 'none';

      // Show loading on button
      const submitBtn = loginForm.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-sm"></span> <span class="lang-en">Signing in...</span><span class="lang-nl">Inloggen...</span>';
      }

      try {
        const result = await Auth.login($('loginEmail')?.value, $('loginPassword')?.value);
        if (result.error) {
          if (errEl) { errEl.textContent = result.error; errEl.style.display = 'block'; }
          Auth.toast(result.error, 'error');
        } else {
          closeAuthModal();
          window.location.href = Auth.getDashboardUrl(result.user);
        }
      } catch (err) {
        if (errEl) { errEl.textContent = 'An unexpected error occurred. Please try again.'; errEl.style.display = 'block'; }
        Auth.toast('Login failed. Please try again.', 'error');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="fas fa-sign-in-alt"></i> <span class="lang-en">Sign In</span><span class="lang-nl">Inloggen</span>';
        }
      }
    });

    // Register submit — use Auth.register()
    registerForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (errEl) errEl.style.display = 'none';
      if (successEl) successEl.style.display = 'none';

      const submitBtn = registerForm.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-sm"></span> <span class="lang-en">Creating account...</span><span class="lang-nl">Account aanmaken...</span>';
      }

      try {
        const result = await Auth.register({
          email: $('regEmail')?.value,
          password: $('regPassword')?.value,
          full_name: $('regName')?.value,
          role: $('regRole')?.value || 'candidate',
          avg_consent: $('regAvgConsent')?.checked === true
        });
        if (result.error) {
          if (errEl) { errEl.textContent = result.error; errEl.style.display = 'block'; }
          Auth.toast(result.error, 'error');
        } else {
          Auth.toast('Account created successfully!', 'success');
          closeAuthModal();
          window.location.href = Auth.getDashboardUrl(result.user);
        }
      } catch (err) {
        if (errEl) { errEl.textContent = 'An unexpected error occurred. Please try again.'; errEl.style.display = 'block'; }
        Auth.toast('Registration failed. Please try again.', 'error');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="fas fa-user-plus"></i> <span class="lang-en">Create Account</span><span class="lang-nl">Account aanmaken</span>';
        }
      }
    });
  }

  // ── Job Board ──────────────────────────────────────────
  function initJobBoard() {
    const grid = $('jobsGrid');
    const BASE_URL = window.location.origin;
    const deptFilter = $('deptFilter');
    const levelFilter = $('levelFilter');
    const searchInput = $('searchInput');
    if (!grid) return;

    let allJobs = [];
    let searchTimeout = null;

    function showLoading() {
      grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:60px 20px"><div class="spinner" style="margin:0 auto 16px"></div><p style="color:var(--text-muted)">Loading vacancies...</p></div>';
    }

    function showError(msg) {
      const lang = localStorage.getItem('gsp_lang') || 'nl';
      const text = msg || (lang === 'nl' ? 'Could not load vacancies. Please try again later.' : 'Could not load vacancies. Please try again later.');
      grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:60px 20px"><i class="fas fa-exclamation-triangle" style="font-size:2rem;color:var(--gold);margin-bottom:12px"></i><p>${text}</p><button class="btn btn-ghost btn-sm" onclick="location.reload()" style="margin-top:16px"><i class="fas fa-redo"></i> Retry</button></div>`;
    }

    async function fetchJobs() {
      showLoading();
      try {
        const res = await fetch(`${API}/api/public/jobs`);
        if (res.ok) {
          const data = await res.json();
          if (Array.isArray(data) && data.length > 0) {
            allJobs = data;
          } else {
            allJobs = [];
          }
        } else {
          showError();
          return;
        }
      } catch (e) {
        console.warn('[Jobs] API fetch failed:', e);
        showError('Network error. Please check your connection.');
        return;
      }
      renderJobs();
    }

    function renderJobs() {
      let filtered = [...allJobs];
      const dept = deptFilter?.value || 'all';
      const level = levelFilter?.value || 'all';
      const search = (searchInput?.value || '').toLowerCase().trim();

      if (dept !== 'all') filtered = filtered.filter(j => j.department === dept);
      if (level !== 'all') filtered = filtered.filter(j => j.seniority === level);
      if (search) {
        filtered = filtered.filter(j =>
          (j.title || '').toLowerCase().includes(search) ||
          (j.description || '').toLowerCase().includes(search) ||
          (j.requirements || '').toLowerCase().includes(search)
        );
      }

      if (filtered.length === 0) {
        const lang = localStorage.getItem('gsp_lang') || 'nl';
        const noneAtAll = allJobs.length === 0;
        let emptyMsg;
        if (noneAtAll) {
          emptyMsg = lang === 'nl'
            ? '<p style="font-size:1.15rem;font-weight:600;color:var(--text)">Op dit moment werven we nieuwe rollen</p><p style="margin-top:10px;color:var(--text-secondary)">Stuur je CV in, dan matchen we je zodra de juiste positie binnenkomt.</p><a href="contact.html" class="btn btn-primary" style="margin-top:20px"><i class="fas fa-paper-plane"></i> Stuur je CV in</a>'
            : '<p style="font-size:1.15rem;font-weight:600;color:var(--text)">We\'re currently sourcing new roles</p><p style="margin-top:10px;color:var(--text-secondary)">Send us your CV and we\'ll match you the moment the right position lands.</p><a href="contact.html" class="btn btn-primary" style="margin-top:20px"><i class="fas fa-paper-plane"></i> Submit your CV</a>';
        } else {
          emptyMsg = lang === 'nl'
            ? '<p style="font-size:1.1rem;font-weight:600;color:var(--text)">Geen vacatures voor deze filters</p><p style="margin-top:8px;color:var(--text-muted)">Pas de filters aan om meer rollen te zien.</p>'
            : '<p style="font-size:1.1rem;font-weight:600;color:var(--text)">No roles match these filters</p><p style="margin-top:8px;color:var(--text-muted)">Adjust the filters to see more positions.</p>';
        }
        grid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:60px 20px">${emptyMsg}</div>`;
        return;
      }

      grid.innerHTML = filtered.map(job => `
        <div class="job-card" data-id="${job.id}" data-slug="${job.slug || job.id}">
          <h3>${job.title}</h3>
          <div class="job-tags">
            <span class="job-tag gold">${job.department}</span>
            <span class="job-tag">${job.seniority}</span>
            <span class="job-tag">${job.location_type || 'On-site'}</span>
          </div>
          <p>${job.description || ''}</p>
          <div class="job-meta">
            <span><i class="fas fa-euro-sign"></i> €${(job.salary_min / 1000).toFixed(0)}k – €${(job.salary_max / 1000).toFixed(0)}k</span>
            <span><i class="fas fa-map-marker-alt"></i> ${job.location_type || 'Netherlands'}</span>
          </div>
          <div class="job-links">
            <a href="vacature.html?id=${job.slug || job.id}" class="job-view-link" onclick="event.stopPropagation()"><span class="lang-en">View details →</span><span class="lang-nl">Bekijk details →</span></a>
          </div>
        </div>
      `).join('');

      grid.querySelectorAll('.job-card').forEach(card => {
        card.addEventListener('click', () => showJobDetail(parseInt(card.dataset.id)));
      });
    }

    function showJobDetail(id) {
      const job = allJobs.find(j => j.id === id);
      if (!job) return;
      const modal = $('jobModal');
      const body = $('jobModalBody');
      const user = Auth.getUser();
      if (!body) return;

      body.innerHTML = `
        <h2 style="margin-bottom:8px">${job.title}</h2>
        <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap">
          ${[job.department, job.seniority, job.location_type].map(t => `<span class="job-tag gold" style="font-size:0.8rem;padding:6px 14px">${t}</span>`).join('')}
        </div>
        <div style="background:var(--bg-alt);padding:16px;border-radius:var(--radius-sm);margin-bottom:16px">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
            <div><strong>Salary:</strong> €${(job.salary_min/1000).toFixed(0)}k – €${(job.salary_max/1000).toFixed(0)}k</div>
            <div><strong>Location:</strong> ${job.location_type || 'Netherlands'}</div>
          </div>
        </div>
        <h3 style="font-size:1rem;margin-bottom:8px">Description</h3>
        <p style="font-size:0.92rem;margin-bottom:16px;color:var(--text-secondary)">${job.description || 'No description available.'}</p>
        <h3 style="font-size:1rem;margin-bottom:8px">Requirements</h3>
        <p style="font-size:0.92rem;margin-bottom:24px;color:var(--text-secondary)">${job.requirements || 'No requirements specified.'}</p>
        <button class="btn btn-gold" style="width:100%;justify-content:center" id="applyFromJobBtn">
          <i class="fas fa-paper-plane"></i> Apply Now
        </button>
        <a href="vacature.html?id=${job.slug || job.id}" class="btn btn-ghost" style="width:100%;justify-content:center;margin-top:8px">
          <span class="lang-en">View full page →</span><span class="lang-nl">Bekijk volledige pagina →</span>
        </a>
      `;
      if (modal) modal.classList.add('active');

      $('applyFromJobBtn')?.addEventListener('click', () => {
        if (modal) modal.classList.remove('active');
        if (user) {
          Auth.toast('Application submitted! We will contact you soon.', 'success');
        } else {
          $('authModal')?.classList.add('active');
        }
      });
    }

    // Modal close handlers
    $('jobModalClose')?.addEventListener('click', () => $('jobModal')?.classList.remove('active'));
    $('jobModal')?.addEventListener('click', (e) => { if (e.target === $('jobModal')) $('jobModal').classList.remove('active'); });

    // Filter events
    deptFilter?.addEventListener('change', renderJobs);
    levelFilter?.addEventListener('change', renderJobs);

    // Debounced search input
    searchInput?.addEventListener('input', () => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(renderJobs, 300);
    });

    fetchJobs();
  }

  // ── Homepage Vacancy Module ─────────────────────────────
  function initHomeVacancies() {
    const section = $('homeVacancies');
    const grid = $('homeVacanciesGrid');
    if (!section || !grid) return; // safe no-op on other pages

    fetch(`${API}/api/public/jobs`)
      .then(res => {
        if (!res.ok) throw new Error('bad response');
        return res.json();
      })
      .then(data => {
        if (!Array.isArray(data) || data.length === 0) {
          section.style.display = 'none';
          return;
        }
        const jobs = data.slice(0, 3);
        grid.innerHTML = jobs.map(job => `
          <div class="vac-card">
            <div class="vac-ref">GSP-${job.id}</div>
            <h3>${job.title}</h3>
            <span class="vac-chip">${job.department || ''}</span>
            <div class="vac-meta"><i class="fas fa-map-marker-alt"></i> ${job.location_type || job.location || 'Netherlands'}</div>
            <a href="vacature.html?id=${job.slug || job.id}" class="vac-link"><span class="lang-en">View vacancy →</span><span class="lang-nl">Bekijk vacature →</span></a>
          </div>
        `).join('');
        section.style.display = '';
      })
      .catch(() => {
        section.style.display = 'none';
      });
  }

  // ── Salary Calculator ──────────────────────────────────
  // Note: key "Embedded Software Engineer" matches the HTML <select> value
  const FALLBACK_SALARIES = {
    'Embedded Software Engineer': {
      Junior: { p25: 40, p50: 47, p75: 52, p90: 55, sample_size: 120 },
      Medior: { p25: 55, p50: 62, p75: 67, p90: 70, sample_size: 180 },
      Senior: { p25: 70, p50: 80, p75: 87, p90: 90, sample_size: 200 },
      Lead: { p25: 90, p50: 100, p75: 107, p90: 110, sample_size: 80 }
    },
    'Frontend Developer': {
      Junior: { p25: 36, p50: 42, p75: 46, p90: 48, sample_size: 90 },
      Medior: { p25: 48, p50: 55, p75: 60, p90: 62, sample_size: 140 },
      Senior: { p25: 62, p50: 70, p75: 75, p90: 78, sample_size: 160 },
      Lead: { p25: 78, p50: 88, p75: 92, p90: 95, sample_size: 50 }
    },
    'Backend Developer': {
      Junior: { p25: 40, p50: 47, p75: 52, p90: 55, sample_size: 100 },
      Medior: { p25: 52, p50: 62, p75: 67, p90: 72, sample_size: 160 },
      Senior: { p25: 68, p50: 78, p75: 84, p90: 88, sample_size: 190 },
      Lead: { p25: 88, p50: 98, p75: 104, p90: 108, sample_size: 60 }
    },
    'C++ Developer': {
      Junior: { p25: 42, p50: 50, p75: 55, p90: 58, sample_size: 140 },
      Medior: { p25: 58, p50: 66, p75: 71, p90: 75, sample_size: 190 },
      Senior: { p25: 75, p50: 85, p75: 91, p90: 95, sample_size: 220 },
      Lead: { p25: 95, p50: 105, p75: 111, p90: 115, sample_size: 70 }
    },
    'Mechatronics Engineer': {
      Junior: { p25: 40, p50: 47, p75: 52, p90: 55, sample_size: 100 },
      Medior: { p25: 55, p50: 63, p75: 68, p90: 72, sample_size: 150 },
      Senior: { p25: 72, p50: 82, p75: 88, p90: 92, sample_size: 170 },
      Lead: { p25: 92, p50: 101, p75: 107, p90: 110, sample_size: 60 }
    },
    'Cybersecurity Engineer': {
      Junior: { p25: 45, p50: 52, p75: 57, p90: 60, sample_size: 90 },
      Medior: { p25: 60, p50: 70, p75: 76, p90: 80, sample_size: 130 },
      Senior: { p25: 80, p50: 90, p75: 96, p90: 100, sample_size: 150 },
      Lead: { p25: 100, p50: 115, p75: 125, p90: 130, sample_size: 50 }
    },
    'Software Engineer': {
      Junior: { p25: 40, p50: 47, p75: 52, p90: 55, sample_size: 200 },
      Medior: { p25: 55, p50: 63, p75: 68, p90: 70, sample_size: 260 },
      Senior: { p25: 70, p50: 80, p75: 86, p90: 90, sample_size: 280 },
      Lead: { p25: 90, p50: 100, p75: 106, p90: 110, sample_size: 90 }
    },
    'AI/ML Engineer': {
      Junior: { p25: 45, p50: 53, p75: 59, p90: 62, sample_size: 80 },
      Medior: { p25: 62, p50: 72, p75: 78, p90: 82, sample_size: 110 },
      Senior: { p25: 82, p50: 93, p75: 100, p90: 105, sample_size: 130 },
      Lead: { p25: 105, p50: 120, p75: 129, p90: 135, sample_size: 40 }
    },
    'DevOps / Cloud Engineer': {
      Junior: { p25: 42, p50: 50, p75: 55, p90: 58, sample_size: 110 },
      Medior: { p25: 58, p50: 66, p75: 72, p90: 75, sample_size: 160 },
      Senior: { p25: 75, p50: 85, p75: 91, p90: 95, sample_size: 180 },
      Lead: { p25: 95, p50: 105, p75: 111, p90: 115, sample_size: 60 }
    },
    'Data Engineer': {
      Junior: { p25: 42, p50: 49, p75: 54, p90: 57, sample_size: 90 },
      Medior: { p25: 55, p50: 64, p75: 70, p90: 74, sample_size: 130 },
      Senior: { p25: 72, p50: 82, p75: 88, p90: 92, sample_size: 150 },
      Lead: { p25: 92, p50: 102, p75: 108, p90: 112, sample_size: 50 }
    },
    'Data Scientist / AI Engineer': {
      Junior: { p25: 45, p50: 53, p75: 59, p90: 62, sample_size: 80 },
      Medior: { p25: 60, p50: 70, p75: 77, p90: 82, sample_size: 110 },
      Senior: { p25: 78, p50: 90, p75: 97, p90: 102, sample_size: 130 },
      Lead: { p25: 98, p50: 112, p75: 120, p90: 125, sample_size: 40 }
    },
    'IT Infrastructure Engineer': {
      Junior: { p25: 32, p50: 38, p75: 42, p90: 44, sample_size: 70 },
      Medior: { p25: 44, p50: 52, p75: 57, p90: 60, sample_size: 100 },
      Senior: { p25: 58, p50: 66, p75: 71, p90: 74, sample_size: 110 },
      Lead: { p25: 72, p50: 80, p75: 85, p90: 88, sample_size: 40 }
    },
    'Systems Architect': {
      Junior: { p25: 50, p50: 57, p75: 62, p90: 65, sample_size: 60 },
      Medior: { p25: 65, p50: 75, p75: 81, p90: 85, sample_size: 100 },
      Senior: { p25: 85, p50: 97, p75: 105, p90: 110, sample_size: 120 },
      Lead: { p25: 110, p50: 125, p75: 134, p90: 140, sample_size: 50 }
    },
    'Software Architect': {
      Junior: { p25: 60, p50: 68, p75: 73, p90: 76, sample_size: 50 },
      Medior: { p25: 75, p50: 84, p75: 90, p90: 94, sample_size: 80 },
      Senior: { p25: 92, p50: 105, p75: 112, p90: 118, sample_size: 100 },
      Lead: { p25: 115, p50: 128, p75: 136, p90: 142, sample_size: 40 }
    },
    'Engineering Manager': {
      Junior: { p25: 55, p50: 64, p75: 70, p90: 73, sample_size: 40 },
      Medior: { p25: 70, p50: 80, p75: 87, p90: 92, sample_size: 70 },
      Senior: { p25: 90, p50: 102, p75: 109, p90: 114, sample_size: 90 },
      Lead: { p25: 110, p50: 125, p75: 134, p90: 140, sample_size: 50 }
    }
  };

  function initSalaryCalc() {
    const btn = $('calcBtn');
    const calcResults = $('calcResults');
    if (!btn) return;

    function showCalcLoading() {
      if (calcResults) {
        const els = ['calcP25', 'calcP50', 'calcP75', 'calcP90'];
        els.forEach(id => { const el = $(id); if (el) el.innerHTML = '<span class="spinner-sm"></span>'; });
        const range = $('calcRange');
        if (range) range.style.width = '0%';
        const sample = $('calcSample');
        if (sample) sample.textContent = '';
      }
    }

    async function calculate() {
      const role = $('calcRole')?.value || 'Software Engineer';
      const level = $('calcLevel')?.value || 'Senior';
      const location = $('calcLocation')?.value || 'Eindhoven';

      showCalcLoading();

      // Try API first
      try {
        const res = await fetch(
          `${API}/api/v1/public/salary-data?role_title=${encodeURIComponent(role)}&seniority=${level}&location=${encodeURIComponent(location)}`
        );
        if (res.ok) {
          const data = await res.json();
          if (data && data.p50) {
            updateResults(data);
            return;
          }
        }
      } catch (e) {
        console.warn('[SalaryCalc] API failed, using fallback:', e);
      }

      // Fallback
      const fb = FALLBACK_SALARIES[role];
      if (fb && fb[level]) {
        updateResults(fb[level]);
      } else {
        updateResults({ p25: 50, p50: 65, p75: 85, p90: 100, sample_size: 0 });
      }
    }

    function updateResults(data) {
      const animate = (id, val) => {
        const el = $(id);
        if (!el) return;
        const target = val;
        let current = 0;
        const step = Math.max(1, Math.ceil(target / 25));
        el.textContent = '€0k';
        const interval = setInterval(() => {
          current += step;
          if (current >= target) { current = target; clearInterval(interval); }
          el.textContent = '€' + current + 'k';
        }, 35);
      };

      animate('calcP25', data.p25 || 0);
      animate('calcP50', data.p50 || 0);
      animate('calcP75', data.p75 || 0);
      animate('calcP90', data.p90 || 0);

      const range = $('calcRange');
      if (range) {
        const spread = (data.p90 || 60) - (data.p25 || 40);
        const pct = Math.min(100, Math.max(10, (spread / 80) * 100));
        range.style.width = pct + '%';
      }

      const sample = $('calcSample');
      if (sample) {
        const lang = localStorage.getItem('gsp_lang') || 'nl';
        sample.textContent = data.sample_size
          ? (lang === 'nl' ? `Gebaseerd op ${data.sample_size} datapunten` : `Based on ${data.sample_size} data points`)
          : (lang === 'nl' ? 'Gebaseerd op branche benchmarks' : 'Based on industry benchmarks');
      }
    }

    btn.addEventListener('click', calculate);
    // Run on load with loading state
    setTimeout(calculate, 300);
  }

  // ── Tech Match Quiz ────────────────────────────────────
  const QUIZ = [
    { q: { en: 'Which area is closest to your work?', nl: 'Welk vakgebied past het best bij jou?' }, options: [
      { text: { en: 'Web & application development', nl: 'Web- & applicatieontwikkeling' }, score: 22 },
      { text: { en: 'Cloud, infrastructure & DevOps', nl: 'Cloud, infrastructuur & DevOps' }, score: 22 },
      { text: { en: 'Data, AI & machine learning', nl: 'Data, AI & machine learning' }, score: 22 },
      { text: { en: 'Security & privacy', nl: 'Security & privacy' }, score: 22 }
    ]},
    { q: { en: 'How many years of experience do you have?', nl: 'Hoeveel jaar ervaring heb je?' }, options: [
      { text: { en: '0–2 years (Junior)', nl: '0–2 jaar (Junior)' }, score: 5 },
      { text: { en: '3–6 years (Medior)', nl: '3–6 jaar (Medior)' }, score: 10 },
      { text: { en: '7–12 years (Senior)', nl: '7–12 jaar (Senior)' }, score: 15 },
      { text: { en: '12+ years (Lead)', nl: '12+ jaar (Lead)' }, score: 20 }
    ]},
    { q: { en: 'What kind of work setup suits you best?', nl: 'Welke werkvorm past het best bij jou?' }, options: [
      { text: { en: 'Fully on-site', nl: 'Volledig op kantoor' }, score: 20 },
      { text: { en: 'Hybrid', nl: 'Hybride' }, score: 25 },
      { text: { en: 'Fully remote (NL)', nl: 'Volledig remote (NL)' }, score: 20 },
      { text: { en: 'Open to relocating within NL', nl: 'Open om te verhuizen binnen NL' }, score: 25 }
    ]},
    { q: { en: 'What kind of company suits you best?', nl: 'Wat voor bedrijf past het best bij jou?' }, options: [
      { text: { en: 'Product company or scale-up', nl: 'Productbedrijf of scale-up' }, score: 15 },
      { text: { en: 'Enterprise / corporate', nl: 'Enterprise / corporate' }, score: 15 },
      { text: { en: 'Consultancy / multiple clients', nl: 'Consultancy / meerdere klanten' }, score: 15 },
      { text: { en: 'Early startup, lots of ownership', nl: 'Vroege startup, veel eigenaarschap' }, score: 15 }
    ]}
  ];

  function initQuiz() {
    const container = $('quizContainer');
    if (!container) return;

    let currentQ = 0;
    let score = 0;

    function getLang() {
      return localStorage.getItem('gsp_lang') || 'nl';
    }

    function showQuizLoading() {
      container.innerHTML = '<div style="text-align:center;padding:40px"><div class="spinner" style="margin:0 auto 16px"></div><p style="color:var(--text-muted)">Loading quiz...</p></div>';
    }

    function renderQuestion() {
      if (currentQ >= QUIZ.length) {
        showResult();
        return;
      }

      const lang = getLang();
      const q = QUIZ[currentQ];
      const questionText = q.q[lang] || q.q.en;

      let dots = '';
      for (let i = 0; i < QUIZ.length; i++) {
        dots += `<div class="quiz-dot ${i < currentQ ? 'completed' : i === currentQ ? 'active' : ''}"></div>`;
      }

      container.innerHTML = `
        <div class="quiz-progress">${dots}</div>
        <div class="quiz-question">${questionText}</div>
        <div class="quiz-options">
          ${q.options.map((opt, i) =>
            `<button class="quiz-option" data-score="${opt.score}">${opt.text[lang] || opt.text.en}</button>`
          ).join('')}
        </div>
      `;

      container.querySelectorAll('.quiz-option').forEach(btn => {
        btn.addEventListener('click', () => {
          score += parseInt(btn.dataset.score);
          currentQ++;
          setTimeout(renderQuestion, 200);
        });
      });
    }

    function showResult() {
      const lang = getLang();
      const pct = Math.min(100, Math.round((score / 85) * 100));

      let label;
      if (lang === 'nl') {
        if (pct >= 80) label = 'Uitstekende match! Je staat sterk op de Nederlandse tech-arbeidsmarkt.';
        else if (pct >= 60) label = 'Groot potentieel! Met enkele focusgebieden ben je een sterke kandidaat.';
        else if (pct >= 40) label = 'Redelijke match. Laten we samen kijken waar jouw kansen liggen.';
        else label = 'Goed begin! Stuur je CV in, dan denken we met je mee over je volgende stap.';
      } else {
        if (pct >= 80) label = 'Excellent match! You are in a strong position in the Dutch tech market.';
        else if (pct >= 60) label = 'Great potential! With some focus areas, you could be a strong candidate.';
        else if (pct >= 40) label = 'Decent match. Let\'s look together at where your opportunities are.';
        else label = 'Good start! Send us your CV and we\'ll help you think through your next step.';
      }

      container.innerHTML = `
        <div class="quiz-progress">
          ${QUIZ.map(() => '<div class="quiz-dot completed"></div>').join('')}
        </div>
      `;

      const quizLead = $('quizLead');
      const quizResult = $('quizResult');
      if (quizResult) {
        quizResult.innerHTML = `
          <div class="quiz-score">${pct}%</div>
          <div class="quiz-label">${label}</div>
          <button class="btn btn-gold" id="quizRestart" style="margin-top:24px"><i class="fas fa-redo"></i> ${lang === 'nl' ? 'Opnieuw' : 'Try Again'}</button>
        `;
      }
      if (quizLead) quizLead.style.display = '';

      $('quizRestart')?.addEventListener('click', () => {
        currentQ = 0;
        score = 0;
        const ql = $('quizLead');
        if (ql) ql.style.display = 'none';
        renderQuestion();
      });

      // Email lead capture
      $('quizEmailBtn')?.addEventListener('click', async () => {
        const email = $('quizEmail')?.value.trim();
        const errEl = $('quizLeadError');
        const successEl = $('quizLeadSuccess');
        if (errEl) errEl.style.display = 'none';
        if (successEl) successEl.style.display = 'none';

        if (!email || !email.includes('@')) {
          if (errEl) {
            errEl.textContent = lang === 'nl' ? 'Voer een geldig e-mailadres in.' : 'Please enter a valid email address.';
            errEl.style.display = 'block';
          }
          return;
        }

        // Show loading state
        const emailBtn = $('quizEmailBtn');
        if (emailBtn) {
          emailBtn.disabled = true;
          emailBtn.innerHTML = '<span class="spinner-sm"></span> Sending...';
        }

        try {
          const res = await fetch(`${API}/api/v1/public/lead`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              email,
              name: 'Quiz Lead',
              message: `Quiz score: ${pct}% - ${label}`,
              interest_type: 'candidate'
            })
          });
          if (res.ok) {
            if (successEl) {
              successEl.textContent = lang === 'nl' ? 'Resultaten verzonden! Check je inbox.' : 'Results sent! Check your inbox.';
              successEl.style.display = 'block';
            }
            if ($('quizEmail')) $('quizEmail').value = '';
          } else {
            if (errEl) {
              errEl.textContent = lang === 'nl' ? 'Verzenden mislukt. Probeer opnieuw.' : 'Failed to send. Try again.';
              errEl.style.display = 'block';
            }
          }
        } catch (e) {
          if (errEl) {
            errEl.textContent = lang === 'nl' ? 'Netwerkfout. Probeer opnieuw.' : 'Network error. Please try again.';
            errEl.style.display = 'block';
          }
        } finally {
          if (emailBtn) {
            emailBtn.disabled = false;
            emailBtn.innerHTML = '<i class="fas fa-envelope"></i> ' + (lang === 'nl' ? 'Stuur mijn resultaten' : 'Send my results');
          }
        }
      });
    }

    showQuizLoading();
    setTimeout(renderQuestion, 300);
  }

  // ── Contact Form ───────────────────────────────────────
  function initContactForm() {
    const form = $('contactForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const errEl = $('contactError');
      const successEl = $('contactSuccess');
      const lang = localStorage.getItem('gsp_lang') || 'nl';
      const submitBtn = form.querySelector('button[type="submit"]');

      if (errEl) errEl.style.display = 'none';
      if (successEl) successEl.style.display = 'none';

      // Show loading state
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-sm"></span> Sending...';
      }

      const data = Object.fromEntries(new FormData(form));
      if (data.interest) {
        data.interest_type = data.interest;
        delete data.interest;
      }
      delete data.gdpr;

      try {
        const res = await fetch(`${API}/api/v1/public/lead`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        });

        if (res.ok) {
          if (successEl) {
            successEl.textContent = lang === 'nl'
              ? 'Bedankt! We nemen binnen 24 uur contact met je op.'
              : 'Thank you! We\'ll get back to you within 24 hours.';
            successEl.style.display = 'block';
          }
          form.reset();
        } else {
          const d = await res.json();
          throw new Error(d.detail || (lang === 'nl' ? 'Verzenden mislukt' : 'Failed to send'));
        }
      } catch (err) {
        if (errEl) { errEl.textContent = err.message; errEl.style.display = 'block'; }
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="fas fa-paper-plane"></i> <span class="lang-en">Send message</span><span class="lang-nl">Verstuur bericht</span>';
        }
      }
    });
  }

  // ── Live Stats ─────────────────────────────────────────
  function initLiveStats() {
    // Static stats are shown by default in HTML.
    // If admin is logged in, try to fetch real stats using Auth module.
    if (!Auth.isLoggedIn()) return;
    const u = Auth.getUser();
    if (!u || u.role !== 'admin') return;

    // Show loading state on stats
    const p = $('statPlacements');
    const pt = $('statPartners');
    if (p) p.textContent = '...';
    if (pt) pt.textContent = '...';

    const token = Auth.getToken();
    if (!token) return;

    fetch(`${API}/api/v1/admin/dashboard`, {
      headers: { 'Authorization': 'Bearer ' + token }
    })
      .then(r => {
        if (!r.ok) throw new Error('Failed to fetch stats');
        return r.json();
      })
      .then(data => {
        if (p && data.active_jobs) p.textContent = data.active_jobs;
        if (pt && data.registered_candidates) pt.textContent = data.registered_candidates;
      })
      .catch(err => {
        console.warn('[LiveStats] Failed to fetch admin dashboard:', err);
        // Restore default static values on error
        if (p) p.textContent = '150+';
        if (pt) pt.textContent = '40+';
      });
  }

  // ── Testimonials Carousel ──────────────────────────────
  function initTestimonials() {
    const container = $('testimonials');
    if (!container) return;

    const cards = qsa('.testimonial-card', container);
    if (cards.length < 2) return;

    let currentIndex = 0;
    let autoRotate = true;
    let intervalId = null;

    // Create carousel wrapper
    const wrapper = document.createElement('div');
    wrapper.className = 'testimonials-carousel';
    wrapper.style.cssText = 'position:relative;overflow:hidden;width:100%;max-width:900px;margin:0 auto;min-height:200px';

    // Move cards into carousel track
    const track = document.createElement('div');
    track.className = 'testimonials-track';
    track.style.cssText = 'display:flex;transition:transform 0.5s ease-in-out';

    cards.forEach(card => {
      const slide = document.createElement('div');
      slide.className = 'testimonial-slide';
      slide.style.cssText = 'min-width:100%;box-sizing:border-box;padding:0 16px';
      slide.appendChild(card.cloneNode(true));
      track.appendChild(slide);
      card.remove();
    });

    wrapper.appendChild(track);
    container.appendChild(wrapper);

    // Add navigation dots
    const dotsContainer = document.createElement('div');
    dotsContainer.className = 'testimonials-dots';
    dotsContainer.style.cssText = 'display:flex;justify-content:center;gap:10px;margin-top:24px';

    const dots = [];
    for (let i = 0; i < cards.length; i++) {
      const dot = document.createElement('button');
      dot.className = 'testimonial-dot';
      dot.setAttribute('aria-label', `Testimonial ${i + 1}`);
      dot.style.cssText = 'width:10px;height:10px;border-radius:50%;border:none;background:var(--border);cursor:pointer;transition:var(--transition)';
      if (i === 0) dot.style.background = 'var(--gold)';
      dot.addEventListener('click', () => goToSlide(i));
      dotsContainer.appendChild(dot);
      dots.push(dot);
    }
    container.appendChild(dotsContainer);

    function goToSlide(index) {
      currentIndex = index;
      track.style.transform = `translateX(-${currentIndex * 100}%)`;
      dots.forEach((d, i) => {
        d.style.background = i === currentIndex ? 'var(--gold)' : 'var(--border)';
      });
    }

    function nextSlide() {
      if (!autoRotate) return;
      goToSlide((currentIndex + 1) % cards.length);
    }

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function startAutoRotate() {
      stopAutoRotate();
      if (prefersReducedMotion) return;
      intervalId = setInterval(nextSlide, 5000);
    }

    function stopAutoRotate() {
      if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
      }
    }

    // Pause on hover, and on keyboard focus so keyboard users get time to read
    wrapper.addEventListener('mouseenter', () => { autoRotate = false; });
    wrapper.addEventListener('mouseleave', () => { autoRotate = true; });
    wrapper.addEventListener('focusin', () => { autoRotate = false; });
    wrapper.addEventListener('focusout', () => { autoRotate = true; });
    dotsContainer.addEventListener('mouseenter', () => { autoRotate = false; });
    dotsContainer.addEventListener('mouseleave', () => { autoRotate = true; });
    dotsContainer.addEventListener('focusin', () => { autoRotate = false; });
    dotsContainer.addEventListener('focusout', () => { autoRotate = true; });

    startAutoRotate();
  }

  // ── Cookie Consent Banner ──────────────────────────────
  function initCookieConsent() {
    const CONSENT_KEY = 'gsp_cookie_consent';
    if (localStorage.getItem(CONSENT_KEY) === 'true') return;

    // Check if banner already exists
    if (document.getElementById('cookieConsentBanner')) return;

    const banner = document.createElement('div');
    banner.id = 'cookieConsentBanner';
    banner.style.cssText = `
      position:fixed;bottom:0;left:0;right:0;z-index:10000;
      background:var(--bg-card);border-top:1px solid var(--border);
      padding:16px 24px;box-shadow:0 -4px 20px rgba(0,0,0,0.15);
      display:flex;flex-wrap:wrap;align-items:center;justify-content:center;
      gap:16px;font-size:0.9rem;
    `;

    const lang = localStorage.getItem('gsp_lang') || 'nl';
    const text = lang === 'nl'
      ? 'Deze site gebruikt functionele cookies voor authenticatie en taalvoorkeur. Geen tracking.'
      : 'This site uses functional cookies for authentication and language preference. No tracking.';

    banner.innerHTML = `
      <span style="color:var(--text-secondary);flex:1;min-width:200px">${text}</span>
      <div style="display:flex;gap:8px;flex-shrink:0">
        <a href="privacy.html" style="font-size:0.85rem;color:var(--gold);text-decoration:none">${lang === 'nl' ? 'Privacybeleid' : 'Privacy Policy'}</a>
        <button id="cookieConsentAccept" class="btn btn-primary btn-sm">${lang === 'nl' ? 'Accepteren' : 'Accept'}</button>
      </div>
    `;

    document.body.appendChild(banner);

    $('cookieConsentAccept')?.addEventListener('click', () => {
      localStorage.setItem(CONSENT_KEY, 'true');
      banner.remove();
    });
  }

  // ── Back-to-Top Button ─────────────────────────────────
  function initBackToTop() {
    // Create button if it doesn't exist
    let btn = $('backToTop');
    if (!btn) {
      btn = document.createElement('button');
      btn.id = 'backToTop';
      btn.setAttribute('aria-label', 'Back to top');
      btn.innerHTML = '<i class="fas fa-arrow-up"></i>';
      btn.style.cssText = `
        position:fixed;bottom:80px;right:20px;z-index:9999;
        width:44px;height:44px;border-radius:50%;
        background:var(--gold);color:var(--bg);border:none;
        cursor:pointer;box-shadow:var(--shadow-md);
        display:flex;align-items:center;justify-content:center;
        font-size:1.1rem;opacity:0;visibility:hidden;
        transition:opacity 0.3s,visibility 0.3s,transform 0.3s;
        transform:translateY(10px);
      `;
      document.body.appendChild(btn);
    }

    const scrollHandler = () => {
      if (window.scrollY > 400) {
        btn.style.opacity = '1';
        btn.style.visibility = 'visible';
        btn.style.transform = 'translateY(0)';
      } else {
        btn.style.opacity = '0';
        btn.style.visibility = 'hidden';
        btn.style.transform = 'translateY(10px)';
      }
    };

    window.addEventListener('scroll', scrollHandler, { passive: true });

    btn.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  // ── Google Sign-In Callback ─────────────────────────────
  // The backend redirects here as https://gsprecruitment.nl/?google_auth=<jwt>
  // (or ?google_auth_error=<code>) after the user completes Google's consent
  // screen. Pick up the token, strip it from the URL immediately (before any
  // other network request can leak it via a Referer header), then fetch the
  // user's profile to finish signing them in the same way a normal
  // email/password login does.
  function handleGoogleAuthCallback() {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('google_auth');
    const error = params.get('google_auth_error');

    if (!token && !error) return;
    window.history.replaceState({}, document.title, window.location.pathname);

    if (error) {
      const messages = {
        access_denied: 'Google sign-in was cancelled.',
        email_not_verified: 'Your Google email is not verified yet. Please verify it with Google first.',
      };
      Auth.toast(messages[error] || 'Google sign-in failed. Please try again.', 'error');
      return;
    }

    fetch(`${Auth.API}/auth/me`, { headers: { 'Authorization': `Bearer ${token}` } })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch profile');
        return res.json();
      })
      .then((user) => {
        Auth.setAuth(token, user);
        Auth.toast('Signed in with Google!', 'success');
        window.location.href = Auth.getDashboardUrl(user);
      })
      .catch(() => {
        Auth.toast('Google sign-in failed. Please try again.', 'error');
      });
  }

  // ── Init Everything ────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    handleGoogleAuthCallback();
    initLang();
    initPreloader();
    initHamburger();
    initHeaderScroll();
    initScrollAnimations();
    initFAQ();
    initAuth();
    initCookieConsent();
    initJobBoard();
    initHomeVacancies();
    initSalaryCalc();
    initQuiz();
    initContactForm();
    initLiveStats();
    initTestimonials();
    initBackToTop();
    initWhatsappFloat();
  });

  // ── Floating WhatsApp Button ───────────────────────────
  function initWhatsappFloat() {
    if (!GSP_WHATSAPP) return; // no number configured — never show a dead link
    const existing = document.querySelector('.mail-float');
    if (existing) existing.classList.add('has-whatsapp-sibling');
    const a = document.createElement('a');
    a.href = `https://wa.me/${GSP_WHATSAPP}?text=Hoi%20GSP%20Recruitment`;
    a.className = 'whatsapp-float';
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.setAttribute('aria-label', 'Chat via WhatsApp');
    a.innerHTML = '<i class="fa-brands fa-whatsapp"></i>';
    document.body.appendChild(a);
  }
})();