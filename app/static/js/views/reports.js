/* Vista Informes — PDF, Excel e informes generados por IA. */
const ViewReports = {

  render(main) {
    main.innerHTML = UI.sectionHeader(
      'Informes',
      'Documentos para auditoria, comites y direccion — PDF y Excel'
    ) + `
      <div id="reports-content">

        <!-- Informes estaticos -->
        <div class="card" style="margin-bottom:16px;">
          <h3 style="margin-bottom:4px;">Informes del registro</h3>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
            Generados directamente desde el registro de riesgos. Sin IA, descarga instantanea.
          </p>
          <div class="card-row">
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;">
              <h4 style="margin:0 0 6px;">Risk Register</h4>
              <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">
                Listado completo de riesgos ordenados por nivel residual. Activo, amenaza,
                niveles inherente/residual, estado y decision de tratamiento. ISO/IEC 27005:2018.
              </p>
              <div style="display:flex;gap:8px;">
                <button class="btn btn-primary" style="flex:1;" onclick="ViewReports._download('rr-pdf')">
                  PDF
                </button>
                <button class="btn" style="flex:1;" onclick="ViewReports._download('rr-excel')">
                  Excel
                </button>
              </div>
            </div>
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;">
              <h4 style="margin:0 0 6px;">Statement of Applicability</h4>
              <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">
                Declaracion de aplicabilidad de los 93 controles ISO 27002:2022, con estado
                y madurez de cada implementacion. Obligatorio para certificacion ISO 27001.
              </p>
              <div style="display:flex;gap:8px;">
                <button class="btn btn-primary" style="flex:1;" onclick="ViewReports._download('soa')">
                  PDF
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Informes IA -->
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;">
            <h3 style="margin:0;">Informes generados por IA</h3>
            <span class="badge badge-muted" style="font-size:10px;">Claude API requerida</span>
          </div>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
            Claude analiza todos los datos del registro de riesgos — activos, amenazas,
            controles, planes de tratamiento y estadisticas — y genera un informe ejecutivo
            en lenguaje natural. Tarda entre 30-60 segundos.
          </p>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            ${[
              {
                id: 'treatment_plan',
                title: 'Plan de Tratamiento de Riesgos',
                desc: 'Narrativa detallada por riesgo: acciones concretas, prioridades (inmediato/corto/medio/largo plazo), metricas de exito y hoja de ruta de implementacion en 3 fases.',
                icon: '📋',
                excel: true,
              },
              {
                id: 'executive_dashboard',
                title: 'Dashboard Ejecutivo',
                desc: 'Postura de riesgo para la Direccion: hallazgos clave, acciones criticas, analisis de KPIs, efectividad de controles y estado de cumplimiento ISO 27001.',
                icon: '📊',
                excel: true,
              },
              {
                id: 'committee_minutes',
                title: 'Acta de Comite de Seguridad',
                desc: 'Acta formal con orden del dia, riesgos aceptados con justificacion, decisiones adoptadas y acciones acordadas. Lista para que el Comite la firme.',
                icon: '🏛️',
                excel: true,
              },
              {
                id: 'followup_report',
                title: 'Informe de Seguimiento ISO 27005',
                desc: 'Evaluacion del proceso segun ISO 27005 clausula 12: monitorizacion, revision, mejora continua, tendencias, fortalezas/debilidades y recomendaciones.',
                icon: '📈',
                excel: true,
              },
            ].map(r => `
              <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;
                          display:flex;flex-direction:column;gap:8px;">
                <div style="display:flex;align-items:center;gap:8px;">
                  <span style="font-size:20px;">${r.icon}</span>
                  <h4 style="margin:0;font-size:14px;line-height:1.3;">${r.title}</h4>
                </div>
                <p style="font-size:12px;color:var(--text-muted);margin:0;line-height:1.5;">${r.desc}</p>
                <div style="margin-top:auto;display:flex;gap:6px;">
                  <button class="btn btn-primary" style="flex:1;font-size:12px;"
                          onclick="ViewReports._generateAI('${r.id}','pdf')" id="btn-${r.id}-pdf">
                    Generar PDF
                  </button>
                  ${r.excel ? `<button class="btn" style="flex:1;font-size:12px;"
                          onclick="ViewReports._generateAI('${r.id}','excel')" id="btn-${r.id}-excel">
                    Generar Excel
                  </button>` : ''}
                </div>
              </div>`).join('')}
          </div>
          <div style="margin-top:12px;background:var(--bg-2);border-radius:8px;padding:10px 14px;font-size:12px;color:var(--text-muted);">
            Los informes de IA toman en cuenta: activos, amenazas, riesgos, controles, planes de tratamiento,
            estadisticas del registro y el contexto organizacional configurado.
          </div>
        </div>

      </div>`;
  },

  _download(type) {
    const actions = {
      'rr-pdf': () => {
        UI.toast('Generando Risk Register PDF...', 'info');
        Api.download('/api/reports/risk-register', 'risk_register.pdf')
           .catch(e => UI.toast(e.message, 'error'));
      },
      'rr-excel': () => {
        UI.toast('Generando Risk Register Excel...', 'info');
        Api.download(
          '/api/reports/risk-register-excel',
          `riskhub_export_${new Date().toISOString().slice(0,10)}.xlsx`
        ).catch(e => UI.toast(e.message, 'error'));
      },
      'soa': () => {
        UI.toast('Generando Statement of Applicability...', 'info');
        Api.download('/api/reports/soa', 'statement_of_applicability.pdf')
           .catch(e => UI.toast(e.message, 'error'));
      },
    };
    if (actions[type]) actions[type]();
  },

  async _generateAI(reportType, format) {
    const btnId = `btn-${reportType}-${format}`;
    const btn = document.getElementById(btnId);
    const labels = {
      treatment_plan: 'Plan de Tratamiento',
      executive_dashboard: 'Dashboard Ejecutivo',
      committee_minutes: 'Acta de Comite',
      followup_report: 'Informe de Seguimiento',
    };
    const label = labels[reportType] || reportType;

    if (btn) { btn.disabled = true; btn.textContent = 'Generando...'; }
    UI.toast(`Generando ${label} (${format.toUpperCase()}) con IA... puede tardar 30-60 s.`, 'info');

    const ext = format === 'excel' ? 'xlsx' : 'pdf';
    const filename = `${reportType}_${new Date().toISOString().slice(0,10)}.${ext}`;

    try {
      const tok = Api.token();
      const resp = await fetch('/api/reports/ai-generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + tok,
        },
        body: JSON.stringify({ report_type: reportType, format }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || resp.statusText);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
      UI.toast(`${label} generado correctamente`, 'success');
    } catch (e) {
      UI.toast('Error al generar el informe: ' + e.message, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = format === 'excel' ? 'Generar Excel' : 'Generar PDF';
      }
    }
  },
};
