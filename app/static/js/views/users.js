/* Vista Usuarios - admin-only. */
const ViewUsers = {
  _sortCol: 'created_at', _sortAsc: false,

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
    document.getElementById('btn-new').onclick = () => ViewUsers._edit();
    ViewUsers._reload();
    ViewUsers._loadSysInfo();
  },

  async _reload() {
    const list = document.getElementById('u-list');
    list.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      let data = await Api.users.list();
      // Client-side sort
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
          ${_th('email','Email')}${_th('full_name','Nombre')}${_th('role','Rol')}
          <th>Estado</th>${_th('last_login_at','Ultimo acceso')}
          ${_th('risk_count','Riesgos')}<th></th>
        </tr></thead>
        <tbody>
          ${data.map(u => {
            const rc = u.risk_count || 0;
            const rcColor = rc === 0 ? 'var(--text-subtle)' : rc >= 5 ? 'var(--risk-high)' : 'var(--brand-purple)';
            return `<tr>
              <td><strong>${UI.esc(u.email)}</strong></td>
              <td>${UI.esc(u.full_name)}</td>
              <td><span class="badge" style="background:var(--brand-purple-4);color:var(--brand-purple);">${u.role}</span></td>
              <td>${u.is_active ? '<span class="badge badge-low">Activo</span>' : '<span class="badge badge-high">Inactivo</span>'}</td>
              <td style="font-size:12px;">${u.last_login_at ? new Date(u.last_login_at).toLocaleString() : '-'}</td>
              <td style="text-align:center;font-weight:700;font-family:var(--font-mono);font-size:13px;">
                ${rc > 0
                  ? `<a href="#/risks?owner=${u.id}" style="color:${rcColor};text-decoration:none;" title="Ver riesgos de ${UI.esc(u.full_name)}">${rc}</a>`
                  : `<span style="color:${rcColor};">0</span>`}
              </td>
              <td><button class="btn btn-ghost" data-edit="${u.id}">Editar</button></td>
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
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  async _edit(id) {
    let u = { email: '', full_name: '', role: 'viewer', is_active: true, password: '' };
    if (id) {
      const all = await Api.users.list();
      u = all.find(x => x.id === id) || u;
    }
    UI.modal(id ? `Editar usuario ${u.email}` : 'Nuevo usuario', `
      <div class="span2"><label>Email *</label>
        <input id="f-email" value="${UI.esc(u.email)}" ${id?'disabled':''}></div>
      <div class="span2"><label>Nombre completo *</label>
        <input id="f-name" value="${UI.esc(u.full_name)}"></div>
      <div><label>Rol *</label>
        <select id="f-role">
          <option value="viewer" ${u.role==='viewer'?'selected':''}>Viewer (solo lectura)</option>
          <option value="analyst" ${u.role==='analyst'?'selected':''}>Analyst (edicion)</option>
          <option value="admin" ${u.role==='admin'?'selected':''}>Admin (todo)</option>
          <option value="superadmin" ${u.role==='superadmin'?'selected':''}>SuperAdmin (licencias)</option>
        </select>
      </div>
      <div><label>Estado</label>
        <select id="f-active">
          <option value="true" ${u.is_active?'selected':''}>Activo</option>
          <option value="false" ${!u.is_active?'selected':''}>Inactivo</option>
        </select>
      </div>
      <div class="span2"><label>Contrasena ${id?'(dejar vacio para no cambiar)':'(mínimo 8 caracteres)'}</label>
        <input type="password" id="f-pass" autocomplete="new-password"></div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                ${id ? '<button class="btn btn-danger" id="m-del">Eliminar</button>' : ''}
                <button class="btn btn-primary" id="m-save">Guardar</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    if (id) document.getElementById('m-del').onclick = async () => {
      if (!await UI.confirm('Eliminar este usuario?')) return;
      try { await Api.users.del(id); UI.closeModal(); UI.toast('Eliminado','success'); ViewUsers._reload(); }
      catch (e) { UI.toast(e.message, 'error'); }
    };
    document.getElementById('m-save').onclick = async () => {
      const pass = document.getElementById('f-pass').value;
      try {
        if (id) {
          const body = {
            full_name: document.getElementById('f-name').value,
            role: document.getElementById('f-role').value,
            is_active: document.getElementById('f-active').value === 'true',
          };
          if (pass) body.password = pass;
          await Api.users.update(id, body);
        } else {
          if (!pass || pass.length < 8) { UI.toast('Contrasena debe tener 8+ caracteres', 'error'); return; }
          await Api.users.create({
            email: document.getElementById('f-email').value,
            full_name: document.getElementById('f-name').value,
            role: document.getElementById('f-role').value,
            password: pass,
          });
        }
        UI.closeModal(); UI.toast('Guardado','success'); ViewUsers._reload();
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
        : 'N/A';
      panel.innerHTML = `
        <div class="card" style="margin-top:24px;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
            <h3 style="margin:0;">Informacion del sistema</h3>
            <button class="btn btn-ghost" id="btn-backup" title="Descargar copia de seguridad de la base de datos">
              Descargar backup DB
            </button>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;">
            ${ViewUsers._infoChip('Version', s.version)}
            ${ViewUsers._infoChip('Entorno', s.env)}
            ${ViewUsers._infoChip('Motor BD', s.db_engine.toUpperCase())}
            ${ViewUsers._infoChip('Tamano BD', dbSize)}
            ${ViewUsers._infoChip('Usuarios', s.total_users)}
            ${ViewUsers._infoChip('Activos', s.total_assets)}
            ${ViewUsers._infoChip('Riesgos', s.total_risks)}
            ${ViewUsers._infoChip('Controles', s.total_controls)}
            ${s.next_alert_check ? ViewUsers._infoChip('Prox. alerta', new Date(s.next_alert_check).toLocaleTimeString()) : ''}
          </div>
        </div>`;
      document.getElementById('btn-backup').onclick = async () => {
        const btn = document.getElementById('btn-backup');
        btn.disabled = true; btn.textContent = 'Descargando...';
        try {
          await Api.admin.backupDb();
          UI.toast('Backup descargado correctamente', 'success');
        } catch (e) {
          UI.toast('Error al descargar backup: ' + e.message, 'error');
        } finally {
          btn.disabled = false; btn.textContent = 'Descargar backup DB';
        }
      };
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
