/* Vista KRIs / KPIs — gestion de indicadores clave de riesgo y rendimiento */
const ViewKRIs = {
  _showHidden: false,
  _category: 'all',
  _statusFilter: 'all',

  // Mapa de categoria -> metric_types que pertenecen a ella
  _CATEGORIES: {
    riesgos: [
      'residual_level', 'inherent_level', 'kri_critical_risks', 'kri_stale_risks',
      'kpi_treatment_rate', 'kpi_mttt', 'kpi_risk_reduction_avg',
      'kpi_appetite_compliance', 'kpi_asset_coverage',
      'kpi_risk_no_owner_rate', 'kpi_high_risks_no_plan',
    ],
    controles: [
      'control_maturity', 'overdue_tasks',
      'kpi_control_coverage', 'kpi_control_maturity_avg',
    ],
    tprm: [
      'kri_high_risk_suppliers', 'kpi_supplier_coverage',
      'kpi_supplier_contract_expiry', 'kpi_supplier_critical_issues',
      'kpi_vendor_issue_mttr', 'kpi_dora_suppliers_assessed',
    ],
    bcp: [
      'kpi_bcp_coverage', 'kpi_bcp_rto_achievement',
      'kpi_bcp_test_frequency', 'kpi_critical_processes_bcp',
    ],
    incidentes: [
      'open_incidents', 'open_ncs', 'kri_critical_cves',
      'kpi_mttr_incidents', 'kpi_nis2_notification_rate',
    ],
    cumplimiento: [
      'kpi_policy_review', 'kpi_nc_closure_rate',
    ],
  },

  get _CATEGORY_LABELS() {
    return {
      all: t('kris.cat_all'),
      riesgos: t('kris.cat_riesgos'),
      controles: t('kris.cat_controles'),
      tprm: t('kris.cat_tprm'),
      bcp: t('kris.cat_bcp'),
      incidentes: t('kris.cat_incidentes'),
      cumplimiento: t('kris.cat_cumplimiento'),
    };
  },

  async render(el) {
    el.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px;">
        <h2 style="margin:0;font-size:1.2rem;">${t('kris.title')}</h2>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
          <label style="display:flex;align-items:center;gap:6px;font-size:0.85rem;cursor:pointer;">
            <input type="checkbox" id="kri-show-hidden"> ${t('kris.show_hidden')}
          </label>
          <button class="btn btn-ghost" id="kri-btn-seed" title="${t('kris.seed_hint')}">${t('kris.seed_btn')}</button>
          <button class="btn btn-ghost" id="kri-btn-eval-all">${t('kris.eval_all_btn')}</button>
          <button class="btn btn-primary" id="kri-btn-new">${t('kris.new_btn')}</button>
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

    UI.tabs(document.getElementById('kri-tabs-wrap'), {
      hub: 'kri-inner',
      label: 'KRIs/KPIs',
      tabs: [
        { id: 'kris-tab', label: t('kris.tab_kris'), render: (p) => ViewKRIs._renderList(p, 'kri') },
        { id: 'kpis-tab', label: t('kris.tab_kpis'), render: (p) => ViewKRIs._renderList(p, 'kpi') },
      ],
    });
  },

  async _reload() {
    const panel = document.getElementById('hubpanel-kri-inner');
    if (!panel) return;
    const activeBtn = document.querySelector('#kri-tabs-wrap .hub-tab.active');
    const type = activeBtn && activeBtn.dataset.tab === 'kpis-tab' ? 'kpi' : 'kri';
    await ViewKRIs._renderList(panel, type);
  },

  // Llamados desde onclick inline en los chips de filtro
  _setCategory(cat) {
    ViewKRIs._category = cat;
    ViewKRIs._reload();
  },

  _setStatus(status) {
    ViewKRIs._statusFilter = status;
    ViewKRIs._reload();
  },

  _filterBar(type) {
    const cats = Object.entries(ViewKRIs._CATEGORY_LABELS);
    const statusOpts = [
      { v: 'all', l: t('kris.status_all') },
      { v: 'breach', l: t('kris.status_breach') },
      { v: 'warning', l: t('kris.status_warning') },
      { v: 'normal', l: t('kris.status_normal') },
    ];

    const chipStyle = (active) =>
      `display:inline-block;padding:4px 12px;border-radius:20px;font-size:0.78rem;cursor:pointer;border:1px solid;transition:all .15s;` +
      (active
        ? `background:var(--brand-purple);color:#fff;border-color:var(--brand-purple);`
        : `background:transparent;color:var(--text-muted);border-color:var(--border-color,#ddd);`);

    const statusBadge = (active, v) => {
      const colors = { breach: 'var(--brand-orange)', warning: '#f59e0b', normal: 'var(--success,#22c55e)', all: 'var(--text-muted)' };
      return `display:inline-block;padding:4px 12px;border-radius:20px;font-size:0.78rem;cursor:pointer;border:1px solid;transition:all .15s;` +
        (active
          ? `background:${colors[v]};color:#fff;border-color:${colors[v]};`
          : `background:transparent;color:var(--text-muted);border-color:var(--border-color,#ddd);`);
    };

    return `
      <div id="kri-filters-${type}" style="margin-bottom:14px;">
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:8px;">
          <span style="font-size:0.75rem;color:var(--text-muted);margin-right:4px;white-space:nowrap;">${t('kris.filter_category')}</span>
          ${cats.map(([v, l]) => `
            <span onclick="ViewKRIs._setCategory('${UI.esc(v)}')"
              style="${chipStyle(ViewKRIs._category === v)}">${l}</span>
          `).join('')}
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
          <span style="font-size:0.75rem;color:var(--text-muted);margin-right:4px;white-space:nowrap;">${t('kris.filter_status')}</span>
          ${statusOpts.map(({ v, l }) => `
            <span onclick="ViewKRIs._setStatus('${UI.esc(v)}')"
              style="${statusBadge(ViewKRIs._statusFilter === v, v)}">${l}</span>
          `).join('')}
        </div>
      </div>
    `;
  },

  _applyFilters(items) {
    let result = items;
    if (ViewKRIs._category !== 'all') {
      const allowed = ViewKRIs._CATEGORIES[ViewKRIs._category] || [];
      result = result.filter(k => allowed.includes(k.metric_type));
    }
    if (ViewKRIs._statusFilter !== 'all') {
      result = result.filter(k => k.status === ViewKRIs._statusFilter);
    }
    return result;
  },

  _getCategoryForMetric(metricType) {
    const labels = ViewKRIs._CATEGORY_LABELS;
    for (const [cat, metrics] of Object.entries(ViewKRIs._CATEGORIES)) {
      if (metrics.includes(metricType)) return labels[cat] || cat;
    }
    return t('kris.cat_none');
  },

  async _renderList(el, type) {
    // Actualizar el boton "+ Nuevo" segun la pestana activa
    const newBtn = document.getElementById('kri-btn-new');
    if (newBtn) {
      newBtn.textContent = type === 'kpi' ? t('kris.new_btn_kpi') : t('kris.new_btn');
      newBtn.onclick = () => ViewKRIs._openModal(null, type);
    }

    el.innerHTML = `<div class="notice">${t('kris.loading')}</div>`;
    try {
      const params = new URLSearchParams({ indicator_type: type, active_only: 'false' });
      if (ViewKRIs._showHidden) params.set('show_hidden', 'true');
      const allItems = await Api.get(`/api/kris?${params}`);

      const filtered = ViewKRIs._applyFilters(allItems);
      const totalLabel = filtered.length !== allItems.length
        ? t('kris.count_of', { filtered: filtered.length, total: allItems.length })
        : `${allItems.length}`;

      if (!allItems.length) {
        el.innerHTML = `
          ${ViewKRIs._filterBar(type)}
          <div class="notice">
            ${type === 'kpi' ? t('kris.no_kpis') : t('kris.no_kris')}
            ${type === 'kpi' ? `<br><button class="btn btn-ghost" onclick="ViewKRIs._seedKpis()">${t('kris.seed_hint')}</button>` : ''}
          </div>`;
        return;
      }

      const countLabel = filtered.length !== 1
        ? t('kris.showing_plural', { n: totalLabel })
        : t('kris.showing', { n: totalLabel });

      el.innerHTML = `
        ${ViewKRIs._filterBar(type)}
        <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:10px;">
          ${countLabel}
        </div>
        ${filtered.length
          ? `<div class="kri-grid">${filtered.map(k => ViewKRIs._cardHtml(k)).join('')}</div>`
          : `<div class="notice">${t('kris.none_match')}</div>`
        }
      `;

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
    const _locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
    const displayName = k.custom_name || k.name;
    const statusColor = k.status === 'breach' ? 'var(--brand-orange)' : k.status === 'warning' ? '#f59e0b' : 'var(--success,#22c55e)';
    const statusLabel = k.status === 'breach' ? 'BREACH' : k.status === 'warning' ? 'WARNING' : 'NORMAL';
    const dirIcon = k.direction === 'higher_is_better' ? '&#8593;' : '&#8595;';
    const dirTitle = k.direction === 'higher_is_better' ? t('kris.dir_higher') : t('kris.dir_lower');
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
            <div style="font-size:0.72rem;color:var(--text-muted);">${t('kris.current_value')}</div>
          </div>
          <div style="font-size:0.82rem;color:var(--text-muted);flex:1;">
            <div title="${dirTitle}" style="margin-bottom:2px;">
              <span style="font-size:1rem;">${dirIcon}</span>
              <span style="font-size:0.78rem;">${dirTitle}</span>
            </div>
            ${k.warning_threshold !== null ? `<div>${t('kris.warn_label')} ${k.warning_threshold}</div>` : ''}
            ${k.breach_threshold !== null ? `<div>${t('kris.breach_label')} ${k.breach_threshold}</div>` : ''}
            ${k.last_evaluated_at ? `<div style="margin-top:4px;">${t('kris.eval_label')} ${new Date(k.last_evaluated_at).toLocaleDateString(_locale, { day: '2-digit', month: '2-digit', year: 'numeric' })}</div>` : ''}
          </div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;">
          <button class="btn btn-ghost btn-sm" data-kri-eval="${k.id}">${t('kris.btn_eval')}</button>
          <button class="btn btn-ghost btn-sm" data-kri-edit="${k.id}">${t('kris.btn_edit')}</button>
          <button class="btn btn-ghost btn-sm" data-kri-hide="${k.id}" data-kri-visible="${k.is_visible}"
            title="${isHidden ? t('kris.btn_show') : t('kris.btn_hide')}">
            ${isHidden ? t('kris.btn_show') : t('kris.btn_hide')}
          </button>
          ${!k.is_system ? `<button class="btn btn-ghost btn-sm" style="color:var(--danger,#ef4444);" data-kri-del="${k.id}" data-kri-system="false">${t('kris.btn_delete')}</button>` : ''}
        </div>
        ${k.is_system ? `<div style="font-size:0.72rem;color:var(--text-muted);margin-top:6px;">${t('kris.system_indicator')}</div>` : ''}
      </div>
    `;
  },

  async _evalOne(id) {
    try {
      await Api.post(`/api/kris/${id}/evaluate`, {});
      ViewKRIs._reload();
      UI.toast(t('kris.eval_done'));
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  },

  async _evalAll() {
    const btn = document.getElementById('kri-btn-eval-all');
    if (btn) { btn.disabled = true; btn.textContent = t('kris.eval_all_loading'); }
    try {
      const r = await Api.post('/api/kris/evaluate-all', {});
      await ViewKRIs._reload();
      UI.toast(t('kris.eval_all_done', { evaluated: r.evaluated, normal: r.normal, warning: r.warning, breach: r.breach }));
    } catch (e) {
      UI.toast(e.message, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = t('kris.eval_all_btn'); }
    }
  },

  async _seedKpis() {
    const btn = document.getElementById('kri-btn-seed');
    if (btn) { btn.disabled = true; btn.textContent = t('kris.seed_btn_loading'); }
    try {
      const r = await Api.post('/api/kris/seed-kpis', {});
      await ViewKRIs._reload();
      UI.toast(t('kris.seed_done', { total: r.total_kpis }));
    } catch (e) {
      UI.toast(e.message, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = t('kris.seed_btn'); }
    }
  },

  async _toggleVisibility(id, currentlyVisible) {
    try {
      await Api.patch(`/api/kris/${id}`, { is_visible: !currentlyVisible });
      ViewKRIs._reload();
      UI.toast(currentlyVisible ? t('kris.hidden_ok') : t('kris.shown_ok'));
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  },

  async _delete(id, isSystem) {
    if (isSystem) {
      UI.toast(t('kris.cannot_delete_system'), 'error');
      return;
    }
    if (!await UI.confirm(t('kris.delete_confirm'))) return;
    try {
      await Api.delete(`/api/kris/${id}`);
      ViewKRIs._reload();
      UI.toast(t('kris.deleted_ok'));
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  },

  async _openModal(id, defaultType) {
    // Si no se pasa defaultType, leer la pestana activa
    if (!defaultType) {
      const activeBtn = document.querySelector('#kri-tabs-wrap .hub-tab.active');
      defaultType = activeBtn && activeBtn.dataset.tab === 'kpis-tab' ? 'kpi' : 'kri';
    }

    let kri = null;
    if (id) {
      try { kri = await Api.get(`/api/kris/${id}`); } catch (e) { UI.toast(e.message, 'error'); return; }
    }

    const effectiveType = kri ? kri.indicator_type : defaultType;

    const metricOptions = [
      // KRI
      { v: 'residual_level', l: I18n.lang() === 'en' ? 'Residual risk level' : 'Nivel residual del riesgo', tp: 'kri' },
      { v: 'inherent_level', l: I18n.lang() === 'en' ? 'Inherent risk level' : 'Nivel inherente del riesgo', tp: 'kri' },
      { v: 'open_incidents', l: I18n.lang() === 'en' ? 'Open incidents' : 'Incidentes abiertos', tp: 'kri' },
      { v: 'open_ncs', l: I18n.lang() === 'en' ? 'Open major non-conformities' : 'No conformidades mayores abiertas', tp: 'kri' },
      { v: 'control_maturity', l: I18n.lang() === 'en' ? 'Average control maturity' : 'Madurez media de controles', tp: 'kri' },
      { v: 'overdue_tasks', l: I18n.lang() === 'en' ? 'Overdue treatment tasks' : 'Tareas de tratamiento vencidas', tp: 'kri' },
      { v: 'kri_critical_risks', l: I18n.lang() === 'en' ? 'Active critical risks (#)' : 'Riesgos criticos activos (#)', tp: 'kri' },
      { v: 'kri_stale_risks', l: I18n.lang() === 'en' ? 'Risks unreviewed >90 days (#)' : 'Riesgos sin revisar >90 dias (#)', tp: 'kri' },
      { v: 'kri_critical_cves', l: I18n.lang() === 'en' ? 'Unremediated critical/high CVEs (#)' : 'CVEs criticos/altos sin remediar (#)', tp: 'kri' },
      { v: 'kri_high_risk_suppliers', l: I18n.lang() === 'en' ? 'Tier-1/2 suppliers with high risk (#)' : 'Proveedores Tier-1/2 con riesgo alto (#)', tp: 'kri' },
      // KPI
      { v: 'kpi_treatment_rate', l: I18n.lang() === 'en' ? 'High risk treatment rate (%)' : 'Tasa de tratamiento riesgos altos (%)', tp: 'kpi' },
      { v: 'kpi_mttt', l: I18n.lang() === 'en' ? 'Mean time to treat (days)' : 'Tiempo medio de tratamiento (dias)', tp: 'kpi' },
      { v: 'kpi_control_coverage', l: I18n.lang() === 'en' ? 'ISO 27002 control coverage (%)' : 'Cobertura controles ISO 27002 (%)', tp: 'kpi' },
      { v: 'kpi_control_maturity_avg', l: I18n.lang() === 'en' ? 'Average control maturity (0-5)' : 'Madurez media de controles (0-5)', tp: 'kpi' },
      { v: 'kpi_policy_review', l: I18n.lang() === 'en' ? 'Policy review compliance (%)' : 'Cumplimiento revision politicas (%)', tp: 'kpi' },
      { v: 'kpi_nc_closure_rate', l: I18n.lang() === 'en' ? 'Non-conformity closure rate (%)' : 'Tasa cierre no conformidades (%)', tp: 'kpi' },
      { v: 'kpi_risk_reduction_avg', l: I18n.lang() === 'en' ? 'Average risk reduction (%)' : 'Reduccion media del riesgo (%)', tp: 'kpi' },
      { v: 'kpi_appetite_compliance', l: I18n.lang() === 'en' ? 'Risk appetite compliance (%)' : 'Conformidad apetito de riesgo (%)', tp: 'kpi' },
      { v: 'kpi_asset_coverage', l: I18n.lang() === 'en' ? 'Assessed assets coverage (%)' : 'Cobertura activos evaluados (%)', tp: 'kpi' },
      { v: 'kpi_risk_no_owner_rate', l: I18n.lang() === 'en' ? 'Risks without owner (%)' : 'Riesgos sin responsable (%)', tp: 'kpi' },
      { v: 'kpi_high_risks_no_plan', l: I18n.lang() === 'en' ? 'High risks without plan (#)' : 'Riesgos altos sin plan (#)', tp: 'kpi' },
      { v: 'kpi_nis2_notification_rate', l: I18n.lang() === 'en' ? 'NIS2 notification rate (%)' : 'Tasa notificacion NIS2 (%)', tp: 'kpi' },
      { v: 'kpi_bcp_coverage', l: I18n.lang() === 'en' ? 'Approved BCP coverage (%)' : 'Cobertura BCP aprobados (%)', tp: 'kpi' },
      { v: 'kpi_mttr_incidents', l: I18n.lang() === 'en' ? 'Incident MTTR (days)' : 'MTTR incidentes (dias)', tp: 'kpi' },
      { v: 'kpi_supplier_coverage', l: I18n.lang() === 'en' ? 'Tier-1 supplier assessment coverage (%)' : 'Cobertura evaluacion proveedores Tier-1 (%)', tp: 'kpi' },
    ];

    // Metrica por defecto: primera que coincide con el tipo activo
    const defaultMetric = kri
      ? kri.metric_type
      : (metricOptions.find(o => o.tp === effectiveType) || metricOptions[0]).v;

    const initialCategory = ViewKRIs._getCategoryForMetric(defaultMetric);

    const html = `
      <form id="kri-form">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div class="form-group">
            <label>${t('kris.form_type')}</label>
            <select id="kri-f-type" ${kri?.is_system ? 'disabled' : ''}>
              <option value="kri" ${effectiveType === 'kri' ? 'selected' : ''}>${t('kris.types.kri')}</option>
              <option value="kpi" ${effectiveType === 'kpi' ? 'selected' : ''}>${t('kris.types.kpi')}</option>
            </select>
          </div>
          <div class="form-group">
            <label>${t('kris.form_category')}
              <span style="font-size:0.72rem;color:var(--text-muted);font-weight:400;"> — ${t('kris.form_category_hint')}</span>
            </label>
            <div id="kri-cat-display" style="padding:7px 10px;background:var(--bg-2,#f5f5f5);border-radius:6px;font-size:0.85rem;border:1px solid var(--border-color,#ddd);">
              ${initialCategory}
            </div>
          </div>
        </div>
        <div class="form-group">
          <label>${t('kris.form_metric')}</label>
          <select id="kri-f-metric" ${kri?.is_system ? 'disabled' : ''}>
            ${metricOptions.map(o => `<option value="${o.v}" ${(kri?.metric_type ?? defaultMetric) === o.v ? 'selected' : ''}>[${o.tp.toUpperCase()}] ${o.l}</option>`).join('')}
          </select>
        </div>
        <div class="form-group">
          <label>${t('kris.form_name')}</label>
          <input id="kri-f-name" value="${UI.esc(kri?.name || '')}" placeholder="${t('kris.form_name_placeholder')}" required>
        </div>
        ${kri ? `
        <div class="form-group">
          <label>${t('kris.form_custom_name')}</label>
          <input id="kri-f-custom" value="${UI.esc(kri?.custom_name || '')}" placeholder="${t('kris.form_custom_placeholder')}">
        </div>` : ''}
        <div class="form-group">
          <label>${t('kris.form_desc')}</label>
          <textarea id="kri-f-desc" rows="2" placeholder="ISO 27001 cl.9.1 — ...">${UI.esc(kri?.description || '')}</textarea>
        </div>
        <div class="form-group">
          <label>${t('kris.form_direction')}</label>
          <select id="kri-f-dir">
            <option value="lower_is_better" ${(!kri || kri.direction === 'lower_is_better') ? 'selected' : ''}>${t('kris.dir_lower_opt')}</option>
            <option value="higher_is_better" ${kri?.direction === 'higher_is_better' ? 'selected' : ''}>${t('kris.dir_higher_opt')}</option>
          </select>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div class="form-group">
            <label>${t('kris.form_warn_threshold')}</label>
            <input id="kri-f-warn" type="number" step="0.1" value="${kri?.warning_threshold ?? ''}">
          </div>
          <div class="form-group">
            <label>${t('kris.form_breach_threshold')}</label>
            <input id="kri-f-breach" type="number" step="0.1" value="${kri?.breach_threshold ?? ''}">
          </div>
        </div>
        <div class="form-group">
          <label>${t('kris.form_email')}</label>
          <input id="kri-f-email" type="email" value="${UI.esc(kri?.recipient_email || '')}" placeholder="${t('kris.form_email_placeholder')}">
        </div>
        <div style="display:flex;gap:16px;flex-wrap:wrap;">
          <label style="display:flex;gap:6px;align-items:center;">
            <input type="checkbox" id="kri-f-active" ${!kri || kri.is_active ? 'checked' : ''}>
            ${t('kris.form_active')}
          </label>
          <label style="display:flex;gap:6px;align-items:center;">
            <input type="checkbox" id="kri-f-alert" ${!kri || kri.alert_on_breach ? 'checked' : ''}>
            ${t('kris.form_alert_breach')}
          </label>
          <label style="display:flex;gap:6px;align-items:center;">
            <input type="checkbox" id="kri-f-visible" ${!kri || kri.is_visible ? 'checked' : ''}>
            ${t('kris.form_visible')}
          </label>
        </div>
      </form>
    `;

    const modalTitle = id
      ? t('kris.modal_edit_title')
      : (effectiveType === 'kpi' ? t('kris.modal_new_kpi_title') : t('kris.modal_new_title'));

    UI.modal(
      modalTitle,
      html,
      {
        actions: `
          <button class="btn btn-ghost" onclick="UI.closeModal()">${t('common.cancel')}</button>
          <button class="btn btn-primary" id="kri-modal-save">${id ? t('common.save') : t('common.create')}</button>
        `,
      }
    );

    // Actualizar categoria al cambiar la metrica
    const metricSel = document.getElementById('kri-f-metric');
    if (metricSel) {
      metricSel.onchange = () => {
        const catDisplay = document.getElementById('kri-cat-display');
        if (catDisplay) catDisplay.textContent = ViewKRIs._getCategoryForMetric(metricSel.value);
      };
    }

    document.getElementById('kri-modal-save').onclick = async () => {
      const ok = await ViewKRIs._save(id, kri);
      if (ok) UI.closeModal();
    };
  },

  async _save(id, existing) {
    const name = document.getElementById('kri-f-name')?.value?.trim();
    if (!name) { UI.toast(t('kris.name_required'), 'error'); return false; }

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
        UI.toast(t('kris.updated_ok'));
      } else {
        const metricType = document.getElementById('kri-f-metric')?.value;
        const indicatorType = document.getElementById('kri-f-type')?.value || 'kri';
        await Api.post('/api/kris', { ...body, metric_type: metricType, indicator_type: indicatorType });
        UI.toast(t('kris.created_ok'));
      }
      await ViewKRIs._reload();
      return true;
    } catch (e) {
      UI.toast(e.message, 'error');
      return false;
    }
  },
};
