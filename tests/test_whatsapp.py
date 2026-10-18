"""Pruebas del generador de enlaces de WhatsApp (código QR)."""

import pytest
from fastapi import HTTPException

from videodl.whatsapp import make_qr_png, validate_whatsapp_link

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------


def test_whatsapp_page_ok(client):
    res = client.get("/link-whatsapp")
    assert res.status_code == 200
    # La página explica el formato de enlace que genera.
    assert "wa.me" in res.text


def test_whatsapp_page_alias(client):
    res = client.get("/generador-enlace-whatsapp")
    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Código QR
# ---------------------------------------------------------------------------


def test_qr_returns_png(client):
    res = client.post("/api/whatsapp/qr", json={"link": "https://wa.me/34600123456"})
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content.startswith(PNG_MAGIC)
    assert len(res.content) > 200


def test_qr_with_message(client):
    link = "https://wa.me/34600123456?text=Hola%2C%20quiero%20informaci%C3%B3n"
    res = client.post("/api/whatsapp/qr", json={"link": link})
    assert res.status_code == 200
    assert res.content.startswith(PNG_MAGIC)


def test_qr_without_number(client):
    """El enlace sin número fijo (para compartir) también se puede codificar."""
    res = client.post("/api/whatsapp/qr", json={"link": "https://wa.me/?text=Hola"})
    assert res.status_code == 200
    assert res.content.startswith(PNG_MAGIC)


def test_qr_accepts_long_message(client):
    """Un mensaje largo tiene que caber igualmente en un QR."""
    link = "https://wa.me/34600123456?text=" + "a" * 400
    res = client.post("/api/whatsapp/qr", json={"link": link})
    assert res.status_code == 200
    assert res.content.startswith(PNG_MAGIC)


def test_qr_rejects_foreign_host(client):
    res = client.post("/api/whatsapp/qr", json={"link": "https://example.com/?text=Hola"})
    assert res.status_code == 400
    # No debe servir como generador de QR genérico.
    assert "WhatsApp" in res.json()["detail"]


def test_qr_rejects_insecure_scheme(client):
    res = client.post("/api/whatsapp/qr", json={"link": "http://wa.me/34600123456"})
    assert res.status_code == 400


def test_qr_rejects_missing_link(client):
    res = client.post("/api/whatsapp/qr", json={})
    assert res.status_code == 422


def test_qr_rejects_too_long_link(client):
    res = client.post("/api/whatsapp/qr", json={"link": "https://wa.me/" + "9" * 1600})
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Unidades
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "link",
    [
        "https://wa.me/34600123456",
        "https://api.whatsapp.com/send?phone=34600123456",
        "https://chat.whatsapp.com/abcdef",
    ],
)
def test_validate_accepts_whatsapp_links(link):
    assert validate_whatsapp_link(link) == link


@pytest.mark.parametrize(
    "link",
    [
        "",
        "   ",
        "https://wa.me.evil.com/34600123456",
        "https://example.com",
        "javascript:alert(1)",
        "http://wa.me/34600123456",
    ],
)
def test_validate_rejects_other_links(link):
    with pytest.raises(HTTPException) as excinfo:
        validate_whatsapp_link(link)
    assert excinfo.value.status_code == 400


def test_validate_strips_whitespace():
    assert validate_whatsapp_link("  https://wa.me/34600123456  ") == "https://wa.me/34600123456"


def test_make_qr_png_is_a_png():
    data = make_qr_png("https://wa.me/34600123456")
    assert data.startswith(PNG_MAGIC)
