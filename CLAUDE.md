# RiskHub - Contexto para Claude Code

## Que es este proyecto

Aplicacion web GRC (Governance, Risk, Compliance) para gestion del riesgo
de seguridad de la informacion, basada en **ISO/IEC 27005:2018** con
catalogo de controles **ISO/IEC 27002:2022**.

**Uso**: on-premise en servidor interno, no expuesta a internet.
Multi-usuario con roles.

## Infraestructura de produccion

- Servidor: Hetzner CX22 — Ubuntu 24.04 — IP 91.99.83.202
- Acceso SSH: `ssh root@91.99.83.202 -i ~/.ssh/id_ed25519`
- App: http://91.99.83.202 via Docker (puerto 80)
- Repo GitHub: github.com/ezequielwolf22/riskhub (privado)
- Deploy: en el servidor ejecutar `bash /opt/riskhub/deploy.sh`

## Decisiones tecnicas

- **Backend**: Python 3.11 + FastAPI + SQLAlchemy 2.0 + SQLite (default) / PostgreSQL (opcional).
- **Frontend**: HTML + Vanilla JS + CSS. Sin frameworks, sin CDNs, todo servido en local.
- **Autenticacion**: JWT (HS256) + bcrypt. Tres roles: `admin`, `analyst`, `viewer`.
- **PDF**: ReportLab con paleta purple/orange.
- **Despliegue**: Docker + docker compose. Volumen `riskhub-data` para BD persistente.
- **IA**: Claude API (Anthropic). RAG con SQLite FTS5. Anonimizacion regex configurable.
- **Branding**: Paleta purple `#59008D` / orange `#D65200`. Variables CSS: `--brand-purple`, `--brand-orange`. Tipografia: Inter.
- **Seguridad**: Rate limiting en memoria, security headers middleware, magic bytes validation, API docs deshabilitados en produccion.

## Estado actual (v1.3.1)

### Backend

- [x] Modelos ISO 27005 (`app/models.py`)
- [x] Esquemas Pydantic (`app/schemas.py`)
- [x] Motor de calculo (`app/services/risk_engine.py`): matriz 5x5 ISO 27005 Annex E.2
- [x] Endpoints REST en `app/routers/` (auth, users, assets, risks, controls, suppliers, incidents, nonconformities, tasks, policies, audits, gdpr, reports, ai, ai_config, documents, admin, audit, alerts, search, context, catalogues)
- [x] Catalogos precargados: 49 amenazas, 67 vulnerabilidades, 93 controles ISO 27002
- [x] Seed inicial: admin + contexto + catalogos
- [x] Agente IA: chat conversacional, RAG FTS5, anonimizacion, feedback loop
- [x] Cifrado Fernet para API key del agente IA
- [x] Hardening OWASP: rate limiting login, security headers, magic bytes upload, autodocs off en produccion

### Frontend

- [x] SPA hash-based (`app/static/`)
- [x] Vistas: dashboard, heatmap, assets, threats, vulnerabilities, risks, controls, reports, context, users, suppliers, incidents, nonconformities, tasks, policies, audits, gdpr, compliance, alerts, integrations, audit, ai-chat, ai-documents, onboarding, guide

### Despliegue

- [x] Dockerfile (python 3.11-slim, healthcheck, usuario no root)
- [x] docker-compose.yml (volumen persistente, red interna, puerto 80, RISKHUB_ENV=production)
- [x] deploy.sh para actualizaciones desde GitHub

## Pendiente

### Proximas funcionalidades
- [ ] SuperAdmin con control de licenciamiento y activacion de modulos por feature flag
- [ ] SSO OIDC/SAML (Microsoft Entra, Google Workspace)
- [ ] Integracion SharePoint (Microsoft Graph API) para importar documentacion SGSI en masa
- [ ] Integraciones SAP / Jagger / Sphera
- [ ] Extraccion automatica de clausulas ISO desde documentos de politicas (IA)
- [ ] Multi-idioma i18n (es/en/de/fr) — decision tomada: selector de idioma en header,
      ficheros `app/static/js/i18n/{es,en}.json`, funcion global `t('key')`.
      Flujo: primero refactorizar vistas a `t()` manteniendo ES, luego anadir EN.
      Diferido hasta que la app este estable.
- [ ] Descargar fuentes Inter a `app/static/vendor/fonts/`
- [ ] Pruebas end-to-end manuales

## Convenciones

- **Naming**: ingles para identificadores, terminos ISO 27005 en ingles.
- **UI**: textos en castellano (es-ES).
- **Python**: PEP 8. Funciones cortas.
- **JS**: vanilla JS moderno, sin build step.
- **Sin emojis** en codigo fuente.
- **Comentarios**: castellano para logica ISO; ingles para tecnicismos.
- **Seguridad**: revisar OWASP antes de añadir funcionalidad que maneje datos del usuario.
- **Vistas nuevas**: siempre actualizar `app/static/js/views/guide.js` con documentacion de la nueva seccion.

## Estructura

```
riskhub/
├── Dockerfile
├── docker-compose.yml
├── deploy.sh
├── .env.example
├── requirements.txt
└── app/
    ├── main.py              # Entrypoint + middleware de seguridad
    ├── config.py
    ├── database.py
    ├── models.py
    ├── schemas.py
    ├── security.py          # JWT + bcrypt + require_role
    ├── seed.py
    ├── middleware/
    │   └── security_headers.py   # X-Content-Type-Options, CSP, etc.
    ├── routers/             # Todos los endpoints REST
    ├── services/
    │   ├── risk_engine.py
    │   ├── audit_service.py
    │   ├── rate_limiter.py  # Brute-force protection en login
    │   ├── rag_service.py
    │   ├── document_service.py
    │   ├── context_builder.py
    │   └── anonymizer.py
    ├── data/                # JSON catalogos ISO 27005 / ISO 27002
    └── static/
        ├── login.html
        ├── index.html
        ├── css/app.css
        ├── img/logo.svg
        └── js/              # api.js, auth.js, ui.js, app.js, views/
```

## Como continuar

1. Lee este archivo.
2. Verifica localmente: `uvicorn app.main:app --reload --port 8000`
3. Para deploy: `git push origin main` y luego `bash /opt/riskhub/deploy.sh` en el servidor.
