"""Regenera app/data/threat_control_map.json con Claude (uso offline, one-shot).

Uso (desde la raiz del repo, requiere ANTHROPIC_API_KEY en el entorno):
    python scripts/generate_threat_control_map.py

El resultado se escribe en app/data/threat_control_map.json y debe revisarse
manualmente antes de commitear: el valor del catalogo es precisamente que un
humano lo haya validado. Las organizaciones ajustan casos particulares via la
tabla threat_control_overrides, no editando este fichero.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app" / "data"

PROMPT = """Eres un experto en ISO/IEC 27005:2018 e ISO/IEC 27002:2022.
Para la amenaza siguiente, devuelve los controles ISO 27002:2022 que la
mitigan de forma significativa, con relevancia 0.1-1.0 (1.0 = control
principal). Entre 3 y 9 controles. Devuelve SOLO JSON:
[{"code": "8.7", "relevance": 0.9}, ...]

Amenaza: {code} — {name}
Categoria: {category}
Descripcion: {description}

Controles disponibles (codigo: nombre):
{controls}
"""


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Falta ANTHROPIC_API_KEY en el entorno.")
        return 1
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    controls = json.loads((DATA / "controls_iso27002_2022.json").read_text(encoding="utf-8"))
    controls_txt = "\n".join(f"{c['code']}: {c['name']}" for c in controls)

    threats = []
    threats += json.loads((DATA / "threats_iso27005.json").read_text(encoding="utf-8"))
    threats += json.loads((DATA / "magerit_threats.json").read_text(encoding="utf-8"))

    out: dict = {
        "_meta": {
            "description": "Mapeo amenaza -> controles ISO/IEC 27002:2022 que la "
                           "mitigan, con relevancia 0-1. El efecto P/D/C se deriva "
                           "en runtime de classify_control().",
            "version": "regenerated",
            "catalogs": ["iso27005", "magerit"],
        }
    }
    for t in threats:
        prompt = PROMPT.format(
            code=t["code"], name=t["name"],
            category=t.get("category", ""),
            description=t.get("description", ""),
            controls=controls_txt,
        )
        msg = client.messages.create(
            model="claude-opus-4-6", max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].removeprefix("json").strip()
        try:
            out[t["code"]] = json.loads(raw)
            print(f"{t['code']}: {len(out[t['code']])} controles")
        except json.JSONDecodeError:
            print(f"{t['code']}: respuesta no parseable, omitida")

    target = DATA / "threat_control_map.json"
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Escrito {target} — revisar manualmente antes de commitear.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
