/* NIS2 Dashboard — Wizard de notificacion Art. 23 */
const ViewNis2Dashboard = (() => {

  let _countdownInterval = null;

  function _stageLabel(s) {
    return {
      early_warning:  t('nis2.stage_early'),
      initial_report: t('nis2.stage_initial'),
      final_report:   t('nis2.stage_final'),
    }[s] || s;
  }

  function _statusLabel(s) {
    return {
      pending:      t('nis2.status_pending'),
      submitted:    t('nis2.status_submitted'),
      acknowledged: t('nis2.status_acknowledged'),
      overdue:      t('nis2.status_overdue'),
    }[s] || s;
  }

  let _wrap = null;

  async function render(container) {
    if (_countdownInterval) clearInterval(_countdownInterval);
    container.innerHTML = UI.sectionHeader(
      t('nis2.dashboard_title'),
      t('nis2.dashboard_subtitle'),
      Auth.canEdit() ? `<button class="btn btn-primary" id="btn-new-nis2-inc">${t('nis2.btn_new_incident')}</button>` : ''
    );
    _wrap = document.createElement('div');
    container.appendChild(_wrap);
    await _load(_wrap);
    document.getElementById('btn-new-nis2-inc')?.addEventListener('click', _openNewIncidentForm);

    if (!document.getElementById('nis2-css')) {
      const s = document.createElement('style');
      s.id = 'nis2-css';
      s.textContent = `.nis2-sc{padding:12px;border-radius:8px;border:2px solid #E9E9E9;text-align:center;min-height:110px;}
        .nis2-sc-label{font-weight:700;font-size:11px;margin-bottom:6px;color:#374151;}
        .nis2-sc-status{font-size:11px;color:#9D9D9D;margin:2px 0;}
        .nis2-cntdwn{font-size:22px;font-weight:800;color:#D97706;margin:4px 0;}
        .nis2-pending{border-color:#D97706;background:#FFFBEB;}
        .nis2-done{border-color:#16a34a;background:#F0FDF4;}
        .nis2-overdue{border-color:#DC2626;background:#FEF2F2;}
        .nis2-overdue .nis2-cntdwn{color:#DC2626;}
        .nis2-missing{border-color:#D1D5DB;background:#F9FAFB;}`;
      document.head.appendChild(s);
    }
  }

  async function _load(container) {
    try {
      const data = await Api.get('/api/nis2/dashboard');

      let html = `
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px;">
        <div class="stat-card">
          <div class="stat-value">${data.incidents_requiring_notification}</div>
          <div class="stat-label">${t('nis2.stat_incidents')}</div>
        </div>
        <div class="stat-card ${data.pending_notifications > 0 ? 'stat-warning' : ''}">
          <div class="stat-value">${data.pending_notifications}</div>
          <div class="stat-label">${t('nis2.stat_pending')}</div>
        </div>
        <div class="stat-card ${data.overdue_notifications > 0 ? 'stat-danger' : ''}">
          <div class="stat-value">${data.overdue_notifications}</div>
          <div class="stat-label">${t('nis2.stat_overdue')}</div>
        </div>
      </div>`;

      if (!data.incidents.length) {
        container.innerHTML = html + UI.emptyState(t('nis2.empty_title'), t('nis2.empty_body'));
        return;
      }

      const stages = ['early_warning', 'initial_report', 'final_report'];
      const locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';

      data.incidents.forEach((inc, idx) => {
        const notifCards = stages.map(stage => {
          const n = (inc.notifications || []).find(x => x.stage === stage);
          if (!n) return `<div class="nis2-sc nis2-missing"><div class="nis2-sc-label">${_stageLabel(stage)}</div><div class="nis2-sc-status">${t('nis2.not_created')}</div></div>`;
          const cls = { pending: 'nis2-pending', submitted: 'nis2-done', overdue: 'nis2-overdue' }[n.status] || '';
          const btnAction = (n.status === 'pending' || n.status === 'overdue')
            ? `<button class="btn btn-sm btn-primary" style="margin-top:4px;" onclick="ViewNis2Dashboard._wizard(${n.id})">${t('nis2.complete_btn')}</button>` : '';
          return `
          <div class="nis2-sc ${cls}">
            <div class="nis2-sc-label">${n.stage_label}</div>
            <div class="nis2-cntdwn" data-deadline="${n.deadline_at || ''}">${n.hours_left != null ? Math.round(Math.max(0, n.hours_left)) + 'h' : '—'}</div>
            <div class="nis2-sc-status">${_statusLabel(n.status)}</div>
            ${btnAction}
            <div style="display:flex;gap:4px;justify-content:center;margin-top:4px;flex-wrap:wrap;">
              <a href="/api/nis2/notifications/${n.id}/pdf" target="_blank" class="btn btn-sm btn-ghost" style="font-size:11px;">PDF</a>
              <button class="btn btn-sm btn-ghost" style="font-size:11px;" onclick="ViewNis2Dashboard._openEvidenceModal(${n.id})">${t('nis2.btn_evidence')}</button>
            </div>
          </div>`;
        }).join('');

        const activityLog = (inc.notifications || []).filter(n => n.submitted_at).map(n => `
          <div style="display:flex;gap:10px;align-items:flex-start;font-size:12px;padding:6px 0;border-bottom:1px solid var(--border);">
            <span style="min-width:70px;color:var(--text-muted);">${n.submitted_at ? n.submitted_at.slice(0,10) : ''}</span>
            <span style="font-weight:600;">${n.stage_label}</span>
            <span style="color:var(--risk-low);">${_statusLabel('submitted')}</span>
            ${n.notification_ref ? `<span style="color:var(--text-muted);"># ${UI.esc(n.notification_ref)}</span>` : ''}
          </div>`).join('') || `<p style="font-size:12px;color:var(--text-muted);">${t('nis2.no_activity')}</p>`;

        html += `
        <div style="background:var(--bg-1);border:1px solid var(--border);border-radius:10px;margin-bottom:14px;overflow:hidden;">
          <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 16px;cursor:pointer;"
               onclick="document.getElementById('nis2-body-${idx}').style.display = document.getElementById('nis2-body-${idx}').style.display === 'none' ? 'block' : 'none'">
            <div style="display:flex;align-items:center;gap:8px;">
              ${UI.codePill(inc.incident_code)}
              <span style="font-weight:600;">${UI.esc(inc.incident_title)}</span>
              <span style="font-size:11px;color:var(--text-muted);">${inc.incident_status}</span>
            </div>
            <div style="display:flex;gap:6px;align-items:center;">
              <button class="btn btn-sm btn-secondary" onclick="event.stopPropagation();ViewNis2Dashboard._createChain(${inc.incident_id})">${t('nis2.create_chain_btn')}</button>
              <span style="color:var(--text-muted);font-size:16px;">&#x25BE;</span>
            </div>
          </div>
          <div id="nis2-body-${idx}" style="padding:0 16px 14px;">
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px;">${notifCards}</div>
            <details style="font-size:13px;">
              <summary style="cursor:pointer;font-weight:600;color:var(--text-muted);margin-bottom:8px;">${t('nis2.activity_log_title')}</summary>
              <div style="margin-top:8px;">${activityLog}</div>
            </details>
          </div>
        </div>`;
      });

      container.innerHTML = html;
      _startCountdowns();
    } catch (e) {
      container.innerHTML = UI.notice('Error: ' + e.message, 'error');
    }
  }

  function _startCountdowns() {
    if (_countdownInterval) clearInterval(_countdownInterval);
    const update = () => {
      document.querySelectorAll('[data-deadline]').forEach(el => {
        if (!el.dataset.deadline) return;
        const diff = new Date(el.dataset.deadline) - new Date();
        if (diff <= 0) { el.textContent = t('nis2.status_overdue'); el.style.color = '#DC2626'; return; }
        const h = Math.floor(diff / 3600000);
        const m = Math.floor((diff % 3600000) / 60000);
        el.textContent = h > 0 ? `${h}h ${m}m` : `${m}m`;
      });
    };
    update();
    _countdownInterval = setInterval(update, 30000);
  }

  async function _createChain(incidentId) {
    try {
      const res = await Api.post(`/api/nis2/incidents/${incidentId}/create-chain`, {});
      UI.toast(t('nis2.notifications_created', { n: res.created }), 'success');
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  async function _wizard(notifId) {
    const n = await Api.get(`/api/nis2/notifications/${notifId}`);
    const c = n.content_json || {};
    const locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:560px;">
      <div class="modal-header">
        <h2>NIS2 — ${UI.esc(n.stage_label)}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <p style="color:#D97706;font-size:12px;">${t('nis2.deadline_label')}: <strong>${n.deadline_at ? new Date(n.deadline_at).toLocaleString(locale) : '—'}</strong></p>
        <label>${t('nis2.authority_label')}</label>
        <input id="nw-auth" class="form-control" value="${UI.esc(n.recipient_authority || 'INCIBE-CERT')}">
        <label style="margin-top:10px;">${t('nis2.ref_label')}</label>
        <input id="nw-ref" class="form-control" placeholder="${t('nis2.ref_placeholder')}" value="${UI.esc(n.notification_ref || '')}">
        <label style="margin-top:10px;">${t('nis2.desc_label')}</label>
        <textarea id="nw-desc" class="form-control" rows="3" style="width:100%">${UI.esc(c.description || '')}</textarea>
        <label style="margin-top:10px;">${t('nis2.systems_label')}</label>
        <input id="nw-sys" class="form-control" value="${UI.esc(c.affected_systems || '')}">
        <label style="margin-top:10px;">${t('nis2.measures_label')}</label>
        <textarea id="nw-measures" class="form-control" rows="2" style="width:100%">${UI.esc(c.measures || '')}</textarea>
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-secondary" onclick="ViewNis2Dashboard._saveWizard(${notifId})">${t('nis2.save_draft_btn')}</button>
          <button class="btn btn-primary" onclick="ViewNis2Dashboard._submitWizard(${notifId})">${t('nis2.submit_wizard_btn')}</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _saveWizard(id) {
    const body = {
      recipient_authority: document.getElementById('nw-auth').value,
      notification_ref: document.getElementById('nw-ref').value,
      content_json: {
        description: document.getElementById('nw-desc').value,
        affected_systems: document.getElementById('nw-sys').value,
        measures: document.getElementById('nw-measures').value,
      },
    };
    await Api.patch(`/api/nis2/notifications/${id}`, body);
    UI.toast(t('nis2.draft_saved'), 'success');
  }

  async function _submitWizard(id) {
    if (!await UI.confirm(t('nis2.submit_confirm'))) return;
    await _saveWizard(id);
    await Api.post(`/api/nis2/notifications/${id}/submit`, {});
    UI.toast(t('nis2.submitted_toast'), 'success');
    document.querySelector('.modal-bg')?.remove();
    location.reload();
  }

  async function _openNewIncidentForm() {
    UI.modal(t('nis2.new_incident_title'), `
      <div class="form-grid">
        <div class="span2"><label>${t('nis2.inc_field_title')} *</label><input id="ni-title" class="input" placeholder="${t('nis2.inc_field_title_placeholder')}"></div>
        <div>
          <label>${t('nis2.inc_field_severity')}</label>
          <select id="ni-severity" class="input">
            <option value="P1">P1 — ${t('incidents.severity_p1') || 'Crítico'}</option>
            <option value="P2">P2 — ${t('incidents.severity_p2') || 'Alto'}</option>
            <option value="P3" selected>P3 — ${t('incidents.severity_p3') || 'Medio'}</option>
            <option value="P4">P4 — ${t('incidents.severity_p4') || 'Bajo'}</option>
          </select>
        </div>
        <div><label>${t('nis2.inc_field_detected')}</label><input type="date" id="ni-detected" class="input" value="${new Date().toISOString().slice(0,10)}"></div>
        <div class="span2"><label>${t('nis2.inc_field_desc')}</label><textarea id="ni-desc" class="input" rows="3" placeholder="${t('nis2.inc_field_desc_placeholder')}"></textarea></div>
        <div class="span2"><label>${t('nis2.inc_field_affected_systems')}</label><input id="ni-systems" class="input" placeholder="${t('nis2.inc_field_affected_systems_placeholder')}"></div>
        <div class="span2"><label>${t('nis2.inc_field_response')}</label><textarea id="ni-response" class="input" rows="2" placeholder="${t('nis2.inc_field_response_placeholder')}"></textarea></div>
      </div>
    `, {
      actions: `<button class="btn" id="ni-cancel">${t('nis2.btn_cancel')}</button>
                <button class="btn btn-primary" id="ni-save">${t('nis2.btn_create_incident')}</button>`
    });
    document.getElementById('ni-cancel').onclick = UI.closeModal;
    document.getElementById('ni-save').onclick = async () => {
      const title = document.getElementById('ni-title').value.trim();
      if (!title) { UI.toast(t('nis2.inc_title_required'), 'error'); return; }
      const systemsVal = document.getElementById('ni-systems').value.trim();
      try {
        const inc = await Api.post('/api/incidents/', {
          title,
          severity: document.getElementById('ni-severity').value,
          detected_at: document.getElementById('ni-detected').value || null,
          description: document.getElementById('ni-desc').value.trim(),
          affected_systems: systemsVal ? systemsVal.split(',').map(s => s.trim()).filter(Boolean) : [],
          response_actions: document.getElementById('ni-response').value.trim(),
          nis2_notification_required: true,
          gdpr_notification_required: true,
          status: 'open',
        });
        UI.toast(t('nis2.incident_created'), 'success');
        UI.closeModal();
        if (_wrap) await _load(_wrap);
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  async function _openEvidenceModal(notifId) {
    const n = await Api.get(`/api/nis2/notifications/${notifId}`);
    const c = n.content_json || {};
    UI.modal(t('nis2.evidence_modal_title'), `
      <div style="display:flex;flex-direction:column;gap:12px;">
        <div><strong>${t('nis2.evidence_stage')}</strong> ${UI.esc(n.stage_label || '')}</div>
        <div>
          <label style="font-weight:600;font-size:13px;display:block;margin-bottom:4px;">${t('nis2.evidence_notes_label')}</label>
          <textarea id="ev-notes" class="input" rows="4">${UI.esc(c.evidence_notes || '')}</textarea>
        </div>
        <div>
          <label style="font-weight:600;font-size:13px;display:block;margin-bottom:4px;">${t('nis2.evidence_refs_label')}</label>
          <input id="ev-refs" class="input" placeholder="${t('nis2.evidence_refs_placeholder')}" value="${UI.esc(c.evidence_refs || '')}">
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="ev-cancel">${t('nis2.btn_cancel')}</button>
                <button class="btn btn-primary" id="ev-save">${t('nis2.btn_save_evidence')}</button>`
    });
    document.getElementById('ev-cancel').onclick = UI.closeModal;
    document.getElementById('ev-save').onclick = async () => {
      const updated_content = {
        ...c,
        evidence_notes: document.getElementById('ev-notes').value.trim(),
        evidence_refs: document.getElementById('ev-refs').value.trim(),
      };
      try {
        await Api.patch(`/api/nis2/notifications/${notifId}`, { content_json: updated_content });
        UI.toast(t('nis2.evidence_saved'), 'success');
        UI.closeModal();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  return { render, _createChain, _wizard, _saveWizard, _submitWizard, _openNewIncidentForm, _openEvidenceModal };
})();
