"""Rutas base del proyecto."""

from __future__ import annotations

from pathlib import Path

# El paquete vive en ``<proyecto>/videodl``, así que la raíz es el directorio padre.
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
