"""Construcción de la aplicación FastAPI."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .clips import router as clips_router
from .compressor import router as compressor_router
from .config import (
    CLIP_MAX_SECONDS,
    COMPRESS_MAX_TARGET_MB,
    CONTENT_SECURITY_POLICY,
    CORS_ORIGINS,
    FFMPEG_AVAILABLE,
    FFPROBE_AVAILABLE,
    MAX_UPLOAD_MB,
    RATE_LIMIT_PER_MINUTE,
    configure_logging,
)
from .legacy import router as legacy_router
from .pages import router as pages_router
from .paths import STATIC_DIR
from .runtime import rate_limiter
from .stores import active_tmpdirs, cleanup_all
from .utils import sweep_temp_dirs
from .whatsapp import SEGNO_AVAILABLE
from .whatsapp import router as whatsapp_router

logger = logging.getLogger("videodl.app")


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
    """Limpia restos de ejecuciones anteriores y arranca el limpiador."""
    configure_logging()
    # Al arrancar no hay trabajos activos: se pueden borrar los restos de más de 5 min.
    await asyncio.to_thread(sweep_temp_dirs, [], 300)
    threading.Thread(target=_janitor_loop, daemon=True).start()
    logger.info("FasTools %s iniciado (ffmpeg=%s)", __version__, FFMPEG_AVAILABLE)
    yield
    logger.info("FasTools detenido")


def create_app() -> FastAPI:
    app = FastAPI(title="FasTools.app", version=__version__, lifespan=lifespan)

    if CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=CORS_ORIGINS,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    csp = CONTENT_SECURITY_POLICY

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
        """Estado del servicio: solo capacidades activas, sin secretos ni rutas."""
        ffmpeg_ok = FFMPEG_AVAILABLE and FFPROBE_AVAILABLE
        return {
            "status": "ok",
            "version": __version__,
            "ffmpeg": FFMPEG_AVAILABLE,
            "ffprobe": FFPROBE_AVAILABLE,
            # El compresor y los clips necesitan ambos binarios.
            "compressor": ffmpeg_ok,
            "clips": ffmpeg_ok,
            "whatsapp": SEGNO_AVAILABLE,
            "clip_max_seconds": CLIP_MAX_SECONDS,
            "max_upload_mb": MAX_UPLOAD_MB,
            "max_target_mb": COMPRESS_MAX_TARGET_MB,
        }

    app.include_router(compressor_router)
    app.include_router(clips_router)
    app.include_router(whatsapp_router)
    app.include_router(legacy_router)
    app.include_router(pages_router)

    # Los archivos estáticos van al final para que la API tenga prioridad.
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app


# Instancia a nivel de módulo para ``uvicorn videodl.app:app``.
app = create_app()
