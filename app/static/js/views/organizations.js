/* Vista de gestion de organizaciones (solo superadmin). */
const ViewOrganizations = (() => {

  let _orgs = [];
  let _selectedOrg = null;
  let _orgUsers = [];
  let _planLimits = null;  // {free:[...], starter:[...], pro:[...], enterprise:null}
  let _container = null;

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
    if (!_planLimits) return true;
    const limits = _planLimits[plan];
    if (limits === null) return true;  // enterprise = all
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
    _container = container;
    container.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('organizations.title')}</h1>
          <p class="page-subtitle">${t('organizations.subtitle')}</p>
        </div>
        <div class="page-actions">
          <button class="btn btn-primary" id="btn-new-org">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            ${t('organizations.new_btn')}
          </button>
        </div>
      </div>
      <div id="orgs-notice"></div>
      <div id="orgs-grid" class="card-grid"></div>
    `;

    document.getElementById('btn-new-org').onclick = () => openNewOrgModal();
    await loadOrgs(container);
  }

  async function loadOrgs(container) {
    const grid = document.getElementById('orgs-grid');
    if (!grid) return;
    grid.innerHTML = `<p class="muted">${t('organizations.loading')}</p>`;
    try {
      await Promise.all([fetchOrgs(), _loadPlanLimits()]);
      renderGrid(grid);
    } catch (e) {
      grid.innerHTML = `<p class="notice">${UI.esc(e.message)}</p>`;
    }
  }

  function renderGrid(grid) {
    if (!_orgs.length) {
      grid.innerHTML = `<p class="muted">${t('organizations.no_orgs')}</p>`;
      return;
    }
    grid.innerHTML = _orgs.map(o => {
      const plan = o.plan || 'starter';
      const limits = _planLimits ? _planLimits[plan] : null;
      const moduleCount = limits === null ? t('organizations.all_modules') : (Array.isArray(limits) ? limits.length : '?');
      return `
      <div class="card" style="cursor:pointer;" data-org-id="${o.id}">
        <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
          <strong style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${UI.esc(o.name)}</strong>
          <div style="display:flex;gap:6px;align-items:center;flex-shrink:0;">
            ${_planBadge(plan)}
            <span class="badge ${o.is_active ? 'badge-success' : 'badge-muted'}">${o.is_active ? t('organizations.active_badge') : t('organizations.inactive_badge')}</span>
          </div>
        </div>
        <div class="card-body" style="font-size:13px;color:var(--text-secondary);">
          <div><b>${t('organizations.modules')}:</b> ${moduleCount}</div>
          <div><b>${t('organizations.domain_label')}</b> ${UI.esc(o.domain || '-')}</div>
          <div><b>${t('organizations.users_label')}</b> ${o.user_count} / ${o.max_users}</div>
          <div><b>${t('organizations.ai_tokens_label')}</b> ${(o.token_usage || 0).toLocaleString()}</div>
          <div style="color:var(--text-muted);margin-top:4px;">${o.created_at ? t('organizations.created_label') + ' ' + o.created_at.split('T')[0] : ''}</div>
        </div>
        <div class="card-footer" style="display:flex;gap:8px;">
          <button class="btn btn-sm btn-secondary" onclick="ViewOrganizations._openDetail(${o.id})">${t('organizations.manage_btn')}</button>
          ${o.is_active
            ? `<button class="btn btn-sm btn-danger" onclick="ViewOrganizations._deactivate(${o.id})">${t('organizations.deactivate_btn')}</button>`
            : `<button class="btn btn-sm btn-secondary" onclick="ViewOrganizations._activate(${o.id})">${t('organizations.activate_btn')}</button>`
          }
          <button class="btn btn-sm btn-danger" style="background:#8B0000;" onclick="ViewOrganizations._deleteOrganization(${o.id}, '${UI.esc(o.name)}')">
            ${t('organizations.delete_perm_btn')}
          </button>
        </div>
      </div>`;
    }).join('');
  }

  async function _openDetail(orgId) {
    const org = _orgs.find(o => o.id === orgId);
    if (!org) return;
    _selectedOrg = org;

    UI.openModal(`
      <div class="modal-head" style="position:sticky;top:0;background:var(--bg-card);z-index:1;padding-bottom:12px;margin-bottom:16px;border-bottom:1px solid var(--border);">
        <h2 style="margin:0;font-size:16px;">${t('organizations.detail_title', { name: UI.esc(org.name) })}</h2>
        <button class="btn btn-ghost" onclick="UI.closeModal()">x</button>
      </div>

      <form id="edit-org-form" style="display:grid;grid-template-columns:1fr 1fr;gap:12px 24px;margin-bottom:20px;">
        <label>${t('organizations.name_label')}
          <input class="input" name="name" value="${UI.esc(org.name)}" required>
        </label>
        <label>${t('organizations.domain_form_label')}
          <input class="input" name="domain" value="${UI.esc(org.domain || '')}" placeholder="empresa.com">
        </label>
        <label>${t('organizations.plan_label')}
          <select class="input" name="plan" onchange="ViewOrganizations._onPlanChange(this, ${org.id})">
            ${['free','starter','pro','enterprise'].map(p =>
              `<option value="${p}" ${(org.plan === p || (!org.plan && p === 'starter')) ? 'selected' : ''}>${(PLAN_COLORS[p] || {label:p}).label}</option>`
            ).join('')}
          </select>
        </label>
        <label>${t('organizations.max_users_label')}
          <input class="input" type="number" name="max_users" value="${org.max_users}" min="1">
        </label>
        <div style="grid-column:1/-1;border-top:1px solid var(--border);padding-top:12px;">
          <div style="display:flex;align-items:center;gap:12px;">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin:0;">
              <div style="position:relative;display:inline-block;width:40px;height:22px;">
                <input type="checkbox" id="org-mfa-toggle" name="mfa_required" ${org.mfa_required ? 'checked' : ''}
                  style="opacity:0;width:0;height:0;position:absolute;"
                  onchange="this.closest('label').querySelector('.toggle-track').style.background=this.checked?'var(--brand-purple)':'var(--border)';this.closest('label').querySelector('.toggle-knob').style.left=this.checked?'20px':'2px'">
                <span class="toggle-track" style="position:absolute;inset:0;border-radius:22px;transition:background .2s;background:${org.mfa_required ? 'var(--brand-purple)' : 'var(--border)'}"></span>
                <span class="toggle-knob" style="position:absolute;top:3px;left:${org.mfa_required ? '20px' : '2px'};width:16px;height:16px;border-radius:50%;background:#fff;transition:left .2s;box-shadow:0 1px 3px rgba(0,0,0,.3)"></span>
              </div>
              <span style="font-size:13px;font-weight:500;">Requerir MFA para todos los usuarios</span>
            </label>
            <span style="font-size:12px;color:var(--text-muted);">Los overrides individuales de cada usuario tienen prioridad. Si hay SSO configurado, el SSO es quien gestiona la autenticacion.</span>
          </div>
        </div>
        <div style="grid-column:1/-1;display:flex;gap:12px;justify-content:flex-end;">
          <button type="submit" class="btn btn-primary">${t('organizations.save_btn')}</button>
        </div>
      </form>

      <hr style="margin:0 0 20px;">
      <div id="org-users-container-${orgId}">
        <p class="muted">${t('organizations.loading')}</p>
      </div>

      <hr style="margin:20px 0;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="font-size:14px;font-weight:600;margin:0;">${t('organizations.flags_section')}</h3>
      </div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">
        ${t('organizations.flags_desc')}
      </p>
      <div id="org-flags-container-${orgId}">
        <p class="muted">${t('organizations.flags_loading')}</p>
      </div>

      <hr style="margin:20px 0;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="font-size:14px;font-weight:600;margin:0;">${t('organizations.license_section')}</h3>
        <button class="btn btn-sm btn-secondary" onclick="ViewOrganizations._openLicenseModal(${orgId})">${t('organizations.manage_license_btn')}</button>
      </div>
      <div id="org-license-container-${orgId}">
        <p class="muted">${t('organizations.license_loading')}</p>
      </div>
    `, { width: '90vw' });

    // Edge hace scrollIntoView a los checkboxes de la tabla de flags al inyectarlos.
    // Ningun reset puntual funciona porque Edge lo sobreescribe en el ciclo de layout.
    // Solucion: setInterval a 16ms que fuerza scrollTop=0 en cada frame hasta que
    // el usuario haga scroll manual (wheel/touch) o pasen 4 segundos.
    const _m = document.querySelector('#modal-root .modal');
    if (_m) {
      let _locked = true;
      const _iv = setInterval(() => { if (_locked) _m.scrollTop = 0; }, 16);
      const _release = () => { _locked = false; clearInterval(_iv); };
      _m.addEventListener('wheel',      _release, { once: true, passive: true });
      _m.addEventListener('touchstart', _release, { once: true, passive: true });
      setTimeout(_release, 4000);
    }

    document.getElementById('edit-org-form').onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const payload = {
        name: fd.get('name'),
        domain: fd.get('domain') || null,
        plan: fd.get('plan'),
        max_users: parseInt(fd.get('max_users')),
        mfa_required: document.getElementById('org-mfa-toggle').checked,
      };
      try {
        await Api.patch(`/api/organizations/${orgId}`, payload);
        UI.toast(t('organizations.org_updated'), 'success');
        await fetchOrgs();
        const g = document.getElementById('orgs-grid');
        if (g) renderGrid(g);
        _openDetail(orgId);
      } catch (err) {
        UI.toast(err.message, 'error');
      }
    };

    // Cargar usuarios, flags y licencia en paralelo (modal ya visible)
    fetchOrgUsers(orgId).catch(() => { _orgUsers = []; }).then(() => {
      const uc = document.getElementById(`org-users-container-${orgId}`);
      if (!uc) return;
      uc.innerHTML = `<h3 style="font-size:14px;font-weight:600;margin-bottom:12px;">${t('organizations.users_section', { n: _orgUsers.length })}</h3>` +
        (_orgUsers.length ? `<table class="table"><thead><tr>
          <th>${t('organizations.col_name')}</th><th>${t('organizations.col_email')}</th>
          <th>${t('organizations.col_role')}</th><th>${t('organizations.col_active')}</th><th></th>
        </tr></thead><tbody>${_orgUsers.map(u => `<tr>
          <td>${UI.esc(u.full_name || u.email)}</td><td>${UI.esc(u.email)}</td>
          <td>${UI.esc(u.role)}</td><td>${u.is_active ? t('organizations.yes_label') : t('organizations.no_label')}</td>
          <td><button class="btn btn-xs btn-ghost" onclick="ViewOrganizations._moveUser(${u.id})">${t('organizations.move_btn')}</button></td>
        </tr>`).join('')}</tbody></table>` : `<p class="muted">${t('organizations.no_users')}</p>`);
    });
    _renderOrgFlags(orgId);
    _renderOrgLicense(orgId);
  }

  async function _renderOrgFlags(orgId) {
    const container = document.getElementById(`org-flags-container-${orgId}`);
    if (!container) return;
    try {
      const flags = await Api.featureFlags.list(orgId);
      if (!flags.length) {
        container.innerHTML = `<p class="muted">${t('organizations.flags_none')}</p>`;
        return;
      }
      const org = _orgs.find(o => o.id === orgId);
      const orgPlan = org ? (org.plan || 'starter') : 'starter';

      container.innerHTML = `
        <table class="table" style="font-size:13px;">
          <thead>
            <tr>
              <th>${t('organizations.col_module')}</th>
              <th>${t('organizations.col_description')}</th>
              <th style="text-align:center;">${t('organizations.col_status')}</th>
              <th style="text-align:center;">${t('organizations.col_plan')}</th>
              <th style="text-align:center;">${t('organizations.col_origin')}</th>
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
                    ? `<label class="toggle" title="${f.enabled ? t('organizations.enabled_title') : t('organizations.disabled_title')}">
                        <input type="checkbox" ${f.enabled ? 'checked' : ''}
                          onchange="ViewOrganizations._toggleOrgFlag('${UI.esc(f.name)}', this.checked, ${orgId})">
                        <span class="toggle-slider"></span>
                       </label>`
                    : `<span title="${t('organizations.no_plan_title')}"
                             style="background:#FEE2E2;color:#a83232;padding:2px 7px;border-radius:4px;font-size:10px;cursor:default;">
                         ${t('organizations.no_plan_badge')}
                       </span>`
                  }
                </td>
                <td style="text-align:center;">
                  ${inPlan
                    ? `<span style="background:#E8F5E9;color:#2e7d32;padding:2px 7px;border-radius:4px;font-size:10px;">${t('organizations.included_badge')}</span>`
                    : `<span style="background:#FEF3C7;color:#92400E;padding:2px 7px;border-radius:4px;font-size:10px;">${t('organizations.upgrade_badge')}</span>`
                  }
                </td>
                <td style="text-align:center;">
                  ${f.org_override
                    ? `<span style="background:var(--brand-purple);color:#fff;padding:2px 7px;border-radius:4px;font-size:11px;">${t('organizations.custom_badge')}</span>`
                    : `<span style="background:var(--bg-secondary);color:var(--text-muted);padding:2px 7px;border-radius:4px;font-size:11px;">${t('organizations.global_badge')}</span>`
                  }
                </td>
                <td style="text-align:right;">
                  ${f.org_override ? `
                    <button class="btn btn-xs btn-ghost"
                      title="${t('organizations.reset_btn')}"
                      onclick="ViewOrganizations._resetOrgFlag('${UI.esc(f.name)}', ${orgId})">
                      ${t('organizations.reset_btn')}
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
    const org = _orgs.find(o => o.id === orgId);
    if (org) org.plan = select.value;
    _renderOrgFlags(orgId);
  }

  async function _toggleOrgFlag(flagName, enabled, orgId) {
    try {
      await Api.featureFlags.update(flagName, enabled, orgId);
      UI.toast(enabled ? t('organizations.module_toggled_on') : t('organizations.module_toggled_off'), 'success');
      await _renderOrgFlags(orgId);
    } catch (err) {
      UI.toast(err.message, 'error');
      await _renderOrgFlags(orgId);
    }
  }

  async function _resetOrgFlag(flagName, orgId) {
    if (!await UI.confirm(t('organizations.reset_confirm', { name: flagName }))) return;
    try {
      await Api.featureFlags.reset(flagName, orgId);
      UI.toast(t('organizations.reset_toast'), 'success');
      await _renderOrgFlags(orgId);
    } catch (err) {
      UI.toast(err.message, 'error');
    }
  }

  async function _renderOrgLicense(orgId) {
    const container = document.getElementById(`org-license-container-${orgId}`);
    if (!container) return;
    const locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
    let licenseHtml = '';

    try {
      const license = await Api.get(`/api/licenses/${orgId}`);
      const statusColors = {
        active:    { bg: '#E8F5E9', text: '#2e7d32' },
        suspended: { bg: '#FFF3CD', text: '#856404' },
        expired:   { bg: '#FEE2E2', text: '#a83232' },
      };
      const colors = statusColors[license.status] || statusColors.active;
      const now = new Date();
      const expiresAt = license.expires_at ? new Date(license.expires_at) : null;
      const isExpired = expiresAt && expiresAt < now;
      const daysLeft = expiresAt ? Math.ceil((expiresAt - now) / (1000 * 60 * 60 * 24)) : null;
      const isExpiringSoon = daysLeft !== null && daysLeft > 0 && daysLeft <= 30;

      let expiryHtml;
      if (!expiresAt) {
        expiryHtml = `<span style="color:var(--text-muted);">${t('organizations.license_no_limit')}</span>`;
      } else if (isExpired) {
        expiryHtml = `<span style="background:#FEE2E2;color:#a83232;padding:2px 7px;border-radius:4px;font-size:11px;font-weight:600;">${t('organizations.license_expired')}</span> — ${expiresAt.toLocaleDateString(locale)}`;
      } else if (isExpiringSoon) {
        expiryHtml = `<span style="background:#FEF3C7;color:#92400E;padding:2px 7px;border-radius:4px;font-size:11px;font-weight:600;">${t('organizations.license_expiring_soon', { n: daysLeft })}</span> — ${expiresAt.toLocaleDateString(locale)}`;
      } else {
        expiryHtml = `<span style="color:var(--text-secondary);">${t('organizations.license_days_left', { n: daysLeft })}</span> — ${expiresAt.toLocaleDateString(locale)}`;
      }

      licenseHtml = `
        <div style="background:var(--bg-secondary);padding:14px;border-radius:8px;display:grid;row-gap:10px;grid-template-columns:130px 1fr;">
          <div style="font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--text-muted);align-self:center;">${t('organizations.license_plan_label')}</div>
          <div style="align-self:center;">${_planBadge(license.plan)}</div>

          <div style="font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--text-muted);align-self:center;">${t('organizations.license_status_label')}</div>
          <div style="align-self:center;"><span style="background:${colors.bg};color:${colors.text};padding:2px 9px;border-radius:4px;font-size:11px;font-weight:700;">${license.status.toUpperCase()}</span></div>

          <div style="font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--text-muted);align-self:center;">${t('organizations.license_expires_label')}</div>
          <div style="align-self:center;font-size:13px;">${expiryHtml}</div>

          <div style="font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.4px;color:var(--text-muted);align-self:center;">${t('organizations.license_issued_label')}</div>
          <div style="align-self:center;font-size:12px;color:var(--text-muted);">${new Date(license.issued_at).toLocaleDateString(locale)}</div>
        </div>
      `;
    } catch (err) {
      if (err.status === 404) {
        licenseHtml = `
          <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:var(--bg-2);border:1px dashed var(--border);border-radius:8px;">
            <span style="font-size:13px;color:var(--text-muted);">${t('organizations.no_license')}</span>
            <button class="btn btn-sm btn-primary" onclick="ViewOrganizations._openLicenseModal(${orgId})">${t('organizations.assign_license_btn')}</button>
          </div>`;
      } else {
        licenseHtml = `<p class="notice">${UI.esc(err.message)}</p>`;
      }
    }

    const jwtSection = `
      <div style="margin-top:14px;padding:14px;background:var(--bg-secondary);border-radius:8px;border-left:3px solid var(--brand-purple);">
        <div style="font-size:13px;font-weight:600;margin-bottom:4px;">${t('organizations.license_jwt_title')}</div>
        <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">${t('organizations.license_jwt_desc')}</p>
        <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;">
          <label style="font-size:12px;color:var(--text-secondary);">
            ${t('organizations.license_jwt_days_label')}
            <input class="input" type="number" id="jwt-days-${orgId}" value="365" min="1" max="3650" style="width:90px;margin-top:4px;display:block;">
          </label>
          <label style="font-size:12px;color:var(--text-secondary);">
            ${t('organizations.license_jwt_grace_label')}
            <input class="input" type="number" id="jwt-grace-${orgId}" value="30" min="0" max="365" style="width:90px;margin-top:4px;display:block;">
          </label>
          <button class="btn btn-primary btn-sm" style="align-self:flex-end;" id="jwt-download-btn-${orgId}" onclick="ViewOrganizations._downloadOrgLicense(${orgId})">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            ${t('organizations.license_jwt_btn')}
          </button>
        </div>
      </div>
    `;

    container.innerHTML = licenseHtml + jwtSection;
  }

  async function _downloadOrgLicense(orgId) {
    const days = parseInt(document.getElementById(`jwt-days-${orgId}`)?.value || '365');
    const graceDays = parseInt(document.getElementById(`jwt-grace-${orgId}`)?.value || '30');
    const btn = document.getElementById(`jwt-download-btn-${orgId}`);

    if (btn) { btn.disabled = true; btn.textContent = t('organizations.license_jwt_generating'); }

    try {
      const token = Auth.token();
      const resp = await fetch(`/api/license/generate/${orgId}?days=${days}&grace_days=${graceDays}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(errData.detail || `HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      const disposition = resp.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename="([^"]+)"/);
      const filename = match ? match[1] : `license_org${orgId}.jwt`;

      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      UI.toast(t('organizations.license_jwt_downloaded'), 'success');
    } catch (e) {
      UI.toast(t('organizations.license_jwt_error') + ': ' + e.message, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> ${t('organizations.license_jwt_btn')}`;
      }
    }
  }

  async function _openLicenseModal(orgId) {
    let license = null;
    let history = [];
    const locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
    try {
      license = await Api.get(`/api/licenses/${orgId}`);
      history = await Api.get(`/api/licenses/${orgId}/audit`);
    } catch (err) {
      if (err.status !== 404) {
        UI.toast(err.message, 'error');
        return;
      }
    }

    const isNew = !license;
    const expiresStr = license && license.expires_at ? license.expires_at.split('T')[0] : '';
    const planOpts = ['free', 'starter', 'pro', 'enterprise'].map(p =>
      `<option value="${p}" ${license && license.plan === p ? 'selected' : ''}>${(PLAN_COLORS[p] || { label: p }).label}</option>`
    ).join('');

    UI.modal(isNew ? t('organizations.license_modal_new') : t('organizations.license_modal_edit'), `
      <div class="form-grid">
        <div class="span2">
          <label>${t('organizations.license_plan_field')}
            <select class="input" id="license-plan" required>${planOpts}</select>
          </label>
        </div>
        ${!isNew ? `
        <div>
          <label>${t('organizations.license_status_field')}
            <select class="input" id="license-status" required>
              <option value="active" ${license.status === 'active' ? 'selected' : ''}>${t('organizations.license_status_active')}</option>
              <option value="suspended" ${license.status === 'suspended' ? 'selected' : ''}>${t('organizations.license_status_suspended')}</option>
              <option value="expired" ${license.status === 'expired' ? 'selected' : ''}>${t('organizations.license_status_expired')}</option>
            </select>
          </label>
        </div>` : ''}
        <div>
          <label>${t('organizations.license_expires_field')}
            <input class="input" type="date" id="license-expires" value="${expiresStr}">
          </label>
        </div>
        <div class="span2">
          <label>${t('organizations.license_reason_field')}
            <input class="input" id="license-reason" placeholder="${t('organizations.license_reason_placeholder')}">
          </label>
        </div>
      </div>

      ${!isNew && history.length ? `
        <hr style="margin:20px 0;">
        <h3 style="font-size:13px;font-weight:600;margin-bottom:12px;">${t('organizations.license_history_title')}</h3>
        <table class="table" style="font-size:12px;">
          <thead><tr>
            <th>${t('organizations.license_col_date')}</th>
            <th>${t('organizations.license_col_plan')}</th>
            <th>${t('organizations.license_col_status')}</th>
            <th>${t('organizations.license_col_reason')}</th>
          </tr></thead>
          <tbody>
            ${history.slice(0, 10).map(h => `
              <tr>
                <td>${new Date(h.changed_at).toLocaleDateString(locale)}</td>
                <td>${h.plan_new || h.plan_old || '-'}</td>
                <td><span style="font-size:10px;background:var(--bg-secondary);padding:1px 4px;border-radius:2px;">${h.status_new || h.status_old || '-'}</span></td>
                <td>${UI.esc(h.reason || '-')}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      ` : (!isNew ? `<hr style="margin:20px 0;"><p class="muted" style="font-size:12px;">${t('organizations.license_no_history')}</p>` : '')}
    `, {
      actions: `
        <button class="btn" id="m-cancel">${t('organizations.cancel_btn')}</button>
        <button class="btn btn-primary" id="m-save">${isNew ? t('organizations.license_modal_new') : t('organizations.save_btn')}</button>
      `,
    });

    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const plan = document.getElementById('license-plan').value;
      const expiresAt = document.getElementById('license-expires').value;
      const reason = document.getElementById('license-reason').value;
      const expiresIso = expiresAt ? new Date(expiresAt + 'T00:00:00Z').toISOString() : null;

      try {
        if (isNew) {
          await Api.post(`/api/licenses/${orgId}`, {
            plan,
            expires_at: expiresIso,
            reason: reason || 'initial_assignment',
          });
          UI.toast(t('organizations.license_assigned'), 'success');
        } else {
          const status = document.getElementById('license-status').value;
          await Api.patch(`/api/licenses/${orgId}`, {
            plan,
            status,
            expires_at: expiresIso,
            reason: reason || null,
          });
          UI.toast(t('organizations.license_updated'), 'success');
        }
        UI.closeModal();
        await _renderOrgLicense(orgId);
      } catch (err) {
        UI.toast(err.message, 'error');
      }
    };
  }

  function _backToList() {
    UI.closeModal();
  }

  async function _deactivate(orgId) {
    if (!await UI.confirm(t('organizations.deactivate_confirm'))) return;
    try {
      await Api.del(`/api/organizations/${orgId}`);
      UI.toast(t('organizations.deactivated_toast'), 'success');
      await fetchOrgs();
      const _g = document.getElementById('orgs-grid'); if (_g) renderGrid(_g);
      _backToList();
    } catch (err) {
      UI.toast(err.message, 'error');
    }
  }

  async function _activate(orgId) {
    try {
      await Api.patch(`/api/organizations/${orgId}`, { is_active: true });
      UI.toast(t('organizations.activated_toast'), 'success');
      await fetchOrgs();
      const _g = document.getElementById('orgs-grid'); if (_g) renderGrid(_g);
    } catch (err) {
      UI.toast(err.message, 'error');
    }
  }

  async function _deleteOrganization(orgId, orgName) {
    if (!confirm(t('organizations.delete_perm_warning', { name: orgName }))) return;

    UI.modal(t('organizations.delete_perm_modal_title'), `
      <div style="background:#FEE2E2;padding:12px;border-radius:8px;margin-bottom:16px;border-left:4px solid #a83232;">
        <strong style="color:#a83232;">${t('organizations.delete_perm_warning_label')}</strong>
        <p style="margin:8px 0 0;font-size:12px;">${t('organizations.delete_perm_warning_desc', { name: orgName })}</p>
      </div>
      <p style="color:var(--text-muted);margin-bottom:8px;">${t('organizations.delete_perm_type_label')}</p>
      <input class="input" id="delete-confirm-text" type="text" placeholder="${t('organizations.delete_perm_placeholder')}" autocomplete="off">
    `, {
      actions: `
        <button class="btn" id="m-cancel">${t('organizations.cancel_btn')}</button>
        <button class="btn" id="m-delete" style="background:#8B0000;color:white;">${t('organizations.delete_perm_btn_modal')}</button>
      `,
    });

    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-delete').onclick = async () => {
      const confirmText = document.getElementById('delete-confirm-text').value;
      const expected = t('organizations.delete_perm_placeholder');
      if (confirmText !== expected) {
        UI.toast(t('organizations.delete_perm_wrong_text'), 'error');
        return;
      }

      const btn = document.getElementById('m-delete');
      btn.disabled = true;
      btn.textContent = t('organizations.deleting_label');

      try {
        await Api.post(`/api/organizations/${orgId}/delete-permanently`, {
          confirmation_text: confirmText,
        });
        UI.toast(t('organizations.deleted_toast'), 'success');
        UI.closeModal();
        await fetchOrgs();
        const _g = document.getElementById('orgs-grid'); if (_g) renderGrid(_g);
        _backToList();
      } catch (err) {
        UI.toast(err.message, 'error');
        btn.disabled = false;
        btn.textContent = t('organizations.delete_perm_btn_modal');
      }
    };
  }

  async function _moveUser(userId) {
    const orgName = prompt(t('organizations.move_user_prompt'));
    if (!orgName) return;
    const dest = _orgs.find(o => o.name === orgName || String(o.id) === orgName);
    if (!dest) {
      UI.toast(t('organizations.move_user_not_found'), 'error');
      return;
    }
    try {
      await Api.patch(`/api/organizations/${_selectedOrg.id}/users/${userId}/move`, { target_org_id: dest.id });
      UI.toast(t('organizations.move_user_toast'), 'success');
      await fetchOrgUsers(_selectedOrg.id);
      _openDetail(_selectedOrg.id);
    } catch (err) {
      UI.toast(err.message, 'error');
    }
  }

  function openNewOrgModal() {
    UI.modal(t('organizations.new_modal_title'), `
      <div class="form-grid">
        <div class="span2">
          <label>${t('organizations.new_name_label')}</label>
          <input class="input" id="org-name" required placeholder="Empresa S.A.">
        </div>
        <div>
          <label>${t('organizations.new_domain_label')}</label>
          <input class="input" id="org-domain" placeholder="empresa.com">
        </div>
        <div>
          <label>${t('organizations.new_plan_label')}</label>
          <select class="input" id="org-plan">
            <option value="free">${t('organizations.plan_options.free')}</option>
            <option value="starter" selected>${t('organizations.plan_options.starter')}</option>
            <option value="pro">${t('organizations.plan_options.pro')}</option>
            <option value="enterprise">${t('organizations.plan_options.enterprise')}</option>
          </select>
        </div>
        <div>
          <label>${t('organizations.new_max_users_label')}</label>
          <input class="input" type="number" id="org-max-users" value="10" min="1">
        </div>
      </div>
    `, {
      actions: `
        <button class="btn" id="m-cancel">${t('organizations.cancel_btn')}</button>
        <button class="btn btn-primary" id="m-save">${t('organizations.create_btn')}</button>
      `,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const name = document.getElementById('org-name').value.trim();
      if (!name) { UI.toast(t('organizations.name_required'), 'error'); return; }
      const payload = {
        name,
        domain: document.getElementById('org-domain').value.trim() || null,
        plan: document.getElementById('org-plan').value,
        max_users: parseInt(document.getElementById('org-max-users').value) || 10,
        is_active: true,
      };
      try {
        await Api.post('/api/organizations/', payload);
        UI.toast(t('organizations.created_toast'), 'success');
        UI.closeModal();
        await fetchOrgs();
        const _g = document.getElementById('orgs-grid'); if (_g) renderGrid(_g);
      } catch (err) {
        UI.toast(err.message, 'error');
      }
    };
  }

  return { render, _openDetail, _backToList, _deactivate, _activate, _moveUser, _toggleOrgFlag, _resetOrgFlag, _onPlanChange, _openLicenseModal, _deleteOrganization, _downloadOrgLicense };
})();
