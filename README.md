# FasTools.app

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/karlossxt/videodl)

Plataforma de multiherramientas gratuitas en español. **Solo procesa archivos que
aporta el usuario**: comprime un vídeo para enviarlo por WhatsApp o Discord, recorta un
clip vertical listo para TikTok, Reels y Shorts, reduce o convierte imágenes, une o
divide PDF y crea un enlace de WhatsApp con mensaje y código QR.

> **La descarga desde plataformas externas se ha retirado.** FasTools ya no usa
> yt-dlp, ni cookies, ni proxies, ni tokens anti-bot. Las rutas antiguas de descarga
> responden `410 Gone` y la portada solo enlaza a las herramientas activas.

## Herramientas

| Página | Para qué sirve |
|---|---|
| `/` | Portada con buscador instantáneo, categorías, herramientas destacadas y catálogo completo. |
| `/herramientas` | Directorio reutilizable con el mismo catálogo, búsqueda y filtros. |
| `/comprimir-video-whatsapp` | **Comprimir vídeo** para que entre en los límites de WhatsApp (16 MB), Discord (10 MB), Telegram, el correo o un tamaño que tú elijas. |
| `/recortar-clip-vertical` | **Recortar clips verticales** (9:16) a partir de un archivo propio, con recorte centrado o fondo desenfocado, listos para TikTok, Reels y Shorts. |
| `/comprimir-imagen` | **Comprimir imágenes** JPG, PNG o WebP con calidad ajustable, vista previa antes/después y descarga directa, sin subirlas al servidor. |
| `/convertir-imagen` | **Convertir imágenes** entre JPG, PNG y WebP, con aviso y color de fondo cuando el destino no admite transparencia. |
| `/redimensionar-imagen` | **Redimensionar imágenes** por píxeles o porcentaje, con proporción bloqueable y presets rápidos. |
| `/unir-pdf` | **Unir PDF** en el orden que elijas, con vista previa de cada documento y sin subir los archivos. |
| `/dividir-pdf` | **Dividir PDF** y extraer páginas o rangos (`1-3, 5`) conservando el orden escrito. |
| `/imagenes-a-pdf` | **Convertir imágenes JPG/PNG a PDF** con páginas A4 o el tamaño de cada imagen. |
| `/pdf-a-jpg` | **Convertir PDF a JPG** con calidad y resolución ajustables; varias páginas se descargan en ZIP. |
| `/comprimir-pdf` | **Comprimir PDF** rasterizando cada página con la calidad y resolución que elijas. |
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
- 🖼️ **Imágenes en el navegador**: comprimir, convertir y redimensionar JPG, PNG y
  WebP con canvas. Validación por firma de bytes, vista previa antes/después, tamaño
  original y final, porcentaje real (también negativo) y descarga local. **La imagen
  nunca se sube**: no hay endpoints de imagen ni peticiones externas.
- 🔍 **Transparencia controlada**: al convertir a JPG se detecta el canal alfa, se avisa
  y se permite elegir el color de fondo; PNG y WebP conservan la transparencia.
- 📐 **Redimensionado flexible**: píxeles o porcentaje, proporción bloqueable, presets
  de 25–100 % y 1920/1080/800 px, con límites de 16 384 px por lado y 64 MP.
- 🧹 **Limpieza en el cliente**: se revocan las URL `blob:` y se vacía el canvas al
  cambiar de imagen o cerrar la página.
- **Suite PDF en el navegador**: unir, dividir, imágenes a PDF, PDF a JPG y comprimir
  con pdf-lib y PDF.js servidos desde el propio sitio. El documento nunca se sube;
  se muestran tamaños reales, progreso, miniaturas y descargas locales.
- **Límites PDF explícitos**: 25 MB por archivo, 75 MB por selección, 300 páginas
  al unir/dividir, 80 páginas al convertir a JPG o comprimir, 64 MP por imagen de
  entrada y un máximo de 40 MP por página renderizada.
- **ZIP sin dependencias extra**: los JPG de un PDF de varias páginas se empaquetan
  con un escritor ZIP mínimo en JavaScript, validado con `zipfile` de Python.
- 🔗 **Enlaces de WhatsApp**: enlace `wa.me` con mensaje y **código QR** en PNG.
- 📊 **Progreso en vivo** de compresión y clips, con opción de cancelar.
- 🗂️ **Limpieza automática**: los archivos viven en una carpeta temporal y se borran
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
- **ffmpeg** y **ffprobe** (compresión, clips y lectura de metadatos de vídeo). Las
  herramientas de imagen no los necesitan: el procesamiento ocurre en el navegador.
- **Node.js 18 o superior** solo para ejecutar las pruebas de los motores de imagen y
  PDF. La app no lo usa en tiempo de ejecución.

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

Las herramientas de imagen y PDF **no tienen API ni endpoint de subida**: el servidor
solo entrega el HTML, el CSS, el JavaScript y las bibliotecas locales; validar,
decodificar, unir, dividir, renderizar y codificar ocurre en el navegador. Es una
decisión de privacidad y se verifica en las pruebas (ausencia de `fetch`,
`XMLHttpRequest`, `FormData` y `/api/` en el código de las herramientas).

`/api/health` publica únicamente capacidades activas y límites públicos:

```json
{
  "status": "ok",
  "version": "3.2.0",
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
node --test tests/image-tools.test.js
node --test tests/pdf-tools.test.js
npm ci
npx playwright install chromium
npm run test:e2e
```

Las pruebas de extremo a extremo generan vídeos de prueba con ffmpeg y se saltan si
`ffmpeg`/`ffprobe` no están instalados. `tests/test_site.py` valida el catálogo, los
enlaces internos, la búsqueda, la navegación móvil, la accesibilidad básica, el modo
claro y el SEO técnico. `tests/test_image_tools.py` comprueba el contrato de las páginas
de imagen, la ausencia de código de subida y ejecuta las pruebas Node del motor.
`tests/image-tools.test.js` cubre sniffing de formatos, límites, proporciones y nombres
de descarga sin necesidad de DOM. `tests/test_pdf_tools.py` comprueba el contrato de
las cinco páginas PDF, la integridad SHA-256 de las bibliotecas locales y que el ZIP
generado en JavaScript se abre con `zipfile`; `tests/pdf-tools.test.js` cubre rangos,
geometría, nombres y CRC32. `tests/e2e/pdf.spec.js` ejecuta con Playwright los flujos
reales de las cinco herramientas y valida los archivos descargados. El CI
(`.github/workflows/ci.yml`) ejecuta ruff, las pruebas Node de imagen y PDF, pytest,
Playwright y un build de Docker con comprobación de `/api/health`.

La matriz de pruebas manuales/E2E de las herramientas de imagen (91 comprobaciones con
Chrome headless), la compatibilidad de navegadores y las limitaciones conocidas están en
[`docs/herramientas-imagen.md`](docs/herramientas-imagen.md). La suite PDF tiene su
propia documentación de límites, bibliotecas, flujos y pruebas Playwright en
[`docs/herramientas-pdf.md`](docs/herramientas-pdf.md).

## Estructura

```
videodl/
  app.py         # create_app, middlewares, /api/health, montaje de estáticos
  catalog.py     # registro único de categorías, herramientas y estados
  views.py       # cabecera, navegación, tarjetas, portada, directorio y SEO
  pages.py       # rutas HTML amigables, alias 301, sitemap.xml y robots.txt
  image_pages.py # textos, controles y SEO de las tres herramientas de imagen
  pdf_pages.py   # textos, controles y SEO de las cinco herramientas PDF
  config.py      # variables de entorno validadas y detección de ffmpeg
  compressor.py  # compresión por tamaño objetivo o calidad
  clips.py       # clips verticales a partir de archivos subidos
  whatsapp.py    # validación de enlaces y QR
  media.py       # ffmpeg/ffprobe
  tasks.py       # lanzador de trabajos en segundo plano
  jobs.py        # almacén de trabajos en memoria con TTL
  legacy.py      # rutas retiradas (410 Gone)
static/          # HTML de herramientas, CSS y JS sin frameworks
  imagen-tool.html # plantilla única de comprimir/convertir/redimensionar
  image-tools.js   # motor de imagen (validación, canvas, medidas, limpieza)
  pdf-tool.html    # plantilla única de las cinco herramientas PDF
  pdf-core.js      # núcleo puro: validación, rangos, geometría, nombres, CRC32 y ZIP
  pdf-suite.js     # interfaz y procesamiento PDF (pdf-lib + PDF.js)
  vendor/pdf/      # pdf-lib 1.17.1, PDF.js 6.4.299 y recursos, con manifest.json
  imagenes.js      # interfaz compartida de las tres herramientas de imagen
tests/           # pruebas unitarias, de API, de sitio y e2e con ffmpeg
docs/            # compatibilidad, límites y matrices de pruebas de imagen y PDF
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
