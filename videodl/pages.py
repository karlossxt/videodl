"""Rutas que sirven las páginas HTML (URLs pensadas para SEO)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from . import views

router = APIRouter(include_in_schema=False)


# ---------------------------------------------------------------------------
# Portada y directorio: se generan desde el catálogo único.
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def page_home(q: str = "", categoria: str = "all"):
    """Portada con buscador, categorías y catálogo de herramientas."""
    return HTMLResponse(views.home_page(q, categoria))


@router.get("/herramientas", response_class=HTMLResponse)
async def page_herramientas(q: str = "", categoria: str = "all"):
    """Directorio reutilizable con todas las herramientas del sitio."""
    return HTMLResponse(views.directory_page(q, categoria))


# ---------------------------------------------------------------------------
# Herramientas que mantienen su propio HTML.
# ---------------------------------------------------------------------------


@router.get("/comprimir-video-whatsapp", response_class=HTMLResponse)
async def page_comprimir():
    """Página dedicada al compresor."""
    return HTMLResponse(views.render_static("comprimir"))


@router.get("/recortar-clip-vertical", response_class=HTMLResponse)
async def page_clips():
    """Página del recortador de clips verticales."""
    return HTMLResponse(views.render_static("clips"))


@router.get("/link-whatsapp", response_class=HTMLResponse)
async def page_whatsapp():
    """Página del generador de enlaces de WhatsApp con código QR."""
    return HTMLResponse(views.render_static("whatsapp"))


@router.get("/legal", response_class=HTMLResponse)
async def page_legal():
    """Aviso legal, privacidad, términos y contacto."""
    return HTMLResponse(views.render_static("legal"))


# ---------------------------------------------------------------------------
# Alias antiguos: redirección permanente a la URL canónica.
# ---------------------------------------------------------------------------


@router.get("/comprimir")
async def alias_comprimir():
    return RedirectResponse("/comprimir-video-whatsapp", status_code=301)


@router.get("/clips-verticales")
@router.get("/clips-twitch-vertical")
async def alias_clips():
    return RedirectResponse("/recortar-clip-vertical", status_code=301)


@router.get("/generador-enlace-whatsapp")
async def alias_whatsapp():
    return RedirectResponse("/link-whatsapp", status_code=301)


# ---------------------------------------------------------------------------
# SEO técnico
# ---------------------------------------------------------------------------


@router.get("/sitemap.xml")
async def sitemap():
    """Sitemap con las URLs canónicas y solo herramientas publicadas."""
    return Response(content=views.sitemap_xml(), media_type="application/xml")


@router.get("/robots.txt")
async def robots():
    return Response(content=views.robots_txt(), media_type="text/plain")
