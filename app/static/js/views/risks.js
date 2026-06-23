/* Vista Riesgos - identificación, analisis, evaluación, tratamiento. */
const ViewRisks = {
  _assets: [], _threats: [], _vulns: [], _impls: [],
  _assetFilter: null,
  _groupFilter: null,   // {id, name} para filtrar por grupo
  _riskTab: 'list',     // 'list' | 'groups'
  _sortCol: 'residual_level', _sortAsc: false,
  _page: 0, _pageSize: 50, _allData: [],

  async render(main) {
    const canEdit = Auth.canEdit();

    // Leer parametros de URL
    const assetMatch = location.hash.match(/[?&]asset_id=(\d+)/);
    const threatMatch = location.hash.match(/[?&]threat_id=(\d+)/);
    const vulnMatch = location.hash.match(/[?&]vulnerability_id=(\d+)/);
    const ownerParam = (location.hash.match(/[?&]owner=([^&]+)/) || [])[1] || null;
    const overdueParam = /[?&]overdue=1/.test(location.hash);
    const supplierOnlyParam = /[?&]supplier_only=1/.test(location.hash);
    ViewRisks._assetFilter = null;
    ViewRisks._threatFilter = null;
    ViewRisks._vulnFilter = null;

    main.innerHTML = UI.sectionHeader(
      t('risks.title'),
      t('risks.subtitle'),
      canEdit ? `<button class="btn btn-primary" id="btn-new">+ ${t('risks.new')}</button><button class="btn btn-ghost" id="btn-discover-ai" style="margin-left:8px;" title="El agente IA identifica riesgos no registrados analizando el contexto de la organizacion">Descubrir con IA</button>` : ''
    ) + `
      <div style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:16px;">
        <button class="risk-tab-btn" data-risk-tab="list"
          style="padding:8px 18px;border:none;background:none;cursor:pointer;font-size:14px;
                 font-weight:600;color:var(--brand-purple);border-bottom:3px solid var(--brand-purple);margin-bottom:-2px;">
          ${t('risks.filter.all')}
        </button>
        <button class="risk-tab-btn" data-risk-tab="groups"
          style="padding:8px 18px;border:none;background:none;cursor:pointer;font-size:14px;
                 font-weight:600;color:var(--text-muted);border-bottom:3px solid transparent;margin-bottom:-2px;">
          ${t('risks.group_by')}
        </button>
      </div>
      <div id="risk-tab-list">
        <div class="toolbar">
          <input type="search" id="r-search" placeholder="${t('common.search')}...">
          <select id="r-status">
            <option value="">${t('common.all')}</option>
            <option value="identified">${t('risks.status.identified')}</option>
            <option value="assessed">${t('risks.status.assessed')}</option>
            <option value="treated">${t('risks.status.treated')}</option>
            <option value="accepted">${t('risks.status.accepted')}</option>
            <option value="closed">${t('risks.status.closed')}</option>
          </select>
          <select id="r-band">
            <option value="">${t('common.all')}</option>
            <option value="6">${t('risks.filter.high')}</option>
            <option value="3">${t('risks.medium_high_filter')}</option>
          </select>
          <select id="r-treatment">
            <option value="">${t('common.all')}</option>
            <option value="modification">${t('risks.treatment_decision.reduce')}</option>
            <option value="retention">${t('risks.treatment_decision.accept')}</option>
            <option value="avoidance">${t('risks.treatment_decision.avoid')}</option>
            <option value="sharing">${t('risks.treatment_decision.transfer')}</option>
            <option value="__none__">${t('common.not_assigned')}</option>
          </select>
          <select id="r-owner">
            <option value="">${t('common.all')}</option>
          </select>
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;white-space:nowrap;">
            <input type="checkbox" id="r-overdue"> ${t('risks.filter.overdue')}
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;white-space:nowrap;">
            <input type="checkbox" id="r-supplier-only"> ${t('risks.supplier_only')}
          </label>
          <button class="btn btn-ghost" id="r-export-csv" title="${t('common.export')}" style="margin-left:auto;">${t('risks.export_excel')}</button>
          ${canEdit ? `
          <button class="btn btn-ghost" id="r-import-tpl" title="${t('risks.template_csv')}">${t('risks.template_csv')}</button>
          <label class="btn btn-ghost" style="cursor:pointer;margin:0;" title="Importar riesgos desde CSV">
            ${t('risks.import_csv')}
            <input type="file" id="r-import-file" accept=".csv" style="display:none;">
          </label>` : ''}
        </div>
        <div id="r-asset-filter" style="display:none;margin-bottom:8px;"></div>
        <div id="r-list"></div>
      </div>
      <div id="risk-tab-groups" style="display:none;">
        <div id="r-group-view"><div class="notice">${t('common.loading')}</div></div>
      </div>
    `;

    // Tab switching
    main.querySelectorAll('.risk-tab-btn').forEach(btn => {
      btn.onclick = () => {
        main.querySelectorAll('.risk-tab-btn').forEach(b => {
          b.style.color = 'var(--text-muted)';
          b.style.borderBottomColor = 'transparent';
        });
        btn.style.color = 'var(--brand-purple)';
        btn.style.borderBottomColor = 'var(--brand-purple)';
        const tab = btn.dataset.riskTab;
        ViewRisks._riskTab = tab;
        document.getElementById('risk-tab-list').style.display = tab === 'list' ? '' : 'none';
        document.getElementById('risk-tab-groups').style.display = tab === 'groups' ? '' : 'none';
        if (tab === 'groups') ViewRisks._renderGroupView();
      };
    });
    if (canEdit) {
      document.getElementById('btn-new').onclick = () => ViewRisks._edit();
      const _dBtn = document.getElementById('btn-discover-ai');
      if (_dBtn) _dBtn.onclick = () => ViewRisks._discoverRisks();
    }
    document.getElementById('r-search').oninput = () => { ViewRisks._page = 0; ViewRisks._reload(); };
    document.getElementById('r-status').onchange = () => { ViewRisks._page = 0; ViewRisks._reload(); };
    document.getElementById('r-band').onchange = () => { ViewRisks._page = 0; ViewRisks._reload(); };
    document.getElementById('r-treatment').onchange = () => { ViewRisks._page = 0; ViewRisks._reload(); };
    document.getElementById('r-owner').onchange = () => { ViewRisks._page = 0; ViewRisks._reload(); };
    document.getElementById('r-overdue').onchange = () => { ViewRisks._page = 0; ViewRisks._reload(); };
    document.getElementById('r-supplier-only').onchange = () => { ViewRisks._page = 0; ViewRisks._reload(); };
    document.getElementById('r-export-csv').onclick = async () => {
      try { await Api.risks.exportCsv(); UI.toast('CSV descargado', 'success'); }
      catch (e) { UI.toast(e.message, 'error'); }
    };
    if (canEdit) {
      document.getElementById('r-import-tpl').onclick = () => Api.risks.importTemplate();
      document.getElementById('r-import-file').onchange = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        try {
          UI.toast('Importando riesgos...', 'info');
          const result = await Api.risks.importCsv(file);
          UI.toast(
            `${result.created} riesgo${result.created !== 1 ? 's' : ''} importado${result.created !== 1 ? 's' : ''}` +
            (result.skipped > 0 ? ` · ${result.skipped} omitido${result.skipped !== 1 ? 's' : ''}` : ''),
            result.created > 0 ? 'success' : 'warn'
          );
          if (result.detail_skipped?.length > 0) {
            console.warn('Filas omitidas:', result.detail_skipped);
          }
          ViewRisks._reload();
        } catch (err) { UI.toast('Error: ' + err.message, 'error'); }
        e.target.value = '';
      };
    }

    // Precargar catálogos en memoria
    await ViewRisks._loadCatalogs();

    // Aplicar filtro de activo si viene de URL
    if (assetMatch) {
      const assetId = parseInt(assetMatch[1]);
      const asset = ViewRisks._assets.find(a => a.id === assetId);
      if (asset) {
        ViewRisks._assetFilter = { id: assetId, name: asset.name };
        const filterDiv = document.getElementById('r-asset-filter');
        filterDiv.style.display = 'block';
        filterDiv.innerHTML = `<div style="background:var(--brand-purple-4);border-left:3px solid var(--brand-purple);
                                            border-radius:0 6px 6px 0;padding:8px 14px;font-size:13px;
                                            display:flex;justify-content:space-between;align-items:center;">
          <span>Mostrando riesgos del activo: <strong>${UI.esc(asset.name)}</strong></span>
          <button class="btn btn-sm" onclick="ViewRisks._clearAssetFilter()">Quitar filtro</button>
        </div>`;
      }
    }

    // Aplicar filtro de amenaza si viene de URL
    if (threatMatch) {
      const threatId = parseInt(threatMatch[1]);
      const threat = ViewRisks._threats.find(t => t.id === threatId);
      if (threat) {
        ViewRisks._threatFilter = { id: threatId, name: threat.name };
        const filterDiv = document.getElementById('r-asset-filter');
        filterDiv.style.display = 'block';
        filterDiv.innerHTML = `<div style="background:var(--brand-orange-4);border-left:3px solid var(--brand-orange);
                                            border-radius:0 6px 6px 0;padding:8px 14px;font-size:13px;
                                            display:flex;justify-content:space-between;align-items:center;">
          <span>Mostrando riesgos de la amenaza: <strong>${UI.esc(threat.code)} — ${UI.esc(threat.name)}</strong></span>
          <button class="btn btn-sm" onclick="ViewRisks._clearAssetFilter()">Quitar filtro</button>
        </div>`;
      }
    }

    // Aplicar filtro de vulnerabilidad si viene de URL
    if (vulnMatch) {
      const vulnId = parseInt(vulnMatch[1]);
      const vuln = ViewRisks._vulns.find(v => v.id === vulnId);
      if (vuln) {
        ViewRisks._vulnFilter = { id: vulnId, name: vuln.name };
        const filterDiv = document.getElementById('r-asset-filter');
        filterDiv.style.display = 'block';
        filterDiv.innerHTML = `<div style="background:var(--brand-orange-4);border-left:3px solid var(--brand-orange);
                                            border-radius:0 6px 6px 0;padding:8px 14px;font-size:13px;
                                            display:flex;justify-content:space-between;align-items:center;">
          <span>Mostrando riesgos con vulnerabilidad: <strong>${UI.esc(vuln.code)} — ${UI.esc(vuln.name)}</strong></span>
          <button class="btn btn-sm" onclick="ViewRisks._clearAssetFilter()">Quitar filtro</button>
        </div>`;
      }
    }

    // Pre-seleccionar filtro de responsable si viene de la URL
    if (ownerParam) {
      const ownerSel = document.getElementById('r-owner');
      if (ownerSel) ownerSel.value = ownerParam;
    }

    // Pre-marcar checkbox de vencidos si viene de la URL
    if (overdueParam) {
      const cb = document.getElementById('r-overdue');
      if (cb) cb.checked = true;
    }

    // Pre-marcar filtro de solo-proveedor si viene de la URL o del dashboard
    if (supplierOnlyParam) {
      const cb = document.getElementById('r-supplier-only');
      if (cb) cb.checked = true;
    }

    await ViewRisks._reload();

    // Atajo desde heatmap: ?id=X
    const m = location.hash.match(/[?&]id=(\d+)/);
    if (m) ViewRisks._edit(parseInt(m[1]));
  },

  _clearAssetFilter() {
    ViewRisks._assetFilter = null;
    ViewRisks._threatFilter = null;
    ViewRisks._vulnFilter = null;
    ViewRisks._groupFilter = null;
    const fb = document.getElementById('r-asset-filter');
    if (fb) fb.style.display = 'none';
    location.hash = '#/risks';
    ViewRisks._reload();
  },

  // ---------- Vista Por Grupo ----------

  async _renderGroupView() {
    const view = document.getElementById('r-group-view');
    view.innerHTML = `<div class="notice">${t('common.loading')}</div>`;
    try {
      // Leer si hay filtro de solo-proveedor activo en la tab de lista
      const supplierOnlyActive = document.getElementById('r-supplier-only')?.checked;
      const summary = await Api.risks.groupSummary();
      if (!summary.length) {
        view.innerHTML = UI.emptyState(t('common.no_results'), 'Crea y valida grupos desde la seccion Activos → Agrupacion.');
        return;
      }
      const levelColor = l => window.RiskLevels ? RiskLevels.colorFor(l) : (l >= 7 ? 'var(--risk-critical)' : l >= 5 ? 'var(--risk-high)' : l >= 3 ? 'var(--risk-medium)' : 'var(--risk-low)');
      const statusBadge = s => ({
        proposed: `<span style="font-size:10px;background:var(--brand-orange);color:#fff;padding:1px 6px;border-radius:8px;">${t('risks.ai_proposed')}</span>`,
        validated: `<span style="font-size:10px;background:var(--risk-low);color:#fff;padding:1px 6px;border-radius:8px;">${t('risks.ai_validated')}</span>`,
        none: '',
      }[s] || '');

      view.innerHTML = `
        <div style="display:flex;align-items:center;gap:16px;margin-bottom:12px;flex-wrap:wrap;">
          <span style="font-size:13px;color:var(--text-muted);">
            Riesgos por grupo de activos. Los riesgos individuales <strong>no se pierden</strong> al reagrupar.
          </span>
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;white-space:nowrap;margin-left:auto;">
            <input type="checkbox" id="rg-supplier-only" ${supplierOnlyActive ? 'checked' : ''}> ${t('risks.supplier_only')}
          </label>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px;">
          ${summary.map(g => {
            const gid = g.group_id ?? -1;
            const hasRisks = g.risk_count > 0;
            return `
            <div style="border:1px solid var(--border);border-radius:8px;padding:14px 16px;
                        background:var(--bg-2);display:flex;flex-direction:column;gap:8px;">
              <div style="display:flex;align-items:flex-start;gap:8px;">
                <div style="flex:1;">
                  <div style="font-weight:700;font-size:14px;">${UI.esc(g.group_name)}</div>
                  <div style="font-size:12px;color:var(--text-muted);margin-top:2px;">
                    ${statusBadge(g.group_status)}
                    ${g.member_count} activos
                  </div>
                </div>
                ${g.max_residual > 0 ? `
                <div style="text-align:right;min-width:50px;">
                  <div style="font-size:22px;font-weight:800;color:${levelColor(g.max_residual)};
                               font-family:var(--font-mono);">${g.max_residual}</div>
                  <div style="font-size:10px;color:var(--text-subtle);">max nivel</div>
                </div>` : ''}
              </div>
              <div style="display:flex;gap:12px;font-size:12px;color:var(--text-muted);">
                <span><strong style="color:var(--text-primary);">${g.risk_count}</strong> riesgos</span>
                ${g.critical_count ? `<span style="color:var(--risk-critical);font-weight:700;">${g.critical_count} criticos</span>` : ''}
                ${g.high_count ? `<span style="color:var(--risk-high);font-weight:600;">${g.high_count} altos</span>` : ''}
              </div>
              <button class="btn ${hasRisks ? 'btn-primary' : 'btn-ghost'}"
                      ${!hasRisks ? 'disabled' : ''}
                      onclick="ViewRisks._showGroupRisks(${gid}, '${UI.esc(g.group_name)}')"
                      style="font-size:12px;padding:5px 14px;align-self:flex-start;">
                ${hasRisks ? 'Ver riesgos' : 'Sin riesgos'}
              </button>
            </div>`;
          }).join('')}
        </div>
      `;
      // Sincronizar checkbox grupo → lista principal
      const rgChk = document.getElementById('rg-supplier-only');
      if (rgChk) {
        rgChk.onchange = () => {
          const mainChk = document.getElementById('r-supplier-only');
          if (mainChk) { mainChk.checked = rgChk.checked; }
          ViewRisks._renderGroupView();
        };
      }
    } catch (e) {
      view.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _showGroupRisks(groupId, groupName) {
    // Activa el tab "Todos" con filtro de grupo
    const listTabBtn = document.querySelector('.risk-tab-btn[data-risk-tab="list"]');
    if (listTabBtn) listTabBtn.click();
    ViewRisks._groupFilter = { id: groupId, name: groupName };
    // Mostrar banner de filtro de grupo
    const filterDiv = document.getElementById('r-asset-filter');
    if (filterDiv) {
      filterDiv.style.display = 'block';
      filterDiv.innerHTML = `<div style="background:rgba(89,0,141,0.08);border-left:3px solid var(--brand-purple);
                                          border-radius:0 6px 6px 0;padding:8px 14px;font-size:13px;
                                          display:flex;justify-content:space-between;align-items:center;">
        <span>Riesgos del grupo: <strong>${UI.esc(groupName)}</strong></span>
        <button class="btn btn-sm" onclick="ViewRisks._clearAssetFilter()">Quitar filtro</button>
      </div>`;
    }
    ViewRisks._page = 0;
    ViewRisks._reload();
  },

  _users: [], _threatFilter: null, _vulnFilter: null,
  _selected: new Set(),

  async _loadCatalogs() {
    try {
      const [a, t, v, i, u, meth] = await Promise.all([
        Api.assets.list({ limit: 10000 }), Api.threats.list({}),
        Api.vulns.list({}), Api.impls.list(),
        Api.listUsers().catch(() => []),
        Api.get('/api/risks/methodology').catch(() => ({ methodology: 'iso27005' })),
      ]);
      ViewRisks._assets = a;
      ViewRisks._threats = t;
      ViewRisks._vulns = v;
      ViewRisks._impls = i;
      ViewRisks._users = u;
      // Guardar metodologia activa en window para que el formulario la use
      window._riskMethodology = meth.methodology || 'iso27005';
      window._mageritFreqLabels = meth.magerit_freq_labels || {};
      window._mageritDimensions = meth.magerit_dimensions || {};
      // Populate owner filter dropdown
      const ownerSel = document.getElementById('r-owner');
      if (ownerSel && u.length) {
        u.forEach(user => {
          const opt = document.createElement('option');
          opt.value = user.id;
          opt.textContent = user.full_name || user.email;
          ownerSel.appendChild(opt);
        });
        // Add "unassigned" option
        const unassigned = document.createElement('option');
        unassigned.value = '__unassigned__';
        unassigned.textContent = t('common.not_assigned');
        ownerSel.appendChild(unassigned);
      }
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  async _reload() {
    const search = document.getElementById('r-search').value.toLowerCase();
    const status = document.getElementById('r-status').value;
    const band = document.getElementById('r-band').value;
    const treatFilter = document.getElementById('r-treatment')?.value || '';
    const list = document.getElementById('r-list');
    list.innerHTML = `<div class="notice">${t('common.loading')}</div>`;
    try {
      const overdue = document.getElementById('r-overdue')?.checked;
      const supplierOnly = document.getElementById('r-supplier-only')?.checked;
      const ownerVal = document.getElementById('r-owner')?.value || '';
      const params = {};
      if (status) params.status = status;
      if (band) params.min_level = band;
      if (ViewRisks._assetFilter) params.asset_id = ViewRisks._assetFilter.id;
      if (ViewRisks._threatFilter) params.threat_id = ViewRisks._threatFilter.id;
      if (ViewRisks._vulnFilter) params.vulnerability_id = ViewRisks._vulnFilter.id;
      if (ViewRisks._groupFilter) params.group_id = ViewRisks._groupFilter.id;
      if (overdue) params.overdue = true;
      if (supplierOnly) params.supplier_only = true;
      if (ownerVal && ownerVal !== '__unassigned__') params.owner_id = ownerVal;
      if (treatFilter && treatFilter !== '__none__') params.treatment = treatFilter;
      let data = await Api.risks.list(params);
      if (ownerVal === '__unassigned__') data = data.filter(r => !r.owner_id);
      if (treatFilter === '__none__') data = data.filter(r => !r.treatment_option);
      if (search) {
        data = data.filter(r =>
          (r.asset && r.asset.name.toLowerCase().includes(search)) ||
          (r.threat && r.threat.name.toLowerCase().includes(search)) ||
          r.code.toLowerCase().includes(search));
      }
      if (!data.length) {
        list.innerHTML = UI.emptyState(
          t('common.no_results'),
          t('risks.new'));
        return;
      }
      // Sort data client-side
      const sortKey = ViewRisks._sortCol;
      const sortAsc = ViewRisks._sortAsc;
      const sortVal = r => {
        if (sortKey === 'code') return r.code || '';
        if (sortKey === 'asset') return (r.asset?.name || '').toLowerCase();
        if (sortKey === 'threat') return (r.threat?.name || '').toLowerCase();
        if (sortKey === 'inherent_level') return r.inherent_level;
        if (sortKey === 'residual_level') return r.residual_level;
        if (sortKey === 'reduction') return r.inherent_level > 0
          ? Math.round((1 - r.residual_level / r.inherent_level) * 100) : 0;
        if (sortKey === 'status') return r.status || '';
        if (sortKey === 'treatment') return r.treatment_option || '';
        if (sortKey === 'owner') {
          const u = ViewRisks._users.find(u => u.id === r.owner_id);
          return u ? (u.full_name || u.email).toLowerCase() : 'zzz';
        }
        return 0;
      };
      data.sort((a, b) => {
        const va = sortVal(a), vb = sortVal(b);
        const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
        return sortAsc ? cmp : -cmp;
      });

      // Paginación
      ViewRisks._allData = data;
      const total = data.length;
      const ps = ViewRisks._pageSize;
      if (ViewRisks._page * ps >= total && ViewRisks._page > 0) ViewRisks._page = Math.max(0, Math.ceil(total / ps) - 1);
      const pageData = data.slice(ViewRisks._page * ps, (ViewRisks._page + 1) * ps);
      const totalPages = Math.ceil(total / ps);

      const _th = (col, label, title) => {
        const active = ViewRisks._sortCol === col;
        const arrow = active ? (ViewRisks._sortAsc ? ' ▲' : ' ▼') : '';
        return `<th style="cursor:pointer;user-select:none;white-space:nowrap;${active?'color:var(--brand-purple);':''}"
                    data-sort="${col}" title="${title||label}">${label}${arrow}</th>`;
      };

      ViewRisks._selected.clear();
      const now = new Date();
      const canEdit = Auth.canEdit();

      const pagerHtml = total > ps ? `
        <div style="display:flex;align-items:center;gap:10px;padding:10px 0;font-size:13px;">
          <button class="btn btn-sm" id="r-prev" ${ViewRisks._page === 0 ? 'disabled' : ''}>← ${t('common.previous')}</button>
          <span style="color:var(--text-muted);">
            ${ViewRisks._page * ps + 1}–${Math.min((ViewRisks._page + 1) * ps, total)} ${t('common.of')} <strong>${total}</strong> ${t('common.risk')}
          </span>
          <button class="btn btn-sm" id="r-next" ${ViewRisks._page >= totalPages - 1 ? 'disabled' : ''}}>${t('common.next')} →</button>
          <span style="font-size:12px;color:var(--text-muted);">${ViewRisks._page + 1} / ${totalPages}</span>
        </div>` : `<div style="padding:6px 0;font-size:12px;color:var(--text-muted);">${total} riesgo${total !== 1 ? 's' : ''}</div>`;

      list.innerHTML = pagerHtml + `<div class="table-wrap"><table class="data" id="r-table">
        <thead>
          <tr>
            ${canEdit ? '<th style="width:28px;"><input type="checkbox" id="r-chk-all" title="Seleccionar todos"></th>' : ''}
            ${_th('code',t('risks.risk_code'))}${_th('asset',t('common.asset'))}${_th('threat',t('common.threat'))}
            ${_th('inherent_level',t('risks.inherent_risk'),t('risks.inherent_risk'))}${_th('residual_level',t('risks.residual_risk'),t('risks.residual_risk'))}${_th('reduction','Red.','Reduccion inherente → residual')}
            ${_th('status',t('common.status'))}${_th('treatment',t('risks.treatment'))}${_th('owner',t('common.owner'),'width:110px;')}<th style="font-size:10px;white-space:nowrap;">BCP</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${pageData.map(r => {
            const red = r.inherent_level > 0
              ? Math.round((1 - r.residual_level / r.inherent_level) * 100) : 0;
            const redColor = red > 0 ? 'var(--risk-low)' : red < 0 ? 'var(--risk-high)' : 'var(--text-muted)';
            const isOverdue = r.treatment_due_date
              && new Date(r.treatment_due_date) < now
              && r.status !== 'treated' && r.status !== 'accepted' && r.status !== 'closed';
            return `<tr data-id="${r.id}" style="cursor:pointer;${isOverdue?'background:rgba(254,226,226,0.4);':''}">
              ${canEdit ? `<td onclick="event.stopPropagation()"><input type="checkbox" class="r-chk" data-id="${r.id}"></td>` : ''}
              <td>
                ${UI.codePill(r.code)}
                ${r.ai_generated ? `<span style="font-size:9px;font-weight:700;background:var(--brand-purple-4);color:var(--brand-purple);border-radius:3px;padding:1px 4px;margin-left:3px;vertical-align:middle;" title="${UI.esc(r.ai_rationale||'Generado por el agente IA')}">IA</span>` : ''}
                ${r.supplier_id ? `<span style="font-size:9px;font-weight:700;background:#FFF3E0;color:#E65100;border-radius:3px;padding:1px 5px;margin-left:3px;vertical-align:middle;" title="Riesgo de proveedor TPRM${r.supplier_name ? ': ' + r.supplier_name : ''}">TPRM</span>` : ''}
              </td>
              <td><strong>${UI.esc(r.asset?.name||'-')}</strong></td>
              <td>${UI.esc(r.threat?.name||'-')}</td>
              <td>${UI.riskPill(r.inherent_level)}</td>
              <td>${UI.riskPill(r.residual_level)}</td>
              <td style="font-size:12px;font-weight:700;color:${redColor};white-space:nowrap;">${red > 0 ? '-' : red < 0 ? '+' : ''}${Math.abs(red)}%</td>
              <td>${UI.statusLabel(r.status)}${isOverdue ? ' <span title="Fecha de tratamiento vencida" style="font-size:10px;font-weight:700;color:var(--risk-high);background:#FEE2E2;border-radius:3px;padding:1px 4px;margin-left:4px;">VENCIDO</span>' : ''}</td>
              <td>${UI.treatmentLabel(r.treatment_option)}</td>
              <td style="font-size:12px;color:var(--text-muted);max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${
                (() => { const u = ViewRisks._users.find(u => u.id === r.owner_id);
                         return u ? UI.esc((u.full_name || u.email).split(' ')[0]) : '-'; })()
              }</td>
              <td>${r.bcp_coverage
                ? `<span style="font-size:10px;background:var(--success-soft,#dcfce7);color:var(--risk-low,#16a34a);
                   border-radius:999px;padding:2px 7px;font-weight:600;white-space:nowrap;"
                   title="Plan: ${UI.esc(r.bcp_coverage.plan_code || '')} &middot; RTO: ${r.bcp_coverage.rto_hours != null ? r.bcp_coverage.rto_hours + 'h' : '?'}">
                   <i class="ti ti-shield-check" style="font-size:10px"></i> BCP ${r.bcp_coverage.coverage_pct || 0}%</span>`
                : '<span style="font-size:10px;color:var(--text-subtle)">—</span>'}</td>
              <td><button class="btn btn-ghost" data-edit="${r.id}" onclick="event.stopPropagation()">${t('common.view')}</button></td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>
      <div id="r-bulk-bar" class="bulk-bar" style="display:none;">
        <span id="r-bulk-count" style="font-weight:600;"></span>
        <select id="r-bulk-status" style="font-size:13px;">
          <option value="">${t('common.all')}</option>
          <option value="identified">${t('risks.status.identified')}</option>
          <option value="assessed">${t('risks.status.assessed')}</option>
          <option value="treated">${t('risks.status.treated')}</option>
          <option value="accepted">${t('risks.status.accepted')}</option>
          <option value="closed">${t('risks.status.closed')}</option>
        </select>
        <select id="r-bulk-treat" style="font-size:13px;">
          <option value="">${t('common.all')}</option>
          <option value="modification">${t('risks.treatment_decision.reduce')}</option>
          <option value="retention">${t('risks.treatment_decision.accept')}</option>
          <option value="avoidance">${t('risks.treatment_decision.avoid')}</option>
          <option value="sharing">${t('risks.treatment_decision.transfer')}</option>
        </select>
        <select id="r-bulk-owner" style="font-size:13px;">
          <option value="">${t('common.assign')}</option>
          <option value="__none__">${t('common.not_assigned')}</option>
          ${ViewRisks._users.map(u => `<option value="${u.id}">${UI.esc(u.full_name || u.email)}</option>`).join('')}
        </select>
        <button class="btn btn-primary" id="r-bulk-apply">${t('common.apply')}</button>
        <button class="btn btn-ghost" id="r-bulk-clear">${t('common.clear')}</button>
      </div>`;

      // Paginación
      const prevBtn = document.getElementById('r-prev');
      const nextBtn = document.getElementById('r-next');
      if (prevBtn) prevBtn.onclick = () => { ViewRisks._page--; ViewRisks._reload(); };
      if (nextBtn) nextBtn.onclick = () => { ViewRisks._page++; ViewRisks._reload(); };

      // Sort header click handlers
      list.querySelectorAll('th[data-sort]').forEach(th => {
        th.onclick = () => {
          const col = th.dataset.sort;
          if (ViewRisks._sortCol === col) {
            ViewRisks._sortAsc = !ViewRisks._sortAsc;
          } else {
            ViewRisks._sortCol = col;
            ViewRisks._sortAsc = col === 'code' || col === 'asset' || col === 'threat';
          }
          ViewRisks._page = 0;
          ViewRisks._reload();
        };
      });

      // Checkbox logic
      if (canEdit) {
        const chkAll = document.getElementById('r-chk-all');
        chkAll.onchange = () => {
          document.querySelectorAll('.r-chk').forEach(c => {
            c.checked = chkAll.checked;
            const id = parseInt(c.dataset.id);
            if (chkAll.checked) ViewRisks._selected.add(id);
            else ViewRisks._selected.delete(id);
          });
          ViewRisks._updateBulkBar();
        };
        document.querySelectorAll('.r-chk').forEach(c => {
          c.onchange = () => {
            const id = parseInt(c.dataset.id);
            if (c.checked) ViewRisks._selected.add(id);
            else ViewRisks._selected.delete(id);
            ViewRisks._updateBulkBar();
          };
        });
        document.getElementById('r-bulk-clear').onclick = () => {
          ViewRisks._selected.clear();
          document.querySelectorAll('.r-chk').forEach(c => c.checked = false);
          if (chkAll) chkAll.checked = false;
          ViewRisks._updateBulkBar();
        };
        document.getElementById('r-bulk-apply').onclick = () => ViewRisks._bulkApply();
      }

      list.querySelectorAll('[data-edit]').forEach(b =>
        b.onclick = (e) => { e.stopPropagation(); ViewRisks._edit(parseInt(b.dataset.edit)); });
      list.querySelectorAll('tr[data-id]').forEach(tr =>
        tr.onclick = () => ViewRisks._edit(parseInt(tr.dataset.id)));
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _updateBulkBar() {
    const bar = document.getElementById('r-bulk-bar');
    const count = document.getElementById('r-bulk-count');
    if (!bar) return;
    const n = ViewRisks._selected.size;
    if (n === 0) {
      bar.style.display = 'none';
    } else {
      bar.style.display = 'flex';
      count.textContent = `${n} ${t('common.risk')}${n > 1 ? 's' : ''} ${t('common.select')}`;
    }
  },

  async _bulkApply() {
    const ids = [...ViewRisks._selected];
    if (!ids.length) return;
    const newStatus = document.getElementById('r-bulk-status').value;
    const newTreat = document.getElementById('r-bulk-treat').value;
    const newOwner = document.getElementById('r-bulk-owner')?.value || '';
    if (!newStatus && !newTreat && !newOwner) {
      UI.toast(t('common.select') + ' ' + t('common.required'), 'error');
      return;
    }
    const body = {};
    if (newStatus) body.status = newStatus;
    if (newTreat) body.treatment_option = newTreat;
    if (newOwner === '__none__') body.owner_id = null;
    else if (newOwner) body.owner_id = parseInt(newOwner);
    const btn = document.getElementById('r-bulk-apply');
    btn.disabled = true; btn.textContent = 'Aplicando...';
    try {
      await Promise.all(ids.map(id => Api.risks.update(id, body)));
      UI.toast(`${ids.length} riesgo${ids.length > 1 ? 's' : ''} actualizados`, 'success');
      ViewRisks._selected.clear();
      ViewRisks._reload();
    } catch (e) {
      UI.toast('Error al actualizar: ' + e.message, 'error');
      btn.disabled = false; btn.textContent = 'Aplicar';
    }
  },

  async _edit(id, cloneData) {
    let r = {
      asset_id: ViewRisks._assets[0]?.id, threat_id: ViewRisks._threats[0]?.id,
      description: '', consequence_description: '',
      inherent_likelihood: 2, inherent_consequence: 2,
      residual_likelihood: 2, residual_consequence: 2,
      vulnerability_ids: [], control_implementation_ids: [],
      status: 'assessed', treatment_option: '', treatment_plan: '',
      acceptance_justification: '',
    };
    if (id) {
      try {
        r = await Api.risks.get(id);
        r.vulnerability_ids = (r.vulnerabilities || []).map(v => v.id);
        r.control_implementation_ids = (r.controls || []).map(c => c.id);
      } catch (e) { UI.toast(e.message, 'error'); return; }
    } else if (cloneData) {
      r = { ...cloneData };
    }

    const canEdit = Auth.canEdit();

    const methodology = window._riskMethodology || 'iso27005';
    const isMagerit = methodology === 'magerit' || methodology === 'combined';
    const freqLabels = window._mageritFreqLabels || {0:'Muy Baja',1:'Baja',2:'Media',3:'Alta',4:'Muy Alta'};
    const dims = window._mageritDimensions || {D:'Disponibilidad',I:'Integridad',C:'Confidencialidad',A:'Autenticidad',T:'Trazabilidad'};

    // Filtrar vulnerabilidades por amenaza seleccionada usando related_threats del catalogo
    const selectedThreat = ViewRisks._threats.find(t => t.id === r.threat_id);
    const threatCode = selectedThreat?.code;
    const relatedVulns = threatCode
      ? ViewRisks._vulns.filter(v => (v.related_threats || []).includes(threatCode))
      : ViewRisks._vulns;
    const savedVulnIds = r.vulnerability_ids || [];
    // Para riesgo nuevo: auto-seleccionar las vulnerabilidades relacionadas con la amenaza
    // Para riesgo existente: respetar las seleccionadas, pero advertir sobre las incorrectas
    const isNew = !id && !cloneData;
    const effectiveVulnIds = (isNew && relatedVulns.length) ? relatedVulns.map(v => v.id) : savedVulnIds;
    const relatedVulnIds = new Set(relatedVulns.map(v => v.id));
    // Vulnerabilidades ya guardadas que NO corresponden a la amenaza actual
    const mismatchedVulnIds = new Set(savedVulnIds.filter(vid => !relatedVulnIds.has(vid)));

    // Filtrar controles por categoria de vulnerabilidad + tema de amenaza
    // Prefijos ISO 27002 relevantes por categoria de vulnerabilidad
    const VULN_CAT_CTRL_PREFIXES = {
      network:      ['8.20','8.21','8.22','8.23','8.24','5.14','8.5','5.15','5.16','5.17','8.2','8.3','8.26'],
      software:     ['8.25','8.26','8.27','8.28','8.29','8.30','8.31','8.32','8.7','8.8','8.9','8.19'],
      hardware:     ['8.1','8.12','7.8','7.9','7.12','7.13','8.13'],
      personnel:    ['6.1','6.2','6.3','6.4','6.5','6.6','5.9','5.10','5.18'],
      site:         ['7.1','7.2','7.3','7.4','7.5','7.6','7.7','7.10','7.11','7.12'],
      organization: ['5.1','5.2','5.3','5.4','5.5','5.6','5.7','5.31','5.32','5.33','5.34'],
    };
    const THREAT_CAT_THEMES = {
      'Physical damage':              ['physical'],
      'Natural events':               ['physical'],
      'Loss of essential services':   ['physical','technological'],
      'Disturbance due to radiation': ['physical'],
      'Compromise of information':    ['technological','organizational'],
      'Technical failures':           ['technological'],
      'Unauthorized actions':         ['technological','organizational','people'],
      'Compromise of functions':      ['organizational','people'],
    };

    // Obtener prefijos de la union de categorias de vulns relacionadas
    const activeVulnCats = [...new Set((relatedVulns.length ? relatedVulns : ViewRisks._vulns).map(v => v.category).filter(Boolean))];
    const activePrefixes = activeVulnCats.flatMap(cat => VULN_CAT_CTRL_PREFIXES[cat] || []);
    const activeThemes   = THREAT_CAT_THEMES[selectedThreat?.category || ''] || [];

    const suggestedImpls = activePrefixes.length
      ? ViewRisks._impls.filter(c => c.control && activePrefixes.some(p => c.control.code?.startsWith(p)))
      : (activeThemes.length ? ViewRisks._impls.filter(c => c.control && activeThemes.includes(c.control.theme)) : []);
    const savedCtrlIds = r.control_implementation_ids || [];
    // Para nuevo riesgo: pre-seleccionar los sugeridos; para existente: respetar seleccion actual
    const effectiveCtrlIds = (isNew && suggestedImpls.length) ? suggestedImpls.map(c => c.id) : savedCtrlIds;

    UI.modal(id ? `${r.code} - ${r.asset?.name || ''}` : t('risks.new'), `
      <div class="span2 notice">
        Riesgo = Activo × Amenaza.
        ${isMagerit
          ? `<strong>Metodología MAGERIT v3</strong>: consecuencia calculada desde las 5 dimensiones DIACAT del activo × degradación.`
          : `Nivel calculado como Consecuencia × Probabilidad (matriz 5x5 ISO 27005 Annex E.2).`}
      </div>
      <div>
        <label>${t('common.asset')} *</label>
        <select id="f-asset" ${id?'disabled':''} onchange="${isMagerit?'ViewRisks._updateMageritPreview()':''}">
          ${ViewRisks._assets.map(a => `<option value="${a.id}" ${r.asset_id===a.id?'selected':''}>${UI.esc(a.code)} - ${UI.esc(a.name)}</option>`).join('')}
        </select>
      </div>
      <div>
        <label>${t('common.threat')} *</label>
        <select id="f-threat" ${id?'disabled':''}>
          ${ViewRisks._threats.map(t => `<option value="${t.id}" ${r.threat_id===t.id?'selected':''}>${UI.esc(t.code)} - ${UI.esc(t.name)}</option>`).join('')}
        </select>
      </div>
      <div class="span2">
        <label>${t('common.description')}</label>
        <textarea id="f-desc" rows="2">${UI.esc(r.description||'')}</textarea>
      </div>
      <div class="span2">
        <label>${t('risks.treatment_plan')}</label>
        <textarea id="f-cons" rows="2">${UI.esc(r.consequence_description||'')}</textarea>
      </div>

      ${isMagerit ? `
      <!-- Bloque MAGERIT: dimensión + degradación + vista previa -->
      <div class="span2" style="background:var(--brand-purple-4);border:1px solid var(--brand-purple-3);border-radius:10px;padding:14px;margin-bottom:4px;">
        <div style="font-size:12px;font-weight:700;color:var(--brand-purple);text-transform:uppercase;margin-bottom:10px;">
          MAGERIT v3 — Valoración del impacto
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;">
          <div>
            <label style="font-size:12px;">Dimensión afectada *</label>
            <select id="f-magerit-dim" onchange="ViewRisks._updateMageritPreview()">
              ${Object.entries(dims).map(([k,v]) =>
                `<option value="${k}" ${(r.magerit_dimension||'D')===k?'selected':''}>${k} — ${v}</option>`
              ).join('')}
            </select>
          </div>
          <div>
            <label style="font-size:12px;">Degradación del activo (%)</label>
            <input type="range" id="f-degrad" min="0" max="100" step="5"
                   value="${r.degradation_pct ?? 50}"
                   style="width:100%;accent-color:var(--brand-purple);"
                   oninput="document.getElementById('f-degrad-val').textContent=this.value+'%';ViewRisks._updateMageritPreview()">
            <div style="text-align:center;font-size:13px;font-weight:700;color:var(--brand-purple);" id="f-degrad-val">${r.degradation_pct ?? 50}%</div>
          </div>
          <div id="magerit-preview-box" style="background:var(--bg-1);border-radius:8px;padding:10px;text-align:center;">
            <div style="font-size:11px;color:var(--text-muted);">Consecuencia calculada</div>
            <div style="font-size:28px;font-weight:800;color:var(--brand-purple);" id="magerit-cons-val">${r.inherent_consequence ?? 0}</div>
            <div style="font-size:11px;color:var(--text-muted);" id="magerit-cons-lbl">—</div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:4px;">Impacto: <span id="magerit-impact-val">${r.magerit_impact ?? '-'}</span></div>
          </div>
        </div>
        <div id="magerit-dims-bar" style="margin-top:10px;display:grid;grid-template-columns:repeat(5,1fr);gap:4px;"></div>
      </div>
      <input type="hidden" id="f-ic" value="${r.inherent_consequence}">
      <div>
        <label>${methodology === 'magerit' ? 'Frecuencia de la amenaza (0-4)' : 'Probabilidad inherente (0-4)'}</label>
        <select id="f-il">
          ${[0,1,2,3,4].map(i => `<option value="${i}" ${r.inherent_likelihood===i?'selected':''}>${i} — ${freqLabels[i]||i}</option>`).join('')}
        </select>
      </div>
      <div id="magerit-cons-display" style="display:flex;flex-direction:column;justify-content:center;">
        <label style="font-size:12px;color:var(--text-muted);">Consecuencia inherente</label>
        <div style="font-size:18px;font-weight:700;color:var(--brand-purple);" id="magerit-ic-display">${r.inherent_consequence}</div>
        <div style="font-size:11px;color:var(--text-muted);">Auto-calculada desde activo × degradación</div>
      </div>
      ` : `
      <div>
        <label>Probabilidad inherente (0-4)</label>
        <input type="number" min="0" max="4" id="f-il" value="${r.inherent_likelihood}">
      </div>
      <div>
        <label>Consecuencia inherente (0-4)</label>
        <input type="number" min="0" max="4" id="f-ic" value="${r.inherent_consequence}">
      </div>`}
      <div class="span2">
        <label style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;">
          Vulnerabilidades asociadas
          ${relatedVulns.length < ViewRisks._vulns.length
            ? `<span style="font-size:11px;font-weight:400;color:var(--text-muted);">
                ${isNew ? 'Auto-seleccionadas:' : 'Relevantes para amenaza:'} ${relatedVulns.length} de ${ViewRisks._vulns.length}
                <a href="#" id="vuln-show-all-link" style="margin-left:6px;color:var(--brand-purple);">Ver todas</a>
               </span>`
            : ''}
        </label>
        ${!isNew && mismatchedVulnIds.size > 0
          ? `<div style="font-size:11px;color:#B45309;background:#FEF3C7;border-radius:6px;padding:6px 10px;margin-bottom:6px;">
              Aviso: ${mismatchedVulnIds.size} vulnerabilidad(es) vinculada(s) no corresponde(n) a la amenaza ${UI.esc(threatCode||'')}. Revisa la seleccion para mayor precision.
             </div>`
          : ''}
        <select id="f-vulns" multiple size="${Math.max(3, Math.min(relatedVulns.length || ViewRisks._vulns.length, 6))}" style="height:auto;" data-threat="${UI.esc(threatCode||'')}">
          ${(relatedVulns.length ? relatedVulns : ViewRisks._vulns).map(v => `<option value="${v.id}" ${effectiveVulnIds.includes(v.id)?'selected':''}>${UI.esc(v.code)} - ${UI.esc(v.name)}</option>`).join('')}
          ${!isNew && mismatchedVulnIds.size > 0
            ? ViewRisks._vulns.filter(v => mismatchedVulnIds.has(v.id))
                .map(v => `<option value="${v.id}" selected>${UI.esc(v.code)} - ${UI.esc(v.name)} [fuera de amenaza]</option>`).join('')
            : ''}
        </select>
      </div>
      <div class="span2">
        <label style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;">
          Controles implementados que mitigan
          ${suggestedImpls.length < ViewRisks._impls.length
            ? `<span style="font-size:11px;font-weight:400;color:var(--text-muted);">
                ${isNew ? 'Pre-seleccionados:' : 'Relevantes para amenaza+vulns:'} ${suggestedImpls.length} de ${ViewRisks._impls.length}
                <a href="#" id="ctrl-show-all-link" style="margin-left:6px;color:var(--brand-purple);">Ver todos</a>
               </span>`
            : ''}
          ${id ? `<button type="button" id="btn-suggest-controls" class="btn btn-ghost" style="font-size:11px;padding:2px 8px;margin-left:auto;">Sugerir con IA</button>` : ''}
        </label>
        <select id="f-impls" multiple size="${Math.max(3, Math.min(suggestedImpls.length || ViewRisks._impls.length, 7))}" style="height:auto;">
          ${(suggestedImpls.length ? suggestedImpls : ViewRisks._impls).map(c => {
            const code = c.control?.code ? `[${UI.esc(c.control.code)}] ` : '';
            return `<option value="${c.id}" ${effectiveCtrlIds.includes(c.id)?'selected':''}>${code}${UI.esc(c.name)} (madurez ${c.maturity}/5, ${UI.controlStatusLabel(c.status)})</option>`;
          }).join('')}
        </select>
      </div>
      <div>
        <label>${t('common.status')}</label>
        <select id="f-status">
          ${['identified','assessed','treated','accepted','closed'].map(s =>
            `<option value="${s}" ${r.status===s?'selected':''}>${UI.statusLabel(s)}</option>`).join('')}
        </select>
      </div>
      <div>
        <label>${t('risks.treatment')}</label>
        <select id="f-treat">
          <option value="">-</option>
          ${['modification','retention','avoidance','sharing'].map(t =>
            `<option value="${t}" ${r.treatment_option===t?'selected':''}>${UI.treatmentLabel(t)}</option>`).join('')}
        </select>
      </div>
      <div class="span2">
        <label>${t('risks.treatment_plan')}</label>
        <textarea id="f-plan" rows="2">${UI.esc(r.treatment_plan||'')}</textarea>
      </div>
      <div>
        <label>${t('common.owner')}</label>
        <select id="f-owner">
          <option value="">- ${t('common.not_assigned')} -</option>
          ${ViewRisks._users.map(u =>
            `<option value="${u.id}" ${r.owner_id===u.id?'selected':''}>${UI.esc(u.full_name||u.email)}</option>`
          ).join('')}
        </select>
      </div>
      <div>
        <label>${t('risks.treatment_deadline')}</label>
        <input type="date" id="f-due" value="${r.treatment_due_date ? r.treatment_due_date.slice(0,10) : ''}">
      </div>
      <div class="span2" id="f-just-wrap" style="${r.status==='accepted'?'':'opacity:0.6;'}">
        <label>${t('risks.notes')} ${r.status==='accepted'?'<span style="color:var(--risk-high);">*</span>':'(si aplica)'}</label>
        <textarea id="f-just" rows="2">${UI.esc(r.acceptance_justification||'')}</textarea>
      </div>
      ${id ? `
      <div class="span2 notice ${r.residual_level <= 2 ? '' : 'notice-warn'}">
        Nivel inherente actual: <strong>${r.inherent_level}</strong> &nbsp;→&nbsp;
        Nivel residual actual: <strong>${r.residual_level}</strong>
        ${r.inherent_level > 0 ? `&nbsp;<span style="font-size:12px;color:var(--risk-low);">(-${Math.round((1-r.residual_level/r.inherent_level)*100)}% reduccion)</span>` : ''}
        ${r.magerit_dimension ? `<br><span style="font-size:12px;">
          <strong>MAGERIT:</strong> dimensión afectada:
          <span style="background:var(--brand-purple);color:#fff;border-radius:4px;padding:1px 7px;font-size:11px;">${r.magerit_dimension}</span>
          &nbsp;·&nbsp; degradación: <strong>${r.degradation_pct ?? '-'}%</strong>
          ${r.magerit_impact != null ? `&nbsp;·&nbsp; impacto calculado: <strong>${r.magerit_impact}</strong>` : ''}
        </span>` : ''}
        ${r.asset && r.asset.monetary_value ? (() => {
          const ale = Math.round(r.asset.monetary_value * (r.residual_level / 8));
          const aleFmt = ale.toLocaleString('es-ES', { style: 'currency', currency: 'EUR', minimumFractionDigits: 0 });
          return `<br><span style="font-size:12px;">ALE estimado (FAIR): <strong>${aleFmt}</strong> <span style="color:var(--text-muted);">(valor activo × nivel residual/8)</span></span>`;
        })() : ''}
        ${r.accepted_at ? `<br><span style="font-size:12px;">Aceptado el ${new Date(r.accepted_at).toLocaleString('es-ES')}</span>` : ''}
        ${r.treatment_due_date ? `<br><span style="font-size:12px;">Fecha limite: <strong>${new Date(r.treatment_due_date).toLocaleDateString('es-ES')}</strong></span>` : ''}
      </div>
      <!-- Sección trazabilidad / madurez / SOA -->
      <div class="span2">
        <details id="risk-trace-details">
          <summary style="cursor:pointer;font-size:13px;font-weight:600;
                          color:var(--brand-purple);padding:8px 0;
                          list-style:none;display:flex;align-items:center;gap:6px;
                          border-top:2px solid var(--brand-purple-3);margin-top:8px;">
            <span style="font-size:10px;">&#9654;</span>
            Madurez, trazabilidad de fuentes y análisis IA — SOA
          </summary>
          <div id="risk-trace-body" style="margin-top:8px;"></div>
        </details>
      </div>
      <div class="span2">
        <details id="risk-history">
          <summary style="cursor:pointer;font-size:13px;color:var(--text-muted);padding:6px 0;
                          list-style:none;display:flex;align-items:center;gap:6px;">
            <span style="font-size:10px;">&#9654;</span> Historial de cambios
          </summary>
          <div id="risk-history-body" style="margin-top:8px;">
            <div class="notice">Cargando historial...</div>
          </div>
        </details>
      </div>` : ''}
    `, {
      actions: canEdit ? `
        <button class="btn" id="m-cancel">${t('common.close')}</button>
        ${id ? '<button class="btn btn-ghost" id="m-bowtie" title="Ver diagrama Bow-Tie de causas y consecuencias">Bow-Tie</button>' : ''}
        ${id ? `<button class="btn btn-ghost" id="m-clone" title="Crear una copia de este riesgo">${t('common.duplicate')}</button>` : ''}
        ${id ? `<button class="btn btn-danger" id="m-del">${t('common.delete')}</button>` : ''}
        <button class="btn btn-primary" id="m-save">${t('common.save')}</button>
      ` : `<button class="btn" id="m-cancel">${t('common.close')}</button>
        ${id ? '<button class="btn btn-ghost" id="m-bowtie" title="Ver diagrama Bow-Tie">Bow-Tie</button>' : ''}`
    });

    document.getElementById('m-cancel').onclick = UI.closeModal;

    // Bowtie diagram
    if (id) {
      const btBtn = document.getElementById('m-bowtie');
      if (btBtn) btBtn.onclick = () => { UI.closeModal(); ViewRisks._bowtie(r); };
    }

    // Duplicar riesgo (clonar)
    if (id && canEdit) {
      const cloneBtn = document.getElementById('m-clone');
      if (cloneBtn) cloneBtn.onclick = () => {
        const cloneData = {
          asset_id: r.asset?.id || r.asset_id,
          threat_id: r.threat?.id || r.threat_id,
          description: r.description || '',
          consequence_description: r.consequence_description || '',
          inherent_likelihood: r.inherent_likelihood,
          inherent_consequence: r.inherent_consequence,
          vulnerability_ids: r.vulnerability_ids || (r.vulnerabilities||[]).map(v=>v.id),
          control_implementation_ids: r.control_implementation_ids || (r.controls||[]).map(c=>c.id),
          status: 'identified',
          treatment_option: r.treatment_option || '',
          treatment_plan: r.treatment_plan || '',
          acceptance_justification: '',
          owner_id: r.owner_id || null,
        };
        UI.closeModal();
        ViewRisks._edit(null, cloneData);
      };
    }

    // Cargar trazabilidad al expandir el <details>
    if (id) {
      const traceDetails = document.getElementById('risk-trace-details');
      if (traceDetails) {
        traceDetails.addEventListener('toggle', async () => {
          if (!traceDetails.open) return;
          const body = document.getElementById('risk-trace-body');
          if (body && body.children.length === 0) {
            body.innerHTML = '<div class="notice">Cargando trazabilidad...</div>';
            await ViewRisks._loadTrace(id, body);
          }
        }, { once: true });
      }
    }

    // Cargar historial de cambios al expandir el <details>
    if (id) {
      const details = document.getElementById('risk-history');
      if (details) {
        details.addEventListener('toggle', async () => {
          if (!details.open) return;
          const body = document.getElementById('risk-history-body');
          try {
            const entries = await Api.audit.history('risk', id);
            if (!entries.length) {
              body.innerHTML = '<p style="font-size:12px;color:var(--text-subtle);">Sin registros de cambio todavia.</p>';
              return;
            }
            const actionColors = {
              create:'background:#D1FAE5;color:#065F46',
              update:'background:#DBEAFE;color:#1E40AF',
              delete:'background:#FEE2E2;color:#991B1B',
            };
            body.innerHTML = entries.map(e => {
              const ts = new Date(e.timestamp).toLocaleString('es-ES', {
                day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
              const style = actionColors[e.action] || 'background:var(--bg-3);color:var(--text-muted)';
              const detail = e.detail && Object.keys(e.detail).length
                ? Object.entries(e.detail).map(([k,v]) => `${UI.esc(k)}: ${UI.esc(String(v))}`).join(' · ')
                : '';
              return `<div style="display:flex;gap:8px;align-items:flex-start;padding:6px 0;
                                  border-bottom:1px solid var(--border);font-size:12px;">
                <span style="color:var(--text-subtle);white-space:nowrap;min-width:110px;">${ts}</span>
                <span class="badge badge-muted" style="${style};font-size:10px;">${UI.esc(e.action)}</span>
                <span style="color:var(--text-muted);">${UI.esc(e.user_name||e.user_email||'')}</span>
                ${detail ? `<span style="color:var(--text-subtle);">${detail}</span>` : ''}
              </div>`;
            }).join('');
          } catch (_) {
            body.innerHTML = '<p style="font-size:12px;color:var(--text-subtle);">No disponible.</p>';
          }
        }, { once: true });
      }
    }

    // Enlace "Ver todas las vulnerabilidades" — expande el selector al catalogo completo
    const vulnShowAll = document.getElementById('vuln-show-all-link');
    if (vulnShowAll) {
      vulnShowAll.addEventListener('click', (e) => {
        e.preventDefault();
        const sel = document.getElementById('f-vulns');
        if (!sel) return;
        const currentSelected = new Set(Array.from(sel.selectedOptions).map(o => parseInt(o.value)));
        sel.innerHTML = ViewRisks._vulns.map(v =>
          `<option value="${v.id}" ${currentSelected.has(v.id)?'selected':''}>${UI.esc(v.code)} - ${UI.esc(v.name)}</option>`
        ).join('');
        sel.size = Math.min(ViewRisks._vulns.length, 8);
        vulnShowAll.textContent = `(mostrando todas — ${ViewRisks._vulns.length})`;
        vulnShowAll.style.pointerEvents = 'none';
        vulnShowAll.style.color = 'var(--text-muted)';
      });
    }

    if (id && canEdit) document.getElementById('m-del').onclick = async () => {
      if (!await UI.confirm(t('risks.delete_confirm'))) return;
      try { await Api.risks.del(id); UI.closeModal(); UI.toast(t('common.success'),'success'); ViewRisks._reload(); }
      catch (e) { UI.toast(e.message, 'error'); }
    };
    // "Ver todos los controles" — expande al catalogo completo sin filtro
    const ctrlShowAll = document.getElementById('ctrl-show-all-link');
    if (ctrlShowAll) {
      ctrlShowAll.addEventListener('click', (e) => {
        e.preventDefault();
        const sel = document.getElementById('f-impls');
        if (!sel) return;
        const currentSelected = new Set(Array.from(sel.selectedOptions).map(o => parseInt(o.value)));
        sel.innerHTML = ViewRisks._impls.map(c => {
          const code = c.control?.code ? `[${UI.esc(c.control.code)}] ` : '';
          return `<option value="${c.id}" ${currentSelected.has(c.id)?'selected':''}>${code}${UI.esc(c.name)} (madurez ${c.maturity}/5, ${UI.controlStatusLabel(c.status)})</option>`;
        }).join('');
        sel.size = Math.min(ViewRisks._impls.length, 9);
        ctrlShowAll.textContent = `(mostrando todos — ${ViewRisks._impls.length})`;
        ctrlShowAll.style.pointerEvents = 'none';
        ctrlShowAll.style.color = 'var(--text-muted)';
      });
    }

    // "Sugerir con IA" — analisis por cadena de ataque y seleccion de controles
    const btnSuggest = document.getElementById('btn-suggest-controls');
    if (btnSuggest && id) {
      btnSuggest.addEventListener('click', async () => {
        btnSuggest.disabled = true;
        btnSuggest.textContent = 'Analizando cadena de ataque...';
        // Eliminar panel previo si existe
        document.getElementById('suggest-ai-panel')?.remove();
        try {
          const result = await Api.post(`/api/risks/${id}/suggest-controls`, {});
          const sel = document.getElementById('f-impls');
          if (!sel) return;

          const suggestedSet = new Set(result.suggested_ids || []);
          const suggestedControls = ViewRisks._impls.filter(c => suggestedSet.has(c.id));

          if (suggestedControls.length) {
            sel.innerHTML = suggestedControls.map(c => {
              const code = c.control?.code ? `[${UI.esc(c.control.code)}] ` : '';
              return `<option value="${c.id}" selected>${code}${UI.esc(c.name)} (madurez ${c.maturity}/5, ${UI.controlStatusLabel(c.status)})</option>`;
            }).join('');
            sel.size = Math.max(3, Math.min(suggestedControls.length, 8));
            const lbl = sel.closest('.span2')?.querySelector('label span');
            if (lbl) lbl.innerHTML = `IA: ${suggestedControls.length} de ${ViewRisks._impls.length} &nbsp;<a href="#" id="ctrl-show-all-link" style="color:var(--brand-purple);">Ver todos</a>`;
            const newShowAll = document.getElementById('ctrl-show-all-link');
            if (newShowAll) {
              newShowAll.addEventListener('click', (e) => {
                e.preventDefault();
                const cur = new Set(Array.from(sel.selectedOptions).map(o => parseInt(o.value)));
                sel.innerHTML = ViewRisks._impls.map(c => {
                  const code = c.control?.code ? `[${UI.esc(c.control.code)}] ` : '';
                  return `<option value="${c.id}" ${cur.has(c.id)?'selected':''}>${code}${UI.esc(c.name)} (madurez ${c.maturity}/5, ${UI.controlStatusLabel(c.status)})</option>`;
                }).join('');
                sel.size = Math.min(ViewRisks._impls.length, 9);
                newShowAll.remove();
              });
            }
          } else {
            UI.toast('La IA no identifico controles especificos para este riesgo', 'info');
          }

          // Panel de razonamiento IA debajo del boton
          const mappingByStep = {};
          (result.control_to_step_mapping || []).forEach(m => {
            if (!mappingByStep[m.attack_step]) mappingByStep[m.attack_step] = [];
            mappingByStep[m.attack_step].push(m);
          });

          const missingHtml = (result.missing_controls || []).map(mc => {
            const priColor = mc.priority === 'alta' ? 'var(--danger)' : mc.priority === 'media' ? 'var(--warning)' : 'var(--text-muted)';
            return `<div style="display:flex;gap:8px;align-items:flex-start;padding:5px 0;border-bottom:1px solid var(--border-light);">
              <span style="font-size:10px;font-weight:700;color:${priColor};min-width:40px;margin-top:2px;">${UI.esc(mc.priority?.toUpperCase() || '?')}</span>
              <div>
                <span style="font-size:11px;font-weight:600;color:var(--text-main);">[${UI.esc(mc.iso27002_code||'')}] ${UI.esc(mc.name||'')}</span>
                <div style="font-size:10px;color:var(--text-muted);">Cubre: ${UI.esc(mc.attack_step||'')}</div>
              </div>
            </div>`;
          }).join('');

          const stepsHtml = Object.entries(mappingByStep).map(([step, ctrls]) => {
            const ctrlsHtml = ctrls.map(m => {
              const typeColor = m.control_type === 'P' ? 'var(--success)' : m.control_type === 'D' ? 'var(--brand-orange)' : 'var(--brand-purple)';
              const typeLabel = m.control_type === 'P' ? 'PREV' : m.control_type === 'D' ? 'DET' : 'CORR';
              const ctrl = ViewRisks._impls.find(c => c.id === m.control_id);
              const ctrlName = ctrl ? (ctrl.control?.code ? `[${ctrl.control.code}] ${ctrl.name}` : ctrl.name) : `ID:${m.control_id}`;
              return `<div style="margin:3px 0 3px 8px;font-size:11px;">
                <span style="display:inline-block;min-width:32px;font-size:9px;font-weight:700;color:${typeColor};border:1px solid ${typeColor};border-radius:3px;padding:0 3px;text-align:center;">${typeLabel}</span>
                <span style="color:var(--text-main);margin-left:4px;">${UI.esc(ctrlName)}</span>
                <div style="font-size:10px;color:var(--text-muted);margin-left:36px;">${UI.esc(m.why||'')}</div>
              </div>`;
            }).join('');
            return `<div style="margin-bottom:8px;">
              <div style="font-size:11px;font-weight:700;color:var(--brand-purple);padding:2px 0;">${UI.esc(step)}</div>
              ${ctrlsHtml}
            </div>`;
          }).join('');

          const panel = document.createElement('div');
          panel.id = 'suggest-ai-panel';
          panel.style.cssText = 'margin-top:10px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:12px;font-size:12px;';
          panel.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
              <span style="font-weight:700;color:var(--brand-purple);font-size:12px;">Razonamiento del agente IA</span>
              <button onclick="document.getElementById('suggest-ai-panel').remove()" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:14px;padding:0;">&times;</button>
            </div>
            ${result.attack_chain_summary ? `<div style="background:var(--bg-alt);border-radius:6px;padding:8px;margin-bottom:10px;font-size:11px;color:var(--text-main);line-height:1.5;">${UI.esc(result.attack_chain_summary)}</div>` : ''}
            ${stepsHtml ? `<div style="margin-bottom:10px;">
              <div style="font-size:11px;font-weight:600;color:var(--text-main);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px;">Cobertura por paso de ataque</div>
              ${stepsHtml}
            </div>` : ''}
            ${result.rationale ? `<div style="font-size:11px;color:var(--text-muted);border-top:1px solid var(--border-light);padding-top:8px;">${UI.esc(result.rationale)}</div>` : ''}
            ${missingHtml ? `<div style="margin-top:10px;border-top:1px solid var(--border-light);padding-top:8px;">
              <div style="font-size:11px;font-weight:600;color:var(--danger);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px;">Controles ausentes detectados</div>
              ${missingHtml}
            </div>` : ''}
          `;
          btnSuggest.insertAdjacentElement('afterend', panel);

          if (suggestedControls.length) UI.toast(`${suggestedControls.length} controles asignados por IA. Puedes ajustar antes de guardar.`, 'success');
        } catch (e) {
          UI.toast('Error en sugerencia IA: ' + e.message, 'error');
        } finally {
          btnSuggest.disabled = false;
          btnSuggest.textContent = 'Sugerir con IA';
        }
      });
    }

    // Para riesgo nuevo: actualizar lista de vulnerabilidades al cambiar la amenaza
    if (!id) {
      const threatSel = document.getElementById('f-threat');
      const vulnSel = document.getElementById('f-vulns');
      if (threatSel && vulnSel) {
        threatSel.addEventListener('change', () => {
          const tCode = ViewRisks._threats.find(t => t.id === parseInt(threatSel.value))?.code;
          const filtered = tCode
            ? ViewRisks._vulns.filter(v => (v.related_threats || []).includes(tCode))
            : ViewRisks._vulns;
          vulnSel.innerHTML = (filtered.length ? filtered : ViewRisks._vulns).map(v =>
            `<option value="${v.id}" selected>${UI.esc(v.code)} - ${UI.esc(v.name)}</option>`
          ).join('');
          vulnSel.size = Math.max(3, Math.min(filtered.length, 6));
          // Actualizar badge de info
          const showAllLink = document.getElementById('vuln-show-all-link');
          if (showAllLink) {
            const total = ViewRisks._vulns.length;
            showAllLink.textContent = filtered.length < total ? `Ver todas (${total})` : '';
            showAllLink.style.pointerEvents = filtered.length < total ? '' : 'none';
          }
        });
      }
    }

    // Resaltar campo justificacion cuando se selecciona "accepted"
    const statusSel = document.getElementById('f-status');
    if (statusSel) statusSel.addEventListener('change', () => {
      const wrap = document.getElementById('f-just-wrap');
      const lbl = wrap?.querySelector('label');
      if (statusSel.value === 'accepted') {
        if (wrap) wrap.style.opacity = '1';
        if (lbl) lbl.innerHTML = UI.esc(t('risks.justification_required')) + ' <span style="color:var(--risk-high);">*</span>';
      } else {
        if (wrap) wrap.style.opacity = '0.6';
        if (lbl) lbl.textContent = t('risks.justification_optional');
      }
    });

    if (canEdit) document.getElementById('m-save').onclick = async () => {
      const getMulti = el => Array.from(el.selectedOptions).map(o => parseInt(o.value));
      const status = document.getElementById('f-status').value;
      const just = document.getElementById('f-just').value.trim();
      // Validar justificacion obligatoria al aceptar
      if (status === 'accepted' && !just) {
        UI.toast('La justificacion de aceptacion es obligatoria al aceptar un riesgo', 'error');
        document.getElementById('f-just').focus();
        return;
      }
      const dueVal = document.getElementById('f-due').value;
      const ownerVal = document.getElementById('f-owner').value;
      // MAGERIT: leer dimension y degradacion si aplica
      const mageritDim = document.getElementById('f-magerit-dim')?.value || null;
      const degradPct = document.getElementById('f-degrad') ? parseInt(document.getElementById('f-degrad').value) : null;
      const body = {
        description: document.getElementById('f-desc').value,
        consequence_description: document.getElementById('f-cons').value,
        inherent_likelihood: parseInt(document.getElementById('f-il').value)||0,
        inherent_consequence: parseInt(document.getElementById('f-ic').value)||0,
        vulnerability_ids: getMulti(document.getElementById('f-vulns')),
        control_implementation_ids: getMulti(document.getElementById('f-impls')),
        status,
        treatment_option: document.getElementById('f-treat').value || null,
        treatment_plan: document.getElementById('f-plan').value,
        owner_id: ownerVal ? parseInt(ownerVal) : null,
        treatment_due_date: dueVal || null,
        acceptance_justification: just || null,
        magerit_dimension: mageritDim,
        degradation_pct: degradPct,
      };
      try {
        if (id) await Api.risks.update(id, body);
        else {
          body.asset_id = parseInt(document.getElementById('f-asset').value);
          body.threat_id = parseInt(document.getElementById('f-threat').value);
          await Api.risks.create(body);
        }
        UI.closeModal(); UI.toast(t('common.success'),'success'); ViewRisks._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  _bowtie(r) {
    const threatName   = r.threat?.name || 'Amenaza';
    const assetName    = r.asset?.name  || 'Activo';
    const vulns        = r.vulnerabilities || [];
    const controls     = r.controls || [];
    const consequence  = r.consequence_description || r.description || 'Consecuencia potencial';
    const riskCode     = r.code || '';

    // Layout constants
    const W = 860, H = 360;
    const CX = W / 2, CY = H / 2;
    const R  = 44;           // radio del circulo central
    const COL_L = 140;       // x del bloque izquierdo
    const COL_R = W - 140;   // x del bloque derecho

    // Causas (left): amenaza + vulnerabilidades
    const leftItems = [threatName, ...vulns.map(v => v.name || v.code)];
    // Efectos (right): consecuencias + controles
    const rightItems = controls.length
      ? controls.map(c => c.name || c.code)
      : [consequence.length > 60 ? consequence.slice(0,57)+'...' : consequence];

    function _color(i, side) {
      const palette = side === 'L'
        ? ['#EF4444','#F97316','#F59E0B','#EAB308','#84CC16']
        : ['#22C55E','#10B981','#0EA5E9','#3B82F6','#6366F1'];
      return palette[i % palette.length];
    }

    function _truncate(s, n) { return s.length > n ? s.slice(0,n-1)+'…' : s; }

    function _nodeGroup(items, side) {
      const total = items.length;
      const spacing = Math.min(64, (H - 60) / Math.max(total, 1));
      const startY  = CY - ((total - 1) * spacing) / 2;
      return items.map((label, i) => {
        const ny   = startY + i * spacing;
        const nx   = side === 'L' ? COL_L : COL_R;
        const color = _color(i, side);
        // Arrow line: node edge → risk circle tangent
        const lineX1 = side === 'L' ? nx + 68 : nx - 68;
        const lineX2 = side === 'L' ? CX - R - 4 : CX + R + 4;
        const arrowD = side === 'L'
          ? `M${lineX2},${CY} l-8,-5 l0,10 z`
          : `M${lineX2},${CY} l8,-5 l0,10 z`;
        return `
          <line x1="${lineX1}" y1="${ny}" x2="${lineX2}" y2="${CY}"
                stroke="${color}" stroke-width="1.5" stroke-dasharray="${side==='R'?'4 3':''}" opacity=".7"/>
          <polygon points="${arrowD.match(/[\d.,\s]+/g)?.join('')||''}"
                   fill="${color}" opacity=".7"/>
          <rect x="${nx - 68}" y="${ny - 16}" width="136" height="32" rx="6"
                fill="${color}22" stroke="${color}" stroke-width="1.5"/>
          <text x="${nx}" y="${ny + 5}" text-anchor="middle"
                font-size="11" font-family="Inter,system-ui,sans-serif"
                fill="${color}" font-weight="600">${_truncate(label, 20)}</text>`;
      }).join('');
    }

    const levelColor = r.residual_level >= 7 ? '#EF4444'
                     : r.residual_level >= 5 ? '#F97316'
                     : r.residual_level >= 3 ? '#F59E0B'
                     : '#22C55E';

    const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}"
         style="width:100%;max-height:380px;display:block;">
      <!-- background -->
      <rect width="${W}" height="${H}" fill="var(--bg-1)" rx="10"/>

      <!-- left label -->
      <text x="${COL_L}" y="22" text-anchor="middle" font-size="11"
            font-family="Inter,system-ui,sans-serif" fill="var(--text-muted)" font-weight="600"
            text-transform="uppercase">CAUSAS (amenaza + vulnerabilidades)</text>

      <!-- right label -->
      <text x="${COL_R}" y="22" text-anchor="middle" font-size="11"
            font-family="Inter,system-ui,sans-serif" fill="var(--text-muted)" font-weight="600">CONSECUENCIAS y CONTROLES</text>

      <!-- node groups -->
      ${_nodeGroup(leftItems, 'L')}
      ${_nodeGroup(rightItems, 'R')}

      <!-- central risk circle -->
      <circle cx="${CX}" cy="${CY}" r="${R}" fill="${levelColor}22" stroke="${levelColor}" stroke-width="2.5"/>
      <text x="${CX}" y="${CY - 8}" text-anchor="middle" font-size="10"
            font-family="Inter,system-ui,sans-serif" fill="${levelColor}" font-weight="700">${riskCode}</text>
      <text x="${CX}" y="${CY + 6}" text-anchor="middle" font-size="10"
            font-family="Inter,system-ui,sans-serif" fill="${levelColor}" font-weight="700">R=${r.residual_level}</text>
      <text x="${CX}" y="${CY + 20}" text-anchor="middle" font-size="9"
            font-family="Inter,system-ui,sans-serif" fill="var(--text-muted)">${_truncate(assetName, 16)}</text>
    </svg>`;

    UI.modal(`Diagrama Bow-Tie — ${riskCode}`, `
      <div class="span2" style="margin-bottom:12px;">
        ${svg}
      </div>
      <div class="span2">
        <table style="width:100%;font-size:12px;border-collapse:collapse;">
          <tr style="background:var(--bg-2);">
            <td style="padding:6px 10px;font-weight:600;color:var(--text-muted);width:120px;">Activo</td>
            <td style="padding:6px 10px;">${UI.esc(assetName)}</td>
            <td style="padding:6px 10px;font-weight:600;color:var(--text-muted);width:120px;">Amenaza</td>
            <td style="padding:6px 10px;">${UI.esc(threatName)}</td>
          </tr>
          <tr>
            <td style="padding:6px 10px;font-weight:600;color:var(--text-muted);">Nivel residual</td>
            <td style="padding:6px 10px;">${UI.riskPill(r.residual_level)}</td>
            <td style="padding:6px 10px;font-weight:600;color:var(--text-muted);">Tratamiento</td>
            <td style="padding:6px 10px;">${UI.treatmentLabel(r.treatment_option)}</td>
          </tr>
          ${vulns.length ? `<tr style="background:var(--bg-2);"><td style="padding:6px 10px;font-weight:600;color:var(--text-muted);">Vulnerabilidades</td>
            <td colspan="3" style="padding:6px 10px;">${vulns.map(v=>UI.esc(v.name||v.code)).join(', ')}</td></tr>` : ''}
          ${controls.length ? `<tr><td style="padding:6px 10px;font-weight:600;color:var(--text-muted);">Controles</td>
            <td colspan="3" style="padding:6px 10px;">${controls.map(c=>UI.esc(c.name||c.code)).join(', ')}</td></tr>` : ''}
        </table>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">${t('common.close')}</button>
                <button class="btn btn-ghost" id="m-back">${t('common.back')}</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-back').onclick = () => { UI.closeModal(); ViewRisks._edit(r.id); };
  },

  // ---- MAGERIT: preview en tiempo real ----

  async _updateMageritPreview() {
    const assetEl = document.getElementById('f-asset');
    const dimEl   = document.getElementById('f-magerit-dim');
    const degradEl = document.getElementById('f-degrad');
    if (!assetEl || !dimEl || !degradEl) return;

    const asset_id     = parseInt(assetEl.value);
    const dimension    = dimEl.value;
    const degradation  = parseInt(degradEl.value);

    try {
      const res = await Api.post('/api/risks/magerit-preview', { asset_id, dimension, degradation_pct: degradation });

      // Actualizar el valor hidden de consecuencia
      const icHidden = document.getElementById('f-ic');
      if (icHidden) icHidden.value = res.consequence;

      // Actualizar el display
      document.getElementById('magerit-cons-val').textContent = res.consequence;
      document.getElementById('magerit-ic-display').textContent = res.consequence;

      const consLabels = [t('risks.magerit_cons_0'),t('risks.magerit_cons_1'),t('risks.magerit_cons_2'),t('risks.magerit_cons_3'),t('risks.magerit_cons_4')];
      document.getElementById('magerit-cons-lbl').textContent = consLabels[res.consequence] || '-';
      document.getElementById('magerit-impact-val').textContent = res.magerit_impact;

      // Barra de dimensiones del activo
      const bar = document.getElementById('magerit-dims-bar');
      if (bar && res.asset_dims) {
        const dimNames = {D:'Disp.',I:'Integr.',C:'Confid.',A:'Autent.',T:'Trazab.'};
        bar.innerHTML = Object.entries(res.asset_dims).map(([d, v]) => `
          <div style="text-align:center;">
            <div style="font-size:10px;color:${d===dimension?'var(--brand-purple)':'var(--text-muted)'};">
              ${d} — ${dimNames[d]||d}
            </div>
            <div style="height:${Math.max(4, v*8)}px;background:${d===dimension?'var(--brand-purple)':'var(--border)'};
                         border-radius:4px;transition:height .2s,background .2s;"></div>
            <div style="font-size:11px;font-weight:700;color:${d===dimension?'var(--brand-purple)':'var(--text-muted)'};">${v}</div>
          </div>`).join('');
      }
    } catch (_) { /* silencioso */ }
  },

  // ============================================================
  // Trazabilidad de madurez y fuentes (SOA)
  // ============================================================

  async _loadTrace(riskId, container) {
    const matColors = ['#EF4444','#F97316','#F59E0B','#84CC16','#22C55E','#0EA5E9'];
    const matBg     = ['#FEE2E2','#FFEDD5','#FEF3C7','#F0FDF4','#DCFCE7','#E0F2FE'];

    try {
      const t = await Api.get(`/api/risks/${riskId}/trace`);

      // --- Cabecera de cálculo ---
      const calcColor = t.combined_efficacy_pct >= 50 ? 'var(--risk-low)' : t.combined_efficacy_pct >= 25 ? '#D97706' : 'var(--risk-high)';
      let html = `
        <div style="background:var(--bg-2);border-radius:10px;padding:14px;margin-bottom:12px;">
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;text-align:center;margin-bottom:10px;">
            <div>
              <div style="font-size:22px;font-weight:800;">${UI.riskPill(t.inherent_level)}</div>
              <div style="font-size:11px;color:var(--text-muted);">Nivel inherente</div>
              <div style="font-size:11px;color:var(--text-muted);">${t.inherent_likelihood_label} × ${t.inherent_consequence_label}</div>
            </div>
            <div>
              <div style="font-size:22px;font-weight:800;color:${calcColor};">${t.combined_efficacy_pct}%</div>
              <div style="font-size:11px;color:var(--text-muted);">Eficacia combinada de controles</div>
              <div style="font-size:11px;color:var(--text-muted);">${t.controls.length} control${t.controls.length !== 1 ? 'es' : ''} vinculado${t.controls.length !== 1 ? 's' : ''}</div>
            </div>
            <div>
              <div style="font-size:22px;font-weight:800;">${UI.riskPill(t.residual_level)}</div>
              <div style="font-size:11px;color:var(--text-muted);">Nivel residual</div>
              <div style="font-size:11px;color:var(--text-muted);">${t.residual_likelihood_label} × ${t.residual_consequence_label}</div>
            </div>
          </div>
          <details style="margin-top:6px;">
            <summary style="font-size:11px;color:var(--text-muted);cursor:pointer;list-style:none;">
              Ver fórmula de cálculo ISO 27005
            </summary>
            <pre style="font-size:11px;background:var(--bg-1);padding:10px;border-radius:6px;margin-top:6px;
                        white-space:pre-wrap;color:var(--text-base);">${UI.esc(t.calculation_formula)}</pre>
          </details>
          ${t.above_appetite ? `<div style="margin-top:8px;padding:6px 10px;background:#FEF3C7;border-radius:6px;font-size:12px;color:#92400E;">
            ⚠ Nivel residual (${t.residual_level}) supera el apetito de riesgo (${t.appetite}). Requiere tratamiento adicional.
          </div>` : `<div style="margin-top:8px;padding:6px 10px;background:#F0FDF4;border-radius:6px;font-size:12px;color:#166534;">
            ✓ Nivel residual (${t.residual_level}) dentro del apetito de riesgo (${t.appetite}).
          </div>`}
        </div>`;

      // --- Controles con trazabilidad ---
      if (t.controls.length) {
        html += `<h4 style="font-size:13px;font-weight:700;margin:0 0 8px;">
          Controles vinculados — trazabilidad de fuentes
        </h4>`;
        t.controls.forEach(c => {
          const bg = matBg[c.maturity] || matBg[0];
          const col = matColors[c.maturity] || matColors[0];
          const refsHtml = (c.evidence_refs || []).map(ref =>
            `<a href="${UI.esc(ref.url || '#')}" target="_blank" rel="noopener"
                style="display:inline-flex;align-items:center;gap:4px;font-size:11px;
                       background:var(--brand-purple-4);border:1px solid var(--brand-purple-3);
                       border-radius:4px;padding:2px 8px;color:var(--brand-purple);
                       text-decoration:none;margin:2px;" title="Referencia SOA">
              📄 ${UI.esc(ref.title || ref.url || 'Documento')}
            </a>`
          ).join('');
          const filesHtml = (c.evidence_files || []).map(f =>
            `<span style="display:inline-flex;align-items:center;gap:4px;font-size:11px;
                          background:#F0FDF4;border:1px solid #86EFAC;
                          border-radius:4px;padding:2px 8px;color:#166534;margin:2px;"
                  title="${f.expires_at ? 'Expira: ' + new Date(f.expires_at).toLocaleDateString('es-ES') : ''}">
              ✓ ${UI.esc(f.code)} — ${UI.esc(f.title)}${f.compliance_requirement ? ` [${UI.esc(f.compliance_requirement)}]` : ''}
            </span>`
          ).join('');
          const noSource = !c.evidence_refs?.length && !c.evidence_files?.length;
          html += `
            <div style="background:var(--bg-1);border:1px solid var(--border);border-radius:10px;
                        padding:12px 14px;margin-bottom:8px;">
              <div style="display:flex;align-items:flex-start;gap:10px;flex-wrap:wrap;">
                <!-- Madurez badge -->
                <div style="min-width:60px;text-align:center;background:${bg};border-radius:8px;padding:6px 10px;">
                  <div style="font-size:20px;font-weight:800;color:${col};">${c.maturity}/5</div>
                  <div style="font-size:9px;color:${col};font-weight:600;">MADUREZ</div>
                </div>
                <div style="flex:1;min-width:0;">
                  <div style="font-weight:600;font-size:14px;">
                    ${c.code ? `<span class="badge badge-muted" style="font-size:10px;">${UI.esc(c.code)}</span> ` : ''}
                    ${UI.esc(c.name)}
                    <span style="margin-left:6px;font-size:11px;font-weight:400;color:var(--text-muted);">
                      ${c.theme ? `[${UI.esc(c.theme)}]` : ''}
                    </span>
                  </div>
                  <div style="font-size:12px;color:var(--text-muted);margin-top:2px;">
                    Estado: <strong>${c.status}</strong> ·
                    Eficacia: <strong style="color:${col};">${c.efficacy_pct}%</strong>
                    <span style="color:var(--text-muted);"> = (${c.maturity}/5 madurez) × (${Math.round(c.contribution*100)}% contribución)</span>
                    ${c.inclusion_reason ? ` · Razón SOA: <em>${UI.esc(c.inclusion_reason)}</em>` : ''}
                    ${c.soa_reviewed_at ? ` · Revisado SOA: ${new Date(c.soa_reviewed_at).toLocaleDateString('es-ES')}` : ''}
                  </div>
                  <!-- Explicación de madurez -->
                  <div style="margin-top:6px;font-size:12px;padding:6px 10px;border-radius:6px;
                              background:${bg};color:#374151;border-left:3px solid ${col};">
                    ${UI.esc(c.maturity_why)}
                  </div>
                  <!-- Fuentes de evidencia -->
                  <div style="margin-top:6px;">
                    ${refsHtml || ''}
                    ${filesHtml || ''}
                    ${noSource ? `<span style="font-size:11px;color:#B45309;background:#FEF3C7;
                                               border-radius:4px;padding:2px 8px;">
                      ⚠ Sin fuentes documentales — la madurez declarada no tiene soporte de evidencia
                    </span>` : ''}
                  </div>
                  ${c.notes ? `<div style="margin-top:4px;font-size:11px;color:var(--text-muted);">
                    Notas: ${UI.esc(c.notes)}
                  </div>` : ''}
                </div>
              </div>
            </div>`;
        });
      } else {
        html += `<div class="notice notice-warn">
          Sin controles vinculados — el nivel residual es igual al inherente.
          Vincula controles ISO 27002 para reducir el riesgo.
        </div>`;
      }

      // --- Evidencia directa del riesgo ---
      if (t.evidence_direct?.length) {
        html += `<h4 style="font-size:13px;font-weight:700;margin:12px 0 6px;">
          Evidencias vinculadas directamente al riesgo
        </h4>
        <div style="display:flex;flex-wrap:wrap;gap:6px;">
          ${t.evidence_direct.map(e => `
            <span style="background:#F0FDF4;border:1px solid #86EFAC;border-radius:6px;
                         padding:4px 10px;font-size:12px;color:#166534;">
              ✓ ${UI.esc(e.code)} — ${UI.esc(e.title)}
              ${e.expires_at ? `<span style="font-size:10px;color:var(--text-muted);"> (exp. ${new Date(e.expires_at).toLocaleDateString('es-ES')})</span>` : ''}
            </span>`).join('')}
        </div>`;
      }

      // --- Vulnerabilidades ---
      if (t.vulnerabilities?.length) {
        html += `<h4 style="font-size:13px;font-weight:700;margin:12px 0 6px;">
          Vulnerabilidades que facilitan la amenaza
        </h4>
        <div style="display:flex;flex-wrap:wrap;gap:4px;">
          ${t.vulnerabilities.map(v => `
            <span style="background:var(--brand-orange-4);border:1px solid var(--brand-orange-3);
                         border-radius:6px;padding:3px 10px;font-size:12px;">
              ${UI.esc(v.code)} — ${UI.esc(v.name)}
            </span>`).join('')}
        </div>`;
      }

      // --- Panel IA multi-tab (auto-lanza análisis al abrir) ---
      html += `<div id="ai-panel-root" style="margin-top:16px;border-top:1px solid var(--border);padding-top:12px;"></div>`;

      container.innerHTML = html;
      ViewRisks._renderAiTabs(riskId, document.getElementById('ai-panel-root'));

    } catch (e) {
      container.innerHTML = `<div class="notice notice-error">${UI.esc(e.message)}</div>`;
    }
  },

  async _requestAiExplain(riskId) {
    const btn = document.getElementById('btn-ai-explain-refresh');
    const result = document.getElementById('ai-tab-content-explain');
    if (!result) return;
    if (btn) { btn.disabled = true; btn.textContent = 'Analizando...'; }
    result.innerHTML = `<div class="notice">${UI.esc(t('risks.ai_analyzing'))}</div>`;
    try {
      const data = await Api.post(`/api/risks/${riskId}/ai-explain`, {});
      const confColor = {'alta':'#166534','media':'#92400E','baja':'#991B1B'}[data.confidence] || '#374151';
      const confBg    = {'alta':'#F0FDF4','media':'#FEF3C7','baja':'#FEE2E2'}[data.confidence] || '#F9FAFB';

      // Cadena de ataque
      const attackHtml = (data.attack_chain || []).map((step, i) => {
        const coverageColor = step.coverage_quality === 'alta' ? 'var(--success)'
          : step.coverage_quality === 'media' ? 'var(--warning)' : 'var(--danger)';
        const coverageLabel = step.coverage_quality === 'alta' ? 'Cubierto'
          : step.coverage_quality === 'media' ? 'Parcial' : 'Sin cobertura';
        const gapHtml = step.gap ? `<div style="margin-top:3px;font-size:10px;color:var(--danger);font-style:italic;">Brecha: ${UI.esc(step.gap)}</div>` : '';
        const ctrlsHtml = (step.controls_covering || []).length
          ? `<div style="font-size:10px;color:var(--text-muted);margin-top:2px;">Controles: ${step.controls_covering.map(c => UI.esc(c)).join(', ')}</div>` : '';
        return `<div style="display:flex;gap:10px;margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid var(--border-light);">
          <div style="min-width:20px;display:flex;flex-direction:column;align-items:center;">
            <div style="width:20px;height:20px;border-radius:50%;background:${coverageColor};display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff;font-weight:700;flex-shrink:0;">${i+1}</div>
            ${i < (data.attack_chain.length - 1) ? `<div style="width:2px;flex:1;background:var(--border-light);margin-top:3px;"></div>` : ''}
          </div>
          <div style="flex:1;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;">
              <span style="font-size:11px;font-weight:700;color:var(--text-main);">${UI.esc(step.step || '')} <span style="font-weight:400;color:var(--text-muted);">(${UI.esc(step.phase || '')})</span></span>
              <span style="font-size:9px;font-weight:700;color:${coverageColor};border:1px solid ${coverageColor};border-radius:3px;padding:1px 5px;white-space:nowrap;margin-left:6px;">${coverageLabel}</span>
            </div>
            <div style="font-size:11px;color:var(--text-base);margin-top:2px;">${UI.esc(step.description || '')}</div>
            ${step.vulnerability_exploited ? `<div style="font-size:10px;color:var(--warning);margin-top:2px;">Explota: ${UI.esc(step.vulnerability_exploited)}</div>` : ''}
            ${ctrlsHtml}
            ${gapHtml}
          </div>
        </div>`;
      }).join('');

      // Efectividad de controles
      const ctrlEffHtml = (data.control_effectiveness || []).map(ce => {
        const typeColor = ce.control_type === 'P' ? 'var(--success)' : ce.control_type === 'D' ? 'var(--brand-orange)' : 'var(--brand-purple)';
        const typeLabel = ce.control_type === 'P' ? 'PREVENTIVO' : ce.control_type === 'D' ? 'DETECTIVO' : 'CORRECTIVO';
        const adjDiff = (ce.adjusted_maturity || 0) < (ce.declared_maturity || 0);
        return `<div style="padding:6px 0;border-bottom:1px solid var(--border-light);">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:11px;font-weight:600;color:var(--text-main);">${UI.esc(ce.control_name || ce.control_code || '')}</span>
            <span style="font-size:9px;font-weight:700;color:${typeColor};border:1px solid ${typeColor};border-radius:3px;padding:1px 4px;">${typeLabel}</span>
          </div>
          <div style="display:flex;gap:12px;margin-top:3px;font-size:10px;color:var(--text-muted);">
            <span>Madurez declarada: <strong style="color:var(--text-main);">${ce.declared_maturity || 0}/5</strong></span>
            <span>Ajustada por evidencia: <strong style="color:${adjDiff ? 'var(--danger)' : 'var(--success)'};">${ce.adjusted_maturity || 0}/5</strong></span>
            <span>Eficacia: <strong style="color:var(--text-main);">${Math.round((ce.efficacy || 0) * 100)}%</strong></span>
          </div>
          ${ce.evidence_reliability ? `<div style="font-size:10px;color:var(--text-muted);margin-top:2px;">${UI.esc(ce.evidence_reliability)}</div>` : ''}
        </div>`;
      }).join('');

      // Controles faltantes
      const missingHtml = (data.missing_controls || []).map(mc => {
        const priColor = mc.priority === 'alta' ? 'var(--danger)' : mc.priority === 'media' ? 'var(--warning)' : 'var(--text-muted)';
        return `<div style="padding:5px 0;border-bottom:1px solid var(--border-light);">
          <div style="display:flex;gap:8px;align-items:flex-start;">
            <span style="font-size:9px;font-weight:700;color:${priColor};border:1px solid ${priColor};border-radius:3px;padding:1px 4px;white-space:nowrap;margin-top:2px;">${(mc.priority||'?').toUpperCase()}</span>
            <div>
              <span style="font-size:11px;font-weight:600;color:var(--text-main);">[${UI.esc(mc.iso_code||'')}] ${UI.esc(mc.name||'')}</span>
              ${mc.why_needed ? `<div style="font-size:10px;color:var(--text-muted);">${UI.esc(mc.why_needed)}</div>` : ''}
            </div>
          </div>
        </div>`;
      }).join('');

      // Alineacion normativa (objeto por framework)
      let normHtml = '';
      if (data.normative_alignment && typeof data.normative_alignment === 'object') {
        const normEntries = Object.entries(data.normative_alignment).map(([fw, info]) => {
          if (!info) return '';
          const st = (typeof info === 'object') ? info.status : null;
          const stColor = st === 'conforme' ? 'var(--success)' : st === 'parcial' ? 'var(--warning)' : st ? 'var(--danger)' : 'var(--text-muted)';
          const details = (typeof info === 'object') ? (info.details || info.gaps || '') : info;
          return `<div style="padding:4px 0;border-bottom:1px solid var(--border-light);">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span style="font-size:11px;font-weight:600;color:var(--text-main);">${UI.esc(fw)}</span>
              ${st ? `<span style="font-size:9px;font-weight:700;color:${stColor};">${UI.esc(st.toUpperCase())}</span>` : ''}
            </div>
            ${details ? `<div style="font-size:10px;color:var(--text-muted);">${UI.esc(String(details))}</div>` : ''}
          </div>`;
        }).filter(Boolean).join('');
        if (normEntries) normHtml = normEntries;
      } else if (data.normative_alignment) {
        normHtml = `<p style="font-size:12px;color:var(--text-base);">${UI.esc(String(data.normative_alignment))}</p>`;
      }

      // Brechas y recomendaciones
      const gapsHtml = (data.gaps_and_recommendations || []).map(g => {
        const text = typeof g === 'object' ? `${g.gap || g.recommendation || ''} ${g.normative_requirement ? `[${g.normative_requirement}]` : ''}` : g;
        return `<li style="font-size:12px;margin-bottom:5px;line-height:1.5;">${UI.esc(text)}</li>`;
      }).join('');

      // Veredicto residual
      const verdict = data.residual_risk_verdict || {};
      const verdictHtml = verdict.recommended_treatment ? `
        <div style="background:var(--bg-alt);border-left:3px solid var(--brand-purple);border-radius:4px;padding:10px;margin-bottom:10px;">
          <div style="font-size:11px;font-weight:700;color:var(--brand-purple);margin-bottom:4px;">Tratamiento recomendado: ${UI.esc(verdict.recommended_treatment.toUpperCase())}</div>
          ${verdict.justification ? `<div style="font-size:12px;color:var(--text-base);">${UI.esc(verdict.justification)}</div>` : ''}
        </div>` : '';

      // Problemas de calidad de datos
      const dqHtml = (data.data_quality_issues || []).length
        ? `<div style="background:#FEF3C7;border-radius:6px;padding:8px;margin-bottom:10px;">
            <div style="font-size:11px;font-weight:700;color:#92400E;margin-bottom:4px;">Advertencias de calidad de datos</div>
            <ul style="margin:0;padding-left:14px;">${data.data_quality_issues.map(d => `<li style="font-size:11px;color:#92400E;">${UI.esc(d)}</li>`).join('')}</ul>
           </div>` : '';

      result.innerHTML = `
        <div style="background:var(--bg-2);border-radius:10px;padding:14px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <strong style="font-size:13px;">Analisis experto IA</strong>
            <span style="background:${confBg};color:${confColor};border-radius:4px;padding:2px 10px;font-size:11px;font-weight:700;">
              Confianza: ${(data.confidence || '').toUpperCase()}
            </span>
          </div>

          ${dqHtml}
          ${verdictHtml}

          <p style="font-size:13px;line-height:1.6;margin-bottom:12px;">${UI.esc(data.executive_summary || '')}</p>

          ${attackHtml ? `
          <div style="margin-bottom:12px;">
            <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px;">Cadena de ataque</div>
            ${attackHtml}
          </div>` : ''}

          ${ctrlEffHtml ? `
          <div style="margin-bottom:12px;">
            <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">Efectividad de controles</div>
            ${ctrlEffHtml}
          </div>` : ''}

          ${data.evidence_quality_assessment ? `
          <div style="margin-bottom:12px;padding:8px;background:var(--bg-alt);border-radius:6px;">
            <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px;">Evaluacion de calidad de evidencia</div>
            <p style="font-size:11px;color:var(--text-base);margin:0;">${UI.esc(data.evidence_quality_assessment)}</p>
          </div>` : ''}

          ${missingHtml ? `
          <div style="margin-bottom:12px;">
            <div style="font-size:11px;font-weight:700;color:var(--danger);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">Controles ausentes</div>
            ${missingHtml}
          </div>` : ''}

          ${gapsHtml ? `
          <div style="margin-bottom:12px;">
            <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">Brechas y recomendaciones</div>
            <ul style="margin:0;padding-left:16px;">${gapsHtml}</ul>
          </div>` : ''}

          ${normHtml ? `
          <div style="margin-bottom:8px;">
            <div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">Alineacion normativa</div>
            ${normHtml}
          </div>` : ''}

          ${data.confidence_reason ? `
          <div style="margin-top:8px;font-size:11px;color:var(--text-muted);font-style:italic;border-top:1px solid var(--border-light);padding-top:6px;">
            Nivel de confianza: ${UI.esc(data.confidence_reason)}
          </div>` : ''}
        </div>`;
      if (btn) { btn.textContent = 'Regenerar'; btn.disabled = false; }
    } catch (e) {
      if (result) result.innerHTML = `<div class="notice notice-error">${UI.esc(e.message)}</div>`;
      if (btn) { btn.textContent = 'Analisis IA'; btn.disabled = false; }
    }
  },

  // ── Panel IA multi-tab ────────────────────────────────────────────────────

  _renderAiTabs(riskId, root) {
    if (!root) return;
    const tabs = [
      { id: 'explain',  label: 'Analisis IA' },
      { id: 'scenario', label: 'Escenario MITRE' },
      { id: 'whatif',   label: 'What-If' },
      { id: 'var',      label: 'VaR' },
      { id: 'history',  label: 'Historial' },
      { id: 'kris',     label: 'KRIs' },
    ];
    const _tabBtn = (t, active) =>
      `<button class="ai-tab-btn" data-ai-tab="${t.id}"
        style="padding:6px 14px;border:none;background:none;cursor:pointer;font-size:13px;font-weight:600;
               color:${active ? 'var(--brand-purple)' : 'var(--text-muted)'};
               border-bottom:3px solid ${active ? 'var(--brand-purple)' : 'transparent'};
               margin-bottom:-2px;white-space:nowrap;">${t.label}</button>`;
    root.innerHTML = `
      <div style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:12px;overflow-x:auto;">
        ${tabs.map((t, i) => _tabBtn(t, i === 0)).join('')}
        <button id="btn-ai-explain-refresh" title="Regenerar analisis IA"
          style="margin-left:auto;padding:4px 12px;border:1px solid var(--border);border-radius:6px;
                 background:none;cursor:pointer;font-size:12px;color:var(--brand-purple);white-space:nowrap;align-self:center;">
          Regenerar
        </button>
      </div>
      ${tabs.map((t, i) =>
        `<div id="ai-tab-content-${t.id}" style="display:${i === 0 ? 'block' : 'none'};"></div>`
      ).join('')}`;

    root.querySelectorAll('.ai-tab-btn').forEach(btn => {
      btn.onclick = () => {
        root.querySelectorAll('.ai-tab-btn').forEach(b => {
          b.style.color = 'var(--text-muted)';
          b.style.borderBottomColor = 'transparent';
        });
        btn.style.color = 'var(--brand-purple)';
        btn.style.borderBottomColor = 'var(--brand-purple)';
        tabs.forEach(t => {
          const el = document.getElementById(`ai-tab-content-${t.id}`);
          if (el) el.style.display = t.id === btn.dataset.aiTab ? 'block' : 'none';
        });
        ViewRisks._loadAiTab(btn.dataset.aiTab, riskId);
      };
    });

    const refreshBtn = document.getElementById('btn-ai-explain-refresh');
    if (refreshBtn) refreshBtn.onclick = () => {
      const active = root.querySelector('.ai-tab-btn[style*="var(--brand-purple)"]');
      const tabId = active ? active.dataset.aiTab : 'explain';
      ViewRisks._forceLoadAiTab(tabId, riskId);
    };

    // Auto-lanza análisis + escenario en paralelo al abrir
    ViewRisks._aiTabLoaded = {};
    ViewRisks._requestAiExplain(riskId);
    ViewRisks._aiTabLoaded['explain'] = true;
    // Escenario se carga en background silenciosamente para tenerlo listo
    ViewRisks._loadAiTabScenario(riskId, true);
    ViewRisks._aiTabLoaded['scenario'] = true;
  },

  _loadAiTab(tabId, riskId) {
    if (ViewRisks._aiTabLoaded && ViewRisks._aiTabLoaded[tabId]) return;
    ViewRisks._forceLoadAiTab(tabId, riskId);
  },

  _forceLoadAiTab(tabId, riskId) {
    if (!ViewRisks._aiTabLoaded) ViewRisks._aiTabLoaded = {};
    ViewRisks._aiTabLoaded[tabId] = true;
    if (tabId === 'explain')  ViewRisks._requestAiExplain(riskId);
    if (tabId === 'scenario') ViewRisks._loadAiTabScenario(riskId, false);
    if (tabId === 'whatif')   ViewRisks._renderWhatIfTab(riskId);
    if (tabId === 'var')      ViewRisks._loadAiVaR(riskId);
    if (tabId === 'history')  ViewRisks._loadSnapshotHistory(riskId);
    if (tabId === 'kris')     ViewRisks._loadRiskKRIs(riskId);
  },

  async _loadAiTabScenario(riskId, silent) {
    const container = document.getElementById('ai-tab-content-scenario');
    if (!container) return;
    if (!silent) container.innerHTML = '<div class="notice">Generando escenario MITRE ATT&CK...</div>';
    try {
      const data = await Api.post(`/api/risks/${riskId}/ai-scenario`, {});
      const stepsHtml = (data.steps || []).map((s, i) => {
        const phaseColor = {'Reconnaissance':'#7C3AED','Resource Development':'#6D28D9',
          'Initial Access':'#1D4ED8','Execution':'#0369A1','Persistence':'#0F766E',
          'Privilege Escalation':'#B45309','Defense Evasion':'#92400E','Credential Access':'#9A3412',
          'Discovery':'#166534','Lateral Movement':'#065F46','Collection':'#1E3A5F',
          'Command and Control':'#4C1D95','Exfiltration':'#831843','Impact':'#991B1B'}[s.tactic] || '#374151';
        return `<div style="display:flex;gap:10px;margin-bottom:10px;">
          <div style="min-width:24px;height:24px;border-radius:50%;background:${phaseColor};display:flex;align-items:center;
                      justify-content:center;font-size:10px;color:#fff;font-weight:700;flex-shrink:0;">${i+1}</div>
          <div style="flex:1;background:var(--bg-1);border-radius:8px;padding:8px 12px;border-left:3px solid ${phaseColor};">
            <div style="font-size:11px;font-weight:700;color:${phaseColor};">${UI.esc(s.tactic||'')} — <code style="font-size:10px;">${UI.esc(s.technique_id||'')}</code> ${UI.esc(s.technique_name||'')}</div>
            <div style="font-size:12px;color:var(--text-base);margin-top:3px;">${UI.esc(s.description||'')}</div>
            ${s.mitigations?.length ? `<div style="font-size:11px;color:var(--success);margin-top:3px;">Mitigaciones: ${s.mitigations.map(m=>UI.esc(m)).join(', ')}</div>` : ''}
            ${s.gaps?.length ? `<div style="font-size:11px;color:var(--danger);margin-top:3px;">Brechas: ${s.gaps.map(g=>UI.esc(g)).join(', ')}</div>` : ''}
          </div>
        </div>`;
      }).join('');
      const critGapsHtml = (data.critical_gaps || []).map(g =>
        `<li style="font-size:12px;color:var(--danger);margin-bottom:4px;">${UI.esc(g)}</li>`
      ).join('');
      const mitigationsHtml = (data.priority_mitigations || []).map(m =>
        `<li style="font-size:12px;margin-bottom:4px;">${UI.esc(m)}</li>`
      ).join('');
      container.innerHTML = `
        <div style="background:var(--bg-2);border-radius:10px;padding:14px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <strong style="font-size:13px;">Kill-chain MITRE ATT&amp;CK</strong>
            ${data.overall_risk_rating ? `<span style="background:var(--bg-1);border:1px solid var(--border);border-radius:4px;padding:2px 10px;font-size:11px;font-weight:700;color:var(--brand-purple);">Rating: ${UI.esc(data.overall_risk_rating.toUpperCase())}</span>` : ''}
          </div>
          ${data.scenario_summary ? `<p style="font-size:13px;line-height:1.6;margin-bottom:12px;">${UI.esc(data.scenario_summary)}</p>` : ''}
          <div style="margin-bottom:12px;">${stepsHtml}</div>
          ${critGapsHtml ? `<div style="margin-bottom:10px;"><div style="font-size:11px;font-weight:700;color:var(--danger);text-transform:uppercase;margin-bottom:6px;">Brechas criticas</div><ul style="margin:0;padding-left:14px;">${critGapsHtml}</ul></div>` : ''}
          ${mitigationsHtml ? `<div><div style="font-size:11px;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px;">Mitigaciones prioritarias</div><ul style="margin:0;padding-left:14px;">${mitigationsHtml}</ul></div>` : ''}
        </div>`;
    } catch (e) {
      if (!silent) container.innerHTML = `<div class="notice notice-error">${UI.esc(e.message)}</div>`;
      else container.innerHTML = `<div class="notice notice-info" style="font-size:12px;">Haz clic en "Escenario MITRE" para generar el kill-chain con IA.</div>`;
    }
  },

  _renderWhatIfTab(riskId) {
    const container = document.getElementById('ai-tab-content-whatif');
    if (!container) return;
    container.innerHTML = `
      <div style="background:var(--bg-2);border-radius:10px;padding:14px;">
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:14px;">
          Simula como cambia el nivel residual si modificas los parametros del riesgo (sin persistir cambios).
        </p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px;">
          <div>
            <label class="form-label" style="font-size:12px;">Probabilidad inherente (1-5)</label>
            <input type="number" id="wif-likelihood" class="form-control" min="1" max="5" step="1" value="3">
          </div>
          <div>
            <label class="form-label" style="font-size:12px;">Impacto inherente (1-5)</label>
            <input type="number" id="wif-consequence" class="form-control" min="1" max="5" step="1" value="3">
          </div>
          <div>
            <label class="form-label" style="font-size:12px;">Madurez de controles (0-5)</label>
            <input type="number" id="wif-maturity" class="form-control" min="0" max="5" step="1">
          </div>
          <div>
            <label class="form-label" style="font-size:12px;">Objetivo residual (nivel 1-9)</label>
            <input type="number" id="wif-target" class="form-control" min="1" max="9" step="1">
          </div>
        </div>
        <button class="btn btn-primary" id="btn-wif-run" style="font-size:13px;">Simular</button>
        <div id="wif-result" style="margin-top:12px;"></div>
      </div>`;
    document.getElementById('btn-wif-run').onclick = async () => {
      const btn = document.getElementById('btn-wif-run');
      const result = document.getElementById('wif-result');
      btn.disabled = true; btn.textContent = 'Calculando...';
      const params = new URLSearchParams();
      const l = document.getElementById('wif-likelihood').value;
      const c = document.getElementById('wif-consequence').value;
      const m = document.getElementById('wif-maturity').value;
      const t = document.getElementById('wif-target').value;
      if (l) params.set('override_likelihood', l);
      if (c) params.set('override_consequence', c);
      if (m) params.set('override_maturity', m);
      if (t) params.set('target_level', t);
      try {
        const data = await Api.get(`/api/risks/${riskId}/simulate?${params.toString()}`);
        const levelColor = lvl => lvl >= 8 ? 'var(--risk-critical)' : lvl >= 6 ? 'var(--risk-high)' : lvl >= 3 ? 'var(--risk-medium)' : 'var(--risk-low)';
        const delta = (data.residual_level_simulated || 0) - (data.residual_level_current || 0);
        const deltaStr = delta < 0 ? `▼ ${Math.abs(delta)} menos` : delta > 0 ? `▲ ${delta} mas` : '= sin cambio';
        const deltaColor = delta < 0 ? 'var(--success)' : delta > 0 ? 'var(--danger)' : 'var(--text-muted)';
        result.innerHTML = `
          <div style="background:var(--bg-1);border-radius:8px;padding:12px;border:1px solid var(--border);">
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:10px;">
              <div style="text-align:center;">
                <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;margin-bottom:4px;">Residual actual</div>
                <div style="font-size:24px;font-weight:800;color:${levelColor(data.residual_level_current)}">${data.residual_level_current}</div>
              </div>
              <div style="text-align:center;">
                <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;margin-bottom:4px;">Residual simulado</div>
                <div style="font-size:24px;font-weight:800;color:${levelColor(data.residual_level_simulated)}">${data.residual_level_simulated}</div>
              </div>
              <div style="text-align:center;">
                <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;margin-bottom:4px;">Delta</div>
                <div style="font-size:18px;font-weight:700;color:${deltaColor}">${deltaStr}</div>
              </div>
            </div>
            ${data.meets_target !== undefined ? `<div style="padding:6px 10px;background:${data.meets_target ? '#F0FDF4' : '#FEF3C7'};border-radius:6px;font-size:12px;color:${data.meets_target ? '#166534' : '#92400E'};">
              ${data.meets_target ? 'El escenario simulado alcanza el objetivo residual.' : `No alcanza el objetivo. Brecha: ${data.gap_to_target || 0} puntos.`}
            </div>` : ''}
            ${data.control_reduction_pct !== undefined ? `<div style="margin-top:8px;font-size:12px;color:var(--text-muted);">Reduccion de controles: <strong>${data.control_reduction_pct}%</strong></div>` : ''}
            ${data.recommendation ? `<div style="margin-top:8px;font-size:12px;line-height:1.5;color:var(--text-base);">${UI.esc(data.recommendation)}</div>` : ''}
          </div>`;
      } catch (e) {
        result.innerHTML = `<div class="notice notice-error">${UI.esc(e.message)}</div>`;
      }
      btn.disabled = false; btn.textContent = 'Simular';
    };
  },

  async _loadAiVaR(riskId) {
    const container = document.getElementById('ai-tab-content-var');
    if (!container) return;
    container.innerHTML = '<div class="notice">Calculando Value at Risk via Monte Carlo...</div>';
    try {
      const data = await Api.get(`/api/risks/${riskId}/value-at-risk`);
      const fmt = v => v !== undefined && v !== null ? v.toFixed(2) : '-';
      const barW = v => Math.min(100, Math.round((v / (data.var_99 || 1)) * 100));
      container.innerHTML = `
        <div style="background:var(--bg-2);border-radius:10px;padding:14px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <strong style="font-size:13px;">Value at Risk — Monte Carlo (${(data.simulations||10000).toLocaleString()} simulaciones)</strong>
          </div>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px;">
            <div style="background:var(--bg-1);border-radius:8px;padding:10px;text-align:center;border:1px solid var(--border);">
              <div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;margin-bottom:4px;">Esperado</div>
              <div style="font-size:22px;font-weight:800;color:var(--text-main);">${fmt(data.expected_loss)}</div>
              <div style="font-size:10px;color:var(--text-muted);">Media</div>
            </div>
            <div style="background:#FEF3C7;border-radius:8px;padding:10px;text-align:center;border:1px solid #FDE68A;">
              <div style="font-size:10px;color:#92400E;text-transform:uppercase;margin-bottom:4px;">VaR 95%</div>
              <div style="font-size:22px;font-weight:800;color:#92400E;">${fmt(data.var_95)}</div>
              <div style="font-size:10px;color:#92400E;">Percentil 95</div>
            </div>
            <div style="background:#FEE2E2;border-radius:8px;padding:10px;text-align:center;border:1px solid #FECACA;">
              <div style="font-size:10px;color:#991B1B;text-transform:uppercase;margin-bottom:4px;">VaR 99%</div>
              <div style="font-size:22px;font-weight:800;color:#991B1B;">${fmt(data.var_99)}</div>
              <div style="font-size:10px;color:#991B1B;">Percentil 99 (Worst case)</div>
            </div>
          </div>
          ${[{label:'Esperado', v:data.expected_loss, color:'var(--brand-purple)'},
             {label:'VaR 95%', v:data.var_95, color:'#92400E'},
             {label:'VaR 99%', v:data.var_99, color:'#991B1B'}].map(({label,v,color}) => `
          <div style="margin-bottom:8px;">
            <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-bottom:3px;">
              <span>${label}</span><span>${fmt(v)}</span>
            </div>
            <div style="background:var(--bg-1);border-radius:4px;height:8px;overflow:hidden;">
              <div style="width:${barW(v||0)}%;height:100%;background:${color};border-radius:4px;"></div>
            </div>
          </div>`).join('')}
          ${data.probability_of_occurrence !== undefined ? `<div style="margin-top:10px;font-size:12px;color:var(--text-muted);">Probabilidad de ocurrencia estimada: <strong>${Math.round((data.probability_of_occurrence||0)*100)}%</strong></div>` : ''}
          ${data.note ? `<div style="margin-top:8px;font-size:11px;color:var(--text-muted);font-style:italic;">${UI.esc(data.note)}</div>` : ''}
        </div>`;
    } catch (e) {
      container.innerHTML = `<div class="notice notice-error">${UI.esc(e.message)}</div>`;
    }
  },

  async _loadSnapshotHistory(riskId) {
    const container = document.getElementById('ai-tab-content-history');
    if (!container) return;
    container.innerHTML = '<div class="notice">Cargando historial de niveles...</div>';
    try {
      const data = await Api.get(`/api/risks/${riskId}/history`);
      const snaps = Array.isArray(data) ? data : (data.snapshots || []);
      if (!snaps.length) {
        container.innerHTML = '<div class="notice notice-info">Sin snapshots mensuales todavia. Se generan automaticamente el dia 1 de cada mes.</div>';
        return;
      }
      // Mini sparkline SVG
      const inh = snaps.map(s => s.inherent_level || 0);
      const res = snaps.map(s => s.residual_level || 0);
      const maxV = Math.max(...inh, ...res, 1);
      const W = 300, H = 60, pad = 4;
      const xStep = (W - pad*2) / Math.max(snaps.length - 1, 1);
      const yScale = v => H - pad - ((v / maxV) * (H - pad*2));
      const pts = arr => arr.map((v, i) => `${pad + i * xStep},${yScale(v)}`).join(' ');
      const svgLine = (arr, color) => snaps.length > 1
        ? `<polyline points="${pts(arr)}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>`
        : `<circle cx="${W/2}" cy="${yScale(arr[0])}" r="4" fill="${color}"/>`;
      const sparkline = `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;height:${H}px;margin-bottom:10px;">
        ${svgLine(inh, '#94A3B8')}${svgLine(res, 'var(--brand-purple)')}
        ${snaps.map((_, i) => `<circle cx="${pad + i * xStep}" cy="${yScale(res[i])}" r="3" fill="var(--brand-purple)" opacity=".7"/>`).join('')}
      </svg>`;
      const rows = snaps.map(s => {
        const d = s.snapshot_date ? new Date(s.snapshot_date).toLocaleDateString('es-ES',{month:'short',year:'numeric'}) : '-';
        const levelColor = lvl => lvl >= 8 ? 'var(--risk-critical)' : lvl >= 6 ? 'var(--risk-high)' : lvl >= 3 ? 'var(--risk-medium)' : 'var(--risk-low)';
        return `<tr>
          <td style="font-size:12px;color:var(--text-muted);">${d}</td>
          <td style="text-align:center;font-weight:700;color:${levelColor(s.inherent_level||0)};">${s.inherent_level||'-'}</td>
          <td style="text-align:center;font-weight:700;color:${levelColor(s.residual_level||0)};">${s.residual_level||'-'}</td>
          <td style="text-align:center;font-size:12px;">${s.control_count ?? '-'}</td>
          <td style="font-size:11px;color:var(--text-muted);">${UI.esc(s.snapshot_reason||'')}</td>
        </tr>`;
      }).join('');
      container.innerHTML = `
        <div style="background:var(--bg-2);border-radius:10px;padding:14px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <strong style="font-size:13px;">Evolucion del nivel de riesgo</strong>
            <div style="display:flex;gap:12px;font-size:11px;color:var(--text-muted);">
              <span style="display:flex;align-items:center;gap:4px;"><span style="display:inline-block;width:12px;height:3px;background:#94A3B8;border-radius:2px;"></span>Inherente</span>
              <span style="display:flex;align-items:center;gap:4px;"><span style="display:inline-block;width:12px;height:3px;background:var(--brand-purple);border-radius:2px;"></span>Residual</span>
            </div>
          </div>
          ${sparkline}
          <div class="table-wrap"><table class="data" style="font-size:12px;">
            <thead><tr><th>Periodo</th><th style="text-align:center;">Inherente</th><th style="text-align:center;">Residual</th><th style="text-align:center;">Controles</th><th>Razon</th></tr></thead>
            <tbody>${rows}</tbody>
          </table></div>
        </div>`;
    } catch (e) {
      container.innerHTML = `<div class="notice notice-error">${UI.esc(e.message)}</div>`;
    }
  },

  async _loadRiskKRIs(riskId) {
    const container = document.getElementById('ai-tab-content-kris');
    if (!container) return;
    container.innerHTML = '<div class="notice">Cargando KRIs vinculados...</div>';
    try {
      const kris = await Api.get(`/api/kris?risk_id=${riskId}`);
      if (!kris.length) {
        container.innerHTML = `
          <div class="notice notice-info" style="margin-bottom:12px;">Sin KRIs vinculados a este riesgo.</div>
          <button class="btn btn-ghost btn-sm" onclick="window.location.hash='kris'">
            Ir al modulo de KRIs
          </button>`;
        return;
      }
      const statusColor = s => s === 'breached' ? 'var(--danger)' : s === 'warning' ? 'var(--warning)' : 'var(--success)';
      const statusLabel = s => s === 'breached' ? 'ALERTA' : s === 'warning' ? 'AVISO' : 'OK';
      const rows = kris.map(k => `
        <div style="background:var(--bg-1);border:1px solid var(--border);border-left:4px solid ${statusColor(k.status)};
                    border-radius:8px;padding:10px 14px;margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
            <div>
              <div style="font-size:13px;font-weight:600;">${UI.esc(k.name)}</div>
              <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${UI.esc(k.metric_type||'')} · Umbral: ${k.threshold_warning ?? '-'} / ${k.threshold_breach ?? '-'}</div>
            </div>
            <div style="text-align:right;flex-shrink:0;">
              <span style="font-size:9px;font-weight:700;color:${statusColor(k.status)};border:1px solid ${statusColor(k.status)};border-radius:3px;padding:1px 6px;">${statusLabel(k.status)}</span>
              <div style="font-size:18px;font-weight:800;color:${statusColor(k.status)};margin-top:2px;">${k.current_value ?? '-'}</div>
            </div>
          </div>
          ${k.last_evaluated_at ? `<div style="font-size:10px;color:var(--text-muted);margin-top:4px;">Ultima evaluacion: ${new Date(k.last_evaluated_at).toLocaleString('es-ES')}</div>` : ''}
        </div>`).join('');
      container.innerHTML = `
        <div style="background:var(--bg-2);border-radius:10px;padding:14px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <strong style="font-size:13px;">Indicadores de Riesgo Clave (KRI)</strong>
            <button class="btn btn-ghost btn-sm" id="btn-eval-kris">Evaluar todos</button>
          </div>
          ${rows}
        </div>`;
      document.getElementById('btn-eval-kris').onclick = async () => {
        try {
          await Promise.all(kris.map(k => Api.post(`/api/kris/${k.id}/evaluate`, {})));
          ViewRisks._aiTabLoaded && delete ViewRisks._aiTabLoaded['kris'];
          ViewRisks._loadRiskKRIs(riskId);
          UI.toast('KRIs evaluados', 'success');
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    } catch (e) {
      container.innerHTML = `<div class="notice notice-error">${UI.esc(e.message)}</div>`;
    }
  },

  async _discoverRisks() {
    const dBtn = document.getElementById('btn-discover-ai');
    if (dBtn) { dBtn.disabled = true; dBtn.textContent = 'Descubriendo...'; }
    try {
      const data = await Api.post('/api/risks/ai-discover', {});
      const discovered = data.discovered || [];
      if (!discovered.length) {
        UI.toast('El agente IA no encontro riesgos no registrados en el contexto actual.', 'info');
        if (dBtn) { dBtn.disabled = false; dBtn.textContent = 'Descubrir con IA'; }
        return;
      }
      // Mostrar modal con riesgos descubiertos
      const rowsHtml = discovered.map((r, i) => {
        const lvlColor = l => l >= 8 ? 'var(--risk-critical)' : l >= 6 ? 'var(--risk-high)' : l >= 3 ? 'var(--risk-medium)' : 'var(--risk-low)';
        return `<div style="background:var(--bg-1);border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
            <div style="flex:1;">
              <div style="font-size:13px;font-weight:600;">${UI.esc(r.name||r.suggested_name||'')}</div>
              <div style="font-size:12px;color:var(--text-muted);margin-top:3px;">${UI.esc(r.description||r.rationale||'')}</div>
              ${r.asset_name ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px;">Activo: ${UI.esc(r.asset_name)} · Amenaza: ${UI.esc(r.threat_name||'-')}</div>` : ''}
              ${r.iso_reference ? `<div style="font-size:11px;color:var(--brand-purple);margin-top:2px;">ISO ref: ${UI.esc(r.iso_reference)}</div>` : ''}
            </div>
            <div style="text-align:center;flex-shrink:0;">
              <div style="font-size:9px;color:var(--text-muted);text-transform:uppercase;">Nivel est.</div>
              <div style="font-size:22px;font-weight:800;color:${lvlColor(r.estimated_level||0)};">${r.estimated_level||'-'}</div>
            </div>
          </div>
        </div>`;
      }).join('');
      const modal = document.createElement('div');
      modal.className = 'modal-overlay active';
      modal.innerHTML = `
        <div class="modal" style="max-width:640px;width:100%;">
          <div class="modal-header">
            <h3 class="modal-title">Riesgos descubiertos por IA (${discovered.length})</h3>
            <button class="modal-close" id="disc-close">&times;</button>
          </div>
          <div class="modal-body" style="max-height:65vh;overflow-y:auto;">
            <div class="notice notice-info" style="margin-bottom:12px;font-size:13px;">
              El agente IA identifico ${discovered.length} riesgo(s) potencial(es) no registrados. Revisalos y crea los que consideres relevantes.
            </div>
            ${rowsHtml}
          </div>
          <div class="modal-footer">
            <button class="btn btn-ghost" id="disc-cancel">Cerrar</button>
          </div>
        </div>`;
      document.body.appendChild(modal);
      const close = () => modal.remove();
      modal.querySelector('#disc-close').onclick = close;
      modal.querySelector('#disc-cancel').onclick = close;
      modal.onclick = e => { if (e.target === modal) close(); };
    } catch (e) {
      UI.toast('Error al descubrir riesgos: ' + (e.message || ''), 'error');
    }
    if (dBtn) { dBtn.disabled = false; dBtn.textContent = 'Descubrir con IA'; }
  },

  // ── Sección de encuestas distribuidas ─────────────────────────────────────

  async renderSurveySection(risk, container) {
    const canEdit = Auth.canEdit();
    let campaigns = [];
    try { campaigns = await Api.get('/api/surveys/campaigns'); } catch (_) {}
    const related = campaigns.filter(c => (c.scope_risk_ids || []).includes(risk.id));

    const surveySummary = (risk.survey_response_count > 0)
      ? `<div style="margin-top:8px;padding:10px 12px;background:#e8f5e9;border-radius:8px;font-size:13px;color:#2e7d32;">
           ${risk.survey_response_count} valoración(es) externas integradas en este riesgo.
           Última: ${risk.last_survey_date ? risk.last_survey_date.slice(0, 10) : 'desconocida'}
         </div>` : '';

    const campaignsHtml = related.length === 0
      ? `<div class="notice notice-info" style="font-size:13px;">
           Sin encuestas enviadas para este riesgo. Pulsa "Nueva encuesta" para solicitar la valoración de los responsables de área.
         </div>`
      : related.map(c => {
          const statusBadge = c.status === 'active' ? 'badge-purple'
            : c.status === 'closed' ? 'badge-low' : 'badge-muted';
          const applyBtn = (c.status === 'closed' && c.completed_responses > 0 && canEdit)
            ? `<button class="btn btn-ghost btn-sm" style="color:var(--success)"
                       data-apply-campaign="${c.id}" title="Aplicar al registro de riesgos">
                 Aplicar
               </button>` : '';
          return `<div class="card" style="padding:14px;margin-bottom:8px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;">
              <div>
                <code style="font-size:11px;">${UI.esc(c.code)}</code>
                <strong style="font-size:14px;margin-left:6px;">${UI.esc(c.title)}</strong>
                <div style="margin-top:4px;display:flex;gap:6px;flex-wrap:wrap;">
                  <span class="badge ${statusBadge}">${c.status}</span>
                  <span style="font-size:12px;color:var(--text-muted);">
                    ${c.completed_responses}/${c.total_respondents} respuestas (${c.response_rate}%)
                  </span>
                </div>
              </div>
              <div style="display:flex;gap:4px;">
                <button class="btn btn-ghost btn-sm" data-survey-results="${c.id}" title="Ver resultados">
                  Resultados
                </button>
                ${applyBtn}
              </div>
            </div>
          </div>`;
        }).join('');

    container.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <div>
          <h4 style="margin:0;font-size:14px;">Evaluaciones distribuidas</h4>
          <p style="margin:2px 0 0;font-size:12px;color:var(--text-muted);">
            Encuestas enviadas a responsables de área sobre este riesgo
          </p>
        </div>
        ${canEdit ? `<button class="btn btn-primary btn-sm" id="btn-new-survey-risk">Nueva encuesta</button>` : ''}
      </div>
      ${campaignsHtml}
      ${surveySummary}
    `;

    if (canEdit) {
      const newBtn = container.querySelector('#btn-new-survey-risk');
      if (newBtn) newBtn.onclick = () => ViewRisks._modalNewSurveyForRisk(risk);
    }

    container.querySelectorAll('[data-survey-results]').forEach(btn => {
      btn.onclick = () => ViewRisks._openSurveyResults(parseInt(btn.dataset.surveyResults));
    });
    container.querySelectorAll('[data-apply-campaign]').forEach(btn => {
      btn.onclick = () => ViewRisks._applySurveyToRisk(parseInt(btn.dataset.applyCampaign));
    });
  },

  async _modalNewSurveyForRisk(risk) {
    let templates = [];
    try { templates = await Api.get('/api/surveys/templates'); } catch (_) {}

    const defaultTemplate = templates.find(t => t.survey_type === 'risk_assessment' && t.is_default) || templates[0];
    const templateOptions = templates.map(t =>
      `<option value="${t.id}" ${defaultTemplate && t.id === defaultTemplate.id ? 'selected' : ''}>${UI.esc(t.name)}</option>`
    ).join('');

    const deadlineDefault = new Date(Date.now() + 14 * 86400000).toISOString().slice(0, 10);

    const modal = document.createElement('div');
    modal.className = 'modal-overlay active';
    modal.innerHTML = `
      <div class="modal" style="max-width:560px;width:100%;">
        <div class="modal-header">
          <h3 class="modal-title">Nueva encuesta para ${UI.esc(risk.name)}</h3>
          <button class="modal-close" id="modal-close-survey">&times;</button>
        </div>
        <div class="modal-body" style="max-height:70vh;overflow-y:auto;">
          <div class="form-group">
            <label class="form-label">Título de la campaña</label>
            <input type="text" id="srv-title" class="form-control"
                   value="${UI.esc(t('risks.survey_default_title', { name: risk.name.slice(0, 60) }))}">
          </div>
          <div class="form-group">
            <label class="form-label">Plantilla</label>
            <select id="srv-template" class="form-control">${templateOptions}</select>
          </div>
          <div class="form-group">
            <label class="form-label">Fecha límite</label>
            <input type="date" id="srv-deadline" class="form-control" value="${deadlineDefault}">
          </div>
          <div class="form-group">
            <label class="form-label">Texto de introducción (opcional)</label>
            <textarea id="srv-intro" class="form-control" rows="2" placeholder="Contexto adicional para el destinatario..."></textarea>
          </div>
          <div class="form-group">
            <label class="form-label" style="font-weight:700;margin-bottom:8px;">
              Destinatarios <span id="srv-respondent-count" style="font-weight:400;color:var(--text-muted);">(0)</span>
            </label>
            <div id="srv-respondents-list"></div>
            <button type="button" class="btn btn-ghost btn-sm" id="btn-add-respondent" style="margin-top:8px;">
              + Añadir destinatario
            </button>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" id="btn-srv-cancel">Cancelar</button>
          <button class="btn btn-primary" id="btn-srv-send">Enviar encuesta</button>
        </div>
      </div>`;
    document.body.appendChild(modal);

    const close = () => modal.remove();
    modal.querySelector('#modal-close-survey').onclick = close;
    modal.querySelector('#btn-srv-cancel').onclick = close;
    modal.onclick = e => { if (e.target === modal) close(); };

    const respondentsList = modal.querySelector('#srv-respondents-list');
    const countLabel = modal.querySelector('#srv-respondent-count');
    const respondents = [];

    const renderRespondents = () => {
      countLabel.textContent = `(${respondents.length})`;
      respondentsList.innerHTML = respondents.map((r, i) => `
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px;flex-wrap:wrap;">
          <input type="text" placeholder="Nombre" value="${UI.esc(r.name)}" data-ri="${i}" data-field="name"
                 class="form-control srv-r-field" style="flex:2;min-width:120px;">
          <input type="email" placeholder="Email" value="${UI.esc(r.email)}" data-ri="${i}" data-field="email"
                 class="form-control srv-r-field" style="flex:2;min-width:140px;">
          <input type="text" placeholder="Rol (opcional)" value="${UI.esc(r.role || '')}" data-ri="${i}" data-field="role"
                 class="form-control srv-r-field" style="flex:1;min-width:100px;">
          <button type="button" class="btn btn-ghost btn-sm" data-del="${i}" style="color:var(--danger);">×</button>
        </div>`).join('');
      respondentsList.querySelectorAll('.srv-r-field').forEach(inp => {
        inp.oninput = () => { respondents[inp.dataset.ri][inp.dataset.field] = inp.value; };
      });
      respondentsList.querySelectorAll('[data-del]').forEach(btn => {
        btn.onclick = () => { respondents.splice(parseInt(btn.dataset.del), 1); renderRespondents(); };
      });
    };

    modal.querySelector('#btn-add-respondent').onclick = () => {
      respondents.push({ name: '', email: '', role: '' });
      renderRespondents();
    };

    modal.querySelector('#btn-srv-send').onclick = async () => {
      const title = modal.querySelector('#srv-title').value.trim();
      const templateId = parseInt(modal.querySelector('#srv-template').value);
      const deadlineVal = modal.querySelector('#srv-deadline').value;
      const intro = modal.querySelector('#srv-intro').value.trim();

      if (!title) { alert('El título es obligatorio.'); return; }
      const validRespondents = respondents.filter(r => r.name && r.email);
      if (validRespondents.length === 0) { alert('Añade al menos un destinatario con nombre y email.'); return; }

      const deadlineDays = deadlineVal
        ? Math.max(1, Math.round((new Date(deadlineVal) - Date.now()) / 86400000))
        : 14;

      const sendBtn = modal.querySelector('#btn-srv-send');
      sendBtn.disabled = true;
      sendBtn.textContent = 'Creando...';

      try {
        const campaign = await Api.post('/api/surveys/campaigns', {
          title, template_id: templateId, scope_risk_ids: [risk.id],
          deadline_days: deadlineDays, intro_text: intro || null,
          show_risk_context: true, allow_comments: true,
        });
        await Api.post(`/api/surveys/campaigns/${campaign.id}/respondents`, {
          respondents: validRespondents.map(r => ({ name: r.name, email: r.email, role: r.role || null })),
        });
        const result = await Api.post(`/api/surveys/campaigns/${campaign.id}/send`, {});
        close();
        UI.toast(`Encuesta creada y ${result.sent || 0} email(s) enviado(s).`, 'success');
        window.dispatchEvent(new Event('risks-updated'));
      } catch (e) {
        sendBtn.disabled = false;
        sendBtn.textContent = 'Enviar encuesta';
        alert('Error: ' + (e.message || 'No se pudo crear la encuesta.'));
      }
    };
  },

  async _openSurveyResults(campaignId) {
    let results;
    try { results = await Api.get(`/api/surveys/campaigns/${campaignId}/results`); } catch (e) {
      alert('No se pudieron cargar los resultados.'); return;
    }

    const questionsHtml = (results.questions || []).map(q => {
      let vizHtml = '';
      if (q.distribution) {
        const entries = Object.entries(q.distribution).sort((a, b) => b[1] - a[1]);
        const max = Math.max(...entries.map(e => e[1]), 1);
        vizHtml = '<div style="margin-top:8px;">' + entries.map(([val, count]) =>
          `<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;font-size:12px;">
             <span style="width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${UI.esc(val)}">${UI.esc(val)}</span>
             <div style="flex:1;background:#eeeef5;border-radius:4px;height:14px;">
               <div style="width:${Math.round(count/max*100)}%;height:100%;background:var(--brand-purple);border-radius:4px;"></div>
             </div>
             <span style="min-width:24px;text-align:right;">${count}</span>
           </div>`
        ).join('') + '</div>';
      }
      const avgHtml = q.average !== undefined
        ? `<span style="font-size:12px;color:var(--text-muted);"> — promedio: <strong>${q.average}</strong></span>` : '';
      return `<div style="margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid #eeeef5;">
        <div style="font-size:13px;font-weight:600;">${UI.esc(q.question_text || '')}</div>
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">${q.response_count} respuesta(s)${avgHtml}</div>
        ${vizHtml}
        ${(q.comments || []).length ? `<div style="margin-top:6px;font-size:12px;color:var(--text-muted);">
          ${q.comments.map(c => `<div style="margin-bottom:2px;">"${UI.esc(c)}"</div>`).join('')}
        </div>` : ''}
      </div>`;
    }).join('');

    const commentsHtml = (results.general_comments || []).length
      ? `<div style="margin-top:12px;">
           <strong style="font-size:12px;">Comentarios generales:</strong>
           ${results.general_comments.map(c => `<div style="font-size:13px;padding:6px 0;border-bottom:1px solid #eeeef5;">"${UI.esc(c)}"</div>`).join('')}
         </div>` : '';

    const modal = document.createElement('div');
    modal.className = 'modal-overlay active';
    modal.innerHTML = `
      <div class="modal" style="max-width:600px;width:100%;">
        <div class="modal-header">
          <h3 class="modal-title">${UI.esc(results.title)} — Resultados</h3>
          <button class="modal-close" id="srv-res-close">&times;</button>
        </div>
        <div class="modal-body" style="max-height:75vh;overflow-y:auto;">
          <div style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap;">
            <div style="text-align:center;padding:12px 20px;background:#f5f5fa;border-radius:8px;">
              <div style="font-size:24px;font-weight:700;color:var(--brand-purple);">${results.response_rate}%</div>
              <div style="font-size:11px;color:var(--text-muted);">Tasa de respuesta</div>
            </div>
            <div style="text-align:center;padding:12px 20px;background:#f5f5fa;border-radius:8px;">
              <div style="font-size:24px;font-weight:700;">${results.completed}/${results.total_respondents}</div>
              <div style="font-size:11px;color:var(--text-muted);">Completadas</div>
            </div>
          </div>
          ${questionsHtml}
          ${commentsHtml}
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" id="srv-res-close2">Cerrar</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
    const close = () => modal.remove();
    modal.querySelector('#srv-res-close').onclick = close;
    modal.querySelector('#srv-res-close2').onclick = close;
    modal.onclick = e => { if (e.target === modal) close(); };
  },

  async _applySurveyToRisk(campaignId) {
    let result;
    try { result = await Api.post(`/api/surveys/campaigns/${campaignId}/apply-to-risks`, {}); }
    catch (e) { alert('Error al aplicar: ' + (e.message || '')); return; }

    if (!result.changes || result.changes.length === 0) {
      alert('No hay cambios a aplicar (ya aplicados o sin respuestas nuevas).'); return;
    }
    const msg = result.changes.map(c =>
      `- ${c.risk_code}: Probabilidad ${c.likelihood_before} → ${c.likelihood_after}, Impacto ${c.impact_before} → ${c.impact_after}`
    ).join('\n');
    const n = result.changes[0]?.responses_count || 0;
    if (confirm(`Se aplicarán los siguientes cambios basados en ${n} respuesta(s):\n\n${msg}\n\n¿Confirmar?`)) {
      UI.toast('Valoraciones aplicadas al registro de riesgos.', 'success');
      window.dispatchEvent(new Event('risks-updated'));
    }
  },
};
