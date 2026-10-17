"""Pruebas de las opciones que se le pasan a yt-dlp."""

import pytest

from videodl import media


@pytest.fixture()
def _sin_ajustes_ytdlp(monkeypatch):
    """Aísla las variables globales que build_opts lee de config."""
    monkeypatch.setattr(media, "YTDLP_PROXY", "")
    monkeypatch.setattr(media, "YTDLP_EXTRACTOR_ARGS", {})
    monkeypatch.setattr(media, "YTDLP_SOCKET_TIMEOUT", 30)
    monkeypatch.setattr(media, "FFMPEG_AVAILABLE", True)


def test_build_opts_basico(tmp_path, _sin_ajustes_ytdlp):
    opts = media.build_opts("video-720", tmp_path, force_keyframes=False)
    assert opts["outtmpl"].endswith("media.%(ext)s")
    assert "bestvideo[height<=720]" in opts["format"]
    assert opts["socket_timeout"] == 30
    assert "proxy" not in opts
    assert "extractor_args" not in opts


def test_build_opts_incluye_proxy_y_extractor_args(tmp_path, monkeypatch, _sin_ajustes_ytdlp):
    """Las variables de entorno llegan hasta las opciones de yt-dlp."""
    monkeypatch.setattr(media, "YTDLP_PROXY", "http://usuario:clave@proxy:8080")
    monkeypatch.setattr(
        media, "YTDLP_EXTRACTOR_ARGS", {"youtube": {"player_client": ["tv"]}}
    )

    opts = media.build_opts("best", tmp_path)

    assert opts["proxy"] == "http://usuario:clave@proxy:8080"
    assert opts["extractor_args"] == {"youtube": {"player_client": ["tv"]}}
