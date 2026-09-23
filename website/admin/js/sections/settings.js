/* ============================================================
   GSP Recruitment — admin/js/sections/settings.js
   Instellingen, feature flags en de MFA-flow (WS-E.12).

   Registreert zichzelf via Admin.registerSection(). Geladen na admin.js
   (kern) en voor nav.js, dat de registry uitleest. Geen ES-module: de
   rest van de site gebruikt die ook niet.
   ============================================================ */
(function () {
  'use strict';
  const { html, raw, mount } = GSP;

  Object.assign(Admin, {
  /* ============================================================
     SETTINGS
     ============================================================ */
  async loadSettings() {
    await this.mfa.loadStatus();
    try {
      const res = await Auth.fetch('/v1/admin/settings');
      if (!res?.ok) return;
      const rows = await res.json();
      this._data.settings = rows;
      rows.forEach(s => {
        const el = document.getElementById(`setting_${s.key}`);
        if (el) {
          if (el.type === 'checkbox') el.checked = s.value === 'true';
          else el.value = s.value || '';
        }
      });
    } catch { console.error('Settings load error'); }
  },

  async saveSettings() {
    const btn = document.getElementById('saveSettingsBtn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving…'; }
    const settings = {};
    document.querySelectorAll('[data-setting-key]').forEach(el => {
      settings[el.dataset.settingKey] = el.type === 'checkbox' ? String(el.checked) : el.value;
    });
    try {
      const res = await Auth.fetch('/v1/admin/settings', {
        method: 'PUT', body: JSON.stringify({ settings }),
      });
      if (res?.ok) Auth.toast('Settings saved', 'success');
      else Auth.toast('Failed to save settings', 'error');
    } catch { Auth.toast('Network error', 'error'); }
    finally { if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-regular fa-floppy-disk"></i> Save Settings'; } }
  },

  /* ============================================================
     MFA (WS-E.12) — settings-section setup/enable/disable + the
     persistent "Zet tweestapsverificatie aan" banner. No inline
     onclick handlers here (CSP) -- everything is wired via
     addEventListener in bindUI(), called once from Admin.init().
     ============================================================ */
  mfa: {
    _enabled: false,

    async loadStatus() {
      try {
        const res = await Auth.fetch('/auth/mfa/status');
        if (!res?.ok) return;
        const data = await res.json();
        this._enabled = !!data.mfa_enabled;
        this.render();
      } catch { /* banner just stays hidden on a transient failure */ }
    },

    render() {
      const banner = document.getElementById('mfaBanner');
      if (banner) banner.hidden = this._enabled;

      const off = document.getElementById('mfaStateOff');
      const on = document.getElementById('mfaStateOn');
      const setup = document.getElementById('mfaSetupPanel');
      const recovery = document.getElementById('mfaRecoveryPanel');
      if (off) off.hidden = this._enabled;
      if (on) on.hidden = !this._enabled;
      if (setup) setup.hidden = true;
      if (recovery) recovery.hidden = true;
    },

    bindUI() {
      document.getElementById('mfaBannerSetupBtn')?.addEventListener('click', () => {
        document.querySelector('.nav-link[data-section="settings"]')?.click();
        document.getElementById('mfaStartSetupBtn')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });

      document.getElementById('mfaStartSetupBtn')?.addEventListener('click', () => this.startSetup());
      document.getElementById('mfaCancelSetupBtn')?.addEventListener('click', () => this.render());
      document.getElementById('mfaConfirmEnableBtn')?.addEventListener('click', () => this.confirmEnable());
      document.getElementById('mfaRecoveryDoneBtn')?.addEventListener('click', () => this.loadStatus());
      document.getElementById('mfaCopyRecoveryBtn')?.addEventListener('click', () => this.copyRecoveryCodes());
      document.getElementById('mfaDisableBtn')?.addEventListener('click', () => this.disable());
    },

    async startSetup() {
      const errEl = document.getElementById('mfaSetupError');
      if (errEl) errEl.hidden = true;
      try {
        const res = await Auth.fetch('/auth/mfa/setup', { method: 'POST' });
        const data = await res?.json();
        if (!res?.ok) {
          Auth.toast(data?.detail || 'Kon MFA-setup niet starten', 'error');
          return;
        }
        document.getElementById('mfaStateOff').hidden = true;
        document.getElementById('mfaSetupPanel').hidden = false;
        document.getElementById('mfaManualSecret').textContent = data.secret || '';
        const holder = document.getElementById('mfaQrHolder');
        // data.qr_svg is server-generated markup (core/mfa.py build_otpauth_svg,
        // fixed <rect>/<svg> structure, no user input interpolated into it) --
        // still routed through a DOMParser round-trip rather than a raw
        // innerHTML assignment, same defense-in-depth posture as
        // GSP.sanitizeHtml for any other server-supplied markup.
        if (holder) {
          holder.innerHTML = '';
          const doc = new DOMParser().parseFromString(data.qr_svg || '', 'image/svg+xml');
          const svg = doc.querySelector('svg');
          if (svg && !doc.querySelector('parsererror')) holder.appendChild(svg);
        }
        const codeInput = document.getElementById('mfaEnableCode');
        if (codeInput) { codeInput.value = ''; codeInput.focus(); }
      } catch {
        Auth.toast('Netwerkfout. Probeer het opnieuw.', 'error');
      }
    },

    async confirmEnable() {
      const errEl = document.getElementById('mfaSetupError');
      const code = document.getElementById('mfaEnableCode')?.value?.trim();
      if (!code) {
        if (errEl) { errEl.textContent = 'Voer de code uit je authenticator-app in.'; errEl.hidden = false; }
        return;
      }
      const btn = document.getElementById('mfaConfirmEnableBtn');
      if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Bezig…'; }
      try {
        const res = await Auth.fetch('/auth/mfa/enable', {
          method: 'POST', body: JSON.stringify({ code }),
        });
        const data = await res?.json();
        if (!res?.ok) {
          if (errEl) { errEl.textContent = data?.detail || 'Ongeldige code.'; errEl.hidden = false; }
          return;
        }
        this._enabled = true;
        document.getElementById('mfaSetupPanel').hidden = true;
        document.getElementById('mfaRecoveryPanel').hidden = false;
        document.getElementById('mfaRecoveryCodes').textContent = (data.recovery_codes || []).join('\n');
        document.getElementById('mfaBanner').hidden = true;
        Auth.toast('Tweestapsverificatie ingeschakeld', 'success');
      } catch {
        Auth.toast('Netwerkfout. Probeer het opnieuw.', 'error');
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Bevestigen en inschakelen'; }
      }
    },

    async copyRecoveryCodes() {
      const text = document.getElementById('mfaRecoveryCodes')?.textContent || '';
      try {
        await navigator.clipboard.writeText(text);
        Auth.toast('Herstelcodes gekopieerd', 'success');
      } catch {
        Auth.toast('Kopiëren mislukt, selecteer en kopieer de codes handmatig', 'warning');
      }
    },

    async disable() {
      const errEl = document.getElementById('mfaDisableError');
      const code = document.getElementById('mfaDisableCode')?.value?.trim();
      if (errEl) errEl.hidden = true;
      if (!code) {
        if (errEl) { errEl.textContent = 'Voer een code uit je authenticator-app in.'; errEl.hidden = false; }
        return;
      }
      const btn = document.getElementById('mfaDisableBtn');
      if (btn) { btn.disabled = true; }
      try {
        const res = await Auth.fetch('/auth/mfa/disable', {
          method: 'POST', body: JSON.stringify({ code }),
        });
        const data = await res?.json();
        if (!res?.ok) {
          if (errEl) { errEl.textContent = data?.detail || 'Ongeldige code.'; errEl.hidden = false; }
          return;
        }
        this._enabled = false;
        Auth.toast('Tweestapsverificatie uitgeschakeld', 'success');
        this.render();
      } catch {
        Auth.toast('Netwerkfout. Probeer het opnieuw.', 'error');
      } finally {
        if (btn) btn.disabled = false;
      }
    },
  },
  });

  Admin.registerSection({
    id: 'settings',
    title: 'Settings',
    loader: () => Admin.loadSettings(),
    filters: [],
    actions: {
      'save-settings': () => Admin.saveSettings(),
    },
  });
})();
