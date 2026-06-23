/* Heatmap - matriz 5x5 ISO 27005 Annex E.2. */
const ViewHeatmap = {
  mode: 'residual',

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      t('heatmap.title'),
      t('heatmap.subtitle'),
      `<button class="btn" data-mode="inherent">${t('heatmap.inherent')}</button>
       <button class="btn btn-primary" data-mode="residual">${t('heatmap.residual')}</button>
       <button class="btn" data-mode="compare">${t('heatmap.compare')}</button>`
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
    wrap.innerHTML = UI.notice(t('common.loading'));
    try {
      if (ViewHeatmap.mode === 'compare') {
        await ViewHeatmap._drawCompare(wrap);
      } else {
        await ViewHeatmap._drawSingle(wrap, ViewHeatmap.mode);
      }
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  async _drawSingle(wrap, mode) {
    const data = await Api.risks.heatmap(mode);
    wrap.innerHTML = `
      <div style="display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap;">
        <div>
          <div class="heatmap-axis-y" style="margin-bottom:8px;">${t('heatmap.impact')}</div>
          <div class="heatmap" id="hm-grid-single">
            ${ViewHeatmap._rows(data.matrix)}
            <div class="corner"></div>
            ${[0,1,2,3,4].map(i => `<div class="col-label">${t(`heatmap.likelihood_${i}`)}</div>`).join('')}
          </div>
          <div style="margin-top:8px;text-align:center;" class="heatmap-axis-x">${t('heatmap.likelihood')}</div>
        </div>
        <div style="flex:1;min-width:280px;">
          <h3>${t('heatmap.how_to_read')}</h3>
          <p style="font-size:13px;color:var(--text-muted);">
            ${t('heatmap.how_to_read_body')}
          </p>
          <ul style="font-size:12px;color:var(--text-muted);padding-left:18px;">
            ${(window.RiskLevels ? RiskLevels.all() : [
              { label:'Bajo',  color:'var(--risk-low)',    min_level:0, max_level:2 },
              { label:'Medio', color:'var(--risk-medium)', min_level:3, max_level:5 },
              { label:'Alto',  color:'var(--risk-high)',   min_level:6, max_level:8 },
            ]).map((b, i, arr) => `<li><strong style="color:${b.color};">${b.label} (${b.min_level}-${b.max_level}):</strong> ${
              i === 0 ? t('heatmap.level_low_action') :
              i === arr.length - 1 ? t('heatmap.level_high_action') : t('heatmap.level_medium_action')
            }</li>`).join('')}
          </ul>
          <p style="font-size:12px;color:var(--text-subtle);margin-top:12px;">
            ${t('heatmap.click_cell')}
          </p>
        </div>
      </div>
      <div id="hm-detail" style="margin-top:24px;"></div>
    `;
    document.querySelectorAll('#hm-grid-single .cell').forEach(c => {
      c.onclick = () => ViewHeatmap._detail(
        parseInt(c.dataset.cons), parseInt(c.dataset.lik), data.matrix, 'hm-detail');
    });
  },

  async _drawCompare(wrap) {
    const [iData, rData] = await Promise.all([
      Api.risks.heatmap('inherent'),
      Api.risks.heatmap('residual'),
    ]);
    wrap.innerHTML = `
      <div style="margin-bottom:14px;">
        <p style="font-size:13px;color:var(--text-muted);margin:0;">${t('heatmap.compare_desc')}</p>
      </div>
      <div style="display:flex;gap:32px;align-items:flex-start;flex-wrap:wrap;overflow-x:auto;">
        <div style="flex-shrink:0;">
          <div style="font-weight:700;color:var(--brand-purple);font-size:14px;margin-bottom:6px;text-align:center;">
            ${t('heatmap.inherent')}
          </div>
          <div class="heatmap-axis-y" style="margin-bottom:8px;">${t('heatmap.impact')}</div>
          <div class="heatmap" id="hm-grid-inherent">
            ${ViewHeatmap._rows(iData.matrix)}
            <div class="corner"></div>
            ${[0,1,2,3,4].map(i => `<div class="col-label">${t(`heatmap.likelihood_${i}`)}</div>`).join('')}
          </div>
          <div style="margin-top:8px;text-align:center;" class="heatmap-axis-x">${t('heatmap.likelihood')}</div>
        </div>
        <div style="flex-shrink:0;">
          <div style="font-weight:700;color:var(--brand-purple);font-size:14px;margin-bottom:6px;text-align:center;">
            ${t('heatmap.residual')}
          </div>
          <div class="heatmap-axis-y" style="margin-bottom:8px;">${t('heatmap.impact')}</div>
          <div class="heatmap" id="hm-grid-residual">
            ${ViewHeatmap._rows(rData.matrix)}
            <div class="corner"></div>
            ${[0,1,2,3,4].map(i => `<div class="col-label">${t(`heatmap.likelihood_${i}`)}</div>`).join('')}
          </div>
          <div style="margin-top:8px;text-align:center;" class="heatmap-axis-x">${t('heatmap.likelihood')}</div>
        </div>
        <div style="flex:1;min-width:260px;">
          <h3>${t('heatmap.how_to_read')}</h3>
          <p style="font-size:13px;color:var(--text-muted);">
            ${t('heatmap.how_to_read_body')}
          </p>
          <ul style="font-size:12px;color:var(--text-muted);padding-left:18px;">
            ${(window.RiskLevels ? RiskLevels.all() : [
              { label:'Bajo',  color:'var(--risk-low)',    min_level:0, max_level:2 },
              { label:'Medio', color:'var(--risk-medium)', min_level:3, max_level:5 },
              { label:'Alto',  color:'var(--risk-high)',   min_level:6, max_level:8 },
            ]).map((b, i, arr) => `<li><strong style="color:${b.color};">${b.label} (${b.min_level}-${b.max_level}):</strong> ${
              i === 0 ? t('heatmap.level_low_action') :
              i === arr.length - 1 ? t('heatmap.level_high_action') : t('heatmap.level_medium_action')
            }</li>`).join('')}
          </ul>
          <p style="font-size:12px;color:var(--text-subtle);margin-top:12px;">
            ${t('heatmap.click_cell')}
          </p>
        </div>
      </div>
      <div id="hm-detail" style="margin-top:24px;"></div>
    `;
    document.querySelectorAll('#hm-grid-inherent .cell').forEach(c => {
      c.onclick = () => ViewHeatmap._detail(
        parseInt(c.dataset.cons), parseInt(c.dataset.lik), iData.matrix, 'hm-detail');
    });
    document.querySelectorAll('#hm-grid-residual .cell').forEach(c => {
      c.onclick = () => ViewHeatmap._detail(
        parseInt(c.dataset.cons), parseInt(c.dataset.lik), rData.matrix, 'hm-detail');
    });
  },

  _rows(matrix) {
    // matrix viene como filas top-down (consecuencia 4..0). columnas 0..4 probabilidad.
    const labelsY = [0,1,2,3,4].map(i => t(`heatmap.consequence_${i}`));
    let html = '';
    matrix.forEach((row, ri) => {
      html += `<div class="row-label">${labelsY[ri]}</div>`;
      row.forEach((cell, ci) => {
        const cons = 4 - ri;
        const lik = ci;
        const lvl = ViewHeatmap._lvl(cons, lik);
        html += `<div class="cell risk-pill-${lvl}" data-cons="${cons}" data-lik="${lik}">
          <div class="count">${cell.count}</div>
          <div class="level">L${lvl}</div>
        </div>`;
      });
    });
    return html;
  },

  _lvl(cons, lik) {
    const M = [[0,1,2,3,4],[1,2,3,4,5],[2,3,4,5,6],[3,4,5,6,7],[4,5,6,7,8]];
    return M[cons][lik];
  },

  _detail(cons, lik, matrix, detailId) {
    const ri = 4 - cons;
    const cell = matrix[ri][lik];
    const wrap = document.getElementById(detailId || 'hm-detail');
    if (!wrap) return;
    if (!cell.risks.length) {
      wrap.innerHTML = `<p style="color:var(--text-subtle);">${t('common.no_results')}</p>`;
      return;
    }
    wrap.innerHTML = `
      <h3>${t('heatmap.risks_in_cell')} (${t('heatmap.impact')} ${cons} / ${t('heatmap.likelihood')} ${lik})</h3>
      <div class="table-wrap"><table class="data">
        <thead><tr><th>${t('risks.risk_code')}</th><th>${t('common.asset')}</th><th>${t('common.threat')}</th><th>${t('common.level')}</th></tr></thead>
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
