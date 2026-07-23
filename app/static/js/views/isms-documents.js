/* Vista ISMS — Gestión Documental Unificada — ISO 27001 cl. 5.2
   Combina ViewPolicies (versionado, aprobación, generador IA) y
   ViewAiDocuments (subida, indexado, análisis ISMS, madurez, gap). */

const ViewIsmsDocuments = (() => {

  // --- Constantes ---

  const NS = 'isms_documents_hub';
  const STATUS_LABELS = {
    draft: t(`${NS}.status.draft`), review: t(`${NS}.status.review`), approved: t(`${NS}.status.approved`),
    published: t(`${NS}.status.published`), obsolete: t(`${NS}.status.obsolete`),
  };
  const STATUS_COLORS = {
    draft: 'var(--text-muted)', review: 'var(--brand-orange)',
    approved: 'var(--brand-purple)', published: 'var(--risk-low)', obsolete: '#aaa',
  };
  const DOC_LEVEL_LABELS = {
    1: t(`${NS}.level.1.long`), 2: t(`${NS}.level.2.long`), 3: t(`${NS}.level.3.long`), 4: t(`${NS}.level.4.long`),
  };
  const DOC_LEVEL_SHORT = {
    1: t(`${NS}.level.1.short`), 2: t(`${NS}.level.2.short`), 3: t(`${NS}.level.3.short`), 4: t(`${NS}.level.4.short`),
  };
  const DOC_LEVEL_COLORS = {
    1: 'var(--brand-purple)', 2: 'var(--brand-orange)', 3: '#0891b2', 4: '#16a34a',
  };
  const DOC_LEVEL_MAX_MATURITY = { 1: 2, 2: 3, 3: 4, 4: 5 };
  const ISMS_TYPES = {
    politica: t(`${NS}.isms_type.politica`), norma: t(`${NS}.isms_type.norma`),
    instruccion_tecnica: t(`${NS}.isms_type.instruccion_tecnica`), evidencia: t(`${NS}.isms_type.evidencia`),
  };
  const ISMS_TYPE_COLORS = {
    politica: 'var(--brand-purple)', norma: 'var(--brand-orange)',
    instruccion_tecnica: '#0891b2', evidencia: '#6b7280',
  };
  const FILE_STATUS_LABELS = {
    indexed: t(`${NS}.file_status.indexed`), processing: t(`${NS}.file_status.processing`),
    pending: t(`${NS}.file_status.pending`), error: t(`${NS}.file_status.error`),
  };
  const FILE_STATUS_COLORS = {
    indexed: 'var(--risk-low)', processing: 'var(--brand-orange)',
    pending: 'var(--text-muted)', error: 'var(--risk-critical)',
  };
  const ISMS_STATUS_LABELS = {
    analysing: t(`${NS}.ai_status.analysing`), analysed: t(`${NS}.ai_status.analysed`),
    skipped: t(`${NS}.ai_status.skipped`), error: t(`${NS}.ai_status.error`),
  };
  const ISMS_STATUS_COLORS = {
    analysing: 'var(--brand-orange)', analysed: 'var(--risk-low)',
    skipped: 'var(--text-muted)', error: 'var(--risk-critical)',
  };
  const FRAMEWORKS = [
    { value: 'ISO 27001', label: t(`${NS}.framework.iso27001`) },
    { value: 'NIS2',      label: t(`${NS}.framework.nis2`) },
    { value: 'DORA',      label: t(`${NS}.framework.dora`) },
    { value: 'ENS',       label: t(`${NS}.framework.ens`) },
    { value: 'GDPR',      label: t(`${NS}.framework.gdpr`) },
    { value: 'NIST CSF',  label: t(`${NS}.framework.nist_csf`) },
    { value: 'PCI DSS',   label: t(`${NS}.framework.pci_dss`) },
    { value: 'libre',     label: t(`${NS}.framework.libre`) },
  ];
  const CATEGORY_LABELS = {
    architecture:       t(`${NS}.category.architecture`),
    normative:          t(`${NS}.category.normative`),
    policies:           t(`${NS}.category.policies`),
    assets_inventory:   t(`${NS}.category.assets_inventory`),
    risk_assessments:   t(`${NS}.category.risk_assessments`),
    critical_suppliers: t(`${NS}.category.critical_suppliers`),
    incidents_lessons:  t(`${NS}.category.incidents_lessons`),
    other:              t(`${NS}.category.other`),
  };
  const ACCEPTED_EXTS = ['pdf', 'docx', 'txt', 'csv', 'jpg', 'jpeg', 'png'];

  // Eje de clasificacion documental (F2): separa normativa de evidencias
  const DOC_CLASS_LABELS = {
    normative: t(`${NS}.doc_class.normative`), record: t(`${NS}.doc_class.record`),
    reference: t(`${NS}.doc_class.reference`), unclassified: t(`${NS}.doc_class.unclassified`),
  };
  const DOC_CLASS_COLORS = {
    normative: 'var(--brand-purple)', record: '#0891b2',
    reference: '#6b7280', unclassified: 'var(--brand-orange)',
  };

  // Niveles de madurez CMM
  const MATURITY_LABELS = [0, 1, 2, 3, 4, 5].map(n => t(`${NS}.maturity_level.${n}`));

  // --- Estado ---

  let _docs     = [];   // AiDocument[]
  let _policies = [];   // Policy[]
  let _merged   = [];   // filas combinadas
  let _users    = [];
  let _filter   = 'all';
  let _searchQ  = '';
  let _statusFilter = '';
  let _classFilter  = '';   // filtro por doc_class (normative/record/reference/unclassified)
  let _queue    = [];
  let _queueId  = 0;
  let _uploading = false;
  let _pollTimer = null;
  const _selected = new Set();   // ids de AiDocument marcados para acciones masivas

  // --- Helpers visuales ---

  function _levelBadge(level) {
    const l = parseInt(level) || 1;
    const label = DOC_LEVEL_SHORT[l] || t(`${NS}.level.1.short`);
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

  function _docClassBadge(cls) {
    if (!cls) return '';
    const label = DOC_CLASS_LABELS[cls] || cls;
    const color = DOC_CLASS_COLORS[cls] || '#888';
    const title = t(`${NS}.doc_class.${cls}_title`);
    return `<span title="${title}" style="display:inline-block;padding:1px 6px;border-radius:999px;
      font-size:9px;font-weight:700;background:${color}18;color:${color};border:1px solid ${color}40;
      text-transform:uppercase;letter-spacing:.03em;">${label}</span>`;
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

    if (_classFilter) {
      rows = rows.filter(r => r.doc && r.doc.doc_class === _classFilter);
    }

    return rows;
  }

  // --- Render principal ---

  async function render(el) {
    _stopPoll();
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t(`${NS}.header.title`)}</h1>
          <p class="page-sub">${t(`${NS}.header.subtitle`)}</p>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
          <input type="file" id="isms-ai-input" accept=".pdf,.docx,.txt" style="display:none;">
          <button class="btn" id="btn-isms-ai-extract" title="${t(`${NS}.header.btn_extract_ai_title`)}">
            ${t(`${NS}.header.btn_extract_ai`)}
          </button>
          <button onclick="ViewIsmsDocuments._generateWithAI()" class="btn"
                  style="background:linear-gradient(90deg,var(--brand-purple),var(--brand-orange));color:#fff;border:none;">
            ${t(`${NS}.header.btn_generate_ai`)}
          </button>
          <button class="btn btn-primary" id="btn-isms-new-pol">${t(`${NS}.header.btn_new`)}</button>
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
      aiBtn.disabled = true; aiBtn.textContent = t(`${NS}.header.btn_extract_ai_loading`);
      try {
        const extracted = await Api.policies.aiExtract(file);
        UI.toast(t(`${NS}.toast.extract_complete`), 'success');
        _openFormEnhanced(null, extracted);
      } catch (e) {
        UI.toast(t(`${NS}.toast.extract_error`, { error: e.message }), 'error');
      } finally {
        aiBtn.disabled = false; aiBtn.textContent = t(`${NS}.header.btn_extract_ai`);
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
          <div style="font-size:11px;color:var(--text-muted);">${t(`${NS}.stats.total_entries`)}</div>
        </div>
        <div class="card" style="text-align:center;padding:12px;">
          <div style="font-size:22px;font-weight:700;color:var(--risk-low);">${totalPolicies}</div>
          <div style="font-size:11px;color:var(--text-muted);">${t(`${NS}.stats.isms_records`)}</div>
        </div>
        <div class="card" style="text-align:center;padding:12px;">
          <div style="font-size:22px;font-weight:700;color:var(--risk-low);">${indexedDocs}</div>
          <div style="font-size:11px;color:var(--text-muted);">${t(`${NS}.stats.indexed_files`)}</div>
        </div>
        <div class="card" style="text-align:center;padding:12px;">
          <div style="font-size:22px;font-weight:700;color:var(--brand-orange);">${analysedDocs}</div>
          <div style="font-size:11px;color:var(--text-muted);">${t(`${NS}.stats.analysed_isms`)}</div>
        </div>
        <div class="card" style="text-align:center;padding:12px;">
          <div style="font-size:22px;font-weight:700;color:${overdueCount > 0 ? 'var(--risk-high)' : 'var(--text-muted)'};">${overdueCount}</div>
          <div style="font-size:11px;color:var(--text-muted);">${t(`${NS}.stats.overdue_review`)}</div>
        </div>
      </div>

      <!-- Zona de subida -->
      <div id="isms-upload-section" style="margin-bottom:14px;">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <label class="btn btn-primary" style="cursor:pointer;font-size:13px;"
                 title="${t(`${NS}.upload.btn_upload_title`)}">
            ${t(`${NS}.upload.btn_upload`)}
            <input type="file" id="isms-file-input"
                   accept=".pdf,.docx,.txt,.csv,.jpg,.jpeg,.png" multiple style="display:none;">
          </label>
          ${indexedDocs > 0 ? `
          <button class="btn btn-ghost" id="isms-analyze-pending-btn" style="font-size:12px;"
                  onclick="ViewIsmsDocuments._analyzePending()"
                  title="${t(`${NS}.upload.btn_analyze_pending_title`)}">
            ${t(`${NS}.upload.btn_analyze_pending`)}
          </button>
          <button class="btn btn-ghost" id="isms-analyze-all-btn" style="font-size:12px;"
                  onclick="ViewIsmsDocuments._analyzeAll()"
                  title="${t(`${NS}.upload.btn_reanalyze_all_title`)}">
            ${t(`${NS}.upload.btn_reanalyze_all`, { count: indexedDocs })}
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
          ${t(`${NS}.upload.dropzone_text`)}<br>
          <span style="font-size:11px;">${t(`${NS}.upload.dropzone_hint`)}</span>
        </div>
        <div id="isms-queue"></div>
      </div>

      <!-- Filtros por nivel -->
      <div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;
                  border-bottom:1px solid var(--border);padding-bottom:10px;">
        <button class="btn ${_filter === 'all' ? 'btn-primary' : ''} isms-lvl-tab" data-f="all">
          ${t(`${NS}.filters.tab_all`, { n: _merged.length })}
        </button>
        ${[1, 2, 3, 4].map(l => {
          const n = byLevel[l] || 0;
          return n > 0
            ? `<button class="btn ${_filter == l ? 'btn-primary' : ''} isms-lvl-tab" data-f="${l}">
                ${t(`${NS}.filters.tab_level`, { level: l, label: DOC_LEVEL_SHORT[l], n })}
               </button>` : '';
        }).join('')}
        ${noDocCnt > 0 ? `
        <button class="btn ${_filter === 'no_doc' ? 'btn-primary' : ''} isms-lvl-tab" data-f="no_doc"
                title="${t(`${NS}.filters.tab_no_doc_title`)}">
          ${t(`${NS}.filters.tab_no_doc`, { n: noDocCnt })}
        </button>` : ''}
        ${noPolicyCnt > 0 ? `
        <button class="btn ${_filter === 'no_policy' ? 'btn-primary' : ''} isms-lvl-tab" data-f="no_policy"
                title="${t(`${NS}.filters.tab_no_policy_title`)}">
          ${t(`${NS}.filters.tab_no_policy`, { n: noPolicyCnt })}
        </button>` : ''}
      </div>

      <!-- Busqueda y filtro de estado -->
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <input type="search" id="isms-search" class="input" style="width:220px;"
               placeholder="${t(`${NS}.filters.search_placeholder`)}" value="${UI.esc(_searchQ)}">
        <select id="isms-status-filter" class="input" style="width:160px;">
          <option value="">${t(`${NS}.filters.all_statuses`)}</option>
          ${Object.entries(STATUS_LABELS).map(([k, l]) =>
            `<option value="${k}" ${_statusFilter === k ? 'selected' : ''}>${l}</option>`
          ).join('')}
        </select>
        <select id="isms-class-filter" class="input" style="width:160px;">
          <option value="">${t(`${NS}.doc_class.filter_all`)}</option>
          ${Object.entries(DOC_CLASS_LABELS).map(([k, l]) =>
            `<option value="${k}" ${_classFilter === k ? 'selected' : ''}>${l}</option>`
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
    root.querySelector('#isms-class-filter').onchange = (e) => { _classFilter = e.target.value; _renderTable(); };

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
      wrap.innerHTML = `${_bulkBarHtml()}
        <p class="text-muted" style="text-align:center;margin-top:24px;">${t(`${NS}.table.no_docs_found`)}</p>`;
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
          fileCellHtml += `<br><span onclick="ViewIsmsDocuments._showError(${doc.id})"
            style="font-size:10px;color:var(--risk-critical);cursor:pointer;text-decoration:underline;"
            title="${t(`${NS}.table.view_error_title`)}">${t(`${NS}.table.view_error`)}</span>`;
        }
      } else {
        fileCellHtml = `<span style="font-size:11px;color:var(--text-muted);"
          title="${t(`${NS}.table.no_file_title`)}">${t(`${NS}.table.no_file`)}</span>`;
      }

      // Columna análisis ISMS
      let ismsCellHtml;
      if (doc && doc.isms_status) {
        const ic = ISMS_STATUS_COLORS[doc.isms_status] || 'var(--text-muted)';
        const il = ISMS_STATUS_LABELS[doc.isms_status] || doc.isms_status;
        const tooltip = doc.isms_summary_text ? ` title="${UI.esc(doc.isms_summary_text.slice(0, 200))}"` : '';
        if (doc.isms_status === 'error') {
          ismsCellHtml = `<span onclick="ViewIsmsDocuments._showError(${doc.id})"
            style="font-size:11px;font-weight:600;color:${ic};cursor:pointer;text-decoration:underline;"
            title="${t(`${NS}.table.view_error_title`)}">${il}</span>`;
        } else {
          ismsCellHtml = `<span style="font-size:11px;font-weight:600;color:${ic};"${tooltip}>${il}</span>`;
        }
        if (doc.isms_status === 'analysing') {
          ismsCellHtml += ' <span style="font-size:10px;color:var(--text-muted);">&#8635;</span>';
        }
      } else if (doc && doc.status === 'indexed') {
        ismsCellHtml = `<span style="font-size:11px;color:var(--text-muted);">${t(`${NS}.table.pending`)}</span>`;
      } else {
        ismsCellHtml = '<span style="font-size:11px;color:var(--text-muted);">-</span>';
      }

      // Columna controles/madurez
      let controlsHtml = '-';
      if (doc && doc.isms_controls_updated > 0) {
        controlsHtml = `<span onclick="ViewIsmsDocuments._showMaturityModal(${doc.id})"
          style="cursor:pointer;font-size:11px;color:var(--brand-purple);text-decoration:underline;"
          title="${t(`${NS}.table.view_maturity_title`)}">
          ${t(`${NS}.table.n_ctrl`, { n: doc.isms_controls_updated })}
        </span>`;
        if (doc.extracted_clauses && doc.extracted_clauses.length > 0) {
          controlsHtml += `<br><span onclick="ViewIsmsDocuments._showClauses(${doc.id})"
            style="cursor:pointer;font-size:10px;color:var(--brand-orange);text-decoration:underline;">
            ${t(`${NS}.table.n_clauses`, { n: doc.extracted_clauses.length })}
          </span>`;
        }
      }

      // Acciones
      const actions = [];
      if (policy) {
        actions.push(`<button class="btn btn-sm" onclick="ViewIsmsDocuments._editPolicy(${policy.id})">${t(`${NS}.table.btn_edit`)}</button>`);
      }
      if (doc && doc.status === 'indexed') {
        if (!doc.isms_status || doc.isms_status === 'error' || doc.isms_status === 'skipped') {
          actions.push(`<button class="btn btn-sm btn-ghost" onclick="ViewIsmsDocuments._analyze(${doc.id})">${t(`${NS}.table.btn_analyze`)}</button>`);
        } else if (doc.isms_status === 'analysed') {
          actions.push(`<button class="btn btn-sm btn-ghost" onclick="ViewIsmsDocuments._analyze(${doc.id})">${t(`${NS}.table.btn_reanalyze`)}</button>`);
        }
        if (doc.isms_controls_updated > 0) {
          actions.push(`<button class="btn btn-sm btn-ghost" onclick="ViewIsmsDocuments._showMaturityModal(${doc.id})">${t(`${NS}.table.btn_maturity`)}</button>`);
        }
      } else if (doc && (doc.status === 'error' || doc.status === 'pending')) {
        actions.push(`<button class="btn btn-sm btn-ghost" onclick="ViewIsmsDocuments._reprocess(${doc.id})">${t(`${NS}.table.btn_reprocess`)}</button>`);
      }
      if (policy) {
        actions.push(`<button class="btn btn-sm btn-danger" onclick="ViewIsmsDocuments._deletePolicy(${policy.id})">${t(`${NS}.table.btn_delete`)}</button>`);
      } else if (doc) {
        actions.push(`<button class="btn btn-sm btn-danger" onclick="ViewIsmsDocuments._deleteDoc(${doc.id})">${t(`${NS}.table.btn_delete`)}</button>`);
      }

      // Indicador de tipo de fila
      const typeTag = type === 'policy_only'
        ? `<span style="font-size:9px;background:#6b728018;color:#6b7280;border:1px solid #6b728030;
                        border-radius:3px;padding:1px 4px;margin-left:4px;vertical-align:middle;">${t(`${NS}.table.tag_no_file`)}</span>`
        : type === 'doc_only'
        ? `<span style="font-size:9px;background:var(--brand-orange)18;color:var(--brand-orange);
                        border:1px solid var(--brand-orange)30;border-radius:3px;padding:1px 4px;
                        margin-left:4px;vertical-align:middle;">${t(`${NS}.table.tag_no_record`)}</span>`
        : '';

      const rowStyle = reviewOverdue ? 'background:rgba(254,226,226,0.3);' : '';

      // Checkbox de seleccion: solo filas con documento (las acciones masivas
      // operan sobre AiDocument; una fila policy_only no tiene archivo).
      const selectCell = doc
        ? `<td onclick="event.stopPropagation()" style="text-align:center;">
             <input type="checkbox" class="isms-row-check" data-id="${doc.id}"
                    ${_selected.has(doc.id) ? 'checked' : ''}>
           </td>`
        : '<td></td>';

      return `
        <tr style="${rowStyle}">
          ${selectCell}
          <td>${effectiveLevel ? _levelBadge(effectiveLevel) : '<span style="font-size:11px;color:var(--text-muted);">-</span>'}</td>
          <td style="max-width:320px;">
            ${code ? `<div style="font-size:10px;font-family:var(--font-mono);color:var(--brand-purple);font-weight:700;margin-bottom:2px;">${UI.esc(code)}</div>` : ''}
            <div style="font-size:13px;font-weight:600;">
              ${UI.esc(title)}${typeTag}
            </div>
            <div style="margin-top:3px;display:flex;gap:4px;flex-wrap:wrap;align-items:center;">
              ${doc && doc.doc_class ? _docClassBadge(doc.doc_class) : ''}
              ${policy && policy.category ? _typeBadge(policy.category) : ''}
            </div>
          </td>
          <td style="font-size:12px;font-family:var(--font-mono);">${version ? 'v' + UI.esc(version) : '-'}</td>
          <td>${status ? _statusBadge(status) : '-'}</td>
          <td>${fileCellHtml}</td>
          <td>${ismsCellHtml}</td>
          <td>${controlsHtml}</td>
          <td style="font-size:12px;">
            ${reviewDate
              ? `<span style="color:${reviewOverdue ? 'var(--risk-high)' : 'inherit'};font-weight:${reviewOverdue ? '700' : '400'};">
                   ${reviewDate.slice(0, 10)}${reviewOverdue ? `<br><small>${t(`${NS}.table.overdue_suffix`)}</small>` : ''}
                 </span>`
              : '-'}
          </td>
          <td onclick="event.stopPropagation()" style="white-space:nowrap;">
            <div style="display:flex;gap:3px;flex-wrap:wrap;">${actions.join('')}</div>
          </td>
        </tr>`;
    }).join('');

    // Ids de documento visibles con el filtro actual (para "seleccionar todo")
    const visibleDocIds = rows.filter(r => r.doc).map(r => r.doc.id);
    const allChecked = visibleDocIds.length > 0 && visibleDocIds.every(id => _selected.has(id));

    wrap.innerHTML = `
      ${_bulkBarHtml()}
      <div class="card" style="padding:0;overflow-x:auto;">
        <table class="data" style="min-width:920px;">
          <thead>
            <tr>
              <th style="width:34px;text-align:center;">
                <input type="checkbox" id="isms-check-all" title="${t(`${NS}.table.col_select_title`)}"
                       ${allChecked ? 'checked' : ''}>
              </th>
              <th>${t(`${NS}.table.col_level`)}</th>
              <th>${t(`${NS}.table.col_code_title`)}</th>
              <th>${t(`${NS}.table.col_version`)}</th>
              <th>${t(`${NS}.table.col_status`)}</th>
              <th>${t(`${NS}.table.col_file`)}</th>
              <th>${t(`${NS}.table.col_isms_analysis`)}</th>
              <th>${t(`${NS}.table.col_controls`)}</th>
              <th>${t(`${NS}.table.col_review`)}</th>
              <th>${t(`${NS}.table.col_actions`)}</th>
            </tr>
          </thead>
          <tbody>${tableRows}</tbody>
        </table>
      </div>`;

    // Cablear checkboxes de fila
    wrap.querySelectorAll('.isms-row-check').forEach(cb => {
      cb.onchange = () => {
        const id = parseInt(cb.dataset.id);
        if (cb.checked) _selected.add(id); else _selected.delete(id);
        _renderBulkBar();
        const head = document.getElementById('isms-check-all');
        if (head) head.checked = visibleDocIds.length > 0 && visibleDocIds.every(i => _selected.has(i));
      };
    });

    // Seleccionar / deseleccionar todos los visibles
    const checkAll = document.getElementById('isms-check-all');
    if (checkAll) {
      checkAll.onchange = () => {
        if (checkAll.checked) visibleDocIds.forEach(id => _selected.add(id));
        else visibleDocIds.forEach(id => _selected.delete(id));
        _renderTable();
      };
    }
  }

  // --- Barra de acciones masivas ---

  function _bulkBarHtml() {
    if (_selected.size === 0) return '';
    return `
      <div id="isms-bulk-bar" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;
           margin-bottom:10px;padding:10px 12px;border-radius:8px;
           background:var(--brand-purple-4, rgba(89,0,141,0.06));border:1px solid var(--border);">
        <strong style="font-size:13px;color:var(--brand-purple);">
          ${t(`${NS}.bulk.selected`, { n: _selected.size })}
        </strong>
        <button class="btn btn-sm btn-ghost" onclick="ViewIsmsDocuments._bulkClear()">${t(`${NS}.bulk.clear`)}</button>
        <span style="flex:1;"></span>
        <button class="btn btn-sm btn-ghost" onclick="ViewIsmsDocuments._bulkAnalyze()">${t(`${NS}.bulk.analyze`)}</button>
        <button class="btn btn-sm btn-ghost" onclick="ViewIsmsDocuments._bulkRecategorize()">${t(`${NS}.bulk.recategorize`)}</button>
        <button class="btn btn-sm btn-danger" onclick="ViewIsmsDocuments._bulkDelete()">${t(`${NS}.bulk.delete`)}</button>
      </div>`;
  }

  function _renderBulkBar() {
    const wrap = document.getElementById('isms-table-wrap');
    if (!wrap) return;
    const existing = document.getElementById('isms-bulk-bar');
    const html = _bulkBarHtml();
    if (existing) {
      if (html) existing.outerHTML = html; else existing.remove();
    } else if (html) {
      wrap.insertAdjacentHTML('afterbegin', html);
    }
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
        UI.toast(t(`${NS}.upload.unsupported_format`, { name: file.name }), 'error');
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
          <strong style="font-size:14px;">${t(`${NS}.upload.queue.title`)}
            <span style="font-weight:400;font-size:12px;color:var(--text-muted);">${t(`${NS}.upload.queue.files_count`, { n: _queue.length, s: _queue.length !== 1 ? 's' : '' })}</span>
          </strong>
          ${pending.length > 0 && !_uploading ? `
            <div style="display:flex;gap:8px;">
              <button class="btn btn-ghost" style="font-size:12px;" id="isms-clear-queue">${t(`${NS}.upload.queue.clear_pending`)}</button>
              <button class="btn btn-primary" style="font-size:12px;" id="isms-upload-all">
                ${t(`${NS}.upload.queue.upload_btn`, { n: pending.length, s: pending.length !== 1 ? 's' : '' })}
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
              ? `<span style="color:var(--risk-low);">&#10003; ${t(`${NS}.upload.queue.status_uploaded`)}</span>`
              : isError
              ? `<span style="color:var(--risk-critical);" title="${UI.esc(item.error || '')}">&#10007; ${t(`${NS}.upload.queue.status_error`)}</span>`
              : isUploading
              ? `<span style="color:var(--brand-orange);">${t(`${NS}.upload.queue.status_uploading`)}</span>` : '';
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
                    <option value="other" ${item.category === 'other' ? 'selected' : ''}>${t(`${NS}.upload.queue.category_auto`)}</option>
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
            <button class="btn btn-ghost" style="font-size:12px;" id="isms-dismiss-done">${t(`${NS}.upload.queue.clear_completed`)}</button>
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
        item.status = 'error'; item.error = e.message || t(`${NS}.toast.unknown_error`); fail++;
      }
      _renderQueue();
    }

    _uploading = false;
    await _load();
    if (ok > 0 && fail === 0) {
      UI.toast(t(`${NS}.toast.upload_success`, { ok, s: ok !== 1 ? 's' : '' }), 'success');
    } else if (ok > 0) {
      UI.toast(t(`${NS}.toast.upload_partial`, { ok, fail }), 'error');
    } else {
      UI.toast(t(`${NS}.toast.upload_error`), 'error');
    }
    _renderQueue();
    _renderRoot();
    _startPollIfNeeded();
  }

  // --- Polling para documentos en análisis ---

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
      UI.toast(t(`${NS}.toast.analysis_started`), 'success');
      _startPollIfNeeded();
    } catch (e) { UI.toast(t(`${NS}.toast.generic_error`, { error: e.message }), 'error'); }
  }

  async function _reprocess(docId) {
    try {
      await Api.aiDocuments.reprocess(docId);
      await _load(); _renderRoot();
      UI.toast(t(`${NS}.toast.doc_reprocessed`), 'success');
    } catch (e) { UI.toast(t(`${NS}.toast.generic_error`, { error: e.message }), 'error'); }
  }

  async function _deleteDoc(docId) {
    if (!confirm(t(`${NS}.toast.confirm_delete_doc`))) return;
    try {
      await Api.aiDocuments.del(docId);
      await _load(); _renderRoot();
      UI.toast(t(`${NS}.toast.doc_deleted`), 'success');
    } catch (e) { UI.toast(t(`${NS}.toast.generic_error`, { error: e.message }), 'error'); }
  }

  async function _deletePolicy(policyId) {
    if (!confirm(t(`${NS}.toast.confirm_delete_policy`))) return;
    try {
      await Api.policies.del(policyId);
      await _load(); _renderRoot();
      UI.toast(t(`${NS}.toast.policy_deleted`), 'success');
    } catch (e) { UI.toast(t(`${NS}.toast.generic_error`, { error: e.message }), 'error'); }
  }

  async function _analyzePending() {
    const btn = document.getElementById('isms-analyze-pending-btn');
    if (btn) { btn.disabled = true; btn.textContent = t(`${NS}.upload.starting`); }
    try {
      const res = await Api.aiDocuments.analyzePending();
      await _load(); _renderRoot();
      const msg = res.stuck_reset > 0
        ? t(`${NS}.toast.pending_reset_and_queued`, { reset: res.stuck_reset, queued: res.queued })
        : (res.queued > 0 ? t(`${NS}.toast.pending_queued`, { queued: res.queued }) : t(`${NS}.toast.pending_none`));
      UI.toast(msg, 'success');
      _startPollIfNeeded();
    } catch (e) {
      UI.toast(t(`${NS}.toast.generic_error`, { error: e.message }), 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = t(`${NS}.upload.btn_analyze_pending`); }
    }
  }

  async function _analyzeAll() {
    const btn = document.getElementById('isms-analyze-all-btn');
    if (btn) { btn.disabled = true; btn.textContent = t(`${NS}.upload.starting`); }
    try {
      const res = await Api.aiDocuments.analyzeAll();
      await _load(); _renderRoot();
      UI.toast(res.message || t(`${NS}.toast.reanalyze_started`, { queued: res.queued }), 'success');
      _startPollIfNeeded();
    } catch (e) {
      UI.toast(t(`${NS}.toast.generic_error`, { error: e.message }), 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = t(`${NS}.upload.btn_reanalyze_all_reset`); }
    }
  }

  // --- Acciones masivas ---

  function _bulkClear() {
    _selected.clear();
    _renderTable();
  }

  async function _bulkDelete() {
    if (_selected.size === 0) return;
    const ids = Array.from(_selected);
    // Preview: cuenta que se desvincularia sin borrar nada.
    let detail = '';
    try {
      const preview = await Api.aiDocuments.bulk({ action: 'delete', doc_ids: ids, dry_run: true });
      const det = preview.detached || {};
      const parts = Object.entries(det).filter(([, n]) => n > 0)
        .map(([k, n]) => `${n} ${k}`);
      if (parts.length) detail = t(`${NS}.bulk.detail_detached`, { items: parts.join(', ') });
    } catch (_) { /* si el preview falla, se pide confirmacion igual */ }

    if (!confirm(t(`${NS}.bulk.confirm_delete`, { docs: ids.length, detail }))) return;
    try {
      const res = await Api.aiDocuments.bulk({ action: 'delete', doc_ids: ids });
      _selected.clear();
      await _load(); _renderRoot();
      _bulkToast('delete', res);
    } catch (e) { UI.toast(t(`${NS}.toast.generic_error`, { error: e.message }), 'error'); }
  }

  async function _bulkAnalyze() {
    if (_selected.size === 0) return;
    const ids = Array.from(_selected);
    try {
      const res = await Api.aiDocuments.bulk({ action: 'analyze', doc_ids: ids });
      _selected.clear();
      await _load(); _renderRoot();
      _bulkToast('analyze', res);
      _startPollIfNeeded();
    } catch (e) { UI.toast(t(`${NS}.toast.generic_error`, { error: e.message }), 'error'); }
  }

  async function _bulkRecategorize() {
    if (_selected.size === 0) return;
    const opts = Object.entries(CATEGORY_LABELS).map(([k, l]) => `${k} = ${l}`).join('\n');
    const cat = prompt(`${t(`${NS}.bulk.recategorize_prompt`)}\n\n${opts}`, 'policies');
    if (!cat || !CATEGORY_LABELS[cat]) return;
    const ids = Array.from(_selected);
    try {
      const res = await Api.aiDocuments.bulk({ action: 'recategorize', doc_ids: ids, category: cat });
      _selected.clear();
      await _load(); _renderRoot();
      _bulkToast('recategorize', res);
    } catch (e) { UI.toast(t(`${NS}.toast.generic_error`, { error: e.message }), 'error'); }
  }

  function _bulkToast(action, res) {
    const skipped = res.skipped || {};
    const skipCount = Object.values(skipped).reduce((a, v) => a + (Array.isArray(v) ? v.length : 0), 0);
    UI.toast(t(`${NS}.bulk.done`, { action, ok: res.affected || 0, skip: skipCount }), 'success');
  }

  // --- Modal de detalle de error ---
  // El cliente pedia poder ver el error real: antes solo habia un badge rojo mudo.

  function _showError(docId) {
    const doc = _docs.find(d => d.id === docId);
    if (!doc) return;
    const msg = (doc.isms_summary && (doc.isms_summary.error || doc.isms_summary.reason))
      || doc.error_message || doc.isms_summary_text || '-';
    const canRetry = doc.status === 'indexed';
    UI.modal(
      t(`${NS}.error_modal.title`),
      `<div style="font-family:var(--font-mono);font-size:12px;white-space:pre-wrap;
            background:var(--bg-subtle,#f6f6f8);border:1px solid var(--border);
            border-radius:6px;padding:12px;max-height:40vh;overflow:auto;color:var(--risk-critical);">
         ${UI.esc(String(msg))}
       </div>
       <p style="font-size:12px;color:var(--text-muted);margin-top:10px;">${t(`${NS}.error_modal.hint`)}</p>`,
      {
        width: 'min(640px, 95vw)',
        actions: `<button class="btn" id="m-cancel">${t(`${NS}.error_modal.close`)}</button>
                  ${canRetry ? `<button class="btn btn-primary" id="m-retry">${t(`${NS}.error_modal.retry`)}</button>` : ''}`,
      }
    );
    document.getElementById('m-cancel').onclick = UI.closeModal;
    const retry = document.getElementById('m-retry');
    if (retry) retry.onclick = () => { UI.closeModal(); _analyze(docId); };
  }

  // --- Formulario de política ---

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
    UI.modal(t(`${NS}.versioning_modal.title`), `
      <p style="margin-bottom:10px;">${t(`${NS}.versioning_modal.body_status`, {
        code: UI.esc(policy.code), status: STATUS_LABELS[policy.status] || policy.status, version: UI.esc(policy.version || '1.0'),
      })}</p>
      <p style="font-size:13px;color:var(--text-subtle);">${t(`${NS}.versioning_modal.body_next`, { version: UI.esc(nextVer) })}</p>
    `, {
      actions: `<button class="btn" id="m-cancel">${t(`${NS}.common.cancel`)}</button>
                <button class="btn btn-primary" id="m-confirm-v">${t(`${NS}.versioning_modal.btn_confirm`, { version: UI.esc(nextVer) })}</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-confirm-v').onclick = async () => {
      try {
        const draft = await Api.policies.newVersion(policy.id);
        UI.toast(t(`${NS}.toast.version_created`, { version: draft.version }), 'success');
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
      policy ? t(`${NS}.edit_lock.modal_title_edit`, { code: policy.code }) : t(`${NS}.edit_lock.modal_title_new`),
      _formHtml(policy, extracted),
      {
        actions: `<button class="btn" id="m-cancel">${t(`${NS}.common.cancel`)}</button>
                  <button class="btn btn-primary" id="m-save">${t(`${NS}.common.save`)}</button>`,
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
        ${notes ? `<div class="span2"><div class="notice" style="margin-bottom:4px;font-size:12px;">${t(`${NS}.form.ai_note`, { notes: UI.esc(notes) })}</div></div>` : ''}
        <div class="span2">
          <label>${t(`${NS}.form.title_label`)}</label>
          <input id="f-title" class="input" value="${UI.esc(title)}">
        </div>

        <div>
          <label>${t(`${NS}.form.hierarchy_level_label`)}
            <span title="${t(`${NS}.form.hierarchy_level_tooltip`)}"
                  style="cursor:help;color:var(--text-muted);font-weight:400;font-size:11px;"> (?)</span>
          </label>
          <select id="f-doc-level" class="input" onchange="ViewIsmsDocuments._onLevelChange(this)">
            ${Object.entries(DOC_LEVEL_LABELS).map(([k, l]) =>
              `<option value="${k}" ${docLevel == k ? 'selected' : ''}>${t(`${NS}.form.level_option`, { k, label: l, max: DOC_LEVEL_MAX_MATURITY[k] })}</option>`
            ).join('')}
          </select>
          <div id="f-level-hint" style="font-size:11px;color:var(--text-muted);margin-top:3px;"></div>
        </div>

        <div>
          <label>${t(`${NS}.form.parent_label`)}</label>
          <select id="f-parent" class="input">
            <option value="">${t(`${NS}.form.parent_none_option`)}</option>
            ${parentOptions}
          </select>
          <div style="font-size:11px;color:var(--text-muted);margin-top:3px;">
            ${t(`${NS}.form.parent_help`)}
          </div>
        </div>

        <div>
          <label>${t(`${NS}.form.doc_type_label`)}</label>
          <select id="f-cat" class="input">
            <option value="">${t(`${NS}.form.doc_type_none_option`)}</option>
            ${Object.entries(ISMS_TYPES).map(([k, l]) =>
              `<option value="${k}" ${normalizedCat === k ? 'selected' : ''}>${l}</option>`
            ).join('')}
          </select>
          ${category && !normalizedCat ? `<div style="font-size:11px;color:var(--text-muted);margin-top:3px;">${t(`${NS}.form.doc_type_detected`, { category: UI.esc(category) })}</div>` : ''}
        </div>

        <div>
          <label>${t(`${NS}.form.status_label`)}</label>
          <select id="f-status" class="input">
            ${Object.entries(STATUS_LABELS).map(([k, l]) =>
              `<option value="${k}" ${(p.status || 'draft') === k ? 'selected' : ''}>${l}</option>`
            ).join('')}
          </select>
        </div>

        <div>
          <label>${t(`${NS}.form.version_label`)}</label>
          <input id="f-version" class="input" value="${UI.esc(version)}">
        </div>

        <div>
          <label>${t(`${NS}.form.owner_label`)}</label>
          <select id="f-owner" class="input">
            <option value="">${t(`${NS}.form.owner_none_option`)}</option>
            ${_users.map(u =>
              `<option value="${u.id}" ${p.owner_id === u.id ? 'selected' : ''}>${UI.esc(u.full_name || u.email)}</option>`
            ).join('')}
          </select>
        </div>

        <div>
          <label>${t(`${NS}.form.review_date_label`)}</label>
          <input type="date" id="f-review" class="input" value="${UI.esc(review)}">
        </div>

        <div>
          <label>${t(`${NS}.form.clauses_label`)}</label>
          <input id="f-clauses" class="input" value="${UI.esc(clauses)}">
        </div>

        <div class="span2">
          <label>${t(`${NS}.form.scope_label`)}</label>
          <textarea id="f-scope" class="input" rows="2">${UI.esc(scope)}</textarea>
        </div>

        <div class="span2">
          <label>${t(`${NS}.form.content_label`)}</label>
          <textarea id="f-content" class="input" rows="5">${UI.esc(content)}</textarea>
        </div>

        ${policy && policy.source_document_id ? `
        <div class="span2" style="padding-top:14px;border-top:1px solid var(--border);margin-top:4px;">
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--text-muted);
                      letter-spacing:.5px;margin-bottom:8px;">${t(`${NS}.form.maturity_analysis_label`)}</div>
          <div id="pol-maturity-panel">
            <div style="font-size:12px;color:var(--text-muted);">${t(`${NS}.form.loading`)}</div>
          </div>
        </div>` : ''}
      </div>`;
  }

  function _onLevelChange(sel) {
    const hint = document.getElementById('f-level-hint');
    if (!hint) return;
    const l = parseInt(sel.value) || 1;
    const hints = {
      1: t(`${NS}.form.level_hint_1`),
      2: t(`${NS}.form.level_hint_2`),
      3: t(`${NS}.form.level_hint_3`),
      4: t(`${NS}.form.level_hint_4`),
    };
    hint.textContent = hints[l] || '';
  }

  async function _save(policy) {
    const title = document.getElementById('f-title').value.trim();
    if (!title) { UI.toast(t(`${NS}.toast.title_required`), 'error'); return; }
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
        UI.toast(t(`${NS}.toast.policy_updated`), 'success');
      } else {
        await Api.policies.create(payload);
        UI.toast(t(`${NS}.toast.policy_created`), 'success');
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
    t(`${NS}.maturity_panel.default_gap_0`),
    t(`${NS}.maturity_panel.default_gap_1`),
    t(`${NS}.maturity_panel.default_gap_2`),
    t(`${NS}.maturity_panel.default_gap_3`),
    t(`${NS}.maturity_panel.default_gap_4`),
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
      panel.innerHTML = `<p style="font-size:12px;color:var(--text-muted);">${t(`${NS}.maturity_panel.no_analysis`)}</p>`;
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
            ${rationale ? `<div style="margin-bottom:7px;"><div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);letter-spacing:.4px;margin-bottom:3px;">${t(`${NS}.maturity_panel.why_label`, { n: c.maturity || 0 })}</div><div style="background:var(--bg-2);border-left:3px solid ${color};border-radius:0 4px 4px 0;padding:6px 10px;">${UI.esc(rationale)}</div></div>` : ''}
            ${displayGap ? `<div><div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);letter-spacing:.4px;margin-bottom:3px;">${t(`${NS}.maturity_panel.gap_label`)}</div><div style="background:rgba(89,0,141,.05);border-left:3px solid var(--brand-purple);border-radius:0 4px 4px 0;padding:6px 10px;">${UI.esc(displayGap)}</div></div>` : ''}
          </div>
        </div>`;
    }).join('');

    panel.innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;padding:8px 12px;background:var(--bg-2);border-radius:6px;margin-bottom:8px;">
        <div style="font-size:20px;font-weight:800;color:${avgColor};">${avg.toFixed(1)}</div>
        <div style="flex:1;">
          <div style="font-size:12px;font-weight:600;">${t(`${NS}.maturity_panel.title`)}</div>
          <div style="font-size:11px;color:var(--text-muted);">${t(`${NS}.maturity_panel.controls_count`, { n: controls.length, es: controls.length !== 1 ? 'es' : '' })}</div>
        </div>
      </div>
      ${rows}`;
  }

  // --- Modal de madurez completo ---

  const _MODAL_LEVEL_LABELS = {
    1: t(`${NS}.level.1.long`), 2: t(`${NS}.level.2.long`), 3: t(`${NS}.level.3.long`), 4: t(`${NS}.level.4.long`),
  };

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
      UI.toast(t(`${NS}.toast.maturity_load_error`, { error: e.message }), 'error'); return;
    }
    if (!controls.length) {
      UI.toast(t(`${NS}.toast.no_linked_controls`), 'info');
      return;
    }

    const avgMaturity  = controls.reduce((s, c) => s + (c.maturity || 0), 0) / controls.length;
    const avgColor     = _maturityColor(Math.round(avgMaturity));
    const summary      = doc?.isms_summary || {};
    const docLevel     = summary.document_level || 1;
    const docLevelLabel = summary.document_level_label || _MODAL_LEVEL_LABELS[docLevel] || t(`${NS}.level.1.long`);
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
              <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);letter-spacing:.5px;margin-bottom:5px;">${t(`${NS}.maturity_modal.rationale_label`)}</div>
              <div style="font-size:12px;line-height:1.65;background:var(--bg-2);border-radius:6px;padding:8px 12px;border-left:3px solid ${color};">${UI.esc(rationale)}</div>
            </div>` : ''}
          ${gap ? `
            <div>
              <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);letter-spacing:.5px;margin-bottom:5px;">${t(`${NS}.maturity_modal.gap_label`)}</div>
              <div style="font-size:12px;line-height:1.65;background:rgba(89,0,141,.05);border-radius:6px;padding:8px 12px;border-left:3px solid var(--brand-purple);">${UI.esc(gap)}</div>
            </div>` : (!rationale ? `
            <div style="font-size:11px;color:var(--text-muted);font-style:italic;margin-top:4px;">
              ${t(`${NS}.maturity_modal.no_gap`)}
            </div>` : '')}
        </div>`;
    }).join('');

    UI.openModal(`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">${t(`${NS}.maturity_modal.header`)}</h3>
        <button class="btn btn-ghost btn-sm" onclick="UI.closeModal()">&#10005;</button>
      </div>
      <div style="margin-bottom:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <span style="font-size:12px;color:var(--text-muted);">${t(`${NS}.maturity_modal.doc_label`)}</span>
        <strong style="font-size:12px;">${UI.esc(doc?.original_name || '')}</strong>
        <span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:10px;font-weight:700;
                     background:${docLevelColor}18;color:${docLevelColor};border:1px solid ${docLevelColor}40;">
          ${t(`${NS}.maturity_modal.level_badge`, { level: docLevel, label: docLevelLabel })}
        </span>
      </div>
      <div style="background:var(--bg-2);border-radius:8px;padding:12px 16px;margin-bottom:12px;display:flex;align-items:center;gap:14px;">
        <div style="font-size:28px;font-weight:800;color:${avgColor};">${avgMaturity.toFixed(1)}</div>
        <div>
          <div style="font-size:13px;font-weight:600;">${t(`${NS}.maturity_panel.title`)}</div>
          <div style="font-size:11px;color:var(--text-muted);">
            ${t(`${NS}.maturity_modal.controls_count`, { n: controls.length, es: controls.length !== 1 ? 'es' : '' })} &nbsp;&middot;&nbsp;
            ${t(`${NS}.maturity_modal.max_maturity`, { level: docLevel, max: levelMaxMaturity })}
          </div>
        </div>
      </div>
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:14px;padding:7px 10px;
                  background:rgba(89,0,141,.04);border-radius:5px;border:1px solid rgba(89,0,141,.1);">
        ${t(`${NS}.maturity_modal.explanation`, { level: docLevel, label: docLevelLabel, max: levelMaxMaturity })}
      </div>
      <div style="overflow-y:auto;max-height:56vh;">${rows}</div>
    `, { width: '700px' });
  }

  // --- Modal de cláusulas ISO ---

  function _showClauses(docId) {
    const doc = _docs.find(d => d.id === docId);
    if (!doc) return;
    const clauses = Array.isArray(doc.extracted_clauses) ? doc.extracted_clauses : [];
    if (!clauses.length) { UI.toast(t(`${NS}.toast.no_clauses`), 'info'); return; }

    const rows = clauses.map(c => `
      <tr style="border-bottom:1px solid var(--border);">
        <td style="padding:8px 12px;font-weight:600;color:var(--brand-purple);white-space:nowrap;">${UI.esc(c.ref)}</td>
        <td style="padding:8px 12px;font-size:13px;">${UI.esc(c.title || '')}</td>
        <td style="padding:8px 12px;text-align:center;">
          ${c.control_id ? `<a href="#/controls" style="font-size:11px;color:var(--risk-low);">${t(`${NS}.clauses_modal.control_hash`, { id: c.control_id })}</a>` : '<span style="font-size:11px;color:var(--text-muted);">-</span>'}
        </td>
        <td style="padding:8px 12px;text-align:center;font-size:11px;color:${c.confidence >= 0.8 ? 'var(--risk-low)' : 'var(--brand-orange)'};">
          ${Math.round((c.confidence || 0) * 100)}%
        </td>
      </tr>`).join('');

    UI.openModal(`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">${t(`${NS}.clauses_modal.header`)}</h3>
        <button class="btn btn-ghost btn-sm" onclick="UI.closeModal()">x</button>
      </div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">${t(`${NS}.clauses_modal.doc_line`, { name: UI.esc(doc.original_name) })}</p>
      <div style="overflow-y:auto;max-height:60vh;">
        <table style="width:100%;border-collapse:collapse;">
          <thead>
            <tr style="background:var(--bg-2);font-size:11px;text-transform:uppercase;color:var(--text-muted);">
              <th style="padding:8px 12px;text-align:left;">${t(`${NS}.clauses_modal.col_clause`)}</th>
              <th style="padding:8px 12px;text-align:left;">${t(`${NS}.clauses_modal.col_title`)}</th>
              <th style="padding:8px 12px;text-align:center;">${t(`${NS}.clauses_modal.col_control`)}</th>
              <th style="padding:8px 12px;text-align:center;">${t(`${NS}.clauses_modal.col_confidence`)}</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `, { width: '680px' });
  }

  // --- Generación con IA ---

  async function _generateWithAI() {
    UI.openModal(`
      <div style="max-width:600px;">
        <h3 style="margin:0 0 4px;color:var(--brand-purple);font-size:17px;">${t(`${NS}.generate_modal.title`)}</h3>
        <p style="font-size:12px;color:var(--text-muted);margin:0 0 18px;">
          ${t(`${NS}.generate_modal.subtitle`)}
        </p>
        <div class="form-grid" style="gap:12px;">
          <div>
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">${t(`${NS}.generate_modal.doc_type_label`)}</label>
            <select id="gen-type" class="input" style="width:100%;">
              <option value="politica">${t(`${NS}.generate_modal.opt_politica`)}</option>
              <option value="norma">${t(`${NS}.generate_modal.opt_norma`)}</option>
              <option value="instruccion_tecnica">${t(`${NS}.generate_modal.opt_instruccion`)}</option>
            </select>
          </div>
          <div>
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">${t(`${NS}.generate_modal.framework_label`)}</label>
            <select id="gen-framework" class="input" style="width:100%;">
              ${FRAMEWORKS.map(f => `<option value="${UI.esc(f.value)}">${UI.esc(f.label)}</option>`).join('')}
            </select>
          </div>
          <div class="span2">
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">${t(`${NS}.generate_modal.title_label`)}</label>
            <input id="gen-title" class="input" style="width:100%;" placeholder="${t(`${NS}.generate_modal.title_placeholder`)}">
          </div>
          <div class="span2">
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">${t(`${NS}.generate_modal.desc_label`)}</label>
            <textarea id="gen-desc" class="input" rows="3" style="width:100%;"
                      placeholder="${t(`${NS}.generate_modal.desc_placeholder`)}"></textarea>
          </div>
          <div class="span2">
            <label style="font-size:12px;font-weight:600;display:block;margin-bottom:4px;">
              ${t(`${NS}.generate_modal.context_label`)}
            </label>
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;border:1px dashed var(--border);
                          border-radius:6px;padding:8px 12px;font-size:12px;color:var(--text-muted);">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              <span id="gen-file-label">${t(`${NS}.generate_modal.upload_hint`)}</span>
              <input type="file" id="gen-context-file" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg"
                     style="display:none;" onchange="ViewIsmsDocuments._onGenFileChange(this)">
            </label>
          </div>
        </div>
        <div style="margin-top:16px;background:#fff8e6;border:1px solid #f0c040;border-radius:8px;
                    padding:10px 14px;font-size:12px;color:#7a5800;line-height:1.5;">
          ${t(`${NS}.generate_modal.warning_banner`)}
        </div>
        <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;">
          <button onclick="UI.closeModal()" class="btn">${t(`${NS}.common.cancel`)}</button>
          <button onclick="ViewIsmsDocuments._submitGenerate()" class="btn"
                  style="background:linear-gradient(90deg,var(--brand-purple),var(--brand-orange));color:#fff;border:none;">
            ${t(`${NS}.header.btn_generate_ai`)}
          </button>
        </div>
      </div>`);
  }

  function _onGenFileChange(input) {
    const label = document.getElementById('gen-file-label');
    if (label && input.files[0]) {
      label.textContent = t(`${NS}.generate_modal.file_size_label`, { name: input.files[0].name, size: (input.files[0].size / 1024).toFixed(0) });
    }
  }

  async function _submitGenerate() {
    const title = document.getElementById('gen-title')?.value.trim();
    if (!title) { UI.toast(t(`${NS}.toast.title_required`), 'error'); return; }
    const docType   = document.getElementById('gen-type')?.value;
    const framework = document.getElementById('gen-framework')?.value;
    const desc      = document.getElementById('gen-desc')?.value.trim();
    const file      = document.getElementById('gen-context-file')?.files[0] || null;

    UI.closeModal();
    UI.toast(t(`${NS}.toast.generating`), 'info');

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
            <span style="font-size:11px;color:var(--text-muted);align-self:center;">${t(`${NS}.generate_modal.result_framework`, { framework: UI.esc(result.framework || framework) })}</span>
          </div>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px;">${t(`${NS}.generate_modal.review_before_save`)}</p>
          <textarea id="gen-result-content" style="width:100%;height:340px;font-size:12px;font-family:monospace;
                    border:1px solid var(--border);border-radius:6px;padding:10px;resize:vertical;">${UI.esc(result.content)}</textarea>
          <div style="margin-top:10px;background:#fff8e6;border:1px solid #f0c040;border-radius:6px;
                      padding:8px 12px;font-size:11px;color:#7a5800;">
            ${t(`${NS}.generate_modal.warning_banner2`)}
          </div>
          <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end;">
            <button onclick="UI.closeModal()" class="btn">${t(`${NS}.generate_modal.btn_discard`)}</button>
            <button onclick="ViewIsmsDocuments._saveGenerated(${JSON.stringify({
              title: result.title,
              category: result.category || docType,
              iso_clauses: result.iso_clauses || [],
              framework,
            }).replace(/"/g, '&quot;')})"
                    class="btn btn-primary">${t(`${NS}.generate_modal.btn_save_draft`)}</button>
          </div>
        </div>`);
    } catch (e) {
      UI.toast(t(`${NS}.toast.generate_error`, { error: e.message }), 'error');
    }
  }

  async function _saveGenerated(meta) {
    const content = document.getElementById('gen-result-content')?.value || '';
    try {
      await Api.policies.create({
        title: meta.title, content, category: meta.category || null,
        iso_clauses: meta.iso_clauses || [],
        scope: t(`${NS}.generate_modal.default_scope`),
        version: '1.0', status: 'draft', review_cycle_months: 12,
      });
      UI.closeModal();
      UI.toast(t(`${NS}.toast.draft_saved`), 'success');
      await _load(); _renderRoot();
    } catch (e) { UI.toast(t(`${NS}.toast.save_error`, { error: e.message }), 'error'); }
  }

  // ============================================================
  // FASE 1 — Flujo de aprobación por email
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
        <strong>${t(`${NS}.approval.smtp_title`)}</strong> ${t(`${NS}.approval.smtp_body_before_link`)}
        <a href="#/admin-hub/integrations" onclick="UI.closeModal()"
           style="color:#59008D;font-weight:600;">${t(`${NS}.approval.smtp_link_text`)}</a>
        ${t(`${NS}.approval.smtp_body_after_link`)}
      </div>`;

    UI.openModal(`
      <div style="min-width:520px;max-width:600px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="margin:0;font-size:16px;color:var(--brand-purple);">${t(`${NS}.approval.title`)}</h3>
          <button onclick="UI.closeModal()" class="btn btn-ghost btn-sm">&#10005;</button>
        </div>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
          ${t(`${NS}.approval.doc_line`, { code: UI.esc(policy.code), title: UI.esc(policy.title), version: UI.esc(policy.version || '1.0') })}
        </p>
        ${smtpBanner}

        <div style="margin-bottom:14px;">
          <label style="font-size:12px;font-weight:600;display:block;margin-bottom:6px;">${t(`${NS}.approval.mode_label`)}</label>
          <div style="display:flex;gap:8px;">
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;
                          padding:8px 14px;border:2px solid var(--border);border-radius:8px;flex:1;
                          transition:border-color .15s;" id="mode-parallel-label">
              <input type="radio" name="appr-mode" value="parallel" checked
                     onchange="ViewIsmsDocuments._onApprModeChange(this)">
              <div>
                <div style="font-weight:600;">${t(`${NS}.approval.mode_parallel`)}</div>
                <div style="font-size:11px;color:var(--text-muted);">${t(`${NS}.approval.mode_parallel_desc`)}</div>
              </div>
            </label>
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;
                          padding:8px 14px;border:2px solid var(--border);border-radius:8px;flex:1;
                          transition:border-color .15s;" id="mode-sequential-label">
              <input type="radio" name="appr-mode" value="sequential"
                     onchange="ViewIsmsDocuments._onApprModeChange(this)">
              <div>
                <div style="font-weight:600;">${t(`${NS}.approval.mode_sequential`)}</div>
                <div style="font-size:11px;color:var(--text-muted);">${t(`${NS}.approval.mode_sequential_desc`)}</div>
              </div>
            </label>
          </div>
        </div>

        <div style="margin-bottom:12px;">
          <label style="font-size:12px;font-weight:600;display:block;margin-bottom:6px;">${t(`${NS}.approval.approvers_label`)}</label>
          <div id="approver-list"></div>
          <button onclick="ViewIsmsDocuments._addApproverRow()"
                  class="btn btn-ghost btn-sm" style="margin-top:6px;">${t(`${NS}.approval.btn_add_approver`)}</button>
          <div id="order-hint" style="display:none;font-size:11px;color:var(--text-muted);
               margin-top:8px;padding:6px 10px;background:rgba(89,0,141,.05);border-radius:5px;">
            ${t(`${NS}.approval.order_hint`)}
          </div>
        </div>

        <div style="display:flex;gap:8px;justify-content:flex-end;padding-top:12px;
                    border-top:1px solid var(--border);">
          <button onclick="UI.closeModal()" class="btn">${t(`${NS}.common.cancel`)}</button>
          <button onclick="ViewIsmsDocuments._submitApproval(${policy.id})"
                  class="btn btn-primary" ${smtpOk ? '' : 'style="opacity:.5"'}>
            ${t(`${NS}.approval.btn_submit`)}
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
      <input class="input appr-email" placeholder="${t(`${NS}.approval.placeholder_email`)}" style="flex:2;">
      <input class="input appr-name" placeholder="${t(`${NS}.approval.placeholder_name`)}" style="flex:1.5;">
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
      UI.toast(t(`${NS}.toast.approver_email_required`), 'error'); return;
    }
    try {
      await Api.approvals.create(policyId, { approvers, mode });
      UI.closeModal();
      UI.toast(t(`${NS}.toast.approval_sent`), 'success');
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
      UI.toast(t(`${NS}.toast.no_approval_rounds`), 'info'); return;
    }

    const STATUS_ICON = { pending: '⏳', approved: '✅', rejected: '❌', waiting: '⌛', cancelled: '🚫' };
    const STATUS_COLOR = {
      pending: 'var(--brand-orange)', approved: 'var(--risk-low)',
      rejected: 'var(--risk-critical)', waiting: 'var(--text-muted)', cancelled: '#aaa',
    };
    const dateLocale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';

    const reqHtml = reqs.map(r => {
      const badge = r.status === 'approved' ? '#22c55e' : r.status === 'rejected' ? '#ef4444'
                  : r.status === 'cancelled' ? '#9ca3af' : 'var(--brand-orange)';
      const modeLabel = r.mode === 'sequential' ? t(`${NS}.approval.mode_sequential`) : t(`${NS}.approval.mode_parallel`);
      const approversHtml = r.approvals.map(a => `
        <div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;
                    border-bottom:1px solid var(--border);">
          <span style="font-size:16px;flex-shrink:0;">${STATUS_ICON[a.status] || '?'}</span>
          <div style="flex:1;">
            <div style="font-size:13px;font-weight:500;">${UI.esc(a.email)}</div>
            ${a.name ? `<div style="font-size:11px;color:var(--text-muted);">${UI.esc(a.name)}</div>` : ''}
            ${r.mode === 'sequential' ? `<div style="font-size:11px;color:var(--brand-purple);">${t(`${NS}.approval_log.order_label`, { n: a.order_index })}</div>` : ''}
          </div>
          <div style="text-align:right;font-size:11px;color:var(--text-muted);">
            ${a.responded_at ? t(`${NS}.approval_log.responded_label`, { date: new Date(a.responded_at).toLocaleString(dateLocale) }) :
              a.sent_at ? t(`${NS}.approval_log.sent_label`, { date: new Date(a.sent_at).toLocaleString(dateLocale) }) : ''}
            ${a.response_notes ? `<div style="color:var(--text);margin-top:3px;font-style:italic;">"${UI.esc(a.response_notes)}"</div>` : ''}
            ${a.ip_address ? `<div style="color:#ccc;">${t(`${NS}.approval_log.ip_label`, { ip: UI.esc(a.ip_address) })}</div>` : ''}
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
              ${new Date(r.created_at).toLocaleString(dateLocale)}
            </span>
            ${r.status === 'pending' ? `
            <button onclick="ViewIsmsDocuments._cancelApproval(${policy.id},${r.id})"
                    style="border:1px solid var(--risk-critical);background:none;cursor:pointer;
                           font-size:11px;color:var(--risk-critical);border-radius:4px;padding:2px 7px;">
              ${t(`${NS}.common.cancel`)}
            </button>` : ''}
          </div>
          <div style="padding:0 14px;">${approversHtml}</div>
        </div>`;
    }).join('');

    UI.openModal(`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">${t(`${NS}.approval_log.title`)}</h3>
        <button onclick="UI.closeModal()" class="btn btn-ghost btn-sm">&#10005;</button>
      </div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:14px;">
        ${UI.esc(policy.code)} — ${UI.esc(policy.title)}
      </p>
      <div style="overflow-y:auto;max-height:60vh;">${reqHtml}</div>
    `, { width: '640px' });
  }

  async function _cancelApproval(policyId, reqId) {
    if (!confirm(t(`${NS}.toast.confirm_cancel_approval`))) return;
    try {
      await Api.approvals.cancel(policyId, reqId);
      UI.toast(t(`${NS}.toast.approval_cancelled`), 'success');
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
      UI.toast(t(`${NS}.toast.no_version_history`), 'info'); return;
    }

    const STATUS_COLOR = {
      approved: '#22c55e', published: '#0891b2', draft: '#9ca3af',
      review: 'var(--brand-orange)', obsolete: '#9ca3af',
    };
    const STATUS_LABEL = STATUS_LABELS;
    const dateLocale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';

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
                background:var(--brand-purple-4);padding:1px 6px;border-radius:3px;">${t(`${NS}.version_history.current_badge`)}</span>` : ''}
            </div>
            ${v.approved_at ? `<div style="font-size:11px;color:var(--text-muted);">
              ${t(`${NS}.version_history.approved_on`, { date: new Date(v.approved_at).toLocaleDateString(dateLocale, { day:'2-digit', month:'long', year:'numeric' }) })}
              ${v.approved_by ? t(`${NS}.version_history.approved_by_suffix`, { name: UI.esc(v.approved_by) }) : ''}</div>` :
              v.created_at ? `<div style="font-size:11px;color:var(--text-muted);">
              ${t(`${NS}.version_history.created_on`, { date: new Date(v.created_at).toLocaleDateString(dateLocale, { day:'2-digit', month:'long', year:'numeric' }) })}</div>` : ''}
          </div>
        </div>`;
    }).join('');

    UI.openModal(`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">${t(`${NS}.version_history.title`)}</h3>
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
      UI.toast(t(`${NS}.toast.hierarchy_load_error`), 'error'); return;
    }

    const DOC_LEVEL_COLOR_MAP = {
      1: 'var(--brand-purple)', 2: 'var(--brand-orange)', 3: '#0891b2', 4: '#16a34a',
    };
    const DOC_LEVEL_NAME = {
      1: t(`${NS}.level.1.short`), 2: t(`${NS}.level.2.short`), 3: t(`${NS}.level.3.short`), 4: t(`${NS}.level.4.short`),
    };

    function _hierBadge(level) {
      const c = DOC_LEVEL_COLOR_MAP[level] || '#9ca3af';
      return `<span style="padding:1px 6px;border-radius:3px;font-size:10px;font-weight:700;
                            background:${c}18;color:${c};">
                ${t(`${NS}.hierarchy.level_badge`, { level, name: DOC_LEVEL_NAME[level] || '' })}
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
      : `<span style="font-size:12px;color:var(--text-muted);">${t(`${NS}.hierarchy.no_parent`)}</span>`;

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
      : `<p style="font-size:13px;color:var(--text-muted);text-align:center;padding:20px 0;">${t(`${NS}.hierarchy.no_children`)}</p>`;

    UI.openModal(`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">${t(`${NS}.hierarchy.title`)}</h3>
        <button onclick="UI.closeModal()" class="btn btn-ghost btn-sm">&#10005;</button>
      </div>

      <div style="background:var(--bg-2);border-radius:8px;padding:12px 16px;margin-bottom:16px;">
        <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);
                    letter-spacing:.5px;margin-bottom:6px;">${t(`${NS}.hierarchy.path_title`)}</div>
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
          ${t(`${NS}.hierarchy.dependents_title`, { n: hier.children.length })}
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
        if (e.message && e.message.includes('edición por')) {
          UI.toast(t(`${NS}.toast.doc_locked`, { msg: e.message }), 'error'); return;
        }
        // Si el checkout falla por otro motivo lo ignoramos
      }
    }

    const isDraftOrReview = !policy || !['approved','published','obsolete'].includes(policy.status);
    const isExisting = !!policy;

    const extraActions = isExisting ? `
      <button class="btn btn-ghost btn-sm" id="m-versions"
              style="margin-right:auto;">${t(`${NS}.edit_lock.btn_versions`)}</button>
      <button class="btn btn-ghost btn-sm" id="m-hierarchy">${t(`${NS}.edit_lock.btn_hierarchy`)}</button>
      ${isDraftOrReview ? `<button class="btn btn-ghost btn-sm" id="m-appr-log">${t(`${NS}.edit_lock.btn_approvals`)}</button>
      <button class="btn" id="m-request-appr"
              style="background:var(--brand-orange);color:#fff;border:none;">
        ${t(`${NS}.approval.title`)}
      </button>` : `<button class="btn btn-ghost btn-sm" id="m-appr-log">${t(`${NS}.edit_lock.btn_approvals`)}</button>`}
    ` : '';

    UI.modal(
      policy ? t(`${NS}.edit_lock.modal_title_edit`, { code: policy.code }) : t(`${NS}.edit_lock.modal_title_new`),
      _formHtml(policy, extracted),
      {
        actions: `
          ${extraActions}
          <button class="btn" id="m-cancel">${t(`${NS}.common.cancel`)}</button>
          <button class="btn btn-primary" id="m-save">${t(`${NS}.common.save`)}</button>`,
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
        lockBadge.textContent = t(`${NS}.edit_lock.blocked_badge`);
        modal.prepend(lockBadge);
      }
    }
  }

  // _openFormEnhanced reemplaza a _openForm en los sitios de llamada
  // dentro del módulo; _editPolicy y _openVersioningModal llaman a _openFormEnhanced

  // --- API publica ---

  return {
    render,
    _setQueueCat, _removeFromQueue,
    _analyze, _reprocess, _deleteDoc, _deletePolicy,
    _analyzePending, _analyzeAll,
    // F0: acciones masivas y detalle de error
    _bulkClear, _bulkDelete, _bulkAnalyze, _bulkRecategorize, _showError,
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
