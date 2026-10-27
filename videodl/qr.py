"""Generador de códigos QR genéricos.

A diferencia del endpoint de WhatsApp, aquí el usuario decide el contenido:
un enlace, texto, una red WiFi, un correo, un teléfono o un SMS. El servidor
solo dibuja la imagen (segno) y no guarda el contenido.
"""

from __future__ import annotations

import io
import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from .models import QrRequest

logger = logging.getLogger("videodl.qr")

router = APIRouter()

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_ERROR_LEVELS = {"l", "m", "q", "h"}
_FORMATS = {"png", "svg"}

# Un QR con más de ~1200 bytes deja de ser legible al imprimirlo en pequeño y
# puede superar la capacidad de la versión 40 con corrección alta.
MAX_DATA_BYTES = 1200
MIN_CONTRAST = 3.0

try:  # segno es Python puro, pero la app debe seguir arrancando sin él.
    import segno

    SEGNO_AVAILABLE = True
except ImportError:  # pragma: no cover - solo si falta la dependencia
    segno = None
    SEGNO_AVAILABLE = False


def _channel_luminance(value: int) -> float:
    channel = value / 255
    return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    """Luminancia relativa (WCAG) de un color ``#rrggbb``."""
    red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return (
        0.2126 * _channel_luminance(red)
        + 0.7152 * _channel_luminance(green)
        + 0.0722 * _channel_luminance(blue)
    )


def contrast_ratio(first: str, second: str) -> float:
    """Relación de contraste WCAG entre dos colores (1 a 21)."""
    high, low = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def validate_style(payload: QrRequest) -> tuple[str, str, str, str]:
    """Valida colores, formato y nivel de corrección; devuelve valores normalizados."""
    dark = payload.dark.strip().lower()
    light = payload.light.strip().lower()
    for color in (dark, light):
        if not _HEX_COLOR.match(color):
            raise HTTPException(
                status_code=400,
                detail="Los colores deben escribirse en formato hexadecimal #rrggbb.",
            )

    if relative_luminance(dark) >= relative_luminance(light):
        raise HTTPException(
            status_code=400,
            detail="Los módulos del QR deben ser más oscuros que el fondo.",
        )
    if contrast_ratio(dark, light) < MIN_CONTRAST:
        raise HTTPException(
            status_code=400,
            detail=(
                "El contraste entre el color del QR y el fondo es demasiado bajo. "
                "Usa negro sobre blanco o colores con más diferencia."
            ),
        )

    error = payload.error.strip().lower()
    if error not in _ERROR_LEVELS:
        raise HTTPException(status_code=400, detail="Nivel de corrección no válido.")

    output = payload.format.strip().lower()
    if output not in _FORMATS:
        raise HTTPException(status_code=400, detail="Formato de salida no válido.")

    return dark, light, error, output


def make_qr_image(
    data: str,
    *,
    size: int = 512,
    margin: int = 3,
    error: str = "m",
    dark: str = "#000000",
    light: str = "#ffffff",
    output: str = "png",
) -> tuple[bytes, str]:
    """Devuelve ``(contenido, media_type)`` para el QR solicitado."""
    if not SEGNO_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="El servidor no puede generar códigos QR ahora mismo.",
        )
    if len(data.encode("utf-8")) > MAX_DATA_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El contenido es demasiado largo para un QR legible "
                f"(máximo {MAX_DATA_BYTES} bytes). Acórtalo o usa un enlace."
            ),
        )

    try:
        qr = segno.make_qr(data, error=error)
    except segno.DataOverflowError as exc:
        raise HTTPException(
            status_code=400,
            detail="El contenido no cabe en un código QR con ese nivel de corrección.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="No se pudo crear el código QR.") from exc

    buffer = io.BytesIO()
    if output == "svg":
        # El SVG se escala al tamaño pedido; sigue siendo vectorial.
        modules = qr.symbol_size(border=margin)[0]
        qr.save(
            buffer,
            kind="svg",
            scale=size / modules,
            border=margin,
            dark=dark,
            light=light,
            xmldecl=True,
        )
        return buffer.getvalue(), "image/svg+xml"

    modules = qr.symbol_size(border=margin)[0]
    scale = max(1, size // modules)
    qr.save(
        buffer,
        kind="png",
        scale=scale,
        border=margin,
        dark=dark,
        light=light,
    )
    return buffer.getvalue(), "image/png"


@router.post("/api/qr")
async def generate_qr(payload: QrRequest):
    """Genera un QR PNG o SVG a partir del contenido y el estilo indicados."""
    dark, light, error, output = validate_style(payload)
    content, media_type = make_qr_image(
        payload.data,
        size=payload.size,
        margin=payload.margin,
        error=error,
        dark=dark,
        light=light,
        output=output,
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'inline; filename="codigo-qr.{output}"',
        },
    )
