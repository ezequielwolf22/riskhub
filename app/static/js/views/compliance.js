/* Vista de dashboard de cumplimiento multi-framework. */

/**
 * Renderiza un SVG de progress ring circular para el dashboard de compliance.
 * @param {number} pct  Porcentaje 0-100
 * @param {number} size Tamano en px (default 80)
 * @param {number} strokeWidth Grosor del trazo (default 8)
 * @returns {string} HTML del ring
 */
function _renderProgressRing(pct, size = 80, strokeWidth = 8) {
  const r = (size - strokeWidth) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  const colorClass = pct >= 80 ? 'high' : pct >= 60 ? 'medium' : 'low';
  return `
    <div class="progress-ring-wrap">
      <svg class="progress-ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <circle class="progress-ring-bg" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${strokeWidth}"/>
        <circle class="progress-ring-fill ${colorClass}" cx="${size / 2}" cy="${size / 2}" r="${r}"
          stroke-width="${strokeWidth}"
          stroke-dasharray="${circ.toFixed(2)}"
          stroke-dashoffset="${offset.toFixed(2)}"
        />
      </svg>
      <div class="progress-ring-label">${pct}<span style="font-size:14px;font-weight:500;color:var(--text-subtle)">%</span></div>
    </div>
  `;
}

const ViewCompliance = (() => {

  // Estado de panel expandido por framework key
  let _expandedPanel = null;
  // Cache de datos de compliance para los paneles
  let _compData = null;
  // Cache de controles implementados para los paneles ISO/NIST/ENS
  let _implsData = null;
  // Normativas activas y nivel ENS desde el contexto organizacional
  let _activeFrameworks = null;   // null = mostrar todo; [] = ISO 27001 mínimo
  let _ensLevel = null;

  // Mapa interno de frameworks disponibles
  const _FW_META = {
    iso27001: { label: 'ISO 27001:2022',      dataKey: 'iso27001' },
    iso22301: { label: 'ISO 22301:2019',      dataKey: 'iso22301' },
    nis2:     { label: 'NIS2',                dataKey: 'nis2' },
    nist_csf: { label: 'NIST CSF 2.0',        dataKey: 'nist_csf' },
    ens:      { label: 'ENS RD 311/2022',     dataKey: 'ens' },
    gdpr:     { label: 'GDPR / RGPD',         dataKey: 'gdpr' },
    pcidss:   { label: 'PCI-DSS v4.0',        dataKey: 'pcidss' },
    soc2:     { label: 'SOC 2 Type II',        dataKey: 'soc2' },
    hipaa:    { label: 'HIPAA Security Rule',  dataKey: 'hipaa' },
  };

  // Cache de datos BCP/BCM para ISO 22301
  let _bcpCompData = null;

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

  function _getActiveFrameworkKeys() {
    // Si no hay normativas configuradas → mostrar todos los frameworks disponibles
    const all = Object.keys(_FW_META);
    if (!_activeFrameworks || _activeFrameworks.length === 0) {
      // ISO 22301 solo si hay datos BCP
      if (!_bcpCompData) return all.filter(k => k !== 'iso22301');
      return all;
    }
    // Filtrar solo los que tienen datos en _FW_META
    const active = _activeFrameworks.filter(k => _FW_META[k]);
    // Siempre garantizar ISO 27001 como base
    if (!active.includes('iso27001')) active.unshift('iso27001');
    // ISO 22301 siempre visible si hay datos BCP, independiente de active_frameworks
    if (_bcpCompData && !active.includes('iso22301')) active.push('iso22301');
    return active;
  }

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
    // Determinar qué frameworks mostrar
    const activeKeys = _getActiveFrameworkKeys();
    gaugesEl.innerHTML = activeKeys
      .map(k => {
        const m = _FW_META[k];
        if (!m) return '';
        const d = data[m.dataKey] || {};
        const score = k === 'nist_csf' ? (nist?.score || 0) : (d.score || 0);
        const sublabel = (k === 'ens' && _ensLevel)
          ? `Nivel ${_ensLevel.charAt(0).toUpperCase() + _ensLevel.slice(1)}`
          : (d.label || '');
        return _gaugeHtml(m.label, score, sublabel, k);
      }).join('');

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
      iso22301: 'ISO 22301:2019 — Continuidad del negocio',
      nis2:     'NIS2 — Directiva EU 2022/2555',
      nist_csf: 'NIST CSF 2.0',
      ens:      'ENS RD 311/2022',
      gdpr:     'GDPR / RGPD',
      pcidss:   'PCI-DSS v4.0',
      soc2:     'SOC 2 Type II',
      hipaa:    'HIPAA Security Rule',
    };

    let innerHtml = '';

    if (key === 'iso27001') {
      innerHtml = _iso27001PanelHtml(data);
    } else if (key === 'iso22301') {
      innerHtml = _iso22301PanelHtml(data);
    } else if (key === 'nis2') {
      innerHtml = _nis2PanelHtml(data);
    } else if (key === 'nist_csf') {
      innerHtml = _nistPanelHtml(data);
    } else if (key === 'ens') {
      innerHtml = _ensPanelHtml(data);
    } else {
      // Panel genérico para GDPR, PCI-DSS, SOC 2, HIPAA
      innerHtml = _genericFrameworkPanel(key, data);
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
        const needsAnalysis = c.maturity < 5;
        return `<tr>
          <td style="font-size:11px;white-space:nowrap;color:var(--text-muted);">${UI.esc(c.code || '-')}</td>
          <td style="font-size:12px;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
              title="${UI.esc(c.name || '-')}">${UI.esc(c.name || '-')}</td>
          <td>${_statusBadge(c.status)}</td>
          <td style="min-width:120px;">${_maturityBar(c.maturity)}</td>
          <td style="font-size:11px;max-width:200px;">
            ${needsAnalysis
              ? `<span style="color:var(--brand-purple);cursor:pointer;font-size:11px;text-decoration:underline;"
                       onclick="ViewCompliance._showGapModal(${c.id})">
                   Ver analisis${c.notes ? ' IA' : ''}</span>`
              : '<span style="color:var(--risk-low);font-size:11px;">Optimo</span>'}
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
                <th>Codigo</th><th>Control</th><th>Estado</th><th>Madurez</th><th>Analisis IA</th>
              </tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        </details>`;
    }).join('');

    return themeHtml + _gapsSection(data.iso27001?.gaps);
  }

  function _iso22301PanelHtml(data) {
    const d = data.iso22301 || {};
    const clauses = d.clauses || [];
    const kpis = d.kpis || {};

    if (!clauses.length) {
      return `
        <div style="text-align:center;padding:24px;">
          <p style="color:var(--text-muted);font-size:13px;margin-bottom:12px;">
            No hay datos de continuidad de negocio registrados todavia.
          </p>
          <button class="btn btn-primary" onclick="App.navigate('bcp');UI.closeModal();">
            Ir a BCP/BCM para configurar
          </button>
        </div>`;
    }

    const scoreColor = _scoreColor(d.score || 0);

    const clauseRows = clauses.map(c => {
      const color = _scoreColor(c.score);
      return `<tr>
        <td style="font-size:11px;font-weight:700;white-space:nowrap;color:var(--text-muted);">Cl. ${UI.esc(c.id)}</td>
        <td style="font-size:12px;">${UI.esc(c.title)}</td>
        <td style="min-width:120px;">
          <div style="background:var(--border);border-radius:999px;height:7px;overflow:hidden;">
            <div style="width:${c.score}%;background:${color};height:100%;border-radius:999px;transition:width .4s;"></div>
          </div>
        </td>
        <td style="font-size:12px;font-weight:700;color:${color};white-space:nowrap;">${c.score}%</td>
      </tr>`;
    }).join('');

    const kpiItems = [
      { label: 'Procesos totales',     val: kpis.processes_total || 0 },
      { label: 'Procesos con BIA',     val: kpis.processes_with_bia || 0, color: 'var(--risk-low)' },
      { label: 'Planes totales',       val: kpis.plans_total || 0 },
      { label: 'Planes aprobados',     val: kpis.plans_approved || 0, color: 'var(--risk-low)' },
      { label: 'Ejercicios 12m',       val: kpis.tests_recent_12m || 0, color: 'var(--brand-purple)' },
      { label: 'Ejercicios superados', val: kpis.tests_passed || 0, color: 'var(--risk-low)' },
      { label: 'Estrategias impl.',    val: kpis.strategies_implemented || 0, color: 'var(--risk-low)' },
      { label: 'Evidencias',           val: kpis.evidence_items || 0 },
    ];

    const kpiHtml = kpiItems.map(k => `
      <div class="stat-card" style="text-align:center;min-width:100px;padding:10px 14px;">
        <div class="stat-value" style="${k.color ? 'color:' + k.color + ';' : ''}">${k.val}</div>
        <div class="stat-label">${UI.esc(k.label)}</div>
      </div>`).join('');

    const locHtml = (d.locations || []).length ? `
      <h4 style="font-size:13px;font-weight:700;margin:16px 0 8px;">Sedes / Ubicaciones</h4>
      <div style="overflow-x:auto;">
        <table class="data" style="font-size:12px;width:100%;">
          <thead><tr><th>Sede</th><th>Score</th><th>Estado</th><th>Planes aprobados</th><th>Ultimo ejercicio</th></tr></thead>
          <tbody>
            ${(d.locations || []).map(loc => {
              const sc = loc.score >= 70 ? 'var(--risk-low)' : loc.score >= 40 ? 'var(--risk-medium)' : 'var(--risk-high)';
              const statusLabel = { green: 'Conforme', yellow: 'Parcial', red: 'Critico' }[loc.status] || loc.status;
              return `<tr>
                <td style="font-size:12px;">${UI.esc(loc.name)}</td>
                <td style="font-size:12px;font-weight:700;color:${sc};">${loc.score}%</td>
                <td><span style="color:${sc};font-size:11px;font-weight:600;">${UI.esc(statusLabel)}</span></td>
                <td style="font-size:12px;">${loc.plans_approved} / ${loc.plans_total}</td>
                <td style="font-size:11px;color:var(--text-muted);">${loc.last_test_date || '-'}</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>` : '';

    return `
      <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;flex-wrap:wrap;">
        <div style="text-align:center;min-width:90px;">
          <div style="font-size:36px;font-weight:800;color:${scoreColor};">${d.score || 0}</div>
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;">Score global</div>
        </div>
        <div style="flex:1;font-size:13px;color:var(--text-muted);min-width:180px;">
          Puntuacion calculada a partir de los datos de la seccion BCP/BCM (planes, procesos, ejercicios
          y estrategias de continuidad). Los datos son identicos a los de esa seccion y se
          actualizan automaticamente al modificar cualquier elemento BCM.
          <br>
          <button class="btn btn-ghost" style="margin-top:8px;font-size:12px;"
                  onclick="App.navigate('bcp');">
            Ir a BCP/BCM para editar &#8594;
          </button>
        </div>
      </div>

      <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;">KPIs de continuidad</h4>
      <div class="stats-row" style="margin-bottom:16px;flex-wrap:wrap;">${kpiHtml}</div>

      <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;">Clausulas ISO 22301</h4>
      <div style="overflow-x:auto;margin-bottom:16px;">
        <table class="data" style="font-size:12px;width:100%;">
          <thead><tr><th>Clausula</th><th>Titulo</th><th>Cobertura</th><th>%</th></tr></thead>
          <tbody>${clauseRows}</tbody>
        </table>
      </div>
      ${locHtml}
    `;
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

  // Panel genérico para GDPR, PCI-DSS, SOC 2, HIPAA
  function _genericFrameworkPanel(key, data) {
    const fwData = data[key] || {};
    const score  = fwData.score ?? 0;
    const gaps   = fwData.gaps  || [];
    const label  = fwData.label || key.toUpperCase();

    const actionsByFramework = {
      gdpr: [
        { action: 'Registra todas las actividades de tratamiento (Art. 30 RGPD)', link: 'gdpr', label: 'Ir a RGPD' },
        { action: 'Completa DPIAs para tratamientos de alto riesgo (Art. 35 RGPD)', link: 'gdpr', label: 'Ir a RGPD' },
        { action: 'Documenta la base legal de cada actividad de tratamiento (Art. 6 RGPD)', link: null },
        { action: 'Implementa controles de privacidad por diseño: cifrado, seudonimización, minimización de datos', link: 'controls', label: 'Ir a Controles' },
        { action: 'Establece procedimientos de respuesta a violaciones de datos (Art. 33, 72h)', link: 'incidents', label: 'Ir a Incidentes' },
      ],
      pcidss: [
        { action: 'Implementa control de acceso basado en necesidad de conocer (Req. 7 PCI-DSS v4.0)', link: 'controls' },
        { action: 'Cifra datos de titulares de tarjeta en reposo y en tránsito (Req. 3, 4)', link: 'controls' },
        { action: 'Mantén inventario de sistemas que almacenan, procesan o transmiten datos de pago (Req. 12)', link: 'assets', label: 'Ir a Activos' },
        { action: 'Gestiona parches y vulnerabilidades con regularidad (Req. 6)', link: 'cve', label: 'Ir a CVE' },
        { action: 'Monitoriza y analiza logs de acceso (Req. 10)', link: 'controls' },
      ],
      soc2: [
        { action: 'Documenta controles de acceso lógico (CC6 — Common Criteria)', link: 'controls' },
        { action: 'Implementa monitorización de actividad del sistema (CC7)', link: 'controls' },
        { action: 'Define SLAs de disponibilidad para sistemas críticos (A1 — Availability)', link: 'assets', label: 'Ir a Activos' },
        { action: 'Mantén políticas de seguridad formales y revisadas (CC1 — Control Environment)', link: 'policies', label: 'Ir a Políticas' },
        { action: 'Documenta el proceso de gestión de cambios (CC8)', link: 'audit', label: 'Ir a Auditorías' },
      ],
      hipaa: [
        { action: 'Implementa controles de acceso a ePHI con MFA (§ 164.312.a.1)', link: 'controls' },
        { action: 'Cifra toda la información de salud protegida (§ 164.312.a.2.iv)', link: 'controls' },
        { action: 'Activa logs de auditoría para accesos a ePHI (§ 164.312.b)', link: 'controls' },
        { action: 'Define plan de contingencia y backups con pruebas (§ 164.312.a.2.ii)', link: 'controls' },
        { action: 'Evalúa y documenta riesgos sobre ePHI periódicamente (§ 164.308.a.1)', link: 'risks', label: 'Ir a Riesgos' },
      ],
    };

    const actions = actionsByFramework[key] || [];
    const actionsHtml = actions.map((a, i) => `
      <div style="display:flex;justify-content:space-between;align-items:center;
                  padding:10px 12px;${i%2===0?'background:var(--bg-2);':''}border-radius:6px;gap:12px;">
        <div style="font-size:12px;flex:1;">${UI.esc(a.action)}</div>
        ${a.link ? `<button class="btn btn-sm" style="flex-shrink:0;font-size:11px;"
          onclick="App.navigate('${a.link}');UI.closeModal();">${a.label||'Ver'}</button>` : ''}
      </div>`).join('');

    const scoreColor = score >= 75 ? '#059669' : score >= 50 ? '#D97706' : score >= 25 ? '#DC2626' : '#9D1B1B';

    return `
      <div style="display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap;margin-bottom:16px;">
        <div style="text-align:center;min-width:100px;">
          <div style="font-size:36px;font-weight:800;color:${scoreColor};">${score}</div>
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;">Puntuación</div>
        </div>
        <div style="flex:1;min-width:200px;">
          <p style="font-size:13px;color:var(--text-muted);margin:0 0 8px;">
            Puntuación calculada a partir de los controles implementados, gestión de riesgos e incidentes
            relevantes para ${UI.esc(label)}.
          </p>
          ${_gapsSection(gaps)}
        </div>
      </div>
      <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;">Acciones recomendadas</h4>
      ${actionsHtml}
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
          <p class="page-sub">Puntuacion multi-framework: ISO 27001 | ISO 22301 | NIS2 | NIST CSF 2.0 | ENS</p>
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
    _activeFrameworks = null;
    _ensLevel = null;
    _bcpCompData = null;
    try {
      const [data, implsList, ctx, realStatus, bcpComp] = await Promise.all([
        Api.compliance.summary().catch(() => ({})),
        Api.impls.list().catch(() => []),
        Api.get('/api/context/').catch(() => null),
        Api.complianceFrameworks.status().catch(() => null),
        Api.get('/api/bcp/compliance/iso22301').catch(() => null),
      ]);
      _compData = data;
      _implsData = implsList;
      // Inyectar datos ISO 22301 desde BCP/BCM (fuente de verdad: sección BCP)
      _bcpCompData = bcpComp;
      if (bcpComp && typeof bcpComp.score_global === 'number') {
        _compData.iso22301 = {
          score: bcpComp.score_global,
          clauses: bcpComp.clauses || [],
          kpis: bcpComp.kpis || {},
          locations: bcpComp.locations || [],
        };
      }
      if (ctx?.active_frameworks?.length) {
        _activeFrameworks = ctx.active_frameworks;
      }
      if (ctx?.ens_level) {
        _ensLevel = ctx.ens_level;
      }

      // Insertar panel de estado real multi-framework si hay datos nuevos
      if (realStatus && realStatus.frameworks && realStatus.frameworks.length > 0) {
        const realPanel = _buildRealStatusPanel(realStatus);
        content.innerHTML = realPanel;
        const legacyDiv = document.createElement('div');
        legacyDiv.id = 'comp-legacy';
        content.appendChild(legacyDiv);
        _render(legacyDiv, data);
      } else {
        _render(content, data);
      }

      // Wire legacy gap button
      const gapBtn = document.getElementById('btn-gap-analysis');
      if (gapBtn) gapBtn.onclick = _runGapAnalysis;
    } catch (e) {
      content.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _buildRealStatusPanel(status) {
    const fw = status.frameworks || [];
    const col = pct => pct >= 75 ? 'var(--risk-low)' : pct >= 50 ? 'var(--risk-medium)' : 'var(--risk-high)';
    const bar = (pct, c) => `<div style="background:#eee;border-radius:4px;height:8px;overflow:hidden;">
      <div style="width:${pct}%;background:${c};height:100%;border-radius:4px;"></div></div>`;

    const fwCards = fw.map(f => `
      <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:16px;min-width:200px;flex:1;">
        <div style="font-size:12px;font-weight:700;color:var(--brand-purple);margin-bottom:8px;">
          ${UI.esc(f.framework_name || f.framework_code)}
          ${f.is_audit_ready ? '<span style="background:#E8F5E9;color:#2e7d32;padding:2px 6px;border-radius:8px;font-size:10px;margin-left:4px;">✓ Audit Ready</span>' : ''}
        </div>
        <div style="font-size:28px;font-weight:800;color:${col(f.overall_pct)};">${f.overall_pct}%</div>
        <div style="font-size:11px;color:#9d9d9d;margin:4px 0 6px;">Cumplimiento global</div>
        ${bar(f.overall_pct, col(f.overall_pct))}
        ${f.gaps && f.gaps.length ? `<div style="font-size:11px;color:#c25a1f;margin-top:6px;">${f.gaps.length} gap(s)</div>` : ''}
      </div>`).join('');

    return `
      <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:20px;margin-bottom:20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <div>
            <h2 style="font-size:15px;font-weight:700;color:var(--brand-purple);margin:0;">
              Estado real de cumplimiento normativo
            </h2>
            <p style="color:#9d9d9d;font-size:12px;margin:4px 0 0;">
              Basado en controles implementados y evidencias subidas
            </p>
          </div>
          <div style="display:flex;gap:8px;">
            <a href="#/evidence" onclick="App.navigate('evidence');return false;"
               class="btn-outline" style="font-size:12px;padding:5px 12px;">+ Evidencias</a>
            <button onclick="ViewCompliance._configureFrameworks()"
                    class="btn-outline" style="font-size:12px;padding:5px 12px;">Configurar</button>
          </div>
        </div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;">${fwCards}</div>
        <div style="margin-top:12px;font-size:12px;color:#9d9d9d;">
          Cumplimiento global ponderado: <strong>${status.overall_pct || 0}%</strong> |
          Total gaps: <strong>${status.total_gaps || 0}</strong>
        </div>
      </div>
      <div id="comp-legacy-placeholder"></div>`;
  }

  function _render(content, data) {
    const meta = data._meta || {};
    const nist = data.nist_csf || {};
    const fns = nist.functions || {};
    const activeKeys = _getActiveFrameworkKeys();

    // Banner de normativas activas
    const fwBanner = (_activeFrameworks && _activeFrameworks.length > 0) ? `
      <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;
           background:var(--brand-purple-4);border:1px solid var(--brand-purple-3);
           border-radius:8px;padding:10px 14px;margin-bottom:16px;font-size:13px;">
        <div>
          <strong style="color:var(--brand-purple);">Normativas activas:</strong>
          ${activeKeys.map(k => {
            const m = _FW_META[k];
            const extra = (k === 'ens' && _ensLevel)
              ? ` <span style="font-size:10px;background:var(--brand-purple);color:#fff;border-radius:3px;padding:1px 5px;">
                    ${_ensLevel.toUpperCase()}</span>` : '';
            return m ? `<span class="badge badge-muted" style="margin-left:4px;">${m.label}${extra}</span>` : '';
          }).join('')}
        </div>
        <a href="#questionnaire" onclick="App.navigate('questionnaire');return false;"
           style="font-size:11px;color:var(--brand-purple);text-decoration:underline;">
          Cambiar normativas
        </a>
      </div>` : `
      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;
           padding:10px 14px;margin-bottom:16px;font-size:12px;color:var(--text-muted);">
        Mostrando todos los frameworks. Ejecuta el <a href="#questionnaire"
          onclick="App.navigate('questionnaire');return false;"
          style="color:var(--brand-purple);">cuestionario IA</a>
        y selecciona las normativas aplicables para personalizar esta vista.
      </div>`;

    // Paneles de brechas — solo frameworks activos
    const gapPanels = activeKeys
      .filter(k => ['iso27001','nis2','nist_csf','ens'].includes(k))
      .map(k => {
        const m = _FW_META[k];
        if (!k || !m) return '';
        if (k === 'nist_csf') return `
          <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;">
            <h3 style="font-size:14px;font-weight:700;margin:0 0 4px;">NIST CSF 2.0 — Funciones</h3>
            <p style="font-size:12px;color:var(--text-muted);margin:0 0 8px;">Cobertura por función</p>
            ${_nistFunctionsHtml(fns)}
          </div>`;
        const d = data[m.dataKey] || {};
        const subtitle = k === 'ens'
          ? (_ensLevel ? `Nivel ${_ensLevel.charAt(0).toUpperCase()+_ensLevel.slice(1)} · Anexo II` : 'Anexo II')
          : (k === 'nis2' ? 'Art. 21 y 23' : 'Cláusula 6.1.3 y 10.1');
        return `
          <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;">
            <h3 style="font-size:14px;font-weight:700;margin:0 0 4px;">${m.label} — Brechas</h3>
            <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">${subtitle}</p>
            ${_gapsHtml(d.gaps)}
          </div>`;
      }).filter(Boolean);

    // Agrupar en filas de 2
    const gapRows = [];
    for (let i = 0; i < gapPanels.length; i += 2) {
      gapRows.push(`<div style="display:grid;grid-template-columns:${gapPanels[i+1] ? '1fr 1fr' : '1fr'};gap:16px;margin-bottom:16px;" class="compliance-detail-grid">
        ${gapPanels[i]}${gapPanels[i+1] || ''}
      </div>`);
    }

    content.innerHTML = `
      ${fwBanner}
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

      <!-- Gauges por framework (solo activos) -->
      <div id="comp-gauges" style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px;"></div>

      <!-- Panel de detalle expandible -->
      <div id="comp-detail-panel" style="display:none;margin-bottom:20px;"></div>

      <!-- Paneles de brechas por normativa activa -->
      ${gapRows.join('')}

      <p style="font-size:11px;color:var(--text-muted);margin-top:16px;text-align:center;">
        Puntuaciones calculadas a partir de los datos registrados en RiskHub.
        Actualizar regularmente para reflejar el estado real del SGSI.
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
              ${activeKeys.map(k => {
                const m = _FW_META[k];
                return m ? `<option value="${k}">${m.label}</option>` : '';
              }).join('')}
            </select>
            <button class="btn btn-primary" id="btn-gap-analysis">Analizar brechas</button>
          </div>
        </div>
        <div id="gap-results" style="display:none;"></div>
      </div>
    `;
    // Rellenar gauges ahora que el DOM está listo
    _rerenderGaugesAndPanels();
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

  // ============================================================
  // Modal de madurez / gap analysis por control (ISO 27001 panel)
  // ============================================================

  const _GAP_MATURITY_LABELS = ['Inexistente', 'Inicial', 'Basico', 'Definido', 'Gestionado', 'Optimizado'];

  // Texto generico cuando no hay analisis IA guardado
  const _GAP_DEFAULT_WHY = [
    'Este control no existe ni esta configurado en la organizacion. No aporta reduccion del riesgo.',
    'El control existe de forma ad-hoc, sin proceso formal ni documentacion. Reduccion minima e inconsistente.',
    'El control esta documentado pero su aplicacion es inconsistente o incompleta. Reduccion parcial del riesgo.',
    'El control esta implementado de forma estandarizada pero sin revisiones periodicas ni metricas de eficacia.',
    'El control se mide y gestiona activamente con metricas definidas. Falta implementar mejora continua formal.',
    '',
  ];

  const _GAP_DEFAULT_GAP = [
    'Implementar el control desde cero: definir el proceso, documentarlo, asignar responsable, establecer metricas y revision periodica.',
    'Formalizar el proceso: crear documentacion oficial, establecer procedimientos escritos, comunicar a los equipos y medir resultados.',
    'Estandarizar la aplicacion: garantizar consistencia en todos los casos, implementar controles de calidad y medir la eficacia con KPIs definidos.',
    'Añadir metricas de eficacia: establecer KPIs, revisar resultados periodicamente, documentar excepciones y reducir la variabilidad del proceso.',
    'Implementar mejora continua: analizar tendencias, automatizar donde sea posible, revisar benchmarks del sector y documentar las optimizaciones.',
    '',
  ];

  function _gapMaturityColor(v) {
    if (v >= 5) return 'var(--risk-low)';
    if (v >= 4) return '#22c55e';
    if (v >= 3) return 'var(--risk-medium)';
    if (v >= 2) return 'var(--risk-high)';
    return 'var(--risk-critical)';
  }

  function _gapMaturityBarFull(v) {
    const color = _gapMaturityColor(v);
    const bars = Array.from({length: 5}, (_, i) =>
      `<div style="width:20px;height:12px;border-radius:3px;background:${i < v ? color : 'var(--bg-3)'};"></div>`
    ).join('');
    return `<div style="display:flex;gap:4px;align-items:center;">
      ${bars}
      <span style="font-size:14px;font-weight:800;color:${color};margin-left:8px;">${v}/5</span>
      <span style="font-size:12px;color:var(--text-muted);margin-left:4px;">${_GAP_MATURITY_LABELS[v] || ''}</span>
    </div>`;
  }

  function _parseGapNotes(notes) {
    if (!notes) return { rationale: '', gap: '' };
    const gapSep = '\n\nPara llegar a nivel 5: ';
    const gapIdx = notes.indexOf(gapSep);
    let rationale = notes;
    let gap = '';
    if (gapIdx >= 0) {
      rationale = notes.slice(0, gapIdx);
      gap = notes.slice(gapIdx + gapSep.length);
    }
    rationale = rationale.replace(/^Nivel actual \(\d+\/5\): /, '');
    return { rationale, gap };
  }

  function _showGapModal(implId) {
    const raw = (_implsData || []).find(i => i.id === implId);
    if (!raw) { UI.toast('Sin datos de madurez disponibles para este control', 'info'); return; }
    const c = _flatImpl(raw);
    const { rationale, gap } = _parseGapNotes(c.notes);
    const color = _gapMaturityColor(c.maturity);
    const v = Math.min(5, Math.max(0, c.maturity || 0));

    // Usar texto IA si existe, sino texto generico por nivel
    const isAI = !!(rationale || gap);
    const displayRationale = rationale || _GAP_DEFAULT_WHY[v] || '';
    const displayGap = gap || _GAP_DEFAULT_GAP[v] || '';

    const aiNote = isAI
      ? `<div style="font-size:10px;color:var(--risk-low);margin-bottom:12px;">
           Analisis generado por IA a partir del documento fuente
         </div>`
      : `<div style="font-size:10px;color:var(--text-muted);margin-bottom:12px;">
           Descripcion generica por nivel de madurez &mdash;
           sube el documento al Agente IA para obtener analisis personalizado
         </div>`;

    UI.openModal(`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">Analisis de madurez</h3>
        <button class="btn btn-ghost btn-sm" onclick="UI.closeModal()">&#10005;</button>
      </div>

      <div style="margin-bottom:12px;">
        <span style="font-size:11px;font-weight:700;background:var(--brand-purple-4);color:var(--brand-purple);
                     border-radius:3px;padding:2px 8px;margin-right:8px;">${UI.esc(c.code || '-')}</span>
        <span style="font-size:14px;font-weight:700;">${UI.esc(c.name || '-')}</span>
      </div>

      <div style="background:var(--bg-2);border-radius:8px;padding:14px 16px;margin-bottom:10px;">
        ${_gapMaturityBarFull(c.maturity)}
      </div>

      ${aiNote}

      ${displayRationale ? `
        <div style="margin-bottom:14px;">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);
                      letter-spacing:.6px;margin-bottom:6px;">Por que esta en nivel ${v}/5</div>
          <div style="font-size:13px;line-height:1.7;color:var(--text-base);background:var(--bg-2);
                      border-radius:6px;padding:12px 14px;border-left:4px solid ${color};">
            ${UI.esc(displayRationale)}
          </div>
        </div>` : ''}

      ${displayGap ? `
        <div>
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);
                      letter-spacing:.6px;margin-bottom:6px;">Para llegar a nivel 5 (Optimizado)</div>
          <div style="font-size:13px;line-height:1.7;color:var(--text-base);
                      background:rgba(89,0,141,.05);border-radius:6px;padding:12px 14px;
                      border-left:4px solid var(--brand-purple);">
            ${UI.esc(displayGap)}
          </div>
        </div>` : ''}

      <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border);
                  display:flex;justify-content:flex-end;gap:8px;">
        <a href="#/controls" onclick="UI.closeModal();" class="btn btn-ghost" style="font-size:12px;">
          Ver en Controles
        </a>
        <button onclick="UI.closeModal();" class="btn btn-primary" style="font-size:12px;">Cerrar</button>
      </div>
    `, { width: '640px' });
  }

  function _configureFrameworks() {
    Api.complianceFrameworks.list().then(available => {
      Api.get('/api/context/').then(ctx => {
        const active = (ctx && ctx.active_frameworks) || [];
        const checkboxes = available.map(fw => `
          <label style="display:flex;align-items:center;gap:8px;padding:6px 0;cursor:pointer;">
            <input type="checkbox" class="fw-cb" value="${UI.esc(fw.code)}"
                   ${active.includes(fw.code) ? 'checked' : ''}>
            <div>
              <div style="font-size:13px;font-weight:600;">${UI.esc(fw.name)}</div>
              <div style="font-size:11px;color:#9d9d9d;">${fw.requirements_count} requisitos</div>
            </div>
          </label>`).join('');
        UI.openModal(`
          <h3 style="margin:0 0 16px;color:var(--brand-purple);">Configurar frameworks normativos</h3>
          <p style="font-size:13px;color:#666;margin-bottom:12px;">
            Selecciona los frameworks que debe cumplir tu organización.
          </p>
          <div style="max-height:350px;overflow-y:auto;">${checkboxes}</div>
          <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;">
            <button onclick="UI.closeModal()" class="btn-outline">Cancelar</button>
            <button onclick="ViewCompliance._saveFrameworks()" class="btn-primary">Guardar</button>
          </div>`);
      }).catch(() => UI.toast('Error cargando contexto', 'error'));
    }).catch(() => UI.toast('Error cargando frameworks', 'error'));
  }

  async function _saveFrameworks() {
    const selected = [...document.querySelectorAll('.fw-cb:checked')].map(c => c.value);
    if (!selected.length) { UI.toast('Selecciona al menos un framework', 'error'); return; }
    try {
      await Api.complianceFrameworks.subscribe({ frameworks: selected });
      UI.closeModal();
      UI.toast('Frameworks configurados correctamente', 'success');
      setTimeout(() => location.reload(), 800);
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  return { render, _togglePanel, _filterGapTable: () => {}, _configureFrameworks, _saveFrameworks, _showGapModal };
})();
