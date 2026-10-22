"""Router de clips verticales a partir de archivos propios.

El modo «pegar un enlace» se retiró con el descargador: ahora solo se recortan y
reencuadran vídeos que el usuario sube desde su equipo.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .config import (
    CLIP_MAX_SECONDS,
    FFMPEG,
    FFMPEG_AVAILABLE,
    FFPROBE_AVAILABLE,
    MAX_UPLOAD_MB,
    X264_PRESET,
)
from .media import Cancelled, ffprobe_meta, run_ffmpeg
from .stores import clips
from .tasks import spawn_job
from .uploads import save_video_upload
from .utils import centered_crop, even, public_error, rmtree_robust, sanitize_filename, time_tag

logger = logging.getLogger("videodl.clips")

router = APIRouter()

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


def clip_filter(aspect: str, quality: str, w: int, h: int):
    """Devuelve (filtro de vídeo o None, ancho, alto) para el formato pedido."""
    sizes = _CLIP_SIZES.get(quality) or _CLIP_SIZES["media"]

    if aspect in ("vertical", "vertical-blur"):
        tw, th = sizes["v"]
        cw, ch, x, y = centered_crop(w, h, 9, 16)
        if aspect == "vertical":
            return f"crop={cw}:{ch}:{x}:{y},scale={tw}:{th},setsar=1", tw, th

        # Fondo desenfocado: se genera a baja resolución (mucho más rápido en
        # CPUs modestas) y luego se estira al tamaño final.
        bw, bh = even(tw / 4), even(th / 4)
        vf = (
            f"split=2[bg][fg];"
            f"[bg]crop={cw}:{ch}:{x}:{y},scale={bw}:{bh},boxblur=8:2,scale={tw}:{th}[fondo];"
            f"[fg]scale={tw}:{th}:force_original_aspect_ratio=decrease[delante];"
            f"[fondo][delante]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
        return vf, tw, th

    if aspect == "square":
        side = sizes["sq"]
        cw, ch, x, y = centered_crop(w, h, 1, 1)
        return f"crop={cw}:{ch}:{x}:{y},scale={side}:{side},setsar=1", side, side

    # Original: solo se limita el lado corto si hace falta (en un vertical, el
    # ancho). Limitar la altura dejaba un 1080x1920 en 608x1080 sin necesidad.
    cap = even(sizes["orig"])
    corto = min(w, h) if w and h else 0
    if corto and corto > cap:
        if w >= h:
            return f"scale=-2:{cap},setsar=1", even(w * cap / h), cap
        return f"scale={cap}:-2,setsar=1", cap, even(h * cap / w)
    return None, w, h


def clip_transform(
    job_id: str,
    src: Path,
    dest: Path,
    start: float | None,
    end: float | None,
    aspect: str,
    quality: str,
    pct_from: float,
    pct_to: float,
) -> dict:
    """Recorta el fragmento y lo reencuadra. Devuelve tamaño y duración finales."""
    meta = ffprobe_meta(src)
    if not meta["has_video"]:
        raise RuntimeError("El archivo no contiene pista de vídeo.")

    vf, out_w, out_h = clip_filter(aspect, quality, meta["width"] or 0, meta["height"] or 0)

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
    code = run_ffmpeg(args, clips, job_id, seg, pct_from, pct_to)
    if code != 0 or not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError("No se pudo generar el clip (ffmpeg falló).")

    return {"width": out_w or meta["width"], "height": out_h or meta["height"], "duration": seg}


def _clip_finish(job_id: str, dest: Path, base: str, start, end, aspect: str) -> None:
    etiqueta = _CLIP_LABELS.get(aspect, "vertical")
    rango = f"{time_tag(start) or '0m00s'}-{time_tag(end)}"
    nombre = f"{sanitize_filename(base)} {etiqueta} {rango}.mp4"
    clips.update(
        job_id,
        status="finished",
        percent=100.0,
        message="¡Clip listo!",
        output_size=dest.stat().st_size,
        filename=nombre,
        path=str(dest),
    )


def _run_clip_job_upload(job_id, src: Path, base_name, start, end, aspect, quality) -> None:
    """Hilo: recorta y reencuadra un archivo ya subido."""
    tmpdir = src.parent
    try:
        clips.update(
            job_id, status="transforming", percent=5.0,
            message="Recortando y reencuadrando…",
        )
        dest = tmpdir / "clip.mp4"
        datos = clip_transform(job_id, src, dest, start, end, aspect, quality, 5.0, 99.0)
        clips.update(job_id, width=datos["width"], height=datos["height"], duration=datos["duration"])
        _clip_finish(job_id, dest, base_name.rsplit(".", 1)[0], start, end, aspect)
    except Cancelled:
        rmtree_robust(tmpdir)
        clips.update(job_id, status="cancelled", message="Cancelado", tmpdir=None)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error al recortar el clip %s", job_id)
        rmtree_robust(tmpdir)
        clips.update(
            job_id,
            status="error",
            error=public_error(exc, "No se pudo crear el clip."),
            message="Error",
            tmpdir=None,
        )


def clip_validate(aspect: str, quality: str, start: float, end: float) -> None:
    # Primero se valida la entrada del usuario; luego la capacidad del servidor.
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
    if not (FFMPEG_AVAILABLE and FFPROBE_AVAILABLE):
        raise HTTPException(
            status_code=503,
            detail="El servidor no tiene ffmpeg instalado; el recortador no está disponible.",
        )


@router.get("/api/clips/options")
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
    }


@router.post("/api/clips/upload")
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

    # Si el navegador no nos da el fin del fragmento, se usa todo el vídeo.
    fin = float(end) if end and end > 0 else float(duration) if duration > 0 else 0.0
    if start < 0 or fin <= start:
        raise HTTPException(status_code=400, detail="Rango de recorte no válido.")
    clip_validate(aspect, quality, float(start), fin)

    src, total = await save_video_upload(file, dir_prefix="videodl_clip_")

    clips.cleanup_stale()
    job_id = clips.new(
        source=src.name, percent=0.0, message="Preparando…",
        downloaded=0, total=0, speed=None, eta=None, input_size=total, output_size=0,
        filename=None, path=None, width=None, height=None, duration=None, tmpdir=str(src.parent),
    )
    try:
        spawn_job(_run_clip_job_upload, job_id, src, src.name, float(start), fin, aspect, quality)
    except HTTPException:
        # Sin hueco para el trabajo: no dejar ni el registro ni la carpeta temporal.
        clips.delete(job_id)
        rmtree_robust(src.parent)
        raise
    return {"id": job_id}


@router.get("/api/clips/{job_id}")
async def clip_status(job_id: str):
    """Estado y progreso de un clip."""
    job = clips.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return {
        k: job.get(k)
        for k in (
            "id", "status", "percent", "message", "input_size", "output_size",
            "filename", "width", "height", "duration", "error",
        )
    }


@router.get("/api/clips/{job_id}/file")
async def clip_file(job_id: str):
    """Devuelve el clip terminado y libera sus recursos."""
    job = clips.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if job["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="El clip fue cancelado")
    if job["status"] != "finished" or not job.get("path"):
        raise HTTPException(status_code=409, detail="El clip todavía no está listo")

    path = Path(job["path"])
    if not path.exists():
        clips.delete(job_id)
        raise HTTPException(status_code=410, detail="El archivo ya no está disponible")

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=job["filename"] or "clip.mp4",
        background=BackgroundTask(lambda: clips.delete(job_id)),
    )


@router.post("/api/clips/{job_id}/cancel")
async def cancel_clip_job(job_id: str):
    """Solicita cancelar un clip en curso."""
    status = clips.request_cancel(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if status in ("finished", "error", "cancelled"):
        return {"ok": False, "status": status}
    return {"ok": True, "status": "cancelling"}
