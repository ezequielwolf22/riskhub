/* Vista MAGERIT v3 — valoración de activos y catálogo de amenazas. */
const ViewMagerit = (() => {

  const _DIM_COLORS = { D:'#1565c0', I:'#2e7d32', C:'#6A1B9A', A:'#c25a1f', T:'#555' };
  const _DIM_LABELS = { D:'Disponibilidad', I:'Integridad', C:'Confidencialidad', A:'Autenticidad', T:'Trazabilidad' };

  function _dimBar(dim, val) {
    const col = _DIM_COLORS[dim] || '#888';
    return `
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">
        <span style="width:14px;font-size:11px;font-weight:700;color:${col};">${dim}</span>
        <div style="flex:1;background:#eee;border-radius:3px;height:7px;overflow:hidden;">
          <div style="width:${val * 10}%;background:${col};height:100%;border-radius:3px;"></div>
        </div>
        <span style="width:14px;font-size:11px;color:#666;">${val}</span>
      </div>`;
  }

  function _originBadge(origin) {
    const m = { N:['#E3F2FD','#1565c0','Natural'], E:['#E8F5E9','#2e7d32','Error'], A:['#FEE2E2','#a83232','Ataque'] };
    const [bg, col, label] = m[origin] || ['#f5f5f5','#666','?'];
    return `<span style="background:${bg};color:${col};padding:2px 7px;border-radius:8px;font-size:10px;font-weight:600;">${label}</span>`;
  }

  async function render(el) {
    // Esta sección está integrada en Activos y Amenazas.
    // Redirigir automáticamente a Activos.
    App.navigate('assets');
    return;

    el.innerHTML = `
      <div style="max-width:1100px;margin:0 auto;padding:24px 0;">

        <!-- Banner de estado de la metodología -->
        <div style="padding:14px 18px;border-radius:10px;margin-bottom:20px;
             background:${isActive ? 'var(--brand-purple-4)' : 'var(--bg-2)'};
             border:1px solid ${isActive ? 'var(--brand-purple-3)' : 'var(--border)'};">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
            <div style="flex:1;">
              <strong style="font-size:14px;color:${isActive?'var(--brand-purple)':'var(--text-muted)'};">
                ${isActive ? t('magerit.active_banner') : t('magerit.inactive_banner')}
              </strong>
              <p style="margin:4px 0 0;font-size:12px;color:var(--text-muted);">
                ${isActive
                  ? t('magerit.active_hint')
                  : t('magerit.inactive_hint')}
              </p>
            </div>
            ${!isActive ? `
            <button class="btn btn-primary btn-sm" onclick="App.navigate('context')">
              Activar MAGERIT en Contexto
            </button>` : ''}
          </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:12px;">
          <div>
            <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0;">
              Análisis dimensional MAGERIT v3
            </h1>
            <p style="color:#9d9d9d;font-size:13px;margin:4px 0 0;">
              Valoración de activos por las 5 dimensiones de seguridad: D/I/C/A/T
            </p>
          </div>
          <div style="display:flex;gap:8px;">
            <button onclick="ViewMagerit._seedThreats()" class="btn-outline" style="font-size:13px;">
              Cargar amenazas MAGERIT
            </button>
            <button onclick="ViewMagerit._showAnalysis()" class="btn-primary" style="font-size:13px;">
              Análisis de activos
            </button>
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
          <!-- Dimensiones -->
          <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:18px;">
            <h2 style="font-size:14px;font-weight:700;color:var(--brand-purple);margin:0 0 12px;">Dimensiones de seguridad</h2>
            ${Object.entries(_DIM_LABELS).map(([k,v]) => `
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
                <span style="width:20px;height:20px;border-radius:50%;background:${_DIM_COLORS[k]};
                             color:#fff;font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;">${k}</span>
                <span style="font-size:13px;">${v}</span>
              </div>`).join('')}
          </div>
          <!-- Escala -->
          <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:18px;">
            <h2 style="font-size:14px;font-weight:700;color:var(--brand-purple);margin:0 0 12px;">Escala de valoración (1-10)</h2>
            ${[1,3,5,7,9].map(n => `
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                <span style="min-width:24px;font-size:13px;font-weight:700;color:var(--brand-purple);">${n}</span>
                <span style="font-size:12px;color:#555;">
                  ${n<=2?t('magerit.deg_very_low'):n<=4?t('magerit.deg_low_med'):n<=6?t('magerit.deg_high'):n<=8?t('magerit.deg_very_high'):t('magerit.deg_extreme')}
                </span>
              </div>`).join('')}
          </div>
        </div>

        <!-- Catálogo de amenazas -->
        <div id="magerit-threats" style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;overflow:hidden;">
          <div style="padding:16px 20px;border-bottom:1px solid #f0f0f0;display:flex;justify-content:space-between;">
            <h2 style="font-size:14px;font-weight:700;color:var(--brand-purple);margin:0;">
              Catálogo de amenazas MAGERIT v3
            </h2>
            <div style="display:flex;gap:8px;">
              <select id="magerit-filter-origin" class="input-field" style="font-size:12px;padding:3px 8px;"
                      onchange="ViewMagerit._filterThreats()">
                <option value="">Todos los orígenes</option>
                <option value="N">Desastres naturales</option>
                <option value="E">Errores no intencionados</option>
                <option value="A">Ataques deliberados</option>
              </select>
            </div>
          </div>
          <div id="magerit-threats-body">
            <div style="text-align:center;padding:32px;color:#9d9d9d;">Cargando...</div>
          </div>
        </div>

        <!-- Panel de análisis (oculto por defecto) -->
        <div id="magerit-analysis-panel" style="display:none;margin-top:16px;"></div>
      </div>`;

    await _loadThreats();
  }

  let _allThreats = [];

  async function _loadThreats() {
    const el = document.getElementById('magerit-threats-body');
    try {
      _allThreats = await Api.magerit.threats();
      _renderThreats(_allThreats);
    } catch (e) {
      el.innerHTML = `<div style="color:var(--risk-critical);padding:16px;">Error: ${UI.esc(e.message)}</div>`;
    }
  }

  function _renderThreats(threats) {
    const el = document.getElementById('magerit-threats-body');
    if (!threats.length) {
      el.innerHTML = `<div style="text-align:center;padding:32px;color:#9d9d9d;">
        ${t('ui_views.mag_no_threats')}</div>`;
      return;
    }
    const groups = {};
    threats.forEach(t => {
      const g = t.category || 'Otras';
      if (!groups[g]) groups[g] = [];
      groups[g].push(t);
    });
    el.innerHTML = Object.entries(groups).map(([cat, items]) => `
      <div style="border-bottom:1px solid #f0f0f0;">
        <div style="padding:8px 20px;background:#f9f9f9;font-size:11px;font-weight:700;
                    color:#666;text-transform:uppercase;letter-spacing:.5px;">${UI.esc(cat)}</div>
        ${items.map(t => `
          <div style="padding:10px 20px;border-bottom:1px solid #f5f5f5;display:flex;align-items:flex-start;gap:12px;">
            <div style="min-width:70px;">${_originBadge(t.origin)}</div>
            <div style="flex:1;">
              <div style="font-size:13px;font-weight:600;">${UI.esc(t.name)}
                <span style="font-size:11px;color:#9d9d9d;font-weight:400;margin-left:6px;">[${UI.esc(t.code)}]</span>
              </div>
              <div style="font-size:12px;color:#666;margin-top:2px;">${UI.esc(t.description || '')}</div>
              ${t.dimension ? `<div style="font-size:11px;color:var(--brand-purple);margin-top:2px;">
                Dimensiones: ${t.dimension.join(', ')}</div>` : ''}
            </div>
            <div style="min-width:120px;">
              <div style="font-size:11px;color:#9d9d9d;margin-bottom:2px;">Probabilidad: ${t.likelihood}/4</div>
              <div style="font-size:11px;color:#9d9d9d;">Consecuencia: ${t.consequence}/4</div>
            </div>
          </div>`).join('')}
      </div>`).join('');
  }

  function _filterThreats() {
    const origin = document.getElementById('magerit-filter-origin').value;
    const filtered = origin ? _allThreats.filter(t => t.origin === origin) : _allThreats;
    _renderThreats(filtered);
  }

  async function _seedThreats() {
    try {
      const r = await Api.magerit.seed();
      UI.toast(r.message || 'Amenazas cargadas', 'success');
      await _loadThreats();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _showAnalysis() {
    const panel = document.getElementById('magerit-analysis-panel');
    panel.style.display = 'block';
    panel.innerHTML = '<div style="text-align:center;padding:24px;color:#9d9d9d;">Calculando valoraciones...</div>';
    try {
      const data = await Api.magerit.analysis();
      const assets = data.asset_valuations || [];
      if (!assets.length) {
        panel.innerHTML = `<div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:24px;text-align:center;color:#9d9d9d;">
          No hay activos para valorar. Crea activos primero.</div>`;
        return;
      }
      panel.innerHTML = `
        <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;overflow:hidden;">
          <div style="padding:14px 20px;border-bottom:1px solid #f0f0f0;">
            <h2 style="font-size:14px;font-weight:700;color:var(--brand-purple);margin:0;">
              Valoración MAGERIT de activos (${assets.length})
            </h2>
          </div>
          ${assets.map(a => `
            <div style="padding:12px 20px;border-bottom:1px solid #f5f5f5;display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
              <div style="min-width:160px;">
                <div style="font-size:13px;font-weight:600;">${UI.esc(a.asset_name)}</div>
                <div style="font-size:11px;color:#9d9d9d;">${UI.esc(a.magerit_type)}</div>
              </div>
              <div style="flex:1;min-width:200px;">
                ${Object.entries(a.dimensions || {}).map(([d,v]) => _dimBar(d,v)).join('')}
              </div>
              <div style="min-width:60px;text-align:center;">
                <div style="font-size:22px;font-weight:800;color:${a.value_max >= 6 ? 'var(--risk-critical)' : a.value_max >= 4 ? 'var(--risk-high)' : 'var(--risk-low)'};">${a.value_max}</div>
                <div style="font-size:10px;color:#9d9d9d;">valor max</div>
              </div>
            </div>`).join('')}
        </div>`;
    } catch (e) {
      panel.innerHTML = `<div style="color:var(--risk-critical);padding:16px;">Error: ${UI.esc(e.message)}</div>`;
    }
  }

  return { render, _seedThreats, _showAnalysis, _filterThreats };
})();
