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
      'Catálogo de herramientas y guías de conexión con RiskHub'
    ) + '<div id="int-content"></div>';
    this._renderCatalog();
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
