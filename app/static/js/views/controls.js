/* Vista Controles - catálogo ISO 27002:2022 + implementaciónes. */
const ViewControls = {
  _tab: 'impls', _catalog: [], _sortCol: 'id', _sortAsc: false, _overdueOnly: false,

  _framework: 'iso27001',

  async render(main) {
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      t('controls.title'),
      t('controls.subtitle'),
      canEdit ? `<button class="btn btn-primary" id="btn-new-impl">+ ${t('controls.new')}</button>` : ''
    ) + `
      <div class="toolbar">
        <button class="btn ${ViewControls._tab==='impls'?'btn-primary':''}" data-tab="impls">${t('controls.implementations')}</button>
        <button class="btn ${ViewControls._tab==='catalog'?'btn-primary':''}" data-tab="catalog">${t('controls.catalog_tab')}</button>
        <span class="spacer"></span>
        ${ViewControls._tab === 'catalog' ? `
          <select id="c-framework" style="font-size:13px;padding:4px 10px;border-radius:6px;border:1px solid var(--border);background:var(--bg-1);font-weight:600;color:var(--brand-purple);">
            <option value="iso27001" ${ViewControls._framework==='iso27001'?'selected':''}>ISO 27001 / ISO 27002:2022</option>
            <option value="ens"      ${ViewControls._framework==='ens'?'selected':''}>ENS RD 311/2022</option>
            <option value="nist_csf" ${ViewControls._framework==='nist_csf'?'selected':''}>NIST CSF 2.0</option>
            <option value="nis2"     ${ViewControls._framework==='nis2'?'selected':''}>NIS2 — Art. 21</option>
            <option value="gdpr"     ${ViewControls._framework==='gdpr'?'selected':''}>GDPR / RGPD</option>
            <option value="pcidss"   ${ViewControls._framework==='pcidss'?'selected':''}>PCI-DSS v4.0</option>
            <option value="iso22301" ${ViewControls._framework==='iso22301'?'selected':''}>ISO 22301:2019</option>
          </select>` : ''}
        <input type="search" id="c-search" placeholder="${t('common.search')}...">
        <select id="c-theme" ${ViewControls._tab==='catalog'?'':'style=""'}>
          <option value="">${t('common.all')}</option>
          <option value="organizational">${t('controls.theme_org')}</option>
          <option value="people">${t('controls.theme_people')}</option>
          <option value="physical">${t('controls.theme_physical')}</option>
          <option value="technological">${t('controls.theme_tech')}</option>
        </select>
        <select id="c-status" style="${ViewControls._tab==='impls'?'':'display:none;'}">
          <option value="">${t('common.all')}</option>
          <option value="implemented">${t('controls.implementation_status.implemented')}</option>
          <option value="partial">${t('controls.implementation_status.partial')}</option>
          <option value="planned">${t('controls.implementation_status.planned')}</option>
          <option value="not_implemented">${t('controls.implementation_status.not_implemented')}</option>
        </select>
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;white-space:nowrap;${ViewControls._tab==='impls'?'':'display:none;'}">
          <input type="checkbox" id="c-overdue" ${ViewControls._overdueOnly?'checked':''}> ${t('controls.overdue_only')}
        </label>
        <button class="btn btn-ghost" id="btn-soa-csv" title="${t('controls.export_soa')}">${t('controls.soa_short')} CSV</button>
        <button class="btn btn-ghost" id="btn-ccm-run" title="${t('ccm.title')}">Tests CCM</button>
      </div>
      <div id="c-list"></div>
    `;

    document.querySelectorAll('.toolbar [data-tab]').forEach(b => b.onclick = () => {
      ViewControls._tab = b.dataset.tab;
      ViewControls.render(main);
    });
    document.getElementById('c-framework')?.addEventListener('change', (e) => {
      ViewControls._framework = e.target.value;
      ViewControls._reload();
    });
    document.getElementById('c-search').oninput = () => ViewControls._reload();
    document.getElementById('c-theme').onchange = () => ViewControls._reload();
    document.getElementById('c-status').onchange = () => ViewControls._reload();
    const overdueChk = document.getElementById('c-overdue');
    if (overdueChk) overdueChk.onchange = () => {
      ViewControls._overdueOnly = overdueChk.checked;
      ViewControls._reload();
    };
    if (canEdit) document.getElementById('btn-new-impl').onclick = () => ViewControls._editImpl();
    document.getElementById('btn-soa-csv').onclick = async () => {
      try { await Api.controls.exportSoaCsv(); UI.toast(t('controls.export_soa'), 'success'); }
      catch (e) { UI.toast(e.message, 'error'); }
    };
    document.getElementById('btn-ccm-run').onclick = async () => {
      if (typeof ViewCcm !== 'undefined' && typeof ViewCcm._runTests === 'function') {
        ViewCcm._runTests();
      } else {
        try {
          UI.toast('Ejecutando tests CCM...', 'info');
          const result = await Api.post('/api/ccm/run', {});
          const passed = result.passed ?? result.tests_passed ?? '?';
          const failed = result.failed ?? result.tests_failed ?? '?';
          const total = result.total ?? result.tests_total ?? '?';
          UI.toast(`CCM: ${passed}/${total} tests OK, ${failed} fallos`, failed > 0 ? 'warning' : 'success');
        } catch (e) {
          UI.toast('Error ejecutando CCM: ' + e.message, 'error');
        }
      }
    };

    ViewControls._catalog = await Api.controls.list({});
    ViewControls._reload();
  },

  async _reload() {
    const list = document.getElementById('c-list');
    list.innerHTML = `<div class="notice">${t('common.loading_data')}</div>`;
    try {
      if (ViewControls._tab === 'catalog') {
        await ViewControls._renderCatalog();
      } else {
        await ViewControls._renderImpls();
      }
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _FRAMEWORK_GROUPS: {
    iso27001: null,
    ens: [
      { id: 'identificacion', label: t('ui_views.ens_identification'), keywords: ['organizational', 'risk', 'governance', 'policy'] },
      { id: 'proteccion',     label: t('ui_views.ens_protection'),  keywords: ['access', 'cryptography', 'physical', 'network', 'human', 'asset'] },
      { id: 'deteccion',      label: t('ui_views.ens_detection'),      keywords: ['monitoring', 'detection', 'audit', 'log'] },
      { id: 'respuesta',      label: t('ui_views.ens_response'),           keywords: ['incident', 'response', 'communication'] },
      { id: 'recuperacion',   label: t('ui_views.ens_recovery'),                 keywords: ['recovery', 'continuity', 'backup', 'resilience'] },
    ],
    nist_csf: [
      { id: 'GOVERN',   label: 'GV — Govern',   concepts: ['govern'] },
      { id: 'IDENTIFY',  label: 'ID — Identify',  concepts: ['identify'] },
      { id: 'PROTECT',   label: 'PR — Protect',   concepts: ['protect'] },
      { id: 'DETECT',    label: 'DE — Detect',    concepts: ['detect'] },
      { id: 'RESPOND',   label: 'RS — Respond',   concepts: ['respond'] },
      { id: 'RECOVER',   label: 'RC — Recover',   concepts: ['recover'] },
    ],
    nis2: [
      { id: 'a', label: 'Art. 21.2.a — Políticas de análisis de riesgos y seguridad',          keywords: ['risk', 'policy', 'organizational'] },
      { id: 'b', label: 'Art. 21.2.b — Gestión de incidentes',                                  keywords: ['incident', 'response', 'detect'] },
      { id: 'c', label: 'Art. 21.2.c — Continuidad del negocio y gestión de crisis',            keywords: ['continuity', 'backup', 'recovery'] },
      { id: 'd', label: 'Art. 21.2.d — Seguridad de la cadena de suministro',                   keywords: ['supplier', 'supply', 'third'] },
      { id: 'e', label: 'Art. 21.2.e — Seguridad en desarrollo y mantenimiento',                keywords: ['development', 'change', 'vulnerability'] },
      { id: 'f', label: 'Art. 21.2.f — Políticas para evaluar eficacia de medidas',             keywords: ['audit', 'review', 'assessment'] },
      { id: 'g', label: 'Art. 21.2.g — Ciberhigiene y formación',                              keywords: ['awareness', 'training', 'human'] },
      { id: 'h', label: 'Art. 21.2.h — Políticas de criptografía',                             keywords: ['cryptography', 'encryption'] },
      { id: 'i', label: 'Art. 21.2.i — Seguridad RRHH, control de acceso y activos',           keywords: ['access', 'asset', 'human'] },
      { id: 'j', label: 'Art. 21.2.j — MFA y comunicaciones seguras',                          keywords: ['authentication', 'network', 'secure'] },
    ],
    gdpr: [
      { id: 'art5',   label: 'Art. 5 — Principios de tratamiento (minimización, integridad)',   keywords: ['data', 'privacy', 'integrity'] },
      { id: 'art25',  label: 'Art. 25 — Privacidad por diseño',                                keywords: ['design', 'privacy', 'data'] },
      { id: 'art32',  label: 'Art. 32 — Seguridad del tratamiento',                            keywords: ['encryption', 'access', 'network', 'backup'] },
      { id: 'art33',  label: 'Art. 33/34 — Notificación de violaciones',                       keywords: ['incident', 'response', 'detect'] },
    ],
    pcidss: null,
    iso22301: [
      { id: 'cl6', label: 'Cl. 6 — Planificación (BIA, análisis de riesgos)',  keywords: ['risk', 'assessment', 'continuity'] },
      { id: 'cl8', label: 'Cl. 8 — Operación (BCP, DR, comunicación)',         keywords: ['continuity', 'backup', 'recovery', 'communication'] },
      { id: 'cl9', label: 'Cl. 9 — Evaluación del desempeño',                  keywords: ['audit', 'review', 'monitoring'] },
    ],
  },

  async _renderCatalog() {
    const q = document.getElementById('c-search')?.value.toLowerCase() || '';
    const theme = document.getElementById('c-theme')?.value || '';
    const fw = ViewControls._framework || 'iso27001';
    const list = document.getElementById('c-list');
    let data = ViewControls._catalog;
    if (q) data = data.filter(c => (c.name + c.code + (c.description || '')).toLowerCase().includes(q));
    if (theme) data = data.filter(c => c.theme === theme);

    const canEdit = Auth.canEdit();

    const _fwLabel = {
      iso27001: 'ISO 27001:2022 / ISO 27002:2022',
      ens: 'ENS RD 311/2022',
      nist_csf: 'NIST CSF 2.0',
      nis2: 'NIS2 — Art. 21',
      gdpr: 'GDPR / RGPD',
      pcidss: 'PCI-DSS v4.0',
      iso22301: 'ISO 22301:2019',
    }[fw] || fw;

    const _controlRow = (c) => `
      <tr>
        <td>${UI.codePill(c.code)}</td>
        <td><strong>${UI.esc(c.name)}</strong>
            ${c.description ? `<div style="font-size:11px;color:var(--text-subtle);">${UI.esc(c.description.slice(0,120))}${c.description.length>120?'…':''}</div>` : ''}</td>
        <td><span style="font-size:11px;color:var(--text-muted);">${UI.esc(c.theme||'-')}</span></td>
        <td style="font-size:11px;">${(c.control_type||[]).join(', ')}</td>
        <td style="font-size:11px;font-family:var(--font-mono);">${(c.properties||[]).map(p => p[0].toUpperCase()).join(' ')}</td>
        <td style="text-align:center;">
          ${canEdit
            ? `<label title="Marcar como control obligatorio (piso residual)" style="cursor:pointer;display:inline-flex;align-items:center;gap:4px;">
                <input type="checkbox" data-mandatory-id="${c.id}" ${c.is_mandatory ? 'checked' : ''}>
                ${c.is_mandatory ? `<span style="font-size:10px;font-weight:700;color:var(--danger);">OBLIGATORIO</span>` : ''}
               </label>`
            : (c.is_mandatory ? `<span style="font-size:10px;font-weight:700;color:var(--danger);">OBLIGATORIO</span>` : '')}
        </td>
      </tr>`;

    const _tableHtml = (rows) => `<div class="table-wrap"><table class="data">
      <thead><tr>
        <th>${t('controls.control_code')}</th>
        <th>${t('controls.control_name')}</th>
        <th>${t('controls.theme')}</th>
        <th>${t('common.type')}</th>
        <th>${t('controls.properties')}</th>
        <th>${t('controls.mandatory')}</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;

    const groups = ViewControls._FRAMEWORK_GROUPS[fw];

    let html = `<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
      <span style="font-size:13px;font-weight:700;color:var(--brand-purple);">${UI.esc(_fwLabel)}</span>
      <span style="font-size:12px;color:var(--text-muted);">${t('controls.catalog_controls_count', { n: data.length })}</span>
    </div>`;

    if (!groups) {
      // ISO 27001 / PCI-DSS: tabla plana agrupada por tema ISO 27002
      const byTheme = {};
      data.forEach(c => {
        const k = c.theme || 'other';
        if (!byTheme[k]) byTheme[k] = [];
        byTheme[k].push(c);
      });
      const order = ['organizational','people','physical','technological'];
      const keys = [...order.filter(k => byTheme[k]), ...Object.keys(byTheme).filter(k => !order.includes(k))];
      const themeLabel = { organizational: t('controls.theme_org'), people: t('controls.theme_people'), physical: t('controls.theme_physical'), technological: t('controls.theme_tech') };
      if (!data.length) {
        html += `<p style="color:var(--text-muted);font-size:13px;padding:16px 0;">${t('controls.no_results')}</p>`;
      } else {
        html += keys.map(k => {
          const items = byTheme[k];
          return `<details open style="margin-bottom:12px;">
            <summary style="cursor:pointer;font-weight:700;font-size:13px;padding:6px 0;border-bottom:1px solid var(--border);margin-bottom:6px;color:var(--text-base);">
              ${UI.esc(themeLabel[k] || k)} <span style="font-weight:400;color:var(--text-muted);">(${items.length})</span>
            </summary>
            ${_tableHtml(items.map(_controlRow).join(''))}
          </details>`;
        }).join('');
      }
    } else if (fw === 'nist_csf') {
      // NIST CSF: agrupar por cybersec_concepts
      groups.forEach(g => {
        const matched = data.filter(c => (c.cybersec_concepts || []).some(cc => g.concepts.includes(cc.toLowerCase())));
        if (!matched.length) return;
        html += `<details open style="margin-bottom:12px;">
          <summary style="cursor:pointer;font-weight:700;font-size:13px;padding:6px 0;border-bottom:1px solid var(--border);margin-bottom:6px;color:var(--brand-purple);">
            ${UI.esc(g.label)} <span style="font-weight:400;color:var(--text-muted);">(${matched.length})</span>
          </summary>
          ${_tableHtml(matched.map(_controlRow).join(''))}
        </details>`;
      });
      const ungrouped = data.filter(c => !groups.some(g => (c.cybersec_concepts || []).some(cc => g.concepts.includes(cc.toLowerCase()))));
      if (ungrouped.length) {
        html += `<details style="margin-bottom:12px;">
          <summary style="cursor:pointer;font-weight:700;font-size:13px;padding:6px 0;border-bottom:1px solid var(--border);margin-bottom:6px;color:var(--text-muted);">
            ${t('controls.catalog_others')} (${ungrouped.length})
          </summary>
          ${_tableHtml(ungrouped.map(_controlRow).join(''))}
        </details>`;
      }
    } else {
      // ENS, NIS2, GDPR, ISO 22301: agrupar por keyword matching
      groups.forEach(g => {
        const matched = data.filter(c => {
          const haystack = ((c.name || '') + ' ' + (c.description || '') + ' ' + (c.theme || '') + ' ' + (c.code || '')).toLowerCase();
          return g.keywords.some(k => haystack.includes(k));
        });
        if (!matched.length) return;
        html += `<details open style="margin-bottom:12px;">
          <summary style="cursor:pointer;font-weight:700;font-size:13px;padding:6px 0;border-bottom:1px solid var(--border);margin-bottom:6px;color:var(--brand-purple);">
            ${UI.esc(g.label)} <span style="font-weight:400;color:var(--text-muted);">(${matched.length})</span>
          </summary>
          ${_tableHtml(matched.map(_controlRow).join(''))}
        </details>`;
      });
    }

    if (!data.length && !groups) {
      html = `<p style="color:var(--text-muted);font-size:13px;padding:16px 0;">${t('controls.no_results')}</p>`;
    }

    list.innerHTML = html;

    if (canEdit) {
      list.querySelectorAll('[data-mandatory-id]').forEach(chk => {
        chk.onchange = async () => {
          const cid = parseInt(chk.dataset.mandatoryId);
          try {
            await Api.patch(`/api/controls/catalog/${cid}`, { is_mandatory: chk.checked });
            const ctrl = ViewControls._catalog.find(c => c.id === cid);
            if (ctrl) ctrl.is_mandatory = chk.checked;
            UI.toast(t('common.success'), 'success');
          } catch (e) {
            chk.checked = !chk.checked;
            UI.toast(e.message, 'error');
          }
        };
      });
    }
  },

  async _renderImpls() {
    const list = document.getElementById('c-list');
    let data = await Api.impls.list();
    // Apply search/status/theme filters client-side
    const q = (document.getElementById('c-search')?.value || '').toLowerCase();
    const statusF = document.getElementById('c-status')?.value || '';
    const themeF = document.getElementById('c-theme')?.value || '';
    if (q) data = data.filter(i => i.name.toLowerCase().includes(q) || i.control?.code?.toLowerCase().includes(q) || i.control?.name?.toLowerCase().includes(q));
    if (statusF) data = data.filter(i => i.status === statusF);
    if (themeF) data = data.filter(i => i.control?.theme === themeF);
    if (ViewControls._overdueOnly) {
      const now2 = new Date();
      data = data.filter(i => i.next_review && new Date(i.next_review) < now2 && i.status !== 'not_implemented');
    }
    if (!data.length) {
      list.innerHTML = UI.emptyState(
        t('controls.empty_title'),
        t('controls.empty_hint')
      );
      return;
    }
    // Client-side sort
    const _sv = i => {
      const k = ViewControls._sortCol;
      if (k === 'control') return i.control?.code || '';
      if (k === 'name') return (i.name || '').toLowerCase();
      if (k === 'status') return i.status || '';
      if (k === 'maturity') return i.maturity || 0;
      if (k === 'risks') return i.risk_count || 0;
      if (k === 'next_review') return i.next_review || 'zzz';
      return i.id;
    };
    data.sort((a, b) => {
      const va = _sv(a), vb = _sv(b);
      const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
      return ViewControls._sortAsc ? cmp : -cmp;
    });
    const _th = (col, label, style) => {
      const active = ViewControls._sortCol === col;
      const arrow = active ? (ViewControls._sortAsc ? ' ▲' : ' ▼') : '';
      return `<th style="cursor:pointer;user-select:none;white-space:nowrap;${active?'color:var(--brand-purple);':''}${style||''}"
                  data-sort="${col}">${label}${arrow}</th>`;
    };

    const now = new Date();
    const overdueCount = data.filter(i =>
      i.next_review && new Date(i.next_review) < now && i.status !== 'not_implemented').length;
    list.innerHTML = `
      ${overdueCount ? `<div style="background:#FEF9C3;border:1px solid #FDE68A;border-radius:6px;padding:10px 14px;font-size:13px;color:#92400E;margin-bottom:12px;">
        <strong>${overdueCount} ${t('common.control')}${overdueCount>1?'es':''}</strong> ${t('controls.degraded')} (${t('controls.review_date')}).
      </div>` : ''}
      <div class="table-wrap"><table class="data">
      <thead><tr>
        ${_th('control',t('common.control'))}${_th('name',t('controls.implementation'))}${_th('status',t('common.status'))}${_th('maturity',t('controls.maturity'))}
        ${_th('risks',t('common.risk'),'width:70px;text-align:center;')}
        ${_th('next_review',t('controls.review_date'))}<th></th>
      </tr></thead>
      <tbody>
        ${data.map(i => {
          const reviewOverdue = i.next_review && new Date(i.next_review) < now
            && i.status !== 'not_implemented';
          const rc = i.risk_count || 0;
          const rcColor = rc === 0 ? 'var(--text-subtle)' : rc >= 3 ? 'var(--risk-low)' : 'var(--text-muted)';
          return `<tr data-id="${i.id}" style="cursor:pointer;${reviewOverdue?'background:rgba(254,249,195,0.5);':''}">
            <td>${UI.codePill(i.control.code)} <span style="font-size:11px;color:var(--text-subtle);">${UI.esc(i.control.name).slice(0,40)}</span></td>
            <td><strong>${UI.esc(i.name)}</strong></td>
            <td>${UI.controlStatusLabel(i.status)}</td>
            <td>
              ${ViewControls._maturityBar(i.maturity)}
              ${i.notes && i.notes.includes('nivel') ? `<div style="font-size:10px;color:var(--brand-purple);margin-top:2px;" title="${UI.esc(i.notes.slice(0,300))}">${t('ui_views.ctrl_gap_ai_available')}</div>` : ''}
            </td>
            <td style="text-align:center;font-weight:700;font-family:var(--font-mono);font-size:13px;color:${rcColor};" title="${t('ui_views.ctrl_risks_mitigated', {n: rc})}">${rc}</td>
            <td style="font-size:12px;">${i.next_review
              ? `<span style="color:${reviewOverdue?'var(--risk-high)':'inherit'};font-weight:${reviewOverdue?'700':'400'};">${new Date(i.next_review).toLocaleDateString()}</span>${reviewOverdue?' <span style="font-size:10px;background:#FEF9C3;color:#92400E;border-radius:3px;padding:1px 4px;">REVISIÓN</span>':''}`
              : '-'}</td>
            <td style="white-space:nowrap;" onclick="event.stopPropagation()">
              ${Auth.canEdit() ? `<button class="btn btn-ghost" data-edit="${i.id}">${t('common.edit')}</button>` : ''}
              ${Auth.canEdit() && i.status !== 'not_implemented' ? `
                <button class="btn btn-ghost" data-propagate="${i.id}"
                        title="${t('controls.propagate_title')}"
                        style="font-size:11px;padding:3px 8px;">
                  ${t('controls.propagate')}
                </button>` : ''}
            </td>
          </tr>`;
        }).join('')}
      </tbody>
    </table></div>`;
    list.querySelectorAll('th[data-sort]').forEach(th => {
      th.onclick = () => {
        const col = th.dataset.sort;
        if (ViewControls._sortCol === col) ViewControls._sortAsc = !ViewControls._sortAsc;
        else { ViewControls._sortCol = col; ViewControls._sortAsc = col !== 'maturity' && col !== 'risks'; }
        ViewControls._renderImpls();
      };
    });
    list.querySelectorAll('[data-edit]').forEach(b =>
      b.onclick = (e) => { e.stopPropagation(); ViewControls._editImpl(parseInt(b.dataset.edit)); });
    list.querySelectorAll('[data-propagate]').forEach(b =>
      b.onclick = (e) => { e.stopPropagation(); ViewControls._propagate(parseInt(b.dataset.propagate), b); });
    list.querySelectorAll('tr[data-id]').forEach(tr =>
      tr.onclick = () => ViewControls._editImpl(parseInt(tr.dataset.id)));
  },

  async _propagate(id, btn) {
    const origText = btn.textContent;
    btn.disabled = true;
    btn.textContent = t('ai.analyzing');
    try {
      const r = await Api.impls.propagate(id);
      const msg = [
        r.step1_recalculated ? t('ui_views.ctrl_recalc_risks', {n: r.step1_recalculated}) : null,
        r.step2_candidates_evaluated ? t('ui_views.ctrl_candidates_eval', {n: r.step2_candidates_evaluated}) : null,
        r.step2_linked ? t('ui_views.ctrl_new_links', {n: r.step2_linked}) : null,
      ].filter(Boolean).join(' · ') || r.message || t('ui_views.ctrl_propagation_done');
      UI.toast(msg, 'success');
      ViewControls._renderImpls();
    } catch (e) {
      UI.toast(t('common.error') + ': ' + e.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = origText;
    }
  },

  _maturityBar(level) {
    const bars = Array.from({length: 5}, (_, i) =>
      `<div style="width:12px;height:8px;border-radius:2px;background:${
        i < level ? 'var(--brand-purple)' : 'var(--bg-3)'};"></div>`).join('');
    return `<div style="display:flex;gap:3px;align-items:center;">
      ${bars}<span style="font-family:var(--font-mono);font-size:11px;margin-left:4px;color:var(--text-muted);">${level}/5</span></div>`;
  },

  async _editImpl(id) {
    let data = { control_id: ViewControls._catalog[0]?.id, name: '', description: '',
                 status: 'not_implemented', maturity: 0, notes: '', evidence: '' };
    if (id) {
      const all = await Api.impls.list();
      data = all.find(x => x.id === id) || data;
      data.control_id = data.control?.id || data.control_id;
    }
    UI.modal(id ? `${t('controls.edit')} ${id}` : t('controls.new'), `
      <div class="span2">
        <label>${t('controls.reference_control')} *</label>
        <select id="f-control">
          ${ViewControls._catalog.map(c =>
            `<option value="${c.id}" ${data.control_id===c.id?'selected':''}>${UI.esc(c.code)} - ${UI.esc(c.name)}</option>`).join('')}
        </select>
      </div>
      <div class="span2"><label>${t('controls.impl_name')} *</label>
        <input id="f-name" value="${UI.esc(data.name)}" placeholder="ej. EDR CrowdStrike en endpoints corporativos"></div>
      <div class="span2"><label>${t('common.description')}</label>
        <textarea id="f-desc" rows="2">${UI.esc(data.description||'')}</textarea></div>
      <div><label>${t('common.status')}</label>
        <select id="f-status">
          ${['planned','implemented','partial','not_implemented'].map(s =>
            `<option value="${s}" ${data.status===s?'selected':''}>${UI.controlStatusLabel(s)}</option>`).join('')}
        </select>
      </div>
      <div><label>${t('controls.maturity')} (0-5)</label>
        <input type="number" min="0" max="5" id="f-mat" value="${data.maturity||0}"></div>
      <div><label>${t('controls.last_review')}</label>
        <input type="date" id="f-last-rev" value="${data.last_review ? data.last_review.slice(0,10) : ''}"></div>
      <div><label>${t('controls.review_date')}</label>
        <input type="date" id="f-next-rev" value="${data.next_review ? data.next_review.slice(0,10) : ''}"></div>
      <div class="span2"><label>${t('controls.evidence')}</label>
        <textarea id="f-evi" rows="2">${UI.esc(data.evidence||'')}</textarea></div>
      <div class="span2"><label>${t('common.notes')}</label>
        <textarea id="f-notes" rows="2">${UI.esc(data.notes||'')}</textarea></div>
      ${data.notes && data.notes.includes('nivel') ? `
      <div class="span2">
        <div style="background:linear-gradient(135deg,rgba(89,0,141,.07),rgba(214,82,0,.05));
                    border:1px solid rgba(89,0,141,.2);border-radius:8px;padding:12px 14px;margin-top:4px;">
          <div style="font-size:11px;font-weight:700;text-transform:uppercase;
                      color:var(--brand-purple);letter-spacing:.4px;margin-bottom:8px;">
            ${t('controls.ai_maturity_analysis')}
          </div>
          <div style="font-size:12px;line-height:1.7;color:var(--text-base);white-space:pre-wrap;">${UI.esc(data.notes)}</div>
          <div style="font-size:10px;color:var(--text-muted);margin-top:6px;">
            Generado automáticamente al analizar el documento fuente. Edita el campo Notas para personalizar.
          </div>
        </div>
      </div>` : ''}
      <div class="span2" style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);">
        <p style="font-size:11px;text-transform:uppercase;color:var(--text-muted);margin:0 0 8px;letter-spacing:.05em;">${t('controls.soa_short')} — ISO 27001:2022 cl. 6.1.3</p>
      </div>
      <div><label>${t('controls.inclusion_reason')}</label>
        <select id="f-incl-reason">
          <option value="">${t('ui_views.reason_select')}</option>
          ${[['legal',t('ui_views.reason_legal')],['contractual',t('ui_views.reason_contractual')],['risk',t('ui_views.reason_risk')],['best_practice',t('ui_views.reason_best_practice')]]
            .map(([v,l]) => `<option value="${v}" ${data.inclusion_reason===v?'selected':''}>${l}</option>`).join('')}
        </select>
      </div>
      <div><label>${t('controls.last_review_soa')}</label>
        <input type="date" id="f-soa-rev" value="${data.soa_reviewed_at ? data.soa_reviewed_at.slice(0,10) : ''}">
      </div>
      <div class="span2"><label>${t('controls.exclusion_justification')}</label>
        <textarea id="f-excl-just" rows="2">${UI.esc(data.exclusion_justification||'')}</textarea>
      </div>
      <div class="span2"><label>${t('controls.evidence_refs')}</label>
        <textarea id="f-evid-refs" rows="3" placeholder="Política de seguridad | https://intranet/...&#10;Evidencia CrowdStrike | /docs/evidencias/...">${
          (data.evidence_refs || []).map(r => `${r.title || ''}${r.url ? ' | ' + r.url : ''}`).join('\n')
        }</textarea>
      </div>
      ${id ? `
      <div class="span2">
        <details id="impl-history">
          <summary style="cursor:pointer;font-size:13px;color:var(--text-muted);padding:6px 0;
                          list-style:none;display:flex;align-items:center;gap:6px;">
            <span style="font-size:10px;">&#9654;</span> ${t('controls.change_history')}
          </summary>
          <div id="impl-history-body" style="margin-top:8px;">
            <div class="notice">${t('common.loading_data')}</div>
          </div>
        </details>
      </div>` : ''}
    `, {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                ${id ? `<button class="btn btn-danger" id="m-del">${t('common.delete')}</button>` : ''}
                <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;

    // Historial de cambios (lazy-load al expandir)
    if (id) {
      const det = document.getElementById('impl-history');
      if (det) {
        det.addEventListener('toggle', async () => {
          if (!det.open) return;
          const body = document.getElementById('impl-history-body');
          try {
            const entries = await Api.audit.history('control_impl', id);
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
      if (!await UI.confirm(t('common.confirm_delete'))) return;
      try { await Api.impls.del(id); UI.closeModal(); UI.toast(t('common.success'),'success'); ViewControls._reload(); }
      catch (e) { UI.toast(e.message, 'error'); }
    };
    document.getElementById('m-save').onclick = async () => {
      const lastRev = document.getElementById('f-last-rev').value;
      const nextRev = document.getElementById('f-next-rev').value;
      const soaRev = document.getElementById('f-soa-rev').value;
      // Parsear referencias de evidencia
      const evidRefsRaw = document.getElementById('f-evid-refs').value.trim();
      const evidence_refs = evidRefsRaw
        ? evidRefsRaw.split('\n').map(line => {
            const parts = line.split('|');
            return { title: (parts[0]||'').trim(), url: (parts[1]||'').trim() };
          }).filter(r => r.title || r.url)
        : [];
      const body = {
        control_id: parseInt(document.getElementById('f-control').value),
        name: document.getElementById('f-name').value,
        description: document.getElementById('f-desc').value,
        status: document.getElementById('f-status').value,
        maturity: parseInt(document.getElementById('f-mat').value)||0,
        last_review: lastRev || null,
        next_review: nextRev || null,
        evidence: document.getElementById('f-evi').value,
        notes: document.getElementById('f-notes').value,
        inclusion_reason: document.getElementById('f-incl-reason').value || null,
        exclusion_justification: document.getElementById('f-excl-just').value.trim() || null,
        evidence_refs: evidence_refs.length ? evidence_refs : null,
        soa_reviewed_at: soaRev ? new Date(soaRev).toISOString() : null,
      };
      try {
        if (id) await Api.impls.update(id, body);
        else await Api.impls.create(body);
        UI.closeModal(); UI.toast(t('common.success'),'success'); ViewControls._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },
};
