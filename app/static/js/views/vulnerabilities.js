/* Vista Vulnerabilidades - catálogo ISO 27005 Annex D. */
const ViewVulns = {
  _sortCol: 'code', _sortAsc: true,

  async render(main) {
    const canEdit = Auth.canEdit();
    main.innerHTML = UI.sectionHeader(
      t('vulnerabilities.title'),
      t('vulnerabilities.subtitle'),
      canEdit ? `<button class="btn btn-primary" id="btn-new">+ ${t('vulnerabilities.new')}</button>` : ''
    ) + `
      <div class="toolbar">
        <input type="search" id="v-search" placeholder="${t('vulnerabilities.search_placeholder')}">
        <select id="v-cat">
          <option value="">${t('vulnerabilities.all_categories')}</option>
          <option value="hardware">${t('vulnerabilities.cat_hardware')}</option>
          <option value="software">${t('vulnerabilities.cat_software')}</option>
          <option value="network">${t('vulnerabilities.cat_network')}</option>
          <option value="personnel">${t('vulnerabilities.cat_personnel')}</option>
          <option value="site">${t('vulnerabilities.cat_site')}</option>
          <option value="organization">${t('vulnerabilities.cat_organization')}</option>
        </select>
      </div>
      <div id="v-list"></div>
    `;
    if (canEdit) document.getElementById('btn-new').onclick = () => ViewVulns._edit();
    document.getElementById('v-search').oninput = () => ViewVulns._reload();
    document.getElementById('v-cat').onchange = () => ViewVulns._reload();
    ViewVulns._reload();
  },

  async _reload() {
    const q = document.getElementById('v-search').value;
    const cat = document.getElementById('v-cat').value;
    const list = document.getElementById('v-list');
    list.innerHTML = `<div class="notice">${t('common.loading')}</div>`;
    try {
      const params = {};
      if (q) params.q = q;
      if (cat) params.category = cat;
      const data = await Api.vulns.list(params);
      const canEdit = Auth.canEdit();
      if (!data.length) {
        list.innerHTML = UI.emptyState(t('vulnerabilities.no_results'), t('vulnerabilities.adjust_filters'));
        return;
      }

      // Client-side sort
      const _sv = v => {
        const k = ViewVulns._sortCol;
        if (k === 'code') return v.code || '';
        if (k === 'name') return (v.name || '').toLowerCase();
        if (k === 'category') return (v.category || '').toLowerCase();
        if (k === 'risks') return v.risk_count || 0;
        return '';
      };
      data.sort((a, b) => {
        const va = _sv(a), vb = _sv(b);
        const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
        return ViewVulns._sortAsc ? cmp : -cmp;
      });
      const _th = (col, label, style) => {
        const active = ViewVulns._sortCol === col;
        const arrow = active ? (ViewVulns._sortAsc ? ' ▲' : ' ▼') : '';
        return `<th style="cursor:pointer;user-select:none;${active?'color:var(--brand-purple);':''}${style||''}"
                    data-sort="${col}">${label}${arrow}</th>`;
      };

      list.innerHTML = `<div class="table-wrap"><table class="data">
        <thead><tr>
          ${_th('code',t('vulnerabilities.col_code'))}${_th('name',t('vulnerabilities.col_name'))}${_th('category',t('vulnerabilities.col_category'))}
          <th>${t('vulnerabilities.col_related_threats')}</th>
          ${_th('risks',t('vulnerabilities.col_risks'),'width:70px;text-align:center;')}<th></th>
        </tr></thead>
        <tbody>
          ${data.map(v => {
            const rc = v.risk_count || 0;
            const rcColor = rc === 0 ? 'var(--text-subtle)' : rc >= 5 ? 'var(--risk-high)' : 'var(--brand-purple)';
            return `
            <tr>
              <td>${UI.codePill(v.code)}</td>
              <td><strong>${UI.esc(v.name)}</strong>
                  ${v.description ? `<div style="font-size:11px;color:var(--text-subtle);">${UI.esc(v.description)}</div>` : ''}</td>
              <td>${UI.esc(v.category||'-')}</td>
              <td style="font-size:11px;font-family:var(--font-mono);">${(v.related_threats||[]).join(', ')||'-'}</td>
              <td style="text-align:center;">
                <a href="#/risks?vulnerability_id=${v.id}" title="${t('vulnerabilities.view_risks_title')}"
                   style="font-weight:700;font-family:var(--font-mono);font-size:13px;
                          color:${rcColor};text-decoration:none;">${rc}</a>
              </td>
              <td style="white-space:nowrap;">
                ${v.is_custom
                  ? `<span class="badge badge-muted">Custom</span>
                     ${canEdit ? `
                       <button class="btn btn-sm" style="margin-left:4px;"
                         onclick="ViewVulns._edit(${JSON.stringify(v).replace(/"/g,'&quot;')})">${t('common.edit')}</button>
                       <button class="btn btn-sm btn-danger" style="margin-left:2px;"
                         onclick="ViewVulns._del(${v.id},'${UI.esc(v.name)}')">${t('common.delete')}</button>
                     ` : ''}
                  `
                  : '<span class="badge" style="background:var(--brand-purple-4);color:var(--brand-purple);">ISO</span>'
                }
              </td>
            </tr>`;}).join('')}
        </tbody>
      </table></div>`;
      list.querySelectorAll('th[data-sort]').forEach(th => {
        th.onclick = () => {
          const col = th.dataset.sort;
          if (ViewVulns._sortCol === col) ViewVulns._sortAsc = !ViewVulns._sortAsc;
          else { ViewVulns._sortCol = col; ViewVulns._sortAsc = col !== 'risks'; }
          ViewVulns._reload();
        };
      });
    } catch (e) {
      list.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _edit(v) {
    const isNew = !v;
    UI.modal(isNew ? t('vulnerabilities.new_custom_title') : t('vulnerabilities.edit_custom_title'), `
      <div><label>${t('vulnerabilities.form_code')}</label>
        <input id="f-code" value="${isNew ? '' : UI.esc(v.code)}"></div>
      <div><label>${t('vulnerabilities.form_category')}</label>
        <select id="f-cat">
          <option value="hardware" ${!isNew && v.category==='hardware' ? 'selected':''}>${t('vulnerabilities.cat_hardware')}</option>
          <option value="software" ${!isNew && v.category==='software' ? 'selected':''}>${t('vulnerabilities.cat_software')}</option>
          <option value="network" ${!isNew && v.category==='network' ? 'selected':''}>${t('vulnerabilities.cat_network')}</option>
          <option value="personnel" ${!isNew && v.category==='personnel' ? 'selected':''}>${t('vulnerabilities.cat_personnel')}</option>
          <option value="site" ${!isNew && v.category==='site' ? 'selected':''}>${t('vulnerabilities.cat_site')}</option>
          <option value="organization" ${!isNew && v.category==='organization' ? 'selected':''}>${t('vulnerabilities.cat_organization')}</option>
        </select>
      </div>
      <div class="span2"><label>${t('vulnerabilities.form_name')}</label>
        <input id="f-name" value="${isNew ? '' : UI.esc(v.name)}"></div>
      <div class="span2"><label>${t('vulnerabilities.form_description')}</label>
        <textarea id="f-desc" rows="2">${isNew ? '' : UI.esc(v.description||'')}</textarea></div>
      <div class="span2"><label>${t('vulnerabilities.form_related_threats')}</label>
        <input id="f-rel" placeholder="T.CYB.01, T.UNA.04"
          value="${isNew ? '' : (v.related_threats||[]).join(', ')}"></div>
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
        related_threats: document.getElementById('f-rel').value.split(',')
                           .map(s=>s.trim()).filter(Boolean),
      };
      try {
        if (isNew) {
          await Api.vulns.create(payload);
          UI.toast(t('vulnerabilities.created'), 'success');
        } else {
          await Api.vulns.update(v.id, payload);
          UI.toast(t('vulnerabilities.updated'), 'success');
        }
        UI.closeModal(); ViewVulns._reload();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  },

  async _del(id, name) {
    if (!await UI.confirm(t('vulnerabilities.delete_confirm', {name}))) return;
    try {
      await Api.vulns.del(id);
      UI.toast(t('vulnerabilities.deleted'), 'success');
      ViewVulns._reload();
    } catch (e) { UI.toast(e.message, 'error'); }
  },
};
