"""RAG: busqueda de fragmentos relevantes en FTS5 con expansion bilingue ES/EN."""
import logging
import re
import unicodedata
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger("riskhub.rag")

# Caracteres especiales del motor FTS5 que podrian alterar la sintaxis de busqueda
_FTS5_SPECIAL = re.compile(r'["\*\^\(\)\{\}\[\]~\-\+:]+')

# ---------------------------------------------------------------------------
# Diccionario de expansion bilingue para dominio seguridad de la informacion
# Clave: termino en espanol (normalizado, sin tildes, minusculas)
# Valor: lista de sinonimos/equivalentes en ingles para buscar en documentos EN
# ---------------------------------------------------------------------------
_ES_TO_EN: dict[str, list[str]] = {
    # Autenticacion y contraseñas
    "contrasena": ["password", "passwords", "passphrase", "credential", "credentials"],
    "contrasenas": ["password", "passwords", "credentials"],
    "clave": ["password", "key", "passphrase"],
    "claves": ["passwords", "keys"],
    "politica": ["policy", "procedure", "standard", "guideline"],
    "politicas": ["policies", "procedures", "standards"],
    "complejidad": ["complexity", "requirements", "strength", "rules"],
    "longitud": ["length", "minimum", "characters", "chars"],
    "minima": ["minimum", "min", "least"],
    "minimo": ["minimum", "min", "least"],
    "maxima": ["maximum", "max"],
    "maximo": ["maximum", "max"],
    "caracteres": ["characters", "chars", "length"],
    "mayusculas": ["uppercase", "capital", "capitals"],
    "minusculas": ["lowercase"],
    "numeros": ["numbers", "numeric", "digits"],
    "digitos": ["digits", "numbers"],
    "simbolos": ["symbols", "special characters", "special"],
    "caducidad": ["expiration", "expiry", "rotation", "validity", "age"],
    "vencimiento": ["expiration", "expiry", "expire"],
    "renovacion": ["renewal", "rotation", "change", "reset"],
    "historial": ["history", "reuse", "previous"],
    "reutilizacion": ["reuse", "history", "rotation"],
    "bloqueo": ["lockout", "lock", "block", "disabled"],
    "intentos": ["attempts", "tries", "retries"],
    "fallidos": ["failed", "failure", "unsuccessful", "attempts"],
    "autenticacion": ["authentication", "MFA", "2FA", "multi-factor", "login", "logon"],
    "autentificacion": ["authentication", "MFA", "2FA"],
    "multifactor": ["MFA", "multi-factor", "2FA", "two-factor"],
    "mfa": ["MFA", "multi-factor", "two-factor", "authentication"],
    "sso": ["SSO", "single sign-on", "federation"],
    "token": ["token", "OTP", "TOTP"],
    "certificado": ["certificate", "PKI", "digital certificate"],
    "certificados": ["certificates", "PKI"],
    "sesion": ["session", "timeout", "inactivity"],
    "sesiones": ["sessions", "timeout"],
    "timeout": ["timeout", "inactivity", "session"],
    # Control de acceso
    "acceso": ["access", "login", "logon", "authorization"],
    "control": ["control", "measure", "management"],
    "acceso remoto": ["remote access", "VPN", "remote"],
    "remoto": ["remote", "VPN", "remote access"],
    "vpn": ["VPN", "tunnel", "remote access"],
    "privilegios": ["privileges", "permissions", "rights"],
    "privilegio": ["privilege", "permission", "right"],
    "permisos": ["permissions", "access rights", "privileges"],
    "roles": ["roles", "RBAC", "permissions"],
    "usuario": ["user", "account", "identity"],
    "usuarios": ["users", "accounts", "identities"],
    "administrador": ["administrator", "admin", "privileged"],
    "superusuario": ["root", "administrator", "admin", "privileged"],
    "cuenta": ["account", "identity", "user"],
    "cuentas": ["accounts", "identities", "users"],
    "identidad": ["identity", "IAM", "account"],
    # Cifrado
    "cifrado": ["encryption", "cipher", "encrypted", "cryptography"],
    "cifrar": ["encrypt", "encryption", "cryptography"],
    "encriptacion": ["encryption", "cipher", "cryptography"],
    "descifrado": ["decryption", "decrypt"],
    "criptografia": ["cryptography", "encryption", "PKI"],
    "firma": ["signature", "digital signature", "signing"],
    "hash": ["hash", "hashing", "digest"],
    "aes": ["AES", "encryption", "cipher"],
    "tls": ["TLS", "SSL", "HTTPS", "transport"],
    "ssl": ["SSL", "TLS", "HTTPS"],
    "https": ["HTTPS", "TLS", "SSL"],
    # Gestion de riesgos
    "riesgo": ["risk", "threat", "vulnerability"],
    "riesgos": ["risks", "threats"],
    "amenaza": ["threat", "attack", "adversary"],
    "amenazas": ["threats", "attacks"],
    "vulnerabilidad": ["vulnerability", "weakness", "flaw", "CVE"],
    "vulnerabilidades": ["vulnerabilities", "weaknesses", "CVEs"],
    "impacto": ["impact", "consequence", "damage"],
    "probabilidad": ["probability", "likelihood", "frequency"],
    "mitigacion": ["mitigation", "control", "countermeasure"],
    "tratamiento": ["treatment", "response", "remediation"],
    "aceptacion": ["acceptance", "acceptance criteria", "risk acceptance"],
    "apetito": ["appetite", "tolerance", "risk appetite"],
    # Activos
    "activo": ["asset", "resource", "information asset"],
    "activos": ["assets", "resources"],
    "inventario": ["inventory", "register", "catalogue"],
    "clasificacion": ["classification", "labeling", "categorization"],
    "propietario": ["owner", "custodian", "responsible"],
    "servidor": ["server", "host", "system"],
    "servidores": ["servers", "hosts", "systems"],
    "base de datos": ["database", "DB", "data store"],
    "aplicacion": ["application", "app", "software", "system"],
    "aplicaciones": ["applications", "apps", "software"],
    "red": ["network", "infrastructure", "LAN", "WAN"],
    "redes": ["networks", "infrastructure"],
    "nube": ["cloud", "SaaS", "IaaS", "PaaS"],
    "dispositivo": ["device", "endpoint", "hardware"],
    "dispositivos": ["devices", "endpoints"],
    # Incidentes y respuesta
    "incidente": ["incident", "event", "breach", "security incident"],
    "incidentes": ["incidents", "events", "breaches"],
    "brecha": ["breach", "data breach", "leak"],
    "respuesta": ["response", "handling", "management"],
    "notificacion": ["notification", "reporting", "alert"],
    "forense": ["forensic", "investigation", "analysis"],
    "recuperacion": ["recovery", "restore", "restoration"],
    # Continuidad
    "continuidad": ["continuity", "BCP", "BCM", "business continuity"],
    "disponibilidad": ["availability", "uptime", "continuity"],
    "rto": ["RTO", "recovery time", "objective"],
    "rpo": ["RPO", "recovery point", "objective"],
    "backup": ["backup", "recovery", "restore", "replication"],
    "copia": ["backup", "copy", "replica"],
    "recuperacion": ["recovery", "restore", "failover"],
    # Cumplimiento y auditoria
    "auditoria": ["audit", "review", "assessment", "inspection"],
    "auditoria": ["audit", "review", "assessment"],
    "conformidad": ["compliance", "conformity", "adherence"],
    "cumplimiento": ["compliance", "conformance", "conformity"],
    "revision": ["review", "assessment", "evaluation"],
    "prueba": ["test", "testing", "check", "verification"],
    "evidencia": ["evidence", "proof", "record", "log"],
    "registro": ["record", "log", "register", "trail"],
    "trazabilidad": ["traceability", "audit trail", "log", "tracking"],
    "monitoreo": ["monitoring", "surveillance", "logging", "detection"],
    "supervision": ["supervision", "monitoring", "oversight"],
    "iso": ["ISO", "standard", "framework"],
    "ens": ["ENS", "national security scheme", "standard"],
    "gdpr": ["GDPR", "RGPD", "privacy", "data protection"],
    "nis2": ["NIS2", "directive", "cybersecurity"],
    # Proveedores
    "proveedor": ["supplier", "vendor", "third party", "third-party"],
    "proveedores": ["suppliers", "vendors", "third parties"],
    "subcontrata": ["subcontractor", "vendor", "outsourcing"],
    "externaliza": ["outsourcing", "third-party"],
    # Seguridad fisica
    "fisica": ["physical", "facility", "premises"],
    "fisico": ["physical", "hardware", "facility"],
    "instalacion": ["facility", "premises", "site"],
    "datacenter": ["datacenter", "data center", "facility"],
    "camara": ["camera", "CCTV", "surveillance"],
    # Desarrollo seguro
    "desarrollo": ["development", "SDLC", "software development"],
    "codigo": ["code", "software", "application"],
    "prueba": ["test", "testing", "QA"],
    "despliegue": ["deployment", "release", "production"],
    "parche": ["patch", "update", "hotfix", "fix"],
    "parches": ["patches", "updates", "hotfixes"],
    "actualizacion": ["update", "patch", "upgrade"],
    # Datos personales
    "datos": ["data", "information", "records"],
    "datos personales": ["personal data", "PII", "personal information"],
    "personales": ["personal", "PII", "sensitive"],
    "privacidad": ["privacy", "data protection", "GDPR"],
    "retencion": ["retention", "storage", "period"],
    "borrado": ["deletion", "erasure", "destruction", "purge"],
    # Criptografia / PKI
    "certificado": ["certificate", "digital certificate", "PKI"],
    "autoridad": ["authority", "CA", "certification authority"],
    "clave publica": ["public key", "PKI", "certificate"],
    "clave privada": ["private key", "secret key"],
    # Terminos frecuentes en preguntas
    "dice": ["states", "says", "requires", "specifies"],
    "requiere": ["requires", "must", "mandatory", "shall"],
    "obligatorio": ["mandatory", "required", "must", "shall"],
    "recomendado": ["recommended", "should", "best practice"],
    "prohibido": ["prohibited", "forbidden", "not allowed"],
    "permitido": ["allowed", "permitted", "authorized"],
    "politica": ["policy", "procedure", "standard"],
}


def _normalize(text: str) -> str:
    """Convierte a minusculas y elimina tildes/diacriticos."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _expand_to_english(query: str) -> list[str]:
    """Extrae terminos EN equivalentes a los terminos ES encontrados en la query.

    Retorna lista de palabras/frases EN que amplian la busqueda en documentos EN.
    Primero prueba frases de 2-3 palabras, luego palabras individuales.
    """
    norm = _normalize(query)
    collected: list[str] = []
    seen: set[str] = set()

    # Buscar frases de hasta 3 palabras (matches compuestos)
    words = norm.split()
    for window in (3, 2):
        for i in range(len(words) - window + 1):
            phrase = " ".join(words[i:i + window])
            if phrase in _ES_TO_EN:
                for en in _ES_TO_EN[phrase]:
                    if en not in seen:
                        seen.add(en)
                        collected.append(en)

    # Buscar palabras individuales
    for w in words:
        if w in _ES_TO_EN:
            for en in _ES_TO_EN[w]:
                if en not in seen:
                    seen.add(en)
                    collected.append(en)

    return collected


_STOPWORDS_ES = {
    "que", "qué", "de", "del", "en", "el", "la", "los", "las", "un", "una",
    "y", "o", "a", "al", "es", "por", "para", "con", "se", "su", "sus",
    "me", "mi", "no", "si", "lo", "le", "hay", "como", "cómo", "cuál",
    "cual", "cuáles", "cuales", "sobre", "más", "mas", "pero", "ya", "has",
    "dime", "dame", "puedes", "puedo", "quiero", "saber", "decir", "dice",
    "dices", "tiene", "tienen", "puede", "pueden", "qué", "este", "esta",
    "estos", "estas", "son", "fue", "ser", "estar", "hace", "hacer", "hay",
    "cuanto", "cuánto", "donde", "dónde", "cuando", "cuándo", "quien",
    "quién", "alguno", "alguna", "todos", "todas", "cada", "muy", "alguna",
    "algo", "nada", "tener", "tengo", "tenemos",
}


def _sanitize_fts5(query: str) -> str:
    """Elimina operadores especiales FTS5 para evitar inyeccion de sintaxis."""
    safe = _FTS5_SPECIAL.sub(" ", query)
    return " ".join(safe.split())[:500]


def _meaningful_words(text: str) -> list[str]:
    """Extrae palabras significativas (sin stopwords, longitud > 2)."""
    safe = _sanitize_fts5(text)
    norm = _normalize(safe)
    return [w for w in norm.split() if len(w) > 2 and w not in _STOPWORDS_ES]


def _fts5_query_variants(query: str) -> list[str]:
    """Genera variantes de query FTS5 en orden de mayor a menor especificidad.

    Estrategia:
    1. Frase exacta ES (entre comillas)
    2. Palabras clave ES en AND (sin stopwords)
    3. Terminos EN equivalentes en AND (traduccion automatica del dominio)
    4. Cada termino EN individualmente (OR implicito al iterar)
    5. Prefijo del primer termino ES con comodin
    """
    safe_original = _sanitize_fts5(query)
    es_words = _meaningful_words(query)
    en_terms = _expand_to_english(query)

    variants: list[str] = []

    # 1. Frase exacta en ES
    if safe_original:
        variants.append(f'"{safe_original}"')

    # 2. AND de palabras clave ES (max 5)
    if len(es_words) > 1:
        variants.append(" ".join(es_words[:5]))
    elif es_words:
        variants.append(es_words[0])

    # 3. Terminos EN clave en AND (los primeros 4 son los mas relevantes)
    if en_terms:
        primary_en = en_terms[:4]
        if len(primary_en) > 1:
            variants.append(" ".join(primary_en))
        # 4. Cada termino EN por separado (para maxima cobertura)
        for term in primary_en:
            if f'"{term}"' not in variants:
                variants.append(f'"{term}"')

    # 5. Prefijo comodin del primer termino ES
    if es_words:
        variants.append(f"{es_words[0]}*")

    # Eliminar duplicados manteniendo orden
    seen: set[str] = set()
    unique: list[str] = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def _run_fts5(
    db: Session,
    fts_query: str,
    top_k: int,
    organization_id: int | None,
) -> list[tuple]:
    """Ejecuta una query FTS5 y devuelve las filas crudas."""
    if organization_id is not None:
        return db.execute(
            text(
                "SELECT c.content, d.original_name, d.category FROM ai_document_chunks c "
                "JOIN ai_chunks_fts fts ON fts.rowid = c.id "
                "JOIN ai_documents d ON d.id = c.document_id "
                "WHERE ai_chunks_fts MATCH :q "
                "AND d.organization_id = :org_id "
                "ORDER BY rank LIMIT :k"
            ),
            {"q": fts_query, "k": top_k, "org_id": organization_id},
        ).fetchall()
    return db.execute(
        text(
            "SELECT c.content, d.original_name, d.category FROM ai_document_chunks c "
            "JOIN ai_chunks_fts fts ON fts.rowid = c.id "
            "JOIN ai_documents d ON d.id = c.document_id "
            "WHERE ai_chunks_fts MATCH :q "
            "ORDER BY rank LIMIT :k"
        ),
        {"q": fts_query, "k": top_k},
    ).fetchall()


def search_chunks(
    db: Session,
    query: str,
    top_k: int = 8,
    organization_id: int | None = None,
    voyage_api_key: str | None = None,
) -> list[str]:
    """Busca y devuelve los top_k fragmentos mas relevantes (solo texto)."""
    results = search_chunks_with_source(
        db, query, top_k=top_k, organization_id=organization_id, voyage_api_key=voyage_api_key
    )
    return [r["content"] for r in results]


def search_chunks_with_source(
    db: Session,
    query: str,
    top_k: int = 8,
    organization_id: int | None = None,
    voyage_api_key: str | None = None,
) -> list[dict]:
    """Busqueda semantica multilingue con Voyage AI + fallback a FTS5.

    Orden:
    1. Voyage AI embedding search (semantico, multilingual) — si voyage_api_key disponible
    2. FTS5 con expansion bilingue ES/EN (keywords exactos)

    Nunca se cruzan datos entre tenants (organization_id obligatorio en uso normal).
    """
    if not query or not query.strip():
        return []

    # -- Nivel 1: busqueda semantica con embeddings Voyage AI --
    if voyage_api_key:
        try:
            from app.services.embedding_service import embed_query, search_by_embedding
            query_emb = embed_query(query, voyage_api_key)
            if query_emb:
                results = search_by_embedding(db, query_emb, top_k, organization_id)
                if results:
                    logger.debug("RAG embedding: %d resultados (top score %.3f)",
                                 len(results), results[0].get("score", 0))
                    return results
        except Exception as e:
            logger.warning("Embedding search error, fallback a FTS5: %s", e)

    # -- Nivel 2: FTS5 con expansion bilingue y FUSION de variantes --
    # Antes se devolvia la primera variante con resultados; ahora se ejecutan
    # todas y se fusionan por puntuacion (especificidad de la variante +
    # posicion en su ranking), deduplicando por contenido.
    try:
        variants = _fts5_query_variants(query)
        fused: dict[str, dict] = {}
        for idx, variant in enumerate(variants):
            try:
                rows = _run_fts5(db, variant, top_k, organization_id)
            except Exception:
                continue
            for pos, r in enumerate(rows):
                key = (r[0] or "")[:200]
                score = (len(variants) - idx) * 100 - pos
                if key not in fused or score > fused[key]["_score"]:
                    fused[key] = {
                        "content": r[0], "doc_name": r[1] or "Documento",
                        "category": r[2] or "", "_score": score,
                    }
        if fused:
            ranked = sorted(fused.values(), key=lambda x: -x["_score"])[:top_k]
            for r in ranked:
                r.pop("_score", None)
            logger.debug("RAG FTS5 fusion: %d variantes -> %d resultados",
                         len(variants), len(ranked))
            return ranked
    except Exception:
        pass

    logger.debug("RAG: sin resultados para query: %r", query[:80])
    return []


# ---------- Indice FTS de entidades de negocio (v6.0.0) ----------
# Riesgos, controles, politicas y evidencias analizadas quedan buscables por
# el chat: "que riesgos afectan al ERP" recupera registros aunque no esten
# entre los 15 del contexto fijo.

def refresh_entity_index(db: Session) -> int:
    """Reconstruye ai_entity_fts con las entidades de negocio actuales.

    Se ejecuta desde el scheduler (nocturno). Rebuild completo: el volumen
    es pequeno (miles de filas) y evita logica de sincronizacion incremental.
    """
    from app.models import (
        ControlImplementation, Evidence, Policy, Risk,
    )
    try:
        db.execute(text("DELETE FROM ai_entity_fts"))
    except Exception:
        return 0  # FTS5 no disponible

    inserted = 0

    def _add(content: str, etype: str, ref: str, org_id) -> None:
        nonlocal inserted
        if not content or not content.strip():
            return
        db.execute(
            text("INSERT INTO ai_entity_fts(content, entity_type, entity_ref, org_id) "
                 "VALUES (:c, :t, :r, :o)"),
            {"c": content[:2000], "t": etype, "r": ref, "o": str(org_id or "")},
        )
        inserted += 1

    for r in db.query(Risk).all():
        asset = r.asset.name if r.asset else ""
        threat = r.threat.name if r.threat else ""
        _add(
            f"{r.code} riesgo {asset} {threat} {r.description or ''} {r.ai_rationale or ''}",
            "risk", r.code, r.organization_id,
        )
    for ci in db.query(ControlImplementation).all():
        code = ci.control.code if ci.control else ""
        _add(
            f"{code} control {ci.name or ''} {ci.evidence or ''} {ci.notes or ''}",
            "control", code or str(ci.id), ci.organization_id,
        )
    for p in db.query(Policy).all():
        _add(
            f"{p.code or ''} politica {p.title or ''} {(p.scope or '')[:200]} "
            f"{(p.content or '')[:400]}",
            "policy", p.code or str(p.id), p.organization_id,
        )
    for ev in db.query(Evidence).filter(Evidence.ai_review.isnot(None)).all():
        rev = ev.ai_review or {}
        facts = " ".join(rev.get("key_facts") or [])
        _add(
            f"{ev.code} evidencia {ev.title or ''} {rev.get('summary', '')} {facts}",
            "evidence", ev.code, ev.organization_id,
        )

    db.commit()
    logger.info("RAG entidades: indice reconstruido (%d filas)", inserted)
    return inserted


def search_entities(db: Session, query: str, top_k: int = 6,
                    organization_id: int | None = None) -> list[dict]:
    """Busca entidades de negocio relacionadas con la consulta del chat."""
    if not query or not query.strip():
        return []
    results: list[dict] = []
    seen: set[str] = set()
    try:
        for variant in _fts5_query_variants(query):
            rows = db.execute(
                text("SELECT content, entity_type, entity_ref FROM ai_entity_fts "
                     "WHERE ai_entity_fts MATCH :q AND org_id = :o "
                     "ORDER BY rank LIMIT :k"),
                {"q": variant, "o": str(organization_id or ""), "k": top_k},
            ).fetchall()
            for r in rows:
                key = f"{r[1]}:{r[2]}"
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "content": r[0], "entity_type": r[1], "entity_ref": r[2],
                })
                if len(results) >= top_k:
                    return results
    except Exception:
        logger.debug("search_entities fallo", exc_info=True)
    return results


def ask(prompt: str, org_id: Optional[int] = None) -> Optional[str]:
    """Llamada directa a Claude para preguntas simples (sin RAG)."""
    try:
        from app.config import settings
        api_key = getattr(settings, "anthropic_api_key", None)
        if not api_key:
            return None
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        logger.debug("rag_service.ask fallo: %s", e)
        return None
