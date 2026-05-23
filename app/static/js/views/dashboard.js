/* Dashboard - resumen ejecutivo. */
const ViewDashboard = {
  async render(main) {
    main.innerHTML = UI.sectionHeader(
      'Vision global del riesgo',
      'Resumen del estado actual de los riesgos de seguridad de la informacion'
    ) + '<div id="dash-content">' + UI.notice('Cargando datos...') + '</div>';

    try {
      const s = await Api.risks.summary();
      const c = document.getElementById('dash-content');
      c.innerHTML = `
        <div class="card-row" style="margin-bottom:20px;">
          <div class="kpi">
            <div class="label">Activos inventariados</div>
            <div class="value">${s.total_assets}</div>
          </div>
          <div class="kpi">
            <div class="label">Riesgos identificados</div>
            <div class="value">${s.total_risks}</div>
          </div>
          <div class="kpi">
            <div class="label">Controles implantados</div>
            <div class="value">${s.total_controls}</div>
            <div class="hint">de ${s.total_threats} amenazas y ${s.total_vulnerabilities} vulnerabilidades en catalogo</div>
          </div>
          <div class="kpi" style="background: linear-gradient(45deg, #FFE6CE 0%, #EDD1FF 100%);">
            <div class="label">Riesgos altos sin tratar</div>
            <div class="value">${s.by_band.high}</div>
            <div class="hint">requieren atencion inmediata</div>
          </div>
        </div>

        <div class="card-row" style="margin-bottom:20px;">
          <div class="kpi" style="cursor:pointer;${s.overdue_treatments > 0 ? 'background:linear-gradient(45deg,#FEE2E2,#FECACA);border-color:#FCA5A5;' : ''}"
               onclick="location.hash='#/risks?overdue=1'" title="Ver riesgos con tratamiento vencido">
            <div class="label">Tratamientos vencidos</div>
            <div class="value" style="${s.overdue_treatments > 0 ? 'color:#991B1B;' : ''}">${s.overdue_treatments}</div>
            <div class="hint">clic para ver detalle</div>
          </div>
          <div class="kpi" style="${s.no_treatment_high > 0 ? 'background:linear-gradient(45deg,#FEF9C3,#FDE68A);border-color:#FCD34D;' : ''}">
            <div class="label">Altos sin plan definido</div>
            <div class="value" style="${s.no_treatment_high > 0 ? 'color:#92400E;' : ''}">${s.no_treatment_high}</div>
            <div class="hint">riesgos >= 5 sin opcion de tratamiento</div>
          </div>
          <div class="kpi" style="background:linear-gradient(45deg,#D1FAE5,#A7F3D0);">
            <div class="label">Reduccion del riesgo</div>
            <div class="value" style="color:#065F46;">${s.risk_reduction_pct}%</div>
            <div class="hint">reduccion media inherente → residual</div>
          </div>
        </div>

        <div class="card-row">
          <div class="card">
            <h3>Distribucion por nivel residual</h3>
            <div style="display:flex;gap:24px;margin-top:12px;">
              <div style="flex:1;text-align:center;">
                <div style="font-size:28px;font-weight:700;color:var(--risk-low);">${s.by_band.low}</div>
                <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;">Bajos</div>
              </div>
              <div style="flex:1;text-align:center;">
                <div style="font-size:28px;font-weight:700;color:var(--risk-medium);">${s.by_band.medium}</div>
                <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;">Medios</div>
              </div>
              <div style="flex:1;text-align:center;">
                <div style="font-size:28px;font-weight:700;color:var(--risk-high);">${s.by_band.high}</div>
                <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;">Altos</div>
              </div>
            </div>
            <div style="margin-top:18px;height:8px;border-radius:4px;overflow:hidden;display:flex;background:var(--bg-3);">
              ${ViewDashboard._bar(s.by_band.low, s.total_risks, 'var(--risk-low)')}
              ${ViewDashboard._bar(s.by_band.medium, s.total_risks, 'var(--risk-medium)')}
              ${ViewDashboard._bar(s.by_band.high, s.total_risks, 'var(--risk-high)')}
            </div>
          </div>

          <div class="card">
            <h3>Por estado del ciclo</h3>
            <table class="data" style="margin-top:8px;">
              <tbody>
                ${Object.entries(s.by_status).map(([k, v]) => `
                  <tr>
                    <td>${UI.statusLabel(k)}</td>
                    <td style="text-align:right;font-family:var(--font-mono);font-weight:600;">${v}</td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>

          <div class="card">
            <h3>Por decision de tratamiento</h3>
            <table class="data" style="margin-top:8px;">
              <tbody>
                ${Object.entries(s.by_treatment).map(([k, v]) => `
                  <tr>
                    <td>${UI.treatmentLabel(k)}</td>
                    <td style="text-align:right;font-family:var(--font-mono);font-weight:600;">${v}</td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>
        </div>

        <div class="card" style="margin-top:16px;">
          <h3>Top 10 riesgos por nivel residual</h3>
          ${s.top_risks.length === 0
            ? '<p style="color:var(--text-subtle);">No hay riesgos registrados todavia. Comienza creando activos y asociandoles amenazas.</p>'
            : `<div class="table-wrap"><table class="data">
                <thead><tr><th>Codigo</th><th>Activo</th><th>Amenaza</th><th>Nivel</th></tr></thead>
                <tbody>
                  ${s.top_risks.map(r => `
                    <tr style="cursor:pointer;" onclick="location.hash='#/risks'">
                      <td>${UI.codePill(r.code)}</td>
                      <td>${UI.esc(r.asset)}</td>
                      <td>${UI.esc(r.threat)}</td>
                      <td>${UI.riskPill(r.level)}</td>
                    </tr>`).join('')}
                </tbody>
              </table></div>`}
        </div>
      `;
    } catch (e) {
      main.innerHTML += `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _bar(v, total, color) {
    if (!total) return '';
    const pct = (v / total) * 100;
    return `<div style="width:${pct}%;background:${color};"></div>`;
  },
};
