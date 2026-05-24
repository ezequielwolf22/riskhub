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
            <div class="value">${s.controls_implemented}<span style="font-size:16px;color:var(--text-muted);">/${s.total_controls}</span></div>
            <div class="hint">madurez media: ${s.controls_avg_maturity}/5 · ${s.total_threats} amenazas · ${s.total_vulnerabilities} vuln.</div>
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
                <thead><tr><th>Codigo</th><th>Activo</th><th>Amenaza</th><th>Nivel</th><th>Reduccion</th></tr></thead>
                <tbody>
                  ${s.top_risks.map(r => {
                    const red = r.inherent_level > 0
                      ? Math.round((1 - r.level / r.inherent_level) * 100) : 0;
                    return `<tr style="cursor:pointer;" onclick="location.hash='#/risks?id=${r.id}'">
                      <td>${UI.codePill(r.code)}</td>
                      <td>${UI.esc(r.asset)}</td>
                      <td>${UI.esc(r.threat)}</td>
                      <td>${UI.riskPill(r.level)}</td>
                      <td><span style="font-size:12px;font-weight:600;color:${red>0?'var(--risk-low)':red<0?'var(--risk-high)':'var(--text-muted)'};">${red > 0 ? '-' : red < 0 ? '+' : ''}${Math.abs(red)}%</span></td>
                    </tr>`;}).join('')}
                </tbody>
              </table></div>`}
        </div>

        <div class="card-row" style="margin-top:16px;">
          <div class="card">
            <h3>Acciones rapidas</h3>
            <div style="display:flex;flex-direction:column;gap:8px;margin-top:8px;">
              <a href="#/risks?overdue=1" class="quick-action-btn ${s.overdue_treatments > 0 ? 'urgent' : ''}">
                <span>Tratamientos vencidos</span>
                <span class="qa-count">${s.overdue_treatments}</span>
              </a>
              <a href="#/risks" class="quick-action-btn ${s.no_treatment_high > 0 ? 'warn' : ''}">
                <span>Altos sin plan</span>
                <span class="qa-count">${s.no_treatment_high}</span>
              </a>
              <a href="#/calendar" class="quick-action-btn">
                <span>Ver calendario</span>
                <span style="font-size:12px;color:var(--text-muted);">→</span>
              </a>
              <a href="#/heatmap" class="quick-action-btn">
                <span>Mapa de calor</span>
                <span style="font-size:12px;color:var(--text-muted);">→</span>
              </a>
            </div>
          </div>

          <div class="card" style="flex:2;">
            <h3>Proximos vencimientos <span style="font-size:12px;font-weight:400;color:var(--text-muted);">(30 dias)</span></h3>
            <div id="dash-upcoming" style="margin-top:8px;"></div>
          </div>
        </div>
      `;
      // Cargar proximos vencimientos
      ViewDashboard._loadUpcoming();
    } catch (e) {
      main.innerHTML += `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  async _loadUpcoming() {
    const el = document.getElementById('dash-upcoming');
    if (!el) return;
    try {
      const all = await Api.risks.list();
      const now = new Date();
      const in30 = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
      const upcoming = all
        .filter(r => r.treatment_due_date && r.status !== 'accepted' && r.status !== 'closed')
        .map(r => ({ ...r, _due: new Date(r.treatment_due_date) }))
        .filter(r => r._due >= now && r._due <= in30)
        .sort((a, b) => a._due - b._due)
        .slice(0, 8);

      if (!upcoming.length) {
        el.innerHTML = '<p style="color:var(--text-subtle);font-size:13px;">Sin vencimientos en los proximos 30 dias.</p>';
        return;
      }
      el.innerHTML = upcoming.map(r => {
        const days = Math.ceil((r._due - now) / (1000 * 60 * 60 * 24));
        const urgency = days <= 7 ? 'var(--risk-high)' : days <= 14 ? 'var(--risk-medium)' : 'var(--risk-low)';
        return `<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border);">
          ${UI.codePill(r.code)}
          <span style="flex:1;font-size:13px;">${UI.esc(r.asset?.name||'-')}</span>
          <span style="font-size:12px;font-weight:600;color:${urgency};white-space:nowrap;">
            ${days === 0 ? 'Hoy' : days === 1 ? 'Manana' : 'en ' + days + ' dias'}
          </span>
        </div>`;
      }).join('');
    } catch (_) { /* silencioso */ }
  },

  _bar(v, total, color) {
    if (!total) return '';
    const pct = (v / total) * 100;
    return `<div style="width:${pct}%;background:${color};"></div>`;
  },
};
