/* Vista Auditoria Interna — ISO 27001 cl. 9.2. */
const ViewAudits = (() => {

  const AUDIT_TYPE_LABELS = {
    internal: 'Interna', external: 'Externa',
    surveillance: 'Seguimiento', recertification: 'Recertificacion',
  };
  const STATUS_LABELS = {
    planned: 'Planificada', in_progress: 'En curso',
    completed: 'Completada', cancelled: 'Cancelada',
  };
  const STATUS_COLORS = {
    planned: 'var(--brand-purple)', in_progress: 'var(--brand-orange)',
    completed: 'var(--risk-low)', cancelled: '#aaa',
  };
  const FINDING_TYPE_LABELS = {
    major_nc: 'NC Mayor', minor_nc: 'NC Menor',
    observation: 'Observacion', opportunity: 'Oportunidad', conformity: 'Conformidad',
  };
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
          <h1 class="page-title">Auditoria Interna</h1>
          <p class="page-sub">Programa de auditorias — ISO 27001 cl. 9.2</p>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-primary" id="btn-new-aud">+ Nueva auditoria</button>
        </div>
      </div>

      <div class="stats-row" id="aud-stats" style="margin-bottom:16px;"></div>
      <div id="aud-list"></div>
    `;

    document.getElementById('btn-new-aud').onclick = () => _openAuditForm(null);

    try {
      [_users, _nonconformities] = await Promise.all([
        Api.listUsers().catch(() => []),
        Api.nonconformities.list({}).catch(() => []),
      ]);
    } catch (_) {}

    await _loadStats();
    await _refresh();
  }

  async function _loadStats() {
    try {
      const s = await Api.audits.summary();
      const wrap = document.getElementById('aud-stats');
      if (!wrap) return;
      wrap.innerHTML = `
        <div class="stat-card"><div class="stat-value">${s.total_programs}</div><div class="stat-label">Auditorias</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.by_status.in_progress||0}</div><div class="stat-label">En curso</div></div>
        <div class="stat-card"><div class="stat-value">${s.total_findings}</div><div class="stat-label">Hallazgos</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-critical);">${s.open_major_ncs}</div><div class="stat-label">NC Mayores sin NC</div></div>
      `;
    } catch (_) {}
  }

  async function _refresh() {
    const list = document.getElementById('aud-list');
    if (!list) return;
    list.innerHTML = '<p class="text-muted">Cargando...</p>';
    try {
      const data = await Api.audits.list({});
      if (!data.length) {
        list.innerHTML = '<p class="text-muted" style="margin-top:24px;text-align:center;">No hay auditorias registradas.</p>';
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
            ${a.auditor_lead ? `<div style="font-size:12px;color:var(--text-muted);margin-top:3px;">Auditor lider: ${UI.esc(a.auditor_lead)}</div>` : ''}
          </div>
          <div style="text-align:right;font-size:12px;color:var(--text-muted);white-space:nowrap;">
            ${a.planned_start ? `<div>Inicio: ${a.planned_start.slice(0,10)}</div>` : ''}
            ${a.planned_end ? `<div>Fin: ${a.planned_end.slice(0,10)}</div>` : ''}
          </div>
        </div>
        ${a.findings && a.findings.length ? `
          <div style="display:flex;gap:8px;margin-top:10px;">
            ${ncMajor ? `${_badge(ncMajor + ' NC Mayor' + (ncMajor>1?'es':''), 'var(--risk-critical)')}` : ''}
            ${ncMinor ? `${_badge(ncMinor + ' NC Menor' + (ncMinor>1?'es':''), 'var(--risk-high)')}` : ''}
            ${obs ? `${_badge(obs + ' Observaci' + (obs>1?'ones':'on'), 'var(--brand-orange)')}` : ''}
          </div>` : ''}
      </div>`;
  }

  async function _openAuditDetail(id) {
    const data = await Api.audits.get(id);
    UI.modal(`${data.code} — ${data.title}`, `
      <div style="display:flex;flex-direction:column;gap:12px;">
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          ${_badge(AUDIT_TYPE_LABELS[data.audit_type]||data.audit_type, 'var(--brand-purple)')}
          ${_badge(STATUS_LABELS[data.status]||data.status, STATUS_COLORS[data.status]||'#888')}
        </div>
        ${data.scope ? `<div><strong>Alcance:</strong><br><span style="font-size:13px;">${UI.esc(data.scope)}</span></div>` : ''}
        ${data.objectives ? `<div><strong>Objetivos:</strong><br><span style="font-size:13px;">${UI.esc(data.objectives)}</span></div>` : ''}
        ${data.criteria ? `<div><strong>Criterios:</strong><br><span style="font-size:13px;">${UI.esc(data.criteria)}</span></div>` : ''}
        ${data.auditor_lead ? `<div style="font-size:13px;"><strong>Auditor lider:</strong> ${UI.esc(data.auditor_lead)}</div>` : ''}
        ${data.conclusion ? `<div style="background:var(--bg-2);border-radius:6px;padding:10px;"><strong>Conclusion:</strong><br><span style="font-size:13px;">${UI.esc(data.conclusion)}</span></div>` : ''}

        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <strong>Hallazgos (${(data.findings||[]).length})</strong>
            ${Auth.canEdit() ? `<button class="btn btn-sm btn-primary" id="btn-add-finding">+ Hallazgo</button>` : ''}
          </div>
          <div id="findings-list">
            ${(data.findings||[]).length ? (data.findings||[]).map(f => `
              <div style="padding:8px 12px;border:1px solid var(--border);border-radius:6px;margin-bottom:6px;background:var(--bg-2);">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
                  <div>
                    ${_badge(FINDING_TYPE_LABELS[f.finding_type]||f.finding_type, FINDING_TYPE_COLORS[f.finding_type]||'#888')}
                    ${f.iso_clause ? `<span style="font-size:11px;font-family:var(--font-mono);color:var(--text-muted);margin-left:6px;">${UI.esc(f.iso_clause)}</span>` : ''}
                  </div>
                  ${Auth.canEdit() ? `<button class="btn btn-sm btn-danger" data-del-finding="${f.id}" onclick="event.stopPropagation()">Eliminar</button>` : ''}
                </div>
                <div style="font-weight:600;font-size:13px;margin-top:4px;">${UI.esc(f.title)}</div>
                ${f.description ? `<div style="font-size:12px;color:var(--text-muted);margin-top:2px;">${UI.esc(f.description)}</div>` : ''}
                ${f.recommendation ? `<div style="font-size:12px;color:var(--brand-purple);margin-top:4px;">Recomendacion: ${UI.esc(f.recommendation)}</div>` : ''}
              </div>`).join('')
            : '<p style="font-size:13px;color:var(--text-muted);">Sin hallazgos registrados.</p>'}
          </div>
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="m-close-det">Cerrar</button>
                ${Auth.canEdit() ? `<button class="btn btn-ghost" id="m-edit-aud">Editar</button>` : ''}
                ${Auth.canEdit() ? `<button class="btn btn-danger" id="m-del-aud">Eliminar</button>` : ''}`
    });

    document.getElementById('m-close-det').onclick = UI.closeModal;

    if (Auth.canEdit()) {
      document.getElementById('m-edit-aud').onclick = () => { UI.closeModal(); _openAuditForm(data); };
      document.getElementById('m-del-aud').onclick = async () => {
        if (!confirm('Eliminar auditoria y todos sus hallazgos?')) return;
        try {
          await Api.audits.del(data.id);
          UI.toast('Auditoria eliminada', 'success');
          UI.closeModal(); await _loadStats(); await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };

      const btnAddFinding = document.getElementById('btn-add-finding');
      if (btnAddFinding) btnAddFinding.onclick = () => _openFindingForm(data.id);

      document.querySelectorAll('[data-del-finding]').forEach(btn => {
        btn.onclick = async (e) => {
          e.stopPropagation();
          if (!confirm('Eliminar hallazgo?')) return;
          try {
            await Api.audits.delFinding(data.id, btn.dataset.delFinding);
            UI.toast('Hallazgo eliminado', 'success');
            UI.closeModal(); _openAuditDetail(data.id);
          } catch (e2) { UI.toast(e2.message, 'error'); }
        };
      });
    }
  }

  function _openFindingForm(auditId) {
    UI.modal('Nuevo hallazgo', `
      <div class="form-grid">
        <div class="span2">
          <label>Tipo de hallazgo</label>
          <select id="ff-type" class="input">
            ${Object.entries(FINDING_TYPE_LABELS).map(([k,l]) => `<option value="${k}">${l}</option>`).join('')}
          </select>
        </div>
        <div class="span2"><label>Titulo *</label><input id="ff-title" class="input" placeholder="ej. No existe procedimiento documentado de backup"></div>
        <div><label>Clausula ISO</label><input id="ff-clause" class="input" placeholder="ej. 8.13 / A.12.3"></div>
        <div>
          <label>Vincular a NC existente</label>
          <select id="ff-nc" class="input">
            <option value="">— Crear NC por separado —</option>
            ${_nonconformities.map(nc => `<option value="${nc.id}">${UI.esc(nc.code)} — ${UI.esc(nc.title)}</option>`).join('')}
          </select>
        </div>
        <div class="span2"><label>Descripcion / evidencia</label><textarea id="ff-desc" class="input" rows="3"></textarea></div>
        <div class="span2"><label>Recomendacion</label><textarea id="ff-rec" class="input" rows="2"></textarea></div>
      </div>
    `, {
      actions: `<button class="btn" id="mf-cancel">Cancelar</button>
                <button class="btn btn-primary" id="mf-save">Guardar hallazgo</button>`
    });
    document.getElementById('mf-cancel').onclick = () => { UI.closeModal(); _openAuditDetail(auditId); };
    document.getElementById('mf-save').onclick = async () => {
      const title = document.getElementById('ff-title').value.trim();
      if (!title) { UI.toast('El titulo es obligatorio', 'error'); return; }
      const ncVal = document.getElementById('ff-nc').value;
      const payload = {
        finding_type: document.getElementById('ff-type').value,
        title,
        description: document.getElementById('ff-desc').value.trim(),
        evidence: '',
        iso_clause: document.getElementById('ff-clause').value.trim() || null,
        recommendation: document.getElementById('ff-rec').value.trim(),
        nonconformity_id: ncVal ? parseInt(ncVal) : null,
      };
      try {
        await Api.audits.createFinding(auditId, payload);
        UI.toast('Hallazgo registrado', 'success');
        UI.closeModal();
        await _loadStats(); await _refresh();
        _openAuditDetail(auditId);
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  function _auditFormHtml(a) {
    const v = a || {};
    return `
      <div class="form-grid">
        <div class="span2"><label>Titulo *</label><input id="fa-title" class="input" value="${UI.esc(v.title||'')}"></div>
        <div>
          <label>Tipo</label>
          <select id="fa-type" class="input">
            ${Object.entries(AUDIT_TYPE_LABELS).map(([k,l]) => `<option value="${k}" ${(v.audit_type||'internal')===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div>
          <label>Estado</label>
          <select id="fa-status" class="input">
            ${Object.entries(STATUS_LABELS).map(([k,l]) => `<option value="${k}" ${(v.status||'planned')===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div><label>Auditor lider</label><input id="fa-lead" class="input" value="${UI.esc(v.auditor_lead||'')}"></div>
        <div>
          <label>Responsable</label>
          <select id="fa-owner" class="input">
            <option value="">— Sin asignar —</option>
            ${_users.map(u => `<option value="${u.id}" ${v.owner_id===u.id?'selected':''}>${UI.esc(u.full_name||u.email)}</option>`).join('')}
          </select>
        </div>
        <div><label>Inicio planificado</label><input type="date" id="fa-start" class="input" value="${v.planned_start?v.planned_start.slice(0,10):''}"></div>
        <div><label>Fin planificado</label><input type="date" id="fa-end" class="input" value="${v.planned_end?v.planned_end.slice(0,10):''}"></div>
        <div class="span2"><label>Alcance</label><textarea id="fa-scope" class="input" rows="2">${UI.esc(v.scope||'')}</textarea></div>
        <div class="span2"><label>Objetivos</label><textarea id="fa-obj" class="input" rows="2">${UI.esc(v.objectives||'')}</textarea></div>
        <div class="span2"><label>Criterios (normas auditadas)</label><textarea id="fa-crit" class="input" rows="2">${UI.esc(v.criteria||'')}</textarea></div>
        <div class="span2"><label>Conclusion</label><textarea id="fa-concl" class="input" rows="3">${UI.esc(v.conclusion||'')}</textarea></div>
      </div>`;
  }

  function _openAuditForm(a) {
    UI.modal(a ? `Editar ${a.code}` : 'Nueva auditoria', _auditFormHtml(a), {
      actions: `<button class="btn" id="ma-cancel">Cancelar</button>
                <button class="btn btn-primary" id="ma-save">Guardar</button>`,
    });
    document.getElementById('ma-cancel').onclick = UI.closeModal;
    document.getElementById('ma-save').onclick = () => _saveAudit(a);
  }

  async function _saveAudit(a) {
    const title = document.getElementById('fa-title').value.trim();
    if (!title) { UI.toast('El titulo es obligatorio', 'error'); return; }
    const ownerVal = document.getElementById('fa-owner').value;
    const payload = {
      title,
      audit_type: document.getElementById('fa-type').value,
      status: document.getElementById('fa-status').value,
      auditor_lead: document.getElementById('fa-lead').value.trim() || null,
      owner_id: ownerVal ? parseInt(ownerVal) : null,
      planned_start: document.getElementById('fa-start').value || null,
      planned_end: document.getElementById('fa-end').value || null,
      scope: document.getElementById('fa-scope').value.trim(),
      objectives: document.getElementById('fa-obj').value.trim(),
      criteria: document.getElementById('fa-crit').value.trim(),
      conclusion: document.getElementById('fa-concl').value.trim(),
    };
    try {
      if (a) {
        await Api.audits.update(a.id, payload);
        UI.toast('Auditoria actualizada', 'success');
      } else {
        await Api.audits.create(payload);
        UI.toast('Auditoria creada', 'success');
      }
      UI.closeModal();
      await _loadStats(); await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  return { render };
})();
