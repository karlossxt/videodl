# Changelog

Todas las novedades relevantes de este proyecto. Formato basado en
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).

## [3.2.0] - 2026-10-25

### Añadido
- **Suite PDF en el navegador** con cuatro herramientas:
  - `/unir-pdf`: combina varios PDF, permite reordenar documentos y avisa de que unir
    no comprime.
  - `/dividir-pdf`: extrae páginas o rangos (`1-3, 5, 8-10`) conservando el orden
    escrito, con vista previa y validación de límites.
  - `/imagenes-a-pdf`: crea un PDF con imágenes JPG/PNG, reordena, elige A4 vertical,
    A4 horizontal o el tamaño de cada imagen y conserva la transparencia del PNG.
  - `/pdf-a-jpg`: renderiza páginas con calidad y escala ajustables; una página se
    descarga como JPG y varias como ZIP.
- **pdf-lib 1.17.1** (MIT) y **PDF.js 6.4.299** (Apache-2.0) vendorizados en
  `static/vendor/pdf/`, con fuentes estándar, CMaps, ICC y WASM locales. No se usa CDN.
  `manifest.json` incluye versiones, licencias, integridad npm y SHA-256 de los 203
  archivos vendorizados (sin contar el propio manifest); una prueba verifica que
  coincide con el contenido real.
- **Núcleo puro testeable** en `static/pdf-core.js`: validación por firma, rangos,
  orden, geometría A4, límites de render, nombres seguros, CRC32 y un escritor ZIP
  *store* sin JSZip.
- **Interfaz compartida** (`static/pdf-tool.html`, `static/pdf-suite.js`,
  `videodl/pdf_pages.py`) con selección o arrastre, lista reordenable, miniaturas,
  progreso real, tamaños de entrada/salida y descargas.
- Límites explícitos: 25 MB por archivo, 75 MB total, 10 PDF, 20 imágenes, 300 páginas
  al unir/dividir, 80 al convertir a JPG, 64 MP por imagen de entrada y 40 MP / 8192 px
  por página renderizada.
- Errores claros para PDF corruptos, vacíos, sin páginas y protegidos con contraseña
  (no se intenta descifrar). Avisos de memoria para selecciones grandes.
- Pruebas nuevas: `tests/pdf-tools.test.js` (Node) y `tests/test_pdf_tools.py`
  (contrato, catálogo, integridad de vendor, límites y ZIP interoperable). El CI
  ejecuta las suites Node de imagen y PDF, además de pytest y el build Docker.
- Documentación en `docs/herramientas-pdf.md` con arquitectura, límites, navegadores,
  privacidad, matriz E2E de 64 comprobaciones y limitaciones conocidas.

### Cambiado
- El catálogo incorpora las cuatro rutas nuevas; `unir-pdf` deja de mostrarse como
  «Próximamente» y se añaden al sitemap, a la navegación «PDF» y a las herramientas
  relacionadas. `comprimir-pdf` sigue pendiente y no se presenta como disponible.
- La CSP incluye `worker-src 'self'` para el worker module local de PDF.js.
- `README.md` y `CHANGELOG.md` documentan la nueva suite y sus límites.

## [3.1.0] - 2026-10-22

### Añadido
- **Catálogo único de herramientas** en `videodl/catalog.py`: categorías, estado
  (`available`/`soon`), iconos, descripciones y palabras clave. La portada, el
  directorio y las herramientas relacionadas se generan desde ese registro.
- **Nueva portada** con buscador instantáneo, filtros por categoría, herramientas
  destacadas, catálogo completo y flujos relacionados. `/herramientas` reutiliza el
  mismo catálogo y buscador.
- **Modo claro opcional** con preferencia guardada, menú móvil accesible y navegación,
  cabecera y pie compartidos entre todas las páginas.
- **SEO técnico**: canonical y Open Graph por página, `sitemap.xml`, `robots.txt` y
  variable `SITE_URL` (con `RENDER_EXTERNAL_URL` como respaldo en Render).
- Espacios publicitarios preparados en HTML/CSS, ocultos y sin scripts de terceros.
- Pruebas de catálogo, enlaces internos, búsqueda, navegación móvil, accesibilidad
  básica, modo claro y SEO en `tests/test_site.py`.
- **Tres herramientas de imagen que funcionan en el navegador**:
  - `/comprimir-imagen`: calidad ajustable, formato original o salida JPG/PNG/WebP,
    comparación de tamaños y porcentaje real de reducción (también si es negativo).
  - `/convertir-imagen`: conversión entre JPG, PNG y WebP con control de calidad,
    detección de transparencia, aviso al elegir JPG y color de fondo configurable.
  - `/redimensionar-imagen`: píxeles o porcentaje, proporción bloqueable, presets
    rápidos y límites de 16 384 px por lado y 64 MP.
- **Privacidad por diseño**: las imágenes no se suben. La validación por firma de bytes,
  el canvas, la codificación y la descarga se hacen en el cliente; no hay endpoints de
  imagen ni peticiones a `/api/`. Se revocan las URL `blob:` y se vacía el canvas al
  cambiar de archivo o cerrar la página.
- **Plantilla y motor compartidos** (`static/imagen-tool.html`, `static/image-tools.js`,
  `static/imagenes.js`) con contenido propio por modo en `videodl/image_pages.py`,
  navegación «Imágenes» y estilos responsive con fondo de cuadros para transparencia.
- Pruebas nuevas: `tests/image-tools.test.js` (Node, sin DOM) para sniffing de JPG, PNG,
  WebP, GIF, AVIF, BMP y SVG, límites, proporciones, calidad y nombres seguros;
  `tests/test_image_tools.py` para el contrato HTML, el catálogo, la ausencia de código
  de subida y la ejecución de las pruebas Node. Matriz E2E de 91 comprobaciones con
  Chrome headless documentada en `docs/herramientas-imagen.md`.
- Documentación de compatibilidad de navegadores, límites, manejo de transparencia y
  limitaciones conocidas (EXIF no se conserva, WebP depende del navegador, ampliar no
  crea detalle, memoria en móviles).

### Cambiado
- Las herramientas no implementadas aparecen como **Próximamente**, sin enlace ni
  página vacía.
- `static/index.html` y `static/herramientas.html` se sustituyen por páginas generadas
  desde el catálogo.
- Los alias antiguos (`/comprimir`, `/clips-verticales`, `/clips-twitch-vertical`,
  `/generador-enlace-whatsapp`) redirigen con **301** a su URL canónica.
- Versión **3.1.0**.

## [3.0.0]

### Cambiado (ruptura deliberada)
- **VideoDL deja de descargar vídeos de plataformas externas.** La app solo procesa
  archivos aportados por el usuario: compresión, clips verticales y enlaces de
  WhatsApp. Se retiran yt-dlp, el proveedor de PO tokens (bgutil), el runtime Deno,
  las cookies, los proxies, la impersonación y la lista de plataformas pausadas.
- El **recortador de clips** ya no acepta enlaces: solo archivos subidos. Se elimina
  la pestaña «Pegar enlace» y el modo URL del backend.
- La **portada** pasa a un directorio de herramientas; el formulario de descargas y su
  JavaScript se eliminan. El rediseño completo queda para más adelante.
- `/api/health` publica solo capacidades activas y límites públicos (sin cookies,
  rutas ni diagnósticos de red).
- Las rutas antiguas (`/api/info`, `/api/download`, `/api/jobs…`, `/api/subtitles`,
  `/api/thumbnail`, `POST /api/clips`) responden **410 Gone**.
- `README`, `.env.example`, `Dockerfile`, `requirements.txt` y `pyproject.toml`
  actualizados a la nueva arquitectura. Versión **3.0.0**.

### Añadido
- Módulo `videodl/tasks.py` con el lanzador de trabajos en segundo plano, extraído del
  antiguo `downloader.py` para evitar dependencias circulares.
- Módulo `videodl/legacy.py` con las respuestas 410 de las rutas retiradas.
- Pruebas de regresión de subida, compresión, clips y QR, y comprobaciones de que las
  dependencias de descarga no vuelven al proyecto.

### Corregido
- Los errores genéricos del compresor y del recortador ya no exponen `str(exc)` al
  cliente: solo se publican los mensajes controlados por la app.
- Mojibake en `pyproject.toml` y `videodl/__init__.py`.

## [2.4.0]

### Añadido
- Página **`/legal`** con aviso legal, política de privacidad, términos de uso y
  contacto/retirada de contenido, enlazada desde el pie de todas las páginas.
- Hueco para el **botón de Ko-fi** en el pie, oculto hasta configurar el usuario
  para no dejar un enlace roto.

## [2.3.3]

### Corregido
- **Dailymotion, fallos intermitentes**: cuando la extracción devolvía «No video
  formats found», se reintentaba tres veces seguidas y sin pausa, así que a veces se
  agotaban los intentos antes de que Dailymotion publicara el manifest. Ahora tiene
  cuatro intentos (tres en descarga) con esperas de 2, 4 y 6 segundos. El resto de
  webs mantiene tres intentos (dos en descarga) con una pausa de 1 segundo.

## [2.3.2]

### Cambiado
- **YouTube y Reddit, no disponibles por el momento**: además de la leyenda en la
  portada, la app **rechaza esos enlaces al instante** con el motivo y alternativas
  que sí funcionan (TikTok, Instagram, X, Facebook, Twitch, Dailymotion, Vimeo o un
  MP4/WebM directo), en vez de esperar a una extracción que desde el servidor acaba
  fallando. La lista se cambia sin tocar código con `VIDEODL_DISABLED_PLATFORMS`
  (`""` vuelve a permitir todas).
- `/api/health` publica `disabled_platforms` para saber de un vistazo qué webs están
  pausadas.
- La leyenda de la portada pasa de «Próximamente» a «No disponible».

## [2.3.1]

### Corregido
- **Compresor, tope de resolución**: si el vídeo ya cabía en el tamaño pedido, se
  copiaba tal cual aunque superara la resolución elegida. Ahora se reescala cuando
  hace falta.

## [2.3.0]

Preparación del lanzamiento: YouTube y Reddit quedan **pendientes** (necesitan un
proxy residencial de pago) y se revisan las herramientas que ya funcionan.

### Añadido
- La portada marca **YouTube y Reddit como «Próximamente»** y explica el motivo, en
  vez de prometer plataformas que desde el servidor no descargan. Se añaden
  **Dailymotion** y **Vimeo** a la lista de sitios compatibles (probados en producción).
- Dailymotion: si la primera extracción devuelve 0 formatos (fallo puntual habitual
  desde una IP de servidor), se **reintenta sola** antes de rendirse. También se
  reintenta el análisis de la URL.
- El botón de **solo audio** aparece en webs que únicamente ofrecen formatos
  combinados (Dailymotion): el MP3 se extrae del MP4.

### Corregido
- **Compresor, vídeo vertical**: el tope de resolución se aplica al lado corto. Un
  1080x1920 con «720p» salía en 406x720; ahora sale en 720x1280. Sin tope, conserva
  su resolución (antes también se achicaba a 608x1080).
- **Compresor, tamaño incumplido**: si el objetivo no cabía ni con la calidad mínima,
  se devolvía un archivo **más grande del pedido** sin avisar. Ahora se reintenta con
  un tramo de progreso propio y, si aun así no cabe, el trabajo termina con un error
  claro que sugiere un tamaño mayor (nunca se entrega algo que no cabe en WhatsApp).
- **Compresor, WebM/VP9**: si el archivo ya cabía se remultiplexaba a MP4 conservando
  VP9/Opus, que WhatsApp, iOS y QuickTime no reproducen. Solo se copia sin recodificar
  si es H.264 + AAC/MP3; el resto se convierte.
- **Compresor**: la barra de progreso ya no retrocede de 98 % a 5 % cuando hace falta
  una segunda pasada.
- **Clips, formato «Original»**: los vídeos verticales se limitaban por la altura
  (un 1080x1920 quedaba en 608x1080). Ahora se limita el lado corto y conserva la
  resolución.
- El tamaño personalizado del compresor usa el máximo que publica la API
  (`max_target_mb`) en vez de un 200 fijo.

## [2.2.8]

### Corregido
- Un **único Secret File con otro nombre** no se detectaba: si el servicio tenía
  solo `reddit.txt` (sin «cookie» en el nombre y sin `cookies.txt`), la app
  arrancaba **sin ninguna cookie**. Ahora, cuando no hay `cookies.txt`, también se
  reconoce por su contenido, así que un tarro de Reddit puede ser el único fichero.

## [2.2.7]

### Añadido
- Los Secret Files de cookies en **JSON** (Cookie-Editor, EditThisCookie) se
  convierten al formato Netscape al cargarlos, igual que ya se hacía con
  `YTDLP_COOKIES` y `YTDLP_COOKIES_B64`. Antes se ignoraban **en silencio**: el
  tarro estaba subido y parecía que la subida no había llegado.
- `/api/health` publica `cookies_ignored`: tarros que existen pero no se pudieron
  usar, con el motivo (formato desconocido, vacío, sin permisos). Solo lista
  ficheros que *parecen* cookies, nunca otros secretos.

### Corregido
- Los ficheros extra se descubren con `stat` en vez de `Path.is_file()`, que
  devuelve `False` sin avisar cuando falta permiso de lectura.

## [2.2.6]

### Añadido
- Los errores de sesión dicen ahora **qué pasa con las cookies de esa web** en vez
  de un «añade cookies» que no distingue nada: si no hay ningún tarro de esa
  plataforma, si lo hay pero se exportó sin la cuenta iniciada, si la sesión está
  caducada (yt-dlp no envía cookies caducadas, así que parece configurado y no
  autentica) o si la trae vigente y aun así la rechazan (suele ser la IP del
  servidor). Se ve en `/api/info` y en el error del trabajo, y no expone valores
  de cookies: solo cuántas hay, de qué web y si caducaron.
- `config.cookie_status(url)`: cuántas cookies hay de esa web en la copia de
  trabajo y si traen sesión vigente o caducada.

## [2.2.5]

### Añadido
- Admite **varios Secret Files de cookies a la vez**, uno por plataforma
  (`cookies.txt` para YouTube, `reddit.txt` para Reddit…). Se detectan por su
  contenido en formato Netscape y se unen en una sola copia de trabajo: las cookies
  van por dominio, así que cada web recibe solo las suyas. Ante una cookie repetida
  manda siempre `cookies.txt`, de modo que añadir tarros solo puede aportar sitios
  nuevos. `/api/health` publica los nombres de todos en `cookies_file`
  (`"cookies.txt, reddit.txt"`).

### Corregido
- **Reddit no descargaba nada** y el error que se veía era el mensaje crudo de
  yt-dlp en inglés. Reddit cerró su API pública a los anónimos, así que exige una
  sesión iniciada («Account authentication is required») **para cualquier vídeo**.
  Ahora hay un mensaje que lo explica y dice qué hacer, y otro para cuando Reddit
  bloquea la IP del servidor para su API (ahí las cookies no bastan: hace falta
  `YTDLP_PROXY`).

## [2.2.4]

### Corregido
- **TikTok no descargaba nada**, y el mensaje que aparecía («El video tiene
  restricción de edad») no tenía nada que ver con la causa. Eran tres fallos
  distintos:
  - Faltaba el extra `curl-cffi` de yt-dlp, que aporta la **impersonación de
    navegador**; sin él TikTok responde *"Unexpected response from webpage
    request"*. Es independiente del runtime de JavaScript que necesita YouTube.
  - El traductor de errores buscaba «age» y «Confirm» en el texto, y el aviso de
    yt-dlp contiene «webp**age** request» y «Confirm you are on the latest
    version»: **cualquier** fallo genérico se explicaba como restricción de edad.
    Ahora solo se detectan los mensajes reales de restricción de edad.
  - En **vídeo vertical** (TikTok, Reels, Shorts) la calidad se etiquetaba con el
    lado largo —un 1080x1920 aparecía como «1920p»— y el selector filtraba solo por
    altura, así que en un vertical `height<=720` no encajaba con ningún formato y
    se acababa descargando el mejor. La etiqueta pasa a usar el lado corto
    («1080p») y el selector también prueba por ancho.

### Añadido
- `/api/health` publica `impersonation` (si `curl-cffi` está instalado), para saber
  de un vistazo si las webs que exigen impersonación van a funcionar.

## [2.2.3]

### Añadido
- `/api/health` publica también el **nombre** del fichero de cookies
  (`cookies_file`; nunca la ruta). Con más de un Secret File es lo que hace falta
  para saber cuál se está usando y cuál hay que actualizar.

### Cambiado
- Si en `/etc/secrets` hay varios ficheros de cookies, se usa siempre `cookies.txt`.
  Antes ganaba el primero por orden alfabético, de modo que añadir un fichero nuevo
  (con otro nombre) podía cambiar cuál se usaba sin querer.

## [2.2.2]

### Corregido
- **La copia de cookies se degradaba sola.** yt-dlp reescribe el `cookiefile` al
  cerrar cada extracción y, cuando YouTube rota la sesión, guarda el tarro ya sin
  ella. La copia privada de la app se escribía una sola vez, al arrancar, así que
  bastaba con que una extracción perdiera la sesión para que **todas las
  siguientes** fueran anónimas sin avisar (yt-dlp solo avisa cuando nota que la
  pierde por el camino). Ahora la copia se rehace desde el original antes de cada
  extracción.

### Añadido
- `/api/health` dice de dónde salen las cookies (`cookies_source`) y si la última
  extracción vio que YouTube ya no las acepta (`cookies_rotated`). Con dos orígenes
  configurados a la vez es fácil actualizar el que no se usa; ahora se ve en un
  vistazo. Sigue sin publicarse ninguna ruta ni el contenido.

## [2.2.1]

### Añadido
- **Diagnóstico de cookies rotadas.** YouTube invalida las cookies de la sesión
  exportada cada cierto tiempo. Cuando eso pasa el `cookies.txt` sigue pareciendo
  correcto (trae `SID`, `__Secure-1PSID`…), yt-dlp avisa con un WARNING («The
  provided YouTube account cookies are no longer valid») y sigue como anónimo, así
  que el usuario acababa viendo el genérico «configura cookies de una sesión
  iniciada» cuando lo que tenía que hacer era **renovar** las que ya tenía. Ahora la
  app recuerda ese aviso y el error lo explica. Gracias a esto se encontró la causa
  real del bloqueo del servicio en producción: las cookies estaban rotadas.

### Notas
- Medido con la 2.2.0 ya desplegada: los PO tokens **sí** entran en juego (en el plan
  gratuito la extracción pasa de ~3 s a ~13 s, que es el tiempo de generarlos), pero
  por sí solos no levantan la comprobación anti-bot de YouTube desde la IP de
  Render. Siguen haciendo falta cookies frescas o una IP residencial
  (`YTDLP_PROXY`).

## [2.2.0]

### Añadido
- **PO tokens de YouTube: la imagen firma sus peticiones.** Se instala el proveedor
  [`bgutil-ytdlp-pot-provider`](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)
  2.0.2 en modo «script» sobre el Deno que ya traía `yt-dlp[default,deno]`. Es lo
  que YouTube exige a las IPs de nube para servir buena parte de sus vídeos: sin
  token responde con su comprobación anti-bot («Sign in to confirm you're not a
  bot») por muchas cookies que se manden y sea cual sea el cliente elegido.
  `videodl/pot.py` amplía el corte de 20 s del plugin con **`YTDLP_POT_TIMEOUT`**
  (segundos; `0` desactiva el proveedor), pensando en el plan gratuito (0,1 CPU).
- CI: la construcción de la imagen ya valida el montaje (el propio `RUN` ejecuta el
  script del proveedor) y una prueba (`tests/test_requirements.py`) impide que se
  desincronicen las versiones del plugin y del `Dockerfile`, porque el plugin
  rechaza la petición si no coinciden.

## [2.1.3]

### Añadido
- **Diagnóstico de cookies en `/api/health`**: `cookies_session` (si el fichero
  trae una sesión de YouTube iniciada) y `cookies_count`. El arranque avisa
  además por logging cuando las cookies cargadas no incluyen ninguna cookie de
  sesión (`SID`, `__Secure-1PSID`…). Es el fallo que más se cuela al depurar
  YouTube: el fichero es válido, la app lo carga, pero yt-dlp navega como
  anónimo y la plataforma sigue pidiendo verificación. Solo se leen **nombres**
  de cookies, nunca sus valores.

### Cambiado
- El mensaje de error anti-bot ya no promete que configurar cookies lo arregle:
  pide cookies **con sesión iniciada** y ofrece el proxy (`YTDLP_PROXY`) como
  alternativa, porque hay vídeos que YouTube no sirve a IPs de nube.

### Investigado (sin cambios de código)
- **La v1 no se rompió: es YouTube.** Medido desde Render con el servicio de
  pruebas (sin cookies, con `YTDLP_EXTRACTOR_ARGS=youtube:player_client=all` y
  también sin el runtime de JavaScript, como la v1): de 7 vídeos probados solo
  pasó el de control, muy popular; el resto recibió la comprobación anti-bot,
  incluido el que fallaba. Elegir cliente no cambia nada, así que desde la nube
  hacen falta cookies **con sesión** o un proxy residencial.

## [2.1.2]

### Cambiado
- **yt-dlp se instala con su runtime de JavaScript** (`yt-dlp[default,deno]`: el
  solucionador `yt-dlp-ejs` y el runtime `deno`). yt-dlp moderno lo exige para
  YouTube: sin él la extracción se degrada y avisa de que faltarán formatos. Se
  añadió investigando el «en la v1 sí funcionaba» (aquella imagen llevaba una
  versión anterior a este requisito). **No era la causa** del aviso anti-bot
  desde la nube, que se aclaró en 2.1.3.
- Prueba nueva (`tests/test_requirements.py`) para que no se vuelva a dejar
  yt-dlp sin los extras: el fallo solo aparecía al desplegar.

## [2.1.1]

### Arreglado
- **Las descargas con cookies ya no se pierden al terminar.** yt-dlp reescribe el fichero de cookies al cerrar cada descarga; si ese fichero es de solo lectura (Render monta así los Secret Files en `/etc/secrets`) saltaba un `PermissionError` que tiraba una descarga ya completada y, además, tapaba el error real (el usuario veía un genérico «Error inesperado durante la descarga»). Ahora se trabaja siempre sobre una copia privada con permiso de escritura, tanto para un Secret File como para `YTDLP_COOKIES_FILE`.
- **El análisis («Analizar») y los subtítulos ya mandan las cookies**, el proxy y el cliente de extracción. Antes iban sin nada de eso, así que desde el servidor YouTube respondía con el aviso anti-bot aunque hubiera cookies configuradas: el análisis era justo lo que fallaba.
- 6 pruebas nuevas: la copia escribible de las cookies, el cierre de yt-dlp sin `PermissionError`, y que el análisis salga con `cookiefile`.

### Cambiado
- `media.connection_opts()` centraliza cookies, proxy, tiempo de espera y cliente de extracción; lo usan igual el análisis, los subtítulos y las descargas.

## [2.1.0]

### Añadido
- **Generador de enlaces de WhatsApp** (`/link-whatsapp` y `/generador-enlace-whatsapp`): crea el enlace `wa.me` con el mensaje ya escrito, con plantillas de mensaje, opción de enlace sin número fijo, copia del enlace, apertura directa, compartición, botón HTML y **descarga del código QR**.
- Endpoint `POST /api/whatsapp/qr`, que dibuja el código QR (PNG) de un enlace de WhatsApp. Solo acepta enlaces de `wa.me` / `whatsapp.com`, así que no sirve como generador de QR genérico.
- Dependencia `segno` (Python puro, sin binarios) para dibujar el QR.
- 21 pruebas nuevas del generador: página, validación del enlace y código QR.
- El enlace de WhatsApp aparece ya en la navegación de todas las páginas y la tarjeta del directorio pasa de «Muy pronto» a «Disponible».

### Cambiado
- La versión pasa a 2.1.0.
- `static/common.js` gana la reutilización de `api()` y del manejo de errores desde el nuevo generador.

## [2.0.0]

### Añadido
- Suite de pruebas con pytest (seguridad, utilidades, trabajos, API) y CI en GitHub Actions.- Pruebas de extremo a extremo con ffmpeg (`tests/test_e2e_ffmpeg.py`): generan un vídeo y recorren el compresor y el recortador de clips de principio a fin.
- El CI también construye la imagen Docker y comprueba que el contenedor responde en `/api/health`.
- Configuración de lint con ruff (`pyproject.toml`) y `.editorconfig`.
- `SECURITY.md`, `CONTRIBUTING.md` y `.env.example`.
- Logging estructurado en todo el backend.
- Protección anti-SSRF en todas las URLs y en la descarga de miniaturas.
- `YTDLP_PROXY` (sacar las peticiones por un proxy) y `YTDLP_EXTRACTOR_ARGS` (elegir otro cliente de extracción) para cuando la plataforma bloquea la IP del servidor.
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
- El error del control anti-bot de YouTube ahora explica que hay que configurar cookies en el servidor (antes solo decía que hacía falta iniciar sesión).- Las páginas HTML usan rutas absolutas, metadatos descriptivos y roles/etiquetas ARIA (pestañas, zonas de arrastre, barras de progreso y avisos) con foco visible y respeto por `prefers-reduced-motion`.

### Arreglado
- El filtro anti-SSRF bloqueaba **cualquier dominio**: `host_is_public` cortaba con `return` el caso de IP literal y nunca llegaba a resolver el DNS (solo funcionaban las IPs escritas directamente). Ahora solo se rechazan las IPs internas/privadas reales. Añadidas pruebas de regresión con dominios.
- En la imagen Docker los Secret Files de Render no se podían leer (el usuario de la app no pertenecía al grupo `1000`), así que las cookies nunca se cargaban desde `/etc/secrets`. Ahora el usuario se añade a ese grupo y un fallo de permisos deja un aviso en los registros en lugar de silenciarse.
- Un ffmpeg colgado ya no retiene un hilo para siempre (timeout de proceso).
- Las descargas usan `socket_timeout` para no quedar colgadas.
- `resolve_output` ignora archivos incompletos (`.part`, `.ytdl`).
- El idioma de subtítulos se valida para que no actúe como comodín.
- Se evita devolver rutas internas del servidor en los mensajes de error.
- XSS en la lista de calidades: los datos del vídeo se insertan como texto y no como HTML.
- El sondeo de trabajos del frontend ya no se queda en marcha para siempre ni sigue consultando un trabajo antiguo tras restablecer (fuga en el compresor y en los clips).
