/* views/onboarding.js - Wizard lineal de setup inicial en 5 pasos.
 *
 * Paso 1: Organizacion      -> /api/context/ + /api/ai/config/
 * Paso 2: Cuestionario IA   -> /api/ai/questionnaire (troceado en sub-pantallas)
 * Paso 3: Documentos        -> /api/ai/documents/ (drag & drop, vectorizacion automatica)
 * Paso 4: Revisar propuesta -> /api/ai/analyze/async + polling + /api/ai/import
 * Paso 5: Automatizaciones  -> tarjetas informativas + API key + setup_completed
 *
 * Estado persistente:
 *   localStorage riskhub_wizard_step     -> paso actual (1-5)
 *   localStorage riskhub_wizard_substep  -> sub-pantalla del cuestionario
 *   localStorage riskhub_wizard_answers  -> respuestas del cuestionario (JSON)
 *   localStorage riskhub_onboarding_done / riskhub_onboarding_skipped (mecanismo existente)
 */

const ViewOnboarding = (() => {

  const LS_STEP    = 'riskhub_wizard_step';
  const LS_SUBSTEP = 'riskhub_wizard_substep';
  const LS_ANSWERS = 'riskhub_wizard_answers';

  const STEPS = [
    { n: 1, label: 'Organizacion' },
    { n: 2, label: 'Cuestionario IA' },
    { n: 3, label: 'Documentos' },
    { n: 4, label: 'Revisar propuesta' },
    { n: 5, label: 'Automatizaciones' },
  ];

  const ACCEPTED_EXTS = ['pdf', 'docx', 'txt', 'csv'];

  const SECTORS = ['Financiero / Banca', 'Sanitario / Salud', 'Industrial / Manufactura',
    'Tecnologia / Software', 'Administracion publica', 'Educacion',
    'Energia / Utilities', 'Retail / Comercio', 'Servicios profesionales', 'Otro'];

  const SIZES = ['< 50 empleados', '50-250 empleados', '250-1.000 empleados',
    '1.000-5.000 empleados', '> 5.000 empleados'];

  const AUTOMATIONS = [
    { title: 'Escaneo CVE automatico',
      desc: 'Consulta periodica de la NVD para detectar vulnerabilidades conocidas en tu stack tecnologico y vincularlas a los activos.' },
    { title: 'Re-escaneo OSINT semanal',
      desc: 'Revision semanal de exposicion externa (dominios, emails, IPs). Los hallazgos criticos generan incidentes automaticamente.' },
    { title: 'Informe mensual',
      desc: 'Generacion automatica de un informe ejecutivo mensual con la evolucion del riesgo y el estado del SGSI.' },
    { title: 'Escalado de tareas',
      desc: 'Las tareas vencidas se escalan automaticamente para que ninguna accion de tratamiento quede olvidada.' },
    { title: 'Revision de politicas',
      desc: 'Aviso automatico cuando una politica supera su fecha de revision prevista.' },
    { title: 'Degradacion de controles',
      desc: 'Deteccion de controles cuya efectividad decae con el tiempo sin evidencias recientes.' },
  ];

  // ---------- Estado ----------

  let _step = 1;          // paso actual 1-5
  let _substep = 0;       // sub-pantalla dentro del paso 2
  let _cfg = null;        // /api/ai/config/
  let _ctx = null;        // /api/context/
  let _questions = null;  // definicion del cuestionario
  let _groups = [];       // sub-pantallas: [{title, questions}]
  let _answers = {};      // respuestas acumuladas
  let _customControls = [];
  let _docs = [];         // documentos ya subidos
  let _queue = [];        // cola de subida paso 3: {name, size, status, error}
  let _uploading = false;
  let _result = null;     // resultado del analisis IA
  let _importResult = null;
  let _analyzing = false;
  let _busy = false;      // operacion async de navegacion en curso

  // ---------- Entry point ----------

  async function render(main) {
    // Resetear estado async entre renders para evitar valores obsoletos
    _result = null;
    _importResult = null;
    _analyzing = false;
    _busy = false;

    main.innerHTML = '<div id="wz-root">' + UI.notice('Cargando...') + '</div>';

    _restoreLocal();
    await _loadBase();
    if (!document.getElementById('wz-root')) return; // tab desmontado mientras cargaba
    _renderWizard();
  }

  function _restoreLocal() {
    const s = parseInt(localStorage.getItem(LS_STEP), 10);
    _step = (s >= 1 && s <= 5) ? s : 1;
    const ss = parseInt(localStorage.getItem(LS_SUBSTEP), 10);
    _substep = (ss >= 0) ? ss : 0;
    try {
      const a = JSON.parse(localStorage.getItem(LS_ANSWERS) || '{}');
      if (a && typeof a === 'object') _answers = a;
    } catch (_) { _answers = {}; }
    if (Array.isArray(_answers.custom_controls)) {
      _customControls = [..._answers.custom_controls];
    }
  }

  function _persistLocal() {
    localStorage.setItem(LS_STEP, String(_step));
    localStorage.setItem(LS_SUBSTEP, String(_substep));
    if (_customControls.length) _answers.custom_controls = [..._customControls];
    localStorage.setItem(LS_ANSWERS, JSON.stringify(_answers));
  }

  async function _loadBase() {
    const results = await Promise.allSettled([
      Api.aiConfig.get(),
      Api.context.get(),
      Api.aiDocuments.list(),
    ]);
    _cfg  = results[0].status === 'fulfilled' ? results[0].value
          : { model: 'claude-opus-4-5', anonymization_level: 'medium',
              setup_completed: false, has_api_key: false };
    _ctx  = results[1].status === 'fulfilled' ? (results[1].value || {}) : {};
    _docs = results[2].status === 'fulfilled' ? (results[2].value || []) : [];
  }

  async function _loadQuestions() {
    if (_questions) return;
    const data = await Api.get('/api/ai/questionnaire');
    _questions = data.questions || [];
    // Respuestas guardadas server-side (de un analisis previo) como base;
    // las respuestas locales del wizard tienen prioridad por ser mas recientes.
    if (data.saved_answers && Object.keys(data.saved_answers).length > 0) {
      _answers = { ...data.saved_answers, ..._answers };
      if (Array.isArray(_answers.custom_controls) && !_customControls.length) {
        _customControls = [..._answers.custom_controls];
      }
    }
    // Agrupar por categoria -> sub-pantallas de 2-3 preguntas
    const byCat = [];
    _questions.forEach(q => {
      let g = byCat.find(x => x.title === q.category);
      if (!g) { g = { title: q.category, questions: [] }; byCat.push(g); }
      g.questions.push(q);
    });
    _groups = byCat;
    if (_substep >= _groups.length) _substep = 0;
  }

  // ---------- Layout general ----------

  function _renderWizard() {
    const root = document.getElementById('wz-root');
    if (!root) return;
    root.innerHTML = `
      ${_renderProgress()}
      <div class="card wizard-card" id="wz-card">
        <div id="wz-body"></div>
        <div class="wizard-nav" id="wz-nav"></div>
      </div>
      <div class="wizard-later">
        <button type="button" class="btn btn-ghost" id="wz-later">Completar mas tarde</button>
      </div>`;
    document.getElementById('wz-later').onclick = _skipLater;
    _renderStep();
  }

  function _renderProgress() {
    return `
      <ol class="wizard-progress" aria-label="Progreso del asistente">
        ${STEPS.map(s => {
          const state = s.n < _step ? 'done' : (s.n === _step ? 'active' : '');
          return `
            <li class="wizard-step ${state}" ${s.n === _step ? 'aria-current="step"' : ''}>
              <span class="wizard-step-dot">${s.n < _step ? '&#10003;' : s.n}</span>
              <span class="wizard-step-label">${UI.esc(s.label)}</span>
            </li>`;
        }).join('')}
      </ol>`;
  }

  function _updateProgress() {
    const ol = document.querySelector('#wz-root .wizard-progress');
    if (ol) ol.outerHTML = _renderProgress();
  }

  async function _renderStep() {
    _persistLocal();
    _updateProgress();
    const body = document.getElementById('wz-body');
    if (!body) return;
    try {
      if (_step === 1) _renderStep1(body);
      else if (_step === 2) await _renderStep2(body);
      else if (_step === 3) _renderStep3(body);
      else if (_step === 4) _renderStep4(body);
      else _renderStep5(body);
    } catch (e) {
      body.innerHTML = `
        <div class="notice notice-error">${UI.esc(e.message)}</div>
        <button type="button" class="btn btn-primary" style="margin-top:12px;"
                onclick="ViewOnboarding._retryStep()">Reintentar</button>`;
      _renderNav({ nextDisabled: true });
      return;
    }
    // Foco al titulo del paso (accesibilidad)
    const h = document.getElementById('wz-step-title');
    if (h) h.focus();
  }

  function _retryStep() { _renderStep(); }

  function _renderNav(opts = {}) {
    const nav = document.getElementById('wz-nav');
    if (!nav) return;
    const isLast = _step === 5;
    nav.innerHTML = `
      <button type="button" class="btn btn-ghost" id="wz-prev"
              ${(_step === 1 && _substep === 0) || _busy ? 'disabled' : ''}>
        &larr; Atras
      </button>
      <span class="wizard-nav-error" id="wz-nav-error" role="alert"></span>
      ${isLast ? `
        <button type="button" class="btn btn-primary" id="wz-finish" ${_busy ? 'disabled' : ''}>
          Finalizar setup
        </button>` : `
        <button type="button" class="btn btn-primary" id="wz-next"
                ${opts.nextDisabled || _busy ? 'disabled' : ''}>
          ${UI.esc(opts.nextLabel || 'Siguiente')} &rarr;
        </button>`}`;
    const prev = document.getElementById('wz-prev');
    if (prev) prev.onclick = _prev;
    const next = document.getElementById('wz-next');
    if (next) next.onclick = _next;
    const fin = document.getElementById('wz-finish');
    if (fin) fin.onclick = _finish;
  }

  function _navError(msg) {
    const el = document.getElementById('wz-nav-error');
    if (el) el.textContent = msg || '';
  }

  function _setBusy(busy, label) {
    _busy = busy;
    ['wz-prev', 'wz-next', 'wz-finish', 'wz-later'].forEach(id => {
      const b = document.getElementById(id);
      if (b) b.disabled = busy || (id === 'wz-prev' && _step === 1 && _substep === 0);
    });
    const next = document.getElementById('wz-next') || document.getElementById('wz-finish');
    if (next && label) next.textContent = busy ? label : next.textContent;
  }

  function _stepTitle(title, hint) {
    return `
      <h2 class="wizard-step-title" id="wz-step-title" tabindex="-1">${UI.esc(title)}</h2>
      ${hint ? `<p class="wizard-step-hint">${hint}</p>` : ''}`;
  }

  function _skipLater() {
    localStorage.setItem('riskhub_onboarding_skipped', '1');
    _persistLocal();
    UI.toast('Puedes retomar el asistente desde Setup en el menu lateral', 'info');
    location.hash = '/home';
  }

  // ---------- Navegacion ----------

  async function _prev() {
    if (_busy) return;
    _navError('');
    if (_step === 2 && _substep > 0) {
      _collectSubstepAnswers();   // guardar lo escrito antes de retroceder
      _substep--;
    } else if (_step > 1) {
      if (_step === 2) _collectSubstepAnswers();
      _step--;
      if (_step === 2 && _groups.length) _substep = _groups.length - 1;
    }
    _renderStep();
  }

  async function _next() {
    if (_busy) return;
    _navError('');
    try {
      if (_step === 1) {
        if (!(await _saveStep1())) return;
        _step = 2; _substep = 0;
      } else if (_step === 2) {
        if (!_validateSubstep()) return;
        _collectSubstepAnswers();
        if (_substep < _groups.length - 1) {
          _substep++;
        } else {
          _step = 3;
        }
      } else if (_step === 3) {
        _step = 4;
      } else if (_step === 4) {
        _step = 5;
      }
      _renderStep();
    } catch (e) {
      _navError(e.message);
    }
  }

  // ============================================================
  // Paso 1 — Organizacion
  // ============================================================

  function _renderStep1(body) {
    const name  = _ctx.organization_name || '';
    const scope = _ctx.scope || '';
    body.innerHTML = `
      ${_stepTitle('Datos de la organizacion',
        'Lo imprescindible para empezar. El resto del contexto lo completara la IA con el cuestionario y tus documentos.')}
      <div class="form-grid">
        <div class="span2">
          <label for="wz-org-name">Nombre de la organizacion <span class="wizard-req">*</span></label>
          <input id="wz-org-name" type="text" maxlength="200" value="${UI.esc(name)}"
                 placeholder="Ej: Acme Iberia S.L.">
          <div class="wizard-field-error" id="wz-err-org-name" role="alert"></div>
        </div>
        <div>
          <label for="wz-sector">Sector de actividad <span class="wizard-req">*</span></label>
          <select id="wz-sector">
            <option value="">-- Seleccionar --</option>
            ${SECTORS.map(s =>
              `<option value="${UI.esc(s)}"${_cfg.org_sector === s ? ' selected' : ''}>${UI.esc(s)}</option>`
            ).join('')}
          </select>
          <div class="wizard-field-error" id="wz-err-sector" role="alert"></div>
        </div>
        <div>
          <label for="wz-size">Tamano de la organizacion <span class="wizard-req">*</span></label>
          <select id="wz-size">
            <option value="">-- Seleccionar --</option>
            ${SIZES.map(s =>
              `<option value="${UI.esc(s)}"${_cfg.org_size === s ? ' selected' : ''}>${UI.esc(s)}</option>`
            ).join('')}
          </select>
          <div class="wizard-field-error" id="wz-err-size" role="alert"></div>
        </div>
        <div class="span2">
          <label for="wz-scope">Alcance del SGSI <span class="wizard-req">*</span></label>
          <textarea id="wz-scope" rows="3"
            placeholder="Ej: Sistemas de informacion que soportan la facturacion y la atencion al cliente en la sede central...">${UI.esc(scope)}</textarea>
          <div class="wizard-field-error" id="wz-err-scope" role="alert"></div>
        </div>
      </div>`;
    _renderNav();
  }

  function _fieldError(id, msg) {
    const el = document.getElementById('wz-err-' + id);
    if (el) el.textContent = msg || '';
  }

  async function _saveStep1() {
    const name   = document.getElementById('wz-org-name').value.trim();
    const sector = document.getElementById('wz-sector').value;
    const size   = document.getElementById('wz-size').value;
    const scope  = document.getElementById('wz-scope').value.trim();

    let ok = true;
    _fieldError('org-name', name ? '' : 'Introduce el nombre de la organizacion.');
    _fieldError('sector',   sector ? '' : 'Selecciona un sector.');
    _fieldError('size',     size ? '' : 'Selecciona el tamano.');
    _fieldError('scope',    scope ? '' : 'Describe brevemente el alcance del SGSI.');
    if (!name || !sector || !size || !scope) ok = false;
    if (!ok) { _navError('Completa los campos marcados.'); return false; }

    _setBusy(true, 'Guardando...');
    try {
      // Contexto SGSI (mismo endpoint que la vista Contexto)
      _ctx = await Api.context.update({ organization_name: name, scope: scope });
      // Perfil en config IA (mismo endpoint que el onboarding anterior)
      _cfg = { ..._cfg, ...await Api.aiConfig.update({ org_sector: sector, org_size: size }) };
      return true;
    } catch (e) {
      const msg = e.status === 403
        ? 'Necesitas rol de administrador para guardar el contexto. Pide a un admin que complete el asistente.'
        : 'No se pudo guardar: ' + e.message;
      _navError(msg);
      return false;
    } finally {
      _setBusy(false);
      _renderNav();
    }
  }

  // ============================================================
  // Paso 2 — Cuestionario IA (sub-pantallas por categoria)
  // ============================================================

  async function _renderStep2(body) {
    body.innerHTML = '<div class="notice">Cargando cuestionario...</div>';
    await _loadQuestions();
    const group = _groups[_substep];
    if (!group) { _step = 3; _renderStep(); return; }

    const pct = Math.round(((_substep) / _groups.length) * 100);

    body.innerHTML = `
      ${_stepTitle('Cuestionario IA — ' + group.title,
        'Tus respuestas alimentan el analisis de riesgos ISO 27005 / MAGERIT del paso 4. Se guardan automaticamente al avanzar.')}
      <div class="wizard-substep" aria-label="Progreso del cuestionario">
        <div class="wizard-substep-bar"><div style="width:${pct}%;"></div></div>
        <span class="wizard-substep-text">Bloque ${_substep + 1} de ${_groups.length}</span>
      </div>
      ${group.questions.map(_renderQuestion).join('')}`;

    _prefillSubstep(group);
    _wireQuestionEvents();
    _renderNav({ nextLabel: _substep < _groups.length - 1 ? 'Siguiente' : 'Siguiente paso' });
  }

  function _renderQuestion(q) {
    const req = q.required ? ' <span class="wizard-req">*</span>' : '';
    let control = '';

    if (q.type === 'select') {
      control = `
        <select id="wzq-${UI.esc(q.id)}">
          <option value="">-- Selecciona --</option>
          ${(q.options || []).map(o => `<option value="${UI.esc(o)}">${UI.esc(o)}</option>`).join('')}
        </select>`;
    } else if (q.type === 'multiselect') {
      control = `
        <div class="wizard-ms-grid" id="wz-ms-${UI.esc(q.id)}">
          ${(q.options || []).map(o => `
            <label class="wizard-ms-opt">
              <input type="checkbox" data-wzq="${UI.esc(q.id)}" value="${UI.esc(o)}">
              <span>${UI.esc(o)}</span>
            </label>`).join('')}
        </div>`;
      if (q.id === 'regulations') {
        control += `
          <div id="wz-ens-wrap" class="wizard-ens-wrap" style="display:none;">
            <span class="wizard-ens-title">Nivel ENS (RD 311/2022) <span class="wizard-req">*</span></span>
            <div class="wizard-ens-opts">
              ${['basico', 'medio', 'alto'].map(lvl => `
                <label class="wizard-ens-opt">
                  <input type="radio" name="wz_ens_level" value="${lvl}">
                  ${lvl.charAt(0).toUpperCase() + lvl.slice(1)}
                </label>`).join('')}
            </div>
          </div>`;
      }
      if (q.id === 'controls_existing') {
        control += `
          <div class="wizard-custom-ctrl">
            <label for="wz-custom-ctrl-input">Anadir control adicional (no esta en la lista)</label>
            <div class="wizard-custom-ctrl-row">
              <input id="wz-custom-ctrl-input" type="text" maxlength="120"
                     placeholder="Ej: WAF, PAM, Zero Trust, cifrado de emails...">
              <button type="button" class="btn" onclick="ViewOnboarding._addCustomControl()">+ Anadir</button>
            </div>
            <div id="wz-custom-ctrl-list" class="wizard-custom-ctrl-list"></div>
          </div>`;
      }
    } else { // textarea
      control = `<textarea id="wzq-${UI.esc(q.id)}" rows="3"
        placeholder="Opcional — escribe cualquier informacion relevante..."></textarea>`;
    }

    const extra = q.allow_extra ? `
      <button type="button" class="btn btn-ghost wizard-extra-btn"
              onclick="ViewOnboarding._toggleExtra('${UI.esc(q.id)}')">+ Anadir criterio</button>
      <div id="wz-extra-wrap-${UI.esc(q.id)}" style="display:none;margin-top:8px;">
        <label for="wz-extra-${UI.esc(q.id)}" class="wizard-extra-label">Criterio adicional para el agente IA</label>
        <textarea id="wz-extra-${UI.esc(q.id)}" rows="2"
          placeholder="Contexto, restriccion o requisito relevante sobre este punto..."></textarea>
      </div>` : '';

    return `
      <div class="wizard-question" id="wz-q-${UI.esc(q.id)}">
        <label class="wizard-question-label" ${q.type !== 'multiselect' ? `for="wzq-${UI.esc(q.id)}"` : ''}>
          ${UI.esc(q.question)}${req}
        </label>
        ${control}
        ${extra}
        <div class="wizard-field-error" id="wz-qerr-${UI.esc(q.id)}" role="alert"></div>
      </div>`;
  }

  function _prefillSubstep(group) {
    group.questions.forEach(q => {
      const val = _answers[q.id];
      if (q.type === 'select' || q.type === 'textarea') {
        const el = document.getElementById('wzq-' + q.id);
        if (el && val) el.value = val;
      } else if (q.type === 'multiselect') {
        const vals = Array.isArray(val) ? val : (val ? [val] : []);
        document.querySelectorAll(`input[data-wzq="${q.id}"]`).forEach(cb => {
          cb.checked = vals.includes(cb.value);
          _highlightMsOpt(cb);
        });
      }
      if (q.allow_extra && _answers['extra_' + q.id]) {
        const wrap = document.getElementById('wz-extra-wrap-' + q.id);
        const inp  = document.getElementById('wz-extra-' + q.id);
        if (wrap) wrap.style.display = '';
        if (inp)  inp.value = _answers['extra_' + q.id];
      }
    });
    // ENS
    const ensWrap = document.getElementById('wz-ens-wrap');
    if (ensWrap) {
      const ensChecked = [...document.querySelectorAll('input[data-wzq="regulations"]:checked')]
        .some(cb => cb.value.startsWith('ENS'));
      ensWrap.style.display = ensChecked ? '' : 'none';
      if (_answers.ens_level) {
        const r = document.querySelector(`input[name="wz_ens_level"][value="${_answers.ens_level}"]`);
        if (r) r.checked = true;
      }
    }
    _renderCustomControls();
  }

  function _highlightMsOpt(cb) {
    const lbl = cb.closest('.wizard-ms-opt');
    if (lbl) lbl.classList.toggle('checked', cb.checked);
  }

  function _wireQuestionEvents() {
    document.querySelectorAll('.wizard-ms-opt input[type=checkbox]').forEach(cb => {
      cb.addEventListener('change', () => {
        _highlightMsOpt(cb);
        if (cb.dataset.wzq === 'regulations' && cb.value.startsWith('ENS')) {
          const wrap = document.getElementById('wz-ens-wrap');
          if (wrap) {
            wrap.style.display = cb.checked ? '' : 'none';
            if (!cb.checked) {
              document.querySelectorAll('input[name="wz_ens_level"]').forEach(r => r.checked = false);
            }
          }
        }
      });
    });
    const ctrlInput = document.getElementById('wz-custom-ctrl-input');
    if (ctrlInput) {
      ctrlInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); _addCustomControl(); }
      });
    }
  }

  function _toggleExtra(qId) {
    const wrap = document.getElementById('wz-extra-wrap-' + qId);
    if (!wrap) return;
    const visible = wrap.style.display !== 'none';
    wrap.style.display = visible ? 'none' : '';
    if (!visible) document.getElementById('wz-extra-' + qId)?.focus();
  }

  function _addCustomControl() {
    const input = document.getElementById('wz-custom-ctrl-input');
    const val = input ? input.value.trim() : '';
    if (!val) return;
    if (_customControls.includes(val)) { UI.toast('Ese control ya esta anadido', 'info'); return; }
    _customControls.push(val);
    input.value = '';
    _renderCustomControls();
  }

  function _removeCustomControl(idx) {
    _customControls.splice(idx, 1);
    _renderCustomControls();
  }

  function _renderCustomControls() {
    const list = document.getElementById('wz-custom-ctrl-list');
    if (!list) return;
    list.innerHTML = _customControls.map((c, i) => `
      <span class="wizard-chip">
        ${UI.esc(c)}
        <button type="button" aria-label="Quitar ${UI.esc(c)}"
                onclick="ViewOnboarding._removeCustomControl(${i})">&times;</button>
      </span>`).join('');
  }

  function _collectSubstepAnswers() {
    const group = _groups[_substep];
    if (!group) return;
    group.questions.forEach(q => {
      if (q.type === 'select' || q.type === 'textarea') {
        const el = document.getElementById('wzq-' + q.id);
        if (el) _answers[q.id] = el.value;
      } else if (q.type === 'multiselect') {
        const grid = document.getElementById('wz-ms-' + q.id);
        if (grid) {
          _answers[q.id] = [...grid.querySelectorAll('input:checked')].map(cb => cb.value);
        }
      }
      if (q.allow_extra) {
        const extra = document.getElementById('wz-extra-' + q.id);
        if (extra) {
          const v = extra.value.trim();
          if (v) _answers['extra_' + q.id] = v;
          else delete _answers['extra_' + q.id];
        }
      }
    });
    const ens = document.querySelector('input[name="wz_ens_level"]:checked');
    if (ens) _answers.ens_level = ens.value;
    else if (document.getElementById('wz-ens-wrap')) delete _answers.ens_level;
    if (_customControls.length) _answers.custom_controls = [..._customControls];
    else delete _answers.custom_controls;
    _persistLocal();
  }

  function _validateSubstep() {
    const group = _groups[_substep];
    if (!group) return true;
    let firstBad = null;
    group.questions.forEach(q => {
      let bad = false;
      if (q.required) {
        if (q.type === 'select') {
          const el = document.getElementById('wzq-' + q.id);
          bad = !el || !el.value;
        } else if (q.type === 'multiselect') {
          const grid = document.getElementById('wz-ms-' + q.id);
          bad = !grid || grid.querySelectorAll('input:checked').length === 0;
        }
      }
      const err = document.getElementById('wz-qerr-' + q.id);
      if (err) err.textContent = bad ? 'Esta pregunta es obligatoria.' : '';
      if (bad && !firstBad) firstBad = q.id;
    });
    // ENS: si se ha marcado ENS hay que elegir nivel
    const ensWrap = document.getElementById('wz-ens-wrap');
    if (ensWrap && ensWrap.style.display !== 'none') {
      const sel = document.querySelector('input[name="wz_ens_level"]:checked');
      if (!sel) {
        const err = document.getElementById('wz-qerr-regulations');
        if (err) err.textContent = 'Selecciona el nivel ENS (basico, medio o alto).';
        if (!firstBad) firstBad = 'regulations';
      }
    }
    if (firstBad) {
      _navError('Revisa las preguntas marcadas.');
      document.getElementById('wz-q-' + firstBad)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return false;
    }
    return true;
  }

  // ============================================================
  // Paso 3 — Documentos (drag & drop, vectorizacion automatica)
  // ============================================================

  function _renderStep3(body) {
    body.innerHTML = `
      ${_stepTitle('Documentos de contexto',
        'Sube politicas, inventarios, diagramas o evaluaciones previas (PDF, DOCX, TXT, CSV). ' +
        'La vectorizacion e indexado son automaticos al subir. Este paso es opcional: puedes continuar sin documentos.')}
      <div id="wz-dropzone" class="wizard-dropzone" role="button" tabindex="0"
           aria-label="Zona para arrastrar documentos o pulsar para seleccionar">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
        <div>Arrastra aqui uno o varios documentos<br>
          <span class="wizard-dropzone-hint">o pulsa para seleccionar (PDF, DOCX, TXT, CSV)</span>
        </div>
        <input type="file" id="wz-file-input" accept=".pdf,.docx,.txt,.csv" multiple
               style="display:none;" aria-hidden="true">
      </div>
      <div id="wz-upload-list"></div>
      <div id="wz-doc-list"></div>`;

    _wireDropzone();
    _renderUploadList();
    _renderDocList();
    _renderNav();
  }

  function _wireDropzone() {
    const dz = document.getElementById('wz-dropzone');
    const input = document.getElementById('wz-file-input');
    if (!dz || !input) return;
    dz.onclick = () => input.click();
    dz.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } };
    input.onchange = e => { _enqueueFiles(Array.from(e.target.files)); e.target.value = ''; };
    dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('over'); });
    dz.addEventListener('dragleave', e => { if (!dz.contains(e.relatedTarget)) dz.classList.remove('over'); });
    dz.addEventListener('drop', e => {
      e.preventDefault();
      dz.classList.remove('over');
      _enqueueFiles(Array.from(e.dataTransfer.files));
    });
  }

  // Misma heuristica de categoria que la vista de documentos IA
  function _guessCategory(filename) {
    const n = filename.toLowerCase().replace(/[_\-\.]/g, ' ');
    if (/politic|policy|procedur|instruc|manual|proceso|reglamento interno/.test(n)) return 'policies';
    if (/arquitect|topolog|diagrama|network|infraestruc|red corp|architecture/.test(n)) return 'architecture';
    if (/normativ|compliance|nis2|gdpr|rgpd|iso\s?27|directiva|reglamento|boe|legisl/.test(n)) return 'normative';
    if (/incidente|incident|postmortem|leccion|lesson|forense|analisis forense/.test(n)) return 'incidents_lessons';
    if (/inventario|inventory|activo|asset|cmdb|hardware|software|catalogo/.test(n)) return 'assets_inventory';
    if (/proveedor|supplier|vendor|tercero|contrato|sla|dpa|acuerdo/.test(n)) return 'critical_suppliers';
    if (/riesgo|risk|evaluac|assessment|amenaza|vulnerabilid|dpia|impacto/.test(n)) return 'risk_assessments';
    return 'other';
  }

  async function _enqueueFiles(files) {
    const valid = [];
    for (const f of files) {
      const ext = f.name.split('.').pop().toLowerCase();
      if (!ACCEPTED_EXTS.includes(ext)) {
        UI.toast(`${f.name}: formato no soportado. Solo PDF, DOCX, TXT, CSV.`, 'error');
        continue;
      }
      valid.push(f);
      _queue.push({ name: f.name, size: f.size, status: 'pending', error: null, _file: f });
    }
    if (!valid.length) return;
    _renderUploadList();
    if (!_uploading) await _processQueue();
  }

  async function _processQueue() {
    _uploading = true;
    _setBusy(true);
    let item;
    while ((item = _queue.find(q => q.status === 'pending'))) {
      item.status = 'uploading';
      _renderUploadList();
      try {
        await Api.aiDocuments.upload(item._file, _guessCategory(item.name));
        item.status = 'done';
      } catch (e) {
        item.status = 'error';
        item.error = e.message || 'Error desconocido';
      }
      _renderUploadList();
    }
    _uploading = false;
    _setBusy(false);
    try { _docs = await Api.aiDocuments.list(); } catch (_) { /* mantener lista previa */ }
    _renderDocList();
    _renderNav();
    const ok = _queue.filter(q => q.status === 'done').length;
    const fail = _queue.filter(q => q.status === 'error').length;
    if (ok && !fail) UI.toast(`${ok} documento${ok !== 1 ? 's' : ''} subido${ok !== 1 ? 's' : ''} — indexado automatico iniciado`, 'success');
    else if (fail) UI.toast(`${ok} subidos, ${fail} con error`, 'error');
  }

  function _renderUploadList() {
    const c = document.getElementById('wz-upload-list');
    if (!c) return;
    if (!_queue.length) { c.innerHTML = ''; return; }
    c.innerHTML = `
      <div class="wizard-upload-list" aria-live="polite">
        ${_queue.map(q => {
          const size = q.size < 1024 * 1024
            ? Math.round(q.size / 1024) + ' KB'
            : (q.size / 1024 / 1024).toFixed(1) + ' MB';
          const st = q.status === 'done'
            ? '<span class="wizard-up-ok">&#10003; Subido</span>'
            : q.status === 'error'
            ? `<span class="wizard-up-err" title="${UI.esc(q.error || '')}">&#10007; ${UI.esc(q.error || 'Error')}</span>`
            : q.status === 'uploading'
            ? '<span class="wizard-up-busy">Subiendo...</span>'
            : '<span class="wizard-up-wait">En cola</span>';
          return `
            <div class="wizard-upload-item">
              <span class="wizard-upload-name" title="${UI.esc(q.name)}">${UI.esc(q.name)}</span>
              <span class="wizard-upload-size">${size}</span>
              ${st}
            </div>`;
        }).join('')}
      </div>`;
  }

  function _renderDocList() {
    const c = document.getElementById('wz-doc-list');
    if (!c) return;
    if (!_docs.length) {
      c.innerHTML = '<p class="wizard-muted">Aun no hay documentos subidos.</p>';
      return;
    }
    const statusLabels = { indexed: 'Indexado', processing: 'Procesando', pending: 'Pendiente', error: 'Error' };
    c.innerHTML = `
      <h3 class="wizard-subhead">Documentos ya disponibles (${_docs.length})</h3>
      <div class="wizard-upload-list">
        ${_docs.map(d => `
          <div class="wizard-upload-item">
            <span class="wizard-upload-name" title="${UI.esc(d.original_name)}">${UI.esc(d.original_name)}</span>
            ${d.chunk_count ? `<span class="wizard-upload-size">${d.chunk_count} frags</span>` : ''}
            <span class="${d.status === 'indexed' ? 'wizard-up-ok' : d.status === 'error' ? 'wizard-up-err' : 'wizard-up-busy'}"
                  ${d.error_message ? `title="${UI.esc(d.error_message)}"` : ''}>
              ${statusLabels[d.status] || UI.esc(String(d.status))}
            </span>
          </div>`).join('')}
      </div>`;
  }

  // ============================================================
  // Paso 4 — Revisar propuesta (analisis IA + aceptacion)
  // ============================================================

  function _renderStep4(body) {
    if (_importResult) { _renderStep4Summary(body); return; }
    if (_result) { _renderStep4Proposal(body); return; }

    const hasKey = !!(_cfg && _cfg.has_api_key);
    body.innerHTML = `
      ${_stepTitle('Analisis y propuesta de la IA',
        'El agente analizara tus respuestas segun ISO 27005 y MAGERIT v3 y propondra activos, riesgos y controles. Suele tardar entre 30 y 60 segundos.')}
      ${!hasKey ? `
        <div class="notice notice-warn" style="margin-bottom:14px;">
          No hay API key de Anthropic configurada. Puedes introducirla ahora para lanzar el analisis,
          o saltar este paso y configurarla en el paso 5.
          <div class="wizard-inline-key">
            <label for="wz-pre-apikey">API Key de Anthropic</label>
            <div class="wizard-custom-ctrl-row">
              <input type="password" id="wz-pre-apikey" placeholder="sk-ant-api03-..." autocomplete="new-password">
              <button type="button" class="btn" id="wz-pre-apikey-save">Guardar clave</button>
            </div>
            <div class="wizard-field-error" id="wz-err-pre-apikey" role="alert"></div>
          </div>
        </div>` : ''}
      <div id="wz-analyze-zone" class="wizard-analyze-zone">
        <button type="button" class="btn btn-primary wizard-analyze-btn" id="wz-launch"
                ${!hasKey ? 'disabled' : ''}>
          Lanzar analisis IA
        </button>
        <p class="wizard-muted">Tambien puedes pulsar &ldquo;Siguiente&rdquo; para saltar el analisis y hacerlo mas tarde desde la seccion Agente IA.</p>
        <div class="wizard-field-error" id="wz-err-analyze" role="alert"></div>
      </div>`;

    const launch = document.getElementById('wz-launch');
    if (launch) launch.onclick = _launchAnalysis;
    const saveKey = document.getElementById('wz-pre-apikey-save');
    if (saveKey) saveKey.onclick = async () => {
      const key = document.getElementById('wz-pre-apikey').value.trim();
      if (!key) { _fieldError('pre-apikey', 'Introduce la API key.'); return; }
      saveKey.disabled = true; saveKey.textContent = 'Guardando...';
      try {
        _cfg = { ..._cfg, ...await Api.aiConfig.update({ api_key: key }) };
        UI.toast('API key guardada', 'success');
        _renderStep4(document.getElementById('wz-body'));
      } catch (e) {
        _fieldError('pre-apikey', 'No se pudo guardar: ' + e.message);
        saveKey.disabled = false; saveKey.textContent = 'Guardar clave';
      }
    };
    _renderNav({ nextLabel: 'Omitir y continuar' });
  }

  function _missingRequired() {
    if (!_questions) return [];
    return _questions
      .filter(q => q.required)
      .filter(q => {
        const v = _answers[q.id];
        return q.type === 'multiselect' ? !(Array.isArray(v) && v.length) : !v;
      })
      .map(q => q.question);
  }

  async function _launchAnalysis() {
    if (_analyzing) return;
    const errEl = document.getElementById('wz-err-analyze');
    try { await _loadQuestions(); } catch (e) {
      if (errEl) errEl.textContent = 'No se pudo cargar el cuestionario: ' + e.message;
      return;
    }
    const missing = _missingRequired();
    if (missing.length) {
      if (errEl) errEl.textContent =
        'Faltan respuestas obligatorias del cuestionario (paso 2): ' + missing[0].slice(0, 60) + '...';
      return;
    }

    _analyzing = true;
    _setBusy(true);
    const zone = document.getElementById('wz-analyze-zone');
    if (zone) zone.innerHTML = `
      <div class="wizard-spinner" aria-hidden="true"></div>
      <h3>Analizando el perfil de riesgo...</h3>
      <p class="wizard-muted">El agente evalua amenazas, vulnerabilidades y controles segun ISO 27005 y MAGERIT v3.</p>
      <p class="wizard-muted" id="wz-analyze-timer" aria-live="polite"></p>`;

    try {
      // Mismo flujo async + polling que la vista de cuestionario
      const { job_id } = await Api.post('/api/ai/analyze/async', { answers: _answers });
      const startMs = Date.now();
      for (;;) {
        await new Promise(r => setTimeout(r, 3000));
        const timer = document.getElementById('wz-analyze-timer');
        if (timer) timer.textContent = `Tiempo transcurrido: ${Math.round((Date.now() - startMs) / 1000)}s`;
        const data = await Api.get(`/api/ai/analyze/status/${job_id}`);
        if (data.status === 'done') { _result = data.result; break; }
        if (data.status === 'error') throw new Error(data.error || 'Error desconocido en el analisis');
      }
      _renderStep4Proposal(document.getElementById('wz-body'));
    } catch (e) {
      const z = document.getElementById('wz-analyze-zone');
      if (z) z.innerHTML = `
        <div class="notice notice-error">${UI.esc(e.message)}</div>
        <button type="button" class="btn btn-primary" style="margin-top:12px;"
                onclick="ViewOnboarding._retryStep()">Volver a intentarlo</button>`;
    } finally {
      _analyzing = false;
      _setBusy(false);
      _renderNav({ nextLabel: _result ? 'Siguiente' : 'Omitir y continuar' });
    }
  }

  function _renderStep4Proposal(body) {
    const scenarios = (_result && _result.scenarios) || [];
    const appetite = _result.risk_appetite ?? 3;
    body.innerHTML = `
      ${_stepTitle('Revisar propuesta de la IA',
        'Revisa los escenarios propuestos. Los marcados se crearan como activos y riesgos en el sistema; ' +
        'los controles ISO 27002 asociados se vincularan automaticamente.')}
      ${_result.summary ? `
        <div class="wizard-summary-box">
          <strong>Resumen del analisis</strong>
          <p>${UI.esc(_result.summary)}</p>
          <span class="wizard-muted">Apetito de riesgo propuesto: ${UI.esc(String(appetite))}/8
            &middot; Normativas: ${UI.esc(((_result.active_frameworks || []).join(', ') || '-').toUpperCase())}</span>
        </div>` : ''}
      <div class="wizard-proposal-head">
        <label class="wizard-ms-opt" style="display:inline-flex;">
          <input type="checkbox" id="wz-sel-all" checked>
          <span>Seleccionar todos (${scenarios.length})</span>
        </label>
      </div>
      <div class="wizard-proposal-list">
        ${scenarios.map((sc, i) => `
          <label class="wizard-proposal-item">
            <input type="checkbox" class="wz-sc-check" data-idx="${i}" checked>
            <span class="wizard-proposal-text">
              <strong>${UI.esc(sc.asset_suggestion || '')}</strong>
              <span class="wizard-muted"> — ${UI.esc(sc.threat_name || '')}</span><br>
              <span class="wizard-proposal-meta">
                Inherente ${UI.riskPill(sc.inherent_level)} &rarr; Residual ${UI.riskPill(sc.residual_level)}
                ${(sc.control_codes || []).slice(0, 4).map(c => `<span class="code-pill">${UI.esc(c)}</span>`).join(' ')}
                ${(sc.control_codes || []).length > 4 ? `+${sc.control_codes.length - 4}` : ''}
              </span>
            </span>
          </label>`).join('')}
      </div>
      <div class="wizard-proposal-actions">
        <button type="button" class="btn btn-primary" id="wz-accept">Aceptar seleccionados</button>
        <div class="wizard-field-error" id="wz-err-accept" role="alert"></div>
      </div>`;

    const selAll = document.getElementById('wz-sel-all');
    if (selAll) selAll.onchange = () => {
      document.querySelectorAll('.wz-sc-check').forEach(cb => { cb.checked = selAll.checked; });
    };
    const accept = document.getElementById('wz-accept');
    if (accept) accept.onclick = _acceptSelected;
    _renderNav({ nextLabel: 'Omitir y continuar' });
  }

  async function _acceptSelected() {
    const checks = [...document.querySelectorAll('.wz-sc-check:checked')];
    const errEl = document.getElementById('wz-err-accept');
    if (!checks.length) {
      if (errEl) errEl.textContent = 'Selecciona al menos un escenario o pulsa "Omitir y continuar".';
      return;
    }
    const scenarios = (_result.scenarios || []);
    const selected = checks.map(cb => scenarios[parseInt(cb.dataset.idx, 10)]).filter(Boolean);

    const btn = document.getElementById('wz-accept');
    if (btn) { btn.disabled = true; btn.textContent = 'Creando riesgos...'; }
    _setBusy(true);
    try {
      const payload = { scenarios: selected };
      if (_result.risk_appetite !== undefined && _result.risk_appetite !== null) {
        payload.risk_appetite = _result.risk_appetite;
      }
      if (_result.active_frameworks && _result.active_frameworks.length) {
        payload.active_frameworks = _result.active_frameworks;
      }
      if (_result.ens_level) payload.ens_level = _result.ens_level;
      _importResult = await Api.post('/api/ai/import', payload);
      _renderStep4Summary(document.getElementById('wz-body'));
    } catch (e) {
      if (errEl) errEl.textContent = 'No se pudieron crear los riesgos: ' + e.message;
      if (btn) { btn.disabled = false; btn.textContent = 'Aceptar seleccionados'; }
    } finally {
      _setBusy(false);
      _renderNav();
    }
  }

  function _renderStep4Summary(body) {
    const created = _importResult?.created ?? 0;
    const skipped = _importResult?.skipped ?? 0;
    body.innerHTML = `
      ${_stepTitle('Propuesta aplicada',
        'El contexto organizacional, el apetito de riesgo y las normativas quedan guardados para informes y cumplimiento.')}
      <div class="wizard-result-box">
        <div class="wizard-result-num">${created}</div>
        <div>
          <strong>riesgo${created !== 1 ? 's' : ''} creado${created !== 1 ? 's' : ''} en el registro</strong>
          ${skipped ? `<div class="wizard-muted">${skipped} escenario${skipped !== 1 ? 's' : ''} omitido${skipped !== 1 ? 's' : ''} (duplicados o sin activo/amenaza valida)</div>` : ''}
          <div class="wizard-muted">Podras revisarlos en la seccion Riesgos al terminar el asistente.</div>
        </div>
      </div>`;
    _renderNav();
  }

  // ============================================================
  // Paso 5 — Automatizaciones + API key + finalizar
  // ============================================================

  function _renderStep5(body) {
    const hasKey = !!(_cfg && _cfg.has_api_key);
    body.innerHTML = `
      ${_stepTitle('Automatizaciones activas',
        'RiskHub ejecuta estas tareas de forma automatica mediante su planificador interno. No requieren configuracion.')}
      <div class="wizard-auto-grid">
        ${AUTOMATIONS.map(a => `
          <div class="wizard-auto-card">
            <div class="wizard-auto-head">
              <strong>${UI.esc(a.title)}</strong>
              <span class="wizard-auto-badge">Activado</span>
            </div>
            <p>${UI.esc(a.desc)}</p>
          </div>`).join('')}
      </div>

      <h3 class="wizard-subhead">Agente IA</h3>
      ${hasKey ? `
        <p class="wizard-key-ok">API key de Anthropic configurada. El agente IA esta operativo.</p>
      ` : `
        <p class="wizard-muted">Introduce tu API key de Anthropic para activar el agente IA
          (chat, analisis de documentos y propuestas de riesgo).
          <a href="https://console.anthropic.com/" target="_blank" rel="noopener">Obtener clave</a>
        </p>
        <div class="form-grid">
          <div class="span2">
            <label for="wz-apikey">API Key de Anthropic</label>
            <input type="password" id="wz-apikey" placeholder="sk-ant-api03-..." autocomplete="new-password">
            <div class="wizard-field-error" id="wz-err-apikey" role="alert"></div>
          </div>
        </div>
      `}
      <div class="wizard-field-error" id="wz-err-finish" role="alert"></div>`;
    _renderNav();
  }

  async function _finish() {
    if (_busy) return;
    const errEl = document.getElementById('wz-err-finish');
    if (errEl) errEl.textContent = '';
    _setBusy(true);
    const fin = document.getElementById('wz-finish');
    if (fin) fin.textContent = 'Finalizando...';
    try {
      const payload = { setup_completed: true };
      const keyInput = document.getElementById('wz-apikey');
      if (keyInput && keyInput.value.trim()) payload.api_key = keyInput.value.trim();
      _cfg = { ..._cfg, ...await Api.aiConfig.update(payload) };

      // Mecanismo existente de app.js: marca el onboarding como hecho
      localStorage.setItem('riskhub_onboarding_done', '1');
      localStorage.removeItem('riskhub_onboarding_skipped');
      localStorage.removeItem(LS_STEP);
      localStorage.removeItem(LS_SUBSTEP);
      localStorage.removeItem(LS_ANSWERS);

      UI.toast('Setup completado. Bienvenido a RiskHub.', 'success');
      location.hash = '/home';
    } catch (e) {
      const msg = e.status === 403
        ? 'Necesitas rol de administrador para completar el setup.'
        : 'No se pudo finalizar: ' + e.message;
      if (errEl) errEl.textContent = msg;
      if (fin) fin.textContent = 'Finalizar setup';
      _setBusy(false);
      _renderNav();
    }
  }

  // Metodos invocados desde HTML inline
  return { render, _toggleExtra, _addCustomControl, _removeCustomControl, _retryStep };

})();
