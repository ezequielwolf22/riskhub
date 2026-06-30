/* Dashboard ejecutivo — KPIs, top riesgos, trend, compliance, informe PDF. Editable por widgets. */
const ViewExecutive = (() => {

  // ── Widget catalog ────────────────────────────────────────────────────────

  function _getCatalog() {
    return {
      exec_kpis:       { label: t('executive.widget_kpis'),       group: 'executive' },
      exec_trend:      { label: t('executive.widget_trend'),      group: 'executive' },
      exec_compliance: { label: t('executive.widget_compliance'), group: 'executive' },
      exec_top_risks:  { label: t('executive.widget_top_risks'),  group: 'executive' },
      exec_dist:       { label: t('executive.widget_dist'),       group: 'risks'     },
      exec_incidents:  { label: t('executive.widget_incidents'),  group: 'incidents' },
      exec_tasks:      { label: t('executive.widget_tasks'),      group: 'tasks'     },
      exec_bcp:        { label: t('executive.widget_bcp'),        group: 'continuity'},
      exec_tprm:       { label: t('executive.widget_tprm'),       group: 'suppliers' },
    };
  }

  const EXEC_DEFAULT = ['exec_kpis', 'exec_trend', 'exec_compliance', 'exec_top_risks'];

  function _getLayout() {
    try {
      const s = localStorage.getItem('riskhub_exec_layout');
      if (s) {
        const p = JSON.parse(s);
        if (Array.isArray(p) && p.length > 0) return p;
      }
    } catch (_) {}
    return EXEC_DEFAULT.slice();
  }

  function _saveLayout(layout) {
    localStorage.setItem('riskhub_exec_layout', JSON.stringify(layout));
  }

  // ── Color helpers ─────────────────────────────────────────────────────────

  function _color(val, thresholds) {
    if (val <= thresholds.good)  return 'var(--risk-low)';
    if (val <= thresholds.warn)  return 'var(--risk-medium)';
    return 'var(--risk-high)';
  }

  function _pctColor(pct) {
    if (pct >= 75) return 'var(--risk-low)';
    if (pct >= 50) return 'var(--risk-medium)';
    if (pct >= 25) return 'var(--risk-high)';
    return 'var(--risk-critical)';
  }

  // ── Widget renderers ──────────────────────────────────────────────────────

  function _kpiCard(label, value, unit, color) {
    return `
      <div style="background:var(--bg-card);border-radius:8px;border:1px solid var(--border);
                  padding:18px 20px;text-align:center;min-width:120px;flex:1;">
        <div style="font-size:28px;font-weight:700;color:${color};">${value}${unit || ''}</div>
        <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;margin-top:4px;
                    letter-spacing:.5px;">${label}</div>
      </div>`;
  }

  function _progressBar(pct, color) {
    return `
      <div style="background:var(--bg-3);border-radius:4px;height:8px;width:100%;overflow:hidden;">
        <div style="width:${pct}%;background:${color};height:100%;border-radius:4px;
                    transition:width .4s;"></div>
      </div>`;
  }

  function _trendBars(trend) {
    if (!trend || !trend.length) return `<p style="color:var(--text-muted);font-size:13px;">${t('executive.no_trend')}</p>`;
    const maxCreated = Math.max(...trend.map(d => d.created), 1);
    return `
      <div style="display:flex;gap:3px;height:90px;">
        ${trend.slice(-30).map(d => `
          <div title="${d.date}: ${d.created} ${t('executive.trend_new')}, ${d.high} ${t('executive.trend_high')}"
               style="flex:1;min-width:6px;display:flex;flex-direction:column;justify-content:flex-end;">
            <div style="width:100%;background:${d.high > 0 ? 'var(--brand-orange)' : 'var(--brand-purple)'};
                        height:${Math.max(4, Math.round(d.created / maxCreated * 82))}px;
                        border-radius:2px 2px 0 0;opacity:.85;"></div>
          </div>`).join('')}
      </div>
      <div style="display:flex;gap:16px;margin-top:8px;font-size:11px;color:var(--text-muted);">
        <span><span style="display:inline-block;width:10px;height:10px;background:var(--brand-purple);border-radius:2px;margin-right:4px;"></span>${t('executive.trend_new')}</span>
        <span><span style="display:inline-block;width:10px;height:10px;background:var(--brand-orange);border-radius:2px;margin-right:4px;"></span>${t('executive.trend_high')}</span>
      </div>`;
  }

  function _renderKpis(kpis) {
    const mitigated = kpis.mitigated_pct || 0;
    const controls  = kpis.controls_pct  || 0;
    return `
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px;">
        ${_kpiCard(t('executive.kpi_total'),     kpis.total_risks,        '', 'var(--brand-purple)')}
        ${_kpiCard(t('executive.kpi_high'),       kpis.high_risks,         '', _color(kpis.high_risks, {good:2, warn:5}))}
        ${_kpiCard(t('executive.kpi_appetite'),   kpis.risks_over_appetite,'', _color(kpis.risks_over_appetite, {good:2, warn:5}))}
        ${_kpiCard(t('executive.kpi_mitigated'),  mitigated,              '%', _pctColor(mitigated))}
        ${_kpiCard(t('executive.kpi_controls'),   controls,               '%', _pctColor(controls))}
        ${_kpiCard(t('executive.kpi_overdue'),    kpis.overdue_tasks,      '', _color(kpis.overdue_tasks, {good:0, warn:3}))}
        ${_kpiCard(t('executive.kpi_incidents'),  kpis.incidents_30d,      '', _color(kpis.incidents_30d, {good:0, warn:3}))}
        ${_kpiCard(t('executive.kpi_avg_age'),    kpis.mat_days,          'd', _color(kpis.mat_days, {good:15, warn:30}))}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:8px;">
        <div>
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">
            ${t('executive.mitigated_pct', {pct: mitigated})}
          </div>
          ${_progressBar(mitigated, _pctColor(mitigated))}
        </div>
        <div>
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">
            ${t('executive.controls_pct', {pct: controls})}
          </div>
          ${_progressBar(controls, _pctColor(controls))}
        </div>
      </div>`;
  }

  function _renderTopRisks(risks) {
    if (!risks || !risks.length) return `<p style="color:var(--text-muted);font-size:13px;">${t('executive.no_risks')}</p>`;
    const _levelColor = l => {
      if (!window.RiskLevels) return l >= 6 ? '#a83232' : l >= 4 ? '#c25a1f' : '#2e7d32';
      return RiskLevels.colorFor(l);
    };
    const _bgMap = {
      'var(--risk-low)': '#E8F5E9', 'var(--risk-medium)': '#FEF0E3',
      'var(--risk-high)': '#FEE2E2', 'var(--risk-critical)': '#FDECEA',
      'var(--brand-purple)': '#F3E8FF',
    };
    const _levelBg = l => {
      if (!window.RiskLevels) return l >= 6 ? '#FEE2E2' : l >= 4 ? '#FEF0E3' : '#E8F5E9';
      const c = RiskLevels.colorFor(l);
      return _bgMap[c] || c + '33';
    };
    return `
      <div class="table-wrap">
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
          <tr style="background:var(--brand-purple);color:#fff;">
            <th style="padding:8px 10px;text-align:left;font-weight:600;">${t('executive.col_code')}</th>
            <th style="padding:8px 10px;text-align:left;font-weight:600;">${t('executive.col_description')}</th>
            <th style="padding:8px 10px;text-align:left;font-weight:600;">${t('executive.col_asset')}</th>
            <th style="padding:8px 10px;text-align:center;font-weight:600;">${t('executive.col_level')}</th>
            <th style="padding:8px 10px;text-align:left;font-weight:600;">${t('executive.col_status')}</th>
          </tr>
        </thead>
        <tbody>
          ${risks.map((r, i) => `
            <tr style="background:${i % 2 === 0 ? 'var(--bg-card)' : 'var(--bg-2)'};cursor:pointer;"
                onclick="location.hash='#/risks?id=${r.id}'">
              <td style="padding:8px 10px;font-weight:600;color:var(--brand-purple);">${UI.esc(r.code)}</td>
              <td style="padding:8px 10px;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
                  title="${UI.esc(r.description)}">${UI.esc(r.description)}</td>
              <td style="padding:8px 10px;color:var(--text-muted);">${UI.esc(r.asset_name || '—')}</td>
              <td style="padding:8px 10px;text-align:center;">
                <span style="background:${_levelBg(r.residual_level)};color:${_levelColor(r.residual_level)};
                             padding:2px 8px;border-radius:10px;font-weight:700;font-size:12px;">
                  ${r.residual_level}
                </span>
              </td>
              <td style="padding:8px 10px;font-size:11px;color:var(--text-muted);">${UI.esc(r.status)}</td>
            </tr>`).join('')}
        </tbody>
      </table>
      </div>`;
  }

  function _renderCompliance(comp) {
    if (!comp || !comp.frameworks || !comp.frameworks.length) {
      return `<p style="color:var(--text-muted);font-size:13px;">${t('executive.no_frameworks')} ${t('executive.activate_compliance')}.</p>`;
    }
    return comp.frameworks.map(fw => `
      <div style="margin-bottom:14px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <span style="font-size:13px;font-weight:600;">${UI.esc(fw.framework_name)}</span>
          <span style="font-size:13px;font-weight:700;color:${_pctColor(fw.overall_pct)};">
            ${fw.overall_pct}%
            ${fw.is_audit_ready ? `<span style="font-size:11px;color:var(--risk-low);margin-left:6px;">✓ ${t('executive.audit_ready')}</span>` : ''}
          </span>
        </div>
        ${_progressBar(fw.overall_pct, _pctColor(fw.overall_pct))}
        ${fw.gaps && fw.gaps.length ? `
          <div style="font-size:11px;color:var(--text-muted);margin-top:4px;">
            ${t('executive.gaps_pending', {n: fw.gaps.length, s: fw.gaps.length > 1 ? 's' : ''})}
          </div>` : ''}
      </div>`).join('');
  }

  function _renderDist(risks) {
    if (!risks) return `<p style="color:var(--text-muted);font-size:13px;">${t('executive.no_risks')}</p>`;
    const _bl = window.RiskLevels ? RiskLevels.all().slice().reverse() : [
      { code:'high',   label: t('risks.level.high'),   color:'var(--risk-high)',   min_level:6, max_level:8 },
      { code:'medium', label: t('risks.level.medium'), color:'var(--risk-medium)', min_level:3, max_level:5 },
      { code:'low',    label: t('risks.level.low'),    color:'var(--risk-low)',    min_level:0, max_level:2 },
    ];
    const bar = (pct, color) => `
      <div style="height:5px;border-radius:3px;background:var(--bg-3);overflow:hidden;">
        <div style="height:100%;width:${pct}%;background:${color};border-radius:3px;transition:width .4s;"></div>
      </div>`;
    return `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;">
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px;">${t('dashboard.dist_by_level')}</div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${_bl.map(b => `
              <div>
                <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
                  <span>${b.label} (${b.min_level}–${b.max_level})</span>
                  <span style="font-weight:700;color:${b.color};">${risks.by_band?.[b.code] || 0}</span>
                </div>
                ${bar(risks.total_risks ? Math.round((risks.by_band?.[b.code]||0)/risks.total_risks*100) : 0, b.color)}
              </div>`).join('')}
          </div>
        </div>
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px;">${t('dashboard.dist_by_status')}</div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${Object.entries(risks.by_status || {}).filter(([,v]) => v > 0).map(([k, v]) => `
              <div>
                <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
                  <span>${UI.statusLabel(k)}</span>
                  <span style="font-weight:600;">${v}</span>
                </div>
                ${bar(risks.total_risks ? Math.round(v/risks.total_risks*100) : 0, 'var(--brand-purple)')}
              </div>`).join('') || `<p style="font-size:13px;color:var(--text-muted);margin:0;">${t('common.no_results')}</p>`}
          </div>
        </div>
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px;">${t('dashboard.dist_by_treatment')}</div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${Object.entries(risks.by_treatment || {}).filter(([,v]) => v > 0).map(([k, v]) => `
              <div>
                <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
                  <span>${UI.treatmentLabel(k)}</span>
                  <span style="font-weight:600;">${v}</span>
                </div>
                ${bar(risks.total_risks ? Math.round(v/risks.total_risks*100) : 0, 'var(--brand-orange)')}
              </div>`).join('') || `<p style="font-size:13px;color:var(--text-muted);margin:0;">${t('dashboard.no_treatment_data')}</p>`}
          </div>
        </div>
      </div>`;
  }

  function _renderIncidents(incidents) {
    if (!incidents) return `<p style="color:var(--text-muted);font-size:13px;">${t('common.no_results')}</p>`;
    const line = (label, val, color, href) => `
      <a href="${href || '#/incidents'}" style="text-decoration:none;color:inherit;display:flex;justify-content:space-between;align-items:center;font-size:13px;padding:7px 0;border-bottom:1px solid var(--border);">
        <span style="color:var(--text-muted);">${label}</span>
        <span style="font-weight:700;color:${color};">${val ?? '—'}</span>
      </a>`;
    return `
      <div>
        ${line(t('dashboard.module_open'),        incidents.open,                         incidents.open > 0 ? 'var(--risk-medium)' : 'var(--risk-low)',   '#/incidents?status=open')}
        ${line(t('dashboard.module_p1p2'),         incidents.p1_p2_open,                   incidents.p1_p2_open > 0 ? 'var(--risk-high)' : 'var(--risk-low)', '#/incidents?severity=p1')}
        ${line(t('dashboard.module_nis2_pending'), incidents.nis2_pending_notification,    incidents.nis2_pending_notification > 0 ? 'var(--risk-critical)' : 'var(--risk-low)', '#/incidents')}
        ${line(t('dashboard.module_history'),      incidents.total,                        'var(--text-muted)', '#/incidents')}
      </div>`;
  }

  function _renderTasks(tasks) {
    if (!tasks) return `<p style="color:var(--text-muted);font-size:13px;">${t('common.no_results')}</p>`;
    const line = (label, val, color, href) => `
      <a href="${href || '#/tasks'}" style="text-decoration:none;color:inherit;display:flex;justify-content:space-between;align-items:center;font-size:13px;padding:7px 0;border-bottom:1px solid var(--border);">
        <span style="color:var(--text-muted);">${label}</span>
        <span style="font-weight:700;color:${color};">${val ?? '—'}</span>
      </a>`;
    return `
      <div>
        ${line(t('dashboard.overdue'),          tasks.overdue,                    tasks.overdue > 0 ? 'var(--risk-high)' : 'var(--risk-low)',   '#/tasks?overdue=1')}
        ${line(t('dashboard.module_in_progress'),tasks.by_status?.in_progress||0, 'var(--brand-purple)', '#/tasks?status=in_progress')}
        ${line(t('dashboard.module_pending'),    tasks.by_status?.pending||0,      'var(--text-muted)',   '#/tasks?status=pending')}
        ${line(t('dashboard.module_completed'),  tasks.by_status?.done||0,         'var(--risk-low)',     '#/tasks?status=done')}
      </div>`;
  }

  // ── Section wrapper ───────────────────────────────────────────────────────

  function _section(title, content, link) {
    return `
      <section style="background:var(--bg-card);border-radius:8px;border:1px solid var(--border);padding:20px;margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin:0 0 16px;padding-bottom:8px;border-bottom:2px solid var(--brand-orange);">
          <h2 style="font-size:15px;font-weight:700;color:var(--brand-purple);margin:0;">${title}</h2>
          ${link ? `<a href="${link}" style="font-size:11px;color:var(--brand-purple);">${t('dashboard.module_view_all')} →</a>` : ''}
        </div>
        ${content}
      </section>`;
  }

  // ── Edit panel ────────────────────────────────────────────────────────────

  function _openEditor() {
    const layout  = _getLayout();
    const CATALOG = _getCatalog();
    const groupOrder = ['executive','risks','incidents','tasks','continuity','suppliers'];
    const groupLabels = {
      executive:  t('executive.group_executive'),
      risks:      t('dashboard.mod_group_risks'),
      incidents:  t('dashboard.mod_group_incidents'),
      tasks:      t('dashboard.mod_group_tasks'),
      continuity: t('dashboard.mod_group_continuity'),
      suppliers:  t('dashboard.mod_group_suppliers'),
    };
    const groups = {};
    for (const [id, w] of Object.entries(CATALOG)) {
      if (!groups[w.group]) groups[w.group] = [];
      groups[w.group].push({ id, ...w });
    }
    const rows = groupOrder.filter(g => groups[g]).map(grp => `
      <div style="margin-bottom:14px;">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted);margin-bottom:6px;">${UI.esc(groupLabels[grp] || grp)}</div>
        ${groups[grp].map(w => {
          const on = layout.includes(w.id);
          return `<label style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--border);cursor:pointer;">
            <input type="checkbox" data-exec-wid="${w.id}" ${on ? 'checked' : ''} style="accent-color:var(--brand-purple);width:16px;height:16px;">
            <span style="font-size:13px;">${w.label}</span>
          </label>`;
        }).join('')}
      </div>`).join('');

    UI.modal(
      t('executive.customize_title'),
      `<div style="padding:4px 0;">${rows}</div>`,
      {
        width: '440px',
        actions: `
          <button class="btn btn-primary" id="exec-edit-save">${UI.esc(t('common.save'))}</button>
          <button class="btn btn-outline" id="exec-edit-reset">${UI.esc(t('common.reset'))}</button>
          <button class="btn" onclick="UI.closeModal()">${UI.esc(t('common.cancel'))}</button>`,
      }
    );
    document.getElementById('exec-edit-save').onclick = () => {
      const newLayout = Object.keys(CATALOG).filter(id => {
        const el = document.querySelector(`[data-exec-wid="${id}"]`);
        return el && el.checked;
      });
      _saveLayout(newLayout.length ? newLayout : EXEC_DEFAULT.slice());
      UI.closeModal();
      _load();
    };
    document.getElementById('exec-edit-reset').onclick = () => {
      _saveLayout(EXEC_DEFAULT.slice());
      UI.closeModal();
      _load();
    };
  }

  // ── Main render ───────────────────────────────────────────────────────────

  async function render(el) {
    el.innerHTML = `
      <div style="max-width:1100px;margin:0 auto;padding:24px 0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;flex-wrap:wrap;gap:12px;">
          <div>
            <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0;">
              ${t('executive.dashboard_title')}
            </h1>
            <p style="color:var(--text-muted);font-size:13px;margin:4px 0 0;">
              ${t('executive.dashboard_subtitle')}
            </p>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button onclick="ViewExecutive._openEditor()" class="btn btn-outline" style="font-size:13px;padding:6px 14px;">
              ${t('executive.customize_btn')}
            </button>
            <button onclick="ViewExecutive._refresh()" class="btn btn-outline" style="font-size:13px;padding:6px 14px;">
              ${t('executive.refresh')}
            </button>
            <a href="/api/executive/board-report/pdf" target="_blank"
               style="background:var(--brand-orange);color:#fff;border:none;border-radius:6px;
                      padding:6px 14px;font-size:13px;font-weight:600;text-decoration:none;cursor:pointer;">
              ${t('executive.download_pdf')}
            </a>
          </div>
        </div>
        <div id="exec-content"><div style="text-align:center;padding:60px;color:var(--text-muted);">${t('executive.loading')}</div></div>
      </div>`;

    await _load();
  }

  async function _load() {
    const el = document.getElementById('exec-content');
    if (!el) return;
    el.innerHTML = `<div style="text-align:center;padding:40px;color:var(--text-muted);">${t('executive.loading')}</div>`;
    try {
      const results = await Promise.allSettled([
        Api.executive.kpis(),
        Api.executive.topRisks(10),
        Api.executive.riskTrend(30),
        Api.executive.boardReport().catch(() => null),
        Api.incidents.summary().catch(() => null),
        Api.tasks.summary().catch(() => null),
        Api.get('/api/bcp/dashboard').catch(() => null),
        Api.tprm.summary().catch(() => null),
        Api.risks.summary().catch(() => null),
      ]);

      const kpis      = results[0].status === 'fulfilled' ? results[0].value : null;
      const topRisks  = results[1].status === 'fulfilled' ? results[1].value : [];
      const trend     = results[2].status === 'fulfilled' ? results[2].value : [];
      const board     = results[3].status === 'fulfilled' ? results[3].value : null;
      const incidents = results[4].status === 'fulfilled' ? results[4].value : null;
      const tasks     = results[5].status === 'fulfilled' ? results[5].value : null;
      const bcpData   = results[6].status === 'fulfilled' ? results[6].value : null;
      const tprmData  = results[7].status === 'fulfilled' ? results[7].value : null;
      const risks     = results[8].status === 'fulfilled' ? results[8].value : null;
      const compliance = board?.compliance || null;

      if (!kpis) throw new Error(t('executive.error_loading'));

      const layout = _getLayout();
      const parts  = [];

      for (const wid of layout) {
        switch (wid) {
          case 'exec_kpis':
            parts.push(_section(t('executive.kpis_section'), _renderKpis(kpis)));
            break;
          case 'exec_trend':
            parts.push(_section(t('executive.trend_section'), _trendBars(trend)));
            break;
          case 'exec_compliance':
            parts.push(_section(t('executive.compliance_section'), _renderCompliance(compliance), '#/compliance'));
            break;
          case 'exec_top_risks':
            parts.push(_section(t('executive.top_risks_section'), _renderTopRisks(topRisks), '#/risks'));
            break;
          case 'exec_dist':
            parts.push(_section(t('executive.widget_dist'), _renderDist(risks), '#/heatmap'));
            break;
          case 'exec_incidents':
            parts.push(_section(t('executive.widget_incidents'), _renderIncidents(incidents), '#/incidents'));
            break;
          case 'exec_tasks':
            parts.push(_section(t('executive.widget_tasks'), _renderTasks(tasks), '#/tasks'));
            break;
          case 'exec_bcp':
            if (typeof ViewDashboard !== 'undefined') {
              const html = ViewDashboard._bcpPanelHtml(bcpData);
              if (html) parts.push(html);
            }
            break;
          case 'exec_tprm':
            if (typeof ViewDashboard !== 'undefined') {
              const html = ViewDashboard._tprmPanelHtml(tprmData, risks);
              if (html) parts.push(html);
            }
            break;
        }
      }

      el.innerHTML = parts.join('') ||
        `<p style="color:var(--text-muted);padding:40px;text-align:center;">${t('executive.no_widgets')}</p>`;
    } catch (e) {
      el.innerHTML = `<div style="color:var(--risk-critical);padding:24px;">${t('executive.error_loading')} ${UI.esc(e.message)}</div>`;
    }
  }

  function _refresh() { _load(); }

  return { render, _refresh, _openEditor };
})();
