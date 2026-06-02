/* Vista Agente IA — Cuestionario de contexto + análisis de riesgos ISO 27005 / MAGERIT. */
const ViewQuestionnaire = {
  _questions: null,
  _answers: {},
  _result: null,

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      'Agente IA — Análisis de riesgos',
      'Cuestionario de contexto organizacional · ISO 27005 + MAGERIT v3'
    ) + '<div id="ai-content"></div>';
    await this._loadQuestionnaire();
  },

  async _loadQuestionnaire() {
    const c = document.getElementById('ai-content');
    try {
      const data = await Api.get('/api/ai/questionnaire');
      this._questions = data.questions;
      if (data.saved_answers && Object.keys(data.saved_answers).length > 0) {
        this._answers = { ...data.saved_answers };
      }
      this._renderForm(c);
      if (Object.keys(this._answers).length > 0) {
        this._prefillForm(this._answers);
      }
    } catch (e) {
      c.innerHTML = UI.notice('Error al cargar el cuestionario: ' + UI.esc(e.message), 'error');
    }
  },

  _prefillForm(answers) {
    if (!answers) return;
    for (const [id, val] of Object.entries(answers)) {
      if (!val) continue;
      const sel = document.getElementById('q-' + id);
      if (sel && sel.tagName === 'SELECT') { sel.value = val; continue; }
      const ta = document.getElementById('q-' + id);
      if (ta && ta.tagName === 'TEXTAREA') { ta.value = val; continue; }
      const vals = Array.isArray(val) ? val : [val];
      vals.forEach(v => {
        const grid = document.getElementById('ms-grid-' + id);
        if (grid) {
          grid.querySelectorAll('input[type=checkbox]').forEach(cb => {
            if (cb.value === v) { cb.checked = true; cb.dispatchEvent(new Event('change')); }
          });
        }
      });
    }
    if (answers.ens_level) {
      const ensRad = document.querySelector(`input[name="ens_level"][value="${answers.ens_level}"]`);
      if (ensRad) { ensRad.checked = true; ensRad.dispatchEvent(new Event('change')); }
    }
    for (const [k, v] of Object.entries(answers)) {
      if (k.startsWith('extra_') && v) {
        const qid = k.replace('extra_', '');
        const wrap = document.getElementById('extra-wrap-' + qid);
        const inp  = document.getElementById('extra-' + qid);
        if (wrap) wrap.style.display = '';
        if (inp)  inp.value = v;
      }
    }
    if (answers.custom_controls && Array.isArray(answers.custom_controls)) {
      answers.custom_controls.forEach(c => {
        if (typeof ViewQuestionnaire._customControls !== 'undefined') {
          ViewQuestionnaire._customControls.add(c);
        }
      });
    }
  },

  _renderForm(container) {
    const qs = this._questions;
    const cats = {};
    qs.forEach(q => {
      if (!cats[q.category]) cats[q.category] = [];
      cats[q.category].push(q);
    });

    const catIcons = {
      'Contexto organizacional': '🏢',
      'Activos y datos': '🗄️',
      'Exposición': '🌐',
      'Controles existentes': '🛡️',
      'Apetito de riesgo': '📊',
    };

    let html = `
      <div class="card" style="margin-bottom:16px;background:linear-gradient(135deg,var(--brand-purple-4),var(--brand-orange-4));border:1px solid var(--brand-purple-3);">
        <p style="margin:0;font-size:14px;color:var(--text-base);">
          <strong>¿Cómo funciona?</strong> Responde las preguntas sobre tu organización.
          El agente IA analizará el perfil de riesgo siguiendo <strong>ISO/IEC 27005:2018</strong> y
          <strong>MAGERIT v3</strong>, creará automáticamente los riesgos en el sistema y guardará el
          contexto organizacional para adaptar informes, cumplimiento y respuestas del agente.
          <br><span style="font-size:12px;color:var(--text-muted);">
            Puedes añadir criterios adicionales con el botón <strong>"+ Añadir criterio"</strong>.
          </span>
        </p>
      </div>`;

    Object.entries(cats).forEach(([cat, questions]) => {
      html += `<div class="card" style="margin-bottom:16px;">
        <h3 style="margin-bottom:16px;">${catIcons[cat] || '📋'} ${cat}</h3>
        <div class="modal-body">`;

      questions.forEach(q => {
        const req = q.required ? '<span style="color:var(--brand-orange)">*</span>' : '';
        html += `<div class="span2"><label style="display:flex;justify-content:space-between;align-items:baseline;">
          <span>${UI.esc(q.question)} ${req}</span>
          ${q.allow_extra ? `<button type="button" class="btn btn-ghost btn-sm" style="font-size:11px;padding:2px 8px;"
            onclick="ViewQuestionnaire._toggleExtra('${q.id}')">+ Añadir criterio</button>` : ''}
        </label>`;

        if (q.type === 'select') {
          html += `<select id="q-${q.id}" style="width:100%;">
            <option value="">— Selecciona —</option>
            ${q.options.map(o => `<option value="${UI.esc(o)}">${UI.esc(o)}</option>`).join('')}
          </select>`;
        } else if (q.type === 'multiselect') {
          html += `<div id="ms-grid-${q.id}" style="display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:8px;">
            ${q.options.map(o => {
              const isEns = (q.id === 'regulations' && o.startsWith('ENS'));
              return `
              <label class="ms-opt" style="display:block;cursor:pointer;background:var(--bg-2);
                     border:1px solid var(--border);border-radius:8px;
                     padding:10px 12px;font-size:13px;line-height:1.5;
                     transition:background .15s,border-color .15s;">
                <input type="checkbox" data-q="${q.id}" value="${UI.esc(o)}"
                       style="accent-color:var(--brand-purple);margin-right:8px;vertical-align:middle;flex-shrink:0;"
                       ${isEns ? `onchange="ViewQuestionnaire._toggleEnsLevel(this)"` : ''}>
                <span style="vertical-align:middle;">${UI.esc(o)}</span>
              </label>`;
            }).join('')}
          </div>
          ${q.id === 'regulations' ? `
            <div id="ens-level-wrap" style="display:none;margin-top:8px;padding:12px;
                 background:var(--brand-purple-4);border:1px solid var(--brand-purple-3);border-radius:8px;">
              <label style="font-size:12px;font-weight:600;color:var(--brand-purple);display:block;margin-bottom:8px;">
                Nivel ENS (RD 311/2022) *
              </label>
              <div style="display:flex;gap:8px;flex-wrap:wrap;">
                ${['basico','medio','alto'].map(lvl => `
                  <label style="display:flex;align-items:center;gap:6px;cursor:pointer;
                         background:var(--bg-1);border:2px solid var(--border);border-radius:8px;
                         padding:8px 16px;font-size:13px;font-weight:600;
                         transition:border-color .15s,background .15s;"
                         id="ens-lvl-lbl-${lvl}">
                    <input type="radio" name="ens_level" value="${lvl}" id="ens-lvl-${lvl}"
                           style="accent-color:var(--brand-purple);"
                           onchange="ViewQuestionnaire._highlightEnsLevel('${lvl}')">
                    ${lvl.charAt(0).toUpperCase() + lvl.slice(1)}
                  </label>`).join('')}
              </div>
              <p style="font-size:11px;color:var(--text-muted);margin:8px 0 0;">
                Básico: sistemas de categoría BAJA · Medio: categoría MEDIA · Alto: categoría ALTA
              </p>
            </div>` : ''}
          ${q.id === 'controls_existing' ? `
            <div style="margin-top:10px;border-top:1px dashed var(--border);padding-top:10px;">
              <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:6px;">
                Añadir control adicional (no está en la lista)
              </label>
              <div style="display:flex;gap:8px;align-items:center;">
                <input id="custom-ctrl-input" class="input" style="flex:1;"
                  placeholder="Ej: WAF, PAM, Zero Trust, cifrado de emails..."
                  onkeydown="if(event.key==='Enter'){event.preventDefault();ViewQuestionnaire._addCustomControl();}">
                <button type="button" class="btn btn-sm" onclick="ViewQuestionnaire._addCustomControl()">+ Añadir</button>
              </div>
              <div id="custom-ctrl-list" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;"></div>
            </div>` : ''}`;
        } else if (q.type === 'textarea') {
          html += `<textarea id="q-${q.id}" rows="3" style="width:100%;"
                    placeholder="Opcional — escribe cualquier información relevante..."></textarea>`;
        }

        if (q.allow_extra) {
          html += `
            <div id="extra-wrap-${q.id}" style="display:none;margin-top:8px;">
              <label style="font-size:11px;color:var(--text-muted);">Criterio adicional para el agente IA</label>
              <textarea id="extra-${q.id}" rows="2" class="input" style="width:100%;font-size:12px;"
                placeholder="Describe cualquier contexto, restriccion, requisito normativo o detalle relevante sobre este punto..."></textarea>
            </div>`;
        }

        html += `</div>`;
      });

      html += `</div></div>`;
    });

    html += `
      <div style="text-align:right;margin-top:8px;">
        <button class="btn btn-primary" id="btn-analyze" style="font-size:15px;padding:12px 32px;">
          Analizar con IA
        </button>
      </div>`;

    document.getElementById('ai-content').innerHTML = html;
    this._customControls = [];

    document.querySelectorAll('.ms-opt').forEach(label => {
      const cb = label.querySelector('input');
      cb.addEventListener('change', () => {
        label.style.background = cb.checked ? 'var(--brand-purple-4)' : 'var(--bg-2)';
        label.style.borderColor = cb.checked ? 'var(--brand-purple)' : 'var(--border)';
      });
    });

    document.getElementById('btn-analyze').onclick = () => this._submit();
  },

  _toggleEnsLevel(checkbox) {
    const wrap = document.getElementById('ens-level-wrap');
    if (!wrap) return;
    wrap.style.display = checkbox.checked ? '' : 'none';
    if (!checkbox.checked) {
      document.querySelectorAll('input[name="ens_level"]').forEach(r => r.checked = false);
      document.querySelectorAll('[id^="ens-lvl-lbl-"]').forEach(l => {
        l.style.borderColor = 'var(--border)'; l.style.background = 'var(--bg-1)';
      });
    }
  },

  _highlightEnsLevel(lvl) {
    ['basico','medio','alto'].forEach(l => {
      const lbl = document.getElementById(`ens-lvl-lbl-${l}`);
      if (lbl) {
        lbl.style.borderColor = l === lvl ? 'var(--brand-purple)' : 'var(--border)';
        lbl.style.background  = l === lvl ? 'var(--brand-purple-4)' : 'var(--bg-1)';
      }
    });
  },

  _customControls: [],

  _addCustomControl() {
    const input = document.getElementById('custom-ctrl-input');
    const val = input?.value.trim();
    if (!val) return;
    if (this._customControls.includes(val)) {
      UI.toast('Ese control ya está añadido', 'warn'); return;
    }
    this._customControls.push(val);
    input.value = '';
    this._renderCustomControls();
  },

  _removeCustomControl(idx) {
    this._customControls.splice(idx, 1);
    this._renderCustomControls();
  },

  _renderCustomControls() {
    const list = document.getElementById('custom-ctrl-list');
    if (!list) return;
    list.innerHTML = this._customControls.map((c, i) => `
      <span style="display:inline-flex;align-items:center;gap:4px;background:var(--brand-purple-4);
            border:1px solid var(--brand-purple-3);border-radius:20px;padding:4px 12px;font-size:12px;">
        ${UI.esc(c)}
        <button type="button" onclick="ViewQuestionnaire._removeCustomControl(${i})"
          style="background:none;border:none;cursor:pointer;color:var(--brand-purple);font-size:14px;padding:0 0 0 4px;">×</button>
      </span>`).join('');
  },

  _toggleExtra(qId) {
    const wrap = document.getElementById(`extra-wrap-${qId}`);
    if (wrap) {
      const visible = wrap.style.display !== 'none';
      wrap.style.display = visible ? 'none' : '';
      if (!visible) document.getElementById(`extra-${qId}`)?.focus();
    }
  },

  _collectAnswers() {
    const answers = {};
    const missing = [];

    this._questions.forEach(q => {
      if (q.type === 'select') {
        const el = document.getElementById(`q-${q.id}`);
        if (el) answers[q.id] = el.value;
        if (q.required && !el?.value) missing.push(q.question.substring(0, 50));
      } else if (q.type === 'multiselect') {
        const checked = [...document.querySelectorAll(`input[data-q="${q.id}"]:checked`)]
          .map(cb => cb.value);
        answers[q.id] = checked;
        if (q.required && checked.length === 0) missing.push(q.question.substring(0, 50));
      } else if (q.type === 'textarea') {
        const el = document.getElementById(`q-${q.id}`);
        if (el) answers[q.id] = el.value;
      }
      if (q.allow_extra) {
        const extraEl = document.getElementById(`extra-${q.id}`);
        if (extraEl && extraEl.value.trim()) {
          answers[`extra_${q.id}`] = extraEl.value.trim();
        }
      }
    });

    const ensChecked = document.querySelector('input[name="ens_level"]:checked');
    if (ensChecked) answers.ens_level = ensChecked.value;

    if (this._customControls.length > 0) {
      answers.custom_controls = [...this._customControls];
    }

    return { answers, missing };
  },

  _ensureSpinnerStyle() {
    if (!document.getElementById('spinner-style')) {
      const s = document.createElement('style');
      s.id = 'spinner-style';
      s.textContent = `.spinner{width:40px;height:40px;border:4px solid var(--border);
        border-top-color:var(--brand-purple);border-radius:50%;
        animation:spin 0.8s linear infinite;margin:0 auto;}
        @keyframes spin{to{transform:rotate(360deg)}}`;
      document.head.appendChild(s);
    }
  },

  _showSpinner(msg, sub) {
    const c = document.getElementById('ai-content');
    if (!c) return;
    this._ensureSpinnerStyle();
    c.innerHTML = `
      <div class="card" style="text-align:center;padding:48px 24px;">
        <div style="font-size:48px;margin-bottom:16px;">🤖</div>
        <h3 id="spinner-title">${msg}</h3>
        <p id="spinner-sub" style="color:var(--text-muted);margin-top:8px;">${sub}</p>
        <div style="margin-top:24px;" class="spinner"></div>
        <p id="spinner-timer" style="margin-top:16px;font-size:12px;color:var(--text-muted);"></p>
      </div>`;
  },

  _updateSpinnerTimer(elapsed) {
    const el = document.getElementById('spinner-timer');
    if (el) el.textContent = `Tiempo transcurrido: ${elapsed}s`;
  },

  // Polling de /api/ai/analyze/status/{jobId} cada 3 segundos
  async _pollAnalysis(jobId) {
    const startMs = Date.now();
    for (;;) {
      await new Promise(r => setTimeout(r, 3000));
      this._updateSpinnerTimer(Math.round((Date.now() - startMs) / 1000));
      const data = await Api.get(`/api/ai/analyze/status/${jobId}`);
      if (data.status === 'done')   return data.result;
      if (data.status === 'error')  throw new Error(data.error || 'Error desconocido en el análisis');
      // 'running' → seguir esperando
    }
  },

  async _submit() {
    const { answers, missing } = this._collectAnswers();
    if (missing.length > 0) {
      UI.toast(`Completa los campos obligatorios: ${missing.slice(0,2).join(', ')}...`, 'error');
      return;
    }

    this._answers = answers;
    const c = document.getElementById('ai-content');

    this._showSpinner(
      'Analizando el perfil de riesgo...',
      'El agente evalúa amenazas, vulnerabilidades y controles según <strong>ISO 27005</strong> y <strong>MAGERIT v3</strong>.<br>Esto puede tardar entre 30 y 60 segundos.'
    );

    try {
      // 1. Lanzar análisis en background — devuelve job_id inmediatamente (< 1 s)
      const { job_id } = await Api.post('/api/ai/analyze/async', { answers });

      // 2. Polling hasta que el hilo de fondo termine
      const result = await this._pollAnalysis(job_id);
      this._result = result;

      // 3. Actualizar spinner y auto-aplicar riesgos
      const title = document.getElementById('spinner-title');
      const sub   = document.getElementById('spinner-sub');
      if (title) title.textContent = 'Aplicando riesgos al sistema...';
      if (sub)   sub.innerHTML = 'Creando escenarios en el registro y guardando el contexto organizacional.';

      let importResult = null;
      try {
        const payload = { scenarios: result.scenarios || [] };
        if (result.risk_appetite !== undefined && result.risk_appetite !== null) {
          payload.risk_appetite = result.risk_appetite;
        }
        if (result.active_frameworks?.length) {
          payload.active_frameworks = result.active_frameworks;
        }
        if (result.ens_level) {
          payload.ens_level = result.ens_level;
        }
        importResult = await Api.post('/api/ai/import', payload);
      } catch (importErr) {
        console.warn('Auto-aplicación de riesgos con advertencia:', importErr.message);
      }

      // 4. Mostrar análisis ejecutivo
      this._renderResults(c, result, importResult);
    } catch (e) {
      c.innerHTML = `
        <div class="notice notice-error" style="margin-bottom:16px;">${UI.esc(e.message)}</div>
        <div style="text-align:center;margin-top:16px;">
          <button class="btn btn-primary" onclick="ViewQuestionnaire.render(document.getElementById('main'))">
            Volver al cuestionario
          </button>
        </div>`;
    }
  },

  _renderResults(container, result, importResult) {
    const scenarios = result.scenarios || [];
    const appetite = result.risk_appetite ?? 3;
    const aboveAppetite = scenarios.filter(s => s.above_appetite).length;
    const belowAppetite = scenarios.length - aboveAppetite;

    const created = importResult?.created ?? 0;
    const skipped = importResult?.skipped ?? 0;

    const treatmentLabel = t => ({
      modification: '<span style="color:#D97706;font-size:10px;font-weight:700;">MITIGAR</span>',
      retention:    '<span style="color:#059669;font-size:10px;font-weight:700;">ACEPTAR</span>',
      avoidance:    '<span style="color:#B91C1C;font-size:10px;font-weight:700;">EVITAR</span>',
      sharing:      '<span style="color:#2563EB;font-size:10px;font-weight:700;">TRANSFERIR</span>',
    }[t] || '');

    // Normativas aplicadas
    const frameworks = (result.active_frameworks || []).join(', ').toUpperCase() || '—';

    let html = `
      <!-- Cabecera de análisis ejecutivo -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:8px;">
        <div>
          <h2 style="margin:0;font-size:18px;">Análisis ejecutivo</h2>
          <span style="font-size:12px;color:var(--text-muted);">Contexto organizacional guardado · Normativas: ${UI.esc(frameworks)}</span>
        </div>
        <button class="btn btn-primary" onclick="App.navigate('risks')"
          style="display:flex;align-items:center;gap:6px;font-size:14px;">
          Ver riesgos en sección Riesgos &rarr;
        </button>
      </div>

      <!-- Estado de aplicación -->
      <div class="card" style="margin-bottom:16px;background:${created > 0 ? 'var(--bg-success,#f0fdf4)' : 'var(--bg-2)'};border:1px solid ${created > 0 ? '#86efac' : 'var(--border)'};">
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
          <div style="font-size:28px;">${created > 0 ? '✓' : '⚠'}</div>
          <div>
            <strong style="font-size:15px;">${created > 0 ? `${created} riesgo${created !== 1 ? 's' : ''} creado${created !== 1 ? 's' : ''} en el sistema` : 'Riesgos ya existentes en el sistema'}</strong>
            ${skipped > 0 ? `<div style="font-size:12px;color:var(--text-muted);">${skipped} escenario${skipped !== 1 ? 's' : ''} omitido${skipped !== 1 ? 's' : ''} (ya existentes o sin activo/amenaza válida)</div>` : ''}
            <div style="font-size:12px;color:var(--text-muted);margin-top:2px;">
              Apetito de riesgo (<strong>${appetite}</strong>/8) y normativas guardados en el contexto organizacional.
              El agente IA, los informes y el cumplimiento reflejarán este perfil.
            </div>
          </div>
        </div>
      </div>

      <!-- Resumen ejecutivo -->
      <div class="card" style="margin-bottom:16px;border-left:4px solid var(--brand-purple);">
        <h3>Resumen</h3>
        <p style="margin-top:8px;line-height:1.6;">${UI.esc(result.summary || '')}</p>
        ${result.top_risks?.length ? `
          <div style="margin-top:12px;">
            <strong style="font-size:12px;text-transform:uppercase;color:var(--text-muted);">
              Riesgos críticos identificados
            </strong>
            <ul style="margin-top:6px;padding-left:20px;">
              ${result.top_risks.map(r => `<li style="margin-bottom:4px;">${UI.esc(r)}</li>`).join('')}
            </ul>
          </div>` : ''}
      </div>

      <!-- Apetito de riesgo -->
      <div class="card" style="margin-bottom:16px;background:var(--bg-2);">
        <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
          <div style="text-align:center;">
            <div style="font-size:28px;font-weight:700;color:var(--brand-purple);">${appetite}</div>
            <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;">Apetito de riesgo<br>(escala 0-8)</div>
          </div>
          <div style="flex:1;min-width:160px;">
            <div style="height:10px;border-radius:5px;background:linear-gradient(90deg,#059669,#D97706,#B91C1C);position:relative;margin-bottom:4px;">
              <div style="position:absolute;left:${Math.round(appetite/8*100)}%;top:-4px;width:18px;height:18px;
                           border-radius:50%;background:#fff;border:3px solid var(--brand-purple);transform:translateX(-50%);"></div>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text-muted);">
              <span>0 Mínimo</span><span>4 Moderado</span><span>8 Máximo</span>
            </div>
          </div>
          <div style="display:flex;gap:16px;text-align:center;">
            <div>
              <div style="font-size:20px;font-weight:700;color:#B91C1C;">${aboveAppetite}</div>
              <div style="font-size:11px;color:var(--text-muted);">Sobre apetito<br><small>requieren mitigación</small></div>
            </div>
            <div>
              <div style="font-size:20px;font-weight:700;color:#059669;">${belowAppetite}</div>
              <div style="font-size:11px;color:var(--text-muted);">Dentro de apetito<br><small>se pueden aceptar</small></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Escenarios generados (solo lectura, expandibles) -->
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <h3>Escenarios de riesgo analizados (${scenarios.length})</h3>
          <span style="font-size:12px;color:var(--text-muted);">Haz clic en una fila para ver el detalle</span>
        </div>
        <div style="overflow-x:auto;">
          <table class="data">
            <thead>
              <tr>
                <th>Activo</th>
                <th>Amenaza</th>
                <th style="width:60px;text-align:center;">Inh.</th>
                <th style="width:80px;text-align:center;">Controles</th>
                <th style="width:60px;text-align:center;">Res.</th>
                <th style="width:80px;text-align:center;">Tratamiento</th>
              </tr>
            </thead>
            <tbody>
              ${scenarios.map((sc, i) => `
                <tr style="cursor:pointer;${sc.above_appetite ? 'border-left:3px solid #D97706;' : ''}"
                    onclick="ViewQuestionnaire._toggleDetail(${i})">
                  <td>
                    <strong>${UI.esc(sc.asset_suggestion || '')}</strong>
                    <div style="font-size:11px;color:var(--text-muted);">${UI.esc(sc.asset_type || '')}</div>
                  </td>
                  <td>
                    ${sc.threat_code ? `<span class="badge badge-muted" style="font-size:10px;">${UI.esc(sc.threat_code)}</span> ` : ''}
                    ${UI.esc(sc.threat_name || '')}
                    <div style="font-size:11px;color:var(--text-muted);">dim: ${UI.esc(sc.magerit_dimension || '')}</div>
                  </td>
                  <td style="text-align:center;">${UI.riskPill(sc.inherent_level)}</td>
                  <td style="text-align:center;font-size:11px;">
                    ${(sc.control_codes || []).slice(0,3).map(c =>
                      `<span class="badge badge-muted">${UI.esc(c)}</span>`).join(' ')}
                    ${(sc.control_codes || []).length > 3 ? `+${sc.control_codes.length - 3}` : ''}
                  </td>
                  <td style="text-align:center;">${UI.riskPill(sc.residual_level)}</td>
                  <td style="text-align:center;">${treatmentLabel(sc.treatment_option)}</td>
                </tr>
                <tr id="sc-detail-${i}" style="display:none;background:var(--bg-2);">
                  <td colspan="6" style="padding:8px 12px;font-size:12px;color:var(--text-muted);border-top:none;">
                    <strong>Vulnerabilidad:</strong> ${UI.esc(sc.vulnerability_description || '')}<br>
                    <strong>Justificación:</strong> ${UI.esc(sc.rationale || '')}
                    ${sc.control_rationale ? `<br><strong>Controles aplicables:</strong> ${UI.esc(sc.control_rationale)}` : ''}
                  </td>
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>

      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;">
        <button class="btn" onclick="ViewQuestionnaire.render(document.getElementById('main'))">
          ← Nuevo análisis
        </button>
        <button class="btn btn-primary" onclick="App.navigate('risks')"
          style="font-size:15px;padding:12px 28px;">
          Ver riesgos en sección Riesgos &rarr;
        </button>
      </div>`;

    container.innerHTML = html;
  },

  _toggleDetail(i) {
    const row = document.getElementById(`sc-detail-${i}`);
    if (row) row.style.display = row.style.display === 'none' ? '' : 'none';
  },
};
