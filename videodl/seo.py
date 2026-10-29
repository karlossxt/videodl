"""Datos estructurados (JSON-LD de schema.org) para las páginas indexables.

Solo se describe lo que la página ya muestra y lo que el catálogo declara: el
nombre y la descripción de cada herramienta, su categoría y que es gratuita.
No hay valoraciones, reseñas ni precios inventados. Las páginas ``noindex`` no
llevan datos estructurados.
"""

from __future__ import annotations

import json
from typing import Any

from . import catalog, config, i18n

# Categorías del catálogo -> ``applicationCategory`` admitido por Google.
_APP_CATEGORY = {
    "video": "MultimediaApplication",
    "audio": "MultimediaApplication",
    "imagenes": "MultimediaApplication",
    "pdf": "UtilitiesApplication",
    "productividad": "UtilitiesApplication",
}


def abs_url(path: str, lang: str = i18n.DEFAULT_LANG) -> str:
    """URL absoluta (dominio configurado) de una ruta base en el idioma pedido."""
    return config.SITE_URL.rstrip("/") + i18n.localize_path(lang, path)


def _nav_label(lang: str, key: str, fallback: str) -> str:
    nav = i18n.get_translations(lang).get("nav", {})
    for item in nav.get("items", []) if isinstance(nav, dict) else []:
        if isinstance(item, dict) and item.get("key") == key and item.get("label"):
            return str(item["label"])
    return fallback


def _breadcrumbs(lang: str, trail: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": index, "name": name, "item": url}
            for index, (name, url) in enumerate(trail, start=1)
        ],
    }


def structured_data(meta: Any, lang: str, site_name: str) -> list[dict[str, Any]]:
    """Objetos JSON-LD para una página (vacío si no es indexable)."""
    if not str(meta.robots).lower().startswith("index"):
        return []
    normalized = i18n.normalize_lang(lang)
    home_url = abs_url("/", normalized)
    home_label = _nav_label(normalized, "home", "Inicio")
    tools_label = _nav_label(normalized, "tools", "Herramientas")

    if meta.key == "home":
        return [
            {
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@type": "WebSite",
                        "@id": f"{home_url}#website",
                        "url": home_url,
                        "name": site_name,
                        "description": meta.description,
                        "inLanguage": normalized,
                        "publisher": {"@id": f"{home_url}#organization"},
                    },
                    {
                        "@type": "Organization",
                        "@id": f"{home_url}#organization",
                        "name": site_name,
                        "url": home_url,
                    },
                ],
            }
        ]

    page_url = abs_url(meta.path, normalized)

    if meta.key == "directory":
        items = [
            {
                "@type": "ListItem",
                "position": index,
                "name": tool.name,
                "url": abs_url(tool.route or "", normalized),
            }
            for index, tool in enumerate(catalog.available_tools(normalized), start=1)
        ]
        return [
            {
                "@context": "https://schema.org",
                "@graph": [
                    {
                        "@type": "CollectionPage",
                        "@id": f"{page_url}#page",
                        "url": page_url,
                        "name": meta.title,
                        "description": meta.description,
                        "inLanguage": normalized,
                        "mainEntity": {"@type": "ItemList", "itemListElement": items},
                    },
                    _breadcrumbs(
                        normalized,
                        [(home_label, home_url), (tools_label, page_url)],
                    ),
                ],
            }
        ]

    tool = catalog.tool_by_slug(meta.tool_slug) if meta.tool_slug else None
    if tool is None or not tool.available:
        return []
    tool = catalog.localized_tool(tool, normalized)
    directory_url = abs_url("/herramientas", normalized)
    return [
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "WebApplication",
                    "@id": f"{page_url}#app",
                    "url": page_url,
                    "name": tool.name,
                    "description": meta.description,
                    "applicationCategory": _APP_CATEGORY.get(
                        tool.category, "UtilitiesApplication"
                    ),
                    "operatingSystem": "Any",
                    "inLanguage": normalized,
                    "isAccessibleForFree": True,
                    "offers": {
                        "@type": "Offer",
                        "price": "0",
                        "priceCurrency": "USD",
                    },
                },
                _breadcrumbs(
                    normalized,
                    [
                        (home_label, home_url),
                        (tools_label, directory_url),
                        (tool.name, page_url),
                    ],
                ),
            ],
        }
    ]


def json_ld_html(objects: list[dict[str, Any]]) -> str:
    """``<script type="application/ld+json">`` seguro para incrustar en HTML."""
    tags = []
    for obj in objects:
        payload = (
            json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
        tags.append(f'  <script type="application/ld+json">{payload}</script>')
    return "\n".join(tags)


__all__ = ["abs_url", "json_ld_html", "structured_data"]
