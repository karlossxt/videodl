"""Vistas HTML compartidas y generación de páginas.

No usa un motor de plantillas pesado: las páginas estáticas conservan su HTML y
aquí se sustituyen unos marcadores (``<!-- HEAD -->``, ``<!-- NAV -->``,
``<!-- FOOTER -->``, ``<!-- RELATED -->``). La portada y el directorio se
generan desde el catálogo único de ``videodl/catalog.py``.
"""

from __future__ import annotations

import html
import unicodedata
from dataclasses import dataclass, replace
from datetime import date
from xml.sax.saxutils import escape as xml_escape

from . import analytics, config, i18n, seo
from .catalog import (
    Tool,
    category_by_slug,
    category_name,
    featured_tools,
    localized_categories,
    localized_tools,
    related_tools,
    tool_by_slug,
)
from .paths import STATIC_DIR

SITE_NAME = config.SITE_NAME
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
        title="Fastools — Todas tus herramientas en un solo lugar",
        description=(
            "Convierte, comprime y edita archivos gratis, sin instalaciones. "
            "Herramientas de vídeo, audio, imágenes, PDF y productividad."
        ),
        nav="home",
    ),
    "directory": PageMeta(
        key="directory",
        path="/herramientas",
        title="Directorio de herramientas gratis — Fastools",
        description=(
            "Explora todas las herramientas de Fastools: vídeo, audio, imágenes, PDF, "
            "códigos QR y enlaces de WhatsApp. Gratis y sin registro."
        ),
        nav="tools",
    ),
    "comprimir": PageMeta(
        key="comprimir",
        path="/comprimir-video-whatsapp",
        title="Comprimir vídeo para WhatsApp y Discord — Fastools",
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
        title="Recortar clip vertical para TikTok y Reels — Fastools",
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
        title="Generador de enlaces y QR de WhatsApp — Fastools",
        description=(
            "Crea un enlace wa.me con el mensaje ya escrito y descárgalo como código "
            "QR. Ideal para negocios, webs y redes sociales."
        ),
        nav="whatsapp",
        tool_slug="link-whatsapp",
    ),
    "generador-qr": PageMeta(
        key="generador-qr",
        path="/generador-qr",
        title="Generador de códigos QR gratis — Fastools",
        description=(
            "Crea códigos QR para enlaces, texto, WiFi, email, teléfono o SMS. Elige "
            "colores y tamaño y descárgalo en PNG o SVG, gratis y sin registro."
        ),
        nav="tools",
        tool_slug="generador-qr",
    ),
    "transcribir-audio": PageMeta(
        key="transcribir-audio",
        path="/transcribir-audio",
        title="Transcribir audio a texto (TXT, SRT, VTT) — Fastools",
        description=(
            "Convierte la voz de un audio o vídeo en texto editable con marcas de "
            "tiempo. Descarga la transcripción en TXT, SRT o VTT, gratis y sin registro."
        ),
        nav="tools",
        tool_slug="transcribir-audio",
    ),
    "comprimir-imagen": PageMeta(
        key="comprimir-imagen",
        path="/comprimir-imagen",
        title="Comprimir imágenes JPG, PNG y WebP — Fastools",
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
        title="Convertir imágenes entre JPG, PNG y WebP — Fastools",
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
        title="Redimensionar imágenes por píxeles o porcentaje — Fastools",
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
        title="Unir PDF online y ordenar documentos — Fastools",
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
        title="Dividir PDF y extraer páginas o rangos — Fastools",
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
        title="Convertir imágenes JPG y PNG a PDF — Fastools",
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
        title="Convertir PDF a JPG y descargar en ZIP — Fastools",
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
        title="Comprimir PDF online y reducir su peso — Fastools",
        description=(
            "Reduce el peso de un PDF con calidad y resolución ajustables. Cada página se "
            "rasteriza en tu navegador, sin subir el documento ni registrarte."
        ),
        nav="pdf",
        tool_slug="comprimir-pdf",
    ),
    "privacy": PageMeta(
        key="privacy",
        path="/privacidad",
        title="Privacidad — Fastools",
        description="Qué ocurre con los archivos y los datos que usas en Fastools.",
        nav=None,
        robots="noindex, follow",
    ),
}

# Si se configuró otra marca (por ejemplo, Fastools.es), se aplica a los títulos
# y descripciones sin repetir el nombre en cada PageMeta.
if SITE_NAME != "Fastools":
    PAGE_META = {
        key: replace(
            meta,
            title=meta.title.replace("Fastools", SITE_NAME),
            description=meta.description.replace("Fastools", SITE_NAME),
        )
        for key, meta in PAGE_META.items()
    }

def meta_for(key: str, lang: str = i18n.DEFAULT_LANG) -> PageMeta:
    """Metadatos SEO en el idioma pedido, con la marca configurada aplicada.

    Una página cuya herramienta aún no está disponible (``status="soon"`` o sin
    ruta) sale siempre con ``noindex``, aunque alguien le añada una ruta antes
    de tiempo.
    """
    meta = _localized_meta(key, lang)
    if meta.tool_slug:
        tool = tool_by_slug(meta.tool_slug)
        if tool is None or not tool.available:
            meta = replace(meta, robots="noindex, follow")
    return meta


def _localized_meta(key: str, lang: str = i18n.DEFAULT_LANG) -> PageMeta:
    meta = PAGE_META[key]
    if i18n.normalize_lang(lang) == i18n.DEFAULT_LANG:
        return meta
    title = i18n.tr(lang, f"meta.{key}.title", meta.title)
    description = i18n.tr(lang, f"meta.{key}.description", meta.description)
    if SITE_NAME != "Fastools":
        title = title.replace("Fastools", SITE_NAME)
        description = description.replace("Fastools", SITE_NAME)
    return replace(meta, title=title, description=description)


# Archivo HTML de las páginas que mantienen su estructura propia.
PAGE_FILES = {
    "comprimir": "comprimir.html",
    "clips": "clips.html",
    "whatsapp": "whatsapp.html",
    "generador-qr": "qr.html",
    "transcribir-audio": "transcribe.html",
    "privacy": "privacidad.html",
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



def sitemap_keys() -> tuple[str, ...]:
    """Páginas indexables: portada, directorio y herramientas disponibles.

    Se deriva del catálogo, así una herramienta «próximamente» o una página
    ``noindex`` nunca entra en el sitemap por olvido.
    """
    keys = ["home", "directory"]
    for key, meta in PAGE_META.items():
        if not meta.tool_slug:
            continue
        if meta_for(key).robots.lower().startswith("index"):
            keys.append(key)
    return tuple(keys)


SITEMAP_KEYS = sitemap_keys()


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


def tool_search_text(
    tool: Tool, lang: str = i18n.DEFAULT_LANG
) -> str:
    return " ".join(
        (
            tool.name,
            tool.description,
            category_name(tool.category, lang),
            *tool.keywords,
        )
    )


def matches(tool: Tool, query: str, lang: str = i18n.DEFAULT_LANG) -> bool:
    needle = _normalize(query.strip())
    return not needle or needle in _normalize(tool_search_text(tool, lang))


def filter_tools(
    query: str = "", category: str = "all", lang: str = i18n.DEFAULT_LANG
) -> tuple[Tool, ...]:
    category = category if category_by_slug(category) else "all"
    return tuple(
        tool
        for tool in localized_tools(lang)
        if matches(tool, query, lang)
        and (category == "all" or tool.category == category)
    )


def _count_label(count: int, lang: str = i18n.DEFAULT_LANG) -> str:
    key = "common.count_one" if count == 1 else "common.count_many"
    fallback = "1 herramienta" if count == 1 else f"{count} herramientas"
    return i18n.tr(lang, key, fallback, count=count)


# ---------------------------------------------------------------------------
# Cabecera, navegación y pie
# ---------------------------------------------------------------------------


def head_html(meta: PageMeta, lang: str = i18n.DEFAULT_LANG) -> str:
    normalized = i18n.normalize_lang(lang)
    localized_path = i18n.localize_path(normalized, meta.path)
    url = canonical(localized_path)
    urls = i18n.language_urls(meta.path)
    alternates = "\n".join(
        f'  <link rel="alternate" hreflang="{code}" href="{e(canonical(href))}" />'
        for code, href in urls.items()
    )
    og_locale = "es_ES" if normalized == "es" else "en_US"
    alternate_locale = "en_US" if normalized == "es" else "es_ES"
    inline = i18n.inline_script(normalized)
    image_url = canonical("/og-image.png")
    # Una página de error no tiene URL canónica ni versiones de idioma.
    url_tags = (
        ""
        if meta.key == "404"
        else f'  <link rel="canonical" href="{e(url)}" />\n{alternates}\n'
    )
    og_url = "" if meta.key == "404" else f'  <meta property="og:url" content="{e(url)}" />\n'
    ld_tag = seo.json_ld_html(seo.structured_data(meta, normalized, SITE_NAME))
    ld = f"\n{ld_tag}" if ld_tag else ""
    gtm_tag = analytics.gtm_head_html()
    gtm = f"\n{gtm_tag}" if gtm_tag else ""
    # Fragmento de Auto Ads que entrega AdSense. Se incluye directamente en el
    # <head> compartido para garantizar que se publica en todas las páginas.
    adsense = (
        '  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
        '?client=ca-pub-6317177060588245" crossorigin="anonymous"></script>\n'
    )
    return f"""  <base href="/" />
  <title>{e(meta.title)}</title>
  <meta name="description" content="{e(meta.description)}" />
  <meta name="robots" content="{e(meta.robots)}" />
{url_tags}  <meta name="color-scheme" content="dark light" />
  <meta name="theme-color" content="#080c14" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="{e(SITE_NAME)}" />
  <meta property="og:locale" content="{og_locale}" />
  <meta property="og:locale:alternate" content="{alternate_locale}" />
  <meta property="og:title" content="{e(meta.title)}" />
  <meta property="og:description" content="{e(meta.description)}" />
{og_url}  <meta property="og:image" content="{e(image_url)}" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />
  <meta property="og:image:alt" content="{e(SITE_NAME)}" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{e(meta.title)}" />
  <meta name="twitter:description" content="{e(meta.description)}" />
  <meta name="twitter:image" content="{e(image_url)}" />
  <link rel="stylesheet" href="/style.css" />
  <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
  <link rel="sitemap" type="application/xml" href="/sitemap.xml" />
{adsense}  <script>{inline}</script>
  <script src="/site.js"></script>{ld}{gtm}"""


def _brand_html() -> str:
    """Marca visible; si existe un sufijo de dominio, lo separa visualmente."""
    base, dot, suffix = SITE_NAME.rpartition(".")
    name = base if dot else SITE_NAME
    name_html = (
        'Fas<span class="accent">tools</span>'
        if name.casefold() == "fastools"
        else e(name)
    )
    if not dot:
        return name_html
    return f'{name_html} <span class="brand-tools">.{e(suffix)}</span>'


def language_switch_html(
    current_path: str, lang: str = i18n.DEFAULT_LANG
) -> str:
    """Selector ES/EN que conserva la página actual."""
    normalized = i18n.normalize_lang(lang)
    urls = i18n.language_urls(current_path)
    label = i18n.t(normalized, "nav.language_label")
    es_current = ' aria-current="true"' if normalized == "es" else ""
    en_current = ' aria-current="true"' if normalized == "en" else ""
    return f"""<div class="lang-switch" role="group" aria-label="{e(label)}" translate="no" data-i18n-skip>
      <a href="{e(urls['es'])}" hreflang="es" lang="es"{es_current}>ES</a>
      <a href="{e(urls['en'])}" hreflang="en" lang="en"{en_current}>EN</a>
    </div>"""


def nav_html(
    active: str | None,
    lang: str = i18n.DEFAULT_LANG,
    current_path: str = "/",
) -> str:
    normalized = i18n.normalize_lang(lang)
    nav_data = i18n.get_translations(normalized).get("nav", {})
    items = nav_data.get("items") if isinstance(nav_data, dict) else None
    if not isinstance(items, list):
        items = [
            {"key": key, "label": label, "path": href}
            for key, label, href in NAV_ITEMS
        ]
    links = []
    for item in items:
        key = str(item.get("key", ""))
        label = str(item.get("label", key))
        href = i18n.localize_path(normalized, str(item.get("path", "/")))
        current = ' aria-current="page"' if key == active else ""
        links.append(f'<a href="{e(href)}"{current}>{e(label)}</a>')
    return f"""{analytics.gtm_noscript_html()}<a class="skip-link" href="#main">{e(i18n.t(normalized, "nav.skip"))}</a>
<header class="site-header" translate="no" data-i18n-skip>
  <div class="page-shell nav-shell">
    <a class="site-brand" href="{e(i18n.localize_path(normalized, "/"))}" aria-label="{e(i18n.t(normalized, "nav.brand_aria", site=SITE_NAME))}" translate="no" data-i18n-skip>
      <span class="brand-mark" aria-hidden="true">F</span>
      <span class="brand-text">{_brand_html()}</span>
    </a>
    <button class="nav-toggle" type="button" data-nav-toggle aria-expanded="false" aria-controls="site-menu" aria-label="{e(i18n.t(normalized, "nav.menu_toggle"))}">
      <span class="nav-toggle-bar" aria-hidden="true"></span>
      <span class="nav-toggle-bar" aria-hidden="true"></span>
      <span class="nav-toggle-bar" aria-hidden="true"></span>
    </button>
    <nav id="site-menu" class="site-menu" aria-label="{e(i18n.t(normalized, "nav.menu_label"))}">
      {"".join(links)}
    </nav>
    {language_switch_html(current_path, normalized)}
    <button class="theme-toggle" type="button" data-theme-toggle aria-pressed="false" aria-label="{e(i18n.t(normalized, "nav.theme_light"))}">
      <span class="theme-toggle-icon" data-theme-icon aria-hidden="true">☀</span>
      <span class="theme-toggle-text" data-theme-text>{e(i18n.t(normalized, "nav.theme_text_light"))}</span>
    </button>
  </div>
</header>"""


def footer_html(lang: str = i18n.DEFAULT_LANG) -> str:
    normalized = i18n.normalize_lang(lang)
    year = date.today().year
    home = i18n.localize_path(normalized, "/")
    tools = i18n.localize_path(normalized, "/herramientas")
    privacy = i18n.localize_path(normalized, "/privacidad")
    return f"""<footer class="site-footer" translate="no" data-i18n-skip>
  <div class="page-shell footer-shell">
    <div class="footer-brand">
      <a class="site-brand" href="{e(home)}" aria-label="{e(i18n.t(normalized, "nav.brand_aria", site=SITE_NAME))}" translate="no" data-i18n-skip>
        <span class="brand-mark" aria-hidden="true">F</span>
        <span class="brand-text">{_brand_html()}</span>
      </a>
      <p>{e(i18n.t(normalized, "footer.tagline"))}. {e(i18n.t(normalized, "footer.note"))}</p>
    </div>
    <nav class="footer-links" aria-label="{e(i18n.t(normalized, "footer.links_label"))}">
      <a href="{e(tools)}">{e(i18n.t(normalized, "footer.tools"))}</a>
      <a href="{e(privacy)}">{e(i18n.t(normalized, "footer.privacy"))}</a>
    </nav>
    <p class="footer-note">
      <span>{e(i18n.t(normalized, "footer.copyright", year=year, site=SITE_NAME))}</span>
      <span class="footer-credit">{"Desarrollado por" if normalized == "es" else "Developed by"}
        <a href="https://oncenueve.com.mx" target="_blank" rel="noopener noreferrer">OnceNueve</a>
      </span>
    </p>
  </div>
</footer>"""


# ---------------------------------------------------------------------------
# Tarjetas y bloques de herramientas
# ---------------------------------------------------------------------------


def tool_card(
    tool: Tool,
    *,
    hidden: bool = False,
    compact: bool = False,
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    search_text = e(tool_search_text(tool, lang))
    category = e(category_name(tool.category, lang))
    classes = "tool-card" + (" is-soon" if not tool.available else "")
    classes += " tool-card-compact" if compact else ""
    hidden_attr = " hidden" if hidden else ""

    if tool.available:
        badge = f'<span class="tool-badge">{e(i18n.t(lang, "common.free"))}</span>'
        open_tag = (
            f'<a class="{classes}" href="{e(tool.route)}" data-tool-card '
            f'data-category="{e(tool.category)}" data-search="{search_text}" '
            f'aria-label="{e(tool.name)}: {e(tool.description)}"{hidden_attr}>'
        )
        close_tag = "</a>"
    else:
        soon = e(i18n.t(lang, "common.soon"))
        badge = f'<span class="tool-badge soon">{soon}</span>'
        open_tag = (
            f'<article class="{classes}" data-tool-card data-category="{e(tool.category)}" '
            f'data-search="{search_text}" aria-label="{e(tool.name)}: {e(soon)}"{hidden_attr}>'
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
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    hidden_slugs = hidden_slugs or set()
    cards = "".join(
        tool_card(
            tool,
            hidden=tool.slug in hidden_slugs,
            compact=compact,
            lang=lang,
        )
        for tool in tools
    )
    search_attr = " data-tools-grid" if searchable else ""
    return (
        f'<div class="tools-grid{" tools-grid-compact" if compact else ""}"'
        f"{search_attr}>{cards}</div>"
    )


def featured_section(lang: str = i18n.DEFAULT_LANG) -> str:
    tools = featured_tools(lang)
    if not tools:
        return ""
    return f"""<section class="tools-section" aria-labelledby="featured-title">
  <div class="section-heading">
    <div>
      <p class="section-kicker">{e(i18n.t(lang, "common.featured_kicker"))}</p>
      <h2 id="featured-title">{e(i18n.t(lang, "common.featured_title"))}</h2>
      <p class="section-sub">{e(i18n.t(lang, "common.featured_sub"))}</p>
    </div>
  </div>
  {tools_grid(tools, compact=True, lang=lang)}
</section>"""


def workflows_section(lang: str = i18n.DEFAULT_LANG) -> str:
    """Dos combinaciones reales entre las herramientas disponibles."""
    compress = i18n.localize_path(lang, "/comprimir-video-whatsapp")
    whatsapp = i18n.localize_path(lang, "/link-whatsapp")
    clips = i18n.localize_path(lang, "/recortar-clip-vertical")
    return f"""<section class="workflow-section" aria-labelledby="workflow-title">
  <div class="section-heading">
    <div>
      <p class="section-kicker">{e(i18n.t(lang, "common.workflow_kicker"))}</p>
      <h2 id="workflow-title">{e(i18n.t(lang, "common.workflow_title"))}</h2>
      <p class="section-sub">{e(i18n.t(lang, "common.workflow_sub"))}</p>
    </div>
  </div>
  <div class="workflow-grid">
    <article class="workflow-card">
      <h3>{e(i18n.t(lang, "common.workflow_compress_title"))}</h3>
      <p>{e(i18n.t(lang, "common.workflow_compress_text"))}</p>
      <p class="workflow-links">
        <a href="{e(compress)}">{e(i18n.t(lang, "common.workflow_compress_link"))}</a>
        <span aria-hidden="true">+</span>
        <a href="{e(whatsapp)}">{e(i18n.t(lang, "common.workflow_whatsapp_link"))}</a>
      </p>
    </article>
    <article class="workflow-card">
      <h3>{e(i18n.t(lang, "common.workflow_clip_title"))}</h3>
      <p>{e(i18n.t(lang, "common.workflow_clip_text"))}</p>
      <p class="workflow-links">
        <a href="{e(clips)}">{e(i18n.t(lang, "common.workflow_clip_link"))}</a>
        <span aria-hidden="true">+</span>
        <a href="{e(compress)}">{e(i18n.t(lang, "common.workflow_compress_link"))}</a>
      </p>
    </article>
  </div>
</section>"""


def explorer_section(
    query: str,
    category: str,
    hidden_slugs: set[str],
    visible_count: int,
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    empty_hidden = "" if visible_count == 0 else " hidden"
    return f"""<section class="tools-section" id="todas-las-herramientas" aria-labelledby="tools-title">
  <div class="section-heading">
    <div>
      <p class="section-kicker">{e(i18n.t(lang, "common.catalog_kicker"))}</p>
      <h2 id="tools-title">{e(i18n.t(lang, "common.catalog_title"))}</h2>
      <p class="section-sub">{e(i18n.t(lang, "common.catalog_sub"))}</p>
    </div>
    <p class="tools-count" data-tools-count role="status" aria-live="polite">{e(_count_label(visible_count, lang))}</p>
  </div>
  <!-- Hueco publicitario preparado: oculto y sin scripts de terceros. -->
  <div class="ad-slot" data-ad-slot="catalog-inline" aria-hidden="true" hidden></div>
  {tools_grid(localized_tools(lang), hidden_slugs=hidden_slugs, searchable=True, lang=lang)}
  <p class="tools-empty" data-tools-empty{empty_hidden}>{e(i18n.t(lang, "common.empty"))}</p>
</section>"""


# ---------------------------------------------------------------------------
# Portada y directorio
# ---------------------------------------------------------------------------


def _hero(
    title: str,
    subtitle: str,
    query: str,
    category: str,
    base_path: str,
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    active = category if category_by_slug(category) else "all"
    chips = [
        f'<a class="category-chip{" is-active" if active == "all" else ""}" '
        f'href="{e(base_path)}" data-category="all" data-category-chip'
        + (' aria-current="true"' if active == "all" else "")
        + f'>{e(i18n.t(lang, "common.all"))}</a>'
    ]
    for item in localized_categories(lang):
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
    <p class="hero-kicker">{e(i18n.t(lang, "common.hero_kicker", site=SITE_NAME))}</p>
    <h1 id="hero-title" class="hero-title">{e(title)}</h1>
    <p class="hero-lede">{e(subtitle)}</p>
    <form class="tools-search" role="search" method="get" action="{e(base_path)}">
      <label class="sr-only" for="tool-search">{e(i18n.t(lang, "common.search_label"))}</label>
      <svg class="tools-search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
        <circle cx="11" cy="11" r="7"></circle>
        <path d="m20 20-3.6-3.6"></path>
      </svg>
      <input id="tool-search" name="q" type="search" value="{e(query)}" placeholder="{e(i18n.t(lang, "common.search_placeholder"))}" autocomplete="off" data-tool-search />
      <input type="hidden" name="categoria" value="{e(active)}" data-category-input />
      <button class="tools-search-btn" type="submit">{e(i18n.t(lang, "common.search_button"))}</button>
    </form>
    <nav class="category-chips" aria-label="{e(i18n.t(lang, "common.category_filter"))}">
      {"".join(chips)}
    </nav>
    <p class="hero-note">{e(i18n.t(lang, "common.hero_note"))}</p>
  </div>
</section>"""


def page_document(
    meta: PageMeta,
    body: str,
    scripts: tuple[str, ...] = (),
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    normalized = i18n.normalize_lang(lang)
    script_tags = "".join(f'  <script src="{e(src)}"></script>\n' for src in scripts)
    return f"""<!DOCTYPE html>
<html lang="{normalized}" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
{head_html(meta, normalized)}
</head>
<body>
{body}
{script_tags}</body>
</html>"""


def home_page(
    query: str = "",
    category: str = "all",
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    normalized = i18n.normalize_lang(lang)
    meta = meta_for("home", normalized)
    filtered = filter_tools(query, category, normalized)
    filtered_slugs = {tool.slug for tool in filtered}
    hidden = {
        tool.slug for tool in localized_tools(normalized) if tool.slug not in filtered_slugs
    }
    filtering = bool(query.strip()) or category_by_slug(category) is not None
    if filtering:
        meta = replace(meta, robots="noindex, follow")
    extra = "" if filtering else featured_section(normalized) + workflows_section(normalized)

    body = f"""{nav_html("home", normalized, meta.path)}
<main id="main">
  {_hero(
      i18n.t(normalized, "common.home_title"),
      i18n.t(normalized, "common.home_subtitle"),
      query,
      category,
      i18n.localize_path(normalized, "/"),
      normalized,
  )}
  <div class="page-shell">
    {extra}
    {explorer_section(query, category, hidden, len(filtered), normalized)}
  </div>
</main>
{footer_html(normalized)}"""
    return page_document(meta, body, scripts=("/tools.js",), lang=normalized)


def directory_page(
    query: str = "",
    category: str = "all",
    lang: str = i18n.DEFAULT_LANG,
) -> str:
    normalized = i18n.normalize_lang(lang)
    meta = meta_for("directory", normalized)
    filtered = filter_tools(query, category, normalized)
    filtered_slugs = {tool.slug for tool in filtered}
    hidden = {
        tool.slug for tool in localized_tools(normalized) if tool.slug not in filtered_slugs
    }
    if bool(query.strip()) or category_by_slug(category) is not None:
        meta = replace(meta, robots="noindex, follow")
    body = f"""{nav_html("tools", normalized, meta.path)}
<main id="main">
  {_hero(
      i18n.t(normalized, "common.directory_title"),
      i18n.t(normalized, "common.directory_subtitle", site=SITE_NAME),
      query,
      category,
      i18n.localize_path(normalized, "/herramientas"),
      normalized,
  )}
  <div class="page-shell">
    {explorer_section(query, category, hidden, len(filtered), normalized)}
  </div>
</main>
{footer_html(normalized)}"""
    return page_document(meta, body, scripts=("/tools.js",), lang=normalized)


# ---------------------------------------------------------------------------
# Páginas estáticas con marcadores compartidos
# ---------------------------------------------------------------------------


def related_html(
    tool_slug: str, lang: str = i18n.DEFAULT_LANG
) -> str:
    normalized = i18n.normalize_lang(lang)
    tools = related_tools(tool_slug, lang=normalized)
    if not tools:
        return ""
    return f"""<section class="tools-section related-tools" aria-labelledby="related-title">
  <div class="section-heading">
    <div>
      <p class="section-kicker">{e(i18n.t(normalized, "common.related_kicker"))}</p>
      <h2 id="related-title">{e(i18n.t(normalized, "common.related_title"))}</h2>
    </div>
  </div>
  {tools_grid(tools, compact=True, lang=normalized)}
</section>"""


def render_static(key: str, lang: str = i18n.DEFAULT_LANG) -> str:
    normalized = i18n.normalize_lang(lang)
    meta = meta_for(key, normalized)
    html_text = (STATIC_DIR / PAGE_FILES[key]).read_text(encoding="utf-8")
    replacements = {
        "<!-- HEAD -->": head_html(meta, normalized),
        "<!-- NAV -->": nav_html(meta.nav, normalized, meta.path),
        "<!-- FOOTER -->": footer_html(normalized),
        "<!-- RELATED -->": (
            related_html(meta.tool_slug, normalized) if meta.tool_slug else ""
        ),
    }
    for marker, value in replacements.items():
        html_text = html_text.replace(marker, value)
    html_text = html_text.replace('<html lang="es"', f'<html lang="{normalized}"', 1)
    return i18n.translate_html(html_text, normalized)


# ---------------------------------------------------------------------------
# SEO
# ---------------------------------------------------------------------------


def not_found_page(lang: str = i18n.DEFAULT_LANG) -> str:
    """Página 404 con ``noindex``, sin canonical y con el diseño del sitio."""
    normalized = i18n.normalize_lang(lang)
    title = i18n.t(normalized, "common.not_found_title")
    text = i18n.t(normalized, "common.not_found_text")
    meta = PageMeta(
        key="404",
        path="/",
        title=f"{title} — {SITE_NAME}",
        description=text,
        nav=None,
        robots="noindex, nofollow",
    )
    home = i18n.localize_path(normalized, "/")
    tools = i18n.localize_path(normalized, "/herramientas")
    body = f"""{nav_html(None, normalized, home)}
<main id="main" class="legal-page">
  <header class="legal-hero">
    <h1>{e(title)}</h1>
    <p>{e(text)}</p>
  </header>
  <section class="legal-card">
    <p><a href="{e(home)}">{e(i18n.t(normalized, "common.not_found_home"))}</a> ·
    <a href="{e(tools)}">{e(i18n.t(normalized, "common.not_found_tools"))}</a></p>
  </section>
</main>
{footer_html(normalized)}"""
    return page_document(meta, body, lang=normalized)


def sitemap_xml() -> str:
    urls = []
    for key in sitemap_keys():
        meta = PAGE_META[key]
        priority = "1.0" if key == "home" else "0.8" if key != "directory" else "0.9"
        urls_variants = i18n.language_urls(meta.path)
        for code in ("es", "en"):
            alternates = "".join(
                f'    <xhtml:link rel="alternate" hreflang="{alt_code}" '
                f'href="{xml_escape(canonical(alt_path))}" />\n'
                for alt_code, alt_path in urls_variants.items()
            )
            urls.append(
                "  <url>\n"
                f"    <loc>{xml_escape(canonical(urls_variants[code]))}</loc>\n"
                f"{alternates}"
                "    <changefreq>weekly</changefreq>\n"
                f"    <priority>{priority}</priority>\n"
                "  </url>"
            )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )


def robots_txt() -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /health\n"
        f"Sitemap: {site_url()}/sitemap.xml\n"
    )
