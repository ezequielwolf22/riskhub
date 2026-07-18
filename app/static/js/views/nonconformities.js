/* Vista de no conformidades y acciones correctivas (ISO 27001:2022 cl. 10.1). */
const ViewNonConformities = (() => {

  const STATUS_LABELS = () => ({
    open: t('nonconformities.status.open'),
    in_progress: t('nonconformities.status.in_progress'),
    pending_verification: t('common.pending'),
    closed: t('nonconformities.status.closed'),
  });
  const STATUS_COLORS = {
    open: 'var(--risk-critical)', in_progress: 'var(--risk-high)',
    pending_verification: 'var(--risk-medium)', closed: 'var(--text-muted)',
  };
  const SEV_LABELS = () => ({
    observation: t('nonconformities.severity.observation'),
    minor: t('nonconformities.severity.minor'),
    major: t('nonconformities.severity.major'),
  });
  const SEV_COLORS = {
    observation: 'var(--text-muted)', minor: 'var(--risk-medium)', major: 'var(--risk-critical)',
  };

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  async function render(el) {
    const statusLabels = STATUS_LABELS();
    const sevLabels = SEV_LABELS();
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('nonconformities.title')}</h1>
          <p class="page-sub">${t('nonconformities.subtitle')}</p>
        </div>
        <button class="btn btn-primary" id="btn-new-nc">+ ${t('nonconformities.new')}</button>
      </div>

      <div class="stats-row" id="nc-stats" style="margin-bottom:16px;"></div>

      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <select id="f-status" class="input" style="width:190px;">
          <option value="">${t('common.all')}</option>
          ${Object.entries(statusLabels).map(([k,l]) => `<option value="${k}">${l}</option>`).join('')}
        </select>
        <select id="f-severity" class="input" style="width:160px;">
          <option value="">${t('common.all')}</option>
          ${Object.entries(sevLabels).map(([k,l]) => `<option value="${k}">${l}</option>`).join('')}
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
        <div class="stat-card"><div class="stat-value">${s.total}</div><div class="stat-label">${t('common.total')} NC</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-high);">${s.open}</div><div class="stat-label">${t('nonconformities.status.open')}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-critical);">${s.major_open}</div><div class="stat-label">${t('nonconformities.severity.major')} ${t('nonconformities.status.open').toLowerCase()}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.overdue}</div><div class="stat-label">${t('tasks.overdue')}</div></div>
      `;
    } catch (_) {}
  }

  async function _refresh() {
    const status = document.getElementById('f-status')?.value || '';
    const severity = document.getElementById('f-severity')?.value || '';
    const wrap = document.getElementById('nc-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = `<p class="text-muted">${t('common.loading')}</p>`;
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
    const statusLabels = STATUS_LABELS();
    const sevLabels = SEV_LABELS();
    if (!data.length) {
      wrap.innerHTML = `<p class="text-muted" style="margin-top:24px;text-align:center;">${t('common.no_results')}</p>`;
      return;
    }
    const now = new Date();
    const rows = data.map(nc => {
      const isOverdue = nc.due_date && new Date(nc.due_date) < now && nc.status !== 'closed';
      return `
        <tr ${isOverdue ? 'style="background:var(--risk-bg-high);"' : ''}>
          <td><b>${UI.esc(nc.code)}</b></td>
          <td>${UI.esc(nc.title)}</td>
          <td>${_badge(sevLabels[nc.severity] || nc.severity, SEV_COLORS[nc.severity] || '#888')}</td>
          <td>${_badge(statusLabels[nc.status] || nc.status, STATUS_COLORS[nc.status] || '#888')}</td>
          <td>${UI.esc(nc.iso_clause || '-')}</td>
          <td>${nc.due_date ? nc.due_date.slice(0,10) : '-'}${isOverdue ? ` <b style="color:var(--risk-critical);">[${t('tasks.overdue').toUpperCase()}]</b>` : ''}</td>
          <td>
            <button class="btn btn-sm" data-id="${nc.id}" data-action="edit">${t('common.edit')}</button>
            <button class="btn btn-sm btn-danger" data-id="${nc.id}" data-action="del">${t('common.delete')}</button>
          </td>
        </tr>
      `;
    }).join('');

    wrap.innerHTML = `
      <table class="data">
        <thead>
          <tr>
            <th>${t('common.name')}</th><th>${t('nonconformities.nc_title')}</th><th>${t('common.severity')}</th><th>${t('common.status')}</th>
            <th>${t('nonconformities.linked_audit')}</th><th>${t('common.due_date')}</th><th>${t('common.actions')}</th>
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
        if (!confirm(t('nonconformities.delete_confirm'))) return;
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
    const statusLabels = STATUS_LABELS();
    const sevLabels = SEV_LABELS();
    const v = nc || {};
    return `
      <div class="form-grid">
        <div class="span2"><label>${t('nonconformities.nc_title')} *</label><input id="f-title" class="input" value="${UI.esc(v.title || '')}"></div>
        <div><label>${t('common.severity')}</label>
          <select id="f-sev" class="input">
            ${Object.entries(sevLabels).map(([k,l]) => `<option value="${k}" ${v.severity===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div><label>${t('common.status')}</label>
          <select id="f-stat" class="input">
            ${Object.entries(statusLabels).map(([k,l]) => `<option value="${k}" ${v.status===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div><label>${t('nonconformities.linked_audit')}</label><input id="f-clause" class="input" value="${UI.esc(v.iso_clause || '')}" placeholder="Ej: 6.1.2, 9.2..."></div>
        <div><label>${t('common.source')}</label><input id="f-source" class="input" value="${UI.esc(v.source || '')}" placeholder="Auditoría interna, auditoría externa..."></div>
        <div class="span2"><label>${t('common.description')}</label><textarea id="f-desc" class="input" rows="3">${UI.esc(v.description || '')}</textarea></div>
        <div class="span2"><label>${t('nonconformities.root_cause')}</label><textarea id="f-root" class="input" rows="2">${UI.esc(v.root_cause || '')}</textarea></div>
        <div class="span2"><label>${t('nonconformities.corrective_action')}</label><textarea id="f-action" class="input" rows="2">${UI.esc(v.corrective_action || '')}</textarea></div>
        <div><label>${t('common.due_date')}</label><input type="date" id="f-due" class="input" value="${v.due_date ? v.due_date.slice(0,10) : ''}"></div>
        <div><label>${t('controls.evidence')}</label><input id="f-evidence" class="input" value="${UI.esc(v.evidence || '')}"></div>
      </div>
    `;
  }

  function _openForm(nc) {
    UI.modal(nc ? `${t('nonconformities.edit')} ${nc.code}` : t('nonconformities.new'), _formHtml(nc), {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => _save(nc);
  }

  async function _save(nc) {
    const title = document.getElementById('f-title').value.trim();
    if (!title) { UI.toast(t('common.required'), 'error'); return; }
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
        UI.toast(t('common.success'), 'success');
      } else {
        await Api.nonconformities.create(payload);
        UI.toast(t('common.success'), 'success');
      }
      UI.closeModal();
      await _loadStats();
      await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  return { render };
})();
