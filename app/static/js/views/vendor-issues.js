/* Vista de hallazgos de proveedores — gestion completa con SLAs, impacto, causa raiz, acciones. */
const ViewVendorIssues = (() => {

  const SEV_LABELS = {
    critical: 'Critico', high: 'Alto', medium: 'Medio',
    low: 'Bajo', informational: 'Informativo',
  };
  const SEV_COLORS = {
    critical: 'var(--risk-critical)', high: 'var(--risk-high)',
    medium: 'var(--risk-medium)', low: 'var(--risk-low)', informational: '#9CA3AF',
  };
  const STATUS_LABELS = {
    open: 'Abierto', acknowledged: 'Reconocido', in_remediation: 'En remediacion',
    mitigated: 'Mitigado', accepted: 'Aceptado', closed: 'Cerrado', overdue: 'Vencido',
  };
  const STATUS_COLORS = {
    open: 'var(--risk-high)', acknowledged: 'var(--risk-medium)',
    in_remediation: '#6366F1', mitigated: '#10B981',
    accepted: '#9CA3AF', closed: 'var(--text-muted)', overdue: 'var(--risk-critical)',
  };
  const SOURCE_LABELS = {
    questionnaire: 'Cuestionario', external_rating: 'Calificacion externa',
    manual: 'Manual', incident: 'Incidente', monitoring: 'Monitoreo',
  };

  let _suppliers = [];
  let _allIssues = [];

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  // --------------- RENDER PRINCIPAL ---------------

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Hallazgos de proveedores</h1>
          <p class="page-sub">SLA, impacto, causa raiz y plan de remediacion — TPRM §2.1</p>
        </div>
        ${Auth.canEdit() ? '<button class="btn btn-primary" id="btn-new-issue">+ Nuevo hallazgo</button>' : ''}
      </div>

      <div id="vi-stats" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:16px;"></div>

      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">
        <select id="f-supplier" class="input" style="width:220px;">
          <option value="">Todos los proveedores</option>
        </select>
        <select id="f-severity" class="input" style="width:160px;">
          <option value="">Todas las severidades</option>
          ${Object.entries(SEV_LABELS).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}
        </select>
        <select id="f-status" class="input" style="width:180px;">
          <option value="">Todos los estados</option>
          ${Object.entries(STATUS_LABELS).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}
        </select>
        <label style="display:flex;align-items:center;gap:5px;font-size:13px;cursor:pointer;white-space:nowrap;margin-left:auto;">
          <input type="checkbox" id="f-overdue"> Solo vencidos
        </label>
      </div>

      <div id="vi-list"></div>
    `;

    if (Auth.canEdit()) document.getElementById('btn-new-issue').onclick = () => _openForm();
    document.getElementById('f-supplier').onchange = _refresh;
    document.getElementById('f-severity').onchange = _refresh;
    document.getElementById('f-status').onchange = _refresh;
    document.getElementById('f-overdue').onchange = _refresh;

    await _loadSuppliers();
    await _loadStats();
    await _refresh();
  }

  async function _loadSuppliers() {
    try {
      _suppliers = await Api.suppliers.list();
      const sel = document.getElementById('f-supplier');
      if (!sel) return;
      _suppliers.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.name;
        sel.appendChild(opt);
      });
    } catch (_) {}
  }

  async function _loadStats() {
    try {
      const s = await Api.vendor_issues.summary();
      const wrap = document.getElementById('vi-stats');
      if (!wrap) return;
      const kpi = (val, label, color) => `
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:12px 14px;text-align:center;">
          <div style="font-size:26px;font-weight:800;color:${color || 'var(--brand-purple)'};font-family:var(--font-mono);">${val}</div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:4px;font-weight:600;">${label}</div>
        </div>`;
      wrap.innerHTML =
        kpi(s.total, 'Total hallazgos') +
        kpi(s.open, 'Abiertos', s.open > 0 ? 'var(--risk-high)' : '') +
        kpi(s.overdue, 'Vencidos', s.overdue > 0 ? 'var(--risk-critical)' : '') +
        kpi(s.by_severity.critical || 0, 'Criticos', (s.by_severity.critical||0) > 0 ? 'var(--risk-critical)' : '') +
        kpi(s.by_severity.high || 0, 'Altos', (s.by_severity.high||0) > 0 ? 'var(--risk-high)' : '');
    } catch (_) {}
  }

  async function _refresh() {
    const supplierId = document.getElementById('f-supplier')?.value || '';
    const severity   = document.getElementById('f-severity')?.value  || '';
    const status     = document.getElementById('f-status')?.value    || '';
    const overdueChk = document.getElementById('f-overdue')?.checked;
    const wrap = document.getElementById('vi-list');
    if (!wrap) return;
    wrap.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      const params = {};
      if (supplierId) params.supplier_id = supplierId;
      if (severity)   params.severity    = severity;
      if (status)     params.status      = status;
      if (overdueChk) params.overdue     = true;
      _allIssues = await Api.vendor_issues.list(params);
      _renderTable(wrap);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _renderTable(wrap) {
    if (!_allIssues.length) {
      wrap.innerHTML = '<div class="empty-state" style="padding:40px;text-align:center;color:var(--text-muted);">No se encontraron hallazgos.</div>';
      return;
    }
    const now = new Date();
    const rows = _allIssues.map(issue => {
      const isOverdue = issue.status === 'overdue' || (
        issue.due_date && new Date(issue.due_date) < now &&
        !['closed','mitigated','accepted'].includes(issue.status)
      );
      const slaCount  = (issue.sla_breaches || []).length;
      const actsTotal = (issue.action_items || []).length;
      const actsDone  = (issue.action_items || []).filter(a => a.done).length;
      const dueDateStr = issue.due_date
        ? new Date(issue.due_date).toLocaleDateString('es-ES') : '—';
      return `
        <tr style="cursor:pointer;${isOverdue ? 'background:rgba(254,226,226,0.35);' : ''}"
            onclick="ViewVendorIssues._openDetail(${issue.id})">
          <td><strong>${UI.esc(issue.code)}</strong></td>
          <td>${UI.esc(issue.supplier_name || '—')}</td>
          <td>
            ${UI.esc(issue.title)}
            ${slaCount ? `<br><span style="font-size:10px;color:var(--risk-high);font-weight:600;">${slaCount} SLA incumplido${slaCount>1?'s':''}</span>` : ''}
          </td>
          <td>${_badge(SEV_LABELS[issue.severity] || issue.severity, SEV_COLORS[issue.severity] || '#888')}</td>
          <td>${_badge(STATUS_LABELS[issue.status] || issue.status, STATUS_COLORS[issue.status] || '#888')}</td>
          <td style="${isOverdue ? 'color:var(--risk-critical);font-weight:700;' : ''}">${dueDateStr}${isOverdue ? ' VENCIDO' : ''}</td>
          <td style="font-size:11px;color:var(--text-muted);">${actsTotal ? `${actsDone}/${actsTotal} acciones` : '—'}</td>
          <td onclick="event.stopPropagation()">
            ${Auth.canEdit() ? `<button class="btn btn-sm" onclick="ViewVendorIssues._openForm(${issue.id})">Editar</button>
            <button class="btn btn-sm btn-danger" onclick="ViewVendorIssues._del(${issue.id})">Eliminar</button>` : ''}
          </td>
        </tr>`;
    }).join('');

    wrap.innerHTML = `
      <div class="table-wrap">
        <table class="data">
          <thead><tr>
            <th>Codigo</th><th>Proveedor</th><th>Titulo</th>
            <th>Severidad</th><th>Estado</th><th>Vence</th><th>Acciones</th><th></th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  // --------------- DETALLE ---------------

  async function _openDetail(id) {
    const issue = _allIssues.find(i => i.id === id);
    if (!issue) return;
    const isOverdue = issue.status === 'overdue' || (
      issue.due_date && new Date(issue.due_date) < new Date() &&
      !['closed','mitigated','accepted'].includes(issue.status)
    );
    const slaHtml = (issue.sla_breaches || []).length
      ? `<div style="margin-top:10px;">
          <strong style="font-size:12px;color:var(--risk-high);">SLAs incumplidos:</strong>
          <ul style="margin:4px 0 0 16px;font-size:13px;">
            ${(issue.sla_breaches||[]).map(b => `<li><strong>${UI.esc(b.sla_name)}</strong>${b.details ? ' — ' + UI.esc(b.details) : ''}</li>`).join('')}
          </ul>
        </div>` : '';

    const actHtml = (issue.action_items || []).length
      ? `<div style="margin-top:10px;">
          <strong style="font-size:12px;color:var(--text-muted);">Items de accion:</strong>
          <ul style="margin:4px 0 0 16px;font-size:13px;">
            ${(issue.action_items||[]).map(a => `<li style="${a.done?'text-decoration:line-through;color:var(--text-subtle);':''}">${UI.esc(a.text)}${a.due_date ? ' <span style="font-size:11px;color:var(--text-muted);">('+a.due_date+')</span>' : ''}</li>`).join('')}
          </ul>
        </div>` : '';

    const evidHtml = (issue.evidence_refs || []).length
      ? `<div style="margin-top:10px;">
          <strong style="font-size:12px;color:var(--text-muted);">Evidencias:</strong>
          <ul style="margin:4px 0 0 16px;font-size:13px;">
            ${(issue.evidence_refs||[]).map(e => `<li>${e.url ? `<a href="${UI.esc(e.url)}" target="_blank" rel="noopener">${UI.esc(e.name||e.url)}</a>` : UI.esc(e.name||'')}</li>`).join('')}
          </ul>
        </div>` : '';

    UI.modal(`${UI.esc(issue.code)} — ${UI.esc(issue.title)}`, `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px;font-size:13px;">
        <div><strong>Proveedor:</strong> ${UI.esc(issue.supplier_name||'—')}</div>
        <div><strong>Fuente:</strong> ${UI.esc(SOURCE_LABELS[issue.source]||issue.source)}</div>
        <div><strong>Severidad:</strong> ${_badge(SEV_LABELS[issue.severity]||issue.severity, SEV_COLORS[issue.severity]||'#888')}</div>
        <div><strong>Estado:</strong> ${_badge(STATUS_LABELS[issue.status]||issue.status, STATUS_COLORS[issue.status]||'#888')}${isOverdue ? ' <span style="font-size:10px;color:var(--risk-critical);font-weight:700;">VENCIDO</span>' : ''}</div>
        <div><strong>Descubierto:</strong> ${new Date(issue.discovered_at).toLocaleDateString('es-ES')}</div>
        <div><strong>Vence:</strong> ${issue.due_date ? new Date(issue.due_date).toLocaleDateString('es-ES') : '—'}</div>
      </div>
      ${issue.description ? `<div style="font-size:13px;margin-bottom:10px;"><strong>Descripcion:</strong><br>${UI.esc(issue.description)}</div>` : ''}
      ${slaHtml}
      ${issue.impact_description ? `<div style="margin-top:10px;font-size:13px;"><strong>Impacto:</strong><br>${UI.esc(issue.impact_description)}</div>` : ''}
      ${issue.root_cause ? `<div style="margin-top:10px;font-size:13px;"><strong>Causa raiz:</strong><br>${UI.esc(issue.root_cause)}</div>` : ''}
      ${issue.remediation_plan ? `<div style="margin-top:10px;font-size:13px;"><strong>Plan de remediacion:</strong><br>${UI.esc(issue.remediation_plan)}</div>` : ''}
      ${actHtml}
      ${evidHtml}
      ${issue.resolution_notes ? `<div style="margin-top:10px;font-size:13px;border-top:1px solid var(--border);padding-top:10px;"><strong>Notas de resolucion:</strong><br>${UI.esc(issue.resolution_notes)}</div>` : ''}
    `, {
      actions: `<button class="btn" onclick="UI.closeModal()">Cerrar</button>
                ${Auth.canEdit() ? `<button class="btn btn-primary" onclick="UI.closeModal();ViewVendorIssues._openForm(${issue.id})">Editar</button>` : ''}`,
    });
  }

  // --------------- FORMULARIO (crear / editar) ---------------

  async function _openForm(id) {
    const issue = id ? _allIssues.find(i => i.id === id) : null;

    // SLAs del proveedor seleccionado (para nuevo hallazgo)
    let supplierSlas = [];
    if (issue) {
      const sup = _suppliers.find(s => s.id === issue.supplier_id);
      supplierSlas = sup?.slas || [];
    }

    // Items de accion actuales
    let actionItems = issue?.action_items || [];

    UI.modal(issue ? `Editar ${issue.code}` : 'Nuevo hallazgo', _formHtml(issue, supplierSlas, actionItems), {
      actions: `<button class="btn" onclick="UI.closeModal()">Cancelar</button>
                <button class="btn btn-primary" id="vi-save-btn">${issue ? 'Guardar cambios' : 'Crear hallazgo'}</button>`,
    });

    // Actualizar SLAs al cambiar proveedor (solo en creacion)
    if (!issue) {
      document.getElementById('vi-f-supplier').onchange = async (e) => {
        const sup = _suppliers.find(s => s.id == e.target.value);
        supplierSlas = sup?.slas || [];
        _renderSlaBreachwes(supplierSlas, []);
      };
    } else {
      // En edicion los SLAs ya estan pre-renderizados — cablear checkboxes
      _wireSlaCheckboxes();
    }

    // Boton + para añadir item de accion
    document.getElementById('vi-add-action')?.addEventListener('click', () => {
      const text = document.getElementById('vi-new-action-text')?.value?.trim();
      if (!text) return;
      actionItems = [...actionItems, { text, done: false, due_date: document.getElementById('vi-new-action-due')?.value || null }];
      _renderActionItems(actionItems);
      if (document.getElementById('vi-new-action-text')) document.getElementById('vi-new-action-text').value = '';
    });

    // Cablear items de accion ya pre-renderizados
    if (actionItems.length) _wireActionItems(actionItems);

    document.getElementById('vi-save-btn').onclick = () => _save(issue?.id, supplierSlas, actionItems);
  }

  function _formHtml(issue, supplierSlas, actionItems) {
    const supOptions = _suppliers.map(s =>
      `<option value="${s.id}" ${issue?.supplier_id == s.id ? 'selected' : ''}>${UI.esc(s.name)}</option>`
    ).join('');

    const slaBreachesHtml = _slaBreachwesHtml(supplierSlas, issue?.sla_breaches || []);

    return `<div class="form-grid" style="max-height:70vh;overflow-y:auto;padding-right:4px;">
      <!-- Proveedor (solo en creacion) -->
      ${!issue ? `
      <div class="span2">
        <label>Proveedor *</label>
        <select id="vi-f-supplier" class="input">
          <option value="">— Seleccionar proveedor —</option>
          ${supOptions}
        </select>
      </div>` : `<input type="hidden" id="vi-f-supplier" value="${issue.supplier_id}">`}

      <!-- Titulo y fuente -->
      <div class="span2">
        <label>Titulo *</label>
        <input id="vi-f-title" class="input" value="${UI.esc(issue?.title||'')}" placeholder="Describe el hallazgo brevemente">
      </div>
      <div>
        <label>Severidad</label>
        <select id="vi-f-severity" class="input">
          ${Object.entries(SEV_LABELS).map(([k, l]) =>
            `<option value="${k}" ${(issue?.severity||'medium')===k?'selected':''}>${l}</option>`
          ).join('')}
        </select>
      </div>
      <div>
        <label>Fuente</label>
        <select id="vi-f-source" class="input">
          ${Object.entries(SOURCE_LABELS).map(([k, l]) =>
            `<option value="${k}" ${(issue?.source||'manual')===k?'selected':''}>${l}</option>`
          ).join('')}
        </select>
      </div>

      ${issue ? `
      <div>
        <label>Estado</label>
        <select id="vi-f-status" class="input">
          ${Object.entries(STATUS_LABELS).map(([k, l]) =>
            `<option value="${k}" ${issue.status===k?'selected':''}>${l}</option>`
          ).join('')}
        </select>
      </div>
      <div>
        <label>Fecha limite</label>
        <input type="date" id="vi-f-due" class="input" value="${issue.due_date?issue.due_date.slice(0,10):''}">
      </div>` : `<div>
        <label>Fecha limite (opcional)</label>
        <input type="date" id="vi-f-due" class="input">
      </div><div></div>`}

      <!-- Descripcion -->
      <div class="span2">
        <label>Descripcion</label>
        <textarea id="vi-f-desc" class="input" rows="3" placeholder="Detalla el hallazgo...">${UI.esc(issue?.description||'')}</textarea>
      </div>

      <!-- SLA breaches -->
      <div class="span2" id="vi-sla-section">
        <label style="font-weight:700;">SLAs incumplidos</label>
        <div id="vi-sla-breaches">${slaBreachesHtml}</div>
      </div>

      <!-- Impacto -->
      <div class="span2">
        <label>Descripcion del impacto</label>
        <textarea id="vi-f-impact" class="input" rows="2" placeholder="Impacto operativo, reputacional o regulatorio...">${UI.esc(issue?.impact_description||'')}</textarea>
      </div>

      <!-- Causa raiz -->
      <div class="span2">
        <label>Causa raiz</label>
        <textarea id="vi-f-root" class="input" rows="2" placeholder="Analisis de causa raiz (5 Whys, Ishikawa...)...">${UI.esc(issue?.root_cause||'')}</textarea>
      </div>

      <!-- Plan de remediacion -->
      <div class="span2">
        <label>Plan de remediacion</label>
        <textarea id="vi-f-plan" class="input" rows="3" placeholder="Acciones y plazos para resolver el hallazgo...">${UI.esc(issue?.remediation_plan||'')}</textarea>
      </div>

      <!-- Items de accion -->
      <div class="span2">
        <label style="font-weight:700;">Items de accion</label>
        <div id="vi-action-items">${_actionItemsHtml(actionItems)}</div>
        <div style="display:flex;gap:6px;margin-top:6px;">
          <input id="vi-new-action-text" class="input" style="flex:1;" placeholder="Nueva accion...">
          <input type="date" id="vi-new-action-due" class="input" style="width:130px;" title="Fecha limite de la accion">
          <button type="button" id="vi-add-action" class="btn btn-sm">+ Agregar</button>
        </div>
      </div>

      <!-- Evidencias -->
      <div class="span2">
        <label>Referencias de evidencia (URL o nombre)</label>
        <textarea id="vi-f-evidence" class="input" rows="2" placeholder="Una por linea: https://... o Nombre del fichero">${(issue?.evidence_refs||[]).map(e=>e.url||e.name||'').join('\n')}</textarea>
      </div>

      ${issue ? `
      <!-- Notas de resolucion -->
      <div class="span2">
        <label>Notas de resolucion</label>
        <textarea id="vi-f-resolution" class="input" rows="2" placeholder="Comentarios al cerrar o mitigar el hallazgo...">${UI.esc(issue?.resolution_notes||'')}</textarea>
      </div>` : ''}
    </div>`;
  }

  function _slaBreachwesHtml(supplierSlas, currentBreaches) {
    if (!supplierSlas.length) {
      return `<p style="font-size:12px;color:var(--text-muted);margin:4px 0;">
        El proveedor no tiene SLAs registrados.
        <a href="#/suppliers" style="color:var(--brand-purple);">Ir a Proveedores → Editar para definir SLAs</a>.
      </p>`;
    }
    return supplierSlas.map(sla => {
      const breach = currentBreaches.find(b => b.sla_id === sla.id);
      return `<div style="border:1px solid var(--border);border-radius:6px;padding:8px 12px;margin-bottom:6px;background:var(--bg-2);">
        <label style="display:flex;align-items:flex-start;gap:8px;cursor:pointer;">
          <input type="checkbox" class="vi-sla-chk" data-sla-id="${UI.esc(sla.id)}" data-sla-name="${UI.esc(sla.name)}"
            style="margin-top:3px;" ${breach ? 'checked' : ''}>
          <div style="flex:1;">
            <div style="font-size:13px;font-weight:600;">${UI.esc(sla.name)}
              ${sla.metric ? `<span style="font-size:11px;color:var(--text-muted);font-weight:400;margin-left:6px;">${UI.esc(sla.metric)}</span>` : ''}
            </div>
            ${sla.category ? `<div style="font-size:11px;color:var(--text-subtle);">${UI.esc(sla.category)}</div>` : ''}
            <input type="text" class="input vi-sla-details" data-sla-id="${UI.esc(sla.id)}"
              placeholder="Detalle del incumplimiento (opcional)..."
              style="margin-top:6px;font-size:12px;${!breach?'display:none;':''}"
              value="${breach ? UI.esc(breach.details||'') : ''}">
          </div>
        </label>
      </div>`;
    }).join('');
  }

  function _renderSlaBreachwes(supplierSlas, currentBreaches) {
    const container = document.getElementById('vi-sla-breaches');
    if (container) {
      container.innerHTML = _slaBreachwesHtml(supplierSlas, currentBreaches);
      _wireSlaCheckboxes();
    }
  }

  function _wireSlaCheckboxes() {
    document.querySelectorAll('.vi-sla-chk').forEach(chk => {
      chk.onchange = () => {
        const details = document.querySelector(`.vi-sla-details[data-sla-id="${chk.dataset.slaId}"]`);
        if (details) details.style.display = chk.checked ? '' : 'none';
      };
    });
  }

  function _actionItemsHtml(items) {
    if (!items.length) return '<p style="font-size:12px;color:var(--text-muted);margin:4px 0;">Sin items de accion aun.</p>';
    return items.map((a, i) => `
      <div style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--border);">
        <input type="checkbox" class="vi-act-done" data-idx="${i}" ${a.done?'checked':''}>
        <span style="flex:1;font-size:13px;${a.done?'text-decoration:line-through;color:var(--text-subtle);':''}">${UI.esc(a.text)}</span>
        ${a.due_date ? `<span style="font-size:11px;color:var(--text-muted);">${a.due_date}</span>` : ''}
        <button type="button" class="btn btn-sm btn-danger vi-act-del" data-idx="${i}" style="padding:2px 7px;font-size:11px;">X</button>
      </div>`).join('');
  }

  function _renderActionItems(items) {
    const container = document.getElementById('vi-action-items');
    if (container) {
      container.innerHTML = _actionItemsHtml(items);
      _wireActionItems(items);
    }
  }

  function _wireActionItems(items) {
    document.querySelectorAll('.vi-act-done').forEach(chk => {
      chk.onchange = () => {
        items[parseInt(chk.dataset.idx)].done = chk.checked;
        _renderActionItems(items);
      };
    });
    document.querySelectorAll('.vi-act-del').forEach(btn => {
      btn.onclick = () => {
        items.splice(parseInt(btn.dataset.idx), 1);
        _renderActionItems(items);
      };
    });
  }

  function _collectSlaBreaches() {
    const breaches = [];
    document.querySelectorAll('.vi-sla-chk:checked').forEach(chk => {
      const details = document.querySelector(`.vi-sla-details[data-sla-id="${chk.dataset.slaId}"]`);
      breaches.push({
        sla_id: chk.dataset.slaId,
        sla_name: chk.dataset.slaName,
        details: details?.value?.trim() || '',
      });
    });
    return breaches;
  }

  async function _save(id, supplierSlas, actionItems) {
    const supplierId = document.getElementById('vi-f-supplier')?.value;
    const title      = document.getElementById('vi-f-title')?.value?.trim();
    const severity   = document.getElementById('vi-f-severity')?.value;
    const source     = document.getElementById('vi-f-source')?.value;
    const status     = document.getElementById('vi-f-status')?.value;
    const due        = document.getElementById('vi-f-due')?.value || null;
    const desc       = document.getElementById('vi-f-desc')?.value?.trim() || null;
    const impact     = document.getElementById('vi-f-impact')?.value?.trim() || null;
    const rootCause  = document.getElementById('vi-f-root')?.value?.trim() || null;
    const plan       = document.getElementById('vi-f-plan')?.value?.trim() || null;
    const resolution = document.getElementById('vi-f-resolution')?.value?.trim() || null;

    if (!title) { UI.toast('El titulo es obligatorio', 'error'); return; }
    if (!id && !supplierId) { UI.toast('Selecciona un proveedor', 'error'); return; }

    // Recoger SLA breaches del DOM
    const slaBreaches = _collectSlaBreaches();

    // Evidencias: una por linea
    const evidText = document.getElementById('vi-f-evidence')?.value || '';
    const evidenceRefs = evidText.split('\n').map(l => l.trim()).filter(Boolean).map(l => {
      return l.startsWith('http') ? { name: l, url: l } : { name: l, url: null };
    });

    const body = {
      title, severity, source, description: desc,
      due_date: due ? new Date(due).toISOString() : null,
      sla_breaches: slaBreaches.length ? slaBreaches : null,
      impact_description: impact,
      root_cause: rootCause,
      remediation_plan: plan,
      action_items: actionItems.length ? actionItems : null,
      evidence_refs: evidenceRefs.length ? evidenceRefs : null,
      resolution_notes: resolution,
    };

    if (!id) { body.supplier_id = parseInt(supplierId); body.source = source; }
    if (status) body.status = status;

    const btn = document.getElementById('vi-save-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Guardando...'; }
    try {
      if (id) {
        await Api.vendor_issues.update(id, body);
      } else {
        await Api.vendor_issues.create(body);
      }
      UI.closeModal();
      UI.toast(id ? 'Hallazgo actualizado' : 'Hallazgo creado', 'success');
      await _loadStats();
      await _refresh();
    } catch (e) {
      UI.toast(e.message, 'error');
      if (btn) { btn.disabled = false; btn.textContent = id ? 'Guardar cambios' : 'Crear hallazgo'; }
    }
  }

  async function _del(id) {
    if (!confirm('¿Eliminar este hallazgo? Esta accion es irreversible.')) return;
    try {
      await Api.vendor_issues.del(id);
      UI.toast('Hallazgo eliminado', 'success');
      await _loadStats();
      await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  return { render, _openDetail, _openForm, _del };
})();
