    /* ================================================================
       Candidate Portal — Full API integration
       ================================================================ */

    /* ---- Auth Guard ---- */
    const user = Auth.requireAuth(['candidate']);
    if (!user) { /* redirect handled in requireAuth */ }

    // WS-B.2: show the "viewing as" banner + return-to-admin control when
    // this session is an admin impersonating this candidate.
    if (user) Auth.renderImpersonationBanner();

    /* ---- WS-E.2: e-mail verification gate ----
       Auth.requireAuth() only checks the JWT is valid; is_verified is a
       separate, backend-enforced gate (core/deps.py get_verified_user
       returns 403 on every /v1/candidate/* endpoint until confirmed). Show
       the overlay and stop here rather than firing API calls that will
       just 403. */
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

    /* ---- Sidebar Navigation ---- */
    const sectionTitles = {
      dashboard: { en: 'Dashboard', nl: 'Dashboard' },
      profile: { en: 'My Profile', nl: 'Mijn Profiel' },
      salary: { en: 'Salary Tool', nl: 'Salaristool' },
      matches: { en: 'My Matches', nl: 'Mijn Matches' },
      applications: { en: 'Applications', nl: 'Sollicitaties' },
      messages: { en: 'Messages', nl: 'Berichten' },
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
    }

    document.querySelectorAll('.sidebar-nav-item').forEach(item => {
      item.addEventListener('click', () => navigateTo(item.dataset.section));
    });

    const hash = window.location.hash.replace('#', '');
    if (hash && sectionTitles[hash]) navigateTo(hash);

    /* ---- Mobile menu ---- */
    const mobileBtn = document.getElementById('mobileMenuBtn');
    const sidebar = document.getElementById('sidebar');
    if (window.innerWidth <= 768) mobileBtn.style.display = '';
    window.addEventListener('resize', () => { mobileBtn.style.display = window.innerWidth <= 768 ? '' : 'none'; });
    mobileBtn.addEventListener('click', () => sidebar.classList.toggle('open'));

    /* ================================================================
       API: Load Dashboard
       ================================================================ */
    async function loadDashboard() {
      try {
        const [profileRes, dashboardRes, matchesRes] = await Promise.all([
          Auth.fetch('/v1/candidate/profile'),
          Auth.fetch('/v1/candidate/dashboard'),
          Auth.fetch('/v1/candidate/matches?limit=5'),
        ]);
        const profile = profileRes ? await profileRes.json() : {};
        const dashboard = dashboardRes ? await dashboardRes.json() : {};
        const matchesData = matchesRes ? await matchesRes.json() : { items: [] };

        // Stats
        document.getElementById('statMatches').textContent = dashboard.match_count ?? 0;
        document.getElementById('statViews').textContent = dashboard.profile_views ?? 0;
        document.getElementById('statMessages').textContent = dashboard.unread_messages ?? 0;
        document.getElementById('statSaved').textContent = dashboard.saved_jobs_count ?? 0;

        // Sidebar user
        const name = user.full_name || profile.full_name || user.email?.split('@')[0] || 'Candidate';
        const email = user.email || profile.email || '';
        const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
        document.getElementById('sidebarName').textContent = name;
        document.getElementById('sidebarEmail').textContent = email;
        document.getElementById('sidebarAvatar').textContent = initials;
        document.getElementById('profileAvatar').textContent = initials;
        document.getElementById('profileName').textContent = name;
        document.getElementById('profileEmail').textContent = email;

        // Top matches
        const topMatchesEl = document.getElementById('topMatchesList');
        if (matchesData.items && matchesData.items.length > 0) {
          topMatchesEl.innerHTML = matchesData.items.map(m => {
            const score = Math.round(m.match_score || 0);
            const salary = m.salary_min && m.salary_max ? `€${m.salary_min/1000}K – €${m.salary_max/1000}K` : '';
            const location = m.location ? ` — ${m.location}` : '';
            return `<div class="match-card">
              <div class="match-score">Match ${score}</div>
              <div class="match-info">
                <h4>${GSP.esc(m.job_title || 'Job')}</h4>
                <p class="match-company">${GSP.esc(m.company_name || '')}${GSP.esc(location)}</p>
                <p>${GSP.esc(salary)}${m.location_type ? ' · ' + GSP.esc(m.location_type) : ''}</p>
              </div>
              <button class="btn btn-sm btn-primary lang-en" data-action="apply-job" data-id="${Number(m.job_id) || 0}">Apply</button>
              <button class="btn btn-sm btn-primary lang-nl" data-action="apply-job" data-id="${Number(m.job_id) || 0}">Solliciteer</button>
            </div>`;
          }).join('');
        }

        // Profile completion (estimate)
        const pct = profile ? calcProfileCompletion(profile) : 0;
        document.querySelector('#section-dashboard .progress-bar-fill').style.width = pct + '%';
        document.querySelector('#section-dashboard .progress-bar-fill').parentElement.previousElementSibling.textContent = pct + '%';

        // Recent activity (from profile updated_at)
        const activityEl = document.getElementById('recentActivity');
        if (profile && profile.updated_at) {
          const d = new Date(profile.updated_at);
          activityEl.innerHTML = `<div class="activity-item">
            <div class="activity-icon" style="background:rgba(250,200,0,0.1);color:var(--gold-500);"><i class="fa-regular fa-pen-to-square"></i></div>
            <div class="activity-content">
              <div class="activity-text lang-en">Profile last updated</div>
              <div class="activity-text lang-nl">Profiel laatst bijgewerkt</div>
              <div class="activity-time">${d.toLocaleDateString()}</div>
            </div>
          </div>`;
        }

        // Profile form fields
        if (profile) {
          const nameParts = (profile.full_name || name || '').split(' ');
          if (document.getElementById('profFirstName')) document.getElementById('profFirstName').value = nameParts[0] || '';
          if (document.getElementById('profLastName')) document.getElementById('profLastName').value = nameParts.slice(1).join(' ') || '';
          if (document.getElementById('profEmail')) document.getElementById('profEmail').value = email;
          if (document.getElementById('profPhone')) document.getElementById('profPhone').value = profile.phone || '';
          if (document.getElementById('profRole')) document.getElementById('profRole').value = profile.current_title || '';
          if (document.getElementById('profExperience')) {
            const yrs = profile.years_experience;
            if (yrs != null) {
              const opt = yrs <= 2 ? '0-2' : yrs <= 5 ? '3-5' : yrs <= 10 ? '6-10' : '10+';
              document.getElementById('profExperience').value = opt;
            }
          }
        }
      } catch (err) {
        console.error('Dashboard load error:', err);
        Auth.renderLoadError(document.getElementById('topMatchesList'), loadDashboard);
        Auth.renderLoadError(document.getElementById('recentActivity'), loadDashboard);
      }
    }

    function calcProfileCompletion(p) {
      let score = 0;
      const fields = ['full_name','phone','current_title','years_experience','skills','cv_file_path','location'];
      const step = Math.floor(100 / fields.length);
      fields.forEach(f => { if (p[f] && (Array.isArray(p[f]) ? p[f].length > 0 : true)) score += step; });
      return Math.min(score, 100);
    }

    /* ================================================================
       API: Load Profile
       ================================================================ */
    async function loadProfile() {
      try {
        const res = await Auth.fetch('/v1/candidate/profile');
        if (!res) return;
        const profile = await res.json();
        if (!profile) return;

        const name = profile.full_name || user.full_name || '';
        const email = profile.email || user.email || '';
        const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

        document.getElementById('profileAvatar').textContent = initials;
        document.getElementById('profileName').textContent = name;
        document.getElementById('profileEmail').textContent = email;

        const nameParts = name.split(' ');
        if (document.getElementById('profFirstName')) document.getElementById('profFirstName').value = nameParts[0] || '';
        if (document.getElementById('profLastName')) document.getElementById('profLastName').value = nameParts.slice(1).join(' ') || '';
        if (document.getElementById('profEmail')) document.getElementById('profEmail').value = email;
        if (document.getElementById('profPhone')) document.getElementById('profPhone').value = profile.phone || '';
        if (document.getElementById('profRole')) document.getElementById('profRole').value = profile.current_title || '';

        // CV status
        if (profile.cv_file_path) {
          const cvStatus = document.getElementById('profileCvStatus');
          const cvName = document.getElementById('profileCvName');
          if (cvStatus && cvName) {
            cvStatus.style.display = 'block';
            cvName.textContent = profile.cv_file_path.split('/').pop();
          }
        }

        // Talentpool consent (WS-C.17) -- checked + expiry shown only
        // while consent_talentpool_until is still in the future; an
        // expired or never-set date leaves the box unchecked, same as
        // outreach.py's _draft_refusal treats it.
        applyTalentpoolConsentState(profile);
      } catch (err) {
        console.error('Profile load error:', err);
      }
    }

    /* ---- Profile form submit ---- */
    document.getElementById('profileForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        const data = {
          full_name: (document.getElementById('profFirstName').value + ' ' + document.getElementById('profLastName').value).trim(),
          phone: document.getElementById('profPhone').value,
          current_title: document.getElementById('profRole').value,
        };
        const res = await Auth.fetch('/v1/candidate/profile', {
          method: 'PUT',
          body: JSON.stringify(data),
        });
        if (res && res.ok) {
          Auth.toast(document.documentElement.getAttribute('data-lang') === 'nl' ? 'Profiel opgeslagen!' : 'Profile saved!');
        } else {
          Auth.toast('Failed to save profile', 'error');
        }
      } catch (err) {
        Auth.toast('Error saving profile', 'error');
      }
    });

    /* ---- Talentpool consent (WS-C.17) ----
       GET /v1/candidate/profile now includes consent_talentpool_at/_until/
       _scope/_source (read via the candidates row) -- applyTalentpoolConsentState()
       reflects them on load, and again after a save, so the checkbox and
       expiry text always match what's actually on file. */
    const tpCheck = document.getElementById('talentpoolConsentCheck');
    const tpSaveBtn = document.getElementById('talentpoolConsentSaveBtn');
    const tpStatus = document.getElementById('talentpoolConsentStatus');

    function applyTalentpoolConsentState(profile) {
      if (!tpCheck || !tpStatus) return;
      const isNl = document.documentElement.getAttribute('data-lang') === 'nl';
      const until = profile.consent_talentpool_until ? new Date(profile.consent_talentpool_until) : null;
      const active = !!(until && until.getTime() > Date.now());
      tpCheck.checked = active;
      tpStatus.textContent = active
        ? (isNl ? `Actief tot ${until.toLocaleDateString('nl-NL')}.` : `Active until ${until.toLocaleDateString('en-GB')}.`)
        : '';
    }

    if (tpCheck && tpSaveBtn) {
      tpSaveBtn.addEventListener('click', async () => {
        const isNl = document.documentElement.getAttribute('data-lang') === 'nl';
        try {
          const res = await Auth.fetch('/v1/candidate/talentpool-consent', {
            method: 'POST',
            body: JSON.stringify({
              consent: tpCheck.checked,
              scope: tpCheck.checked ? 'matching_and_contact' : null,
            }),
          });
          if (res && res.ok) {
            const row = await res.json();
            applyTalentpoolConsentState(row);
            if (!row.consent_talentpool_until && tpStatus) {
              tpStatus.textContent = isNl ? 'Talentpool-toestemming ingetrokken.' : 'Talent pool consent withdrawn.';
            }
            Auth.toast(isNl ? 'Opgeslagen!' : 'Saved!');
          } else {
            Auth.toast(isNl ? 'Opslaan mislukt' : 'Failed to save', 'error');
          }
        } catch (err) {
          Auth.toast('Error saving talentpool consent', 'error');
        }
      });
    }

    /* ---- CV Upload ---- */
    const pCvZone = document.getElementById('profileCvZone');
    const pCvInput = document.getElementById('profileCvInput');
    const pCvStatus = document.getElementById('profileCvStatus');
    const pCvName = document.getElementById('profileCvName');

    if (pCvZone && pCvInput) {
      pCvZone.addEventListener('click', () => pCvInput.click());
      pCvZone.addEventListener('dragover', (e) => { e.preventDefault(); pCvZone.style.borderColor = 'var(--gold-500)'; });
      pCvZone.addEventListener('dragleave', () => { pCvZone.style.borderColor = ''; });
      pCvZone.addEventListener('drop', async (e) => {
        e.preventDefault();
        pCvZone.style.borderColor = '';
        if (e.dataTransfer.files.length) await uploadCvFile(e.dataTransfer.files[0]);
      });
      pCvInput.addEventListener('change', async () => {
        if (pCvInput.files.length) await uploadCvFile(pCvInput.files[0]);
      });
    }

    async function uploadCvFile(file) {
      const formData = new FormData();
      formData.append('file', file);
      try {
        const token = Auth.getToken();
        const res = await fetch(`${Auth.API}/v1/candidate/cv`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          body: formData,
        });
        if (res.ok) {
          pCvStatus.style.display = 'block';
          pCvName.textContent = file.name;
          pCvZone.querySelector('p').textContent = 'CV uploaded!';
          Auth.toast('CV uploaded successfully!', 'success');
        } else {
          Auth.toast('CV upload failed', 'error');
        }
      } catch (err) {
        Auth.toast('Error uploading CV', 'error');
      }
    }

    /* ---- Password change ---- */
    document.getElementById('passwordChangeForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const inputs = e.target.querySelectorAll('input[type="password"]');
      const currentPw = inputs[0].value;
      const newPw = inputs[1].value;
      const confirmPw = inputs[2].value;
      if (newPw !== confirmPw) {
        Auth.toast('Passwords do not match', 'error');
        return;
      }
      if (newPw.length < 8) {
        Auth.toast('New password must be at least 8 characters', 'error');
        return;
      }
      try {
        const res = await Auth.fetch('/auth/change-password', {
          method: 'POST',
          body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
        });
        if (res && res.ok) {
          Auth.toast(document.documentElement.getAttribute('data-lang') === 'nl' ? 'Wachtwoord bijgewerkt!' : 'Password updated!', 'success');
          inputs.forEach(i => i.value = '');
        } else {
          const err = res ? await res.json().catch(() => ({})) : {};
          Auth.toast(err.detail || 'Failed to update password', 'error');
        }
      } catch (err) {
        Auth.toast('Error updating password', 'error');
      }
    });

    /* ================================================================
       API: Load Matches
       ================================================================ */
    async function loadMatches() {
      try {
        const res = await Auth.fetch('/v1/candidate/matches?limit=50');
        if (!res) return;
        const data = await res.json();
        const list = document.getElementById('matchesList');
        if (!data.items || data.items.length === 0) {
          list.innerHTML = '<p style="color:var(--navy-200);text-align:center;padding:var(--space-2xl);">No matches found yet.</p>';
          return;
        }
        list.innerHTML = data.items.map(m => {
          const score = Math.round(m.match_score || 0);
          const salary = m.salary_min && m.salary_max ? `€${m.salary_min/1000}K – €${m.salary_max/1000}K` : '';
          const location = m.location ? ` — ${m.location}` : '';
          return `<div class="match-card">
            <div class="match-score">Match ${score}</div>
            <div class="match-info">
              <h4>${GSP.esc(m.job_title || 'Job')}</h4>
              <p class="match-company">${GSP.esc(m.company_name || '')}${GSP.esc(location)}</p>
              <p>${GSP.esc(salary)}${m.location_type ? ' · ' + GSP.esc(m.location_type) : ''}</p>
              <div style="margin-top:6px;display:flex;gap:4px;">
                <span class="tag tag-green">${GSP.esc(m.status || 'New')}</span>
              </div>
            </div>
            <button class="btn btn-sm btn-primary lang-en" data-action="apply-job" data-id="${Number(m.job_id) || 0}">Apply Now</button>
            <button class="btn btn-sm btn-primary lang-nl" data-action="apply-job" data-id="${Number(m.job_id) || 0}">Solliciteer</button>
          </div>`;
        }).join('');
      } catch (err) {
        console.error('Matches load error:', err);
        Auth.renderLoadError(document.getElementById('matchesList'), loadMatches);
      }
    }

    /* ---- Apply to job ---- */
    window.applyToJob = async function(jobId) {
      try {
        const res = await Auth.fetch('/v1/candidate/applications', {
          method: 'POST',
          body: JSON.stringify({ job_id: jobId }),
        });
        if (res && res.ok) {
          Auth.toast(document.documentElement.getAttribute('data-lang') === 'nl' ? 'Sollicitatie verstuurd!' : 'Applied successfully!');
        } else if (res) {
          const err = await res.json();
          Auth.toast(err.detail || 'Application failed', 'error');
        }
      } catch (err) {
        Auth.toast('Error applying', 'error');
      }
    };

    /* ---- Namespace for inline onclick compatibility ---- */
    window.app = window.app || {};
    window.app.matches = { apply: applyToJob };

    /* ================================================================
       API: Load Applications
       ================================================================ */
    async function loadApplications() {
      try {
        const res = await Auth.fetch('/v1/candidate/applications?limit=50');
        if (!res) return;
        const data = await res.json();
        const tbody = document.querySelector('#section-applications table tbody');
        if (!data.items || data.items.length === 0) {
          tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--navy-200);padding:var(--space-2xl);">No applications yet.</td></tr>';
          return;
        }
        tbody.innerHTML = data.items.map(a => {
          const date = a.created_at ? new Date(a.created_at).toLocaleDateString() : '';
          const statusMap = { 'applied': 'Applied', 'interviewing': 'Interview', 'offered': 'Offer', 'placed': 'Placed', 'rejected': 'Rejected' };
          const statusBadge = {
            'applied': 'badge-blue', 'interviewing': 'badge-gold', 'offered': 'badge-purple', 'placed': 'badge-green', 'rejected': 'badge-gray'
          }[a.status] || 'badge-blue';
          return `<tr>
            <td style="font-weight:600;color:var(--white);">${GSP.esc(a.job_title || '-')}</td>
            <td>${GSP.esc(a.company_name || '-')}</td>
            <td style="font-size:var(--font-size-xs);color:var(--navy-200);">${GSP.esc(date)}</td>
            <td><span class="badge ${statusBadge}">${GSP.esc(statusMap[a.status] || a.status)}</span></td>
            <td><button class="btn btn-sm btn-ghost" data-action="toast-details-soon"><i class="fa-regular fa-eye"></i></button></td>
          </tr>`;
        }).join('');
      } catch (err) {
        console.error('Applications load error:', err);
        const tbody = document.querySelector('#section-applications table tbody');
        if (tbody) {
          const id = '_retryApps';
          tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--navy-200);padding:var(--space-2xl);">
            <span class="lang-nl">Kon niet laden — <a href="#" id="${id}">probeer opnieuw</a></span>
            <span class="lang-en">Could not load — <a href="#" id="${id}_en">try again</a></span>
          </td></tr>`;
          document.getElementById(id)?.addEventListener('click', (e) => { e.preventDefault(); loadApplications(); });
          document.getElementById(id + '_en')?.addEventListener('click', (e) => { e.preventDefault(); loadApplications(); });
        }
      }
    }

    /* ================================================================
       API: Load Messages
       ================================================================ */
    async function loadMessages() {
      try {
        const res = await Auth.fetch('/v1/candidate/messages?limit=50');
        if (!res) return;
        const data = await res.json();
        const msgContainer = document.querySelector('#section-messages .dashboard-grid > div:first-child');
        if (!data.messages || data.messages.length === 0) {
          msgContainer.innerHTML = '<p style="color:var(--navy-200);text-align:center;padding:var(--space-2xl);">No messages yet.</p>';
          return;
        }
        msgContainer.innerHTML = data.messages.map(m => {
          const isUnread = !m.opened_at && m.status !== 'draft';
          const time = m.created_at ? new Date(m.created_at).toLocaleDateString() : '';
          return `<div class="message-item ${isUnread ? 'unread' : ''}">
            <div class="avatar avatar-navy avatar-sm">${GSP.esc((m.sender_name || 'GS').slice(0,2).toUpperCase())}</div>
            <div style="flex:1;min-width:0;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <h4 style="font-size:var(--font-size-sm);font-weight:600;color:var(--white);">${GSP.esc(m.sender_name || 'GSP Recruitment')}</h4>
                <span style="font-size:var(--font-size-xs);color:var(--navy-200);">${GSP.esc(time)}</span>
              </div>
              <p style="font-size:var(--font-size-xs);color:var(--navy-200);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${GSP.esc(m.subject || m.message_text || '')}</p>
              ${isUnread ? '<span class="badge badge-gold" style="font-size:0.6rem;padding:0.1rem 0.4rem;">New</span>' : ''}
            </div>
          </div>`;
        }).join('');
      } catch (err) {
        console.error('Messages load error:', err);
        const msgContainer = document.querySelector('#section-messages .dashboard-grid > div:first-child');
        Auth.renderLoadError(msgContainer, loadMessages);
      }
    }

    /* ================================================================
       API: Salary Benchmark
       ================================================================ */
    async function updateSalaryDisplay() {
      const role = document.getElementById('salaryRole').value;
      const level = document.getElementById('salaryLevel').value;
      try {
        const res = await Auth.fetch(`/v1/candidate/salary-benchmark?role_title=${encodeURIComponent(role)}&seniority=${encodeURIComponent(level)}`);
        if (!res) return;
        const data = await res.json();
        const chartEl = document.querySelector('#section-salary .chart-placeholder');
        if (data && data.length > 0) {
          const d = data[0];
          chartEl.innerHTML = `<div style="text-align:center;">
            <div style="font-size:var(--font-size-4xl);font-weight:800;color:var(--gold-500);">€${(d.p25/1000).toFixed(0)}K – €${(d.p75/1000).toFixed(0)}K</div>
            <p style="color:var(--navy-200);font-size:var(--font-size-sm);">${GSP.esc(d.role_title)} — Netherlands 2026</p>
          </div>`;
          // Update percentile cards
          const cards = document.querySelectorAll('#section-salary .stat-card .stat-value');
          if (cards.length >= 3) {
            cards[0].textContent = '€' + (d.p25/1000).toFixed(0) + 'K';
            cards[1].textContent = '€' + (d.p50/1000).toFixed(0) + 'K';
            cards[2].textContent = '€' + (d.p75/1000).toFixed(0) + 'K';
          }
        } else {
          chartEl.innerHTML = `<div style="text-align:center;color:var(--navy-200);padding:var(--space-lg);">No benchmark data available for this selection.</div>`;
        }
      } catch (err) {
        console.error('Salary benchmark error:', err);
      }
    }

    document.getElementById('salaryRole').addEventListener('change', updateSalaryDisplay);
    document.getElementById('salaryLevel').addEventListener('change', updateSalaryDisplay);

    /* ---- Export PDF (no-op, frontend only) ---- */
    document.getElementById('exportPdfBtn').addEventListener('click', () => {
      Auth.toast('Salary report PDF downloaded!', 'success');
    });

    /* ================================================================
       API: Add skill
       ================================================================ */
    document.querySelector('#section-profile .btn-outline')?.addEventListener('click', async () => {
      const input = document.querySelector('#section-profile input[placeholder*="skill"]');
      if (!input || !input.value.trim()) return;
      try {
        const profileRes = await Auth.fetch('/v1/candidate/profile');
        if (!profileRes) return;
        const profile = await profileRes.json();
        const skills = profile.skills || [];
        skills.push(input.value.trim());
        await Auth.fetch('/v1/candidate/profile', {
          method: 'PUT',
          body: JSON.stringify({ skills }),
        });
        input.value = '';
        Auth.toast('Skill added!', 'success');
        loadProfile();
      } catch (err) {
        Auth.toast('Error adding skill', 'error');
      }
    });

    /* ================================================================
       Initial load
       ================================================================ */
    document.addEventListener('DOMContentLoaded', () => {
      loadDashboard();
      loadMatches();
      loadApplications();
      loadMessages();
    });

    /* ---- Logout ---- */
    document.getElementById('sidebarLogoutBtn').addEventListener('click', () => Auth.logout());

    /* ---- Language sync ---- */
    const savedLang = localStorage.getItem('gsp_lang');
    if (savedLang === 'nl' || savedLang === 'en') {
      document.documentElement.setAttribute('data-lang', savedLang);
    }

    /* ---- Delegated data-action handler (WS-A.9b: no inline onclick=
       attributes -- the enforced CSP drops 'unsafe-inline' from
       script-src, which also governs inline event-handler attributes). */
    document.addEventListener('click', (e) => {
      const el = e.target.closest('[data-action]');
      if (!el) return;
      const id = el.dataset.id;
      switch (el.dataset.action) {
        case 'navigate': navigateTo(el.dataset.section); break;
        case 'apply-job': applyToJob(Number(id) || 0); break;
        case 'toast-details-soon': Auth.toast('Details coming soon'); break;
        case 'toast-delete-account':
          Auth.toast('Contact info@gsprecruitment.nl to delete your account', 'warning');
          break;
      }
    });
