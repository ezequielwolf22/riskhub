/* views/onboarding.js - Configuracion del Agente IA y onboarding de documentos. */

const ViewOnboarding = (() => {

  const CATEGORIES = [
    { id: 'architecture',        label: 'Arquitectura y sistemas',
      desc: 'Diagramas de red, inventarios de sistemas, arquitecturas cloud/on-premise.' },
    { id: 'normative',           label: 'Normativa y compliance',
      desc: 'Normas aplicables: ISO 27001, ENS, NIS2, GDPR, PCI-DSS, HIPAA.' },
    { id: 'policies',            label: 'Politicas y procedimientos',
      desc: 'Politica de seguridad, gestion de accesos, backups, continuidad de negocio.' },
    { id: 'assets_inventory',    label: 'Inventario de activos',
      desc: 'Listado de activos TI, valoracion CIA, clasificacion por criticidad.' },
    { id: 'risk_assessments',    label: 'Evaluaciones de riesgo previas',
      desc: 'Informes de analisis de riesgos anteriores, DPIA, auditorias.' },
    { id: 'critical_suppliers',  label: 'Proveedores criticos',
      desc: 'Contratos, evaluaciones de terceros, SLA, acuerdos de tratamiento de datos.' },
    { id: 'incidents_lessons',   label: 'Incidentes y lecciones aprendidas',
      desc: 'Informes post-incidente, root cause analysis, planes de mejora.' },
    { id: 'other',               label: 'Otros documentos',
      desc: 'Cualquier documentacion adicional relevante para el contexto de la organizacion.' },
  ];

  const MODELS = [
    { value: 'claude-opus-4-5',  label: 'Claude Opus 4.5 (mas potente)' },
    { value: 'claude-sonnet-4-5', label: 'Claude Sonnet 4.5 (equilibrado)' },
    { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5 (mas rapido)' },
  ];

  const ANON_LEVELS = [
    { value: 'low',    label: 'Bajo — solo IPs y emails' },
    { value: 'medium', label: 'Medio — IPs, emails y dominios (recomendado)' },
    { value: 'high',   label: 'Alto — IPs, emails, dominios y nombres propios' },
  ];

  let _cfg = null;
  let _docs = [];
  let _saving = false;

  // ---------- Render principal ----------

  async function render(main) {
    main.innerHTML = UI.sectionHeader(
      'Configuracion del Agente IA',
      'Contextualiza el agente con la informacion de tu organizacion para obtener analisis mas precisos.'
    ) + '<div id="ob-root"></div>';
    await _load();
    _render();
  }

  async function _load() {
    try {
      [_cfg, _docs] = await Promise.all([
        Api.aiConfig.get(),
        Api.aiDocuments.list(),
      ]);
    } catch (_) {
      _cfg = { model: 'claude-opus-4-5', anonymization_level: 'medium',
               setup_completed: false, has_api_key: false };
      _docs = [];
    }
  }

  function _render() {
    const root = document.getElementById('ob-root');
    if (!root) return;

    const completionPct = _computeCompletion();

    root.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 320px;gap:20px;align-items:start;">

        <!-- columna izquierda: secciones -->
        <div>
          ${_renderWelcome(completionPct)}
          ${_renderProfileSection()}
          ${CATEGORIES.map(_renderDocSection).join('')}
          ${_renderAiConfigSection()}
        </div>

        <!-- columna derecha: resumen -->
        <div style="position:sticky;top:80px;">
          ${_renderSidebar(completionPct)}
        </div>

      </div>`;

    _wireEvents();
  }

  // ---------- Seccion de bienvenida ----------

  function _renderWelcome(pct) {
    const bar = `<div style="background:var(--border);border-radius:999px;height:6px;margin:8px 0 4px;">
      <div style="background:var(--brand-purple);height:6px;border-radius:999px;width:${pct}%;transition:width .4s;"></div>
    </div>`;
    return `
      <div class="card" style="margin-bottom:16px;border-left:4px solid var(--brand-purple);">
        <h3 style="margin:0 0 8px;font-size:16px;color:var(--brand-purple);">
          Configuracion completada al ${pct}%
        </h3>
        ${bar}
        <p style="font-size:13px;color:var(--text-muted);margin:6px 0 0;line-height:1.5;">
          Cuantos mas documentos y datos proporciones, mas preciso sera el agente.
          Puedes volver aqui en cualquier momento para actualizar la informacion.
        </p>
        <div style="margin-top:12px;display:flex;gap:10px;flex-wrap:wrap;">
          <a href="#/ai-chat" class="btn btn-primary" style="font-size:13px;">
            Ir al Chat IA
          </a>
          <a href="#/ai-documents" class="btn btn-ghost" style="font-size:13px;">
            Gestionar documentos
          </a>
          ${!_cfg.setup_completed ? `
            <button class="btn btn-ghost" id="ob-skip" style="font-size:13px;color:var(--text-muted);">
              Omitir por ahora
            </button>` : ''}
        </div>
      </div>`;
  }

  // ---------- Perfil de organizacion ----------

  function _renderProfileSection() {
    const c = _cfg || {};
    return `
      <div class="card ob-section" id="ob-sec-profile" style="margin-bottom:16px;">
        <div class="ob-sec-header" style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
          <div style="width:32px;height:32px;background:var(--brand-purple-4);border-radius:8px;
                      display:flex;align-items:center;justify-content:center;flex-shrink:0;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--brand-purple)"
                 stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/>
              <path d="M8 7h8M8 12h8M8 17h4"/></svg>
          </div>
          <div>
            <h3 style="margin:0;font-size:15px;">Perfil de la organizacion</h3>
            <p style="margin:0;font-size:12px;color:var(--text-muted);">
              Contexto basico para que el agente entienda tu organizacion.
            </p>
          </div>
        </div>
        <div class="form-grid">
          <div>
            <label>Sector de actividad</label>
            <select id="ob-sector">
              <option value="">-- Seleccionar --</option>
              ${['Financiero / Banca','Sanitario / Salud','Industrial / Manufactura',
                 'Tecnologia / Software','Administracion publica','Educacion',
                 'Energia / Utilities','Retail / Comercio','Servicios profesionales','Otro']
                .map(s => `<option value="${s}"${c.org_sector===s?' selected':''}>${s}</option>`)
                .join('')}
            </select>
          </div>
          <div>
            <label>Tamano de la organizacion</label>
            <select id="ob-size">
              <option value="">-- Seleccionar --</option>
              ${['< 50 empleados','50-250 empleados','250-1.000 empleados',
                 '1.000-5.000 empleados','> 5.000 empleados']
                .map(s => `<option value="${s}"${c.org_size===s?' selected':''}>${s}</option>`)
                .join('')}
            </select>
          </div>
          <div class="span2">
            <label>Procesos criticos del negocio</label>
            <textarea id="ob-processes" rows="3" placeholder="Ej: facturacion, atencion al cliente, produccion industrial, trading...">${c.org_critical_processes || ''}</textarea>
          </div>
          <div class="span2">
            <label>Stack tecnologico principal</label>
            <textarea id="ob-tech" rows="2" placeholder="Ej: AWS, Active Directory, SAP ERP, Microsoft 365, servidores on-premise...">${c.org_tech_stack || ''}</textarea>
          </div>
        </div>
        <div style="margin-top:12px;">
          <button class="btn btn-primary" id="ob-save-profile">Guardar perfil</button>
        </div>
      </div>`;
  }

  // ---------- Seccion de carga de documentos ----------

  function _renderDocSection(cat) {
    const catDocs = _docs.filter(d => d.category === cat.id);
    const statusIcons = { indexed: '✓', processing: '⟳', pending: '⌛', error: '✗' };
    const statusColors = { indexed: 'var(--risk-low)', processing: 'var(--brand-orange)',
                           pending: 'var(--text-muted)', error: 'var(--risk-critical)' };
    const docsHtml = catDocs.length ? `
      <div style="margin-top:10px;display:flex;flex-direction:column;gap:6px;">
        ${catDocs.map(d => `
          <div style="display:flex;align-items:center;gap:8px;padding:7px 10px;
                      background:var(--bg-2);border-radius:6px;font-size:12px;">
            <span style="color:${statusColors[d.status]||'var(--text-muted)'};">
              ${statusIcons[d.status]||'?'}
            </span>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
                  title="${UI.esc(d.original_name)}">${UI.esc(d.original_name)}</span>
            ${d.chunk_count ? `<span style="color:var(--text-muted);">${d.chunk_count} frags</span>` : ''}
            ${d.error_message ? `<span style="color:var(--risk-critical);" title="${UI.esc(d.error_message)}">!</span>` : ''}
            <button class="btn btn-ghost" style="padding:2px 6px;font-size:11px;"
                    onclick="ViewOnboarding._deleteDoc(${d.id})" title="Eliminar">x</button>
          </div>`).join('')}
      </div>` : `<p style="font-size:12px;color:var(--text-muted);margin:8px 0 0;">
        Sin documentos en esta categoria.</p>`;

    return `
      <div class="card ob-section" id="ob-sec-${cat.id}" style="margin-bottom:16px;">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;">
          <div style="display:flex;align-items:center;gap:10px;">
            <div style="width:32px;height:32px;background:var(--bg-3);border-radius:8px;
                        display:flex;align-items:center;justify-content:center;flex-shrink:0;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/></svg>
            </div>
            <div>
              <h4 style="margin:0;font-size:14px;">${cat.label}
                ${catDocs.length ? `<span style="background:var(--brand-purple-4);color:var(--brand-purple);
                  border-radius:999px;padding:1px 7px;font-size:11px;font-weight:600;margin-left:6px;">
                  ${catDocs.length}</span>` : ''}
              </h4>
              <p style="margin:0;font-size:12px;color:var(--text-muted);">${cat.desc}</p>
            </div>
          </div>
          <label class="btn btn-ghost" style="cursor:pointer;font-size:12px;white-space:nowrap;">
            Subir archivo
            <input type="file" accept=".pdf,.docx,.txt,.csv" style="display:none;"
                   onchange="ViewOnboarding._upload(this, '${cat.id}')">
          </label>
        </div>
        ${docsHtml}
        <div id="ob-up-status-${cat.id}" style="font-size:12px;margin-top:6px;"></div>
      </div>`;
  }

  // ---------- Seccion de configuracion del agente ----------

  function _renderAiConfigSection() {
    const c = _cfg || {};
    const keyOk = c.has_api_key;
    return `
      <div class="card ob-section" id="ob-sec-ai-config" style="margin-bottom:16px;
           border: 2px solid ${keyOk ? 'var(--risk-low)' : 'var(--brand-orange)'};">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">
          <div style="width:32px;height:32px;background:var(--brand-purple-4);border-radius:8px;
                      display:flex;align-items:center;justify-content:center;flex-shrink:0;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--brand-purple)"
                 stroke-width="2"><circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06
                       a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09
                       A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83
                       l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09
                       A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83
                       l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09
                       a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83
                       l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09
                       a1.65 1.65 0 0 0-1.51 1z"/></svg>
          </div>
          <div>
            <h3 style="margin:0;font-size:15px;">Configuracion del Agente IA</h3>
            <p style="margin:0;font-size:12px;color:var(--text-muted);">
              ${keyOk
                ? '<span style="color:var(--risk-low);">API key configurada</span>'
                : '<span style="color:var(--brand-orange);">Requiere API key de Anthropic para activar el agente.</span>'}
            </p>
          </div>
        </div>
        <div class="form-grid">
          <div class="span2">
            <label>API Key de Anthropic
              <a href="https://console.anthropic.com/" target="_blank"
                 style="font-size:11px;margin-left:6px;color:var(--brand-purple);">
                Obtener clave
              </a>
            </label>
            <input type="password" id="ob-apikey" placeholder="${keyOk ? '••••••••••••••• (configurada)' : 'sk-ant-api03-...'}" autocomplete="new-password">
          </div>
          <div class="span2">
            <label>API Key de Voyage AI
              <span style="font-size:11px;margin-left:6px;color:var(--text-muted);">Opcional — activa busqueda semantica multilingue en documentos</span>
              <a href="https://www.voyageai.com/" target="_blank"
                 style="font-size:11px;margin-left:6px;color:var(--brand-purple);">
                Obtener clave gratis
              </a>
            </label>
            <input type="password" id="ob-voyage-key" placeholder="${c.has_voyage_key ? '••••••••••••••• (configurada)' : 'pa-...'}" autocomplete="new-password">
            ${c.has_voyage_key ? `<div style="margin-top:6px;display:flex;gap:8px;align-items:center;">
              <span style="font-size:12px;color:var(--risk-low);">Busqueda semantica activa</span>
              <button class="btn btn-ghost" style="font-size:11px;padding:3px 8px;" id="ob-embed-existing">Vectorizar documentos existentes</button>
            </div>` : '<p style="font-size:12px;color:var(--text-muted);margin:4px 0 0;">Sin esta clave el agente usa busqueda por palabras clave. Con ella entiende preguntas en cualquier idioma aunque el documento este en otro.</p>'}
          </div>
          <div>
            <label>Modelo</label>
            <select id="ob-model">
              ${MODELS.map(m =>
                `<option value="${m.value}"${(c.model||'claude-opus-4-5')===m.value?' selected':''}>${m.label}</option>`
              ).join('')}
            </select>
          </div>
          <div>
            <label>Nivel de anonimizacion de datos</label>
            <select id="ob-anon">
              ${ANON_LEVELS.map(a =>
                `<option value="${a.value}"${(c.anonymization_level||'medium')===a.value?' selected':''}>${a.label}</option>`
              ).join('')}
            </select>
          </div>
        </div>
        <div style="margin-top:12px;display:flex;gap:10px;align-items:center;">
          <button class="btn btn-primary" id="ob-save-ai">Guardar configuracion</button>
          <button class="btn btn-ghost" id="ob-test-ai">Probar conexion</button>
          <span id="ob-test-result" style="font-size:12px;"></span>
        </div>
      </div>`;
  }

  // ---------- Sidebar resumen ----------

  function _renderSidebar(pct) {
    const docsByCategory = {};
    CATEGORIES.forEach(c => {
      docsByCategory[c.id] = _docs.filter(d => d.category === c.id).length;
    });
    const totalDocs = _docs.length;
    const indexedDocs = _docs.filter(d => d.status === 'indexed').length;

    return `
      <div class="card" style="margin-bottom:16px;">
        <h4 style="margin:0 0 12px;font-size:13px;text-transform:uppercase;
                   color:var(--text-muted);letter-spacing:.5px;">Resumen</h4>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;">
          <div style="text-align:center;padding:10px;background:var(--bg-2);border-radius:8px;">
            <div style="font-size:22px;font-weight:700;color:var(--brand-purple);">${totalDocs}</div>
            <div style="font-size:11px;color:var(--text-muted);">Documentos</div>
          </div>
          <div style="text-align:center;padding:10px;background:var(--bg-2);border-radius:8px;">
            <div style="font-size:22px;font-weight:700;color:var(--risk-low);">${indexedDocs}</div>
            <div style="font-size:11px;color:var(--text-muted);">Indexados</div>
          </div>
        </div>

        <h4 style="margin:0 0 8px;font-size:12px;color:var(--text-muted);">Por categoria</h4>
        ${CATEGORIES.map(c => {
          const n = docsByCategory[c.id] || 0;
          return `
            <div style="display:flex;justify-content:space-between;align-items:center;
                        padding:4px 0;font-size:12px;border-bottom:1px solid var(--border);">
              <span style="color:var(--text-base);">${c.label}</span>
              <span style="color:${n>0?'var(--risk-low)':'var(--text-muted)'};">
                ${n > 0 ? n : '-'}
              </span>
            </div>`;
        }).join('')}

        <div style="margin-top:14px;">
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">
            Estado de la API
          </div>
          <div style="font-size:13px;font-weight:600;
                      color:${_cfg && _cfg.has_api_key ? 'var(--risk-low)' : 'var(--brand-orange)'};">
            ${_cfg && _cfg.has_api_key ? 'Conectado' : 'Sin configurar'}
          </div>
        </div>

        <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border);">
          <a href="#/ai-chat" class="btn btn-primary" style="width:100%;text-align:center;">
            Abrir Chat IA
          </a>
        </div>
      </div>`;
  }

  // ---------- Calcular porcentaje de completado ----------

  function _computeCompletion() {
    let score = 0;
    const total = 10;
    if (_cfg && (_cfg.org_sector || _cfg.org_size)) score += 2;
    if (_cfg && _cfg.org_critical_processes) score++;
    if (_cfg && _cfg.org_tech_stack) score++;
    if (_cfg && _cfg.has_api_key) score += 2;
    // +1 por cada categoria con al menos un doc (max 4)
    const catsWithDocs = new Set(_docs.filter(d => d.status === 'indexed').map(d => d.category));
    score += Math.min(4, catsWithDocs.size);
    return Math.round((score / total) * 100);
  }

  // ---------- Eventos ----------

  function _wireEvents() {
    // Guardar perfil
    const saveProfile = document.getElementById('ob-save-profile');
    if (saveProfile) saveProfile.onclick = _saveProfile;

    // Guardar config IA
    const saveAi = document.getElementById('ob-save-ai');
    if (saveAi) saveAi.onclick = _saveAiConfig;

    // Probar conexion
    const testAi = document.getElementById('ob-test-ai');
    if (testAi) testAi.onclick = _testConnection;

    // Vectorizar documentos existentes con Voyage AI
    const embedExisting = document.getElementById('ob-embed-existing');
    if (embedExisting) embedExisting.onclick = _embedExisting;

    // Skip
    const skip = document.getElementById('ob-skip');
    if (skip) skip.onclick = () => {
      localStorage.setItem('riskhub_onboarding_skipped', '1');
      location.hash = '/dashboard';
    };
  }

  async function _saveProfile() {
    if (_saving) return;
    _saving = true;
    const btn = document.getElementById('ob-save-profile');
    if (btn) btn.disabled = true;
    try {
      const payload = {
        org_sector: document.getElementById('ob-sector').value || null,
        org_size: document.getElementById('ob-size').value || null,
        org_critical_processes: document.getElementById('ob-processes').value || null,
        org_tech_stack: document.getElementById('ob-tech').value || null,
      };
      _cfg = { ..._cfg, ...await Api.aiConfig.update(payload) };
      UI.toast('Perfil guardado', 'success');
      _render();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    } finally {
      _saving = false;
    }
  }

  async function _saveAiConfig() {
    if (_saving) return;
    _saving = true;
    try {
      const apiKey = document.getElementById('ob-apikey').value.trim();
      const voyageKey = document.getElementById('ob-voyage-key')?.value.trim();
      const payload = {
        model: document.getElementById('ob-model').value,
        anonymization_level: document.getElementById('ob-anon').value,
        setup_completed: true,
      };
      if (apiKey) payload.api_key = apiKey;
      if (voyageKey) payload.voyage_api_key = voyageKey;
      _cfg = { ..._cfg, ...await Api.aiConfig.update(payload) };
      UI.toast('Configuracion guardada', 'success');
      _render();
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    } finally {
      _saving = false;
    }
  }

  async function _embedExisting() {
    const btn = document.getElementById('ob-embed-existing');
    if (btn) { btn.disabled = true; btn.textContent = 'Vectorizando...'; }
    try {
      await Api.post('/api/ai/config/embed-existing', {});
      UI.toast('Vectorizacion iniciada. Los documentos estaran listos en unos minutos.', 'success');
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Vectorizar documentos existentes'; }
    }
  }

  async function _testConnection() {
    const el = document.getElementById('ob-test-result');
    if (el) el.textContent = 'Probando...';
    try {
      // Guardar primero si hay clave nueva
      const apiKey = document.getElementById('ob-apikey').value.trim();
      if (apiKey) await Api.aiConfig.update({ api_key: apiKey });
      const res = await Api.aiConfig.test();
      if (el) el.innerHTML = `<span style="color:var(--risk-low);">Conexion OK — modelo: ${UI.esc(String(res.model))}</span>`;
    } catch (e) {
      if (el) el.innerHTML = `<span style="color:var(--risk-critical);">${e.message}</span>`;
    }
  }

  async function _upload(input, category) {
    const file = input.files[0];
    if (!file) return;
    const status = document.getElementById('ob-up-status-' + category);
    if (status) status.innerHTML = `<span style="color:var(--brand-orange);">Subiendo ${UI.esc(file.name)}...</span>`;
    try {
      await Api.aiDocuments.upload(file, category);
      _docs = await Api.aiDocuments.list();
      _render();
      UI.toast('Documento indexado correctamente', 'success');
    } catch (e) {
      if (status) status.innerHTML = `<span style="color:var(--risk-critical);">Error: ${UI.esc(e.message)}</span>`;
      UI.toast('Error al subir: ' + e.message, 'error');
    }
    input.value = '';
  }

  async function _deleteDoc(id) {
    if (!confirm('Eliminar este documento del indice?')) return;
    try {
      await Api.aiDocuments.del(id);
      _docs = await Api.aiDocuments.list();
      _render();
      UI.toast('Documento eliminado', 'success');
    } catch (e) {
      UI.toast('Error: ' + e.message, 'error');
    }
  }

  // Exponer metodos que se llaman desde el HTML inline
  return { render, _upload, _deleteDoc };

})();
