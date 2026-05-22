/* Vista Riesgos - identificacion, analisis, evaluacion, tratamiento. */
const ViewRisks = {
  _assets: [], _threats: [], _vulns: [], _impls: [],

  async render(main) {
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      'Registro de riesgos',
      'ISO/IEC 27005:2018 cl. 8-9 - identificacion, analisis, tratamiento',
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
      </div>
      <div id="r-list"></div>
    `;
    if (canEdit) document.getElementById('btn-new').onclick = () => ViewRisks._edit();
    document.getElementById('r-search').oninput = () => ViewRisks._reload();
    document.getElementById('r-status').onchange = () => ViewRisks._reload();
    document.getElementById('r-band').onchange = () => ViewRisks._reload();

    // Precargar catalogos en memoria
    await ViewRisks._loadCatalogs();
    await ViewRisks._reload();

    // Atajo desde heatmap: ?id=X
    const m = location.hash.match(/[?&]id=(\d+)/);
    if (m) ViewRisks._edit(parseInt(m[1]));
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
      const params = {};
      if (status) params.status = status;
      if (band) params.min_level = band;
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
      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead>
          <tr>
            <th>Codigo</th><th>Activo</th><th>Amenaza</th>
            <th>Inh.</th><th>Res.</th><th>Banda</th>
            <th>Estado</th><th>Tratamiento</th><th></th>
          </tr>
        </thead>
        <tbody>
          ${data.map(r => `
            <tr data-id="${r.id}" style="cursor:pointer;">
              <td>${UI.codePill(r.code)}</td>
              <td><strong>${UI.esc(r.asset?.name||'-')}</strong></td>
              <td>${UI.esc(r.threat?.name||'-')}</td>
              <td>${UI.riskPill(r.inherent_level)}</td>
              <td>${UI.riskPill(r.residual_level)}</td>
              <td>${UI.riskBand(r.residual_level)}</td>
              <td>${UI.statusLabel(r.status)}</td>
              <td>${UI.treatmentLabel(r.treatment_option)}</td>
              <td><button class="btn btn-ghost" data-edit="${r.id}">Ver</button></td>
            </tr>`).join('')}
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
        Riesgo = combinacion de un Activo y una Amenaza. El nivel se calcula como
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
        <label>Descripcion del escenario</label>
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
        <label>Vulnerabilidades asociadas (multi-seleccion)</label>
        <select id="f-vulns" multiple size="5" style="height:auto;">
          ${ViewRisks._vulns.map(v => `<option value="${v.id}" ${r.vulnerability_ids?.includes(v.id)?'selected':''}>${UI.esc(v.code)} - ${UI.esc(v.name)}</option>`).join('')}
        </select>
      </div>
      <div class="span2">
        <label>Controles implementados que mitigan (multi-seleccion)</label>
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
        <label>Decision de tratamiento</label>
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
        <label>Justificacion de aceptacion (si aplica)</label>
        <textarea id="f-just" rows="2">${UI.esc(r.acceptance_justification||'')}</textarea>
      </div>
      ${id ? `
      <div class="span2 notice ${r.residual_level <= 2 ? '' : 'notice-warn'}">
        Nivel inherente actual: <strong>${r.inherent_level}</strong> -
        Nivel residual actual: <strong>${r.residual_level}</strong>
        ${r.accepted_at ? `<br>Aceptado el ${r.accepted_at}` : ''}
      </div>` : ''}
    `, {
      actions: canEdit ? `
        <button class="btn" id="m-cancel">Cerrar</button>
        ${id ? '<button class="btn btn-danger" id="m-del">Eliminar</button>' : ''}
        <button class="btn btn-primary" id="m-save">Guardar</button>
      ` : '<button class="btn" id="m-cancel">Cerrar</button>'
    });

    document.getElementById('m-cancel').onclick = UI.closeModal;
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
