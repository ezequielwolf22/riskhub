/* Vista Tratamiento — Cockpit único de planes de tratamiento de riesgos. */
const ViewTreatment = (() => {

  const COLUMNS = [
    { id: 'untreated',    labelKey: 'treatment.col_untreated',    color: 'var(--risk-critical)' },
    { id: 'modification', labelKey: 'treatment.col_modification', color: 'var(--brand-purple)' },
    { id: 'sharing',      labelKey: 'treatment.col_sharing',      color: 'var(--brand-orange)' },
    { id: 'avoidance',    labelKey: 'treatment.col_avoidance',    color: 'var(--text-muted)' },
    { id: 'retention',    labelKey: 'treatment.col_retention',    color: 'var(--risk-low)' },
  ];

  let _board = null;
  let _users = [];
  let _filters = { option: '', owner: '', overdueOnly: false, q: '' };
  let _expandedId = null;

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('treatment.title')}</h1>
          <p class="page-sub">${t('treatment.subtitle')}</p>
        </div>
      </div>
      <div class="stats-row" id="tb-kpis" style="margin-bottom:16px;"></div>
      <div class="card" id="tb-burndown" style="margin-bottom:16px;"></div>
      <div class="card" style="margin-bottom:16px;padding:12px 16px;">
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
          <select id="tb-f-option" class="input" style="width:180px;">
            <option value="">${t('common.all')}</option>
            ${COLUMNS.map(c => `<option value="${c.id}">${t(c.labelKey)}</option>`).join('')}
          </select>
          <select id="tb-f-owner" class="input" style="width:180px;">
            <option value="">${t('treatment.filter_owner')}</option>
          </select>
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;">
            <input type="checkbox" id="tb-f-overdue"> ${t('treatment.filter_overdue_only')}
          </label>
          <input type="text" id="tb-f-search" class="input" style="flex:1;min-width:200px;"
                 placeholder="${t('treatment.search_placeholder')}">
        </div>
      </div>
      <div id="tb-columns"></div>
    `;

    document.getElementById('tb-f-option').onchange = (e) => { _filters.option = e.target.value; _renderColumns(); };
    document.getElementById('tb-f-owner').onchange = (e) => { _filters.owner = e.target.value; _renderColumns(); };
    document.getElementById('tb-f-overdue').onchange = (e) => { _filters.overdueOnly = e.target.checked; _renderColumns(); };
    document.getElementById('tb-f-search').oninput = (e) => { _filters.q = e.target.value.trim().toLowerCase(); _renderColumns(); };

    await _load();
  }

  async function _load() {
    try {
      const [board, users] = await Promise.all([
        Api.risks.treatmentBoard(),
        Api.listUsers().catch(() => []),
      ]);
      _board = board;
      _users = users;
      const sel = document.getElementById('tb-f-owner');
      if (sel) {
        const names = new Set();
        Object.values(board.columns).flat().forEach(it => { if (it.owner_name) names.add(it.owner_name); });
        [...names].sort().forEach(name => {
          const opt = document.createElement('option');
          opt.value = name; opt.textContent = name;
          sel.appendChild(opt);
        });
      }
      _renderKpis();
      _renderBurndown();
      _renderColumns();
    } catch (e) {
      UI.toast(t('common.error') + ': ' + e.message, 'error');
    }
  }

  function _renderKpis() {
    const wrap = document.getElementById('tb-kpis');
    if (!wrap || !_board) return;
    const k = _board.kpis;
    const card = (value, label, color, filterFn) => `
      <div class="stat-card" data-kpi-filter="${filterFn || ''}" style="${filterFn ? 'cursor:pointer;' : ''}">
        <div class="stat-value" style="${color ? `color:${color};` : ''}">${value}</div>
        <div class="stat-label">${label}</div>
      </div>`;
    wrap.innerHTML = [
      card(k.above_appetite, t('treatment.kpi_above_appetite'), k.above_appetite > 0 ? 'var(--risk-high)' : null),
      card(k.above_appetite_no_plan, `${t('treatment.kpi_no_plan')} <small style="display:block;font-weight:400;">${t('treatment.kpi_no_plan_hint')}</small>`, k.above_appetite_no_plan > 0 ? 'var(--risk-critical)' : null),
      card(k.above_appetite_no_coverage, `${t('treatment.kpi_no_coverage')} <small style="display:block;font-weight:400;">${t('treatment.kpi_no_coverage_hint')}</small>`, k.above_appetite_no_coverage > 0 ? 'var(--risk-critical)' : null),
      card(k.overdue_plans, t('treatment.kpi_overdue'), k.overdue_plans > 0 ? 'var(--risk-high)' : null, 'overdue'),
      card(k.avg_progress + '%', t('treatment.kpi_progress'), 'var(--brand-purple)'),
      card(k.pending_acceptance, t('treatment.kpi_pending_acceptance'), k.pending_acceptance > 0 ? 'var(--brand-orange)' : null),
      card(k.treated_without_evidence, `${t('treatment.kpi_no_evidence')} <small style="display:block;font-weight:400;">${t('treatment.kpi_no_evidence_hint')}</small>`, k.treated_without_evidence > 0 ? 'var(--risk-medium)' : null),
    ].join('');

    const overdueCard = wrap.querySelector('[data-kpi-filter="overdue"]');
    if (overdueCard) overdueCard.onclick = () => {
      document.getElementById('tb-f-overdue').checked = true;
      _filters.overdueOnly = true;
      _renderColumns();
    };
  }

  function _renderBurndown() {
    const wrap = document.getElementById('tb-burndown');
    if (!wrap || !_board) return;
    const bd = _board.burndown || { history: [], projected: [], appetite_line: 3 };
    const points = [...(bd.history || []), ...(bd.projected || [])];
    if (points.length < 2) {
      wrap.innerHTML = `<div style="padding:8px;"><h3 style="margin:0 0 6px;font-size:13px;">${t('treatment.burndown_title')}</h3>
        <p class="text-muted" style="font-size:12px;">—</p></div>`;
      return;
    }
    const W = 700, H = 140, PAD = 24;
    const values = points.map(p => p.total_residual || 0);
    const maxV = Math.max(...values, bd.appetite_line || 0, 1);
    const stepX = (W - PAD * 2) / (points.length - 1);
    const y = v => H - PAD - (v / maxV) * (H - PAD * 2);
    const histCount = (bd.history || []).length;

    const histPts = points.slice(0, histCount).map((p, i) => `${PAD + i * stepX},${y(p.total_residual || 0)}`).join(' ');
    const projStart = Math.max(0, histCount - 1);
    const projPts = points.slice(projStart).map((p, i) => `${PAD + (projStart + i) * stepX},${y(p.total_residual || 0)}`).join(' ');
    const appetiteY = y(bd.appetite_line || 0);

    wrap.innerHTML = `
      <div style="padding:8px;">
        <h3 style="margin:0 0 6px;font-size:13px;">${t('treatment.burndown_title')}</h3>
        <svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:700px;height:140px;">
          <line x1="${PAD}" y1="${appetiteY}" x2="${W - PAD}" y2="${appetiteY}" stroke="var(--risk-medium)" stroke-dasharray="3,3" stroke-width="1"/>
          ${histPts ? `<polyline points="${histPts}" fill="none" stroke="var(--brand-purple)" stroke-width="2"/>` : ''}
          ${projPts ? `<polyline points="${projPts}" fill="none" stroke="var(--brand-orange)" stroke-width="2" stroke-dasharray="5,4"/>` : ''}
        </svg>
        <div style="display:flex;gap:16px;font-size:11px;color:var(--text-muted);margin-top:4px;">
          <span><span style="display:inline-block;width:10px;height:2px;background:var(--brand-purple);vertical-align:middle;"></span> ${t('treatment.burndown_history')}</span>
          <span><span style="display:inline-block;width:10px;height:2px;background:var(--brand-orange);vertical-align:middle;"></span> ${t('treatment.burndown_projected')}</span>
        </div>
      </div>`;
  }

  function _matchesFilters(item) {
    if (_filters.owner && item.owner_name !== _filters.owner) return false;
    if (_filters.overdueOnly && !item.overdue) return false;
    if (_filters.q) {
      const hay = `${item.code} ${item.asset_name || ''} ${item.threat_name || ''}`.toLowerCase();
      if (!hay.includes(_filters.q)) return false;
    }
    return true;
  }

  function _renderColumns() {
    const wrap = document.getElementById('tb-columns');
    if (!wrap || !_board) return;
    const cols = _filters.option ? COLUMNS.filter(c => c.id === _filters.option) : COLUMNS;

    wrap.innerHTML = cols.map(col => {
      const items = (_board.columns[col.id] || []).filter(_matchesFilters);
      return `
        <div class="card" style="margin-bottom:14px;${col.id === 'untreated' && items.length ? 'border-left:3px solid var(--risk-critical);' : ''}">
          <div style="display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--border);">
            <span style="width:9px;height:9px;border-radius:50%;background:${col.color};display:inline-block;"></span>
            <strong style="font-size:13px;">${t(col.labelKey)}</strong>
            <span style="margin-left:auto;background:var(--bg-3);border-radius:999px;font-size:11px;font-weight:700;padding:2px 8px;color:var(--text-muted);">${items.length}</span>
          </div>
          ${items.length ? `
          <table class="data-table" style="width:100%;">
            <thead><tr>
              <th>${t('treatment.th_code')}</th>
              <th>${t('treatment.th_asset_threat')}</th>
              <th>${t('treatment.th_residual')}</th>
              <th>${t('treatment.th_progress')}</th>
              <th>${t('treatment.th_due')}</th>
              <th>${t('treatment.th_tasks')}</th>
              <th>${t('treatment.th_initiatives')}</th>
              <th>${t('treatment.th_owner')}</th>
            </tr></thead>
            <tbody>
              ${items.map(it => _rowHtml(it)).join('')}
            </tbody>
          </table>` : `<p class="text-muted" style="padding:12px 14px;font-size:12px;">${t('treatment.empty')}</p>`}
        </div>`;
    }).join('');

    wrap.querySelectorAll('[data-risk-row]').forEach(row => {
      row.onclick = (e) => {
        if (e.target.closest('[data-action]')) return;
        const id = parseInt(row.dataset.riskRow);
        _expandedId = _expandedId === id ? null : id;
        _renderColumns();
      };
    });
    wrap.querySelectorAll('[data-action="new-task"]').forEach(btn => {
      btn.onclick = (e) => { e.stopPropagation(); _openTaskModal(parseInt(btn.dataset.riskId)); };
    });
    wrap.querySelectorAll('[data-action="edit-treatment"]').forEach(btn => {
      btn.onclick = (e) => { e.stopPropagation(); _openTreatmentModal(parseInt(btn.dataset.riskId)); };
    });
    wrap.querySelectorAll('[data-action="ai-plan"]').forEach(btn => {
      btn.onclick = (e) => { e.stopPropagation(); _openAiPlanModal(parseInt(btn.dataset.riskId)); };
    });
    wrap.querySelectorAll('[data-action="open-risk"]').forEach(btn => {
      btn.onclick = (e) => { e.stopPropagation(); location.hash = '/risk-hub/risks'; };
    });
  }

  function _findItem(riskId) {
    for (const items of Object.values(_board.columns)) {
      const found = items.find(i => i.id === riskId);
      if (found) return found;
    }
    return null;
  }

  function _rowHtml(it) {
    const expanded = _expandedId === it.id;
    const dueFmt = it.treatment_due_date ? new Date(it.treatment_due_date).toLocaleDateString() : t('treatment.no_due_date');
    const initiativesHtml = (it.initiatives || []).map(ini => {
      const healthColor = ini.health === 'ok' ? 'var(--risk-low)' : ini.health === 'at_risk' ? 'var(--risk-medium)' : 'var(--risk-critical)';
      return `<span class="badge" title="${UI.esc(ini.title)}" style="background:${healthColor};color:#fff;margin-right:3px;">${UI.esc(ini.code)}</span>`;
    }).join('') || '—';

    let rows = `
      <tr data-risk-row="${it.id}" style="cursor:pointer;">
        <td>${UI.codePill(it.code)} ${it.analysis_stale ? `<span class="badge" style="background:var(--risk-medium);color:#fff;">${t('treatment.stale_badge')}</span>` : ''}</td>
        <td>${UI.esc(it.asset_name || '')}<br><small class="text-muted">${UI.esc(it.threat_name || '')}</small></td>
        <td>${UI.riskPill(it.residual_level)}${it.target_residual_level != null ? ` → ${UI.riskPill(it.target_residual_level)}` : ''}</td>
        <td>
          <div style="background:var(--bg-3);border-radius:999px;height:6px;width:80px;overflow:hidden;">
            <div style="background:var(--brand-purple);height:100%;width:${it.treatment_progress || 0}%;"></div>
          </div>
          <small>${it.treatment_progress || 0}%</small>
        </td>
        <td style="${it.overdue ? 'color:var(--risk-critical);font-weight:600;' : ''}">${dueFmt}</td>
        <td>${it.tasks.done}/${it.tasks.total}${it.tasks.overdue ? ` <span style="color:var(--risk-critical);">(${it.tasks.overdue} ${t('tasks.overdue').toLowerCase()})</span>` : ''}</td>
        <td>${initiativesHtml}</td>
        <td>${UI.esc(it.owner_name || t('treatment.no_owner'))}</td>
      </tr>`;

    if (expanded) {
      const controlsHtml = (it.controls || []).length
        ? `<table class="data-table" style="width:100%;font-size:12px;margin-bottom:10px;">
             <thead><tr><th>${t('common.code')}</th><th>${t('common.name')}</th><th>${t('plandirector.current_maturity')}</th><th>${t('treatment.evidence_col')}</th></tr></thead>
             <tbody>${it.controls.map(c => `
               <tr>
                 <td>${UI.esc(c.code || '')}</td>
                 <td>${UI.esc(c.name || '')}</td>
                 <td>${c.maturity}/5</td>
                 <td>${c.evidence_count ? c.evidence_count : `<span style="color:var(--risk-medium);">0</span>`}</td>
               </tr>`).join('')}</tbody>
           </table>`
        : `<p class="text-muted" style="font-size:12px;">${t('treatment.no_controls')}</p>`;

      const evidenceHtml = (it.evidence || []).length
        ? `<div style="display:flex;gap:6px;flex-wrap:wrap;">${it.evidence.map(ev => `
             <span class="badge" title="${UI.esc(ev.title)}" style="background:${ev.expired ? 'var(--risk-high)' : 'var(--bg-3)'};color:${ev.expired ? '#fff' : 'var(--text)'};">
               ${UI.esc(ev.code)}${ev.quality_level ? ` · ${UI.esc(ev.quality_level)}` : ''}${ev.expired ? ' · ' + t('treatment.evidence_expired') : ''}
             </span>`).join('')}</div>`
        : `<p style="font-size:12px;color:var(--risk-medium);">${t('treatment.no_evidence')}</p>`;

      rows += `
        <tr>
          <td colspan="8" style="background:var(--bg-2);padding:14px;">
            <h5 style="font-size:12px;margin:0 0 4px;">${t('risks.treatment_plan')}</h5>
            <div style="margin-bottom:10px;font-size:12px;white-space:pre-wrap;">
              ${it.treatment_plan ? UI.esc(it.treatment_plan) : t('common.no_data')}
            </div>
            ${it.acceptance && it.acceptance.justification ? `
              <h5 style="font-size:12px;margin:0 0 4px;">${t('treatment.acceptance_justification')}</h5>
              <div style="margin-bottom:10px;font-size:12px;">${UI.esc(it.acceptance.justification)}</div>` : ''}
            <h5 style="font-size:12px;margin:0 0 4px;">${t('treatment.controls_title')}</h5>
            ${controlsHtml}
            <h5 style="font-size:12px;margin:0 0 4px;">${t('treatment.evidence_title')}</h5>
            <div style="margin-bottom:10px;">${evidenceHtml}</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
              <button class="btn btn-sm" data-action="new-task" data-risk-id="${it.id}">+ ${t('treatment.new_task')}</button>
              <button class="btn btn-sm" data-action="edit-treatment" data-risk-id="${it.id}">${t('treatment.edit_treatment')}</button>
              <button class="btn btn-sm" data-action="ai-plan" data-risk-id="${it.id}">${t('treatment.generate_ai_plan')}</button>
              <button class="btn btn-sm btn-ghost" data-action="open-risk" data-risk-id="${it.id}">${t('treatment.open_risk')}</button>
            </div>
          </td>
        </tr>`;
    }
    return rows;
  }

  function _openTaskModal(riskId) {
    UI.modal(t('treatment.new_task'), `
      <div class="form-grid">
        <div class="span2"><label>${t('tasks.task_name')} *</label><input id="tt-title" class="input"></div>
        <div>
          <label>${t('common.owner')}</label>
          <select id="tt-assignee" class="input">
            <option value="">— ${t('common.not_assigned')} —</option>
            ${_users.map(u => `<option value="${u.id}">${UI.esc(u.full_name || u.email)}</option>`).join('')}
          </select>
        </div>
        <div><label>${t('common.due_date')}</label><input type="datetime-local" id="tt-due" class="input"></div>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const title = document.getElementById('tt-title').value.trim();
      if (!title) { UI.toast(t('tasks.task_name') + ' ' + t('common.required').toLowerCase(), 'error'); return; }
      try {
        const assigneeVal = document.getElementById('tt-assignee').value;
        await Api.tasks.create({
          title, risk_id: riskId,
          assigned_to_id: assigneeVal ? parseInt(assigneeVal) : null,
          due_date: document.getElementById('tt-due').value || null,
        });
        UI.toast(t('common.success'), 'success');
        UI.closeModal();
        await _load();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  function _openTreatmentModal(riskId) {
    const item = _findItem(riskId);
    if (!item) return;
    const options = [
      ['modification', t('risks.treatment_decision.reduce')],
      ['retention', t('risks.treatment_decision.accept')],
      ['avoidance', t('risks.treatment_decision.avoid')],
      ['sharing', t('risks.treatment_decision.transfer')],
    ];
    // El formulario se abre SIEMPRE con los valores actuales del riesgo: si se
    // abre vacio, guardar borra el plan y la fecha que ya existian.
    const dueValue = item.treatment_due_date ? item.treatment_due_date.slice(0, 10) : '';
    UI.modal(t('treatment.edit_treatment') + ' — ' + item.code, `
      <div class="form-grid">
        <div>
          <label>${t('risks.treatment')}</label>
          <select id="et-option" class="input">
            ${options.map(([v, l]) => `<option value="${v}" ${v === item.treatment_option ? 'selected' : ''}>${l}</option>`).join('')}
          </select>
        </div>
        <div><label>${t('common.due_date')}</label><input type="date" id="et-due" class="input" value="${dueValue}"></div>
        <div class="span2"><label>${t('risks.treatment_plan')}</label><textarea id="et-plan" class="input" rows="8">${UI.esc(item.treatment_plan || '')}</textarea></div>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      try {
        await Api.risks.update(riskId, {
          treatment_option: document.getElementById('et-option').value,
          treatment_due_date: document.getElementById('et-due').value || null,
          treatment_plan: document.getElementById('et-plan').value.trim(),
        });
        UI.toast(t('common.success'), 'success');
        UI.closeModal();
        await _load();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  async function _openAiPlanModal(riskId) {
    const item = _findItem(riskId);
    if (!item) return;
    UI.modal(t('treatment.generate_ai_plan') + ' — ' + item.code,
      `<p style="font-size:12px;color:var(--text-muted);">${t('treatment.ai_plan_loading')}</p>`,
      { width: 'min(700px,95vw)' });
    let draft;
    try {
      draft = await Api.risks.aiTreatmentPlan(riskId);
    } catch (e) {
      UI.toast(e.message, 'error');
      UI.closeModal();
      return;
    }
    const optionLabels = {
      modification: t('risks.treatment_decision.reduce'), retention: t('risks.treatment_decision.accept'),
      avoidance: t('risks.treatment_decision.avoid'), sharing: t('risks.treatment_decision.transfer'),
    };
    UI.modal(t('treatment.generate_ai_plan') + ' — ' + item.code, `
      <div class="notice" style="margin-bottom:10px;font-size:12px;">${t('plandirector.ai_generated_banner')}: ${UI.esc(draft.rationale || '')}</div>
      <div class="form-grid">
        <div><label>${t('risks.treatment')}</label>
          <select id="ap-option" class="input">
            ${Object.entries(optionLabels).map(([v, l]) => `<option value="${v}" ${v === draft.treatment_option ? 'selected' : ''}>${l}</option>`).join('')}
          </select>
        </div>
        <div class="span2"><label>${t('risks.treatment_plan')}</label><textarea id="ap-plan" class="input" rows="6">${UI.esc(draft.plan || '')}</textarea></div>
      </div>
      ${item.treatment_plan ? `
        <details style="margin-top:8px;">
          <summary style="cursor:pointer;font-size:12px;color:var(--text-muted);">${t('treatment.previous_plan')}</summary>
          <pre style="white-space:pre-wrap;font-size:12px;background:var(--bg-2);padding:8px;border-radius:6px;margin-top:6px;">${UI.esc(item.treatment_plan)}</pre>
        </details>` : ''}
      <h4 style="font-size:12px;margin:12px 0 6px;">${t('treatment.new_task')}</h4>
      <div>
        ${draft.tasks.map((tk, i) => `
          <label style="display:block;font-size:12px;margin-bottom:4px;">
            <input type="checkbox" data-ai-task="${i}" checked> ${UI.esc(tk.title)}
            <span class="badge">${UI.esc(tk.priority)}</span>
          </label>`).join('') || `<p class="text-muted" style="font-size:12px;">${t('common.no_data')}</p>`}
      </div>
    `, {
      width: 'min(700px,95vw)',
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="m-apply">${t('common.apply')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-apply').onclick = async () => {
      try {
        await Api.risks.update(riskId, {
          treatment_option: document.getElementById('ap-option').value,
          treatment_plan: document.getElementById('ap-plan').value.trim(),
        });
        const selectedTasks = draft.tasks.filter((_, i) => document.querySelector(`[data-ai-task="${i}"]`).checked);
        for (const tk of selectedTasks) {
          const due = new Date();
          due.setDate(due.getDate() + (tk.weeks_offset || 0) * 7);
          await Api.tasks.create({ title: tk.title, priority: tk.priority, risk_id: riskId, due_date: due.toISOString() });
        }
        UI.toast(t('common.success'), 'success');
        UI.closeModal();
        await _load();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  return { render };
})();
