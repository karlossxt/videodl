"""Construcción de la aplicación FastAPI."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, errors
from .clips import router as clips_router
from .compressor import router as compressor_router
from .config import (
    CLIP_MAX_SECONDS,
    CORS_ORIGINS,
    FFMPEG_AVAILABLE,
    FFPROBE_AVAILABLE,
    IMPERSONATION_AVAILABLE,
    MAX_UPLOAD_MB,
    RATE_LIMIT_PER_MINUTE,
    configure_logging,
    cookie_file_names,
    cookies,
    disabled_platforms,
    setup_cookies,
)
from .downloader import router as downloader_router
from .pages import router as pages_router
from .paths import STATIC_DIR
from .runtime import rate_limiter
from .stores import active_tmpdirs, cleanup_all
from .utils import sweep_temp_dirs
from .whatsapp import router as whatsapp_router

logger = logging.getLogger("videodl.app")

# CSP por defecto. Se puede sustituir con CONTENT_SECURITY_POLICY o desactivar
# dejando la variable vacía.
_DEFAULT_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob: https:; "
    "media-src 'self' blob: data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


def _resolve_csp() -> str:
    configured = os.environ.get("CONTENT_SECURITY_POLICY")
    if configured is None:
        return _DEFAULT_CSP
    return configured.strip()


def _janitor_loop() -> None:
    """Hilo de limpieza: cada 10 minutos libera trabajos vencidos y residuos."""
    while True:
        time.sleep(600)
        try:
            cleanup_all()
            sweep_temp_dirs(active_tmpdirs(), min_age_seconds=3600)
        except Exception:  # noqa: BLE001 - el limpiador nunca debe caerse
            logger.exception("Fallo en el hilo de limpieza")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Prepara cookies, limpia restos de ejecuciones anteriores y arranca el limpiador."""
    configure_logging()
    setup_cookies()
    # Al arrancar no hay trabajos activos: se pueden borrar los restos de más de 5 min.
    await asyncio.to_thread(sweep_temp_dirs, [], 300)
    threading.Thread(target=_janitor_loop, daemon=True).start()
    logger.info("VideoDL %s iniciado (ffmpeg=%s)", __version__, FFMPEG_AVAILABLE)
    yield
    logger.info("VideoDL detenido")


def create_app() -> FastAPI:
    app = FastAPI(title="VideoDL", version=__version__, lifespan=lifespan)

    if CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=CORS_ORIGINS,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    csp = _resolve_csp()

    @app.middleware("http")
    async def security_and_limits(request: Request, call_next):
        # Rate limiting solo para la API (los estáticos y las páginas no cuentan).
        if RATE_LIMIT_PER_MINUTE > 0 and request.url.path.startswith("/api/"):
            client = request.client.host if request.client else "desconocido"
            if not rate_limiter.allow(client):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Demasiadas peticiones. Espera un momento e inténtalo de nuevo."},
                )

        started = time.perf_counter()
        response = await call_next(request)

        # Cabeceras de seguridad básicas.
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if csp:
            response.headers["Content-Security-Policy"] = csp

        elapsed = time.perf_counter() - started
        if elapsed > 5:
            logger.warning("Petición lenta: %s %s tardó %.1fs", request.method, request.url.path, elapsed)
        return response

    @app.get("/api/health")
    @app.get("/health")
    async def health():
        """Comprobación de estado del servicio (sin filtrar datos sensibles)."""
        return {
            "status": "ok",
            "version": __version__,
            "ffmpeg": FFMPEG_AVAILABLE,
            "ffprobe": FFPROBE_AVAILABLE,
            "compressor": FFMPEG_AVAILABLE and FFPROBE_AVAILABLE,
            "clips": FFMPEG_AVAILABLE and FFPROBE_AVAILABLE,
            # Impersonación de navegador (curl-cffi). Si es false, TikTok y otras
            # webs que la exigen fallan con un error genérico de respuesta.
            "impersonation": IMPERSONATION_AVAILABLE,
            "clip_max_seconds": CLIP_MAX_SECONDS,
            "max_upload_mb": MAX_UPLOAD_MB,
            # Plataformas pausadas a propósito. Se reactivan sin tocar código con
            # VIDEODL_DISABLED_PLATFORMS="" (vuelven todas) o cambiando la lista.
            "disabled_platforms": disabled_platforms(),
            "cookies": bool(cookies.file),
            # Diagnóstico sin filtrar secretos: si las cookies traen una sesión
            # iniciada, cuántas son y de dónde salieron. Un fichero sin sesión se
            # comporta como si no hubiera cookies, y es el fallo más difícil de ver
            # desde fuera (sobre todo cuando se configuran dos orígenes a la vez y
            # el que se actualiza no es el que se usa).
            "cookies_session": cookies.session,
            "cookies_count": cookies.count,
            "cookies_source": cookies.source,
            # Solo el nombre del fichero, nunca la ruta: es lo que hace falta para
            # saber qué Secret File hay que actualizar si hay más de uno.
            "cookies_file": cookie_file_names(),
            # Ficheros de cookies que existen pero no se pudieron usar, con el
            # motivo. Solo se listan los que *parecen* cookies: así un tarro en un
            # formato raro no se pierde en silencio, y no se publican otros secretos.
            "cookies_ignored": cookies.ignored,
            # Lo pone la última extracción: YouTube rota la sesión cada cierto
            # tiempo y, cuando lo hace, el mejor arreglo es volver a exportar.
            "cookies_rotated": errors.cookies_rotadas(),
        }

    app.include_router(downloader_router)
    app.include_router(compressor_router)
    app.include_router(clips_router)
    app.include_router(whatsapp_router)
    app.include_router(pages_router)

    # Los archivos estáticos van al final para que la API tenga prioridad.
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app


# Instancia a nivel de módulo para ``uvicorn videodl.app:app``.
app = create_app()
