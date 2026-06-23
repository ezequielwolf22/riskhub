/* Management Review — ISO 27001 cl. 9.3 */
const ViewManagementReview = (() => {

  function _statusBadge(status) {
    const m = {
      draft:     ['#FEF9C3', '#854d0e', t('management_review.status_draft')],
      conducted: ['#DBEAFE', '#1d4ed8', t('management_review.status_conducted')],
      approved:  ['#D1FAE5', '#065f46', t('management_review.status_approved')],
    };
    const [bg, col, label] = m[status] || ['#F5F5F5', '#9D9D9D', status];
    return `<span style="background:${bg};color:${col};padding:2px 10px;border-radius:10px;font-size:11px;font-weight:700;">${label}</span>`;
  }

  async function render(container) {
    container.innerHTML = UI.sectionHeader(
      t('management_review.title'),
      t('management_review.subtitle'),
      `<button class="btn btn-primary" id="btn-new-mr">${t('management_review.prepare_monthly')}</button>`
    );
    const wrap = document.createElement('div');
    container.appendChild(wrap);
    await _loadList(wrap);
    document.getElementById('btn-new-mr')?.addEventListener('click', _createReview);
  }

  async function _loadList(container) {
    try {
      const reviews = await Api.get('/api/management-review');
      if (!reviews.length) {
        container.innerHTML = UI.emptyState(
          t('management_review.empty_title'),
          t('management_review.empty_body')
        );
        return;
      }
      const _locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
      container.innerHTML = `
      <div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>${t('management_review.col_code')}</th>
            <th>${t('management_review.col_date')}</th>
            <th>${t('management_review.col_status_h')}</th>
            <th>${t('management_review.col_kpis')}</th>
            <th>${t('management_review.col_actions')}</th>
          </tr></thead>
          <tbody>
          ${reviews.map(r => `<tr>
            <td>${UI.codePill(r.code || '-')}</td>
            <td>${r.review_date ? new Date(r.review_date).toLocaleDateString(_locale) : t('management_review.date_unfixed')}</td>
            <td>${_statusBadge(r.status)}</td>
            <td>${r.input_performance_data ? `<span style="color:#16a34a;">${t('management_review.kpis_loaded')}</span>` : '—'}</td>
            <td style="display:flex;gap:4px;flex-wrap:wrap;">
              <button class="btn btn-sm btn-secondary" onclick="ViewManagementReview._detail(${r.id})">${t('management_review.detail_btn')}</button>
              ${r.status !== 'approved' ? `<button class="btn btn-sm btn-secondary" onclick="ViewManagementReview._approve(${r.id})">${t('management_review.approve_btn')}</button>` : ''}
              <a href="/api/management-review/${r.id}/pdf" target="_blank" class="btn btn-sm btn-outline">PDF</a>
            </td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    } catch (e) {
      container.innerHTML = UI.notice('Error: ' + e.message, 'error');
    }
  }

  async function _createReview() {
    try {
      const mr = await Api.post('/api/management-review', {});
      UI.toast(t('management_review.toast_prepared', { code: mr.code }), 'success');
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  async function _detail(id) {
    const mr = await Api.get(`/api/management-review/${id}`);
    const kpis = mr.input_performance_data || {};
    const risks = mr.input_risk_register || [];
    const nc = mr.input_nc_corrections || {};
    const _locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';

    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:680px;max-height:80vh;overflow-y:auto;">
      <div class="modal-header">
        <h2>${UI.esc(mr.code || '')} — ${t('management_review.title')}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <div style="display:flex;gap:8px;margin-bottom:16px;">
          <button class="btn btn-secondary active-tab" id="tab-btn-in" onclick="ViewManagementReview._tabSwitch('in')">${t('management_review.tab_inputs')}</button>
          <button class="btn btn-secondary" id="tab-btn-out" onclick="ViewManagementReview._tabSwitch('out')">${t('management_review.tab_outputs')}</button>
        </div>
        <div id="mr-tab-in">
          <h3 style="font-size:14px;margin:0 0 8px;">${t('management_review.kpis_heading')}</h3>
          <table class="data-table" style="font-size:12px;">
          ${Object.entries(kpis).filter(([k]) => k !== 'generated_at').map(([k, v]) =>
            `<tr><td style="width:50%;"><strong>${k.replace(/_/g, ' ')}</strong></td><td>${v}</td></tr>`
          ).join('')}
          </table>
          <h3 style="font-size:14px;margin:16px 0 8px;">${t('management_review.top_risks')}</h3>
          ${risks.slice(0, 10).map(r => `<div class="list-item" style="font-size:12px;">
            ${UI.codePill(r.code)} ${UI.esc(r.asset || '')} — ${t('management_review.level_label')} <strong>${r.level}</strong> — ${r.status}
          </div>`).join('') || `<p>${t('management_review.no_data')}</p>`}
          <h3 style="font-size:14px;margin:16px 0 8px;">${t('management_review.nc_heading')}</h3>
          <p>${t('management_review.open_nc')}: <strong>${nc.open || 0}</strong> | ${t('management_review.closed_month_nc')}: <strong>${nc.closed_this_month || 0}</strong></p>
          ${mr.input_audit_results?.length ? `
            <h3 style="font-size:14px;margin:16px 0 8px;">${t('management_review.audit_results_heading')}</h3>
            ${mr.input_audit_results.map(a => `<div class="list-item" style="font-size:12px;">
              ${UI.codePill(a.code)} ${UI.esc(a.title || '')} — ${a.finding_count || 0} ${t('management_review.findings_label')}
            </div>`).join('')}` : ''}
        </div>
        <div id="mr-tab-out" style="display:none;">
          <label>${t('management_review.decisions_label')}</label>
          <textarea id="mr-decisions" class="form-control" rows="5" style="width:100%"
            placeholder="${t('management_review.decisions_placeholder')}">${(mr.output_decisions || []).join('\n')}</textarea>
          <label style="margin-top:12px;">${t('management_review.resources_label')}</label>
          <textarea id="mr-resources" class="form-control" rows="3" style="width:100%;margin-top:4px;">${mr.output_resources || ''}</textarea>
          <div style="display:flex;gap:8px;margin-top:12px;">
            <button class="btn btn-secondary" onclick="ViewManagementReview._saveOutputs(${id})">${t('management_review.save_outputs_btn')}</button>
            <button class="btn btn-primary" onclick="ViewManagementReview._conduct(${id})">${t('management_review.mark_conducted_btn')}</button>
          </div>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  function _tabSwitch(tab) {
    document.getElementById('mr-tab-in').style.display = tab === 'in' ? '' : 'none';
    document.getElementById('mr-tab-out').style.display = tab === 'out' ? '' : 'none';
  }

  async function _saveOutputs(id) {
    const decisions = (document.getElementById('mr-decisions')?.value || '').split('\n').filter(Boolean);
    const resources = document.getElementById('mr-resources')?.value || '';
    await Api.patch(`/api/management-review/${id}`, { output_decisions: decisions, output_resources: resources });
    UI.toast(t('management_review.outputs_saved'), 'success');
  }

  async function _conduct(id) {
    await _saveOutputs(id);
    await Api.post(`/api/management-review/${id}/conduct`, {});
    UI.toast(t('management_review.conducted_toast'), 'success');
    document.querySelector('.modal-bg')?.remove();
    location.reload();
  }

  async function _approve(id) {
    if (!await UI.confirm(t('management_review.approve_confirm'))) return;
    try {
      await Api.post(`/api/management-review/${id}/approve`, {});
      UI.toast(t('management_review.approved_toast'), 'success');
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  return { render, _detail, _approve, _tabSwitch, _saveOutputs, _conduct };
})();
