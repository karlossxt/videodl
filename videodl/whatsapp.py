"""Router del generador de enlaces de WhatsApp.

El enlace `wa.me` es texto plano, así que se construye en el navegador: el
resultado se ve al instante mientras se escribe y el número no sale del equipo.
Al servidor solo llega el enlace ya montado, y únicamente para dibujar el código
QR (que es la única parte que no se puede hacer a mano en el navegador sin
dependencias).
"""

from __future__ import annotations

import io
import logging
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .models import WhatsAppQrRequest

logger = logging.getLogger("videodl.whatsapp")

router = APIRouter()

# Solo se codifican enlaces de WhatsApp: así este endpoint no sirve como
# generador de QR genérico (ni como proxy para cualquier URL).
WHATSAPP_HOSTS = {
    "wa.me",
    "whatsapp.com",
    "api.whatsapp.com",
    "web.whatsapp.com",
    "chat.whatsapp.com",
}

try:  # segno es Python puro, pero la app debe seguir arrancando sin él.
    import segno

    SEGNO_AVAILABLE = True
except ImportError:  # pragma: no cover - solo si falta la dependencia
    segno = None
    SEGNO_AVAILABLE = False


def validate_whatsapp_link(link: str) -> str:
    """Comprueba que el enlace apunte a WhatsApp y lo devuelve sin espacios."""
    clean = (link or "").strip()
    if not clean:
        raise HTTPException(status_code=400, detail="Falta el enlace de WhatsApp.")

    parsed = urlparse(clean)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in WHATSAPP_HOSTS:
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden generar códigos QR de enlaces de WhatsApp (wa.me).",
        )
    return clean


def make_qr_png(data: str) -> bytes:
    """Devuelve el código QR de ``data`` como PNG en blanco y negro.

    El fondo blanco con módulos negros es lo que garantiza que cualquier cámara
    lo lea: un QR invertido (claro sobre oscuro) falla en muchos lectores.
    """
    # Con mensajes cortos sobra espacio para la corrección de errores alta; con
    # enlaces largos se baja a "M" para que el QR no se vuelva gigantesco e
    # ilegible al escanear desde una pantalla.
    error = "q" if len(data) <= 220 else "m"
    qr = segno.make_qr(data, error=error)
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=8, border=3)
    return buffer.getvalue()


@router.post("/api/whatsapp/qr")
async def whatsapp_qr(payload: WhatsAppQrRequest):
    """Devuelve el código QR (PNG) del enlace de WhatsApp indicado."""
    if not SEGNO_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="El servidor no puede generar códigos QR ahora mismo.",
        )

    link = validate_whatsapp_link(payload.link)
    png = make_qr_png(link)
    return Response(
        content=png,
        media_type="image/png",
        # El QR se calcula al vuelo y no aporta nada guardarlo en cachés intermedias.
        headers={"Cache-Control": "no-store"},
    )
