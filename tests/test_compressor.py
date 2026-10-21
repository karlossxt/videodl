"""Pruebas de las decisiones del compresor (sin ffmpeg).

Cubren los dos fallos que se colaron en producción: limitar la altura en vídeos
verticales (dejaba un 1080x1920 en 406x720) y remultiplexar códecs que caben en
MP4 pero no se reproducen en el móvil (VP9, AV1…).
"""

from __future__ import annotations

from videodl.compressor import (
    _mb,
    compatible_mp4,
    pick_short_side,
    scale_args,
)


def test_compatible_mp4_h264_aac():
    assert compatible_mp4({"vcodec": "h264", "acodec": "aac", "has_audio": True})


def test_compatible_mp4_h264_sin_audio():
    assert compatible_mp4({"vcodec": "h264", "acodec": "", "has_audio": False})


def test_compatible_mp4_rechaza_vp9():
    # Cabe en MP4, pero WhatsApp/iOS no lo reproducen.
    assert not compatible_mp4({"vcodec": "vp9", "acodec": "opus", "has_audio": True})


def test_compatible_mp4_rechaza_audio_raro():
    assert not compatible_mp4({"vcodec": "h264", "acodec": "opus", "has_audio": True})
    assert not compatible_mp4({"vcodec": "h264", "acodec": "ac3", "has_audio": True})


def test_compatible_mp4_rechaza_sin_datos():
    assert not compatible_mp4({})


def test_pick_short_side_horizontal():
    assert pick_short_side(1920, 1080, 2000, 0) == 1080
    assert pick_short_side(1920, 1080, 1000, 0) == 720
    assert pick_short_side(1920, 1080, 600, 0) == 480
    assert pick_short_side(1920, 1080, 300, 0) == 360


def test_pick_short_side_vertical_usa_el_ancho():
    # 1080x1920: el lado corto es el ancho, así que 720p son 720x1280.
    assert pick_short_side(1080, 1920, 1000, 0) == 720
    assert pick_short_side(1080, 1920, 300, 0) == 360


def test_pick_short_side_respeta_tope_y_origen():
    assert pick_short_side(1080, 1920, 3000, 720) == 720
    # No se amplía un vídeo pequeño.
    assert pick_short_side(480, 270, 3000, 0) == 270
    # Siempre par.
    assert pick_short_side(1920, 1080, 1000, 721) == 720


def test_scale_args_horizontal():
    assert scale_args(1920, 1080, 720) == ["-vf", "scale=-2:720"]


def test_scale_args_vertical():
    assert scale_args(1080, 1920, 720) == ["-vf", "scale=720:-2"]


def test_scale_args_sin_cambio():
    assert scale_args(1280, 720, 720) == []
    assert scale_args(1920, 1080, 0) == []
    assert scale_args(0, 0, 720) == []


def test_mb_sin_decimales_de_mas():
    assert _mb(16 * 1024 * 1024) == "16"
    assert _mb(int(16.5 * 1024 * 1024)) == "16.5"
