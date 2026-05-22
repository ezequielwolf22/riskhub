/* Vista Usuarios - admin-only. */
const ViewUsers = {
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
    ) + '<div id="u-list"></div>';
    document.getElementById('btn-new').onclick = () => ViewUsers._edit();
    ViewUsers._reload();
  },

  async _reload() {
    const list = document.getElementById('u-list');
    list.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      const data = await Api.users.list();
      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr><th>Email</th><th>Nombre</th><th>Rol</th><th>Estado</th><th>Ultimo acceso</th><th></th></tr></thead>
        <tbody>
          ${data.map(u => `
            <tr>
              <td><strong>${UI.esc(u.email)}</strong></td>
              <td>${UI.esc(u.full_name)}</td>
              <td><span class="badge" style="background:var(--brand-purple-4);color:var(--brand-purple);">${u.role}</span></td>
              <td>${u.is_active ? '<span class="badge badge-low">Activo</span>' : '<span class="badge badge-high">Inactivo</span>'}</td>
              <td style="font-size:12px;">${u.last_login_at ? new Date(u.last_login_at).toLocaleString() : '-'}</td>
              <td><button class="btn btn-ghost" data-edit="${u.id}">Editar</button></td>
            </tr>`).join('')}
        </tbody>
      </table></div>`;
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
        </select>
      </div>
      <div><label>Estado</label>
        <select id="f-active">
          <option value="true" ${u.is_active?'selected':''}>Activo</option>
          <option value="false" ${!u.is_active?'selected':''}>Inactivo</option>
        </select>
      </div>
      <div class="span2"><label>Contrasena ${id?'(dejar vacio para no cambiar)':'(minimo 8 caracteres)'}</label>
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
};
