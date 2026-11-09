"""Límites de recursos: peticiones por IP y trabajos simultáneos.

La app ya no recibe URLs externas, así que las protecciones SSRF y la descarga
de imágenes de plataformas se retiraron junto con el descargador. Se conservan
los dos limitadores que protegen la CPU y el disco del servidor.
"""

from __future__ import annotations

import contextlib
import ipaddress
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """Ventana deslizante simple por clave (normalmente la IP del cliente).

    ``per_minute`` es el máximo de peticiones por ventana; la ventana dura un
    minuto salvo que se indique otra con ``window_seconds``.
    """

    def __init__(self, per_minute: int, window_seconds: float = 60.0) -> None:
        self.per_minute = per_minute
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        window = self.window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= self.per_minute:
                return False
            bucket.append(now)
            # Limpieza perezosa de claves inactivas para no crecer sin control.
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v]:
                    self._hits.pop(k, None)
            return True


class ConcurrencyLimiter:
    """Semáforo con adquisición no bloqueante para acotar trabajos pesados."""

    def __init__(self, limit: int) -> None:
        self.limit = max(1, limit)
        self._sem = threading.BoundedSemaphore(self.limit)

    def acquire(self) -> bool:
        return self._sem.acquire(blocking=False)

    def release(self) -> None:
        with contextlib.suppress(ValueError):  # ya liberado
            self._sem.release()


def client_ip(request, header: str = "") -> str:
    """IP del cliente para los límites y los reportes.

    Por defecto es la IP de la conexión. Detrás de un proxy esa IP es la del proxy y
    todos los visitantes parecerían uno solo, así que ``header`` permite indicar la
    cabecera que el proxy rellena con la IP real (p. ej. ``cf-connecting-ip``).

    Solo debe usarse con una cabecera que el proxy **sobrescriba** y a la que el
    cliente no pueda llegar directamente: si no, cualquiera podría falsificarla y
    saltarse los límites. Un valor que no sea una IP válida se ignora.
    """
    if header:
        raw = (request.headers.get(header) or "").split(",")[0].strip()
        if raw:
            try:
                return str(ipaddress.ip_address(raw))
            except ValueError:
                pass
    return request.client.host if request.client else "desconocido"
