/* Vigilancia digital (VisioX DRP).
 *
 * Trae a RiskHub lo que VisioX ve fuera del perimetro: dominios fraudulentos,
 * credenciales filtradas, menciones en dark web, higiene tecnica del perimetro
 * propio e identidades corporativas expuestas.
 *
 * Regla de privacidad de esta vista: los hallazgos marcados como sensibles
 * llegan del backend SIN datos personales. Para verlos hay que pulsar
 * explicitamente "Ver datos protegidos", que llama a un endpoint aparte, exige
 * rol de administracion y deja constancia en el log de auditoria. No se cachea
 * el resultado ni se vuelca al DOM fuera del modal.
 */
const ViewVisioX = (() => {

  const MODULES = {
    surfacex:  { label: 'Perimetro',    icon: '◆' },
    leakx:     { label: 'Credenciales', icon: '◆' },
    phishx:    { label: 'Suplantacion', icon: '◆' },
    darkwatch: { label: 'Dark web',     icon: '◆' },
    vipx:      { label: 'Identidades',  icon: '◆' },
  };

  const TYPE_TO_MODULE = {
    asm_tls: 'surfacex', asm_mail: 'surfacex', asm_domain: 'surfacex',
    leaked_credential: 'leakx', brand_impersonation: 'phishx',
    darkweb_mention: 'darkwatch', vip_exposure: 'vipx',
  };

  const SEV_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];

  let _state = { cfg: null, filters: { severity: '', finding_type: '', status: 'open' }, items: [], total: 0 };

  /* La severidad se codifica con color Y con texto: nunca solo color. */
  function _sevBadge(sev) {
    const v = {
      CRITICAL: 'var(--risk-critical)', HIGH: 'var(--risk-high)',
      MEDIUM: 'var(--risk-medium)', LOW: 'var(--risk-low)',
    }[sev] || '#9CA3AF';
    return `<span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;color:${v};">
      <span style="width:7px;height:7px;border-radius:50%;background:${v};flex:0 0 auto;"></span>${UI.esc(sev || '-')}</span>`;
  }

  function _kpi(label, value, color, sub) {
    return `<div style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:10px;padding:14px 16px;">
      <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em;">${UI.esc(label)}</div>
      <div style="font-size:26px;font-weight:700;color:${color || 'var(--text-primary)'};line-height:1.25;margin-top:2px;">${value}</div>
      ${sub ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${UI.esc(sub)}</div>` : ''}
    </div>`;
  }

  /* ---------- configuracion ---------- */

  function _configModal() {
    const c = _state.cfg || {};
    UI.openModal(`
      <h3 style="margin:0 0 6px;color:var(--brand-purple);">Conectar con VisioX</h3>
      <p style="font-size:13px;color:var(--text-muted);margin:0 0 16px;">
        Pega la API key de servicio emitida en VisioX. Se guarda cifrada y se valida
        antes de guardarla: veras a que cliente de VisioX pertenece.
      </p>
      <div style="display:grid;gap:14px;">
        <div>
          <label style="font-size:12px;color:var(--text-muted);display:block;margin-bottom:4px;">API key</label>
          <input id="vx-key" type="password" class="input-field" style="width:100%;font-family:monospace;"
                 placeholder="${c.configured ? 'Dejar vacio para conservar la actual' : 'vsx_...'}">
        </div>
        <label style="display:flex;gap:8px;align-items:flex-start;font-size:13px;">
          <input id="vx-assets" type="checkbox" ${c.create_assets !== false ? 'checked' : ''} style="margin-top:2px;">
          <span>Dar de alta como activos los dominios que VisioX inventaria.
            <span style="color:var(--text-muted);display:block;font-size:12px;">
              Se crean sin valoracion CIA ni propietario: eso lo decide el negocio.</span></span>
        </label>
        <label style="display:flex;gap:8px;align-items:flex-start;font-size:13px;">
          <input id="vx-auto" type="checkbox" ${c.auto_sync !== false ? 'checked' : ''} style="margin-top:2px;">
          <span>Sincronizar automaticamente cada 6 horas</span>
        </label>
        <label style="display:flex;gap:8px;align-items:flex-start;font-size:13px;">
          <input id="vx-enabled" type="checkbox" ${c.enabled !== false ? 'checked' : ''} style="margin-top:2px;">
          <span>Integracion activa</span>
        </label>
      </div>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:20px;">
        ${c.configured ? '<button class="btn btn-secondary" id="vx-del" style="margin-right:auto;">Desconectar</button>' : ''}
        <button class="btn btn-secondary" onclick="UI.closeModal()">Cancelar</button>
        <button class="btn btn-primary" id="vx-save">Guardar</button>
      </div>
      <div id="vx-msg" style="margin-top:12px;font-size:13px;"></div>
    `);

    document.getElementById('vx-save').onclick = async () => {
      const msg = document.getElementById('vx-msg');
      msg.innerHTML = '<span style="color:var(--text-muted);">Validando contra VisioX...</span>';
      try {
        const r = await Api.visiox.saveConfig({
          api_key: document.getElementById('vx-key').value.trim() || null,
          enabled: document.getElementById('vx-enabled').checked,
          create_assets: document.getElementById('vx-assets').checked,
          auto_sync: document.getElementById('vx-auto').checked,
        });
        msg.innerHTML = `<span style="color:var(--risk-low);">Conectado a ${UI.esc(r.client_name || '')}.</span>`;
        setTimeout(() => { UI.closeModal(); render(); }, 900);
      } catch (e) {
        msg.innerHTML = `<span style="color:var(--risk-critical);">${UI.esc(e.message || 'No se pudo guardar')}</span>`;
      }
    };

    const del = document.getElementById('vx-del');
    if (del) del.onclick = async () => {
      if (!confirm('Se elimina la API key guardada. Los hallazgos ya importados se conservan. Continuar?')) return;
      try { await Api.visiox.deleteConfig(); UI.closeModal(); render(); }
      catch (e) { UI.toast(e.message || 'No se pudo desconectar', 'error'); }
    };
  }

  /* ---------- evidencia protegida ---------- */

  async function _revealEvidence(id) {
    if (!confirm('Vas a ver datos personales (credenciales o identidades).\n\n' +
                 'La consulta queda registrada en el log de auditoria con tu usuario y la hora.\n\nContinuar?')) return;
    try {
      const r = await Api.visiox.evidence(id);
      const rows = Object.entries(r.evidence || {})
        .filter(([, v]) => v !== null && v !== '' && v !== undefined)
        .map(([k, v]) => `<tr>
            <td style="padding:6px 10px;color:var(--text-muted);font-size:12px;white-space:nowrap;vertical-align:top;">${UI.esc(k)}</td>
            <td style="padding:6px 10px;font-family:monospace;font-size:12px;word-break:break-all;">${UI.esc(String(v))}</td>
          </tr>`).join('');
      UI.openModal(`
        <h3 style="margin:0 0 4px;color:var(--brand-purple);">Datos protegidos</h3>
        <p style="font-size:12px;color:var(--text-muted);margin:0 0 14px;">${UI.esc(r.external_id || '')}</p>
        <div style="background:var(--bg-subtle,#faf7fd);border-left:3px solid var(--risk-high);padding:10px 12px;border-radius:0 6px 6px 0;font-size:12px;margin-bottom:14px;">
          Esta consulta ha quedado auditada. No copies estos datos a documentos sin control de acceso.
        </div>
        <table style="width:100%;border-collapse:collapse;">${rows || '<tr><td style="padding:8px;color:var(--text-muted);">Sin contenido.</td></tr>'}</table>
        <div style="display:flex;justify-content:flex-end;margin-top:18px;">
          <button class="btn btn-secondary" onclick="UI.closeModal()">Cerrar</button>
        </div>`);
    } catch (e) {
      UI.toast(e.message || 'No se pudo obtener la evidencia', 'error');
    }
  }

  /* ---------- sincronizacion ---------- */

  async function _sync(btn) {
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Sincronizando...';
    try {
      const r = await Api.visiox.sync();
      const parts = [`${r.items_read} leidos`, `${r.created} nuevos`, `${r.updated} actualizados`];
      if (r.closed) parts.push(`${r.closed} cerrados`);
      if (r.assets_created) parts.push(`${r.assets_created} activos dados de alta`);
      if (r.risks_created) parts.push(`${r.risks_created} riesgos`);
      if (r.incidents_created) parts.push(`${r.incidents_created} incidente`);
      UI.toast(parts.join(' · '), 'success');
      if (!r.complete) {
        UI.toast('El inventario llego incompleto: no se ha cerrado ningun hallazgo.', 'warning');
      }
      render();
    } catch (e) {
      UI.toast(e.message || 'Fallo la sincronizacion', 'error');
      btn.disabled = false;
      btn.textContent = original;
    }
  }

  /* ---------- render ---------- */

  async function render() {
    const el = document.getElementById('view-content') || document.getElementById('content');
    el.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-muted);">Cargando...</div>';

    try {
      _state.cfg = await Api.visiox.getConfig();
    } catch (e) {
      el.innerHTML = `<div style="padding:24px;color:var(--risk-critical);">${UI.esc(e.message || 'Error')}</div>`;
      return;
    }

    if (!_state.cfg.configured) {
      el.innerHTML = `
        <div style="max-width:620px;margin:48px auto;text-align:center;">
          <h2 style="color:var(--brand-purple);margin-bottom:8px;">Vigilancia digital</h2>
          <p style="color:var(--text-muted);font-size:14px;line-height:1.6;margin-bottom:24px;">
            Conecta VisioX para ver aqui los dominios que suplantan tu marca, las credenciales
            de tu organizacion filtradas, las menciones en dark web y la higiene tecnica de tus
            dominios, con su control ISO 27002 asociado.
          </p>
          <button class="btn btn-primary" id="vx-connect">Conectar VisioX</button>
        </div>`;
      document.getElementById('vx-connect').onclick = _configModal;
      return;
    }

    let data = { items: [], total: 0 };
    let summary = null;
    try {
      const q = { source: 'visiox', limit: 200 };
      Object.entries(_state.filters).forEach(([k, v]) => { if (v) q[k] = v; });
      data = await Api.findings.list(q);
    } catch (_) { /* la lista puede fallar sin tumbar la pagina */ }
    try { summary = await Api.findings.summary(); } catch (_) { /* opcional */ }

    _state.items = data.items || [];
    _state.total = data.total || 0;

    const bySev = {};
    const byMod = {};
    _state.items.forEach((f) => {
      bySev[f.severity] = (bySev[f.severity] || 0) + 1;
      const m = TYPE_TO_MODULE[f.finding_type] || 'surfacex';
      byMod[m] = (byMod[m] || 0) + 1;
    });

    const last = _state.cfg.last_run;
    const lastLabel = last
      ? `${last.status === 'ok' ? 'Ultima sincronizacion' : 'Ultimo intento'}: ${UI.fmtDate ? UI.fmtDate(last.started_at) : String(last.started_at).slice(0, 16).replace('T', ' ')}`
      : 'Sin sincronizar todavia';

    el.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;margin-bottom:18px;">
        <div>
          <h2 style="margin:0 0 4px;color:var(--brand-purple);">Vigilancia digital</h2>
          <div style="font-size:13px;color:var(--text-muted);">
            VisioX &middot; ${UI.esc(_state.cfg.client_name || 'cliente sin nombre')}
            <span style="opacity:.6;"> &middot; ${UI.esc(lastLabel)}</span>
          </div>
        </div>
        <div style="display:flex;gap:8px;">
          <button class="btn btn-secondary" id="vx-cfg">Configurar</button>
          <button class="btn btn-primary" id="vx-sync">Sincronizar ahora</button>
        </div>
      </div>

      ${last && last.status === 'error' ? `
        <div style="background:rgba(192,0,32,.08);border-left:3px solid var(--risk-critical);padding:12px 14px;border-radius:0 6px 6px 0;margin-bottom:16px;font-size:13px;">
          <strong>La ultima sincronizacion fallo.</strong> ${UI.esc(last.error_message || '')}
          <div style="color:var(--text-muted);font-size:12px;margin-top:4px;">
            No se ha modificado ni cerrado ningun hallazgo existente.
          </div>
        </div>` : ''}

      ${last && last.status === 'ok' && !last.complete ? `
        <div style="background:rgba(204,102,0,.08);border-left:3px solid var(--risk-medium);padding:12px 14px;border-radius:0 6px 6px 0;margin-bottom:16px;font-size:13px;">
          El ultimo inventario llego <strong>incompleto</strong>, asi que no se cerro ningun hallazgo.
          Puede haber elementos ya resueltos en origen que sigan apareciendo abiertos aqui.
        </div>` : ''}

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:16px;">
        ${_kpi('Total abiertos', _state.total, 'var(--brand-purple)')}
        ${SEV_ORDER.map((s) => _kpi(s.charAt(0) + s.slice(1).toLowerCase(), bySev[s] || 0,
            { CRITICAL: 'var(--risk-critical)', HIGH: 'var(--risk-high)',
              MEDIUM: 'var(--risk-medium)', LOW: 'var(--risk-low)' }[s])).join('')}
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:20px;">
        ${Object.entries(MODULES).map(([k, m]) => _kpi(m.label, byMod[k] || 0)).join('')}
      </div>

      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;align-items:center;">
        <select id="vx-f-sev" class="input-field" style="min-width:150px;">
          <option value="">Toda severidad</option>
          ${SEV_ORDER.map((s) => `<option value="${s}" ${_state.filters.severity === s ? 'selected' : ''}>${s}</option>`).join('')}
        </select>
        <select id="vx-f-type" class="input-field" style="min-width:170px;">
          <option value="">Todos los modulos</option>
          ${Object.entries(TYPE_TO_MODULE).map(([tp, m]) =>
            `<option value="${tp}" ${_state.filters.finding_type === tp ? 'selected' : ''}>${MODULES[m].label} — ${tp}</option>`).join('')}
        </select>
        <select id="vx-f-status" class="input-field" style="min-width:140px;">
          <option value="open" ${_state.filters.status === 'open' ? 'selected' : ''}>Abiertos</option>
          <option value="resolved" ${_state.filters.status === 'resolved' ? 'selected' : ''}>Resueltos</option>
          <option value="" ${!_state.filters.status ? 'selected' : ''}>Todos</option>
        </select>
        <span style="font-size:12px;color:var(--text-muted);margin-left:auto;">
          Mostrando ${_state.items.length} de ${_state.total}
        </span>
      </div>

      <div style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:10px;overflow:hidden;">
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead>
            <tr style="background:var(--bg-subtle,#faf7fd);text-align:left;">
              <th style="padding:10px 12px;font-size:11px;color:var(--text-muted);text-transform:uppercase;">Severidad</th>
              <th style="padding:10px 12px;font-size:11px;color:var(--text-muted);text-transform:uppercase;">Hallazgo</th>
              <th style="padding:10px 12px;font-size:11px;color:var(--text-muted);text-transform:uppercase;">Activo / host</th>
              <th style="padding:10px 12px;font-size:11px;color:var(--text-muted);text-transform:uppercase;">ISO 27002</th>
              <th style="padding:10px 12px;font-size:11px;color:var(--text-muted);text-transform:uppercase;"></th>
            </tr>
          </thead>
          <tbody>
            ${_state.items.length === 0
              ? '<tr><td colspan="5" style="padding:28px;text-align:center;color:var(--text-muted);">Sin hallazgos con estos filtros.</td></tr>'
              : _state.items.map(_row).join('')}
          </tbody>
        </table>
      </div>`;

    document.getElementById('vx-cfg').onclick = _configModal;
    document.getElementById('vx-sync').onclick = (e) => _sync(e.currentTarget);
    ['sev', 'type', 'status'].forEach((k) => {
      const map = { sev: 'severity', type: 'finding_type', status: 'status' };
      document.getElementById('vx-f-' + k).onchange = (e) => {
        _state.filters[map[k]] = e.target.value;
        render();
      };
    });
    el.querySelectorAll('[data-reveal]').forEach((b) => {
      b.onclick = () => _revealEvidence(parseInt(b.dataset.reveal, 10));
    });
  }

  function _row(f) {
    const mod = TYPE_TO_MODULE[f.finding_type] || 'surfacex';
    const ev = f.evidence || {};
    const bits = [];
    if (ev.brand) bits.push(UI.esc(ev.brand));
    if (ev.asset_class) bits.push(UI.esc(ev.asset_class));
    if (ev.critical_host) bits.push('plataforma critica');
    if (ev.unlocked) bits.push('contrasena en claro');
    if (ev.source) bits.push(UI.esc(ev.source));

    return `<tr style="border-top:1px solid var(--border-color);${f.status === 'resolved' ? 'opacity:.55;' : ''}">
      <td style="padding:10px 12px;white-space:nowrap;">${_sevBadge(f.severity)}</td>
      <td style="padding:10px 12px;">
        <div style="font-weight:500;">${UI.esc(f.title || '')}</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">
          ${UI.esc(MODULES[mod].label)}${bits.length ? ' &middot; ' + bits.join(' &middot; ') : ''}
          ${f.status === 'resolved' ? ' &middot; resuelto' : ''}
        </div>
      </td>
      <td style="padding:10px 12px;font-family:monospace;font-size:12px;word-break:break-all;">
        ${UI.esc(f.affected_host || '-')}
        ${f.asset_id ? '' : '<span style="color:var(--text-muted);font-family:inherit;font-size:11px;display:block;">sin activo inventariado</span>'}
      </td>
      <td style="padding:10px 12px;white-space:nowrap;color:var(--text-muted);">${UI.esc(f.iso_control || '-')}</td>
      <td style="padding:10px 12px;white-space:nowrap;text-align:right;">
        ${f.has_protected_evidence
          ? `<button class="btn btn-secondary" style="padding:3px 10px;font-size:11px;" data-reveal="${f.id}">Ver datos protegidos</button>`
          : ''}
        ${f.external_url
          ? `<a href="${UI.esc(f.external_url)}" target="_blank" rel="noopener noreferrer"
               style="font-size:11px;color:var(--brand-purple);margin-left:8px;">VisioX &rarr;</a>`
          : ''}
      </td>
    </tr>`;
  }

  return { render };
})();
