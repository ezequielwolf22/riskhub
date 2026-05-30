/* Vista Politicas de Seguridad — ISO 27001 cl. 5.2. */
const ViewPolicies = (() => {

  const STATUS_LABELS = {
    draft: 'Borrador', review: 'En revision', approved: 'Aprobada',
    published: 'Publicada', obsolete: 'Obsoleta',
  };
  const STATUS_COLORS = {
    draft: 'var(--text-muted)', review: 'var(--brand-orange)',
    approved: 'var(--brand-purple)', published: 'var(--risk-low)', obsolete: '#aaa',
  };

  let _users = [];

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Politicas de Seguridad</h1>
          <p class="page-sub">Gestion del ciclo de vida de politicas — ISO 27001 cl. 5.2</p>
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
          <input type="file" id="pol-ai-input" accept=".pdf,.docx,.txt" style="display:none;">
          <button class="btn" id="btn-ai-extract" title="Cargar un documento PDF/DOCX y extraer los campos con IA">
            Extraer con IA
          </button>
          <button onclick="ViewPolicies._generateWithAI()" class="btn" style="background:linear-gradient(90deg,var(--brand-purple),var(--brand-orange));color:#fff;border:none;">
            ✨ Generar con IA
          </button>
          <button class="btn btn-primary" id="btn-new-pol">+ Nueva politica</button>
        </div>
      </div>

      <div class="stats-row" id="pol-stats" style="margin-bottom:16px;"></div>

      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <input type="search" id="pol-search" class="input" style="width:220px;" placeholder="Buscar por titulo...">
        <select id="pol-status" class="input" style="width:160px;">
          <option value="">Todos los estados</option>
          ${Object.entries(STATUS_LABELS).map(([k,l]) => `<option value="${k}">${l}</option>`).join('')}
        </select>
      </div>

      <div id="pol-table-wrap"></div>
    `;

    document.getElementById('btn-new-pol').onclick = () => _openForm(null);
    document.getElementById('pol-search').oninput = _refresh;
    document.getElementById('pol-status').onchange = _refresh;

    // Extraccion IA
    const aiBtn = document.getElementById('btn-ai-extract');
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
        <div class="stat-card"><div class="stat-value">${s.total}</div><div class="stat-label">Total</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-low);">${s.by_status.published||0}</div><div class="stat-label">Publicadas</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.by_status.review||0}</div><div class="stat-label">En revision</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-high);">${s.overdue_review}</div><div class="stat-label">Revision vencida</div></div>
      `;
    } catch (_) {}
  }

  async function _refresh() {
    const q = document.getElementById('pol-search')?.value || '';
    const status = document.getElementById('pol-status')?.value || '';
    const wrap = document.getElementById('pol-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<p class="text-muted">Cargando...</p>';
    try {
      const params = {};
      if (q) params.q = q;
      if (status) params.status = status;
      const data = await Api.policies.list(params);
      _renderTable(wrap, data);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _renderTable(wrap, data) {
    if (!data.length) {
      wrap.innerHTML = '<p class="text-muted" style="margin-top:24px;text-align:center;">No se encontraron politicas.</p>';
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
          <td><b>${UI.esc(p.title)}</b>
            ${p.category ? `<div style="font-size:11px;color:var(--text-muted);">${UI.esc(p.category)}</div>` : ''}
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
          <tr><th>Codigo</th><th>Titulo</th><th>Version</th><th>Estado</th><th>Revision</th><th>Responsable</th><th>Acciones</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;

    wrap.querySelectorAll('tr[data-id]').forEach(tr =>
      tr.onclick = () => { const p = data.find(x => x.id == tr.dataset.id); if (p) _openForm(p); });
    wrap.querySelectorAll('[data-action="edit"]').forEach(btn =>
      btn.onclick = (e) => { e.stopPropagation(); const p = data.find(x => x.id == btn.dataset.id); if (p) _openForm(p); });
    wrap.querySelectorAll('[data-action="del"]').forEach(btn =>
      btn.onclick = async (e) => {
        e.stopPropagation();
        if (!confirm('Eliminar politica?')) return;
        try {
          await Api.policies.del(btn.dataset.id);
          UI.toast('Politica eliminada', 'success');
          await _loadStats(); await _refresh();
        } catch (e2) { UI.toast(e2.message, 'error'); }
      });
  }

  function _formHtml(p, extracted) {
    // Valores: primero los extraidos por IA, luego los del objeto existente, luego defecto
    const v = p || {};
    const e = extracted || {};
    const title = e.title || v.title || '';
    const version = e.version || v.version || '1.0';
    const category = e.category || v.category || '';
    const scope = e.scope || v.scope || '';
    const content = e.content || v.content || '';
    const review = e.review_date || (v.review_date ? v.review_date.slice(0,10) : '');
    const clauses = e.iso_clauses ? e.iso_clauses.join(', ') : (v.iso_clauses||[]).join(', ');
    const notes = e.confidence_notes || '';
    return `
      <div class="form-grid">
        ${notes ? `<div class="span2"><div class="notice" style="margin-bottom:4px;font-size:12px;">Nota IA: ${UI.esc(notes)}</div></div>` : ''}
        <div class="span2"><label>Titulo *</label><input id="f-title" class="input" value="${UI.esc(title)}"></div>
        <div>
          <label>Estado</label>
          <select id="f-status" class="input">
            ${Object.entries(STATUS_LABELS).map(([k,l]) => `<option value="${k}" ${(v.status||'draft')===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div><label>Version</label><input id="f-version" class="input" value="${UI.esc(version)}"></div>
        <div><label>Categoria</label><input id="f-cat" class="input" value="${UI.esc(category)}"></div>
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
      </div>`;
  }

  function _openForm(p, extracted) {
    UI.modal(p ? `Editar ${p.code}` : 'Nueva politica', _formHtml(p, extracted), {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => _save(p);
  }

  async function _save(p) {
    const title = document.getElementById('f-title').value.trim();
    if (!title) { UI.toast('El titulo es obligatorio', 'error'); return; }
    const clausesRaw = document.getElementById('f-clauses').value.trim();
    const ownerVal = document.getElementById('f-owner').value;
    const payload = {
      title,
      version: document.getElementById('f-version').value.trim() || '1.0',
      category: document.getElementById('f-cat').value.trim() || null,
      status: document.getElementById('f-status').value,
      review_date: document.getElementById('f-review').value || null,
      iso_clauses: clausesRaw ? clausesRaw.split(',').map(s => s.trim()).filter(Boolean) : [],
      scope: document.getElementById('f-scope').value.trim(),
      content: document.getElementById('f-content').value.trim(),
      owner_id: ownerVal ? parseInt(ownerVal) : null,
    };
    try {
      if (p) {
        await Api.policies.update(p.id, payload);
        UI.toast('Politica actualizada', 'success');
      } else {
        await Api.policies.create(payload);
        UI.toast('Politica creada', 'success');
      }
      UI.closeModal();
      await _loadStats(); await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  async function _generateWithAI() {
    const templates = await Api.policyTemplates.list().catch(() => []);
    if (!templates.length) { UI.toast('No hay templates disponibles', 'error'); return; }
    const options = templates.map(t => `
      <option value="${UI.esc(t.id)}">${UI.esc(t.title)}</option>`).join('');
    UI.openModal(`
      <h3 style="margin:0 0 16px;color:var(--brand-purple);">Generar política con IA</h3>
      <p style="font-size:13px;color:#666;margin-bottom:12px;">
        Claude generará una política personalizada con el nombre de tu organización,
        activos, amenazas y frameworks activos.
      </p>
      <div style="display:grid;gap:12px;">
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">Template *</label>
          <select id="gen-template" class="input-field" style="width:100%;">${options}</select>
        </div>
        <div>
          <label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">Contexto adicional (opcional)</label>
          <textarea id="gen-context" class="input-field" rows="3" style="width:100%;"
                    placeholder="Ej: empresa de 200 empleados, sector financiero, datos de tarjetas..."></textarea>
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-top:16px;justify-content:flex-end;">
        <button onclick="UI.closeModal()" class="btn-outline">Cancelar</button>
        <button onclick="ViewPolicies._submitGenerate()" class="btn-primary">Generar con IA</button>
      </div>`);
  }

  async function _submitGenerate() {
    const templateId = document.getElementById('gen-template').value;
    const context = document.getElementById('gen-context').value.trim();
    UI.closeModal();
    UI.toast('Generando política con IA...', 'info');
    try {
      const result = await Api.policyTemplates.generate({
        template_id: templateId,
        extra_context: context || null,
      });
      // Mostrar el resultado para que el usuario lo revise antes de guardar
      UI.openModal(`
        <div style="max-width:700px;">
          <h3 style="margin:0 0 8px;color:var(--brand-purple);">Política generada: ${UI.esc(result.title)}</h3>
          <p style="font-size:12px;color:#9d9d9d;margin-bottom:12px;">
            Revisa el contenido antes de guardar. Puedes editarlo.
          </p>
          <textarea id="gen-result-content" style="width:100%;height:350px;font-size:12px;
                    font-family:monospace;border:1px solid #e0e0e0;border-radius:6px;padding:10px;
                    resize:vertical;">${UI.esc(result.content)}</textarea>
          <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end;">
            <button onclick="UI.closeModal()" class="btn-outline">Descartar</button>
            <button onclick="ViewPolicies._saveGenerated(${JSON.stringify(result).replace(/"/g,'&quot;')})"
                    class="btn-primary">Guardar como política</button>
          </div>
        </div>`);
    } catch (e) {
      UI.toast('Error generando: ' + e.message, 'error');
    }
  }

  async function _saveGenerated(result) {
    const content = document.getElementById('gen-result-content').value;
    const payload = {
      title: result.title,
      content: content,
      iso_clauses: result.iso_controls || [],
      scope: 'Generada automáticamente con IA — revisar y adaptar',
      version: '1.0',
      review_cycle_months: 12,
    };
    try {
      await Api.policies.create(payload);
      UI.closeModal();
      UI.toast('Política guardada correctamente', 'success');
      await _loadStats(); await _refresh();
    } catch (e) {
      UI.toast('Error guardando: ' + e.message, 'error');
    }
  }

  return { render, _generateWithAI, _submitGenerate, _saveGenerated };
})();
