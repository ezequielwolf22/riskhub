/* Change Management — ISO 27001 cl. 6.3 */
const ViewChangeRequests = (() => {

  const STATUS_LABELS = { draft:'Borrador', under_review:'En revision', approved:'Aprobado', rejected:'Rechazado', implemented:'Implementado', verified:'Verificado' };
  const IMPACT_COLORS = { none:'#9D9D9D', low:'#16a34a', medium:'#D97706', high:'#DC2626' };

  async function render(container) {
    container.innerHTML = UI.sectionHeader(
      'Gestion de Cambios',
      'ISO 27001 cl. 6.3 — Control de cambios planificados en el SGSI',
      `<button class="btn btn-primary" id="btn-new-chg">+ Nuevo cambio</button>`
    );
    const wrap = document.createElement('div');
    container.appendChild(wrap);
    await _load(wrap);
    document.getElementById('btn-new-chg')?.addEventListener('click', () => _openForm());
  }

  async function _load(container) {
    try {
      const changes = await Api.get('/api/change-requests');
      if (!changes.length) {
        container.innerHTML = UI.emptyState('Sin solicitudes de cambio', 'Registra cambios en politicas, controles o activos para mantener trazabilidad.');
        return;
      }
      const statuses = ['draft','under_review','approved','implemented','verified'];
      const byStatus = {};
      statuses.concat(['rejected']).forEach(s => byStatus[s] = []);
      changes.forEach(c => { if (byStatus[c.status] !== undefined) byStatus[c.status].push(c); });

      let html = `<div style="overflow-x:auto;"><div style="display:grid;grid-template-columns:repeat(5,minmax(180px,1fr));gap:10px;min-width:820px;">`;
      statuses.forEach(s => {
        html += `<div style="background:#F5F5F5;border-radius:8px;padding:10px;">
          <div style="font-weight:700;font-size:12px;margin-bottom:8px;">${STATUS_LABELS[s]} (${byStatus[s].length})</div>`;
        byStatus[s].forEach(c => {
          html += `<div class="card" style="margin-bottom:8px;padding:8px;cursor:pointer;" onclick="ViewChangeRequests._detail(${c.id})">
            <div style="font-size:11px;">${UI.codePill(c.code)}</div>
            <div style="font-size:12px;margin:4px 0;">${UI.esc((c.title||'').substring(0,45))}</div>
            <span class="badge badge-secondary" style="font-size:10px;">${c.change_type}</span>
            <span style="font-size:11px;color:${IMPACT_COLORS[c.risk_impact]||'#9D9D9D'};margin-left:4px;">⬆ ${c.risk_impact}</span>
          </div>`;
        });
        html += `</div>`;
      });
      html += `</div></div>`;

      if (byStatus.rejected.length) {
        html += `<div style="margin-top:14px;"><h3 style="font-size:12px;color:#DC2626;">Rechazados (${byStatus.rejected.length})</h3>`;
        byStatus.rejected.forEach(c => {
          html += `<div class="list-item" style="font-size:12px;">${UI.codePill(c.code)} ${UI.esc(c.title||'')}</div>`;
        });
        html += `</div>`;
      }
      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = UI.notice('error', 'Error: ' + e.message);
    }
  }

  function _openForm(chg) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
    <div class="modal" style="max-width:500px;">
      <div class="modal-header">
        <h2>${chg ? 'Editar cambio' : 'Nueva solicitud de cambio'}</h2>
        <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
      </div>
      <div class="modal-body">
        <label>Titulo *</label>
        <input id="chg-title" class="form-control" value="${UI.esc(chg?.title||'')}">
        <label style="margin-top:10px;">Tipo</label>
        <select id="chg-type" class="form-control">
          ${['policy','control','asset','process','infrastructure','other'].map(t=>`<option value="${t}"${chg?.change_type===t?' selected':''}>${t}</option>`).join('')}
        </select>
        <label style="margin-top:10px;">Impacto en riesgo</label>
        <select id="chg-impact" class="form-control">
          ${['none','low','medium','high'].map(i=>`<option value="${i}"${chg?.risk_impact===i?' selected':''}>${i}</option>`).join('')}
        </select>
        <label style="margin-top:10px;">Descripcion</label>
        <textarea id="chg-desc" class="form-control" rows="2">${UI.esc(chg?.description||'')}</textarea>
        <label style="margin-top:10px;">Razon de negocio</label>
        <textarea id="chg-reason" class="form-control" rows="2">${UI.esc(chg?.business_reason||'')}</textarea>
        <label style="margin-top:10px;">Fecha planificada</label>
        <input id="chg-date" class="form-control" type="datetime-local" value="${chg?.planned_date?(chg.planned_date.replace('Z','')):''}">
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewChangeRequests._save(${chg?.id||'null'})">Guardar</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Cancelar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _save(id) {
    const body = {
      title: document.getElementById('chg-title').value.trim(),
      change_type: document.getElementById('chg-type').value,
      risk_impact: document.getElementById('chg-impact').value,
      description: document.getElementById('chg-desc').value,
      business_reason: document.getElementById('chg-reason').value,
      planned_date: document.getElementById('chg-date').value || null,
    };
    if (!body.title) { UI.toast('El titulo es obligatorio', 'error'); return; }
    try {
      if (id) await Api.patch(`/api/change-requests/${id}`, body);
      else await Api.post('/api/change-requests', body);
      UI.toast('Cambio guardado', 'success');
      document.querySelector('.modal-overlay')?.remove();
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  async function _detail(id) {
    const c = await Api.get(`/api/change-requests/${id}`);
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
    <div class="modal" style="max-width:500px;">
      <div class="modal-header">
        <h2>${UI.codePill(c.code)} ${UI.esc(c.title||'')}</h2>
        <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
      </div>
      <div class="modal-body">
        <p><strong>Estado:</strong> ${STATUS_LABELS[c.status]||c.status}</p>
        <p><strong>Tipo:</strong> ${c.change_type} | <strong>Impacto:</strong> <span style="color:${IMPACT_COLORS[c.risk_impact]||'#9D9D9D'}">${c.risk_impact}</span></p>
        <p><strong>Descripcion:</strong> ${UI.esc(c.description||'—')}</p>
        <p><strong>Razon:</strong> ${UI.esc(c.business_reason||'—')}</p>
        ${c.planned_date?`<p><strong>Fecha planificada:</strong> ${new Date(c.planned_date).toLocaleDateString('es-ES')}</p>`:''}
        ${c.implemented_at?`<p><strong>Implementado:</strong> ${new Date(c.implemented_at).toLocaleDateString('es-ES')}</p>`:''}
        <div style="display:flex;gap:6px;margin-top:14px;flex-wrap:wrap;">
          ${c.status==='draft'?`<button class="btn btn-secondary" onclick="ViewChangeRequests._action('submit',${id})">Enviar a revision</button>`:''}
          ${c.status==='under_review'?`<button class="btn btn-primary" onclick="ViewChangeRequests._action('approve',${id})">Aprobar</button>`:''}
          ${c.status==='under_review'?`<button class="btn btn-danger" onclick="ViewChangeRequests._action('reject',${id})">Rechazar</button>`:''}
          ${c.status==='approved'?`<button class="btn btn-primary" onclick="ViewChangeRequests._action('implement',${id})">Implementar</button>`:''}
          ${c.status==='implemented'?`<button class="btn btn-primary" onclick="ViewChangeRequests._action('verify',${id})">Verificar</button>`:''}
          ${c.status==='draft'?`<button class="btn btn-secondary" onclick="ViewChangeRequests._editFrom(${id})">Editar</button>`:''}
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _editFrom(id) {
    document.querySelector('.modal-overlay')?.remove();
    const c = await Api.get(`/api/change-requests/${id}`);
    _openForm(c);
  }

  async function _action(action, id) {
    let body = {};
    if (action === 'reject' || action === 'verify') {
      const r = prompt('Motivo / notas:') || '';
      body = { reason: r };
    }
    try {
      await Api.post(`/api/change-requests/${id}/${action}`, body);
      UI.toast('Accion realizada', 'success');
      document.querySelector('.modal-overlay')?.remove();
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  return { render, _detail, _action, _save, _editFrom };
})();
