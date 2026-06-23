/* Vista de plantillas de cuestionario TPRM — editables por el cliente.
   Lista plantillas del sistema (clonables) y personalizadas (editar/eliminar)
   con un editor de preguntas (texto, tipo, peso, evidencia, dominio). */
const ViewVendorTemplates = (() => {

  function _getTypeLabels() {
    return {
      yes_no:         t('vendor_templates.type.yes_no'),
      yes_no_partial: t('vendor_templates.type.yes_no_partial'),
      scale_1_5:      t('vendor_templates.type.scale_1_5'),
      single_choice:  t('vendor_templates.type.single_choice'),
      text_long:      t('vendor_templates.type.text_long'),
    };
  }

  const DOMAINS = [
    'governance', 'risk_management', 'asset_management', 'access_control',
    'cryptography', 'physical_security', 'operations_security', 'network_security',
    'secure_development', 'supplier_chain', 'incident_management', 'business_continuity',
    'compliance_legal', 'privacy', 'ai_governance', 'resilience_testing',
  ];

  function _rulesForType(type) {
    if (type === 'yes_no') return { yes: 100, no: 0, na: null };
    if (type === 'yes_no_partial') return { yes: 100, partial: 50, no: 0, na: null };
    if (type === 'scale_1_5') return { '1': 0, '2': 25, '3': 50, '4': 75, '5': 100 };
    return null;
  }

  let _editQuestions = [];
  let _editId = null;

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('vendor_templates.page_title')}</h1>
          <p class="page-sub">${t('vendor_templates.page_sub')}</p>
        </div>
        ${Auth.canEdit() ? `<button class="btn btn-primary" id="btn-new-tpl">${t('vendor_templates.new_btn')}</button>` : ''}
      </div>
      <div class="card" style="margin-bottom:16px;">
        <h3 style="margin-top:0;">${t('vendor_templates.system_title')}</h3>
        <p style="font-size:12px;color:var(--text-muted);margin-top:0;">${t('vendor_templates.system_desc')}</p>
        <div id="tpl-system">${t('vendor_templates.loading')}</div>
      </div>
      <div class="card">
        <h3 style="margin-top:0;">${t('vendor_templates.custom_title')}</h3>
        <div id="tpl-custom">${t('vendor_templates.loading')}</div>
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
        <th>${t('vendor_templates.col_name')}</th><th>${t('vendor_templates.col_frameworks')}</th>
        <th>${t('vendor_templates.col_questions')}</th><th></th></tr></thead><tbody>
        ${data.map(tpl => `<tr>
          <td><strong>${UI.esc(tpl.name)}</strong><br><span style="font-size:11px;color:var(--text-muted);">${UI.esc(tpl.description || '')}</span></td>
          <td style="font-size:11px;">${(tpl.framework_codes || []).map(UI.esc).join(', ')}</td>
          <td>${tpl.question_count}</td>
          <td>${Auth.canEdit() ? `<button class="btn btn-sm" data-code="${UI.esc(tpl.code)}" data-act="clone">${t('vendor_templates.clone_btn')}</button>` : ''}</td>
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
        wrap.innerHTML = `<p class="text-muted">${t('vendor_templates.no_custom')}</p>`;
        return;
      }
      wrap.innerHTML = `<table class="data"><thead><tr>
        <th>${t('vendor_templates.col_name')}</th><th>${t('vendor_templates.col_origin')}</th>
        <th>${t('vendor_templates.col_questions')}</th><th></th></tr></thead><tbody>
        ${data.map(tpl => `<tr>
          <td><strong>${UI.esc(tpl.name)}</strong><br><span style="font-size:11px;color:var(--text-muted);">${UI.esc(tpl.description || '')}</span></td>
          <td style="font-size:11px;">${tpl.created_from ? UI.esc(tpl.created_from) : t('vendor_templates.custom_origin')}</td>
          <td>${(tpl.questions || []).length}</td>
          <td>
            ${Auth.canEdit() ? `<button class="btn btn-sm" data-id="${tpl.id}" data-act="edit">${t('vendor_templates.edit_btn')}</button>
            <button class="btn btn-sm btn-danger" data-id="${tpl.id}" data-act="del">${t('vendor_templates.delete_btn')}</button>` : ''}
          </td>
        </tr>`).join('')}
      </tbody></table>`;
      wrap.querySelectorAll('[data-act="edit"]').forEach(b => {
        b.onclick = async () => {
          try { const tpl = await Api.tprm.customTemplate(b.dataset.id); _openEditor(tpl); }
          catch (e) { UI.toast(e.message, 'error'); }
        };
      });
      wrap.querySelectorAll('[data-act="del"]').forEach(b => {
        b.onclick = async () => {
          if (!await UI.confirm(t('vendor_templates.delete_confirm'))) return;
          try {
            await Api.tprm.deleteCustomTemplate(b.dataset.id);
            UI.toast(t('vendor_templates.deleted_toast'), 'success');
            _loadCustom();
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  async function _clone(code) {
    try {
      const tpl = await Api.tprm.createCustomTemplate({ from_system_code: code });
      UI.toast(t('vendor_templates.cloned_toast'), 'success');
      await _loadCustom();
      _openEditor(tpl);
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  function _questionRowHtml(q, i) {
    const typeLabels = _getTypeLabels();
    return `
      <div class="tpl-q-row" data-idx="${i}" style="border:1px solid var(--border);border-radius:8px;padding:10px 12px 10px 12px;margin-bottom:8px;background:var(--bg-2,var(--bg));">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:7px;">
          <span style="font-weight:700;color:var(--brand-purple);font-size:13px;min-width:20px;">${i + 1}.</span>
          <div style="display:flex;gap:4px;margin-left:auto;">
            <button class="btn btn-sm tq-up" title="&#8593;" style="padding:2px 9px;line-height:1;">&uarr;</button>
            <button class="btn btn-sm tq-down" title="&#8595;" style="padding:2px 9px;line-height:1;">&darr;</button>
            <button class="btn btn-sm btn-danger tq-del" style="padding:2px 9px;line-height:1;">&times;</button>
          </div>
        </div>
        <textarea class="input tq-text" rows="2"
          style="width:100%;box-sizing:border-box;resize:vertical;font-size:13px;"
          placeholder="${t('vendor_templates.question_placeholder')}">${UI.esc(q.text || '')}</textarea>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;align-items:center;">
          <select class="input tq-type" style="flex:1;min-width:150px;font-size:12px;">
            ${Object.entries(typeLabels).map(([k, l]) => `<option value="${k}" ${(q.type || 'yes_no_partial') === k ? 'selected' : ''}>${l}</option>`).join('')}
          </select>
          <select class="input tq-domain" style="flex:1;min-width:150px;font-size:12px;">
            ${DOMAINS.map(d => `<option value="${d}" ${(q.domain || 'governance') === d ? 'selected' : ''}>${d}</option>`).join('')}
          </select>
          <div style="display:flex;align-items:center;gap:4px;">
            <label style="font-size:11px;color:var(--text-muted);margin:0;white-space:nowrap;">${t('vendor_templates.weight_label')}</label>
            <input type="number" class="input tq-weight" style="width:70px;font-size:12px;" min="0" max="5" step="0.5" value="${q.weight != null ? q.weight : 1}">
          </div>
          <label style="display:flex;align-items:center;gap:5px;font-size:12px;margin:0;white-space:nowrap;cursor:pointer;">
            <input type="checkbox" class="tq-evid" ${q.requires_evidence ? 'checked' : ''}> ${t('vendor_templates.evidence_label')}
          </label>
        </div>
      </div>`;
  }

  function _renderEditorQuestions() {
    const wrap = document.getElementById('tpl-q-list');
    if (!wrap) return;
    wrap.innerHTML = _editQuestions.map((q, i) => _questionRowHtml(q, i)).join('')
      || `<p class="text-muted">${t('vendor_templates.no_questions')}</p>`;
    wrap.querySelectorAll('.tpl-q-row').forEach(row => {
      const i = parseInt(row.dataset.idx);
      row.querySelector('.tq-del').onclick = () => { _syncFromDom(); _editQuestions.splice(i, 1); _renderEditorQuestions(); };
      row.querySelector('.tq-up').onclick = () => { _syncFromDom(); if (i > 0) { [_editQuestions[i - 1], _editQuestions[i]] = [_editQuestions[i], _editQuestions[i - 1]]; _renderEditorQuestions(); } };
      row.querySelector('.tq-down').onclick = () => { _syncFromDom(); if (i < _editQuestions.length - 1) { [_editQuestions[i + 1], _editQuestions[i]] = [_editQuestions[i], _editQuestions[i + 1]]; _renderEditorQuestions(); } };
    });
  }

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
    const title = tpl ? t('vendor_templates.modal_edit_title') : t('vendor_templates.modal_new_title');
    UI.modal(title, `
      <div class="span2"><label>${t('vendor_templates.name_label')}</label><input id="tpl-name" class="input" value="${UI.esc(tpl ? tpl.name : '')}"></div>
      <div class="span2"><label>${t('vendor_templates.desc_label')}</label><input id="tpl-desc" class="input" value="${UI.esc(tpl ? (tpl.description || '') : '')}"></div>
      <div class="span2">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <label style="margin:0;">${t('vendor_templates.questions_label')}</label>
          <button class="btn btn-sm" id="tpl-add-q">${t('vendor_templates.add_question_btn')}</button>
        </div>
        <p style="font-size:11px;color:var(--text-muted);margin:4px 0;">${t('vendor_templates.questions_hint')}</p>
        <div id="tpl-q-list" style="margin-top:8px;max-height:52vh;overflow-y:auto;"></div>
      </div>
    `, {
      width: '820px',
      actions: `<button class="btn" id="tpl-cancel">${t('vendor_templates.cancel_btn')}</button>
                <button class="btn btn-primary" id="tpl-save">${t('vendor_templates.save_btn')}</button>`,
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
    if (!name) { UI.toast(t('vendor_templates.name_required'), 'error'); return; }
    _syncFromDom();
    const questions = _editQuestions.filter(q => q.text).map(q => ({
      ...q,
      scoring_rules: _rulesForType(q.type),
    }));
    if (!questions.length) { UI.toast(t('vendor_templates.question_required'), 'error'); return; }
    const body = {
      name,
      description: document.getElementById('tpl-desc').value.trim() || null,
      questions,
    };
    try {
      if (_editId) await Api.tprm.updateCustomTemplate(_editId, body);
      else await Api.tprm.createCustomTemplate(body);
      UI.closeModal();
      UI.toast(t('vendor_templates.saved_toast'), 'success');
      await _loadCustom();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  return { render };
})();
