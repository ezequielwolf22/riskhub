/* Vista Alertas — Reglas de alerta. Los canales (SMTP, Teams, Power Automate)
 * se configuran en la vista Integraciones, seccion "Integraciones para alertas". */
const ViewAlerts = {

  _settings: null,
  _rules: [],
  _users: [],
  _notif: null,   // catalogo de notificaciones automaticas + config de la org

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      t('alerts.title'),
      t('alerts.subtitle')
    ) + '<div id="alerts-content"></div>';
    await this._load();
  },

  async _load() {
    const c = document.getElementById('alerts-content');
    try {
      const [settings, rules, notif] = await Promise.all([
        Api.get('/api/alerts/settings'),
        Api.get('/api/alerts/rules'),
        Api.get('/api/notification-settings').catch(() => null),
      ]);
      this._settings = settings;
      this._rules = rules || [];
      this._notif = notif;
      this._render(c);
    } catch (e) {
      c.innerHTML = UI.notice(t('common.error') + ': ' + UI.esc(e.message), 'error');
    }
  },

  _render(container) {
    const u = Auth.user();
    const isAdmin = u && (u.role === 'admin' || u.role === 'superadmin');
    const isAnalyst = u && (u.role === 'admin' || u.role === 'superadmin' || u.role === 'analyst');

    const s = this._settings || {};
    const smtpOk = !!s.smtp_host;
    const smtpBadge = smtpOk
      ? `<span class="badge badge-muted" style="background:#D1FAE5;color:#065F46;">${t('alerts.smtp_ok')}</span>`
      : `<span class="badge badge-muted" style="background:#FEF3C7;color:#92400E;">${t('alerts.smtp_missing')}</span>`;

    container.innerHTML = `
      <!-- Estado SMTP -->
      <div class="card" style="margin-bottom:16px;display:flex;align-items:center;gap:16px;padding:14px 20px;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
        <div style="flex:1;">
          <span style="font-size:13px;font-weight:600;">${t('alerts.smtp_section')}</span>
          <span style="margin-left:10px;">${smtpBadge}</span>
          ${smtpOk ? `<div style="font-size:12px;color:var(--text-muted);margin-top:2px;">${UI.esc(s.smtp_host)}:${s.smtp_port} &mdash; ${UI.esc(s.smtp_from || '')}</div>` : ''}
        </div>
        <button class="btn btn-sm" onclick="App.navigate('integrations')">
          ${t('alerts.config_smtp')}
        </button>
        ${smtpOk ? `<button class="btn btn-sm" onclick="ViewAlerts._testEmail()">${t('alerts.send_test')}</button>` : ''}
      </div>

      ${this._notifSection()}

      <!-- Reglas -->
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="margin:0;">${t('alerts.rules_title', { n: this._rules.length })}</h3>
          <div style="display:flex;gap:8px;">
            ${isAnalyst ? `<button class="btn btn-sm" onclick="ViewAlerts._checkRules()">
              ${t('alerts.eval_rules')}</button>` : ''}
            ${isAdmin ? `<button class="btn btn-sm btn-primary" onclick="ViewAlerts._newRule()">
              ${t('alerts.new_rule')}</button>` : ''}
          </div>
        </div>
        ${this._rules.length === 0
          ? `<p style="color:var(--text-muted);font-size:13px;margin:0;">${t('alerts.no_rules')}</p>`
          : `<div style="overflow-x:auto;">
              <table class="data">
                <thead><tr>
                  <th>${t('alerts.col_name')}</th><th>${t('alerts.col_event')}</th><th>${t('alerts.col_threshold')}</th>
                  <th>${t('alerts.col_recipient')}</th><th>${t('alerts.col_last_sent')}</th>
                  <th style="width:90px;">${t('alerts.col_status')}</th>
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
        <h3 style="margin-bottom:16px;">${t('alerts.manual_section')}</h3>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px;">
          ${t('alerts.manual_desc')}
        </p>
        <div class="modal-body">
          <div><label>${t('alerts.manual_risk_id')}</label>
            <input id="alert-risk-id" type="number" placeholder="3" style="width:100%;"></div>
          <div><label>${t('alerts.manual_recipient')}</label>
            <input id="alert-recipient" type="email" placeholder="${t('alerts.rule_email_placeholder')}" style="width:100%;"></div>
          <div class="span2"><label>${t('alerts.manual_reason')}</label>
            <input id="alert-reason" type="text" placeholder="${t('alerts.manual_default_reason')}" style="width:100%;"></div>
        </div>
        <div style="text-align:right;margin-top:12px;">
          <button class="btn btn-primary" onclick="ViewAlerts._sendManual()">${t('alerts.manual_send')}</button>
        </div>
      </div>`;
  },

  // ---------- Notificaciones automaticas (control total por alerta) ----------

  _notifSection() {
    const u = Auth.user();
    const isAdmin = u && (u.role === 'admin' || u.role === 'superadmin');
    if (!isAdmin) return '';
    const data = this._notif;
    if (!data) {
      return `<div class="card" style="margin-bottom:16px;">
        <h3 style="margin:0 0 6px;">Notificaciones automáticas</h3>
        <p style="font-size:13px;color:var(--text-muted);margin:0;">No se pudo cargar el panel de notificaciones.</p>
      </div>`;
    }
    const items = data.settings || [];
    // Agrupar por categoria
    const groups = {};
    items.forEach(it => { (groups[it.category] = groups[it.category] || []).push(it); });

    const chWarn = [];
    if (!data.email_channel_ready) chWarn.push('Email (SMTP) no configurado');
    if (data.admin_emails && data.admin_emails.length === 0) chWarn.push('la organización no tiene administradores con email');

    const rows = Object.keys(groups).map(cat => `
      <tr><td colspan="6" style="background:var(--bg-subtle,#f7f7f9);font-weight:600;font-size:12px;
            text-transform:uppercase;letter-spacing:.03em;color:var(--text-muted);padding:8px 10px;">${UI.esc(cat)}</td></tr>
      ${groups[cat].map(it => this._notifRow(it, data)).join('')}
    `).join('');

    return `
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:6px;">
          <div>
            <h3 style="margin:0 0 4px;">Notificaciones automáticas</h3>
            <p style="font-size:13px;color:var(--text-muted);margin:0;max-width:640px;">
              Control total de los correos que el sistema envía solo. Activa o apaga cada uno, decide
              quién lo recibe, por qué canal, cada cuánto como máximo (anti-repetición) y el umbral
              cuando aplica. Los cambios se guardan al instante.
            </p>
          </div>
          <button class="btn btn-sm" style="white-space:nowrap;border-color:#dc2626;color:#dc2626;"
                  onclick="ViewAlerts._notifSilenceAll()">Silenciar todo</button>
        </div>
        ${chWarn.length ? UI.notice('Aviso: ' + chWarn.join('; ') + '. Las alertas por email no saldrán hasta resolverlo.', 'warn') : ''}
        <div style="overflow-x:auto;">
          <table class="data" style="font-size:13px;">
            <thead><tr>
              <th style="min-width:220px;">Alerta</th>
              <th style="width:70px;">Activa</th>
              <th style="width:130px;">Canal</th>
              <th style="min-width:200px;">Quién recibe</th>
              <th style="width:110px;">Máx. cada</th>
              <th style="width:110px;">Umbral</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>`;
  },

  _notifRow(it, data) {
    const k = it.key;
    const chOpt = (v, label) => `<option value="${v}" ${it.channel === v ? 'selected' : ''}>${label}</option>`;
    const custom = it.recipient_mode === 'custom';
    const recList = (it.recipients || []).join(', ');
    const adminsHint = (data.admin_emails || []).length
      ? `${data.admin_emails.length} admin(s)` : 'sin admins';
    return `
      <tr data-nf="${k}">
        <td>
          <div style="font-weight:600;">${UI.esc(it.label)}</div>
          <div style="font-size:11.5px;color:var(--text-muted);">${UI.esc(it.description)}</div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">Frecuencia: ${UI.esc(it.frequency_human)}</div>
        </td>
        <td style="text-align:center;">
          <label class="switch" style="cursor:pointer;">
            <input type="checkbox" id="nf-en-${k}" ${it.enabled ? 'checked' : ''}
                   onchange="ViewAlerts._notifSave('${k}')">
          </label>
        </td>
        <td>
          <select id="nf-ch-${k}" class="input" style="padding:3px 6px;font-size:12px;"
                  onchange="ViewAlerts._notifSave('${k}')">
            ${chOpt('email', 'Email')}
            ${chOpt('teams', 'Teams')}
            ${chOpt('power_automate', 'Power Automate')}
            ${chOpt('all', 'Todos')}
          </select>
        </td>
        <td>
          <select id="nf-rm-${k}" class="input" style="padding:3px 6px;font-size:12px;margin-bottom:4px;"
                  onchange="ViewAlerts._notifModeChange('${k}')">
            <option value="admins" ${!custom ? 'selected' : ''}>Administradores (${UI.esc(adminsHint)})</option>
            <option value="custom" ${custom ? 'selected' : ''}>Personalizado</option>
          </select>
          <input type="text" id="nf-rc-${k}" class="input" placeholder="email1@x.com, email2@x.com"
                 value="${UI.esc(recList)}" style="padding:3px 6px;font-size:12px;display:${custom ? 'block' : 'none'};"
                 onchange="ViewAlerts._notifSave('${k}')">
        </td>
        <td>
          <div style="display:flex;align-items:center;gap:4px;">
            <input type="number" min="0" max="365" id="nf-cd-${k}" value="${it.cooldown_days}"
                   class="input" style="width:52px;padding:3px 6px;font-size:12px;"
                   onchange="ViewAlerts._notifSave('${k}')">
            <span style="font-size:11px;color:var(--text-muted);">días</span>
          </div>
        </td>
        <td>
          ${it.supports_threshold
            ? `<input type="number" step="0.1" id="nf-th-${k}" value="${it.threshold != null ? it.threshold : ''}"
                     class="input" style="width:64px;padding:3px 6px;font-size:12px;"
                     title="${UI.esc(it.threshold_label || '')}"
                     onchange="ViewAlerts._notifSave('${k}')">`
            : '<span style="font-size:11px;color:var(--text-muted);">—</span>'}
        </td>
      </tr>`;
  },

  _notifModeChange(k) {
    const rc = document.getElementById('nf-rc-' + k);
    const rm = document.getElementById('nf-rm-' + k);
    if (rc && rm) rc.style.display = (rm.value === 'custom') ? 'block' : 'none';
    this._notifSave(k);
  },

  async _notifSave(k) {
    const en = document.getElementById('nf-en-' + k);
    const ch = document.getElementById('nf-ch-' + k);
    const rm = document.getElementById('nf-rm-' + k);
    const rc = document.getElementById('nf-rc-' + k);
    const cd = document.getElementById('nf-cd-' + k);
    const th = document.getElementById('nf-th-' + k);
    const body = {
      enabled: en ? en.checked : undefined,
      channel: ch ? ch.value : undefined,
      recipient_mode: rm ? rm.value : undefined,
      cooldown_days: cd && cd.value !== '' ? parseInt(cd.value, 10) : undefined,
    };
    if (rm && rm.value === 'custom' && rc) {
      body.recipients = rc.value.split(',').map(s => s.trim()).filter(Boolean);
    }
    if (th && th.value !== '') body.threshold = parseFloat(th.value);
    try {
      await Api.put('/api/notification-settings/' + encodeURIComponent(k), body);
      UI.toast('Notificación actualizada', 'success');
    } catch (e) {
      UI.toast('Error: ' + (e.message || 'no se pudo guardar'), 'error');
    }
  },

  async _notifSilenceAll() {
    if (!confirm('Vas a desactivar TODAS las notificaciones automáticas de esta organización. ¿Continuar?')) return;
    try {
      const r = await Api.post('/api/notification-settings/silence-all', {});
      UI.toast('Silenciadas ' + (r.silenced || 0) + ' notificaciones', 'success');
      await this._load();
    } catch (e) {
      UI.toast('Error: ' + (e.message || 'no se pudo silenciar'), 'error');
    }
  },

  // Configuración de umbral por tipo de evento — solo estos tipos muestran/usan el campo umbral.
  _THRESHOLD_CONFIG: {
    risk_critical: { min: 1, max: 8, def: 6 },
    risk_high: { min: 1, max: 8, def: 5 },
    risk_no_treatment: { min: 1, max: 8, def: 5 },
    treatment_due_soon: { min: 1, max: 90, def: 7, labelKey: 'alerts.threshold_label_days', isDays: true },
    supplier_critical_risk: { min: 0, max: 100, def: 70, labelKey: 'alerts.threshold_label_score' },
  },

  _EVENT_ENTITY_LABEL_KEYS: {
    supplier: 'alerts.entity_supplier',
    supplier_questionnaire: 'alerts.entity_supplier_questionnaire',
  },

  // Ocultar/mostrar campo de umbral y bloque de condiciones según el tipo de evento
  _onTypeChange(sel) {
    const cfg = ViewAlerts._THRESHOLD_CONFIG[sel.value];
    const thresholdWrap = document.getElementById('r-threshold-wrap');
    if (thresholdWrap) {
      thresholdWrap.style.display = cfg ? '' : 'none';
      if (cfg) {
        const label = document.getElementById('r-threshold-label');
        if (label) label.textContent = t(cfg.labelKey || 'alerts.rule_threshold_label');
        const inp = document.getElementById('r-threshold');
        if (inp) { inp.min = cfg.min; inp.max = cfg.max; inp.value = cfg.def; }
      }
    }
    const compoundWrap = document.getElementById('r-compound-wrap');
    if (compoundWrap) {
      compoundWrap.style.display = sel.value === 'compound' ? '' : 'none';
    }
    if (sel.value === 'compound') {
      ViewAlerts._onEntityChange(document.getElementById('r-entity'));
    }
  },

  // Actualiza el texto de ayuda de campos disponibles según la entidad elegida (regla personalizada)
  _onEntityChange(sel) {
    const hintEl = document.getElementById('r-fields-hint');
    if (!hintEl) return;
    const entity = sel ? sel.value : 'risk';
    const hintKeys = {
      risk: 'alerts.fields_hint_risk',
      supplier: 'alerts.fields_hint_supplier',
      supplier_questionnaire: 'alerts.fields_hint_supplier_questionnaire',
    };
    hintEl.innerHTML = t(hintKeys[entity] || hintKeys.risk) + '<br>' + t('alerts.fields_hint_operators');
  },

  // Autocompleta el email destinatario con el del usuario interno seleccionado
  _onRecipientUserChange(sel) {
    if (!sel || !sel.value) return;
    const emailInput = document.getElementById('r-email');
    if (emailInput) emailInput.value = sel.value;
  },

  _ruleRow(r) {
    const _locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
    const eventLabels = {
      risk_high: t('alerts.event_risk_high'),
      risk_critical: t('alerts.event_risk_critical'),
      treatment_overdue: t('alerts.event_treatment_overdue'),
      risk_no_treatment: t('alerts.event_risk_no_treatment'),
      daily_digest: t('alerts.event_daily_digest'),
      treatment_due_soon: t('alerts.event_treatment_due_soon'),
      control_review_overdue: t('alerts.event_control_review_overdue'),
      incident_p1p2: t('alerts.event_incident_p1p2'),
      nis2_pending: t('alerts.event_nis2_pending'),
      policy_review_overdue: t('alerts.event_policy_review_overdue'),
      task_overdue: t('alerts.event_task_overdue'),
      compound: t('alerts.event_compound'),
      supplier_created: t('alerts.event_supplier_created'),
      supplier_critical_risk: t('alerts.event_supplier_critical_risk'),
      vendor_issue_created: t('alerts.event_vendor_issue_created'),
      vendor_issue_sla_breach: t('alerts.event_vendor_issue_sla_breach'),
      questionnaire_overdue: t('alerts.event_questionnaire_overdue'),
      bcp_review_overdue: t('alerts.event_bcp_review_overdue'),
      bcp_under_review: t('alerts.event_bcp_under_review'),
      regwatch_new_change: t('alerts.event_regwatch_new_change'),
      regwatch_high_impact: t('alerts.event_regwatch_high_impact'),
    };
    let eventLabel = UI.esc(eventLabels[r.event_type] || r.event_type);
    if (r.event_type === 'compound' && r.entity_type && r.entity_type !== 'risk') {
      const entityKey = ViewAlerts._EVENT_ENTITY_LABEL_KEYS[r.entity_type];
      if (entityKey) eventLabel += ` (${t(entityKey)})`;
    }
    const thCfg = ViewAlerts._THRESHOLD_CONFIG[r.event_type];
    const thresholdDisplay = thCfg
      ? (thCfg.isDays ? `${r.threshold_level} d` : `≥ ${r.threshold_level}`)
      : '—';
    const lastTrig = r.last_triggered_at
      ? new Date(r.last_triggered_at).toLocaleDateString(_locale)
      : t('alerts.last_never');
    return `
      <tr id="rule-row-${r.id}">
        <td><strong>${UI.esc(r.name)}</strong></td>
        <td><span class="badge badge-muted">${eventLabel}</span></td>
        <td style="text-align:center;">${thresholdDisplay}</td>
        <td style="font-size:12px;">${UI.esc(r.recipient_email)}</td>
        <td style="font-size:12px;color:var(--text-muted);">${lastTrig}</td>
        <td style="text-align:center;">
          <button class="btn btn-sm" onclick="ViewAlerts._toggleRule(${r.id})"
                  style="font-size:11px;padding:2px 8px;
                         background:${r.is_active ? '#D1FAE5' : '#F3F4F6'};
                         color:${r.is_active ? '#065F46' : '#6B7280'};">
            ${r.is_active ? t('alerts.rule_active') : t('alerts.rule_inactive')}
          </button>
        </td>
        <td>
          <button class="btn btn-sm" onclick="ViewAlerts._deleteRule(${r.id})"
                  style="color:var(--brand-orange);">&#x2715;</button>
        </td>
      </tr>`;
  },

  async _testEmail() {
    try {
      const res = await Api.post('/api/alerts/test', {});
      UI.toast(res.message || t('alerts.manual_sent'), 'success');
    } catch (e) {
      UI.toast(t('common.error') + ': ' + e.message, 'error');
    }
  },

  async _newRule() {
    try {
      this._users = await Api.users.list();
    } catch (e) {
      this._users = [];
    }
    const userOptions = (this._users || [])
      .map(u => `<option value="${UI.esc(u.email)}">${UI.esc(u.full_name || u.email)} (${UI.esc(u.email)})</option>`)
      .join('');

    UI.modal(t('alerts.new_rule_title'), `
      <div class="form-grid">
        <div class="span2">
          <label>${t('alerts.rule_name_label')}</label>
          <input id="r-name" class="input" type="text" placeholder="${t('alerts.rule_name_placeholder')}">
        </div>
        <div class="span2">
          <label>${t('alerts.rule_type_label')}</label>
          <select id="r-type" class="input" onchange="ViewAlerts._onTypeChange(this)">
            <optgroup label="${t('alerts.group_risks')}">
              <option value="risk_critical">${t('alerts.event_risk_critical_opt')}</option>
              <option value="risk_high">${t('alerts.event_risk_high_opt')}</option>
              <option value="treatment_overdue">${t('alerts.event_treatment_overdue_opt')}</option>
              <option value="risk_no_treatment">${t('alerts.event_risk_no_treatment_opt')}</option>
              <option value="treatment_due_soon">${t('alerts.event_treatment_due_soon_opt')}</option>
              <option value="daily_digest">${t('alerts.event_daily_digest_opt')}</option>
            </optgroup>
            <optgroup label="${t('alerts.group_controls')}">
              <option value="control_review_overdue">${t('alerts.event_control_opt')}</option>
            </optgroup>
            <optgroup label="${t('alerts.group_incidents')}">
              <option value="incident_p1p2">${t('alerts.event_incident_opt')}</option>
              <option value="nis2_pending">${t('alerts.event_nis2_opt')}</option>
            </optgroup>
            <optgroup label="${t('alerts.group_other')}">
              <option value="policy_review_overdue">${t('alerts.event_policy_opt')}</option>
              <option value="task_overdue">${t('alerts.event_task_opt')}</option>
            </optgroup>
            <optgroup label="${t('alerts.group_suppliers')}">
              <option value="supplier_created">${t('alerts.event_supplier_created_opt')}</option>
              <option value="supplier_critical_risk">${t('alerts.event_supplier_critical_risk_opt')}</option>
              <option value="vendor_issue_created">${t('alerts.event_vendor_issue_created_opt')}</option>
              <option value="vendor_issue_sla_breach">${t('alerts.event_vendor_issue_sla_breach_opt')}</option>
              <option value="questionnaire_overdue">${t('alerts.event_questionnaire_overdue_opt')}</option>
            </optgroup>
            <optgroup label="${t('alerts.group_bcp')}">
              <option value="bcp_review_overdue">${t('alerts.event_bcp_review_overdue_opt')}</option>
              <option value="bcp_under_review">${t('alerts.event_bcp_under_review_opt')}</option>
            </optgroup>
            <optgroup label="${t('alerts.group_regwatch')}">
              <option value="regwatch_new_change">${t('alerts.event_regwatch_new_change_opt')}</option>
              <option value="regwatch_high_impact">${t('alerts.event_regwatch_high_impact_opt')}</option>
            </optgroup>
            <optgroup label="${t('alerts.group_other')}">
              <option value="compound">${t('alerts.event_compound_opt')}</option>
            </optgroup>
          </select>
          <div style="font-size:11px;color:var(--text-muted);margin-top:4px;">${t('alerts.custom_alerts_hint')}</div>
        </div>
        <div id="r-threshold-wrap" style="display:none;">
          <label id="r-threshold-label">${t('alerts.rule_threshold_label')}</label>
          <input id="r-threshold" class="input" type="number" value="5" min="1" max="8">
        </div>
        <div>
          <label>${t('alerts.recipient_user_label')}</label>
          <select id="r-user" class="input" onchange="ViewAlerts._onRecipientUserChange(this)">
            <option value="">${t('alerts.recipient_user_placeholder')}</option>
            ${userOptions}
          </select>
          <div style="font-size:11px;color:var(--text-muted);margin-top:4px;">${t('alerts.recipient_user_hint')}</div>
        </div>
        <div class="span2">
          <label>${t('alerts.rule_email_label')}</label>
          <input id="r-email" class="input" type="email" placeholder="${t('alerts.rule_email_placeholder')}">
        </div>
        <div class="span2" id="r-compound-wrap" style="display:none;">
          <div style="background:var(--bg-2);border-radius:8px;padding:12px;border:1px solid var(--border);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px;">
              <div style="display:flex;align-items:center;gap:8px;font-size:13px;">
                ${t('alerts.entity_label')}
                <select id="r-entity" class="input" style="width:auto;padding:3px 8px;" onchange="ViewAlerts._onEntityChange(this)">
                  <option value="risk">${t('alerts.entity_risk')}</option>
                  <option value="supplier">${t('alerts.entity_supplier')}</option>
                  <option value="supplier_questionnaire">${t('alerts.entity_supplier_questionnaire')}</option>
                </select>
              </div>
              <div style="display:flex;align-items:center;gap:8px;font-size:13px;">
                ${t('alerts.compound_logic')}
                <select id="r-logic" class="input" style="width:auto;padding:3px 8px;">
                  <option value="AND">${t('alerts.logic_and')}</option>
                  <option value="OR">${t('alerts.logic_or')}</option>
                </select>
              </div>
            </div>
            <div id="r-conditions-list" style="margin-bottom:10px;"></div>
            <button type="button" class="btn btn-ghost btn-sm" id="btn-add-condition">${t('alerts.add_condition')}</button>
            <div id="r-fields-hint" style="font-size:11px;color:var(--text-muted);margin-top:8px;"></div>
          </div>
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="m-save">${t('alerts.new_rule')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => ViewAlerts._createRule();
    ViewAlerts._onEntityChange(document.getElementById('r-entity'));

    // Compound conditions builder
    const conditions = [];
    const renderConditions = () => {
      const list = document.getElementById('r-conditions-list');
      if (!list) return;
      list.innerHTML = conditions.map((c, i) => `
        <div style="display:flex;gap:6px;align-items:center;margin-bottom:6px;flex-wrap:wrap;">
          <input type="text" placeholder="campo" value="${UI.esc(c.field||'')}" data-ci="${i}" data-cf="field"
                 class="input cond-field" style="flex:2;min-width:120px;">
          <select data-ci="${i}" data-cf="op" class="input cond-field" style="flex:1;min-width:80px;">
            ${['gte','lte','gt','lt','eq'].map(op => `<option value="${op}" ${c.op===op?'selected':''}>${op}</option>`).join('')}
          </select>
          <input type="number" placeholder="valor" value="${c.value??''}" data-ci="${i}" data-cf="value"
                 class="input cond-field" style="flex:1;min-width:80px;">
          <button type="button" class="btn btn-ghost btn-sm" data-del-ci="${i}" style="color:var(--danger);">&#x00D7;</button>
        </div>`).join('');
      list.querySelectorAll('.cond-field').forEach(inp => {
        inp.oninput = inp.onchange = () => {
          const idx = parseInt(inp.dataset.ci);
          const field = inp.dataset.cf;
          conditions[idx][field] = field === 'value' ? (parseFloat(inp.value) || 0) : inp.value;
        };
      });
      list.querySelectorAll('[data-del-ci]').forEach(btn => {
        btn.onclick = () => { conditions.splice(parseInt(btn.dataset.delCi), 1); renderConditions(); };
      });
    };
    document.getElementById('btn-add-condition').onclick = () => {
      conditions.push({ field: 'residual_level', op: 'gte', value: 5 });
      renderConditions();
    };
    ViewAlerts._pendingConditions = conditions;
  },

  async _createRule() {
    const typeVal = document.getElementById('r-type').value;
    const cfg = ViewAlerts._THRESHOLD_CONFIG[typeVal];
    const body = {
      name: document.getElementById('r-name').value.trim(),
      event_type: typeVal,
      recipient_email: document.getElementById('r-email').value.trim(),
      threshold_level: cfg ? (parseInt(document.getElementById('r-threshold').value) || cfg.def) : 0,
    };
    if (typeVal === 'compound') {
      body.entity_type = document.getElementById('r-entity')?.value || 'risk';
      body.logic = document.getElementById('r-logic')?.value || 'AND';
      body.conditions = (ViewAlerts._pendingConditions || []).filter(c => c.field);
      if (!body.conditions.length) {
        UI.toast(t('alerts.rule_fill'), 'error'); return;
      }
    }
    if (!body.name || !body.recipient_email) {
      UI.toast(t('alerts.rule_fill'), 'error'); return;
    }
    try {
      await Api.post('/api/alerts/rules', body);
      UI.closeModal();
      UI.toast(t('alerts.rule_created'), 'success');
      await this._load();
    } catch (e) {
      UI.toast(t('common.error') + ': ' + e.message, 'error');
    }
  },

  async _toggleRule(id) {
    try {
      await Api.patch(`/api/alerts/rules/${id}/toggle`, {});
      await this._load();
    } catch (e) {
      UI.toast(t('common.error') + ': ' + e.message, 'error');
    }
  },

  async _deleteRule(id) {
    if (!await UI.confirm(t('alerts.delete_confirm'))) return;
    try {
      await Api.del(`/api/alerts/rules/${id}`);
      UI.toast(t('alerts.rule_deleted'), 'success');
      await this._load();
    } catch (e) {
      UI.toast(t('common.error') + ': ' + e.message, 'error');
    }
  },

  async _checkRules() {
    try {
      const res = await Api.post('/api/alerts/check-rules', {});
      UI.toast(
        t('alerts.eval_done', { sent: res.sent, total: res.rules_evaluated }),
        res.sent > 0 ? 'success' : 'info'
      );
      if (res.errors?.length > 0) {
        console.error('Send errors:', res.errors);
        UI.toast(t('alerts.eval_errors'), 'warn');
      }
      await this._load();
    } catch (e) {
      UI.toast(t('common.error') + ': ' + e.message, 'error');
    }
  },

  async _sendManual() {
    const riskId = document.getElementById('alert-risk-id').value;
    const recipient = document.getElementById('alert-recipient').value.trim();
    const reason = document.getElementById('alert-reason').value.trim() || t('alerts.manual_default_reason');
    if (!riskId) {
      UI.toast(t('alerts.manual_fill'), 'error'); return;
    }
    try {
      const res = await Api.post(`/api/alerts/send-risk/${riskId}`, { recipient_email: recipient || null, reason });
      UI.toast(res.message || t('alerts.manual_sent'), 'success');
    } catch (e) {
      UI.toast(t('common.error') + ': ' + e.message, 'error');
    }
  },
};
