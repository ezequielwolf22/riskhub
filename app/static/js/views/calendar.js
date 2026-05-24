/* Vista Calendario de tratamiento — fechas limite por mes. */
const ViewCalendar = {
  _year: new Date().getFullYear(),
  _month: new Date().getMonth(), // 0-indexed

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      'Calendario de tratamiento',
      'Fechas limite del plan de tratamiento de riesgos'
    ) + '<div id="cal-root"></div>';
    await ViewCalendar._draw();
  },

  async _draw() {
    const root = document.getElementById('cal-root');
    if (!root) return;
    root.innerHTML = '<div class="notice">Cargando...</div>';

    try {
      const risks = await Api.risks.list();
      // Indexar por fecha de vencimiento (YYYY-MM-DD)
      const byDate = {};
      for (const r of risks) {
        if (!r.treatment_due_date) continue;
        const d = r.treatment_due_date.slice(0, 10);
        if (!byDate[d]) byDate[d] = [];
        byDate[d].push(r);
      }
      root.innerHTML = ViewCalendar._html(byDate);
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
    } catch (e) {
      root.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _html(byDate) {
    const year = ViewCalendar._year;
    const month = ViewCalendar._month;
    const now = new Date();
    const todayStr = now.toISOString().slice(0, 10);

    const monthNames = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                        'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
    const dayNames = ['Lun','Mar','Mie','Jue','Vie','Sab','Dom'];

    // Primera celda: que dia de semana cae el 1 del mes (0=lunes)
    const firstDay = new Date(year, month, 1);
    const startDow = (firstDay.getDay() + 6) % 7; // 0=lun
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    // Cuantas filas necesitamos
    const totalCells = startDow + daysInMonth;
    const rows = Math.ceil(totalCells / 7);

    // Contar risks con vencimiento en este mes
    let monthTotal = 0;
    let monthOverdue = 0;
    for (let d = 1; d <= daysInMonth; d++) {
      const key = `${year}-${String(month + 1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
      const items = byDate[key] || [];
      monthTotal += items.length;
      if (key < todayStr) monthOverdue += items.length;
    }

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
        const items = byDate[key] || [];
        const isToday = key === todayStr;
        const isPast = key < todayStr;

        let pills = '';
        const maxPills = 3;
        items.slice(0, maxPills).forEach(r => {
          const color = r.residual_level >= 6 ? 'var(--risk-high)'
                      : r.residual_level >= 4 ? 'var(--risk-medium)'
                      : 'var(--risk-low)';
          pills += `<div class="cal-pill" style="background:${color};"
                       title="${UI.esc(r.code + ': ' + (r.asset ? r.asset.name : '') + ' — nivel ' + r.residual_level)}"
                       onclick="location.hash='#/risks';event.stopPropagation();"
                    >${UI.esc(r.code)}</div>`;
        });
        if (items.length > maxPills) {
          pills += `<div class="cal-pill-more">+${items.length - maxPills} mas</div>`;
        }

        cells += `
          <div class="cal-cell${isToday ? ' cal-today' : ''}${isPast && items.length ? ' cal-overdue' : ''}">
            <div class="cal-day-num">${dayCounter}</div>
            <div class="cal-pills">${pills}</div>
          </div>`;
        dayCounter++;
      }
    }

    return `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
        <div style="display:flex;align-items:center;gap:10px;">
          <button class="btn btn-ghost" id="cal-prev">&#8592;</button>
          <h2 style="margin:0;font-size:18px;font-weight:700;">${monthNames[month]} ${year}</h2>
          <button class="btn btn-ghost" id="cal-next">&#8594;</button>
          <button class="btn btn-ghost" id="cal-today" style="font-size:12px;">Hoy</button>
        </div>
        <div style="display:flex;gap:16px;font-size:13px;">
          <span>Vencimientos este mes: <strong>${monthTotal}</strong></span>
          ${monthOverdue ? `<span style="color:var(--risk-high);">Vencidos: <strong>${monthOverdue}</strong></span>` : ''}
        </div>
      </div>

      <div class="cal-grid">
        ${dayNames.map(d => `<div class="cal-header-cell">${d}</div>`).join('')}
        ${cells}
      </div>

      <div style="display:flex;gap:16px;margin-top:14px;font-size:12px;align-items:center;">
        <div style="display:flex;align-items:center;gap:6px;">
          <div style="width:12px;height:12px;border-radius:3px;background:var(--risk-high);"></div> Alto (≥6)
        </div>
        <div style="display:flex;align-items:center;gap:6px;">
          <div style="width:12px;height:12px;border-radius:3px;background:var(--risk-medium);"></div> Medio (4–5)
        </div>
        <div style="display:flex;align-items:center;gap:6px;">
          <div style="width:12px;height:12px;border-radius:3px;background:var(--risk-low);"></div> Bajo (&lt;4)
        </div>
        <span style="color:var(--text-muted);margin-left:8px;">Haz clic en una pastilla para ir a Riesgos</span>
      </div>
    `;
  },
};
