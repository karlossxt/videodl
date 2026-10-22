# VideoDL Tools

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/karlossxt/videodl)

Plataforma de multiherramientas gratuitas en español. **Solo procesa archivos que
sube el usuario**: comprime un vídeo para enviarlo por WhatsApp o Discord, recorta un
clip vertical listo para TikTok, Reels y Shorts, o crea un enlace de WhatsApp con
mensaje y código QR.

> **La descarga desde plataformas externas se ha retirado.** VideoDL Tools ya no usa
> yt-dlp, ni cookies, ni proxies, ni tokens anti-bot. Las rutas antiguas de descarga
> responden `410 Gone` y la portada solo enlaza a las herramientas activas.

## Herramientas

| Página | Para qué sirve |
|---|---|
| `/` | Portada con buscador instantáneo, categorías, herramientas destacadas y catálogo completo. |
| `/herramientas` | Directorio reutilizable con el mismo catálogo, búsqueda y filtros. |
| `/comprimir-video-whatsapp` | **Comprimir vídeo** para que entre en los límites de WhatsApp (16 MB), Discord (10 MB), Telegram, el correo o un tamaño que tú elijas. |
| `/recortar-clip-vertical` | **Recortar clips verticales** (9:16) a partir de un archivo propio, con recorte centrado o fondo desenfocado, listos para TikTok, Reels y Shorts. |
| `/link-whatsapp` | **Generar un enlace de WhatsApp** (`wa.me`) con el mensaje ya escrito, y descargarlo como **código QR**. |
| `/legal` | Aviso legal, privacidad, términos de uso y contacto. |

El catálogo vive en `videodl/catalog.py`: la portada, el directorio y las herramientas
relacionadas se generan desde ahí. Las herramientas aún no implementadas aparecen como
**Próximamente**, sin enlace ni página vacía.

## Características

- 🗜️ **Compresor de vídeo**: calcula el bitrate disponible para el tamaño objetivo,
  baja la resolución solo cuando hace falta (respetando el vídeo vertical) y, si el
  archivo ya cabe y es H.264/AAC, lo entrega **sin recodificar**.
- 🎚️ **Modo «priorizar calidad»**: recodifica con CRF sin forzar el tamaño objetivo.
- ✂️ **Clips verticales**: recorte por segundo, formatos 9:16 (recorte centrado o
  fondo desenfocado), 1:1 y original, con calidad ajustable.
- 🔗 **Enlaces de WhatsApp**: enlace `wa.me` con mensaje y **código QR** en PNG.
- 📊 **Progreso en vivo** de compresión y clips, con opción de cancelar.
- 🧹 **Limpieza automática**: los archivos viven en una carpeta temporal y se borran
  al descargarlos o en la limpieza periódica del servidor.
- 🚦 **Límites de recursos**: tamaño de subida, duración de clip, peticiones por IP y
  trabajos simultáneos configurables por entorno.
- 🖥️ **Interfaz web** oscura con **modo claro opcional**, responsive y sin frameworks
  en el frontend.
- 🔎 **Buscador y filtros instantáneos** por categoría, con versión funcional sin
  JavaScript mediante parámetros `q` y `categoria`.
- 🔗 **Navegación compartida** entre páginas (cabecera, pie, tema y menú móvil).
- 🧭 **SEO técnico**: canonical y Open Graph por página, `sitemap.xml`, `robots.txt` y
  URL pública configurable con `SITE_URL`.
- 📢 **Espacios publicitarios preparados** en el HTML y el CSS, sin anuncios ni
  scripts de terceros activos.
- 🐳 **Listo para desplegar**: `Dockerfile`, `docker-compose.yml` y plantillas para
  Render y Railway.
- ✅ Mensajes de error claros en español y cabeceras de seguridad (CSP, nosniff,
  frame-ancestors…).

## Requisitos

- Python 3.10 o superior
- **ffmpeg** y **ffprobe** (compresión, clips y lectura de metadatos)

En Windows, con [winget](https://learn.microsoft.com/windows/package-manager/winget/):

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg
```

## Instalación

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload
```

Abre <http://127.0.0.1:8000>. La configuración es opcional: copia `.env.example` a
`.env` si quieres cambiar límites o el preset de x264.

### Docker

```bash
docker build -t videodl .
docker run --rm -p 8000:8000 videodl
```

O con Compose:

```bash
docker compose up --build
```

## API

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/health` | Estado y capacidades activas (sin secretos). |
| `GET` | `/api/compress/presets` | Presets de compresión y límite de subida. |
| `POST` | `/api/compress` | Sube un vídeo y crea un trabajo de compresión. |
| `GET` | `/api/compress/{id}` | Estado y progreso del trabajo. |
| `GET` | `/api/compress/{id}/file` | Descarga el resultado y libera el trabajo. |
| `POST` | `/api/compress/{id}/cancel` | Cancela un trabajo en curso. |
| `GET` | `/api/clips/options` | Formatos, calidades y duración máxima de clip. |
| `POST` | `/api/clips/upload` | Sube un vídeo y crea un clip. |
| `GET` | `/api/clips/{id}` | Estado y progreso del clip. |
| `GET` | `/api/clips/{id}/file` | Descarga el clip terminado. |
| `POST` | `/api/clips/{id}/cancel` | Cancela un clip en curso. |
| `POST` | `/api/whatsapp/qr` | Devuelve un PNG con el QR de un enlace `wa.me`. |

Las antiguas rutas de descarga (`/api/info`, `/api/download`, `/api/jobs…`,
`/api/subtitles`, `/api/thumbnail` y `POST /api/clips`) responden **`410 Gone`** con
una explicación, para no dejar endpoints huérfanos.

`/api/health` publica únicamente capacidades activas y límites públicos:

```json
{
  "status": "ok",
  "version": "3.1.0",
  "ffmpeg": true,
  "ffprobe": true,
  "compressor": true,
  "clips": true,
  "whatsapp": true,
  "clip_max_seconds": 300,
  "max_upload_mb": 200,
  "max_target_mb": 200
}
```

## Variables de entorno

Todas son opcionales; los valores inválidos se avisan por logging y se sustituyen por
el valor por defecto.

| Variable | Por defecto | Para qué |
|---|---|---|
| `PORT` | `8000` | Puerto de escucha. |
| `LOG_LEVEL` | `INFO` | Nivel de logging. |
| `SITE_URL` | `http://localhost:8000` | URL pública sin barra final para canonical, Open Graph, sitemap y robots. En Render se usa `RENDER_EXTERNAL_URL` si no se define. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Proxies de confianza para `X-Forwarded-For`. |
| `RATE_LIMIT_PER_MINUTE` | `60` | Peticiones por minuto y por IP (`0` = sin límite). |
| `MAX_CONCURRENT_JOBS` | `4` | Compresiones/clips simultáneos. |
| `MAX_UPLOAD_MB` | `200` | Tamaño máximo de archivo subido. |
| `COMPRESS_MAX_TARGET_MB` | `200` | Tope del tamaño objetivo del compresor. |
| `X264_PRESET` | `veryfast` | Preset de x264 (`ultrafast`…`placebo`). |
| `CLIP_MAX_SECONDS` | `300` | Duración máxima de un clip. |
| `FFMPEG_TIMEOUT_SECONDS` | `3600` | Tiempo máximo de un proceso ffmpeg (`0` = sin límite). |
| `CORS_ORIGINS` | vacío | Orígenes CORS separados por comas. |
| `CONTENT_SECURITY_POLICY` | CSP por defecto | CSP personalizada; vacía la desactiva. |

## Pruebas y calidad

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
```

Las pruebas de extremo a extremo generan vídeos de prueba con ffmpeg y se saltan si
`ffmpeg`/`ffprobe` no están instalados. `tests/test_site.py` valida el catálogo, los
enlaces internos, la búsqueda, la navegación móvil, la accesibilidad básica, el modo
claro y el SEO técnico. El CI (`.github/workflows/ci.yml`) ejecuta ruff, pytest y un
build de Docker con comprobación de `/api/health`.

## Estructura

```
videodl/
  app.py         # create_app, middlewares, /api/health, montaje de estáticos
  catalog.py     # registro único de categorías, herramientas y estados
  views.py       # cabecera, navegación, tarjetas, portada, directorio y SEO
  pages.py       # rutas HTML amigables, alias 301, sitemap.xml y robots.txt
  config.py      # variables de entorno validadas y detección de ffmpeg
  compressor.py  # compresión por tamaño objetivo o calidad
  clips.py       # clips verticales a partir de archivos subidos
  whatsapp.py    # validación de enlaces y QR
  media.py       # ffmpeg/ffprobe
  tasks.py       # lanzador de trabajos en segundo plano
  jobs.py        # almacén de trabajos en memoria con TTL
  legacy.py      # rutas retiradas (410 Gone)
static/          # HTML de herramientas, CSS y JS sin frameworks
tests/           # pruebas unitarias, de API, de sitio y e2e con ffmpeg
```

## Despliegue

- **Render**: `render.yaml` crea el servicio desde el Dockerfile.
- **Railway**: `railway.json` usa el Dockerfile y `/api/health` como healthcheck.
- **Docker Compose**: `docker-compose.yml` con límites de CPU/RAM y healthcheck.

La app debe correr con **un solo worker**: el progreso de los trabajos vive en
memoria y todas las peticiones de un trabajo tienen que atenderlas el mismo proceso.

## Uso responsable

Sube solo contenido que te pertenezca o que puedas utilizar libremente. Consulta el
[aviso legal y la política de privacidad](/legal) para más detalle.

## Licencia

MIT.
