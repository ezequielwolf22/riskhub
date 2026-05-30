/* Vista Contexto - ISO 27005 cl. 7. */
const ViewContext = {
  async render(main) {
    const isAdmin = Auth.isAdmin();
    main.innerHTML = UI.sectionHeader(
      'Contexto del SGSI',
      'Criterios, alcance y matriz de evaluación (ISO 27005 cl. 7)'
    ) + '<div id="ctx-content">' + UI.notice('Cargando...') + '</div>';

    try {
      const ctx = await Api.context.get();
      const c = document.getElementById('ctx-content');

      const likLabels = ['Muy improbable', 'Improbable', 'Posible', 'Probable', 'Muy probable'];
      const consLabels = ['Insignificante', 'Menor', 'Moderado', 'Mayor', 'Crítico'];
      const impactDims = ['financial', 'operational', 'reputational', 'regulatory', 'safety'];
      const impactNames = {
        financial: 'Financiero', operational: 'Operacional',
        reputational: 'Reputacional', regulatory: 'Regulatorio', safety: 'Seguridad personal'
      };

      const lik = ctx.likelihood_criteria || {};
      const imp = ctx.impact_criteria || {};
      const acc = ctx.risk_acceptance_criteria || {};
      const rules = (acc.rules || []).join('\n');

      const ro = isAdmin ? '' : 'disabled';
      const roArea = isAdmin ? '' : 'readonly';

      c.innerHTML = `
        <div class="card">
          <h3>Datos generales</h3>
          <div class="modal-body">
            <div class="span2">
              <label>Organización</label>
              <input id="f-org" value="${UI.esc(ctx.organization_name || '')}" ${ro}>
            </div>
            <div class="span2">
              <label>Alcance del SGSI</label>
              <textarea id="f-scope" rows="2" ${roArea}>${UI.esc(ctx.scope || '')}</textarea>
            </div>
            <div class="span2">
              <label>Límites (boundaries)</label>
              <textarea id="f-bounds" rows="2" ${roArea}>${UI.esc(ctx.boundaries || '')}</textarea>
            </div>
            <div>
              <label>Apetito de riesgo — nivel máximo aceptable (0-8)</label>
              <input type="number" min="0" max="8" id="f-appetite" value="${ctx.risk_appetite ?? 3}" ${ro}>
            </div>
            <div class="span2">
              <label>Metodología de análisis de riesgos</label>
              ${!ro ? `
              <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:4px;">
                ${[
                  {v:'iso27005', label:'ISO 27005', desc:'Consecuencia (0-4) y probabilidad (0-4) introducidas manualmente por el analista.'},
                  {v:'magerit',  label:'MAGERIT v3', desc:'Consecuencia calculada desde las 5 dimensiones DIACAT del activo × degradación. Probabilidad en escala de frecuencia MAGERIT.'},
                  {v:'combined', label:'Combinada', desc:'MAGERIT para la consecuencia (auto-calculada) + probabilidad manual ISO 27005.'},
                ].map(m => `
                  <label id="meth-lbl-${m.v}" style="cursor:pointer;border:2px solid ${(ctx.methodology||'iso27005')===m.v?'var(--brand-purple)':'var(--border)'};
                         background:${(ctx.methodology||'iso27005')===m.v?'var(--brand-purple-4)':'var(--bg-2)'};
                         border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:4px;transition:.15s;">
                    <div style="display:flex;align-items:center;gap:8px;">
                      <input type="radio" name="methodology" value="${m.v}" ${(ctx.methodology||'iso27005')===m.v?'checked':''}
                             style="accent-color:var(--brand-purple);"
                             onchange="ViewContext._highlightMeth('${m.v}')">
                      <strong style="font-size:13px;">${m.label}</strong>
                    </div>
                    <span style="font-size:11px;color:var(--text-muted);line-height:1.4;">${m.desc}</span>
                  </label>`).join('')}
              </div>` : `
              <div style="font-size:13px;padding:10px;background:var(--bg-2);border-radius:8px;">
                <strong>${{'iso27005':'ISO 27005','magerit':'MAGERIT v3','combined':'Combinada'}[ctx.methodology||'iso27005']}</strong>
              </div>`}
            </div>
          </div>
        </div>

        <div class="card" style="margin-top:16px;">
          <h3>Criterios de probabilidad</h3>
          <p style="color:var(--text-muted);font-size:13px;margin-bottom:12px;">
            Definición de cada nivel de probabilidad (0 = más improbable, 4 = más probable).
          </p>
          <table class="data">
            <thead><tr><th style="width:140px;">Nivel</th><th>Descripción</th></tr></thead>
            <tbody>
              ${[0,1,2,3,4].map(i => `
                <tr>
                  <td><strong>${i} &ndash; ${likLabels[i]}</strong></td>
                  <td><input id="f-lik-${i}" value="${UI.esc((lik[i] ?? lik[String(i)]) || '')}" style="width:100%;" ${ro}></td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>

        <div class="card" style="margin-top:16px;">
          <h3>Criterios de impacto</h3>
          <p style="color:var(--text-muted);font-size:13px;margin-bottom:12px;">
            Descripción de cada nivel de consecuencia por dimensión (ISO 27005 § 7.2.3).
            El nivel de consecuencia final es el máximo entre todas las dimensiones.
          </p>
          ${impactDims.map(dim => {
            const levels = imp[dim] || {};
            return `
            <h4 style="margin-top:16px;margin-bottom:8px;font-size:12px;text-transform:uppercase;
                       letter-spacing:.06em;color:var(--text-muted);">${impactNames[dim]}</h4>
            <table class="data">
              <thead><tr><th style="width:140px;">Nivel</th><th>Descripción</th></tr></thead>
              <tbody>
                ${[0,1,2,3,4].map(i => `
                  <tr>
                    <td><strong>${i} &ndash; ${consLabels[i]}</strong></td>
                    <td><input id="f-imp-${dim}-${i}" value="${UI.esc((levels[i] ?? levels[String(i)]) || '')}" style="width:100%;" ${ro}></td>
                  </tr>`).join('')}
              </tbody>
            </table>`;
          }).join('')}
        </div>

        <div class="card" style="margin-top:16px;">
          <h3>Criterios de aceptación</h3>
          <p style="color:var(--text-muted);font-size:13px;margin-bottom:12px;">
            Reglas que determinan cuándo un riesgo puede aceptarse sin tratamiento adicional.
            Escribe una regla por línea.
          </p>
          <div>
            <label>Nivel máximo aceptable sin aprobación (0-8)</label>
            <input type="number" min="0" max="8" id="f-acc-appetite" value="${acc.appetite_max_level ?? 3}" ${ro} style="max-width:100px;">
          </div>
          <div style="margin-top:12px;">
            <label>Reglas (una por línea)</label>
            <textarea id="f-acc-rules" rows="6" style="width:100%;font-size:13px;" ${roArea}>${UI.esc(rules)}</textarea>
          </div>
        </div>

        <div class="card" style="margin-top:16px;">
          <h3>Matriz de riesgo</h3>
          <p style="color:var(--text-muted);font-size:13px;">
            Matriz 5×5 Consecuencia × Probabilidad según ISO 27005 Annex E.2.
          </p>
          ${ViewContext._matrixHtml(ctx.risk_matrix)}
        </div>

        ${isAdmin ? `
        <div style="margin-top:24px;text-align:right;">
          <button class="btn btn-primary" id="btn-save">Guardar cambios</button>
        </div>` : ''}
      `;

      if (isAdmin) {
        document.getElementById('btn-save').onclick = async () => {
          try {
            const likCriteria = {};
            [0,1,2,3,4].forEach(i => {
              likCriteria[i] = document.getElementById(`f-lik-${i}`).value;
            });

            const impCriteria = {};
            impactDims.forEach(dim => {
              impCriteria[dim] = {};
              [0,1,2,3,4].forEach(i => {
                impCriteria[dim][i] = document.getElementById(`f-imp-${dim}-${i}`).value;
              });
            });

            const rulesText = document.getElementById('f-acc-rules').value;
            const accCriteria = {
              appetite_max_level: parseInt(document.getElementById('f-acc-appetite').value) || 3,
              rules: rulesText.split('\n').map(r => r.trim()).filter(r => r.length > 0),
            };

            const methEl = document.querySelector('input[name="methodology"]:checked');
            await Api.context.update({
              organization_name: document.getElementById('f-org').value,
              scope: document.getElementById('f-scope').value,
              boundaries: document.getElementById('f-bounds').value,
              risk_appetite: parseInt(document.getElementById('f-appetite').value) || 3,
              methodology: methEl ? methEl.value : 'iso27005',
              likelihood_criteria: likCriteria,
              impact_criteria: impCriteria,
              risk_acceptance_criteria: accCriteria,
            });
            // Notificar a otros módulos del cambio de metodología
            window._riskMethodology = methEl ? methEl.value : 'iso27005';
            UI.toast('Contexto actualizado', 'success');
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      }
    } catch (e) {
      document.getElementById('ctx-content').innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _highlightMeth(val) {
    ['iso27005','magerit','combined'].forEach(v => {
      const lbl = document.getElementById(`meth-lbl-${v}`);
      if (!lbl) return;
      lbl.style.borderColor = v === val ? 'var(--brand-purple)' : 'var(--border)';
      lbl.style.background  = v === val ? 'var(--brand-purple-4)' : 'var(--bg-2)';
    });
  },

  _matrixHtml(matrix) {
    if (!matrix) return '<p style="color:var(--text-subtle);">Matriz no configurada.</p>';
    const labelsX = ['M.improbable','Improbable','Posible','Probable','M.probable'];
    const labelsY = ['Crítico','Mayor','Moderado','Menor','Insignificante'];
    let h = '<div style="overflow-x:auto;"><table class="data" style="max-width:540px;text-align:center;">';
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
