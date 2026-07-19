# Auditoría de Seguridad — RiskHub

**Fecha:** 2026-07-19
**Alcance:** Backend (FastAPI/SQLAlchemy), frontend (Vanilla JS), configuración e infraestructura.
**Contexto de despliegue:** on-premise, servidor interno no expuesto a internet, multi-tenant.

Este informe distingue lo que es un riesgo **real y explotable** de lo que son
mejoras de defensa en profundidad o hallazgos que **no aplican** a esta arquitectura.
Cada punto está verificado contra el código real, no contra patrones genéricos.

---

## Postura general: sólida

La aplicación ya implementa buena parte del hardening esperado:

- JWT con `jti` + tabla de revocación (logout real) y refresh tokens con rotación.
- Lockout de login doble (por IP y por cuenta) persistido en SQLite.
- Rate limit global de API por IP.
- bcrypt para contraseñas; política de fortaleza aplicada.
- MFA TOTP con códigos de recuperación de un solo uso.
- Cifrado Fernet en reposo para documentos, secreto MFA y password SMTP.
- Cabeceras de seguridad completas (CSP, HSTS condicional, X-Frame-Options, etc.).
- Uploads con validación de magic bytes + límite de tamaño; nombres saneados.
- `defusedxml` + límite de tamaño en parsers XML (anti-XXE / anti-billion-laughs).
- `.env` correctamente en `.gitignore` y **no** commiteado.
- Multi-tenancy forzado en queries (`filter_by_org` / `check_org_access`).
- Escape de HTML en frontend (`UI.esc`).

---

## Correcciones aplicadas en esta sesión

### 1. [Descartado por retrocompatibilidad] Credenciales por defecto en el código
`app/config.py`

Se probó a hacer `secret_key`/`admin_email`/`admin_password` obligatorios, pero se
**revirtió** para no romper a clientes on-prem existentes: `admin_email`/
`admin_password` son solo de *seed* (`app/seed.py`), así que un cliente en marcha
puede haberlos quitado de su `.env`; hacerlos obligatorios provocaría un crash al
arrancar. La garantía de seguridad real —que **producción** no arranque con un
secreto débil— **ya existe en `app/main.py`** (`sys.exit(1)` en producción si el
secreto es el default o <32 chars) y se mantiene. `config.py` queda como estaba.

### 2. [Defensa en profundidad — NO era inyección explotable] Borrado de organización
`app/routers/organizations.py`

El borrado en cascada interpolaba nombres de tabla con f-string en `text()`. La
lista de tablas es **hardcodeada** (sin input de usuario), por lo que **no era una
inyección SQL explotable**. Aun así se reescribió con construcción segura de
SQLAlchemy (`delete(sql_table(...))`) para eliminar el patrón peligroso.

**Verificado:** el nuevo statement borra exactamente las filas de la org objetivo
(probado sobre SQLite en memoria) — importante porque un fix mal hecho aquí dejaría
datos de un tenant tras "eliminarlo". Se eliminó también el import `text` ya sin uso.

### 3. [Real — riesgo genuino] Falta de rate limiting en el segundo factor (MFA)
`app/routers/auth.py` → `POST /api/auth/mfa/complete`

El login tenía lockout, pero `/mfa/complete` no. Con el primer factor (contraseña)
comprometido, un atacante obtenía un `mfa_token` de 5 min y podía forzar el código
TOTP de 6 dígitos sin límite por cuenta (el rate limit global de 600/min por IP es
insuficiente y se evade rotando IP).

**Fix:** se aplica el mismo lockout doble (IP + `mfa:<email>`) que el login, ANTES
de verificar el código. Al superar el segundo factor se resetean los contadores.
Test nuevo: `test_mfa_complete_is_rate_limited`.

---

## Hallazgos del audit previo que se DESCARTAN (no aplican / sobrevalorados)

Un audit automático previo marcó estos como "críticos". Tras revisar el código:

- **CSRF tokens (marcado CRÍTICO): NO aplica.** La app autentica con
  `Authorization: Bearer <token>` (token en localStorage, no en cookie). CSRF
  explota credenciales ambientales (cookies que el navegador envía solo); un bearer
  token no se envía automáticamente cross-site. Implementar CSRF aquí sería
  complejidad sin beneficio. *Reevaluar solo si se migra a cookies httpOnly.*
- **Migrar API keys a secrets manager / git-crypt (marcado CRÍTICO): innecesario.**
  El `.env` ya está gitignored y no está en el repo. Para on-premise, variables de
  entorno es el mecanismo estándar. git-crypt resolvería un problema inexistente
  (claves en git).
- **"Inyección SQL" en organizations.py (marcado CRÍTICO): no explotable** (lista
  hardcodeada). Ya reescrito igualmente por higiene (punto 2).
- **HS256 vs RS256:** para un despliegue single-app on-premise donde el mismo
  proceso firma y valida, HS256 con secreto fuerte es adecuado. RS256 aporta poco
  aquí y añade gestión de claves.

---

## Pendientes reales, por prioridad (no aplicados aún)

Menor severidad; a decidir si se abordan:

| # | Tema | Archivo | Severidad | Nota |
|---|------|---------|-----------|------|
| 1 | Fallback a password SMTP en claro si el campo cifrado está vacío | `app/routers/auth.py` (`_try_send_otp_email`), `models.py` | Baja | Migrar los registros legacy y eliminar el fallback. |
| 2 | Derivación de clave Fernet con SHA-256 directo del secret_key | `app/security.py`, `app/services/document_service.py` | Baja | Funcional y consistente; PBKDF2/clave dedicada permitiría rotar el JWT secret sin perder los datos cifrados. Requiere migración con versionado. |
| 3 | Backups sin cifrar | `app/services/backup_service.py` | Baja (on-prem) | La clave viviría en el mismo servidor; solo aporta frente a exfiltración del fichero de backup a un tercero. |
| 4 | Confianza en `X-Real-IP` | `app/routers/auth.py:_client_ip` | Baja | Ya se ignora `X-Forwarded-For`. Validar que venga solo del proxy de confianza si el modelo de amenaza lo requiere. |
| 5 | CSP con `unsafe-inline` en `script-src`/`style-src` | `middleware/security_headers.py` | Baja | Difícil de quitar en esta SPA (handlers inline). No es un fix trivial. |

---

## Cambio pausado a petición del usuario: tokens en cookies httpOnly

Actualmente el JWT se guarda en `localStorage`. Ventaja: simple. Riesgo: si
existiera un XSS, el token sería legible por JS. Alternativa: cookies `httpOnly`
+ `SameSite=Strict` (inaccesibles a JS), lo que **a cambio** obliga a introducir
protección CSRF y rehacer el manejo de sesión en `api.js`/`auth.js` (es un cambio
que invalida las sesiones activas — todos re-login). Queda **pendiente de explicar
y decidir** antes de tocarlo.

---

## Estado de verificación

- `pytest tests/test_auth.py tests/test_auth_hardening.py tests/test_path_traversal.py` → verde (19 auth + 2 path traversal).
- `ruff check` sobre los ficheros tocados → limpio.
- `import app.main` → OK con las env vars requeridas.
- Sin commitear todavía (pendiente tu revisión).
