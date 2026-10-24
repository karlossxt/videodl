"""Pruebas de las tres herramientas de imagen.

Comprueban el contrato de las páginas (HTML accesible, SEO propio, scripts
compartidos, sin subida al servidor) y ejecutan el motor de validación con Node
cuando está disponible.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from videodl.catalog import tool_by_slug
from videodl.image_pages import IMAGE_MAX_MB, IMAGE_TOOL_CONTENT

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
IMAGE_PAGES = {
    "/comprimir-imagen": "compress",
    "/convertir-imagen": "convert",
    "/redimensionar-imagen": "resize",
}


@pytest.mark.parametrize(("path", "mode"), IMAGE_PAGES.items())
def test_paginas_de_imagen_tienen_estructura_comun_y_modo_correcto(client, path, mode):
    text = client.get(path).text

    assert f'data-image-tool="{mode}"' in text
    assert '<link rel="canonical"' in text
    assert '<meta name="description"' in text
    assert 'property="og:title"' in text
    assert 'http-equiv="Content-Security-Policy"' not in text

    # Navegación y pie compartidos, sin copias.
    assert 'data-nav-toggle' in text
    assert 'data-theme-toggle' in text
    assert 'class="site-footer"' in text
    assert 'href="#main"' in text
    assert 'id="main"' in text

    # Mismo motor y misma interfaz para las tres.
    for script in ("common.js", "image-tools.js", "imagenes.js"):
        assert f'src="{script}"' in text
    assert 'id="file-input"' in text
    assert 'id="dropzone"' in text
    assert 'id="input-preview"' in text
    assert 'id="output-preview"' in text
    assert 'id="download-btn"' in text
    assert 'id="error-box"' in text

    # Herramientas relacionadas generadas desde el catálogo.
    assert "Herramientas relacionadas" in text
    assert 'class="tools-grid tools-grid-compact"' in text

    # Sin formularios ni endpoints de subida.
    assert "<form" not in text
    assert "/api/" not in text
    assert "multipart/form-data" not in text


def test_catalogo_marca_las_tres_herramientas_como_disponibles():
    for slug, route in (
        ("comprimir-imagen", "/comprimir-imagen"),
        ("convertir-imagen", "/convertir-imagen"),
        ("redimensionar-imagen", "/redimensionar-imagen"),
    ):
        tool = tool_by_slug(slug)
        assert tool is not None
        assert tool.available
        assert tool.route == route
        assert tool.category == "imagenes"
        assert tool.featured


def test_textos_clave_de_cada_herramienta(client):
    compress = client.get("/comprimir-imagen").text
    assert "La compresión no garantiza que el archivo resulte más pequeño" in compress
    assert "Calidad" in compress
    assert "jpeg-background" in compress
    assert "transparency-warning" in compress

    convert = client.get("/convertir-imagen").text
    assert "JPG no admite transparencia" in convert
    assert "convert-format" in convert
    assert "AVIF" in convert  # se explica por qué no se admite
    assert "image/avif" not in convert

    resize = client.get("/redimensionar-imagen").text
    assert 'id="size-mode"' in resize
    assert 'id="resize-width"' in resize
    assert 'id="resize-height"' in resize
    assert 'id="resize-percent-width"' in resize
    assert 'id="keep-ratio"' in resize
    assert "Mantener la proporción" in resize


def test_no_hay_codigo_de_subida_en_los_assets_de_imagen():
    library = (STATIC / "image-tools.js").read_text(encoding="utf-8")
    interface = (STATIC / "imagenes.js").read_text(encoding="utf-8")

    for code in (library, interface):
        assert "fetch(" not in code
        assert "XMLHttpRequest" not in code
        assert "FormData" not in code
        assert "/api/" not in code

    # Se liberan las URL temporales y los canvas.
    assert "URL.revokeObjectURL" in interface
    assert 'canvas.width = 0' in library
    assert "pagehide" in interface


def test_el_limite_de_tamano_esta_sincronizado_entre_python_y_javascript():
    js = (STATIC / "image-tools.js").read_text(encoding="utf-8")
    match = re.search(r"const MAX_FILE_BYTES = (\d+) \* 1024 \* 1024;", js)
    assert match, "No se encontró MAX_FILE_BYTES en image-tools.js"
    assert int(match.group(1)) == IMAGE_MAX_MB
    template = (STATIC / "imagen-tool.html").read_text(encoding="utf-8")
    assert "<!-- MAX_MB -->" in template


def test_la_plantilla_compartida_no_deja_marcadores_sin_sustituir(client):
    markers = (
        "<!-- HEAD -->",
        "<!-- NAV -->",
        "<!-- FOOTER -->",
        "<!-- RELATED -->",
        "<!-- MODE -->",
        "<!-- HERO_TITLE -->",
        "<!-- HERO_SUB -->",
        "<!-- HERO_BADGE -->",
        "<!-- MAX_MB -->",
        "<!-- CONTROLS -->",
        "<!-- ACTION_LABEL -->",
        "<!-- ACTION_HINT -->",
        "<!-- SEO_CONTENT -->",
    )
    for path in IMAGE_PAGES:
        text = client.get(path).text
        assert f'<span id="limit-hint-2">{IMAGE_MAX_MB} MB</span>' in text
        for marker in markers:
            assert marker not in text, (path, marker)


def test_los_tres_modos_tienen_contenido_seo_propio():
    titles = {content["hero_title"] for content in IMAGE_TOOL_CONTENT.values()}
    seos = {content["seo"] for content in IMAGE_TOOL_CONTENT.values()}
    assert len(titles) == 3
    assert len(seos) == 3
    assert set(IMAGE_TOOL_CONTENT) == {
        "comprimir-imagen",
        "convertir-imagen",
        "redimensionar-imagen",
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no está instalado")
def test_el_motor_de_imagenes_pasa_las_pruebas_de_node():
    result = subprocess.run(
        ["node", "--test", "tests/image-tools.test.js"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_estilos_de_imagen_presentes_y_responsive():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    for selector in (
        ".image-preview-grid",
        ".image-checker",
        ".image-controls",
        ".warning-box",
        ".size-inputs",
        ".preset-row",
        ".compare-saved.is-increase",
    ):
        assert selector in css
    assert "@media (max-width: 700px)" in css
