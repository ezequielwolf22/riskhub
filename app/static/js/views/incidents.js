/* Vista de gestion de incidentes de seguridad (NIS2 / ISO 27001 A.16). */
const ViewIncidents = (() => {

  const SEVERITY_LABELS = {
    p1: t('incidents.severity.p1'), p2: t('incidents.severity.p2'), p3: t('incidents.severity.p3'), p4: t('incidents.severity.p4'),
  };
  const STATUS_LABELS = {
    open: t('incidents.status.open'), investigating: /* TODO: i18n */ 'En investigacion',
    contained: /* TODO: i18n */ 'Contenido', resolved: t('incidents.status.resolved'), closed: t('incidents.status.closed'),
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
          <h1 class="page-title">${t('incidents.title')}</h1>
          <p class="page-sub">${t('incidents.subtitle')}</p>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-primary" id="btn-new-incident">+ ${t('incidents.new')}</button>
        </div>
      </div>

      <div class="stats-row" id="inc-stats" style="margin-bottom:16px;"></div>

      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <select id="f-status" class="input" style="width:160px;">
          <option value="">${t('common.all')}</option>
          <option value="open">${t('incidents.status.open')}</option>
          <option value="investigating">/* TODO: i18n */ En investigacion</option>
          <option value="contained">/* TODO: i18n */ Contenido</option>
          <option value="resolved">${t('incidents.status.resolved')}</option>
          <option value="closed">${t('incidents.status.closed')}</option>
        </select>
        <select id="f-severity" class="input" style="width:160px;">
          <option value="">${t('common.all')}</option>
          <option value="P1">${t('incidents.severity.p1')}</option>
          <option value="P2">${t('incidents.severity.p2')}</option>
          <option value="P3">${t('incidents.severity.p3')}</option>
          <option value="P4">${t('incidents.severity.p4')}</option>
        </select>
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
          <input type="checkbox" id="f-nis2"> ${t('nis2.pending')} NIS2
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
        <div class="stat-card"><div class="stat-value">${s.total}</div><div class="stat-label">${t('common.total')}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-high);">${s.open}</div><div class="stat-label">${t('dashboard.open_incidents')}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-critical);">${s.p1_p2_open}</div><div class="stat-label">${t('dashboard.critical_incidents')}</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.nis2_pending_notification}</div><div class="stat-label">${t('dashboard.nis2_pending')}</div></div>
      `;
    } catch (_) {}
  }

  async function _refresh() {
    const status = document.getElementById('f-status')?.value || '';
    const severity = document.getElementById('f-severity')?.value || '';
    const nis2 = document.getElementById('f-nis2')?.checked || false;
    const wrap = document.getElementById('inc-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = `<p class="text-muted">${t('common.loading')}</p>`;
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
      wrap.innerHTML = `<p class="text-muted" style="margin-top:24px;text-align:center;">${t('common.no_results')}</p>`;
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
          <button class="btn btn-sm" data-id="${inc.id}" data-action="edit">${t('common.edit')}</button>
          <button class="btn btn-sm btn-danger" data-id="${inc.id}" data-action="del">${t('common.delete')}</button>
        </td>
      </tr>
    `).join('');

    wrap.innerHTML = `
      <table class="data">
        <thead>
          <tr>
            <th>${t('risks.risk_code')}</th><th>${t('common.title')}</th><th>${t('common.severity')}</th><th>${t('common.status')}</th>
            <th>NIS2</th><th>${t('incidents.detection_date')}</th><th>${t('common.actions')}</th>
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
        if (!confirm(t('incidents.delete_confirm'))) return;
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
        UI.toast(t('common.success'), 'success');
        await _loadStats();
        await _refresh();
      };
    });
  }

  function _formHtml(inc) {
    const v = inc || {};
    return `
      <div class="form-grid">
        <div class="span2"><label>${t('incidents.incident_name')} *</label><input id="f-title" class="input" value="${UI.esc(v.title || '')}"></div>
        <div><label>${t('common.severity')} *</label>
          <select id="f-sev" class="input">
            ${['p1','p2','p3','p4'].map(s => `<option value="${s}" ${v.severity===s?'selected':''}>${SEVERITY_LABELS[s]}</option>`).join('')}
          </select>
        </div>
        <div><label>${t('common.status')}</label>
          <select id="f-stat" class="input">
            ${Object.entries(STATUS_LABELS).map(([k,l]) => `<option value="${k}" ${v.status===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div class="span2"><label>${t('common.description')}</label><textarea id="f-desc" class="input" rows="3">${UI.esc(v.description || '')}</textarea></div>
        <div><label>${t('incidents.detection_date')}</label><input type="datetime-local" id="f-detected" class="input" value="${v.detected_at ? v.detected_at.slice(0,16) : ''}"></div>
        <div><label>${t('nis2.notification_deadline')}</label><input type="datetime-local" id="f-nis2-sent" class="input" value="${v.nis2_notification_sent_at ? v.nis2_notification_sent_at.slice(0,16) : ''}"></div>
        <div class="span2" style="display:flex;align-items:center;gap:8px;">
          <input type="checkbox" id="f-nis2-req" ${v.nis2_notification_required?'checked':''}>
          <label for="f-nis2-req" style="margin:0;cursor:pointer;">${t('incidents.nis2_notification')}</label>
        </div>
        <div class="span2" style="display:flex;align-items:center;gap:8px;padding:8px 10px;background:rgba(220,38,38,.06);border:1px solid rgba(220,38,38,.2);border-radius:6px;">
          <input type="checkbox" id="f-continuity" ${v.affects_continuity?'checked':''}>
          <div>
            <label for="f-continuity" style="margin:0;cursor:pointer;font-weight:600;">/* TODO: i18n */ Afecta a la continuidad del negocio</label>
            <div style="font-size:11px;color:var(--text-muted)">/* TODO: i18n */ Activa el modulo BCP — al guardar podras activar un plan de continuidad directamente.</div>
          </div>
        </div>
        <div class="span2"><label>${t('incidents.affected_assets')}</label><input id="f-affected" class="input" value="${UI.esc((v.affected_systems || []).join(', '))}"></div>
        <div class="span2"><label>${t('incidents.root_cause')}</label><textarea id="f-root" class="input" rows="2">${UI.esc(v.root_cause || '')}</textarea></div>
        <div class="span2"><label>/* TODO: i18n */ Acciones de respuesta tomadas</label><textarea id="f-response" class="input" rows="2">${UI.esc(v.response_actions || '')}</textarea></div>
        <div class="span2"><label>${t('incidents.lessons_learned')}</label><textarea id="f-lessons" class="input" rows="2">${UI.esc(v.lessons_learned || '')}</textarea></div>
      </div>
    `;
  }

  function _openForm(inc) {
    UI.modal(inc ? `${t('incidents.edit')} ${inc.code}` : t('incidents.new'), _formHtml(inc), {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => _save(inc);
  }

  async function _save(inc) {
    const title = document.getElementById('f-title').value.trim();
    if (!title) { UI.toast(t('incidents.incident_name') + ' ' + t('common.required'), 'error'); return; }
    const affectedRaw = document.getElementById('f-affected').value.trim();
    const affectsContinuity = document.getElementById('f-continuity')?.checked || false;
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
      affects_continuity: affectsContinuity,
    };
    try {
      let saved;
      if (inc) {
        saved = await Api.incidents.update(inc.id, payload);
        UI.toast(t('common.success'), 'success');
      } else {
        saved = await Api.incidents.create(payload);
        UI.toast(t('common.success'), 'success');
      }
      UI.closeModal();
      await _loadStats();
      await _refresh();
      // If affects continuity, offer redirect to BCP activation
      if (affectsContinuity && saved) {
        _offerBcpActivation(saved);
      }
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  function _offerBcpActivation(incident) {
    const modal = document.createElement('div');
    modal.className = 'modal-bg';
    modal.innerHTML = `
    <div class="modal" style="max-width:440px">
      <div class="modal-header" style="border-bottom:2px solid #DC2626">
        <h2 style="color:#DC2626"><i class="ti ti-alert-triangle"></i> Incidente de continuidad</h2>
        <button class="modal-close" onclick="this.closest('.modal-bg').remove()">&#xd7;</button>
      </div>
      <div class="modal-body" style="padding:20px 24px">
        <p style="font-size:13px;margin-bottom:16px">El incidente <strong>${UI.esc(incident.code)}</strong> esta marcado como que afecta a la continuidad del negocio.</p>
        <p style="font-size:13px;color:var(--text-muted)">¿Deseas ir al modulo BCP para activar un plan de continuidad vinculado a este incidente?</p>
      </div>
      <div class="modal-footer" style="display:flex;gap:8px;justify-content:flex-end;padding:12px 20px">
        <button class="btn btn-sm" onclick="this.closest('.modal-bg').remove()">Ahora no</button>
        <button class="btn btn-sm" style="background:#DC2626;color:#fff;border-color:#DC2626" id="go-bcp-btn">
          <i class="ti ti-alert-triangle"></i> Ir a activacion BCP
        </button>
      </div>
    </div>`;
    document.body.appendChild(modal);
    modal.querySelector('#go-bcp-btn').onclick = () => {
      modal.remove();
      // Navigate to BCP section - activaciones tile
      if (typeof App !== 'undefined' && App.navigate) {
        App.navigate('bcp');
      } else {
        window.location.hash = '#bcp';
      }
      // Small delay to let BCP view render, then open the activation modal with incident context
      setTimeout(() => {
        if (typeof ViewBcp !== 'undefined' && ViewBcp._modalActivacion) {
          ViewBcp._setTile?.('activaciones');
          // Store incident info for the activation modal
          window._pendingBcpIncidentId = incident.id;
          window._pendingBcpIncidentTitle = incident.title;
          ViewBcp._modalActivacion();
        }
      }, 400);
    };
  }

  return { render };
})();
