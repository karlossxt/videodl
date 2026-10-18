# VideoDL

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/karlossxt/videodl)

Suite de herramientas de video con interfaz web. Pega el enlace de un video y descárgalo en tu equipo en la calidad que quieras, sube un archivo para comprimirlo y enviarlo por WhatsApp o Discord, recorta un clip vertical listo para TikTok, Reels y Shorts, o crea un enlace de WhatsApp con mensaje y código QR.

> 🌐 **Demo en vivo:** https://videodl-6md8.onrender.com
> *(plan gratuito: si lleva un rato sin usarse, la primera visita puede tardar ~50 s en despertar)*

El backend usa **yt-dlp**, por lo que es compatible con más de 1000 sitios: YouTube, TikTok, Instagram, X / Twitter, Facebook, Reddit, Twitch, Vimeo y enlaces directos MP4/WebM, entre muchos otros.

## Herramientas

| Página | Para qué sirve |
|---|---|
| `/` | **Descargar video y audio** de casi cualquier plataforma: MP4 en cualquier resolución, MP3, subtítulos, miniatura, recortes y cola en lote. |
| `/comprimir-video-whatsapp` | **Comprimir video** para que entre en los límites de WhatsApp (16 MB), Discord (10 MB), Telegram, el correo o un tamaño que tú elijas. |
| `/recortar-clip-vertical` | **Recortar clips verticales** (9:16) de Twitch, Kick, YouTube o de un archivo propio, con recorte centrado o fondo desenfocado, listos para TikTok, Reels y Shorts. |
| `/link-whatsapp` | **Generar un enlace de WhatsApp** (`wa.me`) con el mensaje ya escrito para tu web o tus redes, y descargarlo como **código QR** listo para imprimir. |
| `/herramientas` | Directorio con todas las herramientas del sitio. |

## Características

- 🔍 **Análisis previo**: muestra título, autor, vistas, duración, miniatura y las calidades realmente disponibles.
- 🎬 **Descarga de video** en la máxima calidad o eligiendo una resolución concreta (MP4).
- 🎵 **Solo audio** en MP3 (192 kbps) mediante ffmpeg.
- 📊 **Progreso en vivo**: porcentaje, velocidad, tamaño y tiempo restante mientras se descarga en el servidor, con opción de cancelar.
- ✂️ **Recortador de fragmentos**: descarga solo la parte del video que elijas (inicio y fin) usando ffmpeg.
- 📚 **Cola en lote**: pega varios enlaces, analízalos y descárgalos en orden con estado por elemento (el historial se guarda en el navegador).
- 💬 **Subtítulos** en `.SRT` o `.VTT` (manuales y automáticos) en el idioma que elijas.
- 🖼️ **Descarga de la miniatura** de portada en su resolución original.
- 🗜️ **Compresor de video**: sube un archivo y redúcelo al tamaño objetivo (WhatsApp, Discord, Telegram, correo o MB personalizados). Calcula el bitrate disponible, baja la resolución solo cuando hace falta y, si el video ya cabe, lo entrega **sin recodificar**.
- 🎚️ **Modo "priorizar calidad"**: recodifica con CRF sin forzar el tamaño objetivo, útil para bajar resolución sin destrozar la imagen.
- ✂️ **Clips verticales para TikTok / Reels / Shorts**: pega un directo (VOD) o un clip de Twitch, Kick, YouTube… y descarga **solo los segundos que elijas** ya reencuadrados en 9:16. Incluye recorte centrado, fondo desenfocado para no perder los laterales, cuadrado 1:1 y hasta 5 minutos de clip.
- 🔗 **Generador de enlaces de WhatsApp**: crea un enlace `wa.me` con el mensaje ya escrito (con plantillas), cópialo como botón HTML o descárgalo como **código QR** para imprimir. El enlace se monta en tu navegador; al servidor solo va el enlace para dibujar el QR.
- 🖥️ **Interfaz web** oscura y responsive, sin dependencias de frameworks en el frontend.
- 📋 Botón **Pegar** desde el portapapeles para analizar al instante.
- ✅ Mensajes de error claros en español (video privado, restringido, URL no soportada, etc.).
- 🧹 Limpieza automática de los archivos temporales del servidor.
- 🐳 **Listo para desplegar**: `Dockerfile`, `docker-compose.yml` y plantillas para Render y Railway.

## Requisitos

- Python 3.10 o superior
- **ffmpeg** (necesario para unir video + audio en calidades altas, convertir a MP3 y recortar fragmentos)

En Windows, con [winget](https://learn.microsoft.com/windows/package-manager/winget/):

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg
```

## Instalación

```powershell
# 1. Clonar el repositorio
git clone https://github.com/karlossxt/videodl.git
cd videodl

# 2. Instalar dependencias de Python
python -m pip install -r requirements.txt
```

> 💡 Mantén **yt-dlp actualizado**. Las plataformas cambian con frecuencia y las versiones antiguas dejan de funcionar:
> ```powershell
> python -m pip install --upgrade yt-dlp
> ```

## Uso

```powershell
python -m uvicorn main:app --port 8000
```

Abre <http://127.0.0.1:8000> en el navegador, pega el enlace del video, pulsa **Analizar** y elige el formato que quieras descargar.

La tarjeta de resultado tiene tres pestañas:

- 🎬 **Video**: máxima calidad o una resolución concreta en MP4.
- 🎵 **Solo Audio**: extrae la pista de audio en MP3.
- 🗂️ **Extras**: descarga la miniatura de portada y los subtítulos en `.SRT` o `.VTT`.

Además, con el botón **✂️ Cortar fragmento** puedes indicar el minuto de inicio y de fin para descargar solo esa parte del video (o del audio). El corte se hace con ffmpeg en el servidor y el archivo resultante lleva el rango en el nombre, por ejemplo `video (corte 1m05s-2m30s).mp4`.

Y con **📚 Descargar varios enlaces en lote** puedes pegar una lista de enlaces (uno por línea), elegir el formato para toda la cola y descargarlos uno tras otro, viendo el estado y el progreso de cada uno. La lista se guarda en tu navegador, así que sigue ahí si recargas la página.

### Comprimir video (WhatsApp / Discord)

En **🗜️ Comprimir** (o entrando en <http://127.0.0.1:8000/comprimir-video-whatsapp>) puedes
subir un archivo de tu equipo y reducirlo hasta el tamaño que necesites:

1. Elige o arrastra el video (hasta 200 MB por defecto).
2. Selecciona el destino: WhatsApp 16 MB, WhatsApp HD 64 MB, Discord 10 MB, Discord Nitro 25 MB, Telegram 50 MB, email 20 MB o un tamaño personalizado.
3. Pulsa **Comprimir** y descarga el resultado.

El servidor calcula el bitrate que cabe en ese tamaño, baja la resolución solo si es
imprescindible y, si el video ya cabía, lo entrega sin recodificar (sin pérdida).
Con la opción **Priorizar calidad** se recodifica con CRF y no se fuerza el tamaño.

### Recortar un clip vertical (TikTok / Reels / Shorts)

En **✂️ Clips verticales** (o entrando en <http://127.0.0.1:8000/recortar-clip-vertical>):

1. Pega el enlace de un directo guardado (VOD) o de un clip de Twitch, Kick, YouTube…
   y pulsa **Analizar**. También puedes subir un archivo de tu equipo.
2. Elige el momento con los deslizadores de inicio y fin, o con los atajos de
   **Primeros 30 s**, **Últimos 30 s** y **Todo el video**.
3. Elige el formato de salida:
   - **Vertical 9:16** — recorte centrado, la opción más nítida.
   - **Vertical + fondo** — mantiene el encuadre completo y rellena los lados con una
     copia desenfocada (como las apps de edición).
   - **Cuadrado 1:1** — para el feed de Instagram.
   - **Original** — solo recorta, sin reencuadrar.
4. Pulsa **Crear el clip** y descarga el MP4.

Con enlaces de directos largos, el servidor **solo descarga los segundos pedidos** (más
un pequeño margen de seguridad que después se recorta al segundo exacto): un clip de
30 s en un directo de 10 horas tarda lo mismo que en un video corto. La salida es
H.264 + AAC en MP4, sin marca de agua. Duración máxima configurable con
`CLIP_MAX_SECONDS` (300 s por defecto).

### Crear un enlace de WhatsApp

En **🔗 Enlace de WhatsApp** (o entrando en <http://127.0.0.1:8000/link-whatsapp>)
puedes generar el clásico enlace *click to chat*:

1. Escribe tu número con el prefijo de tu país (si lo pegas con `+`, espacios o
   guiones se limpia solo).
2. Redacta el mensaje que quieres recibir, o elige una plantilla.
3. Copia el enlace, pruébalo, compártelo o descárgalo como **código QR**.

El enlace se monta en tu navegador, así que tu número y tu mensaje no salen de tu
equipo mientras escribes; solo al pedir el código QR se manda el enlace ya montado
al servidor, se convierte en imagen y se descarta sin guardarlo.

```
https://wa.me/<prefijo><numero>?text=<mensaje>
```

Si marcas **Sin número fijo** se genera `https://wa.me/?text=…`, que deja que cada
persona elija el contacto al que escribir.

## Estructura del proyecto

```
.
├── main.py                  # Punto de entrada fino: importa y expone `app`
├── videodl/                 # Paquete de la aplicación
│   ├── app.py               # Crea la app FastAPI (middlewares, salud, estáticos)
│   ├── config.py            # Configuración validada desde variables de entorno
│   ├── security.py          # Protección SSRF, rate limit y límite de concurrencia
│   ├── jobs.py, stores.py   # JobStore genérico y almacenes compartidos
│   ├── downloader.py        # Rutas de descarga (/api/info, /api/jobs…)
│   ├── compressor.py        # Rutas del compresor (/api/compress…)
│   ├── clips.py             # Rutas del recortador (/api/clips…)
│   ├── whatsapp.py          # Generador de enlaces de WhatsApp (/api/whatsapp/qr)
│   ├── media.py             # Envoltorios de ffmpeg/ffprobe y opciones de yt-dlp
│   ├── pages.py, paths.py   # Páginas HTML y resolución segura de archivos
│   ├── models.py, errors.py # Esquemas de petición y errores legibles
│   └── uploads.py, utils.py, constants.py, runtime.py
├── static/
│   ├── index.html / app.js          # Descargador universal
│   ├── comprimir.html / comprimir.js# Compresor para WhatsApp / Discord
│   ├── clips.html / clips.js        # Recortador de clips verticales
│   ├── whatsapp.html / whatsapp.js  # Generador de enlaces de WhatsApp
│   ├── herramientas.html            # Directorio de herramientas
│   ├── common.js                    # Utilidades JS compartidas (window.VD)
│   └── style.css                    # Estilos (compartidos)
├── tests/                   # Pruebas con pytest (API, seguridad, jobs, utils)
├── requirements.txt         # Dependencias de Python (fijadas)
├── requirements-dev.txt     # Dependencias de desarrollo (pytest, ruff…)
├── .env.example             # Plantilla comentada de variables de entorno
├── Dockerfile               # Imagen de producción (incluye ffmpeg)
├── docker-compose.yml       # Ejecución local/servidor con Docker
├── render.yaml              # Blueprint para Render
├── railway.json             # Configuración para Railway
├── SECURITY.md              # Política de seguridad y modelo de amenazas
├── CONTRIBUTING.md          # Cómo contribuir y ejecutar las pruebas
└── CHANGELOG.md             # Historial de cambios
```

`main.py` es solo un puente (`from videodl.app import app`) para que `uvicorn main:app`
y los archivos de plataforma sigan funcionando; también puedes arrancar con
`uvicorn videodl.app:app`.

## API

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/health` _(o `/health`)_ | Estado del servicio: `status`, `version`, disponibilidad de `ffmpeg`/`ffprobe`, `compressor`, `clips`, `clip_max_seconds`, `max_upload_mb` y `cookies` (booleano). No expone rutas ni secretos. |
| `POST` | `/api/info` | Analiza una URL y devuelve metadatos, calidades y subtítulos disponibles. Cuerpo: `{ "url": "..." }` |
| `POST` | `/api/download` | Descarga y devuelve el archivo (bloqueante, sin progreso). Cuerpo: `{ "url": "...", "mode": "best \| audio \| video-<altura>", "title": "...", "start": 0, "end": 30 }` |
| `POST` | `/api/jobs` | Inicia una descarga en segundo plano. Devuelve `{ "id": "..." }`. Mismo cuerpo que `/api/download`. |
| `GET` | `/api/jobs/{id}` | Estado y progreso: `status`, `percent`, `speed`, `eta`, `downloaded`, `total`, `phase`. |
| `GET` | `/api/jobs/{id}/file` | Descarga el archivo del trabajo terminado (libera los recursos al enviarlo). |
| `POST` | `/api/jobs/{id}/cancel` | Cancela un trabajo en curso. |
| `POST` | `/api/subtitles` | Devuelve los subtítulos de un idioma. Cuerpo: `{ "url": "...", "lang": "en", "format": "srt \| vtt", "title": "..." }` |
| `GET` | `/api/thumbnail` | Devuelve la miniatura como archivo. Parámetros: `url`, `title`. |
| `GET` | `/api/compress/presets` | Tamaños recomendados por plataforma, límite de subida y resoluciones admitidas. |
| `POST` | `/api/compress` | Sube un video y lo comprime (`multipart/form-data`): campos `file`, `target_mb` (1–200), `max_height` (`0` = automática) y `quality_mode` (`size` \| `quality`). Devuelve `{ "id": "..." }`. |
| `GET` | `/api/compress/{id}` | Estado y progreso: `status`, `percent`, `message`, `input_size`, `output_size`, `filename`. |
| `GET` | `/api/compress/{id}/file` | Descarga el video comprimido (libera los recursos al enviarlo). |
| `POST` | `/api/compress/{id}/cancel` | Cancela una compresión en curso. |
| `GET` | `/api/clips/options` | Formatos, calidades, duración máxima de clip y límite de subida. |
| `POST` | `/api/clips` | Crea un clip vertical a partir de un fragmento de un video en línea. Cuerpo: `{ "url": "...", "start": 0, "end": 30, "aspect": "vertical \| vertical-blur \| square \| original", "quality": "alta \| media \| baja", "title": "..." }`. Devuelve `{ "id": "..." }`. |
| `POST` | `/api/clips/upload` | Crea un clip vertical desde un archivo propio (`multipart/form-data`): campos `file`, `start`, `end`, `aspect`, `quality`, `duration`. |
| `GET` | `/api/clips/{id}` | Estado y progreso: `status` (`downloading` \| `transforming`), `percent`, `downloaded`, `speed`, `eta`, `width`, `height`, `duration`, `output_size`, `filename`. |
| `GET` | `/api/clips/{id}/file` | Descarga el clip terminado (libera los recursos al enviarlo). |
| `POST` | `/api/clips/{id}/cancel` | Cancela un clip en curso. |
| `POST` | `/api/whatsapp/qr` | Devuelve el **código QR** (PNG) de un enlace de WhatsApp. Cuerpo: `{ "link": "https://wa.me/34600123456?text=Hola" }`. Solo acepta enlaces de `wa.me` / `whatsapp.com` (no es un generador de QR genérico). |

> El frontend usa `/api/jobs` para mostrar la barra de progreso en vivo. `/api/download` se mantiene para usos programáticos o scripts.
>
> Los campos opcionales `start` y `end` (en segundos) recortan el fragmento a descargar. Si se indican, `end` debe ser mayor que `start` y hace falta ffmpeg.

## Pruebas

```powershell
# 1. Dependencias de desarrollo (pytest, ruff…)
python -m pip install -r requirements-dev.txt

# 2. Ejecutar las pruebas y el linter
python -m pytest
ruff check .
```

Las pruebas usan el `TestClient` de FastAPI y **no necesitan conexión a internet**.
La suite se ejecuta igualmente sin ffmpeg: las pruebas que lo necesitan
(`tests/test_e2e_ffmpeg.py`, que generan un vídeo y recorren el compresor y el
recortador de clips) se **saltan** automáticamente. El CI instala ffmpeg, así que
allí se ejecutan todas. En `tests/` hay cobertura de la API, la seguridad (SSRF,
rate limit), el `JobStore`, las utilidades y los pipelines con ffmpeg. El CI
también construye la imagen Docker y comprueba que el contenedor responde en
`/api/health`. Consulta [`CONTRIBUTING.md`](CONTRIBUTING.md) para más detalles.

## Despliegue

La app incluye un `Dockerfile` que ya instala ffmpeg, así que funciona igual en local, en un servidor o en la nube. El servidor escucha en `0.0.0.0` y respeta la variable de entorno `PORT`.

> ⚠️ **Importante:** ejecuta **un solo worker/proceso**. El progreso de las descargas se guarda en memoria, de modo que todas las peticiones de un mismo trabajo deben atenderlas el mismo proceso. Con varios workers, un sondeo de progreso podría caer en otro proceso y devolver "trabajo no encontrado". Los archivos de configuración incluidos ya usan un único proceso.

### Con Docker (local o VPS)

```bash
docker compose up --build
```

Abre <http://localhost:8000>.

O sin Compose:

```bash
docker build -t videodl .
docker run -p 8000:8000 videodl
```

### En Render (recomendado, plan gratuito)

1. Sube el repositorio a GitHub.
2. En [dashboard.render.com](https://dashboard.render.com) → **New** → **Blueprint** y elige el repositorio.
3. Render detecta `render.yaml` y crea el servicio web con el Dockerfile.
4. Cuando termine el despliegue tendrás una URL pública tipo `https://videodl.onrender.com`.

El plan gratuito de Render "duerme" el servicio tras un rato sin uso: la primera petición puede tardar unos segundos en despertarlo.

### En Railway

1. En [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
2. Railway lee `railway.json` y construye con el Dockerfile.
3. En **Settings → Networking** genera un dominio público.

### Notas de producción

- **ffmpeg** debe estar presente (la imagen Docker ya lo incluye) para unir video+audio, generar MP3, recortar fragmentos, comprimir y crear clips verticales.
- **Mantén yt-dlp actualizado**: las plataformas cambian a menudo. Al reconstruir la imagen se instala la última versión permitida por `requirements.txt`.
- **Variables de entorno** (todas opcionales; hay una plantilla comentada en `.env.example`):
  - Servidor: **`PORT`**, **`LOG_LEVEL`**, **`FORWARDED_ALLOW_IPS`** (IP del proxy de confianza para leer `X-Forwarded-For`; déjalo en `127.0.0.1` salvo que uses un proxy propio).
  - Límites: **`RATE_LIMIT_PER_MINUTE`** (peticiones por minuto y por IP, `0` = sin límite), **`MAX_CONCURRENT_JOBS`** (trabajos pesados simultáneos).
  - Vídeo: **`MAX_UPLOAD_MB`**, **`COMPRESS_MAX_TARGET_MB`**, **`X264_PRESET`** (velocidad/calidad de x264, `veryfast` por defecto), **`CLIP_MAX_SECONDS`**, **`CLIP_PAD_SECONDS`** (margen de seguridad descargado de más en cada extremo para clavar el segundo exacto), **`CLIP_MAX_FULL_DOWNLOAD_MB`** (tope cuando el enlace no admite fragmentos), **`FFMPEG_TIMEOUT_SECONDS`** (mata codificaciones colgadas) y **`YTDLP_SOCKET_TIMEOUT`**.
- yt-dlp y plataformas: **`YTDLP_PROXY`** (saca las peticiones por un proxy, útil si la plataforma bloquea la IP del servidor) y **`YTDLP_EXTRACTOR_ARGS`** (eliges otro cliente de extracción, con el formato de `--extractor-args`; por ejemplo `youtube:player_client=tv,web_safari`).
  - Seguridad: **`CORS_ORIGINS`** (orígenes permitidos separados por comas; vacío = mismo origen) y **`CONTENT_SECURITY_POLICY`** (CSP propia; vacío = se usa una por defecto sensata).
  - En servidores gratuitos con poca CPU conviene dejar `X264_PRESET` en `veryfast` o `ultrafast`.
- **Seguridad**: la app valida las URLs (bloquea peticiones a direcciones internas/privadas para evitar SSRF), aplica un límite de peticiones por IP y de trabajos concurrentes, y envía cabeceras de seguridad (incluida una CSP por defecto). Consulta [`SECURITY.md`](SECURITY.md) para el modelo de amenazas y cómo reportar problemas.
- Los archivos se descargan a una carpeta temporal y se borran en cuanto se envían al usuario. Al reiniciar el servicio se limpian los restos.
- Usa la app solo para contenido propio o con licencia; respeta los términos de cada plataforma.

### YouTube desde la nube (PO tokens, cookies y proxy)

Desde una IP de servidor (Render, Railway…) YouTube responde *"Sign in to confirm
you're not a bot"* a buena parte de sus vídeos: quiere una prueba de que hay una
persona al otro lado. La app trae tres mecanismos y los usa en este orden:

1. **PO tokens (automático, ya incluido).** La imagen instala el proveedor
   [`bgutil-ytdlp-pot-provider`](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)
   en modo «script» con el Deno que trae `yt-dlp[default,deno]`: firma cada petición
   con un *PO token*, que es justo lo que YouTube exige a las IPs de nube. No hay
   nada que configurar. El plugin corta la generación a los 20 s, poco para una CPU
   modesta, así que la app amplía ese límite con `YTDLP_POT_TIMEOUT` (`0` desactiva
   el proveedor, útil para comparar con y sin él).
2. **Cookies** de una sesión iniciada: ayudan además con los vídeos que requieren
   cuenta (edad, privados, suscripciones).
3. **`YTDLP_PROXY`**: salir con otra IP (un proxy residencial).

> **Nota técnica (runtime):** yt-dlp moderno necesita un *runtime* de JavaScript para
> YouTube. La imagen instala `yt-dlp[default,deno]` (el solucionador `yt-dlp-ejs` y
> el runtime `deno`); sin él la extracción se degrada y yt-dlp avisa de que faltarán
> formatos. No lo quites al actualizar dependencias a mano: el proveedor de PO tokens
> también lo aprovecha.

> **Nota técnica (versiones):** el plugin de PO tokens y el script del proveedor
> deben ser la misma versión. `requirements.txt` lo fija con `==` y el Dockerfile lo
> instala con `BGUTIL_POT_VERSION`; una prueba
> ([`tests/test_requirements.py`](tests/test_requirements.py)) impide que se
> desincronicen.

#### Cookies (opcional)

La app las busca en este orden:

1. **Secret File** montado en `/etc/secrets/cookies.txt`. En Render se sube desde
   *Environment → Secret Files → Add Secret File* con el nombre `cookies.txt`. **Es la
   vía recomendada**: no hay que codificar nada y el secreto no viaja por el chat.
2. **`YTDLP_COOKIES_FILE`**: ruta a un `cookies.txt` que ya exista en el servidor.
3. **`YTDLP_COOKIES`**: el contenido del archivo como texto.
4. **`YTDLP_COOKIES_B64`**: el mismo contenido en Base64 (por si no puedes pegar
   texto multilínea).

> **Nota para Docker:** los Secret Files de Render pertenecen al grupo `1000`. El
> `Dockerfile` del proyecto añade el usuario de la app a ese grupo para poder
> leerlos; si usas una imagen propia, haz lo mismo o los Secret Files no se
> cargarán (`cookies:false`). La alternativa sin permisos es la variable de
> entorno `YTDLP_COOKIES_B64`.

> **Nota sobre el fichero:** yt-dlp **reescribe** el `cookies.txt` al cerrar cada
> descarga, así que la app trabaja siempre sobre una **copia privada con permiso de
> escritura** (en `.videodl_cookies/`, dentro del directorio temporal). De este modo
> un Secret File de solo lectura no rompe la descarga justo al terminar y tu archivo
> original no se modifica nunca.

Recomendaciones:

- Exporta las cookies **con la sesión de YouTube iniciada**. Es el error más común:
  si el `cookies.txt` se exporta sin haber entrado en la cuenta, no identifica a
  nadie y YouTube sigue tratándote como anónimo. La app lo detecta: si faltan las
  cookies de sesión (`SID`, `__Secure-1PSID`…) lo avisa en el arranque y
  `/api/health` devuelve `"cookies_session": false`.
- Exporta el fichero con una extensión tipo *Get cookies.txt LOCALLY*, en formato
  **Netscape** (la primera línea suele ser `# Netscape HTTP Cookie File`).
- Usa una **cuenta secundaria** de YouTube: si esa cuenta cae en un control
  anti-bot, no pierdes la principal.
- Las cookies se usan para **analizar y para descargar**: si al pulsar *Analizar*
  sale el aviso anti-bot, es que no están llegando, han caducado o no traen sesión.
  Vuelve a exportarlas y actualiza el Secret File (o el despliegue) y espera a que
  Render reinicie el servicio.
- **YouTube rota estas cookies cada cierto tiempo.** Cuando lo hace, el `cookies.txt`
  sigue pareciendo correcto (trae `SID`, `__Secure-1PSID`…) pero ya no autentica, y
  las descargas salen como anónimas con el aviso anti-bot. yt-dlp lo detecta y lo
  avisa (`cookies are no longer valid`); la app lo recuerda y te lo dice en el
  error para que **renueves** el fichero en lugar de buscarte la vida.
- Comprueba el resultado en `/api/health`: `cookies` indica `true` si se cargaron,
  `cookies_count` cuántas hay y `cookies_session` si incluyen una sesión iniciada.
  En los registros del servidor (arranque) se indica desde dónde se cargaron
  (`YTDLP_COOKIES_FILE`, Secret File, `YTDLP_COOKIES` o `YTDLP_COOKIES_B64`); sube
  el nivel con `LOG_LEVEL=INFO`. Por seguridad, la app solo mira los **nombres** de
  las cookies (nunca sus valores) y no publica el origen del fichero.

Sin cookies la app funciona exactamente igual; solo YouTube limita muchas descargas
desde IPs de centro de datos.

Medido en Render, con la configuración actual (runtime de JavaScript, PO tokens
incluidos, cookies «con sesión» pero rotadas): YouTube responde con su comprobación
anti-bot a casi cualquier vídeo desde esa IP; solo pasó el de control, el más
popular. Con y sin cookies, y con **todos** los clientes
(`YTDLP_EXTRACTOR_ARGS=youtube:player_client=all`), el resultado fue el mismo: elegir
cliente no lo arregla. Los PO tokens sí entran en juego (la extracción pasa de ~3 s a
~13 s: ese es el tiempo de generarlos), pero por sí solos **no** levantan la
comprobación desde la nube. Si algún vídeo se resiste con cookies frescas:

- **`YTDLP_PROXY`**: sacar las peticiones por un proxy residencial. Es lo más fiable
  desde la nube (ojo: los proxies gratuitos fallan más de lo que ayudan).
- **Ejecutar la app en tu propio equipo**: desde una IP doméstica no hay
  comprobación anti-bot ni hacen falta cookies, PO tokens ni proxy.

## Aviso legal

Esta herramienta se ofrece únicamente con fines educativos y de uso personal. Descarga solo contenido que te pertenezca, que sea de dominio público o que cuente con licencia de uso. Respeta los derechos de autor y los términos de servicio de cada plataforma; el autor no se responsabiliza del uso indebido de la aplicación.

## Licencia

[MIT](LICENSE)
