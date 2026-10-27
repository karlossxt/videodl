"""Rutas que sirven las páginas HTML (URLs pensadas para SEO).

El español conserva las URLs sin prefijo. El inglés se sirve bajo ``/en/`` y
``/es/...`` redirige a la variante española para evitar contenido duplicado.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from . import image_pages, pdf_pages, views

router = APIRouter(include_in_schema=False)

# Ruta pública -> clave del catálogo de metadatos.
PAGE_ROUTES: dict[str, str] = {
    "/": "home",
    "/herramientas": "directory",
    "/comprimir-video-whatsapp": "comprimir",
    "/recortar-clip-vertical": "clips",
    "/link-whatsapp": "whatsapp",
    "/generador-qr": "generador-qr",
    "/transcribir-audio": "transcribir-audio",
    "/comprimir-imagen": "comprimir-imagen",
    "/convertir-imagen": "convertir-imagen",
    "/redimensionar-imagen": "redimensionar-imagen",
    "/unir-pdf": "unir-pdf",
    "/dividir-pdf": "dividir-pdf",
    "/imagenes-a-pdf": "imagenes-a-pdf",
    "/pdf-a-jpg": "pdf-a-jpg",
    "/comprimir-pdf": "comprimir-pdf",
    "/privacidad": "privacy",
}

IMAGE_KEYS = {"comprimir-imagen", "convertir-imagen", "redimensionar-imagen"}
PDF_KEYS = {"unir-pdf", "dividir-pdf", "imagenes-a-pdf", "pdf-a-jpg", "comprimir-pdf"}

ALIASES: dict[str, str] = {
    "/comprimir": "/comprimir-video-whatsapp",
    "/clips-verticales": "/recortar-clip-vertical",
    "/clips-twitch-vertical": "/recortar-clip-vertical",
    "/generador-enlace-whatsapp": "/link-whatsapp",
    "/legal": "/privacidad",
}


def _render_page(
    key: str,
    lang: str,
    q: str = "",
    categoria: str = "all",
) -> str:
    if key == "home":
        return views.home_page(q, categoria, lang)
    if key == "directory":
        return views.directory_page(q, categoria, lang)
    if key in views.PAGE_FILES:
        return views.render_static(key, lang)
    if key in IMAGE_KEYS:
        return image_pages.render_image_page(key, lang)
    if key in PDF_KEYS:
        return pdf_pages.render_pdf_page(key, lang)
    raise HTTPException(status_code=404, detail="Página no encontrada")


def _page_endpoint(key: str, lang: str):
    async def endpoint(q: str = "", categoria: str = "all") -> HTMLResponse:
        return HTMLResponse(_render_page(key, lang, q, categoria))

    endpoint.__name__ = f"page_{key}_{lang}"
    return endpoint


# Rutas españolas (sin prefijo) e inglesas (con /en).
for _path, _key in PAGE_ROUTES.items():
    router.add_api_route(
        _path,
        _page_endpoint(_key, "es"),
        methods=["GET"],
        response_class=HTMLResponse,
        name=f"page_{_key}_es",
    )
    _en_path = "/en/" if _path == "/" else f"/en{_path}"
    router.add_api_route(
        _en_path,
        _page_endpoint(_key, "en"),
        methods=["GET"],
        response_class=HTMLResponse,
        name=f"page_{_key}_en",
    )


# ---------------------------------------------------------------------------
# Redirecciones de idioma y alias antiguos
# ---------------------------------------------------------------------------


def _target(path: str, request: Request) -> str:
    query = request.url.query
    return f"{path}?{query}" if query else path


@router.get("/en")
async def english_root_redirect(request: Request):
    return RedirectResponse(_target("/en/", request), status_code=301)


@router.get("/es")
async def spanish_root_redirect(request: Request):
    return RedirectResponse(_target("/", request), status_code=301)


@router.get("/es/")
async def spanish_root_slash_redirect(request: Request):
    return RedirectResponse(_target("/", request), status_code=301)


@router.get("/es/{path:path}")
async def spanish_prefixed_redirect(path: str, request: Request):
    base = f"/{path}".rstrip("/") or "/"
    canonical_path = ALIASES.get(base, base)
    return RedirectResponse(_target(canonical_path, request), status_code=301)


for _alias, _canonical in ALIASES.items():
    async def _alias_es(request: Request, canonical: str = _canonical):
        return RedirectResponse(_target(canonical, request), status_code=301)

    async def _alias_en(request: Request, canonical: str = _canonical):
        return RedirectResponse(
            _target(f"/en{canonical}", request), status_code=301
        )

    router.add_api_route(
        _alias,
        _alias_es,
        methods=["GET"],
        name=f"alias_es_{_alias.strip('/')}",
    )
    router.add_api_route(
        f"/en{_alias}",
        _alias_en,
        methods=["GET"],
        name=f"alias_en_{_alias.strip('/')}",
    )


# ---------------------------------------------------------------------------
# SEO técnico
# ---------------------------------------------------------------------------


@router.get("/sitemap.xml")
async def sitemap():
    """Sitemap con las URLs canónicas de ambos idiomas."""
    return Response(content=views.sitemap_xml(), media_type="application/xml")


@router.get("/en/sitemap.xml")
async def sitemap_en():
    return RedirectResponse("/sitemap.xml", status_code=301)


@router.get("/robots.txt")
async def robots():
    return Response(content=views.robots_txt(), media_type="text/plain")
