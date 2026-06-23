/* Vistas hub: agrupan las vistas existentes en hubs con pestanas internas
   (progressive disclosure). Cada hub delega el render de cada pestana en la
   View original via UI.tabs — las vistas existentes no se modifican. */

/* 1. Inicio */
const ViewHomeHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'home',
      label: t('nav.home'),
      tabs: [
        {
          id: 'dashboard', label: t('hub.home.dashboard'),
          render: async (panel) => {
            panel.innerHTML = '<div id="home-dashboard-mount"></div>';
            await ViewDashboard.render(panel.querySelector('#home-dashboard-mount'));
          },
        },
        { id: 'executive', label: t('hub.home.executive'), view: ViewExecutive },
        { id: 'heatmap', label: t('hub.home.heatmap'), view: ViewHeatmap },
      ],
    });
  },
};

/* 2. Riesgos y activos */
const ViewRiskHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'risk-hub',
      label: t('nav.risks_assets'),
      tabs: [
        { id: 'risks', label: t('hub.risk.risks'), view: ViewRisks, route: 'risks' },
        { id: 'assets', label: t('hub.risk.assets'), view: ViewAssets, route: 'assets' },
        { id: 'threats', label: t('hub.risk.threats'), view: ViewThreats },
        { id: 'vulnerabilities', label: t('hub.risk.vulnerabilities'), view: ViewVulns },
        { id: 'magerit', label: t('hub.risk.magerit'), view: ViewMagerit },
        { id: 'kris', label: t('hub.risk.kris'), view: ViewKRIs, route: 'kris' },
      ],
    });
  },
};

/* 3. Vigilancia */
const ViewWatchHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'watch-hub',
      label: t('nav.watch'),
      tabs: [
        { id: 'cve', label: t('hub.watch.cve'), view: ViewCve, route: 'cve' },
        { id: 'osint', label: t('hub.watch.osint'), view: ViewOsint },
        { id: 'external-findings', label: t('hub.watch.external_findings'), view: ViewExternalFindings },
        { id: 'architecture-review', label: t('hub.watch.architecture'), view: ViewArchitectureReview },
        { id: 'predictive', label: t('hub.watch.predictive'), view: ViewPredictive },
      ],
    });
  },
};

/* 4. Cumplimiento */
const ViewComplianceHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'compliance-hub',
      label: t('nav.compliance'),
      tabs: [
        { id: 'compliance', label: t('hub.compliance.normative'), view: ViewCompliance, route: 'compliance' },
        { id: 'controls', label: t('hub.compliance.controls'), view: ViewControls, route: 'controls' },
        { id: 'soa', label: t('hub.compliance.soa'), view: ViewSoaVersions },
        { id: 'policies', label: t('hub.compliance.policies'), view: ViewIsmsDocuments, route: 'policies' },
        {
          id: 'legal',
          label: t('hub.compliance.legal'),
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
        { id: 'audits', label: t('hub.compliance.audits'), view: ViewAudits, route: 'internal-audits' },
        { id: 'nonconformities', label: t('hub.compliance.nonconformities'), view: ViewNonConformities, route: 'nonconformities' },
        { id: 'change-requests', label: t('hub.compliance.change_requests'), view: ViewChangeRequests },
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
      label: t('nav.incidents'),
      tabs: [
        { id: 'incidents', label: t('hub.events.incidents'), view: ViewIncidents, route: 'incidents' },
      ],
    });
  },
};

/* 6. BCP — hub independiente */
const ViewBcpHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'bcp-hub',
      label: t('nav.bcp'),
      tabs: [
        { id: 'bcp', label: t('hub.bcp.bcp'), view: ViewBcp },
      ],
    });
  },
};

/* 7. Informes */
const ViewReportsHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'reports-hub',
      label: t('nav.reports'),
      tabs: [
        { id: 'reports', label: t('hub.reports.reports'), view: ViewReports, route: 'reports' },
        { id: 'schedules', label: t('hub.reports.schedules'), view: ViewReportSchedules },
        { id: 'management-review', label: t('hub.reports.management_review'), view: ViewManagementReview, route: 'management-review' },
        { id: 'evidence', label: t('hub.reports.evidence'), view: ViewEvidence },
        { id: 'trust-portal', label: t('hub.reports.trust_portal'), view: ViewTrustPortal, visible: () => Auth.isAdmin() },
        { id: 'calendar', label: t('hub.reports.calendar'), view: ViewCalendar },
        { id: 'tasks', label: t('hub.reports.tasks'), view: ViewTasks, route: 'tasks' },
      ],
    });
  },
};

/* 8. Agente IA */
const ViewAiHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'ai-hub',
      label: t('nav.ai'),
      tabs: [
        { id: 'chat', label: t('hub.ai.chat'), view: ViewAiChat, route: 'ai-chat' },
        { id: 'awareness', label: t('hub.ai.awareness'), view: ViewAwareness, route: 'awareness' },
        {
          id: 'documents',
          label: t('hub.ai.ai_documents'),
          render: async (_panel) => { location.hash = '/compliance-hub/policies'; },
        },
        {
          id: 'ai-settings',
          label: t('hub.ai.settings'),
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
    el.innerHTML = `<p class="text-muted" style="padding:24px;">${t('common.loading')}</p>`;
    let cfg;
    try {
      cfg = await Api.aiConfig.get();
    } catch (e) {
      el.innerHTML = `<p style="color:var(--danger);padding:24px;">${t('ai.settings_error')} ${UI.esc(e.message)}</p>`;
      return;
    }

    const currentModel = cfg.model || 'claude-opus-4-6';
    const hasKey = !!cfg.has_api_key;

    el.innerHTML = `
      <div style="max-width:560px;padding:24px;display:grid;gap:24px;">

        <div class="card" style="padding:20px;display:grid;gap:16px;">
          <h3 style="margin:0;font-size:15px;font-weight:600;">${t('ai.settings_api_key_title')}</h3>
          <div style="display:flex;align-items:center;gap:12px;">
            <span style="display:inline-block;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:600;
              background:${hasKey ? 'var(--success,#22c55e)' : 'var(--danger,#ef4444)'};color:#fff;">
              ${hasKey ? t('ai.settings_api_key_set') : t('ai.settings_api_key_not_set')}
            </span>
            <span style="font-size:13px;color:var(--text-muted);">
              ${hasKey ? t('ai.settings_api_key_stored') : t('ai.settings_api_key_missing')}
            </span>
          </div>
          <div style="display:grid;gap:8px;">
            <label for="ai-apikey" style="font-size:13px;font-weight:500;">
              ${hasKey ? t('ai.settings_change_key') : t('ai.settings_enter_key')}
            </label>
            <input type="password" id="ai-apikey" placeholder="sk-ant-api03-..."
              autocomplete="new-password"
              style="font-family:monospace;font-size:13px;">
          </div>
        </div>

        <div class="card" style="padding:20px;display:grid;gap:16px;">
          <h3 style="margin:0;font-size:15px;font-weight:600;">${t('ai.settings_model_title')}</h3>
          <p style="margin:0;font-size:13px;color:var(--text-muted);">
            ${t('ai.settings_model_desc')}
          </p>
          <div style="display:grid;gap:8px;">
            <label for="ai-model" style="font-size:13px;font-weight:500;">${t('ai.settings_active_model')}</label>
            <select id="ai-model" style="font-size:13px;">
              ${_AI_MODELS.map(m =>
                `<option value="${m.value}"${m.value === currentModel ? ' selected' : ''}>${UI.esc(m.label)}</option>`
              ).join('')}
            </select>
          </div>
          <div style="padding:10px 12px;background:var(--bg-2);border-radius:6px;font-size:12px;color:var(--text-muted);">
            <strong>${t('ai.settings_quick_guide')}</strong><br>
            <strong>Opus 4.8 / 4.7</strong> — analisis complejos, documentos largos, mayor precision.<br>
            <strong>Opus 4.6</strong> — excelente calidad, buen equilibrio coste/rendimiento.<br>
            <strong>Sonnet 4.6</strong> — rapido y capaz, ideal para uso intensivo.<br>
            <strong>Haiku 4.5</strong> — el mas economico, adecuado para tareas simples y alertas.
          </div>
        </div>

        <div style="display:flex;gap:10px;align-items:center;">
          <button class="btn btn-primary" id="ai-cfg-save">${t('ai.settings_save')}</button>
          <button class="btn btn-ghost" id="ai-cfg-test">${t('ai.settings_test')}</button>
          <span id="ai-cfg-msg" style="font-size:13px;"></span>
        </div>
      </div>`;

    document.getElementById('ai-cfg-save').addEventListener('click', async () => {
      const msg   = document.getElementById('ai-cfg-msg');
      const model = document.getElementById('ai-model').value;
      const key   = (document.getElementById('ai-apikey').value || '').trim();
      const payload = { model };
      if (key) payload.api_key = key;
      msg.textContent = t('ai.settings_saving');
      msg.style.color = 'var(--text-muted)';
      try {
        await Api.aiConfig.update(payload);
        msg.textContent = t('ai.settings_saved');
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
      msg.textContent = t('ai.settings_testing');
      msg.style.color = 'var(--text-muted)';
      try {
        const res = await Api.aiConfig.test();
        msg.textContent = t('ai.settings_connection_ok', { model: res.model });
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
      label: t('nav.suppliers'),
      tabs: [
        { id: 'tprm', label: t('hub.suppliers.tprm'), view: ViewTprm, route: 'tprm' },
        { id: 'suppliers', label: t('hub.suppliers.suppliers'), view: ViewSuppliers, route: 'suppliers' },
        { id: 'assessments', label: t('hub.suppliers.assessments'), view: ViewVendorAssessments, route: 'vendor-assessments' },
        { id: 'issues', label: t('hub.suppliers.issues'), view: ViewVendorIssues, route: 'vendor-issues' },
        { id: 'templates', label: t('hub.suppliers.templates'), view: ViewVendorTemplates, route: 'vendor-templates' },
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
          id: 'wizard', label: t('hub.setup.wizard'),
          render: async (panel) => { await ViewOnboarding.render(panel); },
        },
        { id: 'context', label: t('hub.setup.context'), view: ViewContext, route: 'context' },
        { id: 'regwatch', label: t('hub.setup.regwatch'), view: ViewRegwatch, route: 'regwatch' },
      ],
    });
  },
};

/* 10. Configuracion (solo admin; organizaciones y modulos solo superadmin) */
const ViewAdminHub = {
  async render(el) {
    UI.tabs(el, {
      hub: 'admin-hub',
      label: t('nav.config'),
      tabs: [
        { id: 'users', label: t('hub.admin.users'), view: ViewUsers, visible: () => Auth.isAdmin() },
        { id: 'integrations', label: t('hub.admin.integrations'), view: ViewIntegrations, route: 'integrations' },
        { id: 'itsm', label: t('hub.admin.itsm'), view: ViewItsmConfig, visible: () => Auth.isAdmin() },
        { id: 'webhooks', label: t('hub.admin.webhooks'), view: ViewWebhooks, visible: () => Auth.isAdmin() },
        { id: 'alerts', label: t('hub.admin.alerts'), view: ViewAlerts, route: 'alerts' },
        { id: 'audit', label: t('hub.admin.audit_log'), view: ViewAudit, visible: () => Auth.isAdmin() },
        { id: 'organizations', label: t('hub.admin.organizations'), view: ViewOrganizations, visible: () => Auth.isSuperAdmin() },
        { id: 'feature-flags', label: t('hub.admin.modules'), view: ViewFeatureFlags, visible: () => Auth.isSuperAdmin() },
        { id: 'license', label: t('hub.admin.license'), view: ViewLicense, visible: () => Auth.isAdmin() },
      ],
    });
  },
};
