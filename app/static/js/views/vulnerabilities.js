/* Vista Vulnerabilidades - catálogo ISO 27005 Annex D. */
const ViewVulns = {
  async render(main) {
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      'Catálogo de vulnerabilidades',
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
          <option value="site">Instalaciónes</option>
          <option value="organization">Organización</option>
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
      if (!data.length) {
        list.innerHTML = UI.emptyState('Sin resultados', 'Ajusta los filtros.');
        return;
      }
      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr><th>Codigo</th><th>Nombre</th><th>Categoria</th><th>Amenazas relaciónadas</th><th></th></tr></thead>
        <tbody>
          ${data.map(v => `
            <tr>
              <td>${UI.codePill(v.code)}</td>
              <td><strong>${UI.esc(v.name)}</strong>
                  ${v.description ? `<div style="font-size:11px;color:var(--text-subtle);">${UI.esc(v.description)}</div>` : ''}</td>
              <td>${UI.esc(v.category||'-')}</td>
              <td style="font-size:11px;font-family:var(--font-mono);">${(v.related_threats||[]).join(', ')||'-'}</td>
              <td>${v.is_custom ? '<span class="badge badge-muted">Custom</span>' : '<span class="badge" style="background:var(--brand-purple-4);color:var(--brand-purple);">ISO</span>'}</td>
            </tr>`).join('')}
        </tbody>
      </table></div>`;
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _edit() {
    UI.modal('Nueva vulnerabilidad personalizada', `
      <div><label>Codigo (vacio para auto)</label><input id="f-code"></div>
      <div><label>Categoria *</label>
        <select id="f-cat">
          <option value="hardware">Hardware</option>
          <option value="software">Software</option>
          <option value="network">Red</option>
          <option value="personnel">Personal</option>
          <option value="site">Instalaciónes</option>
          <option value="organization">Organización</option>
        </select>
      </div>
      <div class="span2"><label>Nombre *</label><input id="f-name"></div>
      <div class="span2"><label>Descripción</label><textarea id="f-desc" rows="2"></textarea></div>
      <div class="span2"><label>Amenazas relaciónadas (codigos separados por coma)</label>
        <input id="f-rel" placeholder="T.CYB.01, T.UNA.04"></div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      try {
        await Api.vulns.create({
          code: document.getElementById('f-code').value || undefined,
          name: document.getElementById('f-name').value,
          description: document.getElementById('f-desc').value,
          category: document.getElementById('f-cat').value,
          related_threats: document.getElementById('f-rel').value.split(',')
                             .map(s=>s.trim()).filter(Boolean),
        });
        UI.closeModal(); UI.toast('Vulnerabilidad creada', 'success'); ViewVulns._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },
};
