/* BCP/BIA — Continuidad de negocio (ISO 22301) */
const ViewBcp = (() => {

  const BCP_TABS = [
    { id: 'overview',     label: 'Resumen',           icon: 'ti-dashboard' },
    { id: 'processes',    label: 'Procesos Criticos',  icon: 'ti-sitemap' },
    { id: 'bia',          label: 'BIA',               icon: 'ti-chart-dots' },
    { id: 'dependencies', label: 'Dependencias',       icon: 'ti-link' },
    { id: 'strategies',   label: 'Estrategias',        icon: 'ti-route' },
    { id: 'plans',        label: 'Planes BCP/DRP',     icon: 'ti-file-text' },
    { id: 'tests',        label: 'Tests & Ejercicios', icon: 'ti-clipboard-check' },
    { id: 'suppliers',    label: 'Proveedores BCM',    icon: 'ti-truck' },
    { id: 'import',       label: 'Importar Excel',     icon: 'ti-table-import' },
  ];
  let _activeTab = 'overview';

  const CRIT_COLORS = { critical:'#DC2626', high:'#D97706', medium:'#2563EB', low:'#16a34a' };
  const IMPL_COLORS = { planned:'#6B7280', in_progress:'#D97706', implemented:'#2563EB', tested:'#16a34a' };
  const STATUS_COLORS = { draft:'#6B7280', under_review:'#D97706', approved:'#16a34a', deprecated:'#DC2626' };

  // Cache de datos
  let _procs = [], _deps = [], _strats = [], _plans = [], _tests = [], _slinks = [], _suppliers = [];
  let _container = null;

  // ── Entry point ──────────────────────────────────────────────────────────────

  async function render(container) {
    _container = container;
    container.innerHTML = UI.sectionHeader(
      'Continuidad de Negocio (BCP/BIA)',
      'NIS2 Art. 21.2(b) + ISO 27001 A.5.29 + ISO 22301 — Procesos criticos, RTO/RPO, planes y tests'
    );

    // Tab bar
    const tabBar = document.createElement('div');
    tabBar.className = 'bcp-tab-bar';
    tabBar.innerHTML = BCP_TABS.map(t =>
      `<button class="bcp-tab${t.id === _activeTab ? ' active' : ''}" data-tab="${t.id}">
        <i class="ti ${t.icon}"></i>${t.label}
      </button>`
    ).join('');
    container.appendChild(tabBar);
    tabBar.querySelectorAll('.bcp-tab').forEach(btn =>
      btn.addEventListener('click', () => _switchTab(btn.dataset.tab))
    );

    const content = document.createElement('div');
    content.id = 'bcp-tab-content';
    content.className = 'bcp-tab-content';
    container.appendChild(content);

    await _renderActiveTab();
  }

  function _switchTab(tab) {
    _activeTab = tab;
    _container.querySelectorAll('.bcp-tab').forEach(b =>
      b.classList.toggle('active', b.dataset.tab === tab)
    );
    _renderActiveTab();
  }

  async function _renderActiveTab() {
    const content = document.getElementById('bcp-tab-content');
    if (!content) return;
    content.innerHTML = '<div style="padding:20px;color:var(--text-muted);">Cargando...</div>';
    try {
      switch (_activeTab) {
        case 'overview':     await _tabOverview(content); break;
        case 'processes':    await _tabProcesses(content); break;
        case 'bia':          await _tabBIA(content); break;
        case 'dependencies': await _tabDependencies(content); break;
        case 'strategies':   await _tabStrategies(content); break;
        case 'plans':        await _tabPlans(content); break;
        case 'tests':        await _tabTests(content); break;
        case 'suppliers':    await _tabSuppliers(content); break;
        case 'import':       _tabImport(content); break;
        default: content.innerHTML = '';
      }
    } catch (e) {
      console.error('[BCP] Error en tab', _activeTab, e);
      content.innerHTML = UI.notice('Error al cargar tab "' + _activeTab + '": ' + e.message + ' (ver consola para detalles)');
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
    _procs = await Api.get('/api/bcp/processes').catch(() => []);

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
            <th>Proceso</th><th>Criticidad</th><th>RTO</th><th>RPO</th><th>MTPD</th>
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
          <button class="btn btn-primary btn-lg" id="btn-bia-new2">+ Crear primer proceso BIA</button>
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
      <button class="btn btn-primary" id="btn-bia-new">+ Nuevo proceso BIA</button>
    </div>
    ${bodyHtml}`;

    // listeners siempre DESPUES de asignar innerHTML
    document.getElementById('btn-bia-new')?.addEventListener('click', () => _openProcModal(null, true));
    document.getElementById('btn-bia-new2')?.addEventListener('click', () => _openProcModal(null, true));
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
      <td><strong style="font-size:13px;">${UI.esc(d.name)}</strong>${d.description ? `<div style="font-size:11px;color:var(--text-subtle)">${UI.esc(d.description.substring(0,50))}</div>` : ''}</td>
      <td style="text-align:center;">${d.qty_normal ?? '—'} / ${d.qty_recovery ?? '—'}</td>
      <td style="text-align:center;">${d.rto_hours != null ? d.rto_hours + 'h' : '—'}</td>
      <td style="text-align:center;">${d.is_critical ? '<span class="badge badge-danger" style="font-size:10px;">Si</span>' : '<span style="font-size:11px;color:var(--text-subtle)">No</span>'}</td>
      <td style="font-size:11px;max-width:120px;overflow:hidden;text-overflow:ellipsis;">${UI.esc((d.alternative || '—').substring(0,50))}</td>
      <td style="text-align:center;">${d.recovery_sequence != null ? `<span class="badge">${d.recovery_sequence}</span>` : '—'}</td>
      <td><button class="btn btn-sm btn-secondary" onclick="ViewBcp._editDep(${d.id})">Editar</button></td>
    </tr>`).join('');

    const html = `
    <div style="display:flex;justify-content:flex-end;margin-bottom:16px;gap:8px;">
      <button class="btn btn-primary" id="btn-new-dep"><i class="ti ti-plus"></i> Nueva dependencia de recurso</button>
      <button class="btn btn-secondary" id="btn-new-proc-dep"><i class="ti ti-sitemap"></i> Nueva dep. proceso-proceso</button>
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
  }

  // ── Tab Estrategias ──────────────────────────────────────────────────────────

  async function _tabStrategies(el) {
    [_procs, _strats] = await Promise.all([
      _procs.length ? Promise.resolve(_procs) : Api.get('/api/bcp/processes').catch(() => []),
      Api.get('/api/bcp/strategies').catch(() => []),
    ]);
    el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h3 style="margin:0;">Estrategias de Recuperacion (${_strats.length})</h3>
      <button class="btn btn-primary" id="btn-new-strat">+ Nueva estrategia</button>
    </div>`;
    if (!_strats.length) {
      el.innerHTML += UI.emptyState('No hay estrategias de recuperacion. ISO 22301 cl. 8.3 requiere definir al menos una estrategia por proceso critico.');
    } else {
      const procName = id => id ? ((_procs.find(p => p.id == id)||{}).name || '#'+id) : 'Global';
      el.innerHTML += `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;">
      ${_strats.map(s => `
      <div class="card" style="cursor:pointer;" onclick="ViewBcp._editStrat(${s.id})">
        <div class="card-body">
          <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
            <span class="badge" style="background:#59008D22;color:#59008D;">${s.strategy_type}</span>
            <span style="font-size:12px;color:${IMPL_COLORS[s.implementation_status]||'#666'};">
              ${s.implementation_status}
            </span>
          </div>
          <strong style="font-size:14px;">${UI.esc(s.name)}</strong>
          <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">${UI.esc(procName(s.process_id))}</div>
          ${s.estimated_cost != null ? `<div style="font-size:12px;margin-top:6px;">Coste est.: <strong>${s.estimated_cost.toLocaleString('es-ES')} €</strong></div>` : ''}
        </div>
      </div>`).join('')}
      </div>`;
    }
    document.getElementById('btn-new-strat')?.addEventListener('click', () => _openStratModal());
  }

  // ── Tab Planes ───────────────────────────────────────────────────────────────

  const PLAN_BADGE_CLASS = {
    bcp: 'plan-badge-bcp', drp: 'plan-badge-drp', crp: 'plan-badge-crp',
    cyber_response: 'plan-badge-cyber', pandemic: 'plan-badge-pandemic',
    ems: 'plan-badge-ems', supply_chain: 'plan-badge-supply',
  };
  const PLAN_TYPE_LABELS = {
    bcp: 'BCP', drp: 'DRP', crp: 'CRP',
    cyber_response: 'Cyber', pandemic: 'Pandemia', ems: 'EMS', supply_chain: 'Cadena sum.',
  };
  const CLASSIFICATION_LABELS = { confidential: 'Confidencial', internal: 'Uso interno', restricted: 'Restringido' };

  async function _tabPlans(el) {
    [_procs, _plans] = await Promise.all([
      _procs.length ? Promise.resolve(_procs) : Api.get('/api/bcp/processes').catch(() => []),
      Api.get('/api/bcp/plans').catch(() => []),
    ]);

    const tableHtml = !_plans.length
      ? UI.emptyState('No hay planes BCP/DRP. ISO 22301 cl. 8.4 requiere planes documentados de continuidad.')
      : `<div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>Codigo</th><th>Tipo</th><th>Clasificacion</th><th>Nombre</th><th>Version</th>
            <th>Estado</th><th>Procesos</th><th>Propietario</th><th>Revision</th><th></th>
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
            <td style="font-size:12px;">${(p.process_ids||[]).length}</td>
            <td style="font-size:12px;color:var(--text-subtle);">${UI.esc(p.plan_owner_name||'—')}</td>
            <td style="font-size:12px;">${p.review_date ? new Date(p.review_date).toLocaleDateString('es-ES') : '—'}</td>
            <td style="display:flex;gap:4px;flex-wrap:nowrap;">
              <button class="btn btn-sm btn-secondary" onclick="ViewBcp._editPlan(${p.id})">Editar</button>
              ${['draft','under_review'].includes(p.status) ?
                `<button class="btn btn-sm btn-primary" onclick="ViewBcp._approvePlan(${p.id})">Aprobar</button>` : ''}
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
      Api.get('/api/bcp/tests').catch(() => []),
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
            <td>
              <button class="btn btn-sm btn-secondary" onclick="ViewBcp._openTestResultModal(${t.id})">
                ${t.result ? 'Ver / Editar' : 'Registrar resultado'}
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

  async function _tabSuppliers(el) {
    [_procs, _slinks, _suppliers] = await Promise.all([
      _procs.length ? Promise.resolve(_procs) : Api.get('/api/bcp/processes').catch(() => []),
      Api.get('/api/bcp/supplier-links').catch(() => []),
      Api.get('/api/suppliers').catch(() => []),
    ]);
    el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h3 style="margin:0;">Proveedores BCM (${_slinks.length})</h3>
      <button class="btn btn-primary" id="btn-new-sl">+ Vincular proveedor</button>
    </div>`;
    if (!_slinks.length) {
      el.innerHTML += UI.emptyState('No hay proveedores vinculados al BCP. ISO 22301 cl. 8.2 requiere identificar proveedores criticos.');
    } else {
      el.innerHTML += `
      <div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>Proveedor</th><th>Criticidad BCM</th><th>Procesos dep.</th><th>Impacto RTO</th>
            <th>SLA contrato</th><th>Plan contingencia</th><th>Prov. alternativo</th><th>Ultima revision</th><th></th>
          </tr></thead>
          <tbody>
          ${_slinks.map(s => `<tr>
            <td><strong>${UI.esc(s.supplier_name)}</strong></td>
            <td><span style="color:${CRIT_COLORS[s.criticality]};font-weight:700;">${s.criticality}</span></td>
            <td>${(s.process_ids||[]).length}</td>
            <td>${s.rto_impact_hours != null ? s.rto_impact_hours + 'h' : '—'}</td>
            <td>${s.contract_sla_hours != null ? s.contract_sla_hours + 'h' : '—'}</td>
            <td>${s.has_contingency_plan ?
              '<span class="badge badge-success">&#10003; Si</span>' :
              '<span class="badge badge-danger">&#10007; No</span>'}</td>
            <td>${s.alternative_supplier_name || '—'}</td>
            <td>${s.last_review_date ? new Date(s.last_review_date).toLocaleDateString('es-ES') : '—'}</td>
            <td><button class="btn btn-sm btn-secondary" onclick="ViewBcp._editSL(${s.id})">Editar</button></td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    }
    document.getElementById('btn-new-sl')?.addEventListener('click', () => _openSLModal());
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
    // Cargar usuarios para los selects de responsable
    let users = [];
    try { users = await Api.get('/api/users/'); } catch (_) { }
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
    <div class="modal" style="max-width:680px;max-height:90vh;display:flex;flex-direction:column;">
      <div class="modal-header" style="flex-shrink:0;">
        <h2>${proc ? 'Editar proceso' : (isBia ? 'Nuevo proceso BIA' : 'Nuevo proceso critico')}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="overflow-y:auto;flex:1;padding:20px;display:block;">

        <div class="form-section-divider"><span>INFORMACION BASICA</span></div>
        <div style="margin-bottom:14px;">
          <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">Nombre <span style="color:var(--danger)">*</span></label>
          <input id="pm-name" class="form-control" value="${UI.esc(proc?.name||'')}" style="font-size:13px;">
        </div>
        <div style="margin-bottom:14px;">
          <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">Descripcion</label>
          <textarea id="pm-desc" class="form-control" rows="2" style="font-size:13px;">${UI.esc(proc?.description||'')}</textarea>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">Criticidad <span style="color:var(--danger)">*</span></label>
            <select id="pm-crit" class="form-control" style="font-size:13px;">
              ${['critical','high','medium','low'].map(c=>`<option value="${c}"${proc?.criticality===c?' selected':''}>${{critical:'Critica',high:'Alta',medium:'Media',low:'Baja'}[c]}</option>`).join('')}
            </select>
          </div>
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">Prioridad de recuperacion</label>
            <input id="pm-prio" class="form-control" type="number" min="1" style="font-size:13px;" value="${proc?.priority||''}" placeholder="1 = mas urgente">
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">Responsable</label>
            <select id="pm-owner" class="form-control" style="font-size:13px;">
              <option value="">— Sin asignar —</option>${userOpts}
            </select>
          </div>
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">Responsable de recuperacion</label>
            <select id="pm-rowner" class="form-control" style="font-size:13px;">
              <option value="">— Sin asignar —</option>${rUserOpts}
            </select>
          </div>
        </div>

        <div class="form-section-divider"><span>OBJETIVOS DE RECUPERACION (BIA)</span></div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px;">
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">RTO (horas)</label>
            <div style="font-size:10px;color:var(--text-subtle);margin:2px 0 4px;">Recovery Time Objective</div>
            <input id="pm-rto" class="form-control" type="number" min="0" style="font-size:13px;" value="${proc?.rto_hours??''}">
          </div>
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">RPO (horas)</label>
            <div style="font-size:10px;color:var(--text-subtle);margin:2px 0 4px;">Recovery Point Objective</div>
            <input id="pm-rpo" class="form-control" type="number" min="0" style="font-size:13px;" value="${proc?.rpo_hours??''}">
          </div>
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">MTPD (horas)</label>
            <div style="font-size:10px;color:var(--text-subtle);margin:2px 0 4px;">Max. Tolerable Period of Disruption</div>
            <input id="pm-mtpd" class="form-control" type="number" min="0" style="font-size:13px;" value="${proc?.mtpd_hours??''}">
          </div>
        </div>
        <div style="display:grid;grid-template-columns:160px 1fr;gap:12px;margin-bottom:14px;">
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">Staff minimo</label>
            <div style="font-size:10px;color:var(--text-subtle);margin:2px 0 4px;">Personas para recuperar</div>
            <input id="pm-staff" class="form-control" type="number" min="0" style="font-size:13px;" value="${proc?.min_recovery_staff??''}">
          </div>
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">MBCO — Objetivo Minimo de Continuidad</label>
            <div style="font-size:10px;color:var(--text-subtle);margin:2px 0 4px;">Nivel minimo de servicio aceptable</div>
            <textarea id="pm-mbco" class="form-control" rows="2" style="font-size:13px;" placeholder="Ej: 50% de pedidos procesados, acceso de lectura a datos criticos...">${UI.esc(proc?.mbco||'')}</textarea>
          </div>
        </div>

        <div class="form-section-divider"><span>EVALUACION DE IMPACTO BIA</span></div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;">
          ${[['pm-fi','Financiero','financial_impact'],['pm-ri','Reputacional','reputational_impact'],
             ['pm-li','Legal/Reg.','legal_impact'],['pm-oi','Operacional','operational_impact']].map(([id,lbl,fld])=>`
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">${lbl}</label>
            <select id="${id}" class="form-control" style="font-size:12px;">
              ${IMPACTS.map((imp,i)=>`<option value="${i}"${proc?.[fld]===i?' selected':''}>${imp}</option>`).join('')}
            </select>
          </div>`).join('')}
        </div>

        <div class="form-section-divider"><span>ACTIVACION Y PROCEDIMIENTOS</span></div>
        <div style="margin-bottom:14px;">
          <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">Criterios de activacion <span style="color:var(--danger)">*</span></label>
          <div style="font-size:11px;color:var(--text-subtle);margin:2px 0 4px;">¿Que condiciones deben darse para activar el plan de este proceso?</div>
          <textarea id="pm-activ" class="form-control" rows="2" style="font-size:13px;">${UI.esc(proc?.activation_criteria||'')}</textarea>
        </div>
        <div style="margin-bottom:14px;">
          <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">Procedimiento alternativo <span style="color:var(--danger)">*</span></label>
          <div style="font-size:11px;color:var(--text-subtle);margin:2px 0 4px;">¿Como puede este proceso funcionar manualmente o de forma degradada?</div>
          <textarea id="pm-altproc" class="form-control" rows="2" style="font-size:13px;">${UI.esc(proc?.alternative_procedure||'')}</textarea>
        </div>

        <div class="form-section-divider"><span>RECURSOS Y DOCUMENTACION</span></div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:14px;">
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">Registros vitales</label>
            <div style="font-size:11px;color:var(--text-subtle);margin:2px 0 4px;">Un registro por linea</div>
            <textarea id="pm-vr" class="form-control" rows="3" style="font-size:12px;" placeholder="ERP datos ventas&#10;Contratos con clientes&#10;Certificados SSL">${UI.esc(arrToLines(proc?.vital_records))}</textarea>
          </div>
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">Sistemas IT</label>
            <div style="font-size:11px;color:var(--text-subtle);margin:2px 0 4px;">Un sistema por linea</div>
            <textarea id="pm-it" class="form-control" rows="3" style="font-size:12px;" placeholder="ERP SAP&#10;CRM Salesforce&#10;VPN Cisco">${UI.esc(arrToLines(proc?.it_systems))}</textarea>
          </div>
          <div>
            <label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);">Instalaciones</label>
            <div style="font-size:11px;color:var(--text-subtle);margin:2px 0 4px;">Una instalacion por linea</div>
            <textarea id="pm-fac" class="form-control" rows="3" style="font-size:12px;" placeholder="Sede Madrid&#10;CPD principal&#10;Almacen logistico">${UI.esc(arrToLines(proc?.facilities))}</textarea>
          </div>
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
    await Api.del(`/api/bcp/processes/${id}`);
    UI.toast('Proceso eliminado', 'success');
    document.querySelector('.modal-bg')?.remove();
    _procs = [];
    _switchTab('processes');
  }

  // ── Modales — Dependencia ────────────────────────────────────────────────────

  function _openDepModal(dep, isProcDep) {
    const isProc = isProcDep || dep?.dependency_type === 'process' || !!dep?.depends_on_process_id;
    const DEP_TYPES = ['IT_system','personnel','facility','supplier','utility','communication','transport','external_service'];
    const lbl = (text, req) => `<label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);display:block;margin-bottom:4px;">${text}${req ? ' <span style="color:var(--danger)">*</span>' : ''}</label>`;

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
        <div class="modal-body" style="display:block;padding:20px;">
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
        <div class="modal-body" style="overflow-y:auto;flex:1;padding:20px;">
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
    await Api.del(`/api/bcp/dependencies/${id}`);
    UI.toast('Dependencia eliminada', 'success');
    document.querySelector('.modal-bg')?.remove();
    _switchTab('dependencies');
  }

  // ── Modales — Estrategia ─────────────────────────────────────────────────────

  function _openStratModal(strat) {
    const TYPES = ['hot_site','cold_site','warm_site','work_from_home','outsourcing','manual_workaround','dual_site','cloud_failover'];
    const TYPE_LABELS = {hot_site:'Hot site',cold_site:'Cold site',warm_site:'Warm site',
      work_from_home:'Trabajo remoto',outsourcing:'Outsourcing',manual_workaround:'Procedimiento manual',
      dual_site:'Dual site',cloud_failover:'Cloud failover'};
    const STATUS_OPTS = [{v:'planned',l:'Planificado'},{v:'in_progress',l:'En progreso'},
      {v:'implemented',l:'Implementado'},{v:'tested',l:'Probado'}];
    const lbl = t => `<label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);display:block;margin-bottom:4px;">${t}</label>`;
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:520px;max-height:90vh;display:flex;flex-direction:column;">
      <div class="modal-header" style="flex-shrink:0;">
        <h2>${strat ? 'Editar estrategia' : 'Nueva estrategia de recuperacion'}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="overflow-y:auto;flex:1;padding:20px;display:block;">
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
    const body = {
      strategy_type: document.getElementById('sm-type').value,
      name: document.getElementById('sm-name').value.trim(),
      process_id: parseInt(document.getElementById('sm-proc').value)||null,
      implementation_status: document.getElementById('sm-status').value,
      estimated_cost: parseFloat(document.getElementById('sm-cost').value)||null,
      responsible_id: parseInt(document.getElementById('sm-resp').value)||null,
      target_date: document.getElementById('sm-date').value||null,
      description: document.getElementById('sm-desc').value||null,
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
    await Api.del(`/api/bcp/strategies/${id}`);
    UI.toast('Estrategia eliminada', 'success');
    document.querySelector('.modal-bg')?.remove();
    _switchTab('strategies');
  }

  // ── Drawer — Plan ────────────────────────────────────────────────────────────

  let _currentPlanId = null;

  function _openPlanDrawer(plan) {
    _currentPlanId = plan?.id || null;
    const TYPES = ['bcp','drp','crp','ems','pandemic','cyber_response','supply_chain'];
    const CLASSIFS = [['confidential','Confidencial'],['internal','Uso interno'],['restricted','Restringido']];
    const lbl = (text, req, sub) =>
      `<label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);display:block;margin-bottom:4px;">${text}${req?' <span style="color:var(--danger)">*</span>':''}
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
        <input id="pl-rev" class="form-control" type="date" style="font-size:13px;" value="${plan?.review_date?plan.review_date.substring(0,10):''}">
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

    <!-- SECCION 9: Historial -->
    ${plan ? `<div class="form-section-divider"><span>HISTORIAL Y MANTENIMIENTO</span></div>
    <div style="font-size:12px;color:var(--text-subtle);display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px;">
      <div>Estado: <strong>${UI.esc(plan.status)}</strong></div>
      <div>Ultima prueba: <strong>${plan.last_exercised_at ? new Date(plan.last_exercised_at).toLocaleDateString('es-ES') : '—'}</strong></div>
      ${plan.approved_by_id ? `<div>Aprobado por: <strong>#${plan.approved_by_id}</strong></div>` : ''}
      ${plan.approved_at ? `<div>Aprobado: <strong>${new Date(plan.approved_at).toLocaleDateString('es-ES')}</strong></div>` : ''}
    </div>` : ''}`;

    // Datos en memoria para las tablas inline
    window._planSysDeps = [...sysDeps];
    window._planRoles = [...roles];
    window._planContacts = [...contacts];
    window._planKpis = [...kpis];

    // Guardar save handler actualizado con el ID
    document.getElementById('plan-drawer-save').onclick = () => _savePlan(_currentPlanId);

    _openDrawer('plan-drawer');
  }

  function _onPlanTypeChange(type) {
    const sysSec = document.getElementById('pl-sys-section');
    const procSec = document.getElementById('pl-proc-section');
    if (sysSec) sysSec.style.display = ['drp','crp'].includes(type) ? '' : 'none';
    if (procSec) procSec.style.display = ['drp','crp','cyber_response'].includes(type) ? '' : 'none';
  }

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

  function _editPlan(id) {
    const plan = _plans.find(p => p.id === id);
    _openPlanDrawer(plan);
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
    };

    if (!body.name) { UI.toast('El nombre del plan es obligatorio', 'error'); return; }
    try {
      if (id) await Api.patch(`/api/bcp/plans/${id}`, body);
      else await Api.post('/api/bcp/plans', body);
      UI.toast('Plan guardado', 'success');
      _closePlanDrawer();
      _plans = [];
      _switchTab('plans');
    } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
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

  function _openTestModal() {
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:480px;">
      <div class="modal-header">
        <h2>Programar test BCM</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <label>Tipo *</label>
        <select id="tm-type" class="form-control">
          <option value="tabletop">Tabletop exercise</option>
          <option value="simulation">Simulacion</option>
          <option value="full_test">Test completo</option>
        </select>
        <label style="margin-top:10px;">Fecha programada *</label>
        <input id="tm-date" class="form-control" type="datetime-local">
        <label style="margin-top:10px;">Objetivo</label>
        <input id="tm-obj" class="form-control" placeholder="Objetivo del test">
        <label style="margin-top:10px;">Descripcion del alcance</label>
        <textarea id="tm-scope" class="form-control" rows="2"></textarea>
        <label style="margin-top:10px;">Procesos a evaluar</label>
        <div style="max-height:100px;overflow-y:auto;border:1px solid var(--border);border-radius:4px;padding:6px;">
          ${_procs.map(p=>`<label style="display:flex;gap:6px;align-items:center;padding:2px;">
            <input type="checkbox" value="${p.id}" class="tm-pids"> ${UI.esc(p.name)}
          </label>`).join('')}
        </div>
        <label style="margin-top:10px;">Facilitador (ID usuario)</label>
        <input id="tm-fac" class="form-control" type="number">
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewBcp._saveTest()">Guardar</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
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
    };
    if (!body.scheduled_at) { UI.toast('La fecha es obligatoria', 'error'); return; }
    try {
      await Api.post('/api/bcp/tests', body);
      UI.toast('Test programado', 'success');
      document.querySelector('.modal-bg')?.remove();
      _switchTab('tests');
    } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
  }

  function _openTestResultModal(id) {
    const test = _tests.find(t => t.id === id);
    if (!test) return;
    const lbl = (text, req, sub) =>
      `<label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);display:block;margin-bottom:4px;">${text}${req?' <span style="color:var(--danger)">*</span>':''}
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
      <div class="modal-body" style="overflow-y:auto;flex:1;padding:20px;display:block;">
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
        <div style="margin-bottom:14px;">${lbl('IDs de documentos de evidencia','')}
          <input id="rm-evidence" class="form-control" style="font-size:13px;" placeholder="1, 2, 3 (IDs separados por coma)"
            value="${(test.evidence_doc_ids||[]).join(', ')}">
        </div>
      </div>
      <div class="modal-footer-sticky">
        <div style="display:flex;gap:8px;margin-left:auto;">
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
    const evidenceRaw = (document.getElementById('rm-evidence')?.value || '').trim();
    const evidence = evidenceRaw
      ? evidenceRaw.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n))
      : null;
    const body = {
      conducted_at: document.getElementById('rm-date')?.value || null,
      result,
      findings: document.getElementById('rm-findings')?.value || null,
      lessons_learned: document.getElementById('rm-lessons')?.value || null,
      improvement_actions: document.getElementById('rm-actions')?.value || null,
      evidence_doc_ids: evidence,
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

  function _openSLModal(sl) {
    const lbl = (t, req) => `<label style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--text-subtle);display:block;margin-bottom:4px;">${t}${req?' <span style="color:var(--danger)">*</span>':''}</label>`;
    const CRIT_SL = [{v:'critical',l:'Critica'},{v:'high',l:'Alta'},{v:'medium',l:'Media'},{v:'low',l:'Baja'}];
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:540px;max-height:90vh;display:flex;flex-direction:column;">
      <div class="modal-header" style="flex-shrink:0;">
        <h2>${sl ? 'Editar vinculo BCM' : 'Vincular proveedor al BCP'}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="overflow-y:auto;flex:1;padding:20px;display:block;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>${lbl('Proveedor',true)}
            <select id="slm-sup" class="form-control" style="font-size:13px;" ${sl?'disabled':''}>
              <option value="">— Seleccionar proveedor —</option>
              ${_suppliers.map(s=>`<option value="${s.id}"${sl?.supplier_id===s.id?' selected':''}>${UI.esc(s.name)}</option>`).join('')}
            </select>
          </div>
          <div>${lbl('Criticidad BCM')}
            <select id="slm-crit" class="form-control" style="font-size:13px;">
              ${CRIT_SL.map(c=>`<option value="${c.v}"${sl?.criticality===c.v?' selected':''}>${c.l}</option>`).join('')}
            </select>
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
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
          <div>${lbl('Proveedor alternativo')}
            <select id="slm-alt" class="form-control" style="font-size:13px;">
              <option value="">— Ninguno —</option>
              ${_suppliers.filter(s=>s.id!==sl?.supplier_id).map(s=>
                `<option value="${s.id}"${sl?.alternative_supplier_id===s.id?' selected':''}>${UI.esc(s.name)}</option>`).join('')}
            </select>
          </div>
          <div>${lbl('Ultima revision')}
            <input id="slm-rev" class="form-control" type="date" style="font-size:13px;" value="${sl?.last_review_date?sl.last_review_date.substring(0,10):''}">
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;padding:10px;background:var(--bg-2);border-radius:var(--radius);">
          <input id="slm-hasplan" type="checkbox" style="width:16px;height:16px;" ${sl?.has_contingency_plan?'checked':''}>
          <label for="slm-hasplan" style="margin:0;font-size:13px;cursor:pointer;">Este proveedor tiene plan de contingencia documentado</label>
        </div>
        <div style="margin-bottom:14px;">${lbl('Descripcion del plan de contingencia')}
          <textarea id="slm-desc" class="form-control" rows="2" style="font-size:13px;" placeholder="¿Como se garantiza la continuidad si este proveedor falla?">${UI.esc(sl?.contingency_description||'')}</textarea>
        </div>
        <div style="margin-bottom:14px;">${lbl('Procesos que dependen de este proveedor')}
          <div style="max-height:110px;overflow-y:auto;border:0.5px solid var(--border);border-radius:var(--radius);padding:8px;">
            ${_procs.length ? _procs.map(p=>`<label style="display:flex;gap:6px;align-items:center;padding:3px;font-size:13px;cursor:pointer;">
              <input type="checkbox" value="${p.id}" class="slm-pids" ${(sl?.process_ids||[]).includes(p.id)?'checked':''}>
              <span style="font-size:10px;color:${CRIT_COLORS[p.criticality]||'#666'};font-weight:700;">${p.criticality}</span>
              ${UI.esc(p.name)}
            </label>`).join('') : '<span style="font-size:12px;color:var(--text-subtle)">No hay procesos registrados.</span>'}
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

  return {
    render,
    _switchTab,
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
    _saveTest, _openTestResultModal, _saveTestResult, _onResultChange,
    _editSL, _saveSL, _delSL,
    _openEPModal, _saveEP,
    _handleDrop, _handleFileSelect,
    _setImportMode, _onFileSelect, _renderImportPreview, _confirmImport,
    _runBcpAiAnalysis,
  };
})();
