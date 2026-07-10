"""Servicio para importar hallazgos de herramientas externas (Nessus, Qualys, Burp, etc).

Parsea outputs de cada herramienta → crea ExternalFinding → auto-genera riesgo si severity alta.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Asset, ExternalFinding, ExternalFindingSource, Risk

logger = logging.getLogger("riskhub.external_findings")


# ─────────────────────────────── PARSERS ───────────────────────────────────────

_MAX_XML_BYTES = 50 * 1024 * 1024  # M5: limite 50 MB para evitar DoS por expansion de entidades


def parse_nessus_xml(xml_content: bytes) -> list[dict]:
    """Parsea archivo .nessus (XML) de Tenable Nessus.

    Retorna lista de hallazgos normalizados.
    """
    from defusedxml import ElementTree as ET

    findings = []
    try:
        if len(xml_content) > _MAX_XML_BYTES:
            logger.warning("parse_nessus_xml: archivo demasiado grande (%d bytes), ignorado", len(xml_content))
            return findings
        root = ET.fromstring(xml_content)
        for report_host in root.iter("ReportHost"):
            hostname = report_host.get("name", "")
            for item in report_host.iter("ReportItem"):
                severity_num = int(item.get("severity", "0"))
                if severity_num < 2:  # Solo MEDIUM+ (0=info,1=low,2=medium,3=high,4=critical)
                    continue
                severity_map = {2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}
                severity = severity_map.get(severity_num, "MEDIUM")

                plugin_name = item.get("pluginName", "")
                cve_list = [c.text for c in item.findall(".//cve") if c.text]
                cvss = None
                cvss_el = item.find(".//cvss3_base_score")
                if cvss_el is None:
                    cvss_el = item.find(".//cvss_base_score")
                if cvss_el is not None and cvss_el.text:
                    try:
                        cvss = float(cvss_el.text)
                    except ValueError:
                        pass

                port_el = item.get("port")
                port = int(port_el) if port_el and port_el.isdigit() else None

                description_el = item.find(".//description")
                desc = description_el.text if description_el is not None else ""

                findings.append({
                    "source": ExternalFindingSource.NESSUS.value,
                    "external_id": item.get("pluginID", ""),
                    "title": plugin_name[:512],
                    "description": (desc or "")[:2000],
                    "severity": severity,
                    "cvss_score": cvss,
                    "cve_id": cve_list[0] if cve_list else None,
                    "affected_host": hostname[:512],
                    "affected_port": port,
                    "affected_software": item.get("svc_name", ""),
                })
    except Exception as exc:
        logger.exception("Error parsing Nessus XML: %s", exc)

    return findings


def parse_qualys_xml(xml_content: bytes) -> list[dict]:
    """Parsea reporte XML de Qualys Guard."""
    from defusedxml import ElementTree as ET

    findings = []
    try:
        if len(xml_content) > _MAX_XML_BYTES:
            logger.warning("parse_qualys_xml: archivo demasiado grande, ignorado")
            return findings
        root = ET.fromstring(xml_content)

        for vuln in root.iter("VULN"):
            severity_el = vuln.find("SEVERITY")
            sev_num = int(severity_el.text) if severity_el is not None else 1
            if sev_num < 3:  # 1-2 baja, 3 media, 4-5 alta
                continue
            severity_map = {3: "MEDIUM", 4: "HIGH", 5: "CRITICAL"}
            severity = severity_map.get(sev_num, "MEDIUM")

            qid_el = vuln.find("QID")
            title_el = vuln.find("TITLE")
            desc_el = vuln.find("DIAGNOSIS")
            cve_el = vuln.find("CVE_ID_LIST/CVE_ID/ID")
            cvss_el = vuln.find("CVSS3/BASE")
            if cvss_el is None:
                cvss_el = vuln.find("CVSS/BASE")

            # Host info
            ip_el = vuln.find("../../IP")
            hostname_el = vuln.find("../../DNS")
            host = (ip_el.text if ip_el is not None else "") or ""
            if hostname_el is not None and hostname_el.text:
                host = hostname_el.text

            cvss = None
            if cvss_el is not None and cvss_el.text:
                try:
                    cvss = float(cvss_el.text)
                except ValueError:
                    pass

            findings.append({
                "source": ExternalFindingSource.QUALYS.value,
                "external_id": qid_el.text if qid_el is not None else "",
                "title": (title_el.text if title_el is not None else "Qualys finding")[:512],
                "description": (desc_el.text if desc_el is not None else "")[:2000],
                "severity": severity,
                "cvss_score": cvss,
                "cve_id": cve_el.text if cve_el is not None else None,
                "affected_host": host[:512],
                "affected_port": None,
                "affected_software": "",
            })
    except Exception as exc:
        logger.exception("Error parsing Qualys XML: %s", exc)

    return findings


def parse_burp_xml(xml_content: bytes) -> list[dict]:
    """Parsea reporte XML de Burp Suite."""
    from defusedxml import ElementTree as ET

    findings = []
    try:
        if len(xml_content) > _MAX_XML_BYTES:
            logger.warning("parse_burp_xml: archivo demasiado grande, ignorado")
            return findings
        root = ET.fromstring(xml_content)

        for issue in root.iter("issue"):
            sev_el = issue.find("severity")
            sev = (sev_el.text or "Information") if sev_el is not None else "Information"
            if sev in ("Information", "Low"):
                continue
            sev_map = {"Medium": "MEDIUM", "High": "HIGH", "Critical": "CRITICAL"}
            severity = sev_map.get(sev, "MEDIUM")

            name_el = issue.find("name")
            desc_el = issue.find("issueDetail")
            if desc_el is None:
                desc_el = issue.find("issueBackground")
            host_el = issue.find("host")
            path_el = issue.find("path")
            url_el = issue.find("url")

            host = host_el.text if host_el is not None else ""

            # Extraer CVE si aparece en descripción
            desc_text = desc_el.text if desc_el is not None else ""
            cve_match = re.search(r"CVE-\d{4}-\d{4,}", desc_text or "")
            cve_id = cve_match.group(0) if cve_match else None

            findings.append({
                "source": ExternalFindingSource.BURP.value,
                "external_id": issue.get("serialNumber", ""),
                "title": (name_el.text if name_el is not None else "Burp finding")[:512],
                "description": (desc_text or "")[:2000],
                "severity": severity,
                "cvss_score": None,
                "cve_id": cve_id,
                "affected_host": host[:512],
                "affected_port": None,
                "affected_software": (path_el.text if path_el is not None else ""),
            })
    except Exception as exc:
        logger.exception("Error parsing Burp XML: %s", exc)

    return findings


def parse_openvas_xml(xml_content: bytes) -> list[dict]:
    """Parsea reporte XML de OpenVAS/GVM."""
    from defusedxml import ElementTree as ET

    findings = []
    try:
        if len(xml_content) > _MAX_XML_BYTES:
            logger.warning("parse_openvas_xml: archivo demasiado grande, ignorado")
            return findings
        root = ET.fromstring(xml_content)

        for result in root.iter("result"):
            threat_el = result.find("threat")
            sev = (threat_el.text or "Log") if threat_el is not None else "Log"
            if sev in ("Log", "Debug", "Low"):
                continue
            sev_map = {"Medium": "MEDIUM", "High": "HIGH", "Critical": "CRITICAL"}
            severity = sev_map.get(sev, "MEDIUM")

            name_el = result.find("name")
            desc_el = result.find("description")
            host_el = result.find("host")
            port_el = result.find("port")
            nvt_el = result.find("nvt")
            cve_el = result.find("nvt/refs/ref[@type='cve']")
            cvss_el = result.find("nvt/severities/severity/value")

            host = host_el.text if host_el is not None else ""
            port_str = port_el.text if port_el is not None else ""
            port = None
            if port_str:
                match = re.search(r"\d+", port_str)
                if match:
                    port = int(match.group(0))

            cvss = None
            if cvss_el is not None and cvss_el.text:
                try:
                    cvss = float(cvss_el.text)
                except ValueError:
                    pass

            findings.append({
                "source": ExternalFindingSource.OPENVAS.value,
                "external_id": nvt_el.get("oid", "") if nvt_el is not None else "",
                "title": (name_el.text if name_el is not None else "OpenVAS finding")[:512],
                "description": (desc_el.text if desc_el is not None else "")[:2000],
                "severity": severity,
                "cvss_score": cvss,
                "cve_id": cve_el.get("id") if cve_el is not None else None,
                "affected_host": host[:512],
                "affected_port": port,
                "affected_software": "",
            })
    except Exception as exc:
        logger.exception("Error parsing OpenVAS XML: %s", exc)

    return findings


# ─────────────────────── IMPORT PIPELINE ────────────────────────────────────────

def _match_asset(db: Session, org_id: int, finding: dict) -> Optional[Asset]:
    """Intenta encontrar el asset que corresponde al hallazgo — SQL LIKE en lugar de loop Python."""
    from sqlalchemy import or_
    host = finding.get("affected_host", "").lower()
    software = (finding.get("affected_software", "") or "").lower()

    if not host and not software:
        return None

    conditions = []
    if host:
        conditions.append(Asset.name.ilike(f"%{host}%"))
        conditions.append(Asset.description.ilike(f"%{host}%"))
    if software:
        conditions.append(Asset.name.ilike(f"%{software}%"))
        conditions.append(Asset.description.ilike(f"%{software}%"))

    if not conditions:
        return None

    return db.query(Asset).filter(
        Asset.organization_id == org_id,
        or_(*conditions),
    ).first()


def import_findings(
    db: Session,
    org_id: int,
    source: str,
    findings_data: list[dict],
    auto_create_risks: bool = True,
) -> dict:
    """Importa hallazgos normalizados a BD y opcionalmente crea riesgos.

    Retorna estadísticas: {total, created, duplicates, risks_created}
    """
    from app.services.risk_auto_generator import auto_generate_risk_from_cve

    batch_id = str(uuid.uuid4())[:16]
    stats = {"total": len(findings_data), "created": 0, "duplicates": 0, "risks_created": 0}

    for finding in findings_data:
        # Deduplicar por source + external_id + host
        external_id = finding.get("external_id", "")
        host = finding.get("affected_host", "")

        existing = db.query(ExternalFinding).filter(
            ExternalFinding.organization_id == org_id,
            ExternalFinding.source == source,
            ExternalFinding.external_id == external_id,
            ExternalFinding.affected_host == host,
        ).first()

        if existing:
            stats["duplicates"] += 1
            continue

        asset = _match_asset(db, org_id, finding)

        ef = ExternalFinding(
            organization_id=org_id,
            source=source,
            external_id=external_id[:256] if external_id else None,
            title=finding.get("title", "")[:512],
            description=finding.get("description", "")[:2000],
            severity=finding.get("severity", "MEDIUM"),
            cvss_score=finding.get("cvss_score"),
            cve_id=finding.get("cve_id"),
            affected_host=host[:512] if host else None,
            affected_port=finding.get("affected_port"),
            affected_software=(finding.get("affected_software") or "")[:512],
            asset_id=asset.id if asset else None,
            import_batch_id=batch_id,
            detected_at=datetime.now(timezone.utc),
        )
        db.add(ef)
        db.flush()
        stats["created"] += 1

        # Nueva vigilancia sobre el activo: el analisis IA de sus riesgos
        # queda desactualizado (el usuario decide si re-analizar)
        if asset:
            from app.services.risk_recalc_service import mark_risks_stale_for_asset
            mark_risks_stale_for_asset(
                db, asset.id,
                f"Nuevo hallazgo {finding.get('severity', '')} "
                f"({finding.get('cve_id') or finding.get('source', 'scanner')})",
            )

        # Auto-crear riesgo si severity HIGH/CRITICAL y asset encontrado
        if auto_create_risks and asset and finding.get("severity") in ("HIGH", "CRITICAL"):
            cve_id = finding.get("cve_id")
            consequence = 4 if finding.get("severity") == "CRITICAL" else 3
            if cve_id:
                risk = auto_generate_risk_from_cve(
                    db, asset.id, cve_id,
                    affected_software=finding.get("affected_software", ""),
                    inherent_consequence=consequence,
                    inherent_likelihood=3,
                )
                if risk:
                    ef.risk_id = risk.id
                    stats["risks_created"] += 1
            else:
                # Sin CVE: usar generador generico de hallazgos
                from app.services.risk_auto_generator import auto_generate_risk_from_finding
                risk = auto_generate_risk_from_finding(
                    db, asset.id,
                    title=finding.get("title") or finding.get("name") or "Hallazgo de seguridad",
                    description=finding.get("description") or "",
                    threat_code=f"EXT-{finding.get('source', 'SCANNER').upper()[:8]}",
                    inherent_consequence=consequence,
                    inherent_likelihood=3,
                )
                if risk:
                    ef.risk_id = risk.id
                    stats["risks_created"] += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Error importando hallazgos: %s", exc)
        return {"error": str(exc)}

    logger.info(
        "Import %s (org=%d): total=%d created=%d dup=%d risks=%d",
        source, org_id, stats["total"], stats["created"], stats["duplicates"], stats["risks_created"]
    )
    return stats


def detect_file_format(filename: str, content: bytes) -> Optional[str]:
    """Detecta el formato del archivo de hallazgos."""
    name_lower = filename.lower()

    if name_lower.endswith(".nessus"):
        return "nessus"
    if "qualys" in name_lower and name_lower.endswith(".xml"):
        return "qualys"
    if "burp" in name_lower and name_lower.endswith(".xml"):
        return "burp"
    if name_lower.endswith(".xml"):
        # Detectar por contenido
        preview = content[:1000].decode("utf-8", errors="ignore")
        if "NessusClientData_v2" in preview or "ReportHost" in preview:
            return "nessus"
        if "QUALYS_SCAN_REPORT" in preview or "<RESULTS>" in preview:
            return "qualys"
        if "<issues>" in preview.lower() or "burp" in preview.lower():
            return "burp"
        if "report format_id" in preview.lower() or "openvas" in preview.lower():
            return "openvas"

    return None
