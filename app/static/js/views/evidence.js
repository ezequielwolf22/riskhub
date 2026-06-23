/* Vista de gestión de evidencias centralizadas. */
const ViewEvidence = (() => {

  let _filters = { framework: '', requirement: '', expired_only: false };

  function _getTypeLabels() {
    return {
      policy: t('evidence.type.policy'), procedure: t('evidence.type.procedure'),
      record: t('evidence.type.record'), certificate: t('evidence.type.certificate'),
      screenshot: t('evidence.type.screenshot'), log: t('evidence.type.log'),
      report: t('evidence.type.report'), other: t('evidence.type.other'),
    };
  }

  function _typeLabel(type) {
    return _getTypeLabels()[type] || type;
  }

  function _typeBadge(type) {
    const colors = {
      certificate: '#E3F2FD:#1565c0', policy: '#E8EAF6:#283593',
      report: '#E8F5E9:#2e7d32', record: '#FFF8E1:#F57F17',
      screenshot: '#F3E5F5:#6A1B9A', log: '#FBE9E7:#BF360C',
    };
    const [bg, col] = (colors[type] || '#f0f0f0:#666').split(':');
    return `<span style="background:${bg};color:${col};padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">${_typeLabel(type)}</span>`;
  }

  function _expiryBadge(ev) {
    if (!ev.expires_at) return '';
    const days = Math.ceil((new Date(ev.expires_at) - new Date()) / 86400000);
    if (days < 0) return `<span style="background:#FEE2E2;color:#a83232;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">${t('evidence.expired_badge')}</span>`;
    if (days <= 30) return `<span style="background:#FEF0E3;color:#c25a1f;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">${t('evidence.expiring_badge', { days })}</span>`;
    return `<span style="background:#E8F5E9;color:#2e7d32;padding:2px 8px;border-radius:10px;font-size:11px;">${t('evidence.valid_badge')}</span>`;
  }

  function _uploadModal() {
    const labels = _getTypeLabels();
    UI.openModal(`
      <h3 style="margin:0 0 16px;color:var(--brand-purple);">${t('evidence.upload_title')}</h3>
      <div style="display:grid;gap:12px;">
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('evidence.title_label')}</label>
          <input id="ev-title" class="input-field" placeholder="${t('evidence.title_placeholder')}" style="width:100%;">
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('evidence.type_label')}</label>
          <select id="ev-type" class="input-field" style="width:100%;">
            ${Object.entries(labels).map(([k, v]) => `<option value="${k}">${v}</option>`).join('')}
          </select>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div>
            <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('evidence.framework_label')}</label>
            <input id="ev-fw" class="input-field" placeholder="iso27001, gdpr…" style="width:100%;">
          </div>
          <div>
            <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('evidence.requirement_label')}</label>
            <input id="ev-req" class="input-field" placeholder="A.5.1, Art.32…" style="width:100%;">
          </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div>
            <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('evidence.valid_from_label')}</label>
            <input id="ev-from" type="date" class="input-field" style="width:100%;">
          </div>
          <div>
            <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('evidence.expires_label')}</label>
            <input id="ev-expires" type="date" class="input-field" style="width:100%;">
          </div>
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('evidence.file_label')}</label>
          <input id="ev-file" type="file" style="width:100%;" accept="*/*">
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('evidence.description_label')}</label>
          <textarea id="ev-desc" class="input-field" rows="2" style="width:100%;"
                    placeholder="${t('evidence.description_placeholder')}"></textarea>
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;">
        <button onclick="UI.closeModal()" class="btn-outline">${t('evidence.cancel_btn')}</button>
        <button onclick="ViewEvidence._submitUpload()" class="btn-primary">${t('evidence.upload')}</button>
      </div>`);
  }

  async function _submitUpload() {
    const title = document.getElementById('ev-title').value.trim();
    const file = document.getElementById('ev-file').files[0];
    if (!title || !file) { UI.toast(t('evidence.required_fields'), 'error'); return; }

    const fd = new FormData();
    fd.append('file', file);
    fd.append('title', title);
    fd.append('evidence_type', document.getElementById('ev-type').value);
    const fw = document.getElementById('ev-fw').value.trim();
    const req = document.getElementById('ev-req').value.trim();
    const from = document.getElementById('ev-from').value;
    const expires = document.getElementById('ev-expires').value;
    const desc = document.getElementById('ev-desc').value.trim();
    if (fw) fd.append('compliance_framework', fw);
    if (req) fd.append('compliance_requirement', req);
    if (from) fd.append('valid_from', from);
    if (expires) fd.append('expires_at', expires);
    if (desc) fd.append('description', desc);

    try {
      await Api.evidence.upload(fd);
      UI.closeModal();
      UI.toast(t('evidence.upload_success'), 'success');
      _load();
    } catch (e) {
      UI.toast(t('evidence.upload_error', { msg: e.message }), 'error');
    }
  }

  async function _load() {
    const tbody = document.getElementById('ev-tbody');
    const total = document.getElementById('ev-total');
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:24px;color:#9d9d9d;">${t('evidence.loading')}</td></tr>`;

    try {
      const q = {};
      if (_filters.framework) q.framework = _filters.framework;
      if (_filters.requirement) q.requirement = _filters.requirement;
      if (_filters.expired_only) q.expired_only = true;

      const data = await Api.evidence.list(q);
      if (total) total.textContent = data.total;
      const items = data.items || [];

      if (!items.length) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px;color:#9d9d9d;">${t('evidence.no_evidence')}</td></tr>`;
        return;
      }

      tbody.innerHTML = items.map(ev => `
        <tr style="border-bottom:1px solid #f0f0f0;">
          <td style="padding:10px 12px;font-weight:600;color:var(--brand-purple);">${UI.esc(ev.code)}</td>
          <td style="padding:10px 12px;">
            <div style="font-weight:500;">${UI.esc(ev.title)}</div>
            ${ev.compliance_framework ? `<div style="font-size:11px;color:#9d9d9d;">${UI.esc(ev.compliance_framework)} / ${UI.esc(ev.compliance_requirement || '')}</div>` : ''}
          </td>
          <td style="padding:10px 12px;">${_typeBadge(ev.evidence_type)}</td>
          <td style="padding:10px 12px;font-size:12px;color:#666;">
            v${ev.version}
            ${!ev.is_current ? `<span style="color:#9d9d9d;"> ${t('evidence.old_version')}</span>` : ''}
          </td>
          <td style="padding:10px 12px;">${_expiryBadge(ev)}</td>
          <td style="padding:10px 12px;font-size:12px;color:#9d9d9d;">
            ${ev.created_at ? ev.created_at.slice(0, 10) : '—'}
          </td>
          <td style="padding:10px 12px;">
            <div style="display:flex;gap:6px;justify-content:flex-end;">
              ${ev.filename ? `<a href="${Api.evidence.download(ev.id)}" target="_blank"
                 style="font-size:12px;color:var(--brand-purple);text-decoration:none;
                        padding:3px 8px;border:1px solid var(--brand-purple);border-radius:4px;">
                ${t('evidence.download_btn')}</a>` : ''}
              <button onclick="ViewEvidence._del(${ev.id}, '${UI.esc(ev.code)}')"
                      style="font-size:12px;color:#a83232;background:none;border:1px solid #a83232;
                             border-radius:4px;padding:3px 8px;cursor:pointer;">${t('evidence.delete_btn')}</button>
            </div>
          </td>
        </tr>`).join('');
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="7" style="color:var(--risk-critical);padding:16px;">Error: ${UI.esc(e.message)}</td></tr>`;
    }
  }

  async function _del(id, code) {
    if (!await UI.confirm(t('evidence.delete_confirm', { code }))) return;
    try {
      await Api.evidence.del(id);
      UI.toast(t('evidence.deleted_toast'), 'success');
      _load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  function _applyFilters() {
    _filters.framework = document.getElementById('ev-filter-fw').value.trim();
    _filters.requirement = document.getElementById('ev-filter-req').value.trim();
    _filters.expired_only = document.getElementById('ev-filter-expired').checked;
    _load();
  }

  async function render(el) {
    el.innerHTML = `
      <div style="max-width:1100px;margin:0 auto;padding:24px 0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:12px;">
          <div>
            <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0;">
              ${t('evidence.title')}
            </h1>
            <p style="color:#9d9d9d;font-size:13px;margin:4px 0 0;">
              ${t('evidence.total_label')} <strong id="ev-total">—</strong>
            </p>
          </div>
          <button onclick="ViewEvidence._uploadModal()" class="btn-primary">
            ${t('evidence.upload_btn')}
          </button>
        </div>

        <!-- Filtros -->
        <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:16px;
                    margin-bottom:16px;display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;">
          <div>
            <label style="font-size:11px;color:#9d9d9d;display:block;margin-bottom:4px;">${t('evidence.filter_framework')}</label>
            <input id="ev-filter-fw" class="input-field" placeholder="iso27001, gdpr…"
                   style="width:130px;" value="${_filters.framework}">
          </div>
          <div>
            <label style="font-size:11px;color:#9d9d9d;display:block;margin-bottom:4px;">${t('evidence.filter_requirement')}</label>
            <input id="ev-filter-req" class="input-field" placeholder="A.5.1…"
                   style="width:110px;" value="${_filters.requirement}">
          </div>
          <div style="display:flex;align-items:center;gap:6px;padding-bottom:2px;">
            <input id="ev-filter-expired" type="checkbox" ${_filters.expired_only ? 'checked' : ''}>
            <label for="ev-filter-expired" style="font-size:13px;cursor:pointer;">${t('evidence.filter_expired_only')}</label>
          </div>
          <button onclick="ViewEvidence._applyFilters()" class="btn-primary" style="padding:6px 14px;">${t('evidence.filter_btn')}</button>
        </div>

        <!-- Tabla -->
        <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;overflow:hidden;">
          <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
              <tr style="background:var(--brand-purple);color:#fff;">
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('evidence.col_code')}</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('evidence.col_title')}</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('evidence.col_type')}</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('evidence.col_version')}</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('evidence.col_validity')}</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('evidence.col_date')}</th>
                <th style="padding:10px 12px;text-align:right;font-weight:600;">${t('evidence.col_actions')}</th>
              </tr>
            </thead>
            <tbody id="ev-tbody">
              <tr><td colspan="7" style="text-align:center;padding:24px;color:#9d9d9d;">${t('evidence.loading')}</td></tr>
            </tbody>
          </table>
        </div>
      </div>`;

    await _load();
  }

  return { render, _uploadModal, _submitUpload, _del, _applyFilters, _load };
})();
