/* BCP/BIA — Continuidad de negocio */
const ViewBcp = (() => {

  const CRIT_COLORS = { critical:'#DC2626', high:'#D97706', medium:'#2563EB', low:'#16a34a' };

  async function render(container) {
    container.innerHTML = UI.sectionHeader(
      'Continuidad de Negocio (BCP/BIA)',
      'NIS2 Art. 21.2(b) + ISO 27001 A.5.29 — Procesos criticos, RTO/RPO y tests',
      `<button class="btn btn-primary" id="btn-new-proc">+ Nuevo proceso</button>`
    );

    // Dashboard resumen
    try {
      const dash = await Api.get('/api/bcp/dashboard');
      const dashEl = document.createElement('div');
      dashEl.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;">
        <div class="stat-card"><div class="stat-value">${dash.total_processes}</div><div class="stat-label">Procesos</div></div>
        <div class="stat-card ${dash.critical_processes>0?'stat-warning':''}">
          <div class="stat-value">${dash.critical_processes}</div><div class="stat-label">Criticos</div></div>
        <div class="stat-card ${dash.processes_overdue_test>0?'stat-danger':''}">
          <div class="stat-value">${dash.processes_overdue_test}</div><div class="stat-label">Sin test 12m</div></div>
        <div class="stat-card">
          <div class="stat-value">${dash.total_tests}</div><div class="stat-label">Tests BCM</div></div>
      </div>`;
      container.appendChild(dashEl);
    } catch(e) {}

    // Tabs
    const tabsEl = document.createElement('div');
    tabsEl.innerHTML = `
    <div class="tabs" style="margin-bottom:16px;">
      <button class="tab active" onclick="ViewBcp._tab('procs',this)">Procesos BIA</button>
      <button class="tab" onclick="ViewBcp._tab('tests',this)">Tests BCM</button>
    </div>
    <div id="bcp-procs"></div>
    <div id="bcp-tests" style="display:none;"></div>`;
    container.appendChild(tabsEl);

    await _loadProcs(document.getElementById('bcp-procs'));
    await _loadTests(document.getElementById('bcp-tests'));

    document.getElementById('btn-new-proc')?.addEventListener('click', () => _openProcForm());
  }

  function _tab(name, btn) {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('bcp-procs').style.display = name === 'procs' ? '' : 'none';
    document.getElementById('bcp-tests').style.display = name === 'tests' ? '' : 'none';
  }

  async function _loadProcs(container) {
    try {
      const procs = await Api.get('/api/bcp/processes');
      if (!procs.length) {
        container.innerHTML = UI.empty('No hay procesos BIA. Registra los procesos criticos con sus objetivos de recuperacion.');
        return;
      }
      container.innerHTML = `
      <div class="table-container">
        <table class="data-table">
          <thead><tr><th>Proceso</th><th>Criticidad</th><th>RTO</th><th>RPO</th><th>Ultimo test</th><th>Resultado</th><th>Acciones</th></tr></thead>
          <tbody>
          ${procs.map(p => `<tr>
            <td><strong>${UI.esc(p.name)}</strong></td>
            <td><span style="color:${CRIT_COLORS[p.criticality]};font-weight:700;">${p.criticality}</span></td>
            <td>${p.rto_hours!=null?p.rto_hours+'h':'—'}</td>
            <td>${p.rpo_hours!=null?p.rpo_hours+'h':'—'}</td>
            <td>${p.last_tested_at?new Date(p.last_tested_at).toLocaleDateString('es-ES'):'—'}</td>
            <td>${p.test_result?`<span class="badge badge-${p.test_result==='passed'?'success':p.test_result==='partial'?'warning':'danger'}">${p.test_result}</span>`:'—'}</td>
            <td style="display:flex;gap:4px;">
              <button class="btn btn-sm btn-secondary" onclick="ViewBcp._editProc(${p.id})">Editar</button>
              <button class="btn btn-sm btn-danger" onclick="ViewBcp._delProc(${p.id})">Eliminar</button>
            </td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
      window._bcpProcs = procs;
    } catch (e) {
      container.innerHTML = UI.notice('error', 'Error: ' + e.message);
    }
  }

  async function _loadTests(container) {
    try {
      const tests = await Api.get('/api/bcp/tests');
      container.innerHTML = `<button class="btn btn-secondary" style="margin-bottom:10px;" onclick="ViewBcp._openTestForm()">+ Programar test</button>`;
      if (!tests.length) {
        container.innerHTML += UI.empty('No hay tests BCM programados.');
        return;
      }
      container.innerHTML += `
      <div class="table-container">
        <table class="data-table">
          <thead><tr><th>Codigo</th><th>Tipo</th><th>Programado</th><th>Realizado</th><th>Resultado</th><th>Acciones</th></tr></thead>
          <tbody>
          ${tests.map(t => `<tr>
            <td>${UI.codePill(t.code)}</td>
            <td>${t.test_type}</td>
            <td>${t.scheduled_at?new Date(t.scheduled_at).toLocaleDateString('es-ES'):'—'}</td>
            <td>${t.conducted_at?new Date(t.conducted_at).toLocaleDateString('es-ES'):'—'}</td>
            <td>${t.result?`<span class="badge badge-${t.result==='passed'?'success':t.result==='partial'?'warning':'danger'}">${t.result}</span>`:'—'}</td>
            <td><button class="btn btn-sm btn-secondary" onclick="ViewBcp._updateTest(${t.id})">Actualizar</button></td>
          </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
      window._bcpTests = tests;
    } catch (e) {
      container.innerHTML += UI.notice('error', 'Error: ' + e.message);
    }
  }

  function _editProc(id) {
    const proc = (window._bcpProcs||[]).find(p => p.id === id);
    if (proc) _openProcForm(proc);
  }

  async function _delProc(id) {
    if (!confirm('Eliminar proceso?')) return;
    await Api.del(`/api/bcp/processes/${id}`);
    UI.toast('Proceso eliminado', 'success');
    location.reload();
  }

  function _openProcForm(proc) {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
    <div class="modal" style="max-width:480px;">
      <div class="modal-header">
        <h2>${proc?'Editar proceso':'Nuevo proceso BIA'}</h2>
        <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
      </div>
      <div class="modal-body">
        <label>Nombre *</label>
        <input id="proc-name" class="form-control" value="${UI.esc(proc?.name||'')}">
        <label style="margin-top:10px;">Criticidad</label>
        <select id="proc-crit" class="form-control">
          ${['critical','high','medium','low'].map(c=>`<option value="${c}"${proc?.criticality===c?' selected':''}>${c}</option>`).join('')}
        </select>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:10px;">
          <div><label>RTO (h)</label><input id="proc-rto" class="form-control" type="number" value="${proc?.rto_hours||''}"></div>
          <div><label>RPO (h)</label><input id="proc-rpo" class="form-control" type="number" value="${proc?.rpo_hours||''}"></div>
          <div><label>MTPD (h)</label><input id="proc-mtpd" class="form-control" type="number" value="${proc?.mtpd_hours||''}"></div>
        </div>
        <label style="margin-top:10px;">Descripcion</label>
        <textarea id="proc-desc" class="form-control" rows="2">${UI.esc(proc?.description||'')}</textarea>
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewBcp._saveProc(${proc?.id||'null'})">Guardar</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Cancelar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _saveProc(id) {
    const body = {
      name: document.getElementById('proc-name').value.trim(),
      criticality: document.getElementById('proc-crit').value,
      rto_hours: parseInt(document.getElementById('proc-rto').value)||null,
      rpo_hours: parseInt(document.getElementById('proc-rpo').value)||null,
      mtpd_hours: parseInt(document.getElementById('proc-mtpd').value)||null,
      description: document.getElementById('proc-desc').value,
    };
    if (!body.name) { UI.toast('El nombre es obligatorio', 'error'); return; }
    try {
      if (id) await Api.patch(`/api/bcp/processes/${id}`, body);
      else await Api.post('/api/bcp/processes', body);
      UI.toast('Proceso guardado', 'success');
      document.querySelector('.modal-overlay')?.remove();
      location.reload();
    } catch (e) { UI.toast('Error: '+(e.message||e), 'error'); }
  }

  function _openTestForm() {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
    <div class="modal" style="max-width:380px;">
      <div class="modal-header">
        <h2>Programar test BCM</h2>
        <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
      </div>
      <div class="modal-body">
        <label>Tipo</label>
        <select id="test-type" class="form-control">
          <option value="tabletop">Tabletop exercise</option>
          <option value="simulation">Simulacion</option>
          <option value="full_test">Test completo</option>
        </select>
        <label style="margin-top:10px;">Fecha programada</label>
        <input id="test-date" class="form-control" type="datetime-local">
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewBcp._saveTest()">Guardar</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Cancelar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _saveTest() {
    const body = {
      test_type: document.getElementById('test-type').value,
      process_ids: [],
      scheduled_at: document.getElementById('test-date').value,
    };
    if (!body.scheduled_at) { UI.toast('Indica la fecha', 'error'); return; }
    try {
      await Api.post('/api/bcp/tests', body);
      UI.toast('Test programado', 'success');
      document.querySelector('.modal-overlay')?.remove();
      location.reload();
    } catch (e) { UI.toast('Error: '+(e.message||e), 'error'); }
  }

  function _updateTest(id) {
    const test = (window._bcpTests||[]).find(t => t.id === id);
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
    <div class="modal" style="max-width:380px;">
      <div class="modal-header">
        <h2>Actualizar test ${UI.esc(test?.code||'')}</h2>
        <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">×</button>
      </div>
      <div class="modal-body">
        <label>Fecha de realizacion</label>
        <input id="upd-date" class="form-control" type="datetime-local" value="${test?.conducted_at?(test.conducted_at.replace('Z','')):''}">
        <label style="margin-top:10px;">Resultado</label>
        <select id="upd-result" class="form-control">
          <option value="">—</option>
          ${['passed','partial','failed'].map(r=>`<option value="${r}"${test?.result===r?' selected':''}>${r}</option>`).join('')}
        </select>
        <label style="margin-top:10px;">Hallazgos</label>
        <textarea id="upd-findings" class="form-control" rows="3">${UI.esc(test?.findings||'')}</textarea>
        <div style="display:flex;gap:8px;margin-top:14px;">
          <button class="btn btn-primary" onclick="ViewBcp._doUpdateTest(${id})">Guardar</button>
          <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Cancelar</button>
        </div>
      </div>
    </div>`;
    document.body.appendChild(modal);
  }

  async function _doUpdateTest(id) {
    const body = {
      conducted_at: document.getElementById('upd-date').value||null,
      result: document.getElementById('upd-result').value||null,
      findings: document.getElementById('upd-findings').value,
    };
    try {
      await Api.patch(`/api/bcp/tests/${id}`, body);
      UI.toast('Test actualizado', 'success');
      document.querySelector('.modal-overlay')?.remove();
      location.reload();
    } catch (e) { UI.toast('Error: '+(e.message||e), 'error'); }
  }

  return { render, _tab, _editProc, _delProc, _saveProc, _openTestForm, _saveTest, _updateTest, _doUpdateTest };
})();
