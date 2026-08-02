/* Vista de gestión de proveedores / supply chain risk (NIS2 Art. 21.2.d). */
const ViewSuppliers = (() => {

  function RISK_LABELS() {
    return {
      low:      window.t('suppliers.tier.low'),
      medium:   window.t('suppliers.tier.medium'),
      high:     window.t('suppliers.tier.high'),
      critical: window.t('suppliers.tier.critical'),
    };
  }
  const RISK_COLORS = {
    low: 'var(--risk-low)', medium: 'var(--risk-medium)',
    high: 'var(--risk-high)', critical: 'var(--risk-critical)',
  };

  function _rlBands() {
    return window.RiskLevels ? RiskLevels.all() : [
      { code: 'low',      label: t('common.low'),    color: 'var(--risk-low)'      },
      { code: 'medium',   label: t('common.medium'),   color: 'var(--risk-medium)'   },
      { code: 'high',     label: t('common.high'),    color: 'var(--risk-high)'     },
      { code: 'critical', label: t('common.critical'), color: 'var(--risk-critical)' },
    ];
  }
  function _rlLabel(code) {
    const b = _rlBands().find(x => x.code === code);
    return b ? b.label : (RISK_LABELS()[code] || code);
  }
  function _rlColor(code) {
    const b = _rlBands().find(x => x.code === code);
    return b ? b.color : (RISK_COLORS[code] || '#888');
  }

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  // ── Suppliers Module Review: clasificaciones del cliente (puntos 2/5/6/18) ──
  // Etiquetas en es-ES inline (consistente con el resto de la vista; i18n en punto 16).
  const BIZ_IMPORTANCE = {
    not_relevant: { label: 'No relevante', color: '#94a3b8' },
    normal:       { label: 'Normal',       color: '#3b82f6' },
    important:    { label: 'Importante',   color: '#f59e0b' },
    critical:     { label: 'Crítico',      color: '#dc2626' },
  };
  const SEC_RISK = {
    very_low: { label: 'Muy bajo', color: '#16a34a' },
    low:      { label: 'Bajo',     color: '#65a30d' },
    medium:   { label: 'Medio',    color: '#f59e0b' },
    high:     { label: 'Alto',     color: '#ea580c' },
    critical: { label: 'Crítico',  color: '#dc2626' },
  };
  const REVIEW_FREQ = {
    monthly: 'Mensual', quarterly: 'Trimestral', semiannual: 'Semestral',
    annual: 'Anual', biennial: 'Bienal', none: 'Sin revisión',
  };
  const REVIEW_STATUS = {
    active:         { label: 'Activo',            color: '#16a34a' },
    review_due_90:  { label: 'Revisión en 90 días', color: '#3b82f6' },
    review_due_60:  { label: 'Revisión en 60 días', color: '#f59e0b' },
    review_due_30:  { label: 'Revisión en 30 días', color: '#ea580c' },
    under_review:   { label: 'En revisión',       color: '#8b5cf6' },
    review_overdue: { label: 'Revisión vencida',  color: '#dc2626' },
  };
  const SEC_STATUS = {
    draft:                             { label: 'Borrador',                    color: '#94a3b8' },
    pending_supplier_response:         { label: 'Pendiente respuesta proveedor', color: '#3b82f6' },
    pending_security_review:           { label: 'Pendiente revisión seguridad',  color: '#8b5cf6' },
    pending_additional_info:           { label: 'Pendiente info adicional',      color: '#f59e0b' },
    security_approved:                 { label: 'Aprobado por seguridad',        color: '#16a34a' },
    security_approved_with_mitigation: { label: 'Aprobado con mitigación',       color: '#65a30d' },
    risk_accepted:                     { label: 'Riesgo aceptado',               color: '#0891b2' },
    rejected:                          { label: 'Rechazado',                     color: '#dc2626' },
    offboarded:                        { label: 'Dado de baja',                  color: '#64748b' },
  };
  const AGREEMENT_STATUS = {
    none: 'Sin acuerdo', draft: 'Borrador', pending_signature: 'Pendiente firma',
    signed: 'Firmado', expired: 'Expirado',
  };
  const NEXT_ACTION = {
    internal: { label: 'Nosotros', color: '#8b5cf6' },
    supplier: { label: 'Proveedor', color: '#3b82f6' },
    security: { label: 'Seguridad', color: '#ea580c' },
    none:     { label: '—', color: '#94a3b8' },
  };

  function _enumBadge(map, code) {
    const e = map[code];
    if (!e) return '<span style="color:var(--text-muted);">-</span>';
    return _badge(e.label, e.color);
  }
  function _selOptions(map, selected) {
    return `<option value="">- Sin definir -</option>` + Object.entries(map).map(([k, val]) =>
      `<option value="${k}" ${selected === k ? 'selected' : ''}>${UI.esc(val.label || val)}</option>`
    ).join('');
  }

  // ── Dashboard editable ────────────────────────────────────────────────────
  function _SUP_WIDGETS() {
    return [
      { id: 'total',    label: window.t('suppliers.widget_total'),   def: true },
      { id: 'active',   label: window.t('suppliers.widget_active'),  def: true },
      { id: 'critical', label: window.t('suppliers.widget_critical'),def: true },
      { id: 'overdue',  label: window.t('suppliers.widget_overdue'), def: true },
      { id: 'score',    label: window.t('suppliers.widget_score'),   def: false },
      { id: 'pending',  label: window.t('suppliers.widget_pending'), def: false },
    ];
  }

  function _supDashPrefKey() {
    const u = Auth.user();
    return 'riskhub_dash_suppliers_' + (u?.id || 'default');
  }

  function _supDashPrefs() {
    try { return JSON.parse(localStorage.getItem(_supDashPrefKey()) || '{}'); } catch (_) { return {}; }
  }

  function _isWidgetVisible(prefs, w) {
    return prefs[w.id] !== undefined ? prefs[w.id] : w.def;
  }

  function _openSupDashEditor() {
    const prefs = _supDashPrefs();
    const rows = _SUP_WIDGETS().map(w => {
      const on = _isWidgetVisible(prefs, w);
      return `<label style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);cursor:pointer;">
        <input type="checkbox" data-sup-wid="${w.id}" ${on ? 'checked' : ''} style="accent-color:var(--brand-purple);width:16px;height:16px;">
        <span style="font-size:13px;">${w.label}</span>
      </label>`;
    }).join('');
    UI.modal(
      window.t('suppliers.dashboard_title'),
      `<div style="padding:4px 0;">${rows}</div>`,
      {
        width: '400px',
        actions: `<button class="btn btn-primary" id="sup-dash-save">${window.t('suppliers.dashboard_save')}</button>
                  <button class="btn" id="sup-dash-reset">${window.t('suppliers.dashboard_reset')}</button>
                  <button class="btn" id="sup-dash-cancel">${window.t('suppliers.dashboard_cancel')}</button>`,
      }
    );
    document.getElementById('sup-dash-save').onclick = () => {
      const newPrefs = {};
      _SUP_WIDGETS().forEach(w => {
        const el = document.querySelector(`[data-sup-wid="${w.id}"]`);
        if (el) newPrefs[w.id] = el.checked;
      });
      localStorage.setItem(_supDashPrefKey(), JSON.stringify(newPrefs));
      UI.closeModal();
      _loadStats();
    };
    document.getElementById('sup-dash-reset').onclick = () => {
      localStorage.removeItem(_supDashPrefKey());
      UI.closeModal();
      _loadStats();
    };
    document.getElementById('sup-dash-cancel').onclick = UI.closeModal;
  }

  let _activeSupTab = 'suppliers';
  let _selectedIds = new Set();

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${window.t('suppliers.page_title')}</h1>
          <p class="page-sub">${window.t('suppliers.page_sub')}</p>
        </div>
        <div style="display:flex;gap:8px;" id="sup-header-actions"></div>
      </div>

      <div class="stats-row" id="sup-stats" style="margin-bottom:16px;"></div>

      <div style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:16px;flex-wrap:wrap;">
        <button class="tab-btn" id="suptab-suppliers" onclick="SupTab('suppliers')">${window.t('suppliers.tab_suppliers')}</button>
        <button class="tab-btn" id="suptab-questionnaires" onclick="SupTab('questionnaires')">${window.t('suppliers.tab_questionnaires')}</button>
        <button class="tab-btn" id="suptab-schedules" onclick="SupTab('schedules')">${window.t('suppliers.tab_schedules')}</button>
        <button class="tab-btn" id="suptab-flows" onclick="SupTab('flows')">${window.t('suppliers.tab_flows')}</button>
      </div>
      <div id="sup-tab-content"></div>
    `;

    window.SupTab = function(t) { _setSupTab(t); };

    await _loadStats();
    _setSupTab(_activeSupTab);
  }

  function _setSupTab(tab) {
    _activeSupTab = tab;
    ['suppliers','questionnaires','schedules','flows'].forEach(t => {
      const btn = document.getElementById('suptab-' + t);
      if (!btn) return;
      btn.style.cssText = `padding:8px 20px;font-size:13px;font-weight:600;border:none;
        background:none;cursor:pointer;border-bottom:3px solid ${t===tab?'var(--brand-purple)':'transparent'};
        color:${t===tab?'var(--brand-purple)':'var(--text-muted)'};margin-bottom:-2px;`;
    });
    const actions = document.getElementById('sup-header-actions');
    if (actions) {
      if (tab === 'suppliers') {
        actions.innerHTML = (Auth.canEdit() ? `<button class="btn" id="btn-tprm-settings" title="Configuración del módulo">⚙ Configuración</button> ` : '')
          + (Auth.canEdit() ? `<button class="btn" id="btn-import-sup">${window.t('suppliers.import_btn')}</button> ` : '')
          + `<button class="btn btn-primary" id="btn-new-sup">${window.t('suppliers.new_btn')}</button>`;
        document.getElementById('btn-new-sup').onclick = () => _openForm(null);
        const impBtn = document.getElementById('btn-import-sup');
        if (impBtn) impBtn.onclick = () => _openImport();
        const cfgBtn = document.getElementById('btn-tprm-settings');
        if (cfgBtn) cfgBtn.onclick = () => _openTprmSettings();
      } else if (tab === 'questionnaires') {
        actions.innerHTML = Auth.canEdit() ? `<button class="btn btn-primary" id="btn-new-seq">${window.t('suppliers.new_questionnaire_btn')}</button>` : '';
        if (Auth.canEdit()) document.getElementById('btn-new-seq').onclick = () => _openSeqForm(null);
      } else if (tab === 'schedules') {
        actions.innerHTML = Auth.canEdit() ? `<button class="btn btn-primary" id="btn-new-sched">${window.t('suppliers.new_schedule_btn')}</button>` : '';
        if (Auth.canEdit()) document.getElementById('btn-new-sched').onclick = () => _openScheduleForm(null);
      } else if (tab === 'flows') {
        actions.innerHTML = Auth.canEdit() ? `<button class="btn btn-primary" id="btn-new-flow">${window.t('suppliers.new_flow_btn')}</button>` : '';
        if (Auth.canEdit()) document.getElementById('btn-new-flow').onclick = () => _openFlowForm(null);
      } else {
        actions.innerHTML = '';
      }
    }
    _selectedIds.clear();
    if (tab === 'suppliers') _renderSuppliersTab();
    else if (tab === 'questionnaires') _renderQuestionnairesTab();
    else if (tab === 'schedules') _renderSchedulesTab();
    else if (tab === 'flows') _renderFlowsTab();
  }

  async function _renderSuppliersTab() {
    const wrap = document.getElementById('sup-tab-content');
    wrap.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap;align-items:center;">
        <select id="f-risk" class="input" style="width:150px;">
          <option value="">${window.t('suppliers.filter_all_levels')}</option>
          ${_rlBands().slice().reverse().map(b => `<option value="${b.code}">${UI.esc(b.label)}</option>`).join('')}
        </select>
        <select id="f-critical" class="input" style="width:150px;">
          <option value="">${window.t('suppliers.filter_all')}</option>
          <option value="1">${window.t('suppliers.filter_only_critical')}</option>
          <option value="0">${window.t('suppliers.filter_not_critical')}</option>
        </select>
        <input id="f-q" class="input" placeholder="${window.t('suppliers.filter_search_placeholder')}" style="width:210px;">
        <button id="btn-adv-filter" class="btn btn-sm" style="margin-left:auto;">${window.t('suppliers.filter_advanced')}</button>
      </div>
      <div id="sup-adv-filter" style="display:none;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:10px;">
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;">
          <div><label style="font-size:12px;">${window.t('suppliers.filter_location')}</label><input id="f-adv-location" class="input" placeholder="Madrid, ES"></div>
          <div><label style="font-size:12px;">${window.t('suppliers.filter_dept')}</label><input id="f-adv-dept" class="input" placeholder="TI, Legal..."></div>
          <div><label style="font-size:12px;">${window.t('suppliers.filter_importance')}</label>
            <select id="f-adv-imp" class="input">
              <option value="">${window.t('suppliers.filter_any')}</option>
              <option value="1">1+</option><option value="2">2+</option>
              <option value="3">3+</option><option value="4">4+</option><option value="5">5</option>
            </select>
          </div>
          <div><label style="font-size:12px;">${window.t('suppliers.filter_relation')}</label>
            <select id="f-adv-rel" class="input">
              <option value="">${window.t('suppliers.filter_any_status')}</option>
              <option value="active">${window.t('suppliers.lifecycle_active')}</option>
              <option value="onboarding">${window.t('suppliers.lifecycle_onboarding')}</option>
              <option value="offboarding">${window.t('suppliers.lifecycle_offboarding')}</option>
              <option value="suspended">${window.t('suppliers.filter_suspended')}</option>
              <option value="terminated">${window.t('suppliers.lifecycle_terminated')}</option>
            </select>
          </div>
          <div><label style="font-size:12px;">Importancia de negocio</label>
            <select id="f-adv-biz-imp" class="input"><option value="">Cualquiera</option>${Object.entries(BIZ_IMPORTANCE).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('')}</select>
          </div>
          <div><label style="font-size:12px;">Riesgo de seguridad</label>
            <select id="f-adv-sec-risk" class="input"><option value="">Cualquiera</option>${Object.entries(SEC_RISK).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('')}</select>
          </div>
          <div><label style="font-size:12px;">Estado de seguridad</label>
            <select id="f-adv-sec-status" class="input"><option value="">Cualquiera</option>${Object.entries(SEC_STATUS).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('')}</select>
          </div>
          <div><label style="font-size:12px;">Estado de revisión</label>
            <select id="f-adv-review-status" class="input"><option value="">Cualquiera</option>${Object.entries(REVIEW_STATUS).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join('')}</select>
          </div>
          <div><label style="font-size:12px;">Región operativa</label>
            <select id="f-adv-region" class="input"><option value="">Cualquiera</option></select>
          </div>
        </div>
        <div style="margin-top:8px;display:flex;gap:8px;">
          <button id="btn-adv-apply" class="btn btn-sm btn-primary">${window.t('suppliers.filter_apply')}</button>
          <button id="btn-adv-clear" class="btn btn-sm">${window.t('suppliers.filter_clear')}</button>
        </div>
      </div>
      <div id="sup-table-wrap"></div>
    `;
    document.getElementById('f-risk').onchange = _refresh;
    document.getElementById('f-critical').onchange = _refresh;
    let debounce;
    document.getElementById('f-q').oninput = () => { clearTimeout(debounce); debounce = setTimeout(_refresh, 300); };

    const advBtn = document.getElementById('btn-adv-filter');
    const advPanel = document.getElementById('sup-adv-filter');
    advBtn.onclick = () => {
      const open = advPanel.style.display !== 'none';
      advPanel.style.display = open ? 'none' : 'block';
      advBtn.textContent = open ? 'Filtros avanzados' : 'Ocultar filtros';
    };
    document.getElementById('btn-adv-apply').onclick = _refresh;
    document.getElementById('btn-adv-clear').onclick = () => {
      ['f-adv-location','f-adv-dept','f-adv-imp','f-adv-rel','f-adv-biz-imp',
       'f-adv-sec-risk','f-adv-sec-status','f-adv-review-status','f-adv-region'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      _refresh();
    };
    // Poblar el select de region con la config del modulo (punto 4)
    Api.tprm.getSettings().then(cfg => {
      const sel = document.getElementById('f-adv-region');
      if (sel && cfg.operating_regions) {
        cfg.operating_regions.forEach(r => {
          const o = document.createElement('option'); o.value = r; o.textContent = r; sel.appendChild(o);
        });
      }
    }).catch(() => {});
    await _refresh();
  }

  async function _loadStats() {
    const wrap = document.getElementById('sup-stats');
    if (!wrap) return;
    try {
      const s = await Api.suppliers.summary();
      const prefs = _supDashPrefs();
      const show = (id) => _isWidgetVisible(prefs, _SUP_WIDGETS().find(w => w.id === id));
      const cards = [];
      if (show('total'))
        cards.push(`<div class="stat-card"><div class="stat-value">${s.total}</div><div class="stat-label">${t('suppliers.widget_total')}</div></div>`);
      if (show('active'))
        cards.push(`<div class="stat-card"><div class="stat-value" style="color:#16a34a;">${s.active ?? s.total}</div><div class="stat-label">${t('suppliers.widget_active')}</div></div>`);
      if (show('critical'))
        cards.push(`<div class="stat-card"><div class="stat-value" style="color:var(--risk-critical);">${s.critical_or_high}</div><div class="stat-label">${t('suppliers.widget_critical')}</div></div>`);
      if (show('overdue'))
        cards.push(`<div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.overdue_assessment}</div><div class="stat-label">${t('suppliers.widget_overdue')}</div></div>`);
      if (show('score'))
        cards.push(`<div class="stat-card"><div class="stat-value">${s.avg_score != null ? s.avg_score : '—'}</div><div class="stat-label">${t('suppliers.widget_score')}</div></div>`);
      if (show('pending'))
        cards.push(`<div class="stat-card"><div class="stat-value" style="color:var(--brand-purple);">${s.pending_questionnaires ?? 0}</div><div class="stat-label">Cuest. pendientes</div></div>`);
      wrap.innerHTML = cards.join('')
        + `<button onclick="ViewSuppliers.openDashEditor()" title="Personalizar dashboard"
            style="margin-left:auto;padding:6px 10px;border:1px solid var(--border);border-radius:6px;
                   background:none;cursor:pointer;color:var(--text-muted);font-size:18px;line-height:1;
                   display:flex;align-items:center;">&#9881;</button>`;
    } catch (_) {
      wrap.innerHTML = '';
    }
  }

  async function _refresh() {
    const riskLevel = document.getElementById('f-risk')?.value || '';
    const criticalFilter = document.getElementById('f-critical')?.value || '';
    const q = document.getElementById('f-q')?.value.trim() || '';
    const advLocation = document.getElementById('f-adv-location')?.value.trim().toLowerCase() || '';
    const advDept = document.getElementById('f-adv-dept')?.value.trim().toLowerCase() || '';
    const advImp = document.getElementById('f-adv-imp')?.value || '';
    const advRel = document.getElementById('f-adv-rel')?.value || '';
    const advBizImp = document.getElementById('f-adv-biz-imp')?.value || '';
    const advSecRisk = document.getElementById('f-adv-sec-risk')?.value || '';
    const advSecStatus = document.getElementById('f-adv-sec-status')?.value || '';
    const advReviewStatus = document.getElementById('f-adv-review-status')?.value || '';
    const advRegion = document.getElementById('f-adv-region')?.value || '';
    const wrap = document.getElementById('sup-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<p class="text-muted">Cargando...</p>';
    try {
      const params = {};
      if (riskLevel) params.risk_level = riskLevel;
      if (q) params.q = q;
      if (advBizImp) params.business_importance_level = advBizImp;
      if (advSecRisk) params.security_risk_level = advSecRisk;
      if (advSecStatus) params.security_status = advSecStatus;
      if (advReviewStatus) params.review_status = advReviewStatus;
      if (advRegion) params.operating_region = advRegion;
      let data = await Api.suppliers.list(params);
      if (criticalFilter === '1') data = data.filter(s => s.is_critical);
      else if (criticalFilter === '0') data = data.filter(s => !s.is_critical);
      if (advLocation) data = data.filter(s => (s.location || '').toLowerCase().includes(advLocation));
      if (advDept) data = data.filter(s => (s.department || '').toLowerCase().includes(advDept));
      if (advImp) data = data.filter(s => (s.business_importance || 0) >= parseInt(advImp));
      if (advRel) data = data.filter(s => s.relationship_status === advRel);
      _renderTable(wrap, data);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _updateBulkBar() {
    const bar = document.getElementById('sup-bulk-bar');
    if (!bar) return;
    const n = _selectedIds.size;
    bar.style.display = n > 0 ? 'flex' : 'none';
    const countEl = document.getElementById('sup-sel-count');
    if (countEl) countEl.textContent = `${n} seleccionado${n !== 1 ? 's' : ''}`;
  }

  async function _bulkRecompute() {
    const ids = [..._selectedIds];
    if (!ids.length) return;
    try {
      const r = await Api.suppliers.bulkRecompute(ids);
      UI.toast(t('suppliers.suppliers_recalculated', {n: r.recomputed}), 'success');
      _selectedIds.clear();
      await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  async function _bulkDelete() {
    const ids = [..._selectedIds];
    if (!ids.length) return;
    if (!confirm(t('suppliers.confirm_delete_n', {n: ids.length}))) return;
    try {
      const r = await Api.suppliers.bulkDelete(ids);
      UI.toast(t('suppliers.suppliers_deleted', {n: r.deleted}), 'success');
      _selectedIds.clear();
      await _loadStats();
      await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  function _renderTable(wrap, data) {
    if (!data.length) {
      wrap.innerHTML = `<p class="text-muted" style="margin-top:24px;text-align:center;">${t('suppliers.no_suppliers_found')}</p>`;
      return;
    }
    const canEdit = Auth.canEdit();
    const rows = data.map(s => {
      const assessed = s.last_assessment_at ? s.last_assessment_at.slice(0, 10) : '-';
      const next = s.next_assessment_at ? s.next_assessment_at.slice(0, 10) : '-';
      const tier = s.tier ? _badge(RISK_LABELS()[s.tier] || s.tier, RISK_COLORS[s.tier] || '#888') : '-';
      const inh = (s.inherent_risk_score ?? null) !== null ? s.inherent_risk_score : '-';
      const res = (s.residual_risk_score ?? null) !== null ? s.residual_risk_score : '-';
      const checked = _selectedIds.has(s.id) ? 'checked' : '';
      const critBadge = s.is_critical
        ? `<span style="display:inline-block;padding:2px 7px;border-radius:999px;font-size:10px;font-weight:700;background:#DC2626;color:#fff;">CRÍTICO</span>`
        : `<span style="display:inline-block;padding:2px 7px;border-radius:999px;font-size:10px;font-weight:600;background:var(--bg-2);color:var(--text-muted);border:1px solid var(--border);">Normal</span>`;
      const bizImp = s.business_importance_level ? _enumBadge(BIZ_IMPORTANCE, s.business_importance_level) : '<span style="color:var(--text-muted);">-</span>';
      const secRisk = s.security_risk_level ? _enumBadge(SEC_RISK, s.security_risk_level) : '<span style="color:var(--text-muted);">-</span>';
      const secStatus = s.security_status ? _enumBadge(SEC_STATUS, s.security_status) : '<span style="color:var(--text-muted);">-</span>';
      const nextAction = (s.next_action_owner && s.next_action_owner !== 'none' && NEXT_ACTION[s.next_action_owner])
        ? `<div style="font-size:9px;color:var(--text-muted);margin-top:2px;">→ ${NEXT_ACTION[s.next_action_owner].label}</div>` : '';
      const revBadge = (s.review_status && s.review_status !== 'active' && REVIEW_STATUS[s.review_status])
        ? `<div style="margin-top:3px;">${_badge(REVIEW_STATUS[s.review_status].label, REVIEW_STATUS[s.review_status].color)}</div>` : '';
      return `
        <tr>
          <td style="width:36px;text-align:center;">
            <input type="checkbox" class="sup-chk" data-id="${s.id}" ${checked}
              style="width:15px;height:15px;cursor:pointer;accent-color:var(--brand-purple);">
          </td>
          <td><b>${UI.esc(s.code)}</b></td>
          <td><span data-id="${s.id}" data-action="file" style="cursor:pointer;color:var(--brand-purple);font-weight:600;">${UI.esc(s.name)}</span></td>
          <td>${critBadge}</td>
          <td>${bizImp}</td>
          <td>${secRisk}</td>
          <td>${secStatus}${nextAction}</td>
          <td>${tier}</td>
          <td style="text-align:center;font-weight:700;">${inh}</td>
          <td style="text-align:center;font-weight:700;">${res}</td>
          <td>${assessed}</td>
          <td>${next}${revBadge}</td>
          <td>
            ${canEdit ? `<button class="btn btn-sm" data-id="${s.id}" data-action="recompute" title="Recalcular tier y riesgo">Recalcular</button>` : ''}
            <button class="btn btn-sm" data-id="${s.id}" data-action="edit">Editar</button>
            ${canEdit ? `<button class="btn btn-sm" data-id="${s.id}" data-action="ai" title="Asistente IA (clasificar, analizar, revisar)">IA</button>` : ''}
            <button class="btn btn-sm" data-id="${s.id}" data-name="${UI.esc(s.name)}" data-action="history" title="Historial de cambios">Historial</button>
            ${canEdit ? `<button class="btn btn-sm btn-danger" data-id="${s.id}" data-action="del">${t('common.delete')}</button>` : ''}
          </td>
        </tr>
      `;
    }).join('');

    const allChecked = data.length > 0 && data.every(s => _selectedIds.has(s.id));
    wrap.innerHTML = `
      <div id="sup-bulk-bar" style="display:none;align-items:center;gap:10px;padding:8px 12px;
          background:var(--bg-2);border:1px solid var(--brand-purple);border-radius:6px;margin-bottom:10px;">
        <span id="sup-sel-count" style="font-size:13px;font-weight:600;color:var(--brand-purple);"></span>
        ${canEdit ? `
        <button id="btn-bulk-recompute" class="btn btn-sm" style="margin-left:4px;">Recalcular seleccionados</button>
        <button id="btn-bulk-del" class="btn btn-sm btn-danger">Eliminar seleccionados</button>
        ` : ''}
        <button id="btn-bulk-clear" class="btn btn-sm" style="margin-left:auto;">Deseleccionar todo</button>
      </div>
      <table class="data">
        <thead>
          <tr>
            <th style="width:36px;text-align:center;">
              <input type="checkbox" id="sup-chk-all" ${allChecked ? 'checked' : ''}
                style="width:15px;height:15px;cursor:pointer;accent-color:var(--brand-purple);"
                title="Seleccionar todo">
            </th>
            <th>Código</th><th>Nombre</th><th>Tag</th><th>Imp. negocio</th><th>Riesgo seg.</th><th>Estado seg.</th><th>Tier</th><th>Inherent</th><th>Residual</th>
            <th>Ult. evaluación</th><th>Prox. revisión</th><th>Acciones</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;

    _updateBulkBar();

    document.getElementById('sup-chk-all').onchange = (e) => {
      if (e.target.checked) data.forEach(s => _selectedIds.add(s.id));
      else data.forEach(s => _selectedIds.delete(s.id));
      wrap.querySelectorAll('.sup-chk').forEach(cb => { cb.checked = e.target.checked; });
      _updateBulkBar();
    };

    wrap.querySelectorAll('.sup-chk').forEach(cb => {
      cb.onchange = () => {
        const id = parseInt(cb.dataset.id);
        if (cb.checked) _selectedIds.add(id);
        else _selectedIds.delete(id);
        const chkAll = document.getElementById('sup-chk-all');
        if (chkAll) chkAll.checked = data.every(s => _selectedIds.has(s.id));
        _updateBulkBar();
      };
    });

    const bulkDelBtn = document.getElementById('btn-bulk-del');
    if (bulkDelBtn) bulkDelBtn.onclick = _bulkDelete;
    const bulkRcpBtn = document.getElementById('btn-bulk-recompute');
    if (bulkRcpBtn) bulkRcpBtn.onclick = _bulkRecompute;
    document.getElementById('btn-bulk-clear').onclick = () => {
      _selectedIds.clear();
      wrap.querySelectorAll('.sup-chk').forEach(cb => { cb.checked = false; });
      const chkAll = document.getElementById('sup-chk-all');
      if (chkAll) chkAll.checked = false;
      _updateBulkBar();
    };

    wrap.querySelectorAll('[data-action="recompute"]').forEach(btn => {
      btn.onclick = async () => {
        try {
          await Api.tprm.recompute(btn.dataset.id);
          UI.toast('Riesgo recalculado', 'success');
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });

    wrap.querySelectorAll('[data-action="edit"]').forEach(btn => {
      btn.onclick = () => {
        const sup = data.find(s => s.id == btn.dataset.id);
        if (sup) _openForm(sup);
      };
    });
    wrap.querySelectorAll('[data-action="file"]').forEach(el => {
      el.onclick = () => {
        const sup = data.find(s => s.id == el.dataset.id);
        if (sup) _openSupplierFile(sup);
      };
    });
    wrap.querySelectorAll('[data-action="del"]').forEach(btn => {
      btn.onclick = async () => {
        if (!confirm(t('suppliers.confirm_delete_supplier'))) return;
        try {
          await Api.suppliers.del(btn.dataset.id);
          UI.toast(t('suppliers.supplier_deleted'), 'success');
          _selectedIds.delete(parseInt(btn.dataset.id));
          await _loadStats();
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });
    wrap.querySelectorAll('[data-action="history"]').forEach(btn => {
      btn.onclick = () => {
        if (typeof ViewAudit !== 'undefined') {
          ViewAudit.showEntityHistory('supplier', btn.dataset.id, btn.dataset.name);
        }
      };
    });
    wrap.querySelectorAll('[data-action="ai"]').forEach(btn => {
      btn.onclick = () => {
        const sup = data.find(s => s.id == btn.dataset.id);
        if (sup) _openAiAssistant(sup);
      };
    });
  }

  function _aiListHtml(title, items) {
    if (!items || !items.length) return '';
    return `<div style="margin-top:8px;"><strong style="font-size:12px;color:var(--brand-purple);">${title}</strong>
      <ul style="margin:4px 0 0 16px;font-size:13px;">${items.map(i => `<li>${UI.esc(typeof i === 'string' ? i : JSON.stringify(i))}</li>`).join('')}</ul></div>`;
  }

  function _openAiAssistant(s) {
    UI.modal(`Asistente IA — ${UI.esc(s.name)}`, `
      <div class="span2">
        <p style="font-size:12px;color:var(--text-muted);margin-bottom:10px;">La IA propone; Seguridad mantiene la decisión final. Nada se aplica automáticamente.</p>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
          <button class="btn btn-sm btn-primary" id="ai-classify">Sugerir clasificación</button>
          <button class="btn btn-sm" id="ai-analyze">Analizar proveedor</button>
          <button class="btn btn-sm" id="ai-review">Resumen de revisión</button>
        </div>
        <div id="ai-out" style="min-height:60px;"></div>
      </div>
    `, { actions: `<button class="btn" onclick="UI.closeModal()">Cerrar</button>`, width: 'min(96vw, 720px)' });

    const out = document.getElementById('ai-out');
    const busy = () => { out.innerHTML = '<p class="text-muted" style="font-size:13px;">Consultando IA…</p>'; };

    document.getElementById('ai-classify').onclick = async () => {
      busy();
      try {
        const r = await Api.suppliers.aiClassify(s.id);
        out.innerHTML = `
          <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:6px;padding:10px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:13px;">
              <div><b>Importancia negocio:</b> ${_enumBadge(BIZ_IMPORTANCE, r.business_importance_level)}</div>
              <div><b>Riesgo seguridad:</b> ${_enumBadge(SEC_RISK, r.security_risk_level)}</div>
              <div><b>Frecuencia revisión:</b> ${UI.esc(REVIEW_FREQ[r.review_frequency] || r.review_frequency || '—')}</div>
              <div><b>Confianza:</b> ${Math.round((r.confidence || 0) * 100)}%</div>
            </div>
            ${_aiListHtml('Evaluaciones sugeridas', r.required_assessments)}
            <div style="margin-top:8px;font-size:13px;"><b>Justificación:</b> ${UI.esc(r.rationale || '')}</div>
            <button class="btn btn-sm btn-primary" id="ai-apply" style="margin-top:10px;">Aplicar sugerencia (aprobar)</button>
          </div>`;
        document.getElementById('ai-apply').onclick = async () => {
          try {
            await Api.suppliers.update(s.id, {
              business_importance_level: r.business_importance_level,
              security_risk_level: r.security_risk_level,
              review_frequency: r.review_frequency,
            });
            UI.toast('Clasificación aplicada', 'success');
            UI.closeModal();
            await _refresh();
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      } catch (e) { out.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
    };

    document.getElementById('ai-analyze').onclick = async () => {
      busy();
      try {
        const r = await Api.suppliers.aiAnalyze(s.id);
        out.innerHTML = `
          <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:6px;padding:10px;font-size:13px;">
            <div><b>Resumen:</b> ${UI.esc(r.summary || '')}</div>
            ${_aiListHtml('Datos faltantes', r.missing_data)}
            ${_aiListHtml('Acuerdos faltantes', r.missing_agreements)}
            ${_aiListHtml('Evaluaciones faltantes', r.missing_assessments)}
            ${_aiListHtml('Revisiones', r.overdue_reviews)}
            ${_aiListHtml('Acciones recomendadas', r.recommended_actions)}
          </div>`;
      } catch (e) { out.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
    };

    document.getElementById('ai-review').onclick = async () => {
      busy();
      try {
        const r = await Api.suppliers.aiReviewAssistant(s.id);
        out.innerHTML = `
          <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:6px;padding:10px;font-size:13px;">
            <div><b>Resumen de revisión:</b> ${UI.esc(r.review_summary || '')}</div>
            <div style="margin-top:6px;"><b>Postura:</b> ${UI.esc(r.overall_posture || '—')}</div>
            ${_aiListHtml('Acciones sugeridas', r.suggested_actions)}
            ${_aiListHtml('Recomendaciones de reevaluación', r.reassessment_recommendations)}
          </div>`;
      } catch (e) { out.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
    };
  }

  function _formHtml(s) {
    const v = s || {};
    // grid-column:1/-1 para que el wrapper ocupe todo el ancho del modal-body (que es grid 2col)
    return `
      <div style="grid-column:1/-1;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px 24px;">

        <!-- Fila 1: identificación básica -->
        <div><label>Nombre *</label><input id="f-name" class="input" value="${UI.esc(v.name || '')}"></div>
        <div><label>Categoría</label><input id="f-cat" class="input" value="${UI.esc(v.category || '')}" placeholder="Software, Hardware, Servicios..."></div>
        <div><label>Nivel de riesgo</label>
          <select id="f-risk-level" class="input">
            ${_rlBands().map(b => `<option value="${b.code}" ${v.risk_level===b.code?'selected':''}>${UI.esc(b.label)}</option>`).join('')}
          </select>
        </div>

        <!-- Fila 2: contacto -->
        <div><label>Contacto principal</label><input id="f-contact" class="input" value="${UI.esc(v.contact_name || '')}"></div>
        <div><label>Email principal</label><input id="f-email" class="input" type="email" value="${UI.esc(v.contact_email || '')}"></div>
        <div><label>CC alertas y cuestionarios</label><input id="f-cc-email" class="input" type="email" value="${UI.esc(v.cc_email || '')}" placeholder="responsable@empresa.com"></div>

        <!-- Fila 3: fechas + contrato -->
        <div><label>Última evaluación</label><input type="date" id="f-last-assess" class="input" value="${v.last_assessment_at ? v.last_assessment_at.slice(0,10) : ''}"></div>
        <div><label>Próxima evaluación</label><input type="date" id="f-next-assess" class="input" value="${v.next_assessment_at ? v.next_assessment_at.slice(0,10) : ''}"></div>
        <div><label>Contrato / referencia</label><input id="f-contract" class="input" value="${UI.esc(v.contract_ref || '')}"></div>

        <!-- Fila 4: clasificación interna -->
        <div><label>Ubicacion / sede</label><input id="f-location" class="input" value="${UI.esc(v.location || '')}" placeholder="Madrid, ES"></div>
        <div><label>Departamento responsable</label><input id="f-department" class="input" value="${UI.esc(v.department || '')}" placeholder="TI, Legal, Compras..."></div>
        <div><label>Responsable interno</label><select id="f-internal-owner" class="input"><option value="">- Sin asignar -</option></select></div>

        <!-- Fila 4b: trust portal -->
        <div style="grid-column:1/-1;">
          <label>Trust Portal URL <span style="font-size:11px;color:var(--text-muted);font-weight:400;">(el agente IA analizara esta web para autocompletar la ficha)</span></label>
          <input id="f-trust-portal-url" class="input" type="url" value="${UI.esc(v.trust_portal_url || '')}" placeholder="https://trust.proveedor.com">
        </div>

        <!-- Fila 5: flags + importancia (inline) -->
        <div style="grid-column:1/-1;display:flex;align-items:center;gap:24px;flex-wrap:wrap;padding:4px 0;border-top:1px solid var(--border);margin-top:2px;">
          <label style="display:flex;align-items:center;gap:6px;margin:0;cursor:pointer;font-weight:600;"><input type="checkbox" id="f-critical" ${v.is_critical?'checked':''}> Crítico NIS2</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;cursor:pointer;"><input type="checkbox" id="f-proc" ${v.is_data_processor?'checked':''}> Encargado GDPR</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;cursor:pointer;"><input type="checkbox" id="f-pii" ${v.processes_personal_data?'checked':''}> Trata datos personales</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;cursor:pointer;"><input type="checkbox" id="f-nis2" ${v.is_nis2?'checked':''}> NIS2</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;cursor:pointer;"><input type="checkbox" id="f-dora" ${v.is_dora?'checked':''}> DORA</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;cursor:pointer;"><input type="checkbox" id="f-ens" ${v.is_ens?'checked':''}> ENS</label>
          <div style="margin-left:auto;display:flex;align-items:center;gap:8px;">
            <label style="font-size:12px;color:var(--text-muted);white-space:nowrap;">Importancia negocio (1-5)</label>
            <input type="number" min="1" max="5" id="f-biz-imp" class="input" value="${v.business_importance || ''}" style="width:70px;">
          </div>
        </div>

        <!-- Gobierno y seguridad (Suppliers Module Review) -->
        <div style="grid-column:1/-1;margin-top:4px;border-top:1px solid var(--border);padding-top:8px;">
          <strong style="font-size:13px;color:var(--brand-purple);">Gobierno y seguridad</strong>
          <span style="font-size:11px;color:var(--text-muted);margin-left:8px;">Importancia de negocio y riesgo de seguridad son clasificaciones independientes.</span>
        </div>
        <div><label>Importancia de negocio</label>
          <select id="f-biz-imp-level" class="input">${_selOptions(BIZ_IMPORTANCE, v.business_importance_level)}</select>
        </div>
        <div><label>Riesgo de seguridad</label>
          <select id="f-sec-risk" class="input">${_selOptions(SEC_RISK, v.security_risk_level)}</select>
        </div>
        <div><label>Región operativa</label>
          <select id="f-op-region" class="input"><option value="">- Sin definir -</option>${v.operating_region ? `<option value="${UI.esc(v.operating_region)}" selected>${UI.esc(v.operating_region)}</option>` : ''}</select>
        </div>
        <div><label>Estado de seguridad</label>
          <select id="f-sec-status" class="input">${_selOptions(SEC_STATUS, v.security_status)}</select>
        </div>
        <div><label>Frecuencia de revisión</label>
          <select id="f-review-freq" class="input"><option value="">- Sin definir -</option>${Object.entries(REVIEW_FREQ).map(([k, l]) => `<option value="${k}" ${v.review_frequency === k ? 'selected' : ''}>${l}</option>`).join('')}</select>
        </div>
        <div><label>Estado del acuerdo</label>
          <select id="f-agreement" class="input"><option value="">- Sin definir -</option>${Object.entries(AGREEMENT_STATUS).map(([k, l]) => `<option value="${k}" ${v.agreement_status === k ? 'selected' : ''}>${l}</option>`).join('')}</select>
        </div>
        <div><label>Owner (responsable)</label><select id="f-owner" class="input"><option value="">- Sin asignar -</option></select></div>
        <div><label>Backup Owner (suplente)</label><select id="f-backup-owner" class="input"><option value="">- Sin asignar -</option></select></div>
        <div></div>

        <!-- Notas -->
        <div style="grid-column:1/-1;"><label>Notas / descripción</label><textarea id="f-notes" class="input" rows="2">${UI.esc(v.notes || '')}</textarea></div>

        <!-- TPRM -->
        <div style="grid-column:1/-1;margin-top:4px;border-top:1px solid var(--border);padding-top:8px;">
          <strong style="font-size:13px;color:var(--brand-purple);">TPRM — Perfil de riesgo inherente</strong>
          <span style="font-size:11px;color:var(--text-muted);margin-left:8px;">El tier y el inherent/residual risk se recalculan automáticamente al guardar.</span>
        </div>
        <div><label>Tipo de proveedor</label>
          <select id="f-vendor-type" class="input">
            ${['technology','cloud_provider','professional_services','consultancy','hardware','subcontractor','other'].map(o => `<option value="${o}" ${v.vendor_type===o?'selected':''}>${o}</option>`).join('')}
          </select>
        </div>
        <div><label>Acceso a sistemas</label>
          <select id="f-access" class="input">
            ${['none','api_only','saas','paas','iaas','on_prem','read_write','admin_to_our_systems'].map(o => `<option value="${o}" ${v.system_access_type===o?'selected':''}>${o}</option>`).join('')}
          </select>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
          <div><label>Sensibilidad datos</label><input type="number" min="1" max="5" id="f-data-sens" class="input" value="${v.data_sensitivity || 2}"></div>
          <div><label>Volumen datos</label><input type="number" min="1" max="5" id="f-data-vol" class="input" value="${v.data_volume || 2}"></div>
        </div>
        <div><label>Criticidad para el negocio</label><input type="number" min="1" max="5" id="f-biz-crit" class="input" value="${v.business_criticality || 3}"></div>
        <div><label>Riesgo geografico</label><input type="number" min="1" max="5" id="f-geo" class="input" value="${v.geographic_risk || 1}"></div>

        <!-- Contactos adicionales -->
        <div style="grid-column:1/-1;margin-top:4px;border-top:1px solid var(--border);padding-top:10px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <strong style="font-size:13px;color:var(--brand-purple);">Contactos adicionales</strong>
            <button type="button" id="sup-add-contact" class="btn btn-sm">+ Añadir</button>
          </div>
          <div id="sup-contact-list"></div>
        </div>

        <!-- SLAs -->
        <div style="grid-column:1/-1;border-top:1px solid var(--border);padding-top:10px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <strong style="font-size:13px;color:var(--brand-purple);">SLAs del proveedor</strong>
            <button type="button" id="sup-add-sla" class="btn btn-sm">+ Añadir SLA</button>
          </div>
          <div id="sup-sla-list"></div>
        </div>

        ${s ? `
        <!-- Documentación adjunta -->
        <div style="grid-column:1/-1;border-top:1px solid var(--border);padding-top:10px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <strong style="font-size:13px;color:var(--brand-purple);">Documentación adjunta</strong>
            <label class="btn btn-sm" style="cursor:pointer;">
              + Adjuntar
              <input type="file" id="sup-doc-upload" style="display:none;"
                accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.csv,.png,.jpg,.jpeg,.zip">
            </label>
          </div>
          <div id="sup-doc-list"><p style="font-size:12px;color:var(--text-muted);">Cargando...</p></div>
          <div id="sup-doc-desc-row" style="display:none;gap:6px;align-items:center;margin-top:6px;">
            <input id="sup-doc-desc" class="input" placeholder="${t('suppliers.doc_desc_placeholder')}" style="flex:1;font-size:12px;">
            <button id="sup-doc-confirm" class="btn btn-sm btn-primary">Subir</button>
            <button id="sup-doc-cancel-upload" class="btn btn-sm">Cancelar</button>
          </div>
        </div>

        <!-- Ciclo de vida -->
        <div style="grid-column:1/-1;border-top:1px solid var(--border);padding-top:10px;">
          <strong style="font-size:13px;color:var(--brand-purple);">Ciclo de vida y onboarding</strong>
          <p style="font-size:11px;color:var(--text-muted);margin:2px 0 8px;">Gestiona el stage del proveedor, el checklist de onboarding y los documentos legales.</p>
          <div id="sup-lifecycle-container"><p style="font-size:12px;color:var(--text-muted);">Cargando...</p></div>
        </div>` : ''}
      </div>
    `;
  }

  let _currentSlas = [];
  let _currentContacts = [];
  let _currentEditedSupplier = null;

  let _docPendingFile = null;

  function _openForm(s) {
    _currentEditedSupplier = s || null;
    _currentSlas = s?.slas ? JSON.parse(JSON.stringify(s.slas)) : [];
    _currentContacts = s?.additional_contacts ? JSON.parse(JSON.stringify(s.additional_contacts)) : [];
    UI.modal(s ? t('suppliers.edit_code', {code: s.code}) : t('suppliers.new_supplier'), _formHtml(s), {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`,
      width: 'min(98vw, 1200px)',
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => _save(s);
    _renderSlaList();
    document.getElementById('sup-add-sla').onclick = _addSlaRow;
    _renderContactList();
    document.getElementById('sup-add-contact').onclick = _addContactRow;
    // Poblar selects de responsables (interno, owner, backup owner)
    Api.users.list().then(users => {
      const fill = (elId, selectedId) => {
        const sel = document.getElementById(elId);
        if (!sel) return;
        users.forEach(u => {
          const opt = document.createElement('option');
          opt.value = u.id;
          opt.textContent = u.full_name || u.email;
          if (s && u.id === selectedId) opt.selected = true;
          sel.appendChild(opt);
        });
      };
      fill('f-internal-owner', s?.internal_owner_id);
      fill('f-owner', s?.owner_id);
      fill('f-backup-owner', s?.backup_owner_id);
    }).catch(() => {});
    // Poblar regiones operativas configurables (punto 4)
    Api.tprm.getSettings().then(cfg => {
      const sel = document.getElementById('f-op-region');
      if (!sel || !cfg.operating_regions) return;
      const cur = s?.operating_region || '';
      cfg.operating_regions.forEach(r => {
        if (r === cur) return; // ya insertado como selected
        const opt = document.createElement('option');
        opt.value = r; opt.textContent = r;
        sel.appendChild(opt);
      });
    }).catch(() => {});

    if (s) {
      _loadDocuments(s.id);
      const uploadInput = document.getElementById('sup-doc-upload');
      const descRow = document.getElementById('sup-doc-desc-row');
      if (uploadInput) {
        uploadInput.onchange = () => {
          _docPendingFile = uploadInput.files[0] || null;
          if (_docPendingFile) descRow.style.display = 'flex';
        };
      }
      const confirmBtn = document.getElementById('sup-doc-confirm');
      if (confirmBtn) {
        confirmBtn.onclick = async () => {
          if (!_docPendingFile) return;
          const desc = document.getElementById('sup-doc-desc')?.value.trim() || '';
          confirmBtn.disabled = true;
          confirmBtn.textContent = 'Subiendo...';
          try {
            await Api.suppliers.uploadDocument(s.id, _docPendingFile, desc || undefined);
            UI.toast('Documento adjuntado', 'success');
            _docPendingFile = null;
            if (uploadInput) uploadInput.value = '';
            if (descRow) descRow.style.display = 'none';
            const descEl = document.getElementById('sup-doc-desc');
            if (descEl) descEl.value = '';
            _loadDocuments(s.id);
          } catch (e) {
            UI.toast(e.message, 'error');
          } finally {
            confirmBtn.disabled = false;
            confirmBtn.textContent = t('common.upload');
          }
        };
      }
      const cancelUploadBtn = document.getElementById('sup-doc-cancel-upload');
      if (cancelUploadBtn) {
        cancelUploadBtn.onclick = () => {
          _docPendingFile = null;
          if (uploadInput) uploadInput.value = '';
          if (descRow) descRow.style.display = 'none';
        };
      }
      _loadSupplierFindings(s.id);
      const reloadFindingsBtn = document.getElementById('sup-reload-findings');
      if (reloadFindingsBtn) reloadFindingsBtn.onclick = () => _loadSupplierFindings(s.id);
      _renderLifecycleSection(s.id, s);
    }
  }

  // ---- Lifecycle / Onboarding helpers ----

  function LIFECYCLE_STAGES() {
    return [
      { id: 'prospecting',  label: window.t('suppliers.lifecycle_prospect')    },
      { id: 'onboarding',   label: window.t('suppliers.lifecycle_onboarding')  },
      { id: 'active',       label: window.t('suppliers.lifecycle_active')       },
      { id: 'under_review', label: window.t('suppliers.lifecycle_review')       },
      { id: 'offboarding',  label: window.t('suppliers.lifecycle_offboarding')  },
      { id: 'terminated',   label: window.t('suppliers.lifecycle_terminated')   },
    ];
  }

  // Cache del gate actual para evitar recargas innecesarias
  let _currentGate = null;
  let _currentSupplierId = null;

  async function _renderLifecycleSection(supplierId, supplierData) {
    const wrap = document.getElementById('sup-lifecycle-container');
    if (!wrap) return;

    let sup = supplierData;
    if (!sup) {
      try {
        const all = await Api.suppliers.list();
        sup = all.find(x => x.id == supplierId) || {};
      } catch (_) { sup = {}; }
    }

    _currentSupplierId = supplierId;
    wrap.innerHTML = '<p style="font-size:12px;color:var(--text-muted);">Cargando gate de onboarding...</p>';

    // Cargar evaluación del gate
    let gate = null;
    try {
      gate = await Api.get('/api/onboarding-gate/' + supplierId + '/evaluate');
      _currentGate = gate;
    } catch (_) { gate = null; }

    const stage = sup.lifecycle_stage || '';
    const concentrationFlag = sup.concentration_risk_flag;

    const stageButtons = LIFECYCLE_STAGES().map(st => `
      <button class="lc-stage-btn ${stage === st.id ? 'lc-stage-btn--active' : ''}"
        onclick="ViewSuppliers._changeStage(${supplierId}, '${st.id}')">
        ${st.label}
      </button>
    `).join('');

    // Checklist legacy (solo si no hay gate activo)
    const checklist = sup.onboarding_checklist || [];
    let checklistHtml = '';
    if (stage === 'onboarding' && checklist.length && !gate) {
      const items = checklist.map(item => `
        <div class="lc-checklist-item ${item.completed ? 'completed' : ''}">
          <input type="checkbox" id="lc-item-${UI.esc(item.id)}" ${item.completed ? 'checked' : ''}
            onchange="ViewSuppliers._toggleChecklistItem(${supplierId}, '${UI.esc(item.id)}', this.checked)">
          <label for="lc-item-${UI.esc(item.id)}">${UI.esc(item.title || item.label || item.id)}</label>
        </div>
      `).join('');
      checklistHtml = `<div class="lc-checklist" style="margin-top:10px;">
        <strong style="font-size:12px;color:var(--brand-purple);display:block;margin-bottom:6px;">Checklist de onboarding</strong>
        ${items}
      </div>`;
    }

    // Bloque del gate de seguridad
    const gateHtml = gate ? _renderGateBlock(supplierId, gate, sup) : '';

    // Concentracion DORA
    const concentrationHtml = concentrationFlag ? `
      <div style="margin-top:12px;">
        <div class="alert-box alert-box--warning">
          <strong>Riesgo de concentracion DORA</strong>
          <p style="font-size:12px;margin:4px 0 8px;">Este proveedor supera el 40% de dependencia en procesos críticos.</p>
          <div style="margin-bottom:6px;">
            <label style="font-size:11px;font-weight:600;display:block;margin-bottom:3px;">Notas de mitigación</label>
            <textarea id="lc-concentration-notes" class="input" rows="2"
              placeholder="${t('suppliers.ph_mitigation_notes')}">${UI.esc(sup.concentration_risk_notes || '')}</textarea>
          </div>
          <div style="margin-bottom:8px;">
            <label style="font-size:11px;font-weight:600;display:block;margin-bottom:3px;">Estrategia de salida (DORA Art.28(8))</label>
            <textarea id="lc-exit-strategy" class="input" rows="2"
              placeholder="Estrategia de salida...">${UI.esc(sup.exit_strategy || '')}</textarea>
          </div>
          ${Auth.canEdit() ? `
          <button class="btn btn-sm btn-primary"
            onclick="ViewSuppliers._saveConcentrationMitigation(${supplierId})">
            Guardar mitigación
          </button>` : ''}
        </div>
      </div>` : '';

    // Admin: enlace config del gate
    const adminLink = Auth.isAdmin() ? `
      <div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--border);">
        <button class="btn btn-sm" onclick="ViewSuppliers._openGateConfig()"
          style="font-size:11px;">Configurar gate de onboarding</button>
      </div>` : '';

    wrap.innerHTML = `
      <div class="supplier-lifecycle">
        <div class="lc-header" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:10px;">
          <span style="font-size:13px;">Stage: <strong>${LIFECYCLE_STAGES().find(x => x.id === stage)?.label || stage}</strong></span>
          ${Auth.canEdit() ? `<div class="lc-stage-buttons" style="display:flex;flex-wrap:wrap;gap:4px;">${stageButtons}</div>` : ''}
        </div>
        ${checklistHtml}
        ${gateHtml}
        ${concentrationHtml}
        ${adminLink}
      </div>
    `;
  }

  function _renderGateBlock(supplierId, gate, sup) {
    const levelLabels = { auto: t('suppliers.gate_auto'), standard: t('suppliers.gate_standard'), manual_review: t('suppliers.gate_manual_review') };
    const levelColors = { auto: '#16a34a', standard: '#d97706', manual_review: '#dc2626' };
    const score = gate.score || 0;
    const level = gate.gate_level || 'auto';
    const effectiveLevel = gate.effective_level || level;
    const bypassed = gate.override?.type === 'bypass';
    const forcedControls = gate.override?.type === 'force_controls';
    const thresholds = gate.thresholds || { auto: 30, manual: 60 };

    // Barra de score
    const scoreColor = score >= thresholds.manual ? '#dc2626' : (score >= thresholds.auto ? '#d97706' : '#16a34a');
    const scorePct = Math.min(100, score);

    const overrideBadge = gate.override ? `
      <span style="margin-left:8px;font-size:10px;font-weight:700;padding:2px 7px;border-radius:999px;
        background:${gate.override.type === 'bypass' ? '#fef3c7' : '#ede9fe'};
        color:${gate.override.type === 'bypass' ? '#92400e' : '#5b21b6'};">
        ${gate.override.type === 'bypass' ? 'BYPASS ACTIVO' : 'CONTROLES FORZADOS'}
      </span>` : '';

    // Gate status header
    const gateHeader = `
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px;">
        <div style="flex:1;min-width:180px;">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;">
            <span style="font-size:12px;font-weight:700;color:var(--brand-purple);">Gate de seguridad</span>
            <span style="font-size:11px;font-weight:700;padding:2px 7px;border-radius:999px;
              background:${levelColors[effectiveLevel]}18;color:${levelColors[effectiveLevel]};">
              ${levelLabels[effectiveLevel] || effectiveLevel}
            </span>
            ${overrideBadge}
          </div>
          <div style="height:6px;background:#e5e7eb;border-radius:999px;overflow:hidden;width:100%;max-width:260px;">
            <div style="height:100%;width:${scorePct}%;background:${scoreColor};border-radius:999px;transition:width 0.3s;"></div>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted);max-width:260px;margin-top:2px;">
            <span>Score TPRM: <strong style="color:${scoreColor};">${score}</strong></span>
            <span>Auto&lt;${thresholds.auto} | Manual&gt;${thresholds.manual}</span>
          </div>
        </div>
        ${Auth.canEdit() ? `
        <div style="display:flex;gap:6px;flex-shrink:0;flex-wrap:wrap;">
          ${!gate.override ? `
            <button class="btn btn-sm" onclick="ViewSuppliers._openBypassDialog(${supplierId})"
              title="${t('suppliers.hint_bypass_gate')}" style="font-size:11px;">
              Bypass justificado
            </button>
            <button class="btn btn-sm" onclick="ViewSuppliers._openForceControlsDialog(${supplierId})"
              title="${t('suppliers.force_controls_hint')}" style="font-size:11px;">
              Forzar controles
            </button>
          ` : `
            <button class="btn btn-sm" onclick="ViewSuppliers._clearOverride(${supplierId})"
              style="font-size:11px;border-color:#dc2626;color:#dc2626;">
              Quitar override
            </button>
          `}
        </div>` : ''}
      </div>`;

    // Info del override activo
    const overrideInfo = gate.override ? `
      <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:6px;padding:8px 10px;margin-bottom:10px;font-size:11px;">
        <strong>${gate.override.type === 'bypass' ? 'Bypass activo' : 'Controles adicionales forzados'}</strong>
        ${gate.override.justification ? `<br><span style="color:var(--text-muted);">Justificacion: ${UI.esc(gate.override.justification)}</span>` : ''}
        ${gate.override.at ? `<br><span style="color:var(--text-muted);">${new Date(gate.override.at).toLocaleString('es-ES')}</span>` : ''}
      </div>` : '';

    // Cadena de firmas
    const chainItems = gate.sign_off_chain || [];
    let chainHtml = '';
    if (chainItems.length) {
      const itemsHtml = chainItems.map(it => {
        const isDone = it.signed || it.skipped;
        const isBlocked = !!it.blocked_by;
        const dotColor = it.skipped ? '#9ca3af' : (it.signed ? '#16a34a' : (it.required ? '#dc2626' : '#d97706'));
        const dotLabel = it.skipped ? t('suppliers.st_skipped') : (it.signed ? t('suppliers.st_signed') : (isBlocked ? t('suppliers.st_blocked') : (it.required ? t('suppliers.st_pending') : t('suppliers.st_optional'))));
        const signedDate = it.signed_at ? new Date(it.signed_at).toLocaleDateString('es-ES') : null;
        const forcedBadge = it.forced ? `<span style="font-size:9px;background:#ede9fe;color:#5b21b6;padding:1px 5px;border-radius:999px;margin-left:4px;font-weight:700;">FORZADO</span>` : '';
        const gateBadge = it.score_gate ? `<span style="font-size:9px;background:#fee2e2;color:#991b1b;padding:1px 5px;border-radius:999px;margin-left:4px;">Score&gt;${it.score_gate}</span>` : '';
        const depBadge = it.depends_on ? `<span style="font-size:9px;color:var(--text-muted);margin-left:4px;">dep: ${it.depends_on}</span>` : '';

        let actionHtml = '';
        if (Auth.canEdit() && !isDone && !isBlocked) {
          actionHtml = `
            <div style="display:flex;gap:4px;margin-top:4px;">
              <button class="btn btn-sm" style="font-size:10px;padding:2px 8px;"
                onclick="ViewSuppliers._openSignOffDialog(${supplierId}, '${it.id}', false)">
                Registrar firma
              </button>
              ${it.bypass_allowed ? `
              <button class="btn btn-sm" style="font-size:10px;padding:2px 8px;color:#9ca3af;border-color:#e5e7eb;"
                onclick="ViewSuppliers._openSignOffDialog(${supplierId}, '${it.id}', true)">
                Omitir
              </button>` : ''}
            </div>`;
        } else if (Auth.isAdmin() && isDone) {
          actionHtml = `
            <button class="btn btn-sm" style="font-size:10px;padding:1px 6px;margin-top:3px;color:#9ca3af;border-color:#e5e7eb;"
              onclick="ViewSuppliers._undoSignOff(${supplierId}, '${it.id}')">
              Revertir
            </button>`;
        }

        return `
          <div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid #f5f0fa;">
            <div style="width:8px;height:8px;border-radius:50%;background:${dotColor};flex-shrink:0;margin-top:5px;"></div>
            <div style="flex:1;min-width:0;">
              <div style="font-size:11px;font-weight:600;display:flex;align-items:center;flex-wrap:wrap;gap:2px;">
                ${UI.esc(it.label)}${forcedBadge}${gateBadge}${depBadge}
              </div>
              <div style="font-size:10px;color:${dotColor};font-weight:600;">${dotLabel}
                ${signedDate ? `<span style="color:var(--text-muted);font-weight:400;"> — ${signedDate}${it.signed_by_name ? ' por ' + UI.esc(it.signed_by_name) : ''}</span>` : ''}
                ${it.skipped && it.skip_justification ? `<span style="color:var(--text-muted);font-weight:400;"> — ${UI.esc(it.skip_justification)}</span>` : ''}
                ${isBlocked ? `<span style="color:var(--text-muted);font-weight:400;"> — esperando: ${it.blocked_by}</span>` : ''}
              </div>
              ${actionHtml}
            </div>
          </div>`;
      }).join('');

      chainHtml = `
        <div style="margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <strong style="font-size:12px;color:var(--brand-purple);">Cadena de firmas</strong>
            <span style="font-size:10px;color:${gate.sign_offs_complete ? '#16a34a' : '#dc2626'};font-weight:700;">
              ${gate.sign_offs_complete ? 'Completa' : gate.blocking_items?.length + ' pendiente(s)'}
            </span>
          </div>
          ${itemsHtml}
        </div>`;
    } else {
      chainHtml = `<p style="font-size:12px;color:var(--text-muted);margin-bottom:10px;">${t('suppliers.no_signoff_items')}</p>`;
    }

    // Decision formal
    const decision = gate.decision;
    let decisionHtml = '';
    if (decision) {
      const decColors = { approved: '#16a34a', rejected: '#dc2626', conditional: '#d97706' };
      const decLabels = { approved: t('suppliers.dec_approved'), rejected: t('suppliers.dec_rejected'), conditional: t('suppliers.dec_conditional') };
      decisionHtml = `
        <div style="background:${decColors[decision.status] || '#9ca3af'}10;border:1.5px solid ${decColors[decision.status] || '#9ca3af'};border-radius:6px;padding:8px 10px;margin-bottom:10px;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
            <div>
              <span style="font-size:11px;font-weight:700;color:${decColors[decision.status] || '#9ca3af'};">
                Decision: ${decLabels[decision.status] || decision.status}
              </span>
              ${decision.at ? `<span style="font-size:10px;color:var(--text-muted);margin-left:6px;">${new Date(decision.at).toLocaleString('es-ES')}</span>` : ''}
              ${decision.notes ? `<p style="font-size:11px;color:var(--text-primary);margin:4px 0 0;">${UI.esc(decision.notes)}</p>` : ''}
            </div>
            ${Auth.canEdit() ? `
            <button class="btn btn-sm" style="font-size:10px;flex-shrink:0;"
              onclick="ViewSuppliers._openDecisionDialog(${supplierId})">Cambiar</button>` : ''}
          </div>
          ${decision.conditions && decision.conditions.length ? `
            <div style="margin-top:6px;">
              <div style="font-size:10px;font-weight:700;color:var(--text-muted);margin-bottom:3px;">Condiciones:</div>
              ${decision.conditions.map(c => `
                <div style="font-size:11px;display:flex;align-items:center;gap:6px;">
                  <span style="color:#d97706;">&#9679;</span> ${UI.esc(c.description || '')}
                  ${c.due_days ? `<span style="font-size:10px;color:var(--text-muted);">(${c.due_days}d)</span>` : ''}
                  ${c.vendor_issue_id ? `<a href="#/vendor-issues" style="font-size:10px;color:var(--brand-purple);">VIS</a>` : ''}
                </div>`).join('')}
            </div>` : ''}
        </div>`;
    } else if (Auth.canEdit()) {
      decisionHtml = `
        <div style="margin-bottom:10px;">
          <button class="btn btn-sm btn-primary" onclick="ViewSuppliers._openDecisionDialog(${supplierId})"
            style="font-size:11px;">Registrar decision de seguridad</button>
        </div>`;
    }

    return `
      <div style="border:1.5px solid #ede7f6;border-radius:8px;padding:12px;margin-top:10px;background:#faf8ff;">
        ${gateHeader}
        ${overrideInfo}
        ${decisionHtml}
        ${chainHtml}
      </div>`;
  }

  async function _changeStage(supplierId, stage) {
    try {
      await Api.post('/api/suppliers/' + supplierId + '/lifecycle', { stage });
      UI.toast('Stage actualizado a: ' + (LIFECYCLE_STAGES().find(x => x.id === stage)?.label || stage), 'success');
      _renderLifecycleSection(supplierId, null);
    } catch (e) { UI.toast(e.message || 'Error al cambiar stage', 'error'); }
  }

  async function _toggleChecklistItem(supplierId, itemId, completed) {
    try {
      const r = await Api.patch('/api/suppliers/' + supplierId + '/checklist/' + itemId, { completed });
      if (r && r.lifecycle_changes && r.lifecycle_changes.length) {
        UI.toast('Checklist: ' + r.lifecycle_changes.join(', '), 'success');
      }
      _renderLifecycleSection(supplierId, null);
    } catch (e) { UI.toast(e.message || 'Error al actualizar checklist', 'error'); }
  }

  // --- Sign-off dialog (firma o salto con justificacion) ---
  function _openSignOffDialog(supplierId, itemId, skipMode) {
    const title = skipMode ? 'Omitir item: ' + itemId : 'Registrar firma: ' + itemId;
    UI.modal(title, `
      <div class="span2" style="display:flex;flex-direction:column;gap:10px;">
        ${!skipMode ? `
          <div>
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Firmado por</label>
            <input id="so-signed-by" class="input" placeholder="${t('suppliers.ph_signer_name')}">
          </div>` : ''}
        ${skipMode ? `
          <div>
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Justificacion para omitir *</label>
            <textarea id="so-skip-justification" class="input" rows="3"
              placeholder="${t('suppliers.ph_skip_reason')}"></textarea>
          </div>` : ''}
        ${!skipMode ? `
          <div>
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Justificacion / notas (opcional)</label>
            <textarea id="so-notes" class="input" rows="2" placeholder="Notas adicionales..."></textarea>
          </div>` : ''}
      </div>
    `, {
      actions: `
        <button class="btn" onclick="UI.closeModal()">Cancelar</button>
        <button class="btn btn-primary" id="so-confirm">
          ${skipMode ? 'Omitir' : 'Confirmar firma'}
        </button>`,
      width: '420px',
    });
    document.getElementById('so-confirm').onclick = async () => {
      const payload = { skipped: skipMode };
      if (skipMode) {
        payload.skip_justification = document.getElementById('so-skip-justification')?.value.trim() || '';
        if (!payload.skip_justification) { UI.toast('La justificacion es obligatoria', 'error'); return; }
      } else {
        payload.signed_by = document.getElementById('so-signed-by')?.value.trim() || '';
      }
      try {
        await Api.patch('/api/onboarding-gate/' + supplierId + '/sign-off/' + itemId, payload);
        UI.closeModal();
        UI.toast(skipMode ? 'Item omitido' : 'Firma registrada', 'success');
        _renderLifecycleSection(supplierId, null);
      } catch (e) { UI.toast(e.message || 'Error', 'error'); }
    };
  }

  async function _undoSignOff(supplierId, itemId) {
    if (!confirm('Revertir la firma de "' + itemId + '"?')) return;
    try {
      await Api.del('/api/onboarding-gate/' + supplierId + '/sign-off/' + itemId);
      UI.toast('Firma revertida', 'success');
      _renderLifecycleSection(supplierId, null);
    } catch (e) { UI.toast(e.message || 'Error', 'error'); }
  }

  // --- Bypass dialog ---
  function _openBypassDialog(supplierId) {
    UI.modal(t('suppliers.modal_gate_bypass'), `
      <div class="span2" style="display:flex;flex-direction:column;gap:12px;">
        <div style="background:#fef9c3;border:1px solid #fde047;border-radius:6px;padding:10px;font-size:12px;">
          <strong>Atencion:</strong> El bypass omite los requisitos del gate basados en score.
          La justificacion quedara registrada en el log de auditoría.
        </div>
        <div>
          <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Justificacion * (obligatoria)</label>
          <textarea id="bypass-justification" class="input" rows="3"
            placeholder="${t('suppliers.ph_bypass_reason')}"></textarea>
        </div>
      </div>
    `, {
      actions: `
        <button class="btn" onclick="UI.closeModal()">Cancelar</button>
        <button class="btn" id="bypass-confirm" style="background:#d97706;color:#fff;border-color:#d97706;">
          Aplicar bypass
        </button>`,
      width: '460px',
    });
    document.getElementById('bypass-confirm').onclick = async () => {
      const justification = document.getElementById('bypass-justification')?.value.trim() || '';
      if (!justification) { UI.toast('La justificacion es obligatoria', 'error'); return; }
      try {
        await Api.post('/api/onboarding-gate/' + supplierId + '/override', { type: 'bypass', justification });
        UI.closeModal();
        UI.toast('Bypass aplicado — registrado en auditoría', 'success');
        _renderLifecycleSection(supplierId, null);
      } catch (e) { UI.toast(e.message || 'Error', 'error'); }
    };
  }

  // --- Force controls dialog ---
  function _openForceControlsDialog(supplierId) {
    const gate = _currentGate;
    const existingChain = gate?.sign_off_chain || [];
    const chainIds = existingChain.map(i => i.id);
    // Items base que se pueden forzar aunque no apliquen por score/condicion
    const candidates = [
      { id: 'nda', label: 'NDA / Confidencialidad' },
      { id: 'dpa', label: 'DPA Art. 28 GDPR' },
      { id: 'cross_border', label: t('suppliers.gc_cross_border') },
      { id: 'nis2_addendum', label: 'Addendum NIS2 Art. 21' },
      { id: 'dora_exit', label: 'Estrategia de salida DORA' },
      { id: 'ciso_approval', label: t('suppliers.gc_ciso_approval') },
      { id: 'contract', label: 'Contrato principal' },
    ].filter(c => !existingChain.find(i => i.id === c.id && i.applicable));

    UI.modal('Forzar controles adicionales', `
      <div class="span2" style="display:flex;flex-direction:column;gap:14px;">
        <p style="font-size:12px;color:var(--text-muted);margin:0;">
          Marca los controles que deben ser obligatorios para este proveedor,
          independientemente del score o las condiciones regulatorias.
        </p>
        <div style="display:flex;flex-direction:column;gap:6px;">
          ${candidates.map(c => `
            <label style="display:flex;align-items:center;gap:8px;font-size:12px;cursor:pointer;">
              <input type="checkbox" class="force-ctrl-chk" value="${c.id}">
              ${UI.esc(c.label)}
            </label>`).join('')}
          ${!candidates.length ? '<p style="font-size:12px;color:var(--text-muted);margin:0;">Todos los items ya están en la cadena.</p>' : ''}
          <label style="display:flex;align-items:center;gap:8px;font-size:12px;cursor:pointer;margin-top:4px;">
            <input type="checkbox" id="force-ctrl-other-chk" value="__other__">
            Otro (especificar):
            <input id="force-ctrl-other-text" class="input" style="flex:1;font-size:12px;"
              placeholder="${t('suppliers.ph_custom_control_name')}"
              onclick="event.stopPropagation()"
              oninput="document.getElementById('force-ctrl-other-chk').checked = this.value.trim().length > 0">
          </label>
        </div>
        <div>
          <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Justificacion</label>
          <textarea id="force-justification" class="input" rows="2"
            placeholder="${t('suppliers.ph_force_controls_reason')}"></textarea>
        </div>
      </div>
    `, {
      actions: `
        <button class="btn" onclick="UI.closeModal()">Cancelar</button>
        <button class="btn btn-primary" id="force-confirm">Aplicar</button>`,
      width: '460px',
    });
    document.getElementById('force-confirm').onclick = async () => {
      const checked = [...document.querySelectorAll('.force-ctrl-chk:checked')].map(c => c.value)
        .filter(v => v !== '__other__');
      const otherText = document.getElementById('force-ctrl-other-text')?.value.trim() || '';
      if (document.getElementById('force-ctrl-other-chk')?.checked && otherText) {
        checked.push(otherText);
      }
      if (!checked.length) { UI.toast('Selecciona al menos un control', 'error'); return; }
      const justification = document.getElementById('force-justification')?.value.trim() || '';
      try {
        await Api.post('/api/onboarding-gate/' + supplierId + '/override', {
          type: 'force_controls', justification, extra_signoffs: checked,
        });
        UI.closeModal();
        UI.toast('Controles forzados aplicados', 'success');
        _renderLifecycleSection(supplierId, null);
      } catch (e) { UI.toast(e.message || 'Error', 'error'); }
    };
  }

  // --- Clear override ---
  async function _clearOverride(supplierId) {
    if (!confirm(t('suppliers.confirm_remove_override'))) return;
    try {
      await Api.post('/api/onboarding-gate/' + supplierId + '/override', { type: 'clear' });
      UI.toast('Override eliminado', 'success');
      _renderLifecycleSection(supplierId, null);
    } catch (e) { UI.toast(e.message || 'Error', 'error'); }
  }

  // --- Decision dialog ---
  function _openDecisionDialog(supplierId) {
    UI.modal('Decision formal de ciberseguridad', `
      <div class="span2" style="display:flex;flex-direction:column;gap:12px;">
        <div>
          <label style="font-size:12px;font-weight:600;display:block;margin-bottom:6px;">Decision *</label>
          <div style="display:flex;gap:8px;">
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;
              padding:6px 12px;border:1.5px solid #e5e7eb;border-radius:6px;flex:1;justify-content:center;">
              <input type="radio" name="dec-type" value="approved"> Aprobado
            </label>
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;
              padding:6px 12px;border:1.5px solid #e5e7eb;border-radius:6px;flex:1;justify-content:center;">
              <input type="radio" name="dec-type" value="conditional"> Condicional
            </label>
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;
              padding:6px 12px;border:1.5px solid #e5e7eb;border-radius:6px;flex:1;justify-content:center;">
              <input type="radio" name="dec-type" value="rejected"> Rechazado
            </label>
          </div>
        </div>
        <div>
          <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Notas / razonamiento</label>
          <textarea id="dec-notes" class="input" rows="3"
            placeholder="${t('suppliers.ph_decision_basis')}"></textarea>
        </div>
        <div id="dec-conditions-wrap" style="display:none;">
          <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">
            Condiciones de alta (se crean como hallazgos VIS)
          </label>
          <div id="dec-conditions-list"></div>
          <button type="button" class="btn btn-sm" onclick="ViewSuppliers._addDecisionCondition()"
            style="margin-top:4px;">+ Añadir condicion</button>
        </div>
      </div>
    `, {
      actions: `
        <button class="btn" onclick="UI.closeModal()">Cancelar</button>
        <button class="btn btn-primary" id="dec-confirm">Guardar decision</button>`,
      width: '500px',
    });

    document.querySelectorAll('input[name="dec-type"]').forEach(r => {
      r.onchange = () => {
        const wrap = document.getElementById('dec-conditions-wrap');
        if (wrap) wrap.style.display = r.value === 'conditional' ? '' : 'none';
      };
    });

    document.getElementById('dec-confirm').onclick = async () => {
      const decision = document.querySelector('input[name="dec-type"]:checked')?.value;
      if (!decision) { UI.toast('Selecciona una decision', 'error'); return; }
      const notes = document.getElementById('dec-notes')?.value.trim() || '';
      const conditions = [...document.querySelectorAll('.dec-condition-row')].map(row => ({
        description: row.querySelector('.dec-cond-desc')?.value.trim() || '',
        due_days: parseInt(row.querySelector('.dec-cond-days')?.value || '30', 10),
      })).filter(c => c.description);
      if (decision === 'conditional' && !conditions.length) {
        UI.toast('Añade al menos una condicion', 'error'); return;
      }
      try {
        const r = await Api.post('/api/onboarding-gate/' + supplierId + '/decision', { decision, notes, conditions });
        UI.closeModal();
        UI.toast(t('suppliers.decision_registered') + (r.auto_promoted ? t('suppliers.promoted_to_active') : ''), 'success');
        _renderLifecycleSection(supplierId, null);
      } catch (e) { UI.toast(e.message || 'Error', 'error'); }
    };
  }

  let _decConditionCount = 0;
  function _addDecisionCondition() {
    const list = document.getElementById('dec-conditions-list');
    if (!list) return;
    _decConditionCount++;
    const row = document.createElement('div');
    row.className = 'dec-condition-row';
    row.style.cssText = 'display:flex;gap:6px;margin-bottom:6px;align-items:center;';
    row.innerHTML = `
      <input class="input dec-cond-desc" style="flex:1;font-size:12px;" placeholder="${t('suppliers.condition_desc_placeholder')}">
      <input class="input dec-cond-days" type="number" min="1" max="365" value="30"
        style="width:60px;font-size:12px;" title="${t('suppliers.hint_days_to_comply')}">
      <button type="button" class="btn btn-sm" style="padding:4px 8px;color:#dc2626;"
        onclick="this.parentElement.remove()">X</button>`;
    list.appendChild(row);
  }

  // --- Legacy sign-off (retrocompat con el endpoint antiguo) ---
  async function _recordSignOff(supplierId, type) {
    const signedBy = prompt('Nombre del firmante:');
    if (!signedBy) return;
    try {
      await Api.patch('/api/suppliers/' + supplierId + '/sign-off', { type, signed_by: signedBy });
      UI.toast(type.toUpperCase() + ' registrado', 'success');
      _renderLifecycleSection(supplierId, null);
    } catch (e) { UI.toast(e.message || 'Error al registrar firma', 'error'); }
  }

  async function _saveConcentrationMitigation(supplierId) {
    const notes = document.getElementById('lc-concentration-notes')?.value.trim() || '';
    const exitStrategy = document.getElementById('lc-exit-strategy')?.value.trim() || '';
    try {
      await Api.patch('/api/suppliers/' + supplierId + '/concentration-mitigation', { notes, exit_strategy: exitStrategy });
      UI.toast('Mitigación de concentracion guardada', 'success');
    } catch (e) { UI.toast(e.message || t('suppliers.err_save_mitigation'), 'error'); }
  }

  // --- Admin: config del gate ---
  async function _openGateConfig() {
    let cfg = {};
    try { cfg = await Api.get('/api/onboarding-gate/config'); } catch (_) {}

    const chain = cfg.sign_off_chain || [];

    UI.modal(t('suppliers.modal_gate_config'), `
      <div class="span2" style="display:flex;flex-direction:column;gap:16px;">
        <div>
          <strong style="font-size:13px;color:var(--brand-purple);display:block;margin-bottom:8px;">Umbrales de score TPRM</strong>
          <div style="display:flex;gap:12px;flex-wrap:wrap;">
            <div style="flex:1;min-width:140px;">
              <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Auto-aprobacion por debajo de</label>
              <input id="gc-auto-below" type="number" min="0" max="100" class="input" value="${cfg.auto_approve_below ?? 30}">
              <p style="font-size:10px;color:var(--text-muted);margin:2px 0 0;">Score &lt; X: alta directa sin revisor</p>
            </div>
            <div style="flex:1;min-width:140px;">
              <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Revisión manual por encima de</label>
              <input id="gc-manual-above" type="number" min="0" max="100" class="input" value="${cfg.manual_review_above ?? 60}">
              <p style="font-size:10px;color:var(--text-muted);margin:2px 0 0;">Score &gt; X: revisor CISO obligatorio</p>
            </div>
          </div>
        </div>

        <div>
          <strong style="font-size:13px;color:var(--brand-purple);display:block;margin-bottom:8px;">Política de bypass y forzado</strong>
          <div style="display:flex;gap:12px;flex-wrap:wrap;">
            <div style="flex:1;min-width:140px;">
              <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Rol mínimo para bypass</label>
              <select id="gc-bypass-role" class="input">
                <option value="admin" ${cfg.bypass_min_role === 'admin' ? 'selected' : ''}>Solo admin</option>
                <option value="analyst" ${cfg.bypass_min_role === 'analyst' ? 'selected' : ''}>Analyst o superior</option>
              </select>
            </div>
            <div style="flex:1;min-width:140px;display:flex;flex-direction:column;gap:6px;padding-top:20px;">
              <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;">
                <input type="checkbox" id="gc-bypass-justif" ${cfg.bypass_requires_justification !== false ? 'checked' : ''}>
                Justificacion obligatoria
              </label>
              <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;">
                <input type="checkbox" id="gc-force-allowed" ${cfg.force_controls_allowed !== false ? 'checked' : ''}>
                Permitir forzar controles
              </label>
            </div>
          </div>
        </div>

        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <strong style="font-size:13px;color:var(--brand-purple);">Cadena de firmas</strong>
            <button type="button" class="btn btn-sm" id="gc-add-item">+ Añadir item</button>
          </div>
          <p style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">
            Define los documentos/aprobaciones en orden. Cada empresa configura la suya.
            <em>score_gate</em>: solo aplica si el score supera ese valor.
            <em>depends_on</em>: ID del item que debe firmarse antes.
            <em>required_if</em>: is_data_processor, is_nis2, is_dora, cross_border_transfers.
          </p>
          <div style="display:grid;grid-template-columns:120px 1fr 160px 120px 90px auto 32px;gap:8px;margin-bottom:4px;">
            <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;">ID</span>
            <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;">Etiqueta</span>
            <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;">Required if</span>
            <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;">Depends on</span>
            <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;">Score &gt;</span>
            <span style="font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;">Flags</span>
            <span></span>
          </div>
          <div id="gc-chain-list">
            ${chain.map((it, i) => _gateChainItemRow(it, i)).join('')}
          </div>
        </div>
      </div>
    `, {
      actions: `
        <button class="btn" onclick="UI.closeModal()">Cancelar</button>
        <button class="btn btn-primary" id="gc-save">Guardar configuración</button>`,
    });

    document.getElementById('gc-add-item').onclick = () => {
      const list = document.getElementById('gc-chain-list');
      if (!list) return;
      const idx = list.children.length;
      const div = document.createElement('div');
      div.innerHTML = _gateChainItemRow({ id: '', label: '', required: false, bypass_allowed: true }, idx);
      list.appendChild(div.firstElementChild);
    };

    document.getElementById('gc-save').onclick = async () => {
      const autoBelow = parseInt(document.getElementById('gc-auto-below')?.value || '30', 10);
      const manualAbove = parseInt(document.getElementById('gc-manual-above')?.value || '60', 10);
      if (autoBelow >= manualAbove) { UI.toast('auto_approve_below debe ser menor que manual_review_above', 'error'); return; }

      const chainItems = [...document.querySelectorAll('.gc-chain-row')].map(row => ({
        id: row.querySelector('.gc-item-id')?.value.trim() || '',
        label: row.querySelector('.gc-item-label')?.value.trim() || '',
        required: row.querySelector('.gc-item-required')?.checked || false,
        required_if: row.querySelector('.gc-item-req-if')?.value || null,
        depends_on: row.querySelector('.gc-item-dep')?.value.trim() || null,
        score_gate: parseInt(row.querySelector('.gc-item-score-gate')?.value || '0', 10) || null,
        bypass_allowed: row.querySelector('.gc-item-bypass')?.checked !== false,
      })).filter(it => it.id && it.label);

      try {
        await Api.put('/api/onboarding-gate/config', {
          auto_approve_below: autoBelow,
          manual_review_above: manualAbove,
          bypass_min_role: document.getElementById('gc-bypass-role')?.value || 'admin',
          bypass_requires_justification: document.getElementById('gc-bypass-justif')?.checked !== false,
          force_controls_allowed: document.getElementById('gc-force-allowed')?.checked !== false,
          sign_off_chain: chainItems,
        });
        UI.closeModal();
        UI.toast('Configuración guardada', 'success');
        if (_currentSupplierId) _renderLifecycleSection(_currentSupplierId, null);
      } catch (e) { UI.toast(e.message || 'Error al guardar', 'error'); }
    };
  }

  function _gateChainItemRow(it, idx) {
    const reqIfOpts = ['', 'is_data_processor', 'is_nis2', 'is_dora', 'cross_border_transfers', 'is_ens'];
    return `
      <div class="gc-chain-row" style="display:grid;grid-template-columns:120px 1fr 160px 120px 90px auto 32px;gap:8px;align-items:center;margin-bottom:6px;">
        <input class="input gc-item-id" style="font-size:12px;" placeholder="${t('suppliers.ph_unique_id')}" value="${UI.esc(it.id || '')}">
        <input class="input gc-item-label" style="font-size:12px;" placeholder="Etiqueta visible" value="${UI.esc(it.label || '')}">
        <select class="input gc-item-req-if" style="font-size:12px;">
          ${reqIfOpts.map(o => `<option value="${o}" ${it.required_if === o ? 'selected' : ''}>${o || 'siempre'}</option>`).join('')}
        </select>
        <input class="input gc-item-dep" style="font-size:12px;" placeholder="depends_on ID" value="${UI.esc(it.depends_on || '')}">
        <input class="input gc-item-score-gate" type="number" min="0" max="100" style="font-size:12px;" placeholder="score >" value="${it.score_gate || ''}">
        <div style="display:flex;align-items:center;gap:12px;">
          <label title="Obligatorio siempre" style="font-size:11px;cursor:pointer;display:flex;align-items:center;gap:4px;white-space:nowrap;">
            <input type="checkbox" class="gc-item-required" ${it.required ? 'checked' : ''}> Obligatorio
          </label>
          <label title="${t('suppliers.hint_skippable')}" style="font-size:11px;cursor:pointer;display:flex;align-items:center;gap:4px;white-space:nowrap;">
            <input type="checkbox" class="gc-item-bypass" ${it.bypass_allowed !== false ? 'checked' : ''}> Omitible
          </label>
        </div>
        <button type="button" style="font-size:12px;background:none;border:none;color:#dc2626;cursor:pointer;padding:0;line-height:1;"
          onclick="this.closest('.gc-chain-row').remove()" title="${t('suppliers.remove_item')}">X</button>
      </div>`;
  }

  // ======== EXPEDIENTE COMPLETO DEL PROVEEDOR ========

  let _currentFileSupplier = null;
  let _currentFileDocPending = null;

  function _openSupplierFile(sup) {
    _currentFileSupplier = sup;
    let overlay = document.getElementById('sup-file-overlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'sup-file-overlay';
      document.body.appendChild(overlay);
    }
    overlay.style.cssText = 'position:fixed;inset:0;z-index:1000;background:var(--bg-1);display:flex;flex-direction:column;overflow:hidden;';
    const stageLabel = LIFECYCLE_STAGES().find(x => x.id === sup.lifecycle_stage)?.label || sup.lifecycle_stage || window.t('suppliers.undefined_stage');
    const tierColor = RISK_COLORS[sup.tier] || '#888';
    overlay.innerHTML = `
      <div style="flex-shrink:0;padding:14px 24px;border-bottom:2px solid var(--border);background:var(--bg-2);display:flex;align-items:center;gap:16px;box-shadow:0 1px 4px rgba(0,0,0,.06);">
        <div style="flex:1;min-width:0;">
          <div style="font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:2px;">${window.t('suppliers.file_header')}</div>
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
            <span style="font-size:20px;font-weight:800;color:var(--text-1);">${UI.esc(sup.name)}</span>
            <span style="font-size:11px;color:var(--text-muted);background:var(--bg-1);padding:2px 8px;border-radius:999px;font-weight:600;border:1px solid var(--border);">${UI.esc(sup.code)}</span>
            ${sup.tier ? `<span style="font-size:11px;font-weight:700;color:#fff;background:${tierColor};padding:2px 8px;border-radius:999px;">${RISK_LABELS()[sup.tier]||sup.tier}</span>` : ''}
            ${sup.is_critical ? `<span style="font-size:11px;font-weight:700;color:#fff;background:#DC2626;padding:2px 8px;border-radius:999px;">${window.t('suppliers.critical_badge')}</span>` : ''}
          </div>
          <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">
            Stage: <strong>${UI.esc(stageLabel)}</strong>
            ${sup.inherent_risk_score != null ? ` &bull; Inherent: <strong>${sup.inherent_risk_score}</strong>` : ''}
            ${sup.residual_risk_score != null ? ` &bull; Residual: <strong>${sup.residual_risk_score}</strong>` : ''}
          </div>
        </div>
        <div style="display:flex;gap:8px;flex-shrink:0;">
          ${Auth.canEdit() ? `<button class="btn btn-sm btn-primary" onclick="ViewSuppliers._openFormFromFile()">${window.t('suppliers.edit_data_btn')}</button>` : ''}
          <button onclick="ViewSuppliers._closeSupplierFile()" class="btn btn-sm" style="font-size:18px;line-height:1;padding:4px 12px;" title="${t('common.close')}">&times;</button>
        </div>
      </div>
      <div style="flex-shrink:0;display:flex;border-bottom:1px solid var(--border);background:var(--bg-2);padding:0 20px;overflow-x:auto;">
        ${[['perfil',window.t('suppliers.detail_profile')],['gate',window.t('suppliers.detail_gate')],['cuestionarios',window.t('suppliers.detail_questionnaires')],['documentos',window.t('suppliers.detail_documents')],['hallazgos',window.t('suppliers.detail_findings')]].map(([t,lbl],i) =>
          `<button id="fbtab-${t}" onclick="ViewSuppliers._setFileTab('${t}')"
            style="padding:10px 18px;font-size:13px;font-weight:600;border:none;background:none;cursor:pointer;white-space:nowrap;
              border-bottom:2px solid ${i===0?'var(--brand-purple)':'transparent'};
              color:${i===0?'var(--brand-purple)':'var(--text-muted)'};transition:color .15s,border-color .15s;">
            ${lbl}
          </button>`).join('')}
      </div>
      <div id="sup-file-content" style="flex:1;overflow-y:auto;padding:24px;max-width:1400px;width:100%;margin:0 auto;box-sizing:border-box;"></div>
    `;
    _setFileTab('perfil');
  }

  function _closeSupplierFile() {
    const overlay = document.getElementById('sup-file-overlay');
    if (overlay) overlay.style.display = 'none';
    _currentFileSupplier = null;
  }

  function _openFormFromFile() {
    const sup = _currentFileSupplier;
    if (!sup) return;
    _closeSupplierFile();
    _openForm(sup);
  }

  function _setFileTab(tab) {
    ['perfil','gate','cuestionarios','documentos','hallazgos'].forEach((t) => {
      const btn = document.getElementById('fbtab-' + t);
      if (!btn) return;
      btn.style.borderBottomColor = t === tab ? 'var(--brand-purple)' : 'transparent';
      btn.style.color = t === tab ? 'var(--brand-purple)' : 'var(--text-muted)';
    });
    const content = document.getElementById('sup-file-content');
    if (!content || !_currentFileSupplier) return;
    const sup = _currentFileSupplier;
    if (tab === 'perfil') _renderFileTabPerfil(content, sup);
    else if (tab === 'gate') _renderFileTabGate(content, sup);
    else if (tab === 'cuestionarios') _renderFileTabCuestionarios(content, sup);
    else if (tab === 'documentos') _renderFileTabDocumentos(content, sup);
    else if (tab === 'hallazgos') _renderFileTabHallazgos(content, sup);
  }

  function _infoField(label, value) {
    return `<div>
      <div style="font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">${label}</div>
      <div style="font-size:14px;color:var(--text-1);">${value || '<span style="color:var(--text-muted);">—</span>'}</div>
    </div>`;
  }

  function _renderFileTabPerfil(wrap, sup) {
    const flags = [];
    if (sup.is_nis2) flags.push('<span style="font-size:11px;font-weight:700;background:#EDE9FE;color:#6D28D9;padding:2px 8px;border-radius:999px;">NIS2</span>');
    if (sup.is_dora) flags.push('<span style="font-size:11px;font-weight:700;background:#DBEAFE;color:#1E40AF;padding:2px 8px;border-radius:999px;">DORA</span>');
    if (sup.is_ens) flags.push('<span style="font-size:11px;font-weight:700;background:#D1FAE5;color:#065F46;padding:2px 8px;border-radius:999px;">ENS</span>');
    if (sup.is_data_processor) flags.push('<span style="font-size:11px;font-weight:700;background:#FEF3C7;color:#92400E;padding:2px 8px;border-radius:999px;">Encargado GDPR</span>');
    if (sup.processes_personal_data) flags.push('<span style="font-size:11px;font-weight:700;background:#FEF3C7;color:#92400E;padding:2px 8px;border-radius:999px;">Trata datos personales</span>');
    if (sup.cross_border_transfers) flags.push('<span style="font-size:11px;font-weight:700;background:#FEF3C7;color:#92400E;padding:2px 8px;border-radius:999px;">Transf. internac.</span>');
    if (sup.email_origin) flags.push('<span style="font-size:11px;font-weight:700;background:#E0F2FE;color:#075985;padding:2px 8px;border-radius:999px;">Alta por email</span>');
    if (sup.email_needs_review) flags.push('<span style="font-size:11px;font-weight:700;background:#FEE2E2;color:#991B1B;padding:2px 8px;border-radius:999px;">Pendiente de revisión</span>');
    const slas = sup.slas || [];
    const contacts = sup.additional_contacts || [];
    wrap.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px;margin-bottom:20px;">
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:20px;">
          <div style="font-size:11px;font-weight:700;color:var(--brand-purple);text-transform:uppercase;letter-spacing:.04em;margin-bottom:14px;">Información general</div>
          <div style="display:grid;gap:12px;">
            ${_infoField(t('suppliers.fld_name'), UI.esc(sup.name))}
            ${_infoField('Codigo', UI.esc(sup.code))}
            ${_infoField('Categoria', UI.esc(sup.category))}
            ${_infoField(t('suppliers.fld_type'), UI.esc(sup.vendor_type))}
            ${_infoField('Ubicacion', UI.esc(sup.location))}
            ${_infoField('Departamento', UI.esc(sup.department))}
            ${_infoField('Referencia contrato', UI.esc(sup.contract_ref))}
          </div>
        </div>
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:20px;">
          <div style="font-size:11px;font-weight:700;color:var(--brand-purple);text-transform:uppercase;letter-spacing:.04em;margin-bottom:14px;">Riesgo TPRM</div>
          <div style="display:grid;gap:12px;">
            ${_infoField('Tier', sup.tier ? `<span style="font-weight:700;color:${RISK_COLORS[sup.tier]||'#888'}">${RISK_LABELS()[sup.tier]||sup.tier}</span>` : null)}
            ${_infoField('Score inherente', sup.inherent_risk_score != null ? `<span style="font-size:22px;font-weight:800;">${sup.inherent_risk_score}</span><span style="font-size:11px;color:var(--text-muted);">/100</span>` : null)}
            ${_infoField('Score residual', sup.residual_risk_score != null ? `<span style="font-size:22px;font-weight:800;">${sup.residual_risk_score}</span><span style="font-size:11px;color:var(--text-muted);">/100</span>` : null)}
            ${_infoField('Acceso a sistemas', UI.esc(sup.system_access_type))}
            ${_infoField('Sensibilidad datos', sup.data_sensitivity ? `${sup.data_sensitivity}/5` : null)}
            ${_infoField('Criticidad negocio', sup.business_criticality ? `${sup.business_criticality}/5` : null)}
          </div>
        </div>
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:20px;">
          <div style="font-size:11px;font-weight:700;color:var(--brand-purple);text-transform:uppercase;letter-spacing:.04em;margin-bottom:14px;">Contacto principal</div>
          <div style="display:grid;gap:12px;">
            ${_infoField(t('suppliers.fld_name'), UI.esc(sup.contact_name))}
            ${_infoField('Email', sup.contact_email ? `<a href="mailto:${UI.esc(sup.contact_email)}" style="color:var(--brand-purple);">${UI.esc(sup.contact_email)}</a>` : null)}
            ${_infoField('CC alertas', sup.cc_email ? `<a href="mailto:${UI.esc(sup.cc_email)}" style="color:var(--brand-purple);">${UI.esc(sup.cc_email)}</a>` : null)}
            ${_infoField(t('suppliers.fld_next_assessment'), sup.next_assessment_at ? sup.next_assessment_at.slice(0,10) : null)}
            ${_infoField(t('suppliers.fld_last_assessment'), sup.last_assessment_at ? sup.last_assessment_at.slice(0,10) : null)}
          </div>
        </div>
      </div>
      ${flags.length ? `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px 20px;margin-bottom:20px;">
        <div style="font-size:11px;font-weight:700;color:var(--brand-purple);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px;">Regulacion y clasificación</div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;">${flags.join('')}</div>
      </div>` : ''}
      <!-- Trust Portal IA -->
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px 20px;margin-bottom:20px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
          <div style="font-size:11px;font-weight:700;color:var(--brand-purple);text-transform:uppercase;letter-spacing:.04em;">Trust Portal IA</div>
          ${sup.trust_portal_url ? `<button id="btn-scrape-tp" class="btn btn-sm btn-primary" style="font-size:12px;">Analizar Trust Portal</button>` : ''}
        </div>
        ${sup.trust_portal_url ? `
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
            <a href="${UI.esc(sup.trust_portal_url)}" target="_blank" rel="noopener noreferrer" style="font-size:13px;color:var(--brand-purple);word-break:break-all;">${UI.esc(sup.trust_portal_url)}</a>
          </div>
          ${sup.trust_portal_last_scraped_at ? `<div style="font-size:11px;color:var(--text-muted);">Último análisis: ${sup.trust_portal_last_scraped_at.slice(0,10)}</div>` : '<div style="font-size:11px;color:var(--text-muted);">Sin analizar todavia. Pulsa "Analizar Trust Portal" para que el agente IA extraiga la información.</div>'}
        ` : `<div style="font-size:12px;color:var(--text-muted);">Configura una URL de Trust Portal en la edicion del proveedor para activar el análisis automático por IA.</div>`}
        <div id="tp-scrape-result" style="margin-top:8px;"></div>
      </div>

      ${sup.notes ? `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px 20px;margin-bottom:20px;">
        <div style="font-size:11px;font-weight:700;color:var(--brand-purple);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px;">Notas</div>
        <div style="font-size:13px;color:var(--text-1);white-space:pre-wrap;">${UI.esc(sup.notes)}</div>
      </div>` : ''}
      ${contacts.length ? `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px 20px;margin-bottom:20px;">
        <div style="font-size:11px;font-weight:700;color:var(--brand-purple);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px;">Contactos adicionales</div>
        ${contacts.map(c => `<div style="display:flex;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);">
          <div style="flex:1;font-size:13px;">${UI.esc(c.name||'')} ${c.role ? `<span style="color:var(--text-muted);font-size:11px;">(${UI.esc(c.role)})</span>` : ''}</div>
          <div style="font-size:12px;">${c.email ? `<a href="mailto:${UI.esc(c.email)}" style="color:var(--brand-purple);">${UI.esc(c.email)}</a>` : ''}</div>
        </div>`).join('')}
      </div>` : ''}
      ${slas.length ? `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px 20px;">
        <div style="font-size:11px;font-weight:700;color:var(--brand-purple);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px;">SLAs</div>
        ${slas.map(sla => `<div style="padding:8px 0;border-bottom:1px solid var(--border);">
          <div style="font-size:13px;font-weight:600;">${UI.esc(sla.name||'')} <span style="font-size:11px;color:var(--text-muted);">(${UI.esc(sla.category||'')})</span></div>
          ${sla.metric ? `<div style="font-size:12px;color:var(--text-muted);">${UI.esc(sla.metric)}</div>` : ''}
        </div>`).join('')}
      </div>` : ''}
    `;

    // Boton de análisis IA del trust portal
    const btnScrape = document.getElementById('btn-scrape-tp');
    if (btnScrape) {
      btnScrape.onclick = async () => {
        const resultEl = document.getElementById('tp-scrape-result');
        btnScrape.disabled = true;
        btnScrape.textContent = 'Analizando...';
        if (resultEl) resultEl.innerHTML = '<span style="font-size:12px;color:var(--text-muted);">El agente esta descargando y analizando el trust portal. Esto puede tardar unos segundos...</span>';
        try {
          const res = await API.post(`/api/suppliers/${sup.id}/scrape-trust-portal`, {});
          if (res.ok) {
            const fields = (res.updated_fields || []).join(', ');
            if (resultEl) resultEl.innerHTML = `
              <div style="background:#D1FAE5;color:#065F46;border-radius:6px;padding:10px 14px;font-size:12px;margin-top:4px;">
                <strong>Análisis completado.</strong> ${UI.esc(res.message)}<br>
                ${fields ? `<span style="opacity:.8;">Campos actualizados: ${UI.esc(fields)}</span>` : ''}
              </div>`;
            // Refrescar la ficha para mostrar los datos nuevos
            setTimeout(async () => {
              try {
                const updated = await API.get(`/api/suppliers/${sup.id}`);
                _currentFileSupplier = updated;
                _renderFileTabPerfil(wrap, updated);
              } catch (_) {}
            }, 1200);
          } else {
            if (resultEl) resultEl.innerHTML = `<div style="background:#FEE2E2;color:#991B1B;border-radius:6px;padding:10px 14px;font-size:12px;margin-top:4px;">${UI.esc(res.message || t('suppliers.err_analysis'))}</div>`;
            btnScrape.disabled = false;
            btnScrape.textContent = 'Analizar Trust Portal';
          }
        } catch (err) {
          if (resultEl) resultEl.innerHTML = `<div style="background:#FEE2E2;color:#991B1B;border-radius:6px;padding:10px 14px;font-size:12px;margin-top:4px;">Error de conexión: ${UI.esc(String(err))}</div>`;
          btnScrape.disabled = false;
          btnScrape.textContent = 'Analizar Trust Portal';
        }
      };
    }
  }

  async function _renderFileTabGate(wrap, sup) {
    wrap.innerHTML = `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:20px;">
        <strong style="font-size:13px;color:var(--brand-purple);">Ciclo de vida y gate de onboarding</strong>
        <div id="sup-lifecycle-container" style="margin-top:12px;"><p style="font-size:12px;color:var(--text-muted);">Cargando...</p></div>
      </div>
    `;
    await _renderLifecycleSection(sup.id, sup);
  }

  async function _renderFileTabCuestionarios(wrap, sup) {
    wrap.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <strong style="font-size:15px;">Cuestionarios — ${UI.esc(sup.name)}</strong>
      </div>
      <div id="sup-file-qs-list"><p style="color:var(--text-muted);">Cargando...</p></div>
    `;
    const qWrap = document.getElementById('sup-file-qs-list');
    try {
      const data = await Api.supplier_questionnaires.list({ supplier_id: sup.id });
      if (!qWrap) return;
      if (!data.length) {
        qWrap.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:40px 0;">Sin cuestionarios para este proveedor. Crea uno desde la pestaña Cuestionarios del módulo de Proveedores.</p>';
        return;
      }
      const now = new Date();
      qWrap.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr><th>Código</th><th>Título</th><th>Tipo</th><th>Puntuación</th><th>Respondido</th><th>Expira</th><th>Evaluación IA</th><th></th></tr></thead>
        <tbody>
          ${data.map(q => {
            const submitted = q.submitted_at ? new Date(q.submitted_at).toLocaleDateString('es-ES') : null;
            const expired = q.expires_at && new Date(q.expires_at) < now && !q.submitted_at;
            const expires = q.expires_at ? new Date(q.expires_at).toLocaleDateString('es-ES') : '-';
            const isInternal = q.assignment_type === 'internal';
            const typeHtml = isInternal
              ? '<span style="font-size:10px;font-weight:600;background:#EDE9FE;color:#7C3AED;padding:2px 6px;border-radius:4px;">Interno</span>'
              : '<span style="font-size:10px;font-weight:600;background:#E0F2FE;color:#0369A1;padding:2px 6px;border-radius:4px;">Externo</span>';
            let scoreHtml = '-';
            if (q.score !== null && q.score !== undefined) {
              const sc = q.score;
              const c = sc >= 80 ? '#22C55E' : sc >= 60 ? '#F59E0B' : '#EF4444';
              scoreHtml = `<span style="font-weight:700;color:${c};">${sc}/100</span>`;
            }
            let aiHtml = '-';
            if (q.ai_review && !q.ai_review.error) {
              const asc = q.ai_review.ai_score;
              const ac = asc >= 80 ? '#22C55E' : asc >= 60 ? '#F59E0B' : '#EF4444';
              aiHtml = `<span style="font-weight:700;color:${ac};">${asc}/100</span>`;
            }
            const rwBadge = q.regwatch_review_at
              ? `<span style="display:inline-block;margin-left:6px;font-size:9px;font-weight:700;background:#FEF3C7;color:#92400E;border:1px solid #FCD34D;padding:1px 5px;border-radius:4px;vertical-align:middle;" title="Revisión normativa requerida">NORM</span>`
              : '';
            return `<tr style="${expired?'opacity:.6;':''}${q.regwatch_review_at?'border-left:3px solid #F59E0B;':''}">
              <td>${UI.codePill(q.code)}</td>
              <td><strong>${UI.esc(q.title)}</strong>${rwBadge}</td>
              <td>${typeHtml}</td>
              <td>${scoreHtml}</td>
              <td style="font-size:12px;">${submitted || (expired ? '<span style="color:#EF4444;font-size:11px;">Expirado</span>' : '<span style="color:#F59E0B;font-size:11px;">Pendiente</span>')}</td>
              <td style="font-size:12px;">${expires}</td>
              <td style="font-size:12px;">${aiHtml}</td>
              <td>
                ${!q.submitted_at && !isInternal ? `<button class="btn btn-sm" data-qid="${q.id}" data-qact="link">Copiar enlace</button>` : ''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
      qWrap.querySelectorAll('[data-qact="link"]').forEach(btn => {
        const q = data.find(x => x.id == btn.dataset.qid);
        if (!q) return;
        btn.onclick = () => {
          const link = location.origin + '/supplier-q?token=' + encodeURIComponent(q.token);
          navigator.clipboard.writeText(link).then(() => UI.toast('Enlace copiado al portapapeles', 'success')).catch(() => {});
        };
      });
    } catch (e) {
      if (qWrap) qWrap.innerHTML = `<p style="color:var(--risk-high);">${UI.esc(e.message)}</p>`;
    }
  }

  async function _renderFileTabDocumentos(wrap, sup) {
    wrap.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <strong style="font-size:15px;">Documentación — ${UI.esc(sup.name)}</strong>
        ${Auth.canEdit() ? `<label class="btn btn-sm btn-primary" style="cursor:pointer;">
          + Adjuntar
          <input type="file" id="file-doc-upload" style="display:none;"
            accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.csv,.png,.jpg,.jpeg,.zip">
        </label>` : ''}
      </div>
      <div id="file-doc-desc-row" style="display:none;gap:6px;align-items:center;margin-bottom:12px;">
        <input id="file-doc-desc" class="input" placeholder="${t('suppliers.doc_desc_placeholder')}" style="flex:1;font-size:12px;">
        <button id="file-doc-confirm" class="btn btn-sm btn-primary">Subir</button>
        <button id="file-doc-cancel" class="btn btn-sm">Cancelar</button>
      </div>
      <div id="sup-doc-list"><p style="font-size:12px;color:var(--text-muted);">Cargando...</p></div>
    `;
    _loadDocuments(sup.id);
    const uploadInput = document.getElementById('file-doc-upload');
    const descRow = document.getElementById('file-doc-desc-row');
    if (uploadInput) {
      uploadInput.onchange = () => {
        _currentFileDocPending = uploadInput.files[0] || null;
        if (_currentFileDocPending && descRow) descRow.style.display = 'flex';
      };
    }
    const confirmBtn = document.getElementById('file-doc-confirm');
    if (confirmBtn) {
      confirmBtn.onclick = async () => {
        if (!_currentFileDocPending) return;
        const desc = document.getElementById('file-doc-desc')?.value.trim() || '';
        confirmBtn.disabled = true; confirmBtn.textContent = 'Subiendo...';
        try {
          await Api.suppliers.uploadDocument(sup.id, _currentFileDocPending, desc || undefined);
          UI.toast('Documento adjuntado', 'success');
          _currentFileDocPending = null;
          if (uploadInput) uploadInput.value = '';
          if (descRow) descRow.style.display = 'none';
          _loadDocuments(sup.id);
        } catch (e) { UI.toast(e.message, 'error'); }
        finally { confirmBtn.disabled = false; confirmBtn.textContent = t('common.upload'); }
      };
    }
    const cancelBtn = document.getElementById('file-doc-cancel');
    if (cancelBtn) {
      cancelBtn.onclick = () => {
        _currentFileDocPending = null;
        if (uploadInput) uploadInput.value = '';
        if (descRow) descRow.style.display = 'none';
      };
    }
  }

  async function _renderFileTabHallazgos(wrap, sup) {
    wrap.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <strong style="font-size:15px;">Hallazgos — ${UI.esc(sup.name)}</strong>
        <button class="btn btn-sm" onclick="ViewSuppliers._reloadFileHallazgos()">Actualizar</button>
      </div>
      <div id="sup-findings-list"><p style="font-size:12px;color:var(--text-muted);">Cargando...</p></div>
    `;
    _loadSupplierFindings(sup.id);
  }

  function _reloadFileHallazgos() {
    if (_currentFileSupplier) _loadSupplierFindings(_currentFileSupplier.id);
  }

  // ======== FIN EXPEDIENTE ========

  async function _loadSupplierFindings(supplierId) {
    const wrap = document.getElementById('sup-findings-list');
    if (!wrap) return;
    try {
      const result = await Api.findings.listBySupplier(supplierId);
      const items = result.items || result || [];
      if (!items.length) {
        wrap.innerHTML = '<p style="font-size:12px;color:var(--text-muted);margin:4px 0 0;">Sin hallazgos de monitoreo. El sistema escanea semanalmente sitios con website o email configurado.</p>';
        return;
      }
      const sevColor = { CRITICAL: '#DC2626', HIGH: '#D97706', MEDIUM: '#F59E0B', LOW: '#6B7280' };
      wrap.innerHTML = items.map(f => {
        const date = f.detected_at ? new Date(f.detected_at).toLocaleDateString('es-ES') : '-';
        const sev = (f.severity || 'LOW').toUpperCase();
        const color = sevColor[sev] || '#6B7280';
        const statusBadge = f.status === 'resolved'
          ? '<span style="font-size:10px;background:#D1FAE5;color:#065F46;padding:1px 6px;border-radius:999px;font-weight:600;">Resuelto</span>'
          : f.status === 'accepted'
          ? '<span style="font-size:10px;background:#EDE9FE;color:#5B21B6;padding:1px 6px;border-radius:999px;font-weight:600;">Aceptado</span>'
          : '<span style="font-size:10px;background:#FEE2E2;color:#991B1B;padding:1px 6px;border-radius:999px;font-weight:600;">Abierto</span>';
        return `<div style="border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin-bottom:4px;background:var(--bg-2);">
          <div style="display:flex;align-items:flex-start;gap:8px;">
            <span style="font-size:10px;font-weight:700;color:${color};white-space:nowrap;padding:2px 6px;background:${color}18;border-radius:999px;">${sev}</span>
            <div style="flex:1;min-width:0;">
              <div style="font-size:12px;font-weight:600;">${UI.esc(f.title)}</div>
              ${f.description ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${UI.esc(f.description)}</div>` : ''}
            </div>
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;white-space:nowrap;">
              ${statusBadge}
              <span style="font-size:10px;color:var(--text-muted);">${date}</span>
            </div>
          </div>
        </div>`;
      }).join('');
    } catch (e) {
      wrap.innerHTML = `<p style="font-size:12px;color:var(--risk-high);">${UI.esc(e.message)}</p>`;
    }
  }

  async function _loadDocuments(supplierId) {
    const wrap = document.getElementById('sup-doc-list');
    if (!wrap) return;
    try {
      const docs = await Api.suppliers.listDocuments(supplierId);
      if (!docs.length) {
        wrap.innerHTML = '<p style="font-size:12px;color:var(--text-muted);margin:4px 0 0;">Sin documentos adjuntos.</p>';
        return;
      }
      const canEdit = Auth.canEdit();
      wrap.innerHTML = docs.map(d => {
        const size = d.size ? (d.size > 1024*1024 ? (d.size/1024/1024).toFixed(1)+' MB' : (d.size/1024).toFixed(0)+' KB') : '-';
        const date = d.uploaded_at ? new Date(d.uploaded_at).toLocaleDateString('es-ES') : '-';
        const isAnalyzable = /\.(pdf|docx?|xlsx?|txt|csv)$/i.test(d.filename);
        return `<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid var(--border);border-radius:6px;margin-bottom:4px;background:var(--bg-2);">
          <div style="flex:1;min-width:0;">
            <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${UI.esc(d.filename)}</div>
            <div style="font-size:11px;color:var(--text-muted);">${size} &middot; ${date}${d.description ? ' &middot; ' + UI.esc(d.description) : ''}</div>
          </div>
          ${canEdit && isAnalyzable ? `<button class="btn btn-sm sup-doc-analyze" data-doc-id="${d.id}" data-doc-name="${UI.esc(d.filename)}"
            style="background:var(--brand-purple);color:#fff;border-color:var(--brand-purple);white-space:nowrap;"
            title="${t('suppliers.hint_ai_autofill')}">Analizar con IA</button>` : ''}
          <a href="${Api.suppliers.downloadDocumentUrl(supplierId, d.id)}" target="_blank" class="btn btn-sm" title="${t('common.download')}">${t('common.download')}</a>
          ${canEdit ? `<button class="btn btn-sm btn-danger sup-doc-del" data-doc-id="${d.id}" title="${t('common.delete')}">X</button>` : ''}
        </div>`;
      }).join('');

      wrap.querySelectorAll('.sup-doc-analyze').forEach(btn => {
        btn.onclick = () => _analyzeDocumentAI(supplierId, btn.dataset.docId, btn.dataset.docName, btn);
      });
      wrap.querySelectorAll('.sup-doc-del').forEach(btn => {
        btn.onclick = async () => {
          if (!confirm(t('suppliers.confirm_delete_document'))) return;
          try {
            await Api.suppliers.deleteDocument(supplierId, btn.dataset.docId);
            UI.toast('Documento eliminado', 'success');
            _loadDocuments(supplierId);
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) {
      wrap.innerHTML = `<p style="font-size:12px;color:var(--risk-high);">${UI.esc(e.message)}</p>`;
    }
  }

  async function _analyzeDocumentAI(supplierId, docId, docName, btn) {
    const origLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Analizando...';
    try {
      const result = await Api.suppliers.analyzeDocument(supplierId, docId);
      if (!result.ok) {
        UI.toast(result.message || t('suppliers.err_analysis'), 'error');
        return;
      }
      const fields = result.updated_fields || [];
      if (!fields.length) {
        UI.toast(t('suppliers.agent_no_new_fields'), 'info');
        return;
      }
      const fieldLabels = {
        name: t('suppliers.field_name'), description: t('suppliers.field_description'), services: t('suppliers.field_services'),
        category: t('suppliers.field_category'), vendor_type: t('suppliers.field_vendor_type'),
        contact_name: t('suppliers.field_contact_name'), contact_email: t('suppliers.field_contact_email'),
        cc_email: t('suppliers.field_cc_email'), website: t('suppliers.field_website'), country_code: t('suppliers.field_country_code'),
        contract_ref: t('suppliers.field_contract_ref'), contract_expiry: t('suppliers.field_contract_expiry'),
        location: t('suppliers.field_location'), department: t('suppliers.field_department'),
        certifications: t('suppliers.field_certifications'), notes: t('suppliers.field_notes'),
        is_data_processor: t('suppliers.field_is_data_processor'), processes_personal_data: t('suppliers.field_processes_personal_data'),
        cross_border_transfers: t('suppliers.field_cross_border_transfers'),
        is_critical: t('suppliers.field_is_critical'), is_nis2: 'NIS2', is_dora: 'DORA', is_ens: 'ENS',
        data_sensitivity: t('suppliers.field_data_sensitivity'), data_volume: t('suppliers.field_data_volume'),
        system_access_type: t('suppliers.field_system_access_type'), business_criticality: t('suppliers.field_business_criticality'),
        geographic_risk: t('suppliers.field_geographic_risk'), business_importance: t('suppliers.field_business_importance'),
        slas: 'SLAs', additional_contacts: t('suppliers.field_additional_contacts'),
      };
      const fieldList = fields.map(f => fieldLabels[f] || f).join(', ');
      UI.toast(`${fields.length} campo(s) actualizados: ${fieldList}`, 'success');

      // Recargar la ficha con los datos actualizados
      try {
        const freshSup = await Api.suppliers.get(supplierId);
        UI.closeModal();
        _openForm(freshSup);
      } catch (_) {
        // Si falla la recarga, al menos los datos ya están guardados
      }
    } catch (e) {
      UI.toast(e.message || 'Error analizando el documento', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = origLabel;
    }
  }

  // ---- SLA helpers ----

  function _slaId() {
    return 'sla_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
  }

  function _renderSlaList() {
    const wrap = document.getElementById('sup-sla-list');
    if (!wrap) return;
    if (!_currentSlas.length) {
      wrap.innerHTML = '<p style="font-size:12px;color:var(--text-muted);margin:4px 0 0;">Sin SLAs definidos.</p>';
      return;
    }
    wrap.innerHTML = _currentSlas.map((sla, i) => `
      <div style="border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin-bottom:6px;background:var(--bg-2);">
        <div style="display:flex;gap:6px;align-items:flex-start;">
          <div style="flex:1;display:grid;grid-template-columns:1fr 1fr;gap:6px;">
            <input class="input sla-name" data-idx="${i}" placeholder="${t('suppliers.ph_sla_name')}" value="${UI.esc(sla.name||'')}" style="font-size:12px;">
            <input class="input sla-metric" data-idx="${i}" placeholder="${t('suppliers.ph_sla_metric')}" value="${UI.esc(sla.metric||'')}" style="font-size:12px;">
            <select class="input sla-cat" data-idx="${i}" style="font-size:12px;">
              ${['availability','support','security','performance','recovery','other'].map(c =>
                `<option value="${c}" ${(sla.category||'other')===c?'selected':''}>${c}</option>`
              ).join('')}
            </select>
            <input class="input sla-desc" data-idx="${i}" placeholder="${t('suppliers.short_desc_placeholder')}" value="${UI.esc(sla.description||'')}" style="font-size:12px;">
          </div>
          <button type="button" class="btn btn-sm btn-danger sla-del" data-idx="${i}" style="padding:3px 8px;font-size:12px;margin-top:2px;">X</button>
        </div>
      </div>`).join('');

    // Sync changes back to _currentSlas
    wrap.querySelectorAll('.sla-name').forEach(inp => {
      inp.oninput = () => { _currentSlas[parseInt(inp.dataset.idx)].name = inp.value; };
    });
    wrap.querySelectorAll('.sla-metric').forEach(inp => {
      inp.oninput = () => { _currentSlas[parseInt(inp.dataset.idx)].metric = inp.value; };
    });
    wrap.querySelectorAll('.sla-cat').forEach(sel => {
      sel.onchange = () => { _currentSlas[parseInt(sel.dataset.idx)].category = sel.value; };
    });
    wrap.querySelectorAll('.sla-desc').forEach(inp => {
      inp.oninput = () => { _currentSlas[parseInt(inp.dataset.idx)].description = inp.value; };
    });
    wrap.querySelectorAll('.sla-del').forEach(btn => {
      btn.onclick = () => {
        _currentSlas.splice(parseInt(btn.dataset.idx), 1);
        _renderSlaList();
      };
    });
  }

  function _addSlaRow() {
    _currentSlas.push({ id: _slaId(), name: '', metric: '', category: 'other', description: '' });
    _renderSlaList();
    const inputs = document.querySelectorAll('.sla-name');
    if (inputs.length) inputs[inputs.length - 1].focus();
  }

  // ---- Contactos adicionales helpers ----

  function _renderContactList() {
    const wrap = document.getElementById('sup-contact-list');
    if (!wrap) return;
    if (!_currentContacts.length) {
      wrap.innerHTML = '<p style="font-size:12px;color:var(--text-muted);margin:4px 0 0;">Sin contactos adicionales.</p>';
      return;
    }
    wrap.innerHTML = _currentContacts.map((c, i) => `
      <div style="border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin-bottom:6px;background:var(--bg-2);">
        <div style="display:flex;gap:6px;align-items:flex-start;">
          <div style="flex:1;display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;">
            <input class="input ct-name" data-idx="${i}" placeholder="${t('suppliers.ph_contact_name')}" value="${UI.esc(c.name||'')}" style="font-size:12px;">
            <input class="input ct-email" data-idx="${i}" placeholder="Email *" type="email" value="${UI.esc(c.email||'')}" style="font-size:12px;">
            <input class="input ct-role" data-idx="${i}" placeholder="${t('suppliers.ph_contact_role')}" value="${UI.esc(c.role||'')}" style="font-size:12px;">
          </div>
          <button type="button" class="btn btn-sm btn-danger ct-del" data-idx="${i}" style="padding:3px 8px;font-size:12px;margin-top:2px;">X</button>
        </div>
      </div>`).join('');
    wrap.querySelectorAll('.ct-name').forEach(inp => {
      inp.oninput = () => { _currentContacts[parseInt(inp.dataset.idx)].name = inp.value; };
    });
    wrap.querySelectorAll('.ct-email').forEach(inp => {
      inp.oninput = () => { _currentContacts[parseInt(inp.dataset.idx)].email = inp.value; };
    });
    wrap.querySelectorAll('.ct-role').forEach(inp => {
      inp.oninput = () => { _currentContacts[parseInt(inp.dataset.idx)].role = inp.value; };
    });
    wrap.querySelectorAll('.ct-del').forEach(btn => {
      btn.onclick = () => {
        _currentContacts.splice(parseInt(btn.dataset.idx), 1);
        _renderContactList();
      };
    });
  }

  function _addContactRow() {
    _currentContacts.push({ name: '', email: '', role: '' });
    _renderContactList();
    const inputs = document.querySelectorAll('.ct-name');
    if (inputs.length) inputs[inputs.length - 1].focus();
  }

  async function _save(s) {
    const name = document.getElementById('f-name').value.trim();
    if (!name) { UI.toast('El nombre es obligatorio', 'error'); return; }
    const internalOwnerVal = document.getElementById('f-internal-owner')?.value;
    const bizImpVal = document.getElementById('f-biz-imp')?.value;
    const payload = {
      name,
      category: document.getElementById('f-cat').value.trim(),
      risk_level: document.getElementById('f-risk-level').value,
      is_critical: document.getElementById('f-critical').checked,
      contact_name: document.getElementById('f-contact').value.trim(),
      contact_email: document.getElementById('f-email').value.trim(),
      cc_email: document.getElementById('f-cc-email')?.value.trim() || null,
      additional_contacts: _currentContacts.filter(c => c.name?.trim() && c.email?.trim()).map(c => ({
        name: c.name.trim(), email: c.email.trim(), role: c.role?.trim() || null,
      })),
      location: document.getElementById('f-location')?.value.trim() || null,
      department: document.getElementById('f-department')?.value.trim() || null,
      business_importance: bizImpVal ? (parseInt(bizImpVal) || null) : null,
      internal_owner_id: internalOwnerVal ? (parseInt(internalOwnerVal) || null) : null,
      last_assessment_at: document.getElementById('f-last-assess').value || null,
      next_assessment_at: document.getElementById('f-next-assess').value || null,
      contract_ref: document.getElementById('f-contract').value.trim(),
      notes: document.getElementById('f-notes').value.trim(),
      vendor_type: document.getElementById('f-vendor-type').value,
      system_access_type: document.getElementById('f-access').value,
      data_sensitivity: parseInt(document.getElementById('f-data-sens').value) || 2,
      data_volume: parseInt(document.getElementById('f-data-vol').value) || 2,
      business_criticality: parseInt(document.getElementById('f-biz-crit').value) || 3,
      geographic_risk: parseInt(document.getElementById('f-geo').value) || 1,
      is_data_processor: document.getElementById('f-proc').checked,
      processes_personal_data: document.getElementById('f-pii').checked,
      is_nis2: document.getElementById('f-nis2').checked,
      is_dora: document.getElementById('f-dora').checked,
      is_ens: document.getElementById('f-ens').checked,
      slas: _currentSlas.filter(sl => sl.name?.trim()).map(sl => ({
        id: sl.id || _slaId(),
        name: sl.name.trim(),
        metric: sl.metric?.trim() || null,
        category: sl.category || 'other',
        description: sl.description?.trim() || null,
      })),
      trust_portal_url: document.getElementById('f-trust-portal-url')?.value.trim() || null,
      // Suppliers Module Review (puntos 2/3/4/5/6/13)
      business_importance_level: document.getElementById('f-biz-imp-level')?.value || null,
      security_risk_level: document.getElementById('f-sec-risk')?.value || null,
      operating_region: document.getElementById('f-op-region')?.value || null,
      security_status: document.getElementById('f-sec-status')?.value || null,
      review_frequency: document.getElementById('f-review-freq')?.value || null,
      agreement_status: document.getElementById('f-agreement')?.value || null,
      owner_id: document.getElementById('f-owner')?.value ? parseInt(document.getElementById('f-owner').value) : null,
      backup_owner_id: document.getElementById('f-backup-owner')?.value ? parseInt(document.getElementById('f-backup-owner').value) : null,
    };
    try {
      if (s) {
        await Api.suppliers.update(s.id, payload);
        UI.toast(t('suppliers.supplier_updated'), 'success');
      } else {
        await Api.suppliers.create(payload);
        UI.toast(t('suppliers.supplier_created'), 'success');
      }
      UI.closeModal();
      await _loadStats();
      await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  async function _openTprmSettings() {
    let cfg = {}; let templates = [];
    try {
      [cfg, templates] = await Promise.all([Api.tprm.getSettings(), Api.tprm.templates().catch(() => [])]);
    } catch (e) { UI.toast(e.message, 'error'); return; }
    const tplOptions = (sel) => `<option value="">- Ninguna -</option>` +
      templates.map(tp => `<option value="${tp.code}" ${sel === tp.code ? 'selected' : ''}>${UI.esc(tp.name)}</option>`).join('');
    const modKeys = [
      ['personal_data', 'Datos personales'], ['regulatory', 'Regulatorio'],
      ['offboarding', 'Offboarding'], ['ai_usage', 'Uso de IA'],
    ];
    const trig = cfg.trigger_modules || {};
    const recips = JSON.stringify(cfg.review_notify_recipients || {}, null, 2);
    UI.modal('Configuración del módulo de proveedores', `
      <div class="span2" style="display:grid;gap:14px;">
        <div>
          <label><b>Regiones operativas</b> <span style="font-size:11px;color:var(--text-muted);">(una por línea; editable e independiente de las sedes)</span></label>
          <textarea id="cfg-regions" class="input" rows="5">${UI.esc((cfg.operating_regions || []).join('\n'))}</textarea>
          ${(cfg.region_suggestions || []).length ? `<p style="font-size:11px;color:var(--text-muted);margin-top:4px;">Sugerencias desde sedes BCM: ${cfg.region_suggestions.map(r => UI.esc(r)).join(', ')}</p>` : ''}
        </div>
        <div>
          <label><b>Plantilla de cuestionario estándar</b> <span style="font-size:11px;color:var(--text-muted);">(punto 7 — se usa por defecto al crear cuestionarios)</span></label>
          <select id="cfg-default-tpl" class="input">${tplOptions(cfg.default_template_code)}</select>
        </div>
        <div>
          <label><b>Módulos add-on (se disparan según perfil del proveedor)</b></label>
          <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:4px;">
            ${modKeys.map(([k, lbl]) => `<div><label style="font-size:12px;">${lbl}</label><select class="input cfg-mod" data-key="${k}">${tplOptions(trig[k])}</select></div>`).join('')}
          </div>
        </div>
        <div style="border-top:1px solid var(--border);padding-top:10px;">
          <label style="display:flex;align-items:center;gap:8px;"><input type="checkbox" id="cfg-notify" ${cfg.review_notify_enabled ? 'checked' : ''}> <b>Notificar decisión de seguridad a destinatarios configurados (punto 11)</b></label>
          <p style="font-size:11px;color:var(--text-muted);margin:4px 0;">Destinatarios por región (JSON). Ej: <code>{"__default__":{"finance":["fin@x.com"],"legal":["legal@x.com"]},"Spain":{"finance":["fin.es@x.com"]}}</code></p>
          <textarea id="cfg-recipients" class="input" rows="5" style="font-family:monospace;font-size:12px;">${UI.esc(recips)}</textarea>
        </div>
        <div style="border-top:1px solid var(--border);padding-top:10px;">
          <label><b>Email estándar del cuestionario (punto 7)</b></label>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:4px;">
            <div><label style="font-size:12px;">Asunto (EN)</label><input id="cfg-subj-en" class="input" value="${UI.esc(cfg.standard_email_subject_en || '')}"></div>
            <div><label style="font-size:12px;">Asunto (ES)</label><input id="cfg-subj-es" class="input" value="${UI.esc(cfg.standard_email_subject_es || '')}"></div>
            <div><label style="font-size:12px;">Cuerpo (EN)</label><textarea id="cfg-body-en" class="input" rows="3">${UI.esc(cfg.standard_email_body_en || '')}</textarea></div>
            <div><label style="font-size:12px;">Cuerpo (ES)</label><textarea id="cfg-body-es" class="input" rows="3">${UI.esc(cfg.standard_email_body_es || '')}</textarea></div>
          </div>
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="cfg-cancel">Cancelar</button><button class="btn btn-primary" id="cfg-save">Guardar</button>`,
      width: 'min(96vw, 820px)',
    });
    document.getElementById('cfg-cancel').onclick = UI.closeModal;
    document.getElementById('cfg-save').onclick = async () => {
      const mods = {};
      document.querySelectorAll('.cfg-mod').forEach(sel => { if (sel.value) mods[sel.dataset.key] = sel.value; });
      let recipients = {};
      try { recipients = JSON.parse(document.getElementById('cfg-recipients').value || '{}'); }
      catch (e) { UI.toast('Destinatarios: JSON no válido', 'error'); return; }
      const payload = {
        operating_regions: document.getElementById('cfg-regions').value.split('\n').map(s => s.trim()).filter(Boolean),
        default_template_code: document.getElementById('cfg-default-tpl').value || null,
        trigger_modules: mods,
        review_notify_enabled: document.getElementById('cfg-notify').checked,
        review_notify_recipients: recipients,
        standard_email_subject_en: document.getElementById('cfg-subj-en').value.trim() || null,
        standard_email_subject_es: document.getElementById('cfg-subj-es').value.trim() || null,
        standard_email_body_en: document.getElementById('cfg-body-en').value.trim() || null,
        standard_email_body_es: document.getElementById('cfg-body-es').value.trim() || null,
      };
      try {
        await Api.tprm.updateSettings(payload);
        UI.toast('Configuración guardada', 'success');
        UI.closeModal();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  function _openImport() {
    UI.modal(t('suppliers.import_suppliers'), `
      <div class="span2">
        <p style="font-size:13px;margin-bottom:8px;">Sube un fichero exportado desde Excel u otra herramienta de gestión (OneTrust, ERP, hoja de compras...). Formatos: <strong>CSV, XLSX, XLS, ODS, TSV, JSON</strong>.</p>
        <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">${t('suppliers.import_autodetect')}</p>
        <input type="file" id="imp-file" accept=".csv,.xlsx,.xls,.ods,.tsv,.json" class="input">
        <div id="imp-result" style="margin-top:12px;"></div>
      </div>
    `, {
      actions: `<button class="btn" id="imp-cancel">Cerrar</button>
                <button class="btn btn-primary" id="imp-go">Importar</button>`,
    });
    document.getElementById('imp-cancel').onclick = UI.closeModal;
    document.getElementById('imp-go').onclick = async () => {
      const fileInput = document.getElementById('imp-file');
      const file = fileInput.files && fileInput.files[0];
      if (!file) { UI.toast('Selecciona un fichero', 'error'); return; }
      const resWrap = document.getElementById('imp-result');
      const btn = document.getElementById('imp-go');
      btn.disabled = true;
      resWrap.innerHTML = '<p class="text-muted">Importando...</p>';
      try {
        const r = await Api.suppliers.importFile(file);
        const cols = Object.entries(r.detected_columns || {}).map(([k, v]) => `${k} &larr; "${UI.esc(v)}"`).join(', ');
        resWrap.innerHTML = `
          <div class="notice" style="border-color:var(--risk-low);">
            ${t('suppliers.import_result_detail', {created: r.created, skipped: r.skipped, total: r.total})}
            ${cols ? `<div style="font-size:11px;color:var(--text-muted);margin-top:6px;">Columnas detectadas: ${cols}</div>` : ''}
            ${(r.errors && r.errors.length) ? `<div style="font-size:11px;color:var(--risk-high);margin-top:6px;">Errores: ${r.errors.map(UI.esc).join('; ')}</div>` : ''}
          </div>`;
        UI.toast(t('suppliers.suppliers_imported', {n: r.created}), 'success');
        await _loadStats();
        await _refresh();
      } catch (e) {
        resWrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
      } finally {
        btn.disabled = false;
      }
    };
  }

  // ======== QUESTIONNAIRES TAB ========

  async function _renderQuestionnairesTab() {
    const wrap = document.getElementById('sup-tab-content');
    wrap.innerHTML = `
      <div id="seq-my-tasks"></div>
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">
        <select id="seq-sup-filter" class="input" style="width:220px;">
          <option value="">${t('suppliers.all_suppliers_opt')}</option>
        </select>
        <select id="seq-type-filter" class="input" style="width:180px;">
          <option value="">Todos los tipos</option>
          <option value="external">Externos</option>
          <option value="internal">Internos</option>
        </select>
      </div>
      <div id="seq-list">Cargando...</div>
    `;
    // Mis tareas: cuestionarios asignados al usuario actual
    try {
      const tasks = await Api.supplier_questionnaires.myTasks();
      const tasksWrap = document.getElementById('seq-my-tasks');
      if (tasksWrap && tasks.length) {
        tasksWrap.innerHTML = `
          <div class="card" style="margin-bottom:14px;border-left:3px solid var(--brand-purple);">
            <div class="card-header">
              <div class="card-title"><i class="ti ti-clipboard-list"></i> Mis tareas asignadas (${tasks.length})</div>
            </div>
            <div class="table-wrap"><table class="data"><thead><tr>
              <th>Código</th><th>Título</th><th>Proveedor</th><th>Expira</th><th></th>
            </tr></thead><tbody>
              ${tasks.map(q => `<tr>
                <td>${UI.codePill(q.code)}</td>
                <td><strong>${UI.esc(q.title)}</strong></td>
                <td style="font-size:12px;">${UI.esc(q.supplier_name||'-')}</td>
                <td style="font-size:12px;">${q.expires_at ? new Date(q.expires_at).toLocaleDateString('es-ES') : '-'}</td>
                <td><button class="btn btn-sm btn-primary" data-task-id="${q.id}">Responder</button></td>
              </tr>`).join('')}
            </tbody></table></div>
          </div>`;
        tasksWrap.querySelectorAll('[data-task-id]').forEach(btn => {
          const q = tasks.find(x => x.id == btn.dataset.taskId);
          if (q) btn.onclick = () => _openInternalFillForm(q);
        });
      }
    } catch (_) {}

    // Populate supplier filter
    try {
      const sups = await Api.suppliers.list();
      const sel = document.getElementById('seq-sup-filter');
      if (sel) sups.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.code + ' - ' + s.name;
        sel.appendChild(opt);
      });
    } catch (_) {}
    document.getElementById('seq-sup-filter').onchange = _reloadSeq;
    document.getElementById('seq-type-filter').onchange = _reloadSeq;
    await _reloadSeq();
  }

  async function _reloadSeq() {
    const supId = document.getElementById('seq-sup-filter')?.value;
    const typeFilter = document.getElementById('seq-type-filter')?.value;
    const params = {};
    if (supId) params.supplier_id = supId;
    const wrap = document.getElementById('seq-list');
    if (!wrap) return;
    try {
      let data = await Api.supplier_questionnaires.list(params);
      if (typeFilter) data = data.filter(q => (q.assignment_type || 'external') === typeFilter);
      if (!data.length) {
        wrap.innerHTML = `<p style="color:var(--text-muted);margin-top:24px;text-align:center;">${t('suppliers.no_questionnaires')}</p>`;
        return;
      }
      const now = new Date();
      wrap.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          <th>Código</th><th>Título</th><th>Proveedor</th><th style="width:70px;">Tipo</th><th>Puntuación</th><th>Respondido</th><th>Expira</th><th>Evaluación IA</th><th></th>
        </tr></thead>
        <tbody>
          ${data.map(q => {
            const submitted = q.submitted_at ? new Date(q.submitted_at).toLocaleDateString('es-ES') : null;
            const expired = q.expires_at && new Date(q.expires_at) < now && !q.submitted_at;
            const expires = q.expires_at ? new Date(q.expires_at).toLocaleDateString('es-ES') : '-';
            const isInternal = q.assignment_type === 'internal';
            const typeHtml = isInternal
              ? `<span style="font-size:10px;font-weight:600;background:#EDE9FE;color:#7C3AED;padding:2px 6px;border-radius:4px;">Interno</span>`
              : `<span style="font-size:10px;font-weight:600;background:#E0F2FE;color:#0369A1;padding:2px 6px;border-radius:4px;">Externo</span>`;
            const assignedUserLabel = isInternal && q.assigned_user_name
              ? `<div style="font-size:10px;color:var(--text-muted);">Asignado: ${UI.esc(q.assigned_user_name)}</div>` : '';
            const regwatchBadge = q.regwatch_review_at
              ? `<span style="display:inline-block;margin-left:6px;font-size:9px;font-weight:700;background:#FEF3C7;color:#92400E;border:1px solid #FCD34D;padding:1px 5px;border-radius:4px;vertical-align:middle;" title="Revisión normativa requerida desde ${new Date(q.regwatch_review_at).toLocaleDateString('es-ES')}">NORM</span>`
              : '';
            let scoreHtml = '-';
            if (q.score !== null && q.score !== undefined) {
              const sc = q.score;
              const color = sc >= 80 ? '#22C55E' : sc >= 60 ? '#F59E0B' : '#EF4444';
              scoreHtml = `<span style="font-weight:700;color:${color};">${sc}/100</span>`;
            }
            let aiHtml = '-';
            if (q.submitted_at) {
              if (q.ai_review && !q.ai_review.error) {
                const aiscore = q.ai_review.ai_score;
                const aicolor = aiscore >= 80 ? '#22C55E' : aiscore >= 60 ? '#F59E0B' : '#EF4444';
                const reviewedDate = q.ai_reviewed_at ? new Date(q.ai_reviewed_at).toLocaleDateString('es-ES') : '';
                aiHtml = `<span style="font-weight:700;color:${aicolor};cursor:pointer;" data-id="${q.id}" data-act="view-ai" title="${t('suppliers.hint_view_ai_review', {date: reviewedDate})}">${aiscore}/100</span>`;
                if (Auth.canEdit()) {
                  aiHtml += ` <button class="btn btn-sm" style="font-size:10px;padding:1px 6px;" data-id="${q.id}" data-act="eval-ai" title="Re-evaluar con IA">Re-evaluar</button>`;
                }
              } else if (Auth.canEdit()) {
                aiHtml = `<button class="btn btn-sm" style="font-size:11px;" data-id="${q.id}" data-act="eval-ai">Evaluar IA</button>`;
              }
            }
            return `<tr style="${expired?'opacity:.6;':''}${q.regwatch_review_at?'border-left:3px solid #F59E0B;':''}">
              <td>${UI.codePill(q.code)}</td>
              <td><strong>${UI.esc(q.title)}</strong>${regwatchBadge}${assignedUserLabel}</td>
              <td style="font-size:12px;">${UI.esc(q.supplier_name||'-')}</td>
              <td>${typeHtml}</td>
              <td>${scoreHtml}</td>
              <td style="font-size:12px;">${submitted ? submitted : (expired ? '<span style="color:#EF4444;font-size:11px;">Expirado</span>' : '<span style="color:#F59E0B;font-size:11px;">Pendiente</span>')}</td>
              <td style="font-size:12px;">${expires}</td>
              <td style="font-size:12px;">${aiHtml}</td>
              <td>
                ${Auth.canEdit() && !q.submitted_at && !isInternal ? `<button class="btn btn-sm" data-id="${q.id}" data-act="send" title="${t('suppliers.hint_send_email_contact')}">Enviar</button>` : ''}
                ${Auth.canEdit() && !q.submitted_at && !isInternal ? `<button class="btn btn-sm" data-id="${q.id}" data-act="link" title="${t('suppliers.hint_copy_public_link')}">Enlace</button>` : ''}
                ${Auth.canEdit() && !q.submitted_at ? `<button class="btn btn-sm" data-id="${q.id}" data-act="assign" title="Asignar a usuario interno">Asignar</button>` : ''}
                ${isInternal && !q.submitted_at ? `<button class="btn btn-sm btn-primary" data-id="${q.id}" data-act="fill-internal" title="Responder internamente">Responder</button>` : ''}
                ${Auth.canEdit() && !q.submitted_at ? `<button class="btn btn-sm btn-danger" data-id="${q.id}" data-act="del">${t('common.delete')}</button>` : ''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
      wrap.querySelectorAll('[data-act="link"]').forEach(btn => {
        btn.onclick = () => {
          const q = data.find(x => x.id == btn.dataset.id);
          if (!q) return;
          const link = location.origin + '/supplier-q?token=' + encodeURIComponent(q.token);
          navigator.clipboard.writeText(link).then(() => UI.toast('Enlace copiado al portapapeles', 'success'))
            .catch(() => {
              UI.modal('Enlace publico del cuestionario', `
                <div class="span2">
                  <p style="font-size:13px;margin-bottom:8px;">Copia y comparte este enlace con el proveedor:</p>
                  <input style="width:100%;font-size:12px;font-family:monospace;" value="${UI.esc(link)}" readonly onclick="this.select()">
                </div>
              `, { actions: '<button class="btn btn-primary" id="m-cancel">Cerrar</button>' });
              document.getElementById('m-cancel').onclick = UI.closeModal;
            });
        };
      });
      wrap.querySelectorAll('[data-act="del"]').forEach(btn => {
        btn.onclick = async () => {
          if (!await UI.confirm(t('suppliers.confirm_delete_questionnaire'))) return;
          try { await Api.supplier_questionnaires.del(btn.dataset.id); UI.toast('Eliminado','success'); _reloadSeq(); }
          catch (e) { UI.toast(e.message,'error'); }
        };
      });
      wrap.querySelectorAll('[data-act="send"]').forEach(btn => {
        btn.onclick = async () => {
          btn.disabled = true;
          UI.toast(t('suppliers.sending_email'), 'info');
          try {
            const r = await Api.supplier_questionnaires.send(btn.dataset.id);
            UI.toast('Cuestionario enviado a ' + r.recipient, 'success');
          } catch (e) {
            UI.toast(e.message, 'error');
            btn.disabled = false;
          }
        };
      });
      // AI evaluation buttons
      wrap.querySelectorAll('[data-act="eval-ai"]').forEach(btn => {
        btn.onclick = async () => {
          const q = data.find(x => x.id == btn.dataset.id);
          if (!q) return;
          UI.toast('Evaluando con IA... Esto puede tardar unos segundos.', 'info');
          btn.disabled = true;
          try {
            const result = await Api.supplier_questionnaires_ai.triggerReview(q.id);
            UI.toast('Evaluación IA completada', 'success');
            _showAiReviewModal(q.title || q.code, result);
            await _reloadSeq();
          } catch (e) {
            UI.toast(e.message, 'error');
            btn.disabled = false;
          }
        };
      });
      // AI score click to view existing review
      wrap.querySelectorAll('[data-act="view-ai"]').forEach(el => {
        el.onclick = () => {
          const q = data.find(x => x.id == el.dataset.id);
          if (!q || !q.ai_review) return;
          _showAiReviewModal(q.title || q.code, q.ai_review);
        };
      });
      // Assign to internal user
      wrap.querySelectorAll('[data-act="assign"]').forEach(btn => {
        btn.onclick = async () => {
          const q = data.find(x => x.id == btn.dataset.id);
          if (!q) return;
          await _openAssignModal(q);
        };
      });
      // Fill internal
      wrap.querySelectorAll('[data-act="fill-internal"]').forEach(btn => {
        btn.onclick = () => {
          const q = data.find(x => x.id == btn.dataset.id);
          if (q) _openInternalFillForm(q);
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  async function _openAssignModal(q) {
    let users = [];
    try { users = await Api.users.list(); } catch (_) {}
    const opts = users.filter(u => u.is_active !== false).map(u =>
      `<option value="${u.id}">${UI.esc(u.full_name || u.email)} (${UI.esc(u.email)})</option>`
    ).join('');
    UI.modal(
      `Asignar cuestionario ${q.code} a usuario interno`,
      `<div style="padding:4px 0;">
        <p style="font-size:13px;margin-bottom:12px;color:var(--text-muted);">
          El usuario seleccionado podra responder el cuestionario directamente en la plataforma y recibira un email de notificación.
        </p>
        <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Usuario</label>
        <select id="assign-user-sel" class="input" style="width:100%;">
          <option value="">Selecciona un usuario...</option>
          ${opts}
        </select>
      </div>`,
      {
        width: '480px',
        actions: `<button class="btn btn-primary" id="assign-confirm">Asignar</button>
                  <button class="btn" id="assign-cancel">Cancelar</button>`,
      }
    );
    document.getElementById('assign-cancel').onclick = UI.closeModal;
    document.getElementById('assign-confirm').onclick = async () => {
      const userId = document.getElementById('assign-user-sel')?.value;
      if (!userId) { UI.toast('Selecciona un usuario', 'error'); return; }
      try {
        const r = await Api.supplier_questionnaires.assignInternal(q.id, parseInt(userId));
        UI.closeModal();
        UI.toast(`Cuestionario asignado a ${r.assigned_to}`, 'success');
        _reloadSeq();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  function _openInternalFillForm(q) {
    const questions = q.questions || [];
    const qRows = questions.map((question, i) => {
      const qid = question.id || `q${i + 1}`;
      const qtype = (question.type || '').toLowerCase();
      let inputHtml;
      if (qtype === 'select' || qtype === 'choice') {
        const opts = (question.options || ['Si', 'No']).map(o =>
          `<option value="${UI.esc(o)}">${UI.esc(o)}</option>`
        ).join('');
        inputHtml = `<select id="qans-${qid}" class="input" style="width:100%;"><option value="">Seleccionar...</option>${opts}</select>`;
      } else if (qtype === 'text' || qtype === 'textarea') {
        inputHtml = `<textarea id="qans-${qid}" class="input" rows="2" style="width:100%;"></textarea>`;
      } else {
        // Default: Si/No radio
        inputHtml = `<div style="display:flex;gap:16px;margin-top:4px;">
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
            <input type="radio" name="qans-${qid}" value="Si"> Si
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
            <input type="radio" name="qans-${qid}" value="No"> No
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
            <input type="radio" name="qans-${qid}" value="NA"> No aplica
          </label>
        </div>`;
      }
      return `<div style="padding:12px 0;border-bottom:1px solid var(--border);">
        <div style="font-size:13px;font-weight:600;margin-bottom:6px;">${i + 1}. ${UI.esc(question.text || question.name || '')}</div>
        ${inputHtml}
      </div>`;
    }).join('');

    UI.modal(
      `Responder: ${q.code} — ${q.title}`,
      `<div style="padding:4px 0;">
        <p style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">Proveedor: <strong>${UI.esc(q.supplier_name || '')}</strong></p>
        ${qRows || '<p class="text-muted">Sin preguntas configuradas.</p>'}
      </div>`,
      {
        width: '680px',
        actions: `<button class="btn btn-primary" id="ifill-submit">Enviar respuestas</button>
                  <button class="btn" id="ifill-cancel">Cancelar</button>`,
      }
    );
    document.getElementById('ifill-cancel').onclick = UI.closeModal;
    document.getElementById('ifill-submit').onclick = async () => {
      const answers = {};
      questions.forEach((question, i) => {
        const qid = question.id || `q${i + 1}`;
        const sel = document.getElementById('qans-' + qid);
        if (sel) {
          answers[qid] = sel.value;
        } else {
          const radio = document.querySelector(`input[name="qans-${qid}"]:checked`);
          if (radio) answers[qid] = radio.value;
        }
      });
      try {
        const r = await Api.supplier_questionnaires.internalSubmit(q.id, answers);
        UI.closeModal();
        UI.toast(`Cuestionario enviado. Puntuación: ${r.score}/100`, 'success');
        _reloadSeq();
        // Reload my tasks section
        const tasksWrap = document.getElementById('seq-my-tasks');
        if (tasksWrap) tasksWrap.innerHTML = '';
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  // ---- AI Review Modal ----

  const _AI_COVERAGE_LABELS = {
    fully_covered: 'Cobertura completa',
    partially_covered: 'Cobertura parcial',
    not_covered: 'Sin cobertura',
    unclear: 'No determinado',
  };
  const _AI_EVIDENCE_LABELS = {
    consistent: 'Consistente',
    partially_consistent: 'Parcialmente consistente',
    inconsistent: 'Inconsistente',
    no_evidence: 'Sin evidencia',
  };
  const _AI_COVERAGE_COLORS = {
    fully_covered: '#22C55E',
    partially_covered: '#F59E0B',
    not_covered: '#EF4444',
    unclear: '#6B7280',
  };
  const _AI_EVIDENCE_COLORS = {
    consistent: '#22C55E',
    partially_consistent: '#F59E0B',
    inconsistent: '#EF4444',
    no_evidence: '#6B7280',
  };

  function _showAiReviewModal(title, review) {
    if (!review) return;
    if (review.error) {
      UI.modal(t('suppliers.modal_ai_review_error'), `
        <div class="span2">
          <div class="notice">${UI.esc(review.error)}</div>
          <p style="font-size:13px;margin-top:8px;">La evaluación automática no pudo completarse. Revisa la configuración de la API key en IA &gt; Configuración.</p>
        </div>
      `, { actions: '<button class="btn btn-primary" id="m-close-ai">Cerrar</button>' });
      document.getElementById('m-close-ai').onclick = UI.closeModal;
      return;
    }

    const score = review.ai_score !== null && review.ai_score !== undefined ? review.ai_score : '-';
    const scoreColor = typeof score === 'number' ? (score >= 80 ? '#22C55E' : score >= 60 ? '#F59E0B' : '#EF4444') : '#6B7280';
    const confPct = review.confidence !== null && review.confidence !== undefined
      ? Math.round(review.confidence * 100) + '%' : '-';
    const coverage = review.control_coverage_assessment || 'unclear';
    const evidence = review.evidence_consistency || 'no_evidence';
    const needsManual = review.needs_manual_review;
    const rationale = review.rationale || '';
    const reviewedAt = review.evaluated_at ? new Date(review.evaluated_at).toLocaleString('es-ES') : '';

    const redFlags = Array.isArray(review.red_flags) && review.red_flags.length
      ? review.red_flags.map(f => `<li style="margin-bottom:4px;">${UI.esc(f)}</li>`).join('')
      : '<li style="color:var(--text-muted);">Sin alertas detectadas</li>';

    const followUp = Array.isArray(review.follow_up_questions) && review.follow_up_questions.length
      ? review.follow_up_questions.map(f => `<li style="margin-bottom:4px;">${UI.esc(f)}</li>`).join('')
      : '<li style="color:var(--text-muted);">Sin preguntas adicionales</li>';

    UI.modal(t('suppliers.modal_ai_review', {title: UI.esc(title)}), `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div style="grid-column:1/-1;display:flex;gap:16px;flex-wrap:wrap;align-items:center;border-bottom:1px solid var(--border);padding-bottom:10px;margin-bottom:4px;">
          <div style="text-align:center;">
            <div style="font-size:28px;font-weight:800;color:${scoreColor};">${score}<span style="font-size:14px;">/100</span></div>
            <div style="font-size:11px;color:var(--text-muted);">Puntuación IA</div>
          </div>
          <div style="text-align:center;">
            <div style="font-size:20px;font-weight:700;color:var(--brand-purple);">${confPct}</div>
            <div style="font-size:11px;color:var(--text-muted);">Confianza</div>
          </div>
          ${needsManual ? '<div style="background:#FEF3C7;border:1px solid #F59E0B;border-radius:6px;padding:4px 10px;font-size:12px;font-weight:600;color:#92400E;">Requiere revisión manual</div>' : '<div style="background:#ECFDF5;border:1px solid #22C55E;border-radius:6px;padding:4px 10px;font-size:12px;font-weight:600;color:#065F46;">Sin alerta de revisión</div>'}
          ${reviewedAt ? `<div style="font-size:11px;color:var(--text-muted);margin-left:auto;">Evaluado: ${reviewedAt}</div>` : ''}
        </div>

        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Cobertura de controles</div>
          <span style="display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;background:${_AI_COVERAGE_COLORS[coverage]};color:#fff;">${_AI_COVERAGE_LABELS[coverage] || coverage}</span>
        </div>
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Consistencia de evidencias</div>
          <span style="display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;background:${_AI_EVIDENCE_COLORS[evidence]};color:#fff;">${_AI_EVIDENCE_LABELS[evidence] || evidence}</span>
        </div>

        <div style="grid-column:1/-1;">
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Razonamiento</div>
          <p style="font-size:13px;line-height:1.5;margin:0;background:var(--bg-alt,var(--bg));padding:8px 10px;border-radius:6px;border:1px solid var(--border);">${UI.esc(rationale)}</p>
        </div>

        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Alertas detectadas</div>
          <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.6;">${redFlags}</ul>
        </div>
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Preguntas de seguimiento sugeridas</div>
          <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.6;">${followUp}</ul>
        </div>
      </div>
    `, { actions: '<button class="btn btn-primary" id="m-close-ai">Cerrar</button>' });
    document.getElementById('m-close-ai').onclick = UI.closeModal;
  }

  async function _openSeqForm() {
    let suppliers = [];
    let templates = [];
    let customTpls = [];
    try { suppliers = await Api.suppliers.list(); } catch (_) {}
    try { templates = await Api.tprm.templates(); } catch (_) {}
    try { customTpls = await Api.tprm.customTemplates(); } catch (_) {}
    UI.modal(t('suppliers.new_security_questionnaire'), `
      <div><label>Proveedor *</label>
        <select id="sq-sup">
          <option value="">- Seleccionar -</option>
          ${suppliers.map(s => `<option value="${s.id}">${UI.esc(s.code)} - ${UI.esc(s.name)}</option>`).join('')}
        </select>
      </div>
      <div><label>Plantilla TPRM</label>
        <select id="sq-template">
          <option value="">Estandar NIS2/ISO 27001 (10 preguntas)</option>
          <optgroup label="Plantillas del sistema">
          ${templates.map(t => `<option value="sys:${UI.esc(t.code)}">${UI.esc(t.name)} (${t.question_count} preguntas)</option>`).join('')}
          </optgroup>
          ${customTpls.length ? `<optgroup label="Mis plantillas">
          ${customTpls.map(t => `<option value="custom:${t.id}">${UI.esc(t.name)} (${(t.questions||[]).length} preguntas)</option>`).join('')}
          </optgroup>` : ''}
        </select>
      </div>
      <div><label>Título *</label>
        <input id="sq-title" value="Evaluacion de seguridad NIS2/ISO 27001">
      </div>
      <div><label>Fecha de expiración</label>
        <input type="date" id="sq-expires" value="${new Date(Date.now()+30*86400000).toISOString().slice(0,10)}">
      </div>
      <div><label>Email de notificación (cuando el proveedor responde)</label>
        <input id="sq-notify-email" type="email" class="input" placeholder="gestor@empresa.com (opcional)">
      </div>
      <div class="span2"><label>Notas internas</label>
        <textarea id="sq-notes" rows="2" placeholder="Notas para el equipo interno (no visibles para el proveedor)"></textarea>
      </div>
      <div class="span2" style="display:flex;flex-direction:column;gap:6px;background:var(--bg-2);border:1px solid var(--border);border-radius:6px;padding:8px 10px;">
        <label style="display:flex;align-items:center;gap:8px;margin:0;cursor:pointer;font-size:13px;">
          <input type="checkbox" id="sq-prefill"> Reutilizar respuestas del último cuestionario respondido (el proveedor solo confirma o reporta cambios)
        </label>
        <label style="display:flex;align-items:center;gap:8px;margin:0;cursor:pointer;font-size:13px;">
          <input type="checkbox" id="sq-modules" checked> Adjuntar módulos add-on automáticamente según el perfil del proveedor (datos personales, regulatorio, offboarding…)
        </label>
      </div>
      <div class="span2 notice">
        Elige una plantilla del sistema (ISO 27001, NIS2, DORA, GDPR, ISO 42001, offboarding...) o el set estandar. Tras crear el cuestionario, copia el enlace publico para enviarlo al proveedor.
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Crear y obtener enlace</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const supId = document.getElementById('sq-sup').value;
      const title = document.getElementById('sq-title').value.trim();
      if (!supId) { UI.toast(t('suppliers.select_supplier'),'error'); return; }
      if (!title) { UI.toast('El título es obligatorio','error'); return; }
      const expires = document.getElementById('sq-expires').value;
      const tplVal = document.getElementById('sq-template').value || '';
      const notifyEmail = document.getElementById('sq-notify-email')?.value.trim() || null;
      const body = {
        supplier_id: parseInt(supId),
        title,
        expires_at: expires || null,
        notes: document.getElementById('sq-notes').value.trim(),
        template_code: tplVal.startsWith('sys:') ? tplVal.slice(4) : null,
        custom_template_id: tplVal.startsWith('custom:') ? parseInt(tplVal.slice(7)) : null,
        notify_email: notifyEmail || null,
        prefill_from_previous: document.getElementById('sq-prefill')?.checked || false,
        apply_trigger_modules: document.getElementById('sq-modules')?.checked !== false,
      };
      try {
        const q = await Api.supplier_questionnaires.create(body);
        UI.closeModal();
        const link = location.origin + '/supplier-q?token=' + encodeURIComponent(q.token);
        navigator.clipboard.writeText(link).catch(() => {});
        UI.modal('Cuestionario creado', `
          <div class="span2">
            <p style="font-size:13px;margin-bottom:4px;">Cuestionario <strong>${UI.esc(q.code)}</strong> creado correctamente.</p>
            <p style="font-size:13px;margin-bottom:8px;">Enlace publico copiado al portapapeles. Comparte este enlace con el proveedor:</p>
            <input style="width:100%;font-size:12px;font-family:monospace;" value="${UI.esc(link)}" readonly onclick="this.select()">
            <p style="font-size:12px;color:var(--text-muted);margin-top:8px;">El enlace expira el ${new Date(q.expires_at).toLocaleDateString('es-ES')}.</p>
          </div>
        `, { actions: '<button class="btn btn-primary" id="m-ok">Entendido</button>' });
        document.getElementById('m-ok').onclick = UI.closeModal;
        _reloadSeq();
      } catch (e) { UI.toast(e.message,'error'); }
    };
  }

  // ======== SCHEDULES TAB ========

  async function _renderSchedulesTab() {
    const wrap = document.getElementById('sup-tab-content');
    wrap.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">
        <select id="sched-sup-filter" class="input" style="width:220px;">
          <option value="">${t('suppliers.all_suppliers_opt')}</option>
        </select>
      </div>
      <div id="sched-list">Cargando...</div>
    `;
    try {
      const sups = await Api.suppliers.list();
      const sel = document.getElementById('sched-sup-filter');
      if (sel) sups.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id; opt.textContent = s.code + ' - ' + s.name; sel.appendChild(opt);
      });
    } catch (_) {}
    document.getElementById('sched-sup-filter').onchange = _reloadSchedules;
    await _reloadSchedules();
  }

  async function _reloadSchedules() {
    const supId = document.getElementById('sched-sup-filter')?.value;
    const params = {};
    if (supId) params.supplier_id = supId;
    const wrap = document.getElementById('sched-list');
    if (!wrap) return;
    try {
      const data = await Api.questionnaire_schedules.list(params);
      if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);margin-top:24px;text-align:center;">Sin planificaciones. Crea una para enviar cuestionarios periodicamente.</p>';
        return;
      }
      const INTERVAL_LABELS = { 30:'Mensual', 90:'Trimestral', 180:'Semestral', 365:'Anual' };
      wrap.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          <th>Proveedor</th><th>Título (plantilla)</th><th>Frecuencia</th>
          <th>Próximo envío</th><th>Último envío</th><th>Notificar a</th><th>Estado</th><th></th>
        </tr></thead>
        <tbody>
          ${data.map(sc => {
            const next = sc.next_send_at ? new Date(sc.next_send_at).toLocaleDateString('es-ES') : '-';
            const last = sc.last_sent_at ? new Date(sc.last_sent_at).toLocaleDateString('es-ES') : 'Nunca';
            const freq = INTERVAL_LABELS[sc.interval_days] || t('suppliers.n_days', {n: sc.interval_days});
            const status = sc.enabled
              ? `<span style="color:#22C55E;font-weight:600;font-size:12px;">Activa</span>`
              : `<span style="color:var(--text-muted);font-size:12px;">Pausada</span>`;
            return `<tr>
              <td style="font-size:12px;">${UI.esc(sc.supplier_code || '')} ${UI.esc(sc.supplier_name || '')}</td>
              <td>${UI.esc(sc.title_template)}</td>
              <td style="font-size:12px;">${freq}</td>
              <td style="font-size:12px;">${next}</td>
              <td style="font-size:12px;">${last}</td>
              <td style="font-size:12px;">${UI.esc(sc.notify_email || '-')}</td>
              <td>${status}</td>
              <td>
                ${Auth.canEdit() ? `
                  <button class="btn btn-sm" data-id="${sc.id}" data-sc-act="edit">Editar</button>
                  <button class="btn btn-sm" data-id="${sc.id}" data-sc-act="toggle">${sc.enabled ? 'Pausar' : 'Activar'}</button>
                  <button class="btn btn-sm btn-danger" data-id="${sc.id}" data-sc-act="del">${t('common.delete')}</button>
                ` : ''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;

      wrap.querySelectorAll('[data-sc-act="edit"]').forEach(btn => {
        btn.onclick = () => {
          const sc = data.find(x => x.id == btn.dataset.id);
          if (sc) _openScheduleForm(sc);
        };
      });
      wrap.querySelectorAll('[data-sc-act="toggle"]').forEach(btn => {
        btn.onclick = async () => {
          const sc = data.find(x => x.id == btn.dataset.id);
          if (!sc) return;
          try {
            await Api.questionnaire_schedules.update(sc.id, { enabled: !sc.enabled });
            UI.toast(sc.enabled ? t('suppliers.schedule_paused') : t('suppliers.schedule_enabled'), 'success');
            _reloadSchedules();
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      });
      wrap.querySelectorAll('[data-sc-act="del"]').forEach(btn => {
        btn.onclick = async () => {
          if (!confirm(t('suppliers.confirm_delete_schedule'))) return;
          try {
            await Api.questionnaire_schedules.del(btn.dataset.id);
            UI.toast('Planificación eliminada', 'success');
            _reloadSchedules();
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  async function _openScheduleForm(sc) {
    let suppliers = [], templates = [], customTpls = [];
    try { suppliers = await Api.suppliers.list(); } catch (_) {}
    try { templates = await Api.tprm.templates(); } catch (_) {}
    try { customTpls = await Api.tprm.customTemplates(); } catch (_) {}
    const v = sc || {};
    const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 16);
    UI.modal(sc ? t('suppliers.edit_schedule') : t('suppliers.new_periodic_schedule'), `
      <div><label>Proveedor *</label>
        <select id="sc-sup">
          <option value="">- Seleccionar -</option>
          ${suppliers.map(s => `<option value="${s.id}" ${v.supplier_id == s.id ? 'selected' : ''}>${UI.esc(s.code)} - ${UI.esc(s.name)}</option>`).join('')}
        </select>
      </div>
      <div><label>Título del cuestionario *</label>
        <input id="sc-title" class="input" value="${UI.esc(v.title_template || 'Evaluación de seguridad {year}')}" placeholder="Usa {year} y {month} como variables">
      </div>
      <div><label>Plantilla</label>
        <select id="sc-template" class="input">
          <option value="">Estandar NIS2/ISO 27001</option>
          <optgroup label="Plantillas del sistema">
            ${templates.map(t => `<option value="sys:${UI.esc(t.code)}" ${v.template_code === t.code ? 'selected' : ''}>${UI.esc(t.name)}</option>`).join('')}
          </optgroup>
          ${customTpls.length ? `<optgroup label="Mis plantillas">
            ${customTpls.map(t => `<option value="custom:${t.id}" ${v.custom_template_id == t.id ? 'selected' : ''}>${UI.esc(t.name)}</option>`).join('')}
          </optgroup>` : ''}
        </select>
      </div>
      <div><label>Frecuencia de envío</label>
        <select id="sc-interval" class="input">
          <option value="30" ${v.interval_days==30?'selected':''}>Mensual (30 días)</option>
          <option value="90" ${v.interval_days==90?'selected':''}>Trimestral (90 días)</option>
          <option value="180" ${v.interval_days==180?'selected':''}>Semestral (180 días)</option>
          <option value="365" ${(!v.interval_days||v.interval_days==365)?'selected':''}>Anual (365 días)</option>
        </select>
      </div>
      <div><label>Días de validez del cuestionario enviado</label>
        <input type="number" id="sc-expires" class="input" min="7" max="180" value="${v.expires_days || 30}">
      </div>
      <div><label>Primer/próximo envío</label>
        <input type="datetime-local" id="sc-next" class="input" value="${v.next_send_at ? v.next_send_at.slice(0,16) : tomorrow}">
      </div>
      <div><label>Email de notificación (al responder el proveedor)</label>
        <input type="email" id="sc-notify" class="input" value="${UI.esc(v.notify_email || '')}" placeholder="responsable@empresa.com">
      </div>
      <div class="span2"><label>Notas internas</label>
        <textarea id="sc-notes" class="input" rows="2">${UI.esc(v.notes || '')}</textarea>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const supId = document.getElementById('sc-sup').value;
      const title = document.getElementById('sc-title').value.trim();
      if (!supId) { UI.toast(t('suppliers.select_supplier'), 'error'); return; }
      if (!title) { UI.toast('El título es obligatorio', 'error'); return; }
      const tplVal = document.getElementById('sc-template').value || '';
      const payload = {
        supplier_id: parseInt(supId),
        title_template: title,
        template_code: tplVal.startsWith('sys:') ? tplVal.slice(4) : null,
        custom_template_id: tplVal.startsWith('custom:') ? parseInt(tplVal.slice(7)) : null,
        interval_days: parseInt(document.getElementById('sc-interval').value) || 365,
        expires_days: parseInt(document.getElementById('sc-expires').value) || 30,
        notify_email: document.getElementById('sc-notify').value.trim() || null,
        notes: document.getElementById('sc-notes').value.trim() || null,
        next_send_at: document.getElementById('sc-next').value || null,
      };
      try {
        if (sc) {
          await Api.questionnaire_schedules.update(sc.id, payload);
          UI.toast('Planificación actualizada', 'success');
        } else {
          await Api.questionnaire_schedules.create(payload);
          UI.toast('Planificación creada', 'success');
        }
        UI.closeModal();
        _reloadSchedules();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  // ======== FLOWS TAB ========

  async function _renderFlowsTab() {
    const wrap = document.getElementById('sup-tab-content');
    wrap.innerHTML = `
      <div class="notice" style="margin-bottom:12px;font-size:13px;">
        Los flujos permiten encadenar cuestionarios automáticamente según el resultado de la fase anterior.
        Ejemplo: cuestionario inicial &rarr; si score &lt; 60% enviar cuestionario de riesgo alto, si &ge; 60% enviar uno de riesgo medio.
      </div>
      <div id="flow-list">Cargando...</div>
    `;
    await _reloadFlows();
  }

  async function _reloadFlows() {
    const wrap = document.getElementById('flow-list');
    if (!wrap) return;
    try {
      const data = await Api.questionnaire_flows.list();
      if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);margin-top:24px;text-align:center;">Sin flujos definidos. Crea uno para automatizar secuencias de cuestionarios.</p>';
        return;
      }
      wrap.innerHTML = data.map(f => {
        const stepCount = (f.steps || []).length;
        const initial = (f.steps || []).filter(s => !s.condition).length;
        const conditional = stepCount - initial;
        return `
          <div style="border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:10px;background:var(--bg-2);">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
              <div style="flex:1;">
                <div style="font-weight:700;font-size:14px;">${UI.esc(f.name)}</div>
                ${f.description ? `<div style="font-size:12px;color:var(--text-muted);margin-top:2px;">${UI.esc(f.description)}</div>` : ''}
                <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;">
                  <span style="font-size:11px;background:var(--bg);padding:2px 8px;border-radius:999px;border:1px solid var(--border);">${initial} paso${initial!==1?'s':''} inicial${initial!==1?'es':''}</span>
                  ${conditional ? `<span style="font-size:11px;background:var(--bg);padding:2px 8px;border-radius:999px;border:1px solid var(--border);">${conditional} paso${conditional!==1?'s':''} condicional${conditional!==1?'es':''}</span>` : ''}
                </div>
                <div style="margin-top:8px;">
                  ${(f.steps || []).map((s, i) => {
                    const cond = s.condition
                      ? (s.condition.score_lt !== undefined ? `score &lt; ${s.condition.score_lt}%`
                        : s.condition.score_gte !== undefined ? `score &ge; ${s.condition.score_gte}%`
                        : s.condition.residual_level ? `nivel residual = ${s.condition.residual_level}`
                        : 'condicional')
                      : 'inicial (siempre)';
                    return `<div style="font-size:11px;color:var(--text-muted);margin-top:3px;">
                      <span style="display:inline-block;width:18px;height:18px;border-radius:50%;background:var(--brand-purple);color:#fff;font-size:10px;font-weight:700;text-align:center;line-height:18px;margin-right:4px;">${i+1}</span>
                      <strong>${UI.esc(s.name || s.template_code || 'Paso')}</strong> &mdash; ${cond}
                    </div>`;
                  }).join('')}
                </div>
              </div>
              <div style="display:flex;flex-direction:column;gap:4px;min-width:110px;">
                ${Auth.canEdit() ? `
                  <button class="btn btn-sm" data-id="${f.id}" data-fl-act="edit">Editar flujo</button>
                  <button class="btn btn-sm btn-primary" data-id="${f.id}" data-fl-act="apply">Aplicar a proveedor</button>
                  <button class="btn btn-sm btn-danger" data-id="${f.id}" data-fl-act="del">${t('common.delete')}</button>
                ` : ''}
              </div>
            </div>
          </div>
        `;
      }).join('');

      wrap.querySelectorAll('[data-fl-act="edit"]').forEach(btn => {
        btn.onclick = () => {
          const f = data.find(x => x.id == btn.dataset.id);
          if (f) _openFlowForm(f);
        };
      });
      wrap.querySelectorAll('[data-fl-act="apply"]').forEach(btn => {
        btn.onclick = () => {
          const f = data.find(x => x.id == btn.dataset.id);
          if (f) _openApplyFlowModal(f);
        };
      });
      wrap.querySelectorAll('[data-fl-act="del"]').forEach(btn => {
        btn.onclick = async () => {
          if (!confirm(t('suppliers.confirm_delete_flow'))) return;
          try {
            await Api.questionnaire_flows.del(btn.dataset.id);
            UI.toast('Flujo eliminado', 'success');
            _reloadFlows();
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  async function _openFlowForm(flow) {
    let templates = [], customTpls = [];
    try { templates = await Api.tprm.templates(); } catch (_) {}
    try { customTpls = await Api.tprm.customTemplates(); } catch (_) {}

    const tplOptions = `
      <option value="">Estandar NIS2/ISO 27001</option>
      <optgroup label="Plantillas del sistema">
        ${templates.map(t => `<option value="sys:${UI.esc(t.code)}">${UI.esc(t.name)}</option>`).join('')}
      </optgroup>
      ${customTpls.length ? `<optgroup label="Mis plantillas">
        ${customTpls.map(t => `<option value="custom:${t.id}">${UI.esc(t.name)}</option>`).join('')}
      </optgroup>` : ''}
    `;

    let _flowSteps = flow ? JSON.parse(JSON.stringify(flow.steps || [])) : [];
    if (!_flowSteps.length) {
      _flowSteps = [{ id: 'step_1', name: 'Cuestionario inicial', template_code: null, expires_days: 30, condition: null }];
    }

    function _renderFlowSteps() {
      const stepsWrap = document.getElementById('flow-steps-wrap');
      if (!stepsWrap) return;
      stepsWrap.innerHTML = _flowSteps.map((s, i) => {
        const condType = !s.condition ? 'none'
          : s.condition.score_lt !== undefined ? 'score_lt'
          : s.condition.score_gte !== undefined ? 'score_gte'
          : s.condition.residual_level !== undefined ? 'residual_level'
          : 'none';
        const condVal = s.condition
          ? (s.condition.score_lt ?? s.condition.score_gte ?? s.condition.residual_level ?? '')
          : '';
        const curTpl = s.template_code
          ? (s.template_code.startsWith('custom:') ? `custom:${s.custom_template_id}` : `sys:${s.template_code}`)
          : '';
        return `
          <div style="border:1px solid var(--border);border-radius:6px;padding:10px;margin-bottom:8px;background:var(--bg-2);">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">
              <span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;background:var(--brand-purple);color:#fff;font-size:11px;font-weight:700;">${i+1}</span>
              <input class="input fl-step-name" data-idx="${i}" placeholder="${t('suppliers.ph_step_name')}" value="${UI.esc(s.name||'')}" style="flex:1;font-size:12px;">
              ${_flowSteps.length > 1 ? `<button type="button" class="btn btn-sm btn-danger fl-step-del" data-idx="${i}" style="padding:2px 8px;font-size:11px;">X</button>` : ''}
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
              <div>
                <label style="font-size:11px;color:var(--text-muted);">Plantilla</label>
                <select class="input fl-step-tpl" data-idx="${i}" style="font-size:12px;">
                  ${tplOptions}
                </select>
              </div>
              <div>
                <label style="font-size:11px;color:var(--text-muted);">Días de validez</label>
                <input type="number" class="input fl-step-expires" data-idx="${i}" min="7" max="180" value="${s.expires_days||30}" style="font-size:12px;">
              </div>
              <div>
                <label style="font-size:11px;color:var(--text-muted);">Condicion de envío</label>
                <select class="input fl-step-cond-type" data-idx="${i}" style="font-size:12px;">
                  <option value="none" ${condType==='none'?'selected':''}>Siempre (paso inicial)</option>
                  <option value="score_lt" ${condType==='score_lt'?'selected':''}>Score anterior &lt; X%</option>
                  <option value="score_gte" ${condType==='score_gte'?'selected':''}>Score anterior &ge; X%</option>
                  <option value="residual_level" ${condType==='residual_level'?'selected':''}>Nivel residual igual a...</option>
                </select>
              </div>
              <div>
                <label style="font-size:11px;color:var(--text-muted);">Valor condicion</label>
                <input class="input fl-step-cond-val" data-idx="${i}" placeholder="Ej: 60 o critical" value="${UI.esc(String(condVal))}" style="font-size:12px;" ${condType==='none'?'disabled':''}>
              </div>
            </div>
          </div>
        `;
      }).join('') + `<button type="button" id="fl-add-step" class="btn btn-sm" style="margin-top:4px;">+ Añadir paso</button>`;

      // Set selected template values
      stepsWrap.querySelectorAll('.fl-step-tpl').forEach(sel => {
        const idx = parseInt(sel.dataset.idx);
        const s = _flowSteps[idx];
        const curTpl = s.template_code
          ? (s.template_code.startsWith('custom:') ? `custom:${s.custom_template_id}` : `sys:${s.template_code}`)
          : '';
        sel.value = curTpl;
      });

      // Wire events
      stepsWrap.querySelectorAll('.fl-step-name').forEach(inp => {
        inp.oninput = () => { _flowSteps[parseInt(inp.dataset.idx)].name = inp.value; };
      });
      stepsWrap.querySelectorAll('.fl-step-tpl').forEach(sel => {
        sel.onchange = () => {
          const idx = parseInt(sel.dataset.idx); const v = sel.value;
          if (!v) { _flowSteps[idx].template_code = null; _flowSteps[idx].custom_template_id = null; }
          else if (v.startsWith('sys:')) { _flowSteps[idx].template_code = v.slice(4); _flowSteps[idx].custom_template_id = null; }
          else if (v.startsWith('custom:')) { _flowSteps[idx].template_code = null; _flowSteps[idx].custom_template_id = parseInt(v.slice(7)); }
        };
      });
      stepsWrap.querySelectorAll('.fl-step-expires').forEach(inp => {
        inp.oninput = () => { _flowSteps[parseInt(inp.dataset.idx)].expires_days = parseInt(inp.value) || 30; };
      });
      stepsWrap.querySelectorAll('.fl-step-cond-type').forEach(sel => {
        sel.onchange = () => {
          const idx = parseInt(sel.dataset.idx); const v = sel.value;
          const valInp = stepsWrap.querySelector(`.fl-step-cond-val[data-idx="${idx}"]`);
          if (v === 'none') { _flowSteps[idx].condition = null; if(valInp) valInp.disabled = true; }
          else { if(valInp) valInp.disabled = false; }
        };
      });
      stepsWrap.querySelectorAll('.fl-step-cond-val').forEach(inp => {
        inp.oninput = () => {
          const idx = parseInt(inp.dataset.idx);
          const typeEl = stepsWrap.querySelector(`.fl-step-cond-type[data-idx="${idx}"]`);
          const condType = typeEl?.value || 'none';
          if (condType === 'none') { _flowSteps[idx].condition = null; return; }
          const val = condType === 'residual_level' ? inp.value : (parseInt(inp.value) || 60);
          _flowSteps[idx].condition = { [condType]: val };
        };
      });
      stepsWrap.querySelectorAll('.fl-step-del').forEach(btn => {
        btn.onclick = () => {
          _flowSteps.splice(parseInt(btn.dataset.idx), 1);
          _renderFlowSteps();
        };
      });
      const addBtn = document.getElementById('fl-add-step');
      if (addBtn) {
        addBtn.onclick = () => {
          _flowSteps.push({ id: 'step_' + Date.now(), name: '', template_code: null, expires_days: 30, condition: null });
          _renderFlowSteps();
        };
      }
    }

    UI.modal(flow ? t('suppliers.edit_flow', {name: UI.esc(flow.name)}) : t('suppliers.new_questionnaire_flow'), `
      <div class="span2"><label>Nombre del flujo *</label>
        <input id="fl-name" class="input" value="${UI.esc(flow?.name || '')}" placeholder="${t('suppliers.flow_name_placeholder')}">
      </div>
      <div class="span2"><label>Descripción</label>
        <textarea id="fl-desc" class="input" rows="2">${UI.esc(flow?.description || '')}</textarea>
      </div>
      <div class="span2">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <strong style="font-size:13px;color:var(--brand-purple);">Pasos del flujo</strong>
        </div>
        <div id="flow-steps-wrap"></div>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar flujo</button>`,
      width: '680px',
    });

    document.getElementById('m-cancel').onclick = UI.closeModal;
    _renderFlowSteps();

    document.getElementById('m-save').onclick = async () => {
      const name = document.getElementById('fl-name').value.trim();
      if (!name) { UI.toast('El nombre es obligatorio', 'error'); return; }
      if (!_flowSteps.length) { UI.toast('El flujo necesita al menos un paso', 'error'); return; }
      const payload = {
        name,
        description: document.getElementById('fl-desc').value.trim() || null,
        steps: _flowSteps,
      };
      try {
        if (flow) {
          await Api.questionnaire_flows.update(flow.id, payload);
          UI.toast('Flujo actualizado', 'success');
        } else {
          await Api.questionnaire_flows.create(payload);
          UI.toast('Flujo creado', 'success');
        }
        UI.closeModal();
        _reloadFlows();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  async function _openApplyFlowModal(flow) {
    let suppliers = [];
    try { suppliers = await Api.suppliers.list(); } catch (_) {}
    UI.modal(t('suppliers.modal_apply_flow', {name: UI.esc(flow.name)}), `
      <div>
        <label>Selecciona el proveedor al que iniciar el flujo</label>
        <select id="apply-sup" class="input">
          <option value="">- Seleccionar proveedor -</option>
          ${suppliers.map(s => `<option value="${s.id}">${UI.esc(s.code)} - ${UI.esc(s.name)}</option>`).join('')}
        </select>
      </div>
      <div class="span2 notice" style="font-size:12px;">
        Se creara el primer cuestionario del flujo y se enlazara con este proveedor. Los pasos siguientes se envían al recibir respuesta del anterior.
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-apply">Iniciar flujo</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-apply').onclick = async () => {
      const supId = document.getElementById('apply-sup').value;
      if (!supId) { UI.toast(t('suppliers.select_supplier'), 'error'); return; }
      try {
        const r = await Api.questionnaire_flows.apply(flow.id, supId);
        UI.closeModal();
        const link = location.origin + '/supplier-q?token=' + encodeURIComponent(r.token);
        UI.modal('Flujo iniciado', `
          <div class="span2">
            <p style="font-size:13px;margin-bottom:4px;">Cuestionario <strong>${UI.esc(r.questionnaire_code)}</strong> creado: <em>${UI.esc(r.title)}</em>.</p>
            <p style="font-size:13px;margin-bottom:8px;">Enlace publico para enviar al proveedor:</p>
            <input style="width:100%;font-size:12px;font-family:monospace;" value="${UI.esc(link)}" readonly onclick="this.select()">
          </div>
        `, { actions: '<button class="btn btn-primary" id="m-ok">Entendido</button>' });
        document.getElementById('m-ok').onclick = UI.closeModal;
        navigator.clipboard.writeText(link).catch(() => {});
        _setSupTab('questionnaires');
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  return {
    render,
    openDashEditor: _openSupDashEditor,
    _changeStage,
    _toggleChecklistItem,
    _recordSignOff,
    _saveConcentrationMitigation,
    // Gate de onboarding
    _openSignOffDialog,
    _undoSignOff,
    _openBypassDialog,
    _openForceControlsDialog,
    _clearOverride,
    _openDecisionDialog,
    _addDecisionCondition,
    _renderGateBlock,
    _openGateConfig,
    _gateChainItemRow,
    // Expediente de proveedor
    _openSupplierFile,
    _closeSupplierFile,
    _openFormFromFile,
    _setFileTab,
    _reloadFileHallazgos,
  };
})();
