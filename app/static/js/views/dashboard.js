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
            <div style="display:flex;align-items:center;gap:20px;margin-top:12px;">
              ${ViewDashboard._donut([
                { v: s.by_band.high,   color: 'var(--risk-high)',   label: 'Altos' },
                { v: s.by_band.medium, color: 'var(--risk-medium)', label: 'Medios' },
                { v: s.by_band.low,    color: 'var(--risk-low)',    label: 'Bajos' },
              ], s.total_risks)}
              <div style="flex:1;display:flex;flex-direction:column;gap:8px;">
                ${[
                  { key:'high',   label:'Altos (>5)',    color:'var(--risk-high)' },
                  { key:'medium', label:'Medios (3-5)',  color:'var(--risk-medium)' },
                  { key:'low',    label:'Bajos (<3)',    color:'var(--risk-low)' },
                ].map(b => `
                  <div>
                    <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
                      <span style="color:var(--text-base);">${b.label}</span>
                      <span style="font-weight:700;color:${b.color};">${s.by_band[b.key]}</span>
                    </div>
                    <div style="height:5px;border-radius:3px;background:var(--bg-3);overflow:hidden;">
                      <div style="height:100%;width:${s.total_risks?Math.round(s.by_band[b.key]/s.total_risks*100):0}%;background:${b.color};border-radius:3px;transition:width .4s;"></div>
                    </div>
                  </div>`).join('')}
              </div>
            </div>
          </div>

          <div class="card">
            <h3>Por estado del ciclo</h3>
            <div style="display:flex;flex-direction:column;gap:6px;margin-top:10px;">
              ${Object.entries(s.by_status).filter(([,v]) => v > 0).map(([k, v]) => `
                <div>
                  <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
                    <span>${UI.statusLabel(k)}</span>
                    <span style="font-weight:600;font-family:var(--font-mono);">${v}</span>
                  </div>
                  <div style="height:4px;border-radius:2px;background:var(--bg-3);overflow:hidden;">
                    <div style="height:100%;width:${s.total_risks?Math.round(v/s.total_risks*100):0}%;background:var(--brand-purple);border-radius:2px;"></div>
                  </div>
                </div>`).join('')}
            </div>
          </div>

          <div class="card">
            <h3>Por decision de tratamiento</h3>
            <div style="display:flex;flex-direction:column;gap:6px;margin-top:10px;">
              ${Object.entries(s.by_treatment).filter(([,v]) => v > 0).map(([k, v]) => `
                <div>
                  <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
                    <span>${UI.treatmentLabel(k)}</span>
                    <span style="font-weight:600;font-family:var(--font-mono);">${v}</span>
                  </div>
                  <div style="height:4px;border-radius:2px;background:var(--bg-3);overflow:hidden;">
                    <div style="height:100%;width:${s.total_risks?Math.round(v/s.total_risks*100):0}%;background:var(--brand-orange);border-radius:2px;"></div>
                  </div>
                </div>`).join('')
                || '<p style="font-size:13px;color:var(--text-subtle);margin:0;">Sin datos de tratamiento.</p>'}
            </div>
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

        <div class="card" style="margin-top:16px;" id="dash-controls-card">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
            <h3 style="margin:0;">Cobertura de controles ISO 27002 por tema</h3>
            <a href="#/controls" style="font-size:12px;color:var(--brand-purple);">Ver todos →</a>
          </div>
          <div id="dash-controls-body">
            <p style="color:var(--text-subtle);font-size:13px;">Cargando...</p>
          </div>
        </div>
      `;
      // Cargar proximos vencimientos y cobertura de controles
      ViewDashboard._loadUpcoming();
      ViewDashboard._loadControlsCoverage();
    } catch (e) {
      main.innerHTML += `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  async _loadControlsCoverage() {
    const el = document.getElementById('dash-controls-body');
    if (!el) return;
    try {
      const themes = await Api.controls.statsByTheme();
      if (!themes.length) {
        el.innerHTML = '<p style="color:var(--text-subtle);font-size:13px;">Sin controles implementados todavia. Accede a Controles para empezar.</p>';
        return;
      }
      const themeColors = {
        organizational: 'var(--brand-purple)',
        people: 'var(--brand-orange)',
        physical: '#2563EB',
        technological: '#059669',
      };
      el.innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;">
          ${themes.map(t => {
            const matPct = Math.round((t.avg_maturity / 5) * 100);
            const implPct = t.count ? Math.round((t.implemented / t.count) * 100) : 0;
            const color = themeColors[t.theme] || 'var(--brand-purple)';
            return `
              <div style="padding:14px;border-radius:8px;background:var(--bg-2);border:1px solid var(--border);">
                <div style="font-size:13px;font-weight:600;color:${color};margin-bottom:10px;">
                  ${UI.esc(t.label)}
                </div>
                <div style="margin-bottom:8px;">
                  <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-bottom:3px;">
                    <span>Madurez media</span>
                    <span style="font-weight:700;color:var(--text);">${t.avg_maturity}/5</span>
                  </div>
                  <div style="height:6px;border-radius:3px;background:var(--bg-3);overflow:hidden;">
                    <div style="height:100%;width:${matPct}%;background:${color};border-radius:3px;transition:width .5s;"></div>
                  </div>
                </div>
                <div>
                  <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-bottom:3px;">
                    <span>Implementados</span>
                    <span style="font-weight:700;color:var(--text);">${t.implemented}/${t.count}</span>
                  </div>
                  <div style="height:6px;border-radius:3px;background:var(--bg-3);overflow:hidden;">
                    <div style="height:100%;width:${implPct}%;background:${color};opacity:0.5;border-radius:3px;transition:width .5s;"></div>
                  </div>
                </div>
              </div>`;
          }).join('')}
        </div>`;
    } catch (_) {
      const el2 = document.getElementById('dash-controls-body');
      if (el2) el2.innerHTML = '<p style="color:var(--text-subtle);font-size:13px;">No disponible.</p>';
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

  /* SVG donut chart.
     segments: [{ v, color, label }]
     total: sum of all segments (can include unlabeled remainder)
  */
  _donut(segments, total) {
    const r = 38;
    const cx = 52, cy = 52;
    const circ = 2 * Math.PI * r;
    const size = 104;

    if (!total) {
      return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="flex-shrink:0;">
        <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--bg-3)" stroke-width="18"/>
        <text x="${cx}" y="${cy}" text-anchor="middle" dominant-baseline="middle"
              font-size="13" fill="var(--text-muted)">0</text>
      </svg>`;
    }

    let offset = 0;
    let paths = '';
    for (const seg of segments) {
      const frac = seg.v / total;
      const dash = frac * circ;
      // rotate so first segment starts at top (−90 deg)
      const rotateDeg = -90 + (offset / circ) * 360;
      paths += `<circle
        cx="${cx}" cy="${cy}" r="${r}"
        fill="none"
        stroke="${seg.color}"
        stroke-width="18"
        stroke-dasharray="${dash} ${circ}"
        transform="rotate(${rotateDeg} ${cx} ${cy})"
        style="transition:stroke-dasharray .5s;">
        <title>${seg.label}: ${seg.v}</title>
      </circle>`;
      offset += dash;
    }

    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"
                style="flex-shrink:0;" role="img" aria-label="Distribucion de riesgo">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--bg-3)" stroke-width="18"/>
      ${paths}
      <text x="${cx}" y="${cy - 7}" text-anchor="middle" dominant-baseline="middle"
            font-size="20" font-weight="700" fill="var(--text)">${total}</text>
      <text x="${cx}" y="${cy + 12}" text-anchor="middle" dominant-baseline="middle"
            font-size="9" fill="var(--text-muted)" letter-spacing="0.5">RIESGOS</text>
    </svg>`;
  },
};
