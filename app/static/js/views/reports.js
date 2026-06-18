/* Vista Informes — PDF, Excel e informes generados por IA. */
const ViewReports = {

  render(main) {
    main.innerHTML = UI.sectionHeader(
      'Informes',
      'Documentos para auditoría, comités y dirección — PDF y Excel'
    ) + `
      <div id="reports-content">

        <!-- Informes estaticos -->
        <div class="card" style="margin-bottom:16px;">
          <h3 style="margin-bottom:4px;">Informes del registro</h3>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
            Generados directamente desde los datos registrados. Sin IA, descarga instantanea.
          </p>
          <div class="card-row">
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;">
              <h4 style="margin:0 0 6px;">Estado del SGSI</h4>
              <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">
                Informe ejecutivo multi-modulo: riesgos, controles, incidentes, tareas,
                politicas y RGPD. Resumen de KPIs de todo el sistema en un solo documento.
              </p>
              <div style="display:flex;gap:8px;">
                <button class="btn btn-primary" style="flex:1;" onclick="ViewReports._download('sgsi-status')">
                  PDF
                </button>
              </div>
            </div>
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
                Declaracion de aplicabilidad completa: 93 controles ISO 27002:2022 con estado, madurez,
                razon de inclusion/exclusion, evidencias, fechas de revision y seccion de firma.
              </p>
              <div style="display:flex;gap:8px;">
                <button class="btn btn-primary" style="flex:1;" onclick="ViewReports._download('soa')">
                  PDF
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Revision por la Direccion -->
        <div class="card" style="margin-bottom:16px;border:2px solid var(--brand-purple);">
          <h3 style="margin-bottom:4px;">Revision por la Direccion</h3>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
            Informe completo segun ISO 27001:2022 clausula 9.3 y ENS. Incluye todos los apartados normativos
            con datos reales del sistema — los campos sin datos aparecen marcados [A CUMPLIMENTAR].
            Disponible en PDF (para presentar), Excel (para editar) y Word (para personalizar y firmar).
          </p>
          <div style="display:flex;gap:10px;flex-wrap:wrap;">
            <button class="btn btn-primary" onclick="ViewReports._download('mgmt-review-pdf')">
              PDF
            </button>
            <button class="btn" onclick="ViewReports._download('mgmt-review-excel')">
              Excel editable
            </button>
            <button class="btn" onclick="ViewReports._download('mgmt-review-word')">
              Word (.docx)
            </button>
          </div>
        </div>

        <!-- Post-Mortem BCP -->
        <div class="card" style="margin-bottom:16px;border:2px solid #DC2626;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;">
            <h3 style="margin:0;color:#DC2626;"><i class="ti ti-alert-triangle"></i> Post-Mortem de Continuidad (BCP)</h3>
            <span class="badge" style="font-size:10px;background:rgba(220,38,38,.12);color:#DC2626;">ISO 22301</span>
          </div>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:14px;">
            Informe completo de gestion del incidente de continuidad: cronologia, impacto en el negocio, analisis de causa raiz, evidencias, efectividad de la respuesta y acciones correctivas.
          </p>
          <div id="bcp-pm-list" style="min-height:40px;">
            <p style="font-size:12px;color:var(--text-muted);">Cargando activaciones...</p>
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
                desc: 'Narrativa detallada por riesgo: acciones concretas, prioridades (inmediato/corto/medio/largo plazo), métricas de éxito y hoja de ruta de implementación en 3 fases.',
                icon: '📋',
                excel: true,
              },
              {
                id: 'executive_dashboard',
                title: 'Dashboard Ejecutivo',
                desc: 'Postura de riesgo para la Dirección: hallazgos clave, acciones críticas, análisis de KPIs, efectividad de controles y estado de cumplimiento ISO 27001.',
                icon: '📊',
                excel: true,
              },
              {
                id: 'committee_minutes',
                title: 'Acta de Comite de Seguridad',
                desc: 'Acta formal con orden del día, riesgos aceptados con justificación, decisiones adoptadas y acciones acordadas. Lista para que el Comité la firme.',
                icon: '🏛️',
                excel: true,
              },
              {
                id: 'followup_report',
                title: 'Informe de Seguimiento ISO 27005',
                desc: 'Evaluación del proceso según ISO 27005 cláusula 12: monitorización, revisión, mejora continua, tendencias, fortalezas/debilidades y recomendaciones.',
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
            estadísticas del registro y el contexto organizacional configurado.
          </div>
        </div>

      </div>`;
    // Async: populate BCP post-mortem list
    this._loadBcpActivations();
  },

  async _loadBcpActivations() {
    const wrap = document.getElementById('bcp-pm-list');
    if (!wrap) return;
    try {
      const closed = await Api.get('/api/bcp/activations?status=closed').catch(() => []);
      if (!closed.length) {
        wrap.innerHTML = '<p style="font-size:12px;color:var(--text-muted);">No hay activaciones cerradas. Los post-mortems se generan al cerrar un incidente de continuidad.</p>';
        return;
      }
      wrap.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;">` +
        closed.map(a => {
          const dur = a.closed_at && a.activated_at
            ? Math.round((new Date(a.closed_at) - new Date(a.activated_at)) / 60000) : null;
          return `<div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:14px;">
            <div style="font-size:11px;font-weight:700;color:#DC2626;margin-bottom:4px;">${UI.esc(a.code)}</div>
            <div style="font-size:13px;font-weight:600;margin-bottom:6px;line-height:1.3;">${UI.esc(a.title)}</div>
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:10px;">
              ${a.activated_at ? new Date(a.activated_at).toLocaleDateString('es-ES') : '-'}
              ${dur !== null ? ` · ${dur < 60 ? dur+'min' : Math.round(dur/60)+'h'}` : ''}
            </div>
            <button class="btn btn-sm" style="width:100%;background:#DC2626;color:#fff;border-color:#DC2626;font-size:12px;"
                    onclick="ViewReports._openBcpPostMortem(${a.id})">
              Ver post-mortem
            </button>
          </div>`;
        }).join('') + `</div>`;
    } catch (e) {
      wrap.innerHTML = `<p style="font-size:12px;color:var(--text-muted);">Error al cargar activaciones: ${UI.esc(e.message)}</p>`;
    }
  },

  _openBcpPostMortem(actId) {
    if (typeof ViewBcp !== 'undefined' && ViewBcp._openActivationReport) {
      ViewBcp._openActivationReport(actId);
    } else {
      // Navigate to BCP and open the report there
      if (typeof App !== 'undefined' && App.navigate) {
        App.navigate('bcp');
      } else {
        window.location.hash = '#bcp';
      }
      setTimeout(() => {
        if (typeof ViewBcp !== 'undefined' && ViewBcp._openActivationReport) {
          ViewBcp._openActivationReport(actId);
        }
      }, 500);
    }
  },

  _download(type) {
    const actions = {
      'sgsi-status': () => {
        UI.toast('Generando Informe del Estado del SGSI...', 'info');
        const today = new Date().toISOString().slice(0, 10);
        Api.download('/api/reports/sgsi-status', `sgsi_status_${today}.pdf`)
           .catch(e => UI.toast(e.message, 'error'));
      },
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
        const today = new Date().toISOString().slice(0,10);
        Api.download('/api/reports/soa', `SOA_${today}.pdf`)
           .catch(e => UI.toast(e.message, 'error'));
      },
      'rr-excel': () => {
        UI.toast('Generando Dashboard Ejecutivo Excel...', 'info');
        const today = new Date().toISOString().slice(0,10);
        Api.download('/api/reports/risk-register-excel', `dashboard_ejecutivo_${today}.xlsx`)
           .catch(e => UI.toast(e.message, 'error'));
      },
      'mgmt-review-pdf': () => {
        UI.toast('Generando Revision por la Direccion PDF...', 'info');
        Api.reports.managementReview('pdf').catch(e => UI.toast(e.message, 'error'));
      },
      'mgmt-review-excel': () => {
        UI.toast('Generando Revision por la Direccion Excel...', 'info');
        Api.reports.managementReview('excel').catch(e => UI.toast(e.message, 'error'));
      },
      'mgmt-review-word': () => {
        UI.toast('Generando Revision por la Direccion Word...', 'info');
        Api.reports.managementReview('word').catch(e => UI.toast(e.message, 'error'));
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
