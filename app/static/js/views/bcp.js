/* BCP/BIA — Continuidad de negocio (ISO 22301) — Plataforma BCM */
const ViewBcp = (() => {

  // ── Estado de navegacion ─────────────────────────────────────────────────────
  let _currentMode = 'operar';
  let _currentStep = 1;
  let _currentTile = 'dashboard';
  let _currentSubTabs = { 2: 'procesos', 3: 'dependencies', 4: 'strategies', 5: 'evidence' };
  let _bcmContext = null;
  let _aiPanelInitialized = false;
  let _activeTab = 'overview'; // backward compat

  const CRIT_COLORS = { critical:'#DC2626', high:'#D97706', medium:'#2563EB', low:'#16a34a' };
  const IMPL_COLORS = { planned:'#6B7280', in_progress:'#D97706', implemented:'#2563EB', tested:'#16a34a' };
  const STATUS_COLORS = { draft:'#6B7280', under_review:'#D97706', approved:'#16a34a', deprecated:'#DC2626' };

  let _procs = [], _deps = [], _strats = [], _plans = [], _tests = [], _slinks = [], _suppliers = [];
  let _container = null;
  let _locationFilter = null;
  let _locations = [];
  let _locationMap = {};

  function _locParam(sep) {
    if (!_locationFilter) return '';
    return (sep !== undefined ? sep : '?') + 'location_id=' + _locationFilter;
  }


  async function _loadLocations() {
    try {
      const tree = await Api.get('/api/bcp/locations').catch(() => []);
      _locations = tree;
      const flat = [];
      (function flatten(nodes, depth) {
        nodes.forEach(n => { flat.push({...n, depth}); flatten(n.children || [], depth + 1); });
      })(tree, 0);
      flat.forEach(l => { _locationMap[l.id] = l; });
      const sel = document.getElementById('bcm-sede-select') || document.getElementById('bcp-loc-select');
      if (!sel) return;
      while (sel.options.length > 1) sel.remove(1);
      flat.forEach(loc => {
        const opt = document.createElement('option');
        opt.value = loc.id;
        opt.textContent = ' '.repeat(loc.depth * 2) + loc.name;
        if (loc.id === _locationFilter) opt.selected = true;
        sel.appendChild(opt);
      });
      if (!sel._bcmListenerAdded) {
        sel._bcmListenerAdded = true;
        sel.addEventListener('change', () => {
          _locationFilter = sel.value ? parseInt(sel.value) : null;
          _updateSedeBadge();
          _loadSedeStats();
          _renderContent();
        });
      }
    } catch (e) { console.warn('BCM: no se pudieron cargar localizaciones', e); }
  }

  function _updateSedeBadge() {
    const badge = document.getElementById('bcm-sede-badge');
    if (!badge) return;
    if (_locationFilter) {
      badge.style.display = 'inline-flex';
      const nameEl = badge.querySelector('.bcm-sede-name');
      if (nameEl) nameEl.textContent = _locationMap[_locationFilter]?.name || '';
    } else {
      badge.style.display = 'none';
    }
  }

  async function _loadSedeStats() {
    const el = document.getElementById('bcm-sede-stats');
    if (!el) return;
    try {
      const c = await Api.get('/api/bcp/compliance/iso22301' + _locParam()).catch(() => null);
      if (!c) { el.innerHTML = ''; return; }
      const k = c.kpis || {};
      const score = c.score_global || 0;
      const sc = score >= 70 ? '#16a34a' : score >= 40 ? '#ca8a04' : '#dc2626';
      let statsHtml = '<span class="bcm-stat" style="color:' + sc + '"><i class="ti ti-shield-check"></i> ' + score + '%</span>';
      statsHtml += '<span class="bcm-stat"><i class="ti ti-sitemap"></i> ' + (k.processes_total || 0) + ' proc.</span>';
      statsHtml += '<span class="bcm-stat"><i class="ti ti-file-text"></i> ' + (k.plans_approved || 0) + '/' + (k.plans_total || 0) + ' planes</span>';
      if ((k.tests_overdue || 0) > 0) {
        statsHtml += '<span class="bcm-stat" style="color:#dc2626"><i class="ti ti-alert-triangle"></i> ' + k.tests_overdue + ' test vencido</span>';
      }
      el.innerHTML = statsHtml;
    } catch (_) { el.innerHTML = ''; }
  }

  // Entry point

  async function render(container) {
    _container = container;
    _bcmContext = await Api.get('/api/bcp/context').catch(() => null);

    const wizardLabel = (_bcmContext && _bcmContext.wizard_completed) ? 'Contexto IA' : 'Configurar IA';
    const wizardDot = (!_bcmContext || !_bcmContext.wizard_completed) ? '<span class="bcm-badge-dot"></span>' : '';

    container.innerHTML = '<div class="bcm-platform">'
      + '<div class="bcm-header">'
      + '<div class="bcm-header-row1">'
      + '<div class="bcm-brand">'
      + '<i class="ti ti-shield-check" style="color:var(--primary);font-size:19px"></i>'
      + '<div>'
      + '<div style="font-size:15px;font-weight:700;line-height:1.2">Continuidad de Negocio</div>'
      + '<div style="font-size:11px;color:var(--text-subtle)">ISO 22301 &middot; NIS2 Art.21.2(b) &middot; ISO 27001 A.5.29</div>'
      + '</div></div>'
      + '<div class="bcm-mode-toggle">'
      + '<button class="bcm-mode-btn" id="bcm-btn-config" onclick="ViewBcp._setMode(\'config\')"><i class="ti ti-settings-2"></i> Configurar BCP</button>'
      + '<button class="bcm-mode-btn active" id="bcm-btn-operar" onclick="ViewBcp._setMode(\'operar\')"><i class="ti ti-activity"></i> Operar BCP</button>'
      + '</div>'
      + '<div style="display:flex;gap:8px;align-items:center">'
      + '<button class="btn btn-ghost btn-sm" id="btn-bcm-wizard" title="Configurar contexto del agente IA">'
      + '<i class="ti ti-brain"></i> <span id="bcm-wizard-label">' + wizardLabel + '</span>' + wizardDot + '</button>'
      + '<button class="btn btn-ghost btn-sm" onclick="ViewBcp._exportBcp()"><i class="ti ti-file-export"></i> Exportar</button>'
      + '</div></div>'
      + '<div class="bcm-sede-bar">'
      + '<i class="ti ti-map-pin" style="color:var(--text-subtle);font-size:13px;flex-shrink:0"></i>'
      + '<span class="bcm-sede-label">Sede:</span>'
      + '<select id="bcm-sede-select" class="bcm-sede-select">'
      + '<option value="">Vista corporativa (todas las sedes)</option>'
      + '</select>'
      + '<span id="bcm-sede-badge" style="display:none" class="bcm-sede-badge">'
      + '<i class="ti ti-map-pin" style="font-size:10px"></i>'
      + '<span class="bcm-sede-name"></span>'
      + '<button onclick="ViewBcp._clearSede()" title="Ver todas">&times;</button>'
      + '</span>'
      + '<div id="bcm-sede-stats" class="bcm-sede-stats-row"></div>'
      + '</div></div>'
      + '<div class="bcm-content" id="bcm-content">'
      + '<div style="padding:40px;text-align:center;color:var(--text-subtle)"><i class="ti ti-loader-2 ti-spin"></i> Cargando...</div>'
      + '</div></div>';

    _initAiPanel();

    container.querySelector('#btn-bcm-wizard').addEventListener('click', () => {
      _currentStep = 0;
      _renderContent();
    });

    await _loadLocations();
    await _renderContent();
    _loadSedeStats();
  }

  // Navigation

  function _setMode(mode) {
    _currentMode = mode;
    if (_currentStep === 0) _currentStep = 1; // escapar wizard si estaba activo
    document.getElementById('bcm-btn-config')?.classList.toggle('active', mode === 'config');
    document.getElementById('bcm-btn-operar')?.classList.toggle('active', mode === 'operar');
    _renderContent();
  }

  function _setStep(step) {
    _currentMode = 'config';
    _currentStep = step;
    document.getElementById('bcm-btn-config')?.classList.add('active');
    document.getElementById('bcm-btn-operar')?.classList.remove('active');
    _renderContent();
  }

  function _setTile(tile) {
    _currentMode = 'operar';
    _currentStep = 1; // escapar wizard si estaba activo
    _currentTile = tile;
    _renderContent();
  }

  function _setSubTab(step, tab) {
    _currentSubTabs[step] = tab;
    _renderContent();
  }

  function _clearSede() {
    _locationFilter = null;
    const sel = document.getElementById('bcm-sede-select');
    if (sel) sel.value = '';
    _updateSedeBadge();
    _loadSedeStats();
    _renderContent();
  }

  function _exportBcp() {
    window.location.href = '/api/bcp/export';
  }

  // Backward compat
  function _switchTab(tab) {
    const toStep = { locations:1, processes:2, bia:2, dependencies:3, suppliers:3, strategies:4, plans:4, evidence:5, import:5 };
    const toTile = { overview:'dashboard', graph:'graph', tests:'tests', recommendations:'alertas' };
    if (toStep[tab]) _setStep(toStep[tab]);
    else if (toTile[tab]) { _currentTile = toTile[tab]; _setMode('operar'); }
    else _renderContent();
  }

  function _renderActiveTab() { _renderContent(); }

  // Render dispatcher

  async function _renderContent() {
    const content = document.getElementById('bcm-content');
    if (!content) return;
    content.innerHTML = '<div style="padding:30px;text-align:center;color:var(--text-subtle)"><i class="ti ti-loader-2 ti-spin"></i></div>';
    try {
      if (_currentStep === 0) {
        await _contextWizard(content);
      } else if (_currentMode === 'config') {
        await _renderConfigMode(content);
      } else {
        await _renderOperarMode(content);
      }
    } catch (e) {
      console.error('[BCM]', e);
      content.innerHTML = '<div class="notice notice-error">Error: ' + UI.esc(e.message) + '</div>';
    }
  }

  // ── Tab Overview ─────────────────────────────────────────────────────────────

  async function _tabOverview(el) {
    const [dash, isoResp, procs, deps, plans, tests] = await Promise.all([
      Api.get('/api/bcp/dashboard').catch(() => ({})),
      Api.get('/api/bcp/iso22301-status').catch(() => ({})),
      Api.get('/api/bcp/processes').catch(() => []),
      Api.get('/api/bcp/dependencies').catch(() => []),
      Api.get('/api/bcp/plans').catch(() => []),
      Api.get('/api/bcp/tests').catch(() => []),
    ]);
    // poblar cache para tabs que se visiten a continuacion
    if (procs.length) _procs = procs;
    if (deps.length)  _deps  = deps;
    if (plans.length) _plans = plans;
    if (tests.length) _tests = tests;

    // La API ahora devuelve un dict {clauses, pct, implemented, partial, total, is_ready}
    const iso = isoResp && isoResp.clauses ? isoResp : { clauses: [], pct: 0, implemented: 0, partial: 0, total: 0 };
    const clauses = iso.clauses || [];
    const gaps = clauses.filter(c => c.status === 'gap');
    const partials = clauses.filter(c => c.status === 'partial');
    const implemented = clauses.filter(c => c.status === 'implemented');

    const pctColor = iso.pct >= 80 ? 'var(--risk-low)' : iso.pct >= 50 ? 'var(--risk-medium)' : 'var(--risk-critical)';

    el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <div style="display:flex;align-items:center;gap:12px;">
        <div style="font-size:28px;font-weight:800;color:${pctColor}">${iso.pct}%</div>
        <div>
          <div style="font-size:13px;font-weight:600;">Cumplimiento ISO 22301</div>
          <div style="font-size:11px;color:var(--text-subtle);">${implemented.length} implementadas · ${partials.length} parciales · ${gaps.length} gaps de ${iso.total}</div>
        </div>
      </div>
      <button class="btn btn-secondary" id="btn-bcp-ai-analyze" style="display:flex;align-items:center;gap:6px;">
        <i class="ti ti-brain"></i> Analizar gaps con IA
      </button>
    </div>
    <div id="bcp-ai-result"></div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;">
      <div class="stat-card">
        <div class="stat-value">${dash.total_processes ?? 0}</div>
        <div class="stat-label">Procesos registrados</div>
      </div>
      <div class="stat-card ${(dash.bia_avg_pct ?? 0) < 60 ? 'stat-warning' : ''}">
        <div class="stat-value">${dash.bia_avg_pct ?? 0}%</div>
        <div class="stat-label">BIA completado (media)</div>
      </div>
      <div class="stat-card ${(dash.approved_plans ?? 0) === 0 ? 'stat-warning' : ''}">
        <div class="stat-value">${dash.approved_plans ?? 0}</div>
        <div class="stat-label">Planes aprobados</div>
      </div>
      <div class="stat-card ${(dash.processes_overdue_test ?? 0) > 0 ? 'stat-danger' : ''}">
        <div class="stat-value">${dash.tests_done ?? 0}</div>
        <div class="stat-label">Tests realizados</div>
      </div>
    </div>

    ${gaps.length > 0 ? `
    <div class="notice notice-warning" style="margin-bottom:16px;">
      <strong>Gaps ISO 22301 detectados:</strong>
      ${gaps.map(g => `<span class="badge badge-danger" style="margin:2px;">${UI.esc(g.id)} ${UI.esc(g.name)}</span>`).join('')}
    </div>` : ''}

    <div style="display:grid;grid-template-columns:3fr 1fr;gap:16px;">
      <div class="card">
        <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;">
          <h3 style="margin:0;">Checklist ISO 22301:2019 — ${iso.total} clausulas</h3>
        </div>
        <div class="card-body" style="padding:0 16px;">
          ${clauses.map(c => `
          <div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:0.5px solid var(--border)">
            <i class="ti ${c.status==='implemented' ? 'ti-circle-check' : c.status==='partial' ? 'ti-circle-half-2' : 'ti-circle-x'}"
               style="color:${c.status==='implemented' ? 'var(--risk-low)' : c.status==='partial' ? 'var(--risk-medium)' : 'var(--risk-critical)'};font-size:16px;flex-shrink:0;margin-top:2px"></i>
            <div style="flex:1;min-width:0">
              <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                <span style="font-size:11px;font-weight:700;color:var(--text-subtle);font-family:var(--font-mono)">${UI.esc(c.id)}</span>
                <span style="font-size:13px;font-weight:500">${UI.esc(c.name)}</span>
                <span style="font-size:10px;color:var(--text-subtle);margin-left:auto">${UI.esc(c.reference || '')}</span>
              </div>
              <div style="font-size:11px;color:var(--text-subtle);margin-top:2px">${UI.esc(c.detail || '')}</div>
            </div>
          </div>`).join('')}
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:12px;">
        <div class="card">
          <div class="card-header"><h3 style="margin:0;font-size:13px;">Actividad</h3></div>
          <div class="card-body" style="padding:12px;">
            <div style="display:grid;gap:8px;font-size:13px;">
              <div style="display:flex;justify-content:space-between;">
                <span style="color:var(--text-subtle)">Sin test (12m)</span>
                <strong style="color:${(dash.processes_overdue_test??0)>0?'var(--risk-critical)':'var(--risk-low)'}">${dash.processes_overdue_test ?? 0}</strong>
              </div>
              <div style="display:flex;justify-content:space-between;">
                <span style="color:var(--text-subtle)">Tests totales</span>
                <strong>${dash.total_tests ?? 0}</strong>
              </div>
              <div style="display:flex;justify-content:space-between;">
                <span style="color:var(--text-subtle)">Criticos</span>
                <strong>${dash.critical_processes ?? 0}</strong>
              </div>
              <div style="display:flex;justify-content:space-between;">
                <span style="color:var(--text-subtle)">Ultimo test</span>
                <strong style="font-size:11px">${dash.last_test_date ? new Date(dash.last_test_date).toLocaleDateString('es-ES') : '—'}</strong>
              </div>
            </div>
          </div>
        </div>
        <div class="card">
          <div class="card-header"><h3 style="margin:0;font-size:13px;">Cumplimiento</h3></div>
          <div class="card-body" style="padding:12px;">
            <div style="display:grid;gap:6px;font-size:12px;">
              <div style="display:flex;justify-content:space-between;">
                <span style="color:var(--risk-low)">Implementadas</span><strong>${implemented.length}</strong>
              </div>
              <div style="display:flex;justify-content:space-between;">
                <span style="color:var(--risk-medium)">Parciales</span><strong>${partials.length}</strong>
              </div>
              <div style="display:flex;justify-content:space-between;">
                <span style="color:var(--risk-critical)">Gaps</span><strong>${gaps.length}</strong>
              </div>
              ${iso.is_ready ? `<div style="margin-top:6px;padding:6px;background:var(--success-soft,#dcfce7);border-radius:6px;font-size:11px;color:var(--risk-low);font-weight:600;text-align:center;">Lista para certificacion</div>` : ''}
            </div>
          </div>
        </div>
      </div>
    </div>
    <div id="bcp-continuity-map"><div style="padding:20px;text-align:center;color:var(--text-subtle);font-size:13px;">Cargando mapa...</div></div>`;

    document.getElementById('btn-bcp-ai-analyze')?.addEventListener('click', _runBcpAiAnalysis);

    // Renderizar mapa conceptual y KPIs debajo del checklist
    const mapWrap = document.getElementById('bcp-continuity-map');
    if (mapWrap) _renderContinuityMap(mapWrap, procs, deps, plans, tests, dash);
  }

  // ── Mapa conceptual de continuidad ───────────────────────────────────────────

  function _renderContinuityMap(wrap, procs, deps, plans, tests, dash) {
    if (!procs.length) {
      wrap.innerHTML = `<div style="text-align:center;padding:32px;color:var(--text-subtle);font-size:13px;">
        Registra procesos criticos para ver el mapa de continuidad.
      </div>`;
      return;
    }

    // Colores y datos derivados
    const CRIT_COLOR  = { critical:'#DC2626', high:'#D97706', medium:'#2563EB', low:'#16a34a' };
    const CRIT_BG     = { critical:'#FEF2F2', high:'#FFFBEB', medium:'#EFF6FF', low:'#F0FDF4' };
    const CRIT_ORDER  = { critical:0, high:1, medium:2, low:3 };
    const CRIT_LABEL  = { critical:'CRITICA', high:'ALTA', medium:'MEDIA', low:'BAJA' };

    const approvedPlanIds = new Set(
      plans.filter(p => p.status === 'approved' || p.status === 'active')
           .flatMap(p => p.process_ids || [])
    );
    const testByProc = {};
    tests.forEach(t => (t.process_ids || []).forEach(pid => {
      if (!testByProc[pid] || t.conducted_at > (testByProc[pid].conducted_at || '')) testByProc[pid] = t;
    }));

    // Agrupar por criticidad
    const sorted = [...procs].sort((a, b) => (CRIT_ORDER[a.criticality]||4) - (CRIT_ORDER[b.criticality]||4));
    const groups = {};
    sorted.forEach(p => {
      const c = p.criticality || 'low';
      (groups[c] = groups[c] || []).push(p);
    });

    // Layout de nodos en cuadrícula SVG
    const NR       = 38;     // radio del nodo
    const H_GAP    = 130;    // separacion horizontal entre centros
    const V_GAP    = 110;    // separacion vertical entre filas
    const PAD_TOP  = 28;
    const PAD_LEFT = 64;     // espacio para etiqueta de fila
    const rows     = Object.entries(groups).filter(([,g]) => g.length);
    const maxPerRow= Math.max(...rows.map(([,g]) => g.length));
    const SVG_W    = Math.max(480, PAD_LEFT + maxPerRow * H_GAP + 20);
    const SVG_H    = PAD_TOP + rows.length * V_GAP + 30;

    const pos = {};  // pid -> {x, y}
    rows.forEach(([crit, group], rowIdx) => {
      const totalW = (group.length - 1) * H_GAP;
      const startX = PAD_LEFT + (SVG_W - PAD_LEFT - totalW) / 2;
      group.forEach((p, i) => { pos[p.id] = { x: startX + i * H_GAP, y: PAD_TOP + NR + rowIdx * V_GAP }; });
    });

    // Líneas de dependencia (proceso-a-proceso)
    const procDepLines = deps
      .filter(d => d.depends_on_process_id && pos[d.process_id] && pos[d.depends_on_process_id])
      .map(d => {
        const f = pos[d.depends_on_process_id], t = pos[d.process_id];
        const dx = t.x - f.x, dy = t.y - f.y;
        const dist = Math.sqrt(dx*dx + dy*dy) || 1;
        const ux = dx/dist, uy = dy/dist;
        const x1 = f.x + ux*NR, y1 = f.y + uy*NR;
        const x2 = t.x - ux*(NR+8), y2 = t.y - uy*(NR+8);
        const mx = (x1+x2)/2, my = (y1+y2)/2 - 20;
        return `<path d="M${x1},${y1} Q${mx},${my} ${x2},${y2}"
          fill="none" stroke="#94A3B8" stroke-width="1.5" stroke-dasharray="5 3"
          marker-end="url(#bcp-arrow)" opacity="0.7"/>`;
      }).join('');

    // Nodos de proceso
    const nodesSvg = sorted.map(p => {
      const pt = pos[p.id]; if (!pt) return '';
      const col   = CRIT_COLOR[p.criticality] || '#6B7280';
      const bg    = CRIT_BG[p.criticality]    || '#F9FAFB';
      const bia   = p.bia_pct || 0;
      const circ  = 2 * Math.PI * NR;
      const dash  = (bia / 100) * circ;
      const hasPlan  = approvedPlanIds.has(p.id);
      const testR    = testByProc[p.id]?.result;
      const testCol  = testR === 'passed' ? '#16a34a' : testR === 'partial' ? '#D97706' : testR === 'failed' ? '#DC2626' : null;
      const biaCol   = bia >= 80 ? '#16a34a' : bia >= 50 ? '#D97706' : '#DC2626';

      // Nombre truncado en 2 líneas de ~13 chars
      const words = p.name.split(' ');
      let l1 = '', l2 = '';
      for (const w of words) {
        if (!l1 || (l1+' '+w).length <= 13) l1 = l1 ? l1+' '+w : w;
        else if (!l2 || (l2+' '+w).length <= 13) l2 = l2 ? l2+' '+w : w;
      }
      if (l2.length > 13) l2 = l2.substring(0,12) + '…';

      return `
      <g data-id="${p.id}" onclick="ViewBcp._switchTab('processes')"
         style="cursor:pointer;" role="button" aria-label="${p.name.replace(/"/g,'&quot;')}">
        <title>${p.name} | BIA: ${bia}% | ${p.criticality}${hasPlan ? ' | Plan aprobado' : ''}${testR ? ' | Test: ' + testR : ''}</title>
        <!-- halo plan aprobado -->
        ${hasPlan ? `<circle cx="${pt.x}" cy="${pt.y}" r="${NR+9}" fill="none" stroke="#16a34a" stroke-width="2" opacity="0.4"/>` : ''}
        <!-- fondo -->
        <circle cx="${pt.x}" cy="${pt.y}" r="${NR+2}" fill="${bg}" stroke="${col}" stroke-width="1.5"/>
        <!-- ring track -->
        <circle cx="${pt.x}" cy="${pt.y}" r="${NR}" fill="none" stroke="#E2E8F0" stroke-width="5"/>
        <!-- ring BIA -->
        <circle cx="${pt.x}" cy="${pt.y}" r="${NR}" fill="none" stroke="${biaCol}" stroke-width="5"
                stroke-linecap="round" stroke-dasharray="${dash.toFixed(1)} ${circ.toFixed(1)}"
                transform="rotate(-90 ${pt.x} ${pt.y})"/>
        <!-- relleno interior -->
        <circle cx="${pt.x}" cy="${pt.y}" r="${NR-7}" fill="${col}" fill-opacity="0.12"/>
        <!-- texto nombre -->
        <text x="${pt.x}" y="${l2 ? pt.y - 7 : pt.y}" text-anchor="middle" dominant-baseline="middle"
              font-size="9.5" font-weight="700" fill="${col}" font-family="Inter,system-ui,sans-serif">${UI.esc(l1)}</text>
        ${l2 ? `<text x="${pt.x}" y="${pt.y + 9}" text-anchor="middle" dominant-baseline="middle"
              font-size="9.5" font-weight="700" fill="${col}" font-family="Inter,system-ui,sans-serif">${UI.esc(l2)}</text>` : ''}
        <!-- BIA % -->
        <text x="${pt.x}" y="${pt.y + NR + 14}" text-anchor="middle"
              font-size="9" font-weight="700" fill="${biaCol}" font-family="Inter,system-ui,sans-serif">BIA ${bia}%</text>
        <!-- badge test -->
        ${testCol ? `<circle cx="${pt.x + NR - 3}" cy="${pt.y + NR - 3}" r="7" fill="${testCol}" stroke="white" stroke-width="1.5"/>
          <text x="${pt.x + NR - 3}" y="${pt.y + NR - 3}" text-anchor="middle" dominant-baseline="middle"
                font-size="8" fill="white" font-weight="700">T</text>` : ''}
        <!-- badge plan -->
        ${hasPlan ? `<circle cx="${pt.x - NR + 3}" cy="${pt.y - NR + 3}" r="7" fill="#16a34a" stroke="white" stroke-width="1.5"/>
          <text x="${pt.x - NR + 3}" y="${pt.y - NR + 3}" text-anchor="middle" dominant-baseline="middle"
                font-size="8" fill="white" font-weight="700">P</text>` : ''}
      </g>`;
    }).join('');

    // Etiquetas de fila (criticidad)
    const rowLabels = rows.map(([crit], i) => {
      const y = PAD_TOP + NR + i * V_GAP;
      return `<text x="4" y="${y}" dominant-baseline="middle"
                    font-size="8.5" font-weight="800" fill="${CRIT_COLOR[crit]||'#666'}"
                    font-family="Inter,system-ui,sans-serif" letter-spacing="0.08em"
                    transform="rotate(-90, 20, ${y})">${CRIT_LABEL[crit]||crit}</text>`;
    }).join('');

    // KPIs adicionales
    const critCount  = procs.filter(p => p.criticality === 'critical').length;
    const highCount  = procs.filter(p => p.criticality === 'high').length;
    const withPlan   = procs.filter(p => approvedPlanIds.has(p.id)).length;
    const withTest   = procs.filter(p => testByProc[p.id]?.result === 'passed').length;
    const bia80      = procs.filter(p => (p.bia_pct||0) >= 80).length;
    const procDepCnt = deps.filter(d => d.depends_on_process_id).length;
    const resCnt     = deps.filter(d => !d.depends_on_process_id).length;

    wrap.innerHTML = `
    <div class="card" style="margin-top:20px;">
      <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;padding-bottom:8px;">
        <h3 style="margin:0;font-size:14px;"><i class="ti ti-topology-ring-3" style="margin-right:6px;"></i>Mapa de Continuidad</h3>
        <div style="display:flex;gap:16px;font-size:11px;color:var(--text-subtle);">
          <span><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#16a34a;margin-right:3px;"></span>P plan aprobado</span>
          <span><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#16a34a;margin-right:3px;"></span>T test pasado</span>
          <span><span style="display:inline-block;width:8px;height:8px;background:#DC2626;margin-right:3px;"></span>T test fallido</span>
          <span style="font-style:italic;">Ring = % BIA completado</span>
        </div>
      </div>
      <div class="card-body" style="padding:8px 16px 16px;">
        <!-- KPIs compactos -->
        <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin-bottom:16px;">
          ${[
            ['Criticos', critCount, '#DC2626'],
            ['Altos', highCount, '#D97706'],
            ['BIA ≥80%', bia80 + '/' + procs.length, '#16a34a'],
            ['Con plan', withPlan + '/' + procs.length, '#16a34a'],
            ['Test OK', withTest + '/' + procs.length, '#16a34a'],
            ['Dep. proc.', procDepCnt, '#2563EB'],
            ['Dep. recursos', resCnt, '#6B7280'],
          ].map(([l,v,c]) => `
          <div style="text-align:center;padding:8px 4px;background:var(--bg-2);border-radius:8px;">
            <div style="font-size:16px;font-weight:800;color:${c};">${v}</div>
            <div style="font-size:9.5px;color:var(--text-subtle);font-weight:600;text-transform:uppercase;letter-spacing:.04em;margin-top:2px;">${l}</div>
          </div>`).join('')}
        </div>
        <!-- SVG mapa -->
        <div style="overflow-x:auto;border:0.5px solid var(--border);border-radius:10px;background:var(--bg-2);padding:12px;">
          <svg viewBox="0 0 ${SVG_W} ${SVG_H}" width="100%" style="min-width:${Math.min(SVG_W, 360)}px;max-height:${SVG_H + 20}px;">
            <defs>
              <marker id="bcp-arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="#94A3B8"/>
              </marker>
            </defs>
            ${rowLabels}
            ${procDepLines}
            ${nodesSvg}
          </svg>
        </div>
        ${procDepLines ? '' : `<div style="font-size:11px;color:var(--text-subtle);margin-top:6px;text-align:center;">
          Sin dependencias proceso-proceso registradas. Añadelas en el tab <strong>Dependencias</strong>.
        </div>`}
      </div>
    </div>`;
  }

  async function _runBcpAiAnalysis() {
    const btn = document.getElementById('btn-bcp-ai-analyze');
    const resultEl = document.getElementById('bcp-ai-result');
    if (!btn || !resultEl) return;
    btn.disabled = true;
    btn.innerHTML = '<i class="ti ti-loader-2 ti-spin"></i> Analizando...';
    resultEl.innerHTML = '';
    try {
      const res = await Api.post('/api/bcp/analyze', {});
      // La API devuelve {analysis: "markdown text", format: "markdown"}
      const analysisText = res.analysis || '';
      // Renderizar markdown simple: headers, listas, negrita
      const rendered = analysisText
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/^## (.+)$/gm, '<h4 style="margin:16px 0 8px;font-size:14px;font-weight:700;color:var(--text)">$1</h4>')
        .replace(/^### (.+)$/gm, '<h5 style="margin:12px 0 6px;font-size:13px;font-weight:600">$1</h5>')
        .replace(/^\* (.+)$/gm, '<div style="display:flex;gap:6px;margin:4px 0;"><span style="color:var(--primary);flex-shrink:0">•</span><span>$1</span></div>')
        .replace(/^(\d+)\. (.+)$/gm, '<div style="display:flex;gap:6px;margin:4px 0;"><span style="font-weight:700;flex-shrink:0;min-width:16px">$1.</span><span>$2</span></div>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n\n/g, '<br>');

      resultEl.innerHTML = `
      <div class="card" style="margin-bottom:16px;border-left:4px solid var(--primary);">
        <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;">
          <h3 style="margin:0;"><i class="ti ti-brain"></i> Analisis IA — Informe de gaps BCP/ISO 22301</h3>
          <button class="btn btn-sm btn-ghost" onclick="this.closest('.card').remove()">
            <i class="ti ti-x"></i>
          </button>
        </div>
        <div class="card-body" style="font-size:13px;line-height:1.6;">${rendered || 'Sin analisis disponible'}</div>
      </div>`;
    } catch (e) {
      resultEl.innerHTML = UI.notice('Error en analisis IA: ' + e.message + '. Asegurate de tener la API key de IA configurada.');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="ti ti-brain"></i> Analizar gaps con IA';
    }
  }

  // ── Tab Procesos ─────────────────────────────────────────────────────────────

  async function _tabProcesses(el) {
    _procs = await Api.get('/api/bcp/processes' + _locParam()).catch(() => []);

    const headerHtml = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
      <h3 style="margin:0;">Procesos Criticos (${_procs.length})</h3>
      <button class="btn btn-primary" id="btn-new-proc"><i class="ti ti-plus"></i> Nuevo proceso</button>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:12px;">
      <input class="form-control" id="proc-search" placeholder="Buscar por nombre..." style="max-width:280px;font-size:13px;">
      <select class="form-control" id="proc-crit-filter" style="max-width:160px;font-size:13px;">
        <option value="">Todas las criticidades</option>
        <option value="critical">Critica</option>
        <option value="high">Alta</option>
        <option value="medium">Media</option>
        <option value="low">Baja</option>
      </select>
    </div>`;

    const emptyHtml = `<div style="text-align:center;padding:48px 24px;border:2px dashed var(--border);border-radius:8px;">
      <i class="ti ti-sitemap" style="font-size:48px;color:var(--text-muted);"></i>
      <h3 style="margin:16px 0 8px;">Sin procesos criticos registrados</h3>
      <p style="color:var(--text-muted);margin-bottom:20px;max-width:400px;margin-left:auto;margin-right:auto;">
        ISO 22301 cl. 8.2 requiere identificar las actividades criticas y sus objetivos de recuperacion (RTO/RPO/MTPD).
      </p>
      <button class="btn btn-primary btn-lg" id="btn-new-proc-empty">
        <i class="ti ti-plus"></i> Crear primer proceso critico
      </button>
    </div>`;

    const CRIT_LABELS = { critical: 'Critica', high: 'Alta', medium: 'Media', low: 'Baja' };

    function renderTable(list) {
      if (!list.length) return `<div style="padding:24px;text-align:center;color:var(--text-subtle);">Sin resultados para este filtro.</div>`;
      return `<div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>Proceso</th><th>Criticidad</th><th>Localiz.</th><th>RTO</th><th>RPO</th><th>MTPD</th>
            <th>BIA%</th><th>Dep.</th><th>Propietario</th><th>Ultimo test</th><th></th>
          </tr></thead>
          <tbody>
          ${list.map(p => {
            const biaColor = (p.bia_pct||0) >= 80 ? '#16a34a' : (p.bia_pct||0) >= 50 ? '#D97706' : '#DC2626';
            const ownerName = p.owner_name || (p.owner_id ? '#' + p.owner_id : '—');
            const depCount = (_deps.filter(d => d.process_id === p.id)).length;
            return `<tr>
              <td><strong>${UI.esc(p.name)}</strong>${p.description ? `<div style="font-size:11px;color:var(--text-subtle)">${UI.esc(p.description.substring(0,60))}</div>` : ''}</td>
              <td><span style="color:${CRIT_COLORS[p.criticality]};font-weight:700;font-size:12px;">${CRIT_LABELS[p.criticality]||p.criticality}</span></td>
              <td style="font-size:11px;color:var(--text-subtle)">${UI.esc(_locationMap[p.location_id]?.name || '—')}</td>
              <td>${p.rto_hours != null ? p.rto_hours + 'h' : '—'}</td>
              <td>${p.rpo_hours != null ? p.rpo_hours + 'h' : '—'}</td>
              <td>${p.mtpd_hours != null ? p.mtpd_hours + 'h' : '—'}</td>
              <td>
                <div style="display:flex;align-items:center;gap:6px;">
                  <div style="flex:1;height:5px;background:var(--bg-3);border-radius:3px;min-width:40px;">
                    <div style="width:${p.bia_pct||0}%;height:100%;background:${biaColor};border-radius:3px;"></div>
                  </div>
                  <span style="font-size:11px;color:${biaColor};font-weight:600;">${p.bia_pct||0}%</span>
                </div>
              </td>
              <td>${depCount > 0 ? `<span class="badge" style="font-size:10px;">${depCount}</span>` : '—'}</td>
              <td style="font-size:12px;color:var(--text-subtle);">${UI.esc(ownerName)}</td>
              <td style="font-size:12px;">${p.last_tested_at ? new Date(p.last_tested_at).toLocaleDateString('es-ES') : '—'}</td>
              <td><button class="btn btn-sm btn-secondary" onclick="ViewBcp._editProc(${p.id})">Editar</button></td>
            </tr>`;
          }).join('')}
          </tbody>
        </table>
      </div>`;
    }

    el.innerHTML = headerHtml + (!_procs.length ? emptyHtml : `<div id="proc-table-wrap">${renderTable(_procs)}</div>`);

    document.getElementById('btn-new-proc')?.addEventListener('click', () => _openProcModal());
    document.getElementById('btn-new-proc-empty')?.addEventListener('click', () => _openProcModal());

    function applyFilters() {
      const search = (document.getElementById('proc-search')?.value || '').toLowerCase();
      const critFilter = document.getElementById('proc-crit-filter')?.value || '';
      const filtered = _procs.filter(p =>
        (!search || p.name.toLowerCase().includes(search)) &&
        (!critFilter || p.criticality === critFilter)
      );
      const wrap = document.getElementById('proc-table-wrap');
      if (wrap) wrap.innerHTML = renderTable(filtered);
    }

    document.getElementById('proc-search')?.addEventListener('input', applyFilters);
    document.getElementById('proc-crit-filter')?.addEventListener('change', applyFilters);
  }

  // ── Tab BIA ──────────────────────────────────────────────────────────────────

  async function _tabBIA(el) {
    if (!_procs.length) _procs = await Api.get('/api/bcp/processes').catch(() => []);
    const IMPACT_LABELS = ['Ninguno','Bajo','Medio','Alto'];
    const IMPACT_COLORS = ['#6B7280','#16a34a','#D97706','#DC2626'];
    // IMPORTANTE: construir todo el HTML antes de asignarlo para evitar que
    // innerHTML += destruya los event listeners adjuntados previamente.
    const bodyHtml = !_procs.length
      ? `<div style="text-align:center;padding:48px 24px;">
          <i class="ti ti-chart-dots" style="font-size:48px;color:var(--text-muted);"></i>
          <h3 style="margin:16px 0 8px;">Sin procesos BIA</h3>
          <p style="color:var(--text-muted);margin-bottom:20px;">Registra primero tus procesos criticos para completar el Analisis de Impacto.</p>
          <button class="btn btn-primary btn-lg" id="btn-bia-new2">+ Crear primer BIA</button>
        </div>`
      : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:16px;">
    ${_procs.map(p => {
      const pct = p.bia_pct || 0;
      const color = pct >= 80 ? '#16a34a' : pct >= 50 ? '#D97706' : '#DC2626';
      return `
      <div class="card">
        <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;">
          <div>
            <strong>${UI.esc(p.name)}</strong>
            <span style="color:${CRIT_COLORS[p.criticality]};font-size:12px;margin-left:8px;">${p.criticality}</span>
          </div>
          <button class="btn btn-sm btn-secondary" onclick="ViewBcp._editProc(${p.id})">Completar BIA</button>
        </div>
        <div class="card-body">
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px;text-align:center;">
            <div style="background:var(--bg-2);border-radius:6px;padding:8px;">
              <div style="font-size:16px;font-weight:700;">${p.rto_hours != null ? p.rto_hours + 'h' : '—'}</div>
              <div style="font-size:11px;color:var(--text-muted);">RTO</div>
            </div>
            <div style="background:var(--bg-2);border-radius:6px;padding:8px;">
              <div style="font-size:16px;font-weight:700;">${p.rpo_hours != null ? p.rpo_hours + 'h' : '—'}</div>
              <div style="font-size:11px;color:var(--text-muted);">RPO</div>
            </div>
            <div style="background:var(--bg-2);border-radius:6px;padding:8px;">
              <div style="font-size:16px;font-weight:700;">${p.mtpd_hours != null ? p.mtpd_hours + 'h' : '—'}</div>
              <div style="font-size:11px;color:var(--text-muted);">MTPD</div>
            </div>
            <div style="background:var(--bg-2);border-radius:6px;padding:8px;">
              <div style="font-size:13px;font-weight:700;">${p.mbco ? UI.esc(p.mbco.substring(0,15)) : '—'}</div>
              <div style="font-size:11px;color:var(--text-muted);">MBCO</div>
            </div>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;">
            ${[['Financiero', p.financial_impact], ['Reputacional', p.reputational_impact],
               ['Legal', p.legal_impact], ['Operacional', p.operational_impact]].map(([lbl, val]) =>
              `<span style="padding:3px 8px;border-radius:12px;font-size:11px;background:${IMPACT_COLORS[val??0]}22;color:${IMPACT_COLORS[val??0]};border:1px solid ${IMPACT_COLORS[val??0]}44;">
                ${lbl}: ${IMPACT_LABELS[val??0]}
              </span>`
            ).join('')}
          </div>
          <div style="margin-bottom:6px;">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
              <span>Completitud BIA</span><span style="color:${color};font-weight:700;">${pct}%</span>
            </div>
            <div style="height:8px;background:var(--bg-3);border-radius:4px;">
              <div style="width:${pct}%;height:100%;background:${color};border-radius:4px;transition:.3s;"></div>
            </div>
          </div>
          ${(p.bia_missing||[]).length > 0 ? `
          <div style="font-size:11px;color:#DC2626;margin-top:6px;">
            Falta: ${p.bia_missing.join(', ')}
          </div>` : ''}
        </div>
      </div>`;
    }).join('')}
    </div>`;

    el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h3 style="margin:0;">Analisis de Impacto (BIA) — ${_procs.length} procesos</h3>
      <button class="btn btn-primary" id="btn-bia-new">+ Nuevo BIA</button>
    </div>
    ${bodyHtml}`;

    // listeners siempre DESPUES de asignar innerHTML
    document.getElementById('btn-bia-new')?.addEventListener('click', () => _openBiaPicker());
    document.getElementById('btn-bia-new2')?.addEventListener('click', () => _openBiaPicker());
  }

  // ── Tab Dependencias ─────────────────────────────────────────────────────────

  const DEP_ICONS = {
    IT_system: 'ti-cpu', personnel: 'ti-users', facility: 'ti-building',
    supplier: 'ti-truck', utility: 'ti-plug', communication: 'ti-phone',
    transport: 'ti-car', external_service: 'ti-world', process: 'ti-sitemap',
  };
  const DEP_LABELS = {
    IT_system: 'Sistema IT', personnel: 'Personal', facility: 'Instalacion',
    supplier: 'Proveedor', utility: 'Suministro', communication: 'Comunicacion',
    transport: 'Transporte', external_service: 'Servicio externo', process: 'Proceso',
  };

  async function _tabDependencies(el) {
    [_procs, _deps] = await Promise.all([
      _procs.length ? Promise.resolve(_procs) : Api.get('/api/bcp/processes').catch(() => []),
      Api.get('/api/bcp/dependencies').catch(() => []),
    ]);

    const procName = id => (_procs.find(p => p.id == id) || {}).name || '#' + id;

    // Separar dependencias: process-to-process vs recursos
    const procDeps = _deps.filter(d => d.dependency_type === 'process' || d.depends_on_process_id);
    const resourceDeps = _deps.filter(d => d.dependency_type !== 'process' && !d.depends_on_process_id);

    const procDepRows = procDeps.map(d => `<tr>
      <td style="font-size:12px;">${UI.esc(procName(d.process_id))}</td>
      <td>${UI.esc(procName(d.depends_on_process_id || d.process_id))} ${d.depends_on_process_id ? '' : '<span style="font-size:10px;color:var(--text-subtle)">(proceso origen)</span>'}</td>
      <td style="font-size:12px;">${UI.esc(d.description || d.notes || '—')}</td>
      <td style="text-align:center;">${d.recovery_sequence != null ? `<span class="badge">${d.recovery_sequence}</span>` : '—'}</td>
      <td style="font-size:12px;">${UI.esc(d.alternative || '—')}</td>
      <td><button class="btn btn-sm btn-secondary" onclick="ViewBcp._editDep(${d.id})">Editar</button></td>
    </tr>`).join('');

    const resourceRows = resourceDeps.map(d => `<tr>
      <td><i class="ti ${DEP_ICONS[d.dependency_type] || 'ti-circle'}" style="margin-right:4px;"></i>${DEP_LABELS[d.dependency_type] || d.dependency_type}</td>
      <td style="font-size:12px;">${UI.esc(procName(d.process_id))}</td>
      <td><strong style="font-size:13px;">${UI.esc(d.name)}</strong>${d.notes === 'auto:location_alternate' ? ' <span class="badge badge-muted" style="font-size:9px;">auto</span>' : ''}${d.description ? `<div style="font-size:11px;color:var(--text-subtle)">${UI.esc(d.description.substring(0,60))}</div>` : ''}</td>
      <td style="text-align:center;">${d.qty_normal ?? '—'} / ${d.qty_recovery ?? '—'}</td>
      <td style="text-align:center;">${d.rto_hours != null ? d.rto_hours + 'h' : '—'}</td>
      <td style="text-align:center;">${d.is_critical ? '<span class="badge badge-danger" style="font-size:10px;">Critica</span>' : '<span style="font-size:11px;color:var(--text-subtle)">No critica</span>'}</td>
      <td style="font-size:11px;max-width:120px;overflow:hidden;text-overflow:ellipsis;">${UI.esc((d.alternative || '—').substring(0,50))}</td>
      <td style="text-align:center;">${d.recovery_sequence != null ? `<span class="badge">${d.recovery_sequence}</span>` : '—'}</td>
      <td><button class="btn btn-sm btn-secondary" onclick="ViewBcp._editDep(${d.id})">Editar</button></td>
    </tr>`).join('');

    const html = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:8px;flex-wrap:wrap;">
      <div style="display:flex;align-items:center;gap:6px;">
        <button class="btn btn-ghost btn-sm" id="btn-sync-loc-deps" title="Detecta localizaciones con sede alternativa y crea dependencias automáticamente">
          <i class="ti ti-refresh"></i> Sincronizar dependencias de sedes
        </button>
      </div>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-primary" id="btn-new-dep"><i class="ti ti-plus"></i> Nueva dependencia de recurso</button>
        <button class="btn btn-secondary" id="btn-new-proc-dep"><i class="ti ti-sitemap"></i> Nueva dep. proceso-proceso</button>
      </div>
    </div>

    <div class="card" style="margin-bottom:16px;">
      <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;">
        <h3 style="margin:0;"><i class="ti ti-sitemap" style="margin-right:6px;"></i>Dependencias entre procesos</h3>
        <span style="font-size:12px;color:var(--text-subtle);">${procDeps.length} registradas</span>
      </div>
      <div style="font-size:12px;color:var(--text-subtle);padding:0 16px 8px;">
        Un proceso no puede iniciar su recuperacion hasta que el proceso dependiente este operativo.
      </div>
      ${!procDeps.length
        ? `<div style="padding:24px;text-align:center;color:var(--text-subtle);">Sin dependencias proceso-proceso registradas. Usa el boton "Nueva dep. proceso-proceso".</div>`
        : `<div style="overflow-x:auto;"><table class="data-table" style="font-size:12px;">
          <thead><tr><th>Este proceso</th><th>Depende de</th><th>Motivo</th><th>Secuencia</th><th>Impacto</th><th></th></tr></thead>
          <tbody>${procDepRows}</tbody>
        </table></div>`
      }
    </div>

    <div class="card">
      <div class="card-header" style="display:flex;justify-content:space-between;align-items:center;">
        <h3 style="margin:0;"><i class="ti ti-link" style="margin-right:6px;"></i>Recursos y dependencias externas</h3>
        <span style="font-size:12px;color:var(--text-subtle);">${resourceDeps.length} registradas</span>
      </div>
      <div style="font-size:12px;color:var(--text-subtle);padding:0 16px 8px;">
        Recursos que necesita cada proceso para recuperarse: sistemas IT, personal, instalaciones, proveedores, suministros.
      </div>
      ${!resourceDeps.length
        ? `<div style="padding:24px;text-align:center;color:var(--text-subtle);">Sin dependencias de recursos registradas.</div>`
        : `<div style="overflow-x:auto;"><table class="data-table" style="font-size:12px;">
          <thead><tr>
            <th>Tipo</th><th>Proceso</th><th>Recurso</th><th>Normal/Recup.</th>
            <th>RTO nec.</th><th>Critico</th><th>Alternativa</th><th>Seq.</th><th></th>
          </tr></thead>
          <tbody>${resourceRows}</tbody>
        </table></div>`
      }
    </div>`;

    el.innerHTML = html;
    document.getElementById('btn-new-dep')?.addEventListener('click', () => _openDepModal());
    document.getElementById('btn-new-proc-dep')?.addEventListener('click', () => _openDepModal(null, true));
    document.getElementById('btn-sync-loc-deps')?.addEventListener('click', async () => {
      const btn = document.getElementById('btn-sync-loc-deps');
      if (btn) { btn.disabled = true; btn.innerHTML = '<i class="ti ti-loader-2 ti-spin"></i> Sincronizando...'; }
      try {
        const res = await Api.post('/api/bcp/locations/sync-all-deps', {});
        UI.toast(res.created > 0
          ? res.created + ' dependencia(s) creada(s) de ' + res.locations_processed + ' sede(s) con alternativa'
          : 'No hay dependencias nuevas que crear', res.created > 0 ? 'success' : 'info');
        if (res.created > 0) _renderContent();
      } catch (e) {
        UI.toast('Error: ' + (e.message || e), 'error');
      } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '<i class="ti ti-refresh"></i> Sincronizar dependencias de sedes'; }
      }
    });
  }

  // ── Tab Estrategias ──────────────────────────────────────────────────────────

  const IMPL_LABELS = {
    planned: 'Planificado', in_progress: 'En progreso',
    implemented: 'Implementado', tested: 'Probado',
  };
  const STRAT_TYPE_LABELS = {
    hot_site: 'Hot site', cold_site: 'Cold site', warm_site: 'Warm site',
    work_from_home: 'Trabajo remoto', outsourcing: 'Outsourcing',
    manual_workaround: 'Procedimiento manual', dual_site: 'Dual site',
    cloud_failover: 'Cloud failover',
  };

  async function _tabStrategies(el) {
    [_procs, _strats] = await Promise.all([
      _procs.length ? Promise.resolve(_procs) : Api.get('/api/bcp/processes').catch(() => []),
      Api.get('/api/bcp/strategies').catch(() => []),
    ]);

    const procName = id => id ? ((_procs.find(p => p.id == id) || {}).name || '#' + id) : 'Global';

    // Construir TODO el HTML antes de asignar (evita que innerHTML += destruya listeners)
    const bodyHtml = !_strats.length
      ? UI.emptyState(
          'Sin estrategias de recuperacion',
          'ISO 22301 cl. 8.3 requiere al menos una estrategia por proceso critico. Tipos: hot site, trabajo remoto, procedimiento manual, cloud failover...'
        )
      : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;">
        ${_strats.map(s => `
        <div class="card" style="cursor:pointer;transition:box-shadow .15s;"
             onmouseenter="this.style.boxShadow='var(--shadow-md)'"
             onmouseleave="this.style.boxShadow=''"
             onclick="ViewBcp._editStrat(${s.id})">
          <div class="card-body">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
              <span class="badge" style="background:#59008D22;color:#59008D;font-size:11px;">
                <i class="ti ti-route" style="font-size:10px;margin-right:3px;"></i>
                ${STRAT_TYPE_LABELS[s.strategy_type] || s.strategy_type}
              </span>
              <span style="font-size:11px;font-weight:600;color:${IMPL_COLORS[s.implementation_status]||'#666'};">
                ${IMPL_LABELS[s.implementation_status] || s.implementation_status}
              </span>
            </div>
            <strong style="font-size:14px;display:block;margin-bottom:4px;">${UI.esc(s.name)}</strong>
            <div style="font-size:12px;color:var(--text-subtle);">
              <i class="ti ti-sitemap" style="font-size:11px;margin-right:3px;"></i>${UI.esc(procName(s.process_id))}
            </div>
            ${s.description ? `<div style="font-size:12px;color:var(--text-subtle);margin-top:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${UI.esc(s.description.substring(0, 80))}</div>` : ''}
            ${s.estimated_cost != null ? `<div style="font-size:12px;margin-top:8px;padding-top:8px;border-top:0.5px solid var(--border);">Coste estimado: <strong>${s.estimated_cost.toLocaleString('es-ES')} €</strong></div>` : ''}
            ${s.target_date ? `<div style="font-size:11px;color:var(--text-subtle);margin-top:4px;">Fecha objetivo: ${new Date(s.target_date).toLocaleDateString('es-ES')}</div>` : ''}
          </div>
        </div>`).join('')}
      </div>`;

    el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h3 style="margin:0;">Estrategias de Recuperacion (${_strats.length})</h3>
      <button class="btn btn-primary" id="btn-new-strat">
        <i class="ti ti-plus"></i> Nueva estrategia
      </button>
    </div>
    ${bodyHtml}`;

    // Listener DESPUES de asignar innerHTML
    document.getElementById('btn-new-strat')?.addEventListener('click', () => _openStratModal());
  }

  // ── Tab Planes ───────────────────────────────────────────────────────────────

  const PLAN_BADGE_CLASS = {
    bcp: 'plan-badge-bcp', drp: 'plan-badge-drp', crp: 'plan-badge-crp',
    cyber_response: 'plan-badge-cyber', pandemic: 'plan-badge-pandemic',
    ems: 'plan-badge-ems', supply_chain: 'plan-badge-supply',
  };
  const PLAN_TYPE_LABELS = {
    bcp: 'Plan de Continuidad de Negocio (BCP)',
    drp: 'Plan de Recuperacion ante Desastres (DRP)',
    crp: 'Plan de Respuesta a Crisis (CRP)',
    cyber_response: 'Plan de Respuesta Cibernetica',
    pandemic: 'Plan de Continuidad ante Pandemia',
    ems: 'Sistema de Gestion de Emergencias (EMS)',
    supply_chain: 'Plan de Continuidad de Cadena de Suministro',
  };
  const CLASSIFICATION_LABELS = { confidential: 'Confidencial', internal: 'Uso interno', restricted: 'Restringido' };

  async function _tabPlans(el) {
    [_procs, _plans] = await Promise.all([
      _procs.length ? Promise.resolve(_procs) : Api.get('/api/bcp/processes').catch(() => []),
      Api.get('/api/bcp/plans' + _locParam()).catch(() => []),
    ]);

    const tableHtml = !_plans.length
      ? UI.emptyState('No hay planes BCP/DRP. ISO 22301 cl. 8.4 requiere planes documentados de continuidad.')
      : `<div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>Codigo</th><th>Tipo</th><th>Clasificacion</th><th>Nombre</th><th>Version</th>
            <th>Estado</th><th>Localiz.</th><th>Procesos</th><th>Propietario</th><th>Revision</th><th></th>
          </tr></thead>
          <tbody>
          ${_plans.map(p => `<tr>
            <td>${UI.codePill(p.code)}</td>
            <td><span class="badge ${PLAN_BADGE_CLASS[p.plan_type]||''}" style="font-size:11px;">${PLAN_TYPE_LABELS[p.plan_type]||p.plan_type}</span></td>
            <td style="font-size:11px;color:var(--text-subtle);">${CLASSIFICATION_LABELS[p.classification]||'—'}</td>
            <td><strong>${UI.esc(p.name)}</strong></td>
            <td style="font-size:12px;color:var(--text-subtle);">v${UI.esc(p.version||'1.0')}</td>
            <td><span class="badge badge-${p.status==='approved'?'success':p.status==='under_review'?'warning':'secondary'}"
              style="background:${STATUS_COLORS[p.status]||'#666'}22;color:${STATUS_COLORS[p.status]||'#666'};font-size:11px;">${p.status}</span></td>
            <td style="font-size:11px;color:var(--text-subtle)">${UI.esc(_locationMap[p.location_id]?.name || '—')}</td>
            <td style="font-size:12px;">${(p.process_ids||[]).length}</td>
            <td style="font-size:12px;color:var(--text-subtle);">${UI.esc(p.plan_owner_name||'—')}</td>
            <td style="font-size:12px;">${p.review_date ? new Date(p.review_date).toLocaleDateString('es-ES') : '—'}</td>
            <td class="bcm-plan-actions-cell">
              <button class="btn btn-sm btn-ghost" style="padding:4px 8px"
                onclick="ViewBcp._togglePlanMenu(event,${p.id})">
                <i class="ti ti-dots-vertical"></i>
              </button>
              <div id="plan-menu-${p.id}" style="display:none;position:absolute;right:0;top:100%;z-index:200;
                background:var(--bg-1);border:1px solid var(--border);border-radius:6px;
                box-shadow:0 4px 16px rgba(0,0,0,.15);min-width:190px;overflow:hidden">
                <button class="plan-menu-item" onclick="ViewBcp._editPlan(${p.id});ViewBcp._closePlanMenus()">
                  <i class="ti ti-edit"></i> Editar plan
                </button>
                ${['draft','under_review'].includes(p.status) ? `
                <button class="plan-menu-item" onclick="ViewBcp._approvePlan(${p.id});ViewBcp._closePlanMenus()">
                  <i class="ti ti-check"></i> Aprobar
                </button>` : ''}
                <div style="height:1px;background:var(--border);margin:2px 0"></div>
                <button class="plan-menu-item plan-menu-danger" onclick="ViewBcp._activatePlanDirect(${p.id});ViewBcp._closePlanMenus()">
                  <i class="ti ti-alert-triangle"></i> Activar plan
                </button>
                <button class="plan-menu-item" onclick="ViewBcp._sendPlanMessage(${p.id});ViewBcp._closePlanMenus()">
                  <i class="ti ti-send"></i> Mensaje a stakeholders
                </button>
                <button class="plan-menu-item" onclick="ViewBcp._scheduleTestForPlan(${p.id});ViewBcp._closePlanMenus()">
                  <i class="ti ti-calendar-event"></i> Programar test
                </button>
                <div style="height:1px;background:var(--border);margin:2px 0"></div>
                <button class="plan-menu-item" onclick="ViewBcp._viewPlanContext(${p.id});ViewBcp._closePlanMenus()">
                  <i class="ti ti-layout-grid"></i> Ver contexto completo
                </button>
                <button class="plan-menu-item" onclick="ViewBcp._viewPlanActivations(${p.id});ViewBcp._closePlanMenus()">
                  <i class="ti ti-history"></i> Historial activaciones
                </button>
              </div>
            </td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;

    el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h3 style="margin:0;">Planes BCP/DRP (${_plans.length})</h3>
      <button class="btn btn-primary" id="btn-new-plan"><i class="ti ti-plus"></i> Nuevo plan</button>
    </div>
    ${tableHtml}
    <!-- Drawer para formulario de plan -->
    <div class="drawer-overlay" id="plan-drawer-overlay"></div>
    <div class="drawer-panel" id="plan-drawer">
      <div class="drawer-header">
        <h3 class="drawer-title" id="plan-drawer-title">Nuevo Plan</h3>
        <div style="display:flex;gap:8px;margin-left:auto;">
          <button class="btn btn-sm" id="plan-drawer-cancel">Cancelar</button>
          <button class="btn btn-primary btn-sm" id="plan-drawer-save">
            <i class="ti ti-check"></i> Guardar
          </button>
        </div>
      </div>
      <div class="drawer-body" id="plan-drawer-body"></div>
    </div>`;

    document.getElementById('btn-new-plan')?.addEventListener('click', () => _openPlanDrawer());
    document.getElementById('plan-drawer-cancel')?.addEventListener('click', () => _closePlanDrawer());
    document.getElementById('plan-drawer-overlay')?.addEventListener('click', () => _closePlanDrawer());
    document.getElementById('plan-drawer-save')?.addEventListener('click', () => _savePlan(_currentPlanId));
  }

  // ── Tab Tests ────────────────────────────────────────────────────────────────

  async function _tabTests(el) {
    [_procs, _tests] = await Promise.all([
      _procs.length ? Promise.resolve(_procs) : Api.get('/api/bcp/processes').catch(() => []),
      Api.get('/api/bcp/tests' + _locParam()).catch(() => []),
    ]);
    const year = new Date().getFullYear();
    const ep = await Api.get(`/api/bcp/exercise-programme?year=${year}`).catch(() => []);

    el.innerHTML = `
    <div style="display:grid;grid-template-columns:70% 30%;gap:16px;">
      <div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="margin:0;">Tests y Ejercicios (${_tests.length})</h3>
          <button class="btn btn-primary" id="btn-new-test">+ Programar test</button>
        </div>
        <div id="tests-list"></div>
      </div>
      <div>
        <div class="card">
          <div class="card-header"><h3>Programa ${year}</h3></div>
          <div class="card-body">
            ${ep.length ? ep.map(p => `
              <div style="margin-bottom:10px;">
                <strong>${p.year}</strong>
                <span class="badge badge-${p.status==='approved'?'success':'warning'}" style="margin-left:6px;">${p.status}</span>
                <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">${p.overall_objective ? UI.esc(p.overall_objective.substring(0,80)) : 'Sin objetivo definido'}</div>
                ${p.exercises ? `<div style="font-size:12px;margin-top:4px;">${(p.exercises||[]).length} ejercicio(s) planificado(s)</div>` : ''}
              </div>`).join('') :
              `<p style="color:var(--text-muted);font-size:13px;">Sin programa de ejercicios para ${year}.</p>
               <button class="btn btn-sm btn-secondary" onclick="ViewBcp._openEPModal(${year})">Crear programa ${year}</button>`
            }
          </div>
        </div>
      </div>
    </div>`;

    const testsList = document.getElementById('tests-list');
    if (!_tests.length) {
      testsList.innerHTML = UI.emptyState('No hay tests programados. ISO 22301 cl. 8.5 requiere ejercicios periodicos.');
    } else {
      testsList.innerHTML = `
      <div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>Codigo</th><th>Tipo</th><th>Objetivo</th><th>Programado</th>
            <th>Realizado</th><th>Resultado</th><th></th>
          </tr></thead>
          <tbody>
          ${_tests.map(t => `<tr>
            <td>${UI.codePill(t.code)}</td>
            <td>${t.test_type}</td>
            <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;">${t.objective ? UI.esc(t.objective.substring(0,60)) : '—'}</td>
            <td>${t.scheduled_at ? new Date(t.scheduled_at).toLocaleDateString('es-ES') : '—'}</td>
            <td>${t.conducted_at ? new Date(t.conducted_at).toLocaleDateString('es-ES') : '—'}</td>
            <td>${t.result ?
              `<span class="badge badge-${t.result==='passed'?'success':t.result==='partial'?'warning':'danger'}">${t.result}</span>` : '—'}</td>
            <td style="display:flex;gap:4px;flex-wrap:nowrap">
              <button class="btn btn-sm btn-secondary" onclick="ViewBcp._openTestResultModal(${t.id})">
                ${t.result ? 'Ver / Editar' : 'Registrar resultado'}
              </button>
              <button class="btn btn-sm btn-ghost" title="Generar checklist con IA" onclick="ViewBcp._genAiChecklist(${t.id})" style="padding:4px 7px">
                <i class="ti ti-sparkles" style="font-size:13px;color:var(--primary)"></i>
              </button>
            </td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    }
    document.getElementById('btn-new-test')?.addEventListener('click', () => _openTestModal());
  }

  // ── Tab Proveedores BCM ──────────────────────────────────────────────────────

  const CRIT_LABELS_BCM = { critical: 'Critica', high: 'Alta', medium: 'Media', low: 'Baja' };

  async function _tabSuppliers(el) {
    [_procs, _slinks, _suppliers] = await Promise.all([
      _procs.length ? Promise.resolve(_procs) : Api.get('/api/bcp/processes').catch(() => []),
      Api.get('/api/bcp/supplier-links' + _locParam()).catch(() => []),
      Api.get('/api/suppliers/').catch(() => []),
    ]);

    // Construir TODO el HTML antes de asignar (evita que innerHTML += destruya listeners)
    const bodyHtml = !_slinks.length
      ? UI.emptyState(
          'Sin proveedores BCM vinculados',
          'ISO 22301 cl. 8.2 requiere identificar los proveedores criticos y su impacto en la continuidad.'
        )
      : `<div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>Proveedor</th>
            <th>Criticidad BCM</th>
            <th>Procesos</th>
            <th>RTO impacto</th>
            <th>SLA contrato</th>
            <th>Contingencia</th>
            <th>Alternativo</th>
            <th>Revision</th>
            <th></th>
          </tr></thead>
          <tbody>
          ${_slinks.map(s => `<tr>
            <td>
              <strong>${UI.esc(s.supplier_name)}</strong>
              ${s.notes ? `<div style="font-size:11px;color:var(--text-subtle)">${UI.esc(s.notes.substring(0, 50))}</div>` : ''}
            </td>
            <td>
              <span style="color:${CRIT_COLORS[s.criticality]};font-weight:700;font-size:12px;">
                ${CRIT_LABELS_BCM[s.criticality] || s.criticality}
              </span>
            </td>
            <td style="text-align:center;">${(s.process_ids || []).length}</td>
            <td style="font-size:13px;">${s.rto_impact_hours != null ? '<strong>' + s.rto_impact_hours + 'h</strong>' : '—'}</td>
            <td style="font-size:12px;color:var(--text-subtle);">${s.contract_sla_hours != null ? s.contract_sla_hours + 'h' : '—'}</td>
            <td style="text-align:center;">
              ${s.has_contingency_plan
                ? '<span class="badge badge-success" style="font-size:11px;"><i class="ti ti-check" style="font-size:10px;"></i> Si</span>'
                : '<span class="badge" style="font-size:11px;color:var(--risk-high);background:var(--risk-high-soft,#FEE2E2);">No</span>'}
            </td>
            <td style="font-size:12px;color:var(--text-subtle);">${s.alternative_supplier_name || '—'}</td>
            <td style="font-size:12px;color:var(--text-subtle);">${s.last_review_date ? new Date(s.last_review_date).toLocaleDateString('es-ES') : '—'}</td>
            <td>
              <button class="btn btn-sm btn-secondary" onclick="ViewBcp._editSL(${s.id})">Editar</button>
            </td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;

    el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h3 style="margin:0;">Proveedores BCM (${_slinks.length})</h3>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-ghost btn-sm" id="btn-analyze-suppliers">
          <i class="ti ti-brain"></i> Analizar con IA
        </button>
        <button class="btn btn-primary btn-sm" id="btn-new-sl">
          <i class="ti ti-plus"></i> Vincular proveedor
        </button>
      </div>
    </div>
    ${bodyHtml}
    <div id="supplier-ai-result"></div>`;

    document.getElementById('btn-new-sl')?.addEventListener('click', () => _openSLModal());
    document.getElementById('btn-analyze-suppliers')?.addEventListener('click', async () => {
      const btn = document.getElementById('btn-analyze-suppliers');
      if (!btn) return;
      btn.disabled = true;
      btn.innerHTML = '<i class="ti ti-loader-2 ti-spin"></i>';
      const url = '/api/bcp/suppliers/analyze-ai' + _locParam();
      try {
        const res = await Api.post(url, {});
        const div = document.getElementById('supplier-ai-result');
        if (div) div.innerHTML = `<div class="card" style="padding:14px;margin-top:12px;border-left:3px solid var(--primary)">
          <div style="display:flex;justify-content:space-between;margin-bottom:8px">
            <strong><i class="ti ti-brain"></i> Análisis IA de proveedores BCM</strong>
            <button class="btn btn-ghost btn-sm" onclick="document.getElementById('supplier-ai-result').innerHTML=''"><i class="ti ti-x"></i></button>
          </div>
          <div style="font-size:13px;line-height:1.6;white-space:pre-wrap">${UI.esc(res.analysis || JSON.stringify(res))}</div>
        </div>`;
      } catch (e) { UI.toast('Error en análisis IA: ' + (e.message || e), 'error'); }
      finally { btn.disabled = false; btn.innerHTML = '<i class="ti ti-brain"></i> Analizar con IA'; }
    });
  }

  // ── Tab Importar / Exportar Excel ───────────────────────────────────────────

  let _importMode = 'std';

  function _tabImport(el) {
    el.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px;">
      <!-- Panel exportar -->
      <div class="card">
        <div class="card-header"><h3><i class="ti ti-table-export"></i> Exportar datos actuales</h3></div>
        <div class="card-body">
          <p style="color:var(--text-muted);font-size:14px;">Descarga todos tus procesos, dependencias, planes y tests en formato Excel.</p>
          <a href="/api/bcp/export" class="btn btn-secondary" download="BCP_datos.xlsx">
            <i class="ti ti-download"></i> Descargar BCP_datos.xlsx
          </a>
          <div style="margin-top:12px;">
            <a href="/api/bcp/import/template" class="btn btn-secondary btn-sm" download>
              <i class="ti ti-file-download"></i> Descargar plantilla vacia
            </a>
          </div>
        </div>
      </div>
      <!-- Panel importar -->
      <div class="card">
        <div class="card-header"><h3><i class="ti ti-table-import"></i> Importar datos</h3></div>
        <div class="card-body">
          <div style="display:flex;gap:8px;margin-bottom:12px;">
            <button class="btn btn-secondary btn-sm active" id="import-mode-std"
              onclick="ViewBcp._setImportMode('std')">
              <i class="ti ti-file-spreadsheet"></i> Plantilla estandar
            </button>
            <button class="btn btn-secondary btn-sm" id="import-mode-ai"
              onclick="ViewBcp._setImportMode('ai')">
              <i class="ti ti-brain"></i> Cualquier formato (IA)
            </button>
          </div>
          <div id="import-mode-desc" style="font-size:13px;color:var(--text-muted);margin-bottom:12px;">
            Usa la plantilla descargada arriba. El sistema valida la estructura exacta.
          </div>
          <label style="display:block;border:2px dashed var(--border);border-radius:8px;padding:24px;text-align:center;cursor:pointer;transition:.2s;"
                 id="drop-zone"
                 ondragover="event.preventDefault()"
                 ondrop="ViewBcp._handleDrop(event)">
            <i class="ti ti-cloud-upload" style="font-size:32px;color:var(--text-muted);"></i>
            <div id="drop-zone-label" style="margin-top:8px;color:var(--text-muted);">Arrastra el archivo aqui o haz clic</div>
            <div style="font-size:12px;margin-top:4px;color:var(--text-muted);">.xlsx &middot; .xls &middot; .csv</div>
            <input type="file" accept=".xlsx,.xls,.csv" style="display:none;" id="import-file-input"
                   onchange="ViewBcp._onFileSelect(this.files[0])">
          </label>
        </div>
      </div>
    </div>
    <div id="import-preview-area"></div>`;

    document.getElementById('drop-zone').addEventListener('click', () => {
      document.getElementById('import-file-input').click();
    });
  }

  function _setImportMode(mode) {
    _importMode = mode;
    document.getElementById('import-mode-std')?.classList.toggle('active', mode === 'std');
    document.getElementById('import-mode-ai')?.classList.toggle('active', mode === 'ai');
    const desc = document.getElementById('import-mode-desc');
    if (desc) desc.textContent = mode === 'ai'
      ? 'Claude analizara la estructura de tu Excel y mapeara automaticamente los campos BCP, aunque no siga la plantilla exacta.'
      : 'Usa la plantilla descargada arriba. El sistema valida la estructura exacta.';
  }

  function _handleDrop(event) {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file) _onFileSelect(file);
  }

  // Kept for backward-compat (old inline handler in older markup if any)
  async function _handleFileSelect(file) {
    return _onFileSelect(file);
  }

  async function _onFileSelect(file) {
    if (!file) return;
    const dropZone = document.getElementById('drop-zone');
    const lbl = document.getElementById('drop-zone-label');
    if (dropZone) dropZone.style.borderColor = 'var(--primary)';
    if (lbl) lbl.textContent = file.name;

    const area = document.getElementById('import-preview-area');
    if (area) area.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);">Analizando archivo...</div>';

    const formData = new FormData();
    formData.append('file', file);

    try {
      const endpoint = _importMode === 'ai' ? '/api/bcp/import/ai-preview' : '/api/bcp/import/preview';
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + (localStorage.getItem('riskhub_token') || '') },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || res.statusText);
      }
      const preview = await res.json();
      _renderImportPreview(preview, file);
    } catch (e) {
      if (area) area.innerHTML = UI.notice('Error al analizar: ' + e.message);
    }
  }

  function _renderImportPreview(preview, file) {
    const area = document.getElementById('import-preview-area');
    if (!area) return;
    const hasErrors = preview.errors && preview.errors.length > 0;
    const hasWarnings = preview.ai_warnings && preview.ai_warnings.length > 0;

    let aiInfo = '';
    if (preview.ai_mapping && Object.keys(preview.ai_mapping).length) {
      const mapped = Object.entries(preview.ai_mapping)
        .filter(([, v]) => v)
        .map(([k, v]) => `<span class="badge badge-info" style="margin:2px;">${UI.esc(k)} &rarr; ${UI.esc(v)}</span>`)
        .join('');
      const conf = Math.round((preview.ai_confidence || 0) * 100);
      aiInfo = `
      <div class="card" style="margin-bottom:16px;">
        <div class="card-header"><h4><i class="ti ti-brain"></i> Mapeo detectado por IA (confianza: ${conf}%)</h4></div>
        <div class="card-body">${mapped || 'No se detecto ningun mapeo'}</div>
      </div>`;
    }

    const procs = preview.processes || [];
    area.innerHTML = `
    ${aiInfo}
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px;">
      <div class="stat-card"><div class="stat-value">${preview.summary.processes_found}</div><div class="stat-label">Procesos</div></div>
      <div class="stat-card"><div class="stat-value">${preview.summary.dependencies_found}</div><div class="stat-label">Dependencias</div></div>
      <div class="stat-card"><div class="stat-value">${preview.summary.suppliers_found}</div><div class="stat-label">Proveedores</div></div>
    </div>
    ${hasErrors ? `<div class="notice notice-warning" style="margin-bottom:8px;"><strong>Errores:</strong> ${preview.errors.map(e => UI.esc(e)).join('; ')}</div>` : ''}
    ${hasWarnings ? `<div class="notice notice-warning" style="margin-bottom:8px;"><strong>Avisos IA:</strong> ${preview.ai_warnings.map(w => UI.esc(w)).join('; ')}</div>` : ''}
    ${procs.length ? `
    <h4>Vista previa (primeros ${procs.length} procesos):</h4>
    <div class="table-container">
      <table class="data-table">
        <thead><tr><th>Nombre</th><th>Criticidad</th><th>RTO</th><th>RPO</th></tr></thead>
        <tbody>
        ${procs.map(p => `<tr>
          <td>${UI.esc(p.name)}</td>
          <td>${UI.esc(String(p.criticality))}</td>
          <td>${p.rto_hours != null ? p.rto_hours + 'h' : '&mdash;'}</td>
          <td>${p.rpo_hours != null ? p.rpo_hours + 'h' : '&mdash;'}</td>
        </tr>`).join('')}
        </tbody>
      </table>
    </div>` : ''}
    ${!hasErrors && preview.summary.processes_found > 0 ? `
    <div style="display:flex;gap:8px;margin-top:16px;">
      <button class="btn btn-primary" id="btn-confirm-import">
        <i class="ti ti-check"></i> Confirmar importacion (${preview.summary.processes_found} procesos)
      </button>
    </div>` : ''}`;

    // Guardar preview y file para la confirmacion
    window._bcpLastPreview = preview;
    document.getElementById('btn-confirm-import')?.addEventListener('click', () => _confirmImport(file));
  }

  async function _confirmImport(file) {
    if (!confirm(`Importar ${window._bcpLastPreview?.summary?.processes_found || 0} procesos?`)) return;
    const btn = document.getElementById('btn-confirm-import');
    if (btn) { btn.disabled = true; btn.textContent = 'Importando...'; }

    const formData = new FormData();
    const inputFile = document.getElementById('import-file-input');
    const fileToSend = (inputFile && inputFile.files[0]) || file;
    if (!fileToSend) {
      UI.toast('Selecciona el archivo de nuevo para confirmar', 'error');
      if (btn) btn.disabled = false;
      return;
    }
    formData.append('file', fileToSend);

    try {
      const res = await fetch('/api/bcp/import/confirm', {
        method: 'POST',
        headers: { 'Authorization': 'Bearer ' + (localStorage.getItem('riskhub_token') || '') },
        body: formData,
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
      const result = await res.json();
      UI.toast(
        `Importacion completada: ${result.created.processes} procesos, ${result.created.dependencies} dependencias`,
        'success'
      );
      _procs = [];
      _switchTab('processes');
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
      if (btn) { btn.disabled = false; btn.textContent = 'Confirmar importacion'; }
    }
  }

  // ── Modales — Proceso ────────────────────────────────────────────────────────

  async function _openProcModal(proc, isBia) {
    let users = [], locFlat = [];
    try {
      [users] = await Promise.all([
        Api.get('/api/users/').catch(() => []),
      ]);
      // Flatten location map for select
      (function flatten(nodes) {
        nodes.forEach(n => { locFlat.push(n); flatten(n.children || []); });
      })(_locations);
    } catch (_) { }
    const userOpts = users.map(u =>
      `<option value="${u.id}"${(proc?.owner_id === u.id) ? ' selected' : ''}>${UI.esc(u.full_name || u.email)}</option>`
    ).join('');
    const rUserOpts = users.map(u =>
      `<option value="${u.id}"${(proc?.recovery_owner_id === u.id) ? ' selected' : ''}>${UI.esc(u.full_name || u.email)}</option>`
    ).join('');

    const IMPACTS = ['0 — Ninguno', '1 — Menor', '2 — Significativo', '3 — Critico'];

    // Convertir arrays JSON a texto multi-linea (una linea por item)
    const arrToLines = (arr) => Array.isArray(arr) ? arr.join('\n') : (arr || '');

    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:720px;max-height:92vh;display:flex;flex-direction:column;">
      <div class="modal-header" style="flex-shrink:0;">
        <h2>${proc ? 'Editar proceso' : (isBia ? 'Nuevo BIA' : 'Nuevo proceso critico')}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="overflow-y:auto;flex:1;padding:20px 24px;display:block;">

        <div class="form-section-divider"><span>INFORMACION BASICA</span></div>
        <div style="margin-bottom:14px;">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Nombre <span style="color:var(--danger)">*</span></label>
          <input id="pm-name" class="form-control" value="${UI.esc(proc?.name||'')}" style="font-size:13px;">
        </div>
        <div style="margin-bottom:14px;">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Descripcion</label>
          <textarea id="pm-desc" class="form-control" rows="2" style="font-size:13px;">${UI.esc(proc?.description||'')}</textarea>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Criticidad <span style="color:var(--danger)">*</span></label>
            <select id="pm-crit" class="form-control" style="font-size:13px;">
              ${['critical','high','medium','low'].map(c=>`<option value="${c}"${proc?.criticality===c?' selected':''}>${{critical:'Critica',high:'Alta',medium:'Media',low:'Baja'}[c]}</option>`).join('')}
            </select>
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Prioridad de recuperacion</label>
            <input id="pm-prio" class="form-control" type="number" min="1" style="font-size:13px;" value="${proc?.priority||''}" placeholder="1 = mas urgente">
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Responsable</label>
            <select id="pm-owner" class="form-control" style="font-size:13px;">
              <option value="">— Sin asignar —</option>${userOpts}
            </select>
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Responsable de recuperacion</label>
            <select id="pm-rowner" class="form-control" style="font-size:13px;">
              <option value="">— Sin asignar —</option>${rUserOpts}
            </select>
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Localización</label>
            <select id="pm-location" class="form-control" style="font-size:13px;">
              <option value="">— Sin localización asignada —</option>
              ${locFlat.map(l => `<option value="${l.id}"${(proc?.location_id === l.id || (!proc && _locationFilter === l.id)) ? ' selected' : ''}>${'&nbsp;'.repeat((l.depth || 0) * 2)}${UI.esc(l.name)}</option>`).join('')}
            </select>
          </div>
        </div>

        ${proc ? (() => {
          const pct = proc.bia_pct || 0;
          const color = pct >= 80 ? '#16a34a' : pct >= 50 ? '#D97706' : '#DC2626';
          const missing = proc.bia_missing || [];
          const fieldLabels = {
            rto_hours:'RTO', rpo_hours:'RPO', mtpd_hours:'MTPD', mbco:'MBCO',
            financial_impact:'Impacto financiero', reputational_impact:'Impacto reputacional',
            legal_impact:'Impacto legal', operational_impact:'Impacto operacional',
            activation_criteria:'Criterios activacion', vital_records:'Registros vitales',
          };
          return `<div style="padding:10px 14px;background:${color}14;border:1px solid ${color}44;border-radius:var(--radius);margin-bottom:14px;display:flex;align-items:center;gap:14px;">
            <div style="flex:1;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
                <span style="font-size:12px;font-weight:700;color:${color};">Completitud BIA: ${pct}%</span>
                ${pct >= 80 ? '<span style="font-size:11px;color:#16a34a;">Listo para certificacion ISO 22301</span>' : ''}
              </div>
              <div style="height:6px;background:${color}22;border-radius:3px;">
                <div style="width:${pct}%;height:100%;background:${color};border-radius:3px;transition:.3s;"></div>
              </div>
              ${missing.length ? `<div style="margin-top:6px;font-size:11px;color:${color};">Pendiente: ${missing.map(f=>fieldLabels[f]||f).join(' · ')}</div>` : ''}
            </div>
          </div>`;
        })() : ''}
        <div class="form-section-divider"><span>OBJETIVOS DE RECUPERACION (BIA)</span></div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px;">
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">RTO (horas)</label>
            <div style="font-size:10px;color:var(--text-subtle);margin:2px 0 4px;">Recovery Time Objective</div>
            <input id="pm-rto" class="form-control" type="number" min="0" style="font-size:13px;" value="${proc?.rto_hours??''}" oninput="ViewBcp._calcBiaImpact()">
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">RPO (horas)</label>
            <div style="font-size:10px;color:var(--text-subtle);margin:2px 0 4px;">Recovery Point Objective</div>
            <input id="pm-rpo" class="form-control" type="number" min="0" style="font-size:13px;" value="${proc?.rpo_hours??''}">
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">MTPD (horas)</label>
            <div style="font-size:10px;color:var(--text-subtle);margin:2px 0 4px;">Max. Tolerable Period of Disruption</div>
            <input id="pm-mtpd" class="form-control" type="number" min="0" style="font-size:13px;" value="${proc?.mtpd_hours??''}" oninput="ViewBcp._calcBiaImpact()">
          </div>
        </div>
        <div style="display:grid;grid-template-columns:160px 1fr;gap:12px;margin-bottom:14px;">
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Staff minimo</label>
            <div style="font-size:10px;color:var(--text-subtle);margin:2px 0 4px;">Personas para recuperar</div>
            <input id="pm-staff" class="form-control" type="number" min="0" style="font-size:13px;" value="${proc?.min_recovery_staff??''}">
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">MBCO — Objetivo Minimo de Continuidad</label>
            <div style="font-size:10px;color:var(--text-subtle);margin:2px 0 4px;">Nivel minimo de servicio aceptable</div>
            <textarea id="pm-mbco" class="form-control" rows="2" style="font-size:13px;" placeholder="Ej: 50% de pedidos procesados, acceso de lectura a datos criticos...">${UI.esc(proc?.mbco||'')}</textarea>
          </div>
        </div>

        <div class="form-section-divider"><span>EVALUACION DE IMPACTO BIA</span></div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;">
          ${[['pm-fi','Financiero','financial_impact'],['pm-ri','Reputacional','reputational_impact'],
             ['pm-li','Legal/Reg.','legal_impact'],['pm-oi','Operacional','operational_impact']].map(([id,lbl,fld])=>`
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">${lbl}</label>
            <select id="${id}" class="form-control" style="font-size:12px;">
              ${IMPACTS.map((imp,i)=>`<option value="${i}"${proc?.[fld]===i?' selected':''}>${imp}</option>`).join('')}
            </select>
          </div>`).join('')}
        </div>

        <div class="form-section-divider"><span>ACTIVACION Y PROCEDIMIENTOS</span></div>
        <div style="margin-bottom:14px;">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Criterios de activacion <span style="color:var(--danger)">*</span></label>
          <div style="font-size:11px;color:var(--text-subtle);margin:2px 0 4px;">¿Que condiciones deben darse para activar el plan de este proceso?</div>
          <textarea id="pm-activ" class="form-control" rows="2" style="font-size:13px;">${UI.esc(proc?.activation_criteria||'')}</textarea>
        </div>
        <div style="margin-bottom:14px;">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Procedimiento alternativo <span style="color:var(--danger)">*</span></label>
          <div style="font-size:11px;color:var(--text-subtle);margin:2px 0 4px;">¿Como puede este proceso funcionar manualmente o de forma degradada?</div>
          <textarea id="pm-altproc" class="form-control" rows="2" style="font-size:13px;">${UI.esc(proc?.alternative_procedure||'')}</textarea>
        </div>

        <div class="form-section-divider"><span>RECURSOS Y DOCUMENTACION</span></div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:14px;">
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Registros vitales</label>
            <div style="font-size:11px;color:var(--text-subtle);margin:2px 0 4px;">Un registro por linea</div>
            <textarea id="pm-vr" class="form-control" rows="3" style="font-size:12px;" placeholder="ERP datos ventas&#10;Contratos con clientes&#10;Certificados SSL">${UI.esc(arrToLines(proc?.vital_records))}</textarea>
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Sistemas IT</label>
            <div style="font-size:11px;color:var(--text-subtle);margin:2px 0 4px;">Un sistema por linea</div>
            <textarea id="pm-it" class="form-control" rows="3" style="font-size:12px;" placeholder="ERP SAP&#10;CRM Salesforce&#10;VPN Cisco">${UI.esc(arrToLines(proc?.it_systems))}</textarea>
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Instalaciones</label>
            <div style="font-size:11px;color:var(--text-subtle);margin:2px 0 4px;">Una instalacion por linea</div>
            <textarea id="pm-fac" class="form-control" rows="3" style="font-size:12px;" placeholder="Sede Madrid&#10;CPD principal&#10;Almacen logistico">${UI.esc(arrToLines(proc?.facilities))}</textarea>
          </div>
        </div>

        <div class="form-section-divider"><span>PARAMETROS ENS Y ECONOMICOS</span></div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Categoria ENS</label>
            <select id="pm-ens" class="form-control" style="font-size:13px;">
              <option value="">— No aplica —</option>
              ${['ALTA','MEDIA','BASICA'].map(c => `<option value="${c}"${proc?.ens_category===c?' selected':''}>${c}</option>`).join('')}
            </select>
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Coste indisponibilidad (€/h)</label>
            <div style="font-size:11px;color:var(--text-subtle);margin:2px 0 4px;">Para calcular impacto economico</div>
            <input id="pm-cph" class="form-control" type="number" min="0" style="font-size:13px;" value="${proc?.cost_per_hour??''}" placeholder="Ej: 2500" oninput="ViewBcp._calcBiaImpact()">
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            <div>
              <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Version BIA</label>
              <input id="pm-biaver" class="form-control" style="font-size:13px;" value="${UI.esc(proc?.bia_version||'')}" placeholder="v1.0">
            </div>
            <div>
              <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">Proxima revision</label>
              <input id="pm-biarev" class="form-control" type="date" style="font-size:13px;" value="${proc?.bia_review_date?proc.bia_review_date.substring(0,10):''}">
            </div>
          </div>
        </div>

        <div class="form-section-divider"><span>IMPACTO PROGRESIVO EN EL TIEMPO</span></div>
        <div style="font-size:11px;color:var(--text-subtle);margin-bottom:8px;">¿Como evoluciona el impacto si el proceso sigue sin disponibilidad? (0=Bajo · 1=Medio · 2=Alto)</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:14px;">
          ${[['pm-i1h','A la hora 1','impact_1h'],['pm-i24h','A las 24 horas','impact_24h'],['pm-i7d','A los 7 dias','impact_7d']].map(([id,lbl,fld]) => `
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;">${lbl}</label>
            <select id="${id}" class="form-control" style="font-size:13px;">
              <option value="0"${proc?.[fld]===0?' selected':!proc?.[fld]&&proc?.[fld]!==0?' selected':''}>Bajo</option>
              <option value="1"${proc?.[fld]===1?' selected':''}>Medio</option>
              <option value="2"${proc?.[fld]===2?' selected':''}>Alto</option>
            </select>
          </div>`).join('')}
        </div>

        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;margin-top:4px;">
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px;letter-spacing:.04em;">Calculadora de impacto economico — ISO 22301 §8.2.3</div>
          <div style="font-family:monospace;font-size:11px;color:var(--text-subtle);background:var(--bg-1);padding:5px 10px;border-radius:3px;margin-bottom:10px;">Impacto (€) = €/h × RTO (h)&nbsp;&nbsp;|&nbsp;&nbsp;Regla: RPO &lt; RTO &lt; MTPD</div>
          <div id="pm-calc-result" style="font-family:monospace;font-size:14px;font-weight:700;color:var(--text-primary);min-height:20px;"></div>
          <div id="pm-rto-warn" style="display:none;margin-top:8px;padding:8px 12px;background:#fef2f2;border:1px solid #fca5a5;border-radius:4px;color:#b91c1c;font-size:12px;font-weight:600;">ALERTA: RTO &gt;= MTPD — El plan de recuperacion es INVIABLE. Reduzca el RTO o revise el MTPD.</div>
        </div>

      </div>
      <div class="modal-footer-sticky">
        ${proc ? `<button class="btn btn-danger btn-sm" onclick="ViewBcp._delProc(${proc.id})"><i class="ti ti-trash"></i> Eliminar</button>` : ''}
        <div style="display:flex;gap:8px;margin-left:auto;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-primary btn-sm" onclick="ViewBcp._saveProc(${proc?.id||'null'})"><i class="ti ti-check"></i> Guardar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  function _editProc(id) {
    const proc = _procs.find(p => p.id === id);
    if (proc) _openProcModal(proc);
    else Api.get('/api/bcp/processes').then(list => {
      const p = list.find(x => x.id === id);
      if (p) { _procs = list; _openProcModal(p); }
    }).catch(() => {});
  }

  async function _openBiaPicker() {
    if (!_procs.length) _procs = await Api.get('/api/bcp/processes').catch(() => []);
    const incomplete = _procs.filter(p => (p.bia_pct || 0) < 100).sort((a, b) => {
      const order = { critical: 0, high: 1, medium: 2, low: 3 };
      return (order[a.criticality] ?? 2) - (order[b.criticality] ?? 2);
    });

    if (!incomplete.length) { _openProcModal(null, true); return; }

    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:480px;">
      <div class="modal-header">
        <h2>Nuevo / Completar BIA</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:20px 24px;">
        <p style="margin:0 0 14px;font-size:13px;color:var(--text-subtle);">
          El BIA forma parte del proceso critico. Selecciona un proceso existente para completar su analisis de impacto, o crea uno nuevo.
        </p>
        <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:6px;">Proceso</label>
        <select id="bia-proc-sel" class="form-control" style="font-size:13px;margin-bottom:12px;">
          <option value="new">+ Crear proceso nuevo</option>
          <optgroup label="Procesos con BIA incompleto">
            ${incomplete.map(p => {
              const pct = p.bia_pct || 0;
              const color = pct >= 80 ? '#16a34a' : pct >= 50 ? '#D97706' : '#DC2626';
              return `<option value="${p.id}" data-pct="${pct}" data-missing='${JSON.stringify(p.bia_missing||[])}'>${UI.esc(p.name)} — BIA ${pct}%</option>`;
            }).join('')}
          </optgroup>
        </select>
        <div id="bia-picker-preview" style="display:none;padding:10px;background:var(--bg-2);border-radius:var(--radius);font-size:12px;"></div>
      </div>
      <div class="modal-footer-sticky">
        <div style="display:flex;gap:8px;margin-left:auto;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-primary btn-sm" id="bia-pick-go"><i class="ti ti-arrow-right"></i> Continuar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);

    const sel = modal.querySelector('#bia-proc-sel');
    const preview = modal.querySelector('#bia-picker-preview');

    function updatePreview() {
      const opt = sel.options[sel.selectedIndex];
      const val = sel.value;
      if (val === 'new') { preview.style.display = 'none'; return; }
      const pct = parseInt(opt.dataset.pct || '0');
      const color = pct >= 80 ? '#16a34a' : pct >= 50 ? '#D97706' : '#DC2626';
      let missing = [];
      try { missing = JSON.parse(opt.dataset.missing || '[]'); } catch (_) {}
      const fieldLabels = {
        rto_hours: 'RTO', rpo_hours: 'RPO', mtpd_hours: 'MTPD', mbco: 'MBCO',
        financial_impact: 'Impacto financiero', reputational_impact: 'Impacto reputacional',
        legal_impact: 'Impacto legal', operational_impact: 'Impacto operacional',
        activation_criteria: 'Criterios de activacion', vital_records: 'Registros vitales',
      };
      preview.style.display = 'block';
      preview.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <span style="font-weight:700;font-size:13px;">${UI.esc(opt.text.split(' — ')[0])}</span>
          <span style="color:${color};font-weight:700;">BIA ${pct}%</span>
        </div>
        <div style="height:5px;background:var(--bg-3);border-radius:3px;margin-bottom:8px;">
          <div style="width:${pct}%;height:100%;background:${color};border-radius:3px;"></div>
        </div>
        ${missing.length
          ? `<div style="color:#DC2626;font-size:11px;">Campos pendientes: ${missing.map(f => fieldLabels[f] || f).join(', ')}</div>`
          : '<div style="color:#16a34a;font-size:11px;">BIA completamente relleno</div>'}`;
    }

    sel.addEventListener('change', updatePreview);
    updatePreview();

    modal.querySelector('#bia-pick-go').addEventListener('click', () => {
      const val = sel.value;
      modal.remove();
      if (val === 'new') { _openProcModal(null, true); }
      else { const p = _procs.find(x => x.id === parseInt(val)); if (p) _openProcModal(p); }
    });
  }

  async function _saveProc(id) {
    const g = eid => document.getElementById(eid);
    // Convertir textarea multi-linea a array (filtrar lineas vacias)
    const linesToArr = (val) => {
      const lines = (val || '').split('\n').map(l => l.trim()).filter(Boolean);
      return lines.length ? lines : null;
    };
    const body = {
      name: g('pm-name').value.trim(),
      description: g('pm-desc').value || null,
      criticality: g('pm-crit').value,
      priority: parseInt(g('pm-prio').value) || null,
      owner_id: parseInt(g('pm-owner').value) || null,
      recovery_owner_id: parseInt(g('pm-rowner').value) || null,
      rto_hours: parseInt(g('pm-rto').value) || null,
      rpo_hours: parseInt(g('pm-rpo').value) || null,
      mtpd_hours: parseInt(g('pm-mtpd').value) || null,
      min_recovery_staff: parseInt(g('pm-staff').value) || null,
      mbco: g('pm-mbco').value || null,
      financial_impact: parseInt(g('pm-fi').value),
      reputational_impact: parseInt(g('pm-ri').value),
      legal_impact: parseInt(g('pm-li').value),
      operational_impact: parseInt(g('pm-oi').value),
      activation_criteria: g('pm-activ').value || null,
      alternative_procedure: g('pm-altproc').value || null,
      vital_records: linesToArr(g('pm-vr')?.value),
      it_systems: linesToArr(g('pm-it')?.value),
      facilities: linesToArr(g('pm-fac')?.value),
      // BIA campos normativos
      ens_category: g('pm-ens')?.value || null,
      cost_per_hour: parseFloat(g('pm-cph')?.value) || null,
      impact_1h: parseInt(g('pm-i1h')?.value) ?? null,
      impact_24h: parseInt(g('pm-i24h')?.value) ?? null,
      impact_7d: parseInt(g('pm-i7d')?.value) ?? null,
      bia_version: g('pm-biaver')?.value || null,
      bia_review_date: g('pm-biarev')?.value || null,
      location_id: parseInt(g('pm-location')?.value) || null,
    };
    if (!body.name) { UI.toast('El nombre es obligatorio', 'error'); return; }
    try {
      if (id) await Api.patch(`/api/bcp/processes/${id}`, body);
      else await Api.post('/api/bcp/processes', body);
      UI.toast('Proceso guardado', 'success');
      document.querySelector('.modal-bg')?.remove();
      _procs = [];
      _switchTab('processes');
    } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
  }

  async function _delProc(id) {
    if (!confirm('Eliminar proceso? Esta accion no se puede deshacer.')) return;
    try {
      await Api.del(`/api/bcp/processes/${id}`);
      UI.toast('Proceso eliminado', 'success');
      document.querySelector('.modal-bg')?.remove();
      _procs = [];
      _switchTab('processes');
    } catch (e) { UI.toast('Error al eliminar: ' + (e.message || e), 'error'); }
  }

  // ── Modales — Dependencia ────────────────────────────────────────────────────

  function _openDepModal(dep, isProcDep) {
    const isProc = isProcDep || dep?.dependency_type === 'process' || !!dep?.depends_on_process_id;
    const DEP_TYPES = ['IT_system','personnel','facility','supplier','utility','communication','transport','external_service'];
    const lbl = (text, req) => `<label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;display:block;margin-bottom:4px;">${text}${req ? ' <span style="color:var(--danger)">*</span>' : ''}</label>`;

    const modal = document.createElement('div');
    modal.className = 'modal-bg';

    if (isProc) {
      // Formulario proceso-proceso
      modal.innerHTML = `
      <div class="modal" style="max-width:520px;">
        <div class="modal-header">
          <h2>${dep ? 'Editar dependencia de proceso' : 'Nueva dependencia proceso-proceso'}</h2>
          <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
        </div>
        <div style="display:block;padding:20px;overflow-y:auto;">
          <div style="margin-bottom:14px;">${lbl('Proceso origen', true)}
            <select id="dm-proc" class="form-control" style="font-size:13px;">
              ${_procs.map(p=>`<option value="${p.id}"${dep?.process_id===p.id?' selected':''}>${UI.esc(p.name)}</option>`).join('')}
            </select>
          </div>
          <div style="margin-bottom:14px;">${lbl('Depende de (proceso)', true)}
            <select id="dm-dep-proc" class="form-control" style="font-size:13px;">
              <option value="">— Seleccionar proceso dependiente —</option>
              ${_procs.map(p=>`<option value="${p.id}"${dep?.depends_on_process_id===p.id?' selected':''}>${UI.esc(p.name)}</option>`).join('')}
            </select>
          </div>
          <div style="margin-bottom:14px;">${lbl('Motivo / descripcion')}
            <textarea id="dm-name" class="form-control" rows="2" style="font-size:13px;" placeholder="¿Por que depende este proceso del otro?">${UI.esc(dep?.description || dep?.name || '')}</textarea>
          </div>
          <div style="margin-bottom:14px;">${lbl('Secuencia de recuperacion')}
            <input id="dm-seq" class="form-control" type="number" min="1" style="font-size:13px;" value="${dep?.recovery_sequence??''}" placeholder="Orden (1 = primero que debe estar disponible)">
          </div>
          <div style="margin-bottom:14px;">${lbl('Impacto si no esta disponible')}
            <textarea id="dm-alt" class="form-control" rows="2" style="font-size:13px;" placeholder="¿Que pasa si este proceso dependiente no esta disponible?">${UI.esc(dep?.alternative||'')}</textarea>
          </div>
        </div>
        <div class="modal-footer-sticky">
          ${dep ? `<button class="btn btn-danger btn-sm" onclick="ViewBcp._delDep(${dep.id})"><i class="ti ti-trash"></i></button>` : ''}
          <div style="display:flex;gap:8px;margin-left:auto;">
            <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
            <button class="btn btn-primary btn-sm" onclick="ViewBcp._saveDep(${dep?.id||'null'}, true)"><i class="ti ti-check"></i> Guardar</button>
          </div>
        </div>
      </div>`;
    } else {
      // Formulario recurso / dependencia externa
      modal.innerHTML = `
      <div class="modal" style="max-width:580px;max-height:90vh;display:flex;flex-direction:column;">
        <div class="modal-header" style="flex-shrink:0;">
          <h2>${dep ? 'Editar recurso/dependencia' : 'Nueva dependencia de recurso'}</h2>
          <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
        </div>
        <div class="modal-body" style="overflow-y:auto;flex:1;padding:20px;display:block;">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
            <div>${lbl('Proceso critico', true)}
              <select id="dm-proc" class="form-control" style="font-size:13px;">
                ${_procs.map(p=>`<option value="${p.id}"${dep?.process_id===p.id?' selected':''}>${UI.esc(p.name)}</option>`).join('')}
              </select>
            </div>
            <div>${lbl('Tipo de dependencia', true)}
              <select id="dm-type" class="form-control" style="font-size:13px;">
                ${DEP_TYPES.map(t=>`<option value="${t}"${dep?.dependency_type===t?' selected':''}>${DEP_LABELS[t]||t}</option>`).join('')}
              </select>
            </div>
          </div>
          <div style="margin-bottom:14px;">${lbl('Nombre del recurso', true)}
            <input id="dm-name" class="form-control" style="font-size:13px;" value="${UI.esc(dep?.name||'')}" placeholder="Ej: ERP SAP, Equipo tecnico de red">
          </div>
          <div style="margin-bottom:14px;">${lbl('Descripcion')}
            <textarea id="dm-desc" class="form-control" rows="2" style="font-size:13px;">${UI.esc(dep?.description||'')}</textarea>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:14px;">
            <div>${lbl('Qty operacion normal')}
              <input id="dm-qn" class="form-control" type="number" style="font-size:13px;" value="${dep?.qty_normal??''}">
            </div>
            <div>${lbl('Qty minima recuperacion')}
              <input id="dm-qr" class="form-control" type="number" style="font-size:13px;" value="${dep?.qty_recovery??''}">
            </div>
            <div>${lbl('RTO necesario (horas)')}
              <input id="dm-rto" class="form-control" type="number" style="font-size:13px;" value="${dep?.rto_hours??''}">
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
            <div>${lbl('Secuencia de recuperacion')}
              <div style="font-size:11px;color:var(--text-subtle);margin:2px 0 4px;">Orden (1 = primero que debe estar)</div>
              <input id="dm-seq" class="form-control" type="number" min="1" style="font-size:13px;" value="${dep?.recovery_sequence??''}">
            </div>
            <div style="display:flex;align-items:center;gap:8px;padding-top:26px;">
              <input id="dm-crit" type="checkbox" ${dep?.is_critical?' checked':''}>
              <label for="dm-crit" style="margin:0;font-size:13px;">Es critico (sin el, la recuperacion no puede comenzar)</label>
            </div>
          </div>
          <div style="margin-bottom:14px;">${lbl('Procedimiento alternativo')}
            <textarea id="dm-alt" class="form-control" rows="2" style="font-size:13px;" placeholder="¿Que se hace si no esta disponible?">${UI.esc(dep?.alternative||'')}</textarea>
          </div>
          <div style="margin-bottom:14px;">${lbl('Notas adicionales')}
            <textarea id="dm-notes" class="form-control" rows="2" style="font-size:13px;">${UI.esc(dep?.notes||'')}</textarea>
          </div>

          <!-- Interconexion tecnica -->
          <details style="margin-bottom:4px;border:1px solid var(--border);border-radius:6px;overflow:hidden;" ${dep?.connection_type ? 'open' : ''}>
            <summary style="padding:8px 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--text-subtle);cursor:pointer;background:var(--bg-2);user-select:none;">
              <i class="ti ti-git-branch" style="margin-right:4px"></i> Interconexion tecnica (ISO 22301 §8.2)
            </summary>
            <div style="padding:14px;display:grid;grid-template-columns:1fr 1fr;gap:10px;">
              <div>${lbl('Tipo de conexion')}
                <select id="dm-conn-type" class="form-control" style="font-size:13px;">
                  <option value="">— Seleccionar —</option>
                  ${['API','database','network','file_transfer','manual','messaging'].map(v=>
                    `<option value="${v}"${dep?.connection_type===v?' selected':''}>${v}</option>`).join('')}
                </select>
              </div>
              <div>${lbl('Protocolo')}
                <input id="dm-protocol" class="form-control" style="font-size:13px;" placeholder="HTTPS, SQL, SMB, SFTP..." value="${UI.esc(dep?.protocol||'')}">
              </div>
              <div>${lbl('Direccion del flujo')}
                <select id="dm-data-dir" class="form-control" style="font-size:13px;">
                  <option value="">— Seleccionar —</option>
                  ${[['in','Entrada (in)'],['out','Salida (out)'],['both','Bidireccional (both)']].map(([v,l])=>
                    `<option value="${v}"${dep?.data_direction===v?' selected':''}>${l}</option>`).join('')}
                </select>
              </div>
              <div>${lbl('Clasificacion del dato')}
                <select id="dm-data-class" class="form-control" style="font-size:13px;">
                  <option value="">— Seleccionar —</option>
                  ${[['public','Publico'],['internal','Interno'],['confidential','Confidencial'],['strictly_confidential','Estrictamente confidencial']].map(([v,l])=>
                    `<option value="${v}"${dep?.data_classification===v?' selected':''}>${l}</option>`).join('')}
                </select>
              </div>
            </div>
          </details>

        </div>
        <div class="modal-footer-sticky">
          ${dep ? `<button class="btn btn-danger btn-sm" onclick="ViewBcp._delDep(${dep.id})"><i class="ti ti-trash"></i> Eliminar</button>` : ''}
          <div style="display:flex;gap:8px;margin-left:auto;">
            <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
            <button class="btn btn-primary btn-sm" onclick="ViewBcp._saveDep(${dep?.id||'null'}, false)"><i class="ti ti-check"></i> Guardar</button>
          </div>
        </div>
      </div>`;
    }
    document.body.appendChild(modal);
  }

  function _editDep(id) { _openDepModal(_deps.find(d => d.id === id)); }

  async function _saveDep(id, isProc) {
    const g = eid => document.getElementById(eid);
    let body;
    if (isProc) {
      const depProcId = parseInt(g('dm-dep-proc')?.value) || null;
      if (!depProcId) { UI.toast('Selecciona el proceso del que depende', 'error'); return; }
      body = {
        process_id: parseInt(g('dm-proc').value),
        dependency_type: 'process',
        name: g('dm-name')?.value?.trim() || 'Dependencia de proceso',
        description: g('dm-name')?.value?.trim() || null,
        depends_on_process_id: depProcId,
        recovery_sequence: parseInt(g('dm-seq')?.value) || null,
        alternative: g('dm-alt')?.value || null,
        is_critical: false,
      };
    } else {
      body = {
        process_id: parseInt(g('dm-proc').value),
        dependency_type: g('dm-type').value,
        name: g('dm-name').value.trim(),
        description: g('dm-desc')?.value || null,
        qty_normal: parseInt(g('dm-qn').value) || null,
        qty_recovery: parseInt(g('dm-qr').value) || null,
        rto_hours: parseInt(g('dm-rto').value) || null,
        is_critical: g('dm-crit')?.checked || false,
        alternative: g('dm-alt')?.value || null,
        recovery_sequence: parseInt(g('dm-seq')?.value) || null,
        notes: g('dm-notes')?.value || null,
        connection_type:     g('dm-conn-type')?.value  || null,
        protocol:            g('dm-protocol')?.value   || null,
        data_direction:      g('dm-data-dir')?.value   || null,
        data_classification: g('dm-data-class')?.value || null,
      };
      if (!body.name) { UI.toast('El nombre del recurso es obligatorio', 'error'); return; }
    }
    try {
      if (id) await Api.patch(`/api/bcp/dependencies/${id}`, body);
      else await Api.post('/api/bcp/dependencies', body);
      UI.toast('Dependencia guardada', 'success');
      document.querySelector('.modal-bg')?.remove();
      _deps = [];
      _switchTab('dependencies');
    } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
  }

  async function _delDep(id) {
    if (!confirm('Eliminar dependencia?')) return;
    try {
      await Api.del(`/api/bcp/dependencies/${id}`);
      UI.toast('Dependencia eliminada', 'success');
      document.querySelector('.modal-bg')?.remove();
      _switchTab('dependencies');
    } catch (e) { UI.toast('Error al eliminar: ' + (e.message || e), 'error'); }
  }

  // ── Modales — Estrategia ─────────────────────────────────────────────────────

  function _openStratModal(strat) {
    const TYPES = ['hot_site','cold_site','warm_site','work_from_home','outsourcing','manual_workaround','dual_site','cloud_failover'];
    const TYPE_LABELS = {hot_site:'Hot site',cold_site:'Cold site',warm_site:'Warm site',
      work_from_home:'Trabajo remoto',outsourcing:'Outsourcing',manual_workaround:'Procedimiento manual',
      dual_site:'Dual site',cloud_failover:'Cloud failover'};
    const STATUS_OPTS = [{v:'planned',l:'Planificado'},{v:'in_progress',l:'En progreso'},
      {v:'implemented',l:'Implementado'},{v:'tested',l:'Probado'}];
    const lbl = t => `<label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;display:block;margin-bottom:4px;">${t}</label>`;
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:520px;max-height:90vh;display:flex;flex-direction:column;">
      <div class="modal-header" style="flex-shrink:0;">
        <h2>${strat ? 'Editar estrategia' : 'Nueva estrategia de recuperacion'}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="overflow-y:auto;flex:1;padding:20px 24px;display:block;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>${lbl('Tipo *')}
            <select id="sm-type" class="form-control" style="font-size:13px;">
              ${TYPES.map(t=>`<option value="${t}"${strat?.strategy_type===t?' selected':''}>${TYPE_LABELS[t]||t}</option>`).join('')}
            </select>
          </div>
          <div>${lbl('Estado')}
            <select id="sm-status" class="form-control" style="font-size:13px;">
              ${STATUS_OPTS.map(s=>`<option value="${s.v}"${strat?.implementation_status===s.v?' selected':''}>${s.l}</option>`).join('')}
            </select>
          </div>
        </div>
        <div style="margin-bottom:14px;">${lbl('Nombre *')}
          <input id="sm-name" class="form-control" style="font-size:13px;" value="${UI.esc(strat?.name||'')}">
        </div>
        <div style="margin-bottom:14px;">${lbl('Proceso vinculado (opcional)')}
          <select id="sm-proc" class="form-control" style="font-size:13px;">
            <option value="">— Global (aplica a todos los procesos) —</option>
            ${_procs.map(p=>`<option value="${p.id}"${strat?.process_id===p.id?' selected':''}>${UI.esc(p.name)}</option>`).join('')}
          </select>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>${lbl('Coste estimado (€)')}
            <input id="sm-cost" class="form-control" type="number" style="font-size:13px;" value="${strat?.estimated_cost??''}">
          </div>
          <div>${lbl('Fecha objetivo')}
            <input id="sm-date" class="form-control" type="date" style="font-size:13px;" value="${strat?.target_date?strat.target_date.substring(0,10):''}">
          </div>
        </div>
        <div style="margin-bottom:14px;">${lbl('Descripcion')}
          <textarea id="sm-desc" class="form-control" rows="3" style="font-size:13px;">${UI.esc(strat?.description||'')}</textarea>
        </div>

        <!-- Seccion colapsable: Configuracion tecnica IT -->
        <details style="margin-bottom:14px;border:1px solid var(--border);border-radius:6px;overflow:hidden;" ${strat?.it_config ? 'open' : ''}>
          <summary style="padding:10px 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--text-subtle);cursor:pointer;background:var(--bg-2);user-select:none;">
            <i class="ti ti-server" style="margin-right:4px"></i> Configuracion tecnica IT (ISO 22301 §8.4)
          </summary>
          <div style="padding:14px;display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <div>${lbl('Disponibilidad objetivo (%)')}
              <input id="sm-avail" class="form-control" type="number" min="0" max="100" step="0.01" style="font-size:13px;" value="${strat?.it_config?.availability_pct??''}">
            </div>
            <div>${lbl('Tipo failover')}
              <select id="sm-failover" class="form-control" style="font-size:13px;">
                <option value="">— Seleccionar —</option>
                ${['none','active-passive','active-active'].map(v=>`<option value="${v}"${strat?.it_config?.failover_type===v?' selected':''}>${v}</option>`).join('')}
              </select>
            </div>
            <div>${lbl('vCPUs compute')}
              <input id="sm-vcpu" class="form-control" type="number" min="0" style="font-size:13px;" value="${strat?.it_config?.compute_vcpus??''}">
            </div>
            <div>${lbl('RAM (GB)')}
              <input id="sm-ram" class="form-control" type="number" min="0" style="font-size:13px;" value="${strat?.it_config?.ram_gb??''}">
            </div>
            <div>${lbl('Almacenamiento (TB)')}
              <input id="sm-stor" class="form-control" type="number" min="0" step="0.1" style="font-size:13px;" value="${strat?.it_config?.storage_tb??''}">
            </div>
            <div>${lbl('Virtualizacion')}
              <input id="sm-virt" class="form-control" style="font-size:13px;" placeholder="VMware / Hyper-V / KVM..." value="${UI.esc(strat?.it_config?.virtualization_type||'')}">
            </div>
            <div>${lbl('Hosts minimos')}
              <input id="sm-hosts" class="form-control" type="number" min="1" style="font-size:13px;" value="${strat?.it_config?.min_hosts??''}">
            </div>
            <div>${lbl('Ubicacion backup offsite')}
              <input id="sm-offsite" class="form-control" style="font-size:13px;" placeholder="CPD secundario, cloud..." value="${UI.esc(strat?.it_config?.offsite_location||'')}">
            </div>
            <div>${lbl('RPO backup (horas)')}
              <input id="sm-bkp-rpo" class="form-control" type="number" min="0" style="font-size:13px;" value="${strat?.it_config?.backup_rpo_hours??''}">
            </div>
            <div>${lbl('RTO backup (horas)')}
              <input id="sm-bkp-rto" class="form-control" type="number" min="0" style="font-size:13px;" value="${strat?.it_config?.backup_rto_hours??''}">
            </div>
            <div style="grid-column:span 2">${lbl('Retencion backup (dias)')}
              <input id="sm-bkp-ret" class="form-control" type="number" min="1" style="font-size:13px;" value="${strat?.it_config?.backup_retention_days??''}">
            </div>
          </div>
        </details>

        <!-- Seccion colapsable: Monitorizacion y mantenimiento -->
        <details style="margin-bottom:14px;border:1px solid var(--border);border-radius:6px;overflow:hidden;" ${strat?.monitoring_config ? 'open' : ''}>
          <summary style="padding:10px 14px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--text-subtle);cursor:pointer;background:var(--bg-2);user-select:none;">
            <i class="ti ti-activity" style="margin-right:4px"></i> Monitorizacion y mantenimiento
          </summary>
          <div style="padding:14px;display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <div>${lbl('Herramienta de monitorizacion')}
              <input id="sm-mon-tool" class="form-control" style="font-size:13px;" placeholder="Zabbix, Nagios, Datadog..." value="${UI.esc(strat?.monitoring_config?.monitoring_tool||'')}">
            </div>
            <div>${lbl('Email alertas')}
              <input id="sm-mon-email" class="form-control" type="email" style="font-size:13px;" value="${UI.esc(strat?.monitoring_config?.alert_email||'')}">
            </div>
            <div>${lbl('Umbral CPU (%)')}
              <input id="sm-thr-cpu" class="form-control" type="number" min="0" max="100" style="font-size:13px;" value="${strat?.monitoring_config?.threshold_cpu_pct??''}">
            </div>
            <div>${lbl('Umbral memoria (%)')}
              <input id="sm-thr-mem" class="form-control" type="number" min="0" max="100" style="font-size:13px;" value="${strat?.monitoring_config?.threshold_mem_pct??''}">
            </div>
            <div>${lbl('Ventana mantenimiento')}
              <input id="sm-maint" class="form-control" style="font-size:13px;" placeholder="Ej: sabados 02:00-04:00 UTC" value="${UI.esc(strat?.monitoring_config?.maintenance_window||'')}">
            </div>
            <div>${lbl('Parches de seguridad (dias)')}
              <input id="sm-patch-sec" class="form-control" type="number" min="1" style="font-size:13px;" value="${strat?.monitoring_config?.security_patch_days??''}">
            </div>
            <div style="grid-column:span 2">${lbl('Actualizaciones de funcionalidad (dias)')}
              <input id="sm-patch-feat" class="form-control" type="number" min="1" style="font-size:13px;" value="${strat?.monitoring_config?.feature_update_days??''}">
            </div>
          </div>
        </details>

      </div>
      <div class="modal-footer-sticky">
        ${strat ? `<button class="btn btn-danger btn-sm" onclick="ViewBcp._delStrat(${strat.id})"><i class="ti ti-trash"></i> Eliminar</button>` : ''}
        <div style="display:flex;gap:8px;margin-left:auto;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-primary btn-sm" onclick="ViewBcp._saveStrat(${strat?.id||'null'})"><i class="ti ti-check"></i> Guardar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  function _editStrat(id) { _openStratModal(_strats.find(s => s.id === id)); }

  async function _saveStrat(id) {
    const g = i => document.getElementById(i);
    const itCfg = {
      availability_pct:      parseFloat(g('sm-avail')?.value)  || null,
      compute_vcpus:         parseInt(g('sm-vcpu')?.value)      || null,
      ram_gb:                parseInt(g('sm-ram')?.value)        || null,
      storage_tb:            parseFloat(g('sm-stor')?.value)    || null,
      failover_type:         g('sm-failover')?.value            || null,
      virtualization_type:   g('sm-virt')?.value                || null,
      min_hosts:             parseInt(g('sm-hosts')?.value)      || null,
      backup_rpo_hours:      parseInt(g('sm-bkp-rpo')?.value)   || null,
      backup_rto_hours:      parseInt(g('sm-bkp-rto')?.value)   || null,
      backup_retention_days: parseInt(g('sm-bkp-ret')?.value)   || null,
      offsite_location:      g('sm-offsite')?.value             || null,
    };
    const monCfg = {
      monitoring_tool:       g('sm-mon-tool')?.value  || null,
      threshold_cpu_pct:     parseInt(g('sm-thr-cpu')?.value)  || null,
      threshold_mem_pct:     parseInt(g('sm-thr-mem')?.value)  || null,
      alert_email:           g('sm-mon-email')?.value || null,
      maintenance_window:    g('sm-maint')?.value     || null,
      security_patch_days:   parseInt(g('sm-patch-sec')?.value)  || null,
      feature_update_days:   parseInt(g('sm-patch-feat')?.value) || null,
    };
    const itHasData  = Object.values(itCfg).some(v => v !== null && v !== '');
    const monHasData = Object.values(monCfg).some(v => v !== null && v !== '');
    const body = {
      strategy_type: g('sm-type').value,
      name: g('sm-name').value.trim(),
      process_id: parseInt(g('sm-proc').value)||null,
      implementation_status: g('sm-status').value,
      estimated_cost: parseFloat(g('sm-cost').value)||null,
      target_date: g('sm-date').value||null,
      description: g('sm-desc').value||null,
      it_config:         itHasData  ? itCfg  : null,
      monitoring_config: monHasData ? monCfg : null,
    };
    if (!body.name) { UI.toast('El nombre es obligatorio', 'error'); return; }
    try {
      if (id) await Api.patch(`/api/bcp/strategies/${id}`, body);
      else await Api.post('/api/bcp/strategies', body);
      UI.toast('Estrategia guardada', 'success');
      document.querySelector('.modal-bg')?.remove();
      _switchTab('strategies');
    } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
  }

  async function _delStrat(id) {
    if (!confirm('Eliminar estrategia?')) return;
    try {
      await Api.del(`/api/bcp/strategies/${id}`);
      UI.toast('Estrategia eliminada', 'success');
      document.querySelector('.modal-bg')?.remove();
      _switchTab('strategies');
    } catch (e) { UI.toast('Error al eliminar: ' + (e.message || e), 'error'); }
  }

  // ── Drawer — Plan ────────────────────────────────────────────────────────────

  let _currentPlanId = null;

  function _openPlanDrawer(plan) {
    _currentPlanId = plan?.id || null;
    const TYPES = ['bcp','drp','crp','ems','pandemic','cyber_response','supply_chain'];
    const CLASSIFS = [['confidential','Confidencial'],['internal','Uso interno'],['restricted','Restringido']];
    const lbl = (text, req, sub) =>
      `<label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;display:block;margin-bottom:4px;">${text}${req?' <span style="color:var(--danger)">*</span>':''}
      </label>${sub?`<div style="font-size:10px;color:var(--text-subtle);margin-bottom:4px;">${sub}</div>`:''}`;

    // Obtener secciones del plan
    const sections = plan?.sections || [];
    const getSec = id => (sections.find(s => s.id === id) || {}).content || '';
    const sysDeps = plan?.system_dependencies || [];
    const roles = plan?.roles_matrix || [];
    const contacts = plan?.contact_list || [];
    const kpis = plan?.kpis || [];

    const titleEl = document.getElementById('plan-drawer-title');
    if (titleEl) titleEl.textContent = plan ? `Editar plan: ${plan.code}` : 'Nuevo Plan BCP/DRP';

    const body = document.getElementById('plan-drawer-body');
    if (!body) return;

    const showForTypes = (types, pt) => types.includes(pt || 'bcp') ? '' : 'style="display:none"';
    const currType = plan?.plan_type || 'bcp';

    body.innerHTML = `
    <!-- SECCION 1: Cabecera -->
    <div class="form-section-divider"><span>CABECERA DEL PLAN</span></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
      <div>${lbl('Tipo de plan','*')}
        <select id="pl-type" class="form-control" style="font-size:13px;" onchange="ViewBcp._onPlanTypeChange(this.value)">
          ${TYPES.map(t=>`<option value="${t}"${currType===t?' selected':''}>${PLAN_TYPE_LABELS[t]||t}</option>`).join('')}
        </select>
      </div>
      <div>${lbl('Version')}
        <input id="pl-ver" class="form-control" style="font-size:13px;" value="${UI.esc(plan?.version||'1.0')}">
      </div>
    </div>
    <div style="margin-bottom:14px;">${lbl('Nombre del plan','*')}
      <input id="pl-name" class="form-control" style="font-size:13px;" value="${UI.esc(plan?.name||'')}">
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
      <div>${lbl('Clasificacion')}
        <select id="pl-class" class="form-control" style="font-size:13px;">
          <option value="">— Sin clasificar —</option>
          ${CLASSIFS.map(([v,l])=>`<option value="${v}"${plan?.classification===v?' selected':''}>${l}</option>`).join('')}
        </select>
      </div>
      <div>${lbl('Propietario del plan')}
        <input id="pl-owner" class="form-control" style="font-size:13px;" value="${UI.esc(plan?.plan_owner_name||'')}" placeholder="Nombre del responsable">
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
      <div>${lbl('Fecha proxima revision')}
        <input id="pl-rev" class="form-control" type="date" style="font-size:13px;" value="${plan?.review_date ? plan.review_date.substring(0,10) : (() => { const d = new Date(); d.setFullYear(d.getFullYear()+1); return d.toISOString().substring(0,10); })()}">
      </div>
      <div>${lbl('ID documento vinculado')}
        <input id="pl-doc" class="form-control" type="number" style="font-size:13px;" value="${plan?.document_id||''}" placeholder="ID del documento en Agente IA">
      </div>
    </div>
    <div style="margin-bottom:14px;">${lbl('Procesos cubiertos')}
      <div style="max-height:120px;overflow-y:auto;border:0.5px solid var(--border);border-radius:var(--radius);padding:8px;">
      ${_procs.map(p => `<label style="display:flex;gap:6px;align-items:center;padding:3px;font-size:13px;cursor:pointer;">
        <input type="checkbox" value="${p.id}" class="pl-pids" ${(plan?.process_ids||[]).includes(p.id)?'checked':''}>
        <span class="badge" style="font-size:10px;background:${CRIT_COLORS[p.criticality]||''}22;color:${CRIT_COLORS[p.criticality]||'#666'}">${p.criticality}</span>
        ${UI.esc(p.name)}
      </label>`).join('')}
      </div>
    </div>

    <!-- SECCION 2: Alcance y objetivos -->
    <div class="form-section-divider"><span>ALCANCE Y OBJETIVOS</span></div>
    <div style="margin-bottom:14px;">${lbl('Alcance del plan')}
      <textarea id="pl-scope" class="form-control" rows="3" style="font-size:13px;" placeholder="¿Que sistemas, procesos y areas cubre este plan?">${UI.esc(plan?.scope||'')}</textarea>
    </div>
    <div style="margin-bottom:14px;">${lbl('Criterios de activacion')}
      <div style="font-size:10px;color:var(--text-subtle);margin-bottom:4px;">¿Cuando se activa este plan? Incluir condiciones formales.</div>
      <textarea id="pl-activ" class="form-control" rows="3" style="font-size:13px;">${UI.esc(plan?.activation_criteria||'')}</textarea>
    </div>
    <div style="margin-bottom:14px;">${lbl('Resumen ejecutivo')}
      <textarea id="pl-sum" class="form-control" rows="2" style="font-size:13px;">${UI.esc(plan?.content_summary||'')}</textarea>
    </div>

    <!-- SECCION 3: RTO/RPO por sistema (solo DRP/CRP) -->
    <div id="pl-sys-section" ${showForTypes(['drp','crp'], currType)}>
      <div class="form-section-divider"><span>RTO/RPO POR SISTEMA</span></div>
      <div class="inline-table-wrap" style="margin-bottom:8px;">
        <table class="inline-table">
          <thead><tr><th>Sistema / Servicio</th><th>RTO (h)</th><th>RPO (h)</th><th>Responsable</th><th>Notas</th><th style="width:30px"></th></tr></thead>
          <tbody id="pl-sys-tbody">
            ${sysDeps.map((s,i)=>`<tr>
              <td><input value="${UI.esc(s.system_name||'')}" oninput="ViewBcp._updateSysDep(${i},'system_name',this.value)"></td>
              <td><input type="number" value="${s.rto_hours??''}" style="width:60px;" oninput="ViewBcp._updateSysDep(${i},'rto_hours',this.value)"></td>
              <td><input type="number" value="${s.rpo_hours??''}" style="width:60px;" oninput="ViewBcp._updateSysDep(${i},'rpo_hours',this.value)"></td>
              <td><input value="${UI.esc(s.responsible||'')}" oninput="ViewBcp._updateSysDep(${i},'responsible',this.value)"></td>
              <td><input value="${UI.esc(s.notes||'')}" oninput="ViewBcp._updateSysDep(${i},'notes',this.value)"></td>
              <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeSysDep(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
      <button class="btn btn-ghost btn-sm" onclick="ViewBcp._addSysDep()" style="margin-bottom:14px;font-size:12px;">
        <i class="ti ti-plus"></i> Anadir sistema
      </button>
    </div>

    <!-- SECCION 4: Procedimientos de recuperacion (DRP/CRP/Cyber) -->
    <div id="pl-proc-section" ${showForTypes(['drp','crp','cyber_response'], currType)}>
      <div class="form-section-divider"><span>PROCEDIMIENTOS DE RECUPERACION</span></div>
      ${[
        ['notification','Notificacion','Quién avisa a quién y como en las primeras horas. Incluir: (1) como se detecta, (2) a quien se notifica, (3) plazo, (4) escalado.'],
        ['activation','Activacion','Quién tiene autoridad para activar, criterios formales, lista de verificacion pre-activacion.'],
        ['recovery','Recuperacion tecnica','Secuencia de recuperacion de sistemas, pasos por sistema, validaciones de integridad, ubicacion de backups.'],
        ['reconstitution','Reconstitucion','Criterios para declarar recuperacion completa, pruebas de validacion, comunicacion de reanudacion, revision post-incidente.'],
      ].map(([secId, title, hint]) => `
      <div style="margin-bottom:14px;">${lbl(title)}
        <div style="font-size:10px;color:var(--text-subtle);margin-bottom:4px;">${hint}</div>
        <textarea id="pl-sec-${secId}" class="form-control" rows="3" style="font-size:13px;">${UI.esc(getSec(secId))}</textarea>
      </div>`).join('')}
    </div>

    <!-- SECCION 5: Roles y responsabilidades -->
    <div class="form-section-divider"><span>ROLES Y RESPONSABILIDADES</span></div>
    <div class="inline-table-wrap" style="margin-bottom:8px;">
      <table class="inline-table">
        <thead><tr><th>Rol / Equipo</th><th>Responsable (nombre)</th><th>Acciones notificacion</th><th>Acciones recuperacion</th><th style="width:30px"></th></tr></thead>
        <tbody id="pl-roles-tbody">
          ${roles.map((r,i)=>`<tr>
            <td><input value="${UI.esc(r.role_name||'')}" oninput="ViewBcp._updateRole(${i},'role_name',this.value)"></td>
            <td><input value="${UI.esc(r.responsible||'')}" oninput="ViewBcp._updateRole(${i},'responsible',this.value)"></td>
            <td><textarea rows="1" style="resize:none;" oninput="ViewBcp._updateRole(${i},'actions_notification',this.value)">${UI.esc(r.actions_notification||'')}</textarea></td>
            <td><textarea rows="1" style="resize:none;" oninput="ViewBcp._updateRole(${i},'actions_recovery',this.value)">${UI.esc(r.actions_recovery||'')}</textarea></td>
            <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeRole(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
    <div style="display:flex;gap:6px;margin-bottom:14px;">
      <button class="btn btn-ghost btn-sm" onclick="ViewBcp._addRole()" style="font-size:12px;"><i class="ti ti-plus"></i> Anadir rol</button>
      <button class="btn btn-ghost btn-sm" onclick="ViewBcp._loadDRPRoles()" style="font-size:12px;"><i class="ti ti-template"></i> Plantilla DRP</button>
    </div>

    <!-- SECCION 6: Contactos y escalada -->
    <div class="form-section-divider"><span>LISTA DE CONTACTOS Y ESCALADA</span></div>
    <div style="font-size:11px;color:var(--text-subtle);margin-bottom:8px;">Incluir todos los contactos necesarios durante una activacion: equipo interno, proveedores criticos y contactos de emergencia.</div>
    <div class="inline-table-wrap" style="margin-bottom:8px;">
      <table class="inline-table">
        <thead><tr><th>Nombre</th><th>Rol / Equipo</th><th>Telefono</th><th>Email</th><th>Backup</th><th>Tlf backup</th><th style="width:30px"></th></tr></thead>
        <tbody id="pl-contacts-tbody">
          ${contacts.map((c,i)=>`<tr>
            <td><input value="${UI.esc(c.name||'')}" oninput="ViewBcp._updateContact(${i},'name',this.value)"></td>
            <td><input value="${UI.esc(c.role||'')}" oninput="ViewBcp._updateContact(${i},'role',this.value)"></td>
            <td><input value="${UI.esc(c.phone||'')}" oninput="ViewBcp._updateContact(${i},'phone',this.value)"></td>
            <td><input value="${UI.esc(c.email||'')}" oninput="ViewBcp._updateContact(${i},'email',this.value)"></td>
            <td><input value="${UI.esc(c.backup_name||'')}" oninput="ViewBcp._updateContact(${i},'backup_name',this.value)"></td>
            <td><input value="${UI.esc(c.backup_phone||'')}" oninput="ViewBcp._updateContact(${i},'backup_phone',this.value)"></td>
            <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeContact(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
    <button class="btn btn-ghost btn-sm" onclick="ViewBcp._addContact()" style="margin-bottom:14px;font-size:12px;"><i class="ti ti-plus"></i> Anadir contacto</button>

    <!-- SECCION 7: Contingencia IT y workarounds -->
    <div class="form-section-divider"><span>CONTINGENCIA IT Y WORKAROUNDS</span></div>
    <div style="margin-bottom:14px;">${lbl('Procedimientos de trabajo temporal')}
      <div style="font-size:10px;color:var(--text-subtle);margin-bottom:4px;">¿Como puede el negocio seguir operando sin los sistemas afectados?</div>
      <textarea id="pl-workaround" class="form-control" rows="3" style="font-size:13px;">${UI.esc(plan?.sections?.find?.(s=>s.id==='workaround')?.content||'')}</textarea>
    </div>
    <div style="margin-bottom:14px;">${lbl('Recuperacion de datos')}
      <div style="font-size:10px;color:var(--text-subtle);margin-bottom:4px;">Ubicacion de backups, acceso, validacion de integridad.</div>
      <textarea id="pl-backup" class="form-control" rows="2" style="font-size:13px;">${UI.esc(plan?.sections?.find?.(s=>s.id==='backup')?.content||'')}</textarea>
    </div>

    <!-- SECCION 8: KPIs -->
    <div class="form-section-divider"><span>KPIs Y METRICAS</span></div>
    <div class="inline-table-wrap" style="margin-bottom:8px;">
      <table class="inline-table">
        <thead><tr><th>Metrica</th><th>Objetivo</th><th>Como medir</th><th style="width:30px"></th></tr></thead>
        <tbody id="pl-kpis-tbody">
          ${kpis.map((k,i)=>`<tr>
            <td><input value="${UI.esc(k.metric||'')}" oninput="ViewBcp._updateKPI(${i},'metric',this.value)"></td>
            <td><input value="${UI.esc(k.target||'')}" style="width:80px;" oninput="ViewBcp._updateKPI(${i},'target',this.value)"></td>
            <td><input value="${UI.esc(k.measure||'')}" oninput="ViewBcp._updateKPI(${i},'measure',this.value)"></td>
            <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeKPI(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
    <div style="display:flex;gap:6px;margin-bottom:14px;">
      <button class="btn btn-ghost btn-sm" onclick="ViewBcp._addKPI()" style="font-size:12px;"><i class="ti ti-plus"></i> Anadir KPI</button>
      <button class="btn btn-ghost btn-sm" onclick="ViewBcp._loadStandardKPIs()" style="font-size:12px;"><i class="ti ti-template"></i> KPIs estandar DRP</button>
    </div>

    <!-- SECCION DR SITE (solo DRP/CRP/cyber_response) -->
    <div id="pl-drsite-section" ${showForTypes(['drp','crp','cyber_response'], currType)}>
      <div class="form-section-divider"><span>SITIO ALTERNATIVO — DR SITE</span></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
        <div>${lbl('Tipo de DR Site')}
          <select id="pl-drsite-type" class="form-control" style="font-size:13px;">
            <option value="">— Sin DR Site —</option>
            ${[['hot','Hot site — Failover automatico (<15 min)'],['warm','Warm site — Failover semi-auto (1-4h)'],
               ['cold','Cold site — Restauracion manual (>4h)'],['cloud','Cloud DR — Instancias on-demand']]
              .map(([v,l])=>`<option value="${v}"${plan?.dr_site?.site_type===v?' selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div>${lbl('Ubicacion DR Site')}
          <input id="pl-drsite-loc" class="form-control" style="font-size:13px;"
            value="${UI.esc(plan?.dr_site?.location||'')}" placeholder="Ciudad · Distancia a sede principal">
        </div>
        <div>${lbl('Acceso (IP / VPN / ref. boveda)')}
          <input id="pl-drsite-access" class="form-control" style="font-size:13px;"
            value="${UI.esc(plan?.dr_site?.access_info||'')}" placeholder="IP gestion · ref. boveda credenciales">
        </div>
        <div>${lbl('RTO de activacion del DR Site (horas)')}
          <input id="pl-drsite-rto" class="form-control" type="number" min="0" style="font-size:13px;"
            value="${plan?.dr_site?.rto_hours??''}" placeholder="Tiempo hasta que el DR site esta operativo">
        </div>
        <div>${lbl('Capacidad instalada')}
          <input id="pl-drsite-cap" class="form-control" style="font-size:13px;"
            value="${UI.esc(plan?.dr_site?.capacity||'')}" placeholder="Servidores, almacenamiento, RAM total">
        </div>
        <div>${lbl('Conectividad')}
          <input id="pl-drsite-conn" class="form-control" style="font-size:13px;"
            value="${UI.esc(plan?.dr_site?.connectivity||'')}" placeholder="ISP · ancho de banda · latencia">
        </div>
      </div>
      <div style="margin-bottom:14px;">${lbl('Infraestructura disponible (notas)')}
        <textarea id="pl-drsite-notes" class="form-control" rows="3" style="font-size:13px;"
          placeholder="Servidores, VMs, networking, sistemas preinstalados...">${UI.esc(plan?.dr_site?.infrastructure_notes||'')}</textarea>
      </div>
    </div>

    <!-- SECCION POLITICA DE BACKUPS (solo DRP/CRP) -->
    <div id="pl-backup-section" ${showForTypes(['drp','crp'], currType)}>
      <div class="form-section-divider"><span>POLITICA DE BACKUPS</span></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
        <div>${lbl('Regla 3-2-1 aplicada')}
          <select id="pl-bkp-321" class="form-control" style="font-size:13px;">
            <option value="si"${plan?.backup_policy?.rule_321==='si'?' selected':''}>Si — 3 copias, 2 soportes, 1 offsite</option>
            <option value="parcial"${plan?.backup_policy?.rule_321==='parcial'?' selected':''}>Parcial</option>
            <option value="no"${plan?.backup_policy?.rule_321==='no'?' selected':''}>No — requiere accion</option>
          </select>
        </div>
        <div>${lbl('Cifrado de backups')}
          <select id="pl-bkp-enc" class="form-control" style="font-size:13px;">
            <option value="aes256"${plan?.backup_policy?.encryption==='aes256'?' selected':''}>AES-256 en transito y reposo</option>
            <option value="reposo"${plan?.backup_policy?.encryption==='reposo'?' selected':''}>Solo en reposo</option>
            <option value="no"${plan?.backup_policy?.encryption==='no'?' selected':''}>No cifrado — requiere accion</option>
          </select>
        </div>
        <div>${lbl('Retencion minima')}
          <input id="pl-bkp-ret" class="form-control" style="font-size:13px;"
            value="${UI.esc(plan?.backup_policy?.retention||'')}" placeholder="Ej: 30 dias diario + 12 meses mensual">
        </div>
        <div>${lbl('Almacenamiento offsite')}
          <input id="pl-bkp-offsite" class="form-control" style="font-size:13px;"
            value="${UI.esc(plan?.backup_policy?.offsite_location||'')}" placeholder="Proveedor cloud · region · distancia">
        </div>
      </div>
      <div style="font-size:11px;color:var(--text-subtle);margin-bottom:8px;">Un backup sin prueba de restauracion documentada no es valido para auditoria.</div>
      <div class="inline-table-wrap" style="margin-bottom:8px;">
        <table class="inline-table">
          <thead><tr>
            <th>Sistema</th><th>Tipo</th><th>Frecuencia</th><th>Retencion</th>
            <th>RPO cubierto</th><th>Ubicacion</th><th>Ultimo test</th><th>Resultado</th>
            <th style="width:30px"></th>
          </tr></thead>
          <tbody id="pl-backup-tbody">
            ${(plan?.backup_policy?.items||[]).map((b,i)=>`<tr>
              <td><input value="${UI.esc(b.system||'')}" oninput="ViewBcp._updateBkpItem(${i},'system',this.value)"></td>
              <td><select oninput="ViewBcp._updateBkpItem(${i},'backup_type',this.value)" style="font-size:11px;">
                ${['Completo diario','Incremental','Diferencial','Replicacion sincrona'].map(t=>
                  `<option${b.backup_type===t?' selected':''}>${t}</option>`).join('')}
              </select></td>
              <td><input value="${UI.esc(b.frequency||'')}" style="width:70px;" oninput="ViewBcp._updateBkpItem(${i},'frequency',this.value)"></td>
              <td><input value="${UI.esc(b.retention||'')}" style="width:60px;" oninput="ViewBcp._updateBkpItem(${i},'retention',this.value)"></td>
              <td><input value="${UI.esc(b.rpo_covered||'')}" style="width:55px;" oninput="ViewBcp._updateBkpItem(${i},'rpo_covered',this.value)"></td>
              <td><input value="${UI.esc(b.location||'')}" oninput="ViewBcp._updateBkpItem(${i},'location',this.value)"></td>
              <td><input type="date" value="${b.last_test_date||''}" oninput="ViewBcp._updateBkpItem(${i},'last_test_date',this.value)"></td>
              <td><select oninput="ViewBcp._updateBkpItem(${i},'last_test_result',this.value)" style="font-size:11px;">
                ${['OK','Parcial','Fallido','Pendiente'].map(r=>
                  `<option${b.last_test_result===r?' selected':''}>${r}</option>`).join('')}
              </select></td>
              <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeBkpItem(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
            </tr>`).join('')}
          </tbody>
        </table>
      </div>
      <button class="btn btn-ghost btn-sm" onclick="ViewBcp._addBkpItem()" style="margin-bottom:14px;font-size:12px;">
        <i class="ti ti-plus"></i> Anadir sistema
      </button>
    </div>

    <!-- SECCION: Comunicacion en crisis -->
    <div id="pl-comms-section">
      <div class="form-section-divider"><span>COMUNICACION EN CRISIS — ISO 22301 §8.4.4</span></div>
      <div style="font-size:12px;color:var(--text-subtle);margin-bottom:12px;">Canales y plantillas de comunicacion para partes interesadas durante una interrupcion. ENS [op.cont.2].</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px;">
        <div>
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px;">Canal primario</label>
          <input id="pl-cc-primary" class="form-control" style="font-size:13px;"
            value="${UI.esc(plan?.crisis_comms?.primary_channel||'')}" placeholder="Teams / Slack / Signal">
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px;">Canal secundario (si TI caido)</label>
          <input id="pl-cc-secondary" class="form-control" style="font-size:13px;"
            value="${UI.esc(plan?.crisis_comms?.secondary_channel||'')}" placeholder="WhatsApp / SMS / Telefono">
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px;">Canal externo</label>
          <input id="pl-cc-external" class="form-control" style="font-size:13px;"
            value="${UI.esc(plan?.crisis_comms?.external_channel||'')}" placeholder="Email institucional / Portal">
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
        <div>
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px;">Plantilla comunicado interno</label>
          <textarea id="pl-cc-tpl-int" class="form-control" rows="5" style="font-size:12px;font-family:monospace;"
            placeholder="[INCIDENTE] Impacto en [SERVICIO] detectado el [FECHA]...">${UI.esc(plan?.crisis_comms?.template_internal||'')}</textarea>
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px;">Plantilla comunicado externo</label>
          <textarea id="pl-cc-tpl-ext" class="form-control" rows="5" style="font-size:12px;font-family:monospace;"
            placeholder="Estimados usuarios, se ha detectado un incidente que afecta a [SERVICIO]...">${UI.esc(plan?.crisis_comms?.template_external||'')}</textarea>
        </div>
      </div>
    </div>

    <!-- SECCION 10: Clasificacion y gestion -->
    <div class="form-section-divider"><span>CLASIFICACION Y GESTION</span></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
      <div>${lbl('Tipo de instalacion')}
        <select id="pl-inst-type" class="form-control" style="font-size:13px;">
          <option value="">— Sin clasificar —</option>
          ${[['cloud_saas','Cloud SaaS'],['cloud_iaas','Cloud IaaS'],['on_prem','On-premise'],['hybrid','Hibrido'],['enduser_device','Dispositivo usuario final']]
            .map(([v,l])=>`<option value="${v}"${plan?.installation_type===v?' selected':''}>${l}</option>`).join('')}
        </select>
      </div>
      <div>${lbl('Clasificacion del dato')}
        <select id="pl-data-class" class="form-control" style="font-size:13px;">
          <option value="">— Sin clasificar —</option>
          ${[['public','Publico'],['internal','Interno'],['confidential','Confidencial'],['strictly_confidential','Estrictamente confidencial']]
            .map(([v,l])=>`<option value="${v}"${plan?.data_classification_level===v?' selected':''}>${l}</option>`).join('')}
        </select>
      </div>
      <div>${lbl('Usuarios afectados (estimado)')}
        <input id="pl-users-count" class="form-control" type="number" min="0" style="font-size:13px;" value="${plan?.affected_users_count??''}">
      </div>
      <div style="display:flex;align-items:center;gap:8px;padding-top:20px;">
        <input id="pl-gdpr" type="checkbox" ${plan?.gdpr_data?'checked':''}>
        <label for="pl-gdpr" style="margin:0;font-size:13px;">Datos GDPR / RGPD implicados</label>
      </div>
    </div>

    <!-- Autorizadores -->
    <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px;letter-spacing:.03em;">Autorizadores de activacion</div>
    <div class="inline-table-wrap" style="margin-bottom:8px;">
      <table class="inline-table">
        <thead><tr><th>Nombre</th><th>Rol</th><th>Email</th><th>Telefono</th><th>Suplente</th><th style="width:30px"></th></tr></thead>
        <tbody id="pl-auth-tbody">
          ${(plan?.authorized_activators||[]).map((a,i)=>`<tr>
            <td><input value="${UI.esc(a.name||'')}" oninput="ViewBcp._updateAuthActivator(${i},'name',this.value)"></td>
            <td><input value="${UI.esc(a.role||'')}" oninput="ViewBcp._updateAuthActivator(${i},'role',this.value)"></td>
            <td><input value="${UI.esc(a.email||'')}" oninput="ViewBcp._updateAuthActivator(${i},'email',this.value)"></td>
            <td><input value="${UI.esc(a.phone||'')}" oninput="ViewBcp._updateAuthActivator(${i},'phone',this.value)"></td>
            <td style="text-align:center"><input type="checkbox" ${a.is_deputy?'checked':''} onchange="ViewBcp._updateAuthActivator(${i},'is_deputy',this.checked)"></td>
            <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeAuthActivator(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
    <button class="btn btn-ghost btn-sm" onclick="ViewBcp._addAuthActivator()" style="margin-bottom:14px;font-size:12px;">
      <i class="ti ti-plus"></i> Anadir autorizador
    </button>

    <!-- Documentacion vinculada -->
    <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px;letter-spacing:.03em;">Documentacion vinculada (enlaces externos)</div>
    <div class="inline-table-wrap" style="margin-bottom:8px;">
      <table class="inline-table">
        <thead><tr><th>Titulo</th><th>URL / Referencia</th><th style="width:30px"></th></tr></thead>
        <tbody id="pl-doclinks-tbody">
          ${(plan?.documentation_links||[]).map((d,i)=>`<tr>
            <td><input value="${UI.esc(d.title||'')}" oninput="ViewBcp._updateDocLink(${i},'title',this.value)"></td>
            <td><input value="${UI.esc(d.url||'')}" oninput="ViewBcp._updateDocLink(${i},'url',this.value)" placeholder="https://..."></td>
            <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeDocLink(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
    <button class="btn btn-ghost btn-sm" onclick="ViewBcp._addDocLink()" style="margin-bottom:14px;font-size:12px;">
      <i class="ti ti-plus"></i> Anadir enlace
    </button>

    <!-- Documentos relacionados -->
    <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px;letter-spacing:.03em;">Documentos relacionados (internos)</div>
    <div class="inline-table-wrap" style="margin-bottom:8px;">
      <table class="inline-table">
        <thead><tr><th>Titulo</th><th>Version</th><th>Vigente desde</th><th style="width:30px"></th></tr></thead>
        <tbody id="pl-reldocs-tbody">
          ${(plan?.related_documents||[]).map((d,i)=>`<tr>
            <td><input value="${UI.esc(d.title||'')}" oninput="ViewBcp._updateRelDoc(${i},'title',this.value)"></td>
            <td><input value="${UI.esc(d.doc_version||'')}" style="width:70px;" oninput="ViewBcp._updateRelDoc(${i},'doc_version',this.value)" placeholder="v1.0"></td>
            <td><input type="date" value="${d.valid_from||''}" oninput="ViewBcp._updateRelDoc(${i},'valid_from',this.value)"></td>
            <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeRelDoc(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>
    <button class="btn btn-ghost btn-sm" onclick="ViewBcp._addRelDoc()" style="margin-bottom:14px;font-size:12px;">
      <i class="ti ti-plus"></i> Anadir documento
    </button>

    <!-- SECCION 9: Historial -->
    ${plan ? `<div class="form-section-divider"><span>HISTORIAL Y MANTENIMIENTO</span></div>
    <div style="font-size:12px;color:var(--text-subtle);display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px;">
      <div>Estado: <strong>${UI.esc(plan.status)}</strong></div>
      <div>Ultima prueba: <strong>${plan.last_exercised_at ? new Date(plan.last_exercised_at).toLocaleDateString('es-ES') : '—'}</strong></div>
      ${plan.approved_by_id ? `<div>Aprobado por: <strong>#${plan.approved_by_id}</strong></div>` : ''}
      ${plan.approved_at ? `<div>Aprobado: <strong>${new Date(plan.approved_at).toLocaleDateString('es-ES')}</strong></div>` : ''}
    </div>` : ''}`;

    // Datos en memoria para las tablas inline
    window._planSysDeps  = [...sysDeps];
    window._planRoles    = [...roles];
    window._planContacts = [...contacts];
    window._planKpis     = [...kpis];
    window._planBkpItems = [...(plan?.backup_policy?.items || [])];
    window._planAuthActivators = [...(plan?.authorized_activators || [])];
    window._planDocLinks       = [...(plan?.documentation_links   || [])];
    window._planRelDocs        = [...(plan?.related_documents     || [])];

    // Guardar save handler actualizado con el ID
    document.getElementById('plan-drawer-save').onclick = () => _savePlan(_currentPlanId);

    _openDrawer('plan-drawer');
  }

  function _onPlanTypeChange(type) {
    const sysSec   = document.getElementById('pl-sys-section');
    const procSec  = document.getElementById('pl-proc-section');
    const drsiteSec= document.getElementById('pl-drsite-section');
    const bkpSec   = document.getElementById('pl-backup-section');
    const commsSec = document.getElementById('pl-comms-section');
    if (sysSec)    sysSec.style.display    = ['drp','crp'].includes(type) ? '' : 'none';
    if (procSec)   procSec.style.display   = ['drp','crp','cyber_response'].includes(type) ? '' : 'none';
    if (drsiteSec) drsiteSec.style.display = ['drp','crp','cyber_response'].includes(type) ? '' : 'none';
    if (bkpSec)    bkpSec.style.display    = ['drp','crp'].includes(type) ? '' : 'none';
    if (commsSec)  commsSec.style.display  = ['bcp','drp','crp','ems','pandemic','cyber_response'].includes(type) ? '' : 'none';
  }

  // Helpers tablas inline backup
  function _rerenderBkpItems() {
    const tbody = document.getElementById('pl-backup-tbody');
    if (!tbody) return;
    const BKP_TYPES = ['Completo diario','Incremental','Diferencial','Replicacion sincrona'];
    const RESULTS   = ['OK','Parcial','Fallido','Pendiente'];
    tbody.innerHTML = (window._planBkpItems || []).map((b,i) => `<tr>
      <td><input value="${UI.esc(b.system||'')}" oninput="ViewBcp._updateBkpItem(${i},'system',this.value)"></td>
      <td><select oninput="ViewBcp._updateBkpItem(${i},'backup_type',this.value)" style="font-size:11px;">
        ${BKP_TYPES.map(t=>`<option${b.backup_type===t?' selected':''}>${t}</option>`).join('')}
      </select></td>
      <td><input value="${UI.esc(b.frequency||'')}" style="width:70px;" oninput="ViewBcp._updateBkpItem(${i},'frequency',this.value)"></td>
      <td><input value="${UI.esc(b.retention||'')}" style="width:60px;" oninput="ViewBcp._updateBkpItem(${i},'retention',this.value)"></td>
      <td><input value="${UI.esc(b.rpo_covered||'')}" style="width:55px;" oninput="ViewBcp._updateBkpItem(${i},'rpo_covered',this.value)"></td>
      <td><input value="${UI.esc(b.location||'')}" oninput="ViewBcp._updateBkpItem(${i},'location',this.value)"></td>
      <td><input type="date" value="${b.last_test_date||''}" oninput="ViewBcp._updateBkpItem(${i},'last_test_date',this.value)"></td>
      <td><select oninput="ViewBcp._updateBkpItem(${i},'last_test_result',this.value)" style="font-size:11px;">
        ${RESULTS.map(r=>`<option${b.last_test_result===r?' selected':''}>${r}</option>`).join('')}
      </select></td>
      <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeBkpItem(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
    </tr>`).join('');
  }
  function _addBkpItem() {
    (window._planBkpItems = window._planBkpItems || []).push(
      {system:'',backup_type:'Completo diario',frequency:'',retention:'',rpo_covered:'',location:'',last_test_date:'',last_test_result:'Pendiente'}
    );
    _rerenderBkpItems();
  }
  function _removeBkpItem(i) { (window._planBkpItems||[]).splice(i,1); _rerenderBkpItems(); }
  function _updateBkpItem(i, field, val) { if (window._planBkpItems?.[i]) window._planBkpItems[i][field] = val; }

  // ── Auth activators ──────────────────────────────────────────────────────────
  function _rerenderAuthActivators() {
    const tbody = document.getElementById('pl-auth-tbody');
    if (!tbody) return;
    tbody.innerHTML = (window._planAuthActivators || []).map((a,i) => `<tr>
      <td><input value="${UI.esc(a.name||'')}" oninput="ViewBcp._updateAuthActivator(${i},'name',this.value)"></td>
      <td><input value="${UI.esc(a.role||'')}" oninput="ViewBcp._updateAuthActivator(${i},'role',this.value)"></td>
      <td><input value="${UI.esc(a.email||'')}" oninput="ViewBcp._updateAuthActivator(${i},'email',this.value)"></td>
      <td><input value="${UI.esc(a.phone||'')}" oninput="ViewBcp._updateAuthActivator(${i},'phone',this.value)"></td>
      <td style="text-align:center"><input type="checkbox" ${a.is_deputy?'checked':''} onchange="ViewBcp._updateAuthActivator(${i},'is_deputy',this.checked)"></td>
      <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeAuthActivator(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
    </tr>`).join('');
  }
  function _addAuthActivator() { (window._planAuthActivators = window._planAuthActivators || []).push({name:'',role:'',email:'',phone:'',is_deputy:false}); _rerenderAuthActivators(); }
  function _removeAuthActivator(i) { (window._planAuthActivators||[]).splice(i,1); _rerenderAuthActivators(); }
  function _updateAuthActivator(i, field, val) { if (window._planAuthActivators?.[i]) window._planAuthActivators[i][field] = val; }

  // ── Documentation links ──────────────────────────────────────────────────────
  function _rerenderDocLinks() {
    const tbody = document.getElementById('pl-doclinks-tbody');
    if (!tbody) return;
    tbody.innerHTML = (window._planDocLinks || []).map((d,i) => `<tr>
      <td><input value="${UI.esc(d.title||'')}" oninput="ViewBcp._updateDocLink(${i},'title',this.value)"></td>
      <td><input value="${UI.esc(d.url||'')}" oninput="ViewBcp._updateDocLink(${i},'url',this.value)" placeholder="https://..."></td>
      <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeDocLink(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
    </tr>`).join('');
  }
  function _addDocLink() { (window._planDocLinks = window._planDocLinks || []).push({title:'',url:''}); _rerenderDocLinks(); }
  function _removeDocLink(i) { (window._planDocLinks||[]).splice(i,1); _rerenderDocLinks(); }
  function _updateDocLink(i, field, val) { if (window._planDocLinks?.[i]) window._planDocLinks[i][field] = val; }

  // ── Related documents ────────────────────────────────────────────────────────
  function _rerenderRelDocs() {
    const tbody = document.getElementById('pl-reldocs-tbody');
    if (!tbody) return;
    tbody.innerHTML = (window._planRelDocs || []).map((d,i) => `<tr>
      <td><input value="${UI.esc(d.title||'')}" oninput="ViewBcp._updateRelDoc(${i},'title',this.value)"></td>
      <td><input value="${UI.esc(d.doc_version||'')}" style="width:70px;" oninput="ViewBcp._updateRelDoc(${i},'doc_version',this.value)" placeholder="v1.0"></td>
      <td><input type="date" value="${d.valid_from||''}" oninput="ViewBcp._updateRelDoc(${i},'valid_from',this.value)"></td>
      <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeRelDoc(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
    </tr>`).join('');
  }
  function _addRelDoc() { (window._planRelDocs = window._planRelDocs || []).push({title:'',doc_version:'',valid_from:''}); _rerenderRelDocs(); }
  function _removeRelDoc(i) { (window._planRelDocs||[]).splice(i,1); _rerenderRelDocs(); }
  function _updateRelDoc(i, field, val) { if (window._planRelDocs?.[i]) window._planRelDocs[i][field] = val; }

  // Helpers para tablas inline del drawer de planes
  function _rerenderSysDeps() {
    const tbody = document.getElementById('pl-sys-tbody');
    if (!tbody) return;
    tbody.innerHTML = (window._planSysDeps || []).map((s,i) => `<tr>
      <td><input value="${UI.esc(s.system_name||'')}" oninput="ViewBcp._updateSysDep(${i},'system_name',this.value)"></td>
      <td><input type="number" value="${s.rto_hours??''}" style="width:60px;" oninput="ViewBcp._updateSysDep(${i},'rto_hours',this.value)"></td>
      <td><input type="number" value="${s.rpo_hours??''}" style="width:60px;" oninput="ViewBcp._updateSysDep(${i},'rpo_hours',this.value)"></td>
      <td><input value="${UI.esc(s.responsible||'')}" oninput="ViewBcp._updateSysDep(${i},'responsible',this.value)"></td>
      <td><input value="${UI.esc(s.notes||'')}" oninput="ViewBcp._updateSysDep(${i},'notes',this.value)"></td>
      <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeSysDep(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
    </tr>`).join('');
  }
  function _addSysDep() { (window._planSysDeps = window._planSysDeps || []).push({system_name:'',rto_hours:null,rpo_hours:null,responsible:'',notes:''}); _rerenderSysDeps(); }
  function _removeSysDep(i) { (window._planSysDeps||[]).splice(i,1); _rerenderSysDeps(); }
  function _updateSysDep(i, field, val) { if (window._planSysDeps?.[i]) window._planSysDeps[i][field] = field.includes('hours') ? (parseInt(val)||null) : val; }

  function _rerenderRoles() {
    const tbody = document.getElementById('pl-roles-tbody');
    if (!tbody) return;
    tbody.innerHTML = (window._planRoles || []).map((r,i) => `<tr>
      <td><input value="${UI.esc(r.role_name||'')}" oninput="ViewBcp._updateRole(${i},'role_name',this.value)"></td>
      <td><input value="${UI.esc(r.responsible||'')}" oninput="ViewBcp._updateRole(${i},'responsible',this.value)"></td>
      <td><textarea rows="1" style="resize:none;" oninput="ViewBcp._updateRole(${i},'actions_notification',this.value)">${UI.esc(r.actions_notification||'')}</textarea></td>
      <td><textarea rows="1" style="resize:none;" oninput="ViewBcp._updateRole(${i},'actions_recovery',this.value)">${UI.esc(r.actions_recovery||'')}</textarea></td>
      <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeRole(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
    </tr>`).join('');
  }
  function _addRole() { (window._planRoles = window._planRoles || []).push({role_name:'',responsible:'',actions_notification:'',actions_recovery:''}); _rerenderRoles(); }
  function _removeRole(i) { (window._planRoles||[]).splice(i,1); _rerenderRoles(); }
  function _updateRole(i, field, val) { if (window._planRoles?.[i]) window._planRoles[i][field] = val; }
  function _loadDRPRoles() {
    window._planRoles = [
      {role_name:'Global IT Security Team',responsible:'',actions_notification:'Verificar deteccion y activar protocolo',actions_recovery:'Coordinar recuperacion tecnica'},
      {role_name:'Hosting/Infrastructure Team',responsible:'',actions_notification:'Evaluar impacto en sistemas',actions_recovery:'Recuperar sistemas segun secuencia'},
      {role_name:'Asset Owner',responsible:'',actions_notification:'Notificar a equipos IT',actions_recovery:'Validar integridad de datos'},
      {role_name:'Business Unit Manager',responsible:'',actions_notification:'Comunicar a stakeholders',actions_recovery:'Activar procedimientos manuales'},
      {role_name:'Senior Leadership / Sponsor',responsible:'',actions_notification:'Tomar decision de activacion',actions_recovery:'Aprobar vuelta a operacion normal'},
    ];
    _rerenderRoles();
  }

  function _rerenderContacts() {
    const tbody = document.getElementById('pl-contacts-tbody');
    if (!tbody) return;
    tbody.innerHTML = (window._planContacts || []).map((c,i) => `<tr>
      <td><input value="${UI.esc(c.name||'')}" oninput="ViewBcp._updateContact(${i},'name',this.value)"></td>
      <td><input value="${UI.esc(c.role||'')}" oninput="ViewBcp._updateContact(${i},'role',this.value)"></td>
      <td><input value="${UI.esc(c.phone||'')}" oninput="ViewBcp._updateContact(${i},'phone',this.value)"></td>
      <td><input value="${UI.esc(c.email||'')}" oninput="ViewBcp._updateContact(${i},'email',this.value)"></td>
      <td><input value="${UI.esc(c.backup_name||'')}" oninput="ViewBcp._updateContact(${i},'backup_name',this.value)"></td>
      <td><input value="${UI.esc(c.backup_phone||'')}" oninput="ViewBcp._updateContact(${i},'backup_phone',this.value)"></td>
      <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeContact(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
    </tr>`).join('');
  }
  function _addContact() { (window._planContacts = window._planContacts || []).push({name:'',role:'',phone:'',email:'',backup_name:'',backup_phone:''}); _rerenderContacts(); }
  function _removeContact(i) { (window._planContacts||[]).splice(i,1); _rerenderContacts(); }
  function _updateContact(i, field, val) { if (window._planContacts?.[i]) window._planContacts[i][field] = val; }

  function _rerenderKPIs() {
    const tbody = document.getElementById('pl-kpis-tbody');
    if (!tbody) return;
    tbody.innerHTML = (window._planKpis || []).map((k,i) => `<tr>
      <td><input value="${UI.esc(k.metric||'')}" oninput="ViewBcp._updateKPI(${i},'metric',this.value)"></td>
      <td><input value="${UI.esc(k.target||'')}" style="width:80px;" oninput="ViewBcp._updateKPI(${i},'target',this.value)"></td>
      <td><input value="${UI.esc(k.measure||'')}" oninput="ViewBcp._updateKPI(${i},'measure',this.value)"></td>
      <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._removeKPI(${i})" style="padding:2px 6px;"><i class="ti ti-trash" style="font-size:12px;"></i></button></td>
    </tr>`).join('');
  }
  function _addKPI() { (window._planKpis = window._planKpis || []).push({metric:'',target:'',measure:''}); _rerenderKPIs(); }
  function _removeKPI(i) { (window._planKpis||[]).splice(i,1); _rerenderKPIs(); }
  function _updateKPI(i, field, val) { if (window._planKpis?.[i]) window._planKpis[i][field] = val; }
  function _loadStandardKPIs() {
    window._planKpis = [
      {metric:'RTO objetivo sistemas criticos cumplido',target:'Si',measure:'% ejercicios donde RTO fue respetado'},
      {metric:'RPO objetivo sistemas criticos cumplido',target:'Si',measure:'% datos recuperados dentro del RPO'},
      {metric:'Tests anuales completados con resultado "passed"',target:'>= 90%',measure:'n tests passed / n tests planificados'},
      {metric:'Tiempo real recuperacion vs RTO objetivo',target:'<= 1x RTO',measure:'Tiempo de recuperacion real en ultimo test'},
      {metric:'Escaladas ejecutadas en tiempo',target:'100%',measure:'% contactos notificados en el plazo definido'},
    ];
    _rerenderKPIs();
  }

  function _openDrawer(id) {
    document.getElementById('drawer-overlay-' + id)?.classList.add('open');
    document.getElementById(id)?.classList.add('open');
    // El plan drawer usa su propio overlay con id plan-drawer-overlay
    document.getElementById('plan-drawer-overlay')?.classList.add('open');
    document.getElementById('plan-drawer')?.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
  function _closePlanDrawer() {
    document.getElementById('plan-drawer-overlay')?.classList.remove('open');
    document.getElementById('plan-drawer')?.classList.remove('open');
    document.body.style.overflow = '';
  }

  async function _editPlan(id) {
    let plan = _plans.find(p => p.id === id);
    if (!plan) plan = await Api.get(`/api/bcp/plans/${id}`).catch(() => null);
    if (!plan) { UI.toast('Plan no encontrado', 'error'); return; }
    if (plan.status === 'approved') {
      _openApprovedVersioningModal(plan);
    } else {
      _openPlanDrawer(plan);
    }
  }

  function _bumpVersion(ver) {
    const parts = String(ver || '1.0').split('.');
    return (parseInt(parts[0] || '1') + 1) + '.0';
  }

  function _openApprovedVersioningModal(plan) {
    const nextVer = _bumpVersion(plan.version);
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:460px;">
      <div class="modal-header">
        <h2><i class="ti ti-git-branch"></i> Editar plan aprobado</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body">
        <p style="margin-bottom:10px;">El plan <strong>${UI.esc(plan.code)}</strong> esta actualmente <strong>aprobado</strong> (v${UI.esc(plan.version||'1.0')}).</p>
        <p style="font-size:13px;color:var(--text-subtle);margin-bottom:12px;">Al continuar se creara una nueva version <strong>v${UI.esc(nextVer)}</strong> en borrador con los mismos datos. El plan actual permanecera vigente hasta que la nueva version sea aprobada, momento en que pasara automaticamente a estado <em>obsoleto</em>.</p>
        <div style="display:flex;gap:8px;justify-content:flex-end;padding-top:8px;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-primary btn-sm" id="btn-confirm-version">
            <i class="ti ti-copy"></i> Crear version ${UI.esc(nextVer)}
          </button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#btn-confirm-version').addEventListener('click', async () => {
      modal.remove();
      try {
        UI.toast('Creando nueva version...', 'info');
        const newPlan = await Api.post(`/api/bcp/plans/${plan.id}/new-version`, {});
        UI.toast(`Version ${newPlan.version} creada en borrador`, 'success');
        _plans = await Api.get('/api/bcp/plans').catch(() => _plans);
        _openPlanDrawer(newPlan);
      } catch (e) {
        UI.toast('Error: ' + e.message, 'error');
      }
    });
  }

  async function _savePlan(id) {
    const g = eid => document.getElementById(eid);
    const pids = [...document.querySelectorAll('.pl-pids:checked')].map(c => parseInt(c.value));

    // Construir secciones
    const sections = [
      {id:'notification', title:'Notificacion', content: g('pl-sec-notification')?.value || ''},
      {id:'activation',   title:'Activacion',   content: g('pl-sec-activation')?.value || ''},
      {id:'recovery',     title:'Recuperacion',  content: g('pl-sec-recovery')?.value || ''},
      {id:'reconstitution',title:'Reconstitucion',content: g('pl-sec-reconstitution')?.value || ''},
      {id:'workaround',   title:'Work temporal', content: g('pl-workaround')?.value || ''},
      {id:'backup',       title:'Recuperacion datos', content: g('pl-backup')?.value || ''},
    ].filter(s => s.content);

    const body = {
      plan_type: g('pl-type')?.value || 'bcp',
      name: g('pl-name')?.value?.trim() || '',
      version: g('pl-ver')?.value || '1.0',
      classification: g('pl-class')?.value || null,
      plan_owner_name: g('pl-owner')?.value || null,
      scope: g('pl-scope')?.value || null,
      activation_criteria: g('pl-activ')?.value || null,
      content_summary: g('pl-sum')?.value || null,
      document_id: parseInt(g('pl-doc')?.value) || null,
      review_date: g('pl-rev')?.value || null,
      process_ids: pids,
      sections: sections.length ? sections : null,
      system_dependencies: (window._planSysDeps || []).length ? window._planSysDeps : null,
      roles_matrix: (window._planRoles || []).length ? window._planRoles : null,
      contact_list: (window._planContacts || []).length ? window._planContacts : null,
      kpis: (window._planKpis || []).length ? window._planKpis : null,
      // DR Site
      dr_site: g('pl-drsite-type')?.value ? {
        site_type:            g('pl-drsite-type')?.value || null,
        location:             g('pl-drsite-loc')?.value  || null,
        access_info:          g('pl-drsite-access')?.value || null,
        rto_hours:            parseInt(g('pl-drsite-rto')?.value) || null,
        capacity:             g('pl-drsite-cap')?.value  || null,
        connectivity:         g('pl-drsite-conn')?.value || null,
        infrastructure_notes: g('pl-drsite-notes')?.value || null,
      } : null,
      // Politica de backups
      backup_policy: g('pl-bkp-321')?.value ? {
        rule_321:         g('pl-bkp-321')?.value    || null,
        encryption:       g('pl-bkp-enc')?.value    || null,
        retention:        g('pl-bkp-ret')?.value    || null,
        offsite_location: g('pl-bkp-offsite')?.value || null,
        items:            (window._planBkpItems || []).length ? window._planBkpItems : [],
      } : null,
      // Comunicacion en crisis
      crisis_comms: (g('pl-cc-primary')?.value || g('pl-cc-secondary')?.value || g('pl-cc-external')?.value) ? {
        primary_channel:   g('pl-cc-primary')?.value   || null,
        secondary_channel: g('pl-cc-secondary')?.value || null,
        external_channel:  g('pl-cc-external')?.value  || null,
        template_internal: g('pl-cc-tpl-int')?.value   || null,
        template_external: g('pl-cc-tpl-ext')?.value   || null,
      } : null,
      // Clasificacion y gestion (Sprint 5)
      installation_type:         g('pl-inst-type')?.value  || null,
      data_classification_level: g('pl-data-class')?.value || null,
      gdpr_data:                 g('pl-gdpr')?.checked || false,
      affected_users_count:      parseInt(g('pl-users-count')?.value) || null,
      authorized_activators: (window._planAuthActivators || []).length ? window._planAuthActivators : null,
      documentation_links:   (window._planDocLinks       || []).length ? window._planDocLinks       : null,
      related_documents:     (window._planRelDocs         || []).length ? window._planRelDocs         : null,
    };

    if (!body.name) { UI.toast('El nombre del plan es obligatorio', 'error'); return; }
    if (!id && window._planVersioningCode) {
      body.code = window._planVersioningCode;
    }
    try {
      if (id) await Api.patch(`/api/bcp/plans/${id}`, body);
      else await Api.post('/api/bcp/plans', body);
      window._planVersioningCode = null;
      UI.toast('Plan guardado', 'success');
      _closePlanDrawer();
      _plans = [];
      _switchTab('plans');
    } catch (e) {
      window._planVersioningCode = null;
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  async function _approvePlan(id) {
    const plan = _plans.find(p => p.id === id);
    if (!plan) return;
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:420px;">
      <div class="modal-header"><h2><i class="ti ti-shield-check"></i> Confirmar aprobacion</h2></div>
      <div class="modal-body">
        <p style="margin-bottom:12px;"><strong>${UI.esc(plan.name)}</strong> — v${UI.esc(plan.version||'1.0')} — ${PLAN_TYPE_LABELS[plan.plan_type]||plan.plan_type}</p>
        <p style="font-size:13px;color:var(--text-subtle);">Al aprobar este plan confirmas que ha sido revisado y es valido para su activacion. El plan pasara a estado <strong>aprobado</strong> y podra ser activado en caso de incidente.</p>
        <div class="modal-footer-sticky" style="position:relative;padding:12px 0 0;">
          <div style="display:flex;gap:8px;margin-left:auto;">
            <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
            <button class="btn btn-primary btn-sm" id="btn-confirm-approve" style="background:var(--risk-high);border-color:var(--risk-high);">
              <i class="ti ti-check"></i> Aprobar plan
            </button>
          </div>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#btn-confirm-approve').addEventListener('click', async () => {
      try {
        await Api.post(`/api/bcp/plans/${id}/approve`, {});
        UI.toast('Plan aprobado', 'success');
        modal.remove();
        _plans = [];
        _switchTab('plans');
      } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
    });
  }

  // ── Modales — Test ───────────────────────────────────────────────────────────

  function _openTestModal(id, prefill) {
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:520px;max-height:90vh;display:flex;flex-direction:column">
      <div class="modal-header" style="flex-shrink:0">
        <h2>Programar test BCM</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="overflow-y:auto;flex:1;padding:20px 24px;display:block">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Tipo *</label>
            <select id="tm-type" class="form-control" style="font-size:13px">
              <option value="tabletop">Tabletop exercise</option>
              <option value="simulation">Simulacion</option>
              <option value="full_test">Test completo</option>
            </select>
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Fecha programada *</label>
            <input id="tm-date" class="form-control" type="datetime-local" style="font-size:13px">
          </div>
        </div>
        <div style="margin-bottom:12px">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Plan asociado</label>
          <select id="tm-plan" class="form-control" style="font-size:13px">
            <option value="">— Sin plan especifico —</option>
            ${_plans.map(p=>`<option value="${p.id}">${UI.esc(p.code||'')} ${UI.esc(p.name)}</option>`).join('')}
          </select>
        </div>
        <div style="margin-bottom:12px">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Objetivo</label>
          <input id="tm-obj" class="form-control" style="font-size:13px" placeholder="Objetivo del test">
        </div>
        <div style="margin-bottom:12px">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Descripcion del alcance</label>
          <textarea id="tm-scope" class="form-control" rows="3" style="font-size:13px"></textarea>
        </div>
        <div style="margin-bottom:12px">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Procesos a evaluar</label>
          <div style="max-height:120px;overflow-y:auto;border:1px solid var(--border);border-radius:4px;padding:6px;">
            ${_procs.map(p=>`<label style="display:flex;gap:8px;align-items:center;padding:4px 6px;font-size:13px;cursor:pointer;"><input type="checkbox" value="${p.id}" class="tm-pids" style="flex-shrink:0;margin:0;"><span>${UI.esc(p.name)}</span></label>`).join('')}
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Facilitador (ID usuario)</label>
            <input id="tm-fac" class="form-control" type="number" style="font-size:13px">
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Frecuencia planificada</label>
            <select id="tm-freq" class="form-control" style="font-size:13px">
              <option value="">— Sin definir —</option>
              <option value="mensual">Mensual</option>
              <option value="trimestral">Trimestral</option>
              <option value="semestral">Semestral</option>
              <option value="anual">Anual</option>
            </select>
          </div>
        </div>
        <div id="tm-ai-note" style="display:none;padding:8px 12px;background:rgba(89,0,141,.08);border-left:3px solid var(--primary);border-radius:4px;font-size:12px;margin-bottom:12px">
          <i class="ti ti-sparkles"></i> Tras guardar podras generar un checklist detallado con IA.
        </div>
      </div>
      <div class="modal-footer-sticky">
        <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
        <button class="btn btn-primary btn-sm" onclick="ViewBcp._saveTest()"><i class="ti ti-check"></i> Guardar test</button>
      </div>
    </div>`;
    document.body.appendChild(modal);

    // Auto-rellenar facilitador con usuario actual
    const me = Auth.user();
    if (me?.id) {
      const facEl = modal.querySelector('#tm-fac');
      if (facEl && !facEl.value) facEl.value = me.id;
    }

    // Aplicar prefill (IA recs o plan_id desde menu contextual)
    if (prefill) {
      if (prefill.test_type) {
        const sel = modal.querySelector('#tm-type');
        if (sel) sel.value = prefill.test_type;
      }
      if (prefill.scheduled_date) {
        const inp = modal.querySelector('#tm-date');
        if (inp) inp.value = prefill.scheduled_date + 'T09:00';
      }
      if (prefill.plan_id) {
        const planSel = modal.querySelector('#tm-plan');
        if (planSel) planSel.value = String(prefill.plan_id);
      }
    }
  }

  async function _saveTest() {
    const pids = [...document.querySelectorAll('.tm-pids:checked')].map(c => parseInt(c.value));
    const body = {
      test_type: document.getElementById('tm-type').value,
      scheduled_at: document.getElementById('tm-date').value,
      objective: document.getElementById('tm-obj').value||null,
      scope_description: document.getElementById('tm-scope').value||null,
      process_ids: pids,
      facilitator_id: parseInt(document.getElementById('tm-fac').value)||null,
      frequency: document.getElementById('tm-freq')?.value || null,
      plan_id: parseInt(document.getElementById('tm-plan')?.value) || null,
    };
    if (!body.scheduled_at) { UI.toast('La fecha es obligatoria', 'error'); return; }
    try {
      const resp = await Api.post('/api/bcp/tests', body);
      document.querySelector('.modal-bg')?.remove();
      _tests = [];
      _switchTab('tests');
      const newId = resp?.id;
      if (newId && body.plan_id) {
        // Tiene plan asociado: generar checklist IA automaticamente
        UI.toast('Test creado. Generando checklist con IA...', 'info');
        setTimeout(() => _genAiChecklist(newId), 600);
      } else {
        UI.toast('Test programado', 'success');
      }
    } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
  }

  async function _genAiChecklist(testId) {
    UI.toast('Generando checklist con IA...', 'info');
    try {
      const result = await Api.post(`/api/bcp/tests/${testId}/ai-generate-checklist`);
      _showAiChecklistModal(testId, result);
    } catch (e) {
      UI.toast('Error generando checklist: ' + (e.message || e), 'error');
    }
  }

  function _showAiChecklistModal(testId, result) {
    const cl = result?.checklist || {};
    const renderPhase = (title, items, color) => {
      if (!items?.length) return '';
      return `<div style="margin-bottom:16px">
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:${color};margin-bottom:8px;letter-spacing:.04em">${title}</div>
        ${items.map(item => `
          <div style="display:flex;gap:8px;padding:6px 10px;background:var(--bg-2);border-radius:4px;margin-bottom:4px;font-size:12px">
            <span style="flex-shrink:0;width:20px;height:20px;border-radius:50%;background:${color}22;color:${color};display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700">${item.order||'?'}</span>
            <div>
              <div style="font-weight:600">${UI.esc(item.title||'')}</div>
              ${item.description ? `<div style="color:var(--text-subtle);margin-top:2px">${UI.esc(item.description)}</div>` : ''}
              ${item.process ? `<div style="margin-top:2px"><span class="badge badge-secondary" style="font-size:10px">${UI.esc(item.process)}</span></div>` : ''}
              ${item.expected_rto_h != null ? `<div style="font-size:10px;color:var(--text-subtle)">RTO esperado: ${item.expected_rto_h}h</div>` : ''}
            </div>
          </div>`).join('')}
      </div>`;
    };

    const notifItems = (cl.notification_list || []).map(n =>
      `<div style="font-size:12px;padding:4px 0;border-bottom:1px solid var(--border)">
        <strong>${UI.esc(n.role||'')}</strong>
        ${n.when ? ` <span style="color:var(--text-subtle)">— ${UI.esc(n.when)}</span>` : ''}
        ${n.channel ? ` <span class="badge badge-secondary" style="font-size:10px">${UI.esc(n.channel)}</span>` : ''}
      </div>`).join('');

    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:640px;max-height:92vh;display:flex;flex-direction:column">
      <div class="modal-header">
        <h2><i class="ti ti-sparkles" style="color:var(--primary)"></i> Checklist generado por IA — Test #${testId}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:20px 24px;overflow-y:auto;flex:1">
        <div class="notice notice-info" style="margin-bottom:16px;font-size:12px">
          Checklist generado segun el contexto del plan BCM. Revisa y ajusta antes de ejecutar el test.
        </div>
        ${renderPhase('Pre-test — Preparacion', cl.pre_test, '#059669')}
        ${renderPhase('Pasos del test', cl.test_steps, '#2563eb')}
        ${renderPhase('Post-test — Cierre', cl.post_test, '#d65200')}
        ${notifItems ? `
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px">Lista de notificacion</div>
          ${notifItems}` : ''}
      </div>
      <div class="modal-footer-sticky">
        <button class="btn btn-sm" onclick="navigator.clipboard?.writeText(${JSON.stringify(JSON.stringify(cl, null, 2))});UI.toast('Copiado al portapapeles','success')">
          <i class="ti ti-copy"></i> Copiar JSON
        </button>
        <button class="btn btn-primary btn-sm" onclick="this.closest('.modal-bg').remove()">Cerrar</button>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  function _openTestResultModal(id) {
    const test = _tests.find(t => t.id === id);
    if (!test) return;
    const lbl = (text, req, sub) =>
      `<label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;display:block;margin-bottom:4px;">${text}${req?' <span style="color:var(--danger)">*</span>':''}
      </label>${sub?`<div style="font-size:10px;color:var(--text-subtle);margin-bottom:4px;">${sub}</div>`:''}`;

    const RESULT_DESCS = {
      passed: 'El ejercicio se completo sin problemas significativos.',
      partial: 'Se identificaron problemas menores o areas de mejora.',
      failed: 'El ejercicio no alcanzo los objetivos. Se requieren acciones correctoras.',
    };

    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:520px;max-height:90vh;display:flex;flex-direction:column;">
      <div class="modal-header" style="flex-shrink:0;">
        <h2>Resultado: ${UI.esc(test.code)} — ${test.test_type}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="overflow-y:auto;flex:1;padding:20px 24px;display:block;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>${lbl('Resultado','*')}
            <select id="rm-result" class="form-control" style="font-size:13px;" onchange="ViewBcp._onResultChange(this.value)">
              <option value="">— Sin resultado —</option>
              ${['passed','partial','failed'].map(r =>
                `<option value="${r}"${test.result===r?' selected':''}>${{passed:'Pasado',partial:'Parcial',failed:'Fallido'}[r]}</option>`
              ).join('')}
            </select>
            <div id="rm-result-desc" style="font-size:11px;color:var(--text-subtle);margin-top:4px;">${RESULT_DESCS[test.result]||''}</div>
          </div>
          <div>${lbl('Fecha de realizacion','*')}
            <input id="rm-date" class="form-control" type="datetime-local" style="font-size:13px;"
              value="${test.conducted_at?(test.conducted_at.replace('Z','')||''):''}">
          </div>
        </div>
        <div style="margin-bottom:14px;">${lbl('Hallazgos','','¿Que no funciono segun lo esperado?')}
          <textarea id="rm-findings" class="form-control" rows="3" style="font-size:13px;">${UI.esc(test.findings||'')}</textarea>
        </div>
        <div style="margin-bottom:14px;">${lbl('Lecciones aprendidas',true,'Obligatorio si resultado != Pasado')}
          <textarea id="rm-lessons" class="form-control" rows="3" style="font-size:13px;">${UI.esc(test.lessons_learned||'')}</textarea>
        </div>
        <div style="margin-bottom:14px;">${lbl('Acciones de mejora','')}
          <textarea id="rm-actions" class="form-control" rows="2" style="font-size:13px;">${UI.esc(test.improvement_actions||'')}</textarea>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>${lbl('RTO real conseguido (horas)','','Tiempo que tardo realmente la recuperacion')}
            <input id="rm-rto-achieved" class="form-control" type="number" min="0" style="font-size:13px;"
              value="${test.rto_achieved_hours??''}" placeholder="Ej: 3">
          </div>
          <div>${lbl('RPO real conseguido (horas)','','Datos perdidos reales medidos')}
            <input id="rm-rpo-achieved" class="form-control" type="number" min="0" style="font-size:13px;"
              value="${test.rpo_achieved_hours??''}" placeholder="Ej: 1">
          </div>
        </div>
        <div style="margin-bottom:14px;">
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:6px">Evidencias adjuntas</div>
          <div id="rm-evidence-list" style="margin-bottom:8px">
            <div style="font-size:12px;color:var(--text-subtle)">Cargando evidencias...</div>
          </div>
          <div style="background:var(--bg-2);border:1px dashed var(--border);border-radius:6px;padding:10px 12px">
            <div style="font-size:11px;color:var(--text-subtle);margin-bottom:8px">Adjuntar nueva evidencia (PDF, imagen, Excel...)</div>
            <div style="display:flex;gap:8px;align-items:center">
              <input id="rm-ev-title" class="form-control" style="font-size:12px;flex:1" placeholder="Titulo de la evidencia">
              <input type="file" id="rm-ev-file" class="form-control" style="font-size:12px;flex:1"
                accept=".pdf,.docx,.doc,.txt,.csv,.png,.jpg,.jpeg,.xlsx,.xls">
              <button class="btn btn-sm btn-primary" onclick="ViewBcp._testUploadEvidence(${id})"><i class="ti ti-upload"></i></button>
            </div>
          </div>
        </div>
      </div>
      <div class="modal-footer-sticky">
        <button class="btn btn-ghost btn-sm" onclick="ViewBcp._genAiChecklist(${id});this.closest('.modal-bg').remove()" style="margin-right:auto">
          <i class="ti ti-sparkles" style="color:var(--primary)"></i> Checklist IA
        </button>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-primary btn-sm" onclick="ViewBcp._saveTestResult(${id})"><i class="ti ti-check"></i> Guardar resultado</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);

    // Set description for current result
    const currentResult = test.result || '';
    if (currentResult) {
      const desc = document.getElementById('rm-result-desc');
      if (desc) desc.textContent = RESULT_DESCS[currentResult] || '';
    }

    // Load existing test evidence
    _loadTestEvidence(id);
  }

  async function _loadTestEvidence(testId) {
    const listEl = document.getElementById('rm-evidence-list');
    if (!listEl) return;
    try {
      const items = await Api.get(`/api/bcp/evidence?linked_test_id=${testId}`).catch(() => []);
      if (!items.length) {
        listEl.innerHTML = '<div style="font-size:12px;color:var(--text-subtle)">Sin evidencias adjuntas.</div>';
        return;
      }
      listEl.innerHTML = items.map(e => `
        <div style="display:flex;align-items:center;gap:8px;padding:5px 8px;border:1px solid var(--border);border-radius:6px;margin-bottom:4px;background:var(--bg-2)">
          <i class="ti ti-file" style="font-size:14px;color:var(--primary)"></i>
          <div style="flex:1;min-width:0">
            <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${UI.esc(e.title||e.file_name||'')}</div>
            <div style="font-size:10px;color:var(--text-subtle)">${e.file_size?Math.round(e.file_size/1024)+'KB':''} · ${e.evidence_type||''}</div>
          </div>
          <a href="/api/bcp/evidence/${e.id}/download" target="_blank" class="btn btn-sm" style="font-size:10px;padding:2px 6px">
            <i class="ti ti-download"></i>
          </a>
        </div>
      `).join('');
    } catch (_) {
      listEl.innerHTML = '<div style="font-size:12px;color:var(--text-subtle)">No se pudieron cargar las evidencias.</div>';
    }
  }

  async function _testUploadEvidence(testId) {
    const title = document.getElementById('rm-ev-title')?.value?.trim();
    const fileEl = document.getElementById('rm-ev-file');
    const file = fileEl?.files?.[0];
    if (!title) { UI.toast('Titulo requerido', 'error'); return; }
    if (!file) { UI.toast('Selecciona un archivo', 'error'); return; }
    const fd = new FormData();
    fd.append('title', title);
    fd.append('evidence_type', 'test_evidence');
    fd.append('linked_test_id', String(testId));
    fd.append('file', file);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/bcp/evidence', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Error al subir');
      }
      UI.toast('Evidencia adjuntada', 'success');
      document.getElementById('rm-ev-title').value = '';
      fileEl.value = '';
      await _loadTestEvidence(testId);
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  function _onResultChange(val) {
    const DESCS = {
      passed: 'El ejercicio se completo sin problemas significativos.',
      partial: 'Se identificaron problemas menores o areas de mejora.',
      failed: 'El ejercicio no alcanzo los objetivos. Se requieren acciones correctoras.',
    };
    const el = document.getElementById('rm-result-desc');
    if (el) el.textContent = DESCS[val] || '';
  }

  async function _saveTestResult(id) {
    const result = document.getElementById('rm-result')?.value || null;
    const body = {
      conducted_at: document.getElementById('rm-date')?.value || null,
      result,
      findings: document.getElementById('rm-findings')?.value || null,
      lessons_learned: document.getElementById('rm-lessons')?.value || null,
      improvement_actions: document.getElementById('rm-actions')?.value || null,
      rto_achieved_hours: parseInt(document.getElementById('rm-rto-achieved')?.value) || null,
      rpo_achieved_hours: parseInt(document.getElementById('rm-rpo-achieved')?.value) || null,
    };
    // Validar: si resultado != "passed", lecciones son obligatorias
    if (result && result !== 'passed' && !body.lessons_learned) {
      UI.toast('Las lecciones aprendidas son obligatorias para resultado parcial o fallido', 'error');
      return;
    }
    try {
      await Api.patch(`/api/bcp/tests/${id}`, body);
      UI.toast('Resultado guardado', 'success');
      document.querySelector('.modal-bg')?.remove();

      // Si el test fallo o fue parcial, ofrecer crear NC
      if (result === 'failed' || result === 'partial') {
        _offerCreateNC(id, result);
      } else {
        _switchTab('tests');
      }
    } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
  }

  function _offerCreateNC(testId, result) {
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:420px;">
      <div class="modal-header">
        <h2><i class="ti ti-alert-circle" style="color:var(--risk-high)"></i> Test ${result === 'failed' ? 'fallido' : 'parcial'}</h2>
      </div>
      <div class="modal-body" style="display:block;">
        <p style="font-size:13px;margin-bottom:16px;">Un test ${result === 'failed' ? 'fallido' : 'con resultado parcial'} puede generar una No Conformidad automaticamente para garantizar el seguimiento.
        <br><br><strong>¿Crear NC vinculada a este test?</strong></p>
        <div class="modal-footer-sticky" style="position:relative;padding:12px 0 0;">
          <div style="display:flex;gap:8px;margin-left:auto;">
            <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove();ViewBcp._switchTab('tests')">No por ahora</button>
            <button class="btn btn-primary btn-sm" id="btn-create-nc-from-test">
              <i class="ti ti-plus"></i> Si, crear NC
            </button>
          </div>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#btn-create-nc-from-test').addEventListener('click', async () => {
      try {
        const res = await Api.post(`/api/bcp/tests/${testId}/create-nc`, {});
        UI.toast(`NC ${res.nc_code} creada correctamente`, 'success');
        modal.remove();
        _switchTab('tests');
      } catch (e) {
        UI.toast('Error al crear NC: ' + (e.message || e), 'error');
        modal.remove();
        _switchTab('tests');
      }
    });
  }

  // ── Modales — Proveedor BCM ──────────────────────────────────────────────────

  async function _openSLModal(sl) {
    const lbl = (t, req) => `<label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--text-subtle);padding-left:1px;display:block;margin-bottom:4px;">${t}${req?' <span style="color:var(--danger)">*</span>':''}</label>`;
    const CRIT_SL = [{v:'critical',l:'Critica'},{v:'high',l:'Alta'},{v:'medium',l:'Media'},{v:'low',l:'Baja'}];

    _suppliers = await Api.get('/api/suppliers/').catch(() => _suppliers);

    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:560px;max-height:90vh;display:flex;flex-direction:column;">
      <div class="modal-header" style="flex-shrink:0;">
        <h2>${sl ? 'Editar vinculo BCM' : 'Vincular proveedor al BCP'}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="overflow-y:auto;flex:1;padding:20px 24px;display:block;">
        <div style="margin-bottom:14px;">
          ${lbl('Proveedor',true)}
          <div style="display:flex;gap:8px;align-items:center;">
            <select id="slm-sup" class="form-control" style="font-size:13px;flex:1;" ${sl?'disabled':''}>
              <option value="">— Seleccionar proveedor —</option>
              ${_suppliers.map(s=>`<option value="${s.id}"${sl?.supplier_id===s.id?' selected':''}>${UI.esc(s.name)}</option>`).join('')}
            </select>
            ${!sl ? `<button type="button" class="btn btn-ghost btn-sm" id="slm-btn-new-sup" title="Crear nuevo proveedor" style="white-space:nowrap;flex-shrink:0;">
              <i class="ti ti-plus"></i> Nuevo
            </button>` : ''}
          </div>
          <div id="slm-new-sup-form" style="display:none;margin-top:10px;padding:12px;background:var(--bg-2);border-radius:var(--radius);border:1px solid var(--border);">
            <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px;">Crear nuevo proveedor</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
              <div>
                <label style="font-size:11px;color:var(--text-subtle);display:block;margin-bottom:3px;">Nombre <span style="color:var(--danger)">*</span></label>
                <input id="slm-new-sup-name" class="form-control" style="font-size:13px;" placeholder="Nombre del proveedor">
              </div>
              <div>
                <label style="font-size:11px;color:var(--text-subtle);display:block;margin-bottom:3px;">Categoria</label>
                <input id="slm-new-sup-cat" class="form-control" style="font-size:13px;" placeholder="Ej: Cloud, Software...">
              </div>
            </div>
            <div style="display:flex;gap:8px;justify-content:flex-end;">
              <button type="button" class="btn btn-sm" id="slm-cancel-new-sup">Cancelar</button>
              <button type="button" class="btn btn-primary btn-sm" id="slm-confirm-new-sup"><i class="ti ti-check"></i> Crear</button>
            </div>
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>${lbl('Criticidad BCM')}
            <select id="slm-crit" class="form-control" style="font-size:13px;">
              ${CRIT_SL.map(c=>`<option value="${c.v}"${sl?.criticality===c.v?' selected':''}>${c.l}</option>`).join('')}
            </select>
          </div>
          <div>${lbl('Ultima revision')}
            <input id="slm-rev" class="form-control" type="date" style="font-size:13px;" value="${sl?.last_review_date?sl.last_review_date.substring(0,10):''}">
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>${lbl('RTO impacto si falla (horas)')}
            <input id="slm-rto" class="form-control" type="number" style="font-size:13px;" value="${sl?.rto_impact_hours??''}">
          </div>
          <div>${lbl('SLA contractual (horas)')}
            <input id="slm-sla" class="form-control" type="number" style="font-size:13px;" value="${sl?.contract_sla_hours??''}">
          </div>
        </div>
        <div style="margin-bottom:14px;">${lbl('Proveedor alternativo')}
          <select id="slm-alt" class="form-control" style="font-size:13px;">
            <option value="">— Ninguno —</option>
            ${_suppliers.filter(s=>s.id!==sl?.supplier_id).map(s=>
              `<option value="${s.id}"${sl?.alternative_supplier_id===s.id?' selected':''}>${UI.esc(s.name)}</option>`).join('')}
          </select>
        </div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;padding:10px;background:var(--bg-2);border-radius:var(--radius);">
          <input id="slm-hasplan" type="checkbox" style="width:16px;height:16px;" ${sl?.has_contingency_plan?'checked':''}>
          <label for="slm-hasplan" style="margin:0;font-size:13px;cursor:pointer;display:inline;">Este proveedor tiene plan de contingencia documentado</label>
        </div>
        <div style="margin-bottom:14px;">${lbl('Descripcion del plan de contingencia')}
          <textarea id="slm-desc" class="form-control" rows="2" style="font-size:13px;" placeholder="¿Como se garantiza la continuidad si este proveedor falla?">${UI.esc(sl?.contingency_description||'')}</textarea>
        </div>
        <div style="margin-bottom:14px;">${lbl('Procesos que dependen de este proveedor')}
          <div style="max-height:130px;overflow-y:auto;border:0.5px solid var(--border);border-radius:var(--radius);padding:8px;">
            ${_procs.length ? _procs.map(p=>`
              <div style="display:flex;gap:8px;align-items:center;padding:4px 2px;">
                <input type="checkbox" value="${p.id}" class="slm-pids" style="flex-shrink:0;width:15px;height:15px;" ${(sl?.process_ids||[]).includes(p.id)?'checked':''}>
                <span style="flex-shrink:0;font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;background:${CRIT_COLORS[p.criticality]||'#6B7280'}22;color:${CRIT_COLORS[p.criticality]||'#6B7280'};">${p.criticality}</span>
                <span style="font-size:13px;">${UI.esc(p.name)}</span>
              </div>`).join('') : '<span style="font-size:12px;color:var(--text-subtle)">No hay procesos registrados.</span>'}
          </div>
        </div>
      </div>
      <div class="modal-footer-sticky">
        ${sl ? `<button class="btn btn-danger btn-sm" onclick="ViewBcp._delSL(${sl.id})"><i class="ti ti-trash"></i> Eliminar</button>` : ''}
        <div style="display:flex;gap:8px;margin-left:auto;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-primary btn-sm" onclick="ViewBcp._saveSL(${sl?.id||'null'})"><i class="ti ti-check"></i> Guardar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);

    document.getElementById('slm-btn-new-sup')?.addEventListener('click', () => {
      document.getElementById('slm-new-sup-form').style.display = 'block';
      document.getElementById('slm-btn-new-sup').style.display = 'none';
      document.getElementById('slm-new-sup-name').focus();
    });
    document.getElementById('slm-cancel-new-sup')?.addEventListener('click', () => {
      document.getElementById('slm-new-sup-form').style.display = 'none';
      document.getElementById('slm-btn-new-sup').style.display = '';
    });
    document.getElementById('slm-confirm-new-sup')?.addEventListener('click', async () => {
      const name = document.getElementById('slm-new-sup-name').value.trim();
      if (!name) { UI.toast('El nombre del proveedor es obligatorio', 'error'); return; }
      const cat = document.getElementById('slm-new-sup-cat').value.trim() || null;
      const btn = document.getElementById('slm-confirm-new-sup');
      btn.disabled = true;
      try {
        const created = await Api.post('/api/suppliers/', { name, category: cat });
        _suppliers.push(created);
        const sel = document.getElementById('slm-sup');
        const opt = document.createElement('option');
        opt.value = created.id;
        opt.textContent = created.name;
        opt.selected = true;
        sel.appendChild(opt);
        const altSel = document.getElementById('slm-alt');
        const altOpt = document.createElement('option');
        altOpt.value = created.id;
        altOpt.textContent = created.name;
        altSel.appendChild(altOpt);
        document.getElementById('slm-new-sup-form').style.display = 'none';
        document.getElementById('slm-btn-new-sup').style.display = '';
        document.getElementById('slm-new-sup-name').value = '';
        document.getElementById('slm-new-sup-cat').value = '';
        UI.toast(`Proveedor "${name}" creado`, 'success');
      } catch (e) {
        UI.toast('Error al crear proveedor: ' + (e.message || e), 'error');
      } finally {
        btn.disabled = false;
      }
    });
  }

  function _editSL(id) { _openSLModal(_slinks.find(s => s.id === id)); }

  async function _saveSL(id) {
    const pids = [...document.querySelectorAll('.slm-pids:checked')].map(c => parseInt(c.value));
    const body = {
      supplier_id: parseInt(document.getElementById('slm-sup').value),
      criticality: document.getElementById('slm-crit').value,
      rto_impact_hours: parseInt(document.getElementById('slm-rto').value)||null,
      contract_sla_hours: parseInt(document.getElementById('slm-sla').value)||null,
      has_contingency_plan: document.getElementById('slm-hasplan').checked,
      contingency_description: document.getElementById('slm-desc').value||null,
      alternative_supplier_id: parseInt(document.getElementById('slm-alt').value)||null,
      last_review_date: document.getElementById('slm-rev').value||null,
      process_ids: pids,
    };
    try {
      if (id) await Api.patch(`/api/bcp/supplier-links/${id}`, body);
      else await Api.post('/api/bcp/supplier-links', body);
      UI.toast('Vinculo guardado', 'success');
      document.querySelector('.modal-bg')?.remove();
      _switchTab('suppliers');
    } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
  }

  async function _delSL(id) {
    if (!confirm('Eliminar vinculo BCM?')) return;
    await Api.del(`/api/bcp/supplier-links/${id}`);
    UI.toast('Vinculo eliminado', 'success');
    document.querySelector('.modal-bg')?.remove();
    _switchTab('suppliers');
  }

  // ── Programa ejercicios modal ─────────────────────────────────────────────────

  function _openEPModal(year) {
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:440px;">
      <div class="modal-header">
        <h2>Programa de ejercicios ${year}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <label>Objetivo general</label>
        <textarea id="ep-obj" class="form-control" rows="3"
          placeholder="Objetivo del programa anual de ejercicios..."></textarea>
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewBcp._saveEP(${year})">Crear programa</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _saveEP(year) {
    const body = {
      year: year,
      overall_objective: document.getElementById('ep-obj').value||null,
    };
    try {
      await Api.post('/api/bcp/exercise-programme', body);
      UI.toast('Programa creado', 'success');
      document.querySelector('.modal-bg')?.remove();
      _switchTab('tests');
    } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
  }

  // ── Tab Localizaciones ───────────────────────────────────────────────────────

  async function _tabLocations(container) {
    const [tree, consolidated] = await Promise.all([
      Api.get('/api/bcp/locations').catch(() => []),
      Api.get('/api/bcp/locations/consolidated').catch(() => ({})),
    ]);

    // Actualizar cache global
    _locations = tree;
    const flat = [];
    (function flatten(nodes, depth) {
      nodes.forEach(n => { flat.push({...n, depth}); flatten(n.children || [], depth + 1); });
    })(tree, 0);
    flat.forEach(l => { _locationMap[l.id] = l; });

    const mColor = { green: 'var(--risk-low)', yellow: 'var(--risk-medium)', red: 'var(--risk-critical)' };
    const locData = consolidated.locations || {};
    const total = consolidated.total_locations || 0;
    const orgMaturity = consolidated.org_maturity || 'red';
    const unlocated = consolidated.unlocated_processes || 0;
    const greenCount = flat.filter(l => locData[l.id]?.metrics?.maturity_color === 'green').length;
    const pctGreen = flat.length ? Math.round(greenCount / flat.length * 100) : 0;
    const isAdmin = Auth.canEdit();

    function renderNode(node, depth) {
      const m = locData[node.id]?.metrics || {};
      const tlClass = 'bcm-tl-' + (m.maturity_color || 'red');
      const hasChildren = (node.children || []).length > 0;
      return `
        <div class="bcm-loc-node" style="margin-left:${depth * 24}px;margin-bottom:6px">
          <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--bg-card);border:0.5px solid var(--border);border-radius:var(--radius);${isAdmin ? 'cursor:pointer' : ''}"
            ${isAdmin ? `onclick="if(!event.target.closest('button'))ViewBcp._editLocation(${node.id})"` : ''}>
            ${hasChildren
              ? `<button class="btn btn-ghost btn-sm bcm-loc-toggle" style="padding:2px 4px;min-width:22px" onclick="event.stopPropagation();ViewBcp._toggleLocChildren(${node.id})">
                  <i class="ti ti-chevron-down" id="loc-chev-${node.id}" style="font-size:12px"></i></button>`
              : `<span style="width:22px;flex-shrink:0"></span>`}
            <span class="bcm-traffic-light ${tlClass}"></span>
            <div style="flex:1;min-width:0">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                ${node.code ? `<code style="font-size:10px;color:var(--text-subtle)">${UI.esc(node.code)}</code>` : ''}
                <strong style="font-size:14px">${UI.esc(node.name)}</strong>
                ${node.country ? `<span style="font-size:11px;color:var(--text-subtle)"><i class="ti ti-globe" style="font-size:10px"></i> ${UI.esc(node.country)}</span>` : ''}
                ${isAdmin ? `<span style="font-size:10px;color:var(--text-subtle);opacity:.6"><i class="ti ti-edit" style="font-size:10px"></i> editar</span>` : ''}
              </div>
              <div style="display:flex;gap:14px;margin-top:3px;font-size:11px;color:var(--text-subtle);flex-wrap:wrap">
                <span><strong style="color:var(--risk-critical)">${m.processes_critical || 0}</strong> proc. críticos</span>
                <span><strong style="color:var(--risk-low)">${m.plans_approved || 0}</strong> planes aprobados</span>
                <span>BIA avg <strong>${m.avg_bia_pct || 0}%</strong></span>
                <span><strong>${m.tests_passed_12m || 0}</strong> tests OK 12m</span>
              </div>
            </div>
            <div style="display:flex;gap:6px;flex-shrink:0">
              <button class="btn btn-ghost btn-sm" title="Filtrar por esta localización" onclick="event.stopPropagation();ViewBcp._setLocFilter(${node.id})">
                <i class="ti ti-filter" style="font-size:13px"></i>
              </button>
              ${isAdmin ? `<button class="btn btn-primary btn-sm" style="font-size:11px;padding:4px 10px" onclick="event.stopPropagation();ViewBcp._editLocation(${node.id})">
                <i class="ti ti-edit" style="font-size:11px"></i> Editar
              </button>` : ''}
            </div>
          </div>
          ${hasChildren ? `<div class="bcm-loc-children" id="loc-children-${node.id}">
            ${node.children.map(c => renderNode(c, depth + 1)).join('')}
          </div>` : ''}
        </div>`;
    }

    container.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div>
          <h3 style="margin:0;font-size:16px">Localizaciones BCM</h3>
          <p style="margin:4px 0 0;font-size:12px;color:var(--text-subtle)">ISO 22301 cl. 8.2 — Jerarquía de sedes y unidades</p>
        </div>
        ${isAdmin ? `<button class="btn btn-primary btn-sm" id="btn-new-loc"><i class="ti ti-plus"></i> Nueva localización</button>` : ''}
      </div>

      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">
        <div class="stat-card"><div class="stat-value">${total}</div><div class="stat-label">Total localizaciones</div></div>
        <div class="stat-card ${pctGreen < 50 ? 'stat-warning' : ''}">
          <div class="stat-value" style="color:${mColor[pctGreen >= 50 ? 'green' : 'red']}">${pctGreen}%</div>
          <div class="stat-label">Con madurez verde</div>
        </div>
        <div class="stat-card ${unlocated > 0 ? 'stat-warning' : ''}">
          <div class="stat-value" style="color:${unlocated > 0 ? 'var(--risk-high)' : 'inherit'}">${unlocated}</div>
          <div class="stat-label">Procesos sin localización</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="font-size:15px;font-weight:700;color:${mColor[orgMaturity]}">${orgMaturity.toUpperCase()}</div>
          <div class="stat-label">Madurez global</div>
        </div>
      </div>

      <div id="loc-tree">
        ${tree.length === 0
          ? `<div class="notice notice-info">Sin localizaciones definidas. Crea la primera para organizar tu BCM por sede.</div>`
          : tree.map(n => renderNode(n, 0)).join('')}
      </div>
    `;

    if (isAdmin) {
      container.querySelector('#btn-new-loc')?.addEventListener('click', () => _modalLocation());
    }
  }

  function _toggleLocChildren(id) {
    const children = document.getElementById('loc-children-' + id);
    const chev = document.getElementById('loc-chev-' + id);
    if (!children) return;
    children.classList.toggle('collapsed');
    if (chev) {
      chev.className = children.classList.contains('collapsed')
        ? 'ti ti-chevron-right' : 'ti ti-chevron-down';
      chev.style.fontSize = '12px';
    }
  }

  function _setLocFilter(locId) {
    _locationFilter = locId;
    const sel = document.getElementById('bcm-sede-select') || document.getElementById('bcp-loc-select');
    if (sel) sel.value = locId;
    _updateSedeBadge();
    _loadSedeStats();
    _renderContent();
  }

  async function _editLocation(locId) {
    // Intentar obtener datos frescos del API; caer en cache si falla
    let loc = await Api.get('/api/bcp/locations/' + locId).catch(() => null);
    if (!loc) loc = _locationMap[locId];
    if (!loc) { UI.toast('No se encontró la localización', 'error'); return; }
    _modalLocation(loc);
  }

  async function _modalLocation(loc) {
    let users = [];
    try { users = await Api.get('/api/users/').catch(() => []); } catch (_) {}
    const flatLocs = [];
    (function flatten(nodes) { nodes.forEach(n => { flatLocs.push(n); flatten(n.children || []); }); })(_locations);

    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
      <div class="modal" style="max-width:560px;max-height:92vh;display:flex;flex-direction:column;">
        <div class="modal-header" style="flex-shrink:0;">
          <h2>${loc ? 'Editar localización: ' + UI.esc(loc.name) : 'Nueva localización BCM'}</h2>
          <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
        </div>
        <div class="modal-body" style="overflow-y:auto;flex:1;padding:20px 24px;display:block;">
          <div style="display:grid;grid-template-columns:2fr 1fr;gap:12px;margin-bottom:14px;">
            <div>
              <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle)">Nombre *</label>
              <input id="locm-name" class="form-control" style="font-size:13px" value="${UI.esc(loc?.name || '')}">
            </div>
            <div>
              <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle)">Código</label>
              <input id="locm-code" class="form-control" style="font-size:13px" value="${UI.esc(loc?.code || '')}" ${loc ? 'readonly' : ''} placeholder="LOC-001">
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
            <div>
              <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle)">Localización padre</label>
              <select id="locm-parent" class="form-control" style="font-size:13px">
                <option value="">— Nivel raíz (corporativo) —</option>
                ${flatLocs.filter(l => !loc || l.id !== loc.id).map(l =>
                  `<option value="${l.id}"${loc?.parent_id === l.id ? ' selected' : ''}>${'&nbsp;'.repeat((l.depth || 0) * 2)}${UI.esc(l.name)}</option>`
                ).join('')}
              </select>
            </div>
            <div>
              <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle)">País</label>
              <input id="locm-country" class="form-control" style="font-size:13px" value="${UI.esc(loc?.country || '')}" placeholder="España">
            </div>
          </div>
          <div style="margin-bottom:14px;">
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle)">Dirección</label>
            <textarea id="locm-address" class="form-control" rows="2" style="font-size:13px">${UI.esc(loc?.address || '')}</textarea>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
            <div>
              <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle)">Responsable BCM</label>
              <select id="locm-mgr" class="form-control" style="font-size:13px">
                <option value="">— Sin asignar —</option>
                ${users.map(u => `<option value="${u.id}"${loc?.bcm_manager_id === u.id ? ' selected' : ''}>${UI.esc(u.full_name || u.email)}</option>`).join('')}
              </select>
            </div>
            <div>
              <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle)">Tipo site recuperación</label>
              <select id="locm-site-type" class="form-control" style="font-size:13px">
                <option value="">— Ninguno —</option>
                ${[['hot','Hot site'],['warm','Warm site'],['cold','Cold site'],['cloud','Cloud'],['wfh','Trabajo remoto']].map(([v,l]) =>
                  `<option value="${v}"${loc?.recovery_site_type === v ? ' selected' : ''}>${l}</option>`).join('')}
              </select>
            </div>
          </div>
          <div style="margin-bottom:14px;">
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle)">Descripción del site de recuperación</label>
            <textarea id="locm-site-desc" class="form-control" rows="2" style="font-size:13px">${UI.esc(loc?.recovery_site_description || '')}</textarea>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
            <div>
              <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle)">Localización alternativa</label>
              <select id="locm-alt-loc" class="form-control" style="font-size:13px">
                <option value="">— Ninguna —</option>
                ${flatLocs.filter(l => !loc || l.id !== loc.id).map(l =>
                  `<option value="${l.id}"${loc?.alternate_location_id === l.id ? ' selected' : ''}>${UI.esc(l.name)}</option>`).join('')}
              </select>
            </div>
            <div style="display:flex;align-items:center;gap:10px;padding-top:26px">
              <input id="locm-active" type="checkbox" style="width:16px;height:16px" ${!loc || loc.is_active !== false ? 'checked' : ''}>
              <label for="locm-active" style="margin:0;font-size:13px;cursor:pointer">Activa</label>
            </div>
          </div>
          ${loc ? `<div style="border-top:0.5px solid var(--border);padding-top:12px;margin-top:4px">
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle)">Activos asignados a esta localización</label>
            <div id="loc-assets-list" style="margin-top:6px;font-size:12px;color:var(--text-subtle)">Cargando...</div>
          </div>` : ''}
        </div>
        <div class="modal-footer-sticky">
          ${loc ? `<button class="btn btn-danger btn-sm" id="btn-del-loc-full"><i class="ti ti-trash"></i> Eliminar</button>` : ''}
          <div style="display:flex;gap:8px;margin-left:auto">
            <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
            <button class="btn btn-primary btn-sm" id="btn-save-loc-full"><i class="ti ti-check"></i> Guardar</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);

    if (loc) {
      Api.get('/api/assets/?limit=200').then(data => {
        const items = Array.isArray(data) ? data : (data.items || []);
        const locAssets = items.filter(a => a.bcm_location_id === loc.id);
        const el = modal.querySelector('#loc-assets-list');
        if (!el) return;
        if (!locAssets.length) { el.textContent = 'Sin activos asignados a esta localización.'; return; }
        el.innerHTML = locAssets.map(a =>
          `<span class="badge badge-muted" style="margin:2px;font-size:11px">${UI.esc(a.code || '')} ${UI.esc(a.name)}</span>`
        ).join('');
      }).catch(() => {});
    }

    modal.querySelector('#btn-save-loc-full').onclick = async () => {
      const name = modal.querySelector('#locm-name').value.trim();
      if (!name) return UI.toast('El nombre es obligatorio', 'error');
      const altLocId = parseInt(modal.querySelector('#locm-alt-loc').value) || null;
      const body = {
        name,
        code: modal.querySelector('#locm-code').value.trim() || null,
        parent_id: parseInt(modal.querySelector('#locm-parent').value) || null,
        country: modal.querySelector('#locm-country').value.trim() || null,
        address: modal.querySelector('#locm-address').value.trim() || null,
        bcm_manager_id: parseInt(modal.querySelector('#locm-mgr').value) || null,
        recovery_site_type: modal.querySelector('#locm-site-type').value || null,
        recovery_site_description: modal.querySelector('#locm-site-desc').value.trim() || null,
        alternate_location_id: altLocId,
        is_active: modal.querySelector('#locm-active').checked,
      };
      try {
        let saved;
        if (loc) saved = await Api.patch('/api/bcp/locations/' + loc.id, body);
        else saved = await Api.post('/api/bcp/locations', body);
        UI.toast('Localización guardada', 'success');
        modal.remove();
        await _loadLocations();
        // Auto-crear dependencias si hay sede alternativa configurada
        const savedId = saved?.id || loc?.id;
        if (savedId && altLocId) {
          try {
            const syncRes = await Api.post('/api/bcp/locations/' + savedId + '/sync-deps', {});
            if (syncRes.created > 0) {
              UI.toast(syncRes.created + ' dependencia(s) de localización alternativa creada(s) automáticamente', 'success');
            }
          } catch (_) { /* sync falla silenciosamente */ }
        }
        _setStep(1);
      } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
    };

    if (loc) {
      modal.querySelector('#btn-del-loc-full').onclick = async () => {
        if (!confirm('¿Eliminar localización? Solo posible si no hay procesos vinculados.')) return;
        try {
          await Api.del('/api/bcp/locations/' + loc.id);
          UI.toast('Localización eliminada', 'success');
          modal.remove();
          await _loadLocations();
          _setStep(1);
        } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
      };
    }
  }

  // ── Tab Grafo de dependencias ─────────────────────────────────────────────────

  async function _ensureCytoscape() {
    if (window.cytoscape) return true;
    return new Promise(resolve => {
      const s = document.createElement('script');
      s.src = '/vendor/js/cytoscape.min.js';
      s.onload = () => resolve(true);
      s.onerror = () => resolve(false);
      document.head.appendChild(s);
    });
  }

  async function _tabGraph(container) {
    const cytOk = await _ensureCytoscape();
    if (!cytOk) {
      container.innerHTML = '<div class="notice notice-warning">No se pudo cargar el visualizador de grafo. Verifica que el archivo <code>/vendor/js/cytoscape.min.js</code> esté disponible en el servidor.</div>';
      return;
    }

    container.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px">
        <div>
          <h3 style="margin:0;font-size:16px">Mapa de dependencias BCM</h3>
          <p style="margin:4px 0 0;font-size:12px;color:var(--text-subtle)">Procesos · Activos · Proveedores externos · Rutas criticas — clic en nodo para ver detalle</p>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <select id="graph-loc-filter" class="form-control" style="font-size:12px;width:auto;min-width:140px">
            <option value="">Todas las localizaciones</option>
          </select>
          <button class="btn btn-sm btn-ghost" id="btn-graph-zoom-in" title="Zoom +"><i class="ti ti-zoom-in"></i></button>
          <button class="btn btn-sm btn-ghost" id="btn-graph-zoom-out" title="Zoom -"><i class="ti ti-zoom-out"></i></button>
          <button class="btn btn-sm btn-ghost" id="btn-graph-fit" title="Ajustar todo"><i class="ti ti-arrows-maximize"></i></button>
          <button class="btn btn-sm btn-ghost" id="btn-graph-export" title="Exportar PNG"><i class="ti ti-download"></i></button>
          <button class="btn btn-sm btn-secondary" id="btn-analyze-graph"><i class="ti ti-brain"></i> Analizar con IA</button>
        </div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;font-size:12px">
        <label style="display:flex;gap:5px;align-items:center;cursor:pointer;padding:4px 8px;border:1px solid var(--border);border-radius:4px">
          <input type="checkbox" id="graph-show-assets" checked> <span>Activos IT</span>
        </label>
        <label style="display:flex;gap:5px;align-items:center;cursor:pointer;padding:4px 8px;border:1px solid var(--border);border-radius:4px">
          <input type="checkbox" id="graph-show-suppliers" checked> <span>Proveedores externos</span>
        </label>
        <label style="display:flex;gap:5px;align-items:center;cursor:pointer;padding:4px 8px;border:1px solid var(--border);border-radius:4px">
          <input type="checkbox" id="graph-show-labels" checked> <span>Etiquetas aristas</span>
        </label>
        <label style="display:flex;gap:5px;align-items:center;cursor:pointer;padding:4px 8px;border:1px solid var(--border);border-radius:4px">
          <input type="checkbox" id="graph-only-critical"> <span>Solo criticos</span>
        </label>
      </div>
      <div style="display:grid;grid-template-columns:1fr 300px;gap:14px;align-items:start">
        <div>
          <div id="cy-graph" style="width:100%;height:560px;border:1px solid var(--border);border-radius:var(--radius-lg);position:relative;overflow:hidden;background-color:#0b0b14;background-image:radial-gradient(circle at 15% 12%, rgba(124,58,237,0.14), transparent 45%),radial-gradient(circle at 85% 88%, rgba(5,150,105,0.12), transparent 45%),radial-gradient(circle at 50% 50%, rgba(255,255,255,0.05) 1px, transparent 1.4px);background-size:auto,auto,22px 22px;"></div>
          <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;font-size:11px;color:var(--text-subtle)">
            <div style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;border-radius:50%;background:#7c3aed;display:inline-block"></span>Proceso</div>
            <div style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;border-radius:3px;background:#D65200;display:inline-block"></span>Activo IT</div>
            <div style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;clip-path:polygon(50% 0%,100% 25%,100% 75%,50% 100%,0% 75%,0% 25%);background:#059669;display:inline-block"></span>Proveedor externo</div>
            <div style="display:flex;align-items:center;gap:5px"><span style="width:12px;height:12px;border-radius:50%;border:2px solid #ef4444;display:inline-block"></span>SPOF</div>
            <div style="display:flex;align-items:center;gap:5px"><span style="display:inline-block;width:24px;height:2px;background:#ef4444"></span>Dep. critica</div>
            <div style="display:flex;align-items:center;gap:5px"><span style="display:inline-block;width:24px;height:1px;background:#6b7280;border-top:1px dashed #6b7280"></span>Dep. externa</div>
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:10px;">
          <div class="card" style="padding:12px;">
            <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px">Estadisticas</div>
            <div id="graph-stats" style="font-size:12px;color:var(--text-subtle)">Cargando...</div>
          </div>
          <div id="graph-node-detail" style="display:none"></div>
          <div id="graph-analysis" style="display:none"></div>
        </div>
      </div>
    `;

    // Poblar select de localizaciones
    Object.values(_locationMap).filter(l => !l.parent_id).forEach(loc => {
      const opt = document.createElement('option');
      opt.value = loc.id; opt.textContent = loc.name;
      if (loc.id === _locationFilter) opt.selected = true;
      container.querySelector('#graph-loc-filter').appendChild(opt);
    });

    let _cyInstance = null;

    async function loadGraph(locationId) {
      const url = locationId ? `/api/bcp/graph?location_id=${locationId}` : '/api/bcp/graph';
      const data = await Api.get(url).catch(() => ({ nodes: [], edges: [], stats: {} }));

      const showAssets    = container.querySelector('#graph-show-assets')?.checked !== false;
      const showSuppliers = container.querySelector('#graph-show-suppliers')?.checked !== false;
      const onlyCritical  = container.querySelector('#graph-only-critical')?.checked === true;

      const filteredNodes = (data.nodes || []).filter(n => {
        if (n.type === 'asset'    && !showAssets)    return false;
        if (n.type === 'supplier' && !showSuppliers) return false;
        if (onlyCritical && !['critical', 'high'].includes(n.criticality) && !n.is_spof) return false;
        return true;
      });
      const nodeIds = new Set(filteredNodes.map(n => String(n.id)));
      const filteredEdges = (data.edges || []).filter(e =>
        nodeIds.has(String(e.source)) && nodeIds.has(String(e.target))
      );

      const elements = [
        ...filteredNodes.map(n => ({ data: {
          id: String(n.id), label: n.label || n.name || String(n.id),
          type: n.type, criticality: n.criticality,
          is_spof: n.is_spof ? true : undefined,
          rto: n.rto_hours, location_name: n.location_name,
          _raw: n,
        }})),
        ...filteredEdges.map(e => ({ data: {
          id: 'e-' + e.id, source: String(e.source), target: String(e.target),
          type: e.type, label: e.label || '',
          is_critical: e.is_critical ? true : undefined,
        }})),
      ];

      const cyContainer = container.querySelector('#cy-graph');
      if (!cyContainer) return;
      cyContainer.innerHTML = '';

      if (_cyInstance) { try { _cyInstance.destroy(); } catch (_) {} }

      const showLabels = container.querySelector('#graph-show-labels')?.checked !== false;
      _cyInstance = cytoscape({
        container: cyContainer,
        elements,
        style: [
          { selector: 'node', style: {
            'label': 'data(label)',
            'font-family': 'Inter, -apple-system, sans-serif',
            'font-size': '10px', 'font-weight': 600, 'color': '#f1f5f9',
            'text-valign': 'bottom', 'text-halign': 'center',
            'text-margin-y': '8px',
            'text-background-color': '#0b0b14', 'text-background-opacity': 0.75,
            'text-background-shape': 'roundrectangle', 'text-background-padding': '3px',
            'text-max-width': '90px', 'text-wrap': 'ellipsis',
            'width': '40px', 'height': '40px',
            'border-width': '0px',
            'overlay-opacity': 0,
            'transition-property': 'border-color border-width background-color opacity',
            'transition-duration': '0.18s',
          }},
          // Proceso — esfera purpura con degradado (efecto glossy 3D)
          { selector: 'node[type="process"]', style: {
            'shape': 'ellipse',
            'background-fill': 'radial-gradient',
            'background-gradient-stop-colors': '#c4b5fd #7c3aed #4c1d95',
            'background-gradient-stop-positions': '0 55 100',
            'width': '46px', 'height': '46px',
            'border-width': '2px', 'border-color': '#a78bfa', 'border-opacity': 0.9,
          }},
          { selector: 'node[type="process"][criticality="critical"]', style: {
            'background-gradient-stop-colors': '#ddd6fe #6d28d9 #3b0764',
            'width': '58px', 'height': '58px',
            'border-width': '3px', 'border-color': '#c4b5fd',
            'font-size': '11px',
          }},
          { selector: 'node[type="process"][criticality="high"]', style: {
            'width': '52px', 'height': '52px',
          }},
          // Activo IT — rectangulo naranja con degradado
          { selector: 'node[type="asset"]', style: {
            'shape': 'roundrectangle',
            'background-fill': 'linear-gradient',
            'background-gradient-stop-colors': '#fdba74 #c2410c #7c2d12',
            'background-gradient-stop-positions': '0 55 100',
            'background-gradient-direction': 'to-bottom-right',
            'width': '42px', 'height': '34px',
            'border-width': '2px', 'border-color': '#fb923c', 'border-opacity': 0.9,
          }},
          { selector: 'node[type="asset"][criticality="critical"]', style: {
            'background-gradient-stop-colors': '#fed7aa #9a3412 #431407',
            'width': '52px', 'height': '42px',
          }},
          // Proveedor externo — hexagono verde con degradado
          { selector: 'node[type="supplier"]', style: {
            'shape': 'hexagon',
            'background-fill': 'radial-gradient',
            'background-gradient-stop-colors': '#6ee7b7 #059669 #022c22',
            'background-gradient-stop-positions': '0 55 100',
            'width': '46px', 'height': '46px',
            'border-width': '2px', 'border-color': '#34d399', 'border-opacity': 0.9,
          }},
          { selector: 'node[type="supplier"][criticality="critical"]', style: {
            'background-gradient-stop-colors': '#a7f3d0 #064e3b #022c22',
            'width': '56px', 'height': '56px',
          }},
          { selector: 'node[type="supplier"][criticality="high"]', style: {
            'width': '50px', 'height': '50px',
          }},
          // SPOF — halo rojo pulsante (glow)
          { selector: 'node[?is_spof]', style: {
            'border-width': '3px', 'border-color': '#ef4444',
            'border-style': 'double',
            'underlay-color': '#ef4444', 'underlay-opacity': 0.35,
            'underlay-padding': '7px', 'underlay-shape': 'ellipse',
          }},
          // Criticidad critica — halo ambar sutil
          { selector: 'node[criticality="critical"]', style: {
            'underlay-color': '#fbbf24', 'underlay-opacity': 0.18, 'underlay-padding': '5px',
          }},
          // Nodo seleccionado
          { selector: 'node:selected', style: {
            'border-width': '3px', 'border-color': '#fbbf24', 'border-style': 'solid',
            'underlay-color': '#fbbf24', 'underlay-opacity': 0.3, 'underlay-padding': '8px',
          }},
          // Dim — atenuado al hacer hover sobre otro nodo
          { selector: 'node.bcm-dim, edge.bcm-dim', style: { 'opacity': 0.15 } },
          { selector: 'node.bcm-focus', style: { 'z-index': 999 } },
          { selector: 'edge.bcm-focus', style: { 'opacity': 1, 'z-index': 998 } },
          // Aristas base — curva suave con sombra de profundidad
          { selector: 'edge', style: {
            'width': '1.6px', 'line-color': '#64748b',
            'target-arrow-shape': 'triangle', 'target-arrow-color': '#64748b',
            'arrow-scale': 1.1,
            'curve-style': 'unbundled-bezier', 'control-point-distances': 18, 'control-point-weights': 0.5,
            'font-size': '9px', 'font-family': 'Inter, sans-serif', 'color': '#cbd5e1',
            'label': showLabels ? 'data(label)' : '',
            'text-rotation': 'autorotate',
            'text-background-color': '#0b0b14', 'text-background-opacity': 0.75,
            'text-background-shape': 'roundrectangle', 'text-background-padding': '2px',
            'opacity': 0.85,
            'transition-property': 'line-color width opacity',
            'transition-duration': '0.18s',
          }},
          // Dependencia critica — rojo con mas grosor
          { selector: 'edge[?is_critical]', style: {
            'line-color': '#ef4444', 'target-arrow-color': '#ef4444',
            'width': '2.6px', 'opacity': 0.95,
          }},
          // Proveedor externo — discontinua azul
          { selector: 'edge[?is_external]', style: {
            'line-style': 'dashed', 'line-dash-pattern': [6, 4],
            'line-color': '#3b82f6', 'target-arrow-color': '#3b82f6',
            'width': '1.6px',
          }},
          // Dependencia critica externa (supplier critico)
          { selector: 'edge[?is_critical][?is_external]', style: {
            'line-color': '#f97316', 'target-arrow-color': '#f97316',
            'width': '2.6px',
          }},
        ],
        layout: {
          name: 'cose',
          animate: true, animationDuration: 700,
          nodeDimensionsIncludeLabels: true,
          nodeRepulsion: 9000, edgeElasticity: 110, gravity: 0.25,
          numIter: 1200, coolingFactor: 0.98, idealEdgeLength: 90,
        },
        wheelSensitivity: 0.3,
      });

      // Tooltip flotante al pasar el cursor sobre un nodo
      let tooltipEl = cyContainer.parentElement.querySelector('.bcm-graph-tooltip');
      if (!tooltipEl) {
        tooltipEl = document.createElement('div');
        tooltipEl.className = 'bcm-graph-tooltip';
        tooltipEl.style.cssText = 'position:absolute;display:none;pointer-events:none;z-index:50;'
          + 'background:rgba(15,15,26,0.96);border:1px solid rgba(167,139,250,0.4);border-radius:8px;'
          + 'padding:8px 10px;font-size:11px;color:#e2e8f0;max-width:220px;box-shadow:0 6px 20px rgba(0,0,0,0.45);'
          + 'backdrop-filter:blur(4px);line-height:1.5;';
        cyContainer.appendChild(tooltipEl);
      }
      const typeLabelsTip = { process: 'Proceso de negocio', asset: 'Activo IT', supplier: 'Proveedor externo' };
      const typeColorsTip = { process: '#a78bfa', asset: '#fb923c', supplier: '#34d399' };

      _cyInstance.on('mouseover', 'node', evt => {
        const node = evt.target;
        const raw = node.data('_raw') || {};
        const neighborhood = node.closedNeighborhood();
        _cyInstance.elements().not(neighborhood).addClass('bcm-dim');
        neighborhood.addClass('bcm-focus');

        const critColor = CRIT_COLORS[raw.criticality] || '#94a3b8';
        tooltipEl.innerHTML = `
          <div style="font-weight:700;font-size:12px;color:${typeColorsTip[raw.type] || '#fff'};margin-bottom:3px">${UI.esc(raw.label || raw.name || '')}</div>
          <div style="color:#94a3b8;font-size:10px;text-transform:uppercase;letter-spacing:.03em;margin-bottom:5px">${typeLabelsTip[raw.type] || raw.type}</div>
          <div>Criticidad: <strong style="color:${critColor}">${UI.esc(raw.criticality || '—')}</strong></div>
          ${raw.rto_hours != null ? `<div>RTO: <strong>${raw.rto_hours}h</strong></div>` : ''}
          ${raw.rpo_hours != null ? `<div>RPO: <strong>${raw.rpo_hours}h</strong></div>` : ''}
          ${raw.location_name ? `<div>Sede: <strong>${UI.esc(raw.location_name)}</strong></div>` : ''}
          ${raw.is_spof ? `<div style="color:#f87171;font-weight:700;margin-top:3px"><i class="ti ti-alert-triangle"></i> Punto unico de fallo</div>` : ''}
          <div style="color:#64748b;font-size:10px;margin-top:5px">Clic para ver detalle completo</div>
        `;
        tooltipEl.style.display = 'block';
      });
      _cyInstance.on('mousemove', evt => {
        if (tooltipEl.style.display !== 'block') return;
        const pos = evt.renderedPosition || (evt.target.renderedPosition ? evt.target.renderedPosition() : null);
        if (!pos) return;
        let left = pos.x + 16, top = pos.y + 12;
        if (left + 230 > cyContainer.clientWidth) left = pos.x - 236;
        if (top + 140 > cyContainer.clientHeight) top = pos.y - 140;
        tooltipEl.style.left = left + 'px';
        tooltipEl.style.top = top + 'px';
      });
      _cyInstance.on('mouseout', 'node', () => {
        _cyInstance.elements().removeClass('bcm-dim bcm-focus');
        tooltipEl.style.display = 'none';
      });
      _cyInstance.on('mouseover', 'edge', evt => {
        const edge = evt.target;
        _cyInstance.elements().not(edge.connectedNodes().union(edge)).addClass('bcm-dim');
        edge.addClass('bcm-focus');
      });
      _cyInstance.on('mouseout', 'edge', () => {
        _cyInstance.elements().removeClass('bcm-dim bcm-focus');
      });

      // Clic en nodo → panel de detalle enriquecido
      _cyInstance.on('tap', 'node', evt => {
        const raw = evt.target.data('_raw') || {};
        const detail = container.querySelector('#graph-node-detail');
        if (!detail) return;
        detail.style.display = 'block';
        const typeLabels  = { process: 'Proceso de negocio', asset: 'Activo IT', supplier: 'Proveedor externo' };
        const typeColors  = { process: '#7c3aed', asset: '#c2410c', supplier: '#059669' };
        const critColor   = CRIT_COLORS[raw.criticality] || '#6b7280';
        const plans       = raw.plans || [];

        let extraHtml = '';
        if (raw.type === 'process') {
          extraHtml = `
            ${raw.rto_hours   != null ? `<div>RTO: <strong>${raw.rto_hours}h</strong></div>` : ''}
            ${raw.rpo_hours   != null ? `<div>RPO: <strong>${raw.rpo_hours}h</strong></div>` : ''}
            ${raw.mtpd_hours  != null ? `<div>MTPD: <strong>${raw.mtpd_hours}h</strong></div>` : ''}
            ${raw.cost_per_hour != null ? `<div>Coste/h: <strong>${parseFloat(raw.cost_per_hour).toLocaleString('es-ES')} €</strong></div>` : ''}
            ${raw.location_name ? `<div>Sede: <strong>${UI.esc(raw.location_name)}</strong></div>` : ''}
            ${plans.length ? `<div style="margin-top:6px;padding-top:6px;border-top:1px solid var(--border)">
              <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:3px">Planes asociados</div>
              ${plans.map(pl => `<span class="badge badge-secondary" style="font-size:10px;margin:1px 2px">${UI.esc(pl.code||pl.type)}</span>`).join('')}
            </div>` : ''}
          `;
        } else if (raw.type === 'supplier') {
          extraHtml = `
            ${raw.contract_sla_hours != null ? `<div>SLA contrato: <strong>${raw.contract_sla_hours}h</strong></div>` : ''}
            ${raw.rto_impact_hours  != null ? `<div>Impacto RTO: <strong>${raw.rto_impact_hours}h</strong></div>` : ''}
            <div>Plan contingencia: <strong>${raw.has_contingency ? 'Si' : 'No'}</strong></div>
          `;
        }

        detail.innerHTML = `<div class="card" style="padding:12px;border-left:3px solid ${typeColors[raw.type]||'var(--primary)'}">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:${typeColors[raw.type]||'var(--text-subtle)'};margin-bottom:6px">
            ${typeLabels[raw.type] || raw.type}
          </div>
          <div style="font-size:14px;font-weight:700;margin-bottom:8px;line-height:1.3">${UI.esc(raw.label || raw.name || '')}</div>
          <div style="font-size:12px;display:grid;gap:4px;color:var(--text-subtle)">
            <div>Criticidad: <strong style="color:${critColor}">${UI.esc(raw.criticality || '—')}</strong></div>
            ${extraHtml}
            ${raw.is_spof ? `<div style="margin-top:6px;padding:5px 8px;background:#fee2e2;border-radius:4px;color:#b91c1c;font-weight:700;font-size:11px">
              Punto unico de fallo (SPOF) — 3+ dependencias entrantes
            </div>` : ''}
          </div>
          <div style="display:flex;gap:4px;flex-wrap:wrap;margin-top:8px">
            ${raw.type === 'process' ? `<button class="btn btn-ghost btn-sm" style="font-size:11px"
              onclick="ViewBcp._switchTab('processes')"><i class="ti ti-external-link"></i> Ver proceso</button>` : ''}
            ${raw.type === 'supplier' ? `<button class="btn btn-ghost btn-sm" style="font-size:11px"
              onclick="ViewBcp._setSubTab(3,'suppliers')"><i class="ti ti-external-link"></i> Ver proveedor</button>` : ''}
          </div>
        </div>`;
      });

      // Clic en fondo → deseleccionar
      _cyInstance.on('tap', evt => {
        if (evt.target === _cyInstance) {
          const detail = container.querySelector('#graph-node-detail');
          if (detail) detail.style.display = 'none';
        }
      });

      // Estadísticas
      const stats = data.stats || {};
      const statsEl = container.querySelector('#graph-stats');
      if (statsEl) statsEl.innerHTML = `
        <div>${filteredNodes.length} nodos · ${filteredEdges.length} aristas</div>
        <div style="color:${(stats.spof_count || 0) > 0 ? 'var(--risk-critical)' : 'inherit'}">
          ${stats.spof_count || 0} SPOF${(stats.spof_count || 0) !== 1 ? 's' : ''}
        </div>`;
    }

    await loadGraph(_locationFilter);

    const getLocId = () => {
      const v = container.querySelector('#graph-loc-filter').value;
      return v ? parseInt(v) : (_locationFilter || null);
    };

    container.querySelector('#graph-loc-filter').onchange = async e => {
      await loadGraph(e.target.value ? parseInt(e.target.value) : null);
    };
    container.querySelector('#graph-show-assets').onchange    = () => loadGraph(getLocId());
    container.querySelector('#graph-show-suppliers').onchange = () => loadGraph(getLocId());
    container.querySelector('#graph-only-critical').onchange  = () => loadGraph(getLocId());
    container.querySelector('#graph-show-labels').onchange    = () => loadGraph(getLocId());

    container.querySelector('#btn-graph-zoom-in').onclick  = () => _cyInstance?.zoom({ level: (_cyInstance.zoom() || 1) * 1.25, renderedPosition: { x: _cyInstance.width()/2, y: _cyInstance.height()/2 } });
    container.querySelector('#btn-graph-zoom-out').onclick = () => _cyInstance?.zoom({ level: (_cyInstance.zoom() || 1) * 0.8,  renderedPosition: { x: _cyInstance.width()/2, y: _cyInstance.height()/2 } });
    container.querySelector('#btn-graph-fit').onclick      = () => _cyInstance?.fit(undefined, 30);
    container.querySelector('#btn-graph-export').onclick   = () => {
      if (!_cyInstance) return;
      const png = _cyInstance.png({ full: true, scale: 2, bg: '#0f0f1a' });
      const a = document.createElement('a');
      a.href = png; a.download = 'mapa-dependencias-bcm.png'; a.click();
    };

    container.querySelector('#btn-analyze-graph').onclick = async () => {
      const btn = container.querySelector('#btn-analyze-graph');
      btn.disabled = true;
      btn.innerHTML = '<i class="ti ti-loader-2 ti-spin"></i> Analizando...';
      const locId = container.querySelector('#graph-loc-filter').value;
      try {
        const url = locId ? `/api/bcp/graph/analyze?location_id=${locId}` : '/api/bcp/graph/analyze';
        const res = await Api.post(url, {});
        const div = container.querySelector('#graph-analysis');
        div.style.display = 'block';
        div.innerHTML = `<div class="card" style="padding:12px;margin-top:8px">
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:6px"><i class="ti ti-brain"></i> Análisis IA</div>
          <div style="font-size:12px;line-height:1.6;white-space:pre-wrap">${UI.esc(res.analysis || '')}</div>
        </div>`;
      } catch (e) { UI.toast('Error en análisis IA: ' + (e.message || e), 'error'); }
      finally { btn.disabled = false; btn.innerHTML = '<i class="ti ti-brain"></i> Analizar con IA'; }
    };
  }

  // ── Tab Evidencias ────────────────────────────────────────────────────────────

  async function _tabEvidence(container) {
    // Carga datos en paralelo
    const [evidence, plans, tests, processes] = await Promise.all([
      Api.get('/api/bcp/evidence' + _locParam()).catch(() => []),
      Api.get('/api/bcp/plans' + _locParam()).catch(() => []),
      Api.get('/api/bcp/tests' + _locParam()).catch(() => []),
      Api.get('/api/bcp/processes' + _locParam()).catch(() => []),
    ]);

    const planMap = {}; plans.forEach(p => { planMap[p.id] = p; });
    const testMap = {}; tests.forEach(t => { testMap[t.id] = t; });
    const procMap = {}; processes.forEach(p => { procMap[p.id] = p; });

    const evTypeLabels = {
      test_report: 'Informe test', plan_approval: 'Aprob. plan',
      bcp_activation: 'Activacion BCP', audit_report: 'Informe auditoria',
      backup_validation: 'Valid. backup', training_record: 'Formacion',
      supplier_cert: 'Cert. proveedor', screenshot: 'Captura', other: 'Otro',
    };

    function _buildLinkedName(e) {
      if (e.linked_test_id && testMap[e.linked_test_id])
        return `Test: ${testMap[e.linked_test_id].name || ('#' + e.linked_test_id)}`;
      if (e.linked_plan_id && planMap[e.linked_plan_id])
        return `Plan: ${planMap[e.linked_plan_id].name || ('#' + e.linked_plan_id)}`;
      if (e.linked_process_id && procMap[e.linked_process_id])
        return `Proc: ${procMap[e.linked_process_id].name || ('#' + e.linked_process_id)}`;
      return '—';
    }

    container.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h3 style="margin:0;font-size:16px">Repositorio de evidencias BCM</h3>
        <button class="btn btn-primary btn-sm" id="btn-upload-evidence">
          <i class="ti ti-upload"></i> Subir evidencia
        </button>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
        <select id="ev-filter-type" class="form-control" style="width:160px;font-size:12px">
          <option value="">Tipo de evidencia</option>
          ${Object.entries(evTypeLabels).map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}
        </select>
        <select id="ev-filter-loc" class="form-control" style="width:160px;font-size:12px">
          <option value="">Localización</option>
          ${Object.values(_locationMap).map(l => `<option value="${l.id}">${UI.esc(l.name)}</option>`).join('')}
        </select>
        <select id="ev-filter-linked" class="form-control" style="width:160px;font-size:12px">
          <option value="">Vinculado a</option>
          <option value="plan">Plan</option>
          <option value="test">Test</option>
          <option value="process">Proceso</option>
        </select>
        <button class="btn btn-ghost btn-sm" id="btn-ev-filter">Filtrar</button>
        <button class="btn btn-ghost btn-sm" id="btn-ev-clear">Limpiar</button>
      </div>
      <div id="ev-table-wrap">
        ${_buildEvidenceTable(evidence, planMap, testMap, procMap, evTypeLabels, _buildLinkedName)}
      </div>
    `;

    container.querySelector('#btn-upload-evidence').onclick = () =>
      _modalUploadEvidence(plans, tests, processes, () => _switchTab('evidence'));

    function applyFilter() {
      const type = container.querySelector('#ev-filter-type').value;
      const locId = container.querySelector('#ev-filter-loc').value;
      const linked = container.querySelector('#ev-filter-linked').value;
      let filtered = evidence;
      if (type) filtered = filtered.filter(e => e.evidence_type === type);
      if (locId) filtered = filtered.filter(e => String(e.location_id) === locId);
      if (linked === 'plan') filtered = filtered.filter(e => e.linked_plan_id);
      else if (linked === 'test') filtered = filtered.filter(e => e.linked_test_id);
      else if (linked === 'process') filtered = filtered.filter(e => e.linked_process_id);
      container.querySelector('#ev-table-wrap').innerHTML =
        _buildEvidenceTable(filtered, planMap, testMap, procMap, evTypeLabels, _buildLinkedName);
    }

    container.querySelector('#btn-ev-filter').onclick = applyFilter;
    container.querySelector('#btn-ev-clear').onclick = () => {
      ['#ev-filter-type', '#ev-filter-loc', '#ev-filter-linked'].forEach(id => {
        const el = container.querySelector(id);
        if (el) el.value = '';
      });
      applyFilter();
    };
  }

  function _buildEvidenceTable(evidence, planMap, testMap, procMap, evTypeLabels, _buildLinkedName) {
    if (!evidence.length)
      return `<div class="notice notice-info">Sin evidencias. Sube actas de tests, aprobaciones de planes o informes de auditoria.</div>`;
    return `<div class="table-wrap"><table class="data">
      <thead><tr>
        <th>Tipo</th><th>Titulo</th><th>Localizacion</th>
        <th>Vinculada a</th><th>Integridad</th><th>Fecha</th><th></th>
      </tr></thead>
      <tbody>
        ${evidence.map(e => `<tr>
          <td><span class="badge badge-muted" style="font-size:10px">${UI.esc(evTypeLabels[e.evidence_type] || e.evidence_type)}</span></td>
          <td>
            <strong>${UI.esc(e.title)}</strong>
            ${e.file_name ? `<br><small style="color:var(--text-subtle)">${UI.esc(e.file_name)}</small>` : ''}
            ${e.tags ? `<br><span style="font-size:10px;color:var(--text-subtle)">${UI.esc(e.tags)}</span>` : ''}
          </td>
          <td style="font-size:12px">${UI.esc(_locationMap[e.location_id]?.name || '—')}</td>
          <td style="font-size:12px">${UI.esc(_buildLinkedName(e))}</td>
          <td>
            <span title="SHA-256: ${UI.esc(e.sha256_hash || '')}" style="font-size:10px;font-family:monospace;color:var(--text-subtle)">
              ${e.sha256_hash ? '&#10003; ' + e.sha256_hash.slice(0, 8) + '...' : '—'}
            </span>
          </td>
          <td style="font-size:12px">${e.created_at ? e.created_at.slice(0, 10) : '—'}</td>
          <td>
            <a href="/api/bcp/evidence/${e.id}/download" class="btn btn-ghost btn-sm" title="Descargar" target="_blank">
              <i class="ti ti-download"></i>
            </a>
          </td>
        </tr>`).join('')}
      </tbody>
    </table></div>`;
  }

  function _modalUploadEvidence(plans, tests, processes, onSuccess) {
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
      <div class="modal-box" style="max-width:520px">
        <div class="modal-header">
          <h3>Subir evidencia BCM</h3>
          <button onclick="this.closest('.modal-bg').remove()" class="btn-icon"><i class="ti ti-x"></i></button>
        </div>
        <div class="modal-body" style="display:flex;flex-direction:column;gap:10px">
          <div><label>Titulo *</label>
            <input id="ev-title" class="form-control" placeholder="Acta ejercicio tabletop Q1-2025">
          </div>
          <div><label>Tipo *</label>
            <select id="ev-type" class="form-control">
              <option value="test_report">Informe de test</option>
              <option value="plan_approval">Aprobacion de plan</option>
              <option value="bcp_activation">Activacion BCP real</option>
              <option value="audit_report">Informe de auditoria</option>
              <option value="backup_validation">Validacion de backup</option>
              <option value="training_record">Registro de formacion</option>
              <option value="supplier_cert">Certificacion proveedor</option>
              <option value="screenshot">Captura de pantalla</option>
              <option value="other">Otro</option>
            </select>
          </div>
          <div><label>Localizacion</label>
            <select id="ev-location" class="form-control">
              <option value="">Sin localización</option>
              ${Object.values(_locationMap).map(l => `<option value="${l.id}">${UI.esc(l.name)}</option>`).join('')}
            </select>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
            <div><label>Test vinculado</label>
              <select id="ev-test" class="form-control">
                <option value="">—</option>
                ${(tests || []).map(t => `<option value="${t.id}">${UI.esc(t.name || t.test_type || ('#' + t.id))}</option>`).join('')}
              </select>
            </div>
            <div><label>Plan vinculado</label>
              <select id="ev-plan" class="form-control">
                <option value="">—</option>
                ${(plans || []).map(p => `<option value="${p.id}">${UI.esc(p.name || ('#' + p.id))}</option>`).join('')}
              </select>
            </div>
          </div>
          <div><label>Proceso vinculado</label>
            <select id="ev-process" class="form-control">
              <option value="">—</option>
              ${(processes || []).map(p => `<option value="${p.id}">${UI.esc(p.name || ('#' + p.id))}</option>`).join('')}
            </select>
          </div>
          <div><label>Descripcion</label>
            <textarea id="ev-desc" class="form-control" rows="2" placeholder="Contexto o notas relevantes..."></textarea>
          </div>
          <div><label>Etiquetas (separadas por coma)</label>
            <input id="ev-tags" class="form-control" placeholder="iso22301, ejercicio, q1">
          </div>
          <div><label>Archivo *</label>
            <input id="ev-file" type="file" class="form-control">
          </div>
          <div style="display:flex;gap:8px;margin-top:4px">
            <button class="btn btn-primary" id="btn-save-ev">Subir</button>
            <button class="btn btn-secondary" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);

    modal.querySelector('#btn-save-ev').onclick = async () => {
      const title = modal.querySelector('#ev-title').value.trim();
      const file = modal.querySelector('#ev-file').files[0];
      if (!title || !file) return UI.toast('Titulo y archivo son obligatorios', 'error');
      const fd = new FormData();
      fd.append('file', file);
      const params = new URLSearchParams({ title, evidence_type: modal.querySelector('#ev-type').value });
      const desc = modal.querySelector('#ev-desc').value.trim();
      if (desc) params.set('description', desc);
      const tags = modal.querySelector('#ev-tags').value.trim();
      if (tags) params.set('tags', tags);
      const locId = modal.querySelector('#ev-location').value;
      if (locId) params.set('location_id', locId);
      const testId = modal.querySelector('#ev-test').value;
      if (testId) params.set('linked_test_id', testId);
      const planId = modal.querySelector('#ev-plan').value;
      if (planId) params.set('linked_plan_id', planId);
      const procId = modal.querySelector('#ev-process').value;
      if (procId) params.set('linked_process_id', procId);
      try {
        await fetch(`/api/bcp/evidence?${params}`, {
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + Api.token() },
          body: fd,
        });
        modal.remove();
        UI.toast('Evidencia subida correctamente', 'success');
        if (onSuccess) onSuccess();
      } catch (e) { UI.toast('Error al subir la evidencia', 'error'); }
    };
  }

  // ── Tab Recomendaciones IA ────────────────────────────────────────────────────

  async function _tabRecommendations(container) {
    const pColors = {
      critical: 'var(--risk-critical)', high: 'var(--risk-high)',
      medium: 'var(--risk-medium)', low: 'var(--risk-low)',
    };
    const triggerLabels = {
      plan_approved: 'Plan aprobado', overdue_12m: 'Sin test >12m',
      never_tested: 'Nunca testado', incident: 'Incidente reciente',
      test_failed: 'Test fallido', regulatory: 'Requisito normativo',
    };

    const [recs, plans, assets] = await Promise.all([
      Api.get('/api/bcp/test-recommendations?status=pending' + _locParam('&')).catch(() => []),
      Api.get('/api/bcp/plans' + _locParam()).catch(() => []),
      Api.get('/api/assets/?limit=200').then(d => d.items || d || []).catch(() => []),
    ]);

    container.innerHTML = `
      <div style="display:grid;grid-template-columns:65% 35%;gap:16px;align-items:start">
        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
            <div>
              <h3 style="margin:0;font-size:16px">Tests recomendados por IA</h3>
              <p style="margin:4px 0 0;font-size:12px;color:var(--text-subtle)">
                ISO 22301 cl. 8.5 — <span id="rec-count">${recs.length}</span> recomendacion(es) pendiente(s)
              </p>
            </div>
            <button class="btn btn-primary btn-sm" id="btn-gen-recs">
              <i class="ti ti-refresh"></i> Regenerar
            </button>
          </div>
          <div id="recs-list">
            ${_buildRecsList(recs, pColors, triggerLabels)}
          </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:12px">
          <div class="card" style="padding:14px">
            <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:10px">
              Buscar tests ad-hoc
            </div>
            <div style="display:flex;flex-direction:column;gap:8px">
              <div>
                <label style="font-size:12px">Tipo de plan</label>
                <select id="filter-plan-type" class="form-control" style="font-size:12px">
                  <option value="">Todos</option>
                  ${['bcp','drp','communication','crisis_management','cyber_response'].map(t =>
                    `<option value="${t}">${t}</option>`).join('')}
                </select>
              </div>
              <div>
                <label style="font-size:12px">Activo</label>
                <select id="filter-asset" class="form-control" style="font-size:12px">
                  <option value="">Todos</option>
                  ${assets.map(a => `<option value="${a.id}">${UI.esc((a.code ? a.code + ' — ' : '') + a.name)}</option>`).join('')}
                </select>
              </div>
              <div>
                <label style="font-size:12px">Localizaciones</label>
                <select id="filter-locs" class="form-control" style="font-size:12px" multiple size="4">
                  ${Object.values(_locationMap).map(l =>
                    `<option value="${l.id}"${l.id === _locationFilter ? ' selected' : ''}>${UI.esc(l.name)}</option>`
                  ).join('')}
                </select>
                <div style="font-size:10px;color:var(--text-subtle);margin-top:2px">Ctrl+clic para multiple seleccion</div>
              </div>
              <button class="btn btn-secondary btn-sm" id="btn-apply-filter">
                <i class="ti ti-search"></i> Buscar tests
              </button>
            </div>
          </div>
          <div id="filter-results" style="display:none"></div>
        </div>
      </div>
    `;

    function _buildRecsList(recList, pc, tl) {
      if (!recList.length)
        return `<div class="notice notice-info">Sin recomendaciones pendientes. Pulsa "Regenerar" para analizar el estado actual.</div>`;
      return recList.map(r => {
        const isBiaAlert = r.recommended_test_type === 'bia_incomplete';
        const borderColor = isBiaAlert ? '#D97706' : (pc[r.priority] || 'var(--border)');
        const typeLabel = isBiaAlert ? 'BIA incompleto' : (r.recommended_test_type || r.test_type || '');
        return `
        <div class="card" style="padding:14px;margin-bottom:8px;border-left:3px solid ${borderColor}">
          <div style="display:flex;justify-content:space-between;align-items:flex-start">
            <div style="flex:1">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap">
                <span class="badge" style="background:${borderColor}22;color:${borderColor};font-size:10px">${UI.esc(r.priority || 'medium')}</span>
                ${isBiaAlert
                  ? `<span style="font-size:11px;background:#D9770622;color:#D97706;padding:1px 6px;border-radius:4px;font-weight:700;">BIA</span>`
                  : `<code style="font-size:11px">${UI.esc(typeLabel)}</code>`}
                <span style="font-size:11px;color:var(--text-subtle)">${UI.esc(tl[r.trigger] || r.trigger || '')}</span>
              </div>
              <p style="margin:0;font-size:13px;line-height:1.5">${UI.esc(r.reason || '')}</p>
              ${r.process_name ? `<p style="margin:4px 0 0;font-size:11px;color:var(--text-subtle)"><i class="ti ti-sitemap" style="font-size:10px;"></i> Proceso: <strong>${UI.esc(r.process_name)}</strong></p>` : ''}
              ${r.plan_name ? `<p style="margin:4px 0 0;font-size:11px;color:var(--text-subtle)">Plan: ${UI.esc(r.plan_name)}</p>` : ''}
              ${r.recommended_date ? `<p style="margin:2px 0 0;font-size:11px;color:var(--text-subtle)">Fecha sugerida: ${r.recommended_date.slice(0, 10)}</p>` : ''}
            </div>
            <div style="display:flex;gap:6px;margin-left:12px;flex-shrink:0">
              ${isBiaAlert && r.process_id
                ? `<button class="btn btn-primary btn-sm" data-rec-bia="${r.id}" data-proc-id="${r.process_id}">
                    <i class="ti ti-pencil"></i> Completar BIA
                   </button>`
                : `<button class="btn btn-primary btn-sm" data-rec-accept="${r.id}"
                    data-plan-id="${r.plan_id || ''}" data-test-type="${UI.esc(r.recommended_test_type || '')}"
                    data-rec-date="${r.recommended_date || ''}">
                    <i class="ti ti-check"></i> Aceptar
                   </button>`}
              <button class="btn btn-ghost btn-sm" data-rec-dismiss="${r.id}" title="Descartar">
                <i class="ti ti-x"></i>
              </button>
            </div>
          </div>
        </div>`;
      }).join('');
    }

    function bindRecButtons() {
      container.querySelectorAll('[data-rec-bia]').forEach(btn => {
        btn.onclick = async () => {
          const recId = btn.dataset.recBia;
          const procId = parseInt(btn.dataset.procId);
          await Api.patch(`/api/bcp/test-recommendations/${recId}`, { status: 'accepted' }).catch(() => {});
          _editProc(procId);
        };
      });
      container.querySelectorAll('[data-rec-accept]').forEach(btn => {
        btn.onclick = async () => {
          const recId = btn.dataset.recAccept;
          const planId = btn.dataset.planId;
          const testType = btn.dataset.testType;
          const recDate = btn.dataset.recDate;
          await Api.patch(`/api/bcp/test-recommendations/${recId}`, { status: 'accepted' }).catch(() => {});
          // Abrir modal de test pre-relleno
          _openTestModal(null, {
            plan_id: planId ? parseInt(planId) : undefined,
            test_type: testType || undefined,
            scheduled_date: recDate ? recDate.slice(0, 10) : undefined,
          });
        };
      });
      container.querySelectorAll('[data-rec-dismiss]').forEach(btn => {
        btn.onclick = async () => {
          if (!confirm('Descartar esta recomendacion?')) return;
          await Api.patch(`/api/bcp/test-recommendations/${btn.dataset.recDismiss}`, { status: 'dismissed' });
          const recId = parseInt(btn.dataset.recDismiss);
          const updatedRecs = recs.filter(r => r.id !== recId);
          container.querySelector('#recs-list').innerHTML = _buildRecsList(updatedRecs, pColors, triggerLabels);
          const cnt = container.querySelector('#rec-count');
          if (cnt) cnt.textContent = updatedRecs.length;
          bindRecButtons();
        };
      });
    }

    bindRecButtons();

    container.querySelector('#btn-gen-recs').onclick = async () => {
      const btn = container.querySelector('#btn-gen-recs');
      btn.disabled = true;
      btn.innerHTML = '<i class="ti ti-loader-2 ti-spin"></i>';
      try {
        await Api.post('/api/bcp/test-recommendations/generate', {});
        UI.toast('Recomendaciones regeneradas', 'success');
        _switchTab('recommendations');
      } catch (e) { UI.toast('Error al regenerar', 'error'); }
      finally { btn.disabled = false; btn.innerHTML = '<i class="ti ti-refresh"></i> Regenerar'; }
    };

    container.querySelector('#btn-apply-filter').onclick = async () => {
      const pt = container.querySelector('#filter-plan-type').value;
      const aid = container.querySelector('#filter-asset').value;
      const locsEl = container.querySelector('#filter-locs');
      const locIds = locsEl ? Array.from(locsEl.selectedOptions).map(o => o.value) : [];
      const params = new URLSearchParams();
      if (pt) params.set('plan_type', pt);
      if (aid) params.set('asset_id', aid);
      locIds.forEach(id => params.append('location_id', id));
      const results = await Api.get(`/api/bcp/tests/filter?${params}`).catch(() => []);
      const div = container.querySelector('#filter-results');
      div.style.display = 'block';
      if (!results.length) {
        div.innerHTML = `<div class="notice notice-info">Sin tests con esos filtros.</div>`;
        return;
      }
      div.innerHTML = `<div class="card" style="padding:12px">
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px">
          ${results.length} test(s) encontrado(s)
        </div>
        ${results.map(r => `<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:12px">
          <strong>${UI.esc(r.plan_name || r.name || ('#' + r.id))}</strong>
          <span class="badge badge-muted" style="margin-left:6px;font-size:10px">${UI.esc(r.plan_type || r.test_type || '')}</span>
          ${r.scheduled_date ? `<div style="color:var(--text-subtle);font-size:11px">${r.scheduled_date.slice(0, 10)}</div>` : ''}
        </div>`).join('')}
      </div>`;
    };
  }



  // ── Config mode: stepper ─────────────────────────────────────────────────────

  async function _renderConfigMode(content) {
    const steps = [
      { n:1, label:'Localizaciones', icon:'ti-map-pin' },
      { n:2, label:'Procesos & BIA', icon:'ti-sitemap' },
      { n:3, label:'Dependencias',   icon:'ti-link' },
      { n:4, label:'Planes & DRP',   icon:'ti-file-text' },
      { n:5, label:'Documentacion',  icon:'ti-files' },
    ];
    let stepperHtml = '<div class="bcm-stepper-wrap">';
    steps.forEach((s, i) => {
      const cls = 'bcm-step' + (_currentStep > s.n ? ' done' : '') + (_currentStep === s.n ? ' active' : '');
      const numHtml = _currentStep > s.n ? '<i class="ti ti-check" style="font-size:10px"></i>' : s.n;
      stepperHtml += '<div class="' + cls + '" onclick="ViewBcp._setStep(' + s.n + ')">';
      stepperHtml += '<div class="bcm-step-num">' + numHtml + '</div>';
      stepperHtml += '<div class="bcm-step-label"><i class="ti ' + s.icon + '"></i> ' + s.label + '</div>';
      stepperHtml += '</div>';
      if (i < steps.length - 1) {
        stepperHtml += '<div class="bcm-step-connector' + (_currentStep > s.n ? ' done' : '') + '"></div>';
      }
    });
    stepperHtml += '</div>';
    content.innerHTML = stepperHtml + '<div id="bcm-step-body" class="bcm-step-body"></div>';
    const body = content.querySelector('#bcm-step-body');
    switch (_currentStep) {
      case 1: await _tabLocations(body); break;
      case 2: await _stepProcesosBIA(body); break;
      case 3: await _stepDependencias(body); break;
      case 4: await _stepPlanesDRP(body); break;
      case 5: await _stepDocumentacion(body); break;
    }
  }

  // ── Operar mode: tiles ────────────────────────────────────────────────────────

  async function _renderOperarMode(content) {
    const tiles = [
      { id:'dashboard',     label:'Dashboard ISO 22301', icon:'ti-chart-dots-3',   color:'var(--primary)',   sub:'Score global · clausulas' },
      { id:'graph',         label:'Mapa Dependencias',   icon:'ti-topology-full',  color:'#D65200',          sub:'SPOFs · grafo interactivo' },
      { id:'tests',         label:'Tests & Evidencias',  icon:'ti-clipboard-check',color:'#16a34a',          sub:'Calendario · ejercicios' },
      { id:'alertas',       label:'Alertas & Rec. IA',   icon:'ti-bell-ringing',   color:'#2563EB',          sub:'Vencimientos · rec. IA' },
      { id:'activaciones',  label:'Activar BCP',         icon:'ti-alert-triangle', color:'#DC2626',          sub:'Emergencia · historial' },
    ];
    // Badge de activacion activa
    const activeAct = await Api.get('/api/bcp/activations').catch(() => []).then(list => list.find(a => !a.closed_at));
    let tilesHtml = '<div class="bcm-tiles-grid" style="grid-template-columns:repeat(5,1fr)">';
    tiles.forEach(t => {
      const activeCls = _currentTile === t.id ? ' active' : '';
      const isActTile = t.id === 'activaciones';
      const pulseDot = (isActTile && activeAct)
        ? '<span class="bcm-act-pulse-dot"></span>'
        : '';
      tilesHtml += '<div class="bcm-tile' + activeCls + (isActTile ? ' bcm-tile-danger' : '') + '" onclick="ViewBcp._setTile(\'' + t.id + '\')">';
      tilesHtml += '<div class="bcm-tile-icon" style="background:' + t.color + '18;position:relative">';
      tilesHtml += '<i class="ti ' + t.icon + '" style="color:' + t.color + ';font-size:22px"></i>';
      tilesHtml += pulseDot;
      tilesHtml += '</div>';
      tilesHtml += '<div class="bcm-tile-label">' + t.label + '</div>';
      tilesHtml += '<div class="bcm-tile-sub">' + t.sub + '</div>';
      tilesHtml += '</div>';
    });
    tilesHtml += '</div>';
    content.innerHTML = tilesHtml + '<div id="bcm-tile-body" class="bcm-tile-body"></div>';
    const body = content.querySelector('#bcm-tile-body');
    switch (_currentTile) {
      case 'dashboard':    await _tileDashboard(body); break;
      case 'graph':        await _tabGraph(body); break;
      case 'tests':        await _stepTests(body); break;
      case 'alertas':      await _stepAlertas(body); break;
      case 'activaciones': await _tileActivaciones(body, activeAct); break;
    }
  }

  // ── Step wrappers (sub-tabs within each config step) ─────────────────────────

  function _buildSubTabs(stepN, tabs, body, renderFn) {
    const active = _currentSubTabs[stepN] || tabs[0].id;
    let subTabsHtml = '<div class="bcm-subtabs">';
    tabs.forEach(t => {
      const activeCls = active === t.id ? ' active' : '';
      subTabsHtml += '<button class="bcm-subtab' + activeCls + '" onclick="ViewBcp._setSubTab(\'' + stepN + '\',\'' + t.id + '\')">';
      subTabsHtml += '<i class="ti ' + t.icon + '"></i> ' + t.label + '</button>';
    });
    subTabsHtml += '</div>';
    const prevBtn = stepN > 1
      ? '<button class="btn btn-ghost btn-sm" onclick="ViewBcp._setStep(' + (stepN - 1) + ')"><i class="ti ti-arrow-left"></i> Atras</button>'
      : '<span></span>';
    const nextBtn = stepN < 5
      ? '<button class="btn btn-primary btn-sm" onclick="ViewBcp._setStep(' + (stepN + 1) + ')">Siguiente <i class="ti ti-arrow-right"></i></button>'
      : '';
    const navHtml = '<div class="bcm-step-nav">' + prevBtn + nextBtn + '</div>';
    body.innerHTML = subTabsHtml + '<div id="bcm-subtab-body-' + stepN + '" class="bcm-subtab-body"></div>' + navHtml;
    renderFn(body.querySelector('#bcm-subtab-body-' + stepN), active);
  }

  async function _stepProcesosBIA(body) {
    const tabs = [
      { id:'procesos', label:'Procesos Criticos', icon:'ti-sitemap' },
      { id:'bia',      label:'Analisis BIA',      icon:'ti-chart-dots' },
    ];
    _buildSubTabs(2, tabs, body, async (subBody, active) => {
      if (active === 'procesos') await _tabProcesses(subBody);
      else await _tabBIA(subBody);
    });
  }

  async function _stepDependencias(body) {
    const tabs = [
      { id:'dependencies', label:'Mapa Dependencias', icon:'ti-link' },
      { id:'suppliers',    label:'Proveedores BCM',   icon:'ti-truck' },
    ];
    _buildSubTabs(3, tabs, body, async (subBody, active) => {
      if (active === 'dependencies') await _tabDependencies(subBody);
      else await _tabSuppliers(subBody);
    });
  }

  async function _stepPlanesDRP(body) {
    const tabs = [
      { id:'strategies', label:'Estrategias',    icon:'ti-route' },
      { id:'plans',      label:'Planes BCP/DRP', icon:'ti-file-text' },
      { id:'runbooks',   label:'Runbooks',        icon:'ti-checklist' },
    ];
    _buildSubTabs(4, tabs, body, async (subBody, active) => {
      if (active === 'strategies')    await _tabStrategies(subBody);
      else if (active === 'runbooks') await _tileRunbooks(subBody);
      else await _tabPlans(subBody);
    });
  }

  async function _stepDocumentacion(body) {
    const tabs = [
      { id:'evidence', label:'Evidencias',     icon:'ti-files' },
      { id:'import',   label:'Importar Excel', icon:'ti-table-import' },
    ];
    _buildSubTabs(5, tabs, body, async (subBody, active) => {
      if (active === 'evidence') await _tabEvidence(subBody);
      else _tabImport(subBody);
    });
  }

  async function _stepTests(body) {
    const tabs = [
      { id:'lista',     label:'Lista de tests',    icon:'ti-clipboard-check' },
      { id:'calendario',label:'Calendario',         icon:'ti-calendar-event' },
      { id:'evidence',  label:'Evidencias',         icon:'ti-files' },
    ];
    _buildSubTabs('tests', tabs, body, async (subBody, active) => {
      if (active === 'lista')      await _tabTests(subBody);
      else if (active === 'calendario') await _tileCalendarioTests(subBody);
      else await _tabEvidence(subBody);
    });
  }

  async function _stepAlertas(body) {
    await _richAlertas(body);
  }

  // ── Tile: Dashboard ISO 22301 ─────────────────────────────────────────────────

  async function _tileDashboard(container) {
    container.innerHTML = '<div style="padding:20px;color:var(--text-subtle)"><i class="ti ti-loader-2 ti-spin"></i> Cargando dashboard...</div>';
    const [comp, dash] = await Promise.all([
      Api.get('/api/bcp/compliance/iso22301' + _locParam()).catch(() => null),
      Api.get('/api/bcp/dashboard').catch(() => ({})),
    ]);

    if (!comp) {
      container.innerHTML = '<div class="notice notice-info">No hay datos suficientes para calcular el score ISO 22301. Completa la configuracion en modo Configurar BCP.</div>';
      return;
    }

    const k = comp.kpis || {};
    const score = comp.score_global || 0;
    const scoreColor = score >= 70 ? '#16a34a' : score >= 40 ? '#ca8a04' : '#dc2626';
    const scoreLabel = score >= 70 ? 'Conforme' : score >= 40 ? 'Parcial' : 'No conforme';
    const biaDone = k.processes_with_bia || 0;
    const biaTotal = k.processes_total || 0;
    const biaColor = biaDone < biaTotal ? '#ca8a04' : '#16a34a';
    const biaNote = biaTotal - biaDone > 0 ? (biaTotal - biaDone) + ' sin BIA' : 'Completo';
    const plansApp = k.plans_approved || 0;
    const plansTotal = k.plans_total || 0;
    const testsOvr = k.tests_overdue || 0;
    const testsOvrColor = testsOvr > 0 ? '#dc2626' : '#16a34a';

    let kpiHtml = '<div class="bcm-kpi-grid">';
    kpiHtml += '<div class="bcm-kpi" style="border-top:3px solid ' + scoreColor + '">';
    kpiHtml += '<div class="bcm-kpi-label">Score ISO 22301</div>';
    kpiHtml += '<div class="bcm-kpi-val" style="color:' + scoreColor + '">' + score + '%</div>';
    kpiHtml += '<div class="bcm-kpi-sub" style="color:' + scoreColor + '">' + scoreLabel + '</div></div>';
    kpiHtml += '<div class="bcm-kpi" style="border-top:3px solid var(--primary)">';
    kpiHtml += '<div class="bcm-kpi-label">BIA completado</div>';
    kpiHtml += '<div class="bcm-kpi-val">' + biaDone + '/' + biaTotal + '</div>';
    kpiHtml += '<div class="bcm-kpi-sub" style="color:' + biaColor + '">' + biaNote + '</div></div>';
    kpiHtml += '<div class="bcm-kpi" style="border-top:3px solid #16a34a">';
    kpiHtml += '<div class="bcm-kpi-label">Planes aprobados</div>';
    kpiHtml += '<div class="bcm-kpi-val">' + plansApp + '/' + plansTotal + '</div>';
    kpiHtml += '<div class="bcm-kpi-sub">' + (plansTotal - plansApp) + ' en borrador</div></div>';
    kpiHtml += '<div class="bcm-kpi" style="border-top:3px solid ' + testsOvrColor + '">';
    kpiHtml += '<div class="bcm-kpi-label">Tests vencidos</div>';
    kpiHtml += '<div class="bcm-kpi-val" style="color:' + testsOvrColor + '">' + testsOvr + '</div>';
    kpiHtml += '<div class="bcm-kpi-sub">' + (k.tests_recent_12m || 0) + ' tests en 12 meses</div></div>';
    kpiHtml += '</div>';

    const clausesHtml = (comp.clauses || []).map(c => {
      const cc = c.score >= 70 ? '#16a34a' : c.score >= 40 ? '#ca8a04' : '#dc2626';
      return '<div style="display:flex;align-items:center;gap:8px;font-size:12px">'
        + '<span style="width:32px;flex-shrink:0;font-weight:700;color:var(--text-subtle)">Cl.' + c.id + '</span>'
        + '<span style="flex:1;color:var(--text-subtle)">' + UI.esc(c.title) + '</span>'
        + '<div style="width:120px;height:5px;background:var(--bg-3,#222);border-radius:3px;overflow:hidden;flex-shrink:0">'
        + '<div style="width:' + c.score + '%;height:100%;background:' + cc + ';border-radius:3px"></div></div>'
        + '<span style="width:32px;text-align:right;font-weight:700;color:' + cc + ';flex-shrink:0">' + c.score + '%</span>'
        + '</div>';
    }).join('');

    let locsHtml;
    if (!(comp.locations || []).length) {
      locsHtml = '<div class="notice notice-info" style="margin:0">Sin sedes definidas. Anade localizaciones en Configurar BCP &gt; Localizaciones.</div>';
    } else {
      locsHtml = '<table class="data" style="font-size:12px"><thead><tr><th>Sede</th><th>Score</th><th>Planes</th><th>Ult. test</th></tr></thead><tbody>';
      (comp.locations || []).forEach(loc => {
        const lc = loc.status === 'green' ? '#16a34a' : loc.status === 'yellow' ? '#ca8a04' : '#dc2626';
        locsHtml += '<tr><td><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + lc + ';margin-right:6px"></span>' + UI.esc(loc.name) + '</td>'
          + '<td style="color:' + lc + ';font-weight:700">' + loc.score + '%</td>'
          + '<td>' + loc.plans_approved + '/' + loc.plans_total + '</td>'
          + '<td style="font-size:11px;color:var(--text-subtle)">' + (loc.last_test_date || '&#8212;') + '</td></tr>';
      });
      locsHtml += '</tbody></table>';
    }

    container.innerHTML = '<div class="bcm-dashboard">'
      + kpiHtml
      + '<div class="bcm-dashboard-grid">'
      + '<div class="card"><div class="card-header"><div class="card-title"><i class="ti ti-checklist"></i> Clausulas ISO 22301</div></div>'
      + '<div style="display:flex;flex-direction:column;gap:8px;padding-top:4px">' + clausesHtml + '</div></div>'
      + '<div class="card"><div class="card-header"><div class="card-title"><i class="ti ti-map-pin"></i> Estado por sede</div></div>'
      + locsHtml + '</div>'
      + '</div>'
      + '<div class="card" style="margin-top:14px">'
      + '<div class="card-header"><div class="card-title"><i class="ti ti-brain"></i> Analisis IA del estado BCM</div>'
      + '<button class="btn btn-ghost btn-sm" id="btn-dash-ai-analyze"><i class="ti ti-sparkles"></i> Analizar</button></div>'
      + '<div id="dash-ai-result" style="font-size:12px;color:var(--text-subtle)">Pulsa "Analizar" para que el agente IA evalue el estado actual y proponga acciones de mejora.</div>'
      + '</div></div>';

    container.querySelector('#btn-dash-ai-analyze').onclick = async () => {
      const btn = container.querySelector('#btn-dash-ai-analyze');
      const res = container.querySelector('#dash-ai-result');
      btn.disabled = true;
      btn.innerHTML = '<i class="ti ti-loader-2 ti-spin"></i>';
      try {
        const msg = 'Analiza el estado actual del BCP/BCM de la organizacion. Score ISO 22301: ' + score
          + '%. KPIs: procesos con BIA ' + biaDone + '/' + biaTotal
          + ', planes aprobados ' + plansApp + '/' + plansTotal
          + ', tests vencidos ' + testsOvr
          + '. Identifica los 3 gaps mas criticos y propone acciones concretas y priorizadas.';
        const sedeCtx = _locationFilter ? ', sede: ' + (_locationMap[_locationFilter]?.name || _locationFilter) : '';
        const r = await Api.post('/api/bcp/ai/quick', {
          message: msg,
          context_hint: 'dashboard ISO 22301, vista corporativa' + sedeCtx,
        });
        res.innerHTML = '<div style="line-height:1.7;white-space:pre-wrap">' + UI.esc(r.response || '').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') + '</div>';
      } catch (e) {
        res.innerHTML = '<span style="color:var(--danger)">Error: ' + UI.esc(e.message) + '</span>';
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="ti ti-sparkles"></i> Analizar';
      }
    };
  }

  // ── Context Wizard ────────────────────────────────────────────────────────────

  async function _contextWizard(container) {
    const ctx = _bcmContext || {};
    const activeWizardStep = parseInt(ctx.wizard_step) || 1;
    const wizardSteps = [
      { n:1, title:'Organizacion', fields:[
        { id:'sector', label:'Sector de actividad *', type:'select', options:['Banca/Finanzas','Seguros','Salud','Industria/Manufactura','Energia/Utilities','Telecomunicaciones','Tecnologia/TI','Retail/Comercio','Administracion Publica','Logistica/Transporte','Educacion','Otro'] },
        { id:'employees_range', label:'Empleados', type:'select', options:['1-50','51-200','201-500','501-2000','2001-10000','Mas de 10000'] },
        { id:'geographic_scope', label:'Alcance geografico', type:'select', options:['Local (ciudad/provincia)','Nacional','Internacional (Europa)','Global'] },
        { id:'annual_loss_estimate', label:'Impacto economico estimado por hora de caida (EUR)', type:'text', placeholder:'p.ej. 50000' },
      ]},
      { n:2, title:'Infraestructura y sistemas criticos', fields:[
        { id:'it_architecture', label:'Arquitectura TI', type:'select', options:['100% On-premise','Mayoritariamente On-premise + algo cloud','Hibrido equilibrado','Mayoritariamente cloud','100% Cloud (SaaS/IaaS)'] },
        { id:'critical_infra', label:'Sistemas criticos (uno por linea)', type:'textarea', placeholder:'ERP SAP\nCRM Salesforce\n...', isJson:true },
        { id:'key_suppliers', label:'Proveedores clave de TI/servicios criticos (uno por linea)', type:'textarea', placeholder:'AWS - infraestructura cloud\n...', isJson:true },
      ]},
      { n:3, title:'Escenarios de riesgo y regulacion', fields:[
        { id:'risk_scenarios', label:'Escenarios de continuidad relevantes', type:'checkboxes',
          options:['Ciberataque / ransomware','Incendio o inundacion en sede','Fallo del proveedor cloud principal','Corte de suministro electrico prolongado','Pandemia / ausencia masiva de personal','Fallo de conectividad / red','Desastre natural en sede principal','Fallo de proveedor critico de TI'] },
        { id:'regulations', label:'Regulaciones/normativas aplicables', type:'checkboxes',
          options:['ISO 22301','NIS2 (Directiva europea)','DORA (sector financiero UE)','GDPR','ENS (Esquema Nacional de Seguridad)','PCI-DSS','SOC 2','Otra regulacion sectorial'] },
        { id:'incident_history', label:'Incidentes de continuidad recientes (resumen)', type:'textarea', placeholder:'p.ej. En 2023 sufrimos un ransomware que afecto 4h al ERP.' },
      ]},
      { n:4, title:'Objetivos de recuperacion', fields:[
        { id:'rto_target', label:'RTO objetivo global', type:'select', options:['15 minutos','30 minutos','1 hora','2 horas','4 horas','8 horas','24 horas','48 horas','72 horas'] },
        { id:'rpo_target', label:'RPO objetivo global', type:'select', options:['Cero (tiempo real)','15 minutos','1 hora','4 horas','24 horas','48 horas','72 horas'] },
        { id:'max_tolerable_downtime', label:'MTD - Maximo tiempo de interrupcion tolerable', type:'select', options:['1 hora','4 horas','8 horas','24 horas','48 horas','72 horas','1 semana'] },
      ]},
    ];

    function _fieldVal(field) {
      const raw = ctx[field.id];
      if (field.isJson) return Array.isArray(raw) ? raw.join('\n') : (typeof raw === 'string' ? raw : '');
      if (Array.isArray(raw)) return raw;
      return raw || '';
    }

    function _buildField(f) {
      const val = _fieldVal(f);
      if (f.type === 'select') {
        let opts = '<option value="">-- Seleccionar --</option>';
        f.options.forEach(o => { opts += '<option value="' + UI.esc(o) + '"' + (val === o ? ' selected' : '') + '>' + UI.esc(o) + '</option>'; });
        return '<div class="fg"><label>' + UI.esc(f.label) + '</label><select id="wz-' + f.id + '" class="form-control">' + opts + '</select></div>';
      }
      if (f.type === 'textarea') {
        const v = Array.isArray(val) ? val.join('\n') : val;
        return '<div class="fg"><label>' + UI.esc(f.label) + '</label><textarea id="wz-' + f.id + '" class="form-control" rows="4" placeholder="' + UI.esc(f.placeholder || '') + '">' + UI.esc(v) + '</textarea></div>';
      }
      if (f.type === 'checkboxes') {
        const checked = Array.isArray(val) ? val : [];
        let cbs = '';
        f.options.forEach(o => {
          cbs += '<label style="display:flex;align-items:center;gap:5px;font-size:12px;cursor:pointer;padding:4px 8px;background:var(--bg-3,#1a1a22);border:1px solid var(--border);border-radius:6px">';
          cbs += '<input type="checkbox" value="' + UI.esc(o) + '" class="wz-cb-' + f.id + '"' + (checked.includes(o) ? ' checked' : '') + '> ' + UI.esc(o) + '</label>';
        });
        return '<div class="fg"><label>' + UI.esc(f.label) + '</label><div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:4px">' + cbs + '</div></div>';
      }
      return '<div class="fg"><label>' + UI.esc(f.label) + '</label><input id="wz-' + f.id + '" class="form-control" value="' + UI.esc(String(val || '')) + '" placeholder="' + UI.esc(f.placeholder || '') + '"></div>';
    }

    const ws = wizardSteps.find(s => s.n === activeWizardStep) || wizardSteps[0];
    let fieldsHtml = ws.fields.map(_buildField).join('');

    // Step 2: Autofill button for infrastructure/suppliers
    if (activeWizardStep === 2) {
      fieldsHtml = '<div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:10px 14px;margin-bottom:12px;display:flex;align-items:center;justify-content:space-between">'
        + '<div><div style="font-size:12px;font-weight:700;margin-bottom:2px"><i class="ti ti-sparkles" style="color:var(--primary)"></i> Autocompletar desde la plataforma</div>'
        + '<div style="font-size:11px;color:var(--text-subtle)">El sistema puede sugerir sistemas criticos desde tus activos y proveedores criticos desde TPRM.</div></div>'
        + '<button class="btn btn-sm btn-secondary" id="wz-autofill-btn" onclick="ViewBcp._wizardAutofill()"><i class="ti ti-wand"></i> Autocompletar</button>'
        + '</div>' + fieldsHtml;
    }

    // Step 3: Add "Otros escenarios" expandable section after risk_scenarios field
    if (activeWizardStep === 3) {
      const extraScenarios = (Array.isArray(ctx.risk_scenarios_json)
        ? ctx.risk_scenarios_json
        : (ctx.risk_scenarios_json ? JSON.parse(ctx.risk_scenarios_json) : [])
      ).filter(s => ![
        'Ciberataque / ransomware','Incendio o inundacion en sede','Fallo del proveedor cloud principal',
        'Corte de suministro electrico prolongado','Pandemia / ausencia masiva de personal',
        'Fallo de conectividad / red','Desastre natural en sede principal','Fallo de proveedor critico de TI',
      ].includes(s));
      const extraHtml = '<div class="fg" style="margin-top:-4px">'
        + '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
        + '<span style="font-size:11px;font-weight:700;color:var(--text-subtle)">OTROS ESCENARIOS PERSONALIZADOS</span>'
        + '<button class="btn btn-sm" style="font-size:10px;padding:2px 8px" id="wz-otros-toggle" onclick="ViewBcp._wziardToggleOtros()">'
        + '<i class="ti ti-plus"></i> Anadir otro</button></div>'
        + '<div id="wz-otros-list" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px">'
        + extraScenarios.map((s,i) => `<div style="display:flex;align-items:center;gap:4px;padding:3px 8px;background:var(--bg-3);border:1px solid var(--border);border-radius:6px;font-size:12px"><input type="checkbox" value="${UI.esc(s)}" class="wz-cb-risk_scenarios" checked><span>${UI.esc(s)}</span><button onclick="this.closest(\'div\').remove()" style="border:none;background:none;cursor:pointer;color:var(--text-subtle);font-size:14px;line-height:1;padding:0 2px">×</button></div>`).join('')
        + '</div>'
        + '<div id="wz-otros-input" style="display:none;display:flex;gap:8px">'
        + '<input id="wz-otro-text" class="form-control" style="font-size:12px" placeholder="Describe el escenario...">'
        + '<button class="btn btn-sm btn-primary" onclick="ViewBcp._wizardAddOtroScenario()">Agregar</button>'
        + '</div></div>';
      fieldsHtml = fieldsHtml + extraHtml;
    }

    let stepsNavHtml = '';
    wizardSteps.forEach((s, i) => {
      const bg = s.n === activeWizardStep ? 'var(--primary-soft,#f3e8ff)' : 'var(--bg-2,#18181f)';
      const bd = s.n === activeWizardStep ? 'var(--primary)' : 'var(--border)';
      const nbg = s.n < activeWizardStep ? '#16a34a' : s.n === activeWizardStep ? 'var(--primary)' : 'var(--border)';
      const nbody = s.n < activeWizardStep ? '<i class="ti ti-check" style="font-size:9px"></i>' : s.n;
      const fromN = s.n > 1 ? s.n - 1 : 0;
      stepsNavHtml += '<div style="flex:1;display:flex;align-items:center;gap:6px;padding:8px;border-radius:8px;cursor:pointer;background:' + bg + ';border:1px solid ' + bd + '" onclick="ViewBcp._saveWizardStep(' + fromN + ',' + s.n + ')">';
      stepsNavHtml += '<div style="width:22px;height:22px;border-radius:50%;background:' + nbg + ';color:#fff;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;flex-shrink:0">' + nbody + '</div>';
      stepsNavHtml += '<span style="font-size:11px;font-weight:600;color:var(--text)">' + s.title + '</span></div>';
      if (i < wizardSteps.length - 1) stepsNavHtml += '<div style="width:20px;height:1px;background:var(--border);flex-shrink:0;margin-top:1px;align-self:center"></div>';
    });

    const prevBtnW = activeWizardStep > 1
      ? '<button class="btn btn-ghost btn-sm" onclick="ViewBcp._saveWizardStep(' + activeWizardStep + ',' + (activeWizardStep - 1) + ')"><i class="ti ti-arrow-left"></i> Anterior</button>'
      : '<span></span>';
    const nextBtnW = activeWizardStep < 4
      ? '<button class="btn btn-primary btn-sm" id="btn-wz-next" onclick="ViewBcp._saveWizardStep(' + activeWizardStep + ',' + (activeWizardStep + 1) + ')">Siguiente <i class="ti ti-arrow-right"></i></button>'
      : '<button class="btn btn-primary btn-sm" id="btn-wz-next" onclick="ViewBcp._saveWizardStep(' + activeWizardStep + ',\'done\')"><i class="ti ti-check"></i> Completar y guardar</button>';
    const completedNotice = ctx.wizard_completed
      ? '<div class="notice notice-success" style="margin-top:12px"><i class="ti ti-check"></i> Contexto completado. El agente IA ya tiene informacion de tu organizacion.</div>'
      : '';

    container.innerHTML = '<div style="max-width:700px;margin:0 auto;padding:4px 0">'
      + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">'
      + '<div><h2 style="font-size:17px;font-weight:700;margin:0">Contexto BCM para el Agente IA</h2>'
      + '<p style="font-size:12px;color:var(--text-subtle);margin:4px 0 0">Proporciona contexto organizacional para que el agente IA pueda asistirte mejor en BCP/DRP</p></div>'
      + '<button class="btn btn-ghost btn-sm" onclick="ViewBcp._setStep(1)" title="Volver al modulo BCM"><i class="ti ti-x"></i> Cerrar</button></div>'
      + '<div style="display:flex;gap:8px;margin-bottom:24px">' + stepsNavHtml + '</div>'
      + '<div class="card" style="padding:20px">'
      + '<h3 style="font-size:14px;font-weight:700;margin:0 0 16px">' + activeWizardStep + '. ' + ws.title + '</h3>'
      + '<div style="display:flex;flex-direction:column;gap:12px" id="wz-fields">' + fieldsHtml + '</div>'
      + '<div style="display:flex;justify-content:space-between;margin-top:20px">' + prevBtnW + nextBtnW + '</div>'
      + '</div>' + completedNotice + '</div>';
  }

  async function _wizardAutofill() {
    const btn = document.getElementById('wz-autofill-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="ti ti-loader-2 ti-spin"></i> Buscando...'; }
    try {
      const data = await Api.get('/api/bcp/context/autofill');
      const infraEl = document.getElementById('wz-critical_infra');
      const suppEl = document.getElementById('wz-key_suppliers');
      if (infraEl && data.critical_systems && data.critical_systems.length) {
        const existing = infraEl.value.trim().split('\n').filter(Boolean);
        const merged = [...new Set([...existing, ...data.critical_systems])];
        infraEl.value = merged.join('\n');
        UI.toast(`${data.critical_systems.length} sistemas criticos importados desde activos`, 'success');
      } else if (infraEl) {
        infraEl.placeholder = 'No se encontraron activos criticos/altos en la plataforma. Introducir manualmente.';
      }
      if (suppEl && data.key_suppliers && data.key_suppliers.length) {
        const existing = suppEl.value.trim().split('\n').filter(Boolean);
        const merged = [...new Set([...existing, ...data.key_suppliers])];
        suppEl.value = merged.join('\n');
        UI.toast(`${data.key_suppliers.length} proveedores criticos importados`, 'success');
      }
      if (!data.critical_systems?.length && !data.key_suppliers?.length) {
        UI.toast('No se encontraron datos en la plataforma. Introduce los sistemas manualmente.', 'info');
      }
    } catch (e) {
      UI.toast('Error al autocompletar: ' + e.message, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = '<i class="ti ti-wand"></i> Autocompletar'; }
    }
  }

  function _wziardToggleOtros() {
    const inp = document.getElementById('wz-otros-input');
    if (inp) inp.style.display = inp.style.display === 'none' ? 'flex' : 'none';
  }

  function _wizardAddOtroScenario() {
    const textEl = document.getElementById('wz-otro-text');
    const text = textEl?.value?.trim();
    if (!text) return;
    const list = document.getElementById('wz-otros-list');
    if (!list) return;
    const div = document.createElement('div');
    div.style.cssText = 'display:flex;align-items:center;gap:4px;padding:3px 8px;background:var(--bg-3);border:1px solid var(--border);border-radius:6px;font-size:12px';
    div.innerHTML = `<input type="checkbox" value="${UI.esc(text)}" class="wz-cb-risk_scenarios" checked><span>${UI.esc(text)}</span><button onclick="this.closest('div').remove()" style="border:none;background:none;cursor:pointer;color:var(--text-subtle);font-size:14px;line-height:1;padding:0 2px">×</button>`;
    list.appendChild(div);
    textEl.value = '';
    document.getElementById('wz-otros-input').style.display = 'none';
  }

  async function _saveWizardStep(fromStep, toStep) {
    const body = { wizard_step: typeof toStep === 'number' ? toStep : 4, wizard_completed: toStep === 'done' };

    const collectField = (fieldId, type, isJson) => {
      if (type === 'checkboxes') {
        return Array.from(document.querySelectorAll('.wz-cb-' + fieldId + ':checked')).map(cb => cb.value);
      }
      if (type === 'textarea') {
        const el = document.getElementById('wz-' + fieldId);
        if (!el) return undefined;
        // Solo devolver array si el campo es JSON (listas); texto plano como string
        if (isJson) return el.value.split('\n').map(l => l.trim()).filter(Boolean);
        return el.value.trim();
      }
      const el = document.getElementById('wz-' + fieldId);
      return el ? el.value : undefined;
    };

    const allFields = [
      { id:'sector', type:'select' }, { id:'employees_range', type:'select' },
      { id:'geographic_scope', type:'select' }, { id:'annual_loss_estimate', type:'text' },
      { id:'it_architecture', type:'select' }, { id:'critical_infra', type:'textarea', isJson:true },
      { id:'key_suppliers', type:'textarea', isJson:true },
      { id:'risk_scenarios', type:'checkboxes' }, { id:'regulations', type:'checkboxes' },
      { id:'incident_history', type:'textarea', isJson:false },
      { id:'rto_target', type:'select' }, { id:'rpo_target', type:'select' },
      { id:'max_tolerable_downtime', type:'select' },
    ];

    allFields.forEach(f => {
      const val = collectField(f.id, f.type, f.isJson);
      if (val !== undefined && val !== '') body[f.id] = val;
    });

    try {
      _bcmContext = await Api.post('/api/bcp/context', body);
      const lbl = document.getElementById('bcm-wizard-label');
      if (lbl) lbl.textContent = _bcmContext.wizard_completed ? 'Contexto IA' : 'Configurar IA';
      if (toStep === 'done') {
        UI.toast('Contexto BCM guardado correctamente', 'success');
        _currentStep = 1;
        _renderContent();
      } else {
        _currentStep = 0;
        _bcmContext.wizard_step = typeof toStep === 'number' ? toStep : 4;
        _renderContent();
      }
    } catch (e) {
      UI.toast('Error guardando: ' + e.message, 'error');
    }
  }

  // ── AI Panel (FAB + slide-in drawer) ─────────────────────────────────────────

  function _initAiPanel() {
    if (_aiPanelInitialized) return;
    _aiPanelInitialized = true;
    document.getElementById('bcm-ai-panel')?.remove();
    document.getElementById('bcm-ai-overlay')?.remove();
    document.getElementById('bcm-ai-fab')?.remove();

    const overlay = document.createElement('div');
    overlay.id = 'bcm-ai-overlay';
    overlay.className = 'bcm-ai-overlay';
    overlay.onclick = () => ViewBcp._closeAiPanel();
    document.body.appendChild(overlay);

    const panel = document.createElement('div');
    panel.id = 'bcm-ai-panel';
    panel.className = 'bcm-ai-panel';
    const panelMsg = _bcmContext && _bcmContext.wizard_completed
      ? ''
      : '<em>Para respuestas mas precisas, completa el <strong>Contexto IA</strong> desde el boton del header.</em>';
    panel.innerHTML = '<div class="bcm-ai-header">'
      + '<div style="display:flex;align-items:center;gap:8px"><div class="bcm-ai-dot"></div><strong style="font-size:13px">Asistente BCM</strong></div>'
      + '<button onclick="ViewBcp._closeAiPanel()" style="background:none;border:none;color:var(--text-subtle);cursor:pointer;font-size:16px;padding:2px">&#x2715;</button></div>'
      + '<div class="bcm-ai-ctx" id="bcm-ai-ctx">'
      + '<i class="ti ti-info-circle" style="font-size:11px"></i>'
      + '<span id="bcm-ai-ctx-text">Listo para ayudarte con BCP/DRP</span></div>'
      + '<div class="bcm-ai-msgs" id="bcm-ai-msgs">'
      + '<div class="bcm-ai-msg bcm-ai-msg-ai">Hola. Soy tu asistente de continuidad de negocio. Puedo ayudarte a:<br><strong>&middot; Analizar procesos y dependencias</strong><br><strong>&middot; Completar planes DRP paso a paso</strong><br><strong>&middot; Identificar gaps ISO 22301</strong><br><strong>&middot; Proponer escenarios de test</strong><br><br>' + panelMsg + '</div>'
      + '</div>'
      + '<div class="bcm-ai-suggestions" id="bcm-ai-suggestions">'
      + '<div class="bcm-ai-sug" onclick="ViewBcp._sendAiMsg(\'Analiza el estado actual de mi BCP e identifica los 3 gaps mas criticos\')">Analizar estado BCP</div>'
      + '<div class="bcm-ai-sug" onclick="ViewBcp._sendAiMsg(\'Propone un escenario de test tabletop para los procesos mas criticos\')">Proponer test tabletop</div>'
      + '<div class="bcm-ai-sug" onclick="ViewBcp._sendAiMsg(\'Ayudame a redactar el procedimiento de recuperacion para el proceso mas critico\')">Redactar DRP</div>'
      + '<div class="bcm-ai-sug" onclick="ViewBcp._sendAiMsg(\'Que gaps tengo frente a ISO 22301 clausula 8?\')">Gap ISO 22301</div>'
      + '</div>'
      + '<div class="bcm-ai-input-row">'
      + '<textarea id="bcm-ai-input" class="bcm-ai-input" placeholder="Pregunta sobre BCP, DRP, dependencias, ISO 22301..." rows="1"'
      + ' onkeydown="if(event.key===\'Enter\'&&!event.shiftKey){event.preventDefault();ViewBcp._sendAiMsg()}"></textarea>'
      + '<button class="bcm-ai-send" onclick="ViewBcp._sendAiMsg()"><i class="ti ti-send"></i></button>'
      + '</div>';
    document.body.appendChild(panel);
    // El panel se abre desde el FAB global — no crear FAB separado
  }

  function _openAiPanel() {
    if (!_aiPanelInitialized) _initAiPanel();
    document.getElementById('bcm-ai-panel')?.classList.add('open');
    document.getElementById('bcm-ai-overlay')?.classList.add('show');
    // Ocultar FAB global mientras el panel está abierto
    const fabMain = document.getElementById('quick-actions-fab');
    if (fabMain) fabMain.style.opacity = '0.3';
    const ctxEl = document.getElementById('bcm-ai-ctx-text');
    if (ctxEl) {
      const stepLabels = { 0:'Wizard contexto', 1:'Localizaciones', 2:'Procesos & BIA', 3:'Dependencias', 4:'Planes & DRP', 5:'Documentacion' };
      const tileLabels = { dashboard:'Dashboard ISO 22301', graph:'Mapa Dependencias', tests:'Tests & Evidencias', alertas:'Alertas IA' };
      const screenCtx = _currentMode === 'config'
        ? (stepLabels[_currentStep] || 'Configurar BCP')
        : (tileLabels[_currentTile] || 'Operar BCP');
      const sedeCtx = _locationFilter ? ' · ' + (_locationMap[_locationFilter]?.name || 'Sede') : '';
      ctxEl.textContent = screenCtx + sedeCtx;
    }
  }

  function _closeAiPanel() {
    document.getElementById('bcm-ai-panel')?.classList.remove('open');
    document.getElementById('bcm-ai-overlay')?.classList.remove('show');
    const fabMain = document.getElementById('quick-actions-fab');
    if (fabMain) fabMain.style.opacity = '';
  }

  async function _sendAiMsg(textArg) {
    const inp = document.getElementById('bcm-ai-input');
    const text = textArg || (inp ? inp.value.trim() : '');
    if (!text) return;
    if (inp) inp.value = '';
    const msgs = document.getElementById('bcm-ai-msgs');
    if (!msgs) return;

    const userDiv = document.createElement('div');
    userDiv.className = 'bcm-ai-msg bcm-ai-msg-user';
    userDiv.textContent = text;
    msgs.appendChild(userDiv);
    msgs.scrollTop = msgs.scrollHeight;

    const loadDiv = document.createElement('div');
    loadDiv.className = 'bcm-ai-msg bcm-ai-msg-ai';
    loadDiv.innerHTML = '<i class="ti ti-loader-2 ti-spin"></i> Pensando...';
    msgs.appendChild(loadDiv);
    msgs.scrollTop = msgs.scrollHeight;

    const stepLabels = { 1:'Localizaciones', 2:'Procesos y BIA', 3:'Dependencias', 4:'Planes y DRP', 5:'Documentacion' };
    const tileLabels = { dashboard:'Dashboard ISO 22301', graph:'Mapa Dependencias', tests:'Tests', alertas:'Alertas IA' };
    const screenCtx = _currentMode === 'config'
      ? ('paso ' + (_currentStep || '') + ': ' + (stepLabels[_currentStep] || ''))
      : ('tile ' + (tileLabels[_currentTile] || ''));
    const sedeCtx = _locationFilter ? ', sede: ' + (_locationMap[_locationFilter]?.name || '') : '';

    try {
      const r = await Api.post('/api/bcp/ai/quick', {
        message: text,
        context_hint: screenCtx + sedeCtx,
      });
      loadDiv.innerHTML = (r.response || '').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
    } catch (e) {
      loadDiv.innerHTML = '<span style="color:var(--danger)">Error: ' + UI.esc(e.message) + '</span>';
    }
    msgs.scrollTop = msgs.scrollHeight;
  }

  // ── Tile: Activaciones de emergencia ─────────────────────────────────────────

  const _ACT_TYPE_LABELS = {
    accion: 'Accion', nota: 'Nota', escalada: 'Escalada',
    resolucion: 'Resolucion', decision: 'Decision', comunicacion: 'Comunicacion',
  };
  const _ACT_TYPE_COLORS = {
    accion: '#2563EB', nota: '#6B7280', escalada: '#DC2626',
    resolucion: '#16a34a', decision: '#D97706', comunicacion: '#7C3AED',
  };

  async function _tileActivaciones(body) {
    const allActs = await Api.get('/api/bcp/activations').catch(() => []);
    const active = allActs.find(a => !a.closed_at);

    body.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 340px;gap:16px;height:100%">
        <div>
          ${active ? `
            <div style="border:2px solid #DC2626;border-radius:10px;overflow:hidden;margin-bottom:12px">
              <div style="background:#DC262618;padding:12px 16px;display:flex;align-items:center;justify-content:space-between">
                <div style="display:flex;align-items:center;gap:10px">
                  <span class="bcm-act-pulse-dot" style="position:static;width:12px;height:12px"></span>
                  <strong style="font-size:14px;color:#DC2626">BCP ACTIVADO — ${UI.esc(active.code||'')} ${UI.esc(active.title||'')}</strong>
                </div>
                <div style="display:flex;gap:6px">
                  <button class="btn btn-sm" style="background:#2563EB;color:#fff;font-size:11px"
                    onclick="ViewBcp._openCrisisRoom(${active.id})">
                    <i class="ti ti-external-link"></i> Sala de crisis
                  </button>
                  <button class="btn btn-sm" style="background:#DC262615;color:#DC2626;border:1px solid #DC262640;font-size:11px"
                    onclick="ViewBcp._closeActivacion(${active.id})">
                    <i class="ti ti-lock"></i> Cerrar
                  </button>
                </div>
              </div>
              <div style="padding:12px 16px">
                <div style="display:flex;gap:20px;font-size:12px;color:var(--text-subtle);margin-bottom:10px">
                  <span><b>Activado:</b> ${new Date(active.activated_at).toLocaleString('es-ES')}</span>
                  <span><b>Responsable:</b> ${UI.esc(active.activated_by_name||'—')}</span>
                </div>
                <div style="font-size:11px;font-weight:700;color:var(--text-subtle);margin-bottom:8px;text-transform:uppercase">Timeline reciente</div>
                <div style="max-height:180px;overflow-y:auto">
                  ${(active.situation_log||[]).length === 0
                    ? '<div style="font-size:12px;color:var(--text-subtle);text-align:center;padding:12px">Sin eventos registrados. Usa la sala de crisis para registrar el progreso.</div>'
                    : [...(active.situation_log||[])].reverse().slice(0,8).map(e => {
                        const color = _ACT_TYPE_COLORS[e.entry_type||'accion'] || '#6B7280';
                        const label = _ACT_TYPE_LABELS[e.entry_type||'accion'] || e.entry_type || 'Accion';
                        return `<div style="display:flex;gap:8px;font-size:12px;padding:5px 0;border-bottom:1px solid var(--border)">
                          <span style="color:var(--text-subtle);flex-shrink:0;font-size:11px;width:38px">${new Date(e.timestamp).toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit'})}</span>
                          <span style="flex-shrink:0;padding:1px 6px;border-radius:4px;font-size:10px;font-weight:700;background:${color}18;color:${color}">${UI.esc(label)}</span>
                          <span style="flex:1">${UI.esc(e.text||'')}</span>
                        </div>`;
                      }).join('')
                  }
                </div>
                <div style="margin-top:10px;display:flex;gap:8px">
                  <button class="btn btn-sm btn-secondary" onclick="ViewBcp._quickLogEntry(${active.id})">
                    <i class="ti ti-message-plus"></i> Registrar evento rapido
                  </button>
                  <button class="btn btn-sm btn-secondary" onclick="ViewBcp._openCrisisRoom(${active.id})">
                    <i class="ti ti-paperclip"></i> Adjuntar evidencia
                  </button>
                </div>
              </div>
            </div>
          ` : `
            <div style="border:2px dashed var(--border);border-radius:10px;padding:32px 20px;text-align:center;margin-bottom:12px">
              <div style="width:60px;height:60px;border-radius:50%;background:#DC262615;display:flex;align-items:center;justify-content:center;margin:0 auto 14px">
                <i class="ti ti-shield-check" style="font-size:28px;color:#DC2626"></i>
              </div>
              <div style="font-size:15px;font-weight:700;margin-bottom:6px">Sin activaciones en curso</div>
              <div style="font-size:12px;color:var(--text-subtle);margin-bottom:20px;max-width:380px;margin-left:auto;margin-right:auto">
                El BCP no esta activado. Usa este boton unicamente cuando se detecte un incidente real que requiera activar los planes de continuidad.
              </div>
              <button class="btn" style="background:#DC2626;color:#fff;font-size:14px;font-weight:700;padding:10px 22px"
                onclick="ViewBcp._modalActivacion()">
                <i class="ti ti-alert-triangle"></i> ACTIVAR BCP / DRP
              </button>
            </div>
          `}
        </div>
        <div>
          <div style="font-size:12px;font-weight:700;margin-bottom:10px;text-transform:uppercase;color:var(--text-subtle)">
            Historial (${allActs.length})
          </div>
          ${!allActs.length
            ? '<div class="notice notice-info" style="font-size:12px">Sin activaciones registradas.</div>'
            : allActs.map(a => {
                const isActive = !a.closed_at;
                const dur = a.closed_at
                  ? (() => { const m = Math.round((new Date(a.closed_at)-new Date(a.activated_at))/60000); return m>60?Math.round(m/60)+'h':m+'min'; })()
                  : null;
                return `<div style="border:1px solid ${isActive?'#DC2626':'var(--border)'};border-radius:8px;padding:10px 12px;margin-bottom:8px;cursor:pointer;background:${isActive?'#DC262608':'var(--bg-2)'}"
                  onclick="ViewBcp._openCrisisRoom(${a.id})">
                  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
                    <span style="font-size:12px;font-weight:700;color:${isActive?'#DC2626':'var(--text)'}">${UI.esc(a.code||'')} ${isActive?'<span style="font-size:10px">ACTIVA</span>':''}</span>
                    <span style="font-size:10px;color:var(--text-subtle)">${new Date(a.activated_at).toLocaleDateString('es-ES')}</span>
                  </div>
                  <div style="font-size:11px;color:var(--text-subtle)">${UI.esc(a.title||'—')}</div>
                  ${dur?`<div style="font-size:10px;color:var(--text-subtle);margin-top:2px">Duracion: ${dur}</div>`:''}
                  <div style="display:flex;gap:6px;margin-top:6px">
                    <button class="btn btn-sm" style="font-size:10px;padding:2px 8px"
                      onclick="event.stopPropagation();ViewBcp._openActivationReport(${a.id})">
                      <i class="ti ti-file-report"></i> Post-mortem
                    </button>
                  </div>
                </div>`;
              }).join('')
          }
        </div>
      </div>
    `;
  }

  async function _quickLogEntry(actId) {
    const existing = document.getElementById('modal-quicklog-dyn');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'modal-quicklog-dyn';
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:460px">
      <div class="modal-header"><h2><i class="ti ti-message-plus"></i> Registrar evento</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:16px 20px">
        <div style="margin-bottom:12px">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Tipo de entrada</label>
          <select id="ql-type" class="form-control" style="font-size:13px">
            <option value="accion">Accion tomada</option>
            <option value="nota">Nota / observacion</option>
            <option value="escalada">Escalada</option>
            <option value="resolucion">Paso de resolucion</option>
            <option value="decision">Decision tomada</option>
            <option value="comunicacion">Comunicacion enviada</option>
          </select>
        </div>
        <div style="margin-bottom:12px">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Descripcion *</label>
          <textarea id="ql-text" class="form-control" rows="3" style="font-size:13px" placeholder="Describe la accion, decision o evento..."></textarea>
        </div>
        <div>
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Responsable (opcional)</label>
          <input id="ql-owner" class="form-control" style="font-size:13px" placeholder="Nombre o cargo del responsable">
        </div>
      </div>
      <div class="modal-footer-sticky">
        <div style="display:flex;gap:8px;margin-left:auto">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-sm btn-primary" id="ql-save-btn">Registrar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#ql-save-btn').onclick = async () => {
      const text = modal.querySelector('#ql-text').value.trim();
      if (!text) { UI.toast('Descripcion requerida', 'error'); return; }
      try {
        await Api.post(`/api/bcp/activations/${actId}/log`, {
          entry_type: modal.querySelector('#ql-type').value,
          text,
          action_owner: modal.querySelector('#ql-owner').value.trim() || undefined,
        });
        modal.remove();
        UI.toast('Evento registrado', 'success');
        _setTile('activaciones');
      } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
    };
  }

  async function _openCrisisRoom(actId) {
    const existing = document.getElementById('modal-crisis-room');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'modal-crisis-room';
    modal.className = 'modal-bg';
    modal.innerHTML = `<div class="modal" style="max-width:900px;width:96vw;height:88vh;display:flex;flex-direction:column">
      <div class="modal-header" style="border-bottom:2px solid #DC2626;flex-shrink:0">
        <h2 style="color:#DC2626"><i class="ti ti-alert-triangle"></i> Sala de Crisis — cargando...</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div style="flex:1;overflow:hidden;display:flex;flex-direction:column">
        <div id="cr-content" style="flex:1;overflow-y:auto;padding:16px 20px">
          <div style="text-align:center;padding:40px;color:var(--text-subtle)"><i class="ti ti-loader-2 ti-spin"></i></div>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
    await _renderCrisisRoomContent(actId, modal);
  }

  async function _renderCrisisRoomContent(actId, modal) {
    try {
      const act = await Api.get(`/api/bcp/activations/${actId}`);
      const isActive = !act.closed_at;

      modal.querySelector('h2').innerHTML = `<i class="ti ti-alert-triangle"></i> ${UI.esc(act.code)} — ${UI.esc(act.title)} <span style="font-size:11px;font-weight:400;padding:2px 8px;border-radius:4px;background:${isActive?'#DC262620':'var(--bg-3)'};color:${isActive?'#DC2626':'var(--text-subtle)'};margin-left:8px">${isActive?'ACTIVA':'CERRADA'}</span>`;

      const attachments = act.attachments || [];
      const log = act.situation_log || [];
      const checklist = act.checklist_items || [];

      const tabBtns = ['timeline','adjuntos','checklist','postmortem'];
      const tabLabels = { timeline:'Timeline', adjuntos:'Adjuntos (' + attachments.length + ')', checklist:'Checklist (' + checklist.filter(i=>i.status==='done').length + '/' + checklist.length + ')', postmortem:'Post-Mortem' };

      let activeTab = 'timeline';

      const renderTabs = () => `
        <div style="display:flex;gap:4px;border-bottom:1px solid var(--border);margin-bottom:14px;flex-shrink:0">
          ${tabBtns.map(t => `<button id="cr-tab-${t}" onclick="ViewBcp._crSetTab('${actId}','${t}')"
            style="padding:6px 14px;font-size:12px;font-weight:600;border:none;background:none;cursor:pointer;color:${t===activeTab?'var(--primary)':'var(--text-subtle)'};border-bottom:2px solid ${t===activeTab?'var(--primary)':'transparent'};transition:.15s">
            ${tabLabels[t]}
          </button>`).join('')}
          ${isActive ? `<div style="margin-left:auto;display:flex;gap:6px;padding-bottom:4px">
            <button class="btn btn-sm" style="background:#DC2626;color:#fff;font-size:11px" onclick="ViewBcp._closeActivacion(${actId})">
              <i class="ti ti-lock"></i> Cerrar activacion
            </button>
          </div>` : ''}
        </div>
      `;

      const renderTimeline = () => {
        const logRev = [...log].reverse();
        return `
          ${isActive ? `<div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:14px">
            <div style="font-size:12px;font-weight:700;margin-bottom:10px">Registrar nuevo evento</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
              <select id="cr-etype" class="form-control" style="font-size:12px">
                <option value="accion">Accion tomada</option>
                <option value="nota">Nota / observacion</option>
                <option value="escalada">Escalada</option>
                <option value="resolucion">Paso de resolucion</option>
                <option value="decision">Decision tomada</option>
                <option value="comunicacion">Comunicacion enviada</option>
              </select>
              <input id="cr-eowner" class="form-control" style="font-size:12px" placeholder="Responsable (opcional)">
            </div>
            <textarea id="cr-etext" class="form-control" rows="2" style="font-size:12px;margin-bottom:8px" placeholder="Describe la accion, decision o evento..."></textarea>
            <button class="btn btn-sm btn-primary" onclick="ViewBcp._crAddLog(${actId})"><i class="ti ti-send"></i> Registrar</button>
          </div>` : ''}
          <div style="max-height:360px;overflow-y:auto">
            ${logRev.length === 0
              ? '<div style="text-align:center;padding:24px;color:var(--text-subtle);font-size:12px">Sin eventos registrados.</div>'
              : logRev.map((e,i) => {
                  const color = _ACT_TYPE_COLORS[e.entry_type||'accion'] || '#6B7280';
                  const label = _ACT_TYPE_LABELS[e.entry_type||'accion'] || e.entry_type || 'Accion';
                  return `<div style="display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">
                    <div style="flex-shrink:0;width:6px;border-radius:3px;background:${color};align-self:stretch"></div>
                    <div style="flex:1;min-width:0">
                      <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px">
                        <span style="padding:1px 7px;border-radius:4px;font-size:10px;font-weight:700;background:${color}18;color:${color}">${UI.esc(label)}</span>
                        <span style="font-size:10px;color:var(--text-subtle)">${new Date(e.timestamp).toLocaleString('es-ES',{dateStyle:'short',timeStyle:'short'})}</span>
                        ${e.user_email?`<span style="font-size:10px;color:var(--text-subtle)">${UI.esc(e.user_email)}</span>`:''}
                        ${e.action_owner?`<span style="font-size:10px;color:var(--text-subtle)">Resp: ${UI.esc(e.action_owner)}</span>`:''}
                      </div>
                      <div style="font-size:13px">${UI.esc(e.text||'')}</div>
                    </div>
                  </div>`;
                }).join('')
            }
          </div>
        `;
      };

      const renderAttachments = () => `
        ${isActive ? `<div style="background:var(--bg-2);border:1px dashed var(--border);border-radius:8px;padding:16px;margin-bottom:14px;text-align:center">
          <div style="font-size:12px;color:var(--text-subtle);margin-bottom:10px">Adjunta PDFs, documentos, imagenes, hojas de calculo y otros archivos de evidencia</div>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:10px;text-align:left">
            <input id="cr-att-title" class="form-control" style="font-size:12px" placeholder="Titulo / descripcion *">
            <select id="cr-att-type" class="form-control" style="font-size:12px">
              <option value="log">Log del sistema</option>
              <option value="screenshot">Captura de pantalla</option>
              <option value="report">Informe</option>
              <option value="excel">Hoja de calculo</option>
              <option value="evidencia">Evidencia general</option>
              <option value="comunicacion">Comunicacion</option>
            </select>
            <input type="file" id="cr-att-file" class="form-control" style="font-size:12px"
              accept=".pdf,.docx,.doc,.txt,.csv,.png,.jpg,.jpeg,.gif,.xlsx,.xls">
          </div>
          <button class="btn btn-sm btn-primary" onclick="ViewBcp._crUploadAttachment(${actId})"><i class="ti ti-upload"></i> Subir adjunto</button>
        </div>` : ''}
        ${attachments.length === 0
          ? '<div style="text-align:center;padding:24px;color:var(--text-subtle);font-size:12px">Sin adjuntos. Sube evidencias del incidente.</div>'
          : `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;max-height:360px;overflow-y:auto">
              ${attachments.map(a => {
                const icon = (a.mime_type||'').includes('pdf') ? 'ti-file-type-pdf' :
                  (a.mime_type||'').includes('image') ? 'ti-photo' :
                  (a.mime_type||'').includes('sheet') || (a.mime_type||'').includes('excel') ? 'ti-table' : 'ti-file';
                return `<div style="border:1px solid var(--border);border-radius:8px;padding:10px 12px;background:var(--bg-2)">
                  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                    <i class="ti ${icon}" style="font-size:18px;color:var(--primary)"></i>
                    <div style="min-width:0">
                      <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${UI.esc(a.title||a.file_name||'')}</div>
                      <div style="font-size:10px;color:var(--text-subtle)">${UI.esc(a.evidence_type||'')} · ${a.file_size ? Math.round(a.file_size/1024)+'KB' : ''}</div>
                    </div>
                  </div>
                  <div style="display:flex;gap:6px">
                    <a href="/api/bcp/evidence/${a.id}/download" target="_blank" class="btn btn-sm" style="font-size:10px;padding:2px 8px">
                      <i class="ti ti-download"></i> Descargar
                    </a>
                    ${isActive ? `<button class="btn btn-sm" style="font-size:10px;padding:2px 8px;background:#DC262615;color:#DC2626;border-color:#DC262640"
                      onclick="ViewBcp._crDeleteAttachment(${actId},${a.id})">
                      <i class="ti ti-trash"></i>
                    </button>` : ''}
                  </div>
                </div>`;
              }).join('')}
            </div>`
        }
        ${isActive ? `<div style="margin-top:14px;padding:10px 12px;background:var(--bg-2);border-radius:8px;font-size:12px">
          <div style="font-weight:700;margin-bottom:8px"><i class="ti ti-sparkles" style="color:var(--primary)"></i> Resumen IA de evidencia</div>
          ${act.ai_summary
            ? `<div style="font-size:12px;max-height:120px;overflow-y:auto">${UI.esc(act.ai_summary).replace(/\n/g,'<br>')}</div>
               <button class="btn btn-sm btn-ghost" style="margin-top:8px;font-size:11px" onclick="ViewBcp._crGenerateAISummary(${actId})"><i class="ti ti-refresh"></i> Regenerar</button>`
            : `<div style="font-size:12px;color:var(--text-subtle);margin-bottom:8px">El agente IA puede leer todos los adjuntos y el timeline, y generar un resumen ordenado.</div>
               <button class="btn btn-sm btn-primary" style="font-size:11px" onclick="ViewBcp._crGenerateAISummary(${actId})"><i class="ti ti-sparkles"></i> Generar resumen IA</button>`
          }
        </div>` : (act.ai_summary ? `<div style="margin-top:14px;padding:10px 12px;background:var(--bg-2);border-radius:8px"><div style="font-size:11px;font-weight:700;margin-bottom:6px">Resumen IA</div><div style="font-size:12px">${UI.esc(act.ai_summary).replace(/\n/g,'<br>')}</div></div>` : '')}
      `;

      const renderChecklist = () => `
        <div style="max-height:440px;overflow-y:auto">
          ${checklist.length === 0
            ? '<div style="text-align:center;padding:24px;color:var(--text-subtle);font-size:12px">Sin checklist. Se genera automaticamente al activar el plan.</div>'
            : checklist.map(item => {
                const done = item.status === 'done';
                return `<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border)">
                  ${isActive
                    ? `<input type="checkbox" ${done?'checked':''} ${done?'disabled':''} onchange="ViewBcp._crToggleChecklist(${actId},${item.order},this.checked)"
                         style="margin-top:3px;width:16px;height:16px;flex-shrink:0;cursor:${done?'default':'pointer'}">`
                    : `<span style="width:16px;height:16px;flex-shrink:0;border-radius:50%;background:${done?'#16a34a':'var(--border)'};display:inline-flex;align-items:center;justify-content:center;margin-top:3px">
                         ${done?'<i class="ti ti-check" style="font-size:9px;color:#fff"></i>':''}</span>`
                  }
                  <div style="flex:1;min-width:0">
                    <div style="font-size:13px;font-weight:${done?'400':'600'};color:${done?'var(--text-subtle)':'var(--text)'};text-decoration:${done?'line-through':'none'}">${UI.esc(item.title||'')}</div>
                    ${item.description?`<div style="font-size:11px;color:var(--text-subtle)">${UI.esc(item.description)}</div>`:''}
                    ${done&&item.executed_by?`<div style="font-size:10px;color:var(--text-subtle)">Por ${UI.esc(item.executed_by)}</div>`:''}
                  </div>
                  <span style="font-size:10px;padding:2px 6px;border-radius:4px;background:${done?'#16a34a18':'var(--bg-3)'};color:${done?'#16a34a':'var(--text-subtle)'}">${done?'Hecho':'Pendiente'}</span>
                </div>`;
              }).join('')
          }
        </div>
      `;

      const renderPostMortem = () => `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px">
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Resumen ejecutivo</label>
            <textarea id="cr-pm-exec" class="form-control" rows="5" style="font-size:12px" ${isActive?'':'readonly'}
              placeholder="Resumen del incidente para la alta direccion...">${UI.esc(act.executive_summary||'')}</textarea>
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Causa raiz</label>
            <textarea id="cr-pm-root" class="form-control" rows="5" style="font-size:12px" ${isActive?'':'readonly'}
              placeholder="Analisis de causa raiz...">${UI.esc(act.root_cause||'')}</textarea>
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Lecciones aprendidas</label>
            <textarea id="cr-pm-lessons" class="form-control" rows="4" style="font-size:12px" ${isActive?'':'readonly'}
              placeholder="Que funcionó, que fallo, como mejorar...">${UI.esc(act.lessons_learned||'')}</textarea>
          </div>
          <div>
            <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Acciones correctivas</label>
            <textarea id="cr-pm-improve" class="form-control" rows="4" style="font-size:12px" ${isActive?'':'readonly'}
              placeholder="Mejoras a implementar...">${UI.esc(Array.isArray(act.improvement_actions)?act.improvement_actions.join('\n'):act.improvement_actions||'')}</textarea>
          </div>
        </div>
        ${isActive ? `<div style="display:flex;gap:8px;margin-bottom:14px">
          <button class="btn btn-sm btn-primary" onclick="ViewBcp._crSavePostMortem(${actId})"><i class="ti ti-device-floppy"></i> Guardar borrador</button>
        </div>` : ''}
        <div style="border-top:1px solid var(--border);padding-top:12px;display:flex;gap:8px">
          <button class="btn btn-sm" onclick="ViewBcp._openActivationReport(${actId})" style="background:var(--primary);color:#fff">
            <i class="ti ti-file-report"></i> Generar informe post-mortem
          </button>
        </div>
      `;

      const cr = modal.querySelector('#cr-content');
      window._crCurrentTab = 'timeline';
      window._crActId = actId;
      window._crAct = act;
      window._crModal = modal;

      const render = () => {
        const tab = window._crCurrentTab;
        cr.innerHTML = renderTabs() +
          (tab === 'timeline' ? renderTimeline() :
           tab === 'adjuntos' ? renderAttachments() :
           tab === 'checklist' ? renderChecklist() :
           renderPostMortem());
      };
      window.ViewBcp._crSetTab = (aid, tab) => { window._crCurrentTab = tab; render(); };
      render();
    } catch (e) {
      modal.querySelector('#cr-content').innerHTML = `<div class="notice notice-error">Error: ${UI.esc(e.message)}</div>`;
    }
  }

  async function _crAddLog(actId) {
    const text = document.getElementById('cr-etext')?.value?.trim();
    if (!text) { UI.toast('Descripcion requerida', 'error'); return; }
    try {
      await Api.post(`/api/bcp/activations/${actId}/log`, {
        entry_type: document.getElementById('cr-etype')?.value || 'accion',
        text,
        action_owner: document.getElementById('cr-eowner')?.value?.trim() || undefined,
      });
      UI.toast('Evento registrado', 'success');
      await _renderCrisisRoomContent(actId, window._crModal);
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  async function _crUploadAttachment(actId) {
    const title = document.getElementById('cr-att-title')?.value?.trim();
    const fileEl = document.getElementById('cr-att-file');
    const file = fileEl?.files?.[0];
    if (!title) { UI.toast('Titulo requerido', 'error'); return; }
    if (!file) { UI.toast('Selecciona un archivo', 'error'); return; }
    const fd = new FormData();
    fd.append('title', title);
    fd.append('entry_type', document.getElementById('cr-att-type')?.value || 'evidencia');
    fd.append('file', file);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/bcp/activations/${actId}/attachments`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: fd,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Error al subir archivo');
      }
      UI.toast('Adjunto subido', 'success');
      await _renderCrisisRoomContent(actId, window._crModal);
      window._crCurrentTab = 'adjuntos';
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  async function _crDeleteAttachment(actId, eid) {
    if (!confirm('Eliminar este adjunto?')) return;
    try {
      await Api.del(`/api/bcp/activations/${actId}/attachments/${eid}`);
      UI.toast('Adjunto eliminado', 'success');
      await _renderCrisisRoomContent(actId, window._crModal);
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  async function _crGenerateAISummary(actId) {
    UI.toast('El agente IA esta analizando la evidencia...', 'info');
    try {
      const r = await Api.post(`/api/bcp/activations/${actId}/ai-summary`, {});
      UI.toast('Resumen generado', 'success');
      await _renderCrisisRoomContent(actId, window._crModal);
      window._crCurrentTab = 'adjuntos';
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  async function _crToggleChecklist(actId, order, checked) {
    try {
      await Api.patch(`/api/bcp/activations/${actId}/checklist/${order}`, { status: checked ? 'done' : 'pending' });
      await _renderCrisisRoomContent(actId, window._crModal);
      window._crCurrentTab = 'checklist';
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  async function _crSavePostMortem(actId) {
    const body = {
      executive_summary: document.getElementById('cr-pm-exec')?.value?.trim() || null,
      root_cause: document.getElementById('cr-pm-root')?.value?.trim() || null,
      lessons_learned: document.getElementById('cr-pm-lessons')?.value?.trim() || null,
      improvement_actions: (document.getElementById('cr-pm-improve')?.value?.trim() || '').split('\n').filter(Boolean),
    };
    try {
      await Api.patch(`/api/bcp/activations/${actId}`, body);
      UI.toast('Post-mortem guardado', 'success');
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  async function _openActivationReport(actId) {
    try {
      const data = await Api.get(`/api/bcp/activations/${actId}/report`);
      const act = data.activation;
      const inc = data.linked_incident;
      const dur = data.duration_minutes != null
        ? (data.duration_minutes > 60 ? Math.round(data.duration_minutes/60) + ' h ' + (data.duration_minutes%60) + ' min' : data.duration_minutes + ' min')
        : 'En curso';

      const existing = document.getElementById('modal-postmortem-dyn');
      if (existing) existing.remove();
      const modal = document.createElement('div');
      modal.id = 'modal-postmortem-dyn';
      modal.className = 'modal-bg';
      modal.innerHTML = `
      <div class="modal" style="max-width:780px;width:96vw;max-height:92vh;display:flex;flex-direction:column">
        <div class="modal-header" style="flex-shrink:0;border-bottom:2px solid var(--primary)">
          <h2><i class="ti ti-file-report"></i> Post-Mortem — ${UI.esc(act.code)} ${UI.esc(act.title)}</h2>
          <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
        </div>
        <div style="flex:1;overflow-y:auto;padding:20px 24px">
          <!-- 1. Resumen ejecutivo -->
          <div class="pm-section">
            <div class="pm-section-title">1. Resumen ejecutivo del incidente</div>
            <div class="pm-grid">
              <div><span class="pm-label">Codigo</span><span class="pm-val">${UI.esc(act.code||'—')}</span></div>
              <div><span class="pm-label">Fecha de deteccion</span><span class="pm-val">${act.activated_at?new Date(act.activated_at).toLocaleString('es-ES'):'—'}</span></div>
              <div><span class="pm-label">Duracion total</span><span class="pm-val">${dur}</span></div>
              <div><span class="pm-label">Estado final</span><span class="pm-val">${act.status === 'closed' ? 'Recuperado' : 'En curso'}</span></div>
            </div>
            ${act.executive_summary ? `<div style="margin-top:10px;font-size:13px">${UI.esc(act.executive_summary).replace(/\n/g,'<br>')}</div>` : '<div style="color:var(--text-subtle);font-size:12px;font-style:italic">Sin resumen ejecutivo. Completa el campo en la pestaña Post-Mortem de la sala de crisis.</div>'}
          </div>
          <!-- 2. Cronologia -->
          <div class="pm-section">
            <div class="pm-section-title">2. Cronologia detallada</div>
            ${(act.situation_log||[]).length === 0
              ? '<div style="color:var(--text-subtle);font-size:12px;font-style:italic">Sin eventos registrados.</div>'
              : `<table style="width:100%;border-collapse:collapse;font-size:12px">
                  <thead><tr style="border-bottom:1px solid var(--border)"><th style="text-align:left;padding:4px 8px;font-size:11px">Hora</th><th style="text-align:left;padding:4px 8px;font-size:11px">Tipo</th><th style="text-align:left;padding:4px 8px;font-size:11px">Descripcion</th><th style="text-align:left;padding:4px 8px;font-size:11px">Responsable</th></tr></thead>
                  <tbody>
                    ${(act.situation_log||[]).map(e => `<tr style="border-bottom:1px solid var(--border)">
                      <td style="padding:4px 8px;white-space:nowrap;font-size:11px">${new Date(e.timestamp).toLocaleString('es-ES',{dateStyle:'short',timeStyle:'short'})}</td>
                      <td style="padding:4px 8px"><span style="font-size:10px;font-weight:700;color:${_ACT_TYPE_COLORS[e.entry_type||'accion']||'#666'}">${_ACT_TYPE_LABELS[e.entry_type||'accion']||''}</span></td>
                      <td style="padding:4px 8px">${UI.esc(e.text||'')}</td>
                      <td style="padding:4px 8px;font-size:11px;color:var(--text-subtle)">${UI.esc(e.action_owner||e.user_email||'')}</td>
                    </tr>`).join('')}
                  </tbody>
                </table>`
            }
          </div>
          <!-- 3. Impacto -->
          <div class="pm-section">
            <div class="pm-section-title">3. Impacto en negocio y continuidad</div>
            <div class="pm-grid">
              <div><span class="pm-label">Planes activados</span><span class="pm-val">${(data.plans||[]).map(p=>UI.esc(p.name)).join(', ')||'—'}</span></div>
              <div><span class="pm-label">RTO objetivo</span><span class="pm-val">${act.rto_objective_hours!=null?act.rto_objective_hours+'h':'—'}</span></div>
              <div><span class="pm-label">RTO real</span><span class="pm-val">${act.rto_actual_hours!=null?act.rto_actual_hours+'h':'—'}</span></div>
              ${inc?`<div><span class="pm-label">Incidente vinculado</span><span class="pm-val">${UI.esc(inc.code)} — ${UI.esc(inc.title)}</span></div>`:''}
            </div>
          </div>
          <!-- 4. Causa raiz -->
          <div class="pm-section">
            <div class="pm-section-title">4. Analisis de causa raiz</div>
            ${act.root_cause
              ? `<div style="font-size:13px">${UI.esc(act.root_cause).replace(/\n/g,'<br>')}</div>`
              : '<div style="color:var(--text-subtle);font-size:12px;font-style:italic">Sin analisis de causa raiz registrado.</div>'
            }
          </div>
          <!-- 5. Evidencias -->
          <div class="pm-section">
            <div class="pm-section-title">5. Evidencias y adjuntos (${(data.attachments||[]).length})</div>
            ${(data.attachments||[]).length === 0
              ? '<div style="color:var(--text-subtle);font-size:12px;font-style:italic">Sin adjuntos.</div>'
              : `<div style="display:flex;flex-wrap:wrap;gap:8px">
                  ${(data.attachments||[]).map(a => `<div style="border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:11px;background:var(--bg-2)">
                    <a href="/api/bcp/evidence/${a.id}/download" target="_blank" style="color:var(--primary);font-weight:600">${UI.esc(a.file_name||a.title||'')}</a>
                    <span style="color:var(--text-subtle)"> (${a.file_size?Math.round(a.file_size/1024)+'KB':''})</span>
                  </div>`).join('')}
                </div>`
            }
            ${act.ai_summary ? `<div style="margin-top:10px;padding:10px;background:var(--bg-2);border-radius:6px;font-size:12px"><b><i class="ti ti-sparkles"></i> Resumen IA:</b><br>${UI.esc(act.ai_summary).replace(/\n/g,'<br>')}</div>` : ''}
          </div>
          <!-- 6. Eficacia respuesta -->
          <div class="pm-section">
            <div class="pm-section-title">6. Eficacia de la respuesta</div>
            <div class="pm-grid">
              <div><span class="pm-label">Checklist completado</span><span class="pm-val">${data.checklist_done}/${data.checklist_total} items</span></div>
              <div><span class="pm-label">Eventos registrados</span><span class="pm-val">${data.log_entries_count}</span></div>
              <div><span class="pm-label">Evidencias adjuntas</span><span class="pm-val">${(data.attachments||[]).length}</span></div>
            </div>
            ${act.lessons_learned
              ? `<div style="margin-top:8px;font-size:13px"><b>Lecciones aprendidas:</b><br>${UI.esc(act.lessons_learned).replace(/\n/g,'<br>')}</div>`
              : ''
            }
          </div>
          <!-- 7. Medidas correctivas -->
          <div class="pm-section">
            <div class="pm-section-title">7. Medidas correctivas y preventivas</div>
            ${(Array.isArray(act.improvement_actions) && act.improvement_actions.length)
              ? `<ul style="font-size:13px;margin:0;padding-left:18px">${act.improvement_actions.map(a=>`<li>${UI.esc(String(a))}</li>`).join('')}</ul>`
              : (act.improvement_actions
                  ? `<div style="font-size:13px">${UI.esc(String(act.improvement_actions)).replace(/\n/g,'<br>')}</div>`
                  : '<div style="color:var(--text-subtle);font-size:12px;font-style:italic">Sin acciones correctivas registradas.</div>'
                )
            }
          </div>
        </div>
        <div class="modal-footer-sticky" style="flex-shrink:0">
          <div style="display:flex;gap:8px;margin-left:auto">
            <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cerrar</button>
          </div>
        </div>
      </div>`;
      document.body.appendChild(modal);

      // Inject post-mortem styles if not present
      if (!document.getElementById('pm-styles')) {
        const st = document.createElement('style');
        st.id = 'pm-styles';
        st.textContent = `.pm-section{margin-bottom:18px;padding-bottom:14px;border-bottom:1px solid var(--border)}.pm-section:last-child{border-bottom:none}.pm-section-title{font-size:13px;font-weight:700;color:var(--primary);margin-bottom:10px;text-transform:uppercase;letter-spacing:.03em}.pm-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px}.pm-label{font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:2px}.pm-val{font-size:13px;display:block}`;
        document.head.appendChild(st);
      }
    } catch (e) { UI.toast('Error al cargar el informe: ' + e.message, 'error'); }
  }

  async function _modalActivacion(prefillPlanId) {
    const allPlans = await Api.get('/api/bcp/plans').catch(() => []);
    const plans = allPlans.filter(p => p.status === 'approved');
    const existing = document.getElementById('modal-activacion-dyn');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'modal-activacion-dyn';
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:500px;">
      <div class="modal-header" style="border-bottom:2px solid #DC2626;">
        <h2 style="color:#DC2626;"><i class="ti ti-alert-triangle"></i> Activar BCP / DRP</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:20px 24px;">
        <div class="notice notice-warning" style="margin-bottom:14px;font-size:13px;">
          Usa este boton <strong>unicamente</strong> ante un incidente real que requiera activar los planes de continuidad.
        </div>
        ${!plans.length ? `
          <div class="notice notice-error" style="margin-bottom:14px;font-size:13px;">
            No hay planes aprobados. Aprueba un plan antes de poder activarlo.
          </div>
        ` : ''}
        <div style="margin-bottom:14px;">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px;">Plan a activar <span style="color:var(--danger)">*</span></label>
          <select id="act-plan-sel" class="form-control" style="font-size:13px;" ${!plans.length ? 'disabled' : ''}>
            <option value="">— Seleccionar plan —</option>
            ${plans.map(p => `<option value="${p.id}">${UI.esc(p.code ? p.code+' — ' : '')}${UI.esc(p.name)}</option>`).join('')}
          </select>
        </div>

        <!-- Panel de contexto del plan — se rellena al seleccionar -->
        <div id="act-plan-ctx" style="display:none;margin-bottom:14px;padding:10px 14px;background:rgba(220,38,38,.06);border:1px solid rgba(220,38,38,.2);border-radius:6px;font-size:12px;">
          <div style="font-weight:700;font-size:11px;text-transform:uppercase;color:#DC2626;margin-bottom:8px;letter-spacing:.04em"><i class="ti ti-info-circle"></i> Contexto del plan</div>
          <div id="act-ctx-comms" style="margin-bottom:8px"></div>
          <div id="act-ctx-suppliers" style="margin-bottom:8px"></div>
          <div id="act-ctx-activators"></div>
        </div>

        ${window._pendingBcpIncidentTitle ? `
        <div style="margin-bottom:14px;padding:8px 12px;background:rgba(220,38,38,.08);border:1px solid rgba(220,38,38,.3);border-radius:6px;font-size:12px;">
          <i class="ti ti-link"></i> Vinculado al incidente <strong>${UI.esc(window._pendingBcpIncidentTitle)}</strong> — se enlazara automaticamente al activar.
        </div>` : ''}
        <div style="margin-bottom:14px;">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px;">Nombre / descripcion del incidente <span style="color:var(--danger)">*</span></label>
          <input id="act-incident" class="form-control" style="font-size:13px;" placeholder="Ej: Ransomware detectado en servidor de BD" value="${UI.esc(window._pendingBcpIncidentTitle || '')}">
        </div>
        <div style="margin-bottom:14px;">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px;">Notas iniciales</label>
          <textarea id="act-notes" class="form-control" rows="2" style="font-size:13px;" placeholder="Descripcion breve del estado actual..."></textarea>
        </div>

        <!-- Timeline inicial -->
        <div style="padding:8px 12px;background:var(--bg-2);border-radius:6px;font-size:11px;color:var(--text-subtle)">
          <i class="ti ti-clock"></i> Hora de activacion: <strong id="act-ts">${new Date().toLocaleString('es-ES',{dateStyle:'short',timeStyle:'short'})}</strong>
          &nbsp;·&nbsp; El sistema registrara esta marca temporal como T=0.
        </div>

      </div>
      <div class="modal-footer-sticky">
        <div style="display:flex;gap:8px;margin-left:auto;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-sm" id="act-confirm-btn" style="background:#DC2626;color:#fff;font-weight:700;border-color:#DC2626;" ${!plans.length ? 'disabled' : ''}>
            <i class="ti ti-alert-triangle"></i> CONFIRMAR ACTIVACION
          </button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#act-confirm-btn').addEventListener('click', () => _confirmActivacion(modal));

    // Pre-seleccionar plan si viene del menu contextual
    if (prefillPlanId) {
      const sel = modal.querySelector('#act-plan-sel');
      if (sel) {
        sel.value = String(prefillPlanId);
        sel.dispatchEvent(new Event('change'));
      }
    }

    // Cargar contexto del plan al seleccionar
    modal.querySelector('#act-plan-sel').addEventListener('change', async function() {
      const pid = parseInt(this.value);
      const ctxPanel = modal.querySelector('#act-plan-ctx');
      if (!pid) { ctxPanel.style.display = 'none'; return; }
      try {
        const ctx = await Api.get(`/api/bcp/plans/${pid}/context`);
        const plan = ctx.plan || {};
        const cr = plan.crisis_comms || {};
        const activators = plan.authorized_activators || [];
        const suppliers = (ctx.processes || []).flatMap(p => p.suppliers || []);
        const uniqSup = [...new Map(suppliers.map(s => [s.supplier_id || s.supplier_name, s])).values()];

        const commsHtml = (cr.primary_channel || cr.secondary_channel)
          ? `<div style="margin-bottom:4px"><span style="font-weight:600">Canales:</span>
              ${cr.primary_channel ? `<span class="badge badge-secondary" style="font-size:10px">${UI.esc(cr.primary_channel)}</span>` : ''}
              ${cr.secondary_channel ? `<span class="badge badge-secondary" style="font-size:10px">${UI.esc(cr.secondary_channel)}</span>` : ''}
              ${cr.external_channel ? `<span class="badge badge-secondary" style="font-size:10px">${UI.esc(cr.external_channel)}</span>` : ''}
            </div>
            ${cr.template_internal ? `<div style="margin-top:4px;font-size:11px;color:var(--text-subtle)">Plantilla interna disponible — aparecera en "Mensaje a stakeholders"</div>` : ''}`
          : '<div style="color:var(--text-subtle)">Sin canales de comunicacion configurados en el plan.</div>';

        const supHtml = uniqSup.length
          ? `<div style="font-weight:600;margin-bottom:4px">Proveedores criticos afectados (${uniqSup.length}):</div>
             <div style="display:flex;flex-wrap:wrap;gap:4px">
               ${uniqSup.map(s => `<span class="badge badge-secondary" style="font-size:10px">${UI.esc(s.supplier_name || '')}</span>`).join('')}
             </div>`
          : '';

        const actHtml = activators.length
          ? `<div style="font-weight:600;margin-bottom:4px">Autorizadores:</div>
             <div style="display:flex;flex-wrap:wrap;gap:4px">
               ${activators.map(a => `<span class="badge" style="font-size:10px;background:rgba(220,38,38,.12);color:#dc2626">${UI.esc(a.name)}${a.is_deputy?' (suplente)':''}</span>`).join('')}
             </div>`
          : '';

        modal.querySelector('#act-ctx-comms').innerHTML      = commsHtml;
        modal.querySelector('#act-ctx-suppliers').innerHTML  = supHtml;
        modal.querySelector('#act-ctx-activators').innerHTML = actHtml;
        ctxPanel.style.display = '';

        // Pre-rellenar notas con plantilla interna si existe
        const notesEl = modal.querySelector('#act-notes');
        if (cr.template_internal && !notesEl.value) {
          notesEl.value = cr.template_internal;
        }
      } catch { ctxPanel.style.display = 'none'; }
    });
  }

  function _closeActModal() {
    document.getElementById('modal-activacion-dyn')?.remove();
  }

  async function _confirmActivacion(modal) {
    const root = modal || document.getElementById('modal-activacion-dyn') || document;
    const planId = root.querySelector('#act-plan-sel')?.value;
    const incident = root.querySelector('#act-incident')?.value?.trim();
    if (!planId || !incident) { UI.toast('Completa el plan y el nombre del incidente', 'error'); return; }
    const pendingIncId = window._pendingBcpIncidentId || null;
    try {
      const payload = {
        activated_plan_ids: [parseInt(planId)],
        title: incident,
        notes: root.querySelector('#act-notes')?.value || '',
      };
      if (pendingIncId) payload.incident_id = pendingIncId;
      const act = await Api.post('/api/bcp/activations', payload);
      // Back-link: update incident with the new activation id
      if (pendingIncId && act && act.id) {
        Api.patch(`/api/incidents/${pendingIncId}`, { bcp_activation_id: act.id }).catch(() => {});
      }
      window._pendingBcpIncidentId = null;
      window._pendingBcpIncidentTitle = null;
      _closeActModal();
      UI.toast('BCP activado.', 'warning');
      _setTile('activaciones');
      if (act && act.checklist_items && act.checklist_items.length) {
        _openChecklistModal(act);
      }
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  function _openChecklistModal(act) {
    const existing = document.getElementById('modal-checklist-dyn');
    if (existing) existing.remove();
    const ACTION_LABELS = {
      manual: '',
      notify_users: 'Notificar',
      create_task: 'Crear tarea',
      log_timeline: 'Registrar',
    };
    const renderItem = (item) => {
      const isDone = item.status === 'done';
      const hasAction = item.action_type && item.action_type !== 'manual';
      return `
        <div class="checklist-item" data-order="${item.order}" style="display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:1px solid var(--border);">
          <input type="checkbox" class="chk-item" data-order="${item.order}" ${isDone ? 'checked' : ''}
            style="margin-top:3px;width:16px;height:16px;flex-shrink:0;cursor:${isDone ? 'default' : 'pointer'}" ${isDone ? 'disabled' : ''}>
          <div style="flex:1;min-width:0">
            <div style="font-size:13px;font-weight:${isDone ? '400' : '600'};color:${isDone ? 'var(--text-subtle)' : 'var(--text)'};text-decoration:${isDone ? 'line-through' : 'none'}">${UI.esc(item.title)}</div>
            ${item.description ? `<div style="font-size:11px;color:var(--text-subtle);margin-top:2px">${UI.esc(item.description)}</div>` : ''}
            ${isDone && item.executed_by ? `<div style="font-size:10px;color:var(--text-subtle);margin-top:2px">Ejecutado por ${UI.esc(item.executed_by)}</div>` : ''}
          </div>
          ${!isDone && hasAction ? `
            <button class="btn btn-sm btn-exec" data-order="${item.order}" data-actid="${act.id}"
              style="font-size:11px;flex-shrink:0;white-space:nowrap;">
              <i class="ti ti-bolt"></i> ${ACTION_LABELS[item.action_type] || 'Ejecutar'}
            </button>
          ` : ''}
        </div>
      `;
    };

    const modal = document.createElement('div');
    modal.id = 'modal-checklist-dyn';
    modal.className = 'modal-bg';
    const items = act.checklist_items || [];
    modal.innerHTML = `
    <div class="modal" style="max-width:580px;">
      <div class="modal-header" style="border-bottom:2px solid var(--brand-purple);">
        <h2><i class="ti ti-checklist"></i> Checklist de activacion — ${UI.esc(act.code||'')} ${UI.esc(act.title||'')}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:16px 24px;max-height:60vh;overflow-y:auto;">
        <div style="font-size:12px;color:var(--text-subtle);margin-bottom:12px">
          ${items.filter(i=>i.status==='done').length} / ${items.length} acciones completadas
        </div>
        <div id="checklist-items-container">
          ${items.map(renderItem).join('')}
        </div>
      </div>
      <div class="modal-footer-sticky">
        <div style="display:flex;gap:8px;margin-left:auto;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cerrar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);

    // Checkboxes manuales
    modal.querySelectorAll('.chk-item').forEach(chk => {
      chk.addEventListener('change', async () => {
        const order = parseInt(chk.dataset.order);
        try {
          const res = await Api.patch(`/api/bcp/activations/${act.id}/checklist/${order}`, { status: chk.checked ? 'done' : 'pending' });
          act.checklist_items = res.checklist_items;
          _refreshChecklist(modal, act, renderItem);
        } catch (e) { UI.toast('Error: ' + e.message, 'error'); chk.checked = !chk.checked; }
      });
    });

    // Botones de accion automatica
    modal.querySelectorAll('.btn-exec').forEach(btn => {
      btn.addEventListener('click', async () => {
        const order = parseInt(btn.dataset.order);
        btn.disabled = true;
        btn.innerHTML = '<i class="ti ti-loader"></i> Ejecutando...';
        try {
          const res = await Api.post(`/api/bcp/activations/${act.id}/checklist/${order}/execute`, {});
          act.checklist_items = res.checklist_items;
          _refreshChecklist(modal, act, renderItem);
          UI.toast('Accion ejecutada.', 'success');
        } catch (e) { UI.toast('Error: ' + e.message, 'error'); btn.disabled = false; btn.innerHTML = '<i class="ti ti-bolt"></i> Ejecutar'; }
      });
    });
  }

  function _refreshChecklist(modal, act, renderItem) {
    const container = modal.querySelector('#checklist-items-container');
    if (container) container.innerHTML = (act.checklist_items || []).map(renderItem).join('');
    const summary = modal.querySelector('.modal-body > div:first-child');
    if (summary) {
      const items = act.checklist_items || [];
      summary.textContent = `${items.filter(i=>i.status==='done').length} / ${items.length} acciones completadas`;
    }
    // Rebind events
    modal.querySelectorAll('.chk-item:not([disabled])').forEach(chk => {
      chk.addEventListener('change', async () => {
        const order = parseInt(chk.dataset.order);
        try {
          const res = await Api.patch(`/api/bcp/activations/${act.id}/checklist/${order}`, { status: chk.checked ? 'done' : 'pending' });
          act.checklist_items = res.checklist_items;
          _refreshChecklist(modal, act, renderItem);
        } catch (e) { UI.toast('Error: ' + e.message, 'error'); chk.checked = !chk.checked; }
      });
    });
    modal.querySelectorAll('.btn-exec').forEach(btn => {
      btn.addEventListener('click', async () => {
        const order = parseInt(btn.dataset.order);
        btn.disabled = true;
        btn.innerHTML = '<i class="ti ti-loader"></i> Ejecutando...';
        try {
          const res = await Api.post(`/api/bcp/activations/${act.id}/checklist/${order}/execute`, {});
          act.checklist_items = res.checklist_items;
          _refreshChecklist(modal, act, renderItem);
          UI.toast('Accion ejecutada.', 'success');
        } catch (e) { UI.toast('Error: ' + e.message, 'error'); btn.disabled = false; btn.innerHTML = '<i class="ti ti-bolt"></i> Ejecutar'; }
      });
    });
  }

  function _logActivacion(aid) {
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:460px;">
      <div class="modal-header">
        <h2>Registrar evento</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:20px 24px;">
        <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:6px;">Mensaje del evento <span style="color:var(--danger)">*</span></label>
        <textarea id="log-msg" class="form-control" rows="3" style="font-size:13px;" placeholder="Describe lo que ha ocurrido en este momento..."></textarea>
      </div>
      <div class="modal-footer-sticky">
        <div style="display:flex;gap:8px;margin-left:auto;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-primary btn-sm" id="log-submit"><i class="ti ti-send"></i> Registrar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#log-msg').focus();
    modal.querySelector('#log-submit').addEventListener('click', async () => {
      const msg = modal.querySelector('#log-msg').value.trim();
      if (!msg) { UI.toast('El mensaje no puede estar vacio', 'error'); return; }
      try {
        await Api.post('/api/bcp/activations/' + aid + '/log', { message: msg });
        modal.remove();
        _setTile('activaciones');
      } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
    });
  }

  function _closeActivacion(aid) {
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:460px;">
      <div class="modal-header">
        <h2>Cerrar activacion</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:20px 24px;">
        <div class="notice notice-warning" style="margin-bottom:14px;font-size:13px;">Se cerrara la activacion y se registrara un incidente automaticamente.</div>
        <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:6px;">Notas de cierre</label>
        <textarea id="close-notes" class="form-control" rows="3" style="font-size:13px;" placeholder="Resumen de la respuesta y acciones tomadas..."></textarea>
      </div>
      <div class="modal-footer-sticky">
        <div style="display:flex;gap:8px;margin-left:auto;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-danger btn-sm" id="close-submit"><i class="ti ti-lock"></i> Cerrar activacion</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#close-notes').focus();
    modal.querySelector('#close-submit').addEventListener('click', async () => {
      const notes = modal.querySelector('#close-notes').value;
      try {
        await Api.post('/api/bcp/activations/' + aid + '/close', { closure_notes: notes });
        UI.toast('Activacion cerrada. Se ha registrado el incidente.', 'success');
        modal.remove();
        _setTile('activaciones');
      } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
    });
  }

  // ── Tile: Calendario de tests ─────────────────────────────────────────────────

  async function _tileCalendarioTests(container) {
    const tests = await Api.get('/api/bcp/tests' + _locParam()).catch(() => []);
    const now = new Date();
    const ms30 = 30 * 86400000;
    const ms90 = 90 * 86400000;

    // Agrupar por mes (próximos 6 meses + vencidos)
    const overdue = [];
    const upcoming = {};
    const done = [];

    for (let i = 0; i < 7; i++) {
      const d = new Date(now);
      d.setMonth(d.getMonth() + i);
      const key = d.toISOString().slice(0, 7);
      upcoming[key] = [];
    }

    tests.forEach(t => {
      const sched = t.scheduled_date ? new Date(t.scheduled_date) : null;
      const exec  = t.executed_date  ? new Date(t.executed_date)  : null;
      if (exec || t.status === 'completed' || t.status === 'passed' || t.status === 'failed') {
        done.push(t);
      } else if (sched) {
        if (sched < now) {
          overdue.push(t);
        } else {
          const key = sched.toISOString().slice(0, 7);
          if (upcoming[key]) upcoming[key].push(t);
          else { upcoming[key] = [t]; }
        }
      }
    });

    const monthName = key => {
      const [y, m] = key.split('-');
      return new Date(y, parseInt(m) - 1, 1).toLocaleDateString('es-ES', { month: 'long', year: 'numeric' });
    };

    const testRow = t => {
      const sched = t.scheduled_date ? new Date(t.scheduled_date).toLocaleDateString('es-ES') : '—';
      const diff = t.scheduled_date ? Math.round((new Date(t.scheduled_date) - now) / 86400000) : null;
      const urgColor = diff !== null && diff <= 14 ? '#DC2626' : diff !== null && diff <= 30 ? '#D97706' : '#16a34a';
      return `<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:6px;background:var(--bg-2);margin-bottom:4px;font-size:12px">
        <i class="ti ti-clipboard-check" style="color:${urgColor};flex-shrink:0"></i>
        <div style="flex:1">
          <div style="font-weight:600">${UI.esc(t.name||t.test_type||'Test')}</div>
          <div style="color:var(--text-subtle);font-size:11px">${UI.esc(t.test_type||'')} · ${sched}${diff!==null?' · en '+diff+' días':''}</div>
        </div>
        <button class="btn btn-ghost btn-sm" style="font-size:10px;padding:2px 6px" onclick="ViewBcp._openTestModal(${t.id})">Ver</button>
      </div>`;
    };

    let html = '';

    if (overdue.length) {
      html += `<div class="bcm-cal-month">
        <div class="bcm-cal-month-header" style="color:#DC2626">
          <i class="ti ti-alert-circle"></i> VENCIDOS (${overdue.length})
        </div>
        ${overdue.map(testRow).join('')}
      </div>`;
    }

    const sortedMonths = Object.keys(upcoming).sort();
    sortedMonths.forEach(key => {
      const items = upcoming[key];
      if (!items.length && key < now.toISOString().slice(0, 7)) return;
      const isCurrentMonth = key === now.toISOString().slice(0, 7);
      html += `<div class="bcm-cal-month">
        <div class="bcm-cal-month-header" style="${isCurrentMonth ? 'color:var(--primary);font-weight:800' : ''}">
          <i class="ti ti-calendar"></i> ${monthName(key)}
          ${items.length ? `<span class="badge badge-secondary" style="margin-left:auto">${items.length}</span>` : '<span style="margin-left:auto;font-size:11px;color:var(--text-subtle)">Sin tests</span>'}
        </div>
        ${items.length ? items.map(testRow).join('') : '<div style="font-size:12px;color:var(--text-subtle);padding:4px 8px">Mes libre — considera programar un ejercicio tabletop.</div>'}
      </div>`;
    });

    if (done.length) {
      html += `<details style="margin-top:8px">
        <summary style="font-size:12px;font-weight:700;color:var(--text-subtle);cursor:pointer;padding:4px 0">
          <i class="ti ti-check"></i> Tests completados (${done.length})
        </summary>
        <div style="margin-top:8px">
          ${done.slice(0, 20).map(t => {
            const ex = t.executed_date ? new Date(t.executed_date).toLocaleDateString('es-ES') : '—';
            const col = t.status === 'passed' ? '#16a34a' : t.status === 'failed' ? '#DC2626' : '#6B7280';
            return `<div style="display:flex;align-items:center;gap:8px;padding:5px 8px;font-size:12px;border-bottom:1px solid var(--border)">
              <i class="ti ti-circle-check" style="color:${col}"></i>
              <span style="flex:1">${UI.esc(t.name||t.test_type||'Test')}</span>
              <span style="color:var(--text-subtle)">${ex}</span>
              <span style="color:${col};font-weight:700">${t.status||'—'}</span>
            </div>`;
          }).join('')}
        </div>
      </details>`;
    }

    if (!html) {
      html = '<div class="notice notice-info">No hay tests programados. Crea tests en la pestaña "Lista de tests".</div>';
    }

    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
        <div>
          <div style="font-size:14px;font-weight:700">Calendario de Tests ISO 22301</div>
          <div style="font-size:11px;color:var(--text-subtle)">ISO 22301 cl. 8.5 / 9.1 — Pruebas y ejercicios de continuidad</div>
        </div>
        <button class="btn btn-primary btn-sm" onclick="ViewBcp._openTestModal(null)">
          <i class="ti ti-plus"></i> Programar test
        </button>
      </div>
      <div style="display:flex;gap:10px;margin-bottom:14px">
        <div class="bcm-kpi" style="flex:1;border-top:3px solid #DC2626;padding:10px 12px">
          <div class="bcm-kpi-label">Vencidos</div>
          <div class="bcm-kpi-val" style="font-size:20px;color:#DC2626">${overdue.length}</div>
        </div>
        <div class="bcm-kpi" style="flex:1;border-top:3px solid #D97706;padding:10px 12px">
          <div class="bcm-kpi-label">Proximos 30 dias</div>
          <div class="bcm-kpi-val" style="font-size:20px;color:#D97706">${Object.values(upcoming).flat().filter(t => {
            const d = new Date(t.scheduled_date);
            return d >= now && d <= new Date(now.getTime() + ms30);
          }).length}</div>
        </div>
        <div class="bcm-kpi" style="flex:1;border-top:3px solid #16a34a;padding:10px 12px">
          <div class="bcm-kpi-label">Completados</div>
          <div class="bcm-kpi-val" style="font-size:20px;color:#16a34a">${done.length}</div>
        </div>
      </div>
      <div class="bcm-cal-grid">${html}</div>
    `;
  }

  // ── Tile: Runbooks ────────────────────────────────────────────────────────────

  async function _tileRunbooks(container) {
    const [runbooks, plans] = await Promise.all([
      Api.get('/api/bcp/runbooks').catch(() => []),
      Api.get('/api/bcp/plans').catch(() => []),
    ]);
    const planMap = {};
    plans.forEach(p => { planMap[p.id] = p; });

    container.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
        <div>
          <div style="font-size:14px;font-weight:700">Runbooks de recuperacion</div>
          <div style="font-size:11px;color:var(--text-subtle)">Procedimientos paso a paso enlazados a planes BCP/DRP</div>
        </div>
        <button class="btn btn-primary btn-sm" onclick="ViewBcp._newRunbook()">
          <i class="ti ti-plus"></i> Nuevo runbook
        </button>
      </div>
      ${!runbooks.length
        ? `<div class="notice notice-info">
            Sin runbooks. Los runbooks son procedimientos detallados paso a paso para recuperar sistemas o procesos.
            <button class="btn btn-sm btn-secondary" style="margin-left:10px" onclick="ViewBcp._newRunbook()">Crear primero</button>
          </div>`
        : `<div style="display:flex;flex-direction:column;gap:10px">
            ${runbooks.map(rb => {
              const plan = planMap[rb.plan_id];
              const steps = rb.steps || [];
              const doneSteps = steps.filter(s => s.done).length;
              return `<div class="card" style="padding:14px">
                <div style="display:flex;align-items:flex-start;gap:10px">
                  <div style="width:36px;height:36px;border-radius:50%;background:var(--primary)18;display:flex;align-items:center;justify-content:center;flex-shrink:0">
                    <i class="ti ti-checklist" style="color:var(--primary)"></i>
                  </div>
                  <div style="flex:1;min-width:0">
                    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                      <strong style="font-size:13px">${UI.esc(rb.title||'Sin nombre')}</strong>
                      ${plan ? `<span class="badge badge-secondary" style="font-size:10px">${UI.esc(plan.code||plan.name)}</span>` : ''}
                      <span class="badge" style="font-size:10px;background:${rb.runbook_type==='recovery'?'#16a34a22':rb.runbook_type==='failover'?'#D9770622':'#59008D22'};color:${rb.runbook_type==='recovery'?'#16a34a':rb.runbook_type==='failover'?'#D97706':'#59008D'}">
                        ${rb.runbook_type||'general'}
                      </span>
                    </div>
                    ${rb.scenario ? `<div style="font-size:12px;color:var(--text-subtle);margin-top:3px">${UI.esc(rb.scenario)}</div>` : ''}
                    ${rb.activation_condition ? `
                      <div style="font-size:11px;margin-top:5px;padding:4px 8px;background:var(--bg-2);border-left:3px solid var(--brand-orange,#D65200);border-radius:0 3px 3px 0;">
                        <span style="font-weight:700;color:var(--text-subtle)">Activacion:</span>
                        <span style="color:var(--text-subtle)">&nbsp;${UI.esc(rb.activation_condition.length>100 ? rb.activation_condition.slice(0,100)+'...' : rb.activation_condition)}</span>
                      </div>` : ''}
                    ${rb.responsible_name ? `
                      <div style="font-size:11px;color:var(--text-subtle);margin-top:4px;">
                        <i class="ti ti-user-check" style="margin-right:3px"></i><strong>Responsable:</strong>&nbsp;${UI.esc(rb.responsible_name)}
                        ${rb.backup_responsible_name ? `&nbsp;<span style="color:var(--text-muted)">/ ${UI.esc(rb.backup_responsible_name)}</span>` : ''}
                      </div>` : ''}
                    ${rb.success_criteria ? `
                      <div style="font-size:11px;margin-top:4px;color:var(--text-subtle);">
                        <i class="ti ti-circle-check" style="margin-right:3px;color:#16a34a"></i><strong>Exito:</strong>&nbsp;${UI.esc(rb.success_criteria.length>90 ? rb.success_criteria.slice(0,90)+'...' : rb.success_criteria)}
                      </div>` : ''}
                    ${steps.length ? `
                      <div style="margin-top:8px">
                        <div style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text-subtle);margin-bottom:4px">
                          <span>${doneSteps}/${steps.length} pasos completados</span>
                          <div style="flex:1;height:4px;background:var(--bg-3,#222);border-radius:2px">
                            <div style="width:${steps.length?Math.round(doneSteps/steps.length*100):0}%;height:100%;background:#16a34a;border-radius:2px"></div>
                          </div>
                        </div>
                        ${steps.slice(0, 4).map((s, i) => `
                          <div style="display:flex;align-items:center;gap:6px;font-size:12px;padding:2px 0">
                            <span style="width:18px;height:18px;border-radius:50%;background:${s.done?'#16a34a':'var(--border)'};color:${s.done?'#fff':'var(--text-subtle)'};display:inline-flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;flex-shrink:0">${s.done?'✓':i+1}</span>
                            <span style="color:${s.done?'var(--text-subtle)':'var(--text)'}${s.done?';text-decoration:line-through':''}">${UI.esc(s.description||s.title||'Paso '+(i+1))}</span>
                          </div>
                        `).join('')}
                        ${steps.length > 4 ? `<div style="font-size:11px;color:var(--text-subtle);margin-top:2px">+ ${steps.length-4} pasos mas...</div>` : ''}
                      </div>
                    ` : ''}
                  </div>
                  <div style="display:flex;gap:4px;flex-shrink:0">
                    <button class="btn btn-ghost btn-sm" onclick="ViewBcp._editRunbook(${rb.id})">
                      <i class="ti ti-edit"></i>
                    </button>
                    <button class="btn btn-ghost btn-sm" onclick="ViewBcp._genAiRunbook(${rb.id})"
                      title="Generar pasos con IA">
                      <i class="ti ti-sparkles"></i>
                    </button>
                  </div>
                </div>
              </div>`;
            }).join('')}
          </div>`
      }
    `;
  }

  async function _newRunbook() {
    const plans = await Api.get('/api/bcp/plans').catch(() => []);
    const RB_TYPES = [
      {v:'recovery', l:'Recuperacion'},
      {v:'failover', l:'Failover'},
      {v:'general',  l:'General'},
    ];
    const lbl = t => `<label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px;">${t}</label>`;
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:640px;">
      <div class="modal-header">
        <h2>Nuevo runbook</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:20px 24px;">
        <div style="margin-bottom:14px;">
          ${lbl('Nombre <span style="color:var(--danger)">*</span>')}
          <input id="rb-name" class="form-control" style="font-size:13px;" placeholder="Ej: PROC-01 · Recuperacion Active Directory">
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>${lbl('Plan BCP/DRP asociado')}
            <select id="rb-plan" class="form-control" style="font-size:13px;">
              <option value="">— Ninguno —</option>
              ${plans.map(p=>`<option value="${p.id}">${UI.esc(p.code ? p.code+' — '+p.name : p.name)}</option>`).join('')}
            </select>
          </div>
          <div>${lbl('Tipo')}
            <select id="rb-type" class="form-control" style="font-size:13px;" onchange="
              document.getElementById('rb-tpl-btn').style.display=this.value==='recovery'?'':'none';
            ">
              ${RB_TYPES.map(t=>`<option value="${t.v}">${t.l}</option>`).join('')}
            </select>
          </div>
        </div>
        <div style="margin-bottom:14px;">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
            ${lbl('Descripcion / Objetivo')}
            <button id="rb-tpl-btn" class="btn btn-ghost btn-sm" style="font-size:11px;padding:2px 8px;display:none" onclick="
              document.getElementById('rb-desc').value=
'FASE 1 — DETECCION Y NOTIFICACION\n' +
'Criterio de entrada: Alerta recibida o incidente detectado.\n' +
'Acciones: Notificar al responsable titular y al Crisis Lead. Confirmar el alcance del impacto. Abrir el registro de activacion.\n\n' +
'FASE 2 — ACTIVACION DEL PLAN\n' +
'Criterio de entrada: Incidente confirmado y aprobacion del Crisis Lead.\n' +
'Acciones: Declarar activacion formal. Convocar al equipo de recuperacion. Comunicar a stakeholders internos (canal primario). Acceder a la boveda de credenciales.\n\n' +
'FASE 3 — RECUPERACION TECNICA\n' +
'Criterio de entrada: Recursos de recuperacion disponibles.\n' +
'Acciones: Ejecutar procedimientos tecnicos en el orden definido por secuencia de dependencias. Restaurar backups. Verificar integridad de datos. Activar el DR Site si aplica.\n\n' +
'FASE 4 — RECONSTITUCION Y VALIDACION\n' +
'Criterio de entrada: Sistemas tecnicamente operativos.\n' +
'Acciones: Ejecutar pruebas funcionales con usuarios piloto. Verificar criterio de exito documentado. Comunicar reanudacion a stakeholders. Desactivar el DR Site.\n\n' +
'FASE 5 — CIERRE Y REVISION POST-INCIDENTE\n' +
'Criterio de entrada: Servicio restaurado al nivel MBCO o superior.\n' +
'Acciones: Declarar cierre formal de la activacion. Documentar RTO real. Registrar lecciones aprendidas. Programar revision de plan en los 30 dias siguientes.';
            "><i class="ti ti-template"></i> Plantilla 5 fases</button>
          </div>
          <textarea id="rb-desc" class="form-control" rows="4" style="font-size:13px;" placeholder="Objetivo y alcance de este runbook..."></textarea>
        </div>
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);letter-spacing:.05em;margin:16px 0 10px;padding-top:12px;border-top:1px solid var(--border);">Campos DRP — ISO 22301 §8.4.3</div>
        <div style="margin-bottom:14px;">
          ${lbl('Condicion de activacion')}
          <textarea id="rb-actcond" class="form-control" rows="2" style="font-size:13px;" placeholder="Ej: Servidor principal inaccesible >15 min o fallo total de autenticacion en red."></textarea>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>${lbl('Responsable titular')}
            <input id="rb-resp" class="form-control" style="font-size:13px;" placeholder="Nombre · Cargo">
          </div>
          <div>${lbl('Suplente')}
            <input id="rb-backup" class="form-control" style="font-size:13px;" placeholder="Nombre · Cargo">
          </div>
        </div>
        <div style="margin-bottom:14px;">
          ${lbl('Referencia boveda de credenciales')}
          <input id="rb-vault" class="form-control" style="font-size:13px;" placeholder="Ej: Boveda: carpeta AD-Recovery · Acceso: Crisis Lead + Tech Lead">
        </div>
        <div style="margin-bottom:14px;">
          ${lbl('Criterio de exito (verificacion)')}
          <textarea id="rb-success" class="form-control" rows="2" style="font-size:13px;" placeholder="Ej: Login exitoso de 5 usuarios de prueba en 3 segmentos de red distintos."></textarea>
        </div>
      </div>
      <div class="modal-footer-sticky">
        <div style="display:flex;gap:8px;margin-left:auto;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-primary btn-sm" id="rb-submit"><i class="ti ti-check"></i> Crear runbook</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);

    // Pre-seleccionar plan del contexto actual si existe
    if (_currentPlanId) {
      const planSel = modal.querySelector('#rb-plan');
      if (planSel) planSel.value = String(_currentPlanId);
    }

    // Auto-aplicar plantilla 5 fases cuando tipo=recovery (valor por defecto)
    const typeSelRb = modal.querySelector('#rb-type');
    const descAreaRb = modal.querySelector('#rb-desc');
    const tplBtnRb   = modal.querySelector('#rb-tpl-btn');
    const _applyTpl = () => {
      if (typeSelRb.value === 'recovery' && !descAreaRb.value.trim()) {
        tplBtnRb.click();
      }
      tplBtnRb.style.display = typeSelRb.value === 'recovery' ? '' : 'none';
    };
    _applyTpl();
    typeSelRb.addEventListener('change', _applyTpl);

    modal.querySelector('#rb-name').focus();
    modal.querySelector('#rb-submit').addEventListener('click', async () => {
      const title = modal.querySelector('#rb-name').value.trim();
      if (!title) { UI.toast('El nombre es obligatorio', 'error'); return; }
      const btn = modal.querySelector('#rb-submit');
      btn.disabled = true;
      try {
        await Api.post('/api/bcp/runbooks', {
          title,
          plan_id: parseInt(modal.querySelector('#rb-plan').value) || null,
          test_type: modal.querySelector('#rb-type').value,
          scenario: modal.querySelector('#rb-desc').value.trim() || null,
          activation_condition:  modal.querySelector('#rb-actcond').value.trim() || null,
          credentials_vault_ref: modal.querySelector('#rb-vault').value.trim()   || null,
          success_criteria:      modal.querySelector('#rb-success').value.trim() || null,
          responsible_name:      modal.querySelector('#rb-resp').value.trim()    || null,
          backup_responsible_name: modal.querySelector('#rb-backup').value.trim() || null,
          steps: [],
        });
        UI.toast('Runbook creado', 'success');
        modal.remove();
        _setSubTab(4, 'runbooks');
      } catch (e) { UI.toast('Error: ' + e.message, 'error'); btn.disabled = false; }
    });
  }

  async function _editRunbook(rid) {
    const rb = await Api.get('/api/bcp/runbooks').then(list => list.find(r => r.id === rid)).catch(() => null);
    if (!rb) return;
    const plans = await Api.get('/api/bcp/plans').catch(() => []);
    const RB_TYPES = [
      {v:'recovery', l:'Recuperacion'},
      {v:'failover', l:'Failover'},
      {v:'general',  l:'General'},
    ];
    const lbl = t => `<label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px;">${t}</label>`;
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:640px;">
      <div class="modal-header">
        <h2>Editar runbook</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:20px 24px;">
        <div style="margin-bottom:14px;">
          ${lbl('Nombre <span style="color:var(--danger)">*</span>')}
          <input id="rbe-name" class="form-control" style="font-size:13px;" value="${UI.esc(rb.title||'')}">
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>${lbl('Plan BCP/DRP asociado')}
            <select id="rbe-plan" class="form-control" style="font-size:13px;">
              <option value="">— Ninguno —</option>
              ${plans.map(p=>`<option value="${p.id}"${rb.plan_id===p.id?' selected':''}>${UI.esc(p.code ? p.code+' — '+p.name : p.name)}</option>`).join('')}
            </select>
          </div>
          <div>${lbl('Tipo')}
            <select id="rbe-type" class="form-control" style="font-size:13px;">
              ${RB_TYPES.map(t=>`<option value="${t.v}"${rb.test_type===t.v?' selected':''}>${t.l}</option>`).join('')}
            </select>
          </div>
        </div>
        <div style="margin-bottom:14px;">
          ${lbl('Descripcion / Objetivo')}
          <textarea id="rbe-desc" class="form-control" rows="2" style="font-size:13px;">${UI.esc(rb.scenario||'')}</textarea>
        </div>
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);letter-spacing:.05em;margin:16px 0 10px;padding-top:12px;border-top:1px solid var(--border);">Campos DRP — ISO 22301 §8.4.3</div>
        <div style="margin-bottom:14px;">
          ${lbl('Condicion de activacion')}
          <textarea id="rbe-actcond" class="form-control" rows="2" style="font-size:13px;">${UI.esc(rb.activation_condition||'')}</textarea>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>${lbl('Responsable titular')}
            <input id="rbe-resp" class="form-control" style="font-size:13px;" value="${UI.esc(rb.responsible_name||'')}" placeholder="Nombre · Cargo">
          </div>
          <div>${lbl('Suplente')}
            <input id="rbe-backup" class="form-control" style="font-size:13px;" value="${UI.esc(rb.backup_responsible_name||'')}" placeholder="Nombre · Cargo">
          </div>
        </div>
        <div style="margin-bottom:14px;">
          ${lbl('Referencia boveda de credenciales')}
          <input id="rbe-vault" class="form-control" style="font-size:13px;" value="${UI.esc(rb.credentials_vault_ref||'')}" placeholder="Ej: Boveda: carpeta AD-Recovery · Acceso: Crisis Lead + Tech Lead">
        </div>
        <div style="margin-bottom:14px;">
          ${lbl('Criterio de exito (verificacion)')}
          <textarea id="rbe-success" class="form-control" rows="2" style="font-size:13px;">${UI.esc(rb.success_criteria||'')}</textarea>
        </div>
      </div>
      <div class="modal-footer-sticky">
        <div style="display:flex;gap:8px;margin-left:auto;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-primary btn-sm" id="rbe-submit"><i class="ti ti-check"></i> Guardar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#rbe-submit').addEventListener('click', async () => {
      const name = modal.querySelector('#rbe-name').value.trim();
      if (!name) { UI.toast('El nombre es obligatorio', 'error'); return; }
      const btn = modal.querySelector('#rbe-submit');
      btn.disabled = true;
      try {
        await Api.patch('/api/bcp/runbooks/' + rid, {
          title: modal.querySelector('#rbe-name').value.trim(),
          plan_id: parseInt(modal.querySelector('#rbe-plan').value) || null,
          test_type: modal.querySelector('#rbe-type').value,
          scenario: modal.querySelector('#rbe-desc').value.trim() || null,
          activation_condition:    modal.querySelector('#rbe-actcond').value.trim() || null,
          credentials_vault_ref:   modal.querySelector('#rbe-vault').value.trim()   || null,
          success_criteria:        modal.querySelector('#rbe-success').value.trim() || null,
          responsible_name:        modal.querySelector('#rbe-resp').value.trim()    || null,
          backup_responsible_name: modal.querySelector('#rbe-backup').value.trim()  || null,
        });
        UI.toast('Runbook actualizado', 'success');
        modal.remove();
        _setSubTab(4, 'runbooks');
      } catch (e) { UI.toast('Error: ' + e.message, 'error'); btn.disabled = false; }
    });
  }

  async function _genAiRunbook(rid) {
    UI.toast('Generando pasos con IA...', 'info');
    try {
      await Api.post('/api/bcp/runbooks/' + rid + '/generate-ai', {});
      UI.toast('Pasos generados por IA', 'success');
      _setSubTab(4, 'runbooks');
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  // ── Alertas enriquecidas (vencimientos + recomendaciones IA) ──────────────────

  async function _richAlertas(body) {
    const [comp, tests, plans, recs] = await Promise.all([
      Api.get('/api/bcp/compliance/iso22301' + _locParam()).catch(() => null),
      Api.get('/api/bcp/tests' + _locParam()).catch(() => []),
      Api.get('/api/bcp/plans' + _locParam()).catch(() => []),
      Api.get('/api/bcp/test-recommendations' + _locParam()).catch(() => []),
    ]);

    const now = new Date();
    const ms30 = 30 * 86400000;
    const ms90 = 90 * 86400000;

    // Calcular alertas
    const alerts = { critical:[], warning:[], info:[] };

    // Tests vencidos
    tests.filter(t => !t.executed_date && t.scheduled_date && new Date(t.scheduled_date) < now)
      .forEach(t => alerts.critical.push({
        icon:'ti-clipboard-x', text:`Test vencido: <strong>${t.name||t.test_type}</strong>`, sub: 'Programado: ' + new Date(t.scheduled_date).toLocaleDateString('es-ES'), action: `ViewBcp._openTestModal(${t.id})`, actionLabel:'Ver test',
      }));

    // Planes sin aprobacion
    plans.filter(p => p.status === 'draft').forEach(p => alerts.critical.push({
      icon:'ti-file-x', text:`Plan sin aprobar: <strong>${p.code} — ${p.name}</strong>`, sub:'Estado: borrador · ISO 22301 cl. 8.4.4 requiere aprobacion formal', action:null,
    }));

    // Procesos sin BIA
    const procs = await Api.get('/api/bcp/processes').catch(() => []);
    procs.filter(p => !p.rto && !p.rpo).forEach(p => alerts.warning.push({
      icon:'ti-sitemap', text:`Proceso sin BIA: <strong>${p.name}</strong>`, sub:'Faltan RTO/RPO · ISO 22301 cl. 8.2', action:`ViewBcp._editProc(${p.id})`, actionLabel:'Editar',
    }));

    // Tests proximos 30 dias
    tests.filter(t => !t.executed_date && t.scheduled_date && new Date(t.scheduled_date) >= now && new Date(t.scheduled_date) <= new Date(now.getTime() + ms30))
      .forEach(t => alerts.info.push({
        icon:'ti-calendar-event', text:`Test próximo: <strong>${t.name||t.test_type}</strong>`, sub: 'En ' + Math.round((new Date(t.scheduled_date) - now)/86400000) + ' días · ' + new Date(t.scheduled_date).toLocaleDateString('es-ES'), action: `ViewBcp._openTestModal(${t.id})`, actionLabel:'Ver',
      }));

    // Planes con revision proxima
    plans.filter(p => p.review_date && new Date(p.review_date) >= now && new Date(p.review_date) <= new Date(now.getTime() + ms90))
      .forEach(p => alerts.info.push({
        icon:'ti-calendar-check', text:`Plan con revision proxima: <strong>${p.name}</strong>`, sub:'Revision: ' + new Date(p.review_date).toLocaleDateString('es-ES'), action:null,
      }));

    const renderAlertList = (list, color, label) => {
      if (!list.length) return '';
      return `<div class="bcm-alert-section">
        <div class="bcm-alert-section-header" style="color:${color}">
          <span style="width:8px;height:8px;border-radius:50%;background:${color};display:inline-block"></span>
          ${label} (${list.length})
        </div>
        ${list.map(a => `
          <div class="bcm-alert-item">
            <i class="ti ${a.icon}" style="color:${color};flex-shrink:0;font-size:15px"></i>
            <div style="flex:1;min-width:0">
              <div style="font-size:12px">${a.text}</div>
              ${a.sub ? `<div style="font-size:11px;color:var(--text-subtle)">${a.sub}</div>` : ''}
            </div>
            ${a.action ? `<button class="btn btn-ghost btn-sm" style="font-size:10px;white-space:nowrap" onclick="${a.action}">${a.actionLabel||'Ver'}</button>` : ''}
          </div>
        `).join('')}
      </div>`;
    };

    const totalAlerts = alerts.critical.length + alerts.warning.length + alerts.info.length;

    body.innerHTML = `
      <div style="display:flex;gap:14px;flex-wrap:wrap">
        <div style="flex:1;min-width:280px">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
            <div style="font-size:14px;font-weight:700">
              ${totalAlerts ? `<span style="color:#DC2626">${totalAlerts} alertas activas</span>` : '<span style="color:#16a34a">Sin alertas criticas</span>'}
            </div>
          </div>
          ${!totalAlerts
            ? '<div class="notice notice-success"><i class="ti ti-shield-check"></i> Todo en orden. No hay alertas de vencimiento ni gaps criticos identificados.</div>'
            : renderAlertList(alerts.critical,'#DC2626','CRITICO') +
              renderAlertList(alerts.warning,'#D97706','ATENCION') +
              renderAlertList(alerts.info,'#2563EB','INFORMACION')
          }
        </div>
        <div style="flex:1;min-width:280px">
          <div style="font-size:14px;font-weight:700;margin-bottom:12px">
            Recomendaciones IA (${recs.length})
          </div>
          ${!recs.length
            ? `<div class="notice notice-info">
                Sin recomendaciones pendientes.
                <button class="btn btn-sm btn-secondary" style="margin-left:8px" onclick="ViewBcp._genRecs()">
                  <i class="ti ti-sparkles"></i> Generar con IA
                </button>
              </div>`
            : recs.slice(0,10).map(r => {
                const col = r.priority === 'critical'?'#DC2626':r.priority==='high'?'#D97706':r.priority==='medium'?'#2563EB':'#16a34a';
                return `<div class="bcm-alert-item" style="margin-bottom:6px">
                  <div style="width:6px;height:6px;border-radius:50%;background:${col};flex-shrink:0;margin-top:5px"></div>
                  <div style="flex:1;min-width:0">
                    <div style="font-size:12px;font-weight:600">${UI.esc(r.title||r.recommendation_text||'')}</div>
                    ${r.description ? `<div style="font-size:11px;color:var(--text-subtle)">${UI.esc(r.description)}</div>` : ''}
                    <div style="font-size:10px;color:var(--text-subtle);margin-top:2px">${UI.esc(r.iso_clause||'')} · ${r.priority||''}</div>
                  </div>
                  <button class="btn btn-ghost btn-sm" style="font-size:10px" onclick="ViewBcp._acceptRec(${r.id})">Aceptar</button>
                </div>`;
              }).join('')
          }
          <div style="margin-top:14px">
            <button class="btn btn-ghost btn-sm" onclick="ViewBcp._openAiPanel();ViewBcp._sendAiMsg('Analiza el estado actual del BCP y genera recomendaciones de mejora priorizadas por impacto ISO 22301')">
              <i class="ti ti-brain"></i> Pedir analisis al agente IA
            </button>
          </div>
        </div>
      </div>
    `;
  }

  async function _genRecs() {
    UI.toast('Generando recomendaciones...', 'info');
    try {
      await Api.post('/api/bcp/test-recommendations/generate', {});
      _setTile('alertas');
      UI.toast('Recomendaciones generadas', 'success');
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  async function _acceptRec(rid) {
    try {
      await Api.patch('/api/bcp/test-recommendations/' + rid, { status: 'accepted' });
      _setTile('alertas');
      UI.toast('Recomendacion aceptada', 'success');
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  // ── Plan: menu de acciones contextual ────────────────────────────────────────

  function _injectPlanMenuCss() {
    if (document.getElementById('bcp-plan-menu-style')) return;
    const s = document.createElement('style');
    s.id = 'bcp-plan-menu-style';
    s.textContent = `.plan-menu-item{display:flex;align-items:center;gap:8px;width:100%;padding:8px 14px;font-size:13px;
      background:none;border:none;color:var(--text-primary);cursor:pointer;text-align:left}
      .plan-menu-item:hover{background:var(--bg-2)}
      .plan-menu-item i{font-size:14px;color:var(--text-subtle)}
      .plan-menu-danger{color:#dc2626!important}.plan-menu-danger i{color:#dc2626!important}
      .plan-menu-danger:hover{background:#fee2e2}`;
    document.head.appendChild(s);
  }

  function _togglePlanMenu(e, pid) {
    e.stopPropagation();
    _injectPlanMenuCss();
    const all = document.querySelectorAll('[id^="plan-menu-"]');
    const menu = document.getElementById(`plan-menu-${pid}`);
    all.forEach(m => { if (m !== menu) m.style.display = 'none'; });
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    if (menu.style.display === 'block') {
      const close = () => { menu.style.display = 'none'; document.removeEventListener('click', close); };
      setTimeout(() => document.addEventListener('click', close), 0);
    }
  }

  function _closePlanMenus() {
    document.querySelectorAll('[id^="plan-menu-"]').forEach(m => { m.style.display = 'none'; });
  }

  async function _activatePlanDirect(pid) {
    const plan = _plans.find(p => p.id === pid) || await Api.get(`/api/bcp/plans/${pid}`).catch(() => null);
    if (!plan) return;
    if (plan.status !== 'approved') {
      UI.toast('Solo se pueden activar planes aprobados', 'error'); return;
    }
    _setTile('alertas');
    setTimeout(() => ViewBcp._modalActivacion(pid), 300);
  }

  async function _sendPlanMessage(pid) {
    const plan = _plans.find(p => p.id === pid) || await Api.get(`/api/bcp/plans/${pid}`).catch(() => null);
    if (!plan) return;
    const contacts = [
      ...(plan.contact_list || []),
      ...(plan.authorized_activators || []),
    ];
    const cr = plan.crisis_comms || {};
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:560px;">
      <div class="modal-header">
        <h2><i class="ti ti-send"></i> Mensaje a stakeholders — ${UI.esc(plan.name)}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:20px 24px;">
        <div style="font-size:12px;color:var(--text-subtle);margin-bottom:12px">
          Canal principal: <strong>${UI.esc(cr.primary_channel||'No configurado')}</strong>
          ${cr.secondary_channel ? ` · Secundario: <strong>${UI.esc(cr.secondary_channel)}</strong>` : ''}
        </div>
        <div style="margin-bottom:12px">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Destinatarios</label>
          ${!contacts.length
            ? '<div class="notice notice-warning" style="font-size:12px">No hay contactos definidos en este plan. Edita el plan para añadir la lista de contactos.</div>'
            : `<div style="display:flex;flex-wrap:wrap;gap:6px">
                ${contacts.map(c => `<span class="badge badge-secondary" style="font-size:11px">${UI.esc(c.name||'')} <span style="opacity:.6">${UI.esc(c.role||c.team||'')}</span></span>`).join('')}
              </div>`}
        </div>
        <div style="margin-bottom:12px">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Tipo de comunicado</label>
          <select id="msg-type" class="form-control" style="font-size:13px" onchange="
            const v=this.value;const ta=document.getElementById('msg-body');
            if(v==='internal')ta.value=${JSON.stringify(cr.template_internal||'')};
            if(v==='external')ta.value=${JSON.stringify(cr.template_external||'')};
          ">
            <option value="custom">Mensaje personalizado</option>
            <option value="internal">Plantilla interna</option>
            <option value="external">Plantilla externa</option>
          </select>
        </div>
        <div style="margin-bottom:4px">
          <label style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);display:block;margin-bottom:4px">Mensaje</label>
          <textarea id="msg-body" class="form-control" rows="6" style="font-size:13px" placeholder="Escribe el comunicado...">${UI.esc(cr.template_internal||'')}</textarea>
        </div>
      </div>
      <div class="modal-footer-sticky">
        <div style="font-size:11px;color:var(--text-subtle)">Requiere validacion manual antes de enviar</div>
        <div style="display:flex;gap:8px;margin-left:auto;">
          <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          <button class="btn btn-primary btn-sm" onclick="
            const msg=document.getElementById('msg-body').value.trim();
            if(!msg){UI.toast('El mensaje no puede estar vacio','error');return;}
            UI.toast('Comunicado preparado — envia manualmente por el canal configurado','info');
            this.closest('.modal-bg').remove();
          "><i class="ti ti-check"></i> Confirmar y cerrar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _scheduleTestForPlan(pid) {
    _setSubTab(5, 'tests');
    setTimeout(() => _openTestModal(null, { plan_id: pid }), 400);
  }

  async function _viewPlanContext(pid) {
    const ctx = await Api.get(`/api/bcp/plans/${pid}/context`).catch(() => null);
    if (!ctx) { UI.toast('Error cargando contexto', 'error'); return; }
    const plan = ctx.plan;
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    const procRows = (ctx.processes || []).map(proc => {
      const supBadges = (proc.suppliers || []).map(s => `<span class="badge badge-secondary" style="font-size:10px">${UI.esc(s.supplier_name||'')}</span>`).join(' ');
      const depList = (proc.dependencies || []).filter(d => d.is_critical).map(d => `<span style="color:#dc2626;font-size:10px">⚠ ${UI.esc(d.name)}</span>`).join(' ');
      return `<tr>
        <td><strong>${UI.esc(proc.name)}</strong></td>
        <td style="font-size:11px">${proc.rto_hours != null ? proc.rto_hours+'h' : '—'}</td>
        <td style="font-size:11px">${proc.rpo_hours != null ? proc.rpo_hours+'h' : '—'}</td>
        <td style="font-size:11px">${proc.mtpd_hours != null ? proc.mtpd_hours+'h' : '—'}</td>
        <td style="font-size:11px">${supBadges||'—'}</td>
        <td style="font-size:11px">${depList||'—'}</td>
      </tr>`;
    }).join('');

    modal.innerHTML = `
    <div class="modal" style="max-width:780px;max-height:90vh;display:flex;flex-direction:column">
      <div class="modal-header">
        <h2><i class="ti ti-layout-grid"></i> Contexto completo — ${UI.esc(plan.name)}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:20px 24px;overflow-y:auto;flex:1">
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:16px">
          <div class="card" style="padding:10px;text-align:center">
            <div style="font-size:22px;font-weight:800;color:var(--primary)">${(ctx.processes||[]).length}</div>
            <div style="font-size:11px;color:var(--text-subtle)">Procesos cubiertos</div>
          </div>
          <div class="card" style="padding:10px;text-align:center">
            <div style="font-size:22px;font-weight:800;color:#D65200">${(ctx.runbooks||[]).length}</div>
            <div style="font-size:11px;color:var(--text-subtle)">Runbooks de recuperacion</div>
          </div>
          <div class="card" style="padding:10px;text-align:center">
            <div style="font-size:22px;font-weight:800;color:#059669">${(ctx.processes||[]).reduce((a,p)=>(p.suppliers||[]).length+a,0)}</div>
            <div style="font-size:11px;color:var(--text-subtle)">Proveedores criticos</div>
          </div>
        </div>
        ${procRows ? `
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px">Procesos y metricas BIA</div>
        <div class="table-container" style="margin-bottom:16px">
          <table class="data-table" style="font-size:12px">
            <thead><tr><th>Proceso</th><th>RTO</th><th>RPO</th><th>MTPD</th><th>Proveedores</th><th>Deps criticas</th></tr></thead>
            <tbody>${procRows}</tbody>
          </table>
        </div>` : '<div class="notice notice-info">Sin procesos asociados a este plan.</div>'}
        ${ctx.runbooks?.length ? `
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px">Runbooks de recuperacion</div>
        <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:16px">
          ${ctx.runbooks.map(rb => `<div style="padding:8px 12px;background:var(--bg-2);border-radius:6px;border-left:3px solid var(--primary);font-size:12px">
            <strong>${UI.esc(rb.title)}</strong>
            ${rb.responsible_name ? ` · <span style="color:var(--text-subtle)"><i class="ti ti-user-check"></i> ${UI.esc(rb.responsible_name)}</span>` : ''}
            ${rb.activation_condition ? `<div style="font-size:11px;color:var(--text-subtle);margin-top:3px">${UI.esc(rb.activation_condition.slice(0,100))}${rb.activation_condition.length>100?'...':''}</div>` : ''}
          </div>`).join('')}
        </div>` : ''}
        ${ctx.location ? `
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px">Sede de recuperacion (DR Site)</div>
        <div class="card" style="padding:10px;font-size:12px;margin-bottom:16px">
          <strong>${UI.esc(ctx.location.name)}</strong>
          ${ctx.location.address ? ` · ${UI.esc(ctx.location.address)}` : ''}
          ${ctx.location.recovery_site_type ? ` · Tipo: <strong>${UI.esc(ctx.location.recovery_site_type)}</strong>` : ''}
        </div>` : ''}
      </div>
      <div class="modal-footer-sticky">
        <button class="btn btn-primary btn-sm" onclick="ViewBcp._activatePlanDirect(${pid});this.closest('.modal-bg').remove()">
          <i class="ti ti-alert-triangle"></i> Activar plan
        </button>
        <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Cerrar</button>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _viewPlanActivations(pid) {
    const allActs = await Api.get('/api/bcp/activations').catch(() => []);
    const planActs = allActs.filter(a => (a.activated_plan_ids || []).includes(pid));
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:680px;max-height:90vh;display:flex;flex-direction:column">
      <div class="modal-header">
        <h2><i class="ti ti-history"></i> Historial de activaciones del plan</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:20px 24px;overflow-y:auto;flex:1">
        ${!planActs.length
          ? '<div class="notice notice-info">Este plan no tiene activaciones registradas.</div>'
          : `<div class="table-container">
              <table class="data-table" style="font-size:12px">
                <thead><tr><th>Codigo</th><th>Titulo</th><th>Activado</th><th>Cerrado</th><th>RTO real</th><th>Estado</th><th></th></tr></thead>
                <tbody>
                  ${planActs.map(a => {
                    const dur = a.closed_at && a.activated_at
                      ? Math.round((new Date(a.closed_at) - new Date(a.activated_at)) / 3600000 * 10) / 10 + 'h'
                      : '—';
                    return `<tr>
                      <td>${UI.codePill(a.code||'—')}</td>
                      <td><strong>${UI.esc(a.title||'—')}</strong></td>
                      <td>${a.activated_at ? new Date(a.activated_at).toLocaleString('es-ES',{dateStyle:'short',timeStyle:'short'}) : '—'}</td>
                      <td>${a.closed_at   ? new Date(a.closed_at  ).toLocaleString('es-ES',{dateStyle:'short',timeStyle:'short'}) : '—'}</td>
                      <td>${dur}</td>
                      <td><span class="badge badge-${a.closed_at?'secondary':'danger'}">${a.closed_at?'Cerrada':'Activa'}</span></td>
                      <td><button class="btn btn-ghost btn-sm" onclick="ViewBcp._viewActivationDetail(${a.id});this.closest('.modal-bg').remove()"><i class="ti ti-eye"></i></button></td>
                    </tr>`;
                  }).join('')}
                </tbody>
              </table>
            </div>`}
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _viewActivationDetail(aid) {
    const allActs = await Api.get('/api/bcp/activations').catch(() => []);
    const a = allActs.find(x => x.id === aid);
    if (!a) return;
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    const logEntries = (a.situation_log || []);
    const checklist  = (a.checklist_items || []);
    modal.innerHTML = `
    <div class="modal" style="max-width:640px;max-height:90vh;display:flex;flex-direction:column">
      <div class="modal-header">
        <h2><i class="ti ti-clipboard-check"></i> Activacion ${UI.esc(a.code||'—')} — ${UI.esc(a.title||'')}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="display:block;padding:20px 24px;overflow-y:auto;flex:1">
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:16px">
          <div class="card" style="padding:10px;text-align:center">
            <div style="font-size:11px;color:var(--text-subtle)">Activado</div>
            <div style="font-size:13px;font-weight:700">${a.activated_at ? new Date(a.activated_at).toLocaleString('es-ES',{dateStyle:'short',timeStyle:'short'}) : '—'}</div>
          </div>
          <div class="card" style="padding:10px;text-align:center">
            <div style="font-size:11px;color:var(--text-subtle)">Cerrado</div>
            <div style="font-size:13px;font-weight:700">${a.closed_at ? new Date(a.closed_at).toLocaleString('es-ES',{dateStyle:'short',timeStyle:'short'}) : '<span style="color:#dc2626">Activo</span>'}</div>
          </div>
          <div class="card" style="padding:10px;text-align:center">
            <div style="font-size:11px;color:var(--text-subtle)">RTO real</div>
            <div style="font-size:13px;font-weight:700">${a.rto_actual_hours != null ? a.rto_actual_hours + 'h' : '—'}</div>
          </div>
        </div>
        ${a.lessons_learned ? `
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:6px">Lecciones aprendidas</div>
          <div class="card" style="padding:10px;font-size:13px;margin-bottom:16px">${UI.esc(a.lessons_learned)}</div>
        ` : ''}
        ${checklist.length ? `
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px">Checklist de activacion</div>
          <div style="display:flex;flex-direction:column;gap:4px;margin-bottom:16px">
            ${checklist.map(item => `
              <div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--bg-2);border-radius:4px;font-size:12px">
                <span style="width:18px;height:18px;border-radius:50%;background:${item.status==='done'?'#16a34a':'var(--border)'};color:${item.status==='done'?'#fff':'var(--text-subtle)'};display:flex;align-items:center;justify-content:center;font-size:10px;flex-shrink:0">${item.status==='done'?'✓':item.order}</span>
                <span style="${item.status==='done'?'text-decoration:line-through;color:var(--text-subtle)':''}">${UI.esc(item.title||'')}</span>
                ${item.status==='done'&&item.executed_at?`<span style="margin-left:auto;font-size:10px;color:var(--text-subtle)">${new Date(item.executed_at).toLocaleTimeString('es-ES',{hour:'2-digit',minute:'2-digit'})}</span>`:''}
              </div>`).join('')}
          </div>
        ` : ''}
        ${logEntries.length ? `
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-subtle);margin-bottom:8px">Timeline de eventos (${logEntries.length})</div>
          <div style="display:flex;flex-direction:column;gap:2px">
            ${logEntries.map(e => `
              <div style="display:flex;gap:8px;font-size:12px;padding:4px 0;border-bottom:1px solid var(--border)">
                <span style="color:var(--text-subtle);flex-shrink:0;white-space:nowrap;font-size:11px">${new Date(e.timestamp).toLocaleString('es-ES',{dateStyle:'short',timeStyle:'short'})}</span>
                <span>${UI.esc(e.text||e.message||'')}</span>
              </div>`).join('')}
          </div>
        ` : ''}
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  // ── Activacion: historial consultable completo ───────────────────────────────

  function _calcBiaImpact() {
    const cph  = parseFloat(document.getElementById('pm-cph')?.value)  || 0;
    const rto  = parseFloat(document.getElementById('pm-rto')?.value)  || 0;
    const mtpd = parseFloat(document.getElementById('pm-mtpd')?.value) || 0;
    const resultEl = document.getElementById('pm-calc-result');
    const warnEl   = document.getElementById('pm-rto-warn');
    if (!resultEl) return;
    if (cph > 0 && rto > 0) {
      const impact = cph * rto;
      resultEl.textContent = `Impacto estimado: ${impact.toLocaleString('es-ES', {style:'currency', currency:'EUR', maximumFractionDigits:0})}`;
    } else {
      resultEl.textContent = 'Introduce €/h y RTO para calcular el impacto.';
    }
    if (warnEl) {
      warnEl.style.display = (mtpd > 0 && rto > 0 && rto >= mtpd) ? '' : 'none';
    }
  }

  return {
    render,
    _switchTab, _setMode, _setStep, _setTile, _setSubTab,
    _clearSede, _openAiPanel, _closeAiPanel, _sendAiMsg,
    _saveWizardStep,
    _editProc, _saveProc, _delProc,
    _editDep, _saveDep, _delDep,
    _editStrat, _saveStrat, _delStrat,
    _editPlan, _savePlan, _approvePlan,
    _openPlanDrawer, _closePlanDrawer,
    _onPlanTypeChange,
    _addSysDep, _removeSysDep, _updateSysDep,
    _addRole, _removeRole, _updateRole, _loadDRPRoles,
    _addContact, _removeContact, _updateContact,
    _addKPI, _removeKPI, _updateKPI, _loadStandardKPIs,
    _addBkpItem, _removeBkpItem, _updateBkpItem,
    _saveTest, _openTestResultModal, _saveTestResult, _onResultChange,
    _editSL, _saveSL, _delSL,
    _openEPModal, _saveEP,
    _handleDrop, _handleFileSelect,
    _setImportMode, _onFileSelect, _renderImportPreview, _confirmImport,
    _runBcpAiAnalysis,
    _toggleLocChildren, _setLocFilter, _editLocation, _modalLocation,
    _openTestModal,
    _modalActivacion, _closeActModal, _confirmActivacion, _logActivacion, _closeActivacion,
    _newRunbook, _editRunbook, _genAiRunbook,
    _genRecs, _acceptRec,
    _calcBiaImpact,
    _togglePlanMenu, _closePlanMenus,
    _activatePlanDirect, _sendPlanMessage, _scheduleTestForPlan,
    _viewPlanContext, _viewPlanActivations, _viewActivationDetail,
    _addAuthActivator, _removeAuthActivator, _updateAuthActivator,
    _addDocLink, _removeDocLink, _updateDocLink,
    _addRelDoc, _removeRelDoc, _updateRelDoc,
    _genAiChecklist,
    _editPlan,
    _openApprovedVersioningModal,
    _bumpVersion,
    _openCrisisRoom,
    _quickLogEntry,
    _crAddLog,
    _crUploadAttachment,
    _crDeleteAttachment,
    _crGenerateAISummary,
    _crToggleChecklist,
    _crSavePostMortem,
    _openActivationReport,
    _crSetTab: (aid, tab) => { window._crCurrentTab = tab; if (window._crModal) _renderCrisisRoomContent(aid, window._crModal); },
    _wizardAutofill,
    _wziardToggleOtros,
    _wizardAddOtroScenario,
    _testUploadEvidence,
    _loadTestEvidence,
  };
})();
