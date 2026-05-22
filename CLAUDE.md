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
- **IA**: No incluida en v1.0. Se anadira en v1.1 con Ollama local.
- **Branding**: Paleta purple `#59008D` / orange `#D65200`. Variables CSS: `--brand-purple`, `--brand-orange`. Tipografia: Inter.

## Estado actual (v1.0)

### Backend

- [x] Modelos ISO 27005 (`app/models.py`)
- [x] Esquemas Pydantic (`app/schemas.py`)
- [x] Motor de calculo (`app/services/risk_engine.py`): matriz 5x5 ISO 27005 Annex E.2
- [x] 27 endpoints REST en `app/routers/`
- [x] Catalogos precargados: 49 amenazas, 67 vulnerabilidades, 93 controles ISO 27002
- [x] Seed inicial: admin + contexto + catalogos

### Frontend

- [x] SPA hash-based (`app/static/`)
- [x] Vistas: dashboard, heatmap, assets, threats, vulnerabilities, risks, controls, reports, context, users

### Despliegue

- [x] Dockerfile (python 3.11-slim, healthcheck, usuario no root)
- [x] docker-compose.yml (volumen persistente, red interna, puerto 80)
- [x] deploy.sh para actualizaciones desde GitHub

## Pendiente

### v1.0 (cierre)
- [ ] Descargar fuentes Inter a `app/static/vendor/fonts/`
- [ ] Pruebas end-to-end manuales en produccion

### v1.1
- [ ] **Cuestionarios** para generar cruces activo x amenaza
- [ ] **Agente IA** (Ollama local + Claude API opcional)
- [ ] **Auditoria** visible (modelo `AuditLog` ya existe, falta UI)
- [ ] LDAP/SAML SSO
- [ ] Multi-idioma (en/es/de/fr)
- [ ] Risk Treatment Plan PDF detallado

## Convenciones

- **Naming**: ingles para identificadores, terminos ISO 27005 en ingles.
- **UI**: textos en castellano (es-ES).
- **Python**: PEP 8. Funciones cortas.
- **JS**: vanilla JS moderno, sin build step.
- **Sin emojis** en codigo fuente.
- **Comentarios**: castellano para logica ISO; ingles para tecnicismos.

## Estructura

```
riskhub/
├── Dockerfile
├── docker-compose.yml
├── deploy.sh
├── .env.example
├── requirements.txt
└── app/
    ├── main.py
    ├── config.py
    ├── database.py
    ├── models.py
    ├── schemas.py
    ├── security.py
    ├── seed.py
    ├── routers/       # auth, users, assets, catalogues, controls, risks, context, reports
    ├── services/
    │   └── risk_engine.py
    ├── data/          # JSON catalogos ISO 27005 / ISO 27002
    └── static/
        ├── login.html
        ├── index.html
        ├── css/app.css
        ├── img/logo.svg
        └── js/        # api.js, auth.js, ui.js, app.js, views/
```

## Como continuar

1. Lee este archivo.
2. Verifica localmente: `uvicorn app.main:app --reload --port 8000`
3. Para deploy: `git push origin main` y luego `bash /opt/riskhub/deploy.sh` en el servidor.
