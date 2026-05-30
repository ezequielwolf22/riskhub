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
      <h3 style="margin:0 0 16px;color:var(--brand-purple);">${isEdit ? 'Editar' : 'Nuevo'} Webhook</h3>
      <div style="display:grid;gap:12px;">
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">Nombre *</label>
          <input id="wh-name" class="input-field" style="width:100%;" value="${UI.esc(ev.name || '')}">
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">URL destino * (debe ser pública)</label>
          <input id="wh-url" class="input-field" style="width:100%;"
                 placeholder="https://hooks.ejemplo.com/..." value="${UI.esc(ev.url || '')}">
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">Secret HMAC (opcional)</label>
          <input id="wh-secret" class="input-field" style="width:100%;" type="password"
                 placeholder="Dejar vacío para no firmar">
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:8px;">Eventos *</label>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;">
              <input type="checkbox" id="wh-ev-all" onchange="ViewWebhooks._toggleAll(this)">
              <strong>Todos los eventos</strong>
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
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">Reintentos (1-5)</label>
          <input id="wh-retry" type="number" min="1" max="5" class="input-field"
                 style="width:80px;" value="${ev.retry_count || 3}">
        </div>
        ${isEdit ? `<label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;">
          <input type="checkbox" id="wh-active" ${ev.is_active ? 'checked' : ''}> Activo
        </label>` : ''}
      </div>
      <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;">
        <button onclick="UI.closeModal()" class="btn-outline">Cancelar</button>
        <button onclick="ViewWebhooks._submit(${isEdit ? ev.id : 'null'})" class="btn-primary">
          ${isEdit ? 'Guardar' : 'Crear webhook'}
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

    if (!name || !url) { UI.toast('Nombre y URL son obligatorios', 'error'); return; }
    if (!events.length) { UI.toast('Selecciona al menos un evento', 'error'); return; }

    const body = { name, url, events, retry_count: retry, is_active };
    if (secret) body.secret = secret;

    try {
      if (id) {
        await Api.webhooks.update(id, body);
        UI.toast('Webhook actualizado', 'success');
      } else {
        await Api.webhooks.create(body);
        UI.toast('Webhook creado', 'success');
      }
      UI.closeModal();
      _load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _del(id, name) {
    if (!confirm(`¿Eliminar webhook "${name}"?`)) return;
    try {
      await Api.webhooks.del(id);
      UI.toast('Webhook eliminado', 'success');
      _load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _test(id) {
    UI.toast('Enviando test...', 'info');
    try {
      const r = await Api.webhooks.test(id);
      UI.toast(`Test enviado (${r.triggered} webhook${r.triggered !== 1 ? 's' : ''})`, 'success');
    } catch (e) {
      UI.toast('Error en test: ' + e.message, 'error');
    }
  }

  async function _load() {
    const container = document.getElementById('wh-list');
    if (!container) return;
    try {
      const whs = await Api.webhooks.list();
      if (!whs.length) {
        container.innerHTML = `<div style="text-align:center;padding:48px;color:#9d9d9d;">
          No hay webhooks configurados. Crea el primero con el botón de arriba.</div>`;
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
                ${wh.is_active ? 'Activo' : 'Inactivo'}
              </span>
            </div>
            <div style="font-size:12px;color:#9d9d9d;margin-top:4px;word-break:break-all;">
              ${UI.esc(wh.url)}
            </div>
            <div style="font-size:11px;color:#bbb;margin-top:4px;">
              Eventos: ${(wh.events || []).join(', ') || '—'} |
              Último: ${wh.last_triggered_at ? wh.last_triggered_at.slice(0,16).replace('T',' ') : 'nunca'}
            </div>
          </div>
          <div style="display:flex;gap:6px;">
            <button onclick="ViewWebhooks._test(${wh.id})" class="btn-outline" style="font-size:12px;padding:4px 10px;">
              Test
            </button>
            <button onclick="ViewWebhooks._createModal(${JSON.stringify(wh).replace(/"/g,'&quot;')})"
                    class="btn-outline" style="font-size:12px;padding:4px 10px;">Editar</button>
            <button onclick="ViewWebhooks._del(${wh.id},'${UI.esc(wh.name)}')"
                    style="background:none;border:1px solid #a83232;color:#a83232;border-radius:6px;
                           font-size:12px;padding:4px 10px;cursor:pointer;">Eliminar</button>
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
            <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0;">Webhooks</h1>
            <p style="color:#9d9d9d;font-size:13px;margin:4px 0 0;">
              Notificaciones HTTP a sistemas externos cuando ocurren eventos en RiskHub
            </p>
          </div>
          <button onclick="ViewWebhooks._createModal(null)" class="btn-primary">+ Nuevo webhook</button>
        </div>
        <div id="wh-list" style="display:grid;gap:12px;">
          <div style="text-align:center;padding:32px;color:#9d9d9d;">Cargando...</div>
        </div>
      </div>`;
    await _load();
  }

  return { render, _createModal, _toggleAll, _submit, _del, _test, _load };
})();
