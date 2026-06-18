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
    if (!u || (u.role !== 'admin' && u.role !== 'superadmin')) {
      main.innerHTML = UI.sectionHeader('Log de Auditoria', 'Trazabilidad de operaciones')
        + UI.notice('Esta seccion esta restringida a administradores.', 'warn');
      return;
    }

    main.innerHTML = UI.sectionHeader(
      'Log de Auditoria',
      'Trazabilidad completa de operaciones realizadas en el sistema'
    ) + `
      <div style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:16px;">
        <button id="audit-tab-log" onclick="ViewAudit._setTab('log')"
          style="padding:8px 20px;font-size:13px;font-weight:600;border:none;background:none;cursor:pointer;
                 border-bottom:3px solid var(--brand-purple);color:var(--brand-purple);margin-bottom:-2px;">
          Log completo
        </button>
        <button id="audit-tab-approvals" onclick="ViewAudit._setTab('approvals')"
          style="padding:8px 20px;font-size:13px;font-weight:600;border:none;background:none;cursor:pointer;
                 border-bottom:3px solid transparent;color:var(--text-muted);margin-bottom:-2px;">
          Registro de aprobaciones
        </button>
      </div>
      <div id="audit-tab-content">
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
      </div>
    `;

    document.getElementById('audit-entity').onchange = () => ViewAudit._search();
    document.getElementById('audit-action').onchange = () => ViewAudit._search();

    this._page = 0;
    this._filterEntity = '';
    this._filterAction = '';
    this._filterDateFrom = '';
    this._filterDateTo = '';
    this._currentTab = 'log';
    await this._load();
  },

  _setTab(tab) {
    this._currentTab = tab;
    ['log', 'approvals'].forEach(t => {
      const btn = document.getElementById('audit-tab-' + t);
      if (btn) {
        btn.style.borderBottomColor = t === tab ? 'var(--brand-purple)' : 'transparent';
        btn.style.color = t === tab ? 'var(--brand-purple)' : 'var(--text-muted)';
      }
    });
    const content = document.getElementById('audit-tab-content');
    if (!content) return;
    if (tab === 'approvals') {
      this._loadApprovalsTab(content);
    } else {
      content.innerHTML = `
        <div class="card" style="margin-bottom:16px;">
          <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;">
            <div style="flex:1;min-width:160px;">
              <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Tipo de entidad</label>
              <select id="audit-entity" style="width:100%;">
                <option value="">Todas</option>
                <option value="risk">Riesgo</option><option value="asset">Activo</option>
                <option value="supplier">Proveedor</option><option value="control">Control</option>
                <option value="user">Usuario</option>
              </select>
            </div>
            <div style="flex:1;min-width:160px;">
              <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Accion</label>
              <select id="audit-action" style="width:100%;">
                <option value="">Todas</option>
                <option value="create">Crear</option><option value="update">Actualizar</option>
                <option value="delete">Eliminar</option><option value="login">Login</option>
              </select>
            </div>
            <div style="flex:1;min-width:130px;">
              <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Desde</label>
              <input id="audit-date-from" type="date" style="width:100%;">
            </div>
            <div style="flex:1;min-width:130px;">
              <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Hasta</label>
              <input id="audit-date-to" type="date" style="width:100%;">
            </div>
            <button class="btn btn-primary" onclick="ViewAudit._search()">Filtrar</button>
            <button class="btn" onclick="ViewAudit._reset()">Limpiar</button>
            <button class="btn" onclick="ViewAudit._exportCsv()" style="margin-left:auto;">Exportar CSV</button>
          </div>
        </div>
        <div id="audit-content"></div>`;
      document.getElementById('audit-entity').onchange = () => this._search();
      document.getElementById('audit-action').onchange = () => this._search();
      this._page = 0;
      this._load();
    }
  },

  async _loadApprovalsTab(container) {
    container.innerHTML = `
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;">
          <div style="flex:1;min-width:140px;">
            <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Tipo de entidad</label>
            <input id="app-entity" class="input" placeholder="risk, supplier, policy...">
          </div>
          <div style="flex:1;min-width:120px;">
            <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Email usuario</label>
            <input id="app-user" class="input" placeholder="usuario@empresa.com">
          </div>
          <div style="flex:1;min-width:120px;">
            <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Desde</label>
            <input id="app-from" type="date" class="input">
          </div>
          <div style="flex:1;min-width:120px;">
            <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">Hasta</label>
            <input id="app-to" type="date" class="input">
          </div>
          <button class="btn btn-primary" id="app-search">Filtrar</button>
        </div>
      </div>
      <div id="app-results"><div class="notice">Cargando...</div></div>`;
    const search = async () => {
      const params = { limit: 200 };
      const et = document.getElementById('app-entity')?.value.trim();
      const eu = document.getElementById('app-user')?.value.trim();
      const af = document.getElementById('app-from')?.value;
      const at = document.getElementById('app-to')?.value;
      if (et) params.entity_type = et;
      if (eu) params.user_email = eu;
      if (af) params.date_from = af;
      if (at) params.date_to = at;
      const wrap = document.getElementById('app-results');
      if (!wrap) return;
      try {
        const data = await Api.audit.approvals(params);
        const items = data.items || [];
        if (!items.length) {
          wrap.innerHTML = '<div class="card" style="text-align:center;padding:48px;"><h3 style="color:var(--text-muted);">Sin aprobaciones registradas</h3></div>';
          return;
        }
        wrap.innerHTML = `<div class="card" style="padding:0;overflow:hidden;">
          <div style="padding:10px 16px;border-bottom:1px solid var(--border);font-size:13px;color:var(--text-muted);">
            ${data.total} aprobacion${data.total!==1?'es':''} encontrada${data.total!==1?'s':''}
          </div>
          <div class="table-wrap"><table class="data">
            <thead><tr>
              <th style="width:140px;">Fecha</th><th style="width:160px;">Usuario</th>
              <th style="width:100px;">Accion</th><th style="width:100px;">Tipo</th>
              <th style="width:70px;">ID</th><th>Detalle</th>
            </tr></thead>
            <tbody>${items.map(e => {
              const ts = new Date(e.timestamp).toLocaleString('es-ES', {
                day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit',
              });
              const detail = e.detail && Object.keys(e.detail).length
                ? Object.entries(e.detail).slice(0,4).map(([k,v]) => `${UI.esc(k)}: ${UI.esc(String(v))}`).join(' · ')
                : '—';
              return `<tr>
                <td style="font-size:12px;">${ts}</td>
                <td><div style="font-size:13px;">${UI.esc(e.user_name||'—')}</div>
                    <div style="font-size:11px;color:var(--text-muted);">${UI.esc(e.user_email||'')}</div></td>
                <td><span style="font-size:11px;background:#D1FAE5;color:#065F46;padding:2px 8px;border-radius:999px;font-weight:600;">${UI.esc(e.action)}</span></td>
                <td style="font-size:12px;">${UI.esc(e.entity_type)}</td>
                <td style="font-family:monospace;font-size:11px;color:var(--text-muted);">${UI.esc(e.entity_id||'—')}</td>
                <td style="font-size:11px;color:var(--text-muted);">${detail}</td>
              </tr>`;
            }).join('')}</tbody>
          </table></div>
        </div>`;
      } catch (err) {
        if (document.getElementById('app-results'))
          document.getElementById('app-results').innerHTML = UI.notice('Error: ' + UI.esc(err.message), 'warn');
      }
    };
    document.getElementById('app-search').onclick = search;
    await search();
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

  // ---- Registro de aprobaciones (accesible desde otros modulos) ----

  async showApprovals(opts = {}) {
    const params = { limit: 200 };
    if (opts.entity_type) params.entity_type = opts.entity_type;
    if (opts.date_from) params.date_from = opts.date_from;
    if (opts.date_to) params.date_to = opts.date_to;
    try {
      const data = await Api.audit.approvals(params);
      const items = data.items || [];
      const rows = items.length
        ? items.map(e => {
            const ts = new Date(e.timestamp).toLocaleString('es-ES', {
              day: '2-digit', month: '2-digit', year: 'numeric',
              hour: '2-digit', minute: '2-digit',
            });
            const detail = e.detail && Object.keys(e.detail).length
              ? Object.entries(e.detail).map(([k, v]) => `${UI.esc(k)}: ${UI.esc(String(v))}`).join(' · ')
              : '—';
            return `<tr>
              <td style="font-size:12px;">${ts}</td>
              <td><div style="font-size:13px;">${UI.esc(e.user_name||'—')}</div>
                  <div style="font-size:11px;color:var(--text-muted);">${UI.esc(e.user_email||'')}</div></td>
              <td><span style="font-size:11px;background:#D1FAE5;color:#065F46;padding:2px 7px;border-radius:999px;font-weight:600;">${UI.esc(e.action)}</span></td>
              <td style="font-size:12px;">${UI.esc(e.entity_type)}</td>
              <td style="font-family:monospace;font-size:11px;color:var(--text-muted);">${UI.esc(e.entity_id||'—')}</td>
              <td style="font-size:11px;color:var(--text-muted);">${detail}</td>
            </tr>`;
          }).join('')
        : `<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-muted);">Sin aprobaciones registradas.</td></tr>`;

      UI.modal('Registro de aprobaciones', `
        <div class="span2" style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;">
          <input id="app-from" type="date" class="input" placeholder="Desde" style="width:140px;" ${opts.date_from?`value="${opts.date_from}"`:''}>
          <input id="app-to" type="date" class="input" placeholder="Hasta" style="width:140px;" ${opts.date_to?`value="${opts.date_to}"`:''}>
          <button class="btn btn-sm btn-primary" id="app-filter-btn">Filtrar</button>
          <span style="margin-left:auto;font-size:12px;color:var(--text-muted);align-self:center;">${data.total} registro${data.total!==1?'s':''}</span>
        </div>
        <div class="span2" style="overflow:auto;max-height:420px;">
          <table class="data">
            <thead><tr>
              <th>Fecha</th><th>Usuario</th><th>Accion</th><th>Tipo</th><th>ID</th><th>Detalle</th>
            </tr></thead>
            <tbody id="approval-tbody">${rows}</tbody>
          </table>
        </div>
      `, { actions: '<button class="btn btn-primary" id="m-close-app">Cerrar</button>', width: '820px' });

      document.getElementById('m-close-app').onclick = UI.closeModal;
      document.getElementById('app-filter-btn').onclick = () => {
        this.showApprovals({
          entity_type: opts.entity_type,
          date_from: document.getElementById('app-from')?.value || undefined,
          date_to: document.getElementById('app-to')?.value || undefined,
        });
      };
    } catch (e) { UI.toast('Error al cargar aprobaciones: ' + e.message, 'error'); }
  },

  // Muestra el historial de cambios de una entidad en un modal
  async showEntityHistory(entityType, entityId, label) {
    try {
      const items = await Api.audit.history(entityType, String(entityId));
      const rows = items.length
        ? items.map(e => {
            const ts = new Date(e.timestamp).toLocaleString('es-ES', {
              day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
            });
            const detail = e.detail && Object.keys(e.detail).length
              ? Object.entries(e.detail).map(([k, v]) => `${UI.esc(k)}: ${UI.esc(String(v))}`).join(' · ')
              : '—';
            const isApproval = e.action.includes('approv');
            const badgeStyle = isApproval
              ? 'background:#D1FAE5;color:#065F46'
              : e.action === 'create'
              ? 'background:#EDE9FE;color:#5B21B6'
              : e.action === 'delete'
              ? 'background:#FEE2E2;color:#991B1B'
              : 'background:#DBEAFE;color:#1E40AF';
            return `<tr>
              <td style="font-size:12px;">${ts}</td>
              <td><div style="font-size:13px;">${UI.esc(e.user_name||'—')}</div>
                  <div style="font-size:11px;color:var(--text-muted);">${UI.esc(e.user_email||'')}</div></td>
              <td><span style="font-size:11px;padding:2px 7px;border-radius:999px;font-weight:600;${badgeStyle}">${UI.esc(e.action)}</span></td>
              <td style="font-size:11px;color:var(--text-muted);">${detail}</td>
            </tr>`;
          }).join('')
        : `<tr><td colspan="4" style="text-align:center;padding:24px;color:var(--text-muted);">Sin historial registrado.</td></tr>`;

      UI.modal(`Historial: ${UI.esc(label||entityId)}`, `
        <div class="span2" style="overflow:auto;max-height:420px;">
          <table class="data">
            <thead><tr><th>Fecha</th><th>Usuario</th><th>Accion</th><th>Detalle</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      `, { actions: '<button class="btn btn-primary" id="m-close-hist">Cerrar</button>' });
      document.getElementById('m-close-hist').onclick = UI.closeModal;
    } catch (e) { UI.toast('Error al cargar historial: ' + e.message, 'error'); }
  },
};
