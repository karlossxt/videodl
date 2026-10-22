"""Lanzador de trabajos pesados en segundo plano.

Vive en su propio módulo para que el compresor y el recortador de clips no
dependan del antiguo router de descargas (ya retirado) ni entre ellos.
"""

from __future__ import annotations

import logging
import threading

from fastapi import HTTPException

from .runtime import job_limiter

logger = logging.getLogger("videodl.tasks")


def spawn_job(target, *args) -> None:
    """Lanza un trabajo en un hilo, respetando el límite de concurrencia."""
    if not job_limiter.acquire():
        raise HTTPException(
            status_code=429,
            detail=(
                "El servidor está procesando demasiados vídeos ahora mismo. "
                "Inténtalo de nuevo en unos segundos."
            ),
        )

    def _runner() -> None:
        try:
            target(*args)
        except Exception:  # noqa: BLE001 - último cortafuegos del hilo
            logger.exception("Trabajo en segundo plano falló sin control")
        finally:
            job_limiter.release()

    threading.Thread(target=_runner, daemon=True).start()
