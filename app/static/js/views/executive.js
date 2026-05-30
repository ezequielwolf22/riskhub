/* Dashboard ejecutivo — KPIs, top riesgos, trend, compliance, informe PDF. */
const ViewExecutive = (() => {

  function _color(val, thresholds) {
    // thresholds: {good: X, warn: Y} — mayor = peor (riesgos)
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

  function _kpiCard(label, value, unit, color) {
    return `
      <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;
                  padding:18px 20px;text-align:center;min-width:120px;flex:1;">
        <div style="font-size:28px;font-weight:700;color:${color};">${value}${unit || ''}</div>
        <div style="font-size:11px;color:#9d9d9d;text-transform:uppercase;margin-top:4px;
                    letter-spacing:.5px;">${label}</div>
      </div>`;
  }

  function _progressBar(pct, color) {
    return `
      <div style="background:#eee;border-radius:4px;height:8px;width:100%;overflow:hidden;">
        <div style="width:${pct}%;background:${color};height:100%;border-radius:4px;
                    transition:width .4s;"></div>
      </div>`;
  }

  function _trendBars(trend) {
    if (!trend || !trend.length) return '<p style="color:#9d9d9d;font-size:13px;">Sin datos de trend.</p>';
    const maxCreated = Math.max(...trend.map(d => d.created), 1);
    return `
      <div style="display:flex;gap:3px;align-items:flex-end;height:80px;overflow-x:auto;">
        ${trend.slice(-30).map(d => `
          <div title="${d.date}: ${d.created} creados, ${d.high} altos" style="flex:1;min-width:8px;display:flex;flex-direction:column;gap:2px;align-items:center;">
            <div style="width:100%;background:${d.high > 0 ? 'var(--brand-orange)' : 'var(--brand-purple)'};
                        height:${Math.max(4, Math.round(d.created / maxCreated * 70))}px;
                        border-radius:2px 2px 0 0;opacity:.85;"></div>
          </div>`).join('')}
      </div>
      <div style="display:flex;gap:16px;margin-top:8px;font-size:11px;color:#9d9d9d;">
        <span><span style="display:inline-block;width:10px;height:10px;background:var(--brand-purple);border-radius:2px;margin-right:4px;"></span>Nuevos</span>
        <span><span style="display:inline-block;width:10px;height:10px;background:var(--brand-orange);border-radius:2px;margin-right:4px;"></span>Altos</span>
      </div>`;
  }

  function _renderKpis(kpis) {
    const mitigated = kpis.mitigated_pct || 0;
    const controls = kpis.controls_pct || 0;
    return `
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px;">
        ${_kpiCard('Riesgos totales', kpis.total_risks, '', 'var(--brand-purple)')}
        ${_kpiCard('Altos/Críticos', kpis.high_risks, '', _color(kpis.high_risks, {good:2, warn:5}))}
        ${_kpiCard('Sobre apetito', kpis.risks_over_appetite, '', _color(kpis.risks_over_appetite, {good:2, warn:5}))}
        ${_kpiCard('Mitigados', mitigated, '%', _pctColor(mitigated))}
        ${_kpiCard('Controles impl.', controls, '%', _pctColor(controls))}
        ${_kpiCard('Tareas vencidas', kpis.overdue_tasks, '', _color(kpis.overdue_tasks, {good:0, warn:3}))}
        ${_kpiCard('Incidentes 30d', kpis.incidents_30d, '', _color(kpis.incidents_30d, {good:0, warn:3}))}
        ${_kpiCard('Edad media tto.', kpis.mat_days, 'd', _color(kpis.mat_days, {good:15, warn:30}))}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:8px;">
        <div>
          <div style="font-size:12px;color:#666;margin-bottom:4px;">
            Riesgos mitigados ${mitigated}%
          </div>
          ${_progressBar(mitigated, _pctColor(mitigated))}
        </div>
        <div>
          <div style="font-size:12px;color:#666;margin-bottom:4px;">
            Controles implementados ${controls}%
          </div>
          ${_progressBar(controls, _pctColor(controls))}
        </div>
      </div>`;
  }

  function _renderTopRisks(risks) {
    if (!risks || !risks.length) return '<p style="color:#9d9d9d;font-size:13px;">No hay riesgos activos.</p>';
    const _levelBg = l => l >= 6 ? '#FEE2E2' : l >= 4 ? '#FEF0E3' : '#E8F5E9';
    const _levelColor = l => l >= 6 ? '#a83232' : l >= 4 ? '#c25a1f' : '#2e7d32';
    return `
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
          <tr style="background:var(--brand-purple);color:#fff;">
            <th style="padding:8px 10px;text-align:left;font-weight:600;">Código</th>
            <th style="padding:8px 10px;text-align:left;font-weight:600;">Descripción</th>
            <th style="padding:8px 10px;text-align:left;font-weight:600;">Activo</th>
            <th style="padding:8px 10px;text-align:center;font-weight:600;">Nivel</th>
            <th style="padding:8px 10px;text-align:left;font-weight:600;">Estado</th>
          </tr>
        </thead>
        <tbody>
          ${risks.map((r, i) => `
            <tr style="background:${i % 2 === 0 ? '#fff' : '#f9f9f9'};">
              <td style="padding:8px 10px;font-weight:600;color:var(--brand-purple);">${UI.esc(r.code)}</td>
              <td style="padding:8px 10px;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
                  title="${UI.esc(r.description)}">${UI.esc(r.description)}</td>
              <td style="padding:8px 10px;color:#666;">${UI.esc(r.asset_name || '—')}</td>
              <td style="padding:8px 10px;text-align:center;">
                <span style="background:${_levelBg(r.residual_level)};color:${_levelColor(r.residual_level)};
                             padding:2px 8px;border-radius:10px;font-weight:700;font-size:12px;">
                  ${r.residual_level}
                </span>
              </td>
              <td style="padding:8px 10px;font-size:11px;color:#666;">${UI.esc(r.status)}</td>
            </tr>`).join('')}
        </tbody>
      </table>`;
  }

  function _renderCompliance(comp) {
    if (!comp || !comp.frameworks || !comp.frameworks.length) {
      return '<p style="color:#9d9d9d;font-size:13px;">No hay frameworks configurados. Ve a <strong>Cumplimiento</strong> para activarlos.</p>';
    }
    return comp.frameworks.map(fw => `
      <div style="margin-bottom:14px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
          <span style="font-size:13px;font-weight:600;">${UI.esc(fw.framework_name)}</span>
          <span style="font-size:13px;font-weight:700;color:${_pctColor(fw.overall_pct)};">
            ${fw.overall_pct}%
            ${fw.is_audit_ready ? '<span style="font-size:11px;color:var(--risk-low);margin-left:6px;">✓ Listo auditoría</span>' : ''}
          </span>
        </div>
        ${_progressBar(fw.overall_pct, _pctColor(fw.overall_pct))}
        ${fw.gaps && fw.gaps.length ? `
          <div style="font-size:11px;color:#9d9d9d;margin-top:4px;">
            ${fw.gaps.length} gap${fw.gaps.length > 1 ? 's' : ''} pendiente${fw.gaps.length > 1 ? 's' : ''}
          </div>` : ''}
      </div>`).join('');
  }

  async function render(el) {
    el.innerHTML = `
      <div style="max-width:1100px;margin:0 auto;padding:24px 0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;flex-wrap:wrap;gap:12px;">
          <div>
            <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0;">
              Dashboard Ejecutivo
            </h1>
            <p style="color:#9d9d9d;font-size:13px;margin:4px 0 0;">
              Visión global de riesgos, controles y cumplimiento
            </p>
          </div>
          <div style="display:flex;gap:8px;">
            <button onclick="ViewExecutive._refresh()" class="btn-outline" style="font-size:13px;padding:6px 14px;">
              Actualizar
            </button>
            <a href="/api/executive/board-report/pdf" target="_blank"
               style="background:var(--brand-orange);color:#fff;border:none;border-radius:6px;
                      padding:6px 14px;font-size:13px;font-weight:600;text-decoration:none;cursor:pointer;">
              Descargar informe PDF
            </a>
          </div>
        </div>
        <div id="exec-content"><div style="text-align:center;padding:60px;color:#9d9d9d;">Cargando...</div></div>
      </div>`;

    await _load();
  }

  async function _load() {
    const el = document.getElementById('exec-content');
    try {
      const [kpis, topRisks, trend, compliance] = await Promise.all([
        Api.executive.kpis(),
        Api.executive.topRisks(10),
        Api.executive.riskTrend(30),
        Api.executive.boardReport().then(r => r.compliance).catch(() => null),
      ]);

      el.innerHTML = `
        <!-- KPIs -->
        <section style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:20px;margin-bottom:16px;">
          <h2 style="font-size:15px;font-weight:700;color:var(--brand-purple);margin:0 0 16px;
                     padding-bottom:8px;border-bottom:2px solid var(--brand-orange);">
            Indicadores Clave
          </h2>
          ${_renderKpis(kpis)}
        </section>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
          <!-- Trend -->
          <section style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:20px;">
            <h2 style="font-size:15px;font-weight:700;color:var(--brand-purple);margin:0 0 14px;
                       padding-bottom:8px;border-bottom:2px solid var(--brand-orange);">
              Trend de Riesgos (30 días)
            </h2>
            ${_trendBars(trend)}
          </section>

          <!-- Compliance -->
          <section style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:20px;">
            <h2 style="font-size:15px;font-weight:700;color:var(--brand-purple);margin:0 0 14px;
                       padding-bottom:8px;border-bottom:2px solid var(--brand-orange);">
              Cumplimiento Normativo
            </h2>
            ${_renderCompliance(compliance)}
          </section>
        </div>

        <!-- Top riesgos -->
        <section style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:20px;">
          <h2 style="font-size:15px;font-weight:700;color:var(--brand-purple);margin:0 0 14px;
                     padding-bottom:8px;border-bottom:2px solid var(--brand-orange);">
            Top Riesgos Activos
          </h2>
          ${_renderTopRisks(topRisks)}
        </section>`;
    } catch (e) {
      el.innerHTML = `<div style="color:var(--risk-critical);padding:24px;">Error cargando dashboard: ${UI.esc(e.message)}</div>`;
    }
  }

  function _refresh() { _load(); }

  return { render, _refresh };
})();
