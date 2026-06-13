/* Vistas hub: agrupan las vistas existentes en 8 hubs con pestanas internas
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

/* 4. Cumplimiento */
const ViewComplianceHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'compliance-hub',
      label: 'Cumplimiento',
      tabs: [
        { id: 'compliance', label: 'Normativo', view: ViewCompliance, route: 'compliance' },
        { id: 'controls', label: 'Controles', view: ViewControls, route: 'controls' },
        { id: 'ccm', label: 'Monitor', view: ViewCcm },
        { id: 'soa', label: 'SoA', view: ViewSoaVersions },
        { id: 'policies', label: 'Politicas', view: ViewPolicies, route: 'policies' },
        { id: 'audits', label: 'Auditorias', view: ViewAudits, route: 'internal-audits' },
        { id: 'management-review', label: 'Rev. direccion', view: ViewManagementReview },
        { id: 'change-requests', label: 'Cambios', view: ViewChangeRequests },
      ],
    });
  },
};

/* 5. Eventos */
const ViewEventsHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'events-hub',
      label: 'Eventos',
      tabs: [
        { id: 'incidents', label: 'Incidentes', view: ViewIncidents, route: 'incidents' },
        { id: 'nis2', label: 'NIS2', view: ViewNis2Dashboard },
        { id: 'nonconformities', label: 'No conformidades', view: ViewNonConformities, route: 'nonconformities' },
        { id: 'bcp', label: 'BCP', view: ViewBcp },
        { id: 'suppliers', label: 'Proveedores', view: ViewSuppliers, route: 'suppliers' },
        { id: 'gdpr', label: 'RGPD', view: ViewGdpr, route: 'gdpr' },
      ],
    });
  },
};

/* 6. Informes */
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

/* 7. Agente IA */
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

/* 8. Configuracion (solo admin; organizaciones y modulos solo superadmin) */
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
