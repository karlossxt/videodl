"""Router de clips verticales (TikTok / Reels / YouTube Shorts)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import yt_dlp
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .config import (
    CLIP_MAX_FULL_DOWNLOAD_MB,
    CLIP_MAX_SECONDS,
    CLIP_PAD_SECONDS,
    FFMPEG,
    FFMPEG_AVAILABLE,
    FFPROBE_AVAILABLE,
    MAX_UPLOAD_MB,
    X264_PRESET,
)
from .downloader import spawn_job
from .errors import clean_ytdlp_error
from .media import (
    Cancelled,
    build_opts,
    ffprobe_meta,
    first_video_pts,
    probe_safe,
    resolve_output,
    run_ffmpeg,
)
from .models import ClipRequest
from .security import ensure_public_url
from .stores import clips
from .uploads import save_video_upload
from .utils import centered_crop, even, rmtree_robust, sanitize_filename, time_tag

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

    # Original: solo se limita la altura si hace falta.
    cap = even(sizes["orig"])
    if h and w and h > cap:
        return f"scale=-2:{cap},setsar=1", even(w * cap / h), cap
    return None, w, h


def _make_clip_hook(job_id: str, pct_to: float):
    """Progreso de la descarga del fragmento (0 → pct_to)."""

    def hook(d: dict) -> None:
        job = clips.get(job_id)
        if job and job.get("cancel"):
            raise yt_dlp.utils.DownloadCancelled("Cancelado por el usuario")

        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 100) if total else 0.0
            clips.update(
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
            clips.update(job_id, message="Preparando el recorte…", speed=None, eta=None)

    return hook


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
    seek_absolute: bool = False,
) -> dict:
    """Recorta el fragmento y lo reencuadra. Devuelve tamaño y duración finales."""
    meta = ffprobe_meta(src)
    if not meta["has_video"]:
        raise RuntimeError("El archivo no contiene pista de vídeo.")

    vf, out_w, out_h = clip_filter(aspect, quality, meta["width"] or 0, meta["height"] or 0)

    args = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]
    if start:  # el corte rápido antes de -i evita decodificar lo que no hace falta
        if seek_absolute:
            # El fragmento descargado arrastra marcas de tiempo desplazadas, así que
            # el segundo de corte hay que buscarlo por su valor absoluto.
            args += ["-seek_timestamp", "1"]
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


def _clip_download(job_id, url, tmpdir: Path, start, end, con_rango: bool, exacto: bool = False):
    """Descarga el fragmento pedido (o el vídeo completo) y devuelve (info, ruta).

    Con ``exacto=False`` el fragmento se copia tal cual (barato, pero arrastra el
    trozo del fotograma clave); con ``exacto=True`` yt-dlp recodifica al vuelo para
    que el corte caiga justo en el segundo pedido (mucho más lento).
    """
    opts = build_opts(
        "video-1080",
        tmpdir,
        progress_hook=_make_clip_hook(job_id, 70.0),
        start=start if con_rango else None,
        end=end if con_rango else None,
        force_keyframes=exacto,
    )
    if not con_rango:
        # Si hay que bajar el archivo entero, se pone un tope para no llenar el disco.
        opts["max_filesize"] = CLIP_MAX_FULL_DOWNLOAD_MB * 1024 * 1024
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
    return info, resolve_output(tmpdir, filename)


def _run_clip_job_url(job_id, url, start, end, aspect, quality, title) -> None:
    """Hilo: descarga solo el fragmento pedido y lo convierte en clip vertical."""
    tmpdir = Path(tempfile.mkdtemp(prefix="videodl_clip_"))
    clips.update(
        job_id, tmpdir=str(tmpdir), status="downloading",
        message="Analizando y descargando el fragmento…",
    )
    inicio, fin = float(start), float(end)
    dur = max(0.1, fin - inicio)
    src = None
    info: dict = {}
    corte = (None, None)
    seek_abs = False
    try:
        # Se pide un trozo algo más largo de lo necesario: yt-dlp copia desde el
        # fotograma clave anterior, así que hay que adelantar el inicio y dejar
        # cola suficiente para poder recuperar después el segundo exacto.
        a = max(0.0, inicio - CLIP_PAD_SECONDS)
        problema = None
        meta: dict = {}

        # 1) Intento barato: descarga en copia del trozo ampliado y recorte exacto
        #    en el paso de ffmpeg.
        try:
            info, src = _clip_download(job_id, url, tmpdir, a, fin + CLIP_PAD_SECONDS, True)
            meta = probe_safe(src)
        except yt_dlp.utils.DownloadError:
            problema = "descarga"

        if problema is None:
            p0 = first_video_pts(src) if src is not None else None
            desplazado = p0 is None or p0 <= 0.5
            ss = (inicio - a) if desplazado else inicio
            total = float(meta.get("duration") or 0)
            if not meta.get("has_video") or total <= 0 or ss + dur > total + 0.75:
                problema = "ajuste"
            else:
                corte = (ss, ss + dur)
                seek_abs = True

        # 2) El fragmento no servía: se pide el corte exacto a yt-dlp (recodifica
        #    al vuelo, más lento, pero deja el clip en el segundo pedido).
        if problema == "ajuste":
            rmtree_robust(tmpdir)
            tmpdir = Path(tempfile.mkdtemp(prefix="videodl_clip_"))
            clips.update(
                job_id, tmpdir=str(tmpdir), percent=0.0,
                message="Ajustando el fragmento al segundo exacto…",
            )
            try:
                info, src = _clip_download(job_id, url, tmpdir, inicio, fin, True, exacto=True)
                problema = None if probe_safe(src).get("has_video") else "descarga"
            except yt_dlp.utils.DownloadError:
                problema = "descarga"
            if problema is None:
                corte = (None, None)

        # 3) Último recurso: algunos enlaces (un MP4 suelto, por ejemplo) no admiten
        #    descargar solo un trozo; se baja el archivo completo y se recorta luego.
        if problema == "descarga":
            rmtree_robust(tmpdir)
            tmpdir = Path(tempfile.mkdtemp(prefix="videodl_clip_"))
            clips.update(
                job_id, tmpdir=str(tmpdir), percent=0.0,
                message="Este enlace no admite fragmentos: descargando el vídeo completo…",
            )
            info, src = _clip_download(job_id, url, tmpdir, inicio, fin, False)
            corte = (inicio, fin)

        if src is None:
            raise RuntimeError("No se pudo descargar el vídeo.")

        clips.update(
            job_id, status="transforming", percent=72.0,
            message="Creando el clip en formato vertical…",
            input_size=src.stat().st_size,
            duration=info.get("duration"),
        )

        dest = tmpdir / "clip.mp4"
        datos = clip_transform(
            job_id, src, dest, corte[0], corte[1], aspect, quality, 72.0, 99.0,
            seek_absolute=seek_abs,
        )
        src.unlink(missing_ok=True)

        base = title or info.get("title") or "clip"
        clips.update(job_id, width=datos["width"], height=datos["height"], duration=datos["duration"])
        _clip_finish(job_id, dest, base, inicio, fin, aspect)
    except yt_dlp.utils.DownloadCancelled:
        rmtree_robust(tmpdir)
        clips.update(job_id, status="cancelled", message="Cancelado", tmpdir=None)
    except yt_dlp.utils.DownloadError as exc:
        rmtree_robust(tmpdir)
        clips.update(
            job_id, status="error", error=clean_ytdlp_error(str(exc), url), tmpdir=None
        )
    except Cancelled:
        rmtree_robust(tmpdir)
        clips.update(job_id, status="cancelled", message="Cancelado", tmpdir=None)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error al crear el clip %s", job_id)
        rmtree_robust(tmpdir)
        clips.update(job_id, status="error", error=str(exc), tmpdir=None)


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
        clips.update(job_id, status="error", error=str(exc), tmpdir=None)


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
        "heights": [1080, 720, 480],
    }


@router.post("/api/clips")
async def create_clip_job(req: ClipRequest):
    """Crea un clip vertical a partir de un fragmento de un vídeo en línea."""
    ensure_public_url(req.url)
    clip_validate(req.aspect, req.quality, req.start, req.end)

    clips.cleanup_stale()
    job_id = clips.new(
        url=req.url.strip(), percent=0.0, message="Preparando…",
        downloaded=0, total=0, speed=None, eta=None, input_size=0, output_size=0,
        filename=None, path=None, width=None, height=None, duration=None, tmpdir=None,
    )
    spawn_job(
        _run_clip_job_url,
        job_id, req.url.strip(), req.start, req.end, req.aspect, req.quality, req.title,
    )
    return {"id": job_id}


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
        url=f"archivo:{src.name}", percent=0.0, message="Preparando…",
        downloaded=0, total=0, speed=None, eta=None, input_size=total, output_size=0,
        filename=None, path=None, width=None, height=None, duration=None, tmpdir=str(src.parent),
    )
    spawn_job(_run_clip_job_upload, job_id, src, src.name, float(start), fin, aspect, quality)
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
            "id", "status", "percent", "message", "downloaded", "total", "speed",
            "eta", "input_size", "output_size", "filename", "width", "height",
            "duration", "error",
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
