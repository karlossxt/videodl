"""Envoltorios de ffmpeg/ffprobe y construcción de opciones de yt-dlp."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from .config import (
    FFMPEG_AVAILABLE,
    FFMPEG_TIMEOUT_SECONDS,
    FFPROBE,
    FFPROBE_AVAILABLE,
    YTDLP_EXTRACTOR_ARGS,
    YTDLP_PROXY,
    YTDLP_SOCKET_TIMEOUT,
    cookies,
)
from .jobs import JobStore
from .pot import configure_pot_provider

logger = logging.getLogger("videodl.media")

# Se ajusta el proveedor de PO tokens antes de cualquier extracción (si está
# instalado; si no, no hace nada). Sin él YouTube contesta con su comprobación
# anti-bot desde una IP de nube, por muchas cookies que se manden.
configure_pot_provider()

# Sufijos de archivos incompletos que nunca deben servirse como resultado final.
_TEMP_SUFFIXES = {".part", ".ytdl", ".temp", ".tmp"}

ProgressHook = Callable[[dict], None]


class Cancelled(Exception):
    """Se lanza cuando el usuario cancela un proceso en curso."""


# ---------------------------------------------------------------------------
# yt-dlp
# ---------------------------------------------------------------------------


def format_selector(mode: str) -> str:
    """Construye la cadena de formato de yt-dlp para el modo elegido."""
    if mode == "audio":
        return "bestaudio/best"
    if mode == "best":
        return (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            if FFMPEG_AVAILABLE
            else "best[ext=mp4]/best"
        )
    height = mode.split("-", 1)[1]
    if FFMPEG_AVAILABLE:
        return (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]"
            f"/bestvideo[height<={height}]+bestaudio"
            f"/best[height<={height}][ext=mp4]/best[height<={height}]"
            f"/best"
        )
    return f"best[height<={height}][ext=mp4]/best[height<={height}]/best"


class _YtdlpLogger:
    """Reenvía los mensajes de yt-dlp al registro de la app.

    yt-dlp se ejecuta en modo silencioso y así se perdían avisos que explican los
    fallos: clientes descartados por no admitir cookies, proveedores de PO tokens
    rechazados, «esto es un experimento»… Los avisos y los errores salen con su
    nivel (visibles con ``LOG_LEVEL=INFO``) y el resto a ``DEBUG`` para poder
    seguir una extracción entera con ``LOG_LEVEL=DEBUG``.
    """

    _log = logging.getLogger("videodl.ytdlp")

    def debug(self, message: str) -> None:
        self._log.debug("%s", message)

    def info(self, message: str) -> None:
        self._log.info("%s", message)

    def warning(self, message: str) -> None:
        self._log.warning("%s", message)

    def error(self, message: str) -> None:
        self._log.error("%s", message)


def connection_opts() -> dict:
    """Ajustes de conexión válidos para cualquier llamada a yt-dlp.

    Cookies, proxy y cliente de extracción: cuando la plataforma bloquea la IP
    del servidor (YouTube en la nube), sin esto ni el análisis ni la descarga
    funcionan. El ``cookiefile`` apunta siempre a una copia escribible porque
    yt-dlp reescribe el fichero al cerrar. También se le pasa un ``logger``: sin
    él, yt-dlp se traga sus propios avisos y depurar un bloqueo es a ciegas.
    """
    opts: dict = {"logger": _YtdlpLogger()}
    if YTDLP_SOCKET_TIMEOUT > 0:
        opts["socket_timeout"] = YTDLP_SOCKET_TIMEOUT
    if YTDLP_PROXY:
        opts["proxy"] = YTDLP_PROXY
    if YTDLP_EXTRACTOR_ARGS:
        opts["extractor_args"] = YTDLP_EXTRACTOR_ARGS
    if cookies.file:
        opts["cookiefile"] = cookies.file
    return opts


def info_opts() -> dict:
    """Opciones para analizar una URL (o bajar subtítulos) sin descargar vídeo.

    Incluye las cookies: el análisis pasa por la misma puerta que la descarga, así
    que si el vídeo exige sesión también hay que mandarlas al leerlo.
    """
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        **connection_opts(),
    }


def build_opts(
    mode: str,
    tmpdir: Path,
    progress_hook: ProgressHook | None = None,
    start: float | None = None,
    end: float | None = None,
    force_keyframes: bool = True,
) -> dict:
    """Opciones de yt-dlp comunes a la descarga directa y a los trabajos."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": str(tmpdir / "media.%(ext)s"),
        "format": format_selector(mode),
        "merge_output_format": None if mode == "audio" else "mp4",
        "noprogress": True,
        "restrictfilenames": False,
        "retries": 3,
        # Solo audio -> convertir a mp3 si hay ffmpeg
        "postprocessors": (
            [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
            if mode == "audio" and FFMPEG_AVAILABLE
            else []
        ),
    }

    # Cookies, proxy y cliente de extracción: ver connection_opts().
    opts.update(connection_opts())

    # Recorte de un fragmento (requiere ffmpeg para cortar con precisión)
    if FFMPEG_AVAILABLE and (start is not None or end is not None):
        opts["download_ranges"] = lambda info_dict, ydl: [
            {"start_time": start or 0, "end_time": end}
        ]
        # force_keyframes_at_cuts recodifica el fragmento al vuelo para que el corte
        # caiga exactamente en el segundo pedido. Es muy caro en servidores con poca
        # CPU, así que los clips lo desactivan (cortan después, con ffmpeg).
        opts["force_keyframes_at_cuts"] = bool(force_keyframes)

    if progress_hook is not None:
        opts["progress_hooks"] = [progress_hook]
    return opts


def resolve_output(tmpdir: Path, filename: str) -> Path | None:
    """Devuelve el archivo final generado (el post-procesado puede cambiar la extensión).

    Ignora archivos temporales/incompletos (``.part``, ``.ytdl``…) que yt-dlp deja
    cuando una descarga falla, para no servir un archivo a medias como si fuera el
    resultado final.
    """
    path = Path(filename)
    if path.exists() and _is_final_file(path):
        return path
    candidates = [p for p in tmpdir.iterdir() if p.is_file() and _is_final_file(p)]
    if not candidates:
        return None
    # El archivo más grande suele ser el resultado fusionado (vídeo + audio).
    return max(candidates, key=lambda p: p.stat().st_size)


def _is_final_file(path: Path) -> bool:
    try:
        return (
            path.suffix.lower() not in _TEMP_SUFFIXES
            and not path.name.startswith(".")
            and path.stat().st_size > 0
        )
    except OSError:
        return False


# ---------------------------------------------------------------------------
# ffprobe
# ---------------------------------------------------------------------------


def ffprobe_meta(path: Path) -> dict:
    """Lee duración y resolución reales del archivo con ffprobe."""
    cmd = [
        FFPROBE, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=180, check=True).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("ffprobe falló para %s: %s", path, exc)
        raise RuntimeError("No se pudo analizar el vídeo (ffprobe falló).") from exc

    data = json.loads(raw.decode("utf-8", "replace"))

    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)

    duration = 0.0
    try:
        duration = float(data.get("format", {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0 and video is not None:
        try:
            duration = float(video.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0.0

    width = int(video.get("width") or 0) if video else 0
    height = int(video.get("height") or 0) if video else 0

    # Los vídeos grabados con el móvil suelen llevar la rotación en los
    # metadatos: la resolución "visible" es la rotada.
    rotation = 0
    if video:
        for side_data in video.get("side_data_list") or []:
            if "rotation" in side_data:
                try:
                    rotation = int(side_data["rotation"])
                except (TypeError, ValueError):
                    rotation = 0
    if abs(rotation) % 180 == 90:
        width, height = height, width

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "has_video": video is not None,
        "has_audio": audio is not None,
    }


def probe_safe(path) -> dict:
    """Igual que ``ffprobe_meta`` pero sin lanzar: un archivo roto no tumba el trabajo."""
    if path is None:
        return {}
    try:
        return ffprobe_meta(Path(path))
    except Exception:  # noqa: BLE001 - es deliberadamente tolerante
        return {}


def first_video_pts(path: Path) -> float | None:
    """Instante (en segundos) del primer fotograma de vídeo del archivo.

    Cuando yt-dlp descarga solo un fragmento con ffmpeg, la línea de tiempo
    resultante queda desplazada: el segundo pedido acaba en 0 y el trozo que
    arrastra desde el fotograma clave anterior tiene marcas negativas. Saber
    cuánto se desplazó permite luego recortar con exactitud.
    """
    if not FFPROBE_AVAILABLE:
        return None
    cmd = [
        FFPROBE, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "packet=pts_time", "-of", "csv=p=0",
        "-read_intervals", "%+#1", str(path),
    ]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in raw.decode("utf-8", "replace").splitlines():
        line = line.strip().rstrip(",")
        if not line:
            continue
        try:
            return float(line)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# ffmpeg
# ---------------------------------------------------------------------------


def run_ffmpeg(
    args: list,
    store: JobStore,
    job_id: str,
    duration: float,
    pct_from: float,
    pct_to: float,
) -> int:
    """Ejecuta ffmpeg informando del progreso real. Devuelve el código de salida.

    ``store``/``job_id`` indican de qué almacén leer el estado de cancelación.
    """
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    # Perro guardián: si ffmpeg no termina en el tiempo máximo, se mata. Evita que
    # una codificación colgada retenga un hilo (y su carpeta temporal) para siempre.
    killer: threading.Timer | None = None
    if FFMPEG_TIMEOUT_SECONDS > 0:
        killer = threading.Timer(FFMPEG_TIMEOUT_SECONDS, proc.kill)
        killer.daemon = True
        killer.start()

    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            job = store.get(job_id)
            if job and job.get("cancel"):
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise Cancelled()

            line = raw.strip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            if key in ("out_time_ms", "out_time_us"):
                # ffmpeg llama "ms" a lo que en realidad son microsegundos.
                try:
                    micros = int(value)
                except ValueError:
                    continue
                if micros < 0 or duration <= 0:
                    continue
                done = min(micros / 1_000_000, duration)
                pct = pct_from + (done / duration) * (pct_to - pct_from)
                store.update(job_id, percent=round(min(pct, pct_to), 1))
    finally:
        if killer is not None:
            killer.cancel()
        if proc.stdout is not None:
            proc.stdout.close()
    return proc.wait()
