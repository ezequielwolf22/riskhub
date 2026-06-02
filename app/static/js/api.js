/* Cliente HTTP centralizado para la API REST de RiskHub. */
const Api = {
  token() { return localStorage.getItem('riskhub_token'); },

  async req(path, opts = {}) {
    const headers = opts.headers || {};
    const tok = Api.token();
    if (tok) headers['Authorization'] = 'Bearer ' + tok;
    if (opts.body && !headers['Content-Type'] && !(opts.body instanceof FormData))
      headers['Content-Type'] = 'application/json';

    let resp;
    try {
      resp = await fetch(path, { ...opts, headers });
    } catch (_netErr) {
      // Error de red (sin conexion, proxy bloqueando, DNS, etc.)
      throw new Error('No se pudo conectar con el servidor. Verifica tu conexion de red.');
    }

    if (resp.status === 401) {
      localStorage.removeItem('riskhub_token');
      localStorage.removeItem('riskhub_user');
      window.location.href = '/login';
      throw new Error('No autorizado');
    }
    const ctype = resp.headers.get('content-type') || '';
    let data = null;
    if (resp.status === 204) {
      data = null;
    } else if (ctype.includes('application/json')) {
      data = await resp.json();
    } else {
      const text = await resp.text();
      // Si la respuesta es HTML (proxy, firewall, pagina de error del servidor)
      // no mostramos el HTML crudo — mostramos un mensaje limpio
      if (text && (text.trimStart().startsWith('<') || ctype.includes('text/html'))) {
        data = null;  // se usara el statusText
      } else {
        data = text;
      }
    }

    if (!resp.ok) {
      let msg;
      if (data && data.detail) {
        msg = data.detail;
      } else if (typeof data === 'string' && data && !data.trimStart().startsWith('<')) {
        msg = data;
      } else {
        // Respuesta HTML o vacia: mensaje generico con el codigo HTTP
        msg = `Error ${resp.status}: ${resp.statusText || 'Error del servidor'}`;
      }
      const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      err.status = resp.status; err.data = data; throw err;
    }
    return data;
  },

  get(p, q) {
    const url = q ? p + '?' + new URLSearchParams(q).toString() : p;
    return Api.req(url);
  },
  post(p, body) { return Api.req(p, { method: 'POST', body: JSON.stringify(body) }); },
  patch(p, body) { return Api.req(p, { method: 'PATCH', body: JSON.stringify(body) }); },
  put(p, body) { return Api.req(p, { method: 'PUT', body: JSON.stringify(body) }); },
  del(p) { return Api.req(p, { method: 'DELETE' }); },
  postFile(p, file) {
    const fd = new FormData(); fd.append('file', file);
    return Api.req(p, { method: 'POST', body: fd });
  },
  download(p, filename) {
    const tok = Api.token();
    return fetch(p, { headers: { 'Authorization': 'Bearer ' + tok } })
      .then(r => r.blob())
      .then(b => {
        const url = URL.createObjectURL(b);
        const a = document.createElement('a');
        a.href = url; a.download = filename; a.click();
        URL.revokeObjectURL(url);
      });
  },

  // Endpoints específicos
  me: () => Api.get('/api/auth/me'),
  changePassword: (d) => Api.patch('/api/auth/me/password', d),
  setInitialPassword: (d) => Api.post('/api/auth/set-initial-password', d),
  listUsers: () => Api.get('/api/auth/users'),
  mfa: {
    setup: () => Api.post('/api/auth/mfa/setup', {}),
    verifySetup: (d) => Api.post('/api/auth/mfa/verify-setup', d),
    disable: () => Api.post('/api/auth/mfa/disable', {}),
    disableAdmin: (userId) => Api.post('/api/auth/mfa/disable-admin', { user_id: userId }),
    complete: (d) => Api.post('/api/auth/mfa/complete', d),
  },
  context: {
    get: () => Api.get('/api/context/'),
    update: (d) => Api.put('/api/context/', d),
  },
  assets: {
    list: (q) => Api.get('/api/assets/', q),
    get: (id) => Api.get('/api/assets/' + id),
    create: (d) => Api.post('/api/assets/', d),
    update: (id, d) => Api.put('/api/assets/' + id, d),
    del: (id) => Api.del('/api/assets/' + id),
    template: () => Api.download('/api/assets/import/template', 'assets_template.csv'),
    import: (file) => Api.postFile('/api/assets/import', file),
    smartImport: (file) => Api.postFile('/api/assets/smart-import', file),
    exportCsv: () => Api.download('/api/assets/export/csv', 'assets.csv'),
    analyze: (id) => Api.post('/api/assets/' + id + '/analyze', {}),
    analyzeAll: () => Api.post('/api/assets/analyze-all', {}),
    analyzeAllForce: () => Api.post('/api/assets/analyze-all-force', {}),
    analysisStatus: () => Api.get('/api/assets/analysis-status'),
    bulkDelete: (ids) => Api.post('/api/assets/bulk-delete', { ids }),
  },
  assetGroups: {
    getConfig: () => Api.get('/api/asset-groups/config'),
    saveConfig: (d) => Api.put('/api/asset-groups/config', d),
    resetConfig: () => Api.del('/api/asset-groups/config'),
    propose: () => Api.post('/api/asset-groups/propose', {}),
    list: (status) => Api.get('/api/asset-groups/', status ? { status } : undefined),
    create: (d) => Api.post('/api/asset-groups/', d),
    update: (id, d) => Api.put('/api/asset-groups/' + id, d),
    del: (id) => Api.del('/api/asset-groups/' + id),
    deleteWithAssets: (id) => Api.del('/api/asset-groups/' + id + '/with-assets'),
    validate: (id) => Api.post('/api/asset-groups/' + id + '/validate', {}),
    validateAll: () => Api.post('/api/asset-groups/validate-all', {}),
    moveAsset: (d) => Api.post('/api/asset-groups/move-asset', d),
    split: (id, d) => Api.post('/api/asset-groups/' + id + '/split', d),
  },
  threats: {
    list: (q) => Api.get('/api/threats/', q),
    create: (d) => Api.post('/api/threats/', d),
    update: (id, d) => Api.put('/api/threats/' + id, d),
    del: (id) => Api.del('/api/threats/' + id),
  },
  vulns: {
    list: (q) => Api.get('/api/vulnerabilities/', q),
    create: (d) => Api.post('/api/vulnerabilities/', d),
    update: (id, d) => Api.put('/api/vulnerabilities/' + id, d),
    del: (id) => Api.del('/api/vulnerabilities/' + id),
  },
  audit: {
    list: (q) => Api.get('/api/audit/', q),
    entityTypes: () => Api.get('/api/audit/entity-types'),
    actions: () => Api.get('/api/audit/actions'),
    exportCsv: () => Api.download('/api/audit/export/csv', 'audit_log.csv'),
    history: (type, id) => Api.get(`/api/audit/history/${type}/${id}`),
  },
  controls: {
    list: (q) => Api.get('/api/controls/', q),
    create: (d) => Api.post('/api/controls/', d),
    exportSoaCsv: () => Api.download('/api/controls/export-soa-csv', `soa_${new Date().toISOString().slice(0,10)}.csv`),
    statsByTheme: () => Api.get('/api/controls/stats/by-theme'),
  },
  impls: {
    list: () => Api.get('/api/control-implementations/'),
    create: (d) => Api.post('/api/control-implementations/', d),
    update: (id, d) => Api.put('/api/control-implementations/' + id, d),
    del: (id) => Api.del('/api/control-implementations/' + id),
    propagate: (id) => Api.post('/api/control-implementations/' + id + '/propagate', {}),
  },
  risks: {
    list: (q) => Api.get('/api/risks/', q),
    groupSummary: () => Api.get('/api/risks/group-summary'),
    listOverdue: () => Api.get('/api/risks/', { overdue: true }),
    get: (id) => Api.get('/api/risks/' + id),
    create: (d) => Api.post('/api/risks/', d),
    update: (id, d) => Api.patch('/api/risks/' + id, d),
    del: (id) => Api.del('/api/risks/' + id),
    summary: () => Api.get('/api/risks/stats/summary'),
    heatmap: (mode = 'residual') => Api.get('/api/risks/heatmap/data?mode=' + mode),
    exportCsv: () => Api.download('/api/risks/export/csv', `riesgos_${new Date().toISOString().slice(0,10)}.csv`),
    importTemplate: () => Api.download('/api/risks/import/template', 'risks_template.csv'),
    importCsv: (file) => Api.postFile('/api/risks/import', file),
  },
  users: {
    list: () => Api.get('/api/users/'),
    create: (d) => Api.post('/api/users/', d),
    update: (id, d) => Api.patch('/api/users/' + id, d),
    del: (id) => Api.del('/api/users/' + id),
  },
  reports: {
    riskRegister: () => Api.download('/api/reports/risk-register', 'risk_register.pdf'),
    soa: () => Api.download('/api/reports/soa', `SOA_${new Date().toISOString().slice(0,10)}.pdf`),
    riskRegisterExcel: () => Api.download('/api/reports/risk-register-excel', `dashboard_ejecutivo_${new Date().toISOString().slice(0,10)}.xlsx`),
    aiGenerate: (d) => Api.post('/api/reports/ai-generate', d),
    managementReview: (fmt) => Api.download(
      `/api/reports/management-review?format=${fmt}`,
      `revision_direccion_${new Date().toISOString().slice(0,10)}.${fmt === 'word' ? 'docx' : fmt}`
    ),
  },
  incidents: {
    list: (q) => Api.get('/api/incidents/', q),
    get: (id) => Api.get('/api/incidents/' + id),
    create: (d) => Api.post('/api/incidents/', d),
    update: (id, d) => Api.patch('/api/incidents/' + id, d),
    del: (id) => Api.del('/api/incidents/' + id),
    summary: () => Api.get('/api/incidents/stats/summary'),
  },
  suppliers: {
    list: (q) => Api.get('/api/suppliers/', q),
    get: (id) => Api.get('/api/suppliers/' + id),
    create: (d) => Api.post('/api/suppliers/', d),
    update: (id, d) => Api.patch('/api/suppliers/' + id, d),
    del: (id) => Api.del('/api/suppliers/' + id),
    summary: () => Api.get('/api/suppliers/stats/summary'),
  },
  nonconformities: {
    list: (q) => Api.get('/api/nonconformities/', q),
    get: (id) => Api.get('/api/nonconformities/' + id),
    create: (d) => Api.post('/api/nonconformities/', d),
    update: (id, d) => Api.patch('/api/nonconformities/' + id, d),
    del: (id) => Api.del('/api/nonconformities/' + id),
    summary: () => Api.get('/api/nonconformities/stats/summary'),
  },
  compliance: {
    summary: () => Api.get('/api/ai/compliance/summary'),
  },
  ai: {
    riskSuggest: (d) => Api.post('/api/ai/risk-suggest', d),
    controlGap: (d) => Api.post('/api/ai/control-gap', d),
    chat: (d) => Api.post('/api/ai/chat', d),
    executeAction: (d) => Api.post('/api/ai/execute-action', d),
    feedback: (d) => Api.post('/api/ai/feedback', d),
    feedbackSummary: () => Api.get('/api/ai/feedback/summary'),
    controlGapDetailed: (d) => Api.post('/api/ai/control-gap-detailed', d),
    architectureReview: () => Api.post('/api/ai/architecture-review', {}),
  },
  aiConfig: {
    get: () => Api.get('/api/ai/config/'),
    update: (d) => Api.put('/api/ai/config/', d),
    test: () => Api.post('/api/ai/config/test', {}),
  },
  aiDocuments: {
    list: () => Api.get('/api/ai/documents/'),
    upload: (file, category) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('category', category);
      return Api.req('/api/ai/documents/', { method: 'POST', body: fd });
    },
    del: (id) => Api.del('/api/ai/documents/' + id),
    reprocess: (id) => Api.post('/api/ai/documents/' + id + '/reprocess', {}),
    analyze: (id) => Api.post('/api/ai/documents/' + id + '/analyze', {}),
    analyzeAll: () => Api.post('/api/ai/documents/analyze-all', {}),
  },
  tasks: {
    list: (q) => Api.get('/api/tasks/', q),
    get: (id) => Api.get('/api/tasks/' + id),
    create: (d) => Api.post('/api/tasks/', d),
    update: (id, d) => Api.patch('/api/tasks/' + id, d),
    del: (id) => Api.del('/api/tasks/' + id),
    summary: () => Api.get('/api/tasks/stats/summary'),
  },
  policies: {
    list: (q) => Api.get('/api/policies/', q),
    get: (id) => Api.get('/api/policies/' + id),
    create: (d) => Api.post('/api/policies/', d),
    update: (id, d) => Api.patch('/api/policies/' + id, d),
    del: (id) => Api.del('/api/policies/' + id),
    summary: () => Api.get('/api/policies/stats/summary'),
    aiExtract: (file) => {
      const fd = new FormData();
      fd.append('file', file);
      return Api.req('/api/policies/ai-extract', { method: 'POST', body: fd });
    },
  },
  audits: {
    list: (q) => Api.get('/api/audits/', q),
    get: (id) => Api.get('/api/audits/' + id),
    create: (d) => Api.post('/api/audits/', d),
    update: (id, d) => Api.patch('/api/audits/' + id, d),
    del: (id) => Api.del('/api/audits/' + id),
    summary: () => Api.get('/api/audits/stats/summary'),
    findings: (id) => Api.get('/api/audits/' + id + '/findings'),
    createFinding: (id, d) => Api.post('/api/audits/' + id + '/findings', d),
    updateFinding: (id, fid, d) => Api.patch('/api/audits/' + id + '/findings/' + fid, d),
    delFinding: (id, fid) => Api.del('/api/audits/' + id + '/findings/' + fid),
  },
  supplier_questionnaires: {
    list: (q) => Api.get('/api/supplier-questionnaires/', q),
    get: (id) => Api.get('/api/supplier-questionnaires/' + id),
    create: (d) => Api.post('/api/supplier-questionnaires/', d),
    del: (id) => Api.del('/api/supplier-questionnaires/' + id),
  },
  gdpr: {
    activities: {
      list: (q) => Api.get('/api/gdpr/activities/', q),
      get: (id) => Api.get('/api/gdpr/activities/' + id),
      create: (d) => Api.post('/api/gdpr/activities/', d),
      update: (id, d) => Api.patch('/api/gdpr/activities/' + id, d),
      del: (id) => Api.del('/api/gdpr/activities/' + id),
    },
    dpias: {
      list: (q) => Api.get('/api/gdpr/dpias/', q),
      get: (id) => Api.get('/api/gdpr/dpias/' + id),
      create: (d) => Api.post('/api/gdpr/dpias/', d),
      update: (id, d) => Api.patch('/api/gdpr/dpias/' + id, d),
      del: (id) => Api.del('/api/gdpr/dpias/' + id),
    },
    summary: () => Api.get('/api/gdpr/stats/summary'),
  },
  featureFlags: {
    list: (orgId) => Api.get('/api/feature-flags/' + (orgId ? '?org_id=' + orgId : '')),
    update: (name, enabled, orgId) => Api.patch('/api/feature-flags/' + name, { enabled, organization_id: orgId || null }),
    reset: (name, orgId) => Api.del('/api/feature-flags/' + name + '?org_id=' + orgId),
  },
  sharepoint: {
    getConfig: () => Api.get('/api/integrations/sharepoint/config'),
    saveConfig: (d) => Api.put('/api/integrations/sharepoint/config', d),
    test: () => Api.post('/api/integrations/sharepoint/test', {}),
    sites: (search) => Api.get('/api/integrations/sharepoint/sites', search ? { search } : {}),
    drives: (site_id) => Api.get('/api/integrations/sharepoint/drives', { site_id }),
    files: (drive_id, item_id) => Api.get('/api/integrations/sharepoint/files',
      item_id && item_id !== 'root' ? { drive_id, item_id } : { drive_id }),
    importFiles: (items, category) => Api.post('/api/integrations/sharepoint/import', { items, category }),
  },
  cve: {
    getConfig: () => Api.get('/api/cve/config'),
    saveConfig: (d) => Api.put('/api/cve/config', d),
    search: (q) => Api.get('/api/cve/search', q),
    lookup: (q) => Api.get('/api/cve/lookup', { q }),
    analyze: (d) => Api.post('/api/cve/analyze', d),
    autoScan: (d) => Api.post('/api/cve/auto-scan', d),
    createRisk: (d) => Api.post('/api/cve/create-risk', d),
  },
  awareness: {
    getBranding:   ()  => Api.get('/api/awareness/branding'),
    saveBranding:  (d) => Api.put('/api/awareness/branding', d),
    uploadLogo:    (fd) => {
      const token = localStorage.getItem('riskhub_token') || '';
      return fetch('/api/awareness/branding/logo', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: fd,
      }).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e.detail))));
    },
    deleteLogo:    ()  => Api.del('/api/awareness/branding/logo'),
    getLogo:       ()  => Api.get('/api/awareness/branding/logo'),
    generate:      (d) => Api.post('/api/awareness/generate', d),
    list:          ()  => Api.get('/api/awareness/'),
    create:        (d) => Api.post('/api/awareness/', d),
    get:           (id) => Api.get(`/api/awareness/${id}`),
    update:        (id, d) => Api.put(`/api/awareness/${id}`, d),
    delete:        (id) => Api.del(`/api/awareness/${id}`),
    exportPdf:     (id) => `/api/awareness/${id}/export-pdf`,
  },
  sso: {
    status: () => Api.get('/api/sso/status'),
    getConfig: () => Api.get('/api/sso/config'),
    saveConfig: (d) => Api.put('/api/sso/config', d),
    deleteConfig: () => Api.del('/api/sso/config'),
    test: () => Api.post('/api/sso/test', {}),
  },
  search: (q) => Api.get('/api/search/', { q }),
  admin: {
    systemInfo: () => Api.get('/api/admin/system-info'),
    backupDb: () => Api.download('/api/admin/backup-db', `riskhub_backup_${new Date().toISOString().slice(0,10)}.db`),
    securityStatus: () => Api.get('/api/admin/security-status'),
  },
  alerts: {
    getSettings: () => Api.get('/api/alerts/settings'),
    saveSettings: (d) => Api.put('/api/alerts/settings', d),
    test: () => Api.post('/api/alerts/test', {}),
    rules: () => Api.get('/api/alerts/rules'),
    createRule: (d) => Api.post('/api/alerts/rules', d),
    deleteRule: (id) => Api.del('/api/alerts/rules/' + id),
    toggleRule: (id) => Api.patch('/api/alerts/rules/' + id + '/toggle', {}),
    checkRules: () => Api.post('/api/alerts/check-rules', {}),
    sendRisk: (id, d) => Api.post('/api/alerts/send-risk/' + id, d),
  },
  magerit: {
    threats:       ()         => Api.get('/api/magerit/threats'),
    seed:          ()         => Api.post('/api/magerit/seed', {}),
    deleteCatalog: ()         => Api.del('/api/magerit/catalog'),
    analysis:      ()         => Api.get('/api/magerit/analysis'),
    valuation:     (asset_id) => Api.get(`/api/magerit/assets/${asset_id}/valuation`),
    scale:         ()         => Api.get('/api/magerit/scale'),
  },
  portal: {
    trust: {
      getConfig:       ()           => Api.get('/api/portal/trust/config'),
      saveConfig:      (d)          => Api.put('/api/portal/trust/config', d),
      regenerateToken: ()           => Api.post('/api/portal/trust/regenerate-token', {}),
      getData:         (org, token) => Api.get(`/api/portal/trust/data/${org}/${token}`),
    },
    auditor: {
      getConfig:       ()              => Api.get('/api/portal/auditor/config'),
      regenerateToken: ()              => Api.post('/api/portal/auditor/regenerate-token', {}),
      getData:         (org, token, fw) => Api.get(`/api/portal/auditor/data/${org}/${token}`, fw ? {framework: fw} : {}),
    },
  },
  complianceFrameworks: {
    list:             ()           => Api.get('/api/compliance/frameworks'),
    get:              (code)       => Api.get('/api/compliance/frameworks/' + code),
    status:           ()           => Api.get('/api/compliance/status'),
    frameworkStatus:  (code)       => Api.get('/api/compliance/status/' + code),
    subscribe:        (d)          => Api.post('/api/compliance/subscribe', d),
    updateRequirement:(fw, req, d) => Api.put(`/api/compliance/requirements/${fw}/${req}`, d),
    syncControls:     ()           => Api.post('/api/compliance/sync-controls', {}),
  },
  evidence: {
    list:       (q)  => Api.get('/api/evidence', q),
    get:        (id) => Api.get('/api/evidence/' + id),
    del:        (id) => Api.del('/api/evidence/' + id),
    download:   (id) => `/api/evidence/${id}/download`,
    upload: (fd) => {
      const token = localStorage.getItem('riskhub_token') || '';
      return fetch('/api/evidence', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: fd,
      }).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e.detail || JSON.stringify(e)))));
    },
    newVersion: (id, fd) => {
      const token = localStorage.getItem('riskhub_token') || '';
      return fetch(`/api/evidence/${id}/new-version`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: fd,
      }).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e.detail || JSON.stringify(e)))));
    },
  },
  executive: {
    kpis:        ()        => Api.get('/api/executive/kpis'),
    topRisks:    (limit)   => Api.get('/api/executive/top-risks', limit ? { limit } : {}),
    riskTrend:   (days)    => Api.get('/api/executive/risk-trend', days ? { days } : {}),
    heatmap:     ()        => Api.get('/api/executive/heatmap'),
    boardReport: ()        => Api.get('/api/executive/board-report'),
    boardPdf:    ()        => '/api/executive/board-report/pdf',
  },
  webhooks: {
    list:      ()        => Api.get('/api/webhooks'),
    events:    ()        => Api.get('/api/webhooks/events'),
    create:    (d)       => Api.post('/api/webhooks', d),
    update:    (id, d)   => Api.put('/api/webhooks/' + id, d),
    del:       (id)      => Api.del('/api/webhooks/' + id),
    test:      (id)      => Api.post(`/api/webhooks/${id}/test`, {}),
    deliveries:(id)      => Api.get(`/api/webhooks/${id}/deliveries`),
  },
  ccm: {
    catalog:   ()         => Api.get('/api/ccm/catalog'),
    run:       ()         => Api.post('/api/ccm/run', {}),
    runTest:   (test_id)  => Api.post(`/api/ccm/run/${test_id}`, {}),
  },
  policyTemplates: {
    list:     ()           => Api.get('/api/policies/templates'),
    generate: (d)          => Api.post('/api/policies/generate', d),
  },
  predictive: {
    trend:           (days)  => Api.get('/api/predictive/trend', days ? { days } : {}),
    maturityPath:    ()      => Api.get('/api/predictive/maturity-path'),
    highRiskAssets:  (limit) => Api.get('/api/predictive/high-risk-assets', limit ? { limit } : {}),
    threatForecast:  ()      => Api.get('/api/predictive/threat-forecast'),
  },
  architecture: {
    importDiagram: (fd) => {
      const token = localStorage.getItem('riskhub_token') || '';
      return fetch('/api/architecture/import', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: fd,
      }).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e.detail || JSON.stringify(e)))));
    },
    analyzeText: (d) => Api.post('/api/architecture/analyze-text', d),
  },
  itsm: {
    status:         ()    => Api.get('/api/itsm/status'),
    jira: {
      getConfig:    ()    => Api.get('/api/itsm/jira/config'),
      saveConfig:   (d)   => Api.put('/api/itsm/jira/config', d),
      test:         ()    => Api.post('/api/itsm/jira/test', {}),
      createTicket: (d)   => Api.post('/api/itsm/jira/ticket', d),
    },
    servicenow: {
      getConfig:    ()    => Api.get('/api/itsm/servicenow/config'),
      saveConfig:   (d)   => Api.put('/api/itsm/servicenow/config', d),
      test:         ()    => Api.post('/api/itsm/servicenow/test', {}),
    },
    slack: {
      getConfig:    ()    => Api.get('/api/itsm/slack/config'),
      saveConfig:   (d)   => Api.put('/api/itsm/slack/config', d),
      test:         ()    => Api.post('/api/itsm/slack/test', {}),
    },
    teams: {
      getConfig:    ()    => Api.get('/api/itsm/teams/config'),
      saveConfig:   (d)   => Api.put('/api/itsm/teams/config', d),
      test:         ()    => Api.post('/api/itsm/teams/test', {}),
    },
  },
  findings: {
    list:    (q)  => Api.get('/api/findings', q),
    summary: ()   => Api.get('/api/findings/summary'),
    resolve: (id) => Api.put(`/api/findings/${id}/resolve`, {}),
    import: (fd) => {
      const token = localStorage.getItem('riskhub_token') || '';
      return fetch('/api/findings/import', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: fd,
      }).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e.detail || JSON.stringify(e)))));
    },
  },
  erp: {
    getConfig:  ()  => Api.get('/api/integrations/erp/config'),
    saveConfig: (d) => Api.put('/api/integrations/erp/config', d),
    events:     ()  => Api.get('/api/integrations/erp/events'),
  },
  virustotal: {
    getConfig: () => Api.get('/api/integrations/virustotal/config'),
    saveConfig: (d) => Api.put('/api/integrations/virustotal/config', d),
    deleteConfig: () => Api.delete('/api/integrations/virustotal/config'),
    test: () => Api.post('/api/integrations/virustotal/test', {}),
  },
};
