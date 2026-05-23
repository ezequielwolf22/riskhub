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
    root.innerHTML = `
      <div class="modal-bg" id="modal-bg">
        <div class="modal">
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
