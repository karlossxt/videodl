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

VideoDL acepta URLs y archivos del usuario y ejecuta `yt-dlp` y `ffmpeg` en el
servidor. Las defensas incluyen:

- **Anti-SSRF**: las URLs se comprueban antes de usarse y se rechazan las
  direcciones internas/privadas (incluidas las redirecciones de la miniatura).
- **Límite de subida** en el compresor y los clips (`MAX_UPLOAD_MB`).
- **Rate limiting** por IP (`RATE_LIMIT_PER_MINUTE`) y límite de trabajos
  simultáneos (`MAX_CONCURRENT_JOBS`).
- **Cabeceras de seguridad** y CSP configurables.
- **Temporales** aislados por trabajo y borrados al terminar o al vencer el TTL.
- Las cookies de sesión (si se configuran) se guardan con permisos restringidos.

Nunca subas a un repositorio público un `cookies.txt` ni un `.env` con secretos:
ya están en `.gitignore`.
