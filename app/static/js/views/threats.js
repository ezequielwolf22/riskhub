/* Vista Amenazas — catalogos ISO 27005, MAGERIT v3 y personalizadas. */
const ViewThreats = {
  _sortCol: 'code', _sortAsc: true,
  _activeCatalogs: ['iso27005', 'magerit', 'custom'],  // preferencia org (cargada desde API)

  async render(main) {
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      'Catalogo de amenazas',
      'ISO 27005 Annex C + MAGERIT v3 + personalizadas'
    ) + `
      <div class="toolbar" style="gap:12px;flex-wrap:wrap;align-items:center;">
        <input type="search" id="t-search" placeholder="Buscar codigo, nombre...">
        <select id="t-category"><option value="">Todas las categorias</option></select>

        <!-- Multi-select de catalogos -->
        <div id="catalog-dropdown" style="position:relative;">
          <button class="btn" id="catalog-btn"
                  style="display:flex;align-items:center;gap:6px;min-width:200px;justify-content:space-between;">
            <span id="catalog-btn-label">Todos los catalogos</span>
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <div id="catalog-menu" style="
              display:none;position:absolute;top:calc(100% + 6px);left:0;
              background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;
              padding:6px 0 10px;min-width:280px;z-index:9999;
              box-shadow:0 8px 24px rgba(0,0,0,.18);">
            <div style="padding:10px 14px 8px;font-size:11px;text-transform:uppercase;
                        color:#64748b;font-weight:700;letter-spacing:.6px;border-bottom:1px solid #f1f5f9;margin-bottom:4px;">
              Catalogos de amenazas activos
            </div>
            ${[
              ['iso27005', 'ISO/IEC 27005:2018', '#7C3AED', 'Catalogo estandar internacional (49 amenazas)'],
              ['magerit',  'MAGERIT v3',          '#D97706', 'Metodologia espanola ENS/CCN (51 amenazas)'],
              ['custom',   'Amenazas personalizadas', '#16A34A', 'Creadas manualmente por tu equipo'],
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
              <strong>Efecto:</strong> La seleccion determina que amenazas usa el analisis IA de riesgos
              en Activos. Cambia los catalogos y vuelve a lanzar el analisis de activos.
            </div>
            ${canEdit ? `
              <div style="padding:8px 14px 0;">
                <button class="btn btn-ghost" id="btn-magerit-seed"
                        style="font-size:12px;padding:5px 12px;width:100%;text-align:left;">
                  + Cargar catalogo MAGERIT v3 (si no esta cargado)
                </button>
              </div>
            ` : ''}
          </div>
        </div>

        ${canEdit ? `<button class="btn btn-primary" id="btn-new">+ Nueva amenaza</button>` : ''}
      </div>
      <div id="catalog-info-banner" style="margin-bottom:12px;"></div>
      <div id="t-list"></div>
    `;

    // Cargar preferencia de catalogos desde API
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

    // Cambio en checkboxes de catalogo
    document.querySelectorAll('.catalog-check').forEach(cb => {
      cb.onchange = () => ViewThreats._onCatalogChange();
    });

    if (canEdit) {
      document.getElementById('btn-new').onclick = () => ViewThreats._edit();

      const mageritBtn = document.getElementById('btn-magerit-seed');
      if (mageritBtn) mageritBtn.onclick = async () => {
        mageritBtn.disabled = true; mageritBtn.textContent = 'Cargando...';
        try {
          const r = await Api.magerit.seed();
          const msg = r.created > 0
            ? `${r.created} amenazas MAGERIT v3 cargadas`
            : 'El catalogo MAGERIT ya estaba cargado';
          UI.toast(msg, 'success');
          // Activar magerit automaticamente si no estaba
          if (!ViewThreats._activeCatalogs.includes('magerit')) {
            ViewThreats._activeCatalogs.push('magerit');
            await ViewThreats._saveActiveCatalogs();
          }
          ViewThreats._reload();
        } catch (e) {
          UI.toast('Error: ' + e.message, 'error');
        } finally {
          mageritBtn.disabled = false; mageritBtn.textContent = '+ Cargar catalogo MAGERIT v3';
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
    const _NAMES = { iso27005: 'ISO 27005', magerit: 'MAGERIT v3', custom: 'Personalizadas' };
    if (active.length === 3 || active.length === 0) {
      label.textContent = 'Todos los catalogos';
    } else {
      label.textContent = active.map(c => _NAMES[c] || c).join(' + ');
    }
    ViewThreats._updateInfoBanner();
  },

  _updateInfoBanner() {
    const banner = document.getElementById('catalog-info-banner');
    if (!banner) return;
    const active = ViewThreats._activeCatalogs;
    const _NAMES = { iso27005: 'ISO 27005', magerit: 'MAGERIT v3', custom: 'Personalizadas' };
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
          <span style="color:#475569;font-weight:600;">Catalogos activos:</span>
          ${badges}
        </div>
        <div style="margin-left:auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <span style="font-size:12px;color:#64748b;">
            El analisis IA de riesgos en Activos usara solo estas amenazas.
          </span>
          <a href="#!/assets" style="
              display:inline-flex;align-items:center;gap:4px;padding:5px 12px;
              background:#7C3AED;color:#fff;border-radius:6px;font-size:12px;
              font-weight:600;text-decoration:none;">
            → Ir a Activos y relanzar analisis
          </a>
        </div>
      </div>`;
  },

  async _onCatalogChange() {
    const checked = [...document.querySelectorAll('.catalog-check:checked')].map(cb => cb.value);
    if (checked.length === 0) {
      // Al menos uno debe estar activo — revertir
      ViewThreats._syncCheckboxes();
      UI.toast('Debes tener al menos un catalogo activo', 'warn');
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
    list.innerHTML = '<div class="notice">Cargando...</div>';
    try {
      const params = {};
      if (q) params.q = q;
      if (cat) params.category = cat;
      // Filtrar por catalogos activos
      if (ViewThreats._activeCatalogs.length < 3) {
        params.catalog = ViewThreats._activeCatalogs.join(',');
      }

      const data = await Api.threats.list(params);
      const canEdit = Auth.canEdit();

      // Popular filtro de categorias (solo la primera vez)
      const catSelect = document.getElementById('t-category');
      if (catSelect.options.length === 1) {
        const cats = [...new Set(data.map(t => t.category).filter(Boolean))].sort();
        cats.forEach(c => catSelect.add(new Option(c, c)));
      }

      if (!data.length) {
        list.innerHTML = UI.emptyState('Sin amenazas', 'No se encontraron resultados para los catalogos seleccionados.');
        return;
      }

      // Client-side sort
      const _sv = t => {
        const k = ViewThreats._sortCol;
        if (k === 'code') return t.code || '';
        if (k === 'name') return (t.name || '').toLowerCase();
        if (k === 'origin') return t.origin || '';
        if (k === 'category') return (t.category || '').toLowerCase();
        if (k === 'catalog') return t.catalog || '';
        if (k === 'risks') return t.risk_count || 0;
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

      const _catalogBadge = (t) => {
        if (t.catalog === 'magerit')
          return `<span class="badge" style="background:#FEF0E3;color:#D97706;border:1px solid #FDE68A;">MAGERIT</span>`;
        if (t.catalog === 'custom' || t.is_custom)
          return `<span class="badge" style="background:#DCFCE7;color:#16A34A;border:1px solid #BBF7D0;">Custom</span>`;
        return `<span class="badge" style="background:var(--brand-purple-4);color:var(--brand-purple);">ISO 27005</span>`;
      };

      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          ${_th('code','Codigo')}${_th('name','Nombre')}
          ${_th('catalog','Catalogo','width:90px;')}
          ${_th('origin','Origen')}${_th('category','Categoria')}
          <th>Afecta</th><th>Aplica a</th>
          ${_th('risks','Riesgos','width:70px;text-align:center;')}<th></th>
        </tr></thead>
        <tbody>
          ${data.map(t => {
            const rc = t.risk_count || 0;
            const rcColor = rc === 0 ? 'var(--text-subtle)' : rc >= 5 ? 'var(--risk-high)' : 'var(--brand-purple)';
            const isEditable = t.catalog === 'custom' || t.is_custom;
            return `
            <tr>
              <td>${UI.codePill(t.code)}</td>
              <td>
                <strong>${UI.esc(t.name)}</strong>
                ${t.description ? `<div style="font-size:11px;color:var(--text-subtle);">${UI.esc(t.description.substring(0,80))}${t.description.length>80?'…':''}</div>` : ''}
              </td>
              <td>${_catalogBadge(t)}</td>
              <td>${UI.threatOriginLabel(t.origin)}</td>
              <td>${UI.esc(t.category||'-')}</td>
              <td>${(t.affects||[]).join(', ')||'-'}</td>
              <td style="font-size:11px;color:var(--text-subtle);">${(t.typical_assets||[]).map(UI.assetTypeLabel).join(', ')||'-'}</td>
              <td style="text-align:center;">
                <a href="#/risks?threat_id=${t.id}" title="Ver riesgos de esta amenaza"
                   style="font-weight:700;font-family:var(--font-mono);font-size:13px;
                          color:${rcColor};text-decoration:none;">${rc}</a>
              </td>
              <td style="white-space:nowrap;">
                ${isEditable && canEdit ? `
                  <button class="btn btn-sm" onclick="ViewThreats._edit(${JSON.stringify(t).replace(/"/g,'&quot;')})">Editar</button>
                  <button class="btn btn-sm btn-danger" style="margin-left:2px;"
                    onclick="ViewThreats._del(${t.id},'${UI.esc(t.name)}')">Eliminar</button>
                ` : ''}
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table></div>
      <div style="font-size:12px;color:var(--text-muted);padding:8px 4px;">
        ${data.length} amenazas
        ${ViewThreats._activeCatalogs.length < 3 ? `(filtrando: ${ViewThreats._activeCatalogs.join(', ')})` : '(todos los catalogos)'}
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

  _edit(t) {
    const isNew = !t;
    UI.modal(isNew ? 'Nueva amenaza personalizada' : 'Editar amenaza personalizada', `
      <div><label>Codigo (vacio para auto)</label>
        <input id="f-code" value="${isNew ? '' : UI.esc(t.code)}"></div>
      <div><label>Origen *</label>
        <select id="f-origin">
          <option value="D" ${(!isNew && t.origin==='D')||isNew ? 'selected':''}>Deliberada</option>
          <option value="A" ${!isNew && t.origin==='A' ? 'selected':''}>Accidental</option>
          <option value="E" ${!isNew && t.origin==='E' ? 'selected':''}>Ambiental</option>
        </select>
      </div>
      <div class="span2"><label>Nombre *</label>
        <input id="f-name" value="${isNew ? '' : UI.esc(t.name)}"></div>
      <div class="span2"><label>Descripcion</label>
        <textarea id="f-desc" rows="2">${isNew ? '' : UI.esc(t.description||'')}</textarea></div>
      <div><label>Categoria</label>
        <input id="f-cat" placeholder="Compromise of information"
          value="${isNew ? '' : UI.esc(t.category||'')}"></div>
      <div><label>Afecta a (separado por coma)</label>
        <input id="f-affects" placeholder="C, I, A"
          value="${isNew ? '' : (t.affects||[]).join(', ')}"></div>
    `, {
      actions: `<button class="btn" id="m-cancel">Cancelar</button>
                <button class="btn btn-primary" id="m-save">Guardar</button>`
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
        typical_assets: isNew ? [] : (t.typical_assets||[]),
        catalog: 'custom',
      };
      try {
        if (isNew) {
          await Api.threats.create(payload);
          UI.toast('Amenaza creada', 'success');
        } else {
          await Api.threats.update(t.id, payload);
          UI.toast('Amenaza actualizada', 'success');
        }
        UI.closeModal(); ViewThreats._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  async _del(id, name) {
    if (!confirm(`Eliminar la amenaza "${name}"?`)) return;
    try {
      await Api.threats.del(id);
      UI.toast('Amenaza eliminada', 'success');
      ViewThreats._reload();
    } catch (e) { UI.toast(e.message, 'error'); }
  },
};
