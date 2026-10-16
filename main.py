"""VideoDL - Descarga videos de casi cualquier plataforma.

Backend FastAPI + yt-dlp.

Endpoints:
  POST /api/info     -> analiza una URL y devuelve título, miniatura y calidades
  POST /api/download -> descarga el video/audio y lo devuelve como archivo
"""

import asyncio
import mimetypes
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from typing import Optional
from urllib.request import Request as URLRequest
from urllib.request import urlopen

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="VideoDL")

# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------


class InfoRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    mode: str = "best"  # "best" | "audio" | "video-<height>"
    title: Optional[str] = None  # solo para nombrar el archivo


class SubtitleRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    lang: str = Field(..., min_length=2, max_length=20)
    format: str = "srt"  # "srt" | "vtt"
    title: Optional[str] = None


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


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
    """Descarga el video (o solo audio) y lo sirve como archivo."""
    _validate_url(req.url)

    mode = req.mode
    if mode not in ("best", "audio") and not re.fullmatch(r"video-\d{2,4}", mode):
        raise HTTPException(status_code=400, detail="Modo de descarga inválido")

    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_"))

    if mode == "audio":
        fmt = "bestaudio/best"
    elif mode == "best":
        fmt = (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
            if FFMPEG_AVAILABLE
            else "best[ext=mp4]/best"
        )
    else:  # video-<height>
        height = mode.split("-", 1)[1]
        fmt = (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]"
            f"/bestvideo[height<={height}]+bestaudio"
            f"/best[height<={height}][ext=mp4]/best[height<={height}]"
            if FFMPEG_AVAILABLE
            else f"best[height<={height}][ext=mp4]/best[height<={height}]/best"
        )

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": str(tmpdir / "media.%(ext)s"),
        "format": fmt,
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

    def _download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(req.url.strip(), download=True)
            filename = ydl.prepare_filename(info)
            return info, filename

    try:
        info, filename = await asyncio.to_thread(_download)
    except yt_dlp.utils.DownloadError as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=_clean_ytdlp_error(str(e)))

    # Determinar el archivo final (el post-procesado puede cambiar la extensión)
    path = Path(filename)
    if not path.exists():
        files = [p for p in tmpdir.iterdir() if p.is_file()]
        if not files:
            shutil.rmtree(tmpdir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="No se generó ningún archivo")
        path = files[0]

    base = _sanitize_filename(req.title or info.get("title") or "video")
    ext = "mp3" if mode == "audio" and FFMPEG_AVAILABLE else path.suffix.lstrip(".") or "mp4"
    final_name = f"{base}.{ext}"

    # Limpieza automática tras enviar la respuesta
    from starlette.background import BackgroundTask

    def _cleanup():
        shutil.rmtree(tmpdir, ignore_errors=True)

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=final_name,
        background=BackgroundTask(_cleanup),
    )


@app.get("/api/health")
async def health():
    """Comprobación de estado del servicio."""
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
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=_clean_ytdlp_error(str(e)))

    files = [p for p in tmpdir.iterdir() if p.is_file()]
    if not files:
        shutil.rmtree(tmpdir, ignore_errors=True)
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
        background=BackgroundTask(lambda: shutil.rmtree(tmpdir, ignore_errors=True)),
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
        background=BackgroundTask(lambda: shutil.rmtree(tmpdir, ignore_errors=True)),
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

app.mount("/", StaticFiles(directory="static", html=True), name="static")
