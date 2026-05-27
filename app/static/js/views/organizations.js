/* Vista de gestion de organizaciones (solo superadmin). */
const ViewOrganizations = (() => {

  let _orgs = [];
  let _selectedOrg = null;
  let _orgUsers = [];

  // ---- API helpers ----
  async function fetchOrgs() {
    const r = await Api.get('/api/organizations/');
    _orgs = Array.isArray(r) ? r : [];
    return _orgs;
  }

  async function fetchOrgUsers(orgId) {
    const r = await Api.get(`/api/organizations/${orgId}/users`);
    _orgUsers = Array.isArray(r) ? r : [];
    return _orgUsers;
  }

  // ---- Render ----
  async function render(container) {
    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Organizaciones</h1>
          <p class="page-subtitle">Gestion multi-tenant — Solo superadmin</p>
        </div>
        <div class="page-actions">
          <button class="btn btn-primary" id="btn-new-org">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Nueva organizacion
          </button>
        </div>
      </div>
      <div id="orgs-notice"></div>
      <div id="orgs-grid" class="card-grid"></div>
      <div id="org-detail-panel" style="display:none;"></div>
    `;

    document.getElementById('btn-new-org').onclick = () => openNewOrgModal();

    await loadOrgs(container);
  }

  async function loadOrgs(container) {
    const grid = document.getElementById('orgs-grid');
    if (!grid) return;
    grid.innerHTML = '<p class="muted">Cargando...</p>';
    try {
      await fetchOrgs();
      renderGrid(grid);
    } catch (e) {
      grid.innerHTML = `<p class="notice">${UI.esc(e.message)}</p>`;
    }
  }

  function renderGrid(grid) {
    if (!_orgs.length) {
      grid.innerHTML = '<p class="muted">No hay organizaciones registradas.</p>';
      return;
    }
    grid.innerHTML = _orgs.map(o => `
      <div class="card" style="cursor:pointer;" data-org-id="${o.id}">
        <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;">
          <strong>${UI.esc(o.name)}</strong>
          <span class="badge ${o.is_active ? 'badge-success' : 'badge-muted'}">${o.is_active ? 'Activa' : 'Inactiva'}</span>
        </div>
        <div class="card-body" style="font-size:13px;color:var(--text-secondary);">
          <div><b>Plan:</b> ${UI.esc(o.plan || 'starter')}</div>
          <div><b>Dominio:</b> ${UI.esc(o.domain || '-')}</div>
          <div><b>Usuarios:</b> ${o.user_count} / ${o.max_users}</div>
          <div><b>Tokens IA usados:</b> ${(o.token_usage || 0).toLocaleString()}</div>
          <div style="color:var(--text-muted);margin-top:4px;">${o.created_at ? 'Creada: ' + o.created_at.split('T')[0] : ''}</div>
        </div>
        <div class="card-footer" style="display:flex;gap:8px;">
          <button class="btn btn-sm btn-secondary" onclick="ViewOrganizations._openDetail(${o.id})">Gestionar</button>
          ${o.is_active
            ? `<button class="btn btn-sm btn-danger" onclick="ViewOrganizations._deactivate(${o.id})">Desactivar</button>`
            : `<button class="btn btn-sm btn-secondary" onclick="ViewOrganizations._activate(${o.id})">Activar</button>`
          }
        </div>
      </div>
    `).join('');
  }

  async function _openDetail(orgId) {
    const org = _orgs.find(o => o.id === orgId);
    if (!org) return;
    _selectedOrg = org;

    const panel = document.getElementById('org-detail-panel');
    panel.style.display = 'block';
    panel.innerHTML = '<p class="muted">Cargando usuarios...</p>';

    try {
      await fetchOrgUsers(orgId);
    } catch (_e) {
      _orgUsers = [];
    }

    panel.innerHTML = `
      <div class="card" style="margin-top:24px;">
        <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;">
          <strong>Detalle: ${UI.esc(org.name)}</strong>
          <button class="btn btn-sm btn-ghost" onclick="document.getElementById('org-detail-panel').style.display='none'">Cerrar</button>
        </div>
        <div class="card-body">
          <form id="edit-org-form" style="display:grid;grid-template-columns:1fr 1fr;gap:12px 24px;">
            <label>Nombre
              <input class="input" name="name" value="${UI.esc(org.name)}" required>
            </label>
            <label>Dominio de email
              <input class="input" name="domain" value="${UI.esc(org.domain || '')}" placeholder="empresa.com">
            </label>
            <label>Plan
              <select class="input" name="plan">
                ${['starter','professional','enterprise'].map(p =>
                  `<option value="${p}" ${org.plan === p ? 'selected' : ''}>${p}</option>`
                ).join('')}
              </select>
            </label>
            <label>Max. usuarios
              <input class="input" type="number" name="max_users" value="${org.max_users}" min="1">
            </label>
            <div style="grid-column:1/-1;display:flex;gap:12px;justify-content:flex-end;">
              <button type="submit" class="btn btn-primary">Guardar cambios</button>
            </div>
          </form>

          <hr style="margin:20px 0;">
          <h3 style="font-size:14px;font-weight:600;margin-bottom:12px;">Usuarios (${_orgUsers.length})</h3>
          ${_orgUsers.length ? `
            <table class="table">
              <thead><tr><th>Nombre</th><th>Email</th><th>Rol</th><th>Activo</th><th></th></tr></thead>
              <tbody>
                ${_orgUsers.map(u => `
                  <tr>
                    <td>${UI.esc(u.full_name || u.email)}</td>
                    <td>${UI.esc(u.email)}</td>
                    <td>${UI.esc(u.role)}</td>
                    <td>${u.is_active ? 'Si' : 'No'}</td>
                    <td>
                      <button class="btn btn-xs btn-ghost" onclick="ViewOrganizations._moveUser(${u.id})">Mover</button>
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          ` : '<p class="muted">Sin usuarios.</p>'}
        </div>
      </div>
    `;

    document.getElementById('edit-org-form').onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const payload = {
        name: fd.get('name'),
        domain: fd.get('domain') || null,
        plan: fd.get('plan'),
        max_users: parseInt(fd.get('max_users')),
      };
      try {
        await Api.patch(`/api/organizations/${orgId}`, payload);
        UI.toast('Organizacion actualizada', 'success');
        await fetchOrgs();
        renderGrid(document.getElementById('orgs-grid'));
        _openDetail(orgId);
      } catch (err) {
        UI.toast(err.message, 'error');
      }
    };
  }

  async function _deactivate(orgId) {
    if (!confirm('Desactivar esta organizacion. Sus usuarios no podran iniciar sesion. Continuar?')) return;
    try {
      await Api.del(`/api/organizations/${orgId}`);
      UI.toast('Organizacion desactivada', 'success');
      await fetchOrgs();
      renderGrid(document.getElementById('orgs-grid'));
      const panel = document.getElementById('org-detail-panel');
      if (panel) panel.style.display = 'none';
    } catch (err) {
      UI.toast(err.message, 'error');
    }
  }

  async function _activate(orgId) {
    try {
      await Api.patch(`/api/organizations/${orgId}`, { is_active: true });
      UI.toast('Organizacion activada', 'success');
      await fetchOrgs();
      renderGrid(document.getElementById('orgs-grid'));
    } catch (err) {
      UI.toast(err.message, 'error');
    }
  }

  async function _moveUser(userId) {
    const orgName = prompt('Nombre exacto de la organizacion destino (o ID):');
    if (!orgName) return;
    const dest = _orgs.find(o => o.name === orgName || String(o.id) === orgName);
    if (!dest) {
      UI.toast('Organizacion no encontrada', 'error');
      return;
    }
    try {
      await Api.patch(`/api/organizations/${_selectedOrg.id}/users/${userId}/move`, { target_org_id: dest.id });
      UI.toast('Usuario movido correctamente', 'success');
      await fetchOrgUsers(_selectedOrg.id);
      _openDetail(_selectedOrg.id);
    } catch (err) {
      UI.toast(err.message, 'error');
    }
  }

  function openNewOrgModal() {
    UI.modal('Nueva organizacion', `
      <div class="form-grid">
        <div class="span2">
          <label>Nombre *</label>
          <input class="input" id="org-name" required placeholder="Empresa S.A.">
        </div>
        <div>
          <label>Dominio de email</label>
          <input class="input" id="org-domain" placeholder="empresa.com">
        </div>
        <div>
          <label>Plan</label>
          <select class="input" id="org-plan">
            <option value="starter">starter</option>
            <option value="professional">professional</option>
            <option value="enterprise">enterprise</option>
          </select>
        </div>
        <div>
          <label>Max. usuarios</label>
          <input class="input" type="number" id="org-max-users" value="10" min="1">
        </div>
      </div>
    `, {
      actions: `
        <button class="btn" id="m-cancel">Cancelar</button>
        <button class="btn btn-primary" id="m-save">Crear organizacion</button>
      `,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const name = document.getElementById('org-name').value.trim();
      if (!name) { UI.toast('El nombre es obligatorio', 'error'); return; }
      const payload = {
        name,
        domain: document.getElementById('org-domain').value.trim() || null,
        plan: document.getElementById('org-plan').value,
        max_users: parseInt(document.getElementById('org-max-users').value) || 10,
        is_active: true,
      };
      try {
        await Api.post('/api/organizations/', payload);
        UI.toast('Organizacion creada', 'success');
        UI.closeModal();
        await fetchOrgs();
        renderGrid(document.getElementById('orgs-grid'));
      } catch (err) {
        UI.toast(err.message, 'error');
      }
    };
  }

  return { render, _openDetail, _deactivate, _activate, _moveUser };
})();
