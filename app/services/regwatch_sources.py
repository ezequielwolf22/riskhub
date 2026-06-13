"""Catalogo maestro de fuentes normativas (§3.1 de la spec).

Tabla maestra `normative_source`, configurada por el equipo RiskHub y NO editable
por el tenant. Cada fuente mapea a uno o varios frameworks y se asocia a un
conector (`BaseNormativeWatcher`). El orden de implementacion sugerido por la spec
es: EUR-Lex, BOE, NIST, ENISA primero; ISO scraping en segunda fase.

Estas definiciones se siembran en la tabla `regwatch_sources` desde el seed.
"""

# Definicion canonica de las fuentes. Sin credenciales: las URLs son publicas.
SOURCES: list[dict] = [
    {
        "code": "EURLEX",
        "name": "EUR-Lex — Diario Oficial de la UE",
        "framework_codes": ["NIS2", "DORA", "GDPR", "EU_AI_ACT"],
        "connector_class": "EurLexWatcher",
        "method": "API + RSS",
        "polling_frequency": "daily",
        "fetch_config_json": {
            "base_url": "https://eur-lex.europa.eu",
            "celex_map": {
                "NIS2": "32022L2555",
                "DORA": "32022R2554",
                "EU_AI_ACT": "32024R1689",
            },
        },
    },
    {
        "code": "BOE",
        "name": "BOE — Boletin Oficial del Estado (ENS)",
        "framework_codes": ["ENS"],
        "connector_class": "BoeWatcher",
        "method": "API JSON + RSS",
        "polling_frequency": "daily",
        "fetch_config_json": {
            "base_url": "https://www.boe.es",
            "ens_ref": "BOE-A-2022-7191",  # RD 311/2022
        },
    },
    {
        "code": "ENISA",
        "name": "ENISA + CSIRT-ES (NIS2 guidance)",
        "framework_codes": ["NIS2"],
        "connector_class": "EnisaWatcher",
        "method": "RSS",
        "polling_frequency": "daily",
        "fetch_config_json": {"feed_url": "https://www.enisa.europa.eu/news/rss"},
    },
    {
        "code": "AEPD_EDPB",
        "name": "AEPD + EDPB — Criterios y guidelines GDPR",
        "framework_codes": ["GDPR"],
        "connector_class": "AepdWatcher",
        "method": "API + RSS",
        "polling_frequency": "daily",
        "fetch_config_json": {"base_url": "https://www.aepd.es"},
    },
    {
        "code": "NIST",
        "name": "NIST CSRC — publicaciones",
        "framework_codes": ["NIST_CSF", "NIST_SP_800"],
        "connector_class": "NistWatcher",
        "method": "API oficial + RSS",
        "polling_frequency": "weekly",
        "fetch_config_json": {"api_url": "https://csrc.nist.gov/CSRC/media/feeds/metanorma/json"},
    },
    {
        "code": "ESAS",
        "name": "ESAs (EBA/ESMA/EIOPA) — RTS DORA",
        "framework_codes": ["DORA"],
        "connector_class": "EsasWatcher",
        "method": "RSS",
        "polling_frequency": "daily",
        "fetch_config_json": {},
    },
    {
        "code": "ISO",
        "name": "ISO.org — status de estandares publicados",
        "framework_codes": [
            "ISO_27001", "ISO_27002", "ISO_27017", "ISO_27018",
            "ISO_27701", "ISO_22301", "ISO_42001",
        ],
        "connector_class": "IsoStatusWatcher",
        "method": "Scraping de cambio de estado",
        "polling_frequency": "weekly",
        "fetch_config_json": {"base_url": "https://www.iso.org"},
    },
    {
        "code": "AICPA",
        "name": "AICPA — Trust Services Criteria (SOC 2)",
        "framework_codes": ["SOC_2"],
        "connector_class": "AicpaWatcher",
        "method": "RSS + scraping",
        "polling_frequency": "monthly",
        "fetch_config_json": {},
    },
    {
        "code": "PCI_SSC",
        "name": "PCI Security Standards Council — library",
        "framework_codes": ["PCI_DSS"],
        "connector_class": "PciWatcher",
        "method": "API",
        "polling_frequency": "monthly",
        "fetch_config_json": {"base_url": "https://www.pcisecuritystandards.org"},
    },
    {
        "code": "CSA",
        "name": "Cloud Security Alliance — CCM / CAIQ",
        "framework_codes": ["CSA_CCM", "CSA_CAIQ"],
        "connector_class": "CsaWatcher",
        "method": "RSS + GitHub releases",
        "polling_frequency": "monthly",
        "fetch_config_json": {},
    },
    {
        "code": "CIS",
        "name": "Center for Internet Security — CIS Controls",
        "framework_codes": ["CIS_Controls"],
        "connector_class": "CisWatcher",
        "method": "GitHub releases",
        "polling_frequency": "monthly",
        "fetch_config_json": {},
    },
]


# Mapeo inverso framework_code -> codigos de fuente que lo cubren.
def sources_for_framework(framework_code: str) -> list[str]:
    fc = framework_code.upper()
    return [s["code"] for s in SOURCES if fc in [c.upper() for c in s["framework_codes"]]]


# Codigos de framework reconocidos por el modulo, normalizados.
# Mapea los codigos internos del modulo Compliance / flags regulatorios de
# proveedores a los codigos canonicos del catalogo regwatch.
COMPLIANCE_TO_REGWATCH = {
    "iso27001": "ISO_27001",
    "iso27002": "ISO_27002",
    "iso42001": "ISO_42001",
    "iso22301": "ISO_22301",
    "nis2": "NIS2",
    "dora": "DORA",
    "gdpr": "GDPR",
    "ens": "ENS",
    "nist_csf": "NIST_CSF",
    "soc2": "SOC_2",
    "pci_dss": "PCI_DSS",
    "hipaa": "HIPAA",
    "eu_ai_act": "EU_AI_ACT",
}


def normalize_framework(code: str) -> str:
    """Normaliza un codigo de framework al canonico del catalogo regwatch."""
    if not code:
        return ""
    return COMPLIANCE_TO_REGWATCH.get(code.lower(), code.upper())


# Reverso: canonico regwatch -> codigo del modulo Compliance (para cruzar impacto).
_REGWATCH_TO_COMPLIANCE = {v: k for k, v in COMPLIANCE_TO_REGWATCH.items()}


def to_compliance_code(canonical: str) -> str:
    """Mapea un codigo canonico (ISO_27001) al del modulo Compliance (iso27001)."""
    if not canonical:
        return ""
    return _REGWATCH_TO_COMPLIANCE.get(canonical, canonical.lower())


# Etiquetas legibles en castellano para la UI.
FRAMEWORK_LABELS = {
    "ISO_27001": "ISO/IEC 27001",
    "ISO_27002": "ISO/IEC 27002",
    "ISO_27017": "ISO/IEC 27017",
    "ISO_27018": "ISO/IEC 27018",
    "ISO_27701": "ISO/IEC 27701",
    "ISO_22301": "ISO 22301",
    "ISO_42001": "ISO/IEC 42001",
    "NIS2": "NIS2 (UE 2022/2555)",
    "DORA": "DORA (UE 2022/2554)",
    "GDPR": "RGPD (UE 2016/679)",
    "ENS": "ENS (RD 311/2022)",
    "EU_AI_ACT": "Reglamento de IA de la UE",
    "NIST_CSF": "NIST CSF",
    "NIST_SP_800": "NIST SP 800-x",
    "SOC_2": "SOC 2",
    "PCI_DSS": "PCI DSS",
    "HIPAA": "HIPAA",
    "CSA_CCM": "CSA CCM",
    "CSA_CAIQ": "CSA CAIQ",
    "CIS_Controls": "CIS Controls",
}


def framework_label(code: str) -> str:
    return FRAMEWORK_LABELS.get(code, code)
