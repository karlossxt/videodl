# VideoDL — imagen de producción (FastAPI + yt-dlp + ffmpeg)
# La imagen base va fijada a una versión/distro concretas para builds reproducibles.
FROM python:3.12-slim-bookworm

# ffmpeg es imprescindible: unir video+audio, convertir a MP3 y recortar fragmentos.
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
# Render monta los Secret Files en /etc/secrets y pertenecen al grupo 1000: si el
# usuario de la app no está en ese grupo, no puede leerlos (aunque el archivo
# exista) y /api/health muestra cookies:false. Se crea el grupo si la imagen base
# no lo trae y se añade el usuario como grupo suplementario.
RUN if getent group 1000 > /dev/null; then : ; else groupadd --gid 1000 appgroup; fi \
    && useradd --create-home --uid 10001 appuser \
    && usermod --append --groups 1000 appuser

# Código de la aplicación
COPY --chown=appuser:appuser main.py ./
COPY --chown=appuser:appuser videodl ./videodl
COPY --chown=appuser:appuser static ./static

USER appuser

# Proveedor de PO tokens de YouTube (bgutil) en modo «script», con el Deno que ya
# instaló «yt-dlp[default,deno]». YouTube exige a las IPs de nube una prueba de
# origen para servir buena parte de sus vídeos; sin ella responde con «Sign in to
# confirm you're not a bot» por mucho que se manden cookies. Se instala en el HOME
# del usuario porque es donde lo busca el plugin, y se deja su caché caliente
# (DENO_DIR y el chequeo de versión) para que la primera descarga no compile nada.
# La versión debe coincidir con la de requirements.txt.
ARG BGUTIL_POT_VERSION=2.0.2
ENV DENO_DIR=/home/appuser/.cache/deno
RUN set -eux; \
    mkdir -p /home/appuser/bgutil-ytdlp-pot-provider; \
    curl -fsSL "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/${BGUTIL_POT_VERSION}.tar.gz" \
        | tar -xz --strip-components=1 -C /home/appuser/bgutil-ytdlp-pot-provider; \
    cd /home/appuser/bgutil-ytdlp-pot-provider/server; \
    deno install --allow-scripts=npm:canvas --frozen; \
    deno run --allow-env --allow-net \
        --allow-ffi=/home/appuser/bgutil-ytdlp-pot-provider/server/node_modules \
        --allow-read=/home/appuser/.cache/bgutil-ytdlp-pot-provider,/home/appuser/bgutil-ytdlp-pot-provider/server/node_modules \
        --allow-write=/home/appuser/.cache/bgutil-ytdlp-pot-provider \
        src/generate_once.ts --version

EXPOSE 8000

# Comprueba que el servicio responde (Render/Railway usan /api/health; esto cubre
# también "docker run" directo y Docker Compose).
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/health" > /dev/null || exit 1

# Un solo worker a propósito: el progreso de las descargas vive en memoria, así que
# todas las peticiones de un trabajo deben atenderlas el mismo proceso.
# `exec` garantiza que uvicorn reciba SIGTERM (apagado ordenado de ffmpeg).
# FORWARDED_ALLOW_IPS controla de qué proxy se acepta X-Forwarded-For.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-127.0.0.1}"]
