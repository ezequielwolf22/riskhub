/* Vista Usuarios - admin-only. */
const ViewUsers = {
  _sortCol: 'created_at', _sortAsc: false,
  _orgs: [],      // cache para superadmin
  _myOrg: null,   // org del admin actual (no-superadmin)

  async render(main) {
    if (!Auth.isAdmin()) {
      main.innerHTML = UI.sectionHeader(t('common.error'), t('common.not_available'));
      main.innerHTML += UI.notice(t('common.not_available') + ' — ' + t('auth.role.admin'), 'warn');
      return;
    }

    const isSuperAdmin = Auth.isSuperAdmin();

    if (isSuperAdmin) {
      main.innerHTML = `
        <div class="page-header">
          <div>
            <h1 class="page-title">${t('users.title')}</h1>
            <p class="page-subtitle">${t('users.subtitle')}</p>
          </div>
        </div>
        <div id="u-orgs-list"></div>
        <div id="u-sysinfo"></div>
      `;
      await ViewUsers._reloadSuperAdmin();
    } else {
      main.innerHTML = `
        <div class="page-header">
          <div>
            <h1 class="page-title">${t('users.title')}</h1>
            <p class="page-subtitle" id="u-org-subtitle">${t('common.loading')}</p>
          </div>
          <div class="page-actions">
            <button class="btn btn-primary" id="btn-new">+ ${t('users.new')}</button>
          </div>
        </div>
        <div id="u-list"></div>
        <div id="u-sysinfo"></div>
      `;
      document.getElementById('btn-new').onclick = () => ViewUsers._edit();
      const me = Auth.user();
      if (me && me.organization_id) {
        try {
          const org = await Api.get('/api/organizations/' + me.organization_id);
          ViewUsers._myOrg = org;
          const sub = document.getElementById('u-org-subtitle');
          if (sub) sub.textContent = t('users.subtitle') + ' — ' + (org.name || t('users.organization'));
        } catch (_) {
          const sub = document.getElementById('u-org-subtitle');
          if (sub) sub.textContent = t('users.subtitle');
        }
      } else {
        const sub = document.getElementById('u-org-subtitle');
        if (sub) sub.textContent = t('users.subtitle');
      }
      ViewUsers._reload();
    }
    ViewUsers._loadSysInfo();
  },

  // Superadmin: carga orgs + usuarios y los agrupa
  async _reloadSuperAdmin() {
    const container = document.getElementById('u-orgs-list');
    if (!container) return;
    container.innerHTML = `<div class="notice">${t('common.loading')}</div>`;
    try {
      const [orgs, users] = await Promise.all([
        Api.get('/api/organizations/'),
        Api.users.list(),
      ]);
      ViewUsers._orgs = orgs;

      const usersByOrg = {};
      const noOrgUsers = [];
      users.forEach(u => {
        if (u.organization_id) {
          if (!usersByOrg[u.organization_id]) usersByOrg[u.organization_id] = [];
          usersByOrg[u.organization_id].push(u);
        } else {
          noOrgUsers.push(u);
        }
      });

      if (!orgs.length) {
        container.innerHTML = `<p style="color:var(--text-muted);">${t('common.no_results')}</p>`;
        return;
      }

      let html = orgs.map(org => ViewUsers._renderOrgSection(org, usersByOrg[org.id] || [])).join('');
      if (noOrgUsers.length) {
        html += ViewUsers._renderOrgSection({ id: null, name: t('common.not_assigned') }, noOrgUsers);
      }
      container.innerHTML = html;

      container.querySelectorAll('[data-new-user-org]').forEach(btn => {
        const orgId = btn.dataset.newUserOrg ? parseInt(btn.dataset.newUserOrg) : null;
        btn.onclick = (e) => { e.stopPropagation(); ViewUsers._edit(null, orgId); };
      });
      container.querySelectorAll('[data-edit-user]').forEach(btn => {
        btn.onclick = () => ViewUsers._edit(parseInt(btn.dataset.editUser));
      });
      container.querySelectorAll('[data-mfa-disable-su]').forEach(btn => {
        btn.onclick = () => ViewUsers._disableMfa(parseInt(btn.dataset.mfaDisableSu));
      });
      container.querySelectorAll('.org-section-header').forEach(hdr => {
        hdr.onclick = () => {
          const body = hdr.closest('.org-section').querySelector('.org-section-body');
          const isOpen = body.style.display !== 'none';
          body.style.display = isOpen ? 'none' : '';
          const icon = hdr.querySelector('.org-toggle-icon');
          if (icon) icon.textContent = isOpen ? '▶' : '▼';
        };
      });
    } catch (e) {
      container.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _renderOrgSection(org, users) {
    const count = users.length;
    return `
      <div class="card org-section" style="margin-bottom:16px;padding:0;overflow:hidden;">
        <div class="org-section-header" style="display:flex;align-items:center;justify-content:space-between;padding:14px 20px;cursor:pointer;background:var(--bg-2);border-bottom:1px solid var(--border);">
          <div style="display:flex;align-items:center;gap:12px;">
            <span class="org-toggle-icon" style="font-size:11px;color:var(--text-muted);min-width:10px;">▼</span>
            <strong style="font-size:15px;">${UI.esc(org.name || t('common.not_assigned'))}</strong>
            <span style="background:var(--brand-purple-4);color:var(--brand-purple);padding:2px 10px;border-radius:10px;font-size:11px;font-weight:600;">${count} usuario${count !== 1 ? 's' : ''}</span>
          </div>
          ${org.id ? `<button class="btn btn-primary" data-new-user-org="${org.id}" style="font-size:12px;padding:5px 14px;">+ ${t('users.new')}</button>` : ''}
        </div>
        <div class="org-section-body" style="padding:${count ? '0' : '16px 20px'};">
          ${count === 0
            ? `<p style="color:var(--text-muted);font-size:13px;margin:0;">${t('common.no_results')}</p>`
            : ViewUsers._renderUsersTableSuperAdmin(users)
          }
        </div>
      </div>
    `;
  },

  _renderUsersTableSuperAdmin(users) {
    return `<div class="table-wrap" style="margin:0;"><table class="data">
      <thead><tr>
        <th>${t('users.email')}</th><th>${t('users.full_name')}</th><th>${t('users.role')}</th>
        <th>${t('common.status')}</th><th>${t('users.last_login')}</th><th>MFA</th><th></th>
      </tr></thead>
      <tbody>
        ${users.map(u => {
          const mfaBadge = u.mfa_enabled
            ? '<span class="badge badge-low" title="MFA activo">MFA</span>'
            : (u.must_change_password
                ? '<span class="badge" style="background:var(--brand-orange-4,#fff3e0);color:var(--brand-orange);" title="Primer login pendiente">OTP</span>'
                : '<span style="color:var(--text-subtle);font-size:12px;">-</span>');
          return `<tr>
            <td><strong>${UI.esc(u.email)}</strong></td>
            <td>${UI.esc(u.full_name)}</td>
            <td><span class="badge" style="background:var(--brand-purple-4);color:var(--brand-purple);">${UI.esc(u.role)}</span></td>
            <td>${u.is_active ? `<span class="badge badge-low">${t('users.active')}</span>` : `<span class="badge badge-high">${t('common.inactive')}</span>`}</td>
            <td style="font-size:12px;">${u.last_login_at ? new Date(u.last_login_at).toLocaleString() : '-'}</td>
            <td>${mfaBadge}</td>
            <td style="white-space:nowrap;">
              <button class="btn btn-ghost" data-edit-user="${u.id}">${t('common.edit')}</button>
              ${u.mfa_enabled ? `<button class="btn btn-ghost" data-mfa-disable-su="${u.id}" style="margin-left:4px;">MFA off</button>` : ''}
            </td>
          </tr>`;
        }).join('')}
      </tbody>
    </table></div>`;
  },

  // Admin (no-superadmin): tabla simple de su propia org
  async _reload() {
    const list = document.getElementById('u-list');
    if (!list) return;
    list.innerHTML = `<div class="notice">${t('common.loading')}</div>`;
    try {
      let data = await Api.users.list();
      const _sv = u => {
        const k = ViewUsers._sortCol;
        if (k === 'email') return (u.email || '').toLowerCase();
        if (k === 'full_name') return (u.full_name || '').toLowerCase();
        if (k === 'role') return u.role || '';
        if (k === 'last_login_at') return u.last_login_at || 'zzz';
        if (k === 'risk_count') return u.risk_count || 0;
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
          ${_th('email',t('users.email'))}${_th('full_name',t('users.full_name'))}${_th('role',t('users.role'))}
          <th>${t('common.status')}</th>${_th('last_login_at',t('users.last_login'))}
          ${_th('risk_count',t('risks.title'))}<th>MFA</th><th></th>
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
              <td>${u.is_active ? `<span class="badge badge-low">${t('users.active')}</span>` : `<span class="badge badge-high">${t('common.inactive')}</span>`}</td>
              <td style="font-size:12px;">${u.last_login_at ? new Date(u.last_login_at).toLocaleString() : '-'}</td>
              <td style="text-align:center;font-weight:700;font-family:var(--font-mono);font-size:13px;">
                ${rc > 0
                  ? `<a href="#/risks?owner=${u.id}" style="color:${rcColor};text-decoration:none;" title="Ver riesgos">${rc}</a>`
                  : `<span style="color:${rcColor};">0</span>`}
              </td>
              <td>${mfaBadge}</td>
              <td style="white-space:nowrap;">
                <button class="btn btn-ghost" data-edit="${u.id}">${t('common.edit')}</button>
                ${u.mfa_enabled
                  ? `<button class="btn btn-ghost" data-mfa-disable="${u.id}" style="margin-left:4px;">MFA off</button>`
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
    if (!await UI.confirm(t('users.disable_mfa_confirm'))) return;
    try {
      await Api.post('/api/auth/mfa/disable-admin', { user_id: userId });
      UI.toast('MFA desactivado', 'success');
      Auth.isSuperAdmin() ? ViewUsers._reloadSuperAdmin() : ViewUsers._reload();
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  },

  // defaultOrgId: preselecciona la org cuando superadmin crea desde una seccion especifica
  async _edit(id, defaultOrgId) {
    const isSuperAdmin = Auth.isSuperAdmin();
    if (isSuperAdmin && !ViewUsers._orgs.length) {
      try { ViewUsers._orgs = await Api.get('/api/organizations/'); }
      catch (_) { ViewUsers._orgs = []; }
    }

    let u = { email: '', full_name: '', role: 'viewer', is_active: true, password: '', organization_id: defaultOrgId || null };
    if (id) {
      try {
        const all = await Api.users.list();
        u = all.find(x => x.id === id) || u;
      } catch (_) {}
    }

    const roleOptions = [
      { value: 'viewer',  label: `${t('auth.role.viewer')}` },
      { value: 'analyst', label: `${t('auth.role.analyst')}` },
      { value: 'admin',   label: `${t('auth.role.admin')}` },
    ];
    if (isSuperAdmin) roleOptions.push({ value: 'superadmin', label: `${t('auth.role.superadmin')}` });
    const roleSelect = roleOptions.map(r =>
      `<option value="${r.value}" ${u.role === r.value ? 'selected' : ''}>${r.label}</option>`
    ).join('');

    let orgField = '';
    if (isSuperAdmin && !id) {
      const orgOptions = ViewUsers._orgs.map(o =>
        `<option value="${o.id}" ${defaultOrgId === o.id ? 'selected' : ''}>${UI.esc(o.name)}</option>`
      ).join('');
      orgField = `
        <div class="span2">
          <label>${t('users.organization')} *</label>
          <select id="f-org" class="input">
            <option value="">-- ${t('users.organization')} --</option>
            ${orgOptions}
          </select>
        </div>`;
    } else if (isSuperAdmin && id) {
      const orgOptions = ViewUsers._orgs.map(o =>
        `<option value="${o.id}" ${u.organization_id === o.id ? 'selected' : ''}>${UI.esc(o.name)}</option>`
      ).join('');
      orgField = `
        <div class="span2">
          <label>${t('users.organization')}</label>
          <select id="f-org" class="input">
            <option value="">${t('common.not_assigned')}</option>
            ${orgOptions}
          </select>
        </div>`;
    } else {
      // Admin no-superadmin: org no editable, siempre la suya
      const orgName = ViewUsers._myOrg
        ? ViewUsers._myOrg.name
        : (Auth.user()?.organization_id ? `Org #${Auth.user().organization_id}` : t('users.organization'));
      const orgDomain = ViewUsers._myOrg && ViewUsers._myOrg.domain
        ? ` <span style="font-size:11px;color:var(--text-muted);">(@${UI.esc(ViewUsers._myOrg.domain)})</span>` : '';
      orgField = `
        <div class="span2">
          <label>${t('users.organization')}</label>
          <div class="input" style="background:var(--bg-2);color:var(--text-muted);cursor:default;">${UI.esc(orgName)}${orgDomain}</div>
        </div>`;
    }

    const passNote = id ? '(dejar vacio para no cambiar)' : '(dejar vacio para generar automaticamente)';
    const passHint = id ? '' : `
      <p style="font-size:11px;color:var(--text-muted);margin:4px 0 0;">
        Si dejas el campo vacio, se generara una contrasena temporal segura.
        El usuario debera cambiarla en el primer acceso.
      </p>`;
    const otpWarning = (id && u.must_change_password)
      ? `<div class="span2"><div class="notice warn" style="margin-bottom:0;">
           Este usuario tiene una contrasena temporal activa. Aun no ha realizado el primer login.
         </div></div>`
      : '';

    UI.modal(id ? `${t('users.edit')} — ${u.email}` : t('users.new'), `
      ${otpWarning}
      <div class="span2"><label>${t('users.email')} *</label>
        <input class="input" id="f-email" value="${UI.esc(u.email)}" ${id ? 'disabled' : ''}></div>
      <div class="span2"><label>${t('users.full_name')} *</label>
        <input class="input" id="f-name" value="${UI.esc(u.full_name)}"></div>
      <div><label>${t('users.role')} *</label>
        <select class="input" id="f-role">${roleSelect}</select>
      </div>
      <div><label>${t('common.status')}</label>
        <select class="input" id="f-active">
          <option value="true" ${u.is_active ? 'selected' : ''}>${t('users.active')}</option>
          <option value="false" ${!u.is_active ? 'selected' : ''}>${t('common.inactive')}</option>
        </select>
      </div>
      ${orgField}
      <div class="span2">
        <label>${t('auth.change_password')} ${passNote}</label>
        <input class="input" type="password" id="f-pass" autocomplete="new-password">
        ${passHint}
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                ${id ? `<button class="btn btn-danger" id="m-del">${t('common.delete')}</button>` : ''}
                <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`
    });

    document.getElementById('m-cancel').onclick = UI.closeModal;
    if (id) document.getElementById('m-del').onclick = async () => {
      if (!await UI.confirm(t('users.delete_confirm'))) return;
      try {
        await Api.users.del(id);
        UI.closeModal();
        UI.toast(t('common.delete') + ' — ' + t('common.success'), 'success');
        isSuperAdmin ? ViewUsers._reloadSuperAdmin() : ViewUsers._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
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
          UI.closeModal();
          UI.toast(t('common.success'), 'success');
          isSuperAdmin ? ViewUsers._reloadSuperAdmin() : ViewUsers._reload();
        } else {
          if (isSuperAdmin && orgEl && !orgEl.value) {
            UI.toast('Debes seleccionar una organizacion', 'error'); return;
          }
          const payload = {
            email: document.getElementById('f-email').value,
            full_name: document.getElementById('f-name').value,
            role: document.getElementById('f-role').value,
          };
          if (pass) payload.password = pass;
          // Solo superadmin envía organization_id (el backend ignora este campo para no-superadmin)
          if (isSuperAdmin && orgEl && orgEl.value) payload.organization_id = parseInt(orgEl.value);
          const created = await Api.users.create(payload);
          UI.closeModal();
          isSuperAdmin ? ViewUsers._reloadSuperAdmin() : ViewUsers._reload();
          if (created && created.otp_password) {
            const emailInfo = created.otp_email_sent
              ? 'La contrasena temporal ha sido enviada al email del usuario.'
              : 'No hay SMTP configurado. Comunica la contrasena manualmente.';
            UI.modal(`${t('users.new')} — OTP`, `
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
            UI.toast(t('common.success'), 'success');
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
            <div style="display:flex;gap:8px;">
              ${Auth.isAdmin() ? `<button class="btn btn-secondary" id="btn-cleanup-vulns">Limpiar vulnerabilidades en riesgos</button>` : ''}
              ${Auth.isAdmin() ? `<button class="btn btn-secondary" id="btn-cleanup-ctrls">Limpiar controles en riesgos</button>` : ''}
              ${Auth.isSuperAdmin() ? `<button class="btn btn-ghost" id="btn-backup">Descargar backup DB</button>` : ''}
            </div>
          </div>
          <div id="cleanup-result" style="display:none;margin-bottom:12px;"></div>
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
      const btnCleanup = document.getElementById('btn-cleanup-vulns');
      if (btnCleanup) {
        btnCleanup.onclick = async () => {
          if (!await UI.confirm(
            'Esto reemplazara automaticamente las vulnerabilidades de TODOS los riesgos ' +
            'con las que corresponden a su amenaza segun el catalogo ISO 27005.\n\n' +
            'Los controles existentes no se modifican. Continuar?'
          )) return;
          btnCleanup.disabled = true;
          btnCleanup.textContent = 'Procesando...';
          const resultBox = document.getElementById('cleanup-result');
          try {
            const r = await Api.admin.cleanupVulnerabilities();
            const fixedRows = r.details
              .filter(d => d.action === 'fixed')
              .map(d => `
                <tr>
                  <td style="font-family:monospace;font-size:12px;">${UI.esc(d.risk_code)}</td>
                  <td style="font-size:12px;">${UI.esc(d.threat_code)}</td>
                  <td style="font-size:12px;color:#DC2626;">${(d.removed||[]).join(', ')||'—'}</td>
                  <td style="font-size:12px;color:#059669;">${(d.added||[]).join(', ')||'—'}</td>
                </tr>`).join('');
            resultBox.style.display = 'block';
            resultBox.innerHTML = `
              <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:14px;">
                <div style="font-weight:600;margin-bottom:10px;">
                  Limpieza completada: <span style="color:#059669;">${r.fixed} corregidos</span>
                  de ${r.checked} riesgos revisados
                  ${r.already_correct ? `<span style="color:var(--text-muted);font-weight:400;font-size:12px;margin-left:8px;">(${r.already_correct} ya eran correctos)</span>` : ''}
                  ${r.no_catalog_match ? `<span style="color:var(--text-muted);font-weight:400;font-size:12px;margin-left:8px;">(${r.no_catalog_match} amenazas sin catalogo)</span>` : ''}
                </div>
                ${fixedRows ? `
                  <div style="overflow-x:auto;">
                    <table style="width:100%;border-collapse:collapse;font-size:12px;">
                      <thead><tr>
                        <th style="text-align:left;padding:4px 8px;color:var(--text-muted);">Riesgo</th>
                        <th style="text-align:left;padding:4px 8px;color:var(--text-muted);">Amenaza</th>
                        <th style="text-align:left;padding:4px 8px;color:#DC2626;">Eliminadas</th>
                        <th style="text-align:left;padding:4px 8px;color:#059669;">Anadidas</th>
                      </tr></thead>
                      <tbody>${fixedRows}</tbody>
                    </table>
                  </div>` : '<div style="color:var(--text-muted);font-size:13px;">Todos los riesgos ya tenian las vulnerabilidades correctas.</div>'}
              </div>`;
            UI.toast(`${r.fixed} riesgos corregidos`, r.fixed > 0 ? 'success' : 'info');
          } catch (e) {
            UI.toast('Error en limpieza: ' + e.message, 'error');
          } finally {
            btnCleanup.disabled = false;
            btnCleanup.textContent = 'Limpiar vulnerabilidades en riesgos';
          }
        };
      }

      const btnCleanupCtrls = document.getElementById('btn-cleanup-ctrls');
      if (btnCleanupCtrls) {
        btnCleanupCtrls.onclick = async () => {
          if (!await UI.confirm(
            'Esto reemplazara automaticamente los controles de TODOS los riesgos ' +
            'con los que corresponden a su amenaza y vulnerabilidades segun ISO 27002.\n\n' +
            'Se asignaran los 10 controles mas maduros y relevantes por riesgo. Continuar?'
          )) return;
          btnCleanupCtrls.disabled = true;
          btnCleanupCtrls.textContent = 'Procesando...';
          const resultBox = document.getElementById('cleanup-result');
          try {
            const r = await Api.admin.cleanupControls();
            const fixedRows = r.details
              .filter(d => d.action === 'fixed')
              .map(d => `
                <tr>
                  <td style="font-family:monospace;font-size:12px;">${UI.esc(d.risk_code)}</td>
                  <td style="font-size:12px;">${UI.esc(d.threat_code||'')}</td>
                  <td style="font-size:12px;">${(d.vuln_cats||[]).join(', ')||'—'}</td>
                  <td style="font-size:12px;color:#DC2626;">${(d.removed||[]).join(', ')||'—'}</td>
                  <td style="font-size:12px;color:#059669;">${(d.added||[]).join(', ')||'—'}</td>
                </tr>`).join('');
            resultBox.style.display = 'block';
            resultBox.innerHTML = `
              <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:14px;">
                <div style="font-weight:600;margin-bottom:10px;">
                  Limpieza de controles: <span style="color:#059669;">${r.fixed} corregidos</span>
                  de ${r.checked} riesgos revisados
                  ${r.already_ok ? `<span style="color:var(--text-muted);font-weight:400;font-size:12px;margin-left:8px;">(${r.already_ok} ya eran correctos)</span>` : ''}
                </div>
                ${fixedRows ? `
                  <div style="overflow-x:auto;">
                    <table style="width:100%;border-collapse:collapse;font-size:12px;">
                      <thead><tr>
                        <th style="text-align:left;padding:4px 8px;color:var(--text-muted);">Riesgo</th>
                        <th style="text-align:left;padding:4px 8px;color:var(--text-muted);">Amenaza</th>
                        <th style="text-align:left;padding:4px 8px;color:var(--text-muted);">Cats. Vuln</th>
                        <th style="text-align:left;padding:4px 8px;color:#DC2626;">Eliminados</th>
                        <th style="text-align:left;padding:4px 8px;color:#059669;">Anadidos</th>
                      </tr></thead>
                      <tbody>${fixedRows}</tbody>
                    </table>
                  </div>` : '<div style="color:var(--text-muted);font-size:13px;">Todos los riesgos ya tenian los controles correctos.</div>'}
              </div>`;
            UI.toast(`${r.fixed} riesgos con controles corregidos`, r.fixed > 0 ? 'success' : 'info');
          } catch (e) {
            UI.toast('Error en limpieza de controles: ' + e.message, 'error');
          } finally {
            btnCleanupCtrls.disabled = false;
            btnCleanupCtrls.textContent = 'Limpiar controles en riesgos';
          }
        };
      }

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
