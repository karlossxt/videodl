"""VideoDL: suite de herramientas de vídeo (descarga, compresión y clips).

El paquete está dividido en módulos pequeños y con una única responsabilidad:

  config    -> variables de entorno validadas, detección de ffmpeg y cookies
  utils     -> utilidades puras (nombres de archivo, tamaños, limpieza)
  errors    -> traducción de errores técnicos a mensajes para el usuario
  security  -> validación de URLs, protección SSRF, rate limit y concurrencia
  jobs      -> almacén genérico de trabajos en memoria con TTL
  media     -> envoltorios de ffmpeg/ffprobe y opciones de yt-dlp
  downloader, compressor, clips -> routers de la API
  app       -> creación de la aplicación FastAPI
"""

__version__ = "2.1.2"

__all__ = ["__version__"]
