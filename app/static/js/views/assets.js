/* Vista Activos: CRUD + import/export CSV. */
const ViewAssets = {
  async render(main) {
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      'Inventario de activos',
      'Activos primarios y de soporte (ISO 27005 Annex B)',
      canEdit ? `
        <button class="btn" id="btn-export">Exportar CSV</button>
        <button class="btn" id="btn-template">Plantilla</button>
        <label class="btn">
          Importar CSV
          <input type="file" id="file-import" accept=".csv,.xlsx" style="display:none;">
        </label>
        <button class="btn btn-primary" id="btn-new">+ Nuevo activo</button>
      ` : ''
    ) + `
      <div class="toolbar">
        <input type="search" id="asset-search" placeholder="Buscar por nombre o codigo...">
        <select id="asset-type-filter">
          <option value="">Todos los tipos</option>
          <option value="primary_process">Proceso</option>
          <option value="primary_information">Información</option>
          <option value="support_hardware">Hardware</option>
          <option value="support_software">Software</option>
          <option value="support_network">Red</option>
          <option value="support_personnel">Personal</option>
          <option value="support_site">Instalación</option>
          <option value="support_organization">Organización</option>
        </select>
        <span class="spacer"></span>
        <span id="asset-count" style="color:var(--text-subtle);font-size:12px;"></span>
      </div>
      <div id="asset-list"></div>
    `;

    document.getElementById('asset-search').oninput =
      () => ViewAssets._reload();
    document.getElementById('asset-type-filter').onchange =
      () => ViewAssets._reload();

    if (canEdit) {
      document.getElementById('btn-new').onclick = () => ViewAssets._edit();
      document.getElementById('btn-template').onclick = () => Api.assets.template();
      document.getElementById('btn-export').onclick = () => Api.assets.exportCsv();
      document.getElementById('file-import').onchange = async (e) => {
        const f = e.target.files[0]; if (!f) return;
        try {
          const r = await Api.assets.import(f);
          UI.toast(`Importación: ${r.created} creados, ${r.updated} actualizados, ${r.skipped} omitidos`,
                   r.errors.length ? 'error' : 'success');
          ViewAssets._reload();
        } catch (err) { UI.toast(err.message, 'error'); }
        finally { e.target.value = ''; }
      };
    }

    ViewAssets._reload();
  },

  async _reload() {
    const q = document.getElementById('asset-search').value;
    const t = document.getElementById('asset-type-filter').value;
    const list = document.getElementById('asset-list');
    list.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      const params = {};
      if (q) params.q = q;
      if (t) params.asset_type = t;
      const data = await Api.assets.list(params);
      document.getElementById('asset-count').textContent = `${data.length} activos`;
      if (!data.length) {
        list.innerHTML = UI.emptyState(
          'Sin activos',
          'Crea uno nuevo o importa el inventario desde un CSV.'
        );
        return;
      }
      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead>
          <tr>
            <th>Codigo</th><th>Nombre</th><th>Tipo</th>
            <th>C</th><th>I</th><th>D</th><th>Auth</th><th>Acc</th><th>Max</th>
            <th>Categoria</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${data.map(a => `
            <tr data-id="${a.id}">
              <td>${UI.codePill(a.code)}</td>
              <td><strong>${UI.esc(a.name)}</strong>
                  ${a.description ? `<div style="font-size:11px;color:var(--text-subtle);">${UI.esc(a.description).slice(0,80)}</div>` : ''}</td>
              <td>${UI.assetTypeLabel(a.asset_type)}</td>
              <td>${a.value_confidentiality}</td>
              <td>${a.value_integrity}</td>
              <td>${a.value_availability}</td>
              <td>${a.value_authenticity}</td>
              <td>${a.value_accountability}</td>
              <td>${UI.riskPill(a.value_max * 2)}</td>
              <td>${UI.esc(a.category || '-')}</td>
              <td>${Auth.canEdit() ? `<button class="btn btn-ghost" data-edit="${a.id}">Editar</button>` : ''}</td>
            </tr>`).join('')}
        </tbody>
      </table></div>`;

      list.querySelectorAll('[data-edit]').forEach(b =>
        b.onclick = () => ViewAssets._edit(parseInt(b.dataset.edit)));
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  async _edit(id) {
    let a = { name: '', asset_type: 'support_hardware', description: '',
              category: '', location: '', business_process: '', classification: '',
              value_confidentiality: 0, value_integrity: 0, value_availability: 0,
              value_authenticity: 0, value_accountability: 0 };
    if (id) {
      try { a = await Api.assets.get(id); }
      catch (e) { UI.toast(e.message, 'error'); return; }
    }
    UI.modal(id ? `Editar ${a.code}` : 'Nuevo activo', `
      <div class="span2">
        <label>Nombre *</label>
        <input id="f-name" value="${UI.esc(a.name)}" required>
      </div>
      <div>
        <label>Tipo *</label>
        <select id="f-type">
          ${['primary_process','primary_information','support_hardware','support_software',
             'support_network','support_personnel','support_site','support_organization'].map(t =>
            `<option value="${t}" ${a.asset_type===t?'selected':''}>${UI.assetTypeLabel(t)}</option>`).join('')}
        </select>
      </div>
      <div>
        <label>Categoria</label>
        <input id="f-cat" value="${UI.esc(a.category||'')}">
      </div>
      <div class="span2">
        <label>Descripción</label>
        <textarea id="f-desc" rows="2">${UI.esc(a.description||'')}</textarea>
      </div>
      <div>
        <label>Localización</label>
        <input id="f-loc" value="${UI.esc(a.location||'')}">
      </div>
      <div>
        <label>Proceso de negocio</label>
        <input id="f-proc" value="${UI.esc(a.business_process||'')}">
      </div>
      <div>
        <label>Clasificación</label>
        <select id="f-class">
          ${['','Publico','Interno','Confidencial','Secreto'].map(c =>
            `<option value="${c}" ${a.classification===c?'selected':''}>${c||'-'}</option>`).join('')}
        </select>
      </div>
      <div class="span2"><label>Valoración (0-4)</label></div>
      ${['confidentiality','integrity','availability','authenticity','accountability'].map(d =>
        `<div>
           <label>${({confidentiality:'Confidencialidad',integrity:'Integridad',availability:'Disponibilidad',authenticity:'Autenticidad',accountability:'Trazabilidad'})[d]}</label>
           <input type="number" min="0" max="4" id="f-${d}" value="${a['value_'+d]||0}">
         </div>`).join('')}
    `, {
      actions: `
        <button class="btn" id="m-cancel">Cancelar</button>
        ${id ? `<button class="btn btn-danger" id="m-del">Eliminar</button>` : ''}
        <button class="btn btn-primary" id="m-save">Guardar</button>`
    });

    document.getElementById('m-cancel').onclick = UI.closeModal;
    if (id) document.getElementById('m-del').onclick = async () => {
      if (!await UI.confirm('Eliminar este activo?')) return;
      try { await Api.assets.del(id); UI.closeModal(); UI.toast('Eliminado','success'); ViewAssets._reload(); }
      catch (e) { UI.toast(e.message, 'error'); }
    };
    document.getElementById('m-save').onclick = async () => {
      const body = {
        name: document.getElementById('f-name').value,
        asset_type: document.getElementById('f-type').value,
        description: document.getElementById('f-desc').value,
        category: document.getElementById('f-cat').value,
        location: document.getElementById('f-loc').value,
        business_process: document.getElementById('f-proc').value,
        classification: document.getElementById('f-class').value,
      };
      ['confidentiality','integrity','availability','authenticity','accountability']
        .forEach(d => body['value_'+d] = parseInt(document.getElementById('f-'+d).value) || 0);
      try {
        if (id) await Api.assets.update(id, body);
        else await Api.assets.create(body);
        UI.closeModal(); UI.toast('Guardado', 'success'); ViewAssets._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },
};
