"""Rutas del acortador de enlaces.

* ``POST /api/links``              crea (o reutiliza) un enlace corto.
* ``GET  /api/links/{code}``       muestra el destino SIN visitarlo (vista previa).
* ``POST /api/links/{code}/report`` reporta un enlace; varios reportes lo bloquean.
* ``GET  /l/{code}``               redirige al destino (302) y cuenta la visita.

La lógica de validación y el almacén están en ``links.py``.
"""

from __future__ import annotations

import logging
import sqlite3
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from . import views
from .config import (
    CLIENT_IP_HEADER,
    SHORTLINKS_BLOCKED_HOSTS,
    SHORTLINKS_DB,
    SHORTLINKS_MAX_LINKS,
    SHORTLINKS_PER_HOUR,
    SHORTLINKS_REPORT_THRESHOLD,
    SHORTLINKS_SALT,
    SITE_URL,
)
from .links import (
    LinkCapacityError,
    LinkError,
    LinkStore,
    host_is_blocked,
    is_valid_code,
    normalize_url,
    parse_host_list,
)
from .models import ShortLinkRequest
from .pages import _add_script_nonces
from .security import RateLimiter, client_ip

logger = logging.getLogger("videodl.shortener")

router = APIRouter()

store = LinkStore(
    SHORTLINKS_DB,
    max_links=SHORTLINKS_MAX_LINKS,
    salt=SHORTLINKS_SALT.encode("utf-8") if SHORTLINKS_SALT else None,
)
BLOCKED_HOSTS = parse_host_list(SHORTLINKS_BLOCKED_HOSTS)

# Cupo de enlaces nuevos por IP y hora (aparte del límite general de la API).
create_limiter = RateLimiter(SHORTLINKS_PER_HOUR, window_seconds=3600)

_UNAVAILABLE = "El acortador no está disponible ahora mismo. Inténtalo más tarde."


def _client(request: Request) -> str:
    return client_ip(request, CLIENT_IP_HEADER)


def _own_hosts(request: Request) -> set[str]:
    hosts = {urlsplit(SITE_URL).hostname or ""}
    if request.url.hostname:
        hosts.add(request.url.hostname)
    return {h for h in hosts if h}


def _page(request: Request, status_code: int) -> HTMLResponse:
    """Página de error con el diseño del sitio y el nonce de la CSP."""
    html = views.not_found_page()
    nonce = getattr(request.state, "csp_nonce", "")
    if nonce:
        html = _add_script_nonces(html, nonce)
    return HTMLResponse(html, status_code=status_code)


@router.post("/api/links")
def create_link(payload: ShortLinkRequest, request: Request):
    if SHORTLINKS_PER_HOUR == 0:
        raise HTTPException(
            status_code=503, detail="La creación de enlaces está desactivada por ahora."
        )

    # Se valida primero: un enlace inválido no gasta cupo.
    try:
        url = normalize_url(
            payload.url, own_hosts=_own_hosts(request), blocked_hosts=BLOCKED_HOSTS
        )
    except LinkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not create_limiter.allow(_client(request)):
        raise HTTPException(
            status_code=429,
            detail="Has creado demasiados enlaces seguidos. Inténtalo de nuevo en un rato.",
        )

    try:
        code, created = store.create(url)
    except LinkError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LinkCapacityError as exc:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc
    except (sqlite3.Error, OSError) as exc:
        logger.exception("No se pudo guardar el enlace")
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc

    path = f"/l/{code}"
    return {
        "code": code,
        "path": path,
        "short_url": f"{SITE_URL}{path}",
        "url": url,
        "host": urlsplit(url).hostname,
        "created": created,
    }


@router.get("/api/links/{code}")
def preview_link(code: str):
    """Destino de un enlace corto sin visitarlo ni contar la visita."""
    if not is_valid_code(code):
        raise HTTPException(status_code=404, detail="Ese enlace corto no existe.")
    try:
        link = store.get(code)
    except (sqlite3.Error, OSError) as exc:
        logger.exception("No se pudo leer el enlace")
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc
    if link is None:
        raise HTTPException(status_code=404, detail="Ese enlace corto no existe.")
    if link["disabled"] or host_is_blocked(link["url"], BLOCKED_HOSTS):
        raise HTTPException(status_code=410, detail="Ese enlace fue bloqueado.")
    return {
        "code": link["code"],
        "url": link["url"],
        "host": urlsplit(link["url"]).hostname,
        "clicks": link["clicks"],
        "created": link["created"],
    }


@router.post("/api/links/{code}/report")
def report_link(code: str, request: Request):
    if not is_valid_code(code):
        raise HTTPException(status_code=404, detail="Ese enlace corto no existe.")
    try:
        status = store.report(code, _client(request), SHORTLINKS_REPORT_THRESHOLD)
    except (sqlite3.Error, OSError) as exc:
        logger.exception("No se pudo registrar el reporte")
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from exc
    if status == "unknown":
        raise HTTPException(status_code=404, detail="Ese enlace corto no existe.")
    return {"status": status}


@router.get("/l/{code}", include_in_schema=False)
def follow_link(code: str, request: Request):
    if not is_valid_code(code):
        return _page(request, 404)
    try:
        link = store.resolve(code)
    except (sqlite3.Error, OSError):
        logger.exception("No se pudo resolver el enlace")
        return _page(request, 503)
    if link is None:
        return _page(request, 404)
    # Bloqueado por reportes o por la lista de dominios (que se puede ampliar
    # en caliente con SHORTLINKS_BLOCKED_HOSTS sin tocar la base de datos).
    if link["disabled"] or host_is_blocked(link["url"], BLOCKED_HOSTS):
        return _page(request, 410)
    return RedirectResponse(link["url"], status_code=302)
