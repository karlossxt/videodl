# Changelog

Todas las novedades relevantes de este proyecto. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [2.0.0]

### Añadido
- Suite de pruebas con pytest (seguridad, utilidades, trabajos, API) y CI en GitHub Actions.
- Configuración de lint con ruff (`pyproject.toml`) y `.editorconfig`.
- `SECURITY.md`, `CONTRIBUTING.md` y `.env.example`.
- Logging estructurado en todo el backend.
- Protección anti-SSRF en todas las URLs y en la descarga de miniaturas.
- Rate limiting por IP y límite de trabajos concurrentes (`RATE_LIMIT_PER_MINUTE`, `MAX_CONCURRENT_JOBS`).
- Cabeceras de seguridad y CSP configurables.
- `HEALTHCHECK` en el Dockerfile y healthchecks/límites en Docker Compose.

### Cambiado
- El backend se divide en el paquete `videodl/` (config, security, jobs, media, routers…).
- Los tres almacenes de trabajos duplicados se sustituyen por una clase `JobStore` genérica.
- Las cookies de sesión se guardan con permisos restringidos en un directorio privado.
- `/api/health` deja de exponer datos de configuración sensibles.
- La limpieza por TTL ya no borra trabajos en curso.
- Dependencias actualizadas y `python-multipart` con versión mínima corregida.
- El JavaScript del frontend comparte utilidades en `static/common.js` (objeto global `VD`) en lugar de duplicarlas en cada página, y las peticiones llevan timeout.
- Las páginas HTML usan rutas absolutas, metadatos descriptivos y roles/etiquetas ARIA (pestañas, zonas de arrastre, barras de progreso y avisos) con foco visible y respeto por `prefers-reduced-motion`.

### Arreglado
- Un ffmpeg colgado ya no retiene un hilo para siempre (timeout de proceso).
- Las descargas usan `socket_timeout` para no quedar colgadas.
- `resolve_output` ignora archivos incompletos (`.part`, `.ytdl`).
- El idioma de subtítulos se valida para que no actúe como comodín.
- Se evita devolver rutas internas del servidor en los mensajes de error.
- XSS en la lista de calidades: los datos del vídeo se insertan como texto y no como HTML.
- El sondeo de trabajos del frontend ya no se queda en marcha para siempre ni sigue consultando un trabajo antiguo tras restablecer (fuga en el compresor y en los clips).
