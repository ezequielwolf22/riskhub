/* Vista de gestion de organizaciones (solo superadmin). */
const ViewOrganizations = (() => {

  let _orgs = [];
  let _selectedOrg = null;
  let _orgUsers = [];
  let _planLimits = null;  // {free:[...], starter:[...], pro:[...], enterprise:null}

  const PLAN_COLORS = {
    free:       { bg: '#F3F4F6', text: '#6B7280', label: 'Free' },
    starter:    { bg: '#EEF2FF', text: '#4338CA', label: 'Starter' },
    pro:        { bg: '#F0FDF4', text: '#15803D', label: 'Pro' },
    enterprise: { bg: '#FFF7ED', text: '#C2410C', label: 'Enterprise' },
  };

  function _planBadge(plan) {
    const p = PLAN_COLORS[plan] || PLAN_COLORS.starter;
    return `<span style="background:${p.bg};color:${p.text};padding:2px 10px;border-radius:10px;
                         font-size:11px;font-weight:700;letter-spacing:.3px;">${p.label}</span>`;
  }

  function _isModuleInPlan(flagName, plan) {
    if (!_planLimits) return true;  // si no hay datos, no bloquear
    const limits = _planLimits[plan];
    if (limits === null) return true;  // enterprise = todo
    return Array.isArray(limits) && limits.includes(flagName);
  }

  async function _loadPlanLimits() {
    if (_planLimits) return;
    try {
      _planLimits = await Api.get('/api/feature-flags/plans/limits');
    } catch (_) { _planLimits = {}; }
  }

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
      await Promise.all([fetchOrgs(), _loadPlanLimits()]);
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
    grid.innerHTML = _orgs.map(o => {
      const plan = o.plan || 'starter';
      const limits = _planLimits ? _planLimits[plan] : null;
      const moduleCount = limits === null ? 'Todos' : (Array.isArray(limits) ? limits.length : '?');
      return `
      <div class="card" style="cursor:pointer;" data-org-id="${o.id}">
        <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
          <strong style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${UI.esc(o.name)}</strong>
          <div style="display:flex;gap:6px;align-items:center;flex-shrink:0;">
            ${_planBadge(plan)}
            <span class="badge ${o.is_active ? 'badge-success' : 'badge-muted'}">${o.is_active ? 'Activa' : 'Inactiva'}</span>
          </div>
        </div>
        <div class="card-body" style="font-size:13px;color:var(--text-secondary);">
          <div><b>Modulos:</b> ${moduleCount}</div>
          <div><b>Dominio:</b> ${UI.esc(o.domain || '-')}</div>
          <div><b>Usuarios:</b> ${o.user_count} / ${o.max_users}</div>
          <div><b>Tokens IA:</b> ${(o.token_usage || 0).toLocaleString()}</div>
          <div style="color:var(--text-muted);margin-top:4px;">${o.created_at ? 'Creada: ' + o.created_at.split('T')[0] : ''}</div>
        </div>
        <div class="card-footer" style="display:flex;gap:8px;">
          <button class="btn btn-sm btn-secondary" onclick="ViewOrganizations._openDetail(${o.id})">Gestionar</button>
          ${o.is_active
            ? `<button class="btn btn-sm btn-danger" onclick="ViewOrganizations._deactivate(${o.id})">Desactivar</button>`
            : `<button class="btn btn-sm btn-secondary" onclick="ViewOrganizations._activate(${o.id})">Activar</button>`
          }
        </div>
      </div>`;
    }).join('');
  }

  async function _openDetail(orgId) {
    const org = _orgs.find(o => o.id === orgId);
    if (!org) return;
    _selectedOrg = org;

    const panel = document.getElementById('org-detail-panel');
    panel.style.display = 'block';
    panel.innerHTML = '<p class="muted">Cargando...</p>';

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
              <select class="input" name="plan" onchange="ViewOrganizations._onPlanChange(this, ${org.id})">
                ${['free','starter','pro','enterprise'].map(p =>
                  `<option value="${p}" ${(org.plan === p || (!org.plan && p === 'starter')) ? 'selected' : ''}>${(PLAN_COLORS[p] || {label:p}).label}</option>`
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

          <hr style="margin:20px 0;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <h3 style="font-size:14px;font-weight:600;margin:0;">Modulos (Feature Flags)</h3>
          </div>
          <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">
            Configura que modulos estan disponibles para esta organizacion.
            Los flags con la etiqueta <span style="background:var(--bg-secondary);color:var(--text-muted);padding:1px 6px;border-radius:4px;font-size:11px;">Global</span>
            heredan el valor por defecto del sistema.
          </p>
          <div id="org-flags-container-${orgId}">
            <p class="muted">Cargando modulos...</p>
          </div>
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

    // Cargar y renderizar feature flags de la org
    await _renderOrgFlags(orgId);
  }

  async function _renderOrgFlags(orgId) {
    const container = document.getElementById(`org-flags-container-${orgId}`);
    if (!container) return;
    try {
      const flags = await Api.featureFlags.list(orgId);
      if (!flags.length) {
        container.innerHTML = '<p class="muted">No hay modulos configurados.</p>';
        return;
      }
      const org = _orgs.find(o => o.id === orgId);
      const orgPlan = org ? (org.plan || 'starter') : 'starter';

      container.innerHTML = `
        <table class="table" style="font-size:13px;">
          <thead>
            <tr>
              <th>Modulo</th>
              <th>Descripcion</th>
              <th style="text-align:center;">Estado</th>
              <th style="text-align:center;">Plan</th>
              <th style="text-align:center;">Origen</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${flags.map(f => {
              const inPlan = _isModuleInPlan(f.name, orgPlan);
              return `
              <tr data-flag="${UI.esc(f.name)}" ${!inPlan ? 'style="opacity:.55;"' : ''}>
                <td><strong>${UI.esc(f.label)}</strong></td>
                <td style="color:var(--text-muted);">${UI.esc(f.description || '')}</td>
                <td style="text-align:center;">
                  ${inPlan
                    ? `<label class="toggle" title="${f.enabled ? 'Activado' : 'Desactivado'}">
                        <input type="checkbox" ${f.enabled ? 'checked' : ''}
                          onchange="ViewOrganizations._toggleOrgFlag('${UI.esc(f.name)}', this.checked, ${orgId})">
                        <span class="toggle-slider"></span>
                       </label>`
                    : `<span title="Requiere upgrade de plan"
                             style="background:#FEE2E2;color:#a83232;padding:2px 7px;border-radius:4px;font-size:10px;cursor:default;">
                         Sin plan
                       </span>`
                  }
                </td>
                <td style="text-align:center;">
                  ${inPlan
                    ? `<span style="background:#E8F5E9;color:#2e7d32;padding:2px 7px;border-radius:4px;font-size:10px;">Incluido</span>`
                    : `<span style="background:#FEF3C7;color:#92400E;padding:2px 7px;border-radius:4px;font-size:10px;">Upgrade</span>`
                  }
                </td>
                <td style="text-align:center;">
                  ${f.org_override
                    ? `<span style="background:var(--brand-purple);color:#fff;padding:2px 7px;border-radius:4px;font-size:11px;">Personalizado</span>`
                    : `<span style="background:var(--bg-secondary);color:var(--text-muted);padding:2px 7px;border-radius:4px;font-size:11px;">Global</span>`
                  }
                </td>
                <td style="text-align:right;">
                  ${f.org_override ? `
                    <button class="btn btn-xs btn-ghost"
                      title="Restablecer al valor global"
                      onclick="ViewOrganizations._resetOrgFlag('${UI.esc(f.name)}', ${orgId})">
                      Restablecer
                    </button>
                  ` : ''}
                </td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
      `;
    } catch (err) {
      container.innerHTML = `<p class="notice">${UI.esc(err.message)}</p>`;
    }
  }

  function _onPlanChange(select, orgId) {
    // Actualizar org en cache local para que los badges de plan se reflejen inmediatamente
    const org = _orgs.find(o => o.id === orgId);
    if (org) org.plan = select.value;
    // Re-renderizar los flags para mostrar que modulos estan incluidos en el nuevo plan
    _renderOrgFlags(orgId);
  }

  async function _toggleOrgFlag(flagName, enabled, orgId) {
    try {
      await Api.featureFlags.update(flagName, enabled, orgId);
      UI.toast(`Modulo ${enabled ? 'activado' : 'desactivado'}`, 'success');
      await _renderOrgFlags(orgId);
    } catch (err) {
      UI.toast(err.message, 'error');
      await _renderOrgFlags(orgId);  // revertir visual
    }
  }

  async function _resetOrgFlag(flagName, orgId) {
    if (!confirm(`Restablecer "${flagName}" al valor global para esta organizacion?`)) return;
    try {
      await Api.featureFlags.reset(flagName, orgId);
      UI.toast('Restablecido al valor global', 'success');
      await _renderOrgFlags(orgId);
    } catch (err) {
      UI.toast(err.message, 'error');
    }
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
            <option value="free">Free (3 modulos)</option>
            <option value="starter" selected>Starter (8 modulos)</option>
            <option value="pro">Pro (17 modulos)</option>
            <option value="enterprise">Enterprise (todos)</option>
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

  return { render, _openDetail, _deactivate, _activate, _moveUser, _toggleOrgFlag, _resetOrgFlag, _onPlanChange };
})();
