/* ============================================================
   GSP Recruitment: admin/js/sections/candidates.js
   Kandidatenlijst met type- en statusfilter, de kandidaatdrawer (Profiel,
   Matches, Activiteit, Toestemmingen, SITE-DESIGN-SPEC.md §7.3.2), en de
   referral-intake.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern), ui.js en labels.js, en voor nav.js, dat de registry uitleest.
   Geen ES-module: de rest van de site gebruikt die ook niet.

   §7.3.2, wat dit bestand doet en wat het bewust niet doet:
     - De tab Toestemmingen en de twee wijzigmodals werken op
       `candidates.id` (candidateId hieronder), niet op de kind/itemId-
       sleutel waarmee de lijst en de drawer een kandidaat aanspreken.
       GET /candidates/self-registered/{id} (routers/admin.py) geeft geen
       enkele consentkolom terug, ook al staat er een gekoppelde
       candidates-rij achter: alleen GET /candidates/sourced/{id} doet dat
       (`SELECT c.*`). resolveConsentDetail() haalt daarom bij kind
       'self-registered' een TWEEDE keer op, via kind 'sourced' met het
       candidate_id uit de eerste respons, en cachet dat resultaat apart
       onder de sleutel `sourced:<candidateId>` (nooit gemengd met de
       cache van de eerste, kind-eigen respons: die twee objecten hebben
       verschillende `id`-betekenissen, en een PATCH-respons die per
       ongeluk in de verkeerde sleutel belandt zou `id` van een
       gebruikersaccount stilzwijgend vervangen door een candidates.id).
       Voor kind 'sourced' zijn beide ophalingen dezelfde aanroep, dus
       daar kost dit niets extra. Ontbreekt candidate_id/id helemaal (geen
       gekoppelde candidates-rij), dan toont de tab één zin in plaats van
       drie kaarten. Beide gevallen samen zijn as-built afwijking 1,
       SITE-DESIGN-SPEC.md §7.3.2.
     - De tab Matches is vervangen door de tab Pipeline (§7.3.4): allebei
       lazen GET /admin/pipeline?candidate_id=, dus twee tabs op dezelfde
       gegevens was verwarrend. Pipeline voegt de fasewisselaar en de
       historietijdlijn toe (Admin.loadPipelineTab() in admin.js, gedeeld
       met de klantdrawer in clients.js); Activiteit blijft een eigen tab
       op de bestaande, gedeelde route (GET /admin/activities?
       subject_type=candidate&subject_id=). §7.3.4 as-built.
     - De titelweergave bij een actieve presentatietoestemming
       ("<titel> · Vacature #<id>") is best effort: er is geen admin-route
       voor één losse vacature, dus dit bestand haalt bij het openen van de
       tab eenmalig de volledige (ongefilterde) vacaturelijst op om de
       titel te vinden. Staat de vacature daar niet in (verwijderd, of
       buiten de eerste 200), dan toont de tab alleen "Vacature #<id>".
       As-built afwijking 3.
     - evidence/note/referred_by gaan nooit door console.* en nooit naar
       localStorage: ze verlaten dit bestand uitsluitend als JSON-body van
       de PATCH/POST hierboven. De backend redigeert e-mailadressen erin
       voordat ze het auditlog in gaan (privacy.redact_emails()); dit
       bestand hoeft daar niets voor te doen.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  // Modellen/schemas.py TALENTPOOL_CONSENT_SCOPES, letterlijk overgenomen,
  // niet afgeleid, zodat een backendwijziging hier zichtbaar wordt in
  // plaats van stil te falen op een 422.
  const TALENTPOOL_CONSENT_SCOPES = ['matching_only', 'matching_and_contact'];

  Object.assign(Admin, {
  /* ============================================================
     CANDIDATES: lijst
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
          ${c.is_verified ? raw('<i class="fa-regular fa-circle-check ms-1 text-success-ink" title="Geverifieerd"></i>') : raw('<i class="fa-regular fa-circle ms-1 a-soft" title="Niet geverifieerd"></i>')}
        </td>
        <td class="a-meta">${c.email}</td>
        <td>${c.current_title || '—'}</td>
        <td class="text-center">${c.years_experience ? c.years_experience + ' yrs' : '—'}</td>
        <td class="text-center">
          <span title="Matches">${c.match_count ?? 0}</span>
          ${c.placement_count ? html` / <span class="text-success-ink" title="Placed">${c.placement_count} placed</span>` : ''}
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

  _findCandidateRosterRow(kind, itemId) {
    const roster = (this._data.candidates && this._data.candidates.items) || [];
    return roster.find(c => {
      const effKind = (c.kind === 'self-registered' && c.user_id == null && c.candidate_id != null) ? 'sourced' : c.kind;
      const rowId = effKind === 'self-registered' ? (c.user_id ?? c.id) : (c.candidate_id ?? c.id);
      return effKind === kind && rowId === itemId;
    }) || null;
  },

  /* ============================================================
     KANDIDAATDRAWER: Profiel, Matches, Activiteit, Toestemmingen
     ============================================================ */
  _candidateTabs: [
    { key: 'profiel', label: 'Profiel' },
    { key: 'pipeline', label: 'Pipeline' },
    { key: 'activiteit', label: 'Activiteit' },
    { key: 'toestemmingen', label: 'Toestemmingen' },
  ],

  // Historische naam, nog aangeroepen vanuit de rijactie en het
  // dashboardwidget "Nieuwe registraties"; beide blijven ongewijzigd.
  viewCandidate(kind, itemId) {
    this.openCandidateDrawer(kind, itemId);
  },

  openCandidateDrawer(kind, itemId) {
    const row = this._findCandidateRosterRow(kind, itemId);
    // LOW 5 (security-auditor, review op b9d5b21): de detailcache leeft
    // langer dan één drawersessie. Zonder deze reset toont heropenen van
    // dezelfde kandidaat binnen dezelfde paginasessie de toestemmingen van
    // de vorige keer totdat er een PATCH doorheen gaat. Wissen bij elke
    // opening is eenvoudiger en veiliger dan per kandidaat bijhouden welke
    // sleutels stale zijn.
    this._data.candidateDetail = {};
    this._candidateDrawer = ui.drawer({
      id: 'candidateDrawer',
      title: row?.full_name || 'Kandidaat',
      subtitle: row?.email || '—',
      tabs: this._candidateTabs,
      tabAction: 'candidate-tab',
      activeTab: 'profiel',
      dataset: { kind, id: itemId },
      body: html`<div id="candidateDrawerTabContent" class="a-tabpane"><i class="fa-solid fa-spinner fa-spin"></i></div>`,
      onClose: () => { this._candidateDrawer = null; },
    });
    this.switchCandidateTab(kind, itemId, 'profiel');
  },

  // opts (alleen doorgegeven aan de tab Toestemmingen) laat een geslaagde
  // PATCH een verse ophaling afdwingen (§7.3.2 as-built, HIGH/MEDIUM):
  // switchCandidateTab(kind, itemId, 'toestemmingen', { force: true }).
  switchCandidateTab(kind, itemId, tab, opts = {}) {
    if (this._candidateDrawer) this._candidateDrawer.selectTab(tab);
    const loaders = {
      profiel: () => this.loadCandidateProfileTab(kind, itemId),
      pipeline: () => this.loadCandidatePipelineTab(kind, itemId),
      activiteit: () => this.loadCandidateActivityTab(kind, itemId),
      toestemmingen: () => this.loadCandidateConsentTab(kind, itemId, opts),
    };
    (loaders[tab] || loaders.profiel)();
  },

  // Eén cache per kind/id-paar (de vorm die GET /candidates/{kind}/{id}
  // voor dát kind teruggeeft), gedeeld door de tabs Profiel/Matches/
  // Activiteit. De tab Toestemmingen en de twee wijzigmodals lezen NOOIT
  // rechtstreeks uit deze cache: zie resolveConsentDetail() hieronder.
  async ensureCandidateDetail(kind, itemId, { force = false } = {}) {
    const key = `${kind}:${itemId}`;
    this._data.candidateDetail = this._data.candidateDetail || {};
    if (!force && this._data.candidateDetail[key]) return this._data.candidateDetail[key];
    const res = await Auth.fetch(`/v1/admin/candidates/${kind}/${itemId}`);
    if (!res) throw new Error('network');
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error((data && data.detail) || 'error');
    this._data.candidateDetail[key] = data;
    return data;
  },

  // kind='sourced': item_id IS candidates.id. kind='self-registered': de
  // gekoppelde candidates-rij (indien aanwezig) staat op .candidate_id,
  // zie GET /v1/admin/candidates/{kind}/{id} in routers/admin.py.
  candidateRecordId(detail, kind) {
    if (!detail) return null;
    if (kind === 'sourced') return detail.id ?? null;
    return detail.candidate_id ?? null;
  },

  // De ene plek die de tab Toestemmingen en de twee wijzigmodals gebruiken
  // om aan een candidateId EN aan de consentvelden te komen. Voor kind
  // 'sourced' is dat de gewone detailrespons (dezelfde aanroep als de tab
  // Profiel, dus geen extra netwerkverkeer). Voor kind 'self-registered'
  // levert die eerste respons alleen `candidate_id`; de consentvelden
  // zelf komen pas uit een tweede, expliciete aanroep op kind 'sourced'
  // met dat id, gecachet onder `sourced:<candidateId>`. force geldt voor
  // allebei de aanroepen: na een PATCH is zowel het candidate_id-argument
  // als het consentresultaat opnieuw op te halen waard, ook al verandert
  // het eerste in de praktijk nooit.
  async resolveConsentDetail(kind, itemId, { force = false } = {}) {
    const base = await this.ensureCandidateDetail(kind, itemId, { force });
    const candidateId = this.candidateRecordId(base, kind);
    if (!candidateId) return { candidateId: null, detail: null };
    if (kind === 'sourced') return { candidateId, detail: base };
    const detail = await this.ensureCandidateDetail('sourced', candidateId, { force });
    return { candidateId, detail };
  },

  /* ---- Tab: Profiel ---- */
  async loadCandidateProfileTab(kind, itemId) {
    const el = document.getElementById('candidateDrawerTabContent');
    if (!el) return;
    mount(el, html`<div class="a-state-block"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>`);
    try {
      const detail = await this.ensureCandidateDetail(kind, itemId);
      // code-reviewer op b9d5b21: de drawerkop kwam alleen uit de al
      // geladen rosterrij en bleef "Kandidaat" / een streepje wanneer de
      // drawer buiten die lijst om opende (dashboardwidget, "Kandidaat
      // openen" vanuit de referral-409). Bijwerken zodra het echte detail
      // er is, corrigeert dat zonder een setTitle-API op ui.drawer nodig
      // te hebben.
      const flat = this._flattenDetail(detail);
      this.updateCandidateDrawerHeader(this._pick(flat, 'full_name', 'name'), this._pick(flat, 'email'));
      this.renderCandidateProfileTab(kind, itemId, detail);
    } catch {
      this.setContainerLoadError(el, () => this.loadCandidateProfileTab(kind, itemId));
    }
  },

  // ui.drawer() heeft geen setTitle: de kop hoort bij het element dat
  // panel() bij openen rendert (§7.2b), dus deze functie leest en
  // overschrijft die twee tekstknopen rechtstreeks in plaats van de hele
  // drawer opnieuw te vullen (dat zou de actieve tab en scrollpositie
  // resetten).
  updateCandidateDrawerHeader(fullName, email) {
    const titleEl = document.querySelector('#candidateDrawer__title span');
    if (titleEl) titleEl.textContent = fullName || 'Kandidaat';
    const subtitleEl = document.querySelector('#candidateDrawer .a-modal__subtitle');
    if (subtitleEl) subtitleEl.textContent = email || '—';
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

  renderCandidateProfileTab(kind, itemId, detail) {
    const el = document.getElementById('candidateDrawerTabContent');
    if (!el) return;
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

    mount(el, html`
      <div class="d-flex align-items-start justify-content-between gap-3 mb-2">
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
          ? html`<div class="text-success-ink"><i class="fa-regular fa-circle-check me-1"></i>CV geüpload</div>
             <div class="a-meta mt-1">
               Het bestand zelf is nog niet downloadbaar vanuit dit paneel, alleen via de geauthenticeerde kandidaatroute.
             </div>`
          : html`<div class="a-soft">Geen CV geüpload</div>`}
        ${cvText ? html`
          <div class="a-field-label mt-2">Preview (tekst uit CV)</div>
          <div class="a-scrollbox">${cvText.slice(0, 2000)}${cvText.length > 2000 ? '…' : ''}</div>
        ` : ''}
      </div>

      <div class="d-flex gap-3 flex-wrap">
        <div class="a-stat">
          <div class="a-stat__value">${p('match_count') ?? 0}</div>
          <div class="a-stat__label">Matches</div>
        </div>
        <div class="a-stat">
          <div class="a-stat__value a-stat__value--positive">${p('placement_count') ?? 0}</div>
          <div class="a-stat__label">Placed</div>
        </div>
      </div>
    `);
  },

  /* ---- Tab: Pipeline (§7.3.4, vervangt Matches) ---- */
  async loadCandidatePipelineTab(kind, itemId) {
    const el = document.getElementById('candidateDrawerTabContent');
    if (!el) return;
    mount(el, html`${[0, 1, 2].map(() => html`<div class="a-skel-block"></div>`)}`);
    try {
      const detail = await this.ensureCandidateDetail(kind, itemId);
      const candidateId = this.candidateRecordId(detail, kind);
      if (!candidateId) {
        mount(el, html`<div class="a-state-block">Deze kandidaat heeft nog geen kandidaatrecord; er is geen pipeline om te tonen.</div>`);
        return;
      }
      // showCandidateName: false -- deze drawer toont al één kandidaat, de
      // eigen naam nog eens tonen voegt niets toe (§7.3.4 admin.js).
      this.loadPipelineTab('candidateDrawerTabContent', 'candidate_id', candidateId, { showCandidateName: false });
    } catch {
      this.setContainerLoadError(el, () => this.loadCandidatePipelineTab(kind, itemId));
    }
  },

  /* ---- Tab: Activiteit (GET /admin/activities?subject_type=candidate) ---- */
  async loadCandidateActivityTab(kind, itemId) {
    const el = document.getElementById('candidateDrawerTabContent');
    if (!el) return;
    mount(el, html`<div class="a-state-block"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>`);
    try {
      const detail = await this.ensureCandidateDetail(kind, itemId);
      const candidateId = this.candidateRecordId(detail, kind);
      if (!candidateId) {
        mount(el, html`<div class="a-state-block">Deze kandidaat heeft nog geen kandidaatrecord; er is geen activiteit om te tonen.</div>`);
        return;
      }
      const res = await Auth.fetch(`/v1/admin/activities?subject_type=candidate&subject_id=${candidateId}&limit=50`);
      if (!res) return;
      const data = await res.json();
      if (!res.ok) throw new Error();
      const items = data.items || [];
      mount(el, items.length ? html`
        <div class="table-responsive">
          <table class="table table-vcenter card-table">
            <thead><tr><th>Type</th><th>Notitie</th><th>Datum</th><th>Status</th></tr></thead>
            <tbody>${items.map(a => html`
              <tr>
                <td class="a-cell-strong">${this.activityTypeLabel(a.type)}</td>
                <td class="a-soft">${a.body || '—'}</td>
                <td class="a-soft">${this.retentionDate(a.created_at)}</td>
                <td>${a.completed_at ? html`<span class="badge bg-secondary-lt">Afgerond</span>` : (a.due_at ? html`<span class="badge bg-blue-lt">Open</span>` : '—')}</td>
              </tr>`)}</tbody>
          </table>
        </div>` : html`<div class="a-state-block">Nog geen activiteiten voor deze kandidaat.</div>`);
    } catch {
      this.setContainerLoadError(el, () => this.loadCandidateActivityTab(kind, itemId));
    }
  },

  /* ============================================================
     TAB: TOESTEMMINGEN (§7.3.2)
     ============================================================ */
  async loadCandidateConsentTab(kind, itemId, opts = {}) {
    const el = document.getElementById('candidateDrawerTabContent');
    if (!el) return;
    // §7.2b laadstaat: drie vlakke blokken, geen shimmer.
    mount(el, html`${[0, 1, 2].map(() => html`<div class="a-skel-block"></div>`)}`);
    try {
      const { candidateId, detail } = await this.resolveConsentDetail(kind, itemId, opts);
      if (!candidateId) {
        // As-built afwijking 1: geen gekoppelde candidates-rij, dus geen
        // grondslag om een van de drie toestemmingen op vast te leggen.
        mount(el, html`<div class="a-state-block">Deze kandidaat heeft nog geen kandidaatrecord; toestemmingen zijn hier niet beschikbaar.</div>`);
        return;
      }
      // As-built afwijking 3: er is geen admin-route voor één losse
      // vacature. Alleen wanneer er een actieve presentatietoestemming is
      // (dus een titel te tonen valt) halen we eenmalig, ongefilterd, de
      // volledige vacaturelijst op om die titel te vinden.
      if (detail.consent_spec_presentation_job_id != null && !this._data.jobsAll) {
        try {
          const jres = await Auth.fetch('/v1/admin/jobs?limit=200');
          if (jres && jres.ok) {
            const jdata = await jres.json();
            this._data.jobsAll = jdata.items || [];
          }
        } catch { /* best effort: valt terug op "Vacature #<id>" */ }
      }
      this.renderCandidateConsentTab(kind, itemId, candidateId, detail);
    } catch {
      this.setContainerLoadError(el, () => this.loadCandidateConsentTab(kind, itemId, opts));
    }
  },

  // §7.2f: net als de retentiesectie kent dit tweetal geen eigen 4xx-codes
  // om op te vertakken: de backend valideert scope/job_id al client-side
  // weg (zie de submit*-functies hieronder), dus alleen de generieke
  // fallback op detail.message.
  candidateConsentErrorText(payload, status) {
    if (status === 401 || status === 403) return 'Je hebt geen rechten voor deze handeling.';
    const d = this.errorDetail(payload);
    if (d.message) return d.message;
    return 'Er ging iets mis, probeer het opnieuw.';
  },

  candidateModalAlert(containerId, text, opts = {}) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!text) { mount(el, ''); return; }
    mount(el, html`
      <div class="alert alert-danger" role="alert">
        <i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>
        <span>${text}</span>
        ${opts.action ? html`
          <button type="button" class="btn btn-sm btn-outline-secondary ms-3" data-action="${opts.action}"
            data-candidate-id="${opts.candidateId ?? ''}">${opts.actionLabel || 'Opnieuw proberen'}</button>` : ''}
      </div>`);
    // design-reviewer op b9d5b21: op 390 staat de body van een modal die
    // al gescrolld is (bijvoorbeeld doordat het formulier erboven de
    // ruimte vult), en dan verschijnt deze melding buiten beeld. De
    // gebruiker ziet dan na "Vastleggen" niets veranderen.
    el.scrollIntoView({ block: 'start' });
  },

  // core/retention.py JOB_ALERT_ELIGIBILITY_SQL, letterlijk overgenomen als
  // clientside voorwaarde: er is geen admin-route die deze afleiding al
  // teruggeeft, en GET /candidates/{kind}/{id} levert voor kind='sourced'
  // wel alle kolommen die de voorwaarde nodig heeft (c.*).
  candidateJobAlertEligibility(detail) {
    if (detail.consent_withdrawn_at) return { eligible: false, reason: 'toestemming ingetrokken' };
    if (!detail.email) return { eligible: false, reason: 'geen e-mailadres' };
    const portalBasis = detail.lawful_basis === 'portal_registratie';
    if (!portalBasis && detail.consent_scope !== 'matching_and_contact') {
      return { eligible: false, reason: 'geen geldige toestemmingsomvang' };
    }
    if (!portalBasis) {
      const until = detail.consent_talentpool_until ? new Date(detail.consent_talentpool_until) : null;
      if (!until || isNaN(until.getTime()) || until <= new Date()) {
        return { eligible: false, reason: 'toestemming talentpool verlopen of niet vastgelegd' };
      }
    }
    return { eligible: true, reason: '' };
  },

  renderCandidateConsentTab(kind, itemId, candidateId, detail) {
    const el = document.getElementById('candidateDrawerTabContent');
    if (!el) return;

    const tpActive = !!detail.consent_talentpool_at;
    const spActive = !!detail.consent_spec_presentation_at;
    const withdrawn = !!detail.consent_withdrawn_at;
    const jobId = detail.consent_spec_presentation_job_id;
    const jobsAll = this._data.jobsAll || [];
    const job = jobId != null ? jobsAll.find(j => j.id === jobId) : null;
    const alertsEnabled = detail.job_alert_optin_at != null && detail.job_alert_unsubscribed_at == null;
    const { eligible, reason } = this.candidateJobAlertEligibility(detail);
    // security-auditor LOW 4 op b9d5b21: de backend geeft hier gegarandeerd
    // een 409 met een Engelse zin (admin.py:1171-1176) zodra
    // consent_withdrawn_at staat; de knop meldt dat vooraf, in het
    // Nederlands, in plaats van de aanroep te laten mislukken.
    // chief-of-staff op 3c8f690: de eerdere tekst beloofde "pas na een
    // nieuwe talentpooltoestemming", maar de vastleg-tak van
    // talentpool-consent (admin.py:938-948) raakt consent_withdrawn_at
    // nooit aan, dus die belofte kwam nooit uit. De juiste, blijvende
    // reden staat er nu, en zichtbaar als .a-meta-regel naast de knop:
    // op 390 is er geen hover, dus title alleen is niet genoeg.
    const presentationDisabledReason = withdrawn
      ? 'Deze kandidaat heeft toestemming ingetrokken; presentatie kan niet worden vastgelegd.'
      : '';

    mount(el, html`
      <div class="a-panel mb-3">
        <h4 class="a-cell-strong mb-2">Talentpool</h4>
        <div class="a-metric-row"><span class="a-soft">Status</span>
          <span class="badge ${tpActive ? 'bg-green-lt' : 'bg-secondary-lt'}">${tpActive ? 'Toestemming actief' : 'Geen toestemming'}</span></div>
        ${tpActive ? html`
          <div class="a-metric-row"><span class="a-soft">Omvang</span><span>${AdminLabels.label('toestemmingsomvang', detail.consent_scope, detail.consent_scope || '—')}</span></div>
          <div class="a-metric-row"><span class="a-soft">Vastgelegd</span><span class="a-num--date">${this.retentionDate(detail.consent_talentpool_at)} · Geldig tot: ${this.retentionDate(detail.consent_talentpool_until)}</span></div>
          <div class="a-metric-row"><span class="a-soft">Bron</span><span>${detail.consent_source || '—'} · Grondslag: ${AdminLabels.label('grondslag', detail.lawful_basis, detail.lawful_basis || '—')}</span></div>
        ` : ''}
        ${withdrawn ? html`<div class="a-meta mt-1">Ingetrokken op ${this.retentionDate(detail.consent_withdrawn_at)}</div>` : ''}
        <div class="a-actions mt-2">
          <button type="button" class="btn btn-sm btn-primary" data-action="candidate-talentpool-edit" data-kind="${kind}" data-id="${itemId}">Wijzigen</button>
        </div>
      </div>

      <div class="a-panel mb-3">
        <h4 class="a-cell-strong mb-2">Presentatie bij een opdrachtgever</h4>
        <div class="a-metric-row"><span class="a-soft">Status</span>
          <span class="badge ${spActive ? 'bg-green-lt' : 'bg-secondary-lt'}">${spActive ? 'Toestemming actief' : 'Geen toestemming'}</span></div>
        ${spActive ? html`
          <div class="a-meta mt-1 mb-1">Voor: ${job ? html`${job.title}, Vacature #${job.id}` : html`Vacature #${jobId}`} · vastgelegd ${this.retentionDate(detail.consent_spec_presentation_at)}</div>
        ` : ''}
        <div class="a-actions mt-2">
          <button type="button" class="btn btn-sm btn-primary" data-action="candidate-presentation-edit" data-kind="${kind}" data-id="${itemId}"
            ${raw(presentationDisabledReason ? `disabled title="${GSP.esc(presentationDisabledReason)}"` : '')}>Vastleggen</button>
        </div>
        ${presentationDisabledReason ? html`<div class="a-meta mt-1">${presentationDisabledReason}</div>` : ''}
      </div>

      <div class="a-panel">
        <h4 class="a-cell-strong mb-2">Job-alerts (alleen lezen hier)</h4>
        <div class="a-metric-row"><span class="a-soft">Aangezet</span><span>${alertsEnabled ? 'Ja' : 'Nee'}</span></div>
        <div class="a-metric-row"><span class="a-soft">Komt in aanmerking</span><span>${eligible ? 'Ja' : 'Nee'}</span></div>
        ${!eligible ? html`<div class="a-meta mt-2">Reden: ${reason}</div>` : ''}
        <div class="fs-xs a-soft mt-2">De suppressielijst wordt bij verzending apart gecontroleerd.</div>
      </div>
    `);
  },

  /* ---- Validatiehulpjes (§7.2d): blur op eerste aanraking, direct erna
     op elke input. Nooit tijdens het eerste typen. ---- */
  _wireBlurValidate(el, validateFn) {
    if (!el) return;
    let touched = false;
    el.addEventListener('blur', () => { touched = true; validateFn(); });
    el.addEventListener('input', () => { if (touched) validateFn(); });
  },

  _validateEvidence(el, errId) {
    const val = el.value || '';
    const trimmed = val.trim();
    const errEl = document.getElementById(errId);
    let msg = '';
    if (!trimmed) msg = 'Vul kort in waar de toestemming uit blijkt';
    else if (val.length > 2000) msg = `Maximaal 2000 tekens (nu ${val.length}).`;
    if (errEl) errEl.textContent = msg;
    el.classList.toggle('is-invalid', !!msg);
    if (msg) el.setAttribute('aria-invalid', 'true'); else el.removeAttribute('aria-invalid');
    return !msg;
  },

  // §7.3.2: "boven 2000 tekens een teller in .text-danger-ink." Geen
  // maxlength meer op het veld zelf (dat zou dit onbereikbaar maken: een
  // browser laat een gebruiker dan nooit voorbij de grens typen), dus de
  // teller is de enige zichtbare waarschuwing terwijl _validateEvidence
  // hierboven (bij blur en submit) de daadwerkelijke blokkade blijft.
  _wireEvidenceCounter(el, counterId) {
    const counterEl = document.getElementById(counterId);
    if (!el || !counterEl) return;
    const update = () => {
      const len = (el.value || '').length;
      if (len > 2000) {
        counterEl.textContent = `${len} / 2000 tekens`;
        counterEl.classList.add('text-danger-ink');
      } else {
        counterEl.textContent = '';
        counterEl.classList.remove('text-danger-ink');
      }
    };
    el.addEventListener('input', update);
    update();
  },

  _validateRequired(el, errId, { max } = {}) {
    const val = el.value || '';
    const trimmed = val.trim();
    const errEl = document.getElementById(errId);
    let msg = '';
    if (!trimmed) msg = 'Dit veld is verplicht.';
    else if (max && val.length > max) msg = `Maximaal ${max} tekens (nu ${val.length}).`;
    if (errEl) errEl.textContent = msg;
    el.classList.toggle('is-invalid', !!msg);
    if (msg) el.setAttribute('aria-invalid', 'true'); else el.removeAttribute('aria-invalid');
    return !msg;
  },

  _validateEmail(el, errId) {
    const val = (el.value || '').trim();
    const errEl = document.getElementById(errId);
    let msg = '';
    if (!val) msg = 'Dit veld is verplicht.';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) msg = 'Vul een geldig e-mailadres in.';
    if (errEl) errEl.textContent = msg;
    el.classList.toggle('is-invalid', !!msg);
    if (msg) el.setAttribute('aria-invalid', 'true'); else el.removeAttribute('aria-invalid');
    return !msg;
  },

  /* ---- Modal: Talentpool wijzigen ---- */
  async openTalentpoolConsentModal(kind, itemId) {
    // security-auditor HIGH 1 op b9d5b21: candidateId en de consentvelden
    // komen altijd via resolveConsentDetail(), nooit rechtstreeks uit de
    // kind-eigen cache (die voor 'self-registered' geen consentkolommen
    // draagt).
    const { candidateId, detail } = await this.resolveConsentDetail(kind, itemId);
    if (!candidateId || !detail) return;
    const handle = ui.modal({
      id: 'candidateTalentpoolModal',
      title: 'Talentpool wijzigen',
      body: this.talentpoolConsentForm(detail),
      secondary: { label: 'Annuleren' },
      primary: {
        label: 'Opslaan',
        keepOpen: true,
        onClick: () => { this.submitTalentpoolConsent(handle, kind, itemId, candidateId); },
      },
    });
    this.wireTalentpoolConsentForm();
  },

  talentpoolConsentForm(detail) {
    const scope = detail.consent_scope || '';
    return html`
      <div id="candidateTalentpoolAlert"></div>
      <fieldset class="form-group">
        <legend class="form-label">Toestemming *</legend>
        <div class="form-check">
          <input class="form-check-input" type="radio" name="tpConsent" id="tpConsentGrant" value="grant" checked>
          <label class="form-check-label" for="tpConsentGrant">Vastleggen</label>
        </div>
        <div class="form-check">
          <input class="form-check-input" type="radio" name="tpConsent" id="tpConsentWithdraw" value="withdraw">
          <label class="form-check-label" for="tpConsentWithdraw">Intrekken</label>
        </div>
      </fieldset>
      <div class="form-group" id="tpScopeGroup">
        <label class="form-label" for="tpScope">Omvang *</label>
        <select class="form-select" id="tpScope">
          <option value="">(kies een omvang)</option>
          ${TALENTPOOL_CONSENT_SCOPES.map(s => html`
            <option value="${s}" ${raw(scope === s ? 'selected' : '')}>${AdminLabels.label('toestemmingsomvang', s)}</option>`)}
        </select>
        <div class="invalid-feedback" id="tpScopeError"></div>
      </div>
      <div class="form-group mb-0">
        <div class="form-hint fs-xs a-soft" id="tpEvidenceHint">Waar blijkt de toestemming uit? Bijvoorbeeld: ondertekend formulier van 2 september, of e-mail in het dossier.</div>
        <label class="form-label" for="tpEvidence">Bewijs van toestemming *</label>
        <textarea class="a-textarea" id="tpEvidence" rows="3" aria-describedby="tpEvidenceHint tpEvidenceError"></textarea>
        <div class="invalid-feedback" id="tpEvidenceError"></div>
        <div class="fs-xs" id="tpEvidenceCount" aria-live="polite"></div>
      </div>
      <p class="fs-xs a-soft mt-3 mb-0">Bij het vastleggen geldt een termijn van 12 maanden. Deze notitie komt in het auditlog; e-mailadressen erin worden automatisch onleesbaar gemaakt.</p>
    `;
  },

  wireTalentpoolConsentForm() {
    const grant = document.getElementById('tpConsentGrant');
    const withdraw = document.getElementById('tpConsentWithdraw');
    const scopeEl = document.getElementById('tpScope');
    const evidenceEl = document.getElementById('tpEvidence');
    const toggleScope = () => {
      const isGrant = grant.checked;
      scopeEl.disabled = !isGrant;
      if (!isGrant) {
        scopeEl.classList.remove('is-invalid');
        const err = document.getElementById('tpScopeError');
        if (err) err.textContent = '';
      }
    };
    grant.addEventListener('change', toggleScope);
    withdraw.addEventListener('change', toggleScope);
    toggleScope();
    this._wireBlurValidate(evidenceEl, () => this._validateEvidence(evidenceEl, 'tpEvidenceError'));
    this._wireEvidenceCounter(evidenceEl, 'tpEvidenceCount');
  },

  async submitTalentpoolConsent(handle, kind, itemId, candidateId) {
    const grant = document.getElementById('tpConsentGrant');
    const withdraw = document.getElementById('tpConsentWithdraw');
    const scopeEl = document.getElementById('tpScope');
    const evidenceEl = document.getElementById('tpEvidence');
    const consent = !!(grant && grant.checked);

    let valid = this._validateEvidence(evidenceEl, 'tpEvidenceError');
    const scopeErr = document.getElementById('tpScopeError');
    if (consent) {
      const scopeOk = !!scopeEl.value;
      scopeEl.classList.toggle('is-invalid', !scopeOk);
      if (scopeErr) scopeErr.textContent = scopeOk ? '' : 'Kies een omvang.';
      if (!scopeOk) valid = false;
    } else {
      scopeEl.classList.remove('is-invalid');
      if (scopeErr) scopeErr.textContent = '';
    }
    // Geen aanroep bij een ongeldig formulier: de backend hoeft dit
    // gesprek niet te voeren.
    if (!valid) return;

    this.candidateModalAlert('candidateTalentpoolAlert', '');
    handle.setBusy(true);
    const fields = [grant, withdraw, scopeEl, evidenceEl];
    fields.forEach(n => n && (n.disabled = true));
    try {
      const payload = { consent, evidence: evidenceEl.value.trim() };
      if (consent) payload.scope = scopeEl.value;
      const res = await Auth.fetch(`/v1/admin/candidates/${candidateId}/talentpool-consent`, {
        method: 'PATCH', body: JSON.stringify(payload),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        handle.close();
        Auth.toast('Toestemming bijgewerkt', 'success');
        // security-auditor MEDIUM 2 op b9d5b21: de PATCH-RETURNING draagt
        // consent_withdrawn_at nooit mee (dat stempelt de intrek-tak wel),
        // dus een merge van deze respons kan een ingetrokken status
        // stilzwijgend verbergen. force:true dwingt een verse GET af,
        // zodat de kaart nooit méér toestemming toont dan de backend nu
        // echt vastheeft.
        this.switchCandidateTab(kind, itemId, 'toestemmingen', { force: true });
        return;
      }
      this.candidateModalAlert('candidateTalentpoolAlert', this.candidateConsentErrorText(data, res && res.status));
    } catch {
      this.candidateModalAlert('candidateTalentpoolAlert', 'Netwerkfout, probeer het opnieuw.');
    }
    handle.setBusy(false);
    fields.forEach(n => n && (n.disabled = false));
    scopeEl.disabled = !(grant && grant.checked);
  },

  /* ---- Modal: Presentatie vastleggen ---- */
  async openPresentationConsentModal(kind, itemId) {
    // security-auditor HIGH 1 op b9d5b21: zie openTalentpoolConsentModal.
    const { candidateId, detail } = await this.resolveConsentDetail(kind, itemId);
    if (!candidateId || !detail) return;
    const handle = ui.modal({
      id: 'candidatePresentationModal',
      title: 'Presentatie vastleggen',
      body: html`<div id="candidatePresentationAlert"></div><div class="a-state-block"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>`,
      secondary: { label: 'Annuleren' },
      primary: {
        label: 'Opslaan',
        keepOpen: true,
        onClick: () => { this.submitPresentationConsent(handle, kind, itemId, candidateId); },
      },
    });
    this.fillPresentationConsentModal(handle, detail);
  },

  async fillPresentationConsentModal(handle, detail) {
    // code-reviewer LOW 5 op b9d5b21: zolang de vacaturelijst nog niet
    // binnen is, bestaat #spEvidence niet. Zonder deze knop-vergrendeling
    // gooit een klik op "Opslaan" in dat venster een TypeError in
    // submitPresentationConsent (_validateEvidence op een null-element).
    handle.setBusy(true);
    let jobs = [];
    try {
      const res = await Auth.fetch('/v1/admin/jobs?status=open&limit=200');
      if (res && res.ok) {
        const data = await res.json();
        jobs = data.items || [];
      }
    } catch { /* lege lijst: het formulier meldt dat er niets te kiezen valt */ }
    handle.setBody(this.presentationConsentForm(detail, jobs));
    this.wirePresentationConsentForm();
    handle.setBusy(false);
  },

  presentationConsentForm(detail, jobs) {
    const currentJobId = detail.consent_spec_presentation_job_id;
    return html`
      <div id="candidatePresentationAlert"></div>
      <fieldset class="form-group">
        <legend class="form-label">Toestemming *</legend>
        <div class="form-check">
          <input class="form-check-input" type="radio" name="spConsent" id="spConsentGrant" value="grant" checked>
          <label class="form-check-label" for="spConsentGrant">Vastleggen</label>
        </div>
        <div class="form-check">
          <input class="form-check-input" type="radio" name="spConsent" id="spConsentWithdraw" value="withdraw">
          <label class="form-check-label" for="spConsentWithdraw">Intrekken</label>
        </div>
      </fieldset>
      <div class="form-group" id="spJobGroup">
        <div class="form-hint fs-xs a-soft">Toestemming voor presentatie geldt per rol, niet in het algemeen.</div>
        <label class="form-label" for="spJob">Vacature *</label>
        <select class="form-select" id="spJob" ${raw(jobs.length ? '' : 'disabled')}>
          <option value="">(kies een vacature)</option>
          ${jobs.map(j => html`
            <option value="${j.id}" ${raw(currentJobId === j.id ? 'selected' : '')}>${j.title} · ${j.company_name} · #${j.id}</option>`)}
        </select>
        <div class="invalid-feedback" id="spJobError"></div>
        ${!jobs.length ? html`<div class="fs-xs a-soft mt-1">Er zijn geen open vacatures om te kiezen.</div>` : ''}
      </div>
      <div class="form-group mb-0">
        <div class="form-hint fs-xs a-soft" id="spEvidenceHint">Waar blijkt de toestemming uit? Bijvoorbeeld: ondertekend formulier van 2 september, of e-mail in het dossier.</div>
        <label class="form-label" for="spEvidence">Bewijs van toestemming *</label>
        <textarea class="a-textarea" id="spEvidence" rows="3" aria-describedby="spEvidenceHint spEvidenceError"></textarea>
        <div class="invalid-feedback" id="spEvidenceError"></div>
        <div class="fs-xs" id="spEvidenceCount" aria-live="polite"></div>
      </div>
    `;
  },

  wirePresentationConsentForm() {
    const grant = document.getElementById('spConsentGrant');
    const withdraw = document.getElementById('spConsentWithdraw');
    const jobEl = document.getElementById('spJob');
    const evidenceEl = document.getElementById('spEvidence');
    const hasJobs = jobEl && jobEl.options.length > 1;
    const toggleJob = () => {
      const isGrant = grant.checked;
      jobEl.disabled = !isGrant || !hasJobs;
      if (!isGrant) {
        jobEl.classList.remove('is-invalid');
        const err = document.getElementById('spJobError');
        if (err) err.textContent = '';
      }
    };
    grant.addEventListener('change', toggleJob);
    withdraw.addEventListener('change', toggleJob);
    toggleJob();
    this._wireBlurValidate(evidenceEl, () => this._validateEvidence(evidenceEl, 'spEvidenceError'));
    this._wireEvidenceCounter(evidenceEl, 'spEvidenceCount');
  },

  async submitPresentationConsent(handle, kind, itemId, candidateId) {
    const grant = document.getElementById('spConsentGrant');
    const withdraw = document.getElementById('spConsentWithdraw');
    const jobEl = document.getElementById('spJob');
    const evidenceEl = document.getElementById('spEvidence');
    const consent = !!(grant && grant.checked);

    let valid = this._validateEvidence(evidenceEl, 'spEvidenceError');
    const jobErr = document.getElementById('spJobError');
    if (consent) {
      const jobOk = !!jobEl.value;
      jobEl.classList.toggle('is-invalid', !jobOk);
      if (jobErr) jobErr.textContent = jobOk ? '' : 'Kies een vacature.';
      if (!jobOk) valid = false;
    } else {
      jobEl.classList.remove('is-invalid');
      if (jobErr) jobErr.textContent = '';
    }
    if (!valid) return;

    this.candidateModalAlert('candidatePresentationAlert', '');
    handle.setBusy(true);
    const fields = [grant, withdraw, jobEl, evidenceEl];
    fields.forEach(n => n && (n.disabled = true));
    try {
      const payload = { consent, evidence: evidenceEl.value.trim() };
      if (consent) payload.job_id = Number(jobEl.value);
      const res = await Auth.fetch(`/v1/admin/candidates/${candidateId}/spec-presentation-consent`, {
        method: 'PATCH', body: JSON.stringify(payload),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        handle.close();
        Auth.toast('Toestemming bijgewerkt', 'success');
        // security-auditor MEDIUM 2 op b9d5b21: zie submitTalentpoolConsent.
        this.switchCandidateTab(kind, itemId, 'toestemmingen', { force: true });
        return;
      }
      this.candidateModalAlert('candidatePresentationAlert', this.candidateConsentErrorText(data, res && res.status));
    } catch {
      this.candidateModalAlert('candidatePresentationAlert', 'Netwerkfout, probeer het opnieuw.');
    }
    handle.setBusy(false);
    fields.forEach(n => n && (n.disabled = false));
    jobEl.disabled = !(grant && grant.checked) || jobEl.options.length <= 1;
  },

  /* ============================================================
     REFERRAL-INTAKE
     ============================================================ */
  openReferralModal() {
    const handle = ui.modal({
      id: 'candidateReferralModal',
      title: 'Referral vastleggen',
      wide: true,
      body: this.referralForm(),
      secondary: { label: 'Annuleren' },
      primary: {
        label: 'Vastleggen',
        keepOpen: true,
        onClick: () => { this.submitReferral(handle); },
      },
    });
    this.wireReferralForm();
  },

  referralForm() {
    return html`
      <div id="candidateReferralAlert"></div>
      <div class="form-group">
        <label class="form-label" for="refFullName">Volledige naam *</label>
        <input type="text" class="form-control" id="refFullName" maxlength="200">
        <div class="invalid-feedback" id="refFullNameError"></div>
      </div>
      <div class="form-group">
        <label class="form-label" for="refEmail">E-mailadres *</label>
        <input type="email" class="form-control" id="refEmail">
        <div class="invalid-feedback" id="refEmailError"></div>
      </div>
      <div class="form-group">
        <div class="form-hint fs-xs a-soft" id="refReferredByHint">Deze naam staat in de kennisgeving die deze persoon ontvangt.</div>
        <label class="form-label" for="refReferredBy">Aangedragen door *</label>
        <input type="text" class="form-control" id="refReferredBy" maxlength="200" aria-describedby="refReferredByHint">
        <div class="invalid-feedback" id="refReferredByError"></div>
      </div>
      <div class="form-group">
        <div class="form-hint fs-xs a-soft" id="refEvidenceHint">Wat heeft de aandrager verteld, en wanneer? Bijvoorbeeld: mondeling bevestigd door X op 3 september, hij heeft haar gevraagd.</div>
        <label class="form-label" for="refEvidence">Bewijs van toestemming *</label>
        <textarea class="a-textarea" id="refEvidence" rows="3" aria-describedby="refEvidenceHint refEvidenceError"></textarea>
        <div class="invalid-feedback" id="refEvidenceError"></div>
        <div class="fs-xs" id="refEvidenceCount" aria-live="polite"></div>
      </div>
      <div class="form-group">
        <label class="form-label" for="refNote">Interne notitie</label>
        <textarea class="a-textarea" id="refNote" rows="2" maxlength="2000"></textarea>
      </div>
      <div class="a-panel mb-0">
        <!-- chief-of-staff op 3c8f690: deze tekst moet identiek zijn aan
             wat _REFERRAL_ART14_NL (email_templates.py:524-535) en
             _REFERRAL_TEXT (email_templates.py:558-568) daadwerkelijk
             zeggen. De vorige versie noemde een opsomming van gegevens en
             een doel die de mail niet geeft, en "vervalt na drie maanden"
             terwijl de rij na drie maanden juist op de beoordelingslijst
             komt (REFERRAL_NO_RESPONSE_SQL), niet verdwijnt. -->
        <p class="a-soft mb-0">Deze persoon ontvangt eenmalig een kennisgeving met een bevestigingslink, geldig 24 uur.
          Daarin staat: dat wij zijn of haar gegevens op de datum van vandaag hebben ontvangen via een aanbeveling van
          <strong id="referralInfoName">(nog niet ingevuld)</strong>, met toestemming; dat wij ze drie maanden bewaren
          als er geen reactie komt; en het recht op inzage, bezwaar (art. 21) en afmelden met STOP. De kennisgeving
          bevat geen vacature en geen wervende tekst. Zonder bevestiging doen wij niets met de gegevens; na drie
          maanden komt de invoer op de beoordelingslijst in Bewaartermijnen.</p>
      </div>
    `;
  },

  wireReferralForm() {
    const fullNameEl = document.getElementById('refFullName');
    const emailEl = document.getElementById('refEmail');
    const referredByEl = document.getElementById('refReferredBy');
    const evidenceEl = document.getElementById('refEvidence');
    const infoName = document.getElementById('referralInfoName');
    // Live sync via textContent, nooit via innerHTML: geen escaping nodig
    // omdat er geen markup wordt geïnterpreteerd.
    referredByEl.addEventListener('input', () => {
      infoName.textContent = referredByEl.value.trim() || '(nog niet ingevuld)';
    });
    this._wireBlurValidate(fullNameEl, () => this._validateRequired(fullNameEl, 'refFullNameError', { max: 200 }));
    this._wireBlurValidate(emailEl, () => this._validateEmail(emailEl, 'refEmailError'));
    this._wireBlurValidate(referredByEl, () => this._validateRequired(referredByEl, 'refReferredByError', { max: 200 }));
    this._wireBlurValidate(evidenceEl, () => this._validateEvidence(evidenceEl, 'refEvidenceError'));
    this._wireEvidenceCounter(evidenceEl, 'refEvidenceCount');
  },

  async submitReferral(handle) {
    const fullNameEl = document.getElementById('refFullName');
    const emailEl = document.getElementById('refEmail');
    const referredByEl = document.getElementById('refReferredBy');
    const evidenceEl = document.getElementById('refEvidence');
    const noteEl = document.getElementById('refNote');

    const vFullName = this._validateRequired(fullNameEl, 'refFullNameError', { max: 200 });
    const vEmail = this._validateEmail(emailEl, 'refEmailError');
    const vReferredBy = this._validateRequired(referredByEl, 'refReferredByError', { max: 200 });
    const vEvidence = this._validateEvidence(evidenceEl, 'refEvidenceError');
    if (!(vFullName && vEmail && vReferredBy && vEvidence)) return;

    this.candidateModalAlert('candidateReferralAlert', '');
    handle.setBusy(true);
    const fields = [fullNameEl, emailEl, referredByEl, evidenceEl, noteEl];
    fields.forEach(n => n && (n.disabled = true));
    try {
      const payload = {
        full_name: fullNameEl.value.trim(),
        email: emailEl.value.trim(),
        referred_by: referredByEl.value.trim(),
        evidence: evidenceEl.value.trim(),
        note: noteEl.value.trim() || null,
      };
      const res = await Auth.fetch('/v1/admin/candidates/referral', {
        method: 'POST', body: JSON.stringify(payload),
      });
      const data = res ? await res.json().catch(() => null) : null;
      if (res && res.ok) {
        handle.close();
        Auth.toast('Referral vastgelegd', 'success');
        await this.loadCandidates(this._lastParams.candidates || {});
        return;
      }
      this.showReferralError(data, res && res.status);
    } catch {
      this.candidateModalAlert('candidateReferralAlert', 'Netwerkfout, probeer het opnieuw.');
    }
    handle.setBusy(false);
    fields.forEach(n => n && (n.disabled = false));
  },

  // §7.3.2: twee eigen 409's op detail.code (BV3, referral_email_suppressed
  // en referral_candidate_exists met een knop), en de generieke terugval
  // voor elke andere code (§7.2f punt 3).
  showReferralError(data, status) {
    if (status === 401 || status === 403) {
      this.candidateModalAlert('candidateReferralAlert', 'Je hebt geen rechten voor deze handeling.');
      return;
    }
    const d = this.errorDetail(data);
    if (d.code === 'referral_email_suppressed') {
      this.candidateModalAlert('candidateReferralAlert',
        'Dit adres staat op de suppressielijst. Er mag geen bericht naar dit adres, op geen enkele grondslag.');
      return;
    }
    if (d.code === 'referral_candidate_exists') {
      const candidateId = d.extra && d.extra.candidate_id;
      this.candidateModalAlert('candidateReferralAlert',
        'Er is al een kandidaat met dit adres. Open dat dossier; een referral-invoer mag een bestaande grondslag niet overschrijven.',
        { action: 'candidate-referral-open-existing', actionLabel: 'Kandidaat openen', candidateId });
      return;
    }
    this.candidateModalAlert('candidateReferralAlert', this.candidateConsentErrorText(data, status));
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
      'candidate-tab': (el) => Admin.switchCandidateTab(el.dataset.kind, Number(el.dataset.id), el.dataset.tab),
      'candidate-talentpool-edit': (el) => Admin.openTalentpoolConsentModal(el.dataset.kind, Number(el.dataset.id)),
      'candidate-presentation-edit': (el) => Admin.openPresentationConsentModal(el.dataset.kind, Number(el.dataset.id)),
      'open-referral-modal': () => Admin.openReferralModal(),
      'candidate-referral-open-existing': (el) => {
        const id = Number(el.dataset.candidateId);
        if (!id) return;
        ui.closeTop();
        Admin.viewCandidate('sourced', id);
      },
    },
  });
})();
