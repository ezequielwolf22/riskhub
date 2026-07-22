/* Vista de Ingesta cognitiva — el usuario suelta un pack documental heterogeneo
   y el agente lo lee, deduce la estructura de la organizacion y vuelca las
   filas en la plataforma.

   La pieza central de esta vista NO es la tabla de resultados: es el "mapa de
   volcado" ("como lo entendi"), donde el agente declara con que clave
   descompuso cada documento. Sin eso la ingesta seria una caja negra; con eso
   una persona puede comprobar la comprension antes de fiarse de las filas.

   Consume /api/ingest (ver app/routers/ingest.py) y la cola de trabajos
   existente (/api/jobs) para el progreso. */
const ViewIngest = (() => {

  const NS = 'ingest';
  const ACCEPT = '.xlsx,.xlsm,.xls,.docx,.pdf,.txt,.csv,.md';
  const MAX_FILES = 40;
  const MAX_MB = 25;
  const JOB_TYPE = 'ingest_pack';

  // Estado de la vista. Los valores que vienen del backend (documentos del
  // cliente y salida de un LLM) se guardan aqui y se referencian por indice
  // desde el DOM: nunca se serializan dentro de un atributo HTML.
  let _files = [];
  let _estimate = null;
  let _pollTimer = null;
  let _batch = null;
  let _records = [];
  let _conflicts = [];
  let _profile = null;
  let _overrides = [];
  let _profileDraft = null;

  // ---------- helpers ----------

  function _fmtDate(iso) {
    if (!iso) return '-';
    try { return new Date(iso).toLocaleString(); } catch (e) { return String(iso); }
  }

  function _fmtBytes(n) {
    if (n == null) return '-';
    if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + ' MB';
    if (n >= 1024) return (n / 1024).toFixed(1) + ' KB';
    return n + ' B';
  }

  function _fmtNum(n) {
    const v = Number(n);
    if (!isFinite(v)) return '-';
    return v.toLocaleString();
  }

  function _cost(v) {
    const n = Number(v);
    if (!isFinite(n)) return '-';
    return '$' + (n < 0.01 ? n.toFixed(4) : n.toFixed(2));
  }

  /* Valor de origen desconocido (documento del cliente o LLM) a texto plano.
     El escapado lo hace siempre quien lo pinta con UI.esc. */
  function _val(v) {
    if (v === null || v === undefined || v === '') return '-';
    if (typeof v === 'object') {
      try { return JSON.stringify(v); } catch (e) { return String(v); }
    }
    return String(v);
  }

  /* Etiqueta traducida con fallback a la clave cruda del backend: si manana el
     motor registra una entidad nueva, la vista la muestra igualmente. */
  function _label(group, key) {
    if (!key) return '-';
    const path = `${NS}.${group}.${key}`;
    const val = t(path);
    return val === path ? String(key) : val;
  }

  function _sum(obj) {
    return Object.keys(obj || {}).reduce((a, k) => a + (Number(obj[k]) || 0), 0);
  }

  function _pct(c) {
    const n = Number(c);
    if (!isFinite(n)) return null;
    return Math.round((n <= 1 ? n * 100 : n));
  }

  function _confBadge(c) {
    const pct = _pct(c);
    if (pct === null) return '';
    const color = pct >= 80 ? 'var(--risk-low)'
      : pct >= 55 ? 'var(--brand-orange)' : 'var(--risk-high)';
    return `<span class="badge" style="background:${color};color:#fff;"
             title="${UI.esc(t('ingest.detail.confidence'))}">${pct}%</span>`;
  }

  const _STATUS_BADGE = {
    running: 'badge-medium', completed: 'badge-low',
    failed: 'badge-critical', undone: 'badge-muted',
  };

  function _statusBadge(status) {
    const cls = _STATUS_BADGE[status] || 'badge-muted';
    return `<span class="badge ${cls}">${UI.esc(_label('batch_status', status))}</span>`;
  }

  function _chips(obj) {
    const keys = Object.keys(obj || {}).filter(k => Number(obj[k]) > 0);
    if (!keys.length) return '';
    return `<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:6px;">
      ${keys.map(k => `<span class="badge badge-purple">${UI.esc(_label('entity', k))}
        <b style="margin-left:2px;">${_fmtNum(obj[k])}</b></span>`).join('')}
    </div>`;
  }

  function _stat(label, value, color) {
    return `<div style="flex:1 1 120px;min-width:120px;padding:10px 14px;
              background:var(--bg-2);border-radius:8px;">
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;
                  font-weight:700;color:var(--text-subtle);">${UI.esc(label)}</div>
      <div style="font-size:24px;font-weight:800;line-height:1.2;
                  color:${color || 'var(--text-primary)'};">${UI.esc(String(value))}</div>
    </div>`;
  }

  function _err(box, e) {
    if (box) box.innerHTML = `<div class="notice">${UI.esc(e && e.message ? e.message : String(e))}</div>`;
  }

  // ---------- render principal ----------

  async function render(el) {
    _stopPolling();
    _files = [];
    _estimate = null;
    el.innerHTML = `
      ${UI.sectionHeader(t('ingest.title'), t('ingest.subtitle'))}
      <div class="card" id="ing-upload"></div>
      <div id="ing-progress"></div>
      <div class="card" id="ing-batches"><p class="text-muted">${t('common.loading')}</p></div>
      <div id="ing-detail"></div>
      <div class="card" id="ing-profile"><p class="text-muted">${t('common.loading')}</p></div>
      <div class="card" id="ing-overrides"><p class="text-muted">${t('common.loading')}</p></div>
    `;
    _renderUpload();
    _loadBatches();
    _loadProfile();
    _loadOverrides();
    _resumeRunningJob();
  }

  // ---------- 1. Subir pack ----------

  function _renderUpload() {
    const box = document.getElementById('ing-upload');
    if (!box) return;
    box.innerHTML = `
      <h3 style="margin-top:0;">${t('ingest.upload.title')}</h3>
      <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;">${t('ingest.upload.hint')}</p>

      <div id="ing-drop" style="border:2px dashed var(--border-strong);border-radius:10px;
           padding:26px 16px;text-align:center;cursor:pointer;transition:all .15s;">
        <div style="font-size:14px;font-weight:600;">${t('ingest.upload.dropzone')}</div>
        <div style="font-size:12px;color:var(--text-subtle);margin-top:4px;">
          ${t('ingest.upload.formats')}</div>
        <div style="font-size:11px;color:var(--text-subtle);margin-top:2px;">
          ${t('ingest.upload.limits', { max: MAX_FILES, mb: MAX_MB })}</div>
      </div>
      <input type="file" id="ing-file-input" multiple accept="${ACCEPT}" style="display:none;">

      <div id="ing-file-list" style="margin-top:12px;"></div>

      <div style="display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;margin-top:14px;">
        <div>
          <label for="ing-tier">${t('ingest.upload.tier')}</label>
          <select id="ing-tier" style="min-width:230px;">
            <option value="deep">${t('ingest.upload.tier_deep')}</option>
            <option value="fast">${t('ingest.upload.tier_fast')}</option>
          </select>
        </div>
        <label style="display:flex;align-items:center;gap:8px;font-size:13px;
                      color:var(--text-primary);cursor:pointer;">
          <input type="checkbox" id="ing-apply-profile" checked>
          ${t('ingest.upload.apply_profile')}
        </label>
      </div>
      <p style="font-size:11px;color:var(--text-subtle);margin:6px 0 0;">
        ${t('ingest.upload.apply_profile_hint')}</p>

      <div style="display:flex;gap:8px;margin-top:14px;">
        <button class="btn btn-primary" id="ing-estimate-btn" disabled>${t('ingest.upload.analyze')}</button>
        <button class="btn btn-ghost" id="ing-clear-btn">${t('ingest.upload.clear')}</button>
      </div>

      <div id="ing-estimate-box" style="margin-top:14px;"></div>
    `;

    const input = document.getElementById('ing-file-input');
    const drop = document.getElementById('ing-drop');
    drop.onclick = () => input.click();
    input.onchange = (e) => { _addFiles(Array.from(e.target.files || [])); e.target.value = ''; };
    drop.addEventListener('dragover', (e) => {
      e.preventDefault();
      drop.style.borderColor = 'var(--brand-purple)';
      drop.style.background = 'var(--brand-purple-4)';
    });
    drop.addEventListener('dragleave', (e) => {
      if (drop.contains(e.relatedTarget)) return;
      drop.style.borderColor = '';
      drop.style.background = '';
    });
    drop.addEventListener('drop', (e) => {
      e.preventDefault();
      drop.style.borderColor = '';
      drop.style.background = '';
      _addFiles(Array.from((e.dataTransfer && e.dataTransfer.files) || []));
    });

    document.getElementById('ing-estimate-btn').onclick = _runEstimate;
    document.getElementById('ing-clear-btn').onclick = () => {
      _files = []; _estimate = null;
      _renderFileList();
      document.getElementById('ing-estimate-box').innerHTML = '';
    };
    _renderFileList();
  }

  function _addFiles(list) {
    list.forEach(f => {
      if (_files.length >= MAX_FILES) return;
      if (_files.some(x => x.name === f.name && x.size === f.size)) return;
      _files.push(f);
    });
    _estimate = null;
    const box = document.getElementById('ing-estimate-box');
    if (box) box.innerHTML = '';
    _renderFileList();
  }

  function _renderFileList() {
    const wrap = document.getElementById('ing-file-list');
    if (!wrap) return;
    const btn = document.getElementById('ing-estimate-btn');
    if (btn) btn.disabled = _files.length === 0;
    if (!_files.length) { wrap.innerHTML = ''; return; }
    const tooBig = _files.filter(f => f.size > MAX_MB * 1024 * 1024);
    wrap.innerHTML = `
      <div style="font-size:12px;font-weight:600;margin-bottom:6px;">
        ${t('ingest.upload.selected', { n: _files.length })}</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;">
        ${_files.map((f, i) => `
          <span class="badge badge-muted" style="gap:6px;">
            ${UI.esc(f.name)}
            <small style="opacity:.7;">${_fmtBytes(f.size)}</small>
            <button class="btn btn-ghost btn-sm" data-rm="${i}"
                    style="padding:0 4px;line-height:1;"
                    title="${UI.esc(t('ingest.upload.remove'))}">x</button>
          </span>`).join('')}
      </div>
      ${tooBig.length ? `<div class="notice notice-warn" style="margin-top:8px;">
        ${UI.esc(t('ingest.upload.too_big', { mb: MAX_MB }))}</div>` : ''}
    `;
    wrap.querySelectorAll('[data-rm]').forEach(b => {
      b.onclick = (e) => {
        e.stopPropagation();
        _files.splice(Number(b.dataset.rm), 1);
        _renderFileList();
      };
    });
  }

  function _packForm() {
    const fd = new FormData();
    _files.forEach(f => fd.append('files', f));
    return fd;
  }

  function _tier() {
    const sel = document.getElementById('ing-tier');
    return sel && sel.value === 'fast' ? 'fast' : 'deep';
  }

  async function _runEstimate() {
    const box = document.getElementById('ing-estimate-box');
    const btn = document.getElementById('ing-estimate-btn');
    if (!box) return;
    btn.disabled = true;
    box.innerHTML = `<p class="text-muted">${t('ingest.estimate.working')}</p>`;
    try {
      _estimate = await Api.req(`/api/ingest/estimate?tier=${encodeURIComponent(_tier())}`,
        { method: 'POST', body: _packForm() });
      _renderEstimate();
    } catch (e) {
      _err(box, e);
    } finally {
      btn.disabled = _files.length === 0;
    }
  }

  function _renderEstimate() {
    const box = document.getElementById('ing-estimate-box');
    if (!box || !_estimate) return;
    const d = _estimate;
    const rows = (d.documents || []).map(doc => {
      const s = doc.stats || {};
      const bits = ['sheets', 'tables', 'sections', 'blocks']
        .filter(k => Number(s[k]) > 0)
        .map(k => `${_fmtNum(s[k])} ${t('ingest.estimate.' + k)}`);
      return `<tr>
        <td>${UI.esc(doc.filename)}</td>
        <td><span class="badge badge-muted">${UI.esc(doc.format || '-')}</span></td>
        <td style="font-size:12px;color:var(--text-muted);">${UI.esc(bits.join(' · ') || '-')}</td>
        <td style="text-align:right;">${_fmtNum(doc.chars)}</td>
      </tr>`;
    }).join('');

    box.innerHTML = `
      <div style="border:1px solid var(--border);border-radius:10px;padding:14px;">
        <div style="display:flex;justify-content:space-between;align-items:baseline;
                    flex-wrap:wrap;gap:8px;">
          <h4 style="margin:0;">${t('ingest.estimate.title')}</h4>
          <div style="font-size:13px;">
            ${t('ingest.estimate.cost')}: <b>${_cost(d.estimated_cost_usd)}</b>
            <span style="color:var(--text-subtle);"> · ${t('ingest.estimate.total_chars')}:
              ${_fmtNum(d.total_chars)}</span>
          </div>
        </div>
        ${rows ? `<div style="overflow-x:auto;margin-top:10px;">
          <table class="data">
            <thead><tr>
              <th>${t('ingest.estimate.filename')}</th>
              <th>${t('ingest.estimate.format')}</th>
              <th>${t('ingest.estimate.structure')}</th>
              <th style="text-align:right;">${t('ingest.estimate.chars')}</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table></div>`
        : `<p class="text-muted" style="margin-top:10px;">${t('ingest.estimate.empty')}</p>`}

        ${(d.unsupported || []).length ? `
          <div class="notice notice-warn" style="margin-top:10px;">
            <b>${UI.esc(t('ingest.estimate.unsupported'))}</b>
            <div style="margin-top:4px;font-size:12px;">
              ${d.unsupported.map(u => UI.esc(u)).join('<br>')}</div>
            <div style="margin-top:4px;font-size:11px;">
              ${UI.esc(t('ingest.estimate.unsupported_hint'))}</div>
          </div>` : ''}

        <p style="font-size:11px;color:var(--text-subtle);margin:10px 0 0;">
          ${t('ingest.estimate.cost_hint')}</p>
        <div style="margin-top:12px;">
          <button class="btn btn-primary" id="ing-confirm-btn"
                  ${d.documents_total ? '' : 'disabled'}>
            ${t('ingest.estimate.confirm', { n: d.documents_total || 0, cost: _cost(d.estimated_cost_usd) })}
          </button>
        </div>
      </div>`;

    const btn = document.getElementById('ing-confirm-btn');
    if (btn) btn.onclick = _launchPack;
  }

  async function _launchPack() {
    const btn = document.getElementById('ing-confirm-btn');
    if (btn) btn.disabled = true;
    const applyProfile = !!(document.getElementById('ing-apply-profile') || {}).checked;
    try {
      const res = await Api.req(
        `/api/ingest/pack?tier=${encodeURIComponent(_tier())}&apply_profile=${applyProfile}`,
        { method: 'POST', body: _packForm() });
      UI.toast(res.message || t('ingest.progress.queued'), 'success');
      _files = []; _estimate = null;
      _renderFileList();
      const box = document.getElementById('ing-estimate-box');
      if (box) box.innerHTML = '';
      _startPolling(res.job_id);
    } catch (e) {
      UI.toast(e.message, 'error');
      if (btn) btn.disabled = false;
    }
  }

  // ---------- 2. Progreso ----------

  function _stopPolling() {
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
  }

  async function _resumeRunningJob() {
    try {
      const jobs = await Api.get('/api/jobs', { job_type: JOB_TYPE, limit: 5 });
      const live = (jobs || []).find(j => j.status === 'pending' || j.status === 'running');
      if (live) _startPolling(live.id);
    } catch (e) { /* silencioso: el progreso es accesorio */ }
  }

  function _startPolling(jobId) {
    _stopPolling();
    _renderProgress({ id: jobId, status: 'pending' });
    const tick = async () => {
      if (!document.getElementById('ing-progress')) { _stopPolling(); return; }
      let job;
      try { job = await Api.get('/api/jobs/' + jobId); }
      catch (e) { _stopPolling(); return; }
      _renderProgress(job);
      if (['done', 'error', 'cancelled'].indexOf(job.status) >= 0) {
        _stopPolling();
        await _loadBatches();
        const bid = job.result && job.result.batch_id;
        if (bid) _openBatch(bid);
      }
    };
    tick();
    _pollTimer = setInterval(tick, 3000);
  }

  function _renderProgress(job) {
    const box = document.getElementById('ing-progress');
    if (!box) return;
    if (!job) { box.innerHTML = ''; return; }
    const running = job.status === 'pending' || job.status === 'running';
    const msg = _label('job_status', job.status);
    box.innerHTML = `
      <div class="card" style="border-left:3px solid var(--brand-orange);">
        <div style="display:flex;justify-content:space-between;align-items:center;
                    flex-wrap:wrap;gap:10px;">
          <div>
            <div style="font-weight:700;">${t('ingest.progress.title')} — ${UI.esc(msg)}</div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:2px;">
              ${t('ingest.progress.job')} #${UI.esc(String(job.id))}
              ${job.error ? ' · <span style="color:var(--risk-high);">'
                + UI.esc(job.error) + '</span>' : ''}
            </div>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            ${running ? `<span class="badge badge-medium">${UI.esc(t('ingest.progress.working'))}</span>
              <button class="btn btn-ghost btn-sm" id="ing-cancel-job">${t('ingest.progress.cancel')}</button>`
            : `<button class="btn btn-ghost btn-sm" id="ing-hide-progress">${t('common.close')}</button>`}
          </div>
        </div>
        ${running ? `<p style="font-size:12px;color:var(--text-subtle);margin:10px 0 0;">
          ${t('ingest.progress.hint')}</p>` : ''}
      </div>`;
    const cancel = document.getElementById('ing-cancel-job');
    if (cancel) cancel.onclick = async () => {
      cancel.disabled = true;
      try { await Api.post(`/api/jobs/${job.id}/cancel`, {}); }
      catch (e) { UI.toast(e.message, 'error'); cancel.disabled = false; }
    };
    const hide = document.getElementById('ing-hide-progress');
    if (hide) hide.onclick = () => { box.innerHTML = ''; };
  }

  // ---------- 3. Lotes ----------

  async function _loadBatches() {
    const box = document.getElementById('ing-batches');
    if (!box) return;
    try {
      const batches = await Api.get('/api/ingest/batches', { limit: 25 });
      const rows = (batches || []).map(b => {
        const s = b.summary || {};
        return `<tr data-batch="${b.id}" style="cursor:pointer;">
          <td><b>#${b.id}</b></td>
          <td style="font-size:12px;">${UI.esc(_fmtDate(b.created_at))}</td>
          <td>${_statusBadge(b.status)}</td>
          <td style="text-align:right;">${(b.files || []).length}</td>
          <td style="text-align:right;">${_fmtNum(_sum(s.created))}</td>
          <td style="text-align:right;">${_fmtNum(_sum(s.updated))}</td>
          <td style="text-align:right;">${Number(s.needs_review) > 0
            ? `<span class="badge badge-medium">${_fmtNum(s.needs_review)}</span>`
            : '0'}</td>
          <td style="text-align:right;">${Number(s.conflicts) > 0
            ? `<span class="badge badge-orange">${_fmtNum(s.conflicts)}</span>`
            : '0'}</td>
          <td style="text-align:right;">${_cost(b.estimated_cost_usd)}</td>
        </tr>`;
      }).join('');
      box.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:baseline;">
          <h3 style="margin:0;">${t('ingest.batches.title')}</h3>
          <button class="btn btn-ghost btn-sm" id="ing-batches-reload">${t('common.refresh')}</button>
        </div>
        ${rows ? `<div style="overflow-x:auto;margin-top:10px;">
          <table class="data">
            <thead><tr>
              <th>${t('ingest.batches.id')}</th>
              <th>${t('ingest.batches.date')}</th>
              <th>${t('common.status')}</th>
              <th style="text-align:right;">${t('ingest.batches.files')}</th>
              <th style="text-align:right;">${t('ingest.detail.created')}</th>
              <th style="text-align:right;">${t('ingest.detail.updated')}</th>
              <th style="text-align:right;">${t('ingest.detail.needs_review')}</th>
              <th style="text-align:right;">${t('ingest.detail.conflicts')}</th>
              <th style="text-align:right;">${t('ingest.batches.cost')}</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table></div>
          <p style="font-size:11px;color:var(--text-subtle);margin:8px 0 0;">
            ${t('ingest.batches.click_hint')}</p>`
        : `<p class="text-muted" style="margin-top:10px;">${t('ingest.batches.empty')}</p>`}
      `;
      const reload = document.getElementById('ing-batches-reload');
      if (reload) reload.onclick = _loadBatches;
      box.querySelectorAll('tr[data-batch]').forEach(tr => {
        tr.onclick = () => _openBatch(Number(tr.dataset.batch));
      });
    } catch (e) {
      _err(box, e);
    }
  }

  // ---------- 4. Detalle del lote ----------

  async function _openBatch(id) {
    const box = document.getElementById('ing-detail');
    if (!box) return;
    box.innerHTML = `<div class="card"><p class="text-muted">${t('common.loading')}</p></div>`;
    try {
      _batch = await Api.get('/api/ingest/batches/' + id);
      const [records, conflicts] = await Promise.all([
        Api.get(`/api/ingest/batches/${id}/records`, { needs_review: true })
          .catch(() => []),
        Api.get('/api/ingest/conflicts', { batch_id: id }).catch(() => []),
      ]);
      _records = records || [];
      _conflicts = conflicts || [];
      _renderBatch();
      box.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (e) {
      _err(box, e);
    }
  }

  function _renderBatch() {
    const box = document.getElementById('ing-detail');
    if (!box || !_batch) return;
    const b = _batch;
    const s = b.summary || {};
    const canUndo = Auth.isAdmin() && b.status !== 'undone';
    box.innerHTML = `
      <div class="card" style="border-left:3px solid var(--brand-purple);">
        <div style="display:flex;justify-content:space-between;align-items:baseline;
                    flex-wrap:wrap;gap:10px;">
          <h3 style="margin:0;">${t('ingest.detail.title', { id: b.id })} ${_statusBadge(b.status)}</h3>
          <div style="display:flex;gap:8px;align-items:center;">
            <span style="font-size:12px;color:var(--text-muted);">
              ${UI.esc(_fmtDate(b.created_at))} · ${t('ingest.batches.cost')}:
              <b>${_cost(b.estimated_cost_usd)}</b></span>
            ${canUndo ? `<button class="btn btn-ghost btn-sm" id="ing-undo-btn"
              style="color:var(--risk-high);">${t('ingest.undo.button')}</button>` : ''}
            <button class="btn btn-ghost btn-sm" id="ing-close-detail">${t('common.close')}</button>
          </div>
        </div>
        ${b.undone_at ? `<div class="notice" style="margin-top:10px;">
          ${UI.esc(t('ingest.undo.done_at', { when: _fmtDate(b.undone_at) }))}</div>` : ''}

        <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:14px;">
          ${_stat(t('ingest.detail.created'), _fmtNum(_sum(s.created)))}
          ${_stat(t('ingest.detail.updated'), _fmtNum(_sum(s.updated)))}
          ${_stat(t('ingest.detail.linked'), _fmtNum(_sum(s.linked)))}
          ${_stat(t('ingest.detail.needs_review'), _fmtNum(s.needs_review || 0),
            Number(s.needs_review) > 0 ? 'var(--brand-orange)' : null)}
          ${_stat(t('ingest.detail.conflicts'), _fmtNum(b.conflicts_total || s.conflicts || 0),
            Number(b.conflicts_total || s.conflicts) > 0 ? 'var(--brand-orange)' : null)}
        </div>
        ${_chips(s.created)}

        ${_docsSection(b)}
      </div>

      ${_mapsSection(b)}
      ${_reviewSection()}
      ${_conflictsSection()}
      ${_gapsSection(s)}
      ${_issuesSection(s)}
    `;

    const close = document.getElementById('ing-close-detail');
    if (close) close.onclick = () => { box.innerHTML = ''; _batch = null; };
    const undo = document.getElementById('ing-undo-btn');
    if (undo) undo.onclick = () => _confirmUndo(b, s);
    _wireReview();
    _wireConflicts();
    box.querySelectorAll('[data-map-toggle]').forEach(btn => {
      btn.onclick = () => {
        const panel = document.getElementById('ing-map-' + btn.dataset.mapToggle);
        if (!panel) return;
        const open = panel.style.display !== 'none';
        panel.style.display = open ? 'none' : '';
        btn.textContent = open ? t('ingest.map.expand') : t('ingest.map.collapse');
      };
    });
  }

  function _docsSection(b) {
    const files = b.files || [];
    if (!files.length) return `<p class="text-muted" style="margin-top:14px;">${t('ingest.detail.no_docs')}</p>`;
    const rows = files.map(f => `
      <tr>
        <td>${UI.esc(f.filename)}</td>
        <td><span class="badge badge-muted">${UI.esc(f.format || '-')}</span></td>
        <td>${f.doc_kind ? `<span class="badge badge-purple">${UI.esc(_label('doc_kind', f.doc_kind))}</span>` : '-'}</td>
        <td style="text-align:center;">${_confBadge(f.confidence) || '-'}</td>
        <td style="text-align:right;">${f.units != null ? _fmtNum(f.units) : '-'}</td>
        <td style="text-align:right;">${f.rows != null ? _fmtNum(f.rows) : '-'}</td>
        <td>${f.status === 'failed'
          ? `<span class="badge badge-critical">${UI.esc(t('ingest.detail.failed'))}</span>
             <span style="font-size:11px;color:var(--risk-high);">${UI.esc(f.error || '')}</span>`
          : `<span class="badge badge-low">${UI.esc(t('ingest.detail.ok'))}</span>`}</td>
      </tr>`).join('');
    return `
      <h4 style="margin:18px 0 6px;">${t('ingest.detail.documents')}</h4>
      <div style="overflow-x:auto;">
        <table class="data">
          <thead><tr>
            <th>${t('ingest.estimate.filename')}</th>
            <th>${t('ingest.estimate.format')}</th>
            <th>${t('ingest.detail.doc_kind')}</th>
            <th style="text-align:center;">${t('ingest.detail.confidence')}</th>
            <th style="text-align:right;">${t('ingest.detail.units')}</th>
            <th style="text-align:right;">${t('ingest.detail.rows')}</th>
            <th>${t('common.status')}</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  // ---------- "Como lo entendi" ----------

  function _mapsSection(b) {
    const maps = b.source_maps || [];
    if (!maps.length) return '';
    return `
      <div class="card">
        <h3 style="margin-top:0;">${t('ingest.map.title')}</h3>
        <p style="font-size:13px;color:var(--text-muted);margin:0 0 14px;">${t('ingest.map.hint')}</p>
        ${maps.map(m => _mapCard(m)).join('')}
      </div>`;
  }

  function _mapCard(m) {
    const units = m.units_detected || [];
    const amb = m.ambiguities || [];
    return `
      <div style="border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:14px;">
        <div style="display:flex;justify-content:space-between;align-items:baseline;
                    flex-wrap:wrap;gap:8px;">
          <div>
            <div style="font-size:15px;font-weight:700;">${UI.esc(m.filename || '-')}</div>
            <div style="font-size:11px;color:var(--text-subtle);margin-top:2px;">
              ${m.doc_kind ? `<span class="badge badge-purple">${UI.esc(_label('doc_kind', m.doc_kind))}</span> ` : ''}
              ${m.sha256 ? `<span class="mono" title="${UI.esc(t('ingest.map.sha'))}">
                ${UI.esc(String(m.sha256).slice(0, 12))}</span>` : ''}
              ${m.status ? ` · ${UI.esc(_label('map_status', m.status))}` : ''}
            </div>
          </div>
          <div style="display:flex;gap:8px;align-items:center;">
            ${_confBadge(m.confidence)}
            <button class="btn btn-ghost btn-sm" data-map-toggle="${m.id}">${t('ingest.map.collapse')}</button>
          </div>
        </div>

        <div id="ing-map-${m.id}">
          ${m.rationale ? `
            <div style="margin-top:12px;padding:10px 14px;background:var(--bg-2);
                        border-radius:8px;font-size:13px;line-height:1.7;font-style:italic;">
              <div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;
                          font-weight:700;color:var(--text-subtle);font-style:normal;
                          margin-bottom:4px;">${t('ingest.map.rationale')}</div>
              ${UI.esc(m.rationale)}
            </div>` : ''}

          ${units.length ? units.map(u => _unitBlock(u)).join('')
            : `<p class="text-muted" style="margin-top:12px;">${t('ingest.map.no_units')}</p>`}

          ${amb.length ? `
            <div style="margin-top:14px;padding:12px 14px;background:var(--brand-orange-4);
                        border-left:3px solid var(--brand-orange);border-radius:0 8px 8px 0;">
              <div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;
                          font-weight:700;color:var(--brand-orange);margin-bottom:8px;">
                ${t('ingest.map.ambiguities')}</div>
              ${amb.map(a => `
                <div style="font-size:12px;line-height:1.6;margin-bottom:8px;">
                  <div><b>${UI.esc(t('ingest.map.question'))}:</b> ${UI.esc(_val(a.question))}</div>
                  <div><b>${UI.esc(t('ingest.map.chosen'))}:</b> ${UI.esc(_val(a.chosen))}</div>
                  ${a.why ? `<div style="color:var(--text-muted);">
                    <b>${UI.esc(t('ingest.map.why'))}:</b> ${UI.esc(_val(a.why))}</div>` : ''}
                </div>`).join('')}
            </div>` : ''}
        </div>
      </div>`;
  }

  function _unitBlock(u) {
    const sample = u.sample && typeof u.sample === 'object' ? u.sample : null;
    const sampleRows = sample ? Object.keys(sample).slice(0, 25).map(k => `
      <tr><td style="width:38%;font-weight:600;">${UI.esc(k)}</td>
          <td>${UI.esc(_val(sample[k]))}</td></tr>`).join('') : '';
    return `
      <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border);">
        <div style="display:flex;justify-content:space-between;align-items:baseline;
                    flex-wrap:wrap;gap:8px;">
          <div style="font-size:14px;font-weight:700;">${UI.esc(_val(u.label))}</div>
          <div style="display:flex;gap:6px;align-items:center;">
            ${_confBadge(u.confidence)}
            <span class="badge badge-purple">${UI.esc(_label('entity', u.target_entity))}</span>
            <span class="badge badge-muted">
              ${UI.esc(t('ingest.map.rows_generated', { n: Number(u.unit_count) || 0 }))}</span>
          </div>
        </div>

        <div style="background:var(--brand-purple-4);border-left:3px solid var(--brand-purple);
                    border-radius:0 8px 8px 0;padding:10px 14px;margin:10px 0;">
          <div style="font-size:10px;text-transform:uppercase;letter-spacing:.08em;
                      font-weight:700;color:var(--brand-purple);margin-bottom:4px;">
            ${t('ingest.map.decomposition_key')}</div>
          <div style="font-size:14px;line-height:1.6;">${UI.esc(_val(u.decomposition_key))}</div>
        </div>

        ${u.source_ref ? `<div style="font-size:11px;color:var(--text-subtle);">
          ${UI.esc(t('ingest.map.source_ref'))}:
          <span class="mono">${UI.esc(String(u.source_ref))}</span></div>` : ''}

        ${sampleRows ? `
          <details style="margin-top:8px;">
            <summary style="font-size:12px;cursor:pointer;color:var(--brand-purple);">
              ${UI.esc(t('ingest.map.sample'))}</summary>
            <div style="overflow-x:auto;margin-top:6px;">
              <table class="data" style="font-size:12px;"><tbody>${sampleRows}</tbody></table>
            </div>
          </details>` : ''}
      </div>`;
  }

  // ---------- 5. Revision (solo lo dudoso) ----------

  function _diff(before, after) {
    const a = after && typeof after === 'object' ? after : {};
    const bfr = before && typeof before === 'object' ? before : {};
    const keys = Object.keys(a).length ? Object.keys(a) : Object.keys(bfr);
    if (!keys.length) return '<span class="text-muted">-</span>';
    return keys.slice(0, 12).map(k => {
      const oldV = bfr[k];
      const newV = a[k];
      const changed = JSON.stringify(oldV) !== JSON.stringify(newV);
      if (oldV !== undefined && changed) {
        return `<div><b>${UI.esc(k)}:</b>
          <s style="color:var(--text-subtle);">${UI.esc(_val(oldV))}</s>
          &rarr; <span style="color:var(--brand-purple);">${UI.esc(_val(newV))}</span></div>`;
      }
      return `<div><b>${UI.esc(k)}:</b> ${UI.esc(_val(newV !== undefined ? newV : oldV))}</div>`;
    }).join('');
  }

  function _reviewSection() {
    const pending = _records.filter(r => !r.reverted_at);
    return `
      <div class="card">
        <h3 style="margin-top:0;">${t('ingest.review.title')}</h3>
        <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;">${t('ingest.review.hint')}</p>
        ${_records.length ? `<div style="overflow-x:auto;">
          <table class="data">
            <thead><tr>
              <th>${t('ingest.review.entity')}</th>
              <th>${t('ingest.review.action')}</th>
              <th style="text-align:center;">${t('ingest.detail.confidence')}</th>
              <th>${t('ingest.review.changes')}</th>
              <th></th>
            </tr></thead>
            <tbody>${_records.map((r, i) => `
              <tr${r.reverted_at ? ' style="opacity:.5;"' : ''}>
                <td>
                  <div>${UI.esc(_label('entity', r.entity))}</div>
                  <div style="font-size:11px;color:var(--text-subtle);" class="mono">
                    ${UI.esc(r.table_name || '')}#${UI.esc(String(r.record_id))}</div>
                </td>
                <td><span class="badge badge-muted">${UI.esc(_label('action', r.action))}</span></td>
                <td style="text-align:center;">${_confBadge(r.confidence) || '-'}</td>
                <td style="font-size:12px;line-height:1.6;max-width:420px;">
                  ${_diff(r.before, r.after)}</td>
                <td style="white-space:nowrap;">
                  ${r.reverted_at
                    ? `<span class="badge badge-muted">${UI.esc(t('ingest.review.reverted'))}</span>`
                    : `<button class="btn btn-ghost btn-sm" data-revert="${i}">
                        ${t('ingest.review.revert')}</button>`}
                </td>
              </tr>`).join('')}</tbody>
          </table></div>
          <p style="font-size:11px;color:var(--text-subtle);margin:8px 0 0;">
            ${t('ingest.review.count', { n: pending.length })}</p>`
        : `<p class="text-muted">${t('ingest.review.empty')}</p>`}
      </div>`;
  }

  function _wireReview() {
    document.querySelectorAll('[data-revert]').forEach(btn => {
      btn.onclick = async () => {
        const rec = _records[Number(btn.dataset.revert)];
        if (!rec) return;
        if (!confirm(t('ingest.review.confirm_revert'))) return;
        btn.disabled = true;
        try {
          await Api.post(`/api/ingest/records/${rec.id}/revert`, {});
          UI.toast(t('ingest.review.reverted_ok'), 'success');
          if (_batch) _openBatch(_batch.id);
        } catch (e) {
          UI.toast(e.message, 'error');
          btn.disabled = false;
        }
      };
    });
  }

  // ---------- 6. Conflictos ----------

  function _conflictsSection() {
    return `
      <div class="card">
        <h3 style="margin-top:0;">${t('ingest.conflicts.title')}</h3>
        <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;">${t('ingest.conflicts.hint')}</p>
        ${_conflicts.length
          ? _conflicts.map((c, i) => _conflictCard(c, i)).join('')
          : `<p class="text-muted">${t('ingest.conflicts.empty')}</p>`}
      </div>`;
  }

  function _conflictCard(c, idx) {
    const cands = c.candidates || [];
    const winner = JSON.stringify(c.resolved_value);
    return `
      <div style="border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:12px;">
        <div style="display:flex;justify-content:space-between;align-items:baseline;
                    flex-wrap:wrap;gap:8px;">
          <div>
            <div style="font-size:14px;font-weight:700;">
              ${UI.esc(_label('entity', c.entity))} ·
              <span class="mono">${UI.esc(c.field_name || '')}</span>
            </div>
            <div style="font-size:11px;color:var(--text-subtle);" class="mono">
              ${UI.esc(c.table_name || '')}#${UI.esc(String(c.record_id))}</div>
          </div>
          <div style="display:flex;gap:6px;align-items:center;">
            <span class="badge ${c.status === 'pending' ? 'badge-medium'
              : c.status === 'user_resolved' ? 'badge-purple' : 'badge-muted'}">
              ${UI.esc(_label('conflict_status', c.status))}</span>
            <span class="badge badge-muted" title="${UI.esc(_label('policy_why', c.policy))}">
              ${UI.esc(_label('policy', c.policy))}</span>
          </div>
        </div>

        <p style="font-size:12px;color:var(--text-muted);margin:8px 0 6px;">
          ${UI.esc(_label('policy_why', c.policy))}</p>

        <div style="overflow-x:auto;">
          <table class="data">
            <thead><tr>
              <th>${t('ingest.conflicts.value')}</th>
              <th>${t('ingest.conflicts.source')}</th>
              <th style="text-align:center;">${t('ingest.detail.confidence')}</th>
              <th></th>
            </tr></thead>
            <tbody>
              ${cands.map((cand, ci) => {
                const isWinner = JSON.stringify(cand.value) === winner;
                return `<tr${isWinner ? ' style="background:var(--brand-purple-4);"' : ''}>
                  <td><b>${UI.esc(_val(cand.value))}</b>
                    ${isWinner ? ` <span class="badge badge-purple">${UI.esc(t('ingest.conflicts.winner'))}</span>` : ''}</td>
                  <td style="font-size:12px;">
                    ${UI.esc(cand.source_filename || '-')}
                    ${cand.source_ref ? `<div style="font-size:11px;color:var(--text-subtle);" class="mono">
                      ${UI.esc(String(cand.source_ref))}</div>` : ''}
                    ${cand.sha256 ? `<div style="font-size:10px;color:var(--text-subtle);" class="mono">
                      ${UI.esc(String(cand.sha256).slice(0, 12))}</div>` : ''}
                  </td>
                  <td style="text-align:center;">${_confBadge(cand.confidence) || '-'}</td>
                  <td>${isWinner ? '' : `<button class="btn btn-ghost btn-sm"
                    data-cf="${idx}" data-cand="${ci}">${t('ingest.conflicts.use_this')}</button>`}</td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>

        <div style="display:flex;gap:8px;align-items:flex-end;margin-top:10px;flex-wrap:wrap;">
          <div style="flex:1 1 220px;">
            <label for="ing-cf-custom-${idx}">${t('ingest.conflicts.custom_value')}</label>
            <input type="text" id="ing-cf-custom-${idx}" style="width:100%;" maxlength="500">
          </div>
          <button class="btn btn-ghost btn-sm" data-cf-custom="${idx}">${t('ingest.conflicts.force')}</button>
        </div>
        <p style="font-size:11px;color:var(--text-subtle);margin:8px 0 0;">
          ${t('ingest.conflicts.override_note')}</p>
      </div>`;
  }

  function _wireConflicts() {
    document.querySelectorAll('[data-cf]').forEach(btn => {
      btn.onclick = () => {
        const c = _conflicts[Number(btn.dataset.cf)];
        const cand = c && (c.candidates || [])[Number(btn.dataset.cand)];
        if (!c || !cand) return;
        _resolveConflict(c, cand.value, btn);
      };
    });
    document.querySelectorAll('[data-cf-custom]').forEach(btn => {
      btn.onclick = () => {
        const idx = Number(btn.dataset.cfCustom);
        const c = _conflicts[idx];
        const input = document.getElementById('ing-cf-custom-' + idx);
        if (!c || !input) return;
        const raw = (input.value || '').trim();
        if (!raw) { UI.toast(t('ingest.conflicts.no_value'), 'error'); return; }
        // Si el valor parece numerico se envia como numero: el campo destino
        // puede ser un entero (horas de RTO) y una cadena lo rechazaria.
        const num = Number(raw);
        _resolveConflict(c, (raw !== '' && isFinite(num)) ? num : raw, btn);
      };
    });
  }

  async function _resolveConflict(conflict, value, btn) {
    if (!confirm(t('ingest.conflicts.confirm', { value: _val(value) }))) return;
    if (btn) btn.disabled = true;
    try {
      await Api.post(`/api/ingest/conflicts/${conflict.id}/resolve`, { value });
      UI.toast(t('ingest.conflicts.resolved'), 'success');
      _loadOverrides();
      if (_batch) _openBatch(_batch.id);
    } catch (e) {
      UI.toast(e.message, 'error');
      if (btn) btn.disabled = false;
    }
  }

  // ---------- 7. Huecos ----------

  function _gapsSection(summary) {
    const g = summary.gaps || {};
    const byReason = g.by_reason || {};
    const keys = Object.keys(byReason);
    return `
      <div class="card">
        <h3 style="margin-top:0;">${t('ingest.gaps.title')}</h3>
        <p style="font-size:13px;color:var(--text-muted);margin:0 0 12px;">${t('ingest.gaps.hint')}</p>
        ${keys.length ? `
          <div style="display:flex;flex-wrap:wrap;gap:10px;">
            ${keys.map(k => _stat(_label('gap', k), _fmtNum(byReason[k]), 'var(--brand-orange)')).join('')}
          </div>
          <p style="font-size:12px;color:var(--text-muted);margin:10px 0 0;">
            ${t('ingest.gaps.total', { n: _fmtNum(g.total || 0) })}
            ${g.recalculated != null ? ` · ${t('ingest.gaps.recalculated', { n: _fmtNum(g.recalculated) })}` : ''}
          </p>`
        : `<p class="text-muted">${t('ingest.gaps.empty')}</p>`}
      </div>`;
  }

  // ---------- Avisos y filas descartadas ----------

  function _issuesSection(summary) {
    const warnings = summary.warnings || [];
    const skipped = summary.skipped || [];
    if (!warnings.length && !skipped.length) return '';
    return `
      <div class="card">
        ${warnings.length ? `
          <h3 style="margin-top:0;">${t('ingest.warnings.title')}</h3>
          <ul style="font-size:12px;line-height:1.7;margin:0 0 14px;padding-left:20px;">
            ${warnings.map(w => `<li>${UI.esc(_val(w))}</li>`).join('')}
          </ul>` : ''}
        ${skipped.length ? `
          <h3 style="margin-top:${warnings.length ? '18px' : '0'};">${t('ingest.skipped.title')}</h3>
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 8px;">${t('ingest.skipped.hint')}</p>
          <div style="overflow-x:auto;">
            <table class="data">
              <thead><tr>
                <th>${t('ingest.review.entity')}</th>
                <th>${t('ingest.skipped.reason')}</th>
                <th>${t('ingest.skipped.row')}</th>
              </tr></thead>
              <tbody>${skipped.map(sk => `
                <tr>
                  <td>${UI.esc(_label('entity', sk.entity))}</td>
                  <td style="font-size:12px;">${UI.esc(_val(sk.reason))}</td>
                  <td style="font-size:11px;color:var(--text-subtle);max-width:360px;
                             overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
                      title="${UI.esc(_val(sk.row))}">${UI.esc(_val(sk.row))}</td>
                </tr>`).join('')}</tbody>
            </table>
          </div>` : ''}
      </div>`;
  }

  // ---------- 9. Deshacer el lote ----------

  function _confirmUndo(batch, summary) {
    const total = _sum(summary.created) + _sum(summary.updated) + _sum(summary.linked);
    UI.modal(t('ingest.undo.title'), `
      <p style="font-size:14px;line-height:1.7;">
        ${UI.esc(t('ingest.undo.confirm', { id: batch.id, n: total }))}</p>
      <div class="notice notice-warn">${UI.esc(t('ingest.undo.warn'))}</div>
    `, {
      actions: `<button class="btn" id="ing-undo-cancel">${t('common.cancel')}</button>
                <button class="btn btn-danger" id="ing-undo-ok">${t('ingest.undo.button')}</button>`,
    });
    document.getElementById('ing-undo-cancel').onclick = UI.closeModal;
    document.getElementById('ing-undo-ok').onclick = async () => {
      const btn = document.getElementById('ing-undo-ok');
      btn.disabled = true;
      try {
        const res = await Api.post(`/api/ingest/batches/${batch.id}/undo`, {});
        UI.closeModal();
        if (res.already_undone) UI.toast(t('ingest.undo.already'), 'info');
        else UI.toast(t('ingest.undo.ok', { n: res.reverted || 0 }), 'success');
        if ((res.failed || []).length) {
          UI.toast(t('ingest.undo.failed', { n: res.failed.length }), 'error');
        }
        await _loadBatches();
        _openBatch(batch.id);
      } catch (e) {
        UI.toast(e.message, 'error');
        btn.disabled = false;
      }
    };
  }

  // ---------- 8. Perfil de la organizacion ----------

  async function _loadProfile() {
    const box = document.getElementById('ing-profile');
    if (!box) return;
    try {
      _profile = await Api.get('/api/ingest/profile');
      _profileDraft = null;
      _renderProfile();
    } catch (e) { _err(box, e); }
  }

  function _renderProfile() {
    const box = document.getElementById('ing-profile');
    if (!box || !_profile) return;
    const p = _profile;
    if (!p.exists) {
      box.innerHTML = `
        <h3 style="margin-top:0;">${t('ingest.profile.title')}</h3>
        <p class="text-muted">${t('ingest.profile.none')}</p>`;
      return;
    }
    const structure = _profileDraft || p.structure || {};
    const locs = Array.isArray(structure.locations) ? structure.locations : [];
    const units = Array.isArray(structure.business_units) ? structure.business_units : [];
    const bcm = (p.method || {}).bcm || {};

    box.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:baseline;
                  flex-wrap:wrap;gap:8px;">
        <h3 style="margin:0;">${t('ingest.profile.title')}</h3>
        <div style="display:flex;gap:8px;align-items:center;">
          <span class="badge badge-purple">
            ${UI.esc(_label('derived', p.derived_from || 'unknown'))}</span>
          ${_confBadge(p.confidence)}
          ${p.confirmed_at ? `<span style="font-size:11px;color:var(--text-subtle);">
            ${UI.esc(t('ingest.profile.confirmed_at', { when: _fmtDate(p.confirmed_at) }))}</span>` : ''}
        </div>
      </div>
      <p style="font-size:13px;color:var(--text-muted);margin:6px 0 12px;">${t('ingest.profile.hint')}</p>

      <label for="ing-narrative">${t('ingest.profile.narrative')}</label>
      <textarea id="ing-narrative" rows="4" style="width:100%;"
                maxlength="4000">${UI.esc(p.narrative || '')}</textarea>

      <h4 style="margin:18px 0 6px;">${t('ingest.profile.locations')}</h4>
      <div style="overflow-x:auto;">
        <table class="data" id="ing-loc-table">
          <thead><tr>
            <th>${t('ingest.profile.name')}</th>
            <th>${t('ingest.profile.country')}</th>
            <th>${t('ingest.profile.city')}</th>
            <th>${t('ingest.profile.site_type')}</th>
            <th>${t('ingest.profile.staffing_model')}</th>
            <th>${t('ingest.profile.business_unit')}</th>
            <th></th>
          </tr></thead>
          <tbody>${locs.map((l, i) => _locRow(l, i)).join('')}</tbody>
        </table>
      </div>
      <button class="btn btn-ghost btn-sm" id="ing-add-loc" style="margin-top:8px;">
        ${t('ingest.profile.add_location')}</button>

      <div style="margin-top:16px;">
        <label for="ing-bus-units">${t('ingest.profile.business_units')}</label>
        <input type="text" id="ing-bus-units" style="width:100%;"
               value="${UI.esc(units.join(', '))}">
        <p style="font-size:11px;color:var(--text-subtle);margin:4px 0 0;">
          ${t('ingest.profile.business_units_hint')}</p>
      </div>

      <h4 style="margin:18px 0 6px;">${t('ingest.profile.method')}</h4>
      ${_methodSummary(bcm)}
      <details style="margin-top:8px;">
        <summary style="font-size:12px;cursor:pointer;color:var(--brand-purple);">
          ${UI.esc(t('ingest.profile.method_advanced'))}</summary>
        <textarea id="ing-method-json" rows="8" class="mono"
                  style="width:100%;margin-top:6px;font-size:12px;">${UI.esc(
          JSON.stringify(p.method || {}, null, 2))}</textarea>
        <p style="font-size:11px;color:var(--text-subtle);margin:4px 0 0;">
          ${t('ingest.profile.method_hint')}</p>
      </details>

      <div style="margin-top:14px;">
        <button class="btn btn-primary" id="ing-profile-save">${t('common.save')}</button>
      </div>`;

    _wireProfile();
  }

  function _locRow(l, i) {
    const siteTypes = ['', 'office', 'remote', 'hybrid'];
    const staffing = ['', 'internal', 'external', 'both'];
    return `
      <tr data-loc="${i}">
        <td><input type="text" data-f="name" style="width:100%;"
                   value="${UI.esc(l.name || '')}"></td>
        <td><input type="text" data-f="country" style="width:100%;"
                   value="${UI.esc(l.country || '')}"></td>
        <td><input type="text" data-f="city" style="width:100%;"
                   value="${UI.esc(l.city || '')}"></td>
        <td><select data-f="site_type">
          ${siteTypes.map(v => `<option value="${UI.esc(v)}"
            ${l.site_type === v ? 'selected' : ''}>
            ${v ? UI.esc(_label('site_type', v)) : '-'}</option>`).join('')}
        </select></td>
        <td><select data-f="staffing_model">
          ${staffing.map(v => `<option value="${UI.esc(v)}"
            ${l.staffing_model === v ? 'selected' : ''}>
            ${v ? UI.esc(_label('staffing', v)) : '-'}</option>`).join('')}
        </select></td>
        <td><input type="text" data-f="business_unit" style="width:100%;"
                   value="${UI.esc(l.business_unit || '')}"></td>
        <td><button class="btn btn-ghost btn-sm" data-rm-loc="${i}">${t('common.delete')}</button></td>
      </tr>`;
  }

  function _methodSummary(bcm) {
    const dims = (bcm.dimensions || []).map(d =>
      `<span class="badge badge-muted">${UI.esc(d.label || d.key || '')}</span>`).join(' ');
    const horizons = (bcm.horizons || []).map(h =>
      `<span class="badge badge-muted">${UI.esc(_val(h))}</span>`).join(' ');
    const rto = (bcm.rto_scale || []).map(r =>
      `<span class="badge badge-muted">${UI.esc(r.label || '')}${r.hours != null
        ? ' (' + UI.esc(String(r.hours)) + 'h)' : ''}</span>`).join(' ');
    const bands = (bcm.bands || []).map(b =>
      `<span class="badge badge-muted">${UI.esc(b.label || b.key || '')}</span>`).join(' ');
    const rows = [
      [t('ingest.profile.dimensions'), dims],
      [t('ingest.profile.horizons'), horizons],
      [t('ingest.profile.rto_scale'), rto],
      [t('ingest.profile.bands'), bands],
      [t('ingest.profile.aggregation'), bcm.aggregation ? UI.esc(String(bcm.aggregation)) : ''],
    ].filter(r => r[1]);
    if (!rows.length) return `<p class="text-muted">${t('ingest.profile.method_empty')}</p>`;
    return `<div style="display:grid;gap:6px;">
      ${rows.map(r => `<div style="font-size:12px;">
        <b>${UI.esc(r[0])}:</b> ${r[1]}</div>`).join('')}
    </div>`;
  }

  /* Lee la tabla de sedes tal cual esta en pantalla, incluidas las filas a
     medio rellenar: el borrador de edicion no debe perder lo que el usuario
     acaba de escribir al anadir o quitar una fila. */
  function _readLocationsRaw() {
    return Array.from(document.querySelectorAll('#ing-loc-table tr[data-loc]')).map(tr => {
      const row = {};
      tr.querySelectorAll('[data-f]').forEach(inp => {
        const v = (inp.value || '').trim();
        if (v) row[inp.dataset.f] = v;
      });
      return row;
    });
  }

  /* Lo que se envia al backend: una sede sin nombre no identifica nada. */
  function _readLocations() {
    return _readLocationsRaw().filter(l => l.name);
  }

  function _wireProfile() {
    const add = document.getElementById('ing-add-loc');
    if (add) add.onclick = () => {
      _profileDraft = {
        locations: _readLocationsRaw().concat([{}]),
        business_units: _readUnits(),
      };
      _renderProfile();
    };
    document.querySelectorAll('[data-rm-loc]').forEach(btn => {
      btn.onclick = () => {
        const idx = Number(btn.dataset.rmLoc);
        const locs = _readLocationsRaw();
        locs.splice(idx, 1);
        _profileDraft = { locations: locs, business_units: _readUnits() };
        _renderProfile();
      };
    });
    const save = document.getElementById('ing-profile-save');
    if (save) save.onclick = _saveProfile;
  }

  function _readUnits() {
    const inp = document.getElementById('ing-bus-units');
    if (!inp) return [];
    return (inp.value || '').split(',').map(s => s.trim()).filter(Boolean);
  }

  async function _saveProfile() {
    const btn = document.getElementById('ing-profile-save');
    const methodEl = document.getElementById('ing-method-json');
    let method;
    if (methodEl) {
      try { method = JSON.parse(methodEl.value || '{}'); }
      catch (e) { UI.toast(t('ingest.profile.invalid_json'), 'error'); return; }
      if (method === null || typeof method !== 'object' || Array.isArray(method)) {
        UI.toast(t('ingest.profile.invalid_json'), 'error');
        return;
      }
    }
    const narrative = (document.getElementById('ing-narrative') || {}).value || '';
    btn.disabled = true;
    try {
      await Api.put('/api/ingest/profile', {
        structure: { locations: _readLocations(), business_units: _readUnits() },
        method: method,
        narrative: narrative,
      });
      UI.toast(t('ingest.profile.saved'), 'success');
      _loadProfile();
    } catch (e) {
      UI.toast(e.message, 'error');
      btn.disabled = false;
    }
  }

  // ---------- 10. Valores forzados ----------

  async function _loadOverrides() {
    const box = document.getElementById('ing-overrides');
    if (!box) return;
    try {
      _overrides = await Api.get('/api/ingest/overrides') || [];
      _renderOverrides();
    } catch (e) { _err(box, e); }
  }

  function _renderOverrides() {
    const box = document.getElementById('ing-overrides');
    if (!box) return;
    const rows = _overrides.map((o, i) => `
      <tr>
        <td>
          <div class="mono" style="font-size:12px;">${UI.esc(o.table_name || '')}#${UI.esc(String(o.record_id))}</div>
          <div style="font-size:11px;color:var(--text-subtle);">${UI.esc(o.field_name || '')}</div>
        </td>
        <td><b>${UI.esc(_val(o.value))}</b></td>
        <td style="color:var(--text-subtle);"><s>${UI.esc(_val(o.previous_value))}</s></td>
        <td style="font-size:12px;max-width:320px;">${UI.esc(_val(o.reason))}</td>
        <td style="font-size:11px;">${UI.esc(_fmtDate(o.created_at))}</td>
        <td><button class="btn btn-ghost btn-sm" data-rm-ovr="${i}">
          ${t('ingest.overrides.release')}</button></td>
      </tr>`).join('');
    box.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:baseline;">
        <h3 style="margin:0;">${t('ingest.overrides.title')}</h3>
        <button class="btn btn-ghost btn-sm" id="ing-ovr-reload">${t('common.refresh')}</button>
      </div>
      <div style="background:var(--brand-purple-4);border-left:3px solid var(--brand-purple);
                  border-radius:0 8px 8px 0;padding:10px 14px;margin:10px 0;font-size:13px;
                  line-height:1.6;">${t('ingest.overrides.guarantee')}</div>
      ${rows ? `<div style="overflow-x:auto;">
        <table class="data">
          <thead><tr>
            <th>${t('ingest.overrides.field')}</th>
            <th>${t('ingest.overrides.value')}</th>
            <th>${t('ingest.overrides.previous')}</th>
            <th>${t('ingest.overrides.reason')}</th>
            <th>${t('ingest.overrides.created')}</th>
            <th></th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table></div>`
      : `<p class="text-muted">${t('ingest.overrides.empty')}</p>`}
    `;
    const reload = document.getElementById('ing-ovr-reload');
    if (reload) reload.onclick = _loadOverrides;
    box.querySelectorAll('[data-rm-ovr]').forEach(btn => {
      btn.onclick = async () => {
        const o = _overrides[Number(btn.dataset.rmOvr)];
        if (!o) return;
        if (!confirm(t('ingest.overrides.confirm_release'))) return;
        btn.disabled = true;
        try {
          await Api.del('/api/ingest/overrides/' + o.id);
          UI.toast(t('ingest.overrides.released'), 'success');
          _loadOverrides();
        } catch (e) { UI.toast(e.message, 'error'); btn.disabled = false; }
      };
    });
  }

  return { render };
})();
