"""Registro único del catálogo de herramientas.

La portada, el directorio `/herramientas` y los bloques de herramientas
relacionadas se generan desde aquí. Añadir una herramienta nueva consiste en
añadir una entrada a ``TOOLS`` y crear su ruta en ``videodl/pages.py``: no hay
listas duplicadas en HTML ni en JavaScript.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

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
    Category("pdf", "PDF", "📄", "Une, comprime y organiza documentos PDF."),
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
        description="Combina varios documentos en un solo PDF ordenado.",
        category="pdf",
        icon="📑",
        keywords=("pdf", "unir", "combinar", "documentos"),
    ),
    Tool(
        slug="comprimir-pdf",
        name="Comprimir PDF",
        description="Reduce el peso de un PDF para enviarlo por correo o WhatsApp.",
        category="pdf",
        icon="📉",
        keywords=("pdf", "comprimir", "reducir", "peso"),
    ),
    # --- Productividad -----------------------------------------------------
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


def category_name(slug: str) -> str:
    category = category_by_slug(slug)
    return category.name if category else slug


def available_tools() -> tuple[Tool, ...]:
    return tuple(tool for tool in TOOLS if tool.available)


def featured_tools() -> tuple[Tool, ...]:
    return tuple(tool for tool in available_tools() if tool.featured)


def related_tools(slug: str, limit: int = 2) -> tuple[Tool, ...]:
    """Herramientas disponibles que complementan a la indicada.

    Primero las de la misma categoría y después el resto, para que una página de
    productividad (por ejemplo) siga teniendo relaciones útiles.
    """
    current = tool_by_slug(slug)
    candidates = [tool for tool in available_tools() if tool.slug != slug]
    if current is not None:
        same = [tool for tool in candidates if tool.category == current.category]
        rest = [tool for tool in candidates if tool.category != current.category]
        candidates = same + rest
    return tuple(candidates[:limit])
