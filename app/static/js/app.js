/* app.js - router SPA y arranque. */

const Routes = {
  dashboard: ViewDashboard,
  heatmap: ViewHeatmap,
  questionnaire: ViewQuestionnaire,
  assets: ViewAssets,
  threats: ViewThreats,
  vulnerabilities: ViewVulns,
  risks: ViewRisks,
  controls: ViewControls,
  reports: ViewReports,
  alerts: ViewAlerts,
  integrations: ViewIntegrations,
  guide: ViewGuide,
  context: ViewContext,
  users: ViewUsers,
  audit: ViewAudit,
};

function currentRoute() {
  const h = location.hash.replace(/^#\/?/, '').split('?')[0];
  return h || 'dashboard';
}

function setActive(route) {
  document.querySelectorAll('.sidebar a').forEach(a => {
    a.classList.toggle('active', a.dataset.route === route);
  });
}

async function navigate() {
  if (!Auth.requireAuth()) return;
  const route = currentRoute();
  const view = Routes[route] || Routes.dashboard;
  setActive(route);
  const main = document.getElementById('main');
  main.innerHTML = '';
  try {
    await view.render(main);
  } catch (e) {
    main.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
  }
}

function init() {
  if (!Auth.requireAuth()) return;

  // Header user info
  const u = Auth.user();
  if (u) {
    document.getElementById('user-name').textContent = u.full_name || u.email;
    document.getElementById('user-role').textContent = u.role;
  }
  document.getElementById('btn-logout').onclick = () => Auth.logout();

  // User chip abre modal de perfil
  document.getElementById('user-chip').style.cursor = 'pointer';
  document.getElementById('user-chip').onclick = () => {
    const me = Auth.user() || {};
    UI.modal('Mi perfil', `
      <div class="span2" style="margin-bottom:8px;">
        <p style="font-size:13px;color:var(--text-muted);margin:0 0 4px;">
          <strong>${UI.esc(me.full_name || '')}</strong>
          &nbsp;<span class="badge badge-muted">${UI.esc(me.role || '')}</span>
        </p>
        <p style="font-size:12px;color:var(--text-subtle);margin:0;">${UI.esc(me.email || '')}</p>
      </div>
      <div class="span2"><hr style="border:none;border-top:1px solid var(--border);margin:8px 0;"></div>
      <div class="span2"><label>Contrasena actual *</label><input type="password" id="p-cur"></div>
      <div><label>Nueva contrasena *</label><input type="password" id="p-new"></div>
      <div><label>Repetir nueva contrasena *</label><input type="password" id="p-new2"></div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Cambiar contrasena</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const cur = document.getElementById('p-cur').value;
      const nw = document.getElementById('p-new').value;
      const nw2 = document.getElementById('p-new2').value;
      if (!cur || !nw) { UI.toast('Completa todos los campos', 'error'); return; }
      if (nw !== nw2) { UI.toast('Las contrasenas no coinciden', 'error'); return; }
      if (nw.length < 8) { UI.toast('La nueva contrasena debe tener al menos 8 caracteres', 'error'); return; }
      try {
        await Api.changePassword({ current_password: cur, new_password: nw });
        UI.toast('Contrasena cambiada correctamente', 'success');
        UI.closeModal();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  };

  // Ocultar enlaces admin si no es admin
  if (!Auth.isAdmin()) {
    document.querySelectorAll('[data-admin]').forEach(el => el.style.display = 'none');
  }

  // Busqueda global
  Search.init();

  // Exponer navigate global para uso desde vistas
  window.App = { navigate: (route) => { location.hash = '/' + route; } };

  window.addEventListener('hashchange', () => { Search.close(); navigate(); });
  navigate();
}

init();
