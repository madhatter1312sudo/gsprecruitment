(() => {
  'use strict';
  const lang = localStorage.getItem('gsp_lang') || 'nl';
  // WS-A.8: the site is Dutch-first with an EN toggle everywhere else, but
  // these four messages were English-only regardless of the visitor's
  // chosen language. Auth.validatePassword()'s own messages are shared
  // across every auth form site-wide (auth.js) and stay out of scope here.
  const MSG = {
    passwordsDontMatch: { en: 'Passwords do not match.', nl: 'Wachtwoorden komen niet overeen.' },
    resetSuccess: { en: 'Password reset successfully. You can now sign in.', nl: 'Wachtwoord succesvol gewijzigd. Je kunt nu inloggen.' },
    resetSuccessToast: { en: 'Password reset successfully!', nl: 'Wachtwoord succesvol gewijzigd!' },
    linkInvalid: { en: 'This reset link is invalid or has expired.', nl: 'Deze resetlink is ongeldig of verlopen.' },
    networkError: { en: 'Network error. Please try again.', nl: 'Netwerkfout. Probeer het opnieuw.' },
  };
  const t = (key) => MSG[key][lang] || MSG[key].nl;

  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  const form = document.getElementById('resetPwForm');
  const missing = document.getElementById('resetMissingToken');
  const errEl = document.getElementById('resetPwError');
  const successEl = document.getElementById('resetPwSuccess');

  if (!token) {
    if (form) form.style.display = 'none';
    if (missing) missing.style.display = 'block';
    return;
  }

  form?.addEventListener('submit', async (e) => {
    e.preventDefault();
    errEl.style.display = 'none';
    successEl.style.display = 'none';

    const newPw = document.getElementById('resetPwNew')?.value || '';
    const confirmPw = document.getElementById('resetPwConfirm')?.value || '';

    const pwErr = Auth.validatePassword(newPw);
    if (pwErr) {
      errEl.textContent = pwErr;
      errEl.style.display = 'block';
      return;
    }
    if (newPw !== confirmPw) {
      errEl.textContent = t('passwordsDontMatch');
      errEl.style.display = 'block';
      return;
    }

    const submitBtn = form.querySelector('button[type="submit"]');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="spinner-sm"></span> Saving...';
    }

    try {
      const res = await fetch(`${Auth.API}/auth/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: newPw }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        successEl.textContent = t('resetSuccess');
        successEl.style.display = 'block';
        form.style.display = 'none';
        Auth.toast(t('resetSuccessToast'), 'success');
        setTimeout(() => { window.location.href = '/'; }, 2000);
      } else {
        errEl.textContent = data.detail || t('linkInvalid');
        errEl.style.display = 'block';
      }
    } catch (err) {
      errEl.textContent = t('networkError');
      errEl.style.display = 'block';
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fas fa-key"></i> <span class="lang-en">Set new password</span><span class="lang-nl">Wachtwoord instellen</span>';
      }
    }
  });
})();
