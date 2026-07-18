/* Vista de evaluaciones de proveedor — TPRM v3.9.0.
   Flujo: nueva evaluación → seleccionar proveedor → tipo (análisis de riesgo o plantilla directa)
   → envío automático por email → proveedor completa portal (2 fases si es risk_analysis)
   → usuario ve evidencias y toma decision (aprobar / rechazar / etc.)
*/
const ViewVendorAssessments = (() => {

  const DECISION_LABELS = {
    approve:                 () => t('common.approve'),
    approve_with_conditions: () => t('common.approve'),
    reject:                  () => t('common.reject'),
    request_more_info:       () => t('common.review'),
  };
  const DECISION_COLORS = {
    approve:                 '#16a34a',
    approve_with_conditions: '#f59e0b',
    reject:                  '#ef4444',
    request_more_info:       '#6366f1',
  };
  const LEVEL_LABELS = {
    critical: () => t('common.critical'),
    high:     () => t('common.high'),
    medium:   () => t('common.medium'),
    low:      () => t('common.low'),
    very_low: () => t('common.low'),
  };
  const PHASE_LABELS = {
    profiling:  () => t('tprm.questionnaire'),
    assessment: () => t('tprm.assessment'),
  };

  function _decisionLabel(k) { return DECISION_LABELS[k] ? DECISION_LABELS[k]() : k; }
  function _levelLabel(k) { return LEVEL_LABELS[k] ? LEVEL_LABELS[k]() : k; }

  function _riskColor(score) {
    if (score == null) return 'var(--text-muted)';
    if (!window.RiskLevels) {
      if (score >= 75) return 'var(--risk-critical)';
      if (score >= 50) return 'var(--risk-high)';
      if (score >= 25) return 'var(--risk-medium)';
      return 'var(--risk-low)';
    }
    return RiskLevels.colorFor(Math.round(Math.min(100, score) * 8 / 100));
  }
  function _scorePill(score, level) {
    if (score == null) return '<span style="color:var(--text-muted);">-</span>';
    const color = _riskColor(score);
    const band = window.RiskLevels ? RiskLevels.all().find(b => b.code === level) : null;
    const label = band ? band.label : (_levelLabel(level) || level || '');
    return `<span style="font-weight:700;color:${color};">${score}</span> <span style="font-size:11px;color:${color};">${UI.esc(label)}</span>`;
  }
  function _decisionBadge(rec) {
    if (!rec) return `<span style="color:var(--text-muted);font-size:12px;">${t('common.pending')}</span>`;
    const color = DECISION_COLORS[rec] || 'var(--text-muted)';
    const label = _decisionLabel(rec);
    return `<span style="display:inline-block;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:700;background:${color};color:#fff;">${UI.esc(label)}</span>`;
  }
  function _statusBadge(q) {
    if (!q) return `<span style="color:var(--text-muted);font-size:11px;">${t('common.none')}</span>`;
    if (q.submitted_at) return `<span style="color:#16a34a;font-size:11px;">${t('tprm.assessment_status.submitted')}</span>`;
    return `<span style="color:#f59e0b;font-size:11px;">${t('common.pending')}</span>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">${t('vendor.assessment.title')}</h1>
          <p class="page-sub">${t('vendor.assessment.subtitle')}</p>
        </div>
        ${Auth.canEdit() ? `<button class="btn btn-primary" id="btn-new-vas">+ ${t('vendor.assessment.new')}</button>` : ''}
      </div>
      <div style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <label style="font-size:13px;color:var(--text-muted);margin:0;">${t('common.filter')}:</label>
        <select id="vas-sup-filter" class="input" style="width:240px;">
          <option value="">${t('common.all')}</option>
        </select>
      </div>
      <div id="vas-table-wrap"><p class="text-muted">${t('common.loading')}</p></div>
    `;

    if (Auth.canEdit()) document.getElementById('btn-new-vas').onclick = () => _openForm();

    try {
      const sups = await Api.suppliers.list();
      const sel = document.getElementById('vas-sup-filter');
      if (sel) sups.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.code + ' - ' + s.name;
        sel.appendChild(opt);
      });
    } catch (_) {}

    document.getElementById('vas-sup-filter').onchange = _refresh;
    await _refresh();
  }

  async function _refresh() {
    const supplierId = document.getElementById('vas-sup-filter')?.value;
    const wrap = document.getElementById('vas-table-wrap');
    if (!wrap) return;
    wrap.innerHTML = `<p class="text-muted">${t('common.loading')}</p>`;
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
      wrap.innerHTML = `<p class="text-muted" style="margin-top:24px;text-align:center;">${t('common.no_results')}. ${t('vendor.assessment.new')}.</p>`;
      return;
    }
    const rows = data.map(a => {
      const date = a.assessment_date ? a.assessment_date.slice(0, 10) : '-';
      const typeLabel = a.assessment_type === 'risk_analysis' ? t('common.analyze') : t('tprm.questionnaire');
      const typeBadge = `<span style="font-size:11px;padding:2px 7px;border-radius:4px;background:${a.assessment_type === 'risk_analysis' ? 'rgba(89,0,141,.12)' : 'var(--bg-1)'};color:${a.assessment_type === 'risk_analysis' ? 'var(--brand-purple)' : 'var(--text-muted)'};">${UI.esc(typeLabel)}</span>`;
      const approved = a.approved_at
        ? `<span style="color:#16a34a;font-size:11px;">${t('tprm.assessment_status.approved')} ${a.approved_at.slice(0,10)}</span>`
        : '';
      return `
        <tr>
          <td>${UI.codePill ? UI.codePill(a.code) : `<b>${UI.esc(a.code)}</b>`}</td>
          <td>${UI.esc(a.supplier_name || '-')}</td>
          <td>${typeBadge}</td>
          <td style="font-size:12px;">${UI.esc(date)}</td>
          <td>${_decisionBadge(a.recommendation)}</td>
          <td style="font-size:12px;">${approved}</td>
          <td>
            <button class="btn btn-sm" data-id="${a.id}" data-act="detail">${t('common.view')}</button>
            ${Auth.canEdit() && !a.linked_risk_id ? `<button class="btn btn-sm" data-id="${a.id}" data-act="push">${t('vendor.assessment.push_to_risk')}</button>` : (a.linked_risk_id ? `<span style="color:var(--risk-medium);font-size:11px;">${t('common.approved')}</span>` : '')}
            ${Auth.canEdit() ? `<button class="btn btn-sm btn-danger" data-id="${a.id}" data-act="del">${t('common.delete')}</button>` : ''}
          </td>
        </tr>`;
    }).join('');

    wrap.innerHTML = `
      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>${t('common.name')}</th><th>${t('common.supplier')}</th><th>${t('common.type')}</th><th>${t('common.date')}</th>
              <th>${t('common.result')}</th><th>${t('tprm.assessment_status.approved')}</th><th>${t('common.actions')}</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;

    wrap.querySelectorAll('[data-act="detail"]').forEach(btn =>
      btn.onclick = () => _openDetail(parseInt(btn.dataset.id)));

    wrap.querySelectorAll('[data-act="push"]').forEach(btn =>
      btn.onclick = async () => {
        if (!await UI.confirm(t('tprm.push_to_risk') + '?')) return;
        try {
          const res = await Api.vendor_assessments.pushToRegister(btn.dataset.id);
          UI.toast(`${t('common.risk')} ${res.risk_code} ${t('common.success')}`, 'success');
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      });

    wrap.querySelectorAll('[data-act="del"]').forEach(btn =>
      btn.onclick = async () => {
        if (!await UI.confirm(t('common.confirm_delete'))) return;
        try {
          await Api.vendor_assessments.del(btn.dataset.id);
          UI.toast(t('common.success'), 'success');
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      });
  }

  // ---- Detalle completo con evidencias y decision ----
  async function _openDetail(aid) {
    UI.modal(t('common.loading'), `<p class="text-muted">${t('common.loading')}</p>`, {});
    let a;
    try {
      a = await Api.vendor_assessments.detail(aid);
    } catch (e) {
      UI.modal(t('common.error'), `<p class="notice">${UI.esc(e.message)}</p>`, {
        actions: `<button class="btn" onclick="UI.closeModal()">${t('common.close')}</button>`,
      });
      return;
    }
    _renderDetail(a);
  }

  function _renderDetail(a) {
    const profQ = a.profiling_questionnaire;
    const assQ  = a.assessment_questionnaire;

    // --- Panel de cuestionario ---
    function _qPanel(q, label) {
      if (!q) return `<div class="sq-card" style="padding:16px;"><p style="color:var(--text-muted);font-size:13px;">${label}: ${t('common.pending')}.</p></div>`;

      const submitted = !!q.submitted_at;
      const statusColor = submitted ? '#16a34a' : '#f59e0b';
      const statusText  = submitted ? `${t('tprm.assessment_status.submitted')} ${q.submitted_at.slice(0,10)}` : t('common.pending');

      // NC badges
      const ncHtml = (q.major_nc != null) ? `
        <span style="margin-right:6px;font-size:11px;padding:2px 8px;border-radius:4px;background:#fef2f2;color:#dc2626;font-weight:600;">
          NC ${t('nonconformities.severity.major')}: ${q.major_nc}
        </span>
        <span style="font-size:11px;padding:2px 8px;border-radius:4px;background:#fff7ed;color:#ea580c;font-weight:600;">
          NC ${t('nonconformities.severity.minor')}: ${q.minor_nc}
        </span>` : '';

      // Preguntas + respuestas acordeon
      const qaRows = (q.questions || []).map(qq => {
        const ans = (q.answers || {})[qq.id];
        const evid = (q.evidence || {})[qq.id];
        const ansLabel = ans != null ? String(ans) : '—';
        const _fn = (evid?.filename || evid?.stored_name || 'evidencia').replace(/'/g, '');
        const evidHtml = evid ? `
          <button onclick="ViewVendorAssessments._dlEvidence(${a.id},'${encodeURIComponent(qq.id)}','${_fn}');event.stopPropagation();"
             style="background:none;border:none;cursor:pointer;font-size:11px;color:var(--brand-purple);text-decoration:underline;padding:0;">
            ${t('evidence.title')}: ${UI.esc(evid.filename || evid.stored_name || 'fichero')}
          </button>` : '';
        return `<tr>
          <td style="font-size:12px;padding:6px 8px;color:var(--text-muted);width:40px;">${UI.esc(qq.id)}</td>
          <td style="font-size:12px;padding:6px 8px;">${UI.esc(qq.text || '')}</td>
          <td style="font-size:12px;padding:6px 8px;font-weight:600;">${UI.esc(ansLabel)}</td>
          <td style="font-size:12px;padding:6px 8px;">${evidHtml}</td>
        </tr>`;
      }).join('');

      // AI review
      let aiHtml = '';
      if (q.ai_review) {
        const r = q.ai_review;
        if (r.error) {
          aiHtml = `<p style="font-size:12px;color:var(--text-muted);">${t('tprm.ai_review')}: ${UI.esc(r.error)}</p>`;
        } else {
          const flags = (r.red_flags || []).map(f => `<li style="font-size:12px;">${UI.esc(f)}</li>`).join('');
          const fups = (r.follow_up_questions || []).map(f => `<li style="font-size:12px;">${UI.esc(f)}</li>`).join('');
          aiHtml = `
            <div style="margin-top:12px;padding:12px;background:rgba(89,0,141,.05);border-radius:8px;border:1px solid rgba(89,0,141,.15);">
              <div style="font-size:12px;font-weight:600;margin-bottom:8px;color:var(--brand-purple);">${t('tprm.ai_review')}</div>
              <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:8px;">
                <span style="font-size:12px;">${t('common.score')}: <strong>${r.ai_score ?? '-'}/100</strong></span>
                <span style="font-size:12px;">${t('common.level')}: <strong>${r.confidence != null ? Math.round(r.confidence * 100) + '%' : '-'}</strong></span>
                <span style="font-size:12px;">${t('common.result')}: <strong>${UI.esc(r.control_coverage_assessment || '-')}</strong></span>
              </div>
              ${r.rationale ? `<p style="font-size:12px;color:var(--text-muted);margin:0 0 8px;">${UI.esc(r.rationale)}</p>` : ''}
              ${flags ? `<div style="font-size:12px;font-weight:600;margin-bottom:4px;">${t('common.severity')}:</div><ul style="margin:0 0 8px;padding-left:18px;">${flags}</ul>` : ''}
              ${fups ? `<div style="font-size:12px;font-weight:600;margin-bottom:4px;">${t('common.notes')}:</div><ul style="margin:0;padding-left:18px;">${fups}</ul>` : ''}
              ${r.needs_manual_review ? `<p style="font-size:11px;color:#f59e0b;margin:8px 0 0;font-weight:600;">${t('common.review')}.</p>` : ''}
            </div>`;
        }
      }

      return `
        <div style="border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:12px;">
          <div style="background:var(--bg-1);padding:12px 16px;display:flex;justify-content:space-between;align-items:center;">
            <div>
              <span style="font-size:13px;font-weight:600;">${UI.esc(label)}</span>
              <span style="margin-left:8px;font-size:11px;color:var(--text-muted);">${UI.esc(q.code)}</span>
              ${q.template_code ? `<span style="margin-left:6px;font-size:10px;color:var(--text-muted);">${UI.esc(q.template_code)}</span>` : ''}
            </div>
            <span style="font-size:11px;color:${statusColor};font-weight:600;">${UI.esc(statusText)}</span>
          </div>
          ${submitted ? `
          <div style="padding:12px 16px;border-bottom:1px solid var(--border);display:flex;gap:16px;flex-wrap:wrap;align-items:center;">
            <span style="font-size:13px;">${t('common.score')}: <strong>${q.score ?? '-'}/100</strong></span>
            ${q.residual_risk_level ? `<span style="font-size:12px;">${t('suppliers.residual_risk')}: <strong>${UI.esc(_levelLabel(q.residual_risk_level))}</strong></span>` : ''}
            ${ncHtml}
          </div>
          <details style="margin:0;">
            <summary style="padding:10px 16px;font-size:12px;font-weight:600;cursor:pointer;color:var(--brand-purple);">
              ${t('common.show')} (${(q.questions || []).length})
            </summary>
            <div style="padding:0 16px 16px;">
              <div class="table-wrap" style="max-height:320px;overflow-y:auto;">
                <table class="data" style="font-size:12px;">
                  <thead><tr><th>ID</th><th>${t('common.description')}</th><th>${t('common.result')}</th><th>${t('evidence.title')}</th></tr></thead>
                  <tbody>${qaRows}</tbody>
                </table>
              </div>
              ${aiHtml}
            </div>
          </details>` : `<div style="padding:12px 16px;font-size:12px;color:var(--text-muted);">
            ${t('common.pending')}.
            ${q.token ? `<br><a href="/supplier-q?token=${encodeURIComponent(q.token)}" target="_blank" rel="noopener" style="color:var(--brand-purple);">${t('common.link')}</a>` : ''}
          </div>`}
        </div>`;
    }

    // --- Panel de decision ---
    const hasSubmittedQ = (assQ && assQ.submitted_at) || (!profQ && assQ && assQ.submitted_at);
    const currentDecision = a.recommendation;

    const decisionPanel = hasSubmittedQ ? `
      <div style="margin-top:16px;padding:16px;background:var(--bg-1);border-radius:8px;border:1px solid var(--border);">
        <div style="font-size:13px;font-weight:600;margin-bottom:12px;">${t('common.result')}</div>
        ${currentDecision ? `
          <div style="margin-bottom:12px;">
            ${_decisionBadge(currentDecision)}
            ${a.decision_at ? `<span style="font-size:11px;color:var(--text-muted);margin-left:8px;">${a.decision_at.slice(0,10)}</span>` : ''}
            ${a.decision_notes ? `<p style="font-size:12px;margin:8px 0 0;color:var(--text-base);">"${UI.esc(a.decision_notes)}"</p>` : ''}
          </div>
          <p style="font-size:12px;color:var(--text-muted);">${t('common.change')}.</p>
        ` : `<p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">${t('common.select')}:</p>`}
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;" id="vas-decision-btns">
          ${Object.entries(DECISION_LABELS).map(([k]) => `
            <button class="btn btn-sm" data-decision="${k}"
              style="border-color:${DECISION_COLORS[k]};color:${DECISION_COLORS[k]};${currentDecision === k ? `background:${DECISION_COLORS[k]};color:#fff;` : ''}">
              ${UI.esc(_decisionLabel(k))}
            </button>`).join('')}
        </div>
        <div style="display:flex;gap:8px;align-items:flex-end;" id="vas-decision-confirm" style="display:none;">
          <div style="flex:1;">
            <label style="font-size:12px;color:var(--text-muted);">${t('common.notes')} (${t('common.optional')})</label>
            <textarea id="vas-decision-notes" class="input" rows="2" style="margin-top:4px;"
              placeholder="${t('common.placeholder')}">${UI.esc(a.decision_notes || '')}</textarea>
          </div>
          <button class="btn btn-primary" id="vas-decision-save">${t('common.save')}</button>
        </div>
      </div>` : `
      <div style="margin-top:16px;padding:16px;background:var(--bg-1);border-radius:8px;border:1px solid var(--border);">
        <p style="font-size:13px;color:var(--text-muted);margin:0;">
          ${t('common.pending')}.
        </p>
      </div>`;

    // --- Score por dominio ---
    const domainRows = a.score_by_domain && Object.keys(a.score_by_domain).length
      ? Object.entries(a.score_by_domain).map(([domain, score]) => {
          const pct = Math.max(0, Math.min(100, score));
          const color = _riskColor(100 - pct);
          return `<div style="margin-bottom:8px;">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
              <span>${UI.esc(domain)}</span>
              <span style="font-weight:600;color:${color};">${pct}/100</span>
            </div>
            <div style="background:var(--border);border-radius:4px;height:5px;">
              <div style="background:${color};width:${pct}%;height:5px;border-radius:4px;"></div>
            </div>
          </div>`;
        }).join('')
      : '';

    const bodyHtml = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
        <div>
          <p style="margin:0 0 4px;font-size:12px;color:var(--text-muted);">${t('common.supplier')}</p>
          <p style="margin:0;font-weight:600;">${UI.esc(a.supplier_name || '-')}</p>
        </div>
        <div>
          <p style="margin:0 0 4px;font-size:12px;color:var(--text-muted);">${t('common.type')}</p>
          <p style="margin:0;font-size:13px;">${a.assessment_type === 'risk_analysis' ? t('common.analyze') : t('tprm.questionnaire')}</p>
        </div>
        <div>
          <p style="margin:0 0 4px;font-size:12px;color:var(--text-muted);">${t('suppliers.inherent_risk')}</p>
          <p style="margin:0;">${_scorePill(a.inherent_risk_score, a.inherent_risk_level)}</p>
        </div>
        <div>
          <p style="margin:0 0 4px;font-size:12px;color:var(--text-muted);">${t('suppliers.residual_risk')}</p>
          <p style="margin:0;">${_scorePill(a.residual_risk_score, a.residual_risk_level)}</p>
        </div>
      </div>

      ${domainRows ? `
      <details style="margin-bottom:16px;">
        <summary style="font-size:12px;font-weight:600;cursor:pointer;color:var(--text-muted);">${t('tprm.domain_scores')}</summary>
        <div style="margin-top:10px;">${domainRows}</div>
      </details>` : ''}

      <div style="font-size:13px;font-weight:600;margin:0 0 10px;">${t('tprm.questionnaire')}</div>

      ${a.assessment_type === 'risk_analysis'
        ? _qPanel(profQ, `${t('common.level')} 1 — ${t('tprm.questionnaire')}`) + _qPanel(assQ, `${t('common.level')} 2 — ${t('tprm.assessment')}`)
        : _qPanel(assQ, t('tprm.questionnaire'))}

      ${decisionPanel}
    `;

    const footerActions = `
      <button class="btn" id="vas-det-close">${t('common.close')}</button>
      ${Auth.canEdit() && !a.approved_at ? `<button class="btn" id="vas-det-approve">${t('vendor.assessment.approve')}</button>` : ''}
      ${Auth.canEdit() && a.approved_at && a.is_current !== false ? `<button class="btn" id="vas-det-newversion">${t('common.version')}</button>` : ''}
      ${Auth.canEdit() && !a.linked_risk_id ? `<button class="btn btn-primary" id="vas-det-push">${t('vendor.assessment.push_to_risk')}</button>` : ''}
    `;

    UI.modal(`${t('tprm.assessment')} ${UI.esc(a.code)}`, bodyHtml, { actions: footerActions });

    document.getElementById('vas-det-close').onclick = UI.closeModal;

    const approveBtn = document.getElementById('vas-det-approve');
    if (approveBtn) approveBtn.onclick = async () => {
      if (!await UI.confirm(t('vendor.assessment.approve') + '?')) return;
      try {
        await Api.vendor_assessments.approve(a.id);
        UI.toast(t('common.success'), 'success');
        UI.closeModal();
        await _refresh();
      } catch (e) { UI.toast(e.message, 'error'); }
    };

    const newVersionBtn = document.getElementById('vas-det-newversion');
    if (newVersionBtn) newVersionBtn.onclick = async () => {
      if (!await UI.confirm(
        `${t('common.version')} ${UI.esc(a.supplier_name||'')} — ${UI.esc(a.code)}`
      )) return;
      try {
        const draft = await Api.vendor_assessments.newVersion(a.id);
        UI.toast(`${t('common.version')} ${draft.code} ${t('tprm.assessment_status.draft')}`, 'success');
        UI.closeModal();
        await _refresh();
      } catch (e) { UI.toast(e.message, 'error'); }
    };

    const pushBtn = document.getElementById('vas-det-push');
    if (pushBtn) pushBtn.onclick = async () => {
      if (!await UI.confirm(t('tprm.push_to_risk') + '?')) return;
      try {
        const res = await Api.vendor_assessments.pushToRegister(a.id);
        UI.toast(`${t('common.risk')} ${res.risk_code} ${t('common.success')}`, 'success');
        UI.closeModal();
        await _refresh();
      } catch (e) { UI.toast(e.message, 'error'); }
    };

    // --- Decision interactiva ---
    if (hasSubmittedQ) {
      let pendingDecision = currentDecision || null;
      const confirmDiv = document.getElementById('vas-decision-confirm');

      document.querySelectorAll('#vas-decision-btns [data-decision]').forEach(btn => {
        btn.onclick = () => {
          pendingDecision = btn.dataset.decision;
          // Highlight seleccionado
          document.querySelectorAll('#vas-decision-btns [data-decision]').forEach(b => {
            const k = b.dataset.decision;
            b.style.background = k === pendingDecision ? DECISION_COLORS[k] : '';
            b.style.color = k === pendingDecision ? '#fff' : DECISION_COLORS[k];
          });
          if (confirmDiv) confirmDiv.style.display = 'flex';
        };
      });

      const saveBtn = document.getElementById('vas-decision-save');
      if (saveBtn) saveBtn.onclick = async () => {
        if (!pendingDecision) return;
        const notes = document.getElementById('vas-decision-notes')?.value.trim() || null;
        try {
          await Api.vendor_assessments.decide(a.id, { decision: pendingDecision, notes });
          UI.toast(`${t('common.result')}: "${_decisionLabel(pendingDecision)}" ${t('common.success')}`, 'success');
          UI.closeModal();
          await _refresh();
        } catch (e) { UI.toast(e.message, 'error'); }
      };
    }
  }

  // ---- Mensaje de email por defecto ----
  function _defaultEmailMessage(supplierName, contactName, orgName) {
    const to = contactName || supplierName || 'equipo';
    const org = orgName || 'nuestra organización';
    return `Estimado/a ${to}:\n\nComo parte de nuestro proceso de evaluación de proveedores en ${org}, le solicitamos que complete el cuestionario de seguridad adjunto.\n\nEl cuestionario es confidencial y sus respuestas serán utilizadas exclusivamente para evaluar el nivel de seguridad en el marco de nuestra relacion contractual.\n\nAnte cualquier duda, puede responder a este correo.\n\nGracias por su colaboracion.`;
  }

  // ---- Form nueva evaluación ----
  async function _openForm() {
    let suppliers = [], sysTpls = [], customTpls = [], orgName = '';
    try { suppliers = await Api.suppliers.list(); } catch (_) {}
    try {
      const tplData = await Api.tprm.templates();
      sysTpls = (tplData || []).filter(t => t.is_system_template !== false);
    } catch (_) {}
    try { customTpls = await Api.tprm.customTemplates(); } catch (_) {}
    try {
      const me = JSON.parse(localStorage.getItem('riskhub_user') || '{}');
      orgName = me.organization_name || '';
    } catch (_) {}

    const sysOptions = sysTpls
      .filter(tpl => tpl.code !== 'RH_TPRM_PROFILING_v1')
      .map(tpl => `<option value="sys:${UI.esc(tpl.code)}">${UI.esc(tpl.name)}</option>`)
      .join('');
    const customOptions = customTpls.length
      ? customTpls.map(tpl => `<option value="custom:${tpl.id}">${UI.esc(tpl.name)}</option>`).join('')
      : '';

    // Construir mapa de proveedores para el preview de email
    const supMap = {};
    suppliers.forEach(s => { supMap[s.id] = s; });

    UI.modal(t('vendor.assessment.new'), `
      <div class="form-grid">
        <div class="span2">
          <label>${t('common.supplier')} *</label>
          <select id="vas-f-sup" class="input">
            <option value="">- ${t('common.select_option')} -</option>
            ${suppliers.map(s => `<option value="${s.id}"
              data-email="${UI.esc(s.contact_email || '')}"
              data-contact="${UI.esc(s.contact_name || '')}"
              data-name="${UI.esc(s.name || '')}">
              ${UI.esc(s.code)} - ${UI.esc(s.name)}${s.contact_email ? ' &lt;' + UI.esc(s.contact_email) + '&gt;' : ''}
            </option>`).join('')}
          </select>
        </div>
        <div class="span2">
          <label>${t('common.type')} *</label>
          <select id="vas-f-type" class="input">
            <option value="risk_analysis">${t('common.analyze')}</option>
            <optgroup label="${t('tprm.questionnaire')}">
              ${sysOptions || `<option disabled>${t('common.no_options')}</option>`}
            </optgroup>
            ${customOptions ? `<optgroup label="${t('vendor.templates.custom_template')}">${customOptions}</optgroup>` : ''}
          </select>
        </div>
        <div>
          <label>${t('common.version')}</label>
          <input id="vas-f-period" class="input" placeholder="ej. 2026-Q2">
        </div>
        <div>
          <label>${t('common.due_date')}</label>
          <input type="date" id="vas-f-valid" class="input">
        </div>

        <div class="span2" style="border-top:1px solid var(--border);padding-top:14px;margin-top:4px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
            <label style="margin:0;font-weight:600;">${t('common.email')}</label>
            <button type="button" id="vas-f-reset-msg" class="btn btn-sm" style="font-size:11px;">${t('common.reset')}</button>
          </div>
          <div>
            <label style="font-size:12px;color:var(--text-muted);">${t('common.title')}</label>
            <input id="vas-f-subject" class="input" style="margin-bottom:8px;"
              placeholder="${t('common.placeholder')}">
          </div>
          <div>
            <label style="font-size:12px;color:var(--text-muted);">${t('common.description')}</label>
            <textarea id="vas-f-msg" class="input" rows="7"
              style="font-size:13px;line-height:1.6;margin-top:4px;"
              placeholder="${t('common.placeholder')}">${UI.esc(_defaultEmailMessage('', '', orgName))}</textarea>
          </div>
        </div>
      </div>
    `, {
      actions: `<button class="btn" id="vas-m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="vas-m-save">${t('common.create')} & ${t('common.send')}</button>`,
    });

    // Al cambiar proveedor: actualizar el mensaje con el nombre del contacto
    const supSel = document.getElementById('vas-f-sup');
    supSel.onchange = () => {
      const opt = supSel.options[supSel.selectedIndex];
      const contact = opt?.dataset?.contact || '';
      const name    = opt?.dataset?.name || '';
      const msgArea = document.getElementById('vas-f-msg');
      if (msgArea) {
        msgArea.value = _defaultEmailMessage(name, contact, orgName);
      }
    };

    document.getElementById('vas-f-reset-msg').onclick = () => {
      const opt = supSel.options[supSel.selectedIndex];
      const contact = opt?.dataset?.contact || '';
      const name    = opt?.dataset?.name || '';
      document.getElementById('vas-f-msg').value = _defaultEmailMessage(name, contact, orgName);
      document.getElementById('vas-f-subject').value = '';
    };

    document.getElementById('vas-m-cancel').onclick = UI.closeModal;
    document.getElementById('vas-m-save').onclick = async () => {
      const supId = document.getElementById('vas-f-sup').value;
      if (!supId) { UI.toast(t('common.select'), 'error'); return; }
      const typeVal  = document.getElementById('vas-f-type').value;
      const emailMsg = document.getElementById('vas-f-msg').value.trim();
      const emailSub = document.getElementById('vas-f-subject').value.trim();

      const body = {
        supplier_id: parseInt(supId),
        assessment_type: typeVal === 'risk_analysis' ? 'risk_analysis' : 'direct',
        period_label: document.getElementById('vas-f-period').value.trim() || null,
        valid_until: document.getElementById('vas-f-valid').value || null,
        email_message: emailMsg || null,
        email_subject: emailSub || null,
      };

      if (typeVal.startsWith('sys:')) {
        body.template_code = typeVal.slice(4);
      } else if (typeVal.startsWith('custom:')) {
        body.custom_template_id = parseInt(typeVal.slice(7));
      }

      const saveBtn = document.getElementById('vas-m-save');
      if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = t('common.loading'); }

      try {
        const created = await Api.vendor_assessments.create(body);
        UI.closeModal();
        if (created.email_sent) {
          UI.toast(`${t('tprm.assessment')} ${created.code} ${t('common.success')} — ${t('common.email')} ${created.email_warning || t('common.supplier')}`, 'success');
        } else {
          const warn = created.email_warning || t('common.error');
          UI.toast(`${t('tprm.assessment')} ${created.code} ${t('common.success')} — ${t('common.email')}: ${warn}`, 'warning');
        }
        await _refresh();
      } catch (e) {
        UI.toast(e.message, 'error');
        if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = `${t('common.create')} & ${t('common.send')}`; }
      }
    };
  }

  async function _dlEvidence(aid, questionIdEncoded, filename) {
    try {
      const qid = decodeURIComponent(questionIdEncoded);
      const path = `/api/vendor-assessments/${aid}/evidence/${encodeURIComponent(qid)}`;
      await Api.download(path, filename || 'evidencia');
    } catch (e) {
      UI.toast(t('common.error') + ': ' + e.message, 'error');
    }
  }

  return { render, _dlEvidence };
})();
