/* Vista de configuración de integraciones ITSM (Jira, ServiceNow, Slack, Teams). */
const ViewItsmConfig = (() => {

  function _statusBadge(configured) {
    return configured
      ? '<span style="background:#E8F5E9;color:#2e7d32;padding:2px 8px;border-radius:8px;font-size:11px;">✓ Configurado</span>'
      : '<span style="background:#f5f5f5;color:#9d9d9d;padding:2px 8px;border-radius:8px;font-size:11px;">Sin configurar</span>';
  }

  async function render(el) {
    el.innerHTML = `
      <div style="max-width:900px;margin:0 auto;padding:24px 0;">
        <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0 0 4px;">
          Integraciones ITSM y Notificaciones
        </h1>
        <p style="color:#9d9d9d;font-size:13px;margin:0 0 20px;">
          Conecta RiskHub con tu ITSM y herramientas de comunicación para notificaciones automáticas
        </p>
        <div id="itsm-content"><div style="text-align:center;padding:40px;color:#9d9d9d;">Cargando...</div></div>
      </div>`;
    await _load();
  }

  async function _load() {
    const el = document.getElementById('itsm-content');
    try {
      const status = await Api.itsm.status();
      el.innerHTML = `
        <div style="display:grid;gap:16px;">
          ${_card('jira', 'Jira', status.jira,
            'Crea tickets automáticamente para riesgos HIGH/CRITICAL',
            'https://www.atlassian.com/jira',
            [
              {label:'URL base (ej: https://tu-empresa.atlassian.net)',id:'jira-url',type:'text'},
              {label:'Clave del proyecto (ej: SEC)',id:'jira-proj',type:'text'},
              {label:'Email',id:'jira-email',type:'email'},
              {label:'API Token',id:'jira-token',type:'password'},
            ])}
          ${_card('servicenow', 'ServiceNow', status.servicenow,
            'Crea incidents automáticamente para riesgos críticos',
            'https://www.servicenow.com',
            [
              {label:'Instancia (ej: mi-empresa)',id:'snow-instance',type:'text'},
              {label:'Usuario',id:'snow-user',type:'text'},
              {label:'Contraseña',id:'snow-pass',type:'password'},
            ])}
          ${_card('slack', 'Slack', status.slack,
            'Notificaciones en tiempo real en canales de Slack',
            'https://slack.com',
            [
              {label:'Webhook URL de Slack (https://hooks.slack.com/...)',id:'slack-url',type:'url'},
            ])}
          ${_card('teams', 'Microsoft Teams', status.teams,
            'Notificaciones en tiempo real en canales de Teams',
            'https://teams.microsoft.com',
            [
              {label:'Webhook URL de Teams (https://...webhook.office.com/...)',id:'teams-url',type:'url'},
            ])}
        </div>`;
    } catch (e) {
      el.innerHTML = `<div style="color:var(--risk-critical);padding:16px;">Error: ${UI.esc(e.message)}</div>`;
    }
  }

  function _card(type, name, configured, description, docsUrl, fields) {
    const fieldInputs = fields.map(f => `
      <div>
        <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${f.label}</label>
        <input id="${f.id}" type="${f.type}" class="input-field" style="width:100%;" autocomplete="off">
      </div>`).join('');

    return `
      <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;overflow:hidden;">
        <div style="padding:16px 20px;display:flex;justify-content:space-between;align-items:center;
                    border-bottom:1px solid #f0f0f0;">
          <div>
            <div style="font-size:15px;font-weight:700;">${name}</div>
            <div style="font-size:12px;color:#9d9d9d;margin-top:2px;">${description}</div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            ${_statusBadge(configured)}
            <button onclick="ViewItsmConfig._toggle('${type}')"
                    class="btn-outline" style="font-size:12px;padding:4px 10px;">
              ${configured ? 'Editar' : 'Configurar'}
            </button>
          </div>
        </div>
        <div id="itsm-form-${type}" style="display:none;padding:16px 20px;">
          <div style="display:grid;gap:10px;margin-bottom:14px;">${fieldInputs}</div>
          <div style="display:flex;gap:8px;">
            <button onclick="ViewItsmConfig._save('${type}')" class="btn-primary" style="font-size:13px;">
              Guardar
            </button>
            <button onclick="ViewItsmConfig._test('${type}')" class="btn-outline" style="font-size:13px;">
              Probar conexión
            </button>
            <button onclick="ViewItsmConfig._toggle('${type}')" class="btn-outline" style="font-size:13px;">
              Cancelar
            </button>
          </div>
        </div>
      </div>`;
  }

  function _toggle(type) {
    const form = document.getElementById(`itsm-form-${type}`);
    if (form) form.style.display = form.style.display === 'none' ? 'block' : 'none';
  }

  async function _save(type) {
    let body = {};
    try {
      if (type === 'jira') {
        body = {
          base_url: document.getElementById('jira-url').value.trim(),
          project_key: document.getElementById('jira-proj').value.trim(),
          email: document.getElementById('jira-email').value.trim(),
          api_token: document.getElementById('jira-token').value.trim(),
          auto_create_issues: true,
        };
        await Api.itsm.jira.saveConfig(body);
      } else if (type === 'servicenow') {
        body = {
          instance: document.getElementById('snow-instance').value.trim(),
          username: document.getElementById('snow-user').value.trim(),
          password: document.getElementById('snow-pass').value.trim(),
          auto_create_incidents: true,
        };
        await Api.itsm.servicenow.saveConfig(body);
      } else if (type === 'slack') {
        body = { webhook_url: document.getElementById('slack-url').value.trim() };
        await Api.itsm.slack.saveConfig(body);
      } else if (type === 'teams') {
        body = { webhook_url: document.getElementById('teams-url').value.trim() };
        await Api.itsm.teams.saveConfig(body);
      }
      UI.toast(`${type.toUpperCase()} configurado correctamente`, 'success');
      _load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _test(type) {
    UI.toast('Probando conexión...', 'info');
    try {
      const apis = {
        jira: Api.itsm.jira.test,
        servicenow: Api.itsm.servicenow.test,
        slack: Api.itsm.slack.test,
        teams: Api.itsm.teams.test,
      };
      await apis[type]();
      UI.toast('Conexión exitosa', 'success');
    } catch (e) {
      UI.toast('Error de conexión: ' + e.message, 'error');
    }
  }

  return { render, _toggle, _save, _test };
})();
