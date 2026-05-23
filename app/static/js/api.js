/* Cliente HTTP centralizado para la API REST de RiskHub. */
const Api = {
  token() { return localStorage.getItem('riskhub_token'); },

  async req(path, opts = {}) {
    const headers = opts.headers || {};
    const tok = Api.token();
    if (tok) headers['Authorization'] = 'Bearer ' + tok;
    if (opts.body && !headers['Content-Type'] && !(opts.body instanceof FormData))
      headers['Content-Type'] = 'application/json';

    const resp = await fetch(path, { ...opts, headers });
    if (resp.status === 401) {
      localStorage.removeItem('riskhub_token');
      localStorage.removeItem('riskhub_user');
      window.location.href = '/login';
      throw new Error('No autorizado');
    }
    const ctype = resp.headers.get('content-type') || '';
    let data = null;
    if (ctype.includes('application/json')) data = await resp.json();
    else if (resp.status !== 204) data = await resp.text();
    if (!resp.ok) {
      const msg = data && data.detail ? data.detail : (data || resp.statusText);
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
    exportCsv: () => Api.download('/api/assets/export/csv', 'assets.csv'),
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
  },
  impls: {
    list: () => Api.get('/api/control-implementations/'),
    create: (d) => Api.post('/api/control-implementations/', d),
    update: (id, d) => Api.put('/api/control-implementations/' + id, d),
    del: (id) => Api.del('/api/control-implementations/' + id),
  },
  risks: {
    list: (q) => Api.get('/api/risks/', q),
    get: (id) => Api.get('/api/risks/' + id),
    create: (d) => Api.post('/api/risks/', d),
    update: (id, d) => Api.patch('/api/risks/' + id, d),
    del: (id) => Api.del('/api/risks/' + id),
    summary: () => Api.get('/api/risks/stats/summary'),
    heatmap: (mode = 'residual') => Api.get('/api/risks/heatmap/data?mode=' + mode),
  },
  users: {
    list: () => Api.get('/api/users/'),
    create: (d) => Api.post('/api/users/', d),
    update: (id, d) => Api.patch('/api/users/' + id, d),
    del: (id) => Api.del('/api/users/' + id),
  },
  reports: {
    riskRegister: () => Api.download('/api/reports/risk-register', 'risk_register.pdf'),
    soa: () => Api.download('/api/reports/soa', 'statement_of_applicability.pdf'),
    riskRegisterExcel: () => Api.download('/api/reports/risk-register-excel', 'risk_register.xlsx'),
    aiGenerate: (d) => Api.post('/api/reports/ai-generate', d),
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
};
