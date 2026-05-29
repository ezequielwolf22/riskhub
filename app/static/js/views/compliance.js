/* Vista de dashboard de cumplimiento multi-framework. */
const ViewCompliance = (() => {

  // Estado de panel expandido por framework key
  let _expandedPanel = null;
  // Cache de datos de compliance para los paneles
  let _compData = null;
  // Cache de controles implementados para los paneles ISO/NIST/ENS
  let _implsData = null;

  function _scoreColor(score) {
    if (score >= 75) return 'var(--risk-low)';
    if (score >= 50) return 'var(--risk-medium)';
    if (score >= 25) return 'var(--risk-high)';
    return 'var(--risk-critical)';
  }

  function _scoreLabel(score) {
    if (score >= 75) return 'Conforme';
    if (score >= 50) return 'Parcial';
    if (score >= 25) return 'Deficiente';
    return 'Critico';
  }

  function _gaugeHtml(label, score, sublabel, frameworkKey) {
    const color = _scoreColor(score);
    const pct = Math.min(100, Math.max(0, score));
    const isExpanded = _expandedPanel === frameworkKey;
    return `
      <div class="stat-card" style="flex:1;min-width:200px;text-align:center;padding:20px 16px;
           cursor:pointer;border:2px solid ${isExpanded ? 'var(--brand-purple)' : 'transparent'};
           transition:border .2s,box-shadow .2s;"
           onmouseover="this.style.boxShadow='0 0 0 2px var(--brand-purple-4)'"
           onmouseout="this.style.boxShadow=''"
           onclick="ViewCompliance._togglePanel('${frameworkKey}')"
           title="Clic para ver detalle de ${UI.esc(label)}">
        <div style="font-size:12px;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:8px;">${UI.esc(label)}</div>
        <div style="position:relative;width:100px;height:100px;margin:0 auto 8px;">
          <svg viewBox="0 0 36 36" style="width:100px;height:100px;">
            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none" stroke="var(--border)" stroke-width="3.5"/>
            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none" stroke="${color}" stroke-width="3.5"
              stroke-dasharray="${pct}, 100" stroke-linecap="round"/>
          </svg>
          <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;">
            <div style="font-size:22px;font-weight:800;color:${color};">${pct}</div>
            <div style="font-size:10px;color:var(--text-muted);">/ 100</div>
          </div>
        </div>
        <div style="font-size:13px;font-weight:600;color:${color};">${_scoreLabel(pct)}</div>
        ${sublabel ? `<div style="font-size:11px;color:var(--text-muted);margin-top:4px;">${UI.esc(sublabel)}</div>` : ''}
        <div style="font-size:11px;color:var(--brand-purple);margin-top:8px;">
          ${isExpanded
            ? `<span>&#9650; Ocultar detalle</span>`
            : `<span>&#9660; Ver detalle</span>`}
        </div>
      </div>
    `;
  }

  function _gapsHtml(gaps) {
    if (!gaps || !gaps.length) {
      return '<p style="color:var(--risk-low);font-size:13px;">Sin brechas identificadas.</p>';
    }
    return gaps.map(g => `
      <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:8px;">
        <span style="color:var(--risk-high);font-size:14px;margin-top:2px;">&#9679;</span>
        <span style="font-size:13px;">${UI.esc(g)}</span>
      </div>
    `).join('');
  }

  function _nistFunctionsHtml(fns) {
    if (!fns) return '';
    const fnColors = {
      GOVERN: '#7C3AED', IDENTIFY: '#2563EB', PROTECT: '#059669',
      DETECT: '#D97706', RESPOND: '#DC2626', RECOVER: '#0891B2',
    };
    const bars = Object.entries(fns).map(([fn, score]) => {
      const color = fnColors[fn] || 'var(--brand-purple)';
      return `
        <div style="margin-bottom:10px;">
          <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
            <span style="font-weight:600;color:${color};">${UI.esc(fn)}</span>
            <span style="color:var(--text-muted);">${score}%</span>
          </div>
          <div style="background:var(--border);border-radius:999px;height:8px;overflow:hidden;">
            <div style="width:${score}%;background:${color};height:100%;border-radius:999px;transition:width .4s;"></div>
          </div>
        </div>
      `;
    }).join('');
    return `<div style="margin-top:12px;">${bars}</div>`;
  }

  // Normaliza un impl (puede tener control anidado) a un objeto plano con code/name/theme
  function _flatImpl(i) {
    return {
      id: i.id,
      code:    i.control?.code   || i.code    || '',
      name:    i.control?.name   || i.name    || '',
      theme:   i.control?.theme  || i.theme   || '',
      status:  i.status,
      maturity: i.maturity || 0,
      notes:   i.notes || '',
      description: i.description || '',
    };
  }

  // ============================================================
  // Panel de detalle por framework
  // ============================================================

  function _togglePanel(key) {
    if (_expandedPanel === key) {
      _expandedPanel = null;
    } else {
      _expandedPanel = key;
    }
    _rerenderGaugesAndPanels();
  }

  function _rerenderGaugesAndPanels() {
    if (!_compData) return;
    const gaugesEl = document.getElementById('comp-gauges');
    const panelEl = document.getElementById('comp-detail-panel');
    if (!gaugesEl || !panelEl) return;

    const data = _compData;
    const nist = data.nist_csf || {};

    gaugesEl.innerHTML = `
      ${_gaugeHtml('ISO 27001:2022', data.iso27001?.score || 0, data.iso27001?.label, 'iso27001')}
      ${_gaugeHtml('NIS2', data.nis2?.score || 0, data.nis2?.label, 'nis2')}
      ${_gaugeHtml('NIST CSF 2.0', nist?.score || 0, nist?.label, 'nist_csf')}
      ${_gaugeHtml('ENS RD 311/2022', data.ens?.score || 0, data.ens?.label, 'ens')}
    `;

    if (_expandedPanel) {
      panelEl.style.display = 'block';
      panelEl.innerHTML = _detailPanelHtml(_expandedPanel, data);
      // Wire buttons inside the new panel
      const detailedBtn = document.getElementById('btn-gap-detailed');
      if (detailedBtn) detailedBtn.onclick = () => _runDetailedGapAnalysis(_expandedPanel);
    } else {
      panelEl.style.display = 'none';
      panelEl.innerHTML = '';
    }
  }

  function _statusBadge(status) {
    const map = {
      'implemented': { label: 'Implementado', color: 'var(--risk-low)', bg: '#DCFCE7' },
      'partial':     { label: 'Parcial',       color: '#D97706',        bg: '#FEF9C3' },
      'planned':     { label: 'Planificado',   color: '#2563EB',        bg: '#DBEAFE' },
      'not_implemented': { label: 'No impl.',  color: 'var(--risk-high)', bg: '#FEE2E2' },
    };
    const s = map[status] || { label: status || '-', color: 'var(--text-muted)', bg: 'var(--bg-2)' };
    return `<span style="background:${s.bg};color:${s.color};font-size:10px;font-weight:700;
              padding:2px 7px;border-radius:4px;white-space:nowrap;">${s.label}</span>`;
  }

  function _maturityBar(val) {
    const v = Math.min(5, Math.max(0, val || 0));
    const color = v >= 4 ? 'var(--risk-low)' : v >= 3 ? 'var(--risk-medium)' : v >= 2 ? 'var(--risk-high)' : 'var(--risk-critical)';
    return `<div style="display:flex;align-items:center;gap:6px;">
      <div style="flex:1;background:var(--border);border-radius:999px;height:6px;overflow:hidden;min-width:60px;">
        <div style="width:${v * 20}%;background:${color};height:100%;border-radius:999px;"></div>
      </div>
      <span style="font-size:11px;color:var(--text-muted);white-space:nowrap;">${v}/5</span>
    </div>`;
  }

  function _detailPanelHtml(key, data) {
    const frameworkLabels = {
      iso27001: 'ISO 27001:2022',
      nis2: 'NIS2 — Directiva EU 2022/2555',
      nist_csf: 'NIST CSF 2.0',
      ens: 'ENS RD 311/2022',
    };

    let innerHtml = '';

    if (key === 'iso27001') {
      innerHtml = _iso27001PanelHtml(data);
    } else if (key === 'nis2') {
      innerHtml = _nis2PanelHtml(data);
    } else if (key === 'nist_csf') {
      innerHtml = _nistPanelHtml(data);
    } else if (key === 'ens') {
      innerHtml = _ensPanelHtml(data);
    }

    return `
      <div style="background:var(--bg-card);border:2px solid var(--brand-purple);border-radius:10px;
                  padding:20px;margin-top:0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="font-size:15px;font-weight:700;margin:0;color:var(--brand-purple);">
            ${UI.esc(frameworkLabels[key] || key)} — Detalle
          </h3>
          <div style="display:flex;gap:8px;align-items:center;">
            <button class="btn btn-primary" id="btn-gap-detailed" style="font-size:12px;">
              Analizar brechas con IA
            </button>
            <button class="btn btn-ghost" style="font-size:12px;"
                    onclick="ViewCompliance._togglePanel('${key}')">Cerrar &#10005;</button>
          </div>
        </div>
        <div id="comp-detail-inner">${innerHtml}</div>
        <div id="comp-detail-gap-result" style="margin-top:16px;"></div>
      </div>
    `;
  }

  function _iso27001PanelHtml(data) {
    const impls = (_implsData || []).map(_flatImpl);
    // Group by theme
    const themes = {};
    impls.forEach(i => {
      const theme = (i.theme || 'Sin tema');
      if (!themes[theme]) themes[theme] = [];
      themes[theme].push(i);
    });

    if (!impls.length) {
      return `<p style="color:var(--text-muted);font-size:13px;">No hay controles registrados en esta organizacion.</p>
              ${_gapsSection(data.iso27001?.gaps)}`;
    }

    const themeOrder = ['Organizational', 'People', 'Physical', 'Technological', 'Sin tema'];
    const sortedThemes = Object.keys(themes).sort((a, b) => {
      const ai = themeOrder.indexOf(a), bi = themeOrder.indexOf(b);
      if (ai < 0 && bi < 0) return a.localeCompare(b);
      if (ai < 0) return 1;
      if (bi < 0) return -1;
      return ai - bi;
    });

    const themeHtml = sortedThemes.map(theme => {
      const controls = themes[theme];
      const rows = controls.map(c => {
        const hasGap = c.notes && c.notes.length > 0;
        return `<tr>
          <td style="font-size:11px;white-space:nowrap;color:var(--text-muted);">${UI.esc(c.code || '-')}</td>
          <td style="font-size:12px;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
              title="${UI.esc(c.name || '-')}">${UI.esc(c.name || '-')}</td>
          <td>${_statusBadge(c.status)}</td>
          <td style="min-width:120px;">${_maturityBar(c.maturity)}</td>
          <td style="font-size:11px;max-width:200px;">
            ${hasGap
              ? `<span style="color:var(--brand-orange);cursor:pointer;font-size:11px;"
                       title="${UI.esc(c.notes.slice(0,300))}"
                       onclick="this.parentElement.innerHTML='<span style=font-size:11px>${UI.esc(c.notes.replace(/'/g, '').slice(0,300))}</span>'">
                   Ver gap IA &#9660;</span>`
              : '<span style="color:var(--text-subtle);">-</span>'}
          </td>
        </tr>`;
      }).join('');
      return `
        <details open style="margin-bottom:12px;">
          <summary style="cursor:pointer;font-size:13px;font-weight:700;color:var(--text-base);
                          padding:6px 0;border-bottom:1px solid var(--border);margin-bottom:6px;">
            ${UI.esc(theme)} <span style="font-weight:400;color:var(--text-muted);">(${controls.length} controles)</span>
          </summary>
          <div style="overflow-x:auto;">
            <table class="data" style="font-size:12px;width:100%;">
              <thead><tr>
                <th>Codigo</th><th>Control</th><th>Estado</th><th>Madurez</th><th>Gap IA</th>
              </tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </details>`;
    }).join('');

    return themeHtml + _gapsSection(data.iso27001?.gaps);
  }

  function _nis2PanelHtml(data) {
    // NIS2 Art. 21.2 articles and their mapping to control indicators
    const articles = [
      { id: 'a', text: 'Politicas de analisis de riesgos y seguridad de sistemas (Art. 21.2.a)' },
      { id: 'b', text: 'Gestion de incidentes (Art. 21.2.b)' },
      { id: 'c', text: 'Continuidad del negocio y gestion de crisis (Art. 21.2.c)' },
      { id: 'd', text: 'Seguridad de la cadena de suministro (Art. 21.2.d)' },
      { id: 'e', text: 'Seguridad en adquisicion, desarrollo y mantenimiento de sistemas (Art. 21.2.e)' },
      { id: 'f', text: 'Politicas y procedimientos para evaluar eficacia de medidas (Art. 21.2.f)' },
      { id: 'g', text: 'Practicas basicas de ciberhigiene y formacion (Art. 21.2.g)' },
      { id: 'h', text: 'Politicas sobre uso de criptografia (Art. 21.2.h)' },
      { id: 'i', text: 'Seguridad de recursos humanos, control de acceso y gestion de activos (Art. 21.2.i)' },
      { id: 'j', text: 'Autenticacion multifactor y comunicaciones seguras (Art. 21.2.j)' },
    ];
    const impls = (_implsData || []).map(_flatImpl);
    // Map articles to control coverage (simplified heuristic by theme/keywords)
    const themeMap = {
      a: ['risk', 'organizational', 'governance'],
      b: ['incident'],
      c: ['continuity', 'recovery', 'backup'],
      d: ['supplier', 'supply'],
      e: ['development', 'change', 'vulnerability'],
      f: ['audit', 'review', 'monitoring'],
      g: ['awareness', 'training', 'hygiene'],
      h: ['cryptography', 'encryption'],
      i: ['access', 'identity', 'asset', 'personnel'],
      j: ['authentication', 'mfa', 'communication'],
    };

    const rows = articles.map(art => {
      const keywords = themeMap[art.id] || [];
      const matched = impls.filter(i => {
        const haystack = ((i.name || '') + ' ' + (i.description || '') + ' ' + (i.theme || '')).toLowerCase();
        return keywords.some(k => haystack.includes(k));
      });
      const implemented = matched.filter(i => i.status === 'implemented').length;
      const partial = matched.filter(i => i.status === 'partial').length;
      const statusColor = (implemented + partial) > 0 ? 'var(--risk-low)' : 'var(--risk-high)';
      const statusLabel = (implemented + partial) > 0
        ? `${implemented + partial} controles cubiertos`
        : 'Sin cobertura detectada';
      return `<tr>
        <td style="font-size:12px;">${UI.esc(art.text)}</td>
        <td><span style="color:${statusColor};font-size:12px;font-weight:600;">${statusLabel}</span></td>
      </tr>`;
    }).join('');

    return `
      <div style="overflow-x:auto;margin-bottom:16px;">
        <table class="data" style="font-size:12px;width:100%;">
          <thead><tr><th>Requisito NIS2</th><th>Cobertura estimada</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      ${_gapsSection(data.nis2?.gaps)}
    `;
  }

  function _nistPanelHtml(data) {
    const nist = data.nist_csf || {};
    const fns = nist.functions || {};
    const impls = (_implsData || []).map(_flatImpl);
    const fnColors = {
      GOVERN: '#7C3AED', IDENTIFY: '#2563EB', PROTECT: '#059669',
      DETECT: '#D97706', RESPOND: '#DC2626', RECOVER: '#0891B2',
    };
    // Heuristic: map controls to NIST functions by theme/name keywords
    const fnKeywords = {
      GOVERN:   ['governance', 'policy', 'risk management', 'organizational'],
      IDENTIFY: ['asset', 'inventory', 'risk assessment', 'vulnerability'],
      PROTECT:  ['access', 'cryptography', 'training', 'physical', 'change'],
      DETECT:   ['monitoring', 'incident detection', 'anomaly', 'audit log'],
      RESPOND:  ['incident response', 'communication', 'mitigation'],
      RECOVER:  ['recovery', 'backup', 'continuity', 'lessons'],
    };

    const fnHtml = Object.entries(fns).map(([fn, score]) => {
      const color = fnColors[fn] || 'var(--brand-purple)';
      const keywords = fnKeywords[fn] || [];
      const matched = impls.filter(i => {
        const haystack = ((i.name || '') + ' ' + (i.description || '') + ' ' + (i.theme || '')).toLowerCase();
        return keywords.some(k => haystack.includes(k));
      });
      const controlList = matched.slice(0, 5).map(i =>
        `<li style="font-size:11px;color:var(--text-muted);">${UI.esc(i.name || '-')}</li>`
      ).join('');

      return `
        <div style="margin-bottom:16px;padding:12px;background:var(--bg-2);border-radius:8px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <span style="font-weight:700;color:${color};font-size:13px;">${UI.esc(fn)}</span>
            <span style="font-size:16px;font-weight:800;color:${color};">${score}%</span>
          </div>
          <div style="background:var(--border);border-radius:999px;height:8px;overflow:hidden;margin-bottom:8px;">
            <div style="width:${score}%;background:${color};height:100%;border-radius:999px;transition:width .4s;"></div>
          </div>
          ${matched.length > 0 ? `
            <details>
              <summary style="cursor:pointer;font-size:11px;color:var(--text-muted);">
                ${matched.length} controles contribuyen a esta funcion
              </summary>
              <ul style="margin:4px 0 0 16px;padding:0;">${controlList}
                ${matched.length > 5 ? `<li style="font-size:11px;color:var(--text-subtle);">... y ${matched.length - 5} mas</li>` : ''}
              </ul>
            </details>` : `<p style="font-size:11px;color:var(--text-muted);margin:0;">Sin controles mapeados a esta funcion.</p>`}
        </div>`;
    }).join('');

    return fnHtml;
  }

  function _ensPanelHtml(data) {
    const dimensions = [
      { id: 'identificacion', label: 'Identificacion — Marco organizativo y gestion de riesgos', themes: ['organizational', 'risk'] },
      { id: 'proteccion',     label: 'Proteccion — Medidas de proteccion (Anexo II, Marco OP/MP)', themes: ['access', 'cryptography', 'physical', 'network'] },
      { id: 'deteccion',      label: 'Deteccion — Monitorizacion y deteccion de incidentes', themes: ['monitoring', 'detection', 'audit'] },
      { id: 'respuesta',      label: 'Respuesta — Gestion de incidentes y comunicacion', themes: ['incident', 'response'] },
      { id: 'recuperacion',   label: 'Recuperacion — Continuidad y recuperacion', themes: ['recovery', 'continuity', 'backup'] },
    ];
    const impls = (_implsData || []).map(_flatImpl);

    const rows = dimensions.map(dim => {
      const keywords = dim.themes;
      const matched = impls.filter(i => {
        const haystack = ((i.name || '') + ' ' + (i.description || '') + ' ' + (i.theme || '')).toLowerCase();
        return keywords.some(k => haystack.includes(k));
      });
      const implemented = matched.filter(i => i.status === 'implemented').length;
      const partial = matched.filter(i => i.status === 'partial').length;
      const total = matched.length;
      const pct = total > 0 ? Math.round((implemented + partial * 0.5) / total * 100) : 0;
      const color = _scoreColor(pct);
      return `<tr>
        <td style="font-size:12px;">${UI.esc(dim.label)}</td>
        <td style="min-width:120px;">${_maturityBar(Math.round(pct / 20))}</td>
        <td style="font-size:12px;color:${color};font-weight:600;">${pct}%</td>
        <td style="font-size:11px;color:var(--text-muted);">${total} medidas detectadas</td>
      </tr>`;
    }).join('');

    return `
      <div style="overflow-x:auto;margin-bottom:16px;">
        <table class="data" style="font-size:12px;width:100%;">
          <thead><tr><th>Dimension ENS</th><th>Cobertura</th><th>%</th><th>Medidas</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      ${_gapsSection(data.ens?.gaps)}
    `;
  }

  function _gapsSection(gaps) {
    if (!gaps || !gaps.length) return '';
    return `<div style="margin-top:12px;">
      <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;">Brechas identificadas</h4>
      ${_gapsHtml(gaps)}
    </div>`;
  }

  // ============================================================
  // Detailed AI Gap Analysis modal
  // ============================================================

  async function _runDetailedGapAnalysis(framework) {
    const btn = document.getElementById('btn-gap-detailed');
    const resultDiv = document.getElementById('comp-detail-gap-result');
    if (!resultDiv) return;
    if (btn) { btn.disabled = true; btn.textContent = 'Analizando con IA...'; }
    resultDiv.innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;padding:20px;background:var(--bg-2);border-radius:8px;">
        <div class="loading-spinner" style="width:24px;height:24px;"></div>
        <span style="font-size:13px;color:var(--text-muted);">El agente IA esta realizando el gap analysis detallado...</span>
      </div>`;

    try {
      const d = await Api.ai.controlGapDetailed({ framework, include_implemented: false });
      _renderDetailedGapResult(resultDiv, d, framework);
    } catch (e) {
      resultDiv.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Analizar brechas con IA'; }
    }
  }

  function _renderDetailedGapResult(container, d, framework) {
    const statusColors = {
      'CONFORME':    { bg: '#DCFCE7', color: 'var(--risk-low)' },
      'PARCIAL':     { bg: '#FEF9C3', color: '#D97706' },
      'NO CONFORME': { bg: '#FEE2E2', color: 'var(--risk-critical)' },
      'EXCLUIDO':    { bg: 'var(--bg-2)', color: 'var(--text-muted)' },
    };
    const priorityColors = {
      'INMEDIATA':     'var(--risk-critical)',
      'CORTO PLAZO':   'var(--risk-high)',
      'MEDIO PLAZO':   'var(--risk-medium)',
    };

    const controls = d.controls || [];
    let filterStatus = 'all';

    function _rowsHtml(filterVal) {
      const filtered = filterVal === 'all' ? controls : controls.filter(c => c.status === filterVal);
      if (!filtered.length) return `<tr><td colspan="6" style="text-align:center;padding:16px;color:var(--text-muted);">Sin controles en este estado.</td></tr>`;
      return filtered.map(c => {
        const sc = statusColors[c.status] || { bg: 'var(--bg-2)', color: 'var(--text-muted)' };
        const pc = priorityColors[c.priority] || 'var(--text-muted)';
        return `<tr>
          <td style="font-size:11px;white-space:nowrap;color:var(--text-muted);">${UI.esc(c.code || '-')}</td>
          <td style="font-size:12px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
              title="${UI.esc(c.name || '-')}">${UI.esc(c.name || '-')}</td>
          <td><span style="background:${sc.bg};color:${sc.color};font-size:10px;font-weight:700;
                           padding:2px 7px;border-radius:4px;white-space:nowrap;">${UI.esc(c.status || '-')}</span></td>
          <td style="font-size:11px;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
              title="${UI.esc(c.finding || '-')}">${UI.esc(c.finding || '-')}</td>
          <td style="font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
              title="${UI.esc(c.recommendation || '-')}">${UI.esc(c.recommendation || '-')}</td>
          <td><span style="color:${pc};font-size:10px;font-weight:700;">${UI.esc(c.priority || '-')}</span></td>
        </tr>`;
      }).join('');
    }

    const statusCounts = {};
    controls.forEach(c => { statusCounts[c.status] = (statusCounts[c.status] || 0) + 1; });

    container.innerHTML = `
      <hr style="border:none;border-top:1px solid var(--border);margin:0 0 16px;">
      <!-- Executive summary -->
      ${d.executive_summary ? `
        <div style="background:var(--bg-2);border-left:4px solid var(--brand-purple);
                    padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:16px;">
          <p style="font-size:13px;margin:0;line-height:1.6;">${UI.esc(d.executive_summary)}</p>
        </div>` : ''}

      <!-- Score + top 3 -->
      <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;">
        ${d.framework_score != null ? `
          <div class="stat-card" style="text-align:center;min-width:120px;">
            <div class="stat-value" style="color:${_scoreColor(d.framework_score)};">${d.framework_score}</div>
            <div class="stat-label">Score IA /100</div>
          </div>` : ''}
        ${Object.entries(statusCounts).map(([s, n]) => {
          const sc = statusColors[s] || { bg: 'var(--bg-2)', color: 'var(--text-muted)' };
          return `<div class="stat-card" style="text-align:center;min-width:100px;">
            <div class="stat-value" style="color:${sc.color};">${n}</div>
            <div class="stat-label">${s}</div>
          </div>`;
        }).join('')}
      </div>

      ${d.top_3_priorities?.length ? `
        <div style="margin-bottom:16px;">
          <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;color:var(--risk-critical);">Top 3 prioridades</h4>
          ${d.top_3_priorities.map((p, i) => `
            <div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:8px;
                        padding:10px;background:var(--bg-2);border-radius:6px;">
              <span style="background:var(--risk-critical);color:#fff;font-size:11px;font-weight:700;
                           padding:2px 7px;border-radius:999px;flex-shrink:0;">${i + 1}</span>
              <span style="font-size:13px;">${UI.esc(p)}</span>
            </div>`).join('')}
        </div>` : ''}

      <!-- Filter + table -->
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
        ${['all', 'CONFORME', 'PARCIAL', 'NO CONFORME', 'EXCLUIDO'].map(s => {
          const n = s === 'all' ? controls.length : (statusCounts[s] || 0);
          return `<button class="btn btn-ghost" style="font-size:11px;padding:3px 10px;"
                          onclick="ViewCompliance._filterGapTable(this, '${s}')">
            ${s === 'all' ? 'Todos' : s} (${n})
          </button>`;
        }).join('')}
      </div>
      <div style="overflow-x:auto;">
        <table class="data" id="gap-detail-table" style="font-size:12px;width:100%;">
          <thead><tr>
            <th>Codigo</th><th>Control</th><th>Estado</th><th>Hallazgo</th>
            <th>Recomendacion</th><th>Prioridad</th>
          </tr></thead>
          <tbody id="gap-detail-tbody">${_rowsHtml('all')}</tbody>
        </table>
      </div>
    `;

    // Store filter function
    ViewCompliance._filterGapTable = (btn, status) => {
      document.querySelectorAll('#comp-detail-gap-result .btn').forEach(b => b.classList.remove('btn-primary'));
      btn.classList.add('btn-primary');
      const tbody = document.getElementById('gap-detail-tbody');
      if (tbody) tbody.innerHTML = _rowsHtml(status);
    };
  }

  // ============================================================
  // Main render
  // ============================================================

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Dashboard de Cumplimiento</h1>
          <p class="page-sub">Puntuacion multi-framework: ISO 27001 | NIS2 | NIST CSF 2.0 | ENS</p>
        </div>
        <button class="btn btn-primary" id="btn-refresh-comp">Actualizar</button>
      </div>
      <div id="comp-content"><div class="loading-spinner" style="margin:40px auto;"></div></div>
    `;
    document.getElementById('btn-refresh-comp').onclick = () => _load(el);
    await _load(el);
  }

  async function _load(el) {
    const content = document.getElementById('comp-content');
    if (!content) return;
    content.innerHTML = '<p class="text-muted" style="text-align:center;padding:32px;">Calculando puntuaciones...</p>';
    _expandedPanel = null;
    _compData = null;
    _implsData = null;
    try {
      const [data, implsList] = await Promise.all([
        Api.compliance.summary(),
        Api.impls.list().catch(() => []),
      ]);
      _compData = data;
      _implsData = implsList;
      _render(content, data);
      // Wire legacy gap button
      const gapBtn = document.getElementById('btn-gap-analysis');
      if (gapBtn) gapBtn.onclick = _runGapAnalysis;
    } catch (e) {
      content.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _render(content, data) {
    const meta = data._meta || {};
    const nist = data.nist_csf || {};
    const fns = nist.functions || {};

    content.innerHTML = `
      <!-- Resumen global -->
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:20px;">
        <h2 style="font-size:15px;font-weight:700;margin:0 0 16px;">Resumen operacional</h2>
        <div class="stats-row">
          <div class="stat-card">
            <div class="stat-value">${meta.total_controls || 0}</div>
            <div class="stat-label">Controles activos</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" style="color:var(--risk-low);">${meta.implemented_controls || 0}</div>
            <div class="stat-label">Implementados</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">${meta.total_risks || 0}</div>
            <div class="stat-label">Riesgos totales</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" style="color:var(--risk-medium);">${meta.risks_treated || 0}</div>
            <div class="stat-label">Con tratamiento</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" style="color:var(--risk-high);">${meta.open_incidents || 0}</div>
            <div class="stat-label">Incidentes abiertos</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" style="color:var(--risk-critical);">${meta.open_ncs || 0}</div>
            <div class="stat-label">NC abiertas</div>
          </div>
        </div>
      </div>

      <!-- Gauges por framework (clicables) -->
      <div id="comp-gauges" style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;">
        ${_gaugeHtml('ISO 27001:2022', data.iso27001?.score || 0, data.iso27001?.label, 'iso27001')}
        ${_gaugeHtml('NIS2', data.nis2?.score || 0, data.nis2?.label, 'nis2')}
        ${_gaugeHtml('NIST CSF 2.0', nist?.score || 0, nist?.label, 'nist_csf')}
        ${_gaugeHtml('ENS RD 311/2022', data.ens?.score || 0, data.ens?.label, 'ens')}
      </div>

      <!-- Panel de detalle expandible (se rellena al clicar un gauge) -->
      <div id="comp-detail-panel" style="display:none;margin-bottom:20px;"></div>

      <!-- NIST CSF funciones -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;" class="compliance-detail-grid">
        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;">
          <h3 style="font-size:14px;font-weight:700;margin:0 0 4px;">NIST CSF 2.0 — Funciones</h3>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 8px;">Cobertura por funcion</p>
          ${_nistFunctionsHtml(fns)}
        </div>

        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;">
          <h3 style="font-size:14px;font-weight:700;margin:0 0 4px;">ISO 27001:2022 — Brechas</h3>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">Clausula 6.1.3 y 10.1</p>
          ${_gapsHtml(data.iso27001?.gaps)}
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;" class="compliance-detail-grid">
        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;">
          <h3 style="font-size:14px;font-weight:700;margin:0 0 4px;">NIS2 — Brechas</h3>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">Art. 21 y 23</p>
          ${_gapsHtml(data.nis2?.gaps)}
        </div>
        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;">
          <h3 style="font-size:14px;font-weight:700;margin:0 0 4px;">ENS RD 311/2022 — Brechas</h3>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">Anexo II</p>
          ${_gapsHtml(data.ens?.gaps)}
        </div>
      </div>

      <p style="font-size:11px;color:var(--text-muted);margin-top:16px;text-align:center;">
        Puntuaciones calculadas a partir de los datos registrados en RiskHub. Actualizar regularmente para reflejar el estado real del SGSI.
      </p>

      <!-- AI Gap Analysis section (legacy estadistico) -->
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;margin-top:20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <div>
            <h3 style="font-size:14px;font-weight:700;margin:0 0 4px;">Analisis de brechas de controles (estadistico)</h3>
            <p style="font-size:12px;color:var(--text-muted);margin:0;">Detecta controles sin implementar, temas debiles y problemas SOA por framework. Para gap analysis profundo usa el boton en cada gauge.</p>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            <select id="gap-framework" style="font-size:13px;padding:4px 8px;border-radius:6px;border:1px solid var(--border);background:var(--bg-1);">
              <option value="iso27001">ISO 27001</option>
              <option value="nis2">NIS2</option>
              <option value="nist_csf">NIST CSF</option>
              <option value="ens">ENS</option>
            </select>
            <button class="btn btn-primary" id="btn-gap-analysis">Analizar brechas</button>
          </div>
        </div>
        <div id="gap-results" style="display:none;"></div>
      </div>
    `;
  }

  // ============================================================
  // Legacy gap analysis (estadistico)
  // ============================================================

  async function _runGapAnalysis() {
    const framework = document.getElementById('gap-framework')?.value || 'iso27001';
    const btn = document.getElementById('btn-gap-analysis');
    const resultsDiv = document.getElementById('gap-results');
    if (!resultsDiv) return;
    if (btn) { btn.disabled = true; btn.textContent = 'Analizando...'; }
    resultsDiv.style.display = 'block';
    resultsDiv.innerHTML = '<p style="color:var(--text-muted);font-size:13px;">Analizando controles...</p>';
    try {
      const d = await Api.ai.controlGap({ framework });
      const s = d.summary || {};
      const pct = s.pct_implemented || 0;
      const pctColor = pct >= 75 ? 'var(--risk-low)' : pct >= 50 ? 'var(--risk-medium)' : pct >= 25 ? 'var(--risk-high)' : 'var(--risk-critical)';
      resultsDiv.innerHTML = `
        <hr style="border:none;border-top:1px solid var(--border);margin:0 0 16px;">
        <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;">
          <div class="stat-card"><div class="stat-value">${s.total||0}</div><div class="stat-label">Controles totales</div></div>
          <div class="stat-card"><div class="stat-value" style="color:var(--risk-low);">${s.implemented||0}</div><div class="stat-label">Implementados</div></div>
          <div class="stat-card"><div class="stat-value" style="color:var(--risk-medium);">${s.partial||0}</div><div class="stat-label">Parciales</div></div>
          <div class="stat-card"><div class="stat-value" style="color:var(--risk-high);">${s.not_implemented||0}</div><div class="stat-label">Sin implementar</div></div>
          <div class="stat-card">
            <div class="stat-value" style="color:${pctColor};">${pct}%</div>
            <div class="stat-label">Cobertura efectiva</div>
          </div>
        </div>
        ${d.weak_themes?.length ? `
          <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;color:var(--text-base);">Temas con menor cobertura</h4>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;">
            ${d.weak_themes.map(t => `
              <div style="background:var(--bg-2);border-radius:8px;padding:8px 12px;font-size:12px;min-width:140px;">
                <div style="font-weight:700;color:var(--risk-high);font-size:16px;">${t.score}%</div>
                <div style="font-weight:600;margin:2px 0;">${UI.esc(t.theme)}</div>
                <div style="color:var(--text-muted);">${t.not_implemented} sin implementar de ${t.total}</div>
              </div>`).join('')}
          </div>` : ''}
        ${d.soa_issues ? `
          <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;color:var(--text-base);">Problemas SOA (cl. 6.1.3)</h4>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;">
            ${d.soa_issues.missing_inclusion_reason > 0 ? `<span style="background:#FEF9C3;color:#854D0E;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600;">${d.soa_issues.missing_inclusion_reason} sin razon de inclusion</span>` : ''}
            ${d.soa_issues.missing_evidence > 0 ? `<span style="background:#FEE2E2;color:#991B1B;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600;">${d.soa_issues.missing_evidence} sin evidencia</span>` : ''}
            ${d.soa_issues.overdue_reviews > 0 ? `<span style="background:#FFF7ED;color:#9A3412;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600;">${d.soa_issues.overdue_reviews} revisiones vencidas</span>` : ''}
            ${(!d.soa_issues.missing_inclusion_reason && !d.soa_issues.missing_evidence && !d.soa_issues.overdue_reviews) ? '<span style="color:var(--risk-low);font-size:13px;">Sin problemas SOA detectados.</span>' : ''}
          </div>` : ''}
        ${d.recommendations?.length ? `
          <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;color:var(--text-base);">Recomendaciones</h4>
          <ul style="margin:0 0 12px;padding-left:20px;">
            ${d.recommendations.map(r => `<li style="font-size:13px;margin-bottom:4px;color:var(--text-base);">${UI.esc(r)}</li>`).join('')}
          </ul>` : ''}
        ${d.critical_gaps?.length ? `
          <details style="margin-top:8px;">
            <summary style="cursor:pointer;font-size:13px;font-weight:600;color:var(--text-muted);">
              ${d.critical_gaps.length} controles sin implementar (sin justificacion de exclusion)
            </summary>
            <div style="margin-top:8px;">
              ${d.critical_gaps.map(g => `
                <div style="font-size:12px;padding:4px 0;border-bottom:1px solid var(--border);display:flex;gap:8px;">
                  <span style="color:var(--text-muted);min-width:80px;">${UI.esc(g.theme||'-')}</span>
                  <span style="font-weight:600;">${UI.esc(g.control_name)}</span>
                  <span style="color:var(--text-muted);">madurez ${g.maturity}/5</span>
                </div>`).join('')}
            </div>
          </details>` : ''}
      `;
    } catch (e) {
      resultsDiv.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Analizar brechas'; }
    }
  }

  return { render, _togglePanel, _filterGapTable: () => {} };
})();
