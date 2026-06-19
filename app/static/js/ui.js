/* Utilidades de UI compartidas. */
const UI = {
  esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g,
      c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  },

  riskPill(level) {
    const lvl = Math.max(0, Math.min(8, Number(level) || 0));
    return `<span class="risk-pill risk-pill-${lvl}">${lvl}</span>`;
  },

  riskBand(level) {
    const lvl = Number(level) || 0;
    if (window.RiskLevels) {
      const b = RiskLevels.bandFor(lvl);
      return `<span class="badge" style="background:${b.color};color:#fff;opacity:0.9;">${b.label}</span>`;
    }
    if (lvl <= 2) return '<span class="badge badge-low">Bajo</span>';
    if (lvl <= 5) return '<span class="badge badge-medium">Medio</span>';
    return '<span class="badge badge-high">Alto</span>';
  },

  codePill(code) { return `<span class="code-pill">${UI.esc(code)}</span>`; },

  sectionHeader(title, subtitle, actions) {
    return `<div class="section-header">
      <div class="bracket"></div>
      <div style="flex:1">
        <h1>${UI.esc(title)}<small>${UI.esc(subtitle || '')}</small></h1>
      </div>
      ${actions ? `<div style="display:flex;gap:8px;">${actions}</div>` : ''}
      <button class="btn btn-ghost btn-icon btn-print" onclick="window.print()" title="Imprimir vista actual">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
      </button>
    </div>`;
  },

  emptyState(title, hint) {
    return `<div class="card empty-state">
      <h3>${UI.esc(title)}</h3>
      <p>${UI.esc(hint || '')}</p>
    </div>`;
  },

  notice(text, variant) {
    return `<div class="notice ${variant === 'warn' ? 'notice-warn' : ''}">${UI.esc(text)}</div>`;
  },

  modal(title, html, opts = {}) {
    const root = document.getElementById('modal-root');
    const widthStyle = opts.width ? `max-width:${opts.width};width:95vw;` : '';
    root.innerHTML = `
      <div class="modal-bg" id="modal-bg">
        <div class="modal" style="${widthStyle}">
          <div class="modal-head">
            <h2>${UI.esc(title)}</h2>
            <button class="btn btn-ghost" id="modal-close">x</button>
          </div>
          <div class="modal-body" id="modal-body">${html}</div>
          ${opts.actions ? `<div class="modal-foot">${opts.actions}</div>` : ''}
        </div>
      </div>`;
    document.getElementById('modal-close').onclick = UI.closeModal;
    document.getElementById('modal-bg').addEventListener('click', e => {
      if (e.target.id === 'modal-bg') UI.closeModal();
    });
  },

  openModal(innerHtml, opts = {}) {
    /* Renderiza HTML crudo dentro del contenedor modal (sin title fijo). */
    const root = document.getElementById('modal-root');
    const width = opts.width || '560px';
    root.innerHTML = `
      <div class="modal-bg" id="modal-bg">
        <div class="modal" style="max-width:${width};width:95vw;">
          ${innerHtml}
        </div>
      </div>`;
    document.getElementById('modal-bg').addEventListener('click', e => {
      if (e.target.id === 'modal-bg') UI.closeModal();
    });
  },

  closeModal() {
    document.getElementById('modal-root').innerHTML = '';
  },

  toast(msg, kind = 'info') {
    const root = document.createElement('div');
    root.style.cssText = `position:fixed;bottom:24px;right:24px;
      background:${kind === 'error' ? '#a83232' : kind === 'success' ? '#1c6b3a' : '#262626'};
      color:#fff;padding:12px 18px;border-radius:8px;
      box-shadow:0 4px 16px rgba(0,0,0,0.2);z-index:200;
      font-size:13px;max-width:400px;`;
    root.textContent = msg;
    document.body.appendChild(root);
    setTimeout(() => root.remove(), 3500);
  },

  async confirm(msg) { return window.confirm(msg); },

  /* Overlay de carga (bloquea clicks durante operaciones async) */
  loading(show) {
    const ID = '_ui-loading-overlay';
    if (show) {
      if (!document.getElementById(ID)) {
        const el = document.createElement('div');
        el.id = ID;
        el.style.cssText = [
          'position:fixed', 'inset:0', 'z-index:9997', 'cursor:wait',
          'background:rgba(0,0,0,0.03)',
        ].join(';');
        document.body.appendChild(el);
      }
    } else {
      const el = document.getElementById(ID);
      if (el) el.remove();
    }
  },

  /* Alias de UI.toast para compatibilidad con modulos que usan UI.message() */
  message(msg, kind) { UI.toast(msg, kind); },

  /* ── Componente de pestanas para vistas hub ──────────────────────────────
     Renderiza una barra de pestanas accesible (tablist) y monta la View
     activa en un panel (lazy: solo se renderiza la pestana activa).
     opts = {
       hub:   'risk-hub',          // segmento base del hash
       label: 'Riesgos y activos', // aria-label del tablist
       tabs: [{
         id:    'assets',          // segmento anidado del hash (#/risk-hub/assets)
         label: 'Activos',
         view:  ViewAssets,        // objeto con render(el) — o bien:
         render: async (el)=>{},   // render custom (tiene prioridad sobre view)
         route: 'assets',          // ruta legacy (para feature flags de modulos)
         visible: () => bool,      // visibilidad opcional (rol)
       }],
     }
  */
  tabs(container, opts) {
    const hub = opts.hub;
    const disabled = (window.RiskHubFlags && window.RiskHubFlags.disabled) || null;
    const tabs = (opts.tabs || []).filter(t =>
      (!t.visible || t.visible()) && !(disabled && t.route && disabled.has(t.route)));
    if (!tabs.length) {
      container.innerHTML = UI.notice('No hay secciones disponibles en este modulo.');
      return;
    }

    const hashPath = location.hash.replace(/^#\/?/, '').split('?')[0];
    const sub = hashPath.split('/')[1] || '';
    let active = tabs.find(t => t.id === sub) || tabs[0];

    container.innerHTML = `
      <div class="hub-tabs" role="tablist" aria-label="${UI.esc(opts.label || hub)}">
        ${tabs.map(t => `
          <button type="button" class="hub-tab" role="tab"
                  id="hubtab-${UI.esc(hub)}-${UI.esc(t.id)}"
                  data-tab="${UI.esc(t.id)}"
                  aria-selected="false" aria-controls="hubpanel-${UI.esc(hub)}"
                  tabindex="-1">${UI.esc(t.label)}</button>`).join('')}
      </div>
      <div class="hub-tab-panel" id="hubpanel-${UI.esc(hub)}" role="tabpanel" tabindex="0"></div>`;

    const panel = container.querySelector('.hub-tab-panel');
    const btns = Array.from(container.querySelectorAll('.hub-tab'));

    async function activate(tab, keepQuery) {
      active = tab;
      btns.forEach(b => {
        const on = b.dataset.tab === tab.id;
        b.classList.toggle('active', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
        b.tabIndex = on ? 0 : -1;
      });
      // Hash anidado para deep-linking, sin disparar hashchange ni recargar
      const query = location.hash.split('?')[1];
      const newHash = '#/' + hub + '/' + tab.id + (keepQuery && query ? '?' + query : '');
      if (location.hash !== newHash) history.replaceState(null, '', newHash);
      panel.innerHTML = '';
      panel.setAttribute('aria-labelledby', 'hubtab-' + hub + '-' + tab.id);
      try {
        if (tab.render) await tab.render(panel);
        else await tab.view.render(panel);
      } catch (e) {
        panel.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
      }
    }

    btns.forEach((b, i) => {
      b.onclick = () => activate(tabs[i], false);
      b.onkeydown = (e) => {
        let target = null;
        if (e.key === 'ArrowRight') target = (i + 1) % btns.length;
        else if (e.key === 'ArrowLeft') target = (i - 1 + btns.length) % btns.length;
        else if (e.key === 'Home') target = 0;
        else if (e.key === 'End') target = btns.length - 1;
        if (target === null) return;
        e.preventDefault();
        btns[target].focus();
        activate(tabs[target], false);
      };
    });

    activate(active, true);
  },

  // Decoradores helpers
  assetTypeLabel(t) {
    return ({
      primary_process: 'Proceso',
      primary_information: 'Información',
      support_hardware: 'Hardware',
      support_software: 'Software',
      support_network: 'Red',
      support_personnel: 'Personal',
      support_site: 'Instalación',
      support_organization: 'Organización',
    })[t] || t;
  },

  threatOriginLabel(o) {
    return ({ D: 'Deliberada', A: 'Accidental', E: 'Ambiental' })[o] || o;
  },

  treatmentLabel(t) {
    return ({
      modification: 'Mitigar',
      retention: 'Aceptar',
      avoidance: 'Evitar',
      sharing: 'Transferir',
    })[t] || (t || '-');
  },

  statusLabel(s) {
    return ({
      identified: 'Identificado',
      assessed: 'Evaluado',
      treated: 'Tratado',
      accepted: 'Aceptado',
      closed: 'Cerrado',
    })[s] || s;
  },

  controlStatusLabel(s) {
    return ({
      planned: 'Planificado',
      implemented: 'Implementado',
      partial: 'Parcial',
      not_implemented: 'No implementado',
    })[s] || s;
  },
};
