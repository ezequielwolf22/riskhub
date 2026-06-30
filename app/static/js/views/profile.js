/* Vista Mi Perfil — accesible para cualquier usuario autenticado. */
const ViewProfile = {
  _me: null,
  _tab: 'cuenta',

  async render(main) {
    main.innerHTML = `<div style="max-width:720px;margin:32px auto;padding:0 16px;">
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:24px;">
        <div style="width:56px;height:56px;border-radius:50%;background:var(--brand-purple);color:#fff;display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:700;flex-shrink:0;" id="profile-avatar">?</div>
        <div>
          <h1 style="font-size:20px;font-weight:700;margin:0;" id="profile-title">Mi perfil</h1>
          <p style="font-size:13px;color:var(--text-muted);margin:2px 0 0;" id="profile-subtitle"></p>
        </div>
      </div>
      <div style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:24px;">
        ${['cuenta','seguridad','preferencias'].map(tab => `
          <button id="tab-${tab}" onclick="ViewProfile._setTab('${tab}')"
            style="padding:10px 20px;font-size:13px;font-weight:600;border:none;background:none;cursor:pointer;
                   border-bottom:2px solid transparent;margin-bottom:-2px;color:var(--text-secondary);">
            ${{ cuenta: 'Cuenta', seguridad: 'Seguridad', preferencias: 'Preferencias' }[tab]}
          </button>
        `).join('')}
      </div>
      <div id="profile-tab-content"><p class="muted">Cargando...</p></div>
      <div style="margin-top:32px;padding-top:16px;border-top:1px solid var(--border);">
        <button class="btn btn-ghost" onclick="Auth.logout()" style="color:var(--text-muted);font-size:13px;">
          Cerrar sesion
        </button>
      </div>
    </div>`;

    try {
      ViewProfile._me = await Api.me();
    } catch (_) {
      ViewProfile._me = Auth.user() || {};
    }
    ViewProfile._renderHeader();
    ViewProfile._setTab(ViewProfile._tab);
  },

  _renderHeader() {
    const me = ViewProfile._me || {};
    const initials = (me.full_name || me.email || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
    const av = document.getElementById('profile-avatar');
    if (av) av.textContent = initials;
    const ti = document.getElementById('profile-title');
    if (ti) ti.textContent = me.full_name || me.email || 'Mi perfil';
    const su = document.getElementById('profile-subtitle');
    if (su) su.textContent = `${me.email || ''} · ${me.role || ''}${me.organization_id ? ' · Org #' + me.organization_id : ''}`;
  },

  _setTab(tab) {
    ViewProfile._tab = tab;
    ['cuenta', 'seguridad', 'preferencias'].forEach(t => {
      const btn = document.getElementById('tab-' + t);
      if (!btn) return;
      btn.style.borderBottomColor = t === tab ? 'var(--brand-purple)' : 'transparent';
      btn.style.color = t === tab ? 'var(--brand-purple)' : 'var(--text-secondary)';
    });
    const content = document.getElementById('profile-tab-content');
    if (!content) return;
    if (tab === 'cuenta') ViewProfile._renderCuenta(content);
    else if (tab === 'seguridad') ViewProfile._renderSeguridad(content);
    else if (tab === 'preferencias') ViewProfile._renderPreferencias(content);
  },

  _renderCuenta(el) {
    const me = ViewProfile._me || {};
    const roleLabels = { admin: 'Administrador', analyst: 'Analista', viewer: 'Visor', superadmin: 'Superadmin' };
    el.innerHTML = `
      <div style="display:grid;gap:16px;">
        <div class="card" style="padding:20px;">
          <h3 style="font-size:13px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin:0 0 16px;">Informacion de cuenta</h3>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div>
              <label style="font-size:11px;color:var(--text-muted);font-weight:600;text-transform:uppercase;display:block;margin-bottom:4px;">Nombre completo</label>
              <div style="font-size:14px;">${UI.esc(me.full_name || '-')}</div>
            </div>
            <div>
              <label style="font-size:11px;color:var(--text-muted);font-weight:600;text-transform:uppercase;display:block;margin-bottom:4px;">Email</label>
              <div style="font-size:14px;">${UI.esc(me.email || '-')}</div>
            </div>
            <div>
              <label style="font-size:11px;color:var(--text-muted);font-weight:600;text-transform:uppercase;display:block;margin-bottom:4px;">Rol</label>
              <div><span class="badge badge-muted">${roleLabels[me.role] || me.role || '-'}</span></div>
            </div>
            <div>
              <label style="font-size:11px;color:var(--text-muted);font-weight:600;text-transform:uppercase;display:block;margin-bottom:4px;">Ultimo acceso</label>
              <div style="font-size:14px;color:var(--text-muted);">${me.last_login_at ? new Date(me.last_login_at).toLocaleString('es-ES') : 'Sin datos'}</div>
            </div>
          </div>
        </div>

        <div class="card" style="padding:20px;">
          <h3 style="font-size:13px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin:0 0 12px;">Permisos del rol</h3>
          ${ViewProfile._rolePermissions(me.role)}
        </div>
      </div>`;
  },

  _rolePermissions(role) {
    const perms = {
      viewer: [
        { label: 'Ver activos, riesgos y controles', ok: true },
        { label: 'Ver informes y cumplimiento', ok: true },
        { label: 'Crear o editar registros', ok: false },
        { label: 'Gestionar usuarios', ok: false },
        { label: 'Configuracion de la organizacion', ok: false },
      ],
      analyst: [
        { label: 'Ver activos, riesgos y controles', ok: true },
        { label: 'Crear y editar riesgos, controles, incidentes', ok: true },
        { label: 'Ver informes y cumplimiento', ok: true },
        { label: 'Acceso al agente IA', ok: true },
        { label: 'Gestionar usuarios', ok: false },
        { label: 'Configuracion de la organizacion', ok: false },
      ],
      admin: [
        { label: 'Acceso completo a todos los modulos', ok: true },
        { label: 'Gestionar usuarios de la organizacion', ok: true },
        { label: 'Configuracion de la organizacion', ok: true },
        { label: 'Gestion de integraciones', ok: true },
        { label: 'Crear organizaciones adicionales', ok: false },
      ],
      superadmin: [
        { label: 'Acceso completo a todos los modulos', ok: true },
        { label: 'Gestionar todas las organizaciones', ok: true },
        { label: 'Gestion de licencias y planes', ok: true },
        { label: 'Configuracion global del sistema', ok: true },
      ],
    };
    const list = perms[role] || [{ label: 'Sin permisos definidos', ok: false }];
    return `<ul style="list-style:none;padding:0;margin:0;display:grid;gap:8px;">
      ${list.map(p => `
        <li style="display:flex;align-items:center;gap:8px;font-size:13px;">
          <span style="width:18px;height:18px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;flex-shrink:0;
            background:${p.ok ? 'var(--success-color,#22c55e)' : 'var(--border)'};
            color:${p.ok ? '#fff' : 'var(--text-muted)'};">
            ${p.ok ? '&#10003;' : '&#10005;'}
          </span>
          <span style="color:${p.ok ? 'var(--text-primary)' : 'var(--text-muted);'};">${p.label}</span>
        </li>
      `).join('')}
    </ul>`;
  },

  _renderSeguridad(el) {
    const me = ViewProfile._me || {};
    const mfaActive = me.mfa_enabled;
    el.innerHTML = `
      <div style="display:grid;gap:16px;">
        <div class="card" style="padding:20px;">
          <h3 style="font-size:13px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin:0 0 16px;">Contrasena</h3>
          <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;">Cambia tu contrasena de acceso. Debe tener al menos 8 caracteres.</p>
          <button class="btn btn-secondary" onclick="ViewProfile._showChangePassword()">Cambiar contrasena</button>
          <div id="change-password-form" style="display:none;margin-top:16px;display:grid;gap:10px;">
            <div>
              <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Contrasena actual *</label>
              <input class="input" type="password" id="p-cur" style="max-width:360px;">
            </div>
            <div>
              <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Nueva contrasena *</label>
              <input class="input" type="password" id="p-new" style="max-width:360px;">
            </div>
            <div>
              <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Repetir nueva contrasena *</label>
              <input class="input" type="password" id="p-new2" style="max-width:360px;">
            </div>
            <div style="display:flex;gap:8px;">
              <button class="btn btn-primary" onclick="ViewProfile._savePassword()">Guardar contrasena</button>
              <button class="btn btn-ghost" onclick="ViewProfile._hideChangePassword()">Cancelar</button>
            </div>
          </div>
        </div>

        <div class="card" style="padding:20px;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
            <div>
              <h3 style="font-size:13px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin:0 0 4px;">Autenticacion de dos factores (MFA)</h3>
              <p style="font-size:13px;color:var(--text-muted);margin:0;">
                ${mfaActive
                  ? '<span style="color:var(--success-color,#22c55e);font-weight:600;">&#10003; Activo</span> — Tu cuenta esta protegida con un autenticador.'
                  : 'No configurado. Activa MFA para mayor seguridad usando una app como Google Authenticator o Authy.'}
              </p>
              ${me.mfa_override === true ? '<p style="font-size:11px;color:var(--brand-orange);margin:4px 0 0;">Tu administrador ha requerido MFA para tu cuenta.</p>' : ''}
              ${me.mfa_override === false ? '<p style="font-size:11px;color:var(--text-muted);margin:4px 0 0;">Tu administrador te ha eximido del MFA.</p>' : ''}
            </div>
            <div style="flex-shrink:0;">
              ${mfaActive
                ? `<span style="font-size:12px;color:var(--text-muted);">Solo un administrador puede desactivar el MFA.</span>`
                : `<button class="btn btn-primary" onclick="ViewProfile._setupMfa()">Activar MFA</button>`}
            </div>
          </div>
        </div>
      </div>`;

    // Mostrar el form de contrasena si estaba visible
    if (ViewProfile._passwordFormVisible) {
      const form = document.getElementById('change-password-form');
      if (form) form.style.display = 'grid';
    }
  },

  _passwordFormVisible: false,

  _showChangePassword() {
    ViewProfile._passwordFormVisible = true;
    const form = document.getElementById('change-password-form');
    if (form) { form.style.display = 'grid'; form.style.removeProperty('display'); }
    // Re-render para que aparezca
    const content = document.getElementById('profile-tab-content');
    if (content) ViewProfile._renderSeguridad(content);
    ViewProfile._passwordFormVisible = true;
    const f2 = document.getElementById('change-password-form');
    if (f2) f2.style.display = 'grid';
  },

  _hideChangePassword() {
    ViewProfile._passwordFormVisible = false;
    const form = document.getElementById('change-password-form');
    if (form) form.style.display = 'none';
  },

  async _savePassword() {
    const cur = (document.getElementById('p-cur') || {}).value || '';
    const nw = (document.getElementById('p-new') || {}).value || '';
    const nw2 = (document.getElementById('p-new2') || {}).value || '';
    if (!cur || !nw) { UI.toast('Completa todos los campos', 'error'); return; }
    if (nw !== nw2) { UI.toast('Las contrasenas no coinciden', 'error'); return; }
    if (nw.length < 8) { UI.toast('Minimo 8 caracteres', 'error'); return; }
    try {
      await Api.changePassword({ current_password: cur, new_password: nw });
      UI.toast('Contrasena cambiada correctamente', 'success');
      ViewProfile._passwordFormVisible = false;
      const content = document.getElementById('profile-tab-content');
      if (content) ViewProfile._renderSeguridad(content);
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  async _setupMfa() {
    // Paso 1: pedir contrasena actual para verificar identidad
    UI.modal('Activar MFA — Verificar identidad', `
      <div class="span2">
        <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;">Introduce tu contrasena actual para continuar.</p>
        <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Contrasena actual *</label>
        <input class="input" type="password" id="mfa-step1-pass" autocomplete="current-password">
      </div>
    `, {
      actions: `<button class="btn" onclick="UI.closeModal()">Cancelar</button>
                <button class="btn btn-primary" id="mfa-step1-btn">Continuar</button>`
    });
    document.getElementById('mfa-step1-btn').onclick = async () => {
      const pass = document.getElementById('mfa-step1-pass').value;
      if (!pass) { UI.toast('Introduce tu contrasena', 'error'); return; }
      try {
        const res = await Api.mfa.setup(pass);
        // res contiene secret y otpauth_url; generamos QR via API publica de Google Charts o mostramos el secreto manual
        const secret = res.secret || '';
        const otpauthUrl = res.otpauth_url || '';
        // Generar QR con qrcodejs si disponible, sino mostrar secreto manual
        const qrHtml = `<canvas id="mfa-qr-canvas" style="display:block;margin:0 auto 12px;"></canvas>`;
        UI.modal('Activar MFA — Escanear codigo', `
          <div class="span2" style="text-align:center;">
            <p style="font-size:13px;margin-bottom:12px;">Escanea con tu app de autenticacion (Google Authenticator, Authy, Microsoft Authenticator).</p>
            ${qrHtml}
            <p style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">O introduce el codigo manualmente en tu app:</p>
            <code style="font-size:13px;font-weight:700;letter-spacing:.1em;background:var(--bg-2);padding:6px 12px;border-radius:6px;display:inline-block;margin-bottom:16px;">${UI.esc(secret)}</code>
          </div>
          <div class="span2">
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Codigo de verificacion (6 digitos) *</label>
            <input class="input" type="text" id="mfa-verify-code" placeholder="123456" maxlength="6" inputmode="numeric" style="max-width:200px;">
          </div>
        `, {
          actions: `<button class="btn" onclick="UI.closeModal()">Cancelar</button>
                    <button class="btn btn-primary" id="mfa-verify-btn">Verificar y activar</button>`
        });
        // Generar QR con la libreria si esta cargada, sino usar data URL via canvas
        setTimeout(() => {
          const canvas = document.getElementById('mfa-qr-canvas');
          if (canvas && window.QRCode) {
            new QRCode(canvas, { text: otpauthUrl, width: 200, height: 200 });
          } else if (canvas) {
            // Mostrar el otpauth URL como texto alternativo si no hay libreria QR
            canvas.style.display = 'none';
            const p = document.createElement('p');
            p.style.cssText = 'font-size:10px;color:var(--text-muted);word-break:break-all;margin-bottom:12px;';
            p.textContent = 'URL para app: ' + otpauthUrl;
            canvas.parentNode.insertBefore(p, canvas);
          }
        }, 50);
        document.getElementById('mfa-verify-btn').onclick = async () => {
          const code = document.getElementById('mfa-verify-code').value.trim();
          if (!code || code.length !== 6) { UI.toast('Introduce el codigo de 6 digitos', 'error'); return; }
          try {
            await Api.mfa.verifySetup({ secret, code });
            UI.toast('MFA activado correctamente', 'success');
            UI.closeModal();
            ViewProfile._me = await Api.me();
            const content = document.getElementById('profile-tab-content');
            if (content) ViewProfile._renderSeguridad(content);
          } catch (e) { UI.toast(e.message || 'Codigo incorrecto', 'error'); }
        };
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  _renderPreferencias(el) {
    const prefs = ViewProfile._loadPrefs();
    el.innerHTML = `
      <div class="card" style="padding:20px;">
        <h3 style="font-size:13px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin:0 0 16px;">Preferencias de interfaz</h3>
        <div style="display:grid;gap:16px;">
          <div>
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:6px;">Idioma de la interfaz</label>
            <select class="input" id="pref-lang" style="max-width:240px;" onchange="ViewProfile._savePrefs()">
              <option value="es" ${prefs.lang === 'es' ? 'selected' : ''}>Espanol</option>
              <option value="en" ${prefs.lang === 'en' ? 'selected' : ''}>English</option>
            </select>
          </div>
          <div>
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:6px;">Densidad de tablas</label>
            <select class="input" id="pref-density" style="max-width:240px;" onchange="ViewProfile._savePrefs()">
              <option value="normal" ${prefs.density === 'normal' ? 'selected' : ''}>Normal</option>
              <option value="compact" ${prefs.density === 'compact' ? 'selected' : ''}>Compacta</option>
            </select>
          </div>
          <div>
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:6px;">Notificaciones en pantalla</label>
            <select class="input" id="pref-toasts" style="max-width:240px;" onchange="ViewProfile._savePrefs()">
              <option value="all" ${prefs.toasts === 'all' ? 'selected' : ''}>Todas</option>
              <option value="errors" ${prefs.toasts === 'errors' ? 'selected' : ''}>Solo errores</option>
            </select>
          </div>
        </div>
        <p style="font-size:11px;color:var(--text-muted);margin-top:12px;">Las preferencias se guardan en este navegador.</p>
      </div>`;
  },

  _loadPrefs() {
    try { return JSON.parse(localStorage.getItem('riskhub_prefs') || '{}'); } catch { return {}; }
  },

  _savePrefs() {
    const lang = (document.getElementById('pref-lang') || {}).value || 'es';
    const density = (document.getElementById('pref-density') || {}).value || 'normal';
    const toasts = (document.getElementById('pref-toasts') || {}).value || 'all';
    const prefs = { lang, density, toasts };
    localStorage.setItem('riskhub_prefs', JSON.stringify(prefs));
    // Aplicar idioma si existe el sistema i18n
    if (window.i18n && typeof window.i18n.setLang === 'function') window.i18n.setLang(lang);
    UI.toast('Preferencias guardadas', 'success');
  },
};
