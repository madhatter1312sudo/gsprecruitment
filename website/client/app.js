    /* ================================================================
       Client Portal — Full API integration
       ================================================================ */

    const user = Auth.requireAuth(['client']);
    if (!user) {}

    // WS-B.2: show the "viewing as" banner + return-to-admin control when
    // this session is an admin impersonating this client.
    if (user) Auth.renderImpersonationBanner();

    /* ---- WS-E.2: e-mail verification gate ----
       Auth.requireAuth() only checks the JWT is valid; is_verified is a
       separate, backend-enforced gate (core/deps.py get_verified_user
       returns 403 on every /v1/client/* endpoint until confirmed). The
       further approved_by_admin_at gate (routers/client.py
       _require_candidate_access) only affects the candidate-search
       section, not the whole portal, so it isn't blocked here -- a client
       can see jobs/team/analytics while awaiting approval; the candidate
       search section itself surfaces its own 403 message from the API. */
    function showUnverifiedOverlay() {
      const overlay = document.getElementById('unverifiedOverlay');
      const layout = document.getElementById('portalLayout');
      overlay.style.display = 'flex';
      layout?.setAttribute('aria-hidden', 'true');
      Auth.trapFocus(overlay);
    }

    function hideUnverifiedOverlay() {
      const overlay = document.getElementById('unverifiedOverlay');
      const layout = document.getElementById('portalLayout');
      Auth.releaseFocusTrap(overlay);
      overlay.style.display = 'none';
      layout?.removeAttribute('aria-hidden');
    }

    if (user && !user.is_verified) {
      showUnverifiedOverlay();
      document.getElementById('unverifiedLogoutBtn')?.addEventListener('click', () => Auth.logout());
      document.getElementById('resendVerifyBtn')?.addEventListener('click', async (e) => {
        const btn = e.currentTarget;
        const msg = document.getElementById('resendVerifyMsg');
        btn.disabled = true;
        try {
          const res = await fetch(`${Auth.API}/auth/resend-verification`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: user.email }),
          });
          if (res.ok && msg) {
            msg.textContent = 'Check your inbox for the new link. / Controleer je inbox voor de nieuwe link.';
            msg.style.display = 'block';
          }
        } catch (err) {
          if (msg) {
            msg.textContent = 'Network error — please try again. / Netwerkfout — probeer het opnieuw.';
            msg.style.display = 'block';
          }
        } finally {
          btn.disabled = false;
        }
      });
      throw new Error('unverified'); // stop the rest of this script block (dashboard fetches, listeners)
    }

    /* ================================================================
       WS5 #139/#140: shared pipeline-stage and source-family label maps.
       Mirrors website/admin/js/labels.js's `pipelinefase` map and
       SITE-DESIGN-SPEC.md §7.2e's source table verbatim (same seven
       stages, same seven Dutch labels, same source labels) so "Screening"
       and "Apollo" read the same word in both the client portal and the
       admin panel -- but as its own copy, not an import, because the
       portal does not load admin/js/*.js (§7.5.6, admin bundle stays
       admin-only). The seven values themselves come from migration 043
       (BV8) via models/schemas.py's PipelineStage literal.
       ================================================================ */
    const CANONICAL_STAGES = ['sourced', 'new', 'screening', 'interview', 'offer', 'placed', 'rejected'];
    const STAGE_LABELS = {
      sourced: 'Gesourced', new: 'Nieuw', screening: 'Screening',
      interview: 'Gesprek', offer: 'Aanbod', placed: 'Geplaatst', rejected: 'Afgewezen',
    };
    function stageLabel(stage) {
      if (stage == null || stage === '') return '(leeg)';
      return STAGE_LABELS[stage] || String(stage);
    }
    // SOURCE_FAMILY (core/sources.py) already folds apollo_bulk into
    // 'apollo' server-side, so the client only ever sees these four keys
    // plus, per §7.2e, a free-form value passed unchanged.
    const SOURCE_LABELS = {
      portal_registration: 'Zelf geregistreerd',
      talentpool_optin: 'Talentpool-aanmelding',
      apollo: 'Apollo',
      agent: 'Externe agent',
    };
    function sourceLabel(source) {
      if (source == null || source === '') return '(onbekend)';
      return SOURCE_LABELS[source] || String(source);
    }

    // ACTIVITY_TYPES (routers/activities.py) -- own copy of
    // admin/js/labels.js's `activiteit` map, same six Dutch labels
    // (SITE-DESIGN-SPEC.md §7.3.6b, reused by #141 per §7.3.8c).
    const ACTIVITY_TYPE_LABELS = {
      note: 'Notitie', call: 'Telefoongesprek', email: 'E-mail',
      meeting: 'Afspraak', task: 'Taak', status_change: 'Statuswijziging',
    };
    function activityTypeLabel(type) {
      return ACTIVITY_TYPE_LABELS[type] || String(type || '—');
    }

    const sectionTitles = {
      dashboard: { en: 'Dashboard', nl: 'Dashboard' },
      jobs: { en: 'Job Management', nl: 'Vacatures' },
      candidates: { en: 'Candidate Search', nl: 'Kandidaten Zoeken' },
      analytics: { en: 'Analytics', nl: 'Analytics' },
      team: { en: 'Team', nl: 'Team' },
      settings: { en: 'Settings', nl: 'Instellingen' }
    };

    function navigateTo(section) {
      document.querySelectorAll('.sidebar-nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.section === section);
      });
      document.querySelectorAll('.portal-section').forEach(s => {
        s.classList.toggle('active', s.id === `section-${section}`);
      });
      const title = sectionTitles[section] || sectionTitles.dashboard;
      const enEl = document.querySelector('#pageTitle .lang-en');
      const nlEl = document.querySelector('#pageTitle .lang-nl');
      if (enEl) enEl.textContent = title.en;
      if (nlEl) nlEl.textContent = title.nl;
      window.location.hash = section;
      document.getElementById('sidebar').classList.remove('open');
      // Load section data
      if (section === 'dashboard') loadDashboard();
      else if (section === 'jobs') loadJobs();
      else if (section === 'analytics') loadAnalytics();
      else if (section === 'team') loadTeam();
      else if (section === 'settings') {
        loadClientProfile();
        loadContacts();
        loadActivitySubjects();
        loadActivities();
      }
    }

    document.querySelectorAll('.sidebar-nav-item').forEach(item => {
      item.addEventListener('click', () => navigateTo(item.dataset.section));
    });

    const hash = window.location.hash.replace('#', '');
    if (hash && sectionTitles[hash]) navigateTo(hash);

    const mobileBtn = document.getElementById('mobileMenuBtn');
    const sidebar = document.getElementById('sidebar');
    if (window.innerWidth <= 768) mobileBtn.style.display = '';
    window.addEventListener('resize', () => {
      mobileBtn.style.display = window.innerWidth <= 768 ? '' : 'none';
      syncKanbanAria();
    });

    // Boven 600px tonen alle kolommen hun kaarten altijd (CSS), ongeacht
    // .active -- aria-expanded volgt dat zichtbare gedrag in plaats van de
    // accordeontoestand die er onder 600px wel toe doet.
    function syncKanbanAria() {
      const wide = window.innerWidth > 600;
      document.querySelectorAll('#kanbanBoard .kanban-column h4 button').forEach((btn) => {
        btn.setAttribute('aria-expanded', wide || btn.closest('.kanban-column').classList.contains('active') ? 'true' : 'false');
      });
    }
    mobileBtn.addEventListener('click', () => sidebar.classList.toggle('open'));

    /* ---- Populate sidebar user ---- */
    if (user) {
      const name = user.full_name || user.name || 'Client';
      const email = user.email || 'client@company.com';
      const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
      document.getElementById('sidebarName').textContent = name;
      document.getElementById('sidebarEmail').textContent = email;
      document.getElementById('sidebarAvatar').textContent = initials;
    }

    /* ================================================================
       API: Load Dashboard
       ================================================================ */
    async function loadDashboard() {
      try {
        const [dashRes, pipelineRes] = await Promise.all([
          Auth.fetch('/v1/client/dashboard'),
          Auth.fetch('/v1/client/pipeline?limit=10'),
        ]);
        const dash = dashRes ? await dashRes.json() : {};
        const pipelineData = pipelineRes ? await pipelineRes.json() : { items: [] };

        // Stats
        document.querySelectorAll('#section-dashboard .stats-grid .stat-card .stat-value')[0].textContent = dash.active_jobs ?? 0;
        document.querySelectorAll('#section-dashboard .stats-grid .stat-card .stat-value')[1].textContent = dash.total_candidates_matched ?? 0;
        document.querySelectorAll('#section-dashboard .stats-grid .stat-card .stat-value')[2].textContent = dash.candidates_in_pipeline ?? 0;
        document.querySelectorAll('#section-dashboard .stats-grid .stat-card .stat-value')[3].textContent = dash.placements ?? 0;

        // Recent activity (dashboard widget -- separate from the WS5 #141
        // "Activiteiten" settings card, which reads GET /v1/client/activities)
        const activityContainer = document.getElementById('clientActivity');
        if (activityContainer && pipelineData.items?.length > 0) {
          const recent = pipelineData.items.slice(0, 3);
          activityContainer.innerHTML = recent.map(pe => {
            const time = pe.created_at ? new Date(pe.created_at).toLocaleDateString() : '';
            const name = pe.full_name || null; // gated by presentation consent, see loadKanban()
            return `<div class="activity-item">
              <div class="activity-icon" style="background:rgba(34,197,94,0.1);color:#4ade80;"><i class="fa-regular fa-user-plus"></i></div>
              <div class="activity-content">
                <div class="activity-text lang-en">${GSP.esc(name || 'Candidate #' + pe.candidate_id)} added to ${GSP.esc(pe.job_title || 'pipeline')}</div>
                <div class="activity-text lang-nl">${GSP.esc(name || 'Kandidaat #' + pe.candidate_id)} toegevoegd aan ${GSP.esc(pe.job_title || 'pipeline')}</div>
                <div class="activity-time">${GSP.esc(time)}</div>
              </div>
            </div>`;
          }).join('');
        }
      } catch (err) {
        console.error('Dashboard load error:', err);
      }
      loadKanban();
    }

    /* ================================================================
       WS5 #139: Kanban pipeline -- seven canonical stages plus a trailing
       column for a stage outside that list. See SITE-DESIGN-SPEC.md
       §7.3.8(a). Stage change is a <select> per card, optimistic with
       rollback on failure; PATCH /v1/client/pipeline/{id}/stage is the
       only write, exactly the same route the old four-column build
       already called for reads.
       ================================================================ */
    const kanbanBoardEl = () => document.getElementById('kanbanBoard');

    function kanbanLoadingHtml() {
      // "zeven kolomkoppen met elk twee vlakke kaartblokken" -- flat,
      // content-free card blocks, not a shimmer (house rule: no shimmer
      // skeletons, §7.4 rule 6).
      return CANONICAL_STAGES.map(stage => `
        <div class="kanban-column">
          <h4><button type="button" tabindex="-1"><span>${GSP.esc(stageLabel(stage))}</span></button></h4>
          <div class="kanban-card kanban-card--loading"></div>
          <div class="kanban-card kanban-card--loading"></div>
        </div>`).join('');
    }

    function kanbanCardHtml(entry) {
      const hasName = !!entry.full_name;
      const nameNl = hasName ? GSP.esc(entry.full_name) : `Kandidaat #${Number(entry.candidate_id) || 0}`;
      const nameEn = hasName ? GSP.esc(entry.full_name) : `Candidate #${Number(entry.candidate_id) || 0}`;
      const jobTitle = GSP.esc(entry.job_title || '');
      const changed = entry.updated_at ? new Date(entry.updated_at).toLocaleDateString() : '';
      return `<div class="kanban-card" data-entry-id="${Number(entry.id) || 0}" data-candidate-id="${Number(entry.candidate_id) || 0}">
        <h5 class="lang-en">${nameEn}</h5><h5 class="lang-nl">${nameNl}</h5>
        <p class="fs-xs a-soft">${jobTitle}</p>
        <p class="fs-xs a-soft">${GSP.esc(changed)}</p>
        <select aria-label="Fase" data-original-stage="${GSP.esc(entry.stage ?? '')}">${kanbanStageOptions(entry.stage)}</select>
      </div>`;
    }

    // Zeven canonieke opties plus, wanneer de huidige fase daarbuiten valt
    // (of leeg is -- de kolom heeft geen NOT NULL), een achtste,
    // geselecteerde optie met de ruwe waarde: dezelfde ontsnappingsklep als
    // de admin-select (website/admin/js/admin.js pipelineStageOptions()),
    // eigen kopie, geen import. Die achtste optie wordt nooit verzonden
    // (zie handleStageChange).
    function kanbanStageOptions(currentStage) {
      const known = CANONICAL_STAGES.includes(currentStage);
      let html = CANONICAL_STAGES.map(s =>
        `<option value="${s}" ${s === currentStage ? 'selected' : ''}>${GSP.esc(stageLabel(s))}</option>`
      ).join('');
      if (!known) {
        const value = currentStage ?? '';
        html += `<option value="${GSP.esc(value)}" selected>${GSP.esc(stageLabel(currentStage))} (bestaande waarde)</option>`;
      }
      return html;
    }

    function kanbanColumnHtml(stage, items, opts = {}) {
      const label = opts.rawLabel ? GSP.esc(stage) : GSP.esc(stageLabel(stage));
      const title = opts.rawLabel ? ' title="Fase buiten het standaardoverzicht"' : '';
      const cards = items.map(kanbanCardHtml).join('');
      const empty = items.length
        ? ''
        : '<div class="kanban-empty"><span class="lang-en">No candidates in this stage</span><span class="lang-nl">Geen kandidaten in deze fase</span></div>';
      return `<div class="kanban-column" data-stage="${GSP.esc(stage)}"${title}>
        <h4><button type="button" data-action="toggle-kanban-column" aria-expanded="true"><span>${label}</span><span class="gsp-num">${items.length}</span></button></h4>
        ${cards}${empty}
      </div>`;
    }

    function renderKanbanEmptyState() {
      const el = kanbanBoardEl();
      if (!el) return;
      el.innerHTML = `<div class="kanban-card" style="flex:1;text-align:center;">
        <p><span class="lang-en">There are no candidates in the pipeline yet.</span><span class="lang-nl">Er staan nog geen kandidaten in de pipeline.</span></p>
        <button type="button" class="btn btn-primary" data-action="goto-create-job">
          <span class="lang-en">Post a job</span><span class="lang-nl">Vacature plaatsen</span>
        </button>
      </div>`;
    }

    function renderKanban(items) {
      const el = kanbanBoardEl();
      if (!el) return;
      if (!items.length) { renderKanbanEmptyState(); return; }

      const byStage = {};
      CANONICAL_STAGES.forEach(s => { byStage[s] = []; });
      const extra = []; // [rawStage, items[]] in first-seen order, for a stage outside the seven
      const extraIndex = {};
      items.forEach(entry => {
        const stage = entry.stage;
        if (CANONICAL_STAGES.includes(stage)) {
          byStage[stage].push(entry);
          return;
        }
        const key = stage ?? '';
        if (!(key in extraIndex)) {
          extraIndex[key] = extra.length;
          extra.push([stage, []]);
        }
        extra[extraIndex[key]][1].push(entry);
      });

      let html = CANONICAL_STAGES.map(s => kanbanColumnHtml(s, byStage[s])).join('');
      html += extra.map(([stage, list]) => kanbanColumnHtml(stage, list, { rawLabel: true })).join('');
      el.innerHTML = html;

      // §7.3.8(a) 390px: verticale accordeon, eerste fase met inhoud open.
      const firstNonEmpty = el.querySelector('.kanban-column:not(:has(.kanban-empty))')
        || el.querySelector('.kanban-column');
      if (firstNonEmpty) setKanbanColumnOpen(firstNonEmpty, true);
      syncKanbanAria();
    }

    function setKanbanColumnOpen(columnEl, open) {
      columnEl.classList.toggle('active', open);
      const btn = columnEl.querySelector('h4 button');
      if (btn) btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    async function loadKanban() {
      const el = kanbanBoardEl();
      if (!el) return;
      el.innerHTML = kanbanLoadingHtml();
      try {
        const res = await Auth.fetch('/v1/client/pipeline?limit=200');
        if (!res) return;
        const data = await res.json();
        if (!res.ok) throw new Error();
        renderKanban(data.items || []);
      } catch (err) {
        console.error('Kanban load error:', err);
        Auth.renderLoadError(el, () => loadKanban());
      }
    }

    function kanbanStageErrorText(status) {
      if (status === 401 || status === 403) return 'Je hebt geen rechten voor deze wijziging.';
      if (status === 404) return 'Deze kandidaat staat niet meer in de pipeline. Ververs de pagina.';
      if (status === 422) return 'Deze fase is ongeldig. Kies een van de zeven fasen.';
      return 'Er ging iets mis, probeer het opnieuw.';
    }

    // Stagewijziging (§7.3.8a): de <select> zelf is de optimistische
    // update -- de kaart verhuist meteen naar de gekozen kolom, de PATCH
    // gaat op de achtergrond mee. Bij een 4xx/5xx verhuist de kaart terug
    // en toont Auth.toast de foutmelding; bij succes blijft hij staan.
    async function handleStageChange(selectEl) {
      const cardEl = selectEl.closest('.kanban-card');
      const oldColumnEl = selectEl.closest('.kanban-column');
      if (!cardEl || !oldColumnEl) return;
      const entryId = cardEl.dataset.entryId;
      const newStage = selectEl.value;
      const originalStage = selectEl.dataset.originalStage;
      if (!CANONICAL_STAGES.includes(newStage) || newStage === originalStage) {
        // De ontsnappingsklep-optie mag nooit verzonden worden (§7.3.8a:
        // "niets wordt stilzwijgend verplaatst"); zonder wijziging is er
        // ook niets te bewaren.
        selectEl.value = originalStage;
        return;
      }

      let newColumnEl = kanbanBoardEl()?.querySelector(`.kanban-column[data-stage="${CSS.escape(newStage)}"]`);
      if (!newColumnEl) return; // one of the seven canonical columns always exists
      selectEl.disabled = true;
      moveKanbanCard(cardEl, oldColumnEl, newColumnEl);

      try {
        const res = await Auth.fetch(`/v1/client/pipeline/${entryId}/stage`, {
          method: 'PATCH', body: JSON.stringify({ stage: newStage }),
        });
        if (res && res.ok) {
          selectEl.dataset.originalStage = newStage;
          selectEl.disabled = false;
          Auth.toast('Fase bijgewerkt', 'success');
          return;
        }
        moveKanbanCard(cardEl, newColumnEl, oldColumnEl);
        selectEl.value = originalStage;
        selectEl.disabled = false;
        Auth.toast(kanbanStageErrorText(res && res.status), 'error');
      } catch {
        moveKanbanCard(cardEl, newColumnEl, oldColumnEl);
        selectEl.value = originalStage;
        selectEl.disabled = false;
        Auth.toast('Netwerkfout, probeer het opnieuw.', 'error');
      }
    }

    function moveKanbanCard(cardEl, fromColumnEl, toColumnEl) {
      const select = cardEl.querySelector('select');
      toColumnEl.insertBefore(cardEl, toColumnEl.querySelector('.kanban-empty') || null);
      refreshKanbanColumn(fromColumnEl);
      refreshKanbanColumn(toColumnEl);
      if (select) select.focus();
    }

    function refreshKanbanColumn(columnEl) {
      const count = columnEl.querySelectorAll('.kanban-card').length;
      const countEl = columnEl.querySelector('h4 .gsp-num');
      if (countEl) countEl.textContent = count;
      let emptyEl = columnEl.querySelector('.kanban-empty');
      if (count === 0 && !emptyEl) {
        columnEl.insertAdjacentHTML('beforeend', '<div class="kanban-empty"><span class="lang-en">No candidates in this stage</span><span class="lang-nl">Geen kandidaten in deze fase</span></div>');
      } else if (count > 0 && emptyEl) {
        emptyEl.remove();
      }
    }

    /* ================================================================
       API: Load Jobs
       ================================================================ */
    async function loadJobs() {
      try {
        const res = await Auth.fetch('/v1/client/jobs?limit=50');
        if (!res) return;
        const data = await res.json();
        const list = document.getElementById('jobsList');
        if (!data.items || data.items.length === 0) {
          list.innerHTML = '<p style="color:var(--navy-200);text-align:center;padding:var(--space-2xl);">No jobs yet. Create your first job!</p>';
          return;
        }
        list.innerHTML = data.items.map(j => {
          const statusClass = {
            'open': 'badge-green', 'draft': 'badge-gray', 'closed': 'badge-red', 'filled': 'badge-purple'
          }[j.status] || 'badge-blue';
          const salary = j.salary_min && j.salary_max
            ? `€${(j.salary_min/1000).toFixed(0)}K – €${(j.salary_max/1000).toFixed(0)}K`
            : '';
          const location = j.location_type || '';
          return `<div class="job-card">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;">
              <div>
                <h4 style="font-size:var(--font-size-lg);font-weight:600;color:var(--white);">${GSP.esc(j.title || 'Untitled')}</h4>
                <p style="font-size:var(--font-size-sm);color:var(--navy-200);margin:4px 0;">${salary ? salary + ' · ' : ''}${GSP.esc(location)}${j.seniority ? ' · ' + GSP.esc(j.seniority) : ''}</p>
                <div style="display:flex;gap:var(--space-sm);margin-top:var(--space-sm);">
                  <span class="badge ${statusClass} lang-en">${GSP.esc(j.status || 'draft')}</span>
                  <span class="badge ${statusClass} lang-nl">${j.status === 'open' ? 'Actief' : j.status === 'draft' ? 'Concept' : GSP.esc(j.status)}</span>
                  ${j.department ? `<span class="badge badge-blue">${GSP.esc(j.department)}</span>` : ''}
                </div>
              </div>
              <div style="display:flex;gap:var(--space-sm);">
                <button class="btn btn-sm btn-outline" data-action="edit-job" data-id="${Number(j.id) || 0}"><i class="fa-regular fa-pen-to-square"></i></button>
                <button class="btn btn-sm btn-ghost" style="color:#f87171;" data-action="delete-job" data-id="${Number(j.id) || 0}"><i class="fa-regular fa-trash-can"></i></button>
              </div>
            </div>
          </div>`;
        }).join('');
      } catch (err) {
        console.error('Jobs load error:', err);
      }
    }

    /* ---- Edit job ---- */
    window.editJob = async function(jobId) {
      try {
        const res = await Auth.fetch(`/v1/client/jobs/${jobId}`);
        if (!res || !res.ok) { Auth.toast('Failed to load job', 'error'); return; }
        const job = await res.json();
        window.showJobModal(job);
      } catch (err) {
        Auth.toast('Error loading job', 'error');
      }
    };

    /* ---- Delete job ---- */
    window.deleteJob = async function(jobId) {
      if (!confirm('Delete this job?')) return;
      try {
        const res = await Auth.fetch(`/v1/client/jobs/${jobId}`, { method: 'DELETE' });
        if (res && res.ok) {
          Auth.toast('Job deleted', 'success');
          loadJobs();
        } else {
          Auth.toast('Failed to delete job', 'error');
        }
      } catch (err) {
        Auth.toast('Error deleting job', 'error');
      }
    };

    /* ---- Create job modal ---- */
    document.getElementById('createJobBtn').addEventListener('click', () => {
      window.showJobModal();
    });

    window.showJobModal = function(job = null) {
      const isEdit = !!job;
      const existing = document.getElementById('jobModalOverlay');
      if (existing) existing.remove();

      const overlay = document.createElement('div');
      overlay.id = 'jobModalOverlay';
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:1000;display:flex;align-items:center;justify-content:center;padding:var(--space-lg);';
      overlay.innerHTML = `
        <div style="background:var(--navy-800);border:1px solid var(--navy-600);border-radius:12px;padding:var(--space-2xl);width:100%;max-width:560px;max-height:90vh;overflow-y:auto;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-xl);">
            <h3 style="font-size:var(--font-size-lg);font-weight:600;color:var(--white);">
              <span class="lang-en">${isEdit ? 'Edit Job' : 'Create Job'}</span>
              <span class="lang-nl">${isEdit ? 'Vacature Bewerken' : 'Vacature Aanmaken'}</span>
            </h3>
            <button id="jobModalClose" class="btn btn-sm btn-ghost"><i class="fa-regular fa-xmark"></i></button>
          </div>
          <form id="jobModalForm">
            <div class="form-group">
              <label class="lang-en">Job Title *</label><label class="lang-nl">Functietitel *</label>
              <input type="text" name="title" required placeholder="e.g. Senior Embedded Software Engineer" value="${GSP.esc(job?.title || '')}">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-md);">
              <div class="form-group">
                <label class="lang-en">Department</label><label class="lang-nl">Afdeling</label>
                <input type="text" name="department" placeholder="e.g. R&D" value="${GSP.esc(job?.department || '')}">
              </div>
              <div class="form-group">
                <label class="lang-en">Seniority</label><label class="lang-nl">Niveau</label>
                <select name="seniority">
                  <option value="">Select…</option>
                  ${['junior','mid','senior','lead','executive'].map(s => `<option value="${s}" ${job?.seniority === s ? 'selected' : ''}>${s.charAt(0).toUpperCase()+s.slice(1)}</option>`).join('')}
                </select>
              </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:var(--space-md);">
              <div class="form-group">
                <label class="lang-en">Min Salary (€)</label><label class="lang-nl">Min Salaris (€)</label>
                <input type="number" name="salary_min" placeholder="50000" value="${GSP.esc(job?.salary_min ?? '')}">
              </div>
              <div class="form-group">
                <label class="lang-en">Max Salary (€)</label><label class="lang-nl">Max Salaris (€)</label>
                <input type="number" name="salary_max" placeholder="80000" value="${GSP.esc(job?.salary_max ?? '')}">
              </div>
              <div class="form-group">
                <label class="lang-en">Location Type</label><label class="lang-nl">Werkplek</label>
                <select name="location_type">
                  <option value="">Select…</option>
                  ${['remote','hybrid','onsite'].map(t => `<option value="${t}" ${job?.location_type === t ? 'selected' : ''}>${t.charAt(0).toUpperCase()+t.slice(1)}</option>`).join('')}
                </select>
              </div>
            </div>
            <div class="form-group">
              <label class="lang-en">Description</label><label class="lang-nl">Beschrijving</label>
              <textarea name="description" rows="4" placeholder="Describe the role and responsibilities…" style="width:100%;resize:vertical;">${GSP.esc(job?.description || '')}</textarea>
            </div>
            <div class="form-group">
              <label class="lang-en">Requirements</label><label class="lang-nl">Vereisten</label>
              <textarea name="requirements" rows="3" placeholder="Required skills and experience…" style="width:100%;resize:vertical;">${GSP.esc(job?.requirements || '')}</textarea>
            </div>
            <div class="form-group">
              <label class="lang-en">Nice to Have</label><label class="lang-nl">Pré</label>
              <textarea name="nice_to_have" rows="2" placeholder="Bonus skills…" style="width:100%;resize:vertical;">${GSP.esc(job?.nice_to_have || '')}</textarea>
            </div>
            <div class="form-group">
              <label class="lang-en">Urgency</label><label class="lang-nl">Urgentie</label>
              <select name="urgency">
                ${['normal','high','critical'].map(u => `<option value="${u}" ${job?.urgency === u || (!job?.urgency && u === 'normal') ? 'selected' : ''}>${u.charAt(0).toUpperCase()+u.slice(1)}</option>`).join('')}
              </select>
            </div>
            <div style="display:flex;gap:var(--space-md);justify-content:flex-end;margin-top:var(--space-xl);">
              <button type="button" id="jobModalCancelBtn" class="btn btn-outline">
                <span class="lang-en">Cancel</span><span class="lang-nl">Annuleren</span>
              </button>
              <button type="submit" class="btn btn-primary">
                <i class="fa-regular fa-floppy-disk"></i>
                <span class="lang-en">${isEdit ? 'Save Changes' : 'Create Job'}</span>
                <span class="lang-nl">${isEdit ? 'Opslaan' : 'Aanmaken'}</span>
              </button>
            </div>
          </form>
        </div>
      `;
      document.body.appendChild(overlay);

      overlay.querySelector('#jobModalClose').addEventListener('click', () => overlay.remove());
      overlay.querySelector('#jobModalCancelBtn').addEventListener('click', () => overlay.remove());
      overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

      overlay.querySelector('#jobModalForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = {};
        for (const [k, v] of fd.entries()) {
          if (v !== '') payload[k] = k.includes('salary') ? parseInt(v) || null : v;
        }
        try {
          const url = isEdit ? `/v1/client/jobs/${job.id}` : '/v1/client/jobs';
          const method = isEdit ? 'PUT' : 'POST';
          const res = await Auth.fetch(url, {
            method,
            body: JSON.stringify(payload),
          });
          if (res && (res.ok || res.status === 201)) {
            Auth.toast(isEdit ? 'Job updated!' : 'Job created!', 'success');
            overlay.remove();
            loadJobs();
          } else {
            const err = res ? await res.json().catch(() => ({})) : {};
            Auth.toast(err.detail || 'Failed to save job', 'error');
          }
        } catch (err) {
          Auth.toast('Error saving job', 'error');
        }
      });
    };

    /* ================================================================
       API: Load Analytics
       ================================================================ */
    // Dutch decimal comma, house style (SITE-DESIGN-SPEC.md §7.3.8b's
    // "NN,N dagen"/"NN,N%").
    function formatDutchDecimal(value, digits) {
      return Number(value).toFixed(digits).replace('.', ',');
    }

    // Currency with a thousands separator, house style (STYLE.md): Dutch
    // view "€1.234,56" (dot thousands, comma decimal), English view
    // "€1,234.56" (comma thousands, dot decimal). No rounding beyond the
    // two decimals the API already returns.
    function formatEuro(value) {
      const num = Number(value);
      const isNl = document.documentElement.getAttribute('data-lang') !== 'en';
      const negative = num < 0;
      const [intPart, decPart] = Math.abs(num).toFixed(2).split('.');
      const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, isNl ? '.' : ',');
      const decimalSep = isNl ? ',' : '.';
      return (negative ? '-' : '') + '€' + grouped + decimalSep + decPart;
    }

    // Horizontal bar rows for pipeline_funnel/source_breakdown -- exactly
    // the values the API returned, nothing computed beyond a bar-width
    // percentage relative to the largest bucket (a layout detail, not a
    // derived figure the screen presents as data).
    function renderBarRows(el, dataObj, labelFn, emptyHtml) {
      if (!el) return;
      const entries = Object.entries(dataObj || {});
      if (!entries.length) { el.innerHTML = emptyHtml; return; }
      const max = Math.max(...entries.map(([, n]) => Number(n) || 0), 1);
      el.innerHTML = entries.map(([key, count]) => {
        const pct = Math.round((Number(count) || 0) / max * 100);
        return `<div style="display:flex;align-items:center;gap:var(--space-sm);margin-bottom:var(--space-sm);">
          <span class="fs-xs a-soft" style="width:120px;flex-shrink:0;">${GSP.esc(labelFn(key))}</span>
          <div style="flex:1;background:rgba(74,111,159,0.15);border-radius:4px;height:10px;overflow:hidden;">
            <div style="width:${pct}%;height:100%;background:var(--gold-500);"></div>
          </div>
          <span class="gsp-num fs-xs" style="width:28px;text-align:right;">${GSP.esc(count)}</span>
        </div>`;
      }).join('');
    }

    // WS5 #140: exactly the five fields GET /v1/client/analytics returns,
    // nothing derived, nothing estimated -- see SITE-DESIGN-SPEC.md
    // §7.3.8(b) for the fallback text per field.
    async function loadAnalytics() {
      const ttdEl = document.getElementById('analyticsTimeToHire');
      const offerEl = document.getElementById('analyticsOfferRate');
      const costEl = document.getElementById('analyticsCostPerHire');
      const costNoteEl = document.getElementById('analyticsCostPerHireNote');
      const funnelEl = document.getElementById('analyticsFunnel');
      const sourcesEl = document.getElementById('analyticsSources');
      try {
        const res = await Auth.fetch('/v1/client/analytics');
        if (!res) return;
        const analytics = await res.json();
        if (!res.ok) throw new Error();

        if (ttdEl) {
          ttdEl.textContent = analytics.time_to_hire_avg_days != null
            ? formatDutchDecimal(analytics.time_to_hire_avg_days, 1) + ' dagen'
            : 'n.v.t.';
        }
        // 0% uit nul sollicitaties is geen percentage (§7.3.8b) -- de
        // backend geeft in dat geval al 0, niet null, dus die waarde
        // krijgt hier dezelfde "n.v.t."-behandeling als null.
        if (offerEl) {
          offerEl.textContent = (analytics.offer_rate != null && analytics.offer_rate !== 0)
            ? formatDutchDecimal(analytics.offer_rate, 1) + '%'
            : 'n.v.t.';
        }
        if (costEl) {
          const hasCost = analytics.cost_per_hire_avg != null;
          costEl.textContent = hasCost ? formatEuro(analytics.cost_per_hire_avg) : 'n.v.t.';
          if (costNoteEl) costNoteEl.style.display = hasCost ? 'none' : 'block';
        }
        renderBarRows(funnelEl, analytics.pipeline_funnel, stageLabel,
          '<div style="text-align:center;color:var(--navy-200);font-size:var(--font-size-sm);padding:var(--space-lg) 0;"><span class="lang-en">No candidates in the pipeline yet</span><span class="lang-nl">Nog geen kandidaten in de pipeline</span></div>');
        renderBarRows(sourcesEl, analytics.source_breakdown, sourceLabel,
          '<div style="text-align:center;color:var(--navy-200);font-size:var(--font-size-sm);padding:var(--space-lg) 0;"><span class="lang-en">No source data yet</span><span class="lang-nl">Nog geen herkomstgegevens</span></div>');
      } catch (err) {
        console.error('Analytics load error:', err);
        [ttdEl, offerEl, costEl].forEach(el => { if (el) el.textContent = 'n.v.t.'; });
        if (funnelEl) Auth.renderLoadError(funnelEl, () => loadAnalytics());
        if (sourcesEl) Auth.renderLoadError(sourcesEl, () => loadAnalytics());
      }
    }

    /* ================================================================
       Candidate Search (basic)
       ================================================================ */
    document.querySelector('#section-candidates .btn-primary')?.addEventListener('click', async (e) => {
      // Two EN/NL twin inputs share this search bar; only one is visible at
      // a time (CSS toggles by active language) -- read from whichever is.
      const searchInputs = document.querySelectorAll('#section-candidates .search-bar input');
      const searchInput = Array.from(searchInputs).find((el) => el.offsetParent !== null);
      const query = searchInput ? searchInput.value.trim() : '';
      const resultsEl = document.getElementById('candidateResults');
      try {
        const res = await Auth.fetch(`/v1/client/candidates?limit=20${query ? '&specialisation=' + encodeURIComponent(query) : ''}`);
        if (!res || !resultsEl) return;
        const data = await res.json();
        if (!data.items || data.items.length === 0) {
          resultsEl.innerHTML = `<div style="text-align:center;color:var(--navy-200);font-size:var(--font-size-sm);padding:var(--space-2xl) 0;">
            <span class="lang-en">No candidates found.</span>
            <span class="lang-nl">Geen kandidaten gevonden.</span>
          </div>`;
          return;
        }
        resultsEl.innerHTML = data.items.map(c => {
          const initials = (c.full_name || '').split(' ').map(w => w[0]).join('').slice(0,2).toUpperCase() || '?';
          const name = GSP.esc(c.full_name || 'Onbekend');
          const desc = GSP.esc(c.current_title || (Array.isArray(c.skills) ? c.skills.join(', ') : '') || '');
          return `<div class="candidate-result">
            <div class="avatar avatar-navy">${GSP.esc(initials)}</div>
            <div style="flex:1;min-width:0;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <h4 style="font-size:var(--font-size-sm);font-weight:600;color:var(--white);">${name}</h4>
              </div>
              <p style="font-size:var(--font-size-xs);color:var(--navy-200);margin:2px 0;">${desc}</p>
            </div>
            <div style="display:flex;gap:var(--space-sm);">
              <button class="btn btn-sm btn-outline"><i class="fa-regular fa-bookmark"></i></button>
              <button class="btn btn-sm btn-primary lang-en">Contact</button>
              <button class="btn btn-sm btn-primary lang-nl">Contact</button>
            </div>
          </div>`;
        }).join('');
      } catch (err) {
        console.error('Candidate search error:', err);
        if (resultsEl) Auth.renderLoadError(resultsEl, () => document.querySelector('#section-candidates .btn-primary')?.click());
      }
    });

    /* ================================================================
       API: Load Team
       ================================================================ */
    async function loadTeam() {
      const tbody = document.getElementById('teamTableBody');
      if (!tbody) return;
      try {
        const res = await Auth.fetch('/v1/client/team');
        if (!res) return;
        if (!res.ok) throw new Error();
        const members = await res.json();
        if (!members || members.length === 0) {
          tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--navy-200);padding:var(--space-lg);">No team members yet.</td></tr>';
          return;
        }
        tbody.innerHTML = members.map(m => {
          const roleBadge = m.role === 'admin' ? 'badge-gold' : m.role === 'client' ? 'badge-blue' : 'badge-gray';
          const roleLabel = m.role === 'admin' ? 'Admin' : m.role === 'client' ? 'Client' : m.role;
          const statusBadge = m.is_verified ? 'badge-green' : 'badge-gray';
          const statusLabel = m.is_verified ? 'Active' : 'Pending';
          return `<tr>
            <td style="font-weight:600;color:var(--white);">${GSP.esc(m.full_name || '')}</td>
            <td style="color:var(--navy-200);">${GSP.esc(m.email || '')}</td>
            <td><span class="badge ${roleBadge}">${GSP.esc(roleLabel)}</span></td>
            <td><span class="badge ${statusBadge}">${GSP.esc(statusLabel)}</span></td>
            <td><button class="btn btn-sm btn-ghost"><i class="fa-regular fa-ellipsis-vertical"></i></button></td>
          </tr>`;
        }).join('');
      } catch (err) {
        console.error('Team load error:', err);
        const id = '_retryTeam';
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--navy-200);padding:var(--space-lg);">
          <span class="lang-nl">Kon niet laden — <a href="#" id="${id}">probeer opnieuw</a></span>
          <span class="lang-en">Could not load — <a href="#" id="${id}_en">try again</a></span>
        </td></tr>`;
        document.getElementById(id)?.addEventListener('click', (e) => { e.preventDefault(); loadTeam(); });
        document.getElementById(id + '_en')?.addEventListener('click', (e) => { e.preventDefault(); loadTeam(); });
      }
    }

    /* ================================================================
       Invite Team Member Modal
       ================================================================ */
    window.showInviteModal = function() {
      const existing = document.getElementById('inviteModalOverlay');
      if (existing) existing.remove();

      const overlay = document.createElement('div');
      overlay.id = 'inviteModalOverlay';
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:1000;display:flex;align-items:center;justify-content:center;padding:var(--space-lg);';
      overlay.innerHTML = `
        <div style="background:var(--navy-800);border:1px solid var(--navy-600);border-radius:12px;padding:var(--space-2xl);width:100%;max-width:420px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-xl);">
            <h3 style="font-size:var(--font-size-lg);font-weight:600;color:var(--white);">
              <span class="lang-en">Invite Team Member</span>
              <span class="lang-nl">Lid Uitnodigen</span>
            </h3>
            <button id="inviteModalClose" class="btn btn-sm btn-ghost"><i class="fa-regular fa-xmark"></i></button>
          </div>
          <form id="inviteModalForm">
            <div class="form-group">
              <label class="lang-en">Full Name *</label><label class="lang-nl">Volledige naam *</label>
              <input type="text" name="full_name" required placeholder="Jan de Vries">
            </div>
            <div class="form-group">
              <label>Email *</label>
              <input type="email" name="email" required placeholder="jan@company.com">
            </div>
            <div style="display:flex;gap:var(--space-md);justify-content:flex-end;margin-top:var(--space-xl);">
              <button type="button" id="inviteModalCancelBtn" class="btn btn-outline">
                <span class="lang-en">Cancel</span><span class="lang-nl">Annuleren</span>
              </button>
              <button type="submit" class="btn btn-primary">
                <i class="fa-regular fa-paper-plane"></i>
                <span class="lang-en">Send Invite</span><span class="lang-nl">Uitnodigen</span>
              </button>
            </div>
          </form>
        </div>
      `;
      document.body.appendChild(overlay);

      overlay.querySelector('#inviteModalClose').addEventListener('click', () => overlay.remove());
      overlay.querySelector('#inviteModalCancelBtn').addEventListener('click', () => overlay.remove());
      overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

      overlay.querySelector('#inviteModalForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = { full_name: fd.get('full_name'), email: fd.get('email'), role: 'client' };
        try {
          const res = await Auth.fetch('/v1/client/team', { method: 'POST', body: JSON.stringify(payload) });
          if (res && (res.ok || res.status === 201)) {
            const data = await res.json();
            Auth.toast('Team member invited!', 'success');
            if (data.temporary_password) {
              alert(`Temporary password for ${payload.email}: ${data.temporary_password}\n\nPlease share this securely with the new team member.`);
            }
            overlay.remove();
            loadTeam();
          } else {
            const err = res ? await res.json().catch(() => ({})) : {};
            Auth.toast(err.detail || 'Failed to invite member', 'error');
          }
        } catch (err) {
          Auth.toast('Error inviting member', 'error');
        }
      });
    };

    /* ================================================================
       API: Load / Save Client Profile (Settings)
       ================================================================ */
    async function loadClientProfile() {
      try {
        const res = await Auth.fetch('/v1/client/profile');
        if (!res || !res.ok) return;
        const profile = await res.json();
        const nameEl = document.getElementById('settingsCompanyName');
        const webEl = document.getElementById('settingsWebsite');
        const indEl = document.getElementById('settingsIndustry');
        if (nameEl) nameEl.value = profile.company_name || '';
        if (webEl) webEl.value = profile.domain || '';
        if (indEl && profile.industry) {
          const opt = Array.from(indEl.options).find(o => o.value === profile.industry);
          if (opt) indEl.value = profile.industry;
        }
      } catch (err) {
        console.error('Profile load error:', err);
      }
    }

    const settingsForm = document.getElementById('clientSettingsForm');
    if (settingsForm) {
      settingsForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = {};
        for (const [k, v] of fd.entries()) { if (v) payload[k] = v; }
        try {
          const res = await Auth.fetch('/v1/client/profile', { method: 'PATCH', body: JSON.stringify(payload) });
          if (res && res.ok) {
            Auth.toast('Settings saved!', 'success');
          } else {
            Auth.toast('Failed to save settings', 'error');
          }
        } catch (err) {
          Auth.toast('Error saving settings', 'error');
        }
      });
    }

    /* ================================================================
       WS5 #141: Contacten (Settings)
       GET/POST /v1/client/contacts, PATCH/DELETE
       /v1/client/contacts/{contact_id} (talent-os/backend/routers/
       client_contacts.py) -- scoped server-side to the caller's own
       client via the user_clients join, same as every other
       client-portal route. Role labels match the admin panel's
       website/admin/js/labels.js exactly.
       ================================================================ */
    const CONTACT_ROLE_LABELS = {
      hiring_manager: 'Hiring manager', finance: 'Financiën',
      tekenbevoegd: 'Tekenbevoegd', overig: 'Overig',
    };
    let contactsCache = [];

    async function loadContacts() {
      const el = document.getElementById('contactsList');
      if (!el) return;
      el.innerHTML = '<div style="text-align:center;color:var(--navy-200);font-size:var(--font-size-sm);padding:var(--space-lg) 0;"><i class="fa-solid fa-spinner fa-spin"></i></div>';
      try {
        const res = await Auth.fetch('/v1/client/contacts');
        if (!res) return;
        if (!res.ok) throw new Error();
        const data = await res.json();
        const items = data.items || [];
        contactsCache = items;
        if (!items.length) {
          el.innerHTML = '<div style="text-align:center;color:var(--navy-200);font-size:var(--font-size-sm);padding:var(--space-lg) 0;"><span class="lang-en">No contacts recorded yet.</span><span class="lang-nl">Nog geen contacten vastgelegd.</span></div>';
          return;
        }
        el.innerHTML = items.map(c => `
          <div class="activity-item">
            <div class="activity-icon" style="background:rgba(250,200,0,0.12);color:var(--gold-500);"><i class="fa-regular fa-address-card"></i></div>
            <div class="activity-content">
              <div class="activity-text" style="font-weight:600;color:var(--white);">${GSP.esc(c.full_name || '—')}</div>
              <div class="activity-text a-soft">${GSP.esc(CONTACT_ROLE_LABELS[c.role] || c.role || '')}</div>
              <div class="activity-text fs-xs a-soft">${GSP.esc(c.email || '')}${c.email && c.phone ? ' · ' : ''}${GSP.esc(c.phone || '')}</div>
            </div>
            <div style="display:flex;gap:var(--space-xs);flex-shrink:0;">
              <button type="button" class="btn btn-sm btn-ghost" data-action="edit-contact" data-id="${Number(c.id) || 0}" title="Bewerken">
                <i class="fa-regular fa-pen"></i>
              </button>
              <button type="button" class="btn btn-sm btn-ghost" data-action="delete-contact" data-id="${Number(c.id) || 0}" title="Verwijderen">
                <i class="fa-regular fa-trash"></i>
              </button>
            </div>
          </div>`).join('');
      } catch (err) {
        console.error('Contacts load error:', err);
        Auth.renderLoadError(el, () => loadContacts());
      }
    }

    /* ---- Add/edit contact modal ---- */
    window.showContactModal = function(contact = null) {
      const isEdit = !!contact;
      const existing = document.getElementById('contactModalOverlay');
      if (existing) existing.remove();

      const overlay = document.createElement('div');
      overlay.id = 'contactModalOverlay';
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:1000;display:flex;align-items:center;justify-content:center;padding:var(--space-lg);';
      overlay.innerHTML = `
        <div style="background:var(--navy-800);border:1px solid var(--navy-600);border-radius:12px;padding:var(--space-2xl);width:100%;max-width:480px;max-height:90vh;overflow-y:auto;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--space-xl);">
            <h3 style="font-size:var(--font-size-lg);font-weight:600;color:var(--white);">
              <span class="lang-en">${isEdit ? 'Edit Contact' : 'Add Contact'}</span>
              <span class="lang-nl">${isEdit ? 'Contact Bewerken' : 'Contact Toevoegen'}</span>
            </h3>
            <button type="button" id="contactModalClose" class="btn btn-sm btn-ghost"><i class="fa-regular fa-xmark"></i></button>
          </div>
          <form id="contactModalForm">
            <div class="form-group">
              <label class="lang-en">Name *</label><label class="lang-nl">Naam *</label>
              <input type="text" name="full_name" required maxlength="255" value="${GSP.esc(contact?.full_name || '')}">
            </div>
            <div class="form-group">
              <label class="lang-en">Role</label><label class="lang-nl">Rol</label>
              <select name="role">
                <option value="">Select…</option>
                ${Object.entries(CONTACT_ROLE_LABELS).map(([v, label]) =>
                  `<option value="${v}" ${contact?.role === v ? 'selected' : ''}>${GSP.esc(label)}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label>Email</label>
              <input type="email" name="email" value="${GSP.esc(contact?.email || '')}">
            </div>
            <div class="form-group">
              <label class="lang-en">Phone</label><label class="lang-nl">Telefoon</label>
              <input type="text" name="phone" maxlength="50" value="${GSP.esc(contact?.phone || '')}">
            </div>
            <div style="display:flex;gap:var(--space-md);justify-content:flex-end;margin-top:var(--space-xl);">
              <button type="button" id="contactModalCancelBtn" class="btn btn-outline">
                <span class="lang-en">Cancel</span><span class="lang-nl">Annuleren</span>
              </button>
              <button type="submit" class="btn btn-primary">
                <i class="fa-regular fa-floppy-disk"></i>
                <span class="lang-en">${isEdit ? 'Save Changes' : 'Add Contact'}</span>
                <span class="lang-nl">${isEdit ? 'Opslaan' : 'Toevoegen'}</span>
              </button>
            </div>
          </form>
        </div>
      `;
      document.body.appendChild(overlay);

      overlay.querySelector('#contactModalClose').addEventListener('click', () => overlay.remove());
      overlay.querySelector('#contactModalCancelBtn').addEventListener('click', () => overlay.remove());
      overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

      overlay.querySelector('#contactModalForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        const payload = {};
        for (const [k, v] of fd.entries()) { if (v !== '') payload[k] = v; }
        try {
          const url = isEdit ? `/v1/client/contacts/${contact.id}` : '/v1/client/contacts';
          const method = isEdit ? 'PATCH' : 'POST';
          const res = await Auth.fetch(url, { method, body: JSON.stringify(payload) });
          if (res && (res.ok || res.status === 201)) {
            Auth.toast(isEdit ? 'Contact bijgewerkt' : 'Contact toegevoegd', 'success');
            overlay.remove();
            loadContacts();
          } else {
            const err = res ? await res.json().catch(() => ({})) : {};
            Auth.toast(err.detail || 'Opslaan van contact is mislukt', 'error');
          }
        } catch (err) {
          Auth.toast('Netwerkfout, probeer het opnieuw.', 'error');
        }
      });
    };

    window.editContact = function(contactId) {
      const contact = contactsCache.find(c => Number(c.id) === Number(contactId));
      if (!contact) { Auth.toast('Contact niet gevonden', 'error'); return; }
      window.showContactModal(contact);
    };

    window.deleteContact = async function(contactId) {
      if (!confirm('Dit contact verwijderen?')) return;
      try {
        const res = await Auth.fetch(`/v1/client/contacts/${contactId}`, { method: 'DELETE' });
        if (res && (res.ok || res.status === 204)) {
          Auth.toast('Contact verwijderd', 'success');
          loadContacts();
        } else {
          Auth.toast('Verwijderen van contact is mislukt', 'error');
        }
      } catch (err) {
        Auth.toast('Netwerkfout, probeer het opnieuw.', 'error');
      }
    };

    /* ================================================================
       WS5 #141: Activiteiten (Settings)
       GET/POST /v1/client/activities, scoped server-side to the caller's
       own organisation. A new activity needs a subject (a job the client
       posted, or a candidate in its own pipeline) -- loadActivitySubjects()
       fills #activitySubject from the same two lists the rest of this
       portal already fetches.
       ================================================================ */
    async function loadActivitySubjects() {
      const typeEl = document.getElementById('activitySubjectType');
      const subjectEl = document.getElementById('activitySubject');
      if (!typeEl || !subjectEl) return;
      subjectEl.innerHTML = '<option value="">Laden…</option>';
      try {
        if (typeEl.value === 'candidate') {
          const res = await Auth.fetch('/v1/client/pipeline?limit=200');
          const data = res && res.ok ? await res.json() : { items: [] };
          const seen = new Set();
          const options = (data.items || []).filter((pe) => {
            if (seen.has(pe.candidate_id)) return false;
            seen.add(pe.candidate_id);
            return true;
          }).map((pe) => {
            const label = pe.full_name || `Kandidaat #${pe.candidate_id}`;
            return `<option value="${Number(pe.candidate_id) || 0}">${GSP.esc(label)}</option>`;
          });
          subjectEl.innerHTML = options.length ? options.join('') : '<option value="">Geen kandidaten in de pipeline</option>';
        } else {
          const res = await Auth.fetch('/v1/client/jobs?limit=50');
          const data = res && res.ok ? await res.json() : { items: [] };
          const options = (data.items || []).map((j) => `<option value="${Number(j.id) || 0}">${GSP.esc(j.title || 'Vacature #' + j.id)}</option>`);
          subjectEl.innerHTML = options.length ? options.join('') : '<option value="">Geen vacatures</option>';
        }
      } catch (err) {
        console.error('Activity subjects load error:', err);
        subjectEl.innerHTML = '<option value="">Kon niet laden</option>';
      }
    }

    document.getElementById('activitySubjectType')?.addEventListener('change', () => loadActivitySubjects());

    async function loadActivities() {
      const el = document.getElementById('activitiesList');
      if (!el) return;
      el.innerHTML = '<div style="text-align:center;color:var(--navy-200);font-size:var(--font-size-sm);padding:var(--space-lg) 0;"><i class="fa-solid fa-spinner fa-spin"></i></div>';
      try {
        const res = await Auth.fetch('/v1/client/activities?limit=50');
        if (!res) return;
        if (!res.ok) throw new Error();
        const data = await res.json();
        const items = data.items || [];
        if (!items.length) {
          el.innerHTML = '<div style="text-align:center;color:var(--navy-200);font-size:var(--font-size-sm);padding:var(--space-lg) 0;"><span class="lang-en">No activities recorded yet.</span><span class="lang-nl">Nog geen activiteiten vastgelegd.</span></div>';
          return;
        }
        el.innerHTML = items.map(a => {
          const time = a.created_at ? new Date(a.created_at).toLocaleDateString() : '';
          return `<div class="activity-item">
            <div class="activity-icon" style="background:rgba(74,111,159,0.15);color:var(--navy-100);"><i class="fa-regular fa-note-sticky"></i></div>
            <div class="activity-content">
              <span class="badge badge-blue fs-xs">${GSP.esc(activityTypeLabel(a.type))}</span>
              <div class="activity-text">${GSP.esc(a.body || '')}</div>
              <div class="activity-time">${GSP.esc(time)}</div>
            </div>
          </div>`;
        }).join('');
      } catch (err) {
        console.error('Activities load error:', err);
        Auth.renderLoadError(el, () => loadActivities());
      }
    }

    document.getElementById('activityAddForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const form = e.target;
      const fd = new FormData(form);
      const subjectId = Number(fd.get('subject_id'));
      if (!subjectId) { Auth.toast('Kies eerst een vacature of kandidaat', 'warning'); return; }
      const payload = {
        subject_type: fd.get('subject_type'),
        subject_id: subjectId,
        type: fd.get('type'),
        body: (fd.get('body') || '').toString().trim() || null,
      };
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;
      try {
        const res = await Auth.fetch('/v1/client/activities', { method: 'POST', body: JSON.stringify(payload) });
        if (res && (res.ok || res.status === 201)) {
          Auth.toast('Activiteit toegevoegd', 'success');
          form.reset();
          loadActivities();
        } else {
          Auth.toast('Activiteit opslaan is mislukt', 'error');
        }
      } catch (err) {
        Auth.toast('Netwerkfout, probeer het opnieuw.', 'error');
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });

    /* ================================================================
       Initial load
       ================================================================ */
    document.addEventListener('DOMContentLoaded', () => {
      loadDashboard();
      loadJobs();
    });

    document.getElementById('sidebarLogoutBtn').addEventListener('click', () => Auth.logout());

    const savedLang = localStorage.getItem('gsp_lang');
    if (savedLang === 'nl' || savedLang === 'en') document.documentElement.setAttribute('data-lang', savedLang);

    /* ---- Delegated data-action handler (WS-A.9b: no inline onclick=
       attributes -- the enforced CSP drops 'unsafe-inline' from
       script-src, which also governs inline event-handler attributes). */
    document.addEventListener('click', (e) => {
      const el = e.target.closest('[data-action]');
      if (!el) return;
      const id = el.dataset.id;
      switch (el.dataset.action) {
        case 'show-invite-modal': showInviteModal(); break;
        case 'edit-job': editJob(Number(id) || 0); break;
        case 'delete-job': deleteJob(Number(id) || 0); break;
        case 'add-contact': window.showContactModal(); break;
        case 'edit-contact': window.editContact(Number(id) || 0); break;
        case 'delete-contact': window.deleteContact(Number(id) || 0); break;
        case 'toast-deactivate-client':
          Auth.toast('Contact info@gsprecruitment.nl for account deactivation', 'warning');
          break;
        case 'goto-create-job':
          navigateTo('jobs');
          document.getElementById('createJobBtn')?.click();
          break;
        case 'toggle-kanban-column': {
          // Accordion only at <=600px (§7.3.8a); at desktop width every
          // column already shows its cards regardless of .active, so a
          // click here is a no-op there.
          if (window.innerWidth > 600) break;
          const columnEl = el.closest('.kanban-column');
          if (columnEl) setKanbanColumnOpen(columnEl, !columnEl.classList.contains('active'));
          break;
        }
      }
    });

    // Stagewijziging via de <select> op elke kanban-kaart (§7.3.8a):
    // gedelegeerd, want de kaarten worden dynamisch opgebouwd.
    document.addEventListener('change', (e) => {
      const el = e.target.closest('#kanbanBoard select');
      if (el) handleStageChange(el);
    });
