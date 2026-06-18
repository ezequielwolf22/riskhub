/* Vista de gestion de proveedores / supply chain risk (NIS2 Art. 21.2.d). */
const ViewSuppliers = (() => {

  const RISK_LABELS = {
    low: 'Bajo', medium: 'Medio', high: 'Alto', critical: 'Critico',
  };
  const RISK_COLORS = {
    low: 'var(--risk-low)', medium: 'var(--risk-medium)',
    high: 'var(--risk-high)', critical: 'var(--risk-critical)',
  };

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  let _activeSupTab = 'suppliers';
  let _selectedIds = new Set();

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Proveedores y Cadena de Suministro</h1>
          <p class="page-sub">Gestion de riesgo de terceros — NIS2 Art. 21.2.d / ISO 27001 A.15</p>
        </div>
        <div style="display:flex;gap:8px;" id="sup-header-actions"></div>
      </div>

      <div class="stats-row" id="sup-stats" style="margin-bottom:16px;"></div>

      <div style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:16px;flex-wrap:wrap;">
        <button class="tab-btn" id="suptab-suppliers" onclick="SupTab('suppliers')">Proveedores</button>
        <button class="tab-btn" id="suptab-questionnaires" onclick="SupTab('questionnaires')">Cuestionarios</button>
        <button class="tab-btn" id="suptab-schedules" onclick="SupTab('schedules')">Planificaciones</button>
        <button class="tab-btn" id="suptab-flows" onclick="SupTab('flows')">Flujos</button>
      </div>
      <div id="sup-tab-content"></div>
    `;

    window.SupTab = function(t) { _setSupTab(t); };

    await _loadStats();
    _setSupTab(_activeSupTab);
  }

  function _setSupTab(tab) {
    _activeSupTab = tab;
    ['suppliers','questionnaires','schedules','flows'].forEach(t => {
      const btn = document.getElementById('suptab-' + t);
      if (!btn) return;
      btn.style.cssText = `padding:8px 20px;font-size:13px;font-weight:600;border:none;
        background:none;cursor:pointer;border-bottom:3px solid ${t===tab?'var(--brand-purple)':'transparent'};
        color:${t===tab?'var(--brand-purple)':'var(--text-muted)'};margin-bottom:-2px;`;
    });
    const actions = document.getElementById('sup-header-actions');
    if (actions) {
      if (tab === 'suppliers') {
        actions.innerHTML = (Auth.canEdit() ? '<button class="btn" id="btn-import-sup">Importar</button> ' : '')
          + '<button class="btn btn-primary" id="btn-new-sup">+ Nuevo proveedor</button>';
        document.getElementById('btn-new-sup').onclick = () => _openForm(null);
        const impBtn = document.getElementById('btn-import-sup');
        if (impBtn) impBtn.onclick = () => _openImport();
      } else if (tab === 'questionnaires') {
        actions.innerHTML = Auth.canEdit() ? '<button class="btn btn-primary" id="btn-new-seq">+ Nuevo cuestionario</button>' : '';
        if (Auth.canEdit()) document.getElementById('btn-new-seq').onclick = () => _openSeqForm(null);
      } else if (tab === 'schedules') {
        actions.innerHTML = Auth.canEdit() ? '<button class="btn btn-primary" id="btn-new-sched">+ Nueva planificacion</button>' : '';
        if (Auth.canEdit()) document.getElementById('btn-new-sched').onclick = () => _openScheduleForm(null);
      } else if (tab === 'flows') {
        actions.innerHTML = Auth.canEdit() ? '<button class="btn btn-primary" id="btn-new-flow">+ Nuevo flujo</button>' : '';
        if (Auth.canEdit()) document.getElementById('btn-new-flow').onclick = () => _openFlowForm(null);
      } else {
        actions.innerHTML = '';
      }
    }
    _selectedIds.clear();
    if (tab === 'suppliers') _renderSuppliersTab();
    else if (tab === 'questionnaires') _renderQuestionnairesTab();
    else if (tab === 'schedules') _renderSchedulesTab();
    else if (tab === 'flows') _renderFlowsTab();
  }

  async function _renderSuppliersTab() {
    const wrap = document.getElementById('sup-tab-content');
    wrap.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <select id="f-risk" class="input" style="width:160px;">
          <option value="">Todos los niveles</option>
          <option value="critical">Critico</option>
          <option value="high">Alto</option>
          <option value="medium">Medio</option>
          <option value="low">Bajo</option>
        </select>
        <select id="f-critical" class="input" style="width:160px;">
          <option value="">Todos</option>
          <option value="1">Solo criticos</option>
          <option value="0">No criticos</option>
        </select>
        <input id="f-q" class="input" placeholder="Buscar..." style="width:200px;">
      </div>
      <div id="sup-table-wrap"></div>
    `;
    document.getElementById('f-risk').onchange = _refresh;
    document.getElementById('f-critical').onchange = _refresh;
    let debounce;
    document.getElementById('f-q').oninput = () => { clearTimeout(debounce); debounce = setTimeout(_refresh, 300); };
    await _refresh();
  }

  async function _loadStats() {
    try {
      const s = await Api.suppliers.summary();
      const wrap = document.getElementById('sup-stats');
      if (!wrap) return;
      wrap.innerHTML = `
        <div class="stat-card"><div class="stat-value">${s.total}</div><div class="stat-label">Total proveedores</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-critical);">${s.critical_or_high}</div><div class="stat-label">Criticos / Altos</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.overdue_assessment}</div><div class="stat-label">Evaluacion vencida</div></div>
      `;
    } catch (_) {}
  }

  async function _refresh() {
    const riskLevel = document.getElementById('f-risk')?.value || '';
    const criticalFilter = document.getElementById('f-critical')?.value || '';
    const q = document.getElementById('f-q')?.value.trim() || '';
    const wrap = document.getElementById('sup-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<p class="text-muted">Cargando...</p>';
    try {
      const params = {};
      if (riskLevel) params.risk_level = riskLevel;
      if (q) params.q = q;
      let data = await Api.suppliers.list(params);
      if (criticalFilter === '1') data = data.filter(s => s.is_critical);
      else if (criticalFilter === '0') data = data.filter(s => !s.is_critical);
      _renderTable(wrap, data);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _updateBulkBar() {
    const bar = document.getElementById('sup-bulk-bar');
    if (!bar) return;
    const n = _selectedIds.size;
    bar.style.display = n > 0 ? 'flex' : 'none';
    const countEl = document.getElementById('sup-sel-count');
    if (countEl) countEl.textContent = `${n} seleccionado${n !== 1 ? 's' : ''}`;
  }

  async function _bulkRecompute() {
    const ids = [..._selectedIds];
    if (!ids.length) return;
    try {
      const r = await Api.suppliers.bulkRecompute(ids);
      UI.toast(`${r.recomputed} proveedores recalculados`, 'success');
      _selectedIds.clear();
      await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  async function _bulkDelete() {
    const ids = [..._selectedIds];
    if (!ids.length) return;
    if (!confirm(`Eliminar ${ids.length} proveedor${ids.length !== 1 ? 'es' : ''}?`)) return;
    try {
      const r = await Api.suppliers.bulkDelete(ids);
      UI.toast(`${r.deleted} proveedores eliminados`, 'success');
      _selectedIds.clear();
      await _loadStats();
      await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  function _renderTable(wrap, data) {
    if (!data.length) {
      wrap.innerHTML = '<p class="text-muted" style="margin-top:24px;text-align:center;">No se encontraron proveedores.</p>';
      return;
    }
    const canEdit = Auth.canEdit();
    const rows = data.map(s => {
      const assessed = s.last_assessment_at ? s.last_assessment_at.slice(0, 10) : '-';
      const next = s.next_assessment_at ? s.next_assessment_at.slice(0, 10) : '-';
      const tier = s.tier ? _badge(RISK_LABELS[s.tier] || s.tier, RISK_COLORS[s.tier] || '#888') : '-';
      const inh = (s.inherent_risk_score ?? null) !== null ? s.inherent_risk_score : '-';
      const res = (s.residual_risk_score ?? null) !== null ? s.residual_risk_score : '-';
      const checked = _selectedIds.has(s.id) ? 'checked' : '';
      const critBadge = s.is_critical
        ? `<span style="display:inline-block;padding:2px 7px;border-radius:999px;font-size:10px;font-weight:700;background:#DC2626;color:#fff;">CRITICO</span>`
        : `<span style="display:inline-block;padding:2px 7px;border-radius:999px;font-size:10px;font-weight:600;background:var(--bg-2);color:var(--text-muted);border:1px solid var(--border);">Normal</span>`;
      return `
        <tr>
          <td style="width:36px;text-align:center;">
            <input type="checkbox" class="sup-chk" data-id="${s.id}" ${checked}
              style="width:15px;height:15px;cursor:pointer;accent-color:var(--brand-purple);">
          </td>
          <td><b>${UI.esc(s.code)}</b></td>
          <td>${UI.esc(s.name)}</td>
          <td>${critBadge}</td>
          <td>${tier}</td>
          <td style="text-align:center;font-weight:700;">${inh}</td>
          <td style="text-align:center;font-weight:700;">${res}</td>
          <td>${assessed}</td>
          <td>${next}</td>
          <td>
            ${canEdit ? `<button class="btn btn-sm" data-id="${s.id}" data-action="recompute" title="Recalcular tier y riesgo">Recalcular</button>` : ''}
            <button class="btn btn-sm" data-id="${s.id}" data-action="edit">Editar</button>
            ${canEdit ? `<button class="btn btn-sm btn-danger" data-id="${s.id}" data-action="del">Eliminar</button>` : ''}
          </td>
        </tr>
      `;
    }).join('');

    const allChecked = data.length > 0 && data.every(s => _selectedIds.has(s.id));
    wrap.innerHTML = `
      <div id="sup-bulk-bar" style="display:none;align-items:center;gap:10px;padding:8px 12px;
          background:var(--bg-2);border:1px solid var(--brand-purple);border-radius:6px;margin-bottom:10px;">
        <span id="sup-sel-count" style="font-size:13px;font-weight:600;color:var(--brand-purple);"></span>
        ${canEdit ? `
        <button id="btn-bulk-recompute" class="btn btn-sm" style="margin-left:4px;">Recalcular seleccionados</button>
        <button id="btn-bulk-del" class="btn btn-sm btn-danger">Eliminar seleccionados</button>
        ` : ''}
        <button id="btn-bulk-clear" class="btn btn-sm" style="margin-left:auto;">Deseleccionar todo</button>
      </div>
      <table class="data">
        <thead>
          <tr>
            <th style="width:36px;text-align:center;">
              <input type="checkbox" id="sup-chk-all" ${allChecked ? 'checked' : ''}
                style="width:15px;height:15px;cursor:pointer;accent-color:var(--brand-purple);"
                title="Seleccionar todo">
            </th>
            <th>Codigo</th><th>Nombre</th><th>Tag</th><th>Tier</th><th>Inherent</th><th>Residual</th>
            <th>Ult. evaluacion</th><th>Prox. evaluacion</th><th>Acciones</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;

    _updateBulkBar();

    document.getElementById('sup-chk-all').onchange = (e) => {
      if (e.target.checked) data.forEach(s => _selectedIds.add(s.id));
      else data.forEach(s => _selectedIds.delete(s.id));
      wrap.querySelectorAll('.sup-chk').forEach(cb => { cb.checked = e.target.checked; });
      _updateBulkBar();
    };

    wrap.querySelectorAll('.sup-chk').forEach(cb => {
      cb.onchange = () => {
        const id = parseInt(cb.dataset.id);
        if (cb.checked) _selectedIds.add(id);
        else _selectedIds.delete(id);
        const chkAll = document.getElementById('sup-chk-all');
        if (chkAll) chkAll.checked = data.every(s => _selectedIds.has(s.id));
        _updateBulkBar();
      };
    });

    const bulkDelBtn = document.getElementById('btn-bulk-del');
    if (bulkDelBtn) bulkDelBtn.onclick = _bulkDelete;
    const bulkRcpBtn = document.getElementById('btn-bulk-recompute');
    if (bulkRcpBtn) bulkRcpBtn.onclick = _bulkRecompute;
    document.getElementById('btn-bulk-clear').onclick = () => {
      _selectedIds.clear();
      wrap.querySelectorAll('.sup-chk').forEach(cb => { cb.checked = false; });
      const chkAll = document.getElementById('sup-chk-all');
      if (chkAll) chkAll.checked = false;
      _updateBulkBar();
    };

    wrap.querySelectorAll('[data-action="recompute"]').forEach(btn => {
      btn.onclick = async () => {
        try {
          await Api.tprm.recompute(btn.dataset.id);
          UI.toast('Riesgo recalculado', 'success');
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });

    wrap.querySelectorAll('[data-action="edit"]').forEach(btn => {
      btn.onclick = () => {
        const sup = data.find(s => s.id == btn.dataset.id);
        if (sup) _openForm(sup);
      };
    });
    wrap.querySelectorAll('[data-action="del"]').forEach(btn => {
      btn.onclick = async () => {
        if (!confirm('Eliminar proveedor?')) return;
        try {
          await Api.suppliers.del(btn.dataset.id);
          UI.toast('Proveedor eliminado', 'success');
          _selectedIds.delete(parseInt(btn.dataset.id));
          await _loadStats();
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });
  }

  function _formHtml(s) {
    const v = s || {};
    return `
      <div class="form-grid">
        <div><label>Nombre *</label><input id="f-name" class="input" value="${UI.esc(v.name || '')}"></div>
        <div><label>Categoria</label><input id="f-cat" class="input" value="${UI.esc(v.category || '')}" placeholder="Software, Hardware, Servicios..."></div>
        <div><label>Nivel de riesgo</label>
          <select id="f-risk-level" class="input">
            ${Object.entries(RISK_LABELS).map(([k,l]) => `<option value="${k}" ${v.risk_level===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="checkbox" id="f-critical" ${v.is_critical?'checked':''}>
          <label for="f-critical" style="margin:0;cursor:pointer;">Proveedor critico NIS2</label>
        </div>
        <div><label>Contacto principal</label><input id="f-contact" class="input" value="${UI.esc(v.contact_name || '')}"></div>
        <div><label>Email principal</label><input id="f-email" class="input" type="email" value="${UI.esc(v.contact_email || '')}"></div>
        <div><label>CC (alertas y cuestionarios)</label><input id="f-cc-email" class="input" type="email" value="${UI.esc(v.cc_email || '')}" placeholder="responsable@empresa.com"></div>
        <div><label>Ultima evaluacion</label><input type="date" id="f-last-assess" class="input" value="${v.last_assessment_at ? v.last_assessment_at.slice(0,10) : ''}"></div>
        <div><label>Proxima evaluacion</label><input type="date" id="f-next-assess" class="input" value="${v.next_assessment_at ? v.next_assessment_at.slice(0,10) : ''}"></div>
        <div><label>Contrato / referencia</label><input id="f-contract" class="input" value="${UI.esc(v.contract_ref || '')}"></div>
        <div class="span2"><label>Notas / descripcion</label><textarea id="f-notes" class="input" rows="3">${UI.esc(v.notes || '')}</textarea></div>

        <!-- Contactos adicionales -->
        <div class="span2" style="margin-top:8px;border-top:1px solid var(--border);padding-top:10px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <div>
              <strong style="font-size:13px;color:var(--brand-purple);">Contactos adicionales</strong>
              <p style="font-size:11px;color:var(--text-muted);margin:2px 0 0;">Responsables tecnicos, legales o de compras. Se incluyen en CC de cuestionarios y alertas.</p>
            </div>
            <button type="button" id="sup-add-contact" class="btn btn-sm">+ Anadir</button>
          </div>
          <div id="sup-contact-list"></div>
        </div>

        <!-- Datos internos -->
        <div class="span2" style="margin-top:8px;border-top:1px solid var(--border);padding-top:10px;">
          <strong style="font-size:13px;color:var(--brand-purple);">Datos internos de clasificacion</strong>
          <p style="font-size:11px;color:var(--text-muted);margin:2px 0 0;">Informacion interna para filtros avanzados y reportes.</p>
        </div>
        <div><label>Ubicacion / sede</label><input id="f-location" class="input" value="${UI.esc(v.location || '')}" placeholder="Madrid, ES"></div>
        <div><label>Departamento responsable</label><input id="f-department" class="input" value="${UI.esc(v.department || '')}" placeholder="TI, Legal, Compras..."></div>
        <div><label>Importancia negocio (1-5)</label><input type="number" min="1" max="5" id="f-biz-imp" class="input" value="${v.business_importance || ''}"></div>
        <div><label>Responsable interno</label><select id="f-internal-owner" class="input"><option value="">- Sin asignar -</option></select></div>

        <div class="span2" style="margin-top:8px;border-top:1px solid var(--border);padding-top:10px;">
          <strong style="font-size:13px;color:var(--brand-purple);">TPRM — Perfil de riesgo inherente</strong>
          <p style="font-size:11px;color:var(--text-muted);margin:2px 0 0;">El tier y el inherent/residual risk se recalculan automaticamente al guardar.</p>
        </div>
        <div><label>Tipo de proveedor</label>
          <select id="f-vendor-type" class="input">
            ${['technology','cloud_provider','professional_services','consultancy','hardware','subcontractor','other'].map(o => `<option value="${o}" ${v.vendor_type===o?'selected':''}>${o}</option>`).join('')}
          </select>
        </div>
        <div><label>Acceso a sistemas</label>
          <select id="f-access" class="input">
            ${['none','api_only','saas','paas','iaas','on_prem','read_write','admin_to_our_systems'].map(o => `<option value="${o}" ${v.system_access_type===o?'selected':''}>${o}</option>`).join('')}
          </select>
        </div>
        <div><label>Sensibilidad de datos (1-5)</label><input type="number" min="1" max="5" id="f-data-sens" class="input" value="${v.data_sensitivity || 2}"></div>
        <div><label>Volumen de datos (1-5)</label><input type="number" min="1" max="5" id="f-data-vol" class="input" value="${v.data_volume || 2}"></div>
        <div><label>Criticidad para el negocio (1-5)</label><input type="number" min="1" max="5" id="f-biz-crit" class="input" value="${v.business_criticality || 3}"></div>
        <div><label>Riesgo geografico (1-5)</label><input type="number" min="1" max="5" id="f-geo" class="input" value="${v.geographic_risk || 1}"></div>
        <div class="span2" style="display:flex;flex-wrap:wrap;gap:16px;">
          <label style="display:flex;align-items:center;gap:6px;margin:0;"><input type="checkbox" id="f-proc" ${v.is_data_processor?'checked':''}> Encargado GDPR</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;"><input type="checkbox" id="f-pii" ${v.processes_personal_data?'checked':''}> Trata datos personales</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;"><input type="checkbox" id="f-nis2" ${v.is_nis2?'checked':''}> NIS2</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;"><input type="checkbox" id="f-dora" ${v.is_dora?'checked':''}> DORA</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;"><input type="checkbox" id="f-ens" ${v.is_ens?'checked':''}> ENS</label>
        </div>

        <!-- SLAs del proveedor -->
        <div class="span2" style="margin-top:12px;border-top:1px solid var(--border);padding-top:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <div>
              <strong style="font-size:13px;color:var(--brand-purple);">SLAs del proveedor</strong>
              <p style="font-size:11px;color:var(--text-muted);margin:2px 0 0;">Define los acuerdos de nivel de servicio para luego registrar incumplimientos en Hallazgos.</p>
            </div>
            <button type="button" id="sup-add-sla" class="btn btn-sm">+ Anadir SLA</button>
          </div>
          <div id="sup-sla-list"></div>
        </div>

        ${s ? `
        <!-- Documentacion adjunta (solo en edicion) -->
        <div class="span2" style="margin-top:12px;border-top:1px solid var(--border);padding-top:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <div>
              <strong style="font-size:13px;color:var(--brand-purple);">Documentacion adjunta</strong>
              <p style="font-size:11px;color:var(--text-muted);margin:2px 0 0;">Contratos, certificaciones, informes de auditoria u otros documentos del proveedor.</p>
            </div>
            <label class="btn btn-sm" style="cursor:pointer;">
              + Adjuntar
              <input type="file" id="sup-doc-upload" style="display:none;"
                accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.txt,.csv,.png,.jpg,.jpeg,.zip">
            </label>
          </div>
          <div id="sup-doc-list"><p style="font-size:12px;color:var(--text-muted);">Cargando...</p></div>
          <div id="sup-doc-desc-row" style="display:none;gap:6px;align-items:center;margin-top:6px;">
            <input id="sup-doc-desc" class="input" placeholder="Descripcion del documento (opcional)" style="flex:1;font-size:12px;">
            <button id="sup-doc-confirm" class="btn btn-sm btn-primary">Subir</button>
            <button id="sup-doc-cancel-upload" class="btn btn-sm">Cancelar</button>
          </div>
        </div>` : ''}
      </div>
    `;
  }

  let _currentSlas = [];
  let _currentContacts = [];

  let _docPendingFile = null;

  function _openForm(s) {
    _currentSlas = s?.slas ? JSON.parse(JSON.stringify(s.slas)) : [];
    _currentContacts = s?.additional_contacts ? JSON.parse(JSON.stringify(s.additional_contacts)) : [];
    UI.modal(s ? `Editar ${s.code}` : 'Nuevo proveedor', _formHtml(s), {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`,
      width: '760px',
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => _save(s);
    _renderSlaList();
    document.getElementById('sup-add-sla').onclick = _addSlaRow;
    _renderContactList();
    document.getElementById('sup-add-contact').onclick = _addContactRow;
    // Poblar select de responsable interno
    Api.users.list().then(users => {
      const sel = document.getElementById('f-internal-owner');
      if (!sel) return;
      users.forEach(u => {
        const opt = document.createElement('option');
        opt.value = u.id;
        opt.textContent = u.full_name || u.email;
        if (s && u.id === s.internal_owner_id) opt.selected = true;
        sel.appendChild(opt);
      });
    }).catch(() => {});

    if (s) {
      _loadDocuments(s.id);
      const uploadInput = document.getElementById('sup-doc-upload');
      const descRow = document.getElementById('sup-doc-desc-row');
      if (uploadInput) {
        uploadInput.onchange = () => {
          _docPendingFile = uploadInput.files[0] || null;
          if (_docPendingFile) descRow.style.display = 'flex';
        };
      }
      const confirmBtn = document.getElementById('sup-doc-confirm');
      if (confirmBtn) {
        confirmBtn.onclick = async () => {
          if (!_docPendingFile) return;
          const desc = document.getElementById('sup-doc-desc')?.value.trim() || '';
          confirmBtn.disabled = true;
          confirmBtn.textContent = 'Subiendo...';
          try {
            await Api.suppliers.uploadDocument(s.id, _docPendingFile, desc || undefined);
            UI.toast('Documento adjuntado', 'success');
            _docPendingFile = null;
            if (uploadInput) uploadInput.value = '';
            if (descRow) descRow.style.display = 'none';
            const descEl = document.getElementById('sup-doc-desc');
            if (descEl) descEl.value = '';
            _loadDocuments(s.id);
          } catch (e) {
            UI.toast(e.message, 'error');
          } finally {
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Subir';
          }
        };
      }
      const cancelUploadBtn = document.getElementById('sup-doc-cancel-upload');
      if (cancelUploadBtn) {
        cancelUploadBtn.onclick = () => {
          _docPendingFile = null;
          if (uploadInput) uploadInput.value = '';
          if (descRow) descRow.style.display = 'none';
        };
      }
    }
  }

  async function _loadDocuments(supplierId) {
    const wrap = document.getElementById('sup-doc-list');
    if (!wrap) return;
    try {
      const docs = await Api.suppliers.listDocuments(supplierId);
      if (!docs.length) {
        wrap.innerHTML = '<p style="font-size:12px;color:var(--text-muted);margin:4px 0 0;">Sin documentos adjuntos.</p>';
        return;
      }
      wrap.innerHTML = docs.map(d => {
        const size = d.size ? (d.size > 1024*1024 ? (d.size/1024/1024).toFixed(1)+' MB' : (d.size/1024).toFixed(0)+' KB') : '-';
        const date = d.uploaded_at ? new Date(d.uploaded_at).toLocaleDateString('es-ES') : '-';
        return `<div style="display:flex;align-items:center;gap:8px;padding:6px 8px;border:1px solid var(--border);border-radius:6px;margin-bottom:4px;background:var(--bg-2);">
          <div style="flex:1;min-width:0;">
            <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${UI.esc(d.filename)}</div>
            <div style="font-size:11px;color:var(--text-muted);">${size} &middot; ${date}${d.description ? ' &middot; ' + UI.esc(d.description) : ''}</div>
          </div>
          <a href="${Api.suppliers.downloadDocumentUrl(supplierId, d.id)}" target="_blank" class="btn btn-sm" title="Descargar">Descargar</a>
          ${Auth.canEdit() ? `<button class="btn btn-sm btn-danger sup-doc-del" data-doc-id="${d.id}" title="Eliminar">X</button>` : ''}
        </div>`;
      }).join('');
      wrap.querySelectorAll('.sup-doc-del').forEach(btn => {
        btn.onclick = async () => {
          if (!confirm('Eliminar este documento?')) return;
          try {
            await Api.suppliers.deleteDocument(supplierId, btn.dataset.docId);
            UI.toast('Documento eliminado', 'success');
            _loadDocuments(supplierId);
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) {
      wrap.innerHTML = `<p style="font-size:12px;color:var(--risk-high);">${UI.esc(e.message)}</p>`;
    }
  }

  // ---- SLA helpers ----

  function _slaId() {
    return 'sla_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
  }

  function _renderSlaList() {
    const wrap = document.getElementById('sup-sla-list');
    if (!wrap) return;
    if (!_currentSlas.length) {
      wrap.innerHTML = '<p style="font-size:12px;color:var(--text-muted);margin:4px 0 0;">Sin SLAs definidos.</p>';
      return;
    }
    wrap.innerHTML = _currentSlas.map((sla, i) => `
      <div style="border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin-bottom:6px;background:var(--bg-2);">
        <div style="display:flex;gap:6px;align-items:flex-start;">
          <div style="flex:1;display:grid;grid-template-columns:1fr 1fr;gap:6px;">
            <input class="input sla-name" data-idx="${i}" placeholder="Nombre SLA *" value="${UI.esc(sla.name||'')}" style="font-size:12px;">
            <input class="input sla-metric" data-idx="${i}" placeholder="Metrica / objetivo (ej: 99.9%)" value="${UI.esc(sla.metric||'')}" style="font-size:12px;">
            <select class="input sla-cat" data-idx="${i}" style="font-size:12px;">
              ${['availability','support','security','performance','recovery','other'].map(c =>
                `<option value="${c}" ${(sla.category||'other')===c?'selected':''}>${c}</option>`
              ).join('')}
            </select>
            <input class="input sla-desc" data-idx="${i}" placeholder="Descripcion breve" value="${UI.esc(sla.description||'')}" style="font-size:12px;">
          </div>
          <button type="button" class="btn btn-sm btn-danger sla-del" data-idx="${i}" style="padding:3px 8px;font-size:12px;margin-top:2px;">X</button>
        </div>
      </div>`).join('');

    // Sync changes back to _currentSlas
    wrap.querySelectorAll('.sla-name').forEach(inp => {
      inp.oninput = () => { _currentSlas[parseInt(inp.dataset.idx)].name = inp.value; };
    });
    wrap.querySelectorAll('.sla-metric').forEach(inp => {
      inp.oninput = () => { _currentSlas[parseInt(inp.dataset.idx)].metric = inp.value; };
    });
    wrap.querySelectorAll('.sla-cat').forEach(sel => {
      sel.onchange = () => { _currentSlas[parseInt(sel.dataset.idx)].category = sel.value; };
    });
    wrap.querySelectorAll('.sla-desc').forEach(inp => {
      inp.oninput = () => { _currentSlas[parseInt(inp.dataset.idx)].description = inp.value; };
    });
    wrap.querySelectorAll('.sla-del').forEach(btn => {
      btn.onclick = () => {
        _currentSlas.splice(parseInt(btn.dataset.idx), 1);
        _renderSlaList();
      };
    });
  }

  function _addSlaRow() {
    _currentSlas.push({ id: _slaId(), name: '', metric: '', category: 'other', description: '' });
    _renderSlaList();
    // Focus the last name input
    const inputs = document.querySelectorAll('.sla-name');
    if (inputs.length) inputs[inputs.length - 1].focus();
  }

  async function _save(s) {
    const name = document.getElementById('f-name').value.trim();
    if (!name) { UI.toast('El nombre es obligatorio', 'error'); return; }
    const payload = {
      name,
      category: document.getElementById('f-cat').value.trim(),
      risk_level: document.getElementById('f-risk-level').value,
      is_critical: document.getElementById('f-critical').checked,
      contact_name: document.getElementById('f-contact').value.trim(),
      contact_email: document.getElementById('f-email').value.trim(),
      last_assessment_at: document.getElementById('f-last-assess').value || null,
      next_assessment_at: document.getElementById('f-next-assess').value || null,
      contract_ref: document.getElementById('f-contract').value.trim(),
      notes: document.getElementById('f-notes').value.trim(),
      vendor_type: document.getElementById('f-vendor-type').value,
      system_access_type: document.getElementById('f-access').value,
      data_sensitivity: parseInt(document.getElementById('f-data-sens').value) || 2,
      data_volume: parseInt(document.getElementById('f-data-vol').value) || 2,
      business_criticality: parseInt(document.getElementById('f-biz-crit').value) || 3,
      geographic_risk: parseInt(document.getElementById('f-geo').value) || 1,
      is_data_processor: document.getElementById('f-proc').checked,
      processes_personal_data: document.getElementById('f-pii').checked,
      is_nis2: document.getElementById('f-nis2').checked,
      is_dora: document.getElementById('f-dora').checked,
      is_ens: document.getElementById('f-ens').checked,
      slas: _currentSlas.filter(sl => sl.name?.trim()).map(sl => ({
        id: sl.id || _slaId(),
        name: sl.name.trim(),
        metric: sl.metric?.trim() || null,
        category: sl.category || 'other',
        description: sl.description?.trim() || null,
      })),
    };
    try {
      if (s) {
        await Api.suppliers.update(s.id, payload);
        UI.toast('Proveedor actualizado', 'success');
      } else {
        await Api.suppliers.create(payload);
        UI.toast('Proveedor creado', 'success');
      }
      UI.closeModal();
      await _loadStats();
      await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  function _openImport() {
    UI.modal('Importar proveedores', `
      <div class="span2">
        <p style="font-size:13px;margin-bottom:8px;">Sube un fichero exportado desde Excel u otra herramienta de gestion (OneTrust, ERP, hoja de compras...). Formatos: <strong>CSV, XLSX, XLS, ODS, TSV, JSON</strong>.</p>
        <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">Se detectan automaticamente columnas como nombre, categoria, contacto, email, servicios, web, pais y CIF/NIF/VAT (en espanol o ingles). Los proveedores ya existentes (por nombre) se omiten. Se calcula el tier y el riesgo de cada uno tras importar.</p>
        <input type="file" id="imp-file" accept=".csv,.xlsx,.xls,.ods,.tsv,.json" class="input">
        <div id="imp-result" style="margin-top:12px;"></div>
      </div>
    `, {
      actions: `<button class="btn" id="imp-cancel">Cerrar</button>
                <button class="btn btn-primary" id="imp-go">Importar</button>`,
    });
    document.getElementById('imp-cancel').onclick = UI.closeModal;
    document.getElementById('imp-go').onclick = async () => {
      const fileInput = document.getElementById('imp-file');
      const file = fileInput.files && fileInput.files[0];
      if (!file) { UI.toast('Selecciona un fichero', 'error'); return; }
      const resWrap = document.getElementById('imp-result');
      const btn = document.getElementById('imp-go');
      btn.disabled = true;
      resWrap.innerHTML = '<p class="text-muted">Importando...</p>';
      try {
        const r = await Api.suppliers.importFile(file);
        const cols = Object.entries(r.detected_columns || {}).map(([k, v]) => `${k} &larr; "${UI.esc(v)}"`).join(', ');
        resWrap.innerHTML = `
          <div class="notice" style="border-color:var(--risk-low);">
            <strong>${r.created}</strong> proveedores creados, <strong>${r.skipped}</strong> omitidos (de ${r.total} filas).
            ${cols ? `<div style="font-size:11px;color:var(--text-muted);margin-top:6px;">Columnas detectadas: ${cols}</div>` : ''}
            ${(r.errors && r.errors.length) ? `<div style="font-size:11px;color:var(--risk-high);margin-top:6px;">Errores: ${r.errors.map(UI.esc).join('; ')}</div>` : ''}
          </div>`;
        UI.toast(`${r.created} proveedores importados`, 'success');
        await _loadStats();
        await _refresh();
      } catch (e) {
        resWrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
      } finally {
        btn.disabled = false;
      }
    };
  }

  // ======== QUESTIONNAIRES TAB ========

  async function _renderQuestionnairesTab() {
    const wrap = document.getElementById('sup-tab-content');
    wrap.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">
        <select id="seq-sup-filter" class="input" style="width:220px;">
          <option value="">Todos los proveedores</option>
        </select>
      </div>
      <div id="seq-list">Cargando...</div>
    `;
    // Populate supplier filter
    try {
      const sups = await Api.suppliers.list();
      const sel = document.getElementById('seq-sup-filter');
      if (sel) sups.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.code + ' - ' + s.name;
        sel.appendChild(opt);
      });
    } catch (_) {}
    document.getElementById('seq-sup-filter').onchange = _reloadSeq;
    await _reloadSeq();
  }

  async function _reloadSeq() {
    const supId = document.getElementById('seq-sup-filter')?.value;
    const params = {};
    if (supId) params.supplier_id = supId;
    const wrap = document.getElementById('seq-list');
    if (!wrap) return;
    try {
      const data = await Api.supplier_questionnaires.list(params);
      if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);margin-top:24px;text-align:center;">Sin cuestionarios enviados. Crea uno para enviar el enlace publico al proveedor.</p>';
        return;
      }
      const now = new Date();
      wrap.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          <th>Codigo</th><th>Titulo</th><th>Proveedor</th><th>Puntuacion</th><th>Respondido</th><th>Expira</th><th>Evaluacion IA</th><th></th>
        </tr></thead>
        <tbody>
          ${data.map(q => {
            const submitted = q.submitted_at ? new Date(q.submitted_at).toLocaleDateString('es-ES') : null;
            const expired = q.expires_at && new Date(q.expires_at) < now && !q.submitted_at;
            const expires = q.expires_at ? new Date(q.expires_at).toLocaleDateString('es-ES') : '-';
            let scoreHtml = '-';
            if (q.score !== null && q.score !== undefined) {
              const sc = q.score;
              const color = sc >= 80 ? '#22C55E' : sc >= 60 ? '#F59E0B' : '#EF4444';
              scoreHtml = `<span style="font-weight:700;color:${color};">${sc}/100</span>`;
            }
            // AI review indicator
            let aiHtml = '-';
            if (q.submitted_at) {
              if (q.ai_review && !q.ai_review.error) {
                const aiscore = q.ai_review.ai_score;
                const aicolor = aiscore >= 80 ? '#22C55E' : aiscore >= 60 ? '#F59E0B' : '#EF4444';
                const reviewedDate = q.ai_reviewed_at ? new Date(q.ai_reviewed_at).toLocaleDateString('es-ES') : '';
                aiHtml = `<span style="font-weight:700;color:${aicolor};cursor:pointer;" data-id="${q.id}" data-act="view-ai" title="Ver evaluacion IA (${reviewedDate})">${aiscore}/100</span>`;
                if (Auth.canEdit()) {
                  aiHtml += ` <button class="btn btn-sm" style="font-size:10px;padding:1px 6px;" data-id="${q.id}" data-act="eval-ai" title="Re-evaluar con IA">Re-evaluar</button>`;
                }
              } else if (Auth.canEdit()) {
                aiHtml = `<button class="btn btn-sm" style="font-size:11px;" data-id="${q.id}" data-act="eval-ai">Evaluar IA</button>`;
              }
            }
            return `<tr style="${expired?'opacity:.6;':''}">
              <td>${UI.codePill(q.code)}</td>
              <td><strong>${UI.esc(q.title)}</strong></td>
              <td style="font-size:12px;">${UI.esc(q.supplier_name||'-')}</td>
              <td>${scoreHtml}</td>
              <td style="font-size:12px;">${submitted ? submitted : (expired ? '<span style="color:#EF4444;font-size:11px;">Expirado</span>' : '<span style="color:#F59E0B;font-size:11px;">Pendiente</span>')}</td>
              <td style="font-size:12px;">${expires}</td>
              <td style="font-size:12px;">${aiHtml}</td>
              <td>
                ${Auth.canEdit() && !q.submitted_at ? `<button class="btn btn-sm" data-id="${q.id}" data-act="send" title="Enviar por email al contacto del proveedor">Enviar email</button>` : ''}
                <button class="btn btn-sm" data-id="${q.id}" data-act="link" title="Copiar enlace publico">Copiar enlace</button>
                ${Auth.canEdit() && !q.submitted_at ? `<button class="btn btn-sm btn-danger" data-id="${q.id}" data-act="del">Eliminar</button>` : ''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
      wrap.querySelectorAll('[data-act="link"]').forEach(btn => {
        btn.onclick = () => {
          const q = data.find(x => x.id == btn.dataset.id);
          if (!q) return;
          const link = location.origin + '/supplier-q?token=' + encodeURIComponent(q.token);
          navigator.clipboard.writeText(link).then(() => UI.toast('Enlace copiado al portapapeles', 'success'))
            .catch(() => {
              UI.modal('Enlace publico del cuestionario', `
                <div class="span2">
                  <p style="font-size:13px;margin-bottom:8px;">Copia y comparte este enlace con el proveedor:</p>
                  <input style="width:100%;font-size:12px;font-family:monospace;" value="${UI.esc(link)}" readonly onclick="this.select()">
                </div>
              `, { actions: '<button class="btn btn-primary" id="m-cancel">Cerrar</button>' });
              document.getElementById('m-cancel').onclick = UI.closeModal;
            });
        };
      });
      wrap.querySelectorAll('[data-act="del"]').forEach(btn => {
        btn.onclick = async () => {
          if (!await UI.confirm('Eliminar este cuestionario?')) return;
          try { await Api.supplier_questionnaires.del(btn.dataset.id); UI.toast('Eliminado','success'); _reloadSeq(); }
          catch (e) { UI.toast(e.message,'error'); }
        };
      });
      wrap.querySelectorAll('[data-act="send"]').forEach(btn => {
        btn.onclick = async () => {
          btn.disabled = true;
          UI.toast('Enviando email al proveedor...', 'info');
          try {
            const r = await Api.supplier_questionnaires.send(btn.dataset.id);
            UI.toast('Cuestionario enviado a ' + r.recipient, 'success');
          } catch (e) {
            UI.toast(e.message, 'error');
            btn.disabled = false;
          }
        };
      });
      // AI evaluation buttons
      wrap.querySelectorAll('[data-act="eval-ai"]').forEach(btn => {
        btn.onclick = async () => {
          const q = data.find(x => x.id == btn.dataset.id);
          if (!q) return;
          UI.toast('Evaluando con IA... Esto puede tardar unos segundos.', 'info');
          btn.disabled = true;
          try {
            const result = await Api.supplier_questionnaires_ai.triggerReview(q.id);
            UI.toast('Evaluacion IA completada', 'success');
            _showAiReviewModal(q.title || q.code, result);
            await _reloadSeq();
          } catch (e) {
            UI.toast(e.message, 'error');
            btn.disabled = false;
          }
        };
      });
      // AI score click to view existing review
      wrap.querySelectorAll('[data-act="view-ai"]').forEach(el => {
        el.onclick = () => {
          const q = data.find(x => x.id == el.dataset.id);
          if (!q || !q.ai_review) return;
          _showAiReviewModal(q.title || q.code, q.ai_review);
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  // ---- AI Review Modal ----

  const _AI_COVERAGE_LABELS = {
    fully_covered: 'Cobertura completa',
    partially_covered: 'Cobertura parcial',
    not_covered: 'Sin cobertura',
    unclear: 'No determinado',
  };
  const _AI_EVIDENCE_LABELS = {
    consistent: 'Consistente',
    partially_consistent: 'Parcialmente consistente',
    inconsistent: 'Inconsistente',
    no_evidence: 'Sin evidencia',
  };
  const _AI_COVERAGE_COLORS = {
    fully_covered: '#22C55E',
    partially_covered: '#F59E0B',
    not_covered: '#EF4444',
    unclear: '#6B7280',
  };
  const _AI_EVIDENCE_COLORS = {
    consistent: '#22C55E',
    partially_consistent: '#F59E0B',
    inconsistent: '#EF4444',
    no_evidence: '#6B7280',
  };

  function _showAiReviewModal(title, review) {
    if (!review) return;
    if (review.error) {
      UI.modal('Evaluacion IA — Error', `
        <div class="span2">
          <div class="notice">${UI.esc(review.error)}</div>
          <p style="font-size:13px;margin-top:8px;">La evaluacion automatica no pudo completarse. Revisa la configuracion de la API key en IA &gt; Configuracion.</p>
        </div>
      `, { actions: '<button class="btn btn-primary" id="m-close-ai">Cerrar</button>' });
      document.getElementById('m-close-ai').onclick = UI.closeModal;
      return;
    }

    const score = review.ai_score !== null && review.ai_score !== undefined ? review.ai_score : '-';
    const scoreColor = typeof score === 'number' ? (score >= 80 ? '#22C55E' : score >= 60 ? '#F59E0B' : '#EF4444') : '#6B7280';
    const confPct = review.confidence !== null && review.confidence !== undefined
      ? Math.round(review.confidence * 100) + '%' : '-';
    const coverage = review.control_coverage_assessment || 'unclear';
    const evidence = review.evidence_consistency || 'no_evidence';
    const needsManual = review.needs_manual_review;
    const rationale = review.rationale || '';
    const reviewedAt = review.evaluated_at ? new Date(review.evaluated_at).toLocaleString('es-ES') : '';

    const redFlags = Array.isArray(review.red_flags) && review.red_flags.length
      ? review.red_flags.map(f => `<li style="margin-bottom:4px;">${UI.esc(f)}</li>`).join('')
      : '<li style="color:var(--text-muted);">Sin alertas detectadas</li>';

    const followUp = Array.isArray(review.follow_up_questions) && review.follow_up_questions.length
      ? review.follow_up_questions.map(f => `<li style="margin-bottom:4px;">${UI.esc(f)}</li>`).join('')
      : '<li style="color:var(--text-muted);">Sin preguntas adicionales</li>';

    UI.modal(`Evaluacion IA — ${UI.esc(title)}`, `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div style="grid-column:1/-1;display:flex;gap:16px;flex-wrap:wrap;align-items:center;border-bottom:1px solid var(--border);padding-bottom:10px;margin-bottom:4px;">
          <div style="text-align:center;">
            <div style="font-size:28px;font-weight:800;color:${scoreColor};">${score}<span style="font-size:14px;">/100</span></div>
            <div style="font-size:11px;color:var(--text-muted);">Puntuacion IA</div>
          </div>
          <div style="text-align:center;">
            <div style="font-size:20px;font-weight:700;color:var(--brand-purple);">${confPct}</div>
            <div style="font-size:11px;color:var(--text-muted);">Confianza</div>
          </div>
          ${needsManual ? '<div style="background:#FEF3C7;border:1px solid #F59E0B;border-radius:6px;padding:4px 10px;font-size:12px;font-weight:600;color:#92400E;">Requiere revision manual</div>' : '<div style="background:#ECFDF5;border:1px solid #22C55E;border-radius:6px;padding:4px 10px;font-size:12px;font-weight:600;color:#065F46;">Sin alerta de revision</div>'}
          ${reviewedAt ? `<div style="font-size:11px;color:var(--text-muted);margin-left:auto;">Evaluado: ${reviewedAt}</div>` : ''}
        </div>

        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Cobertura de controles</div>
          <span style="display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;background:${_AI_COVERAGE_COLORS[coverage]};color:#fff;">${_AI_COVERAGE_LABELS[coverage] || coverage}</span>
        </div>
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Consistencia de evidencias</div>
          <span style="display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;background:${_AI_EVIDENCE_COLORS[evidence]};color:#fff;">${_AI_EVIDENCE_LABELS[evidence] || evidence}</span>
        </div>

        <div style="grid-column:1/-1;">
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Razonamiento</div>
          <p style="font-size:13px;line-height:1.5;margin:0;background:var(--bg-alt,var(--bg));padding:8px 10px;border-radius:6px;border:1px solid var(--border);">${UI.esc(rationale)}</p>
        </div>

        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Alertas detectadas</div>
          <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.6;">${redFlags}</ul>
        </div>
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Preguntas de seguimiento sugeridas</div>
          <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.6;">${followUp}</ul>
        </div>
      </div>
    `, { actions: '<button class="btn btn-primary" id="m-close-ai">Cerrar</button>' });
    document.getElementById('m-close-ai').onclick = UI.closeModal;
  }

  async function _openSeqForm() {
    let suppliers = [];
    let templates = [];
    let customTpls = [];
    try { suppliers = await Api.suppliers.list(); } catch (_) {}
    try { templates = await Api.tprm.templates(); } catch (_) {}
    try { customTpls = await Api.tprm.customTemplates(); } catch (_) {}
    UI.modal('Nuevo cuestionario de seguridad', `
      <div><label>Proveedor *</label>
        <select id="sq-sup">
          <option value="">- Seleccionar -</option>
          ${suppliers.map(s => `<option value="${s.id}">${UI.esc(s.code)} - ${UI.esc(s.name)}</option>`).join('')}
        </select>
      </div>
      <div><label>Plantilla TPRM</label>
        <select id="sq-template">
          <option value="">Estandar NIS2/ISO 27001 (10 preguntas)</option>
          <optgroup label="Plantillas del sistema">
          ${templates.map(t => `<option value="sys:${UI.esc(t.code)}">${UI.esc(t.name)} (${t.question_count} preguntas)</option>`).join('')}
          </optgroup>
          ${customTpls.length ? `<optgroup label="Mis plantillas">
          ${customTpls.map(t => `<option value="custom:${t.id}">${UI.esc(t.name)} (${(t.questions||[]).length} preguntas)</option>`).join('')}
          </optgroup>` : ''}
        </select>
      </div>
      <div><label>Titulo *</label>
        <input id="sq-title" value="Evaluacion de seguridad NIS2/ISO 27001">
      </div>
      <div><label>Fecha de expiracion</label>
        <input type="date" id="sq-expires" value="${new Date(Date.now()+30*86400000).toISOString().slice(0,10)}">
      </div>
      <div class="span2"><label>Notas internas</label>
        <textarea id="sq-notes" rows="2" placeholder="Notas para el equipo interno (no visibles para el proveedor)"></textarea>
      </div>
      <div class="span2 notice">
        Elige una plantilla del sistema (ISO 27001, NIS2, DORA, GDPR, ISO 42001, offboarding...) o el set estandar. Tras crear el cuestionario, copia el enlace publico para enviarlo al proveedor.
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Crear y obtener enlace</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const supId = document.getElementById('sq-sup').value;
      const title = document.getElementById('sq-title').value.trim();
      if (!supId) { UI.toast('Selecciona un proveedor','error'); return; }
      if (!title) { UI.toast('El titulo es obligatorio','error'); return; }
      const expires = document.getElementById('sq-expires').value;
      const tplVal = document.getElementById('sq-template').value || '';
      const body = {
        supplier_id: parseInt(supId),
        title,
        expires_at: expires || null,
        notes: document.getElementById('sq-notes').value.trim(),
        template_code: tplVal.startsWith('sys:') ? tplVal.slice(4) : null,
        custom_template_id: tplVal.startsWith('custom:') ? parseInt(tplVal.slice(7)) : null,
      };
      try {
        const q = await Api.supplier_questionnaires.create(body);
        UI.closeModal();
        const link = location.origin + '/supplier-q?token=' + encodeURIComponent(q.token);
        navigator.clipboard.writeText(link).catch(() => {});
        UI.modal('Cuestionario creado', `
          <div class="span2">
            <p style="font-size:13px;margin-bottom:4px;">Cuestionario <strong>${UI.esc(q.code)}</strong> creado correctamente.</p>
            <p style="font-size:13px;margin-bottom:8px;">Enlace publico copiado al portapapeles. Comparte este enlace con el proveedor:</p>
            <input style="width:100%;font-size:12px;font-family:monospace;" value="${UI.esc(link)}" readonly onclick="this.select()">
            <p style="font-size:12px;color:var(--text-muted);margin-top:8px;">El enlace expira el ${new Date(q.expires_at).toLocaleDateString('es-ES')}.</p>
          </div>
        `, { actions: '<button class="btn btn-primary" id="m-ok">Entendido</button>' });
        document.getElementById('m-ok').onclick = UI.closeModal;
        _reloadSeq();
      } catch (e) { UI.toast(e.message,'error'); }
    };
  }

  // ======== SCHEDULES TAB ========

  async function _renderSchedulesTab() {
    const wrap = document.getElementById('sup-tab-content');
    wrap.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">
        <select id="sched-sup-filter" class="input" style="width:220px;">
          <option value="">Todos los proveedores</option>
        </select>
      </div>
      <div id="sched-list">Cargando...</div>
    `;
    try {
      const sups = await Api.suppliers.list();
      const sel = document.getElementById('sched-sup-filter');
      if (sel) sups.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id; opt.textContent = s.code + ' - ' + s.name; sel.appendChild(opt);
      });
    } catch (_) {}
    document.getElementById('sched-sup-filter').onchange = _reloadSchedules;
    await _reloadSchedules();
  }

  async function _reloadSchedules() {
    const supId = document.getElementById('sched-sup-filter')?.value;
    const params = {};
    if (supId) params.supplier_id = supId;
    const wrap = document.getElementById('sched-list');
    if (!wrap) return;
    try {
      const data = await Api.questionnaire_schedules.list(params);
      if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);margin-top:24px;text-align:center;">Sin planificaciones. Crea una para enviar cuestionarios periodicamente.</p>';
        return;
      }
      const INTERVAL_LABELS = { 30:'Mensual', 90:'Trimestral', 180:'Semestral', 365:'Anual' };
      wrap.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          <th>Proveedor</th><th>Titulo (plantilla)</th><th>Frecuencia</th>
          <th>Proximo envio</th><th>Ultimo envio</th><th>Notificar a</th><th>Estado</th><th></th>
        </tr></thead>
        <tbody>
          ${data.map(sc => {
            const next = sc.next_send_at ? new Date(sc.next_send_at).toLocaleDateString('es-ES') : '-';
            const last = sc.last_sent_at ? new Date(sc.last_sent_at).toLocaleDateString('es-ES') : 'Nunca';
            const freq = INTERVAL_LABELS[sc.interval_days] || sc.interval_days + ' dias';
            const status = sc.enabled
              ? `<span style="color:#22C55E;font-weight:600;font-size:12px;">Activa</span>`
              : `<span style="color:var(--text-muted);font-size:12px;">Pausada</span>`;
            return `<tr>
              <td style="font-size:12px;">${UI.esc(sc.supplier_code || '')} ${UI.esc(sc.supplier_name || '')}</td>
              <td>${UI.esc(sc.title_template)}</td>
              <td style="font-size:12px;">${freq}</td>
              <td style="font-size:12px;">${next}</td>
              <td style="font-size:12px;">${last}</td>
              <td style="font-size:12px;">${UI.esc(sc.notify_email || '-')}</td>
              <td>${status}</td>
              <td>
                ${Auth.canEdit() ? `
                  <button class="btn btn-sm" data-id="${sc.id}" data-sc-act="edit">Editar</button>
                  <button class="btn btn-sm" data-id="${sc.id}" data-sc-act="toggle">${sc.enabled ? 'Pausar' : 'Activar'}</button>
                  <button class="btn btn-sm btn-danger" data-id="${sc.id}" data-sc-act="del">Eliminar</button>
                ` : ''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;

      wrap.querySelectorAll('[data-sc-act="edit"]').forEach(btn => {
        btn.onclick = () => {
          const sc = data.find(x => x.id == btn.dataset.id);
          if (sc) _openScheduleForm(sc);
        };
      });
      wrap.querySelectorAll('[data-sc-act="toggle"]').forEach(btn => {
        btn.onclick = async () => {
          const sc = data.find(x => x.id == btn.dataset.id);
          if (!sc) return;
          try {
            await Api.questionnaire_schedules.update(sc.id, { enabled: !sc.enabled });
            UI.toast(sc.enabled ? 'Planificacion pausada' : 'Planificacion activada', 'success');
            _reloadSchedules();
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      });
      wrap.querySelectorAll('[data-sc-act="del"]').forEach(btn => {
        btn.onclick = async () => {
          if (!confirm('Eliminar esta planificacion?')) return;
          try {
            await Api.questionnaire_schedules.del(btn.dataset.id);
            UI.toast('Planificacion eliminada', 'success');
            _reloadSchedules();
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  async function _openScheduleForm(sc) {
    let suppliers = [], templates = [], customTpls = [];
    try { suppliers = await Api.suppliers.list(); } catch (_) {}
    try { templates = await Api.tprm.templates(); } catch (_) {}
    try { customTpls = await Api.tprm.customTemplates(); } catch (_) {}
    const v = sc || {};
    const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 16);
    UI.modal(sc ? 'Editar planificacion' : 'Nueva planificacion periodica', `
      <div><label>Proveedor *</label>
        <select id="sc-sup">
          <option value="">- Seleccionar -</option>
          ${suppliers.map(s => `<option value="${s.id}" ${v.supplier_id == s.id ? 'selected' : ''}>${UI.esc(s.code)} - ${UI.esc(s.name)}</option>`).join('')}
        </select>
      </div>
      <div><label>Titulo del cuestionario *</label>
        <input id="sc-title" class="input" value="${UI.esc(v.title_template || 'Evaluacion de seguridad {year}')}" placeholder="Usa {year} y {month} como variables">
      </div>
      <div><label>Plantilla</label>
        <select id="sc-template" class="input">
          <option value="">Estandar NIS2/ISO 27001</option>
          <optgroup label="Plantillas del sistema">
            ${templates.map(t => `<option value="sys:${UI.esc(t.code)}" ${v.template_code === t.code ? 'selected' : ''}>${UI.esc(t.name)}</option>`).join('')}
          </optgroup>
          ${customTpls.length ? `<optgroup label="Mis plantillas">
            ${customTpls.map(t => `<option value="custom:${t.id}" ${v.custom_template_id == t.id ? 'selected' : ''}>${UI.esc(t.name)}</option>`).join('')}
          </optgroup>` : ''}
        </select>
      </div>
      <div><label>Frecuencia de envio</label>
        <select id="sc-interval" class="input">
          <option value="30" ${v.interval_days==30?'selected':''}>Mensual (30 dias)</option>
          <option value="90" ${v.interval_days==90?'selected':''}>Trimestral (90 dias)</option>
          <option value="180" ${v.interval_days==180?'selected':''}>Semestral (180 dias)</option>
          <option value="365" ${(!v.interval_days||v.interval_days==365)?'selected':''}>Anual (365 dias)</option>
        </select>
      </div>
      <div><label>Dias de validez del cuestionario enviado</label>
        <input type="number" id="sc-expires" class="input" min="7" max="180" value="${v.expires_days || 30}">
      </div>
      <div><label>Primer/proximo envio</label>
        <input type="datetime-local" id="sc-next" class="input" value="${v.next_send_at ? v.next_send_at.slice(0,16) : tomorrow}">
      </div>
      <div><label>Email de notificacion (al responder el proveedor)</label>
        <input type="email" id="sc-notify" class="input" value="${UI.esc(v.notify_email || '')}" placeholder="responsable@empresa.com">
      </div>
      <div class="span2"><label>Notas internas</label>
        <textarea id="sc-notes" class="input" rows="2">${UI.esc(v.notes || '')}</textarea>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const supId = document.getElementById('sc-sup').value;
      const title = document.getElementById('sc-title').value.trim();
      if (!supId) { UI.toast('Selecciona un proveedor', 'error'); return; }
      if (!title) { UI.toast('El titulo es obligatorio', 'error'); return; }
      const tplVal = document.getElementById('sc-template').value || '';
      const payload = {
        supplier_id: parseInt(supId),
        title_template: title,
        template_code: tplVal.startsWith('sys:') ? tplVal.slice(4) : null,
        custom_template_id: tplVal.startsWith('custom:') ? parseInt(tplVal.slice(7)) : null,
        interval_days: parseInt(document.getElementById('sc-interval').value) || 365,
        expires_days: parseInt(document.getElementById('sc-expires').value) || 30,
        notify_email: document.getElementById('sc-notify').value.trim() || null,
        notes: document.getElementById('sc-notes').value.trim() || null,
        next_send_at: document.getElementById('sc-next').value || null,
      };
      try {
        if (sc) {
          await Api.questionnaire_schedules.update(sc.id, payload);
          UI.toast('Planificacion actualizada', 'success');
        } else {
          await Api.questionnaire_schedules.create(payload);
          UI.toast('Planificacion creada', 'success');
        }
        UI.closeModal();
        _reloadSchedules();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  // ======== FLOWS TAB ========

  async function _renderFlowsTab() {
    const wrap = document.getElementById('sup-tab-content');
    wrap.innerHTML = `
      <div class="notice" style="margin-bottom:12px;font-size:13px;">
        Los flujos permiten encadenar cuestionarios automaticamente segun el resultado de la fase anterior.
        Ejemplo: cuestionario inicial &rarr; si score &lt; 60% enviar cuestionario de riesgo alto, si &ge; 60% enviar uno de riesgo medio.
      </div>
      <div id="flow-list">Cargando...</div>
    `;
    await _reloadFlows();
  }

  async function _reloadFlows() {
    const wrap = document.getElementById('flow-list');
    if (!wrap) return;
    try {
      const data = await Api.questionnaire_flows.list();
      if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);margin-top:24px;text-align:center;">Sin flujos definidos. Crea uno para automatizar secuencias de cuestionarios.</p>';
        return;
      }
      wrap.innerHTML = data.map(f => {
        const stepCount = (f.steps || []).length;
        const initial = (f.steps || []).filter(s => !s.condition).length;
        const conditional = stepCount - initial;
        return `
          <div style="border:1px solid var(--border);border-radius:8px;padding:14px 16px;margin-bottom:10px;background:var(--bg-2);">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px;">
              <div style="flex:1;">
                <div style="font-weight:700;font-size:14px;">${UI.esc(f.name)}</div>
                ${f.description ? `<div style="font-size:12px;color:var(--text-muted);margin-top:2px;">${UI.esc(f.description)}</div>` : ''}
                <div style="margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;">
                  <span style="font-size:11px;background:var(--bg);padding:2px 8px;border-radius:999px;border:1px solid var(--border);">${initial} paso${initial!==1?'s':''} inicial${initial!==1?'es':''}</span>
                  ${conditional ? `<span style="font-size:11px;background:var(--bg);padding:2px 8px;border-radius:999px;border:1px solid var(--border);">${conditional} paso${conditional!==1?'s':''} condicional${conditional!==1?'es':''}</span>` : ''}
                </div>
                <div style="margin-top:8px;">
                  ${(f.steps || []).map((s, i) => {
                    const cond = s.condition
                      ? (s.condition.score_lt !== undefined ? `score &lt; ${s.condition.score_lt}%`
                        : s.condition.score_gte !== undefined ? `score &ge; ${s.condition.score_gte}%`
                        : s.condition.residual_level ? `nivel residual = ${s.condition.residual_level}`
                        : 'condicional')
                      : 'inicial (siempre)';
                    return `<div style="font-size:11px;color:var(--text-muted);margin-top:3px;">
                      <span style="display:inline-block;width:18px;height:18px;border-radius:50%;background:var(--brand-purple);color:#fff;font-size:10px;font-weight:700;text-align:center;line-height:18px;margin-right:4px;">${i+1}</span>
                      <strong>${UI.esc(s.name || s.template_code || 'Paso')}</strong> &mdash; ${cond}
                    </div>`;
                  }).join('')}
                </div>
              </div>
              <div style="display:flex;flex-direction:column;gap:4px;min-width:110px;">
                ${Auth.canEdit() ? `
                  <button class="btn btn-sm" data-id="${f.id}" data-fl-act="edit">Editar flujo</button>
                  <button class="btn btn-sm btn-primary" data-id="${f.id}" data-fl-act="apply">Aplicar a proveedor</button>
                  <button class="btn btn-sm btn-danger" data-id="${f.id}" data-fl-act="del">Eliminar</button>
                ` : ''}
              </div>
            </div>
          </div>
        `;
      }).join('');

      wrap.querySelectorAll('[data-fl-act="edit"]').forEach(btn => {
        btn.onclick = () => {
          const f = data.find(x => x.id == btn.dataset.id);
          if (f) _openFlowForm(f);
        };
      });
      wrap.querySelectorAll('[data-fl-act="apply"]').forEach(btn => {
        btn.onclick = () => {
          const f = data.find(x => x.id == btn.dataset.id);
          if (f) _openApplyFlowModal(f);
        };
      });
      wrap.querySelectorAll('[data-fl-act="del"]').forEach(btn => {
        btn.onclick = async () => {
          if (!confirm('Eliminar este flujo?')) return;
          try {
            await Api.questionnaire_flows.del(btn.dataset.id);
            UI.toast('Flujo eliminado', 'success');
            _reloadFlows();
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  async function _openFlowForm(flow) {
    let templates = [], customTpls = [];
    try { templates = await Api.tprm.templates(); } catch (_) {}
    try { customTpls = await Api.tprm.customTemplates(); } catch (_) {}

    const tplOptions = `
      <option value="">Estandar NIS2/ISO 27001</option>
      <optgroup label="Plantillas del sistema">
        ${templates.map(t => `<option value="sys:${UI.esc(t.code)}">${UI.esc(t.name)}</option>`).join('')}
      </optgroup>
      ${customTpls.length ? `<optgroup label="Mis plantillas">
        ${customTpls.map(t => `<option value="custom:${t.id}">${UI.esc(t.name)}</option>`).join('')}
      </optgroup>` : ''}
    `;

    let _flowSteps = flow ? JSON.parse(JSON.stringify(flow.steps || [])) : [];
    if (!_flowSteps.length) {
      _flowSteps = [{ id: 'step_1', name: 'Cuestionario inicial', template_code: null, expires_days: 30, condition: null }];
    }

    function _renderFlowSteps() {
      const stepsWrap = document.getElementById('flow-steps-wrap');
      if (!stepsWrap) return;
      stepsWrap.innerHTML = _flowSteps.map((s, i) => {
        const condType = !s.condition ? 'none'
          : s.condition.score_lt !== undefined ? 'score_lt'
          : s.condition.score_gte !== undefined ? 'score_gte'
          : s.condition.residual_level !== undefined ? 'residual_level'
          : 'none';
        const condVal = s.condition
          ? (s.condition.score_lt ?? s.condition.score_gte ?? s.condition.residual_level ?? '')
          : '';
        const curTpl = s.template_code
          ? (s.template_code.startsWith('custom:') ? `custom:${s.custom_template_id}` : `sys:${s.template_code}`)
          : '';
        return `
          <div style="border:1px solid var(--border);border-radius:6px;padding:10px;margin-bottom:8px;background:var(--bg-2);">
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">
              <span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;background:var(--brand-purple);color:#fff;font-size:11px;font-weight:700;">${i+1}</span>
              <input class="input fl-step-name" data-idx="${i}" placeholder="Nombre del paso" value="${UI.esc(s.name||'')}" style="flex:1;font-size:12px;">
              ${_flowSteps.length > 1 ? `<button type="button" class="btn btn-sm btn-danger fl-step-del" data-idx="${i}" style="padding:2px 8px;font-size:11px;">X</button>` : ''}
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
              <div>
                <label style="font-size:11px;color:var(--text-muted);">Plantilla</label>
                <select class="input fl-step-tpl" data-idx="${i}" style="font-size:12px;">
                  ${tplOptions}
                </select>
              </div>
              <div>
                <label style="font-size:11px;color:var(--text-muted);">Dias de validez</label>
                <input type="number" class="input fl-step-expires" data-idx="${i}" min="7" max="180" value="${s.expires_days||30}" style="font-size:12px;">
              </div>
              <div>
                <label style="font-size:11px;color:var(--text-muted);">Condicion de envio</label>
                <select class="input fl-step-cond-type" data-idx="${i}" style="font-size:12px;">
                  <option value="none" ${condType==='none'?'selected':''}>Siempre (paso inicial)</option>
                  <option value="score_lt" ${condType==='score_lt'?'selected':''}>Score anterior &lt; X%</option>
                  <option value="score_gte" ${condType==='score_gte'?'selected':''}>Score anterior &ge; X%</option>
                  <option value="residual_level" ${condType==='residual_level'?'selected':''}>Nivel residual igual a...</option>
                </select>
              </div>
              <div>
                <label style="font-size:11px;color:var(--text-muted);">Valor condicion</label>
                <input class="input fl-step-cond-val" data-idx="${i}" placeholder="Ej: 60 o critical" value="${UI.esc(String(condVal))}" style="font-size:12px;" ${condType==='none'?'disabled':''}>
              </div>
            </div>
          </div>
        `;
      }).join('') + `<button type="button" id="fl-add-step" class="btn btn-sm" style="margin-top:4px;">+ Anadir paso</button>`;

      // Set selected template values
      stepsWrap.querySelectorAll('.fl-step-tpl').forEach(sel => {
        const idx = parseInt(sel.dataset.idx);
        const s = _flowSteps[idx];
        const curTpl = s.template_code
          ? (s.template_code.startsWith('custom:') ? `custom:${s.custom_template_id}` : `sys:${s.template_code}`)
          : '';
        sel.value = curTpl;
      });

      // Wire events
      stepsWrap.querySelectorAll('.fl-step-name').forEach(inp => {
        inp.oninput = () => { _flowSteps[parseInt(inp.dataset.idx)].name = inp.value; };
      });
      stepsWrap.querySelectorAll('.fl-step-tpl').forEach(sel => {
        sel.onchange = () => {
          const idx = parseInt(sel.dataset.idx); const v = sel.value;
          if (!v) { _flowSteps[idx].template_code = null; _flowSteps[idx].custom_template_id = null; }
          else if (v.startsWith('sys:')) { _flowSteps[idx].template_code = v.slice(4); _flowSteps[idx].custom_template_id = null; }
          else if (v.startsWith('custom:')) { _flowSteps[idx].template_code = null; _flowSteps[idx].custom_template_id = parseInt(v.slice(7)); }
        };
      });
      stepsWrap.querySelectorAll('.fl-step-expires').forEach(inp => {
        inp.oninput = () => { _flowSteps[parseInt(inp.dataset.idx)].expires_days = parseInt(inp.value) || 30; };
      });
      stepsWrap.querySelectorAll('.fl-step-cond-type').forEach(sel => {
        sel.onchange = () => {
          const idx = parseInt(sel.dataset.idx); const v = sel.value;
          const valInp = stepsWrap.querySelector(`.fl-step-cond-val[data-idx="${idx}"]`);
          if (v === 'none') { _flowSteps[idx].condition = null; if(valInp) valInp.disabled = true; }
          else { if(valInp) valInp.disabled = false; }
        };
      });
      stepsWrap.querySelectorAll('.fl-step-cond-val').forEach(inp => {
        inp.oninput = () => {
          const idx = parseInt(inp.dataset.idx);
          const typeEl = stepsWrap.querySelector(`.fl-step-cond-type[data-idx="${idx}"]`);
          const condType = typeEl?.value || 'none';
          if (condType === 'none') { _flowSteps[idx].condition = null; return; }
          const val = condType === 'residual_level' ? inp.value : (parseInt(inp.value) || 60);
          _flowSteps[idx].condition = { [condType]: val };
        };
      });
      stepsWrap.querySelectorAll('.fl-step-del').forEach(btn => {
        btn.onclick = () => {
          _flowSteps.splice(parseInt(btn.dataset.idx), 1);
          _renderFlowSteps();
        };
      });
      const addBtn = document.getElementById('fl-add-step');
      if (addBtn) {
        addBtn.onclick = () => {
          _flowSteps.push({ id: 'step_' + Date.now(), name: '', template_code: null, expires_days: 30, condition: null });
          _renderFlowSteps();
        };
      }
    }

    UI.modal(flow ? `Editar flujo: ${UI.esc(flow.name)}` : 'Nuevo flujo de cuestionarios', `
      <div class="span2"><label>Nombre del flujo *</label>
        <input id="fl-name" class="input" value="${UI.esc(flow?.name || '')}" placeholder="Ej: Evaluacion proveedores criticos">
      </div>
      <div class="span2"><label>Descripcion</label>
        <textarea id="fl-desc" class="input" rows="2">${UI.esc(flow?.description || '')}</textarea>
      </div>
      <div class="span2">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <strong style="font-size:13px;color:var(--brand-purple);">Pasos del flujo</strong>
        </div>
        <div id="flow-steps-wrap"></div>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar flujo</button>`,
      width: '680px',
    });

    document.getElementById('m-cancel').onclick = UI.closeModal;
    _renderFlowSteps();

    document.getElementById('m-save').onclick = async () => {
      const name = document.getElementById('fl-name').value.trim();
      if (!name) { UI.toast('El nombre es obligatorio', 'error'); return; }
      if (!_flowSteps.length) { UI.toast('El flujo necesita al menos un paso', 'error'); return; }
      const payload = {
        name,
        description: document.getElementById('fl-desc').value.trim() || null,
        steps: _flowSteps,
      };
      try {
        if (flow) {
          await Api.questionnaire_flows.update(flow.id, payload);
          UI.toast('Flujo actualizado', 'success');
        } else {
          await Api.questionnaire_flows.create(payload);
          UI.toast('Flujo creado', 'success');
        }
        UI.closeModal();
        _reloadFlows();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  async function _openApplyFlowModal(flow) {
    let suppliers = [];
    try { suppliers = await Api.suppliers.list(); } catch (_) {}
    UI.modal(`Aplicar flujo: ${UI.esc(flow.name)}`, `
      <div>
        <label>Selecciona el proveedor al que iniciar el flujo</label>
        <select id="apply-sup" class="input">
          <option value="">- Seleccionar proveedor -</option>
          ${suppliers.map(s => `<option value="${s.id}">${UI.esc(s.code)} - ${UI.esc(s.name)}</option>`).join('')}
        </select>
      </div>
      <div class="span2 notice" style="font-size:12px;">
        Se creara el primer cuestionario del flujo y se enlazara con este proveedor. Los pasos siguientes se envian al recibir respuesta del anterior.
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-apply">Iniciar flujo</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-apply').onclick = async () => {
      const supId = document.getElementById('apply-sup').value;
      if (!supId) { UI.toast('Selecciona un proveedor', 'error'); return; }
      try {
        const r = await Api.questionnaire_flows.apply(flow.id, supId);
        UI.closeModal();
        const link = location.origin + '/supplier-q?token=' + encodeURIComponent(r.token);
        UI.modal('Flujo iniciado', `
          <div class="span2">
            <p style="font-size:13px;margin-bottom:4px;">Cuestionario <strong>${UI.esc(r.questionnaire_code)}</strong> creado: <em>${UI.esc(r.title)}</em>.</p>
            <p style="font-size:13px;margin-bottom:8px;">Enlace publico para enviar al proveedor:</p>
            <input style="width:100%;font-size:12px;font-family:monospace;" value="${UI.esc(link)}" readonly onclick="this.select()">
          </div>
        `, { actions: '<button class="btn btn-primary" id="m-ok">Entendido</button>' });
        document.getElementById('m-ok').onclick = UI.closeModal;
        navigator.clipboard.writeText(link).catch(() => {});
        _setSupTab('questionnaires');
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  return { render };
})();
