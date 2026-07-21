/* Vista Plan Director — programas, iniciativas, OKRs, controles objetivo y
   riesgos afectados. Automatización: los riesgos se derivan de los controles
   objetivo y la reducción se proyecta con el motor determinista; nunca se
   estima a mano. */
const ViewPlanDirector = (() => {

  const HEALTH_COLOR = { ok: 'var(--risk-low)', at_risk: 'var(--risk-medium)', blocked: 'var(--risk-critical)' };
  const STATUS_COLOR = {
    draft: 'var(--text-muted)', approved: 'var(--brand-orange)', in_progress: 'var(--brand-purple)',
    on_hold: 'var(--risk-medium)', completed: 'var(--risk-low)', cancelled: 'var(--text-subtle)',
  };
  const PRIORITY_COLORS = {
    low: 'var(--risk-low)', medium: 'var(--risk-medium)', high: 'var(--risk-high)', critical: 'var(--risk-critical)',
  };

  let _section = 'summary';
  let _stats = null;
  let _burndown = null;
  let _initiatives = [];
  let _programs = [];
  let _users = [];
  let _impls = [];
  let _roadmap = null;
  let _portfolio = null;
  let _filters = { status: '', program: '', q: '' };
  let _roadFilters = { area: '', env: '', bu: '' };
  let _ganttScale = 'month';

  const SECTIONS = [
    ['summary', 'plandirector.tab_summary'],
    ['plan', 'plandirector.tab_plan'],
    ['roadmap', 'plandirector.tab_roadmap'],
    ['portfolio', 'plandirector.tab_portfolio'],
  ];

  /* Un control objetivo se identifica por su implementacion si la org ya la
     tiene, o por el control del catalogo si aun no existe (el backend la crea
     al guardar). Estas dos funciones traducen entre ambas formas. */
  function _ctrlKey(c) {
    return c.implementation_id ? `i:${c.implementation_id}` : `c:${c.control_id}`;
  }

  function _ctrlFromKey(key) {
    const [kind, rawId] = key.split(':');
    const id = parseInt(rawId);
    return kind === 'i' ? { implementation_id: id } : { control_id: id };
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('hub.risk.plan_director')}</h1>
          <p class="page-sub">${t('plandirector.subtitle')}</p>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          ${SECTIONS.map(([id, key]) => `<button class="btn" id="pd-seg-${id}">${t(key)}</button>`).join('')}
          <button class="btn btn-primary" id="pd-new-initiative">+ ${t('plandirector.new_initiative')}</button>
        </div>
      </div>
      <div id="pd-body"></div>
    `;
    SECTIONS.forEach(([id]) => {
      document.getElementById(`pd-seg-${id}`).onclick = () => { _section = id; _renderBody(); };
    });
    document.getElementById('pd-new-initiative').onclick = () => _openInitiativeWizard();

    await _loadAll();
    _renderBody();
  }

  async function _loadAll() {
    // Cada fuente se resuelve por separado: si una falla (p.ej. stats), el
    // resto de la pantalla sigue funcionando. Antes un unico fallo dejaba
    // programas e iniciativas vacios y parecia que no se hubieran guardado.
    const results = await Promise.allSettled([
      Api.initiatives.stats(),
      Api.initiatives.burndown(),
      Api.initiatives.list({}),
      Api.initiatives.programs.list(),
      Api.listUsers(),
      Api.initiatives.controlCatalog(),
      Api.initiatives.roadmap(),
      Api.initiatives.portfolio(),
    ]);
    const [stats, burndown, initiatives, programs, users, catalog, roadmap, portfolio] = results;
    _stats = stats.status === 'fulfilled' ? stats.value : null;
    _burndown = burndown.status === 'fulfilled' ? burndown.value : null;
    _initiatives = initiatives.status === 'fulfilled' ? initiatives.value : [];
    _programs = programs.status === 'fulfilled' ? programs.value : [];
    _users = users.status === 'fulfilled' ? users.value : [];
    _impls = catalog.status === 'fulfilled' ? catalog.value : [];
    _roadmap = roadmap.status === 'fulfilled' ? roadmap.value : null;
    _portfolio = portfolio.status === 'fulfilled' ? portfolio.value : null;

    const failed = results.filter(r => r.status === 'rejected');
    if (failed.length) {
      UI.toast(t('common.error') + ': ' + (failed[0].reason?.message || ''), 'error');
    }
  }

  function _renderBody() {
    const body = document.getElementById('pd-body');
    if (!body) return;
    SECTIONS.forEach(([id]) => {
      document.getElementById(`pd-seg-${id}`).classList.toggle('btn-primary', _section === id);
    });
    if (_section === 'summary') { body.innerHTML = _summaryHtml(); _wireSummary(); }
    else if (_section === 'plan') { body.innerHTML = _planHtml(); _wirePlan(); }
    else if (_section === 'roadmap') { body.innerHTML = _roadmapHtml(); _wireRoadmap(); }
    else { body.innerHTML = _portfolioHtml(); _wirePortfolio(); }
  }

  // ---------- Roadmap: Gantt, dependencias y camino critico ----------

  function _roadFiltered() {
    const bars = (_roadmap && _roadmap.bars) || [];
    return bars.filter(b => {
      if (_roadFilters.area && b.area !== _roadFilters.area) return false;
      if (_roadFilters.env && b.env !== _roadFilters.env) return false;
      if (_roadFilters.bu && !(b.business_units || []).includes(_roadFilters.bu)) return false;
      return true;
    });
  }

  function _roadmapHtml() {
    if (!_roadmap) return `<div class="card"><p class="text-muted" style="padding:16px;">${t('common.no_data')}</p></div>`;
    const c = _roadmap.counters || {};
    const cycles = (_roadmap.critical_path && _roadmap.critical_path.cycles) || [];
    return `
      <div class="stats-row" style="margin-bottom:14px;">
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-critical);">${c.overdue || 0}</div><div class="stat-label">${t('plandirector.counter_overdue')}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-medium);">${c.due_soon || 0}</div><div class="stat-label">${t('plandirector.counter_due_soon')}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-low);">${c.on_track || 0}</div><div class="stat-label">${t('plandirector.counter_on_track')}</div></div>
        <div class="stat-card"><div class="stat-value">${c.completed || 0}</div><div class="stat-label">${t('plandirector.status.completed')}</div></div>
      </div>
      ${cycles.length ? `<div class="notice" style="margin-bottom:12px;border-left:3px solid var(--risk-critical);">
        <strong>${t('plandirector.cycle_warning')}</strong> ${cycles.map(cy => UI.esc(cy.join(' → '))).join('; ')}
      </div>` : ''}
      <div class="card" style="margin-bottom:14px;padding:12px 16px;">
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
          <select id="rd-area" class="input" style="width:160px;">
            <option value="">${t('plandirector.all_areas')}</option>
            ${(_roadmap.areas || []).map(a => `<option value="${UI.esc(a)}" ${_roadFilters.area === a ? 'selected' : ''}>${UI.esc(a)}</option>`).join('')}
          </select>
          <select id="rd-env" class="input" style="width:140px;">
            <option value="">${t('plandirector.all_envs')}</option>
            ${['IT', 'OT', 'IoT', 'AI'].map(e => `<option value="${e}" ${_roadFilters.env === e ? 'selected' : ''}>${e}</option>`).join('')}
          </select>
          <select id="rd-bu" class="input" style="width:170px;">
            <option value="">${t('plandirector.all_bus')}</option>
            ${(_roadmap.business_units || []).map(b => `<option value="${UI.esc(b)}" ${_roadFilters.bu === b ? 'selected' : ''}>${UI.esc(b)}</option>`).join('')}
          </select>
          <select id="rd-scale" class="input" style="width:140px;">
            <option value="month" ${_ganttScale === 'month' ? 'selected' : ''}>${t('plandirector.scale_month')}</option>
            <option value="quarter" ${_ganttScale === 'quarter' ? 'selected' : ''}>${t('plandirector.scale_quarter')}</option>
          </select>
        </div>
      </div>
      <div class="card" style="padding:12px;overflow-x:auto;">
        <h3 style="margin:0 0 8px;font-size:13px;">${t('plandirector.gantt_title')}</h3>
        ${_ganttSvg(_roadFiltered())}
      </div>
      ${_criticalPathHtml()}
      ${_buMatrixHtml()}
    `;
  }

  function _ganttSvg(bars) {
    const withDates = bars.filter(b => b.start_date && b.target_date);
    if (!withDates.length) {
      return `<p class="text-muted" style="font-size:12px;">${t('plandirector.gantt_no_dates')}</p>`;
    }
    const starts = withDates.map(b => new Date(b.start_date).getTime());
    const ends = withDates.map(b => new Date(b.target_date).getTime());
    const min = new Date(Math.min(...starts));
    const max = new Date(Math.max(...ends));
    // Redondear a inicio/fin de mes para que el eje encaje con las etiquetas
    const t0 = new Date(min.getFullYear(), min.getMonth(), 1).getTime();
    const t1 = new Date(max.getFullYear(), max.getMonth() + 1, 0).getTime();
    const span = Math.max(1, t1 - t0);

    const LABEL_W = 230, ROW_H = 26, HEAD_H = 34, PAD = 8;
    const CHART_W = _ganttScale === 'quarter' ? 620 : 900;
    const W = LABEL_W + CHART_W + PAD * 2;
    const H = HEAD_H + withDates.length * ROW_H + PAD * 2;
    const x = ms => LABEL_W + PAD + ((ms - t0) / span) * CHART_W;

    // Eje temporal
    const ticks = [];
    const cursor = new Date(t0);
    while (cursor.getTime() <= t1) {
      const isQuarter = cursor.getMonth() % 3 === 0;
      if (_ganttScale === 'month' || isQuarter) {
        ticks.push({
          ms: cursor.getTime(),
          label: _ganttScale === 'quarter'
            ? `Q${Math.floor(cursor.getMonth() / 3) + 1} ${String(cursor.getFullYear()).slice(2)}`
            : cursor.toLocaleDateString(undefined, { month: 'short' }) + (cursor.getMonth() === 0 ? ` ${String(cursor.getFullYear()).slice(2)}` : ''),
        });
      }
      cursor.setMonth(cursor.getMonth() + 1);
    }

    const now = Date.now();
    const nowX = now >= t0 && now <= t1 ? x(now) : null;
    const healthColor = h => HEALTH_COLOR[h] || 'var(--text-muted)';

    const rows = withDates.map((b, i) => {
      const y = HEAD_H + i * ROW_H + PAD;
      const bx = x(new Date(b.start_date).getTime());
      const bw = Math.max(3, x(new Date(b.target_date).getTime()) - bx);
      const pct = Math.max(0, Math.min(100, b.progress || 0));
      const title = `${b.code} · ${b.title}${b.health_reasons && b.health_reasons.length ? ' — ' + b.health_reasons.join('; ') : ''}`;
      return `
        <g>
          <title>${UI.esc(title)}</title>
          <text x="${PAD}" y="${y + 15}" font-size="11" fill="var(--text)" >
            ${b.on_critical_path ? '▶ ' : ''}${UI.esc((b.code + ' ' + b.title).slice(0, 34))}
          </text>
          <rect x="${bx}" y="${y + 5}" width="${bw}" height="14" rx="3"
                fill="${healthColor(b.health)}" opacity="0.28"
                stroke="${b.on_critical_path ? 'var(--brand-orange)' : 'none'}" stroke-width="1.5"/>
          <rect x="${bx}" y="${y + 5}" width="${bw * pct / 100}" height="14" rx="3"
                fill="${healthColor(b.health)}"/>
          ${b.quick_win ? `<text x="${bx + bw + 4}" y="${y + 16}" font-size="9" fill="var(--risk-low)">★</text>` : ''}
        </g>`;
    }).join('');

    return `
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;min-width:${W}px;height:${H}px;">
        ${ticks.map(tk => `
          <line x1="${x(tk.ms)}" y1="${HEAD_H - 6}" x2="${x(tk.ms)}" y2="${H - PAD}"
                stroke="var(--border)" stroke-width="1"/>
          <text x="${x(tk.ms) + 3}" y="${HEAD_H - 12}" font-size="10" fill="var(--text-muted)">${tk.label}</text>
        `).join('')}
        ${nowX !== null ? `<line x1="${nowX}" y1="${HEAD_H - 6}" x2="${nowX}" y2="${H - PAD}"
              stroke="var(--brand-orange)" stroke-width="1.5" stroke-dasharray="4,3"/>
              <text x="${nowX + 3}" y="${H - PAD}" font-size="9" fill="var(--brand-orange)">${t('plandirector.today')}</text>` : ''}
        ${rows}
      </svg>
      <div style="display:flex;gap:14px;font-size:11px;color:var(--text-muted);margin-top:6px;flex-wrap:wrap;">
        <span><span style="display:inline-block;width:9px;height:9px;background:var(--risk-low);border-radius:2px;"></span> ${t('plandirector.health_ok')}</span>
        <span><span style="display:inline-block;width:9px;height:9px;background:var(--risk-medium);border-radius:2px;"></span> ${t('plandirector.health_at_risk')}</span>
        <span><span style="display:inline-block;width:9px;height:9px;background:var(--risk-critical);border-radius:2px;"></span> ${t('plandirector.health_blocked')}</span>
        <span>▶ ${t('plandirector.critical_path')}</span>
        <span>★ ${t('plandirector.quick_win')}</span>
      </div>`;
  }

  function _criticalPathHtml() {
    const cp = _roadmap.critical_path || {};
    if (!cp.path || !cp.path.length) return '';
    return `
      <div class="card" style="margin-top:14px;padding:12px 16px;">
        <h3 style="margin:0 0 6px;font-size:13px;">${t('plandirector.critical_path')}
          <span class="text-muted" style="font-weight:400;font-size:11px;">
            — ${t('plandirector.critical_path_hint', { days: cp.total_days })}</span>
        </h3>
        <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;font-size:12px;">
          ${cp.path.map((p, i) => `
            ${i ? '<span style="color:var(--text-muted);">→</span>' : ''}
            <span class="badge" title="${UI.esc(p.title)}">${UI.esc(p.code)} (${p.duration_days}d)</span>
          `).join('')}
        </div>
      </div>`;
  }

  function _buMatrixHtml() {
    const bus = _roadmap.business_units || [];
    const bars = _roadFiltered().filter(b => (b.business_units || []).length);
    if (!bus.length || !bars.length) return '';
    return `
      <div class="card" style="margin-top:14px;">
        <div style="padding:10px 14px;border-bottom:1px solid var(--border);">
          <strong style="font-size:13px;">${t('plandirector.bu_deployment')}</strong>
          <span class="text-muted" style="font-size:11px;"> — ${t('plandirector.bu_deployment_hint')}</span>
        </div>
        <div style="overflow-x:auto;">
          <table class="data-table" style="width:100%;font-size:12px;">
            <thead><tr><th>${t('common.code')}</th><th>${t('common.title')}</th>
              ${bus.map(b => `<th style="text-align:center;">${UI.esc(b)}</th>`).join('')}</tr></thead>
            <tbody>
              ${bars.map(bar => `
                <tr>
                  <td>${UI.codePill(bar.code)}</td>
                  <td>${UI.esc(bar.title.slice(0, 40))}</td>
                  ${bus.map(bu => `<td style="text-align:center;">${
                    (bar.business_units || []).includes(bu)
                      ? `<span style="color:${HEALTH_COLOR[bar.health] || 'var(--text-muted)'};">●</span>` : '·'
                  }</td>`).join('')}
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>`;
  }

  function _wireRoadmap() {
    const bind = (id, key) => {
      const el = document.getElementById(id);
      if (el) el.onchange = (e) => { _roadFilters[key] = e.target.value; _renderBody(); };
    };
    bind('rd-area', 'area');
    bind('rd-env', 'env');
    bind('rd-bu', 'bu');
    const scale = document.getElementById('rd-scale');
    if (scale) scale.onchange = (e) => { _ganttScale = e.target.value; _renderBody(); };
  }

  // ---------- Cartera priorizada y presupuesto ----------

  function _portfolioHtml() {
    if (!_portfolio) return `<div class="card"><p class="text-muted" style="padding:16px;">${t('common.no_data')}</p></div>`;
    const p = _portfolio;
    const b = p.budget || {};
    const fmt = n => (n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
    return `
      <div class="stats-row" style="margin-bottom:14px;">
        <div class="stat-card"><div class="stat-value">${fmt(b.requested)}</div><div class="stat-label">${t('plandirector.budget_requested')}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-low);">${fmt(b.approved)}</div><div class="stat-label">${t('plandirector.budget_approved_label')}</div></div>
        <div class="stat-card"><div class="stat-value">${fmt(b.spent)}</div><div class="stat-label">${t('plandirector.budget_spent')}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:${(b.underfunded || []).length ? 'var(--risk-high)' : ''};">${(b.underfunded || []).length}</div><div class="stat-label">${t('plandirector.underfunded')}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-low);">${(p.quick_wins || []).length}</div><div class="stat-label">${t('plandirector.quick_wins')}</div></div>
      </div>

      ${(b.largest_gaps || []).length ? `
      <div class="card" style="margin-bottom:14px;padding:12px 16px;">
        <h3 style="margin:0 0 8px;font-size:13px;">${t('plandirector.funding_gap')}
          <span class="text-muted" style="font-weight:400;font-size:11px;"> — ${t('plandirector.funding_gap_hint')}</span></h3>
        ${b.largest_gaps.slice(0, 6).map(g => {
          const max = b.largest_gaps[0].gap || 1;
          return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;font-size:12px;">
            <span style="width:90px;">${UI.esc(g.code)}</span>
            <div style="flex:1;background:var(--bg-3);border-radius:3px;height:12px;overflow:hidden;">
              <div style="background:var(--brand-orange);height:100%;width:${(g.gap / max) * 100}%;"></div>
            </div>
            <span style="width:110px;text-align:right;">${fmt(g.gap)}</span>
          </div>`;
        }).join('')}
      </div>` : ''}

      <div class="card">
        <div style="padding:10px 14px;border-bottom:1px solid var(--border);">
          <strong style="font-size:13px;">${t('plandirector.portfolio_ranking')}</strong>
          <span class="text-muted" style="font-size:11px;"> — ${t('plandirector.portfolio_hint')}</span>
        </div>
        <div style="overflow-x:auto;">
        <table class="data-table" style="width:100%;font-size:12px;">
          <thead><tr>
            <th>${t('common.code')}</th><th>${t('common.title')}</th>
            <th>${t('plandirector.reduction_points')}</th>
            <th>${t('plandirector.efficiency')}</th>
            <th>${t('plandirector.cost_per_point')}</th>
            <th>${t('plandirector.horizon')}</th>
            <th>${t('plandirector.origin_col')}</th>
            <th>${t('common.priority')}</th>
          </tr></thead>
          <tbody>
            ${p.initiatives.map(r => `
              <tr>
                <td>${UI.codePill(r.code)}${r.quick_win ? ` <span class="badge" style="background:var(--risk-low);color:#fff;">${t('plandirector.quick_win')}</span>` : ''}</td>
                <td>${UI.esc(r.title)}</td>
                <td>${r.projected_reduction_points}</td>
                <td>${r.priority_score !== null && r.priority_score !== undefined ? r.priority_score : '—'}</td>
                <td>${r.cost_per_point !== null && r.cost_per_point !== undefined ? r.cost_per_point.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '—'}</td>
                <td>${r.horizon ? t('plandirector.horizon_' + r.horizon) : '—'}</td>
                <td>${r.origin ? UI.esc(r.origin) : '—'}</td>
                <td>
                  <span class="badge" style="background:${PRIORITY_COLORS[r.priority] || '#888'};color:#fff;">${UI.esc(r.priority)}</span>
                  ${r.priority_overridden && r.priority_suggested
                    ? `<br><small class="text-muted" title="${t('plandirector.suggested_hint')}">${t('plandirector.suggested')}: ${UI.esc(r.priority_suggested)}</small>` : ''}
                </td>
              </tr>`).join('')}
          </tbody>
        </table>
        </div>
      </div>

      <div class="card" style="margin-top:14px;padding:12px 16px;">
        <h3 style="margin:0 0 8px;font-size:13px;">${t('plandirector.distribution')}</h3>
        <div style="display:flex;gap:24px;flex-wrap:wrap;font-size:12px;">
          ${[['by_horizon', 'plandirector.horizon'], ['by_origin', 'plandirector.origin_col'],
             ['by_action_type', 'plandirector.action_type'], ['by_env', 'plandirector.env'],
             ['by_nist_function', 'NIST']].map(([key, label]) => `
            <div>
              <strong>${label.includes('.') ? t(label) : label}</strong>
              <ul style="margin:4px 0;padding-left:16px;">
                ${Object.entries(p[key] || {}).map(([k, v]) => `<li>${UI.esc(k)}: ${v}</li>`).join('') || '<li>—</li>'}
              </ul>
            </div>`).join('')}
        </div>
      </div>`;
  }

  function _wirePortfolio() { /* solo lectura por ahora */ }

  // ---------- Resumen ----------

  function _summaryHtml() {
    if (!_stats) return '';
    const s = _stats;
    return `
      <div class="stats-row" style="margin-bottom:16px;">
        <div class="stat-card"><div class="stat-value">${s.initiatives_total}</div><div class="stat-label">${t('plandirector.stat_total')}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:${s.by_health.at_risk + s.by_health.blocked > 0 ? 'var(--risk-critical)' : ''}">${s.by_health.at_risk + s.by_health.blocked}</div><div class="stat-label">${t('plandirector.stat_at_risk')}</div></div>
        <div class="stat-card"><div class="stat-value">${s.avg_progress}%</div><div class="stat-label">${t('plandirector.stat_progress')}</div></div>
        <div class="stat-card"><div class="stat-value">${s.risks_covered}</div><div class="stat-label">${t('plandirector.stat_risks_covered')}</div></div>
        <div class="stat-card"><div class="stat-value">${s.budget.approved.toLocaleString()}</div><div class="stat-label">${t('plandirector.stat_budget_approved')}</div></div>
      </div>
      <div class="card" style="padding:14px;margin-bottom:16px;">
        <h3 style="margin:0 0 8px;font-size:13px;">${t('plandirector.reduction_title')}</h3>
        <div style="display:flex;gap:24px;align-items:center;">
          <div><strong style="font-size:20px;color:var(--brand-orange);">${s.reduction.projected_points}</strong> <span class="text-muted" style="font-size:12px;">${t('plandirector.reduction_projected')}</span></div>
          <div><strong style="font-size:20px;color:var(--risk-low);">${s.reduction.achieved_points}</strong> <span class="text-muted" style="font-size:12px;">${t('plandirector.reduction_achieved')}</span></div>
        </div>
      </div>
      ${_burndownHtml()}
      <div class="card" style="margin-top:16px;">
        <div style="padding:10px 14px;border-bottom:1px solid var(--border);">
          <strong style="font-size:13px;">${t('plandirector.uncovered_title')}</strong>
        </div>
        ${(s.high_risks_uncovered || []).length ? `
        <table class="data-table" style="width:100%;">
          <thead><tr><th>${t('treatment.th_code')}</th><th>${t('treatment.th_asset_threat')}</th><th>${t('treatment.th_residual')}</th><th></th></tr></thead>
          <tbody>
            ${s.high_risks_uncovered.map(r => `
              <tr>
                <td>${UI.codePill(r.code)}</td>
                <td>${UI.esc(r.asset_name || '')} <small class="text-muted">${UI.esc(r.threat_name || '')}</small></td>
                <td>${UI.riskPill(r.residual_level)}</td>
                <td style="white-space:nowrap;">
                  <button class="btn btn-sm btn-primary" data-draft-risk="${r.id}" data-risk-code="${UI.esc(r.code)}">${t('plandirector.generate_draft')}</button>
                  <button class="btn btn-sm" data-link-risk="${r.id}" data-risk-code="${UI.esc(r.code)}">${t('plandirector.link_to_initiative')}</button>
                </td>
              </tr>`).join('')}
          </tbody>
        </table>` : `<p class="text-muted" style="padding:12px 14px;font-size:12px;">${t('plandirector.no_uncovered')}</p>`}
      </div>
    `;
  }

  function _burndownHtml() {
    const bd = _burndown || { history: [], projected: [], appetite_line: 3 };
    const points = [...(bd.history || []), ...(bd.projected || [])];
    if (points.length < 2) {
      return `<div class="card" style="padding:14px;"><h3 style="margin:0 0 8px;font-size:13px;">${t('treatment.burndown_title')}</h3><p class="text-muted" style="font-size:12px;">—</p></div>`;
    }
    const W = 900, H = 220, PAD = 30;
    const values = points.map(p => p.total_residual || 0);
    const maxV = Math.max(...values, bd.appetite_line || 0, 1);
    const stepX = (W - PAD * 2) / (points.length - 1);
    const y = v => H - PAD - (v / maxV) * (H - PAD * 2);
    const histCount = (bd.history || []).length;
    const histPts = points.slice(0, histCount).map((p, i) => `${PAD + i * stepX},${y(p.total_residual || 0)}`).join(' ');
    const projStart = Math.max(0, histCount - 1);
    const projPts = points.slice(projStart).map((p, i) => `${PAD + (projStart + i) * stepX},${y(p.total_residual || 0)}`).join(' ');
    const appetiteY = y(bd.appetite_line || 0);
    return `
      <div class="card" style="padding:14px;">
        <h3 style="margin:0 0 8px;font-size:13px;">${t('treatment.burndown_title')}</h3>
        <svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:900px;height:220px;">
          <line x1="${PAD}" y1="${appetiteY}" x2="${W - PAD}" y2="${appetiteY}" stroke="var(--risk-medium)" stroke-dasharray="3,3" stroke-width="1"/>
          ${histPts ? `<polyline points="${histPts}" fill="none" stroke="var(--brand-purple)" stroke-width="2.5"/>` : ''}
          ${projPts ? `<polyline points="${projPts}" fill="none" stroke="var(--brand-orange)" stroke-width="2.5" stroke-dasharray="6,4"/>` : ''}
        </svg>
        <div style="display:flex;gap:16px;font-size:11px;color:var(--text-muted);margin-top:4px;">
          <span><span style="display:inline-block;width:10px;height:2px;background:var(--brand-purple);vertical-align:middle;"></span> ${t('treatment.burndown_history')}</span>
          <span><span style="display:inline-block;width:10px;height:2px;background:var(--brand-orange);vertical-align:middle;"></span> ${t('treatment.burndown_projected')}</span>
        </div>
      </div>`;
  }

  function _wireSummary() {
    document.querySelectorAll('[data-link-risk]').forEach(btn => {
      btn.onclick = () => _openLinkRiskToInitiative(parseInt(btn.dataset.linkRisk), btn.dataset.riskCode);
    });
    document.querySelectorAll('[data-draft-risk]').forEach(btn => {
      btn.onclick = () => _openDraftModal(parseInt(btn.dataset.draftRisk), btn.dataset.riskCode);
    });
  }

  async function _openDraftModal(riskId, riskCode) {
    UI.modal(`${t('plandirector.generate_draft')} — ${riskCode}`,
      `<p style="font-size:12px;color:var(--text-muted);">${t('plandirector.draft_loading')}</p>`,
      { width: 'min(800px,95vw)' });
    let draft;
    try {
      draft = await Api.initiatives.draftForRisk([riskId]);
    } catch (e) {
      UI.toast(e.message, 'error');
      UI.closeModal();
      return;
    }
    const targetsById = new Map(draft.control_targets.map(ct => [ct.implementation_id, ct]));
    const targetImpls = _impls.filter(c => c.implementation_id && targetsById.has(c.implementation_id));
    UI.modal(`${t('plandirector.generate_draft')} — ${riskCode}`, `
      <div class="notice" style="margin-bottom:10px;font-size:12px;">${t('plandirector.ai_generated_banner')}: ${UI.esc(draft.rationale || '')}</div>
      <div class="form-grid">
        <div class="span2"><label>${t('common.title')} *</label><input id="dr-title" class="input" value="${UI.esc(draft.title || '')}"></div>
        <div>
          <label>${t('common.priority')}</label>
          <select id="dr-priority" class="input">
            ${['low', 'medium', 'high', 'critical'].map(p => `<option value="${p}" ${p === draft.priority ? 'selected' : ''}>${p}</option>`).join('')}
          </select>
        </div>
        <div class="span2"><label>${t('common.description')}</label><textarea id="dr-desc" class="input" rows="3">${UI.esc(draft.description || '')}</textarea></div>
      </div>
      <h4 style="font-size:12px;margin:12px 0 6px;">${t('plandirector.control_targets_title')} (${targetImpls.length})</h4>
      <div>
        ${targetImpls.map(c => {
          const ct = targetsById.get(c.implementation_id);
          return `<label style="display:block;font-size:12px;margin-bottom:4px;">
            <input type="checkbox" data-dr-target="${c.implementation_id}" checked>
            ${UI.esc(c.code || '')} — ${UI.esc(c.name || '')}
            (${c.maturity}/5 → <strong>${ct.target_maturity}/5</strong>)
          </label>`;
        }).join('') || `<p class="text-muted" style="font-size:12px;">${t('common.no_data')}</p>`}
      </div>
      ${draft.skipped_controls && draft.skipped_controls.length
        ? `<p class="text-muted" style="font-size:11px;margin-top:6px;">${t('plandirector.import_skipped')}: ${UI.esc(draft.skipped_controls.join(', '))}</p>` : ''}
    `, {
      width: 'min(800px,95vw)',
      actions: `<button class="btn" id="dr-discard">${t('plandirector.draft_discard')}</button>
                <button class="btn btn-primary" id="dr-create">${t('plandirector.draft_create')}</button>`,
    });
    document.getElementById('dr-discard').onclick = async () => {
      try {
        await Api.initiatives.draftDiscard({ risk_ids: draft.risk_ids || [riskId], title: draft.title });
      } catch (_) { /* la señal es best-effort */ }
      UI.closeModal();
    };
    document.getElementById('dr-create').onclick = async () => {
      const title = document.getElementById('dr-title').value.trim();
      if (!title) { UI.toast(t('common.required'), 'error'); return; }
      const selectedTargets = draft.control_targets.filter(ct =>
        document.querySelector(`[data-dr-target="${ct.implementation_id}"]`)?.checked);
      try {
        const created = await Api.initiatives.draftConfirm({
          title,
          description: document.getElementById('dr-desc').value.trim() || null,
          priority: document.getElementById('dr-priority').value,
          expected_risk_reduction: draft.expected_risk_reduction || null,
          rationale: draft.rationale || null,
          control_targets: selectedTargets.map(ct => ({
            implementation_id: ct.implementation_id, target_maturity: ct.target_maturity,
          })),
          risk_ids: draft.risk_ids || [riskId],
        });
        UI.toast(t('common.success'), 'success');
        UI.closeModal();
        await _loadAll();
        _renderBody();
        _openInitiativeDetail(created.id);
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  function _openLinkRiskToInitiative(riskId, riskCode) {
    const activeInitiatives = _initiatives.filter(i => ['draft', 'approved', 'in_progress'].includes(i.status));
    UI.modal(`${t('plandirector.link_to_initiative')} — ${riskCode}`, `
      <div class="form-grid">
        <div class="span2">
          <label>${t('plandirector.choose_initiative')}</label>
          <select id="lr-initiative" class="input">
            ${activeInitiatives.map(i => `<option value="${i.id}">${UI.esc(i.code)} — ${UI.esc(i.title)}</option>`).join('')}
          </select>
        </div>
        <div class="span2"><label>${t('common.notes')}</label><textarea id="lr-rationale" class="input" rows="2"></textarea></div>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const iniId = document.getElementById('lr-initiative').value;
      if (!iniId) { UI.toast(t('common.required'), 'error'); return; }
      try {
        await Api.initiatives.risks.link(iniId, {
          risk_id: riskId, rationale: document.getElementById('lr-rationale').value.trim() || null,
        });
        UI.toast(t('common.success'), 'success');
        UI.closeModal();
        await _loadAll();
        _renderBody();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  // ---------- Plan (arbol Programa -> Iniciativas) ----------

  function _planHtml() {
    return `
      <div class="card" style="margin-bottom:14px;padding:12px 16px;">
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
          <select id="pd-f-status" class="input" style="width:180px;">
            <option value="">${t('common.all')}</option>
            ${['draft', 'approved', 'in_progress', 'on_hold', 'completed', 'cancelled'].map(s => `<option value="${s}">${_statusLabel(s)}</option>`).join('')}
          </select>
          <select id="pd-f-program" class="input" style="width:200px;">
            <option value="">${t('common.all')}</option>
            ${_programs.map(p => `<option value="${p.id}">${UI.esc(p.name)}</option>`).join('')}
          </select>
          <input type="text" id="pd-f-search" class="input" style="flex:1;min-width:200px;" placeholder="${t('common.search')}...">
          <button class="btn btn-ghost" id="pd-new-program">+ ${t('plandirector.new_program')}</button>
          <button class="btn btn-ghost" id="pd-import">${t('plandirector.import_button')}</button>
        </div>
      </div>
      <div id="pd-tree"></div>
    `;
  }

  function _statusLabel(s) {
    const map = {
      draft: t('plandirector.status.draft'), approved: t('plandirector.status.approved'),
      in_progress: t('plandirector.status.in_progress'), on_hold: t('plandirector.status.on_hold'),
      completed: t('plandirector.status.completed'), cancelled: t('plandirector.status.cancelled'),
    };
    return map[s] || s;
  }

  function _wirePlan() {
    document.getElementById('pd-f-status').onchange = (e) => { _filters.status = e.target.value; _renderTree(); };
    document.getElementById('pd-f-program').onchange = (e) => { _filters.program = e.target.value; _renderTree(); };
    document.getElementById('pd-f-search').oninput = (e) => { _filters.q = e.target.value.trim().toLowerCase(); _renderTree(); };
    document.getElementById('pd-new-program').onclick = () => _openProgramModal();
    document.getElementById('pd-import').onclick = () => _openImportModal();
    _renderTree();
  }

  function _renderTree() {
    const wrap = document.getElementById('pd-tree');
    if (!wrap) return;
    let items = _initiatives;
    if (_filters.status) items = items.filter(i => i.status === _filters.status);
    if (_filters.program) items = items.filter(i => String(i.program_id) === _filters.program);
    if (_filters.q) items = items.filter(i => `${i.code} ${i.title}`.toLowerCase().includes(_filters.q));

    const byProgram = new Map();
    items.forEach(i => {
      const key = i.program_id || 0;
      if (!byProgram.has(key)) byProgram.set(key, []);
      byProgram.get(key).push(i);
    });

    if (!items.length) {
      wrap.innerHTML = `<div class="card"><p class="text-muted" style="padding:16px;font-size:13px;">${t('plandirector.no_initiatives')}</p></div>`;
      return;
    }

    wrap.innerHTML = [...byProgram.entries()].map(([progId, list]) => {
      const prog = _programs.find(p => p.id === progId);
      const progName = prog ? prog.name : t('plandirector.no_program');
      return `
        <div class="card" style="margin-bottom:14px;">
          <div style="padding:10px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;">
            <strong style="font-size:13px;">${UI.esc(progName)}</strong>
            ${prog ? `<span class="text-muted" style="font-size:11px;">${UI.esc(prog.area || '')}</span>` : ''}
            <span style="margin-left:auto;font-size:11px;color:var(--text-muted);">${list.length}</span>
          </div>
          <table class="data-table" style="width:100%;">
            <thead><tr>
              <th>${t('common.code')}</th><th>${t('common.title')}</th><th>NIST</th>
              <th>${t('common.status')}</th><th>${t('plandirector.health')}</th>
              <th>${t('common.priority')}</th><th>${t('treatment.th_progress')}</th>
              <th>${t('plandirector.risks_col')}</th><th>${t('plandirector.target_date')}</th><th>${t('common.owner')}</th>
            </tr></thead>
            <tbody>
              ${list.map(i => _initiativeRow(i)).join('')}
            </tbody>
          </table>
        </div>`;
    }).join('');

    wrap.querySelectorAll('[data-open-initiative]').forEach(row => {
      row.onclick = () => _openInitiativeDetail(parseInt(row.dataset.openInitiative));
    });
  }

  function _initiativeRow(i) {
    const healthColor = HEALTH_COLOR[i.health] || 'var(--text-muted)';
    const overdue = i.target_date && i.status !== 'completed' && new Date(i.target_date) < new Date();
    const dateFmt = i.target_date ? new Date(i.target_date).toLocaleDateString() : '—';
    return `
      <tr data-open-initiative="${i.id}" style="cursor:pointer;">
        <td>${UI.codePill(i.code)}</td>
        <td>${UI.esc(i.title)}</td>
        <td>${i.nist_function ? `<span class="badge">${UI.esc(i.nist_function)}</span>` : '—'}</td>
        <td><span class="badge" style="background:${STATUS_COLOR[i.status] || '#888'};color:#fff;">${_statusLabel(i.status)}</span></td>
        <td><span title="${(i.health_reasons || []).join('; ')}" style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${healthColor};"></span></td>
        <td><span class="badge" style="background:${PRIORITY_COLORS[i.priority] || '#888'};color:#fff;">${UI.esc(i.priority)}</span></td>
        <td>
          <div style="background:var(--bg-3);border-radius:999px;height:6px;width:70px;overflow:hidden;display:inline-block;vertical-align:middle;">
            <div style="background:var(--brand-purple);height:100%;width:${i.progress || 0}%;"></div>
          </div> ${i.progress || 0}%
        </td>
        <td>${i.risks_count}${i.projected_reduction_points ? ` <small style="color:var(--risk-low);">(-${i.projected_reduction_points})</small>` : ''}</td>
        <td style="${overdue ? 'color:var(--risk-critical);font-weight:600;' : ''}">${dateFmt}</td>
        <td>${UI.esc(i.owner_name || '—')}</td>
      </tr>`;
  }

  function _openProgramModal() {
    UI.modal(t('plandirector.new_program'), `
      <div class="form-grid">
        <div class="span2"><label>${t('common.name')} *</label><input id="pg-name" class="input"></div>
        <div><label>${t('plandirector.area')}</label><input id="pg-area" class="input"></div>
        <div>
          <label>${t('common.owner')}</label>
          <select id="pg-responsible" class="input">
            <option value="">— ${t('common.not_assigned')} —</option>
            ${_users.map(u => `<option value="${u.id}">${UI.esc(u.full_name || u.email)}</option>`).join('')}
          </select>
        </div>
        <div><label>${t('plandirector.budget')}</label><input type="number" id="pg-budget" class="input"></div>
        <div class="span2"><label>${t('common.description')}</label><textarea id="pg-desc" class="input" rows="2"></textarea></div>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const name = document.getElementById('pg-name').value.trim();
      if (!name) { UI.toast(t('common.required'), 'error'); return; }
      try {
        await Api.initiatives.programs.create({
          name, area: document.getElementById('pg-area').value.trim() || null,
          responsible_id: document.getElementById('pg-responsible').value ? parseInt(document.getElementById('pg-responsible').value) : null,
          budget: document.getElementById('pg-budget').value ? parseFloat(document.getElementById('pg-budget').value) : null,
          description: document.getElementById('pg-desc').value.trim() || null,
        });
        UI.toast(t('common.success'), 'success');
        UI.closeModal();
        await _loadAll();
        _renderBody();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  // ---------- Importar plan desde archivo (IA) ----------

  function _openImportModal() {
    UI.modal(t('plandirector.import_button'), `
      <p class="text-muted" style="font-size:12px;margin-bottom:10px;">${t('plandirector.import_hint')}</p>
      <input type="file" id="im-file" accept=".pdf,.docx,.xlsx,.txt,.md">
      <div id="im-status" style="margin-top:10px;font-size:12px;"></div>
      <div id="im-preview" style="margin-top:10px;"></div>
    `, {
      width: 'min(1000px,95vw)',
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="im-analyze">${t('plandirector.import_analyze')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;

    let preview = null;
    let confirmBtn = null;

    document.getElementById('im-analyze').onclick = async () => {
      const fileInput = document.getElementById('im-file');
      const file = fileInput.files[0];
      if (!file) { UI.toast(t('common.required'), 'error'); return; }
      const statusEl = document.getElementById('im-status');
      statusEl.textContent = t('plandirector.import_analyzing');
      try {
        preview = await Api.initiatives.import(file);
        statusEl.textContent = '';
        _renderImportPreview(preview);
        if (!confirmBtn) {
          confirmBtn = document.createElement('button');
          confirmBtn.className = 'btn btn-primary';
          confirmBtn.textContent = t('plandirector.import_confirm');
          confirmBtn.onclick = async () => {
            try {
              const result = await Api.initiatives.importConfirm(preview);
              UI.toast(t('plandirector.import_created', {
                programs: result.created.programs, initiatives: result.created.initiatives,
                points: result.total_projected_points,
              }), 'success');
              UI.closeModal();
              await _loadAll();
              _section = 'plan';
              _renderBody();
            } catch (e) { UI.toast(e.message, 'error'); }
          };
          document.querySelector('.modal-foot').appendChild(confirmBtn);
        }
      } catch (e) {
        statusEl.textContent = '';
        UI.toast(e.message, 'error');
      }
    };
  }

  function _renderImportPreview(preview) {
    const wrap = document.getElementById('im-preview');
    if (!preview.programs.length) {
      wrap.innerHTML = `<p class="text-muted" style="font-size:12px;">${t('plandirector.import_empty')}</p>`;
      return;
    }
    wrap.innerHTML = preview.programs.map(prog => `
      <div class="card" style="margin-bottom:8px;padding:10px;">
        <strong style="font-size:13px;">${UI.esc(prog.name)}</strong>
        <ul style="font-size:12px;padding-left:18px;margin:6px 0 0;">
          ${prog.initiatives.map(ini => `
            <li>${UI.esc(ini.title)}
              ${ini.control_targets.length ? ` — ${ini.control_targets.length} ${t('plandirector.control_targets_title').toLowerCase()}` : ''}
              ${ini.target_date ? ` — ${ini.target_date}` : ''}
            </li>`).join('')}
        </ul>
      </div>`).join('') + (preview.skipped_controls.length
        ? `<p class="text-muted" style="font-size:11px;">${t('plandirector.import_skipped')}: ${UI.esc(preview.skipped_controls.join(', '))}</p>` : '');
  }

  // ---------- Wizard nueva iniciativa ----------

  function _openInitiativeWizard() {
    let step = 1;
    const state = { targets: [] };

    function stepHtml() {
      if (step === 1) {
        return `
          <div class="form-grid">
            <div class="span2"><label>${t('common.title')} *</label><input id="wi-title" class="input"></div>
            <div>
              <label>${t('plandirector.program')}</label>
              <select id="wi-program" class="input">
                <option value="">— ${t('common.none')} —</option>
                ${_programs.map(p => `<option value="${p.id}">${UI.esc(p.name)}</option>`).join('')}
              </select>
            </div>
            <div>
              <label>${t('common.priority')}</label>
              <select id="wi-priority" class="input">
                ${['low', 'medium', 'high', 'critical'].map(p => `<option value="${p}" ${p === 'medium' ? 'selected' : ''}>${UI.esc(p)}</option>`).join('')}
              </select>
            </div>
            <div>
              <label>NIST</label>
              <select id="wi-nist" class="input">
                <option value="">—</option>
                ${['govern', 'identify', 'protect', 'detect', 'respond', 'recover'].map(n => `<option value="${n}">${n}</option>`).join('')}
              </select>
            </div>
            <div>
              <label>${t('common.owner')}</label>
              <select id="wi-owner" class="input">
                <option value="">— ${t('common.not_assigned')} —</option>
                ${_users.map(u => `<option value="${u.id}">${UI.esc(u.full_name || u.email)}</option>`).join('')}
              </select>
            </div>
            <div><label>${t('plandirector.start_date')}</label><input type="date" id="wi-start" class="input"></div>
            <div><label>${t('plandirector.target_date')}</label><input type="date" id="wi-target" class="input"></div>
            <div><label>${t('plandirector.budget')}</label><input type="number" id="wi-budget" class="input"></div>
            <div class="span2"><label>${t('common.description')}</label><textarea id="wi-desc" class="input" rows="2"></textarea></div>
            <div class="span2"><label>${t('plandirector.expected_reduction')}</label><textarea id="wi-reduction" class="input" rows="2"></textarea></div>
          </div>`;
      }
      // step 2: controles objetivo (catalogo ISO 27002 completo)
      if (!_impls.length) {
        return `<p class="text-muted" style="font-size:13px;">${t('plandirector.catalog_unavailable')}</p>`;
      }
      return `
        <p class="text-muted" style="font-size:12px;margin-bottom:8px;">${t('plandirector.control_targets_hint')}</p>
        <input type="text" id="wi-ctrl-search" class="input" style="margin-bottom:8px;"
               placeholder="${t('common.search')}..." value="${UI.esc(state.ctrlQuery || '')}">
        <div id="wi-ctrl-selected" style="font-size:12px;color:var(--text-muted);margin-bottom:6px;">
          ${t('plandirector.controls_selected', { n: state.targets.length })}
        </div>
        <div style="max-height:320px;overflow:auto;border:1px solid var(--border);border-radius:6px;">
          <table class="data-table" style="width:100%;">
            <thead><tr><th></th><th>${t('common.code')}</th><th>${t('common.name')}</th><th>${t('plandirector.current_maturity')}</th><th>${t('plandirector.target_maturity')}</th></tr></thead>
            <tbody id="wi-ctrl-rows">${_controlRowsHtml(state)}</tbody>
          </table>
        </div>`;
    }

    function _controlRowsHtml(state) {
      const q = (state.ctrlQuery || '').toLowerCase();
      const rows = _impls.filter(c => !q || `${c.code} ${c.name}`.toLowerCase().includes(q));
      if (!rows.length) return `<tr><td colspan="5" class="text-muted" style="font-size:12px;">${t('common.no_data')}</td></tr>`;
      return rows.map(c => {
        const key = _ctrlKey(c);
        const selected = state.targets.find(x => _ctrlKey(x) === key);
        return `<tr>
          <td><input type="checkbox" data-target-check="${key}" ${selected ? 'checked' : ''}></td>
          <td>${UI.esc(c.code || '')}</td>
          <td>${UI.esc(c.name || '')}${c.implemented ? '' : ` <small class="text-muted">${t('plandirector.not_implemented_yet')}</small>`}</td>
          <td>${c.maturity}/5</td>
          <td><input type="number" min="0" max="5" data-target-value="${key}" class="input" style="width:60px;"
                     value="${selected ? selected.target_maturity : Math.min(5, (c.maturity || 0) + 2)}"></td>
        </tr>`;
      }).join('');
    }

    function wire() {
      if (step !== 2) return;
      const search = document.getElementById('wi-ctrl-search');
      if (search) {
        search.oninput = (e) => {
          state.ctrlQuery = e.target.value.trim();
          // Solo se repintan las filas: el foco del buscador se conserva.
          document.getElementById('wi-ctrl-rows').innerHTML = _controlRowsHtml(state);
          wireRows();
        };
      }
      wireRows();
    }

    function wireRows() {
      const counter = document.getElementById('wi-ctrl-selected');
      const refreshCounter = () => {
        if (counter) counter.textContent = t('plandirector.controls_selected', { n: state.targets.length });
      };
      document.querySelectorAll('[data-target-check]').forEach(cb => {
        cb.onchange = () => {
          const key = cb.dataset.targetCheck;
          if (cb.checked) {
            const valInput = document.querySelector(`[data-target-value="${key}"]`);
            const entry = _ctrlFromKey(key);
            entry.target_maturity = parseInt(valInput.value);
            state.targets.push(entry);
          } else {
            state.targets = state.targets.filter(x => _ctrlKey(x) !== key);
          }
          refreshCounter();
        };
      });
      document.querySelectorAll('[data-target-value]').forEach(inp => {
        inp.onchange = () => {
          const entry = state.targets.find(x => _ctrlKey(x) === inp.dataset.targetValue);
          if (entry) entry.target_maturity = parseInt(inp.value);
        };
      });
    }

    function renderModal() {
      UI.modal(`${t('plandirector.new_initiative')} (${step}/2)`, stepHtml(), {
        width: 'min(900px,95vw)',
        actions: `
          <button class="btn" id="m-cancel">${t('common.cancel')}</button>
          ${step === 2 ? `<button class="btn" id="m-back">${t('common.back')}</button>` : ''}
          <button class="btn btn-primary" id="m-next">${step === 1 ? t('common.next') : t('common.save')}</button>`,
      });
      document.getElementById('m-cancel').onclick = UI.closeModal;
      const backBtn = document.getElementById('m-back');
      if (backBtn) backBtn.onclick = () => { step = 1; renderModal(); };
      document.getElementById('m-next').onclick = async () => {
        if (step === 1) {
          const title = document.getElementById('wi-title').value.trim();
          if (!title) { UI.toast(t('common.required'), 'error'); return; }
          state.title = title;
          state.program_id = document.getElementById('wi-program').value ? parseInt(document.getElementById('wi-program').value) : null;
          state.priority = document.getElementById('wi-priority').value;
          state.nist_function = document.getElementById('wi-nist').value || null;
          state.owner_id = document.getElementById('wi-owner').value ? parseInt(document.getElementById('wi-owner').value) : null;
          state.start_date = document.getElementById('wi-start').value || null;
          state.target_date = document.getElementById('wi-target').value || null;
          state.budget = document.getElementById('wi-budget').value ? parseFloat(document.getElementById('wi-budget').value) : null;
          state.description = document.getElementById('wi-desc').value.trim() || null;
          state.expected_risk_reduction = document.getElementById('wi-reduction').value.trim() || null;
          step = 2;
          renderModal();
          return;
        }
        // step 2 -> guardar
        try {
          const created = await Api.initiatives.create({
            title: state.title, program_id: state.program_id, priority: state.priority,
            nist_function: state.nist_function, owner_id: state.owner_id,
            start_date: state.start_date, target_date: state.target_date,
            budget: state.budget, description: state.description,
            expected_risk_reduction: state.expected_risk_reduction,
          });
          for (const target of state.targets) {
            await Api.initiatives.controlTargets.create(created.id, target);
          }
          UI.toast(t('common.success'), 'success');
          UI.closeModal();
          await _loadAll();
          _section = 'plan';
          _renderBody();
          _openInitiativeDetail(created.id);
        } catch (e) { UI.toast(e.message, 'error'); }
      };
      wire();
    }
    renderModal();
  }

  // ---------- Detalle de iniciativa ----------

  async function _openInitiativeDetail(id) {
    let detail;
    try {
      detail = await Api.initiatives.get(id);
    } catch (e) { UI.toast(e.message, 'error'); return; }
    _renderDetailModal(detail);
  }

  function _renderDetailModal(d) {
    const healthColor = HEALTH_COLOR[d.health] || 'var(--text-muted)';
    UI.modal(`${d.code} — ${d.title}`, `
      ${d.ai_generated ? `<div class="notice" style="margin-bottom:10px;">${t('plandirector.ai_generated_banner')}${d.ai_rationale ? `<details style="margin-top:6px;"><summary style="cursor:pointer;font-size:12px;">${t('common.details')}</summary><p style="font-size:12px;">${UI.esc(d.ai_rationale)}</p></details>` : ''}</div>` : ''}
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
        <span class="badge" style="background:${STATUS_COLOR[d.status] || '#888'};color:#fff;">${_statusLabel(d.status)}</span>
        <span class="badge" style="background:${healthColor};color:#fff;" title="${(d.health_reasons || []).join('; ')}">${d.health}</span>
        ${d.nist_function ? `<span class="badge">${UI.esc(d.nist_function)}</span>` : ''}
        <span class="badge" style="background:${PRIORITY_COLORS[d.priority] || '#888'};color:#fff;">${UI.esc(d.priority)}</span>
        <select id="di-status" class="input" style="width:auto;">
          ${['draft', 'approved', 'in_progress', 'on_hold', 'completed', 'cancelled'].map(s => `<option value="${s}" ${s === d.status ? 'selected' : ''}>${_statusLabel(s)}</option>`).join('')}
        </select>
      </div>
      ${d.description ? `<p style="font-size:13px;">${UI.esc(d.description)}</p>` : ''}
      ${d.expected_risk_reduction ? `<p style="font-size:12px;color:var(--text-muted);"><em>${UI.esc(d.expected_risk_reduction)}</em></p>` : ''}
      ${d.verification ? `
        <div class="card" style="padding:10px;margin:10px 0;background:var(--bg-2);">
          <strong style="font-size:12px;">${t('plandirector.verification_title')}</strong>
          <p style="font-size:12px;margin:4px 0;">${t('plandirector.controls_met', { met: d.verification.controls.met, total: d.verification.controls.total })} · ${t('plandirector.risks_met', { met: d.verification.risks.met, total: d.verification.risks.total })}</p>
          ${(d.verification.gaps || []).length ? `<ul style="font-size:11px;margin:4px 0;padding-left:16px;">${d.verification.gaps.map(g => `<li>${g.type === 'control' ? `${UI.esc(g.code)}: objetivo ${UI.esc(g.target)}, alcanzado ${g.achieved ?? '—'}` : `${UI.esc(g.code)}: proyectado ${UI.esc(g.projected)}, alcanzado ${g.achieved ?? '—'}`}</li>`).join('')}</ul>` : ''}
        </div>` : ''}

      <h4 style="font-size:12px;margin:14px 0 6px;">${t('plandirector.control_targets_title')} (${d.control_targets.length})</h4>
      <table class="data-table" style="width:100%;font-size:12px;">
        <thead><tr><th>${t('common.code')}</th><th>${t('common.name')}</th><th>Baseline → ${t('plandirector.current_maturity')} → ${t('plandirector.target_maturity')}</th><th>${t('treatment.evidence_col')}</th><th></th></tr></thead>
        <tbody>
          ${d.control_targets.map(ct => `
            <tr>
              <td>${UI.esc(ct.control_code || '')}</td>
              <td>${UI.esc(ct.control_name || '')}</td>
              <td>${ct.baseline_maturity ?? '—'} → ${ct.current_maturity ?? '—'} → <strong>${ct.target_maturity}</strong></td>
              <td>${(ct.evidence || []).length
                    ? (ct.evidence || []).map(ev => `<span class="badge" title="${UI.esc(ev.title)}" style="background:${ev.expired ? 'var(--risk-high)' : 'var(--bg-3)'};color:${ev.expired ? '#fff' : 'var(--text)'};margin-right:3px;">${UI.esc(ev.code)}${ev.quality_level ? ` · ${UI.esc(ev.quality_level)}` : ''}</span>`).join('')
                    : `<span style="color:var(--risk-medium);">${t('plandirector.no_evidence')}</span>`}</td>
              <td><button class="btn btn-sm btn-ghost" data-del-target="${ct.id}">${t('common.delete')}</button></td>
            </tr>`).join('')}
        </tbody>
      </table>

      <h4 style="font-size:12px;margin:14px 0 6px;">${t('plandirector.risk_links_title')} (${d.risk_links.length})</h4>
      <table class="data-table" style="width:100%;font-size:12px;">
        <thead><tr><th>${t('common.code')}</th><th>Baseline</th><th>${t('plandirector.projected')}</th><th>${t('plandirector.actual')}</th><th>${t('plandirector.origin')}</th><th></th></tr></thead>
        <tbody>
          ${d.risk_links.map(rl => `
            <tr>
              <td>${UI.esc(rl.risk_code || '')}<br><small class="text-muted">${UI.esc(rl.asset_name || '')} / ${UI.esc(rl.threat_name || '')}</small></td>
              <td>${rl.baseline_residual_level ?? '—'}</td>
              <td>${rl.projected_residual_level ?? '—'}</td>
              <td style="${rl.current_residual_level != null && rl.projected_residual_level != null && rl.current_residual_level <= rl.projected_residual_level ? 'color:var(--risk-low);font-weight:600;' : ''}">${rl.current_residual_level ?? '—'}</td>
              <td><span class="badge">${rl.origin}</span></td>
              <td>${rl.origin !== 'auto' ? `<button class="btn btn-sm btn-ghost" data-unlink-risk="${rl.risk_id}">${t('common.delete')}</button>` : ''}</td>
            </tr>`).join('')}
        </tbody>
      </table>

      <h4 style="font-size:12px;margin:14px 0 6px;">${t('plandirector.objectives_title')} (${d.objectives.length})</h4>
      <div id="di-okrs">${_okrsHtml(d)}</div>
      <button class="btn btn-sm" id="di-new-okr">+ ${t('plandirector.new_objective')}</button>

      <h4 style="font-size:12px;margin:14px 0 6px;">${t('plandirector.tasks_title')} (${d.tasks.length})</h4>
      <ul style="font-size:12px;padding-left:18px;">
        ${d.tasks.map(tk => `<li>${UI.esc(tk.title)} — <span class="badge">${tk.status}</span></li>`).join('') || `<li class="text-muted">${t('common.no_data')}</li>`}
      </ul>
      <button class="btn btn-sm" id="di-new-task">+ ${t('treatment.new_task')}</button>

      <h4 style="font-size:12px;margin:14px 0 6px;">${t('plandirector.log_title')}</h4>
      <div style="max-height:160px;overflow:auto;font-size:12px;">
        ${d.log_entries.length ? d.log_entries.map(le => `
          <div style="padding:6px 0;border-bottom:1px solid var(--border);">
            <span class="badge" style="background:${le.entry_type === 'system' ? 'var(--text-muted)' : le.entry_type === 'ai_summary' ? 'var(--brand-purple)' : 'var(--brand-orange)'};color:#fff;">${le.entry_type}</span>
            ${UI.esc(le.text)}
            <div class="text-muted" style="font-size:10px;">${new Date(le.created_at).toLocaleString()}${le.author_name ? ' · ' + UI.esc(le.author_name) : ''}</div>
          </div>`).join('') : `<p class="text-muted">${t('common.no_data')}</p>`}
      </div>
      <div style="display:flex;gap:6px;margin-top:8px;">
        <select id="di-log-type" class="input" style="width:140px;">
          <option value="achievement">${t('plandirector.log_achievement')}</option>
          <option value="risk">${t('plandirector.log_risk')}</option>
          <option value="next_step">${t('plandirector.log_next_step')}</option>
          <option value="comment">${t('plandirector.log_comment')}</option>
        </select>
        <input type="text" id="di-log-text" class="input" style="flex:1;" placeholder="${t('plandirector.log_placeholder')}">
        <button class="btn btn-sm" id="di-log-add">${t('common.add')}</button>
      </div>
    `, { width: 'min(1100px,95vw)', actions: `<button class="btn" id="m-close">${t('common.close') || t('common.cancel')}</button>` });

    document.getElementById('m-close').onclick = UI.closeModal;
    document.getElementById('di-status').onchange = async (e) => {
      try {
        await Api.initiatives.update(d.id, { status: e.target.value });
        UI.toast(t('common.success'), 'success');
        await _loadAll();
        _openInitiativeDetail(d.id);
      } catch (err) { UI.toast(err.message, 'error'); }
    };
    document.querySelectorAll('[data-del-target]').forEach(btn => {
      btn.onclick = async () => {
        try {
          await Api.initiatives.controlTargets.del(d.id, parseInt(btn.dataset.delTarget));
          await _loadAll();
          _openInitiativeDetail(d.id);
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });
    document.querySelectorAll('[data-unlink-risk]').forEach(btn => {
      btn.onclick = async () => {
        try {
          await Api.initiatives.risks.unlink(d.id, parseInt(btn.dataset.unlinkRisk));
          await _loadAll();
          _openInitiativeDetail(d.id);
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });
    document.getElementById('di-new-okr').onclick = () => _openOkrModal(d);
    document.getElementById('di-new-task').onclick = () => _openTaskForInitiative(d);
    document.getElementById('di-log-add').onclick = async () => {
      const text = document.getElementById('di-log-text').value.trim();
      if (!text) return;
      try {
        await Api.initiatives.log.add(d.id, { entry_type: document.getElementById('di-log-type').value, text });
        _openInitiativeDetail(d.id);
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  function _okrsHtml(d) {
    if (!d.objectives.length) return `<p class="text-muted" style="font-size:12px;">${t('common.no_data')}</p>`;
    return `<ul style="font-size:12px;padding-left:18px;">
      ${d.objectives.map(o => `<li>${UI.esc(o.definition)} — <span class="badge">${o.status}</span> — ${o.progress}%</li>`).join('')}
    </ul>`;
  }

  function _openOkrModal(d) {
    UI.modal(t('plandirector.new_objective'), `
      <div class="form-grid">
        <div class="span2"><label>${t('plandirector.okr_definition')} *</label><textarea id="okr-def" class="input" rows="2"></textarea></div>
        <div><label>${t('plandirector.confidence')}</label>
          <select id="okr-conf" class="input">
            <option value="high">${t('common.high')}</option>
            <option value="medium" selected>${t('common.medium')}</option>
            <option value="low">${t('common.low')}</option>
          </select>
        </div>
        <div><label>${t('plandirector.target_date')}</label><input type="date" id="okr-date" class="input"></div>
        <div class="span2"><label>${t('treatment.th_progress')}</label><input type="range" min="0" max="100" id="okr-progress" class="input" value="0"></div>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const definition = document.getElementById('okr-def').value.trim();
      if (!definition) { UI.toast(t('common.required'), 'error'); return; }
      try {
        await Api.initiatives.objectives.create(d.id, {
          definition, confidence: document.getElementById('okr-conf').value,
          target_date: document.getElementById('okr-date').value || null,
          progress: parseInt(document.getElementById('okr-progress').value),
        });
        UI.toast(t('common.success'), 'success');
        await _loadAll();
        _openInitiativeDetail(d.id);
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  function _openTaskForInitiative(d) {
    UI.modal(t('treatment.new_task'), `
      <div class="form-grid">
        <div class="span2"><label>${t('tasks.task_name')} *</label><input id="ti-title" class="input"></div>
        <div>
          <label>${t('tasks.related_risk')} (${t('common.optional')})</label>
          <select id="ti-risk" class="input">
            <option value="">— ${t('common.none')} —</option>
            ${d.risk_links.map(rl => `<option value="${rl.risk_id}">${UI.esc(rl.risk_code)}</option>`).join('')}
          </select>
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const title = document.getElementById('ti-title').value.trim();
      if (!title) { UI.toast(t('common.required'), 'error'); return; }
      try {
        const riskVal = document.getElementById('ti-risk').value;
        await Api.tasks.create({ title, initiative_id: d.id, risk_id: riskVal ? parseInt(riskVal) : null });
        UI.toast(t('common.success'), 'success');
        await _loadAll();
        _openInitiativeDetail(d.id);
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  return { render };
})();
