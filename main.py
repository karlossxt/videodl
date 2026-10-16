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
  GET  /api/health          -> estado del servicio

Tanto /api/download como /api/jobs aceptan "start" y "end" (segundos) para
descargar solo un fragmento del video; el corte se hace con ffmpeg.
"""

import asyncio
import mimetypes
import os
import re
import shutil
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
from fastapi import FastAPI, HTTPException
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


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

# Archivo de cookies opcional (algunas plataformas piden iniciar sesión desde
# servidores). Se rellena desde la variable de entorno YTDLP_COOKIES(_B64).
COOKIES_FILE: Optional[str] = None


def _setup_cookies() -> None:
    """Prepara un cookies.txt temporal si se define YTDLP_COOKIES o YTDLP_COOKIES_B64.

    Sirve para plataformas que exigen sesión iniciada (p. ej. YouTube en la nube).
    Es completamente opcional: si no se definen, la app funciona igual.
    """
    global COOKIES_FILE

    raw = os.environ.get("YTDLP_COOKIES", "").strip()
    if not raw:
        b64 = os.environ.get("YTDLP_COOKIES_B64", "").strip()
        if b64:
            import base64

            try:
                raw = base64.b64decode(b64).decode("utf-8", "replace").strip()
            except Exception:
                raw = ""

    if not raw:
        return

    try:
        path = Path(tempfile.gettempdir()) / "videodl_cookies.txt"
        path.write_text(raw, encoding="utf-8")
        COOKIES_FILE = str(path)
    except OSError:
        COOKIES_FILE = None


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
    return {"status": "ok", "ffmpeg": FFMPEG_AVAILABLE}


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
# Archivos estáticos (al final para que la API tenga prioridad)
# ---------------------------------------------------------------------------

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
