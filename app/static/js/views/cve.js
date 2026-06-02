/* Vista CVE Monitor — Integracion NVD + analisis de riesgo por IA.
   Tabs: Configuracion | Monitor CVEs | Analisis IA
*/
const ViewCve = {

  _tab: 'monitor',
  _cves: [],
  _selectedCves: new Set(),
  _assets: [],
  _selectedAssets: new Set(),
  _analysisResults: [],
  _config: null,

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      'CVE Monitor',
      'Monitoreo de vulnerabilidades en tiempo real (NVD/NIST) con analisis de riesgo por IA'
    ) + `
      <div style="display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap;">
        <button class="btn" id="cve-tab-config" onclick="ViewCve._showTab('config')">Configuracion</button>
        <button class="btn btn-primary" id="cve-tab-monitor" onclick="ViewCve._showTab('monitor')">Monitor CVEs</button>
        <button class="btn" id="cve-tab-analyze" onclick="ViewCve._showTab('analyze')">Analisis IA</button>
      </div>
      <div id="cve-config-panel" style="display:none;"></div>
      <div id="cve-monitor-panel" style="display:none;"></div>
      <div id="cve-analyze-panel" style="display:none;"></div>
    `;
    await this._loadConfig();
    this._showTab(this._tab);
  },

  async _loadConfig() {
    try {
      this._config = await Api.cve.getConfig();
    } catch (e) {
      this._config = { configured: false, has_api_key: false, default_days: 7, default_severity: 'HIGH' };
    }
  },

  _showTab(tab) {
    this._tab = tab;
    ['config', 'monitor', 'analyze'].forEach(t => {
      document.getElementById(`cve-${t}-panel`).style.display = t === tab ? '' : 'none';
      const btn = document.getElementById(`cve-tab-${t}`);
      if (btn) btn.className = t === tab ? 'btn btn-primary' : 'btn';
    });
    if (tab === 'config') this._renderConfig();
    else if (tab === 'monitor') this._renderMonitor();
    else if (tab === 'analyze') this._renderAnalyze();
  },

  // ---- Configuracion ----

  _renderConfig() {
    const p = document.getElementById('cve-config-panel');
    if (!p) return;
    const cfg = this._config || {};
    p.innerHTML = `
      <div class="card" style="max-width:680px;">
        <h3 style="margin:0 0 4px;font-size:15px;">Configuracion CVE Monitor</h3>
        <p style="font-size:12px;color:var(--text-muted);margin:0 0 20px;">
          Fuente de datos: <strong>NVD (NIST National Vulnerability Database) — API v2</strong>.
          Sin API key funciona con limite de 5 req/30s; con API key aumenta a 50 req/30s.
          Solicita tu API key gratuita en
          <a href="https://nvd.nist.gov/developers/request-an-api-key" target="_blank" rel="noopener"
             style="color:var(--brand-purple);">nvd.nist.gov</a>.
        </p>
        <div class="form-grid" style="margin-bottom:16px;">
          <div class="span2"><label style="font-size:12px;">API Key NVD (opcional)</label>
            <input type="password" id="cve-apikey" class="input"
              placeholder="${cfg.has_api_key ? '(API key guardada — dejar en blanco para no cambiar)' : 'Opcional — mejora el rate limit'}">
          </div>
          <div><label style="font-size:12px;">Ventana de tiempo por defecto (dias)</label>
            <input type="number" id="cve-days" class="input" min="1" max="90"
              value="${cfg.default_days || 7}">
          </div>
          <div><label style="font-size:12px;">Severidad minima por defecto</label>
            <select id="cve-sev" class="input">
              ${['CRITICAL','HIGH','MEDIUM','LOW','ALL'].map(s =>
                `<option value="${s}" ${(cfg.default_severity||'HIGH')===s?'selected':''}>${s}</option>`
              ).join('')}
            </select>
          </div>
          <div class="span2" style="display:flex;align-items:center;gap:10px;padding:12px;
              background:var(--bg-2);border-radius:8px;">
            <label class="toggle-switch">
              <input type="checkbox" id="cve-autoscan" ${cfg.auto_scan_enabled?'checked':''}>
              <span class="toggle-slider"></span>
            </label>
            <div>
              <div style="font-size:13px;font-weight:600;">Escaneo automatico diario</div>
              <div style="font-size:11px;color:var(--text-muted);">
                El scheduler comprueba CVEs nuevas cada 24 horas y las deja disponibles en Monitor.
              </div>
            </div>
          </div>
          <div><label style="font-size:12px;">Severidad para escaneo automatico</label>
            <select id="cve-autosev" class="input">
              ${['CRITICAL','HIGH','MEDIUM','LOW','ALL'].map(s =>
                `<option value="${s}" ${(cfg.auto_scan_severity||'CRITICAL')===s?'selected':''}>${s}</option>`
              ).join('')}
            </select>
          </div>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-primary" onclick="ViewCve._saveConfig()">Guardar configuracion</button>
        </div>
        ${cfg.updated_at ? `<p style="font-size:11px;color:var(--text-muted);margin:12px 0 0;">Ultima actualizacion: ${cfg.updated_at.slice(0,19).replace('T',' ')}</p>` : ''}
      </div>

      <div class="card" style="max-width:680px;margin-top:16px;">
        <h4 style="margin:0 0 12px;font-size:13px;">Proveedores de CVE alternativos</h4>
        <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px;">
          Ademas de NVD, puedes consultar estas fuentes complementarias manualmente:
        </p>
        <ul style="font-size:12px;padding-left:20px;margin:0;line-height:1.9;">
          <li><strong>CISA KEV (Known Exploited Vulnerabilities):</strong>
            <a href="https://www.cisa.gov/known-exploited-vulnerabilities-catalog" target="_blank" rel="noopener" style="color:var(--brand-purple);">cisa.gov/known-exploited-vulnerabilities-catalog</a>
            — catalogo de CVEs activamente explotadas.
          </li>
          <li><strong>CVE.org (MITRE):</strong>
            <a href="https://www.cve.org" target="_blank" rel="noopener" style="color:var(--brand-purple);">cve.org</a>
            — fuente oficial de asignacion de IDs CVE.
          </li>
          <li><strong>OSV (Open Source Vulnerabilities):</strong>
            <a href="https://osv.dev" target="_blank" rel="noopener" style="color:var(--brand-purple);">osv.dev</a>
            — base de datos de vulnerabilidades en software open source.
          </li>
          <li><strong>Exploit-DB:</strong>
            <a href="https://www.exploit-db.com" target="_blank" rel="noopener" style="color:var(--brand-purple);">exploit-db.com</a>
            — exploits publicos vinculados a CVEs.
          </li>
        </ul>
      </div>
    `;
  },

  // ---- Busqueda manual ----

  async _lookupManual() {
    const input = document.getElementById('cve-manual-input');
    const q = input?.value.trim();
    if (!q) { UI.toast('Introduce un CVE ID o URL', 'warn'); return; }
    const res = document.getElementById('cve-manual-result');
    if (res) res.innerHTML = '<p class="text-muted" style="font-size:13px;">Buscando en NVD...</p>';
    try {
      const cve = await Api.cve.lookup(q);
      if (res) res.innerHTML = this._cveManualCard(cve);
    } catch (e) {
      if (res) res.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _cveManualCard(cve) {
    const sevColor = { CRITICAL: '#B91C1C', HIGH: '#D97706', MEDIUM: '#2563EB', LOW: '#059669', UNKNOWN: '#6B7280' };
    const col = sevColor[cve.cvss_severity] || '#6B7280';
    const selBtn = `<button class="btn btn-sm btn-primary"
      data-cve="${UI.esc(JSON.stringify(cve))}"
      onclick="ViewCve._addManualCveToAnalysis(JSON.parse(this.dataset.cve))">
      Añadir al análisis IA
    </button>`;
    return `
      <div style="border:1px solid var(--border);border-radius:8px;padding:14px;background:var(--bg-2);">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;margin-bottom:8px;">
          <div>
            <strong style="font-size:14px;">${UI.esc(cve.id)}</strong>
            <span style="margin-left:8px;background:${col};color:#fff;border-radius:4px;
                         padding:2px 8px;font-size:11px;font-weight:700;">${UI.esc(cve.cvss_severity)} ${cve.cvss_score}</span>
          </div>
          <div style="display:flex;gap:6px;">
            ${selBtn}
            <button class="btn btn-sm" onclick="ViewCve._selectedCves.add('${UI.esc(cve.id)}');UI.toast('${UI.esc(cve.id)} añadido a la seleccion','success');">
              Seleccionar
            </button>
          </div>
        </div>
        <p style="font-size:12px;color:var(--text-muted);margin:0 0 8px;line-height:1.5;">${UI.esc(cve.description.slice(0,300))}${cve.description.length>300?'...':''}</p>
        <div style="display:flex;gap:16px;font-size:11px;color:var(--text-muted);">
          <span>Vector: <code>${UI.esc(cve.cvss_vector||'-')}</code></span>
          <span>Publicado: ${UI.esc((cve.published||'').slice(0,10))}</span>
          ${cve.affected_products?.length ? `<span>Productos: ${cve.affected_products.slice(0,4).map(p=>UI.esc(p)).join(', ')}</span>` : ''}
        </div>
      </div>`;
  },

  _addManualCveToAnalysis(cve) {
    // Añadir el CVE a la lista de seleccionados y navegar a Analisis IA
    this._selectedCves.add(cve.id);
    // Guardar el CVE en la lista local para que aparezca en el análisis
    if (!this._cves.find(c => c.id === cve.id)) {
      this._cves.unshift(cve);
    }
    this._showTab('analyze');
    UI.toast(`${cve.id} añadido al análisis IA`, 'success');
  },

  async _saveConfig() {
    const apikey = document.getElementById('cve-apikey')?.value.trim();
    const days = parseInt(document.getElementById('cve-days')?.value || '7');
    const sev = document.getElementById('cve-sev')?.value;
    const autoscan = document.getElementById('cve-autoscan')?.checked || false;
    const autosev = document.getElementById('cve-autosev')?.value;
    try {
      const payload = { default_days: days, default_severity: sev, auto_scan_enabled: autoscan, auto_scan_severity: autosev };
      if (apikey) payload.api_key = apikey;
      const r = await Api.cve.saveConfig(payload);
      UI.toast(r.message, 'success');
      await this._loadConfig();
      this._renderConfig();
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  // ---- Monitor CVEs ----

  _renderMonitor() {
    const p = document.getElementById('cve-monitor-panel');
    if (!p) return;
    const cfg = this._config || {};
    p.innerHTML = `
      <!-- Busqueda manual por ID o URL -->
      <div class="card" style="margin-bottom:16px;border-left:4px solid var(--brand-purple);">
        <h4 style="margin:0 0 8px;font-size:13px;font-weight:600;">Añadir CVE manualmente</h4>
        <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px;">
          Pega un ID CVE o un enlace de NVD / MITRE / CVE.org y pulsa Buscar.
        </p>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <input id="cve-manual-input" class="input" style="flex:1;min-width:260px;"
            placeholder="CVE-2024-12345  ó  https://nvd.nist.gov/vuln/detail/CVE-2024-12345"
            onkeydown="if(event.key==='Enter')ViewCve._lookupManual()">
          <button class="btn btn-primary" onclick="ViewCve._lookupManual()">Buscar</button>
        </div>
        <div id="cve-manual-result" style="margin-top:12px;"></div>
      </div>

      <!-- Busqueda periodica NVD -->
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;">
          <div>
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Ultimos (dias)</label>
            <input type="number" id="cve-f-days" class="input" min="1" max="90"
              value="${cfg.default_days || 7}" style="width:80px;">
          </div>
          <div>
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Severidad minima</label>
            <select id="cve-f-sev" class="input" style="width:130px;">
              ${['CRITICAL','HIGH','MEDIUM','LOW','ALL'].map(s =>
                `<option value="${s}" ${(cfg.default_severity||'HIGH')===s?'selected':''}>${s}</option>`
              ).join('')}
            </select>
          </div>
          <div style="flex:1;min-width:160px;">
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Busqueda (keyword)</label>
            <input id="cve-f-kw" class="input" placeholder="ej: apache, linux, openssl, windows..." style="width:100%;">
          </div>
          <button class="btn btn-primary" onclick="ViewCve._fetchCves()">Buscar CVEs</button>
        </div>
      </div>

      <div id="cve-results-header" style="display:none;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;">
        <span id="cve-results-count" style="font-size:13px;font-weight:600;"></span>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-sm" id="cve-sel-all-btn" onclick="ViewCve._selectAllCves()" style="display:none;">
            Seleccionar todas
          </button>
          <button class="btn btn-primary btn-sm" id="cve-goto-analyze-btn"
            onclick="ViewCve._showTab('analyze')" style="display:none;">
            Analizar seleccionadas con IA
          </button>
        </div>
      </div>
      <div id="cve-table-wrap"></div>
    `;
    if (this._cves.length > 0) this._renderCveTable();
  },

  async _fetchCves() {
    const days = parseInt(document.getElementById('cve-f-days')?.value || '7');
    const sev = document.getElementById('cve-f-sev')?.value;
    const kw = document.getElementById('cve-f-kw')?.value.trim();
    const wrap = document.getElementById('cve-table-wrap');
    if (wrap) wrap.innerHTML = '<p class="text-muted" style="font-size:13px;">Consultando NVD...</p>';
    try {
      const params = { days, severity: sev, max_results: 100 };
      if (kw) params.keyword = kw;
      const r = await Api.cve.search(params);
      this._cves = r.cves || [];
      this._selectedCves.clear();
      this._renderCveTable();
    } catch (e) {
      if (wrap) wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _renderCveTable() {
    const wrap = document.getElementById('cve-table-wrap');
    const header = document.getElementById('cve-results-header');
    const countEl = document.getElementById('cve-results-count');
    const selAllBtn = document.getElementById('cve-sel-all-btn');
    const goAnalyzeBtn = document.getElementById('cve-goto-analyze-btn');
    if (!wrap) return;

    if (header) header.style.display = 'flex';
    if (countEl) countEl.textContent = `${this._cves.length} CVEs encontradas`;
    if (selAllBtn) selAllBtn.style.display = this._cves.length > 0 ? '' : 'none';

    if (!this._cves.length) {
      wrap.innerHTML = '<div class="notice">No se encontraron CVEs con los filtros aplicados.</div>';
      return;
    }

    const sevColor = { CRITICAL: '#b91c1c', HIGH: '#c2410c', MEDIUM: '#d97706', LOW: '#15803d', UNKNOWN: '#9D9D9D' };
    const rows = this._cves.map(c => {
      const sel = this._selectedCves.has(c.id);
      const sc = c.cvss_score || 0;
      const sv = (c.cvss_severity || 'UNKNOWN').toUpperCase();
      return `
        <tr style="${sel ? 'background:var(--brand-purple-4);' : ''}">
          <td style="padding:8px 10px;width:32px;">
            <input type="checkbox" ${sel ? 'checked' : ''}
              onchange="ViewCve._toggleCve('${UI.esc(c.id)}', this.checked)">
          </td>
          <td style="padding:8px 10px;font-family:monospace;font-size:12px;white-space:nowrap;">
            <a href="https://nvd.nist.gov/vuln/detail/${UI.esc(c.id)}" target="_blank" rel="noopener"
               style="color:var(--brand-purple);">${UI.esc(c.id)}</a>
          </td>
          <td style="padding:8px 10px;text-align:center;">
            <span style="font-weight:700;font-size:14px;color:${sevColor[sv]||'#9D9D9D'};">${sc.toFixed(1)}</span>
            <div style="font-size:10px;color:${sevColor[sv]||'#9D9D9D'};font-weight:600;">${sv}</div>
          </td>
          <td style="padding:8px 10px;font-size:12px;max-width:340px;">
            <div style="overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;">
              ${UI.esc(c.description || '-')}
            </div>
            ${c.affected_products?.length ? `<div style="margin-top:4px;font-size:11px;color:var(--text-muted);">
              Productos: ${UI.esc(c.affected_products.slice(0,5).join(', '))}${c.affected_products.length>5?'…':''}
            </div>` : ''}
          </td>
          <td style="padding:8px 10px;font-size:11px;color:var(--text-muted);white-space:nowrap;">
            ${c.published ? c.published.slice(0,10) : '—'}
          </td>
          <td style="padding:8px 10px;font-size:11px;color:var(--text-muted);">${UI.esc(c.cvss_attack_vector||'')}</td>
        </tr>`;
    }).join('');

    wrap.innerHTML = `
      <div style="overflow-x:auto;">
        <table class="data" style="width:100%;font-size:13px;">
          <thead><tr>
            <th style="width:32px;padding:8px 10px;"></th>
            <th style="padding:8px 10px;">CVE ID</th>
            <th style="padding:8px 10px;text-align:center;">CVSS</th>
            <th style="padding:8px 10px;">Descripcion</th>
            <th style="padding:8px 10px;white-space:nowrap;">Publicada</th>
            <th style="padding:8px 10px;">Vector</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
    this._updateSelectionBar();
  },

  _toggleCve(id, checked) {
    if (checked) this._selectedCves.add(id);
    else this._selectedCves.delete(id);
    this._updateSelectionBar();
  },

  _selectAllCves() {
    this._cves.forEach(c => this._selectedCves.add(c.id));
    this._renderCveTable();
  },

  _updateSelectionBar() {
    const goBtn = document.getElementById('cve-goto-analyze-btn');
    if (goBtn) {
      const n = this._selectedCves.size;
      goBtn.style.display = n > 0 ? '' : 'none';
      goBtn.textContent = n > 0 ? `Analizar ${n} CVE${n>1?'s':''} con IA` : '';
    }
  },

  // ---- Analisis IA ----

  _assetSearchFilter: '',

  async _renderAnalyze() {
    const p = document.getElementById('cve-analyze-panel');
    if (!p) return;

    // Cargar activos si no los tenemos (limite alto para tener todo el inventario)
    if (!this._assets.length) {
      try {
        this._assets = await Api.assets.list({ limit: 5000 });
      } catch (e) { this._assets = []; }
    }

    const cfg   = this._config || {};
    const selCveIds = [...this._selectedCves];

    p.innerHTML = `
      <!-- Seleccion de activos -->
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px;">
          <h4 style="margin:0;font-size:14px;font-weight:700;">Activos a evaluar</h4>
          <span id="analyze-asset-sel-count" style="font-size:12px;color:var(--text-muted);
                background:var(--bg-3);padding:2px 8px;border-radius:10px;">
            0 seleccionados
          </span>
          <span style="flex:1;"></span>
          <button class="btn btn-sm" onclick="ViewCve._selectAllAnalyzeAssets()">Todos</button>
          <button class="btn btn-sm" onclick="ViewCve._selectTaggedAssets()"
                  title="Solo activos con software tags configurados">Con software tags</button>
          <button class="btn btn-sm" onclick="ViewCve._clearAnalyzeAssets()">Ninguno</button>
        </div>
        <input id="analyze-asset-search" class="input"
               placeholder="Buscar activo por nombre, tipo o categoria..."
               oninput="ViewCve._filterAnalyzeAssets(this.value)"
               style="margin-bottom:10px;width:100%;max-width:400px;">
        <p style="font-size:11px;color:var(--text-muted);margin:0 0 8px;">
          Los activos con <span style="background:#EDE9FE;color:#6D28D9;padding:1px 5px;border-radius:3px;font-size:10px;">tags</span>
          tienen software identificado y obtienen mejores resultados de escaneo.
          Si no seleccionas ninguno, se usan los primeros 50.
        </p>
        <div id="analyze-asset-list"
             style="max-height:260px;overflow-y:auto;
                    display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:4px;">
          ${this._renderAssetCheckboxes()}
        </div>
      </div>

      <!-- Parametros + botones de escaneo -->
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;align-items:flex-end;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
          <div>
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Severidad minima</label>
            <select id="analyze-sev" class="input" style="width:130px;">
              ${['CRITICAL','HIGH','MEDIUM','LOW','ALL'].map(s =>
                `<option value="${s}" ${(cfg.default_severity||'HIGH')===s?'selected':''}>${s}</option>`
              ).join('')}
            </select>
          </div>
          <div>
            <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px;">Ventana (dias)</label>
            <input type="number" id="analyze-days" class="input" min="1" max="90"
                   value="${cfg.default_days || 7}" style="width:80px;">
          </div>
          <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer;margin-bottom:2px;">
            <input type="checkbox" id="analyze-skip-heuristic"
                   style="accent-color:var(--brand-purple);">
            Forzar analisis de todos los pares
            <span style="color:var(--text-muted);">(mas lento)</span>
          </label>
        </div>

        <!-- Boton principal: escaneo automatico -->
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <button class="btn btn-primary" id="cve-autoscan-btn" onclick="ViewCve._runAutoScan()"
                  style="font-size:14px;padding:10px 22px;font-weight:700;">
            Escanear CVEs de mis activos
          </button>
          <div style="font-size:12px;color:var(--text-muted);max-width:340px;">
            Busca en NVD las CVEs vigentes que afectan a tus activos y analiza el impacto con IA.
            Mismo proceso que el escaneo automatico programado.
          </div>
        </div>

        <!-- Analizar CVEs especificos del Monitor (opcional) -->
        ${selCveIds.length > 0 ? `
        <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border);">
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">
            O analizar estas CVEs especificas seleccionadas del Monitor:
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px;">
            ${selCveIds.slice(0,15).map(id => `
              <span style="font-size:11px;background:var(--bg-3);border:1px solid var(--border);
                           border-radius:4px;padding:2px 8px;font-family:var(--font-mono);
                           display:inline-flex;align-items:center;gap:4px;">
                ${UI.esc(id)}
                <button onclick="ViewCve._removeSelectedCve('${UI.esc(id)}')"
                        style="border:none;background:none;cursor:pointer;color:var(--text-muted);
                               padding:0;font-size:13px;line-height:1;margin-left:2px;">x</button>
              </span>`).join('')}
            ${selCveIds.length > 15 ? `<span style="font-size:11px;color:var(--text-muted);align-self:center;">+${selCveIds.length-15} mas</span>` : ''}
          </div>
          <button class="btn" id="cve-run-specific-btn" onclick="ViewCve._runSpecificAnalysis()">
            Analizar ${selCveIds.length} CVE${selCveIds.length>1?'s':''} seleccionados
          </button>
        </div>` : `
        <div style="margin-top:10px;font-size:12px;color:var(--text-subtle);">
          Tambien puedes seleccionar CVEs concretas en la pestana <strong>Monitor CVEs</strong>
          y analizarlas aqui especificamente.
        </div>`}

        <div id="cve-analyze-status" style="margin-top:12px;display:none;"></div>
      </div>

      <!-- Resultados -->
      <div id="cve-analyze-results"></div>
    `;

    this._updateAnalyzeAssetCount();
  },

  _renderAssetCheckboxes(filter) {
    const f = ((filter !== undefined ? filter : this._assetSearchFilter) || '').toLowerCase();
    const assets = f
      ? this._assets.filter(a =>
          (a.name || '').toLowerCase().includes(f) ||
          (a.asset_type || '').toLowerCase().includes(f) ||
          (a.category || '').toLowerCase().includes(f) ||
          (a.software_tags || []).some(t => t.toLowerCase().includes(f))
        )
      : this._assets;

    if (!assets.length) return '<div style="font-size:13px;color:var(--text-muted);padding:10px;grid-column:1/-1;">Sin activos que coincidan con la busqueda.</div>';

    return assets.slice(0, 300).map(a => {
      const tags    = (a.software_tags || []).slice(0, 4);
      const isSel   = this._selectedAssets.has(a.id);
      return `
      <label style="display:flex;align-items:flex-start;gap:8px;padding:6px 8px;cursor:pointer;
             border-radius:6px;transition:background .1s;
             background:${isSel ? 'rgba(89,0,141,.08)' : 'transparent'};
             border:1px solid ${isSel ? 'var(--brand-purple)' : 'transparent'};">
        <input type="checkbox" class="analyze-asset-chk" value="${a.id}"
               ${isSel ? 'checked' : ''}
               onchange="ViewCve._toggleAnalyzeAsset(${a.id}, this.checked)"
               style="accent-color:var(--brand-purple);margin-top:3px;flex-shrink:0;">
        <div style="min-width:0;flex:1;">
          <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
            ${UI.esc(a.name || '')}
          </div>
          <div style="display:flex;gap:3px;flex-wrap:wrap;margin-top:2px;">
            <span style="font-size:10px;background:var(--bg-2);padding:1px 5px;border-radius:3px;
                         color:var(--text-muted);white-space:nowrap;">
              ${UI.esc((a.asset_type || '').replace(/_/g, ' '))}
            </span>
            ${tags.map(t => `
              <span style="font-size:10px;background:#EDE9FE;color:#6D28D9;
                           padding:1px 5px;border-radius:3px;white-space:nowrap;">
                ${UI.esc(t)}
              </span>`).join('')}
            ${!tags.length ? '<span style="font-size:10px;color:var(--text-subtle);">sin tags</span>' : ''}
          </div>
        </div>
      </label>`;
    }).join('');
  },

  _filterAnalyzeAssets(val) {
    this._assetSearchFilter = val;
    const list = document.getElementById('analyze-asset-list');
    if (list) list.innerHTML = this._renderAssetCheckboxes(val);
    // Re-attach change handlers (they're inline so no action needed)
  },

  _toggleAnalyzeAsset(id, checked) {
    if (checked) this._selectedAssets.add(id);
    else this._selectedAssets.delete(id);
    this._updateAnalyzeAssetCount();
    const lbl = document.querySelector(`.analyze-asset-chk[value="${id}"]`)?.closest('label');
    if (lbl) {
      lbl.style.background = checked ? 'rgba(89,0,141,.08)' : 'transparent';
      lbl.style.borderColor = checked ? 'var(--brand-purple)' : 'transparent';
    }
  },

  _selectAllAnalyzeAssets() {
    this._assets.forEach(a => this._selectedAssets.add(a.id));
    const list = document.getElementById('analyze-asset-list');
    if (list) list.innerHTML = this._renderAssetCheckboxes(this._assetSearchFilter);
    this._updateAnalyzeAssetCount();
  },

  _selectTaggedAssets() {
    this._assets.filter(a => (a.software_tags || []).length > 0)
      .forEach(a => this._selectedAssets.add(a.id));
    const list = document.getElementById('analyze-asset-list');
    if (list) list.innerHTML = this._renderAssetCheckboxes(this._assetSearchFilter);
    this._updateAnalyzeAssetCount();
  },

  _clearAnalyzeAssets() {
    this._selectedAssets.clear();
    const list = document.getElementById('analyze-asset-list');
    if (list) list.innerHTML = this._renderAssetCheckboxes(this._assetSearchFilter);
    this._updateAnalyzeAssetCount();
  },

  _updateAnalyzeAssetCount() {
    const el = document.getElementById('analyze-asset-sel-count');
    if (el) {
      const n = this._selectedAssets.size;
      el.textContent = n === 0 ? 'todos los activos (por defecto)' : `${n} seleccionado${n !== 1 ? 's' : ''}`;
      el.style.background = n > 0 ? 'rgba(89,0,141,.1)' : 'var(--bg-3)';
      el.style.color = n > 0 ? 'var(--brand-purple)' : 'var(--text-muted)';
    }
  },

  _removeSelectedCve(id) {
    this._selectedCves.delete(id);
    this._renderAnalyze();
  },

  _getAnalyzeParams() {
    return {
      assetIds:      [...this._selectedAssets],
      days:          parseInt(document.getElementById('analyze-days')?.value || '7'),
      severity:      document.getElementById('analyze-sev')?.value || 'HIGH',
      skipHeuristic: document.getElementById('analyze-skip-heuristic')?.checked || false,
    };
  },

  _setAnalyzeLoading(msg) {
    const statusEl = document.getElementById('cve-analyze-status');
    const resultsEl = document.getElementById('cve-analyze-results');
    if (statusEl) {
      statusEl.style.display = '';
      statusEl.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;font-size:13px;color:var(--text-muted);">
          <div class="spinner" style="width:18px;height:18px;border-width:2px;"></div>
          ${UI.esc(msg)}
        </div>`;
    }
    if (resultsEl) resultsEl.innerHTML = '';
  },

  async _runAutoScan() {
    const btn = document.getElementById('cve-autoscan-btn');
    const statusEl = document.getElementById('cve-analyze-status');
    const { assetIds, days, severity, skipHeuristic } = this._getAnalyzeParams();
    const nAssets = assetIds.length || 'todos los';

    if (btn) { btn.disabled = true; btn.textContent = 'Escaneando...'; }
    this._setAnalyzeLoading(
      `Buscando CVEs en NVD (ultimos ${days} dias, severidad ${severity}) y analizando contra ${nAssets} activos...`
    );

    try {
      const r = await Api.cve.autoScan({
        asset_ids: assetIds,
        days,
        severity,
        skip_heuristic: skipHeuristic,
        max_cves: 50,
      });
      this._analysisResults = r.results || [];
      if (statusEl) statusEl.style.display = 'none';
      if (r.message && !r.results?.length) {
        document.getElementById('cve-analyze-results').innerHTML =
          `<div class="notice">${UI.esc(r.message)}</div>`;
        return;
      }
      this._renderAnalysisResults(r, { cves_found: r.cves_found });
    } catch (e) {
      if (statusEl) statusEl.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Escanear CVEs de mis activos'; }
    }
  },

  async _runSpecificAnalysis() {
    const btn = document.getElementById('cve-run-specific-btn');
    const statusEl = document.getElementById('cve-analyze-status');
    const rawIds = [...this._selectedCves].map(s => s.trim().toUpperCase()).filter(s => s.startsWith('CVE-'));
    if (!rawIds.length) { UI.toast('No hay CVEs seleccionadas en el Monitor', 'warn'); return; }
    if (rawIds.length > 20) { UI.toast('Maximo 20 CVEs por analisis especifico', 'error'); return; }

    const { assetIds, skipHeuristic } = this._getAnalyzeParams();

    if (btn) { btn.disabled = true; btn.textContent = 'Analizando...'; }
    this._setAnalyzeLoading(
      `Analizando ${rawIds.length} CVE${rawIds.length>1?'s':''} seleccionadas contra ${assetIds.length || 'todos los'} activos...`
    );

    try {
      const r = await Api.cve.analyze({ cve_ids: rawIds, asset_ids: assetIds, skip_heuristic: skipHeuristic });
      this._analysisResults = r.results || [];
      if (statusEl) statusEl.style.display = 'none';
      this._renderAnalysisResults(r, {});
    } catch (e) {
      if (statusEl) statusEl.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = `Analizar ${rawIds.length} CVEs seleccionados`; }
    }
  },

  _renderAnalysisResults(r, meta) {
    const el = document.getElementById('cve-analyze-results');
    if (!el) return;

    const results = r.results || [];
    if (!results.length) {
      el.innerHTML = `
        <div class="card">
          <p style="font-size:13px;color:var(--text-muted);margin:0;">
            No se encontraron pares CVE-Activo que superen el umbral de coincidencia heuristico.
            Activa <em>Analizar todos los pares</em> para forzar el analisis completo.
          </p>
        </div>`;
      return;
    }

    const riskColors = { 5:'#b91c1c', 4:'#c2410c', 3:'#d97706', 2:'#15803d', 1:'#15803d' };
    const riskLabels = { 5:'Critico', 4:'Alto', 3:'Medio', 2:'Bajo', 1:'Muy bajo' };
    const priColors = { alta:'#b91c1c', media:'#d97706', baja:'#15803d' };

    const affectsOnly = results.filter(r => r.analysis?.afecta_activo !== false);
    const notAffects = results.filter(r => r.analysis?.afecta_activo === false);

    const cvesMeta = meta || {};
    let html = `
      <div style="display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:12px;">
        <h3 style="margin:0;font-size:15px;">
          Resultados del analisis
        </h3>
        ${cvesMeta.cves_found ? `<span style="font-size:12px;color:var(--text-muted);">
          ${cvesMeta.cves_found} CVEs encontradas en NVD
        </span>` : ''}
        <span style="font-size:12px;color:var(--text-muted);">${results.length} par${results.length>1?'es':''} evaluados</span>
        <span style="color:#b91c1c;font-weight:600;font-size:12px;">${affectsOnly.length} con impacto detectado</span>
        <span style="font-size:12px;color:var(--text-muted);">/ ${notAffects.length} sin impacto</span>
      </div>`;

    if (affectsOnly.length === 0) {
      html += `<div class="card" style="margin-bottom:12px;"><p style="font-size:13px;margin:0;color:var(--text-muted);">
        La IA no ha detectado impacto directo en los activos evaluados con las CVEs seleccionadas.
        Revisa la seccion de baja confianza a continuacion.
      </p></div>`;
    }

    // Ordenar por riesgo residual descendente
    const sorted = [...affectsOnly].sort((a, b) =>
      (b.analysis?.riesgo_residual || 0) - (a.analysis?.riesgo_residual || 0));

    sorted.forEach((item, idx) => {
      const a = item.analysis || {};
      const cve = item.cve || {};
      const inh = a.riesgo_inherente || 1;
      const res = a.riesgo_residual || 1;
      const confianza = a.confianza || 'baja';
      const actions = a.acciones_mitigacion || [];
      const controls = a.controles_relevantes_detectados || [];
      const recCreate = a.crear_riesgo_recomendado;

      html += `
        <div class="card" style="margin-bottom:12px;border-left:4px solid ${riskColors[res]||'#9D9D9D'};">
          <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:12px;">
            <div style="flex:1;">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
                <span style="font-family:monospace;font-weight:700;color:var(--brand-purple);">${UI.esc(item.cve_id)}</span>
                <span style="font-size:11px;color:var(--text-muted);">→</span>
                <span style="font-weight:600;">${UI.esc(item.asset_name)}</span>
                <span class="badge badge-muted" style="font-size:10px;">${UI.esc(item.asset_type.replace(/_/g,' '))}</span>
                <span class="badge" style="font-size:10px;background:${confianza==='alta'?'var(--risk-low)':confianza==='media'?'#d97706':'#9D9D9D'};color:#fff;">
                  Confianza: ${confianza}
                </span>
              </div>
              <div style="font-size:12px;color:var(--text-muted);">
                CVSS ${(cve.cvss_score||0).toFixed(1)} (${cve.cvss_severity||'?'}) — ${UI.esc((cve.description||'').slice(0,120))}…
              </div>
            </div>
            <div style="text-align:center;min-width:80px;">
              <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">Riesgo residual</div>
              <div style="font-size:28px;font-weight:800;color:${riskColors[res]||'#9D9D9D'};line-height:1;">${res}</div>
              <div style="font-size:11px;color:${riskColors[res]||'#9D9D9D'};font-weight:600;">${riskLabels[res]||'?'}</div>
            </div>
          </div>

          <!-- Metricas -->
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px;">
            <div style="background:var(--bg-2);border-radius:8px;padding:10px 12px;text-align:center;">
              <div style="font-size:11px;color:var(--text-muted);">Riesgo inherente</div>
              <div style="font-size:20px;font-weight:700;color:${riskColors[inh]||'#9D9D9D'};">${inh}</div>
              <div style="font-size:10px;color:var(--text-muted);">${UI.esc(a.riesgo_inherente_justificacion||'').slice(0,60)}</div>
            </div>
            <div style="background:var(--bg-2);border-radius:8px;padding:10px 12px;text-align:center;">
              <div style="font-size:11px;color:var(--text-muted);">Cobertura controles</div>
              <div style="font-size:14px;font-weight:700;margin-top:4px;color:${
                a.cobertura_controles==='suficiente'?'#15803d':
                a.cobertura_controles==='parcial'?'#d97706':'#b91c1c'};">
                ${UI.esc(a.cobertura_controles||'ninguna')}
              </div>
              ${controls.length ? `<div style="font-size:10px;color:var(--text-muted);margin-top:2px;">${UI.esc(controls.slice(0,2).join(', '))}</div>` : ''}
            </div>
            <div style="background:var(--bg-2);border-radius:8px;padding:10px 12px;text-align:center;">
              <div style="font-size:11px;color:var(--text-muted);">Riesgo residual</div>
              <div style="font-size:20px;font-weight:700;color:${riskColors[res]||'#9D9D9D'};">${res}</div>
              <div style="font-size:10px;color:var(--text-muted);">${UI.esc(a.riesgo_residual_justificacion||'').slice(0,60)}</div>
            </div>
          </div>

          <!-- Justificacion -->
          <div style="font-size:12px;margin-bottom:10px;padding:8px 12px;background:var(--bg-2);border-radius:6px;">
            <strong>Por que afecta:</strong> ${UI.esc(a.justificacion_afectacion||'')}
          </div>

          <!-- Acciones de mitigacion -->
          ${actions.length ? `
          <div style="margin-bottom:10px;">
            <div style="font-size:12px;font-weight:600;margin-bottom:6px;">Acciones de mitigacion propuestas:</div>
            ${actions.map(ac => `
              <div style="display:flex;align-items:flex-start;gap:8px;padding:6px 10px;
                  background:var(--bg-2);border-radius:6px;margin-bottom:4px;font-size:12px;">
                <span style="background:${priColors[ac.prioridad]||'#9D9D9D'};color:#fff;
                    border-radius:4px;padding:1px 6px;font-size:10px;white-space:nowrap;margin-top:1px;">
                  ${UI.esc(ac.prioridad||'?')}
                </span>
                ${ac.control_iso ? `<span style="font-family:monospace;font-size:11px;color:var(--brand-purple);
                    white-space:nowrap;">${UI.esc(ac.control_iso)}</span>` : ''}
                <span>${UI.esc(ac.accion||'')}</span>
              </div>`).join('')}
          </div>` : ''}

          <!-- Boton crear riesgo -->
          <div style="display:flex;justify-content:flex-end;gap:8px;">
            ${recCreate ? `<span style="font-size:11px;color:var(--brand-purple);font-weight:600;align-self:center;">
              Riesgo recomendado
            </span>` : ''}
            <button class="btn btn-sm ${recCreate?'btn-primary':''}"
              onclick="ViewCve._createRisk(${idx})">
              Crear riesgo en RiskHub
            </button>
          </div>
        </div>`;
    });

    // Seccion no afectados colapsada
    if (notAffects.length > 0) {
      html += `
        <details style="margin-top:8px;">
          <summary style="font-size:13px;color:var(--text-muted);cursor:pointer;padding:8px 12px;
              background:var(--bg-2);border-radius:8px;">
            ${notAffects.length} par${notAffects.length>1?'es':''} sin impacto detectado (haz clic para ver)
          </summary>
          <div style="margin-top:8px;padding:8px 12px;font-size:12px;color:var(--text-muted);">
            ${notAffects.map(item =>
              `<div style="padding:4px 0;">${UI.esc(item.cve_id)} → ${UI.esc(item.asset_name)}:
              ${UI.esc(item.analysis?.justificacion_afectacion||'')}</div>`
            ).join('')}
          </div>
        </details>`;
    }

    el.innerHTML = html;
  },

  async _createRisk(idx) {
    const item = this._analysisResults[idx];
    if (!item) return;
    try {
      const r = await Api.cve.createRisk({
        cve_id: item.cve_id,
        asset_id: item.asset_id,
        analysis: item.analysis,
        cve_data: item.cve,
      });
      UI.toast(`${r.message}`, 'success');
    } catch (e) { UI.toast(e.message, 'error'); }
  },
};
