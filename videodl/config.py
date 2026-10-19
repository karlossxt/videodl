"""Configuración central de la aplicación.

Toda la configuración se resuelve una sola vez al importar el módulo. A
diferencia de la versión anterior, los valores de entorno se validan: un valor
mal escrito genera un aviso por logging y se usa el valor por defecto, en lugar
de romper el arranque con un ``ValueError``.
"""

from __future__ import annotations

import base64
import contextlib
import importlib.util
import logging
import os
import shutil
import stat as stat_module
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .utils import parse_extractor_args

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

# Impersonación de navegador: la exigen plataformas como TikTok para no rechazar
# la petición. yt-dlp la aporta con el extra "curl-cffi" (está en requirements.txt),
# que es independiente del runtime de JavaScript: deno resuelve la firma de
# YouTube y curl-cffi imita al navegador en el resto de webs.
IMPERSONATION_AVAILABLE = importlib.util.find_spec("curl_cffi") is not None


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
# Proxy para todas las peticiones de yt-dlp. Útil cuando la IP del servidor está
# bloqueada por la plataforma (p. ej. YouTube desde un datacenter). Ejemplos:
# "http://usuario:clave@host:8080" o "socks5://host:1080".
YTDLP_PROXY = env_str("YTDLP_PROXY")
# Argumentos del extractor de yt-dlp, con el mismo formato que la opción
# --extractor-args de la CLI: "youtube:player_client=tv,web_safari".
# Permite elegir otro cliente de extracción sin tocar código.
YTDLP_EXTRACTOR_ARGS = parse_extractor_args(env_str("YTDLP_EXTRACTOR_ARGS"))
# Segundos que se le dejan al proveedor de PO tokens (bgutil) para firmar una
# petición a YouTube. El plugin corta a los 20 s que bastan en un PC normal; un
# plan gratuito (0,1 CPU) puede tardar más, así que se amplía (0 = desactivar el
# proveedor, útil para comparar sin él).
YTDLP_POT_TIMEOUT = env_int("YTDLP_POT_TIMEOUT", 60, minimum=0)


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
    """Ruta al cookies.txt activo, origen, posible error y si trae sesión.

    ``session``/``count`` describen lo que hay dentro del fichero (nombres y
    número de cookies, nunca sus valores). Sirven para detectar el fallo más
    común: exportar las cookies con la sesión de YouTube cerrada, con lo que
    yt-dlp navega como anónimo y la plataforma sigue pidiendo verificación.

    ``origin``/``raw`` recuerdan de dónde salieron para poder rehacer la copia de
    trabajo antes de cada extracción (ver ``refresh_cookies``). ``extras`` son
    otros tarros que se unen al principal (ver ``_merge_cookie_jars``).
    """

    file: str | None = None
    error: str = ""
    source: str = ""
    session: bool = False
    count: int = 0
    origin: str | None = None
    raw: str | None = None
    extras: list[str] = field(default_factory=list)


cookies = CookieInfo()

# Serializa la reescritura de la copia de trabajo (varias extracciones a la vez).
_cookies_lock = threading.Lock()

# Cookies que solo aparecen si se exportó con la cuenta de YouTube iniciada.
# Si no hay ninguna, el fichero no aporta sesión: yt-dlp navegará como anónimo.
_SESSION_COOKIE_NAMES = frozenset({
    "SID", "HSID", "SSID", "APISID", "SAPISID",
    "__Secure-1PSID", "__Secure-3PSID", "LOGIN_INFO",
})


def _cookie_names(raw: str) -> set[str]:
    """Nombres de las cookies del fichero (nunca sus valores).

    En el formato Netscape el nombre ocupa la sexta columna. Las cookies
    ``HttpOnly`` —entre ellas las de la sesión, ``__Secure-1PSID``— llevan el
    prefijo ``#HttpOnly_`` delante del dominio, así que hay que mirarlas antes
    de descartar las líneas que empiezan por ``#``.
    """
    names: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        elif not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) >= 7:
            names.add(fields[5].strip())
    return names


def _cookie_key(line: str) -> tuple[str, str, str] | None:
    """Clave (dominio, ruta, nombre) de una línea del tarro, o ``None`` si no es una cookie."""
    if line.startswith("#HttpOnly_"):
        line = line[len("#HttpOnly_"):]
    elif not line or line.startswith("#"):
        return None
    fields = line.split("\t")
    if len(fields) < 7:
        return None
    return fields[0].strip(), fields[2].strip(), fields[5].strip()


def _merge_cookie_jars(primary: str, extras: list[str]) -> str:
    """Une varios ``cookies.txt`` en uno. Los extras nunca pisan al principal.

    Las cookies van por dominio, así que un tarro de YouTube y otro de Reddit
    conviven sin estorbarse: cada web recibe solo las suyas. Ante una cookie
    repetida (mismo dominio, ruta y nombre) se conserva la del fichero principal,
    de modo que añadir tarros solo puede aportar sitios nuevos, nunca cambiar los
    que ya funcionaban.
    """
    lines = [line for line in primary.splitlines() if line.strip()]
    vistas = {key for line in lines if (key := _cookie_key(line))}

    for extra in extras:
        for line in extra.splitlines():
            if not line.strip():
                continue
            key = _cookie_key(line)
            if key is None:
                # Comentarios y cabeceras de los extras (el principal ya la trae).
                continue
            if key in vistas:
                continue
            vistas.add(key)
            lines.append(line)

    return "\n".join(lines) + "\n"


def _check_session(raw: str, shown: str) -> None:
    """Anota si las cookies traen sesión y avisa si no es así."""
    names = _cookie_names(raw)
    cookies.session = bool(names & _SESSION_COOKIE_NAMES)
    cookies.count = len(names)
    if cookies.session:
        logger.info("Cookies con sesión de YouTube (%d cookies) desde %s", len(names), shown)
        return
    logger.warning(
        "Las cookies de %s no incluyen ninguna cookie de sesión (%d en total): "
        "se enviarán como anónimas y la plataforma seguirá pidiendo verificación "
        "desde el servidor. Exporta cookies.txt con la cuenta de YouTube iniciada.",
        shown,
        len(names),
    )


def _find_secret_file() -> str | None:
    """Devuelve un cookies.txt subido como Secret File (/etc/secrets/...).

    Se busca el nombre canónico (``cookies.txt``) **antes** que cualquier otro que
    contenga «cookie»: si alguien añade un fichero nuevo sin borrar el viejo, el
    orden decide cuál se usa y más vale que sea el de siempre. Usa ``stat`` en lugar
    de ``Path.is_file`` a propósito: ``is_file`` devuelve False (sin avisar) cuando
    no hay permisos, lo que oculta el caso típico de Docker en Render (usuario que
    no pertenece al grupo 1000).
    """
    candidates = [SECRETS_DIR / "cookies.txt"]
    with contextlib.suppress(OSError):
        candidates.extend(
            p for p in sorted(SECRETS_DIR.glob("*cookie*")) if p.name != "cookies.txt"
        )

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


def _looks_like_cookie_jar(path: Path) -> bool:
    """¿El fichero es un ``cookies.txt`` en formato Netscape? (por contenido)

    Se mira el contenido y no el nombre a propósito: un tarro de Reddit se llamará
    ``reddit.txt`` y no tiene por qué llevar «cookie» en el nombre.
    """
    try:
        texto = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return any(_cookie_key(line) is not None for line in texto.splitlines())


def _extra_cookie_files(primary: str) -> list[str]:
    """Otros tarros de cookies del directorio de secretos.

    Render admite varios Secret Files, así que lo natural es tener uno por
    plataforma (``cookies.txt`` para YouTube, ``reddit.txt`` para Reddit…). Se
    unen al principal sin pisarlo (ver ``_merge_cookie_jars``).
    """
    extras: list[str] = []
    if not SECRETS_DIR.is_dir():
        return extras
    with contextlib.suppress(OSError):
        for candidate in sorted(SECRETS_DIR.iterdir()):
            if str(candidate) == primary or not candidate.is_file():
                continue
            if _looks_like_cookie_jar(candidate):
                extras.append(str(candidate))
    return extras


def cookie_file_names() -> str:
    """Nombres de los ficheros de cookies en uso (nunca rutas), para diagnóstico."""
    names = [Path(cookies.origin).name] if cookies.origin else []
    names.extend(Path(extra).name for extra in cookies.extras)
    return ", ".join(names)


# Nombres que suelen delatar una cookie de sesión fuera de YouTube
# (``reddit_session``, ``sessionid``, ``auth_token``…). Solo orientan el mensaje
# de error; no deciden si la cookie se envía o no.
_SESSION_HINTS = ("session", "sid", "auth", "token", "login")


def cookie_status(url: str) -> tuple[int, bool]:
    """Cookies de esa web en la copia de trabajo y si alguna parece de sesión.

    Distingue los tres fallos de autenticación que se confunden entre sí: no
    tener cookies de esa web, tenerlas exportadas sin sesión (se navega como
    anónimo) o tenerlas con sesión y que aun así las rechace (IP de servidor).
    Solo se miran dominios y nombres: nunca los valores.
    """
    if not cookies.file:
        return 0, False
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return 0, False
    try:
        raw = Path(cookies.file).read_text(encoding="utf-8")
    except OSError:
        return 0, False

    total = 0
    sesion = False
    for line in raw.splitlines():
        key = _cookie_key(line)
        if key is None:
            continue
        dominio, _, nombre = key
        dominio = dominio.lstrip(".").lower()
        if not dominio or not (host == dominio or host.endswith("." + dominio)):
            continue
        total += 1
        if nombre == "reddit_session" or any(p in nombre.lower() for p in _SESSION_HINTS):
            sesion = True
    return total, sesion


def _read_cookie_files(path: str, extras: list[str]) -> tuple[str, list[str]] | None:
    """Lee el tarro principal y los extras ya unidos.

    Devuelve ``(contenido, extras leídos)`` o ``None`` si el principal no se pudo
    leer. Un extra ilegible solo se avisa: se pierde ese sitio, no la descarga.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("No se pudieron leer las cookies de %s: %s", path, exc)
        return None

    leidos: list[str] = []
    textos: list[str] = []
    for extra in extras:
        try:
            textos.append(Path(extra).read_text(encoding="utf-8"))
        except OSError as exc:
            logger.warning("No se pudo leer el fichero de cookies %s: %s", extra, exc)
        else:
            leidos.append(extra)

    return _merge_cookie_jars(raw, textos), leidos


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


def _writable_copy(path: str, extras: list[str] | None = None) -> str | None:
    """Copia las cookies a un fichero privado con permiso de escritura.

    yt-dlp **reescribe** el ``cookiefile`` al terminar cada descarga. Los Secret
    Files de Render se montan en solo lectura, así que sin esta copia la descarga
    se completa, se queda sin reescribir el fichero y revienta al cerrar con un
    ``PermissionError`` que además tapa el error real. Devolver ``None`` indica
    que no se pudo leer el original.

    ``extras`` son otros tarros (un Secret File por plataforma) que se unen al
    principal en la misma copia de trabajo.
    """
    leido = _read_cookie_files(path, extras or [])
    if leido is None:
        return None
    raw, leidos = leido

    if not raw.strip():
        logger.warning("El fichero de cookies %s está vacío", path)
    else:
        _check_session(raw, path)
    if leidos:
        logger.info(
            "Cookies: %s junto con %s (cada web recibe solo las suyas)",
            Path(path).name,
            ", ".join(Path(extra).name for extra in leidos),
        )
    return _write_private_cookies(raw)


def refresh_cookies() -> bool:
    """Vuelve a dejar la copia de trabajo igual al origen. Devuelve si lo hizo.

    yt-dlp **reescribe** el ``cookiefile`` al cerrar cada extracción, y cuando
    YouTube rota la sesión guarda el tarro ya sin ella. Sin rehacer la copia, la
    primera petición tras el arranque usaría tus cookies y todas las siguientes
    irían sin sesión (y sin querer: yt-dlp solo avisa cuando nota que las pierde
    por el camino). Por eso se refresca antes de cada extracción.
    """
    if not cookies.file:
        return False

    with _cookies_lock:
        if cookies.origin:
            leido = _read_cookie_files(cookies.origin, cookies.extras)
            if leido is None:
                return False
            raw, _ = leido
        elif cookies.raw is not None:
            raw = cookies.raw
        else:
            return False

        cookies.file = _write_private_cookies(raw)

    # Cada extracción parte de la copia original: el aviso de «cookies rotadas»
    # que se recuerde a partir de aquí habla de esta extracción.
    from . import errors

    errors.olvidar_cookies_rotadas()
    return True


def setup_cookies() -> None:
    """Localiza el cookies.txt opcional, en este orden:

    1. Ruta indicada en YTDLP_COOKIES_FILE.
    2. Un Secret File montado en /etc/secrets (cookies.txt).
    3. El contenido en YTDLP_COOKIES (texto) o YTDLP_COOKIES_B64 (Base64).

    En los dos primeros casos se trabaja sobre una copia escribible (ver
    ``_writable_copy``): yt-dlp reescribe el fichero al cerrar y el original
    puede ser de solo lectura.

    Es totalmente opcional: sin cookies la app funciona igual.
    """
    cookies.file = None
    cookies.error = ""
    cookies.source = ""
    cookies.session = False
    cookies.count = 0
    cookies.origin = None
    cookies.raw = None
    cookies.extras = []

    # Al (re)cargar las cookies se olvida el aviso de «cookies rotadas»: el
    # fichero puede ser nuevo.
    from . import errors

    errors.olvidar_cookies_rotadas()

    # 1) Ruta personalizada
    path = env_str("YTDLP_COOKIES_FILE")
    if path and Path(path).is_file():
        copia = _writable_copy(path)
        if copia is None:
            cookies.error = f"no se pudo leer {path} (¿permisos de lectura?)"
            return
        cookies.file, cookies.source = copia, "YTDLP_COOKIES_FILE"
        cookies.origin = path
        logger.info("Cookies cargadas desde YTDLP_COOKIES_FILE (%s)", path)
        return

    # 2) Secret File (Render: /etc/secrets/cookies.txt)
    found = _find_secret_file()
    if found:
        extras = _extra_cookie_files(found)
        copia = _writable_copy(found, extras)
        if copia is None:
            cookies.error = f"no se pudo leer el Secret File {found} (¿permisos?)"
            return
        cookies.file, cookies.source = copia, "secret-file"
        cookies.origin = found
        cookies.extras = extras
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
        cookies.raw = raw
        _check_session(raw, source)
        logger.info("Cookies cargadas desde %s", source)
    except OSError as exc:
        cookies.file = None
        cookies.error = f"no se pudo escribir: {exc}"
        logger.warning("Cookies: %s", cookies.error)
