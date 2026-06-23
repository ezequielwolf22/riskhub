/* Vista Awareness — Generador de infografias de seguridad por IA. */
const ViewAwareness = (() => {

  function _getTemplates() {
    return {
      risk_alert:     { label: t('awareness.tpl_risk_alert'),     icon: '🚨', color: '#C0392B' },
      best_practices: { label: t('awareness.tpl_best_practices'), icon: '✅', color: '#59008D' },
      policy:         { label: t('awareness.tpl_policy'),         icon: '📜', color: '#1565C0' },
      threat:         { label: t('awareness.tpl_threat'),         icon: '⚠️', color: '#212121' },
      phishing:       { label: t('awareness.tpl_phishing'),       icon: '🎣', color: '#D65200' },
    };
  }

  function _getUrgency() {
    return {
      critical: { label: t('awareness.urgency_critical'), color: '#C0392B' },
      high:     { label: t('awareness.urgency_high'),     color: '#D65200' },
      medium:   { label: t('awareness.urgency_medium'),   color: '#F39C12' },
      low:      { label: t('awareness.urgency_low'),      color: '#27AE60' },
    };
  }

  let _tab = 'generator';
  let _draft = null;
  let _editItem = null;
  let _items = [];
  let _branding = null;
  let _logoDataUrl = null;

  // ================================================================
  // Entry point
  // ================================================================

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Awareness</h1>
          <p class="page-sub">${t('awareness.subtitle')}</p>
        </div>
      </div>
      <div class="tabs" id="aw-tabs">
        <button class="tab active" data-tab="generator">${t('awareness.tab_generator')}</button>
        <button class="tab" data-tab="editor">${t('awareness.tab_editor')}</button>
        <button class="tab" data-tab="library">${t('awareness.tab_library')}</button>
        <button class="tab" data-tab="branding">${t('awareness.tab_branding')}</button>
      </div>
      <div id="aw-body" style="margin-top:16px;"></div>
    `;
    el.querySelectorAll('.tab').forEach(btn => {
      btn.onclick = () => _switchTab(btn.dataset.tab);
    });
    await _loadBranding();
    await _renderTab();
  }

  function _switchTab(tab) {
    _tab = tab;
    document.querySelectorAll('#aw-tabs .tab').forEach(btn =>
      btn.classList.toggle('active', btn.dataset.tab === tab));
    _renderTab();
  }

  async function _renderTab() {
    const body = document.getElementById('aw-body');
    if (!body) return;
    body.innerHTML = `<div class="loading">${t('awareness.loading')}</div>`;
    try {
      if (_tab === 'generator') await _renderGenerator(body);
      else if (_tab === 'editor')   await _renderEditor(body);
      else if (_tab === 'library')  await _renderLibrary(body);
      else if (_tab === 'branding') await _renderBrandingTab(body);
    } catch (e) {
      body.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  // ================================================================
  // Tab: Generador (chat IA)
  // ================================================================

  async function _renderGenerator(wrap) {
    const TEMPLATES = _getTemplates();
    wrap.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">
        <div>
          <div class="card" style="display:flex;flex-direction:column;gap:14px;">
            <h3 style="margin:0;font-size:14px;color:var(--brand-purple);">${t('awareness.gen_describe_title')}</h3>
            <div>
              <label>${t('awareness.gen_template_label')}</label>
              <select id="aw-tpl-select">
                <option value="">${t('awareness.gen_template_ai')}</option>
                ${Object.entries(TEMPLATES).map(([k,v]) =>
                  `<option value="${k}">${v.icon} ${v.label}</option>`).join('')}
              </select>
            </div>
            <div>
              <label>${t('awareness.gen_desc_label')}</label>
              <textarea id="aw-prompt" rows="5" placeholder="${t('awareness.gen_desc_placeholder')}"
                style="width:100%;resize:vertical;"></textarea>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
              <button class="btn" onclick="_awQuickPrompt('phishing')">🎣 ${t('awareness.gen_btn_phishing')}</button>
              <button class="btn" onclick="_awQuickPrompt('password')">🔑 ${t('awareness.gen_btn_password')}</button>
              <button class="btn" onclick="_awQuickPrompt('remote')">🏠 ${t('awareness.gen_btn_remote')}</button>
              <button class="btn" onclick="_awQuickPrompt('usb')">💾 ${t('awareness.gen_btn_usb')}</button>
              <button class="btn" onclick="_awQuickPrompt('social')">📱 ${t('awareness.gen_btn_social')}</button>
            </div>
            <button class="btn btn-primary" id="aw-gen-btn" onclick="_awGenerate()">
              ${t('awareness.gen_btn_generate')}
            </button>
          </div>
          <div id="aw-gen-status" style="margin-top:12px;"></div>
        </div>
        <div>
          <div id="aw-preview-wrap" style="min-height:320px;">
            <div class="card" style="background:var(--bg-2);text-align:center;padding:48px 24px;color:var(--text-muted);">
              <div style="font-size:48px;margin-bottom:12px;">🎨</div>
              <p style="margin:0;">${t('awareness.gen_preview_placeholder')}</p>
              <p style="font-size:12px;margin-top:8px;">${t('awareness.gen_preview_hint')}</p>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  window._awQuickPrompt = function(type) {
    const prompts = {
      phishing: 'Infografia de concienciacion sobre phishing y correos fraudulentos para todos los empleados. Incluir indicadores de alerta y pasos a seguir al recibir un email sospechoso.',
      password: 'Infografia sobre gestion segura de contrasenas: uso de gestores, contrasenas robustas, autenticacion de doble factor y por que no reutilizar contrasenas.',
      remote: 'Infografia de buenas practicas de seguridad para el teletrabajo: conexion VPN, bloqueo de pantalla, redes wifi seguras y uso de dispositivos corporativos.',
      usb: 'Alerta de riesgo sobre el peligro de usar dispositivos USB desconocidos. Incluir casos reales y politica de uso aceptable de dispositivos extraibles.',
      social: 'Buenas practicas de seguridad en redes sociales para empleados: que informacion no compartir, configuracion de privacidad y riesgo de ingenieria social.',
    };
    const el = document.getElementById('aw-prompt');
    if (el) el.value = prompts[type] || '';
  };

  window._awGenerate = async function() {
    const promptEl = document.getElementById('aw-prompt');
    const tplEl = document.getElementById('aw-tpl-select');
    const btn = document.getElementById('aw-gen-btn');
    const status = document.getElementById('aw-gen-status');

    const promptVal = (promptEl?.value || '').trim();
    if (!promptVal) { UI.toast(t('awareness.gen_prompt_required'), 'error'); return; }

    btn.disabled = true;
    btn.textContent = t('awareness.gen_generating');
    if (status) status.innerHTML = `<div class="notice">${t('awareness.gen_status_wait')}</div>`;

    try {
      const res = await Api.awareness.generate({
        prompt: promptVal,
        template: tplEl?.value || null,
      });
      _draft = res.content;
      _renderPreview(document.getElementById('aw-preview-wrap'), _draft);
      if (status) status.innerHTML = `
        <div class="notice" style="background:var(--risk-low-bg,#e8f5e9);border-color:var(--risk-low,#27ae60);">
          ${t('awareness.gen_status_ok')}
          <button class="btn btn-primary" style="margin-left:12px;" onclick="ViewAwareness._goEditDraft()">
            ${t('awareness.gen_btn_edit_save')}
          </button>
        </div>`;
    } catch (e) {
      if (status) status.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = t('awareness.gen_btn_generate');
    }
  };

  // ================================================================
  // Preview renderer (HTML)
  // ================================================================

  function _renderPreview(wrap, content, compact = false) {
    if (!content) {
      wrap.innerHTML = `<div class="card" style="padding:32px;text-align:center;color:var(--text-muted);">${t('awareness.preview_no_content')}</div>`;
      return;
    }
    const TEMPLATES = _getTemplates();
    const URGENCY = _getUrgency();
    const tpl = content.template || 'best_practices';
    const tinfo = TEMPLATES[tpl] || TEMPLATES.best_practices;
    const urg = URGENCY[content.urgency] || URGENCY.medium;
    const fs = compact ? '11px' : '13px';
    const titleFs = compact ? '15px' : '18px';

    const keyPoints = (content.key_points || []).slice(0, 5);
    const doItems = (content.do_items || []).slice(0, 4);
    const dontItems = (content.dont_items || []).slice(0, 3);
    const stat = content.statistic;
    const hashtags = (content.hashtags || []).slice(0, 4).join(' ');

    wrap.innerHTML = `
      <div class="aw-card-preview" style="
        border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.15);
        font-size:${fs};background:var(--bg-1);
      ">
        <div style="background:${tinfo.color};padding:${compact?'12px 16px':'16px 20px'};
                    display:flex;justify-content:space-between;align-items:flex-start;">
          <div style="flex:1;">
            <div style="color:rgba(255,255,255,.8);font-size:10px;font-weight:700;
                        letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;">
              ${tinfo.icon} ${tinfo.label}
            </div>
            <div style="color:#fff;font-size:${titleFs};font-weight:700;line-height:1.2;">
              ${UI.esc(content.title || t('awareness.preview_no_title'))}
            </div>
            ${content.subtitle ? `<div style="color:rgba(255,255,255,.8);font-size:11px;margin-top:4px;">${UI.esc(content.subtitle)}</div>` : ''}
          </div>
          <div style="background:${urg.color};color:#fff;font-size:10px;font-weight:700;
                      padding:4px 10px;border-radius:12px;white-space:nowrap;margin-left:12px;">
            ${urg.label}
          </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0;">
          <div style="padding:${compact?'12px 16px':'16px 20px'};border-right:1px solid var(--border);">
            ${content.main_message ? `
              <div style="font-size:${compact?'12px':'14px'};font-weight:600;color:${tinfo.color};
                          margin-bottom:12px;line-height:1.4;">
                ${UI.esc(content.main_message)}
              </div>` : ''}
            ${keyPoints.length ? `
              <div style="font-size:10px;font-weight:700;color:var(--text-muted);
                          text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">
                ${t('awareness.preview_key_points')}
              </div>
              <ul style="margin:0;padding-left:16px;">
                ${keyPoints.map(p => `
                  <li style="margin-bottom:4px;color:var(--text-1);">${UI.esc(p)}</li>`).join('')}
              </ul>` : ''}
            ${stat ? `
              <div style="margin-top:12px;background:${tinfo.color};color:#fff;
                          border-radius:8px;padding:10px 14px;display:inline-block;">
                <div style="font-size:${compact?'22px':'28px'};font-weight:700;line-height:1;">
                  ${UI.esc(stat.value)}
                </div>
                <div style="font-size:10px;opacity:.85;margin-top:2px;">${UI.esc(stat.label||'')}</div>
              </div>` : ''}
          </div>

          <div style="padding:${compact?'12px 16px':'16px 20px'};">
            ${doItems.length ? `
              <div style="font-size:10px;font-weight:700;color:#27AE60;
                          text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">
                ${t('awareness.preview_do_header')} ✓
              </div>
              <ul style="margin:0 0 12px;padding-left:16px;">
                ${doItems.map(i => `
                  <li style="margin-bottom:4px;color:var(--text-1);">${UI.esc(i)}</li>`).join('')}
              </ul>` : ''}
            ${dontItems.length ? `
              <div style="font-size:10px;font-weight:700;color:#C0392B;
                          text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">
                ${t('awareness.preview_dont_header')} ✗
              </div>
              <ul style="margin:0;padding-left:16px;">
                ${dontItems.map(i => `
                  <li style="margin-bottom:4px;color:var(--text-1);">${UI.esc(i)}</li>`).join('')}
              </ul>` : ''}
            ${content.call_to_action ? `
              <div style="margin-top:12px;background:var(--bg-2);border-radius:8px;
                          padding:10px 12px;border-left:3px solid ${tinfo.color};">
                <div style="font-size:10px;font-weight:700;color:${tinfo.color};
                            text-transform:uppercase;margin-bottom:4px;">${t('awareness.preview_action_header')}</div>
                <div style="font-size:${fs};color:var(--text-1);">${UI.esc(content.call_to_action)}</div>
              </div>` : ''}
          </div>
        </div>

        <div style="background:${tinfo.color};padding:8px 20px;display:flex;
                    justify-content:space-between;align-items:center;">
          <div style="color:rgba(255,255,255,.9);font-size:10px;">
            ${content.contact ? UI.esc(content.contact) : ''}
          </div>
          <div style="color:rgba(255,255,255,.7);font-size:10px;">${UI.esc(hashtags)}</div>
        </div>
      </div>
    `;
  }

  // ================================================================
  // Tab: Editor
  // ================================================================

  async function _renderEditor(wrap) {
    const src = _editItem ? _editItem.content : (_draft || null);
    const TEMPLATES = _getTemplates();
    const URGENCY = _getUrgency();
    if (!src) {
      wrap.innerHTML = `
        <div class="card" style="text-align:center;padding:48px;color:var(--text-muted);">
          <div style="font-size:48px;margin-bottom:12px;">✏️</div>
          <p>${t('awareness.ed_no_item_title')}</p>
          <p style="font-size:12px;">${t('awareness.ed_no_item_desc')}</p>
          <button class="btn btn-primary" onclick="ViewAwareness._switchTab('generator')">${t('awareness.ed_btn_go_gen')}</button>
        </div>`;
      return;
    }

    const content = JSON.parse(JSON.stringify(src)); // deep copy

    wrap.innerHTML = `
      <div style="display:grid;grid-template-columns:340px 1fr;gap:20px;align-items:start;">
        <div class="card" style="display:flex;flex-direction:column;gap:12px;overflow-y:auto;max-height:80vh;">
          <h3 style="margin:0;font-size:14px;color:var(--brand-purple);">${t('awareness.ed_form_title')}</h3>

          <div>
            <label>${t('awareness.ed_tpl_label')}</label>
            <select id="ed-tpl">
              ${Object.entries(TEMPLATES).map(([k,v]) =>
                `<option value="${k}" ${content.template===k?'selected':''}>${v.icon} ${v.label}</option>`).join('')}
            </select>
          </div>
          <div>
            <label>${t('awareness.ed_urgency_label')}</label>
            <select id="ed-urgency">
              ${Object.entries(URGENCY).map(([k,v]) =>
                `<option value="${k}" ${content.urgency===k?'selected':''}>${v.label}</option>`).join('')}
            </select>
          </div>
          <div><label>${t('awareness.ed_title_label')}</label>
            <input id="ed-title" value="${UI.esc(content.title||'')}" maxlength="55"></div>
          <div><label>${t('awareness.ed_subtitle_label')}</label>
            <input id="ed-subtitle" value="${UI.esc(content.subtitle||'')}" maxlength="100"></div>
          <div><label>${t('awareness.ed_main_label')}</label>
            <textarea id="ed-main" rows="3" maxlength="180">${UI.esc(content.main_message||'')}</textarea></div>

          <div>
            <label>${t('awareness.ed_keypoints_label')}</label>
            <textarea id="ed-keypoints" rows="4">${(content.key_points||[]).map(UI.esc).join('\n')}</textarea>
          </div>
          <div>
            <label>${t('awareness.ed_do_label')}</label>
            <textarea id="ed-do" rows="3">${(content.do_items||[]).map(UI.esc).join('\n')}</textarea>
          </div>
          <div>
            <label>${t('awareness.ed_dont_label')}</label>
            <textarea id="ed-dont" rows="3">${(content.dont_items||[]).map(UI.esc).join('\n')}</textarea>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            <div><label>${t('awareness.ed_stat_label')}</label>
              <input id="ed-stat-val" placeholder="85%" value="${UI.esc(content.statistic?.value||'')}"></div>
            <div><label>${t('awareness.ed_stat_desc_label')}</label>
              <input id="ed-stat-lbl" placeholder="de ataques..." value="${UI.esc(content.statistic?.label||'')}"></div>
          </div>
          <div><label>${t('awareness.ed_cta_label')}</label>
            <textarea id="ed-cta" rows="2" maxlength="120">${UI.esc(content.call_to_action||'')}</textarea></div>
          <div><label>${t('awareness.ed_contact_label')}</label>
            <input id="ed-contact" value="${UI.esc(content.contact||'')}"></div>
          <div><label>${t('awareness.ed_hashtags_label')}</label>
            <input id="ed-hashtags" value="${UI.esc((content.hashtags||[]).join(' '))}"></div>

          <button class="btn" id="ed-preview-btn" onclick="_awUpdatePreview()">
            ${t('awareness.ed_btn_preview')}
          </button>

          <hr style="border:none;border-top:1px solid var(--border);margin:4px 0;">
          <div>
            <label>${t('awareness.ed_doc_title_label')}</label>
            <input id="ed-doc-title" value="${UI.esc(_editItem?.title || content.title || '')}" maxlength="255">
          </div>
          <div>
            <label>${t('awareness.ed_status_label')}</label>
            <select id="ed-status">
              <option value="draft" ${(!_editItem||_editItem.status==='draft')?'selected':''}>${t('awareness.ed_status_draft')}</option>
              <option value="published" ${_editItem?.status==='published'?'selected':''}>${t('awareness.ed_status_published')}</option>
            </select>
          </div>
          <div style="display:flex;gap:8px;">
            <button class="btn btn-primary" style="flex:1;" onclick="_awSave()">${t('awareness.ed_btn_save')}</button>
            ${_editItem ? `<button class="btn" onclick="_awExportPdf(${_editItem.id})">${t('awareness.ed_btn_pdf')}</button>` : ''}
          </div>
          ${_editItem ? `<button class="btn" style="border-color:var(--risk-high);color:var(--risk-high);"
            onclick="_awDeleteItem(${_editItem.id})">${t('awareness.ed_btn_delete')}</button>` : ''}
        </div>

        <div>
          <div id="ed-preview-wrap"></div>
        </div>
      </div>
    `;

    ['ed-tpl','ed-urgency','ed-title','ed-subtitle','ed-main',
     'ed-keypoints','ed-do','ed-dont','ed-stat-val','ed-stat-lbl',
     'ed-cta','ed-contact','ed-hashtags'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('input', _awUpdatePreview);
    });

    _awUpdatePreview();
  }

  function _awGetEditorContent() {
    const g = id => document.getElementById(id)?.value || '';
    const lines = id => g(id).split('\n').map(l => l.trim()).filter(Boolean);
    const statVal = g('ed-stat-val').trim();
    return {
      template:      g('ed-tpl') || 'best_practices',
      urgency:       g('ed-urgency') || 'medium',
      title:         g('ed-title'),
      subtitle:      g('ed-subtitle'),
      main_message:  g('ed-main'),
      key_points:    lines('ed-keypoints').slice(0, 5),
      do_items:      lines('ed-do').slice(0, 4),
      dont_items:    lines('ed-dont').slice(0, 3),
      statistic:     statVal ? { value: statVal, label: g('ed-stat-lbl') } : null,
      call_to_action: g('ed-cta'),
      contact:       g('ed-contact'),
      hashtags:      g('ed-hashtags').split(/\s+/).filter(Boolean).slice(0, 4),
    };
  }

  window._awUpdatePreview = function() {
    const pw = document.getElementById('ed-preview-wrap');
    if (!pw) return;
    _renderPreview(pw, _awGetEditorContent());
  };

  window._awSave = async function() {
    const content = _awGetEditorContent();
    const title = document.getElementById('ed-doc-title')?.value?.trim() || content.title || t('awareness.preview_no_title');
    const status = document.getElementById('ed-status')?.value || 'draft';
    try {
      if (_editItem) {
        await Api.awareness.update(_editItem.id, { title, template_type: content.template, content, status });
        UI.toast(t('awareness.save_updated'), 'success');
      } else {
        const saved = await Api.awareness.create({ title, template_type: content.template, content, status });
        _editItem = saved;
        _draft = null;
        UI.toast(t('awareness.save_created'), 'success');
        await _renderEditor(document.getElementById('aw-body'));
      }
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  };

  window._awDeleteItem = async function(id) {
    if (!await UI.confirm(t('awareness.delete_confirm'))) return;
    try {
      await Api.awareness.delete(id);
      _editItem = null;
      _draft = null;
      UI.toast(t('awareness.deleted'), 'success');
      _switchTab('library');
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  };

  window._awExportPdf = async function(id) {
    try {
      const tok = localStorage.getItem('riskhub_token');
      const r = await fetch(`/api/awareness/${id}/export-pdf`, {
        headers: { Authorization: 'Bearer ' + tok },
      });
      if (!r.ok) throw new Error(t('awareness.pdf_error', { status: r.status }));
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `infografia_${id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  };

  // ================================================================
  // Tab: Biblioteca
  // ================================================================

  async function _renderLibrary(wrap) {
    _items = await Api.awareness.list();
    const TEMPLATES = _getTemplates();
    if (!_items.length) {
      wrap.innerHTML = `
        <div class="card" style="text-align:center;padding:48px;color:var(--text-muted);">
          <div style="font-size:48px;margin-bottom:12px;">📚</div>
          <p>${t('awareness.lib_no_items')}</p>
          <button class="btn btn-primary" onclick="ViewAwareness._switchTab('generator')">${t('awareness.lib_btn_create')}</button>
        </div>`;
      return;
    }

    wrap.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;">
        ${_items.map(item => {
          const tpl = TEMPLATES[item.template_type] || TEMPLATES.best_practices;
          const preview = _buildMiniPreview(item.content);
          return `
            <div class="card" style="display:flex;flex-direction:column;gap:0;overflow:hidden;cursor:pointer;"
              onclick="_awOpenItem(${item.id})">
              <div style="background:${tpl.color};padding:10px 14px;
                          display:flex;justify-content:space-between;align-items:center;">
                <span style="color:#fff;font-size:12px;font-weight:700;">
                  ${tpl.icon} ${UI.esc(item.title)}
                </span>
                <span style="background:rgba(255,255,255,.2);color:#fff;font-size:10px;
                             padding:2px 8px;border-radius:10px;">
                  ${item.status === 'published' ? t('awareness.lib_status_published') : t('awareness.lib_status_draft')}
                </span>
              </div>
              <div style="padding:12px 14px;flex:1;font-size:12px;color:var(--text-muted);">
                ${preview}
              </div>
              <div style="padding:8px 14px;border-top:1px solid var(--border);
                          display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:11px;color:var(--text-subtle);">
                  ${item.updated_at ? item.updated_at.slice(0,10) : ''} · ${UI.esc(item.created_by||'')}
                </span>
                <div style="display:flex;gap:6px;">
                  <button class="btn" style="font-size:11px;padding:3px 8px;"
                    onclick="event.stopPropagation();_awExportPdf(${item.id})">${t('awareness.ed_btn_pdf')}</button>
                  <button class="btn" style="font-size:11px;padding:3px 8px;"
                    onclick="event.stopPropagation();_awOpenItem(${item.id})">${t('awareness.lib_btn_edit')}</button>
                </div>
              </div>
            </div>`;
        }).join('')}
      </div>`;
  }

  function _buildMiniPreview(content) {
    if (!content) return '';
    const pts = (content.key_points || []).slice(0, 3);
    return `
      <div style="font-weight:600;color:var(--text-1);margin-bottom:4px;">${UI.esc(content.main_message||'')}</div>
      ${pts.map(p => `<div style="margin-bottom:2px;">• ${UI.esc(p)}</div>`).join('')}`;
  }

  window._awOpenItem = async function(id) {
    const item = _items.find(i => i.id === id);
    if (!item) return;
    _editItem = item;
    _draft = null;
    _switchTab('editor');
  };

  // ================================================================
  // Tab: Marca (Branding)
  // ================================================================

  async function _renderBrandingTab(wrap) {
    const b = _branding || {};
    wrap.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">
        <div class="card" style="display:flex;flex-direction:column;gap:14px;">
          <h3 style="margin:0;font-size:14px;color:var(--brand-purple);">${t('awareness.br_title')}</h3>
          <p style="font-size:12px;color:var(--text-muted);margin:0;">${t('awareness.br_desc')}</p>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div>
              <label>${t('awareness.br_primary_color')}</label>
              <div style="display:flex;gap:8px;align-items:center;">
                <input type="color" id="br-primary" value="${b.primary_color||'#59008D'}"
                  style="width:44px;height:36px;padding:2px;border-radius:6px;cursor:pointer;">
                <input id="br-primary-hex" value="${b.primary_color||'#59008D'}"
                  maxlength="7" style="flex:1;" placeholder="#59008D">
              </div>
            </div>
            <div>
              <label>${t('awareness.br_secondary_color')}</label>
              <div style="display:flex;gap:8px;align-items:center;">
                <input type="color" id="br-secondary" value="${b.secondary_color||'#D65200'}"
                  style="width:44px;height:36px;padding:2px;border-radius:6px;cursor:pointer;">
                <input id="br-secondary-hex" value="${b.secondary_color||'#D65200'}"
                  maxlength="7" style="flex:1;" placeholder="#D65200">
              </div>
            </div>
          </div>

          <div>
            <label>${t('awareness.br_company_label')}</label>
            <input id="br-company" value="${UI.esc(b.company_name||'')}" placeholder="Acme Corp">
          </div>

          <div>
            <label>${t('awareness.br_logo_label')}</label>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
              <input type="file" id="br-logo-file" accept="image/png,image/jpeg,image/svg+xml,image/webp"
                style="flex:1;">
              ${b.has_logo ? `
                <button class="btn" onclick="_awDeleteLogo()"
                  style="border-color:var(--risk-high);color:var(--risk-high);">
                  ${t('awareness.br_btn_delete_logo')}
                </button>` : ''}
            </div>
            ${_logoDataUrl ? `
              <div style="margin-top:8px;">
                <img src="${_logoDataUrl}" style="max-height:60px;max-width:200px;object-fit:contain;
                  border:1px solid var(--border);border-radius:6px;padding:4px;">
              </div>` : b.has_logo ? `
              <div style="margin-top:8px;font-size:12px;color:var(--text-muted);">
                ${t('awareness.br_logo_configured')}
              </div>` : ''}
          </div>

          <button class="btn btn-primary" onclick="_awSaveBranding()">${t('awareness.br_btn_save')}</button>
        </div>

        <div>
          <h4 style="margin:0 0 12px;font-size:13px;color:var(--text-muted);">${t('awareness.br_preview_title')}</h4>
          <div id="br-preview"></div>
        </div>
      </div>
    `;

    const syncColor = (colorId, hexId) => {
      document.getElementById(colorId).oninput = function() {
        document.getElementById(hexId).value = this.value;
        _awUpdateBrandingPreview();
      };
      document.getElementById(hexId).oninput = function() {
        if (/^#[0-9A-Fa-f]{6}$/.test(this.value)) {
          document.getElementById(colorId).value = this.value;
          _awUpdateBrandingPreview();
        }
      };
    };
    syncColor('br-primary', 'br-primary-hex');
    syncColor('br-secondary', 'br-secondary-hex');
    document.getElementById('br-company').oninput = _awUpdateBrandingPreview;

    document.getElementById('br-logo-file').onchange = function() {
      const file = this.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = e => { _logoDataUrl = e.target.result; _awUpdateBrandingPreview(); };
      reader.readAsDataURL(file);
    };

    _awUpdateBrandingPreview();
  }

  function _awUpdateBrandingPreview() {
    const pw = document.getElementById('br-preview');
    if (!pw) return;
    const primary = document.getElementById('br-primary-hex')?.value || '#59008D';
    const company = document.getElementById('br-company')?.value || '';

    const demoContent = {
      template: 'best_practices',
      urgency: 'high',
      title: t('awareness.preview_no_title'),
      subtitle: company || t('awareness.br_no_logo_sub'),
      main_message: t('awareness.br_demo_message'),
      key_points: [t('awareness.tpl_best_practices'), t('awareness.tpl_risk_alert'), t('awareness.tpl_policy')],
      do_items: [],
      dont_items: [],
      call_to_action: '',
      hashtags: ['#Security', '#Awareness'],
    };

    const TEMPLATES = _getTemplates();
    const origColor = TEMPLATES.best_practices.color;
    TEMPLATES.best_practices.color = primary;
    _renderPreview(pw, demoContent, true);
    TEMPLATES.best_practices.color = origColor;

    if (_logoDataUrl) {
      const header = pw.querySelector('.aw-card-preview > div:first-child');
      if (header) {
        const logoDiv = document.createElement('img');
        logoDiv.src = _logoDataUrl;
        logoDiv.style.cssText = 'max-height:36px;max-width:100px;object-fit:contain;margin-left:8px;';
        const flex = header.querySelector('div:first-child');
        if (flex) flex.appendChild(logoDiv);
      }
    }
  }

  window._awSaveBranding = async function() {
    const primary = document.getElementById('br-primary-hex')?.value || '#59008D';
    const secondary = document.getElementById('br-secondary-hex')?.value || '#D65200';
    const company = document.getElementById('br-company')?.value || '';
    try {
      await Api.awareness.saveBranding({ primary_color: primary, secondary_color: secondary, company_name: company });
      const fileEl = document.getElementById('br-logo-file');
      if (fileEl?.files[0]) {
        const fd = new FormData();
        fd.append('file', fileEl.files[0]);
        await Api.awareness.uploadLogo(fd);
      }
      _branding = { primary_color: primary, secondary_color: secondary, company_name: company, has_logo: !!(fileEl?.files[0] || _branding?.has_logo) };
      UI.toast(t('awareness.br_saved'), 'success');
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  };

  window._awDeleteLogo = async function() {
    try {
      await Api.awareness.deleteLogo();
      _logoDataUrl = null;
      if (_branding) _branding.has_logo = false;
      UI.toast(t('awareness.br_logo_deleted'), 'success');
      _renderBrandingTab(document.getElementById('aw-body'));
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  };

  // ================================================================
  // Helpers internos
  // ================================================================

  async function _loadBranding() {
    try {
      _branding = await Api.awareness.getBranding();
    } catch (_) { _branding = null; }
  }

  // ================================================================
  // Exports
  // ================================================================

  return {
    render,
    _switchTab,
    _goEditDraft() {
      _editItem = null;
      _switchTab('editor');
    },
  };
})();
