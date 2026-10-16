# VideoDL

Descargador universal de video y audio con interfaz web. Pega el enlace de un video y descárgalo en tu equipo en la calidad que quieras.

El backend usa **yt-dlp**, por lo que es compatible con más de 1000 sitios: YouTube, TikTok, Instagram, X / Twitter, Facebook, Reddit, Twitch, Vimeo y enlaces directos MP4/WebM, entre muchos otros.

## Características

- 🔍 **Análisis previo**: muestra título, autor, vistas, duración, miniatura y las calidades realmente disponibles.
- 🎬 **Descarga de video** en la máxima calidad o eligiendo una resolución concreta (MP4).
- 🎵 **Solo audio** en MP3 (192 kbps) mediante ffmpeg.
- 📊 **Progreso en vivo**: porcentaje, velocidad, tamaño y tiempo restante mientras se descarga en el servidor, con opción de cancelar.
- 💬 **Subtítulos** en `.SRT` o `.VTT` (manuales y automáticos) en el idioma que elijas.
- 🖼️ **Descarga de la miniatura** de portada en su resolución original.
- 🖥️ **Interfaz web** oscura y responsive, sin dependencias de frameworks en el frontend.
- 📋 Botón **Pegar** desde el portapapeles para analizar al instante.
- ✅ Mensajes de error claros en español (video privado, restringido, URL no soportada, etc.).
- 🧹 Limpieza automática de los archivos temporales del servidor.

## Requisitos

- Python 3.10 o superior
- **ffmpeg** (necesario para unir video + audio en calidades altas y para convertir a MP3)

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

## Estructura del proyecto

```
videodl/
├── main.py              # Backend FastAPI: /api/info y /api/download
├── requirements.txt     # Dependencias de Python
├── static/
│   ├── index.html       # Interfaz web
│   ├── style.css        # Estilos
│   └── app.js           # Lógica del frontend
└── README.md
```

## API

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/health` | Comprueba el estado del servicio y si ffmpeg está disponible. |
| `POST` | `/api/info` | Analiza una URL y devuelve metadatos, calidades y subtítulos disponibles. Cuerpo: `{ "url": "..." }` |
| `POST` | `/api/download` | Descarga y devuelve el archivo (bloqueante, sin progreso). Cuerpo: `{ "url": "...", "mode": "best \| audio \| video-<altura>", "title": "..." }` |
| `POST` | `/api/jobs` | Inicia una descarga en segundo plano. Devuelve `{ "id": "..." }`. Mismo cuerpo que `/api/download`. |
| `GET` | `/api/jobs/{id}` | Estado y progreso: `status`, `percent`, `speed`, `eta`, `downloaded`, `total`, `phase`. |
| `GET` | `/api/jobs/{id}/file` | Descarga el archivo del trabajo terminado (libera los recursos al enviarlo). |
| `POST` | `/api/jobs/{id}/cancel` | Cancela un trabajo en curso. |
| `POST` | `/api/subtitles` | Devuelve los subtítulos de un idioma. Cuerpo: `{ "url": "...", "lang": "en", "format": "srt \| vtt", "title": "..." }` |
| `GET` | `/api/thumbnail` | Devuelve la miniatura como archivo. Parámetros: `url`, `title`. |

> El frontend usa `/api/jobs` para mostrar la barra de progreso en vivo. `/api/download` se mantiene para usos programáticos o scripts.

## Aviso legal

Esta herramienta se ofrece únicamente con fines educativos y de uso personal. Descarga solo contenido que te pertenezca, que sea de dominio público o que cuente con licencia de uso. Respeta los derechos de autor y los términos de servicio de cada plataforma; el autor no se responsabiliza del uso indebido de la aplicación.

## Licencia

[MIT](LICENSE)
