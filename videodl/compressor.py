"""Router del compresor de vídeo (WhatsApp / Discord / Telegram / correo)."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .config import (
    COMPRESS_MAX_TARGET_MB,
    FFMPEG,
    FFMPEG_AVAILABLE,
    FFPROBE_AVAILABLE,
    MAX_UPLOAD_MB,
    X264_PRESET,
)
from .constants import ALLOWED_HEIGHTS, COMPRESS_PRESETS
from .downloader import spawn_job
from .media import Cancelled, ffprobe_meta, run_ffmpeg
from .stores import compressions
from .uploads import save_video_upload
from .utils import rmtree_robust, sanitize_filename

logger = logging.getLogger("videodl.compressor")

router = APIRouter()


def pick_height(src_height: int, video_kbps: float, max_height: int) -> int:
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


def compress_file(
    job_id: str,
    src: Path,
    dest: Path,
    target_bytes: int,
    max_height: int,
    duration: float,
    meta: dict,
    quality_mode: str = "size",
) -> None:
    """Deja en ``dest`` un MP4 por debajo del tamaño objetivo."""
    src_size = src.stat().st_size

    # 1) Si ya cabe, basta con remultiplexar: rápido y sin pérdida de calidad.
    if src_size <= target_bytes and meta.get("has_video"):
        compressions.update(
            job_id, status="compressing", percent=5.0,
            message="Ya cabe en el límite: optimizando sin perder calidad…",
        )
        args = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-progress", "pipe:1", "-nostats",
            "-i", str(src), "-c", "copy", "-movflags", "+faststart", str(dest),
        ]
        code = run_ffmpeg(args, compressions, job_id, duration, 5.0, 90.0)
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
        compressions.update(job_id, status="compressing", percent=5.0, message="Comprimiendo el vídeo…")
        code = run_ffmpeg(args, compressions, job_id, duration, 5.0, 98.0)
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
        height = pick_height(meta.get("height") or 0, video_kbps, max_height)
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
        compressions.update(job_id, status="compressing", percent=5.0, message=msg)

        code = run_ffmpeg(args, compressions, job_id, duration, 5.0, 98.0)
        if code != 0 or not dest.exists() or dest.stat().st_size == 0:
            raise RuntimeError("No se pudo comprimir el vídeo (ffmpeg falló).")
        if dest.stat().st_size <= target_bytes:
            return

        # Se pasó del objetivo: bajar el bitrate y reintentar una sola vez.
        factor = (target_bytes / dest.stat().st_size) * 0.94
        new_kbps = max(60.0, video_kbps * factor)
        if new_kbps >= video_kbps - 5:
            logger.info("Compresión %s: no se puede bajar más sin perder calidad", job_id)
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
        compressions.update(job_id, status="probing", percent=0.0, message="Analizando el vídeo…")
        meta = ffprobe_meta(src)
        if not meta["has_video"]:
            raise RuntimeError("El archivo no contiene pista de vídeo. Sube un MP4, MOV, MKV o WEBM.")
        duration = meta["duration"]
        if duration <= 0:
            raise RuntimeError("No se pudo leer la duración del vídeo.")

        target_bytes = int(target_mb * 1024 * 1024)
        dest = tmpdir / "comprimido.mp4"
        compress_file(job_id, src, dest, target_bytes, max_height, duration, meta, quality_mode)

        if not dest.exists() or dest.stat().st_size == 0:
            raise RuntimeError("No se generó el archivo comprimido.")

        base = sanitize_filename(base_name.rsplit(".", 1)[0] or "video")
        nombre = f"{base} ({int(target_mb)}MB).mp4"
        compressions.update(
            job_id,
            status="finished",
            percent=100.0,
            message="¡Listo!",
            output_size=dest.stat().st_size,
            filename=nombre,
            path=str(dest),
        )
    except Cancelled:
        rmtree_robust(tmpdir)
        compressions.update(job_id, status="cancelled", message="Cancelado", tmpdir=None)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error al comprimir %s", job_id)
        rmtree_robust(tmpdir)
        compressions.update(job_id, status="error", error=str(exc), message="Error", tmpdir=None)


@router.get("/api/compress/presets")
async def compress_presets():
    """Tamaños recomendados (MB) para cada plataforma."""
    return {
        "presets": COMPRESS_PRESETS,
        "max_upload_mb": MAX_UPLOAD_MB,
        "max_target_mb": COMPRESS_MAX_TARGET_MB,
        "heights": sorted(ALLOWED_HEIGHTS),
    }


@router.post("/api/compress")
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
    if target_mb < 1 or target_mb > COMPRESS_MAX_TARGET_MB:
        raise HTTPException(
            status_code=400,
            detail=f"El tamaño objetivo debe estar entre 1 y {COMPRESS_MAX_TARGET_MB} MB.",
        )
    if max_height not in ALLOWED_HEIGHTS:
        raise HTTPException(status_code=400, detail="Resolución no válida.")
    if quality_mode not in ("size", "quality"):
        quality_mode = "size"

    src, total = await save_video_upload(file, dir_prefix="videodl_cmp_")

    compressions.cleanup_stale()
    job_id = compressions.new(
        input_name=sanitize_filename(file.filename or "video"),
        input_size=total,
        output_size=0,
        target_mb=target_mb,
        max_height=max_height,
        message="Preparando…",
        percent=0.0,
        filename=None,
        path=None,
        tmpdir=str(src.parent),
    )
    spawn_job(_run_compress_job, job_id, src, src.name, target_mb, max_height, quality_mode)
    return {"id": job_id}


@router.get("/api/compress/{job_id}")
async def compress_status(job_id: str):
    """Estado y progreso de una compresión."""
    job = compressions.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return {
        k: job.get(k)
        for k in (
            "id", "status", "percent", "message", "input_name", "input_size",
            "output_size", "target_mb", "filename", "error",
        )
    }


@router.get("/api/compress/{job_id}/file")
async def compress_result_file(job_id: str):
    """Devuelve el vídeo comprimido y libera los recursos del trabajo."""
    job = compressions.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if job["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="La compresión fue cancelada")
    if job["status"] != "finished" or not job.get("path"):
        raise HTTPException(status_code=409, detail="La compresión todavía no ha terminado")

    path = Path(job["path"])
    if not path.exists():
        compressions.delete(job_id)
        raise HTTPException(status_code=410, detail="El archivo ya no está disponible")

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=job["filename"] or "video-comprimido.mp4",
        background=BackgroundTask(lambda: compressions.delete(job_id)),
    )


@router.post("/api/compress/{job_id}/cancel")
async def cancel_compress_job(job_id: str):
    """Solicita cancelar una compresión en curso."""
    status = compressions.request_cancel(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if status in ("finished", "error", "cancelled"):
        return {"ok": False, "status": status}
    return {"ok": True, "status": "cancelling"}
