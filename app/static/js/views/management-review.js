/* Management Review — ISO 27001 cl. 9.3 */
const ViewManagementReview = (() => {

  function _statusBadge(status) {
    const m = { draft: ['#FEF9C3','#854d0e','Borrador'], conducted: ['#DBEAFE','#1d4ed8','Celebrada'], approved: ['#D1FAE5','#065f46','Aprobada'] };
    const [bg, col, label] = m[status] || ['#F5F5F5','#9D9D9D', status];
    return `<span style="background:${bg};color:${col};padding:2px 10px;border-radius:10px;font-size:11px;font-weight:700;">${label}</span>`;
  }

  async function render(container) {
    container.innerHTML = UI.sectionHeader(
      'Revision por la Direccion',
      'ISO 27001 cl. 9.3 — Inputs auto-poblados desde el SGSI, outputs formales y acta PDF',
      `<button class="btn btn-primary" id="btn-new-mr">+ Preparar revision mensual</button>`
    );
    const wrap = document.createElement('div');
    container.appendChild(wrap);
    await _loadList(wrap);
    document.getElementById('btn-new-mr')?.addEventListener('click', _createReview);
  }

  async function _loadList(container) {
    try {
      const reviews = await Api.get('/api/management-review');
      if (!reviews.length) {
        container.innerHTML = UI.emptyState('Sin revisiones de direccion', 'Prepara la del mes actual con el boton de arriba.');
        return;
      }
      container.innerHTML = `
      <div class="table-container">
        <table class="data-table">
          <thead><tr><th>Codigo</th><th>Fecha</th><th>Estado</th><th>KPIs</th><th>Acciones</th></tr></thead>
          <tbody>
          ${reviews.map(r => `<tr>
            <td>${UI.codePill(r.code||'-')}</td>
            <td>${r.review_date ? new Date(r.review_date).toLocaleDateString('es-ES') : 'Por fijar'}</td>
            <td>${_statusBadge(r.status)}</td>
            <td>${r.input_performance_data ? '<span style="color:#16a34a;">Cargados</span>' : '—'}</td>
            <td style="display:flex;gap:4px;flex-wrap:wrap;">
              <button class="btn btn-sm btn-secondary" onclick="ViewManagementReview._detail(${r.id})">Detalle</button>
              ${r.status !== 'approved' ? `<button class="btn btn-sm btn-secondary" onclick="ViewManagementReview._approve(${r.id})">Aprobar</button>` : ''}
              <a href="/api/management-review/${r.id}/pdf" target="_blank" class="btn btn-sm btn-outline">PDF</a>
            </td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    } catch (e) {
      container.innerHTML = UI.notice('error', 'Error: ' + e.message);
    }
  }

  async function _createReview() {
    try {
      const mr = await Api.post('/api/management-review', {});
      UI.toast(`Revision ${mr.code} preparada con inputs automaticos`, 'success');
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  async function _detail(id) {
    const mr = await Api.get(`/api/management-review/${id}`);
    const kpis = mr.input_performance_data || {};
    const risks = mr.input_risk_register || [];
    const nc = mr.input_nc_corrections || {};

    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
    <div class="modal" style="max-width:680px;max-height:80vh;overflow-y:auto;">
      <div class="modal-header">
        <h2>${UI.esc(mr.code||'')} — Revision por la Direccion</h2>
        <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
      </div>
      <div class="modal-body">
        <div style="display:flex;gap:8px;margin-bottom:16px;">
          <button class="btn btn-secondary active-tab" id="tab-btn-in" onclick="ViewManagementReview._tabSwitch('in')">Entradas ISO 9.3.2</button>
          <button class="btn btn-secondary" id="tab-btn-out" onclick="ViewManagementReview._tabSwitch('out')">Salidas ISO 9.3.3</button>
        </div>
        <div id="mr-tab-in">
          <h3 style="font-size:14px;margin:0 0 8px;">KPIs del SGSI (auto-poblados)</h3>
          <table class="data-table" style="font-size:12px;">
          ${Object.entries(kpis).filter(([k])=>k!=='generated_at').map(([k,v])=>
            `<tr><td style="width:50%;"><strong>${k.replace(/_/g,' ')}</strong></td><td>${v}</td></tr>`
          ).join('')}
          </table>
          <h3 style="font-size:14px;margin:16px 0 8px;">Top riesgos residuales</h3>
          ${risks.slice(0,10).map(r=>`<div class="list-item" style="font-size:12px;">
            ${UI.codePill(r.code)} ${UI.esc(r.asset||'')} — Nivel <strong>${r.level}</strong> — ${r.status}
          </div>`).join('')||'<p>Sin datos</p>'}
          <h3 style="font-size:14px;margin:16px 0 8px;">No conformidades</h3>
          <p>Abiertas: <strong>${nc.open||0}</strong> | Cerradas este mes: <strong>${nc.closed_this_month||0}</strong></p>
          ${mr.input_audit_results?.length ? `
            <h3 style="font-size:14px;margin:16px 0 8px;">Resultados auditorias</h3>
            ${mr.input_audit_results.map(a=>`<div class="list-item" style="font-size:12px;">
              ${UI.codePill(a.code)} ${UI.esc(a.title||'')} — ${a.finding_count||0} hallazgos
            </div>`).join('')}` : ''}
        </div>
        <div id="mr-tab-out" style="display:none;">
          <label>Decisiones formales adoptadas</label>
          <textarea id="mr-decisions" class="form-control" rows="5" style="width:100%"
            placeholder="Una decision por linea...">${(mr.output_decisions||[]).join('\n')}</textarea>
          <label style="margin-top:12px;">Recursos aprobados</label>
          <textarea id="mr-resources" class="form-control" rows="3" style="width:100%;margin-top:4px;">${mr.output_resources||''}</textarea>
          <div style="display:flex;gap:8px;margin-top:12px;">
            <button class="btn btn-secondary" onclick="ViewManagementReview._saveOutputs(${id})">Guardar salidas</button>
            <button class="btn btn-primary" onclick="ViewManagementReview._conduct(${id})">Marcar como celebrada</button>
          </div>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  function _tabSwitch(tab) {
    document.getElementById('mr-tab-in').style.display = tab === 'in' ? '' : 'none';
    document.getElementById('mr-tab-out').style.display = tab === 'out' ? '' : 'none';
  }

  async function _saveOutputs(id) {
    const decisions = (document.getElementById('mr-decisions')?.value||'').split('\n').filter(Boolean);
    const resources = document.getElementById('mr-resources')?.value||'';
    await Api.patch(`/api/management-review/${id}`, { output_decisions: decisions, output_resources: resources });
    UI.toast('Salidas guardadas', 'success');
  }

  async function _conduct(id) {
    await _saveOutputs(id);
    await Api.post(`/api/management-review/${id}/conduct`, {});
    UI.toast('Revision marcada como celebrada', 'success');
    document.querySelector('.modal-overlay')?.remove();
    location.reload();
  }

  async function _approve(id) {
    if (!confirm('Aprobar esta revision? El acta quedara bloqueada.')) return;
    try {
      await Api.post(`/api/management-review/${id}/approve`, {});
      UI.toast('Revision aprobada', 'success');
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  return { render, _detail, _approve, _tabSwitch, _saveOutputs, _conduct };
})();
