/* Vista GDPR — Registro Art. 30 y DPIA Art. 35. */
const ViewGdpr = (() => {

  const LEGAL_BASIS_LABELS = {
    consent: 'Consentimiento',
    contract: 'Contrato',
    legal_obligation: 'Obligacion legal',
    vital_interests: 'Intereses vitales',
    public_task: 'Tarea de interes publico',
    legitimate_interests: 'Intereses legitimos',
  };

  const DPIA_STATUS_LABELS = {
    pending: 'Pendiente',
    in_progress: 'En curso',
    completed: 'Completada',
    approved: 'Aprobada',
  };

  const DPIA_STATUS_COLORS = {
    pending: '#F59E0B',
    in_progress: '#3B82F6',
    completed: '#6B7280',
    approved: '#22C55E',
  };

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(String(label))}</span>`;
  }

  // ---- ESTADO ----
  let _activeTab = 'activities';
  let _users = [];

  async function render(el) {
    _users = await Api.listUsers().catch(() => []);

    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Privacidad y Proteccion de Datos</h1>
          <p class="page-sub">RGPD Art. 30 — Registro de actividades &nbsp;|&nbsp; RGPD Art. 35 — DPIA</p>
        </div>
      </div>
      <div class="stats-row" id="gdpr-stats" style="margin-bottom:16px;"></div>
      <div style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:20px;">
        <button class="tab-btn" id="tab-activities" onclick="ViewGdprTab('activities')">
          Registro de actividades (Art. 30)
        </button>
        <button class="tab-btn" id="tab-dpias" onclick="ViewGdprTab('dpias')">
          DPIA — Evaluaciones de impacto (Art. 35)
        </button>
      </div>
      <div id="gdpr-tab-content"></div>
    `;

    await _loadStats();
    _setTab(_activeTab);
  }

  window.ViewGdprTab = function(tab) { _setTab(tab); };

  function _setTab(tab) {
    _activeTab = tab;
    ['activities','dpias'].forEach(t => {
      const btn = document.getElementById('tab-' + t);
      if (!btn) return;
      btn.style.cssText = `padding:8px 20px;font-size:13px;font-weight:600;border:none;
        background:none;cursor:pointer;border-bottom:3px solid ${t===tab?'var(--brand-purple)':'transparent'};
        color:${t===tab?'var(--brand-purple)':'var(--text-muted)'};margin-bottom:-2px;`;
    });
    if (tab === 'activities') _renderActivities();
    else _renderDpias();
  }

  async function _loadStats() {
    try {
      const s = await Api.gdpr.summary();
      const wrap = document.getElementById('gdpr-stats');
      if (!wrap) return;
      wrap.innerHTML = `
        <div class="stat-card"><div class="stat-value">${s.total_activities}</div><div class="stat-label">Actividades registradas</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.requires_dpia}</div><div class="stat-label">Requieren DPIA</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-high);">${s.transfers_outside_eu}</div><div class="stat-label">Transferencias fuera UE</div></div>
        <div class="stat-card"><div class="stat-value">${s.total_dpias}</div><div class="stat-label">DPIAs totales</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-medium);">${s.dpias_pending}</div><div class="stat-label">DPIAs pendientes</div></div>
      `;
    } catch (_) {}
  }

  // ======== ACTIVITIES ========

  async function _renderActivities() {
    const wrap = document.getElementById('gdpr-tab-content');
    wrap.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">
        <input id="act-q" class="input" placeholder="Buscar actividad..." style="width:220px;">
        <select id="act-dpia" class="input" style="width:180px;">
          <option value="">Todas</option>
          <option value="true">Requiere DPIA</option>
          <option value="false">Sin DPIA requerida</option>
        </select>
        ${Auth.canEdit() ? '<button class="btn btn-primary" id="btn-new-act">+ Nueva actividad</button>' : ''}
      </div>
      <div id="act-list">Cargando...</div>
    `;
    if (Auth.canEdit()) document.getElementById('btn-new-act').onclick = () => _editActivity(null);
    let debounce;
    document.getElementById('act-q').oninput = () => { clearTimeout(debounce); debounce = setTimeout(_reloadAct, 300); };
    document.getElementById('act-dpia').onchange = _reloadAct;
    await _reloadAct();
  }

  async function _reloadAct() {
    const q = document.getElementById('act-q')?.value.trim();
    const dpia = document.getElementById('act-dpia')?.value;
    const params = {};
    if (q) params.q = q;
    if (dpia !== '') params.requires_dpia = dpia;
    const wrap = document.getElementById('act-list');
    if (!wrap) return;
    try {
      const data = await Api.gdpr.activities.list(params);
      if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);margin-top:24px;text-align:center;">Sin actividades de tratamiento registradas.</p>';
        return;
      }
      wrap.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          <th>Codigo</th><th>Actividad</th><th>Base legal</th><th>Requiere DPIA</th><th>Transferencia UE</th><th>Responsable</th><th></th>
        </tr></thead>
        <tbody>
          ${data.map(a => {
            const owner = _users.find(u => u.id === a.owner_id);
            const ownerName = owner ? (owner.full_name || owner.email) : '-';
            return `<tr>
              <td>${UI.codePill(a.code)}</td>
              <td><strong>${UI.esc(a.title)}</strong></td>
              <td>${UI.esc(LEGAL_BASIS_LABELS[a.legal_basis] || a.legal_basis || '-')}</td>
              <td>${a.requires_dpia ? _badge('Si','#EF4444') : _badge('No','#6B7280')}</td>
              <td>${a.transfers_outside_eu ? _badge('Si','#F59E0B') : _badge('No','#6B7280')}</td>
              <td style="font-size:12px;color:var(--text-muted);">${UI.esc(ownerName)}</td>
              <td>
                <button class="btn btn-sm" data-id="${a.id}" data-act="view">Ver</button>
                ${Auth.canEdit() ? `<button class="btn btn-sm btn-danger" data-id="${a.id}" data-act="del">Eliminar</button>` : ''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
      wrap.querySelectorAll('[data-act="view"]').forEach(btn => {
        btn.onclick = () => {
          const a = data.find(x => x.id == btn.dataset.id);
          if (a) _editActivity(a);
        };
      });
      wrap.querySelectorAll('[data-act="del"]').forEach(btn => {
        btn.onclick = async () => {
          if (!await UI.confirm('Eliminar esta actividad de tratamiento?')) return;
          try { await Api.gdpr.activities.del(btn.dataset.id); UI.toast('Eliminada','success'); _reloadAct(); _loadStats(); }
          catch (e) { UI.toast(e.message,'error'); }
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  function _editActivity(a) {
    const isNew = !a;
    const v = a || {};
    UI.modal(isNew ? 'Nueva actividad de tratamiento' : `${v.code} — ${v.title}`, `
      <div><label>Titulo *</label><input id="fa-title" value="${UI.esc(v.title||'')}"></div>
      <div><label>Base legal</label>
        <select id="fa-legal">
          ${Object.entries(LEGAL_BASIS_LABELS).map(([k,l]) => `<option value="${k}" ${v.legal_basis===k?'selected':''}>${l}</option>`).join('')}
        </select>
      </div>
      <div class="span2"><label>Finalidades del tratamiento</label>
        <textarea id="fa-purposes" rows="2">${UI.esc(v.purposes||'')}</textarea></div>
      <div class="span2"><label>Categorias de datos personales tratados</label>
        <textarea id="fa-cats" rows="2">${UI.esc(Array.isArray(v.data_categories) ? v.data_categories.join(', ') : (v.data_categories||''))}</textarea></div>
      <div><label>Categorias de interesados</label>
        <input id="fa-subjects" value="${UI.esc(Array.isArray(v.data_subjects) ? v.data_subjects.join(', ') : (v.data_subjects||''))}"></div>
      <div><label>Destinatarios</label>
        <input id="fa-recipients" value="${UI.esc(Array.isArray(v.recipients) ? v.recipients.join(', ') : (v.recipients||''))}"></div>
      <div><label>Periodo de retencion</label>
        <input id="fa-retention" value="${UI.esc(v.retention_period||'')}" placeholder="ej. 5 anos, indefinido..."></div>
      <div><label>Responsable del tratamiento</label>
        <select id="fa-owner">
          <option value="">- Sin asignar -</option>
          ${_users.map(u => `<option value="${u.id}" ${v.owner_id===u.id?'selected':''}>${UI.esc(u.full_name||u.email)}</option>`).join('')}
        </select>
      </div>
      <div><label>Nombre del controlador</label>
        <input id="fa-controller" value="${UI.esc(v.controller_name||'')}"></div>
      <div><label>Contacto DPO</label>
        <input id="fa-dpo" value="${UI.esc(v.dpo_contact||'')}"></div>
      <div><label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
        <input type="checkbox" id="fa-dpia" ${v.requires_dpia?'checked':''}> Requiere DPIA (Art. 35)
      </label></div>
      <div><label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
        <input type="checkbox" id="fa-eu" ${v.transfers_outside_eu?'checked':''}> Transferencias fuera de la UE
      </label></div>
      <div class="span2"><label>Garantias para transferencias internacionales</label>
        <input id="fa-safeguards" value="${UI.esc(v.transfer_safeguards||'')}"></div>
      <div class="span2"><label>Medidas de seguridad tecnicas/organizativas</label>
        <textarea id="fa-security" rows="2">${UI.esc(v.security_measures||'')}</textarea></div>
    `, {
      actions: Auth.canEdit() ? `
        <button class="btn" id="m-cancel">Cancelar</button>
        <button class="btn btn-primary" id="m-save">Guardar</button>
      ` : '<button class="btn" id="m-cancel">Cerrar</button>'
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    if (!Auth.canEdit()) return;
    document.getElementById('m-save').onclick = async () => {
      const title = document.getElementById('fa-title').value.trim();
      if (!title) { UI.toast('El titulo es obligatorio','error'); return; }
      const body = {
        title,
        legal_basis: document.getElementById('fa-legal').value,
        purposes: document.getElementById('fa-purposes').value.trim(),
        data_categories: document.getElementById('fa-cats').value.trim(),
        data_subjects: document.getElementById('fa-subjects').value.trim(),
        recipients: document.getElementById('fa-recipients').value.trim(),
        retention_period: document.getElementById('fa-retention').value.trim(),
        controller_name: document.getElementById('fa-controller').value.trim(),
        dpo_contact: document.getElementById('fa-dpo').value.trim(),
        security_measures: document.getElementById('fa-security').value.trim(),
        transfer_safeguards: document.getElementById('fa-safeguards').value.trim(),
        requires_dpia: document.getElementById('fa-dpia').checked,
        transfers_outside_eu: document.getElementById('fa-eu').checked,
        owner_id: document.getElementById('fa-owner').value ? parseInt(document.getElementById('fa-owner').value) : null,
      };
      try {
        if (isNew) await Api.gdpr.activities.create(body);
        else await Api.gdpr.activities.update(a.id, body);
        UI.closeModal(); UI.toast('Guardado','success'); _reloadAct(); _loadStats();
      } catch (e) { UI.toast(e.message,'error'); }
    };
  }

  // ======== DPIAs ========

  async function _renderDpias() {
    const wrap = document.getElementById('gdpr-tab-content');

    // Cargar actividades para el selector
    let activities = [];
    try { activities = await Api.gdpr.activities.list(); } catch (_) {}

    wrap.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">
        <select id="dpia-act-filter" class="input" style="width:240px;">
          <option value="">Todas las actividades</option>
          ${activities.map(a => `<option value="${a.id}">${UI.esc(a.code)} - ${UI.esc(a.title)}</option>`).join('')}
        </select>
        ${Auth.canEdit() ? `<button class="btn btn-primary" id="btn-new-dpia">+ Nueva DPIA</button>` : ''}
      </div>
      <div id="dpia-list">Cargando...</div>
    `;
    if (Auth.canEdit()) document.getElementById('btn-new-dpia').onclick = () => _editDpia(null, activities);
    document.getElementById('dpia-act-filter').onchange = _reloadDpias;
    await _reloadDpias(activities);
  }

  async function _reloadDpias(activities) {
    const actId = document.getElementById('dpia-act-filter')?.value;
    const params = {};
    if (actId) params.activity_id = actId;
    const wrap = document.getElementById('dpia-list');
    if (!wrap) return;
    try {
      const data = await Api.gdpr.dpias.list(params);
      let acts = activities;
      if (!acts) { try { acts = await Api.gdpr.activities.list(); } catch (_) { acts = []; } }
      if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);margin-top:24px;text-align:center;">Sin DPIAs registradas.</p>';
        return;
      }
      wrap.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          <th>Codigo</th><th>Titulo</th><th>Actividad</th><th>Nivel riesgo residual</th><th>Estado</th><th>Revisada</th><th></th>
        </tr></thead>
        <tbody>
          ${data.map(d => {
            const act = acts.find(a => a.id === d.activity_id);
            const statusColor = DPIA_STATUS_COLORS[d.status] || '#6B7280';
            const reviewed = d.reviewed_at ? new Date(d.reviewed_at).toLocaleDateString('es-ES') : '-';
            return `<tr>
              <td>${UI.codePill(d.code)}</td>
              <td><strong>${UI.esc(d.title)}</strong></td>
              <td style="font-size:12px;color:var(--text-muted);">${act ? UI.esc(act.title) : '-'}</td>
              <td>${d.residual_risk_level ? UI.riskPill(d.residual_risk_level) : '-'}</td>
              <td>${_badge(DPIA_STATUS_LABELS[d.status]||d.status, statusColor)}</td>
              <td style="font-size:12px;">${reviewed}</td>
              <td>
                <button class="btn btn-sm" data-id="${d.id}" data-act="view">Ver</button>
                ${Auth.canEdit() ? `<button class="btn btn-sm btn-danger" data-id="${d.id}" data-act="del">Eliminar</button>` : ''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
      wrap.querySelectorAll('[data-act="view"]').forEach(btn => {
        btn.onclick = () => {
          const d = data.find(x => x.id == btn.dataset.id);
          if (d) _editDpia(d, acts);
        };
      });
      wrap.querySelectorAll('[data-act="del"]').forEach(btn => {
        btn.onclick = async () => {
          if (!await UI.confirm('Eliminar esta DPIA?')) return;
          try { await Api.gdpr.dpias.del(btn.dataset.id); UI.toast('Eliminada','success'); _reloadDpias(); _loadStats(); }
          catch (e) { UI.toast(e.message,'error'); }
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  function _editDpia(d, activities) {
    const isNew = !d;
    const v = d || {};
    UI.modal(isNew ? 'Nueva DPIA' : `${v.code} — ${v.title}`, `
      <div class="span2"><label>Titulo *</label><input id="fd-title" value="${UI.esc(v.title||'')}"></div>
      <div><label>Actividad de tratamiento *</label>
        <select id="fd-activity">
          <option value="">- Seleccionar -</option>
          ${(activities||[]).map(a => `<option value="${a.id}" ${v.activity_id===a.id?'selected':''}>${UI.esc(a.code)} - ${UI.esc(a.title)}</option>`).join('')}
        </select>
      </div>
      <div><label>Responsable</label>
        <select id="fd-owner">
          <option value="">- Sin asignar -</option>
          ${_users.map(u => `<option value="${u.id}" ${v.owner_id===u.id?'selected':''}>${UI.esc(u.full_name||u.email)}</option>`).join('')}
        </select>
      </div>
      <div class="span2"><label>Evaluacion de necesidad y proporcionalidad</label>
        <textarea id="fd-necessity" rows="3">${UI.esc(v.necessity_assessment||'')}</textarea></div>
      <div class="span2"><label>Riesgos identificados para los derechos de los interesados</label>
        <textarea id="fd-risks" rows="3">${UI.esc(v.risks_identified||'')}</textarea></div>
      <div class="span2"><label>Medidas previstas para tratar los riesgos</label>
        <textarea id="fd-measures" rows="3">${UI.esc(v.risk_measures||'')}</textarea></div>
      <div><label>Nivel de riesgo residual (0-8)</label>
        <input type="number" min="0" max="8" id="fd-residual" value="${v.residual_risk_level||''}"></div>
      <div><label>Estado</label>
        <select id="fd-status">
          <option value="pending" ${(v.status||'pending')==='pending'?'selected':''}>Pendiente</option>
              <option value="in_progress" ${v.status==='in_progress'?'selected':''}>En curso</option>
              <option value="completed" ${v.status==='completed'?'selected':''}>Completada</option>
              <option value="approved" ${v.status==='approved'?'selected':''}>Aprobada</option>
        </select>
      </div>
      <div class="span2"><label>Opinion del DPO</label>
        <textarea id="fd-dpo" rows="2">${UI.esc(v.dpo_opinion||'')}</textarea></div>
      ${!isNew && v.reviewed_at ? `
        <div class="span2 notice">
          Aprobada el ${new Date(v.reviewed_at).toLocaleString('es-ES')}
          ${v.approved_by_id ? ` por ${UI.esc((_users.find(u=>u.id===v.approved_by_id)||{}).full_name||'')}` : ''}
        </div>` : ''}
    `, {
      actions: Auth.canEdit() ? `
        <button class="btn" id="m-cancel">Cancelar</button>
        <button class="btn btn-primary" id="m-save">Guardar</button>
      ` : '<button class="btn" id="m-cancel">Cerrar</button>'
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    if (!Auth.canEdit()) return;
    document.getElementById('m-save').onclick = async () => {
      const title = document.getElementById('fd-title').value.trim();
      const actId = document.getElementById('fd-activity').value;
      if (!title) { UI.toast('El titulo es obligatorio','error'); return; }
      if (isNew && !actId) { UI.toast('Selecciona una actividad de tratamiento','error'); return; }
      const residualVal = document.getElementById('fd-residual').value;
      const body = {
        title,
        necessity_assessment: document.getElementById('fd-necessity').value.trim(),
        risks_identified: document.getElementById('fd-risks').value.trim(),
        risk_measures: document.getElementById('fd-measures').value.trim(),
        residual_risk_level: residualVal !== '' ? parseInt(residualVal) : null,
        dpo_opinion: document.getElementById('fd-dpo').value.trim(),
        status: document.getElementById('fd-status').value,
        owner_id: document.getElementById('fd-owner').value ? parseInt(document.getElementById('fd-owner').value) : null,
      };
      if (isNew) body.activity_id = parseInt(actId);
      try {
        if (isNew) await Api.gdpr.dpias.create(body);
        else await Api.gdpr.dpias.update(d.id, body);
        UI.closeModal(); UI.toast('Guardado','success'); _reloadDpias(); _loadStats();
      } catch (e) { UI.toast(e.message,'error'); }
    };
  }

  return { render };
})();
