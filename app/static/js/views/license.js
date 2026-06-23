/* Vista de licencia criptografica on-premise — solo admin. */
const ViewLicense = (() => {

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('crypto_license.page_title')}</h1>
          <p class="page-sub">${t('crypto_license.page_subtitle')}</p>
        </div>
      </div>
      <div id="lic-body" style="max-width:720px;display:grid;gap:20px;"></div>
    `;
    await _load(document.getElementById('lic-body'));
  }

  async function _load(wrap) {
    wrap.innerHTML = `<p class="text-muted">${t('common.loading')}</p>`;
    try {
      const data = await Api.get('/api/license/status');
      _render(wrap, data);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _statusLabel(data) {
    if (!data.present)  return { label: t('crypto_license.status_absent'),  color: 'var(--text-muted)' };
    if (!data.valid)    return { label: t('crypto_license.status_invalid'), color: 'var(--danger,#ef4444)' };
    if (data.expired && !data.in_grace) return { label: t('crypto_license.status_expired'), color: 'var(--danger,#ef4444)' };
    if (data.in_grace)  return { label: t('crypto_license.status_grace'),   color: '#F39C12' };
    return { label: t('crypto_license.status_valid'), color: 'var(--success,#22c55e)' };
  }

  function _render(wrap, data) {
    const st = _statusLabel(data);
    const locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
    const fmt = (iso) => iso ? new Date(iso).toLocaleDateString(locale) : '—';

    const modulesText = !data.modules || data.modules.includes('all')
      ? t('crypto_license.modules_all')
      : data.modules.join(', ');

    let alertHtml = '';
    if (data.expired && !data.in_grace) {
      alertHtml = `
        <div style="padding:14px 16px;background:var(--danger-bg,#fef2f2);border:1px solid var(--danger,#ef4444);
                    border-radius:8px;color:var(--danger,#ef4444);font-size:13px;">
          ${t('crypto_license.expired_info')}
        </div>`;
    } else if (data.in_grace) {
      const graceLeft = data.grace_days - Math.max(0, data.days_left !== null ? 0 : 0);
      alertHtml = `
        <div style="padding:14px 16px;background:#fff8e1;border:1px solid #F39C12;
                    border-radius:8px;color:#7B5800;font-size:13px;">
          ${t('crypto_license.grace_info', { n: graceLeft })}
        </div>`;
    }

    wrap.innerHTML = `
      ${alertHtml}

      <div class="card" style="padding:20px;display:grid;gap:14px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <h3 style="margin:0;font-size:15px;font-weight:600;">${t('crypto_license.page_title')}</h3>
          <span style="font-weight:700;color:${st.color};">${st.label}</span>
        </div>

        ${data.present ? `
          <table style="border-collapse:collapse;width:100%;font-size:13px;">
            <tr>
              <td style="padding:6px 0;color:var(--text-muted);width:160px;">${t('crypto_license.org_label')}</td>
              <td style="padding:6px 0;font-weight:600;">${UI.esc(data.org_name || '—')}</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:var(--text-muted);">${t('crypto_license.plan_label')}</td>
              <td style="padding:6px 0;font-weight:600;text-transform:capitalize;">${UI.esc(data.plan || '—')}</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:var(--text-muted);">${t('crypto_license.issued_label')}</td>
              <td style="padding:6px 0;">${fmt(data.issued_at)}</td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:var(--text-muted);">${t('crypto_license.expires_label')}</td>
              <td style="padding:6px 0;">
                ${fmt(data.expires_at)}
                ${data.days_left !== null && !data.expired
                  ? `<span style="margin-left:8px;font-size:11px;color:var(--success,#22c55e);">${t('crypto_license.days_left', { n: data.days_left })}</span>`
                  : ''}
              </td>
            </tr>
            <tr>
              <td style="padding:6px 0;color:var(--text-muted);">${t('crypto_license.modules_label')}</td>
              <td style="padding:6px 0;">${UI.esc(modulesText)}</td>
            </tr>
          </table>
        ` : `
          <p style="font-size:13px;color:var(--text-muted);margin:0;">${t('crypto_license.no_file_info')}</p>
        `}

        ${data.error && data.present ? `
          <div style="font-size:12px;color:var(--danger,#ef4444);">
            <strong>${t('crypto_license.error_label')}:</strong> ${UI.esc(data.error)}
          </div>
        ` : ''}
      </div>

      <div class="card" style="padding:20px;display:grid;gap:14px;">
        <h3 style="margin:0;font-size:15px;font-weight:600;">${t('crypto_license.upload_title')}</h3>
        <p style="font-size:13px;color:var(--text-muted);margin:0;">${t('crypto_license.reload_info')}</p>
        <div>
          <label style="font-size:13px;font-weight:500;">${t('crypto_license.upload_label')}</label>
          <input type="file" id="lic-file" accept=".jwt,.txt" style="margin-top:6px;">
        </div>
        <div style="display:flex;gap:10px;align-items:center;">
          <button class="btn btn-primary" id="lic-upload-btn">${t('crypto_license.upload_btn')}</button>
          <span id="lic-upload-msg" style="font-size:13px;"></span>
        </div>
      </div>
    `;

    document.getElementById('lic-upload-btn').addEventListener('click', () => _upload(wrap));
  }

  async function _upload(wrap) {
    const fileInput = document.getElementById('lic-file');
    const msg = document.getElementById('lic-upload-msg');
    const file = fileInput?.files?.[0];
    if (!file) return;

    msg.textContent = t('common.loading');
    msg.style.color = 'var(--text-muted)';

    try {
      await Api.postFile('/api/license/upload', file);
      msg.textContent = t('crypto_license.upload_ok');
      msg.style.color = 'var(--success,#22c55e)';
      setTimeout(() => _load(wrap), 800);
    } catch (e) {
      msg.textContent = `${t('crypto_license.upload_error')}: ${e.message}`;
      msg.style.color = 'var(--danger,#ef4444)';
    }
  }

  return { render };
})();
