/* Vista Auditoria Interna — ISO 27001 cl. 9.2. */
const ViewAudits = (() => {

  function _getTypeLabels() {
    return {
      internal:        t('audits.type_internal'),
      external:        t('audits.type_external'),
      surveillance:    t('audits.type_surveillance'),
      recertification: t('audits.type_recertification'),
    };
  }

  function _getStatusLabels() {
    return {
      planned:     t('audits.status.planned'),
      in_progress: t('audits.status.in_progress'),
      completed:   t('audits.status.completed'),
      cancelled:   t('audits.status.cancelled'),
    };
  }

  const STATUS_COLORS = {
    planned: 'var(--brand-purple)', in_progress: 'var(--brand-orange)',
    completed: 'var(--risk-low)', cancelled: '#aaa',
  };

  function _getFindingTypeLabels() {
    return {
      major_nc:    t('audits.finding_type.major_nc'),
      minor_nc:    t('audits.finding_type.minor_nc'),
      observation: t('audits.finding_type.observation'),
      opportunity: t('audits.finding_type.opportunity'),
      conformity:  t('audits.finding_type.conformity'),
    };
  }

  const FINDING_TYPE_COLORS = {
    major_nc: 'var(--risk-critical)', minor_nc: 'var(--risk-high)',
    observation: 'var(--brand-orange)', opportunity: 'var(--brand-purple)',
    conformity: 'var(--risk-low)',
  };

  let _users = [];
  let _nonconformities = [];

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('audits.title')}</h1>
          <p class="page-sub">${t('audits.subtitle')}</p>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-ghost" id="btn-toggle-import" title="${t('audits.import_title')}">
            ${t('audits.btn_import')}
          </button>
          <button class="btn btn-primary" id="btn-new-aud">${t('audits.btn_new')}</button>
        </div>
      </div>

      <!-- Zona de importacion colapsable -->
      <div id="import-panel" style="display:none;margin-bottom:20px;">
        <div style="border:2px dashed var(--brand-purple);border-radius:12px;padding:24px;
                    background:var(--bg-2);text-align:center;cursor:pointer;transition:all .2s;"
             id="import-zone">
          <div style="font-size:30px;line-height:1;margin-bottom:8px;color:var(--brand-purple);">&#x2B06;</div>
          <p style="font-size:15px;font-weight:700;margin:0 0 4px;color:var(--fg);">
            ${t('audits.import_title')}
          </p>
          <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;">
            ${t('audits.import_hint')}
          </p>
          <input type="file" id="import-file-input" accept=".pdf,.txt,.docx" style="display:none;">
          <button class="btn btn-primary" id="import-browse-btn" style="pointer-events:none;">
            ${t('audits.btn_select_file')}
          </button>
          <div id="import-file-label" style="margin-top:8px;font-size:13px;color:var(--brand-purple);
               font-weight:600;min-height:18px;"></div>
        </div>
        <div id="import-progress" style="display:none;background:var(--bg-2);border-radius:10px;
             padding:16px 20px;margin-top:12px;border:1px solid var(--border);">
          <div style="display:flex;align-items:center;gap:14px;">
            <div style="width:20px;height:20px;border:3px solid var(--brand-purple);
                        border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;
                        flex-shrink:0;"></div>
            <div>
              <div style="font-size:14px;font-weight:600;">${t('audits.import_analyzing')}</div>
              <div style="font-size:12px;color:var(--text-muted);margin-top:2px;">
                ${t('audits.import_analyzing_sub')}
              </div>
            </div>
          </div>
        </div>
        <div id="import-result"></div>
      </div>

      <div class="stats-row" id="aud-stats" style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px;"></div>

      <div id="aud-list"></div>
    `;

    document.getElementById('btn-new-aud').onclick = () => _openAuditForm(null);
    document.getElementById('btn-toggle-import').onclick = () => {
      const panel = document.getElementById('import-panel');
      const btn = document.getElementById('btn-toggle-import');
      const visible = panel.style.display !== 'none';
      panel.style.display = visible ? 'none' : 'block';
      btn.classList.toggle('btn-primary', !visible);
      btn.classList.toggle('btn-ghost', visible);
    };
    _initImportZone(el);

    try {
      [_users, _nonconformities] = await Promise.all([
        Api.listUsers().catch(() => []),
        Api.nonconformities.list({}).catch(() => []),
      ]);
    } catch (_) {}

    await _loadStats();
    await _refresh();
  }

  function _initImportZone(el) {
    const zone = el.querySelector('#import-zone');
    const fileInput = el.querySelector('#import-file-input');
    const fileLabel = el.querySelector('#import-file-label');

    function _selectFile(file) {
      if (!file) return;
      const ext = file.name.split('.').pop().toLowerCase();
      if (!['pdf', 'txt', 'docx'].includes(ext)) {
        UI.toast(t('audits.import_format_error'), 'error');
        return;
      }
      fileLabel.textContent = file.name + ' (' + (file.size / 1024).toFixed(0) + ' KB)';
      zone.style.borderColor = 'var(--brand-purple)';
      zone.style.background = 'var(--bg-1)';
      _runImportAnalysis(file);
    }

    zone.onclick = () => fileInput.click();
    fileInput.onchange = () => { if (fileInput.files[0]) _selectFile(fileInput.files[0]); };

    zone.ondragover = (e) => {
      e.preventDefault();
      zone.style.background = 'var(--bg-1)';
    };
    zone.ondragleave = () => {
      zone.style.background = 'var(--bg-2)';
    };
    zone.ondrop = (e) => {
      e.preventDefault();
      zone.style.background = 'var(--bg-2)';
      if (e.dataTransfer.files[0]) _selectFile(e.dataTransfer.files[0]);
    };
  }

  async function _runImportAnalysis(file) {
    const progressEl = document.getElementById('import-progress');
    const resultEl = document.getElementById('import-result');
    const zone = document.getElementById('import-zone');
    const fileLabel = document.getElementById('import-file-label');

    progressEl.style.display = 'block';
    resultEl.innerHTML = '';
    zone.style.pointerEvents = 'none';
    zone.style.opacity = '0.6';

    try {
      const today = new Date().toISOString().slice(0, 10);
      const newAudit = await Api.audits.create({
        title: `Informe analizado — ${file.name} (${today})`,
        audit_type: 'internal',
        status: 'completed',
        scope: t('audits.import_scope_default'),
      });
      const auditId = newAudit.id;

      const fd = new FormData();
      fd.append('file', file);
      const resp = await Api.req(`/api/audits/${auditId}/analyze-report`, {
        method: 'POST',
        body: fd,
      });

      _renderAnalysisResult(resultEl, resp, auditId);
      resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      await _loadStats();
      await _refresh();
    } catch (e) {
      resultEl.innerHTML = `
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;
                    padding:16px 20px;margin-bottom:16px;color:var(--risk-critical);">
          ${t('audits.toast_error_prefix')}${UI.esc(e.message)}
        </div>`;
    } finally {
      progressEl.style.display = 'none';
      zone.style.pointerEvents = '';
      zone.style.opacity = '';
      fileLabel.textContent = '';
      document.getElementById('import-file-input').value = '';
    }
  }

  async function _loadStats() {
    try {
      const s = await Api.audits.summary();
      const wrap = document.getElementById('aud-stats');
      if (!wrap) return;
      wrap.innerHTML = `
        <div class="stat-card" style="background:var(--bg-1);border:1px solid var(--border);border-radius:10px;padding:16px 20px;min-width:110px;">
          <div class="stat-value" style="font-size:28px;font-weight:700;">${s.total_programs}</div>
          <div class="stat-label" style="font-size:12px;color:var(--text-muted);">${t('audits.stat_audits')}</div>
        </div>
        <div class="stat-card" style="background:var(--bg-1);border:1px solid var(--border);border-radius:10px;padding:16px 20px;min-width:110px;">
          <div class="stat-value" style="font-size:28px;font-weight:700;color:var(--brand-orange);">${s.by_status.in_progress||0}</div>
          <div class="stat-label" style="font-size:12px;color:var(--text-muted);">${t('audits.stat_in_progress')}</div>
        </div>
        <div class="stat-card" style="background:var(--bg-1);border:1px solid var(--border);border-radius:10px;padding:16px 20px;min-width:110px;cursor:pointer;"
             title="${t('audits.stat_findings_hint')}"
             onclick="location.hash='#nonconformities'">
          <div class="stat-value" style="font-size:28px;font-weight:700;">${s.total_findings}</div>
          <div class="stat-label" style="font-size:12px;color:var(--text-muted);">${t('audits.stat_findings')} &#x2192;</div>
        </div>
        <div class="stat-card" style="background:var(--bg-1);border:1px solid var(--border);border-radius:10px;padding:16px 20px;min-width:110px;cursor:pointer;"
             title="${t('audits.stat_open_major_nc_hint')}"
             onclick="location.hash='#nonconformities'">
          <div class="stat-value" style="font-size:28px;font-weight:700;color:var(--risk-critical);">${s.open_major_ncs}</div>
          <div class="stat-label" style="font-size:12px;color:var(--text-muted);">${t('audits.stat_open_major_nc')} &#x2192;</div>
        </div>
      `;
      wrap.style.display = 'flex';
      wrap.style.gap = '12px';
      wrap.style.flexWrap = 'wrap';
    } catch (_) {}
  }

  async function _refresh() {
    const list = document.getElementById('aud-list');
    if (!list) return;
    list.innerHTML = `<p class="text-muted">${t('audits.loading')}</p>`;
    try {
      const data = await Api.audits.list({});
      if (!data.length) {
        list.innerHTML = `<p class="text-muted" style="margin-top:24px;text-align:center;">${t('audits.empty')}</p>`;
        return;
      }
      list.innerHTML = `
        <div style="display:flex;flex-direction:column;gap:12px;">
          ${data.map(a => _auditCard(a)).join('')}
        </div>`;
      list.querySelectorAll('[data-aud-id]').forEach(card => {
        card.onclick = () => _openAuditDetail(parseInt(card.dataset.audId));
      });
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _auditCard(a) {
    const AUDIT_TYPE_LABELS = _getTypeLabels();
    const STATUS_LABELS = _getStatusLabels();
    const ncMajor = (a.findings||[]).filter(f => f.finding_type === 'major_nc').length;
    const ncMinor = (a.findings||[]).filter(f => f.finding_type === 'minor_nc').length;
    const obs = (a.findings||[]).filter(f => f.finding_type === 'observation').length;
    return `
      <div data-aud-id="${a.id}" style="background:var(--bg-1);border:1px solid var(--border);border-radius:10px;padding:16px 20px;cursor:pointer;transition:box-shadow .15s;"
           onmouseover="this.style.boxShadow='0 2px 12px rgba(0,0,0,.1)'" onmouseout="this.style.boxShadow='none'">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
          <div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
              ${UI.codePill(a.code)}
              ${_badge(AUDIT_TYPE_LABELS[a.audit_type]||a.audit_type, 'var(--brand-purple)')}
              ${_badge(STATUS_LABELS[a.status]||a.status, STATUS_COLORS[a.status]||'#888')}
            </div>
            <div style="font-weight:600;font-size:15px;">${UI.esc(a.title)}</div>
            ${a.auditor_lead ? `<div style="font-size:12px;color:var(--text-muted);margin-top:3px;">${t('audits.card_lead')} ${UI.esc(a.auditor_lead)}</div>` : ''}
          </div>
          <div style="text-align:right;font-size:12px;color:var(--text-muted);white-space:nowrap;">
            ${a.planned_start ? `<div>${t('audits.card_start')} ${a.planned_start.slice(0,10)}</div>` : ''}
            ${a.planned_end ? `<div>${t('audits.card_end')} ${a.planned_end.slice(0,10)}</div>` : ''}
          </div>
        </div>
        ${a.findings && a.findings.length ? `
          <div style="display:flex;gap:8px;margin-top:10px;">
            ${ncMajor ? `${_badge(t(ncMajor > 1 ? 'audits.nc_major_badge_plural' : 'audits.nc_major_badge', { count: ncMajor }), 'var(--risk-critical)')}` : ''}
            ${ncMinor ? `${_badge(t(ncMinor > 1 ? 'audits.nc_minor_badge_plural' : 'audits.nc_minor_badge', { count: ncMinor }), 'var(--risk-high)')}` : ''}
            ${obs ? `${_badge(t(obs > 1 ? 'audits.obs_badge_plural' : 'audits.obs_badge', { count: obs }), 'var(--brand-orange)')}` : ''}
          </div>` : ''}
      </div>`;
  }

  async function _openAuditDetail(id) {
    const AUDIT_TYPE_LABELS = _getTypeLabels();
    const STATUS_LABELS = _getStatusLabels();
    const FINDING_TYPE_LABELS = _getFindingTypeLabels();
    const data = await Api.audits.get(id);
    UI.modal(`${data.code} — ${data.title}`, `
      <div style="display:flex;flex-direction:column;gap:12px;">
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          ${_badge(AUDIT_TYPE_LABELS[data.audit_type]||data.audit_type, 'var(--brand-purple)')}
          ${_badge(STATUS_LABELS[data.status]||data.status, STATUS_COLORS[data.status]||'#888')}
        </div>
        ${data.scope ? `<div><strong>${t('audits.detail_scope')}</strong><br><span style="font-size:13px;">${UI.esc(data.scope)}</span></div>` : ''}
        ${data.objectives ? `<div><strong>${t('audits.detail_objectives')}</strong><br><span style="font-size:13px;">${UI.esc(data.objectives)}</span></div>` : ''}
        ${data.criteria ? `<div><strong>${t('audits.detail_criteria')}</strong><br><span style="font-size:13px;">${UI.esc(data.criteria)}</span></div>` : ''}
        <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:13px;">
          ${data.auditor_lead ? `<div><strong>${t('audits.detail_lead')}</strong> ${UI.esc(data.auditor_lead)}</div>` : ''}
          ${data.auditee ? `<div><strong>${t('audits.detail_auditee')}</strong> ${UI.esc(data.auditee)}</div>` : ''}
          ${data.auditor_team && data.auditor_team.length ? `<div><strong>${t('audits.detail_team')}</strong> ${UI.esc(Array.isArray(data.auditor_team)?data.auditor_team.join(', '):data.auditor_team)}</div>` : ''}
        </div>
        <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:13px;">
          ${data.planned_start ? `<div><strong>${t('audits.detail_planned_start')}</strong> ${data.planned_start.slice(0,10)}</div>` : ''}
          ${data.planned_end ? `<div><strong>${t('audits.detail_planned_end')}</strong> ${data.planned_end.slice(0,10)}</div>` : ''}
          ${data.actual_start ? `<div><strong>${t('audits.detail_actual_start')}</strong> ${data.actual_start.slice(0,10)}</div>` : ''}
          ${data.actual_end ? `<div><strong>${t('audits.detail_actual_end')}</strong> ${data.actual_end.slice(0,10)}</div>` : ''}
        </div>
        ${data.conclusion ? `<div style="background:var(--bg-2);border-radius:6px;padding:10px;"><strong>${t('audits.detail_conclusion')}</strong><br><span style="font-size:13px;">${UI.esc(data.conclusion)}</span></div>` : ''}

        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <strong>${t('audits.detail_findings_count', { count: (data.findings||[]).length })}</strong>
            ${Auth.canEdit() ? `<button class="btn btn-sm btn-primary" id="btn-add-finding">${t('audits.btn_add_finding')}</button>` : ''}
          </div>
          <div id="findings-list">
            ${(data.findings||[]).length ? (data.findings||[]).map(f => _findingCardHtml(f, FINDING_TYPE_LABELS, FINDING_TYPE_COLORS)).join('')
            : `<p style="font-size:13px;color:var(--text-muted);">${t('audits.detail_no_findings')}</p>`}
          </div>
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="m-close-det">${t('audits.btn_close')}</button>
                ${Auth.canEdit() ? `<button class="btn btn-ghost" id="m-edit-aud">${t('audits.btn_edit')}</button>` : ''}
                ${Auth.canEdit() ? `<button class="btn btn-danger" id="m-del-aud">${t('audits.btn_delete')}</button>` : ''}`
    });

    document.getElementById('m-close-det').onclick = UI.closeModal;

    if (Auth.canEdit()) {
      document.getElementById('m-edit-aud').onclick = () => { UI.closeModal(); _openAuditForm(data); };
      document.getElementById('m-del-aud').onclick = async () => {
        if (!await UI.confirm(t('audits.delete_confirm'))) return;
        try {
          await Api.audits.del(data.id);
          UI.toast(t('audits.audit_toast_deleted'), 'success');
          UI.closeModal(); await _loadStats(); await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };

      const btnAddFinding = document.getElementById('btn-add-finding');
      if (btnAddFinding) btnAddFinding.onclick = () => _openFindingForm(data.id);

      document.querySelectorAll('[data-edit-finding]').forEach(btn => {
        btn.onclick = (e) => {
          e.stopPropagation();
          const fid = parseInt(btn.dataset.editFinding);
          const f = (data.findings||[]).find(x => x.id === fid);
          if (f) { UI.closeModal(); _openFindingDetail(data.id, f); }
        };
      });

      document.querySelectorAll('[data-del-finding]').forEach(btn => {
        btn.onclick = async (e) => {
          e.stopPropagation();
          if (!await UI.confirm(t('audits.finding_delete_confirm'))) return;
          try {
            await Api.audits.delFinding(data.id, btn.dataset.delFinding);
            UI.toast(t('audits.finding_toast_deleted'), 'success');
            UI.closeModal(); _openAuditDetail(data.id);
          } catch (e2) { UI.toast(e2.message, 'error'); }
        };
      });
    }
  }

  const FINDING_STATUS_COLORS = {
    open: 'var(--risk-critical)',
    in_progress: 'var(--brand-orange)',
    closed: '#aaa',
    verified: 'var(--risk-low)',
  };

  function _findingStatusLabel(s) {
    return t('audits.finding_status_' + (s||'open'));
  }

  function _findingCardHtml(f, typeLabels, typeColors) {
    const statusColor = FINDING_STATUS_COLORS[f.status] || '#aaa';
    return `
      <div style="padding:10px 14px;border:1px solid var(--border);border-radius:8px;margin-bottom:8px;background:var(--bg-2);">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap;">
          <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            ${_badge(typeLabels[f.finding_type]||f.finding_type, typeColors[f.finding_type]||'#888')}
            ${_badge(_findingStatusLabel(f.status), statusColor)}
            ${f.iso_clause ? `<span style="font-size:11px;font-family:var(--font-mono);color:var(--text-muted);">${UI.esc(f.iso_clause)}</span>` : ''}
          </div>
          <div style="display:flex;gap:6px;">
            ${Auth.canEdit() ? `<button class="btn btn-sm btn-ghost" data-edit-finding="${f.id}" onclick="event.stopPropagation()">${t('audits.btn_edit')}</button>` : ''}
            ${Auth.canEdit() ? `<button class="btn btn-sm btn-danger" data-del-finding="${f.id}" onclick="event.stopPropagation()">${t('audits.btn_delete')}</button>` : ''}
          </div>
        </div>
        <div style="font-weight:600;font-size:13px;margin-top:6px;">${UI.esc(f.title)}</div>
        ${f.description ? `<div style="font-size:12px;color:var(--text-muted);margin-top:2px;">${UI.esc(f.description)}</div>` : ''}
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:6px;font-size:12px;color:var(--text-muted);">
          ${f.deadline ? `<span>${t('audits.finding_deadline')} ${f.deadline.slice(0,10)}</span>` : ''}
          ${f.action_plan ? `<span style="color:var(--brand-purple);">${t('audits.finding_action_plan_short')}</span>` : ''}
          ${(f.comments||[]).length ? `<span>${t('audits.finding_comments_count', {count:(f.comments||[]).length})}</span>` : ''}
        </div>
      </div>`;
  }

  async function _openFindingDetail(auditId, f) {
    const FINDING_TYPE_LABELS = _getFindingTypeLabels();
    const statusColor = FINDING_STATUS_COLORS[f.status] || '#aaa';
    const statusOpts = ['open','in_progress','closed','verified'].map(s =>
      `<option value="${s}" ${f.status===s?'selected':''}>${_findingStatusLabel(s)}</option>`
    ).join('');
    UI.modal(`${t('audits.finding_detail_title')} — ${UI.esc(f.title)}`, `
      <div style="display:flex;flex-direction:column;gap:14px;">
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
          ${_badge(FINDING_TYPE_LABELS[f.finding_type]||f.finding_type, FINDING_TYPE_COLORS[f.finding_type]||'#888')}
          ${_badge(_findingStatusLabel(f.status), statusColor)}
          ${f.iso_clause ? `<code style="font-size:12px;color:var(--text-muted);">${UI.esc(f.iso_clause)}</code>` : ''}
        </div>
        ${f.description ? `<div><strong>${t('audits.finding_desc_label')}</strong><br><span style="font-size:13px;">${UI.esc(f.description)}</span></div>` : ''}
        ${f.recommendation ? `<div style="background:var(--bg-2);border-radius:6px;padding:10px;"><strong>${t('audits.finding_rec_label')}</strong><br><span style="font-size:13px;">${UI.esc(f.recommendation)}</span></div>` : ''}
        ${f.action_plan ? `<div><strong>${t('audits.finding_action_plan')}</strong><br><span style="font-size:13px;">${UI.esc(f.action_plan)}</span></div>` : ''}
        <div style="display:flex;gap:16px;font-size:13px;flex-wrap:wrap;">
          ${f.deadline ? `<div><strong>${t('audits.finding_deadline')}</strong> ${f.deadline.slice(0,10)}</div>` : ''}
          ${f.closed_at ? `<div><strong>${t('audits.finding_closed_at')}</strong> ${f.closed_at.slice(0,10)}</div>` : ''}
        </div>
        ${f.resolution_evidence ? `<div><strong>${t('audits.finding_resolution_evidence')}</strong><br><span style="font-size:13px;">${UI.esc(f.resolution_evidence)}</span></div>` : ''}

        ${Auth.canEdit() ? `
        <div style="border-top:1px solid var(--border);padding-top:12px;">
          <label style="font-weight:600;font-size:13px;display:block;margin-bottom:6px;">${t('audits.finding_change_status')}</label>
          <div style="display:flex;gap:8px;align-items:center;">
            <select id="fd-status" class="input" style="max-width:200px;">${statusOpts}</select>
            <button class="btn btn-sm btn-primary" id="fd-save-status">${t('audits.btn_save')}</button>
          </div>
        </div>` : ''}

        <div style="border-top:1px solid var(--border);padding-top:12px;">
          <strong style="font-size:13px;">${t('audits.finding_comments_title')} (${(f.comments||[]).length})</strong>
          <div id="fd-comments" style="margin-top:8px;display:flex;flex-direction:column;gap:6px;">
            ${(f.comments||[]).map(c => `
              <div style="background:var(--bg-2);border-radius:6px;padding:8px 10px;font-size:13px;">
                <div style="font-weight:600;font-size:11px;color:var(--text-muted);margin-bottom:3px;">${UI.esc(c.author)} · ${c.created_at ? c.created_at.slice(0,10) : ''}</div>
                ${UI.esc(c.text)}
              </div>`).join('') || `<p style="font-size:12px;color:var(--text-muted);">${t('audits.finding_no_comments')}</p>`}
          </div>
          ${Auth.canEdit() ? `
          <div style="display:flex;gap:8px;margin-top:10px;">
            <input id="fd-new-comment" class="input" placeholder="${t('audits.finding_comment_placeholder')}" style="flex:1;">
            <button class="btn btn-sm btn-primary" id="fd-add-comment">${t('audits.btn_comment')}</button>
          </div>` : ''}
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="fd-close">${t('audits.btn_close')}</button>
                ${Auth.canEdit() ? `<button class="btn btn-ghost" id="fd-edit">${t('audits.btn_edit')}</button>` : ''}`
    });

    document.getElementById('fd-close').onclick = () => { UI.closeModal(); _openAuditDetail(auditId); };
    if (Auth.canEdit()) {
      document.getElementById('fd-edit').onclick = () => { UI.closeModal(); _openFindingForm(auditId, f); };

      const saveStatusBtn = document.getElementById('fd-save-status');
      if (saveStatusBtn) saveStatusBtn.onclick = async () => {
        const newStatus = document.getElementById('fd-status').value;
        try {
          const updated = await Api.audits.updateFinding(auditId, f.id, { ...f, status: newStatus });
          UI.toast(t('audits.finding_status_updated'), 'success');
          UI.closeModal(); _openAuditDetail(auditId);
        } catch (e) { UI.toast(e.message, 'error'); }
      };

      const addCommentBtn = document.getElementById('fd-add-comment');
      if (addCommentBtn) addCommentBtn.onclick = async () => {
        const text = document.getElementById('fd-new-comment').value.trim();
        if (!text) return;
        try {
          const updated = await Api.audits.addComment(auditId, f.id, text);
          UI.toast(t('audits.finding_comment_added'), 'success');
          UI.closeModal(); _openFindingDetail(auditId, updated);
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    }
  }

  function _openFindingForm(auditId, existing) {
    const FINDING_TYPE_LABELS = _getFindingTypeLabels();
    const v = existing || {};
    const statusOpts = ['open','in_progress','closed','verified'].map(s =>
      `<option value="${s}" ${(v.status||'open')===s?'selected':''}>${_findingStatusLabel(s)}</option>`
    ).join('');
    const isEdit = !!existing;
    UI.modal(isEdit ? t('audits.edit_finding') : t('audits.new_finding'), `
      <div class="form-grid">
        <div>
          <label>${t('audits.finding_type_label')}</label>
          <select id="ff-type" class="input">
            ${Object.entries(FINDING_TYPE_LABELS).map(([k,l]) => `<option value="${k}" ${(v.finding_type||'minor_nc')===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div>
          <label>${t('audits.finding_status_label')}</label>
          <select id="ff-status" class="input">${statusOpts}</select>
        </div>
        <div class="span2"><label>${t('audits.finding_title_label')}</label><input id="ff-title" class="input" placeholder="${t('audits.finding_title_placeholder')}" value="${UI.esc(v.title||'')}"></div>
        <div><label>${t('audits.finding_clause_label')}</label><input id="ff-clause" class="input" placeholder="${t('audits.finding_clause_placeholder')}" value="${UI.esc(v.iso_clause||'')}"></div>
        <div>
          <label>${t('audits.finding_nc_label')}</label>
          <select id="ff-nc" class="input">
            <option value="">${t('audits.finding_nc_none')}</option>
            ${_nonconformities.map(nc => `<option value="${nc.id}" ${v.nonconformity_id===nc.id?'selected':''}>${UI.esc(nc.code)} — ${UI.esc(nc.title)}</option>`).join('')}
          </select>
        </div>
        <div><label>${t('audits.finding_responsible_label')}</label>
          <select id="ff-resp" class="input">
            <option value="">${t('audits.field_owner_none')}</option>
            ${_users.map(u => `<option value="${u.id}" ${v.responsible_id===u.id?'selected':''}>${UI.esc(u.full_name||u.email)}</option>`).join('')}
          </select>
        </div>
        <div><label>${t('audits.finding_deadline_label')}</label><input type="date" id="ff-deadline" class="input" value="${v.deadline?v.deadline.slice(0,10):''}"></div>
        <div class="span2"><label>${t('audits.finding_desc_label')}</label><textarea id="ff-desc" class="input" rows="3">${UI.esc(v.description||'')}</textarea></div>
        <div class="span2"><label>${t('audits.finding_rec_label')}</label><textarea id="ff-rec" class="input" rows="2">${UI.esc(v.recommendation||'')}</textarea></div>
        <div class="span2"><label>${t('audits.finding_action_plan')}</label><textarea id="ff-plan" class="input" rows="2">${UI.esc(v.action_plan||'')}</textarea></div>
        <div class="span2"><label>${t('audits.finding_resolution_evidence')}</label><textarea id="ff-res-ev" class="input" rows="2">${UI.esc(v.resolution_evidence||'')}</textarea></div>
      </div>
    `, {
      actions: `<button class="btn" id="mf-cancel">${t('audits.btn_cancel')}</button>
                <button class="btn btn-primary" id="mf-save">${t('audits.btn_save_finding')}</button>`
    });
    document.getElementById('mf-cancel').onclick = () => {
      UI.closeModal();
      if (isEdit) _openFindingDetail(auditId, existing);
      else _openAuditDetail(auditId);
    };
    document.getElementById('mf-save').onclick = async () => {
      const title = document.getElementById('ff-title').value.trim();
      if (!title) { UI.toast(t('audits.finding_title_required'), 'error'); return; }
      const ncVal = document.getElementById('ff-nc').value;
      const respVal = document.getElementById('ff-resp').value;
      const payload = {
        finding_type: document.getElementById('ff-type').value,
        status: document.getElementById('ff-status').value,
        title,
        description: document.getElementById('ff-desc').value.trim(),
        evidence: v.evidence || '',
        iso_clause: document.getElementById('ff-clause').value.trim() || null,
        recommendation: document.getElementById('ff-rec').value.trim(),
        nonconformity_id: ncVal ? parseInt(ncVal) : null,
        responsible_id: respVal ? parseInt(respVal) : null,
        deadline: document.getElementById('ff-deadline').value || null,
        action_plan: document.getElementById('ff-plan').value.trim() || null,
        resolution_evidence: document.getElementById('ff-res-ev').value.trim() || null,
      };
      try {
        if (isEdit) {
          await Api.audits.updateFinding(auditId, existing.id, payload);
          UI.toast(t('audits.finding_toast_updated'), 'success');
        } else {
          await Api.audits.createFinding(auditId, payload);
          UI.toast(t('audits.finding_toast_saved'), 'success');
        }
        UI.closeModal();
        await _loadStats(); await _refresh();
        _openAuditDetail(auditId);
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  function _auditFormHtml(a) {
    const AUDIT_TYPE_LABELS = _getTypeLabels();
    const STATUS_LABELS = _getStatusLabels();
    const v = a || {};
    return `
      <div class="form-grid">
        <div class="span2"><label>${t('audits.field_title')}</label><input id="fa-title" class="input" value="${UI.esc(v.title||'')}"></div>
        <div>
          <label>${t('audits.field_type')}</label>
          <select id="fa-type" class="input">
            ${Object.entries(AUDIT_TYPE_LABELS).map(([k,l]) => `<option value="${k}" ${(v.audit_type||'internal')===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div>
          <label>${t('audits.field_status')}</label>
          <select id="fa-status" class="input">
            ${Object.entries(STATUS_LABELS).map(([k,l]) => `<option value="${k}" ${(v.status||'planned')===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div><label>${t('audits.field_lead')}</label><input id="fa-lead" class="input" value="${UI.esc(v.auditor_lead||'')}"></div>
        <div><label>${t('audits.field_auditee')}</label><input id="fa-auditee" class="input" placeholder="${t('audits.field_auditee_placeholder')}" value="${UI.esc(v.auditee||'')}"></div>
        <div class="span2"><label>${t('audits.field_team')}</label><input id="fa-team" class="input" placeholder="${t('audits.field_team_placeholder')}" value="${UI.esc(Array.isArray(v.auditor_team)?v.auditor_team.join(', '):(v.auditor_team||''))}"></div>
        <div class="span2">
          <label>${t('audits.field_owner')}</label>
          <select id="fa-owner" class="input" style="max-width:320px;">
            <option value="">${t('audits.field_owner_none')}</option>
            ${_users.map(u => `<option value="${u.id}" ${v.owner_id===u.id?'selected':''}>${UI.esc(u.full_name||u.email)}</option>`).join('')}
          </select>
        </div>
        <div><label>${t('audits.field_start')}</label><input type="date" id="fa-start" class="input" value="${v.planned_start?v.planned_start.slice(0,10):''}"></div>
        <div><label>${t('audits.field_end')}</label><input type="date" id="fa-end" class="input" value="${v.planned_end?v.planned_end.slice(0,10):''}"></div>
        <div><label>${t('audits.field_actual_start')}</label><input type="date" id="fa-actual-start" class="input" value="${v.actual_start?v.actual_start.slice(0,10):''}"></div>
        <div><label>${t('audits.field_actual_end')}</label><input type="date" id="fa-actual-end" class="input" value="${v.actual_end?v.actual_end.slice(0,10):''}"></div>
        <div class="span2"><label>${t('audits.audit_scope')}</label><textarea id="fa-scope" class="input" rows="2">${UI.esc(v.scope||'')}</textarea></div>
        <div class="span2"><label>${t('audits.field_objectives')}</label><textarea id="fa-obj" class="input" rows="2">${UI.esc(v.objectives||'')}</textarea></div>
        <div class="span2"><label>${t('audits.field_criteria')}</label><textarea id="fa-crit" class="input" rows="2">${UI.esc(v.criteria||'')}</textarea></div>
        <div class="span2"><label>${t('audits.field_conclusion')}</label><textarea id="fa-concl" class="input" rows="3">${UI.esc(v.conclusion||'')}</textarea></div>
      </div>`;
  }

  function _openAuditForm(a) {
    UI.modal(a ? `${t('audits.edit')} ${a.code}` : t('audits.new'), _auditFormHtml(a), {
      actions: `<button class="btn" id="ma-cancel">${t('audits.btn_cancel')}</button>
                <button class="btn btn-primary" id="ma-save">${t('audits.btn_save')}</button>`,
    });
    document.getElementById('ma-cancel').onclick = UI.closeModal;
    document.getElementById('ma-save').onclick = () => _saveAudit(a);
  }

  async function _saveAudit(a) {
    const title = document.getElementById('fa-title').value.trim();
    if (!title) { UI.toast(t('audits.audit_title_required'), 'error'); return; }
    const ownerVal = document.getElementById('fa-owner').value;
    const payload = {
      title,
      audit_type: document.getElementById('fa-type').value,
      status: document.getElementById('fa-status').value,
      auditor_lead: document.getElementById('fa-lead').value.trim() || null,
      auditee: document.getElementById('fa-auditee').value.trim() || null,
      auditor_team: document.getElementById('fa-team').value.trim() ? document.getElementById('fa-team').value.split(',').map(s => s.trim()).filter(Boolean) : [],
      owner_id: ownerVal ? parseInt(ownerVal) : null,
      planned_start: document.getElementById('fa-start').value || null,
      planned_end: document.getElementById('fa-end').value || null,
      actual_start: document.getElementById('fa-actual-start').value || null,
      actual_end: document.getElementById('fa-actual-end').value || null,
      scope: document.getElementById('fa-scope').value.trim(),
      objectives: document.getElementById('fa-obj').value.trim(),
      criteria: document.getElementById('fa-crit').value.trim(),
      conclusion: document.getElementById('fa-concl').value.trim(),
    };
    try {
      if (a) {
        await Api.audits.update(a.id, payload);
        UI.toast(t('audits.audit_toast_updated'), 'success');
      } else {
        await Api.audits.create(payload);
        UI.toast(t('audits.audit_toast_created'), 'success');
      }
      UI.closeModal();
      await _loadStats(); await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  function _defaultDeadline(days) {
    const d = new Date();
    d.setDate(d.getDate() + (parseInt(days) || 30));
    return d.toISOString().slice(0, 10);
  }

  function _openAnalyzeReportModal() {
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:700px;max-height:92vh;overflow-y:auto;">
      <div class="modal-header" style="position:sticky;top:0;background:var(--bg-0);z-index:1;border-bottom:1px solid var(--border);padding-bottom:12px;">
        <h2 style="margin:0;">${t('audits.import_modal_title')}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&times;</button>
      </div>
      <div class="modal-body" style="padding-top:16px;">

        <div style="background:var(--bg-2);border-radius:8px;padding:12px 16px;margin-bottom:20px;font-size:13px;">
          ${t('audits.import_modal_desc')}
        </div>

        <label style="font-weight:600;font-size:13px;">${t('audits.import_title')} *</label>
        <div id="ar-drop-zone" style="border:2px dashed var(--border);border-radius:10px;
             padding:36px 20px;text-align:center;cursor:pointer;transition:all .2s;
             margin:8px 0 20px;background:var(--bg-2);">
          <div style="font-size:40px;color:var(--text-muted);line-height:1;margin-bottom:10px;">&#x2B06;</div>
          <p style="margin:0 0 6px;font-size:15px;font-weight:600;color:var(--fg);">${t('audits.import_drop_text')}</p>
          <p style="margin:0 0 14px;font-size:12px;color:var(--text-muted);">${t('audits.import_drop_sub')}</p>
          <button type="button" class="btn btn-ghost" style="font-size:13px;" id="ar-browse-btn">${t('audits.btn_browse')}</button>
          <input type="file" id="ar-file" accept=".pdf,.txt,.docx" style="display:none;">
          <div id="ar-file-name" style="margin-top:12px;font-size:13px;color:var(--brand-purple);
               font-weight:600;display:none;padding:6px 12px;background:var(--bg-1);
               border-radius:6px;display:inline-block;"></div>
        </div>

        <details style="margin-bottom:20px;">
          <summary style="cursor:pointer;font-size:13px;color:var(--text-muted);font-weight:600;
                          list-style:none;display:flex;align-items:center;gap:6px;">
            <span id="ar-summary-arrow" style="transition:transform .2s;">&#9656;</span>
            ${t('audits.import_link_audit')}
          </summary>
          <div style="margin-top:10px;">
            <select id="ar-audit-sel" class="input">
              <option value="">${t('audits.import_no_link')}</option>
            </select>
            <p style="font-size:11px;color:var(--text-muted);margin:6px 0 0;">
              ${t('audits.import_no_link_hint')}
            </p>
          </div>
        </details>

        <div id="ar-result"></div>

        <div style="display:flex;gap:8px;align-items:center;">
          <button class="btn btn-primary" id="ar-btn-analyze" style="min-width:140px;">
            ${t('audits.btn_analyze')}
          </button>
          <button class="btn btn-ghost" onclick="this.closest('.modal-bg').remove()">${t('audits.btn_cancel')}</button>
          <span id="ar-progress" style="font-size:12px;color:var(--text-muted);display:none;">${t('audits.loading')}</span>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);

    const dropZone = document.getElementById('ar-drop-zone');
    const fileInput = document.getElementById('ar-file');
    const fileNameDiv = document.getElementById('ar-file-name');

    function _showFile(file) {
      if (!file) return;
      fileNameDiv.textContent = '✔ ' + file.name + ' (' + (file.size / 1024).toFixed(0) + ' KB)';
      fileNameDiv.style.display = 'inline-block';
      dropZone.style.borderColor = 'var(--brand-purple)';
      dropZone.style.background = 'var(--bg-1)';
    }

    document.getElementById('ar-browse-btn').onclick = (e) => { e.stopPropagation(); fileInput.click(); };
    dropZone.onclick = () => fileInput.click();
    fileInput.onchange = () => _showFile(fileInput.files[0]);

    dropZone.ondragover = (e) => {
      e.preventDefault();
      dropZone.style.borderColor = 'var(--brand-purple)';
      dropZone.style.background = 'var(--bg-1)';
    };
    dropZone.ondragleave = () => {
      if (!fileInput.files?.length) {
        dropZone.style.borderColor = 'var(--border)';
        dropZone.style.background = 'var(--bg-2)';
      }
    };
    dropZone.ondrop = (e) => {
      e.preventDefault();
      if (e.dataTransfer.files.length) {
        const dt = new DataTransfer();
        dt.items.add(e.dataTransfer.files[0]);
        fileInput.files = dt.files;
        _showFile(e.dataTransfer.files[0]);
      }
    };

    document.getElementById('ar-btn-analyze').onclick = () => _runAnalysis();

    Api.audits.list({}).then(list => {
      const sel = document.getElementById('ar-audit-sel');
      if (!sel || !list.length) return;
      sel.innerHTML = `<option value="">${t('audits.import_no_link')}</option>` +
        list.map(a => `<option value="${a.id}">${UI.esc(a.title || 'Audit ' + a.id)}</option>`).join('');
    }).catch(() => {});
  }

  async function _runAnalysis() {
    const btn = document.getElementById('ar-btn-analyze');
    const resultDiv = document.getElementById('ar-result');
    const fileInput = document.getElementById('ar-file');

    if (!fileInput?.files?.length) { UI.toast(t('audits.import_no_file'), 'error'); return; }

    const file = fileInput.files[0];
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'txt', 'docx'].includes(ext)) {
      UI.toast(t('audits.import_format_error2'), 'error'); return;
    }

    btn.disabled = true;
    btn.textContent = t('audits.loading');
    resultDiv.innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;padding:20px;
                  background:var(--bg-2);border-radius:8px;margin:16px 0;">
        <div style="width:20px;height:20px;border:3px solid var(--brand-purple);
                    border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;
                    flex-shrink:0;"></div>
        <div>
          <div style="font-size:13px;font-weight:600;">${t('audits.import_ai_progress')}</div>
          <div style="font-size:12px;color:var(--text-muted);margin-top:2px;">${t('audits.import_ai_progress_sub')}</div>
        </div>
      </div>`;

    try {
      let auditId = document.getElementById('ar-audit-sel')?.value || '';
      if (!auditId) {
        const today = new Date().toISOString().slice(0, 10);
        const newAudit = await Api.audits.create({
          title: `Analisis IA — ${file.name} (${today})`,
          audit_type: 'internal',
          status: 'completed',
          scope: 'Informe analizado automaticamente por el agente IA',
        });
        auditId = newAudit.id;
      }

      const fd = new FormData();
      fd.append('file', file);

      const resp = await Api.req(`/api/audits/${auditId}/analyze-report`, {
        method: 'POST',
        body: fd,
      });
      _renderAnalysisResult(resultDiv, resp, auditId);
    } catch (e) {
      resultDiv.innerHTML = `<div class="notice" style="margin:16px 0;">${UI.esc(e.message)}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = t('audits.btn_analyze');
    }
  }

  function _renderAnalysisResult(container, data, auditId) {
    const typeColors = {
      major_nc: '#DC2626', minor_nc: '#D97706', observation: '#2563EB',
      opportunity: '#7C3AED', conformity: '#16a34a',
    };
    const FINDING_TYPE_LABELS = _getFindingTypeLabels();
    const priorityColors = { high: '#DC2626', medium: '#D97706', low: '#16a34a' };

    const findings = data.findings || [];
    const isNc = (type) => type === 'major_nc' || type === 'minor_nc';
    const usersOpts = _users.map(u => `<option value="${u.id}">${UI.esc(u.full_name || u.email)}</option>`).join('');

    const findingsHtml = findings.map((f, idx) => `
      <div style="background:var(--bg-2);border-left:4px solid ${typeColors[f.type] || '#9D9D9D'};
                  border-radius:0 8px 8px 0;padding:14px;margin-bottom:10px;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:8px;">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <span style="background:${typeColors[f.type] || '#9D9D9D'};color:#fff;font-size:10px;font-weight:700;
                         padding:2px 8px;border-radius:4px;">${FINDING_TYPE_LABELS[f.type] || UI.esc(f.type)}</span>
            ${f.iso_clause ? `<span style="font-size:11px;color:var(--brand-purple);font-weight:600;">ISO ${UI.esc(f.iso_clause)}</span>` : ''}
            ${f.priority ? `<span style="color:${priorityColors[f.priority] || '#9D9D9D'};font-size:11px;font-weight:600;">${f.priority.toUpperCase()}</span>` : ''}
            ${isNc(f.type) ? `<span style="font-size:10px;color:var(--brand-orange);font-weight:600;">${t('audits.ai_auto_badge')}</span>` : ''}
          </div>
          <button class="btn btn-sm btn-primary" data-ar-idx="${idx}">
            ${t('audits.btn_create_finding')}
          </button>
        </div>
        <div style="margin-bottom:4px;">
          <input class="input" style="font-size:13px;font-weight:600;padding:4px 8px;width:100%;"
                 id="ar-title-${idx}" value="${UI.esc(f.title || '')}">
        </div>
        <div style="margin-bottom:6px;">
          <textarea class="input" rows="2" style="font-size:12px;padding:4px 8px;width:100%;"
                    id="ar-desc-${idx}">${UI.esc(f.description || '')}</textarea>
        </div>
        <div style="margin-bottom:8px;">
          <strong style="font-size:12px;">${t('audits.finding_rec_label')}:</strong>
          <textarea class="input" rows="2" style="font-size:12px;margin-top:4px;padding:4px 8px;width:100%;"
                    id="ar-rec-${idx}">${UI.esc(f.recommendation || '')}</textarea>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:8px;">
          <div>
            <label style="font-size:11px;font-weight:600;display:block;margin-bottom:2px;">${t('audits.ai_field_responsible')}</label>
            <select id="ar-resp-${idx}" class="input" style="font-size:12px;padding:4px 6px;">
              <option value="">${t('audits.ai_field_responsible_none')}</option>
              ${usersOpts}
            </select>
          </div>
          <div>
            <label style="font-size:11px;font-weight:600;display:block;margin-bottom:2px;">${t('audits.ai_field_deadline')}</label>
            <input type="date" id="ar-dead-${idx}" class="input" style="font-size:12px;padding:4px 6px;"
                   value="${_defaultDeadline(f.estimated_days)}">
          </div>
          <div>
            <label style="font-size:11px;font-weight:600;display:block;margin-bottom:2px;">${t('audits.ai_field_status')}</label>
            <select id="ar-status-${idx}" class="input" style="font-size:12px;padding:4px 6px;">
              <option value="open">${t('audits.ai_status_open')}</option>
              <option value="in_progress">${t('audits.ai_status_in_progress')}</option>
            </select>
          </div>
        </div>
        <div>
          <label style="font-size:11px;font-weight:600;display:block;margin-bottom:2px;">${t('audits.ai_field_evidence')}</label>
          <input type="file" id="ar-ev-${idx}" style="font-size:11px;" accept=".pdf,.docx,.xlsx,.jpg,.png,.txt">
        </div>
      </div>`).join('');

    container.innerHTML = `
      <hr style="border:none;border-top:1px solid var(--border);margin:0 0 16px;">
      ${data.summary ? `
        <div style="background:var(--bg-2);border-left:4px solid var(--brand-purple);
                    padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:16px;">
          <strong style="font-size:12px;color:var(--brand-purple);">${t('audits.import_ai_resume')}</strong>
          <p style="font-size:13px;margin:4px 0 0;">${UI.esc(data.summary)}</p>
          ${data.audit_scope ? `<p style="font-size:11px;color:var(--text-muted);margin:4px 0 0;">${t('audits.import_ai_scope')} ${UI.esc(data.audit_scope)}</p>` : ''}
        </div>` : ''}

      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
        ${data.total_major_nc ? `<div class="stat-card" style="min-width:100px;text-align:center;"><div class="stat-value" style="color:#DC2626;">${data.total_major_nc}</div><div class="stat-label">${t('audits.stat_major_nc')}</div></div>` : ''}
        ${data.total_minor_nc ? `<div class="stat-card" style="min-width:100px;text-align:center;"><div class="stat-value" style="color:#D97706;">${data.total_minor_nc}</div><div class="stat-label">${t('audits.stat_minor_nc')}</div></div>` : ''}
        ${data.total_observations ? `<div class="stat-card" style="min-width:100px;text-align:center;"><div class="stat-value" style="color:#2563EB;">${data.total_observations}</div><div class="stat-label">${t('audits.stat_observations')}</div></div>` : ''}
        ${data.total_opportunities ? `<div class="stat-card" style="min-width:100px;text-align:center;"><div class="stat-value" style="color:#7C3AED;">${data.total_opportunities}</div><div class="stat-label">${t('audits.stat_opportunities')}</div></div>` : ''}
      </div>

      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <h4 style="font-size:13px;font-weight:700;margin:0;">
          ${t('audits.import_findings_header', { count: findings.length })}
        </h4>
        ${findings.length ? `<button class="btn btn-ghost" style="font-size:11px;" id="ar-btn-create-all">
          ${t('audits.btn_create_all')}
        </button>` : ''}
      </div>
      ${findingsHtml}
    `;

    const btnAll = container.querySelector('#ar-btn-create-all');
    if (btnAll) {
      btnAll.onclick = () => _createAllFindings(auditId, findings);
    }

    container.querySelectorAll('[data-ar-idx]').forEach(btn => {
      btn.onclick = () => {
        const idx = parseInt(btn.dataset.arIdx);
        const evInput = document.getElementById(`ar-ev-${idx}`);
        const edited = {
          type: findings[idx].type,
          iso_clause: findings[idx].iso_clause,
          priority: findings[idx].priority,
          estimated_days: findings[idx].estimated_days,
          title: document.getElementById(`ar-title-${idx}`)?.value || findings[idx].title,
          description: document.getElementById(`ar-desc-${idx}`)?.value || findings[idx].description,
          recommendation: document.getElementById(`ar-rec-${idx}`)?.value || findings[idx].recommendation,
        };
        const opts = {
          responsible: document.getElementById(`ar-resp-${idx}`)?.value || null,
          deadline: document.getElementById(`ar-dead-${idx}`)?.value || null,
          status: document.getElementById(`ar-status-${idx}`)?.value || 'open',
          evidenceFile: evInput?.files?.length ? evInput.files[0] : null,
        };
        _createFindingFromAI(auditId, edited, opts);
      };
    });
  }

  async function _createFindingFromAI(auditId, finding, opts = {}) {
    const isNc = finding.type === 'major_nc' || finding.type === 'minor_nc';
    const ownerInt = opts.responsible ? parseInt(opts.responsible) : null;
    const dueDateIso = opts.deadline ? new Date(opts.deadline).toISOString() : null;

    try {
      await Api.post(`/api/audits/${auditId}/findings`, {
        finding_type: finding.type,
        title: finding.title,
        description: finding.description,
        iso_clause: finding.iso_clause || null,
        recommendation: finding.recommendation,
      });

      const created = [];

      let ncCreated = false;
      if (isNc) {
        try {
          await Api.nonconformities.create({
            title: finding.title,
            description: finding.description || null,
            source: 'auditoria',
            severity: finding.type === 'major_nc' ? 'major' : 'minor',
            iso_clause: finding.iso_clause || null,
            corrective_action: finding.recommendation || null,
            due_date: dueDateIso,
            owner_id: ownerInt,
          });
          ncCreated = true;
          created.push(t('audits.ai_created_nc', { count: 1 }));
        } catch (_) {}
      }

      if (isNc) {
        try {
          await Api.tasks.create({
            title: `[Auditoria] ${finding.title}`,
            description: finding.recommendation || finding.description || null,
            assigned_to_id: ownerInt,
            due_date: dueDateIso,
            priority: finding.type === 'major_nc' ? 'high' : 'medium',
            notes: `Generado desde analisis IA de auditoria #${auditId}`,
          });
          created.push(t('audits.ai_created_tasks', { count: 1 }));
        } catch (_) {}
      }

      if (opts.evidenceFile) {
        try {
          const fd = new FormData();
          fd.append('file', opts.evidenceFile);
          fd.append('title', `Evidencia: ${finding.title}`);
          fd.append('description', `Hallazgo de auditoria #${auditId}`);
          await Api.evidence.upload(fd);
        } catch (_) {}
      }

      const extra = created.length ? ` + ${created.join(' + ')}` : '';
      UI.toast(`${t('audits.ai_created_toast')}${extra}`, 'success');
      await _loadStats();
      await _refresh();
    } catch (e) {
      UI.toast(t('audits.toast_error_prefix') + e.message, 'error');
    }
  }

  async function _createAllFindings(auditId, findings) {
    let created = 0;
    let ncsCreated = 0;
    let tasksCreated = 0;
    for (let idx = 0; idx < findings.length; idx++) {
      const f = findings[idx];
      const isNc = f.type === 'major_nc' || f.type === 'minor_nc';
      const title = document.getElementById(`ar-title-${idx}`)?.value || f.title;
      const description = document.getElementById(`ar-desc-${idx}`)?.value || f.description;
      const recommendation = document.getElementById(`ar-rec-${idx}`)?.value || f.recommendation;
      const responsible = document.getElementById(`ar-resp-${idx}`)?.value || null;
      const deadline = document.getElementById(`ar-dead-${idx}`)?.value || null;
      const evInput = document.getElementById(`ar-ev-${idx}`);
      const evidenceFile = evInput?.files?.length ? evInput.files[0] : null;
      const ownerInt = responsible ? parseInt(responsible) : null;
      const dueDateIso = deadline ? new Date(deadline).toISOString() : null;

      try {
        await Api.post(`/api/audits/${auditId}/findings`, {
          finding_type: f.type,
          title,
          description: description || null,
          iso_clause: f.iso_clause || null,
          recommendation: recommendation || null,
        });
        created++;

        if (isNc) {
          try {
            await Api.nonconformities.create({
              title,
              description: description || null,
              source: 'auditoria',
              severity: f.type === 'major_nc' ? 'major' : 'minor',
              iso_clause: f.iso_clause || null,
              corrective_action: recommendation || null,
              due_date: dueDateIso,
              owner_id: ownerInt,
            });
            ncsCreated++;
          } catch (_) {}

          try {
            await Api.tasks.create({
              title: `[Auditoria] ${title}`,
              description: recommendation || description || null,
              assigned_to_id: ownerInt,
              due_date: dueDateIso,
              priority: f.type === 'major_nc' ? 'high' : 'medium',
              notes: `Generado desde analisis IA de auditoria #${auditId}`,
            });
            tasksCreated++;
          } catch (_) {}
        }

        if (evidenceFile) {
          try {
            const fd = new FormData();
            fd.append('file', evidenceFile);
            fd.append('title', `Evidencia: ${title}`);
            fd.append('description', `Hallazgo de auditoria #${auditId}`);
            await Api.evidence.upload(fd);
          } catch (_) {}
        }
      } catch (_) {}
    }
    const extra = [];
    if (ncsCreated) extra.push(t('audits.ai_created_nc', { count: ncsCreated }));
    if (tasksCreated) extra.push(t('audits.ai_created_tasks', { count: tasksCreated }));
    UI.toast(t('audits.ai_created_all_toast', { count: created }) + (extra.length ? ' + ' + extra.join(' + ') : ''), 'success');
    document.querySelector('.modal-bg')?.remove();
    await _loadStats();
    await _refresh();
  }

  return { render, _openAnalyzeReportModal, _runAnalysis, _runImportAnalysis, _renderAnalysisResult, _createFindingFromAI, _createAllFindings, _defaultDeadline };
})();
