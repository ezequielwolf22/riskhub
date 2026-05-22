/* Vista Informes - descarga de PDFs con branding. */
const ViewReports = {
  render(main) {
    main.innerHTML = UI.sectionHeader(
      'Informes',
      'Generacion de documentos para auditoria, comites y direccion'
    ) + `
      <div class="card-row">
        <div class="card">
          <h3>Risk Register</h3>
          <p style="color:var(--text-muted);font-size:13px;">
            Listado completo de riesgos registrados ordenados por nivel residual.
            Incluye activo, amenaza, niveles inherente y residual, estado y decision
            de tratamiento. Formato ISO/IEC 27005:2018.
          </p>
          <button class="btn btn-primary" id="btn-rr">Descargar PDF</button>
        </div>
        <div class="card">
          <h3>Statement of Applicability (SoA)</h3>
          <p style="color:var(--text-muted);font-size:13px;">
            Declaracion de aplicabilidad de los 93 controles del Anexo A de
            ISO/IEC 27002:2022, con estado y madurez de cada implementacion.
            Documento obligatorio para certificacion ISO/IEC 27001.
          </p>
          <button class="btn btn-primary" id="btn-soa">Descargar PDF</button>
        </div>
      </div>
      <div class="card" style="margin-top:16px;">
        <h3>Proximos informes (roadmap)</h3>
        <ul style="color:var(--text-muted);font-size:13px;padding-left:18px;">
          <li>Risk Treatment Plan detallado por riesgo.</li>
          <li>Acta de Comite de Seguridad con riesgos aceptados.</li>
          <li>Dashboard ejecutivo (PDF) con KPIs y heatmap.</li>
          <li>Export a Excel del Risk Register completo.</li>
          <li>Informe de seguimiento periodico (ISO 27005 cl. 12).</li>
        </ul>
      </div>
    `;
    document.getElementById('btn-rr').onclick = () => {
      UI.toast('Generando PDF...', 'info');
      Api.reports.riskRegister().catch(e => UI.toast(e.message, 'error'));
    };
    document.getElementById('btn-soa').onclick = () => {
      UI.toast('Generando PDF...', 'info');
      Api.reports.soa().catch(e => UI.toast(e.message, 'error'));
    };
  },
};
