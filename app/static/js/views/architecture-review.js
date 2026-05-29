/* Vista de revision de arquitectura de seguridad con IA. */
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

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Revision de Arquitectura de Seguridad</h1>
          <p class="page-sub">
            El agente IA analiza tus diagramas y documentos de red para detectar vulnerabilidades
            y proponer mejoras alineadas con ISO 27001 y Zero Trust.
          </p>
        </div>
      </div>
      <div id="arch-root"></div>
    `;
    await _renderRoot();
  }

  async function _renderRoot() {
    const root = document.getElementById('arch-root');
    if (!root) return;

    // Verificar si hay documentos de arquitectura disponibles
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
          <h3 style="font-size:15px;font-weight:700;margin:0 0 8px;">Sin documentos de arquitectura</h3>
          <p style="font-size:13px;color:var(--text-muted);margin:0 0 16px;">
            Sube diagramas de red, documentos de arquitectura o topologias (PDF, DOCX, PNG, JPG)
            en la seccion <strong>Docs del Agente</strong> con la categoria
            <strong>Arquitectura y sistemas</strong>.
          </p>
          <a href="#/ai-documents" class="btn btn-primary" style="display:inline-block;">
            Ir a Docs del Agente
          </a>
        </div>`;
      return;
    }

    root.innerHTML = `
      <!-- Lista de documentos disponibles -->
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;
                  padding:16px;margin-bottom:20px;">
        <h3 style="font-size:14px;font-weight:700;margin:0 0 12px;">
          Documentos de arquitectura disponibles (${archDocs.length})
        </h3>
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px;">
          ${archDocs.map(d => `
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:6px;
                        padding:6px 12px;font-size:12px;display:flex;align-items:center;gap:6px;">
              ${d.mime_type && d.mime_type.startsWith('image/')
                ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`
                : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>`}
              <span>${UI.esc(d.original_name)}</span>
              ${d.mime_type && d.mime_type.startsWith('image/')
                ? `<span style="font-size:10px;background:var(--brand-purple-4);color:var(--brand-purple);
                               border-radius:3px;padding:0 4px;">IMAGEN</span>` : ''}
            </div>`).join('')}
        </div>
        <div style="display:flex;justify-content:center;">
          <button class="btn btn-primary" id="btn-start-arch-review" style="padding:10px 28px;font-size:14px;">
            Analizar arquitectura de seguridad
          </button>
        </div>
      </div>

      <!-- Resultado del analisis -->
      <div id="arch-result"></div>
    `;

    document.getElementById('btn-start-arch-review').onclick = _runAnalysis;

    // Si hay resultado cacheado en memoria, mostrarlo
    if (_result) {
      _renderResult(document.getElementById('arch-result'), _result);
    }
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
          El agente esta analizando tus diagramas de red...
        </span>`;
    }

    resultDiv.innerHTML = `
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:10px;
                  padding:32px;text-align:center;">
        <div class="loading-spinner" style="margin:0 auto 16px;width:32px;height:32px;"></div>
        <p style="font-size:13px;color:var(--text-muted);margin:0;">
          El agente esta analizando tus diagramas de red y documentos de arquitectura...<br>
          <span style="font-size:11px;">Esto puede tardar entre 30 y 60 segundos.</span>
        </p>
      </div>`;

    try {
      const d = await Api.ai.architectureReview();
      _result = d;
      _vulnFilter = 'all';
      _renderResult(resultDiv, d);
    } catch (e) {
      resultDiv.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = 'Actualizar analisis';
      }
    }
  }

  function _renderResult(container, d) {
    const vulns = d.vulnerabilities || [];
    const comps = d.components || [];
    const imprs = d.improvements || [];
    const comp = d.compliance || {};

    // Conteo por criticidad
    const critCounts = {};
    vulns.forEach(v => { critCounts[v.risk] = (critCounts[v.risk] || 0) + 1; });

    function _vulnsHtml(filter) {
      const filtered = filter === 'all' ? vulns : vulns.filter(v => v.risk === filter);
      if (!filtered.length) {
        return `<p style="color:var(--text-muted);font-size:13px;padding:12px 0;">
          Sin vulnerabilidades en esta categoria.</p>`;
      }
      return filtered.map(v => {
        const rc = RISK_COLORS[v.risk] || RISK_COLORS['BAJO'];
        return `
          <div style="border:1px solid ${rc.border};background:${rc.bg};border-radius:8px;
                      padding:14px;margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
              <div style="flex:1;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                  <span style="background:${rc.color};color:#fff;font-size:10px;font-weight:700;
                               padding:2px 8px;border-radius:4px;white-space:nowrap;">${UI.esc(v.risk || '-')}</span>
                  ${v.cve ? `<a href="https://nvd.nist.gov/vuln/detail/${UI.esc(v.cve)}" target="_blank"
                               style="font-size:10px;color:var(--brand-purple);font-weight:600;">
                               ${UI.esc(v.cve)}</a>` : ''}
                  ${v.iso_control_violated ? `<span style="font-size:10px;color:var(--text-muted);">
                    ISO ${UI.esc(v.iso_control_violated)}</span>` : ''}
                </div>
                <p style="font-size:13px;margin:0 0 4px;">${UI.esc(v.description || '-')}</p>
                ${v.affected_component ? `<p style="font-size:11px;color:var(--text-muted);margin:0;">
                  Componente: ${UI.esc(v.affected_component)}</p>` : ''}
              </div>
            </div>
          </div>`;
      }).join('');
    }

    container.innerHTML = `
      <!-- Meta info -->
      ${d._meta ? `
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:12px;text-align:right;">
          Analisis de ${d._meta.docs_analyzed} documento(s):
          ${(d._meta.doc_names || []).map(n => UI.esc(n)).join(', ')}
        </div>` : ''}

      <!-- Executive summary -->
      ${d.executive_summary ? `
        <div style="background:var(--bg-card);border:1px solid var(--border);border-left:4px solid var(--brand-purple);
                    border-radius:0 10px 10px 0;padding:16px;margin-bottom:20px;">
          <h3 style="font-size:14px;font-weight:700;margin:0 0 8px;color:var(--brand-purple);">Resumen ejecutivo</h3>
          <p style="font-size:13px;margin:0;line-height:1.6;">${UI.esc(d.executive_summary)}</p>
        </div>` : ''}

      <!-- Stats de vulnerabilidades -->
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
          <div class="stat-label">Componentes</div>
        </div>
        <div class="stat-card" style="text-align:center;min-width:100px;">
          <div class="stat-value" style="color:var(--brand-purple);">${imprs.length}</div>
          <div class="stat-label">Mejoras</div>
        </div>
      </div>

      <!-- 1. Inventario de componentes -->
      ${comps.length > 0 ? `
        <details open style="margin-bottom:16px;">
          <summary style="cursor:pointer;background:var(--bg-card);border:1px solid var(--border);
                          border-radius:10px;padding:14px 16px;font-size:14px;font-weight:700;
                          display:flex;justify-content:space-between;list-style:none;">
            <span>1. Inventario de componentes identificados (${comps.length})</span>
            <span style="color:var(--text-muted);font-weight:400;font-size:12px;">&#9660;</span>
          </summary>
          <div style="background:var(--bg-card);border:1px solid var(--border);border-top:none;
                      border-radius:0 0 10px 10px;padding:16px;">
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px;">
              ${comps.map(c => `
                <div style="background:var(--bg-2);border-radius:6px;padding:10px;">
                  <div style="font-size:11px;font-weight:700;text-transform:uppercase;
                               color:var(--brand-purple);margin-bottom:4px;">${UI.esc(c.type || '-')}</div>
                  <div style="font-size:13px;font-weight:600;">${UI.esc(c.name || '-')}</div>
                  ${c.description ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px;">
                    ${UI.esc(c.description)}</div>` : ''}
                </div>`).join('')}
            </div>
          </div>
        </details>` : ''}

      <!-- 2. Vulnerabilidades -->
      <details open style="margin-bottom:16px;">
        <summary style="cursor:pointer;background:var(--bg-card);border:1px solid var(--border);
                        border-radius:10px;padding:14px 16px;font-size:14px;font-weight:700;
                        display:flex;justify-content:space-between;list-style:none;">
          <span>2. Vulnerabilidades de configuracion (${vulns.length})</span>
          <span style="color:var(--text-muted);font-weight:400;font-size:12px;">&#9660;</span>
        </summary>
        <div style="background:var(--bg-card);border:1px solid var(--border);border-top:none;
                    border-radius:0 0 10px 10px;padding:16px;">
          <!-- Filtros por criticidad -->
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;" id="arch-vuln-filters">
            ${['all', 'CRITICO', 'ALTO', 'MEDIO', 'BAJO'].map(r => {
              const n = r === 'all' ? vulns.length : (critCounts[r] || 0);
              const rc = r === 'all' ? null : RISK_COLORS[r];
              return `<button class="btn ${r === _vulnFilter ? 'btn-primary' : 'btn-ghost'}"
                              style="font-size:11px;padding:3px 10px;${rc ? `color:${rc.color};` : ''}"
                              onclick="ViewArchitectureReview._filterVulns(this, '${r}')">
                ${r === 'all' ? 'Todas' : r} (${n})
              </button>`;
            }).join('')}
          </div>
          <div id="arch-vuln-list">${_vulnsHtml(_vulnFilter)}</div>
        </div>
      </details>

      <!-- 3. Mejoras propuestas -->
      ${imprs.length > 0 ? `
        <details open style="margin-bottom:16px;">
          <summary style="cursor:pointer;background:var(--bg-card);border:1px solid var(--border);
                          border-radius:10px;padding:14px 16px;font-size:14px;font-weight:700;
                          display:flex;justify-content:space-between;list-style:none;">
            <span>3. Mejoras de arquitectura propuestas (${imprs.length})</span>
            <span style="color:var(--text-muted);font-weight:400;font-size:12px;">&#9660;</span>
          </summary>
          <div style="background:var(--bg-card);border:1px solid var(--border);border-top:none;
                      border-radius:0 0 10px 10px;padding:16px;">
            ${imprs.map((im, idx) => {
              const pc = PRIORITY_COLORS[im.priority] || 'var(--text-muted)';
              const effortBadge = { BAJO: '#DCFCE7', MEDIO: '#FEF9C3', ALTO: '#FEE2E2' }[im.effort] || 'var(--bg-2)';
              return `
                <div style="padding:14px;background:var(--bg-2);border-radius:8px;margin-bottom:10px;
                            border-left:3px solid ${pc};">
                  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
                    <span style="font-size:12px;font-weight:700;color:${pc};">
                      ${UI.esc(im.priority || '-')}
                    </span>
                    <span style="background:${effortBadge};font-size:10px;padding:1px 6px;border-radius:3px;">
                      Esfuerzo: ${UI.esc(im.effort || '-')}
                    </span>
                  </div>
                  <p style="font-size:13px;font-weight:600;margin:0 0 4px;">${UI.esc(im.improvement || '-')}</p>
                  ${im.justification ? `<p style="font-size:12px;color:var(--text-muted);margin:0;">
                    ${UI.esc(im.justification)}</p>` : ''}
                </div>`;
            }).join('')}
          </div>
        </details>` : ''}

      <!-- 4. Cumplimiento -->
      <details style="margin-bottom:16px;">
        <summary style="cursor:pointer;background:var(--bg-card);border:1px solid var(--border);
                        border-radius:10px;padding:14px 16px;font-size:14px;font-weight:700;
                        display:flex;justify-content:space-between;list-style:none;">
          <span>4. Cumplimiento con estandares</span>
          <span style="color:var(--text-muted);font-weight:400;font-size:12px;">&#9660;</span>
        </summary>
        <div style="background:var(--bg-card);border:1px solid var(--border);border-top:none;
                    border-radius:0 0 10px 10px;padding:16px;">
          ${comp.iso27002_covered?.length ? `
            <div style="margin-bottom:12px;">
              <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;color:var(--risk-low);">
                Controles ISO 27002 cubiertos
              </h4>
              <div style="display:flex;flex-wrap:wrap;gap:6px;">
                ${comp.iso27002_covered.map(c => `
                  <span style="background:#DCFCE7;color:var(--risk-low);font-size:11px;font-weight:700;
                               padding:2px 8px;border-radius:4px;">${UI.esc(c)}</span>`).join('')}
              </div>
            </div>` : ''}
          ${comp.iso27002_missing?.length ? `
            <div style="margin-bottom:12px;">
              <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;color:var(--risk-high);">
                Controles ISO 27002 no cubiertos
              </h4>
              <div style="display:flex;flex-wrap:wrap;gap:6px;">
                ${comp.iso27002_missing.map(c => `
                  <span style="background:#FEE2E2;color:var(--risk-high);font-size:11px;font-weight:700;
                               padding:2px 8px;border-radius:4px;">${UI.esc(c)}</span>`).join('')}
              </div>
            </div>` : ''}
          ${comp.zero_trust_recommendations?.length ? `
            <div style="margin-bottom:12px;">
              <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;">Recomendaciones Zero Trust</h4>
              <ul style="margin:0;padding-left:20px;">
                ${comp.zero_trust_recommendations.map(r => `
                  <li style="font-size:13px;margin-bottom:4px;">${UI.esc(r)}</li>`).join('')}
              </ul>
            </div>` : ''}
          ${comp.network_segmentation ? `
            <div>
              <h4 style="font-size:13px;font-weight:700;margin:0 0 8px;">Segmentacion de red propuesta</h4>
              <p style="font-size:13px;margin:0;">${UI.esc(comp.network_segmentation)}</p>
            </div>` : ''}
        </div>
      </details>

      <p style="font-size:11px;color:var(--text-muted);text-align:center;margin-top:8px;">
        Analisis generado con IA. Revisar con el equipo de seguridad antes de implementar cambios en produccion.
      </p>
    `;

    // Expose filter function
    ViewArchitectureReview._filterVulns = (btn, risk) => {
      _vulnFilter = risk;
      document.querySelectorAll('#arch-vuln-filters .btn').forEach(b => b.classList.remove('btn-primary'));
      btn.classList.add('btn-primary');
      const list = document.getElementById('arch-vuln-list');
      if (list) {
        const filtered = risk === 'all' ? vulns : vulns.filter(v => v.risk === risk);
        list.innerHTML = filtered.length
          ? filtered.map(v => {
              const rc = RISK_COLORS[v.risk] || RISK_COLORS['BAJO'];
              return `<div style="border:1px solid ${rc.border};background:${rc.bg};border-radius:8px;
                          padding:14px;margin-bottom:10px;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                  <span style="background:${rc.color};color:#fff;font-size:10px;font-weight:700;
                               padding:2px 8px;border-radius:4px;">${UI.esc(v.risk || '-')}</span>
                  ${v.cve ? `<a href="https://nvd.nist.gov/vuln/detail/${UI.esc(v.cve)}" target="_blank"
                               style="font-size:10px;color:var(--brand-purple);font-weight:600;">
                               ${UI.esc(v.cve)}</a>` : ''}
                  ${v.iso_control_violated ? `<span style="font-size:10px;color:var(--text-muted);">ISO ${UI.esc(v.iso_control_violated)}</span>` : ''}
                </div>
                <p style="font-size:13px;margin:0 0 4px;">${UI.esc(v.description || '-')}</p>
                ${v.affected_component ? `<p style="font-size:11px;color:var(--text-muted);margin:0;">Componente: ${UI.esc(v.affected_component)}</p>` : ''}
              </div>`;
            }).join('')
          : `<p style="color:var(--text-muted);font-size:13px;">Sin vulnerabilidades en esta categoria.</p>`;
      }
    };
  }

  return { render, _filterVulns: () => {} };
})();
