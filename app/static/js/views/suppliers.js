/* Vista de gestion de proveedores / supply chain risk (NIS2 Art. 21.2.d). */
const ViewSuppliers = (() => {

  const RISK_LABELS = {
    low: 'Bajo', medium: 'Medio', high: 'Alto', critical: 'Critico',
  };
  const RISK_COLORS = {
    low: 'var(--risk-low)', medium: 'var(--risk-medium)',
    high: 'var(--risk-high)', critical: 'var(--risk-critical)',
  };

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  let _activeSupTab = 'suppliers';

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Proveedores y Cadena de Suministro</h1>
          <p class="page-sub">Gestion de riesgo de terceros — NIS2 Art. 21.2.d / ISO 27001 A.15</p>
        </div>
        <div style="display:flex;gap:8px;" id="sup-header-actions"></div>
      </div>

      <div class="stats-row" id="sup-stats" style="margin-bottom:16px;"></div>

      <div style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:16px;">
        <button class="tab-btn" id="suptab-suppliers" onclick="SupTab('suppliers')">Proveedores</button>
        <button class="tab-btn" id="suptab-questionnaires" onclick="SupTab('questionnaires')">Cuestionarios de seguridad</button>
      </div>
      <div id="sup-tab-content"></div>
    `;

    window.SupTab = function(t) { _setSupTab(t); };

    await _loadStats();
    _setSupTab(_activeSupTab);
  }

  function _setSupTab(tab) {
    _activeSupTab = tab;
    ['suppliers','questionnaires'].forEach(t => {
      const btn = document.getElementById('suptab-' + t);
      if (!btn) return;
      btn.style.cssText = `padding:8px 20px;font-size:13px;font-weight:600;border:none;
        background:none;cursor:pointer;border-bottom:3px solid ${t===tab?'var(--brand-purple)':'transparent'};
        color:${t===tab?'var(--brand-purple)':'var(--text-muted)'};margin-bottom:-2px;`;
    });
    // Update header action button
    const actions = document.getElementById('sup-header-actions');
    if (actions) {
      if (tab === 'suppliers') {
        actions.innerHTML = '<button class="btn btn-primary" id="btn-new-sup">+ Nuevo proveedor</button>';
        document.getElementById('btn-new-sup').onclick = () => _openForm(null);
      } else {
        actions.innerHTML = Auth.canEdit() ? '<button class="btn btn-primary" id="btn-new-seq">+ Nuevo cuestionario</button>' : '';
        if (Auth.canEdit()) document.getElementById('btn-new-seq').onclick = () => _openSeqForm(null);
      }
    }
    if (tab === 'suppliers') _renderSuppliersTab();
    else _renderQuestionnairesTab();
  }

  async function _renderSuppliersTab() {
    const wrap = document.getElementById('sup-tab-content');
    wrap.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <select id="f-risk" class="input" style="width:160px;">
          <option value="">Todos los niveles</option>
          <option value="critical">Critico</option>
          <option value="high">Alto</option>
          <option value="medium">Medio</option>
          <option value="low">Bajo</option>
        </select>
        <input id="f-q" class="input" placeholder="Buscar..." style="width:200px;">
      </div>
      <div id="sup-table-wrap"></div>
    `;
    document.getElementById('f-risk').onchange = _refresh;
    let debounce;
    document.getElementById('f-q').oninput = () => { clearTimeout(debounce); debounce = setTimeout(_refresh, 300); };
    await _refresh();
  }
  }

  async function _loadStats() {
    try {
      const s = await Api.suppliers.summary();
      const wrap = document.getElementById('sup-stats');
      if (!wrap) return;
      wrap.innerHTML = `
        <div class="stat-card"><div class="stat-value">${s.total}</div><div class="stat-label">Total proveedores</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-critical);">${s.critical_or_high}</div><div class="stat-label">Criticos / Altos</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.overdue_assessment}</div><div class="stat-label">Evaluacion vencida</div></div>
      `;
    } catch (_) {}
  }

  async function _refresh() {
    const riskLevel = document.getElementById('f-risk')?.value || '';
    const q = document.getElementById('f-q')?.value.trim() || '';
    const wrap = document.getElementById('sup-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<p class="text-muted">Cargando...</p>';
    try {
      const params = {};
      if (riskLevel) params.risk_level = riskLevel;
      if (q) params.q = q;
      const data = await Api.suppliers.list(params);
      _renderTable(wrap, data);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _renderTable(wrap, data) {
    if (!data.length) {
      wrap.innerHTML = '<p class="text-muted" style="margin-top:24px;text-align:center;">No se encontraron proveedores.</p>';
      return;
    }
    const rows = data.map(s => {
      const assessed = s.last_assessment_at ? s.last_assessment_at.slice(0, 10) : '-';
      const next = s.next_assessment_at ? s.next_assessment_at.slice(0, 10) : '-';
      return `
        <tr>
          <td><b>${UI.esc(s.code)}</b></td>
          <td>${UI.esc(s.name)}</td>
          <td>${UI.esc(s.category || '-')}</td>
          <td>${_badge(RISK_LABELS[s.risk_level] || s.risk_level, RISK_COLORS[s.risk_level] || '#888')}</td>
          <td>${assessed}</td>
          <td>${next}</td>
          <td>${s.is_critical ? '<span style="color:var(--risk-critical);font-weight:700;">Si</span>' : '<span style="color:var(--text-muted);">No</span>'}</td>
          <td>
            <button class="btn btn-sm" data-id="${s.id}" data-action="edit">Editar</button>
            <button class="btn btn-sm btn-danger" data-id="${s.id}" data-action="del">Eliminar</button>
          </td>
        </tr>
      `;
    }).join('');

    wrap.innerHTML = `
      <table class="data">
        <thead>
          <tr>
            <th>Codigo</th><th>Nombre</th><th>Categoria</th><th>Nivel riesgo</th>
            <th>Ult. evaluacion</th><th>Prox. evaluacion</th><th>Critico</th><th>Acciones</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;

    wrap.querySelectorAll('[data-action="edit"]').forEach(btn => {
      btn.onclick = () => {
        const sup = data.find(s => s.id == btn.dataset.id);
        if (sup) _openForm(sup);
      };
    });
    wrap.querySelectorAll('[data-action="del"]').forEach(btn => {
      btn.onclick = async () => {
        if (!confirm('Eliminar proveedor?')) return;
        try {
          await Api.suppliers.del(btn.dataset.id);
          UI.toast('Proveedor eliminado', 'success');
          await _loadStats();
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });
  }

  function _formHtml(s) {
    const v = s || {};
    return `
      <div class="form-grid">
        <div><label>Nombre *</label><input id="f-name" class="input" value="${UI.esc(v.name || '')}"></div>
        <div><label>Categoria</label><input id="f-cat" class="input" value="${UI.esc(v.category || '')}" placeholder="Software, Hardware, Servicios..."></div>
        <div><label>Nivel de riesgo</label>
          <select id="f-risk-level" class="input">
            ${Object.entries(RISK_LABELS).map(([k,l]) => `<option value="${k}" ${v.risk_level===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="checkbox" id="f-critical" ${v.is_critical?'checked':''}>
          <label for="f-critical" style="margin:0;cursor:pointer;">Proveedor critico NIS2</label>
        </div>
        <div><label>Contacto</label><input id="f-contact" class="input" value="${UI.esc(v.contact_name || '')}"></div>
        <div><label>Email contacto</label><input id="f-email" class="input" type="email" value="${UI.esc(v.contact_email || '')}"></div>
        <div><label>Ultima evaluacion</label><input type="date" id="f-last-assess" class="input" value="${v.last_assessment_at ? v.last_assessment_at.slice(0,10) : ''}"></div>
        <div><label>Proxima evaluacion</label><input type="date" id="f-next-assess" class="input" value="${v.next_assessment_at ? v.next_assessment_at.slice(0,10) : ''}"></div>
        <div class="span2"><label>Contrato / referencia</label><input id="f-contract" class="input" value="${UI.esc(v.contract_ref || '')}"></div>
        <div class="span2"><label>Notas / descripcion</label><textarea id="f-notes" class="input" rows="3">${UI.esc(v.notes || '')}</textarea></div>
      </div>
    `;
  }

  function _openForm(s) {
    UI.modal(s ? `Editar ${s.code}` : 'Nuevo proveedor', _formHtml(s), {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => _save(s);
  }

  async function _save(s) {
    const name = document.getElementById('f-name').value.trim();
    if (!name) { UI.toast('El nombre es obligatorio', 'error'); return; }
    const payload = {
      name,
      category: document.getElementById('f-cat').value.trim(),
      risk_level: document.getElementById('f-risk-level').value,
      is_critical: document.getElementById('f-critical').checked,
      contact_name: document.getElementById('f-contact').value.trim(),
      contact_email: document.getElementById('f-email').value.trim(),
      last_assessment_at: document.getElementById('f-last-assess').value || null,
      next_assessment_at: document.getElementById('f-next-assess').value || null,
      contract_ref: document.getElementById('f-contract').value.trim(),
      notes: document.getElementById('f-notes').value.trim(),
    };
    try {
      if (s) {
        await Api.suppliers.update(s.id, payload);
        UI.toast('Proveedor actualizado', 'success');
      } else {
        await Api.suppliers.create(payload);
        UI.toast('Proveedor creado', 'success');
      }
      UI.closeModal();
      await _loadStats();
      await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  // ======== QUESTIONNAIRES TAB ========

  async function _renderQuestionnairesTab() {
    const wrap = document.getElementById('sup-tab-content');
    wrap.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">
        <select id="seq-sup-filter" class="input" style="width:220px;">
          <option value="">Todos los proveedores</option>
        </select>
      </div>
      <div id="seq-list">Cargando...</div>
    `;
    // Populate supplier filter
    try {
      const sups = await Api.suppliers.list();
      const sel = document.getElementById('seq-sup-filter');
      if (sel) sups.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.code + ' - ' + s.name;
        sel.appendChild(opt);
      });
    } catch (_) {}
    document.getElementById('seq-sup-filter').onchange = _reloadSeq;
    await _reloadSeq();
  }

  async function _reloadSeq() {
    const supId = document.getElementById('seq-sup-filter')?.value;
    const params = {};
    if (supId) params.supplier_id = supId;
    const wrap = document.getElementById('seq-list');
    if (!wrap) return;
    try {
      const data = await Api.supplier_questionnaires.list(params);
      if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);margin-top:24px;text-align:center;">Sin cuestionarios enviados. Crea uno para enviar el enlace publico al proveedor.</p>';
        return;
      }
      const now = new Date();
      wrap.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          <th>Codigo</th><th>Titulo</th><th>Proveedor</th><th>Puntuacion</th><th>Respondido</th><th>Expira</th><th></th>
        </tr></thead>
        <tbody>
          ${data.map(q => {
            const submitted = q.submitted_at ? new Date(q.submitted_at).toLocaleDateString('es-ES') : null;
            const expired = q.expires_at && new Date(q.expires_at) < now && !q.submitted_at;
            const expires = q.expires_at ? new Date(q.expires_at).toLocaleDateString('es-ES') : '-';
            let scoreHtml = '-';
            if (q.score !== null && q.score !== undefined) {
              const sc = q.score;
              const color = sc >= 80 ? '#22C55E' : sc >= 60 ? '#F59E0B' : '#EF4444';
              scoreHtml = `<span style="font-weight:700;color:${color};">${sc}/100</span>`;
            }
            return `<tr style="${expired?'opacity:.6;':''}">
              <td>${UI.codePill(q.code)}</td>
              <td><strong>${UI.esc(q.title)}</strong></td>
              <td style="font-size:12px;">${UI.esc(q.supplier_name||'-')}</td>
              <td>${scoreHtml}</td>
              <td style="font-size:12px;">${submitted ? submitted : (expired ? '<span style="color:#EF4444;font-size:11px;">Expirado</span>' : '<span style="color:#F59E0B;font-size:11px;">Pendiente</span>')}</td>
              <td style="font-size:12px;">${expires}</td>
              <td>
                <button class="btn btn-sm" data-id="${q.id}" data-act="link" title="Copiar enlace publico">Copiar enlace</button>
                ${Auth.canEdit() && !q.submitted_at ? `<button class="btn btn-sm btn-danger" data-id="${q.id}" data-act="del">Eliminar</button>` : ''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
      wrap.querySelectorAll('[data-act="link"]').forEach(btn => {
        btn.onclick = () => {
          const q = data.find(x => x.id == btn.dataset.id);
          if (!q) return;
          const link = location.origin + '/supplier-q?token=' + encodeURIComponent(q.token);
          navigator.clipboard.writeText(link).then(() => UI.toast('Enlace copiado al portapapeles', 'success'))
            .catch(() => {
              UI.modal('Enlace publico del cuestionario', `
                <div class="span2">
                  <p style="font-size:13px;margin-bottom:8px;">Copia y comparte este enlace con el proveedor:</p>
                  <input style="width:100%;font-size:12px;font-family:monospace;" value="${UI.esc(link)}" readonly onclick="this.select()">
                </div>
              `, { actions: '<button class="btn btn-primary" id="m-cancel">Cerrar</button>' });
              document.getElementById('m-cancel').onclick = UI.closeModal;
            });
        };
      });
      wrap.querySelectorAll('[data-act="del"]').forEach(btn => {
        btn.onclick = async () => {
          if (!await UI.confirm('Eliminar este cuestionario?')) return;
          try { await Api.supplier_questionnaires.del(btn.dataset.id); UI.toast('Eliminado','success'); _reloadSeq(); }
          catch (e) { UI.toast(e.message,'error'); }
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  async function _openSeqForm() {
    let suppliers = [];
    try { suppliers = await Api.suppliers.list(); } catch (_) {}
    UI.modal('Nuevo cuestionario de seguridad', `
      <div><label>Proveedor *</label>
        <select id="sq-sup">
          <option value="">- Seleccionar -</option>
          ${suppliers.map(s => `<option value="${s.id}">${UI.esc(s.code)} - ${UI.esc(s.name)}</option>`).join('')}
        </select>
      </div>
      <div><label>Titulo *</label>
        <input id="sq-title" value="Evaluacion de seguridad NIS2/ISO 27001">
      </div>
      <div><label>Fecha de expiracion</label>
        <input type="date" id="sq-expires" value="${new Date(Date.now()+30*86400000).toISOString().slice(0,10)}">
      </div>
      <div class="span2"><label>Notas internas</label>
        <textarea id="sq-notes" rows="2" placeholder="Notas para el equipo interno (no visibles para el proveedor)"></textarea>
      </div>
      <div class="span2 notice">
        Se enviaran 10 preguntas estandar NIS2 Art.21 + ISO 27001. Tras crear el cuestionario, copia el enlace publico para enviarlo al proveedor.
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Crear y obtener enlace</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const supId = document.getElementById('sq-sup').value;
      const title = document.getElementById('sq-title').value.trim();
      if (!supId) { UI.toast('Selecciona un proveedor','error'); return; }
      if (!title) { UI.toast('El titulo es obligatorio','error'); return; }
      const expires = document.getElementById('sq-expires').value;
      const body = {
        supplier_id: parseInt(supId),
        title,
        expires_at: expires || null,
        notes: document.getElementById('sq-notes').value.trim(),
      };
      try {
        const q = await Api.supplier_questionnaires.create(body);
        UI.closeModal();
        const link = location.origin + '/supplier-q?token=' + encodeURIComponent(q.token);
        navigator.clipboard.writeText(link).catch(() => {});
        UI.modal('Cuestionario creado', `
          <div class="span2">
            <p style="font-size:13px;margin-bottom:4px;">Cuestionario <strong>${UI.esc(q.code)}</strong> creado correctamente.</p>
            <p style="font-size:13px;margin-bottom:8px;">Enlace publico copiado al portapapeles. Comparte este enlace con el proveedor:</p>
            <input style="width:100%;font-size:12px;font-family:monospace;" value="${UI.esc(link)}" readonly onclick="this.select()">
            <p style="font-size:12px;color:var(--text-muted);margin-top:8px;">El enlace expira el ${new Date(q.expires_at).toLocaleDateString('es-ES')}.</p>
          </div>
        `, { actions: '<button class="btn btn-primary" id="m-ok">Entendido</button>' });
        document.getElementById('m-ok').onclick = UI.closeModal;
        _reloadSeq();
      } catch (e) { UI.toast(e.message,'error'); }
    };
  }

  return { render };
})();
