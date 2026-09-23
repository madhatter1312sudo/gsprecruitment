/* ============================================================
   GSP Recruitment — admin/js/sections/analytics.js
   Platformcijfers en de groeigrafiek (ApexCharts, met fallback).

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern) en voor nav.js, dat de registry uitleest. Geen ES-module: de
   rest van de site gebruikt die ook niet.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  Object.assign(Admin, {
  /* ============================================================
     ANALYTICS
     ============================================================ */
  // WS2 fix: never touch #analyticsContent (the shared parent of both
  // panels) with innerHTML again — a failed fetch used to nuke both the
  // chart card AND the summary card's markup permanently (a later retry
  // had nothing left to mount into). Load/error state is set on
  // #userGrowthChart and #analyticsSummary independently instead, and
  // loadAnalytics() itself rethrows on failure so nav.js's sectionLoaders
  // promise sees the rejection and un-caches the section (retrying it
  // reloads on the next visit, not just via the in-panel retry link).
  async loadAnalytics() {
    const growthEl = document.getElementById('userGrowthChart');
    const summaryEl = document.getElementById('analyticsSummary');
    const spinner = html`<div class="a-state-cell"><i class="fa-solid fa-spinner fa-spin"></i></div>`;
    mount(growthEl, spinner);
    mount(summaryEl, spinner);
    try {
      const res = await Auth.fetch('/v1/admin/analytics');
      if (!res?.ok) throw new Error('Failed');
      const data = await res.json();
      this._data.analytics = data;
      this.renderAnalytics(data);
    } catch (err) {
      this.setContainerLoadError(growthEl, () => this.loadAnalytics());
      this.setContainerLoadError(summaryEl, () => this.loadAnalytics());
      throw err;
    }
  },

  renderAnalytics(data) {
    document.getElementById('kpiJobFillRate').textContent = (data.job_fill_rate ?? 0) + '%';
    document.getElementById('kpiClientRetention').textContent = (data.client_retention_rate ?? 0) + '%';
    document.getElementById('kpiCandidatePlacement').textContent = (data.candidate_satisfaction ?? 0) + '%';

    this.renderAnalyticsSummary(data);

    const growthEl = document.getElementById('userGrowthChart');
    if (!growthEl || !data.user_growth) return;
    const entries = Object.entries(data.user_growth).sort(([a], [b]) => a.localeCompare(b));
    if (!entries.length) { mount(growthEl, html`<div class="a-soft">No data yet</div>`); return; }

    if (window.ApexCharts) {
      mount(growthEl, raw(''));
      growthEl.style.display = '';
      const labels = entries.map(([month]) => new Date(month).toLocaleDateString('en-GB', { month: 'short' }));
      const values = entries.map(([, count]) => count);
      if (this._growthChart) { this._growthChart.destroy(); this._growthChart = null; }
      this._growthChart = new ApexCharts(growthEl, {
        chart: { type: 'bar', height: 200, background: 'transparent', toolbar: { show: false } },
        series: [{ name: 'Users', data: values }],
        xaxis: { categories: labels, axisBorder: { show: false }, axisTicks: { show: false } },
        colors: ['#E8B400'],
        plotOptions: { bar: { borderRadius: 4, columnWidth: '55%' } },
        dataLabels: { enabled: false },
        grid: { borderColor: 'rgba(255,255,255,0.06)' },
        theme: { mode: 'dark' },
      });
      this._growthChart.render();
    } else {
      const max = Math.max(...entries.map(([, v]) => v), 1);
      mount(growthEl, html`<div class="a-barchart">
        ${entries.map(([month, count]) => {
          const h = Math.round((count / max) * 110);
          const label = new Date(month).toLocaleDateString('en-GB', { month: 'short' });
          return html`<div class="a-barchart__col">
            <div class="a-barchart__cap">${count}</div>
            <div class="a-barchart__bar" style="--a-bar-h:${h}px;"></div>
            <div class="a-barchart__cap">${label}</div>
          </div>`;
        })}
      </div>`);
    }
  },

  // Platform Summary card — fill rate, client retention and
  // candidate_satisfaction (API field name unchanged; the UI label is
  // "Plaatsingsratio", matching the KPI card above it).
  renderAnalyticsSummary(data) {
    const el = document.getElementById('analyticsSummary');
    if (!el) return;
    const row = (label, value) => html`
      <div class="a-metric-row">
        <span class="a-soft">${label}</span>
        <strong class="a-cell-strong">${value}%</strong>
      </div>`;
    mount(el, html`
      ${row('Fill rate', data.job_fill_rate ?? 0)}
      ${row('Klantretentie', data.client_retention_rate ?? 0)}
      ${row('Plaatsingsratio', data.candidate_satisfaction ?? 0)}
    `);
  },
  });

  Admin.registerSection({
    id: 'analytics',
    title: 'Analytics',
    loader: () => Admin.loadAnalytics(),
    filters: [],
  });
})();
