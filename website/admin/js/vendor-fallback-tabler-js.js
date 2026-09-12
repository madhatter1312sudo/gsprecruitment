/* WS-A.9b (M1): vendored Tabler JS met een CDN-fallback, zelfde redenering
 * als vendor-fallback-css.js: element gemaakt en listener gekoppeld voordat
 * het script wordt ingevoegd (en dus voordat de fetch kan starten), geen
 * onerror=-attribuut.
 *
 * WS5: tabler.min.js is een UMD die alles onder window.tabler hangt, met
 * daarin een volledige `bootstrap`-namespace (Modal, Offcanvas, Collapse,
 * Tab, Toast, ...). Het zet window.bootstrap zelf niet. Code die op de
 * Bootstrap 5-componenten leunt -- js/ui.js voor modal en drawer, en nav.js
 * dat het zijmenu sluit na navigatie -- verwacht die wel op window. Daarom
 * wordt de namespace hier na het laden doorgezet, voor zowel de lokale
 * kopie als de CDN-fallback. Zonder dit draait ui.js permanent op zijn
 * vangnet en sluit het mobiele zijmenu niet na een navigatie. */
(function () {
  'use strict';

  function exposeBootstrap() {
    if (!window.bootstrap && window.tabler) {
      window.bootstrap = window.tabler.bootstrap || window.tabler;
    }
  }

  var script = document.createElement('script');
  script.src = 'vendor/tabler/js/tabler.min.js';
  script.addEventListener('load', exposeBootstrap, { once: true });
  script.addEventListener('error', function onError() {
    script.removeEventListener('error', onError);
    var fallback = document.createElement('script');
    fallback.src = 'https://cdn.jsdelivr.net/npm/@tabler/core@1.4.0/dist/js/tabler.min.js';
    fallback.addEventListener('load', exposeBootstrap, { once: true });
    document.body.appendChild(fallback);
  }, { once: true });
  document.body.appendChild(script);
})();
