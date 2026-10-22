"""Modelos de entrada de la API (Pydantic)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WhatsAppQrRequest(BaseModel):
    """Enlace de WhatsApp que hay que convertir en código QR."""

    link: str = Field(..., min_length=12, max_length=1500)
