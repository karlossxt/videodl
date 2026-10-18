"""Proveedor de PO tokens de YouTube (``bgutil-ytdlp-pot-provider``).

YouTube pide a las IPs de nube una prueba de origen (PO token) para servir buena
parte de sus vídeos; sin ella contesta con su comprobación anti-bot («Sign in to
confirm you're not a bot») aunque se manden cookies. El proveedor se instala en la
imagen (ver Dockerfile) en modo «script» con Deno, y aquí solo se ajusta su
tiempo máximo: el plugin corta a los 20 s que bastan en un PC normal, pero un plan
gratuito (0,1 CPU) puede tardar más.

Si el proveedor no está instalado, no pasa nada: yt-dlp sigue funcionando como
antes, sin token.
"""

from __future__ import annotations

import logging

from .config import YTDLP_POT_TIMEOUT

logger = logging.getLogger("videodl.pot")


def configure_pot_provider() -> bool:
    """Amplía el corte de tiempo del proveedor. Devuelve si está instalado."""
    try:
        from yt_dlp_plugins.extractor.getpot_bgutil import BgUtilPTPBase
    except Exception:
        # Falta el plugin (imagen sin él) o cambió de nombre: se sigue sin token.
        logger.debug("Proveedor de PO tokens no instalado; YouTube irá sin firmar")
        return False

    try:
        BgUtilPTPBase._GETPOT_TIMEOUT = float(YTDLP_POT_TIMEOUT)
    except Exception:
        logger.warning("No se pudo ajustar el tiempo del proveedor de PO tokens")
        return True

    logger.info(
        "PO tokens de YouTube: proveedor bgutil activo (máximo %.0f s por token)",
        float(YTDLP_POT_TIMEOUT),
    )
    return True
