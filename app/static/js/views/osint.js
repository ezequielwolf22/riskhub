/* Vista OSINT — Inteligencia de fuentes abiertas. */
const ViewOsint = {

  _scans: [],
  _findings: [],
  _identifiers: [],
  _stats: null,
  _tab: 'findings',
  _pollInterval: null,
  _filterRisk: '',
  _filterSource: '',
  _filterStatus: '',
  _filterType: '',
  _searchText: '',
  _bulkMode: false,
  _entraidPanel: false,
  _entraidData: null,

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      'OSINT',
      'Inteligencia de fuentes abiertas: emails, dominios, URLs, usernames, IPs'
    ) + `
      <!-- ── SCAN LAUNCHER (siempre visible) ── -->
      <div id="osint-launcher" class="card" style="margin-bottom:16px;border-left:4px solid var(--brand-purple);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <h3 style="margin:0;font-size:15px;">Lanzar escaneo</h3>
          <div style="display:flex;gap:8px;">
            <button class="btn btn-sm" id="btn-bulk-toggle"
              onclick="ViewOsint._toggleBulk()"
              style="font-size:12px;">
              Modo masivo
            </button>
            <button class="btn btn-sm" id="btn-entraid-toggle"
              onclick="ViewOsint._toggleEntraID()"
              style="font-size:12px;background:var(--bg-muted);">
              Importar de Entra ID
            </button>
          </div>
        </div>

        <!-- Modo individual -->
        <div id="scan-single">
          <div style="display:grid;grid-template-columns:160px 1fr auto;gap:10px;align-items:end;">
            <div>
              <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Tipo</label>
              <select id="scan-type" onchange="ViewOsint._updatePlaceholder()">
                <option value="email">Email</option>
                <option value="domain">Dominio</option>
                <option value="ip">IP</option>
                <option value="url">URL</option>
                <option value="username">Username (GitHub)</option>
              </select>
            </div>
            <div>
              <label id="target-label" style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">
                Email objetivo
              </label>
              <input id="scan-target" type="text" placeholder="usuario@empresa.com"
                onkeydown="if(event.key==='Enter') ViewOsint._startScan()">
            </div>
            <button class="btn btn-primary" onclick="ViewOsint._startScan()" style="height:38px;min-width:100px;">
              Escanear
            </button>
          </div>
        </div>

        <!-- Modo masivo (oculto por defecto) -->
        <div id="scan-bulk" style="display:none;">
          <div style="display:grid;grid-template-columns:160px 1fr auto;gap:10px;align-items:start;">
            <div>
              <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Tipo</label>
              <select id="bulk-type">
                <option value="email">Email</option>
                <option value="domain">Dominio</option>
                <option value="ip">IP</option>
                <option value="url">URL</option>
                <option value="username">Username</option>
              </select>
            </div>
            <div>
              <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">
                Objetivos (uno por linea, maximo 50)
              </label>
              <textarea id="bulk-targets" rows="4" style="width:100%;font-family:monospace;font-size:12px;"
                placeholder="usuario1@empresa.com&#10;usuario2@empresa.com&#10;dominio.com&#10;..."></textarea>
            </div>
            <button class="btn btn-primary" onclick="ViewOsint._startBulkScan()" style="margin-top:20px;min-width:100px;">
              Escanear todos
            </button>
          </div>
          <div style="font-size:12px;color:var(--text-muted);margin-top:6px;">
            Los escaneos se ejecutan en segundo plano. Podras ver el progreso en la pestana Escaneos.
          </div>
        </div>

        <!-- Panel Entra ID (oculto por defecto) -->
        <div id="entraid-panel" style="display:none;border-top:1px solid var(--border-color);margin-top:14px;padding-top:14px;">
          <h4 style="margin:0 0 12px;font-size:14px;color:var(--brand-purple);">
            Importar desde Microsoft Entra ID (Azure AD)
          </h4>
          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:10px;">
            <div>
              <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Tenant ID</label>
              <input id="eid-tenant" type="text" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx">
            </div>
            <div>
              <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Client ID</label>
              <input id="eid-client" type="text" placeholder="App registration client_id">
            </div>
            <div>
              <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Client Secret</label>
              <input id="eid-secret" type="password" placeholder="Client secret value">
            </div>
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            <button class="btn btn-sm" onclick="ViewOsint._entraidTest()">Probar conexion</button>
            <button class="btn btn-sm" onclick="ViewOsint._entraidPreview()">Ver objetivos</button>
            <label style="font-size:12px;display:flex;align-items:center;gap:4px;">
              <input type="checkbox" id="eid-users" checked> Escanear usuarios
            </label>
            <label style="font-size:12px;display:flex;align-items:center;gap:4px;">
              <input type="checkbox" id="eid-domains" checked> Escanear dominios
            </label>
            <input type="number" id="eid-limit" value="50" min="1" max="200"
              style="width:70px;font-size:12px;" title="Limite de usuarios">
            <span style="font-size:11px;color:var(--text-muted);">usuarios max</span>
          </div>
          <div id="entraid-status" style="margin-top:10px;font-size:13px;"></div>
          <div id="entraid-preview" style="margin-top:10px;"></div>
        </div>
      </div>

      <!-- ── TABS ── -->
      <div id="osint-tabs" style="display:flex;gap:4px;border-bottom:2px solid var(--border-color);margin-bottom:16px;">
        ${['findings','scans','identifiers','stats'].map(t => `
          <button class="osint-tab" data-tab="${t}" onclick="ViewOsint._tab='${t}';ViewOsint._renderTab();"
            style="padding:8px 18px;border:none;border-bottom:2px solid transparent;background:none;
                   cursor:pointer;font-size:14px;margin-bottom:-2px;color:var(--text-muted);">
            ${{findings:'Hallazgos',scans:'Escaneos',identifiers:'Objetivos',stats:'Estadisticas'}[t]}
          </button>`).join('')}
      </div>
      <div id="osint-content"></div>

      <!-- ── DRAWER ── -->
      <div id="osint-drawer" style="display:none;position:fixed;right:0;top:0;width:520px;height:100vh;
           background:var(--card-bg);border-left:1px solid var(--border-color);overflow-y:auto;
           z-index:9999;box-shadow:-4px 0 24px rgba(0,0,0,.18);">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:16px 20px;
                    border-bottom:1px solid var(--border-color);background:var(--brand-purple);color:white;
                    position:sticky;top:0;z-index:1;">
          <h3 id="drawer-title" style="margin:0;font-size:16px;">Detalle</h3>
          <button onclick="ViewOsint._closeDrawer()"
            style="background:none;border:none;color:white;font-size:22px;cursor:pointer;padding:0 4px;line-height:1;">
            &times;
          </button>
        </div>
        <div id="drawer-content" style="padding:20px;"></div>
      </div>
    `;

    await this._load();
    this._renderTab();
    this._startPolling();
  },

  async _load() {
    try {
      const [scans, findings, identifiers, stats] = await Promise.all([
        Api.get('/api/v1/osint/scans?limit=200'),
        Api.get('/api/v1/osint/findings?limit=200'),
        Api.get('/api/v1/osint/identifiers?limit=200'),
        Api.get('/api/v1/osint/stats'),
      ]);
      this._scans = scans.items || [];
      this._findings = findings.items || [];
      this._identifiers = identifiers.items || [];
      this._stats = stats;
    } catch (e) {
      UI.message('Error cargando OSINT: ' + e.message, 'error');
    }
  },

  _startPolling() {
    clearInterval(this._pollInterval);
    this._pollInterval = setInterval(async () => {
      const pending = this._scans.filter(s => s.status === 'in_progress' || s.status === 'pending');
      if (pending.length) {
        await this._load();
        this._renderTab();
      }
    }, 3000);
  },

  _renderTab() {
    document.querySelectorAll('.osint-tab').forEach(b => {
      const active = b.dataset.tab === this._tab;
      b.style.color = active ? 'var(--brand-purple)' : 'var(--text-muted)';
      b.style.borderBottomColor = active ? 'var(--brand-purple)' : 'transparent';
      b.style.fontWeight = active ? '600' : '400';
    });
    const c = document.getElementById('osint-content');
    if (!c) return;
    if (this._tab === 'scans') this._renderScans(c);
    else if (this._tab === 'findings') this._renderFindings(c);
    else if (this._tab === 'identifiers') this._renderIdentifiers(c);
    else this._renderStats(c);
  },

  _toggleBulk() {
    this._bulkMode = !this._bulkMode;
    document.getElementById('scan-single').style.display = this._bulkMode ? 'none' : 'block';
    document.getElementById('scan-bulk').style.display = this._bulkMode ? 'block' : 'none';
    document.getElementById('btn-bulk-toggle').style.background =
      this._bulkMode ? 'var(--brand-purple)' : '';
    document.getElementById('btn-bulk-toggle').style.color =
      this._bulkMode ? 'white' : '';
  },

  _toggleEntraID() {
    this._entraidPanel = !this._entraidPanel;
    document.getElementById('entraid-panel').style.display = this._entraidPanel ? 'block' : 'none';
    document.getElementById('btn-entraid-toggle').style.background =
      this._entraidPanel ? 'var(--brand-purple)' : 'var(--bg-muted)';
    document.getElementById('btn-entraid-toggle').style.color =
      this._entraidPanel ? 'white' : '';
  },

  _updatePlaceholder() {
    const labels = {
      email: 'Email objetivo',
      domain: 'Dominio (ej: empresa.com)',
      url: 'URL completa (ej: https://...)',
      username: 'Username de GitHub',
      ip: 'Direccion IP (ej: 8.8.8.8)'
    };
    const placeholders = {
      email: 'usuario@empresa.com',
      domain: 'empresa.com',
      url: 'https://example.com',
      username: 'octocat',
      ip: '8.8.8.8'
    };
    const type = document.getElementById('scan-type')?.value;
    if (type) {
      document.getElementById('target-label').textContent = labels[type] || 'Objetivo';
      document.getElementById('scan-target').placeholder = placeholders[type] || '';
    }
  },

  // ── ESCANEOS ──────────────────────────────────────────────────────────────

  _renderScans(c) {
    const pending = this._scans.filter(s => s.status === 'in_progress' || s.status === 'pending');
    const filtered = this._scans.filter(s => !this._filterStatus || s.status === this._filterStatus);

    c.innerHTML = `
      ${pending.length ? `
      <div style="background:var(--warning-soft);border:1px solid var(--warning);border-radius:8px;
                  padding:10px 14px;margin-bottom:12px;font-size:13px;color:var(--warning);">
        ${pending.length} escaneo(s) en progreso — actualizando automaticamente...
      </div>` : ''}

      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <h3 style="margin:0;">Historial (${this._scans.length})</h3>
          <select onchange="ViewOsint._filterStatus=this.value;ViewOsint._renderTab();" style="font-size:12px;">
            <option value="">Todos los estados</option>
            <option value="completed">Completados</option>
            <option value="in_progress">En progreso</option>
            <option value="pending">Pendientes</option>
            <option value="failed">Fallidos</option>
          </select>
        </div>
        ${filtered.length === 0 ? `
          <p style="color:var(--text-muted);margin:0;">Sin escaneos todavia. Usa el lanzador de arriba.</p>
        ` : `
          <div style="overflow-x:auto;">
            <table class="data">
              <thead><tr>
                <th>Tipo</th><th>Objetivo</th><th>Estado</th>
                <th>Hallazgos</th><th>Score</th><th>Fecha</th><th></th>
              </tr></thead>
              <tbody>
                ${filtered.map(s => `
                <tr style="cursor:pointer;" onclick="ViewOsint._openScanDrawer(${s.id})">
                  <td>${this._typeBadge(s.scan_type)}</td>
                  <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                    <code style="font-size:12px;">${UI.esc(s.target)}</code>
                  </td>
                  <td>${this._statusBadge(s.status)}</td>
                  <td><strong>${s.findings_count || 0}</strong></td>
                  <td><span style="font-weight:600;color:${this._scoreColor(s.risk_score)};">
                    ${(s.risk_score || 0).toFixed(1)}
                  </span></td>
                  <td style="font-size:12px;color:var(--text-muted);">
                    ${new Date(s.started_at).toLocaleString('es-ES')}
                  </td>
                  <td style="text-align:right;">
                    <button class="btn btn-xs" onclick="event.stopPropagation();ViewOsint._openScanDrawer(${s.id})">
                      Ver
                    </button>
                  </td>
                </tr>`).join('')}
              </tbody>
            </table>
          </div>
        `}
      </div>
    `;
  },

  // ── HALLAZGOS ─────────────────────────────────────────────────────────────

  _renderFindings(c) {
    const u = Auth.user();
    const canEdit = u && (u.role === 'admin' || u.role === 'analyst' || u.role === 'superadmin');

    let filtered = this._findings;
    if (this._filterRisk) filtered = filtered.filter(f => f.risk_level === this._filterRisk);
    if (this._filterSource) filtered = filtered.filter(f => f.source === this._filterSource);
    if (this._filterStatus === 'pending') filtered = filtered.filter(f => !f.is_remediated);
    if (this._filterStatus === 'remediated') filtered = filtered.filter(f => f.is_remediated);
    if (this._searchText) {
      const q = this._searchText.toLowerCase();
      filtered = filtered.filter(f =>
        f.title.toLowerCase().includes(q) ||
        (f.description || '').toLowerCase().includes(q)
      );
    }

    const sources = [...new Set(this._findings.map(f => f.source))];
    const pending = this._findings.filter(f => !f.is_remediated).length;
    const critical = this._findings.filter(f => f.risk_level === 'critical' && !f.is_remediated).length;

    c.innerHTML = `
      <!-- Alertas de hallazgos criticos -->
      ${critical > 0 ? `
      <div style="background:#FEF2F2;border-left:4px solid var(--danger);border-radius:6px;
                  padding:10px 14px;margin-bottom:12px;font-size:13px;color:var(--danger);">
        <strong>${critical} hallazgo(s) CRITICOS sin remediar.</strong> Requieren atencion inmediata.
      </div>` : pending > 0 ? `
      <div style="background:var(--warning-soft);border-left:4px solid var(--warning);border-radius:6px;
                  padding:10px 14px;margin-bottom:12px;font-size:13px;color:var(--warning-dark,#92400E);">
        <strong>${pending} hallazgo(s) pendientes de remediar.</strong>
      </div>` : this._findings.length > 0 ? `
      <div style="background:var(--success-soft);border-left:4px solid var(--success);border-radius:6px;
                  padding:10px 14px;margin-bottom:12px;font-size:13px;color:var(--success);">
        Todos los hallazgos estan remediados.
      </div>` : ''}

      <!-- Filtros -->
      <div class="card" style="margin-bottom:12px;padding:12px 16px;">
        <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;">
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
            <input type="text" id="finding-search" placeholder="Buscar..." style="width:180px;"
              value="${UI.esc(this._searchText)}"
              oninput="ViewOsint._searchText=this.value;ViewOsint._renderFindings(document.getElementById('osint-content'));">
            <select onchange="ViewOsint._filterRisk=this.value;ViewOsint._renderFindings(document.getElementById('osint-content'));"
              style="font-size:12px;">
              <option value="">Todo nivel</option>
              ${['critical','high','medium','low','info'].map(r =>
                `<option value="${r}" ${this._filterRisk===r?'selected':''}>${r.toUpperCase()}</option>`
              ).join('')}
            </select>
            <select onchange="ViewOsint._filterSource=this.value;ViewOsint._renderFindings(document.getElementById('osint-content'));"
              style="font-size:12px;">
              <option value="">Toda fuente</option>
              ${sources.map(s => `<option value="${s}" ${this._filterSource===s?'selected':''}>${s}</option>`).join('')}
            </select>
            <select onchange="ViewOsint._filterStatus=this.value;ViewOsint._renderFindings(document.getElementById('osint-content'));"
              style="font-size:12px;">
              <option value="">Todos</option>
              <option value="pending" ${this._filterStatus==='pending'?'selected':''}>Pendientes</option>
              <option value="remediated" ${this._filterStatus==='remediated'?'selected':''}>Remediados</option>
            </select>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            <span style="font-size:12px;color:var(--text-muted);">${filtered.length} resultados</span>
            <button class="btn btn-sm" onclick="ViewOsint._exportCSV()">Exportar CSV</button>
          </div>
        </div>
      </div>

      <div class="card">
        ${filtered.length === 0 ? `
          <p style="color:var(--text-muted);margin:0;">
            ${this._findings.length === 0
              ? 'Sin hallazgos todavia. Lanza un escaneo desde el panel superior.'
              : 'Sin hallazgos con los filtros actuales.'}
          </p>
        ` : `
          <div style="overflow-x:auto;">
            <table class="data">
              <thead><tr>
                <th>Nivel</th><th>Titulo</th><th>Fuente</th><th>Score</th><th>Estado</th><th></th>
              </tr></thead>
              <tbody>
                ${filtered.map(f => `
                <tr style="cursor:pointer;${f.is_remediated?'opacity:0.55;':''}"
                    onclick="ViewOsint._openFindingDrawer(${f.id})">
                  <td>${this._riskBadge(f.risk_level)}</td>
                  <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
                      title="${UI.esc(f.title)}">
                    ${UI.esc(f.title)}
                  </td>
                  <td><span class="badge badge-muted" style="font-size:11px;">${UI.esc(f.source)}</span></td>
                  <td><strong style="color:${this._scoreColor(f.risk_score)};">${f.risk_score.toFixed(1)}</strong></td>
                  <td>
                    <span style="padding:2px 8px;border-radius:4px;font-size:11px;
                      ${f.is_remediated
                        ? 'background:var(--success-soft);color:var(--success);'
                        : 'background:var(--danger-soft);color:var(--danger);'}">
                      ${f.is_remediated ? 'Remediado' : 'Pendiente'}
                    </span>
                  </td>
                  <td style="text-align:right;white-space:nowrap;">
                    ${canEdit ? `
                      <button class="btn btn-xs"
                        onclick="event.stopPropagation();ViewOsint._createIncident(${f.id})"
                        title="Crear incidente de seguridad"
                        style="margin-right:4px;">
                        + Incidente
                      </button>
                      ${f.is_remediated
                        ? `<button class="btn btn-xs" onclick="event.stopPropagation();ViewOsint._unremediate(${f.id})">Desmarcar</button>`
                        : `<button class="btn btn-xs btn-primary" onclick="event.stopPropagation();ViewOsint._remediate(${f.id})">Resolver</button>`
                      }
                    ` : ''}
                  </td>
                </tr>`).join('')}
              </tbody>
            </table>
          </div>
        `}
      </div>
    `;
  },

  // ── IDENTIFICADORES ───────────────────────────────────────────────────────

  _renderIdentifiers(c) {
    const types = [...new Set(this._identifiers.map(i => i.identifier_type))];

    c.innerHTML = `
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <h3 style="margin:0;">Objetivos monitorizados (${this._identifiers.length})</h3>
          ${types.length > 1 ? `
          <select onchange="ViewOsint._filterType=this.value;ViewOsint._renderIdentifiers(document.getElementById('osint-content'));"
            style="font-size:12px;">
            <option value="">Todos los tipos</option>
            ${types.map(t => `<option value="${t}" ${this._filterType===t?'selected':''}>${t}</option>`).join('')}
          </select>` : ''}
        </div>
        ${this._identifiers.length === 0 ? `
          <p style="color:var(--text-muted);margin:0;">
            Sin objetivos todavia. Se registran automaticamente al escanear.
          </p>
        ` : `
          <div style="overflow-x:auto;">
            <table class="data">
              <thead><tr>
                <th>Tipo</th><th>Valor</th><th>Ultimo escaneo</th><th>Riesgo</th><th style="width:140px;"></th>
              </tr></thead>
              <tbody>
                ${this._identifiers
                  .filter(i => !this._filterType || i.identifier_type === this._filterType)
                  .map(i => `
                  <tr>
                    <td>${this._typeBadge(i.identifier_type)}</td>
                    <td><code style="font-size:12px;">${UI.esc(i.value)}</code></td>
                    <td style="font-size:12px;color:var(--text-muted);">
                      ${i.last_scanned_at ? new Date(i.last_scanned_at).toLocaleString('es-ES') : 'Nunca'}
                    </td>
                    <td>${this._riskBadge(i.risk_level)}</td>
                    <td style="text-align:right;white-space:nowrap;">
                      <button class="btn btn-xs"
                        onclick="ViewOsint._rescan('${i.identifier_type}','${UI.esc(i.value)}')">
                        Re-escanear
                      </button>
                      <button class="btn btn-xs" style="margin-left:4px;color:var(--danger);"
                        onclick="ViewOsint._deleteIdentifier(${i.id})">
                        Eliminar
                      </button>
                    </td>
                  </tr>`).join('')}
              </tbody>
            </table>
          </div>
        `}
      </div>
    `;
  },

  // ── ESTADISTICAS ──────────────────────────────────────────────────────────

  _renderStats(c) {
    const s = this._stats || {};
    const rbl = s.risk_by_level || {};
    const sbt = s.scans_by_type || {};
    const fbs = s.findings_by_source || {};
    const total = s.findings_total || 1;

    const bar = (val, max, color) => {
      const pct = max ? Math.round((val / max) * 100) : 0;
      return `<div style="display:flex;align-items:center;gap:8px;">
        <div style="flex:1;height:8px;background:var(--border-color);border-radius:4px;overflow:hidden;">
          <div style="width:${pct}%;height:100%;background:${color};border-radius:4px;transition:width .3s;"></div>
        </div>
        <span style="font-size:12px;color:var(--text-muted);width:28px;text-align:right;">${val}</span>
      </div>`;
    };

    c.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:16px;">
        ${[
          ['Escaneos', s.scans_total||0, 'var(--brand-purple)'],
          ['Hallazgos', s.findings_total||0, 'var(--danger)'],
          ['Por remediar', s.findings_pending||0, 'var(--warning)'],
          ['Remediados', s.findings_remediated||0, 'var(--success)'],
          ['Tasa remediacion', (s.remediation_rate||0)+'%', 'var(--info)'],
          ['Score promedio', (s.avg_risk_score||0).toFixed(1), this._scoreColor(s.avg_risk_score||0)]
        ].map(([label, val, color]) => `
          <div class="card" style="margin:0;text-align:center;padding:16px 12px;">
            <div style="font-size:26px;font-weight:bold;color:${color};">${val}</div>
            <div style="font-size:11px;color:var(--text-muted);margin-top:4px;">${label}</div>
          </div>`).join('')}
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">
        <div class="card" style="margin:0;">
          <h4 style="margin:0 0 14px;">Hallazgos por nivel de riesgo</h4>
          ${[
            ['critical','Critico','#DC2626'],
            ['high','Alto','#F97316'],
            ['medium','Medio','#F59E0B'],
            ['low','Bajo','#10B981'],
            ['info','Info','#6B7280']
          ].map(([key, label, color]) => `
            <div style="margin-bottom:8px;">
              <div style="font-size:12px;margin-bottom:3px;">${label}</div>
              ${bar(rbl[key]||0, total, color)}
            </div>`).join('')}
        </div>

        <div class="card" style="margin:0;">
          <h4 style="margin:0 0 14px;">Escaneos por tipo</h4>
          ${[
            ['email','Email','var(--brand-purple)'],
            ['domain','Dominio','var(--brand-orange)'],
            ['ip','IP','#F59E0B'],
            ['url','URL','var(--info)'],
            ['username','Username','#10B981']
          ].map(([key, label, color]) => `
            <div style="margin-bottom:8px;">
              <div style="font-size:12px;margin-bottom:3px;">${label}</div>
              ${bar(sbt[key]||0, Math.max(...Object.values(sbt), 1), color)}
            </div>`).join('')}
        </div>
      </div>

      ${Object.keys(fbs).length > 0 ? `
      <div class="card">
        <h4 style="margin:0 0 14px;">Hallazgos por fuente</h4>
        <div style="display:flex;flex-wrap:wrap;gap:12px;">
          ${Object.entries(fbs).map(([src, count]) => `
            <div style="background:var(--bg-muted);border-radius:8px;padding:12px 16px;text-align:center;min-width:80px;">
              <div style="font-size:20px;font-weight:bold;color:var(--brand-purple);">${count}</div>
              <div style="font-size:11px;color:var(--text-muted);">${UI.esc(src)}</div>
            </div>`).join('')}
        </div>
      </div>` : ''}
    `;
  },

  // ── DRAWER ESCANEO ────────────────────────────────────────────────────────

  async _openScanDrawer(scanId) {
    const drawer = document.getElementById('osint-drawer');
    const content = document.getElementById('drawer-content');
    const title = document.getElementById('drawer-title');
    drawer.style.display = 'block';
    title.textContent = 'Cargando...';
    content.innerHTML = '<div style="color:var(--text-muted);padding:20px 0;">Cargando...</div>';

    try {
      const data = await Api.get(`/api/v1/osint/scans/${scanId}/findings`);
      const scan = data.scan;
      const findings = data.findings || [];

      title.textContent = scan.target;
      const u = Auth.user();
      const isAdmin = u && (u.role === 'admin' || u.role === 'superadmin');
      const canAct = u && (u.role === 'admin' || u.role === 'analyst' || u.role === 'superadmin');

      content.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
          ${[
            ['Tipo', this._typeBadge(scan.scan_type)],
            ['Estado', this._statusBadge(scan.status)],
            ['Hallazgos', `<strong>${scan.findings_count}</strong>`],
            ['Score', `<strong style="color:${this._scoreColor(scan.risk_score)};">${(scan.risk_score||0).toFixed(1)}</strong>`],
            ['Iniciado', scan.started_at ? new Date(scan.started_at).toLocaleString('es-ES') : '—'],
            ['Completado', scan.completed_at ? new Date(scan.completed_at).toLocaleString('es-ES') : '—'],
          ].map(([l,v]) => `
            <div>
              <div style="font-size:11px;color:var(--text-muted);">${l}</div>
              <div style="font-size:13px;margin-top:2px;">${v}</div>
            </div>`).join('')}
        </div>

        ${scan.error_message ? `
          <div style="background:var(--danger-soft);border-radius:6px;padding:10px;
                      font-size:12px;color:var(--danger);margin-bottom:14px;">
            Error: ${UI.esc(scan.error_message)}
          </div>` : ''}

        <h4 style="margin:0 0 10px;font-size:14px;">Hallazgos (${findings.length})</h4>

        ${findings.length === 0
          ? `<p style="color:var(--text-muted);font-size:13px;">Sin hallazgos registrados.</p>`
          : findings.map(f => `
            <div style="border:1px solid var(--border-color);border-radius:8px;padding:12px;
                        margin-bottom:10px;border-left:4px solid ${this._riskColor(f.risk_level)};">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:6px;">
                <span style="font-size:13px;font-weight:500;cursor:pointer;"
                  onclick="ViewOsint._openFindingDrawer(${f.id})">${UI.esc(f.title)}</span>
                ${this._riskBadge(f.risk_level)}
              </div>
              <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">
                Fuente: ${f.source} | Score: ${f.risk_score.toFixed(1)}
                ${f.is_remediated ? ' | <span style="color:var(--success);">Remediado</span>' : ''}
              </div>
              ${f.description ? `
              <div style="font-size:12px;color:var(--text-muted);white-space:pre-wrap;margin-bottom:8px;">
                ${UI.esc(f.description).substring(0,200)}${f.description.length>200?'...':''}
              </div>` : ''}
              ${canAct ? `
              <div style="display:flex;gap:6px;">
                <button class="btn btn-xs" onclick="ViewOsint._openFindingDrawer(${f.id})">Ver detalle</button>
                <button class="btn btn-xs" onclick="ViewOsint._createIncident(${f.id})"
                  title="Crear incidente de seguridad">+ Incidente</button>
                ${!f.is_remediated
                  ? `<button class="btn btn-xs btn-primary" onclick="ViewOsint._remediateAndRefreshScan(${f.id},${scanId})">Resolver</button>`
                  : ''}
              </div>` : ''}
            </div>`).join('')}

        ${isAdmin ? `
          <div style="border-top:1px solid var(--border-color);padding-top:14px;margin-top:14px;">
            <button class="btn btn-sm" style="background:var(--danger);color:white;"
              onclick="ViewOsint._deleteScan(${scanId})">
              Eliminar escaneo
            </button>
          </div>` : ''}
      `;
    } catch (e) {
      content.innerHTML = `<p style="color:var(--danger);">Error: ${UI.esc(e.message)}</p>`;
    }
  },

  // ── DRAWER HALLAZGO ───────────────────────────────────────────────────────

  async _openFindingDrawer(findingId) {
    const drawer = document.getElementById('osint-drawer');
    const content = document.getElementById('drawer-content');
    const title = document.getElementById('drawer-title');
    drawer.style.display = 'block';
    title.textContent = 'Hallazgo OSINT';
    content.innerHTML = '<div style="color:var(--text-muted);">Cargando...</div>';

    try {
      const f = await Api.get(`/api/v1/osint/findings/${findingId}`);
      const u = Auth.user();
      const canEdit = u && (u.role === 'admin' || u.role === 'analyst' || u.role === 'superadmin');

      let metaHtml = '';
      if (f.extra_data && typeof f.extra_data === 'object') {
        const rows = Object.entries(f.extra_data)
          .filter(([, v]) => v !== null && v !== undefined)
          .map(([k, v]) => {
            const display = typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v);
            return `<tr>
              <td style="font-size:11px;color:var(--text-muted);white-space:nowrap;padding:4px 8px 4px 0;
                          vertical-align:top;">${UI.esc(k)}</td>
              <td style="font-size:12px;padding:4px 0;word-break:break-all;">
                <code>${UI.esc(display.substring(0,400))}</code>
              </td>
            </tr>`;
          }).join('');
        if (rows) {
          metaHtml = `<div style="margin-top:14px;">
            <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px;font-weight:600;">
              Datos tecnicos
            </div>
            <table style="width:100%;border-collapse:collapse;">${rows}</table>
          </div>`;
        }
      }

      content.innerHTML = `
        <div style="border-left:4px solid ${this._riskColor(f.risk_level)};
                    padding:12px 14px;background:var(--bg-muted);border-radius:0 6px 6px 0;
                    margin-bottom:16px;">
          <div style="font-size:15px;font-weight:600;margin-bottom:8px;line-height:1.3;">
            ${UI.esc(f.title)}
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            ${this._riskBadge(f.risk_level)}
            <span class="badge badge-muted" style="font-size:11px;">${UI.esc(f.source)}</span>
            <span class="badge badge-muted" style="font-size:11px;">${UI.esc(f.finding_type)}</span>
            <span style="font-size:12px;font-weight:bold;color:${this._scoreColor(f.risk_score)};">
              Score: ${f.risk_score.toFixed(1)}
            </span>
          </div>
        </div>

        ${f.description ? `
        <div style="margin-bottom:14px;">
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">Descripcion</div>
          <div style="font-size:13px;white-space:pre-wrap;line-height:1.5;">${UI.esc(f.description)}</div>
        </div>` : ''}

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px;">
          ${[
            ['Estado', f.is_remediated
              ? '<span style="color:var(--success);">Remediado</span>'
              : '<span style="color:var(--danger);">Pendiente</span>'],
            ['Detectado', f.created_at ? new Date(f.created_at).toLocaleString('es-ES') : '—'],
            ['Remediado el', f.remediated_at ? new Date(f.remediated_at).toLocaleString('es-ES') : '—'],
          ].map(([l,v]) => `
            <div>
              <div style="font-size:11px;color:var(--text-muted);">${l}</div>
              <div style="font-size:13px;margin-top:2px;">${v}</div>
            </div>`).join('')}
        </div>

        ${metaHtml}

        ${canEdit ? `
        <div style="border-top:1px solid var(--border-color);padding-top:14px;margin-top:16px;">
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;font-weight:600;">Acciones</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
            ${f.is_remediated
              ? `<button class="btn btn-sm" onclick="ViewOsint._unremediate(${f.id})">
                   Desmarcar como remediado
                 </button>`
              : `<button class="btn btn-sm btn-primary" onclick="ViewOsint._remediate(${f.id})">
                   Marcar como remediado
                 </button>`}
            <button class="btn btn-sm" onclick="ViewOsint._createIncident(${f.id})"
              style="background:var(--brand-orange);color:white;">
              Crear incidente
            </button>
          </div>
          <!-- Crear riesgo desde hallazgo -->
          <div style="background:var(--bg-muted);border-radius:6px;padding:10px 12px;">
            <div style="font-size:12px;font-weight:600;margin-bottom:8px;color:var(--brand-purple);">
              Crear riesgo en el registro
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
              <div>
                <label style="font-size:11px;">Activo afectado</label>
                <select id="risk-asset-${f.id}" style="font-size:12px;">
                  <option value="">Cargando...</option>
                </select>
              </div>
              <div>
                <label style="font-size:11px;">Amenaza relacionada</label>
                <select id="risk-threat-${f.id}" style="font-size:12px;">
                  <option value="">Cargando...</option>
                </select>
              </div>
            </div>
            <button class="btn btn-sm"
              style="background:var(--brand-purple);color:white;"
              onclick="ViewOsint._createRisk(${f.id})">
              Crear riesgo
            </button>
          </div>
        </div>` : ''}
      `;
      // Populate asset and threat dropdowns asynchronously
      if (canEdit) {
        this._populateRiskSelectors(f.id);
      }
    } catch (e) {
      content.innerHTML = `<p style="color:var(--danger);">Error: ${UI.esc(e.message)}</p>`;
    }
  },

  async _populateRiskSelectors(findingId) {
    try {
      const [assetsResp, threatsResp] = await Promise.all([
        Api.get('/api/assets?limit=200'),
        Api.get('/api/threats?limit=200')
      ]);
      const assets = assetsResp.items || assetsResp || [];
      const threats = threatsResp.items || threatsResp || [];

      const assetSel = document.getElementById(`risk-asset-${findingId}`);
      const threatSel = document.getElementById(`risk-threat-${findingId}`);
      if (!assetSel || !threatSel) return;

      assetSel.innerHTML = `<option value="">-- Seleccionar activo --</option>` +
        assets.map(a => `<option value="${a.id}">${UI.esc(a.name)}</option>`).join('');
      threatSel.innerHTML = `<option value="">-- Seleccionar amenaza --</option>` +
        threats.map(t => `<option value="${t.id}">${UI.esc(t.name)}</option>`).join('');
    } catch (e) {
      // Silencioso — los selects mostrarán error si no cargan
    }
  },

  _closeDrawer() {
    document.getElementById('osint-drawer').style.display = 'none';
  },

  // ── ACCIONES ESCANEO ──────────────────────────────────────────────────────

  async _startScan() {
    const type = document.getElementById('scan-type')?.value;
    const target = document.getElementById('scan-target')?.value?.trim();
    if (!target) { UI.message('Ingresa el objetivo del escaneo', 'error'); return; }

    const paramKey = { email:'email', url:'url', username:'username', domain:'domain', ip:'ip' }[type] || type;
    const endpoint = `/api/v1/osint/scans/${type}?${paramKey}=${encodeURIComponent(target)}`;

    try {
      UI.loading(true);
      await Api.post(endpoint, {});
      UI.message('Escaneo iniciado. Se ejecuta en segundo plano...', 'success');
      document.getElementById('scan-target').value = '';
      await this._load();
      this._tab = 'scans';
      this._renderTab();
    } catch (e) {
      UI.message('Error: ' + e.message, 'error');
    } finally {
      UI.loading(false);
    }
  },

  async _startBulkScan() {
    const type = document.getElementById('bulk-type')?.value;
    const raw = document.getElementById('bulk-targets')?.value?.trim();
    if (!raw) { UI.message('Ingresa al menos un objetivo', 'error'); return; }

    try {
      UI.loading(true);
      const result = await Api.post(
        `/api/v1/osint/scans/bulk?scan_type=${encodeURIComponent(type)}&targets=${encodeURIComponent(raw)}`,
        {}
      );
      UI.message(
        `${result.created} escaneo(s) iniciados${result.skipped ? `, ${result.skipped} omitidos (ya en progreso)` : ''}.`,
        'success'
      );
      document.getElementById('bulk-targets').value = '';
      await this._load();
      this._tab = 'scans';
      this._renderTab();
    } catch (e) {
      UI.message('Error: ' + e.message, 'error');
    } finally {
      UI.loading(false);
    }
  },

  // ── ENTRA ID ──────────────────────────────────────────────────────────────

  _entraidParams() {
    return {
      tenant_id: document.getElementById('eid-tenant')?.value?.trim(),
      client_id: document.getElementById('eid-client')?.value?.trim(),
      client_secret: document.getElementById('eid-secret')?.value?.trim()
    };
  },

  async _entraidTest() {
    const p = this._entraidParams();
    if (!p.tenant_id || !p.client_id || !p.client_secret) {
      UI.message('Completa todos los campos de Entra ID', 'error'); return;
    }
    const status = document.getElementById('entraid-status');
    status.innerHTML = '<span style="color:var(--text-muted);">Probando conexion...</span>';
    try {
      const r = await Api.post(
        `/api/v1/osint/sources/entraid/test?tenant_id=${encodeURIComponent(p.tenant_id)}&client_id=${encodeURIComponent(p.client_id)}&client_secret=${encodeURIComponent(p.client_secret)}`,
        {}
      );
      if (r.success) {
        status.innerHTML = `<span style="color:var(--success);">
          Conexion exitosa — Tenant: <strong>${UI.esc(r.tenant_name)}</strong>
          ${r.country ? `(${UI.esc(r.country)})` : ''}
        </span>`;
      } else {
        status.innerHTML = `<span style="color:var(--danger);">Error: ${UI.esc(r.error || 'Fallo de conexion')}</span>`;
      }
    } catch (e) {
      status.innerHTML = `<span style="color:var(--danger);">Error: ${UI.esc(e.message)}</span>`;
    }
  },

  async _entraidPreview() {
    const p = this._entraidParams();
    if (!p.tenant_id || !p.client_id || !p.client_secret) {
      UI.message('Completa todos los campos de Entra ID', 'error'); return;
    }
    const preview = document.getElementById('entraid-preview');
    const status = document.getElementById('entraid-status');
    status.innerHTML = '<span style="color:var(--text-muted);">Cargando objetivos del tenant...</span>';
    preview.innerHTML = '';
    try {
      const r = await Api.post(
        `/api/v1/osint/sources/entraid/preview?tenant_id=${encodeURIComponent(p.tenant_id)}&client_id=${encodeURIComponent(p.client_id)}&client_secret=${encodeURIComponent(p.client_secret)}`,
        {}
      );
      this._entraidData = r;
      status.innerHTML = `<span style="color:var(--success);">
        ${r.users_count} usuarios y ${r.domains_count} dominios encontrados.
      </span>`;

      preview.innerHTML = `
        <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          <div>
            <div style="font-size:12px;font-weight:600;margin-bottom:6px;">
              Usuarios (${r.users_count})
            </div>
            <div style="max-height:180px;overflow-y:auto;border:1px solid var(--border-color);
                        border-radius:6px;padding:6px;">
              ${(r.users || []).slice(0, 30).map(u => `
                <div style="font-size:12px;padding:3px 4px;border-bottom:1px solid var(--border-color);">
                  <span style="font-weight:500;">${UI.esc(u.name || u.email)}</span>
                  <br><span style="color:var(--text-muted);font-size:11px;">${UI.esc(u.email)}</span>
                </div>`).join('')}
              ${r.users_count > 30 ? `<div style="font-size:11px;color:var(--text-muted);padding:4px;">...y ${r.users_count-30} mas</div>` : ''}
            </div>
          </div>
          <div>
            <div style="font-size:12px;font-weight:600;margin-bottom:6px;">
              Dominios verificados (${r.domains_count})
            </div>
            <div style="max-height:180px;overflow-y:auto;border:1px solid var(--border-color);
                        border-radius:6px;padding:6px;">
              ${(r.domains || []).map(d => `
                <div style="font-size:12px;padding:3px 4px;border-bottom:1px solid var(--border-color);">
                  <strong>${UI.esc(d.id)}</strong>
                  ${d.is_default ? '<span style="color:var(--brand-purple);font-size:10px;margin-left:4px;">Principal</span>' : ''}
                </div>`).join('')}
            </div>
          </div>
        </div>
        <button class="btn btn-primary" style="margin-top:12px;" onclick="ViewOsint._entraidImport()">
          Importar e iniciar escaneos
        </button>
      `;
    } catch (e) {
      status.innerHTML = `<span style="color:var(--danger);">Error: ${UI.esc(e.message)}</span>`;
    }
  },

  async _entraidImport() {
    const p = this._entraidParams();
    const scanUsers = document.getElementById('eid-users')?.checked ?? true;
    const scanDomains = document.getElementById('eid-domains')?.checked ?? true;
    const userLimit = document.getElementById('eid-limit')?.value || 50;

    if (!p.tenant_id || !p.client_id || !p.client_secret) {
      UI.message('Completa todos los campos de Entra ID', 'error'); return;
    }
    if (!scanUsers && !scanDomains) {
      UI.message('Selecciona al menos un tipo de objetivo para escanear', 'error'); return;
    }

    try {
      UI.loading(true);
      const r = await Api.post(
        `/api/v1/osint/sources/entraid/import?tenant_id=${encodeURIComponent(p.tenant_id)}&client_id=${encodeURIComponent(p.client_id)}&client_secret=${encodeURIComponent(p.client_secret)}&scan_users=${scanUsers}&scan_domains=${scanDomains}&user_limit=${userLimit}`,
        {}
      );
      UI.message(`${r.scans_created} escaneo(s) iniciados desde Entra ID.`, 'success');
      document.getElementById('entraid-status').innerHTML =
        `<span style="color:var(--success);">${r.scans_created} escaneos en cola.</span>`;
      await this._load();
      this._tab = 'scans';
      this._renderTab();
    } catch (e) {
      UI.message('Error importando: ' + e.message, 'error');
    } finally {
      UI.loading(false);
    }
  },

  // ── ACCIONES HALLAZGOS ────────────────────────────────────────────────────

  async _remediate(id) {
    try {
      UI.loading(true);
      await Api.patch(`/api/v1/osint/findings/${id}/remediate`, {});
      UI.message('Hallazgo marcado como remediado', 'success');
      await this._load();
      this._renderTab();
      if (document.getElementById('osint-drawer').style.display !== 'none') {
        this._openFindingDrawer(id);
      }
    } catch (e) { UI.message('Error: ' + e.message, 'error'); }
    finally { UI.loading(false); }
  },

  async _unremediate(id) {
    try {
      UI.loading(true);
      await Api.patch(`/api/v1/osint/findings/${id}/unremediate`, {});
      UI.message('Hallazgo desmarcado', 'success');
      await this._load();
      this._renderTab();
      if (document.getElementById('osint-drawer').style.display !== 'none') {
        this._openFindingDrawer(id);
      }
    } catch (e) { UI.message('Error: ' + e.message, 'error'); }
    finally { UI.loading(false); }
  },

  async _remediateAndRefreshScan(findingId, scanId) {
    try {
      UI.loading(true);
      await Api.patch(`/api/v1/osint/findings/${findingId}/remediate`, {});
      await this._load();
      this._openScanDrawer(scanId);
    } catch (e) { UI.message('Error: ' + e.message, 'error'); }
    finally { UI.loading(false); }
  },

  async _createRisk(findingId) {
    const assetSel = document.getElementById(`risk-asset-${findingId}`);
    const threatSel = document.getElementById(`risk-threat-${findingId}`);
    const assetId = assetSel?.value;
    const threatId = threatSel?.value;
    if (!assetId) { UI.message('Selecciona un activo', 'error'); return; }
    if (!threatId) { UI.message('Selecciona una amenaza', 'error'); return; }
    try {
      UI.loading(true);
      const r = await Api.post(
        `/api/v1/osint/findings/${findingId}/create-risk?asset_id=${assetId}&threat_id=${threatId}`,
        {}
      );
      if (r.already_existed) {
        UI.message(`Ya existe el riesgo ${r.risk_code} para este activo/amenaza`, 'info');
      } else {
        UI.message(`Riesgo ${r.risk_code} creado: ${r.title}`, 'success');
      }
    } catch (e) { UI.message('Error creando riesgo: ' + e.message, 'error'); }
    finally { UI.loading(false); }
  },

  async _createIncident(findingId) {
    try {
      UI.loading(true);
      const r = await Api.post(`/api/v1/osint/findings/${findingId}/create-incident`, {});
      if (r.already_existed) {
        UI.message(`Ya existe el incidente ${r.incident_code}`, 'info');
      } else {
        UI.message(`Incidente ${r.incident_code} creado correctamente`, 'success');
      }
    } catch (e) { UI.message('Error creando incidente: ' + e.message, 'error'); }
    finally { UI.loading(false); }
  },

  async _deleteScan(id) {
    if (!confirm('Eliminar este escaneo y todos sus hallazgos?')) return;
    try {
      UI.loading(true);
      await Api.del(`/api/v1/osint/scans/${id}`);
      UI.message('Escaneo eliminado', 'success');
      this._closeDrawer();
      await this._load();
      this._renderTab();
    } catch (e) { UI.message('Error: ' + e.message, 'error'); }
    finally { UI.loading(false); }
  },

  async _rescan(type, value) {
    const paramKey = { email:'email', url:'url', username:'username', domain:'domain', ip:'ip' }[type] || type;
    const endpoint = `/api/v1/osint/scans/${type}?${paramKey}=${encodeURIComponent(value)}`;
    try {
      UI.loading(true);
      await Api.post(endpoint, {});
      UI.message('Re-escaneo iniciado...', 'success');
      await this._load();
      this._tab = 'scans';
      this._renderTab();
    } catch (e) { UI.message('Error: ' + e.message, 'error'); }
    finally { UI.loading(false); }
  },

  async _exportCSV() {
    try {
      const resp = await fetch('/api/v1/osint/findings/export/csv', {
        headers: { 'Authorization': `Bearer ${Api.token()}` }
      });
      if (!resp.ok) throw new Error('Export failed');
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `osint_findings_${new Date().toISOString().slice(0,10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { UI.message('Error exportando: ' + e.message, 'error'); }
  },

  // ── HELPERS VISUALES ──────────────────────────────────────────────────────

  _riskColor(level) {
    const l = (level || '').replace('OSINTFindingRiskLevel.', '').toLowerCase();
    return {critical:'#DC2626',high:'#F97316',medium:'#F59E0B',low:'#10B981',info:'#6B7280'}[l] || '#6B7280';
  },
  _scoreColor(score) {
    if (!score) return 'var(--text-muted)';
    if (score >= 70) return '#DC2626';
    if (score >= 50) return '#F97316';
    if (score >= 30) return '#F59E0B';
    return '#10B981';
  },
  _riskBadge(level) {
    const l = (level || '').replace('OSINTFindingRiskLevel.', '').toLowerCase();
    const c = this._riskColor(l);
    return `<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;
                         font-weight:600;background:${c}20;color:${c};">${l.toUpperCase()}</span>`;
  },
  _typeBadge(type) {
    const map = {email:'Email',domain:'Dominio',url:'URL',username:'Usuario',ip:'IP'};
    return `<span class="badge badge-muted" style="font-size:11px;">${map[type]||type}</span>`;
  },
  _statusBadge(status) {
    const map = {
      completed: ['var(--success-soft)','var(--success)','Completado'],
      in_progress: ['var(--warning-soft)','var(--warning)','En progreso'],
      pending: ['var(--border-color)','var(--text-muted)','Pendiente'],
      failed: ['var(--danger-soft)','var(--danger)','Fallido']
    };
    const [bg, color, label] = map[status] || ['var(--border-color)','var(--text-muted)', status];
    return `<span style="padding:2px 8px;border-radius:4px;font-size:11px;background:${bg};color:${color};">${label}</span>`;
  }
};
