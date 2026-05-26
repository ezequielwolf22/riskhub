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
    { id: 'policies', title: 'Politicas de seguridad', icon: '📜' },
    { id: 'internal-audits', title: 'Auditoria interna', icon: '🔍' },
    { id: 'compliance', title: 'Cumplimiento multi-framework', icon: '✅' },
    { id: 'incidents', title: 'Incidentes (NIS2)', icon: '🚨' },
    { id: 'suppliers', title: 'Proveedores (supply chain)', icon: '🔗' },
    { id: 'nonconformities', title: 'No conformidades', icon: '⚠️' },
    { id: 'tasks', title: 'Tareas de tratamiento', icon: '📌' },
    { id: 'gdpr', title: 'RGPD / Privacidad', icon: '🔒' },
    { id: 'bowtie', title: 'Diagrama Bow-Tie', icon: '🎀' },
    { id: 'ai-gap', title: 'Analisis de brechas IA', icon: '🧠' },
    { id: 'ai', title: 'Agente IA (cuestionario)', icon: '🤖' },
    { id: 'ai-chat', title: 'Chat con el Agente IA', icon: '💬' },
    { id: 'ai-documents', title: 'Documentos del Agente', icon: '📂' },
    { id: 'onboarding', title: 'Configuracion del Agente', icon: '⚙️' },
    { id: 'reports', title: 'Informes', icon: '📄' },
    { id: 'alerts', title: 'Alertas por email', icon: '🔔' },
    { id: 'integrations', title: 'Integraciones', icon: '🔌' },
    { id: 'cve', title: 'CVE Monitor', icon: '🛡️' },
    { id: 'awareness', title: 'Awareness (Infografias)', icon: '🎨' },
    { id: 'audit', title: 'Log de Auditoria', icon: '📋' },
    { id: 'admin', title: 'Administracion', icon: '👥' },
    { id: 'security', title: 'Seguridad y privacidad', icon: '🔐' },
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
      policies: this._cPolicies,
      'internal-audits': this._cInternalAudits,
      compliance: this._cCompliance,
      incidents: this._cIncidents,
      suppliers: this._cSuppliers,
      nonconformities: this._cNonConformities,
      tasks: this._cTasks,
      gdpr: this._cGdpr,
      bowtie: this._cBowtie,
      'ai-gap': this._cAiGap,
      ai: this._cAI,
      'ai-chat': this._cAiChat,
      'ai-documents': this._cAiDocuments,
      onboarding: this._cOnboarding,
      reports: this._cReports,
      alerts: this._cAlerts,
      integrations: this._cIntegrations,
      cve: this._cCve,
      awareness: this._cAwareness,
      audit: this._cAudit,
      admin: this._cAdmin,
      security: this._cSecurity,
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
      <li><strong>Revisiones de controles (30 dias):</strong> controles ISO 27002 con fecha de proxima revision en los proximos 30 dias o ya vencida. Cada fila muestra codigo, nombre y urgencia (dias restantes o vencidos).</li>
      <li><strong>KPI Sin responsable:</strong> numero de riesgos activos sin propietario asignado. En purpura si hay alguno, para incitar a asignar responsables.</li>
      <li><strong>Acciones rapidas:</strong> botones adicionales para <em>Revisiones controles vencidas</em> y <em>Sin responsable</em>. Haz clic en cualquiera para ir directamente al listado filtrado.</li>
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
    ${this._h('Valor monetario y calculo FAIR/ALE')}
    ${this._p('El campo <strong>Valor monetario (EUR)</strong> permite introducir el valor economico del activo. Si se introduce, el sistema calculara automaticamente el <strong>ALE (Annual Loss Expectancy)</strong> para cada riesgo vinculado a ese activo: <code>ALE = Valor_monetario × (Nivel_residual / 8)</code>. Este calculo es la base del modelo <strong>FAIR (Factor Analysis of Information Risk)</strong>.')}
    ${this._h('Sugerencias de riesgo con IA')}
    ${this._p('Al editar un activo existente, el boton <strong>IA: Sugerir riesgos</strong> consulta el catalogo ISO 27005 y propone los escenarios de riesgo mas relevantes para ese tipo de activo. Usa las sugerencias como punto de partida para crear los riesgos en el Registro de Riesgos.')}
    ${this._h('Jerarquia de activos')}
    ${this._p('Puedes definir un activo padre para cada activo. Esto es útil para representar dependencias: un proceso de negocio depende de varias aplicaciones, que a su vez dependen de servidores. La jerarquía ayuda a entender la propagación del impacto.')}
    ${this._h('Ordenar la tabla de activos')}
    ${this._p('Haz clic en las cabeceras <strong>Codigo</strong>, <strong>Nombre</strong>, <strong>Tipo</strong>, <strong>Max</strong>, <strong>Riesgos</strong> o <strong>Categoria</strong> para ordenar la tabla por ese campo. Un segundo clic invierte el orden. La columna activa se resalta en purpura con una flecha ▲ o ▼.')}
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
    ${this._h('Ordenar los catalogos')}
    ${this._p('Las tablas de amenazas y vulnerabilidades tienen cabeceras de columna clickeables para ordenar. En amenazas puedes ordenar por codigo, nombre, origen, categoria o numero de riesgos. En vulnerabilidades por codigo, nombre, categoria o riesgos. Un segundo clic invierte el orden.')}
    ${this._h('Exposicion en el catalogo')}
    ${this._p('La tabla de amenazas y la de vulnerabilidades muestran una columna <strong>Riesgos</strong> con el número de escenarios de riesgo vinculados a cada entrada. Haz clic en el número para abrir el registro de riesgos filtrado por esa amenaza o vulnerabilidad específica, con un banner indicando el filtro activo y un boton para quitarlo.')}
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
      <li><strong>Responsable:</strong> primer nombre del usuario propietario del riesgo. Si no hay propietario asignado, muestra un guion. La columna es ordenable.</li>
      <li><strong>Duplicar:</strong> el boton <em>Duplicar</em> en el modal de edicion crea una copia del riesgo con los mismos datos (activo, amenaza, descripcion, controles, etc.). El nuevo riesgo se crea en estado Identificado con los selectores de activo y amenaza desbloqueados para que puedas cambiarlos.</li>
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
    ${this._p('La vista <strong>Calendario</strong> muestra en una cuadricula mensual dos tipos de eventos: las <strong>fechas limite de tratamiento</strong> de los riesgos y las <strong>fechas de proxima revision</strong> de los controles ISO 27002. Es la herramienta central para planificar revisiones y detectar vencimientos de forma visual.')}
    ${this._h('Como usar el calendario')}
    ${this._steps([
      'Ve al menu <strong>Calendario</strong> (bajo "Analisis y tratamiento").',
      'El calendario muestra el mes actual. Usa los botones <- / -> para cambiar de mes, o <em>Hoy</em> para volver al mes en curso.',
      'Usa los botones <strong>Todos / Solo riesgos / Solo controles</strong> para filtrar que tipo de eventos se muestran.',
      'Pasa el cursor sobre una pastilla para ver el codigo, nombre y nivel del elemento.',
      'Haz clic en una pastilla de riesgo para abrir el detalle del riesgo directamente.',
      'Haz clic en una pastilla de control para ir a la vista de Controles.',
      'Si hay mas eventos de los que caben en una celda, se muestra "+N mas" para no saturar.',
    ])}
    ${this._h('Filtrar por tipo de evento')}
    ${this._p('Los botones <strong>Todos / Solo riesgos / Solo controles</strong> en la barra superior permiten centrarse en un solo tipo de evento sin cambiar de mes.')}
    ${this._h('Codigo de colores')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong style="color:var(--risk-high);">Rojo:</strong> riesgo con nivel residual alto (>=6).</li>
      <li><strong style="color:var(--risk-medium);">Naranja/amarillo:</strong> riesgo con nivel residual medio (4-5).</li>
      <li><strong style="color:var(--risk-low);">Verde:</strong> riesgo con nivel residual bajo (&lt;4).</li>
      <li><strong style="color:var(--brand-purple);">Morado:</strong> revision de control programada (pendiente).</li>
      <li><strong style="color:var(--brand-orange);">Naranja oscuro:</strong> revision de control vencida.</li>
    </ul>
    ${this._h('Indicadores visuales')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Celda hoy:</strong> borde purple y fondo lila.</li>
      <li><strong>Celda en rojo claro:</strong> fecha ya vencida con elementos pendientes.</li>
      <li><strong>Contadores superiores:</strong> total de vencimientos y revisiones en el mes visible, con cuantos estan ya vencidos.</li>
      <li><strong>Badge en sidebar:</strong> el numero rojo en "Riesgos" indica tratamientos vencidos; el naranja en "Controles" indica revisiones vencidas.</li>
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
    ${this._tip('Si un riesgo no aparece en el calendario, edita el riesgo y establece el campo <em>Fecha limite del plan</em>. Para controles, establece la <em>Proxima revision</em> en la implementacion del control.')}
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
    ${this._h('Ordenar y filtrar implementaciones')}
    ${this._p('En la pestana <strong>Implementaciones</strong> puedes:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Filtrar por estado:</strong> usa el selector de estado (Implementado / Parcial / Planificado / No implementado) para ver solo los controles en una fase concreta del ciclo de vida.</li>
      <li><strong>Solo revision vencida:</strong> marca el checkbox para ver exclusivamente los controles cuya fecha de proxima revision ha pasado y estan activos (no No implementado).</li>
      <li><strong>Ordenar columnas:</strong> haz clic en Control, Implementacion, Estado, Madurez, Riesgos o Proxima revision para ordenar la tabla. Un segundo clic invierte el orden.</li>
    </ul>
    ${this._tip('Filtra por estado <em>Parcial</em> y ordena por <em>Madurez</em> descendente para identificar los controles mas avanzados que necesitan un ultimo esfuerzo para alcanzar el estado <em>Implementado</em>.')}
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
    ${this._h('Campos SOA ampliados (ISO 27001:2022 cl. 6.1.3)')}
    ${this._p('Al editar una implementacion, la seccion <strong>Campos SOA</strong> permite registrar:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Razon de inclusion:</strong> Legal/regulatorio, Contractual, Gestion de riesgo o Buena practica.</li>
      <li><strong>Justificacion de exclusion:</strong> texto libre si el control no aplica a tu organizacion.</li>
      <li><strong>Referencias de evidencia:</strong> lista de documentos con titulo y URL que demuestran la implementacion del control.</li>
      <li><strong>Ultima revision SOA:</strong> fecha en que se reviso la decision de aplicabilidad.</li>
    </ul>
    ${this._p('Estos campos se exportan en el CSV SoA y en el PDF Statement of Applicability para cumplir los requisitos de auditoria ISO 27001:2022.')}
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
    ${this._p('La sección Integraciones tiene dos pestanas: <strong>Live</strong> (integraciones operativas con conexion real) y <strong>Catalogo de guias</strong> (25 herramientas con guias paso a paso para integración manual).')}

    ${this._h('SharePoint (Live — Microsoft Graph API)')}
    ${this._p('Permite importar carpetas completas de documentación SGSI desde SharePoint directamente al Agente IA de RiskHub, sin necesidad de subir archivos uno a uno. Requiere una Azure AD App Registration.')}
    ${this._h('Requisitos previos en Azure')}
    ${this._steps([
      'En Azure Portal, accede a <strong>Azure Active Directory → Registros de aplicaciones → Nueva registro</strong>.',
      'Nombra la app (ej. "RiskHub SharePoint Reader") y selecciona tipo <em>Cuentas solo de este directorio organizativo</em>.',
      'Ve a <strong>Permisos de API → Agregar permiso → Microsoft Graph → Permisos de aplicación</strong>.',
      'Añade los permisos: <code>Sites.Read.All</code> y <code>Files.Read.All</code>.',
      'Haz clic en <strong>Conceder consentimiento de administrador</strong> (requiere rol Global Admin en Azure).',
      'Ve a <strong>Certificados y secretos → Nuevo secreto de cliente</strong> y copia el valor del secreto.',
      'Copia el <strong>ID de inquilino (Tenant ID)</strong> y el <strong>ID de aplicación (Client ID)</strong> desde la página principal de la app.',
    ])}
    ${this._h('Configurar en RiskHub')}
    ${this._steps([
      'Ve a <strong>Integraciones → pestaña Live</strong>.',
      'En la tarjeta SharePoint, haz clic en <strong>Configurar</strong>.',
      'Introduce el Tenant ID, Client ID y Client Secret obtenidos en Azure.',
      'Haz clic en <strong>Guardar</strong> — las credenciales se cifran con Fernet antes de almacenarse.',
      'Usa el boton <strong>Probar conexion</strong> para verificar que RiskHub puede autenticarse con Microsoft Graph.',
    ])}
    ${this._h('Importar documentos desde SharePoint')}
    ${this._steps([
      'Tras configurar la conexion, el navegador de SharePoint se cargara automaticamente.',
      'Selecciona el <strong>Sitio</strong> de SharePoint que contiene la documentacion SGSI.',
      'Selecciona la <strong>Biblioteca de documentos</strong> (Document Library).',
      'Navega por las carpetas haciendo clic en su nombre. El icono de carpeta muestra el numero de elementos.',
      'Marca la casilla junto a cada archivo que deseas importar (PDF, DOCX, TXT, CSV).',
      'Usa <strong>Seleccionar todos los importables</strong> para marcar todos los archivos soportados de la carpeta actual.',
      'Selecciona la <strong>categoria del documento</strong> (politica, procedimiento, marco normativo, etc.).',
      'Haz clic en <strong>Importar seleccionados</strong>. Se importan hasta 20 archivos por lote (max. 20 MB cada uno).',
      'Los archivos se procesan automaticamente y quedan disponibles para el Agente IA en la seccion <em>Documentos del Agente</em>.',
    ])}
    ${this._warn('<strong>Formatos soportados:</strong> PDF, DOCX, TXT y CSV. Los archivos de otros formatos se omiten automaticamente. Tamano maximo por archivo: 20 MB.')}
    ${this._tip('<strong>Buena practica:</strong> Organiza la documentacion SGSI en SharePoint por carpetas tematicas (politicas, procedimientos, registros, evidencias) e importa cada carpeta con la categoria correspondiente en RiskHub. Esto mejora la precision del Agente IA en las consultas.')}

    ${this._h('SSO — Inicio de sesion unico (OIDC)')}
    ${this._p('RiskHub soporta autenticacion federada mediante el protocolo <strong>OpenID Connect (OIDC)</strong>, compatible con Microsoft Entra ID (Azure AD), Google Workspace, Okta y cualquier proveedor OIDC estandar. Permite a los usuarios iniciar sesion con sus credenciales corporativas sin necesidad de una cuenta RiskHub separada.')}
    ${this._h('Configurar el proveedor de identidad (IdP)')}
    ${this._steps([
      '<strong>Microsoft Entra ID (Azure AD):</strong> Ve a Azure Portal → Azure Active Directory → Registros de aplicaciones → Nueva registro. Escoge tipo "Cuentas de este directorio" y anota el <em>Tenant ID</em> y <em>Client ID</em>. En Autenticacion agrega el Redirect URI: <code>[tu-dominio]/api/sso/callback</code>. En Certificados y secretos crea un nuevo secreto.',
      '<strong>Google Workspace:</strong> Ve a Google Cloud Console → APIs y servicios → Credenciales → Crear credenciales → ID de cliente OAuth 2.0. Selecciona "Aplicacion web", configura el URI de redireccion y copia el Client ID y Secret.',
      '<strong>Okta:</strong> Ve a Applications → Create App Integration → OIDC → Web Application. Configura el Sign-in redirect URI como <code>[tu-dominio]/api/sso/callback</code> y copia el Client ID y Client Secret.',
      'Para cualquier otro proveedor: necesitas la <strong>Issuer URL</strong> (URL base OIDC, ej: <em>https://login.microsoftonline.com/{tenant-id}/v2.0</em>), el <strong>Client ID</strong> y el <strong>Client Secret</strong>.',
    ])}
    ${this._h('Configurar SSO en RiskHub')}
    ${this._steps([
      'Ve a <strong>Integraciones → pestaña Live → tarjeta SSO / OIDC</strong>.',
      'Haz clic en <strong>Configurar</strong> e introduce los datos del proveedor: Issuer URL, Client ID y Client Secret.',
      'El campo <strong>Redirect URI</strong> se completa automaticamente con la URL de tu instancia (<code>/api/sso/callback</code>). Copia este valor exacto al IdP.',
      'Configura los <strong>dominios permitidos</strong> (ej: <em>miempresa.com</em>) para restringir el acceso a usuarios del dominio corporativo. Deja en blanco para permitir cualquier dominio validado por el IdP.',
      'Selecciona el <strong>rol por defecto</strong> que se asignara a los usuarios nuevos aprovisionados via SSO (viewer recomendado).',
      'Activa <strong>Aprovisionar automaticamente</strong> si quieres que los usuarios del IdP se creen en RiskHub en su primer inicio de sesion. Si esta desactivado, el admin debe crear la cuenta primero con el mismo email.',
      'Haz clic en <strong>Guardar</strong> — las credenciales se cifran con Fernet antes de almacenarse.',
      'Usa el boton <strong>Probar conexion</strong> para verificar que RiskHub puede descubrir la configuracion OIDC del proveedor.',
    ])}
    ${this._h('Flujo de inicio de sesion via SSO')}
    ${this._steps([
      'En la pantalla de login aparece automaticamente el boton <strong>Iniciar sesion con SSO</strong> (solo si SSO esta configurado).',
      'El usuario hace clic y es redirigido al IdP corporativo (Microsoft, Google, Okta...).',
      'El usuario se autentica con sus credenciales corporativas (MFA incluido si el IdP lo requiere).',
      'El IdP redirige de vuelta a RiskHub con un codigo de autorizacion.',
      'RiskHub valida el codigo, obtiene el perfil del usuario (email, nombre) y emite un JWT de sesion.',
      'Si el usuario no existe y el aprovisionamiento automatico esta activo, se crea la cuenta con el rol por defecto.',
      'El usuario accede directamente al dashboard sin necesidad de introducir una contrasena de RiskHub.',
    ])}
    ${this._warn('<strong>Seguridad:</strong> El flujo SSO usa <em>state tokens</em> con TTL de 10 minutos para proteccion CSRF. Las credenciales del proveedor (Client Secret) se almacenan cifradas con Fernet y nunca se exponen en la interfaz. Los usuarios SSO pueden coexistir con usuarios locales (autenticacion con usuario/contrasena RiskHub).')}
    ${this._tip('<strong>Buena practica:</strong> Configura los dominios permitidos para evitar que usuarios externos a la organizacion puedan autenticarse via SSO aunque tengan cuenta en el IdP. Asigna el rol <em>viewer</em> por defecto y eleva los permisos manualmente segun necesidad.')}

    ${this._h('Catalogo de guias de integracion manual')}
    ${this._p('La pestana <strong>Catalogo de guias</strong> incluye 25 herramientas del mercado con instrucciones detalladas para integrar sus datos con RiskHub manualmente.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>ERP / Gestión de proveedores:</strong> SAP ERP / S/4HANA (OData), SAP Fieldglass / Jagger (VMS), importacion CSV universal desde cualquier ERP.</li>
      <li><strong>Gestión de activos:</strong> LeanIX, ServiceNow CMDB, Axonius, Lansweeper.</li>
      <li><strong>Gestión de vulnerabilidades:</strong> Qualys VMDR, Tenable.io/Nessus, Rapid7 InsightVM, OpenVAS, Wiz, Snyk.</li>
      <li><strong>Gestión de riesgos de terceros:</strong> Sphera, Archer RSA, ServiceNow GRC, Vanta, Drata, OneTrust.</li>
      <li><strong>SIEM / SOC:</strong> Splunk Enterprise Security, Microsoft Sentinel.</li>
      <li><strong>Identidad y acceso:</strong> Microsoft Entra ID, Okta.</li>
      <li><strong>Seguridad cloud:</strong> AWS Security Hub, Microsoft Defender for Cloud, Google Security Command Center.</li>
    </ul>
    ${this._h('Flujo de integracion manual')}
    ${this._steps([
      'Accede al menú Integraciones → Catalogo de guias y selecciona la herramienta.',
      'Lee la guía paso a paso: cómo obtener credenciales API, qué endpoints usar y qué datos exportar.',
      'Exporta los datos desde la herramienta externa (JSON, CSV o XML según la herramienta).',
      'Importa activos a RiskHub mediante el importador CSV de Activos.',
      'Para vulnerabilidades, crea entradas manuales en el catálogo de Vulnerabilidades.',
      'Usa el Agente IA para asociar automáticamente las vulnerabilidades importadas al escenario de riesgo más relevante.',
    ])}
  `;},

  get _cCve() { return `
    ${this._p('El <strong>CVE Monitor</strong> conecta RiskHub con la base de datos de vulnerabilidades NVD (NIST) en tiempo real. El agente IA analiza cada CVE contra tu inventario de activos y genera un analisis de riesgo completo: riesgo inherente, cobertura de controles, riesgo residual y acciones de mitigacion.')}
    ${this._h('Fuente de datos')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>NVD (National Vulnerability Database):</strong> base de datos oficial del NIST con mas de 250.000 CVEs. Actualizada en tiempo real con CVSS scores, vectores de ataque y listas de productos afectados (CPE).</li>
      <li><strong>Sin API key:</strong> funciona con limite de 5 peticiones/30s (suficiente para uso normal).</li>
      <li><strong>Con API key gratuita:</strong> aumenta a 50 peticiones/30s. Solicita en <em>nvd.nist.gov/developers/request-an-api-key</em>.</li>
    </ul>
    ${this._h('Configuracion inicial')}
    ${this._steps([
      'Ve a <strong>CVE Monitor → pestana Configuracion</strong>.',
      'Introduce tu API key de NVD (opcional pero recomendada para un uso intensivo).',
      'Configura la ventana de tiempo por defecto (7 dias es un buen punto de partida).',
      'Selecciona la severidad minima: CRITICAL muestra solo las mas urgentes; HIGH incluye las importantes.',
      'Activa el <strong>escaneo automatico diario</strong> si quieres que el scheduler compruebe CVEs nuevas cada 24h.',
      'Haz clic en Guardar configuracion.',
    ])}
    ${this._h('Buscar y monitorear CVEs')}
    ${this._steps([
      'Ve a la pestana <strong>Monitor CVEs</strong>.',
      'Ajusta los filtros: dias, severidad minima y keyword (ej: "apache", "windows", "openssl").',
      'Haz clic en <strong>Buscar CVEs</strong> — los resultados se obtienen de NVD en tiempo real.',
      'La tabla muestra: CVE ID (con enlace a NVD), score CVSS, descripcion, productos afectados, fecha y vector de ataque.',
      'Marca las casillas de las CVEs que quieres analizar contra tus activos.',
      'Haz clic en <strong>Analizar seleccionadas con IA</strong> para pasar a la pestana de analisis.',
    ])}
    ${this._h('Analisis de riesgo con IA (flujo principal)')}
    ${this._steps([
      'En la pestana <strong>Analisis IA</strong>, las CVEs seleccionadas aparecen precargadas.',
      'Selecciona los activos de tu inventario a evaluar (o deja todos para analizar el inventario completo).',
      'El sistema aplica primero un filtro heuristico (coincidencia CPE vs nombre/descripcion del activo) para evitar pares irrelevantes.',
      'Activa <em>Analizar todos los pares</em> si quieres un analisis exhaustivo sin filtro previo.',
      'Haz clic en <strong>Ejecutar analisis IA</strong> y espera la respuesta del agente (puede tardar 10-30 segundos segun el numero de pares).',
      'Para cada par CVE-Activo el agente evalua: si afecta al activo, riesgo inherente, cobertura de controles existentes, riesgo residual y acciones de mitigacion prioritarias.',
      'Los resultados se ordenan por riesgo residual de mayor a menor.',
    ])}
    ${this._h('Resultado del analisis por par CVE-Activo')}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
      ${[
        ['Afecta al activo','Juicio de la IA (si/no/quizas) con justificacion y nivel de confianza.'],
        ['Riesgo inherente (1-5)','Nivel sin controles, calculado desde CVSS y contexto del activo.'],
        ['Cobertura de controles','Ninguna / Parcial / Suficiente — basado en tus implementaciones ISO 27002.'],
        ['Riesgo residual (1-5)','Nivel real tras descontar la cobertura de los controles activos.'],
        ['Acciones de mitigacion','Lista priorizada con control ISO 27002 asociado y urgencia.'],
        ['Crear riesgo','Boton para registrar el riesgo directamente en el registro de RiskHub.'],
      ].map(([t,d]) => `
        <div style="background:var(--bg-2);border-radius:8px;padding:10px 14px;font-size:13px;">
          <div style="font-weight:600;margin-bottom:4px;color:var(--brand-purple);">${t}</div>
          <div style="color:var(--text-muted);">${d}</div>
        </div>`).join('')}
    </div>
    ${this._h('Crear riesgo desde una CVE')}
    ${this._p('Al hacer clic en <strong>Crear riesgo en RiskHub</strong> en cualquier resultado, el sistema registra automaticamente:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>El activo afectado vinculado al nuevo riesgo.</li>
      <li>La vulnerabilidad CVE creada en el catalogo (si no existia).</li>
      <li>Los niveles de probabilidad e impacto calculados desde el analisis.</li>
      <li>Las notas con el CVE ID, CVSS score, vector y las acciones de mitigacion propuestas.</li>
    </ul>
    ${this._warn('<strong>Contexto RAG:</strong> El agente IA utiliza los documentos SGSI que hayas subido (politicas, procedimientos, SOA) para enriquecer el analisis de cobertura de controles. Cuantos mas documentos tengas indexados, mas preciso sera el analisis residual.')}
    ${this._tip('<strong>Buena practica:</strong> Ejecuta el analisis CVE semanalmente para las CVEs CRITICAL y HIGH. Filtra por los productos de tu inventario usando el campo keyword (ej: el nombre de tu servidor web, sistema operativo o base de datos). Los resultados se pueden convertir en riesgos con un solo clic.')}
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
    ${this._h('Riesgos por usuario')}
    ${this._p('La tabla de usuarios incluye una columna <strong>Riesgos</strong> que muestra cuantos riesgos tiene asignados cada cuenta. Haz clic en el numero para navegar directamente a la vista de riesgos filtrada por ese responsable.')}
    ${this._steps([
      'Un numero en <strong>color morado</strong> indica que el usuario tiene riesgos asignados.',
      'Un numero en <strong>color rojo</strong> indica 5 o mas riesgos asignados (carga elevada).',
      'Un <strong>0 gris</strong> indica que el usuario no es responsable de ningun riesgo activo.',
      'Haz clic en el numero para ir a <em>Riesgos</em> filtrados por ese responsable.',
    ])}
    ${this._h('Ordenar la tabla de usuarios')}
    ${this._p('Haz clic en cualquier encabezado de columna para ordenar la tabla: <strong>Email</strong>, <strong>Nombre</strong>, <strong>Rol</strong>, <strong>Ultimo acceso</strong> o <strong>Riesgos</strong>. Un segundo clic invierte el orden. La columna activa se marca en morado con una flecha ▲ / ▼.')}
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
        <th style="padding:8px 12px;text-align:center;">SuperAdmin</th>
        <th style="padding:8px 12px;text-align:center;">Admin</th>
        <th style="padding:8px 12px;text-align:center;">Analyst</th>
        <th style="padding:8px 12px;text-align:center;">Viewer</th>
      </tr></thead>
      <tbody>
        ${[
          ['Ver riesgos, activos, controles','1','1','1','1'],
          ['Crear / editar riesgos y activos','1','1','1','0'],
          ['Usar el Agente IA','1','1','1','0'],
          ['Generar informes PDF/Excel','1','1','1','1'],
          ['Configurar SMTP','1','1','0','0'],
          ['Crear reglas de alerta','1','1','1','0'],
          ['Gestionar usuarios','1','1','0','0'],
          ['Descargar backup de la BD','1','1','0','0'],
          ['Consultar log de auditoria','1','1','0','0'],
          ['Control de modulos (feature flags)','1','0','0','0'],
          ['Crear usuarios SuperAdmin','1','0','0','0'],
        ].map((r, i) => '<tr '+(i%2?'style="background:var(--bg-2);"':'')+'>'+
          '<td style="padding:8px 12px;">'+r[0]+'</td>'+
          '<td style="padding:8px 12px;text-align:center;color:'+(r[1]==='1'?'var(--brand-orange)':'var(--text-subtle)')+';"><b>'+(r[1]==='1'?'Si':'No')+'</b></td>'+
          '<td style="padding:8px 12px;text-align:center;color:'+(r[2]==='1'?'var(--brand-purple)':'var(--text-subtle)')+';"><b>'+(r[2]==='1'?'Si':'No')+'</b></td>'+
          '<td style="padding:8px 12px;text-align:center;color:'+(r[3]==='1'?'var(--brand-purple)':'var(--text-subtle)')+';"><b>'+(r[3]==='1'?'Si':'No')+'</b></td>'+
          '<td style="padding:8px 12px;text-align:center;color:'+(r[4]==='1'?'var(--brand-purple)':'var(--text-subtle)')+';"><b>'+(r[4]==='1'?'Si':'No')+'</b></td>'+
          '</tr>').join('')}
      </tbody>
    </table>
    ${this._h('Control de Modulos (SuperAdmin)')}
    ${this._p('El rol <strong>SuperAdmin</strong> tiene acceso a la seccion <strong>Control de Modulos</strong> (icono de bandera en el menu lateral, solo visible para superadmin). Desde ahi puede activar o desactivar modulos completos de la aplicacion para todos los usuarios:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Los cambios son inmediatos y se aplican en la proxima recarga de pagina de cada usuario.</li>
      <li>Los modulos desactivados desaparecen del menu lateral. Los datos no se eliminan.</li>
      <li>Util para modelos de licenciamiento: activar solo los modulos contratados.</li>
    </ul>
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
  `; },

  get _cPolicies() { return `
    ${this._p('El modulo de <strong>Politicas de Seguridad</strong> gestiona el ciclo de vida completo de los documentos del SGSI, cumpliendo <strong>ISO 27001:2022 clausula 5.2</strong> (Politica de seguridad de la informacion) y <strong>clausula 7.5</strong> (Informacion documentada).')}
    ${this._h('Estados del ciclo de vida')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);"><th style="padding:8px;">Estado</th><th style="padding:8px;">Descripcion</th><th style="padding:8px;">Accion tipica</th></tr></thead>
      <tbody>
        ${[
          ['Borrador','Politica en redaccion inicial.','Asignar responsable y establecer alcance.'],
          ['En revision','Revisada por stakeholders, pendiente aprobacion.','Recabar comentarios del comite de seguridad.'],
          ['Aprobada','Aprobada formalmente. Fecha de aprobacion registrada.','Comunicar a las partes afectadas.'],
          ['Publicada','Disponible y vigente para toda la organizacion.','Realizar revision periodica (recomendado: anual).'],
          ['Obsoleta','Retirada o sustituida por version mas reciente.','Archivar y crear nueva politica o nueva version.'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          ${r.map(c => `<td style="padding:8px;">${c}</td>`).join('')}
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Campos clave')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Version:</strong> controla la evolucion del documento (ej. 1.0, 1.1, 2.0). Incrementa cuando cambia contenido significativo.</li>
      <li><strong>Clausulas ISO:</strong> referencia directa a las clausulas o controles de ISO 27001/27002 que implementa esta politica.</li>
      <li><strong>Fecha de revision:</strong> cuando vence, la fila se resalta en rojo y el contador de revision vencida aumenta. Tipicamente anual.</li>
      <li><strong>Responsable:</strong> persona encargada de mantener la politica actualizada. Deberia ser el mismo que el owner del proceso descrito.</li>
    </ul>
    ${this._h('Extraccion automatica con IA')}
    ${this._p('El boton <strong>"Extraer con IA"</strong> permite subir un documento PDF, DOCX o TXT de una politica existente. El agente IA analiza el texto y pre-rellena automaticamente los campos del formulario:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Titulo</strong> de la politica.</li>
      <li><strong>Categoria</strong> (Acceso, Criptografia, Backup, etc.).</li>
      <li><strong>Version</strong> detectada en el documento.</li>
      <li><strong>Alcance y contenido</strong> resumidos.</li>
      <li><strong>Fecha de revision / expiracion</strong> — se puede trasladar automaticamente al Calendario.</li>
      <li><strong>Clausulas ISO 27001/27002</strong> referenciadas en el documento — se vinculan con el modulo de Cumplimiento.</li>
    </ul>
    ${this._tip('Siempre revisa los campos extraidos antes de guardar. La IA puede cometer errores en documentos con formato complejo o en idiomas distintos al castellano.')}
    ${this._tip('<strong>Para auditoria ISO 27001:</strong> el auditor verificara que existe al menos una politica de seguridad aprobada por la alta direccion (cl. 5.2.a), que tiene un alcance definido y que se ha comunicado a las partes interesadas relevantes (cl. 5.2.e).')}
  `;},

  get _cInternalAudits() { return `
    ${this._p('El modulo de <strong>Auditoria Interna</strong> implementa el proceso de auditoria del SGSI requerido por <strong>ISO 27001:2022 clausula 9.2</strong>. Permite planificar programas de auditoria, registrar hallazgos y vincularlos con no conformidades para el seguimiento de acciones correctivas.')}
    ${this._h('Tipos de auditoria')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);"><th style="padding:8px;">Tipo</th><th style="padding:8px;">Descripcion</th></tr></thead>
      <tbody>
        ${[
          ['Interna','Auditoria realizada por auditores internos de la organizacion.'],
          ['Externa','Auditoria realizada por una entidad de certificacion o cliente.'],
          ['Seguimiento','Auditoria de vigilancia para verificar el mantenimiento de la certificacion.'],
          ['Recertificacion','Auditoria de renovacion del certificado ISO 27001 (cada 3 anos).'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          ${r.map(c => `<td style="padding:8px;">${c}</td>`).join('')}
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Tipos de hallazgo')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>NC Mayor:</strong> incumplimiento grave. Puede impedir la certificacion si no se resuelve antes de la auditoria de seguimiento.</li>
      <li><strong>NC Menor:</strong> incumplimiento puntual. Debe cerrarse con accion correctiva en el plazo acordado.</li>
      <li><strong>Observacion:</strong> area de mejora identificada. No requiere accion correctiva formal.</li>
      <li><strong>Oportunidad:</strong> sugerencia de mejora del auditor sin relacion con incumplimiento.</li>
      <li><strong>Conformidad:</strong> evidencia positiva de cumplimiento de un requisito.</li>
    </ul>
    ${this._h('Flujo recomendado')}
    ${this._steps([
      'Crea un programa de auditoria con alcance, objetivos y criterios definidos.',
      'Actualiza el estado a <strong>En curso</strong> al comenzar la auditoria.',
      'Registra los hallazgos durante o despues de la auditoria.',
      'Para las NCs Mayor y Menor, vincula el hallazgo a una <strong>No Conformidad</strong> existente o crea una nueva en el modulo correspondiente.',
      'Cuando todas las NCs esten cerradas y verificadas, actualiza el estado de la auditoria a <strong>Completada</strong> y escribe la conclusion.',
    ])}
    ${this._tip('<strong>Trazabilidad completa:</strong> ISO 27001 exige que los hallazgos de auditoria generen acciones correctivas documentadas (cl. 10.1). La vinculacion Hallazgo → No Conformidad garantiza esta trazabilidad para el auditor.')}
  `;},

  get _cCompliance() { return `
    ${this._p('El <strong>Dashboard de Cumplimiento</strong> calcula automaticamente tu nivel de cumplimiento para cuatro marcos normativos en base a los datos registrados en RiskHub: controles implementados, riesgos tratados, incidentes gestionados y no conformidades abiertas.')}
    ${this._h('Marcos normativos cubiertos')}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
      ${[
        ['ISO/IEC 27001:2022','Basado en: cobertura de controles SOA (cl. 6.1.3), tratamiento de riesgos (cl. 6.1.2), propietarios asignados (cl. 6.1.2), estado de riesgos (cl. 8.3) y no conformidades mayores abiertas (cl. 10.1).'],
        ['NIS2 — Directiva EU 2022/2555','Basado en: medidas tecnicas (controles), notificacion de incidentes en 72h (Art. 23), evaluacion de proveedores (Art. 21.2.d) y gestion de riesgos con tratamiento.'],
        ['NIST CSF 2.0','Seis funciones: GOVERN (propietarios y controles), IDENTIFY (riesgos por activo), PROTECT (controles implementados), DETECT (incidentes registrados), RESPOND (incidentes resueltos), RECOVER (lecciones aprendidas documentadas).'],
        ['ENS RD 311/2022','Esquema Nacional de Seguridad espanol. Basado en: implementacion de controles (Anexo II), responsables asignados y mejora continua (no conformidades abiertas).'],
      ].map(([t,d]) => `
        <div style="background:var(--bg-2);border-radius:8px;padding:12px 14px;font-size:13px;">
          <div style="font-weight:700;color:var(--brand-purple);margin-bottom:6px;">${t}</div>
          <div style="color:var(--text-muted);line-height:1.5;">${d}</div>
        </div>`).join('')}
    </div>
    ${this._h('Como interpretar la puntuacion')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--brand-purple);color:#fff;">
        <th style="padding:8px;">Rango</th><th style="padding:8px;">Etiqueta</th><th style="padding:8px;">Interpretacion</th>
      </tr></thead>
      <tbody>
        ${[
          ['75-100','Conforme','Nivel de cumplimiento aceptable para auditoria.','#22C55E'],
          ['50-74','Parcial','Brechas identificadas. Plan de mejora recomendado.','#F59E0B'],
          ['25-49','Deficiente','Brechas significativas. Requiere accion prioritaria.','#EF4444'],
          ['0-24','Critico','Incumplimiento grave. Riesgo regulatorio alto.','#7C3AED'],
        ].map(([r,l,d,c],i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          <td style="padding:8px;font-weight:700;color:${c};">${r}</td>
          <td style="padding:8px;font-weight:600;">${l}</td>
          <td style="padding:8px;color:var(--text-muted);">${d}</td>
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Brechas identificadas')}
    ${this._p('El dashboard muestra las brechas especificas para cada marco con referencia al articulo o clausula normativa afectada. Cada brecha indica que dato falta o que proceso esta incompleto. Usa estas brechas como checklist de mejora.')}
    ${this._tip('<strong>Nota:</strong> Las puntuaciones son estimaciones basadas en los datos registrados. Una auditoria formal puede revelar brechas adicionales no reflejadas en RiskHub.')}
  `;},

  get _cIncidents() { return `
    ${this._p('El modulo de <strong>Incidentes de Seguridad</strong> permite gestionar el ciclo de vida completo de un incidente, desde la deteccion hasta el cierre, incluyendo el flujo de notificacion obligatorio de la directiva <strong>NIS2</strong>.')}
    ${this._h('Ciclo de vida de un incidente')}
    ${this._steps([
      '<strong>Abierto (Open):</strong> incidente detectado, pendiente de investigacion.',
      '<strong>En investigacion (Investigating):</strong> equipo de respuesta activo.',
      '<strong>Contenido (Contained):</strong> propagacion detenida, impacto limitado.',
      '<strong>Resuelto (Resolved):</strong> causa raiz eliminada, sistemas restaurados.',
      '<strong>Cerrado (Closed):</strong> documentado, lecciones aprendidas registradas.',
    ])}
    ${this._h('Clasificacion por severidad')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px;">Severidad</th><th style="padding:8px;">Descripcion</th><th style="padding:8px;">Ejemplo</th>
      </tr></thead>
      <tbody>
        ${[
          ['P1 - Critico','Impacto critico en sistemas esenciales. Escalado inmediato a direccion.','Ransomware, brecha masiva de datos, caida de servicios esenciales.'],
          ['P2 - Alto','Impacto significativo. Plan de respuesta activado en < 4h.','Compromiso de cuentas privilegiadas, exfiltracion de datos confidenciales.'],
          ['P3 - Medio','Impacto moderado. Resolucion en < 24h.','Malware en equipo aislado, acceso no autorizado a informacion no critica.'],
          ['P4 - Bajo','Impacto minimo. Tratamiento planificado.','Politica de contrasenas no seguida, acceso fisico no autorizado a zona de bajo riesgo.'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          ${r.map(c => `<td style="padding:8px;">${c}</td>`).join('')}
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Flujo de notificacion NIS2 (Art. 23)')}
    ${this._p('Para entidades esenciales e importantes bajo la directiva NIS2, los incidentes significativos deben notificarse al CSIRT o autoridad competente nacional:')}
    ${this._steps([
      '<strong>Alerta inicial (24h):</strong> notificacion sin demora injustificada, dentro de las 24 horas desde la deteccion.',
      '<strong>Notificacion intermedia (72h):</strong> evaluacion de impacto y primeras medidas adoptadas.',
      '<strong>Informe final (1 mes):</strong> analisis completo de causa raiz, impacto y medidas de mitigacion.',
    ])}
    ${this._p('Marca el checkbox <em>"Requiere notificacion NIS2"</em> al crear el incidente. Una vez enviada la notificacion, registra la fecha en el campo correspondiente. El dashboard de cumplimiento refleja los incidentes pendientes de notificacion como brecha NIS2.')}
    ${this._h('Lecciones aprendidas')}
    ${this._p('Al cerrar un incidente, documenta siempre las lecciones aprendidas. Estas contribuyen a mejorar el SGSI y son consideradas en el calculo del indicador RECOVER del NIST CSF 2.0.')}
    ${this._tip('<strong>NIS2:</strong> Solo las entidades esenciales e importantes en sectores como energia, transporte, banca, agua, infraestructura digital, administracion publica y salud estan sujetas al Art. 23 de la directiva.')}
  `;},

  get _cSuppliers() { return `
    ${this._p('El modulo de <strong>Proveedores y Cadena de Suministro</strong> permite gestionar el riesgo de terceros conforme a la directiva <strong>NIS2 Art. 21.2.d</strong> e <strong>ISO 27001 A.15 / ISO 27002 cl. 5.19-5.22</strong>.')}
    ${this._h('Por que gestionar el riesgo de proveedores')}
    ${this._p('La mayoria de los ataques modernos llegan a traves de la cadena de suministro (SolarWinds, Log4j, ataques a proveedores de servicios gestionados). La directiva NIS2 impone a las entidades reguladas la obligacion de evaluar y gestionar el riesgo de sus proveedores criticos.')}
    ${this._h('Clasificacion por nivel de riesgo')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px;">Nivel</th><th style="padding:8px;">Descripcion</th><th style="padding:8px;">Accion</th>
      </tr></thead>
      <tbody>
        ${[
          ['Critico','Acceso a sistemas criticos, datos sensibles o infraestructura esencial.','Evaluacion anual obligatoria. Clausulas contractuales de ciberseguridad.'],
          ['Alto','Acceso a sistemas importantes o datos confidenciales.','Evaluacion anual. Cuestionario de seguridad.'],
          ['Medio','Acceso limitado a sistemas no criticos.','Evaluacion bienal. Cuestionario simplificado.'],
          ['Bajo','Sin acceso a sistemas o datos. Proveedor de bajo impacto.','Revision periodica segun politica interna.'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          ${r.map(c => `<td style="padding:8px;">${c}</td>`).join('')}
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Proveedor critico NIS2')}
    ${this._p('Marca el flag <em>"Proveedor critico NIS2"</em> para los proveedores cuya interrupcion o compromiso podria afectar a la continuidad de los servicios esenciales de tu organizacion. Estos proveedores tienen prioridad en las evaluaciones y deben incluirse en el plan de gestion de incidentes.')}
    ${this._h('Seguimiento de evaluaciones')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Ultima evaluacion:</strong> registra la fecha de la ultima evaluacion de seguridad del proveedor.</li>
      <li><strong>Proxima evaluacion:</strong> planifica cuando debe realizarse la siguiente evaluacion.</li>
      <li><strong>Badge vencida:</strong> el dashboard de cumplimiento muestra los proveedores sin evaluacion como brecha NIS2.</li>
    </ul>
    ${this._h('Cuestionarios de seguridad (NIS2 Art. 21.2.d)')}
    ${this._p('Desde la pestana <strong>Cuestionarios de seguridad</strong> dentro de Proveedores puedes enviar evaluaciones automatizadas a tus proveedores sin que necesiten cuenta en RiskHub:')}
    ${this._steps([
      'Pulsa <strong>+ Nuevo cuestionario</strong> y selecciona el proveedor.',
      'Se genera un enlace publico con token seguro. Copialo y enviaselo al contacto del proveedor por email.',
      'El proveedor responde 10 preguntas NIS2+ISO 27001 (Si/No/Parcialmente) desde su navegador.',
      'Al enviar, se calcula la puntuacion (0-100) y se actualiza el score del proveedor automaticamente.',
      'Revisa puntuaciones y respuestas desde la tabla de cuestionarios.',
    ])}
    ${this._tip('<strong>Buena practica:</strong> Incluye clausulas contractuales de ciberseguridad en todos los contratos con proveedores criticos: derecho de auditoria, notificacion de incidentes en 24h, cifrado de datos y planes de continuidad.')}
  `;},

  get _cNonConformities() { return `
    ${this._p('El modulo de <strong>No Conformidades y Acciones Correctivas (CAR)</strong> implementa el proceso de mejora continua requerido por <strong>ISO 27001:2022 clausula 10.1</strong>.')}
    ${this._h('Que es una no conformidad')}
    ${this._p('Una no conformidad (NC) es el incumplimiento de un requisito del SGSI. Puede surgir de una auditoria interna, auditoria externa (de certificacion), revision por la direccion, incidente de seguridad o inspeccion regulatoria.')}
    ${this._h('Tipos de no conformidad')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px;">Tipo</th><th style="padding:8px;">Descripcion</th><th style="padding:8px;">Impacto en auditoria</th>
      </tr></thead>
      <tbody>
        ${[
          ['Mayor','Incumplimiento grave de un requisito normativo. El sistema no cumple su proposito.','Puede bloquear la certificacion ISO 27001.'],
          ['Menor','Incumplimiento puntual que no afecta al sistema global.','No bloquea la certificacion pero debe cerrarse.'],
          ['Observacion','Area de mejora identificada, no es incumplimiento formal.','Informativa. No requiere accion correctiva formal.'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          ${r.map(c => `<td style="padding:8px;">${c}</td>`).join('')}
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Ciclo de vida de una NC')}
    ${this._steps([
      '<strong>Abierta (Open):</strong> NC identificada y documentada con causa raiz y accion correctiva propuesta.',
      '<strong>En proceso (In progress):</strong> accion correctiva en ejecucion. Responsable asignado.',
      '<strong>Pendiente verificacion (Pending):</strong> accion completada, pendiente de verificar su eficacia.',
      '<strong>Cerrada (Closed):</strong> NC resuelta y eficacia verificada. Fecha de cierre registrada.',
    ])}
    ${this._h('Campos clave de una NC')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Clausula ISO:</strong> referencia exacta del requisito incumplido (ej. 6.1.2, 9.2, A.8.2).</li>
      <li><strong>Causa raiz:</strong> analisis de por que se produjo la no conformidad (5 por ques, diagrama de Ishikawa, etc.).</li>
      <li><strong>Accion correctiva:</strong> medidas concretas para eliminar la causa raiz (no solo el sintoma).</li>
      <li><strong>Fecha limite:</strong> plazo maximo para resolver la NC. Las NC vencidas se resaltan en rojo.</li>
      <li><strong>Evidencias:</strong> referencia a los documentos o registros que demuestran la resolucion.</li>
    </ul>
    ${this._h('Impacto en el dashboard de cumplimiento')}
    ${this._p('El numero de no conformidades mayores abiertas penaliza directamente el indicador ISO 27001 del dashboard de cumplimiento. Cada NC mayor abierta reduce la puntuacion en 20 puntos. Cierra las NCs mayores para mejorar tu puntuacion de cumplimiento.')}
    ${this._tip('<strong>Para auditoria ISO 27001:</strong> todas las NCs detectadas en la auditoria de certificacion deben estar cerradas (con evidencia) antes de la auditoria de seguimiento o renovacion.')}
  `;},

  get _cTasks() { return `
    ${this._p('El <strong>tablero Kanban de tareas</strong> convierte el plan de tratamiento de riesgos en tareas accionables, asignables a personas y con fechas limite. Cumple la exigencia de ISO 27005 cl. 9.2 (<em>Preparacion e implementacion del plan de tratamiento</em>) y permite seguimiento operativo diario.')}
    ${this._h('Columnas del tablero')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px;">Columna</th><th style="padding:8px;">Significado</th>
      </tr></thead>
      <tbody>
        ${[
          ['Pendiente','Tarea creada, aun no iniciada.'],
          ['En progreso','Responsable trabajando activamente en la tarea.'],
          ['Bloqueado','Progreso detenido por un impedimento externo (proveedor, presupuesto, etc.).'],
          ['Completado','Tarea terminada y medida de mitigacion aplicada.'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          ${r.map(c => `<td style="padding:8px;">${c}</td>`).join('')}
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Prioridad de tareas')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Critica:</strong> tarea vinculada a un riesgo P1 o con fecha limite inminente.</li>
      <li><strong>Alta:</strong> vinculada a riesgo residual >= 6.</li>
      <li><strong>Media:</strong> riesgo residual 3-5 o tarea de mantenimiento.</li>
      <li><strong>Baja:</strong> mejoras opcionales y de largo plazo.</li>
    </ul>
    ${this._h('Flujo de trabajo recomendado')}
    ${this._steps([
      'Al crear o revisar un riesgo con tratamiento <strong>Modificacion</strong>, crea una o varias tareas vinculadas al riesgo.',
      'Asigna la tarea a la persona responsable de ejecutarla (puede ser diferente al owner del riesgo).',
      'Establece una fecha limite coherente con el <em>treatment_due_date</em> del riesgo.',
      'Mueve las tareas por las columnas usando los botones de flecha o editando su estado.',
      'Cuando todas las tareas de un riesgo esten en <strong>Completado</strong>, revisa el nivel residual y actualiza el estado del riesgo a <strong>Tratado</strong>.',
    ])}
    ${this._h('Indicadores del tablero')}
    ${this._p('La barra de estadisticas superior muestra: total de tareas, tareas en progreso, tareas bloqueadas y tareas vencidas (fecha limite pasada y no completadas). El badge naranja en el sidebar del menu lateral indica el numero de tareas vencidas activas.')}
    ${this._tip('<strong>Consejo:</strong> vincula cada tarea al riesgo correspondiente para poder tener trazabilidad completa desde el riesgo hasta la accion ejecutada. Esta trazabilidad es requerida en auditorias ISO 27001.')}
  `;},

  get _cGdpr() { return `
    ${this._p('El modulo <strong>RGPD / Privacidad</strong> implementa las dos obligaciones documentales clave del <strong>Reglamento General de Proteccion de Datos (RGPD/GDPR)</strong>: el Registro de Actividades de Tratamiento (Art. 30) y las Evaluaciones de Impacto sobre la Proteccion de Datos — DPIA (Art. 35).')}
    ${this._h('Registro de actividades de tratamiento (Art. 30)')}
    ${this._p('Toda organizacion con 250+ empleados o que realice tratamientos de alto riesgo debe mantener este registro. Cada actividad documenta:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Finalidades:</strong> para que se tratan los datos.</li>
      <li><strong>Categorias de datos:</strong> tipos de datos personales (nombre, email, datos de salud, etc.).</li>
      <li><strong>Base legal:</strong> consentimiento, contrato, obligacion legal, intereses legitimos...</li>
      <li><strong>Categorias de interesados:</strong> clientes, empleados, proveedores...</li>
      <li><strong>Periodo de retencion:</strong> cuanto tiempo se conservan los datos.</li>
      <li><strong>Destinatarios:</strong> a quien se comunican o ceden los datos.</li>
      <li><strong>Transferencias internacionales:</strong> si se envian datos fuera de la UE y con que garantias.</li>
    </ul>
    ${this._h('DPIA — Evaluacion de impacto (Art. 35)')}
    ${this._p('Obligatoria cuando el tratamiento es susceptible de entrañar un alto riesgo para los derechos y libertades de las personas: uso de nuevas tecnologias, tratamiento a gran escala de categorias especiales, videovigilancia sistematica, perfilado, etc.')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--brand-purple);color:#fff;">
        <th style="padding:8px;">Estado</th><th style="padding:8px;">Descripcion</th>
      </tr></thead>
      <tbody>
        ${[
          ['Pendiente','DPIA identificada como necesaria, pendiente de realizar.'],
          ['En curso','DPIA en proceso de elaboracion. Equipo asignado.'],
          ['Aprobada','DPIA completada y aprobada. Nivel de riesgo residual aceptable. Fecha de aprobacion registrada automaticamente.'],
          ['Rechazada','Los riesgos identificados son inaceptables. Requiere redisenar el tratamiento o abandonarlo.'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          ${r.map(c => `<td style="padding:8px;">${c}</td>`).join('')}
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Cuestionarios de seguridad a proveedores')}
    ${this._p('Desde la pestana <strong>Cuestionarios de seguridad</strong> dentro de Proveedores, puedes enviar un cuestionario automatizado de 10 preguntas NIS2+ISO 27001 a tus proveedores:')}
    ${this._steps([
      'Crea un cuestionario asociado a un proveedor y establece fecha de expiracion (30 dias por defecto).',
      'Copia el enlace publico generado y enviaselo por email al contacto del proveedor.',
      'El proveedor accede al enlace sin necesidad de cuenta en RiskHub y responde las preguntas (Si/No/Parcialmente).',
      'Al enviar, se calcula automaticamente la puntuacion (0-100) y se actualiza el score del proveedor.',
      'Revisa los resultados en la tabla de cuestionarios.',
    ])}
    ${this._tip('<strong>Privacidad by design (Art. 25):</strong> La vinculacion entre el Registro Art. 30 y las DPIAs Art. 35 facilita demostrar el cumplimiento del principio de privacidad desde el diseno, exigido expresamente por el RGPD.')}
  `;},

  get _cBowtie() { return `
    ${this._p('El <strong>Diagrama Bow-Tie</strong> es una tecnica de visualizacion de riesgos originada en la industria de petroleo y gas (Shell) y adoptada ampliamente en gestion de riesgos de seguridad. Representa graficamente la relacion entre causas, el evento de riesgo central y sus consecuencias.')}
    ${this._h('Como leer un Bow-Tie')}
    <div style="background:var(--bg-2);border-radius:8px;padding:16px;margin-bottom:16px;font-size:13px;">
      <div style="display:grid;grid-template-columns:1fr 80px 1fr;gap:16px;align-items:center;text-align:center;">
        <div style="background:var(--brand-purple-4);border:1px solid var(--brand-purple);border-radius:8px;padding:12px;">
          <div style="font-weight:700;color:var(--brand-purple);margin-bottom:4px;">CAUSAS (izquierda)</div>
          <div style="font-size:12px;color:var(--text-muted);">Amenaza principal + Vulnerabilidades que la facilitan</div>
        </div>
        <div style="background:var(--risk-high);border-radius:50%;width:64px;height:64px;margin:0 auto;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:11px;">RIESGO</div>
        <div style="background:var(--brand-orange-4);border:1px solid var(--brand-orange);border-radius:8px;padding:12px;">
          <div style="font-weight:700;color:var(--brand-orange);margin-bottom:4px;">CONSECUENCIAS (derecha)</div>
          <div style="font-size:12px;color:var(--text-muted);">Impactos potenciales + Controles que los mitigan</div>
        </div>
      </div>
    </div>
    ${this._h('Como acceder al Bow-Tie en RiskHub')}
    ${this._steps([
      'Navega a la vista <strong>Riesgos</strong> y abre cualquier riesgo existente pulsando "Ver".',
      'En la barra de acciones del modal, pulsa el boton <strong>Bow-Tie</strong>.',
      'El diagrama SVG muestra la amenaza y las vulnerabilidades asociadas a la izquierda, el circulo central con el codigo del riesgo y nivel residual, y los controles implementados a la derecha.',
      'Usa el boton "Volver al riesgo" para regresar al formulario de edicion sin cerrar el flujo.',
    ])}
    ${this._h('Interpretacion del color central')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><span style="color:#22C55E;font-weight:700;">Verde</span> — nivel residual bajo (0-2): riesgo aceptable.</li>
      <li><span style="color:#F59E0B;font-weight:700;">Amarillo</span> — nivel residual medio (3-4): monitorizar.</li>
      <li><span style="color:#F97316;font-weight:700;">Naranja</span> — nivel residual moderado-alto (5-6): plan de tratamiento activo.</li>
      <li><span style="color:#EF4444;font-weight:700;">Rojo</span> — nivel residual alto (7-8): accion inmediata requerida.</li>
    </ul>
    ${this._tip('<strong>Para auditorias:</strong> El diagrama Bow-Tie es una herramienta de comunicacion muy valorada en auditorias ISO 27001 para demostrar la comprension de los escenarios de riesgo y la adecuacion de los controles seleccionados.')}
  `;},

  get _cAiGap() { return `
    ${this._p('El <strong>Analisis de brechas IA (M9)</strong> examina el estado de implementacion de tus controles ISO 27002 y genera un informe de brechas adaptado al framework normativo seleccionado: ISO 27001, NIS2, NIST CSF 2.0 o ENS.')}
    ${this._h('Donde encontrarlo')}
    ${this._p('En la vista <strong>Cumplimiento</strong>, al final de la pagina aparece el panel "Analisis de brechas de controles". Selecciona el framework y pulsa <strong>Analizar brechas</strong>.')}
    ${this._h('Que analiza')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Cobertura efectiva:</strong> porcentaje de controles implementados + parciales ponderados (implementado=1, parcial=0.5).</li>
      <li><strong>Temas con menor cobertura:</strong> identifica los temas ISO 27002 (Seguridad fisica, Gestion de accesos, etc.) con menor porcentaje de controles implementados (&lt;40%).</li>
      <li><strong>Problemas SOA (cl. 6.1.3):</strong> controles sin razon de inclusion, sin evidencias adjuntas y con revisiones vencidas.</li>
      <li><strong>Controles criticos sin implementar:</strong> controles no implementados que no tienen justificacion de exclusion documentada.</li>
      <li><strong>Recomendaciones:</strong> lista priorizada de acciones segun el framework seleccionado.</li>
    </ul>
    ${this._h('Recomendaciones por framework')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px;">Framework</th><th style="padding:8px;">Enfoque del analisis</th>
      </tr></thead>
      <tbody>
        ${[
          ['ISO 27001','SOA completo: razon de inclusion, evidencias y exclusiones justificadas (cl. 6.1.3).'],
          ['NIS2','Controles de gestion de incidentes (Art. 21.2.b) y cadena de suministro (Art. 21.2.d).'],
          ['NIST CSF','Funcion PROTECT (controles tecnicos) y DETECT (monitorizacion).'],
          ['ENS','Implementacion del Anexo II y asignacion de responsables.'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          ${r.map(c => `<td style="padding:8px;">${c}</td>`).join('')}
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._tip('<strong>Uso recomendado:</strong> ejecuta el analisis una vez al mes o antes de una auditoria para detectar y corregir brechas documentales. Complementa las puntuaciones del dashboard de cumplimiento con acciones concretas.')}
  `;},

  get _cAwareness() { return `
    ${this._p('El modulo <strong>Awareness</strong> usa el agente IA para generar infografias de concienciacion de seguridad adaptadas al contexto de tu organizacion, los riesgos activos y la industria. Las infografias se pueden editar, personalizar con tu marca y exportar en PDF listas para distribuir.')}

    ${this._h('Plantillas disponibles')}
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px;">
      ${[
        ['🚨 Alerta de Riesgo', 'Rojo/naranja. Para comunicar un riesgo activo o critico con urgencia.'],
        ['✅ Buenas Practicas', 'Purpura. Lista de consejos y habitos de seguridad recomendados.'],
        ['📜 Politica Corporativa', 'Azul. Recordatorio de politicas internas de seguridad.'],
        ['⚠️ Amenaza del Mes', 'Oscuro. Descripcion de una amenaza emergente con indicadores.'],
        ['🎣 Anti-Phishing', 'Naranja. Concienciacion sobre phishing e ingenieria social.'],
      ].map(([t,d]) => `
        <div style="background:var(--bg-2);border-radius:8px;padding:10px 14px;font-size:13px;">
          <div style="font-weight:600;margin-bottom:4px;">${t}</div>
          <div style="color:var(--text-muted);">${d}</div>
        </div>`).join('')}
    </div>

    ${this._h('Generador (chat con IA)')}
    ${this._steps([
      'Ve a <strong>Awareness → Generador</strong>.',
      'Elige una plantilla sugerida o deja que la IA decida segun el contexto.',
      'Describe la infografia que necesitas en el campo de texto. Cuanto mas especifico seas, mejor sera el resultado. Puedes usar los accesos rapidos (Anti-Phishing, Contrasenas, Teletrabajo, etc.).',
      'Pulsa <strong>Generar infografia con IA</strong>. El agente analiza los riesgos activos, el contexto de tu organizacion y genera el contenido estructurado (10-20 segundos).',
      'Revisa la preview en tiempo real. Si el resultado es satisfactorio, pulsa <strong>Editar y guardar</strong> para pasar al editor.',
    ])}

    ${this._h('Editor de contenido')}
    ${this._p('El editor permite modificar todos los campos de la infografia con actualizacion de preview en tiempo real:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Plantilla y urgencia:</strong> cambia el tipo y el nivel (Critico / Alto / Medio / Bajo).</li>
      <li><strong>Titulo y subtitulo:</strong> el titulo aparece en la cabecera, maximo 55 caracteres.</li>
      <li><strong>Mensaje principal:</strong> texto destacado en la columna izquierda.</li>
      <li><strong>Puntos clave:</strong> uno por linea, hasta 5 puntos.</li>
      <li><strong>Haz esto / Evita esto:</strong> lista de acciones positivas y negativas.</li>
      <li><strong>Estadistica destacada:</strong> un dato impactante (ej: "91%") con su descripcion.</li>
      <li><strong>Llamada a la accion y contacto:</strong> aparecen en el pie de la infografia.</li>
      <li><strong>Hashtags:</strong> separados por espacio, max 4.</li>
    </ul>
    ${this._p('Cuando termines de editar, asigna un titulo al documento, selecciona el estado (<em>Borrador</em> o <em>Publicado</em>) y pulsa <strong>Guardar</strong>. Desde la misma pantalla puedes exportar el PDF.')}

    ${this._h('Exportacion PDF')}
    ${this._p('La exportacion genera un PDF en formato A4 apaisado (landscape) optimizado para imprimir en A3/A4 o proyectar en pantalla. El PDF incluye:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Logo de tu empresa (si esta configurado en Marca).</li>
      <li>Colores de marca personalizados aplicados a la cabecera y elementos de acento.</li>
      <li>Nombre de la empresa en la cabecera.</li>
      <li>Todos los campos del contenido: titulo, puntos clave, hacer/no hacer, estadistica, CTA, hashtags.</li>
      <li>Layout de dos columnas con separador central y pie de pagina de marca.</li>
    </ul>

    ${this._h('Configuracion de marca (Branding)')}
    ${this._steps([
      'Ve a <strong>Awareness → Marca</strong>.',
      'Selecciona tu color principal y secundario corporativos usando el selector de color o introduciendo el codigo hex (#RRGGBB).',
      'Introduce el nombre de tu empresa — aparecera en la cabecera del PDF.',
      'Sube tu logo en formato PNG, JPG o SVG (max 2 MB). Se almacena en el servidor.',
      'La preview se actualiza en tiempo real para que veas como quedara la infografia con tu marca.',
      'Pulsa <strong>Guardar configuracion de marca</strong>. La marca se aplica automaticamente a todos los PDF exportados.',
    ])}

    ${this._h('Biblioteca')}
    ${this._p('La pestana <strong>Biblioteca</strong> muestra todas las infografias guardadas en formato de tarjetas con preview. Desde cada tarjeta puedes:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Abrir la infografia en el editor para modificarla.</li>
      <li>Exportar directamente a PDF sin abrir el editor.</li>
      <li>Ver el estado (Borrador / Publicado) y la fecha de ultima modificacion.</li>
    </ul>
    ${this._tip('<strong>Buena practica:</strong> Genera una infografia mensual de "Amenaza del Mes" basandote en las CVEs mas criticas detectadas por el CVE Monitor. Luego distribuyela por email o pantallas digitales. Guarda las infografias publicadas como biblioteca de conocimiento de awareness de tu organizacion.')}
  `;},

  get _cSecurity() { return `
    ${this._p('RiskHub esta disenado para procesar informacion <strong>confidencial de seguridad corporativa</strong>. Esta pagina describe todas las capas de proteccion activas y las acciones adicionales recomendadas para despliegues con datos de alta clasificacion.')}
    ${this._warn('<strong>Puedes (y debes) subir documentacion real:</strong> politicas, procedimientos, evaluaciones de riesgo, evidencias de auditoria, SOA, contratos con proveedores. La plataforma esta preparada para ello.')}

    ${this._h('Capas de cifrado activas')}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
      ${[
        ['Documentos en disco', 'Fernet (AES-128-CBC + HMAC-SHA256): los archivos se cifran con la clave del servidor antes de escribirse en disco. Un atacante con acceso al sistema de archivos no puede leer los documentos sin el SECRET_KEY.'],
        ['API keys e integraciones', 'Todas las claves de API (agente IA, SharePoint, CVE, SSO client_secret) se cifran con Fernet antes de guardarse en la base de datos.'],
        ['Contrasenas de usuario', 'bcrypt con factor de coste 12. Nunca se almacena la contrasena en claro.'],
        ['Tokens de sesion', 'JWT HS256 firmados con el SECRET_KEY. Expiran a las 8 horas.'],
        ['Cifrado en transito', 'HSTS activado (max-age=31536000 + preload). Requiere nginx + TLS delante de la app (ver seccion de instalacion).'],
        ['Anonimizacion IA', 'IPs, emails, dominios, telefonos, DNI/NIF y datos bancarios (IBAN) se reemplazan por tokens antes de enviar contexto al agente IA externo.'],
      ].map(([t,d]) => `
        <div style="background:var(--bg-2);border-radius:8px;padding:10px 14px;font-size:13px;">
          <div style="font-weight:600;margin-bottom:4px;color:var(--brand-purple);">${t}</div>
          <div style="color:var(--text-muted);">${d}</div>
        </div>`).join('')}
    </div>

    ${this._h('Cabeceras de seguridad HTTP (OWASP A05)')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px 12px;text-align:left;border:1px solid var(--border);">Cabecera</th>
        <th style="padding:8px 12px;text-align:left;border:1px solid var(--border);">Proteccion</th>
      </tr></thead>
      <tbody>
        ${[
          ['Content-Security-Policy', 'Bloquea scripts, estilos e iframes de origenes externos. Sin CDNs.'],
          ['X-Content-Type-Options: nosniff', 'Evita MIME-sniffing en uploads (OWASP A08).'],
          ['X-Frame-Options: DENY', 'Bloquea clickjacking via iframes.'],
          ['Strict-Transport-Security', 'Fuerza HTTPS en todos los navegadores que hayan visitado la app.'],
          ['Cache-Control: no-store', 'Todos los endpoints /api/* impiden que el navegador o proxies cacheen datos confidenciales.'],
          ['Cross-Origin-Opener-Policy', 'Aislamiento de contexto — protege contra XS-Leaks.'],
          ['Cross-Origin-Resource-Policy', 'Bloquea que otros origenes carguen recursos internos.'],
          ['Permissions-Policy', 'Deshabilita GPS, microfono, camara, pagos y USB desde la app.'],
        ].map(([h,d],i) => `<tr style="${i%2===1?'background:var(--bg-2);':''}">
          <td style="padding:7px 12px;border:1px solid var(--border);font-family:monospace;font-size:12px;">${h}</td>
          <td style="padding:7px 12px;border:1px solid var(--border);">${d}</td>
        </tr>`).join('')}
      </tbody>
    </table>

    ${this._h('Control de acceso y autenticacion')}
    ${this._p('RiskHub usa un modelo de roles jerarquico. Cada rol hereda los permisos del anterior:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>viewer:</strong> lectura de activos, riesgos y controles. Sin edicion.</li>
      <li><strong>analyst:</strong> creacion y edicion de riesgos, activos, controles, incidentes. Sin gestion de usuarios.</li>
      <li><strong>admin:</strong> todo lo anterior + gestion de usuarios, configuracion SMTP, backups, log de auditoria.</li>
      <li><strong>superadmin:</strong> todo lo anterior + feature flags, licenciamiento, acceso a todos los tenants.</li>
    </ul>

    ${this._h('Anonimizacion configurable del Agente IA')}
    ${this._p('El agente IA procesa datos del contexto de tu organizacion. Para proteger la privacidad ante la API externa (Claude), RiskHub aplica anonimizacion antes de enviar cualquier dato:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Nivel bajo (low):</strong> anonimiza direcciones IP y emails.</li>
      <li><strong>Nivel medio (medium):</strong> lo anterior + nombres de dominio + numeros de telefono.</li>
      <li><strong>Nivel alto (high):</strong> lo anterior + DNI/NIF/CIF + IBAN + tarjetas de credito + mensajes del propio usuario.</li>
    </ul>
    ${this._p('Los tokens son consistentes: el mismo valor siempre produce el mismo token (<code>[IP_1]</code>, <code>[EMAIL_2]</code>, etc.) para que el agente pueda razonar sin exponer el dato real. Configura el nivel en <strong>Onboarding → Configuracion del Agente</strong>.')}

    ${this._h('Acciones de refuerzo recomendadas')}
    ${this._steps([
      '<strong>Activa HTTPS:</strong> instala nginx como reverse proxy delante de RiskHub con un certificado TLS de Let\'s Encrypt (gratuito). Sin TLS, los datos viajan en claro por la red.',
      '<strong>Genera un SECRET_KEY seguro:</strong> ejecuta <code>python -c "import secrets; print(secrets.token_urlsafe(64))"</code> y configura el resultado como <code>RISKHUB_SECRET_KEY</code> en el entorno de Docker. Este secreto protege todos los cifrados Fernet y los JWT.',
      '<strong>Cifra los backups:</strong> el backup de la BD SQLite (disponible en Administracion) contiene los datos en claro (solo el disco de documentos esta cifrado). Cifra los backups con GPG antes de transferirlos: <code>gpg --symmetric --cipher-algo AES256 riskhub_backup.db</code>.',
      '<strong>Limita el acceso de red:</strong> configura el firewall del servidor para que el puerto 80/443 solo sea accesible desde la red corporativa (VPN o IP range). El puerto de la app (8000) no debe estar expuesto directamente a internet.',
      '<strong>Rota el SECRET_KEY periodicamente:</strong> al cambiar el SECRET_KEY, los documentos cifrados con la clave anterior requieren ser resubidos (los Fernet tokens anteriores no se podran descifrar con la nueva clave).',
      '<strong>PostgreSQL para datos de alta clasificacion:</strong> si necesitas cifrado a nivel de base de datos (campo a campo o TDE), migra de SQLite a PostgreSQL con pg_crypto o usa PostgreSQL 16+ con Transparent Data Encryption.',
      '<strong>Revisa el posture de seguridad:</strong> ve a Administracion → Sistema y usa el panel de seguridad para verificar todas las capas activas.',
    ])}

    ${this._h('Privacidad y GDPR')}
    ${this._p('Si tu organizacion esta sujeta al RGPD (Reglamento General de Proteccion de Datos):')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Responsable del tratamiento:</strong> tu organizacion (opera la instancia on-premise).</li>
      <li><strong>Encargado del tratamiento:</strong> Anthropic (Claude API) — solo si usas el Agente IA con datos personales.</li>
      <li><strong>Minimizacion:</strong> configura el nivel de anonimizacion en "alto" para minimizar la PII enviada a la API externa.</li>
      <li><strong>Portabilidad:</strong> usa la funcion de backup de BD + exportacion de informes PDF para cumplir con el derecho de portabilidad.</li>
      <li><strong>Supresion:</strong> la eliminacion de activos/riesgos/usuarios es definitiva (no hay papelera). El log de auditoria mantiene el registro de que existio el registro pero sin contenido personal.</li>
      <li><strong>DPA con Anthropic:</strong> si cargas datos personales en el Agente IA, verifica que Anthropic figure como encargado en tu Registro de Actividades de Tratamiento (RAT).</li>
    </ul>
    ${this._tip('Para despliegues en sectores regulados (banca, salud, infraestructuras criticas): activa el nivel de anonimizacion "alto", configura el agente IA con un modelo self-hosted (Ollama + Llama 3) para eliminar completamente las llamadas a APIs externas, y documenta el tratamiento en el modulo GDPR de RiskHub.')}
  `;},

  get _cMethodology() { return `
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

  get _cAiChat() { return `
    ${this._p('El <strong>Chat con el Agente IA</strong> permite consultar en lenguaje natural el estado de seguridad de tu organizacion. El agente combina el contexto enriquecido de RiskHub (activos, riesgos, controles, incidentes) con los documentos que hayas subido.')}
    ${this._h('Como funciona')}
    ${this._steps([
      'El agente recibe automaticamente el contexto de tu organizacion: activos, riesgos activos, incidentes recientes, controles con baja madurez y proveedores criticos.',
      'Si has subido documentacion (arquitectura, normativa, politicas...), el agente tambien realiza una busqueda por similitud en esos documentos y los incluye en su contexto.',
      'Escribe tu consulta en el campo de texto y pulsa Enter o Enviar.',
      'El agente responde siempre en castellano, con recomendaciones orientadas a la accion.',
      'Puedes valorar cada respuesta (1-5 estrellas) para que el sistema registre la calidad.',
    ])}
    ${this._h('Ejemplos de consultas')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Dame un resumen ejecutivo del estado de riesgos criticos.</li>
      <li>Que controles tienen madurez inferior a 2? Que deberia priorizar?</li>
      <li>Tenemos un incidente de ransomware. Que pasos debo seguir segun NIS2?</li>
      <li>Cuales son las principales brechas en nuestra implementacion de ISO 27002?</li>
      <li>Hay proveedores criticos sin evaluacion reciente?</li>
    </ul>
    ${this._warn('<strong>Importante:</strong> El agente usa la API de Claude (Anthropic). Configura tu API key en <em>Config. Agente</em> antes de usar el chat. La informacion enviada se anonimiza segun el nivel configurado.')}
    ${this._tip('Usa las <em>Preguntas rapidas</em> del panel lateral para consultas frecuentes sin tener que escribirlas.')}
  `;},

  get _cAiDocuments() { return `
    ${this._p('La <strong>Biblioteca de documentos</strong> almacena y procesa los archivos que alimentan el contexto del agente IA. Cada documento se divide en fragmentos (chunks) que se indexan en un motor de busqueda de texto completo (FTS5), permitiendo al agente recuperar la informacion mas relevante para cada consulta.')}
    ${this._h('Categorias de documentos')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px;">Categoria</th><th style="padding:8px;">Tipo de documentos</th>
      </tr></thead>
      <tbody>
        ${[
          ['Arquitectura y sistemas','Diagramas de red, inventarios de sistemas, arquitecturas cloud/on-premise.'],
          ['Normativa y compliance','Normas aplicables: ISO 27001, ENS, NIS2, GDPR, PCI-DSS.'],
          ['Politicas y procedimientos','Politica de seguridad, gestion de accesos, backups, continuidad.'],
          ['Inventario de activos','Listado de activos TI, valoracion CIA, clasificacion por criticidad.'],
          ['Evaluaciones de riesgo','Informes de analisis de riesgos anteriores, DPIA, auditorias.'],
          ['Proveedores criticos','Contratos, evaluaciones de terceros, SLA, acuerdos DPA.'],
          ['Incidentes y lecciones','Informes post-incidente, root cause analysis, planes de mejora.'],
          ['Otros','Cualquier documentacion adicional relevante para el contexto.'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>${r.map(c=>`<td style="padding:8px;">${c}</td>`).join('')}</tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Formatos soportados')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>PDF:</strong> documentos escaneados o generados digitalmente (texto extraido por PyPDF).</li>
      <li><strong>DOCX:</strong> documentos Word (texto extraido por python-docx).</li>
      <li><strong>TXT / CSV:</strong> texto plano, logs, exportaciones.</li>
      <li>Tamano maximo: 20 MB por archivo.</li>
    </ul>
    ${this._h('Estados de procesamiento')}
    ${this._steps([
      '<strong>Pendiente:</strong> archivo recibido, procesamiento no iniciado.',
      '<strong>Procesando:</strong> extrayendo texto y generando fragmentos.',
      '<strong>Indexado:</strong> documento disponible para consultas del agente.',
      '<strong>Error:</strong> fallo durante el procesamiento. Usa Reprocesar para reintentar.',
    ])}
    ${this._tip('Cuantos mas documentos indexados, mas preciso es el agente. Empieza por los documentos de arquitectura y politicas, que suelen contener la informacion de mas valor para el analisis de riesgos.')}
  `;},

  get _cOnboarding() { return `
    ${this._p('La <strong>Configuracion del Agente IA</strong> centraliza todo lo necesario para que el agente tenga el contexto de tu organizacion. Se divide en dos partes: <em>perfil organizacional</em> (datos cuantitativos y cualitativos) y <em>documentacion</em> (archivos que el agente usara como base de conocimiento).')}
    ${this._h('Perfil de la organizacion')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Sector de actividad:</strong> permite al agente priorizar amenazas tipicas del sector (banca, salud, industrial...).</li>
      <li><strong>Tamano:</strong> condiciona el nivel de madurez esperado y los marcos regulatorios aplicables.</li>
      <li><strong>Procesos criticos:</strong> el agente los usa para evaluar impacto de riesgos sobre el negocio.</li>
      <li><strong>Stack tecnologico:</strong> permite identificar vulnerabilidades especificas de las tecnologias en uso.</li>
    </ul>
    ${this._h('Configuracion de la API')}
    ${this._steps([
      'Obten tu API key en <a href="https://console.anthropic.com/" target="_blank" style="color:var(--brand-purple);">console.anthropic.com</a>.',
      'Pega la clave en el campo API Key. Se almacena cifrada (Fernet AES-256).',
      'Selecciona el modelo: Opus (mas potente), Sonnet (equilibrado) o Haiku (mas rapido y economico).',
      'Configura el nivel de anonimizacion: que informacion se enmascara antes de enviar a la API.',
      'Pulsa "Probar conexion" para verificar que la clave es valida.',
    ])}
    ${this._h('Niveles de anonimizacion')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px;">Nivel</th><th style="padding:8px;">Que se enmascara</th><th style="padding:8px;">Recomendado para</th>
      </tr></thead>
      <tbody>
        ${[
          ['Bajo','IPs y direcciones de email','Entornos de prueba o con datos no sensibles'],
          ['Medio (recomendado)','IPs, emails y nombres de dominio','La mayoria de organizaciones'],
          ['Alto','IPs, emails, dominios y nombres propios','Sectores altamente regulados (banca, salud)'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>${r.map(c=>`<td style="padding:8px;">${c}</td>`).join('')}</tr>`).join('')}
      </tbody>
    </table>
    ${this._warn('La primera vez que accedes a RiskHub, el sistema detectara automaticamente si el agente no esta configurado y te redirigira a esta pantalla. Puedes omitir esta configuracion con el boton "Omitir por ahora" y volver cuando estés listo.')}
  `;},
};
