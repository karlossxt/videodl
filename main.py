"""Punto de entrada de VideoDL.

El código vive en el paquete ``videodl``; este archivo solo expone la aplicación
para que ``uvicorn main:app`` (y las plataformas de despliegue) sigan funcionando.
"""

from videodl.app import app

__all__ = ["app"]
