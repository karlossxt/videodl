"""Traducción de errores técnicos a mensajes claros para el usuario."""

from __future__ import annotations

import re


def clean_ytdlp_error(msg: str) -> str:
    """Muestra un mensaje más amigable, sin rutas locales ni ruido técnico."""
    msg = msg.split("\n")[0]
    msg = re.sub(r"^ERROR:\s*", "", msg)
    if "Unsupported URL" in msg:
        return "Esta URL no es compatible con ninguna plataforma soportada."
    if "Private video" in msg or "private" in msg.lower():
        return "El video es privado y no se puede descargar."
    if "Video unavailable" in msg or "unavailable" in msg.lower():
        return "El video no está disponible (puede haber sido eliminado o restringido)."
    if "age" in msg.lower() and "confirm" in msg.lower():
        return "El video tiene restricción de edad y no se puede descargar."
    if "Sign in" in msg or "login" in msg.lower():
        return (
            "La plataforma exige iniciar sesión para servir este vídeo (en YouTube es "
            "su comprobación anti-bot, habitual desde servidores en la nube). Prueba "
            "con cookies exportadas con la sesión iniciada (sección «Cookies» del "
            "README); si ya las tienes, enruta las descargas por un proxy "
            "(YTDLP_PROXY): algunos vídeos no se pueden servir desde la nube."
        )
    if "429" in msg or "Too Many Requests" in msg or "rate limit" in msg.lower():
        return "La plataforma limitó temporalmente las peticiones. Espera un momento e inténtalo de nuevo."
    return f"No se pudo procesar la URL: {msg[:200]}"
