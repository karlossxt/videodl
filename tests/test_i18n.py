"""Pruebas de internacionalización, rutas con prefijo y SEO bilingüe."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from videodl import i18n, views

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "videodl" / "locales"

PAGES = (
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
    "/privacidad",
)


def _english(path: str) -> str:
    return f"/en/{path.lstrip('/')}" if path != "/" else "/en/"


def test_locales_tienen_la_misma_estructura_y_catalogo_completo():
    es = json.loads((LOCALES / "es.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))

    assert set(es) == set(en)
    assert es["meta"].keys() == en["meta"].keys()
    assert es["catalog"]["tools"].keys() == en["catalog"]["tools"].keys()
    assert es["js"].keys() == en["js"].keys()
    assert en["html"], "el mapa de plantillas estáticas no puede estar vacío"

    for key in es["catalog"]["tools"]:
        assert en["catalog"]["tools"][key]["name"].strip()
        assert en["catalog"]["tools"][key]["description"].strip()


def test_las_claves_js_usadas_existen_en_ambos_locales():
    es = json.loads((LOCALES / "es.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    scripts = (
        "common.js",
        "site.js",
        "tools.js",
        "image-tools.js",
        "imagenes.js",
        "pdf-suite.js",
        "pdf-core.js",
        "qr-core.js",
        "comprimir.js",
        "clips.js",
        "qr.js",
        "whatsapp.js",
        "transcribe.js",
    )

    def resolve(data, key):
        for part in key.split("."):
            if not isinstance(data, dict) or part not in data:
                return None
            data = data[part]
        return data

    used = set()
    for name in scripts:
        text = (ROOT / "static" / name).read_text(encoding="utf-8")
        used.update(re.findall(r"\b(?:t|tr|translate)\(\s*[\"']([^\"']+)", text))

    for lang, data in (("es", es), ("en", en)):
        for key in used:
            value = resolve(data.get("js", {}), key) or resolve(data, key)
            assert isinstance(value, str) and value.strip(), (lang, key)


def test_translate_html_deja_intactos_los_comentarios():
    i18n.load_translations()
    source = (
        "<p>Paso 1 · Elige el vídeo</p>"
        "<!-- El campo va fuera: un <button> es HTML inválido -->"
        "<p>Paso 2 · Ajusta el resultado</p>"
    )
    translated = i18n.translate_html(source, "en")
    assert "<!-- El campo va fuera: un <button> es HTML inválido -->" in translated
    assert "Step 1 · Choose the video" in translated
    assert "Step 2 · Adjust the result" in translated

    attrs = (
        '<script>const x = \'title="Elegir o arrastrar un vídeo"\';</script>'
        '<div aria-label="Elegir o arrastrar un vídeo"></div>'
    )
    translated = i18n.translate_html(attrs, "en")
    assert 'const x = \'title="Elegir o arrastrar un vídeo"\'' in translated
    assert 'aria-label="Choose or drag a video"' in translated


def test_i18n_carga_y_devuelve_el_idioma_pedido():
    i18n.load_translations()
    assert i18n.normalize_lang("EN") == "en"
    assert i18n.normalize_lang("fr") == "en"
    assert i18n.t("en", "common.search_button") == "Search"
    assert i18n.t("es", "common.search_button") == "Buscar"
    assert i18n.tr("en", "clave.inexistente", "fallback") == "fallback"
    assert i18n.localize_path("en", "/") == "/en/"
    assert i18n.localize_path("en", "/herramientas") == "/en/herramientas"
    assert i18n.localize_path("es", "/herramientas") == "/herramientas"
    assert i18n.unlocalize_path("/en/unir-pdf") == "/unir-pdf"


@pytest.mark.parametrize("path", PAGES)
def test_version_inglesa_tiene_html_lang_y_hreflang(client, path):
    text = client.get(_english(path)).text

    assert '<html lang="en"' in text
    assert 'hreflang="es"' in text
    assert 'hreflang="en"' in text
    assert 'hreflang="x-default"' in text
    assert 'property="og:locale" content="en_US"' in text
    assert "<title>" in text
    assert "window.I18N_STRINGS" in text


@pytest.mark.parametrize("path", PAGES)
def test_version_espanola_conserva_lang_y_hreflang(client, path):
    text = client.get(path).text

    assert '<html lang="es"' in text
    assert 'hreflang="es"' in text
    assert 'hreflang="en"' in text
    assert 'hreflang="x-default"' in text
    assert 'property="og:locale" content="es_ES"' in text


def test_portada_inglesa_esta_traducida_y_enlaza_al_catalogo_ingles(client):
    text = client.get("/en/").text
    assert "All your tools in one place" in text
    assert "Featured tools" in text
    assert "All tools" in text
    assert "Todas las herramientas" not in text
    assert 'href="/en/comprimir-video-whatsapp"' in text
    assert 'action="/en/"' in text
    assert 'placeholder="Search: compress, clip, PDF, audio…"' in text


def test_directorio_ingles_filtra_y_muestra_categorias_traducidas(client):
    text = client.get("/en/herramientas?categoria=pdf").text
    assert "Tools directory" in text
    assert "PDF" in text
    assert "Video" in text
    assert "Compress video" in text
    assert 'action="/en/herramientas"' in text
    assert 'class="category-chip is-active"' in text


def test_pagina_estatica_inglesa_traduce_el_cuerpo(client):
    text = client.get("/en/comprimir-video-whatsapp").text
    assert "Compress video for WhatsApp, Discord or email" in text
    assert "Step 1" in text
    assert "Paso 1" not in text
    assert 'aria-label="Choose or drag a video"' in text


def test_paginas_de_imagen_y_pdf_traducen_su_contenido(client):
    image = client.get("/en/comprimir-imagen").text
    pdf = client.get("/en/unir-pdf").text
    assert "Compress images without uploading them to the internet" in image
    assert "Elige la imagen" not in image
    assert "Join PDF in the order you want" in pdf
    assert "Elige los documentos" not in pdf


@pytest.mark.parametrize(
    ("path", "location"),
    [
        ("/en", "/en/"),
        ("/es", "/"),
        ("/es/", "/"),
        ("/es/comprimir", "/comprimir-video-whatsapp"),
        ("/en/comprimir", "/en/comprimir-video-whatsapp"),
        ("/en/clips-verticales", "/en/recortar-clip-vertical"),
        ("/en/generador-enlace-whatsapp", "/en/link-whatsapp"),
        ("/legal", "/privacidad"),
        ("/en/legal", "/en/privacidad"),
        ("/es/legal", "/privacidad"),
    ],
)
def test_redirecciones_de_idioma_y_alias(client, path, location):
    res = client.get(path, follow_redirects=False)
    assert res.status_code == 301
    assert res.headers["location"] == location


def test_redireccion_de_idioma_conserva_la_query(client):
    res = client.get("/es/?q=pdf", follow_redirects=False)
    assert res.status_code == 301
    assert res.headers["location"] == "/?q=pdf"


def test_canonical_y_urls_alternativas_apuntan_a_cada_idioma(client):
    es = client.get("/unir-pdf").text
    en = client.get("/en/unir-pdf").text
    site = views.site_url()

    assert f'<link rel="canonical" href="{site}/unir-pdf" />' in es
    assert f'<link rel="canonical" href="{site}/en/unir-pdf" />' in en
    assert f'<link rel="alternate" hreflang="es" href="{site}/unir-pdf" />' in en
    assert (
        f'<link rel="alternate" hreflang="en" href="{site}/en/unir-pdf" />' in es
    )
    assert (
        f'<link rel="alternate" hreflang="x-default" href="{site}/en/unir-pdf" />'
        in es
    )


def test_sitemap_incluye_ambas_variantes_y_alternativas(client):
    res = client.get("/sitemap.xml")
    site = views.site_url()
    assert f"{site}/en/" in res.text
    assert f"{site}/en/herramientas" in res.text
    assert f"{site}/en/transcribir-audio" in res.text
    assert 'xmlns:xhtml="http://www.w3.org/1999/xhtml"' in res.text
    assert f'<xhtml:link rel="alternate" hreflang="es" href="{site}/herramientas" />' in res.text


def test_privacidad_inglesa_tambien_es_noindex(client):
    text = client.get("/en/privacidad").text
    assert '<meta name="robots" content="noindex, follow" />' in text
    assert '<html lang="en"' in text
    assert "What happens to your files and data" in text
    assert "Archivos y datos" not in text


def test_csp_permite_el_script_inline_por_hash(client):
    res = client.get("/en/")
    csp = res.headers.get("content-security-policy", "")
    assert "script-src 'self'" in csp
    assert "'sha256-" in csp
    assert "window.I18N_STRINGS" in res.text


def test_selector_de_idioma_conserva_la_pagina_actual(client):
    text = client.get("/en/unir-pdf").text
    assert 'href="/unir-pdf" hreflang="es"' in text
    assert 'href="/en/unir-pdf" hreflang="en" lang="en" aria-current="true"' in text
    assert ">ES</a>" in text
    assert ">EN</a>" in text


def test_la_cabecera_generada_no_se_retraduce(client):
    text = client.get("/en/comprimir-imagen").text
    assert ">Clips</a>" in text
    assert '<span class="brand-mark" aria-hidden="true">F</span>' in text
    assert 'Fas<span class="accent">Tools</span>' in text


def test_los_textos_estaticos_se_traducen_sin_tocar_code_y_pre(client):
    text = client.get("/en/generador-qr").text
    assert "<code>" in text
    # El mapa no debe romper el contenido de bloques técnicos.
    assert re.search(r"<code>.*?</code>", text, re.S)
