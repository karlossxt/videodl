"""Router de descargas: análisis, descarga directa, trabajos en segundo plano,
subtítulos y miniatura."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import re
import tempfile
import threading
from pathlib import Path

import yt_dlp
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .config import FFMPEG_AVAILABLE
from .errors import clean_ytdlp_error
from .media import build_opts, resolve_output
from .models import DownloadRequest, InfoRequest, JobRequest, SubtitleRequest
from .runtime import job_limiter
from .security import ensure_public_url, fetch_image
from .stores import downloads
from .utils import human_size, rmtree_robust, sanitize_filename, time_tag

logger = logging.getLogger("videodl.downloader")

router = APIRouter()

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

_LANG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,19}$")


# ---------------------------------------------------------------------------
# Validación y utilidades
# ---------------------------------------------------------------------------


def validate_mode(mode: str) -> str:
    if mode in ("best", "audio") or re.fullmatch(r"video-\d{2,4}", mode or ""):
        return mode
    raise HTTPException(status_code=400, detail="Modo de descarga inválido")


def validate_range(start: float | None, end: float | None) -> None:
    """Comprueba que el fragmento solicitado tenga sentido."""
    if (start is not None or end is not None) and not FFMPEG_AVAILABLE:
        raise HTTPException(
            status_code=400,
            detail="Para recortar fragmentos hace falta ffmpeg instalado en el servidor.",
        )
    if start is not None and end is not None and end <= start:
        raise HTTPException(
            status_code=400,
            detail="El fin del fragmento debe ser mayor que el inicio.",
        )


def _sub_label(tracks: list, lang: str) -> str:
    for track in tracks or []:
        name = track.get("name")
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

    auto_langs = [lang for lang in _COMMON_LANGS if lang in auto]
    auto_langs += [lang for lang in auto if lang not in _COMMON_LANGS]
    for lang in auto_langs:
        # Omitir el automático si ya existe uno manual del mismo idioma
        if lang.split("-")[0].lower() in manual_bases:
            continue
        result.append({"lang": lang, "label": _sub_label(auto[lang], lang), "auto": True})

    return result[:14]


def _final_name(
    mode: str,
    title: str | None,
    info: dict,
    path: Path,
    start: float | None = None,
    end: float | None = None,
) -> str:
    base = sanitize_filename(title or info.get("title") or "video")
    if start is not None or end is not None:
        base = f"{base} (corte {time_tag(start or 0)}-{time_tag(end) or 'fin'})"
    ext = "mp3" if mode == "audio" and FFMPEG_AVAILABLE else (path.suffix.lstrip(".") or "mp4")
    return f"{base}.{ext}"


def spawn_job(target, *args) -> None:
    """Lanza un trabajo en un hilo, respetando el límite de concurrencia."""
    if not job_limiter.acquire():
        raise HTTPException(
            status_code=429,
            detail="El servidor está procesando demasiados vídeos ahora mismo. Inténtalo de nuevo en unos segundos.",
        )

    def _runner() -> None:
        try:
            target(*args)
        except Exception:  # noqa: BLE001 - último cortafuegos del hilo
            logger.exception("Trabajo en segundo plano falló sin control")
        finally:
            job_limiter.release()

    threading.Thread(target=_runner, daemon=True).start()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/info")
async def video_info(req: InfoRequest):
    """Analiza la URL sin descargar y devuelve los metadatos y calidades."""
    ensure_public_url(req.url)

    def _extract():
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(req.url.strip(), download=False)

    try:
        info = await asyncio.to_thread(_extract)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=422, detail=clean_ytdlp_error(str(e))) from e

    # Si es una playlist, tomar solo el primer video
    if info.get("_type") == "playlist" and info.get("entries"):
        info = info["entries"][0]

    # Recolectar calidades de video únicas por altura
    qualities: dict[int, dict] = {}
    audio_available = False
    for f in info.get("formats", []) or []:
        vcodec = f.get("vcodec") or "none"
        acodec = f.get("acodec") or "none"
        height = f.get("height")
        if vcodec != "none" and height:
            entry = qualities.get(height)
            size = human_size(f.get("filesize") or f.get("filesize_approx"))
            if entry is None or (size and not entry.get("size")):
                qualities[height] = {
                    "height": height,
                    "label": f"{height}p" + (f" {f.get('fps')}fps" if (f.get("fps") or 0) >= 50 else ""),
                    "ext": f.get("ext"),
                    "size": size,
                }
        # Solo cuenta como audio descargable el formato que NO tiene vídeo.
        if vcodec == "none" and acodec != "none":
            audio_available = True

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
        "audio_available": audio_available,
        "subtitles": _collect_subtitles(info),
        "ffmpeg_available": FFMPEG_AVAILABLE,
    }


@router.post("/api/download")
async def download(req: DownloadRequest):
    """Descarga el video (o solo audio) y lo sirve como archivo (bloqueante)."""
    ensure_public_url(req.url)
    mode = validate_mode(req.mode)
    validate_range(req.start, req.end)

    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_"))
    opts = build_opts(mode, tmpdir, start=req.start, end=req.end)

    def _download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(req.url.strip(), download=True)
            return info, ydl.prepare_filename(info)

    try:
        info, filename = await asyncio.to_thread(_download)
    except yt_dlp.utils.DownloadError as e:
        rmtree_robust(tmpdir)
        raise HTTPException(status_code=422, detail=clean_ytdlp_error(str(e))) from e

    path = resolve_output(tmpdir, filename)
    if path is None:
        rmtree_robust(tmpdir)
        raise HTTPException(status_code=500, detail="No se generó ningún archivo")

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=_final_name(mode, req.title, info, path, req.start, req.end),
        background=BackgroundTask(lambda: rmtree_robust(tmpdir)),
    )


# ---------------------------------------------------------------------------
# Trabajos de descarga en segundo plano (con progreso en vivo)
# ---------------------------------------------------------------------------


def _make_progress_hook(job_id: str):
    """Hook de yt-dlp que actualiza el estado del trabajo y atiende la cancelación."""

    def hook(d: dict) -> None:
        job = downloads.get(job_id)
        if job and job.get("cancel"):
            raise yt_dlp.utils.DownloadCancelled("Cancelado por el usuario")

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            percent = (downloaded / total * 100) if total else 0.0
            # En calidades altas se descargan dos archivos por separado (video y audio)
            name = (d.get("filename") or "").lower()
            phase = "audio" if name.endswith((".m4a", ".mp3", ".opus", ".ogg", ".aac")) else "video"
            downloads.update(
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
            downloads.update(job_id, status="processing", percent=100.0, speed=None, eta=0)

    return hook


def _run_job(job_id, url, mode, title, start=None, end=None) -> None:
    """Se ejecuta en un hilo aparte: descarga y deja el archivo listo."""
    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_job_"))
    downloads.update(job_id, tmpdir=str(tmpdir))

    opts = build_opts(mode, tmpdir, progress_hook=_make_progress_hook(job_id), start=start, end=end)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        path = resolve_output(tmpdir, filename)
        if path is None:
            raise RuntimeError("No se generó ningún archivo")

        downloads.update(
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
        rmtree_robust(tmpdir)
        downloads.update(job_id, status="cancelled", error="Descarga cancelada", tmpdir=None)
    except yt_dlp.utils.DownloadError as e:
        rmtree_robust(tmpdir)
        downloads.update(job_id, status="error", error=clean_ytdlp_error(str(e)), tmpdir=None)
    except Exception:  # noqa: BLE001
        logger.exception("Error inesperado en la descarga %s", job_id)
        rmtree_robust(tmpdir)
        downloads.update(
            job_id, status="error", error="Error inesperado durante la descarga", tmpdir=None
        )


@router.post("/api/jobs")
async def create_job(req: JobRequest):
    """Inicia una descarga en segundo plano y devuelve su identificador."""
    ensure_public_url(req.url)
    mode = validate_mode(req.mode)
    validate_range(req.start, req.end)

    downloads.cleanup_stale()
    job_id = downloads.new(url=req.url.strip(), mode=mode, tmpdir=None, path=None, filename=None,
                           percent=0.0, downloaded=0, total=0, speed=None, eta=None, phase=None)
    spawn_job(_run_job, job_id, req.url.strip(), mode, req.title, req.start, req.end)
    return {"id": job_id}


@router.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    """Estado y progreso de un trabajo."""
    job = downloads.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return {
        k: job.get(k)
        for k in ("id", "status", "percent", "downloaded", "total", "speed", "eta", "error", "filename", "phase")
    }


@router.get("/api/jobs/{job_id}/file")
async def job_file(job_id: str):
    """Devuelve el archivo de un trabajo terminado y libera sus recursos."""
    job = downloads.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if job["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="La descarga fue cancelada")
    if job["status"] != "finished" or not job.get("path"):
        raise HTTPException(status_code=409, detail="La descarga todavía no ha terminado")

    path = Path(job["path"])
    if not path.exists():
        downloads.delete(job_id)
        raise HTTPException(status_code=410, detail="El archivo ya no está disponible")

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=job["filename"] or "video.mp4",
        background=BackgroundTask(lambda: downloads.delete(job_id)),
    )


@router.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Solicita cancelar un trabajo en curso."""
    status = downloads.request_cancel(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if status in ("finished", "error", "cancelled"):
        return {"ok": False, "status": status}
    return {"ok": True, "status": "cancelling"}


@router.post("/api/subtitles")
async def download_subtitles(req: SubtitleRequest):
    """Descarga los subtítulos de un idioma y los sirve en .srt o .vtt."""
    ensure_public_url(req.url)
    # `lang` acaba en un patrón glob de yt-dlp: se restringe a caracteres seguros
    # para que un valor como ".*" no arrastre todas las pistas.
    if not _LANG_RE.match(req.lang or ""):
        raise HTTPException(status_code=400, detail="Idioma de subtítulos no válido.")
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
        rmtree_robust(tmpdir)
        raise HTTPException(status_code=422, detail=clean_ytdlp_error(str(e))) from e

    files = [p for p in tmpdir.iterdir() if p.is_file()]
    if not files:
        rmtree_robust(tmpdir)
        raise HTTPException(
            status_code=404,
            detail="No hay subtítulos disponibles para ese idioma en este video.",
        )

    path = files[0]
    ext = path.suffix.lstrip(".") or fmt
    base = sanitize_filename(req.title or "subtitulos")
    lang = re.sub(r"[^\w\-]", "", req.lang) or "sub"

    return FileResponse(
        path,
        media_type="text/vtt" if ext == "vtt" else "application/x-subrip",
        filename=f"{base}.{lang}.{ext}",
        background=BackgroundTask(lambda: rmtree_robust(tmpdir)),
    )


@router.get("/api/thumbnail")
async def download_thumbnail(url: str, title: str | None = None):
    """Descarga la miniatura del video como archivo (evita problemas de CORS)."""
    try:
        data, content_type = await asyncio.to_thread(fetch_image, url)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo descargar la miniatura %s", url, exc_info=True)
        raise HTTPException(status_code=502, detail="No se pudo descargar la miniatura") from None

    if not content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="El enlace no apunta a una imagen válida")

    suffix = mimetypes.guess_extension(content_type) or ".jpg"
    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_thumb_"))
    path = tmpdir / f"thumb{suffix}"
    path.write_bytes(data)

    name = sanitize_filename(title or "miniatura") + suffix
    return FileResponse(
        path,
        media_type=content_type,
        filename=name,
        background=BackgroundTask(lambda: rmtree_robust(tmpdir)),
    )
