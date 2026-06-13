/* Vista de hallazgos de proveedores con SLA por severidad (TPRM Sprint 7). */
const ViewVendorIssues = (() => {

  const SEV_LABELS = {
    critical: 'Critico',
    high: 'Alto',
    medium: 'Medio',
    low: 'Bajo',
    informational: 'Informativo',
  };

  const SEV_COLORS = {
    critical: 'var(--risk-critical)',
    high: 'var(--risk-high)',
    medium: 'var(--risk-medium)',
    low: 'var(--risk-low)',
    informational: '#9CA3AF',
  };

  const STATUS_LABELS = {
    open: 'Abierto',
    acknowledged: 'Reconocido',
    in_remediation: 'En remediacion',
    mitigated: 'Mitigado',
    accepted: 'Aceptado',
    closed: 'Cerrado',
    overdue: 'Vencido',
  };

  const STATUS_COLORS = {
    open: 'var(--risk-high)',
    acknowledged: 'var(--risk-medium)',
    in_remediation: '#6366F1',
    mitigated: '#10B981',
    accepted: '#9CA3AF',
    closed: 'var(--text-muted)',
    overdue: 'var(--risk-critical)',
  };

  const SOURCE_LABELS = {
    questionnaire: 'Cuestionario',
    external_rating: 'Calificacion externa',
    manual: 'Manual',
    incident: 'Incidente',
    monitoring: 'Monitoreo',
  };

  // Cache de proveedores para el selector de filtro y formulario
  let _suppliers = [];

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Hallazgos de proveedores</h1>
          <p class="page-sub">Gestion de issues con SLA por severidad — remediacion y aceptacion de riesgo</p>
        </div>
        ${Auth.canEdit() ? '<button class="btn btn-primary" id="btn-new-issue">+ Nuevo hallazgo</button>' : ''}
      </div>

      <div class="stats-row" id="vi-stats" style="margin-bottom:16px;"></div>

      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <select id="f-supplier" class="input" style="width:210px;">
          <option value="">Todos los proveedores</option>
        </select>
        <select id="f-severity" class="input" style="width:160px;">
          <option value="">Todas las severidades</option>
          ${Object.entries(SEV_LABELS).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}
        </select>
        <select id="f-status" class="input" style="width:190px;">
          <option value="">Todos los estados</option>
          ${Object.entries(STATUS_LABELS).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}
        </select>
      </div>

      <div id="vi-table-wrap"></div>
    `;

    if (Auth.canEdit()) {
      document.getElementById('btn-new-issue').onclick = () => _openNewForm();
    }
    document.getElementById('f-supplier').onchange = _refresh;
    document.getElementById('f-severity').onchange = _refresh;
    document.getElementById('f-status').onchange = _refresh;

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
      wrap.innerHTML = `
        <div class="stat-card">
          <div class="stat-value">${s.total}</div>
          <div class="stat-label">Total hallazgos</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:var(--risk-high);">${s.open}</div>
          <div class="stat-label">Abiertos</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:var(--risk-critical);">${s.overdue}</div>
          <div class="stat-label">Vencidos</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" style="color:var(--risk-critical);">${s.by_severity.critical || 0}</div>
          <div class="stat-label">Criticos</div>
        </div>
      `;
    } catch (_) {}
  }

  async function _refresh() {
    const supplierId = document.getElementById('f-supplier')?.value || '';
    const severity = document.getElementById('f-severity')?.value || '';
    const status = document.getElementById('f-status')?.value || '';
    const wrap = document.getElementById('vi-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<p class="text-muted">Cargando...</p>';
    try {
      const params = {};
      if (supplierId) params.supplier_id = supplierId;
      if (severity) params.severity = severity;
      if (status) params.status = status;
      const data = await Api.vendor_issues.list(params);
      _renderTable(wrap, data);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _renderTable(wrap, data) {
    if (!data.length) {
      wrap.innerHTML = '<p class="text-muted" style="margin-top:24px;text-align:center;">No se encontraron hallazgos.</p>';
      return;
    }
    const now = new Date();
    const rows = data.map(issue => {
      const isOverdue = issue.status === 'overdue' || (
        issue.due_date &&
        new Date(issue.due_date) < now &&
        !['closed', 'mitigated', 'accepted'].includes(issue.status)
      );
      const dueDateStr = issue.due_date ? issue.due_date.slice(0, 10) : '-';
      const dueDateHtml = issue.due_date
        ? `${dueDateStr}${isOverdue ? ' <b style="color:var(--risk-critical);">[VENCIDO]</b>' : ''}`
        : '-';
      return `
        <tr ${isOverdue ? 'style="background:var(--risk-bg-high);"' : ''}>
          <td><b>${UI.esc(issue.code)}</b></td>
          <td>${UI.esc(issue.supplier_name || '-')}</td>
          <td>${UI.esc(issue.title)}</td>
          <td>${_badge(SEV_LABELS[issue.severity] || issue.severity, SEV_COLORS[issue.severity] || '#888')}</td>
          <td>${_badge(STATUS_LABELS[issue.status] || issue.status, STATUS_COLORS[issue.status] || '#888')}</td>
          <td>${dueDateHtml}</td>
          <td>
            <button class="btn btn-sm" data-id="${issue.id}" data-action="edit">Editar</button>
            <button class="btn btn-sm btn-danger" data-id="${issue.id}" data-action="del">Eliminar</button>
          </td>
        </tr>
      `;
    }).join('');

    wrap.innerHTML = `
      <table class="data">
        <thead>
          <tr>
            <th>Codigo</th>
            <th>Proveedor</th>
            <th>Titulo</th>
            <th>Severidad</th>
            <th>Estado</th>
            <th>Vence</th>
            <th>Acciones</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;

    wrap.querySelectorAll('[data-action="edit"]').forEach(btn => {
      btn.onclick = () => {
        const issue = data.find(i => i.id == btn.dataset.id);
        if (issue) _openEditForm(issue);
      };
    });

    wrap.querySelectorAll('[data-action="del"]').forEach(btn => {
      btn.onclick = async () => {
        if (!confirm('Eliminar este hallazgo?')) return;
        try {
          await Api.vendor_issues.del(btn.dataset.id);
          UI.toast('Hallazgo eliminado', 'success');
          await _loadStats();
          await _refresh();
        } catch (e) {
          UI.toast(e.message, 'error');
        }
      };
    });
  }

  function _supplierOptions(selectedId) {
    return _suppliers.map(s =>
      `<option value="${s.id}" ${s.id == selectedId ? 'selected' : ''}>${UI.esc(s.name)}</option>`
    ).join('');
  }

  function _newFormHtml() {
    return `
      <div class="form-grid">
        <div class="span2"><label>Proveedor *</label>
          <select id="f-supplier-id" class="input">
            <option value="">-- Seleccionar proveedor --</option>
            ${_supplierOptions(null)}
          </select>
        </div>
        <div class="span2"><label>Titulo *</label>
          <input id="f-title" class="input" placeholder="Describe el hallazgo">
        </div>
        <div><label>Severidad</label>
          <select id="f-severity-sel" class="input">
            ${Object.entries(SEV_LABELS).map(([k, l]) =>
              `<option value="${k}" ${k === 'medium' ? 'selected' : ''}>${l}</option>`
            ).join('')}
          </select>
        </div>
        <div><label>Fuente</label>
          <select id="f-source" class="input">
            ${Object.entries(SOURCE_LABELS).map(([k, l]) =>
              `<option value="${k}" ${k === 'manual' ? 'selected' : ''}>${l}</option>`
            ).join('')}
          </select>
        </div>
        <div class="span2"><label>Descripcion</label>
          <textarea id="f-desc" class="input" rows="3" placeholder="Detalle del hallazgo..."></textarea>
        </div>
        <div class="span2"><label>Plan de remediacion</label>
          <textarea id="f-plan" class="input" rows="2" placeholder="Acciones previstas para resolver el hallazgo..."></textarea>
        </div>
      </div>
    `;
  }

  function _editFormHtml(issue) {
    return `
      <div class="form-grid">
        <div><label>Severidad</label>
          <select id="f-severity-sel" class="input">
            ${Object.entries(SEV_LABELS).map(([k, l]) =>
              `<option value="${k}" ${issue.severity === k ? 'selected' : ''}>${l}</option>`
            ).join('')}
          </select>
        </div>
        <div><label>Estado</label>
          <select id="f-status-sel" class="input">
            ${Object.entries(STATUS_LABELS).map(([k, l]) =>
              `<option value="${k}" ${issue.status === k ? 'selected' : ''}>${l}</option>`
            ).join('')}
          </select>
        </div>
        <div><label>Fecha limite</label>
          <input type="date" id="f-due" class="input" value="${issue.due_date ? issue.due_date.slice(0, 10) : ''}">
        </div>
        <div><label>Responsable (ID usuario)</label>
          <input type="number" id="f-assigned" class="input" value="${issue.assigned_to_user_id || ''}" placeholder="ID del usuario responsable">
        </div>
        <div class="span2"><label>Plan de remediacion</label>
          <textarea id="f-plan" class="input" rows="3">${UI.esc(issue.remediation_plan || '')}</textarea>
        </div>
      </div>
    `;
  }

  function _openNewForm() {
    UI.modal('Nuevo hallazgo', _newFormHtml(), {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => _saveNew();
  }

  function _openEditForm(issue) {
    UI.modal(`Editar ${issue.code}`, _editFormHtml(issue), {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => _saveEdit(issue);
  }

  async function _saveNew() {
    const supplierId = document.getElementById('f-supplier-id').value;
    const title = document.getElementById('f-title').value.trim();
    if (!supplierId) { UI.toast('Selecciona un proveedor', 'error'); return; }
    if (!title) { UI.toast('El titulo es obligatorio', 'error'); return; }
    const payload = {
      supplier_id: parseInt(supplierId, 10),
      title,
      severity: document.getElementById('f-severity-sel').value,
      source: document.getElementById('f-source').value,
      description: document.getElementById('f-desc').value.trim() || null,
      remediation_plan: document.getElementById('f-plan').value.trim() || null,
    };
    try {
      await Api.vendor_issues.create(payload);
      UI.toast('Hallazgo creado', 'success');
      UI.closeModal();
      await _loadStats();
      await _refresh();
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  }

  async function _saveEdit(issue) {
    const dueVal = document.getElementById('f-due').value;
    const assignedVal = document.getElementById('f-assigned').value;
    const payload = {
      severity: document.getElementById('f-severity-sel').value,
      status: document.getElementById('f-status-sel').value,
      due_date: dueVal || null,
      assigned_to_user_id: assignedVal ? parseInt(assignedVal, 10) : null,
      remediation_plan: document.getElementById('f-plan').value.trim() || null,
    };
    try {
      await Api.vendor_issues.update(issue.id, payload);
      UI.toast('Hallazgo actualizado', 'success');
      UI.closeModal();
      await _loadStats();
      await _refresh();
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  }

  return { render };
})();
