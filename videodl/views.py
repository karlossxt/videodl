"""Vistas HTML compartidas y generación de páginas.

No usa un motor de plantillas pesado: las páginas estáticas conservan su HTML y
aquí se sustituyen unos marcadores (``<!-- HEAD -->``, ``<!-- NAV -->``,
``<!-- FOOTER -->``, ``<!-- RELATED -->``). La portada y el directorio se
generan desde el catálogo único de ``videodl/catalog.py``.
"""

from __future__ import annotations

import html
import unicodedata
from dataclasses import dataclass
from datetime import date
from xml.sax.saxutils import escape as xml_escape

from . import config
from .catalog import (
    CATEGORIES,
    TOOLS,
    Tool,
    category_by_slug,
    category_name,
    featured_tools,
    related_tools,
)
from .paths import STATIC_DIR

SITE_NAME = "FasTools.app"
SITE_TAGLINE = "Herramientas gratuitas para tus archivos"


@dataclass(frozen=True, slots=True)
class PageMeta:
    key: str
    path: str
    title: str
    description: str
    nav: str | None
    robots: str = "index, follow"
    tool_slug: str | None = None


PAGE_META: dict[str, PageMeta] = {
    "home": PageMeta(
        key="home",
        path="/",
        title="FasTools.app — Todas tus herramientas en un solo lugar",
        description=(
            "Convierte, comprime y edita archivos gratis, sin instalaciones. "
            "Herramientas de vídeo, audio, imágenes, PDF y productividad."
        ),
        nav="home",
    ),
    "directory": PageMeta(
        key="directory",
        path="/herramientas",
        title="Directorio de herramientas gratis — FasTools.app",
        description=(
            "Explora todas las herramientas de FasTools.app: comprimir vídeo, recortar "
            "clips, comprimir y convertir imágenes, unir o dividir PDF, enlaces de WhatsApp "
            "y próximas utilidades de audio y productividad."
        ),
        nav="tools",
    ),
    "comprimir": PageMeta(
        key="comprimir",
        path="/comprimir-video-whatsapp",
        title="Comprimir vídeo para WhatsApp y Discord — FasTools.app",
        description=(
            "Reduce el tamaño de un vídeo para WhatsApp, Discord, Telegram o correo "
            "sin perder más calidad de la necesaria. Gratis y sin registro."
        ),
        nav="comprimir",
        tool_slug="comprimir-video-whatsapp",
    ),
    "clips": PageMeta(
        key="clips",
        path="/recortar-clip-vertical",
        title="Recortar clip vertical para TikTok, Reels y Shorts — FasTools.app",
        description=(
            "Sube tu vídeo, elige los segundos y descárgalo en vertical 9:16, "
            "cuadrado o formato original. Gratis, sin marca de agua y sin registro."
        ),
        nav="clips",
        tool_slug="recortar-clip-vertical",
    ),
    "whatsapp": PageMeta(
        key="whatsapp",
        path="/link-whatsapp",
        title="Generador de enlaces y QR de WhatsApp — FasTools.app",
        description=(
            "Crea un enlace wa.me con el mensaje ya escrito y descárgalo como código "
            "QR. Ideal para negocios, webs y redes sociales."
        ),
        nav="whatsapp",
        tool_slug="link-whatsapp",
    ),
    "comprimir-imagen": PageMeta(
        key="comprimir-imagen",
        path="/comprimir-imagen",
        title="Comprimir imágenes JPG, PNG y WebP — FasTools.app",
        description=(
            "Comprime imágenes JPG, PNG y WebP con calidad ajustable directamente en tu "
            "navegador. Sin subirlas a internet, con vista previa y descarga gratis."
        ),
        nav="imagenes",
        tool_slug="comprimir-imagen",
    ),
    "convertir-imagen": PageMeta(
        key="convertir-imagen",
        path="/convertir-imagen",
        title="Convertir imágenes entre JPG, PNG y WebP — FasTools.app",
        description=(
            "Convierte imágenes JPG, PNG y WebP en tu navegador con control de calidad y "
            "transparencia. Sin registro, sin servidores y con descarga directa."
        ),
        nav="imagenes",
        tool_slug="convertir-imagen",
    ),
    "redimensionar-imagen": PageMeta(
        key="redimensionar-imagen",
        path="/redimensionar-imagen",
        title="Redimensionar imágenes por píxeles o porcentaje — FasTools.app",
        description=(
            "Cambia el ancho y el alto de tus imágenes por píxeles o porcentaje, "
            "manteniendo la proporción. Todo en tu navegador y sin perder el original."
        ),
        nav="imagenes",
        tool_slug="redimensionar-imagen",
    ),
    "unir-pdf": PageMeta(
        key="unir-pdf",
        path="/unir-pdf",
        title="Unir PDF online y ordenar documentos — FasTools.app",
        description=(
            "Combina varios PDF en uno solo, elige el orden de cada documento y descarga "
            "el resultado. Procesamiento local, sin subir archivos ni registro."
        ),
        nav="pdf",
        tool_slug="unir-pdf",
    ),
    "dividir-pdf": PageMeta(
        key="dividir-pdf",
        path="/dividir-pdf",
        title="Dividir PDF y extraer páginas o rangos — FasTools.app",
        description=(
            "Extrae páginas o rangos de un PDF con orden personalizado y vista previa. "
            "El documento se procesa en tu navegador y no se sube a ningún servidor."
        ),
        nav="pdf",
        tool_slug="dividir-pdf",
    ),
    "imagenes-a-pdf": PageMeta(
        key="imagenes-a-pdf",
        path="/imagenes-a-pdf",
        title="Convertir imágenes JPG y PNG a PDF — FasTools.app",
        description=(
            "Crea un PDF con tus imágenes JPG o PNG, ordénalas y elige páginas A4 o el "
            "tamaño original. Todo en tu navegador, sin subir las fotos."
        ),
        nav="pdf",
        tool_slug="imagenes-a-pdf",
    ),
    "pdf-a-jpg": PageMeta(
        key="pdf-a-jpg",
        path="/pdf-a-jpg",
        title="Convertir PDF a JPG y descargar en ZIP — FasTools.app",
        description=(
            "Convierte las páginas de un PDF en imágenes JPG con calidad y resolución "
            "ajustables. Descarga una imagen o un ZIP, sin subir el PDF."
        ),
        nav="pdf",
        tool_slug="pdf-a-jpg",
    ),
    "comprimir-pdf": PageMeta(
        key="comprimir-pdf",
        path="/comprimir-pdf",
        title="Comprimir PDF online y reducir su peso — FasTools.app",
        description=(
            "Reduce el peso de un PDF con calidad y resolución ajustables. Cada página se "
            "rasteriza en tu navegador, sin subir el documento ni registrarte."
        ),
        nav="pdf",
        tool_slug="comprimir-pdf",
    ),
    "legal": PageMeta(
        key="legal",
        path="/legal",
        title="Legal y privacidad — FasTools.app",
        description="Aviso legal, política de privacidad, términos de uso y contacto de FasTools.app.",
        nav=None,
        robots="noindex, follow",
    ),
}

# Archivo HTML de las páginas que mantienen su estructura propia.
PAGE_FILES = {
    "comprimir": "comprimir.html",
    "clips": "clips.html",
    "whatsapp": "whatsapp.html",
    "legal": "legal.html",
}

NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("home", "Inicio", "/"),
    ("tools", "Herramientas", "/herramientas"),
    ("comprimir", "Comprimir", "/comprimir-video-whatsapp"),
    ("clips", "Clips", "/recortar-clip-vertical"),
    ("imagenes", "Imágenes", "/herramientas?categoria=imagenes"),
    ("pdf", "PDF", "/herramientas?categoria=pdf"),
    ("whatsapp", "WhatsApp", "/link-whatsapp"),
)

SITEMAP_KEYS = (
    "home",
    "directory",
    "comprimir",
    "clips",
    "comprimir-imagen",
    "convertir-imagen",
    "redimensionar-imagen",
    "unir-pdf",
    "dividir-pdf",
    "imagenes-a-pdf",
    "pdf-a-jpg",
    "comprimir-pdf",
    "whatsapp",
)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def e(value: object) -> str:
    return html.escape(str(value), quote=True)


def site_url() -> str:
    return config.SITE_URL.rstrip("/")


def canonical(path: str) -> str:
    return f"{site_url()}{path}"


def _normalize(text: str) -> str:
    """Minúsculas y sin acentos: «Vídeo» y «video» deben coincidir."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def tool_search_text(tool: Tool) -> str:
    return " ".join(
        (tool.name, tool.description, category_name(tool.category), *tool.keywords)
    )


def matches(tool: Tool, query: str) -> bool:
    needle = _normalize(query.strip())
    return not needle or needle in _normalize(tool_search_text(tool))


def filter_tools(query: str = "", category: str = "all") -> tuple[Tool, ...]:
    category = category if category_by_slug(category) else "all"
    return tuple(
        tool
        for tool in TOOLS
        if matches(tool, query) and (category == "all" or tool.category == category)
    )


def _count_label(count: int) -> str:
    return "1 herramienta" if count == 1 else f"{count} herramientas"


# ---------------------------------------------------------------------------
# Cabecera, navegación y pie
# ---------------------------------------------------------------------------


def head_html(meta: PageMeta) -> str:
    url = canonical(meta.path)
    return f"""  <title>{e(meta.title)}</title>
  <meta name="description" content="{e(meta.description)}" />
  <meta name="robots" content="{e(meta.robots)}" />
  <link rel="canonical" href="{e(url)}" />
  <meta name="color-scheme" content="dark light" />
  <meta name="theme-color" content="#080c14" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="{e(SITE_NAME)}" />
  <meta property="og:locale" content="es_ES" />
  <meta property="og:title" content="{e(meta.title)}" />
  <meta property="og:description" content="{e(meta.description)}" />
  <meta property="og:url" content="{e(url)}" />
  <meta name="twitter:card" content="summary" />
  <meta name="twitter:title" content="{e(meta.title)}" />
  <meta name="twitter:description" content="{e(meta.description)}" />
  <link rel="stylesheet" href="/style.css" />
  <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
  <link rel="sitemap" type="application/xml" href="/sitemap.xml" />
  <script src="/site.js"></script>"""


def nav_html(active: str | None) -> str:
    links = []
    for key, label, href in NAV_ITEMS:
        current = ' aria-current="page"' if key == active else ""
        links.append(f'<a href="{e(href)}"{current}>{e(label)}</a>')
    return f"""<a class="skip-link" href="#main">Saltar al contenido</a>
<header class="site-header">
  <div class="page-shell nav-shell">
    <a class="site-brand" href="/" aria-label="FasTools.app, inicio">
      <span class="brand-mark" aria-hidden="true">F</span>
      <span class="brand-text">Fas<span class="accent">Tools</span> <span class="brand-tools">.app</span></span>
    </a>
    <button class="nav-toggle" type="button" data-nav-toggle aria-expanded="false" aria-controls="site-menu" aria-label="Abrir menú de navegación">
      <span class="nav-toggle-bar" aria-hidden="true"></span>
      <span class="nav-toggle-bar" aria-hidden="true"></span>
      <span class="nav-toggle-bar" aria-hidden="true"></span>
    </button>
    <nav id="site-menu" class="site-menu" aria-label="Navegación principal">
      {"".join(links)}
    </nav>
    <button class="theme-toggle" type="button" data-theme-toggle aria-pressed="false" aria-label="Cambiar a modo claro">
      <span class="theme-toggle-icon" data-theme-icon aria-hidden="true">☀</span>
      <span class="theme-toggle-text" data-theme-text>Modo claro</span>
    </button>
  </div>
</header>"""


def footer_html() -> str:
    year = date.today().year
    return f"""<footer class="site-footer">
  <div class="page-shell footer-shell">
    <div class="footer-brand">
      <a class="site-brand" href="/" aria-label="FasTools.app, inicio">
        <span class="brand-mark" aria-hidden="true">F</span>
        <span class="brand-text">Fas<span class="accent">Tools</span> <span class="brand-tools">.app</span></span>
      </a>
      <p>{e(SITE_TAGLINE)}. Sin registro y sin instalar nada.</p>
    </div>
    <nav class="footer-links" aria-label="Enlaces legales y de navegación">
      <a href="/herramientas">Herramientas</a>
      <a href="/legal#aviso-legal">Aviso legal</a>
      <a href="/legal#privacidad">Privacidad</a>
      <a href="/legal#terminos">Términos</a>
      <a href="/legal#contacto">Contacto</a>
    </nav>
    <p class="footer-note">© {year} {e(SITE_NAME)} · Hecho en español</p>
  </div>
</footer>"""


# ---------------------------------------------------------------------------
# Tarjetas y bloques de herramientas
# ---------------------------------------------------------------------------


def tool_card(tool: Tool, *, hidden: bool = False, compact: bool = False) -> str:
    search_text = e(tool_search_text(tool))
    category = e(category_name(tool.category))
    classes = "tool-card" + (" is-soon" if not tool.available else "")
    classes += " tool-card-compact" if compact else ""
    hidden_attr = " hidden" if hidden else ""

    if tool.available:
        badge = '<span class="tool-badge">Gratis</span>'
        open_tag = (
            f'<a class="{classes}" href="{e(tool.route)}" data-tool-card '
            f'data-category="{e(tool.category)}" data-search="{search_text}" '
            f'aria-label="{e(tool.name)}: {e(tool.description)}"{hidden_attr}>'
        )
        close_tag = "</a>"
    else:
        badge = '<span class="tool-badge soon">Próximamente</span>'
        open_tag = (
            f'<article class="{classes}" data-tool-card data-category="{e(tool.category)}" '
            f'data-search="{search_text}" aria-label="{e(tool.name)}: próximamente"{hidden_attr}>'
        )
        close_tag = "</article>"

    return f"""{open_tag}
  <span class="tool-card-icon" aria-hidden="true">{e(tool.icon)}</span>
  <span class="tool-card-body">
    <span class="tool-card-head">
      <span class="tool-card-name">{e(tool.name)}</span>
      {badge}
    </span>
    <span class="tool-card-desc">{e(tool.description)}</span>
    <span class="tool-card-category">{category}</span>
  </span>
{close_tag}"""


def tools_grid(
    tools: tuple[Tool, ...],
    *,
    hidden_slugs: set[str] | None = None,
    compact: bool = False,
    searchable: bool = False,
) -> str:
    hidden_slugs = hidden_slugs or set()
    cards = "".join(
        tool_card(tool, hidden=tool.slug in hidden_slugs, compact=compact) for tool in tools
    )
    search_attr = " data-tools-grid" if searchable else ""
    return (
        f'<div class="tools-grid{" tools-grid-compact" if compact else ""}"'
        f"{search_attr}>{cards}</div>"
    )


def featured_section() -> str:
    tools = featured_tools()
    if not tools:
        return ""
    return f"""<section class="tools-section" aria-labelledby="featured-title">
  <div class="section-heading">
    <div>
      <p class="section-kicker">Listas para usar</p>
      <h2 id="featured-title">Herramientas destacadas</h2>
      <p class="section-sub">Empieza por las utilidades que ya funcionan hoy.</p>
    </div>
  </div>
  {tools_grid(tools, compact=True)}
</section>"""


def workflows_section() -> str:
    """Dos combinaciones reales entre las herramientas disponibles."""
    return """<section class="workflow-section" aria-labelledby="workflow-title">
  <div class="section-heading">
    <div>
      <p class="section-kicker">Herramientas relacionadas</p>
      <h2 id="workflow-title">Combínalas según lo que necesites</h2>
      <p class="section-sub">Flujos rápidos con enlaces reales, sin pasos de más.</p>
    </div>
  </div>
  <div class="workflow-grid">
    <article class="workflow-card">
      <h3>Comprime y comparte</h3>
      <p>Deja el vídeo en el tamaño que acepta WhatsApp y genera el enlace del chat.</p>
      <p class="workflow-links">
        <a href="/comprimir-video-whatsapp">Comprimir vídeo</a>
        <span aria-hidden="true">+</span>
        <a href="/link-whatsapp">Enlace de WhatsApp</a>
      </p>
    </article>
    <article class="workflow-card">
      <h3>Recorta y publica</h3>
      <p>Saca el momento que te interesa en 9:16 y comprímelo si pesa demasiado.</p>
      <p class="workflow-links">
        <a href="/recortar-clip-vertical">Recortar clip</a>
        <span aria-hidden="true">+</span>
        <a href="/comprimir-video-whatsapp">Comprimir vídeo</a>
      </p>
    </article>
  </div>
</section>"""


def explorer_section(query: str, category: str, hidden_slugs: set[str], visible_count: int) -> str:
    empty_hidden = "" if visible_count == 0 else " hidden"
    return f"""<section class="tools-section" id="todas-las-herramientas" aria-labelledby="tools-title">
  <div class="section-heading">
    <div>
      <p class="section-kicker">Catálogo completo</p>
      <h2 id="tools-title">Todas las herramientas</h2>
      <p class="section-sub">Filtra por categoría o busca por nombre y palabra clave.</p>
    </div>
    <p class="tools-count" data-tools-count role="status" aria-live="polite">{_count_label(visible_count)}</p>
  </div>
  <!-- Hueco publicitario preparado: oculto y sin scripts de terceros. -->
  <div class="ad-slot" data-ad-slot="catalog-inline" aria-hidden="true" hidden></div>
  {tools_grid(TOOLS, hidden_slugs=hidden_slugs, searchable=True)}
  <p class="tools-empty" data-tools-empty{empty_hidden}>No hay herramientas que coincidan. Prueba con otra palabra o categoría.</p>
</section>"""


# ---------------------------------------------------------------------------
# Portada y directorio
# ---------------------------------------------------------------------------


def _hero(title: str, subtitle: str, query: str, category: str, base_path: str) -> str:
    active = category if category_by_slug(category) else "all"
    chips = [
        f'<a class="category-chip{" is-active" if active == "all" else ""}" '
        f'href="{e(base_path)}" data-category="all" data-category-chip'
        + (' aria-current="true"' if active == "all" else "")
        + ">Todas</a>"
    ]
    for item in CATEGORIES:
        chips.append(
            f'<a class="category-chip{" is-active" if active == item.slug else ""}" '
            f'href="{e(base_path)}?categoria={e(item.slug)}" data-category="{e(item.slug)}" '
            "data-category-chip"
            + (' aria-current="true"' if active == item.slug else "")
            + f'><span aria-hidden="true">{e(item.icon)}</span> {e(item.name)}</a>'
        )

    return f"""<section class="hero-v2" aria-labelledby="hero-title">
  <div class="hero-orbit" aria-hidden="true"></div>
  <div class="page-shell hero-shell">
    <p class="hero-kicker">{e(SITE_NAME)} · gratis y sin registro</p>
    <h1 id="hero-title" class="hero-title">{e(title)}</h1>
    <p class="hero-lede">{e(subtitle)}</p>
    <form class="tools-search" role="search" method="get" action="{e(base_path)}">
      <label class="sr-only" for="tool-search">Buscar herramientas</label>
      <svg class="tools-search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
        <circle cx="11" cy="11" r="7"></circle>
        <path d="m20 20-3.6-3.6"></path>
      </svg>
      <input id="tool-search" name="q" type="search" value="{e(query)}" placeholder="Busca: comprimir, clip, PDF, audio…" autocomplete="off" data-tool-search />
      <input type="hidden" name="categoria" value="{e(active)}" data-category-input />
      <button class="tools-search-btn" type="submit">Buscar</button>
    </form>
    <nav class="category-chips" aria-label="Filtrar por categoría">
      {"".join(chips)}
    </nav>
    <p class="hero-note">Solo procesamos los archivos que subes tú. Nada de descargas de plataformas de terceros.</p>
  </div>
</section>"""


def page_document(meta: PageMeta, body: str, scripts: tuple[str, ...] = ()) -> str:
    script_tags = "".join(f'  <script src="{e(src)}"></script>\n' for src in scripts)
    return f"""<!DOCTYPE html>
<html lang="es" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
{head_html(meta)}
</head>
<body>
{body}
{script_tags}</body>
</html>"""


def home_page(query: str = "", category: str = "all") -> str:
    meta = PAGE_META["home"]
    filtered = filter_tools(query, category)
    filtered_slugs = {tool.slug for tool in filtered}
    hidden = {tool.slug for tool in TOOLS if tool.slug not in filtered_slugs}
    filtering = bool(query.strip()) or category_by_slug(category) is not None
    extra = "" if filtering else featured_section() + workflows_section()

    body = f"""{nav_html("home")}
<main id="main">
  {_hero(
      "Todas tus herramientas en un solo lugar",
      "Convierte, comprime y edita archivos gratis, sin instalaciones",
      query,
      category,
      "/",
  )}
  <div class="page-shell">
    {extra}
    {explorer_section(query, category, hidden, len(filtered))}
  </div>
</main>
{footer_html()}"""
    return page_document(meta, body, scripts=("/tools.js",))


def directory_page(query: str = "", category: str = "all") -> str:
    meta = PAGE_META["directory"]
    filtered = filter_tools(query, category)
    filtered_slugs = {tool.slug for tool in filtered}
    hidden = {tool.slug for tool in TOOLS if tool.slug not in filtered_slugs}
    body = f"""{nav_html("tools")}
<main id="main">
  {_hero(
      "Directorio de herramientas",
      "Todas las utilidades de FasTools.app, ordenadas por categoría y listas para usar",
      query,
      category,
      "/herramientas",
  )}
  <div class="page-shell">
    {explorer_section(query, category, hidden, len(filtered))}
  </div>
</main>
{footer_html()}"""
    return page_document(meta, body, scripts=("/tools.js",))


# ---------------------------------------------------------------------------
# Páginas estáticas con marcadores compartidos
# ---------------------------------------------------------------------------


def related_html(tool_slug: str) -> str:
    tools = related_tools(tool_slug)
    if not tools:
        return ""
    return f"""<section class="tools-section related-tools" aria-labelledby="related-title">
  <div class="section-heading">
    <div>
      <p class="section-kicker">Sigue con</p>
      <h2 id="related-title">Herramientas relacionadas</h2>
    </div>
  </div>
  {tools_grid(tools, compact=True)}
</section>"""


def render_static(key: str) -> str:
    meta = PAGE_META[key]
    html_text = (STATIC_DIR / PAGE_FILES[key]).read_text(encoding="utf-8")
    replacements = {
        "<!-- HEAD -->": head_html(meta),
        "<!-- NAV -->": nav_html(meta.nav),
        "<!-- FOOTER -->": footer_html(),
        "<!-- RELATED -->": related_html(meta.tool_slug) if meta.tool_slug else "",
    }
    for marker, value in replacements.items():
        html_text = html_text.replace(marker, value)
    return html_text


# ---------------------------------------------------------------------------
# SEO
# ---------------------------------------------------------------------------


def sitemap_xml() -> str:
    urls = []
    for key in SITEMAP_KEYS:
        meta = PAGE_META[key]
        priority = "1.0" if key == "home" else "0.8" if key != "directory" else "0.9"
        urls.append(
            "  <url>\n"
            f"    <loc>{xml_escape(canonical(meta.path))}</loc>\n"
            "    <changefreq>weekly</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )


def robots_txt() -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        f"Sitemap: {site_url()}/sitemap.xml\n"
    )
