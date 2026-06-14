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
            panel.innerHTML = '<div id="home-inbox-slot"></div><div id="home-dashboard-mount"></div>';
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

/* 4. Cumplimiento — incluye NIS2 y RGPD */
const ViewComplianceHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'compliance-hub',
      label: 'Cumplimiento',
      tabs: [
        { id: 'compliance', label: 'Normativo', view: ViewCompliance, route: 'compliance' },
        { id: 'controls', label: 'Controles', view: ViewControls, route: 'controls' },
        { id: 'nis2', label: 'NIS2', view: ViewNis2Dashboard },
        { id: 'ccm', label: 'Monitor', view: ViewCcm },
        { id: 'soa', label: 'SoA', view: ViewSoaVersions },
        { id: 'policies', label: 'Politicas', view: ViewPolicies, route: 'policies' },
        { id: 'gdpr', label: 'RGPD', view: ViewGdpr, route: 'gdpr' },
        { id: 'regwatch', label: 'Vigilancia normativa', view: ViewRegwatch, route: 'regwatch' },
        { id: 'audits', label: 'Auditorias', view: ViewAudits, route: 'internal-audits' },
        { id: 'management-review', label: 'Rev. direccion', view: ViewManagementReview },
        { id: 'change-requests', label: 'Cambios', view: ViewChangeRequests },
      ],
    });
  },
};

/* 5. Incidentes — solo incidentes y no conformidades */
const ViewEventsHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'events-hub',
      label: 'Incidentes',
      tabs: [
        { id: 'incidents', label: 'Incidentes', view: ViewIncidents, route: 'incidents' },
        { id: 'nonconformities', label: 'No conformidades', view: ViewNonConformities, route: 'nonconformities' },
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
        { id: 'documents', label: 'Documentos', view: ViewAiDocuments },
      ],
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
