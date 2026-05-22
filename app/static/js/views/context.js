/* Vista Contexto - ISO 27005 cl. 7. */
const ViewContext = {
  async render(main) {
    const isAdmin = Auth.isAdmin();
    main.innerHTML = UI.sectionHeader(
      'Contexto del SGSI',
      'Criterios, alcance y matriz de evaluacion (ISO 27005 cl. 7)'
    ) + '<div id="ctx-content">' + UI.notice('Cargando...') + '</div>';

    try {
      const ctx = await Api.context.get();
      const c = document.getElementById('ctx-content');
      c.innerHTML = `
        <div class="card">
          <h3>Datos generales</h3>
          <div class="modal-body">
            <div class="span2">
              <label>Organizacion</label>
              <input id="f-org" value="${UI.esc(ctx.organization_name||'')}" ${isAdmin?'':'disabled'}>
            </div>
            <div class="span2">
              <label>Alcance del SGSI</label>
              <textarea id="f-scope" rows="2" ${isAdmin?'':'disabled'}>${UI.esc(ctx.scope||'')}</textarea>
            </div>
            <div class="span2">
              <label>Limites (boundaries)</label>
              <textarea id="f-bounds" rows="2" ${isAdmin?'':'disabled'}>${UI.esc(ctx.boundaries||'')}</textarea>
            </div>
            <div>
              <label>Apetito de riesgo (nivel maximo aceptable 0-8)</label>
              <input type="number" min="0" max="8" id="f-appetite" value="${ctx.risk_appetite||3}" ${isAdmin?'':'disabled'}>
            </div>
          </div>
        </div>

        <div class="card" style="margin-top:16px;">
          <h3>Matriz de riesgo</h3>
          <p style="color:var(--text-muted);font-size:13px;">
            Matriz 5x5 de Consecuencia x Probabilidad segun ISO 27005 Annex E.2. Los valores
            son los niveles 0-8 que se aplican automaticamente al evaluar riesgos.
          </p>
          ${ViewContext._matrixHtml(ctx.risk_matrix)}
        </div>

        <div class="card" style="margin-top:16px;">
          <h3>Criterios de probabilidad</h3>
          <table class="data" style="margin-top:8px;">
            <thead><tr><th>Nivel</th><th>Descripcion</th></tr></thead>
            <tbody>
              ${Object.entries(ctx.likelihood_criteria||{}).map(([k, v]) =>
                `<tr><td><strong>${k}</strong></td><td>${UI.esc(v)}</td></tr>`).join('')}
            </tbody>
          </table>
        </div>

        <div class="card" style="margin-top:16px;">
          <h3>Criterios de impacto</h3>
          <p style="font-size:12px;color:var(--text-subtle);">
            Diferentes dimensiones del impacto (ISO 27005 7.2.3). Cualquier dimension con valor
            alto desencadena el nivel de consecuencia correspondiente.
          </p>
          ${Object.entries(ctx.impact_criteria||{}).map(([dim, levels]) => `
            <h4 style="margin-top:14px;text-transform:uppercase;font-size:11px;color:var(--text-muted);letter-spacing:0.06em;">${dim}</h4>
            <table class="data">
              <tbody>
                ${Object.entries(levels).map(([k, v]) =>
                  `<tr><td style="width:40px;"><strong>${k}</strong></td><td>${UI.esc(v)}</td></tr>`).join('')}
              </tbody>
            </table>
          `).join('')}
        </div>

        <div class="card" style="margin-top:16px;">
          <h3>Criterios de aceptacion</h3>
          ${(ctx.risk_acceptance_criteria?.rules || []).map(r =>
            `<p style="font-size:13px;color:var(--text-muted);padding-left:18px;border-left:3px solid var(--brand-orange);margin:8px 0;">${UI.esc(r)}</p>`).join('')}
        </div>

        ${isAdmin ? `
        <div style="margin-top:24px;text-align:right;">
          <button class="btn btn-primary" id="btn-save">Guardar cambios</button>
        </div>` : ''}
      `;

      if (isAdmin) document.getElementById('btn-save').onclick = async () => {
        try {
          await Api.context.update({
            organization_name: document.getElementById('f-org').value,
            scope: document.getElementById('f-scope').value,
            boundaries: document.getElementById('f-bounds').value,
            risk_appetite: parseInt(document.getElementById('f-appetite').value)||3,
          });
          UI.toast('Contexto actualizado', 'success');
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    } catch (e) {
      main.innerHTML += `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _matrixHtml(matrix) {
    if (!matrix) return '<p style="color:var(--text-subtle);">Matriz no configurada.</p>';
    const labelsX = ['M.improbable','Improbable','Posible','Probable','M.probable'];
    const labelsY = ['Critico','Mayor','Moderado','Menor','Insignificante'];
    let h = '<div style="overflow-x:auto;"><table class="data" style="max-width:520px;text-align:center;">';
    h += '<thead><tr><th></th>' + labelsX.map(l => `<th style="text-align:center;">${l}</th>`).join('') + '</tr></thead><tbody>';
    matrix.slice().reverse().forEach((row, ri) => {
      h += `<tr><th style="text-align:right;">${labelsY[ri]}</th>`;
      row.forEach(v => { h += `<td>${UI.riskPill(v)}</td>`; });
      h += '</tr>';
    });
    h += '</tbody></table></div>';
    return h;
  },
};
