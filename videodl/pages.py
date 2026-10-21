"""Rutas que sirven las páginas HTML (URLs pensadas para SEO)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from .paths import STATIC_DIR

router = APIRouter(include_in_schema=False)


@router.get("/comprimir-video-whatsapp")
@router.get("/comprimir")
async def page_comprimir():
    """Página dedicada al compresor."""
    return FileResponse(STATIC_DIR / "comprimir.html")


@router.get("/herramientas")
async def page_herramientas():
    """Directorio con todas las herramientas del sitio."""
    return FileResponse(STATIC_DIR / "herramientas.html")


@router.get("/recortar-clip-vertical")
@router.get("/clips-verticales")
@router.get("/clips-twitch-vertical")
async def page_clips():
    """Página del recortador de clips verticales."""
    return FileResponse(STATIC_DIR / "clips.html")


@router.get("/link-whatsapp")
@router.get("/generador-enlace-whatsapp")
async def page_whatsapp():
    """Página del generador de enlaces de WhatsApp con código QR."""
    return FileResponse(STATIC_DIR / "whatsapp.html")


@router.get("/legal")
async def page_legal():
    """Aviso legal, privacidad, términos y contacto."""
    return FileResponse(STATIC_DIR / "legal.html")
