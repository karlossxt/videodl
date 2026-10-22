"""Pruebas del reencuadre y la validación de clips (sin ffmpeg)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from videodl import clips
from videodl.clips import clip_filter, clip_validate


def test_vertical_recorta_y_escala():
    vf, w, h = clip_filter("vertical", "media", 1920, 1080)
    assert (w, h) == (720, 1280)
    assert vf and vf.startswith("crop=")


def test_original_horizontal_no_amplia():
    vf, w, h = clip_filter("original", "media", 1280, 720)
    assert vf is None
    assert (w, h) == (1280, 720)


def test_original_vertical_limita_el_ancho():
    # 1080x1920 es 1080p en vertical: no debe quedar en 608x1080.
    vf, w, h = clip_filter("original", "alta", 1080, 1920)
    assert vf is None
    assert (w, h) == (1080, 1920)


def test_original_vertical_grande_baja_el_lado_corto():
    vf, w, h = clip_filter("original", "media", 2160, 3840)
    assert vf == "scale=720:-2,setsar=1"
    assert (w, h) == (720, 1280)


def test_original_pequeno_no_se_toca():
    vf, w, h = clip_filter("original", "media", 640, 360)
    assert vf is None
    assert (w, h) == (640, 360)


def test_square():
    vf, w, h = clip_filter("square", "baja", 1920, 1080)
    assert (w, h) == (480, 480)
    assert vf and "crop=" in vf and "scale=480:480" in vf


# ---------------------------------------------------------------------------
# Validación de la entrada del recortador
# ---------------------------------------------------------------------------


@pytest.fixture()
def _ffmpeg_disponible(monkeypatch):
    monkeypatch.setattr(clips, "FFMPEG_AVAILABLE", True)
    monkeypatch.setattr(clips, "FFPROBE_AVAILABLE", True)
    monkeypatch.setattr(clips, "CLIP_MAX_SECONDS", 300)


def test_clip_validate_acepta_valores_correctos(_ffmpeg_disponible):
    clip_validate("vertical", "media", 0, 30)  # no lanza


def test_clip_validate_rechaza_formato_desconocido(_ffmpeg_disponible):
    with pytest.raises(HTTPException) as exc:
        clip_validate("raro", "media", 0, 30)
    assert exc.value.status_code == 400


def test_clip_validate_rechaza_calidad_desconocida(_ffmpeg_disponible):
    with pytest.raises(HTTPException) as exc:
        clip_validate("vertical", "ultra", 0, 30)
    assert exc.value.status_code == 400


def test_clip_validate_exige_un_segundo_minimo(_ffmpeg_disponible):
    with pytest.raises(HTTPException) as exc:
        clip_validate("vertical", "media", 10, 10.5)
    assert exc.value.status_code == 400


def test_clip_validate_respeta_el_maximo(monkeypatch, _ffmpeg_disponible):
    monkeypatch.setattr(clips, "CLIP_MAX_SECONDS", 10)
    with pytest.raises(HTTPException) as exc:
        clip_validate("vertical", "media", 0, 11)
    assert exc.value.status_code == 400


def test_clip_validate_avisa_si_falta_ffmpeg(monkeypatch):
    monkeypatch.setattr(clips, "FFMPEG_AVAILABLE", False)
    monkeypatch.setattr(clips, "FFPROBE_AVAILABLE", True)
    with pytest.raises(HTTPException) as exc:
        clip_validate("vertical", "media", 0, 30)
    assert exc.value.status_code == 503
