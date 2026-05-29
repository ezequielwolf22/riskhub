/* Vista Alertas — Reglas de alerta por email. */
const ViewAlerts = {

  _settings: null,
  _rules: [],

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      'Alertas por email',
      'Reglas de notificacion automatica de riesgos'
    ) + '<div id="alerts-content"></div>';
    await this._load();
  },

  async _load() {
    const c = document.getElementById('alerts-content');
    try {
      const [settings, rules] = await Promise.all([
        Api.get('/api/alerts/settings'),
        Api.get('/api/alerts/rules'),
      ]);
      this._settings = settings;
      this._rules = rules || [];
      this._render(c);
    } catch (e) {
      c.innerHTML = UI.notice('Error al cargar la configuracion: ' + UI.esc(e.message), 'error');
    }
  },

  _render(container) {
    const u = Auth.user();
    const isAnalyst = u && (u.role === 'admin' || u.role === 'superadmin' || u.role === 'analyst');

    const s = this._settings || {};
    const smtpOk = !!s.smtp_host;
    const smtpBadge = smtpOk
      ? `<span class="badge badge-muted" style="background:#D1FAE5;color:#065F46;">SMTP configurado</span>`
      : `<span class="badge badge-muted" style="background:#FEF3C7;color:#92400E;">SMTP sin configurar</span>`;

    container.innerHTML = `
      <!-- Estado SMTP -->
      <div class="card" style="margin-bottom:16px;display:flex;align-items:center;gap:16px;padding:14px 20px;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
        <div style="flex:1;">
          <span style="font-size:13px;font-weight:600;">Servidor de correo (SMTP)</span>
          <span style="margin-left:10px;">${smtpBadge}</span>
          ${smtpOk ? `<div style="font-size:12px;color:var(--text-muted);margin-top:2px;">${UI.esc(s.smtp_host)}:${s.smtp_port} &mdash; ${UI.esc(s.smtp_from || '')}</div>` : ''}
        </div>
        <button class="btn btn-sm" onclick="App.navigate('integrations')">
          Configurar SMTP
        </button>
        ${smtpOk ? `<button class="btn btn-sm" onclick="ViewAlerts._testEmail()">Enviar prueba</button>` : ''}
      </div>

      <!-- Reglas -->
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="margin:0;">Reglas de alerta (${this._rules.length})</h3>
          <div style="display:flex;gap:8px;">
            ${isAnalyst ? `<button class="btn btn-sm" onclick="ViewAlerts._checkRules()">
              Evaluar reglas ahora</button>
            <button class="btn btn-sm btn-primary" onclick="ViewAlerts._newRule()">
              + Nueva regla</button>` : ''}
          </div>
        </div>
        ${this._rules.length === 0
          ? `<p style="color:var(--text-muted);font-size:13px;margin:0;">
               No hay reglas configuradas. Crea una regla para empezar a recibir alertas automaticas.</p>`
          : `<div style="overflow-x:auto;">
              <table class="data">
                <thead><tr>
                  <th>Nombre</th><th>Evento</th><th>Umbral</th>
                  <th>Destinatario</th><th>Ultimo envio</th>
                  <th style="width:90px;">Estado</th>
                  <th style="width:60px;"></th>
                </tr></thead>
                <tbody id="rules-tbody">
                  ${this._rules.map(r => this._ruleRow(r)).join('')}
                </tbody>
              </table>
            </div>`}
      </div>

      <!-- Alerta manual -->
      <div class="card">
        <h3 style="margin-bottom:16px;">Alerta manual de riesgo</h3>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px;">
          Envía una alerta puntual para un riesgo específico a cualquier destinatario.
        </p>
        <div class="modal-body">
          <div><label>Codigo de riesgo (ID numerico)</label>
            <input id="alert-risk-id" type="number" placeholder="Ej: 3" style="width:100%;"></div>
          <div><label>Destinatario</label>
            <input id="alert-recipient" type="email" placeholder="responsable@company.com" style="width:100%;"></div>
          <div class="span2"><label>Motivo</label>
            <input id="alert-reason" type="text" placeholder="Ej: Nuevo análisis de riesgo disponible" style="width:100%;"></div>
        </div>
        <div style="text-align:right;margin-top:12px;">
          <button class="btn btn-primary" onclick="ViewAlerts._sendManual()">Enviar alerta</button>
        </div>
      </div>`;
  },

  // Ocultar/mostrar campo de umbral segun el tipo de evento
  _onTypeChange(sel) {
    const noThreshold = ['daily_digest', 'treatment_overdue', 'control_review_overdue',
                         'incident_p1p2', 'nis2_pending', 'policy_review_overdue', 'task_overdue'];
    const thresholdWrap = document.getElementById('r-threshold-wrap');
    if (thresholdWrap) {
      thresholdWrap.style.display = noThreshold.includes(sel.value) ? 'none' : '';
    }
  },

  _ruleRow(r) {
    const eventLabels = {
      risk_high: 'Riesgo alto',
      risk_critical: 'Riesgo critico',
      treatment_overdue: 'Tratamiento vencido',
      risk_no_treatment: 'Sin plan de tratamiento',
      daily_digest: 'Resumen diario',
      treatment_due_soon: 'Vence pronto',
      control_review_overdue: 'Control vencido',
      incident_p1p2: 'Incidente P1/P2',
      nis2_pending: 'NIS2 pendiente',
      policy_review_overdue: 'Politica vencida',
      task_overdue: 'Tarea vencida',
    };
    const lastTrig = r.last_triggered_at
      ? new Date(r.last_triggered_at).toLocaleDateString('es-ES')
      : 'Nunca';
    return `
      <tr id="rule-row-${r.id}">
        <td><strong>${UI.esc(r.name)}</strong></td>
        <td><span class="badge badge-muted">${UI.esc(eventLabels[r.event_type] || r.event_type)}</span></td>
        <td style="text-align:center;">≥ ${r.threshold_level}</td>
        <td style="font-size:12px;">${UI.esc(r.recipient_email)}</td>
        <td style="font-size:12px;color:var(--text-muted);">${lastTrig}</td>
        <td style="text-align:center;">
          <button class="btn btn-sm" onclick="ViewAlerts._toggleRule(${r.id})"
                  style="font-size:11px;padding:2px 8px;
                         background:${r.is_active ? '#D1FAE5' : '#F3F4F6'};
                         color:${r.is_active ? '#065F46' : '#6B7280'};">
            ${r.is_active ? 'Activa' : 'Inactiva'}
          </button>
        </td>
        <td>
          <button class="btn btn-sm" onclick="ViewAlerts._deleteRule(${r.id})"
                  style="color:var(--brand-orange);">✕</button>
        </td>
      </tr>`;
  },

  async _testEmail() {
    try {
      const res = await Api.post('/api/alerts/test', {});
      UI.toast(res.message || 'Email de prueba enviado', 'success');
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  },

  _newRule() {
    UI.modal('Nueva regla de alerta', `
      <div class="form-grid">
        <div class="span2">
          <label>Nombre de la regla *</label>
          <input id="r-name" class="input" type="text" placeholder="Ej: Alerta riesgos criticos CISO">
        </div>
        <div>
          <label>Tipo de evento *</label>
          <select id="r-type" class="input" onchange="ViewAlerts._onTypeChange(this)">
            <optgroup label="Riesgos">
              <option value="risk_critical">Riesgo critico (nivel >= umbral)</option>
              <option value="risk_high">Riesgo alto (nivel >= umbral)</option>
              <option value="treatment_overdue">Plan de tratamiento vencido</option>
              <option value="risk_no_treatment">Riesgo sin plan de tratamiento</option>
              <option value="treatment_due_soon">Tratamiento proximo a vencer</option>
              <option value="daily_digest">Resumen diario del registro de riesgos</option>
            </optgroup>
            <optgroup label="Controles">
              <option value="control_review_overdue">Revision de control ISO 27002 vencida</option>
            </optgroup>
            <optgroup label="Incidentes">
              <option value="incident_p1p2">Incidentes P1/P2 abiertos</option>
              <option value="nis2_pending">Notificaciones NIS2 pendientes</option>
            </optgroup>
            <optgroup label="Otros modulos">
              <option value="policy_review_overdue">Politicas con revision vencida</option>
              <option value="task_overdue">Tareas de tratamiento vencidas</option>
            </optgroup>
          </select>
        </div>
        <div id="r-threshold-wrap">
          <label>Umbral de nivel</label>
          <input id="r-threshold" class="input" type="number" value="5" min="1" max="8">
        </div>
        <div class="span2">
          <label>Email destinatario *</label>
          <input id="r-email" class="input" type="email" placeholder="responsable@company.com">
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Crear regla</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => ViewAlerts._createRule();
  },

  async _createRule() {
    const body = {
      name: document.getElementById('r-name').value.trim(),
      event_type: document.getElementById('r-type').value,
      recipient_email: document.getElementById('r-email').value.trim(),
      threshold_level: parseInt(document.getElementById('r-threshold').value) || 5,
    };
    if (!body.name || !body.recipient_email) {
      UI.toast('Nombre y email son obligatorios', 'error'); return;
    }
    try {
      await Api.post('/api/alerts/rules', body);
      UI.closeModal();
      UI.toast('Regla creada', 'success');
      await this._load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  },

  async _toggleRule(id) {
    try {
      await Api.patch(`/api/alerts/rules/${id}/toggle`, {});
      await this._load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  },

  async _deleteRule(id) {
    if (!confirm('¿Eliminar esta regla de alerta?')) return;
    try {
      await Api.del(`/api/alerts/rules/${id}`);
      UI.toast('Regla eliminada', 'success');
      await this._load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  },

  async _checkRules() {
    try {
      const res = await Api.post('/api/alerts/check-rules', {});
      UI.toast(
        `Evaluacion completada: ${res.sent} email(s) enviados de ${res.rules_evaluated} regla(s) evaluada(s)`,
        res.sent > 0 ? 'success' : 'info'
      );
      if (res.errors?.length > 0) {
        console.error('Errores de envio:', res.errors);
        UI.toast('Algunos emails no se pudieron enviar. Revisa la consola.', 'warn');
      }
      await this._load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  },

  async _sendManual() {
    const riskId = document.getElementById('alert-risk-id').value;
    const recipient = document.getElementById('alert-recipient').value.trim();
    const reason = document.getElementById('alert-reason').value.trim() || 'Alerta manual de riesgo';
    if (!riskId || !recipient) {
      UI.toast('Introduce el ID del riesgo y el email del destinatario', 'error'); return;
    }
    try {
      const res = await Api.post(`/api/alerts/send-risk/${riskId}`, { recipient_email: recipient, reason });
      UI.toast(res.message || 'Alerta enviada', 'success');
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  },
};
