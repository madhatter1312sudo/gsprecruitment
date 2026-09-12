/* ============================================================
   GSP Recruitment — admin/js/sections/candidates.js
   Kandidatenlijst met type- en statusfilter, en het detailpaneel.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern) en voor nav.js, dat de registry uitleest. Geen ES-module: de
   rest van de site gebruikt die ook niet.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  Object.assign(Admin, {
  /* ============================================================
     CANDIDATES
     ============================================================ */
  async loadCandidates(params = {}) {
    this._lastParams.candidates = params;
    const qs = new URLSearchParams();
    const limit = this._pageSize;
    const offset = ((this._currentPage.candidates || 1) - 1) * limit;
    if (params.search) qs.set('search', params.search);
    if (params.status) qs.set('status', params.status);
    if (params.kind) qs.set('kind', params.kind);
    qs.set('limit', limit);
    qs.set('offset', offset);

    this.setLoading('#section-candidates table tbody', 8);
    try {
      const res = await Auth.fetch(`/v1/admin/candidates?${qs}`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      this._data.candidates = data;
      this.renderCandidates(data);
      this.renderPagination('candidatesPagination', data.total, limit, this._currentPage.candidates, 'candidates');
    } catch (err) {
      this.setLoadError('#section-candidates table tbody', 8, () => this.loadCandidates(params));
    }
  },

  // "sourced" (blue, "Via GSP") came in via our own search/outreach
  // pipeline; "self-registered" (green, "Zelf aangemeld") signed up on the
  // candidate portal themselves.
  kindBadge(kind) {
    if (kind === 'self-registered') return { cls: 'badge bg-green-lt', label: 'Zelf aangemeld' };
    return { cls: 'badge bg-blue-lt', label: 'Via GSP' };
  },

  renderCandidates(data) {
    const tbody = document.querySelector('#section-candidates table tbody');
    if (!tbody) return;
    const items = data.items || [];
    if (!items.length) {
      this.setEmpty('#section-candidates table tbody', 8,
        'Geen kandidaten gevonden voor deze filters. Pas de zoekopdracht of het type-filter aan.');
      return;
    }
    mount(tbody, html`${items.map(c => {
      const kb = this.kindBadge(c.kind);
      // A self-registered row without a resolved user_id (email-case edge) is
      // really a candidates-table row: view it via the sourced detail path.
      const effKind = (c.kind === 'self-registered' && c.user_id == null && c.candidate_id != null) ? 'sourced' : c.kind;
      const itemId = effKind === 'self-registered' ? (c.user_id ?? c.id) : (c.candidate_id ?? c.id);
      return html`
      <tr>
        <td class="a-cell-name">
          ${c.full_name || '—'}
          ${c.is_verified ? raw('<i class="fa-regular fa-circle-check ms-1 a-positive" title="Geverifieerd"></i>') : raw('<i class="fa-regular fa-circle ms-1 a-soft" title="Niet geverifieerd"></i>')}
        </td>
        <td class="a-meta">${c.email}</td>
        <td>${c.current_title || '—'}</td>
        <td class="text-center">${c.years_experience ? c.years_experience + ' yrs' : '—'}</td>
        <td class="text-center">
          <span title="Matches">${c.match_count ?? 0}</span>
          ${c.placement_count ? html` / <span class="a-positive" title="Placed">${c.placement_count} placed</span>` : ''}
        </td>
        <td><span class="${kb.cls}" title="${c.source ? 'Bron: ' + c.source : ''}">${kb.label}</span></td>
        <td>
          <span class="${this.badge(c.status || 'active')}">${this.statusLabel(c.status || 'active')}</span>
        </td>
        <td>
          <button class="btn btn-sm btn-ghost-secondary" data-action="view-candidate" data-kind="${effKind === 'self-registered' ? 'self-registered' : 'sourced'}" data-id="${itemId}" title="View profile">
            <i class="fa-regular fa-eye"></i>
          </button>
        </td>
      </tr>`;
    })}`);
  },

  /* ---- Candidate detail modal (kind-aware) ---- */
  async viewCandidate(kind, itemId) {
    this.openModal('viewCandidateModal', html`
      <div class="a-state-cell">
        <i class="fa-solid fa-spinner fa-spin"></i> Laden…
      </div>`);
    try {
      const res = await Auth.fetch(`/v1/admin/candidates/${kind}/${itemId}`);
      if (!res?.ok) {
        const d = await res?.json().catch(() => null);
        this.openModal('viewCandidateModal', html`
          <h3 class="a-modal__title">Kon profiel niet laden</h3>
          <p class="a-soft">${d?.detail || 'Er ging iets mis bij het ophalen van dit profiel.'}</p>
          <div class="a-actions">
            <button class="btn btn-primary btn-sm" data-action="view-candidate" data-kind="${kind}" data-id="${itemId}">Opnieuw proberen</button>
            <button class="btn btn-ghost-secondary btn-sm" data-action="close-modal">Sluiten</button>
          </div>`);
        return;
      }
      const detail = await res.json();
      this.renderCandidateDetailModal(kind, itemId, detail);
    } catch {
      this.openModal('viewCandidateModal', html`
        <h3 class="a-modal__title">Netwerkfout</h3>
        <p class="a-soft">Kon geen verbinding maken met de server.</p>
        <div class="a-actions">
          <button class="btn btn-primary btn-sm" data-action="view-candidate" data-kind="${kind}" data-id="${itemId}">Opnieuw proberen</button>
          <button class="btn btn-ghost-secondary btn-sm" data-action="close-modal">Sluiten</button>
        </div>`);
    }
  },

  // The detail endpoint's exact response shape depends on kind (a user +
  // candidate_profiles record for self-registered, a candidates row +
  // linked user for sourced). Flatten every nested object we might get
  // (user / profile / candidate_profile / candidate) onto one bag so the
  // renderer below doesn't have to guess which container a field lives in.
  _flattenDetail(detail) {
    const merged = {};
    const layer = (obj) => { if (obj && typeof obj === 'object') Object.assign(merged, obj); };
    layer(detail);
    layer(detail.user);
    layer(detail.candidate);
    layer(detail.candidate_profile);
    layer(detail.profile);
    return merged;
  },

  _pick(obj, ...keys) {
    for (const k of keys) {
      if (obj[k] !== undefined && obj[k] !== null && obj[k] !== '') return obj[k];
    }
    return null;
  },

  renderCandidateDetailModal(kind, itemId, detail) {
    const d = this._flattenDetail(detail);
    const p = this._pick.bind(this, d);

    const fullName = p('full_name', 'name') || 'Onbekend';
    const email = p('email');
    const phone = p('phone', 'phone_number');
    const linkedin = p('linkedin_url', 'linkedin');
    const github = p('github_url', 'github');
    const portfolio = p('portfolio_url', 'website_url', 'website', 'portfolio');
    const skills = Array.isArray(d.skills) ? d.skills : (typeof d.skills === 'string' && d.skills ? d.skills.split(',').map(s => s.trim()) : []);
    const languages = Array.isArray(d.languages) ? d.languages : (typeof d.languages === 'string' && d.languages ? d.languages.split(',').map(s => s.trim()) : []);
    const salaryMin = p('salary_expectation_min', 'salary_min', 'desired_salary_min');
    const salaryMax = p('salary_expectation_max', 'salary_max', 'desired_salary_max');
    const salarySingle = p('salary_expectation', 'desired_salary');
    const notice = p('notice_period_days', 'notice_period', 'notice_period_weeks');
    const relocationRaw = this._pick(d, 'willing_to_relocate', 'relocation', 'relocation_willing', 'open_to_relocation');
    const education = p('education', 'education_level');
    const cvText = p('cv_text');
    const cvFilePath = p('cv_file_path');
    const kb = this.kindBadge(kind);

    // variant is 'skill' of 'lang'; de kleur zit in .a-chip--<variant>.
    const chips = (arr, variant) => arr.length
      ? html`<div class="a-chips">${arr.map(s => html`<span class="badge a-chip a-chip--${variant}">${s}</span>`)}</div>`
      : html`<div class="a-soft">—</div>`;

    const field = (label, value) => html`
      <div><div class="a-field-label">${label}</div><div>${value}</div></div>`;

    let salaryDisplay = raw('—');
    if (salaryMin || salaryMax) {
      salaryDisplay = html`€${salaryMin ?? '?'} – €${salaryMax ?? '?'}`;
    } else if (salarySingle) {
      salaryDisplay = html`€${salarySingle}`;
    }

    let relocationDisplay = raw('—');
    if (relocationRaw === true || relocationRaw === 'true' || relocationRaw === 'yes') relocationDisplay = raw('Ja');
    else if (relocationRaw === false || relocationRaw === 'false' || relocationRaw === 'no') relocationDisplay = raw('Nee');
    else if (relocationRaw) relocationDisplay = html`${relocationRaw}`;

    const safeLinkedin = this.safeUrl(linkedin);
    const safeGithub = this.safeUrl(github);
    const safePortfolio = this.safeUrl(portfolio);
    const contactLinks = raw([
      email ? html`<a href="mailto:${email}" class="btn btn-sm btn-ghost-secondary"><i class="fa-regular fa-envelope me-1"></i>${email}</a>` : '',
      safeLinkedin ? html`<a href="${safeLinkedin}" target="_blank" rel="noopener" class="btn btn-sm btn-ghost-secondary"><i class="fa-brands fa-linkedin me-1"></i>LinkedIn</a>` : '',
      safeGithub ? html`<a href="${safeGithub}" target="_blank" rel="noopener" class="btn btn-sm btn-ghost-secondary"><i class="fa-brands fa-github me-1"></i>GitHub</a>` : '',
      safePortfolio ? html`<a href="${safePortfolio}" target="_blank" rel="noopener" class="btn btn-sm btn-ghost-secondary"><i class="fa-solid fa-globe me-1"></i>Portfolio</a>` : '',
    ].filter(Boolean));
    const hasContactLinks = !!(email || safeLinkedin || safeGithub || safePortfolio);

    this.openModal('viewCandidateModal', html`
      <div class="d-flex align-items-start justify-content-between gap-3 mb-3">
        <h3 class="a-cell-strong m-0">${fullName}</h3>
        <span class="${kb.cls}">${kb.label}</span>
      </div>
      ${hasContactLinks ? html`<div class="d-flex flex-wrap gap-2 mb-4">${contactLinks}</div>` : ''}

      <div class="detail-grid">
        ${field('Phone', phone || '—')}
        ${field('Current Title', p('current_title') || '—')}
        ${field('Company', p('current_company') || '—')}
        ${field('Experience', p('years_experience') ? html`${p('years_experience')} years` : '—')}
        ${field('Location', p('location') || '—')}
        ${field('Source', p('source', 'candidate_source') || '—')}
        ${field('Status', html`<span class="${this.badge(p('status') || p('candidate_status'))}">${p('status') || p('candidate_status') || (kind === 'self-registered' ? 'new' : 'active')}</span>`)}
        ${field('Education', education || '—')}
        ${field('Salary expectation', salaryDisplay)}
        ${field('Notice period', notice ? html`${notice} days` : '—')}
        ${field('Open to relocation', relocationDisplay)}
        ${field('Registered', p('created_at') ? this.formatDate(p('created_at')) : '—')}
      </div>

      <div class="mb-3">
        <div class="a-field-label">Skills</div>
        ${chips(skills, 'skill')}
      </div>
      <div class="mb-4">
        <div class="a-field-label">Languages</div>
        ${chips(languages, 'lang')}
      </div>

      <div class="a-panel mb-4">
        <div class="a-field-label"><i class="fa-regular fa-file-lines me-1"></i>CV</div>
        ${cvFilePath
          ? html`<div class="a-positive"><i class="fa-regular fa-circle-check me-1"></i>CV geüpload</div>
             <div class="a-meta mt-1">
               Het bestand zelf is nog niet downloadbaar vanuit dit paneel — alleen via de geauthenticeerde kandidaatroute.
             </div>`
          : html`<div class="a-soft">Geen CV geüpload</div>`}
        ${cvText ? html`
          <div class="a-field-label mt-2">Preview (tekst uit CV)</div>
          <div class="a-scrollbox">${cvText.slice(0, 2000)}${cvText.length > 2000 ? '…' : ''}</div>
        ` : ''}
      </div>

      <div class="d-flex gap-3 flex-wrap mb-4">
        <div class="a-stat">
          <div class="a-stat__value">${p('match_count') ?? 0}</div>
          <div class="a-meta">Matches</div>
        </div>
        <div class="a-stat">
          <div class="a-stat__value a-stat__value--positive">${p('placement_count') ?? 0}</div>
          <div class="a-meta">Placed</div>
        </div>
      </div>
      <div class="d-flex gap-3">
        <button class="btn btn-ghost-secondary btn-sm" data-action="close-modal">Close</button>
      </div>
    `);
  },
  });

  Admin.registerSection({
    id: 'candidates',
    title: 'All Candidates',
    loader: () => Admin.loadCandidates(),
    filters: [
      // Zoeken houdt de gekozen status- en typefilters vast in plaats van
      // ze bij elke toetsaanslag stil te resetten.
      { selector: '#section-candidates .search-bar input', event: 'input', debounce: 400,
        handler(el) {
          Admin.loadCandidates({
            search: el.value,
            status: document.getElementById('candidateStatusFilter')?.value || undefined,
            kind: document.getElementById('candidateKindFilter')?.value || undefined,
          });
        } },
      { selector: '#candidateStatusFilter', event: 'change',
        handler(el) {
          Admin._currentPage.candidates = 1;
          Admin.loadCandidates({
            status: el.value || undefined,
            kind: document.getElementById('candidateKindFilter')?.value || undefined,
          });
        } },
      { selector: '#candidateKindFilter', event: 'change',
        handler(el) {
          Admin._currentPage.candidates = 1;
          Admin.loadCandidates({
            kind: el.value || undefined,
            status: document.getElementById('candidateStatusFilter')?.value || undefined,
          });
        } },
    ],
    actions: {
      // Ook gebruikt door de dashboardwidget Nieuwe registraties; acties
      // zijn paneelbreed zodra de sectie geladen is.
      'view-candidate': (el) => Admin.viewCandidate(el.dataset.kind || 'self-registered', Number(el.dataset.id)),
    },
  });
})();
