"""Envoltorios de ffmpeg y ffprobe para los archivos del usuario."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from pathlib import Path

from .config import FFMPEG_TIMEOUT_SECONDS, FFPROBE

logger = logging.getLogger("videodl.media")


class Cancelled(Exception):
    """Se lanza cuando el usuario cancela un proceso en curso."""


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
        # Códecs: hacen falta para saber si se puede remultiplexar a MP4 sin
        # recodificar (un VP9 «cabe» en MP4 pero no se reproduce en un móvil).
        "vcodec": (video or {}).get("codec_name") or "",
        "acodec": (audio or {}).get("codec_name") or "",
    }


# ---------------------------------------------------------------------------
# ffmpeg
# ---------------------------------------------------------------------------


def run_ffmpeg(
    args: list,
    store,
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
