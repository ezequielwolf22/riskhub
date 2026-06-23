/* Vista Alertas — Reglas de alerta por email. */
const ViewAlerts = {

  _settings: null,
  _rules: [],

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
      const [settings, rules] = await Promise.all([
        Api.get('/api/alerts/settings'),
        Api.get('/api/alerts/rules'),
      ]);
      this._settings = settings;
      this._rules = rules || [];
      this._render(c);
    } catch (e) {
      c.innerHTML = UI.notice(t('common.error') + ': ' + UI.esc(e.message), 'error');
    }
  },

  _render(container) {
    const u = Auth.user();
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

      <!-- Reglas -->
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="margin:0;">${t('alerts.rules_title', { n: this._rules.length })}</h3>
          <div style="display:flex;gap:8px;">
            ${isAnalyst ? `<button class="btn btn-sm" onclick="ViewAlerts._checkRules()">
              ${t('alerts.eval_rules')}</button>
            <button class="btn btn-sm btn-primary" onclick="ViewAlerts._newRule()">
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

  // Ocultar/mostrar campo de umbral segun el tipo de evento
  _onTypeChange(sel) {
    const noThreshold = ['daily_digest', 'treatment_overdue', 'control_review_overdue',
                         'incident_p1p2', 'nis2_pending', 'policy_review_overdue', 'task_overdue', 'compound'];
    const thresholdWrap = document.getElementById('r-threshold-wrap');
    if (thresholdWrap) {
      thresholdWrap.style.display = noThreshold.includes(sel.value) ? 'none' : '';
    }
    const compoundWrap = document.getElementById('r-compound-wrap');
    if (compoundWrap) {
      compoundWrap.style.display = sel.value === 'compound' ? '' : 'none';
    }
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
    };
    const lastTrig = r.last_triggered_at
      ? new Date(r.last_triggered_at).toLocaleDateString(_locale)
      : t('alerts.last_never');
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

  _newRule() {
    UI.modal(t('alerts.new_rule_title'), `
      <div class="form-grid">
        <div class="span2">
          <label>${t('alerts.rule_name_label')}</label>
          <input id="r-name" class="input" type="text" placeholder="${t('alerts.rule_name_placeholder')}">
        </div>
        <div>
          <label>${t('alerts.rule_type_label')}</label>
          <select id="r-type" class="input" onchange="ViewAlerts._onTypeChange(this)">
            <optgroup label="${t('alerts.group_risks')}">
              <option value="risk_critical">${t('alerts.event_risk_critical_opt')}</option>
              <option value="risk_high">${t('alerts.event_risk_high_opt')}</option>
              <option value="treatment_overdue">${t('alerts.event_treatment_overdue_opt')}</option>
              <option value="risk_no_treatment">${t('alerts.event_risk_no_treatment_opt')}</option>
              <option value="treatment_due_soon">${t('alerts.event_treatment_due_soon_opt')}</option>
              <option value="daily_digest">${t('alerts.event_daily_digest_opt')}</option>
              <option value="compound">${t('alerts.event_compound_opt')}</option>
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
          </select>
        </div>
        <div id="r-threshold-wrap">
          <label>${t('alerts.rule_threshold_label')}</label>
          <input id="r-threshold" class="input" type="number" value="5" min="1" max="8">
        </div>
        <div class="span2">
          <label>${t('alerts.rule_email_label')}</label>
          <input id="r-email" class="input" type="email" placeholder="${t('alerts.rule_email_placeholder')}">
        </div>
        <div class="span2" id="r-compound-wrap" style="display:none;">
          <div style="background:var(--bg-2);border-radius:8px;padding:12px;border:1px solid var(--border);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
              <strong style="font-size:13px;">${t('alerts.compound_conditions')}</strong>
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
            <div style="font-size:11px;color:var(--text-muted);margin-top:8px;">
              Fields: <code>residual_level</code>, <code>inherent_level</code>, <code>control_count</code><br>
              Operators: <code>gte</code> (>=), <code>lte</code> (<=), <code>gt</code> (>), <code>lt</code> (<), <code>eq</code> (=)
            </div>
          </div>
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="m-save">${t('alerts.new_rule')}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => ViewAlerts._createRule();

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
          conditions[idx][field] = field === 'value' ? (parseFloat(inp.value) ?? 0) : inp.value;
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
    const body = {
      name: document.getElementById('r-name').value.trim(),
      event_type: typeVal === 'compound' ? 'risk_high' : typeVal,
      recipient_email: document.getElementById('r-email').value.trim(),
      threshold_level: parseInt(document.getElementById('r-threshold').value) || 5,
    };
    if (typeVal === 'compound' && ViewAlerts._pendingConditions?.length) {
      body.conditions = ViewAlerts._pendingConditions;
      body.logic = document.getElementById('r-logic')?.value || 'AND';
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
    if (!riskId || !recipient) {
      UI.toast(t('alerts.manual_fill'), 'error'); return;
    }
    try {
      const res = await Api.post(`/api/alerts/send-risk/${riskId}`, { recipient_email: recipient, reason });
      UI.toast(res.message || t('alerts.manual_sent'), 'success');
    } catch (e) {
      UI.toast(t('common.error') + ': ' + e.message, 'error');
    }
  },
};
