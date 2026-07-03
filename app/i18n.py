"""Backend i18n module for RiskHub.

Usage in routers:
    from app.i18n import t, get_lang

    @router.get("/example")
    async def example(request: Request):
        lang = get_lang(request)
        raise HTTPException(status_code=404, detail=t("risks.not_found", lang))

    # With interpolation:
    raise HTTPException(
        status_code=423,
        detail=t("auth.account_locked", lang, seconds=remaining),
    )
"""
import json
from pathlib import Path
from typing import Any

_LOCALE_DIR = Path(__file__).parent / "locale"
_SUPPORTED   = ("es", "en")
_DEFAULT     = "es"
_translations: dict[str, dict] = {}


def _deep_merge(base: dict, extra: dict) -> None:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _load() -> None:
    for lang in _SUPPORTED:
        path = _LOCALE_DIR / f"{lang}.json"
        try:
            with open(path, encoding="utf-8") as fh:
                _translations[lang] = json.load(fh)
        except FileNotFoundError:
            _translations[lang] = {}
        # Fragmentos: app/locale/<lang>/*.json se fusionan sobre el fichero base.
        # Permite que modulos aporten sus claves en ficheros separados.
        frag_dir = _LOCALE_DIR / lang
        if frag_dir.is_dir():
            for frag in sorted(frag_dir.glob("*.json")):
                try:
                    with open(frag, encoding="utf-8") as fh:
                        _deep_merge(_translations[lang], json.load(fh))
                except (json.JSONDecodeError, OSError):
                    continue


_load()


def _resolve(obj: dict, key: str) -> Any:
    for part in key.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)  # type: ignore[assignment]
        else:
            return None
    return obj


def t(key: str, lang: str = _DEFAULT, **params: Any) -> str:
    """Return the translated string for *key* in *lang* with optional interpolation."""
    effective = lang if lang in _SUPPORTED else _DEFAULT
    val = _resolve(_translations.get(effective, {}), key)

    if val is None and effective != _DEFAULT:
        val = _resolve(_translations.get(_DEFAULT, {}), key)

    if not isinstance(val, str):
        return key

    for k, v in params.items():
        val = val.replace(f"{{{k}}}", str(v))

    return val


def get_lang(request: Any) -> str:
    """Extract the requested language from the X-Lang header."""
    lang = getattr(request, "headers", {}).get("X-Lang", _DEFAULT)
    return lang if lang in _SUPPORTED else _DEFAULT
