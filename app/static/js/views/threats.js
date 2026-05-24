/* Vista Amenazas - catalogo ISO 27005 Annex C. */
const ViewThreats = {
  _sortCol: 'code', _sortAsc: true,

  async render(main) {
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      'Catalogo de amenazas',
      'ISO/IEC 27005:2018 Annex C + amenazas personalizadas',
      canEdit ? '<button class="btn btn-primary" id="btn-new">+ Nueva amenaza</button>' : ''
    ) + `
      <div class="toolbar">
        <input type="search" id="t-search" placeholder="Buscar...">
        <select id="t-category">
          <option value="">Todas las categorias</option>
        </select>
      </div>
      <div id="t-list"></div>
    `;
    if (canEdit) document.getElementById('btn-new').onclick = () => ViewThreats._edit();
    document.getElementById('t-search').oninput = () => ViewThreats._reload();
    document.getElementById('t-category').onchange = () => ViewThreats._reload();
    ViewThreats._reload();
  },

  async _reload() {
    const q = document.getElementById('t-search').value;
    const cat = document.getElementById('t-category').value;
    const list = document.getElementById('t-list');
    list.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      const params = {};
      if (q) params.q = q;
      if (cat) params.category = cat;
      const data = await Api.threats.list(params);
      const canEdit = Auth.canEdit();

      // Popular filtro de categorias (solo la primera vez)
      const catSelect = document.getElementById('t-category');
      if (catSelect.options.length === 1) {
        const cats = [...new Set(data.map(t => t.category).filter(Boolean))].sort();
        cats.forEach(c => catSelect.add(new Option(c, c)));
      }

      if (!data.length) {
        list.innerHTML = UI.emptyState('Sin amenazas', 'No se encontraron resultados.');
        return;
      }

      // Client-side sort
      const _sv = t => {
        const k = ViewThreats._sortCol;
        if (k === 'code') return t.code || '';
        if (k === 'name') return (t.name || '').toLowerCase();
        if (k === 'origin') return t.origin || '';
        if (k === 'category') return (t.category || '').toLowerCase();
        if (k === 'risks') return t.risk_count || 0;
        return '';
      };
      data.sort((a, b) => {
        const va = _sv(a), vb = _sv(b);
        const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
        return ViewThreats._sortAsc ? cmp : -cmp;
      });
      const _th = (col, label, style) => {
        const active = ViewThreats._sortCol === col;
        const arrow = active ? (ViewThreats._sortAsc ? ' ▲' : ' ▼') : '';
        return `<th style="cursor:pointer;user-select:none;${active?'color:var(--brand-purple);':''}${style||''}"
                    data-sort="${col}">${label}${arrow}</th>`;
      };

      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          ${_th('code','Codigo')}${_th('name','Nombre')}${_th('origin','Origen')}
          ${_th('category','Categoria')}<th>Afecta</th><th>Aplica a</th>
          ${_th('risks','Riesgos','width:70px;text-align:center;')}<th></th>
        </tr></thead>
        <tbody>
          ${data.map(t => {
            const rc = t.risk_count || 0;
            const rcColor = rc === 0 ? 'var(--text-subtle)' : rc >= 5 ? 'var(--risk-high)' : 'var(--brand-purple)';
            return `
            <tr>
              <td>${UI.codePill(t.code)}</td>
              <td>
                <strong>${UI.esc(t.name)}</strong>
                ${t.description ? `<div style="font-size:11px;color:var(--text-subtle);">${UI.esc(t.description)}</div>` : ''}
              </td>
              <td>${UI.threatOriginLabel(t.origin)}</td>
              <td>${UI.esc(t.category||'-')}</td>
              <td>${(t.affects||[]).join(', ')||'-'}</td>
              <td style="font-size:11px;color:var(--text-subtle);">${(t.typical_assets||[]).map(UI.assetTypeLabel).join(', ')||'-'}</td>
              <td style="text-align:center;">
                <a href="#/risks?threat_id=${t.id}" title="Ver riesgos de esta amenaza"
                   style="font-weight:700;font-family:var(--font-mono);font-size:13px;
                          color:${rcColor};text-decoration:none;">${rc}</a>
              </td>
              <td style="white-space:nowrap;">
                ${t.is_custom
                  ? `<span class="badge badge-muted">Custom</span>
                     ${canEdit ? `
                       <button class="btn btn-sm" style="margin-left:4px;"
                         onclick="ViewThreats._edit(${JSON.stringify(t).replace(/"/g,'&quot;')})">Editar</button>
                       <button class="btn btn-sm btn-danger" style="margin-left:2px;"
                         onclick="ViewThreats._del(${t.id},'${UI.esc(t.name)}')">Eliminar</button>
                     ` : ''}
                  `
                  : '<span class="badge" style="background:var(--brand-purple-4);color:var(--brand-purple);">ISO</span>'
                }
              </td>
            </tr>`; }).join('')}
        </tbody>
      </table></div>`;
      list.querySelectorAll('th[data-sort]').forEach(th => {
        th.onclick = () => {
          const col = th.dataset.sort;
          if (ViewThreats._sortCol === col) ViewThreats._sortAsc = !ViewThreats._sortAsc;
          else { ViewThreats._sortCol = col; ViewThreats._sortAsc = col !== 'risks'; }
          ViewThreats._reload();
        };
      });
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _edit(t) {
    const isNew = !t;
    UI.modal(isNew ? 'Nueva amenaza personalizada' : 'Editar amenaza personalizada', `
      <div><label>Codigo (vacio para auto)</label>
        <input id="f-code" value="${isNew ? '' : UI.esc(t.code)}"></div>
      <div><label>Origen *</label>
        <select id="f-origin">
          <option value="D" ${(!isNew && t.origin==='D')||isNew ? 'selected':''}>Deliberada</option>
          <option value="A" ${!isNew && t.origin==='A' ? 'selected':''}>Accidental</option>
          <option value="E" ${!isNew && t.origin==='E' ? 'selected':''}>Ambiental</option>
        </select>
      </div>
      <div class="span2"><label>Nombre *</label>
        <input id="f-name" value="${isNew ? '' : UI.esc(t.name)}"></div>
      <div class="span2"><label>Descripcion</label>
        <textarea id="f-desc" rows="2">${isNew ? '' : UI.esc(t.description||'')}</textarea></div>
      <div><label>Categoria</label>
        <input id="f-cat" placeholder="Compromise of information"
          value="${isNew ? '' : UI.esc(t.category||'')}"></div>
      <div><label>Afecta a (separado por coma)</label>
        <input id="f-affects" placeholder="C, I, A"
          value="${isNew ? '' : (t.affects||[]).join(', ')}"></div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const payload = {
        code: document.getElementById('f-code').value || undefined,
        name: document.getElementById('f-name').value,
        description: document.getElementById('f-desc').value,
        category: document.getElementById('f-cat').value,
        origin: document.getElementById('f-origin').value,
        affects: document.getElementById('f-affects').value.split(',').map(s=>s.trim()).filter(Boolean),
        typical_assets: isNew ? [] : (t.typical_assets||[]),
      };
      try {
        if (isNew) {
          await Api.threats.create(payload);
          UI.toast('Amenaza creada', 'success');
        } else {
          await Api.threats.update(t.id, payload);
          UI.toast('Amenaza actualizada', 'success');
        }
        UI.closeModal(); ViewThreats._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  async _del(id, name) {
    if (!confirm(`Eliminar la amenaza personalizada "${name}"?`)) return;
    try {
      await Api.threats.del(id);
      UI.toast('Amenaza eliminada', 'success');
      ViewThreats._reload();
    } catch (e) { UI.toast(e.message, 'error'); }
  },
};
