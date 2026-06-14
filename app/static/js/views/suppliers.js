/* Vista de gestion de proveedores / supply chain risk (NIS2 Art. 21.2.d). */
const ViewSuppliers = (() => {

  const RISK_LABELS = {
    low: 'Bajo', medium: 'Medio', high: 'Alto', critical: 'Critico',
  };
  const RISK_COLORS = {
    low: 'var(--risk-low)', medium: 'var(--risk-medium)',
    high: 'var(--risk-high)', critical: 'var(--risk-critical)',
  };

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  let _activeSupTab = 'suppliers';

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Proveedores y Cadena de Suministro</h1>
          <p class="page-sub">Gestion de riesgo de terceros — NIS2 Art. 21.2.d / ISO 27001 A.15</p>
        </div>
        <div style="display:flex;gap:8px;" id="sup-header-actions"></div>
      </div>

      <div class="stats-row" id="sup-stats" style="margin-bottom:16px;"></div>

      <div style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:16px;">
        <button class="tab-btn" id="suptab-suppliers" onclick="SupTab('suppliers')">Proveedores</button>
        <button class="tab-btn" id="suptab-questionnaires" onclick="SupTab('questionnaires')">Cuestionarios de seguridad</button>
      </div>
      <div id="sup-tab-content"></div>
    `;

    window.SupTab = function(t) { _setSupTab(t); };

    await _loadStats();
    _setSupTab(_activeSupTab);
  }

  function _setSupTab(tab) {
    _activeSupTab = tab;
    ['suppliers','questionnaires'].forEach(t => {
      const btn = document.getElementById('suptab-' + t);
      if (!btn) return;
      btn.style.cssText = `padding:8px 20px;font-size:13px;font-weight:600;border:none;
        background:none;cursor:pointer;border-bottom:3px solid ${t===tab?'var(--brand-purple)':'transparent'};
        color:${t===tab?'var(--brand-purple)':'var(--text-muted)'};margin-bottom:-2px;`;
    });
    // Update header action button
    const actions = document.getElementById('sup-header-actions');
    if (actions) {
      if (tab === 'suppliers') {
        actions.innerHTML = (Auth.canEdit() ? '<button class="btn" id="btn-import-sup">Importar</button> ' : '')
          + '<button class="btn btn-primary" id="btn-new-sup">+ Nuevo proveedor</button>';
        document.getElementById('btn-new-sup').onclick = () => _openForm(null);
        const impBtn = document.getElementById('btn-import-sup');
        if (impBtn) impBtn.onclick = () => _openImport();
      } else {
        actions.innerHTML = Auth.canEdit() ? '<button class="btn btn-primary" id="btn-new-seq">+ Nuevo cuestionario</button>' : '';
        if (Auth.canEdit()) document.getElementById('btn-new-seq').onclick = () => _openSeqForm(null);
      }
    }
    if (tab === 'suppliers') _renderSuppliersTab();
    else _renderQuestionnairesTab();
  }

  async function _renderSuppliersTab() {
    const wrap = document.getElementById('sup-tab-content');
    wrap.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">
        <select id="f-risk" class="input" style="width:160px;">
          <option value="">Todos los niveles</option>
          <option value="critical">Critico</option>
          <option value="high">Alto</option>
          <option value="medium">Medio</option>
          <option value="low">Bajo</option>
        </select>
        <input id="f-q" class="input" placeholder="Buscar..." style="width:200px;">
      </div>
      <div id="sup-table-wrap"></div>
    `;
    document.getElementById('f-risk').onchange = _refresh;
    let debounce;
    document.getElementById('f-q').oninput = () => { clearTimeout(debounce); debounce = setTimeout(_refresh, 300); };
    await _refresh();
  }

  async function _loadStats() {
    try {
      const s = await Api.suppliers.summary();
      const wrap = document.getElementById('sup-stats');
      if (!wrap) return;
      wrap.innerHTML = `
        <div class="stat-card"><div class="stat-value">${s.total}</div><div class="stat-label">Total proveedores</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--risk-critical);">${s.critical_or_high}</div><div class="stat-label">Criticos / Altos</div></div>
        <div class="stat-card"><div class="stat-value" style="color:var(--brand-orange);">${s.overdue_assessment}</div><div class="stat-label">Evaluacion vencida</div></div>
      `;
    } catch (_) {}
  }

  async function _refresh() {
    const riskLevel = document.getElementById('f-risk')?.value || '';
    const q = document.getElementById('f-q')?.value.trim() || '';
    const wrap = document.getElementById('sup-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<p class="text-muted">Cargando...</p>';
    try {
      const params = {};
      if (riskLevel) params.risk_level = riskLevel;
      if (q) params.q = q;
      const data = await Api.suppliers.list(params);
      _renderTable(wrap, data);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _renderTable(wrap, data) {
    if (!data.length) {
      wrap.innerHTML = '<p class="text-muted" style="margin-top:24px;text-align:center;">No se encontraron proveedores.</p>';
      return;
    }
    const rows = data.map(s => {
      const assessed = s.last_assessment_at ? s.last_assessment_at.slice(0, 10) : '-';
      const next = s.next_assessment_at ? s.next_assessment_at.slice(0, 10) : '-';
      const tier = s.tier ? _badge(RISK_LABELS[s.tier] || s.tier, RISK_COLORS[s.tier] || '#888') : '-';
      const inh = (s.inherent_risk_score ?? null) !== null ? s.inherent_risk_score : '-';
      const res = (s.residual_risk_score ?? null) !== null ? s.residual_risk_score : '-';
      return `
        <tr>
          <td><b>${UI.esc(s.code)}</b></td>
          <td>${UI.esc(s.name)}</td>
          <td>${tier}</td>
          <td style="text-align:center;font-weight:700;">${inh}</td>
          <td style="text-align:center;font-weight:700;">${res}</td>
          <td>${assessed}</td>
          <td>${next}</td>
          <td>
            ${Auth.canEdit() ? `<button class="btn btn-sm" data-id="${s.id}" data-action="recompute" title="Recalcular tier y riesgo">Recalcular</button>` : ''}
            <button class="btn btn-sm" data-id="${s.id}" data-action="edit">Editar</button>
            <button class="btn btn-sm btn-danger" data-id="${s.id}" data-action="del">Eliminar</button>
          </td>
        </tr>
      `;
    }).join('');

    wrap.innerHTML = `
      <table class="data">
        <thead>
          <tr>
            <th>Codigo</th><th>Nombre</th><th>Tier</th><th>Inherent</th><th>Residual</th>
            <th>Ult. evaluacion</th><th>Prox. evaluacion</th><th>Acciones</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;

    wrap.querySelectorAll('[data-action="recompute"]').forEach(btn => {
      btn.onclick = async () => {
        try {
          await Api.tprm.recompute(btn.dataset.id);
          UI.toast('Riesgo recalculado', 'success');
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });

    wrap.querySelectorAll('[data-action="edit"]').forEach(btn => {
      btn.onclick = () => {
        const sup = data.find(s => s.id == btn.dataset.id);
        if (sup) _openForm(sup);
      };
    });
    wrap.querySelectorAll('[data-action="del"]').forEach(btn => {
      btn.onclick = async () => {
        if (!confirm('Eliminar proveedor?')) return;
        try {
          await Api.suppliers.del(btn.dataset.id);
          UI.toast('Proveedor eliminado', 'success');
          await _loadStats();
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });
  }

  function _formHtml(s) {
    const v = s || {};
    return `
      <div class="form-grid">
        <div><label>Nombre *</label><input id="f-name" class="input" value="${UI.esc(v.name || '')}"></div>
        <div><label>Categoria</label><input id="f-cat" class="input" value="${UI.esc(v.category || '')}" placeholder="Software, Hardware, Servicios..."></div>
        <div><label>Nivel de riesgo</label>
          <select id="f-risk-level" class="input">
            ${Object.entries(RISK_LABELS).map(([k,l]) => `<option value="${k}" ${v.risk_level===k?'selected':''}>${l}</option>`).join('')}
          </select>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="checkbox" id="f-critical" ${v.is_critical?'checked':''}>
          <label for="f-critical" style="margin:0;cursor:pointer;">Proveedor critico NIS2</label>
        </div>
        <div><label>Contacto</label><input id="f-contact" class="input" value="${UI.esc(v.contact_name || '')}"></div>
        <div><label>Email contacto</label><input id="f-email" class="input" type="email" value="${UI.esc(v.contact_email || '')}"></div>
        <div><label>Ultima evaluacion</label><input type="date" id="f-last-assess" class="input" value="${v.last_assessment_at ? v.last_assessment_at.slice(0,10) : ''}"></div>
        <div><label>Proxima evaluacion</label><input type="date" id="f-next-assess" class="input" value="${v.next_assessment_at ? v.next_assessment_at.slice(0,10) : ''}"></div>
        <div class="span2"><label>Contrato / referencia</label><input id="f-contract" class="input" value="${UI.esc(v.contract_ref || '')}"></div>
        <div class="span2"><label>Notas / descripcion</label><textarea id="f-notes" class="input" rows="3">${UI.esc(v.notes || '')}</textarea></div>

        <div class="span2" style="margin-top:8px;border-top:1px solid var(--border);padding-top:10px;">
          <strong style="font-size:13px;color:var(--brand-purple);">TPRM — Perfil de riesgo inherente</strong>
          <p style="font-size:11px;color:var(--text-muted);margin:2px 0 0;">El tier y el inherent/residual risk se recalculan automaticamente al guardar.</p>
        </div>
        <div><label>Tipo de proveedor</label>
          <select id="f-vendor-type" class="input">
            ${['technology','cloud_provider','professional_services','consultancy','hardware','subcontractor','other'].map(o => `<option value="${o}" ${v.vendor_type===o?'selected':''}>${o}</option>`).join('')}
          </select>
        </div>
        <div><label>Acceso a sistemas</label>
          <select id="f-access" class="input">
            ${['none','api_only','saas','paas','iaas','on_prem','read_write','admin_to_our_systems'].map(o => `<option value="${o}" ${v.system_access_type===o?'selected':''}>${o}</option>`).join('')}
          </select>
        </div>
        <div><label>Sensibilidad de datos (1-5)</label><input type="number" min="1" max="5" id="f-data-sens" class="input" value="${v.data_sensitivity || 2}"></div>
        <div><label>Volumen de datos (1-5)</label><input type="number" min="1" max="5" id="f-data-vol" class="input" value="${v.data_volume || 2}"></div>
        <div><label>Criticidad para el negocio (1-5)</label><input type="number" min="1" max="5" id="f-biz-crit" class="input" value="${v.business_criticality || 3}"></div>
        <div><label>Riesgo geografico (1-5)</label><input type="number" min="1" max="5" id="f-geo" class="input" value="${v.geographic_risk || 1}"></div>
        <div class="span2" style="display:flex;flex-wrap:wrap;gap:16px;">
          <label style="display:flex;align-items:center;gap:6px;margin:0;"><input type="checkbox" id="f-proc" ${v.is_data_processor?'checked':''}> Encargado GDPR</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;"><input type="checkbox" id="f-pii" ${v.processes_personal_data?'checked':''}> Trata datos personales</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;"><input type="checkbox" id="f-nis2" ${v.is_nis2?'checked':''}> NIS2</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;"><input type="checkbox" id="f-dora" ${v.is_dora?'checked':''}> DORA</label>
          <label style="display:flex;align-items:center;gap:6px;margin:0;"><input type="checkbox" id="f-ens" ${v.is_ens?'checked':''}> ENS</label>
        </div>
      </div>
    `;
  }

  function _openForm(s) {
    UI.modal(s ? `Editar ${s.code}` : 'Nuevo proveedor', _formHtml(s), {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`,
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = () => _save(s);
  }

  async function _save(s) {
    const name = document.getElementById('f-name').value.trim();
    if (!name) { UI.toast('El nombre es obligatorio', 'error'); return; }
    const payload = {
      name,
      category: document.getElementById('f-cat').value.trim(),
      risk_level: document.getElementById('f-risk-level').value,
      is_critical: document.getElementById('f-critical').checked,
      contact_name: document.getElementById('f-contact').value.trim(),
      contact_email: document.getElementById('f-email').value.trim(),
      last_assessment_at: document.getElementById('f-last-assess').value || null,
      next_assessment_at: document.getElementById('f-next-assess').value || null,
      contract_ref: document.getElementById('f-contract').value.trim(),
      notes: document.getElementById('f-notes').value.trim(),
      vendor_type: document.getElementById('f-vendor-type').value,
      system_access_type: document.getElementById('f-access').value,
      data_sensitivity: parseInt(document.getElementById('f-data-sens').value) || 2,
      data_volume: parseInt(document.getElementById('f-data-vol').value) || 2,
      business_criticality: parseInt(document.getElementById('f-biz-crit').value) || 3,
      geographic_risk: parseInt(document.getElementById('f-geo').value) || 1,
      is_data_processor: document.getElementById('f-proc').checked,
      processes_personal_data: document.getElementById('f-pii').checked,
      is_nis2: document.getElementById('f-nis2').checked,
      is_dora: document.getElementById('f-dora').checked,
      is_ens: document.getElementById('f-ens').checked,
    };
    try {
      if (s) {
        await Api.suppliers.update(s.id, payload);
        UI.toast('Proveedor actualizado', 'success');
      } else {
        await Api.suppliers.create(payload);
        UI.toast('Proveedor creado', 'success');
      }
      UI.closeModal();
      await _loadStats();
      await _refresh();
    } catch (e) { UI.toast(e.message, 'error'); }
  }

  function _openImport() {
    UI.modal('Importar proveedores', `
      <div class="span2">
        <p style="font-size:13px;margin-bottom:8px;">Sube un fichero exportado desde Excel u otra herramienta de gestion (OneTrust, ERP, hoja de compras...). Formatos: <strong>CSV, XLSX, XLS, ODS, TSV, JSON</strong>.</p>
        <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">Se detectan automaticamente columnas como nombre, categoria, contacto, email, servicios, web, pais y CIF/NIF/VAT (en espanol o ingles). Los proveedores ya existentes (por nombre) se omiten. Se calcula el tier y el riesgo de cada uno tras importar.</p>
        <input type="file" id="imp-file" accept=".csv,.xlsx,.xls,.ods,.tsv,.json" class="input">
        <div id="imp-result" style="margin-top:12px;"></div>
      </div>
    `, {
      actions: `<button class="btn" id="imp-cancel">Cerrar</button>
                <button class="btn btn-primary" id="imp-go">Importar</button>`,
    });
    document.getElementById('imp-cancel').onclick = UI.closeModal;
    document.getElementById('imp-go').onclick = async () => {
      const fileInput = document.getElementById('imp-file');
      const file = fileInput.files && fileInput.files[0];
      if (!file) { UI.toast('Selecciona un fichero', 'error'); return; }
      const resWrap = document.getElementById('imp-result');
      const btn = document.getElementById('imp-go');
      btn.disabled = true;
      resWrap.innerHTML = '<p class="text-muted">Importando...</p>';
      try {
        const r = await Api.suppliers.importFile(file);
        const cols = Object.entries(r.detected_columns || {}).map(([k, v]) => `${k} &larr; "${UI.esc(v)}"`).join(', ');
        resWrap.innerHTML = `
          <div class="notice" style="border-color:var(--risk-low);">
            <strong>${r.created}</strong> proveedores creados, <strong>${r.skipped}</strong> omitidos (de ${r.total} filas).
            ${cols ? `<div style="font-size:11px;color:var(--text-muted);margin-top:6px;">Columnas detectadas: ${cols}</div>` : ''}
            ${(r.errors && r.errors.length) ? `<div style="font-size:11px;color:var(--risk-high);margin-top:6px;">Errores: ${r.errors.map(UI.esc).join('; ')}</div>` : ''}
          </div>`;
        UI.toast(`${r.created} proveedores importados`, 'success');
        await _loadStats();
        await _refresh();
      } catch (e) {
        resWrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
      } finally {
        btn.disabled = false;
      }
    };
  }

  // ======== QUESTIONNAIRES TAB ========

  async function _renderQuestionnairesTab() {
    const wrap = document.getElementById('sup-tab-content');
    wrap.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">
        <select id="seq-sup-filter" class="input" style="width:220px;">
          <option value="">Todos los proveedores</option>
        </select>
      </div>
      <div id="seq-list">Cargando...</div>
    `;
    // Populate supplier filter
    try {
      const sups = await Api.suppliers.list();
      const sel = document.getElementById('seq-sup-filter');
      if (sel) sups.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.code + ' - ' + s.name;
        sel.appendChild(opt);
      });
    } catch (_) {}
    document.getElementById('seq-sup-filter').onchange = _reloadSeq;
    await _reloadSeq();
  }

  async function _reloadSeq() {
    const supId = document.getElementById('seq-sup-filter')?.value;
    const params = {};
    if (supId) params.supplier_id = supId;
    const wrap = document.getElementById('seq-list');
    if (!wrap) return;
    try {
      const data = await Api.supplier_questionnaires.list(params);
      if (!data.length) {
        wrap.innerHTML = '<p style="color:var(--text-muted);margin-top:24px;text-align:center;">Sin cuestionarios enviados. Crea uno para enviar el enlace publico al proveedor.</p>';
        return;
      }
      const now = new Date();
      wrap.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          <th>Codigo</th><th>Titulo</th><th>Proveedor</th><th>Puntuacion</th><th>Respondido</th><th>Expira</th><th>Evaluacion IA</th><th></th>
        </tr></thead>
        <tbody>
          ${data.map(q => {
            const submitted = q.submitted_at ? new Date(q.submitted_at).toLocaleDateString('es-ES') : null;
            const expired = q.expires_at && new Date(q.expires_at) < now && !q.submitted_at;
            const expires = q.expires_at ? new Date(q.expires_at).toLocaleDateString('es-ES') : '-';
            let scoreHtml = '-';
            if (q.score !== null && q.score !== undefined) {
              const sc = q.score;
              const color = sc >= 80 ? '#22C55E' : sc >= 60 ? '#F59E0B' : '#EF4444';
              scoreHtml = `<span style="font-weight:700;color:${color};">${sc}/100</span>`;
            }
            // AI review indicator
            let aiHtml = '-';
            if (q.submitted_at) {
              if (q.ai_review && !q.ai_review.error) {
                const aiscore = q.ai_review.ai_score;
                const aicolor = aiscore >= 80 ? '#22C55E' : aiscore >= 60 ? '#F59E0B' : '#EF4444';
                const reviewedDate = q.ai_reviewed_at ? new Date(q.ai_reviewed_at).toLocaleDateString('es-ES') : '';
                aiHtml = `<span style="font-weight:700;color:${aicolor};cursor:pointer;" data-id="${q.id}" data-act="view-ai" title="Ver evaluacion IA (${reviewedDate})">${aiscore}/100</span>`;
                if (Auth.canEdit()) {
                  aiHtml += ` <button class="btn btn-sm" style="font-size:10px;padding:1px 6px;" data-id="${q.id}" data-act="eval-ai" title="Re-evaluar con IA">Re-evaluar</button>`;
                }
              } else if (Auth.canEdit()) {
                aiHtml = `<button class="btn btn-sm" style="font-size:11px;" data-id="${q.id}" data-act="eval-ai">Evaluar IA</button>`;
              }
            }
            return `<tr style="${expired?'opacity:.6;':''}">
              <td>${UI.codePill(q.code)}</td>
              <td><strong>${UI.esc(q.title)}</strong></td>
              <td style="font-size:12px;">${UI.esc(q.supplier_name||'-')}</td>
              <td>${scoreHtml}</td>
              <td style="font-size:12px;">${submitted ? submitted : (expired ? '<span style="color:#EF4444;font-size:11px;">Expirado</span>' : '<span style="color:#F59E0B;font-size:11px;">Pendiente</span>')}</td>
              <td style="font-size:12px;">${expires}</td>
              <td style="font-size:12px;">${aiHtml}</td>
              <td>
                ${Auth.canEdit() && !q.submitted_at ? `<button class="btn btn-sm" data-id="${q.id}" data-act="send" title="Enviar por email al contacto del proveedor">Enviar email</button>` : ''}
                <button class="btn btn-sm" data-id="${q.id}" data-act="link" title="Copiar enlace publico">Copiar enlace</button>
                ${Auth.canEdit() && !q.submitted_at ? `<button class="btn btn-sm btn-danger" data-id="${q.id}" data-act="del">Eliminar</button>` : ''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>`;
      wrap.querySelectorAll('[data-act="link"]').forEach(btn => {
        btn.onclick = () => {
          const q = data.find(x => x.id == btn.dataset.id);
          if (!q) return;
          const link = location.origin + '/supplier-q?token=' + encodeURIComponent(q.token);
          navigator.clipboard.writeText(link).then(() => UI.toast('Enlace copiado al portapapeles', 'success'))
            .catch(() => {
              UI.modal('Enlace publico del cuestionario', `
                <div class="span2">
                  <p style="font-size:13px;margin-bottom:8px;">Copia y comparte este enlace con el proveedor:</p>
                  <input style="width:100%;font-size:12px;font-family:monospace;" value="${UI.esc(link)}" readonly onclick="this.select()">
                </div>
              `, { actions: '<button class="btn btn-primary" id="m-cancel">Cerrar</button>' });
              document.getElementById('m-cancel').onclick = UI.closeModal;
            });
        };
      });
      wrap.querySelectorAll('[data-act="del"]').forEach(btn => {
        btn.onclick = async () => {
          if (!await UI.confirm('Eliminar este cuestionario?')) return;
          try { await Api.supplier_questionnaires.del(btn.dataset.id); UI.toast('Eliminado','success'); _reloadSeq(); }
          catch (e) { UI.toast(e.message,'error'); }
        };
      });
      wrap.querySelectorAll('[data-act="send"]').forEach(btn => {
        btn.onclick = async () => {
          btn.disabled = true;
          UI.toast('Enviando email al proveedor...', 'info');
          try {
            const r = await Api.supplier_questionnaires.send(btn.dataset.id);
            UI.toast('Cuestionario enviado a ' + r.recipient, 'success');
          } catch (e) {
            UI.toast(e.message, 'error');
            btn.disabled = false;
          }
        };
      });
      // AI evaluation buttons
      wrap.querySelectorAll('[data-act="eval-ai"]').forEach(btn => {
        btn.onclick = async () => {
          const q = data.find(x => x.id == btn.dataset.id);
          if (!q) return;
          UI.toast('Evaluando con IA... Esto puede tardar unos segundos.', 'info');
          btn.disabled = true;
          try {
            const result = await Api.supplier_questionnaires_ai.triggerReview(q.id);
            UI.toast('Evaluacion IA completada', 'success');
            _showAiReviewModal(q.title || q.code, result);
            await _reloadSeq();
          } catch (e) {
            UI.toast(e.message, 'error');
            btn.disabled = false;
          }
        };
      });
      // AI score click to view existing review
      wrap.querySelectorAll('[data-act="view-ai"]').forEach(el => {
        el.onclick = () => {
          const q = data.find(x => x.id == el.dataset.id);
          if (!q || !q.ai_review) return;
          _showAiReviewModal(q.title || q.code, q.ai_review);
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  // ---- AI Review Modal ----

  const _AI_COVERAGE_LABELS = {
    fully_covered: 'Cobertura completa',
    partially_covered: 'Cobertura parcial',
    not_covered: 'Sin cobertura',
    unclear: 'No determinado',
  };
  const _AI_EVIDENCE_LABELS = {
    consistent: 'Consistente',
    partially_consistent: 'Parcialmente consistente',
    inconsistent: 'Inconsistente',
    no_evidence: 'Sin evidencia',
  };
  const _AI_COVERAGE_COLORS = {
    fully_covered: '#22C55E',
    partially_covered: '#F59E0B',
    not_covered: '#EF4444',
    unclear: '#6B7280',
  };
  const _AI_EVIDENCE_COLORS = {
    consistent: '#22C55E',
    partially_consistent: '#F59E0B',
    inconsistent: '#EF4444',
    no_evidence: '#6B7280',
  };

  function _showAiReviewModal(title, review) {
    if (!review) return;
    if (review.error) {
      UI.modal('Evaluacion IA — Error', `
        <div class="span2">
          <div class="notice">${UI.esc(review.error)}</div>
          <p style="font-size:13px;margin-top:8px;">La evaluacion automatica no pudo completarse. Revisa la configuracion de la API key en IA &gt; Configuracion.</p>
        </div>
      `, { actions: '<button class="btn btn-primary" id="m-close-ai">Cerrar</button>' });
      document.getElementById('m-close-ai').onclick = UI.closeModal;
      return;
    }

    const score = review.ai_score !== null && review.ai_score !== undefined ? review.ai_score : '-';
    const scoreColor = typeof score === 'number' ? (score >= 80 ? '#22C55E' : score >= 60 ? '#F59E0B' : '#EF4444') : '#6B7280';
    const confPct = review.confidence !== null && review.confidence !== undefined
      ? Math.round(review.confidence * 100) + '%' : '-';
    const coverage = review.control_coverage_assessment || 'unclear';
    const evidence = review.evidence_consistency || 'no_evidence';
    const needsManual = review.needs_manual_review;
    const rationale = review.rationale || '';
    const reviewedAt = review.evaluated_at ? new Date(review.evaluated_at).toLocaleString('es-ES') : '';

    const redFlags = Array.isArray(review.red_flags) && review.red_flags.length
      ? review.red_flags.map(f => `<li style="margin-bottom:4px;">${UI.esc(f)}</li>`).join('')
      : '<li style="color:var(--text-muted);">Sin alertas detectadas</li>';

    const followUp = Array.isArray(review.follow_up_questions) && review.follow_up_questions.length
      ? review.follow_up_questions.map(f => `<li style="margin-bottom:4px;">${UI.esc(f)}</li>`).join('')
      : '<li style="color:var(--text-muted);">Sin preguntas adicionales</li>';

    UI.modal(`Evaluacion IA — ${UI.esc(title)}`, `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div style="grid-column:1/-1;display:flex;gap:16px;flex-wrap:wrap;align-items:center;border-bottom:1px solid var(--border);padding-bottom:10px;margin-bottom:4px;">
          <div style="text-align:center;">
            <div style="font-size:28px;font-weight:800;color:${scoreColor};">${score}<span style="font-size:14px;">/100</span></div>
            <div style="font-size:11px;color:var(--text-muted);">Puntuacion IA</div>
          </div>
          <div style="text-align:center;">
            <div style="font-size:20px;font-weight:700;color:var(--brand-purple);">${confPct}</div>
            <div style="font-size:11px;color:var(--text-muted);">Confianza</div>
          </div>
          ${needsManual ? '<div style="background:#FEF3C7;border:1px solid #F59E0B;border-radius:6px;padding:4px 10px;font-size:12px;font-weight:600;color:#92400E;">Requiere revision manual</div>' : '<div style="background:#ECFDF5;border:1px solid #22C55E;border-radius:6px;padding:4px 10px;font-size:12px;font-weight:600;color:#065F46;">Sin alerta de revision</div>'}
          ${reviewedAt ? `<div style="font-size:11px;color:var(--text-muted);margin-left:auto;">Evaluado: ${reviewedAt}</div>` : ''}
        </div>

        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Cobertura de controles</div>
          <span style="display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;background:${_AI_COVERAGE_COLORS[coverage]};color:#fff;">${_AI_COVERAGE_LABELS[coverage] || coverage}</span>
        </div>
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Consistencia de evidencias</div>
          <span style="display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600;background:${_AI_EVIDENCE_COLORS[evidence]};color:#fff;">${_AI_EVIDENCE_LABELS[evidence] || evidence}</span>
        </div>

        <div style="grid-column:1/-1;">
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Razonamiento</div>
          <p style="font-size:13px;line-height:1.5;margin:0;background:var(--bg-alt,var(--bg));padding:8px 10px;border-radius:6px;border:1px solid var(--border);">${UI.esc(rationale)}</p>
        </div>

        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Alertas detectadas</div>
          <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.6;">${redFlags}</ul>
        </div>
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">Preguntas de seguimiento sugeridas</div>
          <ul style="margin:0;padding-left:18px;font-size:13px;line-height:1.6;">${followUp}</ul>
        </div>
      </div>
    `, { actions: '<button class="btn btn-primary" id="m-close-ai">Cerrar</button>' });
    document.getElementById('m-close-ai').onclick = UI.closeModal;
  }

  async function _openSeqForm() {
    let suppliers = [];
    let templates = [];
    let customTpls = [];
    try { suppliers = await Api.suppliers.list(); } catch (_) {}
    try { templates = await Api.tprm.templates(); } catch (_) {}
    try { customTpls = await Api.tprm.customTemplates(); } catch (_) {}
    UI.modal('Nuevo cuestionario de seguridad', `
      <div><label>Proveedor *</label>
        <select id="sq-sup">
          <option value="">- Seleccionar -</option>
          ${suppliers.map(s => `<option value="${s.id}">${UI.esc(s.code)} - ${UI.esc(s.name)}</option>`).join('')}
        </select>
      </div>
      <div><label>Plantilla TPRM</label>
        <select id="sq-template">
          <option value="">Estandar NIS2/ISO 27001 (10 preguntas)</option>
          <optgroup label="Plantillas del sistema">
          ${templates.map(t => `<option value="sys:${UI.esc(t.code)}">${UI.esc(t.name)} (${t.question_count} preguntas)</option>`).join('')}
          </optgroup>
          ${customTpls.length ? `<optgroup label="Mis plantillas">
          ${customTpls.map(t => `<option value="custom:${t.id}">${UI.esc(t.name)} (${(t.questions||[]).length} preguntas)</option>`).join('')}
          </optgroup>` : ''}
        </select>
      </div>
      <div><label>Titulo *</label>
        <input id="sq-title" value="Evaluacion de seguridad NIS2/ISO 27001">
      </div>
      <div><label>Fecha de expiracion</label>
        <input type="date" id="sq-expires" value="${new Date(Date.now()+30*86400000).toISOString().slice(0,10)}">
      </div>
      <div class="span2"><label>Notas internas</label>
        <textarea id="sq-notes" rows="2" placeholder="Notas para el equipo interno (no visibles para el proveedor)"></textarea>
      </div>
      <div class="span2 notice">
        Elige una plantilla del sistema (ISO 27001, NIS2, DORA, GDPR, ISO 42001, offboarding...) o el set estandar. Tras crear el cuestionario, copia el enlace publico para enviarlo al proveedor.
      </div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Crear y obtener enlace</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const supId = document.getElementById('sq-sup').value;
      const title = document.getElementById('sq-title').value.trim();
      if (!supId) { UI.toast('Selecciona un proveedor','error'); return; }
      if (!title) { UI.toast('El titulo es obligatorio','error'); return; }
      const expires = document.getElementById('sq-expires').value;
      const tplVal = document.getElementById('sq-template').value || '';
      const body = {
        supplier_id: parseInt(supId),
        title,
        expires_at: expires || null,
        notes: document.getElementById('sq-notes').value.trim(),
        template_code: tplVal.startsWith('sys:') ? tplVal.slice(4) : null,
        custom_template_id: tplVal.startsWith('custom:') ? parseInt(tplVal.slice(7)) : null,
      };
      try {
        const q = await Api.supplier_questionnaires.create(body);
        UI.closeModal();
        const link = location.origin + '/supplier-q?token=' + encodeURIComponent(q.token);
        navigator.clipboard.writeText(link).catch(() => {});
        UI.modal('Cuestionario creado', `
          <div class="span2">
            <p style="font-size:13px;margin-bottom:4px;">Cuestionario <strong>${UI.esc(q.code)}</strong> creado correctamente.</p>
            <p style="font-size:13px;margin-bottom:8px;">Enlace publico copiado al portapapeles. Comparte este enlace con el proveedor:</p>
            <input style="width:100%;font-size:12px;font-family:monospace;" value="${UI.esc(link)}" readonly onclick="this.select()">
            <p style="font-size:12px;color:var(--text-muted);margin-top:8px;">El enlace expira el ${new Date(q.expires_at).toLocaleDateString('es-ES')}.</p>
          </div>
        `, { actions: '<button class="btn btn-primary" id="m-ok">Entendido</button>' });
        document.getElementById('m-ok').onclick = UI.closeModal;
        _reloadSeq();
      } catch (e) { UI.toast(e.message,'error'); }
    };
  }

  return { render };
})();
