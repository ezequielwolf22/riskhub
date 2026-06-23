/* Informes Programados */
const ViewReportSchedules = (() => {

  async function render(container) {
    container.innerHTML = UI.sectionHeader(
      t('report_schedules.title'),
      t('report_schedules.subtitle'),
      `<button class="btn btn-primary" id="btn-new-sched">${t('report_schedules.new_btn')}</button>`
    );
    const wrap = document.createElement('div');
    container.appendChild(wrap);
    await _load(wrap);
    document.getElementById('btn-new-sched')?.addEventListener('click', _openForm);
  }

  async function _load(container) {
    try {
      const scheds = await Api.get('/api/report-schedules');
      if (!scheds.length) {
        container.innerHTML = UI.emptyState(
          t('report_schedules.empty_title'),
          t('report_schedules.empty_body')
        );
        return;
      }
      const _locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
      container.innerHTML = `
      <div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>${t('report_schedules.col_type')}</th>
            <th>${t('report_schedules.col_frequency')}</th>
            <th>${t('report_schedules.col_recipients')}</th>
            <th>${t('report_schedules.col_last_sent')}</th>
            <th>${t('report_schedules.col_next')}</th>
            <th>${t('report_schedules.col_status')}</th>
            <th>${t('report_schedules.col_actions')}</th>
          </tr></thead>
          <tbody>
          ${scheds.map(s => `<tr>
            <td>${UI.esc(s.report_type)}</td>
            <td>${s.frequency}</td>
            <td style="font-size:11px;">${(s.recipients || []).join(', ')}</td>
            <td>${s.last_sent_at ? new Date(s.last_sent_at).toLocaleDateString(_locale) : '—'}</td>
            <td>${s.next_scheduled_at ? new Date(s.next_scheduled_at).toLocaleDateString(_locale) : '—'}</td>
            <td><span class="badge ${s.is_active ? 'badge-success' : 'badge-secondary'}">${s.is_active ? t('report_schedules.status_active') : t('report_schedules.status_paused')}</span></td>
            <td style="display:flex;gap:4px;">
              <button class="btn btn-sm btn-secondary" onclick="ViewReportSchedules._runNow(${s.id})">${t('report_schedules.run_now_btn')}</button>
              <button class="btn btn-sm btn-danger" onclick="ViewReportSchedules._del(${s.id})">${t('report_schedules.delete_btn')}</button>
            </td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    } catch (e) {
      const errMsg = (e && e.message) || 'Error';
      const statusInfo = (e && e.status) ? ` (${e.status})` : '';
      console.error('ViewReportSchedules error:', e);
      container.innerHTML = UI.notice('error', errMsg + statusInfo);
    }
  }

  async function _runNow(id) {
    UI.toast(t('report_schedules.generating'), 'info');
    try {
      const res = await Api.post(`/api/report-schedules/${id}/run-now`, {});
      UI.toast(t('report_schedules.sent_to', { recipients: (res.recipients || []).join(', ') }), 'success');
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  async function _del(id) {
    if (!await UI.confirm(t('report_schedules.delete_confirm'))) return;
    await Api.del(`/api/report-schedules/${id}`);
    UI.toast(t('report_schedules.deleted_toast'), 'success');
    location.reload();
  }

  function _openForm() {
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:440px;">
      <div class="modal-header">
        <h2>${t('report_schedules.modal_title')}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <label>${t('report_schedules.type_label')}</label>
        <select id="sched-type" class="form-control">
          <option value="executive_dashboard">${t('report_schedules.type_executive')}</option>
          <option value="risk_register">${t('report_schedules.type_risk_register')}</option>
          <option value="committee_minutes">${t('report_schedules.type_committee')}</option>
          <option value="followup_report">${t('report_schedules.type_followup')}</option>
        </select>
        <label style="margin-top:10px;">${t('report_schedules.freq_label')}</label>
        <select id="sched-freq" class="form-control">
          <option value="weekly">${t('report_schedules.freq_weekly')}</option>
          <option value="monthly" selected>${t('report_schedules.freq_monthly')}</option>
          <option value="quarterly">${t('report_schedules.freq_quarterly')}</option>
        </select>
        <label style="margin-top:10px;">${t('report_schedules.recipients_label')}</label>
        <input id="sched-emails" class="form-control" placeholder="${t('report_schedules.recipients_placeholder')}">
        <label style="margin-top:10px;display:flex;align-items:center;gap:8px;">
          <input type="checkbox" id="sched-ai"> ${t('report_schedules.include_ai')}
        </label>
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewReportSchedules._save()">${t('report_schedules.save_btn')}</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-bg').remove()">${t('report_schedules.cancel_btn')}</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _save() {
    const emails = document.getElementById('sched-emails').value.split(',').map(e => e.trim()).filter(Boolean);
    if (!emails.length) { UI.toast(t('report_schedules.email_required'), 'error'); return; }
    const body = {
      report_type:          document.getElementById('sched-type').value,
      frequency:            document.getElementById('sched-freq').value,
      recipients:           emails,
      include_ai_analysis:  document.getElementById('sched-ai').checked,
    };
    try {
      await Api.post('/api/report-schedules', body);
      UI.toast(t('report_schedules.created_toast'), 'success');
      document.querySelector('.modal-bg')?.remove();
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  return { render, _runNow, _del, _save };
})();
