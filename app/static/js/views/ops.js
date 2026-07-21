/* Vista Admin — Operaciones: consumo IA, cola de trabajos, errores y backups. */
const ViewOps = (() => {

  const _JOB_BADGE = {
    pending:   'badge-info',
    running:   'badge-warning',
    done:      'badge-success',
    error:     'badge-danger',
    cancelled: 'badge-muted',
  };

  function _fmtTokens(n) {
    if (n == null) return '-';
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k';
    return String(n);
  }

  function _fmtBytes(n) {
    if (n == null) return '-';
    if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
    if (n >= 1024) return (n / 1024).toFixed(1) + ' KB';
    return n + ' B';
  }

  function _fmtDate(iso) {
    if (!iso) return '-';
    try { return new Date(iso).toLocaleString(); } catch (e) { return iso; }
  }

  async function render(el) {
    const isSuper = Auth.isSuperAdmin();
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('ops.page_title')}</h1>
          <p class="page-sub">${t('ops.page_subtitle')}</p>
        </div>
      </div>
      <div id="ops-usage" class="card" style="margin-bottom:16px;"><p class="text-muted">${t('common.loading')}</p></div>
      ${isSuper ? `<div id="ops-billing" class="card" style="margin-bottom:16px;"><p class="text-muted">${t('common.loading')}</p></div>` : ''}
      <div id="ops-jobs" class="card" style="margin-bottom:16px;"><p class="text-muted">${t('common.loading')}</p></div>
      ${isSuper ? `<div id="ops-errors" class="card" style="margin-bottom:16px;"><p class="text-muted">${t('common.loading')}</p></div>` : ''}
      ${isSuper ? `<div id="ops-backups" class="card" style="margin-bottom:16px;"><p class="text-muted">${t('common.loading')}</p></div>` : ''}
      ${isSuper ? `<div id="ops-regwatch" class="card" style="margin-bottom:16px;"><p class="text-muted">${t('common.loading')}</p></div>` : ''}
    `;
    _loadUsage();
    _loadJobs();
    if (isSuper) { _loadBilling(); _loadErrors(); _loadBackups(); _loadRegwatchQueue(); }
  }

  // ---------- Consumo IA ----------

  async function _loadUsage() {
    const box = document.getElementById('ops-usage');
    if (!box) return;
    try {
      const d = await Api.get('/api/ai/usage');
      const b = d.budget || {};
      const budgetLine = b.monthly_token_budget
        ? `${_fmtTokens(b.consumed_tokens)} / ${_fmtTokens(b.monthly_token_budget)} tokens (${b.pct_used}%)`
        : `${_fmtTokens(b.consumed_tokens)} tokens — ${t('ops.usage.no_budget')}`;
      const rows = (d.current_month || []).map(r => `
        <tr>
          <td>${UI.esc(r.call_type || '-')}</td>
          <td style="font-size:11px;color:var(--text-muted);">${UI.esc(r.model || '-')}</td>
          <td style="text-align:right;">${r.calls}</td>
          <td style="text-align:right;">${_fmtTokens(r.input_tokens)}</td>
          <td style="text-align:right;">${_fmtTokens(r.output_tokens)}</td>
          <td style="text-align:right;">$${(r.estimated_cost_usd || 0).toFixed(2)}</td>
        </tr>`).join('');
      const trend = (d.trend || []).slice(0, 6).map(m =>
        `<span style="margin-right:12px;">${UI.esc(m.month)}: ${_fmtTokens((m.input_tokens || 0) + (m.output_tokens || 0))}</span>`
      ).join('');
      box.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;">
          <h3 style="margin:0;">${t('ops.usage.title')} — ${UI.esc(d.month || '')}</h3>
          <b>${t('ops.usage.est_cost')}: $${((d.totals || {}).estimated_cost_usd || 0).toFixed(2)}</b>
        </div>
        <p style="font-size:12px;color:var(--text-muted);margin:6px 0 10px;">
          ${t('ops.usage.plan')}: <b>${UI.esc(b.plan || '-')}</b> · ${budgetLine}
          ${b.over_budget ? ` · <span style="color:var(--risk-high);font-weight:600;">${t('ops.usage.over_budget')}</span>` : ''}
        </p>
        ${rows ? `
        <div style="overflow-x:auto;">
          <table class="table">
            <thead><tr>
              <th>${t('ops.usage.call_type')}</th><th>${t('ops.usage.model')}</th>
              <th style="text-align:right;">${t('ops.usage.calls')}</th>
              <th style="text-align:right;">${t('ops.usage.tokens_in')}</th>
              <th style="text-align:right;">${t('ops.usage.tokens_out')}</th>
              <th style="text-align:right;">${t('ops.usage.cost')}</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>` : `<p class="text-muted">${t('ops.usage.empty')}</p>`}
        ${trend ? `<p style="font-size:11px;color:var(--text-subtle);margin:8px 0 0;">${t('ops.usage.trend')}: ${trend}</p>` : ''}
      `;
    } catch (e) {
      box.innerHTML = `<h3 style="margin-top:0;">${t('ops.usage.title')}</h3><div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  // ---------- Refacturacion IA por organización (superadmin) ----------

  function _monthOptions() {
    const opts = [];
    const now = new Date();
    for (let i = 0; i < 12; i++) {
      const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - i, 1));
      opts.push(`${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`);
    }
    return opts;
  }

  async function _loadBilling(month) {
    const box = document.getElementById('ops-billing');
    if (!box) return;
    try {
      const q = month ? `?month=${encodeURIComponent(month)}` : '';
      const d = await Api.get(`/api/ai/usage/global${q}`);
      const tot = d.totals || {};
      const rows = (d.organizations || []).map(o => `
        <tr data-org="${o.organization_id == null ? 0 : o.organization_id}" style="cursor:pointer;">
          <td>${UI.esc(o.name || '-')}</td>
          <td>${o.plan ? `<span class="badge badge-info">${UI.esc(o.plan)}</span>` : '<span class="badge badge-muted">plataforma</span>'}</td>
          <td style="text-align:center;">${o.has_own_key
            ? `<span class="badge badge-success">${t('ops.billing.own_key')}</span>`
            : `<span class="badge badge-warning">${t('ops.billing.vendor_key')}</span>`}</td>
          <td style="text-align:right;">${o.calls}</td>
          <td style="text-align:right;">${_fmtTokens(o.input_tokens)}</td>
          <td style="text-align:right;">${_fmtTokens(o.output_tokens)}</td>
          <td style="text-align:right;">$${(o.estimated_cost_usd || 0).toFixed(2)}</td>
          <td style="text-align:right;font-weight:600;">$${(o.billable_cost_usd || 0).toFixed(2)}</td>
        </tr>
        <tr data-detail="${o.organization_id == null ? 0 : o.organization_id}" style="display:none;">
          <td colspan="8" style="background:var(--bg-2);"></td>
        </tr>`).join('');
      const monthSel = _monthOptions().map(m =>
        `<option value="${m}" ${m === d.month ? 'selected' : ''}>${m}</option>`).join('');
      box.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;">
          <h3 style="margin:0;">${t('ops.billing.title')}</h3>
          <div style="display:flex;gap:10px;align-items:baseline;">
            <select id="ops-billing-month" class="input" style="width:auto;padding:4px 8px;font-size:12px;">${monthSel}</select>
            <b>${t('ops.billing.billable')}: $${(tot.billable_cost_usd || 0).toFixed(2)}</b>
          </div>
        </div>
        <p style="font-size:11px;color:var(--text-subtle);margin:6px 0 0;">${t('ops.billing.hint')}
          ${(tot.unknown_cost_usd || 0) > 0 ? ` ${t('ops.billing.unknown_note')}: $${tot.unknown_cost_usd.toFixed(2)}.` : ''}</p>
        ${rows ? `
        <div style="overflow-x:auto;margin-top:10px;">
          <table class="table">
            <thead><tr>
              <th>${t('ops.billing.org')}</th><th>${t('ops.billing.plan')}</th>
              <th style="text-align:center;">${t('ops.billing.key')}</th>
              <th style="text-align:right;">${t('ops.usage.calls')}</th>
              <th style="text-align:right;">${t('ops.usage.tokens_in')}</th>
              <th style="text-align:right;">${t('ops.usage.tokens_out')}</th>
              <th style="text-align:right;">${t('ops.billing.total_cost')}</th>
              <th style="text-align:right;">${t('ops.billing.billable')}</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>` : `<p class="text-muted" style="margin-top:10px;">${t('ops.usage.empty')}</p>`}
      `;
      const sel = document.getElementById('ops-billing-month');
      if (sel) sel.onchange = () => _loadBilling(sel.value);
      box.querySelectorAll('tr[data-org]').forEach(tr => {
        tr.onclick = () => _toggleBillingDetail(box, tr.dataset.org, d.month);
      });
    } catch (e) {
      box.innerHTML = `<h3 style="margin-top:0;">${t('ops.billing.title')}</h3><div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  async function _toggleBillingDetail(box, orgId, month) {
    const row = box.querySelector(`tr[data-detail="${orgId}"]`);
    if (!row) return;
    if (row.style.display !== 'none') { row.style.display = 'none'; return; }
    const cell = row.firstElementChild;
    cell.innerHTML = `<p class="text-muted" style="margin:8px;">${t('common.loading')}</p>`;
    row.style.display = '';
    try {
      const d = await Api.get(`/api/ai/usage/global?month=${encodeURIComponent(month)}&org_id=${orgId}`);
      const rows = (d.detail || []).map(r => `
        <tr>
          <td>${UI.esc(r.call_type || '-')}</td>
          <td style="font-size:11px;color:var(--text-muted);">${UI.esc(r.model || '-')}</td>
          <td>${UI.esc(r.key_source)}</td>
          <td style="text-align:right;">${r.calls}</td>
          <td style="text-align:right;">${_fmtTokens(r.input_tokens)}</td>
          <td style="text-align:right;">${_fmtTokens(r.output_tokens)}</td>
          <td style="text-align:right;">$${(r.estimated_cost_usd || 0).toFixed(3)}</td>
        </tr>`).join('');
      cell.innerHTML = rows ? `
        <table class="table" style="margin:6px 0;">
          <thead><tr>
            <th>${t('ops.usage.call_type')}</th><th>${t('ops.usage.model')}</th>
            <th>${t('ops.billing.key')}</th>
            <th style="text-align:right;">${t('ops.usage.calls')}</th>
            <th style="text-align:right;">${t('ops.usage.tokens_in')}</th>
            <th style="text-align:right;">${t('ops.usage.tokens_out')}</th>
            <th style="text-align:right;">${t('ops.usage.cost')}</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>` : `<p class="text-muted" style="margin:8px;">${t('ops.usage.empty')}</p>`;
    } catch (e) {
      cell.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  // ---------- Cola de trabajos ----------

  async function _loadJobs() {
    const box = document.getElementById('ops-jobs');
    if (!box) return;
    try {
      const jobs = await Api.get('/api/jobs?limit=25');
      const rows = (jobs || []).map(j => `
        <tr>
          <td>${j.id}</td>
          <td>${UI.esc(j.job_type)}</td>
          <td><span class="badge ${_JOB_BADGE[j.status] || 'badge-muted'}">${UI.esc(j.status)}</span></td>
          <td style="text-align:center;">${j.attempts}/${j.max_attempts}</td>
          <td style="font-size:11px;">${_fmtDate(j.created_at)}</td>
          <td style="font-size:11px;">${_fmtDate(j.finished_at)}</td>
          <td style="font-size:11px;color:var(--risk-high);">${UI.esc(j.error || '')}</td>
          <td>${j.status === 'pending'
            ? `<button class="btn btn-ghost btn-sm" data-cancel="${j.id}">${t('ops.jobs.cancel')}</button>` : ''}</td>
        </tr>`).join('');
      box.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:baseline;">
          <h3 style="margin:0;">${t('ops.jobs.title')}</h3>
          <button class="btn btn-ghost btn-sm" id="ops-jobs-reload">${t('common.refresh')}</button>
        </div>
        ${rows ? `
        <div style="overflow-x:auto;margin-top:10px;">
          <table class="table">
            <thead><tr>
              <th>ID</th><th>${t('ops.jobs.type')}</th><th>${t('ops.jobs.status')}</th>
              <th>${t('ops.jobs.attempts')}</th><th>${t('ops.jobs.created')}</th>
              <th>${t('ops.jobs.finished')}</th><th>${t('ops.jobs.error')}</th><th></th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>` : `<p class="text-muted" style="margin-top:10px;">${t('ops.jobs.empty')}</p>`}
      `;
      const reload = document.getElementById('ops-jobs-reload');
      if (reload) reload.onclick = _loadJobs;
      box.querySelectorAll('[data-cancel]').forEach(btn => {
        btn.onclick = async () => {
          try { await Api.post(`/api/jobs/${btn.dataset.cancel}/cancel`); _loadJobs(); }
          catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) {
      box.innerHTML = `<h3 style="margin-top:0;">${t('ops.jobs.title')}</h3><div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  // ---------- Errores capturados (superadmin) ----------

  async function _loadErrors() {
    const box = document.getElementById('ops-errors');
    if (!box) return;
    try {
      const errors = await Api.get('/api/admin/errors?limit=25');
      const rows = (errors || []).map(e => `
        <tr>
          <td style="font-size:11px;font-family:monospace;">${UI.esc(e.request_id || '-')}</td>
          <td>${UI.esc(e.method || '')} ${UI.esc(e.path || '')}</td>
          <td>${UI.esc(e.error_type || '')}</td>
          <td style="font-size:11px;max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
              title="${UI.esc(e.error || '')}">${UI.esc(e.error || '')}</td>
          <td style="font-size:11px;">${_fmtDate(e.created_at)}</td>
        </tr>`).join('');
      box.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:baseline;">
          <h3 style="margin:0;">${t('ops.errors.title')}</h3>
          ${rows ? `<button class="btn btn-ghost btn-sm" id="ops-errors-clear">${t('ops.errors.clear')}</button>` : ''}
        </div>
        ${rows ? `
        <div style="overflow-x:auto;margin-top:10px;">
          <table class="table">
            <thead><tr>
              <th>Request ID</th><th>${t('ops.errors.endpoint')}</th><th>${t('ops.errors.type')}</th>
              <th>${t('ops.errors.detail')}</th><th>${t('ops.errors.when')}</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>` : `<p class="text-muted" style="margin-top:10px;">${t('ops.errors.empty')}</p>`}
      `;
      const clear = document.getElementById('ops-errors-clear');
      if (clear) clear.onclick = async () => {
        if (!confirm(t('ops.errors.confirm_clear'))) return;
        try { await Api.del('/api/admin/errors'); _loadErrors(); }
        catch (e) { UI.toast(e.message, 'error'); }
      };
    } catch (e) {
      box.innerHTML = `<h3 style="margin-top:0;">${t('ops.errors.title')}</h3><div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  // ---------- Backups (superadmin) ----------

  async function _loadBackups() {
    const box = document.getElementById('ops-backups');
    if (!box) return;
    try {
      const d = await Api.get('/api/admin/backups');
      const rows = (d.backups || []).map(b => `
        <tr>
          <td style="font-family:monospace;font-size:12px;">${UI.esc(b.filename)}</td>
          <td style="text-align:right;">${_fmtBytes(b.size_bytes)}</td>
          <td style="font-size:11px;">${_fmtDate(b.created_at)}</td>
          <td><button class="btn btn-ghost btn-sm" data-download="${UI.esc(b.filename)}">${t('ops.backups.download')}</button></td>
        </tr>`).join('');
      box.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;">
          <h3 style="margin:0;">${t('ops.backups.title')}</h3>
          <button class="btn btn-primary btn-sm" id="ops-backup-run">${t('ops.backups.run_now')}</button>
        </div>
        <p style="font-size:11px;color:var(--text-subtle);margin:6px 0 0;">${t('ops.backups.hint')}</p>
        ${rows ? `
        <div style="overflow-x:auto;margin-top:10px;">
          <table class="table">
            <thead><tr>
              <th>${t('ops.backups.file')}</th><th style="text-align:right;">${t('ops.backups.size')}</th>
              <th>${t('ops.backups.date')}</th><th></th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>` : `<p class="text-muted" style="margin-top:10px;">${t('ops.backups.empty')}</p>`}
      `;
      const run = document.getElementById('ops-backup-run');
      if (run) run.onclick = async () => {
        run.disabled = true;
        try { await Api.post('/api/admin/backups/run'); UI.toast(t('ops.backups.done'), 'success'); _loadBackups(); }
        catch (e) { UI.toast(e.message, 'error'); run.disabled = false; }
      };
      box.querySelectorAll('[data-download]').forEach(btn => {
        btn.onclick = async () => {
          try {
            const tok = localStorage.getItem('riskhub_token');
            const resp = await fetch(`/api/admin/backups/${encodeURIComponent(btn.dataset.download)}`, {
              headers: { Authorization: 'Bearer ' + tok },
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const blob = await resp.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = btn.dataset.download;
            a.click();
            URL.revokeObjectURL(a.href);
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) {
      box.innerHTML = `<h3 style="margin-top:0;">${t('ops.backups.title')}</h3><div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  // ---------- Vigilancia normativa: cola de validacion interna (superadmin) ----------

  const _RW_SEV_BADGE = {
    cosmetic: 'badge-muted', clarification: 'badge-muted',
    substantive: 'badge-warning', breaking: 'badge-danger',
  };
  const _RW_REVIEW_STATUSES = ['pending_internal_review', 'detected', 'validated'];

  async function _loadRegwatchQueue() {
    const box = document.getElementById('ops-regwatch');
    if (!box) return;
    try {
      const all = await Promise.all(_RW_REVIEW_STATUSES.map(s => Api.regwatch.adminEvents(s)));
      // 'validated' con severidad cosmetic/clarification se auto-publica solo
      // (sin impacto para el tenant, §5.5) y no necesita revision aqui.
      const rows = all.flat()
        .filter(e => e.status !== 'validated' || (e.severity !== 'cosmetic' && e.severity !== 'clarification'))
        .map(e => `
        <tr data-event="${e.id}">
          <td>${UI.esc(e.framework_code || '-')}</td>
          <td><span class="badge ${_RW_SEV_BADGE[e.severity] || 'badge-muted'}">${UI.esc(e.severity || '-')}</span></td>
          <td>${UI.esc(t('ops.regwatch.status_' + e.status))}</td>
          <td style="text-align:right;">${e.ai_confidence != null ? Math.round(e.ai_confidence * 100) + '%' : '-'}</td>
          <td style="font-size:12px;max-width:360px;">${UI.esc(e.summary_es || '')}</td>
          <td style="font-size:11px;">${_fmtDate(e.detected_at)}</td>
          <td>${e.raw_url ? `<a href="${UI.esc(e.raw_url)}" target="_blank" rel="noopener">↗</a>` : ''}</td>
          <td style="white-space:nowrap;">
            <button class="btn btn-primary btn-sm" data-rw-approve="${e.id}">${t('ops.regwatch.approve')}</button>
            <button class="btn btn-ghost btn-sm" data-rw-reject="${e.id}">${t('ops.regwatch.reject')}</button>
          </td>
        </tr>`).join('');
      box.innerHTML = `
        <h3 style="margin:0 0 4px;">${t('ops.regwatch.title')}</h3>
        <p style="font-size:11px;color:var(--text-subtle);margin:0 0 10px;">${t('ops.regwatch.hint')}</p>
        ${rows ? `
        <div style="overflow-x:auto;">
          <table class="table">
            <thead><tr>
              <th>${t('ops.regwatch.framework')}</th><th>${t('ops.regwatch.severity')}</th>
              <th>${t('common.status')}</th>
              <th style="text-align:right;">${t('ops.regwatch.confidence')}</th>
              <th>${t('ops.regwatch.summary')}</th><th>${t('ops.regwatch.detected')}</th>
              <th>${t('ops.regwatch.source')}</th><th></th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>` : `<p class="text-muted">${t('ops.regwatch.empty')}</p>`}
      `;
      box.querySelectorAll('[data-rw-approve]').forEach(btn => {
        btn.onclick = async () => {
          btn.disabled = true;
          try {
            await Api.regwatch.adminValidateEvent(btn.dataset.rwApprove);
            UI.toast(t('ops.regwatch.approved'), 'success');
            _loadRegwatchQueue();
          } catch (e) { UI.toast(e.message, 'error'); btn.disabled = false; }
        };
      });
      box.querySelectorAll('[data-rw-reject]').forEach(btn => {
        btn.onclick = () => _openRejectModal(btn.dataset.rwReject);
      });
    } catch (e) {
      box.innerHTML = `<h3 style="margin-top:0;">${t('ops.regwatch.title')}</h3><div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _openRejectModal(eventId) {
    UI.modal(t('ops.regwatch.reject'), `
      <p style="font-size:13px;">${t('ops.regwatch.reject_prompt')}</p>
      <textarea id="rw-reject-reason" rows="3" style="width:100%;" maxlength="500"></textarea>
    `, {
      actions: `<button class="btn" id="rw-reject-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="rw-reject-confirm">${t('ops.regwatch.reject')}</button>`,
    });
    document.getElementById('rw-reject-cancel').onclick = UI.closeModal;
    document.getElementById('rw-reject-confirm').onclick = async () => {
      const btn = document.getElementById('rw-reject-confirm');
      btn.disabled = true;
      const reason = document.getElementById('rw-reject-reason').value || '';
      try {
        await Api.regwatch.adminRejectEvent(eventId, reason);
        UI.toast(t('ops.regwatch.rejected'), 'info');
        UI.closeModal();
        _loadRegwatchQueue();
      } catch (e) { UI.toast(e.message, 'error'); btn.disabled = false; }
    };
  }

  return { render };
})();
