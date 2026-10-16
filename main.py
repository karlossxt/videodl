"""VideoDL - Descarga videos de casi cualquier plataforma.

Backend FastAPI + yt-dlp.

Endpoints:
  POST /api/info            -> analiza una URL y devuelve metadatos, calidades y subtítulos
  POST /api/download        -> descarga y devuelve el archivo directamente (bloqueante)
  POST /api/jobs            -> inicia una descarga en segundo plano y devuelve su id
  GET  /api/jobs/{id}       -> progreso en vivo del trabajo (%, velocidad, ETA)
  GET  /api/jobs/{id}/file  -> descarga el archivo del trabajo terminado
  POST /api/jobs/{id}/cancel-> cancela un trabajo en curso
  POST /api/subtitles       -> devuelve los subtítulos en .srt o .vtt
  GET  /api/thumbnail       -> devuelve la miniatura como archivo
  POST /api/compress        -> sube un vídeo y lo comprime a un tamaño objetivo
  GET  /api/compress/{id}   -> progreso de la compresión
  GET  /api/compress/{id}/file -> descarga el vídeo ya comprimido
  POST /api/clips           -> recorta un fragmento y lo convierte en clip vertical
  POST /api/clips/upload    -> crea un clip vertical a partir de un archivo subido
  GET  /api/clips/{id}      -> progreso del clip
  GET  /api/clips/{id}/file -> descarga el clip terminado
  GET  /api/health          -> estado del servicio

Páginas:
  /                         -> descargador universal de vídeo/audio
  /comprimir-video-whatsapp -> compresor de vídeo para WhatsApp / Discord / Telegram
  /recortar-clip-vertical   -> recortador de clips verticales (TikTok / Reels / Shorts)
  /herramientas             -> directorio de herramientas

Tanto /api/download como /api/jobs aceptan "start" y "end" (segundos) para
descargar solo un fragmento del video; el corte se hace con ffmpeg.
"""

import asyncio
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Optional
from urllib.request import Request as URLRequest
from urllib.request import urlopen

from contextlib import asynccontextmanager

import yt_dlp
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------


class InfoRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    mode: str = "best"  # "best" | "audio" | "video-<height>"
    title: Optional[str] = None  # solo para nombrar el archivo
    start: Optional[float] = Field(default=None, ge=0)  # recorte: segundo inicial
    end: Optional[float] = Field(default=None, gt=0)  # recorte: segundo final


class SubtitleRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    lang: str = Field(..., min_length=2, max_length=20)
    format: str = "srt"  # "srt" | "vtt"
    title: Optional[str] = None


class JobRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    mode: str = "best"
    title: Optional[str] = None
    start: Optional[float] = Field(default=None, ge=0)
    end: Optional[float] = Field(default=None, gt=0)


class ClipRequest(BaseModel):
    """Fragmento de un vídeo en línea para convertirlo en clip vertical."""

    url: str = Field(..., min_length=8, max_length=2048)
    start: float = Field(default=0, ge=0)
    end: float = Field(..., gt=0)
    aspect: str = "vertical"  # vertical | vertical-blur | square | original
    quality: str = "media"  # alta | media | baja
    title: Optional[str] = None


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None
FFPROBE_AVAILABLE = shutil.which("ffprobe") is not None
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
# Preset de x264: en servidores gratuitos (CPU muy limitada) conviene "veryfast".
# Se puede ajustar sin tocar código con la variable X264_PRESET.
X264_PRESET = os.environ.get("X264_PRESET", "veryfast")

# Archivo de cookies opcional (algunas plataformas piden iniciar sesión desde
# servidores). Se rellena desde la variable de entorno YTDLP_COOKIES(_B64).
COOKIES_FILE: Optional[str] = None
COOKIES_ERROR: str = ""
COOKIES_SOURCE: str = ""

# Render y otras plataformas montan aquí los "Secret Files".
SECRETS_DIR = Path("/etc/secrets")


def _buscar_secret_file() -> Optional[str]:
    """Devuelve un cookies.txt subido como Secret File (/etc/secrets/...), si existe."""
    candidatos = []
    try:
        candidatos.extend(sorted(SECRETS_DIR.glob("*cookie*")))
    except OSError:
        pass
    candidatos.append(SECRETS_DIR / "cookies.txt")
    for cand in candidatos:
        try:
            if cand.is_file() and cand.stat().st_size > 0:
                return str(cand)
        except OSError:
            continue
    return None


def _setup_cookies() -> None:
    """Localiza el cookies.txt opcional, en este orden:

    1. Ruta indicada en YTDLP_COOKIES_FILE.
    2. Un Secret File montado en /etc/secrets (cookies.txt).
    3. El contenido en YTDLP_COOKIES (texto) o YTDLP_COOKIES_B64 (Base64).

    Es totalmente opcional: sin cookies la app funciona igual.
    """
    global COOKIES_FILE, COOKIES_ERROR, COOKIES_SOURCE

    # 1) Ruta personalizada
    ruta = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if ruta and Path(ruta).is_file():
        COOKIES_FILE, COOKIES_ERROR, COOKIES_SOURCE = ruta, "", "YTDLP_COOKIES_FILE"
        return

    # 2) Secret File (Render: /etc/secrets/cookies.txt)
    encontrado = _buscar_secret_file()
    if encontrado:
        COOKIES_FILE, COOKIES_ERROR, COOKIES_SOURCE = encontrado, "", "secret-file"
        return

    # 3) Contenido en variable de entorno
    raw = os.environ.get("YTDLP_COOKIES", "").strip()
    fuente = "YTDLP_COOKIES"
    if not raw:
        b64 = os.environ.get("YTDLP_COOKIES_B64", "").strip()
        fuente = "YTDLP_COOKIES_B64"
        if b64:
            import base64

            try:
                raw = base64.b64decode(b64).decode("utf-8", "replace").strip()
            except Exception as exc:  # noqa: BLE001
                COOKIES_ERROR = (
                    f"base64 invalido ({len(b64)} caracteres recibidos): {exc}"
                )
                raw = ""

    if not raw:
        COOKIES_ERROR = COOKIES_ERROR or f"sin datos ({fuente} vacia o no definida)"
        return

    # El formato Netscape de cookies.txt usa tabuladores como separador.
    if "\t" not in raw:
        COOKIES_ERROR = (
            f"{fuente} no parece un cookies.txt valido "
            f"(formato Netscape, {len(raw)} caracteres)"
        )
        return

    try:
        path = Path(tempfile.gettempdir()) / "videodl_cookies.txt"
        path.write_text(raw, encoding="utf-8")
        COOKIES_FILE, COOKIES_ERROR, COOKIES_SOURCE = str(path), "", fuente
    except OSError as exc:
        COOKIES_FILE = None
        COOKIES_ERROR = f"no se pudo escribir: {exc}"


def _validate_url(url: str) -> None:
    if not _URL_RE.match(url.strip()):
        raise HTTPException(status_code=400, detail="La URL debe empezar por http:// o https://")


def _sanitize_filename(name: str) -> str:
    """Quita caracteres prohibidos en nombres de archivo (Windows)."""
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:150] or "video"


def _human_size(n: Optional[int]) -> Optional[str]:
    if not n:
        return None
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _validate_mode(mode: str) -> str:
    if mode in ("best", "audio") or re.fullmatch(r"video-\d{2,4}", mode or ""):
        return mode
    raise HTTPException(status_code=400, detail="Modo de descarga inválido")


def _validate_range(start: Optional[float], end: Optional[float]) -> None:
    """Comprueba que el fragmento solicitado tenga sentido."""
    if start is not None or end is not None:
        if not FFMPEG_AVAILABLE:
            raise HTTPException(
                status_code=400,
                detail="Para recortar fragmentos hace falta ffmpeg instalado en el servidor.",
            )
    if start is not None and end is not None and end <= start:
        raise HTTPException(
            status_code=400,
            detail="El fin del fragmento debe ser mayor que el inicio.",
        )


def _format_selector(mode: str) -> str:
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


def _rmtree_robust(path) -> None:
    """Borra un directorio con reintentos: en Windows los archivos pueden seguir bloqueados."""
    p = Path(path)
    for attempt in range(5):
        shutil.rmtree(p, ignore_errors=True)
        if not p.exists():
            return
        time.sleep(0.2 * (attempt + 1))
    shutil.rmtree(p, ignore_errors=True)


def _sweep_temp_dirs() -> None:
    """Elimina carpetas temporales de ejecuciones anteriores (residuos huérfanos)."""
    tmp_root = Path(tempfile.gettempdir())
    for pattern in ("videodl_*",):
        for folder in tmp_root.glob(pattern):
            try:
                if folder.is_dir():
                    age = time.time() - folder.stat().st_mtime
                    if age > 300:  # más de 5 minutos -> no pertenece a trabajos activos
                        _rmtree_robust(folder)
            except OSError:
                continue


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Limpia restos de ejecuciones anteriores y arranca el hilo de limpieza."""
    _setup_cookies()
    await asyncio.to_thread(_sweep_temp_dirs)
    threading.Thread(target=_janitor_loop, daemon=True).start()
    yield


app = FastAPI(title="VideoDL", lifespan=_lifespan)


def _build_opts(
    mode: str,
    tmpdir: Path,
    progress_hook=None,
    start: Optional[float] = None,
    end: Optional[float] = None,
) -> dict:
    """Opciones de yt-dlp comunes a la descarga directa y a los trabajos."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": str(tmpdir / "media.%(ext)s"),
        "format": _format_selector(mode),
        "merge_output_format": None if mode == "audio" else "mp4",
        "noprogress": True,
        "restrictfilenames": False,
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

    # Recorte de un fragmento (requiere ffmpeg para cortar con precisión)
    if FFMPEG_AVAILABLE and (start is not None or end is not None):
        opts["download_ranges"] = lambda info_dict, ydl: [
            {"start_time": start or 0, "end_time": end}
        ]
        opts["force_keyframes_at_cuts"] = True

    if progress_hook is not None:
        opts["progress_hooks"] = [progress_hook]
    if COOKIES_FILE:
        opts["cookiefile"] = COOKIES_FILE
    return opts


def _resolve_output(tmpdir: Path, filename: str):
    """Devuelve el archivo final generado (el post-procesado puede cambiar la extensión)."""
    path = Path(filename)
    if path.exists():
        return path
    files = [p for p in tmpdir.iterdir() if p.is_file()]
    return files[0] if files else None


def _time_tag(seconds: Optional[float]) -> str:
    """Convierte segundos a una etiqueta corta para el nombre del archivo (ej: 1m05s)."""
    if seconds is None:
        return ""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def _final_name(
    mode: str,
    title: Optional[str],
    info: dict,
    path: Path,
    start: Optional[float] = None,
    end: Optional[float] = None,
) -> str:
    base = _sanitize_filename(title or info.get("title") or "video")
    if start is not None or end is not None:
        base = f"{base} (corte {_time_tag(start or 0)}-{_time_tag(end) or 'fin'})"
    ext = "mp3" if mode == "audio" and FFMPEG_AVAILABLE else (path.suffix.lstrip(".") or "mp4")
    return f"{base}.{ext}"


# Idiomas habituales, se muestran primero en la lista de subtítulos
_COMMON_LANGS = ["es", "en", "pt", "fr", "de", "it", "ja", "ko", "zh", "ru", "ar", "hi"]

_LANG_NAMES = {
    "es": "Español", "en": "Inglés", "pt": "Portugués", "fr": "Francés",
    "de": "Alemán", "it": "Italiano", "ja": "Japonés", "ko": "Coreano",
    "zh": "Chino", "zh-Hans": "Chino simplificado", "zh-Hant": "Chino tradicional",
    "ru": "Ruso", "ar": "Árabe", "hi": "Hindi", "nl": "Neerlandés",
    "pl": "Polaco", "tr": "Turco", "sv": "Sueco", "id": "Indonesio",
    "uk": "Ucraniano", "vi": "Vietnamita", "th": "Tailandés", "ca": "Catalán",
}


def _sub_label(tracks: list, lang: str) -> str:
    for t in tracks or []:
        name = t.get("name")
        if name and name.lower() not in (lang.lower(), "unknown"):
            return name
    return _LANG_NAMES.get(lang, lang.upper())


def _collect_subtitles(info: dict) -> list:
    """Combina subtítulos manuales y automáticos, priorizando idiomas comunes."""
    manual = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}

    result = []
    manual_bases = set()
    for lang, tracks in manual.items():
        result.append({"lang": lang, "label": _sub_label(tracks, lang), "auto": False})
        manual_bases.add(lang.split("-")[0].lower())

    auto_langs = [l for l in _COMMON_LANGS if l in auto]
    auto_langs += [l for l in auto if l not in _COMMON_LANGS]
    for lang in auto_langs:
        # Omitir el automático si ya existe uno manual del mismo idioma
        if lang.split("-")[0].lower() in manual_bases:
            continue
        result.append({"lang": lang, "label": _sub_label(auto[lang], lang), "auto": True})

    return result[:14]


# ---------------------------------------------------------------------------
# Endpoints de la API
# ---------------------------------------------------------------------------


@app.post("/api/info")
async def video_info(req: InfoRequest):
    """Analiza la URL sin descargar y devuelve los metadatos y calidades."""
    _validate_url(req.url)

    def _extract():
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(req.url.strip(), download=False)

    try:
        info = await asyncio.to_thread(_extract)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=422, detail=_clean_ytdlp_error(str(e)))

    # Si es una playlist, tomar solo el primer video
    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]

    # Recolectar calidades de video únicas por altura
    qualities: dict[int, dict] = {}
    audio_only = False
    for f in info.get("formats", []) or []:
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        height = f.get("height")
        if vcodec != "none" and height:
            entry = qualities.get(height)
            size = _human_size(f.get("filesize") or f.get("filesize_approx"))
            if entry is None or (size and not entry.get("size")):
                qualities[height] = {
                    "height": height,
                    "label": f"{height}p" + (f" {f.get('fps')}fps" if (f.get("fps") or 0) >= 50 else ""),
                    "ext": f.get("ext"),
                    "size": size,
                }
        if acodec != "none":
            audio_only = True

    ordered = sorted(qualities.values(), key=lambda q: q["height"], reverse=True)

    return {
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel") or info.get("creator"),
        "duration": info.get("duration"),
        "duration_string": info.get("duration_string"),
        "thumbnail": info.get("thumbnail"),
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "view_count": info.get("view_count"),
        "qualities": ordered,
        "audio_available": audio_only,
        "subtitles": _collect_subtitles(info),
        "ffmpeg_available": FFMPEG_AVAILABLE,
    }


@app.post("/api/download")
async def download(req: DownloadRequest):
    """Descarga el video (o solo audio) y lo sirve como archivo (bloqueante)."""
    _validate_url(req.url)
    mode = _validate_mode(req.mode)
    _validate_range(req.start, req.end)

    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_"))
    opts = _build_opts(mode, tmpdir, start=req.start, end=req.end)

    def _download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(req.url.strip(), download=True)
            return info, ydl.prepare_filename(info)

    try:
        info, filename = await asyncio.to_thread(_download)
    except yt_dlp.utils.DownloadError as e:
        _rmtree_robust(tmpdir)
        raise HTTPException(status_code=422, detail=_clean_ytdlp_error(str(e)))

    path = _resolve_output(tmpdir, filename)
    if path is None:
        _rmtree_robust(tmpdir)
        raise HTTPException(status_code=500, detail="No se generó ningún archivo")

    from starlette.background import BackgroundTask

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=_final_name(mode, req.title, info, path, req.start, req.end),
        background=BackgroundTask(lambda: _rmtree_robust(tmpdir)),
    )


# ---------------------------------------------------------------------------
# Trabajos de descarga en segundo plano (con progreso en vivo)
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_JOB_TTL_SECONDS = 3600  # los trabajos terminados se limpian tras 1 hora


def _job_new(url: str, mode: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "percent": 0.0,
            "downloaded": 0,
            "total": 0,
            "speed": None,
            "eta": None,
            "error": None,
            "filename": None,
            "path": None,
            "tmpdir": None,
            "cancel": False,
            "phase": None,
            "created": time.time(),
        }
    return job_id


def _job_update(job_id: str, **fields) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(fields)


def _job_get(job_id: str) -> Optional[dict]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def _jobs_cleanup_stale() -> None:
    """Elimina trabajos antiguos para no acumular basura en memoria y disco."""
    now = time.time()
    with _jobs_lock:
        stale = [jid for jid, j in _jobs.items() if now - j["created"] > _JOB_TTL_SECONDS]
    for jid in stale:
        _job_delete(jid)


def _janitor_loop() -> None:
    """Hilo de limpieza: cada 10 minutos libera trabajos vencidos y residuos."""
    while True:
        time.sleep(600)
        try:
            _jobs_cleanup_stale()
            _cjobs_cleanup_stale()
            _clips_cleanup_stale()
        except Exception:
            pass


def _job_delete(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs.pop(job_id, None)
    if job and job.get("tmpdir"):
        _rmtree_robust(job["tmpdir"])


def _make_progress_hook(job_id: str):
    """Hook de yt-dlp que actualiza el estado del trabajo y atiende la cancelación."""

    def hook(d: dict) -> None:
        job = _job_get(job_id)
        if job and job["cancel"]:
            raise yt_dlp.utils.DownloadCancelled("Cancelado por el usuario")

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            percent = (downloaded / total * 100) if total else 0.0
            # En calidades altas se descargan dos archivos por separado (video y audio)
            name = (d.get("filename") or "").lower()
            phase = "audio" if name.endswith((".m4a", ".mp3", ".opus", ".ogg", ".aac")) else "video"
            _job_update(
                job_id,
                status="downloading",
                percent=round(min(percent, 100.0), 1),
                downloaded=downloaded,
                total=total,
                speed=d.get("speed"),
                eta=d.get("eta"),
                phase=phase,
            )
        elif status == "finished":
            # El archivo actual terminó; puede quedar el post-procesado (unir audio)
            _job_update(job_id, status="processing", percent=100.0, speed=None, eta=0)

    return hook


def _run_job(
    job_id: str,
    url: str,
    mode: str,
    title: Optional[str],
    start: Optional[float] = None,
    end: Optional[float] = None,
) -> None:
    """Se ejecuta en un hilo aparte: descarga y deja el archivo listo."""
    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_job_"))
    _job_update(job_id, tmpdir=str(tmpdir))

    opts = _build_opts(mode, tmpdir, progress_hook=_make_progress_hook(job_id), start=start, end=end)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        path = _resolve_output(tmpdir, filename)
        if path is None:
            raise RuntimeError("No se generó ningún archivo")

        _job_update(
            job_id,
            status="finished",
            percent=100.0,
            speed=None,
            eta=0,
            path=str(path),
            filename=_final_name(mode, title, info, path, start, end),
            downloaded=path.stat().st_size,
        )
    except yt_dlp.utils.DownloadCancelled:
        _rmtree_robust(tmpdir)
        _job_update(job_id, status="cancelled", error="Descarga cancelada", tmpdir=None)
    except yt_dlp.utils.DownloadError as e:
        _rmtree_robust(tmpdir)
        _job_update(job_id, status="error", error=_clean_ytdlp_error(str(e)), tmpdir=None)
    except Exception:
        _rmtree_robust(tmpdir)
        _job_update(job_id, status="error", error="Error inesperado durante la descarga", tmpdir=None)


@app.post("/api/jobs")
async def create_job(req: JobRequest):
    """Inicia una descarga en segundo plano y devuelve su identificador."""
    _validate_url(req.url)
    mode = _validate_mode(req.mode)
    _validate_range(req.start, req.end)

    _jobs_cleanup_stale()
    job_id = _job_new(req.url.strip(), mode)

    threading.Thread(
        target=_run_job,
        args=(job_id, req.url.strip(), mode, req.title, req.start, req.end),
        daemon=True,
    ).start()

    return {"id": job_id}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    """Estado y progreso de un trabajo."""
    job = _job_get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return {
        k: job[k]
        for k in ("id", "status", "percent", "downloaded", "total", "speed", "eta", "error", "filename", "phase")
    }


@app.get("/api/jobs/{job_id}/file")
async def job_file(job_id: str):
    """Devuelve el archivo de un trabajo terminado y libera sus recursos."""
    job = _job_get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if job["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="La descarga fue cancelada")
    if job["status"] != "finished" or not job.get("path"):
        raise HTTPException(status_code=409, detail="La descarga todavía no ha terminado")

    path = Path(job["path"])
    if not path.exists():
        _job_delete(job_id)
        raise HTTPException(status_code=410, detail="El archivo ya no está disponible")

    from starlette.background import BackgroundTask

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=job["filename"] or "video.mp4",
        background=BackgroundTask(lambda: _job_delete(job_id)),
    )


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Solicita cancelar un trabajo en curso."""
    job = _job_get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if job["status"] in ("finished", "error", "cancelled"):
        return {"ok": False, "status": job["status"]}
    _job_update(job_id, cancel=True)
    return {"ok": True, "status": "cancelling"}


@app.get("/api/health")
@app.get("/health")
async def health():
    """Comprobación de estado del servicio (alias /health para plataformas)."""
    cookies_lines = 0
    if COOKIES_FILE:
        try:
            with open(COOKIES_FILE, "r", encoding="utf-8", errors="replace") as fh:
                cookies_lines = sum(
                    1 for ln in fh if ln.strip() and not ln.lstrip().startswith("#")
                )
        except OSError:
            cookies_lines = -1
    return {
        "status": "ok",
        "ffmpeg": FFMPEG_AVAILABLE,
        "ffprobe": FFPROBE_AVAILABLE,
        "compressor": FFMPEG_AVAILABLE and FFPROBE_AVAILABLE,
        "clips": FFMPEG_AVAILABLE and FFPROBE_AVAILABLE,
        "clip_max_seconds": CLIP_MAX_SECONDS,
        "max_upload_mb": MAX_UPLOAD_MB,
        "cookies": bool(COOKIES_FILE),
        "cookies_lines": cookies_lines,
        "cookies_source": COOKIES_SOURCE,
        "cookies_error": COOKIES_ERROR,
        "env_b64_len": len(os.environ.get("YTDLP_COOKIES_B64", "")),
        "env_raw_len": len(os.environ.get("YTDLP_COOKIES", "")),
    }


@app.post("/api/subtitles")
async def download_subtitles(req: SubtitleRequest):
    """Descarga los subtítulos de un idioma y los sirve en .srt o .vtt."""
    _validate_url(req.url)
    fmt = req.format if req.format in ("srt", "vtt") else "srt"

    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_sub_"))

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [req.lang],
        "subtitlesformat": fmt,
        "outtmpl": str(tmpdir / "sub.%(ext)s"),
    }

    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([req.url.strip()])

    try:
        await asyncio.to_thread(_run)
    except yt_dlp.utils.DownloadError as e:
        _rmtree_robust(tmpdir)
        raise HTTPException(status_code=422, detail=_clean_ytdlp_error(str(e)))

    files = [p for p in tmpdir.iterdir() if p.is_file()]
    if not files:
        _rmtree_robust(tmpdir)
        raise HTTPException(
            status_code=404,
            detail="No hay subtítulos disponibles para ese idioma en este video.",
        )

    path = files[0]
    ext = path.suffix.lstrip(".") or fmt
    base = _sanitize_filename(req.title or "subtitulos")
    lang = re.sub(r"[^\w\-]", "", req.lang) or "sub"

    from starlette.background import BackgroundTask

    return FileResponse(
        path,
        media_type="text/vtt" if ext == "vtt" else "application/x-subrip",
        filename=f"{base}.{lang}.{ext}",
        background=BackgroundTask(lambda: _rmtree_robust(tmpdir)),
    )


@app.get("/api/thumbnail")
async def download_thumbnail(url: str, title: Optional[str] = None):
    """Descarga la miniatura del video como archivo (evita problemas de CORS)."""
    if not _URL_RE.match(url):
        raise HTTPException(status_code=400, detail="URL de imagen inválida")

    def _fetch():
        request = URLRequest(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=30) as response:
            content_type = response.headers.get_content_type()
            return response.read(), content_type

    try:
        data, content_type = await asyncio.to_thread(_fetch)
    except Exception:
        raise HTTPException(status_code=502, detail="No se pudo descargar la miniatura")

    if not content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="El enlace no apunta a una imagen válida")

    suffix = mimetypes.guess_extension(content_type) or ".jpg"
    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_thumb_"))
    path = tmpdir / f"thumb{suffix}"
    path.write_bytes(data)

    from starlette.background import BackgroundTask

    name = _sanitize_filename(title or "miniatura") + suffix
    return FileResponse(
        path,
        media_type=content_type,
        filename=name,
        background=BackgroundTask(lambda: _rmtree_robust(tmpdir)),
    )


def _clean_ytdlp_error(msg: str) -> str:
    """Muestra un mensaje más amigable, sin rutas locales ni ruido técnico."""
    msg = msg.split("\n")[0]
    msg = re.sub(r"^ERROR:\s*", "", msg)
    if "Unsupported URL" in msg:
        return "Esta URL no es compatible con ninguna plataforma soportada."
    if "Private video" in msg or "private" in msg.lower():
        return "El video es privado y no se puede descargar."
    if "Video unavailable" in msg or "unavailable" in msg.lower():
        return "El video no está disponible (puede haber sido eliminado o restringido)."
    if "age" in msg.lower() and "confirm" in msg.lower():
        return "El video tiene restricción de edad y no se puede descargar."
    if "Sign in" in msg or "login" in msg.lower():
        return "El contenido requiere iniciar sesión y no se puede descargar."
    if "429" in msg or "Too Many Requests" in msg or "rate limit" in msg.lower():
        return "La plataforma limitó temporalmente las peticiones. Espera un momento e inténtalo de nuevo."
    return f"No se pudo procesar la URL: {msg[:200]}"


# ---------------------------------------------------------------------------
# Compresor de vídeo (WhatsApp / Discord / Telegram / correo)
# ---------------------------------------------------------------------------

# Tamaños máximos típicos (MB) de cada plataforma
COMPRESS_PRESETS = {
    "whatsapp": 16,
    "whatsapp-hd": 64,
    "discord": 10,
    "discord-nitro": 25,
    "telegram": 50,
    "email": 20,
}

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "200"))
_UPLOAD_CHUNK = 1024 * 1024
_ALLOWED_HEIGHTS = {0, 360, 480, 540, 720, 1080, 1440}
_ALLOWED_SUFFIXES = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
    ".mpg", ".mpeg", ".flv", ".ts", ".3gp", ".wmv",
}

_cjobs: dict[str, dict] = {}
_cjobs_lock = threading.Lock()
_CJOB_TTL_SECONDS = 3600


class _Cancelled(Exception):
    """Se lanza cuando el usuario cancela una compresión en curso."""


def _cjob_new(name: str, size: int, target_mb: float, max_height: int) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _cjobs_lock:
        _cjobs[job_id] = {
            "id": job_id,
            "status": "pending",
            "percent": 0.0,
            "message": "Preparando…",
            "input_name": name,
            "input_size": size,
            "output_size": 0,
            "target_mb": target_mb,
            "max_height": max_height,
            "filename": None,
            "path": None,
            "tmpdir": None,
            "error": None,
            "cancel": False,
            "created": time.time(),
        }
    return job_id


def _cjob_update(job_id: str, **fields) -> None:
    with _cjobs_lock:
        job = _cjobs.get(job_id)
        if job is not None:
            job.update(fields)


def _cjob_get(job_id: str) -> Optional[dict]:
    with _cjobs_lock:
        job = _cjobs.get(job_id)
        return dict(job) if job else None


def _cjob_delete(job_id: str) -> None:
    with _cjobs_lock:
        job = _cjobs.pop(job_id, None)
    if job and job.get("tmpdir"):
        _rmtree_robust(job["tmpdir"])


def _cjobs_cleanup_stale() -> None:
    """Elimina trabajos de compresión antiguos (memoria y disco)."""
    now = time.time()
    with _cjobs_lock:
        stale = [jid for jid, j in _cjobs.items() if now - j["created"] > _CJOB_TTL_SECONDS]
    for jid in stale:
        _cjob_delete(jid)


def _ffprobe_meta(path: Path) -> dict:
    """Lee duración y resolución reales del archivo con ffprobe."""
    cmd = [
        FFPROBE, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    raw = subprocess.run(cmd, capture_output=True, timeout=180, check=True).stdout
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
        for sd in video.get("side_data_list") or []:
            if "rotation" in sd:
                try:
                    rotation = int(sd["rotation"])
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


def _run_ffmpeg(
    args: list,
    job_id: str,
    duration: float,
    pct_from: float,
    pct_to: float,
    getter=None,
    updater=None,
) -> int:
    """Ejecuta ffmpeg informando del progreso real. Devuelve el código de salida.

    `getter`/`updater` permiten reutilizarlo con distintos almacenes de trabajos
    (compresor, clips…).
    """
    getter = getter or _cjob_get
    updater = updater or _cjob_update

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            job = getter(job_id)
            if job and job["cancel"]:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise _Cancelled()

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
                updater(job_id, percent=round(min(pct, pct_to), 1))
    finally:
        if proc.stdout is not None:
            proc.stdout.close()
    return proc.wait()


def _pick_height(src_height: int, video_kbps: float, max_height: int) -> int:
    """Elige la resolución vertical máxima razonable para ese bitrate."""
    if max_height and max_height > 0:
        cap = max_height
    elif video_kbps >= 1600:
        cap = 1080
    elif video_kbps >= 900:
        cap = 720
    elif video_kbps >= 460:
        cap = 480
    else:
        cap = 360
    if src_height and src_height < cap:
        cap = src_height
    return cap - (cap % 2)


def _compress_file(
    job_id: str,
    src: Path,
    dest: Path,
    target_bytes: int,
    max_height: int,
    duration: float,
    meta: dict,
    quality_mode: str = "size",
) -> None:
    """Deja en `dest` un MP4 por debajo del tamaño objetivo."""
    src_size = src.stat().st_size

    # 1) Si ya cabe, basta con remultiplexar: rápido y sin pérdida de calidad.
    if src_size <= target_bytes and meta.get("has_video"):
        _cjob_update(
            job_id, status="compressing", percent=5.0,
            message="Ya cabe en el límite: optimizando sin perder calidad…",
        )
        args = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-progress", "pipe:1", "-nostats",
            "-i", str(src), "-c", "copy", "-movflags", "+faststart", str(dest),
        ]
        code = _run_ffmpeg(args, job_id, duration, 5.0, 90.0)
        if code == 0 and dest.exists() and 0 < dest.stat().st_size <= target_bytes:
            return
        dest.unlink(missing_ok=True)

    # 1b) Modo "priorizar calidad": no se fuerza el tamaño, solo se baja resolución.
    if quality_mode == "quality":
        src_h = meta.get("height") or 0
        cap = max_height if max_height > 0 else src_h
        if src_h and src_h < cap:
            cap = src_h
        height = (cap - (cap % 2)) or None

        args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]
        args += ["-i", str(src)]
        if height and src_h > height:
            args += ["-vf", f"scale=-2:{height}"]
        args += [
            "-map_metadata", "-1",
            "-c:v", "libx264", "-preset", X264_PRESET, "-crf", "23",
            "-pix_fmt", "yuv420p", "-profile:v", "main",
            "-c:a", "aac", "-b:a", "128k", "-ac", "2",
            "-movflags", "+faststart",
            str(dest),
        ]
        _cjob_update(job_id, status="compressing", percent=5.0, message="Comprimiendo el vídeo…")
        code = _run_ffmpeg(args, job_id, duration, 5.0, 98.0)
        if code != 0 or not dest.exists() or dest.stat().st_size == 0:
            raise RuntimeError("No se pudo comprimir el vídeo (ffmpeg falló).")
        return

    # 2) Recomprimir calculando el bitrate a partir del tamaño objetivo.
    # El 0,94 deja un margen para el contenedor y el redondeo de ABR: así casi
    # siempre basta con una sola pasada (clave en servidores con poca CPU).
    audio_kbps = 128
    total_kbps = (target_bytes * 8 * 0.94 / duration / 1000) if duration > 0 else 800.0
    if total_kbps < 420:
        audio_kbps = 96
    if total_kbps < 240:
        audio_kbps = 64

    video_kbps = max(60.0, total_kbps - audio_kbps - 4)

    for attempt in range(2):
        height = _pick_height(meta.get("height") or 0, video_kbps, max_height)
        args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]
        args += ["-i", str(src)]
        if height and (meta.get("height") or 0) > height:
            args += ["-vf", f"scale=-2:{height}"]
        args += [
            "-map_metadata", "-1",
            "-c:v", "libx264", "-preset", X264_PRESET,
            "-b:v", f"{int(video_kbps)}k",
            "-maxrate", f"{int(video_kbps)}k",
            "-bufsize", f"{int(video_kbps * 2)}k",
            "-pix_fmt", "yuv420p", "-profile:v", "main",
            "-c:a", "aac", "-b:a", f"{audio_kbps}k", "-ac", "2",
            "-movflags", "+faststart",
            str(dest),
        ]
        msg = "Comprimiendo el vídeo…" if attempt == 0 else "Ajustando el tamaño final…"
        _cjob_update(job_id, status="compressing", percent=5.0, message=msg)

        code = _run_ffmpeg(args, job_id, duration, 5.0, 98.0)
        if code != 0 or not dest.exists() or dest.stat().st_size == 0:
            raise RuntimeError("No se pudo comprimir el vídeo (ffmpeg falló).")
        if dest.stat().st_size <= target_bytes:
            return

        # Se pasó del objetivo: bajar el bitrate y reintentar una sola vez.
        factor = (target_bytes / dest.stat().st_size) * 0.94
        new_kbps = max(60.0, video_kbps * factor)
        if new_kbps >= video_kbps - 5:
            return  # ya estamos en el mínimo razonable
        video_kbps = new_kbps
        dest.unlink(missing_ok=True)


def _run_compress_job(
    job_id: str,
    src: Path,
    base_name: str,
    target_mb: float,
    max_height: int,
    quality_mode: str = "size",
) -> None:
    """Se ejecuta en un hilo aparte: analiza y comprime el vídeo subido."""
    tmpdir = src.parent
    try:
        _cjob_update(job_id, status="probing", percent=0.0, message="Analizando el vídeo…")
        meta = _ffprobe_meta(src)
        if not meta["has_video"]:
            raise RuntimeError("El archivo no contiene pista de vídeo. Sube un MP4, MOV, MKV o WEBM.")
        duration = meta["duration"]
        if duration <= 0:
            raise RuntimeError("No se pudo leer la duración del vídeo.")

        target_bytes = int(target_mb * 1024 * 1024)
        dest = tmpdir / "comprimido.mp4"
        _compress_file(
            job_id, src, dest, target_bytes, max_height, duration, meta, quality_mode
        )

        if not dest.exists() or dest.stat().st_size == 0:
            raise RuntimeError("No se generó el archivo comprimido.")

        base = _sanitize_filename(base_name.rsplit(".", 1)[0] or "video")
        nombre = f"{base} ({int(target_mb)}MB).mp4"
        _cjob_update(
            job_id,
            status="finished",
            percent=100.0,
            message="¡Listo!",
            output_size=dest.stat().st_size,
            filename=nombre,
            path=str(dest),
        )
    except _Cancelled:
        _rmtree_robust(tmpdir)
        _cjob_update(job_id, status="cancelled", message="Cancelado", tmpdir=None)
    except Exception as exc:  # noqa: BLE001
        _rmtree_robust(tmpdir)
        _cjob_update(job_id, status="error", error=str(exc), message="Error", tmpdir=None)


@app.get("/api/compress/presets")
async def compress_presets():
    """Tamaños recomendados (MB) para cada plataforma."""
    return {
        "presets": COMPRESS_PRESETS,
        "max_upload_mb": MAX_UPLOAD_MB,
        "heights": sorted(h for h in _ALLOWED_HEIGHTS),
    }


@app.post("/api/compress")
async def create_compress_job(
    file: UploadFile = File(...),
    target_mb: float = Form(16.0),
    max_height: int = Form(0),
    quality_mode: str = Form("size"),
):
    """Sube un vídeo y lo comprime para que quepa en el tamaño elegido."""
    if not (FFMPEG_AVAILABLE and FFPROBE_AVAILABLE):
        raise HTTPException(
            status_code=503,
            detail="El servidor no tiene ffmpeg instalado; la compresión no está disponible.",
        )
    if target_mb < 1 or target_mb > 200:
        raise HTTPException(status_code=400, detail="El tamaño objetivo debe estar entre 1 y 200 MB.")
    if max_height not in _ALLOWED_HEIGHTS:
        raise HTTPException(status_code=400, detail="Resolución no válida.")
    if quality_mode not in ("size", "quality"):
        quality_mode = "size"

    nombre = _sanitize_filename(file.filename or "video")
    sufijo = Path(nombre).suffix.lower()
    if sufijo not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Formato no compatible. Sube un vídeo (MP4, MOV, MKV, WEBM…).",
        )

    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_cmp_"))
    src = tmpdir / f"entrada{sufijo}"
    limite = MAX_UPLOAD_MB * 1024 * 1024
    total = 0
    try:
        with src.open("wb") as fh:
            while True:
                chunk = await file.read(_UPLOAD_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > limite:
                    raise HTTPException(
                        status_code=413,
                        detail=f"El archivo supera el límite de {MAX_UPLOAD_MB} MB.",
                    )
                fh.write(chunk)
    except HTTPException:
        _rmtree_robust(tmpdir)
        raise
    except Exception:
        _rmtree_robust(tmpdir)
        raise HTTPException(status_code=500, detail="No se pudo guardar el archivo subido.")
    finally:
        await file.close()

    if total == 0:
        _rmtree_robust(tmpdir)
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    _cjobs_cleanup_stale()
    job_id = _cjob_new(nombre, total, target_mb, max_height)
    _cjob_update(job_id, tmpdir=str(tmpdir))

    threading.Thread(
        target=_run_compress_job,
        args=(job_id, src, nombre, target_mb, max_height, quality_mode),
        daemon=True,
    ).start()

    return {"id": job_id}


@app.get("/api/compress/{job_id}")
async def compress_status(job_id: str):
    """Estado y progreso de una compresión."""
    job = _cjob_get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return {
        k: job[k]
        for k in (
            "id", "status", "percent", "message", "input_name", "input_size",
            "output_size", "target_mb", "filename", "error",
        )
    }


@app.get("/api/compress/{job_id}/file")
async def compress_file(job_id: str):
    """Devuelve el vídeo comprimido y libera los recursos del trabajo."""
    job = _cjob_get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if job["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="La compresión fue cancelada")
    if job["status"] != "finished" or not job.get("path"):
        raise HTTPException(status_code=409, detail="La compresión todavía no ha terminado")

    path = Path(job["path"])
    if not path.exists():
        _cjob_delete(job_id)
        raise HTTPException(status_code=410, detail="El archivo ya no está disponible")

    from starlette.background import BackgroundTask

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=job["filename"] or "video-comprimido.mp4",
        background=BackgroundTask(lambda: _cjob_delete(job_id)),
    )


@app.post("/api/compress/{job_id}/cancel")
async def cancel_compress_job(job_id: str):
    """Solicita cancelar una compresión en curso."""
    job = _cjob_get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if job["status"] in ("finished", "error", "cancelled"):
        return {"ok": False, "status": job["status"]}
    _cjob_update(job_id, cancel=True)
    return {"ok": True, "status": "cancelling"}


# ---------------------------------------------------------------------------
# Clips verticales (TikTok / Reels / YouTube Shorts)
# ---------------------------------------------------------------------------

# Resoluciones de salida por calidad: vertical 9:16, cuadrado 1:1 y tope para
# mantener el original horizontal.
_CLIP_SIZES = {
    "alta": {"v": (1080, 1920), "sq": 1080, "orig": 1080},
    "media": {"v": (720, 1280), "sq": 720, "orig": 720},
    "baja": {"v": (480, 854), "sq": 480, "orig": 480},
}
_CLIP_ASPECTS = ("vertical", "vertical-blur", "square", "original")
_CLIP_LABELS = {
    "vertical": "vertical",
    "vertical-blur": "vertical",
    "square": "cuadrado",
    "original": "original",
}
CLIP_MAX_SECONDS = int(os.environ.get("CLIP_MAX_SECONDS", "300"))
# Tope de descarga cuando el enlace no admite fragmentos (se baja el vídeo entero).
CLIP_MAX_FULL_DOWNLOAD_MB = int(os.environ.get("CLIP_MAX_FULL_DOWNLOAD_MB", "500"))

_clips: dict[str, dict] = {}
_clips_lock = threading.Lock()
_CLIP_TTL_SECONDS = 3600


def _clip_new(url: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _clips_lock:
        _clips[job_id] = {
            "id": job_id,
            "status": "pending",
            "percent": 0.0,
            "message": "Preparando…",
            "url": url,
            "downloaded": 0,
            "total": 0,
            "speed": None,
            "eta": None,
            "input_size": 0,
            "output_size": 0,
            "filename": None,
            "path": None,
            "width": None,
            "height": None,
            "duration": None,
            "tmpdir": None,
            "error": None,
            "cancel": False,
            "created": time.time(),
        }
    return job_id


def _clip_update(job_id: str, **fields) -> None:
    with _clips_lock:
        job = _clips.get(job_id)
        if job is not None:
            job.update(fields)


def _clip_get(job_id: str) -> Optional[dict]:
    with _clips_lock:
        job = _clips.get(job_id)
        return dict(job) if job else None


def _clip_delete(job_id: str) -> None:
    with _clips_lock:
        job = _clips.pop(job_id, None)
    if job and job.get("tmpdir"):
        _rmtree_robust(job["tmpdir"])


def _clips_cleanup_stale() -> None:
    now = time.time()
    with _clips_lock:
        stale = [jid for jid, j in _clips.items() if now - j["created"] > _CLIP_TTL_SECONDS]
    for jid in stale:
        _clip_delete(jid)


def _even(n) -> int:
    """Redondea al múltiplo de 2 más cercano (los códecs de vídeo lo necesitan)."""
    return max(2, int(round(float(n) / 2)) * 2)


def _centered_crop(w: int, h: int, rw: int, rh: int):
    """Rectángulo centrado con la proporción rw:rh, siempre dentro del original."""
    def _floor_even(n: int) -> int:
        return max(2, int(n) - (int(n) % 2))

    if w * rh > h * rw:  # la fuente es más ancha -> recortamos a los lados
        cw, ch = _even(h * rw / rh), _even(h)
    else:  # la fuente es más alta -> recortamos arriba y abajo
        cw, ch = _even(w), _even(w * rh / rw)
    cw, ch = min(cw, _floor_even(w)), min(ch, _floor_even(h))
    x = max(0, (w - cw) // 2)
    y = max(0, (h - ch) // 2)
    return cw, ch, x - (x % 2), y - (y % 2)


def _clip_filter(aspect: str, quality: str, w: int, h: int):
    """Devuelve (filtro de vídeo o None, ancho, alto) para el formato pedido."""
    sizes = _CLIP_SIZES.get(quality) or _CLIP_SIZES["media"]

    if aspect in ("vertical", "vertical-blur"):
        tw, th = sizes["v"]
        cw, ch, x, y = _centered_crop(w, h, 9, 16)
        if aspect == "vertical":
            return f"crop={cw}:{ch}:{x}:{y},scale={tw}:{th},setsar=1", tw, th

        # Fondo desenfocado: se genera a baja resolución (mucho más rápido en
        # CPUs modestas) y luego se estira al tamaño final.
        bw, bh = _even(tw / 4), _even(th / 4)
        vf = (
            f"split=2[bg][fg];"
            f"[bg]crop={cw}:{ch}:{x}:{y},scale={bw}:{bh},boxblur=8:2,scale={tw}:{th}[fondo];"
            f"[fg]scale={tw}:{th}:force_original_aspect_ratio=decrease[delante];"
            f"[fondo][delante]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
        return vf, tw, th

    if aspect == "square":
        side = sizes["sq"]
        cw, ch, x, y = _centered_crop(w, h, 1, 1)
        return f"crop={cw}:{ch}:{x}:{y},scale={side}:{side},setsar=1", side, side

    # Original: solo se limita la altura si hace falta.
    cap = _even(sizes["orig"])
    if h and w and h > cap:
        return f"scale=-2:{cap},setsar=1", _even(w * cap / h), cap
    return None, w, h


def _make_clip_hook(job_id: str, pct_to: float):
    """Progreso de la descarga del fragmento (0 → pct_to)."""

    def hook(d: dict) -> None:
        job = _clip_get(job_id)
        if job and job["cancel"]:
            raise yt_dlp.utils.DownloadCancelled("Cancelado por el usuario")

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 100) if total else 0.0
            _clip_update(
                job_id,
                status="downloading",
                message="Descargando solo el fragmento…",
                percent=round(min(pct, 100.0) * pct_to / 100.0, 1),
                downloaded=done,
                total=total,
                speed=d.get("speed"),
                eta=d.get("eta"),
            )
        elif status == "finished":
            _clip_update(job_id, message="Preparando el recorte…", speed=None, eta=None)

    return hook


def _clip_transform(
    job_id: str,
    src: Path,
    dest: Path,
    start: Optional[float],
    end: Optional[float],
    aspect: str,
    quality: str,
    pct_from: float,
    pct_to: float,
) -> dict:
    """Recorta el fragmento y lo reencuadra. Devuelve tamaño y duración finales."""
    meta = _ffprobe_meta(src)
    if not meta["has_video"]:
        raise RuntimeError("El archivo no contiene pista de vídeo.")

    vf, out_w, out_h = _clip_filter(aspect, quality, meta["width"] or 0, meta["height"] or 0)

    args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]
    if start:  # el corte rápido antes de -i evita decodificar lo que no hace falta
        args += ["-ss", f"{float(start):.3f}"]
    args += ["-i", str(src)]
    if end is not None:
        args += ["-t", f"{max(0.1, float(end) - float(start or 0)):.3f}"]
    if vf:
        args += ["-vf", vf]
    args += [
        "-map_metadata", "-1",
        "-c:v", "libx264", "-preset", X264_PRESET, "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-movflags", "+faststart",
        str(dest),
    ]

    seg = (float(end) - float(start or 0)) if end is not None else (meta["duration"] or 0)
    code = _run_ffmpeg(
        args, job_id, seg, pct_from, pct_to, getter=_clip_get, updater=_clip_update
    )
    if code != 0 or not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError("No se pudo generar el clip (ffmpeg falló).")

    return {"width": out_w or meta["width"], "height": out_h or meta["height"], "duration": seg}


def _clip_finish(job_id: str, dest: Path, base: str, start, end, aspect: str) -> None:
    etiqueta = _CLIP_LABELS.get(aspect, "vertical")
    rango = f"{_time_tag(start) or '0m00s'}-{_time_tag(end)}"
    nombre = f"{_sanitize_filename(base)} {etiqueta} {rango}.mp4"
    _clip_update(
        job_id,
        status="finished",
        percent=100.0,
        message="¡Clip listo!",
        output_size=dest.stat().st_size,
        filename=nombre,
        path=str(dest),
    )


def _clip_download(job_id, url, tmpdir: Path, start, end, con_rango: bool):
    """Descarga el fragmento pedido (o el vídeo completo) y devuelve (info, ruta)."""
    opts = _build_opts(
        "video-1080",
        tmpdir,
        progress_hook=_make_clip_hook(job_id, 70.0),
        start=start if con_rango else None,
        end=end if con_rango else None,
    )
    if not con_rango:
        # Si hay que bajar el archivo entero, se pone un tope para no llenar el disco.
        opts["max_filesize"] = CLIP_MAX_FULL_DOWNLOAD_MB * 1024 * 1024
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
    return info, _resolve_output(tmpdir, filename)


def _run_clip_job_url(job_id, url, start, end, aspect, quality, title) -> None:
    """Hilo: descarga solo el fragmento pedido y lo convierte en clip vertical."""
    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_clip_"))
    _clip_update(
        job_id, tmpdir=str(tmpdir), status="downloading",
        message="Analizando y descargando el fragmento…",
    )
    try:
        try:
            info, src = _clip_download(job_id, url, tmpdir, start, end, True)
            corte = (None, None)  # el fragmento ya viene recortado por yt-dlp
        except yt_dlp.utils.DownloadError:
            # Algunos enlaces (un MP4 suelto, por ejemplo) no permiten descargar
            # solo un trozo: se baja el archivo completo y se recorta con ffmpeg.
            _rmtree_robust(tmpdir)
            tmpdir = Path(tempfile.mkdtemp(prefix="videodl_clip_"))
            _clip_update(
                job_id, tmpdir=str(tmpdir), percent=0.0,
                message="Este enlace no admite fragmentos: descargando el vídeo completo…",
            )
            info, src = _clip_download(job_id, url, tmpdir, start, end, False)
            corte = (start, end)

        if src is None:
            raise RuntimeError("No se pudo descargar el vídeo.")

        _clip_update(
            job_id, status="transforming", percent=72.0,
            message="Creando el clip en formato vertical…",
            input_size=src.stat().st_size,
            duration=info.get("duration"),
        )

        dest = tmpdir / "clip.mp4"
        datos = _clip_transform(
            job_id, src, dest, corte[0], corte[1], aspect, quality, 72.0, 99.0
        )
        src.unlink(missing_ok=True)

        base = title or info.get("title") or "clip"
        _clip_update(job_id, width=datos["width"], height=datos["height"], duration=datos["duration"])
        _clip_finish(job_id, dest, base, start, end, aspect)
    except yt_dlp.utils.DownloadCancelled:
        _rmtree_robust(tmpdir)
        _clip_update(job_id, status="cancelled", message="Cancelado", tmpdir=None)
    except yt_dlp.utils.DownloadError as exc:
        _rmtree_robust(tmpdir)
        _clip_update(job_id, status="error", error=_clean_ytdlp_error(str(exc)), tmpdir=None)
    except _Cancelled:
        _rmtree_robust(tmpdir)
        _clip_update(job_id, status="cancelled", message="Cancelado", tmpdir=None)
    except Exception as exc:  # noqa: BLE001
        _rmtree_robust(tmpdir)
        _clip_update(job_id, status="error", error=str(exc), tmpdir=None)


def _run_clip_job_upload(job_id, src: Path, base_name, start, end, aspect, quality) -> None:
    """Hilo: recorta y reencuadra un archivo ya subido."""
    tmpdir = src.parent
    try:
        _clip_update(
            job_id, status="transforming", percent=5.0,
            message="Recortando y reencuadrando…",
        )
        dest = tmpdir / "clip.mp4"
        datos = _clip_transform(job_id, src, dest, start, end, aspect, quality, 5.0, 99.0)
        _clip_update(job_id, width=datos["width"], height=datos["height"], duration=datos["duration"])
        _clip_finish(job_id, dest, base_name.rsplit(".", 1)[0], start, end, aspect)
    except _Cancelled:
        _rmtree_robust(tmpdir)
        _clip_update(job_id, status="cancelled", message="Cancelado", tmpdir=None)
    except Exception as exc:  # noqa: BLE001
        _rmtree_robust(tmpdir)
        _clip_update(job_id, status="error", error=str(exc), tmpdir=None)


def _clip_validate(aspect: str, quality: str, start: float, end: float):
    if not (FFMPEG_AVAILABLE and FFPROBE_AVAILABLE):
        raise HTTPException(
            status_code=503,
            detail="El servidor no tiene ffmpeg instalado; el recortador no está disponible.",
        )
    if aspect not in _CLIP_ASPECTS:
        raise HTTPException(status_code=400, detail="Formato de clip no válido.")
    if quality not in _CLIP_SIZES:
        raise HTTPException(status_code=400, detail="Calidad no válida.")
    dur = float(end) - float(start)
    if dur < 1:
        raise HTTPException(status_code=400, detail="El clip debe durar al menos 1 segundo.")
    if dur > CLIP_MAX_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"El clip no puede durar más de {CLIP_MAX_SECONDS // 60} minutos.",
        )


@app.get("/api/clips/options")
async def clip_options():
    """Formatos, calidades y duración máxima admitidos."""
    return {
        "aspects": list(_CLIP_ASPECTS),
        "qualities": {
            k: {"vertical": list(v["v"]), "square": v["sq"], "original": v["orig"]}
            for k, v in _CLIP_SIZES.items()
        },
        "max_seconds": CLIP_MAX_SECONDS,
        "max_upload_mb": MAX_UPLOAD_MB,
        "heights": [1080, 720, 480],
    }


@app.post("/api/clips")
async def create_clip_job(req: ClipRequest):
    """Crea un clip vertical a partir de un fragmento de un vídeo en línea."""
    _validate_url(req.url)
    _clip_validate(req.aspect, req.quality, req.start, req.end)

    _clips_cleanup_stale()
    job_id = _clip_new(req.url.strip())
    threading.Thread(
        target=_run_clip_job_url,
        args=(job_id, req.url.strip(), req.start, req.end, req.aspect, req.quality, req.title),
        daemon=True,
    ).start()
    return {"id": job_id}


@app.post("/api/clips/upload")
async def create_clip_job_upload(
    file: UploadFile = File(...),
    start: float = Form(0),
    end: float = Form(0),
    aspect: str = Form("vertical"),
    quality: str = Form("media"),
    duration: float = Form(0),
):
    """Crea un clip vertical a partir de un archivo subido (recorte opcional)."""
    if not (FFMPEG_AVAILABLE and FFPROBE_AVAILABLE):
        raise HTTPException(status_code=503, detail="El servidor no tiene ffmpeg instalado.")

    nombre = _sanitize_filename(file.filename or "video")
    sufijo = Path(nombre).suffix.lower()
    if sufijo not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Formato no compatible. Sube un vídeo (MP4, MOV, MKV, WEBM…).",
        )

    # Si el navegador no nos da el fin del fragmento, se usa todo el vídeo.
    fin = float(end) if end and end > 0 else float(duration) if duration > 0 else 0.0
    if start < 0 or fin <= start:
        raise HTTPException(status_code=400, detail="Rango de recorte no válido.")
    _clip_validate(aspect, quality, float(start), fin)

    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_clip_"))
    src = tmpdir / f"entrada{sufijo}"
    limite = MAX_UPLOAD_MB * 1024 * 1024
    total = 0
    try:
        with src.open("wb") as fh:
            while True:
                chunk = await file.read(_UPLOAD_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > limite:
                    raise HTTPException(
                        status_code=413,
                        detail=f"El archivo supera el límite de {MAX_UPLOAD_MB} MB.",
                    )
                fh.write(chunk)
    except HTTPException:
        _rmtree_robust(tmpdir)
        raise
    except Exception:
        _rmtree_robust(tmpdir)
        raise HTTPException(status_code=500, detail="No se pudo guardar el archivo subido.")
    finally:
        await file.close()

    if total == 0:
        _rmtree_robust(tmpdir)
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    _clips_cleanup_stale()
    job_id = _clip_new(f"archivo:{nombre}")
    _clip_update(job_id, tmpdir=str(tmpdir), input_size=total)
    threading.Thread(
        target=_run_clip_job_upload,
        args=(job_id, src, nombre, float(start), fin, aspect, quality),
        daemon=True,
    ).start()
    return {"id": job_id}


@app.get("/api/clips/{job_id}")
async def clip_status(job_id: str):
    """Estado y progreso de un clip."""
    job = _clip_get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return {
        k: job[k]
        for k in (
            "id", "status", "percent", "message", "downloaded", "total", "speed",
            "eta", "input_size", "output_size", "filename", "width", "height",
            "duration", "error",
        )
    }


@app.get("/api/clips/{job_id}/file")
async def clip_file(job_id: str):
    """Devuelve el clip terminado y libera sus recursos."""
    job = _clip_get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if job["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="El clip fue cancelado")
    if job["status"] != "finished" or not job.get("path"):
        raise HTTPException(status_code=409, detail="El clip todavía no está listo")

    path = Path(job["path"])
    if not path.exists():
        _clip_delete(job_id)
        raise HTTPException(status_code=410, detail="El archivo ya no está disponible")

    from starlette.background import BackgroundTask

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=job["filename"] or "clip.mp4",
        background=BackgroundTask(lambda: _clip_delete(job_id)),
    )


@app.post("/api/clips/{job_id}/cancel")
async def cancel_clip_job(job_id: str):
    """Solicita cancelar un clip en curso."""
    job = _clip_get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if job["status"] in ("finished", "error", "cancelled"):
        return {"ok": False, "status": job["status"]}
    _clip_update(job_id, cancel=True)
    return {"ok": True, "status": "cancelling"}


# ---------------------------------------------------------------------------
# Archivos estáticos (al final para que la API tenga prioridad)
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/comprimir-video-whatsapp", include_in_schema=False)
@app.get("/comprimir", include_in_schema=False)
async def page_comprimir():
    """Página dedicada al compresor (URL pensada para posicionar en Google)."""
    return FileResponse(STATIC_DIR / "comprimir.html")


@app.get("/herramientas", include_in_schema=False)
async def page_herramientas():
    """Directorio con todas las herramientas del sitio."""
    return FileResponse(STATIC_DIR / "herramientas.html")


@app.get("/recortar-clip-vertical", include_in_schema=False)
@app.get("/clips-verticales", include_in_schema=False)
@app.get("/clips-twitch-vertical", include_in_schema=False)
async def page_clips():
    """Página del recortador de clips verticales para TikTok/Reels/Shorts."""
    return FileResponse(STATIC_DIR / "clips.html")


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
