/* Informes Programados */
const ViewReportSchedules = (() => {

  async function render(container) {
    container.innerHTML = UI.sectionHeader(
      'Informes Programados',
      'Configura el envio automatico de informes PDF a los destinatarios',
      `<button class="btn btn-primary" id="btn-new-sched">+ Nueva programacion</button>`
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
        container.innerHTML = UI.emptyState('Sin informes programados', 'Configura el envio automatico mensual o semanal para comites y direccion.');
        return;
      }
      container.innerHTML = `
      <div class="table-container">
        <table class="data-table">
          <thead><tr><th>Tipo</th><th>Frecuencia</th><th>Destinatarios</th><th>Ultimo envio</th><th>Proximo</th><th>Estado</th><th>Acciones</th></tr></thead>
          <tbody>
          ${scheds.map(s => `<tr>
            <td>${UI.esc(s.report_type)}</td>
            <td>${s.frequency}</td>
            <td style="font-size:11px;">${(s.recipients||[]).join(', ')}</td>
            <td>${s.last_sent_at ? new Date(s.last_sent_at).toLocaleDateString('es-ES') : '—'}</td>
            <td>${s.next_scheduled_at ? new Date(s.next_scheduled_at).toLocaleDateString('es-ES') : '—'}</td>
            <td><span class="badge ${s.is_active?'badge-success':'badge-secondary'}">${s.is_active?'Activo':'Pausado'}</span></td>
            <td style="display:flex;gap:4px;">
              <button class="btn btn-sm btn-secondary" onclick="ViewReportSchedules._runNow(${s.id})">Enviar ahora</button>
              <button class="btn btn-sm btn-danger" onclick="ViewReportSchedules._del(${s.id})">Eliminar</button>
            </td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    } catch (e) {
      const errMsg = (e && e.message) || 'Error desconocido al cargar programaciones';
      const statusInfo = (e && e.status) ? ` (código ${e.status})` : '';
      console.error('ViewReportSchedules error:', e);
      container.innerHTML = UI.notice('error', errMsg + statusInfo);
    }
  }

  async function _runNow(id) {
    UI.toast('Generando informe...', 'info');
    try {
      const res = await Api.post(`/api/report-schedules/${id}/run-now`, {});
      UI.toast(`Informe enviado a: ${(res.recipients||[]).join(', ')}`, 'success');
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  async function _del(id) {
    if (!confirm('Eliminar esta programacion?')) return;
    await Api.del(`/api/report-schedules/${id}`);
    UI.toast('Eliminada', 'success');
    location.reload();
  }

  function _openForm() {
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:440px;">
      <div class="modal-header">
        <h2>Nueva programacion de informe</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">×</button>
      </div>
      <div class="modal-body">
        <label>Tipo de informe</label>
        <select id="sched-type" class="form-control">
          <option value="executive_dashboard">Dashboard ejecutivo</option>
          <option value="risk_register">Registro de riesgos</option>
          <option value="committee_minutes">Acta de comite</option>
          <option value="followup_report">Seguimiento ISO 27005</option>
        </select>
        <label style="margin-top:10px;">Frecuencia</label>
        <select id="sched-freq" class="form-control">
          <option value="weekly">Semanal</option>
          <option value="monthly" selected>Mensual</option>
          <option value="quarterly">Trimestral</option>
        </select>
        <label style="margin-top:10px;">Destinatarios (emails separados por coma)</label>
        <input id="sched-emails" class="form-control" placeholder="ciso@empresa.com, director@empresa.com">
        <label style="margin-top:10px;display:flex;align-items:center;gap:8px;">
          <input type="checkbox" id="sched-ai"> Incluir analisis IA
        </label>
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewReportSchedules._save()">Guardar</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-bg').remove()">Cancelar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _save() {
    const emails = document.getElementById('sched-emails').value.split(',').map(e=>e.trim()).filter(Boolean);
    if (!emails.length) { UI.toast('Introduce al menos un email', 'error'); return; }
    const body = {
      report_type: document.getElementById('sched-type').value,
      frequency: document.getElementById('sched-freq').value,
      recipients: emails,
      include_ai_analysis: document.getElementById('sched-ai').checked,
    };
    try {
      await Api.post('/api/report-schedules', body);
      UI.toast('Programacion creada', 'success');
      document.querySelector('.modal-bg')?.remove();
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  return { render, _runNow, _del, _save };
})();
