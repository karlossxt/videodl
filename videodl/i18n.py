"""Carga de traducciones y utilidades de internacionalización.

Los locales viven en ``videodl/locales/{lang}.json``. El idioma base es el
español (URLs sin prefijo) y el inglés se sirve bajo ``/en/``. El diccionario
incluye metadatos, catálogo, textos de interfaz y un mapa ``html`` para traducir
las plantillas estáticas sin duplicar cada archivo HTML.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("videodl.i18n")

LOCALES_DIR = Path(__file__).resolve().parent / "locales"
SUPPORTED_LANGS: tuple[str, ...] = ("es", "en")
DEFAULT_LANG = "es"
GLOBAL_LANG = "en"
LOCALE_NAMES = {"es": "Español", "en": "English"}

_translations: dict[str, dict[str, Any]] = {}
_loaded = False

# Etiquetas cuyo contenido no debe traducirse: código, scripts y estilos.
_SKIP_TAGS = {"script", "style", "code", "pre", "textarea"}
_TRANSLATABLE_ATTRS = ("title", "aria-label", "placeholder", "alt")
_TAG_RE = re.compile(r"(<[^>]*>)")
_ATTR_RE = re.compile(
    r'\b(title|aria-label|placeholder|alt)\s*=\s*(["\'])(.*?)\2',
    re.IGNORECASE | re.DOTALL,
)


def normalize_lang(lang: str | None) -> str:
    """Devuelve ``es`` o ``en``; cualquier otro valor cae en el idioma global."""
    value = (lang or "").strip().lower()
    return value if value in SUPPORTED_LANGS else GLOBAL_LANG


def load_translations(*, force: bool = False) -> None:
    """Carga ambos JSON en memoria. Se llama al arrancar la aplicación."""
    global _loaded
    if _loaded and not force:
        return
    _translations.clear()
    for lang in SUPPORTED_LANGS:
        path = LOCALES_DIR / f"{lang}.json"
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("el JSON debe contener un objeto")
            _translations[lang] = data
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.exception("No se pudo cargar el locale %s: %s", lang, exc)
            _translations[lang] = {}
    _loaded = True


def get_translations(lang: str | None) -> dict[str, Any]:
    """Devuelve el diccionario del idioma pedido, con carga diferida."""
    if not _loaded:
        load_translations()
    normalized = normalize_lang(lang)
    return _translations.get(normalized) or _translations.get(GLOBAL_LANG) or {}


def _lookup(data: dict[str, Any], key: str) -> Any:
    current: Any = data
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _format(value: str, values: dict[str, Any]) -> str:
    if not values:
        return value
    for name, replacement in values.items():
        value = value.replace("{" + name + "}", str(replacement))
    return value


def t(lang: str | None, key: str, **values: Any) -> str:
    """Traduce una clave con formato ``seccion.clave``.

    Si falta en el idioma pedido se prueba en inglés y después en español. Si no
    existe en ninguno, se devuelve la propia clave para que el fallo sea visible
    sin romper la página.
    """
    normalized = normalize_lang(lang)
    for candidate in (normalized, GLOBAL_LANG, DEFAULT_LANG):
        value = _lookup(get_translations(candidate), key)
        if isinstance(value, str):
            return _format(value, values)
    return key


def tr(lang: str | None, key: str, default: str, **values: Any) -> str:
    """Como :func:`t`, pero devuelve ``default`` si la clave no existe."""
    value = t(lang, key, **values)
    return default if value == key else value


def html_map(lang: str | None) -> dict[str, str]:
    """Mapa ``texto español -> texto traducido`` para plantillas estáticas."""
    if normalize_lang(lang) == DEFAULT_LANG:
        return {}
    value = get_translations(lang).get("html")
    if not isinstance(value, dict):
        return {}
    return {str(key): str(translation) for key, translation in value.items() if key}


def localize_path(lang: str | None, path: str, query: str = "") -> str:
    """Convierte ``/herramientas`` en ``/en/herramientas`` cuando toca.

    El español conserva la URL sin prefijo para no romper el SEO existente. La
    raíz inglesa es ``/en/`` (con barra final).
    """
    normalized = normalize_lang(lang)
    base = path or "/"
    if base.startswith("/en/") or base == "/en":
        base = base[3:] or "/"
    if not base.startswith("/"):
        base = "/" + base
    if normalized == DEFAULT_LANG:
        result = base
    elif base == "/":
        result = "/en/"
    else:
        result = "/en" + base
    if query:
        result += ("&" if "?" in result else "?") + query.lstrip("?")
    return result


def unlocalize_path(path: str) -> str:
    """Quita el prefijo ``/en`` de una ruta para obtener la ruta canónica base."""
    if path == "/en" or path == "/en/":
        return "/"
    if path.startswith("/en/"):
        return path[3:] or "/"
    return path


def language_urls(path: str) -> dict[str, str]:
    """URLs de las dos variantes y de ``x-default`` para una ruta base."""
    base = unlocalize_path(path)
    return {
        "es": localize_path("es", base),
        "en": localize_path("en", base),
        "x-default": localize_path(GLOBAL_LANG, base),
    }


def frontend_strings(lang: str | None) -> dict[str, Any]:
    """Objeto pequeño que se inyecta como ``window.I18N_STRINGS``."""
    normalized = normalize_lang(lang)
    data = get_translations(normalized)
    return {
        "lang": normalized,
        "js": data.get("js", {}),
        "nav": data.get("nav", {}),
        "common": data.get("common", {}),
    }


def inline_script(lang: str | None) -> str:
    """Script inline estable (mismo contenido siempre para el mismo idioma)."""
    payload = json.dumps(
        frontend_strings(lang),
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    return f"window.I18N_STRINGS = {payload};"


def script_hashes() -> tuple[str, ...]:
    """Hashes CSP de los scripts inline de ambos idiomas."""
    hashes = []
    for lang in SUPPORTED_LANGS:
        digest = hashlib.sha256(inline_script(lang).encode("utf-8")).digest()
        import base64

        hashes.append(base64.b64encode(digest).decode("ascii"))
    return tuple(hashes)


def csp_with_script_hashes(csp: str) -> str:
    """Añade los hashes de los scripts inline a la directiva ``script-src``."""
    if not csp:
        return csp
    tokens = [f"'sha256-{value}'" for value in script_hashes()]
    parts = csp.split(";")
    for index, part in enumerate(parts):
        fields = part.strip().split()
        if fields and fields[0].lower() == "script-src":
            parts[index] = " ".join([*fields, *tokens])
            return ";".join(parts)
    return csp


def _tag_name(tag: str) -> tuple[str, bool]:
    """Devuelve ``(nombre, es_cierre)`` de una etiqueta HTML."""
    match = re.match(r"<\s*(/)?\s*([a-zA-Z0-9:-]+)", tag)
    if not match:
        return "", False
    return match.group(2).lower(), bool(match.group(1))


def translate_html(html_text: str, lang: str | None) -> str:
    """Traduce texto y atributos de una página ya renderizada.

    Se usa para las plantillas HTML estáticas y para el contenido SEO de las
    suites de imagen/PDF, que así no necesitan duplicarse en dos idiomas. No
    toca ``script``, ``style``, ``code``, ``pre`` ni ``textarea``.
    """
    mapping = html_map(lang)
    if not mapping:
        return html_text

    # Los comentarios pueden contener etiquetas y texto que no deben traducirse:
    # si se toca su cierre ``-->`` el navegador oculta el resto de la página.
    comments: list[str] = []

    def stash_comment(match: re.Match[str]) -> str:
        comments.append(match.group(0))
        return f"\x00I18NCOMMENT{len(comments) - 1}\x00"

    protected = re.sub(r"<!--.*?-->", stash_comment, html_text, flags=re.DOTALL)

    def replace_attr(match: re.Match[str]) -> str:
        attr, quote, value = match.groups()
        replacement = mapping.get(value)
        if replacement is None:
            return match.group(0)
        return f'{attr}={quote}{replacement}{quote}'

    parts = _TAG_RE.split(protected)
    skip_stack: list[str] = []
    in_head = False

    for index, part in enumerate(parts):
        if not part:
            continue
        if part.startswith("<"):
            name, closing = _tag_name(part)
            skip_marked = (
                'translate="no"' in part.lower()
                or "data-i18n-skip" in part.lower()
            )
            # Los atributos visibles se traducen solo dentro de etiquetas
            # normales: nunca dentro de head, script, style o bloques omitidos.
            if (
                not in_head
                and not skip_stack
                and not skip_marked
                and name not in {"script", "style"}
            ):
                parts[index] = _ATTR_RE.sub(replace_attr, part)
            if name == "head":
                in_head = not closing
            if name in _SKIP_TAGS or (skip_marked and not closing):
                if closing:
                    if skip_stack and skip_stack[-1] == name:
                        skip_stack.pop()
                else:
                    skip_stack.append(name)
            elif closing and skip_stack and skip_stack[-1] == name:
                skip_stack.pop()
            continue
        if in_head or skip_stack:
            continue
        stripped = part.strip()
        if not stripped or stripped not in mapping:
            continue
        leading = part[: len(part) - len(part.lstrip())]
        trailing = part[len(part.rstrip()) :]
        parts[index] = leading + mapping[stripped] + trailing

    translated = "".join(parts)
    for index, comment in enumerate(comments):
        translated = translated.replace(f"\x00I18NCOMMENT{index}\x00", comment)
    return translated


__all__ = [
    "DEFAULT_LANG",
    "GLOBAL_LANG",
    "LOCALES_DIR",
    "LOCALE_NAMES",
    "SUPPORTED_LANGS",
    "csp_with_script_hashes",
    "frontend_strings",
    "get_translations",
    "html_map",
    "inline_script",
    "language_urls",
    "load_translations",
    "localize_path",
    "normalize_lang",
    "script_hashes",
    "t",
    "tr",
    "translate_html",
    "unlocalize_path",
]
