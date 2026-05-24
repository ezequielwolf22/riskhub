/* Vista Log de Auditoria — solo administradores. */
const ViewAudit = {
  _page: 0,
  _limit: 100,
  _filterEntity: '',
  _filterAction: '',
  _filterDateFrom: '',
  _filterDateTo: '',
  _total: 0,

  async render(main) {
    const u = Auth.user();
    if (!u || u.role !== 'admin') {
      main.innerHTML = UI.sectionHeader('Log de Auditoria', 'Trazabilidad de operaciones')
        + UI.notice('Esta seccion esta restringida a administradores.', 'warn');
      return;
    }

    main.innerHTML = UI.sectionHeader(
      'Log de Auditoria',
      'Trazabilidad completa de operaciones realizadas en el sistema'
    ) + `
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;">
          <div style="flex:1;min-width:160px;">
            <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">
              Tipo de entidad
            </label>
            <select id="audit-entity" style="width:100%;">
              <option value="">Todas</option>
              <option value="risk">Riesgo</option>
              <option value="asset">Activo</option>
              <option value="control">Control</option>
              <option value="control_impl">Control impl.</option>
              <option value="user">Usuario</option>
              <option value="threat">Amenaza</option>
              <option value="vulnerability">Vulnerabilidad</option>
              <option value="context">Contexto</option>
              <option value="alert_rule">Regla de alerta</option>
              <option value="email_settings">Config. SMTP</option>
            </select>
          </div>
          <div style="flex:1;min-width:160px;">
            <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">
              Accion
            </label>
            <select id="audit-action" style="width:100%;">
              <option value="">Todas</option>
              <option value="create">Crear</option>
              <option value="update">Actualizar</option>
              <option value="delete">Eliminar</option>
              <option value="login">Inicio de sesion</option>
            </select>
          </div>
          <div style="flex:1;min-width:130px;">
            <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">
              Desde
            </label>
            <input id="audit-date-from" type="date" style="width:100%;">
          </div>
          <div style="flex:1;min-width:130px;">
            <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">
              Hasta
            </label>
            <input id="audit-date-to" type="date" style="width:100%;">
          </div>
          <button class="btn btn-primary" onclick="ViewAudit._search()">Filtrar</button>
          <button class="btn" onclick="ViewAudit._reset()">Limpiar</button>
          <button class="btn" onclick="ViewAudit._exportCsv()"
            style="margin-left:auto;" title="Descargar log completo (filtrado) en CSV">
            Exportar CSV
          </button>
        </div>
      </div>
      <div id="audit-content"></div>
    `;

    document.getElementById('audit-entity').onchange = () => ViewAudit._search();
    document.getElementById('audit-action').onchange = () => ViewAudit._search();

    this._page = 0;
    this._filterEntity = '';
    this._filterAction = '';
    this._filterDateFrom = '';
    this._filterDateTo = '';
    await this._load();
  },

  _reset() {
    document.getElementById('audit-entity').value = '';
    document.getElementById('audit-action').value = '';
    document.getElementById('audit-date-from').value = '';
    document.getElementById('audit-date-to').value = '';
    this._filterEntity = '';
    this._filterAction = '';
    this._filterDateFrom = '';
    this._filterDateTo = '';
    this._page = 0;
    this._load();
  },

  _search() {
    this._filterEntity = document.getElementById('audit-entity').value;
    this._filterAction = document.getElementById('audit-action').value;
    this._filterDateFrom = document.getElementById('audit-date-from').value;
    this._filterDateTo = document.getElementById('audit-date-to').value;
    this._page = 0;
    this._load();
  },

  async _load() {
    const c = document.getElementById('audit-content');
    c.innerHTML = '<div class="notice">Cargando...</div>';

    const params = {
      skip: this._page * this._limit,
      limit: this._limit,
    };
    if (this._filterEntity) params.entity_type = this._filterEntity;
    if (this._filterAction) params.action = this._filterAction;
    if (this._filterDateFrom) params.date_from = this._filterDateFrom;
    if (this._filterDateTo) params.date_to = this._filterDateTo;

    try {
      const data = await Api.audit.list(params);
      this._total = data.total;
      this._render(c, data);
    } catch (e) {
      c.innerHTML = UI.notice('Error al cargar el log: ' + UI.esc(e.message), 'warn');
    }
  },

  async _exportCsv() {
    try {
      const q = {};
      if (this._filterEntity) q.entity_type = this._filterEntity;
      if (this._filterAction) q.action = this._filterAction;
      if (this._filterDateFrom) q.date_from = this._filterDateFrom;
      if (this._filterDateTo) q.date_to = this._filterDateTo;
      const url = '/api/audit/export/csv' + (Object.keys(q).length ? '?' + new URLSearchParams(q) : '');
      const tok = localStorage.getItem('riskhub_token');
      const r = await fetch(url, { headers: { Authorization: 'Bearer ' + tok } });
      if (!r.ok) throw new Error('Error al exportar');
      const blob = await r.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'audit_log.csv';
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  _render(container, data) {
    const items = data.items || [];
    const totalPages = Math.ceil(this._total / this._limit);
    const currentPage = this._page + 1;

    const actionBadge = (a) => {
      const colors = {
        create: 'background:#D1FAE5;color:#065F46',
        update: 'background:#DBEAFE;color:#1E40AF',
        delete: 'background:#FEE2E2;color:#991B1B',
        login: 'background:#EDE9FE;color:#5B21B6',
      };
      const labels = {
        create: 'Crear',
        update: 'Actualizar',
        delete: 'Eliminar',
        login: 'Login',
      };
      const style = colors[a] || 'background:var(--bg-3);color:var(--text-muted)';
      return `<span class="badge badge-muted" style="${style};font-size:11px;">${UI.esc(labels[a] || a)}</span>`;
    };

    const entityLabel = (t) => ({
      risk: 'Riesgo',
      asset: 'Activo',
      control: 'Control',
      control_impl: 'Control impl.',
      user: 'Usuario',
      threat: 'Amenaza',
      vulnerability: 'Vulnerabilidad',
      context: 'Contexto',
      alert_rule: 'Regla alerta',
      email_settings: 'Config. SMTP',
    })[t] || t;

    if (items.length === 0) {
      container.innerHTML = `
        <div class="card" style="text-align:center;padding:48px 24px;">
          <h3 style="color:var(--text-muted);">No hay entradas en el log</h3>
          <p style="color:var(--text-subtle);font-size:13px;margin-top:8px;">
            Las operaciones de creacion, modificacion y eliminacion se registran automaticamente.
          </p>
        </div>`;
      return;
    }

    container.innerHTML = `
      <div class="card" style="padding:0;overflow:hidden;">
        <div style="padding:12px 16px;border-bottom:1px solid var(--border);
                    display:flex;justify-content:space-between;align-items:center;">
          <span style="font-size:13px;color:var(--text-muted);">
            ${this._total} entrada${this._total !== 1 ? 's' : ''} encontrada${this._total !== 1 ? 's' : ''}
          </span>
          <div style="display:flex;gap:8px;align-items:center;">
            <span style="font-size:12px;color:var(--text-muted);">
              Pagina ${currentPage} de ${Math.max(1, totalPages)}
            </span>
            <button class="btn btn-sm" ${this._page === 0 ? 'disabled' : ''}
                    onclick="ViewAudit._prevPage()">Anterior</button>
            <button class="btn btn-sm" ${currentPage >= totalPages ? 'disabled' : ''}
                    onclick="ViewAudit._nextPage()">Siguiente</button>
          </div>
        </div>
        <div class="table-wrap">
          <table class="data">
            <thead>
              <tr>
                <th style="width:150px;">Fecha y hora</th>
                <th style="width:140px;">Usuario</th>
                <th style="width:90px;">Accion</th>
                <th style="width:100px;">Entidad</th>
                <th style="width:70px;">ID</th>
                <th>Detalle</th>
              </tr>
            </thead>
            <tbody>
              ${items.map(e => {
                const ts = new Date(e.timestamp).toLocaleString('es-ES', {
                  day: '2-digit', month: '2-digit', year: 'numeric',
                  hour: '2-digit', minute: '2-digit', second: '2-digit',
                });
                const detail = e.detail && Object.keys(e.detail).length > 0
                  ? Object.entries(e.detail)
                      .map(([k, v]) => `<span style="color:var(--text-muted);">${UI.esc(k)}:</span> ${UI.esc(String(v))}`)
                      .join(' &nbsp;·&nbsp; ')
                  : '<span style="color:var(--text-subtle);">—</span>';

                return `
                  <tr>
                    <td style="font-family:var(--font-mono);font-size:11px;">${ts}</td>
                    <td>
                      <div style="font-size:13px;">${UI.esc(e.user_name || '—')}</div>
                      <div style="font-size:11px;color:var(--text-muted);">${UI.esc(e.user_email || '')}</div>
                    </td>
                    <td>${actionBadge(e.action)}</td>
                    <td style="font-size:12px;">${UI.esc(entityLabel(e.entity_type))}</td>
                    <td style="font-family:var(--font-mono);font-size:11px;color:var(--text-muted);">
                      ${e.entity_id ? UI.esc(e.entity_id) : '—'}
                    </td>
                    <td style="font-size:12px;">${detail}</td>
                  </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>
      </div>`;
  },

  _prevPage() {
    if (this._page > 0) { this._page--; this._load(); }
  },

  _nextPage() {
    const totalPages = Math.ceil(this._total / this._limit);
    if (this._page + 1 < totalPages) { this._page++; this._load(); }
  },
};
