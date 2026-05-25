/* views/ai-chat.js - Chat conversacional con el Agente IA. */

const ViewAiChat = (() => {

  let _messages = [];   // { role, content }
  let _sending = false;
  let _lastCallLogId = null;

  // ---------- Render principal ----------

  async function render(main) {
    main.innerHTML = UI.sectionHeader(
      'Agente IA',
      'Consulta sobre riesgos, controles, activos e incidentes de tu organizacion.'
    ) + `
      <div style="display:grid;grid-template-columns:1fr 280px;gap:16px;align-items:start;">
        <div>
          <div class="card" style="padding:0;overflow:hidden;">
            <!-- Historial de mensajes -->
            <div id="chat-history" style="
              height:420px;overflow-y:auto;padding:16px;
              display:flex;flex-direction:column;gap:10px;
              background:var(--bg-1);"></div>
            <!-- Input -->
            <div style="border-top:1px solid var(--border);padding:12px;
                        background:var(--bg-0);display:flex;gap:8px;">
              <textarea id="chat-input" rows="2"
                style="flex:1;resize:none;padding:8px 10px;font-size:14px;
                       border:1px solid var(--border);border-radius:6px;
                       background:var(--bg-1);color:var(--text-base);"
                placeholder="Pregunta sobre riesgos, controles, activos... (Enter para enviar)"></textarea>
              <button class="btn btn-primary" id="chat-send"
                      style="align-self:flex-end;min-width:70px;">Enviar</button>
            </div>
          </div>
          <!-- Feedback -->
          <div id="chat-feedback" style="display:none;margin-top:8px;">${_renderFeedback()}</div>
        </div>
        <!-- Panel lateral -->
        <div>
          ${_renderSidePanel()}
        </div>
      </div>`;

    _wireEvents();
    _renderHistory();

    // Mensaje inicial si no hay historial
    if (_messages.length === 0) {
      _appendAssistant(
        'Hola, soy tu agente de seguridad de RiskHub. ' +
        'Puedo ayudarte a analizar riesgos, revisar el estado de controles, ' +
        'interpretar incidentes y mucho mas. ' +
        'Cuanto mas documentacion hayas subido en la configuracion, mas precisas seran mis respuestas.\n\n' +
        '¿En que puedo ayudarte hoy?'
      );
    }
  }

  // ---------- Panel lateral con sugerencias ----------

  function _renderSidePanel() {
    const suggestions = [
      'Dame un resumen del estado de riesgos criticos',
      'Que controles tienen baja madurez?',
      'Resume los incidentes recientes y lecciones aprendidas',
      'Que recomendaciones tienes para mejorar nuestra postura de seguridad?',
      'Cuales son las brechas mas importantes en nuestros controles ISO 27002?',
      'Hay proveedores criticos con riesgo elevado?',
    ];
    return `
      <div class="card" style="margin-bottom:12px;">
        <h4 style="margin:0 0 10px;font-size:12px;text-transform:uppercase;
                   color:var(--text-muted);letter-spacing:.5px;">Preguntas rapidas</h4>
        <div style="display:flex;flex-direction:column;gap:6px;">
          ${suggestions.map(s => `
            <button class="btn btn-ghost" style="text-align:left;font-size:12px;padding:7px 10px;
                    line-height:1.4;height:auto;white-space:normal;"
                    onclick="ViewAiChat._suggest(${JSON.stringify(s)})">
              ${UI.esc(s)}
            </button>`).join('')}
        </div>
      </div>
      <div class="card">
        <h4 style="margin:0 0 8px;font-size:12px;text-transform:uppercase;
                   color:var(--text-muted);letter-spacing:.5px;">Acciones</h4>
        <button class="btn btn-ghost" style="width:100%;font-size:12px;margin-bottom:6px;"
                onclick="ViewAiChat._clearHistory()">Limpiar conversacion</button>
        <a href="#/onboarding" class="btn btn-ghost"
           style="display:block;text-align:center;font-size:12px;margin-bottom:6px;">
          Configuracion IA
        </a>
        <a href="#/ai-documents" class="btn btn-ghost"
           style="display:block;text-align:center;font-size:12px;">
          Gestionar documentos
        </a>
      </div>`;
  }

  // ---------- Feedback widget ----------

  function _renderFeedback() {
    return `
      <div class="card" style="padding:10px 14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <span style="font-size:12px;color:var(--text-muted);">Fue util esta respuesta?</span>
        ${[1,2,3,4,5].map(n => `
          <button class="btn btn-ghost" style="padding:3px 8px;font-size:13px;"
                  onclick="ViewAiChat._sendFeedback(${n})" title="${n}/5">
            ${'★'.repeat(n)}${'☆'.repeat(5-n)}
          </button>`).join('')}
      </div>`;
  }

  // ---------- Renderizado de historial ----------

  function _renderHistory() {
    const hist = document.getElementById('chat-history');
    if (!hist) return;
    hist.innerHTML = '';
    _messages.forEach(m => {
      hist.appendChild(_buildBubble(m.role, m.content));
    });
    hist.scrollTop = hist.scrollHeight;
  }

  function _buildBubble(role, content) {
    const isUser = role === 'user';
    const el = document.createElement('div');
    el.style.cssText = `display:flex;justify-content:${isUser?'flex-end':'flex-start'};`;
    el.innerHTML = `
      <div style="
        max-width:80%;padding:10px 14px;border-radius:12px;font-size:13px;line-height:1.6;
        background:${isUser ? 'var(--brand-purple)' : 'var(--bg-2)'};
        color:${isUser ? '#fff' : 'var(--text-base)'};
        white-space:pre-wrap;word-break:break-word;">
        ${UI.esc(content)}
      </div>`;
    return el;
  }

  function _appendUser(text) {
    _messages.push({ role: 'user', content: text });
    const hist = document.getElementById('chat-history');
    if (hist) {
      hist.appendChild(_buildBubble('user', text));
      hist.scrollTop = hist.scrollHeight;
    }
  }

  function _appendAssistant(text) {
    _messages.push({ role: 'assistant', content: text });
    const hist = document.getElementById('chat-history');
    if (hist) {
      hist.appendChild(_buildBubble('assistant', text));
      hist.scrollTop = hist.scrollHeight;
    }
  }

  function _appendThinking() {
    const hist = document.getElementById('chat-history');
    if (!hist) return;
    const el = document.createElement('div');
    el.id = 'chat-thinking';
    el.style.cssText = 'display:flex;justify-content:flex-start;';
    el.innerHTML = `
      <div style="padding:10px 14px;border-radius:12px;background:var(--bg-2);
                  font-size:13px;color:var(--text-muted);">
        Pensando<span id="chat-dots">.</span>
      </div>`;
    hist.appendChild(el);
    hist.scrollTop = hist.scrollHeight;
    let i = 0;
    el._interval = setInterval(() => {
      const d = document.getElementById('chat-dots');
      if (d) d.textContent = '.'.repeat((++i % 3) + 1);
    }, 400);
  }

  function _removeThinking() {
    const el = document.getElementById('chat-thinking');
    if (el) {
      if (el._interval) clearInterval(el._interval);
      el.remove();
    }
  }

  // ---------- Eventos ----------

  function _wireEvents() {
    const btn = document.getElementById('chat-send');
    const inp = document.getElementById('chat-input');
    if (btn) btn.onclick = _send;
    if (inp) inp.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); _send(); }
    });
  }

  async function _send() {
    if (_sending) return;
    const inp = document.getElementById('chat-input');
    const text = (inp ? inp.value : '').trim();
    if (!text) return;
    if (inp) inp.value = '';

    _sending = true;
    const sendBtn = document.getElementById('chat-send');
    if (sendBtn) sendBtn.disabled = true;

    // Ocultar feedback del mensaje anterior
    const fb = document.getElementById('chat-feedback');
    if (fb) fb.style.display = 'none';

    _appendUser(text);
    _appendThinking();

    try {
      // Solo enviar las ultimas 10 rondas para no saturar el contexto
      const recent = _messages.slice(-20);
      const res = await Api.ai.chat({ messages: recent, max_tokens: 2048 });
      _removeThinking();
      _appendAssistant(res.response || '(Sin respuesta)');
      _lastCallLogId = res.call_log_id || null;
      // Mostrar widget de feedback
      if (fb) fb.style.display = 'block';
    } catch (e) {
      _removeThinking();
      const errMsg = e.message || 'Error desconocido';
      _appendAssistant(
        errMsg.includes('API key') || errMsg.includes('configurada')
          ? 'No hay API key configurada. Ve a Configuracion > Agente IA para añadir tu clave de Anthropic.'
          : 'Error al contactar con el agente: ' + errMsg
      );
    } finally {
      _sending = false;
      if (sendBtn) sendBtn.disabled = false;
    }
  }

  function _suggest(text) {
    const inp = document.getElementById('chat-input');
    if (inp) {
      inp.value = text;
      inp.focus();
    }
  }

  function _clearHistory() {
    _messages = [];
    _lastCallLogId = null;
    const hist = document.getElementById('chat-history');
    if (hist) hist.innerHTML = '';
    const fb = document.getElementById('chat-feedback');
    if (fb) fb.style.display = 'none';
    _appendAssistant('Conversacion reiniciada. Como puedo ayudarte?');
  }

  async function _sendFeedback(rating) {
    try {
      await Api.ai.feedback({
        call_log_id: _lastCallLogId,
        rating,
        call_type: 'chat',
      });
      const fb = document.getElementById('chat-feedback');
      if (fb) fb.innerHTML = `<p style="font-size:12px;color:var(--risk-low);padding:8px 14px;">
        Gracias por tu valoracion (${rating}/5)</p>`;
      UI.toast('Valoracion registrada', 'success');
    } catch (e) {
      UI.toast('Error al enviar valoracion', 'error');
    }
  }

  return { render, _suggest, _clearHistory, _sendFeedback };

})();
