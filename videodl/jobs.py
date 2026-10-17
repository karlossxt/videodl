"""Almacén genérico de trabajos en memoria.

Reemplaza los tres diccionarios duplicados (descargas, compresor y clips) por una
única clase con TTL. A diferencia de la versión anterior, la limpieza **no borra
trabajos en curso**: solo elimina los que ya están en estado terminal (o pide
cancelar los que llevan demasiado tiempo corriendo).
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger("videodl.jobs")

# Estados que indican que el trabajo ya no se está ejecutando.
TERMINAL_STATUSES = frozenset({"finished", "error", "cancelled"})


class JobStore:
    """Colección de trabajos indexados por id, segura para hilos."""

    def __init__(
        self,
        *,
        session: str,
        ttl_seconds: int = 3600,
        hard_ttl_seconds: int | None = None,
    ) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._session = session
        self._ttl = ttl_seconds
        # Los trabajos que nunca terminan se cancelan pasado este tiempo.
        self._hard_ttl = hard_ttl_seconds or ttl_seconds * 3

    # -- CRUD ---------------------------------------------------------------

    def new(self, **fields: Any) -> str:
        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "status": "pending",
            "cancel": False,
            "error": None,
            "created": time.time(),
        }
        job.update(fields)
        with self._lock:
            self._jobs[job_id] = job
        logger.debug("[%s] trabajo %s creado", self._session, job_id)
        return job_id

    def update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(fields)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def request_cancel(self, job_id: str) -> str | None:
        """Marca el trabajo como cancelado. Devuelve su estado (o None si no existe)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job["status"] in TERMINAL_STATUSES:
                return job["status"]
            job["cancel"] = True
        return "cancelling"

    def delete(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job and job.get("tmpdir"):
            from .utils import rmtree_robust

            rmtree_robust(job["tmpdir"])
        logger.debug("[%s] trabajo %s eliminado", self._session, job_id)

    # -- Mantenimiento ------------------------------------------------------

    def active_tmpdirs(self) -> list[str]:
        with self._lock:
            return [
                job["tmpdir"]
                for job in self._jobs.values()
                if job.get("tmpdir") and job["status"] not in TERMINAL_STATUSES
            ]

    def count_active(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j["status"] not in TERMINAL_STATUSES)

    def cleanup_stale(self) -> int:
        """Limpia trabajos vencidos. Devuelve cuántos se eliminaron."""
        now = time.time()
        to_delete: list[str] = []
        to_cancel: list[str] = []
        with self._lock:
            for job_id, job in self._jobs.items():
                age = now - job.get("created", now)
                if job["status"] in TERMINAL_STATUSES:
                    if age > self._ttl:
                        to_delete.append(job_id)
                elif age > self._hard_ttl:
                    job["cancel"] = True
                    to_cancel.append(job_id)
        for job_id in to_delete:
            self.delete(job_id)
        if to_cancel:
            logger.warning(
                "[%s] %s trabajos superaron el tiempo máximo y se cancelaron",
                self._session,
                len(to_cancel),
            )
        return len(to_delete)

    def all_tmpdirs(self) -> Iterable[str]:
        with self._lock:
            return [j["tmpdir"] for j in self._jobs.values() if j.get("tmpdir")]
