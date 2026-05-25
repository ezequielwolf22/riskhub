/* Vista Activos: CRUD + import/export CSV. */
const ViewAssets = {
  _sortCol: 'code', _sortAsc: true,

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
      // Client-side sort
      const _sortVal = a => {
        const k = ViewAssets._sortCol;
        if (k === 'code') return a.code || '';
        if (k === 'name') return (a.name || '').toLowerCase();
        if (k === 'type') return a.asset_type || '';
        if (k === 'value_max') return a.value_max || 0;
        if (k === 'risks') return a.risk_count || 0;
        if (k === 'category') return (a.category || '').toLowerCase();
        return '';
      };
      data.sort((a, b) => {
        const va = _sortVal(a), vb = _sortVal(b);
        const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
        return ViewAssets._sortAsc ? cmp : -cmp;
      });

      const _th = (col, label, title, style) => {
        const active = ViewAssets._sortCol === col;
        const arrow = active ? (ViewAssets._sortAsc ? ' ▲' : ' ▼') : '';
        return `<th style="cursor:pointer;user-select:none;white-space:nowrap;${active?'color:var(--brand-purple);':''}${style||''}"
                    data-sort="${col}" title="${title||label}">${label}${arrow}</th>`;
      };

      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead>
          <tr>
            ${_th('code','Codigo')}${_th('name','Nombre')}${_th('type','Tipo')}
            <th>C</th><th>I</th><th>D</th><th>Auth</th><th>Acc</th>${_th('value_max','Max','Valor maximo CIA')}
            ${_th('category','Categoria')}${_th('risks','Riesgos','Numero de riesgos asociados','width:80px;text-align:center;')}<th></th>
          </tr>
        </thead>
        <tbody>
          ${data.map(a => {
            const rc = a.risk_count || 0;
            const rcColor = rc === 0 ? 'var(--text-subtle)' : rc >= 5 ? 'var(--risk-high)' : 'var(--brand-purple)';
            return `
            <tr data-id="${a.id}" style="cursor:pointer;">
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
              <td style="text-align:center;">
                <a href="#/risks?asset_id=${a.id}" title="Ver riesgos de este activo"
                   style="font-weight:700;font-family:var(--font-mono);font-size:13px;
                          color:${rcColor};text-decoration:none;">${rc}</a>
              </td>
              <td style="white-space:nowrap;" onclick="event.stopPropagation()">
                ${Auth.canEdit() ? `<button class="btn btn-ghost" data-edit="${a.id}">Editar</button>` : ''}
              </td>
            </tr>`;}).join('')}
        </tbody>
      </table></div>`;

      list.querySelectorAll('th[data-sort]').forEach(th => {
        th.onclick = () => {
          const col = th.dataset.sort;
          if (ViewAssets._sortCol === col) ViewAssets._sortAsc = !ViewAssets._sortAsc;
          else { ViewAssets._sortCol = col; ViewAssets._sortAsc = col !== 'value_max' && col !== 'risks'; }
          ViewAssets._reload();
        };
      });
      list.querySelectorAll('[data-edit]').forEach(b =>
        b.onclick = (e) => { e.stopPropagation(); ViewAssets._edit(parseInt(b.dataset.edit)); });
      list.querySelectorAll('tr[data-id]').forEach(tr =>
        tr.onclick = () => ViewAssets._edit(parseInt(tr.dataset.id)));
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  async _edit(id) {
    let a = { name: '', asset_type: 'support_hardware', description: '',
              category: '', location: '', business_process: '', classification: '',
              monetary_value: '', value_confidentiality: 0, value_integrity: 0,
              value_availability: 0, value_authenticity: 0, value_accountability: 0 };
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
      <div>
        <label>Valor monetario (EUR, FAIR/ALE)</label>
        <input type="number" min="0" step="1000" id="f-monetary" value="${a.monetary_value || ''}" placeholder="ej. 50000">
      </div>
      <div class="span2"><label>Valoración CIA (0-4)</label></div>
      ${['confidentiality','integrity','availability','authenticity','accountability'].map(d =>
        `<div>
           <label>${({confidentiality:'Confidencialidad',integrity:'Integridad',availability:'Disponibilidad',authenticity:'Autenticidad',accountability:'Trazabilidad'})[d]}</label>
           <input type="number" min="0" max="4" id="f-${d}" value="${a['value_'+d]||0}">
         </div>`).join('')}
      ${id ? `
      <div class="span2">
        <details id="asset-history">
          <summary style="cursor:pointer;font-size:13px;color:var(--text-muted);padding:6px 0;
                          list-style:none;display:flex;align-items:center;gap:6px;">
            <span style="font-size:10px;">&#9654;</span> Historial de cambios
          </summary>
          <div id="asset-history-body" style="margin-top:8px;">
            <div class="notice">Cargando...</div>
          </div>
        </details>
      </div>` : ''}
    `, {
      actions: `
        <button class="btn" id="m-cancel">Cancelar</button>
        ${id ? `<button class="btn btn-danger" id="m-del">Eliminar</button>` : ''}
        ${id ? `<button class="btn btn-ghost" id="m-ai-suggest" title="Sugerir riesgos basados en amenazas ISO 27005">IA: Sugerir riesgos</button>` : ''}
        <button class="btn btn-primary" id="m-save">Guardar</button>`
    });

    document.getElementById('m-cancel').onclick = UI.closeModal;

    // Historial de cambios (lazy-load al expandir)
    if (id) {
      const det = document.getElementById('asset-history');
      if (det) {
        det.addEventListener('toggle', async () => {
          if (!det.open) return;
          const body = document.getElementById('asset-history-body');
          try {
            const entries = await Api.audit.history('asset', id);
            if (!entries.length) {
              body.innerHTML = '<p style="font-size:12px;color:var(--text-subtle);">Sin registros de cambio todavia.</p>';
              return;
            }
            const actionColors = { create:'background:#D1FAE5;color:#065F46', update:'background:#DBEAFE;color:#1E40AF', delete:'background:#FEE2E2;color:#991B1B' };
            body.innerHTML = entries.map(e => {
              const ts = new Date(e.timestamp).toLocaleString('es-ES', { day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit' });
              const style = actionColors[e.action] || 'background:var(--bg-3);color:var(--text-muted)';
              const detail = e.detail && Object.keys(e.detail).length
                ? Object.entries(e.detail).map(([k,v]) => `${UI.esc(k)}: ${UI.esc(String(v))}`).join(' · ') : '';
              return `<div style="display:flex;gap:8px;align-items:flex-start;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px;">
                <span style="color:var(--text-subtle);white-space:nowrap;min-width:110px;">${ts}</span>
                <span class="badge badge-muted" style="${style};font-size:10px;">${UI.esc(e.action)}</span>
                <span style="color:var(--text-muted);">${UI.esc(e.user_name||e.user_email||'')}</span>
                ${detail ? `<span style="color:var(--text-subtle);">${detail}</span>` : ''}
              </div>`;
            }).join('');
          } catch (_) { body.innerHTML = '<p style="font-size:12px;color:var(--text-subtle);">No disponible.</p>'; }
        }, { once: true });
      }
    }

    if (id) document.getElementById('m-del').onclick = async () => {
      if (!await UI.confirm('Eliminar este activo?')) return;
      try { await Api.assets.del(id); UI.closeModal(); UI.toast('Eliminado','success'); ViewAssets._reload(); }
      catch (e) { UI.toast(e.message, 'error'); }
    };

    // Boton IA: sugerir riesgos para este activo
    if (id) {
      const aiBtn = document.getElementById('m-ai-suggest');
      if (aiBtn) aiBtn.onclick = async () => {
        aiBtn.disabled = true; aiBtn.textContent = 'Analizando...';
        try {
          const result = await Api.ai.riskSuggest({ asset_id: id });
          const suggestions = result.suggestions || result.risks || result || [];
          if (!suggestions.length) {
            UI.toast('No se encontraron sugerencias de riesgo para este activo.', 'info');
            aiBtn.disabled = false; aiBtn.textContent = 'IA: Sugerir riesgos';
            return;
          }
          UI.modal('Sugerencias de riesgo — IA', `
            <div class="span2">
              <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;">
                Basado en el tipo de activo y el catalogo ISO 27005, el sistema identifica los escenarios de riesgo mas probables.
              </p>
              <div style="display:flex;flex-direction:column;gap:8px;">
                ${suggestions.map(s => `
                  <div style="padding:10px 14px;border:1px solid var(--border);border-radius:6px;background:var(--bg-2);">
                    <div style="font-weight:600;font-size:13px;">${UI.esc(s.threat_name || s.threat || '')}</div>
                    ${s.description ? `<div style="font-size:12px;color:var(--text-muted);margin-top:3px;">${UI.esc(s.description)}</div>` : ''}
                    ${s.likelihood !== undefined ? `<div style="font-size:11px;margin-top:4px;color:var(--text-subtle);">Probabilidad estimada: ${s.likelihood}/4 &nbsp;|&nbsp; Impacto: ${s.consequence || s.impact || '-'}/4</div>` : ''}
                  </div>`).join('')}
              </div>
            </div>
          `, { actions: '<button class="btn btn-primary" id="m-close-ai">Cerrar</button>' });
          document.getElementById('m-close-ai').onclick = UI.closeModal;
        } catch (e) {
          UI.toast('Error al consultar IA: ' + e.message, 'error');
          aiBtn.disabled = false; aiBtn.textContent = 'IA: Sugerir riesgos';
        }
      };
    }

    document.getElementById('m-save').onclick = async () => {
      const monetaryRaw = document.getElementById('f-monetary').value;
      const body = {
        name: document.getElementById('f-name').value,
        asset_type: document.getElementById('f-type').value,
        description: document.getElementById('f-desc').value,
        category: document.getElementById('f-cat').value,
        location: document.getElementById('f-loc').value,
        business_process: document.getElementById('f-proc').value,
        classification: document.getElementById('f-class').value,
        monetary_value: monetaryRaw ? parseFloat(monetaryRaw) : null,
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
