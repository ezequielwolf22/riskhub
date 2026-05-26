"""Servicio de generacion de contenido de awareness (infografias de seguridad).

Flujo:
  1. generate_content() — llama al agente IA con contexto de riesgos/org
     y obtiene un dict estructurado con el contenido de la infografia.
  2. export_pdf() — convierte ese dict en un PDF A4 apaisado con
     la marca del cliente (logo, colores) usando ReportLab.

Plantillas disponibles:
  risk_alert      — Alerta de riesgo activo
  best_practices  — Buenas practicas de seguridad
  policy          — Recordatorio de politica corporativa
  threat          — Amenaza del mes
  phishing        — Anti-phishing / ingenieria social
"""
import base64
import io
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("riskhub.awareness")

# ---------- Prompt del generador ----------

_SYSTEM_PROMPT = """Eres un experto en concienciacion de ciberseguridad corporativa.
Tu tarea es generar el contenido de una infografia de seguridad profesional,
clara, impactante y adaptada al contexto de la organizacion.

Devuelve UNICAMENTE un objeto JSON valido con esta estructura exacta (sin markdown):
{
  "template": "<risk_alert|best_practices|policy|threat|phishing>",
  "title": "<titulo impactante, max 55 caracteres>",
  "subtitle": "<subtitulo descriptivo, max 100 caracteres>",
  "urgency": "<low|medium|high|critical>",
  "main_message": "<mensaje clave, max 180 caracteres>",
  "key_points": ["<punto 1>", "<punto 2>", "<punto 3>"],
  "do_items": ["<hacer esto>", "<hacer esto otro>", "<y esto>"],
  "dont_items": ["<no hacer esto>", "<ni esto>"],
  "statistic": {"value": "<dato impactante ej: 91%>", "label": "<breve descripcion del dato>"},
  "call_to_action": "<accion concreta que debe realizar el empleado>",
  "contact": "<a quien reportar o contactar>",
  "references": ["<norma ISO o NIST relevante>"],
  "hashtags": ["#Ciberseguridad", "#Awareness"]
}

Reglas:
- Textos SIEMPRE en castellano.
- key_points: entre 3 y 5 puntos concisos (max 80 chars cada uno).
- do_items: entre 2 y 4 acciones positivas.
- dont_items: entre 2 y 3 prohibiciones claras.
- statistic puede ser null si no aplica.
- El contenido debe ser especifico al contexto y riesgos proporcionados, no generico.
- Usa terminologia ISO 27001/27002 cuando sea apropiado.
"""


def generate_content(
    user_prompt: str,
    org_context: str,
    risks_summary: str,
    api_key: str,
    model: str = "claude-haiku-4-5",
    max_tokens: int = 1500,
) -> dict:
    """Llama al agente IA y devuelve el dict de contenido de la infografia."""
    import anthropic

    full_prompt = (
        f"PETICION DEL USUARIO:\n{user_prompt}\n\n"
        f"CONTEXTO DE LA ORGANIZACION:\n{org_context}\n\n"
        f"RESUMEN DE RIESGOS ACTIVOS:\n{risks_summary}"
    )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": full_prompt}],
    )
    raw = response.content[0].text.strip() if response.content else "{}"
    # Extraer JSON aunque haya texto extra
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        raw = raw[start:end]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("awareness_service: JSON invalido de la IA, devolviendo raw")
        return {"title": "Sin titulo", "main_message": raw[:200]}


# ---------- Colores de plantilla ----------

_TEMPLATE_COLORS = {
    "risk_alert":      {"header": "#C0392B", "accent": "#E74C3C", "badge": "#FDECEA"},
    "best_practices":  {"header": "#59008D", "accent": "#8E44AD", "badge": "#F3E5F5"},
    "policy":          {"header": "#1565C0", "accent": "#1976D2", "badge": "#E3F2FD"},
    "threat":          {"header": "#212121", "accent": "#424242", "badge": "#F5F5F5"},
    "phishing":        {"header": "#D65200", "accent": "#E8670A", "badge": "#FFF3E0"},
}

_TEMPLATE_LABELS = {
    "risk_alert":     "ALERTA DE RIESGO",
    "best_practices": "BUENAS PRACTICAS",
    "policy":         "POLITICA CORPORATIVA",
    "threat":         "AMENAZA DEL MES",
    "phishing":       "ANTI-PHISHING",
}

_URGENCY_COLORS = {
    "critical": "#C0392B",
    "high":     "#D65200",
    "medium":   "#F39C12",
    "low":      "#27AE60",
}

_URGENCY_LABELS = {
    "critical": "CRITICO",
    "high":     "ALTO",
    "medium":   "MEDIO",
    "low":      "BAJO",
}


# ---------- Generacion PDF con ReportLab ----------

def export_pdf(content: dict, branding: Optional[dict] = None) -> bytes:
    """Genera un PDF A4 apaisado (landscape) con la infografia de awareness."""
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import Canvas

    branding = branding or {}
    primary_hex = branding.get("primary_color", "#59008D")
    secondary_hex = branding.get("secondary_color", "#D65200")
    company_name = branding.get("company_name", "")
    logo_data = branding.get("logo_data")  # bytes o None

    tpl = content.get("template", "best_practices")
    tcolors = _TEMPLATE_COLORS.get(tpl, _TEMPLATE_COLORS["best_practices"])
    header_hex = tcolors["header"]
    accent_hex = tcolors["accent"]

    def _c(hex_color: str):
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return rl_colors.Color(r / 255, g / 255, b / 255)

    PAGE_W, PAGE_H = landscape(A4)
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(PAGE_W, PAGE_H))

    # --- Banda superior (header) ---
    c.setFillColor(_c(header_hex))
    c.rect(0, PAGE_H - 28 * mm, PAGE_W, 28 * mm, fill=1, stroke=0)

    # Badge de plantilla
    badge_label = _TEMPLATE_LABELS.get(tpl, tpl.upper())
    c.setFillColor(rl_colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(12 * mm, PAGE_H - 9 * mm, badge_label)

    # Titulo principal
    title = (content.get("title") or "Sin titulo")[:55]
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(rl_colors.white)
    title_x = 12 * mm
    title_y = PAGE_H - 21 * mm
    c.drawString(title_x, title_y, title)

    # Badge urgencia (derecha del header)
    urgency = content.get("urgency", "medium")
    urg_label = _URGENCY_LABELS.get(urgency, urgency.upper())
    urg_color = _URGENCY_COLORS.get(urgency, "#F39C12")
    badge_w, badge_h = 28 * mm, 8 * mm
    badge_x = PAGE_W - badge_w - 12 * mm
    badge_y = PAGE_H - 22 * mm
    c.setFillColor(_c(urg_color))
    c.roundRect(badge_x, badge_y, badge_w, badge_h, 2 * mm, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(rl_colors.white)
    c.drawCentredString(badge_x + badge_w / 2, badge_y + 2.5 * mm, urg_label)

    # Nombre empresa (header derecha)
    if company_name:
        c.setFont("Helvetica", 8)
        c.setFillColor(rl_colors.white)
        c.drawRightString(badge_x - 6 * mm, PAGE_H - 9 * mm, company_name)

    # Logo (si existe)
    if logo_data:
        try:
            from reportlab.lib.utils import ImageReader
            img_reader = ImageReader(io.BytesIO(logo_data))
            logo_x = PAGE_W - 50 * mm
            logo_y = PAGE_H - 26 * mm
            c.drawImage(img_reader, logo_x, logo_y, width=36 * mm, height=20 * mm,
                        preserveAspectRatio=True, mask="auto")
        except Exception:
            pass  # logo invalido, continuar sin el

    # --- Subtitulo ---
    subtitle = (content.get("subtitle") or "")[:100]
    if subtitle:
        c.setFont("Helvetica", 11)
        c.setFillColor(_c(header_hex))
        c.drawString(12 * mm, PAGE_H - 34 * mm, subtitle)

    # --- Cuerpo: columna izquierda (mensaje + puntos clave) ---
    col1_x = 12 * mm
    col2_x = PAGE_W / 2 + 4 * mm
    body_top = PAGE_H - 40 * mm
    col_w = PAGE_W / 2 - 16 * mm

    # Mensaje principal
    main_msg = (content.get("main_message") or "")[:180]
    if main_msg:
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(_c(accent_hex))
        _draw_wrapped(c, main_msg, col1_x, body_top, col_w, "Helvetica-Bold", 12, 15, _c(accent_hex))

    # Puntos clave
    key_pts = (content.get("key_points") or [])[:5]
    y = body_top - 18 * mm
    if key_pts:
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(_c(primary_hex))
        c.drawString(col1_x, y, "PUNTOS CLAVE")
        y -= 5 * mm
        for pt in key_pts:
            c.setFillColor(_c(accent_hex))
            c.circle(col1_x + 2 * mm, y + 1.5 * mm, 1.5 * mm, fill=1, stroke=0)
            c.setFont("Helvetica", 9)
            c.setFillColor(rl_colors.HexColor("#262626"))
            _draw_wrapped(c, str(pt)[:80], col1_x + 6 * mm, y, col_w - 6 * mm,
                          "Helvetica", 9, 12, rl_colors.HexColor("#262626"))
            y -= 8 * mm

    # --- Columna derecha: hacer / no hacer ---
    y2 = body_top

    do_items = (content.get("do_items") or [])[:4]
    dont_items = (content.get("dont_items") or [])[:3]

    if do_items:
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(_c("#27AE60"))
        c.drawString(col2_x, y2, "HAZ ESTO")
        y2 -= 5 * mm
        for item in do_items:
            c.setFillColor(_c("#27AE60"))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(col2_x, y2 + 1 * mm, "✓")
            c.setFont("Helvetica", 9)
            c.setFillColor(rl_colors.HexColor("#262626"))
            _draw_wrapped(c, str(item)[:80], col2_x + 6 * mm, y2, col_w - 6 * mm,
                          "Helvetica", 9, 12, rl_colors.HexColor("#262626"))
            y2 -= 8 * mm

    y2 -= 4 * mm
    if dont_items:
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(_c("#C0392B"))
        c.drawString(col2_x, y2, "EVITA ESTO")
        y2 -= 5 * mm
        for item in dont_items:
            c.setFillColor(_c("#C0392B"))
            c.setFont("Helvetica-Bold", 11)
            c.drawString(col2_x, y2 + 1 * mm, "✗")
            c.setFont("Helvetica", 9)
            c.setFillColor(rl_colors.HexColor("#262626"))
            _draw_wrapped(c, str(item)[:80], col2_x + 6 * mm, y2, col_w - 6 * mm,
                          "Helvetica", 9, 12, rl_colors.HexColor("#262626"))
            y2 -= 8 * mm

    # Estadistica destacada
    stat = content.get("statistic")
    if stat and stat.get("value"):
        stat_y = min(y, y2) - 6 * mm
        box_h = 18 * mm
        stat_x = col1_x
        c.setFillColor(_c(accent_hex))
        c.roundRect(stat_x, stat_y - box_h, col_w / 2, box_h, 3 * mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 22)
        c.setFillColor(rl_colors.white)
        c.drawCentredString(stat_x + col_w / 4, stat_y - box_h / 2 + 3 * mm,
                            str(stat["value"])[:10])
        lbl = str(stat.get("label", ""))[:60]
        c.setFont("Helvetica", 8)
        c.drawCentredString(stat_x + col_w / 4, stat_y - box_h / 2 - 4 * mm, lbl)

    # --- Banda inferior (call to action) ---
    footer_h = 16 * mm
    c.setFillColor(_c(header_hex))
    c.rect(0, 0, PAGE_W, footer_h, fill=1, stroke=0)

    cta = (content.get("call_to_action") or "")[:120]
    contact = (content.get("contact") or "")
    hashtags = " ".join((content.get("hashtags") or [])[:4])

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(rl_colors.white)
    if cta:
        c.drawString(12 * mm, footer_h - 6 * mm, f"ACCION: {cta}")
    if contact:
        c.setFont("Helvetica", 8)
        c.drawString(12 * mm, footer_h - 11 * mm, contact)
    c.setFont("Helvetica", 8)
    c.setFillColor(rl_colors.Color(1, 1, 1, 0.7))
    c.drawRightString(PAGE_W - 12 * mm, footer_h - 8 * mm,
                      f"{hashtags}  |  RiskHub Awareness")

    # Separador central
    c.setStrokeColor(_c(accent_hex))
    c.setLineWidth(0.5)
    c.line(PAGE_W / 2, PAGE_H - 36 * mm, PAGE_W / 2, footer_h + 2 * mm)

    c.save()
    return buf.getvalue()


def _draw_wrapped(canvas, text: str, x: float, y: float, max_w: float,
                  font: str, size: int, leading: int, color) -> float:
    """Dibuja texto con ajuste de linea simple. Devuelve la Y final."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    words = text.split()
    line = ""
    canvas.setFont(font, size)
    canvas.setFillColor(color)
    for word in words:
        test = f"{line} {word}".strip()
        if stringWidth(test, font, size) <= max_w:
            line = test
        else:
            canvas.drawString(x, y, line)
            y -= leading
            line = word
    if line:
        canvas.drawString(x, y, line)
        y -= leading
    return y
