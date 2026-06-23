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


def _load() -> None:
    for lang in _SUPPORTED:
        path = _LOCALE_DIR / f"{lang}.json"
        try:
            with open(path, encoding="utf-8") as fh:
                _translations[lang] = json.load(fh)
        except FileNotFoundError:
            _translations[lang] = {}


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
