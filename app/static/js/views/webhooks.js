/* Vista de configuración de webhooks. */
const ViewWebhooks = (() => {

  let _availableEvents = [];

  async function _loadEvents() {
    try { _availableEvents = await Api.webhooks.events(); } catch (_) {}
  }

  function _createModal(existing) {
    const isEdit = !!existing;
    const ev = existing || {};
    UI.openModal(`
      <h3 style="margin:0 0 16px;color:var(--brand-purple);">${isEdit ? t('webhooks.modal_title_edit') : t('webhooks.modal_title_new')}</h3>
      <div style="display:grid;gap:12px;">
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('webhooks.name_label')}</label>
          <input id="wh-name" class="input-field" style="width:100%;" value="${UI.esc(ev.name || '')}">
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('webhooks.url_label')}</label>
          <input id="wh-url" class="input-field" style="width:100%;"
                 placeholder="${t('webhooks.url_placeholder')}" value="${UI.esc(ev.url || '')}">
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('webhooks.secret_label')}</label>
          <input id="wh-secret" class="input-field" style="width:100%;" type="password"
                 placeholder="${t('webhooks.secret_placeholder')}">
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:8px;">${t('webhooks.events_label')}</label>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;">
              <input type="checkbox" id="wh-ev-all" onchange="ViewWebhooks._toggleAll(this)">
              <strong>${t('webhooks.all_events')}</strong>
            </label>
            ${_availableEvents.map(e => `
              <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;">
                <input type="checkbox" class="wh-ev-cb" value="${UI.esc(e.event)}"
                       ${(ev.events || []).includes(e.event) ? 'checked' : ''}>
                ${UI.esc(e.description)}
              </label>`).join('')}
          </div>
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('webhooks.retry_label')}</label>
          <input id="wh-retry" type="number" min="1" max="5" class="input-field"
                 style="width:80px;" value="${ev.retry_count || 3}">
        </div>
        ${isEdit ? `<label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;">
          <input type="checkbox" id="wh-active" ${ev.is_active ? 'checked' : ''}> ${t('webhooks.active_label')}
        </label>` : ''}
      </div>
      <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;">
        <button onclick="UI.closeModal()" class="btn-outline">${t('webhooks.cancel_btn')}</button>
        <button onclick="ViewWebhooks._submit(${isEdit ? ev.id : 'null'})" class="btn-primary">
          ${isEdit ? t('webhooks.save_btn') : t('webhooks.create_btn')}
        </button>
      </div>`);
  }

  function _toggleAll(cb) {
    document.querySelectorAll('.wh-ev-cb').forEach(c => c.checked = cb.checked);
  }

  async function _submit(id) {
    const name = document.getElementById('wh-name').value.trim();
    const url = document.getElementById('wh-url').value.trim();
    const secret = document.getElementById('wh-secret').value.trim();
    const retry = parseInt(document.getElementById('wh-retry').value) || 3;
    const activeEl = document.getElementById('wh-active');
    const is_active = activeEl ? activeEl.checked : true;

    const allCb = document.getElementById('wh-ev-all');
    let events;
    if (allCb && allCb.checked) {
      events = ['*'];
    } else {
      events = [...document.querySelectorAll('.wh-ev-cb:checked')].map(c => c.value);
    }

    if (!name || !url) { UI.toast(t('webhooks.name_url_required'), 'error'); return; }
    if (!events.length) { UI.toast(t('webhooks.event_required'), 'error'); return; }

    const body = { name, url, events, retry_count: retry, is_active };
    if (secret) body.secret = secret;

    try {
      if (id) {
        await Api.webhooks.update(id, body);
        UI.toast(t('webhooks.updated_toast'), 'success');
      } else {
        await Api.webhooks.create(body);
        UI.toast(t('webhooks.created_toast'), 'success');
      }
      UI.closeModal();
      _load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _del(id, name) {
    if (!await UI.confirm(t('webhooks.delete_confirm', { name }))) return;
    try {
      await Api.webhooks.del(id);
      UI.toast(t('webhooks.deleted_toast'), 'success');
      _load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _test(id) {
    UI.toast(t('common.loading'), 'info');
    try {
      const r = await Api.webhooks.test(id);
      const s = r.triggered !== 1 ? 's' : '';
      UI.toast(t('webhooks.test_sent', { n: r.triggered, s }), 'success');
    } catch (e) {
      UI.toast(t('webhooks.test_error', { msg: e.message }), 'error');
    }
  }

  async function _load() {
    const container = document.getElementById('wh-list');
    if (!container) return;
    try {
      const whs = await Api.webhooks.list();
      if (!whs.length) {
        container.innerHTML = `<div style="text-align:center;padding:48px;color:#9d9d9d;">${t('webhooks.no_webhooks')}</div>`;
        return;
      }
      container.innerHTML = whs.map(wh => `
        <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:16px;
                    display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
          <div style="flex:1;min-width:200px;">
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="font-weight:600;">${UI.esc(wh.name)}</span>
              <span style="background:${wh.is_active ? '#E8F5E9' : '#f0f0f0'};
                           color:${wh.is_active ? '#2e7d32' : '#9d9d9d'};
                           padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">
                ${wh.is_active ? t('webhooks.status.active') : t('webhooks.status.inactive')}
              </span>
            </div>
            <div style="font-size:12px;color:#9d9d9d;margin-top:4px;word-break:break-all;">
              ${UI.esc(wh.url)}
            </div>
            <div style="font-size:11px;color:#bbb;margin-top:4px;">
              ${t('webhooks.events_list', { events: (wh.events || []).join(', ') || '—' })} |
              ${t('webhooks.last_trigger', { date: wh.last_triggered_at ? wh.last_triggered_at.slice(0, 16).replace('T', ' ') : t('webhooks.never') })}
            </div>
          </div>
          <div style="display:flex;gap:6px;">
            <button onclick="ViewWebhooks._test(${wh.id})" class="btn-outline" style="font-size:12px;padding:4px 10px;">
              ${t('webhooks.test_btn')}
            </button>
            <button onclick="ViewWebhooks._createModal(${JSON.stringify(wh).replace(/"/g, '&quot;')})"
                    class="btn-outline" style="font-size:12px;padding:4px 10px;">${t('webhooks.edit_btn')}</button>
            <button onclick="ViewWebhooks._del(${wh.id},'${UI.esc(wh.name)}')"
                    style="background:none;border:1px solid #a83232;color:#a83232;border-radius:6px;
                           font-size:12px;padding:4px 10px;cursor:pointer;">${t('webhooks.delete_btn')}</button>
          </div>
        </div>`).join('');
    } catch (e) {
      container.innerHTML = `<div style="color:var(--risk-critical);padding:16px;">Error: ${UI.esc(e.message)}</div>`;
    }
  }

  async function render(el) {
    await _loadEvents();
    el.innerHTML = `
      <div style="max-width:900px;margin:0 auto;padding:24px 0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
          <div>
            <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0;">${t('webhooks.title')}</h1>
            <p style="color:#9d9d9d;font-size:13px;margin:4px 0 0;">${t('webhooks.subtitle')}</p>
          </div>
          <button onclick="ViewWebhooks._createModal(null)" class="btn-primary">${t('webhooks.new_btn')}</button>
        </div>
        <div id="wh-list" style="display:grid;gap:12px;">
          <div style="text-align:center;padding:32px;color:#9d9d9d;">${t('webhooks.loading')}</div>
        </div>
      </div>`;
    await _load();
  }

  return { render, _createModal, _toggleAll, _submit, _del, _test, _load };
})();
