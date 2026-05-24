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

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Proveedores y Cadena de Suministro</h1>
          <p class="page-sub">Gestion de riesgo de terceros — NIS2 Art. 21.2.d / ISO 27001 A.15</p>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-primary" id="btn-new-sup">+ Nuevo proveedor</button>
        </div>
      </div>

      <div class="stats-row" id="sup-stats" style="margin-bottom:16px;"></div>

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

    document.getElementById('btn-new-sup').onclick = () => _openForm(null);
    document.getElementById('f-risk').onchange = _refresh;
    let debounce;
    document.getElementById('f-q').oninput = () => { clearTimeout(debounce); debounce = setTimeout(_refresh, 300); };

    await _loadStats();
    await _refresh();
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

  return { render };
})();
