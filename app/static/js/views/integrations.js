/* Vista Integraciones — Catalogo de herramientas con guias de conexion a RiskHub. */
const ViewIntegrations = {

  _catalog: [
    // ---- Gestion de activos ----
    {
      id: "leanix", category: "Gestión de activos",
      name: "LeanIX Enterprise Architecture",
      description: "Plataforma de arquitectura empresarial con CMDB cloud-native. Permite gestionar aplicaciones, capacidades de negocio, proveedores y flujos de datos.",
      data: "Aplicaciones, componentes técnicos, interfaces, proveedores → Activos de RiskHub",
      api: "REST API + GraphQL (LeanIX Pathfinder API)",
      auth: "OAuth 2.0 Bearer Token (desde LeanIX Admin → API Tokens)",
      status: "guia",
      steps: [
        "Accede a tu instancia LeanIX (instance.leanix.net) como Administrador.",
        "Ve a Administration → API Tokens y genera un token con permiso READ.",
        "En RiskHub, en esta misma sección, copia la URL base (https://instance.leanix.net/services/pathfinder/v1/) y el token.",
        "Ejecuta una consulta GET /factSheets?type=Application para obtener el listado de aplicaciones.",
        "Mapea cada FactSheet a un Activo de RiskHub: name→nombre, category→tipo (support_software o primary_process).",
        "Importa manualmente los activos clave usando el formulario de Activos de RiskHub.",
        "Repite periódicamente o cuando se añadan nuevas aplicaciones críticas al catálogo LeanIX.",
      ],
      iso_mapping: "ISO 27005 Annex B — Identificación de activos primarios y de soporte.",
    },
    {
      id: "servicenow_cmdb", category: "Gestión de activos",
      name: "ServiceNow CMDB",
      description: "CMDB empresarial integrada en ServiceNow. Contiene CIs (Configuration Items) de hardware, software, redes y servicios de negocio.",
      data: "CIs de hardware, software, servidores, servicios → Activos de RiskHub",
      api: "ServiceNow Table API (REST)",
      auth: "Basic Auth o OAuth 2.0 (ServiceNow Admin → Application Registry)",
      status: "guia",
      steps: [
        "En ServiceNow, crea un usuario de servicio (service account) con rol cmdb_read.",
        "Obtén la URL base: https://instance.service-now.com/api/now/table/cmdb_ci",
        "Filtra por clase CI: cmdb_ci_appl (aplicaciones), cmdb_ci_server (servidores), cmdb_ci_netgear (red).",
        "Exporta en JSON: añade ?sysparm_fields=name,sys_class_name,category,location,u_criticality&sysparm_limit=1000",
        "Mapea campos: name→nombre, sys_class_name→tipo de activo, u_criticality→valoración CIA inicial.",
        "Importa los activos críticos en RiskHub mediante el formulario de Activos.",
        "Complementa la valoración CIA (Confidencialidad, Integridad, Disponibilidad) en RiskHub para cada activo.",
      ],
      iso_mapping: "ISO 27005 Annex B.1 — Primary and supporting assets.",
    },
    {
      id: "axonius", category: "Gestión de activos",
      name: "Axonius Cybersecurity Asset Management",
      description: "Plataforma de gestión de activos de ciberseguridad que correlaciona datos de múltiples fuentes para dar visibilidad completa de dispositivos y usuarios.",
      data: "Dispositivos, usuarios, aplicaciones, instancias cloud → Activos de RiskHub",
      api: "Axonius REST API v2",
      auth: "API Key + API Secret (Settings → API Keys)",
      status: "guia",
      steps: [
        "En Axonius, ve a Settings → API Keys y genera un par API Key / API Secret.",
        "Endpoint base: https://axonius-instance/api/v2/",
        "Consulta GET /assets/devices para obtener dispositivos con sus adaptadores asociados.",
        "Filtra por campos: specific_data.data.hostname, specific_data.data.os.type, adapters_data.",
        "Clasifica activos según su tipo: servidores→support_hardware, aplicaciones→support_software.",
        "Prioriza la importación de activos con mayor número de vulnerabilidades reportadas por Axonius.",
        "Correlaciona con los escáneres de vulnerabilidades conectados a Axonius para enriquecer el contexto.",
      ],
      iso_mapping: "ISO 27005 8.2.2 — Asset identification.",
    },
    {
      id: "lansweeper", category: "Gestión de activos",
      name: "Lansweeper IT Asset Discovery",
      description: "Herramienta de descubrimiento e inventario de activos TI (hardware, software, red). Escanea automáticamente la red para detectar todos los dispositivos.",
      data: "Dispositivos de red, equipos, licencias software → Activos de RiskHub",
      api: "Lansweeper Cloud API (GraphQL) o exportación CSV",
      auth: "API Key desde Lansweeper Cloud → Site Settings",
      status: "guia",
      steps: [
        "Accede a Lansweeper Cloud y ve a Site Settings → API Keys.",
        "Genera una API Key con permiso de lectura (Read-only).",
        "Endpoint GraphQL: https://api.lansweeper.com/api/v2/graphql",
        "Consulta assets con campos: assetName, assetType, IPAddress, operatingSystem, lastSeen.",
        "Exporta también en formato CSV desde Reports → Custom Reports para integración manual.",
        "Prioriza la importación de servidores, dispositivos de red y equipos con datos sensibles.",
        "Actualiza la valoración CIA en RiskHub para cada activo según su rol en los procesos de negocio.",
      ],
      iso_mapping: "ISO 27005 Annex B — Asset types and examples.",
    },

    // ---- Gestion de vulnerabilidades ----
    {
      id: "qualys", category: "Gestión de vulnerabilidades",
      name: "Qualys VMDR",
      description: "Plataforma líder de Vulnerability Management, Detection and Response. Proporciona visibilidad continua de vulnerabilidades en activos TI y cloud.",
      data: "CVEs por activo, severidad CVSS, estado de parcheo → Vulnerabilidades de RiskHub",
      api: "Qualys API v2 (REST XML/JSON)",
      auth: "Basic Auth (usuario/contraseña de Qualys) + API Server URL por región",
      status: "guia",
      steps: [
        "Obtén tu URL de API según región (p.ej. https://qualysapi.qualys.eu para Europa).",
        "Usa tus credenciales de Qualys en Basic Auth en cada petición.",
        "Endpoint: GET /api/2.0/fo/asset/host/vm/detection/?action=list&status=New,Active",
        "El resultado XML contiene HOST_LIST con QID (Qualys ID), CVE, SEVERITY (1-5) y TITLE.",
        "Mapea SEVERITY a nivel de vulnerabilidad: 5=Crítico, 4=Alto, 3=Medio, 2=Bajo, 1=Info.",
        "Para cada CVE detectado, busca la vulnerabilidad correspondiente en el catálogo de RiskHub (Vulnerabilidades).",
        "Si no existe, crea una nueva vulnerabilidad personalizada y asóciala al riesgo correspondiente (activo + amenaza).",
        "Documenta en el campo 'notas' del riesgo el CVE, CVSS score y el activo afectado.",
        "Usa el Agente IA de RiskHub para que asocie automáticamente las vulnerabilidades al escenario de riesgo más relevante.",
      ],
      iso_mapping: "ISO 27005 Annex D — Vulnerabilities and vulnerability assessment methods.",
    },
    {
      id: "tenable", category: "Gestión de vulnerabilidades",
      name: "Tenable.io / Tenable Nessus",
      description: "Solución de gestión de vulnerabilidades ampliamente adoptada. Nessus es el escáner de referencia; Tenable.io es la plataforma cloud con análisis continuo.",
      data: "Vulnerabilidades por host, plugins Nessus, CVSS, exploitability → Vulnerabilidades RiskHub",
      api: "Tenable.io API (REST) o exportación Nessus (.nessus XML)",
      auth: "Access Key + Secret Key (Tenable.io → Settings → My Account → API Keys)",
      status: "guia",
      steps: [
        "En Tenable.io, ve a Settings → My Account → API Keys y genera Access Key y Secret Key.",
        "Cabecera de autenticación: X-ApiKeys: accessKey=XXX;secretKey=YYY",
        "Endpoint: GET /workbenches/vulnerabilities para listado consolidado de vulnerabilidades.",
        "Filtra por severity: GET /workbenches/vulnerabilities?severity=critical,high",
        "Para Nessus standalone, exporta el scan en formato .nessus (XML) y parsea el campo <ReportItem>.",
        "Mapea plugin_name → nombre de vulnerabilidad, cvss3_base_score → severidad.",
        "Cruza el host afectado con el Activo correspondiente en RiskHub (por IP o nombre).",
        "Asocia la vulnerabilidad al Riesgo existente o crea uno nuevo con el Agente IA.",
        "Actualiza el nivel de probabilidad inherente del riesgo si la vulnerabilidad es crítica (CVSS ≥ 9).",
      ],
      iso_mapping: "ISO 27005 Annex D.2 — Technical vulnerabilities.",
    },
    {
      id: "rapid7", category: "Gestión de vulnerabilidades",
      name: "Rapid7 InsightVM",
      description: "Plataforma de gestión de vulnerabilidades con análisis de riesgo contextualizado (RRI - Real Risk), priorización y remediación integrada.",
      data: "Vulnerabilidades por activo, Real Risk Score, estado remediación → RiskHub",
      api: "InsightVM REST API",
      auth: "Basic Auth (usuario administrador de InsightVM) sobre HTTPS",
      status: "guia",
      steps: [
        "URL base: https://hostname:3780/api/3/ (puerto 3780 por defecto).",
        "Endpoint: GET /api/3/vulnerabilities?sort=riskScore,DESC para vulnerabilidades ordenadas por riesgo.",
        "Endpoint por activo: GET /api/3/assets/{assetId}/vulnerabilities",
        "Campos relevantes: title, cvssV3Score, riskScore, status (vulnerable/notVulnerable).",
        "Exporta también desde Reports → Export → XML o CSV para análisis masivo.",
        "Prioriza vulnerabilidades con riskScore > 700 (equivalente a alto/crítico en InsightVM).",
        "Asocia cada vulnerabilidad a activos y riesgos en RiskHub, actualizando el nivel residual.",
        "Documenta el CVE y el Real Risk Score de Rapid7 en el campo descripción del riesgo en RiskHub.",
      ],
      iso_mapping: "ISO 27005 Annex D — Vulnerability identification and assessment.",
    },
    {
      id: "openvas", category: "Gestión de vulnerabilidades",
      name: "OpenVAS / Greenbone",
      description: "Escáner de vulnerabilidades open-source ampliamente usado. Greenbone Community Edition es la distribución gratuita; Greenbone Enterprise ofrece GMP API.",
      data: "Vulnerabilidades detectadas en red, CVEs, NVTs → Vulnerabilidades RiskHub",
      api: "GMP (Greenbone Management Protocol) o exportación XML de resultados",
      auth: "Usuario GMP (greenbone-feed-sync, gvm-cli)",
      status: "guia",
      steps: [
        "Instala gvm-tools: pip install gvm-tools",
        "Conecta al socket: gvm-cli --gmp-username admin --gmp-password PASS socket --socketpath /run/gvmd/gvmd.sock",
        "Exporta resultados del último scan: gvm-cli socket --xml '<get_results/>'",
        "Del XML resultante, extrae <result> con campos: name, severity, host, nvt/cve.",
        "Severity en OpenVAS: 0.0-3.9 Bajo, 4.0-6.9 Medio, 7.0-8.9 Alto, 9.0-10.0 Crítico.",
        "Crea o actualiza vulnerabilidades en RiskHub según los NVTs encontrados.",
        "Asocia al activo correspondiente (por IP) y al riesgo de RiskHub más relevante.",
        "Re-ejecuta el scan periódicamente (mensual o tras cambios en infraestructura).",
      ],
      iso_mapping: "ISO 27005 Annex D.1 — Vulnerability sources and methods.",
    },
    {
      id: "wiz", category: "Gestión de vulnerabilidades",
      name: "Wiz",
      description: "Plataforma de seguridad cloud (CNAPP) que proporciona visibilidad completa de riesgos en AWS, Azure y GCP, incluyendo vulnerabilidades, configuraciones incorrectas y rutas de ataque.",
      data: "Findings cloud (CVEs, misconfigs, IAM), rutas de ataque → Vulnerabilidades y Riesgos RiskHub",
      api: "Wiz GraphQL API",
      auth: "OAuth 2.0 Client Credentials (Wiz → Settings → Service Accounts)",
      status: "guia",
      steps: [
        "En Wiz, ve a Settings → Service Accounts y crea uno con permiso read:vulnerabilities.",
        "Obtén el token: POST https://auth.app.wiz.io/oauth/token con client_id y client_secret.",
        "Endpoint GraphQL: https://api.app.wiz.io/graphql",
        "Query para vulnerabilities: { vulnerabilities(first: 100, filterBy: {severity: [HIGH, CRITICAL]}) { ... } }",
        "Campos clave: name, severity, cveId, affectedEntity (asset), status (open/resolved).",
        "Mapea affectedEntity a activos cloud de RiskHub (instancias EC2, contenedores, etc.).",
        "Prioriza findings de tipo 'attack path' — indican encadenamiento de vulnerabilidades explotable.",
        "Crea riesgos en RiskHub para cada ruta de ataque crítica identificada por Wiz.",
        "Usa el Agente IA de RiskHub para generar el escenario de riesgo completo a partir del finding.",
      ],
      iso_mapping: "ISO 27005 Annex D.2 — Technical vulnerabilities (cloud infrastructure).",
    },
    {
      id: "snyk", category: "Gestión de vulnerabilidades",
      name: "Snyk",
      description: "Plataforma de seguridad para código, dependencias de código abierto, contenedores e IaC. Especialmente relevante para entornos de desarrollo con CI/CD.",
      data: "Vulnerabilidades en código, dependencias (SCA), contenedores, IaC → Vulnerabilidades RiskHub",
      api: "Snyk REST API v1",
      auth: "API Token personal o de servicio (Snyk Account Settings → Auth Token)",
      status: "guia",
      steps: [
        "Obtén tu token en app.snyk.io → Account Settings → Auth Token.",
        "Cabecera: Authorization: token TU_TOKEN",
        "Endpoint: GET /api/v1/org/{orgId}/projects para listar proyectos.",
        "Endpoint issues: GET /api/v1/org/{orgId}/project/{projectId}/issues",
        "Filtra por severity: critical, high, medium para priorizar.",
        "Mapea cada issue a una vulnerabilidad de RiskHub: title→nombre, CVE→código.",
        "El activo afectado es el sistema/aplicación donde reside el código vulnerable.",
        "Documenta el ID de Snyk y el CVE en el campo notas del riesgo en RiskHub.",
        "Re-evalúa el nivel residual del riesgo cuando Snyk marque el issue como 'fixed'.",
      ],
      iso_mapping: "ISO 27005 Annex D.2 — Application and software vulnerabilities.",
    },

    // ---- ERP / Gestion de proveedores ----
    {
      id: "sap_erp", category: "ERP / Gestión de proveedores",
      name: "SAP ERP / SAP S/4HANA",
      description: "Sistema ERP de referencia en grandes organizaciones. Contiene el maestro de proveedores, contratos de aprovisionamiento y datos de proceso críticos que son activos primarios del SGSI.",
      data: "Maestro de proveedores (LFA1/LFB1), contratos (EKKO/EKPO), procesos críticos → Proveedores y Activos RiskHub",
      api: "SAP OData (NetWeaver Gateway) o RFC/BAPI via SAP Integration Suite",
      auth: "Basic Auth o OAuth 2.0 (SAP BTP / SAP Identity Authentication Service)",
      status: "guia",
      steps: [
        "Coordina con el equipo SAP Basis para habilitar el servicio OData del maestro de proveedores: /sap/opu/odata/sap/API_BUSINESS_PARTNER/",
        "Autentícate con usuario de solo lectura (rol: SAP_BC_ODATA_ACCESS): GET /sap/opu/odata/sap/API_BUSINESS_PARTNER/A_Supplier",
        "Exporta los proveedores críticos con campos: Supplier, SupplierName, Country, BlockedForPosting, PurchasingBlockStatus.",
        "Para cada proveedor crítico (contratos activos), crea un Proveedor en RiskHub con nombre, país y categoría.",
        "Exporta los procesos de negocio clave desde SAP (t.code SE16 → tabla JEST o AUFK) para identificar activos primarios.",
        "Alternativamente, exporta desde SAP en formato CSV (t.code SE16N → Lista → Exportar) y usa la importación CSV de Proveedores de RiskHub.",
        "Clasifica los proveedores según el nivel de acceso a datos sensibles: alto (acceso a datos personales o sistemas críticos) / medio / bajo.",
        "Asocia a cada proveedor de alto riesgo la amenaza 'Acceso no autorizado por terceros' y los controles ISO 27002 cl. 5.19-5.22.",
        "Actualiza el nivel de riesgo inherente si el proveedor tiene acceso a activos clasificados como confidenciales o críticos.",
      ],
      iso_mapping: "ISO 27005 Annex B — Primary assets (business processes). ISO 27002:2022 cl. 5.19 (Seguridad de la información en relaciones con proveedores).",
    },
    {
      id: "sap_fieldglass", category: "ERP / Gestión de proveedores",
      name: "SAP Fieldglass (Jagger / VMS)",
      description: "Plataforma de gestión de fuerza de trabajo externa (Vendor Management System). Gestiona contratos con proveedores de servicios, consultores externos y trabajadores contingentes que pueden acceder a activos de información.",
      data: "Trabajadores contingentes, proveedores de servicios, contratos activos → Proveedores y Riesgos RiskHub",
      api: "SAP Fieldglass REST API v1",
      auth: "OAuth 2.0 (SAP Fieldglass Admin → API Credentials)",
      status: "guia",
      steps: [
        "En SAP Fieldglass, accede como Administrador y ve a Configuration → Web Services → API Credentials.",
        "Genera credenciales OAuth 2.0 (client_id + client_secret) con permiso de lectura.",
        "Token endpoint: POST https://www.fieldglass.net/api/oauth2/v2.0/token",
        "Endpoint proveedores: GET https://www.fieldglass.net/api/v1/suppliers?status=active",
        "Endpoint trabajadores: GET https://www.fieldglass.net/api/v1/workers?status=active para trabajadores con acceso a sistemas.",
        "Identifica proveedores con acceso a sistemas críticos: filtra workers con site=datacenter o department=IT.",
        "Para cada proveedor con acceso a datos sensibles, crea un Proveedor en RiskHub con categoría 'Servicios TI' o 'Consultoría'.",
        "Evalúa el riesgo de cada proveedor usando el cuestionario de proveedores de RiskHub (Proveedores → Cuestionarios).",
        "Asocia los controles ISO 27002 cl. 6.6 (Acuerdos de confidencialidad) y 5.20 (Requisitos de seguridad en contratos) a cada proveedor de riesgo alto.",
        "Configura una alerta en RiskHub para notificar cuando expire el contrato de un proveedor con acceso a activos críticos.",
      ],
      iso_mapping: "ISO 27005 — Third-party and supply chain risks. ISO 27002:2022 cl. 5.19, 5.20, 6.6.",
    },
    {
      id: "csv_erp_import", category: "ERP / Gestión de proveedores",
      name: "Importacion CSV desde cualquier ERP",
      description: "Metodo universal para importar proveedores desde cualquier sistema ERP (SAP, Oracle, Microsoft Dynamics, Sage, Holded, etc.) mediante exportacion a CSV.",
      data: "Listado de proveedores exportado del ERP → Proveedores de RiskHub",
      api: "Exportacion nativa a CSV/Excel de cualquier ERP",
      auth: "No requiere — proceso offline de transformacion y carga",
      status: "guia",
      steps: [
        "En tu ERP, exporta el maestro de proveedores activos en formato CSV o Excel.",
        "El fichero debe incluir al menos: nombre, CIF/NIF, pais, categoria de servicio, persona de contacto y email.",
        "Abre el fichero en Excel u hoja de calculo y adapta las columnas al formato de RiskHub.",
        "En RiskHub, ve a Proveedores → boton de importacion (si disponible) o crea los proveedores manualmente para los criticos.",
        "Prioriza los proveedores que: tienen acceso remoto a sistemas, procesan datos personales, o son criticos para la operacion.",
        "Para cada proveedor critico importado, completa: nivel de riesgo inherente, categoria (TI/nube/servicios profesionales/instalaciones), SLA y fecha de revision.",
        "Adjunta el contrato o acuerdo de confidencialidad escaneado en el campo de documentacion del proveedor.",
        "Usa el cuestionario de seguridad de proveedores de RiskHub para evaluar y documentar el nivel de madurez de seguridad de cada proveedor.",
        "Programa una revision periodica en el calendario de RiskHub para los proveedores de nivel de riesgo alto o critico.",
      ],
      iso_mapping: "ISO 27005 Annex B — Supporting assets: suppliers and partners. ISO 27002:2022 cl. 5.19.",
    },

    // ---- Riesgo de terceros ----
    {
      id: "sphera", category: "Gestión de riesgos de terceros",
      name: "Sphera",
      description: "Plataforma GRC líder para gestión de riesgos de terceros, EHS (Environment, Health & Safety) y seguridad de la cadena de suministro.",
      data: "Riesgos de proveedores, evaluaciones de terceros, incidentes → Riesgos y Amenazas RiskHub",
      api: "Sphera REST API (requiere licencia Enterprise)",
      auth: "OAuth 2.0 (Sphera Admin → API Management)",
      status: "guia",
      steps: [
        "Coordina con tu Customer Success Manager de Sphera para habilitar el acceso API.",
        "Obtén las credenciales OAuth 2.0 desde Sphera Admin → API Management.",
        "Endpoint para riesgos de terceros: GET /api/v1/third-party-risks",
        "Campos relevantes: supplier_name, risk_category, risk_score, assessment_date, findings.",
        "Para cada hallazgo crítico de Sphera, identifica el activo RiskHub afectado (sistema, proceso o dato).",
        "Crea o actualiza el Riesgo en RiskHub: amenaza (ej. 'Fallo de proveedor crítico'), activo (proceso de negocio dependiente).",
        "Usa el Agente IA de RiskHub para generar el escenario de riesgo completo a partir del hallazgo de Sphera.",
        "Asocia controles de RiskHub (ej. 5.19 Seguridad de la información en relaciones con proveedores) al riesgo.",
        "Programa revisiones periódicas sincronizadas con los ciclos de evaluación de Sphera.",
      ],
      iso_mapping: "ISO 27005 — Threat identification (supplier/third-party threats). ISO 27002:2022 cl. 5.19-5.22.",
    },
    {
      id: "archer", category: "Gestión de riesgos de terceros",
      name: "Archer RSA / RSA Archer",
      description: "Plataforma GRC enterprise de RSA. Centraliza la gestión de riesgos, cumplimiento, terceros y continuidad de negocio.",
      data: "Riesgos empresariales, evaluaciones de terceros, controles, incidentes → RiskHub",
      api: "Archer Content API (REST/XML-RPC)",
      auth: "Usuario/contraseña Archer + sessionId de API",
      status: "guia",
      steps: [
        "Obtén acceso API: POST /platformapi/core/security/login con user/password para obtener SessionToken.",
        "Endpoint: POST /platformapi/core/content/search para buscar registros de riesgos o terceros.",
        "Define el applicationId de la aplicación 'Third Party Management' en tu instancia Archer.",
        "Exporta campos: Vendor Name, Risk Rating, Assessment Status, Findings, Due Date.",
        "Mapea cada vendor con hallazgos críticos a un activo de RiskHub (el proceso de negocio dependiente).",
        "Crea un Riesgo en RiskHub por cada proveedor crítico con findings abiertos.",
        "Asocia la amenaza correspondiente del catálogo (ej. 'Dependencia de proveedor').",
        "Documenta el ID de Archer en el campo descripción del riesgo para trazabilidad.",
      ],
      iso_mapping: "ISO 27005 — Threat catalogue (organizational context threats). ISO 27002 cl. 5.19.",
    },
    {
      id: "servicenow_grc", category: "Gestión de riesgos de terceros",
      name: "ServiceNow GRC",
      description: "Módulo GRC de ServiceNow para gestión integrada de riesgos, cumplimiento, auditoría y gestión de proveedores en la plataforma Now.",
      data: "Riesgos, controles, evaluaciones de cumplimiento, terceros → RiskHub",
      api: "ServiceNow Table API / GRC API (REST)",
      auth: "Basic Auth o OAuth 2.0 con rol sn_grc_manager",
      status: "guia",
      steps: [
        "Crea un usuario de servicio en ServiceNow con rol sn_grc_manager (solo lectura).",
        "Endpoint riesgos: GET /api/now/table/sn_risk_risk?sysparm_fields=name,description,risk_rating,state",
        "Endpoint terceros: GET /api/now/table/sn_vdr_vendor?sysparm_fields=name,risk_rating,assessment_status",
        "Filtra por risk_rating: critical, high para priorizar la importación.",
        "Mapea cada riesgo de ServiceNow GRC a la estructura ISO 27005 de RiskHub.",
        "Sincroniza el estado del control (sn_compliance_control) con ControlImplementation de RiskHub.",
        "Documenta el sys_id de ServiceNow en RiskHub para mantener la trazabilidad bidireccional.",
      ],
      iso_mapping: "ISO 27005 — Risk management lifecycle integration.",
    },
    {
      id: "vanta", category: "Gestión de riesgos de terceros",
      name: "Vanta",
      description: "Plataforma de automatización de cumplimiento (SOC 2, ISO 27001, GDPR, HIPAA). Monitoriza controles técnicos de forma continua y gestiona evidencias.",
      data: "Estado de controles, gaps de cumplimiento, acceso de empleados → Controles RiskHub",
      api: "Vanta API v1 (REST)",
      auth: "API Token (Vanta → Settings → API Tokens)",
      status: "guia",
      steps: [
        "En Vanta, ve a Settings → API Tokens y genera un token de solo lectura.",
        "Endpoint: GET /v1/controls para listar el estado de todos los controles monitorizados.",
        "Endpoint: GET /v1/tests para ver los tests de cumplimiento y su estado (passing/failing).",
        "Mapea cada control de Vanta con su equivalente en el catálogo ISO 27002 de RiskHub.",
        "Actualiza el campo 'status' de los ControlImplementation en RiskHub según el estado en Vanta.",
        "Usa los failing tests de Vanta para identificar vulnerabilidades y actualizar riesgos en RiskHub.",
        "Sincroniza el nivel de madurez (0-5) del control en RiskHub con la cobertura reportada por Vanta.",
      ],
      iso_mapping: "ISO 27002:2022 — Control implementation status tracking.",
    },
    {
      id: "drata", category: "Gestión de riesgos de terceros",
      name: "Drata",
      description: "Plataforma de compliance continuo y Trust Management para SOC 2, ISO 27001, GDPR y otros frameworks. Automatiza la recogida de evidencias.",
      data: "Estado de controles, evidencias, gaps → Controles y Riesgos RiskHub",
      api: "Drata Public API (REST)",
      auth: "API Key (Drata → Settings → API Keys)",
      status: "guia",
      steps: [
        "Obtén tu API Key en Drata → Settings → API Keys.",
        "Cabecera: drata-api-key: TU_API_KEY",
        "Endpoint: GET /api/public/v1/controls para obtener el estado de todos los controles.",
        "Endpoint: GET /api/public/v1/risks para los riesgos gestionados en Drata.",
        "Para cada control con status FAILING o NEEDS_ATTENTION, actualiza su estado en RiskHub.",
        "Exporta la lista de riesgos de Drata y compara con el registro de riesgos de RiskHub.",
        "Documenta las evidencias recopiladas por Drata en el campo 'evidencias' del ControlImplementation.",
      ],
      iso_mapping: "ISO 27001:2022 — Annex A controls alignment and evidence management.",
    },
    {
      id: "onetrust", category: "Gestión de riesgos de terceros",
      name: "OneTrust",
      description: "Plataforma líder en privacidad, cumplimiento y gestión de riesgos de terceros. Cubre GDPR, CCPA, evaluaciones de impacto (DPIA/PIA) y third-party due diligence.",
      data: "Riesgos de privacidad, DPIAs, evaluaciones de terceros → Riesgos RiskHub",
      api: "OneTrust REST API",
      auth: "OAuth 2.0 Client Credentials (OneTrust → Developer → Applications)",
      status: "guia",
      steps: [
        "En OneTrust, ve a Developer → Applications y registra una nueva aplicación para obtener Client ID y Secret.",
        "Obtén token: POST /api/access/v1/oauth/token",
        "Endpoint assessments: GET /api/datasubject/v3/assessments para DPIAs y evaluaciones de proveedores.",
        "Endpoint terceros: GET /api/thirdparty/v1/vendors para el catálogo de proveedores.",
        "Filtra proveedores con riesgo inherente Alto o Crítico para priorizar.",
        "Crea riesgos en RiskHub para cada proveedor con tratamiento de datos sensibles sin controles suficientes.",
        "Asocia la amenaza 'Acceso no autorizado por terceros' y el activo correspondiente (base de datos, proceso).",
        "Añade los controles ISO 27002 cl. 5.19-5.22 (Seguridad en relaciones con proveedores) al riesgo.",
      ],
      iso_mapping: "ISO 27005 — Privacy-related risks. GDPR Art. 35 (DPIA). ISO 27002 cl. 5.19.",
    },

    // ---- SIEM / SOC ----
    {
      id: "splunk", category: "SIEM / Operaciones de seguridad",
      name: "Splunk Enterprise Security",
      description: "SIEM líder del mercado para análisis de eventos de seguridad, detección de amenazas y respuesta a incidentes. Correlaciona logs de toda la infraestructura.",
      data: "Notable Events, Risk Scores por activo, incidentes detectados → Riesgos y Amenazas RiskHub",
      api: "Splunk REST API + SDK",
      auth: "Usuario/contraseña Splunk o Token de autenticación",
      status: "guia",
      steps: [
        "Genera un token de autenticación en Splunk: Settings → Tokens → New Token.",
        "Endpoint: GET https://splunk:8089/services/search/jobs para ejecutar búsquedas SPL.",
        "Busca notable events de riesgo alto: SPL: index=notable severity=high OR severity=critical | stats count by src_ip, dest_ip, rule_name",
        "Para el Risk Framework de Splunk ES: GET /services/alerts/fired_alerts para alertas activadas.",
        "Correlaciona la dirección IP/hostname con los Activos de RiskHub.",
        "Por cada tipo de ataque recurrente (rule_name), verifica si existe un Riesgo en RiskHub y actualiza su probabilidad.",
        "Exporta el conteo mensual de incidentes por categoría para actualizar la frecuencia de amenazas.",
        "Usa el Agente IA de RiskHub para interpretar patrones de Splunk y generar nuevos escenarios de riesgo.",
      ],
      iso_mapping: "ISO 27005 — Threat likelihood estimation based on incident history.",
    },
    {
      id: "sentinel", category: "SIEM / Operaciones de seguridad",
      name: "Microsoft Sentinel",
      description: "SIEM y SOAR cloud-native de Microsoft Azure. Integra con todo el ecosistema Microsoft 365 y Azure para detección y respuesta a amenazas.",
      data: "Incidents, Security Alerts, Analytics Rules → Amenazas y frecuencia en RiskHub",
      api: "Microsoft Sentinel REST API / Azure Monitor API",
      auth: "Azure AD App Registration con permisos Microsoft.SecurityInsights/incidents/read",
      status: "guia",
      steps: [
        "En Azure AD, registra una aplicación y asigna el rol 'Microsoft Sentinel Reader' al Resource Group.",
        "Obtén token: POST https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token",
        "Endpoint incidents: GET https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.OperationalInsights/workspaces/{ws}/providers/Microsoft.SecurityInsights/incidents",
        "Filtra por severity: High, Critical y status: Active.",
        "Para cada tipo de incidente recurrente, verifica la amenaza correspondiente en RiskHub.",
        "Actualiza la probabilidad inherente del riesgo según la frecuencia de alertas en el último trimestre.",
        "Documenta los MITRE ATT&CK tácticas/técnicas de los incidentes para enriquecer las amenazas de RiskHub.",
        "Genera un informe mensual con el Agente IA usando los datos de Sentinel como contexto adicional.",
      ],
      iso_mapping: "ISO 27005 Annex C — Threat identification using incident data.",
    },

    // ---- Identidad y acceso ----
    {
      id: "entra", category: "Identidad y acceso",
      name: "Microsoft Entra ID (Azure AD)",
      description: "Servicio de identidad y acceso de Microsoft. Gestiona usuarios, grupos, aplicaciones corporativas y políticas de acceso condicional.",
      data: "Usuarios, grupos, aplicaciones registradas, sign-in risk → Activos y contexto RiskHub",
      api: "Microsoft Graph API",
      auth: "OAuth 2.0 + Azure AD App Registration con permisos Directory.Read.All",
      status: "guia",
      steps: [
        "Registra una aplicación en Azure AD con permiso de aplicación: Directory.Read.All, IdentityRiskyUser.Read.All.",
        "Endpoint aplicaciones: GET https://graph.microsoft.com/v1.0/applications",
        "Endpoint usuarios de riesgo: GET https://graph.microsoft.com/v1.0/identityProtection/riskyUsers?$filter=riskLevel eq 'high'",
        "Las aplicaciones registradas son activos de tipo support_software → impórtalas a RiskHub.",
        "Los usuarios de riesgo alto indican un aumento de probabilidad en amenazas de identidad comprometida.",
        "Revisa Identity Protection Alerts y refleja en RiskHub como aumento de probabilidad de amenazas de acceso.",
        "Verifica que los controles ISO 27002 cl. 5.15-5.18 (Gestión de identidades y acceso) estén implementados.",
      ],
      iso_mapping: "ISO 27005 Annex B — Support asset: personnel. ISO 27002 cl. 5.15.",
    },
    {
      id: "okta", category: "Identidad y acceso",
      name: "Okta",
      description: "Plataforma de gestión de identidad y acceso (IAM) cloud-native. Proporciona SSO, MFA, lifecycle management y acceso a aplicaciones SaaS.",
      data: "Aplicaciones integradas, usuarios, eventos de autenticación → Activos y contexto RiskHub",
      api: "Okta Management API (REST)",
      auth: "API Token (Okta Admin → Security → API → Tokens) o OAuth 2.0",
      status: "guia",
      steps: [
        "Genera un API Token con permisos de lectura: Okta Admin → Security → API → Tokens.",
        "Cabecera: Authorization: SSWS TU_TOKEN",
        "Endpoint apps: GET https://company.okta.com/api/v1/apps?filter=status eq ACTIVE",
        "Cada aplicación activa en Okta es un activo de tipo support_software en RiskHub.",
        "Endpoint eventos: GET https://company.okta.com/api/v1/logs?filter=eventType eq 'user.authentication.auth_via_mfa_factor' AND outcome.result eq 'FAILURE'",
        "Los fallos repetidos de MFA indican intentos de acceso no autorizado → sube la probabilidad de amenazas de acceso.",
        "Verifica en RiskHub que el control 5.17 (Authentication information) está implementado para cada app crítica de Okta.",
      ],
      iso_mapping: "ISO 27005 — Threat likelihood (unauthorized access). ISO 27002 cl. 5.17.",
    },

    // ---- Seguridad cloud ----
    {
      id: "aws_security_hub", category: "Seguridad cloud",
      name: "AWS Security Hub",
      description: "Servicio central de seguridad de AWS que agrega, organiza y prioriza alertas de múltiples servicios de AWS (GuardDuty, Inspector, Config, Macie).",
      data: "Security findings, compliance checks (CIS, NIST), vulnerabilidades → RiskHub",
      api: "AWS SDK / AWS CLI (SecurityHub API)",
      auth: "IAM Role con permiso securityhub:GetFindings (asignado a un Access Key de lectura)",
      status: "guia",
      steps: [
        "Crea un IAM User de solo lectura con política AWSSecurityHubReadOnlyAccess.",
        "Instala AWS CLI: aws configure con Access Key ID y Secret Access Key.",
        "Comando: aws securityhub get-findings --filters '{\"SeverityLabel\":[{\"Value\":\"CRITICAL\",\"Comparison\":\"EQUALS\"},{\"Value\":\"HIGH\",\"Comparison\":\"EQUALS\"}]}'",
        "Campos clave: Title, Description, Resources[].Type (activo), Severity.Label, WorkflowState.",
        "Mapea cada finding a un activo de RiskHub: Resources[].Id puede ser un ARN de instancia EC2, S3 bucket, etc.",
        "Para findings de tipo compliance (CIS, NIST), actualiza el estado de controles en RiskHub.",
        "Para findings de GuardDuty, actualiza la probabilidad de amenazas correspondientes.",
        "Automatiza la exportación mensual con: aws securityhub get-findings > findings.json y procésalo.",
      ],
      iso_mapping: "ISO 27005 — Cloud asset risks. ISO 27002 cl. 8.23 (Web filtering), 8.25 (Secure development).",
    },
    {
      id: "defender_cloud", category: "Seguridad cloud",
      name: "Microsoft Defender for Cloud",
      description: "Plataforma de protección de cargas de trabajo cloud (CWPP) y CSPM para Azure, AWS y GCP. Proporciona Secure Score, recomendaciones de seguridad y alertas.",
      data: "Recomendaciones de seguridad, alertas de amenazas, Secure Score → Riesgos y Controles RiskHub",
      api: "Azure Security Center REST API / Microsoft Defender for Cloud API",
      auth: "Azure AD + permisos Security Reader en la suscripción",
      status: "guia",
      steps: [
        "Registra app Azure AD con rol 'Security Reader' en la suscripción.",
        "Endpoint secure score: GET https://management.azure.com/subscriptions/{subId}/providers/Microsoft.Security/secureScores",
        "Endpoint recomendaciones: GET /providers/Microsoft.Security/assessments?$filter=status/code eq 'Unhealthy'",
        "Endpoint alertas: GET /providers/Microsoft.Security/alerts?$filter=properties/severity eq 'High'",
        "Cada recomendación 'Unhealthy' representa un control de RiskHub no implementado.",
        "Actualiza el status del ControlImplementation correspondiente según las recomendaciones de Defender for Cloud.",
        "Las alertas de amenazas activas deben reflejarse como aumento de probabilidad en los riesgos de RiskHub.",
        "Usa el Secure Score como KPI de nivel de madurez de seguridad en los informes ejecutivos de RiskHub.",
      ],
      iso_mapping: "ISO 27005 — Control effectiveness assessment. ISO 27002 cl. 8 (Technological controls).",
    },
    {
      id: "gcp_scc", category: "Seguridad cloud",
      name: "Google Security Command Center",
      description: "Plataforma de gestión de riesgos de seguridad para Google Cloud. Detecta vulnerabilidades, amenazas y configuraciones incorrectas en proyectos GCP.",
      data: "Findings de seguridad, anomalías, misconfiguraciones → Riesgos y Vulnerabilidades RiskHub",
      api: "Security Command Center API (v1)",
      auth: "Service Account con rol roles/securitycenter.findingsViewer",
      status: "guia",
      steps: [
        "Crea un Service Account en GCP IAM con rol roles/securitycenter.findingsViewer.",
        "Descarga la clave JSON del Service Account.",
        "Instala Google Cloud CLI: gcloud auth activate-service-account --key-file=sa-key.json",
        "Comando: gcloud scc findings list organizations/ORG_ID --filter='state=ACTIVE AND severity=HIGH OR severity=CRITICAL'",
        "Campos clave: name (finding ID), category (tipo de vulnerabilidad/amenaza), resourceName (activo GCP), severity.",
        "Mapea resourceName a activos de RiskHub: instances → support_hardware, cloudsql → support_software.",
        "Para findings de tipo VULNERABILITY, crea o actualiza vulnerabilidades en RiskHub.",
        "Para findings de THREAT, actualiza la probabilidad de la amenaza correspondiente.",
      ],
      iso_mapping: "ISO 27005 — Cloud infrastructure risk identification.",
    },
  ],

  _categories() {
    const cats = {};
    this._catalog.forEach(t => {
      if (!cats[t.category]) cats[t.category] = [];
      cats[t.category].push(t);
    });
    return cats;
  },

  async render(main) {
    main.innerHTML = UI.sectionHeader(
      'Integraciones',
      'Integraciones en vivo y catalogo de herramientas GRC'
    ) + `
      <div style="display:flex;gap:8px;margin-bottom:20px;">
        <button class="btn btn-primary" id="int-tab-live" onclick="ViewIntegrations._showTab('live')">Live</button>
        <button class="btn" id="int-tab-catalog" onclick="ViewIntegrations._showTab('catalog')">Catalogo de guias</button>
      </div>
      <div id="int-live"></div>
      <div id="int-content" style="display:none;"></div>
    `;
    this._showTab('live');
  },

  _showTab(tab) {
    document.getElementById('int-live').style.display = tab === 'live' ? '' : 'none';
    document.getElementById('int-content').style.display = tab === 'catalog' ? '' : 'none';
    document.getElementById('int-tab-live').className = tab === 'live' ? 'btn btn-primary' : 'btn';
    document.getElementById('int-tab-catalog').className = tab === 'catalog' ? 'btn btn-primary' : 'btn';
    if (tab === 'live') this._renderLive();
    else this._renderCatalog();
  },

  async _renderLive() {
    const wrap = document.getElementById('int-live');
    if (!wrap) return;
    wrap.innerHTML = `
      <div style="display:grid;gap:20px;">

        <!-- SharePoint -->
        <div class="card" id="sp-card">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
            <div>
              <b style="font-size:15px;">Microsoft SharePoint</b>
              <div style="font-size:11px;color:var(--text-muted);">Importacion masiva de documentos ISMS via Microsoft Graph API</div>
            </div>
            <span id="sp-status-badge" style="margin-left:auto;"></span>
          </div>
          <div id="sp-body">
            <p class="text-muted" style="font-size:13px;">Cargando configuracion...</p>
          </div>
        </div>

        <!-- SSO -->
        <div class="card" id="sso-card">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="8" height="8"/><rect x="13" y="3" width="8" height="8"/>
              <rect x="13" y="13" width="8" height="8"/><rect x="3" y="13" width="8" height="8"/>
            </svg>
            <div>
              <b style="font-size:15px;">SSO — Inicio de sesion corporativo</b>
              <div style="font-size:11px;color:var(--text-muted);">OIDC / OAuth2 — Microsoft Entra ID, Google Workspace, Okta y otros</div>
            </div>
            <span id="sso-status-badge" style="margin-left:auto;"></span>
          </div>
          <div id="sso-body">
            <p class="text-muted" style="font-size:13px;">Cargando configuracion...</p>
          </div>
        </div>

        <!-- SAP / Jagger / Sphera — proximas -->
        <div class="card" style="opacity:.7;">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
            <div>
              <b style="font-size:15px;">SAP / Jagger / Sphera</b>
              <div style="font-size:11px;color:var(--text-muted);">Importacion de proveedores y riesgos desde sistemas ERP y GRC</div>
            </div>
            <span class="badge badge-muted" style="margin-left:auto;">Proximo</span>
          </div>
          <p style="font-size:12px;color:var(--text-muted);margin:0;">
            Importacion de proveedores desde SAP (RFC/OData), sincronizacion de evaluaciones de riesgo
            desde Jagger y exportacion/importacion bidireccional con Sphera. Disponible en v1.4.
            Por ahora puedes usar la importacion CSV en la seccion Proveedores y el catalogo de guias.
          </p>
        </div>

      </div>
    `;
    await Promise.all([this._initSharePoint(), this._initSso()]);
  },

  async _initSharePoint() {
    try {
      const cfg = await Api.sharepoint.getConfig();
      this._renderSharePointBody(cfg);
    } catch (e) {
      document.getElementById('sp-body').innerHTML =
        `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _renderSharePointBody(cfg) {
    const body = document.getElementById('sp-body');
    const badge = document.getElementById('sp-status-badge');
    if (!body) return;

    if (cfg && cfg.configured) {
      badge.innerHTML = `<span class="badge" style="background:var(--risk-low);color:#fff;">Conectado</span>`;
      body.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;font-size:13px;">
          <div><span class="text-muted">Tenant ID:</span> <code>${UI.esc(cfg.tenant_id||'')}</code></div>
          <div><span class="text-muted">Client ID:</span> <code>${UI.esc(cfg.client_id||'')}</code></div>
        </div>
        <div style="display:flex;gap:8px;margin-bottom:16px;">
          <button class="btn btn-sm" onclick="ViewIntegrations._editSpConfig()">Editar credenciales</button>
          <button class="btn btn-sm" onclick="ViewIntegrations._testSp()">Probar conexion</button>
        </div>
        <hr style="border:none;border-top:1px solid var(--border);margin:0 0 16px;">
        <b style="font-size:13px;">Importar documentos desde SharePoint</b>
        <p style="font-size:12px;color:var(--text-muted);margin:4px 0 12px;">
          Selecciona un sitio, una biblioteca y la carpeta que contiene tus documentos ISMS.
          Los archivos PDF, DOCX y TXT se indexaran automaticamente en el agente IA.
        </p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
          <div>
            <label style="font-size:12px;">Sitio</label>
            <select id="sp-site" class="input" style="width:100%;" onchange="ViewIntegrations._loadDrives()">
              <option value="">Cargando sitios...</option>
            </select>
          </div>
          <div>
            <label style="font-size:12px;">Biblioteca</label>
            <select id="sp-drive" class="input" style="width:100%;" onchange="ViewIntegrations._loadFiles('root')">
              <option value="">Selecciona un sitio primero</option>
            </select>
          </div>
        </div>
        <div id="sp-breadcrumb" style="font-size:12px;color:var(--text-muted);margin-bottom:6px;"></div>
        <div id="sp-files" style="min-height:80px;border:1px solid var(--border);border-radius:8px;padding:8px;background:var(--bg-2);"></div>
        <div id="sp-selection" style="margin-top:8px;display:none;align-items:center;gap:8px;flex-wrap:wrap;">
          <span id="sp-sel-count" style="font-size:13px;"></span>
          <select id="sp-cat" class="input" style="width:180px;">
            <option value="other">Categoria: Otro</option>
            <option value="policies">Politicas</option>
            <option value="normative">Normativa</option>
            <option value="risk_assessments">Evaluaciones de riesgo</option>
            <option value="architecture">Arquitectura</option>
            <option value="assets_inventory">Inventario de activos</option>
            <option value="critical_suppliers">Proveedores criticos</option>
            <option value="incidents_lessons">Lecciones de incidentes</option>
          </select>
          <button class="btn btn-primary btn-sm" onclick="ViewIntegrations._importSelected()">
            Importar seleccionados
          </button>
          <button class="btn btn-sm" onclick="ViewIntegrations._clearSelection()">Limpiar</button>
        </div>
      `;
      this._spSelected = [];
      this._spNavStack = [];
      this._loadSites();
    } else {
      badge.innerHTML = `<span class="badge badge-muted">No configurado</span>`;
      body.innerHTML = this._spConfigForm();
    }
  },

  _spConfigForm(prefill) {
    const p = prefill || {};
    return `
      <div class="form-grid" style="margin-bottom:12px;">
        <div class="span2" style="font-size:12px;color:var(--text-muted);">
          Crea un <strong>App Registration</strong> en Azure Portal con permisos de aplicacion
          <code>Sites.Read.All</code> y <code>Files.Read.All</code>,
          luego rellena los campos siguientes.
        </div>
        <div><label style="font-size:12px;">Tenant ID *</label>
          <input id="sp-tenant" class="input" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" value="${UI.esc(p.tenant_id||'')}">
        </div>
        <div><label style="font-size:12px;">Client ID *</label>
          <input id="sp-client" class="input" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" value="${UI.esc(p.client_id||'')}">
        </div>
        <div class="span2"><label style="font-size:12px;">Client Secret *</label>
          <input type="password" id="sp-secret" class="input" placeholder="El secreto del cliente Azure AD">
        </div>
      </div>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-primary" onclick="ViewIntegrations._saveSpConfig()">Guardar y conectar</button>
        ${prefill ? '<button class="btn" onclick="ViewIntegrations._initSharePoint()">Cancelar</button>' : ''}
      </div>
    `;
  },

  _editSpConfig() {
    const body = document.getElementById('sp-body');
    if (body) body.innerHTML = this._spConfigForm({ tenant_id: '(existente)', client_id: '(existente)' });
  },

  async _saveSpConfig() {
    const tenant = document.getElementById('sp-tenant')?.value.trim();
    const client = document.getElementById('sp-client')?.value.trim();
    const secret = document.getElementById('sp-secret')?.value.trim();
    if (!tenant || !client || !secret) {
      UI.toast('Todos los campos son obligatorios', 'error'); return;
    }
    try {
      await Api.sharepoint.saveConfig({ tenant_id: tenant, client_id: client, client_secret: secret });
      UI.toast('Configuracion guardada', 'success');
      await this._initSharePoint();
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  async _testSp() {
    UI.toast('Probando conexion...', 'info');
    try {
      const r = await Api.sharepoint.test();
      UI.toast(r.message, 'success');
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  // ---- SSO ----

  async _initSso() {
    try {
      const cfg = await Api.sso.getConfig();
      this._renderSsoBody(cfg);
    } catch (e) {
      const body = document.getElementById('sso-body');
      if (body) body.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _renderSsoBody(cfg) {
    const body = document.getElementById('sso-body');
    const badge = document.getElementById('sso-status-badge');
    if (!body) return;

    if (cfg && cfg.configured) {
      badge.innerHTML = `<span class="badge" style="background:var(--risk-low);color:#fff;">Activo</span>`;
      body.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px;font-size:13px;">
          <div><span class="text-muted">Issuer:</span><br><code style="font-size:11px;">${UI.esc(cfg.issuer_url||'')}</code></div>
          <div><span class="text-muted">Client ID:</span><br><code style="font-size:11px;">${UI.esc(cfg.client_id||'')}</code></div>
          <div><span class="text-muted">Rol por defecto:</span><br>
            <span class="badge badge-muted">${UI.esc(cfg.default_role||'viewer')}</span>
            ${cfg.auto_provision ? '<span class="badge" style="background:var(--brand-purple);color:#fff;margin-left:4px;">Auto-provision</span>' : ''}
          </div>
        </div>
        ${cfg.allowed_domains ? `<div style="font-size:12px;margin-bottom:12px;"><span class="text-muted">Dominios permitidos:</span> <code>${UI.esc(cfg.allowed_domains)}</code></div>` : ''}
        <div style="display:flex;gap:8px;margin-bottom:8px;">
          <button class="btn btn-sm" onclick="ViewIntegrations._editSsoConfig()">Editar configuracion</button>
          <button class="btn btn-sm" onclick="ViewIntegrations._testSso()">Probar conexion OIDC</button>
          <button class="btn btn-sm btn-danger" onclick="ViewIntegrations._deleteSsoConfig()">Desactivar SSO</button>
        </div>
        <div style="font-size:12px;color:var(--text-muted);">
          URL de callback a configurar en tu proveedor de identidad:
          <code style="font-size:11px;">${UI.esc(cfg.redirect_uri||'')}</code>
        </div>
      `;
    } else {
      badge.innerHTML = `<span class="badge badge-muted">No configurado</span>`;
      body.innerHTML = this._ssoConfigForm();
    }
  },

  _ssoConfigForm(prefill) {
    const p = prefill || {};
    const isEdit = !!prefill;
    return `
      <div class="form-grid" style="margin-bottom:12px;">
        <div class="span2" style="font-size:12px;color:var(--text-muted);">
          Introduce los datos del <strong>App Registration / OAuth2 Client</strong> de tu proveedor de identidad
          (Microsoft Entra ID, Google Workspace, Okta, etc.).<br>
          La URL de callback que debes registrar en el proveedor es:
          <code style="font-size:11px;">${window.location.origin}/api/sso/callback</code>
        </div>
        <div class="span2"><label style="font-size:12px;">Issuer URL *</label>
          <input id="sso-issuer" class="input"
            placeholder="https://login.microsoftonline.com/{tenant-id}/v2.0"
            value="${UI.esc(p.issuer_url||'')}">
        </div>
        <div><label style="font-size:12px;">Client ID *</label>
          <input id="sso-cid" class="input" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" value="${UI.esc(p.client_id||'')}">
        </div>
        <div><label style="font-size:12px;">Client Secret *</label>
          <input type="password" id="sso-secret" class="input" placeholder="${isEdit ? 'Dejar en blanco para no cambiar' : 'Secreto del cliente OAuth2'}">
        </div>
        <div class="span2"><label style="font-size:12px;">Redirect URI (callback) *</label>
          <input id="sso-redirect" class="input"
            value="${UI.esc(p.redirect_uri || (window.location.origin + '/api/sso/callback'))}">
        </div>
        <div><label style="font-size:12px;">Dominios permitidos</label>
          <input id="sso-domains" class="input" placeholder="corp.com,empresa.es  (vacio = sin restriccion)" value="${UI.esc(p.allowed_domains||'')}">
        </div>
        <div><label style="font-size:12px;">Rol por defecto para nuevos usuarios</label>
          <select id="sso-role" class="input">
            ${['viewer','analyst','admin'].map(r =>
              `<option value="${r}" ${(p.default_role||'viewer')===r?'selected':''}>${r}</option>`).join('')}
          </select>
        </div>
        <div class="span2" style="display:flex;align-items:center;gap:10px;">
          <label class="toggle-switch">
            <input type="checkbox" id="sso-provision" ${p.auto_provision?'checked':''}>
            <span class="toggle-slider"></span>
          </label>
          <div>
            <div style="font-size:13px;font-weight:600;">Crear usuarios automaticamente (auto-provision)</div>
            <div style="font-size:11px;color:var(--text-muted);">
              Si esta activado, los usuarios que se autentiquen por SSO y no existan en RiskHub
              seran creados automaticamente con el rol por defecto.
            </div>
          </div>
        </div>
      </div>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-primary" onclick="ViewIntegrations._saveSsoConfig()">Guardar configuracion</button>
        ${isEdit ? '<button class="btn" onclick="ViewIntegrations._initSso()">Cancelar</button>' : ''}
      </div>
    `;
  },

  _editSsoConfig() {
    Api.sso.getConfig().then(cfg => {
      const body = document.getElementById('sso-body');
      if (body) body.innerHTML = this._ssoConfigForm(cfg);
    });
  },

  async _saveSsoConfig() {
    const issuer = document.getElementById('sso-issuer')?.value.trim();
    const cid = document.getElementById('sso-cid')?.value.trim();
    const secret = document.getElementById('sso-secret')?.value.trim();
    const redirect = document.getElementById('sso-redirect')?.value.trim();
    const domains = document.getElementById('sso-domains')?.value.trim();
    const role = document.getElementById('sso-role')?.value;
    const provision = document.getElementById('sso-provision')?.checked || false;
    if (!issuer || !cid || !secret || !redirect) {
      UI.toast('Issuer URL, Client ID, Client Secret y Redirect URI son obligatorios', 'error'); return;
    }
    try {
      const r = await Api.sso.saveConfig({
        issuer_url: issuer, client_id: cid, client_secret: secret,
        redirect_uri: redirect, allowed_domains: domains || null,
        default_role: role, auto_provision: provision,
      });
      UI.toast(r.message, 'success');
      await this._initSso();
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  async _testSso() {
    UI.toast('Probando conexion OIDC...', 'info');
    try {
      const r = await Api.sso.test();
      UI.toast(`${r.message} — Issuer: ${r.issuer || '?'}`, 'success');
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  async _deleteSsoConfig() {
    if (!confirm('Desactivar SSO eliminara la configuracion. Los usuarios que solo usan SSO no podran acceder. ¿Continuar?')) return;
    try {
      await Api.sso.deleteConfig();
      UI.toast('SSO desactivado correctamente', 'success');
      await this._initSso();
    } catch (e) { UI.toast(e.message, 'error'); }
  },

  async _loadSites() {
    const sel = document.getElementById('sp-site');
    if (!sel) return;
    sel.innerHTML = '<option value="">Cargando...</option>';
    try {
      const r = await Api.sharepoint.sites();
      sel.innerHTML = '<option value="">Selecciona un sitio</option>' +
        r.sites.map(s => `<option value="${UI.esc(s.id)}">${UI.esc(s.name)}</option>`).join('');
    } catch (e) { sel.innerHTML = `<option value="">Error: ${UI.esc(e.message)}</option>`; }
  },

  async _loadDrives() {
    const siteId = document.getElementById('sp-site')?.value;
    const driveSel = document.getElementById('sp-drive');
    if (!siteId || !driveSel) return;
    driveSel.innerHTML = '<option value="">Cargando...</option>';
    document.getElementById('sp-files').innerHTML = '';
    try {
      const r = await Api.sharepoint.drives(siteId);
      driveSel.innerHTML = '<option value="">Selecciona una biblioteca</option>' +
        r.drives.map(d => `<option value="${UI.esc(d.id)}">${UI.esc(d.name)}</option>`).join('');
    } catch (e) { driveSel.innerHTML = `<option value="">Error: ${UI.esc(e.message)}</option>`; }
  },

  _spNavStack: [],
  _spSelected: [],

  async _loadFiles(itemId, name) {
    const driveId = document.getElementById('sp-drive')?.value;
    if (!driveId) return;

    // Gestionar breadcrumb
    if (itemId === 'root') {
      this._spNavStack = [];
    } else {
      // Comprobar si ya esta en el stack (navegacion hacia atras)
      const idx = this._spNavStack.findIndex(n => n.id === itemId);
      if (idx >= 0) {
        this._spNavStack = this._spNavStack.slice(0, idx + 1);
      } else {
        this._spNavStack.push({ id: itemId, name: name || itemId });
      }
    }
    this._renderBreadcrumb(driveId);

    const filesDiv = document.getElementById('sp-files');
    filesDiv.innerHTML = '<p class="text-muted" style="padding:8px;">Cargando...</p>';
    try {
      const r = await Api.sharepoint.files(driveId, itemId === 'root' ? null : itemId);
      this._renderFileList(filesDiv, r.items, driveId);
    } catch (e) {
      filesDiv.innerHTML = `<div class="notice">${UI.esc(e.message)}</div>`;
    }
  },

  _renderBreadcrumb(driveId) {
    const bc = document.getElementById('sp-breadcrumb');
    if (!bc) return;
    const parts = [{ id: 'root', name: 'Raiz' }, ...this._spNavStack];
    bc.innerHTML = parts.map((p, i) =>
      i < parts.length - 1
        ? `<a href="#" style="color:var(--brand-purple);" onclick="ViewIntegrations._loadFiles('${UI.esc(p.id)}','${UI.esc(p.name)}');return false;">${UI.esc(p.name)}</a> /`
        : `<span>${UI.esc(p.name)}</span>`
    ).join(' ');
  },

  _renderFileList(container, items, driveId) {
    if (!items.length) {
      container.innerHTML = '<p class="text-muted" style="padding:8px;">Carpeta vacia.</p>';
      return;
    }
    const importable = ['pdf', 'docx', 'txt', 'csv'];
    const rows = items.map(it => {
      const isFile = it.kind === 'file';
      const ext = it.name.split('.').pop().toLowerCase();
      const canImport = isFile && importable.includes(ext);
      const isSelected = this._spSelected.some(s => s.item_id === it.id);
      const sizeStr = isFile ? (it.size > 1048576
        ? (it.size / 1048576).toFixed(1) + ' MB'
        : Math.round(it.size / 1024) + ' KB') : '';

      if (isFile) {
        return `
          <div style="display:flex;align-items:center;gap:8px;padding:6px 4px;
                      border-bottom:1px solid var(--border);font-size:13px;">
            ${canImport
              ? `<input type="checkbox" ${isSelected ? 'checked' : ''}
                   onchange="ViewIntegrations._toggleFile(this,'${UI.esc(it.id)}','${UI.esc(it.name)}','${UI.esc(driveId)}','${UI.esc(it.mime||'')}')">`
              : `<span style="width:16px;"></span>`}
            <span style="color:var(--text-muted);">
              ${canImport ? ext.toUpperCase() : '—'}
            </span>
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
              title="${UI.esc(it.name)}">${UI.esc(it.name)}</span>
            <span style="color:var(--text-muted);font-size:11px;flex-shrink:0;">${sizeStr}</span>
            ${!canImport ? `<span style="font-size:11px;color:var(--text-subtle);">(no soportado)</span>` : ''}
          </div>`;
      } else {
        return `
          <div style="display:flex;align-items:center;gap:8px;padding:6px 4px;
                      border-bottom:1px solid var(--border);font-size:13px;cursor:pointer;"
               onclick="ViewIntegrations._loadFiles('${UI.esc(it.id)}','${UI.esc(it.name)}')">
            <span style="color:var(--brand-purple);">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
            </span>
            <span style="flex:1;">${UI.esc(it.name)}</span>
            <span style="font-size:11px;color:var(--text-muted);">${it.child_count} elementos</span>
            <span style="font-size:11px;color:var(--brand-purple);">Abrir</span>
          </div>`;
      }
    }).join('');

    const totalImportable = items.filter(it => {
      const ext = it.name.split('.').pop().toLowerCase();
      return it.kind === 'file' && ['pdf','docx','txt','csv'].includes(ext);
    }).length;

    container.innerHTML = `
      <div style="padding:4px 4px 6px;display:flex;gap:8px;align-items:center;font-size:12px;color:var(--text-muted);">
        <label style="display:flex;align-items:center;gap:4px;cursor:pointer;">
          <input type="checkbox" id="sp-check-all"
            onchange="ViewIntegrations._toggleAll(this,'${UI.esc(driveId)}',${JSON.stringify(
              items.filter(it => ['pdf','docx','txt','csv'].includes(it.name.split('.').pop().toLowerCase()) && it.kind==='file')
                   .map(it => ({item_id: it.id, name: it.name, drive_id: driveId, mime: it.mime||''}))
            ).replace(/"/g,'&quot;')})">
          Seleccionar todos importables (${totalImportable})
        </label>
      </div>
      ${rows}
    `;
  },

  _toggleFile(chk, itemId, name, driveId, mime) {
    if (chk.checked) {
      if (!this._spSelected.some(s => s.item_id === itemId))
        this._spSelected.push({ item_id: itemId, name, drive_id: driveId, mime });
    } else {
      this._spSelected = this._spSelected.filter(s => s.item_id !== itemId);
    }
    this._updateSelectionBar();
  },

  _toggleAll(chk, driveId, items) {
    if (chk.checked) {
      items.forEach(it => {
        if (!this._spSelected.some(s => s.item_id === it.item_id))
          this._spSelected.push(it);
      });
    } else {
      const ids = new Set(items.map(i => i.item_id));
      this._spSelected = this._spSelected.filter(s => !ids.has(s.item_id));
    }
    this._updateSelectionBar();
  },

  _updateSelectionBar() {
    const bar = document.getElementById('sp-selection');
    const cnt = document.getElementById('sp-sel-count');
    if (!bar || !cnt) return;
    if (this._spSelected.length > 0) {
      bar.style.display = 'flex';
      cnt.textContent = `${this._spSelected.length} archivo(s) seleccionado(s)`;
    } else {
      bar.style.display = 'none';
    }
  },

  _clearSelection() {
    this._spSelected = [];
    this._updateSelectionBar();
    document.querySelectorAll('#sp-files input[type=checkbox]').forEach(c => c.checked = false);
    const all = document.getElementById('sp-check-all');
    if (all) all.checked = false;
  },

  async _importSelected() {
    if (!this._spSelected.length) { UI.toast('Selecciona al menos un archivo', 'error'); return; }
    const cat = document.getElementById('sp-cat')?.value || 'other';
    const btn = document.querySelector('#sp-selection .btn-primary');
    if (btn) { btn.disabled = true; btn.textContent = 'Importando...'; }
    try {
      const r = await Api.sharepoint.importFiles(this._spSelected, cat);
      UI.toast(`Importados: ${r.imported.length} | Omitidos: ${r.skipped.length} | Errores: ${r.errors.length}`, 'success');
      this._clearSelection();
    } catch (e) {
      UI.toast(e.message, 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = 'Importar seleccionados'; }
    }
  },

  _renderCatalog() {
    const cats = this._categories();
    const catIcons = {
      'Gestión de activos': '🗄️',
      'Gestión de vulnerabilidades': '🔍',
      'Gestión de riesgos de terceros': '🤝',
      'SIEM / Operaciones de seguridad': '🛡️',
      'Identidad y acceso': '🔑',
      'Seguridad cloud': '☁️',
    };

    let html = `
      <div class="card" style="margin-bottom:16px;background:linear-gradient(135deg,var(--brand-purple-4),var(--brand-orange-4));border:1px solid var(--brand-purple-3);">
        <p style="margin:0;font-size:14px;color:var(--text-base);">
          <strong>Catálogo de integraciones:</strong> ${this._catalog.length} herramientas del mercado de seguridad y GRC,
          con guías paso a paso para sincronizar datos con RiskHub.
          Las integraciones automatizadas están en el roadmap de v1.2.
          Por ahora, sigue las guías para importar datos manualmente o semi-automáticamente.
        </p>
      </div>`;

    Object.entries(cats).forEach(([cat, tools]) => {
      html += `<div class="card" style="margin-bottom:16px;">
        <h3 style="margin-bottom:16px;">${catIcons[cat] || '🔧'} ${cat}</h3>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;">`;

      tools.forEach(tool => {
        html += `
          <div style="background:var(--bg-2);border:1px solid var(--border);border-radius:10px;
                      padding:16px;display:flex;flex-direction:column;gap:8px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
              <strong style="font-size:14px;line-height:1.3;">${UI.esc(tool.name)}</strong>
              <span class="badge badge-muted" style="font-size:10px;white-space:nowrap;flex-shrink:0;">
                ${UI.esc(tool.api.split('(')[0].trim())}
              </span>
            </div>
            <p style="font-size:12px;color:var(--text-muted);margin:0;line-height:1.5;">
              ${UI.esc(tool.description)}
            </p>
            <p style="font-size:11px;color:var(--text-muted);margin:0;">
              <strong>Datos:</strong> ${UI.esc(tool.data)}
            </p>
            <div style="margin-top:4px;">
              <button class="btn btn-sm btn-primary" style="width:100%;"
                onclick="ViewIntegrations._openGuide('${tool.id}')">
                Ver guía de integración
              </button>
            </div>
          </div>`;
      });

      html += `</div></div>`;
    });

    document.getElementById('int-content').innerHTML = html;
  },

  _openGuide(toolId) {
    const tool = this._catalog.find(t => t.id === toolId);
    if (!tool) return;

    const stepsHtml = tool.steps.map((s, i) =>
      `<div style="display:flex;gap:12px;margin-bottom:10px;">
        <span style="background:var(--brand-purple);color:#fff;border-radius:50%;
                     width:22px;height:22px;flex-shrink:0;display:flex;align-items:center;
                     justify-content:center;font-size:11px;font-weight:700;margin-top:2px;">${i + 1}</span>
        <p style="margin:0;font-size:13px;line-height:1.5;color:var(--text-base);">${UI.esc(s)}</p>
      </div>`
    ).join('');

    const modalHtml = `
      <div class="modal-head">
        <h2 style="font-size:16px;">Guía de integración — ${UI.esc(tool.name)}</h2>
        <button class="btn btn-ghost btn-sm" onclick="UI.closeModal()">✕</button>
      </div>
      <div style="overflow-y:auto;max-height:70vh;padding:4px 0;">
        <div style="margin-bottom:16px;display:grid;gap:6px;">
          <div style="background:var(--bg-2);border-radius:8px;padding:12px 14px;">
            <p style="margin:0 0 4px;font-size:11px;text-transform:uppercase;color:var(--text-muted);font-weight:600;">
              Datos que aporta</p>
            <p style="margin:0;font-size:13px;">${UI.esc(tool.data)}</p>
          </div>
          <div style="background:var(--bg-2);border-radius:8px;padding:12px 14px;">
            <p style="margin:0 0 4px;font-size:11px;text-transform:uppercase;color:var(--text-muted);font-weight:600;">
              API / Protocolo</p>
            <p style="margin:0;font-size:13px;">${UI.esc(tool.api)}</p>
          </div>
          <div style="background:var(--bg-2);border-radius:8px;padding:12px 14px;">
            <p style="margin:0 0 4px;font-size:11px;text-transform:uppercase;color:var(--text-muted);font-weight:600;">
              Autenticación</p>
            <p style="margin:0;font-size:13px;">${UI.esc(tool.auth)}</p>
          </div>
          <div style="background:var(--brand-purple-4);border:1px solid var(--brand-purple-3);border-radius:8px;padding:12px 14px;">
            <p style="margin:0 0 4px;font-size:11px;text-transform:uppercase;color:var(--brand-purple);font-weight:600;">
              Referencia ISO 27005</p>
            <p style="margin:0;font-size:13px;">${UI.esc(tool.iso_mapping)}</p>
          </div>
        </div>
        <h4 style="margin:0 0 12px;font-size:13px;text-transform:uppercase;
                   color:var(--text-muted);letter-spacing:.5px;">Pasos de integración manual</h4>
        ${stepsHtml}
        <div style="margin-top:16px;background:var(--brand-orange-4);border:1px solid var(--brand-orange-3);
                    border-radius:8px;padding:12px 14px;">
          <p style="margin:0;font-size:12px;color:var(--text-base);">
            <strong>Próximamente:</strong> La integración automatizada estará disponible en RiskHub v1.2.
            Incluirá sincronización programada, mapeo configurable de campos y asociación automática
            de vulnerabilidades a riesgos mediante IA.
          </p>
        </div>
      </div>`;

    UI.openModal(modalHtml, { width: '640px' });
  },
};
