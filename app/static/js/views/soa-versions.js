/* SoA Versions — ISO 27001 cl. 6.1.3 */
const ViewSoaVersions = (() => {

  function _badge(status) {
    const m = {
      draft:        ['#FEF9C3', '#854d0e'],
      under_review: ['#DBEAFE', '#1d4ed8'],
      approved:     ['#D1FAE5', '#065f46'],
      superseded:   ['#F5F5F5', '#9D9D9D'],
    };
    const [bg, col] = m[status] || ['#F5F5F5', '#9D9D9D'];
    const labelMap = {
      draft:        t('soa_versions.status_draft'),
      under_review: t('soa_versions.status_under_review'),
      approved:     t('soa_versions.status_approved'),
      superseded:   t('soa_versions.status_superseded'),
    };
    return `<span style="background:${bg};color:${col};padding:2px 10px;border-radius:10px;font-size:11px;font-weight:700;">${labelMap[status] || status}</span>`;
  }

  function _implStatusLabel(s) {
    const m = {
      implemented:     t('soa_versions.status_implemented'),
      partial:         t('soa_versions.status_partial'),
      planned:         t('soa_versions.status_planned'),
      not_implemented: t('soa_versions.status_not_implemented'),
    };
    return m[s] || s || '—';
  }

  function _implStatusBadge(s) {
    const colors = {
      implemented:     ['#D1FAE5', '#065f46'],
      partial:         ['#FEF9C3', '#854d0e'],
      planned:         ['#DBEAFE', '#1d4ed8'],
      not_implemented: ['#FEE2E2', '#991b1b'],
    };
    const [bg, col] = colors[s] || ['#F5F5F5', '#9D9D9D'];
    return `<span style="background:${bg};color:${col};padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600;white-space:nowrap;">${_implStatusLabel(s)}</span>`;
  }

  function _maturityBar(v) {
    v = Math.min(5, Math.max(0, v || 0));
    const color = v >= 4 ? 'var(--risk-low)' : v >= 3 ? 'var(--risk-medium)' : v >= 2 ? 'var(--risk-high)' : 'var(--risk-critical)';
    return `<div style="display:flex;align-items:center;gap:5px;">
      <div style="width:50px;background:var(--border);border-radius:999px;height:5px;overflow:hidden;">
        <div style="width:${v * 20}%;background:${color};height:100%;border-radius:999px;"></div>
      </div>
      <span style="font-size:11px;color:var(--text-muted);">${v}/5</span>
    </div>`;
  }

  function _implsTableHtml(impls, isSnapshot) {
    if (!impls || !impls.length) {
      return `<p style="color:var(--text-muted);font-size:13px;margin:16px 0;">${t('soa_versions.no_controls')}</p>`;
    }

    const stats = {
      implemented: 0, partial: 0, planned: 0, not_implemented: 0,
    };
    impls.forEach(i => {
      const s = isSnapshot ? i.status : (i.status?.value || i.status);
      if (stats[s] !== undefined) stats[s]++;
    });
    const total = impls.length;
    const implPct = total ? Math.round((stats.implemented / total) * 100) : 0;

    const statsHtml = `
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;">
        <div style="background:var(--bg-2);border-radius:8px;padding:10px 16px;text-align:center;min-width:90px;">
          <div style="font-size:22px;font-weight:800;color:var(--risk-low);">${implPct}%</div>
          <div style="font-size:11px;color:var(--text-muted);">${t('soa_versions.stat_coverage')}</div>
        </div>
        <div style="background:var(--bg-2);border-radius:8px;padding:10px 16px;text-align:center;min-width:90px;">
          <div style="font-size:22px;font-weight:800;">${total}</div>
          <div style="font-size:11px;color:var(--text-muted);">${t('soa_versions.stat_total')}</div>
        </div>
        <div style="background:#D1FAE5;border-radius:8px;padding:10px 16px;text-align:center;min-width:90px;">
          <div style="font-size:22px;font-weight:800;color:#065f46;">${stats.implemented}</div>
          <div style="font-size:11px;color:#065f46;">${t('soa_versions.status_implemented')}</div>
        </div>
        <div style="background:#FEF9C3;border-radius:8px;padding:10px 16px;text-align:center;min-width:90px;">
          <div style="font-size:22px;font-weight:800;color:#854d0e;">${stats.partial}</div>
          <div style="font-size:11px;color:#854d0e;">${t('soa_versions.status_partial')}</div>
        </div>
        <div style="background:#FEE2E2;border-radius:8px;padding:10px 16px;text-align:center;min-width:90px;">
          <div style="font-size:22px;font-weight:800;color:#991b1b;">${stats.not_implemented}</div>
          <div style="font-size:11px;color:#991b1b;">${t('soa_versions.status_not_implemented')}</div>
        </div>
      </div>`;

    const rows = impls.map(i => {
      const code    = isSnapshot ? (i.control_code || '—') : (i.control?.code || '—');
      const name    = isSnapshot ? (i.control_name || '—') : (i.control?.name || '—');
      const theme   = isSnapshot ? (i.control_theme || '—') : (i.control?.theme || '—');
      const status  = isSnapshot ? i.status : (i.status?.value || i.status);
      const maturity = i.maturity || 0;
      const reason  = i.inclusion_reason || (i.exclusion_justification ? `[${t('soa_versions.excluded')}] ${i.exclusion_justification}` : '—');
      const evCount = isSnapshot ? (i.evidence_count || 0) : (i.evidence_count || (i.evidence_refs?.length || 0));
      return `<tr>
        <td>${UI.codePill(code)}</td>
        <td style="font-size:13px;">${UI.esc(name)}</td>
        <td><span style="font-size:11px;color:var(--text-muted);">${UI.esc(theme)}</span></td>
        <td>${_implStatusBadge(status)}</td>
        <td>${_maturityBar(maturity)}</td>
        <td style="font-size:12px;max-width:200px;color:var(--text-muted);">${UI.esc(reason)}</td>
        <td style="text-align:center;">${evCount > 0
          ? `<span style="color:var(--brand-purple);font-weight:700;">${evCount}</span>`
          : '<span style="color:var(--text-muted);">—</span>'}</td>
      </tr>`;
    }).join('');

    return statsHtml + `
      <div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>${t('soa_versions.col_code')}</th>
            <th>${t('soa_versions.col_name')}</th>
            <th>${t('soa_versions.col_theme')}</th>
            <th>${t('soa_versions.col_status_h')}</th>
            <th>${t('soa_versions.col_maturity')}</th>
            <th>${t('soa_versions.col_inclusion')}</th>
            <th>${t('soa_versions.col_evidence')}</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function _exportCsv(impls, isSnapshot) {
    const headers = [
      t('soa_versions.col_code'), t('soa_versions.col_name'), t('soa_versions.col_theme'),
      t('soa_versions.col_status_h'), t('soa_versions.col_maturity'),
      t('soa_versions.col_inclusion'), t('soa_versions.col_evidence'),
    ];
    const rows = impls.map(i => {
      const code   = isSnapshot ? (i.control_code || '') : (i.control?.code || '');
      const name   = isSnapshot ? (i.control_name || '') : (i.control?.name || '');
      const theme  = isSnapshot ? (i.control_theme || '') : (i.control?.theme || '');
      const status = isSnapshot ? i.status : (i.status?.value || i.status || '');
      const evCount = isSnapshot ? (i.evidence_count || 0) : (i.evidence_refs?.length || 0);
      return [
        code,
        '"' + name.replace(/"/g, '""') + '"',
        theme,
        status,
        i.maturity || 0,
        '"' + (i.inclusion_reason || i.exclusion_justification || '').replace(/"/g, '""') + '"',
        evCount,
      ];
    });
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const a = document.createElement('a');
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
    a.download = 'SoA_' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
  }

  async function _showVersionModal(v) {
    let data;
    try {
      data = await Api.get(`/api/soa/versions/${v.id}`);
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
      return;
    }
    const _locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
    const snapshot = data.snapshot_json || [];

    UI.modal(
      `${t('soa_versions.version_detail_title')} ${v.version}`,
      `<div>
        <div style="display:flex;gap:12px;align-items:center;margin-bottom:16px;flex-wrap:wrap;">
          ${_badge(v.status)}
          ${v.submitted_at ? `<span style="font-size:12px;color:var(--text-muted);">${t('soa_versions.col_submitted')}: ${new Date(v.submitted_at).toLocaleDateString(_locale)}</span>` : ''}
          ${v.approved_at ? `<span style="font-size:12px;color:var(--text-muted);">${t('soa_versions.col_approved')}: ${new Date(v.approved_at).toLocaleDateString(_locale)}</span>` : ''}
          ${data.approval_notes ? `<span style="font-size:12px;font-style:italic;color:var(--text-muted);">"${UI.esc(data.approval_notes)}"</span>` : ''}
        </div>
        <h4 style="font-size:13px;font-weight:700;margin:0 0 12px;">${t('soa_versions.snapshot_label', { n: snapshot.length })}</h4>
        ${_implsTableHtml(snapshot, true)}
      </div>`,
      {
        width: '1100px',
        actions: `
          <button class="btn btn-ghost" id="msoa-csv">${t('soa_versions.export_csv')}</button>
          ${v.status === 'approved' || v.status === 'superseded'
            ? `<a href="/api/soa/versions/${v.id}/pdf" target="_blank" class="btn btn-ghost">${t('soa_versions.export_pdf')}</a>`
            : ''}
          <button class="btn" id="msoa-close">${t('common.close')}</button>`,
      }
    );
    document.getElementById('msoa-close')?.addEventListener('click', UI.closeModal);
    document.getElementById('msoa-csv')?.addEventListener('click', () => _exportCsv(snapshot, true));
  }

  async function _showCurrentSoaPanel() {
    const panel = document.getElementById('soa-content-panel');
    if (!panel) return;

    if (panel.dataset.loaded === '1') {
      panel.style.display = panel.style.display === 'none' ? '' : 'none';
      return;
    }

    panel.style.display = '';
    panel.innerHTML = `
      <div style="background:var(--bg-2);border-radius:10px;padding:20px 24px;margin-bottom:8px;border:1px solid var(--border);">
        <div class="spinner" style="margin:0 auto;"></div>
        <p style="text-align:center;margin-top:12px;color:var(--text-muted);">${t('soa_versions.loading_controls')}</p>
      </div>`;

    try {
      const [impls, versions] = await Promise.all([
        Api.get('/api/control-implementations/'),
        Api.get('/api/soa/versions').catch(() => []),
      ]);
      const approved = versions.find(v => v.status === 'approved');
      panel.dataset.loaded = '1';
      panel.dataset.impls = JSON.stringify(impls);

      panel.innerHTML = `
        <div style="background:var(--bg-2);border-radius:10px;padding:20px 24px;border:1px solid var(--border);">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px;">
            <h3 style="margin:0;font-size:15px;font-weight:700;">${t('soa_versions.current_soa_title', { n: impls.length })}</h3>
            <div style="display:flex;gap:8px;">
              <button class="btn btn-ghost btn-sm" id="btn-soa-export-csv">${t('soa_versions.export_csv')}</button>
              ${approved ? `<a href="/api/soa/versions/${approved.id}/pdf" target="_blank" class="btn btn-ghost btn-sm">${t('soa_versions.export_pdf')}</a>` : ''}
              <button class="btn btn-ghost btn-sm" id="btn-hide-soa">&#10005;</button>
            </div>
          </div>
          ${_implsTableHtml(impls, false)}
        </div>`;

      document.getElementById('btn-soa-export-csv')?.addEventListener('click', () => {
        _exportCsv(JSON.parse(panel.dataset.impls || '[]'), false);
      });
      document.getElementById('btn-hide-soa')?.addEventListener('click', () => {
        panel.style.display = 'none';
        panel.dataset.loaded = '0';
        panel.innerHTML = '';
      });
    } catch (e) {
      panel.innerHTML = `<div class="notice notice-error" style="margin-bottom:8px;">${UI.esc(e.message)}</div>`;
    }
  }

  async function render(container) {
    container.innerHTML = UI.sectionHeader(
      t('soa_versions.title'),
      t('soa_versions.subtitle'),
      `<div style="display:flex;gap:8px;">
         <button class="btn btn-ghost" id="btn-view-soa">${t('soa_versions.view_soa_btn')}</button>
         ${Auth.canEdit() ? `<button class="btn btn-primary" id="btn-new-soa">${t('soa_versions.new_version_btn')}</button>` : ''}
       </div>`
    );
    const wrap = document.createElement('div');
    container.appendChild(wrap);

    const soaPanel = document.createElement('div');
    soaPanel.id = 'soa-content-panel';
    soaPanel.style.display = 'none';
    soaPanel.style.marginBottom = '20px';
    container.appendChild(soaPanel);

    await _load(wrap);

    document.getElementById('btn-new-soa')?.addEventListener('click', _create);
    document.getElementById('btn-view-soa')?.addEventListener('click', _showCurrentSoaPanel);
  }

  async function _load(container) {
    try {
      const versions = await Api.get('/api/soa/versions');
      if (!versions.length) {
        container.innerHTML = UI.emptyState(
          t('soa_versions.empty_title'),
          t('soa_versions.empty_body')
        );
        return;
      }
      const _locale = I18n.lang() === 'en' ? 'en-GB' : 'es-ES';
      container.innerHTML = `
      <div class="table-container">
        <table class="data-table">
          <thead><tr>
            <th>${t('soa_versions.col_version')}</th>
            <th>${t('soa_versions.col_status_h')}</th>
            <th>${t('soa_versions.col_controls')}</th>
            <th>${t('soa_versions.col_submitted')}</th>
            <th>${t('soa_versions.col_approved')}</th>
            <th>${t('soa_versions.col_actions')}</th>
          </tr></thead>
          <tbody>
          ${versions.map(v => `<tr style="cursor:pointer;" onclick="ViewSoaVersions._viewVersion(${JSON.stringify(JSON.stringify(v))})">
            <td>${UI.codePill(v.version)}</td>
            <td>${_badge(v.status)}</td>
            <td>${v.controls_count}</td>
            <td>${v.submitted_at ? new Date(v.submitted_at).toLocaleDateString(_locale) : '—'}</td>
            <td>${v.approved_at ? new Date(v.approved_at).toLocaleDateString(_locale) : '—'}</td>
            <td onclick="event.stopPropagation()" style="display:flex;gap:4px;flex-wrap:wrap;">
              <button class="btn btn-sm btn-outline" onclick="ViewSoaVersions._viewVersion(${JSON.stringify(JSON.stringify(v))})">${t('soa_versions.view_btn')}</button>
              ${v.status === 'draft' ? `<button class="btn btn-sm btn-secondary" onclick="ViewSoaVersions._submit(${v.id})">${t('soa_versions.submit_btn')}</button>` : ''}
              ${v.status === 'under_review' ? `<button class="btn btn-sm btn-primary" onclick="ViewSoaVersions._approve(${v.id})">${t('soa_versions.approve_btn_action')}</button>` : ''}
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

  function _viewVersion(vJson) {
    const v = typeof vJson === 'string' ? JSON.parse(vJson) : vJson;
    _showVersionModal(v);
  }

  async function _create() {
    try {
      const v = await Api.post('/api/soa/versions', {});
      UI.toast(t('soa_versions.version_created', { v: v.version, n: v.controls_count }), 'success');
      location.reload();
    } catch (e) {
      if (e.status === 409) UI.toast(t('soa_versions.draft_exists_err'), 'warning');
      else UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  async function _submit(id) {
    try {
      await Api.post(`/api/soa/versions/${id}/submit`, {});
      UI.toast(t('soa_versions.submitted_toast'), 'success');
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  async function _approve(id) {
    const notes = prompt(t('soa_versions.approve_prompt')) || '';
    try {
      await Api.post(`/api/soa/versions/${id}/approve`, { approval_notes: notes });
      UI.toast(t('soa_versions.approved_toast'), 'success');
      location.reload();
    } catch (e) {
      UI.toast('Error: ' + (e.message || e), 'error');
    }
  }

  return { render, _submit, _approve, _exportCsv, _viewVersion };
})();
