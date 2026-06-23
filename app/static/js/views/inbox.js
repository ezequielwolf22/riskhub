/* Bandeja de revision: items pendientes de decision humana generados
   por las automatizaciones (riesgos auto-creados, incidentes, NIS2,
   controles degradados, tareas vencidas, no conformidades). */
const ViewInbox = {
  _CSS: `<style>
    .inbox-list { display: flex; flex-direction: column; gap: 10px; }
    .inbox-item { display: flex; align-items: flex-start; gap: 12px;
      padding: 12px 14px; border: 1px solid var(--border, #e2e2e8);
      border-radius: 10px; background: var(--card-bg, #fff); }
    .inbox-item-body { flex: 1; min-width: 0; }
    .inbox-item-title { font-weight: 600; font-size: 13px; margin: 0 0 2px; }
    .inbox-item-desc { font-size: 12px; color: var(--text-muted, #6b6b76);
      margin: 0; overflow: hidden; display: -webkit-box;
      -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
    .inbox-item-meta { font-size: 11px; color: var(--text-muted, #8a8a94); margin-top: 4px; }
    .inbox-item-actions { display: flex; gap: 6px; flex-shrink: 0; align-items: center; }
    .inbox-sev { display: inline-flex; align-items: center; gap: 4px;
      font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 999px;
      white-space: nowrap; flex-shrink: 0; }
    .inbox-sev svg { flex-shrink: 0; }
    .inbox-sev-critical { background: #fde8e8; color: #9b1c1c; }
    .inbox-sev-high { background: #fdf0e0; color: #9a5200; }
    .inbox-sev-medium { background: #fdf6dd; color: #7a6200; }
    .inbox-sev-info { background: #e7eef9; color: #1d4e89; }
    .inbox-counts { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
    .inbox-empty { text-align: center; padding: 24px 12px;
      color: var(--text-muted, #6b6b76); font-size: 13px; }
    .inbox-loading { padding: 20px; text-align: center;
      color: var(--text-muted, #8a8a94); font-size: 13px; }
    .inbox-embed-head { display: flex; align-items: center; justify-content: space-between;
      gap: 8px; margin-bottom: 10px; }
    .inbox-embed-head h3 { margin: 0; font-size: 14px; }
  </style>`,

  get _SEV_META() {
    return {
      critical: { label: t('inbox.sev_critical'), icon: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>' },
      high: { label: t('inbox.sev_high'), icon: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M12 8v5"/><path d="M12 16h.01"/><circle cx="12" cy="12" r="9"/></svg>' },
      medium: { label: t('inbox.sev_medium'), icon: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M8 12h8"/></svg>' },
      info: { label: t('inbox.sev_info'), icon: '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/></svg>' },
    };
  },

  get _TYPE_LABELS() {
    return {
      risk: t('inbox.type_risk'),
      incident: t('inbox.type_incident'),
      nis2: t('inbox.type_nis2'),
      control: t('inbox.type_control'),
      task: t('inbox.type_task'),
      nonconformity: t('inbox.type_nonconformity'),
    };
  },

  /* ---------- helpers ---------- */

  _sevBadge(sev) {
    const m = this._SEV_META[sev] || this._SEV_META.info;
    return `<span class="inbox-sev inbox-sev-${UI.esc(sev)}">${m.icon}${UI.esc(m.label)}</span>`;
  },

  _timeAgo(iso) {
    if (!iso) return '';
    const then = new Date(iso).getTime();
    if (isNaN(then)) return '';
    const mins = Math.floor((Date.now() - then) / 60000);
    if (mins < 1) return t('inbox.time_moment');
    if (mins < 60) return t('inbox.time_mins', {n: mins});
    const hours = Math.floor(mins / 60);
    if (hours < 24) return t('inbox.time_hours', {n: hours});
    const days = Math.floor(hours / 24);
    if (days < 30) return t('inbox.time_days', {n: days});
    const months = Math.floor(days / 30);
    return months > 1 ? t('inbox.time_months_plural', {n: months}) : t('inbox.time_months', {n: months});
  },

  _itemHtml(item, canEdit) {
    const typeLabel = this._TYPE_LABELS[item.type] || item.type;
    const dismissBtn = canEdit
      ? `<button class="btn btn-ghost" data-inbox-dismiss="${UI.esc(item.id)}" title="${t('inbox.dismiss_title')}">${t('inbox.dismiss')}</button>`
      : '';
    return `<div class="inbox-item" data-inbox-item="${UI.esc(item.id)}">
      ${this._sevBadge(item.severity)}
      <div class="inbox-item-body">
        <p class="inbox-item-title">${UI.esc(item.title)}</p>
        <p class="inbox-item-desc">${UI.esc(item.description)}</p>
        <div class="inbox-item-meta">${UI.esc(typeLabel)} &middot; ${UI.esc(this._timeAgo(item.created_at))}</div>
      </div>
      <div class="inbox-item-actions">
        <button class="btn btn-primary" data-inbox-review="${UI.esc(item.link)}">${t('inbox.review')}</button>
        ${dismissBtn}
      </div>
    </div>`;
  },

  _countsHtml(counts) {
    const order = ['critical', 'high', 'medium', 'info'];
    return `<div class="inbox-counts">${order
      .filter(s => (counts[s] || 0) > 0)
      .map(s => `<span class="inbox-sev inbox-sev-${s}">${this._SEV_META[s].icon}${UI.esc(this._SEV_META[s].label)}: ${counts[s]}</span>`)
      .join('')}</div>`;
  },

  _bindActions(container, reloadFn) {
    container.querySelectorAll('[data-inbox-review]').forEach(btn => {
      btn.onclick = () => {
        const link = btn.getAttribute('data-inbox-review') || '';
        // Solo navegar a rutas hash internas para prevenir open-redirect
        if (link.startsWith('#/')) window.location.hash = link.slice(1);
      };
    });
    container.querySelectorAll('[data-inbox-dismiss]').forEach(btn => {
      btn.onclick = async () => {
        const key = btn.getAttribute('data-inbox-dismiss');
        const ok = await UI.confirm(t('inbox.dismiss_confirm'));
        if (!ok) return;
        btn.disabled = true;
        try {
          await Api.post(`/api/inbox/${encodeURIComponent(key)}/dismiss`, {});
          UI.toast(t('inbox.dismissed'), 'success');
          reloadFn();
        } catch (e) {
          btn.disabled = false;
          UI.toast(e.message || t('inbox.dismiss_error'), 'error');
        }
      };
    });
  },

  async _fetch() {
    return Api.get('/api/inbox');
  },

  /* ---------- vista completa (#/inbox) ---------- */

  async render(main) {
    main.innerHTML = this._CSS + UI.sectionHeader(
      t('inbox.title'),
      t('inbox.subtitle')
    ) + `<div class="card" id="inbox-full"><div class="inbox-loading">${t('inbox.loading')}</div></div>`;
    await this._renderInto(document.getElementById('inbox-full'), null);
  },

  async _renderInto(container, limit) {
    if (!container) return;
    let data;
    try {
      data = await this._fetch();
    } catch (e) {
      container.innerHTML = `<div class="inbox-empty">${t('inbox.cannot_load')} ${UI.esc(e.message || '')}</div>`;
      return;
    }
    const canEdit = typeof Auth !== 'undefined' && Auth.canEdit();
    let items = data.items || [];
    const total = items.length;
    if (limit) items = items.slice(0, limit);

    if (!total) {
      container.innerHTML = `<div class="inbox-empty"><strong>${t('inbox.all_done_title')}</strong><br>${t('inbox.no_pending')}</div>`;
      return;
    }
    const more = limit && total > limit
      ? `<div class="inbox-item-meta" style="margin-top:8px;text-align:right;">
           <a href="#/inbox">${t('inbox.view_more', {n: total})}</a></div>`
      : '';
    container.innerHTML = this._countsHtml(data.counts || {}) +
      `<div class="inbox-list">${items.map(i => this._itemHtml(i, canEdit)).join('')}</div>` + more;
    this._bindActions(container, () => this._renderInto(container, limit));
  },

  /* ---------- modo embebido (dashboard) ---------- */

  async renderEmbedded(containerEl, opts) {
    if (!containerEl) return;
    const limit = (opts && opts.limit) || 5;
    containerEl.innerHTML = this._CSS + `<div class="card">
      <div class="inbox-embed-head">
        <h3>${t('inbox.pending_heading')}</h3>
        <a href="#/inbox" style="font-size:12px;">${t('inbox.view_all')}</a>
      </div>
      <div id="inbox-embed-body"><div class="inbox-loading">${t('inbox.loading_short')}</div></div>
    </div>`;
    await this._renderInto(containerEl.querySelector('#inbox-embed-body'), limit);
  },

  /* Monta la tarjeta embebida si el dashboard expone el slot. No-op si no existe. */
  mountIfSlot() {
    const slot = document.getElementById('home-inbox-slot');
    if (!slot) return;
    this.renderEmbedded(slot, { limit: 5 });
  },
};
