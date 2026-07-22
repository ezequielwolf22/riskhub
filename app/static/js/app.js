/* app.js - router SPA y arranque. */

const Routes = {
  // Hubs con pestanas internas (views/hubs.js)
  home: ViewHomeHub,
  'risk-hub': ViewRiskHub,
  'watch-hub': ViewWatchHub,
  'compliance-hub': ViewComplianceHub,
  'events-hub': ViewEventsHub,
  'bcp-hub': ViewBcpHub,
  'reports-hub': ViewReportsHub,
  'ai-hub': ViewAiHub,
  'suppliers-hub': ViewSuppliersHub,
  'setup-hub': ViewSetupHub,
  'admin-hub': ViewAdminHub,
  // Rutas independientes (sin entrada propia en el sidebar)
  guide: ViewGuide,
  onboarding: ViewOnboarding,
  questionnaire: ViewQuestionnaire,
  context: ViewContext,
  inbox: ViewInbox,
  'change-password-required': ViewChangePasswordRequired,
  'mfa-setup-required': ViewMfaSetupRequired,
  profile: ViewProfile,
};

// Mapa explicito de rutas legacy → hub/pestana. Las URLs antiguas siguen
// funcionando: navigate() las reemplaza (location.replace) conservando query.
const LegacyRedirects = {
  dashboard: 'home/dashboard',
  executive: 'home/executive',
  heatmap: 'home/heatmap',
  risks: 'risk-hub/risks',
  treatment: 'risk-hub/treatment',
  'plan-director': 'risk-hub/plan-director',
  assets: 'risk-hub/assets',
  threats: 'risk-hub/threats',
  vulnerabilities: 'risk-hub/vulnerabilities',
  kris: 'risk-hub/kris',
  cve: 'watch-hub/cve',
  osint: 'watch-hub/osint',
  'external-findings': 'watch-hub/external-findings',
  'architecture-review': 'watch-hub/architecture-review',
  predictive: 'watch-hub/predictive',
  compliance: 'compliance-hub/compliance',
  controls: 'compliance-hub/controls',
  regwatch: 'setup-hub/regwatch',
  ccm: 'compliance-hub/controls',
  'soa-versions': 'compliance-hub/soa',
  policies: 'compliance-hub/policies',
  'internal-audits': 'compliance-hub/audits',
  'management-review': 'reports-hub/management-review',
  'change-requests': 'compliance-hub/change-requests',
  incidents: 'events-hub/incidents',
  nonconformities: 'compliance-hub/nonconformities',
  bcp: 'bcp-hub/bcp',
  ingest: 'bcp-hub/ingest',
  'nis2-dashboard': 'compliance-hub/legal',
  gdpr: 'compliance-hub/legal',
  suppliers: 'suppliers-hub/suppliers',
  context: 'setup-hub/context',
  reports: 'reports-hub/reports',
  'report-schedules': 'reports-hub/schedules',
  evidence: 'reports-hub/evidence',
  'trust-portal': 'reports-hub/trust-portal',
  calendar: 'reports-hub/calendar',
  tasks: 'reports-hub/tasks',
  'ai-chat': 'ai-hub/chat',
  'ai-documents': 'compliance-hub/policies',
  users: 'admin-hub/users',
  integrations: 'admin-hub/integrations',
  'itsm-config': 'admin-hub/itsm',
  webhooks: 'admin-hub/webhooks',
  alerts: 'admin-hub/alerts',
  awareness: 'ai-hub/awareness',
  audit: 'admin-hub/audit',
  organizations: 'admin-hub/organizations',
  'feature-flags': 'admin-hub/feature-flags',
  ops: 'admin-hub/ops',
};

function currentRoute() {
  // Primer segmento del hash: '#/risk-hub/assets?x=1' → 'risk-hub'
  const h = location.hash.replace(/^#\/?/, '').split('?')[0].split('/')[0];
  return h || 'home';
}

function setActive(route) {
  document.querySelectorAll('.sidebar a').forEach(a => {
    a.classList.toggle('active', a.dataset.route === route);
  });
}

async function navigate() {
  if (!Auth.requireAuth()) return;
  const route = currentRoute();
  // Redireccion de rutas legacy a su hub/pestana (conservando query string)
  if (LegacyRedirects[route]) {
    const query = location.hash.split('?')[1];
    location.replace('#/' + LegacyRedirects[route] + (query ? '?' + query : ''));
    return;
  }
  // Forzar cambio de contrasena OTP si es el primer login
  const u = Auth.user();
  if (u && u.must_change_password && route !== 'change-password-required') {
    location.hash = '/change-password-required';
    return;
  }
  // Forzar configuracion de MFA si la organizacion/admin lo exige y el usuario aun no lo activo
  if (u && u.must_configure_mfa && route !== 'mfa-setup-required') {
    location.hash = '/mfa-setup-required';
    return;
  }
  const view = Routes[route] || Routes.home;
  setActive(route);
  // Scroll to top on every navigation
  window.scrollTo(0, 0);
  document.getElementById('main').scrollTop = 0;
  const main = document.getElementById('main');
  main.innerHTML = '';
  try {
    await view.render(main);
  } catch (e) {
    main.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
  }
  // Montar bandeja de revision en el slot del dashboard (si existe)
  if (typeof ViewInbox !== 'undefined') ViewInbox.mountIfSlot();
  // Refresh sidebar badges after navigation
  _loadBootstrap();
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

function _initLang() {
  const lang = I18n.lang();
  const btn   = document.getElementById('btn-lang');
  const label = document.getElementById('lang-label');
  if (!btn || !label) return;
  // El botón muestra el idioma AL QUE SE CAMBIARÁ (toggle)
  label.textContent = lang === 'es' ? 'EN' : 'ES';
  btn.title = t('shell.change_lang');
  btn.setAttribute('aria-label', t('shell.change_lang'));
  btn.onclick = () => I18n.setLang(lang === 'es' ? 'en' : 'es');
}

function _updateThemeIcon(theme) {
  document.getElementById('theme-icon-dark').style.display = theme === 'light' ? '' : 'none';
  document.getElementById('theme-icon-light').style.display = theme === 'dark' ? '' : 'none';
}

function _updateSidebarIcons(collapsed) {
  const ic = document.getElementById('sidebar-icon-collapse');
  const ie = document.getElementById('sidebar-icon-expand');
  if (ic) ic.style.display = collapsed ? 'none' : '';
  if (ie) ie.style.display = collapsed ? '' : 'none';
}

// ── Collapsible sidebar sections ─────────────────────────────────────────────

function _initNavSections() {
  const KEY = 'riskhub_nav_collapsed';
  let collapsed;
  try { collapsed = JSON.parse(localStorage.getItem(KEY) || '[]'); }
  catch (e) { collapsed = []; }

  collapsed.forEach(id => {
    const section = document.getElementById(id);
    if (section) section.classList.add('ns-collapsed');
  });
}

function _toggleNavSection(sectionId) {
  const KEY = 'riskhub_nav_collapsed';
  const section = document.getElementById(sectionId);
  if (!section) return;

  section.classList.toggle('ns-collapsed');

  let collapsed;
  try { collapsed = JSON.parse(localStorage.getItem(KEY) || '[]'); }
  catch (e) { collapsed = []; }

  if (section.classList.contains('ns-collapsed')) {
    if (!collapsed.includes(sectionId)) collapsed.push(sectionId);
  } else {
    collapsed = collapsed.filter(id => id !== sectionId);
  }
  localStorage.setItem(KEY, JSON.stringify(collapsed));
}

// ── Bandas de nivel de riesgo configurables ───────────────────────────────────
window.RiskLevels = {
  _bands: [
    { code: 'low',    label: 'Bajo',  min_level: 0, max_level: 2, color: 'var(--risk-low)',    order: 1 },
    { code: 'medium', label: 'Medio', min_level: 3, max_level: 5, color: 'var(--risk-medium)', order: 2 },
    { code: 'high',   label: 'Alto',  min_level: 6, max_level: 8, color: 'var(--risk-high)',   order: 3 },
  ],
  async load() {
    try {
      const data = await Api.risk_levels.get();
      if (Array.isArray(data) && data.length) {
        this._bands = data.slice().sort((a, b) => a.order - b.order);
      }
    } catch (_) { /* silencioso: se usan defaults */ }
  },
  reload() { return this.load(); },
  bandFor(level) {
    const l = Math.max(0, Math.min(8, Number(level) || 0));
    for (const b of this._bands) {
      if (l >= b.min_level && l <= b.max_level) return b;
    }
    return this._bands[this._bands.length - 1];
  },
  colorFor(level) { return this.bandFor(level).color; },
  labelFor(level) { return this.bandFor(level).label; },
  all() { return [...this._bands]; },
};

/* Carga inicial: una sola llamada al servidor para flags + badges + risk levels.
   Sustituye las ~7 llamadas independientes que se hacian al arrancar. */
async function _loadBootstrap() {
  try {
    const data = await Api.get('/api/app/bootstrap');

    // Risk levels
    if (data.risk_levels && data.risk_levels.length) {
      RiskLevels._bands = data.risk_levels.slice().sort((a, b) => a.order - b.order);
    }

    // Feature flags — aplicar al sidebar sin llamada extra a la API
    if (data.flags) {
      ViewFeatureFlags.applyFlagsToSidebar(data.flags);
    }

    // Badges del sidebar
    const b = data.badges || {};
    const badge = document.getElementById('badge-overdue');
    if (badge) {
      badge.textContent = b.overdue_treatments || '';
      badge.style.display = b.overdue_treatments > 0 ? 'inline-block' : 'none';
    }
    const ctrlBadge = document.getElementById('badge-ctrl-review');
    if (ctrlBadge) {
      ctrlBadge.textContent = b.controls_overdue_reviews || '';
      ctrlBadge.style.display = b.controls_overdue_reviews > 0 ? 'inline-block' : 'none';
    }
    const taskBadge = document.getElementById('badge-tasks-overdue');
    if (taskBadge) {
      taskBadge.textContent = b.tasks_overdue || '';
      taskBadge.style.display = b.tasks_overdue > 0 ? 'inline-block' : 'none';
    }
    const nis2Badge = document.getElementById('badge-nis2-urgent');
    if (nis2Badge) {
      nis2Badge.textContent = b.nis2_urgent > 0 ? String(b.nis2_urgent) : '';
      nis2Badge.style.display = b.nis2_urgent > 0 ? 'flex' : 'none';
    }
    const notifBadge = document.getElementById('notif-count');
    if (notifBadge) {
      const total = b.notif_total || 0;
      notifBadge.textContent = total > 9 ? '9+' : String(total);
      notifBadge.style.display = total > 0 ? 'flex' : 'none';
    }
  } catch (_e) {
    // Fallback silencioso: las vistas individuales ya cargan sus propios datos
  }
}

function init() {
  // Manejar SSO callback — llega un code de un solo uso (30s TTL), se intercambia por JWT
  const _ssoParams = new URLSearchParams(window.location.search);
  const _ssoCode = _ssoParams.get('sso_code');
  if (_ssoCode) {
    // Limpiar el code de la URL antes de procesar
    window.history.replaceState({}, '', '/');
    fetch('/api/sso/exchange', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: _ssoCode }),
    })
      .then(r => r.ok ? r.json() : Promise.reject('invalid'))
      .then(data => {
        const tok = data.access_token;
        return fetch('/api/auth/me', { headers: { 'Authorization': 'Bearer ' + tok } })
          .then(r => r.ok ? r.json() : Promise.reject('invalid'))
          .then(user => {
            localStorage.setItem('riskhub_token', tok);
            if (data.refresh_token) localStorage.setItem('riskhub_refresh', data.refresh_token);
            localStorage.setItem('riskhub_user', JSON.stringify(user));
            window.location.reload();
          });
      })
      .catch(() => { window.location.href = '/login?sso_error=token_invalid'; });
    return;   // detener init hasta que el reload complete
  }

  if (!Auth.requireAuth()) return;
  _loadBootstrap();    // flags + risk levels + badges en una sola llamada
  _initTheme();
  _initLang();
  I18n.applyDataAttrs();

  // Sidebar collapse toggle
  const sidebar = document.getElementById('sidebar');
  const savedCollapsed = localStorage.getItem('riskhub_sidebar') === 'collapsed';
  if (savedCollapsed) sidebar.classList.add('collapsed');
  _updateSidebarIcons(savedCollapsed);
  document.getElementById('btn-sidebar-toggle').onclick = () => {
    const isNowCollapsed = sidebar.classList.toggle('collapsed');
    localStorage.setItem('riskhub_sidebar', isNowCollapsed ? 'collapsed' : 'expanded');
    _updateSidebarIcons(isNowCollapsed);
  };

  // Header user info
  const u = Auth.user();
  if (u) {
    document.getElementById('user-name').textContent = u.full_name || u.email;
    document.getElementById('user-role').textContent = u.role;
  }
  document.getElementById('btn-logout').onclick = () => Auth.logout();

  // User chip navega a Mi Perfil
  document.getElementById('user-chip').style.cursor = 'pointer';
  document.getElementById('user-chip').onclick = () => {
    location.hash = '/profile';
  };

  // Selector de organizacion para superadmin
  if (u && u.role === 'superadmin') {
    _initOrgSelector();
  }

  // Ocultar enlaces admin si no es admin
  if (!Auth.isAdmin()) {
    document.querySelectorAll('[data-admin]').forEach(el => el.style.display = 'none');
  }

  // Ocultar enlaces superadmin si no es superadmin
  if (!Auth.isSuperAdmin()) {
    document.querySelectorAll('[data-superadmin]').forEach(el => el.style.display = 'none');
  }

  // Visibilidad de hubs por rol (solo UX — la autorizacion real es server-side):
  // viewer ve Inicio, Riesgos, Cumplimiento e Informes; analyst anade
  // Vigilancia, Eventos y Agente IA; admin ve ademas Configuracion (data-admin).
  if (!Auth.canEdit()) {
    document.querySelectorAll('.sidebar [data-minrole="analyst"]')
      .forEach(el => el.style.display = 'none');
  }

  // Busqueda global
  Search.init();

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
    if (e.key === 'B' && e.shiftKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      document.getElementById('btn-sidebar-toggle').click();
    }
    if (e.key === 'g') {
      // Prefijo g + tecla para navegar (como Gmail)
      window._gPressed = true;
      setTimeout(() => { window._gPressed = false; }, 800);
    }
    if (window._gPressed && e.key !== 'g') {
      e.preventDefault();
      const nav = { d: 'home/dashboard', h: 'home/heatmap', a: 'risk-hub/assets',
                    r: 'risk-hub/risks', c: 'compliance-hub/controls',
                    p: 'reports-hub/reports', l: 'admin-hub/alerts', u: 'admin-hub/users' };
      if (nav[e.key]) location.hash = '/' + nav[e.key];
      window._gPressed = false;
    }
  });

  // Inicializar secciones colapsables del sidebar
  _initNavSections();

  // FAB toggle — boton de acciones rapidas
  const _fabToggle = document.getElementById('fab-toggle');
  const _fabMenu = document.getElementById('fab-menu');
  if (_fabToggle && _fabMenu) {
    _fabToggle.onclick = () => {
      _fabMenu.style.display = _fabMenu.style.display === 'none' ? 'flex' : 'none';
    };
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#quick-actions-fab')) {
        if (_fabMenu) _fabMenu.style.display = 'none';
      }
    });
  }

  // Refrescar badges cada minuto (notif count desde bootstrap)
  setInterval(_loadBootstrap, 60000);

  // Exponer navigate global para uso desde vistas
  window.App = {
    navigate: (route) => { location.hash = '/' + route; },
    toggleSection: _toggleNavSection
  };

  window.addEventListener('hashchange', () => { Search.close(); navigate(); });

  // Redireccion al onboarding en la primera visita (si no se ha omitido y no hay ruta explícita)
  const currentHash = location.hash.replace(/^#\/?/, '').split('?')[0];
  const skipped = localStorage.getItem('riskhub_onboarding_skipped');
  const onboardingDone = localStorage.getItem('riskhub_onboarding_done');
  const _isHome = !currentHash || currentHash === 'dashboard' ||
                  currentHash === 'home' || currentHash === 'home/dashboard';
  if (!skipped && !onboardingDone && _isHome) {
    // Verificar si ya tiene configuracion completada via API
    Api.aiConfig.get().then(cfg => {
      if (!cfg.setup_completed) {
        location.hash = '/onboarding';
        return;
      }
      localStorage.setItem('riskhub_onboarding_done', '1');
    }).catch(() => { /* silencioso: no bloquear si la API falla */ });
  }

  navigate();
}

async function _initOrgSelector() {
  const container = document.getElementById('org-context-selector');
  if (!container) return;
  try {
    const orgs = await Api.get('/api/organizations/');
    if (!Array.isArray(orgs) || orgs.length === 0) return;

    const saved = localStorage.getItem('riskhub_active_org') || '';
    const selectedOrg = orgs.find(o => String(o.id) === saved);
    const label = selectedOrg ? selectedOrg.name : 'Todas las orgs';

    container.style.display = 'flex';
    container.style.alignItems = 'center';
    container.innerHTML = `
      <div class="org-ctx-chip" id="org-ctx-chip" title="Filtrar por organizacion">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
        <span id="org-ctx-label">${UI.esc(label)}</span>
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
      <div id="org-ctx-dropdown" class="org-ctx-dropdown" style="display:none;">
        <div class="org-ctx-opt ${!saved ? 'org-ctx-opt--active' : ''}" data-org-id="">
          Todas las organizaciones
        </div>
        ${orgs.map(o => `
          <div class="org-ctx-opt ${String(o.id) === saved ? 'org-ctx-opt--active' : ''}" data-org-id="${o.id}">
            <span>${UI.esc(o.name)}</span>
            <small>${UI.esc(o.plan || '')}</small>
          </div>
        `).join('')}
      </div>
    `;

    const chip = document.getElementById('org-ctx-chip');
    const dd = document.getElementById('org-ctx-dropdown');

    chip.addEventListener('click', (e) => {
      e.stopPropagation();
      dd.style.display = dd.style.display === 'none' ? '' : 'none';
    });

    dd.querySelectorAll('.org-ctx-opt').forEach(opt => {
      opt.addEventListener('click', (e) => {
        e.stopPropagation();
        const orgId = opt.dataset.orgId;
        if (orgId) {
          localStorage.setItem('riskhub_active_org', orgId);
        } else {
          localStorage.removeItem('riskhub_active_org');
        }
        dd.style.display = 'none';
        // Re-renderizar el selector y recargar la vista actual
        _initOrgSelector();
        navigate();
      });
    });

    document.addEventListener('click', () => {
      if (dd) dd.style.display = 'none';
    }, { once: false });

  } catch (_) { /* silencioso */ }
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
        <tr><td><kbd>Shift</kbd> + <kbd>B</kbd></td><td>Contraer / expandir barra lateral</td></tr>
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
    if (badge) {
      if (s.overdue_treatments > 0) {
        badge.textContent = s.overdue_treatments;
        badge.style.display = 'inline-block';
      } else {
        badge.style.display = 'none';
      }
    }
    const ctrlBadge = document.getElementById('badge-ctrl-review');
    if (ctrlBadge) {
      if (s.controls_overdue_reviews > 0) {
        ctrlBadge.textContent = s.controls_overdue_reviews;
        ctrlBadge.style.display = 'inline-block';
      } else {
        ctrlBadge.style.display = 'none';
      }
    }
  } catch (_) { /* silencioso */ }
  try {
    const ts = await Api.tasks.summary();
    const taskBadge = document.getElementById('badge-tasks-overdue');
    if (taskBadge) {
      if (ts.overdue > 0) {
        taskBadge.textContent = ts.overdue;
        taskBadge.style.display = 'inline-block';
      } else {
        taskBadge.style.display = 'none';
      }
    }
  } catch (_) { /* silencioso */ }
}

init();
