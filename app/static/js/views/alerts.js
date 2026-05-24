/* Vista Alertas — Configuracion SMTP y reglas de alerta por email. */
const ViewAlerts = {

  _settings: null,
  _rules: [],

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      'Alertas por email',
      'Configuracion SMTP y reglas de notificacion automatica de riesgos'
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
    const isAdmin = u && u.role === 'admin';
    const isAnalyst = u && (u.role === 'admin' || u.role === 'analyst');

    const s = this._settings || {};
    const smtpStatus = s.smtp_host
      ? `<span class="badge badge-muted" style="background:var(--success-soft,#D1FAE5);color:#065F46;">Configurado</span>`
      : `<span class="badge badge-muted" style="background:#FEF3C7;color:#92400E;">Sin configurar</span>`;

    container.innerHTML = `
      <!-- SMTP config -->
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="margin:0;">Configuracion SMTP ${smtpStatus}</h3>
          ${isAdmin ? `<button class="btn btn-sm btn-primary" onclick="ViewAlerts._testEmail()">
            Enviar email de prueba</button>` : ''}
        </div>
        ${isAdmin ? `
        <div class="modal-body">
          <div class="span2"><label>Host SMTP</label>
            <input id="smtp-host" type="text" value="${UI.esc(s.smtp_host || '')}"
                   placeholder="smtp.company.com" style="width:100%;"></div>
          <div><label>Puerto</label>
            <input id="smtp-port" type="number" value="${s.smtp_port || 587}"
                   placeholder="587" style="width:100%;"></div>
          <div><label>TLS / STARTTLS</label>
            <select id="smtp-tls" style="width:100%;">
              <option value="true" ${s.smtp_use_tls !== false ? 'selected' : ''}>STARTTLS (recomendado)</option>
              <option value="false" ${s.smtp_use_tls === false ? 'selected' : ''}>SSL directo / Sin TLS</option>
            </select></div>
          <div><label>Usuario SMTP</label>
            <input id="smtp-user" type="text" value="${UI.esc(s.smtp_user || '')}"
                   placeholder="noreply@company.com" style="width:100%;"></div>
          <div><label>Contraseña SMTP</label>
            <input id="smtp-pass" type="password" placeholder="Dejar vacio para no cambiar" style="width:100%;"></div>
          <div><label>Remitente (From)</label>
            <input id="smtp-from" type="email" value="${UI.esc(s.smtp_from || '')}"
                   placeholder="riskhub@company.com" style="width:100%;"></div>
        </div>
        <div style="text-align:right;margin-top:12px;">
          <button class="btn btn-primary" onclick="ViewAlerts._saveSmtp()">Guardar configuracion SMTP</button>
        </div>` : `
        <div class="modal-body">
          ${s.smtp_host ? `
          <div><label>Host</label><p style="margin:4px 0;">${UI.esc(s.smtp_host)}:${s.smtp_port}</p></div>
          <div><label>Remitente</label><p style="margin:4px 0;">${UI.esc(s.smtp_from || '-')}</p></div>
          <div><label>TLS</label><p style="margin:4px 0;">${s.smtp_use_tls ? 'STARTTLS' : 'Sin TLS'}</p></div>
          <div><label>Estado</label><p style="margin:4px 0;">Configurado</p></div>
          ` : '<div class="span2"><p style="color:var(--text-muted);margin:0;">SMTP no configurado. Contacta al administrador.</p></div>'}
        </div>`}
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

  _ruleRow(r) {
    const eventLabels = {
      risk_high: 'Riesgo alto',
      risk_critical: 'Riesgo critico',
      treatment_overdue: 'Tratamiento vencido',
      risk_no_treatment: 'Sin plan de tratamiento',
      daily_digest: 'Resumen diario',
      treatment_due_soon: 'Vence en 7 dias',
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

  async _saveSmtp() {
    const body = {
      smtp_host: document.getElementById('smtp-host').value.trim(),
      smtp_port: parseInt(document.getElementById('smtp-port').value) || 587,
      smtp_use_tls: document.getElementById('smtp-tls').value === 'true',
      smtp_user: document.getElementById('smtp-user').value.trim(),
      smtp_password: document.getElementById('smtp-pass').value,
      smtp_from: document.getElementById('smtp-from').value.trim(),
    };
    if (!body.smtp_host || !body.smtp_from) {
      UI.toast('Host SMTP y remitente son obligatorios', 'error'); return;
    }
    try {
      await Api.put('/api/alerts/settings', body);
      UI.toast('Configuracion SMTP guardada', 'success');
      await this._load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
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
    const html = `
      <div class="modal-head">
        <h2>Nueva regla de alerta</h2>
        <button class="btn btn-ghost btn-sm" onclick="UI.closeModal()">✕</button>
      </div>
      <div class="modal-body">
        <div class="span2"><label>Nombre de la regla <span style="color:var(--brand-orange)">*</span></label>
          <input id="r-name" type="text" placeholder="Ej: Alerta riesgos criticos CISO" style="width:100%;"></div>
        <div><label>Tipo de evento <span style="color:var(--brand-orange)">*</span></label>
          <select id="r-type" style="width:100%;">
            <option value="risk_critical">Riesgo critico (nivel >= umbral)</option>
            <option value="risk_high">Riesgo alto (nivel >= umbral)</option>
            <option value="treatment_overdue">Plan de tratamiento vencido</option>
            <option value="risk_no_treatment">Riesgo sin plan de tratamiento</option>
            <option value="daily_digest">Resumen diario del registro de riesgos</option>
            <option value="treatment_due_soon">Tratamiento proximo a vencer (7 dias)</option>
          </select></div>
        <div><label>Umbral de nivel</label>
          <input id="r-threshold" type="number" value="5" min="1" max="8" style="width:100%;"></div>
        <div class="span2"><label>Email destinatario <span style="color:var(--brand-orange)">*</span></label>
          <input id="r-email" type="email" placeholder="responsable@company.com" style="width:100%;"></div>
      </div>
      <div class="modal-foot">
        <button class="btn" onclick="UI.closeModal()">Cancelar</button>
        <button class="btn btn-primary" onclick="ViewAlerts._createRule()">Crear regla</button>
      </div>`;
    UI.openModal(html);
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
