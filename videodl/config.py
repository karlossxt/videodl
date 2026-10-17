"""Configuración central de la aplicación.

Toda la configuración se resuelve una sola vez al importar el módulo. A
diferencia de la versión anterior, los valores de entorno se validan: un valor
mal escrito genera un aviso por logging y se usa el valor por defecto, en lugar
de romper el arranque con un ``ValueError``.
"""

from __future__ import annotations

import base64
import contextlib
import logging
import os
import shutil
import stat as stat_module
import tempfile
from dataclasses import dataclass
from pathlib import Path

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

MAX_UPLOAD_MB = env_int("MAX_UPLOAD_MB", 200, minimum=1)
# Tope del objetivo de compresión (independiente del límite de subida).
COMPRESS_MAX_TARGET_MB = env_int("COMPRESS_MAX_TARGET_MB", 200, minimum=1)

CLIP_MAX_SECONDS = env_int("CLIP_MAX_SECONDS", 300, minimum=1)
CLIP_MAX_FULL_DOWNLOAD_MB = env_int("CLIP_MAX_FULL_DOWNLOAD_MB", 500, minimum=1)
# Margen de seguridad (segundos) que se descarga de más en cada extremo.
CLIP_PAD_SECONDS = max(4, env_int("CLIP_PAD_SECONDS", 12, minimum=0))

# Tiempo máximo que puede durar un proceso ffmpeg antes de ser matado (0 = sin
# límite). Evita que una codificación colgada retenga un hilo para siempre.
FFMPEG_TIMEOUT_SECONDS = env_int("FFMPEG_TIMEOUT_SECONDS", 3600, minimum=0)
# Timeout de red para yt-dlp (evita descargas colgadas que nunca terminan).
YTDLP_SOCKET_TIMEOUT = env_int("YTDLP_SOCKET_TIMEOUT", 30, minimum=0)


# ---------------------------------------------------------------------------
# Rate limiting y concurrencia
# ---------------------------------------------------------------------------

# Peticiones por minuto y por IP (0 = sin límite).
RATE_LIMIT_PER_MINUTE = env_int("RATE_LIMIT_PER_MINUTE", 60, minimum=0)
# Número máximo de trabajos pesados (descarga/compresión/clip) a la vez.
MAX_CONCURRENT_JOBS = env_int("MAX_CONCURRENT_JOBS", 4, minimum=1)

# Orígenes CORS permitidos (separados por comas). Vacío = mismo origen.
CORS_ORIGINS = [o.strip() for o in env_str("CORS_ORIGINS").split(",") if o.strip()]
# CSP opcional; vacío = no se envía cabecera.
CONTENT_SECURITY_POLICY = env_str("CONTENT_SECURITY_POLICY")


# ---------------------------------------------------------------------------
# Cookies (opcional, para YouTube desde IPs de servidor)
# ---------------------------------------------------------------------------

SECRETS_DIR = Path("/etc/secrets")


@dataclass
class CookieInfo:
    """Ruta al cookies.txt activo, origen y posible error de carga."""

    file: str | None = None
    error: str = ""
    source: str = ""


cookies = CookieInfo()


def _find_secret_file() -> str | None:
    """Devuelve un cookies.txt subido como Secret File (/etc/secrets/...).

    Usa ``stat`` en lugar de ``Path.is_file`` a propósito: ``is_file`` devuelve
    False (sin avisar) cuando no hay permisos, lo que oculta el caso típico de
    Docker en Render (usuario que no pertenece al grupo 1000).
    """
    candidates = []
    with contextlib.suppress(OSError):
        candidates.extend(sorted(SECRETS_DIR.glob("*cookie*")))
    candidates.append(SECRETS_DIR / "cookies.txt")

    if SECRETS_DIR.is_dir():
        with contextlib.suppress(OSError):
            names = sorted(p.name for p in SECRETS_DIR.iterdir())
            if names:
                logger.info("Secret Files en %s: %s", SECRETS_DIR, ", ".join(names))

    for candidate in candidates:
        try:
            info = candidate.stat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.warning("No se pudo leer el Secret File %s: %s", candidate, exc)
            continue
        if stat_module.S_ISREG(info.st_mode) and info.st_size > 0:
            return str(candidate)
    return None


def _write_private_cookies(raw: str) -> str:
    """Escribe las cookies en un directorio privado (no en una ruta predecible).

    Se crea con permisos 0700 y el archivo 0600 para que otros usuarios del
    servidor no puedan leer las cookies de sesión.
    """
    folder = Path(tempfile.gettempdir()) / ".videodl_cookies"
    folder.mkdir(mode=0o700, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(folder, 0o700)
    path = folder / "cookies.txt"
    path.write_text(raw, encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
    return str(path)


def setup_cookies() -> None:
    """Localiza el cookies.txt opcional, en este orden:

    1. Ruta indicada en YTDLP_COOKIES_FILE.
    2. Un Secret File montado en /etc/secrets (cookies.txt).
    3. El contenido en YTDLP_COOKIES (texto) o YTDLP_COOKIES_B64 (Base64).

    Es totalmente opcional: sin cookies la app funciona igual.
    """
    cookies.file = None
    cookies.error = ""
    cookies.source = ""

    # 1) Ruta personalizada
    path = env_str("YTDLP_COOKIES_FILE")
    if path and Path(path).is_file():
        cookies.file, cookies.source = path, "YTDLP_COOKIES_FILE"
        logger.info("Cookies cargadas desde YTDLP_COOKIES_FILE (%s)", path)
        return

    # 2) Secret File (Render: /etc/secrets/cookies.txt)
    found = _find_secret_file()
    if found:
        cookies.file, cookies.source = found, "secret-file"
        logger.info("Cookies cargadas desde un Secret File (%s)", found)
        return

    # 3) Contenido en variable de entorno
    raw = env_str("YTDLP_COOKIES")
    source = "YTDLP_COOKIES"
    if not raw:
        encoded = env_str("YTDLP_COOKIES_B64")
        source = "YTDLP_COOKIES_B64"
        if encoded:
            try:
                raw = base64.b64decode(encoded).decode("utf-8", "replace").strip()
            except Exception as exc:  # noqa: BLE001 - se informa al usuario
                cookies.error = f"base64 invalido ({len(encoded)} caracteres recibidos): {exc}"
                logger.warning("Cookies: %s", cookies.error)
                return

    if not raw:
        cookies.error = f"sin datos ({source} vacía o no definida)"
        return

    # El formato Netscape de cookies.txt usa tabuladores como separador.
    if "\t" not in raw:
        cookies.error = (
            f"{source} no parece un cookies.txt válido "
            f"(formato Netscape, {len(raw)} caracteres)"
        )
        logger.warning("Cookies: %s", cookies.error)
        return

    try:
        cookies.file = _write_private_cookies(raw)
        cookies.source = source
        logger.info("Cookies cargadas desde %s", source)
    except OSError as exc:
        cookies.file = None
        cookies.error = f"no se pudo escribir: {exc}"
        logger.warning("Cookies: %s", cookies.error)
