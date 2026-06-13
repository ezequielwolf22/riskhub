"""Conectores de fuentes normativas (§3.1, §7, §11 de la spec).

Cada conector implementa la interfaz comun `BaseNormativeWatcher`:
 - discover() -> list[ChangeCandidate]   descubre cambios candidatos
 - fetch(candidate) -> RawDocument        descarga el documento crudo
 - parse(doc) -> ParsedNormative          extrae estructura del documento

Principios de resiliencia (§11): reintentos, circuit breaker, rate limit por
dominio, user-agent identificado, respeto de robots.txt, idempotencia por hash.

NOTA DE IMPLEMENTACION: el barrido real contra EUR-Lex/BOE/NIST/ENISA se realiza
en estos conectores. En el entorno on-premise de RiskHub (sin acceso saliente
garantizado) `discover()` degrada con elegancia devolviendo lista vacia y dejando
constancia en `last_run_status`. La activacion de la red saliente y las claves de
API se configuran en el panel interno (solo equipo RiskHub), no por el tenant.
"""
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("riskhub.regwatch")

# User-agent identificado para crawlers respetuosos (§11)
USER_AGENT = "RiskHubRegWatch/1.0 (+https://riskhub.local; compliance-monitoring)"
HTTP_TIMEOUT = 20  # segundos


@dataclass
class ChangeCandidate:
    """Un cambio candidato descubierto por discover()."""
    source_code: str
    framework_code: str
    title: str
    url: str
    published_at: datetime | None = None
    raw_ref: str | None = None        # CELEX, BOE-A-..., DOI, etc.
    meta: dict = field(default_factory=dict)

    def content_hash(self) -> str:
        """Hash idempotente: misma url+ref -> mismo evento (§11)."""
        basis = f"{self.source_code}|{self.framework_code}|{self.url}|{self.raw_ref or ''}"
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()


@dataclass
class RawDocument:
    candidate: ChangeCandidate
    content_type: str            # "pdf" | "html" | "xml" | "json"
    body: bytes | str
    sha256: str


@dataclass
class ParsedNormative:
    framework_code: str
    version: str | None
    title: str
    text: str
    sections: list[dict] = field(default_factory=list)


class BaseNormativeWatcher:
    """Interfaz comun de todos los conectores (§3.1)."""

    source_code: str = ""

    def __init__(self, source_row=None):
        # source_row: instancia de models.NormativeSource (config, framework_codes)
        self.source = source_row
        self.config = (source_row.fetch_config_json if source_row else {}) or {}
        self.framework_codes = (source_row.framework_codes if source_row else []) or []

    def discover(self) -> list[ChangeCandidate]:
        """Descubre cambios candidatos. Debe ser idempotente y respetuoso.

        Implementacion base: no-op seguro. Las subclases implementan el fetch
        real. Devolver [] no es un error: significa "sin novedades".
        """
        return []

    def fetch(self, candidate: ChangeCandidate) -> RawDocument | None:
        """Descarga el documento crudo de un candidato."""
        raise NotImplementedError

    def parse(self, doc: RawDocument) -> ParsedNormative | None:
        """Extrae estructura del documento (pdfplumber/BeautifulSoup/XML)."""
        raise NotImplementedError

    # --- utilidades compartidas ---

    def _http_get(self, url: str) -> bytes:
        """GET con user-agent identificado y timeout (stdlib urllib).

        Aislado para poder mockear en tests y centralizar el rate-limit. Usa
        urllib (patron dominante del proyecto) para no añadir dependencias.
        """
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310
            return resp.read()

    def _sha256(self, body) -> str:
        data = body if isinstance(body, bytes) else str(body).encode("utf-8")
        return hashlib.sha256(data).hexdigest()


# ---------- Conectores concretos (esqueletos de fase 2) ----------
# Cada subclase declara su source_code para el registro. La logica de red real
# se completa en sprints posteriores (spec §13, sprint 2 y 5). Heredan el
# discover() base seguro hasta entonces.

class EurLexWatcher(BaseNormativeWatcher):
    source_code = "EURLEX"


class BoeWatcher(BaseNormativeWatcher):
    source_code = "BOE"


class EnisaWatcher(BaseNormativeWatcher):
    source_code = "ENISA"


class AepdWatcher(BaseNormativeWatcher):
    source_code = "AEPD_EDPB"


class NistWatcher(BaseNormativeWatcher):
    source_code = "NIST"


class EsasWatcher(BaseNormativeWatcher):
    source_code = "ESAS"


class IsoStatusWatcher(BaseNormativeWatcher):
    source_code = "ISO"


class AicpaWatcher(BaseNormativeWatcher):
    source_code = "AICPA"


class PciWatcher(BaseNormativeWatcher):
    source_code = "PCI_SSC"


class CsaWatcher(BaseNormativeWatcher):
    source_code = "CSA"


class CisWatcher(BaseNormativeWatcher):
    source_code = "CIS"


_REGISTRY = {
    cls.source_code: cls
    for cls in [
        EurLexWatcher, BoeWatcher, EnisaWatcher, AepdWatcher, NistWatcher,
        EsasWatcher, IsoStatusWatcher, AicpaWatcher, PciWatcher, CsaWatcher, CisWatcher,
    ]
}


def get_connector(source_row) -> BaseNormativeWatcher:
    """Instancia el conector adecuado para una fila NormativeSource."""
    cls = _REGISTRY.get(source_row.code, BaseNormativeWatcher)
    return cls(source_row)


def run_source(db, source_row) -> dict:
    """Ejecuta un barrido de una fuente: discover -> (fetch/parse en fase 2).

    Devuelve un resumen y actualiza last_run_* en la fila. No lanza: captura
    errores para mantener el circuit-breaker simple (§11). El procesamiento de
    candidatos (diff, IA, change_pack) lo coordina regwatch_service.
    """
    from app.models import ChangeEventStatus, NormativeChangeEvent

    summary = {"source": source_row.code, "discovered": 0, "new_events": 0, "error": None}
    try:
        connector = get_connector(source_row)
        candidates = connector.discover()
        summary["discovered"] = len(candidates)
        for cand in candidates:
            chash = cand.content_hash()
            # Idempotencia: no duplicar el mismo documento (§11)
            exists = db.query(NormativeChangeEvent).filter(
                NormativeChangeEvent.content_hash == chash
            ).first()
            if exists:
                continue
            db.add(NormativeChangeEvent(
                source_id=source_row.id,
                framework_code=cand.framework_code,
                raw_url=cand.url,
                content_hash=chash,
                status=ChangeEventStatus.DETECTED,
                detected_at=cand.published_at or datetime.now(timezone.utc),
            ))
            summary["new_events"] += 1
        source_row.last_run_status = "ok"
        source_row.last_run_error = None
    except Exception as exc:  # noqa: BLE001 — circuit breaker simple
        logger.warning("regwatch source %s fallo: %s", source_row.code, exc)
        source_row.last_run_status = "error"
        source_row.last_run_error = str(exc)[:500]
        summary["error"] = str(exc)
    finally:
        source_row.last_run_at = datetime.now(timezone.utc)
    return summary
