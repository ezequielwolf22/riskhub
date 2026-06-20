/* Vista ISMS — Sistema de Gestion de Seguridad de la Informacion — ISO 27001 */
const ViewPolicies = (() => {

  const STATUS_LABELS = {
    draft: 'Borrador', review: 'En revision', approved: 'Aprobada',
    published: 'Publicada', obsolete: 'Obsoleta',
  };
  const STATUS_COLORS = {
    draft: 'var(--text-muted)', review: 'var(--brand-orange)',
    approved: 'var(--brand-purple)', published: 'var(--risk-low)', obsolete: '#aaa',
  };

  // Tipos de documento ISMS estandarizados
  const ISMS_TYPES = {
    politica:             'Politica',
    norma:                'Norma',
    instruccion_tecnica:  'Instruccion tecnica',
    evidencia:            'Otra evidencia',
  };
  const ISMS_TYPE_COLORS = {
    politica:            'var(--brand-purple)',
    norma:               'var(--brand-orange)',
    instruccion_tecnica: '#0891b2',
    evidencia:           '#6b7280',
  };

  // Jerarquia documental ISO: nivel 1-4
  const DOC_LEVEL_LABELS = {
    1: 'Politica',
    2: 'Norma / Estandar',
    3: 'Procedimiento',
    4: 'Instruccion Tecnica',
  };
  const DOC_LEVEL_COLORS = {
    1: 'var(--brand-purple)',
    2: 'var(--brand-orange)',
    3: '#0891b2',
    4: '#16a34a',
  };
  const DOC_LEVEL_MAX_MATURITY = { 1: 2, 2: 3, 3: 4, 4: 5 };

  function _levelBadge(level) {
    const l = parseInt(level) || 1;
    const label = DOC_LEVEL_LABELS[l] || 'Politica';
    const color = DOC_LEVEL_COLORS[l] || 'var(--brand-purple)';
    return `<span title="Nivel jerarquico: ${label}" style="display:inline-block;padding:1px 6px;border-radius:999px;font-size:10px;font-weight:700;background:${color}18;color:${color};border:1px solid ${color}40;">${l}. ${label}</span>`;
  }

  // Marcos normativos para generacion IA
  const FRAMEWORKS = [
    { value: 'ISO 27001', label: 'ISO/IEC 27001:2022' },
    { value: 'NIS2',      label: 'NIS2 (Directiva UE 2022/2555)' },
    { value: 'DORA',      label: 'DORA (Reglamento UE 2022/2554)' },
    { value: 'ENS',       label: 'ENS (Esquema Nacional de Seguridad)' },
    { value: 'GDPR',      label: 'RGPD / GDPR' },
    { value: 'NIST CSF',  label: 'NIST Cybersecurity Framework' },
    { value: 'PCI DSS',   label: 'PCI DSS v4' },
    { value: 'libre',     label: 'Sin norma especifica' },
  ];

  let _users      = [];
  let _activeType = 'all'; // tab activo

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  function _typeBadge(cat) {
    if (!cat) return '';
    const label = ISMS_TYPES[cat] || UI.esc(cat);
    const color = ISMS_TYPE_COLORS[cat] || '#888';
    return `<span style="display:inline-block;padding:1px 7px;border-radius:999px;font-size:10px;font-weight:700;background:${color}20;color:${color};border:1px solid ${color}40;">${label}</span>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">ISMS</h1>
          <p class="page-sub">Sistema de Gestion de Seguridad de la Informacion — ISO 27001 cl. 5.2</p>
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
          <input type="file" id="pol-ai-input" accept=".pdf,.docx,.txt" style="display:none;">
          <button class="btn" id="btn-ai-extract" title="Cargar un documento PDF/DOCX y extraer los campos con IA">
            Extraer con IA
          </button>
          <button onclick="ViewPolicies._generateWithAI()" class="btn"
                  style="background:linear-gradient(90deg,var(--brand-purple),var(--brand-orange));color:#fff;border:none;">
            Generar con IA
          </button>
          <button class="btn btn-primary" id="btn-new-pol">+ Nuevo documento</button>
        </div>
      </div>

      <div class="stats-row" id="pol-stats" style="margin-bottom:16px;"></div>

      <!-- Tabs de tipo ISMS -->
      <div style="display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap;border-bottom:1px solid var(--border);padding-bottom:10px;">
        <button class="btn btn-primary isms-tab" data-type="all">Todo</button>
        ${Object.entries(ISMS_TYPES).map(([k, l]) =>
          `<button class="btn isms-tab" data-type="${k}">${l}</button>`
        ).join('')}
      </div>

      <!-- Filtros de busqueda -->
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <input type="search" id="pol-search" class="input" style="width:220px;" placeholder="Buscar por titulo...">
        <select id="pol-status" class="input" style="width:160px;">
          <option value="">Todos los estados</option>
          ${Object.entries(STATUS_LABELS).map(([k,l]) => `<option value="${k}">${l}</option>`).join('')}
        </select>
      </div>

      <div id="pol-table-wrap"></div>
    `;

    // Tabs
    el.querySelectorAll('.isms-tab').forEach(btn => {
      btn.onclick = () => {
        el.querySelectorAll('.isms-tab').forEach(b => b.classList.remove('active', 'btn-primary'));
        btn.classList.add('active', 'btn-primary');
        _activeType = btn.dataset.type;
        _refresh();
      };
    });

    document.getElementById('btn-new-pol').onclick = () => _openForm(null);
    document.getElementById('pol-search').oninput = _refresh;
    document.getElementById('pol-status').onchange = _refresh;

    // Extraccion IA
    const aiBtn   = document.getElementById('btn-ai-extract');
    const aiInput = document.getElementById('pol-ai-input');
    aiBtn.onclick = () => aiInput.click();
    aiInput.onchange = async () => {
      const file = aiInput.files[0];
      if (!file) return;
      aiInput.value = '';
      aiBtn.disabled = true;
      aiBtn.textContent = 'Extrayendo...';
      try {
        const extracted = await Api.policies.aiExtract(file);
        UI.toast('Extraccion completada. Revisa los campos extraidos.', 'success');
        _openForm(null, extracted);
      } catch (e) {
        UI.toast('Error al extraer: ' + e.message, 'error');
      } finally {
        aiBtn.disabled = false;
        aiBtn.textContent = 'Extraer con IA';
      }
    };

    try { _users = await Api.listUsers(); } catch (_) { _users = []; }
    await _loadStats();
    await _refresh();
  }

  async function _loadStats() {
    try {
      const s = await Api.policies.summary();
      const wrap = document.getElementById('pol-stats');
      if (!wrap) return;
      wrap.innerHTML = `
        <div class="stat-card"><div class="stat-value">${s.total}</div><div class="stat-label">Total documentos</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-low);">${s.by_status.published||0}</div><div class="stat-label">Publicados</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.by_status.review||0}</div><div class="stat-label">En revision</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-high);">${s.overdue_review}</div><div class="stat-label">Revision vencida</div></div>
      `;
    } catch (_) {}
  }

  async function _refresh() {
    const q      = document.getElementById('pol-search')?.value || '';
    const status = document.getElementById('pol-status')?.value || '';
    const wrap   = document.getElementById('pol-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<p class="text-muted">Cargando...</p>';
    try {
      const params = {};
      if (q) params.q = q;
      if (status) params.status = status;
      if (_activeType !== 'all') params.category = _activeType;
      const data = await Api.policies.list(params);
      _renderTable(wrap, data);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _renderTable(wrap, data) {
    if (!data.length) {
      wrap.innerHTML = '<p class="text-muted" style="margin-top:24px;text-align:center;">No se encontraron documentos ISMS.</p>';
      return;
    }
    const now = new Date();
    const rows = data.map(p => {
      const reviewOverdue = p.review_date && p.status !== 'obsolete'
        && new Date(p.review_date) < now;
      const owner = _users.find(u => u.id === p.owner_id);
      return `
        <tr style="cursor:pointer;${reviewOverdue?'background:rgba(254,226,226,0.3);':''}" data-id="${p.id}">
          <td>${UI.codePill(p.code)}</td>
          <td>
            <b>${UI.esc(p.title)}</b>
            <div style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap;">
              ${_levelBadge(p.document_level || 1)}
              ${p.category ? _typeBadge(p.category) : ''}
            </div>
          </td>
          <td style="font-size:12px;font-family:var(--font-mono);">v${UI.esc(p.version)}</td>
          <td>${_badge(STATUS_LABELS[p.status]||p.status, STATUS_COLORS[p.status]||'#888')}</td>
          <td>${p.review_date ? `<span style="color:${reviewOverdue?'var(--risk-high)':'inherit'};font-weight:${reviewOverdue?'700':'400'};">${p.review_date.slice(0,10)}${reviewOverdue?' (VENCIDA)':''}</span>` : '-'}</td>
          <td style="font-size:12px;">${owner ? UI.esc(owner.full_name||owner.email) : '-'}</td>
          <td onclick="event.stopPropagation()">
            <button class="btn btn-sm" data-id="${p.id}" data-action="edit">Editar</button>
            <button class="btn btn-sm btn-danger" data-id="${p.id}" data-action="del">Eliminar</button>
          </td>
        </tr>`;
    }).join('');
    wrap.innerHTML = `
      <table class="data">
        <thead>
          <tr><th>Codigo</th><th>Titulo / Nivel</th><th>Version</th><th>Estado</th><th>Revision</th><th>Responsable</th><th>Acciones</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;

    wrap.querySelectorAll('tr[data-id]').forEach(tr =>
      tr.onclick = () => { const p = data.find(x => x.id == tr.dataset.id); if (p) _editPolicy(p); });
    wrap.querySelectorAll('[data-action="edit"]').forEach(btn =>
      btn.onclick = (e) => { e.stopPropagation(); const p = data.find(x => x.id == btn.dataset.id); if (p) _editPolicy(p); });
    wrap.querySelectorAll('[data-action="del"]').forEach(btn =>
      btn.onclick = async (e) => {
        e.stopPropagation();
        if (!confirm('Eliminar documento?')) return;
        try {
          await Api.policies.del(btn.dataset.id);
          UI.toast('Documento eliminado', 'success');
          await _loadStats(); await _refresh();
        } catch (e2) { UI.toast(e2.message, 'error'); }
      });
  }

  function _formHtml(p, extracted, allPolicies) {
    const v = p || {};
    const e = extracted || {};
    const title   = e.title   || v.title   || '';
    const version = e.version || v.version || '1.0';
    const category = e.category || v.category || '';
    const scope   = e.scope   || v.scope   || '';
    const content = e.content || v.content || '';
    const review  = e.review_date || (v.review_date ? v.review_date.slice(0,10) : '');
    const clauses = e.iso_clauses ? e.iso_clauses.join(', ') : (v.iso_clauses||[]).join(', ');
    const notes   = e.confidence_notes || '';
    const docLevel = v.document_level || 1;
    const parentId = v.parent_policy_id || '';

    // Normalizar category: si viene texto libre, intentar mapear a uno de los tipos estandar
    const normalizedCat = Object.keys(ISMS_TYPES).includes(category) ? category : '';

    // Construir opciones del selector de documento padre (excluir el propio doc)
    const parentOptions = (allPolicies || [])
      .filter(pp => !p || pp.id !== p.id)
      .map(pp => {
        const lvl = pp.document_level || 1;
        return `<option value="${pp.id}" ${parentId == pp.id ? 'selected' : ''}>[${lvl}] ${UI.esc(pp.code)} — ${UI.esc(pp.title)}</option>`;
      }).join('');

    return `
      <div class="form-grid">
        ${notes ? `<div class="span2"><div class="notice" style="margin-bottom:4px;font-size:12px;">Nota IA: ${UI.esc(notes)}</div></div>` : ''}
        <div class="span2"><label>Titulo *</label><input id="f-title" class="input" value="${UI.esc(title)}"></div>

        <div>
          <label>Nivel jerarquico
            <span title="Jerarquia ISO: Politica (alto nivel) > Norma (reglas) > Procedimiento (pasos) > Instruccion Tecnica (configuracion exacta)"
                  style="cursor:help;color:var(--text-muted);font-weight:400;font-size:11px;"> (?)</span>
          </label>
          <select id="f-doc-level" class="input" onchange="ViewPolicies._onLevelChange(this)">
            ${Object.entries(DOC_LEVEL_LABELS).map(([k, l]) =>
              `<option value="${k}" ${docLevel == k ? 'selected' : ''}>${k}. ${l} (max madurez ${DOC_LEVEL_MAX_MATURITY[k]}/5)</option>`
            ).join('')}
          </select>
          <div id="f-level-hint" style="font-size:11px;color:var(--text-muted);margin-top:3px;"></div>
        </div>

        <div>
          <label>Documento padre (jerarquia)</label>
          <select id="f-parent" class="input">
            <option value="">— Ninguno (documento raiz) —</option>
            ${parentOptions}
          </select>
          <div style="font-size:11px;color:var(--text-muted);margin-top:3px;">Una Norma referencia su Politica padre; un Procedimiento referencia su Norma padre.</div>
        </div>

        <div>
          <label>Tipo de documento ISMS</label>
          <select id="f-cat" class="input">
            <option value="">-- Sin clasificar --</option>
            ${Object.entries(ISMS_TYPES).map(([k, l]) =>
              `<option value="${k}" ${normalizedCat === k ? 'selected' : ''}>${l}</option>`
            ).join('')}
          </select>
          <div style="font-size:11px;color:var(--text-muted);margin-top:3px;">
            ${category && !normalizedCat ? `Tipo detectado por IA: "${UI.esc(category)}" — selecciona el mas adecuado.` : ''}
          </div>
        </div>
        <div>
          <label>Estado</label>
          <select id="f-status" class="input">
            ${Object.entries(STATUS_LABELS).map(([k,l]) => `<option value="${k}" ${(v.status||'draft')===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div><label>Version</label><input id="f-version" class="input" value="${UI.esc(version)}"></div>
        <div>
          <label>Responsable</label>
          <select id="f-owner" class="input">
            <option value="">— Sin asignar —</option>
            ${_users.map(u => `<option value="${u.id}" ${v.owner_id===u.id?'selected':''}>${UI.esc(u.full_name||u.email)}</option>`).join('')}
          </select>
        </div>
        <div><label>Fecha de revision</label><input type="date" id="f-review" class="input" value="${UI.esc(review)}"></div>
        <div><label>Clausulas ISO (separadas por coma)</label><input id="f-clauses" class="input" value="${UI.esc(clauses)}"></div>
        <div class="span2"><label>Alcance</label><textarea id="f-scope" class="input" rows="2">${UI.esc(scope)}</textarea></div>
        <div class="span2"><label>Contenido / resumen</label><textarea id="f-content" class="input" rows="5">${UI.esc(content)}</textarea></div>
        ${p && p.source_document_id ? `
        <div class="span2" style="padding-top:14px;border-top:1px solid var(--border);margin-top:4px;">
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-muted);
                      letter-spacing:.5px;margin-bottom:8px;">Analisis de madurez SGSI</div>
          <div id="pol-maturity-panel">
            <div style="font-size:12px;color:var(--text-muted);">Cargando analisis...</div>
          </div>
        </div>` : ''}
      </div>`;
  }

  function _bumpVersion(ver) {
    const parts = String(ver || '1.0').split('.');
    return (parseInt(parts[0] || '1') + 1) + '.0';
  }

  function _onLevelChange(sel) {
    const hint = document.getElementById('f-level-hint');
    if (!hint) return;
    const l = parseInt(sel.value) || 1;
    const hints = {
      1: 'Define la intencion y compromiso organizativo — alto nivel, sin detalles tecnicos.',
      2: 'Define las reglas de obligado cumplimiento para un area especifica.',
      3: 'Describe pasos detallados para ejecutar un proceso en una solucion concreta.',
      4: 'Proporciona configuraciones exactas y medibles para un sistema especifico.',
    };
    hint.textContent = hints[l] || '';
  }

  // ---------- Helpers de madurez para el panel inline ----------

  const _POL_MATURITY_COLORS = ['var(--risk-critical)','var(--risk-high)','var(--risk-medium)','var(--brand-orange)','#22c55e','var(--risk-low)'];
  const _POL_MATURITY_LABELS = ['Inexistente','Inicial','Basico','Definido','Gestionado','Optimizado'];

  function _polMaturityColor(v) { return _POL_MATURITY_COLORS[Math.min(5, Math.max(0, v))] || 'var(--text-muted)'; }

  function _polParseNotes(notes) {
    if (!notes) return { rationale: '', gap: '' };
    const sep = '\n\nPara llegar a nivel 5: ';
    const idx = notes.indexOf(sep);
    let rationale = notes, gap = '';
    if (idx >= 0) { rationale = notes.slice(0, idx); gap = notes.slice(idx + sep.length); }
    rationale = rationale.replace(/^Nivel actual \(\d+\/5\): /, '');
    return { rationale, gap };
  }

  const _POL_DEFAULT_GAP = [
    'Implementar el control desde cero: definir el proceso, documentarlo, asignar responsable, establecer metricas y revision periodica.',
    'Formalizar el proceso: crear documentacion oficial, establecer procedimientos escritos, comunicar a los equipos y medir resultados.',
    'Estandarizar la aplicacion: garantizar consistencia en todos los casos, implementar controles de calidad y medir la eficacia con KPIs.',
    'Añadir metricas: establecer KPIs, revisar resultados periodicamente, documentar excepciones y reducir variabilidad del proceso.',
    'Implementar mejora continua: analizar tendencias, automatizar donde sea posible, revisar benchmarks y documentar optimizaciones.',
    '',
  ];

  async function _loadPolicyMaturity(docId) {
    const panel = document.getElementById('pol-maturity-panel');
    if (!panel) return;
    let controls = [];
    try {
      controls = await Api.aiDocuments.controls(docId);
    } catch (_) {
      panel.innerHTML = '';
      return;
    }
    if (!controls.length) {
      panel.innerHTML = `<p style="font-size:12px;color:var(--text-muted);">Sin analisis ISMS disponible para este documento.</p>`;
      return;
    }
    const avg = controls.reduce((s, c) => s + (c.maturity || 0), 0) / controls.length;
    const avgColor = _polMaturityColor(Math.round(avg));
    const rows = controls.map(c => {
      const { rationale, gap } = _polParseNotes(c.notes);
      const displayGap = gap || _POL_DEFAULT_GAP[Math.min(4, c.maturity || 0)] || '';
      const color = _polMaturityColor(c.maturity || 0);
      const detId = `pm-det-${c.id}`;
      const bars = Array.from({length: 5}, (_, i) =>
        `<div style="width:10px;height:7px;border-radius:2px;background:${i < c.maturity ? color : 'var(--bg-3)'}"></div>`
      ).join('');
      return `
        <div style="border:1px solid var(--border);border-radius:6px;margin-bottom:5px;overflow:hidden;">
          <div onclick="const d=document.getElementById('${detId}');d.style.display=d.style.display==='none'?'block':'none';"
               style="display:flex;align-items:center;gap:8px;padding:7px 10px;cursor:pointer;
                      background:var(--bg-2);user-select:none;">
            <span style="font-size:10px;font-weight:700;color:var(--brand-purple);background:var(--brand-purple-4);
                         border-radius:3px;padding:1px 5px;white-space:nowrap;flex-shrink:0;">${UI.esc(c.control_code||'-')}</span>
            <span style="font-size:12px;font-weight:500;flex:1;overflow:hidden;text-overflow:ellipsis;
                         white-space:nowrap;" title="${UI.esc(c.control_name||'-')}">${UI.esc(c.control_name||'-')}</span>
            <div style="display:flex;gap:2px;flex-shrink:0;">${bars}</div>
            <span style="font-size:11px;font-weight:700;color:${color};white-space:nowrap;min-width:28px;
                         text-align:right;">${c.maturity||0}/5</span>
          </div>
          <div id="${detId}" style="display:none;padding:8px 12px;font-size:12px;line-height:1.6;background:var(--bg-card);">
            ${rationale ? `
              <div style="margin-bottom:7px;">
                <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);
                            letter-spacing:.4px;margin-bottom:3px;">Por que esta en nivel ${c.maturity||0}/5</div>
                <div style="background:var(--bg-2);border-left:3px solid ${color};
                            border-radius:0 4px 4px 0;padding:6px 10px;">${UI.esc(rationale)}</div>
              </div>` : ''}
            ${displayGap ? `
              <div>
                <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);
                            letter-spacing:.4px;margin-bottom:3px;">Para llegar a nivel 5</div>
                <div style="background:rgba(89,0,141,.05);border-left:3px solid var(--brand-purple);
                            border-radius:0 4px 4px 0;padding:6px 10px;">${UI.esc(displayGap)}</div>
              </div>` : ''}
            ${(!rationale && !displayGap) ? `
              <span style="font-size:11px;color:var(--text-muted);font-style:italic;">
                Re-analiza el documento en Agente IA para obtener el analisis personalizado.
              </span>` : ''}
          </div>
        </div>`;
    }).join('');

    panel.innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;padding:8px 12px;background:var(--bg-2);
                  border-radius:6px;margin-bottom:8px;">
        <div style="font-size:20px;font-weight:800;color:${avgColor};">${avg.toFixed(1)}</div>
        <div style="flex:1;">
          <div style="font-size:12px;font-weight:600;">Madurez aportada por este documento</div>
          <div style="font-size:11px;color:var(--text-muted);">
            ${controls.length} control${controls.length!==1?'es':''} en el alcance especifico de este documento
            &mdash; haz clic en cada uno para ver el gap
          </div>
        </div>
      </div>
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;padding:5px 8px;
                  background:rgba(89,0,141,.04);border-radius:4px;border:1px solid rgba(89,0,141,.1);">
        La madurez global de cada control se calcula agregando las contribuciones de TODOS los documentos del corpus.
        Este panel muestra solo lo que aporta este documento especifico segun su alcance y nivel.
      </div>
      ${rows}`;
  }

  function _editPolicy(p) {
    if (p.status === 'approved' || p.status === 'published') {
      _openVersioningModal(p);
    } else {
      _openForm(p);
    }
  }

  function _openVersioningModal(p) {
    const nextVer = _bumpVersion(p.version);
    UI.modal('Editar documento aprobado', `
      <p style="margin-bottom:10px;">El documento <strong>${UI.esc(p.code)}</strong> esta actualmente <strong>${STATUS_LABELS[p.status]||p.status}</strong> (v${UI.esc(p.version||'1.0')}).</p>
      <p style="font-size:13px;color:var(--text-subtle);margin-bottom:4px;">Al continuar se creara una nueva version <strong>v${UI.esc(nextVer)}</strong> en borrador con el mismo contenido. El documento actual permanecera vigente hasta que la nueva version sea aprobada, momento en que pasara automaticamente a estado <em>obsoleta</em>.</p>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-confirm-version">Crear version ${UI.esc(nextVer)}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-confirm-version').onclick = async () => {
      try {
        const draft = await Api.policies.newVersion(p.id);
        UI.toast(`Version ${draft.version} creada en borrador`, 'success');
        UI.closeModal();
        _openForm(draft);
        await _loadStats(); await _refresh();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  async function _openForm(p, extracted) {
    // Cargar lista de politicas para el selector de documento padre
    let allPolicies = [];
    try { allPolicies = await Api.policies.list({}); } catch (_) {}

    UI.modal(p ? `Editar ${p.code}` : 'Nuevo documento ISMS', _formHtml(p, extracted, allPolicies), {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick   = () => _save(p);
    // Inicializar hint del nivel actual
    const levelSel = document.getElementById('f-doc-level');
    if (levelSel) _onLevelChange(levelSel);
    if (p && p.source_document_id) _loadPolicyMaturity(p.source_document_id);
  }

  async function _save(p) {
    const title = document.getElementById('f-title').value.trim();
    if (!title) { UI.toast('El titulo es obligatorio', 'error'); return; }
    const clausesRaw = document.getElementById('f-clauses').value.trim();
    const ownerVal   = document.getElementById('f-owner').value;
    const parentVal  = document.getElementById('f-parent')?.value;
    const levelVal   = document.getElementById('f-doc-level')?.value;
    const payload = {
      title,
      version:    document.getElementById('f-version').value.trim() || '1.0',
      category:   document.getElementById('f-cat').value || null,
      status:     document.getElementById('f-status').value,
      review_date: document.getElementById('f-review').value || null,
      iso_clauses: clausesRaw ? clausesRaw.split(',').map(s => s.trim()).filter(Boolean) : [],
      scope:   document.getElementById('f-scope').value.trim(),
      content: document.getElementById('f-content').value.trim(),
      owner_id: ownerVal ? parseInt(ownerVal) : null,
      document_level: levelVal ? parseInt(levelVal) : 1,
      parent_policy_id: parentVal ? parseInt(parentVal) : null,
    };
    try {
      if (p) {
        await Api.policies.update(p.id, payload);
        UI.toast('Documento actualizado', 'success');
      } else {
        await Api.policies.create(payload);
        UI.toast('Documento creado', 'success');
      }
      UI.closeModal();
      await _loadStats(); await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  // ============================================================
  // Generacion libre con IA — T7
  // ============================================================

  async function _generateWithAI() {
    UI.openModal(`
      <div style="max-width:600px;">
        <h3 style="margin:0 0 4px;color:var(--brand-purple);font-size:17px;">Generar documento ISMS con IA</h3>
        <p style="font-size:12px;color:var(--text-muted);margin:0 0 18px;">
          El agente IA redactara un borrador adaptado a tu organizacion y al marco normativo elegido.
        </p>

        <div class="form-grid" style="gap:12px;">
          <div>
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Tipo de documento *</label>
            <select id="gen-type" class="input" style="width:100%;">
              <option value="politica">Politica de seguridad</option>
              <option value="norma">Norma</option>
              <option value="instruccion_tecnica">Instruccion tecnica</option>
            </select>
          </div>
          <div>
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Marco normativo</label>
            <select id="gen-framework" class="input" style="width:100%;">
              ${FRAMEWORKS.map(f => `<option value="${UI.esc(f.value)}">${UI.esc(f.label)}</option>`).join('')}
            </select>
          </div>
          <div class="span2">
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Titulo / asunto *</label>
            <input id="gen-title" class="input" style="width:100%;" placeholder="Ej: Politica de Gestion de Accesos">
          </div>
          <div class="span2">
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">Descripcion y alcance</label>
            <textarea id="gen-desc" class="input" rows="3" style="width:100%;"
                      placeholder="Describe el objetivo, alcance, departamentos afectados, contexto especifico..."></textarea>
          </div>
          <div class="span2">
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">
              Documentacion de contexto (opcional)
            </label>
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;
                          border:1px dashed var(--border);border-radius:6px;padding:8px 12px;
                          font-size:12px;color:var(--text-muted);">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              <span id="gen-file-label">Subir documento de referencia (PDF, DOCX, PNG, JPG)</span>
              <input type="file" id="gen-context-file" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
                     style="display:none;" onchange="ViewPolicies._onGenFileChange(this)">
            </label>
          </div>
        </div>

        <!-- Disclaimer -->
        <div style="margin-top:16px;background:#fff8e6;border:1px solid #f0c040;border-radius:8px;
                    padding:10px 14px;font-size:12px;color:#7a5800;line-height:1.5;">
          <strong>Aviso importante:</strong> El documento generado por IA es un borrador de apoyo.
          Debe ser revisado, completado y aprobado por una persona responsable de la organizacion
          antes de su publicacion o uso operativo.
        </div>

        <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;">
          <button onclick="UI.closeModal()" class="btn">Cancelar</button>
          <button onclick="ViewPolicies._submitGenerate()" class="btn"
                  style="background:linear-gradient(90deg,var(--brand-purple),var(--brand-orange));color:#fff;border:none;">
            Generar con IA
          </button>
        </div>
      </div>`);
  }

  function _onGenFileChange(input) {
    const label = document.getElementById('gen-file-label');
    if (label && input.files[0]) {
      label.textContent = input.files[0].name + ' (' + (input.files[0].size / 1024).toFixed(0) + ' KB)';
    }
  }

  async function _submitGenerate() {
    const title = document.getElementById('gen-title')?.value.trim();
    if (!title) { UI.toast('El titulo es obligatorio', 'error'); return; }

    const docType   = document.getElementById('gen-type')?.value;
    const framework = document.getElementById('gen-framework')?.value;
    const desc      = document.getElementById('gen-desc')?.value.trim();
    const fileInput = document.getElementById('gen-context-file');
    const file      = fileInput?.files[0] || null;

    UI.closeModal();
    UI.toast('Generando documento con IA...', 'info');

    try {
      const fd = new FormData();
      fd.append('doc_type',  docType);
      fd.append('title',     title);
      fd.append('framework', framework);
      if (desc)  fd.append('description', desc);
      if (file)  fd.append('context_file', file);

      const result = await Api.req('/api/policies/ai-generate-free', { method: 'POST', body: fd });

      UI.openModal(`
        <div style="max-width:700px;">
          <h3 style="margin:0 0 4px;color:var(--brand-purple);">${UI.esc(result.title)}</h3>
          <div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;">
            ${_typeBadge(result.category)}
            <span style="font-size:11px;color:var(--text-muted);align-self:center;">
              Marco: ${UI.esc(result.framework || framework)}
            </span>
          </div>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px;">
            Revisa el contenido antes de guardar. Puedes editarlo directamente.
          </p>
          <textarea id="gen-result-content" style="width:100%;height:340px;font-size:12px;
                    font-family:monospace;border:1px solid var(--border);border-radius:6px;padding:10px;
                    resize:vertical;">${UI.esc(result.content)}</textarea>
          <div style="margin-top:10px;background:#fff8e6;border:1px solid #f0c040;border-radius:6px;
                      padding:8px 12px;font-size:11px;color:#7a5800;">
            Este borrador ha sido generado por IA y debe ser revisado y aprobado por una persona responsable.
          </div>
          <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end;">
            <button onclick="UI.closeModal()" class="btn">Descartar</button>
            <button onclick="ViewPolicies._saveGenerated(${JSON.stringify({
              title: result.title,
              category: result.category || docType,
              iso_clauses: result.iso_clauses || [],
              framework,
            }).replace(/"/g,'&quot;')})"
                    class="btn btn-primary">Guardar como borrador</button>
          </div>
        </div>`);
    } catch (e) {
      UI.toast('Error generando: ' + e.message, 'error');
    }
  }

  async function _saveGenerated(meta) {
    const content = document.getElementById('gen-result-content')?.value || '';
    const payload = {
      title:       meta.title,
      content,
      category:    meta.category || null,
      iso_clauses: meta.iso_clauses || [],
      scope:       'Generado automaticamente con IA — revisar y adaptar',
      version:     '1.0',
      status:      'draft',
      review_cycle_months: 12,
    };
    try {
      await Api.policies.create(payload);
      UI.closeModal();
      UI.toast('Borrador guardado — revisa y aprueba antes de publicar', 'success');
      await _loadStats(); await _refresh();
    } catch (e) {
      UI.toast('Error guardando: ' + e.message, 'error');
    }
  }

  return { render, _generateWithAI, _onGenFileChange, _submitGenerate, _saveGenerated, _onLevelChange };
})();
