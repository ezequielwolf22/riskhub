/* Vista Tareas — Kanban de plan de tratamiento de riesgos. */
const ViewTasks = (() => {

  const STATUS_COLS = [
    { id: 'pending',     label: () => t('tasks.status.pending'),     color: 'var(--text-muted)' },
    { id: 'in_progress', label: () => t('tasks.status.in_progress'), color: 'var(--brand-purple)' },
    { id: 'blocked',     label: () => t('common.pending') /* TODO: i18n blocked */, color: 'var(--risk-high)' },
    { id: 'done',        label: () => t('tasks.status.completed'),   color: 'var(--risk-low)' },
  ];

  const PRIORITY_COLORS = {
    low: 'var(--risk-low)', medium: 'var(--risk-medium)',
    high: 'var(--risk-high)', critical: 'var(--risk-critical)',
  };
  const PRIORITY_LABELS = () => ({
    low: t('common.low'), medium: t('common.medium'), high: t('common.high'), critical: t('common.critical'),
  });

  let _tasks = [];
  let _users = [];
  let _risks = [];
  let _filterAssignee = '';

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:1px 7px;border-radius:999px;font-size:10px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('tasks.title')}</h1>
          <p class="page-sub">${t('tasks.subtitle')}</p>
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
          <select id="t-filter-assignee" class="input" style="width:180px;">
            <option value="">${t('common.all')}</option>
          </select>
          <button class="btn btn-primary" id="btn-new-task">+ ${t('tasks.new')}</button>
        </div>
      </div>

      <div class="stats-row" id="task-stats" style="margin-bottom:16px;"></div>
      <div id="task-board"></div>
    `;

    document.getElementById('btn-new-task').onclick = () => _openForm(null);
    document.getElementById('t-filter-assignee').onchange = (e) => {
      _filterAssignee = e.target.value;
      _renderBoard();
    };

    await _loadData();
    await _loadStats();
    _renderBoard();
  }

  async function _loadData() {
    try {
      const [tasks, users, risks] = await Promise.all([
        Api.tasks.list({}),
        Api.listUsers().catch(() => []),
        Api.risks.list({}).catch(() => []),
      ]);
      _tasks = tasks;
      _users = users;
      _risks = risks;

      // Populate assignee filter
      const sel = document.getElementById('t-filter-assignee');
      if (sel && users.length) {
        users.forEach(u => {
          const opt = document.createElement('option');
          opt.value = u.id;
          opt.textContent = u.full_name || u.email;
          sel.appendChild(opt);
        });
      }
    } catch (e) {
      UI.toast(t('common.error') + ': ' + e.message, 'error');
    }
  }

  async function _loadStats() {
    try {
      const s = await Api.tasks.summary();
      const wrap = document.getElementById('task-stats');
      if (!wrap) return;
      wrap.innerHTML = `
        <div class="stat-card"><div class="stat-value">${s.total}</div><div class="stat-label">${t('common.total')}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--brand-purple);">${s.by_status.in_progress||0}</div><div class="stat-label">${t('tasks.status.in_progress')}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-high);">${s.by_status.blocked||0}</div><div class="stat-label">${t('common.pending')} /* TODO: i18n blocked */</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-critical);">${s.overdue}</div><div class="stat-label">${t('tasks.overdue')}</div></div>
      `;
    } catch (_) {}
  }

  function _renderBoard() {
    const board = document.getElementById('task-board');
    if (!board) return;
    const now = new Date();
    const canEdit = Auth.canEdit();

    let filtered = _tasks;
    if (_filterAssignee) {
      filtered = filtered.filter(t => String(t.assigned_to_id) === String(_filterAssignee));
    }

    board.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;align-items:start;">
        ${STATUS_COLS.map(col => {
          const colTasks = filtered.filter(t => t.status === col.id);
          return `
            <div style="background:var(--bg-2);border-radius:10px;padding:12px;">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
                <span style="width:10px;height:10px;border-radius:50%;background:${col.color};display:inline-block;"></span>
                <span style="font-weight:600;font-size:13px;">${col.label()}</span>
                <span style="margin-left:auto;background:var(--bg-3);border-radius:999px;font-size:11px;font-weight:700;padding:2px 8px;color:var(--text-muted);">${colTasks.length}</span>
              </div>
              <div style="display:flex;flex-direction:column;gap:8px;" data-col="${col.id}">
                ${colTasks.map(t => _taskCard(t, now, canEdit)).join('')}
                ${canEdit ? `<button class="btn btn-ghost" style="font-size:12px;width:100%;margin-top:4px;" data-add-col="${col.id}">+ ${t('common.add')}</button>` : ''}
              </div>
            </div>`;
        }).join('')}
      </div>
    `;

    // Wire up card clicks
    board.querySelectorAll('[data-task-id]').forEach(card => {
      card.onclick = () => {
        const t = _tasks.find(x => x.id == card.dataset.taskId);
        if (t) _openForm(t);
      };
    });

    // Wire up quick move buttons
    board.querySelectorAll('[data-move-id]').forEach(btn => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const id = parseInt(btn.dataset.moveId);
        const newStatus = btn.dataset.moveTo;
        try {
          await Api.tasks.update(id, { status: newStatus });
          const idx = _tasks.findIndex(x => x.id === id);
          if (idx >= 0) _tasks[idx].status = newStatus;
          _renderBoard();
          await _loadStats();
        } catch (err) { UI.toast(err.message, 'error'); }
      };
    });

    // Wire up "add to column" shortcut
    board.querySelectorAll('[data-add-col]').forEach(btn => {
      btn.onclick = () => _openForm(null, btn.dataset.addCol);
    });
  }

  function _taskCard(t, now, canEdit) {
    const isOverdue = t.due_date && t.status !== 'done'
      && new Date(t.due_date) < now;
    const assignee = _users.find(u => u.id === t.assigned_to_id);
    const riskObj = _risks.find(r => r.id === t.risk_id);
    const dueFmt = t.due_date ? new Date(t.due_date).toLocaleDateString('es-ES') : null;

    const colIdx = STATUS_COLS.findIndex(c => c.id === t.status);
    const prevCol = colIdx > 0 ? STATUS_COLS[colIdx - 1] : null;
    const nextCol = colIdx < STATUS_COLS.length - 1 ? STATUS_COLS[colIdx + 1] : null;

    return `
      <div data-task-id="${t.id}" style="background:var(--bg-1);border:1px solid var(--border);
            border-radius:8px;padding:10px 12px;cursor:pointer;
            ${isOverdue ? 'border-left:3px solid var(--risk-critical);' : ''}
            transition:box-shadow .15s;"
           onmouseover="this.style.boxShadow='0 2px 10px rgba(0,0,0,.12)'"
           onmouseout="this.style.boxShadow='none'">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:6px;">
          <span style="font-size:10px;font-family:var(--font-mono);color:var(--text-muted);">${UI.esc(t.code)}</span>
          ${_badge(PRIORITY_LABELS()[t.priority] || t.priority, PRIORITY_COLORS[t.priority] || '#888')}
        </div>
        <div style="font-weight:600;font-size:13px;margin:5px 0 3px;">${UI.esc(t.title)}</div>
        ${riskObj ? `<div style="font-size:11px;color:var(--text-muted);">${t('common.risk')}: ${UI.esc(riskObj.code)} — ${UI.esc(riskObj.asset?.name||'')}</div>` : ''}
        ${assignee ? `<div style="font-size:11px;color:var(--text-subtle);margin-top:3px;">${t('common.owner')}: ${UI.esc(assignee.full_name||assignee.email)}</div>` : ''}
        ${dueFmt ? `<div style="font-size:11px;margin-top:3px;color:${isOverdue?'var(--risk-critical)':'var(--text-subtle)'};">
          ${isOverdue ? t('tasks.overdue') + ' — ' : ''}${t('common.due_date')}: ${dueFmt}
        </div>` : ''}
        ${canEdit ? `<div style="display:flex;gap:4px;margin-top:8px;justify-content:flex-end;" onclick="event.stopPropagation()">
          ${prevCol ? `<button class="btn btn-sm btn-ghost" data-move-id="${t.id}" data-move-to="${prevCol.id}" title="${prevCol.label()}">◀</button>` : ''}
          ${nextCol ? `<button class="btn btn-sm btn-ghost" data-move-id="${t.id}" data-move-to="${nextCol.id}" title="${nextCol.label()}">▶</button>` : ''}
        </div>` : ''}
      </div>`;
  }

  function _formHtml(t, defaultStatus) {
    const v = t || {};
    const status = v.status || defaultStatus || 'pending';
    return `
      <div class="form-grid">
        <div class="span2"><label>${t('tasks.task_name')} *</label><input id="f-title" class="input" value="${UI.esc(v.title||'')}"></div>
        <div>
          <label>${t('common.status')}</label>
          <select id="f-status" class="input">
            ${STATUS_COLS.map(c => `<option value="${c.id}" ${status===c.id?'selected':''}>${c.label()}</option>`).join('')}
          </select>
        </div>
        <div>
          <label>${t('common.priority')}</label>
          <select id="f-prio" class="input">
            ${Object.entries(PRIORITY_LABELS()).map(([k,l]) => `<option value="${k}" ${(v.priority||'medium')===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div>
          <label>${t('common.owner')}</label>
          <select id="f-assignee" class="input">
            <option value="">— ${t('common.not_assigned')} —</option>
            ${_users.map(u => `<option value="${u.id}" ${v.assigned_to_id===u.id?'selected':''}>${UI.esc(u.full_name||u.email)}</option>`).join('')}
          </select>
        </div>
        <div>
          <label>${t('tasks.related_risk')} (${t('common.optional')})</label>
          <select id="f-risk" class="input">
            <option value="">— ${t('common.none')} —</option>
            ${_risks.map(r => `<option value="${r.id}" ${v.risk_id===r.id?'selected':''}>${UI.esc(r.code)} — ${UI.esc(r.asset?.name||'')}</option>`).join('')}
          </select>
        </div>
        <div><label>${t('common.due_date')}</label><input type="datetime-local" id="f-due" class="input" value="${v.due_date ? v.due_date.slice(0,16) : ''}"></div>
        <div class="span2"><label>${t('common.description')}</label><textarea id="f-desc" class="input" rows="3">${UI.esc(v.description||'')}</textarea></div>
        <div class="span2"><label>${t('common.notes')}</label><textarea id="f-notes" class="input" rows="2">${UI.esc(v.notes||'')}</textarea></div>
      </div>
    `;
  }

  function _openForm(t, defaultStatus) {
    const title = t ? `${t('common.task')} ${t.code}` : t('tasks.new');
    UI.modal(title, _formHtml(t, defaultStatus), {
      actions: `
        <button class="btn" id="m-cancel">${t('common.cancel')}</button>
        ${t ? `<button class="btn btn-danger" id="m-del">${t('common.delete')}</button>` : ''}
        <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    if (t) document.getElementById('m-del').onclick = async () => {
      if (!confirm(t('tasks.delete_confirm'))) return;
      try {
        await Api.tasks.del(t.id);
        UI.toast(t('common.success'), 'success');
        UI.closeModal();
        _tasks = _tasks.filter(x => x.id !== t.id);
        _renderBoard();
        await _loadStats();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
    document.getElementById('m-save').onclick = () => _save(t);
  }

  async function _save(t) {
    const title = document.getElementById('f-title').value.trim();
    if (!title) { UI.toast(t('tasks.task_name') + ' ' + t('common.required').toLowerCase(), 'error'); return; }
    const riskVal = document.getElementById('f-risk').value;
    const assigneeVal = document.getElementById('f-assignee').value;
    const payload = {
      title,
      status: document.getElementById('f-status').value,
      priority: document.getElementById('f-prio').value,
      assigned_to_id: assigneeVal ? parseInt(assigneeVal) : null,
      risk_id: riskVal ? parseInt(riskVal) : null,
      due_date: document.getElementById('f-due').value || null,
      description: document.getElementById('f-desc').value.trim(),
      notes: document.getElementById('f-notes').value.trim(),
    };
    try {
      let updated;
      if (t) {
        updated = await Api.tasks.update(t.id, payload);
        _tasks = _tasks.map(x => x.id === t.id ? updated : x);
        UI.toast(t('common.success'), 'success');
      } else {
        updated = await Api.tasks.create(payload);
        _tasks.unshift(updated);
        UI.toast(t('common.success'), 'success');
      }
      UI.closeModal();
      _renderBoard();
      await _loadStats();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  return { render };
})();
