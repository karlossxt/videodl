"""Seguridad: validación de URLs, protección SSRF, rate limit y concurrencia.

- ``validate_url`` / ``ensure_public_url`` comprueban que la URL es http(s) y
  que no apunta a direcciones internas (loopback, rangos privados, metadata de
  cloud…) para evitar SSRF.
- ``RateLimiter`` limita las peticiones por IP (ventana deslizante).
- ``ConcurrencyLimiter`` acota cuántos trabajos pesados corren a la vez.
- ``fetch_image`` descarga imágenes validando cada redirección y con un tope de
  tamaño.
"""

from __future__ import annotations

import contextlib
import ipaddress
import logging
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import HTTPException

logger = logging.getLogger("videodl.security")

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

# Nombres de host que nunca deben resolverse desde el servidor.
_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "metadata.google.internal"}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal")


def validate_url(url: str) -> None:
    """Comprueba el esquema (http/https). No resuelve el host."""
    if not url or not _URL_RE.match(url.strip()):
        raise HTTPException(status_code=400, detail="La URL debe empezar por http:// o https://")


def _ip_is_public(ip_str: str) -> bool:
    try:
        return ipaddress.ip_address(ip_str).is_global
    except ValueError:
        return False


def host_is_public(host: str) -> bool:
    """True si todas las direcciones IP resueltas del host son públicas."""
    host = (host or "").strip().strip("[]").lower()
    if not host or host in _BLOCKED_HOSTNAMES or host.endswith(_BLOCKED_SUFFIXES):
        return False

    # Si ya es una IP literal, se comprueba directamente.
    # Ojo: hay que usar ``ipaddress.ip_address`` aquí y no ``_ip_is_public``,
    # porque esa auxiliar captura el ValueError y devuelve False, lo que haría
    # que cualquier dominio se rechazara sin llegar a resolver el DNS.
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        pass  # no es una IP literal: hay que resolver el dominio

    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    return all(_ip_is_public(info[4][0]) for info in infos)


def ensure_public_url(url: str) -> None:
    """Valida el esquema y que el host sea público. Lanza HTTPException si no."""
    validate_url(url)
    parsed = urlparse(url.strip())
    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="La URL no tiene un dominio válido")
    if not host_is_public(parsed.hostname):
        raise HTTPException(
            status_code=400,
            detail="No se permiten direcciones internas, privadas o locales.",
        )


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class RateLimiter:
    """Ventana deslizante simple por clave (normalmente la IP del cliente)."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        window = 60.0
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


# ---------------------------------------------------------------------------
# Concurrencia
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Descarga segura de imágenes (miniaturas)
# ---------------------------------------------------------------------------


class _GuardedRedirect(urllib.request.HTTPRedirectHandler):
    """Revalida cada redirección antes de seguirla (evita SSRF por redirect)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        ensure_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_image(url: str, max_bytes: int = 15 * 1024 * 1024) -> tuple[bytes, str]:
    """Descarga una imagen desde ``url`` de forma segura.

    Valida el host, revalida las redirecciones y corta si supera ``max_bytes``.
    Devuelve ``(datos, content_type)``.
    """
    ensure_public_url(url)
    opener = urllib.request.build_opener(_GuardedRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (VideoDL)"})
    with opener.open(request, timeout=30) as response:  # noqa: S310 - host validado
        content_type = response.headers.get_content_type()
        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise HTTPException(status_code=413, detail="La imagen es demasiado grande.")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status_code=413, detail="La imagen es demasiado grande.")
            chunks.append(chunk)
    return b"".join(chunks), content_type
