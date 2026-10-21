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


def test_format_selector_mantiene_la_prioridad_en_video_horizontal(_sin_ajustes_ytdlp):
    selector = media.format_selector("video-720")
    assert selector.startswith("bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]")
    assert selector.endswith("/best")


def test_format_selector_prueba_el_ancho_en_video_vertical(_sin_ajustes_ytdlp):
    """En un 1080x1920 yt-dlp da height=1920, así que filtrando solo por altura no
    encaja ningún formato y se acababa bajando el mejor."""
    assert "bestvideo[width<=720]" in media.format_selector("video-720")


def test_build_opts_incluye_proxy_y_extractor_args(tmp_path, monkeypatch, _sin_ajustes_ytdlp):
    """Las variables de entorno llegan hasta las opciones de yt-dlp."""
    monkeypatch.setattr(media, "YTDLP_PROXY", "http://usuario:clave@proxy:8080")
    monkeypatch.setattr(
        media, "YTDLP_EXTRACTOR_ARGS", {"youtube": {"player_client": ["tv"]}}
    )

    opts = media.build_opts("best", tmp_path)

    assert opts["proxy"] == "http://usuario:clave@proxy:8080"
    assert opts["extractor_args"] == {"youtube": {"player_client": ["tv"]}}


def test_info_opts_manda_las_cookies(monkeypatch, _sin_ajustes_ytdlp):
    """El análisis usa la misma sesión que la descarga.

    YouTube desde una IP de nube responde con el aviso anti-bot al analizar
    aunque haya cookies configuradas si no se le pasan.
    """
    monkeypatch.setattr(media.cookies, "file", "C:/privado/cookies.txt")

    opts = media.info_opts()

    assert opts["cookiefile"] == "C:/privado/cookies.txt"
    assert opts["skip_download"] is True
    assert opts["noplaylist"] is True


def test_info_opts_sin_cookies(monkeypatch, _sin_ajustes_ytdlp):
    monkeypatch.setattr(media.cookies, "file", None)

    assert "cookiefile" not in media.info_opts()


def test_connection_opts_compartido(monkeypatch, _sin_ajustes_ytdlp):
    """Analizar y descargar comparten cookies, proxy y tiempo de espera."""
    monkeypatch.setattr(media, "YTDLP_PROXY", "http://proxy:8080")
    monkeypatch.setattr(media.cookies, "file", "C:/c.txt")

    opts = media.connection_opts()

    assert opts["proxy"] == "http://proxy:8080"
    assert opts["cookiefile"] == "C:/c.txt"
    assert opts["socket_timeout"] == 30
    assert media.info_opts()["cookiefile"] == "C:/c.txt"

def test_extract_with_retry_reintenta_si_no_hay_formatos(monkeypatch):
    intentos = {"n": 0}

    class YDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            intentos["n"] += 1
            if intentos["n"] < 2:
                raise media.yt_dlp.utils.DownloadError(
                    "ERROR: [dailymotion] xat53s6: No video formats found!"
                )
            return {"id": "xat53s6"}

        def prepare_filename(self, info):
            return "media.mp4"

    monkeypatch.setattr(media.yt_dlp, "YoutubeDL", YDL)
    info, filename = media.extract_with_retry("https://x", {}, download=True)
    assert intentos["n"] == 2
    assert info["id"] == "xat53s6"
    assert filename == "media.mp4"


def test_extract_with_retry_no_repite_errores_de_sesion(monkeypatch):
    intentos = {"n": 0}

    class YDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=False):
            intentos["n"] += 1
            raise media.yt_dlp.utils.DownloadError(
                "ERROR: [youtube] x: Sign in to confirm you are not a bot"
            )

    monkeypatch.setattr(media.yt_dlp, "YoutubeDL", YDL)
    with pytest.raises(media.yt_dlp.utils.DownloadError):
        media.extract_with_retry("https://x", {}, download=False)
    assert intentos["n"] == 1
