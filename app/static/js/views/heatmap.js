/* Heatmap - matriz 5x5 ISO 27005 Annex E.2. */
const ViewHeatmap = {
  mode: 'residual',

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      'Mapa de calor',
      'Distribución de riesgos en la matriz Impacto x Probabilidad (ISO 27005 Annex E.2)',
      `<button class="btn" data-mode="inherent">Inherente</button>
       <button class="btn btn-primary" data-mode="residual">Residual</button>`
    );

    main.insertAdjacentHTML('beforeend', '<div id="hm-wrap" class="card"></div>');

    document.querySelectorAll('.section-header [data-mode]').forEach(b => {
      b.onclick = () => {
        ViewHeatmap.mode = b.dataset.mode;
        document.querySelectorAll('.section-header [data-mode]').forEach(x =>
          x.classList.toggle('btn-primary', x.dataset.mode === ViewHeatmap.mode));
        ViewHeatmap._draw();
      };
    });

    ViewHeatmap._draw();
  },

  async _draw() {
    const wrap = document.getElementById('hm-wrap');
    wrap.innerHTML = UI.notice('Cargando heatmap...');
    try {
      const data = await Api.risks.heatmap(ViewHeatmap.mode);
      wrap.innerHTML = `
        <div style="display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap;">
          <div>
            <div class="heatmap-axis-y" style="margin-bottom:8px;">Consecuencia</div>
            <div class="heatmap">
              ${ViewHeatmap._rows(data.matrix)}
              <div class="corner"></div>
              ${['Muy improbable','Improbable','Posible','Probable','Muy probable']
                .map(l => `<div class="col-label">${l}</div>`).join('')}
            </div>
            <div style="margin-top:8px;text-align:center;" class="heatmap-axis-x">Probabilidad</div>
          </div>
          <div style="flex:1;min-width:280px;">
            <h3>Como leer la matriz</h3>
            <p style="font-size:13px;color:var(--text-muted);">
              El nivel resultante (0 a 8) se obtiene cruzando consecuencia x probabilidad
              segun la Tabla E.2 de ISO/IEC 27005:2018.
            </p>
            <ul style="font-size:12px;color:var(--text-muted);padding-left:18px;">
              <li><strong style="color:var(--risk-low);">Bajo (0-2):</strong> retención sin tratamiento adicional.</li>
              <li><strong style="color:var(--risk-medium);">Medio (3-5):</strong> tratamiento recomendado.</li>
              <li><strong style="color:var(--risk-high);">Alto (6-8):</strong> tratamiento obligatorio.</li>
            </ul>
            <p style="font-size:12px;color:var(--text-subtle);margin-top:12px;">
              Click sobre una celda para listar los riesgos contenidos.
            </p>
          </div>
        </div>
        <div id="hm-detail" style="margin-top:24px;"></div>
      `;
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _rows(matrix) {
    // matrix viene como filas top-down (consecuencia 4..0). columnas 0..4 probabilidad.
    const labelsY = ['Critico','Mayor','Moderado','Menor','Insignificante'];
    let html = '';
    matrix.forEach((row, ri) => {
      html += `<div class="row-label">${labelsY[ri]}</div>`;
      row.forEach((cell, ci) => {
        // Calcular nivel real: filas matrix[0]=consequence4, filas matrix[4]=consequence0
        const cons = 4 - ri;
        const lik = ci;
        const lvl = ViewHeatmap._lvl(cons, lik);
        html += `<div class="cell risk-pill-${lvl}" data-cons="${cons}" data-lik="${lik}">
          <div class="count">${cell.count}</div>
          <div class="level">L${lvl}</div>
        </div>`;
      });
    });
    setTimeout(() => {
      document.querySelectorAll('.heatmap .cell').forEach(c => {
        c.onclick = () => ViewHeatmap._detail(
          parseInt(c.dataset.cons), parseInt(c.dataset.lik), matrix);
      });
    }, 0);
    return html;
  },

  _lvl(cons, lik) {
    const M = [[0,1,2,3,4],[1,2,3,4,5],[2,3,4,5,6],[3,4,5,6,7],[4,5,6,7,8]];
    return M[cons][lik];
  },

  _detail(cons, lik, matrix) {
    const ri = 4 - cons;
    const cell = matrix[ri][lik];
    const wrap = document.getElementById('hm-detail');
    if (!cell.risks.length) {
      wrap.innerHTML = '<p style="color:var(--text-subtle);">No hay riesgos en esa celda.</p>';
      return;
    }
    wrap.innerHTML = `
      <h3>Riesgos en consecuencia ${cons} / probabilidad ${lik} (nivel ${ViewHeatmap._lvl(cons, lik)})</h3>
      <div class="table-wrap"><table class="data">
        <thead><tr><th>Codigo</th><th>Activo</th><th>Amenaza</th><th>Nivel</th></tr></thead>
        <tbody>
          ${cell.risks.map(r => `
            <tr style="cursor:pointer;" onclick="location.hash='#/risks?id=${r.id}'">
              <td>${UI.codePill(r.code)}</td>
              <td>${UI.esc(r.asset)}</td>
              <td>${UI.esc(r.threat)}</td>
              <td>${UI.riskPill(r.level)}</td>
            </tr>`).join('')}
        </tbody>
      </table></div>
    `;
  },
};
