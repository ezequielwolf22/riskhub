/* Vistas hub: agrupan las vistas existentes en hubs con pestanas internas
   (progressive disclosure). Cada hub delega el render de cada pestana en la
   View original via UI.tabs — las vistas existentes no se modifican. */

/* 1. Inicio */
const ViewHomeHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'home',
      label: 'Inicio',
      tabs: [
        {
          id: 'dashboard', label: 'Dashboard',
          // Slot reservado para la bandeja de revision (lo monta otro modulo)
          render: async (panel) => {
            panel.innerHTML = '<div id="home-dashboard-mount"></div>';
            await ViewDashboard.render(panel.querySelector('#home-dashboard-mount'));
          },
        },
        { id: 'executive', label: 'Ejecutivo', view: ViewExecutive },
        { id: 'heatmap', label: 'Heatmap', view: ViewHeatmap },
      ],
    });
  },
};

/* 2. Riesgos y activos */
const ViewRiskHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'risk-hub',
      label: 'Riesgos y activos',
      tabs: [
        { id: 'risks', label: 'Registro', view: ViewRisks, route: 'risks' },
        { id: 'assets', label: 'Activos', view: ViewAssets, route: 'assets' },
        { id: 'threats', label: 'Amenazas', view: ViewThreats },
        { id: 'vulnerabilities', label: 'Vulnerabilidades', view: ViewVulns },
        { id: 'magerit', label: 'MAGERIT', view: ViewMagerit },
        { id: 'kris', label: 'KRIs / KPIs', view: ViewKRIs, route: 'kris' },
      ],
    });
  },
};

/* 3. Vigilancia */
const ViewWatchHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'watch-hub',
      label: 'Vigilancia',
      tabs: [
        { id: 'cve', label: 'CVE', view: ViewCve, route: 'cve' },
        { id: 'osint', label: 'OSINT', view: ViewOsint },
        { id: 'external-findings', label: 'Hallazgos externos', view: ViewExternalFindings },
        { id: 'architecture-review', label: 'Rev. arquitectura', view: ViewArchitectureReview },
        { id: 'predictive', label: 'Predictivo', view: ViewPredictive },
      ],
    });
  },
};

/* 4. Cumplimiento */
const ViewComplianceHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'compliance-hub',
      label: 'Cumplimiento',
      tabs: [
        { id: 'compliance', label: 'Normativo', view: ViewCompliance, route: 'compliance' },
        { id: 'controls', label: 'Controles', view: ViewControls, route: 'controls' },
        { id: 'soa', label: 'SoA', view: ViewSoaVersions },
        { id: 'policies', label: 'Documentos ISMS', view: ViewIsmsDocuments, route: 'policies' },
        {
          id: 'legal',
          label: 'Cumplimiento legal',
          render: async (panel) => {
            panel.innerHTML = `
              <div style="display:flex;gap:0;margin-bottom:20px;border-bottom:2px solid var(--border);">
                <button class="legal-subtab active" data-target="legal-gdpr"
                  onclick="ViewComplianceHub._legalTab(this,'legal-gdpr')"
                  style="padding:10px 20px;border:none;background:none;cursor:pointer;font-weight:600;
                         border-bottom:2px solid var(--brand-purple);margin-bottom:-2px;color:var(--brand-purple);">
                  RGPD / GDPR
                </button>
                <button class="legal-subtab" data-target="legal-nis2"
                  onclick="ViewComplianceHub._legalTab(this,'legal-nis2')"
                  style="padding:10px 20px;border:none;background:none;cursor:pointer;font-weight:600;color:var(--text-muted);">
                  NIS2 - Notificaciones
                </button>
              </div>
              <div id="legal-gdpr"></div>
              <div id="legal-nis2" style="display:none;"></div>
            `;
            await ViewGdpr.render(panel.querySelector('#legal-gdpr'));
          },
        },
        { id: 'audits', label: 'Auditorias', view: ViewAudits, route: 'internal-audits' },
        { id: 'nonconformities', label: 'No conformidades', view: ViewNonConformities, route: 'nonconformities' },
        { id: 'change-requests', label: 'Cambios', view: ViewChangeRequests },
      ],
    });
  },

  _legalTab(btn, targetId) {
    document.querySelectorAll('.legal-subtab').forEach(b => {
      b.style.color = 'var(--text-muted)';
      b.style.borderBottom = 'none';
    });
    btn.style.color = 'var(--brand-purple)';
    btn.style.borderBottom = '2px solid var(--brand-purple)';
    btn.style.marginBottom = '-2px';
    ['legal-gdpr', 'legal-nis2'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = id === targetId ? '' : 'none';
    });
    if (targetId === 'legal-nis2') {
      const panel = document.getElementById('legal-nis2');
      if (panel && !panel._loaded) {
        panel._loaded = true;
        ViewNis2Dashboard.render(panel);
      }
    }
  },
};

/* 5. Incidentes */
const ViewEventsHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'events-hub',
      label: 'Incidentes',
      tabs: [
        { id: 'incidents', label: 'Incidentes', view: ViewIncidents, route: 'incidents' },
      ],
    });
  },
};

/* 6. BCP — hub independiente */
const ViewBcpHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'bcp-hub',
      label: 'Continuidad de Negocio',
      tabs: [
        { id: 'bcp', label: 'BCP / BCM', view: ViewBcp },
      ],
    });
  },
};

/* 7. Informes */
const ViewReportsHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'reports-hub',
      label: 'Informes',
      tabs: [
        { id: 'reports', label: 'Informes', view: ViewReports, route: 'reports' },
        { id: 'schedules', label: 'Programados', view: ViewReportSchedules },
        { id: 'management-review', label: 'Rev. direccion', view: ViewManagementReview, route: 'management-review' },
        { id: 'evidence', label: 'Evidencias', view: ViewEvidence },
        { id: 'trust-portal', label: 'Trust Portal', view: ViewTrustPortal, visible: () => Auth.isAdmin() },
        { id: 'calendar', label: 'Calendario', view: ViewCalendar },
        { id: 'tasks', label: 'Tareas', view: ViewTasks, route: 'tasks' },
      ],
    });
  },
};

/* 8. Agente IA */
const ViewAiHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'ai-hub',
      label: 'Agente IA',
      tabs: [
        { id: 'chat', label: 'Chat', view: ViewAiChat, route: 'ai-chat' },
        {
          id: 'documents',
          label: 'Documentos ISMS',
          render: async (_panel) => { location.hash = '/compliance-hub/policies'; },
        },
        {
          id: 'ai-settings',
          label: 'Configuracion',
          visible: () => Auth.isAdmin(),
          render: async (panel) => { await ViewAiSettings.render(panel); },
        },
      ],
    });
  },
};

const _AI_MODELS = [
  { value: 'claude-opus-4-8',   label: 'Opus 4.8  — maximo rendimiento' },
  { value: 'claude-opus-4-7',   label: 'Opus 4.7  — muy potente' },
  { value: 'claude-opus-4-6',   label: 'Opus 4.6  — potente (por defecto)' },
  { value: 'claude-sonnet-4-6', label: 'Sonnet 4.6 — equilibrado' },
  { value: 'claude-haiku-4-5',  label: 'Haiku 4.5  — rapido y economico' },
];

const ViewAiSettings = {
  async render(el) {
    el.innerHTML = '<p class="text-muted" style="padding:24px;">Cargando configuracion...</p>';
    let cfg;
    try {
      cfg = await Api.aiConfig.get();
    } catch (e) {
      el.innerHTML = `<p style="color:var(--danger);padding:24px;">Error cargando configuracion: ${UI.esc(e.message)}</p>`;
      return;
    }

    const currentModel = cfg.model || 'claude-opus-4-6';
    const hasKey = !!cfg.has_api_key;

    el.innerHTML = `
      <div style="max-width:560px;padding:24px;display:grid;gap:24px;">

        <div class="card" style="padding:20px;display:grid;gap:16px;">
          <h3 style="margin:0;font-size:15px;font-weight:600;">API Key de Anthropic</h3>
          <div style="display:flex;align-items:center;gap:12px;">
            <span style="display:inline-block;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:600;
              background:${hasKey ? 'var(--success,#22c55e)' : 'var(--danger,#ef4444)'};color:#fff;">
              ${hasKey ? 'CONFIGURADA' : 'NO CONFIGURADA'}
            </span>
            ${hasKey
              ? '<span style="font-size:13px;color:var(--text-muted);">La clave esta almacenada de forma cifrada.</span>'
              : '<span style="font-size:13px;color:var(--text-muted);">Sin clave no funcionan las funciones IA.</span>'
            }
          </div>
          <div style="display:grid;gap:8px;">
            <label for="ai-apikey" style="font-size:13px;font-weight:500;">
              ${hasKey ? 'Cambiar API key (dejar vacio para mantener la actual)' : 'Introducir API key'}
            </label>
            <input type="password" id="ai-apikey" placeholder="sk-ant-api03-..."
              autocomplete="new-password"
              style="font-family:monospace;font-size:13px;">
          </div>
        </div>

        <div class="card" style="padding:20px;display:grid;gap:16px;">
          <h3 style="margin:0;font-size:15px;font-weight:600;">Modelo Claude</h3>
          <p style="margin:0;font-size:13px;color:var(--text-muted);">
            Todas las funciones IA de la plataforma usaran este modelo.
            Los cambios se aplican a partir de la siguiente llamada.
          </p>
          <div style="display:grid;gap:8px;">
            <label for="ai-model" style="font-size:13px;font-weight:500;">Modelo activo</label>
            <select id="ai-model" style="font-size:13px;">
              ${_AI_MODELS.map(m =>
                `<option value="${m.value}"${m.value === currentModel ? ' selected' : ''}>${UI.esc(m.label)}</option>`
              ).join('')}
            </select>
          </div>
          <div style="padding:10px 12px;background:var(--bg-2);border-radius:6px;font-size:12px;color:var(--text-muted);">
            <strong>Guia rapida:</strong><br>
            <strong>Opus 4.8 / 4.7</strong> — analisis complejos, documentos largos, mayor precision.<br>
            <strong>Opus 4.6</strong> — excelente calidad, buen equilibrio coste/rendimiento.<br>
            <strong>Sonnet 4.6</strong> — rapido y capaz, ideal para uso intensivo.<br>
            <strong>Haiku 4.5</strong> — el mas economico, adecuado para tareas simples y alertas.
          </div>
        </div>

        <div style="display:flex;gap:10px;align-items:center;">
          <button class="btn btn-primary" id="ai-cfg-save">Guardar cambios</button>
          <button class="btn btn-ghost" id="ai-cfg-test">Probar conexion</button>
          <span id="ai-cfg-msg" style="font-size:13px;"></span>
        </div>
      </div>`;

    document.getElementById('ai-cfg-save').addEventListener('click', async () => {
      const msg   = document.getElementById('ai-cfg-msg');
      const model = document.getElementById('ai-model').value;
      const key   = (document.getElementById('ai-apikey').value || '').trim();
      const payload = { model };
      if (key) payload.api_key = key;
      msg.textContent = 'Guardando...';
      msg.style.color = 'var(--text-muted)';
      try {
        await Api.aiConfig.update(payload);
        msg.textContent = 'Guardado correctamente.';
        msg.style.color = 'var(--success,#22c55e)';
        document.getElementById('ai-apikey').value = '';
        if (key) await ViewAiSettings.render(el);
      } catch (e) {
        msg.textContent = 'Error: ' + e.message;
        msg.style.color = 'var(--danger,#ef4444)';
      }
    });

    document.getElementById('ai-cfg-test').addEventListener('click', async () => {
      const msg = document.getElementById('ai-cfg-msg');
      msg.textContent = 'Probando...';
      msg.style.color = 'var(--text-muted)';
      try {
        const res = await Api.aiConfig.test();
        msg.textContent = `Conexion OK — modelo: ${res.model}`;
        msg.style.color = 'var(--success,#22c55e)';
      } catch (e) {
        msg.textContent = 'Error: ' + e.message;
        msg.style.color = 'var(--danger,#ef4444)';
      }
    });
  },
};

/* 9. Proveedores — hub independiente */
const ViewSuppliersHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'suppliers-hub',
      label: 'Proveedores',
      tabs: [
        { id: 'tprm', label: 'TPRM Dashboard', view: ViewTprm, route: 'tprm' },
        { id: 'suppliers', label: 'Proveedores', view: ViewSuppliers, route: 'suppliers' },
        { id: 'assessments', label: 'Evaluaciones', view: ViewVendorAssessments, route: 'vendor-assessments' },
        { id: 'issues', label: 'Hallazgos', view: ViewVendorIssues, route: 'vendor-issues' },
        { id: 'templates', label: 'Plantillas', view: ViewVendorTemplates, route: 'vendor-templates' },
      ],
    });
  },
};

/* 10. Setup — asistente de configuracion inicial */
const ViewSetupHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'setup-hub',
      label: 'Setup',
      tabs: [
        {
          id: 'wizard', label: 'Asistente de configuracion',
          render: async (panel) => { await ViewOnboarding.render(panel); },
        },
        { id: 'context', label: 'Contexto org.', view: ViewContext, route: 'context' },
        { id: 'regwatch', label: 'Vigilancia normativa', view: ViewRegwatch, route: 'regwatch' },
      ],
    });
  },
};

/* 10. Configuracion (solo admin; organizaciones y modulos solo superadmin) */
const ViewAdminHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'admin-hub',
      label: 'Configuracion',
      tabs: [
        { id: 'users', label: 'Usuarios', view: ViewUsers, visible: () => Auth.isAdmin() },
        { id: 'integrations', label: 'Integraciones', view: ViewIntegrations, route: 'integrations' },
        { id: 'itsm', label: 'ITSM', view: ViewItsmConfig, visible: () => Auth.isAdmin() },
        { id: 'webhooks', label: 'Webhooks', view: ViewWebhooks, visible: () => Auth.isAdmin() },
        { id: 'alerts', label: 'Alertas', view: ViewAlerts, route: 'alerts' },
        { id: 'awareness', label: 'Awareness', view: ViewAwareness, route: 'awareness' },
        { id: 'audit', label: 'Auditoria log', view: ViewAudit, visible: () => Auth.isAdmin() },
        { id: 'organizations', label: 'Organizaciones', view: ViewOrganizations, visible: () => Auth.isSuperAdmin() },
        { id: 'feature-flags', label: 'Modulos', view: ViewFeatureFlags, visible: () => Auth.isSuperAdmin() },
      ],
    });
  },
};
