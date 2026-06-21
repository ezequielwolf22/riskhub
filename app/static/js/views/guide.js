/* Vista Guia — Documentacion completa de uso de RiskHub. */
const ViewGuide = {

  _sections: [
    { id: 'intro', title: 'Que es RiskHub', icon: '📖' },
    { id: 'setup', title: 'Puesta en marcha', icon: '🚀' },
    { id: 'navigation', title: 'Navegacion por hubs', icon: '🗂️' },
    { id: 'inbox', title: 'Bandeja de revision', icon: '📥' },
    { id: 'dashboard', title: 'Dashboard ejecutivo', icon: '📊' },
    { id: 'search', title: 'Busqueda global', icon: '🔎' },
    { id: 'context', title: 'Configuracion inicial', icon: '⚙️' },
    { id: 'assets', title: 'Inventario de activos', icon: '🗄️' },
    { id: 'threats', title: 'Amenazas y vulnerabilidades', icon: '🔍' },
    { id: 'risks', title: 'Gestion de riesgos', icon: '📊' },
    { id: 'kris', title: 'KRIs — Indicadores de riesgo', icon: '📈' },
    { id: 'calendar', title: 'Calendario', icon: '📅' },
    { id: 'controls', title: 'Controles ISO 27002', icon: '🛡️' },
    { id: 'policies', title: 'Politicas de seguridad', icon: '📜' },
    { id: 'internal-audits', title: 'Auditoria interna', icon: '🔍' },
    { id: 'compliance', title: 'Cumplimiento multi-framework', icon: '✅' },
    { id: 'incidents', title: 'Incidentes (NIS2)', icon: '🚨' },
    { id: 'suppliers', title: 'Proveedores (supply chain)', icon: '🔗' },
    { id: 'tprm', title: 'TPRM (Riesgo de Terceros)', icon: '🏢' },
    { id: 'nonconformities', title: 'No conformidades', icon: '⚠️' },
    { id: 'tasks', title: 'Tareas de tratamiento', icon: '📌' },
    { id: 'gdpr', title: 'RGPD / Privacidad', icon: '🔒' },
    { id: 'regwatch', title: 'Vigilancia normativa', icon: '📡' },
    { id: 'bowtie', title: 'Diagrama Bow-Tie', icon: '🎀' },
    { id: 'ai-gap', title: 'Analisis de brechas IA', icon: '🧠' },
    { id: 'ai', title: 'Agente IA (cuestionario)', icon: '🤖' },
    { id: 'ai-chat', title: 'Chat con el Agente IA', icon: '💬' },
    { id: 'ai-documents', title: 'Documentos del Agente', icon: '📂' },
    { id: 'architecture-review', title: 'Rev. Arquitectura de Red', icon: '📂' },
    { id: 'onboarding', title: 'Configuracion del Agente', icon: '⚙️' },
    { id: 'executive', title: 'Dashboard Ejecutivo', icon: '📈' },
    { id: 'ccm', title: 'Monit. Continua de Controles', icon: '✅' },
    { id: 'evidence', title: 'Evidencias', icon: '📁' },
    { id: 'magerit', title: 'MAGERIT v3', icon: '🇪🇸' },
    { id: 'predictive', title: 'Analisis Predictivo', icon: '📊' },
    { id: 'trust-portal', title: 'Trust Portal y Auditor', icon: '🔏' },
    { id: 'itsm-config', title: 'ITSM y Notificaciones', icon: '🔔' },
    { id: 'reports', title: 'Informes', icon: '📄' },
    { id: 'alerts', title: 'Alertas por email', icon: '🔔' },
    { id: 'integrations', title: 'Integraciones', icon: '🔌' },
    { id: 'cve', title: 'CVE Monitor', icon: '🛡️' },
    { id: 'osint', title: 'OSINT - Huella Digital', icon: '🕵️' },
    { id: 'external-findings', title: 'Hallazgos Externos', icon: '🔗' },
    { id: 'bcp', title: 'Continuidad de Negocio (BCP)', icon: '♻️' },
    { id: 'webhooks', title: 'Webhooks y Integraciones', icon: '🪝' },
    { id: 'feature-flags', title: 'Feature Flags (Planes)', icon: '🚩' },
    { id: 'awareness', title: 'Awareness (Infografias)', icon: '🎨' },
    { id: 'organizations', title: 'Organizaciones (multi-tenant)', icon: '🏢' },
    { id: 'audit', title: 'Log de Auditoria', icon: '📋' },
    { id: 'admin', title: 'Administracion', icon: '👥' },
    { id: 'security', title: 'Seguridad y privacidad', icon: '🔐' },
    { id: 'methodology', title: 'Metodologia ISO 27005', icon: '📐' },
    { id: 'risk-levels', title: 'Niveles de riesgo', icon: '⚙️' },
    { id: 'questionnaires', title: 'Cuestionarios internos', icon: '📋' },
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
      dashboard: this._cDashboard,
      search: this._cSearch,
      context: this._cContext,
      assets: this._cAssets,
      threats: this._cThreats,
      risks: this._cRisks,
      kris: this._cKris,
      calendar: this._cCalendar,
      controls: this._cControls,
      policies: this._cPolicies,
      'internal-audits': this._cInternalAudits,
      compliance: this._cCompliance,
      incidents: this._cIncidents,
      suppliers: this._cSuppliers,
      tprm: this._cTprm,
      nonconformities: this._cNonConformities,
      tasks: this._cTasks,
      gdpr: this._cGdpr,
      regwatch: this._cRegwatch,
      bowtie: this._cBowtie,
      'ai-gap': this._cAiGap,
      ai: this._cAI,
      'ai-chat': this._cAiChat,
      'ai-documents': this._cAiDocuments,
      'architecture-review': this._cArchitectureReview,
      onboarding: this._cOnboarding,
      executive: this._cExecutive,
      ccm: this._cCcm,
      evidence: this._cEvidence,
      magerit: this._cMagerit,
      predictive: this._cPredictive,
      'trust-portal': this._cTrustPortal,
      'itsm-config': this._cItsmConfig,
      reports: this._cReports,
      alerts: this._cAlerts,
      integrations: this._cIntegrations,
      cve: this._cCve,
      osint: this._cOsint,
      'external-findings': this._cExternalFindings,
      bcp: this._cBcp,
      webhooks: this._cWebhooks,
      'feature-flags': this._cFeatureFlags,
      awareness: this._cAwareness,
      organizations: this._cOrganizations,
      audit: this._cAudit,
      admin: this._cAdmin,
      security: this._cSecurity,
      methodology: this._cMethodology,
      inbox: this._cInbox,
      navigation: this._cNavigation,
      setup: this._cSetup,
      'risk-levels': this._cRiskLevels,
      questionnaires: this._cQuestionnaires,
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
    <div style="background:linear-gradient(135deg,var(--brand-purple-4),var(--brand-orange-4));border-radius:12px;padding:20px 24px;margin-bottom:20px;">
      <div style="font-size:18px;font-weight:700;color:var(--brand-purple);margin-bottom:8px;">RiskHub — Plataforma GRC para ISO/IEC 27005</div>
      <p style="margin:0;font-size:14px;line-height:1.7;color:var(--text-base);">
        RiskHub es una plataforma de <strong>Gobernanza, Riesgo y Cumplimiento (GRC)</strong> disenada para implementar de forma rigurosa el proceso de gestion del riesgo de seguridad de la informacion segun <strong>ISO/IEC 27005:2018</strong>, con el catalogo completo de <strong>93 controles ISO/IEC 27002:2022</strong> y soporte para MAGERIT v3, NIS2, ENS, NIST CSF y GDPR. La herramienta cubre el ciclo completo: identificacion de activos, analisis de riesgos, definicion de tratamientos, gestion de cumplimiento, respuesta a incidentes y generacion de informes de auditoria.
      </p>
    </div>
    ${this._h('Modulos incluidos')}
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:20px;">
      ${[
        ['Gestion de riesgos','Registro completo ISO 27005, matriz 5x5, heatmap, tratamiento y seguimiento con fechas limite.'],
        ['Inventario de activos','Catalogo por tipo ISO 27005, valoracion CIA/MAGERIT, jerarquia, agrupacion con IA, importacion CSV masiva.'],
        ['Controles ISO 27002','93 controles precargados, SoA completo, nivel de madurez CMM, monitor de revisiones vencidas.'],
        ['Agente IA','Claude (Anthropic): analisis automatico de activos, chat GRC, informes narrativos, extraccion de clausulas ISO.'],
        ['Cumplimiento multi-marco','ISO 27001 · NIS2 · NIST CSF · ENS · GDPR · DORA: scoring automatico y brechas identificadas.'],
        ['TPRM','Riesgo de terceros, cuestionarios ponderados, evaluaciones consolidadas, hallazgos con SLA automatico.'],
        ['Incidentes','Ciclo de vida completo, clasificacion P1-P4, flujo de notificacion NIS2, vinculacion a riesgos.'],
        ['Continuidad BCP/DRP','Procesos criticos, BIA, planes con 10 secciones, tests, mapa de dependencias interactivo Cytoscape.'],
        ['CVE Monitor','Conexion NVD/NIST en tiempo real, analisis IA de CVEs contra el inventario, creacion de riesgos con un clic.'],
        ['OSINT','Escaneo de emails, dominios, IPs y usuarios en fuentes abiertas. Pipeline automatico de riesgos e incidentes.'],
        ['Vigilancia normativa','Monitorizacion automatica de 11 fuentes regulatorias (EUR-Lex, BOE, ENISA, NIST...) con propagacion.'],
        ['Informes y evidencias','PDF/Excel con IA, SoA, Trust Portal publico, paquete de auditoria ZIP por framework.'],
      ].map(([t,d]) => `
        <div style="background:var(--bg-2);border-radius:8px;padding:12px 14px;">
          <div style="font-weight:700;font-size:13px;color:var(--brand-purple);margin-bottom:4px;">${t}</div>
          <div style="font-size:12px;color:var(--text-muted);line-height:1.5;">${d}</div>
        </div>`).join('')}
    </div>

    ${this._h('Flujo de trabajo recomendado')}
    <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:20px;">
      ${[
        ['1','Puesta en marcha','Accede con las credenciales recibidas, cambia la contrasena del admin y configura el contexto organizacional. Consulta la seccion <strong>Puesta en marcha</strong> para el proceso completo de instalacion y configuracion inicial.'],
        ['2','Inventario de activos','Importa activos via CSV o creallos uno a uno. Clasifica por tipo ISO 27005 y valora las dimensiones CIA. El analisis de riesgos con IA arranca automaticamente (requiere API key del Agente IA).'],
        ['3','Catalogo de amenazas','Revisa las 49 amenazas y 67 vulnerabilidades precargadas. Anade entradas especificas de tu sector si es necesario.'],
        ['4','Registro de riesgos','Los riesgos se generan automaticamente por el Agente IA. Revisa los niveles calculados, asigna responsables y define planes de tratamiento con fechas limite.'],
        ['5','Controles ISO 27002','Registra los controles con estado y nivel de madurez CMM. Vinculalos a los riesgos para calcular el nivel residual real. Documenta evidencias y justificaciones SOA.'],
        ['6','Cumplimiento y politicas','Activa los frameworks normativos aplicables. Sube politicas y procedimientos al Agente IA para enriquecer automaticamente el SGSI.'],
        ['7','Informes y seguimiento','Genera informes PDF/Excel. Configura alertas por email. Usa el calendario para controlar vencimientos y el dashboard ejecutivo para comunicar la postura a la direccion.'],
      ].map(([n,t,d]) => `
        <div style="display:flex;gap:12px;align-items:flex-start;background:var(--bg-2);border-radius:8px;padding:12px 14px;">
          <span style="background:var(--brand-purple);color:#fff;border-radius:50%;width:24px;height:24px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;margin-top:1px;">${n}</span>
          <div>
            <div style="font-weight:700;font-size:13px;margin-bottom:3px;">${t}</div>
            <div style="font-size:12px;color:var(--text-muted);line-height:1.5;">${d}</div>
          </div>
        </div>`).join('')}
    </div>

    ${this._h('Roles de usuario')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--brand-purple);color:#fff;">
        <th style="padding:8px 12px;text-align:left;">Rol</th>
        <th style="padding:8px 12px;text-align:left;">Permisos</th>
        <th style="padding:8px 12px;text-align:left;">Uso tipico</th>
      </tr></thead>
      <tbody>
        <tr><td style="padding:8px 12px;font-weight:600;">superadmin</td>
            <td style="padding:8px 12px;">Acceso total a todos los tenants, feature flags y planes de licencia.</td>
            <td style="padding:8px 12px;color:var(--text-muted);">Administrador de la plataforma.</td></tr>
        <tr style="background:var(--bg-2);">
            <td style="padding:8px 12px;font-weight:600;">admin</td>
            <td style="padding:8px 12px;">Gestion de usuarios, SMTP, backups, log de auditoria y todas las funciones del SGSI.</td>
            <td style="padding:8px 12px;color:var(--text-muted);">CISO o responsable de seguridad.</td></tr>
        <tr><td style="padding:8px 12px;font-weight:600;">analyst</td>
            <td style="padding:8px 12px;">Crear y editar riesgos, activos, controles, incidentes. Usar el Agente IA. Sin gestion de usuarios.</td>
            <td style="padding:8px 12px;color:var(--text-muted);">Analista de seguridad o consultor GRC.</td></tr>
        <tr style="background:var(--bg-2);">
            <td style="padding:8px 12px;font-weight:600;">viewer</td>
            <td style="padding:8px 12px;">Solo lectura. Ve todos los datos y descarga informes pero no puede modificar nada.</td>
            <td style="padding:8px 12px;color:var(--text-muted);">Auditores, direccion, revisores externos.</td></tr>
      </tbody>
    </table>

    ${this._h('Datos tecnicos')}
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:16px;">
      ${[
        ['Version','RiskHub v2.2.0'],
        ['Metodologia','ISO/IEC 27005:2018 + MAGERIT v3'],
        ['Frameworks cubiertos','ISO 27001 · NIS2 · NIST CSF · ENS · GDPR · DORA · ISO 42001'],
        ['Catalogos incluidos','49 amenazas · 67 vulnerabilidades · 93 controles ISO 27002'],
        ['Tecnologia','Python 3.11 · FastAPI · SQLite/PostgreSQL · Docker'],
        ['Despliegue','On-premise (Docker) o instancia gestionada'],
      ].map(([k,v]) => `
        <div style="background:var(--bg-2);border-radius:8px;padding:10px 14px;">
          <div style="font-size:11px;text-transform:uppercase;color:var(--text-muted);font-weight:600;letter-spacing:.5px;margin-bottom:4px;">${k}</div>
          <div style="font-size:13px;font-weight:600;">${v}</div>
        </div>`).join('')}
    </div>
    ${this._tip('<strong>Primer acceso:</strong> Si acabas de recibir credenciales, ve directamente a la seccion <strong>Puesta en marcha</strong> en el menu de esta guia para completar la configuracion inicial en menos de 30 minutos.')}
  `;},

  get _cDashboard() { return `
    ${this._p('El <strong>Dashboard ejecutivo</strong> es la pantalla principal de RiskHub. Agrega en una sola vista el estado de todos los modulos: riesgos, controles, incidentes, tareas, politicas y RGPD.')}
    ${this._h('Puntuacion de postura de seguridad')}
    ${this._p('El indicador circular en la parte superior (0-100) calcula la postura global del SGSI en base a:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 12px;">
      <li>Porcentaje de riesgos altos sin tratar (hasta -25 pts)</li>
      <li>Tratamientos vencidos (hasta -15 pts)</li>
      <li>Riesgos altos sin plan de tratamiento (hasta -10 pts)</li>
      <li>Incidentes P1/P2 abiertos (hasta -10 pts)</li>
      <li>Notificaciones NIS2 pendientes (-5 pts)</li>
      <li>Tareas vencidas (hasta -8 pts)</li>
      <li>Politicas con revision vencida (hasta -5 pts)</li>
      <li>DPIAs pendientes (hasta -5 pts)</li>
      <li>Cobertura de controles implementados (+10 pts bonus)</li>
    </ul>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;">
      ${[['80-100','Buena','var(--risk-low)'],['60-79','Aceptable','#D97706'],['40-59','Deficiente','var(--risk-high)'],['0-39','Critica','var(--risk-critical)']].map(([r,l,c])=>
        `<div style="background:var(--bg-2);border-radius:8px;padding:8px 12px;font-size:12px;border-left:3px solid ${c};">
          <strong style="color:${c};">${r} pts — ${l}</strong>
        </div>`).join('')}
    </div>
    ${this._h('Panel de chips de modulo')}
    ${this._p('Bajo el indicador circular aparecen chips de acceso rapido a cada modulo. El color indica el estado:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 12px;">
      <li><strong style="color:var(--risk-low);">Verde</strong> — modulo sin alertas activas</li>
      <li><strong style="color:var(--risk-medium);">Ambar</strong> — hay items que requieren atencion</li>
      <li><strong style="color:var(--risk-high);">Rojo</strong> — situacion critica (P1/P2 abiertos, NIS2 pendiente)</li>
    </ul>
    ${this._h('Panel de alertas criticas')}
    ${this._p('A la derecha del indicador aparece una lista consolidada de todos los items urgentes de todos los modulos. Si no hay alertas, el panel muestra confirmacion verde.')}
    ${this._h('KPIs de riesgo')}
    ${this._p('Las dos filas de indicadores muestran los KPIs principales: activos, riesgos, controles, reduccion de riesgo, tratamientos vencidos, incidentes P1/P2 y tareas vencidas. Los indicadores con color de fondo requieren accion inmediata.')}
    ${this._h('Tarjetas de modulos secundarios')}
    ${this._p('La fila de tarjetas debajo de los graficos de riesgo muestra estadisticas detalladas de incidentes, tareas, politicas y RGPD. Cada tarjeta tiene un enlace "Ver todos" para navegar al modulo.')}
    ${this._h('Top 10 riesgos')}
    ${this._p('La tabla muestra los 10 riesgos con mayor nivel residual, con el codigo, activo, amenaza, nivel y porcentaje de reduccion conseguido. Clic en cualquier fila para navegar directamente al riesgo.')}
    ${this._h('Acciones rapidas')}
    ${this._p('El panel lateral izquierdo consolida accesos directos a los items urgentes de todos los modulos. Los botones con borde rojo o naranja indican items que requieren atencion inmediata.')}
    ${this._tip('El dashboard se carga en paralelo — todos los modulos consultan sus APIs simultaneamente para minimizar el tiempo de carga.')}
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
    ${this._h('Analisis de riesgos automatico con IA (v1.7.5)')}
    ${this._p('El agente IA puede analizar automáticamente cada activo del inventario y generar un análisis de riesgos completo aplicando la metodología <strong>MAGERIT v3 / ISO 27005</strong>. El proceso cruza el activo con el catálogo de amenazas, vulnerabilidades y controles implementados para calcular el riesgo inherente y residual sin necesidad de intervención manual.')}
    ${this._h('Como funciona el pipeline de analisis')}
    ${this._steps([
      'El agente recibe el perfil del activo: tipo, valoracion CIA, descripcion y categoria.',
      'Filtra del catalogo las amenazas aplicables al tipo de activo (ej. <em>support_hardware</em> → amenazas fisicas, de red, de malware...).',
      'Para cada amenaza relevante calcula: probabilidad inherente, consecuencia inherente y nivel de riesgo ISO 27005 (escala 0-8).',
      'Identifica las vulnerabilidades del catalogo que aplican a ese activo y amenaza.',
      'Aplica los controles ISO 27002 ya implementados para calcular el riesgo residual.',
      'Crea o actualiza los registros de riesgo en la seccion Riesgos, marcandolos con la etiqueta <strong>IA</strong>.',
    ])}
    ${this._h('Lanzar el analisis')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Por activo individual:</strong> haz clic en el icono <em>⚙</em> de la columna "Analisis IA" en la tabla de activos. El estado cambia a "Analizando..." mientras el agente trabaja en background.</li>
      <li><strong>Para todos los activos:</strong> usa el boton <strong>Analizar riesgos con IA</strong> de la barra de herramientas. Se lanzan todos los activos de la organizacion en paralelo.</li>
    </ul>
    ${this._h('Estados del analisis IA')}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;">
      ${[
        ['Analizando','El agente esta procesando el activo en background.','var(--brand-orange)'],
        ['Analizado','El analisis ha completado. Pasa el cursor para ver el resumen.','var(--risk-low)'],
        ['Error','Fallo en el analisis. Reintenta con el boton ⚙.','var(--risk-high)'],
        ['Sin analisis','El activo aun no ha sido analizado.','var(--text-muted)'],
      ].map(([l,d,c]) =>
        `<div style="background:var(--bg-2);border-radius:8px;padding:8px 12px;border-left:3px solid ${c};">
          <strong style="color:${c};font-size:12px;">${l}</strong>
          <div style="font-size:12px;color:var(--text-muted);margin-top:2px;">${d}</div>
        </div>`).join('')}
    </div>
    ${this._h('Riesgos generados por IA')}
    ${this._p('Los riesgos creados automaticamente por el agente se marcan con la etiqueta <strong style="background:var(--brand-purple-4);color:var(--brand-purple);padding:1px 4px;border-radius:3px;font-size:11px;">IA</strong> junto al codigo en la tabla de riesgos. Pasa el cursor sobre la etiqueta para ver la justificacion del agente.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Los riesgos IA se pueden editar libremente: cambiar probabilidad, consecuencia, controles, plan de tratamiento.</li>
      <li>Si relanzas el analisis sobre un activo, los riesgos IA existentes se actualizan (no se duplican). Los riesgos creados manualmente nunca se sobreescriben.</li>
      <li>Puedes eliminar un riesgo IA si el agente ha generado un escenario que no es aplicable a tu contexto.</li>
    </ul>
    ${this._warn('<strong>Requiere API key:</strong> el analisis de riesgos IA necesita la clave Anthropic configurada en <strong>Configuracion del Agente</strong>. Sin ella, el analisis se omite automaticamente.')}
    ${this._h('Automatizacion completa del ciclo de vida (v1.7.6)')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Crear activo:</strong> el analisis IA arranca automaticamente sin ningun clic adicional.</li>
      <li><strong>Editar activo:</strong> el analisis se relanza en background cuando cambias el tipo, valoracion CIA u otros datos — los riesgos IA se recalculan con los nuevos datos.</li>
      <li><strong>Importar CSV de activos:</strong> el analisis se lanza para cada activo creado o actualizado en la importacion.</li>
      <li><strong>Subir documento al agente:</strong> si el analisis ISMS actualiza controles ISO 27002, los riesgos residuales de todos los activos se recalculan automaticamente para reflejar la nueva cobertura.</li>
    </ul>
    ${this._h('Apetito de riesgo automatico')}
    ${this._p('Tras cada analisis, el sistema compara el nivel residual de cada riesgo IA contra el <strong>apetito de riesgo</strong> configurado en la seccion Contexto. Si un riesgo supera el umbral y tenia decision "retention" (aceptar), se escala automaticamente a "modification" (mitigar) para garantizar que ningun riesgo por encima del apetito quede sin plan de accion.')}
    ${this._tip('<strong>Flujo minimo del usuario:</strong> (1) configura el API key del agente, (2) sube tus documentos SGSI, (3) importa tus activos — el resto lo hace el sistema automaticamente.')}
    ${this._h('Agrupacion de activos con IA (v1.8.0)')}
    ${this._p('Cuando el inventario contiene cientos o miles de activos (por ejemplo tras una importacion masiva o una integracion con CMDB), el analisis riesgo-por-riesgo es redundante: un servidor Windows de produccion tiene el mismo perfil de amenaza que los 400 servidores Windows iguales. La <strong>Agrupacion con IA</strong> resuelve este problema.')}
    ${this._h('Flujo de agrupacion')}
    ${this._steps([
      '<strong>Tab "Agrupacion con IA":</strong> accede desde la vista de Activos pulsando la pestana.',
      '<strong>Configura criterios:</strong> expande el panel "Criterios de agrupacion". Activa o desactiva los criterios segun las necesidades de tu organizacion. Los criterios de nivel 1 son los mas relevantes (tipo de activo); los de nivel 2 y 3 refinan los grupos.',
      '<strong>Analiza con IA:</strong> pulsa "Analizar y proponer grupos con IA". El agente examina todos los activos no agrupados y propone grupos coherentes con ISO 27005, con justificacion metodologica incluida.',
      '<strong>Revisa las propuestas:</strong> cada grupo muestra nombre, numero de activos, muestra de miembros y la razon ISO 27005 del agrupamiento.',
      '<strong>Valida o ajusta:</strong> Valida cada grupo (o todos a la vez), renombra, divide grupos en dos, mueve activos entre grupos, o elimina grupos que no sean relevantes.',
      '<strong>Analisis de riesgo:</strong> al validar un grupo se crea automaticamente un activo representativo con los valores CIA maximos del grupo. El pipeline IA analiza este activo representativo en lugar de cada activo individual.',
    ])}
    ${this._h('Criterios de agrupacion ISO 27005')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px;text-align:left;">Criterio</th>
        <th style="padding:8px;text-align:left;">Nivel</th>
        <th style="padding:8px;text-align:left;">Para que sirve</th>
      </tr></thead>
      <tbody>
        ${[
          ['Tipo de activo ISO 27005','N1','Primaria: hardware, software, red, personal... Las amenazas dependen del tipo.'],
          ['Plataforma / Sistema operativo','N2','Diferencia Windows vs Linux vs Cloud, fisico vs virtual.'],
          ['Clasificacion de la informacion','N2','Separa activos con datos confidenciales de los publicos.'],
          ['Criticidad CIA','N2','Agrupa por perfil de valoracion (critico, alto, medio, bajo).'],
          ['Ubicacion / entorno','N3','Distingue CPD propio vs cloud vs oficina.'],
          ['Propietario / departamento','N3','Util cuando los controles organizacionales difieren por departamento.'],
          ['Proceso de negocio','N3','Agrupa activos que dan soporte al mismo proceso.'],
        ].map((r, i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          <td style="padding:8px;">${r[0]}</td>
          <td style="padding:8px;font-family:monospace;font-size:11px;">${r[1]}</td>
          <td style="padding:8px;color:var(--text-muted);">${r[2]}</td>
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Activo representativo')}
    ${this._p('Cuando validas un grupo, RiskHub crea un <strong>activo representativo</strong> (codigo GRP-XXXX) que resume el grupo. Sus valores CIA son los maximos del grupo (criterio conservador ISO 27005 para no subestimar el riesgo). El pipeline de analisis IA trabaja sobre este representativo, y los riesgos resultantes cubren a todos los miembros del grupo.')}
    ${this._warn('Los activos representativos no aparecen en el inventario normal. Solo son visibles en la seccion Riesgos al filtrar por grupo.')}
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
    ${this._h('Riesgos generados automaticamente por IA (v1.7.5)')}
    ${this._p('Los riesgos creados por el agente IA (desde el analisis de activos, OSINT o importacion de CSV) se identifican con la etiqueta <strong style="background:var(--brand-purple-4);color:var(--brand-purple);padding:1px 5px;border-radius:3px;font-size:11px;">IA</strong> visible junto al codigo del riesgo en la tabla. Esta etiqueta facilita distinguir los riesgos autogenerados de los creados manualmente.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Pasa el cursor sobre la etiqueta IA para ver la <strong>justificacion del agente</strong>: por que ese activo y amenaza generan ese nivel de riesgo.</li>
      <li>Los riesgos IA son completamente editables. Puedes ajustar probabilidad, consecuencia, controles y plan de tratamiento.</li>
      <li>Relanzar el analisis sobre un activo <em>actualiza</em> los riesgos IA existentes; los riesgos manuales nunca se modifican automaticamente.</li>
    </ul>
    ${this._h('Importacion de riesgos desde CSV')}
    ${this._p('El modulo de importacion CSV permite cargar vulnerabilidades y hallazgos externos (reportes de pentest, escaneados de red, CVEs) que el agente vincula automaticamente a los activos del inventario.')}
    ${this._steps([
      'Descarga la plantilla desde <strong>Riesgos → Importar → Descargar plantilla</strong>.',
      'Rellena la plantilla con los hallazgos: activo, amenaza, descripcion, nivel.',
      'Sube el CSV. El agente detecta patrones CVE (formato CVE-YYYY-NNNNN) y los vincula al activo correspondiente.',
      'Los riesgos importados aparecen en el registro con la etiqueta IA y con la fuente identificada.',
    ])}
    ${this._h('Panel IA multi-tab — analisis automatico al abrir un riesgo')}
    ${this._p('Al abrir el detalle de cualquier riesgo, el panel IA se despliega automaticamente con 6 pestanas. El analisis experto y el escenario MITRE se lanzan en paralelo sin que el usuario tenga que hacer nada.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Analisis IA:</strong> explicacion rigurosa del nivel residual, cadena de ataque, efectividad de controles, brechas SOA y alineacion normativa.</li>
      <li><strong>Escenario MITRE:</strong> kill-chain completo con fases ATT&amp;CK, tecnicas TXX, mitigaciones y brechas criticas. Se precarga en background.</li>
      <li><strong>What-If:</strong> simulacion interactiva — cambia probabilidad, impacto o madurez de controles y ve el delta residual al instante sin modificar el registro.</li>
      <li><strong>VaR:</strong> Value at Risk por Monte Carlo (10.000 simulaciones). Muestra la perdida esperada, VaR 95% y VaR 99%.</li>
      <li><strong>Historial:</strong> evolucion mensual del nivel inherente y residual con sparkline y tabla de snapshots.</li>
      <li><strong>KRIs:</strong> indicadores clave de riesgo vinculados a este riesgo — estado (OK/Aviso/Alerta) y valor actual con boton de evaluacion directa.</li>
    </ul>
    ${this._tip('El boton "Regenerar" en el extremo derecho del panel IA vuelve a lanzar la pestana activa. Util tras anadir nuevos controles para ver si el analisis cambia.')}
    ${this._h('Descubrir riesgos con IA')}
    ${this._p('El boton <strong>Descubrir con IA</strong> junto a "Nuevo riesgo" lanza el agente IA para analizar el contexto de la organizacion e identificar riesgos potenciales no registrados. El agente devuelve una lista de sugerencias con nivel estimado, activo, amenaza y referencia ISO 27005.')}
    ${this._h('KRIs (Key Risk Indicators)')}
    ${this._p('Los KRIs son metricas configurables que alertan automaticamente cuando un indicador del riesgo supera el umbral. Se evaluan cada 6 horas por el scheduler.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Metricas disponibles:</strong> nivel residual, incidentes abiertos, madurez de controles, tareas de tratamiento vencidas, respuestas de encuesta y puntuacion de proveedor.</li>
      <li><strong>Dos umbrales:</strong> warning (aviso amarillo) y breach (alerta roja).</li>
      <li><strong>Alertas:</strong> cuando se supera el umbral breach se envia un email al destinatario configurado.</li>
      <li><strong>Panel portfolio:</strong> el widget del dashboard muestra el conteo de KRIs en alerta y aviso en tiempo real.</li>
    </ul>
    ${this._h('Portfolio de riesgos — widget del dashboard')}
    ${this._p('El widget <strong>Portfolio de riesgos</strong> del dashboard muestra el score ponderado del portfolio (media ponderada de niveles residuales por importancia del activo), la tendencia mensual y los KRIs en estado de alerta. Haz clic en cualquier KRI en alerta para ir directamente al detalle del riesgo.')}
    ${this._h('Bucle cerrado de riesgos')}
    ${this._p('El modulo de riesgos implementa retroalimentacion automatica entre todos los modulos del SGSI:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Control implementado → riesgo baja:</strong> al subir la madurez de un control o cambiar su estado a "Implemented", el residual de los riesgos vinculados se recalcula automaticamente.</li>
      <li><strong>NC mayor creada → riesgo sube:</strong> una NC major aplica una penalizacion del 40% sobre la eficacia del control, elevando el residual de los riesgos vinculados. Al cerrar la NC, la penalizacion se elimina y el residual baja.</li>
      <li><strong>Tareas de tratamiento → progreso del riesgo:</strong> cada TreatmentTask asociada a un riesgo contribuye al campo <code>treatment_progress</code> (0-100%). Al completar todas las tareas, el riesgo pasa automaticamente a estado "Treated" y su residual_likelihood se reduce en 1 punto.</li>
      <li><strong>KRI en BREACH → riesgo sube:</strong> si un KRI vinculado a un riesgo cruza el umbral de breach, el residual_likelihood sube +1. Cuando el KRI vuelve a NORMAL o WARNING, el residual_likelihood baja -1 automaticamente.</li>
      <li><strong>Incidente cerrado → likelihood sube:</strong> cerrar un incidente vinculado a un riesgo incrementa el inherent_likelihood en +1, reflejando que la amenaza se materializo (ISO 27005 §8.3).</li>
      <li><strong>Plan BCP activado → residual baja:</strong> activar un plan BCP vinculado a riesgos reduce su residual_likelihood en -1 por cada riesgo vinculado.</li>
    </ul>
    ${this._tip('El bucle cerrado garantiza que el registro de riesgos refleja en todo momento el estado real del SGSI sin necesidad de actualizaciones manuales. Revisa el historial de cambios de un riesgo para ver que evento disparo cada modificacion automatica.')}
    <h3>Bucle cerrado de riesgos (v5.5-5.6)</h3>
    <p>El módulo de riesgos implementa retroalimentación automática en ambas direcciones:</p>
    <table class="guide-table">
      <thead><tr><th>Causa (sube el riesgo)</th><th>Mitigación (baja el riesgo)</th></tr></thead>
      <tbody>
        <tr><td>NC major creada en control</td><td>NC cerrada → penalización eliminada</td></tr>
        <tr><td>Incidente cerrado vinculado</td><td>likelihood+1 (evidencia de materialización ISO 27005)</td></tr>
        <tr><td>KRI pasa a BREACH</td><td>KRI se recupera → residual_likelihood−1</td></tr>
        <tr><td>VendorIssue CRITICAL creado</td><td>VendorIssue cerrado → likelihood−1</td></tr>
        <tr><td>Plan BCP desactivado</td><td>Plan BCP activado → residual_likelihood−1</td></tr>
      </tbody>
    </table>
    <h4>Progreso de tratamiento</h4>
    <p>Cada <strong>TreatmentTask</strong> completada actualiza el campo <code>treatment_progress</code> del riesgo (0-100%). Al completar todas las tareas, el riesgo pasa automáticamente a estado <strong>Treated</strong> y su residual_likelihood se reduce en −1.</p>
  `;},

  get _cKris() { return `
    ${this._p('La seccion <strong>KRIs / KPIs</strong> (pestana del hub de Riesgos) permite monitorizar dos tipos de indicadores: <strong>KRIs</strong> (exposicion del riesgo individual) y <strong>KPIs</strong> (rendimiento del programa SGSI completo). Ambos se evaluan cada 6 horas por el scheduler y generan alertas automaticas en caso de breach.')}
    ${this._h('KRIs — Key Risk Indicators (por riesgo individual)')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>residual_level:</strong> nivel residual del riesgo (1-8).</li>
      <li><strong>inherent_level:</strong> nivel inherente del riesgo (1-8).</li>
      <li><strong>open_incidents:</strong> incidentes abiertos vinculados al riesgo.</li>
      <li><strong>open_ncs:</strong> no conformidades mayores abiertas (org).</li>
      <li><strong>control_maturity:</strong> madurez media de controles del riesgo (0-5).</li>
      <li><strong>overdue_tasks:</strong> tareas de tratamiento vencidas.</li>
    </ul>
    ${this._h('KPIs — Key Performance Indicators (nivel organizacion)')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Tasa de tratamiento (ISO 27001 cl.6.1.3):</strong> % riesgos altos con plan definido.</li>
      <li><strong>MTTT (ISO 27001 cl.9.1):</strong> dias medios de tratamiento.</li>
      <li><strong>Cobertura controles (ISO 27002):</strong> % controles del catalogo implementados o parciales.</li>
      <li><strong>Madurez media controles (ISO 27001 cl.9.1):</strong> promedio 0-5.</li>
      <li><strong>Revision de politicas (ISO 27001 cl.5.2):</strong> % politicas publicadas en plazo de revision.</li>
      <li><strong>Cierre de NCs (ISO 27001 cl.10.1):</strong> % NCs cerradas en &lt;=90 dias.</li>
      <li><strong>Reduccion del riesgo (ISO 27005 §8.6):</strong> % reduccion inherente → residual.</li>
      <li><strong>Apetito de riesgo (ISO 27005 §7.3):</strong> % riesgos dentro del apetito (&lt;=4).</li>
      <li><strong>Cobertura de activos (ISO 27005 §8.2):</strong> % activos con riesgo evaluado.</li>
      <li><strong>Riesgos sin responsable (ISO 27001 cl.5.3):</strong> % riesgos sin owner.</li>
      <li><strong>Riesgos altos sin plan (ISO 27005 §8.4):</strong> numero absoluto.</li>
      <li><strong>Notificacion NIS2 (Art.23):</strong> % incidentes notificados en &lt;72h.</li>
      <li><strong>Cobertura BCP (ISO 22301 / NIS2):</strong> % planes BCP aprobados.</li>
      <li><strong>MTTR incidentes (NIST CSF 2.0):</strong> dias medios de resolucion.</li>
      <li><strong>Cobertura proveedores Tier-1 (ISO 27036 / TPRM):</strong> % evaluados en 12 meses.</li>
    </ul>
    ${this._h('Direccion de los umbrales')}
    ${this._p('<strong>Mayor es mejor</strong> (ej. % cobertura): breach si el valor cae por debajo del umbral breach. <strong>Menor es mejor</strong> (ej. dias, incidentes): breach si el valor supera el umbral breach.')}
    ${this._h('Estados')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong style="color:var(--success,#22c55e);">NORMAL:</strong> dentro de limites.</li>
      <li><strong style="color:#f59e0b;">WARNING:</strong> supera el umbral de aviso.</li>
      <li><strong style="color:var(--brand-orange);">BREACH:</strong> supera el umbral critico — se envia email automatico.</li>
    </ul>
    ${this._h('Edicion y personalizacion')}
    ${this._steps([
      'Accede a Riesgos → pestana KRIs / KPIs.',
      'Haz clic en "Inicializar KPIs" para cargar los 15 KPIs de sistema (idempotente).',
      'Usa "Editar" en cualquier indicador para renombrarlo (nombre personalizado), ajustar umbrales, cambiar email de alerta o descripcion.',
      'Usa "Ocultar" para retirar de la vista indicadores que no son relevantes para tu organizacion.',
      'Los indicadores de sistema (marcados como tal) no se pueden eliminar, solo ocultar.',
      'Puedes crear KRIs personalizados con "Nuevo KRI" y vincularlos a un riesgo concreto.',
    ])}
    ${this._tip('Los KPIs de sistema se inicializan automaticamente al arrancar la aplicacion. Evaluar todos desde la vista KRIs / KPIs actualiza todos los valores instantaneamente antes de la siguiente evaluacion automatica del scheduler.')}
    ${this._h('KPIs del sistema — 15 indicadores detallados')}
    ${this._p('Cada KPI del sistema mide la eficacia global del programa SGSI, no un riesgo individual. A continuacion se describen los 15 indicadores con sus objetivos recomendados:')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--brand-purple);color:#fff;">
        <th style="padding:8px 12px;text-align:left;">Indicador</th>
        <th style="padding:8px 12px;text-align:left;">Marco</th>
        <th style="padding:8px 12px;text-align:left;">Objetivo</th>
      </tr></thead>
      <tbody>
        ${[
          ['Tasa de tratamiento','ISO 27001 cl.6.1.3','> 80% riesgos altos con plan activo'],
          ['MTTT (dias hasta iniciar tratamiento)','ISO 27001 cl.9.1','< 30 dias'],
          ['Cobertura de controles ISO 27002','ISO 27002','> 70% controles implementados o parciales'],
          ['Madurez media de controles','ISO 27001 cl.9.1','> 3 sobre 5'],
          ['Revision de politicas','ISO 27001 cl.5.2','> 90% politicas revisadas en 12 meses'],
          ['Tasa de cierre de NCs','ISO 27001 cl.10.1','> 85% NCs cerradas en SLA'],
          ['Reduccion media de riesgo','ISO 27005 §8.6','> 30% inherente → residual'],
          ['Cumplimiento del apetito','ISO 27005 §7.3','> 80% riesgos dentro del apetito'],
          ['Cobertura de activos','ISO 27005 §8.2','> 95% activos con riesgo evaluado'],
          ['Riesgos sin propietario','ISO 27001 cl.5.3','< 5% riesgos sin owner'],
          ['Riesgos altos sin plan','ISO 27005 §8.4','= 0'],
          ['Notificacion NIS2 en 72h','NIS2 Art.23','100%'],
          ['Cobertura BCP','ISO 22301 / NIS2','> 90% procesos criticos con BCP aprobado'],
          ['MTTR incidentes','NIST CSF 2.0','< 15 dias de resolucion media'],
          ['Cobertura proveedores Tier-1/2','ISO 27036 / TPRM','100% con evaluacion vigente'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          <td style="padding:8px 12px;font-weight:600;">${r[0]}</td>
          <td style="padding:8px 12px;font-size:12px;color:var(--text-muted);">${r[1]}</td>
          <td style="padding:8px 12px;">${r[2]}</td>
        </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Como editar un KPI del sistema')}
    ${this._steps([
      'Ir a Hub de Riesgos → KRIs / KPIs → pestana KPIs.',
      'Clic en el icono de edicion del KPI que quieres personalizar.',
      'Cambiar el nombre visible, los umbrales de warning y breach.',
      'Ocultar KPIs que no apliquen con el toggle "Visible".',
    ])}
    ${this._warn('Los KPIs del sistema no se pueden eliminar, solo ocultar. Ocultarlos no afecta a su calculo interno ni a las alertas de email ya configuradas.')}
    ${this._h('Bucle cerrado de KPIs')}
    ${this._p('Los KPIs no son solo informativos: cuando un KPI pasa a estado BREACH, el sistema puede elevar automaticamente el likelihood del riesgo vinculado. Cuando el KPI se recupera a NORMAL, el likelihood baja automaticamente. Este bucle garantiza que el registro de riesgos refleja en todo momento el estado operativo real del programa SGSI.')}
    <h3>KPIs del programa SGSI</h3>
    <p>Los KPIs miden la eficacia global del programa, no un riesgo individual. Se inicializan desde Hub de Riesgos &gt; KRIs / KPIs &gt; pestaña KPIs &gt; "Inicializar KPIs".</p>
    <h4>Cobertura ISO 27001</h4>
    <ul>
      <li><strong>Tasa de tratamiento</strong>: % riesgos con plan activo (objetivo &gt;80%)</li>
      <li><strong>MTTT</strong>: días medios hasta iniciar tratamiento (objetivo &lt;30 días)</li>
      <li><strong>Cobertura de controles ISO 27002</strong>: % controles implementados (objetivo &gt;70%)</li>
      <li><strong>Madurez media de controles</strong>: promedio 0-5 (objetivo &gt;3)</li>
    </ul>
    <h4>TPRM / Proveedores</h4>
    <ul>
      <li><strong>Contratos expirando en 90 días</strong>: % proveedores tier-1/2 (objetivo &lt;10%)</li>
      <li><strong>Issues críticos abiertos</strong>: # VendorIssues CRITICAL/HIGH (objetivo 0)</li>
      <li><strong>MTTR de issues</strong>: días medios de resolución (objetivo &lt;30 días)</li>
      <li><strong>Proveedores DORA evaluados</strong>: % con evaluación en 12 meses (objetivo 100%)</li>
    </ul>
    <h4>BCP / Continuidad</h4>
    <ul>
      <li><strong>RTO alcanzado</strong>: % tests BCP que cumplen objetivo (objetivo &gt;90%)</li>
      <li><strong>Días desde último test BCP</strong>: objetivo &lt;365 días (ISO 22301 §8.5)</li>
      <li><strong>Procesos críticos con BCP aprobado</strong>: objetivo &gt;90%</li>
    </ul>
    <h4>Bucle cerrado de KPIs</h4>
    <p>Cuando un KRI/KPI pasa a <strong>BREACH</strong>, el sistema eleva el <code>residual_likelihood</code> del riesgo vinculado en +1. Cuando el KRI se recupera a NORMAL, el likelihood baja −1 automáticamente.</p>
    <p>Para editar un KPI: clic en el icono de edición &gt; cambiar nombre, umbrales y visibilidad. Los KPIs del sistema no se pueden eliminar, solo ocultar.</p>
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
    ${this._h('Reglas de alerta — Riesgos')}
    ${this._p('Crea reglas para que RiskHub envie emails automaticamente cuando se cumplan ciertos criterios:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Riesgo critico:</strong> riesgos con nivel residual >= umbral configurado (ej. >=7).</li>
      <li><strong>Riesgo alto:</strong> riesgos con nivel residual >= umbral configurado (ej. >=5).</li>
      <li><strong>Tratamiento vencido:</strong> riesgos con fecha limite de tratamiento vencida.</li>
      <li><strong>Sin plan de tratamiento:</strong> riesgos de alto nivel sin plan de tratamiento definido.</li>
      <li><strong>Resumen diario:</strong> resumen diario con estadisticas globales, tratamientos vencidos y proximos vencimientos en 7 dias. Cooldown de 20 horas.</li>
      <li><strong>Vence pronto:</strong> avisa cuando un tratamiento vencera dentro de X dias (X = umbral). Util para dar margen de reaccion.</li>
    </ul>
    ${this._h('Reglas de alerta — Controles, Incidentes y mas modulos')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Control vencido:</strong> resumen de todos los controles ISO 27002 con fecha de revision vencida.</li>
      <li><strong>Incidente P1/P2:</strong> alerta cuando hay incidentes criticos/altos sin cerrar. Cooldown 20h.</li>
      <li><strong>NIS2 pendiente:</strong> alerta urgente cuando hay notificaciones NIS2 pendientes de enviar al supervisor nacional (plazo 24h por Art. 23 NIS2). Cooldown 20h.</li>
      <li><strong>Politica vencida:</strong> politicas de seguridad con fecha de revision superada. Cooldown 20h.</li>
      <li><strong>Tarea vencida:</strong> tareas de tratamiento con fecha limite superada. Cooldown 20h.</li>
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

  get _cOsint() { return `
    ${this._p('El modulo <strong>OSINT</strong> (Open Source Intelligence) permite escanear la huella digital de emails, dominios, URLs, nombres de usuario e IPs utilizando fuentes abiertas como HaveIBeenPwned, VirusTotal y GitHub. Detecta filtraciones de datos, credenciales expuestas y configuraciones inseguras antes de que sean explotadas.')}
    ${this._h('Como funciona')}
    ${this._steps([
      'Introduce el objetivo en el campo superior (email, dominio, IP, URL o username) y pulsa <strong>Escanear</strong>.',
      'El escaneo se ejecuta en segundo plano. Puedes ver el progreso en la pestana <strong>Escaneos</strong>.',
      'Al terminar, los hallazgos aparecen en la pestana <strong>Hallazgos</strong> con nivel de riesgo y score.',
      'Haz clic en cualquier hallazgo para ver el detalle completo en el panel lateral derecho.',
    ])}
    ${this._h('Tipos de escaneo')}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
      ${[
        ['Email','Comprueba filtraciones en HIBP, LeakCheck e IntelX. Detecta credenciales comprometidas.'],
        ['Dominio','Analiza subdominios, registros DNS, reputacion y configuraciones de seguridad (SPF, DMARC).'],
        ['URL','Verifica la URL contra VirusTotal y listas de malware/phishing.'],
        ['Username','Busca el nombre de usuario en GitHub y redes sociales. Detecta repos publicos con secretos expuestos.'],
        ['IP','Comprueba reputacion en bases de datos de amenazas y detecta puertos abiertos.'],
        ['Modo masivo','Pega hasta 50 objetivos (uno por linea) para escanearlos todos de una vez.'],
      ].map(([t,d]) => `
        <div style="background:var(--bg-2);border-radius:8px;padding:10px 14px;font-size:13px;">
          <div style="font-weight:600;margin-bottom:4px;color:var(--brand-purple);">${t}</div>
          <div style="color:var(--text-muted);">${d}</div>
        </div>`).join('')}
    </div>
    ${this._h('Gestion de hallazgos')}
    ${this._p('Cada hallazgo tiene un nivel de riesgo (CRITICAL / HIGH / MEDIUM / LOW / INFO) y un score 0-100. Desde la tabla o el panel lateral puedes:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Resolver:</strong> marca el hallazgo como remediado una vez aplicada la correccion.</li>
      <li><strong>+ Incidente:</strong> crea automaticamente un incidente de seguridad vinculado al hallazgo para seguimiento NIS2.</li>
      <li><strong>Exportar CSV:</strong> descarga todos los hallazgos en formato Excel-compatible para auditorias.</li>
    </ul>
    ${this._h('Objetivos monitorizados')}
    ${this._p('Cada objetivo escaneado queda registrado en la pestana <strong>Objetivos</strong> con su nivel de riesgo consolidado y la fecha del ultimo escaneo. Desde aqui puedes:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Re-escanear:</strong> lanza un nuevo escaneo del mismo objetivo para actualizar los resultados.</li>
      <li><strong>Eliminar:</strong> elimina el objetivo y todos sus hallazgos asociados de la base de datos. Util para limpiar objetivos de prueba (ej: test@example.com).</li>
    </ul>
    ${this._h('Importar desde Microsoft Entra ID')}
    ${this._p('Si tu organizacion usa Microsoft Entra ID (Azure AD), puedes importar automaticamente todos los usuarios y dominios del tenant para escanearlos en bloque. Necesitas un App Registration con permiso <em>User.Read.All</em>.')}
    ${this._h('Importar de Entra ID')}
    ${this._steps([
      'Despliega el panel <strong>Importar de Entra ID</strong> en el lanzador de escaneos.',
      'Introduce Tenant ID, Client ID y Client Secret del App Registration.',
      'Haz clic en <strong>Ver objetivos</strong> para previsualizar los usuarios y dominios del tenant.',
      'Selecciona si escanear usuarios, dominios o ambos, y define el limite de usuarios.',
      'Haz clic en <strong>Importar e iniciar escaneos</strong> para lanzar todos los escaneos en segundo plano.',
    ])}
    ${this._h('Pipeline automatico completo al completar un escaneo (v1.7.5 + v1.7.6)')}
    ${this._p('Cuando un escaneo OSINT completa, el sistema ejecuta automaticamente tres acciones sin intervencion del usuario:')}
    <ol style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Vinculacion a activos:</strong> el agente busca en el inventario por nombre, dominio o IP. Si encuentra coincidencia, vincula el hallazgo al activo correspondiente.</li>
      <li><strong>Creacion de riesgos:</strong> para cada hallazgo sin riesgo previo, genera un escenario de riesgo en la seccion Riesgos con la etiqueta <strong style="background:var(--brand-purple-4);color:var(--brand-purple);padding:1px 4px;border-radius:3px;font-size:11px;">IA</strong>.</li>
      <li><strong>Creacion de incidente:</strong> si hay hallazgos de nivel CRITICAL o HIGH, se crea automaticamente un incidente de seguridad (P1 si es CRITICAL, P2 si es HIGH) con los hallazgos principales en la descripcion y la bandera NIS2 activada si procede.</li>
    </ol>
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Los riesgos OSINT son completamente editables.</li>
      <li>El incidente auto-creado aparece en la seccion Incidentes listo para investigar — con referencia al scan OSINT que lo originó.</li>
      <li>Si el escaneo no produce hallazgos HIGH o CRITICAL, no se crea ningun incidente.</li>
      <li>Re-escanear el mismo objetivo no duplica el incidente si ya existe uno para ese scan.</li>
    </ul>
    ${this._tip('Los hallazgos CRITICAL sin remediar generan una alerta visual en rojo en la parte superior de la pestana Hallazgos. Configura una regla de alerta por email en <strong>Alertas</strong> para recibir notificaciones automaticas cuando aparezcan hallazgos de alto riesgo.')}
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
    ${this._h('Configurar frameworks activos')}
    ${this._steps([
      'Pulsa <strong>Configurar</strong> en el panel superior del dashboard de cumplimiento.',
      'Selecciona los frameworks que aplican a tu organizacion: ISO 27001, GDPR, NIS2, HIPAA, NIST CSF, SOC2, ENS, DORA, ISO 42001.',
      'El sistema inicializa todos los requisitos de los frameworks seleccionados.',
      'A medida que registras datos en RiskHub (controles, evidencias, riesgos tratados), el cumplimiento se actualiza automaticamente.',
    ])}
    ${this._h('Cross-mapping automatico de controles')}
    ${this._p('Cuando se implementa un control ISO 27002, el sistema propaga automaticamente ese estado a todos los requisitos equivalentes en los frameworks activos. Por ejemplo, implementar el control <strong>8.5 Autenticacion segura</strong> marca simultaneamente ISO 27001 A.8.5, NIST CSF PR.AA, SOC2 CC6.1, HIPAA 164.312(d), NIS2 Art. 21.2.i y ENS op.acc.5. Implementas una vez y el cumplimiento se actualiza en todos los marcos.')}
    ${this._h('Brechas identificadas')}
    ${this._p('El dashboard muestra las brechas especificas para cada marco con referencia al articulo o clausula normativa afectada. Cada brecha indica que dato falta o que proceso esta incompleto. Usa estas brechas como checklist de mejora antes de una auditoria.')}
    ${this._h('Paquete de auditoria')}
    ${this._p('Desde <em>Auditoria → Paquete por framework</em>, genera un ZIP estructurado con el orden oficial del framework: dominios, requisitos, evidencias vinculadas, gaps y attestation SHA-256. Este paquete es el entregable principal para un auditor externo.')}
    ${this._tip('<strong>Nota:</strong> Las puntuaciones son estimaciones basadas en los datos registrados. Una auditoria formal puede revelar brechas adicionales. Usa el dashboard como herramienta de preparacion y seguimiento, no como certificacion de cumplimiento.')}
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
    <h3>Ciclo de vida del proveedor (v5.5)</h3>
    <p>Cada proveedor pasa por etapas formales: <strong>prospecting → onboarding → active → under_review → offboarding → terminated</strong>.</p>
    <p>Para cambiar el stage: Editar proveedor &gt; sección "Ciclo de vida y onboarding" &gt; seleccionar stage.</p>
    <p>Al entrar en <strong>onboarding</strong>, se genera automáticamente un checklist de items según los flags del proveedor (DPA si procesa datos, cláusula NIS2, items DORA, evaluación tier-1 en 30 días). Al llegar al 100%, el proveedor pasa a <strong>active</strong> automáticamente.</p>
    <h4>Sign-off legal</h4>
    <ul>
      <li><strong>DPA (GDPR Art.28)</strong>: Ciclo de vida &gt; "Registrar DPA firmado". Al registrarlo, la tarea GDPR pendiente se cierra automáticamente.</li>
      <li><strong>NDA</strong>: Ciclo de vida &gt; "Registrar NDA firmado"</li>
      <li><strong>Contrato</strong>: Ciclo de vida &gt; "Registrar Contrato"</li>
    </ul>
    <h4>Concentración de riesgo DORA (Art.28)</h4>
    <p>Si &gt;40% de los procesos críticos dependen de un proveedor, se genera alerta y VendorIssue automático. Ver mapa: Hub Proveedores &gt; TPRM &gt; Concentración DORA.</p>
    <p>Para mitigar: documentar notas y estrategia de salida en el proveedor. Al hacerlo, el VendorIssue se cierra automáticamente.</p>
    <h4>SLA → KRI</h4>
    <p>Convierte SLAs de un contrato en KRIs monitorizables: botón "SLA → KRI" en el proveedor. Los umbrales se calculan automáticamente (warning: 98% del objetivo, breach: 95%).</p>
  `;},

  get _cTprm() { return `
    ${this._p('El <strong>Dashboard TPRM (Third-Party Risk Management)</strong> amplia el modulo de Proveedores con la gestion del ciclo de vida del tercero, el <strong>tiering por criticidad</strong> y el calculo de <strong>inherent risk</strong> e <strong>residual risk</strong>, alineado con NIS2, DORA, ENS y GDPR.')}
    ${this._h('Inherent risk y tiering')}
    ${this._p('El inherent risk (0-100, mayor = mas riesgo) se calcula automaticamente a partir del perfil del proveedor: sensibilidad y volumen de datos, tipo de acceso a sistemas, criticidad para el negocio, alcance regulatorio (NIS2/DORA/ENS/GDPR) y riesgo geografico. A partir de ese valor se deriva el <strong>tier</strong>:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Critico</strong> (>= 80): cuestionario completo + DPA + DR/BCP + pentest anual.</li>
      <li><strong>Alto</strong> (60-79), <strong>Medio</strong> (30-59), <strong>Bajo</strong> (< 30).</li>
    </ul>
    ${this._h('Residual risk')}
    ${this._p('El residual risk = inherent risk x (1 - efectividad de controles / 100). La efectividad de controles se deriva de la puntuacion del cuestionario de seguridad del proveedor. Cuanto mejor responda y evidencie, menor es su riesgo residual.')}
    ${this._h('Plantillas de cuestionario del sistema')}
    ${this._p('Al crear un cuestionario puedes elegir una plantilla preestablecida (clonable): ISO 27001 completo, NIS2 art. 21, DORA arts. 28-30, GDPR encargado, declaracion de uso de IA (ISO 42001) o checklist de offboarding. Cada pregunta lleva pesos, reglas de scoring y mapeo a controles del marco correspondiente.')}
    ${this._h('Recalculo del portfolio')}
    ${this._steps([
      'Edita el perfil del proveedor (pestana Proveedores) con los atributos de riesgo inherente.',
      'El tier y los scores se recalculan automaticamente al guardar; tambien con el boton <strong>Recalcular</strong>.',
      'Usa <strong>Recalcular portfolio</strong> en el dashboard TPRM para refrescar toda la cartera.',
      'Consulta el heatmap inherent vs residual y el top 10 de proveedores por riesgo residual.',
    ])}
    ${this._h('Evaluaciones consolidadas')}
    ${this._p('La pestana <strong>Evaluaciones</strong> agrega el riesgo inherente del proveedor, los cuestionarios respondidos (media de puntuaciones) y un desglose por dominio funcional en una unica evaluacion. Cada evaluacion puede <strong>aprobarse</strong> y <strong>enviarse al registro de riesgos ISO 27005</strong> con un clic (boton "Push a riesgos"), creando una entrada de riesgo de cadena de suministro vinculada.')}
    ${this._h('Evaluacion por IA de los cuestionarios')}
    ${this._p('Cuando un proveedor responde un cuestionario, RiskHub puede evaluar las respuestas con IA (Claude) y devolver una puntuacion, nivel de confianza, banderas rojas y preguntas de seguimiento. Si la confianza es baja, el cuestionario se marca para revision manual obligatoria. Requiere configurar la API key en IA -> Configuracion. Tambien puedes lanzarla manualmente con el boton "Evaluar IA" en la tabla de cuestionarios.')}
    ${this._h('Hallazgos y SLA')}
    ${this._p('La pestana <strong>Hallazgos</strong> registra issues del proveedor con SLA automatico por severidad (critico 7 dias, alto 30, medio 90, bajo 180). Los hallazgos vencidos se marcan automaticamente como "Vencido". Gestiona la remediacion, la asignacion y la aceptacion de riesgo desde aqui.')}
    ${this._tip('<strong>Nota:</strong> el modulo reutiliza el registro de proveedores y los cuestionarios existentes; no crea un silo paralelo. Los proveedores con riesgo residual alto pueden vincularse al registro de riesgos ISO 27005 central.')}
    <h3>TPRM inteligente (v5.5-5.6)</h3>
    <h4>Score decay</h4>
    <p>Si un proveedor no es reevaluado en &gt;12 meses, su score se degrada 8%/mes. Se genera un VendorIssue automático (<code>source=score_decay</code>). Para recuperar: realizar nueva evaluación TPRM.</p>
    <h4>Contratos expirando</h4>
    <p>El scheduler comprueba semanalmente contratos que expiren en &lt;90 días y genera un VendorIssue automático. Para cerrar: actualizar la fecha de expiración en el proveedor.</p>
    <h4>VendorIssue CRITICAL → Riesgo ISO 27005</h4>
    <p>Al crear un VendorIssue con severidad CRITICAL, el sistema crea automáticamente un riesgo en el registro. Al cerrar el VendorIssue, el riesgo reduce su likelihood automáticamente.</p>
    <h4>OSINT → VendorIssue</h4>
    <p>Hallazgos OSINT CRITICAL/HIGH que coincidan con el dominio de un proveedor generan un VendorIssue automático. Al resolver el hallazgo, el issue puede marcarse como mitigado.</p>
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

  get _cRegwatch() { return `
    ${this._p('La <strong>Vigilancia Normativa Automatica</strong> mantiene tu catalogo normativo al dia sin que tengas que hacer nada. Funciona como las actualizaciones automaticas de un sistema operativo: lo activas una vez y RiskHub se encarga del resto, avisandote solo cuando necesita tu confirmacion. Esta en <strong>Cumplimiento &rarr; Vigilancia normativa</strong>.')}
    ${this._h('Activacion en un clic')}
    ${this._steps([
      'Pulsa el interruptor <strong>ON</strong> en la tarjeta de Vigilancia Normativa (solo admin).',
      'Confirma con una frase en el dialogo: <em>"Vamos a vigilar N marcos normativos que estas usando..."</em>.',
      'Listo. RiskHub detecta automaticamente los marcos que usas (ISO 27001, NIS2, ENS, RGPD, DORA, ISO 42001...) y empieza a vigilarlos.',
    ])}
    ${this._p('Los frameworks vigilados se <strong>derivan solos</strong> de lo que ya usas en RiskHub (modulo Cumplimiento y clasificacion regulatoria de proveedores). Si empiezas a usar uno nuevo, entra en la vigilancia automaticamente. No hay que configurar fuentes, scrapers ni IA.')}
    ${this._h('Severidad de los cambios')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--brand-purple);color:#fff;">
        <th style="padding:8px;text-align:left;">Severidad</th><th style="padding:8px;text-align:left;">Que ocurre</th>
      </tr></thead>
      <tbody>
        <tr><td style="padding:8px;"><strong>Cosmetico</strong></td><td style="padding:8px;">Cambio de redaccion menor. Se aplica solo; aparece en el historial.</td></tr>
        <tr style="background:var(--bg-2);"><td style="padding:8px;"><strong>Aclaracion</strong></td><td style="padding:8px;">Guidance que clarifica un control. Se aplica solo; va en el digest.</td></tr>
        <tr><td style="padding:8px;"><strong>Sustantivo</strong></td><td style="padding:8px;">Control nuevo/eliminado/modificado. Genera un item en tu bandeja para que decidas sobre tus copias.</td></tr>
        <tr style="background:var(--bg-2);"><td style="padding:8px;"><strong>Version mayor</strong></td><td style="padding:8px;">Nueva version del estandar. Aviso destacado + asistente de revision.</td></tr>
      </tbody>
    </table>
    ${this._h('Bandeja de actualizaciones y revision')}
    ${this._p('Cuando un cambio sustantivo afecta a un marco que usas, aparece un item con dos botones: <strong>Revisar</strong> (abre un asistente breve con el resumen, el impacto sobre tus politicas y requisitos, y un boton Aplicar) y <strong>Aplazar 7 dias</strong>. El historial es exportable a PDF como evidencia ante auditor.')}
    ${this._h('Opciones avanzadas (colapsadas, solo admin)')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Email de notificaciones:</strong> por defecto, el del primer admin.</li>
      <li><strong>Frecuencia del digest:</strong> diaria / semanal (def.) / mensual / nunca.</li>
      <li><strong>Auto-aplicar a copias:</strong> desactivado por defecto; los cambios sustantivos siempre requieren tu confirmacion.</li>
    </ul>
    ${this._tip('<strong>No interpreta legalmente las normas ni sustituye a tu consultor o auditor:</strong> detecta y propone cambios sobre documentos publicos. No procesa datos personales de tu organizacion. Desactivar el interruptor no rompe nada y conserva tu configuracion.')}
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

  get _cOrganizations() { return `
    ${this._p('La seccion <strong>Organizaciones</strong> permite gestionar el multi-tenancy de RiskHub. Solo los usuarios con rol <strong>superadmin</strong> pueden acceder a esta vista. Cada organizacion es un tenant aislado: sus datos (activos, riesgos, controles, incidentes, etc.) son completamente invisibles para otras organizaciones.')}
    ${this._warn('Esta seccion solo es visible para superadmins. Los usuarios con rol admin o analyst no tienen acceso.')}

    ${this._h('Aislamiento de datos (row-level isolation)')}
    ${this._p('Todos los modelos de negocio tienen un campo <code>organization_id</code>. Cada query del backend filtra automaticamente por la organizacion del usuario autenticado. El superadmin puede ver y gestionar todos los tenants.')}

    ${this._h('Funciones disponibles')}
    <ul style="font-size:14px;line-height:1.8;">
      <li><strong>Crear organizacion:</strong> define nombre, dominio de email (usado para auto-asignar usuarios al registrarse), plan y limite de usuarios.</li>
      <li><strong>Editar organizacion:</strong> modificar nombre, dominio, plan y max_users desde el panel de detalle.</li>
      <li><strong>Desactivar / activar:</strong> desactivar una org (soft-delete) impide que sus usuarios inicien sesion sin borrar datos.</li>
      <li><strong>Ver usuarios:</strong> lista de todos los usuarios del tenant con su rol y estado.</li>
      <li><strong>Mover usuario:</strong> el superadmin puede reasignar un usuario a otra organizacion.</li>
    </ul>

    ${this._h('Planes de organizacion')}
    <table style="width:100%;font-size:13px;border-collapse:collapse;">
      <thead><tr><th style="text-align:left;padding:6px;border-bottom:1px solid var(--border)">Plan</th><th style="text-align:left;padding:6px;border-bottom:1px solid var(--border)">Descripcion</th></tr></thead>
      <tbody>
        <tr><td style="padding:6px;border-bottom:1px solid var(--border)"><strong>starter</strong></td><td style="padding:6px;border-bottom:1px solid var(--border)">Organizacion pequena — max 10 usuarios por defecto</td></tr>
        <tr><td style="padding:6px;border-bottom:1px solid var(--border)"><strong>professional</strong></td><td style="padding:6px;border-bottom:1px solid var(--border)">Organizacion mediana — max configurable</td></tr>
        <tr><td style="padding:6px;"><strong>enterprise</strong></td><td style="padding:6px;">Organizacion grande — sin limite practico</td></tr>
      </tbody>
    </table>

    ${this._h('Auto-asignacion de usuarios')}
    ${this._p('Cuando el admin crea un nuevo usuario, el sistema intenta asignarle automaticamente una organizacion: primero busca coincidencia por dominio de email, luego usa la organizacion del admin que lo crea. Esto simplifica el onboarding en entornos multi-empresa.')}

    ${this._tip('<strong>Seguridad:</strong> el aislamiento es a nivel de base de datos (filtros SQL en cada endpoint). No es posible que un usuario vea datos de otra organizacion, ni siquiera conociendo el ID del recurso, gracias a los filtros de org implementados en todos los routers del backend.')}
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

  get _cNavigation() { return `
    ${this._p('RiskHub organiza todas las funcionalidades en <strong>8 hubs</strong> accesibles desde el menu lateral izquierdo. Cada hub agrupa secciones relacionadas en <strong>pestanas internas</strong>, reduciendo el numero de pantallas visibles y facilitando la orientacion.')}
    ${this._h('Los 8 hubs')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--brand-purple);color:#fff;">
        <th style="padding:8px 12px;text-align:left;">Hub</th>
        <th style="padding:8px 12px;text-align:left;">Pestanas incluidas</th>
        <th style="padding:8px 12px;text-align:left;">Roles</th>
      </tr></thead>
      <tbody>
        ${[
          ['Inicio','Dashboard · Ejecutivo · Heatmap + Bandeja de revision','Todos'],
          ['Riesgos y activos','Registro de riesgos · Activos · Amenazas · Vulnerabilidades · MAGERIT','Todos'],
          ['Vigilancia','CVE Monitor · OSINT · Hallazgos externos · Rev. arquitectura · Predictivo','Analyst, Admin'],
          ['Cumplimiento','Normativo · Controles · Monitor · SoA · Politicas · Auditorias · Rev. direccion · Cambios','Todos'],
          ['Eventos','Incidentes · NIS2 · No conformidades · BCP · Proveedores · RGPD','Analyst, Admin'],
          ['Informes','Informes · Programados · Evidencias · Trust Portal · Calendario · Tareas','Todos'],
          ['Agente IA','Chat · Documentos','Analyst, Admin'],
          ['Configuracion','Usuarios · Integraciones · ITSM · Webhooks · Alertas · Awareness · Auditoria · Organizaciones · Modulos','Admin, Superadmin'],
        ].map(([hub, tabs, roles]) => `
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:8px 12px;font-weight:600;">${hub}</td>
            <td style="padding:8px 12px;font-size:12px;color:var(--text-muted);">${tabs}</td>
            <td style="padding:8px 12px;font-size:12px;">${roles}</td>
          </tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Deep-linking')}
    ${this._p('Cada pestana tiene su propia URL: por ejemplo <code>#/compliance-hub/controls</code> o <code>#/events-hub/incidents</code>. Las URLs antiguas (ej. <code>#/risks</code>) redirigen automaticamente a su hub correspondiente, por lo que todos tus favoritos siguen funcionando.')}
    ${this._h('Acciones rapidas (FAB)')}
    ${this._p('El boton <strong>+</strong> en la esquina inferior derecha ofrece tres acciones directas: Nuevo riesgo, Nuevo incidente y Agente IA — las operaciones mas frecuentes sin necesidad de navegar.')}
    ${this._h('Atajos de teclado')}
    ${this._p('Pulsa <kbd>?</kbd> en cualquier momento para ver todos los atajos disponibles. Los atajos <kbd>g</kbd>+<kbd>letra</kbd> permiten navegar directamente a los hubs principales (ej. <kbd>g</kbd>+<kbd>r</kbd> = Riesgos).')}
  `;},

  get _cInbox() { return `
    ${this._p('La <strong>Bandeja de revision</strong> agrega en un unico lugar todos los elementos que las automatizaciones de RiskHub han generado y que requieren una decision humana. Aparece en la parte superior del Dashboard (Inicio) y tambien es accesible en <code>#/inbox</code>.')}
    ${this._h('Que aparece en la bandeja')}
    ${this._steps([
      '<strong>Riesgos auto-generados</strong> — creados automaticamente por el Agente IA al analizar CVEs, hallazgos OSINT o proveedores con score bajo. Aparecen en estado Identificado/Evaluado pendientes de confirmacion.',
      '<strong>Incidentes criticos y altos abiertos</strong> — incidentes P1 y P2 en estado Abierto o En investigacion, incluidos los auto-creados por OSINT.',
      '<strong>Notificaciones NIS2 pendientes</strong> — con indicador de horas restantes de plazo (critico si quedan menos de 12 h).',
      '<strong>Controles degradados</strong> — controles que el scheduler ha degradado automaticamente a PARTIAL por tener la revision vencida.',
      '<strong>Tareas vencidas</strong> — tareas de tratamiento de riesgo con fecha limite superada.',
      '<strong>No conformidades sin accion correctiva</strong> — NC abiertas que aun no tienen definida ninguna accion.',
    ])}
    ${this._h('Severidad y orden')}
    ${this._p('Los elementos se ordenan por severidad (critico > alto > medio > informativo) y luego por fecha. Cada elemento muestra un badge de color con texto descriptivo (no solo color) para accesibilidad.')}
    ${this._h('Acciones disponibles')}
    ${this._p('<strong>Revisar</strong> navega directamente al elemento en su vista correspondiente. <strong>Descartar</strong> (requiere rol Analyst o Admin) elimina el elemento de la bandeja de forma auditada — el registro subyacente no se borra, solo deja de aparecer en la bandeja. Todas las acciones de descarte quedan registradas en el Log de Auditoria.')}
    ${this._h('Automatizacion')}
    ${this._p('La bandeja se actualiza en cada navegacion. El objetivo es que el usuario visite RiskHub una vez por semana, despache los elementos pendientes en pocos minutos, y la aplicacion se encargue del resto de forma autonoma.')}
  `;},

  get _cAiChat() { return `
    ${this._p('El <strong>Chat con el Agente IA</strong> permite consultar en lenguaje natural el estado de seguridad de tu organizacion y recibir guia paso a paso sobre configuracion. El agente combina el contexto enriquecido de RiskHub (activos, riesgos, controles, incidentes) con los documentos que hayas subido.')}
    ${this._h('Como funciona')}
    ${this._steps([
      'El agente recibe automaticamente el contexto de tu organizacion: activos, riesgos activos, incidentes recientes, controles con baja madurez y proveedores criticos.',
      'Si has subido documentacion (arquitectura, normativa, politicas...), el agente tambien realiza una busqueda por similitud en esos documentos y los incluye en su contexto.',
      'Escribe tu consulta en el campo de texto y pulsa Enter o Enviar.',
      'El agente responde siempre en castellano, con recomendaciones orientadas a la accion.',
      'Puedes valorar cada respuesta (1-5 estrellas) para que el sistema registre la calidad.',
    ])}
    ${this._h('Tipos de preguntas que puedes hacer')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--brand-purple);color:#fff;">
        <th style="padding:8px 12px;text-align:left;">Categoria</th>
        <th style="padding:8px 12px;text-align:left;">Ejemplos</th>
      </tr></thead>
      <tbody>
        <tr style="background:var(--bg-2);">
          <td style="padding:8px 12px;font-weight:600;">Analisis de riesgos</td>
          <td style="padding:8px 12px;">Dame un resumen ejecutivo de riesgos criticos. Que riesgos deberia priorizar este mes?</td>
        </tr>
        <tr>
          <td style="padding:8px 12px;font-weight:600;">Controles y madurez</td>
          <td style="padding:8px 12px;">Que controles tienen baja madurez? Propón tareas para mejorar ISO 27002.</td>
        </tr>
        <tr style="background:var(--bg-2);">
          <td style="padding:8px 12px;font-weight:600;">Incidentes y compliance</td>
          <td style="padding:8px 12px;">Tenemos ransomware. Que pasos segun NIS2? Cuales son las brechas en ISO 27002?</td>
        </tr>
        <tr>
          <td style="padding:8px 12px;font-weight:600;">Configuracion y ayuda</td>
          <td style="padding:8px 12px;">Como configuro la API key? Como subo documentos? Como funciona el agente?</td>
        </tr>
        <tr style="background:var(--bg-2);">
          <td style="padding:8px 12px;font-weight:600;">Proveedores y RGPD</td>
          <td style="padding:8px 12px;">Hay proveedores criticos sin evaluacion? Necesitamos actualizar DPIAs?</td>
        </tr>
      </tbody>
    </table>
    ${this._h('Preguntas rapidas sugeridas')}
    ${this._p('En el panel lateral tienes accesos rapidos a preguntas frecuentes sobre analisis de riesgos y control. Tambien puedes acceder directamente a <em>Configuracion IA</em> y <em>Gestionar documentos</em> sin salir del chat.')}
    ${this._warn('<strong>Importante:</strong> El agente usa la API de Claude (Anthropic). Configura tu API key en <em>Config. Agente</em> antes de usar el chat. La informacion enviada se anonimiza segun el nivel configurado.')}
    ${this._tip('<strong>Pro tip:</strong> Cuanto mas documentacion hayas subido (arquitectura, politicas, normativas), mas precisas seran las respuestas del agente. Usa "Como gestiono documentos?" en el chat para recibir instrucciones paso a paso.')}
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
    ${this._h('Subida multiple y arrastre')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Haz clic en <strong>+ Subir documentos</strong> para seleccionar varios archivos a la vez.</li>
      <li>Arrastra archivos desde el explorador de Windows/Mac directamente a la zona de arrastre.</li>
      <li>Asigna categoria a cada archivo antes de hacer clic en <strong>Subir N documentos</strong>.</li>
    </ul>
    ${this._h('Analisis ISMS automatico (v1.7.4)')}
    ${this._p('Tras indexar un documento, el agente IA lo analiza automaticamente en background para enriquecer el SGSI. No es necesaria ninguna accion manual.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Politicas:</strong> si el documento es una politica de seguridad, se crea automaticamente un registro en la seccion Politicas con titulo, categoria, version, alcance, clausulas ISO y fecha de revision.</li>
      <li><strong>Controles ISO 27002:</strong> los controles cubiertos por el documento se crean o actualizan en la seccion Controles (estado, madurez y referencia al documento). El estado solo mejora, nunca se degrada.</li>
      <li><strong>Tareas de tratamiento:</strong> se crean tareas en la seccion Tareas para los riesgos activos cuyas amenazas coincidan con las categorias abordadas en el documento.</li>
    </ul>
    ${this._warn('El analisis ISMS requiere una API key del agente IA configurada. Sin ella, el estado aparece como "Sin IA". Configura la clave en <strong>Configuracion del Agente</strong>.')}
    ${this._tip('Usa el boton <strong>Analizar</strong> en la tabla para relanzar el analisis de cualquier documento ya indexado (util para documentos subidos antes de v1.7.4).')}
    ${this._h('Auto-categorizacion IA (v1.7.8)')}
    ${this._p('Tras el analisis ISMS, el sistema infiere automaticamente la categoria correcta del documento basandose en su contenido. Si se detecta una categoria diferente a la asignada manualmente, se actualiza y aparece un badge <strong>IA</strong> junto a la categoria en la tabla.')}
    ${this._h('Imagenes de arquitectura (v1.7.8)')}
    ${this._p('Puedes subir imagenes PNG y JPG (diagramas de red, topologias) en la categoria <em>Arquitectura y sistemas</em>. Estas imagenes se procesan directamente mediante Claude Vision en la seccion <strong>Rev. Arquitectura</strong>.')}
  `;},

  get _cArchitectureReview() { return `
    ${this._p('La <strong>Revision de Arquitectura de Seguridad</strong> usa IA para analizar tus diagramas y documentos de red, identificar vulnerabilidades de configuracion y proponer mejoras alineadas con ISO 27001 y Zero Trust.')}
    ${this._h('Como usarlo')}
    ${this._steps([
      'Sube diagramas de red, documentos de arquitectura o topologias (PDF, DOCX, PNG, JPG) en la seccion <strong>Docs del Agente</strong> con la categoria <strong>Arquitectura y sistemas</strong>.',
      'Ve a <strong>Rev. Arquitectura</strong> en el menu lateral.',
      'Haz clic en <strong>Analizar arquitectura de seguridad</strong>.',
      'Revisa los resultados: inventario de componentes, vulnerabilidades por criticidad, mejoras propuestas y cumplimiento con ISO 27002 y Zero Trust.',
    ])}
    ${this._h('Resultados del analisis')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Inventario:</strong> componentes identificados (firewalls, servidores, redes, etc.).</li>
      <li><strong>Vulnerabilidades:</strong> problemas de configuracion con nivel de criticidad (CRITICO/ALTO/MEDIO/BAJO), CVE si aplica y control ISO 27002 violado.</li>
      <li><strong>Mejoras:</strong> propuestas concretas con prioridad y esfuerzo estimado.</li>
      <li><strong>Cumplimiento:</strong> controles ISO 27002 cubiertos/no cubiertos, recomendaciones Zero Trust y propuesta de segmentacion de red.</li>
    </ul>
    ${this._warn('El analisis es generado por IA. Debe ser revisado por el equipo de seguridad antes de implementar cambios en produccion.')}
    ${this._tip('Para obtener mejores resultados, sube diagramas en formato imagen (PNG/JPG) junto con documentos de descripcion en texto. El agente analizara ambos formatos en conjunto.')}
  `;},

  get _cExecutive() { return `
    ${this._p('El <strong>Dashboard Ejecutivo</strong> proporciona una visión global de la postura de seguridad de la organización en tiempo real: KPIs, tendencia de riesgos, estado de cumplimiento por framework y top riesgos activos.')}
    ${this._h('KPIs principales')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Riesgos totales / Altos / Sobre apetito:</strong> contadores en tiempo real filtrados por org.</li>
      <li><strong>Mitigados %:</strong> porcentaje de riesgos con tratamiento completado.</li>
      <li><strong>Controles implementados %:</strong> madurez global del SGSI.</li>
      <li><strong>Tareas vencidas / Incidentes 30d / Edad media tratamiento:</strong> métricas operativas.</li>
    </ul>
    ${this._h('Informe PDF ejecutivo')}
    ${this._p('El botón "Descargar informe PDF" genera un informe ejecutivo con KPIs, top riesgos, estado de cumplimiento por framework y resumen narrativo. Útil para presentaciones al Comité de Dirección.')}
    ${this._tip('El informe se genera on-demand. Para envío mensual automático, activa el job de informe mensual en el scheduler (ya activo por defecto el día 1 de cada mes).')}
  `;},

  get _cCcm() { return `
    ${this._p('La <strong>Monitorización Continua de Controles (CCM)</strong> ejecuta 27 tests automáticos sobre los datos internos del SGSI y calcula un score de cumplimiento operativo (0-100).')}
    ${this._h('Cómo funciona')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Los tests se ejecutan manualmente desde la vista o automáticamente cada 24h por el scheduler.</li>
      <li>Cada test verifica un control ISO 27002 específico usando datos internos (no requiere integraciones externas).</li>
      <li>Resultado: PASS / WARNING / FAIL / SKIP con detalle y recomendación de acción.</li>
      <li>Si el score baja de 70 y hay FAILs, se envía email de alerta a los administradores.</li>
    </ul>
    ${this._h('Tests incluidos (27)')}
    ${this._p('Activos con propietario y clasificación, riesgos altos con tratamiento y tareas, controles con evidencia, políticas vigentes, incidentes P1/P2 resueltos, proveedores evaluados anualmente, SLA de tareas, frescura de evidencias (<12m), MFA en admins, vulnerabilidades críticas gestionadas, apetito de riesgo definido, frameworks activos, evidencias de backup, riesgos altos revisados en 90d, usuarios inactivos >90d, contratos de proveedores vigentes, registro GDPR Art.30, auditorías internas anuales, no conformidades gestionadas, contexto SGSI completo, tareas con responsable asignado, formación de awareness, plan de respuesta a incidentes, cobertura de riesgos por activo, evidencias vinculadas a compliance.')}
    ${this._warn('El CCM complementa, no sustituye, a una auditoría formal. Los resultados son orientativos sobre el estado operativo del SGSI.')}
  `;},

  get _cEvidence() { return `
    ${this._p('El <strong>repositorio de Evidencias</strong> centraliza toda la documentación que acredita el cumplimiento de controles y requisitos normativos. Soporta versionado, fechas de expiración y vinculación a frameworks.')}
    ${this._h('Subir evidencias')}
    ${this._steps([
      'Pulsa "+ Subir evidencia" y selecciona el archivo (cualquier formato).',
      'Asigna título, tipo (política, certificado, log, informe...), framework y requisito específico.',
      'Opcionalmente, define fecha de validez y fecha de expiración.',
      'La evidencia queda vinculada al requisito normativo y aparece en el gap analysis.',
    ])}
    ${this._h('Inferencia automática')}
    ${this._p('Cuando subes un documento al Agente IA y se analiza con ISMS, el sistema <strong>infiere automáticamente</strong> qué requisitos de tus frameworks activos cubre el documento y crea las evidencias vinculadas. Un documento de política de backups puede cubrir simultáneamente ISO27001 A.8.13, NIS2 Art.21.2.b, HIPAA y NIST CSF.')}
    ${this._tip('Las evidencias próximas a vencer reciben alertas automáticas 30 días antes de su expiración.')}
  `;},

  get _cMagerit() { return `
    ${this._p('<strong>MAGERIT v3</strong> es la metodología española de análisis y gestión de riesgos desarrollada por el Consejo Superior de Administración Electrónica. RiskHub implementa el catálogo de amenazas MAGERIT y la valoración de activos por dimensiones de seguridad.')}
    ${this._h('Dimensiones de seguridad MAGERIT')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:14px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px;">Dimensión</th><th style="padding:8px;">Descripción</th>
      </tr></thead>
      <tbody>
        ${[['D — Disponibilidad','Garantía de acceso al servicio cuando se necesita'],
           ['I — Integridad','Mantenimiento de la exactitud y completitud de la información'],
           ['C — Confidencialidad','Acceso solo a usuarios autorizados'],
           ['A — Autenticidad','Verificación de la identidad de quien accede o actúa'],
           ['T — Trazabilidad','Registro de quién hizo qué y cuándo'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}><td style="padding:8px;font-weight:600;">${r[0]}</td><td style="padding:8px;">${r[1]}</td></tr>`).join('')}
      </tbody>
    </table>
    ${this._h('Cargar amenazas MAGERIT')}
    ${this._p('Ve a <em>API → /api/magerit/seed</em> o solicita al administrador que cargue el catálogo MAGERIT para tu organización. Se importan las 47 amenazas del libro II de MAGERIT v3 clasificadas en desastres naturales, errores no intencionados y ataques deliberados.')}
    ${this._tip('MAGERIT es obligatorio para organismos de la Administración Pública española y recomendado para empresas que operan bajo el ENS (Esquema Nacional de Seguridad).')}
  `;},

  get _cTrustPortal() { return `
    ${this._p('El <strong>Trust Portal</strong> es una página pública que muestra el estado de cumplimiento de tu organización a clientes, prospects y socios. El <strong>Portal de Auditor</strong> da acceso de solo lectura a auditores externos con un token seguro.')}
    ${this._h('Trust Portal (público)')}
    ${this._steps([
      'Ve a Informes → Trust Portal (requiere rol admin).',
      'Configura qué información mostrar: frameworks, resumen de riesgos, última auditoría.',
      'Copia la URL pública y compártela en tu web corporativa, propuestas comerciales o solicitudes de due diligence.',
      'Si la URL queda comprometida, regenera el token para invalidarla instantáneamente.',
    ])}
    ${this._h('Portal de Auditor (privado por token)')}
    ${this._steps([
      'La URL del auditor incluye un token único que da acceso read-only.',
      'El auditor puede ver: estado por framework, evidencias vinculadas, gaps y requisitos pendientes.',
      'No puede ver datos sensibles (nombres de empleados, contraseñas, configuración interna).',
      'Regenera el token tras cada auditoría para revocar el acceso.',
    ])}
    ${this._warn('Nunca compartas el token de auditor por canales no seguros. Revócalo siempre tras finalizar la auditoría.')}
  `;},

  get _cItsmConfig() { return `
    ${this._p('Las <strong>integraciones ITSM</strong> conectan RiskHub con tus herramientas de gestión de servicios y comunicación para crear tickets y notificaciones automáticamente cuando se detectan riesgos HIGH/CRITICAL.')}
    ${this._h('Integraciones disponibles')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Jira Cloud/Server:</strong> crea issues automáticamente con prioridad basada en el nivel de riesgo.</li>
      <li><strong>ServiceNow:</strong> crea incidents con urgencia e impacto calculados según el nivel residual.</li>
      <li><strong>Slack:</strong> notificaciones en canal con bloques de mensaje estructurados.</li>
      <li><strong>Microsoft Teams:</strong> tarjetas de mensaje adaptativas en canal.</li>
    </ul>
    ${this._h('Configuración')}
    ${this._steps([
      'Ve a Integraciones → ITSM y Notificaciones (requiere rol admin).',
      'Pulsa "Configurar" en la integración deseada e introduce las credenciales.',
      'Usa "Probar conexión" para verificar antes de guardar.',
      'Una vez configurado, RiskHub creará tickets/notificaciones automáticamente cuando un riesgo alcance nivel residual ≥5.',
    ])}
    ${this._warn('Las credenciales se almacenan cifradas con AES-256 (Fernet). Nunca se registran en logs.')}
  `;},

  get _cPredictive() { return `
    ${this._p('El <strong>Análisis Predictivo</strong> analiza la evolución del inventario de riesgos para proyectar tendencias, identificar activos críticos y priorizar qué mejorar para maximizar la postura de seguridad.')}
    ${this._h('Módulos')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Trend de riesgos (90 días):</strong> velocidad de creación, cambio porcentual y forecast a 30 días.</li>
      <li><strong>Camino de madurez:</strong> qué controles implementar primero para mejorar más rápido.</li>
      <li><strong>Activos con mayor riesgo:</strong> activos con más concentración de riesgos altos.</li>
      <li><strong>Forecast de amenazas:</strong> qué amenazas tienen más probabilidad de materializarse basándose en historial.</li>
    </ul>
    ${this._tip('Usa el camino de madurez para priorizar el backlog de controles: los controles parciales tienen el ROI más alto al requerir poco esfuerzo para completarse.')}
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

  get _cExternalFindings() { return `
    ${this._p('Los <strong>Hallazgos Externos</strong> agrupan vulnerabilidades y amenazas detectadas fuera de RiskHub (OSINT, escaneos de terceros, reportes de consultores) y las vinculas automáticamente a tus activos e incidentes.')}
    ${this._h('Casos de uso')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Importar resultados de escaneos Qualys, Nessus o Rapid7 en formato CSV/XML.</li>
      <li>Vincular hallazgos de OSINT a activos específicos.</li>
      <li>Crear incidentes automáticamente cuando se detecte una vulnerabilidad crítica.</li>
      <li>Realizar trazabilidad: qué vulnerabilidades externas impactan cada activo.</li>
    </ul>
    ${this._h('Formato de archivo soportado')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>CSV:</strong> columnas título, descripción, nivel de riesgo, activo afectado.</li>
      <li><strong>XML:</strong> estructura estándar de escáneres de vulnerabilidades.</li>
      <li><strong>JSON:</strong> array de objetos con propiedades de hallazgo.</li>
    </ul>
    ${this._tip('Usa la validación de magic bytes: RiskHub rechaza archivos cuya extensión no coincide con el contenido real para prevenir ataques de carga de archivos maliciosos.')}
  `;},

  get _cWebhooks() { return `
    ${this._p('Los <strong>Webhooks</strong> integran RiskHub con sistemas externos (ERP, ITSM, herramientas de CI/CD) mediante notificaciones en tiempo real. RiskHub puede tanto <em>recibir</em> webhooks (eventos de terceros) como <em>enviar</em> (cuando ocurren cambios en riesgos/incidentes).')}
    ${this._h('Webhooks entrantes (entrada de eventos)')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>ERP (SAP, Jagger, Sphera):</strong> eventos de cambio en activos, usuarios, procesos.</li>
      <li><strong>Seguridad:</strong> alertas de SIEM, detecciones de IDS/IPS.</li>
      <li><strong>Validación HMAC-SHA256:</strong> cada webhook debe incluir firma criptográfica para garantizar que procede del origen esperado.</li>
    </ul>
    ${this._h('Webhooks salientes (notificaciones de RiskHub)')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Riesgo residual sube a nivel alto → notificar a ITSM o Teams.</li>
      <li>Nuevo incidente NIS2 detectado → crear ticket en Jira automáticamente.</li>
      <li>Incidente resuelto → marcar ticket como cerrado.</li>
    </ul>
    ${this._warn('Las credenciales y URLs de webhook se almacenan cifradas (AES-256). Prueba siempre la conexión antes de guardar con el botón "Probar".')}
  `;},

  get _cFeatureFlags() { return `
    ${this._p('Los <strong>Feature Flags</strong> controlan qué módulos de RiskHub están habilitados según el plan de licencia de cada organización. Permite activar/desactivar características sin redeploying.')}
    ${this._h('Planes disponibles')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Free:</strong> Activos, Riesgos, Controles. Hasta 10 usuarios.</li>
      <li><strong>Starter:</strong> Free + Incidentes, Políticas, Tareas, Cumplimiento, Informes.</li>
      <li><strong>Pro:</strong> Starter + Proveedores, No Conformidades, Auditorías, RGPD, IA, CVE, Alertas.</li>
      <li><strong>Enterprise:</strong> Pro + Integraciones avanzadas, SSO/OIDC, consultoría personalizada.</li>
    </ul>
    ${this._h('Gestión de flags')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Superadmin puede establecer flags globales (aplican a todas las orgs) u overrides por organización.</li>
      <li>Admin de organización puede activar módulos permitidos por su plan.</li>
      <li>Los intentos de activar módulos no incluidos en el plan se rechazan automáticamente.</li>
    </ul>
    ${this._tip('Los flags se aplican en tiempo real sin necesidad de reiniciar. Usa el endpoint GET /api/feature-flags/plans/limits para consultar qué módulos incluye cada plan.')}
  `;},

  get _cBcp() { return `
    ${this._p('El modulo de <strong>Continuidad de Negocio (BCP/BIA)</strong> implementa el ciclo completo de gestion de continuidad segun <strong>ISO 22301:2019</strong> (Sistema de Gestion de Continuidad de Negocio) integrado con ISO 27001 A.5.29/A.5.30, ENS op.cont.1/2/3 y NIS2 Art. 21.2(b).')}
    ${this._h('Conceptos clave')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px;">Termino</th><th style="padding:8px;">Definicion</th>
      </tr></thead>
      <tbody>
        ${[
          ['RTO (Recovery Time Objective)','Tiempo maximo tolerable para restaurar un proceso o sistema tras una interrupcion.'],
          ['RPO (Recovery Point Objective)','Cantidad maxima de datos que se puede perder medida en tiempo (antigüedad del ultimo backup valido).'],
          ['MTPD (Max. Tolerable Period of Disruption)','Tiempo maximo absoluto que la organizacion puede sobrevivir sin el proceso.'],
          ['MBCO (Min. Business Continuity Objective)','Nivel minimo de servicio aceptable mientras se recupera el proceso.'],
          ['BIA (Business Impact Analysis)','Analisis que cuantifica el impacto financiero, reputacional, legal y operacional de la interrupcion de cada proceso.'],
          ['Plan BCP','Procedimientos documentados para mantener la continuidad durante una interrupcion.'],
          ['Plan DRP','Plan de Recuperacion ante Desastres: restauracion de sistemas IT tras un evento catastrofico.'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>${r.map(c=>`<td style="padding:8px;">${c}</td>`).join('')}</tr>`).join('')}
      </tbody>
    </table>

    ${this._h('Flujo recomendado ISO 22301')}
    ${this._steps([
      '<strong>Procesos criticos:</strong> Registra los procesos de negocio criticos y sus responsables. Minimo RTO, RPO y MTPD por proceso.',
      '<strong>BIA:</strong> Completa el Analisis de Impacto de Negocio para cada proceso. Un proceso tiene BIA completo cuando rellenas los 10 campos requeridos (RTO, RPO, MTPD, MBCO, 4 impactos, criterios de activacion y registros vitales).',
      '<strong>Dependencias:</strong> Documenta que sistemas IT, personal, instalaciones y proveedores necesita cada proceso para recuperarse.',
      '<strong>Estrategias:</strong> Define al menos una estrategia de recuperacion por proceso critico (hot site, trabajo remoto, procedimiento manual, etc.).',
      '<strong>Planes BCP/DRP:</strong> Crea planes documentados para los procesos. Usa el drawer de 10 secciones para completar roles, contactos, procedimientos, KPIs, autorizadores y documentacion vinculada.',
      '<strong>Tests y ejercicios:</strong> Programa tests periodicos (tabletop, simulacion o test completo). Registra resultados y lecciones aprendidas.',
      '<strong>Proveedores BCM:</strong> Vincula proveedores criticos al BCP, define su impacto en RTO y documenta planes de contingencia.',
    ])}

    ${this._h('Tab Resumen (Overview)')}
    ${this._p('Muestra el estado global del SGCN con 23 clausulas ISO 22301:2019. Cada clausula tiene estado <em>implementado / parcial / gap</em>, detalle y referencia normativa. El porcentaje global indica madurez del sistema. Usa el boton <strong>Analizar gaps con IA</strong> para obtener un informe ejecutivo con referencias a ISO 22301, ISO 27001 A.5.29/A.5.30, ENS y NIS2.')}
    ${this._warn('<strong>Atencion:</strong> El boton "Analizar con IA" consume tokens de la API de Claude. Solo usarlo manualmente cuando necesites el informe de auditor.')}

    ${this._h('Tab Procesos Criticos')}
    ${this._p('Tabla de todos los procesos con criticidad, RTO/RPO/MTPD, % BIA completado y conteo de dependencias. Usa el buscador y el filtro de criticidad para navegar en organizaciones con muchos procesos. Haz clic en <strong>Editar</strong> para abrir el formulario completo con 6 secciones:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Informacion basica:</strong> nombre, descripcion, criticidad, responsables (select de usuarios reales, no IDs).</li>
      <li><strong>Objetivos de recuperacion:</strong> RTO, RPO, MTPD, staff minimo, MBCO.</li>
      <li><strong>Evaluacion de impacto:</strong> 4 dimensiones de impacto (financiero, reputacional, legal, operacional) con escala 0-3.</li>
      <li><strong>Activacion y procedimientos:</strong> criterios de activacion y procedimiento alternativo (obligatorios para BIA completo).</li>
      <li><strong>Recursos y documentacion:</strong> registros vitales, sistemas IT e instalaciones (un elemento por linea, se guardan como array).</li>
    </ul>

    ${this._h('Tab BIA (Analisis de Impacto)')}
    ${this._p('Vista de tarjetas con el estado BIA de cada proceso: metricas RTO/RPO/MTPD/MBCO, badges de impacto por dimension y barra de completitud. El color indica estado: verde >= 80%, naranja >= 50%, rojo < 50%. Un proceso con BIA >= 80% contribuye al cumplimiento de ISO 22301 cl. 8.2 y ENS op.cont.1.')}
    ${this._tip('Para facilitar la auditoria, ISO 22301 cl. 8.2 requiere que al menos el 80% de los procesos criticos (criticidad "critica" o "alta") tengan BIA completo.')}

    ${this._h('Tab Dependencias')}
    ${this._p('Dividido en dos secciones:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Dependencias entre procesos:</strong> relaciones proceso-a-proceso. "El proceso A no puede recuperarse hasta que el proceso B este operativo." Define secuencia de recuperacion y motivo.</li>
      <li><strong>Recursos y dependencias externas:</strong> sistemas IT, personal, instalaciones, proveedores, suministros. Define cantidades en operacion normal y en recuperacion, RTO necesario y si es critico (sin el, la recuperacion no puede comenzar).</li>
    </ul>
    ${this._p('Cada dependencia de recurso puede incluir campos de <strong>interconexion tecnica</strong> (seccion colapsable en el formulario):')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Tipo de conexion:</strong> API, database, network, file_transfer, manual, messaging.</li>
      <li><strong>Protocolo:</strong> HTTPS, SQL, SMB, SFTP, AMQP, etc.</li>
      <li><strong>Direccion del flujo:</strong> entrada, salida o bidireccional.</li>
      <li><strong>Clasificacion del dato:</strong> publico, interno, confidencial, estrictamente confidencial.</li>
    </ul>
    ${this._tip('Los campos de interconexion tecnica enriquecen el mapa de dependencias: las aristas del grafo muestran el tipo de conexion como etiqueta y la clasificacion del dato afecta el color de la arista.')}

    ${this._h('Tab Estrategias (ISO 22301 cl. 8.3)')}
    ${this._p('Una estrategia define como se recuperara un proceso. Tipos disponibles: hot site, cold site, warm site, trabajo remoto, outsourcing, procedimiento manual, dual site, cloud failover. Asigna una estrategia global o vinculada a un proceso especifico. Seguimiento del estado: planificado, en progreso, implementado, probado.')}
    ${this._p('Cada estrategia puede incluir dos secciones colapsables con informacion tecnica detallada:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Configuracion tecnica IT (ISO 22301 §8.4):</strong> disponibilidad objetivo (%), tipo de failover (none/active-passive/active-active), compute (vCPUs, RAM, almacenamiento TB), virtualizacion, hosts minimos, RPO y RTO de backup, retencion de backup y ubicacion offsite.</li>
      <li><strong>Monitorizacion y mantenimiento:</strong> herramienta de monitorizacion, umbrales de alerta CPU/memoria, email de alertas, ventana de mantenimiento y cadencia de aplicacion de parches (seguridad y funcionalidad).</li>
    </ul>

    ${this._h('Tab Planes BCP/DRP (ISO 22301 cl. 8.4)')}
    ${this._p('Formulario en drawer lateral con 10 secciones. Solo aparecen las secciones relevantes segun el tipo de plan:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Cabecera:</strong> tipo, version, clasificacion (confidencial/interno/restringido), propietario, procesos cubiertos.</li>
      <li><strong>Alcance y objetivos:</strong> alcance, criterios de activacion, resumen ejecutivo.</li>
      <li><strong>RTO/RPO por sistema</strong> (solo DRP/CRP): tabla editable con sistemas, objetivos y responsable.</li>
      <li><strong>Procedimientos</strong> (solo DRP/CRP/Cyber): notificacion, activacion, recuperacion tecnica, reconstitucion.</li>
      <li><strong>Roles y responsabilidades:</strong> tabla editable. Boton "Plantilla DRP" precarga roles estandar.</li>
      <li><strong>Contactos y escalada:</strong> lista de contactos con backup.</li>
      <li><strong>Contingencia IT y workarounds:</strong> procedimientos manuales y recuperacion de datos.</li>
      <li><strong>KPIs:</strong> tabla editable. Boton "KPIs estandar DRP" precarga metricas recomendadas.</li>
      <li><strong>Clasificacion y gestion:</strong> tipo de instalacion (cloud SaaS/IaaS, on-premise, hibrido), nivel de clasificacion del dato, flag GDPR, usuarios afectados estimados, autorizadores de activacion (tabla editable con suplentes), enlaces externos a documentacion y documentos internos relacionados con version y fecha de vigencia.</li>
      <li><strong>Historial:</strong> datos de aprobacion y tests vinculados.</li>
    </ul>
    ${this._tip('Para aprobar un plan, haz clic en el boton "Aprobar" de la tabla. Aparece un dialogo de confirmacion. Solo los administradores pueden aprobar planes. Al aprobar, se actualiza automaticamente el estado ISO 27001 A.5.29 y ENS op.cont.2.')}

    ${this._h('Menu de acciones del plan')}
    ${this._p('Cada fila de la tabla de planes tiene un boton de menu contextual (icono tres puntos) con las siguientes acciones:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Editar plan:</strong> abre el drawer de edicion.</li>
      <li><strong>Aprobar:</strong> visible solo si el plan esta en estado borrador o revision.</li>
      <li><strong>Activar plan:</strong> acceso directo al dialogo de activacion de emergencia con el plan preseleccionado.</li>
      <li><strong>Mensaje a stakeholders:</strong> abre un modal para redactar y revisar un comunicado de crisis usando las plantillas configuradas en el plan (interna / externa). El mensaje se confirma manualmente — no se envia automaticamente.</li>
      <li><strong>Programar test:</strong> abre el modal de nuevo test con el plan asociado.</li>
      <li><strong>Ver contexto completo:</strong> panel consolidado con todos los procesos cubiertos (RTO/RPO/MTPD/coste/proveedores/dependencias criticas), runbooks asociados y sede DR. Incluye boton de activacion directa.</li>
      <li><strong>Historial activaciones:</strong> tabla de todas las activaciones vinculadas a este plan, con RTO real, duracion y acceso al detalle de cada activacion (timeline de eventos, checklist ejecutado, lecciones aprendidas).</li>
    </ul>

    ${this._h('Tab Tests y Ejercicios (ISO 22301 cl. 8.5)')}
    ${this._p('Programa y registra los ejercicios de continuidad. Tres tipos disponibles:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Tabletop exercise:</strong> discusion teorica del escenario con el equipo.</li>
      <li><strong>Simulacion:</strong> ejercicio parcial sin afectar sistemas de produccion.</li>
      <li><strong>Full test:</strong> prueba completa del plan en condiciones reales.</li>
    </ul>
    ${this._p('Al crear un test puedes asociarlo a un plan BCP/DRP especifico. Tras guardar, el sistema ofrece generar un checklist detallado con IA.')}
    ${this._p('Al registrar el resultado, los campos <em>hallazgos</em> y <em>lecciones aprendidas</em> son obligatorios si el resultado es parcial o fallido. Si el test falla, el sistema ofrece crear una No Conformidad automaticamente (ISO 22301 cl. 10.1).')}
    ${this._tip('Un "full test" en los ultimos 12 meses cuenta como evidencia para la clausula 9.2 (auditoria interna del SGCN). Los tests superados actualizan ISO 27001 A.5.30 y ENS op.cont.3.')}

    ${this._h('Checklist de test generado por IA')}
    ${this._p('Cada test tiene un boton <em>sparkles</em> que llama al modelo de IA configurado en el sistema para generar un checklist estructurado en tres fases:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Pre-test:</strong> lista de verificacion antes de iniciar el ejercicio (convocatoria, accesos, comunicacion a usuarios).</li>
      <li><strong>Pasos del test:</strong> secuencia ordenada de acciones con proceso asociado y RTO esperado por paso.</li>
      <li><strong>Post-test:</strong> cierre, validacion de criterios de exito y comunicacion de resultados.</li>
    </ul>
    ${this._p('El resultado incluye ademas una lista de notificacion (rol, momento, canal). Puedes copiar el checklist completo en JSON para usarlo en otras herramientas.')}
    ${this._warn('El checklist IA consume tokens de la API de Claude. Requiere que la API key este configurada en Ajustes > Agente IA.')}

    ${this._h('Mapa de dependencias (grafo interactivo)')}
    ${this._p('Vista de grafo interactivo Cytoscape que muestra todos los procesos, activos IT y proveedores externos como nodos conectados por aristas tipadas. Accesible desde la pestana Dependencias.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Nodos proceso (elipse morada):</strong> tamano proporcional a criticidad. Muestra RTO/RPO/MTPD, coste por hora y planes asociados al hacer clic.</li>
      <li><strong>Nodos activo IT (rectangulo naranja):</strong> activos vinculados a procesos via asset_ids o dependencias.</li>
      <li><strong>Nodos proveedor (hexagono verde):</strong> proveedores vinculados via supplier_ids o Proveedores BCM. Muestra SLA contractual, RTO de impacto y si tiene plan de contingencia.</li>
      <li><strong>SPOF (Single Point of Failure):</strong> nodos con 3 o mas dependencias entrantes se marcan con borde rojo doble. Son los puntos de mayor riesgo de fallo en cascada.</li>
    </ul>
    ${this._p('Controles disponibles en la barra de herramientas:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Filtro por sede (location) para ver solo los procesos de una ubicacion.</li>
      <li>Zoom +/- y ajuste automatico al grafo completo.</li>
      <li>Exportar como PNG.</li>
      <li>Mostrar/ocultar etiquetas en las aristas (tipo de conexion, protocolo).</li>
      <li>Filtro "solo criticos" para reducir el ruido visual.</li>
      <li>Analizar con IA: envia el resumen del grafo al modelo configurado y devuelve un informe con SPOFs priorizados, cadena critica de recuperacion y 3 acciones recomendadas con referencia a clausulas ISO 22301.</li>
    </ul>
    ${this._tip('Los proveedores vinculados en "Proveedores BCM" aparecen conectados a los procesos que soportan. Si un proveedor no aparece en el mapa, verifica que tenga procesos asociados en la pestaña Proveedores BCM.')}

    ${this._h('Tab Runbooks de recuperacion (ISO 22301 §8.4.3)')}
    ${this._p('Los runbooks son los procedimientos operativos ejecutables durante una activacion. A diferencia de los planes (estrategicos), los runbooks son tacticos: paso a paso, con responsable asignado.')}
    ${this._p('Campos disponibles en el formulario:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Tipo:</strong> Recuperacion, Failover o General.</li>
      <li><strong>Plan BCP/DRP asociado:</strong> vincula el runbook a un plan para que aparezca en el contexto consolidado del plan.</li>
      <li><strong>Condicion de activacion:</strong> criterio formal para iniciar este runbook (ej. "servidor principal inaccesible >15 min").</li>
      <li><strong>Responsable titular / Suplente:</strong> nombre y cargo del responsable de ejecucion.</li>
      <li><strong>Referencia boveda de credenciales:</strong> ruta o referencia al almacen seguro de credenciales necesarias.</li>
      <li><strong>Criterio de exito:</strong> prueba objetiva de que la recuperacion fue exitosa.</li>
    </ul>
    ${this._p('Al seleccionar tipo <strong>Recuperacion</strong>, aparece el boton <em>"Plantilla 5 fases"</em> que precarga la descripcion con la estructura estandar ISO 22301:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Fase 1 — Deteccion y notificacion:</strong> alertas, confirmacion de alcance, apertura del registro.</li>
      <li><strong>Fase 2 — Activacion del plan:</strong> declaracion formal, convocatoria de equipo, comunicacion inicial.</li>
      <li><strong>Fase 3 — Recuperacion tecnica:</strong> ejecucion en orden de dependencias, restauracion de backups, activacion DR Site.</li>
      <li><strong>Fase 4 — Reconstitucion y validacion:</strong> pruebas funcionales, verificacion del criterio de exito, comunicacion de reanudacion.</li>
      <li><strong>Fase 5 — Cierre y revision post-incidente:</strong> declaracion formal de cierre, registro de RTO real, lecciones aprendidas.</li>
    </ul>

    ${this._h('Activacion de planes de continuidad')}
    ${this._p('El boton rojo "Activar BCP/DRP" o la accion "Activar plan" del menu contextual abre el dialogo de activacion de emergencia. Solo debe usarse ante un incidente real.')}
    ${this._p('Al seleccionar un plan, el sistema carga automaticamente el contexto:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Canales de comunicacion</strong> configurados en el plan (primario, secundario, externo).</li>
      <li><strong>Proveedores criticos afectados</strong> por los procesos cubiertos.</li>
      <li><strong>Autorizadores</strong> definidos en la seccion de clasificacion del plan.</li>
      <li>Si el plan tiene plantilla de comunicado interno, se precarga en el campo de notas iniciales.</li>
    </ul>
    ${this._p('La activacion registra una marca temporal T=0 automaticamente. Una vez confirmada, el sistema abre el checklist de activacion donde cada paso puede marcarse como completado, con hora de ejecucion registrada.')}
    ${this._warn('Solo los usuarios con rol Analyst o Admin pueden activar planes. Una activacion no puede deshacerse — solo cerrarse mediante "Cerrar activacion" con RTO real y lecciones aprendidas.')}

    ${this._h('Historial de activaciones')}
    ${this._p('Accesible desde "Historial activaciones" en el menu contextual de cada plan. Muestra todas las activaciones vinculadas a ese plan con:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li>Codigo de activacion, titulo del incidente, fechas de inicio y cierre.</li>
      <li>RTO real (duracion total de la activacion).</li>
      <li>Estado: activa o cerrada.</li>
      <li>Acceso al detalle: timeline completo de eventos, checklist con estado de cada paso y hora de ejecucion, lecciones aprendidas registradas.</li>
    </ul>

    ${this._h('Tab Proveedores BCM (ISO 22301 cl. 8.2)')}
    ${this._p('Vincula proveedores criticos al programa de continuidad. Para cada vinculo, define: criticidad BCM, RTO de impacto si el proveedor falla, SLA contractual, proveedor alternativo y si tiene plan de contingencia. Asocia los procesos que dependen del proveedor para tener visibilidad cruzada.')}
    ${this._warn('Si el proveedor tiene plan de contingencia documentado, se actualiza automaticamente el estado de ISO 27001 A.5.19 y NIS2 Art.21.2(c) en el modulo de cumplimiento.')}

    ${this._h('Tab Importar / Exportar')}
    ${this._p('Dos modos de importacion Excel:')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Plantilla estandar:</strong> usa la plantilla descargable con las columnas exactas que espera el sistema. Valida la estructura antes de importar y muestra una vista previa.</li>
      <li><strong>Cualquier formato (IA):</strong> sube un Excel propio. Claude analizara la estructura, identificara las columnas BCP aunque no coincidan exactamente, y mapeara los datos. Ideal para importar BIAs existentes o datos de otras herramientas.</li>
    </ul>
    ${this._p('La exportacion genera un Excel con 5 hojas: procesos, dependencias, estrategias, planes y tests.')}

    ${this._h('Integraciones automaticas (sin IA)')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Activo critico sin BCP:</strong> cuando se crea un activo con valor CIA >= 3 y no esta vinculado a ningun proceso BCP, el sistema crea un proceso BCP draft de sugerencia.</li>
      <li><strong>Riesgo critico sin cobertura:</strong> cuando un riesgo alcanza nivel residual >= 6 y su activo no tiene proceso BCP, se activa la misma sugerencia.</li>
      <li><strong>Incidente P1/P2:</strong> si un incidente grave afecta activos de un proceso BCP critico, el sistema anota una alerta de activacion potencial en los contactos de escalada del proceso.</li>
      <li><strong>CVE en activo BCP:</strong> si un CVE afecta un activo de un proceso BCP critico, se anota en los registros vitales del proceso para revision.</li>
      <li><strong>Cobertura BCP en riesgos:</strong> el scheduler mensual calcula que riesgos tienen cobertura de un plan BCP aprobado y muestra un badge verde en el registro de riesgos.</li>
    </ul>

    ${this._h('Cumplimiento normativo automatico')}
    ${this._p('Los eventos BCP actualizan automaticamente el estado en el modulo de cumplimiento:')}
    <table style="width:100%;border-collapse:collapse;font-size:12px;margin-bottom:14px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:6px 8px;">Evento BCP</th>
        <th style="padding:6px 8px;">Normativa actualizada</th>
      </tr></thead>
      <tbody>
        ${[
          ['BIA >= 80% en proceso critico','ISO 27001 A.5.29 (partial) · ENS op.cont.1 (partial)'],
          ['Plan BCP aprobado','ISO 27001 A.5.29 (implemented) · ENS op.cont.2 · NIS2 Art.21.2(b)'],
          ['Plan DRP/CRP aprobado','ISO 27001 A.5.29 + A.5.30 (partial) · ENS op.cont.2 · NIS2 Art.21.2(b)'],
          ['Test superado (passed)','ISO 27001 A.5.30 (implemented) · ENS op.cont.3 · NIS2 Art.21.2(b)'],
          ['Estrategia creada','ISO 27001 A.5.29 (partial) · ENS op.cont.1 (partial)'],
          ['Proveedor con plan contingencia','ISO 27001 A.5.19 (partial) · NIS2 Art.21.2(c)'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>${r.map(c=>`<td style="padding:6px 8px;">${c}</td>`).join('')}</tr>`).join('')}
      </tbody>
    </table>
    ${this._tip('Para ver el estado de cumplimiento detallado, ve a <em>Cumplimiento</em> en el menu lateral y selecciona los frameworks ISO 27001, ENS o NIS2.')}
    <h3>Activación de crisis (v5.5)</h3>
    <p>Para activar un plan BCP durante una contingencia real: Hub BCP &gt; Plan &gt; "Activar plan de crisis".</p>
    <ul>
      <li>El plan queda en estado <strong>ACTIVADO</strong> (rojo)</li>
      <li>Los riesgos vinculados al plan reducen su <code>residual_likelihood</code> en −1 automáticamente</li>
      <li>Se registra en el log con timestamp y usuario</li>
    </ul>
    <p>Para vincular riesgos: editar el plan &gt; sección "Riesgos vinculados".</p>
    <p>Al desactivar (crisis resuelta), el plan vuelve a <strong>standby</strong> y se registra la resolución.</p>
    <h4>Tests BCP y bucle cerrado</h4>
    <ul>
      <li>Sin test en &gt;12 meses → alerta automática del scheduler (ISO 22301 §8.5)</li>
      <li>Test fallido → NonConformidad automática (severity MAJOR)</li>
      <li>Siguiente test aprobado → NC se cierra automáticamente</li>
    </ul>
    <h4>Vinculación NIS2</h4>
    <p>Si el tipo del plan es <code>cyber_response</code> o <code>cyber_recovery</code> y se aprueba, el sistema actualiza automáticamente el estado del control NIS2 Art.21(2)(c) a "Implementado".</p>
  `;},

  get _cSetup() { return `
    <div style="background:linear-gradient(135deg,var(--brand-purple-4),var(--brand-orange-4));border-radius:12px;padding:20px 24px;margin-bottom:20px;">
      <div style="font-size:16px;font-weight:700;color:var(--brand-purple);margin-bottom:6px;">Guia de instalacion y primera configuracion</div>
      <p style="margin:0;font-size:13px;line-height:1.6;color:var(--text-base);">
        Esta seccion explica como acceder a RiskHub por primera vez, como desplegarlo en un servidor propio y como completar la configuracion inicial para empezar a trabajar. Tiempo estimado: <strong>20-30 minutos</strong>.
      </p>
    </div>

    ${this._h('Modalidad A — Instancia gestionada (acceso inmediato)')}
    ${this._p('En esta modalidad, RiskHub corre en un servidor gestionado. El cliente no instala nada: recibe un email con la URL de acceso, el usuario admin y una contrasena temporal.')}
    ${this._steps([
      'Abre el email de bienvenida. Contiene: <strong>URL de acceso</strong>, <strong>usuario admin</strong> (tu email) y <strong>contrasena temporal</strong>.',
      'Abre la URL en tu navegador. Funciona en Chrome, Firefox, Edge y Safari actualizados.',
      'Introduce el email y la contrasena temporal. Haz clic en <strong>Iniciar sesion</strong>.',
      'El sistema te pedira que cambies la contrasena en el primer acceso. Elige una contrasena segura (minimo 12 caracteres, con numeros y simbolos).',
      'Seras redirigido al <strong>Dashboard principal</strong>. La instalacion esta completa — continua en el apartado <em>Configuracion inicial obligatoria</em> de esta misma pagina.',
    ])}
    ${this._tip('<strong>Si no recibes el email:</strong> revisa la carpeta de spam. El remitente es noreply@riskhub.io. Si el problema persiste, contacta con el administrador de la plataforma.')}

    ${this._h('Modalidad B — Servidor propio (on-premise con Docker)')}
    ${this._p('En esta modalidad, RiskHub se instala en un servidor bajo control del cliente. Se necesita acceso root al servidor y Docker instalado. El proceso completo tarda menos de 15 minutos.')}

    <div style="background:var(--bg-2);border-radius:8px;padding:16px;margin-bottom:16px;">
      <div style="font-weight:700;font-size:13px;color:var(--brand-purple);margin-bottom:10px;">Requisitos del servidor</div>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <tbody>
          ${[
            ['Sistema operativo','Ubuntu 22.04 LTS o 24.04 LTS (recomendado). Debian 12 tambien es compatible.'],
            ['CPU','Minimo 2 vCPU. Recomendado: 4 vCPU para entornos con IA activa.'],
            ['RAM','Minimo 4 GB. Recomendado: 8 GB si se usa el Agente IA con muchos documentos.'],
            ['Disco','Minimo 20 GB SSD. Recomendado: 40 GB para almacenamiento de documentos del Agente IA.'],
            ['Red','Puerto 80 (HTTP) y/o 443 (HTTPS) accesible desde los usuarios. Puerto 22 para SSH (administracion).'],
            ['Software','Docker Engine 24+ y Docker Compose v2. Se instalan en el paso 2.'],
          ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-3,var(--bg-2));"':''}>
            <td style="padding:7px 10px;font-weight:600;width:180px;">${r[0]}</td>
            <td style="padding:7px 10px;color:var(--text-muted);">${r[1]}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>

    <div style="font-weight:700;font-size:13px;color:var(--brand-purple);margin:16px 0 8px;text-transform:uppercase;letter-spacing:.5px;">Paso 1 — Conectarse al servidor</div>
    ${this._p('Desde tu ordenador, abre una terminal (Windows: PowerShell o cmd; Mac/Linux: Terminal) y conéctate al servidor:')}
    <div style="background:#1e1e2e;color:#cdd6f4;border-radius:8px;padding:14px 16px;font-family:monospace;font-size:13px;margin-bottom:12px;line-height:1.8;">
      ssh root@IP_DEL_SERVIDOR
    </div>
    ${this._p('Sustituye <code>IP_DEL_SERVIDOR</code> por la IP publica de tu servidor. Si usas clave SSH en lugar de contrasena, añade <code>-i ruta/a/tu/clave.pem</code>.')}

    <div style="font-weight:700;font-size:13px;color:var(--brand-purple);margin:16px 0 8px;text-transform:uppercase;letter-spacing:.5px;">Paso 2 — Instalar Docker (si no esta instalado)</div>
    ${this._p('Ejecuta estos comandos uno a uno en el servidor. Cada uno puede tardar 1-2 minutos:')}
    <div style="background:#1e1e2e;color:#cdd6f4;border-radius:8px;padding:14px 16px;font-family:monospace;font-size:12px;margin-bottom:12px;line-height:2;">
      curl -fsSL https://get.docker.com | sh<br>
      systemctl enable docker<br>
      systemctl start docker
    </div>
    ${this._p('Verifica que Docker esta funcionando:')}
    <div style="background:#1e1e2e;color:#cdd6f4;border-radius:8px;padding:14px 16px;font-family:monospace;font-size:13px;margin-bottom:12px;">
      docker --version
    </div>

    <div style="font-weight:700;font-size:13px;color:var(--brand-purple);margin:16px 0 8px;text-transform:uppercase;letter-spacing:.5px;">Paso 3 — Crear la carpeta de la aplicacion</div>
    <div style="background:#1e1e2e;color:#cdd6f4;border-radius:8px;padding:14px 16px;font-family:monospace;font-size:13px;margin-bottom:12px;line-height:2;">
      mkdir -p /opt/riskhub<br>
      cd /opt/riskhub
    </div>

    <div style="font-weight:700;font-size:13px;color:var(--brand-purple);margin:16px 0 8px;text-transform:uppercase;letter-spacing:.5px;">Paso 4 — Crear el archivo de configuracion (.env)</div>
    ${this._p('Crea el archivo <code>.env</code> con la configuracion de tu instalacion. Todos los campos son importantes:')}
    <div style="background:#1e1e2e;color:#cdd6f4;border-radius:8px;padding:14px 16px;font-family:monospace;font-size:12px;margin-bottom:4px;line-height:2;">
      <span style="color:#89b4fa;"># Clave secreta — genera una unica con el comando de abajo</span><br>
      RISKHUB_SECRET_KEY=<span style="color:#f38ba8;">PON_AQUI_UNA_CLAVE_DE_64_CARACTERES_ALEATORIA</span><br><br>
      <span style="color:#89b4fa;"># Entorno de produccion (no cambiar)</span><br>
      RISKHUB_ENV=production<br><br>
      <span style="color:#89b4fa;"># API key del Agente IA (opcional pero muy recomendado)</span><br>
      RISKHUB_ANTHROPIC_API_KEY=<span style="color:#f38ba8;">sk-ant-xxxx (obtener en console.anthropic.com)</span>
    </div>
    <div style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">Para generar la clave secreta ejecuta: <code style="background:var(--bg-2);padding:2px 6px;border-radius:4px;">python3 -c "import secrets; print(secrets.token_urlsafe(64))"</code></div>

    <div style="font-weight:700;font-size:13px;color:var(--brand-purple);margin:16px 0 8px;text-transform:uppercase;letter-spacing:.5px;">Paso 5 — Descargar y arrancar RiskHub</div>
    ${this._p('Descarga los archivos de despliegue del repositorio y arranca los contenedores:')}
    <div style="background:#1e1e2e;color:#cdd6f4;border-radius:8px;padding:14px 16px;font-family:monospace;font-size:12px;margin-bottom:12px;line-height:2;">
      <span style="color:#89b4fa;"># Clonar el repositorio</span><br>
      git clone https://github.com/ezequielwolf22/riskhub.git .<br><br>
      <span style="color:#89b4fa;"># Arrancar la aplicacion</span><br>
      docker compose up -d<br><br>
      <span style="color:#89b4fa;"># Ver que los contenedores estan corriendo</span><br>
      docker compose ps
    </div>
    ${this._p('El primer arranque tarda 2-3 minutos porque descarga las imagenes Docker y crea la base de datos. Cuando veas <code>healthy</code> en el estado, la aplicacion esta lista.')}

    <div style="font-weight:700;font-size:13px;color:var(--brand-purple);margin:16px 0 8px;text-transform:uppercase;letter-spacing:.5px;">Paso 6 — Primer acceso</div>
    ${this._p('Abre el navegador en <code>http://IP_DEL_SERVIDOR</code>. Aparecera la pantalla de login de RiskHub.')}
    <div style="background:var(--bg-2);border-radius:8px;padding:14px 16px;margin-bottom:12px;font-size:13px;">
      <div style="font-weight:700;margin-bottom:8px;">Credenciales del administrador por defecto:</div>
      <div><strong>Email:</strong> <code>admin@riskhub.local</code></div>
      <div><strong>Contrasena:</strong> <code>RiskHub2024!</code></div>
    </div>
    ${this._warn('<strong>Cambia la contrasena inmediatamente</strong> tras el primer acceso. Haz clic en tu nombre (esquina superior derecha) y selecciona "Cambiar contrasena". La contrasena por defecto es publica y conocida — no la dejes activa en produccion.')}

    ${this._h('Configuracion inicial obligatoria (primeros 30 minutos)')}
    ${this._p('Una vez dentro de RiskHub, sigue esta lista en orden para dejar la plataforma lista para trabajar:')}

    <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:20px;">
      ${[
        ['Cambiar la contrasena del admin','Nombre de usuario (arriba derecha) → Cambiar contrasena. Elige una contrasena de al menos 12 caracteres.','Obligatorio'],
        ['Configurar el contexto organizacional','Menu lateral → Contexto. Rellena: nombre de tu organizacion, alcance del SGSI (que sistemas y areas cubre) y apetito de riesgo. Estos datos se usan en todos los informes y calculos.','Obligatorio'],
        ['Crear usuarios adicionales','Menu lateral → Usuarios → Nuevo usuario. Crea al menos un analista (rol analyst). Asigna roles segun responsabilidades.','Recomendado'],
        ['Configurar el servidor de email (SMTP)','Menu lateral → Alertas → Configuracion SMTP. Sin esto, las alertas automaticas no llegan. Gmail, Microsoft 365 y Exchange on-premise son compatibles.','Recomendado'],
        ['Configurar el Agente IA','Menu lateral → Agente IA → Configuracion. Introduce tu API key de Anthropic. Sin esto, los analisis automaticos de activos, los informes con IA y el chat GRC no funcionan.','Recomendado'],
        ['Activar los frameworks de cumplimiento','Menu lateral → Cumplimiento → Configurar. Selecciona los marcos que aplican a tu organizacion (ISO 27001, NIS2, ENS, GDPR...).','Recomendado'],
        ['Importar o crear activos','Menu lateral → Activos. Puedes importar desde CSV (boton Importar) o crear activos uno a uno. Con el Agente IA configurado, el analisis de riesgos arranca automaticamente.','Siguiente paso'],
        ['Configurar niveles de riesgo personalizados','Menu lateral → Contexto → Niveles de riesgo. Personaliza los rangos y colores de los niveles de riesgo para que coincidan con tu politica interna.','Opcional'],
      ].map(([t,d,badge]) => {
        const bcolor = badge==='Obligatorio'?'var(--risk-high)':badge==='Recomendado'?'var(--brand-orange)':'var(--brand-purple)';
        return `<div style="display:flex;gap:12px;align-items:flex-start;background:var(--bg-2);border-radius:8px;padding:12px 14px;">
          <span style="background:${bcolor};color:#fff;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700;white-space:nowrap;margin-top:2px;">${badge}</span>
          <div>
            <div style="font-weight:700;font-size:13px;margin-bottom:3px;">${t}</div>
            <div style="font-size:12px;color:var(--text-muted);line-height:1.5;">${d}</div>
          </div>
        </div>`;
      }).join('')}
    </div>

    ${this._h('Actualizacion a una nueva version')}
    ${this._p('Para actualizar RiskHub a la ultima version, ejecuta en el servidor:')}
    <div style="background:#1e1e2e;color:#cdd6f4;border-radius:8px;padding:14px 16px;font-family:monospace;font-size:13px;margin-bottom:12px;line-height:2;">
      bash /opt/riskhub/deploy.sh
    </div>
    ${this._p('El script realiza automaticamente: <code>git pull</code> (descarga los cambios), reconstruye la imagen Docker y reinicia los contenedores. La base de datos y todos los datos se preservan en el volumen Docker <code>riskhub-data</code>. El proceso tarda 2-4 minutos.')}
    ${this._warn('<strong>No es necesario parar la aplicacion antes de actualizar.</strong> El script gestiona el reinicio sin perdida de datos. Aun asi, se recomienda hacer un backup antes de cualquier actualizacion importante.')}

    ${this._h('Backup y recuperacion')}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
      <div style="background:var(--bg-2);border-radius:8px;padding:14px;">
        <div style="font-weight:700;font-size:13px;color:var(--brand-purple);margin-bottom:8px;">Backup desde la interfaz (recomendado)</div>
        <div style="font-size:13px;line-height:1.6;">Ve a <strong>Usuarios</strong> → panel <em>Informacion del sistema</em> → boton <strong>Descargar backup DB</strong>. Se descarga un archivo <code>.db</code> con fecha y hora. Guardalo fuera del servidor.</div>
      </div>
      <div style="background:var(--bg-2);border-radius:8px;padding:14px;">
        <div style="font-weight:700;font-size:13px;color:var(--brand-purple);margin-bottom:8px;">Backup desde el servidor</div>
        <div style="font-size:13px;line-height:1.6;">Ejecuta en el servidor:<br><code style="font-size:11px;background:var(--bg-3,var(--bg-2));padding:3px 6px;border-radius:4px;display:block;margin-top:6px;">docker cp riskhub:/app/data/riskhub.db ./backup_$(date +%Y%m%d).db</code></div>
      </div>
    </div>
    ${this._p('Para restaurar un backup: copia el archivo <code>.db</code> al servidor, para los contenedores (<code>docker compose down</code>), reemplaza el archivo de base de datos en el volumen y vuelve a arrancar (<code>docker compose up -d</code>).')}
    ${this._tip('<strong>Automatiza el backup:</strong> configura un cron job en el servidor para ejecutar el backup diariamente y enviar el archivo a un almacenamiento externo (S3, Azure Blob, Google Drive). El backup incluye todos los datos de RiskHub pero NO los documentos del Agente IA (estos se almacenan en el sistema de archivos del volumen Docker).')}

    ${this._h('Acceso HTTPS (produccion)')}
    ${this._p('Por defecto, RiskHub corre en HTTP (puerto 80). Para produccion real, se recomienda activar HTTPS con un certificado TLS. La forma mas sencilla es usar nginx como proxy inverso con Let\'s Encrypt (certificado gratuito):')}
    <div style="background:#1e1e2e;color:#cdd6f4;border-radius:8px;padding:14px 16px;font-family:monospace;font-size:12px;margin-bottom:12px;line-height:2;">
      <span style="color:#89b4fa;"># Instalar nginx y certbot</span><br>
      apt install -y nginx certbot python3-certbot-nginx<br><br>
      <span style="color:#89b4fa;"># Obtener certificado TLS (sustituye tu-dominio.com)</span><br>
      certbot --nginx -d tu-dominio.com
    </div>
    ${this._p('Certbot configura automaticamente nginx para redirigir HTTP a HTTPS y renovar el certificado cada 90 dias. RiskHub activa automaticamente la cabecera <code>Strict-Transport-Security (HSTS)</code> cuando detecta que corre detras de un proxy HTTPS.')}
    ${this._warn('<strong>Si el cliente no tiene dominio propio</strong> puedes usar la IP directa con HTTP para uso interno (dentro de la red corporativa o via VPN). Solo es imprescindible HTTPS si la aplicacion es accesible desde internet.')}

    ${this._h('Verificar que todo funciona')}
    ${this._p('Despues de la instalacion y configuracion inicial, verifica estos puntos:')}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
      ${[
        ['Login funciona','Puedes entrar con tu usuario y la nueva contrasena.'],
        ['Dashboard carga','El dashboard muestra KPIs (aunque esten a cero si aun no hay datos).'],
        ['Email de prueba','Alertas → Configuracion SMTP → boton Enviar email de prueba. Llega el email.'],
        ['Agente IA responde','Agente IA → Chat → escribe "Hola". El agente responde (requiere API key valida).'],
        ['Backup descargable','Usuarios → Informacion del sistema → Descargar backup DB. Se descarga el archivo.'],
        ['Log de auditoria','Auditoria → aparecen los eventos de login y configuracion realizados.'],
      ].map(([t,d]) => `
        <div style="background:var(--bg-2);border-radius:8px;padding:10px 14px;display:flex;gap:10px;align-items:flex-start;">
          <span style="color:var(--risk-low);font-size:16px;flex-shrink:0;">&#10003;</span>
          <div>
            <div style="font-weight:700;font-size:13px;">${t}</div>
            <div style="font-size:12px;color:var(--text-muted);margin-top:2px;">${d}</div>
          </div>
        </div>`).join('')}
    </div>
    ${this._tip('<strong>Problema frecuente:</strong> si la aplicacion no responde despues del arranque, ejecuta <code>docker compose logs -f</code> en el servidor para ver los mensajes de error. Los problemas mas comunes son: puerto 80 ocupado por otro servicio (usa <code>ss -tlnp | grep :80</code> para comprobarlo) o falta de permisos en el directorio de datos.')}
  `;},

  get _cRiskLevels() { return `
    ${this._p('RiskHub permite personalizar completamente los <strong>niveles de riesgo</strong> de tu organizacion: nombres, rangos numericos y colores. Esta configuracion afecta a todos los dashboards, heatmaps, tablas de riesgos y modulo TPRM de forma uniforme.')}

    ${this._h('Donde encontrar la configuracion')}
    ${this._steps([
      'Ve al menu lateral → <strong>Contexto</strong>.',
      'Busca la seccion <strong>Niveles de riesgo</strong> dentro de la pantalla de contexto.',
      'Aparecen los niveles actuales de tu organizacion (por defecto: Bajo, Medio, Alto, Critico).',
    ])}

    ${this._h('Como funciona el sistema de niveles')}
    ${this._p('Cada nivel de riesgo tiene tres atributos que puedes editar:')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px 12px;text-align:left;">Atributo</th>
        <th style="padding:8px 12px;text-align:left;">Descripcion</th>
        <th style="padding:8px 12px;text-align:left;">Ejemplo</th>
      </tr></thead>
      <tbody>
        ${[
          ['Nombre','Etiqueta que aparece en toda la plataforma para ese rango de riesgo.','Critico, Alto, Moderado, Bajo'],
          ['Rango (min - max)','Limite inferior y superior del nivel numerico (escala 0-8 ISO 27005).','7 - 8 para Critico'],
          ['Color','Color hexadecimal que identifica visualmente el nivel en dashboards y tablas.','#EF4444 para Critico'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          <td style="padding:8px 12px;font-weight:600;">${r[0]}</td>
          <td style="padding:8px 12px;">${r[1]}</td>
          <td style="padding:8px 12px;color:var(--text-muted);">${r[2]}</td>
        </tr>`).join('')}
      </tbody>
    </table>

    ${this._h('Niveles por defecto (ISO 27005)')}
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px;">
      ${[
        ['Bajo','0 - 2','#22C55E','Riesgo aceptable. Monitorizar sin accion inmediata.'],
        ['Medio','3 - 4','#F59E0B','Requiere atencion. Planificar tratamiento en el proximo ciclo.'],
        ['Alto','5 - 6','#EF4444','Tratamiento prioritario. Asignar responsable y fecha limite.'],
        ['Critico','7 - 8','#7C3AED','Accion inmediata. Escalar a direccion. No dejar sin plan.'],
      ].map(([n,r,c,d]) => `
        <div style="border-left:4px solid ${c};background:var(--bg-2);border-radius:0 8px 8px 0;padding:10px 12px;">
          <div style="font-weight:700;font-size:14px;color:${c};">${n}</div>
          <div style="font-size:12px;font-weight:600;margin:2px 0;">${r}</div>
          <div style="font-size:11px;color:var(--text-muted);line-height:1.4;">${d}</div>
        </div>`).join('')}
    </div>

    ${this._h('Personalizar los niveles')}
    ${this._steps([
      'En la seccion Niveles de riesgo del Contexto, haz clic en el icono de edicion de cualquier nivel.',
      'Cambia el <strong>nombre</strong> del nivel (ej. cambiar "Alto" por "Severo" o "Grave").',
      'Ajusta el <strong>rango</strong> numerico si tu politica interna usa limites diferentes.',
      'Haz clic en el <strong>selector de color</strong> para elegir un color personalizado. Puedes introducir directamente el codigo hexadecimal (#RRGGBB) o usar el selector visual.',
      'Pulsa <strong>Guardar</strong>. El cambio se aplica inmediatamente a toda la plataforma sin reiniciar.',
    ])}
    ${this._warn('<strong>Regla de consistencia:</strong> los rangos de los niveles deben cubrir toda la escala 0-8 sin solapamientos ni huecos. RiskHub valida esto automaticamente al guardar y te avisara si hay un conflicto de rangos.')}

    ${this._h('Donde se aplican los niveles personalizados')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Tabla de riesgos:</strong> la columna "Nivel residual" muestra el badge con el nombre y color del nivel correspondiente.</li>
      <li><strong>Heatmap:</strong> las celdas de la matriz 5x5 usan el degradado de colores de tus niveles.</li>
      <li><strong>Dashboard ejecutivo:</strong> los KPIs y graficos de distribucion usan tus colores personalizados.</li>
      <li><strong>TPRM:</strong> el heatmap de proveedores (inherente vs residual) usa la misma paleta.</li>
      <li><strong>Informes PDF:</strong> los badges de nivel en los informes reflejan tus nombres y colores.</li>
      <li><strong>Alertas por email:</strong> las reglas de alerta que usan "nivel alto" o "nivel critico" se mapean a tus rangos personalizados.</li>
      <li><strong>Dashboard de compliance:</strong> los contadores de riesgos por nivel usan tu configuracion.</li>
    </ul>

    ${this._h('Ejemplo de configuracion sectorial')}
    ${this._p('Diferentes sectores usan terminologias distintas para los niveles de riesgo. Aqui algunos ejemplos de personalizacion comunes:')}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
      ${[
        ['Banca / Finanzas','Inaceptable (7-8), Alto (5-6), Moderado (3-4), Aceptable (0-2)'],
        ['Salud / Sanitario','Extremo (7-8), Significativo (5-6), Moderado (3-4), Residual (0-2)'],
        ['Administracion Publica (ENS)','Muy alto (7-8), Alto (5-6), Medio (3-4), Bajo (0-2)'],
        ['Industria / Manufactura','Critico (7-8), Importante (5-6), Tolerable (3-4), Aceptable (0-2)'],
      ].map(([sector, niveles]) => `
        <div style="background:var(--bg-2);border-radius:8px;padding:12px 14px;">
          <div style="font-weight:700;font-size:13px;color:var(--brand-purple);margin-bottom:4px;">${sector}</div>
          <div style="font-size:12px;color:var(--text-muted);">${niveles}</div>
        </div>`).join('')}
    </div>
    ${this._tip('<strong>Buena practica:</strong> Define los niveles de riesgo durante la configuracion inicial del contexto, antes de crear los primeros riesgos. Si cambias los rangos despues de tener riesgos creados, los niveles existentes se recalculan automaticamente con los nuevos rangos.')}
  `;},

  get _cQuestionnaires() { return `
    ${this._p('RiskHub ofrece dos modalidades de cuestionario de seguridad para evaluar proveedores: <strong>cuestionarios internos</strong> (gestionados dentro de la plataforma) y <strong>cuestionarios externos</strong> via integraciones con Microsoft Forms o Monday.com. Ambas modalidades se acceden desde el hub de Proveedores.')}

    ${this._h('Opcion A — Cuestionarios internos (recomendado)')}
    ${this._p('Los cuestionarios internos son la via nativa de RiskHub. El proveedor recibe un enlace unico y responde desde su navegador sin necesidad de tener cuenta en la plataforma. Las respuestas se procesan automaticamente con scoring ponderado y opcionalmente se evaluan con el Agente IA.')}

    ${this._h('Como crear un cuestionario interno')}
    ${this._steps([
      'Ve al hub de <strong>Proveedores</strong> y selecciona el proveedor que quieres evaluar.',
      'Haz clic en la pestana <strong>Cuestionarios</strong> dentro del proveedor y pulsa <strong>+ Nuevo cuestionario</strong>.',
      'Elige una <strong>plantilla base</strong>: ISO 27001 completo, NIS2 Art. 21, DORA arts. 28-30, GDPR encargado del tratamiento, declaracion de uso de IA (ISO 42001) u offboarding.',
      'Configura la <strong>fecha de vencimiento</strong> (por defecto 30 dias) y el idioma del cuestionario.',
      'Pulsa <strong>Crear y copiar enlace</strong>. Se genera un token seguro de un solo uso.',
      'Envia el enlace al contacto del proveedor por email. El proveedor accede al cuestionario desde su navegador sin necesidad de cuenta en RiskHub.',
      'Cuando el proveedor envia las respuestas, el sistema calcula automaticamente la puntuacion (0-100) y notifica al responsable.',
    ])}

    ${this._h('Plantillas de cuestionario disponibles')}
    <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px;">
      <thead><tr style="background:var(--bg-2);">
        <th style="padding:8px 12px;text-align:left;">Plantilla</th>
        <th style="padding:8px 12px;text-align:left;">Marco</th>
        <th style="padding:8px 12px;text-align:left;">Uso tipico</th>
      </tr></thead>
      <tbody>
        ${[
          ['ISO 27001 Completo','ISO/IEC 27001:2022','Evaluacion anual de proveedores criticos con acceso a sistemas.'],
          ['NIS2 Art. 21','Directiva NIS2','Entidades reguladas NIS2: verifica medidas tecnicas y organizativas del proveedor.'],
          ['DORA Arts. 28-30','DORA (sector financiero)','Evaluacion de terceros de TIC para entidades financieras bajo DORA.'],
          ['GDPR Encargado','Reglamento GDPR','Proveedores que tratan datos personales en nombre de tu organizacion (DPA).'],
          ['Declaracion IA','ISO 42001','Proveedores que usan o desarrollan sistemas de inteligencia artificial.'],
          ['Offboarding','General','Lista de verificacion de baja de un proveedor: accesos revocados, datos eliminados, contratos terminados.'],
        ].map((r,i) => `<tr ${i%2?'style="background:var(--bg-2);"':''}>
          ${r.map(c => `<td style="padding:8px 12px;">${c}</td>`).join('')}
        </tr>`).join('')}
      </tbody>
    </table>

    ${this._h('Scoring ponderado y evaluacion con IA')}
    ${this._p('Cada pregunta del cuestionario tiene un peso especifico segun su importancia en el marco normativo. Las respuestas (Si / Parcialmente / No / No aplica) se puntuan en una escala ponderada que produce un <strong>score final de 0 a 100</strong>.')}
    <ul style="font-size:13px;padding-left:20px;margin:0 0 14px;">
      <li><strong>Si:</strong> puntuacion completa del peso de la pregunta.</li>
      <li><strong>Parcialmente:</strong> el 50% de la puntuacion del peso.</li>
      <li><strong>No:</strong> 0 puntos. Se registra como brecha.</li>
      <li><strong>No aplica:</strong> se excluye del calculo del denominador.</li>
    </ul>
    ${this._p('Opcionalmente, el Agente IA puede evaluar las respuestas narrativas libres del proveedor y devolver: puntuacion de confianza, banderas rojas detectadas y preguntas de seguimiento recomendadas. Si la confianza es baja, el cuestionario se marca para revision manual obligatoria.')}
    ${this._tip('<strong>Para lanzar la evaluacion IA:</strong> en la tabla de cuestionarios de un proveedor, haz clic en el boton <strong>Evaluar IA</strong> de la fila. Tambien se puede configurar para que se lance automaticamente cuando el proveedor envia las respuestas.')}

    ${this._h('Interpretacion de la puntuacion')}
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px;">
      ${[
        ['80-100','Bueno','Proveedor con buenas practicas de seguridad.','var(--risk-low)'],
        ['60-79','Aceptable','Algunas brechas menores. Seguimiento recomendado.','var(--brand-orange)'],
        ['40-59','Deficiente','Brechas significativas. Plan de mejora requerido.','var(--risk-high)'],
        ['0-39','Critico','Riesgo alto. Considerar cambio de proveedor o auditoria.','#7C3AED'],
      ].map(([r,l,d,c]) => `
        <div style="border-left:4px solid ${c};background:var(--bg-2);border-radius:0 8px 8px 0;padding:10px 12px;">
          <div style="font-weight:700;font-size:14px;color:${c};">${r}</div>
          <div style="font-size:12px;font-weight:600;margin:2px 0;">${l}</div>
          <div style="font-size:11px;color:var(--text-muted);line-height:1.4;">${d}</div>
        </div>`).join('')}
    </div>

    ${this._h('Opcion B — Cuestionarios externos (Microsoft Forms / Monday.com)')}
    ${this._p('Si tu organizacion ya usa Microsoft Forms o Monday.com para las evaluaciones de proveedores, puedes enlazarlos desde RiskHub sin necesidad de migrar los cuestionarios existentes.')}
    ${this._steps([
      'Ve al proveedor → pestana <strong>Cuestionarios</strong> → boton <strong>Enlazar cuestionario externo</strong>.',
      'Selecciona la plataforma: <strong>Microsoft Forms</strong> o <strong>Monday.com</strong>.',
      'Introduce la URL del formulario externo y el identificador del cuestionario.',
      'RiskHub guarda el enlace y lo muestra en la tabla de cuestionarios junto a los internos.',
      'Cuando el proveedor completa el formulario externo, importa manualmente los resultados usando el boton <strong>Importar respuestas</strong> (CSV o JSON segun la plataforma).',
    ])}
    ${this._warn('<strong>Limitacion de cuestionarios externos:</strong> el scoring automatico y la evaluacion IA no estan disponibles para cuestionarios externos. Las respuestas importadas se almacenan como texto libre y la puntuacion debe introducirse manualmente.')}

    ${this._h('Historial y trazabilidad')}
    ${this._p('Todos los cuestionarios (respondidos, pendientes y caducados) quedan registrados en la pestana Cuestionarios del proveedor con: fecha de envio, fecha de respuesta, puntuacion obtenida, cambio respecto al anterior y enlace a las respuestas detalladas. Esta trazabilidad es la evidencia documental requerida por NIS2 Art. 21.2.d para la evaluacion de proveedores.')}
    ${this._tip('<strong>Buena practica:</strong> envia cuestionarios anuales a todos los proveedores con tier Critico y Alto. Usa el dashboard TPRM para ver que proveedores llevan mas de 12 meses sin cuestionario y lanzarlos en bloque.')}
  `;},

};
