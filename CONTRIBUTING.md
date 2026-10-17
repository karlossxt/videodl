# Contribuir a VideoDL

¡Gracias por tu interés! Este documento resume cómo montar el proyecto y qué se
espera de un cambio.

## Puesta en marcha

```bash
git clone https://github.com/karlossxt/videodl.git
cd videodl
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
```

Necesitas **ffmpeg** instalado (para unir vídeo+audio, MP3 y recortes).

```bash
python -m uvicorn main:app --port 8000
```

## Antes de enviar un cambio

```bash
ruff check .     # estilo y errores comunes
pytest           # pruebas (las que dependen de ffmpeg se saltan si no está)
```

`tests/test_e2e_ffmpeg.py` genera un vídeo con ffmpeg y recorre el compresor y el
recortador de clips de principio a fin. Si no tienes ffmpeg instalado esas pruebas
se saltan solas; el CI sí lo instala y las ejecuta.

El código está organizado en el paquete `videodl/`:

- `config.py` – variables de entorno validadas y detección de ffmpeg.
- `security.py` – validación de URLs, anti-SSRF, rate limit y concurrencia.
- `jobs.py` – almacén de trabajos en memoria.
- `media.py` – ffmpeg/ffprobe y opciones de yt-dlp.
- `downloader.py`, `compressor.py`, `clips.py` – routers de la API.
- `app.py` – creación de la aplicación.

## Pautas

- Mantén un único worker: el progreso vive en memoria.
- Añade una prueba para cada arreglo o función nueva.
- Mensajes para el usuario en español; código y comentarios claros.
- No fijes `yt-dlp` a una versión exacta (sus extractores cambian a menudo).
