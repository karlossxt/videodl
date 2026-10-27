# Herramientas PDF

Cinco utilidades que procesan documentos **íntegramente en el navegador**:

| Página | Modo interno | Qué hace |
|---|---|---|
| `/unir-pdf` | `merge` | Combina varios PDF en uno solo, con el orden de documentos que elijas. |
| `/dividir-pdf` | `split` | Extrae páginas o rangos de un PDF, conservando el orden escrito. |
| `/imagenes-a-pdf` | `images` | Crea un PDF con imágenes JPG o PNG, una página por imagen. |
| `/pdf-a-jpg` | `jpg` | Renderiza las páginas de un PDF como JPG y las descarga en un ZIP. |
| `/comprimir-pdf` | `compress` | Rasteriza cada página a JPG y reconstruye el PDF para reducir su peso. |

Comparten plantilla, estilos y motor. No existe ningún endpoint de subida: el servidor
solo entrega el HTML, el CSS, el JavaScript y las bibliotecas locales. Los documentos
nunca viajan al servidor ni a un servicio externo.

## Arquitectura

```
videodl/
  pdf_pages.py            # textos, controles y SEO propios de cada modo
  catalog.py              # las cinco herramientas como "available"
  pages.py                # rutas /unir-pdf, /dividir-pdf, /imagenes-a-pdf, /pdf-a-jpg y /comprimir-pdf
  views.py                # PAGE_META, navegación con "PDF" y sitemap
static/
  pdf-tool.html           # plantilla única con marcadores <!-- ... -->
  pdf-core.js             # utilidades puras: validación, rangos, geometría, nombres y ZIP
  pdf-suite.js            # interfaz, PDF.js, pdf-lib, progreso, descargas y limpieza
  style.css               # estilos .pdf-* reutilizando componentes compartidos
  vendor/pdf/             # pdf-lib, PDF.js y sus recursos, con manifest.json
tests/
  test_pdf_tools.py       # contrato HTML, catálogo, integridad, ZIP y ejecución Node
  pdf-tools.test.js       # pruebas unitarias del núcleo con `node --test`
  e2e/pdf.spec.js         # flujo real en Chromium con Playwright
docs/
  herramientas-pdf.md     # este documento
```

`pdf_pages.py` solo rellena la plantilla. La cabecera, el pie, la navegación, las
herramientas relacionadas y el SEO técnico se generan con las mismas funciones que el
resto del sitio. Las cinco rutas están registradas en `views.PAGE_META` y en el sitemap.

### Flujo de unir PDF

1. Seleccionar o arrastrar dos o más PDF.
2. Validar tamaño, firma `%PDF-` y que pdf-lib pueda leerlos.
3. Ordenar los documentos con las flechas; la lista es el orden final.
4. Copiar las páginas con pdf-lib y descargar el PDF.
5. Mostrar tamaño real de entrada y salida. **Unir no comprime.**

### Flujo de dividir PDF

1. Seleccionar un PDF; se muestran hasta 24 páginas de vista previa.
2. Escribir rangos como `1-3, 5, 8-10` o usar los botones Todas/Impares/Pares/Primera/Última.
3. El orden de salida sigue el orden escrito. `3, 1` produce primero la página 3.
4. Copiar solo las páginas seleccionadas con pdf-lib y descargar el PDF.
5. Si el PDF está cifrado, se muestra un error y no se intenta descifrar.

### Flujo de imágenes a PDF

1. Seleccionar o arrastrar JPG/PNG, hasta 20 imágenes y 75 MB en total.
2. Validar por bytes y decodificar con la API de imagen del navegador.
3. Ordenar las imágenes; cada una será una página.
4. Elegir A4 vertical, A4 horizontal o el tamaño de cada imagen.
5. Incrustar las imágenes con pdf-lib. Los JPG se incrustan como JPG y los PNG como
   PNG; no se recodifican a JPG. La transparencia del PNG se conserva.

### Flujo de PDF a JPG

1. Seleccionar un PDF de hasta 80 páginas.
2. Elegir calidad JPG y escala de renderizado (1×, 1,5× o 2×).
3. Renderizar cada página con PDF.js sobre un canvas blanco.
4. Si hay una página, descargar JPG; si hay varias, descargar un ZIP con un JPG por página.
5. El ZIP se construye en el navegador con método *store* (sin compresión adicional),
   porque los JPG ya están comprimidos. No se añade JSZip.

### Flujo de comprimir PDF

1. Seleccionar un PDF de hasta 80 páginas y 25 MB.
2. Elegir la calidad JPG (40–95 %) y la escala de renderizado (1×, 1,5× o 2×).
3. Renderizar cada página con PDF.js y codificarla como JPG.
4. Reconstruir el PDF con pdf-lib: una página del tamaño original por cada imagen.
5. Mostrar el tamaño de entrada y de salida. Si el resultado pesa más, se avisa y se
   recomienda bajar la calidad o conservar el original.

## Bibliotecas locales

| Biblioteca | Versión | Licencia | Uso |
|---|---|---|---|
| pdf-lib | 1.17.1 | MIT | Leer, copiar, unir y reconstruir PDF; incrustar JPG/PNG. |
| PDF.js | 6.4.299 | Apache-2.0 | Renderizar páginas para miniaturas, JPG y compresión. |

Los archivos están en `static/vendor/pdf/` y se cargan desde el mismo origen. No hay
CDN, `unpkg`, `jsdelivr` ni peticiones a terceros. `manifest.json` guarda la versión,
la licencia, la integridad del paquete npm y el SHA-256 de cada archivo. Una prueba de
Python verifica que el manifest coincide con el contenido real.

PDF.js usa un worker de módulo del mismo origen (`/vendor/pdf/pdf.worker.min.mjs`),
fuentes estándar, CMaps, perfiles ICC y decodificadores WASM locales. La CSP incluye
`worker-src 'self'` y mantiene `connect-src 'self'`.

## Límites

| Límite | Valor | Dónde se aplica |
|---|---|---|
| Tamaño por PDF o imagen | 25 MB | `MAX_FILE_BYTES` en `pdf-core.js` y `PDF_MAX_MB` en `pdf_pages.py` |
| Tamaño total de la selección | 75 MB | `MAX_TOTAL_BYTES` / `PDF_MAX_TOTAL_MB` |
| Documentos para unir | 10 | `MAX_FILES` / `PDF_MAX_FILES` |
| Imágenes para crear un PDF | 20 | `MAX_IMAGES` / `PDF_MAX_IMAGES` |
| Páginas combinadas al unir o dividir | 300 | `MAX_PDF_PAGES` / `PDF_MAX_PAGES` |
| Páginas por conversión a JPG o compresión | 80 | `MAX_RENDER_PAGES` / `PDF_MAX_RENDER_PAGES` |
| Píxeles por imagen de entrada | 64 000 000 | `MAX_IMAGE_PIXELS` / `PDF_MAX_IMAGE_PIXELS` |
| Píxeles por página renderizada | 40 000 000 | `MAX_OUTPUT_PIXELS` |
| Lado máximo del render | 8192 px | `MAX_OUTPUT_SIDE` |

Los límites de tamaño y página se comprueban antes de procesar. Si una página es muy
grande para JPG o para comprimir, `clampRenderScale` reduce la escala automáticamente y la
interfaz lo indica. En el modo «Tamaño de cada imagen», una imagen muy alargada se escala
para que la página no supere los 14 400 puntos que admiten los visores PDF. Los límites son
deliberadamente conservadores para evitar que una pestaña se quede sin memoria en
móviles.

## Manejo de errores

- **PDF corrupto o sin firma**: se rechaza antes de procesar con un mensaje que distingue
  entre contenido no PDF y documento dañado.
- **PDF protegido con contraseña**: pdf-lib y PDF.js no descifran. Se detecta el error y
  se explica que hay que quitar la protección con la aplicación original.
- **PDF sin páginas**: se rechaza con un mensaje claro.
- **Más de 80 páginas al comprimir o convertir a JPG**: se bloquea y se sugiere dividir el
  documento; el resto de modos admiten hasta 300 páginas.
- **Imagen no admitida**: WebP, GIF, AVIF, SVG, HEIC y archivos corruptos se rechazan;
  solo se aceptan JPG y PNG.
- **Memoria**: si el navegador falla al renderizar, se muestra un error y se liberan los
  canvas y las URL temporales conocidas.
- **Límites**: se avisa al añadir archivos grandes y se bloquea la operación si se supera
  el total.

## Privacidad y limpieza

- No hay `fetch`, `XMLHttpRequest`, `FormData` ni rutas `/api/` en el código de la suite.
- Los archivos se leen con `File.arrayBuffer()` y viven en memoria mientras dura la
  operación.
- Se revocan las URL `blob:` de miniaturas y resultados al quitar un archivo, cambiar de
  selección o cerrar la página (`pagehide`).
- Se vacían los canvas (`width = 0`, `height = 0`) después de cada miniatura, página JPG
  y resultado.
- El servidor no recibe el contenido de los archivos, solo sirve assets estáticos.

## Compatibilidad de navegadores

| Navegador | Unir/dividir | Imágenes a PDF | PDF a JPG | Comprimir PDF | Notas |
|---|---|---|---|---|---|
| Chrome / Edge actuales | Sí | Sí | Sí | Sí | Probado con Chromium en Playwright. |
| Firefox actual | Sí | Sí | Sí | Sí | Módulos, worker module, canvas y WASM estándar. |
| Safari actual (macOS/iOS) | Sí | Sí | Sí | Sí | Safari moderno; la memoria disponible es el límite práctico. |
| Navegadores sin módulos ES | No | No | No | No | La suite usa `type="module"` y `import()`. |
| Navegadores sin canvas 2D | Sí para unir/dividir | No | No | No | Sin canvas no se pueden generar miniaturas, JPG ni compresión. |

La suite usa `File`, `Blob`, `URL.createObjectURL`, `TextEncoder`, canvas 2D, módulos
JavaScript y —en el caso de PDF.js— worker module y WebAssembly. No se usa `eval`
(`isEvalSupported: false`).

## Limitaciones conocidas

- **No es un editor de PDF**: no añade texto, marcas de agua, numeración ni formularios.
- **No hace OCR**: un PDF escaneado sigue siendo imágenes; no se convierte en texto
  seleccionable.
- **Unir no comprime**: el resultado puede pesar igual o más que la suma de las partes.
- **Extraer no recomprime**: el peso baja por tener menos páginas, no por compresión.
- **Comprimir rasteriza**: el PDF resultante contiene una imagen JPG por página; se pierden
  texto seleccionable, enlaces, formularios, marcadores y metadatos. Un PDF que ya estaba
  optimizado puede pesar igual o más después de comprimirlo.
- **PDF complejos**: pdf-lib copia páginas, pero marcadores, formularios interactivos,
  capas, adjuntos, firmas digitales y algunas acciones pueden perderse o dejar de
  funcionar. PDF.js puede renderizar de forma algo distinta a un visor de escritorio.
- **Imágenes a PDF**: no conserva metadatos EXIF y no promete un tamaño físico exacto en
  el modo "Tamaño de cada imagen" (se usa 96 ppp como equivalencia). La orientación EXIF
  puede verse distinta a la del carrete del móvil; revisa las fotos verticales.
- **JPG**: no conserva transparencia, enlaces, campos de formulario ni texto
  seleccionable. El fondo se pinta en blanco antes de codificar.
- **ZIP**: se guarda sin compresión adicional; algunos visores muestran el método
  "Store". Es válido y se abre con las herramientas habituales.
- **Memoria**: documentos muy grandes o muchas páginas pueden agotar la memoria del
  navegador aunque estén dentro de los límites. En ese caso conviene dividir el trabajo.
- **Nombres**: se sanean caracteres no válidos y se limitan a 80 caracteres; el nombre
  final puede no coincidir exactamente con el original.

## Pruebas

### Unitarias del núcleo

```bash
node --test tests/pdf-tools.test.js
```

Cubren:

- detección de la firma PDF, incluso con bytes previos;
- archivos vacíos, demasiado grandes, corruptos y con MIME genérico;
- mensajes para PDF cifrado, corrupto y errores desconocidos;
- rangos, orden, repeticiones, rangos invertidos y límites;
- movimiento de elementos sin mutar el array original;
- geometría de A4, tamaño de imagen, fit y escala máxima de render;
- nombres de salida seguros;
- CRC32 y estructura del ZIP con nombres UTF-8.

### Pruebas de integración Python

```bash
pytest tests/test_pdf_tools.py
```

Comprueban:

- las cinco rutas, su modo, navegación, scripts, controles y SEO;
- el catálogo, las herramientas destacadas y el sitemap;
- la ausencia de formularios, `/api/`, `fetch`, `XMLHttpRequest` y `FormData`;
- la sincronización de límites Python/JavaScript;
- la integridad SHA-256 de los 203 archivos vendorizados (sin contar `manifest.json`);
- que el ZIP generado por el núcleo JavaScript se abre con `zipfile` de Python;
- la presencia de estilos responsive.

### Pruebas E2E con Playwright

La suite `tests/e2e/pdf.spec.js` arranca la aplicación con uvicorn y abre Chromium con
Playwright. Comprueba, con descargas reales:

- que las cinco páginas cargan sin errores de consola y con las bibliotecas locales listas;
- unir dos PDF y verificar el número y el orden de las páginas del archivo descargado;
- dividir con `3, 1` y comprobar que el resultado conserva ese orden;
- crear un PDF desde PNG y JPG y verificar que tiene una página por imagen;
- convertir a JPG y validar la firma y el contenido del ZIP descargado;
- comprimir un PDF y comprobar que el resultado se abre y mantiene sus páginas;
- que durante el procesamiento no hay peticiones POST, externas ni a `/api/`.

Se ejecuta en CI con `npm ci`, `npx playwright install --with-deps chromium` y
`npm run test:e2e`. La configuración de `playwright.config.js` levanta uvicorn en el puerto
8010 y reutiliza un servidor local si ya está en marcha.

## Verificación en CI

El workflow `.github/workflows/ci.yml` ejecuta:

```bash
ruff check .
node --test tests/image-tools.test.js
node --test tests/pdf-tools.test.js
pytest
npm ci
npx playwright install --with-deps chromium
npm run test:e2e
```

Además construye la imagen Docker y comprueba `/api/health`. La suite PDF no añade
dependencias Python ni servicios externos en tiempo de ejecución; Playwright solo se usa
en desarrollo y CI.
