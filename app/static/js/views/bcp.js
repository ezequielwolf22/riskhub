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
      content.innerHTML = UI.notice('error', 'Error al cargar: ' + e.message);
    }
  }

  // ── Tab Overview ─────────────────────────────────────────────────────────────

  async function _tabOverview(el) {
    const [dash, iso] = await Promise.all([
      Api.get('/api/bcp/dashboard').catch(() => ({})),
      Api.get('/api/bcp/iso22301-status').catch(() => []),
    ]);

    const gaps = (iso || []).filter(c => c.status === 'gap');
    const partial = (iso || []).filter(c => c.status === 'partial');

    el.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px;">
      <div class="stat-card">
        <div class="stat-value">${dash.total_processes ?? 0}</div>
        <div class="stat-label">Procesos criticos</div>
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
      ${gaps.map(g => `<span class="badge badge-danger" style="margin:2px;">${g.clause} ${g.name}</span>`).join('')}
    </div>` : ''}

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
      <div class="card">
        <div class="card-header"><h3>Checklist ISO 22301</h3></div>
        <div class="card-body" style="padding:0;">
          <table class="data-table">
            <thead><tr><th>Clausula</th><th>Requisito</th><th>Estado</th></tr></thead>
            <tbody>
            ${(iso || []).map(c => `<tr>
              <td><strong>${c.clause}</strong></td>
              <td>${c.name}</td>
              <td><span class="badge badge-${c.status === 'ok' ? 'success' : c.status === 'partial' ? 'warning' : 'danger'}">
                ${c.status === 'ok' ? '&#10003; ok' : c.status === 'partial' ? '&#9888; parcial' : '&#10007; gap'}
              </span></td>
            </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><h3>Resumen de actividad</h3></div>
        <div class="card-body">
          <div style="display:grid;gap:10px;">
            <div style="display:flex;justify-content:space-between;">
              <span>Procesos sin test en 12 meses</span>
              <strong style="color:${(dash.processes_overdue_test??0)>0?'#DC2626':'#16a34a'}">${dash.processes_overdue_test ?? 0}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;">
              <span>Total tests programados</span>
              <strong>${dash.total_tests ?? 0}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;">
              <span>Ultimo test realizado</span>
              <strong>${dash.last_test_date ? new Date(dash.last_test_date).toLocaleDateString('es-ES') : '—'}</strong>
            </div>
            <div style="display:flex;justify-content:space-between;">
              <span>Clausulas OK / Parcial / Gap</span>
              <strong>${(iso||[]).filter(c=>c.status==='ok').length} / ${partial.length} / ${gaps.length}</strong>
            </div>
          </div>
        </div>
      </div>
    </div>`;
  }

  // ── Tab Procesos ─────────────────────────────────────────────────────────────

  async function _tabProcesses(el) {
    _procs = await Api.get('/api/bcp/processes').catch(() => []);
    el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h3 style="margin:0;">Procesos Criticos (${_procs.length})</h3>
      <button class="btn btn-primary" id="btn-new-proc">+ Nuevo proceso</button>
    </div>`;
    if (!_procs.length) {
      el.innerHTML += UI.empty('No hay procesos BIA. Registra los procesos criticos con sus objetivos de recuperacion.');
    } else {
      el.innerHTML += `
      <div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>Proceso</th><th>Criticidad</th><th>RTO</th><th>RPO</th><th>MTPD</th>
            <th>BIA%</th><th>Propietario</th><th>Ultimo test</th><th></th>
          </tr></thead>
          <tbody>
          ${_procs.map(p => `<tr>
            <td><strong>${UI.esc(p.name)}</strong></td>
            <td><span style="color:${CRIT_COLORS[p.criticality]};font-weight:700;">${p.criticality}</span></td>
            <td>${p.rto_hours != null ? p.rto_hours + 'h' : '—'}</td>
            <td>${p.rpo_hours != null ? p.rpo_hours + 'h' : '—'}</td>
            <td>${p.mtpd_hours != null ? p.mtpd_hours + 'h' : '—'}</td>
            <td>
              <div style="display:flex;align-items:center;gap:6px;">
                <div style="flex:1;height:6px;background:var(--bg-3);border-radius:3px;">
                  <div style="width:${p.bia_pct||0}%;height:100%;background:${(p.bia_pct||0)>=80?'#16a34a':(p.bia_pct||0)>=50?'#D97706':'#DC2626'};border-radius:3px;"></div>
                </div>
                <span style="font-size:11px;">${p.bia_pct||0}%</span>
              </div>
            </td>
            <td>${p.owner_id ? '#' + p.owner_id : '—'}</td>
            <td>${p.last_tested_at ? new Date(p.last_tested_at).toLocaleDateString('es-ES') : '—'}</td>
            <td>
              <button class="btn btn-sm btn-secondary" onclick="ViewBcp._editProc(${p.id})">Editar</button>
            </td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    }
    document.getElementById('btn-new-proc')?.addEventListener('click', () => _openProcModal());
  }

  // ── Tab BIA ──────────────────────────────────────────────────────────────────

  async function _tabBIA(el) {
    if (!_procs.length) _procs = await Api.get('/api/bcp/processes').catch(() => []);
    if (!_procs.length) {
      el.innerHTML = UI.empty('No hay procesos. Empieza creando procesos en la tab Procesos Criticos.');
      return;
    }
    const IMPACT_LABELS = ['Ninguno','Bajo','Medio','Alto'];
    const IMPACT_COLORS = ['#6B7280','#16a34a','#D97706','#DC2626'];
    el.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:16px;">
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
  }

  // ── Tab Dependencias ─────────────────────────────────────────────────────────

  async function _tabDependencies(el) {
    [_procs, _deps] = await Promise.all([
      _procs.length ? Promise.resolve(_procs) : Api.get('/api/bcp/processes').catch(() => []),
      Api.get('/api/bcp/dependencies').catch(() => []),
    ]);
    const DEP_ICONS = {
      IT_system:'ti-server', personnel:'ti-users', facility:'ti-building',
      supplier:'ti-truck', utility:'ti-bolt', communication:'ti-phone',
      transport:'ti-car', external_service:'ti-cloud',
    };
    el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <div style="display:flex;gap:8px;align-items:center;">
        <h3 style="margin:0;">Dependencias (${_deps.length})</h3>
        <select id="dep-filter" class="form-control" style="width:200px;">
          <option value="">Todos los procesos</option>
          ${_procs.map(p => `<option value="${p.id}">${UI.esc(p.name)}</option>`).join('')}
        </select>
      </div>
      <button class="btn btn-primary" id="btn-new-dep">+ Nueva dependencia</button>
    </div>
    <div id="dep-table-wrap"></div>`;

    const renderDeps = (filter) => {
      const list = filter ? _deps.filter(d => d.process_id == filter) : _deps;
      const wrap = document.getElementById('dep-table-wrap');
      if (!list.length) { wrap.innerHTML = UI.empty('No hay dependencias registradas.'); return; }
      const procName = id => (_procs.find(p => p.id == id)||{}).name || '#'+id;
      wrap.innerHTML = `
      <div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>Tipo</th><th>Recurso</th><th>Proceso</th>
            <th>Qty normal</th><th>Qty recuperacion</th><th>RTO nec.</th>
            <th>Critico</th><th>Alternativa</th><th></th>
          </tr></thead>
          <tbody>
          ${list.map(d => `<tr>
            <td><i class="ti ${DEP_ICONS[d.dependency_type]||'ti-circle'}"></i> ${d.dependency_type}</td>
            <td>${UI.esc(d.name)}</td>
            <td>${UI.esc(procName(d.process_id))}</td>
            <td>${d.qty_normal ?? '—'}</td>
            <td>${d.qty_recovery ?? '—'}</td>
            <td>${d.rto_hours != null ? d.rto_hours + 'h' : '—'}</td>
            <td>${d.is_critical ? '<span class="badge badge-danger">Si</span>' : '<span class="badge">No</span>'}</td>
            <td style="max-width:150px;overflow:hidden;text-overflow:ellipsis;">${d.alternative ? UI.esc(d.alternative.substring(0,40)) : '—'}</td>
            <td><button class="btn btn-sm btn-secondary" onclick="ViewBcp._editDep(${d.id})">Editar</button></td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    };
    renderDeps('');
    document.getElementById('dep-filter')?.addEventListener('change', e => renderDeps(e.target.value));
    document.getElementById('btn-new-dep')?.addEventListener('click', () => _openDepModal());
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
      el.innerHTML += UI.empty('No hay estrategias de recuperacion. ISO 22301 cl. 8.3 requiere definir al menos una estrategia por proceso critico.');
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

  async function _tabPlans(el) {
    [_procs, _plans] = await Promise.all([
      _procs.length ? Promise.resolve(_procs) : Api.get('/api/bcp/processes').catch(() => []),
      Api.get('/api/bcp/plans').catch(() => []),
    ]);
    el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <h3 style="margin:0;">Planes BCP/DRP (${_plans.length})</h3>
      <button class="btn btn-primary" id="btn-new-plan">+ Nuevo plan</button>
    </div>`;
    if (!_plans.length) {
      el.innerHTML += UI.empty('No hay planes BCP/DRP. ISO 22301 cl. 8.4 requiere planes documentados de continuidad.');
    } else {
      el.innerHTML += `
      <div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>Codigo</th><th>Tipo</th><th>Nombre</th><th>Version</th><th>Estado</th>
            <th>Doc. vinculado</th><th>Procesos</th><th>Ultima prueba</th><th></th>
          </tr></thead>
          <tbody>
          ${_plans.map(p => `<tr>
            <td>${UI.codePill(p.code)}</td>
            <td><span class="badge">${p.plan_type}</span></td>
            <td>${UI.esc(p.name)}</td>
            <td>${UI.esc(p.version || '1.0')}</td>
            <td><span class="badge badge-${p.status==='approved'?'success':p.status==='under_review'?'warning':'secondary'}"
              style="background:${STATUS_COLORS[p.status]||'#666'}22;color:${STATUS_COLORS[p.status]||'#666'};">${p.status}</span></td>
            <td>${p.document_id ? `<a href="#/ai-documents" title="Doc #${p.document_id}"><i class="ti ti-file"></i> #${p.document_id}</a>` : '—'}</td>
            <td>${(p.process_ids||[]).length}</td>
            <td>${p.last_exercised_at ? new Date(p.last_exercised_at).toLocaleDateString('es-ES') : '—'}</td>
            <td style="display:flex;gap:4px;">
              <button class="btn btn-sm btn-secondary" onclick="ViewBcp._editPlan(${p.id})">Editar</button>
              ${['draft','under_review'].includes(p.status) ?
                `<button class="btn btn-sm btn-primary" onclick="ViewBcp._approvePlan(${p.id})">Aprobar</button>` : ''}
            </td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    }
    document.getElementById('btn-new-plan')?.addEventListener('click', () => _openPlanModal());
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
      testsList.innerHTML = UI.empty('No hay tests programados. ISO 22301 cl. 8.5 requiere ejercicios periodicos.');
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
      el.innerHTML += UI.empty('No hay proveedores vinculados al BCP. ISO 22301 cl. 8.2 requiere identificar proveedores criticos.');
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

  // ── Tab Importar Excel ───────────────────────────────────────────────────────

  function _tabImport(el) {
    el.innerHTML = `
    <div style="max-width:700px;">
      <h3>Importar datos BCP desde Excel</h3>
      <div class="card" style="margin-bottom:16px;">
        <div class="card-body">
          <p>El archivo Excel debe contener 3 hojas:</p>
          <ul style="font-size:13px;line-height:1.8;">
            <li><strong>Procesos</strong>: Nombre *, Criticidad, RTO, RPO, MTPD, Descripcion, Propietario, Prioridad</li>
            <li><strong>Dependencias</strong>: Proceso *, Tipo *, Nombre *, RTO necesario, Es critico</li>
            <li><strong>Proveedores BCM</strong>: Proveedor *, Criticidad BCM, RTO impacto</li>
          </ul>
          <a class="btn btn-secondary" href="/api/bcp/import/template" download>
            <i class="ti ti-download"></i> Descargar plantilla Excel
          </a>
        </div>
      </div>

      <div class="card" id="import-step1">
        <div class="card-header"><h4>Paso 1 — Seleccionar archivo</h4></div>
        <div class="card-body">
          <div id="drop-zone" style="border:2px dashed var(--border);border-radius:8px;padding:30px;text-align:center;cursor:pointer;transition:.2s;"
            ondragover="event.preventDefault();this.style.borderColor='var(--primary)'"
            ondragleave="this.style.borderColor='var(--border)'"
            ondrop="ViewBcp._handleDrop(event)">
            <i class="ti ti-table-import" style="font-size:32px;color:var(--text-muted);"></i>
            <div style="margin-top:8px;color:var(--text-muted);">Arrastra un .xlsx aqui o</div>
            <label style="margin-top:8px;display:inline-block;" class="btn btn-secondary btn-sm">
              Seleccionar archivo
              <input type="file" id="import-file" accept=".xlsx,.xls" style="display:none;"
                onchange="ViewBcp._handleFileSelect(this.files[0])">
            </label>
          </div>
        </div>
      </div>

      <div id="import-step2" style="display:none;" class="card">
        <div class="card-header"><h4>Paso 2 — Vista previa</h4></div>
        <div class="card-body" id="import-preview-body"></div>
      </div>
    </div>`;
  }

  async function _handleDrop(event) {
    event.preventDefault();
    document.getElementById('drop-zone').style.borderColor = 'var(--border)';
    const file = event.dataTransfer.files[0];
    if (file) await _handleFileSelect(file);
  }

  async function _handleFileSelect(file) {
    if (!file || !file.name.match(/\.(xlsx|xls)$/i)) {
      UI.toast('Solo se aceptan archivos .xlsx o .xls', 'error');
      return;
    }
    UI.toast('Leyendo archivo...', 'info');
    try {
      const preview = await Api.postFile('/api/bcp/import/preview', file);
      document.getElementById('import-step2').style.display = '';
      const body = document.getElementById('import-preview-body');
      body.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px;">
        <div class="stat-card"><div class="stat-value">${preview.summary.processes_found}</div><div class="stat-label">Procesos detectados</div></div>
        <div class="stat-card"><div class="stat-value">${preview.summary.dependencies_found}</div><div class="stat-label">Dependencias</div></div>
        <div class="stat-card"><div class="stat-value">${preview.summary.suppliers_found}</div><div class="stat-label">Proveedores BCM</div></div>
      </div>
      ${preview.errors.length ? `<div class="notice notice-warning"><strong>Advertencias:</strong> ${preview.errors.join('; ')}</div>` : ''}
      ${preview.processes.length ? `
      <h4>Primeros procesos a importar:</h4>
      <table class="data-table">
        <thead><tr><th>Nombre</th><th>Criticidad</th><th>RTO</th><th>RPO</th></tr></thead>
        <tbody>
        ${preview.processes.map(p => `<tr>
          <td>${UI.esc(p.name)}</td>
          <td>${p.criticality}</td>
          <td>${p.rto_hours != null ? p.rto_hours + 'h' : '—'}</td>
          <td>${p.rpo_hours != null ? p.rpo_hours + 'h' : '—'}</td>
        </tr>`).join('')}
        </tbody>
      </table>` : ''}
      <div style="display:flex;gap:8px;margin-top:16px;">
        <button class="btn btn-primary" id="btn-confirm-import">
          <i class="ti ti-check"></i> Confirmar importacion
        </button>
        <button class="btn btn-secondary" onclick="document.getElementById('import-step2').style.display='none'">
          Cancelar
        </button>
      </div>`;
      document.getElementById('btn-confirm-import').addEventListener('click', () => _confirmImport(file));
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  async function _confirmImport(file) {
    try {
      const res = await Api.postFile('/api/bcp/import/confirm', file);
      UI.toast(`Importacion completada: ${res.created.processes} procesos, ${res.created.dependencies} dependencias, ${res.created.supplier_links} proveedores`, 'success');
      _procs = [];
      setTimeout(() => _switchTab('processes'), 1500);
    } catch (e) {
      UI.toast('Error importando: ' + (e.message || e), 'error');
    }
  }

  // ── Modales — Proceso ────────────────────────────────────────────────────────

  function _openProcModal(proc) {
    const CRIT = ['critical','high','medium','low'];
    const IMPACTS = ['0 — Ninguno','1 — Bajo','2 — Medio','3 — Alto'];
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:640px;">
      <div class="modal-header">
        <h2>${proc ? 'Editar proceso BIA' : 'Nuevo proceso critico'}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div style="grid-column:1/-1;"><label>Nombre *</label>
            <input id="pm-name" class="form-control" value="${UI.esc(proc?.name||'')}"></div>
          <div><label>Criticidad</label>
            <select id="pm-crit" class="form-control">
              ${CRIT.map(c=>`<option value="${c}"${proc?.criticality===c?' selected':''}>${c}</option>`).join('')}
            </select></div>
          <div><label>Prioridad</label><input id="pm-prio" class="form-control" type="number" value="${proc?.priority||''}"></div>
          <div><label>Responsable (ID usuario)</label><input id="pm-owner" class="form-control" type="number" value="${proc?.owner_id||''}"></div>
          <div><label>Resp. recuperacion (ID)</label><input id="pm-rowner" class="form-control" type="number" value="${proc?.recovery_owner_id||''}"></div>
        </div>

        <details open style="margin-top:14px;"><summary style="cursor:pointer;font-weight:600;margin-bottom:10px;">Objetivos BIA (RTO/RPO/MTPD/MBCO)</summary>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">
          <div><label>RTO (h)</label><input id="pm-rto" class="form-control" type="number" value="${proc?.rto_hours??''}"></div>
          <div><label>RPO (h)</label><input id="pm-rpo" class="form-control" type="number" value="${proc?.rpo_hours??''}"></div>
          <div><label>MTPD (h)</label><input id="pm-mtpd" class="form-control" type="number" value="${proc?.mtpd_hours??''}"></div>
          <div><label>Staff min.</label><input id="pm-staff" class="form-control" type="number" value="${proc?.min_recovery_staff??''}"></div>
        </div>
        <div style="margin-top:8px;"><label>MBCO</label>
          <input id="pm-mbco" class="form-control" value="${UI.esc(proc?.mbco||'')}" placeholder="Nivel minimo de servicio aceptable"></div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:8px;">
          ${[['pm-fi','Financiero','financial_impact'],['pm-ri','Reputacional','reputational_impact'],
             ['pm-li','Legal','legal_impact'],['pm-oi','Operacional','operational_impact']].map(([id,lbl,fld])=>`
          <div><label>${lbl}</label><select id="${id}" class="form-control">
            ${IMPACTS.map((imp,i)=>`<option value="${i}"${proc?.[fld]===i?' selected':''}>${imp}</option>`).join('')}
          </select></div>`).join('')}
        </div>
        </details>

        <details style="margin-top:14px;"><summary style="cursor:pointer;font-weight:600;margin-bottom:10px;">Documentacion y procedimientos</summary>
        <label>Descripcion</label>
        <textarea id="pm-desc" class="form-control" rows="2">${UI.esc(proc?.description||'')}</textarea>
        <label style="margin-top:8px;">Criterios de activacion</label>
        <textarea id="pm-activ" class="form-control" rows="2">${UI.esc(proc?.activation_criteria||'')}</textarea>
        <label style="margin-top:8px;">Procedimiento alternativo</label>
        <textarea id="pm-altproc" class="form-control" rows="2">${UI.esc(proc?.alternative_procedure||'')}</textarea>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px;">
          <div><label>Sistemas IT (JSON)</label>
            <textarea id="pm-it" class="form-control" rows="2">${proc?.it_systems ? JSON.stringify(proc.it_systems,null,2) : ''}</textarea></div>
          <div><label>Instalaciones (JSON)</label>
            <textarea id="pm-fac" class="form-control" rows="2">${proc?.facilities ? JSON.stringify(proc.facilities,null,2) : ''}</textarea></div>
        </div>
        </details>

        <div style="display:flex;gap:8px;margin-top:16px;">
          <button class="btn btn-primary" onclick="ViewBcp._saveProc(${proc?.id||'null'})">Guardar</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          ${proc ? `<button class="btn btn-danger" style="margin-left:auto;" onclick="ViewBcp._delProc(${proc.id})">Eliminar</button>` : ''}
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
    const g = id => document.getElementById(id);
    const body = {
      name: g('pm-name').value.trim(),
      criticality: g('pm-crit').value,
      priority: parseInt(g('pm-prio').value)||null,
      rto_hours: parseInt(g('pm-rto').value)||null,
      rpo_hours: parseInt(g('pm-rpo').value)||null,
      mtpd_hours: parseInt(g('pm-mtpd').value)||null,
      mbco: g('pm-mbco').value||null,
      financial_impact: parseInt(g('pm-fi').value),
      reputational_impact: parseInt(g('pm-ri').value),
      legal_impact: parseInt(g('pm-li').value),
      operational_impact: parseInt(g('pm-oi').value),
      min_recovery_staff: parseInt(g('pm-staff').value)||null,
      description: g('pm-desc').value||null,
      activation_criteria: g('pm-activ').value||null,
      alternative_procedure: g('pm-altproc').value||null,
      owner_id: parseInt(g('pm-owner').value)||null,
      recovery_owner_id: parseInt(g('pm-rowner').value)||null,
    };
    try {
      const itVal = g('pm-it').value.trim();
      body.it_systems = itVal ? JSON.parse(itVal) : null;
    } catch(e) { body.it_systems = g('pm-it').value ? [g('pm-it').value] : null; }
    try {
      const facVal = g('pm-fac').value.trim();
      body.facilities = facVal ? JSON.parse(facVal) : null;
    } catch(e) { body.facilities = g('pm-fac').value ? [g('pm-fac').value] : null; }
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

  function _openDepModal(dep) {
    const DEP_TYPES = ['IT_system','personnel','facility','supplier','utility','communication','transport','external_service'];
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:520px;">
      <div class="modal-header">
        <h2>${dep ? 'Editar dependencia' : 'Nueva dependencia'}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <div><label>Proceso *</label>
            <select id="dm-proc" class="form-control">
              ${_procs.map(p=>`<option value="${p.id}"${dep?.process_id===p.id?' selected':''}>${UI.esc(p.name)}</option>`).join('')}
            </select></div>
          <div><label>Tipo *</label>
            <select id="dm-type" class="form-control">
              ${DEP_TYPES.map(t=>`<option value="${t}"${dep?.dependency_type===t?' selected':''}>${t}</option>`).join('')}
            </select></div>
          <div style="grid-column:1/-1;"><label>Nombre *</label>
            <input id="dm-name" class="form-control" value="${UI.esc(dep?.name||'')}"></div>
          <div><label>Qty normal</label><input id="dm-qn" class="form-control" type="number" value="${dep?.qty_normal??''}"></div>
          <div><label>Qty recuperacion</label><input id="dm-qr" class="form-control" type="number" value="${dep?.qty_recovery??''}"></div>
          <div><label>RTO necesario (h)</label><input id="dm-rto" class="form-control" type="number" value="${dep?.rto_hours??''}"></div>
          <div style="display:flex;align-items:center;gap:8px;padding-top:20px;">
            <input id="dm-crit" type="checkbox" ${dep?.is_critical?' checked':''}>
            <label for="dm-crit" style="margin:0;">Es critico</label>
          </div>
          <div style="grid-column:1/-1;"><label>Alternativa</label>
            <textarea id="dm-alt" class="form-control" rows="2">${UI.esc(dep?.alternative||'')}</textarea></div>
        </div>
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewBcp._saveDep(${dep?.id||'null'})">Guardar</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          ${dep ? `<button class="btn btn-danger" style="margin-left:auto;" onclick="ViewBcp._delDep(${dep.id})">Eliminar</button>` : ''}
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  function _editDep(id) { _openDepModal(_deps.find(d => d.id === id)); }

  async function _saveDep(id) {
    const body = {
      process_id: parseInt(document.getElementById('dm-proc').value),
      dependency_type: document.getElementById('dm-type').value,
      name: document.getElementById('dm-name').value.trim(),
      qty_normal: parseInt(document.getElementById('dm-qn').value)||null,
      qty_recovery: parseInt(document.getElementById('dm-qr').value)||null,
      rto_hours: parseInt(document.getElementById('dm-rto').value)||null,
      is_critical: document.getElementById('dm-crit').checked,
      alternative: document.getElementById('dm-alt').value||null,
    };
    if (!body.name) { UI.toast('El nombre es obligatorio', 'error'); return; }
    try {
      if (id) await Api.patch(`/api/bcp/dependencies/${id}`, body);
      else await Api.post('/api/bcp/dependencies', body);
      UI.toast('Dependencia guardada', 'success');
      document.querySelector('.modal-bg')?.remove();
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
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:520px;">
      <div class="modal-header">
        <h2>${strat ? 'Editar estrategia' : 'Nueva estrategia'}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <div><label>Tipo *</label>
            <select id="sm-type" class="form-control">
              ${TYPES.map(t=>`<option value="${t}"${strat?.strategy_type===t?' selected':''}>${t}</option>`).join('')}
            </select></div>
          <div><label>Estado implementacion</label>
            <select id="sm-status" class="form-control">
              ${['planned','in_progress','implemented','tested'].map(s=>
                `<option value="${s}"${strat?.implementation_status===s?' selected':''}>${s}</option>`).join('')}
            </select></div>
          <div style="grid-column:1/-1;"><label>Nombre *</label>
            <input id="sm-name" class="form-control" value="${UI.esc(strat?.name||'')}"></div>
          <div><label>Proceso vinculado (opcional)</label>
            <select id="sm-proc" class="form-control">
              <option value="">Global (sin proceso)</option>
              ${_procs.map(p=>`<option value="${p.id}"${strat?.process_id===p.id?' selected':''}>${UI.esc(p.name)}</option>`).join('')}
            </select></div>
          <div><label>Coste estimado (€)</label>
            <input id="sm-cost" class="form-control" type="number" value="${strat?.estimated_cost??''}"></div>
          <div><label>Responsable (ID)</label>
            <input id="sm-resp" class="form-control" type="number" value="${strat?.responsible_id||''}"></div>
          <div><label>Fecha objetivo</label>
            <input id="sm-date" class="form-control" type="date" value="${strat?.target_date?strat.target_date.substring(0,10):''}"></div>
          <div style="grid-column:1/-1;"><label>Descripcion</label>
            <textarea id="sm-desc" class="form-control" rows="2">${UI.esc(strat?.description||'')}</textarea></div>
        </div>
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewBcp._saveStrat(${strat?.id||'null'})">Guardar</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          ${strat ? `<button class="btn btn-danger" style="margin-left:auto;" onclick="ViewBcp._delStrat(${strat.id})">Eliminar</button>` : ''}
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

  // ── Modales — Plan ───────────────────────────────────────────────────────────

  function _openPlanModal(plan) {
    const TYPES = ['bcp','drp','crp','ems','pandemic','cyber_response','supply_chain'];
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:560px;">
      <div class="modal-header">
        <h2>${plan ? 'Editar plan' : 'Nuevo plan BCP/DRP'}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <div><label>Tipo *</label>
            <select id="plm-type" class="form-control">
              ${TYPES.map(t=>`<option value="${t}"${plan?.plan_type===t?' selected':''}>${t}</option>`).join('')}
            </select></div>
          <div><label>Version</label><input id="plm-ver" class="form-control" value="${UI.esc(plan?.version||'1.0')}"></div>
          <div style="grid-column:1/-1;"><label>Nombre *</label>
            <input id="plm-name" class="form-control" value="${UI.esc(plan?.name||'')}"></div>
          <div style="grid-column:1/-1;"><label>Alcance</label>
            <textarea id="plm-scope" class="form-control" rows="2">${UI.esc(plan?.scope||'')}</textarea></div>
          <div style="grid-column:1/-1;"><label>Criterios de activacion</label>
            <textarea id="plm-activ" class="form-control" rows="2">${UI.esc(plan?.activation_criteria||'')}</textarea></div>
          <div style="grid-column:1/-1;"><label>Resumen de contenido</label>
            <textarea id="plm-sum" class="form-control" rows="2">${UI.esc(plan?.content_summary||'')}</textarea></div>
          <div><label>ID documento vinculado</label>
            <input id="plm-doc" class="form-control" type="number" value="${plan?.document_id||''}"></div>
          <div><label>Fecha revision</label>
            <input id="plm-rev" class="form-control" type="date" value="${plan?.review_date?plan.review_date.substring(0,10):''}"></div>
          <div style="grid-column:1/-1;"><label>Procesos cubiertos</label>
            <div style="max-height:120px;overflow-y:auto;border:1px solid var(--border);border-radius:4px;padding:6px;">
            ${_procs.map(p => `<label style="display:flex;gap:6px;align-items:center;padding:2px;">
              <input type="checkbox" value="${p.id}" class="plm-pids"
                ${(plan?.process_ids||[]).includes(p.id)?'checked':''}> ${UI.esc(p.name)}
            </label>`).join('')}
            </div>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewBcp._savePlan(${plan?.id||'null'})">Guardar</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  function _editPlan(id) { _openPlanModal(_plans.find(p => p.id === id)); }

  async function _savePlan(id) {
    const pids = [...document.querySelectorAll('.plm-pids:checked')].map(c => parseInt(c.value));
    const body = {
      plan_type: document.getElementById('plm-type').value,
      name: document.getElementById('plm-name').value.trim(),
      version: document.getElementById('plm-ver').value||'1.0',
      scope: document.getElementById('plm-scope').value||null,
      activation_criteria: document.getElementById('plm-activ').value||null,
      content_summary: document.getElementById('plm-sum').value||null,
      document_id: parseInt(document.getElementById('plm-doc').value)||null,
      review_date: document.getElementById('plm-rev').value||null,
      process_ids: pids,
    };
    if (!body.name) { UI.toast('El nombre es obligatorio', 'error'); return; }
    try {
      if (id) await Api.patch(`/api/bcp/plans/${id}`, body);
      else await Api.post('/api/bcp/plans', body);
      UI.toast('Plan guardado', 'success');
      document.querySelector('.modal-bg')?.remove();
      _plans = [];
      _switchTab('plans');
    } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
  }

  async function _approvePlan(id) {
    if (!confirm('Aprobar este plan? Su estado cambiara a "approved".')) return;
    try {
      await Api.post(`/api/bcp/plans/${id}/approve`, {});
      UI.toast('Plan aprobado', 'success');
      _plans = [];
      _switchTab('plans');
    } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
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
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:480px;">
      <div class="modal-header">
        <h2>Resultado: ${UI.esc(test.code)}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <label>Fecha de realizacion</label>
        <input id="rm-date" class="form-control" type="datetime-local"
          value="${test.conducted_at?(test.conducted_at.replace('Z','')||''):''}">
        <label style="margin-top:10px;">Resultado</label>
        <select id="rm-result" class="form-control">
          <option value="">Sin resultado</option>
          ${['passed','partial','failed'].map(r=>
            `<option value="${r}"${test.result===r?' selected':''}>${r}</option>`).join('')}
        </select>
        <label style="margin-top:10px;">Hallazgos</label>
        <textarea id="rm-findings" class="form-control" rows="3">${UI.esc(test.findings||'')}</textarea>
        <label style="margin-top:10px;">Lecciones aprendidas</label>
        <textarea id="rm-lessons" class="form-control" rows="3">${UI.esc(test.lessons_learned||'')}</textarea>
        <label style="margin-top:10px;">Acciones de mejora</label>
        <textarea id="rm-actions" class="form-control" rows="2">${UI.esc(test.improvement_actions||'')}</textarea>
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewBcp._saveTestResult(${id})">Guardar</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _saveTestResult(id) {
    const body = {
      conducted_at: document.getElementById('rm-date').value||null,
      result: document.getElementById('rm-result').value||null,
      findings: document.getElementById('rm-findings').value||null,
      lessons_learned: document.getElementById('rm-lessons').value||null,
      improvement_actions: document.getElementById('rm-actions').value||null,
    };
    try {
      await Api.patch(`/api/bcp/tests/${id}`, body);
      UI.toast('Resultado guardado', 'success');
      document.querySelector('.modal-bg')?.remove();
      _switchTab('tests');
    } catch (e) { UI.toast('Error: ' + (e.message || e), 'error'); }
  }

  // ── Modales — Proveedor BCM ──────────────────────────────────────────────────

  function _openSLModal(sl) {
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:520px;">
      <div class="modal-header">
        <h2>${sl ? 'Editar vinculo BCM' : 'Vincular proveedor BCM'}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <div><label>Proveedor *</label>
            <select id="slm-sup" class="form-control" ${sl?'disabled':''}>
              ${_suppliers.map(s=>`<option value="${s.id}"${sl?.supplier_id===s.id?' selected':''}>${UI.esc(s.name)}</option>`).join('')}
            </select></div>
          <div><label>Criticidad BCM</label>
            <select id="slm-crit" class="form-control">
              ${['critical','high','medium','low'].map(c=>
                `<option value="${c}"${sl?.criticality===c?' selected':''}>${c}</option>`).join('')}
            </select></div>
          <div><label>RTO impacto (h)</label>
            <input id="slm-rto" class="form-control" type="number" value="${sl?.rto_impact_hours??''}"></div>
          <div><label>SLA contrato (h)</label>
            <input id="slm-sla" class="form-control" type="number" value="${sl?.contract_sla_hours??''}"></div>
          <div style="display:flex;align-items:center;gap:8px;padding-top:20px;">
            <input id="slm-hasplan" type="checkbox" ${sl?.has_contingency_plan?'checked':''}>
            <label for="slm-hasplan" style="margin:0;">Tiene plan de contingencia</label>
          </div>
          <div><label>Proveedor alternativo</label>
            <select id="slm-alt" class="form-control">
              <option value="">Ninguno</option>
              ${_suppliers.filter(s=>s.id!==sl?.supplier_id).map(s=>
                `<option value="${s.id}"${sl?.alternative_supplier_id===s.id?' selected':''}>${UI.esc(s.name)}</option>`).join('')}
            </select></div>
          <div><label>Ultima revision</label>
            <input id="slm-rev" class="form-control" type="date" value="${sl?.last_review_date?sl.last_review_date.substring(0,10):''}"></div>
          <div style="grid-column:1/-1;"><label>Descripcion plan contingencia</label>
            <textarea id="slm-desc" class="form-control" rows="2">${UI.esc(sl?.contingency_description||'')}</textarea></div>
          <div style="grid-column:1/-1;"><label>Procesos dependientes</label>
            <div style="max-height:100px;overflow-y:auto;border:1px solid var(--border);border-radius:4px;padding:6px;">
              ${_procs.map(p=>`<label style="display:flex;gap:6px;align-items:center;padding:2px;">
                <input type="checkbox" value="${p.id}" class="slm-pids"
                  ${(sl?.process_ids||[]).includes(p.id)?'checked':''}> ${UI.esc(p.name)}
              </label>`).join('')}
            </div>
          </div>
        </div>
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewBcp._saveSL(${sl?.id||'null'})">Guardar</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
          ${sl ? `<button class="btn btn-danger" style="margin-left:auto;" onclick="ViewBcp._delSL(${sl.id})">Eliminar</button>` : ''}
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
    _editProc, _saveProc, _delProc,
    _editDep, _saveDep, _delDep,
    _editStrat, _saveStrat, _delStrat,
    _editPlan, _savePlan, _approvePlan,
    _saveTest, _openTestResultModal, _saveTestResult,
    _editSL, _saveSL, _delSL,
    _openEPModal, _saveEP,
    _handleDrop, _handleFileSelect,
  };
})();
