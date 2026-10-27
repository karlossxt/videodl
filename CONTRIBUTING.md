# Contribuir a FasTools.app

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

Necesitas **ffmpeg** y **ffprobe** instalados para comprimir vídeo y recortar
clips. El generador de enlaces de WhatsApp funciona sin ellos.

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
se saltan solas; el CI sí lo instala y las ejecuta. `tests/test_site.py` valida el
catálogo, los enlaces internos, la búsqueda, la navegación móvil y el SEO.

El código está organizado en el paquete `videodl/`:

- `config.py` – variables de entorno validadas y detección de ffmpeg.
- `catalog.py` – registro único de categorías, herramientas y estados.
- `views.py` – navegación, tarjetas, portada, directorio y SEO.
- `pages.py` – rutas HTML, alias canónicos, sitemap y robots.
- `security.py` – rate limit y concurrencia.
- `jobs.py` – almacén de trabajos en memoria.
- `media.py` – ffmpeg/ffprobe.
- `compressor.py`, `clips.py`, `whatsapp.py` – routers de la API.
- `app.py` – creación de la aplicación.

## Pautas

- Mantén un único worker: el progreso vive en memoria.
- Añade una prueba para cada arreglo o función nueva.
- Añade herramientas nuevas al catálogo de `catalog.py`; evita duplicar listas
  en HTML o JavaScript.
- Mensajes para el usuario en español; código y comentarios claros.
- No reintroduzcas descargas de plataformas externas, cookies, proxies ni
  utilidades de impersonación.
