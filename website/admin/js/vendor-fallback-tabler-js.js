/* WS-A.9b (M1): vendored Tabler JS with a CDN fallback, same reasoning as
 * vendor-fallback-css.js -- element created + listener attached before the
 * script is inserted (and so before the fetch can start), no onerror=
 * attribute. */
(function () {
  'use strict';

  var script = document.createElement('script');
  script.src = 'vendor/tabler/js/tabler.min.js';
  script.addEventListener('error', function onError() {
    script.removeEventListener('error', onError);
    var fallback = document.createElement('script');
    fallback.src = 'https://cdn.jsdelivr.net/npm/@tabler/core@1.4.0/dist/js/tabler.min.js';
    document.body.appendChild(fallback);
  }, { once: true });
  document.body.appendChild(script);
})();
