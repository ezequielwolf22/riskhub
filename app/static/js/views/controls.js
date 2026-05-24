/* Vista Controles - catálogo ISO 27002:2022 + implementaciónes. */
const ViewControls = {
  _tab: 'impls', _catalog: [],

  async render(main) {
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      'Controles de seguridad',
      'ISO/IEC 27002:2022 (93 controles del Anexo A)',
      canEdit ? '<button class="btn btn-primary" id="btn-new-impl">+ Nueva implementación</button>' : ''
    ) + `
      <div class="toolbar">
        <button class="btn ${ViewControls._tab==='impls'?'btn-primary':''}" data-tab="impls">Implementaciónes</button>
        <button class="btn ${ViewControls._tab==='catalog'?'btn-primary':''}" data-tab="catalog">Catálogo ISO 27002:2022</button>
        <span class="spacer"></span>
        <input type="search" id="c-search" placeholder="Buscar...">
        <select id="c-theme">
          <option value="">Todos los temas</option>
          <option value="organizational">Organizaciónal</option>
          <option value="people">Personas</option>
          <option value="physical">Fisico</option>
          <option value="technological">Tecnológico</option>
        </select>
        <button class="btn btn-ghost" id="btn-soa-csv" title="Exportar SoA como CSV">SoA CSV</button>
      </div>
      <div id="c-list"></div>
    `;

    document.querySelectorAll('.toolbar [data-tab]').forEach(b => b.onclick = () => {
      ViewControls._tab = b.dataset.tab;
      ViewControls.render(main);
    });
    document.getElementById('c-search').oninput = () => ViewControls._reload();
    document.getElementById('c-theme').onchange = () => ViewControls._reload();
    if (canEdit) document.getElementById('btn-new-impl').onclick = () => ViewControls._editImpl();
    document.getElementById('btn-soa-csv').onclick = async () => {
      try { await Api.controls.exportSoaCsv(); UI.toast('SoA CSV descargado', 'success'); }
      catch (e) { UI.toast(e.message, 'error'); }
    };

    ViewControls._catalog = await Api.controls.list({});
    ViewControls._reload();
  },

  async _reload() {
    const list = document.getElementById('c-list');
    list.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      if (ViewControls._tab === 'catalog') {
        await ViewControls._renderCatalog();
      } else {
        await ViewControls._renderImpls();
      }
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  async _renderCatalog() {
    const q = document.getElementById('c-search').value.toLowerCase();
    const theme = document.getElementById('c-theme').value;
    const list = document.getElementById('c-list');
    let data = ViewControls._catalog;
    if (q) data = data.filter(c => (c.name + c.code).toLowerCase().includes(q));
    if (theme) data = data.filter(c => c.theme === theme);

    list.innerHTML = `<div class="table-wrap"><table class="data">
      <thead><tr><th>Codigo</th><th>Nombre</th><th>Tema</th><th>Tipo</th><th>Propiedades</th></tr></thead>
      <tbody>
        ${data.map(c => `
          <tr>
            <td>${UI.codePill(c.code)}</td>
            <td><strong>${UI.esc(c.name)}</strong>
                ${c.description ? `<div style="font-size:11px;color:var(--text-subtle);">${UI.esc(c.description)}</div>` : ''}</td>
            <td>${UI.esc(c.theme||'-')}</td>
            <td style="font-size:11px;">${(c.control_type||[]).join(', ')}</td>
            <td style="font-size:11px;font-family:var(--font-mono);">${(c.properties||[]).map(p => p[0].toUpperCase()).join(' ')}</td>
          </tr>`).join('')}
      </tbody>
    </table></div>`;
  },

  async _renderImpls() {
    const list = document.getElementById('c-list');
    const data = await Api.impls.list();
    if (!data.length) {
      list.innerHTML = UI.emptyState(
        'Sin implementaciónes',
        'Crea implementaciónes concretas de los controles para poder asociarlos a riesgos.'
      );
      return;
    }
    const now = new Date();
    const overdueCount = data.filter(i =>
      i.next_review && new Date(i.next_review) < now && i.status !== 'not_implemented').length;
    list.innerHTML = `
      ${overdueCount ? `<div style="background:#FEF9C3;border:1px solid #FDE68A;border-radius:6px;padding:10px 14px;font-size:13px;color:#92400E;margin-bottom:12px;">
        <strong>${overdueCount} control${overdueCount>1?'es':''}</strong> con revision pendiente (fecha proxima revision vencida).
      </div>` : ''}
      <div class="table-wrap"><table class="data">
      <thead><tr><th>Control</th><th>Implementación</th><th>Estado</th><th>Madurez</th><th>Proxima revisión</th><th></th></tr></thead>
      <tbody>
        ${data.map(i => {
          const reviewOverdue = i.next_review && new Date(i.next_review) < now
            && i.status !== 'not_implemented';
          return `<tr data-id="${i.id}" style="cursor:pointer;${reviewOverdue?'background:rgba(254,249,195,0.5);':''}">
            <td>${UI.codePill(i.control.code)} <span style="font-size:11px;color:var(--text-subtle);">${UI.esc(i.control.name).slice(0,40)}</span></td>
            <td><strong>${UI.esc(i.name)}</strong></td>
            <td>${UI.controlStatusLabel(i.status)}</td>
            <td>${ViewControls._maturityBar(i.maturity)}</td>
            <td style="font-size:12px;">${i.next_review
              ? `<span style="color:${reviewOverdue?'var(--risk-high)':'inherit'};font-weight:${reviewOverdue?'700':'400'};">${new Date(i.next_review).toLocaleDateString()}</span>${reviewOverdue?' <span style="font-size:10px;background:#FEF9C3;color:#92400E;border-radius:3px;padding:1px 4px;">REVISION</span>':''}`
              : '-'}</td>
            <td>${Auth.canEdit() ? `<button class="btn btn-ghost" data-edit="${i.id}">Editar</button>` : ''}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table></div>`;
    list.querySelectorAll('[data-edit]').forEach(b =>
      b.onclick = (e) => { e.stopPropagation(); ViewControls._editImpl(parseInt(b.dataset.edit)); });
    list.querySelectorAll('tr[data-id]').forEach(tr =>
      tr.onclick = () => ViewControls._editImpl(parseInt(tr.dataset.id)));
  },

  _maturityBar(level) {
    const bars = Array.from({length: 5}, (_, i) =>
      `<div style="width:12px;height:8px;border-radius:2px;background:${
        i < level ? 'var(--brand-purple)' : 'var(--bg-3)'};"></div>`).join('');
    return `<div style="display:flex;gap:3px;align-items:center;">
      ${bars}<span style="font-family:var(--font-mono);font-size:11px;margin-left:4px;color:var(--text-muted);">${level}/5</span></div>`;
  },

  async _editImpl(id) {
    let data = { control_id: ViewControls._catalog[0]?.id, name: '', description: '',
                 status: 'not_implemented', maturity: 0, notes: '', evidence: '' };
    if (id) {
      const all = await Api.impls.list();
      data = all.find(x => x.id === id) || data;
      data.control_id = data.control?.id || data.control_id;
    }
    UI.modal(id ? `Editar implementación ${id}` : 'Nueva implementación', `
      <div class="span2">
        <label>Control de referencia *</label>
        <select id="f-control">
          ${ViewControls._catalog.map(c =>
            `<option value="${c.id}" ${data.control_id===c.id?'selected':''}>${UI.esc(c.code)} - ${UI.esc(c.name)}</option>`).join('')}
        </select>
      </div>
      <div class="span2"><label>Nombre de la implementación *</label>
        <input id="f-name" value="${UI.esc(data.name)}" placeholder="ej. EDR CrowdStrike en endpoints corporativos"></div>
      <div class="span2"><label>Descripción</label>
        <textarea id="f-desc" rows="2">${UI.esc(data.description||'')}</textarea></div>
      <div><label>Estado</label>
        <select id="f-status">
          ${['planned','implemented','partial','not_implemented'].map(s =>
            `<option value="${s}" ${data.status===s?'selected':''}>${UI.controlStatusLabel(s)}</option>`).join('')}
        </select>
      </div>
      <div><label>Madurez (0-5)</label>
        <input type="number" min="0" max="5" id="f-mat" value="${data.maturity||0}"></div>
      <div><label>Ultima revision</label>
        <input type="date" id="f-last-rev" value="${data.last_review ? data.last_review.slice(0,10) : ''}"></div>
      <div><label>Proxima revision</label>
        <input type="date" id="f-next-rev" value="${data.next_review ? data.next_review.slice(0,10) : ''}"></div>
      <div class="span2"><label>Evidencia / referencia documental</label>
        <textarea id="f-evi" rows="2">${UI.esc(data.evidence||'')}</textarea></div>
      <div class="span2"><label>Notas</label>
        <textarea id="f-notes" rows="2">${UI.esc(data.notes||'')}</textarea></div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                ${id ? '<button class="btn btn-danger" id="m-del">Eliminar</button>' : ''}
                <button class="btn btn-primary" id="m-save">Guardar</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    if (id) document.getElementById('m-del').onclick = async () => {
      if (!await UI.confirm('Eliminar esta implementación?')) return;
      try { await Api.impls.del(id); UI.closeModal(); UI.toast('Eliminado','success'); ViewControls._reload(); }
      catch (e) { UI.toast(e.message, 'error'); }
    };
    document.getElementById('m-save').onclick = async () => {
      const lastRev = document.getElementById('f-last-rev').value;
      const nextRev = document.getElementById('f-next-rev').value;
      const body = {
        control_id: parseInt(document.getElementById('f-control').value),
        name: document.getElementById('f-name').value,
        description: document.getElementById('f-desc').value,
        status: document.getElementById('f-status').value,
        maturity: parseInt(document.getElementById('f-mat').value)||0,
        last_review: lastRev || null,
        next_review: nextRev || null,
        evidence: document.getElementById('f-evi').value,
        notes: document.getElementById('f-notes').value,
      };
      try {
        if (id) await Api.impls.update(id, body);
        else await Api.impls.create(body);
        UI.closeModal(); UI.toast('Guardado','success'); ViewControls._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },
};
