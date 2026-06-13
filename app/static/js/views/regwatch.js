/* Vista de Vigilancia Normativa Automatica (regwatch).
   Filosofia "set it and forget it": un toggle grande, un indicador de estado,
   opciones avanzadas colapsadas, inbox de cambios pendientes e historial.
   Spec: RISKHUB_REGULATORY_WATCH_MODULE_SPEC.md */
const ViewRegwatch = (() => {

  const SEV_LABELS = {
    cosmetic: 'Cosmetico', clarification: 'Aclaracion',
    substantive: 'Sustantivo', breaking: 'Version mayor',
  };
  const SEV_COLORS = {
    cosmetic: '#9CA3AF', clarification: 'var(--risk-low)',
    substantive: 'var(--risk-high)', breaking: 'var(--risk-critical)',
  };

  function _sevBadge(sev) {
    const c = SEV_COLORS[sev] || '#9CA3AF';
    return `<span style="display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600;background:${c};color:#fff;">${SEV_LABELS[sev] || sev}</span>`;
  }

  async function render(el) {
    el.innerHTML = `
      <div class="page-header">
        <div>
          <h1 class="page-title">Vigilancia Normativa Automatica</h1>
          <p class="page-sub">RiskHub mantiene tu catalogo normativo al dia. Solo te avisamos si necesitamos tu confirmacion.</p>
        </div>
      </div>
      <div id="rw-card"></div>
      <div id="rw-inbox" style="margin-top:16px;"></div>
      <div id="rw-history" style="margin-top:16px;"></div>
      <p style="font-size:12px;color:var(--text-muted);margin-top:18px;">
        Esta funcion detecta y propone cambios; no interpreta legalmente las normas ni sustituye a tu consultor o auditor.
        No procesa datos personales de tu organizacion.
      </p>
    `;
    await _load();
  }

  async function _load() {
    try {
      const [status, settings, watched] = await Promise.all([
        Api.regwatch.status(),
        Api.regwatch.getSettings(),
        Api.regwatch.watchedFrameworks(),
      ]);
      _renderCard(status, settings, watched);
      await _loadInbox();
      await _loadHistory();
    } catch (e) {
      document.getElementById('rw-card').innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  }

  function _renderCard(status, settings, watched) {
    const wrap = document.getElementById('rw-card');
    const on = status.is_enabled;
    const dotColor = !on ? '#9CA3AF' : (status.pending_count > 0 ? 'var(--brand-orange)' : 'var(--risk-low)');
    const la = status.last_applied;
    const canEdit = Auth.isAdmin();

    wrap.innerHTML = `
      <div class="card">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;">
          <div style="flex:1;min-width:260px;">
            <h3 style="margin:0 0 6px;">Vigilancia Normativa Automatica</h3>
            <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;max-width:560px;">
              RiskHub vigilara automaticamente los marcos normativos que utilizas y aplicara las actualizaciones a tu catalogo.
              Te avisaremos solo si necesitamos tu confirmacion.
            </p>
            <div style="display:flex;align-items:center;gap:8px;font-size:13px;">
              <span style="width:10px;height:10px;border-radius:50%;background:${dotColor};display:inline-block;"></span>
              <span><b>${UI.esc(status.headline)}</b></span>
              ${status.pending_count > 0 ? `<button class="btn btn-sm" id="rw-goto-inbox">Ver bandeja</button>` : ''}
            </div>
            ${la ? `<p style="font-size:12px;color:var(--text-muted);margin:8px 0 0;">Ultima actualizacion aplicada: ${UI.esc(la.framework)} — ${UI.esc(la.title)}${la.applied_at ? ' · ' + _fmtDate(la.applied_at) : ''}</p>` : ''}
          </div>
          <div style="text-align:right;">
            <label class="rw-switch" title="${canEdit ? 'Activar / desactivar' : 'Solo admin'}">
              <input type="checkbox" id="rw-toggle" ${on ? 'checked' : ''} ${canEdit ? '' : 'disabled'}>
              <span class="rw-slider"></span>
            </label>
            <div style="font-size:11px;color:var(--text-muted);margin-top:4px;">${on ? 'Activo' : 'Inactivo'}</div>
          </div>
        </div>

        <div style="margin-top:14px;border-top:1px solid var(--border);padding-top:12px;">
          <a href="#" id="rw-adv-toggle" style="font-size:13px;color:var(--brand-purple);text-decoration:none;">
            &#9656; Opciones avanzadas</a>
          <div id="rw-adv" style="display:none;margin-top:12px;"></div>
        </div>
      </div>
    `;

    // Estilos del switch (una vez)
    if (!document.getElementById('rw-switch-styles')) {
      const st = document.createElement('style');
      st.id = 'rw-switch-styles';
      st.textContent = `
        .rw-switch{position:relative;display:inline-block;width:52px;height:28px;}
        .rw-switch input{opacity:0;width:0;height:0;}
        .rw-slider{position:absolute;cursor:pointer;inset:0;background:#cbd5e1;border-radius:999px;transition:.2s;}
        .rw-slider:before{content:"";position:absolute;height:22px;width:22px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.2s;}
        .rw-switch input:checked + .rw-slider{background:var(--brand-purple);}
        .rw-switch input:checked + .rw-slider:before{transform:translateX(24px);}
        .rw-switch input:disabled + .rw-slider{opacity:.5;cursor:not-allowed;}
      `;
      document.head.appendChild(st);
    }

    const toggle = document.getElementById('rw-toggle');
    if (toggle && canEdit) {
      toggle.onchange = () => toggle.checked ? _confirmEnable(toggle, watched) : _doDisable(toggle);
    }
    const goto = document.getElementById('rw-goto-inbox');
    if (goto) goto.onclick = () => document.getElementById('rw-inbox').scrollIntoView({ behavior: 'smooth' });

    const advToggle = document.getElementById('rw-adv-toggle');
    advToggle.onclick = (e) => {
      e.preventDefault();
      const adv = document.getElementById('rw-adv');
      const open = adv.style.display === 'none';
      adv.style.display = open ? 'block' : 'none';
      advToggle.innerHTML = (open ? '&#9662; ' : '&#9656; ') + 'Opciones avanzadas';
      if (open && !adv.dataset.loaded) { _renderAdvanced(adv, settings, watched, canEdit); adv.dataset.loaded = '1'; }
    };
  }

  function _renderAdvanced(adv, settings, watched, canEdit) {
    const freqOpts = ['daily', 'weekly', 'monthly', 'never'];
    const freqLabel = { daily: 'Diaria', weekly: 'Semanal (lun 09:00)', monthly: 'Mensual', never: 'Nunca (solo criticas)' };
    adv.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
        <div>
          <label style="font-size:12px;font-weight:600;">Email para notificaciones</label>
          <input type="email" id="rw-email" value="${UI.esc(settings.notification_email || '')}" ${canEdit ? '' : 'disabled'} style="width:100%;">
        </div>
        <div>
          <label style="font-size:12px;font-weight:600;">Frecuencia del digest</label>
          <select id="rw-freq" ${canEdit ? '' : 'disabled'} style="width:100%;">
            ${freqOpts.map(f => `<option value="${f}" ${settings.digest_frequency === f ? 'selected' : ''}>${freqLabel[f]}</option>`).join('')}
          </select>
        </div>
        <div class="span2">
          <label style="font-size:13px;display:flex;align-items:center;gap:8px;cursor:pointer;">
            <input type="checkbox" id="rw-autoapply" ${settings.auto_apply_to_clones ? 'checked' : ''} ${canEdit ? '' : 'disabled'}>
            Auto-aplicar cambios no sustanciales a mis plantillas clonadas y politicas
          </label>
          <p style="font-size:11px;color:var(--text-muted);margin:4px 0 0;">Por defecto desactivado. Los cambios sustanciales siempre requieren tu confirmacion.</p>
        </div>
      </div>
      <div style="margin-top:14px;">
        <label style="font-size:12px;font-weight:600;">Frameworks vigilados (derivado automaticamente, solo lectura)</label>
        <div id="rw-frameworks" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;">
          ${watched.length ? watched.map(f => `
            <span class="badge badge-muted" title="${UI.esc((f.sources || []).join(', '))}" style="${f.muted ? 'opacity:.5;' : ''}">${UI.esc(f.label)}</span>
          `).join('') : '<span style="font-size:12px;color:var(--text-muted);">Aun no se detectan frameworks en uso. Empieza a usar el modulo Compliance o clasifica proveedores (NIS2/DORA/ENS/RGPD).</span>'}
        </div>
      </div>
      ${canEdit ? `<div style="margin-top:14px;text-align:right;"><button class="btn btn-primary btn-sm" id="rw-save-adv">Guardar opciones</button></div>` : ''}
    `;
    const save = document.getElementById('rw-save-adv');
    if (save) save.onclick = async () => {
      save.disabled = true;
      try {
        await Api.regwatch.updateSettings({
          notification_email: document.getElementById('rw-email').value || null,
          digest_frequency: document.getElementById('rw-freq').value,
          auto_apply_to_clones: document.getElementById('rw-autoapply').checked,
        });
        UI.toast('Opciones guardadas', 'success');
      } catch (e) { UI.toast(e.message, 'error'); }
      save.disabled = false;
    };
  }

  async function _confirmEnable(toggle, watched) {
    const n = watched.length;
    const ok = await UI.confirm(
      `Vamos a vigilar ${n} marco(s) normativo(s) que estas usando y a actualizar tu catalogo cuando haya cambios. ` +
      `Recibiras notificaciones solo si necesitamos tu confirmacion. ¿Activamos?`
    );
    if (!ok) { toggle.checked = false; return; }
    try {
      const r = await Api.regwatch.enable();
      UI.toast(`Vigilancia activada. Estas monitorizando ${r.watched_count} marco(s) normativo(s).`, 'success');
      await _load();
    } catch (e) { UI.toast(e.message, 'error'); toggle.checked = false; }
  }

  async function _doDisable(toggle) {
    try {
      await Api.regwatch.disable();
      UI.toast('Vigilancia desactivada. Tu configuracion se conserva.', 'info');
      await _load();
    } catch (e) { UI.toast(e.message, 'error'); toggle.checked = true; }
  }

  async function _loadInbox() {
    const wrap = document.getElementById('rw-inbox');
    try {
      const data = await Api.regwatch.inbox();
      const items = data.items || [];
      if (!items.length) { wrap.innerHTML = ''; return; }
      wrap.innerHTML = `
        <div class="card">
          <h3 style="margin-top:0;">Actualizaciones normativas pendientes (${items.length})</h3>
          ${items.map(_inboxRow).join('')}
        </div>
      `;
      items.forEach(it => {
        const rev = document.getElementById('rw-review-' + it.id);
        const snz = document.getElementById('rw-snooze-' + it.id);
        if (rev) rev.onclick = () => _openWizard(it);
        if (snz) snz.onclick = async () => {
          try { await Api.regwatch.snooze(it.id, 7); UI.toast('Aplazado 7 dias', 'info'); await _loadInbox(); await _refreshStatus(); }
          catch (e) { UI.toast(e.message, 'error'); }
        };
      });
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  function _inboxRow(it) {
    const cc = it.change_counts || {};
    const imp = it.impact || {};
    const impactTxt = `Afecta a ${imp.policies || 0} politica(s) y ${imp.compliance_requirements || 0} requisito(s) de tu cumplimiento.`;
    return `
      <div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:10px;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
          <div style="flex:1;min-width:240px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
              ${_sevBadge(it.severity)}
              <b>${UI.esc(it.framework)}${it.version_to ? ' — ' + UI.esc(it.version_to) : ''}</b>
            </div>
            <div style="font-size:13px;margin-bottom:4px;">${UI.esc(it.title)}</div>
            <div style="font-size:12px;color:var(--text-muted);">
              ${cc.modified || 0} medida(s) modificada(s), ${cc.added || 0} nueva(s), ${cc.removed || 0} eliminada(s). ${impactTxt}
            </div>
          </div>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-primary btn-sm" id="rw-review-${it.id}">Revisar</button>
            <button class="btn btn-sm" id="rw-snooze-${it.id}">Aplazar 7 dias</button>
          </div>
        </div>
      </div>
    `;
  }

  async function _openWizard(it) {
    let detail = it;
    try { detail = await Api.regwatch.inboxItem(it.id); } catch (_) { /* usa it */ }
    const imp = detail.impact || {};
    const hasImpact = (imp.policies || 0) + (imp.compliance_requirements || 0) > 0;
    const mods = detail.controls_modified || [];

    const techDetail = mods.length ? `
      <div style="margin-top:8px;font-size:12px;">
        <table class="data" style="width:100%;"><thead><tr><th>Control</th><th>Campo</th><th>Antes</th><th>Despues</th></tr></thead><tbody>
        ${mods.slice(0, 20).map(m => `<tr><td>${UI.esc(m.control_id || '')}</td><td>${UI.esc(m.field || '')}</td><td>${UI.esc(String(m.before || '').slice(0, 60))}</td><td>${UI.esc(String(m.after || '').slice(0, 60))}</td></tr>`).join('')}
        </tbody></table>
      </div>` : '';

    const body = `
      <div class="span2">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">${_sevBadge(detail.severity)}<b>${UI.esc(detail.framework)}</b></div>
        <p style="font-size:13px;">${UI.esc(detail.title)}</p>
        <p style="font-size:13px;color:var(--text-muted);">${UI.esc(detail.summary || '')}</p>
        <details style="margin-top:8px;"><summary style="cursor:pointer;font-size:13px;color:var(--brand-purple);">Ver detalle tecnico</summary>${techDetail || '<p style="font-size:12px;color:var(--text-muted);margin-top:6px;">Sin cambios atomicos detallados.</p>'}</details>
        <hr style="border:none;border-top:1px solid var(--border);margin:12px 0;">
        ${hasImpact ? `
          <p style="font-size:13px;"><b>Tus elementos afectados</b></p>
          <label style="font-size:13px;display:flex;gap:8px;align-items:center;"><input type="checkbox" id="rw-w-apply" checked> Aplicar el cambio del catalogo central (recomendado)</label>
          <p style="font-size:12px;color:var(--text-muted);margin:6px 0 0;">${imp.policies || 0} politica(s) y ${imp.compliance_requirements || 0} requisito(s) quedaran marcados como impactados para tu revision.</p>
        ` : `
          <p style="font-size:13px;color:var(--text-muted);">No tienes plantillas clonadas ni politicas afectadas. El cambio ya se aplico al catalogo central.</p>
        `}
      </div>
    `;
    UI.modal('Revisar actualizacion normativa', body, {
      actions: `<button class="btn" id="rw-w-cancel">Cancelar</button>
                <button class="btn btn-primary" id="rw-w-apply-btn">${hasImpact ? 'Aplicar' : 'Entendido'}</button>`,
    });
    document.getElementById('rw-w-cancel').onclick = UI.closeModal;
    document.getElementById('rw-w-apply-btn').onclick = async () => {
      const applyEl = document.getElementById('rw-w-apply');
      const decision = { apply_to_clones: applyEl ? applyEl.checked : false };
      try {
        await Api.regwatch.review(detail.id, decision);
        UI.toast('Cambio revisado', 'success');
        UI.closeModal();
        await _loadInbox();
        await _refreshStatus();
      } catch (e) { UI.toast(e.message, 'error'); }
    };
  }

  async function _loadHistory() {
    const wrap = document.getElementById('rw-history');
    try {
      const rows = await Api.regwatch.history();
      wrap.innerHTML = `
        <div class="card">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <h3 style="margin:0;">Historial de cambios aplicados</h3>
            ${rows.length ? `<button class="btn btn-sm" id="rw-pdf">Exportar PDF</button>` : ''}
          </div>
          ${rows.length ? `
            <table class="data" style="margin-top:10px;"><thead><tr><th>Fecha</th><th>Marco</th><th>Severidad</th><th>Cambio</th></tr></thead><tbody>
            ${rows.map(r => `<tr>
              <td>${_fmtDate(r.applied_at || r.published_at)}</td>
              <td>${UI.esc(r.framework)}</td>
              <td>${_sevBadge(r.severity)}</td>
              <td>${UI.esc(r.title)}</td>
            </tr>`).join('')}
            </tbody></table>
          ` : '<p class="text-muted" style="margin-top:8px;">Aun no se han aplicado cambios. Cuando RiskHub detecte una actualizacion de tus marcos, aparecera aqui.</p>'}
        </div>
      `;
      const pdf = document.getElementById('rw-pdf');
      if (pdf) pdf.onclick = () => Api.regwatch.historyPdf();
    } catch (e) { wrap.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`; }
  }

  async function _refreshStatus() {
    try {
      const [status, settings, watched] = await Promise.all([
        Api.regwatch.status(), Api.regwatch.getSettings(), Api.regwatch.watchedFrameworks(),
      ]);
      _renderCard(status, settings, watched);
    } catch (_) { /* silencioso */ }
  }

  function _fmtDate(iso) {
    if (!iso) return '-';
    try { return new Date(iso).toLocaleDateString('es-ES'); } catch (_) { return iso.slice(0, 10); }
  }

  return { render };
})();
