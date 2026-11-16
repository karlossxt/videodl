"""Versión de los assets locales para poder cachearlos sin quedarse viejos.

Los archivos de ``static/`` no llevan huella en el nombre (``style.css``,
``common.js``...). Para que un despliegue no deje código antiguo en caché, las
páginas añaden ``?v=<hash>`` a sus referencias y el middleware solo permite
cachear para siempre las URLs cuya versión sigue vigente; el resto revalida.
"""

from __future__ import annotations

import hashlib
import re

from .paths import STATIC_DIR

# Extensiones que se sirven tal cual desde ``static/``.
_EXTENSIONS = (
    "css",
    "js",
    "mjs",
    "png",
    "jpg",
    "jpeg",
    "svg",
    "webp",
    "ico",
    "woff2",
    "woff",
)

# ``src="..."`` y ``href="..."`` con una ruta local. Las URLs absolutas
# (``https://``, ``//``, ``data:``) quedan fuera porque el grupo no admite ``:``.
_PATTERN = re.compile(
    r'(?P<start>\b(?:src|href)=")(?P<url>(?:/|\./)?[\w./-]+\.(?:'
    + "|".join(_EXTENSIONS)
    + r'))(?P<end>")'
)

_ROOT = STATIC_DIR.resolve()

# rel_path -> (mtime_ns, tamaño, hash). Se recalcula solo si el archivo cambia.
_cache: dict[str, tuple[int, int, str]] = {}


def _version(path: str) -> str:
    """Hash corto del asset, o cadena vacía si no existe o está fuera de static/."""
    rel = path.split("?", 1)[0].lstrip("/")
    if rel.startswith("./"):
        rel = rel[2:]
    if not rel or ".." in rel.split("/"):
        return ""
    file = (STATIC_DIR / rel).resolve()
    if not file.is_relative_to(_ROOT) or not file.is_file():
        return ""
    stat = file.stat()
    cached = _cache.get(rel)
    if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    digest = hashlib.sha256(file.read_bytes()).hexdigest()[:12]
    _cache[rel] = (stat.st_mtime_ns, stat.st_size, digest)
    return digest


def version_for(path: str) -> str:
    """Versión vigente de un asset (cadena vacía si no existe)."""
    return _version(path)


def version_html(html: str) -> str:
    """Añade ``?v=<hash>`` a las referencias locales de CSS, JS e imágenes."""

    def replace(match: re.Match[str]) -> str:
        url = match.group("url")
        digest = _version(url)
        if not digest:
            return match.group(0)
        return f"{match.group('start')}{url}?v={digest}{match.group('end')}"

    return _PATTERN.sub(replace, html)
