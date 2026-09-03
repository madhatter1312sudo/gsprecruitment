(() => {
  'use strict';
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  // GSP.esc() is used below even though every value lands via textContent
  // (never innerHTML) -- this page still loads gsp-util.js and routes any
  // interpolated text through it for defense in depth / consistency with
  // the rest of the portal, per WS-E.2/E.3.
  const mode = GSP.esc(params.get('mode') || '');

  // Security-audit fix: strip the raw token out of the URL immediately,
  // before any fetch/analytics/third-party script on this page can carry
  // it into browser history, a Referer header, or a log line -- same
  // reasoning as the Google-callback fragment fix (routers/auth.py
  // google_callback / script.js handleGoogleAuthCallback). `token` and
  // `mode` are already captured above, so the rest of this script keeps
  // working off those local consts.
  if (token) {
    window.history.replaceState({}, document.title, window.location.pathname);
  }

  const missing = document.getElementById('verifyMissingToken');
  const pending = document.getElementById('verifyPending');
  const resultBox = document.getElementById('verifyResult');
  const resultIcon = document.getElementById('verifyResultIcon');
  const resultText = document.getElementById('verifyResultText');
  const setPwForm = document.getElementById('setPwForm');

  function showMissing() {
    missing.style.display = 'block';
  }

  function showResult(ok, messageEn, messageNl) {
    pending.style.display = 'none';
    setPwForm.style.display = 'none';
    resultBox.style.display = 'block';
    resultIcon.className = 'verify-icon ' + (ok ? 'success' : 'error');
    resultIcon.innerHTML = ok ? '<i class="fas fa-circle-check"></i>' : '<i class="fas fa-circle-xmark"></i>';
    // Both languages shown at once (same pattern the header lang toggle
    // relies on elsewhere); text is set via textContent, not innerHTML.
    resultText.textContent = document.documentElement.dataset.lang === 'en' ? messageEn : `${messageNl} / ${messageEn}`;
  }

  if (!token) {
    showMissing();
    return;
  }

  if (mode === 'set-password') {
    // WS-E.3 team-invite flow: show the set-password form instead of
    // auto-verifying -- the token is consumed by POST /auth/set-password,
    // which also marks the e-mail verified in the same step.
    setPwForm.style.display = 'block';

    setPwForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const errEl = document.getElementById('setPwError');
      const successEl = document.getElementById('setPwSuccess');
      errEl.style.display = 'none';
      successEl.style.display = 'none';

      const newPw = document.getElementById('setPwNew')?.value || '';
      const confirmPw = document.getElementById('setPwConfirm')?.value || '';

      const pwErr = Auth.validatePassword(newPw);
      if (pwErr) {
        errEl.textContent = pwErr;
        errEl.style.display = 'block';
        return;
      }
      if (newPw !== confirmPw) {
        errEl.textContent = 'Passwords do not match.';
        errEl.style.display = 'block';
        return;
      }

      const submitBtn = setPwForm.querySelector('button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-sm"></span> Saving...';
      }

      try {
        const res = await fetch(`${Auth.API}/auth/set-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token, new_password: newPw }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
          Auth.toast('Password set successfully!', 'success');
          showResult(true, 'Your password is set and your account is active. You can now sign in.',
            'Je wachtwoord is ingesteld en je account is actief. Je kunt nu inloggen.');
        } else {
          errEl.textContent = data.detail || 'This link is invalid or has expired.';
          errEl.style.display = 'block';
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fas fa-key"></i> <span class="lang-en">Set password &amp; activate</span><span class="lang-nl">Wachtwoord instellen &amp; activeren</span>';
          }
        }
      } catch (err) {
        errEl.textContent = 'Network error. Please try again.';
        errEl.style.display = 'block';
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="fas fa-key"></i> <span class="lang-en">Set password &amp; activate</span><span class="lang-nl">Wachtwoord instellen &amp; activeren</span>';
        }
      }
    });
    return;
  }

  // WS-E.2: plain verification link -- POST the token immediately, no
  // user action required beyond having clicked the e-mail link.
  pending.style.display = 'block';

  fetch(`${Auth.API}/auth/verify-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
    .then(async (res) => {
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        showResult(true, 'Your e-mail address is confirmed. You can now sign in.',
          'Je e-mailadres is bevestigd. Je kunt nu inloggen.');
      } else {
        showResult(false, data.detail || 'This verification link is invalid or has expired.',
          'Deze verificatielink is ongeldig of verlopen.');
      }
    })
    .catch(() => {
      showResult(false, 'Network error. Please try again.', 'Netwerkfout. Probeer het opnieuw.');
    });
})();
