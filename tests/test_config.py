"""Pruebas de la configuración por variables de entorno."""

from videodl import config


def test_env_int_usa_el_defecto_si_no_existe(monkeypatch):
    monkeypatch.delenv("VIDEODL_TEST_INT", raising=False)
    assert config.env_int("VIDEODL_TEST_INT", 42) == 42


def test_env_int_ignora_valores_invalidos(monkeypatch):
    monkeypatch.setenv("VIDEODL_TEST_INT", "no-es-un-numero")
    assert config.env_int("VIDEODL_TEST_INT", 7) == 7


def test_env_int_respeta_el_minimo(monkeypatch):
    monkeypatch.setenv("VIDEODL_TEST_INT", "0")
    assert config.env_int("VIDEODL_TEST_INT", 5, minimum=1) == 5


def test_env_int_respeta_el_maximo(monkeypatch):
    monkeypatch.setenv("VIDEODL_TEST_INT", "999")
    assert config.env_int("VIDEODL_TEST_INT", 5, maximum=100) == 5


def test_env_int_lee_un_valor_valido(monkeypatch):
    monkeypatch.setenv("VIDEODL_TEST_INT", " 12 ")
    assert config.env_int("VIDEODL_TEST_INT", 5) == 12


def test_env_str_limpia_espacios(monkeypatch):
    monkeypatch.setenv("VIDEODL_TEST_STR", "  hola  ")
    assert config.env_str("VIDEODL_TEST_STR") == "hola"


def test_valores_por_defecto_coherentes():
    assert config.MAX_UPLOAD_MB >= 1
    assert config.COMPRESS_MAX_TARGET_MB >= 1
    assert config.CLIP_MAX_SECONDS >= 1
    assert config.MAX_CONCURRENT_JOBS >= 1
    assert config.X264_PRESET in {
        "ultrafast", "superfast", "veryfast", "faster", "fast",
        "medium", "slow", "slower", "veryslow", "placebo",
    }


def test_site_url_no_termina_en_barra():
    assert not config.SITE_URL.endswith("/")


def test_no_quedan_ajustes_de_descarga():
    """El módulo de configuración no debe exponer proxies, cookies ni yt-dlp."""
    for nombre in dir(config):
        if nombre.startswith("_"):
            continue
        assert "YTDLP" not in nombre
        assert "COOKIE" not in nombre
        assert "PROXY" not in nombre
        assert "PLATFORM" not in nombre
