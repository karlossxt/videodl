"""Pruebas de regresión del guardado de archivos subidos."""

from __future__ import annotations

import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from videodl import uploads
from videodl.uploads import save_video_upload


def _subida(data: bytes, filename: str) -> UploadFile:
    return UploadFile(file=BytesIO(data), filename=filename)


def _guardar(file, prefix: str):
    return asyncio.run(save_video_upload(file, dir_prefix=prefix))


def test_guarda_un_video_valido_y_devuelve_el_tamano(monkeypatch, tmp_path):
    monkeypatch.setattr(uploads, "tempfile", type("T", (), {"mkdtemp": lambda **_: str(tmp_path)}))

    path, total = _guardar(_subida(b"contenido-mp4", "clip.mp4"), "videodl_test_")

    assert path.exists()
    assert path.read_bytes() == b"contenido-mp4"
    assert total == len(b"contenido-mp4")


def test_rechaza_extension_no_permitida():
    with pytest.raises(HTTPException) as exc:
        _guardar(_subida(b"hola", "notas.txt"), "videodl_test_")
    assert exc.value.status_code == 400


def test_rechaza_archivo_vacio():
    with pytest.raises(HTTPException) as exc:
        _guardar(_subida(b"", "vacio.mp4"), "videodl_test_")
    assert exc.value.status_code == 400


def test_rechaza_archivo_demasiado_grande(monkeypatch):
    monkeypatch.setattr(uploads, "MAX_UPLOAD_MB", 0)
    with pytest.raises(HTTPException) as exc:
        _guardar(_subida(b"x", "grande.mp4"), "videodl_test_")
    assert exc.value.status_code == 413


def test_limpia_la_carpeta_temporal_si_falla_el_guardado(monkeypatch, tmp_path):
    """Si el disco falla, el error se traduce y no se propaga el detalle interno."""
    # mkdtemp devuelve un archivo, no una carpeta: abrir "entrada.mp4" dentro falla.
    roto = tmp_path / "no-es-una-carpeta"
    roto.write_bytes(b"x")
    monkeypatch.setattr(uploads, "tempfile", type("T", (), {"mkdtemp": lambda **_: str(roto)}))

    with pytest.raises(HTTPException) as exc:
        _guardar(_subida(b"datos", "clip.mp4"), "videodl_test_")
    assert exc.value.status_code == 500
    assert "disco" not in exc.value.detail.lower()
