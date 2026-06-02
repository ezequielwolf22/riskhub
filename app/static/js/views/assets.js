/* Vista Activos: CRUD + import/export + analisis IA + agrupacion IA. */
const ViewAssets = {
  _sortCol: 'code', _sortAsc: true,
  _pollTimer: null,
  _activeTab: 'inventory',

  async render(main) {
    ViewAssets._stopPoll();
    ViewAssets._activeTab = 'inventory';
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      'Inventario de activos',
      'Activos primarios y de soporte (ISO 27005 Annex B)',
      canEdit ? `
        <span id="inv-actions">
          <button class="btn" id="btn-export">Exportar CSV</button>
          <button class="btn" id="btn-template">Plantilla</button>
          <label class="btn" id="lbl-import" title="Acepta cualquier formato: CSV, XLSX, JSON, etc. La IA normaliza las columnas automaticamente">
            Importar (cualquier formato)
            <input type="file" id="file-import" accept="*" multiple style="display:none;">
          </label>
          <button class="btn btn-ghost" id="btn-analyze-all"
                  title="Analizar riesgos de todos los activos con IA">
            Analizar riesgos con IA
          </button>
          <button class="btn btn-primary" id="btn-new">+ Nuevo activo</button>
        </span>
      ` : ''
    ) + `
      <div style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:16px;">
        <button class="asset-tab active" data-tab="inventory"
          style="padding:8px 18px;border:none;background:none;cursor:pointer;font-size:14px;
                 font-weight:600;color:var(--brand-purple);
                 border-bottom:3px solid var(--brand-purple);margin-bottom:-2px;">
          Inventario
        </button>
        <button class="asset-tab" data-tab="grouping"
          style="padding:8px 18px;border:none;background:none;cursor:pointer;font-size:14px;
                 font-weight:600;color:var(--text-muted);
                 border-bottom:3px solid transparent;margin-bottom:-2px;">
          Agrupacion con IA
        </button>
      </div>
      <div id="tab-inventory">
        <div class="toolbar">
          <input type="search" id="asset-search" placeholder="Buscar por nombre o codigo...">
          <select id="asset-type-filter">
            <option value="">Todos los tipos</option>
            <option value="primary_process">Proceso</option>
            <option value="primary_information">Informacion</option>
            <option value="support_hardware">Hardware</option>
            <option value="support_software">Software</option>
            <option value="support_network">Red</option>
            <option value="support_personnel">Personal</option>
            <option value="support_site">Instalacion</option>
            <option value="support_organization">Organizacion</option>
          </select>
          <span class="spacer"></span>
          <span id="asset-count" style="color:var(--text-subtle);font-size:12px;"></span>
        </div>
        <div id="asset-list"></div>
      </div>
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
        document.getElementById('tab-inventory').style.display = tab === 'inventory' ? '' : 'none';
        document.getElementById('tab-grouping').style.display = tab === 'grouping' ? '' : 'none';
        const invActions = document.getElementById('inv-actions');
        if (invActions) invActions.style.display = tab === 'inventory' ? '' : 'none';
        if (tab === 'grouping') ViewAssets._renderGrouping();
        if (tab === 'inventory') ViewAssets._reload();
      };
    });

    document.getElementById('asset-search').oninput = () => ViewAssets._reload();
    document.getElementById('asset-type-filter').onchange = () => ViewAssets._reload();

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

      // Drag-and-drop sobre el inventario completo
      ViewAssets._setupDrop(main);
      const btnAnalyzeAll = document.getElementById('btn-analyze-all');
      if (btnAnalyzeAll) {
        btnAnalyzeAll.onclick = async () => {
          btnAnalyzeAll.disabled = true;
          btnAnalyzeAll.textContent = 'Iniciando...';
          try {
            const r = await Api.assets.analyzeAll();
            UI.toast(`Analisis IA lanzado para ${r.total} activos`, 'success');
            ViewAssets._reload();
            ViewAssets._startPollIfNeeded();
          } catch (e) {
            UI.toast('Error: ' + e.message, 'error');
          } finally {
            btnAnalyzeAll.disabled = false;
            btnAnalyzeAll.textContent = 'Analizar riesgos con IA';
          }
        };
      }
    }

    ViewAssets._reload();
  },

  async _reload() {
    const q = document.getElementById('asset-search')?.value;
    const t = document.getElementById('asset-type-filter')?.value;
    const list = document.getElementById('asset-list');
    if (!list) return;
    list.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      const params = {};
      if (q) params.q = q;
      if (t) params.asset_type = t;
      const data = await Api.assets.list(params);
      document.getElementById('asset-count').textContent = `${data.length} activos`;
      if (!data.length) {
        list.innerHTML = UI.emptyState(
          'Sin activos',
          'Crea uno nuevo o importa el inventario desde un CSV.'
        );
        return;
      }
      const _sortVal = a => {
        const k = ViewAssets._sortCol;
        if (k === 'code') return a.code || '';
        if (k === 'name') return (a.name || '').toLowerCase();
        if (k === 'type') return a.asset_type || '';
        if (k === 'value_max') return a.value_max || 0;
        if (k === 'risks') return a.risk_count || 0;
        if (k === 'category') return (a.category || '').toLowerCase();
        return '';
      };
      data.sort((a, b) => {
        const va = _sortVal(a), vb = _sortVal(b);
        const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
        return ViewAssets._sortAsc ? cmp : -cmp;
      });

      const _th = (col, label, title, style) => {
        const active = ViewAssets._sortCol === col;
        const arrow = active ? (ViewAssets._sortAsc ? ' ▲' : ' ▼') : '';
        return `<th style="cursor:pointer;user-select:none;white-space:nowrap;${active?'color:var(--brand-purple);':''}${style||''}"
                    data-sort="${col}" title="${title||label}">${label}${arrow}</th>`;
      };

      const _aiStatusBadge = (a) => {
        const s = a.ai_risk_status;
        if (!s) return `<span style="font-size:10px;color:var(--text-subtle);">-</span>`;
        const colors = { analysing:'var(--brand-orange)', analysed:'var(--risk-low)', error:'var(--risk-critical)', skipped:'var(--text-muted)' };
        const labels = { analysing:'Analizando...', analysed:'Analizado', error:'Error', skipped:'Sin IA' };
        const sum = a.ai_risk_summary || {};
        const tip = s === 'analysed'
          ? `${sum.risks_created || 0} creados, ${sum.risks_updated || 0} actualizados`
          : (sum.error || sum.reason || '');
        return `<span style="font-size:10px;font-weight:600;color:${colors[s]||'var(--text-muted)'};"
                      title="${UI.esc(tip)}">${labels[s]||s}</span>`;
      };

      const _groupBadge = (a) => {
        if (!a.group_id) return '';
        return `<span style="font-size:10px;background:var(--brand-purple);color:#fff;
                             padding:2px 6px;border-radius:10px;font-weight:600;"
                      title="Pertenece a un grupo de activos">GRP</span> `;
      };

      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead>
          <tr>
            ${_th('code','Codigo')}${_th('name','Nombre')}${_th('type','Tipo')}
            <th>C</th><th>I</th><th>D</th><th>Auth</th><th>Acc</th>${_th('value_max','Max','Valor maximo CIA')}
            ${_th('category','Categoria')}
            ${_th('risks','Riesgos','Numero de riesgos asociados','width:70px;text-align:center;')}
            <th style="white-space:nowrap;">Analisis IA</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${data.map(a => {
            const rc = a.risk_count || 0;
            const rcColor = rc === 0 ? 'var(--text-subtle)' : rc >= 5 ? 'var(--risk-high)' : 'var(--brand-purple)';
            return `
            <tr data-id="${a.id}" style="cursor:pointer;">
              <td>${UI.codePill(a.code)}</td>
              <td><strong>${_groupBadge(a)}${UI.esc(a.name)}</strong>
                  ${a.description ? `<div style="font-size:11px;color:var(--text-subtle);">${UI.esc(a.description).slice(0,80)}</div>` : ''}</td>
              <td>${UI.assetTypeLabel(a.asset_type)}</td>
              <td>${a.value_confidentiality}</td>
              <td>${a.value_integrity}</td>
              <td>${a.value_availability}</td>
              <td>${a.value_authenticity}</td>
              <td>${a.value_accountability}</td>
              <td>${UI.riskPill(a.value_max * 2)}</td>
              <td>${UI.esc(a.category || '-')}</td>
              <td style="text-align:center;">
                <a href="#/risks?asset_id=${a.id}" title="Ver riesgos de este activo"
                   style="font-weight:700;font-family:var(--font-mono);font-size:13px;
                          color:${rcColor};text-decoration:none;">${rc}</a>
              </td>
              <td style="white-space:nowrap;" onclick="event.stopPropagation()">
                ${_aiStatusBadge(a)}
              </td>
              <td style="white-space:nowrap;" onclick="event.stopPropagation()">
                ${Auth.canEdit() ? `<button class="btn btn-ghost" data-edit="${a.id}">Editar</button>` : ''}
                ${Auth.canEdit() && (!a.ai_risk_status || a.ai_risk_status === 'error' || a.ai_risk_status === 'skipped')
                  ? `<button class="btn btn-ghost" style="font-size:11px;padding:2px 8px;"
                             data-analyze="${a.id}"
                             title="Analizar riesgos con IA para este activo">&#9881; IA</button>`
                  : ''}
              </td>
            </tr>`;}).join('')}
        </tbody>
      </table></div>`;

      list.querySelectorAll('th[data-sort]').forEach(th => {
        th.onclick = () => {
          const col = th.dataset.sort;
          if (ViewAssets._sortCol === col) ViewAssets._sortAsc = !ViewAssets._sortAsc;
          else { ViewAssets._sortCol = col; ViewAssets._sortAsc = col !== 'value_max' && col !== 'risks'; }
          ViewAssets._reload();
        };
      });
      list.querySelectorAll('[data-edit]').forEach(b =>
        b.onclick = (e) => { e.stopPropagation(); ViewAssets._edit(parseInt(b.dataset.edit)); });
      list.querySelectorAll('[data-analyze]').forEach(b =>
        b.onclick = async (e) => {
          e.stopPropagation();
          const id = parseInt(b.dataset.analyze);
          b.disabled = true; b.textContent = '...';
          try {
            await Api.assets.analyze(id);
            UI.toast('Analisis IA iniciado', 'success');
            ViewAssets._reload();
            ViewAssets._startPollIfNeeded();
          } catch (err) {
            UI.toast('Error: ' + err.message, 'error');
            b.disabled = false; b.textContent = '⚙ IA';
          }
        });
      list.querySelectorAll('tr[data-id]').forEach(tr =>
        tr.onclick = () => ViewAssets._edit(parseInt(tr.dataset.id)));

      ViewAssets._startPollIfNeeded();
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _startPollIfNeeded() {
    ViewAssets._stopPoll();
    const assetList = document.querySelector('#asset-list tbody');
    if (!assetList) return;
    const hasAnalysing = assetList.innerHTML.includes('Analizando...');
    if (!hasAnalysing) return;
    ViewAssets._pollTimer = setInterval(async () => {
      try {
        const q = document.getElementById('asset-search')?.value || '';
        const t = document.getElementById('asset-type-filter')?.value || '';
        const params = {};
        if (q) params.q = q;
        if (t) params.asset_type = t;
        const data = await Api.assets.list(params);
        const tbody = document.querySelector('#asset-list tbody');
        if (!tbody) { ViewAssets._stopPoll(); return; }
        data.forEach(a => {
          const tr = document.querySelector(`tr[data-id="${a.id}"]`);
          if (!tr) return;
          const cells = tr.querySelectorAll('td');
          const aiCell = cells[cells.length - 2];
          if (aiCell) {
            const s = a.ai_risk_status;
            const colors = { analysing:'var(--brand-orange)', analysed:'var(--risk-low)', error:'var(--risk-critical)', skipped:'var(--text-muted)' };
            const labels = { analysing:'Analizando...', analysed:'Analizado', error:'Error', skipped:'Sin IA' };
            const sum = a.ai_risk_summary || {};
            const tip = s === 'analysed' ? `${sum.risks_created||0} creados, ${sum.risks_updated||0} actualizados` : (sum.error||sum.reason||'');
            aiCell.innerHTML = `<span style="font-size:10px;font-weight:600;color:${colors[s]||'var(--text-muted)'};" title="${UI.esc(tip)}">${labels[s]||s||'-'}</span>`;
          }
        });
        if (!data.some(a => a.ai_risk_status === 'analysing')) {
          ViewAssets._stopPoll();
        }
      } catch (_) { ViewAssets._stopPoll(); }
    }, 4000);
  },

  _stopPoll() {
    if (ViewAssets._pollTimer) { clearInterval(ViewAssets._pollTimer); ViewAssets._pollTimer = null; }
  },

  // ---------- AGRUPACION CON IA ----------

  async _renderGrouping() {
    const view = document.getElementById('grouping-view');
    if (!view) return;
    view.innerHTML = '<div class="notice">Cargando configuracion...</div>';
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
    const canEdit = Auth.canEdit();
    const proposed = groups.filter(g => g.status === 'proposed');
    const validated = groups.filter(g => g.status === 'validated');
    const totalGrouped = groups.reduce((s, g) => s + g.member_count, 0);

    view.innerHTML = `
      <!-- Panel criterios -->
      <details id="criteria-panel" open>
        <summary style="cursor:pointer;font-size:15px;font-weight:700;
                        padding:12px 0;list-style:none;display:flex;align-items:center;gap:8px;
                        color:var(--brand-purple);">
          <span style="font-size:12px;transition:transform .2s;">&#9654;</span>
          Criterios de agrupacion
          <span style="font-size:11px;font-weight:400;color:var(--text-muted);margin-left:4px;">
            (${cfg.criteria.filter(c=>c.enabled).length} activos)
          </span>
        </summary>
        <div id="criteria-body" style="padding:0 0 16px 20px;">
          <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;">
            Selecciona los criterios que la IA usara para agrupar los activos.
            El nivel 1 es el criterio principal; los niveles 2 y 3 refinan la agrupacion.
          </p>
          <div id="criteria-list" style="display:flex;flex-direction:column;gap:8px;"></div>
          ${canEdit ? `
          <div style="margin-top:14px;display:flex;gap:8px;">
            <button class="btn btn-primary" id="btn-save-criteria">Guardar criterios</button>
            <button class="btn btn-ghost" id="btn-restore-criteria">Restaurar por defecto</button>
          </div>` : ''}
        </div>
      </details>

      <!-- Accion principal -->
      ${canEdit ? `
      <div style="display:flex;align-items:center;gap:12px;padding:16px 0;
                  border-top:1px solid var(--border);border-bottom:1px solid var(--border);
                  margin-bottom:20px;">
        <button class="btn btn-primary" id="btn-propose" style="font-size:15px;padding:10px 22px;">
          Analizar y proponer grupos con IA
        </button>
        <span style="font-size:13px;color:var(--text-muted);">
          ${totalGrouped > 0
            ? `${groups.length} grupos &middot; ${totalGrouped} activos agrupados`
            : 'Sin grupos todavia'}
        </span>
        ${proposed.length ? `
        <button class="btn" id="btn-validate-all"
                style="margin-left:auto;">
          Validar todos (${proposed.length})
        </button>` : ''}
      </div>` : ''}

      <!-- Grupos -->
      <div id="groups-list">
        ${groups.length === 0
          ? `<div style="text-align:center;padding:40px;color:var(--text-muted);font-size:14px;">
               Sin grupos todavia. Pulsa "Analizar y proponer grupos con IA" para comenzar.
             </div>`
          : ''}
        ${proposed.length ? `<h4 style="font-size:13px;color:var(--text-muted);margin:0 0 8px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;">Propuestos (${proposed.length})</h4>` : ''}
        ${proposed.map(g => ViewAssets._groupCard(g, canEdit)).join('')}
        ${validated.length ? `<h4 style="font-size:13px;color:var(--text-muted);margin:16px 0 8px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;">Validados (${validated.length})</h4>` : ''}
        ${validated.map(g => ViewAssets._groupCard(g, canEdit)).join('')}
      </div>
    `;

    // Render criteria checkboxes
    ViewAssets._drawCriteria(cfg.criteria);

    // Handlers
    document.getElementById('criteria-panel')?.addEventListener('toggle', function() {
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
      document.getElementById('btn-validate-all')?.addEventListener('click', () =>
        ViewAssets._validateAll());
    }

    ViewAssets._attachGroupHandlers(canEdit);
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
        <span style="flex-shrink:0;background:${levelColors[c.level]||'var(--text-muted)'};
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
    finally { btn.disabled = false; btn.textContent = 'Guardar criterios'; }
  },

  async _propose() {
    const btn = document.getElementById('btn-propose');
    btn.disabled = true;
    btn.textContent = 'Analizando activos con IA...';
    btn.style.opacity = '0.7';
    try {
      const r = await Api.assetGroups.propose();
      UI.toast(`Agrupacion completada: ${r.groups_created} grupos propuestos para ${r.assets_analyzed} activos`, 'success');
      await ViewAssets._renderGrouping();
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
    finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Analizar y proponer grupos con IA'; btn.style.opacity = ''; }
    }
  },

  async _validateAll() {
    const btn = document.getElementById('btn-validate-all');
    if (btn) { btn.disabled = true; btn.textContent = 'Validando...'; }
    try {
      const r = await Api.assetGroups.validateAll();
      UI.toast(`${r.validated} grupos validados`, 'success');
      await ViewAssets._renderGrouping();
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  },

  _groupCard(g, canEdit) {
    const statusColors = { proposed: 'var(--brand-orange)', validated: 'var(--risk-low)', rejected: 'var(--risk-critical)' };
    const statusLabels = { proposed: 'Propuesto', validated: 'Validado', rejected: 'Rechazado' };
    const membersList = (g.members || []).slice(0, 8).map(m =>
      `<span style="font-size:11px;background:var(--bg-3);padding:2px 7px;border-radius:10px;
                    color:var(--text-muted);">${UI.esc(m.name)}</span>`
    ).join(' ');
    const moreCount = (g.members || []).length > 8 ? g.members.length - 8 : 0;

    return `
    <div class="group-card" data-gid="${g.id}"
         style="border:1px solid var(--border);border-radius:8px;padding:14px 16px;
                margin-bottom:10px;background:var(--bg-2);">
      <div style="display:flex;align-items:flex-start;gap:10px;">
        <div style="flex:1;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <span style="background:${statusColors[g.status]||'var(--text-muted)'};color:#fff;
                         font-size:10px;padding:2px 8px;border-radius:10px;font-weight:600;">
              ${statusLabels[g.status]||g.status}
            </span>
            <strong style="font-size:14px;" class="group-name">${UI.esc(g.name)}</strong>
            <span style="font-size:12px;color:var(--text-muted);">(${g.member_count} activos)</span>
          </div>
          ${g.description ? `<div style="font-size:12px;color:var(--text-muted);margin-bottom:6px;">${UI.esc(g.description)}</div>` : ''}
          ${g.ai_rationale ? `
            <details style="margin-bottom:6px;">
              <summary style="font-size:11px;color:var(--text-subtle);cursor:pointer;list-style:none;">
                Justificacion ISO 27005
              </summary>
              <div style="font-size:12px;color:var(--text-muted);margin-top:4px;padding:8px;
                          background:var(--bg-1);border-radius:4px;">${UI.esc(g.ai_rationale)}</div>
            </details>` : ''}
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;">
            ${membersList}
            ${moreCount ? `<span style="font-size:11px;color:var(--text-subtle);">+${moreCount} mas</span>` : ''}
          </div>
        </div>
        ${canEdit ? `
        <div style="display:flex;flex-direction:column;gap:4px;min-width:100px;align-items:flex-end;">
          ${g.status === 'proposed' ? `
            <button class="btn btn-primary" data-action="validate" data-gid="${g.id}"
                    style="font-size:12px;padding:4px 12px;">Validar</button>` : ''}
          ${g.status === 'validated' && g.representative_asset_id ? `
            <a href="#/risks?asset_id=${g.representative_asset_id}" class="btn btn-ghost"
               style="font-size:12px;padding:4px 12px;">Ver riesgos</a>` : ''}
          <button class="btn btn-ghost" data-action="edit-group" data-gid="${g.id}"
                  style="font-size:12px;padding:4px 12px;">Renombrar</button>
          <button class="btn btn-ghost" data-action="move-asset" data-gid="${g.id}"
                  style="font-size:12px;padding:4px 12px;">Mover activo</button>
          ${g.member_count > 1 ? `
          <button class="btn btn-ghost" data-action="split" data-gid="${g.id}"
                  style="font-size:12px;padding:4px 12px;">Dividir</button>` : ''}
          <button class="btn btn-danger" data-action="delete-group" data-gid="${g.id}"
                  style="font-size:12px;padding:4px 12px;">Eliminar</button>
        </div>` : ''}
      </div>
    </div>`;
  },

  _attachGroupHandlers(canEdit) {
    if (!canEdit) return;
    document.querySelectorAll('[data-action]').forEach(btn => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const action = btn.dataset.action;
        const gid = parseInt(btn.dataset.gid);
        if (action === 'validate') await ViewAssets._validateGroup(gid, btn);
        if (action === 'edit-group') await ViewAssets._editGroupName(gid);
        if (action === 'delete-group') await ViewAssets._deleteGroup(gid);
        if (action === 'move-asset') await ViewAssets._moveAssetModal(gid);
        if (action === 'split') await ViewAssets._splitModal(gid);
      };
    });
  },

  async _validateGroup(gid, btn) {
    btn.disabled = true; btn.textContent = 'Validando...';
    try {
      await Api.assetGroups.validate(gid);
      UI.toast('Grupo validado. Activo representativo creado.', 'success');
      await ViewAssets._renderGrouping();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
      btn.disabled = false; btn.textContent = 'Validar';
    }
  },

  async _editGroupName(gid) {
    const card = document.querySelector(`.group-card[data-gid="${gid}"]`);
    const current = card?.querySelector('.group-name')?.textContent || '';
    UI.modal('Renombrar grupo', `
      <div class="span2">
        <label>Nombre del grupo</label>
        <input id="grp-name" value="${UI.esc(current)}" style="width:100%;">
      </div>
      <div class="span2">
        <label>Descripcion (opcional)</label>
        <textarea id="grp-desc" rows="2" style="width:100%;"></textarea>
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
      if (!name) { UI.toast('El nombre es obligatorio', 'error'); return; }
      try {
        await Api.assetGroups.update(gid, { name, description: desc || undefined });
        UI.closeModal();
        UI.toast('Grupo actualizado', 'success');
        await ViewAssets._renderGrouping();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  async _deleteGroup(gid) {
    if (!await UI.confirm('Eliminar el grupo? Los activos quedaran desagrupados.')) return;
    try {
      await Api.assetGroups.del(gid);
      UI.toast('Grupo eliminado', 'success');
      await ViewAssets._renderGrouping();
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  async _moveAssetModal(gid) {
    const [groups, groupData] = await Promise.all([
      Api.assetGroups.list(),
      Api.assetGroups.list(),
    ]);
    const thisGroup = groups.find(g => g.id === gid);
    if (!thisGroup || !thisGroup.members.length) {
      UI.toast('El grupo no tiene activos para mover', 'error'); return;
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
            `<option value="${g.id}">${UI.esc(g.name)} (${g.member_count} activos)</option>`
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
      const assetId = parseInt(document.getElementById('move-asset-sel').value);
      const targetRaw = document.getElementById('move-target-sel').value;
      const targetGroupId = targetRaw ? parseInt(targetRaw) : null;
      try {
        await Api.assetGroups.moveAsset({ asset_id: assetId, target_group_id: targetGroupId });
        UI.closeModal();
        UI.toast('Activo movido', 'success');
        await ViewAssets._renderGrouping();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  async _splitModal(gid) {
    const groups = await Api.assetGroups.list();
    const thisGroup = groups.find(g => g.id === gid);
    if (!thisGroup || thisGroup.members.length < 2) {
      UI.toast('Se necesitan al menos 2 activos para dividir el grupo', 'error'); return;
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
      if (!newName) { UI.toast('Nombre obligatorio', 'error'); return; }
      const checked = [...document.querySelectorAll('.split-cb:checked')].map(cb => parseInt(cb.value));
      if (!checked.length) { UI.toast('Selecciona al menos un activo', 'error'); return; }
      if (checked.length >= thisGroup.members.length) {
        UI.toast('Deja al menos un activo en el grupo original', 'error'); return;
      }
      try {
        await Api.assetGroups.split(gid, { asset_ids: checked, new_group_name: newName });
        UI.closeModal();
        UI.toast('Grupo dividido', 'success');
        await ViewAssets._renderGrouping();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  // ---------- CRUD de activos ----------

  async _edit(id) {
    let a = { name: '', asset_type: 'support_hardware', description: '',
              category: '', location: '', business_process: '', classification: '',
              monetary_value: '', value_confidentiality: 0, value_integrity: 0,
              value_availability: 0, value_authenticity: 0, value_accountability: 0 };
    if (id) {
      try { a = await Api.assets.get(id); }
      catch (e) { UI.toast(e.message, 'error'); return; }
    }
    UI.modal(id ? `Editar ${a.code}` : 'Nuevo activo', `
      <div class="span2">
        <label>Nombre *</label>
        <input id="f-name" value="${UI.esc(a.name)}" required>
      </div>
      <div>
        <label>Tipo *</label>
        <select id="f-type">
          ${['primary_process','primary_information','support_hardware','support_software',
             'support_network','support_personnel','support_site','support_organization'].map(t =>
            `<option value="${t}" ${a.asset_type===t?'selected':''}>${UI.assetTypeLabel(t)}</option>`).join('')}
        </select>
      </div>
      <div>
        <label>Categoria</label>
        <input id="f-cat" value="${UI.esc(a.category||'')}">
      </div>
      <div class="span2">
        <label>Descripcion</label>
        <textarea id="f-desc" rows="2">${UI.esc(a.description||'')}</textarea>
      </div>
      <div>
        <label>Localizacion</label>
        <input id="f-loc" value="${UI.esc(a.location||'')}">
      </div>
      <div>
        <label>Proceso de negocio</label>
        <input id="f-proc" value="${UI.esc(a.business_process||'')}">
      </div>
      <div>
        <label>Clasificacion</label>
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
        <label>Software instalado <span style="font-weight:400;color:var(--text-muted);">(para correlacion CVE automatica)</span></label>
        <input id="f-software-tags" class="input"
               value="${UI.esc((a.software_tags||[]).join(', '))}"
               placeholder="apache, nginx, openssl, mysql, windows, python... (separados por comas)">
        <p style="font-size:11px;color:var(--text-muted);margin:2px 0 0;">
          Introduce los nombres de software/plataformas del activo. RiskHub los cruza con los
          CPE de cada CVE para detectar vulnerabilidades aplicables automaticamente.
        </p>
      </div>
      <!-- Valoración DIACAT (MAGERIT v3 + ISO 27005) — 5 dimensiones de seguridad -->
      <div class="span2">
        <label>Valoración de dimensiones de seguridad (0 = sin valor · 4 = crítico)</label>
        <p style="font-size:11px;color:var(--text-muted);margin:2px 0 10px;">
          MAGERIT v3 define 5 dimensiones: <strong>D</strong> Disponibilidad ·
          <strong>I</strong> Integridad · <strong>C</strong> Confidencialidad ·
          <strong>A</strong> Autenticidad · <strong>T</strong> Trazabilidad.
          ISO 27005 usa C/I/D (CIA). En modo MAGERIT/Combinado, estos valores determinan
          automáticamente la consecuencia de riesgo.
        </p>
        <!-- Visualización en barras -->
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
        <button class="btn" id="m-cancel">Cancelar</button>
        ${id ? `<button class="btn btn-danger" id="m-del">Eliminar</button>` : ''}
        ${id ? `<button class="btn btn-ghost" id="m-ai-suggest" title="Sugerir riesgos basados en amenazas ISO 27005">IA: Sugerir riesgos</button>` : ''}
        <button class="btn btn-primary" id="m-save">Guardar</button>`
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
            const actionColors = { create:'background:#D1FAE5;color:#065F46', update:'background:#DBEAFE;color:#1E40AF', delete:'background:#FEE2E2;color:#991B1B' };
            body.innerHTML = entries.map(e => {
              const ts = new Date(e.timestamp).toLocaleString('es-ES', { day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit' });
              const style = actionColors[e.action] || 'background:var(--bg-3);color:var(--text-muted)';
              const detail = e.detail && Object.keys(e.detail).length
                ? Object.entries(e.detail).map(([k,v]) => `${UI.esc(k)}: ${UI.esc(String(v))}`).join(' · ') : '';
              return `<div style="display:flex;gap:8px;align-items:flex-start;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px;">
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
      if (!await UI.confirm('Eliminar este activo?')) return;
      try { await Api.assets.del(id); UI.closeModal(); UI.toast('Eliminado','success'); ViewAssets._reload(); }
      catch (e) { UI.toast(e.message, 'error'); }
    };

    if (id) {
      const aiBtn = document.getElementById('m-ai-suggest');
      if (aiBtn) aiBtn.onclick = async () => {
        aiBtn.disabled = true; aiBtn.textContent = 'Analizando...';
        try {
          const result = await Api.ai.riskSuggest({ asset_id: id });
          const suggestions = result.suggestions || result.risks || result || [];
          if (!suggestions.length) {
            UI.toast('No se encontraron sugerencias de riesgo para este activo.', 'info');
            aiBtn.disabled = false; aiBtn.textContent = 'IA: Sugerir riesgos';
            return;
          }
          UI.modal('Sugerencias de riesgo — IA', `
            <div class="span2">
              <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;">
                Basado en el tipo de activo y el catalogo ISO 27005, el sistema identifica los escenarios de riesgo mas probables.
              </p>
              <div style="display:flex;flex-direction:column;gap:8px;">
                ${suggestions.map(s => `
                  <div style="padding:10px 14px;border:1px solid var(--border);border-radius:6px;background:var(--bg-2);">
                    <div style="font-weight:600;font-size:13px;">${UI.esc(s.threat_name || s.threat || '')}</div>
                    ${s.description ? `<div style="font-size:12px;color:var(--text-muted);margin-top:3px;">${UI.esc(s.description)}</div>` : ''}
                    ${s.likelihood !== undefined ? `<div style="font-size:11px;margin-top:4px;color:var(--text-subtle);">Probabilidad estimada: ${s.likelihood}/4 &nbsp;|&nbsp; Impacto: ${s.consequence || s.impact || '-'}/4</div>` : ''}
                  </div>`).join('')}
              </div>
            </div>
          `, { actions: '<button class="btn btn-primary" id="m-close-ai">Cerrar</button>' });
          document.getElementById('m-close-ai').onclick = UI.closeModal;
        } catch (e) {
          UI.toast('Error al consultar IA: ' + e.message, 'error');
          aiBtn.disabled = false; aiBtn.textContent = 'IA: Sugerir riesgos';
        }
      };
    }

    document.getElementById('m-save').onclick = async () => {
      const monetaryRaw = document.getElementById('f-monetary').value;
      const softTagsRaw = (document.getElementById('f-software-tags')?.value || '');
      const softTags = softTagsRaw.split(',').map(t => t.trim().toLowerCase()).filter(Boolean);
      const body = {
        name: document.getElementById('f-name').value,
        asset_type: document.getElementById('f-type').value,
        description: document.getElementById('f-desc').value,
        category: document.getElementById('f-cat').value,
        location: document.getElementById('f-loc').value,
        business_process: document.getElementById('f-proc').value,
        classification: document.getElementById('f-class').value,
        monetary_value: monetaryRaw ? parseFloat(monetaryRaw) : null,
        software_tags: softTags.length ? softTags : null,
      };
      ['confidentiality','integrity','availability','authenticity','accountability']
        .forEach(d => body['value_'+d] = parseInt(document.getElementById('f-'+d).value) || 0);
      try {
        if (id) await Api.assets.update(id, body);
        else await Api.assets.create(body);
        UI.closeModal(); UI.toast('Guardado', 'success'); ViewAssets._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  // Actualiza la barra visual DIACAT en tiempo real al cambiar un valor
  _updateDiacatBar(dim, field, color, rawVal) {
    const val = Math.max(0, Math.min(4, parseInt(rawVal) || 0));
    const bar = document.getElementById(`dbar-${dim}`);
    const lbl = document.getElementById(`dval-${dim}`);
    if (bar) bar.style.height = Math.max(4, val * 14) + 'px';
    if (lbl) lbl.textContent = val;
  },

  // ---------- IMPORT MULTI-ARCHIVO + DRAG & DROP ----------

  async _importFiles(files) {
    if (!files.length) return;

    // Mostrar banner de progreso durante la normalizacion IA
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
    ViewAssets._reload();

    // Modal de resumen siempre visible tras importar
    ViewAssets._showImportResult(results, totalCreated, totalUpdated, totalSkipped);
  },

  _showImportResult(results, created, updated, skipped) {
    const allOk = results.every(r => r.ok);
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
        <h2>Importacion completada</h2>
        <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
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

        ${created > 0 ? `
        <div style="background:#FFF7ED;border-radius:8px;padding:14px;border:1px solid #FED7AA;">
          <div style="font-weight:700;color:#92400E;font-size:13px;margin-bottom:8px;">
            Que quieres hacer con los ${created} activos importados?
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button class="btn btn-primary" onclick="ViewAssets._postImportAnalyze(); this.closest('.modal-overlay').remove();">
              Analizar riesgos activo a activo
            </button>
            <button class="btn btn-secondary" onclick="App.navigate('assets'); document.querySelector('[data-tab=grouping]')?.click(); this.closest('.modal-overlay').remove();">
              Agrupar con IA primero
            </button>
            <button class="btn btn-ghost" onclick="this.closest('.modal-overlay').remove();">
              Solo ver inventario
            </button>
          </div>
          <p style="font-size:11px;color:#9D9D9D;margin:8px 0 0;">
            <strong>Agrupar primero</strong> consolida activos similares y genera un analisis de riesgos por grupo.
            <strong>Analizar directo</strong> genera riesgos individuales para cada activo importado.
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
        UI.toast(`Analisis IA lanzado para ${r.total} activos`, 'success');
        ViewAssets._reload();
        ViewAssets._startPollIfNeeded();
      }
    } catch (e) {
      UI.toast('Error lanzando analisis: ' + e.message, 'error');
    }
  },

  _setupDrop(container) {
    // Crear zona de drop invisible sobre el contenedor
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
        <div style="font-size:40px;margin-bottom:12px;">📂</div>
        <div style="font-size:18px;font-weight:700;color:var(--brand-purple);">
          Suelta aqui para importar
        </div>
        <div style="font-size:13px;color:#9D9D9D;margin-top:6px;">
          CSV, XLSX, JSON, TSV u otro — la IA normaliza las columnas automaticamente
        </div>
      </div>`;
    document.body.appendChild(overlay);

    // Escuchar drag events en toda la ventana mientras la vista esté activa
    const onDragEnter = (e) => {
      if (!e.dataTransfer.types.includes('Files')) return;
      dragCount++;
      overlay.style.display = 'flex';
    };
    const onDragLeave = () => {
      dragCount--;
      if (dragCount <= 0) { dragCount = 0; overlay.style.display = 'none'; }
    };
    const onDragOver = (e) => {
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
    window.addEventListener('dragover', onDragOver);
    window.addEventListener('drop', onDrop);

    // Limpiar listeners cuando se navegue fuera
    const observer = new MutationObserver(() => {
      if (!document.body.contains(container)) {
        window.removeEventListener('dragenter', onDragEnter);
        window.removeEventListener('dragleave', onDragLeave);
        window.removeEventListener('dragover', onDragOver);
        window.removeEventListener('drop', onDrop);
        overlay.remove();
        observer.disconnect();
      }
    });
    observer.observe(document.getElementById('main') || document.body, { childList: true });
  },
};
