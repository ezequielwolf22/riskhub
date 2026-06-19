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

        <div class="card" style="margin-top:16px;" id="rl-card">
          <h3>Niveles de riesgo</h3>
          <p style="color:var(--text-muted);font-size:13px;margin-bottom:12px;">
            Configura las bandas de nivel de riesgo (etiquetas, colores y umbrales 0-8)
            para adaptar la terminología a tu organización.
          </p>
          <div id="rl-body">${UI.notice('Cargando...')}</div>
        </div>

        ${isAdmin ? `
        <div style="margin-top:24px;text-align:right;">
          <button class="btn btn-primary" id="btn-save">Guardar cambios</button>
        </div>` : ''}
      `;

      // Cargar y renderizar configuracion de niveles de riesgo
      ViewContext._loadRiskLevels(isAdmin);

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

  async _loadRiskLevels(isAdmin) {
    const container = document.getElementById('rl-body');
    if (!container) return;
    try {
      const bands = await Api.risk_levels.get();
      container.innerHTML = ViewContext._rlTableHtml(bands, isAdmin);
      if (isAdmin) ViewContext._rlBindEvents(container, bands);
    } catch (e) {
      container.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _rlTableHtml(bands, isAdmin) {
    const ro = isAdmin ? '' : 'disabled';
    const rows = bands.map((b, i) => `
      <tr data-rl-idx="${i}">
        <td style="width:32px;text-align:center;color:var(--text-muted);font-size:12px;">${b.order}</td>
        <td>
          <input class="rl-code" value="${UI.esc(b.code)}" ${ro} style="width:90px;font-size:12px;"
                 placeholder="low">
        </td>
        <td>
          <input class="rl-label" value="${UI.esc(b.label)}" ${ro} style="width:90px;font-size:12px;"
                 placeholder="Bajo">
        </td>
        <td style="display:flex;align-items:center;gap:6px;">
          <input class="rl-min" type="number" min="0" max="8" value="${b.min_level}" ${ro}
                 style="width:50px;font-size:12px;">
          <span style="color:var(--text-muted);">–</span>
          <input class="rl-max" type="number" min="0" max="8" value="${b.max_level}" ${ro}
                 style="width:50px;font-size:12px;">
        </td>
        <td>
          <div style="display:flex;align-items:center;gap:8px;">
            <span class="rl-swatch" style="display:inline-block;width:18px;height:18px;border-radius:4px;
                                          background:${b.color};border:1px solid var(--border);flex-shrink:0;"></span>
            <select class="rl-color" ${ro} style="font-size:12px;">
              ${[
                ['var(--risk-low)',      'Verde (Bajo)'],
                ['var(--risk-medium)',   'Naranja (Medio)'],
                ['var(--risk-high)',     'Rojo oscuro (Alto)'],
                ['var(--risk-critical)', 'Rojo critico'],
                ['var(--brand-purple)',  'Morado (brand)'],
              ].map(([v, l]) => `<option value="${v}" ${b.color === v ? 'selected' : ''}>${l}</option>`).join('')}
            </select>
          </div>
        </td>
        ${isAdmin ? `<td>
          <button class="btn btn-ghost btn-sm rl-del" title="Eliminar banda" data-rl-idx="${i}">&#10005;</button>
        </td>` : '<td></td>'}
      </tr>`).join('');
    return `
      <div style="overflow-x:auto;">
        <table class="data" style="min-width:560px;">
          <thead>
            <tr>
              <th style="width:32px;">#</th>
              <th>Codigo</th>
              <th>Etiqueta</th>
              <th>Rango (0-8)</th>
              <th>Color</th>
              <th style="width:40px;"></th>
            </tr>
          </thead>
          <tbody id="rl-tbody">${rows}</tbody>
        </table>
      </div>
      ${isAdmin ? `
      <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;">
        <button class="btn btn-ghost btn-sm" id="rl-add">+ Anadir banda</button>
        <button class="btn btn-primary btn-sm" id="rl-save">Guardar niveles</button>
        <button class="btn btn-ghost btn-sm" id="rl-reset" style="color:var(--text-muted);">
          Restablecer defaults
        </button>
      </div>` : ''}
    `;
  },

  _rlBindEvents(container, initialBands) {
    let bands = initialBands.map(b => ({ ...b }));

    const refresh = () => {
      const tbody = container.querySelector('#rl-tbody');
      if (!tbody) return;
      tbody.innerHTML = ViewContext._rlTableHtml(bands, true)
        .match(/<tbody id="rl-tbody">([\s\S]*?)<\/tbody>/)?.[1] || '';
      ViewContext._rlBindInlineEvents(container, bands, refresh);
    };

    ViewContext._rlBindInlineEvents(container, bands, refresh);

    container.querySelector('#rl-add')?.addEventListener('click', () => {
      bands.push({
        code: 'nuevo', label: 'Nuevo', min_level: 0, max_level: 0,
        color: 'var(--risk-medium)', order: bands.length + 1,
      });
      refresh();
    });

    container.querySelector('#rl-save')?.addEventListener('click', async () => {
      const updated = ViewContext._rlReadFromDom(container, bands);
      if (!updated) return;
      try {
        const saved = await Api.risk_levels.put(updated);
        await RiskLevels.load();
        UI.toast('Niveles de riesgo guardados', 'success');
        bands = saved;
        refresh();
      } catch (e) {
        UI.toast(e.message, 'error');
      }
    });

    container.querySelector('#rl-reset')?.addEventListener('click', async () => {
      if (!confirm('¿Restablecer los niveles de riesgo a los valores por defecto?')) return;
      try {
        await Api.risk_levels.reset();
        await RiskLevels.load();
        UI.toast('Niveles de riesgo restablecidos', 'success');
        const defaults = await Api.risk_levels.get();
        bands = defaults;
        container.innerHTML = ViewContext._rlTableHtml(defaults, true);
        ViewContext._rlBindEvents(container, defaults);
      } catch (e) {
        UI.toast(e.message, 'error');
      }
    });
  },

  _rlBindInlineEvents(container, bands, refresh) {
    container.querySelectorAll('.rl-del').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.dataset.rlIdx);
        bands.splice(idx, 1);
        bands.forEach((b, i) => { b.order = i + 1; });
        refresh();
      });
    });
    container.querySelectorAll('.rl-color').forEach((sel, i) => {
      sel.addEventListener('change', () => {
        const swatch = sel.closest('td').querySelector('.rl-swatch');
        if (swatch) swatch.style.background = sel.value;
      });
    });
  },

  _rlReadFromDom(container, bands) {
    const rows = container.querySelectorAll('#rl-tbody tr[data-rl-idx]');
    const updated = [];
    let valid = true;
    rows.forEach((tr, i) => {
      const code  = tr.querySelector('.rl-code')?.value?.trim();
      const label = tr.querySelector('.rl-label')?.value?.trim();
      const min   = parseInt(tr.querySelector('.rl-min')?.value);
      const max   = parseInt(tr.querySelector('.rl-max')?.value);
      const color = tr.querySelector('.rl-color')?.value;
      if (!code || !label || isNaN(min) || isNaN(max) || !color) {
        UI.toast('Rellena todos los campos de cada banda', 'error');
        valid = false;
        return;
      }
      if (min > max) {
        UI.toast(`Banda "${label}": el minimo no puede ser mayor que el maximo`, 'error');
        valid = false;
        return;
      }
      updated.push({ code, label, min_level: min, max_level: max, color, order: i + 1 });
    });
    return valid ? updated : null;
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
