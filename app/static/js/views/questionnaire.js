/* Vista Agente IA — Cuestionario de contexto + análisis de riesgos ISO 27005 / MAGERIT. */
const ViewQuestionnaire = {
  _questions: null,
  _answers: {},
  _result: null,
  _selected: new Set(),

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
      this._renderForm(c);
    } catch (e) {
      c.innerHTML = UI.notice('Error al cargar el cuestionario: ' + UI.esc(e.message), 'error');
    }
  },

  _renderForm(container) {
    const qs = this._questions;
    // Agrupar por categoría
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
          <strong>MAGERIT v3</strong>, cruzando activos con amenazas y calculando niveles inherentes
          y residuales. Podrás importar los escenarios generados directamente al registro de riesgos.
        </p>
      </div>`;

    Object.entries(cats).forEach(([cat, questions]) => {
      html += `<div class="card" style="margin-bottom:16px;">
        <h3 style="margin-bottom:16px;">${catIcons[cat] || '📋'} ${cat}</h3>
        <div class="modal-body">`;

      questions.forEach(q => {
        const req = q.required ? '<span style="color:var(--brand-orange)">*</span>' : '';
        html += `<div class="span2"><label>${UI.esc(q.question)} ${req}</label>`;

        if (q.type === 'select') {
          html += `<select id="q-${q.id}" style="width:100%;">
            <option value="">— Selecciona —</option>
            ${q.options.map(o => `<option value="${UI.esc(o)}">${UI.esc(o)}</option>`).join('')}
          </select>`;
        } else if (q.type === 'multiselect') {
          html += `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-top:6px;">
            ${q.options.map(o => `
              <label class="ms-opt" style="display:flex;align-items:flex-start;gap:10px;
                     font-weight:normal;cursor:pointer;background:var(--bg-2);
                     border:1px solid var(--border);border-radius:8px;
                     padding:10px 12px;font-size:13px;line-height:1.4;transition:background .15s,border-color .15s;">
                <input type="checkbox" data-q="${q.id}" value="${UI.esc(o)}"
                       style="accent-color:var(--brand-purple);margin-top:2px;flex-shrink:0;">
                <span>${UI.esc(o)}</span>
              </label>`).join('')}
          </div>`;
        } else if (q.type === 'textarea') {
          html += `<textarea id="q-${q.id}" rows="3" style="width:100%;"
                    placeholder="Opcional — escribe cualquier información relevante..."></textarea>`;
        }

        html += `</div>`;
      });

      html += `</div></div>`;
    });

    html += `
      <div style="text-align:right;margin-top:8px;">
        <button class="btn btn-primary" id="btn-analyze" style="font-size:15px;padding:12px 32px;">
          🤖 Analizar con IA
        </button>
      </div>`;

    document.getElementById('ai-content').innerHTML = html;

    // Estilos hover en multiselect
    document.querySelectorAll('.ms-opt').forEach(label => {
      const cb = label.querySelector('input');
      cb.addEventListener('change', () => {
        label.style.background = cb.checked ? 'var(--brand-purple-4)' : 'var(--bg-2)';
        label.style.borderColor = cb.checked ? 'var(--brand-purple)' : 'var(--border)';
      });
    });

    document.getElementById('btn-analyze').onclick = () => this._submit();
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
    });

    return { answers, missing };
  },

  async _submit() {
    const { answers, missing } = this._collectAnswers();
    if (missing.length > 0) {
      UI.toast(`Completa los campos obligatorios: ${missing.slice(0,2).join(', ')}...`, 'error');
      return;
    }

    this._answers = answers;
    const c = document.getElementById('ai-content');
    c.innerHTML = `
      <div class="card" style="text-align:center;padding:48px 24px;">
        <div style="font-size:48px;margin-bottom:16px;">🤖</div>
        <h3>Analizando el perfil de riesgo...</h3>
        <p style="color:var(--text-muted);margin-top:8px;">
          El agente está evaluando amenazas, vulnerabilidades y controles aplicables<br>
          según <strong>ISO 27005</strong> y <strong>MAGERIT v3</strong>. Puede tardar 20-40 segundos.
        </p>
        <div style="margin-top:24px;" class="spinner"></div>
      </div>`;

    // Añadir estilo spinner si no existe
    if (!document.getElementById('spinner-style')) {
      const style = document.createElement('style');
      style.id = 'spinner-style';
      style.textContent = `.spinner{width:40px;height:40px;border:4px solid var(--border);
        border-top-color:var(--brand-purple);border-radius:50%;animation:spin 0.8s linear infinite;margin:0 auto;}
        @keyframes spin{to{transform:rotate(360deg)}}`;
      document.head.appendChild(style);
    }

    try {
      const result = await Api.post('/api/ai/analyze', { answers });
      this._result = result;
      this._selected = new Set(result.scenarios.map((_, i) => i));
      this._renderResults(c, result);
    } catch (e) {
      c.innerHTML = `
        <div class="notice notice-error" style="margin-bottom:16px;">${UI.esc(e.message)}</div>
        <div style="text-align:center;">
          <button class="btn btn-primary" onclick="ViewQuestionnaire.render(document.getElementById('main'))">
            Volver al cuestionario
          </button>
        </div>`;
    }
  },

  _renderResults(container, result) {
    const scenarios = result.scenarios || [];
    const levelClass = l => l >= 6 ? 'high' : l >= 3 ? 'medium' : 'low';

    let html = `
      <div class="card" style="margin-bottom:16px;border-left:4px solid var(--brand-purple);">
        <h3>Resumen ejecutivo</h3>
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

      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3>Escenarios de riesgo generados (${scenarios.length})</h3>
          <div style="display:flex;gap:8px;">
            <button class="btn btn-sm" onclick="ViewQuestionnaire._selectAll(true)">Seleccionar todo</button>
            <button class="btn btn-sm" onclick="ViewQuestionnaire._selectAll(false)">Deseleccionar todo</button>
          </div>
        </div>
        <p style="color:var(--text-muted);font-size:13px;margin-bottom:12px;">
          Selecciona los escenarios que quieres importar al registro de riesgos.
          Los activos nuevos se crearán automáticamente.
        </p>
        <div style="overflow-x:auto;">
          <table class="data">
            <thead>
              <tr>
                <th style="width:32px;"></th>
                <th>Activo</th>
                <th>Amenaza</th>
                <th>Vulnerabilidad</th>
                <th style="width:60px;text-align:center;">Inh.</th>
                <th style="width:80px;text-align:center;">Controles</th>
                <th style="width:60px;text-align:center;">Res.</th>
              </tr>
            </thead>
            <tbody>
              ${scenarios.map((sc, i) => `
                <tr id="sc-row-${i}" style="cursor:pointer;" onclick="ViewQuestionnaire._toggleRow(${i})">
                  <td><input type="checkbox" id="sc-cb-${i}" checked
                       style="accent-color:var(--brand-purple);"
                       onclick="event.stopPropagation();ViewQuestionnaire._toggleRow(${i})"></td>
                  <td>
                    <strong>${UI.esc(sc.asset_suggestion || '')}</strong>
                    <div style="font-size:11px;color:var(--text-muted);">${UI.esc(sc.asset_type || '')}</div>
                  </td>
                  <td>
                    ${sc.threat_code ? `<span class="badge badge-muted" style="font-size:10px;">${UI.esc(sc.threat_code)}</span> ` : ''}
                    ${UI.esc(sc.threat_name || '')}
                    <div style="font-size:11px;color:var(--text-muted);">dim: ${UI.esc(sc.magerit_dimension || '')}</div>
                  </td>
                  <td style="font-size:12px;color:var(--text-muted);max-width:200px;">
                    ${UI.esc(sc.vulnerability_description || '')}
                  </td>
                  <td style="text-align:center;">${UI.riskPill(sc.inherent_level)}</td>
                  <td style="text-align:center;font-size:11px;">
                    ${(sc.control_codes || []).slice(0,3).map(c =>
                      `<span class="badge badge-muted">${UI.esc(c)}</span>`).join(' ')}
                    ${(sc.control_codes || []).length > 3 ? `+${sc.control_codes.length - 3}` : ''}
                  </td>
                  <td style="text-align:center;">${UI.riskPill(sc.residual_level)}</td>
                </tr>
                <tr class="sc-detail-${i}" style="display:none;background:var(--bg-2);">
                  <td></td>
                  <td colspan="6" style="padding:8px 12px;font-size:12px;color:var(--text-muted);border-top:none;">
                    <strong>Justificación:</strong> ${UI.esc(sc.rationale || '')}
                    ${sc.control_rationale ? `<br><strong>Controles:</strong> ${UI.esc(sc.control_rationale)}` : ''}
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
        <button class="btn btn-primary" id="btn-import" style="font-size:15px;padding:12px 28px;">
          Importar riesgos seleccionados
        </button>
      </div>`;

    container.innerHTML = html;
    document.getElementById('btn-import').onclick = () => this._import(scenarios);
  },

  _toggleRow(i) {
    const cb = document.getElementById(`sc-cb-${i}`);
    const details = document.querySelectorAll(`.sc-detail-${i}`);
    if (cb) {
      cb.checked = !cb.checked;
      if (cb.checked) this._selected.add(i); else this._selected.delete(i);
    }
    details.forEach(d => d.style.display = d.style.display === 'none' ? '' : 'none');
  },

  _selectAll(val) {
    const scenarios = this._result?.scenarios || [];
    scenarios.forEach((_, i) => {
      const cb = document.getElementById(`sc-cb-${i}`);
      if (cb) cb.checked = val;
      if (val) this._selected.add(i); else this._selected.delete(i);
    });
  },

  async _import(scenarios) {
    const toImport = scenarios.filter((_, i) => {
      const cb = document.getElementById(`sc-cb-${i}`);
      return cb?.checked;
    });

    if (toImport.length === 0) {
      UI.toast('Selecciona al menos un escenario para importar', 'warn');
      return;
    }

    const btn = document.getElementById('btn-import');
    btn.disabled = true;
    btn.textContent = 'Importando...';

    try {
      const res = await Api.post('/api/ai/import', { scenarios: toImport });
      UI.toast(
        `✓ ${res.created} riesgos importados${res.skipped > 0 ? ` · ${res.skipped} omitidos` : ''}`,
        'success'
      );
      if (res.detail_skipped?.length > 0) {
        console.warn('Omitidos:', res.detail_skipped);
      }
      // Navegar a riesgos
      setTimeout(() => { App.navigate('risks'); }, 1500);
    } catch (e) {
      UI.toast('Error al importar: ' + e.message, 'error');
      btn.disabled = false;
      btn.textContent = 'Importar riesgos seleccionados';
    }
  },
};
