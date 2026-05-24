/* Vista Vulnerabilidades - catalogo ISO 27005 Annex D. */
const ViewVulns = {
  _sortCol: 'code', _sortAsc: true,

  async render(main) {
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      'Catalogo de vulnerabilidades',
      'ISO/IEC 27005:2018 Annex D + vulnerabilidades personalizadas',
      canEdit ? '<button class="btn btn-primary" id="btn-new">+ Nueva vulnerabilidad</button>' : ''
    ) + `
      <div class="toolbar">
        <input type="search" id="v-search" placeholder="Buscar...">
        <select id="v-cat">
          <option value="">Todas</option>
          <option value="hardware">Hardware</option>
          <option value="software">Software</option>
          <option value="network">Red</option>
          <option value="personnel">Personal</option>
          <option value="site">Instalaciones</option>
          <option value="organization">Organizacion</option>
        </select>
      </div>
      <div id="v-list"></div>
    `;
    if (canEdit) document.getElementById('btn-new').onclick = () => ViewVulns._edit();
    document.getElementById('v-search').oninput = () => ViewVulns._reload();
    document.getElementById('v-cat').onchange = () => ViewVulns._reload();
    ViewVulns._reload();
  },

  async _reload() {
    const q = document.getElementById('v-search').value;
    const cat = document.getElementById('v-cat').value;
    const list = document.getElementById('v-list');
    list.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      const params = {};
      if (q) params.q = q;
      if (cat) params.category = cat;
      const data = await Api.vulns.list(params);
      const canEdit = Auth.canEdit();
      if (!data.length) {
        list.innerHTML = UI.emptyState('Sin resultados', 'Ajusta los filtros.');
        return;
      }

      // Client-side sort
      const _sv = v => {
        const k = ViewVulns._sortCol;
        if (k === 'code') return v.code || '';
        if (k === 'name') return (v.name || '').toLowerCase();
        if (k === 'category') return (v.category || '').toLowerCase();
        if (k === 'risks') return v.risk_count || 0;
        return '';
      };
      data.sort((a, b) => {
        const va = _sv(a), vb = _sv(b);
        const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
        return ViewVulns._sortAsc ? cmp : -cmp;
      });
      const _th = (col, label, style) => {
        const active = ViewVulns._sortCol === col;
        const arrow = active ? (ViewVulns._sortAsc ? ' ▲' : ' ▼') : '';
        return `<th style="cursor:pointer;user-select:none;${active?'color:var(--brand-purple);':''}${style||''}"
                    data-sort="${col}">${label}${arrow}</th>`;
      };

      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          ${_th('code','Codigo')}${_th('name','Nombre')}${_th('category','Categoria')}
          <th>Amenazas relacionadas</th>
          ${_th('risks','Riesgos','width:70px;text-align:center;')}<th></th>
        </tr></thead>
        <tbody>
          ${data.map(v => {
            const rc = v.risk_count || 0;
            const rcColor = rc === 0 ? 'var(--text-subtle)' : rc >= 5 ? 'var(--risk-high)' : 'var(--brand-purple)';
            return `
            <tr>
              <td>${UI.codePill(v.code)}</td>
              <td><strong>${UI.esc(v.name)}</strong>
                  ${v.description ? `<div style="font-size:11px;color:var(--text-subtle);">${UI.esc(v.description)}</div>` : ''}</td>
              <td>${UI.esc(v.category||'-')}</td>
              <td style="font-size:11px;font-family:var(--font-mono);">${(v.related_threats||[]).join(', ')||'-'}</td>
              <td style="text-align:center;font-weight:700;font-family:var(--font-mono);font-size:13px;color:${rcColor};">${rc}</td>
              <td style="white-space:nowrap;">
                ${v.is_custom
                  ? `<span class="badge badge-muted">Custom</span>
                     ${canEdit ? `
                       <button class="btn btn-sm" style="margin-left:4px;"
                         onclick="ViewVulns._edit(${JSON.stringify(v).replace(/"/g,'&quot;')})">Editar</button>
                       <button class="btn btn-sm btn-danger" style="margin-left:2px;"
                         onclick="ViewVulns._del(${v.id},'${UI.esc(v.name)}')">Eliminar</button>
                     ` : ''}
                  `
                  : '<span class="badge" style="background:var(--brand-purple-4);color:var(--brand-purple);">ISO</span>'
                }
              </td>
            </tr>`;}).join('')}
        </tbody>
      </table></div>`;
      list.querySelectorAll('th[data-sort]').forEach(th => {
        th.onclick = () => {
          const col = th.dataset.sort;
          if (ViewVulns._sortCol === col) ViewVulns._sortAsc = !ViewVulns._sortAsc;
          else { ViewVulns._sortCol = col; ViewVulns._sortAsc = col !== 'risks'; }
          ViewVulns._reload();
        };
      });
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _edit(v) {
    const isNew = !v;
    UI.modal(isNew ? 'Nueva vulnerabilidad personalizada' : 'Editar vulnerabilidad personalizada', `
      <div><label>Codigo (vacio para auto)</label>
        <input id="f-code" value="${isNew ? '' : UI.esc(v.code)}"></div>
      <div><label>Categoria *</label>
        <select id="f-cat">
          <option value="hardware" ${!isNew && v.category==='hardware' ? 'selected':''}>Hardware</option>
          <option value="software" ${!isNew && v.category==='software' ? 'selected':''}>Software</option>
          <option value="network" ${!isNew && v.category==='network' ? 'selected':''}>Red</option>
          <option value="personnel" ${!isNew && v.category==='personnel' ? 'selected':''}>Personal</option>
          <option value="site" ${!isNew && v.category==='site' ? 'selected':''}>Instalaciones</option>
          <option value="organization" ${!isNew && v.category==='organization' ? 'selected':''}>Organizacion</option>
        </select>
      </div>
      <div class="span2"><label>Nombre *</label>
        <input id="f-name" value="${isNew ? '' : UI.esc(v.name)}"></div>
      <div class="span2"><label>Descripcion</label>
        <textarea id="f-desc" rows="2">${isNew ? '' : UI.esc(v.description||'')}</textarea></div>
      <div class="span2"><label>Amenazas relacionadas (codigos separados por coma)</label>
        <input id="f-rel" placeholder="T.CYB.01, T.UNA.04"
          value="${isNew ? '' : (v.related_threats||[]).join(', ')}"></div>
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
        related_threats: document.getElementById('f-rel').value.split(',')
                           .map(s=>s.trim()).filter(Boolean),
      };
      try {
        if (isNew) {
          await Api.vulns.create(payload);
          UI.toast('Vulnerabilidad creada', 'success');
        } else {
          await Api.vulns.update(v.id, payload);
          UI.toast('Vulnerabilidad actualizada', 'success');
        }
        UI.closeModal(); ViewVulns._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  async _del(id, name) {
    if (!confirm(`Eliminar la vulnerabilidad personalizada "${name}"?`)) return;
    try {
      await Api.vulns.del(id);
      UI.toast('Vulnerabilidad eliminada', 'success');
      ViewVulns._reload();
    } catch (e) { UI.toast(e.message, 'error'); }
  },
};
