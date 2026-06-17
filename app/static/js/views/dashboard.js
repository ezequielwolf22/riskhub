/* Dashboard - resumen ejecutivo multi-modulo. */

/* --- Catalogo completo de widgets personalizables --- */
const DASHBOARD_WIDGET_CATALOG = {
  posture:   { label: 'Postura de seguridad',    module: 'Seguridad',   desc: 'Score global del SGSI con alertas criticas y estado por modulo.' },
  risks:     { label: 'KPIs de Riesgos',         module: 'Riesgos',     desc: 'Activos, riesgos identificados, nivel alto, tratamientos vencidos y sin responsable.' },
  controls:  { label: 'Distribucion de Riesgos', module: 'Riesgos',     desc: 'Graficos por nivel residual, estado del ciclo y decision de tratamiento.' },
  top10:     { label: 'Top 10 Riesgos',          module: 'Riesgos',     desc: 'Tabla con los 10 riesgos de mayor nivel residual y reduccion porcentual.' },
  incidents: { label: 'Incidentes',              module: 'Incidentes',  desc: 'Abiertos, P1/P2 criticos y notificaciones NIS2 pendientes.' },
  tasks:     { label: 'Tareas',                  module: 'Tareas',      desc: 'Vencidas, en progreso, pendientes y completadas.' },
  policies:  { label: 'Politicas SGSI',          module: 'Politicas',   desc: 'Publicadas, en revision y con revision de ciclo vencida.' },
  gdpr:      { label: 'RGPD / Privacidad',       module: 'RGPD',        desc: 'Actividades de tratamiento, DPIAs pendientes y transferencias fuera de la UE.' },
  tprm:      { label: 'Proveedores TPRM',        module: 'Proveedores', desc: 'Panel de gestion de riesgo de terceros: criticos, altos y evaluaciones pendientes.' },
  bcp:       { label: 'Continuidad (BCP)',        module: 'Continuidad', desc: 'Procesos criticos, planes aprobados, BIA completado y tests ISO 22301.' },
  actions:   { label: 'Acciones y Vencimientos', module: 'Operaciones', desc: 'Acciones urgentes, proximos vencimientos de tratamientos y revisiones de controles.' },
  coverage:  { label: 'Cobertura ISO 27002',     module: 'Controles',   desc: 'Cobertura y madurez de controles por tema: organizativo, personas, fisico y tecnologico.' },
  inbox:     { label: 'Pendiente de tu revision', module: 'Operaciones', desc: 'Items pendientes de tu decision: riesgos auto-generados, incidentes, controles degradados y tareas.' },
};
const DASHBOARD_DEFAULT_LAYOUT = ['inbox','posture','risks','controls','incidents','tasks','policies','gdpr','tprm','bcp','top10','actions','coverage'];

/* Esquema de opciones configurables por tipo de widget.
   Solo se incluyen widgets con al menos una opcion configurable.
   Los demas widgets son fijos en su presentacion. */
const WIDGET_CONFIG_SCHEMA = {
  inbox: [
    { key: 'limit',  label: 'Items a mostrar',             type: 'select', opts: [3, 5, 10, 20], def: 5 },
  ],
  top10: [
    { key: 'count',  label: 'Numero de riesgos a mostrar', type: 'select', opts: [5, 10, 15, 20], def: 10 },
    { key: 'title',  label: 'Titulo personalizado',        type: 'text',   def: '' },
  ],
  coverage: [
    { key: 'title',  label: 'Titulo personalizado',        type: 'text',   def: '' },
  ],
  actions: [
    { key: 'title',  label: 'Titulo personalizado',        type: 'text',   def: '' },
  ],
};

/**
 * Muestra un banner de bienvenida si el cuestionario IA no se ha completado.
 * Se antepone al contenido principal del dashboard.
 */
async function _renderOnboardingBanner(container) {
  try {
    const ctx = await Api.get('/api/context/');
    const isIncomplete = !ctx || !ctx.questionnaire_answers || !ctx.organization_name;
    if (!isIncomplete) return;

    const banner = document.createElement('div');
    banner.className = 'onboarding-banner';
    banner.innerHTML = `
      <div class="banner-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5"><polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
      </div>
      <div class="banner-text">
        <h3>Bienvenido a RiskHub &mdash; Empieza aqui</h3>
        <p>Completa el cuestionario IA para que la plataforma genere automaticamente tu analisis de riesgos, compliance y recomendaciones personalizadas.</p>
      </div>
      <button class="btn btn-white" onclick="location.hash='/questionnaire'">
        Completar Cuestionario IA &rarr;
      </button>
    `;
    container.prepend(banner);
  } catch (_e) { /* silencioso */ }
}

const ViewDashboard = {
  _editMode: false,
  _cachedData: null,
  _cachedMain: null,

  /* Normaliza un item del layout al formato {uid, type, config} */
  _normalizeItem(item, index) {
    if (typeof item === 'string') return { uid: `w_${index}_${item}`, type: item, config: {} };
    return { uid: item.uid || `w_${index}_${item.type}`, type: item.type, config: item.config || {} };
  },

  /* Obtiene el layout en formato [{uid, type, config}].
     Migra automaticamente formatos antiguos (string[]) y layouts sin inbox. */
  _getLayout() {
    try {
      const saved = localStorage.getItem('riskhub_dashboard_layout');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          const items = parsed.map((item, i) => ViewDashboard._normalizeItem(item, i));
          let dirty = items.some((item, i) => parsed[i] !== item); // detectar migracion de formato
          if (!items.some(w => w.type === 'inbox')) {
            items.unshift({ uid: 'w_0_inbox', type: 'inbox', config: {} });
            dirty = true;
          }
          if (dirty) localStorage.setItem('riskhub_dashboard_layout', JSON.stringify(items));
          return items;
        }
      }
    } catch (_e) { /* silencioso */ }
    return DASHBOARD_DEFAULT_LAYOUT.map((type, i) => ({ uid: `w_${i}_${type}`, type, config: {} }));
  },

  /* Guarda el layout en localStorage. */
  _saveLayout(layout) {
    localStorage.setItem('riskhub_dashboard_layout', JSON.stringify(layout));
  },

  /* Restaura el layout por defecto. */
  _resetLayout() {
    localStorage.removeItem('riskhub_dashboard_layout');
    ViewDashboard._exitEdit();
    if (ViewDashboard._cachedMain && ViewDashboard._cachedData) {
      ViewDashboard._renderWithData(ViewDashboard._cachedMain, DASHBOARD_DEFAULT_LAYOUT.slice(), ViewDashboard._cachedData);
    }
  },

  /* Sale del modo edicion sin guardar cambios adicionales. */
  _exitEdit() {
    ViewDashboard._editMode = false;
    const panel = document.getElementById('dash-edit-panel');
    if (panel) panel.remove();
    document.querySelectorAll('[data-widget-id]').forEach(el => {
      el.draggable = false;
      el.style.borderTop = '';
      el.style.opacity = '';
      el.style.cursor = '';
      const handle = el.querySelector('.dash-widget-handle');
      if (handle) handle.remove();
      const rm = el.querySelector('.dash-widget-remove');
      if (rm) rm.remove();
      const cfg = el.querySelector('.dash-widget-config');
      if (cfg) cfg.remove();
    });
    const btn = document.getElementById('dash-customize-btn');
    if (btn) btn.textContent = 'Personalizar dashboard';
  },

  /* Entra en modo edicion mostrando el panel de personalizacion con catalogo por modulo. */
  _enterEdit() {
    // FIX: quitar panel duplicado si ya existe antes de crear uno nuevo
    const existingPanel = document.getElementById('dash-edit-panel');
    if (existingPanel) existingPanel.remove();

    ViewDashboard._editMode = true;
    const layout = ViewDashboard._getLayout();

    // Orden de modulos en el catalogo
    const moduleOrder = ['Seguridad', 'Riesgos', 'Incidentes', 'Tareas', 'Politicas', 'RGPD', 'Proveedores', 'Continuidad', 'Controles', 'Operaciones'];
    const modules = {};
    for (const [id, w] of Object.entries(DASHBOARD_WIDGET_CATALOG)) {
      if (!modules[w.module]) modules[w.module] = [];
      modules[w.module].push({ id, ...w });
    }

    const checkSvg = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5"><polyline points="20 6 9 17 4 12"/></svg>';
    const plusSvg  = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>';

    const gearSvg = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0;" title="Configurable"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';

    const catalogHtml = moduleOrder
      .filter(m => modules[m])
      .map(mod => `
        <div style="margin-bottom:10px;">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--text-muted);margin-bottom:5px;">${UI.esc(mod)}</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            ${modules[mod].map(w => {
              const active = layout.some(item => item.type === w.id);
              const hasConfig = !!WIDGET_CONFIG_SCHEMA[w.id];
              return `<button
                onclick="ViewDashboard._toggleWidget('${w.id}')"
                title="${UI.esc(w.desc)}"
                style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:500;cursor:pointer;transition:all .15s;
                       border:1px solid ${active ? 'var(--brand-purple)' : 'var(--border)'};
                       background:${active ? 'rgba(89,0,141,.07)' : 'var(--bg-3)'};
                       color:${active ? 'var(--brand-purple)' : 'var(--text-muted)'};">
                ${active ? checkSvg : plusSvg}
                ${UI.esc(w.label)}
                ${active && hasConfig ? gearSvg : ''}
              </button>`;
            }).join('')}
          </div>
        </div>`).join('');

    const panel = document.createElement('div');
    panel.id = 'dash-edit-panel';
    panel.style.cssText = 'background:var(--bg-card);border:2px dashed var(--brand-purple);border-radius:10px;padding:16px 18px;margin-bottom:16px;';
    panel.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:8px;">
        <strong style="font-size:14px;">Personalizar dashboard</strong>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-outline btn-sm" onclick="ViewDashboard._resetLayout()">Restaurar por defecto</button>
          <button class="btn btn-primary btn-sm" onclick="ViewDashboard._exitEdit()">Listo</button>
        </div>
      </div>
      <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px;">
        Activa o desactiva widgets desde el catalogo. Arrastra los widgets activos para reordenarlos. El boton <strong>&times;</strong> en cada widget lo quita del dashboard.
      </p>
      <div style="border-top:1px solid var(--border);padding-top:10px;">${catalogHtml}</div>`;

    const content = document.getElementById('dash-content');
    if (content) content.parentNode.insertBefore(panel, content);

    ViewDashboard._activateDragDrop(layout);

    const btn = document.getElementById('dash-customize-btn');
    if (btn) btn.textContent = 'Cerrar personalizacion';
  },

  /* Activa drag-and-drop en los widgets del layout activo. */
  _activateDragDrop(layout) {
    document.querySelectorAll('[data-widget-id]').forEach(el => {
      const type = el.dataset.widgetId;
      if (!layout.some(w => w.type === type)) return;

      el.style.position = 'relative';

      if (!el.querySelector('.dash-widget-handle')) {
        const handle = document.createElement('div');
        handle.className = 'dash-widget-handle';
        handle.title = 'Arrastra para reordenar';
        handle.style.cssText = 'position:absolute;top:8px;left:-20px;width:18px;height:18px;cursor:grab;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:14px;opacity:0.6;';
        handle.textContent = '≡';
        el.appendChild(handle);
      }

      if (!el.querySelector('.dash-widget-remove')) {
        const rm = document.createElement('button');
        rm.className = 'dash-widget-remove';
        rm.title = 'Quitar widget del dashboard';
        rm.innerHTML = '&times;';
        rm.style.cssText = 'position:absolute;top:6px;right:6px;width:22px;height:22px;border-radius:50%;border:1px solid var(--border);background:var(--bg-card);cursor:pointer;font-size:16px;line-height:1;display:flex;align-items:center;justify-content:center;color:var(--text-muted);z-index:5;padding:0;';
        rm.onclick = (e) => { e.stopPropagation(); ViewDashboard._toggleWidget(type); };
        el.appendChild(rm);
      }

      // Boton de configuracion (solo para widgets con opciones configurables)
      if (!el.querySelector('.dash-widget-config') && WIDGET_CONFIG_SCHEMA[type]) {
        const cfg = document.createElement('button');
        cfg.className = 'dash-widget-config';
        cfg.title = 'Configurar widget';
        cfg.innerHTML = '&#9881;';
        cfg.style.cssText = 'position:absolute;top:6px;right:32px;width:22px;height:22px;border-radius:50%;border:1px solid var(--border);background:var(--bg-card);cursor:pointer;font-size:13px;line-height:1;display:flex;align-items:center;justify-content:center;color:var(--brand-purple);z-index:5;padding:0;';
        cfg.onclick = (e) => { e.stopPropagation(); ViewDashboard._openConfig(type); };
        el.appendChild(cfg);
      }

      el.draggable = true;
      el.style.cursor = 'grab';

      el.ondragstart = (e) => {
        e.dataTransfer.setData('text/plain', type);
        e.dataTransfer.effectAllowed = 'move';
        setTimeout(() => { el.style.opacity = '0.5'; }, 0);
      };
      el.ondragend = () => {
        el.style.opacity = '1';
        el.style.borderTop = '';
      };
      el.ondragover = (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        el.style.borderTop = '3px solid var(--brand-purple)';
      };
      el.ondragleave = () => {
        el.style.borderTop = '';
      };
      el.ondrop = (e) => {
        e.preventDefault();
        el.style.borderTop = '';
        const srcType = e.dataTransfer.getData('text/plain');
        if (srcType === type) return;
        const currentLayout = ViewDashboard._getLayout();
        const srcIdx = currentLayout.findIndex(w => w.type === srcType);
        const tgtIdx = currentLayout.findIndex(w => w.type === type);
        if (srcIdx !== -1 && tgtIdx !== -1) {
          const [moved] = currentLayout.splice(srcIdx, 1);
          currentLayout.splice(tgtIdx, 0, moved);
          ViewDashboard._saveLayout(currentLayout);
          if (ViewDashboard._cachedMain && ViewDashboard._cachedData) {
            ViewDashboard._renderWithData(ViewDashboard._cachedMain, currentLayout, ViewDashboard._cachedData);
            ViewDashboard._enterEdit();
          }
        }
      };
    });
  },

  /* Activa o desactiva un widget del dashboard desde el catalogo o el boton X. */
  _toggleWidget(type) {
    const layout = ViewDashboard._getLayout();
    const idx = layout.findIndex(w => w.type === type);
    if (idx !== -1) {
      layout.splice(idx, 1);
    } else {
      const uid = `w_${type}_${Date.now()}`;
      layout.push({ uid, type, config: {} });
    }
    ViewDashboard._saveLayout(layout);
    if (ViewDashboard._cachedMain && ViewDashboard._cachedData) {
      ViewDashboard._renderWithData(ViewDashboard._cachedMain, layout, ViewDashboard._cachedData);
      ViewDashboard._enterEdit();
    }
  },

  /* Abre el modal de configuracion de un widget por su tipo. */
  _openConfig(type) {
    const layout = ViewDashboard._getLayout();
    const item = layout.find(w => w.type === type);
    if (!item) return;
    const schema = WIDGET_CONFIG_SCHEMA[type];
    if (!schema) return;
    const cfg = item.config || {};
    const catalogEntry = DASHBOARD_WIDGET_CATALOG[type] || {};

    const fieldsHtml = schema.map(field => {
      const val = cfg[field.key] !== undefined ? cfg[field.key] : field.def;
      if (field.type === 'select') {
        return `<label style="display:block;margin-bottom:14px;">
          <span style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">${UI.esc(field.label)}</span>
          <select data-cfg-key="${UI.esc(field.key)}"
                  style="width:100%;padding:7px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;background:var(--bg-2);color:var(--text);">
            ${field.opts.map(o => `<option value="${o}" ${o == val ? 'selected' : ''}>${o}</option>`).join('')}
          </select>
        </label>`;
      }
      if (field.type === 'text') {
        return `<label style="display:block;margin-bottom:14px;">
          <span style="font-size:12px;font-weight:600;color:var(--text-muted);display:block;margin-bottom:4px;">${UI.esc(field.label)}</span>
          <input type="text" data-cfg-key="${UI.esc(field.key)}" value="${UI.esc(String(val))}"
                 placeholder="${UI.esc(catalogEntry.label || '')}"
                 style="width:100%;padding:7px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;background:var(--bg-2);color:var(--text);box-sizing:border-box;">
        </label>`;
      }
      return '';
    }).join('');

    UI.openModal(`
      <div class="modal-head">
        <h2 style="font-size:16px;">Configurar: ${UI.esc(catalogEntry.label || type)}</h2>
        <button class="btn btn-ghost" onclick="UI.closeModal()">x</button>
      </div>
      <div class="modal-body">
        <p style="font-size:12px;color:var(--text-muted);margin:0 0 16px;">${UI.esc(catalogEntry.desc || '')}</p>
        ${fieldsHtml}
      </div>
      <div class="modal-foot" style="display:flex;justify-content:flex-end;gap:8px;padding:12px 16px;border-top:1px solid var(--border);">
        <button class="btn btn-outline" onclick="UI.closeModal()">Cancelar</button>
        <button class="btn btn-primary" onclick="ViewDashboard._saveConfig('${UI.esc(type)}')">Guardar</button>
      </div>
    `);
  },

  /* Guarda la configuracion del modal al layout y re-renderiza. */
  _saveConfig(type) {
    const layout = ViewDashboard._getLayout();
    const item = layout.find(w => w.type === type);
    if (!item) { UI.closeModal(); return; }
    const newCfg = { ...(item.config || {}) };
    document.querySelectorAll('[data-cfg-key]').forEach(el => {
      const k = el.dataset.cfgKey;
      newCfg[k] = el.tagName === 'SELECT' ? (isNaN(el.value) ? el.value : Number(el.value)) : el.value;
    });
    item.config = newCfg;
    ViewDashboard._saveLayout(layout);
    UI.closeModal();
    if (ViewDashboard._cachedMain && ViewDashboard._cachedData) {
      ViewDashboard._renderWithData(ViewDashboard._cachedMain, layout, ViewDashboard._cachedData);
      ViewDashboard._enterEdit();
    }
  },

  /* Re-renderiza el dashboard con datos ya cargados (sin peticiones al servidor). */
  _renderWithData(main, layout, data) {
    const { risks, incidents, tasks, policies, gdprData, context, tprmData, bcpData } = data;
    const postureScore = ViewDashboard._calcPosture(risks, incidents, tasks, policies, gdprData);
    const methLabels = { iso27005:'ISO 27005', magerit:'MAGERIT v3', combined:'ISO 27005 + MAGERIT' };
    const meth = context?.methodology || 'iso27005';
    const methBadge = ViewDashboard._methBadgeHtml(context, meth, methLabels);
    const widgetHtml = ViewDashboard._buildWidgetHtml(layout, risks, incidents, tasks, policies, gdprData, context, tprmData, bcpData, postureScore);

    const c = document.getElementById('dash-content');
    if (!c) return; // dash-content siempre existe tras render() inicial
    c.innerHTML = methBadge + widgetHtml;

    // Recargar secciones async (los elementos del DOM cambian con cada re-render)
    ViewDashboard._loadInbox();
    ViewDashboard._loadUpcoming();
    ViewDashboard._loadUpcomingControlReviews();
    ViewDashboard._loadControlsCoverage();
    ViewDashboard._loadRecentActivity();
    ViewDashboard._loadFindingsQuickAction();
  },

  /* Genera el HTML del badge de metodologia. */
  _methBadgeHtml(context, meth, methLabels) {
    return `
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:16px;">
        <span style="font-size:11px;color:var(--text-muted);">Metodologia activa:</span>
        <span style="background:var(--brand-purple);color:#fff;border-radius:20px;
                     padding:3px 12px;font-size:12px;font-weight:700;">
          ${methLabels[meth] || meth}
        </span>
        ${context?.risk_appetite != null ? `
        <span style="font-size:11px;color:var(--text-muted);">Apetito de riesgo:</span>
        <span style="background:var(--bg-2);border:1px solid var(--border);border-radius:20px;
                     padding:3px 12px;font-size:12px;font-weight:700;color:var(--brand-purple);">
          ${context.risk_appetite} / 8
        </span>` : ''}
        ${context?.active_frameworks?.length ? `
        <span style="font-size:11px;color:var(--text-muted);">Normativas:</span>
        ${context.active_frameworks.map(f =>
          `<span style="background:var(--bg-2);border:1px solid var(--border);border-radius:20px;
                       padding:2px 10px;font-size:11px;">${UI.esc(f.toUpperCase())}</span>`
        ).join('')}` : ''}
        <a href="#/context" style="font-size:11px;color:var(--brand-purple);margin-left:4px;">
          Cambiar en Contexto
        </a>
      </div>`;
  },

  /* Construye el HTML de cada widget segun el layout activo. */
  _buildWidgetHtml(layout, risks, incidents, tasks, policies, gdprData, context, tprmData, bcpData, postureScore) {
    const widgets = {
      posture: () => `
        <div data-widget-id="posture" style="margin-bottom:4px;">
          ${ViewDashboard._postureHtml(postureScore, risks, incidents, tasks, policies, gdprData)}
        </div>`,

      risks: () => `
        <div data-widget-id="risks" style="margin-bottom:20px;">
          <div class="card-row" style="margin-bottom:8px;">
            <div class="kpi" style="cursor:pointer;" onclick="location.hash='#/assets'"
                 title="Ver inventario de activos">
              <div class="label">Activos inventariados</div>
              <div class="value">${risks.total_assets}</div>
              <div class="hint">clic para ver inventario</div>
            </div>
            <div class="kpi" style="cursor:pointer;" onclick="location.hash='#/risks'"
                 title="Ver todos los riesgos">
              <div class="label">Riesgos identificados</div>
              <div class="value">${risks.total_risks}</div>
              <div class="hint">clic para ver registro</div>
            </div>
            <div class="kpi" style="cursor:pointer;background:linear-gradient(45deg,#FFE6CE,#EDD1FF);"
                 onclick="location.hash='#/risks?band=high'" title="Ver riesgos altos sin tratar">
              <div class="label">Riesgos altos sin tratar</div>
              <div class="value">${risks.by_band.high}</div>
              <div class="hint">clic para filtrar por nivel alto</div>
            </div>
            <div class="kpi" style="cursor:pointer;${risks.no_owner > 0 ? 'background:linear-gradient(45deg,#EDE9FE,#DDD6FE);border-color:#C4B5FD;' : ''}"
                 onclick="location.hash='#/risks?owner=__unassigned__'" title="Ver riesgos sin responsable">
              <div class="label">Sin responsable asignado</div>
              <div class="value" style="${risks.no_owner > 0 ? 'color:#6D28D9;' : ''}">${risks.no_owner}</div>
              <div class="hint">clic para ver sin propietario</div>
            </div>
          </div>
          <div class="card-row" style="margin-bottom:8px;">
            <div class="kpi" style="cursor:pointer;${risks.overdue_treatments > 0 ? 'background:linear-gradient(45deg,#FEE2E2,#FECACA);border-color:#FCA5A5;' : ''}"
                 onclick="location.hash='#/risks?overdue=1'" title="Ver riesgos con tratamiento vencido">
              <div class="label">Tratamientos vencidos</div>
              <div class="value" style="${risks.overdue_treatments > 0 ? 'color:#991B1B;' : ''}">${risks.overdue_treatments}</div>
              <div class="hint">clic para ver detalle</div>
            </div>
            <div class="kpi" style="cursor:pointer;${risks.no_treatment_high > 0 ? 'background:linear-gradient(45deg,#FEF9C3,#FDE68A);border-color:#FCD34D;' : ''}"
                 onclick="location.hash='#/risks?treatment=__none__&min_level=5'" title="Ver riesgos altos sin plan">
              <div class="label">Altos sin plan definido</div>
              <div class="value" style="${risks.no_treatment_high > 0 ? 'color:#92400E;' : ''}">${risks.no_treatment_high}</div>
              <div class="hint">clic para ver riesgos >= 5 sin tratamiento</div>
            </div>
            <div class="kpi" style="cursor:pointer;background:linear-gradient(45deg,#D1FAE5,#A7F3D0);"
                 onclick="location.hash='#/heatmap'" title="Ver mapa de calor">
              <div class="label">Reduccion del riesgo</div>
              <div class="value" style="color:#065F46;">${risks.risk_reduction_pct}%</div>
              <div class="hint">clic para ver mapa de calor</div>
            </div>
            ${incidents ? `
            <div class="kpi" style="cursor:pointer;${incidents.p1_p2_open > 0 ? 'background:linear-gradient(45deg,#FEE2E2,#FECACA);border-color:#FCA5A5;' : ''}"
                 onclick="location.hash='#/incidents?severity=p1'" title="Incidentes P1/P2 abiertos">
              <div class="label">Incidentes P1/P2</div>
              <div class="value" style="${incidents.p1_p2_open > 0 ? 'color:#991B1B;' : ''}">${incidents.p1_p2_open}</div>
              <div class="hint">${incidents.open} abiertos · clic para ver criticos</div>
            </div>` : ''}
            ${tasks ? `
            <div class="kpi" style="cursor:pointer;${tasks.overdue > 0 ? 'background:linear-gradient(45deg,#FFF7ED,#FED7AA);border-color:#FDBA74;' : ''}"
                 onclick="location.hash='#/tasks?overdue=1'" title="Tareas vencidas">
              <div class="label">Tareas vencidas</div>
              <div class="value" style="${tasks.overdue > 0 ? 'color:#9A3412;' : ''}">${tasks.overdue}</div>
              <div class="hint">${tasks.total} tareas totales · clic para ver vencidas</div>
            </div>` : ''}
          </div>
        </div>`,

      controls: () => `
        <div data-widget-id="controls" style="margin-bottom:0;">
          <div class="card-row">
            <div class="card">
              <h3>Distribucion por nivel residual</h3>
              <div style="display:flex;align-items:center;gap:20px;margin-top:12px;">
                ${ViewDashboard._donut([
                  { v: risks.by_band.high,   color: 'var(--risk-high)',   label: 'Altos' },
                  { v: risks.by_band.medium, color: 'var(--risk-medium)', label: 'Medios' },
                  { v: risks.by_band.low,    color: 'var(--risk-low)',    label: 'Bajos' },
                ], risks.total_risks)}
                <div style="flex:1;display:flex;flex-direction:column;gap:8px;">
                  ${[
                    { key:'high',   label:'Altos (>5)',    color:'var(--risk-high)' },
                    { key:'medium', label:'Medios (3-5)',  color:'var(--risk-medium)' },
                    { key:'low',    label:'Bajos (<3)',    color:'var(--risk-low)' },
                  ].map(b => `
                    <div>
                      <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
                        <span style="color:var(--text-base);">${b.label}</span>
                        <span style="font-weight:700;color:${b.color};">${risks.by_band[b.key]}</span>
                      </div>
                      <div style="height:5px;border-radius:3px;background:var(--bg-3);overflow:hidden;">
                        <div style="height:100%;width:${risks.total_risks?Math.round(risks.by_band[b.key]/risks.total_risks*100):0}%;background:${b.color};border-radius:3px;transition:width .4s;"></div>
                      </div>
                    </div>`).join('')}
                </div>
              </div>
            </div>
            <div class="card">
              <h3>Por estado del ciclo</h3>
              <div style="display:flex;flex-direction:column;gap:6px;margin-top:10px;">
                ${Object.entries(risks.by_status).filter(([,v]) => v > 0).map(([k, v]) => `
                  <div>
                    <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
                      <span>${UI.statusLabel(k)}</span>
                      <span style="font-weight:600;font-family:var(--font-mono);">${v}</span>
                    </div>
                    <div style="height:4px;border-radius:2px;background:var(--bg-3);overflow:hidden;">
                      <div style="height:100%;width:${risks.total_risks?Math.round(v/risks.total_risks*100):0}%;background:var(--brand-purple);border-radius:2px;"></div>
                    </div>
                  </div>`).join('')}
              </div>
            </div>
            <div class="card">
              <h3>Por decision de tratamiento</h3>
              <div style="display:flex;flex-direction:column;gap:6px;margin-top:10px;">
                ${Object.entries(risks.by_treatment).filter(([,v]) => v > 0).map(([k, v]) => `
                  <div>
                    <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px;">
                      <span>${UI.treatmentLabel(k)}</span>
                      <span style="font-weight:600;font-family:var(--font-mono);">${v}</span>
                    </div>
                    <div style="height:4px;border-radius:2px;background:var(--bg-3);overflow:hidden;">
                      <div style="height:100%;width:${risks.total_risks?Math.round(v/risks.total_risks*100):0}%;background:var(--brand-orange);border-radius:2px;"></div>
                    </div>
                  </div>`).join('')
                  || '<p style="font-size:13px;color:var(--text-subtle);margin:0;">Sin datos de tratamiento.</p>'}
              </div>
            </div>
          </div>
        </div>`,

      incidents: () => incidents ? `
          <div class="card" data-widget-id="incidents" style="flex:1;min-width:180px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
              <h3 style="margin:0;font-size:14px;">Incidentes</h3>
              <a href="#/incidents" style="font-size:11px;color:var(--brand-purple);">Ver todos -></a>
            </div>
            <div style="display:flex;flex-direction:column;gap:6px;">
              <a href="#/incidents?status=open" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Abiertos', incidents.open, incidents.open > 0 ? 'var(--risk-medium)' : 'var(--risk-low)')}</a>
              <a href="#/incidents?severity=p1" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('P1 / P2', incidents.p1_p2_open, incidents.p1_p2_open > 0 ? 'var(--risk-high)' : 'var(--risk-low)')}</a>
              <a href="#/incidents?nis2=pending" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('NIS2 pendiente', incidents.nis2_pending_notification, incidents.nis2_pending_notification > 0 ? 'var(--risk-critical)' : 'var(--risk-low)')}</a>
              ${ViewDashboard._moduleStatLine('Total historico', incidents.total, 'var(--text-muted)')}
            </div>
          </div>` : '',

      tasks: () => tasks ? `
          <div class="card" data-widget-id="tasks" style="flex:1;min-width:180px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
              <h3 style="margin:0;font-size:14px;">Tareas</h3>
              <a href="#/tasks" style="font-size:11px;color:var(--brand-purple);">Ver todos -></a>
            </div>
            <div style="display:flex;flex-direction:column;gap:6px;">
              <a href="#/tasks?overdue=1" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Vencidas', tasks.overdue, tasks.overdue > 0 ? 'var(--risk-high)' : 'var(--risk-low)')}</a>
              <a href="#/tasks?status=in_progress" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('En progreso', tasks.by_status?.in_progress || 0, 'var(--brand-purple)')}</a>
              <a href="#/tasks?status=pending" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Pendientes', tasks.by_status?.pending || 0, 'var(--text-muted)')}</a>
              <a href="#/tasks?status=done" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Completadas', tasks.by_status?.done || 0, 'var(--risk-low)')}</a>
            </div>
          </div>` : '',

      policies: () => policies ? `
          <div class="card" data-widget-id="policies" style="flex:1;min-width:180px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
              <h3 style="margin:0;font-size:14px;">Politicas</h3>
              <a href="#/policies" style="font-size:11px;color:var(--brand-purple);">Ver todas -></a>
            </div>
            <div style="display:flex;flex-direction:column;gap:6px;">
              <a href="#/policies?overdue=1" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Revision vencida', policies.overdue_review, policies.overdue_review > 0 ? 'var(--risk-high)' : 'var(--risk-low)')}</a>
              <a href="#/policies?status=published" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Publicadas', policies.by_status?.published || 0, 'var(--risk-low)')}</a>
              <a href="#/policies?status=review" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('En revision', policies.by_status?.review || 0, 'var(--brand-orange)')}</a>
              <a href="#/policies?status=draft" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Borradores', policies.by_status?.draft || 0, 'var(--text-muted)')}</a>
            </div>
          </div>` : '',

      gdpr: () => gdprData ? `
          <div class="card" data-widget-id="gdpr" style="flex:1;min-width:180px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
              <h3 style="margin:0;font-size:14px;">RGPD</h3>
              <a href="#/gdpr" style="font-size:11px;color:var(--brand-purple);">Ver todo -></a>
            </div>
            <div style="display:flex;flex-direction:column;gap:6px;">
              <a href="#/gdpr" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Actividades de tratamiento', gdprData.total_activities, 'var(--text-muted)')}</a>
              <a href="#/gdpr?requires_dpia=1" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Requieren DPIA', gdprData.requires_dpia, gdprData.requires_dpia > 0 ? 'var(--brand-orange)' : 'var(--text-muted)')}</a>
              <a href="#/gdpr?dpias_pending=1" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('DPIAs pendientes', gdprData.dpias_pending, gdprData.dpias_pending > 0 ? 'var(--risk-high)' : 'var(--risk-low)')}</a>
              <a href="#/gdpr" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Transferencias fuera UE', gdprData.transfers_outside_eu, gdprData.transfers_outside_eu > 0 ? 'var(--risk-medium)' : 'var(--text-muted)')}</a>
            </div>
          </div>` : '',

      bcp: () => `
        <div data-widget-id="bcp" style="margin-top:4px;">
          ${ViewDashboard._bcpPanelHtml(bcpData)}
        </div>`,

      tprm: () => `
        <div data-widget-id="tprm" style="margin-top:4px;">
          ${ViewDashboard._tprmPanelHtml(tprmData, risks)}
        </div>`,

      top10: (cfg = {}) => {
        const count = Number(cfg.count) || 10;
        const title = cfg.title || `Top ${count} riesgos por nivel residual`;
        const topRisks = risks.top_risks.slice(0, count);
        return `
        <div data-widget-id="top10" style="margin-top:16px;">
          <div class="card">
            <h3>${UI.esc(title)}</h3>
            ${topRisks.length === 0
              ? '<p style="color:var(--text-subtle);">No hay riesgos registrados todavia. Comienza creando activos y asociandoles amenazas.</p>'
              : `<div class="table-wrap"><table class="data">
                  <thead><tr><th>Codigo</th><th>Activo</th><th>Amenaza</th><th>Nivel</th><th>Reduccion</th></tr></thead>
                  <tbody>
                    ${topRisks.map(r => {
                      const red = r.inherent_level > 0
                        ? Math.round((1 - r.level / r.inherent_level) * 100) : 0;
                      return `<tr style="cursor:pointer;" onclick="location.hash='#/risks?id=${r.id}'">
                        <td>${UI.codePill(r.code)}</td>
                        <td>${UI.esc(r.asset)}</td>
                        <td>${UI.esc(r.threat)}</td>
                        <td>${UI.riskPill(r.level)}</td>
                        <td><span style="font-size:12px;font-weight:600;color:${red>0?'var(--risk-low)':red<0?'var(--risk-high)':'var(--text-muted)'};">${red > 0 ? '-' : red < 0 ? '+' : ''}${Math.abs(red)}%</span></td>
                      </tr>`;}).join('')}
                  </tbody>
                </table></div>`}
          </div>
        </div>`; },

      actions: () => `
        <div data-widget-id="actions" style="margin-top:16px;">
          <div class="card-row">
            <div class="card">
              <h3>Acciones rapidas</h3>
              <div style="display:flex;flex-direction:column;gap:8px;margin-top:8px;">
                <a href="#/risks?overdue=1" class="quick-action-btn ${risks.overdue_treatments > 0 ? 'urgent' : ''}">
                  <span>Tratamientos vencidos</span>
                  <span class="qa-count">${risks.overdue_treatments}</span>
                </a>
                <a href="#/risks" class="quick-action-btn ${risks.no_treatment_high > 0 ? 'warn' : ''}">
                  <span>Altos sin plan</span>
                  <span class="qa-count">${risks.no_treatment_high}</span>
                </a>
                <a href="#/controls" class="quick-action-btn ${risks.controls_overdue_reviews > 0 ? 'urgent' : ''}">
                  <span>Revisiones controles vencidas</span>
                  <span class="qa-count">${risks.controls_overdue_reviews}</span>
                </a>
                <a href="#/risks?owner=__unassigned__" class="quick-action-btn ${risks.no_owner > 0 ? 'warn' : ''}">
                  <span>Sin responsable</span>
                  <span class="qa-count">${risks.no_owner}</span>
                </a>
                ${incidents && incidents.nis2_pending_notification > 0 ? `
                <a href="#/incidents" class="quick-action-btn urgent">
                  <span>NIS2: notificacion pendiente</span>
                  <span class="qa-count">${incidents.nis2_pending_notification}</span>
                </a>` : ''}
                ${tasks && tasks.overdue > 0 ? `
                <a href="#/tasks" class="quick-action-btn warn">
                  <span>Tareas vencidas</span>
                  <span class="qa-count">${tasks.overdue}</span>
                </a>` : ''}
                ${policies && policies.overdue_review > 0 ? `
                <a href="#/policies" class="quick-action-btn warn">
                  <span>Politicas: revision vencida</span>
                  <span class="qa-count">${policies.overdue_review}</span>
                </a>` : ''}
                ${gdprData && gdprData.dpias_pending > 0 ? `
                <a href="#/gdpr" class="quick-action-btn warn">
                  <span>DPIAs pendientes</span>
                  <span class="qa-count">${gdprData.dpias_pending}</span>
                </a>` : ''}
                <a href="#/calendar" class="quick-action-btn">
                  <span>Ver calendario</span>
                  <span style="font-size:12px;color:var(--text-muted);">-></span>
                </a>
                <a href="#/heatmap" class="quick-action-btn">
                  <span>Mapa de calor</span>
                  <span style="font-size:12px;color:var(--text-muted);">-></span>
                </a>
                <a href="#/external-findings" class="quick-action-btn" id="dash-findings-link" style="display:none;">
                  <span>Hallazgos abiertos</span>
                  <span class="qa-count" id="dash-findings-count">0</span>
                </a>
              </div>
            </div>
            <div class="card" style="flex:2;">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                <h3 style="margin:0;">Proximos vencimientos <span style="font-size:12px;font-weight:400;color:var(--text-muted);">(30 dias)</span></h3>
                <a href="#/calendar" style="font-size:12px;color:var(--brand-purple);">Calendario -></a>
              </div>
              <div id="dash-upcoming"></div>
            </div>
            <div class="card" style="flex:2;">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                <h3 style="margin:0;">Revisiones de controles <span style="font-size:12px;font-weight:400;color:var(--text-muted);">(30 dias)</span></h3>
                <a href="#/controls" style="font-size:12px;color:var(--brand-purple);">Ver todos -></a>
              </div>
              <div id="dash-ctrl-upcoming"></div>
            </div>
            <div class="card" style="flex:2;" id="dash-activity-card" style="display:none;">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
                <h3 style="margin:0;">Actividad reciente</h3>
                <a href="#/audit" style="font-size:12px;color:var(--brand-purple);">Ver todo -></a>
              </div>
              <div id="dash-activity-body">
                <p style="color:var(--text-subtle);font-size:13px;">Cargando...</p>
              </div>
            </div>
          </div>
        </div>`,

      coverage: () => `
        <div data-widget-id="coverage" style="margin-top:16px;">
          <div class="card" id="dash-controls-card">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
              <h3 style="margin:0;">Cobertura de controles ISO 27002 por tema</h3>
              <a href="#/controls" style="font-size:12px;color:var(--brand-purple);">Ver todos -></a>
            </div>
            <div id="dash-controls-body">
              <p style="color:var(--text-subtle);font-size:13px;">Cargando...</p>
            </div>
          </div>
        </div>`,

      inbox: () => `
        <div data-widget-id="inbox" style="margin-bottom:16px;">
          <div id="dash-inbox-body">
            <div class="card"><p style="color:var(--text-subtle);font-size:13px;padding:4px 0;">Cargando bandeja...</p></div>
          </div>
        </div>`,
    };

    // Module widgets (incidents/tasks/policies/gdpr) are rendered as flex cards in a shared row.
    // Consecutive module widgets in the layout get grouped together visually.
    const MODULE_TYPES = new Set(['incidents', 'tasks', 'policies', 'gdpr']);
    const parts = [];
    let moduleBuffer = [];

    const flushModuleBuffer = () => {
      if (moduleBuffer.length === 0) return;
      parts.push(`<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:16px;">${moduleBuffer.join('')}</div>`);
      moduleBuffer = [];
    };

    for (const item of layout) {
      const type = typeof item === 'string' ? item : item.type;
      const cfg  = typeof item === 'object' ? (item.config || {}) : {};
      const html = widgets[type] ? widgets[type](cfg) : '';
      if (!html) continue;
      if (MODULE_TYPES.has(type)) {
        moduleBuffer.push(html);
      } else {
        flushModuleBuffer();
        parts.push(html);
      }
    }
    flushModuleBuffer();
    return parts.join('');
  },

  async render(main) {
    ViewDashboard._cachedMain = main;
    ViewDashboard._editMode = false;

    main.innerHTML = UI.sectionHeader(
      'Vision global del riesgo',
      'Resumen ejecutivo del estado del SGSI — todos los modulos',
      `<button id="dash-customize-btn" class="btn btn-outline btn-sm"
         onclick="ViewDashboard._editMode ? ViewDashboard._exitEdit() : ViewDashboard._enterEdit();"
         title="Personalizar widgets del dashboard">
         Personalizar dashboard
       </button>`
    ) + '<div id="dash-content">' + UI.notice('Cargando datos...') + '</div>';

    try {
      // Cargar datos de todos los modulos en paralelo para minimo tiempo de carga
      const [s, inc, tsk, pol, gdpr, ctx, bcpRaw, tprmRaw] = await Promise.allSettled([
        Api.risks.summary(),
        Api.incidents.summary(),
        Api.tasks.summary(),
        Api.policies.summary(),
        Api.gdpr.summary(),
        Api.context.get(),
        Api.get('/api/bcp/dashboard').catch(() => null),
        Api.tprm.summary().catch(() => null),
      ]);

      const risks    = s.status    === 'fulfilled' ? s.value    : null;
      const incidents = inc.status === 'fulfilled' ? inc.value  : null;
      const tasks    = tsk.status  === 'fulfilled' ? tsk.value  : null;
      const policies = pol.status  === 'fulfilled' ? pol.value  : null;
      const gdprData = gdpr.status === 'fulfilled' ? gdpr.value : null;
      const context  = ctx.status  === 'fulfilled' ? ctx.value  : null;
      const tprmData = tprmRaw.status === 'fulfilled' ? tprmRaw.value : null;
      const bcpData  = bcpRaw.status === 'fulfilled' ? bcpRaw.value : null;

      // Exponer metodologia activa globalmente para el formulario de riesgos
      if (context?.methodology) window._riskMethodology = context.methodology;

      if (!risks) throw new Error('No se pudo cargar el resumen de riesgos.');

      // Cachear datos para re-renders sin peticion al servidor
      ViewDashboard._cachedData = { risks, incidents, tasks, policies, gdprData, context, tprmData, bcpData };

      const c = document.getElementById('dash-content');

      // Banner de onboarding si el SGSI no esta configurado (v3.0)
      _renderOnboardingBanner(c);

      const layout = ViewDashboard._getLayout();
      const postureScore = ViewDashboard._calcPosture(risks, incidents, tasks, policies, gdprData);
      const methLabels = { iso27005:'ISO 27005', magerit:'MAGERIT v3', combined:'ISO 27005 + MAGERIT' };
      const meth = context?.methodology || 'iso27005';

      c.innerHTML = ViewDashboard._methBadgeHtml(context, meth, methLabels) +
        ViewDashboard._buildWidgetHtml(layout, risks, incidents, tasks, policies, gdprData, context, tprmData, bcpData, postureScore);

      // Cargar secciones async adicionales
      ViewDashboard._loadInbox();
      ViewDashboard._loadUpcoming();
      ViewDashboard._loadUpcomingControlReviews();
      ViewDashboard._loadControlsCoverage();
      ViewDashboard._loadRecentActivity();
      ViewDashboard._loadFindingsQuickAction();
    } catch (e) {
      main.innerHTML += `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  /* Calcula una puntuacion de postura de seguridad (0-100). */
  _calcPosture(risks, incidents, tasks, policies, gdpr) {
    let score = 100;
    const r = risks || {};

    // Penalizaciones por riesgos
    const totalR = r.total_risks || 0;
    if (totalR > 0) {
      const highPct = (r.by_band?.high || 0) / totalR;
      score -= Math.round(highPct * 25); // hasta -25 por % de riesgos altos
    }
    if ((r.overdue_treatments || 0) > 0) score -= Math.min(15, r.overdue_treatments * 3);
    if ((r.no_treatment_high || 0) > 0) score -= Math.min(10, r.no_treatment_high * 2);
    if ((r.no_owner || 0) > 0) score -= Math.min(5, r.no_owner);

    // Bonificacion por controles implementados
    const totalC = r.total_controls || 0;
    if (totalC > 0) {
      const implPct = (r.controls_implemented || 0) / totalC;
      score += Math.round(implPct * 10); // hasta +10 por cobertura de controles
    }

    // Penalizacion por incidentes
    if (incidents) {
      if ((incidents.p1_p2_open || 0) > 0) score -= Math.min(10, incidents.p1_p2_open * 5);
      if ((incidents.nis2_pending_notification || 0) > 0) score -= 5;
    }

    // Penalizacion por tareas vencidas
    if (tasks && (tasks.overdue || 0) > 0) score -= Math.min(8, tasks.overdue * 2);

    // Penalizacion por politicas sin revisar
    if (policies && (policies.overdue_review || 0) > 0) score -= Math.min(5, policies.overdue_review);

    // Penalizacion por DPIAs pendientes
    if (gdpr && (gdpr.dpias_pending || 0) > 0) score -= Math.min(5, gdpr.dpias_pending * 2);

    return Math.max(0, Math.min(100, score));
  },

  /* Banda de color segun la puntuacion. */
  _postureColor(score) {
    if (score >= 80) return 'var(--risk-low)';
    if (score >= 60) return '#D97706';
    if (score >= 40) return 'var(--risk-high)';
    return 'var(--risk-critical)';
  },
  _postureLabel(score) {
    if (score >= 80) return 'Buena';
    if (score >= 60) return 'Aceptable';
    if (score >= 40) return 'Deficiente';
    return 'Critica';
  },

  /* HTML del panel de postura de seguridad. */
  _postureHtml(score, risks, incidents, tasks, policies, gdprData) {
    const color = ViewDashboard._postureColor(score);
    const label = ViewDashboard._postureLabel(score);
    const circ = 2 * Math.PI * 30;
    const dash = (score / 100) * circ;

    // Cuenta de alertas criticas para mostrar en el banner
    const critItems = [];
    if (risks?.overdue_treatments > 0) critItems.push(`${risks.overdue_treatments} tratamiento${risks.overdue_treatments>1?'s':''} vencido${risks.overdue_treatments>1?'s':''}`);
    if (incidents?.p1_p2_open > 0) critItems.push(`${incidents.p1_p2_open} incidente${incidents.p1_p2_open>1?'s':''} P1/P2 abierto${incidents.p1_p2_open>1?'s':''}`);
    if (incidents?.nis2_pending_notification > 0) critItems.push(`${incidents.nis2_pending_notification} notificacion NIS2 pendiente`);
    if (tasks?.overdue > 0) critItems.push(`${tasks.overdue} tarea${tasks.overdue>1?'s':''} vencida${tasks.overdue>1?'s':''}`);
    if (policies?.overdue_review > 0) critItems.push(`${policies.overdue_review} politica${policies.overdue_review>1?'s':''} con revision vencida`);
    if (gdprData?.dpias_pending > 0) critItems.push(`${gdprData.dpias_pending} DPIA pendiente${gdprData.dpias_pending>1?'s':''}`);

    return `
      <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:20px;display:flex;align-items:center;gap:24px;flex-wrap:wrap;">
        <!-- Indicador circular de postura -->
        <div style="flex-shrink:0;text-align:center;">
          <svg width="90" height="90" viewBox="0 0 70 70">
            <circle cx="35" cy="35" r="30" fill="none" stroke="var(--border)" stroke-width="7"/>
            <circle cx="35" cy="35" r="30" fill="none" stroke="${color}" stroke-width="7"
              stroke-dasharray="${dash.toFixed(1)} ${circ.toFixed(1)}" stroke-linecap="round"
              transform="rotate(-90 35 35)" style="transition:stroke-dasharray .6s;"/>
            <text x="35" y="32" text-anchor="middle" dominant-baseline="middle" font-size="16" font-weight="800" fill="${color}">${score}</text>
            <text x="35" y="46" text-anchor="middle" dominant-baseline="middle" font-size="7" fill="var(--text-muted)">/100</text>
          </svg>
          <div style="font-size:12px;font-weight:700;color:${color};margin-top:2px;">${label}</div>
          <div style="font-size:10px;color:var(--text-subtle);">Postura global</div>
        </div>

        <!-- Resumen rapido por modulo -->
        <div style="flex:1;min-width:260px;">
          <div style="font-size:14px;font-weight:700;color:var(--text-base);margin-bottom:10px;">Estado del SGSI</div>
          <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:8px;">
            ${ViewDashboard._moduleChipHtml('Riesgos', risks?.total_risks ?? '-', risks?.by_band?.high > 0 ? 'warn' : 'ok', '#/risks')}
            ${ViewDashboard._moduleChipHtml('Controles', (risks?.controls_implemented ?? '-') + '/' + (risks?.total_controls ?? '-'), 'neutral', '#/controls')}
            ${incidents ? ViewDashboard._moduleChipHtml('Incidentes', incidents.open + ' abiertos', incidents.p1_p2_open > 0 ? 'crit' : incidents.open > 0 ? 'warn' : 'ok', '#/incidents') : ''}
            ${tasks ? ViewDashboard._moduleChipHtml('Tareas', tasks.overdue + ' vencidas', tasks.overdue > 0 ? 'warn' : 'ok', '#/tasks') : ''}
            ${policies ? ViewDashboard._moduleChipHtml('Politicas', policies.total + ' total', policies.overdue_review > 0 ? 'warn' : 'ok', '#/policies') : ''}
            ${gdprData ? ViewDashboard._moduleChipHtml('RGPD', gdprData.dpias_pending + ' DPIAs', gdprData.dpias_pending > 0 ? 'warn' : 'ok', '#/gdpr') : ''}
          </div>
        </div>

        <!-- Alertas criticas (si las hay) -->
        ${critItems.length ? `
        <div style="flex:1;min-width:220px;border-left:3px solid ${score < 60 ? 'var(--risk-high)' : 'var(--risk-medium)'};padding-left:16px;">
          <div style="font-size:12px;font-weight:700;color:var(--text-muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px;">Requiere atencion</div>
          ${critItems.slice(0, 5).map(item => `
            <div style="display:flex;align-items:center;gap:6px;margin-bottom:5px;font-size:12px;">
              <span style="width:6px;height:6px;border-radius:50%;background:${score < 60 ? 'var(--risk-high)' : 'var(--risk-medium)'};flex-shrink:0;"></span>
              <span>${UI.esc(item)}</span>
            </div>`).join('')}
          ${critItems.length > 5 ? `<div style="font-size:11px;color:var(--text-muted);margin-top:4px;">+${critItems.length - 5} alertas mas</div>` : ''}
        </div>` : `
        <div style="flex:1;min-width:180px;border-left:3px solid var(--risk-low);padding-left:16px;">
          <div style="font-size:12px;font-weight:700;color:var(--risk-low);margin-bottom:4px;">Sin alertas criticas</div>
          <div style="font-size:12px;color:var(--text-muted);">Todos los indicadores dentro de rangos aceptables.</div>
        </div>`}
      </div>
    `;
  },

  /* Chip de modulo para el panel de postura. */
  _moduleChipHtml(label, value, state, href) {
    const colors = { ok: 'var(--risk-low)', warn: 'var(--risk-medium)', crit: 'var(--risk-high)', neutral: 'var(--brand-purple)' };
    const bg = { ok: 'rgba(16,185,129,.08)', warn: 'rgba(245,158,11,.08)', crit: 'rgba(239,68,68,.08)', neutral: 'rgba(89,0,141,.06)' };
    const c = colors[state] || colors.neutral;
    const b = bg[state] || bg.neutral;
    return `
      <a href="${href}" style="text-decoration:none;display:block;background:${b};border:1px solid ${c}20;border-radius:8px;padding:8px 10px;transition:box-shadow .15s;" title="Ir a ${label}">
        <div style="font-size:11px;font-weight:700;color:${c};text-transform:uppercase;letter-spacing:.3px;margin-bottom:2px;">${UI.esc(label)}</div>
        <div style="font-size:13px;font-weight:600;color:var(--text-base);">${UI.esc(String(value))}</div>
      </a>
    `;
  },

  /* Panel BCP/ISO 22301 para el dashboard global. */
  _bcpPanelHtml(bcp) {
    if (!bcp || (!bcp.total_processes && bcp.total_processes !== 0)) return '';
    const biaPct   = bcp.bia_avg_pct   ?? 0;
    const approved = bcp.approved_plans ?? 0;
    const overdue  = bcp.processes_overdue_test ?? 0;
    const critical = bcp.critical_processes ?? 0;
    const testsDone= bcp.tests_done ?? 0;
    const total    = bcp.total_processes ?? 0;

    // Calcular semaforo BCP
    const bcpOk = approved > 0 && biaPct >= 60 && overdue === 0;
    const bcpWarn = approved === 0 || biaPct < 60 || overdue > 0;
    const statusColor = bcpOk ? 'var(--risk-low)' : bcpWarn ? 'var(--risk-medium)' : 'var(--risk-critical)';
    const statusLabel = bcpOk ? 'Operativo' : approved === 0 ? 'Sin planes' : biaPct < 40 ? 'BIA incompleto' : 'Revision necesaria';

    const bar = (pct, col) => `
      <div style="height:4px;border-radius:2px;background:var(--bg-3);overflow:hidden;margin-top:2px;">
        <div style="height:100%;width:${pct}%;background:${col};border-radius:2px;transition:width .4s;"></div>
      </div>`;

    return `
    <div class="card" style="margin-top:16px;" onclick="location.hash='#/bcp'" style="cursor:pointer;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
        <div style="display:flex;align-items:center;gap:10px;">
          <div style="width:10px;height:10px;border-radius:50%;background:${statusColor};flex-shrink:0;box-shadow:0 0 0 3px ${statusColor}22;"></div>
          <h3 style="margin:0;font-size:14px;">Continuidad de Negocio <span style="font-size:11px;font-weight:400;color:var(--text-subtle);">ISO 22301</span></h3>
          <span style="font-size:11px;padding:2px 8px;border-radius:20px;font-weight:600;background:${statusColor}22;color:${statusColor};">${statusLabel}</span>
        </div>
        <a href="#/bcp" style="font-size:11px;color:var(--brand-purple);">Ver modulo BCP -></a>
      </div>
      <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:12px;">
        <div style="text-align:center;">
          <div style="font-size:22px;font-weight:800;color:var(--text);">${total}</div>
          <div style="font-size:10px;color:var(--text-subtle);text-transform:uppercase;font-weight:600;letter-spacing:.04em;">Procesos</div>
          ${bar(total ? 100 : 0, 'var(--brand-purple)')}
        </div>
        <div style="text-align:center;">
          <div style="font-size:22px;font-weight:800;color:${critical > 0 ? 'var(--risk-critical)' : 'var(--text)'};">${critical}</div>
          <div style="font-size:10px;color:var(--text-subtle);text-transform:uppercase;font-weight:600;letter-spacing:.04em;">Criticos</div>
          ${bar(total ? critical/total*100 : 0, 'var(--risk-critical)')}
        </div>
        <div style="text-align:center;">
          <div style="font-size:22px;font-weight:800;color:${biaPct < 60 ? 'var(--risk-medium)' : 'var(--risk-low)'};">${biaPct}%</div>
          <div style="font-size:10px;color:var(--text-subtle);text-transform:uppercase;font-weight:600;letter-spacing:.04em;">BIA media</div>
          ${bar(biaPct, biaPct >= 80 ? 'var(--risk-low)' : biaPct >= 50 ? 'var(--risk-medium)' : 'var(--risk-critical)')}
        </div>
        <div style="text-align:center;">
          <div style="font-size:22px;font-weight:800;color:${approved === 0 ? 'var(--risk-critical)' : 'var(--risk-low)'};">${approved}</div>
          <div style="font-size:10px;color:var(--text-subtle);text-transform:uppercase;font-weight:600;letter-spacing:.04em;">Planes aprobados</div>
          ${bar(approved > 0 ? 100 : 0, 'var(--risk-low)')}
        </div>
        <div style="text-align:center;">
          <div style="font-size:22px;font-weight:800;color:${testsDone === 0 ? 'var(--risk-medium)' : 'var(--risk-low)'};">${testsDone}</div>
          <div style="font-size:10px;color:var(--text-subtle);text-transform:uppercase;font-weight:600;letter-spacing:.04em;">Tests OK</div>
          ${bar(testsDone > 0 ? 100 : 0, 'var(--risk-low)')}
        </div>
        <div style="text-align:center;">
          <div style="font-size:22px;font-weight:800;color:${overdue > 0 ? 'var(--risk-high)' : 'var(--risk-low)'};">${overdue}</div>
          <div style="font-size:10px;color:var(--text-subtle);text-transform:uppercase;font-weight:600;letter-spacing:.04em;">Sin test 12m</div>
          ${bar(overdue > 0 ? Math.min(overdue/Math.max(total,1)*100, 100) : 0, 'var(--risk-high)')}
        </div>
      </div>
      ${bcp.last_test_date ? `<div style="font-size:11px;color:var(--text-subtle);margin-top:10px;text-align:right;">Ultimo test: ${new Date(bcp.last_test_date).toLocaleDateString('es-ES')}</div>` : ''}
    </div>`;
  },

  /* Panel TPRM (gestion de riesgo de terceros) para el dashboard global. */
  _tprmPanelHtml(tprm, risks) {
    if (!tprm) return '';
    const totalSup   = tprm.total                           ?? 0;
    const critical   = tprm.by_residual_level?.critical     ?? 0;
    const high       = tprm.by_residual_level?.high         ?? 0;
    const pending    = tprm.pending_assessments             ?? 0;
    const completed  = tprm.completed_assessments           ?? 0;
    const supRisks   = risks?.supplier_risks_count          ?? 0;

    if (totalSup === 0) return '';

    const critColor = critical > 0 ? '#DC2626' : 'var(--text-muted)';
    const pendColor = pending  > 0 ? '#D97706' : 'var(--text-muted)';

    const bar = (pct, color) => `
      <div style="height:4px;border-radius:2px;background:var(--bg-3);overflow:hidden;margin-top:4px;">
        <div style="height:100%;width:${Math.min(pct,100)}%;background:${color};border-radius:2px;"></div>
      </div>`;

    return `
    <div class="card" style="margin-top:16px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;flex-wrap:wrap;gap:8px;">
        <div>
          <h3 style="margin:0;">Gestion de riesgo de terceros (TPRM)</h3>
          <p style="font-size:12px;color:var(--text-muted);margin:3px 0 0;">ISO 27001 A.5.19 — Seguridad de la cadena de suministro</p>
        </div>
        <a href="#/suppliers" style="font-size:12px;color:var(--brand-purple);font-weight:600;text-decoration:none;">
          Ver modulo TPRM &rarr;
        </a>
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;">
        <div style="background:var(--bg-2);border-radius:8px;padding:12px 14px;border:1px solid var(--border);">
          <div style="font-size:11px;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em;">Proveedores</div>
          <div style="font-size:28px;font-weight:800;color:var(--brand-purple);font-family:var(--font-mono);margin-top:4px;">${totalSup}</div>
          <div style="font-size:11px;color:var(--text-subtle);">en cartera activa</div>
        </div>
        <div style="background:var(--bg-2);border-radius:8px;padding:12px 14px;border:1px solid var(--border);${critical > 0 ? 'border-color:#FCA5A5;background:#FFF5F5;' : ''}">
          <div style="font-size:11px;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em;">Riesgo critico</div>
          <div style="font-size:28px;font-weight:800;color:${critColor};font-family:var(--font-mono);margin-top:4px;">${critical}</div>
          <div style="font-size:11px;color:var(--text-subtle);">${critical > 0 ? 'proveedores criticos' : 'sin proveedores criticos'}</div>
          ${bar(totalSup ? critical/totalSup*100 : 0, '#DC2626')}
        </div>
        <div style="background:var(--bg-2);border-radius:8px;padding:12px 14px;border:1px solid var(--border);">
          <div style="font-size:11px;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em;">Riesgo alto</div>
          <div style="font-size:28px;font-weight:800;color:${high > 0 ? '#D97706' : 'var(--text-muted)'};font-family:var(--font-mono);margin-top:4px;">${high}</div>
          <div style="font-size:11px;color:var(--text-subtle);">proveedores nivel alto</div>
          ${bar(totalSup ? high/totalSup*100 : 0, '#D97706')}
        </div>
        <div style="background:var(--bg-2);border-radius:8px;padding:12px 14px;border:1px solid var(--border);${pending > 0 ? 'border-color:#FCD34D;background:#FFFBEB;' : ''}">
          <div style="font-size:11px;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em;">Evaluaciones pendientes</div>
          <div style="font-size:28px;font-weight:800;color:${pendColor};font-family:var(--font-mono);margin-top:4px;">${pending}</div>
          <div style="font-size:11px;color:var(--text-subtle);">${completed} completadas · <a href="#/suppliers?tab=evaluaciones" style="color:var(--brand-purple);">ver evaluaciones</a></div>
        </div>
        ${supRisks > 0 ? `
        <div style="background:var(--bg-2);border-radius:8px;padding:12px 14px;border:1px solid var(--border);cursor:pointer;"
             onclick="location.hash='#/risks?supplier_only=1'" title="Ver riesgos de proveedores">
          <div style="font-size:11px;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em;">Riesgos de proveedor</div>
          <div style="font-size:28px;font-weight:800;color:var(--brand-orange);font-family:var(--font-mono);margin-top:4px;">${supRisks}</div>
          <div style="font-size:11px;color:var(--brand-purple);">clic para filtrar en registro</div>
        </div>` : ''}
      </div>
    </div>`;
  },

  /* Fila de tarjetas de modulos secundarios (incidentes, tareas, politicas, GDPR, BCP). */
  _modulesRowHtml(incidents, tasks, policies, gdprData, bcpData) {
    const cards = [];

    if (incidents) {
      cards.push(`
        <div class="card" style="flex:1;min-width:200px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <h3 style="margin:0;font-size:14px;">Incidentes</h3>
            <a href="#/incidents" style="font-size:11px;color:var(--brand-purple);">Ver todos -></a>
          </div>
          <div style="display:flex;flex-direction:column;gap:6px;">
            <a href="#/incidents?status=open" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Abiertos', incidents.open, incidents.open > 0 ? 'var(--risk-medium)' : 'var(--risk-low)')}</a>
            <a href="#/incidents?severity=p1" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('P1 / P2', incidents.p1_p2_open, incidents.p1_p2_open > 0 ? 'var(--risk-high)' : 'var(--risk-low)')}</a>
            <a href="#/incidents?nis2=pending" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('NIS2 pendiente', incidents.nis2_pending_notification, incidents.nis2_pending_notification > 0 ? 'var(--risk-critical)' : 'var(--risk-low)')}</a>
            ${ViewDashboard._moduleStatLine('Total historico', incidents.total, 'var(--text-muted)')}
          </div>
        </div>`);
    }

    if (tasks) {
      const done = tasks.by_status?.done || 0;
      const inProgress = tasks.by_status?.in_progress || 0;
      const pending = tasks.by_status?.pending || 0;
      cards.push(`
        <div class="card" style="flex:1;min-width:200px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <h3 style="margin:0;font-size:14px;">Tareas</h3>
            <a href="#/tasks" style="font-size:11px;color:var(--brand-purple);">Ver todos -></a>
          </div>
          <div style="display:flex;flex-direction:column;gap:6px;">
            <a href="#/tasks?overdue=1" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Vencidas', tasks.overdue, tasks.overdue > 0 ? 'var(--risk-high)' : 'var(--risk-low)')}</a>
            <a href="#/tasks?status=in_progress" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('En progreso', inProgress, 'var(--brand-purple)')}</a>
            <a href="#/tasks?status=pending" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Pendientes', pending, 'var(--text-muted)')}</a>
            <a href="#/tasks?status=done" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Completadas', done, 'var(--risk-low)')}</a>
          </div>
        </div>`);
    }

    if (policies) {
      const pub = policies.by_status?.published || 0;
      const rev = policies.by_status?.review || 0;
      const draft = policies.by_status?.draft || 0;
      cards.push(`
        <div class="card" style="flex:1;min-width:200px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <h3 style="margin:0;font-size:14px;">Politicas</h3>
            <a href="#/policies" style="font-size:11px;color:var(--brand-purple);">Ver todas -></a>
          </div>
          <div style="display:flex;flex-direction:column;gap:6px;">
            <a href="#/policies?overdue=1" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Revision vencida', policies.overdue_review, policies.overdue_review > 0 ? 'var(--risk-high)' : 'var(--risk-low)')}</a>
            <a href="#/policies?status=published" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Publicadas', pub, 'var(--risk-low)')}</a>
            <a href="#/policies?status=review" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('En revision', rev, 'var(--brand-orange)')}</a>
            <a href="#/policies?status=draft" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Borradores', draft, 'var(--text-muted)')}</a>
          </div>
        </div>`);
    }

    if (gdprData) {
      cards.push(`
        <div class="card" style="flex:1;min-width:200px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <h3 style="margin:0;font-size:14px;">RGPD</h3>
            <a href="#/gdpr" style="font-size:11px;color:var(--brand-purple);">Ver todo -></a>
          </div>
          <div style="display:flex;flex-direction:column;gap:6px;">
            <a href="#/gdpr" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Actividades de tratamiento', gdprData.total_activities, 'var(--text-muted)')}</a>
            <a href="#/gdpr?requires_dpia=1" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Requieren DPIA', gdprData.requires_dpia, gdprData.requires_dpia > 0 ? 'var(--brand-orange)' : 'var(--text-muted)')}</a>
            <a href="#/gdpr?dpias_pending=1" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('DPIAs pendientes', gdprData.dpias_pending, gdprData.dpias_pending > 0 ? 'var(--risk-high)' : 'var(--risk-low)')}</a>
            <a href="#/gdpr" style="text-decoration:none;color:inherit;">${ViewDashboard._moduleStatLine('Transferencias fuera UE', gdprData.transfers_outside_eu, gdprData.transfers_outside_eu > 0 ? 'var(--risk-medium)' : 'var(--text-muted)')}</a>
          </div>
        </div>`);
    }

    if (bcpData && (bcpData.total_processes > 0 || bcpData.approved_plans > 0)) {
      const biaPct = bcpData.bia_avg_pct ?? 0;
      const ovrd = bcpData.processes_overdue_test ?? 0;
      cards.push(`
        <div class="card" style="flex:1;min-width:200px;cursor:pointer;" onclick="location.hash='#/bcp'">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <h3 style="margin:0;font-size:14px;">Continuidad BCP</h3>
            <a href="#/bcp" style="font-size:11px;color:var(--brand-purple);" onclick="event.stopPropagation()">Ver -></a>
          </div>
          <div style="display:flex;flex-direction:column;gap:6px;">
            ${ViewDashboard._moduleStatLine('Procesos registrados', bcpData.total_processes ?? 0, 'var(--text-muted)')}
            ${ViewDashboard._moduleStatLine('Planes aprobados', bcpData.approved_plans ?? 0, (bcpData.approved_plans ?? 0) === 0 ? 'var(--risk-high)' : 'var(--risk-low)')}
            ${ViewDashboard._moduleStatLine('BIA completado (media)', biaPct + '%', biaPct < 60 ? 'var(--risk-medium)' : 'var(--risk-low)')}
            ${ViewDashboard._moduleStatLine('Sin test en 12 meses', ovrd, ovrd > 0 ? 'var(--risk-high)' : 'var(--risk-low)')}
          </div>
        </div>`);
    }

    if (!cards.length) return '';
    return `<div class="card-row" style="margin-top:16px;">${cards.join('')}</div>`;
  },

  /* Linea de stat dentro de una tarjeta de modulo. */
  _moduleStatLine(label, value, color) {
    return `
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;padding:3px 0;border-bottom:1px solid var(--border);">
        <span style="color:var(--text-muted);">${UI.esc(label)}</span>
        <span style="font-weight:700;color:${color};">${value ?? '-'}</span>
      </div>`;
  },

  async _loadRecentActivity() {
    // Solo visible para admins (endpoint de auditoria requiere admin)
    const u = Auth.user();
    const card = document.getElementById('dash-activity-card');
    if (!card) return;
    if (!u || (u.role !== 'admin' && u.role !== 'superadmin')) { card.style.display = 'none'; return; }
    card.style.display = '';
    const el = document.getElementById('dash-activity-body');
    try {
      const data = await Api.audit.list({ limit: 8 });
      const items = data.items || [];
      if (!items.length) {
        el.innerHTML = '<p style="color:var(--text-subtle);font-size:13px;">Sin actividad registrada.</p>';
        return;
      }
      const actionColors = {
        create: '#065F46', update: '#1E40AF', delete: '#991B1B', login: '#5B21B6',
      };
      const entityLabel = {
        risk: 'Riesgo', asset: 'Activo', control: 'Control', user: 'Usuario',
        threat: 'Amenaza', vulnerability: 'Vuln.', context: 'Contexto',
        alert_rule: 'Alerta', email_settings: 'SMTP', control_impl: 'Control impl.',
        incident: 'Incidente', policy: 'Politica', task: 'Tarea', supplier: 'Proveedor',
      };
      el.innerHTML = items.map(e => {
        const ts = new Date(e.timestamp).toLocaleString('es-ES', {
          day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
        });
        const actionColor = actionColors[e.action] || '#6B7280';
        return `<div style="display:flex;align-items:center;gap:8px;padding:5px 0;
                             border-bottom:1px solid var(--border);font-size:12px;">
          <span style="color:var(--text-subtle);min-width:88px;font-family:var(--font-mono);">${ts}</span>
          <span style="width:6px;height:6px;border-radius:50%;background:${actionColor};flex-shrink:0;"></span>
          <span style="color:var(--text-muted);min-width:60px;">${UI.esc(entityLabel[e.entity_type] || e.entity_type)}</span>
          <span style="color:var(--text);flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
            ${UI.esc(e.user_name || e.user_email || 'Sistema')}
          </span>
        </div>`;
      }).join('');
    } catch (_) {
      if (card) card.style.display = 'none';
    }
  },

  async _loadControlsCoverage() {
    const el = document.getElementById('dash-controls-body');
    if (!el) return;
    try {
      const themes = await Api.controls.statsByTheme();
      if (!themes.length) {
        el.innerHTML = '<p style="color:var(--text-subtle);font-size:13px;">Sin controles implementados todavia. Accede a Controles para empezar.</p>';
        return;
      }
      const themeColors = {
        organizational: 'var(--brand-purple)',
        people: 'var(--brand-orange)',
        physical: '#2563EB',
        technological: '#059669',
      };
      el.innerHTML = `
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;">
          ${themes.map(t => {
            const matPct = Math.round((t.avg_maturity / 5) * 100);
            const implPct = t.count ? Math.round((t.implemented / t.count) * 100) : 0;
            const color = themeColors[t.theme] || 'var(--brand-purple)';
            return `
              <div style="padding:14px;border-radius:8px;background:var(--bg-2);border:1px solid var(--border);">
                <div style="font-size:13px;font-weight:600;color:${color};margin-bottom:10px;">
                  ${UI.esc(t.label)}
                </div>
                <div style="margin-bottom:8px;">
                  <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-bottom:3px;">
                    <span>Madurez media</span>
                    <span style="font-weight:700;color:var(--text);">${t.avg_maturity}/5</span>
                  </div>
                  <div style="height:6px;border-radius:3px;background:var(--bg-3);overflow:hidden;">
                    <div style="height:100%;width:${matPct}%;background:${color};border-radius:3px;transition:width .5s;"></div>
                  </div>
                </div>
                <div>
                  <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-bottom:3px;">
                    <span>Implementados</span>
                    <span style="font-weight:700;color:var(--text);">${t.implemented}/${t.count}</span>
                  </div>
                  <div style="height:6px;border-radius:3px;background:var(--bg-3);overflow:hidden;">
                    <div style="height:100%;width:${implPct}%;background:${color};opacity:0.5;border-radius:3px;transition:width .5s;"></div>
                  </div>
                </div>
              </div>`;
          }).join('')}
        </div>`;
    } catch (_) {
      const el2 = document.getElementById('dash-controls-body');
      if (el2) el2.innerHTML = '<p style="color:var(--text-subtle);font-size:13px;">No disponible.</p>';
    }
  },

  async _loadInbox() {
    const el = document.getElementById('dash-inbox-body');
    if (!el || typeof ViewInbox === 'undefined') return;
    const layout = ViewDashboard._getLayout();
    const inboxItem = layout.find(w => w.type === 'inbox');
    const limit = Number(inboxItem?.config?.limit) || 5;
    await ViewInbox.renderEmbedded(el, { limit });
  },

  async _loadUpcomingControlReviews() {
    const el = document.getElementById('dash-ctrl-upcoming');
    if (!el) return;
    try {
      const all = await Api.impls.list();
      const now = new Date();
      const in30 = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
      // Incluir vencidas y proximas revisiones (excluir not_implemented)
      const reviews = all
        .filter(c => c.next_review && c.status !== 'not_implemented')
        .map(c => ({ ...c, _due: new Date(c.next_review) }))
        .filter(c => c._due <= in30)
        .sort((a, b) => a._due - b._due)
        .slice(0, 8);

      if (!reviews.length) {
        el.innerHTML = '<p style="color:var(--text-subtle);font-size:13px;">Sin revisiones programadas en los proximos 30 dias.</p>';
        return;
      }
      el.innerHTML = reviews.map(c => {
        const days = Math.ceil((c._due - now) / (1000 * 60 * 60 * 24));
        const overdue = days < 0;
        const urgency = overdue ? 'var(--risk-high)' : days <= 7 ? 'var(--risk-medium)' : 'var(--text-muted)';
        const label = overdue
          ? `${Math.abs(days)} dias vencido`
          : days === 0 ? 'Hoy' : days === 1 ? 'Manana' : `en ${days} dias`;
        return `<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border);">
          ${UI.codePill(c.control?.code || '-')}
          <span style="flex:1;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
                title="${UI.esc(c.name)}">${UI.esc(c.name)}</span>
          <span style="font-size:11px;font-weight:600;color:${urgency};white-space:nowrap;">${label}</span>
        </div>`;
      }).join('');
    } catch (_) { /* silencioso */ }
  },

  async _loadFindingsQuickAction() {
    const link = document.getElementById('dash-findings-link');
    const countEl = document.getElementById('dash-findings-count');
    if (!link || !countEl) return;
    try {
      const s = await Api.findings.summary();
      const open = s.open || 0;
      if (!open) { link.style.display = 'none'; return; }
      countEl.textContent = open;
      link.classList.toggle('warn', open > 0);
      link.style.display = '';
    } catch (_) { /* silencioso */ }
  },

  async _loadUpcoming() {
    const el = document.getElementById('dash-upcoming');
    if (!el) return;
    try {
      const all = await Api.risks.list();
      const now = new Date();
      const in30 = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
      const upcoming = all
        .filter(r => r.treatment_due_date && r.status !== 'accepted' && r.status !== 'closed')
        .map(r => ({ ...r, _due: new Date(r.treatment_due_date) }))
        .filter(r => r._due >= now && r._due <= in30)
        .sort((a, b) => a._due - b._due)
        .slice(0, 8);

      if (!upcoming.length) {
        el.innerHTML = '<p style="color:var(--text-subtle);font-size:13px;">Sin vencimientos en los proximos 30 dias.</p>';
        return;
      }
      el.innerHTML = upcoming.map(r => {
        const days = Math.ceil((r._due - now) / (1000 * 60 * 60 * 24));
        const urgency = days <= 7 ? 'var(--risk-high)' : days <= 14 ? 'var(--risk-medium)' : 'var(--risk-low)';
        return `<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border);">
          ${UI.codePill(r.code)}
          <span style="flex:1;font-size:13px;">${UI.esc(r.asset?.name||'-')}</span>
          <span style="font-size:12px;font-weight:600;color:${urgency};white-space:nowrap;">
            ${days === 0 ? 'Hoy' : days === 1 ? 'Manana' : 'en ' + days + ' dias'}
          </span>
        </div>`;
      }).join('');
    } catch (_) { /* silencioso */ }
  },

  _bar(v, total, color) {
    if (!total) return '';
    const pct = (v / total) * 100;
    return `<div style="width:${pct}%;background:${color};"></div>`;
  },

  /* SVG donut chart.
     segments: [{ v, color, label }]
     total: sum of all segments (can include unlabeled remainder)
  */
  _donut(segments, total) {
    const r = 38;
    const cx = 52, cy = 52;
    const circ = 2 * Math.PI * r;
    const size = 104;

    if (!total) {
      return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="flex-shrink:0;">
        <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--bg-3)" stroke-width="18"/>
        <text x="${cx}" y="${cy}" text-anchor="middle" dominant-baseline="middle"
              font-size="13" fill="var(--text-muted)">0</text>
      </svg>`;
    }

    let offset = 0;
    let paths = '';
    for (const seg of segments) {
      const frac = seg.v / total;
      const dash = frac * circ;
      const rotateDeg = -90 + (offset / circ) * 360;
      paths += `<circle
        cx="${cx}" cy="${cy}" r="${r}"
        fill="none"
        stroke="${seg.color}"
        stroke-width="18"
        stroke-dasharray="${dash} ${circ}"
        transform="rotate(${rotateDeg} ${cx} ${cy})"
        style="transition:stroke-dasharray .5s;">
        <title>${seg.label}: ${seg.v}</title>
      </circle>`;
      offset += dash;
    }

    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"
                style="flex-shrink:0;" role="img" aria-label="Distribucion de riesgo">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--bg-3)" stroke-width="18"/>
      ${paths}
      <text x="${cx}" y="${cy - 7}" text-anchor="middle" dominant-baseline="middle"
            font-size="20" font-weight="700" fill="var(--text)">${total}</text>
      <text x="${cx}" y="${cy + 12}" text-anchor="middle" dominant-baseline="middle"
            font-size="9" fill="var(--text-muted)" letter-spacing="0.5">RIESGOS</text>
    </svg>`;
  },
};
