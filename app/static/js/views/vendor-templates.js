/* Vista de plantillas de cuestionario TPRM — editables por el cliente.
   Lista plantillas del sistema (clonables) y personalizadas (editar/eliminar)
   con un editor de preguntas (texto, tipo, peso, evidencia, dominio). */
const ViewVendorTemplates = (() => {

  const TYPE_LABELS = {
    yes_no: 'Si / No',
    yes_no_partial: 'Si / Parcial / No',
    scale_1_5: 'Escala 1-5',
    single_choice: 'Opcion unica',
    text_long: 'Texto libre',
  };

  const DOMAINS = [
    'governance', 'risk_management', 'asset_management', 'access_control',
    'cryptography', 'physical_security', 'operations_security', 'network_security',
    'secure_development', 'supplier_chain', 'incident_management', 'business_continuity',
    'compliance_legal', 'privacy', 'ai_governance', 'resilience_testing',
  ];

  // Reglas de scoring derivadas del tipo (deterministas)
  function _rulesForType(type) {
    if (type === 'yes_no') return { yes: 100, no: 0, na: null };
    if (type === 'yes_no_partial') return { yes: 100, partial: 50, no: 0, na: null };
    if (type === 'scale_1_5') return { '1': 0, '2': 25, '3': 50, '4': 75, '5': 100 };
    return null; // text_long / single_choice editados: sin reglas automaticas
  }

  let _editQuestions = [];   // estado del editor en memoria
  let _editId = null;        // id de la plantilla custom en edicion (null = nueva)

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Plantillas de cuestionario</h1>
          <p class="page-sub">Clona y edita los cuestionarios de evaluacion de proveedores. Preguntas representativas, no exhaustivas.</p>
        </div>
        ${Auth.canEdit() ? '<button class="btn btn-primary" id="btn-new-tpl">+ Nueva plantilla</button>' : ''}
      </div>
      <div class="card" style="margin-bottom:16px;">
        <h3 style="margin-top:0;">Plantillas del sistema</h3>
        <p style="font-size:12px;color:var(--text-muted);margin-top:0;">De solo lectura. Usa "Clonar" para crear una copia editable.</p>
        <div id="tpl-system">Cargando...</div>
      </div>
      <div class="card">
        <h3 style="margin-top:0;">Plantillas personalizadas</h3>
        <div id="tpl-custom">Cargando...</div>
      </div>
    `;
    const nb = document.getElementById('btn-new-tpl');
    if (nb) nb.onclick = () => _openEditor(null);
    await _loadSystem();
    await _loadCustom();
  }

  async function _loadSystem() {
    const wrap = document.getElementById('tpl-system');
    try {
      const data = await Api.tprm.templates();
      wrap.innerHTML = `<table class="data"><thead><tr>
        <th>Nombre</th><th>Marcos</th><th>Preguntas</th><th></th></tr></thead><tbody>
        ${data.map(t => `<tr>
          <td><strong>${UI.esc(t.name)}</strong><br><span style="font-size:11px;color:var(--text-muted);">${UI.esc(t.description || '')}</span></td>
          <td style="font-size:11px;">${(t.framework_codes || []).map(UI.esc).join(', ')}</td>
          <td>${t.question_count}</td>
          <td>${Auth.canEdit() ? `<button class="btn btn-sm" data-code="${UI.esc(t.code)}" data-act="clone">Clonar</button>` : ''}</td>
        </tr>`).join('')}
      </tbody></table>`;
      wrap.querySelectorAll('[data-act="clone"]').forEach(b => {
        b.onclick = () => _clone(b.dataset.code);
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  async function _loadCustom() {
    const wrap = document.getElementById('tpl-custom');
    try {
      const data = await Api.tprm.customTemplates();
      if (!data.length) {
        wrap.innerHTML = '<p class="text-muted">No hay plantillas personalizadas. Clona una del sistema o crea una nueva.</p>';
        return;
      }
      wrap.innerHTML = `<table class="data"><thead><tr>
        <th>Nombre</th><th>Origen</th><th>Preguntas</th><th></th></tr></thead><tbody>
        ${data.map(t => `<tr>
          <td><strong>${UI.esc(t.name)}</strong><br><span style="font-size:11px;color:var(--text-muted);">${UI.esc(t.description || '')}</span></td>
          <td style="font-size:11px;">${t.created_from ? UI.esc(t.created_from) : 'Personalizada'}</td>
          <td>${(t.questions || []).length}</td>
          <td>
            ${Auth.canEdit() ? `<button class="btn btn-sm" data-id="${t.id}" data-act="edit">Editar</button>
            <button class="btn btn-sm btn-danger" data-id="${t.id}" data-act="del">Eliminar</button>` : ''}
          </td>
        </tr>`).join('')}
      </tbody></table>`;
      wrap.querySelectorAll('[data-act="edit"]').forEach(b => {
        b.onclick = async () => {
          try { const t = await Api.tprm.customTemplate(b.dataset.id); _openEditor(t); }
          catch (e) { UI.toast(e.message, 'error'); }
        };
      });
      wrap.querySelectorAll('[data-act="del"]').forEach(b => {
        b.onclick = async () => {
          if (!await UI.confirm('Eliminar esta plantilla?')) return;
          try { await Api.tprm.deleteCustomTemplate(b.dataset.id); UI.toast('Eliminada', 'success'); _loadCustom(); }
          catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  async function _clone(code) {
    try {
      const t = await Api.tprm.createCustomTemplate({ from_system_code: code });
      UI.toast('Plantilla clonada. Editala a tu gusto.', 'success');
      await _loadCustom();
      _openEditor(t);
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  function _questionRowHtml(q, i) {
    return `
      <div class="tpl-q-row" data-idx="${i}" style="border:1px solid var(--border);border-radius:8px;padding:10px 12px 10px 12px;margin-bottom:8px;background:var(--bg-2,var(--bg));">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:7px;">
          <span style="font-weight:700;color:var(--brand-purple);font-size:13px;min-width:20px;">${i + 1}.</span>
          <div style="display:flex;gap:4px;margin-left:auto;">
            <button class="btn btn-sm tq-up" title="Subir" style="padding:2px 9px;line-height:1;">&uarr;</button>
            <button class="btn btn-sm tq-down" title="Bajar" style="padding:2px 9px;line-height:1;">&darr;</button>
            <button class="btn btn-sm btn-danger tq-del" title="Eliminar" style="padding:2px 9px;line-height:1;">&times;</button>
          </div>
        </div>
        <textarea class="input tq-text" rows="2"
          style="width:100%;box-sizing:border-box;resize:vertical;font-size:13px;"
          placeholder="Texto de la pregunta">${UI.esc(q.text || '')}</textarea>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;align-items:center;">
          <select class="input tq-type" style="flex:1;min-width:150px;font-size:12px;">
            ${Object.entries(TYPE_LABELS).map(([k, l]) => `<option value="${k}" ${ (q.type || 'yes_no_partial') === k ? 'selected' : '' }>${l}</option>`).join('')}
          </select>
          <select class="input tq-domain" style="flex:1;min-width:150px;font-size:12px;">
            ${DOMAINS.map(d => `<option value="${d}" ${ (q.domain || 'governance') === d ? 'selected' : '' }>${d}</option>`).join('')}
          </select>
          <div style="display:flex;align-items:center;gap:4px;">
            <label style="font-size:11px;color:var(--text-muted);margin:0;white-space:nowrap;">Peso</label>
            <input type="number" class="input tq-weight" style="width:70px;font-size:12px;" min="0" max="5" step="0.5" value="${q.weight != null ? q.weight : 1}">
          </div>
          <label style="display:flex;align-items:center;gap:5px;font-size:12px;margin:0;white-space:nowrap;cursor:pointer;">
            <input type="checkbox" class="tq-evid" ${q.requires_evidence ? 'checked' : ''}> Evidencia
          </label>
        </div>
      </div>`;
  }

  function _renderEditorQuestions() {
    const wrap = document.getElementById('tpl-q-list');
    if (!wrap) return;
    wrap.innerHTML = _editQuestions.map((q, i) => _questionRowHtml(q, i)).join('')
      || '<p class="text-muted">Sin preguntas. Anade la primera.</p>';
    wrap.querySelectorAll('.tpl-q-row').forEach(row => {
      const i = parseInt(row.dataset.idx);
      row.querySelector('.tq-del').onclick = () => { _syncFromDom(); _editQuestions.splice(i, 1); _renderEditorQuestions(); };
      row.querySelector('.tq-up').onclick = () => { _syncFromDom(); if (i > 0) { [_editQuestions[i-1], _editQuestions[i]] = [_editQuestions[i], _editQuestions[i-1]]; _renderEditorQuestions(); } };
      row.querySelector('.tq-down').onclick = () => { _syncFromDom(); if (i < _editQuestions.length - 1) { [_editQuestions[i+1], _editQuestions[i]] = [_editQuestions[i], _editQuestions[i+1]]; _renderEditorQuestions(); } };
    });
  }

  // Lee el DOM del editor a _editQuestions (preserva ediciones antes de reordenar/borrar)
  function _syncFromDom() {
    const rows = document.querySelectorAll('#tpl-q-list .tpl-q-row');
    const out = [];
    rows.forEach((row, i) => {
      const prev = _editQuestions[parseInt(row.dataset.idx)] || {};
      out.push({
        id: prev.id || ('q' + (i + 1) + '_' + Math.random().toString(36).slice(2, 6)),
        text: row.querySelector('.tq-text').value.trim(),
        type: row.querySelector('.tq-type').value,
        domain: row.querySelector('.tq-domain').value,
        weight: parseFloat(row.querySelector('.tq-weight').value) || 1,
        requires_evidence: row.querySelector('.tq-evid').checked,
        control_refs: prev.control_refs || [],
      });
    });
    _editQuestions = out;
  }

  function _openEditor(tpl) {
    _editId = tpl ? tpl.id : null;
    _editQuestions = tpl && tpl.questions ? tpl.questions.map(q => Object.assign({}, q)) : [];
    UI.modal(tpl ? `Editar plantilla` : 'Nueva plantilla', `
      <div class="span2"><label>Nombre *</label><input id="tpl-name" class="input" value="${UI.esc(tpl ? tpl.name : '')}"></div>
      <div class="span2"><label>Descripcion</label><input id="tpl-desc" class="input" value="${UI.esc(tpl ? (tpl.description || '') : '')}"></div>
      <div class="span2">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <label style="margin:0;">Preguntas</label>
          <button class="btn btn-sm" id="tpl-add-q">+ Anadir pregunta</button>
        </div>
        <p style="font-size:11px;color:var(--text-muted);margin:4px 0;">El peso pondera la pregunta en la puntuacion. "Evidencia" pide un documento al proveedor (opcional para el; penaliza el score si falta).</p>
        <div id="tpl-q-list" style="margin-top:8px;max-height:52vh;overflow-y:auto;"></div>
      </div>
    `, {
      width: '820px',
      actions: `<button class="btn" id="tpl-cancel">Cancelar</button>
                <button class="btn btn-primary" id="tpl-save">Guardar plantilla</button>`,
    });
    _renderEditorQuestions();
    document.getElementById('tpl-add-q').onclick = () => {
      _syncFromDom();
      _editQuestions.push({ text: '', type: 'yes_no_partial', domain: 'governance', weight: 1, requires_evidence: false });
      _renderEditorQuestions();
    };
    document.getElementById('tpl-cancel').onclick = UI.closeModal;
    document.getElementById('tpl-save').onclick = _save;
  }

  async function _save() {
    const name = document.getElementById('tpl-name').value.trim();
    if (!name) { UI.toast('El nombre es obligatorio', 'error'); return; }
    _syncFromDom();
    const questions = _editQuestions.filter(q => q.text).map(q => ({
      ...q,
      scoring_rules: _rulesForType(q.type),
    }));
    if (!questions.length) { UI.toast('Anade al menos una pregunta con texto', 'error'); return; }
    const body = {
      name,
      description: document.getElementById('tpl-desc').value.trim() || null,
      questions,
    };
    try {
      if (_editId) await Api.tprm.updateCustomTemplate(_editId, body);
      else await Api.tprm.createCustomTemplate(body);
      UI.closeModal();
      UI.toast('Plantilla guardada', 'success');
      await _loadCustom();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  return { render };
})();
