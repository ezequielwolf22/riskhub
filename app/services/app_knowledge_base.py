"""
Base de conocimiento funcional de RiskHub.
Proporciona documentacion interna sobre flujos, configuraciones y metodologias
para que el agente IA pueda responder preguntas funcionales de los usuarios.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Estructura: cada entrada tiene:
#   keywords: palabras clave que activan esta seccion (minusculas)
#   title:    titulo de la seccion
#   content:  documentacion detallada en castellano
# ---------------------------------------------------------------------------

_KNOWLEDGE: list[dict] = [

    # ------------------------------------------------------------------
    # GESTION DE RIESGOS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "riesgo", "riesgos", "calcul", "matriz", "nivel", "inherente", "residual",
            "apetito", "iso 27005", "likelihood", "consequence", "probabilidad", "impacto",
            "tratamiento", "modificacion", "retencion", "evitacion", "transferencia", "sharing",
            "avoidance", "retention", "modification", "5x5",
        ],
        "title": "Gestion de riesgos — metodologia y calculo",
        "content": """
## Gestion de riesgos — metodologia y calculo

### Metodologias disponibles
RiskHub soporta dos metodologias de calculo de riesgo configurables desde Contexto > Metodologia:
- **ISO 27005**: matriz 5x5 (consecuencia x probabilidad) con escala 0-8.
- **MAGERIT v3**: valoracion de activos por dimensiones CIA (Confidencialidad, Integridad, Disponibilidad,
  Autenticidad, Trazabilidad); el nivel de riesgo se calcula como frecuencia de amenaza x degradacion del activo.
- **Modo combinado**: estructura ISO 27005 con valores MAGERIT y seguimiento por dimension.

### Matriz de calculo ISO 27005 (Annex E.2)
La matriz 5x5 combina consecuencia (0-4) y probabilidad (0-4) para producir un nivel de riesgo de 0-8:
- Nivel 0-2: BAJO
- Nivel 3-4: MEDIO
- Nivel 5-6: ALTO
- Nivel 7-8: CRITICO

### Riesgo inherente vs residual
- **Riesgo inherente**: nivel de riesgo SIN aplicar controles existentes.
- **Riesgo residual**: nivel de riesgo DESPUES de aplicar los controles implementados.
  El motor recalcula el residual aplicando la reduccion aportada por controles implementados
  con madurez >= 3.

### Opciones de tratamiento
Cuando el nivel residual supera el apetito de riesgo configurado:
- **Modificacion (mitigar)**: implementar controles adicionales.
- **Retencion (aceptar)**: aceptar el riesgo conscientemente, requiere justificacion.
- **Evitacion**: eliminar la actividad que origina el riesgo.
- **Transferencia/Comparticion**: seguro cibernetico, outsourcing con SLA.

El sistema asigna automaticamente 'modificacion' cuando el residual > apetito, y permite
al analista cambiar la opcion con justificacion documentada.

### Flujo de creacion de un riesgo
1. Ir a Riesgos > Nuevo riesgo.
2. Seleccionar activo, amenaza (catalogo ISO 27005 con 49 amenazas) y vulnerabilidad (67 en catalogo).
3. El motor calcula automaticamente inherente y residual.
4. Asignar tratamiento, responsable y fecha objetivo.
5. Opcionalmente vincular controles ISO 27002 del catalogo de 93 controles.
6. El estado evoluciona: identified > assessed > treated > monitored > closed.

### Deteccion de duplicados
Al crear un riesgo, el sistema detecta automaticamente riesgos similares (mismo activo + amenaza)
y devuelve HTTP 409 con los candidatos para evitar duplicidad.
""",
    },

    # ------------------------------------------------------------------
    # AMENAZAS Y VULNERABILIDADES
    # ------------------------------------------------------------------
    {
        "keywords": [
            "amenaza", "amenazas", "vulnerabilidad", "vulnerabilidades", "catalogo",
            "cruce", "activo", "vinculacion", "asociar", "linkage",
        ],
        "title": "Amenazas, vulnerabilidades y su vinculacion con riesgos",
        "content": """
## Amenazas, vulnerabilidades y su vinculacion con riesgos

### Catalogos precargados
- **49 amenazas ISO 27005** clasificadas por categoria (natural, humana-accidental, humana-intencional, tecnica).
- **67 vulnerabilidades** alineadas con ISO 27005 Annex D.

### Como se cruzan los riesgos con amenazas
Cada riesgo tiene exactamente:
- 1 activo afectado (o sugerencia de activo si no existe aun).
- 1 amenaza del catalogo (campo `threat_code`, ej. T-H5 para 'Acceso no autorizado').
- 1 descripcion de vulnerabilidad explotada.
- 1 dimension MAGERIT afectada (confidencialidad, integridad, disponibilidad, autenticidad, trazabilidad).
- N controles ISO 27002 vinculados como mitigacion.

El analisis IA automatico (boton 'Analizar con IA') genera escenarios de riesgo completos
cruzando activos del inventario con amenazas del catalogo y sugiriendo controles pertinentes.

### Gestionar amenazas personalizadas
Ademas del catalogo precargado, se pueden crear amenazas propias desde Amenazas > Nueva amenaza.
Estas se integran con el motor de calculo igual que las del catalogo.

### Ver riesgos por activo o por amenaza
- En la vista Activos, cada activo muestra el badge de riesgos asociados.
- En la vista Amenazas, se puede ver cuantos riesgos activos referencian cada amenaza.
- El heatmap (vista Heatmap) muestra la distribucion de riesgos en la matriz probabilidad x impacto.
""",
    },

    # ------------------------------------------------------------------
    # ACTIVOS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "activo", "activos", "inventario", "asset", "tipo de activo", "primario",
            "soporte", "propietario activo", "valoracion activo", "activo informacion",
        ],
        "title": "Gestion de activos de informacion",
        "content": """
## Gestion de activos de informacion

### Tipos de activos (ISO 27005)
- **Activos primarios de informacion**: datos personales, informacion financiera, propiedad intelectual.
- **Activos primarios de proceso**: procesos de negocio criticos.
- **Activos de soporte**: hardware, software, infraestructura de red, servicios externos, RRHH, instalaciones.

### Valoracion CIA
Cada activo se valora en tres dimensiones de 0-4:
- **Confidencialidad**: impacto si la informacion es divulgada sin autorizacion.
- **Integridad**: impacto si la informacion es modificada sin autorizacion.
- **Disponibilidad**: impacto si el activo no esta disponible cuando se necesita.

La valoracion determina el peso del activo en el calculo de riesgo.

### Flujo de creacion
1. Ir a Activos > Nuevo activo.
2. Asignar codigo unico, nombre, tipo y propietario.
3. Valorar CIA (0-4).
4. Opcionalmente relacionar con documentos del SGSI (el sistema detecta menciones del nombre del activo
   en documentos indexados y los vincula automaticamente).

### Integracion con SGSI (ISMS)
Cuando se indexa un documento en IA > Documentos, el sistema analiza el texto y vincula automaticamente
los activos cuyo nombre aparece en el documento. Los activos muestran el badge 'Documentado'.
Cuando se actualiza un control vinculado al activo, se desencadena un re-analisis automatico.
""",
    },

    # ------------------------------------------------------------------
    # CONTROLES ISO 27002
    # ------------------------------------------------------------------
    {
        "keywords": [
            "control", "controles", "iso 27002", "implementacion", "madurez", "gap",
            "soa", "statement of applicability", "declaracion de aplicabilidad",
            "gap analysis", "dominio", "organizacional", "personas", "fisico", "tecnologico",
        ],
        "title": "Controles ISO 27002:2022 — implementacion y gap analysis",
        "content": """
## Controles ISO 27002:2022 — implementacion y gap analysis

### Catalogo de controles
93 controles ISO 27002:2022 organizados en 4 dominios:
- **5. Controles Organizacionales** (37 controles): politicas, roles, gestion de activos, etc.
- **6. Controles de Personas** (8 controles): seleccion, formacion, acuerdos de confidencialidad.
- **7. Controles Fisicos** (14 controles): perimetros fisicos, acceso fisico, medios.
- **8. Controles Tecnologicos** (34 controles): autenticacion, cifrado, gestion de vulnerabilidades, etc.

### Niveles de madurez (escala 1-5)
- 1 — Inicial: control inexistente o ad-hoc.
- 2 — Repetible: proceso existe pero no documentado.
- 3 — Definido: proceso documentado y estandarizado.
- 4 — Gestionado: se mide y controla.
- 5 — Optimizado: mejora continua, automatizado.

### Gap Analysis
Disponible en IA > Control Gap Analysis. El sistema:
1. Compara controles implementados vs requeridos por los frameworks activos.
2. Usa Claude para analizar brechas y priorizar por criticidad.
3. Genera un informe con controles faltantes, nivel de madurez actual vs objetivo, y acciones recomendadas.

### Statement of Applicability (SoA)
En Compliance > SoA se declara cada control como aplicable/no aplicable con justificacion.
Cuando Regwatch detecta un cambio normativo, los controles afectados se marcan para revision
y aparecen en el campo `regwatch_review_at`.

### Degradacion automatica
El scheduler de RiskHub revisa periodicamente los controles con madurez baja (<=2) y genera
alertas de degradacion. Los controles no implementados se destacan en el dashboard.
""",
    },

    # ------------------------------------------------------------------
    # PROVEEDORES / TPRM
    # ------------------------------------------------------------------
    {
        "keywords": [
            "tprm", "third party risk", "cuestionario tprm", "scoring tprm",
            "supply chain", "cadena suministro", "tier", "due diligence",
            "gestion proveedores", "evaluacion tprm", "plantilla tprm",
        ],
        "title": "Gestion de proveedores y TPRM",
        "content": """
## Gestion de proveedores y TPRM (Third-Party Risk Management)

### Flujo de gestion de proveedores
1. **Alta**: Proveedores > Nuevo proveedor. Asignar nombre, categoria, pais, contacto.
2. **Clasificacion**: el sistema calcula automaticamente el riesgo inherente segun el tipo de proveedor,
   datos accedidos, criticidad de servicios y presencia regulatoria.
3. **Tiering** (§4.3): el motor TPRM asigna Tier 1 (critico), Tier 2 (importante) o Tier 3 (estandar).
4. **Cuestionario de seguridad**: enviar plantilla predefinida o personalizada para que el proveedor responda.
5. **Evaluacion consolidada**: VendorAssessment calcula score por dominio y score global.
6. **Scoring residual** (§5.2): combina inherente + respuestas del cuestionario + issues abiertos.
7. **Aprobacion**: el evaluador aprueba la evaluacion y puede empujar el riesgo al registro ISO 27005.

### Ciclo de vida del proveedor
Etapas: prospect > due_diligence > onboarding > active > under_review > offboarding > terminated.
El sistema permite registrar la fecha de inicio y vencimiento del contrato.

### Plantillas de cuestionario (7 predefinidas)
1. Seguridad general (ISO 27001)
2. Proveedores cloud / SaaS
3. Proveedores con acceso a datos personales (GDPR)
4. Infraestructura critica (NIS2)
5. Servicios financieros (DORA)
6. Desarrollo de software
7. BCP / Continuidad

Cada plantilla mapea sus preguntas a controles ISO 27002. Se pueden clonar y personalizar.

### Evaluacion IA automatica
Cuando un proveedor responde un cuestionario, se puede disparar una evaluacion IA
(POST /api/supplier-questionnaires/{id}/ai-review) que analiza las respuestas con guardrails,
detecta respuestas inconsistentes y genera un resumen de riesgo con hallazgos priorizados.

### Riesgo automatico de supply chain
Si el score residual de un proveedor baja de 30 puntos, RiskHub crea automaticamente
un riesgo de cadena de suministro con metodologia ISO 27005, vinculado al proveedor.

### Flags regulatorios
- **Procesador GDPR Art.28**: proveedor que trata datos personales — requiere DPA.
- **Sujeto NIS2**: incluido en cadena de suministro critica NIS2.
- **ICT DORA**: proveedor ICT critico segun DORA — requiere evaluacion periodica.
- **Concentracion DORA**: proveedor que supera el 40% de procesos criticos.

### VendorIssues (hallazgos)
Los hallazgos se crean automaticamente desde evaluaciones o manualmente.
Severidad: critical (SLA 48h), high (7 dias), medium (30 dias), low (90 dias).
El vencimiento del SLA se calcula automaticamente y genera alertas.
""",
    },

    # ------------------------------------------------------------------
    # SSO
    # ------------------------------------------------------------------
    {
        "keywords": [
            "sso", "saml", "oidc", "oauth", "entra", "azure ad", "google", "okta",
            "autenticacion", "single sign-on", "inicio de sesion", "identity provider", "idp",
        ],
        "title": "Configuracion SSO (OIDC/SAML)",
        "content": """
## Configuracion SSO (Single Sign-On)

RiskHub soporta SSO via OIDC y SAML 2.0 con los principales proveedores de identidad.
La configuracion se realiza en **Integraciones > SSO** (requiere rol admin).

### Proveedores soportados
- **Microsoft Entra ID (Azure AD)**: OIDC o SAML.
- **Google Workspace**: OIDC.
- **Okta**: OIDC o SAML.
- **Cualquier IdP compatible**: mediante OIDC generico.

### Pasos para configurar SSO con Entra ID (OIDC)
1. En Azure Portal > App registrations > New registration.
   - Nombre: RiskHub (o cualquier nombre descriptivo).
   - Redirect URI: https://TU-DOMINIO/api/sso/oidc/callback
2. Anota el **Client ID** y el **Tenant ID**.
3. En Certificates & secrets > New client secret — copia el valor inmediatamente.
4. En RiskHub > Integraciones > SSO:
   - Seleccionar proveedor: Entra ID.
   - Pegar Client ID, Client Secret y Tenant ID.
   - Activar SSO.
5. Los usuarios se crean automaticamente en RiskHub la primera vez que se autentican via SSO.
   El rol inicial asignado es 'viewer' — el admin puede cambiarlo desde Usuarios.

### Pasos para configurar SSO con Google
1. En Google Cloud Console > APIs & Services > Credentials > Create OAuth 2.0 Client.
   - Application type: Web application.
   - Authorized redirect URI: https://TU-DOMINIO/api/sso/oidc/callback
2. Anota Client ID y Client Secret.
3. En RiskHub > Integraciones > SSO:
   - Proveedor: Google.
   - Pegar credenciales y activar.

### Pasos para configurar SSO con Okta (SAML)
1. En Okta Admin Console > Applications > Create App Integration > SAML 2.0.
   - Single sign-on URL: https://TU-DOMINIO/api/sso/saml/acs
   - Audience URI: https://TU-DOMINIO
2. Descarga el metadata XML del IdP.
3. En RiskHub > Integraciones > SSO:
   - Proveedor: Okta (SAML).
   - Pega el metadata XML o la URL del metadata.

### Boton SSO en login
Una vez configurado y activado, aparece el boton 'Iniciar sesion con [Proveedor]' en la pantalla
de login. Los usuarios existentes que tengan el mismo email que el IdP se vinculan automaticamente.

### Notas de seguridad
- Las credenciales del IdP (client_secret, certificados SAML) se cifran con Fernet antes de persistirse.
- El flujo OIDC usa PKCE para proteger contra ataques de interception.
- Los tokens JWT de sesion se emiten con la misma duracion que en autenticacion local.
""",
    },

    # ------------------------------------------------------------------
    # SHAREPOINT
    # ------------------------------------------------------------------
    {
        "keywords": [
            "sharepoint", "microsoft", "onedrive", "documentos", "biblioteca", "site",
            "office 365", "m365",
        ],
        "title": "Configuracion SharePoint",
        "content": """
## Configuracion SharePoint / Microsoft 365

RiskHub puede conectarse a SharePoint Online para explorar y referenciar documentos del SGSI
directamente desde la plataforma. Se configura en **Integraciones > SharePoint** (requiere rol admin).

### Requisitos previos
- Tenant de Microsoft 365 con SharePoint Online activo.
- Permisos para registrar una App en Azure AD.

### Pasos de configuracion
1. En Azure Portal > App registrations > New registration.
   - Nombre: RiskHub SharePoint.
   - Redirect URI: no necesaria (flujo client credentials).
2. En API permissions > Add permission > Microsoft Graph:
   - Sites.Read.All (Application permission) — para leer sitios y documentos.
   - Files.Read.All (Application permission).
   - Hacer clic en 'Grant admin consent'.
3. En Certificates & secrets > New client secret — copia el valor.
4. Anota: Tenant ID, Client ID, Client Secret.
5. En RiskHub > Integraciones > SharePoint:
   - Pegar Tenant ID, Client ID y Client Secret.
   - Introducir la URL del sitio SharePoint (ej. https://EMPRESA.sharepoint.com/sites/SGSI).
   - Guardar y probar conexion.

### Uso del file browser
Una vez configurado, aparece el boton 'Explorar SharePoint' en Integraciones > SharePoint.
Permite navegar la jerarquia de carpetas y seleccionar documentos para referenciar o importar.
Los documentos seleccionados se pueden indexar directamente en el motor RAG del agente IA.

### Seguridad
- Las credenciales de SharePoint se cifran con Fernet en la base de datos.
- El acceso es de solo lectura (Sites.Read.All, Files.Read.All).
- Todo acceso queda registrado en el log de auditoria de RiskHub.
""",
    },

    # ------------------------------------------------------------------
    # INTEGRACIONES ERP / WEBHOOKS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "erp", "webhook", "sap", "jagger", "sphera", "hmac", "integracion",
            "evento", "payload", "activo automatico", "incidente automatico",
        ],
        "title": "Integraciones ERP y webhooks",
        "content": """
## Integraciones ERP y Webhooks

### ERP Webhooks (Integraciones > ERP Webhooks)
RiskHub recibe eventos de sistemas ERP externos via webhooks firmados con HMAC-SHA256.
Sistemas preconfigurados: SAP, Jagger, Sphera.

### Como funciona
1. El sistema externo envia un POST a https://TU-DOMINIO/api/integrations/erp/webhook/{source}
2. La cabecera `X-RiskHub-Signature` contiene el HMAC-SHA256 del body firmado con el secret configurado.
3. RiskHub verifica la firma, rechazando payloads sin firma valida.
4. Segun el tipo de evento, se crean o actualizan automaticamente activos o incidentes.

### Tipos de evento soportados
- `asset.created` / `asset.updated`: sincroniza activos de inventario.
- `incident.created`: crea un incidente de seguridad vinculado al activo.
- `risk.change`: actualiza el nivel de riesgo de un activo existente.

### Configuracion
1. En Integraciones > ERP Webhooks > Nuevo conector.
2. Seleccionar sistema (SAP / Jagger / Sphera / Custom).
3. Introducir el webhook secret (minimo 32 caracteres).
4. Copiar la URL de endpoint generada y configurarla en el sistema externo.
5. El log de eventos recibidos esta disponible en la misma pantalla.

### Seguridad
- El secret se almacena cifrado con Fernet.
- Se rechaza cualquier request sin firma valida o con firma incorrecta.
- Log completo de cada evento recibido (timestamp, source, tipo, resultado).

### Webhooks salientes
RiskHub tambien puede enviar webhooks salientes cuando ocurren eventos internos
(nuevo riesgo critico, incidente CRITICAL, vencimiento de control, etc.).
Se configuran en Integraciones > Webhooks Salientes con URL de destino y secret HMAC.
""",
    },

    # ------------------------------------------------------------------
    # AGENTE IA — CONFIGURACION Y FLUJOS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "agente", "ia", "inteligencia artificial", "api key", "anthropic", "claude",
            "rag", "documentos", "embeddings", "voyage", "chat", "configurar ia",
            "modelo", "anonimizacion", "anonymization",
        ],
        "title": "Agente IA — configuracion y flujos",
        "content": """
## Agente IA de RiskHub — configuracion y flujos

### Configuracion inicial
El agente IA requiere una API key de Anthropic. Se configura en **IA > Configuracion del Agente**:
1. Obtener API key en console.anthropic.com.
2. Pegar la clave en el campo 'API Key de Anthropic'. Se cifra con Fernet antes de guardarse.
3. (Opcional) Configurar API key de Voyage AI para activar busqueda semantica vectorial avanzada.
4. Seleccionar el modelo (por defecto claude-opus-4-6 — maxima capacidad; claude-haiku-4-5 para
   respuestas rapidas con menor coste).
5. Configurar nivel de anonimizacion de PII:
   - **Bajo**: sin anonimizacion.
   - **Medio**: IPs, emails y dominios enmascarados ([IP_1], [EMAIL_2]).
   - **Alto**: tambien telefonos, DNI, IBAN y nombres propios.
6. Guardar y usar el boton 'Probar conexion' para verificar.

### Indexacion de documentos
1. Ir a IA > Documentos.
2. Subir el documento (PDF, Word, TXT, Excel — maximo 50 MB). Se valida con magic bytes.
3. El sistema extrae el texto, lo divide en fragmentos (chunks) y los indexa en FTS5.
4. Si hay API key de Voyage AI configurada, genera embeddings vectoriales para busqueda semantica.
5. El documento queda disponible para el agente en las conversaciones del chat.

### Como funciona el RAG (busqueda en documentos)
Cuando el usuario hace una pregunta en el chat:
1. El sistema busca fragmentos relevantes en los documentos indexados usando dos estrategias:
   - **Semantica (Voyage AI)**: compara el embedding de la pregunta con los embeddings de los fragmentos.
   - **FTS5 (palabra clave)**: busqueda de texto completo con expansion bilingue ES/EN.
2. Los fragmentos mas relevantes se inyectan en el contexto del agente.
3. El agente puede citar la fuente textualmente en su respuesta.

### Analisis automatico de riesgos (IA > Analizar)
El agente genera escenarios de riesgo completos basados en:
- El cuestionario organizacional (sector, empleados, normativas aplicables, sistemas, etc.).
- El inventario de activos existente.
- El catalogo de amenazas y vulnerabilidades.
- Los controles implementados actuales.
El resultado se importa al registro de riesgos con un solo clic.

### Analisis de documentos (ISMS)
Los documentos subidos se analizan automaticamente para:
- Extraer referencias a clausulas ISO 27001/27002 (con Claude Haiku).
- Vincular el documento a los activos cuyo nombre aparece en el texto.
- Calcular un score de cobertura del SGSI.

### Herramientas del agente (acciones propuestas)
El agente puede proponer acciones que el usuario debe CONFIRMAR antes de ejecutar:
- Crear tarea de tratamiento de riesgo.
- Cambiar el estado de un riesgo.
- Registrar un nuevo incidente.
- Programar revision urgente de un control.

### Feedback y mejora continua
El usuario puede valorar cada respuesta del agente (1-5 estrellas). El feedback se almacena
y puede usarse para ajustar el comportamiento del agente en futuras sesiones.
""",
    },

    # ------------------------------------------------------------------
    # INCIDENTES
    # ------------------------------------------------------------------
    {
        "keywords": [
            "incidente", "incidentes", "gestion de incidentes", "severidad", "estado",
            "open", "investigating", "contained", "resolved", "closed", "registro",
        ],
        "title": "Gestion de incidentes de seguridad",
        "content": """
## Gestion de incidentes de seguridad

### Flujo de un incidente
1. **Registro**: Incidentes > Nuevo incidente. Campos: titulo, descripcion, severidad, activo afectado.
2. **Severidades**: critical, high, medium, low, informational.
3. **Estados del ciclo de vida**: open > investigating > contained > resolved > closed.
4. **Auto-linkage**: al crear un incidente sobre un activo, el sistema vincula automaticamente
   los riesgos activos asociados a ese activo.
5. **Tareas de respuesta**: se pueden crear tareas de respuesta al incidente directamente desde el incidente.
6. **Informe post-incidente**: al cerrar un incidente, el sistema solicita un analisis de causa raiz.

### Auto-creacion desde OSINT
Si el modulo OSINT detecta hallazgos CRITICAL o HIGH en el escaneo de dominio/email/IP,
crea automaticamente un incidente con la informacion del hallazgo y el activo relacionado.

### Metricas de incidentes
El dashboard muestra: MTTD (Mean Time to Detect), MTTR (Mean Time to Respond),
distribucion por severidad y tendencia mensual.
""",
    },

    # ------------------------------------------------------------------
    # NO CONFORMIDADES
    # ------------------------------------------------------------------
    {
        "keywords": [
            "no conformidad", "no conformidades", "nc", "nonconformity", "auditoria interna",
            "hallazgo", "accion correctiva", "iso 27001", "accion preventiva",
        ],
        "title": "No conformidades y acciones correctivas",
        "content": """
## No conformidades y acciones correctivas

### Que es una no conformidad
Incumplimiento de un requisito del SGSI (ISO 27001 clausula 10.1). Puede originarse en:
- Auditorias internas o externas.
- Revision por la direccion.
- Hallazgos de controles fallidos.
- Incidentes de seguridad.

### Flujo de gestion
1. **Registro**: No Conformidades > Nueva NC. Campos: titulo, descripcion, severidad (critical/major/minor/observation),
   clausula ISO 27001 afectada, activo relacionado.
2. **Auto-linkage**: al crear una NC sobre un activo, se vinculan automaticamente los riesgos activos del activo.
3. **Accion correctiva**: documentar la causa raiz (metodologia 5-WHY disponible) y las acciones correctivas.
4. **Seguimiento**: asignar responsable, fecha objetivo, y verificar eficacia.
5. **Estados**: open > in_progress > pending_verification > closed.
6. **Cierre**: requiere evidencia de la correccion y verificacion de eficacia.

### Severidades
- **Critical**: riesgo inmediato a la confidencialidad, integridad o disponibilidad.
- **Major**: incumplimiento sistematico de un requisito ISO 27001.
- **Minor**: desviacion puntual o incompleta implementacion.
- **Observation**: area de mejora identificada (no es no conformidad).
""",
    },

    # ------------------------------------------------------------------
    # POLITICAS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "politica", "politicas", "policy", "revision", "aprobacion", "ciclo de vida",
            "documentacion", "propietario", "vencimiento",
        ],
        "title": "Gestion de politicas de seguridad",
        "content": """
## Gestion de politicas de seguridad

### Tipos de politicas
- Politica de Seguridad de la Informacion (PSI) — nivel estrategico.
- Politicas operativas: control de acceso, gestion de contraseñas, uso aceptable, BCP, etc.
- Procedimientos: instrucciones tecnicas de implementacion.
- Guias y estandares.

### Flujo de gestion
1. **Creacion**: Politicas > Nueva politica. Asignar: tipo, propietario, fecha de vigencia,
   marco normativo al que da respuesta (ISO 27001, NIS2, GDPR...).
2. **Revision periodica**: el scheduler de RiskHub comprueba periodicamente si las politicas
   han superado su fecha de revision y genera alertas al propietario.
3. **Aprobacion**: la politica pasa por un flujo de borrador > revision > aprobacion > vigente.
4. **Vinculacion**: cada politica puede vincularse a controles ISO 27002 especificos.
5. **Regwatch**: si se detecta un cambio normativo relevante, las politicas afectadas
   se marcan automaticamente con `regwatch_review_at` para que el propietario las revise.

### Evidencias
Se pueden adjuntar evidencias de aprobacion (PDF, imagen) a cada politica desde la vista de detalle.
Las evidencias se almacenan cifradas en reposo.
""",
    },

    # ------------------------------------------------------------------
    # AUDITORIAS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "auditoria interna", "auditoria externa", "auditorias", "plan de auditoria",
            "programa de auditoria", "auditoria iso 27001", "hallazgo auditoria",
            "checklist auditoria", "certificacion",
        ],
        "title": "Gestion de auditorias del SGSI",
        "content": """
## Gestion de auditorias del SGSI

### Tipos de auditoria
- **Interna**: realizada por personal propio o auditores internos designados.
- **Externa**: certificacion ISO 27001, supervision regulatoria.
- **De proveedores**: evaluacion del cumplimiento del proveedor.

### Flujo de auditoria
1. **Planificacion**: Auditorias > Nueva auditoria. Definir: tipo, alcance, auditor responsable,
   fecha inicio/fin, criterios (ISO 27001, NIS2, ENS...).
2. **Ejecucion**: registrar hallazgos (no conformidades, observaciones) directamente desde la auditoria.
   Los hallazgos se convierten automaticamente en No Conformidades en el registro NC.
3. **Informe**: generar el informe de auditoria en PDF con los hallazgos, resumen de cumplimiento
   y plan de accion correctiva.
4. **Seguimiento**: las NC generadas tienen su ciclo de vida propio y se siguen desde el modulo NC.
5. **Cierre**: la auditoria se cierra cuando todos los hallazgos criticos tienen accion correctiva aceptada.

### Programa de auditorias
El programa de auditorias muestra el calendario anual de auditorias planificadas, su estado
y el historial de auditorias completadas.
""",
    },

    # ------------------------------------------------------------------
    # CUMPLIMIENTO / COMPLIANCE
    # ------------------------------------------------------------------
    {
        "keywords": [
            "compliance", "cumplimiento", "framework", "iso 27001", "nis2", "nist",
            "ens", "gdpr", "pci", "soc2", "hipaa", "score", "porcentaje",
        ],
        "title": "Gestion de cumplimiento normativo",
        "content": """
## Gestion de cumplimiento normativo

### Frameworks soportados
ISO 27001:2022, NIS2, NIST CSF, ENS (Esquema Nacional de Seguridad), GDPR,
PCI-DSS, SOC 2, HIPAA, ISO 42001 (IA).

### Como funciona el scoring de compliance
El sistema calcula automaticamente el porcentaje de cumplimiento para cada framework activo:
- Cada framework tiene una lista de controles o requisitos.
- El score se calcula como: (controles implementados con madurez >= 3) / (total controles aplicables) * 100.
- Los controles marcados como 'no aplicable' en el SoA se excluyen del denominador.

### Activar frameworks
En Contexto > Normativas activas, seleccionar los frameworks aplicables a la organizacion.
Solo los frameworks activos generan alertas de cumplimiento y aparecen en los informes.

### Gap Analysis de IA
Disponible en IA > Gap Analysis. El agente analiza el estado actual de los controles
y genera un informe detallado con:
- Controles no implementados o con madurez insuficiente.
- Prioridad de implementacion segun criticidad del framework.
- Estimacion de esfuerzo para alcanzar el nivel objetivo.

### Regwatch (Vigilancia Normativa)
El modulo Regwatch monitoriza automaticamente 11 fuentes normativas:
EUR-Lex, BOE, ENISA, AEPD/EDPB, NIST, EBA, ISO, AICPA, PCI, CSA, CIS.
Cuando se detecta un cambio relevante:
1. Se crea un evento en el inbox del tenant.
2. El agente IA analiza el impacto con Claude Haiku.
3. Se propaga el cambio: marcos de compliance, politicas, controles SoA, cuestionarios de proveedores.
4. Se crean tareas de tratamiento en los riesgos afectados.
""",
    },

    # ------------------------------------------------------------------
    # GDPR
    # ------------------------------------------------------------------
    {
        "keywords": [
            "gdpr", "rgpd", "datos personales", "tratamiento", "registro de actividades",
            "dpia", "derechos", "interesado", "base juridica", "dpa", "data processor",
            "transferencia internacional",
        ],
        "title": "Modulo GDPR",
        "content": """
## Modulo GDPR

### Registro de actividades de tratamiento (RAT)
Cumple el art. 30 RGPD. Para cada actividad de tratamiento se registra:
- Nombre y descripcion del tratamiento.
- Base juridica (consentimiento, contrato, obligacion legal, interes vital, interes publico, interes legitimo).
- Categorias de datos y de interesados.
- Responsable, corresponsables, encargados de tratamiento.
- Paises de transferencia (UE / fuera UE con salvaguardas).
- Plazos de conservacion.
- Medidas de seguridad aplicadas.

### DPIA (Evaluacion de Impacto)
Para tratamientos de alto riesgo (art. 35 RGPD). El sistema guia el proceso:
1. Describir el tratamiento y su necesidad.
2. Evaluar la necesidad y proporcionalidad.
3. Identificar y evaluar riesgos para los derechos y libertades.
4. Definir medidas para mitigar riesgos.
5. Generar el informe DPIA en PDF.

### Gestion de derechos de interesados
Registro de solicitudes de ejercicio de derechos: acceso, rectificacion, supresion,
portabilidad, oposicion, limitacion. Con control de plazo de respuesta (1 mes, art. 12 RGPD).

### Proveedores (Encargados de tratamiento)
Los proveedores marcados como 'Procesador GDPR' se vinculan al RAT y requieren
un DPA (Data Processing Agreement) vigente. El sistema alerta cuando el DPA esta proximo a vencer.
""",
    },

    # ------------------------------------------------------------------
    # ALERTAS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "alerta", "alertas", "notificacion", "email", "umbral", "trigger",
            "escalada", "vencimiento",
        ],
        "title": "Sistema de alertas",
        "content": """
## Sistema de alertas

### Tipos de alertas
- **Riesgo critico**: cuando un riesgo supera el nivel de apetito configurado.
- **Tarea vencida**: tareas de tratamiento que superan su fecha objetivo.
- **Control degradado**: controles cuya madurez baja por inactividad o evaluacion.
- **Proveedor**: score residual de proveedor bajo del umbral o SLA de hallazgo vencido.
- **Politica**: politica con fecha de revision superada.
- **Certificacion**: auditoria de certificacion proxima a vencer.
- **CVE**: vulnerabilidad critica en NVD que impacta a activos inventariados.
- **OSINT**: hallazgo critico en escaneo de dominio/email/IP.
- **Regwatch**: cambio normativo relevante detectado en fuentes monitorizadas.

### Configuracion de alertas por email
En Alertas > Configuracion:
1. Activar notificaciones por email.
2. Introducir servidor SMTP, puerto, credenciales.
3. Configurar destinatarios por tipo de alerta.
4. Definir umbrales de nivel de riesgo para notificacion.

### Escalada automatica
El scheduler (APScheduler) revisa diariamente:
- Tareas vencidas: escala automaticamente al supervisor del responsable.
- Revisiones de politica: notifica al propietario de la politica.
- SLA de VendorIssues: cierra o escala segun configuracion.
""",
    },

    # ------------------------------------------------------------------
    # INFORMES
    # ------------------------------------------------------------------
    {
        "keywords": [
            "informe", "informes", "report", "pdf", "exportar", "dashboard", "ejecutivo",
            "postura", "resumen", "metricas",
        ],
        "title": "Informes y exportacion",
        "content": """
## Informes y exportacion

### Tipos de informes disponibles
- **Informe de postura de seguridad**: resumen ejecutivo del estado del SGSI.
  Incluye: nivel de riesgo global, top 10 riesgos criticos, cobertura de controles,
  incidentes del periodo, estado de cumplimiento por framework.
- **Informe de riesgos**: listado completo con filtros por estado, nivel, activo.
- **Informe de proveedores TPRM**: evaluaciones consolidadas, top riesgos de terceros.
- **Informe de auditoria**: hallazgos, plan de accion correctiva.
- **Informe DPIA**: evaluacion de impacto GDPR en formato reglamentario.
- **Informe ejecutivo** (vista Executive): KPIs de alto nivel para la direccion.

### Generacion de PDF
Todos los informes se exportan a PDF usando ReportLab con la paleta corporativa de RiskHub
(purple #59008D, orange #D65200).

### Informe mensual automatico
El scheduler genera automaticamente un informe mensual de postura y lo envia
por email a los destinatarios configurados en Alertas > Configuracion.

### Dashboard en tiempo real
El dashboard principal muestra:
- Heatmap de riesgos (matriz probabilidad x impacto).
- KPIs: riesgos criticos, incidentes abiertos, controles por implementar, score de compliance.
- Tendencias del ultimo mes.
""",
    },

    # ------------------------------------------------------------------
    # OSINT
    # ------------------------------------------------------------------
    {
        "keywords": [
            "osint", "escaneo", "dominio", "email", "ip", "url", "username",
            "inteligencia", "exposicion", "breach", "haveibeenpwned",
        ],
        "title": "Modulo OSINT",
        "content": """
## Modulo OSINT (Inteligencia de amenazas externas)

### Que es
El modulo OSINT permite escanear dominios, emails, IPs, URLs y usernames de la organizacion
para detectar exposicion publica, filtraciones de credenciales y amenazas externas.

### Tipos de escaneo
- **Email**: verifica si el email ha sido comprometido en brechas conocidas.
- **Dominio**: DNS records, subdominios, reputacion, certificados SSL.
- **IP**: geolocalizado, reputacion en blacklists, puertos abiertos (escaneo pasivo).
- **URL**: analisis de reputacion y deteccion de phishing.
- **Username**: presencia en redes sociales y foros de hacking.

### Flujo automatico
1. Configurar targets en OSINT > Configuracion (dominios y emails de la organizacion).
2. El scheduler ejecuta un re-scan semanal automatico.
3. Si se detecta un hallazgo CRITICAL o HIGH, se crea automaticamente un incidente de seguridad.
4. Los hallazgos se vinculan a los activos del inventario que correspondan (por nombre de dominio, IP, etc.).

### Uso manual
En OSINT > Nuevo escaneo, se puede lanzar un escaneo puntual de cualquier indicador.
Los resultados aparecen en el historial con timeline de cambios.
""",
    },

    # ------------------------------------------------------------------
    # CVE
    # ------------------------------------------------------------------
    {
        "keywords": [
            "cve", "vulnerabilidad", "nvd", "parche", "patch", "cvss", "nist nvd",
            "escaneo de vulnerabilidades",
        ],
        "title": "Modulo CVE — gestion de vulnerabilidades conocidas",
        "content": """
## Modulo CVE — gestion de vulnerabilidades conocidas

### Como funciona
RiskHub se conecta a la NVD API (NIST National Vulnerability Database) para:
1. **Escaneo diario automatico**: descarga CVEs publicados en las ultimas 24 horas.
2. **Matching con activos**: compara el software/vendor de cada activo con los CPE de los CVEs.
3. **Analisis IA de impacto**: Claude analiza si el CVE afecta realmente al stack tecnologico
   de la organizacion y genera una estimacion de impacto.
4. **Linkage a activos**: los CVEs que impactan activos inventariados se vinculan automaticamente.
5. **Alertas**: CVEs con CVSS >= 9.0 (criticos) generan alertas inmediatas.

### Vista CVE
En CVE se muestra el listado de vulnerabilidades conocidas relevantes para la organizacion,
con columnas: CVE-ID, CVSS Score, fecha, activos afectados, estado de remediacion.

### Gestion de remediacion
Cada CVE vinculado a un activo puede tener:
- Estado: pending / mitigating / mitigated / accepted.
- Tarea de tratamiento vinculada (patch, workaround, etc.).
- Fecha objetivo de remediacion.
""",
    },

    # ------------------------------------------------------------------
    # ROLES Y USUARIOS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "rol", "roles", "usuario", "usuarios", "permisos", "admin", "analyst",
            "viewer", "superadmin", "acceso", "gestion de usuarios",
        ],
        "title": "Roles y gestion de usuarios",
        "content": """
## Roles y gestion de usuarios

### Roles disponibles
- **superadmin**: acceso total a todas las organizaciones (multi-tenant). Solo para operadores de la plataforma.
- **admin**: administrador de la organizacion. Gestiona usuarios, integraciones, configuracion global.
- **analyst**: analista de seguridad. Puede crear/editar riesgos, incidentes, controles, politicas.
- **viewer**: solo lectura. Ve dashboards e informes sin poder modificar datos.

### Gestion de usuarios (admin)
1. Ir a Usuarios > Nuevo usuario.
2. Completar: nombre, email, rol, organizacion.
3. El usuario recibe un email con enlace de activacion (si el email SMTP esta configurado).
4. Desde la lista de usuarios: activar/desactivar, cambiar rol, resetear contraseña.

### Integracion con SSO
Cuando un usuario se autentica por primera vez via SSO, se crea automaticamente con rol 'viewer'.
El admin puede cambiar el rol desde Usuarios.

### Seguridad de contraseñas
- Hash bcrypt con cost factor 12.
- No se almacenan contraseñas en texto claro.
- Rate limiting en el endpoint de login: 5 intentos fallidos → bloqueo temporal de 15 minutos.
- Los tokens JWT tienen expiracion configurable (por defecto 8 horas).

### Multi-tenancia
Cada organizacion tiene sus propios datos completamente aislados.
El superadmin puede ver todas las organizaciones desde Organizaciones > Panel de superadmin.
""",
    },

    # ------------------------------------------------------------------
    # PLANES / LICENCIAMIENTO
    # ------------------------------------------------------------------
    {
        "keywords": [
            "plan", "planes", "licencia", "free", "starter", "pro", "enterprise",
            "modulos", "limite", "feature flag", "funcionalidad",
        ],
        "title": "Planes y licenciamiento",
        "content": """
## Planes y licenciamiento

### Planes disponibles
- **Free**: funcionalidades basicas de gestion de riesgos. Sin agente IA, sin integraciones.
- **Starter**: agente IA, documentos (limite 10), OSINT basico, 1 framework de compliance.
- **Pro**: todos los modulos excepto multi-tenancy avanzado. TPRM, Regwatch, CVE, SSO, SharePoint.
- **Enterprise**: sin limites. Multi-tenancy, Regwatch completo, soporte prioritario.

### Como ver el plan activo
En Organizaciones > Mi Organizacion se muestra el plan activo con los modulos disponibles
y los que estan bloqueados. Los modulos bloqueados muestran un badge de upgrade.

### Feature Flags
El endpoint GET /api/feature-flags/plans/limits devuelve los limites de cada plan.
Los modulos bloqueados devuelven HTTP 402 (Payment Required) al intentar acceder.

### Cambiar de plan
Solo el superadmin puede cambiar el plan de una organizacion desde
Organizaciones > [Organizacion] > Cambiar plan.
""",
    },

    # ------------------------------------------------------------------
    # BCP / CONTINUIDAD DE NEGOCIO
    # ------------------------------------------------------------------
    {
        "keywords": [
            "bcp", "continuidad", "recuperacion", "disaster recovery", "rto", "rpo",
            "plan de continuidad", "business continuity",
        ],
        "title": "Planes de continuidad de negocio (BCP)",
        "content": """
## Planes de continuidad de negocio (BCP)

### Que es
El modulo BCP permite documentar y gestionar los planes de continuidad de negocio
alineados con ISO 22301 e ISO 27031.

### Componentes de un plan BCP
- **Analisis de impacto en negocio (BIA)**: identificar procesos criticos, RTO y RPO objetivo.
- **Estrategias de recuperacion**: procedimientos alternativos, ubicaciones de contingencia.
- **Equipos de respuesta**: roles y responsabilidades en caso de activacion.
- **Procedimientos de activacion**: criterios y pasos para activar el plan.
- **Pruebas y ejercicios**: programacion y registro de simulacros.

### Vinculacion con riesgos
Los riesgos de alta disponibilidad (A en CIA) se vinculan automaticamente al BCP del
proceso de negocio afectado.

### Regwatch y BCP
Si Regwatch detecta un cambio normativo que impacta al BCP (ej. nueva regulacion de resiliencia
operativa DORA), el plan se marca automaticamente como `under_review` para actualizacion.
""",
    },

    # ------------------------------------------------------------------
    # TAREAS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "tarea", "tareas", "task", "tratamiento", "responsable", "vencimiento",
            "seguimiento", "plan de accion",
        ],
        "title": "Gestion de tareas de tratamiento",
        "content": """
## Gestion de tareas de tratamiento

### Para que sirven las tareas
Las tareas formalizan las acciones de tratamiento de riesgos, correcciones de NC,
mejoras de controles y planes de accion de auditoria.

### Tipos de tarea
- **Tratamiento de riesgo**: vinculada a un riesgo especifico, reduce el nivel residual.
- **Accion correctiva (NC)**: vinculada a una no conformidad.
- **Mejora de control**: aumentar la madurez de un control ISO 27002.
- **Auditoria**: accion derivada de un hallazgo de auditoria.
- **General**: cualquier tarea de seguridad no vinculada a los anteriores.

### Flujo
1. Crear tarea (manual o desde el agente IA que la propone).
2. Asignar responsable, fecha objetivo y prioridad.
3. El responsable recibe notificacion (si email SMTP configurado).
4. Estados: pending > in_progress > completed > verified.
5. Al completar una tarea de tratamiento, el sistema recalcula el nivel residual del riesgo.

### Escalada automatica
El scheduler de APScheduler escala diariamente las tareas vencidas al supervisor del responsable
y genera una alerta en el dashboard.
""",
    },
    # ------------------------------------------------------------------
    # CCM — CONTINUOUS CONTROL MONITORING
    # ------------------------------------------------------------------
    {
        "keywords": [
            "ccm", "continuous control monitoring", "monitoreo continuo", "test", "tests",
            "verificacion automatica", "control automatico", "score ccm",
        ],
        "title": "CCM — Continuous Control Monitoring",
        "content": """
## CCM — Continuous Control Monitoring

### Que es
El modulo CCM ejecuta tests automaticos sobre la base de datos de RiskHub para verificar
que los controles del SGSI estan funcionando correctamente en tiempo real.
No requiere integracion externa — evalua el estado actual de los datos internos.

### Como funciona
1. Ir a **CCM** desde el menu lateral.
2. Ver el catalogo de tests disponibles (organizados por dominio ISO 27002).
3. Ejecutar todos los tests con el boton 'Ejecutar todos' o un test especifico.
4. El sistema calcula un score CCM global (0-100) y un score por dominio.

### Ejemplos de tests incluidos
- Controles con madurez <= 1 existentes.
- Riesgos criticos sin tarea de tratamiento asignada.
- Incidentes abiertos con mas de 30 dias sin actividad.
- Politicas sin revision en los ultimos 12 meses.
- Proveedores criticos sin evaluacion en los ultimos 6 meses.
- No conformidades abiertas con mas de 90 dias.
- Usuarios sin actividad en los ultimos 90 dias.
- Activos sin propietario asignado.

### Interpretacion del score
- 90-100: excelente — controles funcionando segun lo esperado.
- 70-89: aceptable — algunas brechas que requieren atencion.
- 50-69: deficiente — brechas significativas, accion inmediata recomendada.
- < 50: critico — fallos sistematicos en controles, escalada necesaria.

### Uso recomendado
Ejecutar CCM semanalmente o antes de auditorias internas/externas para
tener evidencia objetiva del estado operativo de los controles.
""",
    },

    # ------------------------------------------------------------------
    # ANALISIS PREDICTIVO
    # ------------------------------------------------------------------
    {
        "keywords": [
            "predictivo", "prediccion", "tendencia", "forecast", "tendencias",
            "madurez path", "trajectory", "high risk assets", "amenaza forecast",
            "analisis predictivo",
        ],
        "title": "Analisis predictivo de riesgos",
        "content": """
## Analisis predictivo de riesgos

### Que es
El modulo Predictivo analiza el historial de snapshots de riesgos para proyectar tendencias
futuras y recomendar el camino optimo hacia la madurez objetivo.

### Funcionalidades

**Tendencia de riesgos** (`/api/predictive/trend`):
- Analiza los snapshots de riesgos de los ultimos N dias (por defecto 90).
- Calcula la variacion media de niveles residuales.
- Identifica si la postura de riesgo de la organizacion mejora, se mantiene o empeora.
- Grafico de evolucion temporal con bandas de confianza.

**Activos de alto riesgo** (`/api/predictive/high-risk-assets`):
- Lista los activos cuyo riesgo agregado supera el apetito definido.
- Ordena por urgencia de tratamiento.

**Forecast de amenazas** (`/api/predictive/threat-forecast`):
- Basandose en el historial de incidentes y hallazgos externos, proyecta
  las amenazas con mayor probabilidad de materializarse en los proximos 90 dias.

**Path de madurez** (`/api/predictive/maturity-path`):
- Compara el nivel de madurez actual vs. el objetivo configurado.
- Genera una hoja de ruta priorizada de mejoras de controles.
- Estima el tiempo necesario para alcanzar cada nivel.

### Como usar
Ir a **Predictivo** desde el menu lateral. La vista muestra los cuatro paneles
con graficos interactivos y recomendaciones priorizadas.
""",
    },

    # ------------------------------------------------------------------
    # ARCHITECTURE REVIEW
    # ------------------------------------------------------------------
    {
        "keywords": [
            "arquitectura", "architecture review", "diagrama", "drawio", "stride",
            "revision de arquitectura", "import diagrama", "threat modeling",
            "modelado de amenazas",
        ],
        "title": "Revision de arquitectura de seguridad",
        "content": """
## Revision de arquitectura de seguridad

### Que es
El modulo Architecture Review importa diagramas de arquitectura y usa IA para realizar
un analisis de seguridad automatico basado en la metodologia STRIDE.

### Formatos de entrada soportados
- **Archivo .drawio / .xml** (diagrams.net): el sistema parsea nodos, conectores y etiquetas.
- **Descripcion textual**: descripcion en lenguaje natural de la arquitectura.
- **Combinacion**: archivo + descripcion con contexto adicional.

### Que genera el analisis
1. **Auto-creacion de activos**: cada nodo del diagrama se convierte en un activo
   en el inventario de RiskHub con el tipo inferido (servidor, base de datos, red, etc.).
2. **Analisis STRIDE**: para cada componente y flujo de datos, el sistema evalua:
   - Spoofing (suplantacion de identidad)
   - Tampering (manipulacion de datos)
   - Repudiation (repudio)
   - Information Disclosure (divulgacion de informacion)
   - Denial of Service (denegacion de servicio)
   - Elevation of Privilege (escalada de privilegios)
3. **Amenazas generadas**: cada hallazgo STRIDE se convierte en un ExternalFinding
   disponible en el modulo de Hallazgos Externos.
4. **Riesgos sugeridos**: los hallazgos de alta criticidad se pueden convertir en
   riesgos ISO 27005 con un clic.

### Flujo de uso
1. Ir a **Architecture Review** desde el menu.
2. Subir el archivo .drawio o escribir la descripcion.
3. Activar 'Usar IA' para el analisis STRIDE automatico.
4. Revisar activos y amenazas generados.
5. Aprobar los que sean relevantes para importarlos al registro de riesgos.
""",
    },

    # ------------------------------------------------------------------
    # KRIs / KPIs
    # ------------------------------------------------------------------
    {
        "keywords": [
            "kri", "kris", "kpi", "kpis", "key risk indicator", "key performance indicator",
            "umbral", "breach", "warning", "indicador", "metrica",
        ],
        "title": "KRIs y KPIs — Indicadores clave de riesgo y rendimiento",
        "content": """
## KRIs y KPIs

### Que son
- **KRI (Key Risk Indicator)**: metrica que senala el nivel de exposicion al riesgo.
  Cuando supera un umbral, indica que el riesgo puede materializarse.
- **KPI (Key Performance Indicator)**: metrica de rendimiento del programa de seguridad.

### Como crear un KRI/KPI
1. Ir a **KRIs** desde el menu lateral.
2. Crear nuevo indicador: nombre, tipo de metrica, tipo (KRI/KPI), direccion
   (higher_is_better o lower_is_better).
3. Configurar umbrales:
   - **Warning threshold**: valor que activa una advertencia.
   - **Breach threshold**: valor critico que dispara alerta.
4. Activar alerta por email al superar el breach (opcional).
5. Opcionalmente vincular el KRI a un riesgo especifico del registro.

### Tipos de metricas disponibles (KRIMetricType)
- Numero de riesgos criticos activos.
- Numero de incidentes abiertos.
- Porcentaje de controles implementados.
- Numero de proveedores con score bajo.
- Numero de tareas vencidas.
- Numero de politicas sin revisar.
- Metricas personalizadas (valor manual o calculado).

### Estados de un KRI
- **normal**: valor por debajo del warning threshold.
- **warning**: valor entre warning y breach threshold.
- **breach**: valor supera el breach threshold — alerta generada.

### Vista ejecutiva de KRIs
En la vista **Executive** se muestra el panel de KRIs/KPIs en formato de semaforo
para la presentacion a la direccion.
""",
    },

    # ------------------------------------------------------------------
    # MANAGEMENT REVIEW
    # ------------------------------------------------------------------
    {
        "keywords": [
            "management review", "revision por la direccion", "direccion", "iso 27001 9.3",
            "comite de seguridad", "informe de direccion", "inputs", "outputs",
        ],
        "title": "Revision por la Direccion (ISO 27001 cl. 9.3)",
        "content": """
## Revision por la Direccion (ISO 27001 clausula 9.3)

### Que es
La Revision por la Direccion es un requisito ISO 27001 (clausula 9.3) que exige que la alta
direccion revise periodicamente el SGSI para asegurar su idoneidad, adecuacion y eficacia.

### Como crear una sesion de revision
1. Ir a **Management Review** desde el menu.
2. Crear nueva revision: fecha, participantes (array de nombres/cargos).
3. El sistema auto-rellena los inputs requeridos por ISO 27001:
   - Estado de acciones de revisiones anteriores.
   - Cambios en el contexto organizacional (externos e internos).
   - Feedback de partes interesadas.
   - Resultado de evaluaciones de riesgo.
   - Estado del programa de tratamiento de riesgos.
   - Resultados de monitoreo y medicion.
   - Resultados de auditorias.
   - Cumplimiento de objetivos de seguridad.
4. Registrar las decisiones (outputs) de la direccion:
   - Recursos asignados.
   - Objetivos de seguridad actualizados.
   - Decisiones de mejora continua.
5. Generar el informe de revision en PDF.

### Periodicidad recomendada
ISO 27001 requiere realizarla al menos una vez al ano. Para organizaciones con
mayor exposicion se recomienda trimestralmente.
""",
    },

    # ------------------------------------------------------------------
    # EXTERNAL FINDINGS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "hallazgo", "hallazgos", "hallazgos externos", "external findings",
            "nessus", "qualys", "burp", "openvas", "escaner", "scanner",
            "importar hallazgos", "vulnerabilidad tecnica",
        ],
        "title": "Hallazgos externos — importacion de escaneres",
        "content": """
## Hallazgos externos

### Que es
El modulo de Hallazgos Externos centraliza los resultados de herramientas de escaneo
de seguridad tecnica (Nessus, Qualys, Burp Suite, OpenVAS) y los integra con el
registro de riesgos ISO 27005.

### Formatos de importacion soportados
- **Nessus**: archivo .nessus (XML).
- **Qualys**: informe XML de Qualys.
- **Burp Suite**: exportacion XML de Burp.
- **OpenVAS**: informe XML de OpenVAS.
El sistema detecta automaticamente el formato al subir el archivo.

### Tambien se generan hallazgos desde
- **Architecture Review**: hallazgos STRIDE del analisis de diagramas.
- **OSINT**: hallazgos de escaneos de dominio/email/IP.
- **CVE**: vulnerabilidades matcheadas contra activos.

### Flujo de gestion
1. Ir a **Hallazgos Externos** desde el menu.
2. Subir el archivo de resultados del escaner.
3. El sistema importa los hallazgos con: titulo, severidad, CVSS, CVE, host afectado,
   software afectado.
4. Vincular cada hallazgo al activo correspondiente del inventario.
5. Para cada hallazgo, elegir la accion:
   - **Convertir en incidente**: para hallazgos activos/explotados.
   - **Convertir en riesgo**: para vulnerabilidades que representan riesgo futuro.
   - **Aceptar**: para falsos positivos o riesgos aceptados conscientemente.
   - **Resolver**: cuando el hallazgo ha sido remedidado (patch aplicado).

### Severidades
CRITICAL, HIGH, MEDIUM, LOW — mapeadas desde el CVSS score del escaner.
""",
    },

    # ------------------------------------------------------------------
    # CHANGE MANAGEMENT
    # ------------------------------------------------------------------
    {
        "keywords": [
            "change management", "gestion de cambios", "solicitud de cambio",
            "change request", "aprobacion de cambio", "chg", "iso 27001 6.3",
            "ventana de mantenimiento", "comite de cambios",
        ],
        "title": "Gestion de cambios (ISO 27001 cl. 6.3)",
        "content": """
## Gestion de cambios (ISO 27001 clausula 6.3)

### Que es
El modulo de Gestion de Cambios formaliza el proceso de control de cambios en el SGSI
segun ISO 27001 clausula 6.3: cualquier cambio planificado debe evaluarse, aprobarse
y gestionarse de forma controlada.

### Tipos de cambio
- **Politica**: modificacion de politicas de seguridad.
- **Control**: cambio en la implementacion de controles.
- **Activo**: alta, baja o modificacion de activos criticos.
- **Proceso**: cambio en procesos de negocio con impacto en seguridad.
- **Infraestructura**: cambios en sistemas, redes, plataformas.
- **Otro**: cambios que no encajan en las categorias anteriores.

### Flujo de gestion
1. **Solicitud** (draft): crear la solicitud de cambio con descripcion, tipo,
   impacto estimado (none/low/medium/high) y justificacion.
2. **Revision** (under_review): el responsable evalua el impacto en la seguridad,
   disponibilidad y continuidad.
3. **Aprobacion / Rechazo**: el comite o admin aprueba o rechaza con justificacion.
4. **Implementacion**: ejecutar el cambio en la ventana de mantenimiento acordada.
5. **Verificacion**: comprobar que el cambio se implemento correctamente
   y no introdujo nuevos riesgos.

### Codigo de cambio
Cada solicitud recibe un codigo secuencial automatico: CHG-0001, CHG-0002, etc.

### Integracion con otros modulos
Un cambio aprobado puede vincularse a: riesgos afectados, controles modificados,
incidentes derivados del cambio, o tareas de seguimiento.
""",
    },

    # ------------------------------------------------------------------
    # AWARENESS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "awareness", "concienciacion", "formacion", "capacitacion", "sensibilizacion",
            "campana", "phishing simulado", "e-learning", "training",
        ],
        "title": "Gestion de concienciacion y formacion en seguridad",
        "content": """
## Gestion de concienciacion y formacion (Awareness)

### Que es
El modulo Awareness gestiona el programa de concienciacion en seguridad de la informacion
exigido por ISO 27001 (clausula 7.3) y por regulaciones como NIS2 y ENS.

### Tipos de contenido
- **Articulo**: contenido informativo sobre buenas practicas de seguridad.
- **Video**: enlace a video formativo.
- **Quiz**: cuestionario de evaluacion de conocimientos.
- **Campana de phishing simulado**: ejercicio de concienciacion practica.
- **Politica para leer y aceptar**: politica que el empleado debe confirmar haber leido.

### Flujo de creacion
1. Ir a **Awareness** desde el menu.
2. Crear nuevo item: titulo, tipo, contenido/URL, publico objetivo.
3. Publicar y distribuir (via email si SMTP configurado, o enlace directo).
4. Los empleados acceden via enlace publico sin necesidad de cuenta en RiskHub.
5. El sistema registra quien ha completado cada item y cuando.

### Branding personalizado
El modulo soporta configuracion de branding (logo, colores) para que las comunicaciones
de awareness se muestren con la identidad corporativa de la organizacion.

### Evidencia para auditorias
Los registros de completado (quien, cuando, score en quiz) se almacenan y se pueden
exportar como evidencia para auditorias ISO 27001, NIS2 o ENS.
""",
    },

    # ------------------------------------------------------------------
    # SURVEYS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "survey", "surveys", "encuesta", "encuestas", "cuestionario distribuido",
            "campana de encuesta", "evaluacion distribuida",
        ],
        "title": "Encuestas distribuidas",
        "content": """
## Encuestas distribuidas (Surveys)

### Que es
El modulo Surveys permite crear y distribuir encuestas de evaluacion de riesgo
a empleados, departamentos o proveedores sin que necesiten cuenta en RiskHub.

### Diferencia con los cuestionarios de proveedor (TPRM)
- Los **cuestionarios TPRM** son para evaluar proveedores externos con preguntas
  tecnicas de seguridad alineadas a ISO 27002.
- Las **Surveys** son para recoger informacion de forma masiva de empleados internos
  o grupos externos (ej. evaluacion de cultura de seguridad, BIA departamental).

### Flujo de creacion
1. Crear una plantilla de encuesta con preguntas (texto libre, escala, opcion multiple).
2. Crear una campana: seleccionar plantilla, definir destinatarios y fecha limite.
3. El sistema envia los enlaces de respuesta por email.
4. Los destinatarios responden sin autenticacion (enlace tokenizado).
5. Los resultados se agregan y muestran en el dashboard de la campana.

### Casos de uso tipicos
- Encuesta de cultura de seguridad anual (ISO 27001 cl. 7.3).
- Business Impact Analysis (BIA) departamental para BCP.
- Evaluacion de proveedores de bajo riesgo (alternativa ligera a cuestionarios TPRM).
- Post-incident review anonima.
""",
    },

    # ------------------------------------------------------------------
    # TRUST PORTAL
    # ------------------------------------------------------------------
    {
        "keywords": [
            "trust portal", "portal confianza", "portal externo", "portal proveedor",
            "sin cuenta", "tokenizado", "enlace unico proveedor",
        ],
        "title": "Trust Portal — portal externo para proveedores",
        "content": """
## Trust Portal

### Que es
El Trust Portal es un portal web publico (sin autenticacion) donde los proveedores
pueden responder cuestionarios de seguridad enviados por RiskHub.

### Como funciona
1. Desde el modulo de Proveedores, enviar un cuestionario a un proveedor externo.
2. El sistema genera un enlace unico y tokenizado para ese cuestionario especifico.
3. El proveedor accede al enlace y responde las preguntas directamente en el portal.
4. No necesita tener cuenta en RiskHub ni instalar nada.
5. Las respuestas se guardan automaticamente en RiskHub para su evaluacion.

### Seguridad del portal
- Cada enlace es unico, con token de un solo uso y fecha de expiracion configurable.
- El proveedor solo puede ver su propio cuestionario, no datos de la organizacion.
- Los enlaces pueden revocarse manualmente si es necesario.

### Personalizacion
El portal muestra el nombre de la organizacion y puede incluir el logo corporativo
(configuracion de branding en Awareness > Configuracion de marca).
""",
    },

    # ------------------------------------------------------------------
    # ITSM
    # ------------------------------------------------------------------
    {
        "keywords": [
            "itsm", "servicenow", "jira", "ticket", "ticketing", "integracion itsm",
            "sincronizar tareas", "service management",
        ],
        "title": "Integracion ITSM (ServiceNow, Jira)",
        "content": """
## Integracion ITSM

### Que es
El modulo ITSM permite sincronizar las tareas de tratamiento de RiskHub con herramientas
de gestion de servicios IT como ServiceNow o Jira.

### Configuracion
1. Ir a **Integraciones > ITSM** desde el menu.
2. Seleccionar el sistema ITSM (ServiceNow / Jira).
3. Para **ServiceNow**:
   - Instancia URL (ej. https://empresa.service-now.com).
   - Usuario y contrasena de servicio (o OAuth token).
   - Tabla de destino (incident, change_request, etc.).
4. Para **Jira**:
   - URL del servidor Jira.
   - Email del usuario + API token (generado en account.atlassian.com).
   - Proyecto y tipo de issue de destino.
5. Guardar y probar la conexion.

### Sincronizacion de tareas
Una vez configurado, al crear una tarea de tratamiento en RiskHub se puede
opcionalmente crear el ticket correspondiente en el ITSM con un clic.
Los cambios de estado en el ITSM pueden propagarse de vuelta a RiskHub via webhook.

### Casos de uso
- Equipo de IT gestiona los remediation tickets en Jira; CISO ve el estado en RiskHub.
- Cambios de infraestructura se registran en ServiceNow y se vinculan al riesgo ISO 27005.
""",
    },

    # ------------------------------------------------------------------
    # EVIDENCE
    # ------------------------------------------------------------------
    {
        "keywords": [
            "evidencia", "evidencias", "evidence", "adjunto", "adjuntar", "documento",
            "prueba", "certificado", "log", "screenshot", "versionado evidencia",
        ],
        "title": "Gestion centralizada de evidencias",
        "content": """
## Gestion centralizada de evidencias

### Que es
El modulo Evidence centraliza todas las evidencias del SGSI con versionado,
audit trail e integridad verificable mediante SHA-256.

### Tipos de evidencia
- **Politica**: copia aprobada de una politica de seguridad.
- **Procedimiento**: documentacion de procedimientos operativos.
- **Registro**: registros de actividad (logs, actas, etc.).
- **Certificado**: certificados de formacion, cumplimiento, etc.
- **Captura de pantalla**: evidencia visual de configuracion o estado.
- **Log**: extraccion de logs de sistemas.
- **Informe**: informes de auditoria, analisis, etc.
- **Otro**: cualquier otro tipo de evidencia.

### Vinculacion
Cada evidencia puede vincularse a:
- Un **control ISO 27002** especifico (evidencia de implementacion).
- Un **riesgo** (evidencia de tratamiento o aceptacion).
- Una **politica** (evidencia de aprobacion o revision).
- Un **requisito de compliance** (evidencia para auditoria).

### Versionado
Cuando se actualiza una evidencia, la version anterior se mantiene como historico.
El campo `is_current` indica la version vigente. El campo `version` es un contador incremental.

### Integridad
Cada evidencia almacena el hash SHA-256 del archivo al momento de la subida.
Cualquier modificacion del archivo seria detectable al comparar el hash.

### Expiracion
Se puede configurar una fecha de expiracion para certificados o evidencias con validez temporal.
El sistema genera alertas cuando la evidencia esta proxima a vencer.

### Subir una evidencia
1. Ir a **Evidencias** desde el menu lateral.
2. Crear nueva evidencia: titulo, tipo, descripcion.
3. Adjuntar el archivo (PDF, imagen, log — validado con magic bytes).
4. Vincular al control, riesgo o politica correspondiente.
5. La evidencia queda disponible en la vista de detalle del elemento vinculado.
""",
    },

    # ------------------------------------------------------------------
    # REGWATCH DETALLADO
    # ------------------------------------------------------------------
    {
        "keywords": [
            "regwatch", "vigilancia normativa", "fuente normativa", "cambio normativo",
            "inbox regwatch", "conector", "eur-lex", "boe", "enisa", "aepd", "nist",
            "eba", "normativa automatica", "sweep",
        ],
        "title": "Regwatch — Vigilancia normativa automatica",
        "content": """
## Regwatch — Vigilancia normativa automatica

### Que es
Regwatch monitoriza automaticamente 11 fuentes normativas y regulatorias en tiempo real,
detecta cambios relevantes y propaga el impacto a los elementos del SGSI afectados.

### Fuentes monitorizadas (11 conectores)
1. **EUR-Lex** (SPARQL): legislacion y reglamentos de la Union Europea.
2. **BOE** (RSS): Boletin Oficial del Estado espanol.
3. **ENISA** (RSS): publicaciones y guias de la Agencia de Ciberseguridad de la UE.
4. **AEPD/EDPB** (RSS): novedades de proteccion de datos (GDPR).
5. **NIST** (JSON+RSS): publicaciones del NIST (CSF, SP 800-xx).
6. **EBA** (RSS): Autoridad Bancaria Europea (DORA, PSD2, etc.).
7. **ISO** (status): cambios en el status de normas ISO.
8. **AICPA**: actualizaciones SOC 2.
9. **PCI**: cambios en PCI-DSS.
10. **CSA**: guias de Cloud Security Alliance.
11. **CIS**: benchmarks y controles CIS.

### Flujo automatico
1. El scheduler ejecuta un sweep periodico de todas las fuentes.
2. Los cambios detectados se analizan con Claude Haiku para extraer el impacto.
3. Se crea un **ChangePack** con el resumen del cambio y los elementos afectados.
4. Se propaga el impacto:
   - Catalogo de controles: actualiza la descripcion si el control cambio.
   - SoA: marca los requisitos de compliance afectados para revision (`regwatch_review_at`).
   - Politicas: marca las politicas que referencian las clausulas afectadas.
   - Planes BCP: marca los planes bajo revision si el cambio afecta a resiliencia.
   - Cuestionarios TPRM: marca los cuestionarios de proveedores sujetos a la regulacion.
   - Riesgos: crea tareas de tratamiento en los riesgos cubiertos por la norma.
5. El tenant recibe un item en su **Inbox** de Regwatch.

### Inbox de Regwatch
En **Regwatch > Inbox** se muestran todos los cambios normativos pendientes de revision.
Para cada item se puede:
- Revisar el resumen del cambio y el analisis de impacto IA.
- Aprobar los cambios sugeridos (actualizar politicas, controles, etc.).
- Descartar (con justificacion) si el cambio no es relevante.
- Posponer (snooze) para revisarlo mas adelante.

### Configuracion
En **Regwatch > Configuracion**:
- Activar/desactivar fuentes individuales.
- Configurar los frameworks relevantes para la organizacion (filtra cambios irrelevantes).
- Configurar el email de notificacion para nuevos cambios.
""",
    },

    # ------------------------------------------------------------------
    # NIS2 DASHBOARD
    # ------------------------------------------------------------------
    {
        "keywords": [
            "nis2", "nis 2", "directiva nis2", "operador esencial", "entidad importante",
            "notificacion nis2", "articulo 21", "articulo 23", "incidente significativo",
        ],
        "title": "Dashboard NIS2",
        "content": """
## Dashboard NIS2

### Que es
El Dashboard NIS2 muestra el estado de cumplimiento especifico de la Directiva NIS2
(UE 2022/2555) con los 10 requisitos del articulo 21 y el flujo de notificacion
de incidentes del articulo 23.

### Los 10 requisitos del articulo 21 NIS2
1. Politicas de analisis de riesgos y seguridad de los sistemas de informacion.
2. Gestion de incidentes.
3. Continuidad de las actividades y gestion de crisis.
4. Seguridad de la cadena de suministro.
5. Seguridad en la adquisicion, el desarrollo y el mantenimiento de redes y sistemas.
6. Politicas y procedimientos para evaluar la eficacia de las medidas de gestion de riesgos.
7. Practicas basicas de ciberigiene y formacion en ciberseguridad.
8. Politicas y procedimientos relativos al uso de criptografia.
9. Seguridad de los recursos humanos, politicas de control de acceso y gestion de activos.
10. Uso de autenticacion multifactor o de autenticacion continua.

### Notificacion de incidentes (articulo 23)
NIS2 exige notificar incidentes significativos a la autoridad competente:
- **Alerta temprana**: en 24 horas desde la deteccion.
- **Notificacion**: en 72 horas con informacion inicial.
- **Informe intermedio**: si se solicita.
- **Informe final**: en 1 mes con causa raiz, impacto y medidas correctoras.

Desde la vista de un incidente marcado como 'significativo NIS2', se puede
generar el borrador de notificacion en formato requerido.
""",
    },

    # ------------------------------------------------------------------
    # ONBOARDING / CONFIGURACION INICIAL
    # ------------------------------------------------------------------
    {
        "keywords": [
            "onboarding", "configuracion inicial", "primeros pasos", "setup",
            "wizard", "empezar", "comenzar", "nuevo organizacion",
        ],
        "title": "Onboarding — configuracion inicial de la organizacion",
        "content": """
## Onboarding — configuracion inicial

### Que es
El wizard de Onboarding guia al administrador en la configuracion inicial de RiskHub
para una nueva organizacion. Se activa automaticamente en el primer inicio de sesion
si el sistema detecta que la organizacion no tiene configuracion basica.

### Pasos del wizard
1. **Nombre y perfil**: nombre de la organizacion, sector, numero de empleados.
2. **Contexto del SGSI**: definir el alcance del SGSI (que sistemas y procesos incluye),
   las fronteras organizacionales y el apetito de riesgo (0-8).
3. **Metodologia**: seleccionar ISO 27005, MAGERIT v3 o combinado.
4. **Frameworks normativos**: seleccionar las normativas aplicables
   (ISO 27001, NIS2, GDPR, ENS, NIST, PCI-DSS, etc.).
5. **Primer activo**: registrar al menos un activo critico para empezar.
6. **Configuracion del agente IA**: pegar la API key de Anthropic (opcional pero recomendado).
7. **Email / Alertas**: configurar SMTP para notificaciones (opcional).

### Configuracion del contexto del SGSI (posterior)
Si ya se completo el onboarding, el contexto se gestiona desde **Contexto** en el menu:
- Alcance y fronteras del SGSI.
- Apetito de riesgo.
- Metodologia activa.
- Frameworks normativos activos.
- Nivel ENS (bajo/medio/alto) si aplica.
- Respuestas al cuestionario IA organizacional.
""",
    },

    # ------------------------------------------------------------------
    # SOA VERSIONS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "soa", "statement of applicability", "declaracion de aplicabilidad",
            "version soa", "soa versions", "versionado soa", "historico soa",
        ],
        "title": "Versionado del Statement of Applicability (SoA)",
        "content": """
## Versionado del Statement of Applicability (SoA)

### Que es el SoA
El Statement of Applicability (Declaracion de Aplicabilidad) es un documento obligatorio
de ISO 27001 (Anexo A) que declara, para cada control de ISO 27002:
- Si es aplicable o no aplicable a la organizacion.
- La justificacion de la decision.
- El estado de implementacion.

### Gestion del SoA en RiskHub
En **Compliance > SoA** se gestiona el estado de cada control:
- Aplicable / No aplicable + justificacion.
- Estado: planned / partial / implemented / audited.
- Porcentaje de completitud.
- Responsable asignado.
- Evidencias adjuntas.

### Versionado
RiskHub mantiene un historico de versiones del SoA completo:
- Cada vez que se aprueba formalmente el SoA, se crea una snapshot con fecha y autor.
- Las versiones anteriores se conservan para trazabilidad en auditorias.
- En **SoA Versions** se pueden comparar versiones y ver que cambio entre ellas.

### Regwatch y el SoA
Cuando Regwatch detecta un cambio normativo que afecta a controles ISO 27002,
los requisitos afectados se marcan con `regwatch_review_at` para que el responsable
revise si el estado del control en el SoA debe actualizarse.
""",
    },

    # ------------------------------------------------------------------
    # REPORT SCHEDULES
    # ------------------------------------------------------------------
    {
        "keywords": [
            "informe programado", "report schedule", "programar informe", "automatico informe",
            "envio automatico", "scheduled report", "informe periodico",
        ],
        "title": "Programacion de informes automaticos",
        "content": """
## Programacion de informes automaticos (Report Schedules)

### Que es
El modulo Report Schedules permite configurar la generacion y envio automatico
de informes de RiskHub en intervalos regulares.

### Como configurar un informe programado
1. Ir a **Informes > Programar informe**.
2. Seleccionar el tipo de informe (postura de seguridad, riesgos, proveedores, compliance, etc.).
3. Configurar la frecuencia: diario, semanal, mensual, trimestral.
4. Definir los destinatarios (emails separados por comas).
5. Opcionalmente, aplicar filtros (periodo, framework, activo, etc.).
6. Activar el schedule.

### Informes disponibles para programar
- Informe mensual de postura de seguridad (KPIs ejecutivos).
- Informe de riesgos criticos activos.
- Informe de cumplimiento por framework.
- Informe de proveedores con score bajo.
- Informe de tareas vencidas.

### Prerrequisito
Para el envio por email es necesario tener configurado el servidor SMTP
en Alertas > Configuracion de email.
""",
    },

    # ------------------------------------------------------------------
    # VENDOR TEMPLATES — EDITOR DE PLANTILLAS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "plantilla proveedor", "vendor template", "editor plantilla", "cuestionario plantilla",
            "crear plantilla", "clonar plantilla", "preguntas cuestionario",
        ],
        "title": "Editor de plantillas de cuestionario de proveedores",
        "content": """
## Editor de plantillas de cuestionario de proveedores

### Que es
El editor de plantillas permite crear, clonar y personalizar los cuestionarios
que se envian a los proveedores para evaluar su postura de seguridad.

### Plantillas del sistema (7 predefinidas, de solo lectura)
1. Seguridad general (ISO 27001)
2. Proveedores cloud / SaaS
3. Proveedores con acceso a datos personales (GDPR)
4. Infraestructura critica (NIS2)
5. Servicios financieros (DORA)
6. Desarrollo de software
7. BCP / Continuidad

Estas plantillas no se pueden eliminar pero si clonar para personalizarlas.

### Crear una plantilla personalizada
1. Ir a **Proveedores > Plantillas de cuestionario** (icono en el hub de proveedores).
2. Clonar una plantilla existente o crear desde cero.
3. Editar preguntas: cada pregunta tiene tipo (texto, si/no, escala, multiple) y peso de scoring.
4. Asignar controles ISO 27002 a cada pregunta para el scoring ponderado.
5. Guardar y publicar la plantilla para usarla en nuevos cuestionarios.

### Scoring ponderado
Cada pregunta tiene un peso (0-100). La respuesta del proveedor se pondera
segun ese peso para calcular el score final del cuestionario (0-100).
Las respuestas 'no' o 'no aplica' en preguntas de alto peso impactan significativamente el score.
""",
    },

    # ------------------------------------------------------------------
    # INBOX — BANDEJA DE NOTIFICACIONES
    # ------------------------------------------------------------------
    {
        "keywords": [
            "inbox", "bandeja", "notificaciones", "notificacion", "pendiente revision",
            "cambio normativo pendiente", "entrada",
        ],
        "title": "Inbox — bandeja de notificaciones y eventos",
        "content": """
## Inbox

### Que es
El Inbox es la bandeja de entrada de notificaciones importantes que requieren
atencion del administrador o analista.

### Tipos de items en el Inbox
- **Regwatch**: cambios normativos detectados que requieren revision del SGSI.
- **KRI en breach**: indicador de riesgo que ha superado el umbral critico.
- **Proveedor**: vencimiento de evaluacion TPRM o hallazgo critico nuevo.
- **Politica**: politica con fecha de revision vencida.
- **Evidencia**: evidencia proxima a vencer o vencida.

### Gestion de items
Para cada item del inbox se puede:
- **Revisar**: ver el detalle del evento y el impacto calculado.
- **Actuar**: ir directamente al elemento afectado para tomar accion.
- **Posponer (snooze)**: marcar para revisarlo en N dias.
- **Descartar**: cerrar el item con justificacion si no requiere accion.

### Acceso
El Inbox es accesible desde el icono de notificaciones en la barra superior de la app,
o desde **Inbox** en el menu lateral. Los items sin leer se muestran con un badge numerico.
""",
    },

    # ------------------------------------------------------------------
    # CALENDAR
    # ------------------------------------------------------------------
    {
        "keywords": [
            "calendario", "calendar", "vencimientos", "fechas", "planificacion",
            "agenda", "proximas actividades",
        ],
        "title": "Calendario del SGSI",
        "content": """
## Calendario del SGSI

### Que es
El Calendario muestra una vista consolidada de todos los vencimientos y actividades
planificadas del SGSI en un formato de calendario mensual/semanal.

### Que aparece en el calendario
- Fechas de vencimiento de tareas de tratamiento.
- Fechas de revision de politicas.
- Auditorias programadas (inicio y fin).
- Cuestionarios de proveedores con fecha limite.
- Fechas de expiracion de evidencias.
- Ejercicios BCP/BCM planificados.
- Campanas de awareness con fecha limite.
- Informes programados (report schedules).
- Fechas de vencimiento de KRIs en breach.

### Filtros
Se puede filtrar el calendario por tipo de evento, responsable o modulo.

### Uso recomendado
Revisar el calendario semanalmente para anticipar vencimientos y planificar
la carga de trabajo del equipo de seguridad.
""",
    },

    # ------------------------------------------------------------------
    # ISMS DOCUMENTS (diferente de IA Documentos)
    # ------------------------------------------------------------------
    {
        "keywords": [
            "isms document", "documentos isms", "documento sgsi", "politica documento",
            "procedimiento documento", "gestion documental", "jerarquia documental",
        ],
        "title": "Gestion documental del SGSI (ISMS Documents)",
        "content": """
## Gestion documental del SGSI (ISMS Documents)

### Diferencia con IA > Documentos
- **IA > Documentos** (ai-documents): documentos subidos para indexacion RAG
  y analisis IA. Se usan para que el agente pueda responder preguntas sobre su contenido.
- **ISMS Documents**: el repositorio documental formal del SGSI, con jerarquia,
  versionado y flujo de aprobacion. Son los documentos 'vivos' del sistema de gestion.

### Jerarquia documental ISO 27001
El sistema soporta 4 niveles jerarquicos:
- **Nivel 1 — Politica**: politicas de alto nivel (Politica de Seguridad PSI, etc.).
- **Nivel 2 — Norma/Estandar**: normas que desarrollan las politicas.
- **Nivel 3 — Procedimiento**: procedimientos operativos detallados.
- **Nivel 4 — Instruccion tecnica**: instrucciones tecnicas especificas.

Un documento de nivel 2 o inferior debe referenciar al documento de nivel superior
que lo ampara (campo `parent_policy_id`).

### Funcionalidades
- Crear, editar y versionar documentos con control de cambios.
- Flujo de aprobacion formal (draft > revision > aprobado > publicado).
- Checkout exclusivo: cuando un usuario edita un documento, queda bloqueado
  para otros (auto-release tras 4 horas de inactividad).
- Vinculacion a controles ISO 27002 que el documento implementa (`intended_controls`).
- Exportacion a PDF con formato corporativo.

### Diferencia con el modulo Politicas
**Politicas** es el modulo principal para gestionar politicas de seguridad.
**ISMS Documents** es el repositorio completo que incluye politicas + procedimientos
+ instrucciones tecnicas en su jerarquia completa.
""",
    },

    # ------------------------------------------------------------------
    # AUDIT LOG
    # ------------------------------------------------------------------
    {
        "keywords": [
            "audit log", "log auditoria", "log de auditoria", "trazabilidad",
            "quien hizo que", "historial acciones", "registro actividad",
            "inmutable", "quién hizo qué", "auditoria usuarios",
        ],
        "title": "Log de auditoria — trazabilidad de acciones",
        "content": """
## Log de auditoria

### Que es
El Log de Auditoria registra de forma inmutable todas las acciones relevantes
realizadas en RiskHub: creaciones, modificaciones, eliminaciones, accesos y exportaciones.

### Acceso
En **Auditoria** (menu lateral, seccion de administracion) se puede visualizar
el historial completo de acciones con filtros por:
- Usuario que realizo la accion.
- Tipo de accion (crear, modificar, eliminar, exportar, acceder, etc.).
- Modulo afectado (riesgos, incidentes, proveedores, etc.).
- Rango de fechas.

### Que se registra
- Creacion, modificacion y eliminacion de cualquier entidad del sistema.
- Cambios de estado de riesgos, incidentes, tareas, politicas.
- Exportaciones de informes y datos.
- Intentos de autenticacion (exitosos y fallidos).
- Cambios de configuracion (API keys, integraciones).
- Acciones del agente IA y herramientas ejecutadas.
- Accesos a documentos sensibles.

### Formato de cada entrada
Cada entrada del log incluye: timestamp UTC, usuario (email + ID), accion,
modulo afectado, ID del elemento afectado y contexto adicional (IP si disponible).

### Inmutabilidad
El log de auditoria es de solo lectura — ningun usuario, ni el superadmin,
puede eliminar o modificar entradas. Es la base de evidencia para auditorias ISO 27001.
""",
    },

    # ------------------------------------------------------------------
    # RISK LEVEL CONFIG
    # ------------------------------------------------------------------
    {
        "keywords": [
            "risk level config", "configuracion niveles", "bandas de riesgo",
            "personalizar matriz", "colores riesgo", "umbrales riesgo",
            "bajo medio alto critico",
        ],
        "title": "Configuracion de niveles de riesgo",
        "content": """
## Configuracion de niveles de riesgo

### Que es
Permite personalizar las bandas de nivel de riesgo para adaptar la escala 0-8
de ISO 27005 a la terminologia y umbrales de la organizacion.

### Configuracion por defecto
- **Bajo**: niveles 0-2 (color verde).
- **Medio**: niveles 3-4 (color amarillo).
- **Alto**: niveles 5-6 (color naranja).
- **Critico**: niveles 7-8 (color rojo).

### Como personalizar
1. Ir a **Configuracion > Niveles de riesgo** (admin).
2. Para cada banda: modificar el label, los umbrales min/max y el color.
3. Guardar — los cambios se aplican inmediatamente en todos los dashboards y heatmaps.

### Caso de uso tipico
Una organizacion con metodologia MAGERIT puede querer usar la terminologia
'Muy bajo / Bajo / Medio / Alto / Muy alto / Critico' con 6 bandas
en lugar de las 4 por defecto.

### Impacto del cambio
El cambio de bandas afecta a la visualizacion y a las alertas, pero NO
recalcula los niveles numericos de los riesgos (que dependen de la matriz ISO 27005).
""",
    },

    # ------------------------------------------------------------------
    # POLICY APPROVALS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "aprobacion politica", "policy approval", "flujo aprobacion", "firma",
            "aprobador", "aprobar politica", "rechazar politica", "approval request",
        ],
        "title": "Flujo de aprobacion formal de politicas",
        "content": """
## Flujo de aprobacion formal de politicas

### Que es
RiskHub incluye un flujo de aprobacion formal para politicas que requieren
validacion explicita de uno o varios aprobadores (ej. CISO, Director, DPO).

### Modos de aprobacion
- **Paralelo**: todos los aprobadores reciben la solicitud al mismo tiempo.
  La politica se aprueba cuando TODOS han aprobado.
- **Secuencial**: los aprobadores reciben la solicitud en orden.
  Cada aprobador debe aprobar antes de que se notifique al siguiente.

### Flujo
1. El redactor finaliza la politica y lanza una solicitud de aprobacion.
2. Especifica los aprobadores (nombre + email) y el modo (paralelo/secuencial).
3. Cada aprobador recibe un email con un enlace unico (token de un solo uso).
4. El aprobador hace clic en el enlace → ve el contenido de la politica → aprueba o rechaza con notas.
5. Cuando todos aprueban → la politica pasa automaticamente a estado 'Aprobada'.
6. Si alguno rechaza → la politica vuelve a 'Borrador' y el redactor recibe notificacion.

### Trazabilidad
Cada decision de aprobacion queda registrada con: nombre del aprobador, fecha,
IP de acceso y notas. Esta informacion es evidencia para auditorias ISO 27001.

### Expiracion de tokens
Los tokens de aprobacion tienen fecha de expiracion configurable.
Si vence sin respuesta, se puede reenviar la solicitud desde RiskHub.
""",
    },

    # ------------------------------------------------------------------
    # ASSET GROUPS
    # ------------------------------------------------------------------
    {
        "keywords": [
            "asset group", "grupo de activos", "agrupacion activos", "categoria activos",
            "organizar activos", "dominio activos",
        ],
        "title": "Grupos de activos",
        "content": """
## Grupos de activos

### Que es
Los grupos de activos permiten organizar el inventario en colecciones logicas
para facilitar la gestion, los informes y la aplicacion de controles por grupo.

### Casos de uso tipicos
- Agrupar activos por sede (Madrid, Barcelona, Cloud).
- Agrupar por entorno (produccion, desarrollo, test).
- Agrupar por dominio de negocio (Finanzas, RRHH, Operaciones).
- Agrupar por clasificacion de datos (datos personales, datos financieros).

### Creacion de un grupo
1. Ir a **Activos > Grupos** desde la vista de activos.
2. Crear nuevo grupo: nombre, descripcion, criterio de agrupacion.
3. Asignar activos al grupo (manualmente o con reglas automaticas basadas en tipo o etiqueta).

### Beneficios
- Filtrar el heatmap de riesgos por grupo de activos.
- Generar informes de riesgo segmentados por grupo.
- Aplicar controles o politicas a un grupo completo.
- Visualizar la exposicion de riesgo por dominio de negocio.
""",
    },

    # ------------------------------------------------------------------
    # HEATMAP
    # ------------------------------------------------------------------
    {
        "keywords": [
            "heatmap", "mapa de calor", "matriz de riesgo", "cuadrante", "burbuja",
            "visualizacion riesgos", "grafico riesgo",
        ],
        "title": "Heatmap — mapa de calor de riesgos",
        "content": """
## Heatmap — mapa de calor de riesgos

### Que es
El Heatmap es la representacion visual de todos los riesgos activos sobre la
matriz probabilidad x impacto (5x5) de ISO 27005.

### Como leer el heatmap
- **Eje X (horizontal)**: consecuencia / impacto (0=minimo, 4=catastrofico).
- **Eje Y (vertical)**: probabilidad / likelihood (0=muy rara, 4=casi segura).
- **Cada burbuja**: un riesgo del registro. El tamano puede indicar el numero de activos afectados.
- **Color**: nivel de riesgo (verde=bajo, amarillo=medio, naranja=alto, rojo=critico).
- **Zona roja** (esquina superior derecha): riesgos que exceden el apetito de riesgo.

### Interaccion
- Hacer clic en una burbuja muestra el detalle del riesgo.
- Filtros disponibles: activo, amenaza, propietario, estado, nivel ENS.
- Toggle: ver riesgo inherente o residual.

### Heatmap por activo o por grupo
En la vista de un activo especifico, el heatmap muestra solo los riesgos de ese activo.
En Asset Groups se puede ver el heatmap agregado por grupo.

### Uso en auditorias
El heatmap es una de las evidencias visuales mas valoradas en auditorias ISO 27001.
Se puede exportar como imagen PNG desde el boton de descarga.
""",
    },

    # ------------------------------------------------------------------
    # MAGERIT DETALLADO
    # ------------------------------------------------------------------
    {
        "keywords": [
            "magerit", "magerit v3", "valoracion activo", "degradacion", "frecuencia",
            "dimension magerit", "trazabilidad magerit", "autenticidad",
            "metodologia magerit",
        ],
        "title": "Metodologia MAGERIT v3 — detalle",
        "content": """
## Metodologia MAGERIT v3 — detalle

### Que es MAGERIT
MAGERIT (Metodologia de Analisis y Gestion de Riesgos de los Sistemas de Informacion)
es la metodologia de analisis de riesgos del gobierno espanol, obligatoria para
el ENS (Esquema Nacional de Seguridad) y muy usada en el sector publico espanol.

### Diferencias clave con ISO 27005
- **ISO 27005**: consecuencia x probabilidad (escala 0-4 cada una → nivel 0-8).
- **MAGERIT**: valor del activo por dimension CIA x frecuencia de amenaza x degradacion potencial.
  El riesgo = valor x frecuencia x degradacion (escala 1-10).

### Dimensiones MAGERIT
Cada activo se valora en 5 dimensiones (de 0 a 10):
- **C — Confidencialidad**: impacto de la divulgacion no autorizada.
- **I — Integridad**: impacto de la modificacion no autorizada.
- **A — Disponibilidad**: impacto de la no disponibilidad.
- **Au — Autenticidad**: impacto de la imposibilidad de verificar la identidad del origen.
- **T — Trazabilidad**: impacto de no poder rastrear quie accedio o modifico.

### Vista MAGERIT en RiskHub
En **MAGERIT** (menu lateral) se muestra:
- Valoracion de activos por dimension.
- Mapa de amenazas con frecuencia estimada y degradacion por dimension.
- Nivel de riesgo calculado por dimension y activo.
- Comparativa de riesgo inherente vs. residual por dimension.

### Cuando usar MAGERIT en vez de ISO 27005
- Organizaciones del sector publico espanol (ENS obligatorio).
- Cuando se necesita valorar el riesgo por dimension CIA de forma independiente.
- Cuando el marco regulatorio o el cliente exige expresamente MAGERIT.
En modo combinado, RiskHub usa la estructura ISO 27005 pero incorpora los valores MAGERIT.
""",
    },

    # ------------------------------------------------------------------
    # VENDOR ASSESSMENTS DETALLADO
    # ------------------------------------------------------------------
    {
        "keywords": [
            "vendor assessment", "evaluacion consolidada", "assessment consolidado",
            "score por dominio", "push risk register", "aprobar evaluacion",
            "evaluacion formal proveedor", "assessment proveedor",
        ],
        "title": "Evaluaciones consolidadas de proveedores (VendorAssessments)",
        "content": """
## Evaluaciones consolidadas de proveedores

### Que es
Una VendorAssessment es una evaluacion formal y consolidada de un proveedor
que agrega los resultados de uno o varios cuestionarios TPRM con el score inherente
y los hallazgos abiertos para producir una decision de riesgo documentada.

### Estructura de la evaluacion
- **Score por dominio**: el sistema calcula un score (0-100) para cada dominio
  evaluado (gobernanza, seguridad tecnica, datos personales, continuidad, etc.).
- **Score global**: media ponderada de los scores por dominio.
- **Recomendacion**: approve / conditional_approve / reject.
- **Hallazgos criticos**: lista de VendorIssues que deben resolverse.

### Flujo de evaluacion
1. Crear la evaluacion desde Proveedores > [Proveedor] > Nueva evaluacion.
2. Vincular los cuestionarios respondidos que forman la base de la evaluacion.
3. El sistema calcula automaticamente los scores por dominio.
4. El evaluador revisa, ajusta si es necesario y registra la decision final.
5. **Aprobar**: el proveedor queda clasificado como evaluado.
6. **Push to Risk Register**: los hallazgos criticos se convierten en riesgos ISO 27005
   en el registro de riesgos de la organizacion.

### Periodicidad recomendada
- **Tier 1 (critico)**: evaluacion completa anual, revision de hallazgos trimestral.
- **Tier 2 (importante)**: evaluacion completa cada 2 anos.
- **Tier 3 (estandar)**: cuestionario simplificado cada 3 anos.
""",
    },

    # ------------------------------------------------------------------
    # VENDOR ISSUES DETALLADO
    # ------------------------------------------------------------------
    {
        "keywords": [
            "vendor issue", "hallazgo proveedor", "issue proveedor", "finding proveedor",
            "sla hallazgo", "critico proveedor", "remediar proveedor",
        ],
        "title": "Hallazgos de proveedores (VendorIssues)",
        "content": """
## Hallazgos de proveedores (VendorIssues)

### Que es
Los VendorIssues son hallazgos de seguridad especificos identificados en un proveedor,
ya sea durante la evaluacion TPRM, la revision IA del cuestionario, o detectados manualmente.

### Severidades y SLA automatico
El sistema asigna automaticamente un SLA de resolucion segun la severidad:
- **Critical**: 48 horas para iniciar la mitigacion.
- **High**: 7 dias.
- **Medium**: 30 dias.
- **Low**: 90 dias.

La fecha de vencimiento del SLA se calcula automaticamente al crear el hallazgo.

### Estados del ciclo de vida
open > in_remediation > mitigated > verified > closed / accepted / risk_transferred.

### Como se crean los hallazgos
1. **Automaticamente** por la revision IA del cuestionario (AI Review).
2. **Automaticamente** al aprobar una evaluacion consolidada con hallazgos criticos.
3. **Manualmente** desde la vista del proveedor > Hallazgos > Nuevo hallazgo.

### Alertas por vencimiento de SLA
El scheduler verifica diariamente los hallazgos con SLA vencido y:
- Genera una alerta en el Inbox.
- Notifica al responsable por email (si SMTP configurado).
- Escala al evaluador supervisor si pasa 48h adicionales sin accion.

### Vista consolidada
En **Proveedores > Hallazgos** se muestra el listado global de todos los hallazgos
de todos los proveedores, con filtros por severidad, estado, proveedor y vencimiento.
""",
    },

    # ------------------------------------------------------------------
    # CONTEXT / SGSI SETUP
    # ------------------------------------------------------------------
    {
        "keywords": [
            "contexto sgsi", "context", "alcance sgsi", "fronteras", "apetito riesgo configurar",
            "metodologia configurar", "frameworks activos", "ens nivel", "cuestionario ia",
        ],
        "title": "Configuracion del contexto del SGSI",
        "content": """
## Configuracion del contexto del SGSI

### Que es
La seccion **Contexto** (menu lateral) es el punto central de configuracion del SGSI.
Define los parametros que el motor de riesgo, el agente IA y los dashboards usan
como base para todos los calculos y recomendaciones.

### Campos principales
- **Nombre de la organizacion**: nombre oficial que aparece en informes.
- **Alcance del SGSI**: descripcion de que sistemas, procesos y ubicaciones
  estan dentro del perimetro del SGSI (clausula 4.3 ISO 27001).
- **Fronteras organizacionales**: que queda fuera del alcance y por que.
- **Apetito de riesgo** (0-8): nivel maximo de riesgo residual que la organizacion
  acepta conscientemente. Riesgos por encima de este nivel requieren tratamiento obligatorio.
- **Metodologia**: ISO 27005 / MAGERIT v3 / Combinado.
- **Frameworks normativos activos**: ISO 27001, NIS2, GDPR, ENS, NIST, PCI-DSS, HIPAA, SOC 2.
- **Nivel ENS**: bajo / medio / alto (solo si ENS esta activo).
- **Cuestionario IA**: respuestas al cuestionario organizacional que el agente IA usa
  como contexto (sector, empleados, sistemas, tipo de datos, historial de incidentes, etc.).

### Por que es importante configurar bien el contexto
- El agente IA usa el contexto para personalizar sus analisis y recomendaciones.
- El motor de calculo usa el apetito de riesgo para determinar que riesgos
  requieren tratamiento obligatorio.
- El scoring de compliance se calcula sobre los frameworks activos seleccionados.
- Los dashboards NIS2, ENS, etc. solo aparecen si el framework esta activo.
""",
    },

]


# ---------------------------------------------------------------------------
# Motor de busqueda por keywords
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "como", "con", "que", "del", "los", "las", "una", "uno", "para",
    "por", "son", "ser", "hay", "del", "sus", "les", "tiene", "esta",
    "este", "ese", "esa", "mas", "muy", "sin", "sobre", "entre", "todo",
    "cuando", "donde", "quien", "cuanto", "cuantos", "cada", "solo",
    "from", "with", "that", "this", "what", "when", "where", "how",
    "the", "and", "are", "for", "not", "all", "has",
}


def _normalize(text: str) -> str:
    """Normaliza texto para comparacion: minusculas, sin acentos, sin puntuacion."""
    text = text.lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n",
        "à": "a", "è": "e", "ì": "i", "ò": "o", "ù": "u",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def search_app_knowledge(query: str, max_sections: int = 3) -> list[dict]:
    """
    Busca en la base de conocimiento las secciones mas relevantes para la consulta.
    Devuelve una lista de dicts con 'title' y 'content'.
    """
    if not query or not query.strip():
        return []

    normalized_query = _normalize(query)
    # Tokens: 3+ chars y no stopword; palabras de 1-2 chars siempre se descartan
    tokens = [
        t for t in re.split(r"[\s,;.!?¿¡()\"\']+", normalized_query)
        if len(t) >= 3 and t not in _STOPWORDS
    ]
    if not tokens:
        return []

    scored: list[tuple[int, dict]] = []
    for section in _KNOWLEDGE:
        score = 0
        normalized_kws = [_normalize(kw) for kw in section["keywords"]]
        for token in tokens:
            for kw in normalized_kws:
                if token == kw:
                    score += 3          # match exacto — peso alto
                elif len(token) >= 3 and (token in kw or kw in token):
                    score += 1          # match parcial — solo si el token tiene sustancia
        if score > 0:
            scored.append((score, section))

    # Ordenar por score descendente y devolver los top max_sections
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:max_sections]]


def format_knowledge_sections(sections: list[dict]) -> str:
    """Formatea las secciones encontradas para inyectar en el contexto del agente."""
    if not sections:
        return ""
    lines = ["\n## Manual funcional de RiskHub — secciones relevantes"]
    for sec in sections:
        lines.append(f"\n### {sec['title']}")
        lines.append(sec["content"].strip())
    return "\n".join(lines)
