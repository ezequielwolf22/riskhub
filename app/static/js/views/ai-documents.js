/* views/ai-documents.js - Biblioteca de documentos del Agente IA. */

const ViewAiDocuments = (() => {

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

  const STATUS_LABELS = {
    indexed:    'Indexado',
    processing: 'Procesando',
    pending:    'Pendiente',
    error:      'Error',
  };

  const STATUS_COLORS = {
    indexed:    'var(--risk-low)',
    processing: 'var(--brand-orange)',
    pending:    'var(--text-muted)',
    error:      'var(--risk-critical)',
  };

  // ISMS analysis status (v1.7.4)
  const ISMS_LABELS = {
    analysing: 'Analizando...',
    analysed:  'Analizado',
    skipped:   'Sin IA',
    error:     'Error IA',
  };
  const ISMS_COLORS = {
    analysing: 'var(--brand-orange)',
    analysed:  'var(--risk-low)',
    skipped:   'var(--text-muted)',
    error:     'var(--risk-critical)',
  };
  // Intervalo de polling para documentos en estado "analysing"
  let _pollTimer = null;

  const ACCEPTED_EXTS = ['pdf', 'docx', 'txt', 'csv', 'jpg', 'jpeg', 'png'];

  let _docs    = [];
  let _filter  = 'all';
  // Cola de subida: [{id, file, category, status, error}]
  // status: 'pending' | 'uploading' | 'done' | 'error'
  let _queue   = [];
  let _queueId = 0;
  let _uploading = false;

  // ---------- Render principal ----------

  async function render(main) {
    // Limpiar timer anterior si el usuario navega fuera y vuelve
    _stopPoll();
    main.innerHTML = UI.sectionHeader(
      'Documentos del Agente IA',
      'Gestiona los documentos que alimentan el contexto del agente de seguridad.'
    ) + '<div id="aid-root"></div>';
    await _load();
    _renderRoot();
    _startPollIfNeeded();
    // Mostrar banner si ya hay errores de creditos al entrar
    const hasCredit = _docs.some(d =>
      d.isms_status === 'error' &&
      (d.isms_summary_text || '').toLowerCase().includes('credito')
    );
    if (hasCredit) _showCreditBanner();
  }

  function _startPollIfNeeded() {
    _stopPoll();
    const analysing = _docs.filter(d => d.isms_status === 'analysing');
    if (analysing.length === 0) return;
    _pollTimer = setInterval(async () => {
      await _load();
      const tbody = document.getElementById('aid-tbody');
      if (tbody) tbody.innerHTML = _renderRows();
      _updateStats();
      if (!_docs.some(d => d.isms_status === 'analysing')) {
        _stopPoll();
        // Detectar errores de creditos al terminar
        const creditErrors = _docs.filter(d =>
          d.isms_status === 'error' &&
          (d.isms_summary_text || '').toLowerCase().includes('credito')
        );
        if (creditErrors.length > 0) _showCreditBanner();
      }
    }, 4000);
  }

  function _showCreditBanner() {
    const existing = document.getElementById('aid-credit-banner');
    if (existing) return;
    const banner = document.createElement('div');
    banner.id = 'aid-credit-banner';
    banner.style.cssText = `
      background:#FEF3C7;border:1px solid #F59E0B;border-radius:8px;
      padding:12px 16px;margin-bottom:16px;display:flex;align-items:center;gap:10px;
      font-size:13px;color:#92400E;
    `;
    banner.innerHTML = `
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" style="flex-shrink:0;">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      <span>
        <strong>Sin creditos Anthropic:</strong> el analisis de documentos se ha detenido.
        Recarga creditos en
        <a href="https://console.anthropic.com/settings/billing" target="_blank"
           style="color:#92400E;font-weight:700;">console.anthropic.com/settings/billing</a>
        y luego pulsa <em>Analizar pendientes</em>.
      </span>
      <button onclick="this.parentElement.remove()"
              style="margin-left:auto;background:none;border:none;cursor:pointer;
                     font-size:16px;color:#92400E;padding:0 4px;">&times;</button>
    `;
    const root = document.getElementById('aid-root');
    root?.insertBefore(banner, root.firstChild);
  }

  function _stopPoll() {
    if (_pollTimer !== null) { clearInterval(_pollTimer); _pollTimer = null; }
  }

  async function _load() {
    try {
      _docs = await Api.aiDocuments.list();
    } catch (_) {
      _docs = [];
    }
  }

  function _renderRoot() {
    const root = document.getElementById('aid-root');
    if (!root) return;

    const cats = Object.keys(CATEGORY_LABELS);
    const indexedCount = _docs.filter(d => d.status === 'indexed').length;
    const errorCount   = _docs.filter(d => d.status === 'error').length;

    root.innerHTML = `
      <!-- Stats -->
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;">
        <div class="card" style="text-align:center;padding:14px;">
          <div style="font-size:24px;font-weight:700;color:var(--brand-purple);">${_docs.length}</div>
          <div style="font-size:12px;color:var(--text-muted);">Total documentos</div>
        </div>
        <div class="card" style="text-align:center;padding:14px;">
          <div style="font-size:24px;font-weight:700;color:var(--risk-low);">${indexedCount}</div>
          <div style="font-size:12px;color:var(--text-muted);">Indexados</div>
        </div>
        <div class="card" style="text-align:center;padding:14px;">
          <div style="font-size:24px;font-weight:700;color:var(--brand-orange);">
            ${_docs.reduce((s, d) => s + (d.chunk_count || 0), 0)}
          </div>
          <div style="font-size:12px;color:var(--text-muted);">Fragmentos totales</div>
        </div>
        <div class="card" style="text-align:center;padding:14px;">
          <div style="font-size:24px;font-weight:700;
               color:${errorCount > 0 ? 'var(--risk-critical)' : 'var(--text-muted)'};">
            ${errorCount}
          </div>
          <div style="font-size:12px;color:var(--text-muted);">Con error</div>
        </div>
      </div>

      <!-- Filtros + botones de accion -->
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap;">
        <button class="btn ${_filter === 'all' ? 'btn-primary' : 'btn-ghost'}"
                style="font-size:12px;" onclick="ViewAiDocuments._setFilter('all')">
          Todos (${_docs.length})
        </button>
        ${cats.map(c => {
          const n = _docs.filter(d => d.category === c).length;
          return n > 0 ? `
            <button class="btn ${_filter === c ? 'btn-primary' : 'btn-ghost'}"
                    style="font-size:12px;" onclick="ViewAiDocuments._setFilter('${c}')">
              ${CATEGORY_LABELS[c]} (${n})
            </button>` : '';
        }).join('')}
        <div style="margin-left:auto;display:flex;gap:8px;align-items:center;">
          ${indexedCount > 0 ? `
          <button class="btn btn-ghost" id="aid-analyze-pending-btn"
                  style="font-size:12px;" onclick="ViewAiDocuments._analyzePending()"
                  title="Analiza documentos sin analizar y resetea los atascados. No toca los ya analizados.">
            Analizar pendientes
          </button>
          <button class="btn btn-ghost" id="aid-analyze-all-btn"
                  style="font-size:12px;" onclick="ViewAiDocuments._analyzeAll()"
                  title="Re-analizar TODOS los documentos indexados (incluye ya analizados)">
            Re-analizar todos (${indexedCount})
          </button>
` : ''}
          <label class="btn btn-primary" style="cursor:pointer;font-size:13px;"
                 title="Selecciona uno o varios archivos (PDF, DOCX, TXT, CSV, JPG, PNG)">
            + Subir documentos
            <input type="file" id="aid-file-input"
                   accept=".pdf,.docx,.txt,.csv,.jpg,.jpeg,.png" multiple style="display:none;">
          </label>
        </div>
      </div>

      <!-- Zona de arrastre -->
      <div id="aid-dropzone"
           style="border:2px dashed var(--border);border-radius:10px;
                  padding:28px 20px;text-align:center;margin-bottom:16px;
                  cursor:pointer;transition:all .15s;color:var(--text-muted);font-size:13px;">
        <div style="margin-bottom:6px;">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"
               style="display:inline-block;vertical-align:middle;opacity:.5;">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
        </div>
        Arrastra aqui uno o varios documentos (PDF, DOCX, TXT, CSV, JPG, PNG)<br>
        <span style="font-size:11px;">o usa el boton &ldquo;Subir documentos&rdquo;</span>
      </div>

      <!-- Cola de subida (se rellena dinamicamente) -->
      <div id="aid-queue"></div>

      <!-- Tabla de documentos existentes -->
      <div class="card" style="padding:0;overflow:hidden;">
        <table class="data">
          <thead>
            <tr>
              <th>Documento</th>
              <th>Categoria</th>
              <th>Estado indexado</th>
              <th>Analisis ISMS</th>
              <th>Resultado</th>
              <th>Fragmentos</th>
              <th>Fecha</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="aid-tbody">
            ${_renderRows()}
          </tbody>
        </table>
      </div>
      <div id="aid-cat-modal" style="display:none;"></div>`;

    _attachListeners();
    _renderQueue();
  }

  // ---------- Event listeners (re-adjuntar tras cada renderRoot) ----------

  function _attachListeners() {
    // Input multi-archivo
    const fileInput = document.getElementById('aid-file-input');
    if (fileInput) {
      fileInput.onchange = (e) => {
        _addFilesToQueue(Array.from(e.target.files));
        e.target.value = '';   // reset para permitir re-seleccionar los mismos archivos
      };
    }

    // Zona de arrastre
    const dz = document.getElementById('aid-dropzone');
    if (!dz) return;

    // Click en la zona abre el selector de archivos
    dz.onclick = () => document.getElementById('aid-file-input')?.click();

    dz.addEventListener('dragover', (e) => {
      e.preventDefault();
      dz.style.borderColor   = 'var(--brand-purple)';
      dz.style.background    = 'var(--brand-purple-4)';
      dz.style.color         = 'var(--brand-purple)';
    });

    dz.addEventListener('dragleave', (e) => {
      // Solo resetear si el cursor sale realmente de la zona
      if (!dz.contains(e.relatedTarget)) {
        _resetDropzone(dz);
      }
    });

    dz.addEventListener('drop', (e) => {
      e.preventDefault();
      _resetDropzone(dz);
      const files = Array.from(e.dataTransfer.files);
      _addFilesToQueue(files);
    });
  }

  function _resetDropzone(dz) {
    dz.style.borderColor = '';
    dz.style.background  = '';
    dz.style.color       = '';
  }

  // ---------- Cola de subida ----------

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
        UI.toast(`${file.name}: formato no soportado. Solo PDF, DOCX, TXT, CSV.`, 'error');
        continue;
      }
      // Evitar duplicados pendientes por nombre
      const alreadyPending = _queue.some(q => q.file.name === file.name && q.status === 'pending');
      if (alreadyPending) continue;
      const guessedCat = _guessCategoryFromName(file.name);
      _queue.push({ id: ++_queueId, file, category: guessedCat, status: 'pending', error: null });
      added++;
    }
    if (added > 0) _renderQueue();
  }

  function _renderQueue() {
    const container = document.getElementById('aid-queue');
    if (!container) return;

    const pending  = _queue.filter(q => q.status === 'pending');
    const active   = _queue.filter(q => q.status !== 'pending');

    if (_queue.length === 0) {
      container.innerHTML = '';
      return;
    }

    const catOptions = Object.entries(CATEGORY_LABELS)
      .map(([v, l]) => `<option value="${v}">${l}</option>`).join('');

    container.innerHTML = `
      <div class="card" style="margin-bottom:16px;padding:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <strong style="font-size:14px;">
            Cola de subida
            <span style="font-weight:400;font-size:12px;color:var(--text-muted);">
              — ${_queue.length} archivo${_queue.length !== 1 ? 's' : ''}
            </span>
          </strong>
          ${pending.length > 0 && !_uploading ? `
            <div style="display:flex;gap:8px;">
              <button class="btn btn-ghost" style="font-size:12px;" id="aid-clear-queue">
                Limpiar pendientes
              </button>
              <button class="btn btn-primary" style="font-size:12px;" id="aid-upload-all">
                Subir ${pending.length} documento${pending.length !== 1 ? 's' : ''}
              </button>
            </div>` : ''}
        </div>

        <div style="display:flex;flex-direction:column;gap:6px;" id="aid-queue-list">
          ${_queue.map(item => {
            const isProcessing = item.status === 'uploading';
            const isDone       = item.status === 'done';
            const isError      = item.status === 'error';
            const isPending    = item.status === 'pending';

            const statusIcon = isDone
              ? `<span style="color:var(--risk-low);font-size:13px;">&#10003; Subido</span>`
              : isError
              ? `<span style="color:var(--risk-critical);font-size:12px;" title="${UI.esc(item.error || '')}">&#10007; Error</span>`
              : isProcessing
              ? `<span style="color:var(--brand-orange);font-size:12px;">Subiendo...</span>`
              : '';

            const ext = item.file.name.split('.').pop().toUpperCase();
            const size = item.file.size < 1024 * 1024
              ? (item.file.size / 1024).toFixed(0) + ' KB'
              : (item.file.size / 1024 / 1024).toFixed(1) + ' MB';

            return `
              <div style="display:flex;align-items:center;gap:10px;padding:8px 10px;
                          border-radius:6px;background:var(--bg-2);
                          border:1px solid ${isError ? 'var(--risk-critical)' : isDone ? 'var(--risk-low)' : 'var(--border)'};
                          opacity:${isDone ? '.65' : '1'};">
                <span style="font-size:10px;font-weight:700;background:var(--brand-purple-4);
                             color:var(--brand-purple);border-radius:3px;padding:1px 5px;
                             flex-shrink:0;">${ext}</span>
                <span style="flex:1;font-size:12px;overflow:hidden;text-overflow:ellipsis;
                             white-space:nowrap;" title="${UI.esc(item.file.name)}">
                  ${UI.esc(item.file.name)}
                </span>
                <span style="font-size:11px;color:var(--text-subtle);flex-shrink:0;">${size}</span>
                ${isPending ? `
                  <select class="input" style="font-size:11px;padding:3px 6px;height:auto;
                                               min-width:180px;flex-shrink:0;"
                          title="El agente IA reclasificara automaticamente tras analizar el contenido"
                          data-qid="${item.id}" onchange="ViewAiDocuments._setQueueCat(${item.id}, this.value)">
                    <option value="other" ${item.category === 'other' ? 'selected' : ''}>Auto (IA detecta categoria)</option>
                    ${Object.entries(CATEGORY_LABELS).filter(([v]) => v !== 'other').map(([v, l]) =>
                      `<option value="${v}" ${item.category === v ? 'selected' : ''}>${l}</option>`
                    ).join('')}
                    <option value="other" ${item.category === 'other' ? '' : ''}>Otros</option>
                  </select>
                  <button class="btn btn-ghost"
                          style="font-size:11px;padding:2px 8px;color:var(--risk-critical);flex-shrink:0;"
                          onclick="ViewAiDocuments._removeFromQueue(${item.id})">&#10005;</button>
                ` : `
                  <span style="font-size:11px;color:var(--text-muted);flex-shrink:0;min-width:160px;">
                    ${CATEGORY_LABELS[item.category] || item.category}
                  </span>
                  <span style="min-width:80px;text-align:right;flex-shrink:0;">${statusIcon}</span>
                `}
              </div>`;
          }).join('')}
        </div>

        ${!_uploading && active.length > 0 ? `
          <div style="margin-top:10px;text-align:right;">
            <button class="btn btn-ghost" style="font-size:12px;" id="aid-dismiss-done">
              Limpiar completados
            </button>
          </div>` : ''}
      </div>`;

    // Botones
    const btnUpload = document.getElementById('aid-upload-all');
    if (btnUpload) btnUpload.onclick = _startUploadAll;

    const btnClear = document.getElementById('aid-clear-queue');
    if (btnClear) btnClear.onclick = () => {
      _queue = _queue.filter(q => q.status !== 'pending');
      _renderQueue();
    };

    const btnDismiss = document.getElementById('aid-dismiss-done');
    if (btnDismiss) btnDismiss.onclick = () => {
      _queue = _queue.filter(q => q.status !== 'done');
      _renderQueue();
    };
  }

  function _setQueueCat(id, value) {
    const item = _queue.find(q => q.id === id);
    if (item) item.category = value;
  }

  function _removeFromQueue(id) {
    _queue = _queue.filter(q => q.id !== id);
    _renderQueue();
  }

  // ---------- Subida batch ----------

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
        item.status = 'done';
        ok++;
      } catch (e) {
        item.status = 'error';
        item.error  = e.message || 'Error desconocido';
        fail++;
      }
      _renderQueue();
    }

    _uploading = false;
    // Recargar lista de documentos una sola vez al acabar
    await _load();
    const tbody = document.getElementById('aid-tbody');
    if (tbody) tbody.innerHTML = _renderRows();
    // Actualizar stats y filtros sin perder la cola
    _updateStats();

    if (ok > 0 && fail === 0) {
      UI.toast(`${ok} documento${ok !== 1 ? 's' : ''} subido${ok !== 1 ? 's' : ''} correctamente — analisis ISMS iniciado`, 'success');
    } else if (ok > 0 && fail > 0) {
      UI.toast(`${ok} subidos, ${fail} con error`, 'error');
    } else {
      UI.toast('Error al subir los documentos', 'error');
    }
    _renderQueue();
    // Iniciar polling si hay documentos en analisis ISMS
    _startPollIfNeeded();
  }

  // Actualizar solo los contadores del stats bar sin reconstruir todo
  function _updateStats() {
    const indexedCount = _docs.filter(d => d.status === 'indexed').length;
    const errorCount   = _docs.filter(d => d.status === 'error').length;
    const totalFrags   = _docs.reduce((s, d) => s + (d.chunk_count || 0), 0);

    const chips = document.querySelectorAll('#aid-root .card > div:first-child');
    // Stats chips: total, indexed, fragments, errors
    const statValues = [_docs.length, indexedCount, totalFrags, errorCount];
    document.querySelectorAll('#aid-root .card[style*="text-align:center"] div:first-child').forEach((el, i) => {
      if (statValues[i] !== undefined) el.textContent = statValues[i];
    });

    // Actualizar filtros de categoria
    const filterBar = document.querySelector('#aid-root > div:nth-child(2)');
    if (filterBar) {
      const cats = Object.keys(CATEGORY_LABELS);
      cats.forEach(c => {
        const n = _docs.filter(d => d.category === c).length;
        const btn = filterBar.querySelector(`button[onclick*="_setFilter('${c}')"]`);
        if (btn) btn.textContent = `${CATEGORY_LABELS[c]} (${n})`;
        else if (n > 0) {
          // El filtro no existia antes — reconstruir root completo
          _renderRoot();
          return;
        }
      });
    }
  }

  // ---------- Tabla de documentos ----------

  function _ismsResultCell(d) {
    if (!d.isms_status || d.isms_status === 'analysing') return '<td>-</td>';
    const parts = [];
    if (d.isms_policy_id) {
      parts.push(`<a href="#/policies" style="font-size:11px;color:var(--brand-purple);">
        Politica creada</a>`);
    }
    if (d.isms_controls_updated > 0) {
      const madurezLink = d.isms_status === 'analysed'
        ? `&nbsp;<span onclick="ViewAiDocuments._showMaturityModal(${d.id})"
              style="cursor:pointer;font-size:11px;color:var(--brand-purple);text-decoration:underline;"
              title="Ver nivel de madurez y gap analysis por control">Ver madurez</span>`
        : '';
      parts.push(`<span>
        <a href="#/controls" style="font-size:11px;color:var(--risk-low);"
           title="Ver controles actualizados por este documento">
          ${d.isms_controls_updated} control${d.isms_controls_updated !== 1 ? 'es' : ''} actualizados
        </a>${madurezLink}
      </span>`);
    }
    if (d.isms_tasks_created > 0) {
      parts.push(`<a href="#/tasks" style="font-size:11px;color:var(--brand-orange);">
        ${d.isms_tasks_created} tarea${d.isms_tasks_created !== 1 ? 's' : ''}</a>`);
    }
    const tooltip = d.isms_summary_text ? UI.esc(d.isms_summary_text.slice(0, 300)) : '';

    // Clausulas ISO extraidas por IA (v2.2)
    const clauses = Array.isArray(d.extracted_clauses) ? d.extracted_clauses : [];
    if (clauses.length > 0) {
      parts.push(`<span style="cursor:pointer;font-size:11px;color:var(--brand-purple);"
        onclick="ViewAiDocuments._showClauses(${d.id})" title="Ver clausulas ISO extraidas">
        ${clauses.length} clausula${clauses.length !== 1 ? 's' : ''} ISO</span>`);
    }

    return `<td style="font-size:11px;line-height:1.7;" title="${tooltip}">
      ${parts.length ? parts.join('<br>') : '<span style="color:var(--text-muted);">Sin resultados</span>'}
      ${tooltip ? `<div style="font-size:10px;color:var(--text-subtle);margin-top:2px;max-width:220px;
                               overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
                       title="${tooltip}">${tooltip}</div>` : ''}
    </td>`;
  }

  // ---------- Helpers de madurez ----------

  function _parseGapNotes(notes) {
    if (!notes) return { rationale: '', gap: '' };
    const gapSep = '\n\nPara llegar a nivel 5: ';
    const gapIdx = notes.indexOf(gapSep);
    let rationale = notes;
    let gap = '';
    if (gapIdx >= 0) {
      rationale = notes.slice(0, gapIdx);
      gap = notes.slice(gapIdx + gapSep.length);
    }
    rationale = rationale.replace(/^Nivel actual \(\d+\/5\): /, '');
    return { rationale, gap };
  }

  const _MATURITY_LABELS = ['Inexistente', 'Inicial', 'Basico', 'Definido', 'Gestionado', 'Optimizado'];

  function _maturityColor(v) {
    if (v >= 5) return 'var(--risk-low)';
    if (v >= 4) return '#22c55e';
    if (v >= 3) return 'var(--risk-medium)';
    if (v >= 2) return 'var(--risk-high)';
    return 'var(--risk-critical)';
  }

  function _maturityBarLarge(v) {
    const color = _maturityColor(v);
    const bars = Array.from({length: 5}, (_, i) =>
      `<div style="width:20px;height:12px;border-radius:3px;background:${i < v ? color : 'var(--bg-3)'};"></div>`
    ).join('');
    return `<div style="display:flex;gap:4px;align-items:center;">
      ${bars}
      <span style="font-size:13px;font-weight:800;color:${color};margin-left:8px;">${v}/5</span>
      <span style="font-size:12px;color:var(--text-muted);margin-left:4px;">${_MATURITY_LABELS[v] || ''}</span>
    </div>`;
  }

  async function _showMaturityModal(docId) {
    const doc = _docs.find(d => d.id === docId);
    let controls = [];
    try {
      controls = await Api.aiDocuments.controls(docId);
    } catch (e) {
      UI.toast('Error cargando datos de madurez: ' + e.message, 'error');
      return;
    }

    if (!controls.length) {
      UI.toast('No se encontraron controles vinculados a este documento. Re-analiza para generar el gap analysis.', 'info');
      return;
    }

    const avgMaturity = controls.reduce((s, c) => s + (c.maturity || 0), 0) / controls.length;
    const avgColor = _maturityColor(Math.round(avgMaturity));

    const rows = controls.map(c => {
      const { rationale, gap } = _parseGapNotes(c.notes);
      const color = _maturityColor(c.maturity || 0);
      const hasAnalysis = rationale || gap;
      return `
        <div style="border:1px solid var(--border);border-radius:8px;padding:14px;margin-bottom:12px;">
          <div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:10px;flex-wrap:wrap;">
            <span style="font-size:11px;font-weight:700;background:var(--brand-purple-4);
                         color:var(--brand-purple);border-radius:3px;padding:2px 7px;white-space:nowrap;
                         flex-shrink:0;">${UI.esc(c.control_code || '-')}</span>
            <span style="font-size:13px;font-weight:600;flex:1;">${UI.esc(c.control_name || '-')}</span>
          </div>
          <div style="margin-bottom:${hasAnalysis ? '12px' : '0'};">${_maturityBarLarge(c.maturity || 0)}</div>
          ${rationale ? `
            <div style="margin-bottom:8px;">
              <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);
                          letter-spacing:.5px;margin-bottom:5px;">Justificacion del nivel actual</div>
              <div style="font-size:12px;line-height:1.65;color:var(--text-base);background:var(--bg-2);
                          border-radius:6px;padding:8px 12px;border-left:3px solid ${color};">
                ${UI.esc(rationale)}
              </div>
            </div>` : ''}
          ${gap ? `
            <div>
              <div style="font-size:10px;font-weight:700;text-transform:uppercase;color:var(--text-muted);
                          letter-spacing:.5px;margin-bottom:5px;">Para llegar a nivel 5 (Optimizado)</div>
              <div style="font-size:12px;line-height:1.65;color:var(--text-base);
                          background:rgba(89,0,141,.05);border-radius:6px;padding:8px 12px;
                          border-left:3px solid var(--brand-purple);">
                ${UI.esc(gap)}
              </div>
            </div>` : (!hasAnalysis ? `
            <div style="font-size:11px;color:var(--text-muted);font-style:italic;margin-top:4px;">
              Sin analisis de gap disponible para este control. Re-analiza el documento para generarlo.
            </div>` : '')}
        </div>`;
    }).join('');

    UI.openModal(`
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">Analisis de madurez por control</h3>
        <button class="btn btn-ghost btn-sm" onclick="UI.closeModal()">&#10005;</button>
      </div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">
        Documento: <strong>${UI.esc(doc?.original_name || '')}</strong>
      </p>
      <div style="background:var(--bg-2);border-radius:8px;padding:12px 16px;margin-bottom:16px;
                  display:flex;align-items:center;gap:14px;">
        <div style="font-size:28px;font-weight:800;color:${avgColor};">${avgMaturity.toFixed(1)}</div>
        <div>
          <div style="font-size:13px;font-weight:600;color:var(--text-base);">Madurez promedio del documento</div>
          <div style="font-size:11px;color:var(--text-muted);">
            Calculada sobre ${controls.length} control${controls.length !== 1 ? 'es' : ''} identificados
            &nbsp;&middot;&nbsp;
            <a href="#/controls" onclick="UI.closeModal();" style="color:var(--brand-purple);">Ver todos los controles</a>
          </div>
        </div>
      </div>
      <div style="overflow-y:auto;max-height:62vh;">
        ${rows}
      </div>
    `, { width: '700px' });
  }

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
          ${c.control_id
            ? `<a href="#/controls" style="font-size:11px;color:var(--risk-low);">Control #${c.control_id}</a>`
            : `<span style="font-size:11px;color:var(--text-muted);">-</span>`}
        </td>
        <td style="padding:8px 12px;text-align:center;font-size:11px;color:${c.confidence >= 0.8 ? 'var(--risk-low)' : 'var(--brand-orange)'};">
          ${Math.round((c.confidence || 0) * 100)}%
        </td>
      </tr>
    `).join('');

    UI.openModal(`
      <div class="modal-head" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <h3 style="margin:0;font-size:15px;color:var(--brand-purple);">Clausulas ISO extraidas</h3>
        <button class="btn btn-ghost btn-sm" onclick="UI.closeModal()">x</button>
      </div>
      <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">
        Documento: <strong>${UI.esc(doc.original_name)}</strong>
      </p>
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

  function _renderRows() {
    const visible = _filter === 'all' ? _docs : _docs.filter(d => d.category === _filter);
    if (!visible.length) {
      return `<tr><td colspan="8" style="text-align:center;padding:24px;
        color:var(--text-muted);">Sin documentos en esta categoria.</td></tr>`;
    }
    return visible.map((d, i) => {
      const ismsColor = ISMS_COLORS[d.isms_status] || 'var(--text-muted)';
      const ismsLabel = ISMS_LABELS[d.isms_status] || (d.status === 'indexed' ? 'Pendiente' : '-');
      const ismsTooltip = d.isms_status === 'error' && d.isms_summary_text
        ? ` title="${UI.esc(d.isms_summary_text)}"` : '';
      return `
      <tr style="${i % 2 === 0 ? '' : 'background:var(--bg-2);'}">
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
            title="${UI.esc(d.original_name)}">${UI.esc(d.original_name)}</td>
        <td style="font-size:12px;">
          ${CATEGORY_LABELS[d.category] || d.category}
          ${d.auto_categorized ? `<span style="display:inline-block;margin-left:4px;font-size:9px;
            background:var(--brand-purple-4);color:var(--brand-purple);
            border-radius:4px;padding:1px 5px;vertical-align:middle;"
            title="Categoria detectada automaticamente por el agente IA">IA</span>` : ''}
        </td>
        <td>
          <span style="font-size:11px;font-weight:600;
                       color:${STATUS_COLORS[d.status] || 'var(--text-muted)'};">
            ${STATUS_LABELS[d.status] || d.status}
          </span>
          ${d.error_message ? `<br><span style="font-size:10px;color:var(--risk-critical);"
            title="${UI.esc(d.error_message)}">Ver error</span>` : ''}
        </td>
        <td>
          <span style="font-size:11px;font-weight:600;color:${ismsColor};"${ismsTooltip}>
            ${ismsLabel}
          </span>
          ${d.isms_status === 'analysing'
            ? `<span style="font-size:10px;color:var(--text-muted);margin-left:4px;">&#8635;</span>`
            : ''}
        </td>
        ${_ismsResultCell(d)}
        <td style="text-align:right;">${d.chunk_count || 0}</td>
        <td style="font-size:12px;">${d.created_at ? d.created_at.slice(0, 10) : '-'}</td>
        <td style="white-space:nowrap;">
          ${d.status === 'indexed' && (!d.isms_status || d.isms_status === 'error' || d.isms_status === 'skipped' || d.isms_status === 'analysing') ? `
            <button class="btn btn-ghost" style="font-size:11px;padding:2px 8px;"
                    onclick="ViewAiDocuments._analyze(${d.id})">${d.isms_status === 'analysing' ? 'Reintentar analisis' : 'Analizar'}</button>` : ''}
          ${d.status === 'error' || d.status === 'pending' ? `
            <button class="btn btn-ghost" style="font-size:11px;padding:2px 8px;"
                    onclick="ViewAiDocuments._reprocess(${d.id})">Reprocesar</button>` : ''}
          <button class="btn btn-ghost"
                  style="font-size:11px;padding:2px 8px;color:var(--risk-critical);"
                  onclick="ViewAiDocuments._delete(${d.id})">Eliminar</button>
        </td>
      </tr>`;
    }).join('');
  }

  // ---------- Acciones ----------

  function _setFilter(cat) {
    _filter = cat;
    _renderRoot();
  }

  async function _reprocess(id) {
    try {
      await Api.aiDocuments.reprocess(id);
      await _load();
      _renderRoot();
      UI.toast('Documento reprocesado', 'success');
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _delete(id) {
    if (!confirm('Eliminar este documento del indice de contexto?')) return;
    try {
      await Api.aiDocuments.del(id);
      await _load();
      _renderRoot();
      UI.toast('Documento eliminado', 'success');
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  async function _analyze(id) {
    try {
      await Api.aiDocuments.analyze(id);
      // Actualizar solo la fila de estado mientras se analiza en background
      await _load();
      const tbody = document.getElementById('aid-tbody');
      if (tbody) tbody.innerHTML = _renderRows();
      UI.toast('Analisis ISMS iniciado', 'success');
      _startPollIfNeeded();
    } catch (e) {
      UI.toast('Error al iniciar analisis: ' + e.message, 'error');
    }
  }

  async function _analyzePending() {
    const btn = document.getElementById('aid-analyze-pending-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Iniciando...'; }
    try {
      const res = await Api.aiDocuments.analyzePending();
      await _load();
      const tbody = document.getElementById('aid-tbody');
      if (tbody) tbody.innerHTML = _renderRows();
      const msg = res.stuck_reset > 0
        ? `${res.stuck_reset} atascados reseteados. ${res.queued} documentos en cola.`
        : (res.queued > 0 ? `${res.queued} documentos pendientes en cola.` : 'No hay documentos pendientes.');
      UI.toast(msg, 'success');
      _startPollIfNeeded();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Analizar pendientes'; }
    }
  }

  async function _analyzeAll() {
    const btn = document.getElementById('aid-analyze-all-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Iniciando...'; }
    try {
      const res = await Api.aiDocuments.analyzeAll();
      await _load();
      const tbody = document.getElementById('aid-tbody');
      if (tbody) tbody.innerHTML = _renderRows();
      UI.toast(res.message || `Analisis iniciado para ${res.queued} documentos`, 'success');
      _startPollIfNeeded();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = `Re-analizar todos`; }
    }
  }

  return { render, _setFilter, _setQueueCat, _removeFromQueue, _reprocess, _delete, _analyze, _analyzeAll, _analyzePending, _showClauses, _showMaturityModal };

})();
