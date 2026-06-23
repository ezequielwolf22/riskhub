/* views/ai-chat.js - Chat conversacional con el Agente IA. */

const ViewAiChat = (() => {

  let _messages = [];   // { role, content }
  let _sending = false;
  let _lastCallLogId = null;

  // ---------- Render principal ----------

  async function render(main) {
    main.innerHTML = UI.sectionHeader(
      t('ai.chat_title'),
      t('ai_chat.subtitle')
    ) + `
      <div style="display:grid;grid-template-columns:1fr 280px;gap:16px;align-items:start;" class="ai-chat-grid">
        <div>
          <div class="card" style="padding:0;overflow:hidden;">
            <!-- Historial de mensajes -->
            <div id="chat-history" style="
              height:480px;overflow-y:auto;padding:16px;
              display:flex;flex-direction:column;gap:10px;
              background:var(--bg-1);"></div>
            <!-- Input -->
            <div style="border-top:1px solid var(--border);padding:12px;
                        background:var(--bg-0);display:flex;gap:8px;">
              <textarea id="chat-input" rows="2"
                style="flex:1;resize:none;padding:8px 10px;font-size:14px;
                       border:1px solid var(--border);border-radius:6px;
                       background:var(--bg-1);color:var(--text-base);"
                placeholder="${t('ai.placeholder')}"></textarea>
              <button class="btn btn-primary" id="chat-send"
                      style="align-self:flex-end;min-width:70px;">${t('ai.send')}</button>
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
      _appendAssistant(t('ai_chat.initial_greeting'));
    }
  }

  // ---------- Panel lateral con sugerencias ----------

  function _renderSidePanel() {
    const suggestions = [
      t('ai_chat.suggestion_0'),
      t('ai_chat.suggestion_1'),
      t('ai_chat.suggestion_2'),
      t('ai_chat.suggestion_3'),
      t('ai_chat.suggestion_4'),
      t('ai_chat.suggestion_5'),
      t('ai_chat.suggestion_6'),
      t('ai_chat.suggestion_7'),
    ];
    return `
      <div class="card" style="margin-bottom:12px;">
        <h4 style="margin:0 0 10px;font-size:12px;text-transform:uppercase;
                   color:var(--text-muted);letter-spacing:.5px;">${UI.esc(t('ai_chat.quick_questions'))}</h4>
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
                   color:var(--text-muted);letter-spacing:.5px;">${t('common.actions')}</h4>
        <button class="btn btn-ghost" style="width:100%;font-size:12px;margin-bottom:6px;"
                onclick="ViewAiChat._clearHistory()">${t('ai.clear_history')}</button>
        <a href="#/onboarding" class="btn btn-ghost"
           style="display:block;text-align:center;font-size:12px;margin-bottom:6px;">
          ${t('common.configure')} IA
        </a>
        <a href="#/ai-documents" class="btn btn-ghost"
           style="display:block;text-align:center;font-size:12px;">
          ${t('ai.documents_title')}
        </a>
      </div>`;
  }

  // ---------- Feedback widget ----------

  function _renderFeedback() {
    return `
      <div class="card" style="padding:10px 14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
        <span style="font-size:12px;color:var(--text-muted);">${t('ai.feedback_positive')}?</span>
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
    el.style.cssText = `display:flex;justify-content:${isUser ? 'flex-end' : 'flex-start'};`;
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

  // ---------- Action cards — propuestas del agente ----------

  function _buildActionCard(action) {
    const card = document.createElement('div');
    card.dataset.actionId = action.action_id;
    card.style.cssText = `
      margin-left:8px;padding:12px 14px;border-radius:10px;
      background:linear-gradient(135deg,rgba(89,0,141,.08),rgba(214,82,0,.06));
      border:1px solid rgba(89,0,141,.25);font-size:12px;
      display:flex;flex-direction:column;gap:8px;`;

    const iconMap = {
      create_treatment_task: '📋',
      update_risk_status: '🔄',
      create_incident: '⚠️',
      schedule_control_review: '🔍',
    };
    const icon = iconMap[action.action_name] || '⚡';

    card.innerHTML = `
      <div style="display:flex;align-items:flex-start;gap:8px;">
        <span style="font-size:16px;line-height:1;">${icon}</span>
        <div>
          <div style="font-weight:600;color:var(--brand-purple);margin-bottom:2px;">
            ${t('ai_chat.action_proposed')}
          </div>
          <div style="color:var(--text-base);line-height:1.5;">${UI.esc(action.label)}</div>
        </div>
      </div>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-primary" style="font-size:11px;padding:5px 14px;"
                onclick="ViewAiChat._confirmAction(this, ${JSON.stringify(action).replace(/"/g, '&quot;')})">
          ${t('common.confirm')}
        </button>
        <button class="btn btn-ghost" style="font-size:11px;padding:5px 14px;"
                onclick="ViewAiChat._rejectAction(this)">
          ${t('common.reject')}
        </button>
      </div>`;
    return card;
  }

  async function _confirmAction(btn, action) {
    btn.disabled = true;
    btn.textContent = t('common.run') || 'Ejecutando...';
    const card = btn.closest('[data-action-id]');
    try {
      const res = await Api.ai.executeAction({
        action_name: action.action_name,
        action_input: action.action_input,
      });
      // Reemplazar botones por mensaje de exito
      const btns = card.querySelector('div:last-child');
      if (btns) btns.innerHTML = `
        <span style="color:var(--risk-low);font-weight:600;font-size:12px;">
          ${t('common.success')}: ${UI.esc(res.message || 'OK')}
        </span>`;
      card.style.borderColor = 'var(--risk-low)';
      card.style.background = 'rgba(46,125,50,.06)';
      UI.toast(res.message || t('common.success'), 'success');
    } catch (e) {
      btn.disabled = false;
      btn.textContent = t('common.confirm');
      UI.toast(t('common.error') + ': ' + (e.message || 'fallo al ejecutar'), 'error');
    }
  }

  function _rejectAction(btn) {
    const card = btn.closest('[data-action-id]');
    if (card) {
      card.style.opacity = '0.4';
      card.style.pointerEvents = 'none';
      const btns = card.querySelector('div:last-child');
      if (btns) btns.innerHTML = `
        <span style="color:var(--text-muted);font-size:12px;">${t('inbox.dismiss')}</span>`;
    }
  }

  function _appendUser(text) {
    _messages.push({ role: 'user', content: text });
    const hist = document.getElementById('chat-history');
    if (hist) {
      hist.appendChild(_buildBubble('user', text));
      hist.scrollTop = hist.scrollHeight;
    }
  }

  function _appendAssistant(text, actions) {
    _messages.push({ role: 'assistant', content: text });
    const hist = document.getElementById('chat-history');
    if (!hist) return;

    // Burbuja de texto
    if (text) hist.appendChild(_buildBubble('assistant', text));

    // Action cards debajo de la burbuja
    if (actions && actions.length > 0) {
      const wrapper = document.createElement('div');
      wrapper.style.cssText = 'display:flex;flex-direction:column;gap:8px;padding-left:4px;';
      actions.forEach(a => wrapper.appendChild(_buildActionCard(a)));
      hist.appendChild(wrapper);
    }

    hist.scrollTop = hist.scrollHeight;
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
        ${t('ai.thinking')}<span id="chat-dots">.</span>
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
      _appendAssistant(res.response || '', res.actions || []);
      _lastCallLogId = res.call_log_id || null;
      // Mostrar widget de feedback solo si hay respuesta textual
      if (fb && res.response) fb.style.display = 'block';
    } catch (e) {
      _removeThinking();
      const errMsg = e.message || t('common.unknown');
      _appendAssistant(
        errMsg.includes('API key') || errMsg.includes('configurada')
          ? t('ai.not_configured')
          : t('common.error') + ': ' + errMsg
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
    _appendAssistant(t('ai_chat.history_reset'));
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
        ${t('ai_chat.rating_saved_msg', { rating })}</p>`;
      UI.toast(t('ai_chat.rating_saved'), 'success');
    } catch (e) {
      UI.toast(t('common.error'), 'error');
    }
  }

  return { render, _suggest, _clearHistory, _sendFeedback, _confirmAction, _rejectAction };

})();
