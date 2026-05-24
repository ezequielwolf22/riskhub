/* Vista Calendario de tratamiento — fechas limite por mes. */
const ViewCalendar = {
  _year: new Date().getFullYear(),
  _month: new Date().getMonth(), // 0-indexed
  _mode: 'all', // 'all' | 'risks' | 'controls'

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      'Calendario de tratamiento',
      'Vencimientos del plan de tratamiento de riesgos y revisiones de controles'
    ) + '<div id="cal-root"></div>';
    await ViewCalendar._draw();
  },

  async _draw() {
    const root = document.getElementById('cal-root');
    if (!root) return;
    root.innerHTML = '<div class="notice">Cargando...</div>';

    try {
      const [risks, impls] = await Promise.all([
        Api.risks.list(),
        Api.impls.list(),
      ]);

      // Indexar riesgos por fecha de vencimiento de tratamiento
      const risksByDate = {};
      for (const r of risks) {
        if (!r.treatment_due_date) continue;
        const d = r.treatment_due_date.slice(0, 10);
        if (!risksByDate[d]) risksByDate[d] = [];
        risksByDate[d].push(r);
      }

      // Indexar controles por fecha de proxima revision
      const ctrlByDate = {};
      for (const c of impls) {
        if (!c.next_review || c.status === 'not_implemented') continue;
        const d = c.next_review.slice(0, 10);
        if (!ctrlByDate[d]) ctrlByDate[d] = [];
        ctrlByDate[d].push(c);
      }

      root.innerHTML = ViewCalendar._html(risksByDate, ctrlByDate);

      document.getElementById('cal-prev').onclick = () => {
        ViewCalendar._month--;
        if (ViewCalendar._month < 0) { ViewCalendar._month = 11; ViewCalendar._year--; }
        ViewCalendar._draw();
      };
      document.getElementById('cal-next').onclick = () => {
        ViewCalendar._month++;
        if (ViewCalendar._month > 11) { ViewCalendar._month = 0; ViewCalendar._year++; }
        ViewCalendar._draw();
      };
      document.getElementById('cal-today').onclick = () => {
        const now = new Date();
        ViewCalendar._year = now.getFullYear();
        ViewCalendar._month = now.getMonth();
        ViewCalendar._draw();
      };
      document.querySelectorAll('[data-cal-mode]').forEach(btn => {
        btn.onclick = () => {
          ViewCalendar._mode = btn.dataset.calMode;
          ViewCalendar._draw();
        };
      });
    } catch (e) {
      root.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _html(risksByDate, ctrlByDate) {
    const year = ViewCalendar._year;
    const month = ViewCalendar._month;
    const now = new Date();
    const todayStr = now.toISOString().slice(0, 10);

    const monthNames = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                        'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
    const dayNames = ['Lun','Mar','Mie','Jue','Vie','Sab','Dom'];

    const firstDay = new Date(year, month, 1);
    const startDow = (firstDay.getDay() + 6) % 7; // 0=lun
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const totalCells = startDow + daysInMonth;
    const rows = Math.ceil(totalCells / 7);

    // Contar totales del mes
    let monthRisks = 0, monthRisksOverdue = 0;
    let monthCtrls = 0, monthCtrlsOverdue = 0;
    for (let d = 1; d <= daysInMonth; d++) {
      const key = `${year}-${String(month + 1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const r = risksByDate[key] || [];
      const c = ctrlByDate[key] || [];
      monthRisks += r.length;
      monthCtrls += c.length;
      if (key < todayStr) { monthRisksOverdue += r.length; monthCtrlsOverdue += c.length; }
    }

    const mode = ViewCalendar._mode;

    // Generar celdas
    let cells = '';
    let dayCounter = 1;
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < 7; col++) {
        const cellIndex = row * 7 + col;
        if (cellIndex < startDow || dayCounter > daysInMonth) {
          cells += '<div class="cal-cell cal-empty"></div>';
          continue;
        }
        const key = `${year}-${String(month + 1).padStart(2,'0')}-${String(dayCounter).padStart(2,'0')}`;
        const risks = risksByDate[key] || [];
        const ctrls = ctrlByDate[key] || [];
        const isToday = key === todayStr;
        const isPast = key < todayStr;
        const hasOverdue = isPast && (risks.length > 0 || ctrls.length > 0);

        let pills = '';
        const maxRiskPills = mode === 'all' ? 2 : 3;
        const maxCtrlPills = mode === 'all' ? 2 : 3;

        if (mode !== 'controls') {
          risks.slice(0, maxRiskPills).forEach(r => {
            const color = r.residual_level >= 6 ? 'var(--risk-high)'
                        : r.residual_level >= 4 ? 'var(--risk-medium)'
                        : 'var(--risk-low)';
            pills += `<div class="cal-pill" style="background:${color};"
                         title="${UI.esc(r.code + ': ' + (r.asset ? r.asset.name : '') + ' — nivel ' + r.residual_level)}"
                         onclick="location.hash='#/risks?id=${r.id}';event.stopPropagation();"
                      >${UI.esc(r.code)}</div>`;
          });
          const extraRisks = risks.length - maxRiskPills;
          if (extraRisks > 0) {
            pills += `<div class="cal-pill-more">+${extraRisks} riesgo${extraRisks > 1 ? 's' : ''}</div>`;
          }
        }

        if (mode !== 'risks') {
          ctrls.slice(0, maxCtrlPills).forEach(c => {
            const ctrlOverdue = key < todayStr;
            const bg = ctrlOverdue ? 'var(--brand-orange)' : 'var(--brand-purple)';
            pills += `<div class="cal-pill" style="background:${bg};opacity:0.85;"
                         title="${UI.esc((c.control?.code || '') + ': ' + c.name)}"
                         onclick="location.hash='#/controls';event.stopPropagation();"
                      >${UI.esc(c.control?.code || 'CTR')}</div>`;
          });
          const extraCtrls = ctrls.length - maxCtrlPills;
          if (extraCtrls > 0) {
            pills += `<div class="cal-pill-more" style="color:var(--brand-purple);">+${extraCtrls} ctrl${extraCtrls > 1 ? 's' : ''}</div>`;
          }
        }

        cells += `
          <div class="cal-cell${isToday ? ' cal-today' : ''}${hasOverdue ? ' cal-overdue' : ''}">
            <div class="cal-day-num">${dayCounter}</div>
            <div class="cal-pills">${pills}</div>
          </div>`;
        dayCounter++;
      }
    }

    const modeBtn = (val, label) => {
      const active = mode === val;
      return `<button class="btn ${active ? 'btn-primary' : ''}" data-cal-mode="${val}" style="font-size:12px;padding:4px 10px;">${label}</button>`;
    };

    return `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px;">
        <div style="display:flex;align-items:center;gap:10px;">
          <button class="btn btn-ghost" id="cal-prev">&#8592;</button>
          <h2 style="margin:0;font-size:18px;font-weight:700;">${monthNames[month]} ${year}</h2>
          <button class="btn btn-ghost" id="cal-next">&#8594;</button>
          <button class="btn btn-ghost" id="cal-today" style="font-size:12px;">Hoy</button>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          ${modeBtn('all','Todos')}${modeBtn('risks','Solo riesgos')}${modeBtn('controls','Solo controles')}
        </div>
        <div style="display:flex;gap:16px;font-size:13px;flex-wrap:wrap;">
          ${monthRisks ? `<span>Vencimientos riesgos: <strong>${monthRisks}</strong>${monthRisksOverdue ? ` <span style="color:var(--risk-high);">(${monthRisksOverdue} vencido${monthRisksOverdue>1?'s':''})</span>` : ''}</span>` : ''}
          ${monthCtrls ? `<span>Revisiones controles: <strong>${monthCtrls}</strong>${monthCtrlsOverdue ? ` <span style="color:var(--brand-orange);">(${monthCtrlsOverdue} vencida${monthCtrlsOverdue>1?'s':''})</span>` : ''}</span>` : ''}
          ${!monthRisks && !monthCtrls ? '<span style="color:var(--text-subtle);">Sin eventos este mes</span>' : ''}
        </div>
      </div>

      <div class="cal-grid">
        ${dayNames.map(d => `<div class="cal-header-cell">${d}</div>`).join('')}
        ${cells}
      </div>

      <div style="display:flex;gap:16px;margin-top:14px;font-size:12px;align-items:center;flex-wrap:wrap;">
        <div style="display:flex;align-items:center;gap:6px;">
          <div style="width:12px;height:12px;border-radius:3px;background:var(--risk-high);"></div> Riesgo alto (&ge;6)
        </div>
        <div style="display:flex;align-items:center;gap:6px;">
          <div style="width:12px;height:12px;border-radius:3px;background:var(--risk-medium);"></div> Riesgo medio (4-5)
        </div>
        <div style="display:flex;align-items:center;gap:6px;">
          <div style="width:12px;height:12px;border-radius:3px;background:var(--risk-low);"></div> Riesgo bajo (&lt;4)
        </div>
        <div style="display:flex;align-items:center;gap:6px;">
          <div style="width:12px;height:12px;border-radius:3px;background:var(--brand-purple);"></div> Control (proxima revision)
        </div>
        <div style="display:flex;align-items:center;gap:6px;">
          <div style="width:12px;height:12px;border-radius:3px;background:var(--brand-orange);"></div> Control (revision vencida)
        </div>
        <span style="color:var(--text-muted);margin-left:8px;">Haz clic en una pastilla para ir al detalle</span>
      </div>
    `;
  },
};
