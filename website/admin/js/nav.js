  /* ---- Navigation ---- */
  const sectionTitles = {
    dashboard: 'Dashboard', users: 'User Management', jobs: 'All Jobs',
    candidates: 'All Candidates', outreach: 'Outreach', blog: 'Blog', analytics: 'Analytics',
    audit: 'Audit Log', cms: 'Content CMS', settings: 'Settings',
  };

  const sectionLoaders = {
    users:      () => Admin.loadUsers(),
    jobs:       () => Admin.loadJobs(),
    candidates: () => Admin.loadCandidates(),
    outreach:   () => Admin.loadOutreach(),
    blog:       () => Admin.loadBlog(),
    analytics:  () => Admin.loadAnalytics(),
    audit:      () => Admin.loadAuditLog(),
    cms:        () => Admin.loadContent(),
    settings:   () => Admin.loadSettings(),
  };

  const loaded = new Set(['dashboard']);

  function navigateTo(section) {
    document.querySelectorAll('.nav-link[data-section]').forEach(item => {
      item.classList.toggle('active', item.dataset.section === section);
    });
    document.querySelectorAll('.portal-section').forEach(s => {
      s.classList.toggle('active', s.id === `section-${section}`);
    });
    document.getElementById('pageTitle').textContent = sectionTitles[section] || section;
    window.location.hash = section;
    const menu = document.getElementById('sidebar-menu');
    if (menu && menu.classList.contains('show') && window.bootstrap) {
      window.bootstrap.Collapse.getOrCreateInstance(menu).hide();
    }

    if (!loaded.has(section) && sectionLoaders[section]) {
      loaded.add(section);
      sectionLoaders[section]();
    }
  }

  document.querySelectorAll('.nav-link[data-section]').forEach(item => {
    item.addEventListener('click', (e) => { e.preventDefault(); navigateTo(item.dataset.section); });
  });

  const hash = window.location.hash.replace('#', '');
  if (hash && sectionTitles[hash]) navigateTo(hash);

  /* ---- Logout ---- */
  document.getElementById('sidebarLogoutBtn').addEventListener('click', () => Auth.logout());

  /* ---- Audit filter input ---- */
  const auditInput = document.getElementById('auditActionFilter');
  if (auditInput) {
    let t;
    auditInput.addEventListener('input', e => {
      clearTimeout(t);
      t = setTimeout(() => {
        Admin._currentPage.audit = 1;
        Admin.loadAuditLog({ action: e.target.value.trim() || undefined });
      }, 500);
    });
  }

  /* ---- User search live ---- */
  const userSearch = document.getElementById('userSearch');
  if (userSearch) {
    let t;
    userSearch.addEventListener('input', e => {
      clearTimeout(t);
      t = setTimeout(() => {
        Admin._currentPage.users = 1;
        Admin.loadUsers({ search: e.target.value.trim() });
      }, 400);
    });
  }

  /* ---- Outreach status filter ---- */
  const outreachStatusFilter = document.getElementById('outreachStatusFilter');
  if (outreachStatusFilter) {
    outreachStatusFilter.addEventListener('change', e => {
      Admin._currentPage.outreach = 1;
      Admin.loadOutreach({ status: e.target.value || undefined });
    });
  }

  /* ---- Blog status filter ---- */
  const blogStatusFilter = document.getElementById('blogStatusFilter');
  if (blogStatusFilter) {
    blogStatusFilter.addEventListener('change', e => {
      Admin._currentPage.blog = 1;
      Admin.loadBlog({ status: e.target.value || undefined });
    });
  }

  /* ---- Candidate status filter ---- */
  const candStatusFilter = document.getElementById('candidateStatusFilter');
  if (candStatusFilter) {
    candStatusFilter.addEventListener('change', e => {
      Admin._currentPage.candidates = 1;
      Admin.loadCandidates({ status: e.target.value || undefined, kind: document.getElementById('candidateKindFilter')?.value || undefined });
    });
  }

  /* ---- Candidate kind filter (Alle / Zelf geregistreerd / Gesourced) ---- */
  const candKindFilter = document.getElementById('candidateKindFilter');
  if (candKindFilter) {
    candKindFilter.addEventListener('change', e => {
      Admin._currentPage.candidates = 1;
      Admin.loadCandidates({ kind: e.target.value || undefined, status: document.getElementById('candidateStatusFilter')?.value || undefined });
    });
  }

  /* ---- Language preference ---- */
  const savedLang = localStorage.getItem('gsp_lang');
  if (savedLang === 'nl' || savedLang === 'en') document.documentElement.setAttribute('data-lang', savedLang);
