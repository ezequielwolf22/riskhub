/* Vista de no conformidades y acciones correctivas (ISO 27001:2022 cl. 10.1). */
const ViewNonConformities = (() => {

  const STATUS_LABELS = {
    open: 'Abierta', in_progress: 'En proceso',
    pending_verification: 'Pendiente verificacion', closed: 'Cerrada',
  };
  const STATUS_COLORS = {
    open: 'var(--risk-critical)', in_progress: 'var(--risk-high)',
    pending_verification: 'var(--risk-medium)', closed: 'var(--text-muted)',
  };
  const SEV_LABELS = { observation: 'Observacion', minor: 'Menor', major: 'Mayor' };
  const SEV_COLORS = {
    observation: 'var(--text-muted)', minor: 'var(--risk-medium)', major: 'var(--risk-critical)',
  };

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">No Conformidades y Acciones Correctivas</h1>
          <p class="page-sub">Gestion de no conformidades — ISO 27001:2022 clausula 10.1</p>
        </div>
        <button class="btn btn-primary" id="btn-new-nc">+ Nueva NC</button>
      </div>

      <div class="stats-row" id="nc-stats" style="margin-bottom:16px;"></div>

      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <select id="f-status" class="input" style="width:190px;">
          <option value="">Todos los estados</option>
          ${Object.entries(STATUS_LABELS).map(([k,l]) => `<option value="${k}">${l}</option>`).join('')}
        </select>
        <select id="f-severity" class="input" style="width:160px;">
          <option value="">Todas las severidades</option>
          ${Object.entries(SEV_LABELS).map(([k,l]) => `<option value="${k}">${l}</option>`).join('')}
        </select>
      </div>

      <div id="nc-table-wrap"></div>
    `;

    document.getElementById('btn-new-nc').onclick = () => _openForm(null);
    document.getElementById('f-status').onchange = _refresh;
    document.getElementById('f-severity').onchange = _refresh;

    await _loadStats();
    await _refresh();
  }

  async function _loadStats() {
    try {
      const s = await Api.nonconformities.summary();
      const wrap = document.getElementById('nc-stats');
      if (!wrap) return;
      wrap.innerHTML = `
        <div class="stat-card"><div class="stat-value">${s.total}</div><div class="stat-label">Total NC</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-high);">${s.open}</div><div class="stat-label">Abiertas</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-critical);">${s.major_open}</div><div class="stat-label">Mayores abiertas</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.overdue}</div><div class="stat-label">Vencidas</div></div>
      `;
    } catch (_) {}
  }

  async function _refresh() {
    const status = document.getElementById('f-status')?.value || '';
    const severity = document.getElementById('f-severity')?.value || '';
    const wrap = document.getElementById('nc-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<p class="text-muted">Cargando...</p>';
    try {
      const params = {};
      if (status) params.status = status;
      if (severity) params.severity = severity;
      const data = await Api.nonconformities.list(params);
      _renderTable(wrap, data);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _renderTable(wrap, data) {
    if (!data.length) {
      wrap.innerHTML = '<p class="text-muted" style="margin-top:24px;text-align:center;">No se encontraron no conformidades.</p>';
      return;
    }
    const now = new Date();
    const rows = data.map(nc => {
      const isOverdue = nc.due_date && new Date(nc.due_date) < now && nc.status !== 'closed';
      return `
        <tr ${isOverdue ? 'style="background:var(--risk-bg-high);"' : ''}>
          <td><b>${UI.esc(nc.code)}</b></td>
          <td>${UI.esc(nc.title)}</td>
          <td>${_badge(SEV_LABELS[nc.severity] || nc.severity, SEV_COLORS[nc.severity] || '#888')}</td>
          <td>${_badge(STATUS_LABELS[nc.status] || nc.status, STATUS_COLORS[nc.status] || '#888')}</td>
          <td>${UI.esc(nc.iso_clause || '-')}</td>
          <td>${nc.due_date ? nc.due_date.slice(0,10) : '-'}${isOverdue ? ' <b style="color:var(--risk-critical);">[VENCIDA]</b>' : ''}</td>
          <td>
            <button class="btn btn-sm" data-id="${nc.id}" data-action="edit">Editar</button>
            <button class="btn btn-sm btn-danger" data-id="${nc.id}" data-action="del">Eliminar</button>
          </td>
        </tr>
      `;
    }).join('');

    wrap.innerHTML = `
      <table class="data">
        <thead>
          <tr>
            <th>Codigo</th><th>Titulo</th><th>Severidad</th><th>Estado</th>
            <th>Clausula ISO</th><th>Fecha limite</th><th>Acciones</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;

    wrap.querySelectorAll('[data-action="edit"]').forEach(btn => {
      btn.onclick = () => {
        const nc = data.find(n => n.id == btn.dataset.id);
        if (nc) _openForm(nc);
      };
    });
    wrap.querySelectorAll('[data-action="del"]').forEach(btn => {
      btn.onclick = async () => {
        if (!confirm('Eliminar no conformidad?')) return;
        try {
          await Api.nonconformities.del(btn.dataset.id);
          UI.toast('NC eliminada', 'success');
          await _loadStats();
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });
  }

  function _formHtml(nc) {
    const v = nc || {};
    return `
      <div class="form-grid">
        <div class="span2"><label>Titulo *</label><input id="f-title" class="input" value="${UI.esc(v.title || '')}"></div>
        <div><label>Severidad</label>
          <select id="f-sev" class="input">
            ${Object.entries(SEV_LABELS).map(([k,l]) => `<option value="${k}" ${v.severity===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div><label>Estado</label>
          <select id="f-stat" class="input">
            ${Object.entries(STATUS_LABELS).map(([k,l]) => `<option value="${k}" ${v.status===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div><label>Clausula ISO</label><input id="f-clause" class="input" value="${UI.esc(v.iso_clause || '')}" placeholder="Ej: 6.1.2, 9.2..."></div>
        <div><label>Origen / fuente</label><input id="f-source" class="input" value="${UI.esc(v.source || '')}" placeholder="Auditoria interna, auditoria externa..."></div>
        <div class="span2"><label>Descripcion</label><textarea id="f-desc" class="input" rows="3">${UI.esc(v.description || '')}</textarea></div>
        <div class="span2"><label>Causa raiz</label><textarea id="f-root" class="input" rows="2">${UI.esc(v.root_cause || '')}</textarea></div>
        <div class="span2"><label>Accion correctiva</label><textarea id="f-action" class="input" rows="2">${UI.esc(v.corrective_action || '')}</textarea></div>
        <div><label>Fecha limite</label><input type="date" id="f-due" class="input" value="${v.due_date ? v.due_date.slice(0,10) : ''}"></div>
        <div><label>Evidencias</label><input id="f-evidence" class="input" value="${UI.esc(v.evidence || '')}"></div>
      </div>
    `;
  }

  function _openForm(nc) {
    UI.modal(nc ? `Editar ${nc.code}` : 'Nueva no conformidad', _formHtml(nc), {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => _save(nc);
  }

  async function _save(nc) {
    const title = document.getElementById('f-title').value.trim();
    if (!title) { UI.toast('El titulo es obligatorio', 'error'); return; }
    const payload = {
      title,
      severity: document.getElementById('f-sev').value,
      status: document.getElementById('f-stat').value,
      iso_clause: document.getElementById('f-clause').value.trim(),
      source: document.getElementById('f-source').value.trim(),
      description: document.getElementById('f-desc').value.trim(),
      root_cause: document.getElementById('f-root').value.trim(),
      corrective_action: document.getElementById('f-action').value.trim(),
      due_date: document.getElementById('f-due').value || null,
      evidence: document.getElementById('f-evidence').value.trim(),
    };
    try {
      if (nc) {
        await Api.nonconformities.update(nc.id, payload);
        UI.toast('NC actualizada', 'success');
      } else {
        await Api.nonconformities.create(payload);
        UI.toast('NC creada', 'success');
      }
      UI.closeModal();
      await _loadStats();
      await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  return { render };
})();
