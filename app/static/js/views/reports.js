/* Vista Informes — PDF, Excel, informes IA y plantillas de marca. */
const ViewReports = {

  _tab: 'reports',  // 'reports' | 'templates'

  render(main) {
    main.innerHTML = UI.sectionHeader(
      t('reports.title'),
      t('reports.subtitle')
    ) + `
      <div style="display:flex;gap:8px;margin-bottom:20px;border-bottom:2px solid var(--border);padding-bottom:0;">
        <button id="tab-reports" class="tab-btn tab-btn-active" onclick="ViewReports._switchTab('reports')">
          ${t('reports.generate')}
        </button>
        <button id="tab-templates" class="tab-btn" onclick="ViewReports._switchTab('templates')">
          ${t('reports.tab_templates')}
        </button>
      </div>

      <div id="panel-reports">
        <!-- Informes estaticos -->
        <div class="card" style="margin-bottom:16px;">
          <h3 style="margin-bottom:4px;">${t('reports.static_title')}</h3>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
            ${t('reports.static_desc')}
          </p>
          <div class="card-row">
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;">
              <h4 style="margin:0 0 6px;">${t('reports.sgsi_title')}</h4>
              <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">
                ${t('reports.sgsi_desc')}
              </p>
              <div style="display:flex;gap:8px;">
                <button class="btn btn-primary" style="flex:1;" onclick="ViewReports._download('sgsi-status')">
                  PDF
                </button>
              </div>
            </div>
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;">
              <h4 style="margin:0 0 6px;">${t('reports.rr_title')}</h4>
              <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">
                ${t('reports.rr_desc')}
              </p>
              <div style="display:flex;gap:8px;">
                <button class="btn btn-primary" style="flex:1;" onclick="ViewReports._download('rr-pdf')">
                  PDF
                </button>
                <button class="btn" style="flex:1;" onclick="ViewReports._download('rr-excel')">
                  ${t('reports.download_excel')}
                </button>
              </div>
            </div>
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;">
              <h4 style="margin:0 0 6px;">Statement of Applicability</h4>
              <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">
                ${t('reports.soa_desc')}
              </p>
              <div style="display:flex;gap:8px;">
                <button class="btn btn-primary" style="flex:1;" onclick="ViewReports._download('soa')">
                  PDF
                </button>
              </div>
            </div>
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;">
              <h4 style="margin:0 0 6px;">${t('reports.tprm_title')}</h4>
              <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">
                ${t('reports.tprm_desc')}
              </p>
              <div style="display:flex;gap:8px;">
                <button class="btn btn-primary" style="flex:1;" onclick="ViewReports._download('tprm')">
                  PDF
                </button>
              </div>
            </div>
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;">
              <h4 style="margin:0 0 6px;">${t('reports.treatment_full_title')}</h4>
              <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">
                ${t('reports.treatment_full_desc')}
              </p>
              <div style="display:flex;gap:8px;">
                <button class="btn btn-primary" style="flex:1;" onclick="ViewReports._download('treatment-full')">
                  PDF
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Revisión por la Dirección -->
        <div class="card" style="margin-bottom:16px;border:2px solid var(--brand-purple);">
          <h3 style="margin-bottom:4px;">${t('reports.mgmt_review_title')}</h3>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
            ${t('reports.mgmt_review_desc')}
          </p>
          <div style="display:flex;gap:10px;flex-wrap:wrap;">
            <button class="btn btn-primary" onclick="ViewReports._download('mgmt-review-pdf')">
              PDF
            </button>
            <button class="btn" onclick="ViewReports._download('mgmt-review-excel')">
              ${t('reports.download_excel')}
            </button>
            <button class="btn" onclick="ViewReports._download('mgmt-review-word')">
              Word (.docx)
            </button>
          </div>
        </div>

        <!-- Post-Mortem BCP -->
        <div class="card" style="margin-bottom:16px;border:2px solid #DC2626;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;">
            <h3 style="margin:0;color:#DC2626;"><i class="ti ti-alert-triangle"></i> ${t('reports.bcp_pm_title')}</h3>
            <span class="badge" style="font-size:10px;background:rgba(220,38,38,.12);color:#DC2626;">ISO 22301</span>
          </div>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:14px;">
            ${t('reports.bcp_pm_desc')}
          </p>
          <div id="bcp-pm-list" style="min-height:40px;">
            <p style="font-size:12px;color:var(--text-muted);">${t('common.loading')}</p>
          </div>
        </div>

        <!-- Informes IA -->
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;">
            <h3 style="margin:0;">${t('reports.ai_section_title')}</h3>
            <span class="badge badge-muted" style="font-size:10px;">${t('reports.claude_api_required')}</span>
          </div>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
            ${t('reports.ai_section_desc')}
          </p>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            ${[
              {
                id: 'treatment_plan',
                title: t('reports.ai_treatment_plan_title'),
                desc: t('reports.ai_treatment_plan_desc'),
                icon: '📋',
                excel: true,
              },
              {
                id: 'executive_dashboard',
                title: t('reports.ai_executive_dashboard_title'),
                desc: t('reports.ai_executive_dashboard_desc'),
                icon: '📊',
                excel: true,
              },
              {
                id: 'committee_minutes',
                title: t('reports.ai_committee_minutes_title'),
                desc: t('reports.ai_committee_minutes_desc'),
                icon: '🏛️',
                excel: true,
              },
              {
                id: 'followup_report',
                title: t('reports.ai_followup_report_title'),
                desc: t('reports.ai_followup_report_desc'),
                icon: '📈',
                excel: true,
              },
            ].map(r => `
              <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;
                          display:flex;flex-direction:column;gap:8px;">
                <div style="display:flex;align-items:center;gap:8px;">
                  <span style="font-size:20px;">${r.icon}</span>
                  <h4 style="margin:0;font-size:14px;line-height:1.3;">${r.title}</h4>
                </div>
                <p style="font-size:12px;color:var(--text-muted);margin:0;line-height:1.5;">${r.desc}</p>
                <div style="margin-top:auto;display:flex;gap:6px;">
                  <button class="btn btn-primary" style="flex:1;font-size:12px;"
                          onclick="ViewReports._generateAI('${r.id}','pdf')" id="btn-${r.id}-pdf">
                    ${t('reports.download_pdf')}
                  </button>
                  ${r.excel ? `<button class="btn" style="flex:1;font-size:12px;"
                          onclick="ViewReports._generateAI('${r.id}','excel')" id="btn-${r.id}-excel">
                    ${t('reports.download_excel')}
                  </button>` : ''}
                </div>
              </div>`).join('')}
          </div>
          <div style="margin-top:12px;background:var(--bg-2);border-radius:8px;padding:10px 14px;font-size:12px;color:var(--text-muted);">
            ${t('reports.ai_footer_note')}
          </div>
        </div>
      </div>

      <div id="panel-templates" style="display:none;"></div>
    `;

    this._loadBcpActivations();
  },

  _switchTab(tab) {
    this._tab = tab;
    document.getElementById('panel-reports').style.display = tab === 'reports' ? '' : 'none';
    document.getElementById('panel-templates').style.display = tab === 'templates' ? '' : 'none';
    document.getElementById('tab-reports').className = 'tab-btn' + (tab === 'reports' ? ' tab-btn-active' : '');
    document.getElementById('tab-templates').className = 'tab-btn' + (tab === 'templates' ? ' tab-btn-active' : '');
    if (tab === 'templates') this._renderTemplates();
  },

  // ── PLANTILLAS ──────────────────────────────────────────────

  get _REPORT_TYPES() {
    return [
      { id: 'all',                label: t('reports.tpl_type_all'),       desc: t('reports.tpl_type_all_desc') },
      { id: 'risk_register',      label: t('reports.tpl_type_rr'),        desc: t('reports.tpl_type_rr_desc') },
      { id: 'soa',                label: t('reports.tpl_type_soa'),       desc: t('reports.tpl_type_soa_desc') },
      { id: 'sgsi_status',        label: t('reports.tpl_type_sgsi'),      desc: t('reports.tpl_type_sgsi_desc') },
      { id: 'management_review',  label: t('reports.tpl_type_mgmt'),      desc: t('reports.tpl_type_mgmt_desc') },
      { id: 'treatment_plan',     label: t('reports.tpl_type_treatment'), desc: t('reports.tpl_type_treatment_desc') },
      { id: 'executive_dashboard',label: t('reports.tpl_type_executive'), desc: t('reports.tpl_type_executive_desc') },
      { id: 'committee_minutes',  label: t('reports.tpl_type_committee'), desc: t('reports.tpl_type_committee_desc') },
      { id: 'followup_report',    label: t('reports.tpl_type_followup'),  desc: t('reports.tpl_type_followup_desc') },
    ];
  },

  async _renderTemplates() {
    const wrap = document.getElementById('panel-templates');
    wrap.innerHTML = `<p style="color:var(--text-muted);font-size:13px;">${t('common.loading')}</p>`;
    try {
      const list = await Api.get('/api/report-templates');
      const byType = {};
      list.forEach(cfg => { byType[cfg.report_type] = cfg; });

      wrap.innerHTML = `
        <div class="card" style="margin-bottom:16px;">
          <h3 style="margin-bottom:4px;">${t('reports.tpl_title')}</h3>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
            ${t('reports.tpl_desc')}
          </p>
          <div style="display:grid;gap:10px;">
            ${this._REPORT_TYPES.map(rt => {
              const cfg = byType[rt.id];
              const hasTemplate = !!cfg;
              const primaryColor = cfg?.primary_color || '#59008D';
              const secondaryColor = cfg?.secondary_color || '#D65200';
              const hasFile = cfg?.has_template_file;
              return `
              <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;
                          padding:14px 16px;display:flex;align-items:center;gap:14px;">
                <div style="display:flex;gap:4px;flex-shrink:0;">
                  <div style="width:14px;height:14px;border-radius:3px;background:${UI.esc(primaryColor)};border:1px solid var(--border);"></div>
                  <div style="width:14px;height:14px;border-radius:3px;background:${UI.esc(secondaryColor)};border:1px solid var(--border);"></div>
                </div>
                <div style="flex:1;min-width:0;">
                  <div style="font-weight:600;font-size:14px;">${UI.esc(rt.label)}</div>
                  <div style="font-size:12px;color:var(--text-muted);">${UI.esc(rt.desc)}${hasFile ? ` <span style="color:var(--brand-purple);">· ${t('reports.tpl_file_active')}</span>` : ''}</div>
                </div>
                ${hasTemplate ? `<span class="badge badge-success" style="font-size:10px;flex-shrink:0;">${t('reports.tpl_customized')}</span>` : `<span class="badge badge-muted" style="font-size:10px;flex-shrink:0;">${t('reports.tpl_default')}</span>`}
                <button class="btn btn-sm btn-primary" style="flex-shrink:0;" onclick="ViewReports._openTemplateModal('${rt.id}','${UI.esc(rt.label)}')">
                  ${t('reports.tpl_configure')}
                </button>
                ${hasTemplate ? `<button class="btn btn-sm" style="flex-shrink:0;color:#DC2626;border-color:#DC2626;" onclick="ViewReports._deleteTemplate('${rt.id}')">
                  ${t('reports.tpl_reset')}
                </button>` : ''}
              </div>`;
            }).join('')}
          </div>
        </div>`;
    } catch (e) {
      wrap.innerHTML = `<p style="color:var(--danger);">${t('reports.error_loading_templates')} ${UI.esc(e.message)}</p>`;
    }
  },

  async _openTemplateModal(reportType, label) {
    let current = {};
    try {
      current = await Api.get(`/api/report-templates/${reportType}`);
    } catch (_) {}

    const modalId = 'modal-report-template';
    UI.modal({
      id: modalId,
      title: t('reports.tpl_modal_title', { label }),
      width: 560,
      body: `
        <div style="display:grid;gap:16px;">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <label style="font-size:13px;font-weight:600;">
              ${t('reports.tpl_primary_color')}
              <div style="display:flex;align-items:center;gap:8px;margin-top:4px;">
                <input type="color" id="tpl-primary" value="${current.primary_color || '#59008D'}"
                       style="width:44px;height:36px;border-radius:6px;border:1px solid var(--border);cursor:pointer;padding:2px;">
                <input type="text" id="tpl-primary-hex" value="${current.primary_color || '#59008D'}"
                       maxlength="7" style="flex:1;font-family:monospace;"
                       oninput="document.getElementById('tpl-primary').value=this.value">
              </div>
            </label>
            <label style="font-size:13px;font-weight:600;">
              ${t('reports.tpl_secondary_color')}
              <div style="display:flex;align-items:center;gap:8px;margin-top:4px;">
                <input type="color" id="tpl-secondary" value="${current.secondary_color || '#D65200'}"
                       style="width:44px;height:36px;border-radius:6px;border:1px solid var(--border);cursor:pointer;padding:2px;">
                <input type="text" id="tpl-secondary-hex" value="${current.secondary_color || '#D65200'}"
                       maxlength="7" style="font-family:monospace;"
                       oninput="document.getElementById('tpl-secondary').value=this.value">
              </div>
            </label>
          </div>

          <label style="font-size:13px;font-weight:600;">
            ${t('reports.tpl_font')}
            <select id="tpl-font" style="width:100%;margin-top:4px;">
              ${['Helvetica','Times-Roman','Courier'].map(f =>
                `<option value="${f}" ${(current.font_family||'Helvetica')===f?'selected':''}>${f}</option>`
              ).join('')}
            </select>
          </label>

          <label style="font-size:13px;font-weight:600;">
            ${t('reports.tpl_company')}
            <input type="text" id="tpl-company" value="${UI.esc(current.company_name||'')}"
                   placeholder="Ej: Acme Corp S.L." style="width:100%;margin-top:4px;">
          </label>

          <label style="font-size:13px;font-weight:600;">
            ${t('reports.tpl_header_title')}
            <input type="text" id="tpl-header-title" value="${UI.esc(current.header_title||'')}"
                   placeholder="Ej: Confidencial — Solo uso interno" style="width:100%;margin-top:4px;">
          </label>

          <label style="font-size:13px;font-weight:600;">
            ${t('reports.tpl_footer')}
            <input type="text" id="tpl-footer" value="${UI.esc(current.footer_text||'')}"
                   placeholder="Ej: Acme Corp — Clasificado: Confidencial" style="width:100%;margin-top:4px;">
          </label>

          <label style="font-size:13px;font-weight:600;">
            ${t('reports.tpl_subtitle')}
            <input type="text" id="tpl-subtitle" value="${UI.esc(current.cover_subtitle||'')}"
                   placeholder="Ej: Ejercicio 2025 — Para uso del Comite de Dirección" style="width:100%;margin-top:4px;">
          </label>

          <div>
            <div style="font-size:13px;font-weight:600;margin-bottom:6px;">${t('reports.tpl_logo')}</div>
            ${current.has_logo ? `
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                <img src="/api/report-templates/${reportType}/logo" alt="Logo"
                     style="max-height:40px;max-width:160px;object-fit:contain;border:1px solid var(--border);border-radius:6px;padding:4px;">
                <button class="btn btn-sm" style="color:#DC2626;border-color:#DC2626;"
                        onclick="ViewReports._deleteLogo('${reportType}')">${t('reports.tpl_delete_logo')}</button>
              </div>` : ''}
            <input type="file" id="tpl-logo" accept=".png,.jpg,.jpeg,.webp" style="font-size:13px;">
          </div>

          <div style="border:1px solid var(--border);border-radius:8px;padding:14px;">
            <div style="font-size:13px;font-weight:600;margin-bottom:4px;">${t('reports.tpl_file_title')}</div>
            <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px;">
              ${t('reports.tpl_file_desc')}
            </p>
            ${current.has_template_file ? `
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;
                          background:var(--bg-2);border-radius:6px;padding:8px 12px;">
                <span style="font-size:18px;">${current.template_mime && current.template_mime.includes('html') ? '' : ''}</span>
                <div style="flex:1;">
                  <div style="font-size:13px;font-weight:600;">${t('reports.tpl_file_active')}</div>
                  <div style="font-size:11px;color:var(--text-muted);">${current.template_mime && current.template_mime.includes('html') ? t('reports.tpl_file_active_html') : 'Word (.docx)'}</div>
                </div>
                <button class="btn btn-sm" style="color:#DC2626;border-color:#DC2626;"
                        onclick="ViewReports._deleteTemplateFile('${reportType}')">${t('reports.tpl_delete_file')}</button>
              </div>` : ''}
            <input type="file" id="tpl-template-file" accept=".docx,.html,.htm" style="font-size:13px;">
          </div>

          <div style="background:var(--bg-2);border-radius:8px;padding:10px 14px;font-size:12px;color:var(--text-muted);">
            ${t('reports.tpl_footer_note')}
          </div>
        </div>
      `,
      actions: [
        { label: t('common.cancel'), variant: 'secondary', action: () => UI.closeModal(modalId) },
        { label: t('common.save'), variant: 'primary', action: () => ViewReports._saveTemplate(reportType, modalId) },
      ],
    });

    // Sincronizar color picker <-> hex input
    document.getElementById('tpl-primary').addEventListener('input', e => {
      document.getElementById('tpl-primary-hex').value = e.target.value;
    });
    document.getElementById('tpl-secondary').addEventListener('input', e => {
      document.getElementById('tpl-secondary-hex').value = e.target.value;
    });
  },

  async _saveTemplate(reportType, modalId) {
    const primaryColor = document.getElementById('tpl-primary-hex').value.trim();
    const secondaryColor = document.getElementById('tpl-secondary-hex').value.trim();
    if (!/^#[0-9A-Fa-f]{6}$/.test(primaryColor)) {
      UI.toast(t('reports.invalid_primary_color'), 'error'); return;
    }
    if (!/^#[0-9A-Fa-f]{6}$/.test(secondaryColor)) {
      UI.toast(t('reports.invalid_secondary_color'), 'error'); return;
    }
    try {
      await Api.put(`/api/report-templates/${reportType}`, {
        primary_color: primaryColor,
        secondary_color: secondaryColor,
        font_family: document.getElementById('tpl-font').value,
        company_name: document.getElementById('tpl-company').value.trim() || null,
        header_title: document.getElementById('tpl-header-title').value.trim() || null,
        footer_text: document.getElementById('tpl-footer').value.trim() || null,
        cover_subtitle: document.getElementById('tpl-subtitle').value.trim() || null,
      });

      const tok = Api.token();

      // Subir logo si se selecciono uno
      const logoInput = document.getElementById('tpl-logo');
      if (logoInput && logoInput.files[0]) {
        const fd = new FormData();
        fd.append('file', logoInput.files[0]);
        const resp = await fetch(`/api/report-templates/${reportType}/logo`, {
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + tok },
          body: fd,
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: resp.statusText }));
          throw new Error('Error subiendo logo: ' + (err.detail || resp.statusText));
        }
      }

      // Subir fichero de plantilla base si se selecciono uno
      const tplFileInput = document.getElementById('tpl-template-file');
      if (tplFileInput && tplFileInput.files[0]) {
        const fd = new FormData();
        fd.append('file', tplFileInput.files[0]);
        const resp = await fetch(`/api/report-templates/${reportType}/template-file`, {
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + tok },
          body: fd,
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: resp.statusText }));
          throw new Error('Error subiendo plantilla: ' + (err.detail || resp.statusText));
        }
      }

      UI.closeModal(modalId);
      UI.toast(t('common.success'), 'success');
      this._renderTemplates();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  },

  async _deleteTemplate(reportType) {
    if (!confirm(t('common.confirm_delete'))) return;
    try {
      await Api.del(`/api/report-templates/${reportType}`);
      UI.toast(t('common.success'), 'success');
      this._renderTemplates();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  },

  async _deleteLogo(reportType) {
    if (!confirm(t('common.confirm_delete'))) return;
    try {
      await Api.del(`/api/report-templates/${reportType}/logo`);
      UI.toast(t('common.success'), 'success');
      const rt = this._REPORT_TYPES.find(r => r.id === reportType);
      this._openTemplateModal(reportType, rt ? rt.label : reportType);
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  },

  async _deleteTemplateFile(reportType) {
    if (!confirm('Eliminar el fichero de plantilla base. Los informes usaran la plantilla por defecto de RiskHub.')) return;
    try {
      await Api.del(`/api/report-templates/${reportType}/template-file`);
      UI.toast(t('common.success'), 'success');
      const rt = this._REPORT_TYPES.find(r => r.id === reportType);
      this._openTemplateModal(reportType, rt ? rt.label : reportType);
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  },

  // ── BCP POST-MORTEM ─────────────────────────────────────────

  async _loadBcpActivations() {
    const wrap = document.getElementById('bcp-pm-list');
    if (!wrap) return;
    try {
      const closed = await Api.get('/api/bcp/activations?status=closed').catch(() => []);
      if (!closed.length) {
        wrap.innerHTML = '<p style="font-size:12px;color:var(--text-muted);">No hay activaciones cerradas. Los post-mortems se generan al cerrar un incidente de continuidad.</p>';
        return;
      }
      wrap.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;">` +
        closed.map(a => {
          const dur = a.closed_at && a.activated_at
            ? Math.round((new Date(a.closed_at) - new Date(a.activated_at)) / 60000) : null;
          return `<div style="background:var(--bg-2);border:1px solid var(--border);border-radius:8px;padding:14px;">
            <div style="font-size:11px;font-weight:700;color:#DC2626;margin-bottom:4px;">${UI.esc(a.code)}</div>
            <div style="font-size:13px;font-weight:600;margin-bottom:6px;line-height:1.3;">${UI.esc(a.title)}</div>
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:10px;">
              ${a.activated_at ? new Date(a.activated_at).toLocaleDateString('es-ES') : '-'}
              ${dur !== null ? ` · ${dur < 60 ? dur+'min' : Math.round(dur/60)+'h'}` : ''}
            </div>
            <button class="btn btn-sm" style="width:100%;background:#DC2626;color:#fff;border-color:#DC2626;font-size:12px;"
                    onclick="ViewReports._openBcpPostMortem(${a.id})">
              ${t('common.view')}
            </button>
          </div>`;
        }).join('') + `</div>`;
    } catch (e) {
      wrap.innerHTML = `<p style="font-size:12px;color:var(--text-muted);">Error al cargar activaciones: ${UI.esc(e.message)}</p>`;
    }
  },

  _openBcpPostMortem(actId) {
    if (typeof ViewBcp !== 'undefined' && ViewBcp._openActivationReport) {
      ViewBcp._openActivationReport(actId);
    } else {
      if (typeof App !== 'undefined' && App.navigate) {
        App.navigate('bcp');
      } else {
        window.location.hash = '#bcp';
      }
      setTimeout(() => {
        if (typeof ViewBcp !== 'undefined' && ViewBcp._openActivationReport) {
          ViewBcp._openActivationReport(actId);
        }
      }, 500);
    }
  },

  // ── DESCARGAS ───────────────────────────────────────────────

  _download(type) {
    const actions = {
      'sgsi-status': () => {
        UI.toast(t('reports.generating'), 'info');
        const today = new Date().toISOString().slice(0, 10);
        Api.download('/api/reports/sgsi-status', `sgsi_status_${today}.pdf`)
           .catch(e => UI.toast(e.message, 'error'));
      },
      'rr-pdf': () => {
        UI.toast(t('reports.generating'), 'info');
        Api.download('/api/reports/risk-register', 'risk_register.pdf')
           .catch(e => UI.toast(e.message, 'error'));
      },
      'rr-excel': () => {
        UI.toast(t('reports.generating'), 'info');
        Api.download(
          '/api/reports/risk-register-excel',
          `riskhub_export_${new Date().toISOString().slice(0,10)}.xlsx`
        ).catch(e => UI.toast(e.message, 'error'));
      },
      'soa': () => {
        UI.toast(t('reports.generating'), 'info');
        const today = new Date().toISOString().slice(0,10);
        Api.download('/api/reports/soa', `SOA_${today}.pdf`)
           .catch(e => UI.toast(e.message, 'error'));
      },
      'tprm': () => {
        UI.toast(t('reports.generating'), 'info');
        const today = new Date().toISOString().slice(0,10);
        Api.download('/api/reports/tprm', `informe_tprm_${today}.pdf`)
           .catch(e => UI.toast(e.message, 'error'));
      },
      'treatment-full': () => {
        UI.toast(t('reports.generating'), 'info');
        const today = new Date().toISOString().slice(0,10);
        Api.download('/api/reports/treatment-plan', `plan_tratamiento_${today}.pdf`)
           .catch(e => UI.toast(e.message, 'error'));
      },
      'mgmt-review-pdf': () => {
        UI.toast(t('reports.generating'), 'info');
        Api.reports.managementReview('pdf').catch(e => UI.toast(e.message, 'error'));
      },
      'mgmt-review-excel': () => {
        UI.toast(t('reports.generating'), 'info');
        Api.reports.managementReview('excel').catch(e => UI.toast(e.message, 'error'));
      },
      'mgmt-review-word': () => {
        UI.toast(t('reports.generating'), 'info');
        Api.reports.managementReview('word').catch(e => UI.toast(e.message, 'error'));
      },
    };
    if (actions[type]) actions[type]();
  },

  async _generateAI(reportType, format) {
    const btnId = `btn-${reportType}-${format}`;
    const btn = document.getElementById(btnId);
    const labels = {
      treatment_plan: 'Plan de Tratamiento',
      executive_dashboard: 'Dashboard Ejecutivo',
      committee_minutes: 'Acta de Comite',
      followup_report: 'Informe de Seguimiento',
    };
    const label = labels[reportType] || reportType;

    if (btn) { btn.disabled = true; btn.textContent = t('ai.generating'); }
    UI.toast(`${t('reports.generate')} ${label} (${format.toUpperCase()}) con IA... puede tardar 30-60 s.`, 'info');

    const ext = format === 'excel' ? 'xlsx' : 'pdf';
    const filename = `${reportType}_${new Date().toISOString().slice(0,10)}.${ext}`;

    try {
      const tok = Api.token();
      const resp = await fetch('/api/reports/ai-generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + tok,
        },
        body: JSON.stringify({ report_type: reportType, format }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || resp.statusText);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = filename; a.click();
      URL.revokeObjectURL(url);
      UI.toast(`${label} — ${t('common.success')}`, 'success');
    } catch (e) {
      UI.toast('Error al generar el informe: ' + e.message, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = format === 'excel' ? t('reports.download_excel') : t('reports.download_pdf');
      }
    }
  },
};
