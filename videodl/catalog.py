"""Registro único del catálogo de herramientas.

La portada, el directorio `/herramientas` y los bloques de herramientas
relacionadas se generan desde aquí. Añadir una herramienta nueva consiste en
añadir una entrada a ``TOOLS`` y crear su ruta en ``videodl/pages.py``: no hay
listas duplicadas en HTML ni en JavaScript.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from . import i18n

Status = Literal["available", "soon"]


@dataclass(frozen=True, slots=True)
class Category:
    slug: str
    name: str
    icon: str
    description: str


@dataclass(frozen=True, slots=True)
class Tool:
    slug: str
    name: str
    description: str
    category: str
    icon: str
    keywords: tuple[str, ...] = ()
    route: str | None = None
    status: Status = "soon"
    featured: bool = False

    @property
    def available(self) -> bool:
        return self.status == "available" and bool(self.route)


# El orden importa: define el orden de las categorías y de la cuadrícula.
CATEGORIES: tuple[Category, ...] = (
    Category("video", "Vídeo", "🎬", "Comprime, recorta y convierte vídeo."),
    Category("audio", "Audio", "🎧", "Extrae, une y convierte pistas de audio."),
    Category("imagenes", "Imágenes", "🖼️", "Comprime, convierte y redimensiona imágenes."),
    Category("pdf", "PDF", "📄", "Une, divide, comprime y convierte documentos PDF."),
    Category("productividad", "Productividad", "⚡", "Enlaces, códigos QR y utilidades del día a día."),
)

TOOLS: tuple[Tool, ...] = (
    # --- Vídeo -------------------------------------------------------------
    Tool(
        slug="comprimir-video-whatsapp",
        name="Comprimir vídeo",
        description="Reduce un vídeo para WhatsApp, Discord, Telegram o correo sin perder más calidad de la necesaria.",
        category="video",
        icon="🗜️",
        keywords=("comprimir", "whatsapp", "discord", "telegram", "tamaño", "mb", "mp4"),
        route="/comprimir-video-whatsapp",
        status="available",
        featured=True,
    ),
    Tool(
        slug="recortar-clip-vertical",
        name="Recortar clip vertical",
        description="Recorta los segundos que quieras y reencuadra en 9:16, 1:1 o formato original.",
        category="video",
        icon="✂️",
        keywords=("clip", "vertical", "tiktok", "reels", "shorts", "recortar", "9:16"),
        route="/recortar-clip-vertical",
        status="available",
        featured=True,
    ),
    Tool(
        slug="video-a-gif",
        name="Convertir vídeo a GIF",
        description="Crea GIFs optimizados a partir de un fragmento de tu vídeo.",
        category="video",
        icon="🎞️",
        keywords=("gif", "convertir", "animación"),
    ),
    # --- Audio -------------------------------------------------------------
    Tool(
        slug="transcribir-audio",
        name="Transcribir audio a texto",
        description="Convierte la voz de un audio o vídeo en texto editable y descarga TXT, SRT o VTT.",
        category="audio",
        icon="📝",
        keywords=(
            "transcribir", "transcripción", "audio", "texto", "voz", "subtítulos",
            "srt", "vtt", "whisper", "dictado",
        ),
        route="/transcribir-audio",
        status="available",
        featured=True,
    ),
    Tool(
        slug="extraer-audio",
        name="Extraer audio (MP3)",
        description="Separa la pista de audio de un vídeo y descárgala en MP3.",
        category="audio",
        icon="🎵",
        keywords=("mp3", "audio", "extraer", "música", "voz"),
    ),
    Tool(
        slug="unir-audio",
        name="Unir o cortar audio",
        description="Combina varias pistas o recorta un audio por segundos.",
        category="audio",
        icon="🎚️",
        keywords=("unir", "cortar", "audio", "mp3", "wav"),
    ),
    # --- Imágenes ----------------------------------------------------------
    Tool(
        slug="comprimir-imagen",
        name="Comprimir imágenes",
        description="Reduce el peso de JPG, PNG o WebP con calidad ajustable y sin subirlas al servidor.",
        category="imagenes",
        icon="🗻",
        keywords=("imagen", "jpg", "png", "webp", "comprimir", "peso", "calidad"),
        route="/comprimir-imagen",
        status="available",
        featured=True,
    ),
    Tool(
        slug="convertir-imagen",
        name="Convertir imágenes",
        description="Cambia entre JPG, PNG y WebP en el navegador, con transparencia y calidad configurables.",
        category="imagenes",
        icon="🔄",
        keywords=("convertir", "imagen", "jpg", "jpeg", "png", "webp", "formato"),
        route="/convertir-imagen",
        status="available",
        featured=True,
    ),
    Tool(
        slug="redimensionar-imagen",
        name="Redimensionar imágenes",
        description="Cambia el ancho y el alto por píxeles o porcentaje manteniendo la proporción.",
        category="imagenes",
        icon="📐",
        keywords=("redimensionar", "escalar", "tamaño", "píxeles", "porcentaje", "imagen"),
        route="/redimensionar-imagen",
        status="available",
        featured=True,
    ),
    # --- PDF ---------------------------------------------------------------
    Tool(
        slug="unir-pdf",
        name="Unir PDF",
        description="Combina varios documentos en un solo PDF y decide el orden de cada uno.",
        category="pdf",
        icon="📑",
        keywords=("pdf", "unir", "combinar", "documentos", "orden"),
        route="/unir-pdf",
        status="available",
        featured=True,
    ),
    Tool(
        slug="dividir-pdf",
        name="Dividir PDF",
        description="Extrae páginas o rangos de un PDF y descarga solo lo que necesitas.",
        category="pdf",
        icon="✂️",
        keywords=("pdf", "dividir", "extraer", "páginas", "rangos", "separar"),
        route="/dividir-pdf",
        status="available",
    ),
    Tool(
        slug="imagenes-a-pdf",
        name="Imágenes a PDF",
        description="Convierte fotos y capturas JPG o PNG en un PDF ordenado.",
        category="pdf",
        icon="🖼️",
        keywords=("pdf", "imágenes", "jpg", "png", "convertir", "fotos"),
        route="/imagenes-a-pdf",
        status="available",
    ),
    Tool(
        slug="pdf-a-jpg",
        name="PDF a JPG",
        description="Convierte las páginas de un PDF en imágenes JPG y descárgalas en ZIP.",
        category="pdf",
        icon="🖨️",
        keywords=("pdf", "jpg", "imagen", "convertir", "páginas", "zip"),
        route="/pdf-a-jpg",
        status="available",
        featured=True,
    ),
    Tool(
        slug="comprimir-pdf",
        name="Comprimir PDF",
        description="Reduce el peso de un PDF rasterizando sus páginas con calidad ajustable.",
        category="pdf",
        icon="🗜️",
        keywords=("pdf", "comprimir", "reducir", "peso", "optimizar"),
        route="/comprimir-pdf",
        status="available",
    ),
    # --- Productividad -----------------------------------------------------
    Tool(
        slug="generador-qr",
        name="Generador de códigos QR",
        description="Crea QR de enlaces, texto, WiFi, email, teléfono o SMS y descárgalos en PNG o SVG.",
        category="productividad",
        icon="🔳",
        keywords=(
            "qr", "código qr", "generador", "wifi", "enlace", "url", "email",
            "teléfono", "sms", "svg", "png",
        ),
        route="/generador-qr",
        status="available",
        featured=True,
    ),
    Tool(
        slug="link-whatsapp",
        name="Enlace y QR de WhatsApp",
        description="Genera un enlace wa.me con el mensaje ya escrito y descarga su código QR.",
        category="productividad",
        icon="🔗",
        keywords=("whatsapp", "wa.me", "enlace", "qr", "código qr", "negocio"),
        route="/link-whatsapp",
        status="available",
        featured=True,
    ),
    Tool(
        slug="acortar-enlaces",
        name="Acortar enlaces",
        description="Crea enlaces cortos y compártelos con un solo clic.",
        category="productividad",
        icon="✳️",
        keywords=("acortar", "enlace", "url", "link"),
    ),
)


def tool_by_slug(slug: str) -> Tool | None:
    return next((tool for tool in TOOLS if tool.slug == slug), None)


def category_by_slug(slug: str) -> Category | None:
    return next((category for category in CATEGORIES if category.slug == slug), None)


def localized_category(category: Category, lang: str = i18n.DEFAULT_LANG) -> Category:
    """Devuelve la categoría con nombre y descripción en el idioma pedido."""
    if i18n.normalize_lang(lang) == i18n.DEFAULT_LANG:
        return category
    return replace(
        category,
        name=i18n.tr(lang, f"catalog.categories.{category.slug}.name", category.name),
        description=i18n.tr(
            lang,
            f"catalog.categories.{category.slug}.description",
            category.description,
        ),
    )


def localized_tool(tool: Tool, lang: str = i18n.DEFAULT_LANG) -> Tool:
    """Devuelve la herramienta traducida y con su ruta bajo ``/en`` si toca."""
    if i18n.normalize_lang(lang) == i18n.DEFAULT_LANG:
        return tool
    catalog = i18n.get_translations(lang).get("catalog", {})
    tools = catalog.get("tools", {}) if isinstance(catalog, dict) else {}
    data = tools.get(tool.slug, {}) if isinstance(tools, dict) else {}
    keywords = data.get("keywords") if isinstance(data, dict) else None
    return replace(
        tool,
        name=i18n.tr(lang, f"catalog.tools.{tool.slug}.name", tool.name),
        description=i18n.tr(
            lang, f"catalog.tools.{tool.slug}.description", tool.description
        ),
        keywords=tuple(keywords) if isinstance(keywords, list) else tool.keywords,
        route=i18n.localize_path(lang, tool.route) if tool.route else None,
    )


def localized_categories(lang: str = i18n.DEFAULT_LANG) -> tuple[Category, ...]:
    return tuple(localized_category(category, lang) for category in CATEGORIES)


def localized_tools(lang: str = i18n.DEFAULT_LANG) -> tuple[Tool, ...]:
    return tuple(localized_tool(tool, lang) for tool in TOOLS)


def category_name(slug: str, lang: str = i18n.DEFAULT_LANG) -> str:
    category = category_by_slug(slug)
    if category is None:
        return slug
    return localized_category(category, lang).name


def available_tools(lang: str = i18n.DEFAULT_LANG) -> tuple[Tool, ...]:
    if i18n.normalize_lang(lang) != i18n.DEFAULT_LANG:
        return tuple(tool for tool in localized_tools(lang) if tool.available)
    return tuple(tool for tool in TOOLS if tool.available)


def featured_tools(lang: str = i18n.DEFAULT_LANG) -> tuple[Tool, ...]:
    return tuple(tool for tool in available_tools(lang) if tool.featured)


def related_tools(
    slug: str, limit: int = 2, lang: str = i18n.DEFAULT_LANG
) -> tuple[Tool, ...]:
    """Herramientas disponibles que complementan a la indicada.

    Primero las de la misma categoría y después el resto, para que una página de
    productividad (por ejemplo) siga teniendo relaciones útiles.
    """
    current = tool_by_slug(slug)
    candidates = [tool for tool in available_tools(lang) if tool.slug != slug]
    if current is not None:
        same = [tool for tool in candidates if tool.category == current.category]
        rest = [tool for tool in candidates if tool.category != current.category]
        candidates = same + rest
    return tuple(candidates[:limit])
