"""Modelos de entrada de la API (Pydantic)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WhatsAppQrRequest(BaseModel):
    """Enlace de WhatsApp que hay que convertir en código QR."""

    link: str = Field(..., min_length=12, max_length=1500)


class QrRequest(BaseModel):
    """Contenido y apariencia de un código QR genérico."""

    data: str = Field(..., min_length=1, max_length=1200)
    size: int = Field(512, ge=128, le=1024)
    margin: int = Field(3, ge=0, le=10)
    error: str = "m"
    dark: str = "#000000"
    light: str = "#ffffff"
    format: str = "png"
