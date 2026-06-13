/* Vista de dashboard TPRM (Third-Party Risk Management).
   Portfolio de proveedores: tiering, inherent vs residual risk, alcance regulatorio. */
const ViewTprm = (() => {

  const TIER_LABELS = { critical: 'Critico', high: 'Alto', medium: 'Medio', low: 'Bajo', unrated: 'Sin clasificar' };
  const TIER_COLORS = {
    critical: 'var(--risk-critical)', high: 'var(--risk-high)',
    medium: 'var(--risk-medium)', low: 'var(--risk-low)', unrated: '#9CA3AF',
  };
  const LEVEL_LABELS = {
    critical: 'Critico', high: 'Alto', medium: 'Medio',
    low: 'Bajo', very_low: 'Muy bajo', unknown: 'Sin datos',
  };

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  function _riskColor(score) {
    if (score === null || score === undefined) return '#9CA3AF';
    if (score >= 75) return 'var(--risk-critical)';
    if (score >= 50) return 'var(--risk-high)';
    if (score >= 25) return 'var(--risk-medium)';
    return 'var(--risk-low)';
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">TPRM — Riesgo de Terceros</h1>
          <p class="page-sub">Ciclo de vida del proveedor, tiering e inherent/residual risk — NIS2 / DORA / ENS / GDPR</p>
        </div>
        <div style="display:flex;gap:8px;">
          ${Auth.canEdit() ? '<button class="btn btn-primary" id="btn-recompute-all">Recalcular portfolio</button>' : ''}
        </div>
      </div>
      <div class="stats-row" id="tprm-stats" style="margin-bottom:16px;"></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
        <div class="card"><h3 style="margin-top:0;">Distribucion por tier</h3><div id="tprm-tier"></div></div>
        <div class="card"><h3 style="margin-top:0;">Riesgo residual</h3><div id="tprm-residual"></div></div>
      </div>
      <div class="card" style="margin-bottom:16px;">
        <h3 style="margin-top:0;">Mapa inherent vs residual</h3>
        <div id="tprm-heatmap"></div>
      </div>
      <div class="card">
        <h3 style="margin-top:0;">Top 10 proveedores por riesgo residual</h3>
        <div id="tprm-top"></div>
      </div>
    `;
    const btn = document.getElementById('btn-recompute-all');
    if (btn) btn.onclick = async () => {
      btn.disabled = true;
      try {
        const r = await Api.tprm.recomputeAll();
        UI.toast(`Recalculados ${r.recomputed} proveedores`, 'success');
        await _load();
      } catch (e) { UI.toast(e.message, 'error'); }
      btn.disabled = false;
    };
    await _load();
  }

  async function _load() {
    try {
      const [s, hm] = await Promise.all([Api.tprm.summary(), Api.tprm.heatmap()]);
      _renderStats(s);
      _renderTierBars(s);
      _renderResidual(s);
      _renderTop(s);
      _renderHeatmap(hm);
    } catch (e) {
      const wrap = document.getElementById('tprm-stats');
      if (wrap) wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _renderStats(s) {
    const wrap = document.getElementById('tprm-stats');
    if (!wrap) return;
    const r = s.regulatory_scope || {};
    wrap.innerHTML = `
      <div class="stat-card"><div class="stat-value">${s.total}</div><div class="stat-label">Proveedores</div></div>
      <div class="stat-card"><div class="stat-value" style="color:var(--risk-critical);">${(s.by_tier.critical||0)}</div><div class="stat-label">Tier critico</div></div>
      <div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.overdue_assessment}</div><div class="stat-label">Evaluacion vencida</div></div>
      <div class="stat-card"><div class="stat-value">${r.nis2||0}/${r.dora||0}</div><div class="stat-label">NIS2 / DORA</div></div>
      <div class="stat-card"><div class="stat-value">${r.gdpr_processors||0}</div><div class="stat-label">Encargados GDPR</div></div>
    `;
  }

  function _renderTierBars(s) {
    const wrap = document.getElementById('tprm-tier');
    if (!wrap) return;
    const total = s.total || 1;
    wrap.innerHTML = ['critical', 'high', 'medium', 'low', 'unrated'].map(t => {
      const n = s.by_tier[t] || 0;
      const pct = Math.round(n / total * 100);
      return `<div style="margin-bottom:8px;">
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
          <span>${TIER_LABELS[t]}</span><span>${n}</span></div>
        <div style="background:var(--bg-soft,#eee);border-radius:4px;height:10px;overflow:hidden;">
          <div style="width:${pct}%;height:100%;background:${TIER_COLORS[t]};"></div></div>
      </div>`;
    }).join('');
  }

  function _renderResidual(s) {
    const wrap = document.getElementById('tprm-residual');
    if (!wrap) return;
    const br = s.by_residual_level || {};
    const total = s.total || 1;
    wrap.innerHTML = ['critical', 'high', 'medium', 'low', 'very_low'].map(l => {
      const n = br[l] || 0;
      const pct = Math.round(n / total * 100);
      return `<div style="margin-bottom:8px;">
        <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
          <span>${LEVEL_LABELS[l]}</span><span>${n}</span></div>
        <div style="background:var(--bg-soft,#eee);border-radius:4px;height:10px;overflow:hidden;">
          <div style="width:${pct}%;height:100%;background:${_riskColor(l==='critical'?80:l==='high'?60:l==='medium'?40:l==='low'?20:5)};"></div></div>
      </div>`;
    }).join('');
  }

  function _renderTop(s) {
    const wrap = document.getElementById('tprm-top');
    if (!wrap) return;
    const top = s.top_residual || [];
    if (!top.length) { wrap.innerHTML = '<p class="text-muted">Sin datos. Recalcula el portfolio para generar el scoring.</p>'; return; }
    wrap.innerHTML = `<table class="data"><thead><tr>
      <th>Codigo</th><th>Nombre</th><th>Tier</th><th>Inherent</th><th>Residual</th></tr></thead><tbody>
      ${top.map(v => `<tr>
        <td><b>${UI.esc(v.code)}</b></td>
        <td>${UI.esc(v.name)}</td>
        <td>${v.tier ? _badge(TIER_LABELS[v.tier], TIER_COLORS[v.tier]) : '-'}</td>
        <td><span style="font-weight:700;color:${_riskColor(v.inherent_risk_score)};">${v.inherent_risk_score ?? '-'}</span></td>
        <td><span style="font-weight:700;color:${_riskColor(v.residual_risk_score)};">${v.residual_risk_score ?? '-'}</span></td>
      </tr>`).join('')}
    </tbody></table>`;
  }

  function _renderHeatmap(data) {
    const wrap = document.getElementById('tprm-heatmap');
    if (!wrap) return;
    if (!data.length) { wrap.innerHTML = '<p class="text-muted">Sin proveedores con scoring calculado.</p>'; return; }
    const W = 460, H = 320, pad = 40;
    const pts = data.map(d => {
      const x = pad + (d.inherent_risk_score / 100) * (W - 2 * pad);
      const y = H - pad - (d.residual_risk_score / 100) * (H - 2 * pad);
      const color = TIER_COLORS[d.tier] || '#9CA3AF';
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="6" fill="${color}" fill-opacity="0.75" stroke="#fff" stroke-width="1"><title>${UI.esc(d.code + ' ' + d.name)} — inherent ${d.inherent_risk_score}, residual ${d.residual_risk_score}</title></circle>`;
    }).join('');
    wrap.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="max-width:100%;height:auto;">
      <line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}" stroke="var(--border,#ccc)"/>
      <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H-pad}" stroke="var(--border,#ccc)"/>
      <text x="${W/2}" y="${H-8}" font-size="11" text-anchor="middle" fill="var(--text-muted)">Inherent risk →</text>
      <text x="14" y="${H/2}" font-size="11" text-anchor="middle" fill="var(--text-muted)" transform="rotate(-90 14 ${H/2})">Residual risk →</text>
      ${pts}
    </svg>`;
  }

  return { render };
})();
