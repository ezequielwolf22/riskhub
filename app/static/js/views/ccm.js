/* Vista de Continuous Control Monitoring. */
const ViewCcm = (() => {

  function _statusBadge(status) {
    const m = {
      PASS:    ['#E8F5E9','#2e7d32','✓'],
      FAIL:    ['#FEE2E2','#a83232','✗'],
      WARNING: ['#FEF0E3','#c25a1f','⚠'],
      SKIP:    ['#f5f5f5','#9d9d9d','—'],
    };
    const [bg, col, icon] = m[status] || ['#f5f5f5','#9d9d9d','?'];
    return `<span style="background:${bg};color:${col};padding:3px 10px;border-radius:12px;
                         font-size:11px;font-weight:700;">${icon} ${status}</span>`;
  }

  function _scoreGauge(score) {
    const col = score >= 80 ? 'var(--risk-low)' : score >= 60 ? 'var(--risk-medium)' : 'var(--risk-critical)';
    return `
      <div style="text-align:center;">
        <div style="font-size:52px;font-weight:800;color:${col};line-height:1;">${score}</div>
        <div style="font-size:14px;color:#9d9d9d;">/ 100</div>
        <div style="background:#eee;border-radius:8px;height:12px;margin:12px 0 0;overflow:hidden;">
          <div style="width:${score}%;background:${col};height:100%;border-radius:8px;transition:width .5s;"></div>
        </div>
      </div>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div style="max-width:1100px;margin:0 auto;padding:24px 0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:12px;">
          <div>
            <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0;">
              Monitorización Continua de Controles
            </h1>
            <p style="color:#9d9d9d;font-size:13px;margin:4px 0 0;">
              Tests automáticos sobre el estado real de los controles del SGSI
            </p>
          </div>
          <button onclick="ViewCcm._runTests()" class="btn-primary" id="ccm-run-btn">
            Ejecutar tests
          </button>
        </div>
        <div id="ccm-content">
          <div style="text-align:center;padding:60px;color:#9d9d9d;">
            Pulsa "Ejecutar tests" para analizar el estado de los controles
          </div>
        </div>
      </div>`;
  }

  async function _runTests() {
    const btn = document.getElementById('ccm-run-btn');
    const el = document.getElementById('ccm-content');
    if (btn) btn.disabled = true;
    el.innerHTML = `<div style="text-align:center;padding:60px;color:#9d9d9d;">Ejecutando tests...</div>`;

    try {
      const data = await Api.post('/api/ccm/run', {});
      _renderResults(el, data);
    } catch (e) {
      el.innerHTML = `<div style="color:var(--risk-critical);padding:24px;">Error: ${UI.esc(e.message)}</div>`;
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function _renderResults(el, data) {
    const results = data.results || [];
    const counts = data.counts || {};
    const fails = results.filter(r => r.status === 'FAIL');
    const warnings = results.filter(r => r.status === 'WARNING');
    const passes = results.filter(r => r.status === 'PASS');

    el.innerHTML = `
      <!-- Score + resumen -->
      <div style="display:grid;grid-template-columns:200px 1fr;gap:16px;margin-bottom:16px;">
        <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:24px;">
          ${_scoreGauge(data.score || 0)}
          <div style="text-align:center;margin-top:12px;font-size:12px;color:#666;">
            CCM Score
          </div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">
          ${[['PASS', counts.PASS||0,'#E8F5E9','#2e7d32'],
             ['WARNING', counts.WARNING||0,'#FEF0E3','#c25a1f'],
             ['FAIL', counts.FAIL||0,'#FEE2E2','#a83232'],
             ['SKIP', counts.SKIP||0,'#f5f5f5','#9d9d9d'],
            ].map(([s,n,bg,col]) => `
            <div style="background:${bg};border-radius:8px;padding:16px;text-align:center;">
              <div style="font-size:28px;font-weight:700;color:${col};">${n}</div>
              <div style="font-size:11px;color:${col};text-transform:uppercase;">${s}</div>
            </div>`).join('')}
        </div>
      </div>

      <!-- FAILs primero -->
      ${fails.length ? `
      <section style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;
                      margin-bottom:16px;overflow:hidden;">
        <div style="background:#FEE2E2;padding:12px 16px;border-bottom:1px solid #f5c6c6;">
          <strong style="color:#a83232;">✗ ${fails.length} control(es) fallando — requieren acción</strong>
        </div>
        ${fails.map(r => _testRow(r)).join('')}
      </section>` : ''}

      <!-- WARNINGs -->
      ${warnings.length ? `
      <section style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;
                      margin-bottom:16px;overflow:hidden;">
        <div style="background:#FEF0E3;padding:12px 16px;border-bottom:1px solid #f5ddb4;">
          <strong style="color:#c25a1f;">⚠ ${warnings.length} control(es) con advertencias</strong>
        </div>
        ${warnings.map(r => _testRow(r)).join('')}
      </section>` : ''}

      <!-- PASSes -->
      <section style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;overflow:hidden;">
        <div style="background:#E8F5E9;padding:12px 16px;border-bottom:1px solid #c8e6c9;">
          <strong style="color:#2e7d32;">✓ ${passes.length} control(es) verificados correctamente</strong>
        </div>
        ${passes.map(r => _testRow(r)).join('')}
      </section>

      <div style="margin-top:12px;font-size:12px;color:#9d9d9d;text-align:right;">
        Ejecutado: ${data.timestamp ? data.timestamp.slice(0,16).replace('T',' ') : '—'} UTC
      </div>`;
  }

  function _testRow(r) {
    return `
      <div style="padding:12px 16px;border-bottom:1px solid #f5f5f5;display:flex;
                  justify-content:space-between;align-items:flex-start;gap:12px;">
        <div style="flex:1;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <span style="font-size:11px;font-weight:700;color:var(--brand-purple);
                         background:#f0e8f8;padding:2px 6px;border-radius:4px;">${UI.esc(r.control_code)}</span>
            <span style="font-size:13px;font-weight:600;">${UI.esc(r.name)}</span>
          </div>
          <div style="font-size:12px;color:#666;">${UI.esc(r.detail)}</div>
          ${r.recommendation ? `<div style="font-size:12px;color:var(--brand-orange);margin-top:4px;">
            → ${UI.esc(r.recommendation)}</div>` : ''}
        </div>
        <div style="flex-shrink:0;">${_statusBadge(r.status)}</div>
      </div>`;
  }

  return { render, _runTests };
})();
