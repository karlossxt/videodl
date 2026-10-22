"""Configuración central de la aplicación.

Toda la configuración se resuelve una sola vez al importar el módulo. Los
valores de entorno se validan: un valor mal escrito genera un aviso por logging
y se usa el valor por defecto, en lugar de romper el arranque con un
``ValueError``.

La app solo procesa archivos aportados por el usuario: no hay ajustes de
descargas, proxies ni cookies de plataformas externas.
"""

from __future__ import annotations

import logging
import os
import shutil

logger = logging.getLogger("videodl.config")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def configure_logging() -> None:
    """Configura el logging una sola vez (nivel ajustable con ``LOG_LEVEL``)."""
    level = os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


# ---------------------------------------------------------------------------
# ffmpeg / ffprobe
# ---------------------------------------------------------------------------

_ffmpeg_path = shutil.which("ffmpeg")
_ffprobe_path = shutil.which("ffprobe")

FFMPEG_AVAILABLE = _ffmpeg_path is not None
FFPROBE_AVAILABLE = _ffprobe_path is not None
FFMPEG = _ffmpeg_path or "ffmpeg"
FFPROBE = _ffprobe_path or "ffprobe"


# ---------------------------------------------------------------------------
# Lectura de variables de entorno
# ---------------------------------------------------------------------------


def env_int(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Lee un entero de entorno; ante un valor inválido avisa y usa el defecto."""
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning("%s=%r no es un número entero; se usa %s", name, raw, default)
        return default
    if minimum is not None and value < minimum:
        logger.warning("%s=%s es menor que %s; se usa %s", name, value, minimum, default)
        return default
    if maximum is not None and value > maximum:
        logger.warning("%s=%s es mayor que %s; se usa %s", name, value, maximum, default)
        return default
    return value


def env_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# ---------------------------------------------------------------------------
# Parámetros de vídeo
# ---------------------------------------------------------------------------

# Presets válidos de x264. En servidores gratuitos (CPU muy limitada) conviene
# "veryfast". Se puede ajustar sin tocar código con la variable X264_PRESET.
_X264_PRESETS = {
    "ultrafast", "superfast", "veryfast", "faster", "fast",
    "medium", "slow", "slower", "veryslow", "placebo",
}
X264_PRESET = env_str("X264_PRESET", "veryfast").lower() or "veryfast"
if X264_PRESET not in _X264_PRESETS:
    logger.warning(
        "X264_PRESET=%r no es un preset válido de x264; se usa 'veryfast'", X264_PRESET
    )
    X264_PRESET = "veryfast"

# Tamaño máximo de archivo que el usuario puede subir.
MAX_UPLOAD_MB = env_int("MAX_UPLOAD_MB", 200, minimum=1)
# Tope del objetivo de compresión (independiente del límite de subida).
COMPRESS_MAX_TARGET_MB = env_int("COMPRESS_MAX_TARGET_MB", 200, minimum=1)
# Duración máxima de un clip.
CLIP_MAX_SECONDS = env_int("CLIP_MAX_SECONDS", 300, minimum=1)

# Tiempo máximo que puede durar un proceso ffmpeg antes de ser matado (0 = sin
# límite). Evita que una codificación colgada retenga un hilo para siempre.
FFMPEG_TIMEOUT_SECONDS = env_int("FFMPEG_TIMEOUT_SECONDS", 3600, minimum=0)


# ---------------------------------------------------------------------------
# Rate limiting y concurrencia
# ---------------------------------------------------------------------------

# Peticiones por minuto y por IP (0 = sin límite).
RATE_LIMIT_PER_MINUTE = env_int("RATE_LIMIT_PER_MINUTE", 60, minimum=0)
# Número máximo de trabajos pesados (compresión/clip) a la vez.
MAX_CONCURRENT_JOBS = env_int("MAX_CONCURRENT_JOBS", 4, minimum=1)

# Orígenes CORS permitidos (separados por comas). Vacío = mismo origen.
CORS_ORIGINS = [o.strip() for o in env_str("CORS_ORIGINS").split(",") if o.strip()]

# URL pública del sitio, sin barra final. Se usa para canonical, Open Graph,
# sitemap.xml y robots.txt. En Render se toma su URL automática si no se define.
SITE_URL = (
    (
        env_str("SITE_URL")
        or env_str("RENDER_EXTERNAL_URL")
        or "http://localhost:8000"
    ).rstrip("/")
    or "http://localhost:8000"
)

# CSP por defecto. Se puede sustituir con CONTENT_SECURITY_POLICY; dejarla
# vacía desactiva la cabecera.
DEFAULT_CONTENT_SECURITY_POLICY = (
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
_csp_env = os.environ.get("CONTENT_SECURITY_POLICY")
CONTENT_SECURITY_POLICY = (
    DEFAULT_CONTENT_SECURITY_POLICY if _csp_env is None else _csp_env.strip()
)
