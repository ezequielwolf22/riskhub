/* Change Management — ISO 27001 cl. 6.3 */
const ViewChangeRequests = (() => {

  const STATUS_LABELS = {
    draft: 'Borrador', under_review: 'En revision', approved: 'Aprobado',
    rejected: 'Rechazado', implemented: 'Implementado', verified: 'Verificado',
  };
  const IMPACT_COLORS = { none: '#9D9D9D', low: '#16a34a', medium: '#D97706', high: '#DC2626' };
  const TYPE_LABELS = {
    policy: 'Politica', control: 'Control', asset: 'Activo',
    process: 'Proceso', infrastructure: 'Infraestructura', other: 'Otro',
  };

  let _wrap = null;

  async function render(container) {
    container.innerHTML = UI.sectionHeader(
      'Gestion de Cambios',
      'ISO 27001 cl. 6.3 — Control de cambios planificados en el SGSI',
      `<button class="btn btn-primary" id="btn-new-chg">+ Nuevo cambio</button>`
    );
    _wrap = document.createElement('div');
    container.appendChild(_wrap);
    document.getElementById('btn-new-chg').addEventListener('click', () => _openForm(null));
    await _load();
  }

  async function _load() {
    if (!_wrap) return;
    _wrap.innerHTML = '<p class="text-muted" style="margin-top:24px;">Cargando...</p>';
    try {
      const changes = await Api.get('/api/change-requests');
      if (!changes.length) {
        _wrap.innerHTML = UI.emptyState('Sin solicitudes de cambio', 'Registra cambios en politicas, controles o activos para mantener trazabilidad.');
        return;
      }
      const statuses = ['draft', 'under_review', 'approved', 'implemented', 'verified'];
      const byStatus = {};
      statuses.concat(['rejected']).forEach(s => { byStatus[s] = []; });
      changes.forEach(c => { if (byStatus[c.status] !== undefined) byStatus[c.status].push(c); });

      let html = `<div style="overflow-x:auto;margin-top:16px;">
        <div style="display:grid;grid-template-columns:repeat(5,minmax(180px,1fr));gap:10px;min-width:820px;">`;
      statuses.forEach(s => {
        html += `<div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:10px;">
          <div style="font-weight:700;font-size:12px;margin-bottom:8px;color:var(--text-muted);">
            ${STATUS_LABELS[s]} (${byStatus[s].length})
          </div>`;
        byStatus[s].forEach(c => {
          html += `<div class="card" style="margin-bottom:8px;padding:10px;cursor:pointer;"
                        onclick="ViewChangeRequests._detail(${c.id})">
            <div style="margin-bottom:4px;">${UI.codePill(c.code)}</div>
            <div style="font-size:12px;font-weight:600;margin-bottom:6px;">${UI.esc((c.title || '').substring(0, 50))}</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
              <span style="font-size:10px;background:var(--bg-3);padding:2px 6px;border-radius:4px;">
                ${TYPE_LABELS[c.change_type] || c.change_type}
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
            Rechazados (${byStatus.rejected.length})
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
    UI.modal(chg ? `Editar ${chg.code}` : 'Nueva solicitud de cambio', `
      <div class="form-grid">
        <div class="span2">
          <label>Titulo *</label>
          <input id="chg-title" class="input" value="${UI.esc(chg?.title || '')}">
        </div>
        <div>
          <label>Tipo de cambio</label>
          <select id="chg-type" class="input">
            ${Object.entries(TYPE_LABELS).map(([k, v]) =>
              `<option value="${k}" ${chg?.change_type === k ? 'selected' : ''}>${v}</option>`
            ).join('')}
          </select>
        </div>
        <div>
          <label>Impacto en riesgo</label>
          <select id="chg-impact" class="input">
            <option value="none" ${chg?.risk_impact === 'none' ? 'selected' : ''}>Sin impacto</option>
            <option value="low" ${chg?.risk_impact === 'low' ? 'selected' : ''}>Bajo</option>
            <option value="medium" ${chg?.risk_impact === 'medium' ? 'selected' : ''}>Medio</option>
            <option value="high" ${chg?.risk_impact === 'high' ? 'selected' : ''}>Alto</option>
          </select>
        </div>
        <div class="span2">
          <label>Descripcion</label>
          <textarea id="chg-desc" class="input" rows="3">${UI.esc(chg?.description || '')}</textarea>
        </div>
        <div class="span2">
          <label>Razon de negocio</label>
          <textarea id="chg-reason" class="input" rows="2">${UI.esc(chg?.business_reason || '')}</textarea>
        </div>
        <div>
          <label>Fecha planificada</label>
          <input id="chg-date" class="input" type="datetime-local"
                 value="${chg?.planned_date ? chg.planned_date.replace('Z', '') : ''}">
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="mc-cancel">Cancelar</button>
                <button class="btn btn-primary" id="mc-save">Guardar</button>`,
    });
    document.getElementById('mc-cancel').onclick = UI.closeModal;
    document.getElementById('mc-save').onclick = () => _save(chg?.id || null);
  }

  async function _save(id) {
    const title = document.getElementById('chg-title').value.trim();
    if (!title) { UI.toast('El titulo es obligatorio', 'error'); return; }
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
        UI.toast('Cambio actualizado', 'success');
      } else {
        await Api.post('/api/change-requests', body);
        UI.toast('Cambio registrado', 'success');
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

    UI.modal(`${UI.codePill(c.code)} ${UI.esc(c.title || '')}`, `
      <div style="display:flex;flex-direction:column;gap:10px;">
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <span style="background:var(--brand-purple);color:#fff;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;">
            ${STATUS_LABELS[c.status] || c.status}
          </span>
          <span style="background:var(--bg-3);padding:2px 10px;border-radius:999px;font-size:12px;">
            ${TYPE_LABELS[c.change_type] || c.change_type}
          </span>
          <span style="color:${IMPACT_COLORS[c.risk_impact] || '#9D9D9D'};font-size:12px;font-weight:600;">
            Impacto: ${c.risk_impact}
          </span>
        </div>
        ${c.description ? `<div><strong style="font-size:12px;">Descripcion:</strong><p style="font-size:13px;margin:4px 0 0;">${UI.esc(c.description)}</p></div>` : ''}
        ${c.business_reason ? `<div><strong style="font-size:12px;">Razon de negocio:</strong><p style="font-size:13px;margin:4px 0 0;">${UI.esc(c.business_reason)}</p></div>` : ''}
        ${c.planned_date ? `<div style="font-size:13px;"><strong>Fecha planificada:</strong> ${new Date(c.planned_date).toLocaleDateString('es-ES')}</div>` : ''}
        ${c.implemented_at ? `<div style="font-size:13px;"><strong>Implementado:</strong> ${new Date(c.implemented_at).toLocaleDateString('es-ES')}</div>` : ''}
        ${c.verification_notes ? `<div><strong style="font-size:12px;">Notas de verificacion:</strong><p style="font-size:13px;margin:4px 0 0;">${UI.esc(c.verification_notes)}</p></div>` : ''}
      </div>
    `, {
      actions: `
        <button class="btn" id="md-close">Cerrar</button>
        ${c.status === 'draft' ? `<button class="btn btn-ghost" id="md-edit">Editar</button>` : ''}
        ${c.status === 'draft' ? `<button class="btn btn-secondary" id="md-submit">Enviar a revision</button>` : ''}
        ${c.status === 'under_review' ? `<button class="btn btn-danger" id="md-reject">Rechazar</button>` : ''}
        ${c.status === 'under_review' ? `<button class="btn btn-primary" id="md-approve">Aprobar</button>` : ''}
        ${c.status === 'approved' ? `<button class="btn btn-primary" id="md-implement">Implementar</button>` : ''}
        ${c.status === 'implemented' ? `<button class="btn btn-primary" id="md-verify">Verificar</button>` : ''}
      `,
    });

    document.getElementById('md-close').onclick = UI.closeModal;
    document.getElementById('md-edit')?.onclick = () => { UI.closeModal(); _openForm(c); };
    document.getElementById('md-submit')?.onclick = () => _action('submit', id);
    document.getElementById('md-approve')?.onclick = () => _action('approve', id);
    document.getElementById('md-reject')?.onclick = () => _action('reject', id);
    document.getElementById('md-implement')?.onclick = () => _action('implement', id);
    document.getElementById('md-verify')?.onclick = () => _action('verify', id);
  }

  async function _action(action, id) {
    let body = {};
    if (action === 'reject' || action === 'verify') {
      const r = prompt(action === 'reject' ? 'Motivo del rechazo:' : 'Notas de verificacion:') || '';
      body = { reason: r };
    }
    try {
      await Api.post(`/api/change-requests/${id}/${action}`, body);
      UI.toast('Accion realizada correctamente', 'success');
      UI.closeModal();
      await _load();
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  }

  return { render, _detail, _action, _save };
})();
