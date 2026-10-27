"""Transcripción de audio a texto con faster-whisper (opcional).

La dependencia no forma parte de ``requirements.txt``: descargar modelos y
ejecutar Whisper consume CPU y RAM. Si falta ``faster-whisper``, la página sigue
publicada y la API responde 503 con una explicación. La app funciona igual.
"""

from __future__ import annotations

import logging
import re
import threading
import unicodedata
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from .config import (
    FFMPEG,
    FFMPEG_AVAILABLE,
    FFPROBE_AVAILABLE,
    TRANSCRIBE_BEAM_SIZE,
    TRANSCRIBE_COMPUTE_TYPE,
    TRANSCRIBE_DEVICE,
    TRANSCRIBE_LANGUAGE,
    TRANSCRIBE_MAX_MB,
    TRANSCRIBE_MAX_SECONDS,
    TRANSCRIBE_MODEL,
)
from .constants import ALLOWED_AUDIO_SUFFIXES
from .media import Cancelled, ffprobe_meta, run_ffmpeg
from .stores import transcriptions
from .tasks import spawn_job
from .uploads import save_media_upload
from .utils import public_error, rmtree_robust, sanitize_filename

logger = logging.getLogger("videodl.transcribe")

router = APIRouter()

try:  # Dependencia opcional y pesada.
    from faster_whisper import WhisperModel

    FASTER_WHISPER_AVAILABLE = True
except ImportError:  # pragma: no cover - solo si falta la dependencia
    WhisperModel = None
    FASTER_WHISPER_AVAILABLE = False

TRANSCRIBE_AVAILABLE = FASTER_WHISPER_AVAILABLE and FFMPEG_AVAILABLE and FFPROBE_AVAILABLE

_MODEL_LOCK = threading.Lock()
_MODELS: dict[tuple[str, str, str], object] = {}

_LANGUAGE_RE = re.compile(r"^[a-z]{2,3}$")
_SUPPORTED_FORMATS = {"txt", "srt", "vtt"}


# ---------------------------------------------------------------------------
# Modelo y validaciones
# ---------------------------------------------------------------------------


def load_model():
    """Carga el modelo una sola vez y lo reutiliza entre trabajos."""
    if not FASTER_WHISPER_AVAILABLE:
        raise RuntimeError(
            "La transcripción no está instalada en el servidor. "
            "Instala faster-whisper para activarla."
        )

    key = (TRANSCRIBE_MODEL, TRANSCRIBE_DEVICE, TRANSCRIBE_COMPUTE_TYPE)
    with _MODEL_LOCK:
        model = _MODELS.get(key)
        if model is None:
            try:
                model = WhisperModel(
                    TRANSCRIBE_MODEL,
                    device=TRANSCRIBE_DEVICE,
                    compute_type=TRANSCRIBE_COMPUTE_TYPE,
                )
            except Exception as exc:  # noqa: BLE001 - fallo de librería nativa o descarga
                logger.exception("No se pudo cargar el modelo %s", TRANSCRIBE_MODEL)
                raise RuntimeError(
                    "No se pudo cargar el modelo de transcripción. Revisa el espacio "
                    "en disco y la conexión para descargarlo la primera vez."
                ) from exc
            _MODELS[key] = model
        return model


def normalize_language(value: str | None) -> str | None:
    """Devuelve un código ISO 639 válido, ``None`` para detección automática."""
    cleaned = (value or "").strip().lower()
    if cleaned in {"", "auto", "automático", "automatico"}:
        return TRANSCRIBE_LANGUAGE or None
    if not _LANGUAGE_RE.fullmatch(cleaned):
        raise HTTPException(
            status_code=400,
            detail="Código de idioma no válido. Usa «auto» o un código como «es».",
        )
    return cleaned


def format_timestamp(seconds: float, *, decimal: str = ",") -> str:
    """Formatea segundos como ``HH:MM:SS,mmm`` (SRT) o ``HH:MM:SS.mmm`` (VTT)."""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal}{millis:03d}"


def build_txt(segments: list[dict]) -> str:
    """Texto plano: une los segmentos y normaliza espacios."""
    parts = [re.sub(r"\s+", " ", str(segment.get("text", ""))).strip() for segment in segments]
    text = " ".join(part for part in parts if part).strip()
    return f"{text}\n" if text else ""


def build_srt(segments: list[dict]) -> str:
    """Subtítulos SRT con todos los segmentos con texto."""
    blocks: list[str] = []
    for index, segment in enumerate(segments, start=1):
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = float(segment.get("start") or 0)
        end = float(segment.get("end") or start)
        if end <= start:
            end = start + 0.5
        blocks.append(
            f"{index}\n"
            f"{format_timestamp(start)} --> {format_timestamp(end)}\n"
            f"{text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def build_vtt(segments: list[dict]) -> str:
    """Subtítulos WebVTT con todos los segmentos con texto."""
    blocks: list[str] = ["WEBVTT"]
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = float(segment.get("start") or 0)
        end = float(segment.get("end") or start)
        if end <= start:
            end = start + 0.5
        blocks.append(
            f"{format_timestamp(start, decimal='.')} --> "
            f"{format_timestamp(end, decimal='.')}\n{text}"
        )
    return "\n\n".join(blocks) + "\n"


def _content_disposition(filename: str) -> str:
    """Cabecera segura para nombres con acentos (RFC 5987 + ASCII de reserva)."""
    ascii_name = (
        unicodedata.normalize("NFKD", filename)
        .encode("ascii", "ignore")
        .decode("ascii")
        .replace('"', "")
        or "transcripcion.txt"
    )
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


# ---------------------------------------------------------------------------
# Procesamiento
# ---------------------------------------------------------------------------


def transcribe_audio(audio_path: Path, language: str | None):
    """Devuelve ``(segmentos, información)`` del modelo para el audio indicado."""
    model = load_model()

    # Se pasa un array float32 en lugar de la ruta: faster-whisper 1.2.1 usa
    # PyAV para decodificar rutas y esa ruta se rompe con PyAV 19. Como ffmpeg
    # ya dejó un WAV mono a 16 kHz, leerlo con la librería estándar es más
    # rápido, no añade otra dependencia nativa y evita el problema.
    import wave

    import numpy as np

    with wave.open(str(audio_path), "rb") as wav:
        if (
            wav.getnchannels() != 1
            or wav.getframerate() != 16000
            or wav.getsampwidth() != 2
        ):
            raise RuntimeError("El audio extraído no tiene el formato esperado.")
        frames = wav.readframes(wav.getnframes())
    audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0

    return model.transcribe(
        audio,
        language=language,
        beam_size=TRANSCRIBE_BEAM_SIZE,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,
        word_timestamps=False,
    )


def extract_audio(src: Path, dest: Path, job_id: str, duration: float) -> None:
    """Extrae una pista mono a 16 kHz, el formato que espera Whisper."""
    args = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-progress", "pipe:1", "-nostats",
        "-i", str(src),
        "-vn", "-map", "0:a:0",
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(dest),
    ]
    transcriptions.update(
        job_id, status="extracting", percent=2.0, message="Extrayendo el audio…"
    )
    code = run_ffmpeg(args, transcriptions, job_id, duration, 2.0, 10.0)
    if code != 0 or not dest.exists() or dest.stat().st_size == 0:
        raise RuntimeError("No se pudo extraer el audio del archivo. Prueba con otro formato.")


def _run_transcribe_job(job_id: str, src: Path) -> None:
    """Trabajo en segundo plano: analiza, extrae el audio y transcribe."""
    tmpdir = src.parent
    try:
        transcriptions.update(
            job_id, status="probing", percent=0.0, message="Analizando el archivo…"
        )
        meta = ffprobe_meta(src)
        if not meta.get("has_audio"):
            raise RuntimeError("El archivo no contiene ninguna pista de audio.")

        duration = float(meta.get("duration") or 0)
        if duration <= 0:
            raise RuntimeError("No se pudo leer la duración del audio.")
        if duration > TRANSCRIBE_MAX_SECONDS:
            minutes = max(1, TRANSCRIBE_MAX_SECONDS // 60)
            raise RuntimeError(
                f"El audio dura demasiado. El máximo es de {minutes} minutos."
            )

        audio = tmpdir / "audio.wav"
        extract_audio(src, audio, job_id, duration)

        job = transcriptions.get(job_id) or {}
        language = job.get("language") or TRANSCRIBE_LANGUAGE or None
        transcriptions.update(
            job_id,
            status="transcribing",
            percent=10.0,
            message="Cargando el modelo y transcribiendo…",
        )
        segment_iter, info = transcribe_audio(audio, language)

        collected: list[dict] = []
        for segment in segment_iter:
            current = transcriptions.get(job_id)
            if current and current.get("cancel"):
                raise Cancelled()

            text = (getattr(segment, "text", "") or "").strip()
            start = float(getattr(segment, "start", 0) or 0)
            end = float(getattr(segment, "end", start) or start)
            if text:
                collected.append(
                    {"start": round(start, 3), "end": round(end, 3), "text": text}
                )

            if duration > 0:
                percent = 10.0 + 85.0 * min(max(end, 0) / duration, 1)
                transcriptions.update(job_id, percent=round(min(percent, 95.0), 1))

        if not collected:
            raise RuntimeError(
                "No se detectó voz en el audio. Comprueba que el volumen sea audible "
                "y que el archivo no esté en silencio."
            )

        detected = getattr(info, "language", None) or language or "desconocido"
        probability = getattr(info, "language_probability", None)
        text = build_txt(collected).strip()

        transcriptions.update(
            job_id,
            status="finished",
            percent=100.0,
            message="¡Listo!",
            text=text,
            segments=collected,
            segments_count=len(collected),
            language=detected,
            language_probability=(
                round(float(probability), 4) if probability is not None else None
            ),
            duration=round(duration, 1),
            tmpdir=None,
        )
        rmtree_robust(tmpdir)
    except Cancelled:
        rmtree_robust(tmpdir)
        transcriptions.update(
            job_id, status="cancelled", message="Cancelado", tmpdir=None
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error al transcribir %s", job_id)
        rmtree_robust(tmpdir)
        transcriptions.update(
            job_id,
            status="error",
            error=public_error(exc, "No se pudo transcribir el audio."),
            message="Error",
            tmpdir=None,
        )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@router.get("/api/transcribe/options")
async def transcribe_options():
    """Capacidades públicas de la transcripción."""
    return {
        "available": TRANSCRIBE_AVAILABLE,
        "model": TRANSCRIBE_MODEL,
        "max_seconds": TRANSCRIBE_MAX_SECONDS,
        "max_upload_mb": TRANSCRIBE_MAX_MB,
        "language": TRANSCRIBE_LANGUAGE or "auto",
    }


@router.post("/api/transcribe")
async def create_transcription(
    file: UploadFile = File(...),
    language: str = Form(""),
):
    """Sube un audio o vídeo y crea un trabajo de transcripción."""
    if not TRANSCRIBE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                "La transcripción no está activada en este servidor. "
                "Instala faster-whisper y vuelve a intentarlo."
            ),
        )

    chosen_language = normalize_language(language)
    src, total = await save_media_upload(
        file,
        dir_prefix="videodl_tr_",
        allowed_suffixes=ALLOWED_AUDIO_SUFFIXES,
        max_mb=TRANSCRIBE_MAX_MB,
        format_label="de audio o vídeo (MP3, WAV, M4A, MP4, MOV…)",
        base_name="entrada",
    )

    transcriptions.cleanup_stale()
    job_id = transcriptions.new(
        input_name=sanitize_filename(file.filename or "audio"),
        input_size=total,
        output_size=0,
        message="Preparando…",
        percent=0.0,
        text=None,
        segments=[],
        segments_count=0,
        language=chosen_language,
        language_probability=None,
        duration=0,
        tmpdir=str(src.parent),
    )
    try:
        spawn_job(
            _run_transcribe_job,
            job_id,
            src,
            busy_detail=(
                "El servidor está procesando demasiados archivos ahora mismo. "
                "Inténtalo de nuevo en unos segundos."
            ),
        )
    except HTTPException:
        transcriptions.delete(job_id)
        rmtree_robust(src.parent)
        raise

    return {"id": job_id}


@router.get("/api/transcribe/{job_id}")
async def transcribe_status(job_id: str):
    """Estado, progreso y texto de una transcripción."""
    job = transcriptions.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return {
        key: job.get(key)
        for key in (
            "id",
            "status",
            "percent",
            "message",
            "input_name",
            "input_size",
            "duration",
            "language",
            "language_probability",
            "segments_count",
            "text",
            "error",
        )
    }


@router.get("/api/transcribe/{job_id}/file")
async def transcribe_file(job_id: str, format: str = "txt"):
    """Descarga la transcripción en TXT, SRT o VTT."""
    output = (format or "txt").strip().lower()
    if output not in _SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail="Formato no válido. Usa txt, srt o vtt.")

    job = transcriptions.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if job["status"] == "cancelled":
        raise HTTPException(status_code=409, detail="La transcripción fue cancelada")
    if job["status"] != "finished":
        raise HTTPException(status_code=409, detail="La transcripción todavía no ha terminado")

    segments = job.get("segments") or []
    if not segments:
        raise HTTPException(status_code=410, detail="La transcripción ya no está disponible")

    builders = {"txt": build_txt, "srt": build_srt, "vtt": build_vtt}
    media_types = {
        "txt": "text/plain; charset=utf-8",
        "srt": "application/x-subrip; charset=utf-8",
        "vtt": "text/vtt; charset=utf-8",
    }
    base = Path(job.get("input_name") or "transcripcion").stem or "transcripcion"
    filename = f"{sanitize_filename(base)}.{output}"

    return Response(
        content=builders[output](segments).encode("utf-8"),
        media_type=media_types[output],
        headers={
            "Content-Disposition": _content_disposition(filename),
            "Cache-Control": "no-store",
        },
    )


@router.post("/api/transcribe/{job_id}/cancel")
async def cancel_transcription(job_id: str):
    """Solicita cancelar una transcripción en curso."""
    status = transcriptions.request_cancel(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    if status in ("finished", "error", "cancelled"):
        return {"ok": False, "status": status}
    return {"ok": True, "status": "cancelling"}
