/* Vista de configuración del Trust Portal y Auditor Portal. */
const ViewTrustPortal = (() => {

  async function render(el) {
    el.innerHTML = `
      <div style="max-width:900px;margin:0 auto;padding:24px 0;">
        <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0 0 4px;">
          ${t('trust_portal.title')}
        </h1>
        <p style="color:#9d9d9d;font-size:13px;margin:0 0 20px;">
          ${t('trust_portal.subtitle')}
        </p>
        <div id="portal-content"><div style="text-align:center;padding:40px;color:#9d9d9d;">${t('trust_portal.loading')}</div></div>
      </div>`;
    await _load();
  }

  async function _load() {
    const el = document.getElementById('portal-content');
    try {
      const [trustCfg, auditorCfg] = await Promise.all([
        Api.get('/api/portal/trust/config').catch(() => null),
        Api.get('/api/portal/auditor/config').catch(() => null),
      ]);
      el.innerHTML = `
        <div style="display:grid;gap:16px;">
          ${_trustCard(trustCfg)}
          ${_auditorCard(auditorCfg)}
        </div>`;
    } catch (e) {
      el.innerHTML = `<div style="color:var(--risk-critical);padding:16px;">Error: ${UI.esc(e.message)}</div>`;
    }
  }

  function _trustCard(cfg) {
    if (!cfg) return '';
    const publicUrl = `${location.origin}${cfg.public_url || ''}`;
    return `
      <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
          <div>
            <h2 style="font-size:16px;font-weight:700;color:var(--brand-purple);margin:0;">${t('trust_portal.trust_title')}</h2>
            <p style="font-size:12px;color:#9d9d9d;margin:4px 0 0;">${t('trust_portal.trust_desc')}</p>
          </div>
          <span style="background:#E3F2FD;color:#1565c0;padding:4px 10px;border-radius:8px;font-size:11px;font-weight:600;">
            ${t('trust_portal.public_label')}
          </span>
        </div>
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:6px;
                    padding:10px 12px;margin-bottom:16px;display:flex;gap:8px;align-items:center;">
          <input type="text" value="${UI.esc(publicUrl)}" readonly
                 class="input" style="flex:1;font-size:12px;font-family:var(--font-mono);">
          <button onclick="navigator.clipboard.writeText('${UI.esc(publicUrl)}');UI.toast(t('trust_portal.url_copied'),'success')"
                  class="btn btn-sm">${t('trust_portal.copy_btn')}</button>
          <a href="${UI.esc(publicUrl)}" target="_blank" class="btn btn-sm">${t('trust_portal.view_btn')}</a>
        </div>
        <div style="display:flex;flex-direction:column;gap:10px;margin-bottom:16px;">
          ${_checkRow('tp-enabled', cfg.enabled, t('trust_portal.portal_active'), t('trust_portal.portal_active_desc'))}
          ${_checkRow('tp-show-frameworks', cfg.show_frameworks, t('trust_portal.show_frameworks'), t('trust_portal.show_frameworks_desc'))}
          ${_checkRow('tp-show-audit', cfg.show_last_audit, t('trust_portal.show_audit'), t('trust_portal.show_audit_desc'))}
          ${_checkRow('tp-show-risks', cfg.show_risks_summary, t('trust_portal.show_risks'), t('trust_portal.show_risks_desc'))}
        </div>
        <div style="margin-bottom:16px;">
          <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:6px;font-weight:600;">
            ${t('trust_portal.custom_msg_label')}
          </label>
          <textarea id="tp-message" class="input" rows="2" style="width:100%;box-sizing:border-box;"
                    placeholder="${t('trust_portal.custom_msg_placeholder')}">${UI.esc(cfg.custom_message || '')}</textarea>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button onclick="ViewTrustPortal._saveTrust()" class="btn btn-primary">${t('trust_portal.save_trust')}</button>
          <button onclick="ViewTrustPortal._regenerateTrustToken()" class="btn"
                  style="color:var(--risk-high);border-color:var(--risk-high);">
            ${t('trust_portal.regen_trust_token')}
          </button>
        </div>
      </div>`;
  }

  function _checkRow(id, checked, label, desc) {
    return `
      <label style="display:flex;align-items:center;gap:10px;font-size:13px;cursor:pointer;
                    padding:10px 12px;border:1px solid var(--border);border-radius:6px;
                    background:var(--bg-2);transition:background .15s;"
             onmouseover="this.style.background='var(--bg-3)'" onmouseout="this.style.background='var(--bg-2)'">
        <input type="checkbox" id="${id}" ${checked ? 'checked' : ''}
               style="width:16px;height:16px;flex-shrink:0;accent-color:var(--brand-purple);">
        <div>
          <div style="font-weight:600;">${label}</div>
          <div style="font-size:11px;color:var(--text-muted);">${desc}</div>
        </div>
      </label>`;
  }

  function _auditorCard(cfg) {
    if (!cfg) return '';
    const auditorUrl = `${location.origin}${cfg.auditor_url || ''}`;
    return `
      <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
          <div>
            <h2 style="font-size:16px;font-weight:700;color:var(--brand-purple);margin:0;">${t('trust_portal.auditor_title')}</h2>
            <p style="font-size:12px;color:#9d9d9d;margin:4px 0 0;">${t('trust_portal.auditor_desc')}</p>
          </div>
          <span style="background:#FEF0E3;color:#c25a1f;padding:4px 10px;border-radius:8px;font-size:11px;font-weight:600;">
            ${t('trust_portal.private_label')}
          </span>
        </div>
        <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:6px;
                    padding:10px 12px;margin-bottom:16px;display:flex;gap:8px;align-items:center;">
          <input type="text" value="${UI.esc(auditorUrl)}" readonly
                 class="input" style="flex:1;font-size:12px;font-family:var(--font-mono);">
          <button onclick="navigator.clipboard.writeText('${UI.esc(auditorUrl)}');UI.toast(t('trust_portal.url_copied'),'success')"
                  class="btn btn-sm">${t('trust_portal.copy_btn')}</button>
        </div>
        <p style="font-size:12px;color:#9d9d9d;margin-bottom:12px;">
          ${t('trust_portal.auditor_readonly_info')}
        </p>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button onclick="ViewTrustPortal._regenerateAuditorToken()" class="btn"
                  style="color:var(--risk-high);border-color:var(--risk-high);">
            ${t('trust_portal.regen_auditor_token')}
          </button>
        </div>
      </div>`;
  }

  async function _saveTrust() {
    const body = {
      enabled:           document.getElementById('tp-enabled').checked,
      show_frameworks:   document.getElementById('tp-show-frameworks').checked,
      show_risks_summary: document.getElementById('tp-show-risks').checked,
      show_last_audit:   document.getElementById('tp-show-audit').checked,
      custom_message:    document.getElementById('tp-message').value.trim() || null,
    };
    try {
      await Api.put('/api/portal/trust/config', body);
      UI.toast(t('trust_portal.trust_saved'), 'success');
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _regenerateTrustToken() {
    if (!await UI.confirm(t('trust_portal.regen_trust_confirm'))) return;
    try {
      await Api.post('/api/portal/trust/regenerate-token', {});
      UI.toast(t('trust_portal.token_regenerated'), 'success');
      _load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _regenerateAuditorToken() {
    if (!await UI.confirm(t('trust_portal.regen_auditor_confirm'))) return;
    try {
      await Api.post('/api/portal/auditor/regenerate-token', {});
      UI.toast(t('trust_portal.auditor_token_regenerated'), 'success');
      _load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  return { render, _saveTrust, _regenerateTrustToken, _regenerateAuditorToken };
})();
