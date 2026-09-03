(() => {
  'use strict';
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
      errEl.textContent = 'Passwords do not match.';
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
        successEl.textContent = 'Password reset successfully. You can now sign in.';
        successEl.style.display = 'block';
        form.style.display = 'none';
        Auth.toast('Password reset successfully!', 'success');
        setTimeout(() => { window.location.href = '/'; }, 2000);
      } else {
        errEl.textContent = data.detail || 'This reset link is invalid or has expired.';
        errEl.style.display = 'block';
      }
    } catch (err) {
      errEl.textContent = 'Network error. Please try again.';
      errEl.style.display = 'block';
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fas fa-key"></i> <span class="lang-en">Set new password</span><span class="lang-nl">Wachtwoord instellen</span>';
      }
    }
  });
})();
