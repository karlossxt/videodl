"""Rutas retiradas del antiguo descargador.

Se mantienen aquí para responder con un 410 Gone explícito en lugar de dejar
endpoints huérfanos o un 405/404 ambiguo. Ninguna de estas rutas procesa URLs ni
sirve archivos: la app solo trabaja con archivos que sube el usuario.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(include_in_schema=False)

_GONE = (
    "La descarga desde plataformas externas se ha retirado. "
    "Fastools solo procesa archivos propios: sube tu vídeo en /comprimir-video-whatsapp "
    "o en /recortar-clip-vertical."
)


def _gone() -> JSONResponse:
    return JSONResponse(status_code=410, content={"detail": _GONE})


@router.post("/api/info")
@router.post("/api/download")
@router.post("/api/jobs")
@router.post("/api/subtitles")
@router.get("/api/thumbnail")
@router.get("/api/jobs/{job_id}")
@router.get("/api/jobs/{job_id}/file")
@router.post("/api/jobs/{job_id}/cancel")
async def removed_download_routes(job_id: str | None = None):
    """Cualquier ruta del descargador antiguo responde 410 Gone."""
    return _gone()


@router.post("/api/clips")
async def removed_url_clips():
    """El recorte desde enlaces también se retiró; solo queda la subida."""
    return _gone()
