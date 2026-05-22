/* Vista Amenazas - catálogo ISO 27005 Annex C. */
const ViewThreats = {
  async render(main) {
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      'Catálogo de amenazas',
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

      // Popular filtro de categorias
      const catSelect = document.getElementById('t-category');
      if (catSelect.options.length === 1) {
        const cats = [...new Set(data.map(t => t.category).filter(Boolean))].sort();
        cats.forEach(c => catSelect.add(new Option(c, c)));
      }

      if (!data.length) {
        list.innerHTML = UI.emptyState('Sin amenazas', 'No se encontraron resultados.');
        return;
      }
      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr><th>Codigo</th><th>Nombre</th><th>Origen</th><th>Categoria</th><th>Afecta</th><th>Aplica a</th><th></th></tr></thead>
        <tbody>
          ${data.map(t => `
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
              <td>${t.is_custom ? '<span class="badge badge-muted">Custom</span>' : '<span class="badge" style="background:var(--brand-purple-4);color:var(--brand-purple);">ISO</span>'}</td>
            </tr>`).join('')}
        </tbody>
      </table></div>`;
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _edit() {
    UI.modal('Nueva amenaza personalizada', `
      <div><label>Codigo (vacio para auto)</label><input id="f-code"></div>
      <div><label>Origen *</label>
        <select id="f-origin">
          <option value="D">Deliberada</option>
          <option value="A">Accidental</option>
          <option value="E">Ambiental</option>
        </select>
      </div>
      <div class="span2"><label>Nombre *</label><input id="f-name"></div>
      <div class="span2"><label>Descripción</label><textarea id="f-desc" rows="2"></textarea></div>
      <div><label>Categoria</label><input id="f-cat" placeholder="Compromise of information"></div>
      <div><label>Afecta a (separado por coma)</label><input id="f-affects" placeholder="C, I, A"></div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      try {
        await Api.threats.create({
          code: document.getElementById('f-code').value || undefined,
          name: document.getElementById('f-name').value,
          description: document.getElementById('f-desc').value,
          category: document.getElementById('f-cat').value,
          origin: document.getElementById('f-origin').value,
          affects: document.getElementById('f-affects').value.split(',')
                     .map(s=>s.trim()).filter(Boolean),
          typical_assets: [],
        });
        UI.closeModal(); UI.toast('Amenaza creada','success'); ViewThreats._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },
};
