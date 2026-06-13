/* Vista SuperAdmin — Gestion de Feature Flags (modulos habilitados por licencia). */
const ViewFeatureFlags = (() => {

  const MODULE_ROUTES = {
    module_assets:           'assets',
    module_risks:            'risks',
    module_controls:         'controls',
    module_policies:         'policies',
    module_incidents:        'incidents',
    module_suppliers:        'suppliers',
    module_nonconformities:  'nonconformities',
    module_tasks:            'tasks',
    module_audits:           'internal-audits',
    module_gdpr:             'gdpr',
    module_compliance:       'compliance',
    module_ai:               'ai-chat',
    module_reports:          'reports',
    module_integrations:     'integrations',
    module_alerts:           'alerts',
    module_cve:              'cve',
    module_awareness:        'awareness',
  };

  let _flags = [];

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Control de Modulos</h1>
          <p class="page-sub">Activa o desactiva secciones de la aplicacion — solo superadmin</p>
        </div>
      </div>
      <div class="notice" style="margin-bottom:16px;">
        Los cambios son inmediatos. Los usuarios activos veran los modulos ocultarse/aparecer en su
        proxima recarga de pagina.
      </div>
      <div id="ff-wrap" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;"></div>
    `;
    await _load();
  }

  async function _load() {
    const wrap = document.getElementById('ff-wrap');
    if (!wrap) return;
    try {
      _flags = await Api.featureFlags.list();
      _render(wrap);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _render(wrap) {
    if (!_flags.length) {
      wrap.innerHTML = '<p class="text-muted">No hay modulos configurados.</p>';
      return;
    }
    wrap.innerHTML = _flags.map(f => `
      <div class="card" style="display:flex;flex-direction:column;gap:8px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <b style="font-size:14px;">${UI.esc(f.label)}</b>
          <label class="toggle-switch" title="${f.enabled ? 'Desactivar' : 'Activar'} modulo">
            <input type="checkbox" data-name="${UI.esc(f.name)}" ${f.enabled ? 'checked' : ''}>
            <span class="toggle-slider"></span>
          </label>
        </div>
        <p style="font-size:12px;color:var(--text-muted);margin:0;">${UI.esc(f.description||'')}</p>
        <div style="display:flex;gap:8px;align-items:center;font-size:11px;color:var(--text-subtle);">
          <span>${f.enabled
            ? '<span style="color:var(--risk-low);font-weight:600;">Activo</span>'
            : '<span style="color:var(--text-muted);">Inactivo</span>'}</span>
          ${f.updated_at ? `<span>— ultima actualizacion: ${f.updated_at.slice(0,10)}</span>` : ''}
          ${f.updated_by ? `<span>por ${UI.esc(f.updated_by)}</span>` : ''}
        </div>
      </div>
    `).join('');

    // Eventos de los toggles
    wrap.querySelectorAll('input[type="checkbox"]').forEach(chk => {
      chk.onchange = async function() {
        const name = this.dataset.name;
        const enabled = this.checked;
        try {
          await Api.featureFlags.update(name, enabled);
          const flag = _flags.find(f => f.name === name);
          if (flag) flag.enabled = enabled;
          UI.toast(`Modulo ${enabled ? 'activado' : 'desactivado'}`, 'success');
          // Sincronizar el sidebar inmediatamente
          _syncSidebar();
        } catch (e) {
          UI.toast(e.message, 'error');
          // Revertir el toggle
          this.checked = !enabled;
        }
      };
    });
  }

  function _publishDisabled(flags) {
    // Set global consultado por UI.tabs: las pestanas de los hubs declaran
    // su ruta legacy en `route` y se ocultan si el modulo esta deshabilitado.
    window.RiskHubFlags = window.RiskHubFlags || { disabled: new Set() };
    flags.forEach(f => {
      const route = MODULE_ROUTES[f.name];
      if (!route) return;
      if (f.enabled) window.RiskHubFlags.disabled.delete(route);
      else window.RiskHubFlags.disabled.add(route);
    });
  }

  function _syncSidebar() {
    // Ocultar/mostrar enlaces del sidebar segun el estado de los flags
    _publishDisabled(_flags);
    _flags.forEach(f => {
      const route = MODULE_ROUTES[f.name];
      if (!route) return;
      document.querySelectorAll(`.sidebar a[data-route="${route}"]`).forEach(a => {
        a.style.display = f.enabled ? '' : 'none';
      });
    });
  }

  // Exportada para que app.js la llame al arrancar
  async function applyFlagsToSidebar() {
    try {
      const flags = await Api.featureFlags.list();
      _publishDisabled(flags);
      flags.forEach(f => {
        const route = MODULE_ROUTES[f.name];
        if (!route) return;
        document.querySelectorAll(`.sidebar a[data-route="${route}"]`).forEach(a => {
          a.style.display = f.enabled ? '' : 'none';
        });
      });
    } catch (_) { /* silencioso — no bloquear si falla */ }
  }

  return { render, applyFlagsToSidebar };
})();
