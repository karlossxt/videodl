"""Pruebas del generador de códigos QR genérico."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from videodl import qr

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------


def test_qr_page_ok(client):
    res = client.get("/generador-qr")
    assert res.status_code == 200
    assert "Generador de códigos QR" in res.text
    assert "qr-core.js" in res.text
    assert "qr.js" in res.text


def test_qr_page_incluye_tipos_y_descargas(client):
    text = client.get("/generador-qr").text
    for marker in ("WiFi", "Email", "Teléfono", "SMS", "PNG", "SVG", "Descargar QR"):
        assert marker in text


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def test_qr_png(client):
    res = client.post("/api/qr", json={"data": "https://example.com"})
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content.startswith(PNG_MAGIC)
    assert len(res.content) > 200


def test_qr_svg(client):
    res = client.post(
        "/api/qr",
        json={"data": "https://example.com", "format": "svg", "size": 512},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/svg+xml"
    assert b"<svg" in res.content
    assert b"</svg>" in res.content


def test_qr_wifi_payload(client):
    payload = "WIFI:T:WPA;S:MiRed;P:secreto\\;123;;"
    res = client.post("/api/qr", json={"data": payload})
    assert res.status_code == 200
    assert res.content.startswith(PNG_MAGIC)


def test_qr_custom_colors(client):
    res = client.post(
        "/api/qr",
        json={"data": "hola", "dark": "#0b3d91", "light": "#ffffff"},
    )
    assert res.status_code == 200
    assert res.content.startswith(PNG_MAGIC)


@pytest.mark.parametrize("color", ["negro", "#fff", "#12345", "rgb(0,0,0)"])
def test_qr_rejects_bad_colors(client, color):
    res = client.post("/api/qr", json={"data": "hola", "dark": color})
    assert res.status_code == 400
    assert "hexadecimal" in res.json()["detail"]


def test_qr_rejects_inverted_colors(client):
    res = client.post(
        "/api/qr",
        json={"data": "hola", "dark": "#ffffff", "light": "#000000"},
    )
    assert res.status_code == 400
    assert "oscuros" in res.json()["detail"]


def test_qr_rejects_low_contrast(client):
    res = client.post(
        "/api/qr",
        json={"data": "hola", "dark": "#777777", "light": "#888888"},
    )
    assert res.status_code == 400
    assert "contraste" in res.json()["detail"].lower()


def test_qr_rejects_bad_error_level(client):
    res = client.post("/api/qr", json={"data": "hola", "error": "z"})
    assert res.status_code == 400
    assert "corrección" in res.json()["detail"]


def test_qr_rejects_bad_format(client):
    res = client.post("/api/qr", json={"data": "hola", "format": "pdf"})
    assert res.status_code == 400
    assert "Formato" in res.json()["detail"]


def test_qr_rejects_empty_data(client):
    assert client.post("/api/qr", json={"data": ""}).status_code == 422


def test_qr_rejects_too_many_characters(client):
    assert client.post("/api/qr", json={"data": "a" * 1201}).status_code == 422


def test_qr_rejects_too_many_bytes(client):
    """1200 caracteres con acentos superan el límite en bytes, no en caracteres."""
    res = client.post("/api/qr", json={"data": "ñ" * 700})
    assert res.status_code == 400
    assert "bytes" in res.json()["detail"]


def test_qr_rejects_out_of_range_size(client):
    assert client.post("/api/qr", json={"data": "hola", "size": 64}).status_code == 422
    assert client.post("/api/qr", json={"data": "hola", "size": 2048}).status_code == 422


def test_qr_does_not_store_content(client):
    """El contenido no aparece en ninguna respuesta de la API."""
    marker = "contenido-secreto-123456"
    client.post("/api/qr", json={"data": marker})
    health = client.get("/api/health")
    assert marker not in health.text


# ---------------------------------------------------------------------------
# Unidades
# ---------------------------------------------------------------------------


def test_contrast_ratio_extremos():
    assert qr.contrast_ratio("#000000", "#ffffff") == pytest.approx(21, abs=0.01)
    assert qr.contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1, abs=0.01)


def test_validate_style_normaliza_mayusculas():
    from videodl.models import QrRequest

    dark, light, error, output = qr.validate_style(
        QrRequest(data="hola", dark="#000000", light="#FFFFFF", error="H", format="SVG")
    )
    assert dark == "#000000"
    assert light == "#ffffff"
    assert error == "h"
    assert output == "svg"


def test_make_qr_image_sin_segno(monkeypatch):
    monkeypatch.setattr(qr, "SEGNO_AVAILABLE", False)
    with pytest.raises(HTTPException) as excinfo:
        qr.make_qr_image("hola")
    assert excinfo.value.status_code == 503
