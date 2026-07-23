/* Vista "Metodo de la organizacion".
 *
 * Muestra que parametros usa esta organizacion para calcular, de donde sale
 * cada uno (su politica citada, una decision manual, o el defecto de la
 * plataforma), que reglas suyas la herramienta todavia no sabe aplicar, y donde
 * lo que se calcula diverge de su propia norma. La procedencia se ensena junto
 * al valor, nunca escondida: es lo que hace defendible una cifra en auditoria.
 */
const ViewMethod = (() => {

  const _MODULES = [
    { id: 'bcm',  label: () => t('method.mod_bcm') },
    { id: 'risk', label: () => t('method.mod_risk') },
    { id: 'tprm', label: () => t('method.mod_tprm') },
  ];

  const _SOURCE_BADGE = {
    policy:  'badge-success',
    manual:  'badge-warning',
    default: 'badge-muted',
  };

  const _KIND_BADGE = {
    default_used_despite_policy: 'badge-danger',
    manual_override_diverges_from_policy: 'badge-warning',
    unmodelled_rule: 'badge-info',
    policy_below_norm: 'badge-danger',
  };

  function _sourceLabel(src) {
    return t('method.source_' + src) || src;
  }

  function _fmtVal(v) {
    if (v == null || v === '') return '<span class="text-muted">-</span>';
    if (typeof v === 'object') {
      const s = JSON.stringify(v);
      return `<code>${UI.esc(s.length > 120 ? s.slice(0, 117) + '...' : s)}</code>`;
    }
    return `<code>${UI.esc(String(v))}</code>`;
  }

  function _canEdit() {
    return Auth.canEdit ? Auth.canEdit() : Auth.isAdmin();
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('method.page_title')}</h1>
          <p class="page-sub">${t('method.page_subtitle')}</p>
        </div>
      </div>
      <div id="method-summary" class="card" style="margin-bottom:16px;"><p class="text-muted">${t('common.loading')}</p></div>
      <div id="method-conformance" class="card" style="margin-bottom:16px;"><p class="text-muted">${t('common.loading')}</p></div>
      <div id="method-statements" class="card" style="margin-bottom:16px;"><p class="text-muted">${t('common.loading')}</p></div>
      <div id="method-params" class="card"><p class="text-muted">${t('common.loading')}</p></div>
    `;
    _loadSummary();
    _loadConformance();
    _loadStatements();
    _loadParams();
  }

  // ---------- Resumen ----------

  async function _loadSummary() {
    const box = document.getElementById('method-summary');
    if (!box) return;
    try {
      const d = await Api.get('/api/method/conformance');
      const s = d.summary || {};
      box.innerHTML = `
        <h2 class="card-title">${t('method.summary_title')}</h2>
        <p class="text-muted" style="margin:0 0 12px;">${t('method.summary_help')}</p>
        <div class="stat-row" style="display:flex;flex-wrap:wrap;gap:12px;">
          ${_stat(s.from_policy, t('method.stat_from_policy'), 'var(--brand-purple)')}
          ${_stat(s.manual, t('method.stat_manual'), 'var(--brand-orange)')}
          ${_stat(s.default, t('method.stat_default'), 'var(--text-muted)')}
          ${_stat(s.wired + '/' + s.parameters_total, t('method.stat_wired'), 'var(--text)')}
          ${_stat(s.findings_total, t('method.stat_findings'), s.findings_total ? 'var(--danger, #c0392b)' : 'var(--text-muted)')}
        </div>`;
    } catch (e) {
      box.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _stat(value, label, color) {
    return `<div style="min-width:120px;flex:1;">
      <div style="font-size:26px;font-weight:700;color:${color};">${UI.esc(String(value == null ? '-' : value))}</div>
      <div style="font-size:12px;color:var(--text-muted);">${UI.esc(label)}</div>
    </div>`;
  }

  // ---------- Conformidad ----------

  async function _loadConformance() {
    const box = document.getElementById('method-conformance');
    if (!box) return;
    try {
      const d = await Api.get('/api/method/conformance');
      const findings = (d.findings || []).filter(f => f.status !== 'accepted');
      const refreshBtn = _canEdit()
        ? `<button class="btn btn-sm btn-ghost" id="method-refresh">${t('method.refresh')}</button>` : '';
      if (!findings.length) {
        box.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <h2 class="card-title" style="margin:0;">${t('method.conformance_title')}</h2>${refreshBtn}
          </div>
          <p class="text-muted" style="margin:12px 0 0;">${t('method.conformance_clean')}</p>`;
      } else {
        box.innerHTML = `
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <h2 class="card-title" style="margin:0;">${t('method.conformance_title')} (${findings.length})</h2>${refreshBtn}
          </div>
          <div style="display:flex;flex-direction:column;gap:10px;">
            ${findings.map(_findingCard).join('')}
          </div>`;
      }
      const rb = document.getElementById('method-refresh');
      if (rb) rb.onclick = async () => {
        rb.disabled = true;
        try { await Api.post('/api/method/conformance/refresh'); _loadAll(); }
        catch (e) { UI.toast(e.message, 'error'); rb.disabled = false; }
      };
      box.querySelectorAll('[data-accept]').forEach(btn => {
        btn.onclick = async () => {
          try {
            await Api.post(`/api/method/conformance/findings/${btn.dataset.accept}/accept`);
            _loadConformance(); _loadSummary();
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) {
      box.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _findingCard(f) {
    const badge = _KIND_BADGE[f.kind] || 'badge-muted';
    // policy_below_norm no es un error de calculo: hay que dejarlo claro o el
    // usuario pensara que la herramienta esta rota.
    const isNorm = f.kind === 'policy_below_norm';
    const detail = isNorm
      ? `<div style="font-size:12px;margin-top:6px;">
           <span class="text-muted">${t('method.your_method')}:</span> ${_fmtVal(f.effective_value)}
           &nbsp;·&nbsp;
           <span class="text-muted">${UI.esc(f.normative_ref || '')}:</span> ${_fmtVal(f.normative_value)}
         </div>
         <div style="font-size:12px;margin-top:4px;color:var(--brand-orange);">${t('method.calc_with_yours')}</div>`
      : `<div style="font-size:12px;margin-top:6px;">
           <span class="text-muted">${t('method.effective')}:</span> ${_fmtVal(f.effective_value)}
           ${f.policy_value != null ? `&nbsp;·&nbsp;<span class="text-muted">${t('method.policy')}:</span> ${_fmtVal(f.policy_value)}` : ''}
         </div>`;
    const acceptBtn = _canEdit()
      ? `<button class="btn btn-xs btn-ghost" data-accept="${f.id}">${t('method.accept')}</button>` : '';
    return `<div style="border:1px solid var(--border);border-radius:8px;padding:12px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
        <div>
          <span class="badge ${badge}">${t('method.kind_' + f.kind) || UI.esc(f.kind)}</span>
          ${f.parameter_key ? `<code style="font-size:11px;margin-left:6px;">${UI.esc(f.parameter_key)}</code>` : ''}
        </div>
        ${acceptBtn}
      </div>
      <p style="margin:8px 0 0;font-size:13px;">${UI.esc(f.summary || '')}</p>
      ${detail}
    </div>`;
  }

  // ---------- Declaraciones extraidas de la politica ----------

  async function _loadStatements() {
    const box = document.getElementById('method-statements');
    if (!box) return;
    try {
      const all = await Api.get('/api/method/statements');
      const active = all.filter(s => s.status !== 'rejected');
      if (!active.length) {
        box.innerHTML = `<h2 class="card-title">${t('method.statements_title')}</h2>
          <p class="text-muted" style="margin:12px 0 0;">${t('method.statements_empty')}</p>`;
        return;
      }
      const proposed = active.filter(s => s.status === 'proposed');
      const bound = active.filter(s => s.status === 'bound');
      const unmodelled = active.filter(s => s.status === 'unmodelled');
      box.innerHTML = `
        <h2 class="card-title">${t('method.statements_title')}</h2>
        <p class="text-muted" style="margin:0 0 12px;">${t('method.statements_help')}</p>
        ${_stmtGroup(t('method.stmt_proposed'), proposed, true)}
        ${_stmtGroup(t('method.stmt_unmodelled'), unmodelled, false, t('method.unmodelled_help'))}
        ${_stmtGroup(t('method.stmt_bound'), bound, false)}
      `;
      _wireStatementButtons(box);
    } catch (e) {
      box.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _stmtGroup(title, list, actionable, help) {
    if (!list.length) return '';
    return `<div style="margin-top:14px;">
      <h3 style="font-size:14px;margin:0 0 4px;">${UI.esc(title)} (${list.length})</h3>
      ${help ? `<p class="text-muted" style="font-size:12px;margin:0 0 8px;">${UI.esc(help)}</p>` : ''}
      <div style="display:flex;flex-direction:column;gap:10px;">
        ${list.map(s => _stmtCard(s, actionable)).join('')}
      </div>
    </div>`;
  }

  function _stmtCard(s, actionable) {
    const cite = [s.source_document, s.source_section].filter(Boolean).map(UI.esc).join(' · ');
    const conf = s.confidence != null ? Math.round(s.confidence * 100) + '%' : '';
    const buttons = (actionable && _canEdit())
      ? `<div style="display:flex;gap:6px;">
           <button class="btn btn-xs btn-primary" data-apply="${s.id}">${t('method.apply')}</button>
           <button class="btn btn-xs btn-ghost" data-reject="${s.id}">${t('method.reject')}</button>
         </div>`
      : (_canEdit() && s.status === 'unmodelled'
          ? `<button class="btn btn-xs btn-ghost" data-reject="${s.id}">${t('method.reject')}</button>` : '');
    return `<div style="border:1px solid var(--border);border-radius:8px;padding:12px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
        <div style="min-width:0;">
          ${s.parameter_key ? `<code style="font-size:11px;">${UI.esc(s.parameter_key)}</code>` : `<span class="badge badge-info">${t('method.no_parameter')}</span>`}
          ${s.proposed_value != null ? `&nbsp;→&nbsp;${_fmtVal(s.proposed_value)}` : ''}
          ${conf ? `<span class="text-muted" style="font-size:11px;margin-left:6px;">${t('method.confidence')} ${conf}</span>` : ''}
        </div>
        ${buttons}
      </div>
      <blockquote style="margin:10px 0 4px;padding:8px 12px;border-left:3px solid var(--brand-purple);background:var(--bg-subtle, rgba(89,0,141,.05));font-size:13px;font-style:italic;">
        ${UI.esc(s.quote || '')}
      </blockquote>
      <div style="font-size:11px;color:var(--text-muted);">${cite || t('method.no_citation')}</div>
      ${s.interpretation ? `<p style="font-size:12px;margin:6px 0 0;">${UI.esc(s.interpretation)}</p>` : ''}
    </div>`;
  }

  function _wireStatementButtons(box) {
    box.querySelectorAll('[data-apply]').forEach(btn => {
      btn.onclick = async () => {
        try {
          await Api.post(`/api/method/statements/${btn.dataset.apply}/apply`);
          UI.toast(t('method.applied'), 'success');
          _loadAll();
        } catch (e) {
          // El backend puede decir que hay un valor manual: ofrecer forzar.
          if ((e.message || '').toLowerCase().includes('manual')
              && await UI.confirm(t('method.force_apply_q'))) {
            try {
              await Api.post(`/api/method/statements/${btn.dataset.apply}/apply?force=true`);
              UI.toast(t('method.applied'), 'success'); _loadAll();
            } catch (e2) { UI.toast(e2.message, 'error'); }
          } else {
            UI.toast(e.message, 'error');
          }
        }
      };
    });
    box.querySelectorAll('[data-reject]').forEach(btn => {
      btn.onclick = async () => {
        try {
          await Api.post(`/api/method/statements/${btn.dataset.reject}/reject`);
          _loadStatements(); _loadConformance(); _loadSummary();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });
  }

  // ---------- Parametros por modulo ----------

  async function _loadParams() {
    const box = document.getElementById('method-params');
    if (!box) return;
    try {
      const params = await Api.get('/api/method/parameters');
      const byModule = {};
      params.forEach(p => { (byModule[p.module] = byModule[p.module] || []).push(p); });
      box.innerHTML = `
        <h2 class="card-title">${t('method.params_title')}</h2>
        <p class="text-muted" style="margin:0 0 12px;">${t('method.params_help')}</p>
        ${_MODULES.map(m => _moduleBlock(m, byModule[m.id] || [])).join('')}
      `;
      box.querySelectorAll('[data-edit]').forEach(btn => {
        btn.onclick = () => _openEditor(params.find(p => p.key === btn.dataset.edit));
      });
      box.querySelectorAll('[data-reset]').forEach(btn => {
        btn.onclick = async () => {
          if (!await UI.confirm(t('method.reset_q'))) return;
          try { await Api.del(`/api/method/parameters/${encodeURIComponent(btn.dataset.reset)}`);
            UI.toast(t('method.reset_done'), 'success'); _loadAll();
          } catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) {
      box.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _moduleBlock(m, params) {
    if (!params.length) return '';
    return `<div style="margin-top:16px;">
      <h3 style="font-size:15px;margin:0 0 8px;">${UI.esc(m.label())}</h3>
      <div style="display:flex;flex-direction:column;gap:8px;">
        ${params.map(_paramRow).join('')}
      </div>
    </div>`;
  }

  function _paramRow(p) {
    const badge = _SOURCE_BADGE[p.source] || 'badge-muted';
    const wiredMark = p.wired ? ''
      : `<span class="badge badge-muted" title="${t('method.not_wired_help')}">${t('method.not_wired')}</span>`;
    const actions = _canEdit()
      ? `<div style="display:flex;gap:6px;flex-shrink:0;">
           <button class="btn btn-xs btn-ghost" data-edit="${UI.esc(p.key)}">${t('method.edit')}</button>
           ${p.source !== 'default' ? `<button class="btn btn-xs btn-ghost" data-reset="${UI.esc(p.key)}">${t('method.reset')}</button>` : ''}
         </div>` : '';
    return `<div style="border:1px solid var(--border);border-radius:8px;padding:10px 12px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
        <div style="min-width:0;">
          <div style="font-weight:600;font-size:13px;">${UI.esc(p.label)} ${wiredMark}</div>
          <code style="font-size:11px;color:var(--text-muted);">${UI.esc(p.key)}</code>
        </div>
        ${actions}
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:8px;flex-wrap:wrap;">
        <div>${_fmtVal(p.value)}</div>
        <div style="text-align:right;">
          <span class="badge ${badge}">${_sourceLabel(p.source)}</span>
          <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${UI.esc(p.explain || '')}</div>
        </div>
      </div>
      ${p.description ? `<p class="text-muted" style="font-size:12px;margin:8px 0 0;">${UI.esc(p.description)}</p>` : ''}
    </div>`;
  }

  // ---------- Editor por tipo ----------

  function _openEditor(p) {
    if (!p) return;
    const body = (p.type === 'formula') ? _formulaEditor(p) : _valueEditor(p);
    UI.openModal(`
      <h2 style="margin-top:0;">${UI.esc(p.label)}</h2>
      <code style="font-size:11px;color:var(--text-muted);">${UI.esc(p.key)}</code>
      ${p.description ? `<p class="text-muted" style="font-size:13px;">${UI.esc(p.description)}</p>` : ''}
      <div id="method-editor-body" style="margin-top:12px;">${body}</div>
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px;">
        <button class="btn btn-ghost" id="method-cancel">${t('common.cancel')}</button>
        <button class="btn btn-primary" id="method-save">${t('common.save')}</button>
      </div>
    `, { width: p.type === 'formula' ? '640px' : '480px' });

    document.getElementById('method-cancel').onclick = UI.closeModal;
    document.getElementById('method-save').onclick = () => _saveEditor(p);
    if (p.type === 'formula') _wireFormulaValidation(p);
  }

  function _valueEditor(p) {
    if (p.type === 'enum' && p.choices) {
      return `<select id="method-input" class="input" style="width:100%;">
        ${p.choices.map(c => `<option value="${UI.esc(String(c))}" ${String(p.value) === String(c) ? 'selected' : ''}>${UI.esc(String(c))}</option>`).join('')}
      </select>`;
    }
    if (p.type === 'number' || p.type === 'cadence') {
      return `<input id="method-input" type="number" class="input" style="width:100%;"
                value="${p.value != null ? UI.esc(String(p.value)) : ''}"
                placeholder="${UI.esc(String(p.default != null ? p.default : ''))}">
              ${p.unit ? `<span class="text-muted" style="font-size:12px;">${UI.esc(p.unit)}</span>` : ''}`;
    }
    // weights / scale / bands / matrix / dimensions / fields → JSON validado
    const val = p.value != null ? p.value : p.default;
    return `<p class="text-muted" style="font-size:12px;margin:0 0 6px;">${t('method.json_help')}</p>
      <textarea id="method-input" class="input" rows="12" style="width:100%;font-family:monospace;font-size:12px;">${UI.esc(JSON.stringify(val, null, 2))}</textarea>
      <div id="method-json-error" style="color:var(--danger,#c0392b);font-size:12px;margin-top:4px;"></div>`;
  }

  function _readValue(p) {
    const input = document.getElementById('method-input');
    if (!input) return undefined;
    if (p.type === 'number' || p.type === 'cadence') {
      return input.value === '' ? null : Number(input.value);
    }
    if (p.type === 'enum') return input.value;
    // JSON
    try {
      const parsed = JSON.parse(input.value);
      const errBox = document.getElementById('method-json-error');
      if (errBox) errBox.textContent = '';
      return parsed;
    } catch (e) {
      const errBox = document.getElementById('method-json-error');
      if (errBox) errBox.textContent = t('method.json_invalid') + ' ' + e.message;
      throw new Error(t('method.json_invalid'));
    }
  }

  async function _saveEditor(p) {
    let value;
    try { value = _readValue(p); } catch (e) { return; }
    if (p.type === 'formula') value = document.getElementById('method-formula-expr').value;
    try {
      await Api.put(`/api/method/parameters/${encodeURIComponent(p.key)}`, { value });
      UI.closeModal();
      UI.toast(t('method.saved'), 'success');
      _loadAll();
    } catch (e) {
      // El backend explica por que un valor no vale (opciones, cadencia,
      // formula peligrosa, pesos): se muestra tal cual.
      UI.toast(e.message, 'error');
    }
  }

  // ---------- Editor de formula con validacion en vivo ----------

  function _formulaEditor(p) {
    const vars = p.variables || [];
    return `
      <p class="text-muted" style="font-size:12px;margin:0 0 6px;">${t('method.formula_help')}</p>
      <textarea id="method-formula-expr" class="input" rows="3" style="width:100%;font-family:monospace;">${UI.esc(String(p.value || ''))}</textarea>
      <div style="font-size:12px;margin-top:8px;">
        <div><span class="text-muted">${t('method.formula_vars')}:</span> ${vars.map(v => `<code>${UI.esc(v)}</code>`).join(' ') || '-'}</div>
        <div id="method-formula-fns" style="margin-top:2px;"></div>
      </div>
      <div style="margin-top:10px;">
        <div class="text-muted" style="font-size:12px;">${t('method.formula_test')}</div>
        <div id="method-formula-sample" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:4px;">
          ${vars.map(v => `<label style="font-size:11px;">${UI.esc(v)}
            <input data-var="${UI.esc(v)}" type="number" value="1" class="input" style="width:70px;display:inline-block;"></label>`).join('')}
        </div>
      </div>
      <div id="method-formula-result" style="margin-top:10px;font-size:13px;"></div>`;
  }

  function _wireFormulaValidation(p) {
    const expr = document.getElementById('method-formula-expr');
    const runValidation = async () => {
      const sample = {};
      document.querySelectorAll('#method-formula-sample [data-var]').forEach(inp => {
        sample[inp.dataset.var] = Number(inp.value) || 0;
      });
      const resBox = document.getElementById('method-formula-result');
      if (!expr.value.trim()) { resBox.innerHTML = ''; return; }
      try {
        const d = await Api.post('/api/method/formula/validate', {
          expression: expr.value, variables: p.variables || [], samples: [sample],
        });
        const fnsBox = document.getElementById('method-formula-fns');
        if (fnsBox && d.functions) {
          fnsBox.innerHTML = `<span class="text-muted">${t('method.formula_fns')}:</span> ${d.functions.map(f => `<code>${UI.esc(f)}</code>`).join(' ')}`;
        }
        if (!d.valid) {
          // Si alguien prueba __import__('os') el backend lo rechaza aqui.
          resBox.innerHTML = `<span style="color:var(--danger,#c0392b);">${UI.esc(d.error || t('method.formula_invalid'))}</span>`;
        } else {
          const r = (d.results && d.results[0]) ? d.results[0].result : '?';
          resBox.innerHTML = `<span style="color:var(--brand-purple);">${t('method.formula_ok')} → <b>${UI.esc(String(r))}</b></span>`;
        }
      } catch (e) {
        resBox.innerHTML = `<span style="color:var(--danger,#c0392b);">${UI.esc(e.message)}</span>`;
      }
    };
    let deb;
    expr.addEventListener('input', () => { clearTimeout(deb); deb = setTimeout(runValidation, 350); });
    document.querySelectorAll('#method-formula-sample [data-var]').forEach(
      inp => inp.addEventListener('input', () => { clearTimeout(deb); deb = setTimeout(runValidation, 350); }));
    runValidation();
  }

  // ---------- Utilidades ----------

  function _loadAll() {
    _loadSummary(); _loadConformance(); _loadStatements(); _loadParams();
  }

  return { render };
})();
