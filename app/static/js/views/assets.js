/* Vista Activos: CRUD + import/export + análisis IA + agrupación IA. */
const ViewAssets = {
  _sortCol: 'code', _sortAsc: true,
  _pollTimer: null,
  _groupPollTimer: null,
  _activeTab: 'inventory',
  _page: 1,
  _pageSize: 50,
  _allAssets: [],
  _selectedIds: new Set(),

  async render(main) {
    ViewAssets._stopPoll();
    if (ViewAssets._groupPollTimer) { clearInterval(ViewAssets._groupPollTimer); ViewAssets._groupPollTimer = null; }
    ViewAssets._activeTab = 'inventory';
    ViewAssets._page = 1;
    ViewAssets._allAssets = [];
    ViewAssets._selectedIds = new Set();
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      t('assets.title'),
      t('assets.subtitle'),
      canEdit ? `
        <span id="inv-actions">
          <button class="btn" id="btn-export">${t('common.export')} CSV</button>
          <button class="btn" id="btn-template">${t('assets.template_btn')}</button>
          <label class="btn" id="lbl-import" title="Acepta cualquier formato: CSV, XLSX, JSON, etc. La IA normaliza las columnas automáticamente">
            ${t('common.import')} (${t('common.all')})
            <input type="file" id="file-import" accept="*" multiple style="display:none;">
          </label>
          <button class="btn btn-ghost" id="btn-analyze-pending"
                  title="${t('assets.hint_analyze_pending')}">
            ${t('assets.analyze_pending')}
          </button>
          <button class="btn btn-ghost" id="btn-analyze-cia"
                  title="${t('assets.hint_analyze_ens')}">
            ${t('assets.estimate_ens')}
          </button>
          <button class="btn btn-ghost" id="btn-analyze-all"
                  title="${t('assets.hint_analyze_all')}">
            ${t('assets.reanalyze_all')}
          </button>
          <button class="btn btn-primary" id="btn-new">+ ${t('assets.new')}</button>
        </span>
      ` : ''
    ) + `
      <div style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:16px;">
        <button class="asset-tab active" data-tab="inventory"
          style="padding:8px 18px;border:none;background:none;cursor:pointer;font-size:14px;
                 font-weight:600;color:var(--brand-purple);
                 border-bottom:3px solid var(--brand-purple);margin-bottom:-2px;">
          ${t('assets.inventory_tab')}
        </button>
        <button class="asset-tab" data-tab="groups-results"
          style="padding:8px 18px;border:none;background:none;cursor:pointer;font-size:14px;
                 font-weight:600;color:var(--text-muted);
                 border-bottom:3px solid transparent;margin-bottom:-2px;">
          ${t('assets.groups_tab')}
        </button>
        <button class="asset-tab" data-tab="grouping"
          style="padding:8px 18px;border:none;background:none;cursor:pointer;font-size:14px;
                 font-weight:600;color:var(--text-muted);
                 border-bottom:3px solid transparent;margin-bottom:-2px;">
          ${t('assets.ai_grouping')}
        </button>
      </div>
      <div id="tab-inventory">
        <div class="toolbar">
          <input type="search" id="asset-search" placeholder="${t('common.search')}...">
          <select id="asset-type-filter">
            <option value="">${t('common.all')}</option>
            <option value="primary_process">${t('assets.type.primary')}</option>
            <option value="primary_information">${t('assets.type.information')}</option>
            <option value="support_hardware">${t('assets.type.hardware')}</option>
            <option value="support_software">${t('assets.type.software')}</option>
            <option value="support_network">${t('assets.type.support_network')}</option>
            <option value="support_personnel">${t('assets.type.people')}</option>
            <option value="support_site">${t('assets.type.facilities')}</option>
            <option value="support_organization">${t('assets.type.support_organization')}</option>
          </select>
          <span class="spacer"></span>
          <span id="asset-count" style="color:var(--text-subtle);font-size:12px;"></span>
        </div>
        <div id="asset-list"></div>
      </div>
      <div id="tab-groups-results" style="display:none;padding:4px 0;"></div>
      <div id="tab-grouping" style="display:none;">
        <div id="grouping-view"><div class="notice">Cargando...</div></div>
      </div>
    `;

    // Tab switching
    main.querySelectorAll('.asset-tab').forEach(btn => {
      btn.onclick = () => {
        main.querySelectorAll('.asset-tab').forEach(b => {
          b.style.color = 'var(--text-muted)';
          b.style.borderBottomColor = 'transparent';
        });
        btn.style.color = 'var(--brand-purple)';
        btn.style.borderBottomColor = 'var(--brand-purple)';
        const tab = btn.dataset.tab;
        ViewAssets._activeTab = tab;
        document.getElementById('tab-inventory').style.display       = tab === 'inventory'       ? '' : 'none';
        document.getElementById('tab-groups-results').style.display  = tab === 'groups-results'  ? '' : 'none';
        document.getElementById('tab-grouping').style.display        = tab === 'grouping'        ? '' : 'none';
        const invActions = document.getElementById('inv-actions');
        if (invActions) invActions.style.display = tab === 'inventory' ? '' : 'none';
        if (tab !== 'inventory') {
          ViewAssets._selectedIds.clear();
          const bar = document.getElementById('asset-selection-bar');
          if (bar) bar.remove();
        }
        if (tab === 'grouping')       ViewAssets._renderGrouping();
        if (tab === 'groups-results') ViewAssets._renderGroupsResults();
        if (tab === 'inventory')      ViewAssets._reload();
      };
    });

    document.getElementById('asset-search').oninput = () => {
      ViewAssets._page = 1;
      ViewAssets._applyFiltersAndRender();
    };
    document.getElementById('asset-type-filter').onchange = () => {
      ViewAssets._page = 1;
      ViewAssets._applyFiltersAndRender();
    };

    if (canEdit) {
      document.getElementById('btn-new').onclick = () => ViewAssets._edit();
      document.getElementById('btn-template').onclick = () => Api.assets.template();
      document.getElementById('btn-export').onclick = () => Api.assets.exportCsv();
      document.getElementById('file-import').onchange = async (e) => {
        const files = Array.from(e.target.files);
        if (!files.length) return;
        await ViewAssets._importFiles(files);
        e.target.value = '';
      };
      ViewAssets._setupDrop(main);

      // Confirmación con coste estimado antes de lanzar un análisis masivo:
      // cuantos activos van de verdad (los grupos validados cubren miembros),
      // con que modelos y el coste aproximado en la API de IA.
      async function _confirmWithCost(prefix) {
        let est = null;
        try { est = await Api.assets.costEstimate(); } catch (e) { /* sin estimacion */ }
        if (!est) return UI.confirm(prefix);
        const lines = [
          prefix, '',
          t('assets.will_analyze_n', {n: est.to_analyze}) +
            (est.covered_by_groups ? ` (${est.covered_by_groups} más quedan cubiertos por sus grupos validados)` : ''),
          `Modelos: ${est.normal} con ${est.model_fast}, ${est.critical} críticos con ${est.model_deep}`,
          `Coste estimado en la API de IA: ~$${est.estimated_cost_usd} USD` +
            (est.uses_batch_api ? ' (con descuento del 50% por proceso en lote)' : ''),
        ];
        return UI.confirm(lines.join('\n'));
      }

      const btnPending = document.getElementById('btn-analyze-pending');
      if (btnPending) {
        btnPending.onclick = async () => {
          if (!await _confirmWithCost(t('assets.confirm_analyze_pending'))) return;
          btnPending.disabled = true;
          btnPending.textContent = 'Lanzando...';
          try {
            // reset-stuck resetea atascados y lanza pendientes en una sola llamada
            const r = await Api.assets.resetStuck();
            if (r.pending === 0 && r.stuck_reset === 0) {
              UI.toast(t('assets.all_analyzed'), 'info');
            } else {
              const stuckMsg = r.stuck_reset > 0 ? ` (${r.stuck_reset} atascados reseteados)` : '';
              UI.toast(
                t('assets.analysis_started', {n: r.pending, extra: stuckMsg}),
                'success', 6000
              );
            }
            ViewAssets._reload();
            ViewAssets._startPollIfNeeded();
          } catch (e) {
            UI.toast('Error: ' + e.message, 'error');
          } finally {
            btnPending.disabled = false;
            btnPending.textContent = t('assets.btn_analyze_pending');
          }
        };
      }

      const btnCia = document.getElementById('btn-analyze-cia');
      if (btnCia) {
        btnCia.onclick = async () => {
          btnCia.disabled = true;
          btnCia.textContent = 'Lanzando...';
          try {
            const r = await Api.assets.analyzeCiaZero();
            if (r.total === 0) {
              UI.toast(t('assets.all_ens_valued'), 'info');
            } else {
              UI.toast(`${r.total} activos con dimensiones ENS a 0 — análisis lanzado. La IA estimará C, I, D, Autenticidad y Trazabilidad.`, 'success', 6000);
              ViewAssets._reload();
              ViewAssets._startPollIfNeeded();
            }
          } catch (e) {
            UI.toast('Error: ' + e.message, 'error');
          } finally {
            btnCia.disabled = false;
            btnCia.textContent = 'Estimar dimensiones ENS';
          }
        };
      }

      const btnAnalyzeAll = document.getElementById('btn-analyze-all');
      if (btnAnalyzeAll) {
        btnAnalyzeAll.onclick = async () => {
          const status = await Api.assets.analysisStatus().catch(() => null);
          const total = status ? status.total : '?';
          if (!await _confirmWithCost(
            `¿Re-analizar TODOS los activos (${total}) con IA?\n\nEsto resetea el análisis existente y relanza todos desde cero (el coste estimado crecerá en consecuencia).`
          )) return;
          btnAnalyzeAll.disabled = true;
          btnAnalyzeAll.textContent = 'Iniciando...';
          try {
            const r = await Api.assets.analyzeAllForce();
            UI.toast(t('assets.forced_analysis_started', {n: r.total}), 'success');
            ViewAssets._reload();
            ViewAssets._startPollIfNeeded();
          } catch (e) {
            UI.toast('Error: ' + e.message, 'error');
          } finally {
            btnAnalyzeAll.disabled = false;
            btnAnalyzeAll.textContent = t('assets.btn_reanalyze_all');
          }
        };
      }
    }

    ViewAssets._reload();

    // Detener el poll y limpiar la barra de selección cuando el usuario navegue fuera de esta seccion
    const _viewCleanupObserver = new MutationObserver(() => {
      if (!document.getElementById('asset-list')) {
        ViewAssets._stopPoll();
        if (ViewAssets._groupPollTimer) { clearInterval(ViewAssets._groupPollTimer); ViewAssets._groupPollTimer = null; }
        document.getElementById('asset-selection-bar')?.remove();
        _viewCleanupObserver.disconnect();
      }
    });
    _viewCleanupObserver.observe(document.getElementById('main') || document.body, { childList: true });
  },

  // ---------- INVENTARIO PAGINADO ----------

  async _reload() {
    const list = document.getElementById('asset-list');
    if (!list) return;
    list.innerHTML = `<div class="notice">${t('common.loading')}</div>`;
    try {
      const data = await Api.assets.list({ limit: 10000 });
      ViewAssets._allAssets = data;
      ViewAssets._page = 1;
      ViewAssets._applyFiltersAndRender();
      // Mostrar banner si ya hay errores de créditos
      const hasCredit = data.some(a =>
        a.ai_risk_status === 'error' &&
        (a.ai_risk_summary?.error || '').toLowerCase().includes('credito')
      );
      if (hasCredit) ViewAssets._showCreditBanner();
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _applyFiltersAndRender() {
    const list = document.getElementById('asset-list');
    if (!list) return;
    const q = (document.getElementById('asset-search')?.value || '').toLowerCase();
    const typeFilter = document.getElementById('asset-type-filter')?.value || '';

    let data = ViewAssets._allAssets;
    if (q) data = data.filter(a =>
      (a.name || '').toLowerCase().includes(q) ||
      (a.code || '').toLowerCase().includes(q) ||
      (a.description || '').toLowerCase().includes(q)
    );
    if (typeFilter) data = data.filter(a => a.asset_type === typeFilter);

    const _sortVal = a => {
      const k = ViewAssets._sortCol;
      if (k === 'code')      return a.code || '';
      if (k === 'name')      return (a.name || '').toLowerCase();
      if (k === 'type')      return a.asset_type || '';
      if (k === 'value_max') return a.value_max || 0;
      if (k === 'risks')     return a.risk_count || 0;
      if (k === 'category')  return (a.category || '').toLowerCase();
      return '';
    };
    data.sort((a, b) => {
      const va = _sortVal(a), vb = _sortVal(b);
      const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
      return ViewAssets._sortAsc ? cmp : -cmp;
    });

    const total      = data.length;
    const ps         = ViewAssets._pageSize;
    const totalPages = Math.max(1, Math.ceil(total / ps));
    if (ViewAssets._page > totalPages) ViewAssets._page = totalPages;
    if (ViewAssets._page < 1)          ViewAssets._page = 1;
    const start    = (ViewAssets._page - 1) * ps;
    const pageData = data.slice(start, start + ps);

    const countEl = document.getElementById('asset-count');
    if (countEl) {
      countEl.textContent = total > ps
        ? t('assets.range_of_assets', {from: start + 1, to: Math.min(start + ps, total), total: total})
        : t('assets.n_assets', {n: total});
    }

    // Banner de estado de análisis IA
    ViewAssets._updateAnalysisBanner();

    if (!total) {
      list.innerHTML = UI.emptyState(t('common.no_results'), t('assets.new'));
      return;
    }

    ViewAssets._renderTableContent(list, pageData, total, totalPages);
    ViewAssets._startPollIfNeeded();
  },

  _renderTableContent(list, pageData, total, totalPages) {
    const ps   = ViewAssets._pageSize;
    const page = ViewAssets._page;

    const _th = (col, label, title, style) => {
      const active = ViewAssets._sortCol === col;
      const arrow  = active ? (ViewAssets._sortAsc ? ' ▲' : ' ▼') : '';
      return `<th style="cursor:pointer;user-select:none;white-space:nowrap;${active ? 'color:var(--brand-purple);' : ''}${style || ''}"
                  data-sort="${col}" title="${title || label}">${label}${arrow}</th>`;
    };

    const _aiStatusBadge = (a) => {
      const s = a.ai_risk_status;
      if (!s) return `<span style="font-size:10px;color:var(--text-subtle);">-</span>`;
      const colors = { analysing: 'var(--brand-orange)', analysed: 'var(--risk-low)', error: 'var(--risk-critical)', skipped: 'var(--text-muted)' };
      const labels = { analysing: t('assets.st_analysing'), analysed: t('assets.st_analysed'), error: 'Error', skipped: t('assets.st_no_ai') };
      const sum = a.ai_risk_summary || {};
      const tip = s === 'analysed'
        ? t('assets.created_updated', {c: sum.risks_created || 0, u: sum.risks_updated || 0})
        : (sum.error || sum.reason || '');
      return `<span style="font-size:10px;font-weight:600;color:${colors[s] || 'var(--text-muted)'};"
                    title="${UI.esc(tip)}">${labels[s] || s}</span>`;
    };

    const _groupBadge = (a) => {
      if (!a.group_id) return '';
      return `<span style="font-size:10px;background:var(--brand-purple);color:#fff;
                           padding:2px 6px;border-radius:10px;font-weight:600;"
                    title="${t('assets.belongs_to_group')}">GRP</span> `;
    };

    const allPageIds = pageData.map(a => a.id);
    const allPageSelected = allPageIds.length > 0 && allPageIds.every(id => ViewAssets._selectedIds.has(id));

    list.innerHTML = `<div class="table-wrap"><table class="data">
      <thead>
        <tr>
          <th style="width:32px;padding:4px 6px;" onclick="event.stopPropagation()">
            <input type="checkbox" id="chk-all" ${allPageSelected ? 'checked' : ''}
                   style="accent-color:var(--brand-purple);cursor:pointer;"
                   title="${t('assets.select_all_page')}">
          </th>
          ${_th('code', t('risks.risk_code'))}${_th('name', t('common.name'))}${_th('type', t('common.type'))}
          <th title="${t('assets.confidentiality')}">C</th>
          <th title="${t('assets.integrity')}">I</th>
          <th title="${t('assets.availability')}">D</th>
          <th title="${t('assets.confidentiality')} (ENS Annex I)" style="color:var(--brand-orange)">Au</th>
          <th title="Trazabilidad (ENS Annex I)" style="color:var(--brand-orange)">Tr</th>
          ${_th('value_max', 'Max', t('assets.asset_value'))}
          ${_th('category', t('common.category'))}
          ${_th('risks', t('common.risk'), t('assets.linked_risks'), 'width:70px;text-align:center;')}
          <th style="white-space:nowrap;">${t('common.analyze')} IA</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        ${pageData.map(a => {
          const rc      = a.risk_count || 0;
          const rcColor = rc === 0 ? 'var(--text-subtle)' : rc >= 5 ? 'var(--risk-high)' : 'var(--brand-purple)';
          const checked = ViewAssets._selectedIds.has(a.id);
          return `
          <tr data-id="${a.id}" style="cursor:pointer;${checked ? 'background:var(--bg-3);' : ''}">
            <td style="padding:4px 6px;" onclick="event.stopPropagation()">
              <input type="checkbox" class="row-chk" data-id="${a.id}" ${checked ? 'checked' : ''}
                     style="accent-color:var(--brand-purple);cursor:pointer;">
            </td>
            <td>${UI.codePill(a.code)}</td>
            <td><strong>${_groupBadge(a)}${UI.esc(a.name)}</strong>
                ${a.description ? `<div style="font-size:11px;color:var(--text-subtle);">${UI.esc(a.description).slice(0, 80)}</div>` : ''}</td>
            <td>${UI.assetTypeLabel(a.asset_type)}</td>
            <td>${a.value_confidentiality}</td>
            <td>${a.value_integrity}</td>
            <td>${a.value_availability}</td>
            <td>${a.value_authenticity}</td>
            <td>${a.value_accountability}</td>
            <td>${UI.riskPill(a.value_max * 2)}</td>
            <td>${UI.esc(a.category || '-')}</td>
            <td style="text-align:center;">
              <a href="#/risks?asset_id=${a.id}" title="${t('assets.view_asset_risks')}"
                 style="font-weight:700;font-family:var(--font-mono);font-size:13px;
                        color:${rcColor};text-decoration:none;">${rc}</a>
            </td>
            <td style="white-space:nowrap;" onclick="event.stopPropagation()">
              ${_aiStatusBadge(a)}
            </td>
            <td style="white-space:nowrap;" onclick="event.stopPropagation()">
              ${Auth.canEdit() ? `<button class="btn btn-ghost" data-edit="${a.id}">${t('common.edit')}</button>` : ''}
              ${Auth.canEdit() && (!a.ai_risk_status || a.ai_risk_status === 'error' || a.ai_risk_status === 'skipped')
                ? `<button class="btn btn-ghost" style="font-size:11px;padding:2px 8px;"
                           data-analyze="${a.id}"
                           title="${t('assets.analyze_asset_ai')}">&#9881; IA</button>`
                : ''}
            </td>
          </tr>`;
        }).join('')}
      </tbody>
    </table></div>
    <div style="display:flex;align-items:center;gap:10px;padding:12px 2px;flex-wrap:wrap;border-top:1px solid var(--border);">
      <button class="btn btn-ghost" id="pg-first" ${page <= 1 ? 'disabled' : ''}
              style="padding:4px 10px;font-size:13px;">«</button>
      <button class="btn btn-ghost" id="pg-prev" ${page <= 1 ? 'disabled' : ''}
              style="padding:4px 12px;font-size:13px;">← ${t('common.previous')}</button>
      <span style="font-size:13px;color:var(--text-muted);white-space:nowrap;">
        ${page} ${t('common.of')} <strong>${totalPages}</strong>
      </span>
      <button class="btn btn-ghost" id="pg-next" ${page >= totalPages ? 'disabled' : ''}
              style="padding:4px 12px;font-size:13px;">${t('common.next')} →</button>
      <button class="btn btn-ghost" id="pg-last" ${page >= totalPages ? 'disabled' : ''}
              style="padding:4px 10px;font-size:13px;">»</button>
      <span style="flex:1;"></span>
      <label style="font-size:13px;color:var(--text-muted);display:flex;align-items:center;gap:6px;white-space:nowrap;">
        ${t('common.rows_per_page')}:
        <select id="page-size-sel"
                style="padding:4px 8px;border:1px solid var(--border);border-radius:4px;font-size:13px;background:var(--bg-2);">
          <option value="25"  ${ps ===  25 ? 'selected' : ''}>25</option>
          <option value="50"  ${ps ===  50 ? 'selected' : ''}>50</option>
          <option value="100" ${ps === 100 ? 'selected' : ''}>100</option>
          <option value="250" ${ps === 250 ? 'selected' : ''}>250</option>
        </select>
      </label>
    </div>`;

    // Checkbox: select all on page
    document.getElementById('chk-all')?.addEventListener('change', (e) => {
      allPageIds.forEach(id => {
        if (e.target.checked) ViewAssets._selectedIds.add(id);
        else ViewAssets._selectedIds.delete(id);
      });
      ViewAssets._applyFiltersAndRender();
    });

    // Checkbox: individual rows
    list.querySelectorAll('.row-chk').forEach(cb => {
      cb.addEventListener('change', (e) => {
        const id = parseInt(e.target.dataset.id);
        if (e.target.checked) ViewAssets._selectedIds.add(id);
        else ViewAssets._selectedIds.delete(id);
        ViewAssets._updateSelectionBar();
        // Highlight row
        const tr = e.target.closest('tr');
        if (tr) tr.style.background = e.target.checked ? 'var(--bg-3)' : '';
      });
    });

    // Show/hide selection bar
    ViewAssets._updateSelectionBar();

    // Sort
    list.querySelectorAll('th[data-sort]').forEach(th => {
      th.onclick = () => {
        const col = th.dataset.sort;
        if (ViewAssets._sortCol === col) ViewAssets._sortAsc = !ViewAssets._sortAsc;
        else { ViewAssets._sortCol = col; ViewAssets._sortAsc = col !== 'value_max' && col !== 'risks'; }
        ViewAssets._applyFiltersAndRender();
      };
    });

    // Row actions
    list.querySelectorAll('[data-edit]').forEach(b =>
      b.onclick = (e) => { e.stopPropagation(); ViewAssets._edit(parseInt(b.dataset.edit)); });
    list.querySelectorAll('[data-analyze]').forEach(b =>
      b.onclick = async (e) => {
        e.stopPropagation();
        const id = parseInt(b.dataset.analyze);
        b.disabled = true; b.textContent = '...';
        try {
          await Api.assets.analyze(id);
          UI.toast('Análisis IA iniciado', 'success');
          ViewAssets._reload();
          ViewAssets._startPollIfNeeded();
        } catch (err) {
          UI.toast('Error: ' + err.message, 'error');
          b.disabled = false; b.textContent = '⚙ IA';
        }
      });
    list.querySelectorAll('tr[data-id]').forEach(tr =>
      tr.onclick = () => ViewAssets._edit(parseInt(tr.dataset.id)));

    // Pagination
    const _getFilteredTotal = () => {
      const q = (document.getElementById('asset-search')?.value || '').toLowerCase();
      const typeFilter = document.getElementById('asset-type-filter')?.value || '';
      let d = ViewAssets._allAssets;
      if (q) d = d.filter(a =>
        (a.name || '').toLowerCase().includes(q) ||
        (a.code || '').toLowerCase().includes(q) ||
        (a.description || '').toLowerCase().includes(q)
      );
      if (typeFilter) d = d.filter(a => a.asset_type === typeFilter);
      return d.length;
    };
    document.getElementById('pg-first')?.addEventListener('click', () => {
      ViewAssets._page = 1; ViewAssets._applyFiltersAndRender();
    });
    document.getElementById('pg-prev')?.addEventListener('click', () => {
      if (ViewAssets._page > 1) { ViewAssets._page--; ViewAssets._applyFiltersAndRender(); }
    });
    document.getElementById('pg-next')?.addEventListener('click', () => {
      const tp = Math.max(1, Math.ceil(_getFilteredTotal() / ViewAssets._pageSize));
      if (ViewAssets._page < tp) { ViewAssets._page++; ViewAssets._applyFiltersAndRender(); }
    });
    document.getElementById('pg-last')?.addEventListener('click', () => {
      ViewAssets._page = Math.max(1, Math.ceil(_getFilteredTotal() / ViewAssets._pageSize));
      ViewAssets._applyFiltersAndRender();
    });
    document.getElementById('page-size-sel')?.addEventListener('change', (e) => {
      ViewAssets._pageSize = parseInt(e.target.value);
      ViewAssets._page = 1;
      ViewAssets._applyFiltersAndRender();
    });
  },

  async _updateAnalysisBanner() {
    const listEl = document.getElementById('asset-list');
    if (!listEl) return;

    let banner = document.getElementById('analysis-status-banner');

    try {
      const s = await Api.assets.analysisStatus();
      const pending   = (s.total || 0) - (s.analysed || 0) - (s.skipped || 0);
      const hasError  = (s.error || 0) > 0;
      const inProgress = (s.analysing || 0) > 0;
      const pct = s.progress_pct || 0;

      if (!banner) {
        banner = document.createElement('div');
        banner.id = 'analysis-status-banner';
        listEl.parentNode.insertBefore(banner, listEl);
      }

      if (s.total === 0) { banner.innerHTML = ''; return; }

      if (inProgress) {
        const barWidth = Math.max(4, Math.round(pct));
        banner.innerHTML = `
          <div style="background:#FFF7ED;border:1px solid #FED7AA;border-radius:8px;
                      padding:12px 16px;margin-bottom:10px;font-size:13px;">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
              <div class="spinner" style="width:16px;height:16px;border-width:2px;flex-shrink:0;border-color:rgba(146,64,14,.3);border-top-color:#92400E;"></div>
              <span style="color:#92400E;font-weight:600;">
                Analizando activos en paralelo (lotes de 15, 8 simultáneos)...
              </span>
              <span style="margin-left:auto;color:#92400E;font-weight:700;">
                ${s.analysed} / ${s.total} (${pct}%)
              </span>
            </div>
            <div style="height:6px;background:#FED7AA;border-radius:3px;overflow:hidden;">
              <div style="width:${barWidth}%;height:100%;background:#D97706;border-radius:3px;transition:width .5s;"></div>
            </div>
            <div style="margin-top:6px;font-size:11px;color:#92400E;">
              ${s.analysing} en curso · ${s.error || 0} errores ·
              ${(s.total - s.analysed - s.analysing - (s.error||0) - (s.skipped||0))} pendientes
            </div>
          </div>`;
      } else if (pending > 0 || hasError) {
        banner.innerHTML = `
          <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;
                      padding:8px 14px;margin-bottom:10px;display:flex;align-items:center;
                      gap:12px;font-size:13px;flex-wrap:wrap;">
            <span style="color:#166534;">
              <strong>${s.analysed}</strong>/${s.total} analizados (${pct}%)
              ${hasError ? `&nbsp;·&nbsp;<span style="color:#dc2626;">${s.error} con error</span>` : ''}
              ${(s.total - s.analysed - s.skipped - s.error) > 0 ? `&nbsp;·&nbsp;<span style="color:#92400E;">${t('assets.unanalyzed_count', {n: s.total - s.analysed - s.skipped - s.error})}</span>` : ''}
            </span>
            <button class="btn btn-ghost" id="banner-analyze-pending"
                    style="font-size:12px;padding:3px 10px;margin-left:auto;"
                    onclick="document.getElementById('btn-analyze-pending')?.click()">
              Analizar ${pending} pendientes
            </button>
          </div>`;
      } else if (s.analysed === s.total) {
        banner.innerHTML = `
          <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;
                      padding:8px 14px;margin-bottom:10px;font-size:13px;color:#166534;">
            Todos los activos analizados (${s.total}/${s.total}, ${pct}%)
          </div>`;
        // Auto-ocultar tras 5s si todo ok
        setTimeout(() => { if (banner) banner.innerHTML = ''; }, 5000);
      }
    } catch (_) {
      if (banner) banner.innerHTML = '';
    }
  },

  _updateSelectionBar() {
    const n = ViewAssets._selectedIds.size;
    let bar = document.getElementById('asset-selection-bar');

    if (n === 0) {
      if (bar) bar.remove();
      return;
    }

    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'asset-selection-bar';
      bar.style.cssText = `
        position:fixed;bottom:0;left:0;right:0;z-index:1000;
        background:var(--brand-purple);color:#fff;
        padding:12px 24px;display:flex;align-items:center;gap:16px;
        box-shadow:0 -4px 16px rgba(0,0,0,.2);`;
      document.body.appendChild(bar);
    }

    bar.innerHTML = `
      <span style="font-size:14px;font-weight:700;">
        ${n} ${t('common.asset')}${n !== 1 ? 's' : ''} ${t('common.select')}
      </span>
      <button id="sel-deselect" class="btn"
              style="background:rgba(255,255,255,.2);color:#fff;border-color:rgba(255,255,255,.3);
                     font-size:13px;padding:4px 14px;">
        ${t('common.clear')}
      </button>
      <span style="flex:1;"></span>
      <button id="sel-delete" class="btn"
              style="background:#dc2626;color:#fff;border-color:#dc2626;
                     font-size:13px;padding:6px 18px;font-weight:700;">
        ${t('common.delete')} ${n} ${t('common.asset')}${n !== 1 ? 's' : ''}
      </button>`;

    document.getElementById('sel-deselect').onclick = () => {
      ViewAssets._selectedIds.clear();
      ViewAssets._applyFiltersAndRender();
    };
    document.getElementById('sel-delete').onclick = () => ViewAssets._bulkDelete();
  },

  async _bulkDelete() {
    const ids = [...ViewAssets._selectedIds];
    if (!ids.length) return;
    const ok = await UI.confirm(
      t('assets.confirm_delete_assets', {n: ids.length})
    );
    if (!ok) return;
    const btn = document.getElementById('sel-delete');
    if (btn) { btn.disabled = true; btn.textContent = 'Eliminando...'; }
    try {
      const r = await Api.assets.bulkDelete(ids);
      UI.toast(t('assets.assets_deleted', {n: r.deleted}), 'success');
      ViewAssets._selectedIds.clear();
      await ViewAssets._reload();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
      if (btn) { btn.disabled = false; btn.textContent = t('assets.btn_delete_n_assets', {n: ids.length}); }
    }
  },

  _startPollIfNeeded() {
    ViewAssets._stopPoll();
    // Arrancar poll si hay activos analizando (en cache) O si el servidor dice que hay en curso
    const hasAnalysing = ViewAssets._allAssets.some(a => a.ai_risk_status === 'analysing');
    // También arrancar si el banner muestra que hay pendientes/en-curso (detectado en banner)
    const bannerHasSpinner = document.getElementById('analysis-status-banner')?.innerHTML.includes('spinner');
    if (!hasAnalysing && !bannerHasSpinner) return;

    const colors = { analysing: 'var(--brand-orange)', analysed: 'var(--risk-low)', error: 'var(--risk-critical)', skipped: 'var(--text-muted)' };
    const labels = { analysing: 'Analizando...', analysed: 'Analizado', error: 'Error', skipped: 'Sin IA' };

    ViewAssets._pollTimer = setInterval(async () => {
      try {
        // Si el usuario navego a otra seccion, parar el poll limpiamente
        if (!document.getElementById('asset-list')) {
          ViewAssets._stopPoll();
          return;
        }
        const data = await Api.assets.list({ limit: 10000 });
        ViewAssets._allAssets = data;

        // Actualizar solo las celdas de estado IA en las filas visibles (sin re-render)
        data.forEach(a => {
          const tr = document.querySelector(`tr[data-id="${a.id}"]`);
          if (!tr) return;
          const cells  = tr.querySelectorAll('td');
          const aiCell = cells[cells.length - 2];
          if (!aiCell) return;
          const s   = a.ai_risk_status;
          const sum = a.ai_risk_summary || {};
          const tip = s === 'analysed'
            ? t('assets.created_updated', {c: sum.risks_created || 0, u: sum.risks_updated || 0})
            : (sum.error || sum.reason || '');
          aiCell.innerHTML = `<span style="font-size:10px;font-weight:600;color:${colors[s] || 'var(--text-muted)'};"
                                    title="${UI.esc(tip)}">${labels[s] || s || '-'}</span>`;
        });

        // Mostrar progreso global en el contador
        const stillAnalysing = data.filter(a => a.ai_risk_status === 'analysing').length;
        const countEl = document.getElementById('asset-count');
        if (countEl) {
          if (stillAnalysing > 0) {
            const done = data.filter(a => a.ai_risk_status === 'analysed').length;
            countEl.textContent = t('assets.analyzing_progress', {done: done, total: data.length});
            countEl.style.color = 'var(--brand-orange)';
          } else {
            countEl.style.color = '';
            // Refrescar tabla al terminar para mostrar estados finales y botones correctos
            ViewAssets._applyFiltersAndRender();
          }
        }

        if (stillAnalysing === 0) {
          ViewAssets._stopPoll();
          ViewAssets._updateAnalysisBanner();
          // Detectar errores de créditos al terminar el análisis
          const creditErrors = data.filter(a =>
            a.ai_risk_status === 'error' &&
            (a.ai_risk_summary?.error || '').toLowerCase().includes('credito')
          );
          if (creditErrors.length > 0) {
            ViewAssets._showCreditBanner();
          }
        } else {
          ViewAssets._updateAnalysisBanner();
        }
      } catch (_) { ViewAssets._stopPoll(); }
    }, 3000);
  },

  _showCreditBanner() {
    const existing = document.getElementById('credit-error-banner');
    if (existing) return;
    const banner = document.createElement('div');
    banner.id = 'credit-error-banner';
    banner.style.cssText = `
      background:#FEF3C7;border:1px solid #F59E0B;border-radius:8px;
      padding:12px 16px;margin-bottom:16px;display:flex;align-items:center;gap:10px;
      font-size:13px;color:#92400E;
    `;
    banner.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" style="flex-shrink:0;">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <span>
        <strong>Sin créditos Anthropic:</strong> el análisis se ha detenido.
        Recarga créditos en
        <a href="https://console.anthropic.com/settings/billing" target="_blank"
           style="color:#92400E;font-weight:700;">console.anthropic.com/settings/billing</a>
        y luego pulsa <em>Analizar pendientes</em>.
      </span>
      <button onclick="this.parentElement.remove()"
              style="margin-left:auto;background:none;border:none;cursor:pointer;
                     font-size:16px;color:#92400E;padding:0 4px;">&times;</button>
    `;
    const listEl = document.getElementById('asset-list');
    listEl?.parentElement?.insertBefore(banner, listEl);
  },

  _stopPoll() {
    if (ViewAssets._pollTimer) { clearInterval(ViewAssets._pollTimer); ViewAssets._pollTimer = null; }
  },

  // ---------- TAB GRUPOS: RESULTADOS ----------

  async _renderGroupsResults() {
    const view = document.getElementById('tab-groups-results');
    if (!view) return;
    view.innerHTML = `<div class="notice">${t('assets.loading_groups')}</div>`;
    try {
      const groups = await Api.assetGroups.list();
      ViewAssets._drawGroupsResults(view, groups);
    } catch (e) {
      view.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _drawGroupsResults(view, groups) {
    const canEdit  = Auth.canEdit();
    const proposed = groups.filter(g => g.status === 'proposed');
    const validated = groups.filter(g => g.status === 'validated');
    const totalGrouped = groups.reduce((s, g) => s + (g.member_count || 0), 0);

    if (!groups.length) {
      view.innerHTML = `
        <div style="text-align:center;padding:60px 20px;color:var(--text-muted);">
          <div style="font-size:56px;opacity:.3;margin-bottom:16px;">&#128193;</div>
          <div style="font-size:16px;font-weight:700;color:var(--text);margin-bottom:8px;">Sin grupos creados todavia</div>
          <div style="font-size:13px;margin-bottom:24px;">
            Ve a la pestaña "Agrupación con IA" para analizar y proponer grupos automáticamente.
          </div>
          <button class="btn btn-primary"
                  onclick="document.querySelector('[data-tab=grouping]')?.click()">
            Ir a Agrupación con IA
          </button>
        </div>`;
      return;
    }

    view.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;">
        <div style="padding:14px;background:var(--bg-2);border-radius:8px;text-align:center;border:1px solid var(--border);">
          <div style="font-size:28px;font-weight:800;color:var(--brand-purple);">${groups.length}</div>
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;margin-top:2px;">Grupos totales</div>
        </div>
        <div style="padding:14px;background:var(--bg-2);border-radius:8px;text-align:center;border:1px solid var(--border);">
          <div style="font-size:28px;font-weight:800;color:var(--text);">${totalGrouped}</div>
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;margin-top:2px;">Activos agrupados</div>
        </div>
        <div style="padding:14px;background:#D1FAE5;border-radius:8px;text-align:center;border:1px solid #A7F3D0;">
          <div style="font-size:28px;font-weight:800;color:#065f46;">${validated.length}</div>
          <div style="font-size:11px;color:#065f46;text-transform:uppercase;margin-top:2px;">Validados</div>
        </div>
        <div style="padding:14px;background:#FFF7ED;border-radius:8px;text-align:center;border:1px solid #FED7AA;">
          <div style="font-size:28px;font-weight:800;color:#92400E;">${proposed.length}</div>
          <div style="font-size:11px;color:#92400E;text-transform:uppercase;margin-top:2px;">Pendientes</div>
        </div>
      </div>

      ${canEdit ? `
      <div style="margin-bottom:18px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;
                  padding:14px;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;">
        ${proposed.length ? `
        <button class="btn btn-primary" id="btn-validate-all-results">
          Validar propuestos (${proposed.length})
        </button>` : ''}
        ${validated.length ? `
        <button class="btn btn-primary" id="btn-analyze-groups"
                style="background:var(--brand-purple);"
                title="${t('assets.hint_analyze_groups', {n: validated.length})}">
          Analizar grupos con IA (${validated.length})
        </button>` : ''}
        <span style="font-size:12px;color:var(--text-muted);line-height:1.4;">
          ${validated.length
            ? `Opcion B: el agente analiza ${validated.length} grupos en lugar de los activos individuales. Los riesgos se generan sobre el activo representativo del grupo.`
            : t('assets.validate_groups_hint')}
        </span>
      </div>` : ''}
      <div id="group-analysis-banner" style="margin-bottom:12px;"></div>

      ${proposed.length ? `
      <h4 style="font-size:11px;color:var(--text-muted);text-transform:uppercase;
                 letter-spacing:.6px;margin:0 0 10px;font-weight:700;">
        Propuestos — pendientes de validación (${proposed.length})
      </h4>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:12px;margin-bottom:24px;">
        ${proposed.map(g => ViewAssets._groupResultCard(g, canEdit)).join('')}
      </div>` : ''}

      ${validated.length ? `
      <h4 style="font-size:11px;color:var(--text-muted);text-transform:uppercase;
                 letter-spacing:.6px;margin:0 0 10px;font-weight:700;">
        Validados — listos para análisis de riesgo (${validated.length})
      </h4>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:12px;">
        ${validated.map(g => ViewAssets._groupResultCard(g, canEdit)).join('')}
      </div>` : ''}
    `;

    const btnValidateAll = document.getElementById('btn-validate-all-results');
    if (btnValidateAll) {
      btnValidateAll.onclick = async () => {
        btnValidateAll.disabled = true;
        btnValidateAll.textContent = 'Validando...';
        try {
          const r = await Api.assetGroups.validateAll();
          if (r.validated > 0) {
            UI.toast(`${r.validated} grupo${r.validated !== 1 ? 's' : ''} validado${r.validated !== 1 ? 's' : ''}`, 'success');
          } else if (r.errors && r.errors.length > 0) {
            UI.toast('Error al validar: ' + r.errors[0].error, 'error');
          } else {
            UI.toast('No habia grupos propuestos para validar', 'info');
          }
          await ViewAssets._renderGroupsResults();
        } catch (e) {
          UI.toast('Error: ' + e.message, 'error');
          btnValidateAll.disabled = false;
          btnValidateAll.textContent = 'Validar propuestos';
        }
      };
    }

    document.getElementById('btn-analyze-groups')?.addEventListener('click', async () => {
      const btn = document.getElementById('btn-analyze-groups');
      if (btn) { btn.disabled = true; btn.textContent = 'Iniciando...'; }
      try {
        const r = await Api.assets.analyzeGroups();
        if (r.ok === false) {
          UI.toast(r.message || 'Sin grupos validados', 'info');
        } else {
          UI.toast(r.message || 'Análisis de grupos iniciado', 'success', 6000);
          ViewAssets._startGroupPoll();
        }
      } catch (e) {
        UI.toast('Error: ' + e.message, 'error');
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = t('assets.btn_analyze_groups', {n: validated.length}); }
      }
    });

    ViewAssets._updateGroupAnalysisBanner();

    view.querySelectorAll('[data-result-action]').forEach(btn => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const action = btn.dataset.resultAction;
        const gid    = parseInt(btn.dataset.gid);
        if (action === 'validate')          await ViewAssets._validateGroupResult(gid, btn);
        if (action === 'edit-group')        await ViewAssets._editGroupName(gid);
        if (action === 'delete-group')      await ViewAssets._deleteGroup(gid);
        if (action === 'delete-with-assets') await ViewAssets._deleteGroupWithAssets(gid);
        if (action === 'move-asset')        await ViewAssets._moveAssetModal(gid);
        if (action === 'split')             await ViewAssets._splitModal(gid);
      };
    });
  },

  async _updateGroupAnalysisBanner() {
    const banner = document.getElementById('group-analysis-banner');
    if (!banner) return;
    try {
      const s = await Api.assets.groupAnalysisStatus();
      if (!s.total) { banner.innerHTML = ''; return; }
      const pct = s.progress_pct || 0;
      if (s.analysing > 0) {
        const barWidth = Math.max(4, Math.round(pct));
        banner.innerHTML = `
          <div style="background:#F5F3FF;border:1px solid #DDD6FE;border-radius:8px;
                      padding:12px 16px;font-size:13px;">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
              <div class="spinner" style="width:16px;height:16px;border-width:2px;flex-shrink:0;
                   border-color:rgba(89,0,141,.2);border-top-color:var(--brand-purple);"></div>
              <span style="color:var(--brand-purple);font-weight:600;">
                Analizando grupos con IA (Opcion B)...
              </span>
              <span style="margin-left:auto;color:var(--brand-purple);font-weight:700;">
                ${s.analysed} / ${s.total} (${pct}%)
              </span>
            </div>
            <div style="height:6px;background:#DDD6FE;border-radius:3px;overflow:hidden;">
              <div style="width:${barWidth}%;height:100%;background:var(--brand-purple);
                          border-radius:3px;transition:width .5s;"></div>
            </div>
            <div style="margin-top:6px;font-size:11px;color:var(--brand-purple);">
              ${s.analysing} en curso &middot; ${s.error || 0} errores &middot;
              ${s.pending - s.analysing} pendientes
            </div>
          </div>`;
        ViewAssets._startGroupPoll();
      } else if (s.analysed > 0) {
        banner.innerHTML = `
          <div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;
                      padding:8px 14px;font-size:13px;color:#166534;display:flex;
                      align-items:center;gap:8px;">
            <span>&#10003; ${s.analysed} grupos analizados (${pct}%)
            ${s.error > 0 ? `&nbsp;&middot;&nbsp;<span style="color:#dc2626;">${s.error} con error</span>` : ''}
            </span>
            <button class="btn btn-ghost" style="margin-left:auto;font-size:12px;padding:3px 10px;"
                    onclick="document.getElementById('btn-analyze-groups')?.click()">
              Re-analizar
            </button>
          </div>`;
      } else {
        banner.innerHTML = '';
      }
    } catch (_) { if (banner) banner.innerHTML = ''; }
  },

  _startGroupPoll() {
    if (ViewAssets._groupPollTimer) return;
    ViewAssets._groupPollTimer = setInterval(async () => {
      if (!document.getElementById('group-analysis-banner')) {
        clearInterval(ViewAssets._groupPollTimer);
        ViewAssets._groupPollTimer = null;
        return;
      }
      try {
        const s = await Api.assets.groupAnalysisStatus();
        if (s.analysing === 0) {
          clearInterval(ViewAssets._groupPollTimer);
          ViewAssets._groupPollTimer = null;
          await ViewAssets._renderGroupsResults();
        } else {
          await ViewAssets._updateGroupAnalysisBanner();
        }
      } catch (_) {
        clearInterval(ViewAssets._groupPollTimer);
        ViewAssets._groupPollTimer = null;
      }
    }, 3500);
  },

  _groupResultCard(g, canEdit) {
    const statusColors = { proposed: 'var(--brand-orange)', validated: 'var(--risk-low)', rejected: 'var(--risk-critical)' };
    const statusLabels = { proposed: 'Propuesto', validated: 'Validado', rejected: 'Rechazado' };
    const typeLabels   = {
      primary_process: 'Proceso', primary_information: 'Informacion',
      support_hardware: 'Hardware', support_software: 'Software',
      support_network: 'Red', support_personnel: 'Personal',
      support_site: 'Instalacion', support_organization: 'Organizacion',
    };

    // Distribucion de tipos
    const typeCount = {};
    (g.members || []).forEach(m => {
      const t = m.asset_type || 'otro';
      typeCount[t] = (typeCount[t] || 0) + 1;
    });
    const typeBadges = Object.entries(typeCount).map(([t, n]) =>
      `<span style="font-size:10px;background:var(--bg-3);padding:2px 7px;border-radius:10px;
                   color:var(--text-muted);white-space:nowrap;">${n}x ${typeLabels[t] || t}</span>`
    ).join('');

    // Valores maximos del grupo
    const members = g.members || [];
    const maxC = members.reduce((m, a) => Math.max(m, a.value_confidentiality || 0), 0);
    const maxI = members.reduce((m, a) => Math.max(m, a.value_integrity || 0), 0);
    const maxD = members.reduce((m, a) => Math.max(m, a.value_availability || 0), 0);

    // Lista completa de activos del grupo
    const memberRows = members.map(m =>
      `<div style="display:flex;align-items:center;gap:8px;padding:4px 0;
                   border-bottom:1px solid var(--border);font-size:12px;">
        <span style="font-family:var(--font-mono);font-size:10px;color:var(--text-subtle);
                     min-width:72px;flex-shrink:0;">${UI.esc(m.code || '')}</span>
        <span style="flex:1;color:var(--text);font-weight:500;">${UI.esc(m.name)}</span>
        <span style="font-size:10px;color:var(--text-muted);flex-shrink:0;">
          ${typeLabels[m.asset_type] || m.asset_type || ''}
        </span>
        ${m.value_confidentiality !== undefined ? `
        <span style="font-size:10px;color:var(--text-subtle);flex-shrink:0;">
          C${m.value_confidentiality} I${m.value_integrity} D${m.value_availability}
        </span>` : ''}
      </div>`
    ).join('');

    return `
    <div style="border:1px solid var(--border);border-radius:10px;background:var(--bg-2);
                overflow:hidden;display:flex;flex-direction:column;">
      <!-- Cabecera -->
      <div style="padding:12px 14px;background:var(--bg);border-bottom:1px solid var(--border);">
        <div style="display:flex;align-items:flex-start;gap:8px;">
          <div style="flex:1;min-width:0;">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:5px;">
              <span style="background:${statusColors[g.status] || 'var(--text-muted)'};color:#fff;
                           font-size:10px;padding:2px 8px;border-radius:10px;font-weight:700;flex-shrink:0;">
                ${statusLabels[g.status] || g.status}
              </span>
              <strong style="font-size:14px;">${UI.esc(g.name)}</strong>
            </div>
            <div style="display:flex;gap:5px;flex-wrap:wrap;align-items:center;">
              <span style="font-size:12px;font-weight:600;color:var(--text-muted);">${g.member_count} activos</span>
              ${typeBadges}
            </div>
          </div>
          ${canEdit ? `
          <div style="display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end;flex-shrink:0;">
            ${g.status === 'proposed' ? `
              <button class="btn btn-primary" data-result-action="validate" data-gid="${g.id}"
                      style="font-size:11px;padding:3px 10px;">Validar</button>` : ''}
            ${g.status === 'validated' && g.representative_asset_id ? `
              <a href="#/risks?asset_id=${g.representative_asset_id}" class="btn btn-ghost"
                 style="font-size:11px;padding:3px 10px;">Ver riesgos</a>` : ''}
            <button class="btn btn-ghost" data-result-action="edit-group" data-gid="${g.id}"
                    style="font-size:11px;padding:3px 10px;">Renombrar</button>
            <button class="btn btn-ghost" data-result-action="move-asset" data-gid="${g.id}"
                    style="font-size:11px;padding:3px 10px;">Mover activo</button>
            ${g.member_count > 1 ? `
            <button class="btn btn-ghost" data-result-action="split" data-gid="${g.id}"
                    style="font-size:11px;padding:3px 10px;">Dividir</button>` : ''}
            <button class="btn btn-danger" data-result-action="delete-group" data-gid="${g.id}"
                    style="font-size:11px;padding:3px 10px;"
                    title="${t('assets.hint_del_group_keep')}">
              Eliminar grupo
            </button>
            <button class="btn btn-danger" data-result-action="delete-with-assets" data-gid="${g.id}"
                    style="font-size:11px;padding:3px 10px;opacity:.8;"
                    title="${t('assets.hint_del_group_assets')}">
              Eliminar todo
            </button>
          </div>` : ''}
        </div>
      </div>

      <!-- Descripción y justificacion IA -->
      ${g.description || g.ai_rationale ? `
      <div style="padding:10px 14px;background:var(--bg-1);border-bottom:1px solid var(--border);font-size:12px;">
        ${g.description ? `<div style="color:var(--text);margin-bottom:4px;">${UI.esc(g.description)}</div>` : ''}
        ${g.ai_rationale ? `<div style="color:var(--text-muted);font-style:italic;">
          Justificacion ISO 27005: ${UI.esc(g.ai_rationale)}</div>` : ''}
      </div>` : ''}

      <!-- Valoración CIA del grupo -->
      <div style="padding:8px 14px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;
                  border-bottom:1px solid var(--border);background:var(--bg);">
        <span style="font-size:11px;color:var(--text-muted);font-weight:600;">Valores max.:</span>
        <span style="font-size:11px;">
          <strong style="color:#6A1B9A;">C</strong> ${maxC} &nbsp;
          <strong style="color:#2e7d32;">I</strong> ${maxI} &nbsp;
          <strong style="color:#1565c0;">D</strong> ${maxD}
        </span>
        ${g.status === 'validated' ? (() => {
          const s = g.rep_ai_status;
          if (!s) return `<span style="margin-left:auto;font-size:11px;color:#92400E;font-weight:600;">${t('assets.group_unanalyzed')}"Analizar grupos con IA"</span>`;
          const colors = { analysing: 'var(--brand-orange)', analysed: 'var(--risk-low)', error: 'var(--risk-critical)' };
          const labels = { analysing: t('assets.st_analysing'), analysed: t('assets.st_analysed'), error: 'Error' };
          const sum = g.rep_ai_summary || {};
          const tip = s === 'analysed'
            ? t('assets.risks_created_updated', {c: sum.risks_created || 0, u: sum.risks_updated || 0})
            : (sum.error || '');
          return `<span style="margin-left:auto;font-size:11px;font-weight:700;color:${colors[s] || 'var(--text-muted)'};"
                        title="${UI.esc(tip)}">${labels[s] || s}</span>`;
        })() : `
        <span style="margin-left:auto;font-size:11px;color:#92400E;">
          Pendiente de validación
        </span>`}
      </div>

      <!-- Lista de activos con scroll -->
      <details ${members.length <= 6 ? 'open' : ''} style="flex:1;">
        <summary style="cursor:pointer;padding:8px 14px;font-size:12px;font-weight:600;
                        color:var(--text-muted);list-style:none;display:flex;align-items:center;
                        gap:6px;user-select:none;background:var(--bg-2);">
          <span id="grp-arrow-${g.id}" style="font-size:10px;display:inline-block;
                transition:transform .15s;">&#9654;</span>
          Activos del grupo (${g.member_count})
          ${g.status === 'validated' && g.representative_asset_id ? `
          <span style="font-size:10px;color:#16a34a;margin-left:auto;font-weight:400;">
            Activo representativo creado
          </span>` : ''}
        </summary>
        <div style="max-height:220px;overflow-y:auto;padding:4px 14px 10px;">
          ${memberRows || ('<div style="font-size:12px;color:var(--text-muted);padding:8px 0;">' + t('assets.no_assets_in_group') + '</div>')}
        </div>
      </details>
    </div>`;
  },

  async _validateGroupResult(gid, btn) {
    if (btn) { btn.disabled = true; btn.textContent = 'Validando...'; }
    try {
      await Api.assetGroups.validate(gid);
      UI.toast(t('assets.group_validated'), 'success');
      await ViewAssets._renderGroupsResults();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
      if (btn) { btn.disabled = false; btn.textContent = 'Validar'; }
    }
  },

  async _refreshGroupViews() {
    if (ViewAssets._activeTab === 'groups-results') {
      await ViewAssets._renderGroupsResults();
    } else if (ViewAssets._activeTab === 'grouping') {
      await ViewAssets._renderGrouping();
    } else {
      await ViewAssets._renderGroupsResults();
    }
  },

  // ---------- TAB AGRUPACIÓN CON IA (configuración) ----------

  async _renderGrouping() {
    const view = document.getElementById('grouping-view');
    if (!view) return;
    view.innerHTML = `<div class="notice">${t('assets.loading_config')}</div>`;
    try {
      const [cfg, groups] = await Promise.all([
        Api.assetGroups.getConfig(),
        Api.assetGroups.list(),
      ]);
      ViewAssets._drawGrouping(view, cfg, groups);
    } catch (e) {
      view.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _drawGrouping(view, cfg, groups) {
    const canEdit      = Auth.canEdit();
    const totalGrouped = groups.reduce((s, g) => s + (g.member_count || 0), 0);

    view.innerHTML = `
      <details id="criteria-panel" open>
        <summary style="cursor:pointer;font-size:15px;font-weight:700;
                        padding:12px 0;list-style:none;display:flex;align-items:center;gap:8px;
                        color:var(--brand-purple);">
          <span style="font-size:12px;transition:transform .2s;">&#9654;</span>
          Criterios de agrupación
          <span style="font-size:11px;font-weight:400;color:var(--text-muted);margin-left:4px;">
            (${cfg.criteria.filter(c => c.enabled).length} habilitados)
          </span>
        </summary>
        <div id="criteria-body" style="padding:0 0 16px 20px;">
          <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;">
            Selecciona los criterios que la IA usara para agrupar los activos.
            El nivel 1 es el criterio principal; los niveles 2 y 3 refinan la agrupación.
          </p>
          <div id="criteria-list" style="display:flex;flex-direction:column;gap:8px;"></div>
          ${canEdit ? `
          <div style="margin-top:14px;display:flex;gap:8px;">
            <button class="btn btn-primary" id="btn-save-criteria">Guardar criterios</button>
            <button class="btn btn-ghost" id="btn-restore-criteria">Restaurar por defecto</button>
          </div>` : ''}
        </div>
      </details>

      ${canEdit ? `
      <div style="display:flex;align-items:center;gap:12px;padding:16px 0;
                  border-top:1px solid var(--border);border-bottom:1px solid var(--border);
                  margin-bottom:20px;flex-wrap:wrap;">
        <button class="btn btn-primary" id="btn-propose" style="font-size:15px;padding:10px 22px;">
          Analizar y proponer grupos con IA
        </button>
        <span style="font-size:13px;color:var(--text-muted);">
          ${totalGrouped > 0
            ? t('assets.groups_assets_summary', {g: groups.length, a: totalGrouped})
            : 'Sin grupos todavia'}
        </span>
        ${groups.length > 0 ? `
        <button class="btn btn-ghost" style="margin-left:auto;font-size:13px;"
                onclick="document.querySelector('[data-tab=groups-results]')?.click()">
          Ver resultados (${groups.length} grupos) &rarr;
        </button>` : ''}
      </div>` : ''}

      <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;
                  padding:14px 16px;font-size:13px;color:var(--text-muted);line-height:1.6;">
        <strong style="color:var(--text);">Como funciona:</strong>
        La IA analiza todos los activos del inventario y los agrupa según los criterios seleccionados.
        Los grupos <em>propuestos</em> deben validarse en la pestaña <strong>Grupos</strong> antes de
        usarse en el análisis de riesgos.
        Los grupos <em>validados</em> generan un activo representativo que concentra el calculo de
        riesgos para todo el grupo (ISO 27005 Annex B.3).
      </div>
    `;

    ViewAssets._drawCriteria(cfg.criteria);

    document.getElementById('criteria-panel')?.addEventListener('toggle', function () {
      const arrow = this.querySelector('summary span');
      if (arrow) arrow.style.transform = this.open ? 'rotate(90deg)' : '';
    });

    if (canEdit) {
      document.getElementById('btn-save-criteria')?.addEventListener('click', () =>
        ViewAssets._saveCriteria());
      document.getElementById('btn-restore-criteria')?.addEventListener('click', async () => {
        if (!await UI.confirm('Restaurar criterios por defecto?')) return;
        try {
          await Api.assetGroups.resetConfig();
          const cfg2 = await Api.assetGroups.getConfig();
          ViewAssets._drawCriteria(cfg2.criteria);
          UI.toast('Criterios restaurados', 'success');
        } catch (e) { UI.toast(e.message, 'error'); }
      });
      document.getElementById('btn-propose')?.addEventListener('click', () =>
        ViewAssets._propose());
    }
  },

  _drawCriteria(criteria) {
    const list = document.getElementById('criteria-list');
    if (!list) return;
    const levelColors = { 1: 'var(--brand-purple)', 2: 'var(--brand-orange)', 3: 'var(--risk-medium)' };
    list.innerHTML = criteria.map((c, i) => `
      <label style="display:flex;align-items:center;gap:12px;padding:10px 14px;
                    border:1px solid var(--border);border-radius:6px;cursor:pointer;
                    background:${c.enabled ? 'var(--bg-2)' : 'var(--bg)'};
                    transition:background .15s;width:100%;box-sizing:border-box;">
        <input type="checkbox" data-ci="${i}" ${c.enabled ? 'checked' : ''}
               style="flex-shrink:0;accent-color:var(--brand-purple);width:16px;height:16px;"
               onchange="ViewAssets._toggleCriterion(${i})">
        <span style="flex-shrink:0;background:${levelColors[c.level] || 'var(--text-muted)'};
                     color:#fff;font-size:10px;font-weight:700;padding:2px 7px;
                     border-radius:10px;white-space:nowrap;">N${c.level}</span>
        <div style="flex:1;min-width:0;">
          <div style="font-weight:600;font-size:13px;color:var(--text);">${UI.esc(c.name)}</div>
          <div style="font-size:12px;color:var(--text-muted);margin-top:2px;line-height:1.4;">
            ${UI.esc(c.description)}
          </div>
        </div>
      </label>
    `).join('');
    list._criteria = criteria;
  },

  _toggleCriterion(idx) {
    const list = document.getElementById('criteria-list');
    if (!list || !list._criteria) return;
    list._criteria[idx].enabled = !list._criteria[idx].enabled;
    const label = list.querySelectorAll('label')[idx];
    if (label) label.style.background = list._criteria[idx].enabled ? 'var(--bg-2)' : 'var(--bg-1)';
  },

  async _saveCriteria() {
    const list = document.getElementById('criteria-list');
    if (!list || !list._criteria) return;
    const btn = document.getElementById('btn-save-criteria');
    btn.disabled = true; btn.textContent = 'Guardando...';
    try {
      await Api.assetGroups.saveConfig({ criteria: list._criteria });
      UI.toast('Criterios guardados', 'success');
    } catch (e) { UI.toast(e.message, 'error'); }
    finally { btn.disabled = false; btn.textContent = t('assets.btn_save_criteria'); }
  },

  async _propose() {
    const btn = document.getElementById('btn-propose');
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = t('assets.analyzing_with_ai');
    btn.style.opacity = '0.7';
    try {
      const r = await Api.assetGroups.propose();
      UI.toast(t('assets.grouping_done', {g: r.groups_created, a: r.assets_analyzed}), 'success');
      // Navegar a la pestaña de resultados automáticamente
      document.querySelector('[data-tab=groups-results]')?.click();
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
    finally {
      if (btn) { btn.disabled = false; btn.textContent = t('assets.btn_propose_groups'); btn.style.opacity = ''; }
    }
  },

  // ---------- ACCIONES DE GRUPO (compartidas) ----------

  async _editGroupName(gid) {
    const groups = await Api.assetGroups.list();
    const g = groups.find(x => x.id === gid);
    if (!g) return;
    UI.modal('Renombrar grupo', `
      <div class="span2">
        <label>Nombre del grupo</label>
        <input id="grp-name" value="${UI.esc(g.name)}" style="width:100%;">
      </div>
      <div class="span2">
        <label>Descripción (opcional)</label>
        <textarea id="grp-desc" rows="2" style="width:100%;">${UI.esc(g.description || '')}</textarea>
      </div>
    `, {
      actions: `
        <button class="btn" id="m-cancel">Cancelar</button>
        <button class="btn btn-primary" id="m-save">Guardar</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const name = document.getElementById('grp-name').value.trim();
      const desc = document.getElementById('grp-desc').value.trim();
      if (!name) { UI.toast(t('assets.name_required'), 'error'); return; }
      try {
        await Api.assetGroups.update(gid, { name, description: desc || undefined });
        UI.closeModal();
        UI.toast(t('assets.group_updated'), 'success');
        await ViewAssets._refreshGroupViews();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  async _deleteGroup(gid) {
    if (!await UI.confirm(t('assets.confirm_delete_group'))) return;
    try {
      await Api.assetGroups.del(gid);
      UI.toast(t('assets.group_deleted'), 'success');
      await ViewAssets._refreshGroupViews();
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  async _deleteGroupWithAssets(gid) {
    const groups = await Api.assetGroups.list().catch(() => []);
    const g = groups.find(x => x.id === gid);
    const n = g ? g.member_count : '?';
    if (!await UI.confirm(
      `Eliminar el grupo y sus ${n} activos?\n\nEsta acción borra permanentemente todos los activos del grupo del inventario. Los riesgos vinculados quedaran sin activo.`
    )) return;
    try {
      const r = await Api.assetGroups.deleteWithAssets(gid);
      UI.toast(t('assets.group_deleted_with', {n: r.deleted_assets}), 'success');
      ViewAssets._allAssets = [];
      await ViewAssets._reload();
      await ViewAssets._refreshGroupViews();
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  },

  async _moveAssetModal(gid) {
    const groups    = await Api.assetGroups.list();
    const thisGroup = groups.find(g => g.id === gid);
    if (!thisGroup || !thisGroup.members.length) {
      UI.toast(t('assets.group_no_assets_move'), 'error'); return;
    }
    const otherGroups = groups.filter(g => g.id !== gid);
    UI.modal('Mover activo a otro grupo', `
      <div class="span2">
        <label>Activo a mover</label>
        <select id="move-asset-sel" style="width:100%;">
          ${thisGroup.members.map(m =>
            `<option value="${m.id}">${UI.esc(m.name)} (${UI.esc(m.code)})</option>`
          ).join('')}
        </select>
      </div>
      <div class="span2">
        <label>Grupo destino</label>
        <select id="move-target-sel" style="width:100%;">
          <option value="">-- Desagrupar (sin grupo) --</option>
          ${otherGroups.map(g =>
            `<option value="${g.id}">${t('assets.group_opt_members', {name: UI.esc(g.name), n: g.member_count})}</option>`
          ).join('')}
        </select>
      </div>
    `, {
      actions: `
        <button class="btn" id="m-cancel">Cancelar</button>
        <button class="btn btn-primary" id="m-save">Mover</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const assetId      = parseInt(document.getElementById('move-asset-sel').value);
      const targetRaw    = document.getElementById('move-target-sel').value;
      const targetGroupId = targetRaw ? parseInt(targetRaw) : null;
      try {
        await Api.assetGroups.moveAsset({ asset_id: assetId, target_group_id: targetGroupId });
        UI.closeModal();
        UI.toast('Activo movido', 'success');
        await ViewAssets._refreshGroupViews();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  async _splitModal(gid) {
    const groups    = await Api.assetGroups.list();
    const thisGroup = groups.find(g => g.id === gid);
    if (!thisGroup || thisGroup.members.length < 2) {
      UI.toast(t('assets.need_2_assets'), 'error'); return;
    }
    UI.modal('Dividir grupo', `
      <div class="span2">
        <label>Nombre del nuevo grupo</label>
        <input id="split-name" value="${UI.esc(thisGroup.name)} (2)" style="width:100%;">
      </div>
      <div class="span2">
        <label>Selecciona los activos que pasaran al nuevo grupo</label>
        <div style="display:flex;flex-direction:column;gap:6px;max-height:260px;overflow-y:auto;
                    padding:8px;border:1px solid var(--border);border-radius:6px;margin-top:4px;">
          ${thisGroup.members.map(m => `
            <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;">
              <input type="checkbox" value="${m.id}" class="split-cb"
                     style="accent-color:var(--brand-purple);">
              <span><strong>${UI.esc(m.name)}</strong>
                    <span style="font-size:11px;color:var(--text-muted);">${UI.esc(m.code)}</span></span>
            </label>`).join('')}
        </div>
      </div>
    `, {
      actions: `
        <button class="btn" id="m-cancel">Cancelar</button>
        <button class="btn btn-primary" id="m-save">Dividir</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const newName = document.getElementById('split-name').value.trim();
      if (!newName) { UI.toast(t('assets.name_required_short'), 'error'); return; }
      const checked = [...document.querySelectorAll('.split-cb:checked')].map(cb => parseInt(cb.value));
      if (!checked.length) { UI.toast(t('assets.select_one_asset'), 'error'); return; }
      if (checked.length >= thisGroup.members.length) {
        UI.toast('Deja al menos un activo en el grupo original', 'error'); return;
      }
      try {
        await Api.assetGroups.split(gid, { asset_ids: checked, new_group_name: newName });
        UI.closeModal();
        UI.toast('Grupo dividido', 'success');
        await ViewAssets._refreshGroupViews();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  // ---------- CRUD DE ACTIVOS ----------

  async _edit(id) {
    let a = { name: '', asset_type: 'support_hardware', description: '',
              category: '', location: '', business_process: '', classification: '',
              monetary_value: '', value_confidentiality: 0, value_integrity: 0,
              value_availability: 0, value_authenticity: 0, value_accountability: 0 };
    if (id) {
      try { a = await Api.assets.get(id); }
      catch (e) { UI.toast(e.message, 'error'); return; }
    }
    UI.modal(id ? `${t('assets.edit')} ${a.code}` : t('assets.new'), `
      <div class="span2">
        <label>${t('common.name')} *</label>
        <input id="f-name" value="${UI.esc(a.name)}" required>
      </div>
      <div>
        <label>${t('common.type')} *</label>
        <select id="f-type">
          ${['primary_process','primary_information','support_hardware','support_software',
             'support_network','support_personnel','support_site','support_organization'].map(t =>
            `<option value="${t}" ${a.asset_type===t?'selected':''}>${UI.assetTypeLabel(t)}</option>`).join('')}
        </select>
      </div>
      <div>
        <label>${t('common.category')}</label>
        <input id="f-cat" value="${UI.esc(a.category||'')}">
      </div>
      <div class="span2">
        <label>${t('common.description')}</label>
        <textarea id="f-desc" rows="2">${UI.esc(a.description||'')}</textarea>
      </div>
      <div>
        <label>${t('assets.location')}</label>
        <input id="f-loc" value="${UI.esc(a.location||'')}">
      </div>
      <div>
        <label>${t('assets.business_process')}</label>
        <input id="f-proc" value="${UI.esc(a.business_process||'')}">
      </div>
      <div>
        <label>${t('assets.classification')}</label>
        <select id="f-class">
          ${['','Publico','Interno','Confidencial','Secreto'].map(c =>
            `<option value="${c}" ${a.classification===c?'selected':''}>${c||'-'}</option>`).join('')}
        </select>
      </div>
      <div>
        <label>Valor monetario (EUR, FAIR/ALE)</label>
        <input type="number" min="0" step="1000" id="f-monetary" value="${a.monetary_value || ''}" placeholder="ej. 50000">
      </div>
      <div class="span2">
        <label>Software instalado <span style="font-weight:400;color:var(--text-muted);">(para correlación CVE automática)</span></label>
        <input id="f-software-tags" class="input"
               value="${UI.esc((a.software_tags||[]).join(', '))}"
               placeholder="apache, nginx, openssl, mysql, windows, python... (separados por comas)">
        <p style="font-size:11px;color:var(--text-muted);margin:2px 0 0;">
          Introduce los nombres de software/plataformas del activo. RiskHub los cruza con los
          CPE de cada CVE para detectar vulnerabilidades aplicables automáticamente.
        </p>
      </div>
      <div class="span2">
        <label>Valoración de dimensiones de seguridad (0 = sin valor · 4 = crítico)</label>
        <p style="font-size:11px;color:var(--text-muted);margin:2px 0 10px;">
          MAGERIT v3 define 5 dimensiones: <strong>D</strong> Disponibilidad ·
          <strong>I</strong> Integridad · <strong>C</strong> Confidencialidad ·
          <strong>A</strong> Autenticidad · <strong>T</strong> Trazabilidad.
          ISO 27005 usa C/I/D (CIA). En modo MAGERIT/Combinado, estos valores determinan
          automáticamente la consecuencia de riesgo.
        </p>
        <div id="diacat-preview" style="display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-bottom:12px;">
          ${[
            ['D','availability','#1565c0','Disponibilidad'],
            ['I','integrity','#2e7d32','Integridad'],
            ['C','confidentiality','#6A1B9A','Confidencialidad'],
            ['A','authenticity','#c25a1f','Autenticidad'],
            ['T','accountability','#555','Trazabilidad'],
          ].map(([dim, field, color, label]) => {
            const val = a['value_' + field] || 0;
            return `
            <div style="text-align:center;">
              <div style="font-size:11px;color:${color};font-weight:700;margin-bottom:4px;">${dim}</div>
              <div style="height:${Math.max(4, val * 14)}px;background:${color};border-radius:4px;
                           margin:0 auto;width:28px;transition:height .3s;" id="dbar-${dim}"></div>
              <div style="font-size:12px;font-weight:700;margin-top:4px;color:${color};" id="dval-${dim}">${val}</div>
              <div style="font-size:10px;color:var(--text-muted);">${label}</div>
            </div>`;
          }).join('')}
        </div>
      </div>
      ${[
        ['D','availability','#1565c0','Disponibilidad'],
        ['I','integrity','#2e7d32','Integridad'],
        ['C','confidentiality','#6A1B9A','Confidencialidad'],
        ['A','authenticity','#c25a1f','Autenticidad'],
        ['T','accountability','#555','Trazabilidad'],
      ].map(([dim, field, color, label]) =>
        `<div>
           <label style="color:${color};font-weight:600;">${dim} — ${label}</label>
           <input type="number" min="0" max="4" id="f-${field}" value="${a['value_'+field]||0}"
                  oninput="ViewAssets._updateDiacatBar('${dim}','${field}','${color}',this.value)">
         </div>`).join('')}
      ${id ? `
      <div class="span2">
        <details id="asset-history">
          <summary style="cursor:pointer;font-size:13px;color:var(--text-muted);padding:6px 0;
                          list-style:none;display:flex;align-items:center;gap:6px;">
            <span style="font-size:10px;">&#9654;</span> Historial de cambios
          </summary>
          <div id="asset-history-body" style="margin-top:8px;">
            <div class="notice">Cargando...</div>
          </div>
        </details>
      </div>` : ''}
    `, {
      actions: `
        <button class="btn" id="m-cancel">${t('common.cancel')}</button>
        ${id ? `<button class="btn btn-danger" id="m-del">${t('common.delete')}</button>` : ''}
        ${id ? `<button class="btn btn-ghost" id="m-ai-suggest" title="Sugerir riesgos basados en amenazas ISO 27005">IA: ${t('common.analyze')}</button>` : ''}
        <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`
    });

    document.getElementById('m-cancel').onclick = UI.closeModal;

    if (id) {
      const det = document.getElementById('asset-history');
      if (det) {
        det.addEventListener('toggle', async () => {
          if (!det.open) return;
          const body = document.getElementById('asset-history-body');
          try {
            const entries = await Api.audit.history('asset', id);
            if (!entries.length) {
              body.innerHTML = '<p style="font-size:12px;color:var(--text-subtle);">Sin registros de cambio todavia.</p>';
              return;
            }
            const actionColors = {
              create: 'background:#D1FAE5;color:#065F46',
              update: 'background:#DBEAFE;color:#1E40AF',
              delete: 'background:#FEE2E2;color:#991B1B',
            };
            body.innerHTML = entries.map(e => {
              const ts    = new Date(e.timestamp).toLocaleString('es-ES', { day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit' });
              const style = actionColors[e.action] || 'background:var(--bg-3);color:var(--text-muted)';
              const detail = e.detail && Object.keys(e.detail).length
                ? Object.entries(e.detail).map(([k,v]) => `${UI.esc(k)}: ${UI.esc(String(v))}`).join(' · ') : '';
              return `<div style="display:flex;gap:8px;align-items:flex-start;padding:6px 0;
                               border-bottom:1px solid var(--border);font-size:12px;">
                <span style="color:var(--text-subtle);white-space:nowrap;min-width:110px;">${ts}</span>
                <span class="badge badge-muted" style="${style};font-size:10px;">${UI.esc(e.action)}</span>
                <span style="color:var(--text-muted);">${UI.esc(e.user_name||e.user_email||'')}</span>
                ${detail ? `<span style="color:var(--text-subtle);">${detail}</span>` : ''}
              </div>`;
            }).join('');
          } catch (_) { body.innerHTML = '<p style="font-size:12px;color:var(--text-subtle);">No disponible.</p>'; }
        }, { once: true });
      }
    }

    if (id) document.getElementById('m-del').onclick = async () => {
      if (!await UI.confirm(t('assets.delete_confirm'))) return;
      try {
        await Api.assets.del(id);
        UI.closeModal(); UI.toast(t('common.success'), 'success');
        ViewAssets._allAssets = ViewAssets._allAssets.filter(a => a.id !== id);
        ViewAssets._applyFiltersAndRender();
      } catch (e) { UI.toast(e.message, 'error'); }
    };

    if (id) {
      const aiBtn = document.getElementById('m-ai-suggest');
      if (aiBtn) aiBtn.onclick = async () => {
        aiBtn.disabled = true; aiBtn.textContent = t('assets.st_analysing');
        try {
          const result      = await Api.ai.riskSuggest({ asset_id: id });
          const suggestions = result.suggestions || result.risks || result || [];
          if (!suggestions.length) {
            UI.toast(t('assets.no_risk_suggestions'), 'info');
            aiBtn.disabled = false; aiBtn.textContent = t('assets.btn_ai_suggest_risks');
            return;
          }
          UI.modal(t('assets.modal_risk_suggestions'), `
            <div class="span2">
              <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;">
                Basado en el tipo de activo y el catálogo ISO 27005, el sistema identifica los
                escenarios de riesgo mas probables.
              </p>
              <div style="display:flex;flex-direction:column;gap:8px;">
                ${suggestions.map(s => `
                  <div style="padding:10px 14px;border:1px solid var(--border);border-radius:6px;background:var(--bg-2);">
                    <div style="font-weight:600;font-size:13px;">${UI.esc(s.threat_name || s.threat || '')}</div>
                    ${s.description ? `<div style="font-size:12px;color:var(--text-muted);margin-top:3px;">${UI.esc(s.description)}</div>` : ''}
                    ${s.likelihood !== undefined
                      ? `<div style="font-size:11px;margin-top:4px;color:var(--text-subtle);">
                           Probabilidad estimada: ${s.likelihood}/4 &nbsp;|&nbsp; Impacto: ${s.consequence || s.impact || '-'}/4
                         </div>` : ''}
                  </div>`).join('')}
              </div>
            </div>
          `, { actions: '<button class="btn btn-primary" id="m-close-ai">Cerrar</button>' });
          document.getElementById('m-close-ai').onclick = UI.closeModal;
        } catch (e) {
          UI.toast('Error al consultar IA: ' + e.message, 'error');
          aiBtn.disabled = false; aiBtn.textContent = t('assets.btn_ai_suggest_risks');
        }
      };
    }

    document.getElementById('m-save').onclick = async () => {
      const monetaryRaw = document.getElementById('f-monetary').value;
      const softTagsRaw = (document.getElementById('f-software-tags')?.value || '');
      const softTags    = softTagsRaw.split(',').map(t => t.trim().toLowerCase()).filter(Boolean);
      const body = {
        name:             document.getElementById('f-name').value,
        asset_type:       document.getElementById('f-type').value,
        description:      document.getElementById('f-desc').value,
        category:         document.getElementById('f-cat').value,
        location:         document.getElementById('f-loc').value,
        business_process: document.getElementById('f-proc').value,
        classification:   document.getElementById('f-class').value,
        monetary_value:   monetaryRaw ? parseFloat(monetaryRaw) : null,
        software_tags:    softTags.length ? softTags : null,
      };
      ['confidentiality','integrity','availability','authenticity','accountability']
        .forEach(d => body['value_'+d] = parseInt(document.getElementById('f-'+d).value) || 0);
      try {
        if (id) await Api.assets.update(id, body);
        else    await Api.assets.create(body);
        UI.closeModal(); UI.toast(t('assets.saved'), 'success');
        await ViewAssets._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  _updateDiacatBar(dim, field, color, rawVal) {
    const val = Math.max(0, Math.min(4, parseInt(rawVal) || 0));
    const bar = document.getElementById(`dbar-${dim}`);
    const lbl = document.getElementById(`dval-${dim}`);
    if (bar) bar.style.height = Math.max(4, val * 14) + 'px';
    if (lbl) lbl.textContent  = val;
  },

  // ---------- IMPORT MULTI-ARCHIVO + DRAG & DROP ----------

  async _importFiles(files) {
    if (!files.length) return;

    const progressBanner = document.createElement('div');
    progressBanner.id = 'import-progress-banner';
    progressBanner.style.cssText = `
      position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
      background:#59008D;color:#fff;padding:14px 28px;border-radius:10px;
      font-size:14px;font-weight:600;z-index:10000;
      box-shadow:0 4px 20px rgba(0,0,0,.25);display:flex;align-items:center;gap:12px;`;
    progressBanner.innerHTML = `
      <span style="width:18px;height:18px;border:2px solid rgba(255,255,255,.4);
                   border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;
                   display:inline-block;flex-shrink:0;"></span>
      <span id="import-progress-text">
        Analizando ${files.length} archivo${files.length > 1 ? 's' : ''}...
        La IA esta normalizando las columnas.
      </span>`;

    if (!document.getElementById('import-spin-style')) {
      const s = document.createElement('style');
      s.id = 'import-spin-style';
      s.textContent = '@keyframes spin{to{transform:rotate(360deg)}}';
      document.head.appendChild(s);
    }
    document.body.appendChild(progressBanner);

    const setText = (t) => {
      const el = document.getElementById('import-progress-text');
      if (el) el.textContent = t;
    };

    let totalCreated = 0, totalUpdated = 0, totalSkipped = 0;
    const results = [];

    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      setText(`Procesando ${f.name} (${i + 1}/${files.length})...`);
      try {
        const r = await Api.assets.smartImport(f);
        totalCreated += r.created || 0;
        totalUpdated += r.updated || 0;
        totalSkipped += r.skipped || 0;
        results.push({ name: f.name, ok: true, ...r });
      } catch (err) {
        results.push({ name: f.name, ok: false, error: err.message });
      }
    }

    progressBanner.remove();
    await ViewAssets._reload();

    ViewAssets._showImportResult(results, totalCreated, totalUpdated, totalSkipped);
  },

  _showImportResult(results, created, updated, skipped) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';

    const fileRows = results.map(r => {
      if (r.ok) {
        return `<div style="padding:8px 0;border-bottom:1px solid var(--border);">
          <strong>${UI.esc(r.name)}</strong>
          <span style="float:right;color:#16a34a;">${r.created} nuevos · ${r.updated} actualizados</span>
          ${r.mapping_notes ? `<div style="font-size:11px;color:#9D9D9D;margin-top:2px;">
            IA: ${UI.esc(r.mapping_notes)}</div>` : ''}
        </div>`;
      }
      return `<div style="padding:8px 0;border-bottom:1px solid var(--border);">
        <strong>${UI.esc(r.name)}</strong>
        <span style="float:right;color:#DC2626;">Error</span>
        <div style="font-size:11px;color:#DC2626;margin-top:2px;">${UI.esc(r.error)}</div>
      </div>`;
    }).join('');

    modal.innerHTML = `
    <div class="modal" style="max-width:520px;">
      <div class="modal-header">
        <h2>Importación completada</h2>
        <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">x</button>
      </div>
      <div class="modal-body">
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px;">
          <div style="text-align:center;padding:12px;background:#D1FAE5;border-radius:8px;">
            <div style="font-size:28px;font-weight:800;color:#065f46;">${created}</div>
            <div style="font-size:11px;color:#065f46;text-transform:uppercase;">Nuevos</div>
          </div>
          <div style="text-align:center;padding:12px;background:#DBEAFE;border-radius:8px;">
            <div style="font-size:28px;font-weight:800;color:#1d4ed8;">${updated}</div>
            <div style="font-size:11px;color:#1d4ed8;text-transform:uppercase;">Actualizados</div>
          </div>
          <div style="text-align:center;padding:12px;background:#F5F5F5;border-radius:8px;">
            <div style="font-size:28px;font-weight:800;color:#9D9D9D;">${skipped}</div>
            <div style="font-size:11px;color:#9D9D9D;text-transform:uppercase;">Omitidos</div>
          </div>
        </div>

        <div style="max-height:180px;overflow-y:auto;margin-bottom:16px;">${fileRows}</div>

        ${created > 0 || updated > 0 ? `
        <div style="background:#FFF7ED;border-radius:8px;padding:14px;border:1px solid #FED7AA;">
          <div style="font-weight:700;color:#92400E;font-size:13px;margin-bottom:8px;">
            Que quieres hacer con los ${created + updated} activos importados?
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button class="btn btn-primary" onclick="ViewAssets._postImportAnalyze(); this.closest('.modal-overlay').remove();">
              Analizar riesgos activo a activo
            </button>
            <button class="btn" onclick="document.querySelector('[data-tab=grouping]')?.click(); this.closest('.modal-overlay').remove();">
              Agrupar con IA primero
            </button>
            <button class="btn btn-ghost" onclick="this.closest('.modal-overlay').remove();">
              Solo ver inventario
            </button>
          </div>
          <p style="font-size:11px;color:#9D9D9D;margin:8px 0 0;">
            <strong>Agrupar primero</strong> consolida activos similares y genera análisis de riesgos por grupo.
            <strong>Analizar directo</strong> genera riesgos individuales para cada activo.
          </p>
        </div>` : ''}
      </div>
    </div>`;
    document.body.appendChild(modal);
  },

  async _postImportAnalyze() {
    try {
      const btn = document.getElementById('btn-analyze-all');
      if (btn) btn.click();
      else {
        const r = await Api.assets.analyzeAll();
        UI.toast(t('assets.ai_analysis_launched', {n: r.total}), 'success');
        ViewAssets._startPollIfNeeded();
      }
    } catch (e) {
      UI.toast('Error lanzando análisis: ' + e.message, 'error');
    }
  },

  _setupDrop(container) {
    let dragCount = 0;
    const overlay = document.createElement('div');
    overlay.id = 'asset-drop-overlay';
    overlay.style.cssText = `
      display:none;position:fixed;inset:0;z-index:9999;
      background:rgba(89,0,141,0.15);border:3px dashed var(--brand-purple);
      border-radius:12px;pointer-events:none;
      align-items:center;justify-content:center;flex-direction:column;
    `;
    overlay.innerHTML = `
      <div style="background:#fff;border-radius:12px;padding:32px 48px;text-align:center;
                  box-shadow:0 8px 32px rgba(0,0,0,.2);">
        <div style="font-size:40px;margin-bottom:12px;">&#128193;</div>
        <div style="font-size:18px;font-weight:700;color:var(--brand-purple);">
          Suelta aquí para importar
        </div>
        <div style="font-size:13px;color:#9D9D9D;margin-top:6px;">
          CSV, XLSX, JSON, TSV u otro — la IA normaliza las columnas automáticamente
        </div>
      </div>`;
    document.body.appendChild(overlay);

    const onDragEnter = (e) => {
      if (!e.dataTransfer.types.includes('Files')) return;
      dragCount++;
      overlay.style.display = 'flex';
    };
    const onDragLeave = () => {
      dragCount--;
      if (dragCount <= 0) { dragCount = 0; overlay.style.display = 'none'; }
    };
    const onDragOver  = (e) => {
      if (e.dataTransfer.types.includes('Files')) e.preventDefault();
    };
    const onDrop = async (e) => {
      e.preventDefault();
      dragCount = 0;
      overlay.style.display = 'none';
      const files = Array.from(e.dataTransfer.files);
      if (files.length) await ViewAssets._importFiles(files);
    };

    window.addEventListener('dragenter', onDragEnter);
    window.addEventListener('dragleave', onDragLeave);
    window.addEventListener('dragover',  onDragOver);
    window.addEventListener('drop',      onDrop);

    const observer = new MutationObserver(() => {
      if (!document.body.contains(container)) {
        window.removeEventListener('dragenter', onDragEnter);
        window.removeEventListener('dragleave', onDragLeave);
        window.removeEventListener('dragover',  onDragOver);
        window.removeEventListener('drop',      onDrop);
        overlay.remove();
        observer.disconnect();
      }
    });
    observer.observe(document.getElementById('main') || document.body, { childList: true });
  },
};
