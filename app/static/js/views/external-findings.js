/* Vista de hallazgos externos (Nessus, Qualys, Burp, OpenVAS). */
const ViewExternalFindings = (() => {

  let _filters = { severity: '', source: '', status: '', source_document: '' };
  let _assetsCache = null;
  let _sourceDocsCache = [];

  const SOURCE_LABELS = {
    nessus: 'Nessus', qualys: 'Qualys', burp: 'Burp', openvas: 'OpenVAS',
    architecture_review: t('ext_findings.arch_review_src'),
  };

  async function _getAssets() {
    if (_assetsCache) return _assetsCache;
    try { _assetsCache = await Api.assets.list(); } catch (_) { _assetsCache = []; }
    return _assetsCache;
  }

  function _sevBadge(sev) {
    const m = { CRITICAL: ['#FEE2E2','#a83232'], HIGH: ['#FEF0E3','#c25a1f'],
                MEDIUM: ['#FFFDE7','#795500'], LOW: ['#E8F5E9','#2e7d32'] };
    const [bg, col] = m[sev] || ['#f0f0f0','#666'];
    return `<span style="background:${bg};color:${col};padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">${sev}</span>`;
  }

  function _importModal() {
    UI.openModal(`
      <h3 style="margin:0 0 16px;color:var(--brand-purple);">${t('ext_findings.import_title')}</h3>
      <p style="font-size:13px;color:#666;margin-bottom:12px;">
        ${t('ext_findings.import_desc')}
      </p>
      <div style="display:grid;gap:12px;">
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('ext_findings.file_label')}</label>
          <input id="fi-file" type="file" accept=".nessus,.xml" style="width:100%;">
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">${t('ext_findings.source_auto')}</label>
          <select id="fi-source" class="input-field" style="width:100%;">
            <option value="">${t('ext_findings.auto_detect')}</option>
            <option value="nessus">Nessus</option>
            <option value="qualys">Qualys</option>
            <option value="burp">Burp Suite</option>
            <option value="openvas">OpenVAS / GVM</option>
          </select>
        </div>
        <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;">
          <input type="checkbox" id="fi-auto-risks" checked>
          ${t('ext_findings.auto_create_risks')}
        </label>
      </div>
      <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;">
        <button onclick="UI.closeModal()" class="btn-outline">${t('ext_findings.cancel')}</button>
        <button onclick="ViewExternalFindings._submitImport()" class="btn-primary">${t('ext_findings.import_btn')}</button>
      </div>`);
  }

  async function _submitImport() {
    const file = document.getElementById('fi-file').files[0];
    if (!file) { UI.toast(t('ext_findings.select_file'), 'error'); return; }

    const fd = new FormData();
    fd.append('file', file);
    const source = document.getElementById('fi-source').value;
    if (source) fd.append('source', source);
    const autoRisks = document.getElementById('fi-auto-risks').checked;
    fd.append('auto_create_risks', autoRisks);

    UI.toast(t('ext_findings.importing'), 'info');
    try {
      const r = await Api.findings.import(fd);
      UI.closeModal();
      const s = r.stats || {};
      UI.toast(t('ext_findings.import_result', {created: s.created || 0, duplicates: s.duplicates || 0, risks: s.risks_created || 0}), 'success');
      _load();
    } catch (e) {
      UI.toast(t('ext_findings.import_error', {msg: e.message}), 'error');
    }
  }

  async function _resolve(id) {
    try {
      await Api.findings.resolve(id);
      UI.toast(t('ext_findings.marked_resolved'), 'success');
      _load();
    } catch (e) {
      UI.toast(t('ext_findings.error_generic', {msg: e.message}), 'error');
    }
  }

  async function _transferToIncident(id) {
    try {
      const r = await Api.findings.createIncident(id);
      UI.toast(t('ext_findings.incident_created', {code: r.incident_code}), 'success');
      _load();
    } catch (e) {
      UI.toast(t('ext_findings.error_generic', {msg: e.message}), 'error');
    }
  }

  async function _transferToRiskModal(id) {
    const assets = await _getAssets();
    if (!assets.length) {
      UI.toast(t('ext_findings.no_assets'), 'error');
      return;
    }
    UI.openModal(`
      <h3 style="margin:0 0 16px;color:var(--brand-purple);">${t('ext_findings.transfer_to_risk')}</h3>
      <p style="font-size:13px;color:#666;margin-bottom:12px;">
        ${t('ext_findings.transfer_desc')}
      </p>
      <select id="fi-risk-asset" class="input-field" style="width:100%;">
        ${assets.map(a => `<option value="${a.id}">${UI.esc(a.name)}</option>`).join('')}
      </select>
      <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;">
        <button onclick="UI.closeModal()" class="btn-outline">${t('ext_findings.cancel')}</button>
        <button onclick="ViewExternalFindings._submitTransferToRisk(${id})" class="btn-primary">${t('ext_findings.create_risk')}</button>
      </div>`);
  }

  async function _submitTransferToRisk(id) {
    const assetId = parseInt(document.getElementById('fi-risk-asset').value, 10);
    try {
      const r = await Api.findings.createRisk(id, assetId);
      UI.closeModal();
      UI.toast(t('ext_findings.risk_created', {code: r.risk_code}), 'success');
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
            <div style="font-size:11px;color:#9d9d9d;text-transform:uppercase;">${t('ext_findings.total')}</div>
          </div>
        </div>`;
    } catch (_) {}
  }

  async function _load() {
    const tbody = document.getElementById('fi-tbody');
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:24px;color:#9d9d9d;">${t('ext_findings.loading')}</td></tr>`;

    try {
      const q = { limit: 100 };
      if (_filters.severity) q.severity = _filters.severity;
      if (_filters.source) q.source = _filters.source;
      if (_filters.status) q.status = _filters.status;
      if (_filters.source_document) q.source_document = _filters.source_document;

      const data = await Api.findings.list(q);
      await _loadSummary();
      await _loadSourceDocuments();

      const items = data.items || [];
      if (!items.length) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px;color:#9d9d9d;">
          ${t('ext_findings.no_findings')}</td></tr>`;
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
            <span style="background:#f0f0f0;padding:2px 6px;border-radius:4px;">${UI.esc(SOURCE_LABELS[f.source] || f.source)}</span>
            ${f.source_document ? `<div style="font-size:10px;color:#9d9d9d;margin-top:2px;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${UI.esc(f.source_document)}">${UI.esc(f.source_document)}</div>` : ''}
          </td>
          <td style="padding:10px 12px;font-size:12px;color:#666;">${UI.esc(f.affected_host || '—')}</td>
          <td style="padding:10px 12px;font-size:12px;">
            ${f.asset_id ? `<span style="color:var(--brand-purple);">${t('ext_findings.asset_n', {id: f.asset_id})}</span>` : `<span style="color:#bbb;">${t('ext_findings.unlinked')}</span>`}
            ${f.risk_id ? `<br><a href="#/risks" style="color:var(--risk-high);font-size:11px;">${t('ext_findings.risk_n', {id: f.risk_id})}</a>` : ''}
            ${f.incident_id ? `<br><a href="#/incidents" style="color:var(--brand-orange);font-size:11px;">${t('ext_findings.incident_n', {id: f.incident_id})}</a>` : ''}
          </td>
          <td style="padding:10px 12px;">
            <span style="background:${f.status === 'resolved' ? '#E8F5E9' : '#FEF0E3'};
                         color:${f.status === 'resolved' ? '#2e7d32' : '#c25a1f'};
                         padding:2px 8px;border-radius:10px;font-size:11px;">
              ${f.status === 'resolved' ? t('ext_findings.resolved') : t('ext_findings.open')}
            </span>
          </td>
          <td style="padding:10px 12px;">
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              ${f.status !== 'resolved' ? `
                <button onclick="ViewExternalFindings._resolve(${f.id})"
                        class="btn-outline" style="font-size:12px;padding:3px 8px;">
                  ${t('ext_findings.btn_resolve')}
                </button>` : ''}
              ${!f.incident_id ? `
                <button onclick="ViewExternalFindings._transferToIncident(${f.id})"
                        class="btn-outline" style="font-size:12px;padding:3px 8px;">
                  ${t('ext_findings.btn_to_incident')}
                </button>` : ''}
              ${!f.risk_id ? `
                <button onclick="ViewExternalFindings._transferToRiskModal(${f.id})"
                        class="btn-outline" style="font-size:12px;padding:3px 8px;">
                  ${t('ext_findings.btn_to_risk')}
                </button>` : ''}
            </div>
          </td>
        </tr>`).join('');
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="7" style="color:var(--risk-critical);padding:16px;">${t('ext_findings.table_error', {msg: UI.esc(e.message)})}</td></tr>`;
    }
  }

  async function _loadSourceDocuments() {
    try {
      const r = await Api.findings.sourceDocuments();
      _sourceDocsCache = r.documents || [];
      const sel = document.getElementById('fi-filter-doc');
      if (!sel) return;
      sel.parentElement.style.display = _sourceDocsCache.length ? '' : 'none';
      const current = sel.value;
      sel.innerHTML = `<option value="">${t('ext_findings.f_all_m')}</option>` +
        _sourceDocsCache.map(d => `<option value="${UI.esc(d)}">${UI.esc(d)}</option>`).join('');
      sel.value = current;
    } catch (_) {}
  }

  function _applyFilters() {
    _filters.severity = document.getElementById('fi-filter-sev').value;
    _filters.source = document.getElementById('fi-filter-src').value;
    _filters.status = document.getElementById('fi-filter-status').value;
    const docSel = document.getElementById('fi-filter-doc');
    _filters.source_document = docSel ? docSel.value : '';
    _load();
  }

  async function render(el) {
    el.innerHTML = `
      <div style="max-width:1100px;margin:0 auto;padding:24px 0;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:12px;">
          <div>
            <h1 style="font-size:22px;font-weight:700;color:var(--brand-purple);margin:0;">
              ${t('ext_findings.title_h1')}
            </h1>
            <p style="color:#9d9d9d;font-size:13px;margin:4px 0 0;">
              ${t('ext_findings.subtitle')}
            </p>
          </div>
          <button onclick="ViewExternalFindings._importModal()" class="btn-primary">
            ${t('ext_findings.import_findings_btn')}
          </button>
        </div>

        <!-- Resumen -->
        <div id="fi-summary" style="margin-bottom:16px;"></div>

        <!-- Filtros -->
        <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;padding:14px;
                    margin-bottom:16px;display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;">
          <div>
            <label style="font-size:11px;color:#9d9d9d;display:block;margin-bottom:4px;">${t('ext_findings.f_severity')}</label>
            <select id="fi-filter-sev" class="input-field" style="width:120px;">
              <option value="">${t('ext_findings.f_all_f')}</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
          <div>
            <label style="font-size:11px;color:#9d9d9d;display:block;margin-bottom:4px;">${t('ext_findings.f_source')}</label>
            <select id="fi-filter-src" class="input-field" style="width:120px;">
              <option value="">${t('ext_findings.f_all_f')}</option>
              <option value="nessus">Nessus</option>
              <option value="qualys">Qualys</option>
              <option value="burp">Burp</option>
              <option value="openvas">OpenVAS</option>
              <option value="architecture_review">${t('ext_findings.arch_review_src')}</option>
            </select>
          </div>
          <div>
            <label style="font-size:11px;color:#9d9d9d;display:block;margin-bottom:4px;">${t('ext_findings.f_status')}</label>
            <select id="fi-filter-status" class="input-field" style="width:110px;">
              <option value="">${t('ext_findings.f_all_m')}</option>
              <option value="open">${t('ext_findings.open')}</option>
              <option value="resolved">${t('ext_findings.resolved')}</option>
            </select>
          </div>
          <div style="display:none;">
            <label style="font-size:11px;color:#9d9d9d;display:block;margin-bottom:4px;">${t('ext_findings.f_source_doc')}</label>
            <select id="fi-filter-doc" class="input-field" style="width:160px;">
              <option value="">${t('ext_findings.f_all_m')}</option>
            </select>
          </div>
          <button onclick="ViewExternalFindings._applyFilters()" class="btn-primary" style="padding:6px 14px;">${t('ext_findings.filter_btn')}</button>
        </div>

        <!-- Tabla -->
        <div style="background:#fff;border-radius:8px;border:1px solid #e0e0e0;overflow:hidden;">
          <table style="width:100%;border-collapse:collapse;font-size:13px;">
            <thead>
              <tr style="background:var(--brand-purple);color:#fff;">
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('ext_findings.f_severity')}</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('ext_findings.th_title_cve')}</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('ext_findings.f_source')}</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('ext_findings.th_affected_host')}</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('ext_findings.th_asset_risk')}</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('ext_findings.f_status')}</th>
                <th style="padding:10px 12px;text-align:left;font-weight:600;">${t('ext_findings.th_action')}</th>
              </tr>
            </thead>
            <tbody id="fi-tbody">
              <tr><td colspan="7" style="text-align:center;padding:24px;color:#9d9d9d;">${t('ext_findings.loading')}</td></tr>
            </tbody>
          </table>
        </div>
      </div>`;

    await _load();
    await _loadSummary();
  }

  return {
    render, _importModal, _submitImport, _resolve, _applyFilters, _load,
    _transferToIncident, _transferToRiskModal, _submitTransferToRisk,
  };
})();
