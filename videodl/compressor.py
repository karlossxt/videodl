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

# Por debajo de este bitrate de vídeo la imagen se ve mal y, aun así, el archivo
# puede seguir sin caber: mejor decírselo al usuario que servir algo peor sin
# avisar.
_MIN_VIDEO_KBPS = 60.0
_MAX_INTENTOS = 3

# Códecs que se pueden copiar tal cual a MP4 y se reproducen en cualquier móvil
# (WhatsApp incluido). Un VP9 o un AV1 «caben» en MP4, pero luego no se ven: por
# eso no basta con comprobar que el archivo quepa para remultiplexar.
_MP4_VIDEO_CODECS = frozenset({"h264"})
_MP4_AUDIO_CODECS = frozenset({"aac", "mp3"})


def compatible_mp4(meta: dict) -> bool:
    """¿Se puede copiar a MP4 sin recodificar y que se reproduzca en todas partes?"""
    if meta.get("vcodec") not in _MP4_VIDEO_CODECS:
        return False
    return not meta.get("has_audio") or meta.get("acodec") in _MP4_AUDIO_CODECS


def pick_short_side(
    src_width: int, src_height: int, video_kbps: float, max_height: int
) -> int:
    """Lado corto máximo razonable para ese bitrate.

    El tope va en el **lado corto** para que un vídeo vertical no acabe
    achicado: un 1080x1920 con tope 720 debe quedar en 720x1280, no en 406x720
    (que es lo que sale al limitar la altura en vertical).
    """
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
    if src_width and src_height:
        cap = min(cap, src_width, src_height)
    elif src_height:
        cap = min(cap, src_height)
    return cap - (cap % 2)


def scale_args(src_width: int, src_height: int, cap: int) -> list[str]:
    """Argumentos ``-vf`` para dejar el lado corto en ``cap`` (vacío si ya cabe)."""
    if not cap or not src_width or not src_height:
        return []
    if min(src_width, src_height) <= cap:
        return []
    if src_width >= src_height:
        return ["-vf", f"scale=-2:{cap}"]
    return ["-vf", f"scale={cap}:-2"]


def _mb(target_bytes: int) -> str:
    """«16» o «16.5», sin decimales que sobren."""
    return f"{target_bytes / (1024 * 1024):g}"


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
    """Deja en ``dest`` un MP4 por debajo del tamaño objetivo.

    En modo ``size`` el objetivo es una promesa: si no se puede cumplir sin
    destrozar la calidad, se lanza ``RuntimeError`` en vez de devolver un archivo
    más grande del pedido (el usuario lo enviaría por WhatsApp y no cabría).
    """
    src_size = src.stat().st_size
    src_width = meta.get("width") or 0
    src_height = meta.get("height") or 0

    # 1) Si ya cabe, los códecs son compatibles y no hay que bajar resolución,
    # basta con remultiplexar: rápido y sin pérdida de calidad. Si los códecs no
    # son compatibles (VP9, AV1, Opus…) hay que recodificar aunque quepa: un MP4
    # con VP9 no se reproduce en WhatsApp ni en un iPhone.
    necesita_escala = bool(
        max_height
        and src_width
        and src_height
        and min(src_width, src_height) > max_height
    )
    if (
        src_size <= target_bytes
        and meta.get("has_video")
        and compatible_mp4(meta)
        and not necesita_escala
    ):
        compressions.update(
            job_id, status="compressing", percent=5.0,
            message="Ya cabe en el límite: optimizando sin perder calidad…",
        )
        args = [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-progress", "pipe:1", "-nostats",
            "-i", str(src),
            # Solo vídeo y audio: copiar subtítulos o datos a MP4 puede fallar.
            "-map", "0:v:0", "-map", "0:a?",
            "-c", "copy", "-movflags", "+faststart", str(dest),
        ]
        code = run_ffmpeg(args, compressions, job_id, duration, 5.0, 90.0)
        if code == 0 and dest.exists() and 0 < dest.stat().st_size <= target_bytes:
            return
        dest.unlink(missing_ok=True)

    # 1b) Modo "priorizar calidad": no se fuerza el tamaño, solo se baja resolución.
    if quality_mode == "quality":
        cap = max_height if max_height > 0 else min(src_width, src_height)
        cap = (cap - (cap % 2)) or 0

        args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]
        args += ["-i", str(src)]
        args += scale_args(src_width, src_height, cap)
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

    video_kbps = max(_MIN_VIDEO_KBPS, total_kbps - audio_kbps - 4)

    # Cada reintento ocupa su propio tramo de la barra: si empieza otra pasada,
    # el progreso no retrocede de 98 % a 5 % (parecía que se había roto).
    tramos = [(5.0, 60.0), (60.0, 85.0), (85.0, 98.0)]

    # Si el archivo ya cabía, solo se recodifica para bajar la resolución: el
    # bitrate disponible no debe decidir el tamaño (daría 360p a un vídeo que ya
    # entraba en 720p). El bitrate calculado sí vale: es >= el del origen.
    solo_escala = src_size <= target_bytes

    for attempt in range(_MAX_INTENTOS):
        pct_from, pct_to = tramos[min(attempt, len(tramos) - 1)]
        if solo_escala:
            cap = min(max_height, src_width, src_height) if src_width and src_height else max_height
            cap -= cap % 2
        else:
            cap = pick_short_side(src_width, src_height, video_kbps, max_height)
        args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]
        args += ["-i", str(src)]
        args += scale_args(src_width, src_height, cap)
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
        compressions.update(job_id, status="compressing", percent=pct_from, message=msg)

        code = run_ffmpeg(args, compressions, job_id, duration, pct_from, pct_to)
        if code != 0 or not dest.exists() or dest.stat().st_size == 0:
            raise RuntimeError("No se pudo comprimir el vídeo (ffmpeg falló).")
        if dest.stat().st_size <= target_bytes:
            return

        # Se pasó del objetivo: bajar el bitrate y reintentar.
        factor = (target_bytes / dest.stat().st_size) * 0.96
        nuevo = max(_MIN_VIDEO_KBPS, video_kbps * factor)
        dest.unlink(missing_ok=True)
        if attempt == _MAX_INTENTOS - 1 or nuevo >= video_kbps - 5:
            break
        video_kbps = nuevo

    # No se cumplió el objetivo: se borra el intento para no entregar un archivo
    # que no cabe donde el usuario lo va a enviar.
    destino = _mb(target_bytes)
    raise RuntimeError(
        f"No se puede dejar en {destino} MB sin una calidad inservible: el vídeo es "
        "demasiado largo o la resolución muy alta. Prueba un tamaño mayor, una "
        "resolución menor o un vídeo más corto (o elige «Priorizar calidad»)."
    )


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
        nombre = f"{base} ({_mb(target_bytes)}MB).mp4"
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
