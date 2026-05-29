/* Vista Awareness — Generador de infografias de seguridad por IA. */
const ViewAwareness = (() => {

  const TEMPLATES = {
    risk_alert:     { label: 'Alerta de Riesgo',         icon: '🚨', color: '#C0392B' },
    best_practices: { label: 'Buenas Practicas',          icon: '✅', color: '#59008D' },
    policy:         { label: 'Politica Corporativa',      icon: '📜', color: '#1565C0' },
    threat:         { label: 'Amenaza del Mes',           icon: '⚠️', color: '#212121' },
    phishing:       { label: 'Anti-Phishing',             icon: '🎣', color: '#D65200' },
  };

  const URGENCY = {
    critical: { label: 'Critico',  color: '#C0392B' },
    high:     { label: 'Alto',     color: '#D65200' },
    medium:   { label: 'Medio',    color: '#F39C12' },
    low:      { label: 'Bajo',     color: '#27AE60' },
  };

  let _tab = 'generator';
  let _draft = null;       // contenido generado pendiente de guardar
  let _editItem = null;    // item en edicion
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
          <p class="page-sub">Genera infografias de concienciacion de seguridad con IA</p>
        </div>
      </div>
      <div class="tabs" id="aw-tabs">
        <button class="tab active" data-tab="generator">Generador</button>
        <button class="tab" data-tab="editor">Editor</button>
        <button class="tab" data-tab="library">Biblioteca</button>
        <button class="tab" data-tab="branding">Marca</button>
      </div>
      <div id="aw-body" style="margin-top:16px;"></div>
    `;
    el.querySelectorAll('.tab').forEach(t => {
      t.onclick = () => _switchTab(t.dataset.tab);
    });
    await _loadBranding();
    await _renderTab();
  }

  function _switchTab(tab) {
    _tab = tab;
    document.querySelectorAll('#aw-tabs .tab').forEach(t =>
      t.classList.toggle('active', t.dataset.tab === tab));
    _renderTab();
  }

  async function _renderTab() {
    const body = document.getElementById('aw-body');
    if (!body) return;
    body.innerHTML = '<div class="loading">Cargando...</div>';
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
    wrap.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;">
        <!-- Panel izquierdo: formulario -->
        <div>
          <div class="card" style="display:flex;flex-direction:column;gap:14px;">
            <h3 style="margin:0;font-size:14px;color:var(--brand-purple);">Describe la infografia que necesitas</h3>
            <div>
              <label>Plantilla sugerida</label>
              <select id="aw-tpl-select">
                <option value="">Que la IA decida</option>
                ${Object.entries(TEMPLATES).map(([k,v]) =>
                  `<option value="${k}">${v.icon} ${v.label}</option>`).join('')}
              </select>
            </div>
            <div>
              <label>Descripcion *</label>
              <textarea id="aw-prompt" rows="5" placeholder="Ej: Quiero una infografia sobre los riesgos de phishing para empleados de finanzas, destacando los indicadores mas comunes y como reportar..."
                style="width:100%;resize:vertical;"></textarea>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
              <button class="btn" onclick="_awQuickPrompt('phishing')">🎣 Anti-Phishing</button>
              <button class="btn" onclick="_awQuickPrompt('password')">🔑 Contrasenas</button>
              <button class="btn" onclick="_awQuickPrompt('remote')">🏠 Teletrabajo</button>
              <button class="btn" onclick="_awQuickPrompt('usb')">💾 Dispositivos USB</button>
              <button class="btn" onclick="_awQuickPrompt('social')">📱 Redes sociales</button>
            </div>
            <button class="btn btn-primary" id="aw-gen-btn" onclick="_awGenerate()">
              Generar infografia con IA
            </button>
          </div>
          <div id="aw-gen-status" style="margin-top:12px;"></div>
        </div>
        <!-- Panel derecho: preview -->
        <div>
          <div id="aw-preview-wrap" style="min-height:320px;">
            <div class="card" style="background:var(--bg-2);text-align:center;padding:48px 24px;color:var(--text-muted);">
              <div style="font-size:48px;margin-bottom:12px;">🎨</div>
              <p style="margin:0;">La preview de la infografia aparecera aqui</p>
              <p style="font-size:12px;margin-top:8px;">Describe lo que necesitas y pulsa "Generar"</p>
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

    const prompt = (promptEl?.value || '').trim();
    if (!prompt) { UI.toast('Describe la infografia que necesitas', 'error'); return; }

    btn.disabled = true;
    btn.textContent = 'Generando...';
    if (status) status.innerHTML = '<div class="notice">El agente IA esta generando el contenido... (10-20 segundos)</div>';

    try {
      const res = await Api.awareness.generate({
        prompt,
        template: tplEl?.value || null,
      });
      _draft = res.content;
      _renderPreview(document.getElementById('aw-preview-wrap'), _draft);
      if (status) status.innerHTML = `
        <div class="notice" style="background:var(--risk-low-bg,#e8f5e9);border-color:var(--risk-low,#27ae60);">
          Infografia generada correctamente.
          <button class="btn btn-primary" style="margin-left:12px;" onclick="ViewAwareness._goEditDraft()">
            Editar y guardar
          </button>
        </div>`;
    } catch (e) {
      if (status) status.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = 'Generar infografia con IA';
    }
  };

  // ================================================================
  // Preview renderer (HTML)
  // ================================================================

  function _renderPreview(wrap, content, compact = false) {
    if (!content) {
      wrap.innerHTML = '<div class="card" style="padding:32px;text-align:center;color:var(--text-muted);">Sin contenido</div>';
      return;
    }
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
        <!-- Header -->
        <div style="background:${tinfo.color};padding:${compact?'12px 16px':'16px 20px'};
                    display:flex;justify-content:space-between;align-items:flex-start;">
          <div style="flex:1;">
            <div style="color:rgba(255,255,255,.8);font-size:10px;font-weight:700;
                        letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;">
              ${tinfo.icon} ${tinfo.label}
            </div>
            <div style="color:#fff;font-size:${titleFs};font-weight:700;line-height:1.2;">
              ${UI.esc(content.title || 'Sin titulo')}
            </div>
            ${content.subtitle ? `<div style="color:rgba(255,255,255,.8);font-size:11px;margin-top:4px;">${UI.esc(content.subtitle)}</div>` : ''}
          </div>
          <div style="background:${urg.color};color:#fff;font-size:10px;font-weight:700;
                      padding:4px 10px;border-radius:12px;white-space:nowrap;margin-left:12px;">
            ${urg.label}
          </div>
        </div>

        <!-- Body -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:0;">
          <!-- Col izquierda -->
          <div style="padding:${compact?'12px 16px':'16px 20px'};border-right:1px solid var(--border);">
            ${content.main_message ? `
              <div style="font-size:${compact?'12px':'14px'};font-weight:600;color:${tinfo.color};
                          margin-bottom:12px;line-height:1.4;">
                ${UI.esc(content.main_message)}
              </div>` : ''}
            ${keyPoints.length ? `
              <div style="font-size:10px;font-weight:700;color:var(--text-muted);
                          text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">
                Puntos clave
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

          <!-- Col derecha -->
          <div style="padding:${compact?'12px 16px':'16px 20px'};">
            ${doItems.length ? `
              <div style="font-size:10px;font-weight:700;color:#27AE60;
                          text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">
                Haz esto ✓
              </div>
              <ul style="margin:0 0 12px;padding-left:16px;">
                ${doItems.map(i => `
                  <li style="margin-bottom:4px;color:var(--text-1);">${UI.esc(i)}</li>`).join('')}
              </ul>` : ''}
            ${dontItems.length ? `
              <div style="font-size:10px;font-weight:700;color:#C0392B;
                          text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;">
                Evita esto ✗
              </div>
              <ul style="margin:0;padding-left:16px;">
                ${dontItems.map(i => `
                  <li style="margin-bottom:4px;color:var(--text-1);">${UI.esc(i)}</li>`).join('')}
              </ul>` : ''}
            ${content.call_to_action ? `
              <div style="margin-top:12px;background:var(--bg-2);border-radius:8px;
                          padding:10px 12px;border-left:3px solid ${tinfo.color};">
                <div style="font-size:10px;font-weight:700;color:${tinfo.color};
                            text-transform:uppercase;margin-bottom:4px;">Accion</div>
                <div style="font-size:${fs};color:var(--text-1);">${UI.esc(content.call_to_action)}</div>
              </div>` : ''}
          </div>
        </div>

        <!-- Footer -->
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
    if (!src) {
      wrap.innerHTML = `
        <div class="card" style="text-align:center;padding:48px;color:var(--text-muted);">
          <div style="font-size:48px;margin-bottom:12px;">✏️</div>
          <p>No hay ninguna infografia abierta para editar.</p>
          <p style="font-size:12px;">Genera una nueva en el Generador o abre una desde la Biblioteca.</p>
          <button class="btn btn-primary" onclick="ViewAwareness._switchTab('generator')">Ir al Generador</button>
        </div>`;
      return;
    }

    let content = JSON.parse(JSON.stringify(src)); // deep copy

    wrap.innerHTML = `
      <div style="display:grid;grid-template-columns:340px 1fr;gap:20px;align-items:start;">
        <!-- Formulario de edicion -->
        <div class="card" style="display:flex;flex-direction:column;gap:12px;overflow-y:auto;max-height:80vh;">
          <h3 style="margin:0;font-size:14px;color:var(--brand-purple);">Editar contenido</h3>

          <div>
            <label>Plantilla</label>
            <select id="ed-tpl">
              ${Object.entries(TEMPLATES).map(([k,v]) =>
                `<option value="${k}" ${content.template===k?'selected':''}>${v.icon} ${v.label}</option>`).join('')}
            </select>
          </div>
          <div>
            <label>Urgencia</label>
            <select id="ed-urgency">
              ${Object.entries(URGENCY).map(([k,v]) =>
                `<option value="${k}" ${content.urgency===k?'selected':''}>${v.label}</option>`).join('')}
            </select>
          </div>
          <div><label>Titulo</label>
            <input id="ed-title" value="${UI.esc(content.title||'')}" maxlength="55"></div>
          <div><label>Subtitulo</label>
            <input id="ed-subtitle" value="${UI.esc(content.subtitle||'')}" maxlength="100"></div>
          <div><label>Mensaje principal</label>
            <textarea id="ed-main" rows="3" maxlength="180">${UI.esc(content.main_message||'')}</textarea></div>

          <div>
            <label>Puntos clave (uno por linea)</label>
            <textarea id="ed-keypoints" rows="4">${(content.key_points||[]).map(UI.esc).join('\n')}</textarea>
          </div>
          <div>
            <label>Haz esto (uno por linea)</label>
            <textarea id="ed-do" rows="3">${(content.do_items||[]).map(UI.esc).join('\n')}</textarea>
          </div>
          <div>
            <label>Evita esto (uno por linea)</label>
            <textarea id="ed-dont" rows="3">${(content.dont_items||[]).map(UI.esc).join('\n')}</textarea>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            <div><label>Estadistica</label>
              <input id="ed-stat-val" placeholder="85%" value="${UI.esc(content.statistic?.value||'')}"></div>
            <div><label>Descripcion</label>
              <input id="ed-stat-lbl" placeholder="de ataques..." value="${UI.esc(content.statistic?.label||'')}"></div>
          </div>
          <div><label>Llamada a la accion</label>
            <textarea id="ed-cta" rows="2" maxlength="120">${UI.esc(content.call_to_action||'')}</textarea></div>
          <div><label>Contacto / Reporte a</label>
            <input id="ed-contact" value="${UI.esc(content.contact||'')}"></div>
          <div><label>Hashtags (separados por espacio)</label>
            <input id="ed-hashtags" value="${UI.esc((content.hashtags||[]).join(' '))}"></div>

          <button class="btn" id="ed-preview-btn" onclick="_awUpdatePreview()">
            Actualizar preview
          </button>

          <hr style="border:none;border-top:1px solid var(--border);margin:4px 0;">
          <div>
            <label>Titulo del documento</label>
            <input id="ed-doc-title" value="${UI.esc(_editItem?.title || content.title || '')}" maxlength="255">
          </div>
          <div>
            <label>Estado</label>
            <select id="ed-status">
              <option value="draft" ${(!_editItem||_editItem.status==='draft')?'selected':''}>Borrador</option>
              <option value="published" ${_editItem?.status==='published'?'selected':''}>Publicado</option>
            </select>
          </div>
          <div style="display:flex;gap:8px;">
            <button class="btn btn-primary" style="flex:1;" onclick="_awSave()">Guardar</button>
            ${_editItem ? `<button class="btn" onclick="_awExportPdf(${_editItem.id})">PDF</button>` : ''}
          </div>
          ${_editItem ? `<button class="btn" style="border-color:var(--risk-high);color:var(--risk-high);"
            onclick="_awDeleteItem(${_editItem.id})">Eliminar</button>` : ''}
        </div>

        <!-- Preview live -->
        <div>
          <div id="ed-preview-wrap"></div>
        </div>
      </div>
    `;

    // Añadir listeners para actualizar preview en tiempo real
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
    const title = document.getElementById('ed-doc-title')?.value?.trim() || content.title || 'Sin titulo';
    const status = document.getElementById('ed-status')?.value || 'draft';
    try {
      if (_editItem) {
        await Api.awareness.update(_editItem.id, { title, template_type: content.template, content, status });
        UI.toast('Infografia actualizada', 'success');
      } else {
        const saved = await Api.awareness.create({ title, template_type: content.template, content, status });
        _editItem = saved;
        _draft = null;
        UI.toast('Infografia guardada', 'success');
        await _renderEditor(document.getElementById('aw-body'));
      }
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  };

  window._awDeleteItem = async function(id) {
    if (!confirm('¿Eliminar esta infografia?')) return;
    try {
      await Api.awareness.delete(id);
      _editItem = null;
      _draft = null;
      UI.toast('Eliminada', 'success');
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
      if (!r.ok) throw new Error('Error al descargar el PDF (' + r.status + ')');
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
    if (!_items.length) {
      wrap.innerHTML = `
        <div class="card" style="text-align:center;padding:48px;color:var(--text-muted);">
          <div style="font-size:48px;margin-bottom:12px;">📚</div>
          <p>No hay infografias guardadas todavia.</p>
          <button class="btn btn-primary" onclick="ViewAwareness._switchTab('generator')">Crear primera infografia</button>
        </div>`;
      return;
    }

    wrap.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;">
        ${_items.map(item => {
          const tpl = TEMPLATES[item.template_type] || TEMPLATES.best_practices;
          const preview = _buildMiniPreview(item.content, tpl);
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
                  ${item.status === 'published' ? 'Publicado' : 'Borrador'}
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
                    onclick="event.stopPropagation();_awExportPdf(${item.id})">PDF</button>
                  <button class="btn" style="font-size:11px;padding:3px 8px;"
                    onclick="event.stopPropagation();_awOpenItem(${item.id})">Editar</button>
                </div>
              </div>
            </div>`;
        }).join('')}
      </div>`;
  }

  function _buildMiniPreview(content, tpl) {
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
          <h3 style="margin:0;font-size:14px;color:var(--brand-purple);">Configuracion de marca</h3>
          <p style="font-size:12px;color:var(--text-muted);margin:0;">
            Estos colores y logo se aplicaran a todas las infografias exportadas en PDF.
          </p>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div>
              <label>Color principal</label>
              <div style="display:flex;gap:8px;align-items:center;">
                <input type="color" id="br-primary" value="${b.primary_color||'#59008D'}"
                  style="width:44px;height:36px;padding:2px;border-radius:6px;cursor:pointer;">
                <input id="br-primary-hex" value="${b.primary_color||'#59008D'}"
                  maxlength="7" style="flex:1;" placeholder="#59008D">
              </div>
            </div>
            <div>
              <label>Color secundario</label>
              <div style="display:flex;gap:8px;align-items:center;">
                <input type="color" id="br-secondary" value="${b.secondary_color||'#D65200'}"
                  style="width:44px;height:36px;padding:2px;border-radius:6px;cursor:pointer;">
                <input id="br-secondary-hex" value="${b.secondary_color||'#D65200'}"
                  maxlength="7" style="flex:1;" placeholder="#D65200">
              </div>
            </div>
          </div>

          <div>
            <label>Nombre de la empresa</label>
            <input id="br-company" value="${UI.esc(b.company_name||'')}" placeholder="Acme Corp">
          </div>

          <div>
            <label>Logo (PNG, JPG o SVG — max 2 MB)</label>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
              <input type="file" id="br-logo-file" accept="image/png,image/jpeg,image/svg+xml,image/webp"
                style="flex:1;">
              ${b.has_logo ? `
                <button class="btn" onclick="_awDeleteLogo()"
                  style="border-color:var(--risk-high);color:var(--risk-high);">
                  Eliminar logo
                </button>` : ''}
            </div>
            ${_logoDataUrl ? `
              <div style="margin-top:8px;">
                <img src="${_logoDataUrl}" style="max-height:60px;max-width:200px;object-fit:contain;
                  border:1px solid var(--border);border-radius:6px;padding:4px;">
              </div>` : b.has_logo ? `
              <div style="margin-top:8px;font-size:12px;color:var(--text-muted);">
                Logo configurado. Sube uno nuevo para reemplazarlo.
              </div>` : ''}
          </div>

          <button class="btn btn-primary" onclick="_awSaveBranding()">Guardar configuracion de marca</button>
        </div>

        <!-- Preview de marca -->
        <div>
          <h4 style="margin:0 0 12px;font-size:13px;color:var(--text-muted);">Preview con tu marca</h4>
          <div id="br-preview"></div>
        </div>
      </div>
    `;

    // Sincronizar inputs de color
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

    // Logo preview
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
    const secondary = document.getElementById('br-secondary-hex')?.value || '#D65200';
    const company = document.getElementById('br-company')?.value || '';

    // Infografia de demo con los colores de marca
    const demoContent = {
      template: 'best_practices',
      urgency: 'high',
      title: 'Seguridad de la Informacion',
      subtitle: company || 'Tu empresa',
      main_message: 'Protege los activos de informacion corporativa en todo momento.',
      key_points: ['Usa contrasenas seguras y unicas', 'Reporta incidentes de seguridad', 'Mantén el software actualizado'],
      do_items: ['Bloquea tu equipo al alejarte', 'Verifica destinatarios antes de enviar'],
      dont_items: ['No uses redes wifi publicas sin VPN', 'No compartas credenciales'],
      call_to_action: 'Reporta cualquier incidente a seguridad@empresa.com',
      hashtags: ['#Seguridad', '#Awareness'],
    };

    // Temporalmente cambiamos el color de la plantilla para el preview
    const origColor = TEMPLATES.best_practices.color;
    TEMPLATES.best_practices.color = primary;
    _renderPreview(pw, demoContent, true);
    TEMPLATES.best_practices.color = origColor;

    // Mostrar logo si hay
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
      // Subir logo si se selecciono uno nuevo
      const fileEl = document.getElementById('br-logo-file');
      if (fileEl?.files[0]) {
        const fd = new FormData();
        fd.append('file', fileEl.files[0]);
        await Api.awareness.uploadLogo(fd);
      }
      _branding = { primary_color: primary, secondary_color: secondary, company_name: company, has_logo: !!(fileEl?.files[0] || _branding?.has_logo) };
      UI.toast('Marca guardada correctamente', 'success');
    } catch (e) {
      UI.toast(e.message, 'error');
    }
  };

  window._awDeleteLogo = async function() {
    try {
      await Api.awareness.deleteLogo();
      _logoDataUrl = null;
      if (_branding) _branding.has_logo = false;
      UI.toast('Logo eliminado', 'success');
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
