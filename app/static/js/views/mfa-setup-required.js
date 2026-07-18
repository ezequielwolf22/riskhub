/* Vista de configuración obligatoria de MFA (política de la organización o forzado por admin). */
const ViewMfaSetupRequired = {
  _step: 'password',
  _secret: '',

  async render(main) {
    ViewMfaSetupRequired._step = 'password';
    main.innerHTML = `
      <div style="display:flex;justify-content:center;align-items:flex-start;min-height:60vh;padding:40px 16px;">
        <div class="card" style="width:100%;max-width:460px;">
          <h2 style="margin-bottom:6px;">Verificación en dos pasos requerida</h2>
          <p style="color:var(--text-muted);margin-bottom:24px;font-size:14px;">
            Tu administrador exige autenticación de dos factores (MFA) para acceder a RiskHub.
            Configura tu app de autenticación (Google Authenticator, Microsoft Authenticator, Authy)
            antes de continuar.
          </p>
          <div id="msr-error" class="login-error" style="display:none;margin-bottom:16px;"></div>
          <div id="msr-content"></div>
        </div>
      </div>`;
    ViewMfaSetupRequired._renderPasswordStep();
  },

  _renderPasswordStep() {
    ViewMfaSetupRequired._step = 'password';
    const content = document.getElementById('msr-content');
    content.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:14px;">
        <div>
          <label style="display:block;font-size:13px;font-weight:500;margin-bottom:4px;">
            Contraseña actual *
          </label>
          <input type="password" id="msr-password" class="input" autocomplete="current-password">
        </div>
        <button class="btn btn-primary" id="msr-continue" style="margin-top:8px;">
          Continuar
        </button>
        <button class="btn btn-ghost" onclick="Auth.logout()" style="font-size:13px;color:var(--text-muted);">
          Cerrar sesión
        </button>
      </div>`;

    document.getElementById('msr-continue').onclick = async () => {
      const password = document.getElementById('msr-password').value;
      const errBox = document.getElementById('msr-error');
      errBox.style.display = 'none';
      if (!password) {
        errBox.textContent = 'Introduce tu contraseña actual.';
        errBox.style.display = 'block';
        return;
      }
      const btn = document.getElementById('msr-continue');
      btn.disabled = true;
      btn.textContent = 'Verificando...';
      try {
        const res = await Api.mfa.setup(password);
        ViewMfaSetupRequired._secret = res.secret || '';
        ViewMfaSetupRequired._renderQrStep(res.otpauth_url || '');
      } catch (e) {
        errBox.textContent = e.message || 'No se pudo iniciar la configuración de MFA.';
        errBox.style.display = 'block';
        btn.disabled = false;
        btn.textContent = 'Continuar';
      }
    };
  },

  _renderQrStep(otpauthUrl) {
    ViewMfaSetupRequired._step = 'qr';
    const content = document.getElementById('msr-content');
    content.innerHTML = `
      <div style="text-align:center;">
        <p style="font-size:13px;margin-bottom:12px;">
          Escanea este código con tu app de autenticación.
        </p>
        <canvas id="msr-qr-canvas" style="display:block;margin:0 auto 12px;"></canvas>
        <p style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">O introduce el código manualmente:</p>
        <code style="font-size:13px;font-weight:700;letter-spacing:.1em;background:var(--bg-2);padding:6px 12px;border-radius:6px;display:inline-block;margin-bottom:16px;">
          ${UI.esc(ViewMfaSetupRequired._secret)}
        </code>
        <div style="text-align:left;margin-top:8px;">
          <label style="display:block;font-size:13px;font-weight:500;margin-bottom:4px;">
            Código de verificación (6 digitos) *
          </label>
          <input type="text" id="msr-code" class="input" placeholder="123456" maxlength="6" inputmode="numeric">
        </div>
        <button class="btn btn-primary" id="msr-verify" style="margin-top:14px;width:100%;">
          Verificar y activar
        </button>
      </div>`;

    setTimeout(() => {
      const canvas = document.getElementById('msr-qr-canvas');
      if (canvas && window.QRCode) {
        new QRCode(canvas, { text: otpauthUrl, width: 200, height: 200 });
      } else if (canvas) {
        canvas.style.display = 'none';
        const p = document.createElement('p');
        p.style.cssText = 'font-size:10px;color:var(--text-muted);word-break:break-all;margin-bottom:12px;';
        p.textContent = 'URL para app: ' + otpauthUrl;
        canvas.parentNode.insertBefore(p, canvas);
      }
    }, 50);

    document.getElementById('msr-verify').onclick = async () => {
      const code = document.getElementById('msr-code').value.trim();
      const errBox = document.getElementById('msr-error');
      errBox.style.display = 'none';
      if (!code || code.length !== 6) {
        errBox.textContent = 'Introduce el código de 6 digitos.';
        errBox.style.display = 'block';
        return;
      }
      const btn = document.getElementById('msr-verify');
      btn.disabled = true;
      btn.textContent = 'Verificando...';
      try {
        const res = await Api.mfa.verifySetup({ secret: ViewMfaSetupRequired._secret, code });
        ViewMfaSetupRequired._renderBackupCodesStep(res.backup_codes || []);
      } catch (e) {
        errBox.textContent = e.message || 'Código incorrecto.';
        errBox.style.display = 'block';
        btn.disabled = false;
        btn.textContent = 'Verificar y activar';
      }
    };
  },

  _renderBackupCodesStep(codes) {
    ViewMfaSetupRequired._step = 'backup';
    const content = document.getElementById('msr-content');
    content.innerHTML = `
      <div>
        <p style="font-size:13px;color:var(--success-color,#22c55e);font-weight:600;margin-bottom:8px;">
          &#10003; MFA activado correctamente
        </p>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px;">
          Guarda estos códigos de recuperación en un lugar seguro. Cada uno es de un solo uso
          y no podras verlos de nuevo.
        </p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;background:var(--bg-2);padding:12px;border-radius:6px;margin-bottom:16px;">
          ${codes.map(c => `<code style="font-size:13px;">${UI.esc(c)}</code>`).join('')}
        </div>
        <button class="btn btn-primary" id="msr-finish" style="width:100%;">
          Continuar a RiskHub
        </button>
      </div>`;

    document.getElementById('msr-finish').onclick = () => {
      const u = Auth.user();
      if (u) {
        u.mfa_enabled = true;
        u.must_configure_mfa = false;
        localStorage.setItem('riskhub_user', JSON.stringify(u));
      }
      window.location.hash = '/dashboard';
    };
  },
};
