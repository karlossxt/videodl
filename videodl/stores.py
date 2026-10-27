"""Almacenes de trabajos y tareas de mantenimiento comunes."""

from __future__ import annotations

from .jobs import JobStore

# Un almacén por dominio de la API. Comparten el mismo TTL (1 hora).
downloads = JobStore(session="downloads")
compressions = JobStore(session="compressions")
clips = JobStore(session="clips")
transcriptions = JobStore(session="transcriptions")

ALL_STORES: tuple[JobStore, ...] = (downloads, compressions, clips, transcriptions)


def cleanup_all() -> int:
    """Limpia los trabajos vencidos de todos los almacenes."""
    return sum(store.cleanup_stale() for store in ALL_STORES)


def active_tmpdirs() -> list[str]:
    """Carpetas temporales de trabajos en curso (para no borrarlas al limpiar)."""
    result: list[str] = []
    for store in ALL_STORES:
        result.extend(store.active_tmpdirs())
    return result
