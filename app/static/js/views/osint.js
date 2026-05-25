/* Vista OSINT — Escaneo de inteligencia de fuentes abiertas (huella-digital). */
const ViewOsint = {

  _scans: [],
  _findings: [],
  _identifiers: [],
  _stats: null,
  _tab: 'scans',
  _selectedScan: null,
  _pollInterval: null,

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      'OSINT — Inteligencia de fuentes abiertas',
      'Escaneo de datos públicos expuestos: emails, URLs, dominios, usernames en HIBP, VirusTotal, GitHub, redes sociales'
    ) + `
      <div style="margin-bottom:16px; display:flex; gap:8px; border-bottom:1px solid var(--border-color); padding-bottom:12px;">
        <button class="tab-btn" onclick="ViewOsint._selectTab('scans')">📊 Escaneos</button>
        <button class="tab-btn" onclick="ViewOsint._selectTab('findings')">🔍 Hallazgos</button>
        <button class="tab-btn" onclick="ViewOsint._selectTab('identifiers')">👤 Identificadores</button>
        <button class="tab-btn" onclick="ViewOsint._selectTab('stats')">📈 Estadísticas</button>
      </div>
      <div id="osint-content"></div>
    `;
    document.querySelectorAll('.tab-btn').forEach(b => b.style.padding = '8px 12px');
    this._tab = 'scans';
    await this._load();
    this._startPolling();
  },

  async _load() {
    const c = document.getElementById('osint-content');
    try {
      const [scans, findings, identifiers, stats] = await Promise.all([
        Api.get('/api/v1/osint/scans?limit=100'),
        Api.get('/api/v1/osint/findings?limit=100'),
        Api.get('/api/v1/osint/identifiers?limit=100'),
        Api.get('/api/v1/osint/stats'),
      ]);
      this._scans = scans.items || [];
      this._findings = findings.items || [];
      this._identifiers = identifiers.items || [];
      this._stats = stats;
      this._render(c);
    } catch (e) {
      c.innerHTML = UI.notice('Error al cargar OSINT: ' + UI.esc(e.message), 'error');
    }
  },

  _startPolling() {
    clearInterval(this._pollInterval);
    this._pollInterval = setInterval(() => {
      const inProgress = this._scans.filter(s => s.status === 'in_progress' || s.status === 'pending');
      if (inProgress.length > 0) {
        this._load();
      }
    }, 3000);
  },

  _selectTab(tab) {
    this._tab = tab;
    const c = document.getElementById('osint-content');
    this._render(c);
  },

  _render(container) {
    if (this._tab === 'scans') {
      this._renderScans(container);
    } else if (this._tab === 'findings') {
      this._renderFindings(container);
    } else if (this._tab === 'identifiers') {
      this._renderIdentifiers(container);
    } else if (this._tab === 'stats') {
      this._renderStats(container);
    }
  },

  _renderScans(container) {
    const u = Auth.user();
    const isAnalyst = u && (u.role === 'admin' || u.role === 'analyst');

    let scansByType = { email: [], url: [], username: [], domain: [], ip: [] };
    this._scans.forEach(s => {
      if (scansByType[s.scan_type]) scansByType[s.scan_type].push(s);
    });

    container.innerHTML = `
      ${isAnalyst ? `
      <div class="card" style="margin-bottom:16px;">
        <h3 style="margin:0 0 16px 0;">Iniciar nuevo escaneo</h3>
        <div class="modal-body">
          <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px;">
            <div>
              <label>Tipo de escaneo</label>
              <select id="scan-type" style="width:100%;">
                <option value="email">📧 Email</option>
                <option value="url">🔗 URL</option>
                <option value="username">👤 Username (GitHub)</option>
                <option value="domain">🌐 Dominio</option>
              </select>
            </div>
            <div>
              <label>Objetivo</label>
              <input id="scan-target" type="text" placeholder="ejemplo@company.com o https://..."
                     style="width:100%;">
            </div>
          </div>
          <button class="btn btn-primary" onclick="ViewOsint._startScan()">
            Iniciar escaneo</button>
        </div>
      </div>
      ` : ''}

      <div class="card">
        <h3 style="margin:0 0 12px 0;">Escaneos activos y completados</h3>
        ${this._scans.length === 0 ? `
          <p style="color:var(--text-muted); margin:0;">Sin escaneos. ${isAnalyst ? 'Inicia uno arriba.' : ''}</p>
        ` : `
          <div style="overflow-x:auto;">
            <table class="data">
              <thead><tr>
                <th>Tipo</th><th>Objetivo</th><th>Estado</th><th>Hallazgos</th><th>Riesgo</th><th>Fecha</th><th></th>
              </tr></thead>
              <tbody>
                ${this._scans.map(s => `
                <tr style="cursor:pointer;" onclick="ViewOsint._selectScan(${s.id})">
                  <td>
                    <span class="badge badge-muted" style="background:var(--info-soft);color:var(--info);">
                      ${s.scan_type}
                    </span>
                  </td>
                  <td><code style="font-size:12px;">${UI.esc(s.target)}</code></td>
                  <td>
                    <span class="badge" style="background:${
                      s.status === 'completed' ? 'var(--success-soft);color:var(--success)' :
                      s.status === 'in_progress' ? 'var(--warning-soft);color:var(--warning)' :
                      s.status === 'failed' ? 'var(--danger-soft);color:var(--danger)' :
                      'var(--border-color);color:var(--text-muted)'
                    };">
                      ${s.status}
                    </span>
                  </td>
                  <td><strong>${s.findings_count}</strong></td>
                  <td><strong>${s.risk_score.toFixed(1)}</strong></td>
                  <td style="font-size:12px; color:var(--text-muted);">
                    ${new Date(s.started_at).toLocaleString('es-ES')}
                  </td>
                  <td style="text-align:right;">
                    <button class="btn btn-xs" onclick="event.stopPropagation(); ViewOsint._viewScan(${s.id})">
                      Ver
                    </button>
                  </td>
                </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `}
      </div>
    `;
  },

  _renderFindings(container) {
    const u = Auth.user();
    const isAnalyst = u && (u.role === 'admin' || u.role === 'analyst');

    const unremediated = this._findings.filter(f => !f.is_remediated);
    const remediated = this._findings.filter(f => f.is_remediated);

    container.innerHTML = `
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
          <h3 style="margin:0;">Hallazgos por remediar (${unremediated.length})</h3>
          <span class="badge" style="background:var(--danger-soft); color:var(--danger); padding:4px 8px;">
            ${unremediated.length}
          </span>
        </div>
        ${unremediated.length === 0 ? `
          <p style="color:var(--success); margin:0;">✓ No hay hallazgos por remediar</p>
        ` : `
          <div style="overflow-x:auto;">
            <table class="data">
              <thead><tr>
                <th>Título</th><th>Fuente</th><th>Riesgo</th><th>Score</th><th></th>
              </tr></thead>
              <tbody>
                ${unremediated.map(f => `
                <tr onclick="ViewOsint._viewFinding(${f.id})" style="cursor:pointer;">
                  <td>${UI.esc(f.title)}</td>
                  <td><span class="badge badge-muted">${f.source}</span></td>
                  <td>
                    <span class="badge" style="background:${this._riskBadgeColor(f.risk_level)};
                                               color:white; padding:3px 8px;">
                      ${f.risk_level.toUpperCase()}
                    </span>
                  </td>
                  <td><strong>${f.risk_score.toFixed(1)}</strong></td>
                  <td style="text-align:right;">
                    <button class="btn btn-xs" onclick="event.stopPropagation(); ViewOsint._remediateFinding(${f.id})">
                      Marcar resuelto
                    </button>
                  </td>
                </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `}
      </div>

      ${remediated.length > 0 ? `
      <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
          <h3 style="margin:0;">Hallazgos remediados (${remediated.length})</h3>
          <span class="badge" style="background:var(--success-soft); color:var(--success); padding:4px 8px;">
            ${remediated.length}
          </span>
        </div>
        <div style="overflow-x:auto;">
          <table class="data" style="opacity:0.7;">
            <thead><tr>
              <th>Título</th><th>Fuente</th><th>Riesgo</th><th>Score</th><th></th>
            </tr></thead>
            <tbody>
              ${remediated.map(f => `
              <tr>
                <td>${UI.esc(f.title)}</td>
                <td><span class="badge badge-muted">${f.source}</span></td>
                <td>
                  <span class="badge" style="background:var(--success-soft); color:var(--success); padding:3px 8px;">
                    ${f.risk_level.toUpperCase()}
                  </span>
                </td>
                <td><strong>${f.risk_score.toFixed(1)}</strong></td>
                <td style="text-align:right;">
                  <button class="btn btn-xs" onclick="ViewOsint._unremediateFinding(${f.id})">
                    Desmarcar
                  </button>
                </td>
              </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
      ` : ''}
    `;
  },

  _renderIdentifiers(container) {
    container.innerHTML = `
      <div class="card">
        <h3 style="margin:0 0 12px 0;">Identificadores monitorizados (${this._identifiers.length})</h3>
        ${this._identifiers.length === 0 ? `
          <p style="color:var(--text-muted); margin:0;">Sin identificadores. Se agregaran automaticamente al iniciar escaneos.</p>
        ` : `
          <div style="overflow-x:auto;">
            <table class="data">
              <thead><tr>
                <th>Tipo</th><th>Valor</th><th>Último escaneo</th><th>Riesgo actual</th><th></th>
              </tr></thead>
              <tbody>
                ${this._identifiers.map(i => `
                <tr>
                  <td><span class="badge badge-muted">${i.identifier_type}</span></td>
                  <td><code style="font-size:12px;">${UI.esc(i.value)}</code></td>
                  <td style="font-size:12px; color:var(--text-muted);">
                    ${i.last_scanned_at ? new Date(i.last_scanned_at).toLocaleString('es-ES') : 'Nunca'}
                  </td>
                  <td>
                    <span class="badge" style="background:${this._riskBadgeColor(i.risk_level)}; color:white; padding:3px 8px;">
                      ${i.risk_level.toUpperCase()}
                    </span>
                  </td>
                  <td style="text-align:right;">
                    <button class="btn btn-xs" onclick="ViewOsint._rescanIdentifier('${i.identifier_type}', '${UI.esc(i.value)}')">
                      Re-escanear
                    </button>
                  </td>
                </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        `}
      </div>
    `;
  },

  _renderStats(container) {
    const stats = this._stats || {};
    container.innerHTML = `
      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(200px, 1fr)); gap:12px; margin-bottom:16px;">
        <div class="card" style="margin:0; text-align:center;">
          <div style="font-size:28px; font-weight:bold; color:var(--primary);">${stats.scans_total || 0}</div>
          <div style="font-size:12px; color:var(--text-muted); margin-top:4px;">Escaneos realizados</div>
        </div>
        <div class="card" style="margin:0; text-align:center;">
          <div style="font-size:28px; font-weight:bold; color:var(--danger);">${stats.findings_total || 0}</div>
          <div style="font-size:12px; color:var(--text-muted); margin-top:4px;">Hallazgos totales</div>
        </div>
        <div class="card" style="margin:0; text-align:center;">
          <div style="font-size:28px; font-weight:bold; color:var(--warning);">${stats.findings_pending || 0}</div>
          <div style="font-size:12px; color:var(--text-muted); margin-top:4px;">Por remediar</div>
        </div>
        <div class="card" style="margin:0; text-align:center;">
          <div style="font-size:28px; font-weight:bold; color:var(--success);">${stats.findings_remediated || 0}</div>
          <div style="font-size:12px; color:var(--text-muted); margin-top:4px;">Remediados</div>
        </div>
      </div>

      <div class="card">
        <h3 style="margin:0 0 12px 0;">Hallazgos por nivel de riesgo</h3>
        ${stats.risk_by_level ? `
          <div style="display:grid; grid-template-columns:repeat(5, 1fr); gap:8px;">
            ${Object.entries(stats.risk_by_level).map(([level, count]) => `
              <div style="text-align:center; padding:12px; background:${this._riskBadgeColor(level)}20; border-radius:6px;">
                <div style="font-size:20px; font-weight:bold; color:${this._riskBadgeColor(level)};">${count}</div>
                <div style="font-size:11px; color:var(--text-muted); text-transform:uppercase; margin-top:4px;">${level}</div>
              </div>
            `).join('')}
          </div>
        ` : '<p style="color:var(--text-muted); margin:0;">Sin datos</p>'}
      </div>
    `;
  },

  async _startScan() {
    const type = document.getElementById('scan-type')?.value;
    const target = document.getElementById('scan-target')?.value;

    if (!target || target.trim() === '') {
      UI.message('Ingresa el objetivo del escaneo', 'error');
      return;
    }

    try {
      UI.loading(true);
      const endpoint = `/api/v1/osint/scans/${type}?${type === 'email' ? 'email' : type === 'url' ? 'url' : 'username'}=${encodeURIComponent(target)}`;
      await Api.post(endpoint, {});
      UI.message('Escaneo iniciado. Se ejecutará en segundo plano...', 'success');
      document.getElementById('scan-target').value = '';
      setTimeout(() => this._load(), 500);
    } catch (e) {
      UI.message('Error: ' + e.message, 'error');
    } finally {
      UI.loading(false);
    }
  },

  async _remediateFinding(findingId) {
    if (!confirm('¿Marcar este hallazgo como remediado?')) return;
    try {
      UI.loading(true);
      await Api.patch(`/api/v1/osint/findings/${findingId}/remediate`, {});
      UI.message('Hallazgo marcado como remediado', 'success');
      await this._load();
    } catch (e) {
      UI.message('Error: ' + e.message, 'error');
    } finally {
      UI.loading(false);
    }
  },

  async _unremediateFinding(findingId) {
    if (!confirm('¿Desmarcar este hallazgo como remediado?')) return;
    try {
      UI.loading(true);
      await Api.patch(`/api/v1/osint/findings/${findingId}/unremediate`, {});
      UI.message('Hallazgo desmarcado', 'success');
      await this._load();
    } catch (e) {
      UI.message('Error: ' + e.message, 'error');
    } finally {
      UI.loading(false);
    }
  },

  _selectScan(scanId) {
    this._selectedScan = this._scans.find(s => s.id === scanId);
  },

  _viewScan(scanId) {
    const scan = this._scans.find(s => s.id === scanId);
    if (!scan) return;
    const scanFindings = this._findings.filter(f => f.scan_id === scanId);
    const msg = `
      Escaneo: ${scan.target}
      Estado: ${scan.status}
      Hallazgos: ${scan.findings_count}
      Riesgo promedio: ${scan.risk_score.toFixed(1)}

      ${scanFindings.map(f => `• ${f.title}`).join('\\n')}
    `;
    alert(msg);
  },

  _viewFinding(findingId) {
    const f = this._findings.find(x => x.id === findingId);
    if (!f) return;
    const msg = `
      ${f.title}
      Tipo: ${f.finding_type}
      Fuente: ${f.source}
      Riesgo: ${f.risk_level} (${f.risk_score})

      ${f.description || ''}
    `;
    alert(msg);
  },

  async _rescanIdentifier(type, value) {
    try {
      UI.loading(true);
      const endpoint = `/api/v1/osint/scans/${type}?${type === 'email' ? 'email' : 'username'}=${encodeURIComponent(value)}`;
      await Api.post(endpoint, {});
      UI.message('Re-escaneo iniciado...', 'success');
      setTimeout(() => this._load(), 500);
    } catch (e) {
      UI.message('Error: ' + e.message, 'error');
    } finally {
      UI.loading(false);
    }
  },

  _riskBadgeColor(level) {
    const colors = {
      'critical': 'var(--danger)',
      'high': '#DC2626',
      'medium': 'var(--warning)',
      'low': '#10B981',
      'info': '#6B7280'
    };
    return colors[level] || 'var(--text-muted)';
  }
};
