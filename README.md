# VideoDL

Descargador universal de video y audio con interfaz web. Pega el enlace de un video y descárgalo en tu equipo en la calidad que quieras.

El backend usa **yt-dlp**, por lo que es compatible con más de 1000 sitios: YouTube, TikTok, Instagram, X / Twitter, Facebook, Reddit, Twitch, Vimeo y enlaces directos MP4/WebM, entre muchos otros.

## Características

- 🔍 **Análisis previo**: muestra título, autor, vistas, duración, miniatura y las calidades realmente disponibles.
- 🎬 **Descarga de video** en la máxima calidad o eligiendo una resolución concreta (MP4).
- 🎵 **Solo audio** en MP3 (192 kbps) mediante ffmpeg.
- 📊 **Progreso en vivo**: porcentaje, velocidad, tamaño y tiempo restante mientras se descarga en el servidor, con opción de cancelar.
- ✂️ **Recortador de fragmentos**: descarga solo la parte del video que elijas (inicio y fin) usando ffmpeg.
- 📚 **Cola en lote**: pega varios enlaces, analízalos y descárgalos en orden con estado por elemento (el historial se guarda en el navegador).
- 💬 **Subtítulos** en `.SRT` o `.VTT` (manuales y automáticos) en el idioma que elijas.
- 🖼️ **Descarga de la miniatura** de portada en su resolución original.
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

## Estructura del proyecto

```
videodl/
├── main.py                # Backend FastAPI
├── requirements.txt       # Dependencias de Python
├── static/
│   ├── index.html         # Interfaz web
│   ├── style.css          # Estilos
│   └── app.js             # Lógica del frontend
├── Dockerfile             # Imagen de producción (incluye ffmpeg)
├── docker-compose.yml     # Ejecución local/servidor con Docker
├── render.yaml            # Blueprint para Render
├── railway.json           # Configuración para Railway
└── README.md
```

## API

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/health` | Comprueba el estado del servicio y si ffmpeg está disponible. |
| `POST` | `/api/info` | Analiza una URL y devuelve metadatos, calidades y subtítulos disponibles. Cuerpo: `{ "url": "..." }` |
| `POST` | `/api/download` | Descarga y devuelve el archivo (bloqueante, sin progreso). Cuerpo: `{ "url": "...", "mode": "best \| audio \| video-<altura>", "title": "...", "start": 0, "end": 30 }` |
| `POST` | `/api/jobs` | Inicia una descarga en segundo plano. Devuelve `{ "id": "..." }`. Mismo cuerpo que `/api/download`. |
| `GET` | `/api/jobs/{id}` | Estado y progreso: `status`, `percent`, `speed`, `eta`, `downloaded`, `total`, `phase`. |
| `GET` | `/api/jobs/{id}/file` | Descarga el archivo del trabajo terminado (libera los recursos al enviarlo). |
| `POST` | `/api/jobs/{id}/cancel` | Cancela un trabajo en curso. |
| `POST` | `/api/subtitles` | Devuelve los subtítulos de un idioma. Cuerpo: `{ "url": "...", "lang": "en", "format": "srt \| vtt", "title": "..." }` |
| `GET` | `/api/thumbnail` | Devuelve la miniatura como archivo. Parámetros: `url`, `title`. |

> El frontend usa `/api/jobs` para mostrar la barra de progreso en vivo. `/api/download` se mantiene para usos programáticos o scripts.
>
> Los campos opcionales `start` y `end` (en segundos) recortan el fragmento a descargar. Si se indican, `end` debe ser mayor que `start` y hace falta ffmpeg.

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

- **ffmpeg** debe estar presente (la imagen Docker ya lo incluye) para unir video+audio, generar MP3 y recortar fragmentos.
- **Mantén yt-dlp actualizado**: las plataformas cambian a menudo. Al reconstruir la imagen se instala la última versión permitida por `requirements.txt`.
- Los archivos se descargan a una carpeta temporal y se borran en cuanto se envían al usuario. Al reiniciar el servicio se limpian los restos.
- Usa la app solo para contenido propio o con licencia; respeta los términos de cada plataforma.

## Aviso legal

Esta herramienta se ofrece únicamente con fines educativos y de uso personal. Descarga solo contenido que te pertenezca, que sea de dominio público o que cuente con licencia de uso. Respeta los derechos de autor y los términos de servicio de cada plataforma; el autor no se responsabiliza del uso indebido de la aplicación.

## Licencia

[MIT](LICENSE)
