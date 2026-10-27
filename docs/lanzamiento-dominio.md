# Guía de lanzamiento y compra de dominio

Revisión del 26 de octubre de 2026. Resume el estado del proyecto para publicarlo con
un dominio propio y las comprobaciones que quedan fuera del código.

## 1. Dominio: qué está disponible

Comprobación rápida con DNS y RDAP (los registradores son la fuente definitiva; vuelve a
confirmar el precio y la disponibilidad antes de pagar):

| Dominio | Estado el 26/10/2026 | Notas |
|---|---|---|
| `fastools.app` | **Registrado** | Creado el 12/07/2026, expira el 12/07/2027. Registrador: Porkbun. Tiene `clientDeleteProhibited` y `clientTransferProhibited`. No está libre. |
| `fastools.com` | **Registrado** | Dominio antiguo (2012), a nombre de un tercero. Registrador: NameBright/TurnCommerce. Expira el 26/11/2026, pero eso no lo libera automáticamente. |
| `fastools.es` | Sin registro A | Probablemente libre, pero `.es` no ofrece RDAP público. Confírmalo en un registrador español (p. ej. NIC.es o un agente). |
| `fastools.dev` | Sin registro RDAP | Aparece libre. `.dev` exige HTTPS (está en la lista HSTS de Google). |
| `fastools.tools` | Sin registro RDAP | Aparece libre. Encaja con el nombre «FasTools», aunque es más largo. |
| `fastools.site` | Sin registro RDAP | Aparece libre. |
| `fastools.pro` | Sin registro RDAP | Aparece libre. |
| `fastools.store` | Sin registro RDAP | Aparece libre. |
| `fastools.cloud` | Sin registro RDAP | Aparece libre. |
| `fastools.page` | Sin registro RDAP | Aparece libre. |
| `fastools.wiki` | Sin registro RDAP | Aparece libre. |
| `fastools.io` | **Registrado** | No disponible. |
| `fastools.online` | **Registrado** | No disponible. |
| `fastools.xyz` | **Registrado** | No disponible. |
| `fastools.cc` | **Registrado** | No disponible. |

Recomendación:

- Si el público es español, `fastools.es` es la opción más coherente con el contenido y
  con la marca. Confirma antes que está libre.
- Si quieres un dominio corto y disponible hoy, `fastools.tools` o `fastools.dev` son
  buenas alternativas. `.app` no se puede comprar salvo que el titular actual lo venda.
- No compres `fastools.com` a un inversor sin comparar el precio con registrar una
  alternativa: suele ser mucho más caro y no aporta SEO por sí solo.
- Comprueba que «FasTools» no esté registrado como marca en tu jurisdicción antes de
  invertir en el dominio. No es asesoramiento jurídico.

> La marca visible por defecto es `FasTools.app`. Si compras otro dominio, define
> `SITE_NAME=FasTools.es` (o el nombre que elijas): se aplica a títulos, cabecera, pie,
> Open Graph y la nota de privacidad. Los metadatos de los PDF usan «FasTools» sin sufijo.

## 2. ¿Está listo el código?

Sí para funcionar; no para publicar sin elegir dominio y configurar el despliegue.

### Ya resuelto

- [x] Catálogo único, portada, directorio, búsqueda y herramientas relacionadas.
- [x] Compresión de vídeo, clips verticales, imágenes, PDF, QR y WhatsApp.
- [x] Transcripción con `faster-whisper` opcional y degradación limpia a `503`.
- [x] Robots, sitemap, canonical, Open Graph, títulos y descripciones por página.
- [x] CSP, `nosniff`, `frame-ancestors`, límite de subida y rate limiting.
- [x] Sin cookies de analítica, sin anuncios activos y sin scripts de terceros.
- [x] Modo claro/oscuro, navegación móvil y nota de privacidad redactada.
- [x] Pruebas de API, catálogo, SEO, seguridad, QR y transcripción.
- [x] Dockerfile, Compose, Render y Railway; `/api/health` público y acotado.
- [x] Limpieza de temporales y trabajos con TTL.

### Bloqueantes antes de publicar

- [ ] **Dominio decidido y comprado**; actualizar `SITE_URL` con `https://` y sin barra
  final.
- [ ] **HTTPS** activo en el host. Los dominios `.app` y `.dev` lo exigen; no publiques
  HTTP.
- [ ] **Proveedor de alojamiento**: elige uno y revisa que su tratamiento de datos encaje
  con la nota de privacidad. Si quieres detallarlo, añade el nombre y el país.
- [ ] **Plan de transcripción**: en Render gratuito (0,1 CPU / 512 MB) usa `tiny` y audios
  cortos, o sube de plan. Con `base`/`small` necesitas 1–2 GB de RAM.
- [ ] **Correo del dominio**: SPF, DKIM y DMARC si vas a enviar desde `@tudominio`.

### Recomendado antes o poco después de publicar

- [ ] **Imagen Open Graph** (`og:image`) de 1200×630 px y `twitter:image`. Hoy se comparte
  sin miniatura.
- [ ] **Favicon PNG** y `apple-touch-icon` además del SVG (algunos navegadores y
  previsualizaciones no usan SVG).
- [ ] **Página 404 propia** con enlaces a herramientas, en lugar del 404 por defecto.
- [ ] **Monitorización**: uptime, logs con retención y alerta si `/api/health` falla.
- [ ] **Copia de seguridad** de configuración y variables; los archivos de usuario no se
  guardan, pero el modelo de transcripción y la config sí importan.
- [ ] **Search Console / Bing Webmaster** y envío del sitemap.
- [ ] **Analítica**: si añades Plausible/GA/AdSense, amplía la nota de privacidad y añade
  consentimiento cuando corresponda. Hoy no hay cookies de terceros. Lo mismo si añades
  cuentas, formularios o publicidad.
- [ ] **Límites de producción**: decide `RATE_LIMIT_PER_MINUTE`, `MAX_CONCURRENT_JOBS`,
  `MAX_UPLOAD_MB`, `TRANSCRIBE_MAX_SECONDS` y `TRANSCRIBE_MAX_MB`.
- [ ] **Un solo worker**: los trabajos viven en memoria. No escales horizontalmente sin
  mover el estado a Redis/DB y compartir el almacenamiento temporal.
- [ ] **Prueba real** de cada herramienta desde el dominio final, incluida la subida de
  un audio y la descarga de TXT/SRT/VTT.
- [ ] **Revisión de marca**: dominio y nombre no deben chocar con una marca registrada.

## 3. Puesta en marcha mínima

1. Compra el dominio y configura los DNS del host.
2. Define las variables:

   ```env
   SITE_URL=https://tudominio.tld
   SITE_NAME=FasTools.tld
   RATE_LIMIT_PER_MINUTE=60
   MAX_CONCURRENT_JOBS=2
   MAX_UPLOAD_MB=200
   TRANSCRIBE_MODEL=tiny   # o base/small según el plan
   TRANSCRIBE_MAX_MB=100
   TRANSCRIBE_MAX_SECONDS=1800
   ```

3. Construye la imagen. Sin transcripción:

   ```bash
   docker build -t fastools .
   ```

   Con transcripción y modelo precargado:

   ```bash
   docker build \
     --build-arg INSTALL_TRANSCRIBE=1 \
     --build-arg PRELOAD_TRANSCRIBE=1 \
     --build-arg TRANSCRIBE_MODEL=tiny \
     -t fastools .
   ```

4. Arranca con **un worker** y comprueba:

   ```bash
   curl -fsS https://tudominio.tld/api/health
   curl -fsS https://tudominio.tld/robots.txt
   curl -fsS https://tudominio.tld/sitemap.xml
   ```

5. Abre `/`, `/herramientas`, `/generador-qr`, `/transcribir-audio` y `/privacidad` desde
   el dominio real. Prueba un QR con la cámara y un audio corto con cada formato de salida.

## 4. Después de publicar

- Revisa los logs las primeras 24–48 h: errores 500, 429 por rate limit, tiempos de
  transcripción y memoria.
- Si usas `base` o `small`, vigila el RSS del contenedor. El modelo se carga una vez por
  proceso y se queda en memoria.
- Mantén la nota de privacidad al día si cambias host, analítica, publicidad o formas de
  contacto.
- Guarda una copia de `SITE_URL`, las variables de entorno y la versión desplegada.
