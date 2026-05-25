# RiskHub

Plataforma de **gestion del riesgo de seguridad de la informacion**
basada en **ISO/IEC 27005:2018**, con catalogo de controles **ISO/IEC 27002:2022**
y agente de IA integrado.

Disenada para correr **on-premise**, sin dependencias de internet, en un servidor
interno. Multi-usuario con roles diferenciados.

---

## Caracteristicas

- **Inventario de activos** (CRUD + import/export CSV/XLSX) segun ISO 27005 Annex B
  (activos primarios vs activos de soporte, valoracion CIA + autenticidad + trazabilidad).
- **Catalogo de amenazas** ISO 27005 Annex C precargado (49 amenazas tipicas)
  + amenazas personalizadas.
- **Catalogo de vulnerabilidades** ISO 27005 Annex D precargado (67 vulnerabilidades)
  + vulnerabilidades personalizadas.
- **Catalogo de controles** ISO/IEC 27002:2022 precargado (los 93 controles del Anexo A)
  + controles personalizados y sus implementaciones concretas con estado y madurez.
- **Riesgos** = activo x amenaza con calculo automatico inherent/residual segun
  matriz 5x5 ISO 27005 Annex E.2 (escala 0-8).
- **Heatmap** interactivo modo inherente / residual.
- **Tratamiento** ISO 27005 cl. 9: modificacion / retencion / evitacion / transferencia.
- **Aceptacion** formal con trazabilidad (quien y cuando).
- **Multi-usuario** con tres roles: `admin`, `analyst`, `viewer`.
- **Informes PDF** con branding personalizable: Risk Register, Statement of Applicability.
- **Agente IA** (Claude API): chat conversacional, sugerencias de riesgos y controles,
  RAG sobre documentacion interna del SGSI, anonimizacion configurable.
- **Gestion de proveedores, no conformidades, incidentes, tareas, politicas** y mas.
- **Branding**: paleta purple `#59008D` / orange `#D65200`. Tipografia Inter (local, sin CDN).

---

## Stack tecnico

| Capa | Tecnologia |
|------|-----------|
| Backend | Python 3.11 + FastAPI + SQLAlchemy 2.0 |
| Base de datos | SQLite (por defecto) o PostgreSQL |
| Frontend | HTML + CSS + Vanilla JS (sin frameworks ni CDNs) |
| PDF | ReportLab |
| Importacion | pandas + openpyxl |
| Auth | JWT (HS256) + bcrypt |
| IA | Claude API (Anthropic) + RAG FTS5 |
| Despliegue | Docker + docker compose |

Todo el stack es libre y autocontenido. Cero dependencias externas en runtime
(salvo la API de IA, que es opcional).

---

## Despliegue rapido con Docker

Requisitos: **Docker 20.10+** y **docker compose**.

```bash
# 1. Clonar el repositorio
git clone https://github.com/ezequielwolf22/riskhub.git
cd riskhub

# 2. Crear el archivo .env
cp .env.example .env
nano .env   # rellenar RISKHUB_SECRET_KEY y RISKHUB_ADMIN_PASSWORD

# Genera una clave secreta segura:
python3 -c "import secrets; print(secrets.token_urlsafe(64))"

# 3. Arrancar
docker compose up -d

# 4. Verificar
curl http://localhost/api/health
```

La aplicacion estara disponible en `http://localhost` (puerto configurable
en `.env` con `RISKHUB_PORT_HOST`).

**Login inicial**: el email/password configurados en `.env`. **Cambia la contrasena en el
primer inicio de sesion**.

### Datos persistentes

Los datos se guardan en el volumen Docker `riskhub-data` (`/srv/data` dentro
del contenedor). Backup recomendado:

```bash
docker run --rm -v riskhub-data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/riskhub-$(date +%F).tar.gz /data
```

---

## Despliegue sin Docker (desarrollo)

Requisitos: **Python 3.11+**.

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/Mac
# .venv\Scripts\activate       # Windows

pip install -r requirements.txt

export RISKHUB_SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(64))")
export RISKHUB_ADMIN_EMAIL=admin@company.internal
export RISKHUB_ADMIN_PASSWORD=ChangeMe123!

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## Configuracion (variables de entorno)

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `RISKHUB_SECRET_KEY` | (obligatoria) | Clave para firmar JWT. Min 32 caracteres. |
| `RISKHUB_ADMIN_EMAIL` | `admin@company.internal` | Email del admin inicial. |
| `RISKHUB_ADMIN_PASSWORD` | (obligatoria) | Contrasena del admin inicial. |
| `RISKHUB_DB_PATH` | `./riskhub.db` | Ruta de la BD SQLite. |
| `RISKHUB_DATABASE_URL` | (vacio) | Si se especifica, se ignora `DB_PATH`. Ej: `postgresql://user:pass@host/db`. |
| `RISKHUB_JWT_EXPIRES_MINUTES` | 480 | Duracion del token (8h). |
| `RISKHUB_ENV` | `development` | `production` desactiva CORS abierto. |
| `RISKHUB_ANTHROPIC_API_KEY` | (opcional) | Clave API de Claude para el agente IA. |

---

## Logo

Coloca tu logo en `app/static/img/logo.svg`. El archivo actual es el logo
por defecto de RiskHub. Para usar tu logo corporativo:

1. Sustituye `app/static/img/logo.svg` por tu SVG (mantén el nombre del archivo).
2. Reinicia el contenedor: `docker compose restart`.

---

## Tipografia

El producto usa **Inter** como tipografia principal. Las fuentes deben servirse
en local (sin CDN).

```bash
mkdir -p app/static/vendor/fonts && cd app/static/vendor/fonts
# Descarga las fuentes Inter desde https://rsms.me/inter/
# y copia los archivos:
#   Inter-Regular.woff2  Inter-Medium.woff2  Inter-Bold.woff2
#   JetBrainsMono-Regular.woff2
```

Si no se sirven fuentes locales, el navegador hace fallback al stack del
sistema (San Francisco / Segoe UI / Arial). La app sigue funcionando.

---

## Roles y permisos

| Rol | Permisos |
|-----|----------|
| `viewer` | Lectura completa de todas las vistas. No puede modificar nada. |
| `analyst` | viewer + CRUD de activos, riesgos, controles, amenazas/vulns custom. |
| `admin` | analyst + gestion de usuarios y contexto del SGSI. |

Para crear usuarios, entra como admin y ve a `#/users`.

---

## Estructura del proyecto

```
riskhub/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── README.md
├── CLAUDE.md                       # Contexto para continuar en Claude Code
└── app/
    ├── main.py                     # Entrypoint FastAPI
    ├── config.py                   # Variables de entorno
    ├── database.py                 # Sesion SQLAlchemy
    ├── models.py                   # Modelos ISO 27005
    ├── schemas.py                  # Pydantic DTOs
    ├── security.py                 # JWT + bcrypt
    ├── seed.py                     # Carga inicial admin + catalogos
    ├── routers/
    │   ├── auth.py                 # Login + /me
    │   ├── users.py                # Gestion usuarios
    │   ├── assets.py               # CRUD + import CSV/Excel
    │   ├── catalogues.py           # Amenazas + vulnerabilidades
    │   ├── controls.py             # ISO 27002 + implementaciones
    │   ├── risks.py                # Riesgos + heatmap + stats
    │   ├── context.py              # Contexto SGSI
    │   ├── reports.py              # PDFs
    │   ├── ai.py                   # Agente IA + chat + RAG
    │   ├── ai_config.py            # Configuracion agente IA
    │   └── documents.py            # Documentos RAG del agente
    ├── services/
    │   ├── risk_engine.py          # Matriz 5x5, calc inherent/residual
    │   ├── context_builder.py      # Contexto para llamadas IA
    │   ├── rag_service.py          # Busqueda semantica FTS5
    │   ├── document_service.py     # Extraccion + chunking de documentos
    │   └── anonymizer.py          # Anonimizacion PII antes de llamadas IA
    ├── data/
    │   ├── threats_iso27005.json   # 49 amenazas
    │   ├── vulnerabilities_iso27005.json  # 67 vulns
    │   └── controls_iso27002_2022.json    # 93 controles
    └── static/
        ├── login.html
        ├── index.html              # SPA principal
        ├── css/app.css
        ├── img/logo.svg
        ├── vendor/fonts/           # Inter + JetBrains Mono
        └── js/
            ├── api.js              # Cliente HTTP
            ├── auth.js             # Sesion
            ├── ui.js               # Helpers UI
            ├── app.js              # Router SPA
            └── views/              # Una vista por seccion
```

---

## Despliegue en produccion (hardening)

Resumen de buenas practicas para entornos productivos:

1. VM Ubuntu 24.04 LTS, 2 vCPU / 4 GB RAM / 40 GB disco.
2. SSH solo con clave (no password).
3. Firewall: solo 22 (SSH) y 443/80 (HTTPS/HTTP).
4. Docker + docker compose instalados.
5. Reverse proxy (Caddy o nginx) con TLS.
6. `RISKHUB_ENV=production` en `.env`.
7. Backup nocturno del volumen `riskhub-data`.

---

## Comparativa con productos comerciales

| Capacidad | RiskHub | SAI360 | PILAR (CCN-CERT) | OneTrust |
|-----------|:-------:|:------:|:----------------:|:--------:|
| ISO 27005 nativo | si | si | si (MAGERIT) | parcial |
| Catalogos precargados | si | si | si | si |
| Heatmap interactivo | si | si | si | si |
| On-premise | si | parcial | si | no |
| Codigo abierto / auditable | si | no | no | no |
| Agente IA integrado | si | parcial | no | parcial |
| Coste de licencia | 0 | alto | gratis (sector publico ES) | alto |
| Branding personalizado | si | limitado | no | si |

---

## Roadmap

- [ ] SuperAdmin con control de licenciamiento y activacion de modulos.
- [ ] OIDC/SAML SSO (Microsoft Entra, Google Workspace).
- [ ] Integracion SharePoint para importar documentacion SGSI en masa.
- [ ] Integraciones SAP / Jagger / Sphera.
- [ ] Extraccion automatica de clausulas ISO desde documentos de politicas.
- [ ] Multi-idioma (en/es/de/fr).
- [ ] Workflow de aprobacion de tratamientos con doble firma.

---

## Licencia y soporte

Uso interno. Para incidencias o nuevas funcionalidades, contacta con el
equipo responsable del SGSI.
