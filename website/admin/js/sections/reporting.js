/* ============================================================
   GSP Recruitment — admin/js/sections/reporting.js
   Rapportage, volledig berekend uit data die de API al teruggeeft.

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern) en voor nav.js, dat de registry uitleest. Geen ES-module: de
   rest van de site gebruikt die ook niet.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  Object.assign(Admin, {
  /* ============================================================
     RAPPORTAGE — computed client-side from data the API already
     returns (no invented KPIs): open jobs per dienstlijn
     (employment_type, excluding is_demo -- the admin jobs endpoint
     already excludes those unless include_demo=true), and leads per
     category this week/month + total unread, from the most recent 200
     leads (the leads endpoint has no date filter, so this is a sample,
     called out in the UI caption rather than pretending it's exhaustive).
     ============================================================ */
  async loadReporting() {
    const el = document.getElementById('reportingContent');
    if (el) mount(el, html`<div class="a-state-cell"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>`);
    try {
      const [jobsRes, leadsRes, unreadRes] = await Promise.all([
        Auth.fetch('/v1/admin/jobs?status=open&limit=200'),
        Auth.fetch('/v1/admin/leads?limit=200'),
        Auth.fetch('/v1/admin/leads?unread=true&limit=1'),
      ]);
      if (!jobsRes?.ok || !leadsRes?.ok) throw new Error('Failed');
      const jobsData = await jobsRes.json();
      const leadsData = await leadsRes.json();
      const unreadData = unreadRes?.ok ? await unreadRes.json() : null;
      this.renderReporting(jobsData, leadsData, unreadData);
    } catch {
      if (el) mount(el, html`<div class="a-state-cell text-danger-ink">Rapportage kon niet geladen worden.</div>`);
    }
  },

  renderReporting(jobsData, leadsData, unreadData) {
    const el = document.getElementById('reportingContent');
    if (!el) return;

    const jobs = jobsData.items || [];
    const byType = new Map();
    jobs.forEach(j => {
      const t = j.employment_type || 'onbekend';
      byType.set(t, (byType.get(t) || 0) + 1);
    });

    const now = new Date();
    const startOfWeek = new Date(now);
    const dow = (startOfWeek.getDay() + 6) % 7; // Monday = 0
    startOfWeek.setDate(startOfWeek.getDate() - dow);
    startOfWeek.setHours(0, 0, 0, 0);
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);

    const leads = leadsData.items || [];
    const bucket = () => ({ werving_selectie: 0, detachering_internationaal: 0, kandidaat: 0, overig: 0, quiz: 0 });
    const week = bucket();
    const month = bucket();
    leads.forEach(l => {
      const created = new Date(l.created_at);
      const key = l.interest_type || 'quiz';
      if (created >= startOfWeek) week[key] = (week[key] || 0) + 1;
      if (created >= startOfMonth) month[key] = (month[key] || 0) + 1;
    });

    const jobsCapNote = (jobsData.total || 0) > jobs.length ? html`<div class="a-meta mt-2">Toont ${jobs.length} van ${jobsData.total} open vacatures.</div>` : '';
    const leadsCapNote = (leadsData.total || 0) > leads.length ? html`<div class="a-meta mt-2">Gebaseerd op de meest recente ${leads.length} van ${leadsData.total} leads.</div>` : '';

    const rows = [
      ['werving_selectie', 'Werving & selectie'], ['detachering_internationaal', 'Detachering (internationaal)'],
      ['kandidaat', 'Kandidaat'], ['overig', 'Overig'], ['quiz', 'Quiz (geen categorie)'],
    ];

    mount(el, html`
      <div class="row row-deck row-cards mb-4">
        <div class="col-sm-4">
          <div class="card card-sm"><div class="card-body">
            <div class="subheader"><i class="fa-solid fa-briefcase me-1"></i>Open vacatures</div>
            <div class="h1 mb-0">${jobs.length}</div>
          </div></div>
        </div>
        <div class="col-sm-4">
          <div class="card card-sm"><div class="card-body">
            <div class="subheader"><i class="fa-solid fa-envelope me-1"></i>Leads ongelezen</div>
            <div class="h1 mb-0">${unreadData ? (unreadData.total ?? 0) : '—'}</div>
          </div></div>
        </div>
        <div class="col-sm-4">
          <div class="card card-sm"><div class="card-body">
            <div class="subheader"><i class="fa-regular fa-calendar me-1"></i>Leads deze week</div>
            <div class="h1 mb-0">${Object.values(week).reduce((a, b) => a + b, 0)}</div>
          </div></div>
        </div>
      </div>

      <div class="row row-cards">
        <div class="col-lg-6">
          <div class="card">
            <div class="card-header"><h3 class="card-title"><i class="fa-solid fa-layer-group text-primary me-2"></i>Open vacatures per dienstlijn</h3></div>
            <div class="card-body">
              ${byType.size ? html`<table class="table table-vcenter card-table">
                <tbody>${Array.from(byType.entries()).map(([t, n]) => html`
                  <tr><td class="a-soft">${this.dienstlijnLabel(t)}</td><td class="text-end a-cell-name">${n}</td></tr>`)}</tbody>
              </table>` : html`<div class="a-soft">Geen open vacatures.</div>`}
              ${jobsCapNote}
            </div>
          </div>
        </div>
        <div class="col-lg-6">
          <div class="card">
            <div class="card-header"><h3 class="card-title"><i class="fa-solid fa-chart-column text-primary me-2"></i>Leads per categorie</h3></div>
            <div class="card-body">
              <table class="table table-vcenter card-table">
                <thead><tr><th>Categorie</th><th class="text-end">Deze week</th><th class="text-end">Deze maand</th></tr></thead>
                <tbody>${rows.map(([key, label]) => html`
                  <tr>
                    <td class="a-soft">${label}</td>
                    <td class="text-end a-cell-strong">${week[key] || 0}</td>
                    <td class="text-end a-cell-strong">${month[key] || 0}</td>
                  </tr>`)}</tbody>
              </table>
              ${leadsCapNote}
            </div>
          </div>
        </div>
      </div>
    `);
  },
  });

  Admin.registerSection({
    id: 'reporting',
    title: 'Rapportage',
    skeletonHtml: () => html`
      <div id="reportingContent">
        <div class="a-state-cell"><i class="fa-solid fa-spinner fa-spin"></i> Laden…</div>
      </div>`,
    loader: () => Admin.loadReporting(),
    filters: [],
  });
})();
