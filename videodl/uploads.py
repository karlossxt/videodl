"""Guardado de archivos subidos por el usuario, acotado por tamaño."""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterable
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .config import MAX_UPLOAD_MB
from .constants import ALLOWED_SUFFIXES, UPLOAD_CHUNK
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
