/* Vistas hub: agrupan las vistas existentes en hubs con pestañas internas
   (progressive disclosure). Cada hub delega el render de cada pestaña en la
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
        { id: 'treatment', label: t('hub.risk.treatment'), view: ViewTreatment, route: 'treatment' },
        { id: 'plan-director', label: t('hub.risk.plan_director'), view: ViewPlanDirector, route: 'plan-director' },
        { id: 'assets', label: t('hub.risk.assets'), view: ViewAssets, route: 'assets' },
        { id: 'threats', label: t('hub.risk.threats'), view: ViewThreats },
        { id: 'vulnerabilities', label: t('hub.risk.vulnerabilities'), view: ViewVulns },
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
        { id: 'visiox', label: t('hub.watch.visiox'), view: ViewVisioX },
        { id: 'cve', label: t('hub.watch.cve'), view: ViewCve, route: 'cve' },
        { id: 'osint', label: t('hub.watch.osint'), view: ViewOsint },
        { id: 'external-findings', label: t('hub.watch.external_findings'), view: ViewExternalFindings },
        { id: 'architecture-review', label: t('hub.watch.architecture'), view: ViewArchitectureReview },
        { id: 'predictive', label: t('hub.watch.predictive'), view: ViewPredictive },
        { id: 'supplier-monitor', label: t('hub.watch.supplier_monitor'), view: ViewSupplierMonitor },
      ],
    });
  },
};

/* Vista de monitoreo automático de proveedores */
const ViewSupplierMonitor = (() => {
  const STATUS_COLOR = { ok: 'var(--risk-low)', issue: 'var(--risk-critical)', unknown: '#9CA3AF' };
  const TIER_COLOR   = { critical: 'var(--risk-critical)', high: 'var(--risk-high)', medium: 'var(--risk-medium)', low: 'var(--risk-low)', unrated: '#9CA3AF' };

  function _statusBadge(status) {
    const c = STATUS_COLOR[status] || '#9CA3AF';
    const labels = { ok: t('supplier_monitor.status_ok'), issue: t('supplier_monitor.status_issue'), unknown: t('supplier_monitor.status_unknown') };
    return `<span style="display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:600;background:${c};color:#fff;">
      <span style="width:7px;height:7px;border-radius:50%;background:rgba(255,255,255,.7);display:inline-block;"></span>${labels[status] || status}</span>`;
  }

  function _tierBadge(tier) {
    if (!tier) return '';
    const c = TIER_COLOR[tier] || '#9CA3AF';
    return `<span style="padding:2px 7px;border-radius:4px;font-size:10px;font-weight:600;background:${c};color:#fff;">${tier.toUpperCase()}</span>`;
  }

  function _fmtDate(iso) {
    if (!iso) return '—';
    try {
      const locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
      return new Date(iso).toLocaleString(locale, { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch (_) { return iso.slice(0, 16); }
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header" style="margin-bottom:16px;">
        <div>
          <h1 class="page-title">${t('supplier_monitor.title')}</h1>
          <p class="page-sub">${t('supplier_monitor.subtitle')}</p>
        </div>
        <button class="btn btn-sm" id="sm-refresh">${t('supplier_monitor.refresh')}</button>
      </div>
      <div id="sm-kpis" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:20px;"></div>
      <div id="sm-table"></div>
    `;
    document.getElementById('sm-refresh').onclick = () => _load(el);
    await _load(el);
  }

  async function _load(el) {
    const tableEl = document.getElementById('sm-table');
    const kpisEl  = document.getElementById('sm-kpis');
    tableEl.innerHTML = `<p class="text-muted">${t('common.loading')}</p>`;
    try {
      const rows = await Api.suppliers.monitoring();
      const total   = rows.length;
      const ok      = rows.filter(r => r.monitoring_status === 'ok').length;
      const issue   = rows.filter(r => r.monitoring_status === 'issue').length;
      const unknown = rows.filter(r => r.monitoring_status === 'unknown').length;

      kpisEl.innerHTML = [
        { label: t('supplier_monitor.kpi_total'),   value: total,   color: 'var(--brand-purple)' },
        { label: t('supplier_monitor.kpi_ok'),       value: ok,      color: 'var(--risk-low)' },
        { label: t('supplier_monitor.kpi_issue'),    value: issue,   color: 'var(--risk-critical)' },
        { label: t('supplier_monitor.kpi_unknown'),  value: unknown, color: '#9CA3AF' },
      ].map(k => `
        <div class="card" style="padding:14px;text-align:center;">
          <div style="font-size:28px;font-weight:700;color:${k.color};">${k.value}</div>
          <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;margin-top:4px;">${k.label}</div>
        </div>`).join('');

      if (!rows.length) {
        tableEl.innerHTML = `<div class="card"><p class="text-muted">${t('supplier_monitor.no_suppliers')}</p></div>`;
        return;
      }

      tableEl.innerHTML = `
        <div class="card" style="padding:0;overflow:hidden;">
          <table class="data" style="width:100%;margin:0;">
            <thead><tr>
              <th>${t('supplier_monitor.col_name')}</th>
              <th>${t('supplier_monitor.col_tier')}</th>
              <th>${t('supplier_monitor.col_target')}</th>
              <th>${t('supplier_monitor.col_status')}</th>
              <th>${t('supplier_monitor.col_last_scan')}</th>
              <th>${t('supplier_monitor.col_finding')}</th>
              <th></th>
            </tr></thead>
            <tbody>
            ${rows.map(r => `
              <tr>
                <td><span style="font-weight:600;">${UI.esc(r.name)}</span><br>
                    <span style="font-size:11px;color:var(--text-muted);">${UI.esc(r.code)}</span></td>
                <td>${_tierBadge(r.tier)}</td>
                <td style="font-size:12px;color:var(--text-muted);">${UI.esc(r.website || r.contact_email || '—')}</td>
                <td>${_statusBadge(r.monitoring_status)}</td>
                <td style="font-size:12px;">${_fmtDate(r.last_monitored_at)}</td>
                <td style="font-size:12px;max-width:260px;">
                  ${r.finding
                    ? `<span style="color:var(--risk-critical);font-weight:600;">${UI.esc(r.finding.severity)}</span> — ${UI.esc((r.finding.description || r.finding.title || '').slice(0, 100))}`
                    : `<span style="color:var(--text-muted);">${t('supplier_monitor.no_finding')}</span>`}
                </td>
                <td><button class="btn btn-sm" data-sm-rescan="${r.id}">${t('supplier_monitor.rescan')}</button></td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>
      `;

      tableEl.querySelectorAll('[data-sm-rescan]').forEach(btn => {
        btn.onclick = async () => {
          const id = btn.dataset.smRescan;
          btn.disabled = true;
          btn.textContent = t('common.loading');
          try {
            const res = await Api.suppliers.rescan(id);
            UI.toast(t('supplier_monitor.rescan_done', { status: res.monitoring_status }), 'success');
            await _load(el);
          } catch (e) {
            UI.toast(e.message, 'error');
            btn.disabled = false;
            btn.textContent = t('supplier_monitor.rescan');
          }
        };
      });
    } catch (e) {
      tableEl.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  return { render };
})();

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
        { id: 'ingest', label: t('hub.bcp.ingest'), view: ViewIngest,
          visible: () => Auth.canEdit() },
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
  { value: 'claude-opus-4-8',   label: t('hub.model_opus') },
  { value: 'claude-opus-4-7',   label: 'Opus 4.7  — muy potente' },
  { value: 'claude-opus-4-6',   label: 'Opus 4.6  — potente (por defecto)' },
  { value: 'claude-sonnet-4-6', label: 'Sonnet 4.6 — equilibrado' },
  { value: 'claude-haiku-4-5',  label: t('hub.model_haiku') },
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
    const decryptError = !!cfg.api_key_decrypt_error;

    el.innerHTML = `
      <div style="max-width:560px;padding:24px;display:grid;gap:24px;">

        ${decryptError ? `
        <div style="padding:14px 16px;background:#fff3cd;border:1px solid #ffc107;border-radius:8px;color:#856404;font-size:13px;line-height:1.5;">
          <strong>Aviso: la API key no puede descifrarse.</strong><br>
          La clave guardada en la base de datos no puede leerse porque
          <code>RISKHUB_SECRET_KEY</code> cambio desde que se guardo.
          Introduce la API key de nuevo para que quede cifrada con la clave actual.
        </div>` : ''}

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
              ${decryptError ? 'Vuelve a introducir la API key (sk-ant-api03-...)' : hasKey ? t('ai.settings_change_key') : t('ai.settings_enter_key')}
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
            <strong>Opus 4.8 / 4.7</strong> — análisis complejos, documentos largos, mayor precisión.<br>
            <strong>Opus 4.6</strong> — excelente calidad, buen equilibrio coste/rendimiento.<br>
            <strong>Sonnet 4.6</strong> — rápido y capaz, ideal para uso intensivo.<br>
            <strong>Haiku 4.5</strong> — el mas economico, adecuado para tareas simples y alertas.
          </div>
          <label style="display:flex;align-items:flex-start;gap:10px;font-size:13px;cursor:pointer;">
            <input type="checkbox" id="ai-force-deep" ${cfg.force_deep_analysis ? 'checked' : ''}
                   style="margin-top:2px;">
            <span>
              <strong>${t('ai.settings_force_deep')}</strong><br>
              <span style="color:var(--text-muted);font-size:12px;">${t('ai.settings_force_deep_desc')}</span>
            </span>
          </label>
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
      const forceDeep = document.getElementById('ai-force-deep').checked;
      const payload = { model, force_deep_analysis: forceDeep };
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

/* 10. Setup — asistente de configuración inicial */
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

/* 10. Configuración (solo admin; organizaciones y módulos solo superadmin) */
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
        { id: 'ops', label: t('hub.admin.ops'), view: ViewOps, visible: () => Auth.isAdmin() },
        { id: 'method', label: t('hub.admin.method'), view: ViewMethod, visible: () => Auth.isAdmin() },
        { id: 'license', label: t('hub.admin.license'), view: ViewLicense, visible: () => Auth.isAdmin() },
      ],
    });
  },
};
