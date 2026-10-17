"""Modelos de entrada de la API (Pydantic)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class InfoRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)


class DownloadRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    mode: str = "best"  # "best" | "audio" | "video-<height>"
    title: str | None = None  # solo para nombrar el archivo
    start: float | None = Field(default=None, ge=0)  # recorte: segundo inicial
    end: float | None = Field(default=None, gt=0)  # recorte: segundo final


class SubtitleRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    lang: str = Field(..., min_length=2, max_length=20)
    format: str = "srt"  # "srt" | "vtt"
    title: str | None = None


class JobRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    mode: str = "best"
    title: str | None = None
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, gt=0)


class ClipRequest(BaseModel):
    """Fragmento de un vídeo en línea para convertirlo en clip vertical."""

    url: str = Field(..., min_length=8, max_length=2048)
    start: float = Field(default=0, ge=0)
    end: float = Field(..., gt=0)
    aspect: str = "vertical"  # vertical | vertical-blur | square | original
    quality: str = "media"  # alta | media | baja
    title: str | None = None
