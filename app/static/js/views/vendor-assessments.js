/* Vista de evaluaciones consolidadas de proveedor — TPRM Sprint 4. */
const ViewVendorAssessments = (() => {

  const REC_LABELS = {
    approve:                'Aprobar',
    approve_with_conditions:'Aprobar con condiciones',
    reject:                 'Rechazar',
    request_more_info:      'Solicitar mas informacion',
  };

  const LEVEL_LABELS = {
    critical: 'Critico',
    high:     'Alto',
    medium:   'Medio',
    low:      'Bajo',
    very_low: 'Muy bajo',
    unknown:  'Desconocido',
  };

  function _riskColor(score) {
    if (score == null) return 'var(--text-muted)';
    if (score >= 75) return 'var(--risk-critical)';
    if (score >= 50) return 'var(--risk-high)';
    if (score >= 25) return 'var(--risk-medium)';
    return 'var(--risk-low)';
  }

  function _badge(label, color) {
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }

  function _scorePill(score, level) {
    if (score == null) return '<span style="color:var(--text-muted);">-</span>';
    const color = _riskColor(score);
    const label = LEVEL_LABELS[level] || level || '';
    return `<span style="font-weight:700;color:${color};">${score}</span> <span style="font-size:11px;color:${color};">${UI.esc(label)}</span>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Evaluaciones de proveedores</h1>
          <p class="page-sub">Evaluacion consolidada de riesgo por proveedor — TPRM. Agrega cuestionarios y envia al Risk Register ISO 27005.</p>
        </div>
        ${Auth.canEdit() ? '<button class="btn btn-primary" id="btn-new-vas">+ Nueva evaluacion</button>' : ''}
      </div>

      <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <select id="vas-sup-filter" class="input" style="width:240px;">
          <option value="">Todos los proveedores</option>
        </select>
      </div>

      <div id="vas-table-wrap"><p class="text-muted">Cargando...</p></div>
    `;

    if (Auth.canEdit()) {
      document.getElementById('btn-new-vas').onclick = () => _openForm();
    }

    // Poblar filtro de proveedores
    try {
      const sups = await Api.suppliers.list();
      const sel = document.getElementById('vas-sup-filter');
      if (sel) {
        sups.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.id;
          opt.textContent = s.code + ' - ' + s.name;
          sel.appendChild(opt);
        });
      }
    } catch (_) {}

    document.getElementById('vas-sup-filter').onchange = _refresh;
    await _refresh();
  }

  async function _refresh() {
    const supplierId = document.getElementById('vas-sup-filter')?.value;
    const wrap = document.getElementById('vas-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<p class="text-muted">Cargando...</p>';
    try {
      const params = {};
      if (supplierId) params.supplier_id = supplierId;
      const data = await Api.vendor_assessments.list(params);
      _renderTable(wrap, data);
    } catch (e) {
      wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _renderTable(wrap, data) {
    if (!data.length) {
      wrap.innerHTML = '<p class="text-muted" style="margin-top:24px;text-align:center;">No hay evaluaciones registradas. Crea la primera con el boton "+ Nueva evaluacion".</p>';
      return;
    }

    const rows = data.map(a => {
      const date = a.assessment_date ? a.assessment_date.slice(0, 10) : '-';
      const rec = a.recommendation ? (REC_LABELS[a.recommendation] || a.recommendation) : '-';
      const approved = a.approved_at
        ? `<span style="color:var(--risk-low);font-size:11px;">Aprobado ${a.approved_at.slice(0,10)}</span>`
        : '<span style="color:var(--text-muted);font-size:11px;">Sin aprobar</span>';
      const linkedRisk = a.linked_risk_id
        ? `<span style="color:var(--risk-medium);font-size:11px;">En registro</span>`
        : '';

      return `
        <tr>
          <td>${UI.codePill ? UI.codePill(a.code) : `<b>${UI.esc(a.code)}</b>`}</td>
          <td>${UI.esc(a.supplier_name || '-')}</td>
          <td style="font-size:12px;">${UI.esc(date)}</td>
          <td>${_scorePill(a.inherent_risk_score, a.inherent_risk_level)}</td>
          <td>${_scorePill(a.residual_risk_score, a.residual_risk_level)}</td>
          <td style="font-size:12px;">${UI.esc(rec)}</td>
          <td style="font-size:12px;">${approved}</td>
          <td>
            <button class="btn btn-sm" data-id="${a.id}" data-act="view">Ver</button>
            ${Auth.canEdit() && !a.approved_at ? `<button class="btn btn-sm" data-id="${a.id}" data-act="approve">Aprobar</button>` : ''}
            ${Auth.canEdit() && !a.linked_risk_id ? `<button class="btn btn-sm" data-id="${a.id}" data-act="push">Push a riesgos</button>` : linkedRisk}
            ${Auth.canEdit() ? `<button class="btn btn-sm btn-danger" data-id="${a.id}" data-act="del">Eliminar</button>` : ''}
          </td>
        </tr>
      `;
    }).join('');

    wrap.innerHTML = `
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>Codigo</th>
              <th>Proveedor</th>
              <th>Fecha</th>
              <th>Inherente</th>
              <th>Residual</th>
              <th>Recomendacion</th>
              <th>Estado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;

    wrap.querySelectorAll('[data-act="view"]').forEach(btn => {
      btn.onclick = () => {
        const a = data.find(x => x.id == btn.dataset.id);
        if (a) _openDetail(a);
      };
    });

    wrap.querySelectorAll('[data-act="approve"]').forEach(btn => {
      btn.onclick = async () => {
        if (!await UI.confirm('Aprobar esta evaluacion?')) return;
        try {
          await Api.vendor_assessments.approve(btn.dataset.id);
          UI.toast('Evaluacion aprobada', 'success');
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });

    wrap.querySelectorAll('[data-act="push"]').forEach(btn => {
      btn.onclick = async () => {
        if (!await UI.confirm('Enviar esta evaluacion al Risk Register ISO 27005?')) return;
        try {
          const res = await Api.vendor_assessments.pushToRegister(btn.dataset.id);
          UI.toast(`Riesgo ${res.risk_code} creado en el registro`, 'success');
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });

    wrap.querySelectorAll('[data-act="del"]').forEach(btn => {
      btn.onclick = async () => {
        if (!await UI.confirm('Eliminar esta evaluacion?')) return;
        try {
          await Api.vendor_assessments.del(btn.dataset.id);
          UI.toast('Evaluacion eliminada', 'success');
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    });
  }

  function _openDetail(a) {
    const domainRows = a.score_by_domain && Object.keys(a.score_by_domain).length
      ? Object.entries(a.score_by_domain).map(([domain, score]) => {
          const pct = Math.max(0, Math.min(100, score));
          const color = _riskColor(100 - pct); // invertido: postura alta = color bajo riesgo
          return `
            <div style="margin-bottom:8px;">
              <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
                <span>${UI.esc(domain)}</span>
                <span style="font-weight:600;color:${color};">${pct}/100</span>
              </div>
              <div style="background:var(--border);border-radius:4px;height:6px;">
                <div style="background:${color};width:${pct}%;height:6px;border-radius:4px;"></div>
              </div>
            </div>
          `;
        }).join('')
      : '<p style="color:var(--text-muted);font-size:12px;">Sin detalle por dominio disponible.</p>';

    const recLabel = a.recommendation ? (REC_LABELS[a.recommendation] || a.recommendation) : 'Sin recomendacion';
    const approvedLine = a.approved_at
      ? `<p><strong>Aprobado:</strong> ${a.approved_at.slice(0, 10)} (usuario #${a.approver_user_id})</p>`
      : '<p style="color:var(--text-muted);">Pendiente de aprobacion.</p>';
    const riskLine = a.linked_risk_id
      ? `<p><strong>Riesgo vinculado:</strong> ID ${a.linked_risk_id}</p>`
      : '<p style="color:var(--text-muted);">Sin riesgo vinculado en el registro.</p>';

    UI.modal(`Evaluacion ${UI.esc(a.code)} — ${UI.esc(a.supplier_name || '')}`, `
      <div class="form-grid">
        <div>
          <p><strong>Periodo:</strong> ${UI.esc(a.period_label || '-')}</p>
          <p><strong>Fecha:</strong> ${a.assessment_date ? a.assessment_date.slice(0, 10) : '-'}</p>
          <p><strong>Recomendacion:</strong> ${UI.esc(recLabel)}</p>
          ${approvedLine}
          ${riskLine}
        </div>
        <div>
          <p><strong>Riesgo inherente:</strong> ${_scorePill(a.inherent_risk_score, a.inherent_risk_level)}</p>
          <p><strong>Eficacia de controles:</strong> <span style="font-weight:700;">${a.control_effectiveness_score ?? '-'}</span></p>
          <p><strong>Riesgo residual:</strong> ${_scorePill(a.residual_risk_score, a.residual_risk_level)}</p>
        </div>
        <div class="span2">
          <strong style="font-size:13px;">Score por dominio</strong>
          <div style="margin-top:8px;">${domainRows}</div>
        </div>
        ${a.summary ? `
        <div class="span2">
          <strong style="font-size:13px;">Resumen</strong>
          <p style="font-size:13px;margin-top:4px;white-space:pre-wrap;">${UI.esc(a.summary)}</p>
        </div>` : ''}
      </div>
    `, {
      actions: '<button class="btn btn-primary" id="m-close-vas">Cerrar</button>',
    });
    document.getElementById('m-close-vas').onclick = UI.closeModal;
  }

  async function _openForm() {
    let suppliers = [];
    try { suppliers = await Api.suppliers.list(); } catch (_) {}

    UI.modal('Nueva evaluacion de proveedor', `
      <div class="form-grid">
        <div class="span2">
          <label>Proveedor *</label>
          <select id="vas-f-sup" class="input">
            <option value="">- Seleccionar -</option>
            ${suppliers.map(s => `<option value="${s.id}">${UI.esc(s.code)} - ${UI.esc(s.name)}</option>`).join('')}
          </select>
        </div>
        <div>
          <label>Periodo</label>
          <input id="vas-f-period" class="input" placeholder="ej. 2026-Q2" value="">
        </div>
        <div>
          <label>Valido hasta</label>
          <input type="date" id="vas-f-valid" class="input">
        </div>
        <div class="span2">
          <label>Recomendacion</label>
          <select id="vas-f-rec" class="input">
            <option value="">Sin recomendacion</option>
            ${Object.entries(REC_LABELS).map(([k, l]) => `<option value="${k}">${UI.esc(l)}</option>`).join('')}
          </select>
        </div>
        <div class="span2">
          <label>Resumen / observaciones</label>
          <textarea id="vas-f-summary" class="input" rows="3" placeholder="Descripcion de los hallazgos principales y conclusion de la evaluacion..."></textarea>
        </div>
        <div class="span2 notice" style="font-size:12px;">
          Los scores inherente, de control y residual se calculan automaticamente a partir del perfil TPRM del proveedor y sus cuestionarios enviados.
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="vas-m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="vas-m-save">Crear evaluacion</button>`,
    });

    document.getElementById('vas-m-cancel').onclick = UI.closeModal;
    document.getElementById('vas-m-save').onclick = async () => {
      const supId = document.getElementById('vas-f-sup').value;
      if (!supId) { UI.toast('Selecciona un proveedor', 'error'); return; }

      const body = {
        supplier_id: parseInt(supId),
        period_label: document.getElementById('vas-f-period').value.trim() || null,
        valid_until: document.getElementById('vas-f-valid').value || null,
        recommendation: document.getElementById('vas-f-rec').value || null,
        summary: document.getElementById('vas-f-summary').value.trim() || null,
      };

      try {
        const created = await Api.vendor_assessments.create(body);
        UI.closeModal();
        UI.toast(`Evaluacion ${created.code} creada`, 'success');
        await _refresh();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  return { render };
})();
