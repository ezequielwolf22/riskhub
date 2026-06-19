/* Vista de dashboard TPRM (Third-Party Risk Management).
   Portfolio de proveedores: KPIs, tiering, distribucion de riesgo, proximas revisiones. */
const ViewTprm = (() => {

  const TIER_LABELS  = { critical: 'Critico', high: 'Alto', medium: 'Medio', low: 'Bajo', unrated: 'Sin clasificar' };
  const TIER_COLORS  = {
    critical: 'var(--risk-critical)', high: 'var(--risk-high)',
    medium: 'var(--risk-medium)', low: 'var(--risk-low)', unrated: '#9CA3AF',
  };
  const LEVEL_LABELS = {
    critical: 'Critico', high: 'Alto', medium: 'Medio',
    low: 'Bajo', very_low: 'Muy bajo', unknown: 'Sin datos',
  };
  const LEVEL_COLORS = {
    critical: 'var(--risk-critical)', high: 'var(--risk-high)',
    medium: 'var(--risk-medium)', low: 'var(--risk-low)', very_low: 'var(--risk-low)', unknown: '#9CA3AF',
  };

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  function _scoreColor(score) {
    if (score === null || score === undefined) return '#9CA3AF';
    if (!window.RiskLevels) {
      if (score >= 75) return 'var(--risk-critical)';
      if (score >= 50) return 'var(--risk-high)';
      if (score >= 25) return 'var(--risk-medium)';
      return 'var(--risk-low)';
    }
    return RiskLevels.colorFor(Math.round(Math.min(100, score) * 8 / 100));
  }

  // Convierte score 0-100 a porcentaje de arco SVG para el gauge
  function _gaugeHtml(value10) {
    if (value10 === null || value10 === undefined) {
      return `<div style="text-align:center;padding:16px;">
        <div style="font-size:13px;color:var(--text-muted);">Sin scoring calculado</div>
        <div style="font-size:11px;color:var(--text-subtle);margin-top:4px;">Recalcula el portfolio para generar el indice</div>
      </div>`;
    }
    const pct = value10 / 10; // 0-1
    const _isoLvl = Math.round(pct * 8);
    const color = window.RiskLevels ? RiskLevels.colorFor(_isoLvl)
      : pct >= 0.75 ? 'var(--risk-critical)' : pct >= 0.5 ? 'var(--risk-high)' : pct >= 0.25 ? 'var(--risk-medium)' : 'var(--risk-low)';
    const label = window.RiskLevels ? RiskLevels.labelFor(_isoLvl)
      : pct >= 0.75 ? 'Critico' : pct >= 0.5 ? 'Alto' : pct >= 0.25 ? 'Medio' : 'Bajo';
    // SVG half-circle gauge
    const r = 52, cx = 70, cy = 65;
    const startAngle = Math.PI;
    const endAngle = startAngle + pct * Math.PI;
    const x1 = cx + r * Math.cos(startAngle);
    const y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle);
    const y2 = cy + r * Math.sin(endAngle);
    const largeArc = pct > 0.5 ? 1 : 0;
    return `
      <div style="display:flex;flex-direction:column;align-items:center;padding:8px 0;">
        <svg viewBox="0 0 140 80" width="160" style="overflow:hidden;">
          <path d="M ${cx-r} ${cy} A ${r} ${r} 0 0 1 ${cx+r} ${cy}" fill="none" stroke="var(--bg-3)" stroke-width="12" stroke-linecap="round"/>
          ${pct > 0 ? `<path d="M ${x1.toFixed(1)} ${y1.toFixed(1)} A ${r} ${r} 0 ${largeArc} 1 ${x2.toFixed(1)} ${y2.toFixed(1)}" fill="none" stroke="${color}" stroke-width="12" stroke-linecap="round"/>` : ''}
          <text x="${cx}" y="${cy - 8}" text-anchor="middle" font-size="26" font-weight="800" fill="${color}" font-family="var(--font-mono)">${value10.toFixed(1)}</text>
          <text x="${cx}" y="${cy + 6}" text-anchor="middle" font-size="11" fill="var(--text-muted)">/ 10</text>
        </svg>
        <div style="font-size:13px;font-weight:700;color:${color};margin-top:6px;">${label}</div>
        <div style="font-size:11px;color:var(--text-subtle);margin-top:2px;">Riesgo TPRM ponderado del portfolio</div>
      </div>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">TPRM &mdash; Riesgo de Terceros</h1>
          <p class="page-sub">Ciclo de vida del proveedor, tiering e inherent/residual risk &mdash; NIS2 / DORA / ENS / GDPR</p>
        </div>
        <div style="display:flex;gap:8px;">
          ${Auth.canEdit() ? '<button class="btn btn-primary" id="btn-recompute-all">Recalcular portfolio</button>' : ''}
        </div>
      </div>
      <div id="tprm-body"><div class="notice">Cargando...</div></div>
    `;
    const btn = document.getElementById('btn-recompute-all');
    if (btn) btn.onclick = async () => {
      btn.disabled = true; btn.textContent = 'Recalculando...';
      try {
        const r = await Api.tprm.recomputeAll();
        UI.toast(`Recalculados ${r.recomputed} proveedores`, 'success');
        await _load();
      } catch (e) { UI.toast(e.message, 'error'); }
      btn.disabled = false; btn.textContent = 'Recalcular portfolio';
    };
    await _load();
  }

  async function _load() {
    try {
      const [s, hm] = await Promise.all([Api.tprm.summary(), Api.tprm.heatmap()]);
      const body = document.getElementById('tprm-body');
      if (!body) return;
      body.innerHTML = _buildHtml(s, hm);
    } catch (e) {
      const body = document.getElementById('tprm-body');
      if (body) body.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _buildHtml(s, hm) {
    const total    = s.total || 0;
    const treated  = s.treated_count  ?? 0;
    const untreated = s.untreated_count ?? total;
    const score10  = s.portfolio_score_10;
    const reg      = s.regulatory_scope || {};
    const br       = s.by_residual_level || {};
    const bt       = s.by_tier || {};
    const upcoming = s.upcoming_reviews || [];
    const topRes   = s.top_residual || [];

    // Porcentaje tratados
    const treatedPct = total ? Math.round(treated / total * 100) : 0;

    return `
    <!-- FILA 1: KPIs principales -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:16px;">
      <div class="card" style="text-align:center;padding:16px 12px;">
        <div style="font-size:32px;font-weight:800;color:var(--brand-purple);font-family:var(--font-mono);">${total}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px;font-weight:600;">Proveedores en cartera</div>
      </div>
      <div class="card" style="text-align:center;padding:16px 12px;${s.overdue_assessment > 0 ? 'border-color:#FCA5A5;' : ''}">
        <div style="font-size:32px;font-weight:800;color:${s.overdue_assessment > 0 ? 'var(--risk-high)' : 'var(--text-muted)'};font-family:var(--font-mono);">${s.overdue_assessment}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px;font-weight:600;">Evaluaciones vencidas</div>
      </div>
      <div class="card" style="text-align:center;padding:16px 12px;">
        <div style="font-size:32px;font-weight:800;color:${(br.critical||0) > 0 ? 'var(--risk-critical)' : 'var(--text-muted)'};font-family:var(--font-mono);">${br.critical||0}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px;font-weight:600;">Riesgo residual critico</div>
      </div>
      <div class="card" style="text-align:center;padding:16px 12px;">
        <div style="font-size:14px;font-weight:700;color:var(--text-muted);margin-bottom:4px;">${reg.nis2||0} NIS2 &nbsp;·&nbsp; ${reg.dora||0} DORA</div>
        <div style="font-size:14px;font-weight:700;color:var(--text-muted);">${reg.gdpr_processors||0} GDPR &nbsp;·&nbsp; ${reg.ens||0} ENS</div>
        <div style="font-size:11px;color:var(--text-subtle);margin-top:6px;">Alcance regulatorio</div>
      </div>
    </div>

    <!-- FILA 2: Gauge + Tratados vs sin tratar + Distribucion por nivel -->
    <div style="display:grid;grid-template-columns:200px 1fr 1fr;gap:16px;margin-bottom:16px;">

      <!-- Gauge riesgo ponderado -->
      <div class="card" style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:16px 10px;">
        ${_gaugeHtml(score10)}
      </div>

      <!-- Tratados vs sin tratar -->
      <div class="card">
        <h3 style="margin:0 0 12px;font-size:14px;">Proveedores tratados vs pendientes</h3>
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
          <div style="flex:1;">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
              <span style="color:var(--risk-low);font-weight:600;">Tratados (con decision)</span>
              <span style="font-weight:700;">${treated} <span style="color:var(--text-muted);font-weight:400;">(${treatedPct}%)</span></span>
            </div>
            <div style="height:8px;border-radius:4px;background:var(--bg-3);overflow:hidden;">
              <div style="height:100%;width:${treatedPct}%;background:var(--risk-low);border-radius:4px;transition:width .4s;"></div>
            </div>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
          <div style="flex:1;">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
              <span style="color:var(--risk-medium);font-weight:600;">Sin tratar (pendientes)</span>
              <span style="font-weight:700;">${untreated} <span style="color:var(--text-muted);font-weight:400;">(${100 - treatedPct}%)</span></span>
            </div>
            <div style="height:8px;border-radius:4px;background:var(--bg-3);overflow:hidden;">
              <div style="height:100%;width:${100 - treatedPct}%;background:var(--risk-medium);border-radius:4px;transition:width .4s;"></div>
            </div>
          </div>
        </div>
        <div style="font-size:12px;color:var(--text-muted);font-style:italic;">"Tratado" = tiene al menos una evaluacion con decision (aprobado/rechazado).</div>
      </div>

      <!-- Distribucion por nivel residual -->
      <div class="card">
        <h3 style="margin:0 0 12px;font-size:14px;">Distribucion por nivel de riesgo</h3>
        ${(window.RiskLevels ? RiskLevels.all().slice().reverse() : [
          { code:'high',   label:'Alto',  color:'var(--risk-high)'   },
          { code:'medium', label:'Medio', color:'var(--risk-medium)' },
          { code:'low',    label:'Bajo',  color:'var(--risk-low)'    },
        ]).map(b => {
          const n = br[b.code] || 0;
          const pct = total ? Math.round(n / total * 100) : 0;
          return `<div style="margin-bottom:7px;">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
              <span style="color:${b.color};font-weight:600;">${UI.esc(b.label)}</span>
              <span style="font-weight:700;">${n} <span style="color:var(--text-muted);font-weight:400;">${pct}%</span></span>
            </div>
            <div style="height:6px;border-radius:3px;background:var(--bg-3);overflow:hidden;">
              <div style="height:100%;width:${pct}%;background:${b.color};border-radius:3px;"></div>
            </div>
          </div>`;
        }).join('')}
      </div>
    </div>

    <!-- FILA 3: Proximas revisiones + Distribucion por tier -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">

      <!-- Proximas revisiones -->
      <div class="card">
        <h3 style="margin:0 0 12px;font-size:14px;">Proximas revisiones (90 dias)</h3>
        ${upcoming.length === 0
          ? '<p style="font-size:13px;color:var(--text-subtle);">No hay revisiones programadas en los proximos 90 dias.</p>'
          : `<table class="data" style="font-size:12px;">
              <thead><tr><th>Proveedor</th><th>Tier</th><th>Fecha</th><th>Score</th></tr></thead>
              <tbody>
                ${upcoming.map(u => {
                  const days = Math.ceil((new Date(u.next_assessment_at) - new Date()) / 86400000);
                  const urgentColor = days <= 14 ? 'var(--risk-high)' : days <= 30 ? 'var(--risk-medium)' : 'var(--text-muted)';
                  return `<tr>
                    <td><strong>${UI.esc(u.name)}</strong><br><span style="color:var(--text-muted);font-size:10px;">${UI.esc(u.code)}</span></td>
                    <td>${u.tier ? _badge(TIER_LABELS[u.tier], TIER_COLORS[u.tier]) : '—'}</td>
                    <td style="color:${urgentColor};font-weight:600;">${new Date(u.next_assessment_at).toLocaleDateString('es-ES')}<br><span style="font-size:10px;">en ${days}d</span></td>
                    <td style="font-weight:700;color:${_scoreColor(u.residual_risk_score)};">${u.residual_risk_score ?? '—'}</td>
                  </tr>`;
                }).join('')}
              </tbody>
            </table>`}
      </div>

      <!-- Distribucion por tier -->
      <div class="card">
        <h3 style="margin:0 0 12px;font-size:14px;">Distribucion por tier</h3>
        ${['critical','high','medium','low','unrated'].map(t => {
          const n = bt[t] || 0;
          const pct = total ? Math.round(n / total * 100) : 0;
          return `<div style="margin-bottom:7px;">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
              <span style="color:${TIER_COLORS[t]};font-weight:600;">${TIER_LABELS[t]}</span>
              <span style="font-weight:700;">${n} <span style="color:var(--text-muted);font-weight:400;">${pct}%</span></span>
            </div>
            <div style="height:6px;border-radius:3px;background:var(--bg-3);overflow:hidden;">
              <div style="height:100%;width:${pct}%;background:${TIER_COLORS[t]};border-radius:3px;"></div>
            </div>
          </div>`;
        }).join('')}
      </div>
    </div>

    <!-- FILA 4: Mapa inherent vs residual -->
    <div class="card" style="margin-bottom:16px;">
      <h3 style="margin:0 0 12px;font-size:14px;">Mapa inherent vs residual (por proveedor)</h3>
      <div id="tprm-heatmap-inner"></div>
    </div>

    <!-- FILA 5: Top 10 por riesgo residual -->
    <div class="card">
      <h3 style="margin:0 0 12px;font-size:14px;">Top 10 proveedores por riesgo residual</h3>
      ${topRes.length === 0
        ? '<p style="font-size:13px;color:var(--text-subtle);">Sin datos. Recalcula el portfolio.</p>'
        : `<table class="data"><thead><tr>
            <th>Codigo</th><th>Nombre</th><th>Tier</th><th>Inherent</th><th>Residual</th><th>Reduccion</th>
          </tr></thead><tbody>
          ${topRes.map(v => {
            const red = v.inherent_risk_score > 0
              ? Math.round((1 - v.residual_risk_score / v.inherent_risk_score) * 100) : null;
            return `<tr>
              <td><strong>${UI.esc(v.code)}</strong></td>
              <td>${UI.esc(v.name)}</td>
              <td>${v.tier ? _badge(TIER_LABELS[v.tier], TIER_COLORS[v.tier]) : '—'}</td>
              <td><span style="font-weight:700;color:${_scoreColor(v.inherent_risk_score)};">${v.inherent_risk_score ?? '—'}</span></td>
              <td><span style="font-weight:700;color:${_scoreColor(v.residual_risk_score)};">${v.residual_risk_score ?? '—'}</span></td>
              <td style="font-size:12px;font-weight:700;color:${red > 0 ? 'var(--risk-low)' : red < 0 ? 'var(--risk-high)' : 'var(--text-muted)'};">
                ${red !== null ? (red > 0 ? '-' : red < 0 ? '+' : '') + Math.abs(red) + '%' : '—'}
              </td>
            </tr>`;
          }).join('')}
          </tbody></table>`}
    </div>
    `;

    // Renderizar heatmap SVG tras insertar el HTML
    setTimeout(() => _renderHeatmap(hm, document.getElementById('tprm-heatmap-inner')), 0);
  }

  function _renderHeatmap(data, wrap) {
    if (!wrap) return;
    if (!data || !data.length) {
      wrap.innerHTML = '<p style="font-size:13px;color:var(--text-subtle);">Sin proveedores con scoring calculado.</p>';
      return;
    }
    const W = 460, H = 280, pad = 44;
    const pts = data.map(d => {
      const x = pad + (d.inherent_risk_score / 100) * (W - 2 * pad);
      const y = H - pad - (d.residual_risk_score / 100) * (H - 2 * pad);
      const color = TIER_COLORS[d.tier] || '#9CA3AF';
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="6" fill="${color}" fill-opacity="0.8" stroke="#fff" stroke-width="1.5">
        <title>${UI.esc(d.code + ' ' + d.name)} — inherent ${d.inherent_risk_score}, residual ${d.residual_risk_score}</title>
      </circle>`;
    }).join('');
    // Linea de referencia (inherent = residual)
    const refX1 = pad, refY1 = H - pad, refX2 = W - pad, refY2 = pad;
    wrap.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="max-width:100%;height:auto;">
      <line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}" stroke="var(--border)" stroke-width="1"/>
      <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H-pad}" stroke="var(--border)" stroke-width="1"/>
      <line x1="${refX1}" y1="${refY1}" x2="${refX2}" y2="${refY2}" stroke="var(--border)" stroke-width="1" stroke-dasharray="4,4" opacity=".5"/>
      <text x="${W/2}" y="${H-6}" font-size="11" text-anchor="middle" fill="var(--text-muted)">Riesgo inherente →</text>
      <text x="14" y="${H/2}" font-size="11" text-anchor="middle" fill="var(--text-muted)" transform="rotate(-90 14 ${H/2})">Riesgo residual →</text>
      <text x="${W-8}" y="${H-pad-4}" font-size="9" fill="var(--text-subtle)" text-anchor="end">Sin reduccion</text>
      ${pts}
    </svg>`;
  }

  return { render };
})();
