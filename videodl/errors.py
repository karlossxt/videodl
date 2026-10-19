"""Traducción de errores técnicos a mensajes claros para el usuario."""

from __future__ import annotations

import re

# YouTube rota cada cierto tiempo las cookies de la sesión exportada. yt-dlp lo
# avisa con un WARNING («The provided YouTube account cookies are no longer
# valid») y sigue como anónimo, así que el error que acaba viendo el usuario es
# el anti-bot y parece un problema de configuración cuando en realidad es que el
# fichero ya no autentica. Se recuerda el aviso para poder explicarlo.
_AVISO_COOKIES_ROTADAS = "cookies are no longer valid"
_cookies_rotadas = False


def aviso_cookies_rotadas(mensaje: str) -> bool:
    """¿Es el aviso de cookies rotadas de yt-dlp? Si lo es, se recuerda."""
    global _cookies_rotadas
    if _AVISO_COOKIES_ROTADAS in mensaje.lower():
        _cookies_rotadas = True
        return True
    return False


def cookies_rotadas() -> bool:
    """¿Se ha detectado que YouTube invalidó las cookies de la sesión?"""
    return _cookies_rotadas


def olvidar_cookies_rotadas() -> None:
    """Borra el recuerdo del aviso (al volver a cargar la configuración)."""
    global _cookies_rotadas
    _cookies_rotadas = False


def clean_ytdlp_error(msg: str, url: str = "") -> str:
    """Muestra un mensaje más amigable, sin rutas locales ni ruido técnico.

    Si se pasa ``url`` y el fallo era de sesión, se añade qué falta exactamente
    (ver ``_pista_cookies``), que es lo que de verdad ayuda cuando una plataforma
    pide cuenta y no se sabe si el tarro llegó, si trae sesión o si la rechazan.
    """
    return _pista_cookies(_mensaje(msg), msg, url)


def _mensaje(msg: str) -> str:
    """Traducción del error de yt-dlp, sin la pista de cookies."""
    msg = msg.split("\n")[0]
    msg = re.sub(r"^ERROR:\s*", "", msg)
    low = msg.lower()
    if "Unsupported URL" in msg:
        return "Esta URL no es compatible con ninguna plataforma soportada."
    if "Private video" in msg or "private" in low:
        return "El video es privado y no se puede descargar."
    if "Video unavailable" in msg or "unavailable" in low:
        return "El video no está disponible (puede haber sido eliminado o restringido)."
    # Ojo: no basta con buscar "age", porque aparece en palabras como "webpage" y
    # marcaba como restricción de edad cualquier fallo genérico (el aviso de yt-dlp
    # termina en "Confirm you are on the latest version").
    if "age-restricted" in low or "age restricted" in low or "confirm your age" in low:
        return "El video tiene restricción de edad y no se puede descargar."
    if "Sign in" in msg or "login" in low:
        if cookies_rotadas():
            return (
                "YouTube invalidó las cookies de tu sesión (las rota cada cierto "
                "tiempo): el fichero es correcto, pero ya no autentica, así que la "
                "descarga sale como anónima y YouTube responde con su comprobación "
                "anti-bot. Vuelve a exportar cookies.txt con la sesión iniciada, "
                "actualiza el Secret File y reintenta."
            )
        return (
            "La plataforma exige iniciar sesión para servir este vídeo (en YouTube es "
            "su comprobación anti-bot, habitual desde servidores en la nube). Prueba "
            "con cookies exportadas con la sesión iniciada (sección «Cookies» del "
            "README); si ya las tienes, enruta las descargas por un proxy "
            "(YTDLP_PROXY): algunos vídeos no se pueden servir desde la nube."
        )
    if "429" in msg or "Too Many Requests" in msg or "rate limit" in low:
        return "La plataforma limitó temporalmente las peticiones. Espera un momento e inténtalo de nuevo."
    if "unable to access the reddit api" in low:
        return (
            "Reddit bloquea la IP del servidor para su API, así que ni con cookies "
            "válidas se puede: hay que salir por un proxy residencial "
            "(`YTDLP_PROXY`). Consulta las secciones «Cookies» y «Proxy» del README."
        )
    if "authentication is required" in low:
        return (
            "Esta plataforma ya no sirve los vídeos a quien no tenga la sesión "
            "iniciada (Reddit cerró su API pública). El administrador debe añadir "
            "cookies de esa web exportadas con la sesión abierta: consulta la "
            "sección «Cookies» del README."
        )
    return f"No se pudo procesar la URL: {msg[:200]}"


def _pista_cookies(detalle: str, msg: str, url: str) -> str:
    """Concreta qué pasa con las cookies de esa web cuando piden sesión.

    Sin esto, «añade cookies» no distingue los tres casos posibles y es fácil
    subir un fichero que no cambia nada: sin cookies de esa web, con cookies pero
    exportadas sin cuenta, o con sesión y aun así rechazadas por la IP.
    """
    if not url or cookies_rotadas():
        return detalle

    low = msg.lower()
    if "authentication is required" not in low and "sign in" not in low:
        return detalle

    from .config import cookie_status

    total, sesion = cookie_status(url)
    if not total:
        pista = (
            "Ahora mismo no hay ninguna cookie de esta web cargada: falta su "
            "fichero (uno por plataforma, p. ej. reddit.txt)."
        )
    elif not sesion:
        pista = (
            f"Hay {_cuantas(total)} de esta web, pero ninguna parece de sesión: "
            "se exportaron sin la cuenta iniciada."
        )
    else:
        pista = (
            f"Hay {_cuantas(total)} de esta web con sesión; si aun así falla, la "
            "plataforma está rechazando la sesión desde esta IP."
        )
    return f"{detalle} {pista}"


def _cuantas(total: int) -> str:
    """«1 cookie» / «37 cookies», para que la pista se lea en castellano."""
    return "1 cookie" if total == 1 else f"{total} cookies"

