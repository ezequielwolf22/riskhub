/* Vista de gestion de incidentes de seguridad (NIS2 / ISO 27001 A.16). */
const ViewIncidents = (() => {

  const SEVERITY_LABELS = {
    p1: 'Critico (P1)', p2: 'Alto (P2)', p3: 'Medio (P3)', p4: 'Bajo (P4)',
  };
  const STATUS_LABELS = {
    open: 'Abierto', investigating: 'En investigacion',
    contained: 'Contenido', resolved: 'Resuelto', closed: 'Cerrado',
  };
  const STATUS_COLORS = {
    open: 'var(--risk-critical)', investigating: 'var(--risk-high)',
    contained: 'var(--risk-medium)', resolved: 'var(--risk-low)', closed: 'var(--text-muted)',
  };
  const SEV_COLORS = {
    p1: 'var(--risk-critical)', p2: 'var(--risk-high)',
    p3: 'var(--risk-medium)', p4: 'var(--risk-low)',
  };

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Incidentes de Seguridad</h1>
          <p class="page-sub">Gestion de incidentes conforme a ISO 27001 A.16 y NIS2 Art. 23</p>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-primary" id="btn-new-incident">+ Nuevo incidente</button>
        </div>
      </div>

      <div class="stats-row" id="inc-stats" style="margin-bottom:16px;"></div>

      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <select id="f-status" class="input" style="width:160px;">
          <option value="">Todos los estados</option>
          <option value="open">Abierto</option>
          <option value="investigating">En investigacion</option>
          <option value="contained">Contenido</option>
          <option value="resolved">Resuelto</option>
          <option value="closed">Cerrado</option>
        </select>
        <select id="f-severity" class="input" style="width:160px;">
          <option value="">Todas las severidades</option>
          <option value="P1">Critico (P1)</option>
          <option value="P2">Alto (P2)</option>
          <option value="P3">Medio (P3)</option>
          <option value="P4">Bajo (P4)</option>
        </select>
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
          <input type="checkbox" id="f-nis2"> Solo NIS2 pendientes
        </label>
      </div>

      <div id="inc-table-wrap"></div>
    `;

    document.getElementById('btn-new-incident').onclick = () => _openForm(null);
    document.getElementById('f-status').onchange = _refresh;
    document.getElementById('f-severity').onchange = _refresh;
    document.getElementById('f-nis2').onchange = _refresh;

    await _loadStats();
    await _refresh();
  }

  async function _loadStats() {
    try {
      const s = await Api.incidents.summary();
      const wrap = document.getElementById('inc-stats');
      if (!wrap) return;
      wrap.innerHTML = `
        <div class="stat-card"><div class="stat-value">${s.total}</div><div class="stat-label">Total</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-high);">${s.open}</div><div class="stat-label">Abiertos</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-critical);">${s.p1_p2_open}</div><div class="stat-label">P1/P2 activos</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.nis2_pending_notification}</div><div class="stat-label">NIS2 pendientes</div></div>
      `;
    } catch (_) {}
  }

  async function _refresh() {
    const status = document.getElementById('f-status')?.value || '';
    const severity = document.getElementById('f-severity')?.value || '';
    const nis2 = document.getElementById('f-nis2')?.checked || false;
    const wrap = document.getElementById('inc-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<p class="text-muted">Cargando...</p>';
    try {
      const q = {};
      if (status) q.status = status;
      if (severity) q.severity = severity;
      if (nis2) q.nis2 = 'true';
      const data = await Api.incidents.list(q);
      _renderTable(wrap, data);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _renderTable(wrap, data) {
    if (!data.length) {
      wrap.innerHTML = '<p class="text-muted" style="margin-top:24px;text-align:center;">No se encontraron incidentes.</p>';
      return;
    }
    const rows = data.map(inc => `
      <tr>
        <td><b>${UI.esc(inc.code)}</b></td>
        <td>${UI.esc(inc.title)}</td>
        <td>${_badge(SEVERITY_LABELS[inc.severity] || inc.severity, SEV_COLORS[inc.severity] || '#888')}</td>
        <td>${_badge(STATUS_LABELS[inc.status] || inc.status, STATUS_COLORS[inc.status] || '#888')}</td>
        <td>${inc.nis2_notification_required ? (inc.nis2_notification_sent_at
          ? '<span style="color:var(--risk-low);font-size:11px;">Notificado</span>'
          : '<span style="color:var(--risk-critical);font-size:11px;font-weight:700;">Pendiente</span>')
          : '<span style="color:var(--text-muted);font-size:11px;">No</span>'}</td>
        <td>${inc.detected_at ? inc.detected_at.slice(0, 10) : '-'}</td>
        <td>
          <button class="btn btn-sm" data-id="${inc.id}" data-action="edit">Editar</button>
          <button class="btn btn-sm btn-danger" data-id="${inc.id}" data-action="del">Eliminar</button>
        </td>
      </tr>
    `).join('');

    wrap.innerHTML = `
      <table class="data">
        <thead>
          <tr>
            <th>Codigo</th><th>Titulo</th><th>Severidad</th><th>Estado</th>
            <th>NIS2</th><th>Detectado</th><th>Acciones</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;

    wrap.querySelectorAll('[data-action="edit"]').forEach(btn => {
      btn.onclick = async () => {
        const inc = data.find(i => i.id == btn.dataset.id);
        if (inc) _openForm(inc);
      };
    });
    wrap.querySelectorAll('[data-action="del"]').forEach(btn => {
      btn.onclick = async (ev) => {
        ev.stopPropagation();
        if (btn.disabled) return;
        if (!confirm('Eliminar incidente?')) return;
        btn.disabled = true;
        try {
          await Api.incidents.del(btn.dataset.id);
        } catch (e) {
          if (!e.status || e.status !== 404) {
            btn.disabled = false;
            UI.toast(e.message, 'error');
            return;
          }
        }
        UI.toast('Incidente eliminado', 'success');
        await _loadStats();
        await _refresh();
      };
    });
  }

  function _formHtml(inc) {
    const v = inc || {};
    return `
      <div class="form-grid">
        <div class="span2"><label>Titulo *</label><input id="f-title" class="input" value="${UI.esc(v.title || '')}"></div>
        <div><label>Severidad *</label>
          <select id="f-sev" class="input">
            ${['p1','p2','p3','p4'].map(s => `<option value="${s}" ${v.severity===s?'selected':''}>${SEVERITY_LABELS[s]}</option>`).join('')}
          </select>
        </div>
        <div><label>Estado</label>
          <select id="f-stat" class="input">
            ${Object.entries(STATUS_LABELS).map(([k,l]) => `<option value="${k}" ${v.status===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div class="span2"><label>Descripcion</label><textarea id="f-desc" class="input" rows="3">${UI.esc(v.description || '')}</textarea></div>
        <div><label>Fecha deteccion</label><input type="datetime-local" id="f-detected" class="input" value="${v.detected_at ? v.detected_at.slice(0,16) : ''}"></div>
        <div><label>Fecha notificacion NIS2</label><input type="datetime-local" id="f-nis2-sent" class="input" value="${v.nis2_notification_sent_at ? v.nis2_notification_sent_at.slice(0,16) : ''}"></div>
        <div class="span2" style="display:flex;align-items:center;gap:8px;">
          <input type="checkbox" id="f-nis2-req" ${v.nis2_notification_required?'checked':''}>
          <label for="f-nis2-req" style="margin:0;cursor:pointer;">Requiere notificacion NIS2 (Art. 23)</label>
        </div>
        <div class="span2"><label>Sistemas afectados (separados por coma)</label><input id="f-affected" class="input" value="${UI.esc((v.affected_systems || []).join(', '))}"></div>
        <div class="span2"><label>Causa raiz</label><textarea id="f-root" class="input" rows="2">${UI.esc(v.root_cause || '')}</textarea></div>
        <div class="span2"><label>Acciones de respuesta tomadas</label><textarea id="f-response" class="input" rows="2">${UI.esc(v.response_actions || '')}</textarea></div>
        <div class="span2"><label>Lecciones aprendidas</label><textarea id="f-lessons" class="input" rows="2">${UI.esc(v.lessons_learned || '')}</textarea></div>
      </div>
    `;
  }

  function _openForm(inc) {
    UI.modal(inc ? `Editar incidente ${inc.code}` : 'Nuevo incidente', _formHtml(inc), {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => _save(inc);
  }

  async function _save(inc) {
    const title = document.getElementById('f-title').value.trim();
    if (!title) { UI.toast('El titulo es obligatorio', 'error'); return; }
    const affectedRaw = document.getElementById('f-affected').value.trim();
    const payload = {
      title,
      severity: document.getElementById('f-sev').value,
      status: document.getElementById('f-stat').value,
      description: document.getElementById('f-desc').value.trim(),
      detected_at: document.getElementById('f-detected').value || null,
      nis2_notification_required: document.getElementById('f-nis2-req').checked,
      nis2_notification_sent_at: document.getElementById('f-nis2-sent').value || null,
      affected_systems: affectedRaw ? affectedRaw.split(',').map(s => s.trim()).filter(Boolean) : [],
      root_cause: document.getElementById('f-root').value.trim(),
      response_actions: document.getElementById('f-response').value.trim(),
      lessons_learned: document.getElementById('f-lessons').value.trim(),
    };
    try {
      if (inc) {
        await Api.incidents.update(inc.id, payload);
        UI.toast('Incidente actualizado', 'success');
      } else {
        await Api.incidents.create(payload);
        UI.toast('Incidente creado', 'success');
      }
      UI.closeModal();
      await _loadStats();
      await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  return { render };
})();
