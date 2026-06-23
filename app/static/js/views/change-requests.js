/* Change Management — ISO 27001 cl. 6.3 */
const ViewChangeRequests = (() => {

  function _getStatusLabels() {
    return {
      draft: t('change_requests.status.draft'),
      under_review: t('change_requests.status.under_review'),
      approved: t('change_requests.status.approved'),
      rejected: t('change_requests.status.rejected'),
      implemented: t('change_requests.status.implemented'),
      verified: t('change_requests.status.verified'),
    };
  }

  function _getTypeLabels() {
    return {
      policy: t('change_requests.type.policy'),
      control: t('change_requests.type.control'),
      asset: t('change_requests.type.asset'),
      process: t('change_requests.type.process'),
      infrastructure: t('change_requests.type.infrastructure'),
      other: t('change_requests.type.other'),
    };
  }

  const IMPACT_COLORS = { none: '#9D9D9D', low: '#16a34a', medium: '#D97706', high: '#DC2626' };

  let _wrap = null;

  async function render(container) {
    container.innerHTML = UI.sectionHeader(
      t('change_requests.title'),
      t('change_requests.subtitle'),
      `<button class="btn btn-primary" id="btn-new-chg">${t('change_requests.new_btn')}</button>`
    );
    _wrap = document.createElement('div');
    container.appendChild(_wrap);
    document.getElementById('btn-new-chg').addEventListener('click', () => _openForm(null));
    await _load();
  }

  async function _load() {
    if (!_wrap) return;
    _wrap.innerHTML = `<p class="text-muted" style="margin-top:24px;">${t('change_requests.loading')}</p>`;
    try {
      const changes = await Api.get('/api/change-requests');
      if (!changes.length) {
        _wrap.innerHTML = UI.emptyState(t('change_requests.empty_title'), t('change_requests.empty_body'));
        return;
      }
      const statusLabels = _getStatusLabels();
      const typeLabels = _getTypeLabels();
      const statuses = ['draft', 'under_review', 'approved', 'implemented', 'verified'];
      const byStatus = {};
      statuses.concat(['rejected']).forEach(s => { byStatus[s] = []; });
      changes.forEach(c => { if (byStatus[c.status] !== undefined) byStatus[c.status].push(c); });

      let html = `<div style="overflow-x:auto;margin-top:16px;">
        <div style="display:grid;grid-template-columns:repeat(5,minmax(180px,1fr));gap:10px;min-width:820px;">`;
      statuses.forEach(s => {
        html += `<div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:10px;">
          <div style="font-weight:700;font-size:12px;margin-bottom:8px;color:var(--text-muted);">
            ${statusLabels[s]} (${byStatus[s].length})
          </div>`;
        byStatus[s].forEach(c => {
          html += `<div class="card" style="margin-bottom:8px;padding:10px;cursor:pointer;"
                        onclick="ViewChangeRequests._detail(${c.id})">
            <div style="margin-bottom:4px;">${UI.codePill(c.code)}</div>
            <div style="font-size:12px;font-weight:600;margin-bottom:6px;">${UI.esc((c.title || '').substring(0, 50))}</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
              <span style="font-size:10px;background:var(--bg-3);padding:2px 6px;border-radius:4px;">
                ${typeLabels[c.change_type] || c.change_type}
              </span>
              <span style="font-size:11px;font-weight:600;color:${IMPACT_COLORS[c.risk_impact] || '#9D9D9D'};">
                ${c.risk_impact}
              </span>
            </div>
          </div>`;
        });
        html += `</div>`;
      });
      html += `</div></div>`;

      if (byStatus.rejected.length) {
        html += `<div style="margin-top:16px;">
          <h3 style="font-size:13px;color:var(--risk-critical);margin-bottom:8px;">
            ${t('change_requests.rejected_heading')} (${byStatus.rejected.length})
          </h3>`;
        byStatus.rejected.forEach(c => {
          html += `<div style="padding:8px 12px;border:1px solid var(--border);border-radius:6px;
                               margin-bottom:6px;font-size:13px;cursor:pointer;"
                       onclick="ViewChangeRequests._detail(${c.id})">
            ${UI.codePill(c.code)} ${UI.esc(c.title || '')}
          </div>`;
        });
        html += `</div>`;
      }
      _wrap.innerHTML = html;
    } catch (e) {
      _wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _openForm(chg) {
    const typeLabels = _getTypeLabels();
    const title = chg ? t('change_requests.modal_edit_title', { code: chg.code }) : t('change_requests.modal_new_title');
    UI.modal(title, `
      <div class="form-grid">
        <div class="span2">
          <label>${t('change_requests.form_title')} *</label>
          <input id="chg-title" class="input" value="${UI.esc(chg?.title || '')}">
        </div>
        <div>
          <label>${t('change_requests.form_type')}</label>
          <select id="chg-type" class="input">
            ${Object.entries(typeLabels).map(([k, v]) =>
              `<option value="${k}" ${chg?.change_type === k ? 'selected' : ''}>${v}</option>`
            ).join('')}
          </select>
        </div>
        <div>
          <label>${t('change_requests.form_impact')}</label>
          <select id="chg-impact" class="input">
            <option value="none" ${chg?.risk_impact === 'none' ? 'selected' : ''}>${t('change_requests.impact_none')}</option>
            <option value="low" ${chg?.risk_impact === 'low' ? 'selected' : ''}>${t('change_requests.impact_low')}</option>
            <option value="medium" ${chg?.risk_impact === 'medium' ? 'selected' : ''}>${t('change_requests.impact_medium')}</option>
            <option value="high" ${chg?.risk_impact === 'high' ? 'selected' : ''}>${t('change_requests.impact_high')}</option>
          </select>
        </div>
        <div class="span2">
          <label>${t('change_requests.form_description')}</label>
          <textarea id="chg-desc" class="input" rows="3">${UI.esc(chg?.description || '')}</textarea>
        </div>
        <div class="span2">
          <label>${t('change_requests.form_reason')}</label>
          <textarea id="chg-reason" class="input" rows="2">${UI.esc(chg?.business_reason || '')}</textarea>
        </div>
        <div>
          <label>${t('change_requests.form_date')}</label>
          <input id="chg-date" class="input" type="datetime-local"
                 value="${chg?.planned_date ? chg.planned_date.replace('Z', '') : ''}">
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="mc-cancel">${t('change_requests.cancel_btn')}</button>
                <button class="btn btn-primary" id="mc-save">${t('change_requests.save_btn')}</button>`,
    });
    document.getElementById('mc-cancel').onclick = UI.closeModal;
    document.getElementById('mc-save').onclick = () => _save(chg?.id || null);
  }

  async function _save(id) {
    const title = document.getElementById('chg-title').value.trim();
    if (!title) { UI.toast(t('change_requests.title_required'), 'error'); return; }
    const body = {
      title,
      change_type: document.getElementById('chg-type').value,
      risk_impact: document.getElementById('chg-impact').value,
      description: document.getElementById('chg-desc').value.trim(),
      business_reason: document.getElementById('chg-reason').value.trim(),
      planned_date: document.getElementById('chg-date').value || null,
    };
    try {
      if (id) {
        await Api.patch(`/api/change-requests/${id}`, body);
        UI.toast(t('change_requests.updated_toast'), 'success');
      } else {
        await Api.post('/api/change-requests', body);
        UI.toast(t('change_requests.created_toast'), 'success');
      }
      UI.closeModal();
      await _load();
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  }

  async function _detail(id) {
    let c;
    try {
      c = await Api.get(`/api/change-requests/${id}`);
    } catch (e) {
      UI.toast(e.message, 'error'); return;
    }

    const statusLabels = _getStatusLabels();
    const typeLabels = _getTypeLabels();
    const locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';

    UI.modal(`${UI.codePill(c.code)} ${UI.esc(c.title || '')}`, `
      <div style="display:flex;flex-direction:column;gap:10px;">
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <span style="background:var(--brand-purple);color:#fff;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;">
            ${statusLabels[c.status] || c.status}
          </span>
          <span style="background:var(--bg-3);padding:2px 10px;border-radius:999px;font-size:12px;">
            ${typeLabels[c.change_type] || c.change_type}
          </span>
          <span style="color:${IMPACT_COLORS[c.risk_impact] || '#9D9D9D'};font-size:12px;font-weight:600;">
            ${t('change_requests.impact_label')}: ${c.risk_impact}
          </span>
        </div>
        ${c.description ? `<div><strong style="font-size:12px;">${t('change_requests.form_description')}:</strong><p style="font-size:13px;margin:4px 0 0;">${UI.esc(c.description)}</p></div>` : ''}
        ${c.business_reason ? `<div><strong style="font-size:12px;">${t('change_requests.form_reason')}:</strong><p style="font-size:13px;margin:4px 0 0;">${UI.esc(c.business_reason)}</p></div>` : ''}
        ${c.planned_date ? `<div style="font-size:13px;"><strong>${t('change_requests.planned_date_label')}:</strong> ${new Date(c.planned_date).toLocaleDateString(locale)}</div>` : ''}
        ${c.implemented_at ? `<div style="font-size:13px;"><strong>${t('change_requests.implemented_label')}:</strong> ${new Date(c.implemented_at).toLocaleDateString(locale)}</div>` : ''}
        ${c.verification_notes ? `<div><strong style="font-size:12px;">${t('change_requests.verification_label')}:</strong><p style="font-size:13px;margin:4px 0 0;">${UI.esc(c.verification_notes)}</p></div>` : ''}
      </div>
    `, {
      actions: `
        <button class="btn" id="md-close">${t('change_requests.close_btn')}</button>
        ${c.status === 'draft' ? `<button class="btn btn-ghost" id="md-edit">${t('change_requests.edit_btn')}</button>` : ''}
        ${c.status === 'draft' ? `<button class="btn btn-secondary" id="md-submit">${t('change_requests.submit_btn_action')}</button>` : ''}
        ${c.status === 'under_review' ? `<button class="btn btn-danger" id="md-reject">${t('change_requests.reject_btn')}</button>` : ''}
        ${c.status === 'under_review' ? `<button class="btn btn-primary" id="md-approve">${t('change_requests.approve_btn')}</button>` : ''}
        ${c.status === 'approved' ? `<button class="btn btn-primary" id="md-implement">${t('change_requests.implement_btn')}</button>` : ''}
        ${c.status === 'implemented' ? `<button class="btn btn-primary" id="md-verify">${t('change_requests.verify_btn')}</button>` : ''}
      `,
    });

    document.getElementById('md-close').onclick = UI.closeModal;
    document.getElementById('md-edit')?.addEventListener('click', () => { UI.closeModal(); _openForm(c); });
    document.getElementById('md-submit')?.addEventListener('click', () => _action('submit', id));
    document.getElementById('md-approve')?.addEventListener('click', () => _action('approve', id));
    document.getElementById('md-reject')?.addEventListener('click', () => _action('reject', id));
    document.getElementById('md-implement')?.addEventListener('click', () => _action('implement', id));
    document.getElementById('md-verify')?.addEventListener('click', () => _action('verify', id));
  }

  async function _action(action, id) {
    let body = {};
    if (action === 'reject' || action === 'verify') {
      const promptKey = action === 'reject' ? 'change_requests.reject_prompt' : 'change_requests.verify_prompt';
      const r = prompt(t(promptKey)) || '';
      body = { reason: r };
    }
    try {
      await Api.post(`/api/change-requests/${id}/${action}`, body);
      UI.toast(t('change_requests.action_done'), 'success');
      UI.closeModal();
      await _load();
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  }

  return { render, _detail, _action, _save };
})();
