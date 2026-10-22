"""VideoDL: suite de herramientas de vídeo sobre archivos propios.

El paquete está dividido en módulos pequeños y con una única responsabilidad:

  config    -> variables de entorno validadas y detección de ffmpeg
  utils     -> utilidades puras (nombres de archivo, tamaños, limpieza)
  security  -> rate limit y límite de trabajos simultáneos
  jobs      -> almacén genérico de trabajos en memoria con TTL
  media     -> envoltorios de ffmpeg/ffprobe
  tasks     -> lanzador de trabajos en segundo plano
  catalog   -> registro único de herramientas y categorías
  views     -> navegación, tarjetas, portada, directorio y SEO
  pages     -> rutas HTML, alias canónicos, sitemap y robots
  compressor, clips, whatsapp -> routers de la API
  legacy    -> rutas retiradas del antiguo descargador (410 Gone)
  app       -> creación de la aplicación FastAPI
"""

__version__ = "3.1.0"

__all__ = ["__version__"]
