/* Vista de Vigilancia Normativa Automatica (regwatch).
   Filosofia "set it and forget it": un toggle grande, un indicador de estado,
   opciones avanzadas colapsadas, inbox de cambios pendientes e historial.
   Spec: RISKHUB_REGULATORY_WATCH_MODULE_SPEC.md */
const ViewRegwatch = (() => {

  function _getSevLabels() {
    return {
      cosmetic:      t('regwatch.sev_cosmetic'),
      clarification: t('regwatch.sev_clarification'),
      substantive:   t('regwatch.sev_substantive'),
      breaking:      t('regwatch.sev_breaking'),
    };
  }

  const SEV_COLORS = {
    cosmetic: '#9CA3AF', clarification: 'var(--risk-low)',
    substantive: 'var(--risk-high)', breaking: 'var(--risk-critical)',
  };

  function _sevBadge(sev) {
    const c = SEV_COLORS[sev] || '#9CA3AF';
    const labels = _getSevLabels();
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${c};color:#fff;">${labels[sev] || sev}</span>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('regwatch.title')}</h1>
          <p class="page-sub">${t('regwatch.subtitle')}</p>
        </div>
      </div>
      <div id="rw-card"></div>
      <div id="rw-inbox" style="margin-top:16px;"></div>
      <div id="rw-history" style="margin-top:16px;"></div>
      <p style="font-size:12px;color:var(--text-muted);margin-top:18px;">
        ${t('regwatch.disclaimer')}
      </p>
    `;
    await _load();
  }

  async function _load() {
    try {
      const [status, settings, watched] = await Promise.all([
        Api.regwatch.status(),
        Api.regwatch.getSettings(),
        Api.regwatch.watchedFrameworks(),
      ]);
      _renderCard(status, settings, watched);
      await _loadInbox();
      await _loadHistory();
    } catch (e) {
      document.getElementById('rw-card').innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _timeAgo(iso) {
    if (!iso) return t('regwatch.since_pending');
    const then = new Date(iso).getTime();
    if (isNaN(then)) return t('regwatch.since_pending');
    const hours = Math.floor((Date.now() - then) / 3600000);
    if (hours < 1) return t('regwatch.since_lt_1h');
    if (hours < 24) return t('regwatch.since_hours', {n: hours});
    return t('regwatch.since_days', {n: Math.floor(hours / 24)});
  }

  function _headline(status) {
    if (status.state === 'inactive') return t('regwatch.headline_inactive');
    if (status.state === 'active_pending') return t('regwatch.headline_pending', {n: status.pending_count});
    return t('regwatch.headline_ok', {when: _timeAgo(status.last_sweep_at)});
  }

  function _renderCard(status, settings, watched) {
    const wrap = document.getElementById('rw-card');
    const on = status.is_enabled;
    const dotColor = !on ? '#9CA3AF' : (status.pending_count > 0 ? 'var(--brand-orange)' : 'var(--risk-low)');
    const la = status.last_applied;
    const canEdit = Auth.isAdmin();

    wrap.innerHTML = `
      <div class="card">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;">
          <div style="flex:1;min-width:260px;">
            <h3 style="margin:0 0 6px;">${t('regwatch.card_title')}</h3>
            <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;max-width:560px;">
              ${t('regwatch.card_desc')}
            </p>
            <div style="display:flex;align-items:center;gap:8px;font-size:13px;">
              <span style="width:10px;height:10px;border-radius:50%;background:${dotColor};display:inline-block;"></span>
              <span><b>${UI.esc(_headline(status))}</b></span>
              ${status.pending_count > 0 ? `<button class="btn btn-sm" id="rw-goto-inbox">${t('regwatch.goto_inbox')}</button>` : ''}
            </div>
            ${la ? `<p style="font-size:12px;color:var(--text-muted);margin:8px 0 0;">${t('regwatch.last_update')} ${UI.esc(la.framework)} — ${UI.esc(la.title)}${la.applied_at ? ' · ' + _fmtDate(la.applied_at) : ''}</p>` : ''}
          </div>
          <div style="text-align:right;">
            <label class="rw-switch" title="${canEdit ? t('regwatch.toggle_title_admin') : t('regwatch.toggle_title_readonly')}">
              <input type="checkbox" id="rw-toggle" ${on ? 'checked' : ''} ${canEdit ? '' : 'disabled'}>
              <span class="rw-slider"></span>
            </label>
            <div style="font-size:11px;color:var(--text-muted);margin-top:4px;">${on ? t('regwatch.toggle_active') : t('regwatch.toggle_inactive')}</div>
          </div>
        </div>

        <div style="margin-top:14px;border-top:1px solid var(--border);padding-top:12px;">
          <a href="#" id="rw-adv-toggle" style="font-size:13px;color:var(--brand-purple);text-decoration:none;">
            &#9656; ${t('regwatch.adv_options')}</a>
          <div id="rw-adv" style="display:none;margin-top:12px;"></div>
        </div>
      </div>
    `;

    // Estilos del switch (una vez)
    if (!document.getElementById('rw-switch-styles')) {
      const st = document.createElement('style');
      st.id = 'rw-switch-styles';
      st.textContent = `
        .rw-switch{position:relative;display:inline-block;width:52px;height:28px;}
        .rw-switch input{opacity:0;width:0;height:0;}
        .rw-slider{position:absolute;cursor:pointer;inset:0;background:#cbd5e1;border-radius:999px;transition:.2s;}
        .rw-slider:before{content:"";position:absolute;height:22px;width:22px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.2s;}
        .rw-switch input:checked + .rw-slider{background:var(--brand-purple);}
        .rw-switch input:checked + .rw-slider:before{transform:translateX(24px);}
        .rw-switch input:disabled + .rw-slider{opacity:.5;cursor:not-allowed;}
      `;
      document.head.appendChild(st);
    }

    const toggle = document.getElementById('rw-toggle');
    if (toggle && canEdit) {
      toggle.onchange = () => toggle.checked ? _confirmEnable(toggle, watched) : _doDisable(toggle);
    }
    const goto = document.getElementById('rw-goto-inbox');
    if (goto) goto.onclick = () => document.getElementById('rw-inbox').scrollIntoView({ behavior: 'smooth' });

    const advToggle = document.getElementById('rw-adv-toggle');
    advToggle.onclick = (e) => {
      e.preventDefault();
      const adv = document.getElementById('rw-adv');
      const open = adv.style.display === 'none';
      adv.style.display = open ? 'block' : 'none';
      advToggle.innerHTML = (open ? '&#9662; ' : '&#9656; ') + t('regwatch.adv_options');
      if (open && !adv.dataset.loaded) { _renderAdvanced(adv, settings, watched, canEdit); adv.dataset.loaded = '1'; }
    };
  }

  function _renderAdvanced(adv, settings, watched, canEdit) {
    const freqOpts = ['daily', 'weekly', 'monthly', 'never'];
    const freqLabel = {
      daily:   t('regwatch.freq_daily'),
      weekly:  t('regwatch.freq_weekly'),
      monthly: t('regwatch.freq_monthly'),
      never:   t('regwatch.freq_never'),
    };
    adv.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
        <div>
          <label style="font-size:12px;font-weight:600;">${t('regwatch.adv_email_label')}</label>
          <input type="email" id="rw-email" value="${UI.esc(settings.notification_email || '')}" ${canEdit ? '' : 'disabled'} style="width:100%;">
        </div>
        <div>
          <label style="font-size:12px;font-weight:600;">${t('regwatch.adv_freq_label')}</label>
          <select id="rw-freq" ${canEdit ? '' : 'disabled'} style="width:100%;">
            ${freqOpts.map(f => `<option value="${f}" ${settings.digest_frequency === f ? 'selected' : ''}>${freqLabel[f]}</option>`).join('')}
          </select>
        </div>
        <div class="span2">
          <label style="font-size:13px;display:flex;align-items:center;gap:8px;cursor:pointer;">
            <input type="checkbox" id="rw-autoapply" ${settings.auto_apply_to_clones ? 'checked' : ''} ${canEdit ? '' : 'disabled'}>
            ${t('regwatch.adv_autoapply_label')}
          </label>
          <p style="font-size:11px;color:var(--text-muted);margin:4px 0 0;">${t('regwatch.adv_autoapply_desc')}</p>
        </div>
      </div>
      <div style="margin-top:14px;">
        <label style="font-size:12px;font-weight:600;">${t('regwatch.adv_frameworks_label')}</label>
        <div id="rw-frameworks" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;">
          ${watched.length ? watched.map(f => `
            <span class="badge badge-muted" title="${UI.esc((f.sources || []).join(', '))}" style="${f.muted ? 'opacity:.5;' : ''}">${UI.esc(f.label)}</span>
          `).join('') : `<span style="font-size:12px;color:var(--text-muted);">${t('regwatch.adv_no_frameworks')}</span>`}
        </div>
      </div>
      ${canEdit ? `<div style="margin-top:14px;text-align:right;"><button class="btn btn-primary btn-sm" id="rw-save-adv">${t('regwatch.adv_save')}</button></div>` : ''}
    `;
    const save = document.getElementById('rw-save-adv');
    if (save) save.onclick = async () => {
      save.disabled = true;
      try {
        await Api.regwatch.updateSettings({
          notification_email: document.getElementById('rw-email').value || null,
          digest_frequency: document.getElementById('rw-freq').value,
          auto_apply_to_clones: document.getElementById('rw-autoapply').checked,
        });
        UI.toast(t('regwatch.adv_saved'), 'success');
      } catch (e) { UI.toast(e.message, 'error'); }
      save.disabled = false;
    };
  }

  async function _confirmEnable(toggle, watched) {
    const n = watched.length;
    const ok = await UI.confirm(t('regwatch.enable_confirm', {n}));
    if (!ok) { toggle.checked = false; return; }
    try {
      const r = await Api.regwatch.enable();
      UI.toast(t('regwatch.enabled_toast', {n: r.watched_count}), 'success');
      await _load();
    } catch (e) { UI.toast(e.message, 'error'); toggle.checked = false; }
  }

  async function _doDisable(toggle) {
    try {
      await Api.regwatch.disable();
      UI.toast(t('regwatch.disabled_toast'), 'info');
      await _load();
    } catch (e) { UI.toast(e.message, 'error'); toggle.checked = true; }
  }

  async function _loadInbox() {
    const wrap = document.getElementById('rw-inbox');
    try {
      const data = await Api.regwatch.inbox();
      const items = data.items || [];
      if (!items.length) { wrap.innerHTML = ''; return; }
      wrap.innerHTML = `
        <div class="card">
          <h3 style="margin-top:0;">${t('regwatch.inbox_title', {n: items.length})}</h3>
          ${items.map(_inboxRow).join('')}
        </div>
      `;
      items.forEach(it => {
        const rev = document.getElementById('rw-review-' + it.id);
        const snz = document.getElementById('rw-snooze-' + it.id);
        if (rev) rev.onclick = () => _openWizard(it);
        if (snz) snz.onclick = async () => {
          try { await Api.regwatch.snooze(it.id, 7); UI.toast(t('regwatch.inbox_snoozed'), 'info'); await _loadInbox(); await _refreshStatus(); }
          catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  function _inboxRow(it) {
    const cc = it.change_counts || {};
    const imp = it.impact || {};
    const badges = _impactBadges(imp);
    return `
      <div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:10px;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
          <div style="flex:1;min-width:240px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
              ${_sevBadge(it.severity)}
              <b>${UI.esc(it.framework)}${it.version_to ? ' — ' + UI.esc(it.version_to) : ''}</b>
            </div>
            <div style="font-size:13px;margin-bottom:6px;">${UI.esc(it.title)}</div>
            <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px;">
              ${t('regwatch.inbox_modified', {n: cc.modified || 0})} · ${t('regwatch.inbox_added', {n: cc.added || 0})} · ${t('regwatch.inbox_removed', {n: cc.removed || 0})}
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;">${badges}</div>
          </div>
          <div style="display:flex;gap:6px;flex-shrink:0;">
            <button class="btn btn-primary btn-sm" id="rw-review-${it.id}">${t('regwatch.inbox_review')}</button>
            <button class="btn btn-sm" id="rw-snooze-${it.id}">${t('regwatch.inbox_snooze')}</button>
          </div>
        </div>
      </div>
    `;
  }

  async function _openWizard(it) {
    let detail = it;
    try { detail = await Api.regwatch.inboxItem(it.id); } catch (_) { /* usa it */ }
    const imp = detail.impact || {};
    const totalImpact = (imp.policies || 0) + (imp.compliance_requirements || 0) +
                        (imp.control_implementations || 0) + (imp.bcp_plans || 0);
    const mods = detail.controls_modified || [];

    const techDetail = mods.length ? `
      <div style="margin-top:8px;font-size:12px;">
        <table class="data" style="width:100%;"><thead><tr>
          <th>${t('regwatch.col_control')}</th><th>${t('regwatch.col_field')}</th>
          <th>${t('regwatch.col_before')}</th><th>${t('regwatch.col_after')}</th>
        </tr></thead><tbody>
        ${mods.slice(0, 20).map(m => `<tr><td>${UI.esc(m.control_id || '')}</td><td>${UI.esc(m.field || '')}</td><td>${UI.esc(String(m.before || '').slice(0, 60))}</td><td>${UI.esc(String(m.after || '').slice(0, 60))}</td></tr>`).join('')}
        </tbody></table>
      </div>` : '';

    const impactBadges = _impactBadges(imp);

    const body = `
      <div>
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">${_sevBadge(detail.severity)}<b>${UI.esc(detail.framework)}</b></div>
        <p style="font-size:13px;">${UI.esc(detail.title)}</p>
        <p style="font-size:13px;color:var(--text-muted);">${UI.esc(detail.summary || '')}</p>
        <details style="margin-top:8px;"><summary style="cursor:pointer;font-size:13px;color:var(--brand-purple);">${t('regwatch.wizard_tech_detail')}</summary>${techDetail || `<p style="font-size:12px;color:var(--text-muted);margin-top:6px;">${t('regwatch.wizard_tech_none')}</p>`}</details>
        <hr style="border:none;border-top:1px solid var(--border);margin:12px 0;">
        ${totalImpact > 0 ? `
          <p style="font-size:13px;font-weight:600;margin:0 0 8px;">${t('regwatch.wizard_impact_heading')}</p>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;">${impactBadges}</div>
          <div style="display:flex;gap:12px;flex-direction:column;">
            <label style="font-size:13px;display:flex;gap:8px;align-items:flex-start;cursor:pointer;">
              <input type="radio" name="rw-decision" value="apply" checked style="margin-top:3px;">
              <span><b>${t('regwatch.wizard_apply')}</b> — ${t('regwatch.wizard_apply_desc')}</span>
            </label>
            <label style="font-size:13px;display:flex;gap:8px;align-items:flex-start;cursor:pointer;">
              <input type="radio" name="rw-decision" value="keep_my_version" style="margin-top:3px;">
              <span><b>${t('regwatch.wizard_keep')}</b> — ${t('regwatch.wizard_keep_desc')}</span>
            </label>
          </div>
        ` : `
          <p style="font-size:13px;color:var(--text-muted);">${t('regwatch.wizard_no_impact')}</p>
        `}
        <div id="rw-w-result" style="display:none;margin-top:12px;padding:10px;background:var(--bg-subtle,#f8fafc);border-radius:6px;font-size:13px;"></div>
      </div>
    `;
    UI.modal(t('regwatch.wizard_title'), body, {
      actions: `<button class="btn" id="rw-w-cancel">${t('regwatch.wizard_cancel')}</button>
                <button class="btn btn-primary" id="rw-w-apply-btn">${t('regwatch.wizard_confirm')}</button>`,
    });
    document.getElementById('rw-w-cancel').onclick = UI.closeModal;
    document.getElementById('rw-w-apply-btn').onclick = async () => {
      const btn = document.getElementById('rw-w-apply-btn');
      btn.disabled = true;
      const radioEl = document.querySelector('input[name="rw-decision"]:checked');
      const action = radioEl ? radioEl.value : 'apply';
      const decision = { action };
      try {
        const resp = await Api.regwatch.review(detail.id, decision);
        const prop = resp.propagation || {};
        if (action === 'apply' && Object.keys(prop).length) {
          const res = document.getElementById('rw-w-result');
          res.style.display = 'block';
          res.innerHTML = `<b>${t('regwatch.wizard_applied')}</b><br>${_propagationSummary(prop)}`;
          btn.textContent = t('regwatch.wizard_close');
          btn.disabled = false;
          btn.onclick = async () => { UI.closeModal(); await _loadInbox(); await _refreshStatus(); };
        } else {
          UI.toast(action === 'apply' ? t('regwatch.wizard_toast_apply') : t('regwatch.wizard_toast_keep'), 'success');
          UI.closeModal();
          await _loadInbox();
          await _refreshStatus();
        }
      } catch (e) { UI.toast(e.message, 'error'); btn.disabled = false; }
    };
  }

  function _impactBadges(imp) {
    const items = [
      { key: 'control_implementations', label: t('regwatch.impact_controls'), color: 'var(--brand-purple)' },
      { key: 'policies',                label: t('regwatch.impact_policies'),  color: 'var(--brand-orange)' },
      { key: 'compliance_requirements', label: t('regwatch.impact_requirements'), color: 'var(--risk-high)' },
      { key: 'bcp_plans',               label: t('regwatch.impact_bcp'),       color: '#0EA5E9' },
      { key: 'risks',                   label: t('regwatch.impact_risks'),      color: '#F59E0B' },
    ];
    return items
      .filter(i => (imp[i.key] || 0) > 0)
      .map(i => `<span style="padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;background:${i.color};color:#fff;">${imp[i.key]} ${i.label}</span>`)
      .join('') || `<span style="font-size:12px;color:var(--text-muted);">${t('regwatch.impact_none')}</span>`;
  }

  function _propagationSummary(prop) {
    const map = {
      catalog_controls_updated:         t('regwatch.prop_controls'),
      control_implementations_flagged:  t('regwatch.prop_soa'),
      policies_flagged:                 t('regwatch.prop_policies'),
      bcp_plans_flagged:                t('regwatch.prop_bcp'),
      supplier_questionnaires_flagged:  t('regwatch.prop_questionnaires'),
      compliance_requirements_flagged:  t('regwatch.prop_compliance'),
      tasks_created:                    t('regwatch.prop_tasks'),
    };
    const lines = Object.entries(map)
      .filter(([k]) => (prop[k] || 0) > 0)
      .map(([k, label]) => `<span style="display:block;padding:2px 0;">&#x2714; ${prop[k]} ${label}</span>`);
    return lines.length ? lines.join('') : t('regwatch.prop_none');
  }

  async function _loadHistory() {
    const wrap = document.getElementById('rw-history');
    const _locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
    try {
      const rows = await Api.regwatch.history();
      wrap.innerHTML = `
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <h3 style="margin:0;">${t('regwatch.history_title')}</h3>
            ${rows.length ? `<button class="btn btn-sm" id="rw-pdf">${t('regwatch.history_export')}</button>` : ''}
          </div>
          ${rows.length ? `
            <table class="data" style="margin-top:10px;"><thead><tr>
              <th>${t('regwatch.col_date')}</th>
              <th>${t('regwatch.col_framework')}</th>
              <th>${t('regwatch.col_severity')}</th>
              <th>${t('regwatch.col_change')}</th>
            </tr></thead><tbody>
            ${rows.map(r => `<tr>
              <td>${_fmtDate(r.applied_at || r.published_at)}</td>
              <td>${UI.esc(r.framework)}</td>
              <td>${_sevBadge(r.severity)}</td>
              <td>${UI.esc(r.title)}</td>
            </tr>`).join('')}
            </tbody></table>
          ` : `<p class="text-muted" style="margin-top:8px;">${t('regwatch.history_none')}</p>`}
        </div>
      `;
      const pdf = document.getElementById('rw-pdf');
      if (pdf) pdf.onclick = () => Api.regwatch.historyPdf();
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  async function _refreshStatus() {
    try {
      const [status, settings, watched] = await Promise.all([
        Api.regwatch.status(), Api.regwatch.getSettings(), Api.regwatch.watchedFrameworks(),
      ]);
      _renderCard(status, settings, watched);
    } catch (_) { /* silencioso */ }
  }

  function _fmtDate(iso) {
    if (!iso) return '-';
    const _locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
    try { return new Date(iso).toLocaleDateString(_locale); } catch (_) { return iso.slice(0, 10); }
  }

  return { render };
})();
