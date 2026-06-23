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
          Plantillas de marca
        </button>
      </div>

      <div id="panel-reports">
        <!-- Informes estaticos -->
        <div class="card" style="margin-bottom:16px;">
          <h3 style="margin-bottom:4px;">Informes del registro</h3>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
            Generados directamente desde los datos registrados. Sin IA, descarga instantanea.
          </p>
          <div class="card-row">
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;">
              <h4 style="margin:0 0 6px;">Estado del SGSI</h4>
              <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">
                Informe ejecutivo multi-modulo: riesgos, controles, incidentes, tareas,
                politicas y RGPD. Resumen de KPIs de todo el sistema en un solo documento.
              </p>
              <div style="display:flex;gap:8px;">
                <button class="btn btn-primary" style="flex:1;" onclick="ViewReports._download('sgsi-status')">
                  PDF
                </button>
              </div>
            </div>
            <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;padding:16px;">
              <h4 style="margin:0 0 6px;">Risk Register</h4>
              <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px;">
                Listado completo de riesgos ordenados por nivel residual. Activo, amenaza,
                niveles inherente/residual, estado y decision de tratamiento. ISO/IEC 27005:2018.
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
                Declaracion de aplicabilidad completa: 93 controles ISO 27002:2022 con estado, madurez,
                razon de inclusion/exclusion, evidencias, fechas de revision y seccion de firma.
              </p>
              <div style="display:flex;gap:8px;">
                <button class="btn btn-primary" style="flex:1;" onclick="ViewReports._download('soa')">
                  PDF
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Revision por la Direccion -->
        <div class="card" style="margin-bottom:16px;border:2px solid var(--brand-purple);">
          <h3 style="margin-bottom:4px;">Revision por la Direccion</h3>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
            Informe completo segun ISO 27001:2022 clausula 9.3 y ENS. Incluye todos los apartados normativos
            con datos reales del sistema — los campos sin datos aparecen marcados [A CUMPLIMENTAR].
            Disponible en PDF (para presentar), Excel (para editar) y Word (para personalizar y firmar).
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
            <h3 style="margin:0;color:#DC2626;"><i class="ti ti-alert-triangle"></i> Post-Mortem de Continuidad (BCP)</h3>
            <span class="badge" style="font-size:10px;background:rgba(220,38,38,.12);color:#DC2626;">ISO 22301</span>
          </div>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:14px;">
            Informe completo de gestion del incidente de continuidad: cronologia, impacto en el negocio, analisis de causa raiz, evidencias, efectividad de la respuesta y acciones correctivas.
          </p>
          <div id="bcp-pm-list" style="min-height:40px;">
            <p style="font-size:12px;color:var(--text-muted);">${t('common.loading')}</p>
          </div>
        </div>

        <!-- Informes IA -->
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;">
            <h3 style="margin:0;">Informes generados por IA</h3>
            <span class="badge badge-muted" style="font-size:10px;">${t('reports.claude_api_required')}</span>
          </div>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
            Claude analiza todos los datos del registro de riesgos — activos, amenazas,
            controles, planes de tratamiento y estadisticas — y genera un informe ejecutivo
            en lenguaje natural. Tarda entre 30-60 segundos.
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
            Los informes de IA toman en cuenta: activos, amenazas, riesgos, controles, planes de tratamiento,
            estadísticas del registro y el contexto organizacional configurado.
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

  _REPORT_TYPES: [
    { id: 'all',                label: 'Global (todos los informes)', desc: 'Se aplica a cualquier informe que no tenga plantilla especifica.' },
    { id: 'risk_register',      label: 'Risk Register',              desc: 'PDF de riesgos ordenados por nivel residual.' },
    { id: 'soa',                label: 'Statement of Applicability', desc: 'Declaracion de aplicabilidad ISO 27002:2022.' },
    { id: 'sgsi_status',        label: 'Estado del SGSI',            desc: 'Informe ejecutivo multi-modulo.' },
    { id: 'management_review',  label: 'Revision por la Direccion',  desc: 'ISO 27001:2022 clausula 9.3.' },
    { id: 'treatment_plan',     label: 'Plan de Tratamiento (IA)',   desc: 'Narrativa de tratamiento generada por Claude.' },
    { id: 'executive_dashboard',label: 'Dashboard Ejecutivo (IA)',   desc: 'Postura de riesgo para la Direccion.' },
    { id: 'committee_minutes',  label: 'Acta de Comite (IA)',        desc: 'Acta formal del comite de seguridad.' },
    { id: 'followup_report',    label: 'Seguimiento ISO 27005 (IA)', desc: 'Monitoreo y mejora continua.' },
  ],

  async _renderTemplates() {
    const wrap = document.getElementById('panel-templates');
    wrap.innerHTML = `<p style="color:var(--text-muted);font-size:13px;">${t('common.loading')}</p>`;
    try {
      const list = await Api.get('/api/report-templates');
      const byType = {};
      list.forEach(cfg => { byType[cfg.report_type] = cfg; });

      wrap.innerHTML = `
        <div class="card" style="margin-bottom:16px;">
          <h3 style="margin-bottom:4px;">Plantillas de marca</h3>
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px;">
            Personaliza colores, logo, fuente y textos para cada tipo de informe.
            La plantilla <b>Global</b> se aplica a todos los que no tengan configuracion especifica.
            Opcionalmente puedes subir un fichero <b>.docx</b> o <b>.html</b> como plantilla base
            que la IA rellenara con los datos del sistema.
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
                  <div style="font-size:12px;color:var(--text-muted);">${UI.esc(rt.desc)}${hasFile ? ' <span style="color:var(--brand-purple);">· Plantilla de fichero activa</span>' : ''}</div>
                </div>
                ${hasTemplate ? `<span class="badge badge-success" style="font-size:10px;flex-shrink:0;">Personalizado</span>` : `<span class="badge badge-muted" style="font-size:10px;flex-shrink:0;">Por defecto</span>`}
                <button class="btn btn-sm btn-primary" style="flex-shrink:0;" onclick="ViewReports._openTemplateModal('${rt.id}','${UI.esc(rt.label)}')">
                  Configurar
                </button>
                ${hasTemplate ? `<button class="btn btn-sm" style="flex-shrink:0;color:#DC2626;border-color:#DC2626;" onclick="ViewReports._deleteTemplate('${rt.id}')">
                  Resetear
                </button>` : ''}
              </div>`;
            }).join('')}
          </div>
        </div>`;
    } catch (e) {
      wrap.innerHTML = `<p style="color:var(--danger);">Error al cargar plantillas: ${UI.esc(e.message)}</p>`;
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
      title: `Plantilla: ${label}`,
      width: 560,
      body: `
        <div style="display:grid;gap:16px;">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <label style="font-size:13px;font-weight:600;">
              Color primario
              <div style="display:flex;align-items:center;gap:8px;margin-top:4px;">
                <input type="color" id="tpl-primary" value="${current.primary_color || '#59008D'}"
                       style="width:44px;height:36px;border-radius:6px;border:1px solid var(--border);cursor:pointer;padding:2px;">
                <input type="text" id="tpl-primary-hex" value="${current.primary_color || '#59008D'}"
                       maxlength="7" style="flex:1;font-family:monospace;"
                       oninput="document.getElementById('tpl-primary').value=this.value">
              </div>
            </label>
            <label style="font-size:13px;font-weight:600;">
              Color secundario
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
            Fuente
            <select id="tpl-font" style="width:100%;margin-top:4px;">
              ${['Helvetica','Times-Roman','Courier'].map(f =>
                `<option value="${f}" ${(current.font_family||'Helvetica')===f?'selected':''}>${f}</option>`
              ).join('')}
            </select>
          </label>

          <label style="font-size:13px;font-weight:600;">
            Nombre de empresa (aparece en cabecera y pie)
            <input type="text" id="tpl-company" value="${UI.esc(current.company_name||'')}"
                   placeholder="Ej: Acme Corp S.L." style="width:100%;margin-top:4px;">
          </label>

          <label style="font-size:13px;font-weight:600;">
            Titulo de cabecera (opcional)
            <input type="text" id="tpl-header-title" value="${UI.esc(current.header_title||'')}"
                   placeholder="Ej: Confidencial — Solo uso interno" style="width:100%;margin-top:4px;">
          </label>

          <label style="font-size:13px;font-weight:600;">
            Texto de pie de pagina (opcional — sobreescribe el predeterminado)
            <input type="text" id="tpl-footer" value="${UI.esc(current.footer_text||'')}"
                   placeholder="Ej: Acme Corp — Clasificado: Confidencial" style="width:100%;margin-top:4px;">
          </label>

          <label style="font-size:13px;font-weight:600;">
            Subtitulo de portada (opcional)
            <input type="text" id="tpl-subtitle" value="${UI.esc(current.cover_subtitle||'')}"
                   placeholder="Ej: Ejercicio 2025 — Para uso del Comite de Direccion" style="width:100%;margin-top:4px;">
          </label>

          <div>
            <div style="font-size:13px;font-weight:600;margin-bottom:6px;">Logo (PNG, JPG o WebP — max 2 MB)</div>
            ${current.has_logo ? `
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                <img src="/api/report-templates/${reportType}/logo" alt="Logo"
                     style="max-height:40px;max-width:160px;object-fit:contain;border:1px solid var(--border);border-radius:6px;padding:4px;">
                <button class="btn btn-sm" style="color:#DC2626;border-color:#DC2626;"
                        onclick="ViewReports._deleteLogo('${reportType}')">Eliminar logo</button>
              </div>` : ''}
            <input type="file" id="tpl-logo" accept=".png,.jpg,.jpeg,.webp" style="font-size:13px;">
          </div>

          <div style="border:1px solid var(--border);border-radius:8px;padding:14px;">
            <div style="font-size:13px;font-weight:600;margin-bottom:4px;">Fichero de plantilla base (.docx o .html — max 10 MB)</div>
            <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px;">
              Sube un documento Word o HTML con los estilos, colores y estructura de tu organizacion.
              La IA rellenara las secciones marcadas con <code>{{variable}}</code> con los datos reales del sistema.
              Si no se sube ninguno, se usa la plantilla por defecto de RiskHub.
            </p>
            ${current.has_template_file ? `
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;
                          background:var(--bg-2);border-radius:6px;padding:8px 12px;">
                <span style="font-size:18px;">${current.template_mime && current.template_mime.includes('html') ? '' : ''}</span>
                <div style="flex:1;">
                  <div style="font-size:13px;font-weight:600;">Plantilla activa</div>
                  <div style="font-size:11px;color:var(--text-muted);">${current.template_mime && current.template_mime.includes('html') ? 'HTML' : 'Word (.docx)'}</div>
                </div>
                <button class="btn btn-sm" style="color:#DC2626;border-color:#DC2626;"
                        onclick="ViewReports._deleteTemplateFile('${reportType}')">Eliminar plantilla</button>
              </div>` : ''}
            <input type="file" id="tpl-template-file" accept=".docx,.html,.htm" style="font-size:13px;">
          </div>

          <div style="background:var(--bg-2);border-radius:8px;padding:10px 14px;font-size:12px;color:var(--text-muted);">
            Los cambios se aplican a los proximos informes generados. Los informes ya descargados no se modifican.
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
        UI.toast('Generando Informe del Estado del SGSI...', 'info');
        const today = new Date().toISOString().slice(0, 10);
        Api.download('/api/reports/sgsi-status', `sgsi_status_${today}.pdf`)
           .catch(e => UI.toast(e.message, 'error'));
      },
      'rr-pdf': () => {
        UI.toast('Generando Risk Register PDF...', 'info');
        Api.download('/api/reports/risk-register', 'risk_register.pdf')
           .catch(e => UI.toast(e.message, 'error'));
      },
      'rr-excel': () => {
        UI.toast('Generando Risk Register Excel...', 'info');
        Api.download(
          '/api/reports/risk-register-excel',
          `riskhub_export_${new Date().toISOString().slice(0,10)}.xlsx`
        ).catch(e => UI.toast(e.message, 'error'));
      },
      'soa': () => {
        UI.toast('Generando Statement of Applicability...', 'info');
        const today = new Date().toISOString().slice(0,10);
        Api.download('/api/reports/soa', `SOA_${today}.pdf`)
           .catch(e => UI.toast(e.message, 'error'));
      },
      'mgmt-review-pdf': () => {
        UI.toast('Generando Revision por la Direccion PDF...', 'info');
        Api.reports.managementReview('pdf').catch(e => UI.toast(e.message, 'error'));
      },
      'mgmt-review-excel': () => {
        UI.toast('Generando Revision por la Direccion Excel...', 'info');
        Api.reports.managementReview('excel').catch(e => UI.toast(e.message, 'error'));
      },
      'mgmt-review-word': () => {
        UI.toast('Generando Revision por la Direccion Word...', 'info');
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
