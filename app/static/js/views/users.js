/* Vista Usuarios - admin-only. */
const ViewUsers = {
  _sortCol: 'created_at', _sortAsc: false,
  _orgs: [],   // cache de organizaciones para superadmin

  async render(main) {
    if (!Auth.isAdmin()) {
      main.innerHTML = UI.sectionHeader('Acceso restringido', 'Solo administradores');
      main.innerHTML += UI.notice('Esta seccion requiere rol de administrador.', 'warn');
      return;
    }
    main.innerHTML = UI.sectionHeader(
      'Usuarios',
      'Cuentas con acceso a RiskHub',
      '<button class="btn btn-primary" id="btn-new">+ Nuevo usuario</button>'
    ) + '<div id="u-list"></div><div id="u-sysinfo"></div>';

    // Pre-cargar orgs si es superadmin (necesario para la columna y el modal)
    if (Auth.isSuperAdmin()) {
      try {
        ViewUsers._orgs = await Api.get('/api/organizations/');
      } catch (_) { ViewUsers._orgs = []; }
    }

    document.getElementById('btn-new').onclick = () => ViewUsers._edit();
    ViewUsers._reload();
    ViewUsers._loadSysInfo();
  },

  _orgName(orgId) {
    if (!orgId) return '-';
    const o = ViewUsers._orgs.find(x => x.id === orgId);
    return o ? o.name : `Org #${orgId}`;
  },

  async _reload() {
    const list = document.getElementById('u-list');
    list.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      let data = await Api.users.list();
      const isSuperAdmin = Auth.isSuperAdmin();

      // Client-side sort
      const _sv = u => {
        const k = ViewUsers._sortCol;
        if (k === 'email') return (u.email || '').toLowerCase();
        if (k === 'full_name') return (u.full_name || '').toLowerCase();
        if (k === 'role') return u.role || '';
        if (k === 'last_login_at') return u.last_login_at || 'zzz';
        if (k === 'risk_count') return u.risk_count || 0;
        if (k === 'org') return ViewUsers._orgName(u.organization_id).toLowerCase();
        return u.created_at || '';
      };
      data.sort((a, b) => {
        const va = _sv(a), vb = _sv(b);
        const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
        return ViewUsers._sortAsc ? cmp : -cmp;
      });
      const _th = (col, label) => {
        const active = ViewUsers._sortCol === col;
        const arrow = active ? (ViewUsers._sortAsc ? ' ▲' : ' ▼') : '';
        return `<th style="cursor:pointer;user-select:none;white-space:nowrap;${active?'color:var(--brand-purple);':''}" data-sort="${col}">${label}${arrow}</th>`;
      };
      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          ${_th('email','Email')}${_th('full_name','Nombre')}${_th('role','Rol')}
          ${isSuperAdmin ? _th('org','Organizacion') : ''}
          <th>Estado</th>${_th('last_login_at','Ultimo acceso')}
          ${_th('risk_count','Riesgos')}<th>MFA</th><th></th>
        </tr></thead>
        <tbody>
          ${data.map(u => {
            const rc = u.risk_count || 0;
            const rcColor = rc === 0 ? 'var(--text-subtle)' : rc >= 5 ? 'var(--risk-high)' : 'var(--brand-purple)';
            const mfaBadge = u.mfa_enabled
              ? '<span class="badge badge-low" title="MFA activo">MFA</span>'
              : (u.must_change_password
                  ? '<span class="badge" style="background:var(--brand-orange-4,#fff3e0);color:var(--brand-orange);" title="Primer login pendiente">OTP</span>'
                  : '<span style="color:var(--text-subtle);font-size:12px;">-</span>');
            return `<tr>
              <td><strong>${UI.esc(u.email)}</strong></td>
              <td>${UI.esc(u.full_name)}</td>
              <td><span class="badge" style="background:var(--brand-purple-4);color:var(--brand-purple);">${UI.esc(u.role)}</span></td>
              ${isSuperAdmin ? `<td style="font-size:12px;">${UI.esc(ViewUsers._orgName(u.organization_id))}</td>` : ''}
              <td>${u.is_active ? '<span class="badge badge-low">Activo</span>' : '<span class="badge badge-high">Inactivo</span>'}</td>
              <td style="font-size:12px;">${u.last_login_at ? new Date(u.last_login_at).toLocaleString() : '-'}</td>
              <td style="text-align:center;font-weight:700;font-family:var(--font-mono);font-size:13px;">
                ${rc > 0
                  ? `<a href="#/risks?owner=${u.id}" style="color:${rcColor};text-decoration:none;" title="Ver riesgos de ${UI.esc(u.full_name)}">${rc}</a>`
                  : `<span style="color:${rcColor};">0</span>`}
              </td>
              <td>${mfaBadge}</td>
              <td style="white-space:nowrap;">
                <button class="btn btn-ghost" data-edit="${u.id}">Editar</button>
                ${u.mfa_enabled
                  ? `<button class="btn btn-ghost" data-mfa-disable="${u.id}" title="Desactivar MFA de este usuario" style="margin-left:4px;">MFA off</button>`
                  : ''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
      list.querySelectorAll('th[data-sort]').forEach(th => {
        th.onclick = () => {
          const col = th.dataset.sort;
          if (ViewUsers._sortCol === col) ViewUsers._sortAsc = !ViewUsers._sortAsc;
          else { ViewUsers._sortCol = col; ViewUsers._sortAsc = col !== 'risk_count'; }
          ViewUsers._reload();
        };
      });
      list.querySelectorAll('[data-edit]').forEach(b =>
        b.onclick = () => ViewUsers._edit(parseInt(b.dataset.edit)));
      list.querySelectorAll('[data-mfa-disable]').forEach(b =>
        b.onclick = () => ViewUsers._disableMfa(parseInt(b.dataset.mfaDisable)));
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  async _disableMfa(userId) {
    if (!await UI.confirm('Desactivar MFA para este usuario? El usuario debera volver a configurarlo.')) return;
    try {
      await Api.post('/api/auth/mfa/disable-admin', { user_id: userId });
      UI.toast('MFA desactivado', 'success');
      ViewUsers._reload();
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  },

  async _edit(id) {
    const isSuperAdmin = Auth.isSuperAdmin();
    let u = { email: '', full_name: '', role: 'viewer', is_active: true, password: '', organization_id: null };
    if (id) {
      const all = await Api.users.list();
      u = all.find(x => x.id === id) || u;
    }

    // Opciones de rol: solo superadmin puede ver/asignar el rol superadmin
    const roleOptions = [
      { value: 'viewer',     label: 'Viewer (solo lectura)' },
      { value: 'analyst',    label: 'Analyst (edicion)' },
      { value: 'admin',      label: 'Admin (todo)' },
    ];
    if (isSuperAdmin) {
      roleOptions.push({ value: 'superadmin', label: 'SuperAdmin (licencias)' });
    }
    const roleSelect = roleOptions.map(r =>
      `<option value="${r.value}" ${u.role === r.value ? 'selected' : ''}>${r.label}</option>`
    ).join('');

    // Campo organizacion — solo superadmin, solo al crear
    let orgField = '';
    if (isSuperAdmin && !id) {
      const orgOptions = ViewUsers._orgs.map(o =>
        `<option value="${o.id}">${UI.esc(o.name)}</option>`
      ).join('');
      orgField = `
        <div class="span2">
          <label>Organizacion *</label>
          <select id="f-org" class="input">
            <option value="">-- Seleccionar organizacion --</option>
            ${orgOptions}
          </select>
        </div>`;
    } else if (isSuperAdmin && id) {
      // Edicion: mostrar org actual y permitir cambiarla
      const orgOptions = ViewUsers._orgs.map(o =>
        `<option value="${o.id}" ${u.organization_id === o.id ? 'selected' : ''}>${UI.esc(o.name)}</option>`
      ).join('');
      orgField = `
        <div class="span2">
          <label>Organizacion</label>
          <select id="f-org" class="input">
            <option value="">Sin organizacion</option>
            ${orgOptions}
          </select>
        </div>`;
    }

    // Nota contrasena: al crear, si se deja vacio se genera automaticamente
    const passNote = id
      ? '(dejar vacio para no cambiar)'
      : '(dejar vacio para generar automaticamente y enviar por email si hay SMTP configurado)';
    const passHint = id ? '' : `
      <p style="font-size:11px;color:var(--text-muted);margin:4px 0 0;">
        Si dejas el campo vacio, se generara una contrasena temporal segura.
        El usuario debera cambiarla en su primer acceso.
      </p>`;

    // Aviso de OTP pendiente al editar
    const otpWarning = (id && u.must_change_password)
      ? `<div class="span2"><div class="notice warn" style="margin-bottom:0;">
           Este usuario tiene una contrasena temporal activa. Aun no ha realizado el primer login.
         </div></div>`
      : '';

    UI.modal(id ? `Editar usuario ${u.email}` : 'Nuevo usuario', `
      ${otpWarning}
      <div class="span2"><label>Email *</label>
        <input class="input" id="f-email" value="${UI.esc(u.email)}" ${id ? 'disabled' : ''}></div>
      <div class="span2"><label>Nombre completo *</label>
        <input class="input" id="f-name" value="${UI.esc(u.full_name)}"></div>
      <div><label>Rol *</label>
        <select class="input" id="f-role">${roleSelect}</select>
      </div>
      <div><label>Estado</label>
        <select class="input" id="f-active">
          <option value="true" ${u.is_active ? 'selected' : ''}>Activo</option>
          <option value="false" ${!u.is_active ? 'selected' : ''}>Inactivo</option>
        </select>
      </div>
      ${orgField}
      <div class="span2">
        <label>Contrasena ${passNote}</label>
        <input class="input" type="password" id="f-pass" autocomplete="new-password">
        ${passHint}
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                ${id ? '<button class="btn btn-danger" id="m-del">Eliminar</button>' : ''}
                <button class="btn btn-primary" id="m-save">Guardar</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    if (id) document.getElementById('m-del').onclick = async () => {
      if (!await UI.confirm('Eliminar este usuario?')) return;
      try { await Api.users.del(id); UI.closeModal(); UI.toast('Eliminado', 'success'); ViewUsers._reload(); }
      catch (e) { UI.toast(e.message, 'error'); }
    };
    document.getElementById('m-save').onclick = async () => {
      const pass = document.getElementById('f-pass').value;
      const orgEl = document.getElementById('f-org');
      try {
        if (id) {
          const body = {
            full_name: document.getElementById('f-name').value,
            role: document.getElementById('f-role').value,
            is_active: document.getElementById('f-active').value === 'true',
          };
          if (pass) body.password = pass;
          if (orgEl) {
            const orgVal = orgEl.value;
            body.organization_id = orgVal ? parseInt(orgVal) : null;
          }
          await Api.users.update(id, body);
          UI.closeModal(); UI.toast('Guardado', 'success'); ViewUsers._reload();
        } else {
          // Superadmin debe seleccionar org obligatoriamente
          if (isSuperAdmin && orgEl && !orgEl.value) {
            UI.toast('Debes seleccionar una organizacion', 'error'); return;
          }
          const payload = {
            email: document.getElementById('f-email').value,
            full_name: document.getElementById('f-name').value,
            role: document.getElementById('f-role').value,
          };
          // Solo incluir password si se ha escrito algo
          if (pass) payload.password = pass;
          if (orgEl && orgEl.value) payload.organization_id = parseInt(orgEl.value);
          const created = await Api.users.create(payload);
          UI.closeModal();
          ViewUsers._reload();
          // Si el backend genero una OTP, mostrarla al admin
          if (created && created.otp_password) {
            const emailInfo = created.otp_email_sent
              ? 'La contrasena temporal ha sido enviada al email del usuario.'
              : 'No hay SMTP configurado. Comunica la contrasena manualmente.';
            UI.modal('Usuario creado - Contrasena temporal', `
              <div class="span2">
                <p style="margin-bottom:12px;">
                  El usuario <strong>${UI.esc(created.email)}</strong> ha sido creado con una contrasena temporal.
                  Debera cambiarla en el primer acceso.
                </p>
                <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:12px;font-family:var(--font-mono);font-size:15px;letter-spacing:0.05em;word-break:break-all;text-align:center;margin-bottom:12px;">
                  ${UI.esc(created.otp_password)}
                </div>
                <p style="font-size:12px;color:var(--text-muted);">${emailInfo}</p>
              </div>
            `, {
              actions: '<button class="btn btn-primary" id="m-otp-ok">Entendido</button>'
            });
            document.getElementById('m-otp-ok').onclick = UI.closeModal;
          } else {
            UI.toast('Usuario creado', 'success');
          }
        }
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  async _loadSysInfo() {
    const panel = document.getElementById('u-sysinfo');
    if (!panel) return;
    try {
      const s = await Api.admin.systemInfo();
      const dbSize = s.db_size_bytes != null
        ? (s.db_size_bytes < 1024 * 1024
            ? (s.db_size_bytes / 1024).toFixed(1) + ' KB'
            : (s.db_size_bytes / 1024 / 1024).toFixed(2) + ' MB')
        : null;
      panel.innerHTML = `
        <div class="card" style="margin-top:24px;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
            <h3 style="margin:0;">Informacion del sistema</h3>
            ${Auth.isSuperAdmin() ? `<button class="btn btn-ghost" id="btn-backup" title="Descargar copia de seguridad de la base de datos">
              Descargar backup DB
            </button>` : ''}
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;">
            ${ViewUsers._infoChip('Version', s.version)}
            ${ViewUsers._infoChip('Entorno', s.env)}
            ${ViewUsers._infoChip('Motor BD', s.db_engine.toUpperCase())}
            ${dbSize ? ViewUsers._infoChip('Tamano BD', dbSize) : ''}
            ${ViewUsers._infoChip('Usuarios', s.total_users)}
            ${ViewUsers._infoChip('Activos', s.total_assets)}
            ${ViewUsers._infoChip('Riesgos', s.total_risks)}
            ${ViewUsers._infoChip('Controles', s.total_controls)}
            ${s.next_alert_check ? ViewUsers._infoChip('Prox. alerta', new Date(s.next_alert_check).toLocaleTimeString()) : ''}
          </div>
        </div>`;
      const btnBackup = document.getElementById('btn-backup');
      if (btnBackup) {
        btnBackup.onclick = async () => {
          btnBackup.disabled = true; btnBackup.textContent = 'Descargando...';
          try {
            await Api.admin.backupDb();
            UI.toast('Backup descargado correctamente', 'success');
          } catch (e) {
            UI.toast('Error al descargar backup: ' + e.message, 'error');
          } finally {
            btnBackup.disabled = false; btnBackup.textContent = 'Descargar backup DB';
          }
        };
      }
    } catch (e) {
      panel.innerHTML = `<div class="notice" style="margin-top:16px;">No se pudo cargar la informacion del sistema: ${UI.esc(e.message)}</div>`;
    }
  },

  _infoChip(label, value) {
    return `<div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:10px 14px;">
      <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">${UI.esc(String(label))}</div>
      <div style="font-weight:600;font-size:15px;">${UI.esc(String(value))}</div>
    </div>`;
  },
};
