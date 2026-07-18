/* Vista Amenazas — catálogos ISO 27005, MAGERIT v3 y personalizadas. */
const ViewThreats = {
  _sortCol: 'code', _sortAsc: true,
  _activeCatalogs: ['iso27005', 'magerit', 'custom'],  // preferencia org (cargada desde API)

  async render(main) {
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      t('threats.title'),
      t('threats.subtitle')
    ) + `
      <div class="toolbar" style="gap:12px;flex-wrap:wrap;align-items:center;">
        <input type="search" id="t-search" placeholder="${t('threats.search_placeholder')}">
        <select id="t-category"><option value="">${t('threats.all_categories')}</option></select>

        <!-- Multi-select de catálogos -->
        <div id="catalog-dropdown" style="position:relative;">
          <button class="btn" id="catalog-btn"
                  style="display:flex;align-items:center;gap:6px;min-width:200px;justify-content:space-between;">
            <span id="catalog-btn-label">${t('threats.all_catalogs')}</span>
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <div id="catalog-menu" style="
              display:none;position:absolute;top:calc(100% + 6px);left:0;
              background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;
              padding:6px 0 10px;min-width:280px;z-index:9999;
              box-shadow:0 8px 24px rgba(0,0,0,.18);">
            <div style="padding:10px 14px 8px;font-size:11px;text-transform:uppercase;
                        color:#64748b;font-weight:700;letter-spacing:.6px;border-bottom:1px solid #f1f5f9;margin-bottom:4px;">
              ${t('threats.catalogs_heading')}
            </div>
            ${[
              ['iso27005', t('threats.catalog_iso'),    '#7C3AED', t('threats.catalog_iso_desc')],
              ['magerit',  t('threats.catalog_magerit'), '#D97706', t('threats.catalog_magerit_desc')],
              ['custom',   t('threats.catalog_custom'),  '#16A34A', t('threats.catalog_custom_desc')],
            ].map(([val, label, color, desc]) => `
              <label style="display:flex;align-items:flex-start;gap:10px;padding:9px 14px;
                            cursor:pointer;background:#fff;transition:background .1s;" class="catalog-opt"
                     onmouseover="this.style.background='#f8fafc'"
                     onmouseout="this.style.background='#fff'">
                <input type="checkbox" class="catalog-check" value="${val}"
                       style="margin-top:3px;width:15px;height:15px;accent-color:${color};cursor:pointer;">
                <div>
                  <div style="font-size:13px;font-weight:600;color:${color};">${label}</div>
                  <div style="font-size:11px;color:#94a3b8;margin-top:1px;">${desc}</div>
                </div>
              </label>
            `).join('')}
            <div style="margin:8px 14px 0;padding:8px 10px;background:#f0fdf4;
                        border:1px solid #bbf7d0;border-radius:6px;font-size:11px;color:#166534;">
              <strong>${t('threats.catalog_effect_label')}</strong> ${t('threats.catalog_effect_body')}
            </div>
            ${canEdit ? `
              <div style="padding:8px 14px 0;">
                <button class="btn btn-ghost" id="btn-magerit-seed"
                        style="font-size:12px;padding:5px 12px;width:100%;text-align:left;">
                  ${t('threats.load_magerit_btn')}
                </button>
              </div>
            ` : ''}
          </div>
        </div>

        ${canEdit ? `<button class="btn btn-primary" id="btn-new">${t('threats.new_btn')}</button>` : ''}
      </div>
      <div id="catalog-info-banner" style="margin-bottom:12px;"></div>
      <div id="t-list"></div>
    `;

    // Cargar preferencia de catálogos desde API
    await ViewThreats._loadActiveCatalogs();

    // Toggle del dropdown
    document.getElementById('catalog-btn').onclick = (e) => {
      e.stopPropagation();
      const menu = document.getElementById('catalog-menu');
      menu.style.display = menu.style.display === 'none' ? '' : 'none';
    };
    document.addEventListener('click', () => {
      const menu = document.getElementById('catalog-menu');
      if (menu) menu.style.display = 'none';
    }, { once: false });
    document.getElementById('catalog-menu').onclick = e => e.stopPropagation();

    // Cambio en checkboxes de catálogo
    document.querySelectorAll('.catalog-check').forEach(cb => {
      cb.onchange = () => ViewThreats._onCatalogChange();
    });

    if (canEdit) {
      document.getElementById('btn-new').onclick = () => ViewThreats._edit();

      const mageritBtn = document.getElementById('btn-magerit-seed');
      if (mageritBtn) mageritBtn.onclick = async () => {
        mageritBtn.disabled = true; mageritBtn.textContent = t('threats.magerit_loading');
        try {
          const r = await Api.magerit.seed();
          const msg = r.created > 0
            ? t('threats.magerit_loaded', {n: r.created})
            : t('threats.magerit_already');
          UI.toast(msg, 'success');
          // Activar magerit automáticamente si no estaba
          if (!ViewThreats._activeCatalogs.includes('magerit')) {
            ViewThreats._activeCatalogs.push('magerit');
            await ViewThreats._saveActiveCatalogs();
          }
          ViewThreats._reload();
        } catch (e) {
          UI.toast('Error: ' + e.message, 'error');
        } finally {
          mageritBtn.disabled = false; mageritBtn.textContent = t('threats.magerit_btn_reset');
        }
      };
    }

    document.getElementById('t-search').oninput = () => ViewThreats._reload();
    document.getElementById('t-category').onchange = () => ViewThreats._reload();
    ViewThreats._reload();
  },

  async _loadActiveCatalogs() {
    try {
      const data = await Api.get('/api/threats/active-catalogs');
      ViewThreats._activeCatalogs = data.active_catalogs || ['iso27005', 'magerit', 'custom'];
    } catch (_) {
      ViewThreats._activeCatalogs = ['iso27005', 'magerit', 'custom'];
    }
    ViewThreats._syncCheckboxes();
    ViewThreats._updateCatalogBtnLabel();
  },

  _syncCheckboxes() {
    document.querySelectorAll('.catalog-check').forEach(cb => {
      cb.checked = ViewThreats._activeCatalogs.includes(cb.value);
    });
  },

  _updateCatalogBtnLabel() {
    const label = document.getElementById('catalog-btn-label');
    if (!label) return;
    const active = ViewThreats._activeCatalogs;
    const _NAMES = {
      iso27005: t('threats.custom_name_iso'),
      magerit:  t('threats.custom_name_magerit'),
      custom:   t('threats.custom_name_custom'),
    };
    if (active.length === 3 || active.length === 0) {
      label.textContent = t('threats.all_catalogs');
    } else {
      label.textContent = active.map(c => _NAMES[c] || c).join(' + ');
    }
    ViewThreats._updateInfoBanner();
  },

  _updateInfoBanner() {
    const banner = document.getElementById('catalog-info-banner');
    if (!banner) return;
    const active = ViewThreats._activeCatalogs;
    const _NAMES = {
      iso27005: t('threats.custom_name_iso'),
      magerit:  t('threats.custom_name_magerit'),
      custom:   t('threats.custom_name_custom'),
    };
    const _COLORS = { iso27005: '#7C3AED', magerit: '#D97706', custom: '#16A34A' };
    const badges = active.map(c =>
      `<span style="display:inline-block;padding:2px 8px;background:${_COLORS[c]}22;
              color:${_COLORS[c]};border:1px solid ${_COLORS[c]}44;border-radius:4px;
              font-size:11px;font-weight:600;">${_NAMES[c]||c}</span>`
    ).join(' ');

    banner.innerHTML = `
      <div style="display:flex;align-items:center;gap:12px;padding:10px 14px;
                  background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
                  font-size:13px;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <span style="color:#475569;font-weight:600;">${t('threats.active_catalogs_label')}</span>
          ${badges}
        </div>
        <div style="margin-left:auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <span style="font-size:12px;color:#64748b;">
            ${t('threats.catalog_info_body')}
          </span>
          <a href="#!/assets" style="
              display:inline-flex;align-items:center;gap:4px;padding:5px 12px;
              background:#7C3AED;color:#fff;border-radius:6px;font-size:12px;
              font-weight:600;text-decoration:none;">
            ${t('threats.goto_assets')}
          </a>
        </div>
      </div>`;
  },

  async _onCatalogChange() {
    const checked = [...document.querySelectorAll('.catalog-check:checked')].map(cb => cb.value);
    if (checked.length === 0) {
      // Al menos uno debe estar activo — revertir
      ViewThreats._syncCheckboxes();
      UI.toast(t('threats.min_one_catalog'), 'warn');
      return;
    }
    ViewThreats._activeCatalogs = checked;
    ViewThreats._updateCatalogBtnLabel();
    await ViewThreats._saveActiveCatalogs();
    ViewThreats._reload();
  },

  async _saveActiveCatalogs() {
    try {
      await Api.put('/api/threats/active-catalogs', { active_catalogs: ViewThreats._activeCatalogs });
    } catch (_) { /* no bloquear */ }
  },

  async _reload() {
    const q = document.getElementById('t-search').value;
    const cat = document.getElementById('t-category').value;
    const list = document.getElementById('t-list');
    list.innerHTML = `<div class="notice">${t('threats.loading')}</div>`;
    try {
      const params = {};
      if (q) params.q = q;
      if (cat) params.category = cat;
      // Filtrar por catálogos activos
      if (ViewThreats._activeCatalogs.length < 3) {
        params.catalog = ViewThreats._activeCatalogs.join(',');
      }

      const data = await Api.threats.list(params);
      const canEdit = Auth.canEdit();

      // Popular filtro de categorías (solo la primera vez)
      const catSelect = document.getElementById('t-category');
      if (catSelect.options.length === 1) {
        const cats = [...new Set(data.map(t => t.category).filter(Boolean))].sort();
        cats.forEach(c => catSelect.add(new Option(c, c)));
      }

      if (!data.length) {
        list.innerHTML = UI.emptyState(t('threats.no_results'), t('threats.no_results_body'));
        return;
      }

      // Client-side sort
      const _sv = th => {
        const k = ViewThreats._sortCol;
        if (k === 'code') return th.code || '';
        if (k === 'name') return (th.name || '').toLowerCase();
        if (k === 'origin') return th.origin || '';
        if (k === 'category') return (th.category || '').toLowerCase();
        if (k === 'catalog') return th.catalog || '';
        if (k === 'risks') return th.risk_count || 0;
        return '';
      };
      data.sort((a, b) => {
        const va = _sv(a), vb = _sv(b);
        const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
        return ViewThreats._sortAsc ? cmp : -cmp;
      });

      const _th = (col, label, style) => {
        const active = ViewThreats._sortCol === col;
        const arrow = active ? (ViewThreats._sortAsc ? ' ▲' : ' ▼') : '';
        return `<th style="cursor:pointer;user-select:none;${active?'color:var(--brand-purple);':''}${style||''}"
                    data-sort="${col}">${label}${arrow}</th>`;
      };

      const _catalogBadge = (th) => {
        if (th.catalog === 'magerit')
          return `<span class="badge" style="background:#FEF0E3;color:#D97706;border:1px solid #FDE68A;">MAGERIT</span>`;
        if (th.catalog === 'custom' || th.is_custom)
          return `<span class="badge" style="background:#DCFCE7;color:#16A34A;border:1px solid #BBF7D0;">Custom</span>`;
        return `<span class="badge" style="background:var(--brand-purple-4);color:var(--brand-purple);">ISO 27005</span>`;
      };

      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          ${_th('code', t('threats.col_code'))}${_th('name', t('threats.col_name'))}
          ${_th('catalog', t('threats.col_catalog'), 'width:90px;')}
          ${_th('origin', t('threats.col_origin'))}${_th('category', t('threats.col_category'))}
          <th>${t('threats.col_affects')}</th><th>${t('threats.col_assets')}</th>
          ${_th('risks', t('threats.col_risks'), 'width:70px;text-align:center;')}<th></th>
        </tr></thead>
        <tbody>
          ${data.map(th => {
            const rc = th.risk_count || 0;
            const rcColor = rc === 0 ? 'var(--text-subtle)' : rc >= 5 ? 'var(--risk-high)' : 'var(--brand-purple)';
            const isEditable = th.catalog === 'custom' || th.is_custom;
            return `
            <tr>
              <td>${UI.codePill(th.code)}</td>
              <td>
                <strong>${UI.esc(th.name)}</strong>
                ${th.description ? `<div style="font-size:11px;color:var(--text-subtle);">${UI.esc(th.description.substring(0,80))}${th.description.length>80?'…':''}</div>` : ''}
              </td>
              <td>${_catalogBadge(th)}</td>
              <td>${UI.threatOriginLabel(th.origin)}</td>
              <td>${UI.esc(th.category||'-')}</td>
              <td>${(th.affects||[]).join(', ')||'-'}</td>
              <td style="font-size:11px;color:var(--text-subtle);">${(th.typical_assets||[]).map(UI.assetTypeLabel).join(', ')||'-'}</td>
              <td style="text-align:center;">
                <a href="#/risks?threat_id=${th.id}" title="${t('threats.view_risks_title')}"
                   style="font-weight:700;font-family:var(--font-mono);font-size:13px;
                          color:${rcColor};text-decoration:none;">${rc}</a>
              </td>
              <td style="white-space:nowrap;">
                ${isEditable && canEdit ? `
                  <button class="btn btn-sm" onclick="ViewThreats._edit(${JSON.stringify(th).replace(/"/g,'&quot;')})">${t('common.edit')}</button>
                  <button class="btn btn-sm btn-danger" style="margin-left:2px;"
                    onclick="ViewThreats._del(${th.id},'${UI.esc(th.name)}')">${t('common.delete')}</button>
                ` : ''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>
      <div style="font-size:12px;color:var(--text-muted);padding:8px 4px;">
        ${ViewThreats._activeCatalogs.length < 3
          ? t('threats.count_filtered', {n: data.length, catalogs: ViewThreats._activeCatalogs.join(', ')})
          : t('threats.count_all', {n: data.length})}
      </div>`;

      list.querySelectorAll('th[data-sort]').forEach(th => {
        th.onclick = () => {
          const col = th.dataset.sort;
          if (ViewThreats._sortCol === col) ViewThreats._sortAsc = !ViewThreats._sortAsc;
          else { ViewThreats._sortCol = col; ViewThreats._sortAsc = col !== 'risks'; }
          ViewThreats._reload();
        };
      });
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _edit(th) {
    const isNew = !th;
    UI.modal(isNew ? t('threats.new_custom_title') : t('threats.edit_custom_title'), `
      <div><label>${t('threats.form_code')}</label>
        <input id="f-code" value="${isNew ? '' : UI.esc(th.code)}"></div>
      <div><label>${t('threats.form_origin')}</label>
        <select id="f-origin">
          <option value="D" ${(!isNew && th.origin==='D')||isNew ? 'selected':''}>${t('threats.origin_deliberate')}</option>
          <option value="A" ${!isNew && th.origin==='A' ? 'selected':''}>${t('threats.origin_accidental')}</option>
          <option value="E" ${!isNew && th.origin==='E' ? 'selected':''}>${t('threats.origin_environmental')}</option>
        </select>
      </div>
      <div class="span2"><label>${t('threats.form_name')}</label>
        <input id="f-name" value="${isNew ? '' : UI.esc(th.name)}"></div>
      <div class="span2"><label>${t('threats.form_description')}</label>
        <textarea id="f-desc" rows="2">${isNew ? '' : UI.esc(th.description||'')}</textarea></div>
      <div><label>${t('threats.form_category')}</label>
        <input id="f-cat" placeholder="Compromise of information"
          value="${isNew ? '' : UI.esc(th.category||'')}"></div>
      <div><label>${t('threats.form_affects')}</label>
        <input id="f-affects" placeholder="C, I, A"
          value="${isNew ? '' : (th.affects||[]).join(', ')}"></div>
    `, {
      actions: `<button class="btn" id="m-cancel">${t('common.cancel')}</button>
                <button class="btn btn-primary" id="m-save">${t('common.save')}</button>`
    });
    document.getElementById('m-cancel').onclick = UI.closeModal;
    document.getElementById('m-save').onclick = async () => {
      const payload = {
        code: document.getElementById('f-code').value || undefined,
        name: document.getElementById('f-name').value,
        description: document.getElementById('f-desc').value,
        category: document.getElementById('f-cat').value,
        origin: document.getElementById('f-origin').value,
        affects: document.getElementById('f-affects').value.split(',').map(s=>s.trim()).filter(Boolean),
        typical_assets: isNew ? [] : (th.typical_assets||[]),
        catalog: 'custom',
      };
      try {
        if (isNew) {
          await Api.threats.create(payload);
          UI.toast(t('threats.created'), 'success');
        } else {
          await Api.threats.update(th.id, payload);
          UI.toast(t('threats.updated'), 'success');
        }
        UI.closeModal(); ViewThreats._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  async _del(id, name) {
    if (!await UI.confirm(t('threats.delete_confirm', {name}))) return;
    try {
      await Api.threats.del(id);
      UI.toast(t('threats.deleted'), 'success');
      ViewThreats._reload();
    } catch (e) { UI.toast(e.message, 'error'); }
  },
};
