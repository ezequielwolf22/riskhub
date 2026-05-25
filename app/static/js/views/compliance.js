/* Vista de dashboard de cumplimiento multi-framework. */
const ViewCompliance = (() => {

  function _scoreColor(score) {
    if (score >= 75) return 'var(--risk-low)';
    if (score >= 50) return 'var(--risk-medium)';
    if (score >= 25) return 'var(--risk-high)';
    return 'var(--risk-critical)';
  }

  function _scoreLabel(score) {
    if (score >= 75) return 'Conforme';
    if (score >= 50) return 'Parcial';
    if (score >= 25) return 'Deficiente';
    return 'Critico';
  }

  function _gaugeHtml(label, score, sublabel) {
    const color = _scoreColor(score);
    const pct = Math.min(100, Math.max(0, score));
    return `
      <div class="stat-card" style="flex:1;min-width:200px;text-align:center;padding:20px 16px;">
        <div style="font-size:12px;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:8px;">${UI.esc(label)}</div>
        <div style="position:relative;width:100px;height:100px;margin:0 auto 8px;">
          <svg viewBox="0 0 36 36" style="width:100px;height:100px;">
            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none" stroke="var(--border)" stroke-width="3.5"/>
            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none" stroke="${color}" stroke-width="3.5"
              stroke-dasharray="${pct}, 100" stroke-linecap="round"/>
          </svg>
          <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;">
            <div style="font-size:22px;font-weight:800;color:${color};">${pct}</div>
            <div style="font-size:10px;color:var(--text-muted);">/ 100</div>
          </div>
        </div>
        <div style="font-size:13px;font-weight:600;color:${color};">${_scoreLabel(pct)}</div>
        ${sublabel ? `<div style="font-size:11px;color:var(--text-muted);margin-top:4px;">${UI.esc(sublabel)}</div>` : ''}
      </div>
    `;
  }

  function _gapsHtml(gaps) {
    if (!gaps || !gaps.length) {
      return '<p style="color:var(--risk-low);font-size:13px;">Sin brechas identificadas.</p>';
    }
    return gaps.map(g => `
      <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px;">
        <span style="color:var(--risk-high);font-size:14px;margin-top:2px;">&#9679;</span>
        <span style="font-size:13px;">${UI.esc(g)}</span>
      </div>
    `).join('');
  }

  function _nistFunctionsHtml(fns) {
    if (!fns) return '';
    const fnColors = {
      GOVERN: '#7C3AED', IDENTIFY: '#2563EB', PROTECT: '#059669',
      DETECT: '#D97706', RESPOND: '#DC2626', RECOVER: '#0891B2',
    };
    const bars = Object.entries(fns).map(([fn, score]) => {
      const color = fnColors[fn] || 'var(--brand-purple)';
      return `
        <div style="margin-bottom:10px;">
          <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
            <span style="font-weight:600;color:${color};">${UI.esc(fn)}</span>
            <span style="color:var(--text-muted);">${score}%</span>
          </div>
          <div style="background:var(--border);border-radius:999px;height:8px;overflow:hidden;">
            <div style="width:${score}%;background:${color};height:100%;border-radius:999px;transition:width .4s;"></div>
          </div>
        </div>
      `;
    }).join('');
    return `<div style="margin-top:12px;">${bars}</div>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Dashboard de Cumplimiento</h1>
          <p class="page-sub">Puntuacion multi-framework: ISO 27001 | NIS2 | NIST CSF 2.0 | ENS</p>
        </div>
        <button class="btn btn-primary" id="btn-refresh-comp">Actualizar</button>
      </div>
      <div id="comp-content"><div class="loading-spinner" style="margin:40px auto;"></div></div>
    `;
    document.getElementById('btn-refresh-comp').onclick = () => _load(el);
    await _load(el);
  }

  async function _load(el) {
    const content = document.getElementById('comp-content');
    if (!content) return;
    content.innerHTML = '<p class="text-muted" style="text-align:center;padding:32px;">Calculando puntuaciones...</p>';
    try {
      const data = await Api.compliance.summary();
      _render(content, data);
      // Wire AI gap button (rendered inside _render)
      const gapBtn = document.getElementById('btn-gap-analysis');
      if (gapBtn) gapBtn.onclick = _runGapAnalysis;
    } catch (e) {
      content.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _render(content, data) {
    const meta = data._meta || {};
    const nist = data.nist_csf || {};
    const fns = nist.functions || {};

    content.innerHTML = `
      <!-- Resumen global -->
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:20px;">
        <h2 style="font-size:15px;font-weight:700;margin:0 0 16px;">Resumen operacional</h2>
        <div class="stats-row">
          <div class="stat-card">
            <div class="stat-value">${meta.total_controls || 0}</div>
            <div class="stat-label">Controles activos</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" style="color:var(--risk-low);">${meta.implemented_controls || 0}</div>
            <div class="stat-label">Implementados</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">${meta.total_risks || 0}</div>
            <div class="stat-label">Riesgos totales</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" style="color:var(--risk-medium);">${meta.risks_treated || 0}</div>
            <div class="stat-label">Con tratamiento</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" style="color:var(--risk-high);">${meta.open_incidents || 0}</div>
            <div class="stat-label">Incidentes abiertos</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" style="color:var(--risk-critical);">${meta.open_ncs || 0}</div>
            <div class="stat-label">NC abiertas</div>
          </div>
        </div>
      </div>

      <!-- Gauges por framework -->
      <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px;">
        ${_gaugeHtml('ISO 27001:2022', data.iso27001?.score || 0, data.iso27001?.label)}
        ${_gaugeHtml('NIS2', data.nis2?.score || 0, data.nis2?.label)}
        ${_gaugeHtml('NIST CSF 2.0', nist?.score || 0, nist?.label)}
        ${_gaugeHtml('ENS RD 311/2022', data.ens?.score || 0, data.ens?.label)}
      </div>

      <!-- NIST CSF funciones -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;" class="compliance-detail-grid">
        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;">
          <h3 style="font-size:14px;font-weight:700;margin:0 0 4px;">NIST CSF 2.0 — Funciones</h3>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 8px;">Cobertura por funcion</p>
          ${_nistFunctionsHtml(fns)}
        </div>

        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;">
          <h3 style="font-size:14px;font-weight:700;margin:0 0 4px;">ISO 27001:2022 — Brechas</h3>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">Clausula 6.1.3 y 10.1</p>
          ${_gapsHtml(data.iso27001?.gaps)}
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;" class="compliance-detail-grid">
        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;">
          <h3 style="font-size:14px;font-weight:700;margin:0 0 4px;">NIS2 — Brechas</h3>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">Art. 21 y 23</p>
          ${_gapsHtml(data.nis2?.gaps)}
        </div>
        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;">
          <h3 style="font-size:14px;font-weight:700;margin:0 0 4px;">ENS RD 311/2022 — Brechas</h3>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">Anexo II</p>
          ${_gapsHtml(data.ens?.gaps)}
        </div>
      </div>

      <p style="font-size:11px;color:var(--text-muted);margin-top:16px;text-align:center;">
        Puntuaciones calculadas a partir de los datos registrados en RiskHub. Actualizar regularmente para reflejar el estado real del SGSI.
      </p>

      <!-- AI Gap Analysis section -->
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;margin-top:20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <div>
            <h3 style="font-size:14px;font-weight:700;margin:0 0 4px;">Analisis de brechas de controles (M9)</h3>
            <p style="font-size:12px;color:var(--text-muted);margin:0;">Detecta controles sin implementar, temas debiles y problemas SOA por framework</p>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            <select id="gap-framework" style="font-size:13px;padding:4px 8px;border-radius:6px;border:1px solid var(--border);background:var(--bg-1);">
              <option value="iso27001">ISO 27001</option>
              <option value="nis2">NIS2</option>
              <option value="nist_csf">NIST CSF</option>
              <option value="ens">ENS</option>
            </select>
            <button class="btn btn-primary" id="btn-gap-analysis">Analizar brechas</button>
          </div>
        </div>
        <div id="gap-results" style="display:none;"></div>
      </div>
    `;
  }

  async function _runGapAnalysis() {
    const framework = document.getElementById('gap-framework')?.value || 'iso27001';
    const btn = document.getElementById('btn-gap-analysis');
    const resultsDiv = document.getElementById('gap-results');
    if (!resultsDiv) return;
    if (btn) { btn.disabled = true; btn.textContent = 'Analizando...'; }
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = '<p style="color:var(--text-muted);font-size:13px;">Analizando controles...</p>';
    try {
      const d = await Api.ai.controlGap({ framework });
      const s = d.summary || {};
      const pct = s.pct_implemented || 0;
      const pctColor = pct >= 75 ? 'var(--risk-low)' : pct >= 50 ? 'var(--risk-medium)' : pct >= 25 ? 'var(--risk-high)' : 'var(--risk-critical)';
      resultsDiv.innerHTML = `
        <hr style="border:none;border-top:1px solid var(--border);margin:0 0 16px;">
        <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;">
          <div class="stat-card"><div class="stat-value">${s.total||0}</div><div class="stat-label">Controles totales</div></div>
          <div class="stat-card"><div class="stat-value" style="color:var(--risk-low);">${s.implemented||0}</div><div class="stat-label">Implementados</div></div>
          <div class="stat-card"><div class="stat-value" style="color:var(--risk-medium);">${s.partial||0}</div><div class="stat-label">Parciales</div></div>
          <div class="stat-card"><div class="stat-value" style="color:var(--risk-high);">${s.not_implemented||0}</div><div class="stat-label">Sin implementar</div></div>
          <div class="stat-card">
            <div class="stat-value" style="color:${pctColor};">${pct}%</div>
            <div class="stat-label">Cobertura efectiva</div>
          </div>
        </div>
        ${d.weak_themes?.length ? `
          <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;color:var(--text-base);">Temas con menor cobertura</h4>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;">
            ${d.weak_themes.map(t => `
              <div style="background:var(--bg-2);border-radius:8px;padding:8px 12px;font-size:12px;min-width:140px;">
                <div style="font-weight:700;color:var(--risk-high);font-size:16px;">${t.score}%</div>
                <div style="font-weight:600;margin:2px 0;">${UI.esc(t.theme)}</div>
                <div style="color:var(--text-muted);">${t.not_implemented} sin implementar de ${t.total}</div>
              </div>`).join('')}
          </div>` : ''}
        ${d.soa_issues ? `
          <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;color:var(--text-base);">Problemas SOA (cl. 6.1.3)</h4>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;">
            ${d.soa_issues.missing_inclusion_reason > 0 ? `<span style="background:#FEF9C3;color:#854D0E;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600;">${d.soa_issues.missing_inclusion_reason} sin razon de inclusion</span>` : ''}
            ${d.soa_issues.missing_evidence > 0 ? `<span style="background:#FEE2E2;color:#991B1B;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600;">${d.soa_issues.missing_evidence} sin evidencia</span>` : ''}
            ${d.soa_issues.overdue_reviews > 0 ? `<span style="background:#FFF7ED;color:#9A3412;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600;">${d.soa_issues.overdue_reviews} revisiones vencidas</span>` : ''}
            ${(!d.soa_issues.missing_inclusion_reason && !d.soa_issues.missing_evidence && !d.soa_issues.overdue_reviews) ? '<span style="color:var(--risk-low);font-size:13px;">Sin problemas SOA detectados.</span>' : ''}
          </div>` : ''}
        ${d.recommendations?.length ? `
          <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;color:var(--text-base);">Recomendaciones</h4>
          <ul style="margin:0 0 12px;padding-left:20px;">
            ${d.recommendations.map(r => `<li style="font-size:13px;margin-bottom:4px;color:var(--text-base);">${UI.esc(r)}</li>`).join('')}
          </ul>` : ''}
        ${d.critical_gaps?.length ? `
          <details style="margin-top:8px;">
            <summary style="cursor:pointer;font-size:13px;font-weight:600;color:var(--text-muted);">
              ${d.critical_gaps.length} controles sin implementar (sin justificacion de exclusion)
            </summary>
            <div style="margin-top:8px;">
              ${d.critical_gaps.map(g => `
                <div style="font-size:12px;padding:4px 0;border-bottom:1px solid var(--border);display:flex;gap:8px;">
                  <span style="color:var(--text-muted);min-width:80px;">${UI.esc(g.theme||'-')}</span>
                  <span style="font-weight:600;">${UI.esc(g.control_name)}</span>
                  <span style="color:var(--text-muted);">madurez ${g.maturity}/5</span>
                </div>`).join('')}
            </div>
          </details>` : ''}
      `;
    } catch (e) {
      resultsDiv.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Analizar brechas'; }
    }
  }

  return { render };
})();
