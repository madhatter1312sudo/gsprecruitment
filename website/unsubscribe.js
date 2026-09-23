(() => {
  'use strict';

  // WS3c -- een-klik-afmelden voor vacature-alerts.
  //
  // Zelfde tokenbehandeling als talentpool-confirm.js: het token komt uit
  // het URL-FRAGMENT (#token=...), nooit uit de querystring. Een fragment
  // wordt nooit in de request-regel naar de server gestuurd, staat dus
  // niet in een nginx/Caddy-accesslog en gaat niet mee in een
  // Referer-header. services/scheduler.py's job_alert_job bouwt de
  // voettekstlink in die vorm (_job_alert_unsubscribe_links).
  //
  // Anders dan talentpool-confirm.js wordt hier NIET automatisch bij het
  // laden gepost. Het afmeldtoken is eenmalig (job_alert_sends.used_at):
  // zou deze pagina bij het openen alvast "alerts" versturen, dan was het
  // token op en kon de bezoeker daarna niet meer voor "alle contact"
  // kiezen. Hij kiest dus eerst, en pas dan gaat er één verzoek uit.
  const hash = window.location.hash.replace(/^#/, '');
  const params = new URLSearchParams(hash);
  const token = params.get('token');

  // Zelfde reden als in verify.js/talentpool-confirm.js: haal het token
  // meteen uit de URL, voordat een script of de browsergeschiedenis het
  // kan meenemen.
  if (token) {
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  const missing = document.getElementById('unsubMissingToken');
  const choice = document.getElementById('unsubChoice');
  const pending = document.getElementById('unsubPending');
  const resultBox = document.getElementById('unsubResult');
  const resultIcon = document.getElementById('unsubResultIcon');
  const resultText = document.getElementById('unsubResultText');

  function showResult(ok, messageEn, messageNl) {
    pending.style.display = 'none';
    choice.style.display = 'none';
    resultBox.style.display = 'block';
    resultIcon.className = 'verify-icon ' + (ok ? 'success' : 'error');
    resultIcon.innerHTML = ok ? '<i class="fas fa-circle-check"></i>' : '<i class="fas fa-circle-xmark"></i>';
    // textContent, nooit innerHTML; GSP.esc() bovendien, net als
    // talentpool-confirm.js, ook al zijn dit vaste strings uit dit
    // bestand zelf.
    resultText.textContent = document.documentElement.dataset.lang === 'en'
      ? GSP.esc(messageEn)
      : `${GSP.esc(messageNl)} / ${GSP.esc(messageEn)}`;
  }

  if (!token) {
    missing.style.display = 'block';
    return;
  }

  choice.style.display = 'block';

  function submit(scope) {
    choice.style.display = 'none';
    pending.style.display = 'block';

    fetch(`${Auth.API}/public/unsubscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, scope }),
    })
      .then(async (res) => {
        if (!res.ok) {
          showResult(false,
            'Something went wrong. Please try again later.',
            'Er ging iets mis. Probeer het later opnieuw.');
          return;
        }
        // De backend antwoordt bewust altijd hetzelfde, ook voor een
        // onbekend of al gebruikt token (geen enumeratie-orakel), dus
        // deze pagina kan en mag niet meer zeggen dan dit.
        if (scope === 'all') {
          showResult(true,
            'If this link was valid, you will not receive any further messages from us.',
            'Als deze link geldig was, ontvang je geen berichten meer van ons.');
        } else {
          showResult(true,
            'If this link was valid, you will not receive further job alerts.',
            'Als deze link geldig was, ontvang je geen vacature-alerts meer.');
        }
      })
      .catch(() => {
        showResult(false, 'Network error. Please try again.', 'Netwerkfout. Probeer het opnieuw.');
      });
  }

  document.getElementById('unsubAlerts').addEventListener('click', () => submit('alerts'));
  document.getElementById('unsubAll').addEventListener('click', () => submit('all'));
})();
