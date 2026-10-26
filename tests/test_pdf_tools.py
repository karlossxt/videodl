"""Pruebas de la suite PDF.

Comprueban el contrato de las cuatro páginas, el catálogo, la ausencia de
subidas al servidor, la integridad de las bibliotecas locales y la
interoperabilidad del ZIP generado en el navegador con el lector de Python.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pytest

from videodl.catalog import TOOLS, tool_by_slug
from videodl.pdf_pages import (
    PDF_MAX_FILES,
    PDF_MAX_IMAGE_PIXELS,
    PDF_MAX_IMAGES,
    PDF_MAX_MB,
    PDF_MAX_PAGES,
    PDF_MAX_RENDER_PAGES,
    PDF_MAX_TOTAL_MB,
    PDF_TOOL_CONTENT,
)

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
VENDOR = STATIC / "vendor" / "pdf"
PDF_PAGES = {
    "/unir-pdf": "merge",
    "/dividir-pdf": "split",
    "/imagenes-a-pdf": "images",
    "/pdf-a-jpg": "jpg",
}


@pytest.mark.parametrize(("path", "mode"), PDF_PAGES.items())
def test_paginas_pdf_tienen_estructura_comun_y_modo_correcto(client, path, mode):
    response = client.get(path)
    assert response.status_code == 200
    text = response.text

    assert f'data-pdf-tool="{mode}"' in text
    assert '<link rel="canonical"' in text
    assert '<meta name="description"' in text
    assert 'property="og:title"' in text
    assert 'http-equiv="Content-Security-Policy"' not in text

    # Navegación, pie y utilidades compartidas.
    assert 'data-nav-toggle' in text
    assert 'data-theme-toggle' in text
    assert 'class="site-footer"' in text
    assert 'href="#main"' in text
    assert 'id="main"' in text
    for script in ("common.js", "image-tools.js", "pdf-core.js", "pdf-suite.js"):
        assert f'src="{script}"' in text
    assert 'type="module" src="pdf-suite.js"' in text

    # Contrato de la interfaz.
    assert 'id="file-input"' in text
    assert 'id="dropzone"' in text
    assert 'id="file-list"' in text
    assert 'id="preview-grid"' in text
    assert 'id="process-btn"' in text
    assert 'id="progress"' in text
    assert 'id="download-btn"' in text
    assert 'id="error-box"' in text

    # Herramientas relacionadas generadas desde el catálogo.
    assert "Herramientas relacionadas" in text
    assert 'class="tools-grid tools-grid-compact"' in text

    # Sin formularios ni endpoints de subida.
    assert "<form" not in text
    assert "/api/" not in text
    assert "multipart/form-data" not in text


def test_catalogo_incluye_las_cuatro_herramientas_pdf():
    expected = {
        "unir-pdf": "/unir-pdf",
        "dividir-pdf": "/dividir-pdf",
        "imagenes-a-pdf": "/imagenes-a-pdf",
        "pdf-a-jpg": "/pdf-a-jpg",
    }
    for slug, route in expected.items():
        tool = tool_by_slug(slug)
        assert tool is not None, slug
        assert tool.available, slug
        assert tool.route == route
        assert tool.category == "pdf"
        assert tool.featured == (slug in {"unir-pdf", "pdf-a-jpg"})
        assert tool.icon.strip() and "?" not in tool.icon
        assert len(tool.description.strip()) > 20

    # La tarjeta del catálogo ya no debe ofrecer un falso "Próximamente" para
    # estas cuatro rutas.
    available_slugs = {tool.slug for tool in TOOLS if tool.available}
    assert expected.keys() <= available_slugs


def test_textos_clave_y_limites_de_cada_modo(client):
    merge = client.get("/unir-pdf").text
    assert "Unir no es comprimir" in merge
    assert "El orden de la lista será el orden del PDF final" in merge
    assert "protegido con contraseña" in merge
    assert "formularios" in merge

    split = client.get("/dividir-pdf").text
    assert 'id="page-ranges"' in split
    assert "1-3, 5, 8-10" in split
    assert "El orden de salida sigue el orden" in split
    assert "no hace OCR" in split or "no se aplica OCR" in split

    images = client.get("/imagenes-a-pdf").text
    assert 'id="page-size"' in images
    assert "JPG o PNG" in images
    assert "transparencia del PNG" in images
    assert "no aplica OCR" in images or "No aplica OCR" in images

    jpg = client.get("/pdf-a-jpg").text
    assert 'id="jpg-quality"' in jpg
    assert 'id="render-scale"' in jpg
    assert "ZIP" in jpg
    assert "no aplica OCR" in jpg or "no ofrece" in jpg
    assert "fondo se pinta en blanco" in jpg or "fondo se pintó en blanco" in jpg

    for path in PDF_PAGES:
        text = client.get(path).text
        assert f"{PDF_MAX_MB} MB" in text
        if path in {"/unir-pdf", "/dividir-pdf"}:
            assert str(PDF_MAX_PAGES) in text
        if path == "/pdf-a-jpg":
            assert str(PDF_MAX_RENDER_PAGES) in text


def test_no_hay_codigo_de_subida_en_los_assets_pdf():
    core = (STATIC / "pdf-core.js").read_text(encoding="utf-8")
    suite = (STATIC / "pdf-suite.js").read_text(encoding="utf-8")
    template = (STATIC / "pdf-tool.html").read_text(encoding="utf-8")
    pages = (ROOT / "videodl" / "pdf_pages.py").read_text(encoding="utf-8")

    for code in (core, suite):
        assert "fetch(" not in code
        assert "XMLHttpRequest" not in code
        assert "FormData" not in code
        assert "/api/" not in code

    # Carga de bibliotecas desde el propio sitio, nunca desde una CDN.
    assert "vendor/pdf/pdf-lib.esm.min.js" in suite
    assert "vendor/pdf/pdf.min.mjs" in suite
    assert "vendor/pdf/pdf.worker.min.mjs" in suite
    assert "cdn." not in template.lower()
    assert "unpkg" not in template.lower()
    assert "jsdelivr" not in template.lower()
    assert "https://" not in pages

    # Se liberan URLs temporales y canvas al cambiar de archivo o salir.
    assert "URL.revokeObjectURL" in suite
    assert "canvas.width = 0" in suite
    assert "pagehide" in suite


def test_limites_sincronizados_entre_python_y_javascript():
    core = (STATIC / "pdf-core.js").read_text(encoding="utf-8")
    expected = {
        "MAX_FILE_BYTES": PDF_MAX_MB,
        "MAX_TOTAL_BYTES": PDF_MAX_TOTAL_MB,
        "MAX_FILES": PDF_MAX_FILES,
        "MAX_IMAGES": PDF_MAX_IMAGES,
        "MAX_PDF_PAGES": PDF_MAX_PAGES,
        "MAX_RENDER_PAGES": PDF_MAX_RENDER_PAGES,
    }
    for name, megabytes in expected.items():
        if name in {"MAX_FILE_BYTES", "MAX_TOTAL_BYTES"}:
            match = re.search(rf"const {name} = (\d+) \* 1024 \* 1024;", core)
            assert match, name
            assert int(match.group(1)) == megabytes
        else:
            match = re.search(rf"const {name} = (\d+);", core)
            assert match, name
            assert int(match.group(1)) == megabytes

    match = re.search(r"const MAX_IMAGE_PIXELS = (\d+) \* 1000 \* 1000;", core)
    assert match
    assert int(match.group(1)) * 1_000_000 == PDF_MAX_IMAGE_PIXELS
    assert (
        f"{PDF_MAX_IMAGE_PIXELS // 1_000_000} megapíxeles"
        in PDF_TOOL_CONTENT["imagenes-a-pdf"]["seo"]
    )


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
        "<!-- STEP_ONE_TITLE -->",
        "<!-- DROP_ARIA -->",
        "<!-- DROP_ICON -->",
        "<!-- DROP_TITLE -->",
        "<!-- DROP_SUB -->",
        "<!-- ACCEPT -->",
        "<!-- MULTIPLE -->",
        "<!-- FILES_TITLE -->",
        "<!-- CONTROLS -->",
        "<!-- ACTION_LABEL -->",
        "<!-- ACTION_HINT -->",
        "<!-- SEO_CONTENT -->",
    )
    for path in PDF_PAGES:
        text = client.get(path).text
        for marker in markers:
            assert marker not in text, (path, marker)


def test_los_cuatro_modos_tienen_contenido_seo_propio():
    assert set(PDF_TOOL_CONTENT) == {
        "unir-pdf",
        "dividir-pdf",
        "imagenes-a-pdf",
        "pdf-a-jpg",
    }
    assert len({content["hero_title"] for content in PDF_TOOL_CONTENT.values()}) == 4
    assert len({content["seo"] for content in PDF_TOOL_CONTENT.values()}) == 4
    assert len({content["action_label"] for content in PDF_TOOL_CONTENT.values()}) == 4


def test_sitemap_incluye_las_cuatro_paginas(client):
    sitemap = client.get("/sitemap.xml").text
    for path in PDF_PAGES:
        assert path in sitemap or path.lstrip("/") in sitemap


def test_csp_permite_worker_local_y_no_cdn():
    from videodl.config import DEFAULT_CONTENT_SECURITY_POLICY

    assert "script-src 'self'" in DEFAULT_CONTENT_SECURITY_POLICY
    assert "worker-src 'self'" in DEFAULT_CONTENT_SECURITY_POLICY
    assert "connect-src 'self'" in DEFAULT_CONTENT_SECURITY_POLICY
    assert "cdn" not in DEFAULT_CONTENT_SECURITY_POLICY.lower()


def test_bibliotecas_locales_tienen_manifest_e_integridad():
    manifest_path = VENDOR / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    versions = {library["name"]: library["version"] for library in manifest["libraries"]}
    assert versions == {"pdf-lib": "1.17.1", "pdfjs-dist": "6.4.299"}
    licenses = {library["name"]: library["license"] for library in manifest["libraries"]}
    assert licenses == {"pdf-lib": "MIT", "pdfjs-dist": "Apache-2.0"}

    declared = manifest["files"]
    actual = {
        path.relative_to(VENDOR).as_posix()
        for path in VENDOR.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    assert set(declared) == actual
    for relative, info in declared.items():
        path = VENDOR / relative
        assert path.is_file()
        assert path.stat().st_size == info["bytes"], relative
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == info["sha256"], relative

    # Los archivos principales existen y no son placeholders vacíos.
    assert (VENDOR / "pdf-lib.esm.min.js").stat().st_size > 100_000
    assert (VENDOR / "pdf.min.mjs").stat().st_size > 100_000
    assert (VENDOR / "pdf.worker.min.mjs").stat().st_size > 500_000
    assert (VENDOR / "standard_fonts").is_dir()
    assert (VENDOR / "cmaps").is_dir()
    assert (VENDOR / "wasm").is_dir()


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no está instalado")
def test_el_nucleo_pdf_pasa_las_pruebas_de_node():
    result = subprocess.run(
        ["node", "--test", "tests/pdf-tools.test.js"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no está instalado")
def test_el_zip_generado_por_el_navegador_se_abre_con_python():
    """El ZIP se construye a mano en JS; Python comprueba que es interoperable."""
    script = """
const fs = require("fs");
const core = require("./static/pdf-core.js");
const zip = core.zipStore(
  [
    { name: "pagina-01.jpg", data: Uint8Array.from([0xff, 0xd8, 0xff, 0xd9]) },
    { name: "pagina-02.jpg", data: Uint8Array.from([0xff, 0xd8, 0x01, 0x02, 0xff, 0xd9]) },
  ],
  { date: new Date(2020, 0, 2, 12, 30, 0) }
);
fs.writeFileSync(process.env.ZIP_OUT, Buffer.from(zip));
"""
    with tempfile.TemporaryDirectory() as temp_dir:
        output = Path(temp_dir) / "resultado.zip"
        env = {**os.environ, "ZIP_OUT": str(output)}
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        with zipfile.ZipFile(output) as archive:
            assert archive.namelist() == ["pagina-01.jpg", "pagina-02.jpg"]
            assert archive.read("pagina-01.jpg") == b"\xff\xd8\xff\xd9"
            assert archive.read("pagina-02.jpg") == b"\xff\xd8\x01\x02\xff\xd9"
            assert archive.testzip() is None


def test_estilos_pdf_presentes_y_responsive():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    for selector in (
        ".pdf-file-list",
        ".pdf-file-item",
        ".pdf-preview-grid",
        ".pdf-preview-frame",
        ".pdf-controls",
        ".pdf-progress",
        ".pdf-result-previews",
        "@media (max-width: 700px)",
    ):
        assert selector in css
