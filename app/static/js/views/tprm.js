/* Vista de dashboard TPRM (Third-Party Risk Management).
   Portfolio de proveedores: KPIs, tiering, distribucion de riesgo, próximas revisiones. */
const ViewTprm = (() => {

  const TIER_LABELS  = {
    critical: () => t('suppliers.tier.critical'),
    high:     () => t('suppliers.tier.high'),
    medium:   () => t('suppliers.tier.medium'),
    low:      () => t('suppliers.tier.low'),
    unrated:  () => t('common.not_assigned'),
  };
  const TIER_COLORS  = {
    critical: 'var(--risk-critical)', high: 'var(--risk-high)',
    medium: 'var(--risk-medium)', low: 'var(--risk-low)', unrated: '#9CA3AF',
  };
  const LEVEL_COLORS = {
    critical: 'var(--risk-critical)', high: 'var(--risk-high)',
    medium: 'var(--risk-medium)', low: 'var(--risk-low)', very_low: 'var(--risk-low)', unknown: '#9CA3AF',
  };

  function _tierLabel(tier) {
    return TIER_LABELS[tier] ? TIER_LABELS[tier]() : tier;
  }

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
        <div style="font-size:13px;color:var(--text-muted);">${t('common.not_available')}</div>
        <div style="font-size:11px;color:var(--text-subtle);margin-top:4px;">${t('tprm.score')}</div>
      </div>`;
    }
    const pct = value10 / 10; // 0-1
    const _isoLvl = Math.round(pct * 8);
    const color = window.RiskLevels ? RiskLevels.colorFor(_isoLvl)
      : pct >= 0.75 ? 'var(--risk-critical)' : pct >= 0.5 ? 'var(--risk-high)' : pct >= 0.25 ? 'var(--risk-medium)' : 'var(--risk-low)';
    const label = window.RiskLevels ? RiskLevels.labelFor(_isoLvl)
      : pct >= 0.75 ? t('common.critical') : pct >= 0.5 ? t('common.high') : pct >= 0.25 ? t('common.medium') : t('common.low');
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
        <div style="font-size:11px;color:var(--text-subtle);margin-top:2px;">${t('tprm.score')}</div>
      </div>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('tprm.title')}</h1>
          <p class="page-sub">${t('tprm.subtitle')}</p>
        </div>
        <div style="display:flex;gap:8px;">
          ${Auth.canEdit() ? `<button class="btn btn-primary" id="btn-recompute-all">${t('common.calculate')}</button>` : ''}
        </div>
      </div>
      <div id="tprm-body"><div class="notice">${t('common.loading')}</div></div>
    `;
    const btn = document.getElementById('btn-recompute-all');
    if (btn) btn.onclick = async () => {
      btn.disabled = true; btn.textContent = t('common.loading');
      try {
        const r = await Api.tprm.recomputeAll();
        UI.toast(`${t('common.total')}: ${r.recomputed}`, 'success');
        await _load();
      } catch (e) { UI.toast(e.message, 'error'); }
      btn.disabled = false; btn.textContent = t('common.calculate');
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
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px;font-weight:600;">${t('common.supplier')}</div>
      </div>
      <div class="card" style="text-align:center;padding:16px 12px;${s.overdue_assessment > 0 ? 'border-color:#FCA5A5;' : ''}">
        <div style="font-size:32px;font-weight:800;color:${s.overdue_assessment > 0 ? 'var(--risk-high)' : 'var(--text-muted)'};font-family:var(--font-mono);">${s.overdue_assessment}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px;font-weight:600;">${t('tprm.assessment')}</div>
      </div>
      <div class="card" style="text-align:center;padding:16px 12px;">
        <div style="font-size:32px;font-weight:800;color:${(br.critical||0) > 0 ? 'var(--risk-critical)' : 'var(--text-muted)'};font-family:var(--font-mono);">${br.critical||0}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px;font-weight:600;">${t('suppliers.residual_risk')}</div>
      </div>
      <div class="card" style="text-align:center;padding:16px 12px;">
        <div style="font-size:14px;font-weight:700;color:var(--text-muted);margin-bottom:4px;">${reg.nis2||0} NIS2 &nbsp;·&nbsp; ${reg.dora||0} DORA</div>
        <div style="font-size:14px;font-weight:700;color:var(--text-muted);">${reg.gdpr_processors||0} GDPR &nbsp;·&nbsp; ${reg.ens||0} ENS</div>
        <div style="font-size:11px;color:var(--text-subtle);margin-top:6px;">${t('common.type')}</div>
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
        <h3 style="margin:0 0 12px;font-size:14px;">${t('suppliers.title')}</h3>
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
          <div style="flex:1;">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
              <span style="color:var(--risk-low);font-weight:600;">${t('common.approved')}</span>
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
              <span style="color:var(--risk-medium);font-weight:600;">${t('common.pending')}</span>
              <span style="font-weight:700;">${untreated} <span style="color:var(--text-muted);font-weight:400;">(${100 - treatedPct}%)</span></span>
            </div>
            <div style="height:8px;border-radius:4px;background:var(--bg-3);overflow:hidden;">
              <div style="height:100%;width:${100 - treatedPct}%;background:var(--risk-medium);border-radius:4px;transition:width .4s;"></div>
            </div>
          </div>
        </div>
        <div style="font-size:12px;color:var(--text-muted);font-style:italic;">"${t('common.approved')}" = ${t('tprm.assessment_status.approved')}.</div>
      </div>

      <!-- Distribucion por nivel residual -->
      <div class="card">
        <h3 style="margin:0 0 12px;font-size:14px;">${t('suppliers.residual_risk')}</h3>
        ${(window.RiskLevels ? RiskLevels.all().slice().reverse() : [
          { code:'high',   label: t('common.high'),   color:'var(--risk-high)'   },
          { code:'medium', label: t('common.medium'), color:'var(--risk-medium)' },
          { code:'low',    label: t('common.low'),    color:'var(--risk-low)'    },
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

    <!-- FILA 3: Próximas revisiones + Distribucion por tier -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">

      <!-- Próximas revisiones -->
      <div class="card">
        <h3 style="margin:0 0 12px;font-size:14px;">${t('tprm.assessment')}</h3>
        ${upcoming.length === 0
          ? `<p style="font-size:13px;color:var(--text-subtle);">${t('common.no_results')}</p>`
          : `<table class="data" style="font-size:12px;">
              <thead><tr><th>${t('common.name')}</th><th>${t('suppliers.tier.critical')}</th><th>${t('common.date')}</th><th>${t('tprm.score')}</th></tr></thead>
              <tbody>
                ${upcoming.map(u => {
                  const days = Math.ceil((new Date(u.next_assessment_at) - new Date()) / 86400000);
                  const urgentColor = days <= 14 ? 'var(--risk-high)' : days <= 30 ? 'var(--risk-medium)' : 'var(--text-muted)';
                  return `<tr>
                    <td><strong>${UI.esc(u.name)}</strong><br><span style="color:var(--text-muted);font-size:10px;">${UI.esc(u.code)}</span></td>
                    <td>${u.tier ? _badge(_tierLabel(u.tier), TIER_COLORS[u.tier]) : '—'}</td>
                    <td style="color:${urgentColor};font-weight:600;">${new Date(u.next_assessment_at).toLocaleDateString('es-ES')}<br><span style="font-size:10px;">${days}d</span></td>
                    <td style="font-weight:700;color:${_scoreColor(u.residual_risk_score)};">${u.residual_risk_score ?? '—'}</td>
                  </tr>`;
                }).join('')}
              </tbody>
            </table>`}
      </div>

      <!-- Distribucion por tier -->
      <div class="card">
        <h3 style="margin:0 0 12px;font-size:14px;">${t('common.level')}</h3>
        ${['critical','high','medium','low','unrated'].map(tier => {
          const n = bt[tier] || 0;
          const pct = total ? Math.round(n / total * 100) : 0;
          return `<div style="margin-bottom:7px;">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
              <span style="color:${TIER_COLORS[tier]};font-weight:600;">${_tierLabel(tier)}</span>
              <span style="font-weight:700;">${n} <span style="color:var(--text-muted);font-weight:400;">${pct}%</span></span>
            </div>
            <div style="height:6px;border-radius:3px;background:var(--bg-3);overflow:hidden;">
              <div style="height:100%;width:${pct}%;background:${TIER_COLORS[tier]};border-radius:3px;"></div>
            </div>
          </div>`;
        }).join('')}
      </div>
    </div>

    <!-- FILA 4: Mapa inherent vs residual -->
    <div class="card" style="margin-bottom:16px;">
      <h3 style="margin:0 0 12px;font-size:14px;">${t('suppliers.inherent_risk')} vs ${t('suppliers.residual_risk')}</h3>
      <div id="tprm-heatmap-inner"></div>
    </div>

    <!-- FILA 5: Top 10 por riesgo residual -->
    <div class="card">
      <h3 style="margin:0 0 12px;font-size:14px;">${t('tprm.heatmap')}</h3>
      ${topRes.length === 0
        ? `<p style="font-size:13px;color:var(--text-subtle);">${t('common.no_results')}</p>`
        : `<table class="data"><thead><tr>
            <th>${t('common.name')}</th><th>${t('common.name')}</th><th>${t('common.level')}</th><th>${t('suppliers.inherent_risk')}</th><th>${t('suppliers.residual_risk')}</th><th>${t('common.result')}</th>
          </tr></thead><tbody>
          ${topRes.map(v => {
            const red = v.inherent_risk_score > 0
              ? Math.round((1 - v.residual_risk_score / v.inherent_risk_score) * 100) : null;
            return `<tr>
              <td><strong>${UI.esc(v.code)}</strong></td>
              <td>${UI.esc(v.name)}</td>
              <td>${v.tier ? _badge(_tierLabel(v.tier), TIER_COLORS[v.tier]) : '—'}</td>
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
      wrap.innerHTML = `<p style="font-size:13px;color:var(--text-subtle);">${t('common.no_results')}</p>`;
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
    // Línea de referencia (inherent = residual)
    const refX1 = pad, refY1 = H - pad, refX2 = W - pad, refY2 = pad;
    wrap.innerHTML = `<svg viewBox="0 0 ${W} ${H}" style="max-width:100%;height:auto;">
      <line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}" stroke="var(--border)" stroke-width="1"/>
      <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H-pad}" stroke="var(--border)" stroke-width="1"/>
      <line x1="${refX1}" y1="${refY1}" x2="${refX2}" y2="${refY2}" stroke="var(--border)" stroke-width="1" stroke-dasharray="4,4" opacity=".5"/>
      <text x="${W/2}" y="${H-6}" font-size="11" text-anchor="middle" fill="var(--text-muted)">${t('suppliers.inherent_risk')} →</text>
      <text x="14" y="${H/2}" font-size="11" text-anchor="middle" fill="var(--text-muted)" transform="rotate(-90 14 ${H/2})">${t('suppliers.residual_risk')} →</text>
      <text x="${W-8}" y="${H-pad-4}" font-size="9" fill="var(--text-subtle)" text-anchor="end">${t('common.na')}</text>
      ${pts}
    </svg>`;
  }

  function _escHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  async function renderConcentrationRisk(container) {
    container.innerHTML = `<p class="text-muted">${t('common.loading_data')}</p>`;
    let data;
    try {
      data = await Api.get('/api/tprm/concentration-risk');
    } catch (e) {
      container.innerHTML = '<p class="text-muted">' + t('common.error') + ': ' + _escHtml(e.message) + '</p>';
      return;
    }

    if (!data || !data.length) {
      container.innerHTML = `<p class="text-muted">${t('common.no_results')}</p>`;
      return;
    }

    const rows = data.map(d => `
      <tr class="${d.is_critical ? 'row--warning' : ''}">
        <td>${_escHtml(d.supplier_name)} <span class="badge badge--tier">${_escHtml(d.tier || '-')}</span></td>
        <td style="text-align:center;">${d.critical_processes_dependent} / ${d.total_critical_processes}</td>
        <td>
          <div style="display:flex;align-items:center;gap:6px;">
            <div class="progress-bar" style="width:${Math.min(d.concentration_pct, 100)}px;"></div>
            <span style="font-size:12px;font-weight:600;">${d.concentration_pct}%</span>
          </div>
        </td>
        <td>${d.is_critical
          ? `<span class="badge badge--danger">DORA: ${t('common.critical')}</span>`
          : '<span class="badge badge--ok">OK</span>'}</td>
        <td style="font-size:12px;color:var(--text-muted);">
          ${d.mitigation && d.mitigation.notes
            ? _escHtml(d.mitigation.notes.substring(0, 60)) + (d.mitigation.notes.length > 60 ? '...' : '')
            : `<span style="color:var(--text-subtle);">${t('common.notes')}</span>`}
        </td>
      </tr>
    `).join('');

    container.innerHTML = `
      <table class="data-table">
        <thead>
          <tr>
            <th>${t('common.supplier')}</th>
            <th style="text-align:center;">${t('common.level')}</th>
            <th>${t('common.score')}</th>
            <th>${t('common.status')}</th>
            <th>${t('common.notes')}</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  return { render, renderConcentrationRisk };
})();
