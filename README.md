# FasTools.app

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/karlossxt/videodl)

Plataforma de multiherramientas gratuitas en español. **Solo procesa archivos que
aporta el usuario**: comprime un vídeo para enviarlo por WhatsApp o Discord, recorta un
clip vertical listo para TikTok, Reels y Shorts, transcribe un audio a texto, reduce o
convierte imágenes, une o divide PDF y crea códigos QR o enlaces de WhatsApp con mensaje.

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
| `/transcribir-audio` | **Transcribir audio o vídeo a texto** con marcas de tiempo y descarga en TXT, SRT o VTT. Requiere la dependencia opcional `faster-whisper`. |
| `/generador-qr` | **Generar códigos QR** de enlaces, texto, WiFi, email, teléfono o SMS, con tamaño, colores y descarga en PNG o SVG. |
| `/comprimir-imagen` | **Comprimir imágenes** JPG, PNG o WebP con calidad ajustable, vista previa antes/después y descarga directa, sin subirlas al servidor. |
| `/convertir-imagen` | **Convertir imágenes** entre JPG, PNG y WebP, con aviso y color de fondo cuando el destino no admite transparencia. |
| `/redimensionar-imagen` | **Redimensionar imágenes** por píxeles o porcentaje, con proporción bloqueable y presets rápidos. |
| `/unir-pdf` | **Unir PDF** en el orden que elijas, con vista previa de cada documento y sin subir los archivos. |
| `/dividir-pdf` | **Dividir PDF** y extraer páginas o rangos (`1-3, 5`) conservando el orden escrito. |
| `/imagenes-a-pdf` | **Convertir imágenes JPG/PNG a PDF** con páginas A4 o el tamaño de cada imagen. |
| `/pdf-a-jpg` | **Convertir PDF a JPG** con calidad y resolución ajustables; varias páginas se descargan en ZIP. |
| `/comprimir-pdf` | **Comprimir PDF** rasterizando cada página con la calidad y resolución que elijas. |
| `/link-whatsapp` | **Generar un enlace de WhatsApp** (`wa.me`) con el mensaje ya escrito, y descargarlo como **código QR**. |
| `/privacidad` | Nota de privacidad: archivos temporales, datos técnicos y almacenamiento local. |

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
- 🔳 **Generador de QR**: enlaces, texto, WiFi (WPA/WEP/abierta y oculta), email, teléfono
  y SMS; tamaño, margen, nivel de corrección y colores con validación de contraste;
  descarga en PNG o SVG. El contenido no se guarda.
- 📝 **Transcripción opcional**: audio o vídeo a texto con faster-whisper, detección de
  idioma, progreso, cancelación y descarga en TXT, SRT o VTT. El modelo se ejecuta en el
  servidor y el audio se borra al terminar.
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
- 🌍 **Bilingüe español/inglés**: el español conserva las URLs sin prefijo y el inglés
  se sirve bajo `/en/...`, con selector de idioma, `hreflang`, `x-default` y sitemap
  con ambas variantes. Las rutas `/es/...` redirigen a la versión española. Los textos
  dinámicos de compresión, clips, QR, WhatsApp, transcripción, imágenes y PDF también
  se traducen sin peticiones adicionales.
- 🧭 **SEO técnico**: canonical y Open Graph por página, `sitemap.xml`, `robots.txt` y
  URL pública configurable con `SITE_URL`.
- 📢 **Espacios publicitarios preparados** en el HTML y el CSS, sin anuncios ni
  scripts de terceros activos.
- 🐳 **Listo para desplegar**: `Dockerfile`, `docker-compose.yml` y plantillas para
  Render y Railway.
- ✅ Mensajes de error claros, interfaz bilingüe y cabeceras de seguridad (CSP con
  hashes para los textos JS inline, nosniff, frame-ancestors…).

## Requisitos

- Python 3.10 o superior
- **ffmpeg** y **ffprobe** (compresión, clips, transcripción y lectura de metadatos de
  vídeo). Las herramientas de imagen no los necesitan: el procesamiento ocurre en el
  navegador.
- **Opcional:** `faster-whisper` para la transcripción de audio. Sin esta dependencia la
  página sigue publicada y la API responde `503`; el resto del sitio funciona igual.
- **Node.js 18 o superior** solo para ejecutar las pruebas de los motores de imagen, PDF y
  QR. La app no lo usa en tiempo de ejecución.

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

Para activar la transcripción:

```bash
pip install -r requirements-transcribe.txt
# El modelo se descarga en el primer uso (caché de Hugging Face).
TRANSCRIBE_MODEL=base uvicorn main:app --reload
```

En CPU, `tiny` o `base` son los modelos razonables para un servidor pequeño; `small`
mejora la precisión en español a cambio de más CPU y RAM. La primera transcripción
descarga el modelo (cientos de MB según el tamaño) y puede tardar más.

### Docker

```bash
docker build -t videodl .
docker run --rm -p 8000:8000 videodl
```

Para incluir la transcripción en la imagen (y opcionalmente descargar el modelo durante
el build):

```bash
docker build \
  --build-arg INSTALL_TRANSCRIBE=1 \
  --build-arg PRELOAD_TRANSCRIBE=1 \
  --build-arg TRANSCRIBE_MODEL=base \
  -t videodl .
```

O con Compose:

```bash
docker compose up --build
```

La caché de modelos se guarda en `/app/.cache/huggingface`; si quieres conservarla entre
contenedores, monta un volumen sobre esa ruta.

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
| `POST` | `/api/qr` | Devuelve un QR PNG o SVG de un contenido y estilo validados. |
| `GET` | `/api/transcribe/options` | Capacidades, modelo y límites de la transcripción. |
| `POST` | `/api/transcribe` | Sube un audio o vídeo y crea un trabajo de transcripción. |
| `GET` | `/api/transcribe/{id}` | Estado, progreso, idioma detectado y texto. |
| `GET` | `/api/transcribe/{id}/file?format=txt|srt|vtt` | Descarga la transcripción. |
| `POST` | `/api/transcribe/{id}/cancel` | Cancela una transcripción en curso. |

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
  "qr": true,
  "transcribe": true,
  "transcribe_model": "base",
  "transcribe_max_seconds": 1800,
  "transcribe_max_mb": 100,
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
| `SITE_NAME` | `FasTools.app` | Marca visible en títulos, cabecera, pie y Open Graph. Cámbiala si usas otro dominio (p. ej. `FasTools.es`). |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Proxies de confianza para `X-Forwarded-For`. |
| `RATE_LIMIT_PER_MINUTE` | `60` | Peticiones por minuto y por IP (`0` = sin límite). |
| `MAX_CONCURRENT_JOBS` | `4` | Compresiones/clips simultáneos. |
| `MAX_UPLOAD_MB` | `200` | Tamaño máximo de archivo subido. |
| `COMPRESS_MAX_TARGET_MB` | `200` | Tope del tamaño objetivo del compresor. |
| `X264_PRESET` | `veryfast` | Preset de x264 (`ultrafast`…`placebo`). |
| `CLIP_MAX_SECONDS` | `300` | Duración máxima de un clip. |
| `FFMPEG_TIMEOUT_SECONDS` | `3600` | Tiempo máximo de un proceso ffmpeg (`0` = sin límite). |
| `TRANSCRIBE_MODEL` | `base` | Modelo de faster-whisper (`tiny`, `base`, `small`, `medium`, `large-v3`). |
| `TRANSCRIBE_DEVICE` | `cpu` | `cpu`, `cuda` o `auto`. |
| `TRANSCRIBE_COMPUTE_TYPE` | `int8` | `int8`, `int8_float16`, `float16` o `float32`. |
| `TRANSCRIBE_BEAM_SIZE` | `1` | 1 = más rápido; 5 = algo más preciso. |
| `TRANSCRIBE_MAX_SECONDS` | `1800` | Duración máxima del audio. |
| `TRANSCRIBE_MAX_MB` | `100` | Tamaño máximo del audio o vídeo subido. |
| `TRANSCRIBE_LANGUAGE` | vacío | Idioma fijo (`es`, `en`…) o vacío para detección automática. |
| `CORS_ORIGINS` | vacío | Orígenes CORS separados por comas. |
| `CONTENT_SECURITY_POLICY` | CSP por defecto | CSP personalizada; vacía la desactiva. |

## Pruebas y calidad

```bash
pip install -r requirements-dev.txt
ruff check .
pytest
node --test tests/image-tools.test.js
node --test tests/pdf-tools.test.js
node --test tests/qr-core.test.js
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
geometría, nombres y CRC32. `tests/qr-core.test.js` cubre los payloads de WiFi, email,
teléfono y SMS, el escape de caracteres y el contraste de colores. `tests/test_qr.py` y
`tests/test_transcribe.py` cubren las páginas, la API y los formatos SRT/VTT.
`tests/e2e/pdf.spec.js` ejecuta con Playwright los flujos
reales de las cinco herramientas y valida los archivos descargados. `tests/test_i18n.py`
comprueba la paridad de los locales, las rutas `/en/`, las redirecciones `/es/`, los
metadatos `hreflang` y el sitemap bilingüe. El CI (`.github/workflows/ci.yml`) ejecuta
ruff, las pruebas Node de imagen, PDF y QR, pytest, Playwright y un build de Docker con
comprobación de `/api/health`.

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
  i18n.py        # carga de locales, traducción, rutas por idioma y hashes CSP
  locales/       # es.json y en.json (metadatos, catálogo, UI y mapa de plantillas)
  views.py       # cabecera, navegación, tarjetas, portada, directorio y SEO
  pages.py       # rutas HTML amigables, alias 301, sitemap.xml y robots.txt
  image_pages.py # textos, controles y SEO de las tres herramientas de imagen
  pdf_pages.py   # textos, controles y SEO de las cinco herramientas PDF
  config.py      # variables de entorno validadas y detección de ffmpeg
  compressor.py  # compresión por tamaño objetivo o calidad
  clips.py       # clips verticales a partir de archivos subidos
  whatsapp.py    # validación de enlaces y QR
  qr.py          # generador de QR genérico (PNG/SVG)
  transcribe.py  # transcripción opcional con faster-whisper
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
  qr-core.js       # payloads de QR, validación y contraste (también para Node)
  qr.js            # interfaz del generador de QR
  transcribe.js    # interfaz de transcripción (subida, progreso, descargas)
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

La transcripción es la herramienta más exigente. En el plan gratuito de Render (0,1 CPU
y 512 MB) solo es viable con `TRANSCRIBE_MODEL=tiny` y audios cortos; para `base` o
`small` conviene un plan con al menos 1–2 GB de RAM. El modelo se carga una vez por
proceso y se reutiliza. El resto de herramientas no necesitan `faster-whisper`.

Antes de publicar con un dominio propio, revisa la
[guía de lanzamiento](docs/lanzamiento-dominio.md): dominio, `SITE_URL`, HTTPS,
analítica y límites de la transcripción.

## Uso responsable

Sube solo contenido que te pertenezca o que puedas utilizar libremente. Consulta la
[nota de privacidad](/privacidad) para saber qué ocurre con los archivos y los datos.

## Licencia

MIT.
