/* ============================================================
   GSP Recruitment — admin/js/nav.js
   Navigatie en filterbinding, allebei gevoed door de sectieregistry
   (Admin.registerSection, zie js/admin.js). Dit bestand kent zelf geen
   enkele sectie bij naam meer: titels, loaders en filters komen uit de
   registry, zodat er één plek is waar een sectie zichzelf beschrijft.
   Laadt als laatste script, na alle sectiemodules.
   ============================================================ */

/* ---- Navigatie ---- */
const sectionTitles = {};
const sectionLoaders = {};
Admin.sections().forEach(sec => {
  sectionTitles[sec.id] = sec.title || sec.id;
  // Het dashboard laadt Admin.init() zelf al; het staat daarom wel in de
  // titelmap maar niet in de loadermap (anders zou het eerste bezoek aan
  // #dashboard een tweede keer laden).
  if (sec.id !== 'dashboard' && typeof sec.loader === 'function') {
    sectionLoaders[sec.id] = sec.loader;
  }
});

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
    // Elke loader is async. Een sectie waarvan het laden afwijst (bijv.
    // loadAnalytics() bij een mislukte fetch, WS2) wordt hier weer
    // ontcachet, zodat een volgend bezoek het opnieuw probeert in plaats
    // van voorgoed op een leeg of foutpaneel te blijven staan.
    Promise.resolve(sectionLoaders[section]()).catch(() => { loaded.delete(section); });
  }
}

document.querySelectorAll('.nav-link[data-section]').forEach(item => {
  item.addEventListener('click', (e) => { e.preventDefault(); navigateTo(item.dataset.section); });
});

const hash = window.location.hash.replace('#', '');
if (hash && sectionTitles[hash]) navigateTo(hash);

/* ---- Filters uit de registry ----
   Precies één binding per element. Hiervoor stond de helft van deze
   handlers in nav.js en de andere helft in Admin.bindFilters(); die
   tweedeling is de reden dat een dubbele binding ooit twee API-calls per
   toetsaanslag opleverde (commit d0917af). Nu is er één lus. */
Admin.sections().forEach(sec => {
  (sec.filters || []).forEach(filter => {
    document.querySelectorAll(filter.selector).forEach(el => {
      if (el.dataset.gspFilterBound === '1') return;
      el.dataset.gspFilterBound = '1';
      const run = filter.debounce
        ? Admin.debounce(() => filter.handler(el), filter.debounce)
        : (e) => filter.handler(el, e);
      el.addEventListener(filter.event || 'change', run);
    });
  });
});

/* ---- Logout ---- */
document.getElementById('sidebarLogoutBtn').addEventListener('click', () => Auth.logout());

/* ---- Taalvoorkeur ---- */
const savedLang = localStorage.getItem('gsp_lang');
if (savedLang === 'nl' || savedLang === 'en') document.documentElement.setAttribute('data-lang', savedLang);
