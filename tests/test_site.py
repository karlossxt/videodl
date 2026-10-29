"""Pruebas del catálogo, la portada, el directorio y el SEO técnico."""

from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

from videodl import views
from videodl.catalog import CATEGORIES, TOOLS, available_tools

PAGES = (
    "/",
    "/herramientas",
    "/comprimir-video-whatsapp",
    "/recortar-clip-vertical",
    "/transcribir-audio",
    "/comprimir-imagen",
    "/convertir-imagen",
    "/redimensionar-imagen",
    "/generador-qr",
    "/link-whatsapp",
    "/privacidad",
)


class _Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs):
        self.items.append((tag, dict(attrs)))


def parse_tags(text: str) -> list[tuple[str, dict[str, str | None]]]:
    parser = _Tags()
    parser.feed(text)
    return parser.items


def tool_cards(text: str) -> list[dict[str, str | None]]:
    return [attrs for _, attrs in parse_tags(text) if "data-tool-card" in attrs]


def visible_categories(text: str) -> set[str]:
    return {
        str(card["data-category"])
        for card in tool_cards(text)
        if "hidden" not in card
    }


def ids(text: str) -> list[str]:
    return [
        str(attrs["id"])
        for _, attrs in parse_tags(text)
        if "id" in attrs and attrs["id"]
    ]


def internal_links(text: str) -> set[str]:
    return {
        href
        for tag, attrs in parse_tags(text)
        if tag == "a"
        and (href := attrs.get("href"))
        and href.startswith("/")
        and not href.startswith("//")
    }


# ---------------------------------------------------------------------------
# Catálogo único
# ---------------------------------------------------------------------------


def test_catalogo_coherente_y_sin_duplicados():
    slugs = [tool.slug for tool in TOOLS]
    assert len(slugs) == len(set(slugs))

    categories = {category.slug for category in CATEGORIES}
    assert all(tool.category in categories for tool in TOOLS)
    assert categories == {"video", "audio", "imagenes", "pdf", "productividad"}

    # Cada categoría tiene al menos una entrada (disponible o próxima).
    assert {tool.category for tool in TOOLS} == categories

    # Las herramientas próximas no tienen ruta ni se pueden enlazar.
    for tool in TOOLS:
        if tool.status == "soon":
            assert tool.route is None
            assert not tool.available
        else:
            assert tool.available
            assert tool.route and tool.route.startswith("/")

    # Toda herramienta publicada tiene metadatos y la misma URL en el catálogo,
    # la ruta y su canonical.
    published = {
        meta.tool_slug: meta for meta in views.PAGE_META.values() if meta.tool_slug
    }
    for tool in available_tools():
        assert tool.slug in published
        assert published[tool.slug].path == tool.route


def test_herramientas_disponibles_tienen_pagina_real(client):
    for tool in available_tools():
        res = client.get(tool.route)
        assert res.status_code == 200, tool.route
        assert f'<link rel="canonical" href="{views.canonical(tool.route)}"' in res.text


def test_footer_incluye_credito_oncenueve(client):
    response = client.get("/")
    assert response.status_code == 200
    assert 'href="https://oncenueve.com.mx"' in response.text
    assert 'rel="noopener noreferrer"' in response.text
    assert "Desarrollado por" in response.text
    assert ">OnceNueve</a>" in response.text


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("/comprimir", "/comprimir-video-whatsapp"),
        ("/clips-verticales", "/recortar-clip-vertical"),
        ("/clips-twitch-vertical", "/recortar-clip-vertical"),
        ("/generador-enlace-whatsapp", "/link-whatsapp"),
    ],
)
def test_alias_redirigen_a_la_url_canonica(client, alias, canonical):
    res = client.get(alias, follow_redirects=False)
    assert res.status_code == 301
    assert res.headers["location"] == canonical


def test_herramientas_proximas_no_publican_paginas(client):
    for tool in TOOLS:
        if tool.status == "soon":
            assert client.get(f"/{tool.slug}").status_code == 404


# ---------------------------------------------------------------------------
# Portada y directorio
# ---------------------------------------------------------------------------


def test_portada_tiene_hero_buscador_y_categorias(client):
    text = client.get("/").text

    assert "Todas tus herramientas en un solo lugar" in text
    assert "Convierte, comprime y edita archivos gratis, sin instalaciones" in text
    assert 'data-tool-search' in text
    assert 'name="q"' in text
    assert 'action="/"' in text
    for category in ("Vídeo", "Audio", "Imágenes", "PDF", "Productividad"):
        assert category in text

    home_cards = tool_cards(text)
    # Las destacadas se repiten en el catálogo completo, pero no hay datos nuevos.
    assert len({card["data-search"] for card in home_cards}) == len(TOOLS)
    assert len(visible_categories(text)) == len(CATEGORIES)

    # Los chips del filtro se distinguen de las tarjetas, que también llevan
    # data-category pero deben conservar su enlace.
    chips = [
        attrs
        for tag, attrs in parse_tags(text)
        if tag == "a" and "data-category-chip" in attrs
    ]
    assert len(chips) == len(CATEGORIES) + 1
    assert all("data-category" in chip for chip in chips)
    assert all("data-category-chip" not in card for card in home_cards)


def test_portada_enlaza_solo_herramientas_implementadas(client):
    text = client.get("/").text

    for tool in available_tools():
        assert f'href="{tool.route}"' in text

    for tool in TOOLS:
        if tool.status == "soon":
            assert f'href="/{tool.slug}"' not in text

    # La etiqueta Próximamente solo aparece en las tarjetas no publicadas.
    soon_cards = [tool for tool in TOOLS if tool.status == "soon"]
    assert text.count('class="tool-badge soon"') == len(soon_cards)


def test_directorio_reutiliza_el_mismo_catalogo(client):
    home = client.get("/").text
    directory = client.get("/herramientas").text

    assert len({card["data-search"] for card in tool_cards(home)}) == len(TOOLS)
    assert len(tool_cards(directory)) == len(TOOLS)
    for tool in TOOLS:
        assert tool.name in directory
    assert "Directorio de herramientas" in directory
    assert "/tools.js" in directory


def test_busqueda_en_servidor_filtra_por_texto_y_categoria(client):
    pdf = client.get("/?q=pdf").text
    assert visible_categories(pdf) == {"pdf"}
    assert f"{len(views.filter_tools('pdf'))} herramientas" in pdf

    clip = client.get("/herramientas?q=clip").text
    assert visible_categories(clip) == {"video"}
    assert "1 herramienta" in clip

    audio = client.get("/herramientas?categoria=audio").text
    assert visible_categories(audio) == {"audio"}
    assert 'class="category-chip is-active"' in audio

    empty = client.get("/?q=no-existe-esta-herramienta").text
    assert visible_categories(empty) == set()
    assert "0 herramientas" in empty


def test_buscador_instantaneo_conectado_al_html(client):
    text = client.get("/").text
    assert "/tools.js" in text
    js = (views.STATIC_DIR / "tools.js").read_text(encoding="utf-8")
    assert "data-tool-search" in js
    assert "dataset.search" in js
    assert "data-tools-count" in js
    assert "aria-current" in js

    # El selector de chips no puede abarcar las tarjetas: si lo hace, el clic
    # en una herramienta se intercepta como filtro y no navega.
    assert 'querySelectorAll("[data-category-chip]")' in js
    assert 'querySelectorAll("[data-category]")' not in js

    # Solo la cuadrícula del catálogo se filtra: las destacadas no se duplican
    # en el recuento ni desaparecen al escribir en el buscador.
    grids = re.findall(r'<div class="[^"]*tools-grid[^"]*"[^>]*>', text)
    assert len([grid for grid in grids if "data-tools-grid" in grid]) == 1

    # Cada tarjeta lleva el texto que usa el filtro, sin depender de otra lista.
    for card in tool_cards(text):
        assert card["data-search"]
        assert card["data-category"]


# ---------------------------------------------------------------------------
# Navegación móvil y accesibilidad básica
# ---------------------------------------------------------------------------


def test_navegacion_movil_y_tema_compartidos(client):
    for path in PAGES:
        text = client.get(path).text
        assert 'data-nav-toggle' in text
        assert 'aria-controls="site-menu"' in text
        assert 'id="site-menu"' in text
        assert 'data-theme-toggle' in text
        assert 'aria-pressed=' in text
        assert 'href="#main"' in text
        assert 'id="main"' in text
        assert "/site.js" in text

    js = (views.STATIC_DIR / "site.js").read_text(encoding="utf-8")
    assert "aria-expanded" in js
    assert "is-open" in js
    assert "Escape" in js
    assert "localStorage" in js
    assert 'classList.add("js")' in js

    css = (views.STATIC_DIR / "style.css").read_text(encoding="utf-8")
    assert '@media (max-width: 760px)' in css
    assert ".site-menu.is-open" in css
    assert 'html[data-theme="light"]' in css
    assert "html:not(.js)" in css


def test_accesibilidad_basica_de_las_paginas(client):
    for path in PAGES:
        text = client.get(path).text
        assert '<html lang="es"' in text
        assert text.count("<h1") == 1, path
        assert "viewport" in text

        page_ids = ids(text)
        assert len(page_ids) == len(set(page_ids)), path

        assert 'href="#"' not in text
        assert "javascript:" not in text

        for link in internal_links(text):
            target = link.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue
            assert client.get(target).status_code < 400, (path, target)


def test_buscador_tiene_etiqueta_y_controles_accesibles(client):
    text = client.get("/").text
    assert 'for="tool-search"' in text
    assert 'id="tool-search"' in text
    assert 'role="search"' in text
    assert 'role="status"' in text
    assert 'aria-live="polite"' in text
    assert 'type="submit"' in text
    assert ">Buscar</button>" in text


# ---------------------------------------------------------------------------
# SEO técnico
# ---------------------------------------------------------------------------


def test_canonical_y_open_graph_en_todas_las_paginas(client):
    for path in PAGES:
        text = client.get(path).text
        assert '<link rel="canonical"' in text
        assert 'property="og:title"' in text
        assert 'property="og:description"' in text
        assert 'property="og:url"' in text
        assert 'property="og:site_name" content="Fastools"' in text
        assert '<meta name="description"' in text
        assert "<title>" in text


def test_meta_del_directorio_no_presenta_como_pendientes_las_imagenes(client):
    description = views.PAGE_META["directory"].description
    assert "imágenes" in description
    assert "próximas utilidades de audio, imágenes" not in description
    assert description in client.get("/herramientas").text


def test_site_url_de_entorno_se_usa_en_canonical_sitemap_y_robots(client, monkeypatch):
    monkeypatch.setattr(views.config, "SITE_URL", "https://example.com")

    home = client.get("/").text
    assert '<link rel="canonical" href="https://example.com/" />' in home
    assert 'property="og:url" content="https://example.com/"' in home

    sitemap = client.get("/sitemap.xml").text
    assert "https://example.com/herramientas" in sitemap
    assert "<loc>https://example.com/</loc>" in sitemap

    robots = client.get("/robots.txt").text
    assert "Sitemap: https://example.com/sitemap.xml" in robots


def test_sitemap_solo_incluye_paginas_publicadas(client):
    res = client.get("/sitemap.xml")
    assert res.status_code == 200
    assert "application/xml" in res.headers["content-type"]

    site = views.site_url()
    locs = set(re.findall(r"<loc>(.*?)</loc>", res.text))
    spanish = {
        "/",
        "/herramientas",
        "/comprimir-video-whatsapp",
        "/recortar-clip-vertical",
        "/transcribir-audio",
        "/comprimir-imagen",
        "/convertir-imagen",
        "/redimensionar-imagen",
        "/unir-pdf",
        "/dividir-pdf",
        "/imagenes-a-pdf",
        "/pdf-a-jpg",
        "/comprimir-pdf",
        "/generador-qr",
        "/link-whatsapp",
    }
    expected = {f"{site}{path}" for path in spanish}
    expected |= {
        f"{site}/en/" if path == "/" else f"{site}/en{path}" for path in spanish
    }
    assert locs == expected
    assert 'hreflang="es"' in res.text
    assert 'hreflang="en"' in res.text
    assert 'hreflang="x-default"' in res.text
    assert all("/privacidad" not in loc for loc in locs)
    for tool in TOOLS:
        if tool.status == "soon":
            assert tool.slug not in res.text


def test_robots_txt(client):
    res = client.get("/robots.txt")
    assert res.status_code == 200
    assert "text/plain" in res.headers["content-type"]
    assert "User-agent: *" in res.text
    assert "Disallow: /api/" in res.text
    assert f"Sitemap: {views.site_url()}/sitemap.xml" in res.text


def test_privacidad_es_noindex(client):
    assert (
        '<meta name="robots" content="noindex, follow" />'
        in client.get("/privacidad").text
    )


# ---------------------------------------------------------------------------
# Sin anuncios ni scripts de terceros
# ---------------------------------------------------------------------------


def test_no_hay_scripts_de_terceros_ni_anuncios_activos(client):
    for path in PAGES:
        text = client.get(path).text
        assert not re.search(r'<script[^>]+src="https?://', text), path
        assert "GTM-THCKMRK3" in text, path  # Google Tag Manager en todas las páginas
        assert "googletagmanager.com/ns.html?id=GTM-THCKMRK3" in text, path  # <noscript>
        for marker in ("adsbygoogle", "google-analytics", "fonts.googleapis"):
            assert marker not in text, (path, marker)

    for path in ("/", "/herramientas"):
        text = client.get(path).text
        assert 'data-ad-slot="catalog-inline"' in text
        assert 'data-ad-slot="catalog-inline" aria-hidden="true" hidden' in text


def test_csp_permite_google_tag_manager(client):
    csp = client.get("/").headers["content-security-policy"]
    script_src = next(p for p in csp.split(";") if p.strip().startswith("script-src"))
    assert "https://www.googletagmanager.com" in script_src
    assert "'sha256-" in script_src
    assert "frame-src 'self' https://www.googletagmanager.com" in csp
