/* Vista de configuración del Trust Portal y Auditor Portal. */
const ViewTrustPortal = (() => {

  async function render(el) {
    el.innerHTML = `
      <div style="max-width:900px;margin:0 auto;padding:24px 0;">
        <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0 0 4px;">
          Trust Portal y Auditor Portal
        </h1>
        <p style="color:#9d9d9d;font-size:13px;margin:0 0 20px;">
          Comparte el estado de cumplimiento con clientes y auditores externos
        </p>
        <div id="portal-content"><div style="text-align:center;padding:40px;color:#9d9d9d;">Cargando...</div></div>
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
            <h2 style="font-size:16px;font-weight:700;color:var(--brand-purple);margin:0;">Trust Portal</h2>
            <p style="font-size:12px;color:#9d9d9d;margin:4px 0 0;">
              Página pública de cumplimiento — compártela con clientes y prospects
            </p>
          </div>
          <span style="background:#E3F2FD;color:#1565c0;padding:4px 10px;border-radius:8px;font-size:11px;font-weight:600;">
            PÚBLICO
          </span>
        </div>
        <div style="background:#f9f9f9;border-radius:6px;padding:12px;margin-bottom:12px;display:flex;gap:8px;align-items:center;">
          <input type="text" value="${UI.esc(publicUrl)}" readonly
                 style="flex:1;border:none;background:transparent;font-size:12px;font-family:monospace;color:#444;">
          <button onclick="navigator.clipboard.writeText('${UI.esc(publicUrl)}');UI.toast('URL copiada','success')"
                  class="btn-outline" style="font-size:11px;padding:3px 8px;">Copiar</button>
          <a href="${UI.esc(publicUrl)}" target="_blank" class="btn-outline" style="font-size:11px;padding:3px 8px;">
            Ver
          </a>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px;">
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
            <input type="checkbox" id="tp-show-frameworks" ${cfg.show_frameworks ? 'checked' : ''}> Mostrar cumplimiento por framework
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
            <input type="checkbox" id="tp-show-risks" ${cfg.show_risks_summary ? 'checked' : ''}> Mostrar resumen de riesgos
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
            <input type="checkbox" id="tp-show-audit" ${cfg.show_last_audit ? 'checked' : ''}> Mostrar última auditoría
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
            <input type="checkbox" id="tp-enabled" ${cfg.enabled ? 'checked' : ''}> Portal activo
          </label>
        </div>
        <div style="margin-bottom:12px;">
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">Mensaje personalizado (opcional)</label>
          <textarea id="tp-message" class="input-field" rows="2" style="width:100%;" placeholder="Bienvenido a nuestro portal de confianza...">${UI.esc(cfg.custom_message || '')}</textarea>
        </div>
        <div style="display:flex;gap:8px;">
          <button onclick="ViewTrustPortal._saveTrust()" class="btn-primary" style="font-size:13px;">Guardar configuración</button>
          <button onclick="ViewTrustPortal._regenerateTrustToken()" class="btn-outline" style="font-size:13px;color:#a83232;">
            Regenerar token (invalida URL actual)
          </button>
        </div>
      </div>`;
  }

  function _auditorCard(cfg) {
    if (!cfg) return '';
    const auditorUrl = `${location.origin}${cfg.auditor_url || ''}`;
    return `
      <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
          <div>
            <h2 style="font-size:16px;font-weight:700;color:var(--brand-purple);margin:0;">Portal de Auditor</h2>
            <p style="font-size:12px;color:#9d9d9d;margin:4px 0 0;">
              Acceso de solo lectura para auditores externos — incluye evidencias, gaps y requisitos
            </p>
          </div>
          <span style="background:#FEF0E3;color:#c25a1f;padding:4px 10px;border-radius:8px;font-size:11px;font-weight:600;">
            PRIVADO (TOKEN)
          </span>
        </div>
        <div style="background:#f9f9f9;border-radius:6px;padding:12px;margin-bottom:12px;display:flex;gap:8px;align-items:center;">
          <input type="text" value="${UI.esc(auditorUrl)}" readonly
                 style="flex:1;border:none;background:transparent;font-size:12px;font-family:monospace;color:#444;">
          <button onclick="navigator.clipboard.writeText('${UI.esc(auditorUrl)}');UI.toast('URL copiada','success')"
                  class="btn-outline" style="font-size:11px;padding:3px 8px;">Copiar</button>
        </div>
        <p style="font-size:12px;color:#9d9d9d;margin-bottom:12px;">
          Esta URL da acceso de solo lectura al estado de cumplimiento, evidencias y gaps.
          Solo compártela con tu auditor externo. Puedes revocarla regenerando el token.
        </p>
        <div style="display:flex;gap:8px;">
          <button onclick="ViewTrustPortal._regenerateAuditorToken()" class="btn-outline"
                  style="font-size:13px;color:#a83232;">
            Regenerar token (invalida URL actual)
          </button>
        </div>
      </div>`;
  }

  async function _saveTrust() {
    const body = {
      enabled: document.getElementById('tp-enabled').checked,
      show_frameworks: document.getElementById('tp-show-frameworks').checked,
      show_risks_summary: document.getElementById('tp-show-risks').checked,
      show_last_audit: document.getElementById('tp-show-audit').checked,
      custom_message: document.getElementById('tp-message').value.trim() || null,
    };
    try {
      await Api.put('/api/portal/trust/config', body);
      UI.toast('Trust Portal guardado', 'success');
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _regenerateTrustToken() {
    if (!confirm('¿Regenerar token? La URL actual dejará de funcionar.')) return;
    try {
      await Api.post('/api/portal/trust/regenerate-token', {});
      UI.toast('Token regenerado', 'success');
      _load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _regenerateAuditorToken() {
    if (!confirm('¿Regenerar token de auditor? La URL actual dejará de funcionar.')) return;
    try {
      await Api.post('/api/portal/auditor/regenerate-token', {});
      UI.toast('Token de auditor regenerado', 'success');
      _load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  return { render, _saveTrust, _regenerateTrustToken, _regenerateAuditorToken };
})();
