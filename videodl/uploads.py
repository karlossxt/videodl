"""Guardado de archivos subidos por el usuario, acotado por tamaño."""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import MAX_UPLOAD_MB
from .constants import ALLOWED_AUDIO_SUFFIXES, ALLOWED_SUFFIXES, UPLOAD_CHUNK
from .utils import rmtree_robust, sanitize_filename

logger = logging.getLogger("videodl.uploads")


async def save_media_upload(
    file: UploadFile,
    *,
    dir_prefix: str,
    allowed_suffixes: Iterable[str],
    max_mb: int,
    format_label: str,
    base_name: str = "entrada",
) -> tuple[Path, int]:
    """Guarda un archivo subido en una carpeta temporal.

    Comprueba la extensión, escribe por bloques y aborta si se supera
    ``max_mb``. Devuelve ``(ruta, bytes_escritos)``. En caso de error limpia la
    carpeta y lanza ``HTTPException``.
    """
    name = sanitize_filename(file.filename or base_name)
    suffix = Path(name).suffix.lower()
    if suffix not in set(allowed_suffixes):
        raise HTTPException(
            status_code=400,
            detail=f"Formato no compatible. Sube un archivo {format_label}.",
        )

    tmpdir = Path(tempfile.mkdtemp(prefix=dir_prefix))
    dest = tmpdir / f"{base_name}{suffix}"
    limit = max_mb * 1024 * 1024
    total = 0
    try:
        with dest.open("wb") as fh:
            while True:
                chunk = await file.read(UPLOAD_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise HTTPException(
                        status_code=413,
                        detail=f"El archivo supera el límite de {max_mb} MB.",
                    )
                fh.write(chunk)
    except HTTPException:
        rmtree_robust(tmpdir)
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("No se pudo guardar la subida")
        rmtree_robust(tmpdir)
        raise HTTPException(status_code=500, detail="No se pudo guardar el archivo subido.") from exc
    finally:
        await file.close()

    if total == 0:
        rmtree_robust(tmpdir)
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    return dest, total


async def save_video_upload(file: UploadFile, *, dir_prefix: str) -> tuple[Path, int]:
    """Guarda un vídeo subido (usado por el compresor y los clips)."""
    return await save_media_upload(
        file,
        dir_prefix=dir_prefix,
        allowed_suffixes=ALLOWED_SUFFIXES,
        max_mb=MAX_UPLOAD_MB,
        format_label="de vídeo (MP4, MOV, MKV, WEBM…)",
        base_name="entrada",
    )


async def save_audio_uploads(
    files: Sequence[UploadFile],
    *,
    dir_prefix: str,
    max_mb: int,
) -> tuple[list[Path], int]:
    """Guarda varios audios (o vídeos) subidos en UNA misma carpeta temporal.

    El límite de ``max_mb`` es acumulado entre todos los archivos. Devuelve las
    rutas en el mismo orden en que llegaron. Ante cualquier error limpia la
    carpeta y lanza ``HTTPException``.
    """
    suffixes = set(ALLOWED_AUDIO_SUFFIXES)
    names = []
    for file in files:
        name = sanitize_filename(file.filename or "audio")
        if Path(name).suffix.lower() not in suffixes:
            for pending in files:
                await pending.close()
            raise HTTPException(
                status_code=400,
                detail="Formato no compatible. Sube archivos de audio (MP3, WAV, M4A, OGG, FLAC…).",
            )
        names.append(name)

    tmpdir = Path(tempfile.mkdtemp(prefix=dir_prefix))
    limit = max_mb * 1024 * 1024
    total = 0
    paths: list[Path] = []
    try:
        for index, (file, name) in enumerate(zip(files, names, strict=True)):
            dest = tmpdir / f"entrada{index:02d}{Path(name).suffix.lower()}"
            written = 0
            with dest.open("wb") as fh:
                while True:
                    chunk = await file.read(UPLOAD_CHUNK)
                    if not chunk:
                        break
                    written += len(chunk)
                    total += len(chunk)
                    if total > limit:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Los archivos superan el límite de {max_mb} MB en total.",
                        )
                    fh.write(chunk)
            if written == 0:
                raise HTTPException(status_code=400, detail="Uno de los archivos está vacío.")
            paths.append(dest)
    except HTTPException:
        rmtree_robust(tmpdir)
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("No se pudieron guardar las subidas de audio")
        rmtree_robust(tmpdir)
        raise HTTPException(status_code=500, detail="No se pudieron guardar los archivos subidos.") from exc
    finally:
        for file in files:
            await file.close()

    return paths, total
