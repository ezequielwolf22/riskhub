/* Vista de análisis predictivo: trend, maturity path, activos críticos, threat forecast. */
const ViewPredictive = (() => {

  function _signalBadge(signal) {
    const m = { 'Alta': ['#FEE2E2','#a83232'], 'Media': ['#FEF0E3','#c25a1f'], 'Baja': ['#E8F5E9','#2e7d32'] };
    const [bg, col] = m[signal] || ['#f0f0f0','#666'];
    return `<span style="background:${bg};color:${col};padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">${signal}</span>`;
  }

  function _trendIcon(direction) {
    if (direction === 'increasing') return '<span style="color:var(--risk-critical);font-size:18px;">↑</span>';
    if (direction === 'decreasing') return '<span style="color:var(--risk-low);font-size:18px;">↓</span>';
    return '<span style="color:#9d9d9d;font-size:18px;">→</span>';
  }

  function _progressBar(pct, color) {
    return `<div style="background:#eee;border-radius:4px;height:8px;width:100%;overflow:hidden;">
      <div style="width:${Math.min(100,pct)}%;background:${color};height:100%;border-radius:4px;transition:width .4s;"></div>
    </div>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div style="max-width:1100px;margin:0 auto;padding:24px 0;">
        <div style="margin-bottom:24px;">
          <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0;">Análisis Predictivo</h1>
          <p style="color:#9d9d9d;font-size:13px;margin:4px 0 0;">Forecasting de riesgos, madurez y amenazas</p>
        </div>
        <div id="pred-content"><div style="text-align:center;padding:60px;color:#9d9d9d;">Cargando...</div></div>
      </div>`;
    await _load();
  }

  async function _load() {
    const el = document.getElementById('pred-content');
    try {
      const [trend, maturity, highRiskAssets, forecast] = await Promise.all([
        Api.get('/api/predictive/trend', { days: 90 }),
        Api.get('/api/predictive/maturity-path'),
        Api.get('/api/predictive/high-risk-assets', { limit: 8 }),
        Api.get('/api/predictive/threat-forecast'),
      ]);

      el.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">

          <!-- Trend -->
          <section style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:20px;">
            <h2 style="font-size:15px;font-weight:700;color:var(--brand-purple);margin:0 0 14px;
                       padding-bottom:8px;border-bottom:2px solid var(--brand-orange);">
              Trend de Riesgos (90 días) ${_trendIcon(trend.trend_direction)}
            </h2>
            <div style="font-size:20px;font-weight:700;color:var(--brand-purple);margin-bottom:4px;">
              ${trend.trend_label}
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:12px 0;">
              <div style="text-align:center;background:#f9f9f9;border-radius:6px;padding:10px;">
                <div style="font-size:20px;font-weight:700;color:var(--brand-purple);">${trend.total_risks}</div>
                <div style="font-size:11px;color:#9d9d9d;">Total periodo</div>
              </div>
              <div style="text-align:center;background:#f9f9f9;border-radius:6px;padding:10px;">
                <div style="font-size:20px;font-weight:700;color:${trend.total_change_pct > 0 ? 'var(--risk-critical)' : 'var(--risk-low)'};">
                  ${trend.total_change_pct > 0 ? '+' : ''}${trend.total_change_pct}%
                </div>
                <div style="font-size:11px;color:#9d9d9d;">Cambio</div>
              </div>
              <div style="text-align:center;background:#f9f9f9;border-radius:6px;padding:10px;">
                <div style="font-size:20px;font-weight:700;color:var(--brand-orange);">${trend.forecast_30d_total}</div>
                <div style="font-size:11px;color:#9d9d9d;">Forecast 30d</div>
              </div>
            </div>
            <div style="font-size:12px;color:#9d9d9d;margin-top:8px;">
              Velocidad: <strong>${trend.velocity_per_day}</strong> riesgos/día |
              Altos forecast: <strong>${trend.forecast_30d_high}</strong>
            </div>
          </section>

          <!-- Maturity Path -->
          <section style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:20px;">
            <h2 style="font-size:15px;font-weight:700;color:var(--brand-purple);margin:0 0 14px;
                       padding-bottom:8px;border-bottom:2px solid var(--brand-orange);">
              Camino de Madurez
            </h2>
            <div style="margin-bottom:12px;">
              <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                <span style="font-size:12px;color:#666;">Implementación actual</span>
                <span style="font-size:12px;font-weight:700;">${maturity.current_implementation_pct}%</span>
              </div>
              ${_progressBar(maturity.current_implementation_pct, 'var(--brand-purple)')}
            </div>
            <div style="margin-bottom:12px;">
              <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                <span style="font-size:12px;color:#666;">Objetivo alcanzable</span>
                <span style="font-size:12px;font-weight:700;color:var(--risk-low);">${maturity.target_pct}%</span>
              </div>
              ${_progressBar(maturity.target_pct, 'var(--risk-low)')}
            </div>
            <div style="font-size:12px;color:#9d9d9d;margin-bottom:10px;">
              ${maturity.implemented}/${maturity.total_controls} controles implementados |
              ${maturity.partial} parciales
            </div>
            <div style="max-height:160px;overflow-y:auto;">
              ${(maturity.recommendations || []).slice(0, 4).map(r => `
                <div style="border-left:3px solid ${r.priority === 'high' ? 'var(--brand-orange)' : '#ddd'};
                            padding:6px 10px;margin-bottom:6px;background:#f9f9f9;border-radius:0 4px 4px 0;">
                  <div style="font-size:12px;font-weight:600;">${UI.esc(r.title)}</div>
                  <div style="font-size:11px;color:#9d9d9d;">~${r.estimated_days}d esfuerzo</div>
                </div>`).join('')}
            </div>
          </section>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">

          <!-- Activos críticos -->
          <section style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:20px;">
            <h2 style="font-size:15px;font-weight:700;color:var(--brand-purple);margin:0 0 14px;
                       padding-bottom:8px;border-bottom:2px solid var(--brand-orange);">
              Activos con Mayor Riesgo
            </h2>
            ${(highRiskAssets || []).length === 0
              ? '<p style="color:#9d9d9d;font-size:13px;">No hay datos suficientes.</p>'
              : (highRiskAssets || []).map(a => `
                <div style="display:flex;justify-content:space-between;align-items:center;
                            padding:8px 0;border-bottom:1px solid #f5f5f5;">
                  <div style="flex:1;">
                    <div style="font-size:13px;font-weight:600;">${UI.esc(a.asset_name)}</div>
                    <div style="font-size:11px;color:#9d9d9d;">${UI.esc(a.asset_type)} | ${a.high_risk_count} riesgos altos</div>
                  </div>
                  <div style="text-align:right;">
                    <span style="background:#FEE2E2;color:#a83232;padding:2px 8px;border-radius:10px;
                                 font-size:12px;font-weight:700;">Nivel ${a.max_residual_level}</span>
                  </div>
                </div>`).join('')}
          </section>

          <!-- Threat Forecast -->
          <section style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:20px;">
            <h2 style="font-size:15px;font-weight:700;color:var(--brand-purple);margin:0 0 14px;
                       padding-bottom:8px;border-bottom:2px solid var(--brand-orange);">
              Forecast de Amenazas
            </h2>
            ${(forecast || []).length === 0
              ? '<p style="color:#9d9d9d;font-size:13px;">No hay datos suficientes de amenazas.</p>'
              : (forecast || []).map(f => `
                <div style="display:flex;justify-content:space-between;align-items:center;
                            padding:8px 0;border-bottom:1px solid #f5f5f5;">
                  <div style="flex:1;">
                    <div style="font-size:13px;font-weight:600;max-width:220px;overflow:hidden;
                                text-overflow:ellipsis;white-space:nowrap;" title="${UI.esc(f.threat_name)}">
                      ${UI.esc(f.threat_name)}
                    </div>
                    <div style="font-size:11px;color:#9d9d9d;">${f.risk_count} riesgos | L avg: ${f.avg_likelihood}</div>
                  </div>
                  <div>${_signalBadge(f.signal)}</div>
                </div>`).join('')}
          </section>
        </div>`;

    } catch (e) {
      el.innerHTML = `<div style="color:var(--risk-critical);padding:24px;">Error: ${UI.esc(e.message)}</div>`;
    }
  }

  return { render };
})();
