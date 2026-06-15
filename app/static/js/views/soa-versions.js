/* SoA Versions — ISO 27001 cl. 6.1.3 */
const ViewSoaVersions = (() => {

  function _badge(status) {
    const m = { draft: ['#FEF9C3','#854d0e'], under_review: ['#DBEAFE','#1d4ed8'], approved: ['#D1FAE5','#065f46'], superseded: ['#F5F5F5','#9D9D9D'] };
    const [bg, col] = m[status] || ['#F5F5F5','#9D9D9D'];
    return `<span style="background:${bg};color:${col};padding:2px 10px;border-radius:10px;font-size:11px;font-weight:700;">${status.replace('_',' ')}</span>`;
  }

  function _statusLabel(s) {
    const m = { implemented: 'Implementado', partial: 'Parcial', planned: 'Planificado', not_implemented: 'No implementado' };
    return m[s] || s || '—';
  }

  function _exportCsv(impls) {
    const headers = ['Codigo','Nombre','Tema','Estado','Madurez','Razon inclusion','Notas'];
    const rows = impls.map(i => [
      i.control?.code||'',
      '"'+(i.control?.name||'').replace(/"/g,'""')+'"',
      i.control?.theme||'',
      i.status||'',
      i.maturity||0,
      '"'+(i.inclusion_reason||'').replace(/"/g,'""')+'"',
      '"'+(i.notes||'').replace(/"/g,'""')+'"',
    ]);
    const csv = [headers.join(','), ...rows.map(r=>r.join(','))].join('\n');
    const a = document.createElement('a');
    a.href = 'data:text/csv;charset=utf-8,'+encodeURIComponent(csv);
    a.download = 'SoA_'+new Date().toISOString().slice(0,10)+'.csv';
    a.click();
  }

  async function _loadSoaPanel(versions) {
    const panel = document.getElementById('soa-content-panel');
    if (!panel) return;
    if (panel.dataset.loaded === '1') {
      panel.style.display = panel.style.display === 'none' ? '' : 'none';
      return;
    }
    panel.innerHTML = '<div class="notice">Cargando controles...</div>';
    panel.style.display = '';
    try {
      const impls = await Api.get('/api/controls/implementations');
      const approved = versions ? versions.find(v => v.status === 'approved') : null;

      panel.dataset.loaded = '1';
      panel.dataset.impls = JSON.stringify(impls);

      panel.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;margin:20px 0 12px;">
          <h3 style="margin:0;font-size:15px;">Contenido SoA actual (${impls.length} controles)</h3>
          <div style="display:flex;gap:8px;">
            <button class="btn btn-ghost btn-sm" id="btn-soa-export-csv">Exportar CSV</button>
            ${approved ? `<a href="/api/soa/versions/${approved.id}/pdf" target="_blank" class="btn btn-ghost btn-sm">Exportar PDF</a>` : ''}
          </div>
        </div>
        <div class="table-container">
          <table class="data-table">
            <thead>
              <tr>
                <th>Codigo</th>
                <th>Nombre</th>
                <th>Tema</th>
                <th>Estado</th>
                <th>Madurez</th>
                <th>Razon inclusion</th>
                <th>Evidencia</th>
              </tr>
            </thead>
            <tbody>
              ${impls.map(i => `<tr>
                <td>${UI.codePill ? UI.codePill(i.control?.code||'—') : (i.control?.code||'—')}</td>
                <td>${i.control?.name || '—'}</td>
                <td><span style="font-size:11px;">${i.control?.theme||'—'}</span></td>
                <td>${_statusLabel(i.status)}</td>
                <td style="text-align:center;">${i.maturity != null ? i.maturity : '—'}</td>
                <td style="font-size:12px;max-width:240px;">${i.inclusion_reason || '—'}</td>
                <td style="text-align:center;">${i.evidence_count > 0 ? '<span style="color:var(--brand-purple);font-weight:700;">Si</span>' : 'No'}</td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>`;

      document.getElementById('btn-soa-export-csv')?.addEventListener('click', () => {
        _exportCsv(JSON.parse(panel.dataset.impls || '[]'));
      });
    } catch (e) {
      panel.innerHTML = UI.notice ? UI.notice('error', 'Error cargando SoA: ' + e.message) : `<div class="notice">${e.message}</div>`;
    }
  }

  async function render(container) {
    container.innerHTML = UI.sectionHeader(
      'Declaracion de Aplicabilidad (SoA)',
      'ISO 27001 cl. 6.1.3 — Historial de versiones aprobadas con snapshot inmutable',
      `<div style="display:flex;gap:8px;">
         <button class="btn btn-ghost" id="btn-view-soa">Ver SoA actual</button>
         <button class="btn btn-primary" id="btn-new-soa">+ Nueva version borrador</button>
       </div>`
    );
    const wrap = document.createElement('div');
    container.appendChild(wrap);
    const soaPanel = document.createElement('div');
    soaPanel.id = 'soa-content-panel';
    soaPanel.style.display = 'none';
    container.appendChild(soaPanel);
    await _load(wrap);
    document.getElementById('btn-new-soa')?.addEventListener('click', _create);
    document.getElementById('btn-view-soa')?.addEventListener('click', async () => {
      const versions = await Api.get('/api/soa/versions').catch(() => []);
      await _loadSoaPanel(versions);
    });
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

  return { render, _submit, _approve, _exportCsv };
})();
