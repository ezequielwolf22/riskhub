/* Vista Guia — Documentacion completa de uso de RiskHub. */
const ViewGuide = {

  _sections: [
    { id: 'intro', title: 'Introduccion', icon: '📖' },
    { id: 'search', title: 'Busqueda global', icon: '🔎' },
    { id: 'context', title: 'Configuracion inicial', icon: '⚙️' },
    { id: 'assets', title: 'Inventario de activos', icon: '🗄️' },
    { id: 'threats', title: 'Amenazas y vulnerabilidades', icon: '🔍' },
    { id: 'risks', title: 'Gestion de riesgos', icon: '📊' },
    { id: 'calendar', title: 'Calendario', icon: '📅' },
    { id: 'controls', title: 'Controles ISO 27002', icon: '🛡️' },
    { id: 'ai', title: 'Agente IA', icon: '🤖' },
    { id: 'reports', title: 'Informes', icon: '📄' },
    { id: 'alerts', title: 'Alertas por email', icon: '🔔' },
    { id: 'integrations', title: 'Integraciones', icon: '🔗' },
    { id: 'audit', title: 'Log de Auditoria', icon: '📋' },
    { id: 'admin', title: 'Administracion', icon: '👥' },
    { id: 'methodology', title: 'Metodologia ISO 27005', icon: '📐' },
  ],

  _active: 'intro',

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      'Guia de uso',
      'Documentacion completa de RiskHub — ISO/IEC 27005:2018 + MAGERIT v3'
    ) + '<div id="guide-root"></div>';
    this._renderLayout();
  },

  _renderLayout() {
    const navItems = this._sections.map(s =>
      `<a href="#" onclick="ViewGuide._show('${s.id}');return false;"
          id="gnav-${s.id}"
          style="display:flex;align-items:center;gap:8px;padding:8px 12px;
                 border-radius:6px;font-size:13px;color:var(--text-base);
                 text-decoration:none;transition:background .15s;">
        <span>${s.icon}</span> ${s.title}
      </a>`
    ).join('');

    document.getElementById('guide-root').innerHTML = `
      <div style="display:grid;grid-template-columns:220px 1fr;gap:20px;align-items:start;">
        <div class="card" style="position:sticky;top:80px;">
          <p style="font-size:11px;text-transform:uppercase;color:var(--text-muted);
                    font-weight:600;margin:0 0 8px;letter-spacing:.5px;">Contenido</p>
          <nav id="guide-nav" style="display:flex;flex-direction:column;gap:2px;">
            ${navItems}
          </nav>
        </div>
        <div id="guide-content"></div>
      </div>`;

    this._show(this._active);
  },

  _show(id) {
    this._active = id;
    document.querySelectorAll('[id^="gnav-"]').forEach(el => {
      el.style.background = el.id === `gnav-${id}` ? 'var(--brand-purple-4)' : '';
      el.style.color = el.id === `gnav-${id}` ? 'var(--brand-purple)' : '';
      el.style.fontWeight = el.id === `gnav-${id}` ? '600' : '';
    });
    const sec = this._sections.find(s => s.id === id);
    const content = this._getContent(id);
    document.getElementById('guide-content').innerHTML = `
      <div class="card" style="margin-bottom:0;">
        <h2 style="margin-top:0;display:flex;align-items:center;gap:10px;">
          <span style="font-size:24px;">${sec.icon}</span> ${sec.title}
        </h2>
        ${content}
      </div>`;
  },

  _getContent(id) {
    return ({
      intro: this._cIntro,
      search: this._cSearch,
      context: this._cContext,
      assets: this._cAssets,
      threats: this._cThreats,
      risks: this._cRisks,
      calendar: this._cCalendar,
      controls: this._cControls,
      ai: this._cAI,
      reports: this._cReports,
      alerts: this._cAlerts,
      integrations: this._cIntegrations,
      audit: this._cAudit,
      admin: this._cAdmin,
      methodology: this._cMethodology,
    })[id] || '<p>Seccion en construccion.</p>';
  },

  _h(text) {
    return `<h3 style="color:var(--brand-purple);margin:24px 0 8px;font-size:14px;
                       text-transform:uppercase;letter-spacing:.5px;">${text}</h3>`;
  },

  _p(text) {
    return `<p style="font-size:14px;line-height:1.7;color:var(--text-base);margin:0 0 10px;">${text}</p>`;
  },

  _tip(text) {
    return `<div style="background:var(--brand-purple-4);border-left:3px solid var(--brand-purple);
                        border-radius:0 6px 6px 0;padding:10px 14px;margin:10px 0;font-size:13px;">
              ${text}</div>`;
  },

  _warn(text) {
    return `<div style="background:var(--brand-orange-4);border-left:3px solid var(--brand-orange);
                        border-radius:0 6px 6px 0;padding:10px 14px;margin:10px 0;font-size:13px;">
              ${text}</div>`;
  },

  _steps(steps) {
    return `<ol style="padding-left:20px;margin:8px 0 16px;">
      ${steps.map(s => `<li style="font-size:13px;line-height:1.6;margin-bottom:6px;">${s}</li>`).join('')}
    </ol>`;
  },

  _badge(text, color) {
    color = color || 'var(--brand-purple)';
    return `<span style="background:${color};color:#fff;padding:2px 8px;border-radius:4px;
                         font-size:11px;font-weight:600;">${text}</span>`;
  },

  get _cIntro() { return `
    ${this._p('RiskHub es una plataforma de <strong>Gobernanza, Riesgo y Cumplimiento (GRC)</strong> diseñada para implementar el proceso de gestión del riesgo de seguridad de la información según <strong>ISO/IEC 27005:2018</strong> con el catálogo de controles de <strong>ISO/IEC 27002:2022</strong>.')}
    ${this._h('Para qué sirve RiskHub')}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
      ${['Identificar y catalogar activos de información','Asociar amenazas y vulnerabilidades a cada activo','Calcular niveles de riesgo inherente y residual','Definir planes de tratamiento por riesgo','Gestionar controles ISO 27002:2022','Generar informes para auditoría y dirección','Usar IA para análisis de riesgo automatizado','Enviar alertas por email a los responsables','Busqueda global por codigo, nombre o descripcion','Calendario de vencimientos de tratamiento','Exportar datos a CSV y PDF'].map(f =>
        `<div style="background:var(--bg-2);border-radius:8px;padding:10px 14px;font-size:13px;">
          <span style="color:var(--brand-purple);font-weight:700;">✓</span> ${f}
        </div>`).join('')}
    </div>
    ${this._h('Dashboard — vision ejecutiva')}
    ${this._p('La pantalla principal (Dashboard) ofrece una vision global en tiempo real:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>KPIs:</strong> activos, riesgos, controles, tratamientos vencidos, altos sin plan, reduccion media del riesgo.</li>
      <li><strong>Distribucion por nivel residual:</strong> grafico donut SVG con proporcion alto/medio/bajo y barras de porcentaje.</li>
      <li><strong>Por estado y por decision:</strong> barras mini con porcentaje del ciclo de vida y opciones de tratamiento.</li>
      <li><strong>Acciones rapidas:</strong> accesos directos a tratamientos vencidos, riesgos sin plan, calendario y heatmap.</li>
      <li><strong>Proximos vencimientos (30 dias):</strong> lista de riesgos con fecha limite proxima, con countdown en dias.</li>
      <li><strong>Top 10 riesgos:</strong> riesgos mas criticos con porcentaje de reduccion. Haz clic para abrir el detalle.</li>
      <li><strong>Cobertura de controles por tema ISO 27002:</strong> tarjetas con madurez media e implementados/total para Organizacional, Personas, Fisico y Tecnologico.</li>
    </ul>
    ${this._h('Flujo de trabajo recomendado')}
    ${this._steps([
      '<strong>Configura el contexto organizacional</strong> (menú Contexto): nombre de la organización, alcance del SGSI, criterios de probabilidad e impacto.',
      '<strong>Importa o crea activos</strong> (menú Activos): inventaria todos los sistemas, aplicaciones, datos y procesos del alcance.',
      '<strong>Revisa el catálogo de amenazas</strong> (menú Amenazas): las 49 amenazas de ISO 27005 Annex C están precargadas. Añade las específicas de tu sector.',
      '<strong>Revisa el catálogo de vulnerabilidades</strong> (menú Vulnerabilidades): las 67 vulnerabilidades de ISO 27005 Annex D están disponibles.',
      '<strong>Usa el Agente IA</strong> (menú Agente IA): responde el cuestionario de contexto. El agente genera automáticamente los escenarios de riesgo más relevantes para tu organización.',
      '<strong>Revisa y ajusta los riesgos</strong> (menú Riesgos): valida los niveles calculados, asigna responsables y define planes de tratamiento.',
      '<strong>Asocia controles</strong> (menú Controles): vincula controles ISO 27002 implementados a cada riesgo para calcular el nivel residual.',
      '<strong>Genera informes</strong> (menú Informes): Risk Register PDF/Excel, SoA, y reportes ejecutivos con IA.',
      '<strong>Configura alertas</strong> (menú Alertas): recibe notificaciones por email cuando un riesgo supere el umbral configurado.',
    ])}
    ${this._h('Roles de usuario')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--brand-purple);color:#fff;">
        <th style="padding:8px 12px;text-align:left;">Rol</th>
        <th style="padding:8px 12px;text-align:left;">Permisos</th>
      </tr></thead>
      <tbody>
        <tr><td style="padding:8px 12px;font-weight:600;">admin</td>
            <td style="padding:8px 12px;">Acceso total. Gestión de usuarios, configuración SMTP, todas las funciones.</td></tr>
        <tr style="background:var(--bg-2);">
            <td style="padding:8px 12px;font-weight:600;">analyst</td>
            <td style="padding:8px 12px;">Crear y editar riesgos, activos, controles. Usar el Agente IA. Configurar alertas. No puede gestionar usuarios.</td></tr>
        <tr><td style="padding:8px 12px;font-weight:600;">viewer</td>
            <td style="padding:8px 12px;">Solo lectura. Puede ver todos los datos y descargar informes pero no modificar nada.</td></tr>
      </tbody>
    </table>
  `;},

  get _cSearch() { return `
    ${this._p('RiskHub incluye una barra de <strong>busqueda global</strong> en la cabecera de la aplicacion. Desde un unico campo puedes localizar activos, riesgos, amenazas, vulnerabilidades y controles sin tener que navegar por cada seccion.')}
    ${this._h('Como usar la busqueda')}
    ${this._steps([
      'Haz clic en el campo <em>"Buscar activos, riesgos, amenazas..."</em> en la parte superior de la pantalla.',
      'Escribe al menos 2 caracteres. Los resultados aparecen en un desplegable en tiempo real (con debounce de 280 ms).',
      'Los resultados se agrupan por tipo: Activos, Riesgos, Amenazas, Vulnerabilidades y Controles.',
      'Haz clic en cualquier resultado para navegar directamente a la seccion correspondiente.',
      'Pulsa <kbd>Esc</kbd> para cerrar el desplegable sin navegar.',
    ])}
    ${this._h('Atajo de teclado')}
    ${this._p('Pulsa <kbd>/</kbd> desde cualquier pagina (sin que el foco este en un campo de texto) para activar la busqueda automaticamente. Este atajo agiliza la navegacion sin usar el raton.')}
    ${this._h('Navegacion con teclado')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><kbd>/</kbd> — focaliza la busqueda desde cualquier pagina.</li>
      <li><kbd>↓</kbd> — mueve el foco al primer resultado del desplegable.</li>
      <li><kbd>↑</kbd> / <kbd>↓</kbd> — navega entre los resultados.</li>
      <li><kbd>Enter</kbd> — abre el resultado seleccionado.</li>
      <li><kbd>Esc</kbd> — cierra el desplegable y devuelve el foco al campo de busqueda.</li>
    </ul>
    ${this._tip('La busqueda filtra por nombre, descripcion y codigo. Por ejemplo: escribe "RSK-0012" para ir directamente a ese riesgo, o "servidor" para encontrar todos los activos de tipo servidor.')}
    ${this._h('Modo oscuro')}
    ${this._p('RiskHub incluye un tema oscuro completo. Puedes activarlo o desactivarlo con el boton de la <strong>luna/sol</strong> en la cabecera, o usando el atajo <kbd>Shift</kbd> + <kbd>D</kbd>. La preferencia se guarda en el navegador y persiste entre sesiones.')}
    ${this._h('Barra lateral colapsable')}
    ${this._p('La barra de navegacion lateral se puede contraer para ganar espacio horizontal en la zona de contenido. Haz clic en el <strong>boton de flecha</strong> situado en la parte inferior del menu lateral, o usa el atajo <kbd>Shift</kbd> + <kbd>B</kbd>. En modo contraido solo se muestran los iconos de cada seccion. La preferencia se guarda automaticamente en el navegador.')}
  `;},

  get _cContext() { return `
    ${this._p('El contexto organizacional define el marco de referencia del proceso de gestión del riesgo según la <strong>cláusula 7 de ISO 27005:2018</strong>. Es el primer paso y condiciona todos los cálculos posteriores.')}
    ${this._h('Campos del contexto')}
    ${this._steps([
      '<strong>Nombre de la organización:</strong> identifica los documentos generados.',
      '<strong>Alcance del SGSI:</strong> describe qué sistemas, procesos y ubicaciones están dentro del alcance. Sé específico para limitar correctamente el análisis de riesgo.',
      '<strong>Límites:</strong> qué queda explícitamente fuera del alcance.',
      '<strong>Apetito de riesgo:</strong> nivel máximo de riesgo residual aceptable (escala 0-8). Riesgos por encima de este umbral deben tratarse obligatoriamente.',
      '<strong>Criterios de probabilidad (likelihood):</strong> define qué significa cada nivel del 1 al 5 en términos de frecuencia de ocurrencia de amenazas.',
      '<strong>Criterios de impacto:</strong> define qué significa cada nivel del 1 al 5 para las 5 dimensiones CIA (Confidencialidad, Integridad, Disponibilidad, Autenticidad, Responsabilidad).',
      '<strong>Criterios de aceptación:</strong> define cuándo un riesgo puede aceptarse sin tratamiento.',
    ])}
    ${this._tip('<strong>Recomendación:</strong> Completa el contexto antes de empezar el análisis. Los criterios de probabilidad e impacto son la base de la matriz de riesgo y afectan a todos los cálculos.')}
    ${this._h('Criterios predeterminados')}
    ${this._p('RiskHub incluye criterios predefinidos alineados con <strong>ISO 27005 Annex E.2</strong>. Puedes personalizarlos para adaptarlos al sector y tamaño de tu organización. Los criterios editados se aplican a todos los riesgos nuevos y pueden revisarse periódicamente.')}
  `;},

  get _cAssets() { return `
    ${this._p('El inventario de activos es la base del análisis de riesgo. Siguiendo <strong>ISO 27005 Annex B</strong>, los activos se clasifican en primarios (procesos e información) y de soporte (hardware, software, red, personal, instalaciones, organización).')}
    ${this._h('Tipos de activo disponibles')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);"><th style="padding:8px;text-align:left;">Tipo</th><th style="padding:8px;text-align:left;">Descripcion</th><th style="padding:8px;text-align:left;">Ejemplos</th></tr></thead>
      <tbody>
        ${[
          ['primary_process','Proceso de negocio primario','Proceso de ventas, gestión de RRHH, producción'],
          ['primary_information','Información primaria','Base de datos de clientes, propiedad intelectual, registros financieros'],
          ['support_hardware','Hardware de soporte','Servidores, estaciones de trabajo, dispositivos de red'],
          ['support_software','Software de soporte','ERP, CRM, sistemas operativos, middleware'],
          ['support_network','Red de soporte','LAN, WAN, VPN, firewall'],
          ['support_personnel','Personal de soporte','Administradores de sistemas, desarrolladores, RRHH'],
          ['support_site','Instalaciones','CPD, oficinas, sala de servidores'],
          ['support_organization','Organización de soporte','Proveedores críticos, subcontratistas'],
        ].map((r, i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          <td style="padding:8px;font-family:monospace;font-size:11px;">${r[0]}</td>
          <td style="padding:8px;">${r[1]}</td><td style="padding:8px;color:var(--text-muted);">${r[2]}</td>
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Valoracion CIA (escala 0-4)')}
    ${this._p('Cada activo tiene una valoración en 5 dimensiones: <strong>C</strong>onfidencialidad, <strong>I</strong>ntegridad, <strong>D</strong>isponibilidad, <strong>Au</strong>tenticidad y <strong>Ac</strong>countability. El valor máximo de las cinco dimensiones determina el "valor del activo" usado en los cálculos MAGERIT.')}
    ${this._h('Importacion masiva')}
    ${this._steps([
      'Descarga la plantilla CSV desde Activos → Importar → Descargar plantilla.',
      'Rellena el CSV con los activos: code, name, asset_type, description, classification, value_c, value_i, value_a.',
      'Sube el CSV desde Activos → Importar → Seleccionar archivo.',
      'El sistema valida el formato y crea los activos. Los errores se reportan fila a fila.',
    ])}
    ${this._tip('<strong>Consejo:</strong> Empieza importando los activos críticos (aquellos que, si fallan, impactan directamente al negocio). Luego añade los de soporte. Usa el campo "proceso de negocio" para agrupar activos por área funcional.')}
    ${this._h('Jerarquia de activos')}
    ${this._p('Puedes definir un activo padre para cada activo. Esto es útil para representar dependencias: un proceso de negocio depende de varias aplicaciones, que a su vez dependen de servidores. La jerarquía ayuda a entender la propagación del impacto.')}
    ${this._h('Ver riesgos de un activo')}
    ${this._p('La tabla de activos muestra una columna <strong>Riesgos</strong> con el número de escenarios de riesgo asociados a cada activo. El número es un enlace que filtra directamente la vista de Riesgos. El color indica la exposición: rojo si el activo tiene 5 o más riesgos, púrpura si tiene alguno, gris si no tiene ninguno.')}
  `;},

  get _cThreats() { return `
    ${this._p('RiskHub incluye <strong>49 amenazas del catálogo ISO 27005 Annex C</strong> y <strong>67 vulnerabilidades de ISO 27005 Annex D</strong>, precargadas y listas para usar.')}
    ${this._h('Catalogo de amenazas ISO 27005')}
    ${this._p('Las amenazas se organizan por origen y categoría. Cada amenaza tiene:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Código:</strong> identificador único (ej. THR-0001).</li>
      <li><strong>Origen:</strong> Deliberado (D), Accidental (A) o Ambiental (E).</li>
      <li><strong>Categoría:</strong> ej. Physical damage, Natural events, Technical failures, Malicious acts.</li>
      <li><strong>Activos típicos:</strong> tipos de activo a los que aplica la amenaza.</li>
      <li><strong>Dimensiones afectadas:</strong> C, I, A, Autenticidad o Accountability.</li>
    </ul>
    ${this._h('Catalogo de vulnerabilidades ISO 27005')}
    ${this._p('Las vulnerabilidades se clasifican por categoría: hardware, software, red, personal, instalaciones u organización. Cada vulnerabilidad puede vincularse a amenazas relacionadas del catálogo.')}
    ${this._h('Creacion de amenazas/vulnerabilidades personalizadas')}
    ${this._steps([
      'Ve al menú Amenazas o Vulnerabilidades.',
      'Haz clic en "Nueva amenaza" / "Nueva vulnerabilidad".',
      'Completa el formulario: código personalizado, nombre, descripción, categoría, origen.',
      'Las entradas personalizadas se marcan con la etiqueta <strong>Custom</strong> en la tabla para diferenciarlas del catálogo ISO estándar.',
    ])}
    ${this._h('Edicion y eliminacion de entradas personalizadas')}
    ${this._p('Los usuarios con rol <strong>analyst</strong> o <strong>admin</strong> pueden editar o eliminar las entradas personalizadas. Las entradas del catálogo ISO oficial (marcadas <strong>ISO</strong>) son de solo lectura y no se pueden modificar ni borrar.')}
    ${this._steps([
      'En la tabla de amenazas o vulnerabilidades, localiza la entrada personalizada (etiqueta <strong>Custom</strong>).',
      'Haz clic en <strong>Editar</strong> para modificar cualquier campo del formulario.',
      'Haz clic en <strong>Eliminar</strong> para borrar la entrada. Se pedirá confirmación.',
      'Todas las operaciones quedan registradas en el <strong>Log de Auditoría</strong>.',
    ])}
    ${this._h('Exposicion en el catalogo')}
    ${this._p('La tabla de amenazas y la de vulnerabilidades muestran una columna <strong>Riesgos</strong> con el número de escenarios de riesgo vinculados a cada entrada. Esto permite identificar qué amenazas o vulnerabilidades generan mayor exposición sin necesidad de ir al registro de riesgos.')}
    ${this._tip('<strong>Tip:</strong> Antes de crear una amenaza personalizada, busca en el catálogo ISO 27005 precargado. Es probable que ya exista una amenaza equivalente. Las amenazas personalizadas son útiles para sectores específicos (ej. amenazas de salud, aviación, energía).')}
  `;},

  get _cRisks() { return `
    ${this._p('Un riesgo en RiskHub es la combinación única de un <strong>Activo × Amenaza</strong> (ISO 27005 §8.3). La matriz 5×5 calcula automáticamente el nivel de riesgo inherente y residual.')}
    ${this._h('Nivel de riesgo — escala 0 a 8')}
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px;">
      ${[['0-2','Bajo','Riesgo aceptable. Monitorizar.','#22C55E'],['3-4','Medio','Requiere atencion. Planificar tratamiento.','#F59E0B'],['5-6','Alto','Tratamiento prioritario.','#EF4444'],['7-8','Critico','Tratamiento inmediato. Escalar a direccion.','#7C3AED']].map(([r,l,d,c]) =>
        `<div style="background:${c}15;border:1px solid ${c}40;border-radius:8px;padding:10px 12px;">
          <div style="font-size:18px;font-weight:700;color:${c};">${r}</div>
          <div style="font-weight:600;font-size:13px;">${l}</div>
          <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">${d}</div>
        </div>`).join('')}
    </div>
    ${this._h('Riesgo inherente vs. residual')}
    ${this._p('<strong>Nivel inherente:</strong> nivel de riesgo SIN considerar los controles existentes. Refleja la exposición bruta. <strong>Nivel residual:</strong> nivel de riesgo DESPUÉS de aplicar los controles. Es el nivel real al que está expuesta la organización.')}
    ${this._h('Creacion manual de un riesgo')}
    ${this._steps([
      'Ve al menú Riesgos → Nuevo riesgo.',
      'Selecciona el Activo afectado del inventario.',
      'Selecciona la Amenaza del catálogo.',
      'Define Probabilidad inherente (0-4) y Consecuencia inherente (0-4). El nivel inherente se calcula automáticamente con la matriz ISO 27005.',
      'Opcional: añade Vulnerabilidades que expliquen la exposición.',
      'Opcional: añade Controles implementados para calcular el nivel residual.',
      'Define el Plan de tratamiento: opción (modificar, retener, evitar, compartir), responsable y fecha límite.',
    ])}
    ${this._h('Opciones de tratamiento ISO 27005')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px;">Opcion</th><th style="padding:8px;">Descripcion</th><th style="padding:8px;">Cuando usarla</th>
      </tr></thead>
      <tbody>
        ${[
          ['Modification (mitigar)','Implementar controles para reducir probabilidad o impacto.','Riesgos por encima del apetito con controles disponibles y coste proporcional.'],
          ['Retention (aceptar)','Asumir el riesgo sin acción adicional.','Riesgos por debajo del apetito o donde el coste de tratamiento supera al impacto.'],
          ['Avoidance (evitar)','Eliminar la actividad que genera el riesgo.','Riesgos críticos sin controles efectivos disponibles.'],
          ['Sharing (transferir)','Compartir el riesgo con un tercero (seguro, outsourcing).','Riesgos cuya gestión es más eficiente externamente.'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          <td style="padding:8px;font-weight:600;">${r[0]}</td>
          <td style="padding:8px;">${r[1]}</td>
          <td style="padding:8px;color:var(--text-muted);">${r[2]}</td>
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Estados del riesgo')}
    ${this._p('Identified → Assessed → Treated → Accepted → Closed. El flujo asegura que todos los riesgos siguen el proceso completo antes de cerrarse.')}
    ${this._h('Heatmap de riesgos')}
    ${this._p('El Heatmap (menú Heatmap) visualiza todos los riesgos en la matriz 5×5 de probabilidad × impacto, diferenciando el nivel inherente del residual. Es el artefacto principal para la comunicación a dirección. Haz clic en cualquier celda del heatmap para ver la lista de riesgos en esa posicion.')}
    ${this._h('Tabla de riesgos — columnas informativas')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Red.:</strong> porcentaje de reduccion del riesgo (inherente → residual). Verde = reduccion, rojo = riesgo residual mayor que el inherente.</li>
      <li><strong>VENCIDO:</strong> badge naranja en la columna Estado cuando la fecha limite de tratamiento ha pasado y el riesgo no esta cerrado ni aceptado. Las filas vencidas aparecen en rojo claro.</li>
      <li><strong>Exportar CSV:</strong> boton en la barra de herramientas para descargar todos los riesgos con campos ISO 27005 (niveles inherentes, residuales, estado, tratamiento, fechas).</li>
    </ul>
    ${this._h('Acciones masivas (bulk actions)')}
    ${this._p('Analistas y administradores pueden seleccionar multiples riesgos a la vez usando los <strong>checkboxes</strong> de la primera columna y aplicar cambios en bloque desde la barra morada que aparece en la parte inferior.')}
    ${this._steps([
      'Marca los checkboxes de los riesgos que quieras actualizar, o usa el checkbox de la cabecera para seleccionar todos.',
      'En la barra de acciones masivas (purple, en la parte inferior), elige el nuevo estado o la decision de tratamiento.',
      'Haz clic en <strong>Aplicar</strong>. Los cambios se ejecutan en paralelo y la tabla se recarga automaticamente.',
    ])}
    ${this._h('Ordenar la tabla de riesgos')}
    ${this._p('Haz clic en cualquier cabecera de columna de la tabla de riesgos para ordenar por ese campo. Un segundo clic invierte el orden. La columna activa muestra una flecha <strong>▲</strong> (ascendente) o <strong>▼</strong> (descendente) y su titulo se resalta en purpura.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Codigo:</strong> orden alfanumerico por RSK-XXXX.</li>
      <li><strong>Activo / Amenaza:</strong> orden alfabetico por nombre.</li>
      <li><strong>Inh. / Res.:</strong> orden numerico por nivel inherente o residual.</li>
      <li><strong>Red.:</strong> orden por porcentaje de reduccion de riesgo.</li>
      <li><strong>Estado / Tratamiento:</strong> orden alfabetico por valor del campo.</li>
    </ul>
    ${this._tip('Por defecto la tabla muestra los riesgos ordenados por nivel residual descendente (los mas criticos primero). El orden se resetea cada vez que se cambia un filtro.')}
    ${this._h('Acciones masivas (bulk actions)')}
    ${this._p('Analistas y administradores pueden seleccionar multiples riesgos a la vez usando los <strong>checkboxes</strong> de la primera columna y aplicar cambios en bloque desde la barra morada que aparece en la parte inferior.')}
    ${this._steps([
      'Marca los checkboxes de los riesgos que quieras actualizar, o usa el checkbox de la cabecera para seleccionar todos.',
      'En la barra de acciones masivas (purple, en la parte inferior), elige el nuevo estado, la decision de tratamiento, o asigna un responsable.',
      'Haz clic en <strong>Aplicar</strong>. Los cambios se ejecutan en paralelo y la tabla se recarga automaticamente.',
    ])}
    ${this._tip('Las acciones masivas son utiles para cerrar un grupo de riesgos al final de un ciclo de revision, asignar la misma decision de tratamiento a varios riesgos relacionados, o asignar un responsable a todos los riesgos de un activo a la vez. El selector <em>Sin responsable</em> elimina el propietario de todos los riesgos seleccionados.')}
    ${this._h('Filtro por responsable')}
    ${this._p('La barra de herramientas de Riesgos incluye un selector <strong>Cualquier responsable</strong> que permite filtrar el registro por el propietario asignado a cada riesgo.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Selecciona un usuario de la lista desplegable para ver solo los riesgos asignados a esa persona.</li>
      <li>La opcion <strong>Sin responsable</strong> muestra los riesgos que aun no tienen propietario asignado — util para detectar riesgos huerfanos que necesitan asignacion.</li>
      <li>El filtro se combina con el resto de filtros activos (busqueda por texto, estado, nivel).</li>
    </ul>
    ${this._tip('Usa el filtro por responsable junto con el filtro de estado <em>Identified</em> para encontrar rapidamente todos los riesgos nuevos sin propietario ni plan de tratamiento asignados.')}
    ${this._h('Historial de cambios de un riesgo')}
    ${this._p('Al abrir un riesgo existente, al final del formulario aparece la sección <strong>Historial de cambios</strong>. Haz clic para expandirla y ver todas las modificaciones realizadas sobre ese riesgo: timestamp, usuario responsable, acción (crear/actualizar/eliminar) y campos modificados. Útil para auditorías y para justificar decisiones ante comités de seguridad.')}
  `;},

  get _cCalendar() { return `
    ${this._p('La vista <strong>Calendario</strong> muestra todos los riesgos con fecha limite de tratamiento definida en una cuadricula mensual. Es la forma mas rapida de detectar vencimientos proximos y planificar revisiones.')}
    ${this._h('Como usar el calendario')}
    ${this._steps([
      'Ve al menu <strong>Calendario</strong> (bajo "Analisis y tratamiento").',
      'El calendario muestra el mes actual. Usa los botones ← / → para cambiar de mes, o <em>Hoy</em> para volver al mes en curso.',
      'Cada pastilla de color representa un riesgo: rojo = alto (≥6), naranja = medio (4–5), verde = bajo (&lt;4).',
      'Pasa el cursor sobre una pastilla para ver el codigo del riesgo, activo y nivel.',
      'Haz clic en una pastilla para ir a la vista de Riesgos y consultar el detalle.',
      'Si hay mas de 3 riesgos en un dia, se muestra "+ N mas" para no saturar la celda.',
    ])}
    ${this._h('Indicadores visuales')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Celda hoy:</strong> borde purple y fondo lila — identifica rapidamente el dia actual.</li>
      <li><strong>Celda en rojo claro:</strong> fecha ya vencida con riesgos pendientes de tratamiento.</li>
      <li><strong>Contador de vencidos:</strong> encima del calendario, muestra cuantos riesgos tienen fecha vencida en el mes visible.</li>
      <li><strong>Badge en sidebar:</strong> el numero en rojo junto a "Riesgos" indica tratamientos globalmente vencidos.</li>
    </ul>
    ${this._h('Exportar riesgos a CSV')}
    ${this._p('En la vista <strong>Riesgos</strong>, el boton <em>Exportar CSV</em> (barra de herramientas, derecha) descarga todos los riesgos en formato CSV con niveles inherentes, residuales, estado, plan de tratamiento y fecha limite. Compatible con Excel y cualquier hoja de calculo.')}
    ${this._h('Importar riesgos desde CSV')}
    ${this._steps([
      'Descarga la <strong>Plantilla</strong> (boton en la barra de herramientas) para ver el formato exacto esperado.',
      'Rellena el CSV: columnas <em>Activo_Codigo</em> (ej. AST-0001) y <em>Amenaza_Codigo</em> (ej. T-CYB-01) son obligatorias.',
      'Probabilidad y consecuencia (0-4 cada una) se calculan automaticamente para obtener el nivel.',
      'Haz clic en <em>Importar CSV</em> y selecciona el fichero. Los duplicados (mismo activo + amenaza) se omiten.',
      'Revisa el toast de resultado: indica cuantos riesgos se crearon y cuantos se omitieron con el motivo.',
    ])}
    ${this._tip('Si un riesgo no aparece en el calendario, es porque no tiene fecha limite de tratamiento definida. Edita el riesgo y establece el campo <em>Fecha limite del plan</em> para que aparezca en el calendario.')}
  `;},

  get _cControls() { return `
    ${this._p('RiskHub incluye los <strong>93 controles de ISO/IEC 27002:2022</strong> organizados en 4 temas: Organizacionales, Personas, Físicos y Tecnológicos.')}
    ${this._h('Estructura de controles')}
    ${this._p('Cada control del catálogo tiene: código, nombre, descripción, tema, tipo (preventivo/detectivo/correctivo), propiedades de seguridad (CIA) y conceptos de ciberseguridad (NIST CSF: identify/protect/detect/respond/recover).')}
    ${this._h('Implementacion de un control')}
    ${this._steps([
      'Ve al menú Controles → Nueva implementación.',
      'Selecciona el control ISO 27002 del catálogo.',
      'Define el nombre específico de la implementación en tu organización (ej. "Firewall perimetral Fortinet").',
      'Indica el estado: No implementado / Planificado / Parcial / Implementado.',
      'Asigna un nivel de madurez del 0 al 5 (escala CMM).',
      'Añade evidencias, propietario y fechas de revisión.',
    ])}
    ${this._h('Vinculacion de controles a riesgos')}
    ${this._p('Desde el detalle de un riesgo, puedes asociar controles implementados. El sistema calculará el nivel residual teniendo en cuenta la contribución de cada control (factor de reducción 0-1). Un control implementado al 100% con contribución 1.0 reduce el riesgo al nivel mínimo de la matriz para esa combinación.')}
    ${this._h('Fechas de revision de controles')}
    ${this._p('Al editar una implementacion puedes establecer la <strong>Ultima revision</strong> y la <strong>Proxima revision</strong>. Cuando la proxima revision vence, la fila aparece resaltada en amarillo con el badge <em>REVISION</em> y un aviso aparece al inicio de la lista. Esto ayuda a planificar las revisiones periodicas del SGSI.')}
    ${this._h('Badge de revisiones vencidas')}
    ${this._p('El enlace <strong>Controles</strong> en la barra lateral muestra un badge naranja con el numero de implementaciones que tienen la fecha de proxima revision vencida (y cuyo estado no es "No implementado"). Esto permite detectar controles que necesitan atencion sin entrar a la vista de Controles.')}
    ${this._tip('Si el badge naranja de Controles muestra un numero, abre la vista de Controles y filtra o revisa las filas resaltadas en amarillo con el badge <em>REVISION</em>.')}
    ${this._h('Riesgos mitigados por control')}
    ${this._p('La tabla de implementaciones muestra una columna <strong>Riesgos</strong> con el numero de escenarios de riesgo que cada control mitiga actualmente. El numero se actualiza en tiempo real cada vez que se asocia o desasocia un control a un riesgo.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Un valor <strong>0</strong> (en gris) indica que el control esta implementado pero no se ha vinculado a ningun riesgo todavia. Considera revisarlo.</li>
      <li>Un valor <strong>1-2</strong> (en gris oscuro) indica cobertura normal.</li>
      <li>Un valor <strong>3 o mas</strong> (en verde) indica que el control es un mitigador clave: su degradacion o eliminacion afectaria a multiples riesgos.</li>
    </ul>
    ${this._tip('Usa esta columna para identificar los controles mas criticos de tu SGSI. Un control que mitiga 5 o mas riesgos es un punto unico de fallo: asegurate de que su nivel de madurez sea alto y sus revisiones esten al dia.')}
    ${this._h('Statement of Applicability (SoA)')}
    ${this._p('El informe SoA (ISO 27001 §6.1.3.d) lista todos los controles de ISO 27002 con su estado de aplicabilidad.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>PDF:</strong> Informes → Statement of Applicability — informe completo con justificaciones.</li>
      <li><strong>CSV:</strong> Controles → boton <em>SoA CSV</em> — exporta los 93 controles con estado de aplicabilidad, nivel de madurez y proxima revision. Compatible con Excel.</li>
    </ul>
    ${this._tip('<strong>Para certificación ISO 27001:</strong> todos los controles del Anexo A deben estar justificados (aplicables o excluidos con justificación). Usa el campo descripción de la implementación para documentar la justificación.')}
  `;},

  get _cAI() { return `
    ${this._p('El Agente IA de RiskHub usa <strong>Claude (Anthropic)</strong> con metodología dual <strong>ISO 27005 + MAGERIT v3</strong> para generar automáticamente escenarios de riesgo completos a partir de un cuestionario de contexto organizacional.')}
    ${this._warn('<strong>Requisito:</strong> Necesitas una API key de Anthropic configurada en el servidor (variable RISKHUB_ANTHROPIC_API_KEY). Sin ella, el cuestionario carga pero el análisis no se ejecuta.')}
    ${this._h('Como funciona el agente')}
    ${this._steps([
      'Responde el cuestionario de 12 preguntas sobre: sector, tamaño, normativas, sistemas, tipos de datos, acceso remoto, terceros, incidentes pasados, controles existentes, madurez y RTO.',
      'El agente combina tus respuestas con el catálogo completo de activos, amenazas y controles de RiskHub.',
      'Claude analiza el perfil y genera entre 10-20 escenarios de riesgo con: activo sugerido, amenaza (código ISO 27005), vulnerabilidad, nivel inherente, controles aplicables (códigos ISO 27002) y nivel residual.',
      'Revisa los escenarios en la tabla de resultados. Puedes seleccionar cuáles importar.',
      'Los activos nuevos se crean automáticamente. Los riesgos se importan al registro.',
    ])}
    ${this._h('Campos de cada escenario generado')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Activo sugerido:</strong> nombre descriptivo del activo afectado, con tipo ISO 27005.</li>
      <li><strong>Amenaza:</strong> nombre y código del catálogo ISO 27005 Annex C + dimensión MAGERIT afectada.</li>
      <li><strong>Vulnerabilidad:</strong> descripción de la debilidad que permite que la amenaza se materialice.</li>
      <li><strong>Nivel inherente (0-8):</strong> calculado con la matriz ISO 27005 × probabilidad × consecuencia.</li>
      <li><strong>Controles:</strong> 2-5 controles ISO 27002 más relevantes para este escenario.</li>
      <li><strong>Nivel residual (0-8):</strong> nivel estimado tras aplicar los controles sugeridos.</li>
      <li><strong>Justificación:</strong> razonamiento del agente para asignar los niveles.</li>
    </ul>
    ${this._h('Iteraciones del analisis')}
    ${this._p('Puedes ejecutar el análisis múltiples veces con diferentes respuestas al cuestionario para explorar diferentes perfiles de riesgo (ej. antes y después de una migración a cloud). Cada análisis genera un conjunto nuevo de escenarios para importar.')}
    ${this._tip('<strong>Tip:</strong> El análisis tarda entre 20-40 segundos. Usa la sesión del Agente IA como punto de partida y luego refina manualmente los riesgos en el registro para ajustar la probabilidad e impacto a la realidad de tu organización.')}
  `;},

  get _cReports() { return `
    ${this._p('RiskHub genera informes en <strong>PDF</strong> (con branding purple/orange) y <strong>Excel</strong> (.xlsx) para auditoría, dirección y comités.')}
    ${this._h('Informes estaticos')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Risk Register PDF:</strong> listado completo de riesgos ordenados por nivel residual. Incluye activo, amenaza, niveles, estado y decisión de tratamiento.</li>
      <li><strong>Risk Register Excel:</strong> exportación completa en 4 hojas: Riesgos, Activos, Controles y Resumen estadístico. Permite análisis adicional en Excel.</li>
      <li><strong>Statement of Applicability (SoA):</strong> declaración de aplicabilidad de los 93 controles ISO 27002, con estado y madurez. Obligatorio para certificación ISO 27001.</li>
    </ul>
    ${this._h('Informes generados por IA')}
    ${this._p('Los informes de IA usan Claude para generar contenido narrativo profesional a partir de todos los datos del registro de riesgos. Cada informe es único y contextualizado.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Plan de Tratamiento de Riesgos:</strong> narrativa detallada por riesgo con acciones concretas, métricas de éxito y hoja de ruta de implementación en 3 fases.</li>
      <li><strong>Dashboard Ejecutivo:</strong> informe de postura de riesgo para dirección no técnica: hallazgos clave, acciones críticas, análisis de KPIs, estado de cumplimiento ISO 27001.</li>
      <li><strong>Acta de Comité de Seguridad:</strong> acta formal con orden del día, riesgos aceptados, decisiones adoptadas y acciones acordadas. Lista para que el Comité la firme.</li>
      <li><strong>Informe de Seguimiento ISO 27005:</strong> evaluación del proceso de gestión del riesgo según ISO 27005 cl. 12: monitorización, revisión, mejora, tendencias y recomendaciones.</li>
    </ul>
    ${this._warn('<strong>Requisito:</strong> Los informes de IA requieren la API key de Anthropic configurada. La generación tarda entre 30-60 segundos.')}
    ${this._h('Eleccion de formato')}
    ${this._p('Para cada informe de IA puedes elegir el formato de salida: <strong>PDF</strong> (recomendado para presentaciones y auditorías) o <strong>Excel</strong> (recomendado para edición y análisis posterior).')}
  `;},

  get _cAlerts() { return `
    ${this._p('El sistema de alertas por email de RiskHub notifica automáticamente a los responsables cuando se detectan riesgos que requieren atención inmediata.')}
    ${this._h('Configuracion SMTP')}
    ${this._steps([
      'Ve al menú Alertas (solo accesible para admin y analyst).',
      'Configura el servidor SMTP: host, puerto, usuario, contraseña y dirección de remitente.',
      'Activa TLS/STARTTLS según la configuración de tu servidor de correo.',
      'Haz clic en "Enviar email de prueba" para verificar que la configuración es correcta.',
    ])}
    ${this._h('Servidores SMTP compatibles')}
    <table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:7px;">Servidor</th><th style="padding:7px;">Host</th>
        <th style="padding:7px;">Puerto</th><th style="padding:7px;">TLS</th>
      </tr></thead>
      <tbody>
        ${[
          ['Gmail','smtp.gmail.com','587','STARTTLS (requiere contraseña de aplicacion)'],
          ['Microsoft 365','smtp.office365.com','587','STARTTLS'],
          ['Exchange on-premise','tu-servidor-exchange','25 o 587','Segun configuracion'],
          ['Sendmail/Postfix','localhost','25','Segun configuracion'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          ${r.map(c => `<td style="padding:7px;">${c}</td>`).join('')}
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Reglas de alerta')}
    ${this._p('Crea reglas para que RiskHub envíe emails automáticamente cuando se cumplan ciertos criterios:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>risk_critical:</strong> riesgos con nivel residual ≥ umbral configurado (ej. ≥7).</li>
      <li><strong>risk_high:</strong> riesgos con nivel residual ≥ umbral configurado (ej. ≥5).</li>
      <li><strong>treatment_overdue:</strong> riesgos con fecha límite de tratamiento vencida.</li>
      <li><strong>risk_no_treatment:</strong> riesgos de alto nivel sin plan de tratamiento definido.</li>
      <li><strong>daily_digest:</strong> resumen diario con estadisticas globales, tratamientos vencidos y proximos vencimientos en 7 dias. Se envia una vez al dia (cooldown de 20 horas).</li>
      <li><strong>treatment_due_soon:</strong> avisa cuando un tratamiento vencera dentro de X dias (X = umbral configurado). Util para dar margen de reaccion.</li>
      <li><strong>control_review_overdue:</strong> envia un resumen de todos los controles ISO 27002 con fecha de revision vencida. Util para el responsable de cumplimiento.</li>
    </ul>
    ${this._h('Evaluacion de reglas')}
    ${this._p('Las reglas se evaluan de <strong>dos formas</strong>:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 12px;">
      <li><strong>Automaticamente:</strong> RiskHub evalua todas las reglas activas <strong>cada hora</strong> en segundo plano. No es necesario hacer nada; los emails se envian solos cuando se cumplen los criterios.</li>
      <li><strong>Manualmente:</strong> desde Alertas → <em>Evaluar reglas ahora</em> puedes forzar una evaluacion inmediata sin esperar al ciclo automatico.</li>
    </ul>
    ${this._steps([
      'El sistema comprueba todos los riesgos activos contra cada regla activada.',
      'Si un riesgo cumple el criterio, se envía un email con el detalle del riesgo al destinatario configurado.',
      'Se registra la fecha de último envío por regla para trazabilidad.',
      'El panel de Informacion del sistema (Usuarios → scroll abajo) muestra la hora de la proxima evaluacion automatica.',
    ])}
    ${this._tip('Si el servidor SMTP no esta configurado, la evaluacion automatica se omite silenciosamente hasta que se configure una cuenta de correo valida.')}
    ${this._h('Alertas manuales')}
    ${this._p('Desde el detalle de cualquier riesgo (menú Riesgos), puedes enviar una alerta manual a cualquier email. Útil para notificar al propietario del riesgo de una actualización importante.')}
  `;},

  get _cIntegrations() { return `
    ${this._p('RiskHub incluye un catálogo de <strong>25 herramientas del mercado</strong> de seguridad y GRC con guías detalladas de integración. Las integraciones automatizadas están en el roadmap de v1.2.')}
    ${this._h('Categorias disponibles')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Gestión de activos:</strong> LeanIX, ServiceNow CMDB, Axonius, Lansweeper.</li>
      <li><strong>Gestión de vulnerabilidades:</strong> Qualys VMDR, Tenable.io/Nessus, Rapid7 InsightVM, OpenVAS, Wiz, Snyk.</li>
      <li><strong>Gestión de riesgos de terceros:</strong> Sphera, Archer RSA, ServiceNow GRC, Vanta, Drata, OneTrust.</li>
      <li><strong>SIEM / SOC:</strong> Splunk Enterprise Security, Microsoft Sentinel.</li>
      <li><strong>Identidad y acceso:</strong> Microsoft Entra ID, Okta.</li>
      <li><strong>Seguridad cloud:</strong> AWS Security Hub, Microsoft Defender for Cloud, Google Security Command Center.</li>
    </ul>
    ${this._h('Flujo de integracion manual (actual)')}
    ${this._steps([
      'Accede al menú Integraciones y selecciona la herramienta.',
      'Lee la guía paso a paso: cómo obtener credenciales API, qué endpoints usar y qué datos exportar.',
      'Exporta los datos desde la herramienta externa (JSON, CSV o XML según la herramienta).',
      'Importa activos a RiskHub mediante el importador CSV de Activos.',
      'Para vulnerabilidades, crea entradas manuales en el catálogo de Vulnerabilidades.',
      'Usa el Agente IA para asociar automáticamente las vulnerabilidades importadas al escenario de riesgo más relevante.',
      'Configura una alerta por email para notificar al responsable del riesgo.',
    ])}
    ${this._tip('<strong>v1.2 (roadmap):</strong> Las integraciones automatizadas permitirán configurar la URL y API key de cada herramienta directamente en RiskHub, con sincronización programada y asociación automática por IA. Las guías actuales te preparan para esta automatización futura.')}
  `;},

  get _cAudit() { return `
    ${this._p('El log de auditoría registra de forma automática e inmutable todas las operaciones de creación, modificación y eliminación realizadas en RiskHub. Proporciona trazabilidad completa para cumplimiento normativo y análisis forense.')}
    ${this._warn('<strong>Acceso restringido:</strong> Solo los usuarios con rol <strong>admin</strong> pueden consultar el log de auditoría.')}
    ${this._h('Eventos registrados automáticamente')}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
      ${[
        ['Inicio de sesión','Cada acceso exitoso: usuario, rol y timestamp.'],
        ['Riesgos','Creación, modificación y eliminación de riesgos con nivel y estado.'],
        ['Activos','Creación, modificación y eliminación de activos con tipo y código.'],
        ['Controles','Altas, actualizaciones y bajas de implementaciones de controles.'],
        ['Usuarios','Creación, modificación de rol/estado y eliminación de cuentas.'],
        ['Catálogos','Amenazas y vulnerabilidades personalizadas: creación, edición y eliminación.'],
        ['Configuración','Cambios en contexto organizacional, SMTP y reglas de alerta.'],
      ].map(([t, d]) => `
        <div style="background:var(--bg-2);border-radius:8px;padding:10px 14px;font-size:13px;">
          <div style="font-weight:600;margin-bottom:4px;color:var(--brand-purple);">${t}</div>
          <div style="color:var(--text-muted);">${d}</div>
        </div>`).join('')}
    </div>
    ${this._h('Informacion de cada entrada')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px;text-align:left;">Campo</th>
        <th style="padding:8px;text-align:left;">Descripcion</th>
      </tr></thead>
      <tbody>
        ${[
          ['Fecha y hora','Timestamp UTC preciso al segundo de cuando ocurrió la acción.'],
          ['Usuario','Nombre completo y email del usuario que realizó la operación.'],
          ['Accion','create / update / delete / login — codificado y filtrable.'],
          ['Entidad','Tipo de objeto afectado: risk, asset, control_impl, user.'],
          ['ID','Identificador interno del objeto afectado (si existe).'],
          ['Detalle','JSON con los campos más relevantes: código, nombre, estado, rol, etc.'],
        ].map((r, i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          <td style="padding:8px;font-weight:600;font-family:monospace;font-size:12px;">${r[0]}</td>
          <td style="padding:8px;">${r[1]}</td>
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Como consultar el log')}
    ${this._steps([
      'Accede al menú <strong>Auditoría</strong> en la barra lateral (visible solo para admin).',
      'Usa el filtro <strong>Tipo de entidad</strong> para ver riesgos, activos, controles, usuarios, amenazas, vulnerabilidades, configuración SMTP o reglas de alerta.',
      'Usa el filtro <strong>Acción</strong> para ver solo creaciones, modificaciones, eliminaciones o inicios de sesión.',
      'Usa los campos <strong>Desde</strong> y <strong>Hasta</strong> para acotar el log a un rango de fechas especifico. Puedes combinarlos con los otros filtros.',
      'Haz clic en <strong>Exportar CSV</strong> para descargar el log completo (con los filtros activos, incluido el rango de fechas) en formato CSV para análisis externo.',
      'Los resultados se muestran de más reciente a más antiguo, 100 entradas por página.',
      'Usa los botones Anterior/Siguiente para navegar entre páginas de resultados.',
    ])}
    ${this._h('Casos de uso tipicos')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Preparación de auditoría ISO 27001:</strong> demuestra que los cambios en el SGSI son trazables y atribuibles a usuarios identificados.</li>
      <li><strong>Investigación de incidentes:</strong> identifica quién modificó un riesgo o eliminó un activo antes de un incidente.</li>
      <li><strong>Control de cambios:</strong> verifica que los cambios en riesgos críticos fueron realizados por usuarios autorizados.</li>
      <li><strong>Cumplimiento GDPR:</strong> acredita quién tuvo acceso y modificó activos de información personal.</li>
    </ul>
    ${this._tip('<strong>Buena práctica:</strong> Revisa el log de auditoría mensualmente como parte del proceso de monitorización y revisión del SGSI (ISO 27005 cl. 12). Exporta las entradas relevantes junto con los informes de seguimiento periódico.')}
  `;},

  get _cAdmin() { return `
    ${this._p('La seccion de administracion de RiskHub agrupa las funciones exclusivas del rol <strong>admin</strong>: gestion de usuarios, log de auditoria, configuracion SMTP y mantenimiento del sistema.')}
    ${this._h('Gestion de usuarios')}
    ${this._steps([
      'Ve al menu <strong>Usuarios</strong> (solo visible para admin).',
      'Crea nuevos usuarios con email, nombre completo, rol y contrasena inicial.',
      'Cambia el rol de cualquier usuario (admin / analyst / viewer).',
      'Activa o desactiva cuentas sin eliminarlas: el historial de auditoria se conserva.',
      'Elimina usuarios que ya no deban acceder. La accion queda registrada en el log.',
    ])}
    ${this._h('Cambio de contrasena (todos los roles)')}
    ${this._p('Cualquier usuario autenticado puede cambiar su propia contrasena. Haz clic en el <strong>chip de usuario</strong> (esquina superior derecha, con tu nombre y rol) para abrir el formulario de cambio de contrasena. Se requiere introducir la contrasena actual para confirmar la identidad.')}
    ${this._tip('<strong>Seguridad:</strong> Cambia tu contrasena regularmente y usa una combinacion de letras, numeros y simbolos. La nueva contrasena debe tener al menos 8 caracteres.')}
    ${this._h('Copia de seguridad de la base de datos')}
    ${this._p('La seccion <strong>Usuarios</strong> incluye un panel de <em>Informacion del sistema</em> visible solo para administradores. Desde ahi puedes descargar una copia de la base de datos SQLite con un solo clic.')}
    ${this._steps([
      'Ve al menu <strong>Usuarios</strong>.',
      'Desplazate hasta el panel <em>Informacion del sistema</em>, al final de la pagina.',
      'Haz clic en <strong>Descargar backup DB</strong>.',
      'Se descarga un archivo <code>.db</code> con la fecha y hora actuales en el nombre.',
      'Guarda el archivo en un lugar seguro fuera del servidor.',
    ])}
    ${this._tip('El panel tambien muestra la version de RiskHub, el motor de base de datos, el tamano del archivo y un resumen del numero de entidades registradas. El evento de descarga queda registrado en el log de auditoria.')}
    ${this._h('Log de auditoria')}
    ${this._p('Ve al menu <strong>Auditoria</strong> para consultar el registro completo de operaciones. Cada accion sobre riesgos, activos, controles y usuarios queda anotada con timestamp, usuario responsable y detalle. Consulta la seccion <em>Log de Auditoria</em> de esta guia para mas informacion.')}
    ${this._h('Roles y permisos detallados')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--brand-purple);color:#fff;">
        <th style="padding:8px 12px;text-align:left;">Funcion</th>
        <th style="padding:8px 12px;text-align:center;">Admin</th>
        <th style="padding:8px 12px;text-align:center;">Analyst</th>
        <th style="padding:8px 12px;text-align:center;">Viewer</th>
      </tr></thead>
      <tbody>
        ${[
          ['Ver riesgos, activos, controles','1','1','1'],
          ['Crear / editar riesgos y activos','1','1','0'],
          ['Usar el Agente IA','1','1','0'],
          ['Generar informes PDF/Excel','1','1','1'],
          ['Configurar SMTP','1','0','0'],
          ['Crear reglas de alerta','1','1','0'],
          ['Gestionar usuarios','1','0','0'],
          ['Descargar backup de la BD','1','0','0'],
          ['Consultar log de auditoria','1','0','0'],
        ].map((r, i) => '<tr '+(i%2?'style="background:var(--bg-2);"':'')+'>'+
          '<td style="padding:8px 12px;">'+r[0]+'</td>'+
          '<td style="padding:8px 12px;text-align:center;color:'+(r[1]==='1'?'var(--brand-purple)':'var(--text-subtle)')+';"><b>'+(r[1]==='1'?'Si':'No')+'</b></td>'+
          '<td style="padding:8px 12px;text-align:center;color:'+(r[2]==='1'?'var(--brand-purple)':'var(--text-subtle)')+';"><b>'+(r[2]==='1'?'Si':'No')+'</b></td>'+
          '<td style="padding:8px 12px;text-align:center;color:'+(r[3]==='1'?'var(--brand-purple)':'var(--text-subtle)')+';"><b>'+(r[3]==='1'?'Si':'No')+'</b></td>'+
          '</tr>').join('')}
      </tbody>
    </table>
    ${this._h('Seguridad de la instalacion')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Cambia la contrasena del admin inicial en el primer acceso.</li>
      <li>Genera un RISKHUB_SECRET_KEY fuerte (minimo 64 caracteres aleatorios).</li>
      <li>No expongas el puerto de RiskHub directamente a internet. Usa un proxy inverso (nginx) con HTTPS.</li>
      <li>Realiza copias de seguridad periodicas usando el boton <em>Descargar backup DB</em> o volcando el volumen Docker <code>riskhub-data</code>.</li>
      <li>Revisa los logs del contenedor: <code>docker logs riskhub</code>.</li>
    </ul>
    ${this._h('Actualizacion de RiskHub')}
    ${this._steps([
      'En el servidor ejecuta: <code>bash /opt/riskhub/deploy.sh</code>',
      'El script realiza: git pull, docker build (sin cache) y docker compose up -d.',
      'La base de datos se preserva en el volumen Docker. No se pierden datos.',
      'Los catalogos de amenazas y vulnerabilidades se actualizan automaticamente.',
    ])}
  `;};\n\n  get _cMethodology() { return `
    ${this._p('RiskHub implementa la metodología de gestión del riesgo de seguridad de la información de <strong>ISO/IEC 27005:2018</strong> con elementos cuantitativos de <strong>MAGERIT v3</strong> del MPTFP español.')}
    ${this._h('ISO/IEC 27005:2018 — Proceso de gestion del riesgo')}
    <div style="position:relative;padding:16px;background:var(--bg-2);border-radius:8px;margin-bottom:16px;">
      ${['Establecimiento del contexto (cl. 7)','Identificación del riesgo (cl. 8.2)','Análisis del riesgo (cl. 8.3)','Evaluación del riesgo (cl. 8.4)','Tratamiento del riesgo (cl. 9)','Aceptación del riesgo (cl. 10)','Comunicación del riesgo (cl. 11)','Monitorización y revisión (cl. 12)'].map((s, i) =>
        `<div style="display:flex;align-items:center;gap:10px;margin-bottom:${i<7?'6px':'0'};">
          <span style="background:var(--brand-purple);color:#fff;border-radius:50%;width:22px;height:22px;
                       flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;">${i+1}</span>
          <span style="font-size:13px;">${s}</span>
        </div>`).join('')}
    </div>
    ${this._h('Matriz de riesgo 5x5 — ISO 27005 Annex E.2')}
    ${this._p('El nivel de riesgo se calcula como <strong>f(Probabilidad × Consecuencia)</strong> usando la matriz de 5×5 niveles del Annex E.2 de ISO 27005. El resultado es un nivel entre 0 y 8:')}
    <div style="overflow-x:auto;margin-bottom:16px;">
      <table style="border-collapse:collapse;font-size:11px;min-width:400px;">
        <thead>
          <tr>
            <th style="padding:6px;background:var(--bg-2);border:1px solid var(--border);">P \\ C</th>
            ${['1','2','3','4','5'].map(c => `<th style="padding:6px;background:var(--bg-2);border:1px solid var(--border);text-align:center;">${c}</th>`).join('')}
          </tr>
        </thead>
        <tbody>
          ${[[4,5,5,6,7],[3,4,5,6,6],[2,3,4,5,5],[1,2,3,4,5],[0,1,2,3,4]].map((row, ri) =>
            `<tr>
              <td style="padding:6px;font-weight:600;background:var(--bg-2);border:1px solid var(--border);text-align:center;">${5-ri}</td>
              ${row.map(v => {
                const bg = v>=7?'#EF444420':v>=5?'#F59E0B20':v>=3?'#FEF9C3':'#22C55E20';
                return `<td style="padding:6px;text-align:center;background:${bg};border:1px solid var(--border);font-weight:700;">${v}</td>`;
              }).join('')}
            </tr>`).join('')}
        </tbody>
      </table>
      <p style="font-size:11px;color:var(--text-muted);margin-top:4px;">P = Probabilidad (1-5), C = Consecuencia (1-5)</p>
    </div>
    ${this._h('MAGERIT v3 — Elementos metodologicos')}
    ${this._p('RiskHub incorpora elementos de MAGERIT v3 del Ministerio de Hacienda de España:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Dimensiones de seguridad:</strong> Confidencialidad (C), Integridad (I), Disponibilidad (D), Autenticidad (A), Trazabilidad (T) — mapean a las dimensiones CIA extendidas de ISO 27005.</li>
      <li><strong>Catálogo de amenazas MAGERIT:</strong> codificadas como códigos de amenaza en el Agente IA (ej. E.1, A.11, I.5).</li>
      <li><strong>Valoración de activos:</strong> escala 0-4 por dimensión, con valor máximo determinando el valor del activo (método de los peores casos).</li>
      <li><strong>Degradación × Frecuencia:</strong> el Agente IA usa este cálculo MAGERIT para estimar el nivel inherente de forma complementaria a la matriz ISO 27005.</li>
    </ul>
    ${this._h('Referencias normativas')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>ISO/IEC 27005:2018 — Information security risk management</li>
      <li>ISO/IEC 27001:2022 — Information security management systems requirements</li>
      <li>ISO/IEC 27002:2022 — Information security controls</li>
      <li>MAGERIT v3 — Metodología de Análisis y Gestión de Riesgos de los Sistemas de Información (MPTFP, España)</li>
      <li>NIST SP 800-30 r1 — Guide for Conducting Risk Assessments</li>
      <li>MITRE ATT&CK — Adversarial Tactics, Techniques and Common Knowledge</li>
    </ul>
  `;},
};
