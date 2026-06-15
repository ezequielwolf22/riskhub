/* NIS2 Dashboard — Wizard de notificacion Art. 23 */
const ViewNis2Dashboard = (() => {

  let _countdownInterval = null;

  function _stageLabel(s) {
    return { early_warning: 'Alerta temprana (24h)', initial_report: 'Notif. inicial (72h)', final_report: 'Informe final (30d)' }[s] || s;
  }

  function _statusLabel(s) {
    return { pending: 'Pendiente', submitted: 'Enviado', acknowledged: 'Confirmado', overdue: 'VENCIDO' }[s] || s;
  }

  async function render(container) {
    if (_countdownInterval) clearInterval(_countdownInterval);
    container.innerHTML = UI.sectionHeader(
      'NIS2 — Centro de Notificaciones',
      'Directiva (UE) 2022/2555 Art. 23 — Plazos obligatorios: 24h / 72h / 30 dias'
    );
    const wrap = document.createElement('div');
    container.appendChild(wrap);
    await _load(wrap);

    // CSS para stage cards
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
        <div class="stat-card"><div class="stat-value">${data.incidents_requiring_notification}</div><div class="stat-label">Incidentes NIS2</div></div>
        <div class="stat-card ${data.pending_notifications>0?'stat-warning':''}">
          <div class="stat-value">${data.pending_notifications}</div><div class="stat-label">Pendientes</div></div>
        <div class="stat-card ${data.overdue_notifications>0?'stat-danger':''}">
          <div class="stat-value">${data.overdue_notifications}</div><div class="stat-label">Vencidas</div></div>
      </div>`;

      if (!data.incidents.length) {
        container.innerHTML = html + UI.emptyState('Sin incidentes NIS2', 'No hay incidentes con notificacion NIS2 requerida.');
        return;
      }

      const stages = ['early_warning', 'initial_report', 'final_report'];
      data.incidents.forEach(inc => {
        const notifCards = stages.map(stage => {
          const n = (inc.notifications||[]).find(x => x.stage === stage);
          if (!n) return `<div class="nis2-sc nis2-missing"><div class="nis2-sc-label">${_stageLabel(stage)}</div><div class="nis2-sc-status">Sin crear</div></div>`;
          const cls = { pending: 'nis2-pending', submitted: 'nis2-done', overdue: 'nis2-overdue' }[n.status] || '';
          const btnAction = (n.status === 'pending' || n.status === 'overdue')
            ? `<button class="btn btn-sm btn-primary" style="margin-top:4px;" onclick="ViewNis2Dashboard._wizard(${n.id})">Completar</button>` : '';
          return `
          <div class="nis2-sc ${cls}">
            <div class="nis2-sc-label">${n.stage_label}</div>
            <div class="nis2-cntdwn" data-deadline="${n.deadline_at||''}">${n.hours_left!=null ? Math.round(Math.max(0,n.hours_left))+'h' : '—'}</div>
            <div class="nis2-sc-status">${_statusLabel(n.status)}</div>
            ${btnAction}
            <a href="/api/nis2/notifications/${n.id}/pdf" target="_blank" class="btn btn-sm btn-outline" style="margin-top:4px;">PDF</a>
          </div>`;
        }).join('');

        html += `
        <div class="card" style="margin-bottom:14px;">
          <div class="card-header">
            ${UI.codePill(inc.incident_code)} ${UI.esc(inc.incident_title)}
            <span style="margin-left:8px;font-size:11px;color:#9D9D9D;">${inc.incident_status}</span>
            <button class="btn btn-sm btn-secondary" style="float:right;"
              onclick="ViewNis2Dashboard._createChain(${inc.incident_id})">Crear cadena NIS2</button>
          </div>
          <div class="card-body">
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;">${notifCards}</div>
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
        if (diff <= 0) { el.textContent = 'VENCIDO'; el.style.color = '#DC2626'; return; }
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
      UI.toast(`${res.created} notificaciones NIS2 creadas`, 'success');
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  async function _wizard(notifId) {
    const n = await Api.get(`/api/nis2/notifications/${notifId}`);
    const c = n.content_json || {};
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:560px;">
      <div class="modal-header">
        <h2>NIS2 — ${UI.esc(n.stage_label)}</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <p style="color:#D97706;font-size:12px;">Plazo: <strong>${n.deadline_at ? new Date(n.deadline_at).toLocaleString('es-ES') : '—'}</strong></p>
        <label>Autoridad receptora</label>
        <input id="nw-auth" class="form-control" value="${UI.esc(n.recipient_authority||'INCIBE-CERT')}">
        <label style="margin-top:10px;">Referencia expediente</label>
        <input id="nw-ref" class="form-control" placeholder="Numero de expediente..." value="${UI.esc(n.notification_ref||'')}">
        <label style="margin-top:10px;">Descripcion del incidente</label>
        <textarea id="nw-desc" class="form-control" rows="3" style="width:100%">${UI.esc(c.description||'')}</textarea>
        <label style="margin-top:10px;">Sistemas afectados</label>
        <input id="nw-sys" class="form-control" value="${UI.esc(c.affected_systems||'')}">
        <label style="margin-top:10px;">Medidas adoptadas</label>
        <textarea id="nw-measures" class="form-control" rows="2" style="width:100%">${UI.esc(c.measures||'')}</textarea>
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-secondary" onclick="ViewNis2Dashboard._saveWizard(${notifId})">Guardar borrador</button>
          <button class="btn btn-primary" onclick="ViewNis2Dashboard._submitWizard(${notifId})">Marcar como enviada</button>
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
    UI.toast('Borrador guardado', 'success');
  }

  async function _submitWizard(id) {
    if (!confirm('Marcar como enviada? El timestamp quedara registrado de forma inmutable.')) return;
    await _saveWizard(id);
    await Api.post(`/api/nis2/notifications/${id}/submit`, {});
    UI.toast('Notificacion marcada como enviada', 'success');
    document.querySelector('.modal-bg')?.remove();
    location.reload();
  }

  return { render, _createChain, _wizard, _saveWizard, _submitWizard };
})();
