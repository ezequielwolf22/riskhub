/* Vista ISMS — Gestion Documental Unificada — ISO 27001 cl. 5.2
   Combina ViewPolicies (versionado, aprobacion, generador IA) y
   ViewAiDocuments (subida, indexado, analisis ISMS, madurez, gap). */

const ViewIsmsDocuments = (() => {

  // --- Constantes ---

  const STATUS_LABELS = {
    draft: 'Borrador', review: 'En revision', approved: 'Aprobada',
    published: 'Publicada', obsolete: 'Obsoleta',
  };
  const STATUS_COLORS = {
    draft: 'var(--text-muted)', review: 'var(--brand-orange)',
    approved: 'var(--brand-purple)', published: 'var(--risk-low)', obsolete: '#aaa',
  };
  const DOC_LEVEL_LABELS = {
    1: 'Politica', 2: 'Norma / Estandar', 3: 'Procedimiento', 4: 'Instruccion Tecnica',
  };
  const DOC_LEVEL_SHORT = { 1: 'Politica', 2: 'Norma', 3: 'Procedimiento', 4: 'Instruccion' };
  const DOC_LEVEL_COLORS = {
    1: 'var(--brand-purple)', 2: 'var(--brand-orange)', 3: '#0891b2', 4: '#16a34a',
  };
  const DOC_LEVEL_MAX_MATURITY = { 1: 2, 2: 3, 3: 4, 4: 5 };
  const ISMS_TYPES = {
    politica: 'Politica', norma: 'Norma',
    instruccion_tecnica: 'Instruccion tecnica', evidencia: 'Otra evidencia',
  };
  const ISMS_TYPE_COLORS = {
    politica: 'var(--brand-purple)', norma: 'var(--brand-orange)',
    instruccion_tecnica: '#0891b2', evidencia: '#6b7280',
  };
  const FILE_STATUS_LABELS = {
    indexed: 'Indexado', processing: 'Procesando', pending: 'Pendiente', error: 'Error',
  };
  const FILE_STATUS_COLORS = {
    indexed: 'var(--risk-low)', processing: 'var(--brand-orange)',
    pending: 'var(--text-muted)', error: 'var(--risk-critical)',
  };
  const ISMS_STATUS_LABELS = {
    analysing: 'Analizando...', analysed: 'Analizado', skipped: 'Sin IA', error: 'Error IA',
  };
  const ISMS_STATUS_COLORS = {
    analysing: 'var(--brand-orange)', analysed: 'var(--risk-low)',
    skipped: 'var(--text-muted)', error: 'var(--risk-critical)',
  };
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
  const CATEGORY_LABELS = {
    architecture:       'Arquitectura y sistemas',
    normative:          'Normativa y compliance',
    policies:           'Politicas y procedimientos',
    assets_inventory:   'Inventario de activos',
    risk_assessments:   'Evaluaciones de riesgo',
    critical_suppliers: 'Proveedores criticos',
    incidents_lessons:  'Incidentes y lecciones',
    other:              'Otros',
  };
  const ACCEPTED_EXTS = ['pdf', 'docx', 'txt', 'csv', 'jpg', 'jpeg', 'png'];

  // Niveles de madurez CMM
  const MATURITY_LABELS = ['Inexistente', 'Inicial', 'Basico', 'Definido', 'Gestionado', 'Optimizado'];

  // --- Estado ---

  let _docs     = [];   // AiDocument[]
  let _policies = [];   // Policy[]
  let _merged   = [];   // filas combinadas
  let _users    = [];
  let _filter   = 'all';
  let _searchQ  = '';
  let _statusFilter = '';
  let _queue    = [];
  let _queueId  = 0;
  let _uploading = false;
  let _pollTimer = null;

  // --- Helpers visuales ---

  function _levelBadge(level) {
    const l = parseInt(level) || 1;
    const label = DOC_LEVEL_SHORT[l] || 'Politica';
    const color = DOC_LEVEL_COLORS[l] || 'var(--brand-purple)';
    return `<span title="${DOC_LEVEL_LABELS[l]}" style="display:inline-block;padding:1px 6px;border-radius:999px;font-size:10px;font-weight:700;background:${color}18;color:${color};border:1px solid ${color}40;">${l}. ${label}</span>`;
  }

  function _statusBadge(status) {
    if (!status) return '';
    const color = STATUS_COLORS[status] || '#888';
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(STATUS_LABELS[status] || status)}</span>`;
  }

  function _typeBadge(cat) {
    if (!cat) return '';
    const label = ISMS_TYPES[cat] || UI.esc(cat);
    const color = ISMS_TYPE_COLORS[cat] || '#888';
    return `<span style="display:inline-block;padding:1px 7px;border-radius:999px;font-size:10px;font-weight:700;background:${color}20;color:${color};border:1px solid ${color}40;">${label}</span>`;
  }

  function _maturityColor(v) {
    if (v >= 5) return 'var(--risk-low)';
    if (v >= 4) return '#22c55e';
    if (v >= 3) return 'var(--risk-medium)';
    if (v >= 2) return 'var(--risk-high)';
    return 'var(--risk-critical)';
  }

  // --- Carga y fusion de datos ---

  async function _load() {
    try { _docs     = await Api.aiDocuments.list(); } catch (_) { _docs = []; }
    try { _policies = await Api.policies.list({});  } catch (_) { _policies = []; }
    _merged = _buildMerged();
  }

  function _buildMerged() {
    const rows = [];
    const coveredPolicyIds = new Set();

    // Paso 1: cada AiDocument, con su Policy vinculada (si existe)
    for (const doc of _docs) {
      const policyId = doc.isms_policy_id || (doc.isms_summary && doc.isms_summary.policy_id);
      const policy = policyId ? _policies.find(p => p.id === policyId) : null;
      if (policy) coveredPolicyIds.add(policy.id);
      const level = policy
        ? (policy.document_level || 1)
        : (doc.isms_summary && doc.isms_summary.document_level) || null;
      rows.push({ type: policy ? 'unified' : 'doc_only', doc, policy: policy || null, level });
    }

    // Paso 2: Policies sin AiDocument vinculado
    for (const policy of _policies) {
      if (!coveredPolicyIds.has(policy.id)) {
        rows.push({ type: 'policy_only', doc: null, policy, level: policy.document_level || 1 });
      }
    }

    return rows;
  }

  function _filteredMerged() {
    let rows = _merged;

    if (_filter === 'no_doc') {
      rows = rows.filter(r => r.type === 'policy_only');
    } else if (_filter === 'no_policy') {
      rows = rows.filter(r => r.type === 'doc_only');
    } else if (_filter !== 'all') {
      const lvl = parseInt(_filter);
      if (lvl) rows = rows.filter(r => r.level === lvl);
    }

    if (_searchQ) {
      const q = _searchQ.toLowerCase();
      rows = rows.filter(r => {
        const title = (r.policy && r.policy.title) || (r.doc && r.doc.original_name) || '';
        const code  = (r.policy && r.policy.code)  || '';
        return title.toLowerCase().includes(q) || code.toLowerCase().includes(q);
      });
    }

    if (_statusFilter) {
      rows = rows.filter(r => r.policy && r.policy.status === _statusFilter);
    }

    return rows;
  }

  // --- Render principal ---

  async function render(el) {
    _stopPoll();
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Documentos ISMS</h1>
          <p class="page-sub">Gestion documental unificada — ISO 27001 cl. 5.2 — Politicas, normas, procedimientos e instrucciones tecnicas</p>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <input type="file" id="isms-ai-input" accept=".pdf,.docx,.txt" style="display:none;">
          <button class="btn" id="btn-isms-ai-extract" title="Cargar un documento y extraer los campos con IA">
            Extraer con IA
          </button>
          <button onclick="ViewIsmsDocuments._generateWithAI()" class="btn"
                  style="background:linear-gradient(90deg,var(--brand-purple),var(--brand-orange));color:#fff;border:none;">
            Generar con IA
          </button>
          <button class="btn btn-primary" id="btn-isms-new-pol">+ Nuevo registro</button>
        </div>
      </div>
      <div id="isms-root"></div>`;

    const aiBtn   = document.getElementById('btn-isms-ai-extract');
    const aiInput = document.getElementById('isms-ai-input');
    aiBtn.onclick = () => aiInput.click();
    aiInput.onchange = async () => {
      const file = aiInput.files[0];
      if (!file) return;
      aiInput.value = '';
      aiBtn.disabled = true; aiBtn.textContent = 'Extrayendo...';
      try {
        const extracted = await Api.policies.aiExtract(file);
        UI.toast('Extraccion completada. Revisa los campos.', 'success');
        _openFormEnhanced(null, extracted);
      } catch (e) {
        UI.toast('Error al extraer: ' + e.message, 'error');
      } finally {
        aiBtn.disabled = false; aiBtn.textContent = 'Extraer con IA';
      }
    };

    document.getElementById('btn-isms-new-pol').onclick = () => _openFormEnhanced(null);

    try { _users = await Api.listUsers(); } catch (_) { _users = []; }
    await _load();
    _renderRoot();
    _startPollIfNeeded();
  }

  // --- Construccion de la UI ---

  function _renderRoot() {
    const root = document.getElementById('isms-root');
    if (!root) return;

    const totalDocs    = _docs.length;
    const indexedDocs  = _docs.filter(d => d.status === 'indexed').length;
    const analysedDocs = _docs.filter(d => d.isms_status === 'analysed').length;
    const totalPolicies = _policies.length;
    const now = new Date();
    const overdueCount = _policies.filter(p =>
      p.review_date && p.status !== 'obsolete' && new Date(p.review_date) < now
    ).length;

    const byLevel   = { 1: 0, 2: 0, 3: 0, 4: 0 };
    const noDocCnt  = _merged.filter(r => r.type === 'policy_only').length;
    const noPolicyCnt = _merged.filter(r => r.type === 'doc_only').length;
    _merged.forEach(r => { if (r.level) byLevel[r.level] = (byLevel[r.level] || 0) + 1; });

    root.innerHTML = `
      <!-- Stats -->
      <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px;">
        <div class="card" style="text-align:center;padding:12px;">
          <div style="font-size:22px;font-weight:700;color:var(--brand-purple);">${_merged.length}</div>
          <div style="font-size:11px;color:var(--text-muted);">Total entradas</div>
        </div>
        <div class="card" style="text-align:center;padding:12px;">
          <div style="font-size:22px;font-weight:700;color:var(--risk-low);">${totalPolicies}</div>
          <div style="font-size:11px;color:var(--text-muted);">Registros ISMS</div>
        </div>
        <div class="card" style="text-align:center;padding:12px;">
          <div style="font-size:22px;font-weight:700;color:var(--risk-low);">${indexedDocs}</div>
          <div style="font-size:11px;color:var(--text-muted);">Archivos indexados</div>
        </div>
        <div class="card" style="text-align:center;padding:12px;">
          <div style="font-size:22px;font-weight:700;color:var(--brand-orange);">${analysedDocs}</div>
          <div style="font-size:11px;color:var(--text-muted);">Analizados ISMS</div>
        </div>
        <div class="card" style="text-align:center;padding:12px;">
          <div style="font-size:22px;font-weight:700;color:${overdueCount > 0 ? 'var(--risk-high)' : 'var(--text-muted)'};">${overdueCount}</div>
          <div style="font-size:11px;color:var(--text-muted);">Revision vencida</div>
        </div>
      </div>

      <!-- Zona de subida -->
      <div id="isms-upload-section" style="margin-bottom:14px;">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <label class="btn btn-primary" style="cursor:pointer;font-size:13px;"
                 title="Selecciona uno o varios archivos (PDF, DOCX, TXT, CSV, JPG, PNG)">
            + Subir documentos
            <input type="file" id="isms-file-input"
                   accept=".pdf,.docx,.txt,.csv,.jpg,.jpeg,.png" multiple style="display:none;">
          </label>
          ${indexedDocs > 0 ? `
          <button class="btn btn-ghost" id="isms-analyze-pending-btn" style="font-size:12px;"
                  onclick="ViewIsmsDocuments._analyzePending()"
                  title="Analiza documentos pendientes y resetea los atascados">
            Analizar pendientes
          </button>
          <button class="btn btn-ghost" id="isms-analyze-all-btn" style="font-size:12px;"
                  onclick="ViewIsmsDocuments._analyzeAll()"
                  title="Re-analizar TODOS los documentos indexados">
            Re-analizar todos (${indexedDocs})
          </button>` : ''}
        </div>

        <!-- Zona de arrastre -->
        <div id="isms-dropzone"
             style="display:none;border:2px dashed var(--border);border-radius:10px;
                    padding:24px 20px;text-align:center;margin-top:10px;cursor:pointer;
                    transition:all .15s;color:var(--text-muted);font-size:13px;">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.5" style="display:inline-block;vertical-align:middle;opacity:.5;margin-bottom:6px;">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg><br>
          Arrastra aqui uno o varios documentos (PDF, DOCX, TXT, CSV, JPG, PNG)<br>
          <span style="font-size:11px;">o usa el boton "Subir documentos"</span>
        </div>
        <div id="isms-queue"></div>
      </div>

      <!-- Filtros por nivel -->
      <div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;
                  border-bottom:1px solid var(--border);padding-bottom:10px;">
        <button class="btn ${_filter === 'all' ? 'btn-primary' : ''} isms-lvl-tab" data-f="all">
          Todos (${_merged.length})
        </button>
        ${[1, 2, 3, 4].map(l => {
          const n = byLevel[l] || 0;
          return n > 0
            ? `<button class="btn ${_filter == l ? 'btn-primary' : ''} isms-lvl-tab" data-f="${l}">
                ${l}. ${DOC_LEVEL_SHORT[l]} (${n})
               </button>` : '';
        }).join('')}
        ${noDocCnt > 0 ? `
        <button class="btn ${_filter === 'no_doc' ? 'btn-primary' : ''} isms-lvl-tab" data-f="no_doc"
                title="Registros ISMS sin archivo subido">
          Sin archivo (${noDocCnt})
        </button>` : ''}
        ${noPolicyCnt > 0 ? `
        <button class="btn ${_filter === 'no_policy' ? 'btn-primary' : ''} isms-lvl-tab" data-f="no_policy"
                title="Archivos subidos sin registro ISMS asociado aun">
          Sin registro (${noPolicyCnt})
        </button>` : ''}
      </div>

      <!-- Busqueda y filtro de estado -->
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <input type="search" id="isms-search" class="input" style="width:220px;"
               placeholder="Buscar por titulo o codigo..." value="${UI.esc(_searchQ)}">
        <select id="isms-status-filter" class="input" style="width:160px;">
          <option value="">Todos los estados</option>
          ${Object.entries(STATUS_LABELS).map(([k, l]) =>
            `<option value="${k}" ${_statusFilter === k ? 'selected' : ''}>${l}</option>`
          ).join('')}
        </select>
      </div>

      <!-- Tabla unificada -->
      <div id="isms-table-wrap"></div>
    `;

    // Tabs de nivel
    root.querySelectorAll('.isms-lvl-tab').forEach(btn => {
      btn.onclick = () => { _filter = btn.dataset.f; _renderRoot(); };
    });

    // Busqueda y estado
    root.querySelector('#isms-search').oninput   = (e) => { _searchQ = e.target.value; _renderTable(); };
    root.querySelector('#isms-status-filter').onchange = (e) => { _statusFilter = e.target.value; _renderTable(); };

    // Upload file input
    const fileInput = document.getElementById('isms-file-input');
    if (fileInput) {
      fileInput.onchange = (e) => {
        _addFilesToQueue(Array.from(e.target.files));
        e.target.value = '';
      };
    }

    // Dropzone
    const dropzone = document.getElementById('isms-dropzone');
    if (dropzone) {
      dropzone.onclick = () => fileInput && fileInput.click();
      dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.style.borderColor = 'var(--brand-purple)';
        dropzone.style.background  = 'var(--brand-purple-4)';
        dropzone.style.color       = 'var(--brand-purple)';
      });
      dropzone.addEventListener('dragleave', (e) => {
        if (!dropzone.contains(e.relatedTarget)) {
          dropzone.style.borderColor = '';
          dropzone.style.background  = '';
          dropzone.style.color       = '';
        }
      });
      dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.style.borderColor = '';
        dropzone.style.background  = '';
        dropzone.style.color       = '';
        _addFilesToQueue(Array.from(e.dataTransfer.files));
        dropzone.style.display = 'none';
      });
    }

    // Drag global sobre toda la seccion
    const uploadSection = document.getElementById('isms-upload-section');
    if (uploadSection) {
      uploadSection.addEventListener('dragover', (e) => {
        e.preventDefault();
        if (dropzone) dropzone.style.display = 'block';
      });
    }

    _renderQueue();
    _renderTable();
  }

  // --- Tabla unificada ---

  function _renderTable() {
    const wrap = document.getElementById('isms-table-wrap');
    if (!wrap) return;
    const rows = _filteredMerged();

    if (!rows.length) {
      wrap.innerHTML = '<p class="text-muted" style="text-align:center;margin-top:24px;">No se encontraron documentos.</p>';
      return;
    }

    const now = new Date();
    const tableRows = rows.map(item => {
      const { type, doc, policy, level } = item;
      const effectiveLevel = level;
      const title      = policy ? policy.title : (doc ? doc.original_name : '-');
      const code       = policy ? policy.code  : null;
      const version    = policy ? policy.version : null;
      const status     = policy ? policy.status  : null;
      const reviewDate = policy ? policy.review_date : null;
      const reviewOverdue = reviewDate && status !== 'obsolete' && new Date(reviewDate) < now;
      const owner = policy ? _users.find(u => u.id === policy.owner_id) : null;

      // Columna archivo
      let fileCellHtml;
      if (doc) {
        const fc = FILE_STATUS_COLORS[doc.status] || 'var(--text-muted)';
        const fl = FILE_STATUS_LABELS[doc.status] || doc.status;
        fileCellHtml = `<span style="font-size:11px;font-weight:600;color:${fc};">${fl}</span>`;
        if (doc.error_message) {
          fileCellHtml += `<br><span style="font-size:10px;color:var(--risk-critical);"
            title="${UI.esc(doc.error_message)}">Ver error</span>`;
        }
      } else {
        fileCellHtml = `<span style="font-size:11px;color:var(--text-muted);"
          title="Sube el archivo correspondiente con el boton Subir documentos">Sin archivo</span>`;
      }

      // Columna analisis ISMS
      let ismsCellHtml;
      if (doc && doc.isms_status) {
        const ic = ISMS_STATUS_COLORS[doc.isms_status] || 'var(--text-muted)';
        const il = ISMS_STATUS_LABELS[doc.isms_status] || doc.isms_status;
        const tooltip = doc.isms_summary_text ? ` title="${UI.esc(doc.isms_summary_text.slice(0, 200))}"` : '';
        ismsCellHtml = `<span style="font-size:11px;font-weight:600;color:${ic};"${tooltip}>${il}</span>`;
        if (doc.isms_status === 'analysing') {
          ismsCellHtml += ' <span style="font-size:10px;color:var(--text-muted);">&#8635;</span>';
        }
      } else if (doc && doc.status === 'indexed') {
        ismsCellHtml = `<span style="font-size:11px;color:var(--text-muted);">Pendiente</span>`;
      } else {
        ismsCellHtml = '<span style="font-size:11px;color:var(--text-muted);">-</span>';
      }

      // Columna controles/madurez
      let controlsHtml = '-';
      if (doc && doc.isms_controls_updated > 0) {
        controlsHtml = `<span onclick="ViewIsmsDocuments._showMaturityModal(${doc.id})"
          style="cursor:pointer;font-size:11px;color:var(--brand-purple);text-decoration:underline;"
          title="Ver madurez y gap analysis por control">
          ${doc.isms_controls_updated} ctrl
        </span>`;
        if (doc.extracted_clauses && doc.extracted_clauses.length > 0) {
          controlsHtml += `<br><span onclick="ViewIsmsDocuments._showClauses(${doc.id})"
            style="cursor:pointer;font-size:10px;color:var(--brand-orange);text-decoration:underline;">
            ${doc.extracted_clauses.length} clausulas
          </span>`;
        }
      }

      // Acciones
      const actions = [];
      if (policy) {
        actions.push(`<button class="btn btn-sm" onclick="ViewIsmsDocuments._editPolicy(${policy.id})">Editar</button>`);
      }
      if (doc && doc.status === 'indexed') {
        if (!doc.isms_status || doc.isms_status === 'error' || doc.isms_status === 'skipped') {
          actions.push(`<button class="btn btn-sm btn-ghost" onclick="ViewIsmsDocuments._analyze(${doc.id})">Analizar</button>`);
        } else if (doc.isms_status === 'analysed') {
          actions.push(`<button class="btn btn-sm btn-ghost" onclick="ViewIsmsDocuments._analyze(${doc.id})">Re-analizar</button>`);
        }
        if (doc.isms_controls_updated > 0) {
          actions.push(`<button class="btn btn-sm btn-ghost" onclick="ViewIsmsDocuments._showMaturityModal(${doc.id})">Madurez</button>`);
        }
      } else if (doc && (doc.status === 'error' || doc.status === 'pending')) {
        actions.push(`<button class="btn btn-sm btn-ghost" onclick="ViewIsmsDocuments._reprocess(${doc.id})">Reprocesar</button>`);
      }
      if (policy) {
        actions.push(`<button class="btn btn-sm btn-danger" onclick="ViewIsmsDocuments._deletePolicy(${policy.id})">Eliminar</button>`);
      } else if (doc) {
        actions.push(`<button class="btn btn-sm btn-danger" onclick="ViewIsmsDocuments._deleteDoc(${doc.id})">Eliminar</button>`);
      }

      // Indicador de tipo de fila
      const typeTag = type === 'policy_only'
        ? `<span style="font-size:9px;background:#6b728018;color:#6b7280;border:1px solid #6b728030;
                        border-radius:3px;padding:1px 4px;margin-left:4px;vertical-align:middle;">SIN ARCHIVO</span>`
        : type === 'doc_only'
        ? `<span style="font-size:9px;background:var(--brand-orange)18;color:var(--brand-orange);
                        border:1px solid var(--brand-orange)30;border-radius:3px;padding:1px 4px;
                        margin-left:4px;vertical-align:middle;">SIN REGISTRO</span>`
        : '';

      const rowStyle = reviewOverdue ? 'background:rgba(254,226,226,0.3);' : '';

      return `
        <tr style="${rowStyle}">
          <td>${effectiveLevel ? _levelBadge(effectiveLevel) : '<span style="font-size:11px;color:var(--text-muted);">-</span>'}</td>
          <td style="max-width:320px;">
            ${code ? `<div style="font-size:10px;font-family:var(--font-mono);color:var(--brand-purple);font-weight:700;margin-bottom:2px;">${UI.esc(code)}</div>` : ''}
            <div style="font-size:13px;font-weight:600;">
              ${UI.esc(title)}${typeTag}
            </div>
            ${policy && policy.category ? `<div style="margin-top:3px;">${_typeBadge(policy.category)}</div>` : ''}
          </td>
          <td style="font-size:12px;font-family:var(--font-mono);">${version ? 'v' + UI.esc(version) : '-'}</td>
          <td>${status ? _statusBadge(status) : '-'}</td>
          <td>${fileCellHtml}</td>
          <td>${ismsCellHtml}</td>
          <td>${controlsHtml}</td>
          <td style="font-size:12px;">
            ${reviewDate
              ? `<span style="color:${reviewOverdue ? 'var(--risk-high)' : 'inherit'};font-weight:${reviewOverdue ? '700' : '400'};">
                   ${reviewDate.slice(0, 10)}${reviewOverdue ? '<br><small>(VENCIDA)</small>' : ''}
                 </span>`
              : '-'}
          </td>
          <td onclick="event.stopPropagation()" style="white-space:nowrap;">
            <div style="display:flex;gap:3px;flex-wrap:wrap;">${actions.join('')}</div>
          </td>
        </tr>`;
    }).join('');

    wrap.innerHTML = `
      <div class="card" style="padding:0;overflow:hidden;">
        <table class="data">
          <thead>
            <tr>
              <th>Nivel</th>
              <th>Codigo / Titulo</th>
              <th>Version</th>
              <th>Estado</th>
              <th>Archivo</th>
              <th>Analisis ISMS</th>
              <th>Controles</th>
              <th>Revision</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>${tableRows}</tbody>
        </table>
      </div>`;
  }

  // --- Cola de subida ---

  function _guessCategoryFromName(filename) {
    const n = filename.toLowerCase().replace(/[_\-\.]/g, ' ');
    if (/politic|policy|procedur|instruc|manual|proceso|reglamento interno/.test(n)) return 'policies';
    if (/arquitect|topolog|diagrama|network|infraestruc|red corp|architecture/.test(n)) return 'architecture';
    if (/normativ|compliance|nis2|gdpr|rgpd|iso\s?27|directiva|reglamento|boe|legisl/.test(n)) return 'normative';
    if (/incidente|incident|postmortem|leccion|lesson|forense|analisis forense/.test(n)) return 'incidents_lessons';
    if (/inventario|inventory|activo|asset|cmdb|hardware|software|catalogo/.test(n)) return 'assets_inventory';
    if (/proveedor|supplier|vendor|tercero|contrato|sla|dpa|acuerdo/.test(n)) return 'critical_suppliers';
    if (/riesgo|risk|evaluac|assessment|amenaza|vulnerabilid|dpia|impacto/.test(n)) return 'risk_assessments';
    return 'other';
  }

  function _addFilesToQueue(files) {
    let added = 0;
    for (const file of files) {
      const ext = file.name.split('.').pop().toLowerCase();
      if (!ACCEPTED_EXTS.includes(ext)) {
        UI.toast(`${file.name}: formato no soportado.`, 'error');
        continue;
      }
      const alreadyPending = _queue.some(q => q.file.name === file.name && q.status === 'pending');
      if (alreadyPending) continue;
      _queue.push({ id: ++_queueId, file, category: _guessCategoryFromName(file.name), status: 'pending', error: null });
      added++;
    }
    if (added > 0) _renderQueue();
  }

  function _renderQueue() {
    const container = document.getElementById('isms-queue');
    if (!container) return;
    if (!_queue.length) { container.innerHTML = ''; return; }

    const pending = _queue.filter(q => q.status === 'pending');
    const active  = _queue.filter(q => q.status !== 'pending');

    container.innerHTML = `
      <div class="card" style="margin-top:10px;margin-bottom:14px;padding:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <strong style="font-size:14px;">Cola de subida
            <span style="font-weight:400;font-size:12px;color:var(--text-muted);">— ${_queue.length} archivo${_queue.length !== 1 ? 's' : ''}</span>
          </strong>
          ${pending.length > 0 && !_uploading ? `
            <div style="display:flex;gap:8px;">
              <button class="btn btn-ghost" style="font-size:12px;" id="isms-clear-queue">Limpiar pendientes</button>
              <button class="btn btn-primary" style="font-size:12px;" id="isms-upload-all">
                Subir ${pending.length} documento${pending.length !== 1 ? 's' : ''}
              </button>
            </div>` : ''}
        </div>
        <div style="display:flex;flex-direction:column;gap:6px;">
          ${_queue.map(item => {
            const isDone    = item.status === 'done';
            const isError   = item.status === 'error';
            const isPending = item.status === 'pending';
            const isUploading = item.status === 'uploading';
            const ext  = item.file.name.split('.').pop().toUpperCase();
            const size = item.file.size < 1024 * 1024
              ? (item.file.size / 1024).toFixed(0) + ' KB'
              : (item.file.size / 1024 / 1024).toFixed(1) + ' MB';
            const statusIcon = isDone
              ? `<span style="color:var(--risk-low);">&#10003; Subido</span>`
              : isError
              ? `<span style="color:var(--risk-critical);" title="${UI.esc(item.error || '')}">&#10007; Error</span>`
              : isUploading
              ? `<span style="color:var(--brand-orange);">Subiendo...</span>` : '';
            return `
              <div style="display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:6px;
                          background:var(--bg-2);border:1px solid ${isError ? 'var(--risk-critical)' : isDone ? 'var(--risk-low)' : 'var(--border)'};
                          opacity:${isDone ? '.65' : '1'};">
                <span style="font-size:10px;font-weight:700;background:var(--brand-purple-4);color:var(--brand-purple);
                             border-radius:3px;padding:1px 5px;flex-shrink:0;">${ext}</span>
                <span style="flex:1;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
                      title="${UI.esc(item.file.name)}">${UI.esc(item.file.name)}</span>
                <span style="font-size:11px;color:var(--text-subtle);flex-shrink:0;">${size}</span>
                ${isPending ? `
                  <select class="input" style="font-size:11px;padding:3px 6px;height:auto;min-width:180px;flex-shrink:0;"
                          onchange="ViewIsmsDocuments._setQueueCat(${item.id}, this.value)">
                    <option value="other" ${item.category === 'other' ? 'selected' : ''}>Auto (IA detecta)</option>
                    ${Object.entries(CATEGORY_LABELS).filter(([v]) => v !== 'other').map(([v, l]) =>
                      `<option value="${v}" ${item.category === v ? 'selected' : ''}>${l}</option>`
                    ).join('')}
                  </select>
                  <button class="btn btn-ghost" style="font-size:11px;padding:2px 8px;color:var(--risk-critical);flex-shrink:0;"
                          onclick="ViewIsmsDocuments._removeFromQueue(${item.id})">&#10005;</button>
                ` : `
                  <span style="font-size:11px;color:var(--text-muted);flex-shrink:0;min-width:160px;">${CATEGORY_LABELS[item.category] || item.category}</span>
                  <span style="min-width:80px;text-align:right;flex-shrink:0;font-size:12px;">${statusIcon}</span>
                `}
              </div>`;
          }).join('')}
        </div>
        ${!_uploading && active.length > 0 ? `
          <div style="margin-top:10px;text-align:right;">
            <button class="btn btn-ghost" style="font-size:12px;" id="isms-dismiss-done">Limpiar completados</button>
          </div>` : ''}
      </div>`;

    const btnUpload  = document.getElementById('isms-upload-all');
    if (btnUpload)  btnUpload.onclick  = _startUploadAll;
    const btnClear   = document.getElementById('isms-clear-queue');
    if (btnClear)   btnClear.onclick   = () => { _queue = _queue.filter(q => q.status !== 'pending'); _renderQueue(); };
    const btnDismiss = document.getElementById('isms-dismiss-done');
    if (btnDismiss) btnDismiss.onclick = () => { _queue = _queue.filter(q => q.status !== 'done'); _renderQueue(); };
  }

  async function _startUploadAll() {
    if (_uploading) return;
    const pending = _queue.filter(q => q.status === 'pending');
    if (!pending.length) return;
    _uploading = true;
    _renderQueue();

    let ok = 0, fail = 0;
    for (const item of pending) {
      item.status = 'uploading';
      _renderQueue();
      try {
        await Api.aiDocuments.upload(item.file, item.category);
        item.status = 'done'; ok++;
      } catch (e) {
        item.status = 'error'; item.error = e.message || 'Error desconocido'; fail++;
      }
      _renderQueue();
    }

    _uploading = false;
    await _load();
    if (ok > 0 && fail === 0) {
      UI.toast(`${ok} documento${ok !== 1 ? 's' : ''} subido${ok !== 1 ? 's' : ''} — analisis ISMS iniciado`, 'success');
    } else if (ok > 0) {
      UI.toast(`${ok} subidos, ${fail} con error`, 'error');
    } else {
      UI.toast('Error al subir los documentos', 'error');
    }
    _renderQueue();
    _renderRoot();
    _startPollIfNeeded();
  }

  // --- Polling para documentos en analisis ---

  function _startPollIfNeeded() {
    _stopPoll();
    if (!_docs.some(d => d.isms_status === 'analysing')) return;
    _pollTimer = setInterval(async () => {
      await _load();
      _renderRoot();
      if (!_docs.some(d => d.isms_status === 'analysing')) _stopPoll();
    }, 4000);
  }

  function _stopPoll() {
    if (_pollTimer !== null) { clearInterval(_pollTimer); _pollTimer = null; }
  }

  // --- Acciones sobre documentos ---

  function _setQueueCat(id, value) {
    const item = _queue.find(q => q.id === id);
    if (item) item.category = value;
  }

  function _removeFromQueue(id) {
    _queue = _queue.filter(q => q.id !== id);
    _renderQueue();
  }

  async function _analyze(docId) {
    try {
      await Api.aiDocuments.analyze(docId);
      await _load(); _renderRoot();
      UI.toast('Analisis ISMS iniciado', 'success');
      _startPollIfNeeded();
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  async function _reprocess(docId) {
    try {
      await Api.aiDocuments.reprocess(docId);
      await _load(); _renderRoot();
      UI.toast('Documento reprocesado', 'success');
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  async function _deleteDoc(docId) {
    if (!confirm('Eliminar este archivo del indice?')) return;
    try {
      await Api.aiDocuments.del(docId);
      await _load(); _renderRoot();
      UI.toast('Archivo eliminado', 'success');
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  async function _deletePolicy(policyId) {
    if (!confirm('Eliminar este registro ISMS?')) return;
    try {
      await Api.policies.del(policyId);
      await _load(); _renderRoot();
      UI.toast('Registro eliminado', 'success');
    } catch (e) { UI.toast('Error: ' + e.message, 'error'); }
  }

  async function _analyzePending() {
    const btn = document.getElementById('isms-analyze-pending-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Iniciando...'; }
    try {
      const res = await Api.aiDocuments.analyzePending();
      await _load(); _renderRoot();
      const msg = res.stuck_reset > 0
        ? `${res.stuck_reset} atascados reseteados. ${res.queued} en cola.`
        : (res.queued > 0 ? `${res.queued} documentos en cola.` : 'No hay documentos pendientes.');
      UI.toast(msg, 'success');
      _startPollIfNeeded();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Analizar pendientes'; }
    }
  }

  async function _analyzeAll() {
    const btn = document.getElementById('isms-analyze-all-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Iniciando...'; }
    try {
      const res = await Api.aiDocuments.analyzeAll();
      await _load(); _renderRoot();
      UI.toast(res.message || `Analisis iniciado para ${res.queued} documentos`, 'success');
      _startPollIfNeeded();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Re-analizar todos'; }
    }
  }

  // --- Formulario de politica ---

  function _editPolicy(policyId) {
    const policy = _policies.find(p => p.id === policyId);
    if (!policy) return;
    if (policy.status === 'approved' || policy.status === 'published') {
      _openVersioningModal(policy);
    } else {
      _openFormEnhanced(policy);
    }
  }

  function _openVersioningModal(policy) {
    const nextVer = _bumpVersion(policy.version);
    UI.modal('Editar documento aprobado', `
      <p style="margin-bottom:10px;">El documento <strong>${UI.esc(policy.code)}</strong> esta
        <strong>${STATUS_LABELS[policy.status] || policy.status}</strong> (v${UI.esc(policy.version || '1.0')}).</p>
      <p style="font-size:13px;color:var(--text-subtle);">Se creara una nueva version
        <strong>v${UI.esc(nextVer)}</strong> en borrador. El documento actual permanece vigente
        hasta que la nueva version sea aprobada.</p>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-confirm-v">Crear version ${UI.esc(nextVer)}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-confirm-v').onclick = async () => {
      try {
        const draft = await Api.policies.newVersion(policy.id);
        UI.toast(`Version ${draft.version} creada en borrador`, 'success');
        UI.closeModal();
        _openFormEnhanced(draft);
        await _load(); _renderRoot();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  function _bumpVersion(ver) {
    const parts = String(ver || '1.0').split('.');
    return (parseInt(parts[0] || '1') + 1) + '.0';
  }

  async function _openForm(policy, extracted) {
    UI.modal(
      policy ? `Editar ${policy.code}` : 'Nuevo registro ISMS',
      _formHtml(policy, extracted),
      {
        actions: `<button class="btn" id="m-cancel">Cancelar</button>
                  <button class="btn btn-primary" id="m-save">Guardar</button>`,
      }
    );
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick   = () => _save(policy);
    const levelSel = document.getElementById('f-doc-level');
    if (levelSel) _onLevelChange(levelSel);
    if (policy && policy.source_document_id) _loadPolicyMaturity(policy.source_document_id);
  }

  function _formHtml(policy, extracted) {
    const p = policy || {};
    const e = extracted || {};
    const title    = e.title    || p.title    || '';
    const version  = e.version  || p.version  || '1.0';
    const category = e.category || p.category || '';
    const scope    = e.scope    || p.scope    || '';
    const content  = e.content  || p.content  || '';
    const review   = e.review_date || (p.review_date ? p.review_date.slice(0, 10) : '');
    const clauses  = e.iso_clauses ? e.iso_clauses.join(', ') : (p.iso_clauses || []).join(', ');
    const notes    = e.confidence_notes || '';
    const docLevel = p.document_level || 1;
    const parentId = p.parent_policy_id || '';
    const normalizedCat = Object.keys(ISMS_TYPES).includes(category) ? category : '';

    const parentOptions = _policies
      .filter(pp => !policy || pp.id !== policy.id)
      .map(pp => {
        const lvl = pp.document_level || 1;
        return `<option value="${pp.id}" ${parentId == pp.id ? 'selected' : ''}>[${lvl}] ${UI.esc(pp.code)} — ${UI.esc(pp.title)}</option>`;
      }).join('');

    return `
      <div class="form-grid">
        ${notes ? `<div class="span2"><div class="notice" style="margin-bottom:4px;font-size:12px;">Nota IA: ${UI.esc(notes)}</div></div>` : ''}
        <div class="span2">
          <label>Titulo *</label>
          <input id="f-title" class="input" value="${UI.esc(title)}">
        </div>

        <div>
          <label>Nivel jerarquico
            <span title="Politica (alto nivel) > Norma (reglas) > Procedimiento (pasos) > Instruccion Tecnica (exacto)"
                  style="cursor:help;color:var(--text-muted);font-weight:400;font-size:11px;"> (?)</span>
          </label>
          <select id="f-doc-level" class="input" onchange="ViewIsmsDocuments._onLevelChange(this)">
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
          <div style="font-size:11px;color:var(--text-muted);margin-top:3px;">
            Una Norma referencia su Politica padre; un Procedimiento referencia su Norma padre.
          </div>
        </div>

        <div>
          <label>Tipo de documento ISMS</label>
          <select id="f-cat" class="input">
            <option value="">-- Sin clasificar --</option>
            ${Object.entries(ISMS_TYPES).map(([k, l]) =>
              `<option value="${k}" ${normalizedCat === k ? 'selected' : ''}>${l}</option>`
            ).join('')}
          </select>
          ${category && !normalizedCat ? `<div style="font-size:11px;color:var(--text-muted);margin-top:3px;">Detectado por IA: "${UI.esc(category)}"</div>` : ''}
        </div>

        <div>
          <label>Estado</label>
          <select id="f-status" class="input">
            ${Object.entries(STATUS_LABELS).map(([k, l]) =>
              `<option value="${k}" ${(p.status || 'draft') === k ? 'selected' : ''}>${l}</option>`
            ).join('')}
          </select>
        </div>

        <div>
          <label>Version</label>
          <input id="f-version" class="input" value="${UI.esc(version)}">
        </div>

        <div>
          <label>Responsable</label>
          <select id="f-owner" class="input">
            <option value="">— Sin asignar —</option>
            ${_users.map(u =>
              `<option value="${u.id}" ${p.owner_id === u.id ? 'selected' : ''}>${UI.esc(u.full_name || u.email)}</option>`
            ).join('')}
          </select>
        </div>

        <div>
          <label>Fecha de revision</label>
          <input type="date" id="f-review" class="input" value="${UI.esc(review)}">
        </div>

        <div>
          <label>Clausulas ISO (separadas por coma)</label>
          <input id="f-clauses" class="input" value="${UI.esc(clauses)}">
        </div>

        <div class="span2">
          <label>Alcance</label>
          <textarea id="f-scope" class="input" rows="2">${UI.esc(scope)}</textarea>
        </div>

        <div class="span2">
          <label>Contenido / resumen</label>
          <textarea id="f-content" class="input" rows="5">${UI.esc(content)}</textarea>
        </div>

        ${policy && policy.source_document_id ? `
        <div class="span2" style="padding-top:14px;border-top:1px solid var(--border);margin-top:4px;">
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-muted);
                      letter-spacing:.5px;margin-bottom:8px;">Analisis de madurez SGSI</div>
          <div id="pol-maturity-panel">
            <div style="font-size:12px;color:var(--text-muted);">Cargando...</div>
          </div>
        </div>` : ''}
      </div>`;
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

  async function _save(policy) {
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
      document_level:   levelVal ? parseInt(levelVal) : 1,
      parent_policy_id: parentVal ? parseInt(parentVal) : null,
    };
    try {
      if (policy) {
        await Api.policies.update(policy.id, payload);
        UI.toast('Registro actualizado', 'success');
      } else {
        await Api.policies.create(payload);
        UI.toast('Registro creado', 'success');
      }
      UI.closeModal();
      await _load(); _renderRoot();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  // --- Panel de madurez en el formulario ---

  const _POL_MATURITY_COLORS = [
    'var(--risk-critical)', 'var(--risk-high)', 'var(--risk-medium)',
    'var(--brand-orange)', '#22c55e', 'var(--risk-low)',
  ];
  const _POL_DEFAULT_GAP = [
    'Implementar el control desde cero: definir el proceso, documentarlo, asignar responsable.',
    'Formalizar el proceso: crear documentacion oficial y comunicar a los equipos.',
    'Estandarizar la aplicacion: garantizar consistencia y medir la eficacia con KPIs.',
    'Añadir metricas: establecer KPIs, revisar resultados periodicamente.',
    'Implementar mejora continua: analizar tendencias y automatizar donde sea posible.',
    '',
  ];

  function _polParseNotes(notes) {
    if (!notes) return { rationale: '', gap: '' };
    const sep = '\n\nPara llegar a nivel 5: ';
    const idx = notes.indexOf(sep);
    let rationale = notes, gap = '';
    if (idx >= 0) { rationale = notes.slice(0, idx); gap = notes.slice(idx + sep.length); }
    rationale = rationale.replace(/^Nivel actual \(\d+\/5\): /, '');
    return { rationale, gap };
  }

  async function _loadPolicyMaturity(docId) {
    const panel = document.getElementById('pol-maturity-panel');
    if (!panel) return;
    let controls = [];
    try { controls = await Api.aiDocuments.controls(docId); } catch (_) { panel.innerHTML = ''; return; }
    if (!controls.length) {
      panel.innerHTML = `<p style="font-size:12px;color:var(--text-muted);">Sin analisis ISMS disponible.</p>`;
      return;
    }
    const avg = controls.reduce((s, c) => s + (c.maturity || 0), 0) / controls.length;
    const avgColor = _POL_MATURITY_COLORS[Math.min(5, Math.round(avg))];
    const rows = controls.map(c => {
      const { rationale, gap } = _polParseNotes(c.notes);
      const displayGap = gap || _POL_DEFAULT_GAP[Math.min(4, c.maturity || 0)] || '';
      const color = _POL_MATURITY_COLORS[Math.min(5, Math.max(0, c.maturity || 0))];
      const detId = `pm-det-${c.id}`;
      const bars = Array.from({ length: 5 }, (_, i) =>
        `<div style="width:10px;height:7px;border-radius:2px;background:${i < c.maturity ? color : 'var(--bg-3)'}"></div>`
      ).join('');
      return `
        <div style="border:1px solid var(--border);border-radius:6px;margin-bottom:5px;overflow:hidden;">
          <div onclick="const d=document.getElementById('${detId}');d.style.display=d.style.display==='none'?'block':'none';"
               style="display:flex;align-items:center;gap:8px;padding:7px 10px;cursor:pointer;background:var(--bg-2);user-select:none;">
            <span style="font-size:10px;font-weight:700;color:var(--brand-purple);background:var(--brand-purple-4);
                         border-radius:3px;padding:1px 5px;white-space:nowrap;flex-shrink:0;">${UI.esc(c.control_code || '-')}</span>
            <span style="font-size:12px;font-weight:500;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${UI.esc(c.control_name || '-')}</span>
            <div style="display:flex;gap:2px;flex-shrink:0;">${bars}</div>
            <span style="font-size:11px;font-weight:700;color:${color};white-space:nowrap;min-width:28px;text-align:right;">${c.maturity || 0}/5</span>
          </div>
          <div id="${detId}" style="display:none;padding:8px 12px;font-size:12px;line-height:1.6;background:var(--bg-card);">
            ${rationale ? `<div style="margin-bottom:7px;"><div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);letter-spacing:.4px;margin-bottom:3px;">Por que esta en nivel ${c.maturity || 0}/5</div><div style="background:var(--bg-2);border-left:3px solid ${color};border-radius:0 4px 4px 0;padding:6px 10px;">${UI.esc(rationale)}</div></div>` : ''}
            ${displayGap ? `<div><div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);letter-spacing:.4px;margin-bottom:3px;">Para llegar a nivel 5</div><div style="background:rgba(89,0,141,.05);border-left:3px solid var(--brand-purple);border-radius:0 4px 4px 0;padding:6px 10px;">${UI.esc(displayGap)}</div></div>` : ''}
          </div>
        </div>`;
    }).join('');

    panel.innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;padding:8px 12px;background:var(--bg-2);border-radius:6px;margin-bottom:8px;">
        <div style="font-size:20px;font-weight:800;color:${avgColor};">${avg.toFixed(1)}</div>
        <div style="flex:1;">
          <div style="font-size:12px;font-weight:600;">Madurez aportada por este documento</div>
          <div style="font-size:11px;color:var(--text-muted);">${controls.length} control${controls.length !== 1 ? 'es' : ''} en el alcance de este documento</div>
        </div>
      </div>
      ${rows}`;
  }

  // --- Modal de madurez completo ---

  const _MODAL_LEVEL_LABELS = { 1: 'Politica', 2: 'Norma', 3: 'Procedimiento', 4: 'Instruccion Tecnica' };

  function _maturityBarLarge(v) {
    const color = _maturityColor(v);
    const bars = Array.from({ length: 5 }, (_, i) =>
      `<div style="width:20px;height:12px;border-radius:3px;background:${i < v ? color : 'var(--bg-3)'}"></div>`
    ).join('');
    return `<div style="display:flex;gap:4px;align-items:center;">
      ${bars}
      <span style="font-size:13px;font-weight:800;color:${color};margin-left:8px;">${v}/5</span>
      <span style="font-size:12px;color:var(--text-muted);margin-left:4px;">${MATURITY_LABELS[v] || ''}</span>
    </div>`;
  }

  function _parseGapNotes(notes) {
    if (!notes) return { rationale: '', gap: '' };
    const sep = '\n\nPara llegar a nivel 5: ';
    const idx = notes.indexOf(sep);
    let rationale = notes, gap = '';
    if (idx >= 0) { rationale = notes.slice(0, idx); gap = notes.slice(idx + sep.length); }
    rationale = rationale.replace(/^Nivel actual \(\d+\/5\): /, '');
    return { rationale, gap };
  }

  async function _showMaturityModal(docId) {
    const doc = _docs.find(d => d.id === docId);
    let controls = [];
    try {
      controls = await Api.aiDocuments.controls(docId);
    } catch (e) {
      UI.toast('Error cargando madurez: ' + e.message, 'error'); return;
    }
    if (!controls.length) {
      UI.toast('Sin controles vinculados. Re-analiza el documento para generar el gap analysis.', 'info');
      return;
    }

    const avgMaturity  = controls.reduce((s, c) => s + (c.maturity || 0), 0) / controls.length;
    const avgColor     = _maturityColor(Math.round(avgMaturity));
    const summary      = doc?.isms_summary || {};
    const docLevel     = summary.document_level || 1;
    const docLevelLabel = summary.document_level_label || _MODAL_LEVEL_LABELS[docLevel] || 'Politica';
    const docLevelColor = DOC_LEVEL_COLORS[docLevel] || 'var(--brand-purple)';
    const levelMaxMaturity = DOC_LEVEL_MAX_MATURITY[docLevel] || 5;

    const rows = controls.map(c => {
      const { rationale, gap } = _parseGapNotes(c.notes);
      const color = _maturityColor(c.maturity || 0);
      return `
        <div style="border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:12px;">
          <div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:10px;flex-wrap:wrap;">
            <span style="font-size:11px;font-weight:700;background:var(--brand-purple-4);color:var(--brand-purple);
                         border-radius:3px;padding:2px 7px;white-space:nowrap;flex-shrink:0;">${UI.esc(c.control_code || '-')}</span>
            <span style="font-size:13px;font-weight:600;flex:1;">${UI.esc(c.control_name || '-')}</span>
          </div>
          <div style="margin-bottom:${(rationale || gap) ? '12px' : '0'};">${_maturityBarLarge(c.maturity || 0)}</div>
          ${rationale ? `
            <div style="margin-bottom:8px;">
              <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);letter-spacing:.5px;margin-bottom:5px;">Justificacion del nivel actual</div>
              <div style="font-size:12px;line-height:1.65;background:var(--bg-2);border-radius:6px;padding:8px 12px;border-left:3px solid ${color};">${UI.esc(rationale)}</div>
            </div>` : ''}
          ${gap ? `
            <div>
              <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);letter-spacing:.5px;margin-bottom:5px;">Para llegar a nivel 5 (Optimizado)</div>
              <div style="font-size:12px;line-height:1.65;background:rgba(89,0,141,.05);border-radius:6px;padding:8px 12px;border-left:3px solid var(--brand-purple);">${UI.esc(gap)}</div>
            </div>` : (!rationale ? `
            <div style="font-size:11px;color:var(--text-muted);font-style:italic;margin-top:4px;">
              Sin analisis de gap disponible. Re-analiza el documento para generarlo.
            </div>` : '')}
        </div>`;
    }).join('');

    UI.openModal(`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">Analisis de madurez por control</h3>
        <button class="btn btn-ghost btn-sm" onclick="UI.closeModal()">&#10005;</button>
      </div>
      <div style="margin-bottom:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <span style="font-size:12px;color:var(--text-muted);">Documento:</span>
        <strong style="font-size:12px;">${UI.esc(doc?.original_name || '')}</strong>
        <span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:10px;font-weight:700;
                     background:${docLevelColor}18;color:${docLevelColor};border:1px solid ${docLevelColor}40;">
          Nivel ${docLevel}: ${docLevelLabel}
        </span>
      </div>
      <div style="background:var(--bg-2);border-radius:8px;padding:12px 16px;margin-bottom:12px;display:flex;align-items:center;gap:14px;">
        <div style="font-size:28px;font-weight:800;color:${avgColor};">${avgMaturity.toFixed(1)}</div>
        <div>
          <div style="font-size:13px;font-weight:600;">Madurez aportada por este documento</div>
          <div style="font-size:11px;color:var(--text-muted);">
            ${controls.length} control${controls.length !== 1 ? 'es' : ''} en el alcance &nbsp;&middot;&nbsp;
            Madurez maxima nivel ${docLevel}: <strong>${levelMaxMaturity}/5</strong>
          </div>
        </div>
      </div>
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:14px;padding:7px 10px;
                  background:rgba(89,0,141,.04);border-radius:5px;border:1px solid rgba(89,0,141,.1);">
        Un documento de nivel ${docLevel} (${docLevelLabel}) puede aportar hasta ${levelMaxMaturity}/5 de madurez.
        Para alcanzar nivel 5 en un control se necesita cubrir toda la cadena:
        Politica &#8594; Norma &#8594; Procedimiento &#8594; Instruccion Tecnica.
      </div>
      <div style="overflow-y:auto;max-height:56vh;">${rows}</div>
    `, { width: '700px' });
  }

  // --- Modal de clausulas ISO ---

  function _showClauses(docId) {
    const doc = _docs.find(d => d.id === docId);
    if (!doc) return;
    const clauses = Array.isArray(doc.extracted_clauses) ? doc.extracted_clauses : [];
    if (!clauses.length) { UI.toast('No hay clausulas extraidas', 'info'); return; }

    const rows = clauses.map(c => `
      <tr style="border-bottom:1px solid var(--border);">
        <td style="padding:8px 12px;font-weight:600;color:var(--brand-purple);white-space:nowrap;">${UI.esc(c.ref)}</td>
        <td style="padding:8px 12px;font-size:13px;">${UI.esc(c.title || '')}</td>
        <td style="padding:8px 12px;text-align:center;">
          ${c.control_id ? `<a href="#/controls" style="font-size:11px;color:var(--risk-low);">Control #${c.control_id}</a>` : '<span style="font-size:11px;color:var(--text-muted);">-</span>'}
        </td>
        <td style="padding:8px 12px;text-align:center;font-size:11px;color:${c.confidence >= 0.8 ? 'var(--risk-low)' : 'var(--brand-orange)'};">
          ${Math.round((c.confidence || 0) * 100)}%
        </td>
      </tr>`).join('');

    UI.openModal(`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">Clausulas ISO extraidas</h3>
        <button class="btn btn-ghost btn-sm" onclick="UI.closeModal()">x</button>
      </div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">Documento: <strong>${UI.esc(doc.original_name)}</strong></p>
      <div style="overflow-y:auto;max-height:60vh;">
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr style="background:var(--bg-2);font-size:11px;text-transform:uppercase;color:var(--text-muted);">
              <th style="padding:8px 12px;text-align:left;">Clausula</th>
              <th style="padding:8px 12px;text-align:left;">Titulo</th>
              <th style="padding:8px 12px;text-align:center;">Control</th>
              <th style="padding:8px 12px;text-align:center;">Confianza</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `, { width: '680px' });
  }

  // --- Generacion con IA ---

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
                      placeholder="Objetivo, alcance, departamentos afectados, contexto especifico..."></textarea>
          </div>
          <div class="span2">
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">
              Documentacion de contexto (opcional)
            </label>
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;border:1px dashed var(--border);
                          border-radius:6px;padding:8px 12px;font-size:12px;color:var(--text-muted);">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              <span id="gen-file-label">Subir documento de referencia (PDF, DOCX, PNG, JPG)</span>
              <input type="file" id="gen-context-file" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
                     style="display:none;" onchange="ViewIsmsDocuments._onGenFileChange(this)">
            </label>
          </div>
        </div>
        <div style="margin-top:16px;background:#fff8e6;border:1px solid #f0c040;border-radius:8px;
                    padding:10px 14px;font-size:12px;color:#7a5800;line-height:1.5;">
          <strong>Aviso importante:</strong> El documento generado por IA es un borrador de apoyo.
          Debe ser revisado, completado y aprobado antes de su publicacion o uso operativo.
        </div>
        <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;">
          <button onclick="UI.closeModal()" class="btn">Cancelar</button>
          <button onclick="ViewIsmsDocuments._submitGenerate()" class="btn"
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
    const file      = document.getElementById('gen-context-file')?.files[0] || null;

    UI.closeModal();
    UI.toast('Generando documento con IA...', 'info');

    try {
      const fd = new FormData();
      fd.append('doc_type', docType);
      fd.append('title', title);
      fd.append('framework', framework);
      if (desc) fd.append('description', desc);
      if (file) fd.append('context_file', file);

      const result = await Api.req('/api/policies/ai-generate-free', { method: 'POST', body: fd });

      UI.openModal(`
        <div style="max-width:700px;">
          <h3 style="margin:0 0 4px;color:var(--brand-purple);">${UI.esc(result.title)}</h3>
          <div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;">
            ${_typeBadge(result.category)}
            <span style="font-size:11px;color:var(--text-muted);align-self:center;">Marco: ${UI.esc(result.framework || framework)}</span>
          </div>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px;">Revisa el contenido antes de guardar. Puedes editarlo directamente.</p>
          <textarea id="gen-result-content" style="width:100%;height:340px;font-size:12px;font-family:monospace;
                    border:1px solid var(--border);border-radius:6px;padding:10px;resize:vertical;">${UI.esc(result.content)}</textarea>
          <div style="margin-top:10px;background:#fff8e6;border:1px solid #f0c040;border-radius:6px;
                      padding:8px 12px;font-size:11px;color:#7a5800;">
            Este borrador ha sido generado por IA y debe ser revisado y aprobado por una persona responsable.
          </div>
          <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end;">
            <button onclick="UI.closeModal()" class="btn">Descartar</button>
            <button onclick="ViewIsmsDocuments._saveGenerated(${JSON.stringify({
              title: result.title,
              category: result.category || docType,
              iso_clauses: result.iso_clauses || [],
              framework,
            }).replace(/"/g, '&quot;')})"
                    class="btn btn-primary">Guardar como borrador</button>
          </div>
        </div>`);
    } catch (e) {
      UI.toast('Error generando: ' + e.message, 'error');
    }
  }

  async function _saveGenerated(meta) {
    const content = document.getElementById('gen-result-content')?.value || '';
    try {
      await Api.policies.create({
        title: meta.title, content, category: meta.category || null,
        iso_clauses: meta.iso_clauses || [],
        scope: 'Generado automaticamente con IA — revisar y adaptar',
        version: '1.0', status: 'draft', review_cycle_months: 12,
      });
      UI.closeModal();
      UI.toast('Borrador guardado — revisa y aprueba antes de publicar', 'success');
      await _load(); _renderRoot();
    } catch (e) { UI.toast('Error guardando: ' + e.message, 'error'); }
  }

  // ============================================================
  // FASE 1 — Flujo de aprobacion por email
  // ============================================================

  let _smtpConfigured = null;

  async function _checkSmtp() {
    if (_smtpConfigured !== null) return _smtpConfigured;
    try {
      const cfg = await Api.alerts.getSettings();
      _smtpConfigured = !!(cfg && cfg.smtp_host);
    } catch (_) { _smtpConfigured = false; }
    return _smtpConfigured;
  }

  async function _openApprovalForm(policy) {
    const smtpOk = await _checkSmtp();
    const smtpBanner = smtpOk ? '' : `
      <div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;
                  padding:10px 14px;margin-bottom:16px;font-size:13px;color:#92400e;">
        <strong>SMTP no configurado.</strong> Configura el correo saliente en
        <a href="#/admin-hub/integrations" onclick="UI.closeModal()"
           style="color:#59008D;font-weight:600;">Configuracion &rarr; Integraciones</a>
        para poder enviar los emails de solicitud.
      </div>`;

    UI.openModal(`
      <div style="min-width:520px;max-width:600px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="margin:0;font-size:16px;color:var(--brand-purple);">Solicitar aprobacion</h3>
          <button onclick="UI.closeModal()" class="btn btn-ghost btn-sm">&#10005;</button>
        </div>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
          Documento: <strong>${UI.esc(policy.code)} — ${UI.esc(policy.title)}</strong> (v${UI.esc(policy.version || '1.0')})
        </p>
        ${smtpBanner}

        <div style="margin-bottom:14px;">
          <label style="font-size:12px;font-weight:600;display:block;margin-bottom:6px;">Modo de aprobacion</label>
          <div style="display:flex;gap:8px;">
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;
                          padding:8px 14px;border:2px solid var(--border);border-radius:8px;flex:1;
                          transition:border-color .15s;" id="mode-parallel-label">
              <input type="radio" name="appr-mode" value="parallel" checked
                     onchange="ViewIsmsDocuments._onApprModeChange(this)">
              <div>
                <div style="font-weight:600;">Paralelo</div>
                <div style="font-size:11px;color:var(--text-muted);">Todos reciben el email a la vez</div>
              </div>
            </label>
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;
                          padding:8px 14px;border:2px solid var(--border);border-radius:8px;flex:1;
                          transition:border-color .15s;" id="mode-sequential-label">
              <input type="radio" name="appr-mode" value="sequential"
                     onchange="ViewIsmsDocuments._onApprModeChange(this)">
              <div>
                <div style="font-weight:600;">Secuencial</div>
                <div style="font-size:11px;color:var(--text-muted);">Cada uno solo recibe el email cuando el anterior aprueba</div>
              </div>
            </label>
          </div>
        </div>

        <div style="margin-bottom:12px;">
          <label style="font-size:12px;font-weight:600;display:block;margin-bottom:6px;">Aprobadores</label>
          <div id="approver-list"></div>
          <button onclick="ViewIsmsDocuments._addApproverRow()"
                  class="btn btn-ghost btn-sm" style="margin-top:6px;">+ Agregar aprobador</button>
          <div id="order-hint" style="display:none;font-size:11px;color:var(--text-muted);
               margin-top:8px;padding:6px 10px;background:rgba(89,0,141,.05);border-radius:5px;">
            En modo secuencial, usa las flechas para definir el orden de aprobacion.
          </div>
        </div>

        <div style="display:flex;gap:8px;justify-content:flex-end;padding-top:12px;
                    border-top:1px solid var(--border);">
          <button onclick="UI.closeModal()" class="btn">Cancelar</button>
          <button onclick="ViewIsmsDocuments._submitApproval(${policy.id})"
                  class="btn btn-primary" ${smtpOk ? '' : 'style="opacity:.5"'}>
            Enviar solicitud
          </button>
        </div>
      </div>`);

    _addApproverRow();
    _onApprModeChange(document.querySelector('[name=appr-mode]'));
  }

  function _addApproverRow() {
    const list = document.getElementById('approver-list');
    if (!list) return;
    const idx = list.children.length + 1;
    const row = document.createElement('div');
    row.className = 'approver-row';
    row.dataset.order = idx;
    row.style.cssText = 'display:flex;gap:6px;align-items:center;margin-bottom:6px;';
    row.innerHTML = `
      <div style="display:none;flex-direction:column;gap:1px;" class="order-arrows">
        <button onclick="ViewIsmsDocuments._moveApprover(this,-1)"
                style="border:1px solid var(--border);background:var(--bg-2);border-radius:3px;
                       width:22px;height:18px;cursor:pointer;font-size:10px;line-height:1;">&#9650;</button>
        <button onclick="ViewIsmsDocuments._moveApprover(this,1)"
                style="border:1px solid var(--border);background:var(--bg-2);border-radius:3px;
                       width:22px;height:18px;cursor:pointer;font-size:10px;line-height:1;">&#9660;</button>
      </div>
      <span class="order-num" style="display:none;font-size:12px;font-weight:700;
            color:var(--brand-purple);min-width:18px;text-align:center;">${idx}</span>
      <input class="input appr-email" placeholder="email@empresa.com" style="flex:2;">
      <input class="input appr-name" placeholder="Nombre (opcional)" style="flex:1.5;">
      <button onclick="this.closest('.approver-row').remove();ViewIsmsDocuments._reorderApprovers()"
              style="border:none;background:none;cursor:pointer;color:var(--text-muted);font-size:16px;
                     padding:0 4px;">&#10005;</button>`;
    list.appendChild(row);
  }

  function _onApprModeChange(radio) {
    const mode = document.querySelector('[name=appr-mode]:checked')?.value || 'parallel';
    document.getElementById('order-hint').style.display = mode === 'sequential' ? '' : 'none';
    document.querySelectorAll('.order-arrows').forEach(el => {
      el.style.display = mode === 'sequential' ? 'flex' : 'none';
    });
    document.querySelectorAll('.order-num').forEach(el => {
      el.style.display = mode === 'sequential' ? '' : 'none';
    });
    // Highlight selected mode label
    const pl = document.getElementById('mode-parallel-label');
    const sl = document.getElementById('mode-sequential-label');
    if (pl) pl.style.borderColor = mode === 'parallel' ? 'var(--brand-purple)' : 'var(--border)';
    if (sl) sl.style.borderColor = mode === 'sequential' ? 'var(--brand-purple)' : 'var(--border)';
  }

  function _moveApprover(btn, dir) {
    const row = btn.closest('.approver-row');
    const list = row.parentElement;
    if (dir === -1 && row.previousElementSibling) {
      list.insertBefore(row, row.previousElementSibling);
    } else if (dir === 1 && row.nextElementSibling) {
      list.insertBefore(row.nextElementSibling, row);
    }
    _reorderApprovers();
  }

  function _reorderApprovers() {
    document.querySelectorAll('.approver-row').forEach((row, i) => {
      row.dataset.order = i + 1;
      const num = row.querySelector('.order-num');
      if (num) num.textContent = i + 1;
    });
  }

  async function _submitApproval(policyId) {
    const mode = document.querySelector('[name=appr-mode]:checked')?.value || 'parallel';
    const rows = document.querySelectorAll('.approver-row');
    const approvers = [];
    let valid = true;
    rows.forEach((row, i) => {
      const email = row.querySelector('.appr-email')?.value.trim();
      const name = row.querySelector('.appr-name')?.value.trim();
      if (!email || !email.includes('@')) { valid = false; return; }
      approvers.push({ email, name: name || null, order_index: i + 1 });
    });
    if (!valid || !approvers.length) {
      UI.toast('Ingresa al menos un email valido', 'error'); return;
    }
    try {
      await Api.approvals.create(policyId, { approvers, mode });
      UI.closeModal();
      UI.toast('Solicitud de aprobacion enviada', 'success');
      await _load(); _renderRoot();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  // ============================================================
  // FASE 1 — Log de aprobaciones
  // ============================================================

  async function _showApprovalLog(policy) {
    let reqs = [];
    try { reqs = await Api.approvals.list(policy.id); } catch (_) {}

    if (!reqs.length) {
      UI.toast('No hay rondas de aprobacion para este documento', 'info'); return;
    }

    const STATUS_ICON = { pending: '⏳', approved: '✅', rejected: '❌', waiting: '⌛', cancelled: '🚫' };
    const STATUS_COLOR = {
      pending: 'var(--brand-orange)', approved: 'var(--risk-low)',
      rejected: 'var(--risk-critical)', waiting: 'var(--text-muted)', cancelled: '#aaa',
    };

    const reqHtml = reqs.map(r => {
      const badge = r.status === 'approved' ? '#22c55e' : r.status === 'rejected' ? '#ef4444'
                  : r.status === 'cancelled' ? '#9ca3af' : 'var(--brand-orange)';
      const modeLabel = r.mode === 'sequential' ? 'Secuencial' : 'Paralelo';
      const approversHtml = r.approvals.map(a => `
        <div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;
                    border-bottom:1px solid var(--border);">
          <span style="font-size:16px;flex-shrink:0;">${STATUS_ICON[a.status] || '?'}</span>
          <div style="flex:1;">
            <div style="font-size:13px;font-weight:500;">${UI.esc(a.email)}</div>
            ${a.name ? `<div style="font-size:11px;color:var(--text-muted);">${UI.esc(a.name)}</div>` : ''}
            ${r.mode === 'sequential' ? `<div style="font-size:11px;color:var(--brand-purple);">Orden ${a.order_index}</div>` : ''}
          </div>
          <div style="text-align:right;font-size:11px;color:var(--text-muted);">
            ${a.responded_at ? `Respondio: ${new Date(a.responded_at).toLocaleString('es-ES')}` :
              a.sent_at ? `Email enviado: ${new Date(a.sent_at).toLocaleString('es-ES')}` : ''}
            ${a.response_notes ? `<div style="color:var(--text);margin-top:3px;font-style:italic;">"${UI.esc(a.response_notes)}"</div>` : ''}
            ${a.ip_address ? `<div style="color:#ccc;">IP: ${UI.esc(a.ip_address)}</div>` : ''}
          </div>
        </div>`).join('');

      return `
        <div style="border:1px solid var(--border);border-radius:8px;margin-bottom:12px;overflow:hidden;">
          <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--bg-2);">
            <span style="padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700;
                         background:${badge}20;color:${badge};">
              ${r.status.toUpperCase()}
            </span>
            <span style="font-size:12px;font-weight:600;">${modeLabel}</span>
            <span style="font-size:11px;color:var(--text-muted);margin-left:auto;">
              ${new Date(r.created_at).toLocaleString('es-ES')}
            </span>
            ${r.status === 'pending' ? `
            <button onclick="ViewIsmsDocuments._cancelApproval(${policy.id},${r.id})"
                    style="border:1px solid var(--risk-critical);background:none;cursor:pointer;
                           font-size:11px;color:var(--risk-critical);border-radius:4px;padding:2px 7px;">
              Cancelar
            </button>` : ''}
          </div>
          <div style="padding:0 14px;">${approversHtml}</div>
        </div>`;
    }).join('');

    UI.openModal(`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">Historial de aprobaciones</h3>
        <button onclick="UI.closeModal()" class="btn btn-ghost btn-sm">&#10005;</button>
      </div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:14px;">
        ${UI.esc(policy.code)} — ${UI.esc(policy.title)}
      </p>
      <div style="overflow-y:auto;max-height:60vh;">${reqHtml}</div>
    `, { width: '640px' });
  }

  async function _cancelApproval(policyId, reqId) {
    if (!confirm('Cancelar esta solicitud de aprobacion?')) return;
    try {
      await Api.approvals.cancel(policyId, reqId);
      UI.toast('Solicitud cancelada', 'success');
      await _load(); _renderRoot();
      UI.closeModal();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  // ============================================================
  // FASE 2 — Timeline de versiones
  // ============================================================

  async function _showVersionHistory(policy) {
    let versions = [];
    try { versions = await Api.policies.versions(policy.id); } catch (_) {}

    if (!versions.length) {
      UI.toast('No hay historial de versiones', 'info'); return;
    }

    const STATUS_COLOR = {
      approved: '#22c55e', published: '#0891b2', draft: '#9ca3af',
      review: 'var(--brand-orange)', obsolete: '#9ca3af',
    };
    const STATUS_LABEL = {
      approved: 'Aprobada', published: 'Publicada', draft: 'Borrador',
      review: 'En revision', obsolete: 'Obsoleta',
    };

    const timelineHtml = versions.map((v, i) => {
      const color = STATUS_COLOR[v.status] || '#9ca3af';
      const isFirst = i === 0;
      return `
        <div style="display:flex;gap:14px;margin-bottom:${isFirst ? '0' : '8px'};">
          <div style="display:flex;flex-direction:column;align-items:center;gap:0;">
            <div style="width:14px;height:14px;border-radius:50%;background:${color};
                        border:2px solid ${color};flex-shrink:0;margin-top:3px;
                        ${v.is_current ? 'box-shadow:0 0 0 3px ' + color + '30;' : ''}"></div>
            ${i < versions.length - 1 ? `<div style="width:2px;flex:1;background:var(--border);margin:4px 0;min-height:24px;"></div>` : ''}
          </div>
          <div style="flex:1;padding-bottom:12px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:3px;">
              <span style="font-size:13px;font-weight:700;">v${UI.esc(v.version)}</span>
              <span style="padding:1px 7px;border-radius:999px;font-size:10px;font-weight:700;
                           background:${color}20;color:${color};">
                ${STATUS_LABEL[v.status] || v.status}
              </span>
              ${v.is_current ? `<span style="font-size:10px;font-weight:700;color:var(--brand-purple);
                background:var(--brand-purple-4);padding:1px 6px;border-radius:3px;">Actual</span>` : ''}
            </div>
            ${v.approved_at ? `<div style="font-size:11px;color:var(--text-muted);">
              Aprobado el ${new Date(v.approved_at).toLocaleDateString('es-ES', { day:'2-digit', month:'long', year:'numeric' })}
              ${v.approved_by ? ` por ${UI.esc(v.approved_by)}` : ''}</div>` :
              v.created_at ? `<div style="font-size:11px;color:var(--text-muted);">
              Creado el ${new Date(v.created_at).toLocaleDateString('es-ES', { day:'2-digit', month:'long', year:'numeric' })}</div>` : ''}
          </div>
        </div>`;
    }).join('');

    UI.openModal(`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">Historial de versiones</h3>
        <button onclick="UI.closeModal()" class="btn btn-ghost btn-sm">&#10005;</button>
      </div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:18px;">
        ${UI.esc(policy.code)} — ${UI.esc(policy.title)}
      </p>
      <div style="overflow-y:auto;max-height:60vh;">${timelineHtml}</div>
    `, { width: '440px' });
  }

  // ============================================================
  // FASE 3 — Jerarquia documental
  // ============================================================

  async function _showHierarchy(policy) {
    let hier = null;
    try { hier = await Api.policies.hierarchy(policy.id); } catch (_) {}

    if (!hier) {
      UI.toast('Error cargando jerarquia', 'error'); return;
    }

    const DOC_LEVEL_COLOR_MAP = {
      1: 'var(--brand-purple)', 2: 'var(--brand-orange)', 3: '#0891b2', 4: '#16a34a',
    };
    const DOC_LEVEL_NAME = { 1: 'Politica', 2: 'Norma', 3: 'Procedimiento', 4: 'Instruccion' };

    function _hierBadge(level) {
      const c = DOC_LEVEL_COLOR_MAP[level] || '#9ca3af';
      return `<span style="padding:1px 6px;border-radius:3px;font-size:10px;font-weight:700;
                            background:${c}18;color:${c};">
                Niv.${level} ${DOC_LEVEL_NAME[level] || ''}
              </span>`;
    }

    // Breadcrumb de padres
    const breadcrumb = hier.parents.length
      ? hier.parents.map(p => `
          <span style="display:inline-flex;align-items:center;gap:5px;font-size:12px;">
            ${_hierBadge(p.document_level)}
            <a href="#/compliance-hub/policies" onclick="UI.closeModal()"
               style="color:var(--brand-purple);font-weight:500;">${UI.esc(p.code)}</a>
            <span style="color:var(--text-muted);">${UI.esc(p.title)}</span>
          </span>
          <span style="color:var(--text-muted);margin:0 6px;">/</span>`).join('')
      : `<span style="font-size:12px;color:var(--text-muted);">Sin documento padre (raiz)</span>`;

    // Hijos
    const childrenHtml = hier.children.length
      ? hier.children.map(c => `
          <div style="display:flex;align-items:center;gap:10px;padding:8px 12px;
                      border:1px solid var(--border);border-radius:6px;margin-bottom:6px;">
            ${_hierBadge(c.document_level)}
            <div style="flex:1;">
              <div style="font-size:13px;font-weight:500;">${UI.esc(c.code)} — ${UI.esc(c.title)}</div>
              <div style="font-size:11px;color:var(--text-muted);">v${UI.esc(c.version || '1.0')}</div>
            </div>
            <span style="font-size:11px;color:var(--text-muted);">${STATUS_LABELS[c.status] || c.status}</span>
          </div>`).join('')
      : `<p style="font-size:13px;color:var(--text-muted);text-align:center;padding:20px 0;">Sin documentos hijo</p>`;

    UI.openModal(`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">Jerarquia documental</h3>
        <button onclick="UI.closeModal()" class="btn btn-ghost btn-sm">&#10005;</button>
      </div>

      <div style="background:var(--bg-2);border-radius:8px;padding:12px 16px;margin-bottom:16px;">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);
                    letter-spacing:.5px;margin-bottom:6px;">Camino jerarquico</div>
        <div style="display:flex;align-items:center;flex-wrap:wrap;gap:2px;">
          ${breadcrumb}
          <span style="display:inline-flex;align-items:center;gap:5px;font-size:12px;">
            ${_hierBadge(hier.current.document_level)}
            <strong>${UI.esc(hier.current.code)}</strong>
            <span>${UI.esc(hier.current.title)}</span>
          </span>
        </div>
      </div>

      <div>
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-muted);
                    letter-spacing:.5px;margin-bottom:8px;">
          Documentos dependientes (${hier.children.length})
        </div>
        <div style="overflow-y:auto;max-height:40vh;">${childrenHtml}</div>
      </div>
    `, { width: '560px' });
  }

  // ============================================================
  // Actualizacion de _openForm para incluir botones de las 3 fases
  // ============================================================

  async function _openFormEnhanced(policy, extracted) {
    // Checkout: intentar bloquear el documento para edicion
    let checkoutInfo = null;
    if (policy) {
      try { checkoutInfo = await Api.policies.checkout(policy.id); }
      catch (e) {
        if (e.message && e.message.includes('edicion por')) {
          UI.toast('Documento bloqueado: ' + e.message, 'error'); return;
        }
        // Si el checkout falla por otro motivo lo ignoramos
      }
    }

    const isDraftOrReview = !policy || !['approved','published','obsolete'].includes(policy.status);
    const isExisting = !!policy;

    const extraActions = isExisting ? `
      <button class="btn btn-ghost btn-sm" id="m-versions"
              style="margin-right:auto;">Versiones</button>
      <button class="btn btn-ghost btn-sm" id="m-hierarchy">Jerarquia</button>
      ${isDraftOrReview ? `<button class="btn btn-ghost btn-sm" id="m-appr-log">Aprobaciones</button>
      <button class="btn" id="m-request-appr"
              style="background:var(--brand-orange);color:#fff;border:none;">
        Solicitar aprobacion
      </button>` : `<button class="btn btn-ghost btn-sm" id="m-appr-log">Aprobaciones</button>`}
    ` : '';

    UI.modal(
      policy ? `Editar ${policy.code}` : 'Nuevo registro ISMS',
      _formHtml(policy, extracted),
      {
        actions: `
          ${extraActions}
          <button class="btn" id="m-cancel">Cancelar</button>
          <button class="btn btn-primary" id="m-save">Guardar</button>`,
      }
    );

    document.getElementById('m-cancel').onclick = async () => {
      if (policy) { try { await Api.policies.checkin(policy.id); } catch (_) {} }
      UI.closeModal();
    };
    document.getElementById('m-save').onclick = async () => {
      await _save(policy);
      if (policy) { try { await Api.policies.checkin(policy.id); } catch (_) {} }
    };

    if (isExisting) {
      document.getElementById('m-versions').onclick = () => _showVersionHistory(policy);
      document.getElementById('m-hierarchy').onclick = () => _showHierarchy(policy);
      const apprLogBtn = document.getElementById('m-appr-log');
      if (apprLogBtn) apprLogBtn.onclick = () => _showApprovalLog(policy);
      const apprBtn = document.getElementById('m-request-appr');
      if (apprBtn) apprBtn.onclick = () => { UI.closeModal(); _openApprovalForm(policy); };
    }

    const levelSel = document.getElementById('f-doc-level');
    if (levelSel) _onLevelChange(levelSel);
    if (policy && policy.source_document_id) _loadPolicyMaturity(policy.source_document_id);

    // Mostrar indicador de checkout
    if (checkoutInfo && policy) {
      const modal = document.querySelector('.modal-body') || document.querySelector('[class*="modal"]');
      if (modal) {
        const lockBadge = document.createElement('div');
        lockBadge.style.cssText = 'font-size:11px;color:var(--brand-orange);padding:4px 10px;' +
          'background:rgba(214,82,0,.08);border-radius:4px;margin-bottom:8px;';
        lockBadge.textContent = 'Documento bloqueado para edicion exclusiva por ti';
        modal.prepend(lockBadge);
      }
    }
  }

  // _openFormEnhanced reemplaza a _openForm en los sitios de llamada
  // dentro del modulo; _editPolicy y _openVersioningModal llaman a _openFormEnhanced

  // --- API publica ---

  return {
    render,
    _setQueueCat, _removeFromQueue,
    _analyze, _reprocess, _deleteDoc, _deletePolicy,
    _analyzePending, _analyzeAll,
    _editPolicy,
    _showMaturityModal, _showClauses,
    _generateWithAI, _onGenFileChange, _submitGenerate, _saveGenerated,
    _onLevelChange,
    // Fase 1
    _openApprovalForm, _addApproverRow, _onApprModeChange, _moveApprover,
    _reorderApprovers, _submitApproval, _showApprovalLog, _cancelApproval,
    // Fase 2
    _showVersionHistory,
    // Fase 3
    _showHierarchy,
  };
})();
