(() => {
  'use strict';

  // WS-C.17 security-audit fix: the token comes from the URL *fragment*
  // (#token=...), never the query string -- a fragment is never sent to
  // the server in the request line, never logged by nginx/Caddy access
  // logs, and never forwarded in a Referer header the way a ?token=
  // query param would be. routers/public.py's confirmation e-mail link
  // must use #token= to match (see _send_talentpool_confirm_email).
  const hash = window.location.hash.replace(/^#/, '');
  const params = new URLSearchParams(hash);
  const token = params.get('token');

  // Security-audit fix (same reasoning as verify.js): strip the token out
  // of the URL immediately, before any fetch/analytics/third-party script
  // on this page can carry it into browser history or a log line.
  if (token) {
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  const missing = document.getElementById('verifyMissingToken');
  const pending = document.getElementById('verifyPending');
  const resultBox = document.getElementById('verifyResult');
  const resultIcon = document.getElementById('verifyResultIcon');
  const resultText = document.getElementById('verifyResultText');

  function showMissing() {
    missing.style.display = 'block';
  }

  function showResult(ok, messageEn, messageNl) {
    pending.style.display = 'none';
    resultBox.style.display = 'block';
    resultIcon.className = 'verify-icon ' + (ok ? 'success' : 'error');
    resultIcon.innerHTML = ok ? '<i class="fas fa-circle-check"></i>' : '<i class="fas fa-circle-xmark"></i>';
    // Both languages shown at once; text is set via textContent, not
    // innerHTML -- GSP.esc() below even though messageEn/messageNl are
    // fixed strings this script wrote itself, for defense in depth /
    // consistency with verify.js.
    resultText.textContent = document.documentElement.dataset.lang === 'en'
      ? GSP.esc(messageEn)
      : `${GSP.esc(messageNl)} / ${GSP.esc(messageEn)}`;
  }

  if (!token) {
    showMissing();
    return;
  }

  pending.style.display = 'block';

  fetch(`${Auth.API}/public/talentpool-confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
    .then(async (res) => {
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        showResult(true,
          'Your talent pool sign-up is confirmed. We will contact you about roles that fit.',
          'Je talentpool-aanmelding is bevestigd. Wij nemen contact op bij passende rollen.');
      } else {
        showResult(false,
          data.detail || 'This confirmation link is invalid or has expired.',
          'Deze bevestigingslink is ongeldig of verlopen.');
      }
    })
    .catch(() => {
      showResult(false, 'Network error. Please try again.', 'Netwerkfout. Probeer het opnieuw.');
    });
})();
