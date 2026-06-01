/* SoA Versions — ISO 27001 cl. 6.1.3 */
const ViewSoaVersions = (() => {

  function _badge(status) {
    const m = { draft: ['#FEF9C3','#854d0e'], under_review: ['#DBEAFE','#1d4ed8'], approved: ['#D1FAE5','#065f46'], superseded: ['#F5F5F5','#9D9D9D'] };
    const [bg, col] = m[status] || ['#F5F5F5','#9D9D9D'];
    return `<span style="background:${bg};color:${col};padding:2px 10px;border-radius:10px;font-size:11px;font-weight:700;">${status.replace('_',' ')}</span>`;
  }

  async function render(container) {
    container.innerHTML = UI.sectionHeader(
      'Declaracion de Aplicabilidad (SoA)',
      'ISO 27001 cl. 6.1.3 — Historial de versiones aprobadas con snapshot inmutable',
      `<button class="btn btn-primary" id="btn-new-soa">+ Nueva version borrador</button>`
    );
    const wrap = document.createElement('div');
    container.appendChild(wrap);
    await _load(wrap);
    document.getElementById('btn-new-soa')?.addEventListener('click', _create);
  }

  async function _load(container) {
    try {
      const versions = await Api.get('/api/soa/versions');
      if (!versions.length) {
        container.innerHTML = UI.empty('No hay versiones de SoA. Crea una nueva para capturar el estado actual de los controles implementados.');
        return;
      }
      container.innerHTML = `
      <div class="table-container">
        <table class="data-table">
          <thead><tr><th>Version</th><th>Estado</th><th>Controles</th><th>Enviada</th><th>Aprobada</th><th>Acciones</th></tr></thead>
          <tbody>
          ${versions.map(v => `<tr>
            <td>${UI.codePill(v.version)}</td>
            <td>${_badge(v.status)}</td>
            <td>${v.controls_count}</td>
            <td>${v.submitted_at ? new Date(v.submitted_at).toLocaleDateString('es-ES') : '—'}</td>
            <td>${v.approved_at ? new Date(v.approved_at).toLocaleDateString('es-ES') : '—'}</td>
            <td style="display:flex;gap:4px;flex-wrap:wrap;">
              ${v.status === 'draft' ? `<button class="btn btn-sm btn-secondary" onclick="ViewSoaVersions._submit(${v.id})">Enviar revision</button>` : ''}
              ${v.status === 'under_review' ? `<button class="btn btn-sm btn-primary" onclick="ViewSoaVersions._approve(${v.id})">Aprobar</button>` : ''}
              ${v.status === 'approved' || v.status === 'superseded' ? `<a href="/api/soa/versions/${v.id}/pdf" target="_blank" class="btn btn-sm btn-outline">PDF</a>` : ''}
            </td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
    } catch (e) {
      container.innerHTML = UI.notice('error', 'Error: ' + e.message);
    }
  }

  async function _create() {
    try {
      const v = await Api.post('/api/soa/versions', {});
      UI.toast(`Version ${v.version} creada con ${v.controls_count} controles`, 'success');
      location.reload();
    } catch (e) {
      if (e.status === 409) UI.toast('Ya existe un borrador activo de SoA', 'warning');
      else UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  async function _submit(id) {
    await Api.post(`/api/soa/versions/${id}/submit`, {});
    UI.toast('Version enviada para revision', 'success');
    location.reload();
  }

  async function _approve(id) {
    const notes = prompt('Notas de aprobacion (opcional):') || '';
    try {
      await Api.post(`/api/soa/versions/${id}/approve`, { approval_notes: notes });
      UI.toast('SoA aprobada. Snapshot inmutable guardado.', 'success');
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  return { render, _submit, _approve };
})();
