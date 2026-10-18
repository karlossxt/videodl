"""Pruebas del ajuste del proveedor de PO tokens de YouTube (``bgutil``)."""

import sys

from videodl import config, pot


def test_amplia_el_corte_de_tiempo_del_plugin():
    """El plugin corta a 20 s, poco para un plan gratuito: se amplía."""
    from yt_dlp_plugins.extractor.getpot_bgutil import BgUtilPTPBase

    original = BgUtilPTPBase._GETPOT_TIMEOUT
    try:
        assert pot.configure_pot_provider() is True
        obtenido = BgUtilPTPBase._GETPOT_TIMEOUT
        assert obtenido == float(config.YTDLP_POT_TIMEOUT)
    finally:
        BgUtilPTPBase._GETPOT_TIMEOUT = original


def test_sin_plugin_no_falla_ni_cambia_nada(monkeypatch):
    """Si el proveedor no está instalado, la app debe seguir igual (sin token)."""
    monkeypatch.setitem(sys.modules, "yt_dlp_plugins.extractor.getpot_bgutil", None)

    assert pot.configure_pot_provider() is False
