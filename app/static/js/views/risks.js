/* Vista Riesgos - identificación, analisis, evaluación, tratamiento. */
const ViewRisks = {
  _assets: [], _threats: [], _vulns: [], _impls: [],
  _assetFilter: null, // { id, name } cuando se filtra por activo desde la vista de activos
  _sortCol: 'residual_level', _sortAsc: false, // orden por defecto: residual desc

  async render(main) {
    const canEdit = Auth.canEdit();

    // Leer parametros de URL
    const assetMatch = location.hash.match(/[?&]asset_id=(\d+)/);
    const threatMatch = location.hash.match(/[?&]threat_id=(\d+)/);
    const vulnMatch = location.hash.match(/[?&]vulnerability_id=(\d+)/);
    const ownerParam = (location.hash.match(/[?&]owner=([^&]+)/) || [])[1] || null;
    const overdueParam = /[?&]overdue=1/.test(location.hash);
    ViewRisks._assetFilter = null;
    ViewRisks._threatFilter = null;
    ViewRisks._vulnFilter = null;

    main.innerHTML = UI.sectionHeader(
      'Registro de riesgos',
      'ISO/IEC 27005:2018 cl. 8-9 — identificación, análisis, tratamiento',
      canEdit ? '<button class="btn btn-primary" id="btn-new">+ Nuevo riesgo</button>' : ''
    ) + `
      <div class="toolbar">
        <input type="search" id="r-search" placeholder="Buscar por activo o amenaza...">
        <select id="r-status">
          <option value="">Cualquier estado</option>
          <option value="identified">Identificado</option>
          <option value="assessed">Evaluado</option>
          <option value="treated">Tratado</option>
          <option value="accepted">Aceptado</option>
          <option value="closed">Cerrado</option>
        </select>
        <select id="r-band">
          <option value="">Cualquier nivel</option>
          <option value="6">Solo altos (6+)</option>
          <option value="3">Medios y altos (3+)</option>
        </select>
        <select id="r-owner">
          <option value="">Cualquier responsable</option>
        </select>
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;white-space:nowrap;">
          <input type="checkbox" id="r-overdue"> Solo vencidos
        </label>
        <button class="btn btn-ghost" id="r-export-csv" title="Exportar tabla como CSV" style="margin-left:auto;">Exportar CSV</button>
        ${canEdit ? `
        <button class="btn btn-ghost" id="r-import-tpl" title="Descargar plantilla CSV de importacion">Plantilla</button>
        <label class="btn btn-ghost" style="cursor:pointer;margin:0;" title="Importar riesgos desde CSV">
          Importar CSV
          <input type="file" id="r-import-file" accept=".csv" style="display:none;">
        </label>` : ''}
      </div>
      <div id="r-asset-filter" style="display:none;margin-bottom:8px;"></div>
      <div id="r-list"></div>
    `;
    if (canEdit) document.getElementById('btn-new').onclick = () => ViewRisks._edit();
    document.getElementById('r-search').oninput = () => ViewRisks._reload();
    document.getElementById('r-status').onchange = () => ViewRisks._reload();
    document.getElementById('r-band').onchange = () => ViewRisks._reload();
    document.getElementById('r-owner').onchange = () => ViewRisks._reload();
    document.getElementById('r-overdue').onchange = () => ViewRisks._reload();
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

    await ViewRisks._reload();

    // Atajo desde heatmap: ?id=X
    const m = location.hash.match(/[?&]id=(\d+)/);
    if (m) ViewRisks._edit(parseInt(m[1]));
  },

  _clearAssetFilter() {
    ViewRisks._assetFilter = null;
    ViewRisks._threatFilter = null;
    ViewRisks._vulnFilter = null;
    document.getElementById('r-asset-filter').style.display = 'none';
    location.hash = '#/risks';
    ViewRisks._reload();
  },

  _users: [], _threatFilter: null, _vulnFilter: null,
  _selected: new Set(),

  async _loadCatalogs() {
    try {
      const [a, t, v, i, u, meth] = await Promise.all([
        Api.assets.list({}), Api.threats.list({}),
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
        unassigned.textContent = 'Sin responsable';
        ownerSel.appendChild(unassigned);
      }
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  async _reload() {
    const search = document.getElementById('r-search').value.toLowerCase();
    const status = document.getElementById('r-status').value;
    const band = document.getElementById('r-band').value;
    const list = document.getElementById('r-list');
    list.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      const overdue = document.getElementById('r-overdue')?.checked;
      const ownerVal = document.getElementById('r-owner')?.value || '';
      const params = {};
      if (status) params.status = status;
      if (band) params.min_level = band;
      if (ViewRisks._assetFilter) params.asset_id = ViewRisks._assetFilter.id;
      if (ViewRisks._threatFilter) params.threat_id = ViewRisks._threatFilter.id;
      if (ViewRisks._vulnFilter) params.vulnerability_id = ViewRisks._vulnFilter.id;
      if (overdue) params.overdue = true;
      if (ownerVal && ownerVal !== '__unassigned__') params.owner_id = ownerVal;
      let data = await Api.risks.list(params);
      // Client-side filter for unassigned
      if (ownerVal === '__unassigned__') {
        data = data.filter(r => !r.owner_id);
      }
      if (search) {
        data = data.filter(r =>
          (r.asset && r.asset.name.toLowerCase().includes(search)) ||
          (r.threat && r.threat.name.toLowerCase().includes(search)) ||
          r.code.toLowerCase().includes(search));
      }
      if (!data.length) {
        list.innerHTML = UI.emptyState(
          'Sin riesgos',
          'Crea uno asociando un activo con una amenaza, o ajusta los filtros.');
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

      const _th = (col, label, title) => {
        const active = ViewRisks._sortCol === col;
        const arrow = active ? (ViewRisks._sortAsc ? ' ▲' : ' ▼') : '';
        return `<th style="cursor:pointer;user-select:none;white-space:nowrap;${active?'color:var(--brand-purple);':''}"
                    data-sort="${col}" title="${title||label}">${label}${arrow}</th>`;
      };

      ViewRisks._selected.clear();
      const now = new Date();
      const canEdit = Auth.canEdit();
      list.innerHTML = `<div class="table-wrap"><table class="data" id="r-table">
        <thead>
          <tr>
            ${canEdit ? '<th style="width:28px;"><input type="checkbox" id="r-chk-all" title="Seleccionar todos"></th>' : ''}
            ${_th('code','Codigo')}${_th('asset','Activo')}${_th('threat','Amenaza')}
            ${_th('inherent_level','Inh.','Nivel inherente')}${_th('residual_level','Res.','Nivel residual')}${_th('reduction','Red.','Reduccion inherente → residual')}
            ${_th('status','Estado')}${_th('treatment','Tratamiento')}${_th('owner','Responsable','width:110px;')}<th></th>
          </tr>
        </thead>
        <tbody>
          ${data.map(r => {
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
              <td><button class="btn btn-ghost" data-edit="${r.id}" onclick="event.stopPropagation()">Ver</button></td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>
      <div id="r-bulk-bar" class="bulk-bar" style="display:none;">
        <span id="r-bulk-count" style="font-weight:600;"></span>
        <select id="r-bulk-status" style="font-size:13px;">
          <option value="">Cambiar estado a...</option>
          <option value="identified">Identificado</option>
          <option value="assessed">Evaluado</option>
          <option value="treated">Tratado</option>
          <option value="accepted">Aceptado</option>
          <option value="closed">Cerrado</option>
        </select>
        <select id="r-bulk-treat" style="font-size:13px;">
          <option value="">Cambiar tratamiento a...</option>
          <option value="modification">Modificacion</option>
          <option value="retention">Retencion</option>
          <option value="avoidance">Evitacion</option>
          <option value="sharing">Transferencia</option>
        </select>
        <select id="r-bulk-owner" style="font-size:13px;">
          <option value="">Asignar responsable...</option>
          <option value="__none__">Sin responsable</option>
          ${ViewRisks._users.map(u => `<option value="${u.id}">${UI.esc(u.full_name || u.email)}</option>`).join('')}
        </select>
        <button class="btn btn-primary" id="r-bulk-apply">Aplicar</button>
        <button class="btn btn-ghost" id="r-bulk-clear">Limpiar seleccion</button>
      </div>`;

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
      count.textContent = `${n} riesgo${n > 1 ? 's' : ''} seleccionado${n > 1 ? 's' : ''}`;
    }
  },

  async _bulkApply() {
    const ids = [...ViewRisks._selected];
    if (!ids.length) return;
    const newStatus = document.getElementById('r-bulk-status').value;
    const newTreat = document.getElementById('r-bulk-treat').value;
    const newOwner = document.getElementById('r-bulk-owner')?.value || '';
    if (!newStatus && !newTreat && !newOwner) {
      UI.toast('Selecciona al menos un cambio (estado, tratamiento o responsable)', 'error');
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

    UI.modal(id ? `${r.code} - ${r.asset?.name || ''}` : 'Nuevo riesgo', `
      <div class="span2 notice">
        Riesgo = Activo × Amenaza.
        ${isMagerit
          ? `<strong>Metodología MAGERIT v3</strong>: consecuencia calculada desde las 5 dimensiones DIACAT del activo × degradación.`
          : `Nivel calculado como Consecuencia × Probabilidad (matriz 5x5 ISO 27005 Annex E.2).`}
      </div>
      <div>
        <label>Activo *</label>
        <select id="f-asset" ${id?'disabled':''} onchange="${isMagerit?'ViewRisks._updateMageritPreview()':''}">
          ${ViewRisks._assets.map(a => `<option value="${a.id}" ${r.asset_id===a.id?'selected':''}>${UI.esc(a.code)} - ${UI.esc(a.name)}</option>`).join('')}
        </select>
      </div>
      <div>
        <label>Amenaza *</label>
        <select id="f-threat" ${id?'disabled':''}>
          ${ViewRisks._threats.map(t => `<option value="${t.id}" ${r.threat_id===t.id?'selected':''}>${UI.esc(t.code)} - ${UI.esc(t.name)}</option>`).join('')}
        </select>
      </div>
      <div class="span2">
        <label>Descripción del escenario</label>
        <textarea id="f-desc" rows="2">${UI.esc(r.description||'')}</textarea>
      </div>
      <div class="span2">
        <label>Consecuencias esperadas</label>
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
        <label>Vulnerabilidades asociadas (multi-selección)</label>
        <select id="f-vulns" multiple size="5" style="height:auto;">
          ${ViewRisks._vulns.map(v => `<option value="${v.id}" ${r.vulnerability_ids?.includes(v.id)?'selected':''}>${UI.esc(v.code)} - ${UI.esc(v.name)}</option>`).join('')}
        </select>
      </div>
      <div class="span2">
        <label>Controles implementados que mitigan (multi-selección)</label>
        <select id="f-impls" multiple size="5" style="height:auto;">
          ${ViewRisks._impls.map(c => `<option value="${c.id}" ${r.control_implementation_ids?.includes(c.id)?'selected':''}>${UI.esc(c.name)} (madurez ${c.maturity}/5, ${UI.controlStatusLabel(c.status)})</option>`).join('')}
        </select>
      </div>
      <div>
        <label>Estado</label>
        <select id="f-status">
          ${['identified','assessed','treated','accepted','closed'].map(s =>
            `<option value="${s}" ${r.status===s?'selected':''}>${UI.statusLabel(s)}</option>`).join('')}
        </select>
      </div>
      <div>
        <label>Decisión de tratamiento</label>
        <select id="f-treat">
          <option value="">-</option>
          ${['modification','retention','avoidance','sharing'].map(t =>
            `<option value="${t}" ${r.treatment_option===t?'selected':''}>${UI.treatmentLabel(t)}</option>`).join('')}
        </select>
      </div>
      <div class="span2">
        <label>Plan de tratamiento</label>
        <textarea id="f-plan" rows="2">${UI.esc(r.treatment_plan||'')}</textarea>
      </div>
      <div>
        <label>Responsable del riesgo</label>
        <select id="f-owner">
          <option value="">- Sin asignar -</option>
          ${ViewRisks._users.map(u =>
            `<option value="${u.id}" ${r.owner_id===u.id?'selected':''}>${UI.esc(u.full_name||u.email)}</option>`
          ).join('')}
        </select>
      </div>
      <div>
        <label>Fecha limite del plan</label>
        <input type="date" id="f-due" value="${r.treatment_due_date ? r.treatment_due_date.slice(0,10) : ''}">
      </div>
      <div class="span2" id="f-just-wrap" style="${r.status==='accepted'?'':'opacity:0.6;'}">
        <label>Justificación de aceptación ${r.status==='accepted'?'<span style="color:var(--risk-high);">*</span>':'(si aplica)'}</label>
        <textarea id="f-just" rows="2">${UI.esc(r.acceptance_justification||'')}</textarea>
      </div>
      ${id ? `
      <div class="span2 notice ${r.residual_level <= 2 ? '' : 'notice-warn'}">
        Nivel inherente actual: <strong>${r.inherent_level}</strong> &nbsp;→&nbsp;
        Nivel residual actual: <strong>${r.residual_level}</strong>
        ${r.inherent_level > 0 ? `&nbsp;<span style="font-size:12px;color:var(--risk-low);">(-${Math.round((1-r.residual_level/r.inherent_level)*100)}% reduccion)</span>` : ''}
        ${r.asset && r.asset.monetary_value ? (() => {
          const ale = Math.round(r.asset.monetary_value * (r.residual_level / 8));
          const aleFmt = ale.toLocaleString('es-ES', { style: 'currency', currency: 'EUR', minimumFractionDigits: 0 });
          return `<br><span style="font-size:12px;">ALE estimado (FAIR): <strong>${aleFmt}</strong> <span style="color:var(--text-muted);">(valor activo × nivel residual/8)</span></span>`;
        })() : ''}
        ${r.accepted_at ? `<br><span style="font-size:12px;">Aceptado el ${new Date(r.accepted_at).toLocaleString('es-ES')}</span>` : ''}
        ${r.treatment_due_date ? `<br><span style="font-size:12px;">Fecha limite: <strong>${new Date(r.treatment_due_date).toLocaleDateString('es-ES')}</strong></span>` : ''}
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
        <button class="btn" id="m-cancel">Cerrar</button>
        ${id ? '<button class="btn btn-ghost" id="m-bowtie" title="Ver diagrama Bow-Tie de causas y consecuencias">Bow-Tie</button>' : ''}
        ${id ? '<button class="btn btn-ghost" id="m-clone" title="Crear una copia de este riesgo">Duplicar</button>' : ''}
        ${id ? '<button class="btn btn-danger" id="m-del">Eliminar</button>' : ''}
        <button class="btn btn-primary" id="m-save">Guardar</button>
      ` : `<button class="btn" id="m-cancel">Cerrar</button>
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

    if (id && canEdit) document.getElementById('m-del').onclick = async () => {
      if (!await UI.confirm('Eliminar este riesgo?')) return;
      try { await Api.risks.del(id); UI.closeModal(); UI.toast('Eliminado','success'); ViewRisks._reload(); }
      catch (e) { UI.toast(e.message, 'error'); }
    };
    // Resaltar campo justificacion cuando se selecciona "accepted"
    const statusSel = document.getElementById('f-status');
    if (statusSel) statusSel.addEventListener('change', () => {
      const wrap = document.getElementById('f-just-wrap');
      const lbl = wrap?.querySelector('label');
      if (statusSel.value === 'accepted') {
        if (wrap) wrap.style.opacity = '1';
        if (lbl) lbl.innerHTML = 'Justificación de aceptación <span style="color:var(--risk-high);">*</span>';
      } else {
        if (wrap) wrap.style.opacity = '0.6';
        if (lbl) lbl.textContent = 'Justificación de aceptación (si aplica)';
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
        UI.closeModal(); UI.toast('Guardado','success'); ViewRisks._reload();
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
      actions: `<button class="btn" id="m-cancel">Cerrar</button>
                <button class="btn btn-ghost" id="m-back">Volver al riesgo</button>`
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

      const consLabels = ['Insignificante','Menor','Moderado','Mayor','Crítico'];
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
};
