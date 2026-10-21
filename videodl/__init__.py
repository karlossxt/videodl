"""VideoDL: suite de herramientas de vÃ­deo (descarga, compresiÃ³n y clips).

El paquete estÃ¡ dividido en mÃ³dulos pequeÃ±os y con una Ãºnica responsabilidad:

  config    -> variables de entorno validadas, detecciÃ³n de ffmpeg y cookies
  utils     -> utilidades puras (nombres de archivo, tamaÃ±os, limpieza)
  errors    -> traducciÃ³n de errores tÃ©cnicos a mensajes para el usuario
  security  -> validaciÃ³n de URLs, protecciÃ³n SSRF, rate limit y concurrencia
  jobs      -> almacÃ©n genÃ©rico de trabajos en memoria con TTL
  media     -> envoltorios de ffmpeg/ffprobe y opciones de yt-dlp
  downloader, compressor, clips -> routers de la API
  app       -> creaciÃ³n de la aplicaciÃ³n FastAPI
"""

__version__ = "2.3.2"

__all__ = ["__version__"]
