/* app.js - router SPA y arranque. */

const Routes = {
  dashboard: ViewDashboard,
  heatmap: ViewHeatmap,
  assets: ViewAssets,
  threats: ViewThreats,
  vulnerabilities: ViewVulns,
  risks: ViewRisks,
  controls: ViewControls,
  reports: ViewReports,
  context: ViewContext,
  users: ViewUsers,
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

  // Ocultar enlaces admin si no es admin
  if (!Auth.isAdmin()) {
    document.querySelectorAll('[data-admin]').forEach(el => el.style.display = 'none');
  }

  window.addEventListener('hashchange', navigate);
  navigate();
}

init();
