"""Herramientas de ffmpeg con archivos propios: vídeo a GIF, extraer audio y
unir o cortar audio.

Siguen el mismo patrón que los clips verticales: la subida se guarda en una
carpeta temporal, un hilo ejecuta ffmpeg informando del progreso y el resultado
se entrega una sola vez y se borra al descargarlo.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .config import (
    AUDIO_MAX_FILES,
    FFMPEG,
    FFMPEG_AVAILABLE,
    FFPROBE_AVAILABLE,
    GIF_MAX_SECONDS,
    MAX_UPLOAD_MB,
)
from .constants import ALLOWED_AUDIO_SUFFIXES
from .media import Cancelled, ffprobe_meta, run_ffmpeg
from .stores import audios, gifs
from .tasks import spawn_job
from .uploads import save_audio_uploads, save_media_upload, save_video_upload
from .utils import public_error, rmtree_robust, sanitize_filename, time_tag

logger = logging.getLogger("videodl.media_tools")

router = APIRouter()

_PUBLIC_FIELDS = (
    "id", "status", "percent", "message", "input_size", "output_size",
    "filename", "duration", "error",
)


# ---------------------------------------------------------------------------
# Piezas comunes
# ---------------------------------------------------------------------------


def _require_ffmpeg() -> None:
    if not (FFMPEG_AVAILABLE and FFPROBE_AVAILABLE):
        raise HTTPException(
            status_code=503,
            detail="El servidor no tiene ffmpeg instalado; esta herramienta no está disponible.",
        )


def _public_status(store, job_id: str) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return {key: job.get(key) for key in _PUBLIC_FIELDS}


def _deliver(store, job_id: str, fallback_name: str, fallback_type: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if job["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="El trabajo fue cancelado")
    if job["status"] != "finished" or not job.get("path"):
        raise HTTPException(status_code=409, detail="El resultado todavía no está listo")

    path = Path(job["path"])
    if not path.exists():
        store.delete(job_id)
        raise HTTPException(status_code=410, detail="El archivo ya no está disponible")

    return FileResponse(
        path,
        media_type=job.get("media_type") or fallback_type,
        filename=job.get("filename") or fallback_name,
        background=BackgroundTask(lambda: store.delete(job_id)),
    )


def _cancel(store, job_id: str) -> dict:
    status = store.request_cancel(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if status in ("finished", "error", "cancelled"):
        return {"ok": False, "status": status}
    return {"ok": True, "status": "cancelling"}


def _fail(store, job_id: str, tmpdir: Path, exc: Exception, fallback: str, label: str) -> None:
    if isinstance(exc, Cancelled):
        rmtree_robust(tmpdir)
        store.update(job_id, status="cancelled", message="Cancelado", tmpdir=None)
        return
    logger.exception("Error en %s %s", label, job_id)
    rmtree_robust(tmpdir)
    store.update(
        job_id,
        status="error",
        error=public_error(exc, fallback),
        message="Error",
        tmpdir=None,
    )


def _base_name(filename: str) -> str:
    return sanitize_filename(filename.rsplit(".", 1)[0]) if filename else "archivo"


# ---------------------------------------------------------------------------
# Vídeo a GIF
# ---------------------------------------------------------------------------

GIF_WIDTHS = (320, 480, 640)
GIF_FPS = (8, 10, 12, 15)


def gif_args(src: Path, dest: Path, start: float, seconds: float, width: int, fps: int) -> list:
    """Comando de ffmpeg con paleta propia: GIFs mucho más nítidos y ligeros."""
    vf = (
        f"fps={fps},scale=w='min({width},iw)':h=-2:flags=lanczos,"
        "split[a][b];[a]palettegen=stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle"
    )
    args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]
    if start:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(src), "-t", f"{seconds:.3f}", "-an", "-vf", vf, "-loop", "0", str(dest)]
    return args


def _run_gif_job(job_id: str, src: Path, base: str, start: float, end: float, width: int, fps: int) -> None:
    tmpdir = src.parent
    try:
        gifs.update(job_id, status="transforming", percent=5.0, message="Creando el GIF…")
        meta = ffprobe_meta(src)
        if not meta["has_video"]:
            raise RuntimeError("El archivo no contiene pista de vídeo.")
        seconds = end - start
        dest = tmpdir / "salida.gif"
        code = run_ffmpeg(gif_args(src, dest, start, seconds, width, fps), gifs, job_id, seconds, 5.0, 99.0)
        if code != 0 or not dest.exists() or dest.stat().st_size == 0:
            raise RuntimeError("No se pudo crear el GIF (ffmpeg falló).")
        gifs.update(
            job_id,
            status="finished",
            percent=100.0,
            message="¡GIF listo!",
            output_size=dest.stat().st_size,
            duration=seconds,
            filename=f"{base} {time_tag(start)}-{time_tag(end)}.gif",
            path=str(dest),
        )
    except Exception as exc:  # noqa: BLE001
        _fail(gifs, job_id, tmpdir, exc, "No se pudo crear el GIF.", "GIF")


def gif_validate(start: float, end: float, width: int, fps: int) -> None:
    if width not in GIF_WIDTHS:
        raise HTTPException(status_code=400, detail="Ancho de GIF no válido.")
    if fps not in GIF_FPS:
        raise HTTPException(status_code=400, detail="Fotogramas por segundo no válidos.")
    if start < 0 or end <= start:
        raise HTTPException(status_code=400, detail="Rango de recorte no válido.")
    seconds = end - start
    if seconds < 0.5:
        raise HTTPException(status_code=400, detail="El GIF debe durar al menos medio segundo.")
    if seconds > GIF_MAX_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=f"El GIF no puede durar más de {GIF_MAX_SECONDS} segundos.",
        )


@router.get("/api/gif/options")
async def gif_options():
    return {
        "widths": list(GIF_WIDTHS),
        "fps": list(GIF_FPS),
        "max_seconds": GIF_MAX_SECONDS,
        "max_upload_mb": MAX_UPLOAD_MB,
    }


@router.post("/api/gif/upload")
async def create_gif_job(
    file: UploadFile = File(...),
    start: float = Form(0),
    end: float = Form(0),
    width: int = Form(480),
    fps: int = Form(12),
):
    _require_ffmpeg()
    gif_validate(float(start), float(end), int(width), int(fps))

    src, total = await save_video_upload(file, dir_prefix="videodl_gif_")
    gifs.cleanup_stale()
    job_id = gifs.new(
        source=src.name, percent=0.0, message="Preparando…", input_size=total,
        output_size=0, filename=None, path=None, duration=None, tmpdir=str(src.parent),
        media_type="image/gif",
    )
    base = _base_name(file.filename or "video")
    try:
        spawn_job(_run_gif_job, job_id, src, base, float(start), float(end), int(width), int(fps))
    except HTTPException:
        gifs.delete(job_id)
        rmtree_robust(src.parent)
        raise
    return {"id": job_id}


@router.get("/api/gif/{job_id}")
async def gif_status(job_id: str):
    return _public_status(gifs, job_id)


@router.get("/api/gif/{job_id}/file")
async def gif_file(job_id: str):
    return _deliver(gifs, job_id, "animacion.gif", "image/gif")


@router.post("/api/gif/{job_id}/cancel")
async def gif_cancel(job_id: str):
    return _cancel(gifs, job_id)


# ---------------------------------------------------------------------------
# Audio: formatos de salida (extraer, unir y cortar)
# ---------------------------------------------------------------------------

AUDIO_FORMATS = ("mp3", "m4a", "wav")
AUDIO_BITRATES = (128, 192, 256, 320)

_AUDIO_MEDIA = {"mp3": "audio/mpeg", "m4a": "audio/mp4", "wav": "audio/wav"}


def _audio_codec_args(fmt: str, bitrate: int) -> list:
    if fmt == "mp3":
        return ["-c:a", "libmp3lame", "-b:a", f"{bitrate}k"]
    if fmt == "m4a":
        return ["-c:a", "aac", "-b:a", f"{bitrate}k", "-movflags", "+faststart"]
    return ["-c:a", "pcm_s16le"]


def _audio_validate_format(fmt: str, bitrate: int) -> None:
    if fmt not in AUDIO_FORMATS:
        raise HTTPException(status_code=400, detail="Formato de audio no válido.")
    if bitrate not in AUDIO_BITRATES:
        raise HTTPException(status_code=400, detail="Calidad de audio no válida.")


@router.get("/api/audio/options")
async def audio_options():
    return {
        "formats": list(AUDIO_FORMATS),
        "bitrates": list(AUDIO_BITRATES),
        "max_files": AUDIO_MAX_FILES,
        "max_upload_mb": MAX_UPLOAD_MB,
    }


@router.get("/api/audio/{job_id}")
async def audio_status(job_id: str):
    return _public_status(audios, job_id)


@router.get("/api/audio/{job_id}/file")
async def audio_file(job_id: str):
    return _deliver(audios, job_id, "audio.mp3", "audio/mpeg")


@router.post("/api/audio/{job_id}/cancel")
async def audio_cancel(job_id: str):
    return _cancel(audios, job_id)


# ---------------------------------------------------------------------------
# Extraer audio de un vídeo (o convertir un audio)
# ---------------------------------------------------------------------------


def _run_extract_job(job_id: str, src: Path, base: str, fmt: str, bitrate: int) -> None:
    tmpdir = src.parent
    try:
        audios.update(job_id, status="transforming", percent=5.0, message="Extrayendo el audio…")
        meta = ffprobe_meta(src)
        if not meta["has_audio"]:
            raise RuntimeError("El archivo no contiene pista de audio.")
        dest = tmpdir / f"salida.{fmt}"
        args = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats",
            "-i", str(src), "-vn", "-map", "0:a:0", "-map_metadata", "-1",
            *_audio_codec_args(fmt, bitrate), str(dest),
        ]
        code = run_ffmpeg(args, audios, job_id, meta["duration"], 5.0, 99.0)
        if code != 0 or not dest.exists() or dest.stat().st_size == 0:
            raise RuntimeError("No se pudo extraer el audio (ffmpeg falló).")
        audios.update(
            job_id,
            status="finished",
            percent=100.0,
            message="¡Audio listo!",
            output_size=dest.stat().st_size,
            duration=meta["duration"],
            filename=f"{base}.{fmt}",
            path=str(dest),
        )
    except Exception as exc:  # noqa: BLE001
        _fail(audios, job_id, tmpdir, exc, "No se pudo extraer el audio.", "extracción de audio")


@router.post("/api/audio/extract")
async def create_extract_job(
    file: UploadFile = File(...),
    format: str = Form("mp3"),
    bitrate: int = Form(192),
):
    _require_ffmpeg()
    _audio_validate_format(format, int(bitrate))

    src, total = await save_media_upload(
        file,
        dir_prefix="videodl_audio_",
        allowed_suffixes=ALLOWED_AUDIO_SUFFIXES,
        max_mb=MAX_UPLOAD_MB,
        format_label="de vídeo o de audio",
        base_name="entrada",
    )
    audios.cleanup_stale()
    job_id = audios.new(
        source=src.name, percent=0.0, message="Preparando…", input_size=total,
        output_size=0, filename=None, path=None, duration=None, tmpdir=str(src.parent),
        media_type=_AUDIO_MEDIA[format],
    )
    base = _base_name(file.filename or "audio")
    try:
        spawn_job(_run_extract_job, job_id, src, base, format, int(bitrate))
    except HTTPException:
        audios.delete(job_id)
        rmtree_robust(src.parent)
        raise
    return {"id": job_id}


# ---------------------------------------------------------------------------
# Unir y cortar audio
# ---------------------------------------------------------------------------


def edit_filter(count: int) -> str:
    """Filtro que normaliza cada entrada y las concatena en orden."""
    parts = [
        f"[{i}:a:0]aresample=44100,aformat=channel_layouts=stereo[a{i}]" for i in range(count)
    ]
    joined = "".join(f"[a{i}]" for i in range(count))
    return ";".join(parts) + f";{joined}concat=n={count}:v=0:a=1[out]"


def _run_edit_job(
    job_id: str, sources: list[Path], bases: list[str], start: float, end: float,
    fmt: str, bitrate: int,
) -> None:
    tmpdir = sources[0].parent
    try:
        audios.update(job_id, status="transforming", percent=3.0, message="Preparando el audio…")
        total = 0.0
        for src in sources:
            meta = ffprobe_meta(src)
            if not meta["has_audio"]:
                raise RuntimeError("Uno de los archivos no contiene pista de audio.")
            total += meta["duration"]
        if total <= 0:
            raise RuntimeError("No se pudo leer la duración de los archivos.")
        if start >= total:
            raise RuntimeError("El inicio del recorte supera la duración del audio.")

        stop = min(end, total) if end > 0 else total
        if stop <= start:
            raise RuntimeError("El final del recorte debe ser posterior al inicio.")
        seconds = stop - start

        dest = tmpdir / f"salida.{fmt}"
        args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]
        for src in sources:
            args += ["-i", str(src)]
        args += ["-filter_complex", edit_filter(len(sources)), "-map", "[out]"]
        if start > 0:
            args += ["-ss", f"{start:.3f}"]
        if end > 0 or start > 0:
            args += ["-t", f"{seconds:.3f}"]
        args += ["-map_metadata", "-1", *_audio_codec_args(fmt, bitrate), str(dest)]

        audios.update(job_id, message="Procesando el audio…", percent=5.0)
        code = run_ffmpeg(args, audios, job_id, seconds, 5.0, 99.0)
        if code != 0 or not dest.exists() or dest.stat().st_size == 0:
            raise RuntimeError("No se pudo procesar el audio (ffmpeg falló).")

        name = "audio-unido" if len(sources) > 1 else f"{bases[0]} recortado"
        audios.update(
            job_id,
            status="finished",
            percent=100.0,
            message="¡Audio listo!",
            output_size=dest.stat().st_size,
            duration=seconds,
            filename=f"{name}.{fmt}",
            path=str(dest),
        )
    except Exception as exc:  # noqa: BLE001
        _fail(audios, job_id, tmpdir, exc, "No se pudo procesar el audio.", "edición de audio")


@router.post("/api/audio/edit")
async def create_edit_job(
    files: list[UploadFile] = File(...),
    start: float = Form(0),
    end: float = Form(0),
    format: str = Form("mp3"),
    bitrate: int = Form(192),
):
    _require_ffmpeg()
    _audio_validate_format(format, int(bitrate))
    if not files:
        raise HTTPException(status_code=400, detail="Sube al menos un archivo.")
    if len(files) > AUDIO_MAX_FILES:
        for pending in files:
            await pending.close()
        raise HTTPException(
            status_code=400,
            detail=f"Puedes unir hasta {AUDIO_MAX_FILES} archivos a la vez.",
        )
    if start < 0 or end < 0 or (end > 0 and end <= start):
        for pending in files:
            await pending.close()
        raise HTTPException(status_code=400, detail="Rango de recorte no válido.")
    if len(files) == 1 and start <= 0 and end <= 0:
        for pending in files:
            await pending.close()
        raise HTTPException(
            status_code=400,
            detail="Sube al menos dos archivos para unirlos o indica un recorte.",
        )

    bases = [_base_name(f.filename or "audio") for f in files]
    sources, total = await save_audio_uploads(
        files, dir_prefix="videodl_audio_", max_mb=MAX_UPLOAD_MB
    )
    audios.cleanup_stale()
    job_id = audios.new(
        source=f"{len(sources)} archivos", percent=0.0, message="Preparando…",
        input_size=total, output_size=0, filename=None, path=None, duration=None,
        tmpdir=str(sources[0].parent), media_type=_AUDIO_MEDIA[format],
    )
    try:
        spawn_job(
            _run_edit_job, job_id, sources, bases, float(start), float(end), format, int(bitrate)
        )
    except HTTPException:
        audios.delete(job_id)
        rmtree_robust(sources[0].parent)
        raise
    return {"id": job_id}
