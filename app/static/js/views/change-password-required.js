/* Vista de cambio obligatorio de contraseña (primer login con OTP). */
const ViewChangePasswordRequired = {
  async render(main) {
    main.innerHTML = `
      <div style="display:flex;justify-content:center;align-items:flex-start;min-height:60vh;padding:40px 16px;">
        <div class="card" style="width:100%;max-width:460px;">
          <h2 style="margin-bottom:6px;">Cambio de contraseña requerido</h2>
          <p style="color:var(--text-muted);margin-bottom:24px;font-size:14px;">
            Tu cuenta fue creada con una contraseña temporal.
            Debes establecer una nueva contraseña antes de continuar.
          </p>
          <div id="cpr-error" class="login-error" style="display:none;margin-bottom:16px;"></div>
          <div style="display:flex;flex-direction:column;gap:14px;">
            <div>
              <label style="display:block;font-size:13px;font-weight:500;margin-bottom:4px;">
                Contraseña actual (temporal) *
              </label>
              <input type="password" id="cpr-current" class="input" autocomplete="current-password">
            </div>
            <div>
              <label style="display:block;font-size:13px;font-weight:500;margin-bottom:4px;">
                Nueva contraseña *
              </label>
              <input type="password" id="cpr-new" class="input" autocomplete="new-password">
              <p style="font-size:11px;color:var(--text-subtle);margin:4px 0 0;">
                Mínimo 8 caracteres, con mayuscula, minuscula, digito y simbolo especial.
              </p>
            </div>
            <div>
              <label style="display:block;font-size:13px;font-weight:500;margin-bottom:4px;">
                Confirmar nueva contraseña *
              </label>
              <input type="password" id="cpr-confirm" class="input" autocomplete="new-password">
            </div>
            <button class="btn btn-primary" id="cpr-save" style="margin-top:8px;">
              Establecer nueva contraseña
            </button>
          </div>
        </div>
      </div>`;

    document.getElementById('cpr-save').onclick = async () => {
      const current = document.getElementById('cpr-current').value;
      const newPwd  = document.getElementById('cpr-new').value;
      const confirm = document.getElementById('cpr-confirm').value;
      const errBox  = document.getElementById('cpr-error');
      errBox.style.display = 'none';

      if (!current || !newPwd || !confirm) {
        errBox.textContent = t('change_password.err_all_fields');
        errBox.style.display = 'block';
        return;
      }
      if (newPwd !== confirm) {
        errBox.textContent = t('change_password.err_mismatch');
        errBox.style.display = 'block';
        return;
      }

      const btn = document.getElementById('cpr-save');
      btn.disabled = true;
      btn.textContent = 'Guardando...';
      try {
        await Api.post('/api/auth/set-initial-password', {
          current_password: current,
          new_password: newPwd,
        });
        // Actualizar el objeto de usuario en localStorage para limpiar el flag
        const u = Auth.user();
        if (u) {
          u.must_change_password = false;
          localStorage.setItem('riskhub_user', JSON.stringify(u));
        }
        // Navegar al dashboard
        window.location.hash = '/dashboard';
      } catch (e) {
        errBox.textContent = e.message || t('change_password.err_change');
        errBox.style.display = 'block';
        btn.disabled = false;
        btn.textContent = t('change_password.btn_set_password');
      }
    };
  },
};
