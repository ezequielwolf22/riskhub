/* Vista de hallazgos externos (Nessus, Qualys, Burp, OpenVAS). */
const ViewExternalFindings = (() => {

  let _filters = { severity: '', source: '', status: '' };

  function _sevBadge(sev) {
    const m = { CRITICAL: ['#FEE2E2','#a83232'], HIGH: ['#FEF0E3','#c25a1f'],
                MEDIUM: ['#FFFDE7','#795500'], LOW: ['#E8F5E9','#2e7d32'] };
    const [bg, col] = m[sev] || ['#f0f0f0','#666'];
    return `<span style="background:${bg};color:${col};padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">${sev}</span>`;
  }

  function _importModal() {
    UI.modal(`
      <h3 style="margin:0 0 16px;color:var(--brand-purple);">Importar hallazgos</h3>
      <p style="font-size:13px;color:#666;margin-bottom:12px;">
        Sube el archivo de resultados de tu herramienta de seguridad.
        Formatos soportados: <strong>Nessus (.nessus)</strong>, <strong>Qualys XML</strong>,
        <strong>Burp Suite XML</strong>, <strong>OpenVAS XML</strong>.
      </p>
      <div style="display:grid;gap:12px;">
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">Archivo *</label>
          <input id="fi-file" type="file" accept=".nessus,.xml" style="width:100%;">
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">
            Fuente (auto-detectado si se deja vacío)
          </label>
          <select id="fi-source" class="input-field" style="width:100%;">
            <option value="">Auto-detectar</option>
            <option value="nessus">Nessus</option>
            <option value="qualys">Qualys</option>
            <option value="burp">Burp Suite</option>
            <option value="openvas">OpenVAS / GVM</option>
          </select>
        </div>
        <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;">
          <input type="checkbox" id="fi-auto-risks" checked>
          Crear riesgos automáticamente para hallazgos HIGH/CRITICAL
        </label>
      </div>
      <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;">
        <button onclick="UI.closeModal()" class="btn-outline">Cancelar</button>
        <button onclick="ViewExternalFindings._submitImport()" class="btn-primary">Importar</button>
      </div>`);
  }

  async function _submitImport() {
    const file = document.getElementById('fi-file').files[0];
    if (!file) { UI.toast('Selecciona un archivo', 'error'); return; }

    const fd = new FormData();
    fd.append('file', file);
    const source = document.getElementById('fi-source').value;
    if (source) fd.append('source', source);
    const autoRisks = document.getElementById('fi-auto-risks').checked;
    fd.append('auto_create_risks', autoRisks);

    UI.toast('Importando...', 'info');
    try {
      const r = await Api.findings.import(fd);
      UI.closeModal();
      const s = r.stats || {};
      UI.toast(
        `Importado: ${s.created || 0} nuevos, ${s.duplicates || 0} duplicados, ${s.risks_created || 0} riesgos creados`,
        'success'
      );
      _load();
    } catch (e) {
      UI.toast('Error importando: ' + e.message, 'error');
    }
  }

  async function _resolve(id) {
    try {
      await Api.findings.resolve(id);
      UI.toast('Marcado como resuelto', 'success');
      _load();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _loadSummary() {
    try {
      const s = await Api.findings.summary();
      const bySev = s.by_severity || {};
      const total = s.total || 0;
      const el = document.getElementById('fi-summary');
      if (!el) return;
      el.innerHTML = `
        <div style="display:flex;gap:12px;flex-wrap:wrap;">
          ${['CRITICAL','HIGH','MEDIUM','LOW'].map(sev => {
            const cnt = bySev[sev] || 0;
            const colors = { CRITICAL: ['#FEE2E2','#a83232'], HIGH: ['#FEF0E3','#c25a1f'],
                             MEDIUM: ['#FFFDE7','#795500'], LOW: ['#E8F5E9','#2e7d32'] };
            const [bg, col] = colors[sev];
            return `<div style="background:${bg};border-radius:8px;padding:12px 18px;text-align:center;min-width:90px;">
              <div style="font-size:22px;font-weight:700;color:${col};">${cnt}</div>
              <div style="font-size:11px;color:${col};text-transform:uppercase;">${sev}</div>
            </div>`;
          }).join('')}
          <div style="background:#f5f5f5;border-radius:8px;padding:12px 18px;text-align:center;min-width:90px;">
            <div style="font-size:22px;font-weight:700;color:var(--brand-purple);">${total}</div>
            <div style="font-size:11px;color:#9d9d9d;text-transform:uppercase;">Total</div>
          </div>
        </div>`;
    } catch (_) {}
  }

  async function _load() {
    const tbody = document.getElementById('fi-tbody');
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:24px;color:#9d9d9d;">Cargando...</td></tr>`;

    try {
      const q = { limit: 100 };
      if (_filters.severity) q.severity = _filters.severity;
      if (_filters.source) q.source = _filters.source;
      if (_filters.status) q.status = _filters.status;

      const data = await Api.findings.list(q);
      await _loadSummary();

      const items = data.items || [];
      if (!items.length) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px;color:#9d9d9d;">
          No hay hallazgos. Importa resultados de Nessus, Qualys, Burp o OpenVAS.</td></tr>`;
        return;
      }

      tbody.innerHTML = items.map(f => `
        <tr style="border-bottom:1px solid #f0f0f0;${f.status === 'resolved' ? 'opacity:.6;' : ''}">
          <td style="padding:10px 12px;">${_sevBadge(f.severity)}</td>
          <td style="padding:10px 12px;">
            <div style="font-weight:500;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
                 title="${UI.esc(f.title)}">${UI.esc(f.title)}</div>
            ${f.cve_id ? `<div style="font-size:11px;color:var(--brand-orange);">CVE: ${UI.esc(f.cve_id)}</div>` : ''}
          </td>
          <td style="padding:10px 12px;font-size:12px;color:#666;">
            <span style="background:#f0f0f0;padding:2px 6px;border-radius:4px;">${UI.esc(f.source)}</span>
          </td>
          <td style="padding:10px 12px;font-size:12px;color:#666;">${UI.esc(f.affected_host || '—')}</td>
          <td style="padding:10px 12px;font-size:12px;">
            ${f.asset_id ? `<span style="color:var(--brand-purple);">Activo #${f.asset_id}</span>` : '<span style="color:#bbb;">Sin enlazar</span>'}
            ${f.risk_id ? `<br><span style="color:var(--risk-high);font-size:11px;">Riesgo #${f.risk_id}</span>` : ''}
          </td>
          <td style="padding:10px 12px;">
            <span style="background:${f.status === 'resolved' ? '#E8F5E9' : '#FEF0E3'};
                         color:${f.status === 'resolved' ? '#2e7d32' : '#c25a1f'};
                         padding:2px 8px;border-radius:10px;font-size:11px;">
              ${f.status === 'resolved' ? 'Resuelto' : 'Abierto'}
            </span>
          </td>
          <td style="padding:10px 12px;">
            ${f.status !== 'resolved' ? `
              <button onclick="ViewExternalFindings._resolve(${f.id})"
                      class="btn-outline" style="font-size:12px;padding:3px 8px;">
                Resolver
              </button>` : ''}
          </td>
        </tr>`).join('');
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="7" style="color:var(--risk-critical);padding:16px;">Error: ${UI.esc(e.message)}</td></tr>`;
    }
  }

  function _applyFilters() {
    _filters.severity = document.getElementById('fi-filter-sev').value;
    _filters.source = document.getElementById('fi-filter-src').value;
    _filters.status = document.getElementById('fi-filter-status').value;
    _load();
  }

  async function render(el) {
    el.innerHTML = `
      <div style="max-width:1100px;margin:0 auto;padding:24px 0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:12px;">
          <div>
            <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0;">
              Hallazgos Externos
            </h1>
            <p style="color:#9d9d9d;font-size:13px;margin:4px 0 0;">
              Nessus, Qualys, Burp Suite, OpenVAS — auto-correlación con activos y riesgos
            </p>
          </div>
          <button onclick="ViewExternalFindings._importModal()" class="btn-primary">
            + Importar hallazgos
          </button>
        </div>

        <!-- Resumen -->
        <div id="fi-summary" style="margin-bottom:16px;"></div>

        <!-- Filtros -->
        <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:14px;
                    margin-bottom:16px;display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;">
          <div>
            <label style="font-size:11px;color:#9d9d9d;display:block;margin-bottom:4px;">Severidad</label>
            <select id="fi-filter-sev" class="input-field" style="width:120px;">
              <option value="">Todas</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
          <div>
            <label style="font-size:11px;color:#9d9d9d;display:block;margin-bottom:4px;">Fuente</label>
            <select id="fi-filter-src" class="input-field" style="width:120px;">
              <option value="">Todas</option>
              <option value="nessus">Nessus</option>
              <option value="qualys">Qualys</option>
              <option value="burp">Burp</option>
              <option value="openvas">OpenVAS</option>
            </select>
          </div>
          <div>
            <label style="font-size:11px;color:#9d9d9d;display:block;margin-bottom:4px;">Estado</label>
            <select id="fi-filter-status" class="input-field" style="width:110px;">
              <option value="">Todos</option>
              <option value="open">Abierto</option>
              <option value="resolved">Resuelto</option>
            </select>
          </div>
          <button onclick="ViewExternalFindings._applyFilters()" class="btn-primary" style="padding:6px 14px;">Filtrar</button>
        </div>

        <!-- Tabla -->
        <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;overflow:hidden;">
          <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
              <tr style="background:var(--brand-purple);color:#fff;">
                <th style="padding:10px 12px;text-align:left;font-weight:600;">Severidad</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">Título / CVE</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">Fuente</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">Host afectado</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">Activo / Riesgo</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">Estado</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">Acción</th>
              </tr>
            </thead>
            <tbody id="fi-tbody">
              <tr><td colspan="7" style="text-align:center;padding:24px;color:#9d9d9d;">Cargando...</td></tr>
            </tbody>
          </table>
        </div>
      </div>`;

    await _load();
    await _loadSummary();
  }

  return { render, _importModal, _submitImport, _resolve, _applyFilters, _load };
})();
