/* app.js - router SPA y arranque. */

const Routes = {
  dashboard: ViewDashboard,
  heatmap: ViewHeatmap,
  questionnaire: ViewQuestionnaire,
  assets: ViewAssets,
  threats: ViewThreats,
  vulnerabilities: ViewVulns,
  risks: ViewRisks,
  calendar: ViewCalendar,
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

function _initTheme() {
  const saved = localStorage.getItem('riskhub_theme') || 'light';
  document.documentElement.setAttribute('data-theme', saved);
  _updateThemeIcon(saved);
  document.getElementById('btn-theme').onclick = () => {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('riskhub_theme', next);
    _updateThemeIcon(next);
  };
}

function _updateThemeIcon(theme) {
  document.getElementById('theme-icon-dark').style.display = theme === 'light' ? '' : 'none';
  document.getElementById('theme-icon-light').style.display = theme === 'dark' ? '' : 'none';
}

function init() {
  if (!Auth.requireAuth()) return;
  _initTheme();

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

  // Badge de vencidos en sidebar
  _loadOverdueBadge();

  // Atajos de teclado globales
  document.addEventListener('keydown', (e) => {
    const tag = document.activeElement.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      _showShortcutsHelp();
    }
    if (e.key === 'D' && e.shiftKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      document.getElementById('btn-theme').click();
    }
    if (e.key === 'g') {
      // Prefijo g + tecla para navegar (como Gmail)
      window._gPressed = true;
      setTimeout(() => { window._gPressed = false; }, 800);
    }
    if (window._gPressed && e.key !== 'g') {
      e.preventDefault();
      const nav = { d: 'dashboard', h: 'heatmap', a: 'assets', r: 'risks',
                    c: 'controls', p: 'reports', l: 'alerts', u: 'users' };
      if (nav[e.key]) location.hash = '/' + nav[e.key];
      window._gPressed = false;
    }
  });

  // Exponer navigate global para uso desde vistas
  window.App = { navigate: (route) => { location.hash = '/' + route; } };

  window.addEventListener('hashchange', () => { Search.close(); navigate(); });
  navigate();
}

function _showShortcutsHelp() {
  UI.modal('Atajos de teclado', `
    <table class="data" style="width:100%;font-size:13px;">
      <thead><tr><th>Atajo</th><th>Accion</th></tr></thead>
      <tbody>
        <tr><td><kbd>/</kbd></td><td>Activar busqueda global</td></tr>
        <tr style="background:var(--bg-2);"><td><kbd>?</kbd></td><td>Mostrar este dialogo de atajos</td></tr>
        <tr><td><kbd>Esc</kbd></td><td>Cerrar busqueda / modal</td></tr>
        <tr style="background:var(--bg-2);"><td><kbd>g</kbd> + <kbd>d</kbd></td><td>Ir al Dashboard</td></tr>
        <tr><td><kbd>g</kbd> + <kbd>h</kbd></td><td>Ir al Heatmap</td></tr>
        <tr style="background:var(--bg-2);"><td><kbd>g</kbd> + <kbd>a</kbd></td><td>Ir a Activos</td></tr>
        <tr><td><kbd>g</kbd> + <kbd>r</kbd></td><td>Ir a Riesgos</td></tr>
        <tr style="background:var(--bg-2);"><td><kbd>g</kbd> + <kbd>c</kbd></td><td>Ir a Controles</td></tr>
        <tr><td><kbd>g</kbd> + <kbd>p</kbd></td><td>Ir a Informes</td></tr>
        <tr style="background:var(--bg-2);"><td><kbd>g</kbd> + <kbd>l</kbd></td><td>Ir a Alertas</td></tr>
        <tr><td><kbd>g</kbd> + <kbd>u</kbd></td><td>Ir a Usuarios (admin)</td></tr>
        <tr style="background:var(--bg-2);"><td><kbd>↓</kbd> <kbd>↑</kbd></td><td>Navegar resultados de busqueda</td></tr>
        <tr><td><kbd>Enter</kbd></td><td>Abrir resultado seleccionado</td></tr>
        <tr style="background:var(--bg-2);"><td><kbd>Shift</kbd> + <kbd>D</kbd></td><td>Alternar modo oscuro / claro</td></tr>
      </tbody>
    </table>
    <p style="font-size:12px;color:var(--text-muted);margin-top:12px;">Los atajos de navegacion (g+...) solo funcionan cuando el foco no esta en un campo de texto.</p>
  `, { actions: '<button class="btn btn-primary" id="m-cancel">Cerrar</button>' });
  document.getElementById('m-cancel').onclick = UI.closeModal;
}

async function _loadOverdueBadge() {
  try {
    const s = await Api.risks.summary();
    const badge = document.getElementById('badge-overdue');
    if (!badge) return;
    if (s.overdue_treatments > 0) {
      badge.textContent = s.overdue_treatments;
      badge.style.display = 'inline-block';
    } else {
      badge.style.display = 'none';
    }
  } catch (_) { /* silencioso */ }
}

init();
