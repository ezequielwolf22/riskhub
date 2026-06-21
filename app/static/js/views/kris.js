/* Vista KRIs / KPIs — gestion de indicadores clave de riesgo y rendimiento */
const ViewKRIs = {
  _showHidden: false,

  async render(el) {
    el.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px;">
        <h2 style="margin:0;font-size:1.2rem;">KRIs / KPIs</h2>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
          <label style="display:flex;align-items:center;gap:6px;font-size:0.85rem;cursor:pointer;">
            <input type="checkbox" id="kri-show-hidden"> Mostrar ocultos
          </label>
          <button class="btn btn-ghost" id="kri-btn-seed" title="Inicializar KPIs de sistema por defecto">Inicializar KPIs</button>
          <button class="btn btn-ghost" id="kri-btn-eval-all">Evaluar todos</button>
          <button class="btn btn-primary" id="kri-btn-new">+ Nuevo KRI</button>
        </div>
      </div>
      <div id="kri-tabs-wrap"></div>
    `;

    document.getElementById('kri-show-hidden').onchange = (e) => {
      ViewKRIs._showHidden = e.target.checked;
      ViewKRIs._reload();
    };
    document.getElementById('kri-btn-seed').onclick = () => ViewKRIs._seedKpis();
    document.getElementById('kri-btn-eval-all').onclick = () => ViewKRIs._evalAll();
    document.getElementById('kri-btn-new').onclick = () => ViewKRIs._openModal(null);

    UI.tabs(document.getElementById('kri-tabs-wrap'), {
      hub: 'kri-inner',
      label: 'KRIs/KPIs',
      tabs: [
        { id: 'kris-tab', label: 'KRIs', render: (p) => ViewKRIs._renderList(p, 'kri') },
        { id: 'kpis-tab', label: 'KPIs', render: (p) => ViewKRIs._renderList(p, 'kpi') },
      ],
    });
  },

  async _reload() {
    // Re-renderiza la pestana activa
    const active = document.querySelector('[data-hub="kri-inner"] .tab-panel:not([hidden])');
    if (active) {
      const type = active.id.includes('kpis') ? 'kpi' : 'kri';
      await ViewKRIs._renderList(active, type);
    }
  },

  async _renderList(el, type) {
    el.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      const params = new URLSearchParams({ indicator_type: type, active_only: 'false' });
      if (ViewKRIs._showHidden) params.set('show_hidden', 'true');
      const items = await Api.get(`/api/kris?${params}`);
      if (!items.length) {
        el.innerHTML = `<div class="notice">
          No hay ${type === 'kpi' ? 'KPIs' : 'KRIs'} configurados.
          ${type === 'kpi' ? '<br><button class="btn btn-ghost" onclick="ViewKRIs._seedKpis()">Inicializar KPIs por defecto</button>' : ''}
        </div>`;
        return;
      }
      el.innerHTML = `<div class="kri-grid">${items.map(k => ViewKRIs._cardHtml(k)).join('')}</div>`;
      el.querySelectorAll('[data-kri-eval]').forEach(btn => {
        btn.onclick = () => ViewKRIs._evalOne(parseInt(btn.dataset.kriEval));
      });
      el.querySelectorAll('[data-kri-edit]').forEach(btn => {
        btn.onclick = () => ViewKRIs._openModal(parseInt(btn.dataset.kriEdit));
      });
      el.querySelectorAll('[data-kri-del]').forEach(btn => {
        btn.onclick = () => ViewKRIs._delete(parseInt(btn.dataset.kriDel), btn.dataset.kriSystem === 'true');
      });
      el.querySelectorAll('[data-kri-hide]').forEach(btn => {
        btn.onclick = () => ViewKRIs._toggleVisibility(parseInt(btn.dataset.kriHide), btn.dataset.kriVisible === 'true');
      });
    } catch (e) {
      el.innerHTML = `<div class="notice notice-error">${UI.esc(e.message)}</div>`;
    }
  },

  _cardHtml(k) {
    const displayName = k.custom_name || k.name;
    const statusColor = k.status === 'breach' ? 'var(--brand-orange)' : k.status === 'warning' ? '#f59e0b' : 'var(--success,#22c55e)';
    const statusLabel = k.status === 'breach' ? 'BREACH' : k.status === 'warning' ? 'WARNING' : 'NORMAL';
    const dirIcon = k.direction === 'higher_is_better' ? '&#8593;' : '&#8595;';
    const dirTitle = k.direction === 'higher_is_better' ? 'Mayor es mejor' : 'Menor es mejor';
    const valueStr = k.current_value !== null && k.current_value !== undefined
      ? (Number.isInteger(k.current_value) ? k.current_value : k.current_value.toFixed(1))
      : '—';
    const isHidden = !k.is_visible;

    return `
      <div class="kri-card${isHidden ? ' kri-card--hidden' : ''}" style="opacity:${isHidden ? 0.6 : 1}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
          <div>
            <span class="kri-card__name">${UI.esc(displayName)}</span>
            ${k.custom_name ? `<span style="font-size:0.72rem;color:var(--text-muted);margin-left:4px;">(${UI.esc(k.name)})</span>` : ''}
          </div>
          <span class="badge" style="background:${statusColor};color:#fff;flex-shrink:0;">${statusLabel}</span>
        </div>
        ${k.description ? `<div style="font-size:0.78rem;color:var(--text-muted);margin:4px 0 8px;">${UI.esc(k.description)}</div>` : ''}
        <div style="display:flex;gap:16px;margin:10px 0;align-items:center;flex-wrap:wrap;">
          <div style="text-align:center;">
            <div style="font-size:1.5rem;font-weight:700;color:${statusColor};">${valueStr}</div>
            <div style="font-size:0.72rem;color:var(--text-muted);">Valor actual</div>
          </div>
          <div style="font-size:0.82rem;color:var(--text-muted);flex:1;">
            <div title="${dirTitle}" style="margin-bottom:2px;">
              <span style="font-size:1rem;">${dirIcon}</span>
              <span style="font-size:0.78rem;">${dirTitle}</span>
            </div>
            ${k.warning_threshold !== null ? `<div>Aviso: ${k.warning_threshold}</div>` : ''}
            ${k.breach_threshold !== null ? `<div>Breach: ${k.breach_threshold}</div>` : ''}
            ${k.last_evaluated_at ? `<div style="margin-top:4px;">Eval: ${UI.fmtDate(k.last_evaluated_at)}</div>` : ''}
          </div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;">
          <button class="btn btn-ghost btn-sm" data-kri-eval="${k.id}">Evaluar</button>
          <button class="btn btn-ghost btn-sm" data-kri-edit="${k.id}">Editar</button>
          <button class="btn btn-ghost btn-sm" data-kri-hide="${k.id}" data-kri-visible="${k.is_visible}"
            title="${isHidden ? 'Mostrar' : 'Ocultar'}">
            ${isHidden ? 'Mostrar' : 'Ocultar'}
          </button>
          ${!k.is_system ? `<button class="btn btn-ghost btn-sm" style="color:var(--danger,#ef4444);" data-kri-del="${k.id}" data-kri-system="false">Eliminar</button>` : ''}
        </div>
        ${k.is_system ? `<div style="font-size:0.72rem;color:var(--text-muted);margin-top:6px;">Indicador de sistema</div>` : ''}
      </div>
    `;
  },

  async _evalOne(id) {
    try {
      await Api.post(`/api/kris/${id}/evaluate`, {});
      ViewKRIs._reload();
      UI.toast('Evaluacion completada');
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  },

  async _evalAll() {
    const btn = document.getElementById('kri-btn-eval-all');
    if (btn) { btn.disabled = true; btn.textContent = 'Evaluando...'; }
    try {
      const r = await Api.post('/api/kris/evaluate-all', {});
      await ViewKRIs._reload();
      UI.toast(`Evaluados ${r.evaluated}: ${r.normal} normales, ${r.warning} aviso, ${r.breach} breach`);
    } catch (e) {
      UI.toast(e.message, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Evaluar todos'; }
    }
  },

  async _seedKpis() {
    const btn = document.getElementById('kri-btn-seed');
    if (btn) { btn.disabled = true; btn.textContent = 'Inicializando...'; }
    try {
      const r = await Api.post('/api/kris/seed-kpis', {});
      await ViewKRIs._reload();
      UI.toast(`KPIs inicializados. Total: ${r.total_kpis}`);
    } catch (e) {
      UI.toast(e.message, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Inicializar KPIs'; }
    }
  },

  async _toggleVisibility(id, currentlyVisible) {
    try {
      await Api.patch(`/api/kris/${id}`, { is_visible: !currentlyVisible });
      ViewKRIs._reload();
      UI.toast(currentlyVisible ? 'Indicador ocultado' : 'Indicador mostrado');
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  },

  async _delete(id, isSystem) {
    if (isSystem) {
      UI.toast('Los indicadores de sistema no se pueden eliminar. Puedes ocultarlos.', 'error');
      return;
    }
    if (!confirm('Eliminar este indicador?')) return;
    try {
      await Api.delete(`/api/kris/${id}`);
      ViewKRIs._reload();
      UI.toast('Indicador eliminado');
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  },

  async _openModal(id) {
    let kri = null;
    if (id) {
      try { kri = await Api.get(`/api/kris/${id}`); } catch (e) { UI.toast(e.message, 'error'); return; }
    }

    const metricOptions = [
      // KRI
      { v: 'residual_level', l: 'Nivel residual del riesgo', t: 'kri' },
      { v: 'inherent_level', l: 'Nivel inherente del riesgo', t: 'kri' },
      { v: 'open_incidents', l: 'Incidentes abiertos', t: 'kri' },
      { v: 'open_ncs', l: 'No conformidades mayores abiertas', t: 'kri' },
      { v: 'control_maturity', l: 'Madurez media de controles', t: 'kri' },
      { v: 'overdue_tasks', l: 'Tareas de tratamiento vencidas', t: 'kri' },
      // KPI
      { v: 'kpi_treatment_rate', l: 'Tasa de tratamiento riesgos altos (%)', t: 'kpi' },
      { v: 'kpi_mttt', l: 'Tiempo medio de tratamiento (dias)', t: 'kpi' },
      { v: 'kpi_control_coverage', l: 'Cobertura controles ISO 27002 (%)', t: 'kpi' },
      { v: 'kpi_control_maturity_avg', l: 'Madurez media de controles (0-5)', t: 'kpi' },
      { v: 'kpi_policy_review', l: 'Cumplimiento revision politicas (%)', t: 'kpi' },
      { v: 'kpi_nc_closure_rate', l: 'Tasa cierre no conformidades (%)', t: 'kpi' },
      { v: 'kpi_risk_reduction_avg', l: 'Reduccion media del riesgo (%)', t: 'kpi' },
      { v: 'kpi_appetite_compliance', l: 'Conformidad apetito de riesgo (%)', t: 'kpi' },
      { v: 'kpi_asset_coverage', l: 'Cobertura activos evaluados (%)', t: 'kpi' },
      { v: 'kpi_risk_no_owner_rate', l: 'Riesgos sin responsable (%)', t: 'kpi' },
      { v: 'kpi_high_risks_no_plan', l: 'Riesgos altos sin plan (#)', t: 'kpi' },
      { v: 'kpi_nis2_notification_rate', l: 'Tasa notificacion NIS2 (%)', t: 'kpi' },
      { v: 'kpi_bcp_coverage', l: 'Cobertura BCP aprobados (%)', t: 'kpi' },
      { v: 'kpi_mttr_incidents', l: 'MTTR incidentes (dias)', t: 'kpi' },
      { v: 'kpi_supplier_coverage', l: 'Cobertura evaluacion proveedores Tier-1 (%)', t: 'kpi' },
    ];

    const html = `
      <form id="kri-form">
        <div class="form-group">
          <label>Tipo de indicador</label>
          <select id="kri-f-type" ${kri?.is_system ? 'disabled' : ''}>
            <option value="kri" ${(!kri || kri.indicator_type === 'kri') ? 'selected' : ''}>KRI — Indicador de riesgo</option>
            <option value="kpi" ${kri?.indicator_type === 'kpi' ? 'selected' : ''}>KPI — Indicador de rendimiento</option>
          </select>
        </div>
        <div class="form-group">
          <label>Metrica</label>
          <select id="kri-f-metric" ${kri?.is_system ? 'disabled' : ''}>
            ${metricOptions.map(o => `<option value="${o.v}" ${kri?.metric_type === o.v ? 'selected' : ''}>[${o.t.toUpperCase()}] ${o.l}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>Nombre</label>
          <input id="kri-f-name" value="${UI.esc(kri?.name || '')}" placeholder="Nombre del indicador" required>
        </div>
        ${kri ? `
        <div class="form-group">
          <label>Nombre personalizado (opcional)</label>
          <input id="kri-f-custom" value="${UI.esc(kri?.custom_name || '')}" placeholder="Deja vacio para usar el nombre original">
        </div>` : ''}
        <div class="form-group">
          <label>Descripcion / referencia normativa</label>
          <textarea id="kri-f-desc" rows="2" placeholder="ISO 27001 cl.9.1 — ...">${UI.esc(kri?.description || '')}</textarea>
        </div>
        <div class="form-group">
          <label>Direccion</label>
          <select id="kri-f-dir">
            <option value="lower_is_better" ${(!kri || kri.direction === 'lower_is_better') ? 'selected' : ''}>Menor es mejor (ej. incidentes, dias)</option>
            <option value="higher_is_better" ${kri?.direction === 'higher_is_better' ? 'selected' : ''}>Mayor es mejor (ej. % cobertura, madurez)</option>
          </select>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div class="form-group">
            <label>Umbral de aviso</label>
            <input id="kri-f-warn" type="number" step="0.1" value="${kri?.warning_threshold ?? ''}">
          </div>
          <div class="form-group">
            <label>Umbral de breach</label>
            <input id="kri-f-breach" type="number" step="0.1" value="${kri?.breach_threshold ?? ''}">
          </div>
        </div>
        <div class="form-group">
          <label>Email de alerta (opcional)</label>
          <input id="kri-f-email" type="email" value="${UI.esc(kri?.recipient_email || '')}" placeholder="seguridad@empresa.com">
        </div>
        <div style="display:flex;gap:16px;flex-wrap:wrap;">
          <label style="display:flex;gap:6px;align-items:center;">
            <input type="checkbox" id="kri-f-active" ${!kri || kri.is_active ? 'checked' : ''}>
            Activo
          </label>
          <label style="display:flex;gap:6px;align-items:center;">
            <input type="checkbox" id="kri-f-alert" ${!kri || kri.alert_on_breach ? 'checked' : ''}>
            Alertar en breach
          </label>
          <label style="display:flex;gap:6px;align-items:center;">
            <input type="checkbox" id="kri-f-visible" ${!kri || kri.is_visible ? 'checked' : ''}>
            Visible
          </label>
        </div>
      </form>
    `;

    UI.modal({
      title: id ? 'Editar indicador' : 'Nuevo KRI',
      body: html,
      actions: [
        {
          label: id ? 'Guardar' : 'Crear',
          primary: true,
          onclick: async () => {
            await ViewKRIs._save(id, kri);
            return true;
          },
        },
      ],
    });
  },

  async _save(id, existing) {
    const name = document.getElementById('kri-f-name')?.value?.trim();
    if (!name) { UI.toast('El nombre es obligatorio', 'error'); return false; }

    const body = {
      name,
      description: document.getElementById('kri-f-desc')?.value?.trim() || null,
      direction: document.getElementById('kri-f-dir')?.value || 'lower_is_better',
      warning_threshold: parseFloat(document.getElementById('kri-f-warn')?.value) || null,
      breach_threshold: parseFloat(document.getElementById('kri-f-breach')?.value) || null,
      recipient_email: document.getElementById('kri-f-email')?.value?.trim() || null,
      is_active: document.getElementById('kri-f-active')?.checked ?? true,
      alert_on_breach: document.getElementById('kri-f-alert')?.checked ?? true,
      is_visible: document.getElementById('kri-f-visible')?.checked ?? true,
    };

    if (document.getElementById('kri-f-custom')) {
      const cn = document.getElementById('kri-f-custom')?.value?.trim();
      body.custom_name = cn || null;
    }

    try {
      if (id) {
        await Api.patch(`/api/kris/${id}`, body);
        UI.toast('Indicador actualizado');
      } else {
        const metricType = document.getElementById('kri-f-metric')?.value;
        const indicatorType = document.getElementById('kri-f-type')?.value || 'kri';
        await Api.post('/api/kris', { ...body, metric_type: metricType, indicator_type: indicatorType });
        UI.toast('Indicador creado');
      }
      await ViewKRIs._reload();
      return true;
    } catch (e) {
      UI.toast(e.message, 'error');
      return false;
    }
  },
};
