/* WS-A.9b (M1): vendored CSS with a CDN fallback, without inline onerror=
 * attributes (blocked once the enforced CSP drops 'unsafe-inline' from
 * script-src -- inline event-handler attributes are governed by script-src
 * too). Creates the <link> elements here instead of in the HTML so the
 * error listener is always attached before the fetch starts (no race). */
(function () {
  'use strict';

  function loadCss(href, fallbackHref) {
    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.addEventListener('error', function onError() {
      link.removeEventListener('error', onError);
      link.href = fallbackHref;
    }, { once: true });
    document.head.appendChild(link);
  }

  loadCss('vendor/fontawesome/css/all.min.css', 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css');
  loadCss('vendor/tabler/css/tabler.min.css', 'https://cdn.jsdelivr.net/npm/@tabler/core@1.4.0/dist/css/tabler.min.css');
})();
