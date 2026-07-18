/* Vista de revisión de arquitectura de seguridad con IA. */
const ViewArchitectureReview = (() => {

  const RISK_COLORS = {
    CRITICO: { bg: '#FEE2E2', color: 'var(--risk-critical)', border: '#F87171' },
    ALTO:    { bg: '#FFF7ED', color: 'var(--risk-high)',     border: '#FB923C' },
    MEDIO:   { bg: '#FEF9C3', color: '#D97706',              border: '#FCD34D' },
    BAJO:    { bg: '#DCFCE7', color: 'var(--risk-low)',      border: '#86EFAC' },
  };

  const PRIORITY_COLORS = {
    ALTA:  'var(--risk-critical)',
    MEDIA: 'var(--risk-medium)',
    BAJA:  'var(--risk-low)',
  };

  let _result = null;
  let _vulnFilter = 'all';
  let _docFilter = 'all';
  let _assetsCache = null;

  function _getStatusBadge() {
    return {
      open:     { bg: '#FEF0E3', color: '#c25a1f', label: t('arch_review.status.open') },
      resolved: { bg: '#E8F5E9', color: '#2e7d32', label: t('arch_review.status.resolved') },
      accepted: { bg: '#E8F5E9', color: '#2e7d32', label: t('arch_review.status.accepted') },
    };
  }

  async function _getAssets() {
    if (_assetsCache) return _assetsCache;
    try { _assetsCache = await Api.assets.list(); } catch (_) { _assetsCache = []; }
    return _assetsCache;
  }

  async function _resolveFinding(findingId) {
    if (!findingId) return;
    try {
      await Api.findings.resolve(findingId);
      UI.toast(t('arch_review.resolved_toast'), 'success');
      const v = (_result.vulnerabilities || []).find(x => x.finding_id === findingId);
      if (v) v.finding_status = 'resolved';
      _renderResult(document.getElementById('arch-result'), _result);
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _transferToIncident(findingId) {
    if (!findingId) return;
    try {
      const r = await Api.findings.createIncident(findingId);
      UI.toast(t('arch_review.incident_created', { code: r.incident_code }), 'success');
      const v = (_result.vulnerabilities || []).find(x => x.finding_id === findingId);
      if (v) v.finding_incident_id = r.incident_id;
      _renderResult(document.getElementById('arch-result'), _result);
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _transferToRiskModal(findingId) {
    if (!findingId) return;
    const assets = await _getAssets();
    if (!assets.length) {
      UI.toast(t('arch_review.no_assets_error'), 'error');
      return;
    }
    UI.openModal(`
      <h3 style="margin:0 0 16px;color:var(--brand-purple);">${t('arch_review.transfer_risk_title')}</h3>
      <p style="font-size:13px;color:#666;margin-bottom:12px;">
        ${t('arch_review.transfer_risk_desc')}
      </p>
      <select id="arch-risk-asset" class="input-field" style="width:100%;">
        ${assets.map(a => `<option value="${a.id}">${UI.esc(a.name)}</option>`).join('')}
      </select>
      <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;">
        <button onclick="UI.closeModal()" class="btn-outline">${t('arch_review.cancel_btn')}</button>
        <button onclick="ViewArchitectureReview._submitTransferToRisk(${findingId})" class="btn-primary">
          ${t('arch_review.create_risk_btn')}
        </button>
      </div>`);
  }

  async function _submitTransferToRisk(findingId) {
    const assetId = parseInt(document.getElementById('arch-risk-asset').value, 10);
    try {
      const r = await Api.findings.createRisk(findingId, assetId);
      UI.closeModal();
      UI.toast(t('arch_review.risk_created', { code: r.risk_code }), 'success');
      const v = (_result.vulnerabilities || []).find(x => x.finding_id === findingId);
      if (v) v.finding_risk_id = r.risk_id;
      _renderResult(document.getElementById('arch-result'), _result);
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _createTaskFromImprovement(idx) {
    const imp = (_result.improvements || [])[idx];
    if (!imp || imp._task_created) return;
    const priorityMap = { ALTA: 'critical', MEDIA: 'medium', BAJA: 'low' };
    try {
      const sourceNote = imp.source_document ? ` (${imp.source_document})` : '';
      await Api.tasks.create({
        title: imp.improvement.slice(0, 255),
        description: imp.justification || imp.improvement,
        priority: priorityMap[imp.priority] || 'medium',
        notes: `${t('arch_review.task_notes')}${sourceNote}.`,
      });
      imp._task_created = true;
      UI.toast(t('arch_review.task_toast'), 'success');
      _renderResult(document.getElementById('arch-result'), _result);
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('arch_review.page_title')}</h1>
          <p class="page-sub">${t('arch_review.page_sub')}</p>
        </div>
      </div>
      <div id="arch-root"></div>
    `;
    await _renderRoot();
  }

  async function _renderRoot() {
    const root = document.getElementById('arch-root');
    if (!root) return;

    let archDocs = [];
    try {
      const allDocs = await Api.aiDocuments.list();
      archDocs = allDocs.filter(d => d.category === 'architecture' && d.status === 'indexed');
    } catch (_) {}

    if (archDocs.length === 0) {
      root.innerHTML = `
        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;
                    padding:32px;text-align:center;max-width:600px;margin:0 auto;">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)"
               stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
               style="display:block;margin:0 auto 16px;">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <path d="M9 9h6M9 12h4M9 15h6"/>
          </svg>
          <h3 style="font-size:15px;font-weight:700;margin:0 0 8px;">${t('arch_review.no_docs_title')}</h3>
          <p style="font-size:13px;color:var(--text-muted);margin:0 0 16px;">${t('arch_review.no_docs_desc')}</p>
          <a href="#/ai-documents" class="btn btn-primary" style="display:inline-block;">
            ${t('arch_review.no_docs_link')}
          </a>
        </div>`;
      return;
    }

    root.innerHTML = `
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;
                  padding:16px;margin-bottom:20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
          <h3 style="font-size:14px;font-weight:700;margin:0;">
            ${t('arch_review.docs_available', { n: archDocs.length })}
          </h3>
          <a href="#/ai-documents" class="btn btn-outline" style="font-size:12px;padding:5px 12px;">
            ${t('arch_review.upload_link')}
          </a>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px;">
          ${archDocs.map(d => `
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:6px;
                        padding:6px 12px;font-size:12px;display:flex;align-items:center;gap:6px;">
              ${d.mime_type && d.mime_type.startsWith('image/')
                ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`
                : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>`}
              <span>${UI.esc(d.original_name)}</span>
              ${d.mime_type && d.mime_type.startsWith('image/')
                ? `<span style="font-size:10px;background:var(--brand-purple-4);color:var(--brand-purple);border-radius:3px;padding:0 4px;">IMG</span>` : ''}
            </div>`).join('')}
        </div>
        <div style="display:flex;justify-content:center;">
          <button class="btn btn-primary" id="btn-start-arch-review" style="padding:10px 28px;font-size:14px;">
            ${t('arch_review.analyze_btn')}
          </button>
        </div>
      </div>
      <div id="arch-result"></div>
    `;

    document.getElementById('btn-start-arch-review').onclick = _runAnalysis;

    if (_result) _renderResult(document.getElementById('arch-result'), _result);
  }

  async function _runAnalysis() {
    const btn = document.getElementById('btn-start-arch-review');
    const resultDiv = document.getElementById('arch-result');
    if (!resultDiv) return;

    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `
        <span style="display:inline-flex;align-items:center;gap:10px;">
          <span class="loading-spinner" style="width:18px;height:18px;border-width:2px;"></span>
          ${t('arch_review.analyzing_title')}
        </span>`;
    }

    resultDiv.innerHTML = `
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;
                  padding:32px;text-align:center;">
        <div class="loading-spinner" style="margin:0 auto 16px;width:32px;height:32px;"></div>
        <p style="font-size:13px;color:var(--text-muted);margin:0;">
          ${t('arch_review.loading_title')}<br>
          <span style="font-size:11px;">${t('arch_review.loading_sub')}</span>
        </p>
      </div>`;

    try {
      const d = await Api.ai.architectureReview();
      _result = d;
      _vulnFilter = 'all';
      _docFilter = 'all';
      _renderResult(resultDiv, d);
    } catch (e) {
      resultDiv.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = t('arch_review.refresh_btn');
      }
    }
  }

  function _renderResult(container, d) {
    const vulns = d.vulnerabilities || [];
    const comps = d.components || [];
    const imprs = d.improvements || [];
    const comp  = d.compliance || {};

    const critCounts = {};
    vulns.forEach(v => { critCounts[v.risk] = (critCounts[v.risk] || 0) + 1; });

    const docNames = Array.from(new Set(vulns.map(v => v.source_document).filter(Boolean)));

    function _matchesFilters(v) {
      const sevOk = _vulnFilter === 'all' || v.risk === _vulnFilter;
      const docOk = _docFilter === 'all' || v.source_document === _docFilter;
      return sevOk && docOk;
    }

    function _vulnsHtml() {
      const filtered = vulns.filter(_matchesFilters);
      const statusBadge = _getStatusBadge();
      if (!filtered.length) {
        return `<p style="color:var(--text-muted);font-size:13px;padding:12px 0;">${t('arch_review.no_vulns')}</p>`;
      }
      return filtered.map(v => {
        const rc = RISK_COLORS[v.risk] || RISK_COLORS['BAJO'];
        const st = statusBadge[v.finding_status] || statusBadge.open;
        const isResolved = v.finding_status === 'resolved' || v.finding_status === 'accepted';
        return `
          <div style="border:1px solid ${rc.border};background:${rc.bg};border-radius:8px;
                      padding:14px;margin-bottom:10px;${isResolved ? 'opacity:.65;' : ''}">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
              <div style="flex:1;min-width:240px;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
                  <span style="background:${rc.color};color:#fff;font-size:10px;font-weight:700;
                               padding:2px 8px;border-radius:4px;white-space:nowrap;">${UI.esc(v.risk || '-')}</span>
                  ${v.finding_id ? `<span style="background:${st.bg};color:${st.color};font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px;">${st.label}</span>` : ''}
                  ${v.cve ? `<a href="https://nvd.nist.gov/vuln/detail/${UI.esc(v.cve)}" target="_blank"
                               style="font-size:10px;color:var(--brand-purple);font-weight:600;">${UI.esc(v.cve)}</a>` : ''}
                  ${v.iso_control_violated ? `<span style="font-size:10px;color:var(--text-muted);">ISO ${UI.esc(v.iso_control_violated)}</span>` : ''}
                  ${v.source_document ? `<span style="font-size:10px;background:var(--bg-2);border:1px solid var(--border);border-radius:4px;padding:1px 6px;color:var(--text-muted);">${UI.esc(v.source_document)}</span>` : ''}
                </div>
                <p style="font-size:13px;margin:0 0 4px;">${UI.esc(v.description || '-')}</p>
                ${v.affected_component ? `<p style="font-size:11px;color:var(--text-muted);margin:0;">${t('arch_review.component_label')} ${UI.esc(v.affected_component)}</p>` : ''}
              </div>
              ${v.finding_id ? `
                <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:flex-start;">
                  ${!isResolved ? `
                    <button class="btn btn-ghost" style="font-size:11px;padding:3px 8px;"
                            onclick="ViewArchitectureReview._resolveFinding(${v.finding_id}, this)">
                      ${t('arch_review.resolve_btn')}
                    </button>
                    ${!v.finding_incident_id ? `
                    <button class="btn btn-ghost" style="font-size:11px;padding:3px 8px;"
                            onclick="ViewArchitectureReview._transferToIncident(${v.finding_id})">
                      ${t('arch_review.to_incident_btn')}
                    </button>` : `
                    <a href="#/incidents" class="btn btn-ghost" style="font-size:11px;padding:3px 8px;">
                      ${t('arch_review.view_incident_btn')}
                    </a>`}
                    ${!v.finding_risk_id ? `
                    <button class="btn btn-ghost" style="font-size:11px;padding:3px 8px;"
                            onclick="ViewArchitectureReview._transferToRiskModal(${v.finding_id})">
                      ${t('arch_review.create_risk_btn')}
                    </button>` : `
                    <a href="#/risks" class="btn btn-ghost" style="font-size:11px;padding:3px 8px;">
                      ${t('arch_review.view_risk_btn')}
                    </a>`}
                  ` : ''}
                </div>` : ''}
            </div>
          </div>`;
      }).join('');
    }

    container.innerHTML = `
      ${d._meta ? `
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:12px;text-align:right;">
          ${t('arch_review.meta_docs', { n: d._meta.docs_analyzed, names: (d._meta.doc_names || []).map(n => UI.esc(n)).join(', ') })}
        </div>` : ''}

      ${d.executive_summary ? `
        <div style="background:var(--bg-card);border:1px solid var(--border);border-left:4px solid var(--brand-purple);
                    border-radius:0 10px 10px 0;padding:16px;margin-bottom:20px;">
          <h3 style="font-size:14px;font-weight:700;margin:0 0 8px;color:var(--brand-purple);">${t('arch_review.executive_summary')}</h3>
          <p style="font-size:13px;margin:0;line-height:1.6;">${UI.esc(d.executive_summary)}</p>
        </div>` : ''}

      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px;">
        ${['CRITICO', 'ALTO', 'MEDIO', 'BAJO'].map(risk => {
          const n = critCounts[risk] || 0;
          const rc = RISK_COLORS[risk];
          return `<div class="stat-card" style="text-align:center;min-width:100px;">
            <div class="stat-value" style="color:${rc.color};">${n}</div>
            <div class="stat-label">${risk}</div>
          </div>`;
        }).join('')}
        <div class="stat-card" style="text-align:center;min-width:100px;">
          <div class="stat-value">${comps.length}</div>
          <div class="stat-label">${t('arch_review.stat_components')}</div>
        </div>
        <div class="stat-card" style="text-align:center;min-width:100px;">
          <div class="stat-value" style="color:var(--brand-purple);">${imprs.length}</div>
          <div class="stat-label">${t('arch_review.stat_improvements')}</div>
        </div>
      </div>

      ${comps.length > 0 ? `
        <details open style="margin-bottom:16px;">
          <summary style="cursor:pointer;background:var(--bg-card);border:1px solid var(--border);
                          border-radius:10px;padding:14px 16px;font-size:14px;font-weight:700;
                          display:flex;justify-content:space-between;list-style:none;">
            <span>${t('arch_review.section_components', { n: comps.length })}</span>
            <span style="color:var(--text-muted);font-weight:400;font-size:12px;">&#9660;</span>
          </summary>
          <div style="background:var(--bg-card);border:1px solid var(--border);border-top:none;
                      border-radius:0 0 10px 10px;padding:16px;">
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px;">
              ${comps.map(c => `
                <div style="background:var(--bg-2);border-radius:6px;padding:10px;">
                  <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--brand-purple);margin-bottom:4px;">${UI.esc(c.type || '-')}</div>
                  <div style="font-size:13px;font-weight:600;">${UI.esc(c.name || '-')}</div>
                  ${c.description ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${UI.esc(c.description)}</div>` : ''}
                </div>`).join('')}
            </div>
          </div>
        </details>` : ''}

      <details open style="margin-bottom:16px;">
        <summary style="cursor:pointer;background:var(--bg-card);border:1px solid var(--border);
                        border-radius:10px;padding:14px 16px;font-size:14px;font-weight:700;
                        display:flex;justify-content:space-between;list-style:none;">
          <span>${t('arch_review.section_vulns', { n: vulns.length })}</span>
          <span style="color:var(--text-muted);font-weight:400;font-size:12px;">&#9660;</span>
        </summary>
        <div style="background:var(--bg-card);border:1px solid var(--border);border-top:none;
                    border-radius:0 0 10px 10px;padding:16px;">
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;" id="arch-vuln-filters">
            ${['all', 'CRITICO', 'ALTO', 'MEDIO', 'BAJO'].map(r => {
              const n = r === 'all' ? vulns.length : (critCounts[r] || 0);
              const rc = r === 'all' ? null : RISK_COLORS[r];
              return `<button class="btn ${r === _vulnFilter ? 'btn-primary' : 'btn-ghost'}"
                              style="font-size:11px;padding:3px 10px;${rc ? `color:${rc.color};` : ''}"
                              onclick="ViewArchitectureReview._filterVulns(this, '${r}')">
                ${r === 'all' ? t('arch_review.filter_all') : r} (${n})
              </button>`;
            }).join('')}
          </div>
          ${docNames.length > 1 ? `
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:14px;">
            <span style="font-size:11px;color:var(--text-muted);">${t('arch_review.filter_doc_label')}</span>
            <div style="display:flex;gap:6px;flex-wrap:wrap;" id="arch-doc-filters">
              ${['all', ...docNames].map(doc => `
                <button class="btn ${doc === _docFilter ? 'btn-primary' : 'btn-ghost'}"
                        style="font-size:11px;padding:3px 10px;"
                        onclick="ViewArchitectureReview._filterDocs(this, '${UI.esc(doc).replace(/'/g, "\\'")}')">
                  ${doc === 'all' ? t('arch_review.filter_doc_all') : UI.esc(doc)}
                </button>`).join('')}
            </div>
          </div>` : ''}
          <div id="arch-vuln-list">${_vulnsHtml()}</div>
        </div>
      </details>

      ${imprs.length > 0 ? `
        <details open style="margin-bottom:16px;">
          <summary style="cursor:pointer;background:var(--bg-card);border:1px solid var(--border);
                          border-radius:10px;padding:14px 16px;font-size:14px;font-weight:700;
                          display:flex;justify-content:space-between;list-style:none;">
            <span>${t('arch_review.section_improvements', { n: imprs.length })}</span>
            <span style="color:var(--text-muted);font-weight:400;font-size:12px;">&#9660;</span>
          </summary>
          <div style="background:var(--bg-card);border:1px solid var(--border);border-top:none;
                      border-radius:0 0 10px 10px;padding:16px;">
            ${imprs.map((im, idx) => {
              const pc = PRIORITY_COLORS[im.priority] || 'var(--text-muted)';
              const effortBg = { BAJO: '#DCFCE7', MEDIO: '#FEF9C3', ALTO: '#FEE2E2' }[im.effort] || 'var(--bg-2)';
              return `
                <div style="padding:14px;background:var(--bg-2);border-radius:8px;margin-bottom:10px;border-left:3px solid ${pc};">
                  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
                    <span style="font-size:12px;font-weight:700;color:${pc};">${UI.esc(im.priority || '-')}</span>
                    <span style="background:${effortBg};font-size:10px;padding:1px 6px;border-radius:3px;">
                      ${t('arch_review.effort_label')} ${UI.esc(im.effort || '-')}
                    </span>
                    ${im.source_document ? `<span style="font-size:10px;background:var(--bg-3);border-radius:3px;padding:1px 6px;color:var(--text-muted);">${UI.esc(im.source_document)}</span>` : ''}
                  </div>
                  <p style="font-size:13px;font-weight:600;margin:0 0 4px;">${UI.esc(im.improvement || '-')}</p>
                  ${im.justification ? `<p style="font-size:12px;color:var(--text-muted);margin:0 0 8px;">${UI.esc(im.justification)}</p>` : ''}
                  <button class="btn ${im._task_created ? 'btn-ghost' : 'btn-primary'}"
                          style="font-size:11px;padding:3px 10px;" ${im._task_created ? 'disabled' : ''}
                          onclick="ViewArchitectureReview._createTaskFromImprovement(${idx}, this)">
                    ${im._task_created ? t('arch_review.task_created_btn') : t('arch_review.create_task_btn')}
                  </button>
                </div>`;
            }).join('')}
          </div>
        </details>` : ''}

      <details style="margin-bottom:16px;">
        <summary style="cursor:pointer;background:var(--bg-card);border:1px solid var(--border);
                        border-radius:10px;padding:14px 16px;font-size:14px;font-weight:700;
                        display:flex;justify-content:space-between;list-style:none;">
          <span>${t('arch_review.section_compliance')}</span>
          <span style="color:var(--text-muted);font-weight:400;font-size:12px;">&#9660;</span>
        </summary>
        <div style="background:var(--bg-card);border:1px solid var(--border);border-top:none;
                    border-radius:0 0 10px 10px;padding:16px;">
          ${comp.iso27002_covered?.length ? `
            <div style="margin-bottom:12px;">
              <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;color:var(--risk-low);">${t('arch_review.iso_covered')}</h4>
              <div style="display:flex;flex-wrap:wrap;gap:6px;">
                ${comp.iso27002_covered.map(c => `<span style="background:#DCFCE7;color:var(--risk-low);font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;">${UI.esc(c)}</span>`).join('')}
              </div>
            </div>` : ''}
          ${comp.iso27002_missing?.length ? `
            <div style="margin-bottom:12px;">
              <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;color:var(--risk-high);">${t('arch_review.iso_missing')}</h4>
              <div style="display:flex;flex-wrap:wrap;gap:6px;">
                ${comp.iso27002_missing.map(c => `<span style="background:#FEE2E2;color:var(--risk-high);font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;">${UI.esc(c)}</span>`).join('')}
              </div>
            </div>` : ''}
          ${comp.zero_trust_recommendations?.length ? `
            <div style="margin-bottom:12px;">
              <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;">${t('arch_review.zero_trust')}</h4>
              <ul style="margin:0;padding-left:20px;">
                ${comp.zero_trust_recommendations.map(r => `<li style="font-size:13px;margin-bottom:4px;">${UI.esc(r)}</li>`).join('')}
              </ul>
            </div>` : ''}
          ${comp.network_segmentation ? `
            <div>
              <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;">${t('arch_review.net_segmentation')}</h4>
              <p style="font-size:13px;margin:0;">${UI.esc(comp.network_segmentation)}</p>
            </div>` : ''}
        </div>
      </details>

      <p style="font-size:11px;color:var(--text-muted);text-align:center;margin-top:8px;">
        ${t('arch_review.ai_disclaimer')}
      </p>
    `;

    ViewArchitectureReview._filterVulns = (btn, risk) => {
      _vulnFilter = risk;
      document.querySelectorAll('#arch-vuln-filters .btn').forEach(b => b.classList.remove('btn-primary'));
      btn.classList.add('btn-primary');
      const list = document.getElementById('arch-vuln-list');
      if (list) list.innerHTML = _vulnsHtml();
    };

    ViewArchitectureReview._filterDocs = (btn, doc) => {
      _docFilter = doc;
      document.querySelectorAll('#arch-doc-filters .btn').forEach(b => b.classList.remove('btn-primary'));
      btn.classList.add('btn-primary');
      const list = document.getElementById('arch-vuln-list');
      if (list) list.innerHTML = _vulnsHtml();
    };
  }

  return {
    render,
    _filterVulns: () => {},
    _filterDocs: () => {},
    _resolveFinding,
    _transferToIncident,
    _transferToRiskModal,
    _submitTransferToRisk,
    _createTaskFromImprovement,
  };
})();
