"""Utilidades puras (sin dependencias del framework ni de ffmpeg)."""

from __future__ import annotations

import logging
import re
import shutil
import tempfile
import time
import unicodedata
from collections.abc import Iterable
from pathlib import Path

logger = logging.getLogger("videodl.utils")


def sanitize_filename(name: str) -> str:
    """Quita caracteres prohibidos en nombres de archivo (Windows incluido)."""
    name = unicodedata.normalize("NFKC", name or "")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:150] or "video"


def parse_extractor_args(raw: str) -> dict[str, dict[str, list[str]]]:
    """Convierte ``"youtube:player_client=tv,web"`` en el diccionario que espera yt-dlp.

    Acepta el mismo formato que ``--extractor-args`` de la línea de comandos:
    pares ``extractor:clave=valor`` separados por ``;`` y listas separadas por
    comas. Permite elegir otro cliente de extracción (p. ej. cuando YouTube
    bloquea el que se usa por defecto) sin tocar el código.
    """
    result: dict[str, dict[str, list[str]]] = {}
    extractor: str | None = None
    for chunk in (raw or "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            extractor, _, chunk = chunk.partition(":")
            extractor = extractor.strip().lower()
            chunk = chunk.strip()
            if extractor:
                result.setdefault(extractor, {})
        if not chunk:
            continue
        if extractor is None or "=" not in chunk:
            logger.warning("Argumento de extractor ignorado: %r", chunk)
            continue
        key, _, value = chunk.partition("=")
        key = key.strip()
        values = [v.strip() for v in value.split(",") if v.strip()]
        if not key or not values:
            logger.warning("Argumento de extractor ignorado: %r", chunk)
            continue
        result[extractor][key] = values
    return {name: args for name, args in result.items() if args}


def human_size(n: int | None) -> str | None:
    if not n:
        return None
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def rmtree_robust(path) -> None:
    """Borra un directorio con reintentos: en Windows los archivos pueden seguir bloqueados."""
    target = Path(path)
    for attempt in range(5):
        shutil.rmtree(target, ignore_errors=True)
        if not target.exists():
            return
        time.sleep(0.2 * (attempt + 1))
    shutil.rmtree(target, ignore_errors=True)


def sweep_temp_dirs(active_paths: Iterable[str] = (), min_age_seconds: int = 3600) -> int:
    """Elimina carpetas temporales huérfanas de ``videodl_*``.

    Nunca toca las carpetas que pertenecen a trabajos en curso (``active_paths``)
    y solo borra las que llevan más de ``min_age_seconds`` sin modificarse.
    Devuelve cuántas se eliminaron.
    """
    active = {str(Path(p)) for p in active_paths if p}
    removed = 0
    tmp_root = Path(tempfile.gettempdir())
    for folder in tmp_root.glob("videodl_*"):
        try:
            if str(folder) in active or not folder.is_dir():
                continue
            age = time.time() - folder.stat().st_mtime
            if age > min_age_seconds:
                rmtree_robust(folder)
                removed += 1
        except OSError:
            continue
    return removed


def time_tag(seconds: float | None) -> str:
    """Convierte segundos a una etiqueta corta (ej: 1m05s)."""
    if seconds is None:
        return ""
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    return f"{minutes}m{secs:02d}s"


def even(n) -> int:
    """Redondea al múltiplo de 2 más cercano (los códecs de vídeo lo necesitan)."""
    return max(2, int(round(float(n) / 2)) * 2)


def centered_crop(w: int, h: int, rw: int, rh: int) -> tuple[int, int, int, int]:
    """Rectángulo centrado con la proporción rw:rh, siempre dentro del original."""

    def _floor_even(n: int) -> int:
        return max(2, int(n) - (int(n) % 2))

    if w * rh > h * rw:  # la fuente es más ancha -> recortamos a los lados
        cw, ch = even(h * rw / rh), even(h)
    else:  # la fuente es más alta -> recortamos arriba y abajo
        cw, ch = even(w), even(w * rh / rw)
    cw, ch = min(cw, _floor_even(w)), min(ch, _floor_even(h))
    x = max(0, (w - cw) // 2)
    y = max(0, (h - ch) // 2)
    return cw, ch, x - (x % 2), y - (y % 2)
