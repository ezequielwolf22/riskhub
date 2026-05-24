/* Vista Riesgos - identificación, analisis, evaluación, tratamiento. */
const ViewRisks = {
  _assets: [], _threats: [], _vulns: [], _impls: [],
  _assetFilter: null, // { id, name } cuando se filtra por activo desde la vista de activos

  async render(main) {
    const canEdit = Auth.canEdit();

    // Leer parametros de URL
    const assetMatch = location.hash.match(/[?&]asset_id=(\d+)/);
    const overdueParam = /[?&]overdue=1/.test(location.hash);
    ViewRisks._assetFilter = null;

    main.innerHTML = UI.sectionHeader(
      'Registro de riesgos',
      'ISO/IEC 27005:2018 cl. 8-9 — identificación, análisis, tratamiento',
      canEdit ? '<button class="btn btn-primary" id="btn-new">+ Nuevo riesgo</button>' : ''
    ) + `
      <div class="toolbar">
        <input type="search" id="r-search" placeholder="Buscar por activo o amenaza...">
        <select id="r-status">
          <option value="">Cualquier estado</option>
          <option value="identified">Identificado</option>
          <option value="assessed">Evaluado</option>
          <option value="treated">Tratado</option>
          <option value="accepted">Aceptado</option>
          <option value="closed">Cerrado</option>
        </select>
        <select id="r-band">
          <option value="">Cualquier nivel</option>
          <option value="6">Solo altos (6+)</option>
          <option value="3">Medios y altos (3+)</option>
        </select>
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;white-space:nowrap;">
          <input type="checkbox" id="r-overdue"> Solo vencidos
        </label>
        <button class="btn btn-ghost" id="r-export-csv" title="Exportar tabla como CSV" style="margin-left:auto;">Exportar CSV</button>
      </div>
      <div id="r-asset-filter" style="display:none;margin-bottom:8px;"></div>
      <div id="r-list"></div>
    `;
    if (canEdit) document.getElementById('btn-new').onclick = () => ViewRisks._edit();
    document.getElementById('r-search').oninput = () => ViewRisks._reload();
    document.getElementById('r-status').onchange = () => ViewRisks._reload();
    document.getElementById('r-band').onchange = () => ViewRisks._reload();
    document.getElementById('r-overdue').onchange = () => ViewRisks._reload();
    document.getElementById('r-export-csv').onclick = async () => {
      try { await Api.risks.exportCsv(); UI.toast('CSV descargado', 'success'); }
      catch (e) { UI.toast(e.message, 'error'); }
    };

    // Precargar catálogos en memoria
    await ViewRisks._loadCatalogs();

    // Aplicar filtro de activo si viene de URL
    if (assetMatch) {
      const assetId = parseInt(assetMatch[1]);
      const asset = ViewRisks._assets.find(a => a.id === assetId);
      if (asset) {
        ViewRisks._assetFilter = { id: assetId, name: asset.name };
        const filterDiv = document.getElementById('r-asset-filter');
        filterDiv.style.display = 'block';
        filterDiv.innerHTML = `<div style="background:var(--brand-purple-4);border-left:3px solid var(--brand-purple);
                                            border-radius:0 6px 6px 0;padding:8px 14px;font-size:13px;
                                            display:flex;justify-content:space-between;align-items:center;">
          <span>Mostrando riesgos del activo: <strong>${UI.esc(asset.name)}</strong></span>
          <button class="btn btn-sm" onclick="ViewRisks._clearAssetFilter()">Quitar filtro</button>
        </div>`;
      }
    }

    // Pre-marcar checkbox de vencidos si viene de la URL
    if (overdueParam) {
      const cb = document.getElementById('r-overdue');
      if (cb) cb.checked = true;
    }

    await ViewRisks._reload();

    // Atajo desde heatmap: ?id=X
    const m = location.hash.match(/[?&]id=(\d+)/);
    if (m) ViewRisks._edit(parseInt(m[1]));
  },

  _clearAssetFilter() {
    ViewRisks._assetFilter = null;
    document.getElementById('r-asset-filter').style.display = 'none';
    location.hash = '#/risks';
    ViewRisks._reload();
  },

  async _loadCatalogs() {
    try {
      const [a, t, v, i] = await Promise.all([
        Api.assets.list({}), Api.threats.list({}),
        Api.vulns.list({}), Api.impls.list(),
      ]);
      ViewRisks._assets = a;
      ViewRisks._threats = t;
      ViewRisks._vulns = v;
      ViewRisks._impls = i;
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  async _reload() {
    const search = document.getElementById('r-search').value.toLowerCase();
    const status = document.getElementById('r-status').value;
    const band = document.getElementById('r-band').value;
    const list = document.getElementById('r-list');
    list.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      const overdue = document.getElementById('r-overdue')?.checked;
      const params = {};
      if (status) params.status = status;
      if (band) params.min_level = band;
      if (ViewRisks._assetFilter) params.asset_id = ViewRisks._assetFilter.id;
      if (overdue) params.overdue = true;
      let data = await Api.risks.list(params);
      if (search) {
        data = data.filter(r =>
          (r.asset && r.asset.name.toLowerCase().includes(search)) ||
          (r.threat && r.threat.name.toLowerCase().includes(search)) ||
          r.code.toLowerCase().includes(search));
      }
      if (!data.length) {
        list.innerHTML = UI.emptyState(
          'Sin riesgos',
          'Crea uno asociando un activo con una amenaza, o ajusta los filtros.');
        return;
      }
      const now = new Date();
      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead>
          <tr>
            <th>Codigo</th><th>Activo</th><th>Amenaza</th>
            <th>Inh.</th><th>Res.</th><th title="Reduccion inherente → residual">Red.</th>
            <th>Estado</th><th>Tratamiento</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${data.map(r => {
            const red = r.inherent_level > 0
              ? Math.round((1 - r.residual_level / r.inherent_level) * 100) : 0;
            const redColor = red > 0 ? 'var(--risk-low)' : red < 0 ? 'var(--risk-high)' : 'var(--text-muted)';
            const isOverdue = r.treatment_due_date
              && new Date(r.treatment_due_date) < now
              && r.status !== 'treated' && r.status !== 'accepted' && r.status !== 'closed';
            return `<tr data-id="${r.id}" style="cursor:pointer;${isOverdue?'background:rgba(254,226,226,0.4);':''}">
              <td>${UI.codePill(r.code)}</td>
              <td><strong>${UI.esc(r.asset?.name||'-')}</strong></td>
              <td>${UI.esc(r.threat?.name||'-')}</td>
              <td>${UI.riskPill(r.inherent_level)}</td>
              <td>${UI.riskPill(r.residual_level)}</td>
              <td style="font-size:12px;font-weight:700;color:${redColor};white-space:nowrap;">${red > 0 ? '-' : red < 0 ? '+' : ''}${Math.abs(red)}%</td>
              <td>${UI.statusLabel(r.status)}${isOverdue ? ' <span title="Fecha de tratamiento vencida" style="font-size:10px;font-weight:700;color:var(--risk-high);background:#FEE2E2;border-radius:3px;padding:1px 4px;margin-left:4px;">VENCIDO</span>' : ''}</td>
              <td>${UI.treatmentLabel(r.treatment_option)}</td>
              <td><button class="btn btn-ghost" data-edit="${r.id}">Ver</button></td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
      list.querySelectorAll('[data-edit]').forEach(b =>
        b.onclick = (e) => { e.stopPropagation(); ViewRisks._edit(parseInt(b.dataset.edit)); });
      list.querySelectorAll('tr[data-id]').forEach(tr =>
        tr.onclick = () => ViewRisks._edit(parseInt(tr.dataset.id)));
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  async _edit(id) {
    let r = {
      asset_id: ViewRisks._assets[0]?.id, threat_id: ViewRisks._threats[0]?.id,
      description: '', consequence_description: '',
      inherent_likelihood: 2, inherent_consequence: 2,
      residual_likelihood: 2, residual_consequence: 2,
      vulnerability_ids: [], control_implementation_ids: [],
      status: 'assessed', treatment_option: '', treatment_plan: '',
      acceptance_justification: '',
    };
    if (id) {
      try {
        r = await Api.risks.get(id);
        r.vulnerability_ids = (r.vulnerabilities || []).map(v => v.id);
        r.control_implementation_ids = (r.controls || []).map(c => c.id);
      } catch (e) { UI.toast(e.message, 'error'); return; }
    }

    const canEdit = Auth.canEdit();

    UI.modal(id ? `${r.code} - ${r.asset?.name || ''}` : 'Nuevo riesgo', `
      <div class="span2 notice">
        Riesgo = combinación de un Activo y una Amenaza. El nivel se calcula como
        Consecuencia x Probabilidad (matriz 5x5 ISO 27005 Annex E.2).
      </div>
      <div>
        <label>Activo *</label>
        <select id="f-asset" ${id?'disabled':''}>
          ${ViewRisks._assets.map(a => `<option value="${a.id}" ${r.asset_id===a.id?'selected':''}>${UI.esc(a.code)} - ${UI.esc(a.name)}</option>`).join('')}
        </select>
      </div>
      <div>
        <label>Amenaza *</label>
        <select id="f-threat" ${id?'disabled':''}>
          ${ViewRisks._threats.map(t => `<option value="${t.id}" ${r.threat_id===t.id?'selected':''}>${UI.esc(t.code)} - ${UI.esc(t.name)}</option>`).join('')}
        </select>
      </div>
      <div class="span2">
        <label>Descripción del escenario</label>
        <textarea id="f-desc" rows="2">${UI.esc(r.description||'')}</textarea>
      </div>
      <div class="span2">
        <label>Consecuencias esperadas</label>
        <textarea id="f-cons" rows="2">${UI.esc(r.consequence_description||'')}</textarea>
      </div>
      <div>
        <label>Probabilidad inherente (0-4)</label>
        <input type="number" min="0" max="4" id="f-il" value="${r.inherent_likelihood}">
      </div>
      <div>
        <label>Consecuencia inherente (0-4)</label>
        <input type="number" min="0" max="4" id="f-ic" value="${r.inherent_consequence}">
      </div>
      <div class="span2">
        <label>Vulnerabilidades asociadas (multi-selección)</label>
        <select id="f-vulns" multiple size="5" style="height:auto;">
          ${ViewRisks._vulns.map(v => `<option value="${v.id}" ${r.vulnerability_ids?.includes(v.id)?'selected':''}>${UI.esc(v.code)} - ${UI.esc(v.name)}</option>`).join('')}
        </select>
      </div>
      <div class="span2">
        <label>Controles implementados que mitigan (multi-selección)</label>
        <select id="f-impls" multiple size="5" style="height:auto;">
          ${ViewRisks._impls.map(c => `<option value="${c.id}" ${r.control_implementation_ids?.includes(c.id)?'selected':''}>${UI.esc(c.name)} (madurez ${c.maturity}/5, ${UI.controlStatusLabel(c.status)})</option>`).join('')}
        </select>
      </div>
      <div>
        <label>Estado</label>
        <select id="f-status">
          ${['identified','assessed','treated','accepted','closed'].map(s =>
            `<option value="${s}" ${r.status===s?'selected':''}>${UI.statusLabel(s)}</option>`).join('')}
        </select>
      </div>
      <div>
        <label>Decisión de tratamiento</label>
        <select id="f-treat">
          <option value="">-</option>
          ${['modification','retention','avoidance','sharing'].map(t =>
            `<option value="${t}" ${r.treatment_option===t?'selected':''}>${UI.treatmentLabel(t)}</option>`).join('')}
        </select>
      </div>
      <div class="span2">
        <label>Plan de tratamiento</label>
        <textarea id="f-plan" rows="2">${UI.esc(r.treatment_plan||'')}</textarea>
      </div>
      <div class="span2">
        <label>Justificación de aceptación (si aplica)</label>
        <textarea id="f-just" rows="2">${UI.esc(r.acceptance_justification||'')}</textarea>
      </div>
      ${id ? `
      <div class="span2 notice ${r.residual_level <= 2 ? '' : 'notice-warn'}">
        Nivel inherente actual: <strong>${r.inherent_level}</strong> -
        Nivel residual actual: <strong>${r.residual_level}</strong>
        ${r.accepted_at ? `<br>Aceptado el ${r.accepted_at}` : ''}
      </div>
      <div class="span2">
        <details id="risk-history">
          <summary style="cursor:pointer;font-size:13px;color:var(--text-muted);padding:6px 0;
                          list-style:none;display:flex;align-items:center;gap:6px;">
            <span style="font-size:10px;">&#9654;</span> Historial de cambios
          </summary>
          <div id="risk-history-body" style="margin-top:8px;">
            <div class="notice">Cargando historial...</div>
          </div>
        </details>
      </div>` : ''}
    `, {
      actions: canEdit ? `
        <button class="btn" id="m-cancel">Cerrar</button>
        ${id ? '<button class="btn btn-danger" id="m-del">Eliminar</button>' : ''}
        <button class="btn btn-primary" id="m-save">Guardar</button>
      ` : '<button class="btn" id="m-cancel">Cerrar</button>'
    });

    document.getElementById('m-cancel').onclick = UI.closeModal;

    // Cargar historial de cambios al expandir el <details>
    if (id) {
      const details = document.getElementById('risk-history');
      if (details) {
        details.addEventListener('toggle', async () => {
          if (!details.open) return;
          const body = document.getElementById('risk-history-body');
          try {
            const entries = await Api.audit.history('risk', id);
            if (!entries.length) {
              body.innerHTML = '<p style="font-size:12px;color:var(--text-subtle);">Sin registros de cambio todavia.</p>';
              return;
            }
            const actionColors = {
              create:'background:#D1FAE5;color:#065F46',
              update:'background:#DBEAFE;color:#1E40AF',
              delete:'background:#FEE2E2;color:#991B1B',
            };
            body.innerHTML = entries.map(e => {
              const ts = new Date(e.timestamp).toLocaleString('es-ES', {
                day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
              const style = actionColors[e.action] || 'background:var(--bg-3);color:var(--text-muted)';
              const detail = e.detail && Object.keys(e.detail).length
                ? Object.entries(e.detail).map(([k,v]) => `${UI.esc(k)}: ${UI.esc(String(v))}`).join(' · ')
                : '';
              return `<div style="display:flex;gap:8px;align-items:flex-start;padding:6px 0;
                                  border-bottom:1px solid var(--border);font-size:12px;">
                <span style="color:var(--text-subtle);white-space:nowrap;min-width:110px;">${ts}</span>
                <span class="badge badge-muted" style="${style};font-size:10px;">${UI.esc(e.action)}</span>
                <span style="color:var(--text-muted);">${UI.esc(e.user_name||e.user_email||'')}</span>
                ${detail ? `<span style="color:var(--text-subtle);">${detail}</span>` : ''}
              </div>`;
            }).join('');
          } catch (_) {
            body.innerHTML = '<p style="font-size:12px;color:var(--text-subtle);">No disponible.</p>';
          }
        }, { once: true });
      }
    }

    if (id && canEdit) document.getElementById('m-del').onclick = async () => {
      if (!await UI.confirm('Eliminar este riesgo?')) return;
      try { await Api.risks.del(id); UI.closeModal(); UI.toast('Eliminado','success'); ViewRisks._reload(); }
      catch (e) { UI.toast(e.message, 'error'); }
    };
    if (canEdit) document.getElementById('m-save').onclick = async () => {
      const getMulti = el => Array.from(el.selectedOptions).map(o => parseInt(o.value));
      const body = {
        description: document.getElementById('f-desc').value,
        consequence_description: document.getElementById('f-cons').value,
        inherent_likelihood: parseInt(document.getElementById('f-il').value)||0,
        inherent_consequence: parseInt(document.getElementById('f-ic').value)||0,
        vulnerability_ids: getMulti(document.getElementById('f-vulns')),
        control_implementation_ids: getMulti(document.getElementById('f-impls')),
        status: document.getElementById('f-status').value,
        treatment_option: document.getElementById('f-treat').value || null,
        treatment_plan: document.getElementById('f-plan').value,
        acceptance_justification: document.getElementById('f-just').value,
      };
      try {
        if (id) await Api.risks.update(id, body);
        else {
          body.asset_id = parseInt(document.getElementById('f-asset').value);
          body.threat_id = parseInt(document.getElementById('f-threat').value);
          await Api.risks.create(body);
        }
        UI.closeModal(); UI.toast('Guardado','success'); ViewRisks._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },
};
