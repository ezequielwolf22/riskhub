"""Catalogo unico de las notificaciones automaticas del sistema.

Cada job del scheduler que envia correo declara aqui su `alert_key`. Este registro
es la fuente de verdad para:
  - el gating por-organizacion (notification_settings.should_notify)
  - el panel de Configuracion -> Alertas (una fila editable por entrada)

Anadir una alerta nueva = anadir una entrada aqui y llamar a
`notification_settings.send_notification(..., alert_key=...)` desde el job.

Campos de cada entrada:
  key                  clave estable (no cambiar: se persiste en notification_settings)
  label                nombre en castellano para la UI
  category             agrupacion en el panel
  description          que dispara la alerta (para el usuario)
  frequency_human      cadencia real del job (informativo; el cron es fijo)
  default_enabled      si la alerta esta activa cuando no hay fila de configuracion
  default_cooldown_days  anti-flood por defecto: no reenviar hasta pasar N dias (0 = sin limite)
  supports_threshold   si la alerta expone un umbral configurable a nivel de org
  threshold_label      etiqueta del umbral (cuando supports_threshold)
  threshold_default    valor por defecto del umbral
  audience             'org' (admins del cliente) | 'platform' (superadmin)
"""
from __future__ import annotations

from typing import Optional

# Orden = orden de aparicion en el panel.
ALERT_CATALOG: list[dict] = [
    # ---- Indicadores ----
    {
        "key": "kri_breach",
        "label": "KPI / KRI en breach",
        "category": "Indicadores",
        "description": "Un indicador (KPI o KRI) supera su umbral de incumplimiento.",
        "frequency_human": "Al cruzar el umbral (evaluacion cada 6 h)",
        "default_enabled": True,
        # La deduplicacion de indicadores es por-indicador (KRI.last_alert_at + edge-trigger),
        # no por-org: aqui 0 para no suprimir el aviso de otros indicadores en breach.
        "default_cooldown_days": 0,
        "supports_threshold": False,
        "audience": "org",
    },
    # ---- Controles ----
    {
        "key": "ccm_fail",
        "label": "Monitorizacion continua (CCM): controles en FAIL",
        "category": "Controles",
        "description": "El score de Continuous Control Monitoring cae por debajo del umbral y hay controles fallando.",
        "frequency_human": "Diario",
        "default_enabled": True,
        "default_cooldown_days": 7,
        "supports_threshold": True,
        "threshold_label": "Alertar si el score CCM es menor que",
        "threshold_default": 70.0,
        "audience": "org",
    },
    # ---- Riesgos ----
    {
        "key": "risk_review_due",
        "label": "Revision de riesgo vencida / programada",
        "category": "Riesgos",
        "description": "Un riesgo tiene la revision periodica vencida o proxima.",
        "frequency_human": "Diario",
        "default_enabled": True,
        # Dedup por-riesgo (Risk.last_review_notified_at); 0 para no suprimir otros riesgos.
        "default_cooldown_days": 0,
        "supports_threshold": False,
        "audience": "org",
    },
    # ---- Politicas ----
    {
        "key": "policy_review",
        "label": "Revision de politicas proxima o vencida",
        "category": "Politicas",
        "description": "Una politica publicada se acerca a su fecha de revision o la ha superado.",
        "frequency_human": "Diario",
        "default_enabled": True,
        # Recordatorio por-documento (a su owner); 0 para no suprimir otros documentos.
        "default_cooldown_days": 0,
        "supports_threshold": False,
        "audience": "org",
    },
    # ---- Evidencias ----
    {
        "key": "evidence_expiry",
        "label": "Evidencias proximas a vencer",
        "category": "Evidencias",
        "description": "Una evidencia de control esta a punto de caducar.",
        "frequency_human": "Diario",
        "default_enabled": True,
        # Dedup por-evidencia (Evidence.expiry_alert_sent); 0 para no suprimir avisos
        # de otras evidencias.
        "default_cooldown_days": 0,
        "supports_threshold": False,
        "audience": "org",
    },
    # ---- Compliance ----
    {
        "key": "compliance_review",
        "label": "Requisitos de compliance sin revision",
        "category": "Compliance",
        "description": "Requisitos de un marco de cumplimiento llevan demasiado tiempo sin revisarse.",
        "frequency_human": "Mensual (dia 1)",
        "default_enabled": True,
        "default_cooldown_days": 14,
        "supports_threshold": False,
        "audience": "org",
    },
    {
        "key": "soa_review",
        "label": "Declaracion de Aplicabilidad (SoA) sin revision anual",
        "category": "Compliance",
        "description": "La SoA no se ha revisado en el ultimo ano.",
        "frequency_human": "Semanal",
        "default_enabled": True,
        "default_cooldown_days": 14,
        "supports_threshold": False,
        "audience": "org",
    },
    # ---- Continuidad (BCP / ISO 22301) ----
    {
        "key": "bcp_test_overdue",
        "label": "Procesos BCM sin test de continuidad",
        "category": "Continuidad de negocio",
        "description": "Procesos criticos que llevan mas de 12 meses sin probar el plan.",
        "frequency_human": "Semanal (lunes)",
        "default_enabled": True,
        "default_cooldown_days": 14,
        "supports_threshold": False,
        "audience": "org",
    },
    {
        "key": "bcp_plan_review",
        "label": "Planes de continuidad con revision vencida",
        "category": "Continuidad de negocio",
        "description": "Planes BCP cuya revision periodica ha vencido.",
        "frequency_human": "Mensual (dia 1)",
        "default_enabled": True,
        "default_cooldown_days": 14,
        "supports_threshold": False,
        "audience": "org",
    },
    {
        "key": "bcp_bia_gap",
        "label": "Analisis de Impacto (BIA) incompletos",
        "category": "Continuidad de negocio",
        "description": "Procesos criticos sin el BIA completo.",
        "frequency_human": "Mensual (dia 15)",
        "default_enabled": True,
        "default_cooldown_days": 14,
        "supports_threshold": False,
        "audience": "org",
    },
    # ---- Informes ----
    {
        "key": "monthly_report",
        "label": "Informe mensual de seguridad",
        "category": "Informes",
        "description": "Resumen mensual del estado del SGSI por correo.",
        "frequency_human": "Mensual (dia 1)",
        "default_enabled": True,
        "default_cooldown_days": 0,
        "supports_threshold": False,
        "audience": "org",
    },
    {
        "key": "scheduled_reports",
        "label": "Informes programados",
        "category": "Informes",
        "description": "Envio de los informes que el usuario ha planificado.",
        "frequency_human": "Segun la planificacion de cada informe",
        "default_enabled": True,
        "default_cooldown_days": 0,
        "supports_threshold": False,
        "audience": "org",
    },
    # ---- Proveedores / TPRM ----
    {
        "key": "questionnaire_lifecycle",
        "label": "Cuestionarios de proveedor (envio, expiracion y respuesta)",
        "category": "Proveedores (TPRM)",
        "description": "Envio de cuestionarios planificados, recordatorios de expiracion y aviso de respuesta.",
        "frequency_human": "Diario / semanal",
        "default_enabled": True,
        "default_cooldown_days": 0,
        "supports_threshold": False,
        "audience": "org",
    },
]

# Nota: las alertas de proveedor por hallazgo (contrato expirando, monitoreo
# web/SSL/DNS) NO se envian directamente: crean un VendorIssue y su correo sale
# por el motor de reglas (event_type vendor_issue_*), configurable en la vista
# Alertas -> Reglas. Los digest de vigilancia normativa y Plan Director tienen su
# propia cadencia (digest_frequency / periodicidad del comite). Por eso no se
# duplican aqui: se controlan en su modulo.

_BY_KEY = {e["key"]: e for e in ALERT_CATALOG}
VALID_ALERT_KEYS = set(_BY_KEY.keys())


def get_catalog_entry(alert_key: str) -> Optional[dict]:
    return _BY_KEY.get(alert_key)


def catalog_for_audience(audience: str = "org") -> list[dict]:
    return [e for e in ALERT_CATALOG if e.get("audience", "org") == audience]
