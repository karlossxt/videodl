# VideoDL — imagen de producción (FastAPI + ffmpeg)
# La imagen base va fijada a una versión/distro concretas para builds reproducibles.
FROM python:3.12-slim-bookworm

# ffmpeg/ffprobe son imprescindibles: comprimir, recortar y leer metadatos.
# curl se usa solo para el HEALTHCHECK.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Dependencias primero (mejor caché de capas)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Usuario sin privilegios.
RUN useradd --create-home --uid 10001 appuser

# Código de la aplicación
COPY --chown=appuser:appuser main.py ./
COPY --chown=appuser:appuser videodl ./videodl
COPY --chown=appuser:appuser static ./static

USER appuser

EXPOSE 8000

# Comprueba que el servicio responde (Render/Railway usan /api/health; esto cubre
# también "docker run" directo y Docker Compose).
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/health" > /dev/null || exit 1

# Un solo worker a propósito: el progreso de los trabajos vive en memoria, así que
# todas las peticiones de un trabajo deben atenderlas el mismo proceso.
# `exec` garantiza que uvicorn reciba SIGTERM (apagado ordenado de ffmpeg).
# FORWARDED_ALLOW_IPS controla de qué proxy se acepta X-Forwarded-For.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1}"]
