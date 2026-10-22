# Política de seguridad

## Versiones soportadas

Solo se da soporte a la última versión de la rama principal.

## Cómo reportar una vulnerabilidad

Si encuentras un problema de seguridad, **no abras un issue público**. Escribe al
autor del repositorio (ver el perfil de GitHub) con:

- una descripción del problema y su impacto,
- los pasos para reproducirlo,
- y, si es posible, una propuesta de solución.

Se intentará responder en un plazo razonable.

## Superficie de riesgo

VideoDL Tools acepta únicamente archivos subidos por el usuario y ejecuta
`ffmpeg`/`ffprobe` en el servidor. No hay descargas de plataformas externas, URLs
de entrada, proxies ni cookies de sesión. Las defensas incluyen:

- **Límite de subida** en el compresor y los clips (`MAX_UPLOAD_MB`) y validación
  del tipo de archivo antes de procesarlo.
- **Rate limiting** por IP (`RATE_LIMIT_PER_MINUTE`) y límite de trabajos
  simultáneos (`MAX_CONCURRENT_JOBS`).
- **Cabeceras de seguridad** y CSP configurables.
- **Temporales** aislados por trabajo y borrados al terminar o al vencer el TTL.
- **Tiempo máximo de ffmpeg** configurable con `FFMPEG_TIMEOUT_SECONDS`.
- El tema claro/oscuro se guarda solo en `localStorage`; no se envía al servidor.

Nunca subas a un repositorio público un `.env` con secretos: ya está en
`.gitignore`.
