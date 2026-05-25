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

  let _docs = [];
  let _filter = 'all';

  // ---------- Render principal ----------

  async function render(main) {
    main.innerHTML = UI.sectionHeader(
      'Documentos del Agente IA',
      'Gestiona los documentos que alimentan el contexto del agente de seguridad.'
    ) + '<div id="aid-root"></div>';
    await _load();
    _renderRoot();
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
    const errorCount = _docs.filter(d => d.status === 'error').length;

    root.innerHTML = `
      <!-- Stats bar -->
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
          <div style="font-size:24px;font-weight:700;color:${errorCount>0?'var(--risk-critical)':'var(--text-muted)'};">
            ${errorCount}
          </div>
          <div style="font-size:12px;color:var(--text-muted);">Con error</div>
        </div>
      </div>

      <!-- Filtros + upload -->
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap;">
        <button class="btn ${_filter==='all'?'btn-primary':'btn-ghost'}"
                style="font-size:12px;" onclick="ViewAiDocuments._setFilter('all')">
          Todos (${_docs.length})
        </button>
        ${cats.map(c => {
          const n = _docs.filter(d => d.category === c).length;
          return n > 0 ? `
            <button class="btn ${_filter===c?'btn-primary':'btn-ghost'}"
                    style="font-size:12px;" onclick="ViewAiDocuments._setFilter('${c}')">
              ${CATEGORY_LABELS[c]} (${n})
            </button>` : '';
        }).join('')}
        <div style="margin-left:auto;">
          <label class="btn btn-primary" style="cursor:pointer;font-size:13px;">
            + Subir documento
            <input type="file" accept=".pdf,.docx,.txt" style="display:none;"
                   onchange="ViewAiDocuments._uploadDialog(this)">
          </label>
        </div>
      </div>

      <!-- Tabla de documentos -->
      <div class="card" style="padding:0;overflow:hidden;">
        <table class="data">
          <thead>
            <tr>
              <th>Documento</th>
              <th>Categoria</th>
              <th>Estado</th>
              <th>Fragmentos</th>
              <th>Subido por</th>
              <th>Fecha</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="aid-tbody">
            ${_renderRows()}
          </tbody>
        </table>
      </div>
      <div id="aid-upload-status" style="margin-top:8px;font-size:13px;"></div>
      <div id="aid-cat-modal" style="display:none;"></div>`;
  }

  function _renderRows() {
    const visible = _filter === 'all' ? _docs : _docs.filter(d => d.category === _filter);
    if (!visible.length) {
      return `<tr><td colspan="7" style="text-align:center;padding:24px;
        color:var(--text-muted);">Sin documentos en esta categoria.</td></tr>`;
    }
    return visible.map((d, i) => `
      <tr style="${i % 2 === 0 ? '' : 'background:var(--bg-2);'}">
        <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
            title="${UI.esc(d.original_name)}">${UI.esc(d.original_name)}</td>
        <td style="font-size:12px;">${CATEGORY_LABELS[d.category] || d.category}</td>
        <td>
          <span style="font-size:11px;font-weight:600;color:${STATUS_COLORS[d.status]||'var(--text-muted)'};">
            ${STATUS_LABELS[d.status] || d.status}
          </span>
          ${d.error_message ? `<br><span style="font-size:10px;color:var(--risk-critical);"
            title="${UI.esc(d.error_message)}">Ver error</span>` : ''}
        </td>
        <td style="text-align:right;">${d.chunk_count || 0}</td>
        <td style="font-size:12px;">${UI.esc(d.uploaded_by || '-')}</td>
        <td style="font-size:12px;">${d.created_at ? d.created_at.slice(0, 10) : '-'}</td>
        <td style="white-space:nowrap;">
          ${d.status === 'error' || d.status === 'pending' ? `
            <button class="btn btn-ghost" style="font-size:11px;padding:2px 8px;"
                    onclick="ViewAiDocuments._reprocess(${d.id})">Reprocesar</button>` : ''}
          <button class="btn btn-ghost" style="font-size:11px;padding:2px 8px;color:var(--risk-critical);"
                  onclick="ViewAiDocuments._delete(${d.id})">Eliminar</button>
        </td>
      </tr>`).join('');
  }

  // ---------- Acciones ----------

  function _setFilter(cat) {
    _filter = cat;
    _renderRoot();
  }

  function _uploadDialog(input) {
    const file = input.files[0];
    if (!file) return;
    // Pedir categoria via modal
    const cats = Object.entries(CATEGORY_LABELS);
    UI.modal('Seleccionar categoria', `
      <p style="font-size:13px;margin:0 0 12px;">
        Selecciona la categoria del documento <strong>${UI.esc(file.name)}</strong>:
      </p>
      <div style="display:flex;flex-direction:column;gap:6px;" id="cat-sel">
        ${cats.map(([v, l]) => `
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;
                 padding:8px;border-radius:6px;border:1px solid var(--border);font-size:13px;">
            <input type="radio" name="cat-pick" value="${v}">
            ${l}
          </label>`).join('')}
      </div>
    `, {
      actions: `
        <button class="btn" id="m-cancel">Cancelar</button>
        <button class="btn btn-primary" id="m-upload">Subir</button>`
    });
    document.getElementById('m-cancel').onclick = () => { UI.closeModal(); input.value = ''; };
    document.getElementById('m-upload').onclick = async () => {
      const sel = document.querySelector('input[name="cat-pick"]:checked');
      if (!sel) { UI.toast('Selecciona una categoria', 'error'); return; }
      UI.closeModal();
      await _doUpload(file, sel.value);
      input.value = '';
    };
  }

  async function _doUpload(file, category) {
    const statusEl = document.getElementById('aid-upload-status');
    if (statusEl) statusEl.innerHTML = `<span style="color:var(--brand-orange);">
      Subiendo ${UI.esc(file.name)}...</span>`;
    try {
      await Api.aiDocuments.upload(file, category);
      await _load();
      _renderRoot();
      UI.toast('Documento subido e indexado', 'success');
    } catch (e) {
      if (statusEl) statusEl.innerHTML = `<span style="color:var(--risk-critical);">
        Error: ${UI.esc(e.message)}</span>`;
      UI.toast('Error: ' + e.message, 'error');
    }
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

  return { render, _setFilter, _uploadDialog, _reprocess, _delete };

})();
