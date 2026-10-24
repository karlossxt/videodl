# Herramientas de imagen

Tres utilidades que procesan imágenes **íntegramente en el navegador**:

| Página | Modo interno | Qué hace |
|---|---|---|
| `/comprimir-imagen` | `compress` | Reduce el peso con calidad ajustable y permite mantener el formato o cambiar a JPG, PNG o WebP. |
| `/convertir-imagen` | `convert` | Cambia entre JPG, PNG y WebP con control de calidad y de transparencia. |
| `/redimensionar-imagen` | `resize` | Cambia el ancho y el alto en píxeles o porcentaje, con proporción bloqueable. |

Las tres comparten plantilla, motor y hoja de estilos. No existe ningún endpoint de
subida: la imagen nunca viaja al servidor ni a un servicio externo.

## Arquitectura

```
videodl/
  image_pages.py          # textos, controles y SEO propios de cada modo
  catalog.py              # las tres herramientas como «available»
  pages.py                # rutas HTML /comprimir-imagen, /convertir-imagen, /redimensionar-imagen
  views.py                # PAGE_META, navegación con «Imágenes» y sitemap
static/
  imagen-tool.html        # plantilla única con marcadores <!-- ... -->
  image-tools.js          # motor puro: validación, sniffing, medidas, canvas y limpieza
  imagenes.js             # interfaz: estado, eventos, vistas previas y descargas
  style.css               # estilos .image-*, checkerboard, avisos y responsive
tests/
  test_image_tools.py     # contrato HTML, catálogo, assets y ejecución de las pruebas Node
  image-tools.test.js     # pruebas unitarias del motor con `node --test`
```

`image_pages.py` solo rellena la plantilla. La cabecera, el pie, la navegación, las
herramientas relacionadas y el SEO técnico se generan con las mismas funciones que el
resto del sitio. Las tres rutas están registradas en `views.PAGE_META` y en el sitemap.

### Flujo de procesamiento

1. **Selección**: `<input type="file">` o arrastrar y soltar sobre la zona de subida.
2. **Validación real**:
   - tamaño vacío o superior a 25 MB;
   - tipo declarado, extensión y **firma de bytes** (el contenido manda sobre el nombre);
   - rechazo explícito de GIF, BMP, SVG, AVIF, HEIC/HEIF y archivos sin firma conocida;
   - comprobación de que el archivo se puede decodificar como imagen.
3. **Carga**: `URL.createObjectURL` y decodificación con `Image.decode()` cuando está
   disponible.
4. **Límites geométricos**: 16 384 px por lado y 64 megapíxeles. Si se superan, se avisa
   antes de dibujar.
5. **Transparencia**: se escanea el canal alfa para avisar al convertir a JPG y ofrecer
   un color de fondo opaco (blanco por defecto).
6. **Procesado**: un `<canvas>` intermedio dibuja la imagen con las dimensiones de salida
   y `canvas.toBlob()` genera el archivo final.
7. **Resultado**: vista previa del «antes» y el «después», tamaño original, tamaño final,
   porcentaje real de reducción (también si es negativo) y descarga.
8. **Limpieza**: se revocan las URL temporales al cambiar de archivo, al reiniciar el
   flujo o al cerrar la página (`pagehide`), y se vacía el canvas (`width = 0`).

## Límites

| Límite | Valor | Dónde se aplica |
|---|---|---|
| Tamaño de archivo | 25 MB | `MAX_FILE_BYTES` en `image-tools.js` y `IMAGE_MAX_MB` en `image_pages.py` |
| Lado máximo | 16 384 px | Entrada y salida |
| Píxeles máximos | 64 000 000 | Entrada y salida |
| Escala por porcentaje | 1 %–400 % | Modo porcentaje |
| Formatos aceptados | JPG/JPEG/JFIF, PNG, WebP | Validación por firma |
| Formatos de salida | JPG, PNG, WebP | WebP solo si el navegador lo codifica |

Una prueba de Python comprueba que el límite de 25 MB está sincronizado entre el motor
JavaScript y el texto de las páginas.

## Formatos y transparencia

| Formato | Compresión | Canal alfa | Notas |
|---|---|---|---|
| JPG | Con pérdida | No | Se rellena el fondo (color elegible en comprimir/convertir; blanco al redimensionar). |
| PNG | Sin pérdida | Sí | El deslizador de calidad se desactiva: no cambia el resultado. |
| WebP | Con o sin pérdida | Sí | La opción se desactiva si `canvas.toDataURL("image/webp")` no devuelve WebP. |

- Al comprimir se puede mantener el formato original o elegir otro. Mantener el formato
  permite que un PNG siga siendo PNG; cambiar a JPG o WebP es lo que suele reducir su peso.
- La detección de transparencia escanea la imagen completa hasta 4 MP. Por encima de ese
  tamaño se muestrea con un lado máximo de 1024 px, de modo que una zona transparente muy
  pequeña podría no detectarse; aun así el JPG se genera siempre opaco.
- Un JPG **nunca** conserva transparencia real: el fondo se pinta antes de codificar.

## Comprimir no siempre reduce

La interfaz lo indica antes y después de procesar. Si la imagen ya estaba optimizada, el
archivo recodificado puede pesar igual o más. El porcentaje que se muestra es el real
(`(original - final) / original`), con signo negativo cuando el resultado crece. El archivo
original del usuario nunca se modifica.

## Compatibilidad de navegadores

| Navegador | JPG/PNG | WebP de salida | Notas |
|---|---|---|---|
| Chrome / Edge actuales | Sí | Sí | Probado con Chrome headless en la matriz E2E. |
| Firefox actual | Sí | Sí | Canvas 2D y `toBlob` estándar. |
| Safari actual (macOS/iOS) | Sí | Sí | Safari moderno codifica WebP; si no, la opción se desactiva. |
| Navegadores móviles actuales | Sí | Según motor | Comparten el mismo canvas; la memoria disponible es el límite práctico. |
| Navegadores sin canvas 2D o sin `toBlob` | No | No | No se comprueba al cargar: al procesar se muestra un error y no se genera archivo. |

Requisitos del navegador: `File`, `Blob`, `URL.createObjectURL`, `<canvas>` 2D,
`canvas.toBlob` y `Image`. No se usa WebAssembly, workers ni ninguna dependencia externa.
La CSP incluye `blob:` en `img-src` para las vistas previas y limita `connect-src` a
`'self'`, de modo que la página no puede enviar la imagen a un tercero.

## Pruebas

### Unitarias del motor

```bash
node --test tests/image-tools.test.js
```

Cubren:

- detección por bytes de JPG, PNG, WebP, GIF, AVIF, BMP y SVG;
- MIME genérico o extensión engañosa;
- archivos vacíos, demasiado grandes, corruptos y no compatibles;
- porcentaje de reducción positivo, cero y negativo;
- conversión de porcentajes, proporción y redondeo;
- límites por lado y por megapíxeles;
- normalización de calidad y nombres de descarga seguros (incluida una ruta `../`).

### Páginas y assets

```bash
.venv/Scripts/python.exe -m pytest tests/test_image_tools.py tests/test_site.py
```

Comprueban estructura accesible, canonical/Open Graph, navegación compartida, scripts
compartidos, ausencia de `<form>`, de `/api/` y de código de subida (`fetch`,
`XMLHttpRequest`, `FormData`), libertad de las URL temporales y presencia de estilos
responsive.

### Extremo a extremo en Chrome

Se ejecutó una batería de **91 comprobaciones** con Chrome headless y el protocolo CDP
sobre `http://127.0.0.1:8765`, con estos casos:

| Caso | Resultado comprobado |
|---|---|
| JPG válido 1200 × 800 | Vista previa, compresión al 60 %, tamaños, porcentaje, descarga `.jpg` con firma válida. |
| PNG transparente 320 × 240 → JPG | Aviso visible, selector de fondo, esquina rellenada con el color elegido, descarga `.jpg`. |
| PNG transparente → WebP | WebP real, dimensiones conservadas, descarga `.webp`. |
| PNG transparente → PNG | Canal alfa intacto (`alpha = 0` en la esquina), descarga `.png`. |
| JPG → PNG | PNG real, deslizador de calidad desactivado. |
| PNG corrupto | Error «dañado», sin imagen a medio cargar. |
| JPG falso (texto renombrado) | Error de imagen no válida. |
| GIF animado | Rechazo con mensaje que nombra GIF. |
| SVG | Rechazo con mensaje que nombra SVG. |
| AVIF | Rechazo con mensaje que nombra AVIF. |
| Archivo vacío | Error de archivo vacío. |
| PNG 17 000 × 1 | Error de límite de dimensiones. |
| PNG 16 × 16 | Se procesa correctamente. |
| Redimensionar 50 % | 1200 × 800 → 600 × 400. |
| Redimensionar por píxeles | 300 × 200 y proporción automática del alto. |
| Proporción desbloqueada | 500 × 100 exactos (deformación visible). |
| PNG transparente al 50 % | 160 × 120, alfa conservado. |
| WebP de entrada | Aceptado, conserva formato al redimensionar y al comprimir. |
| Navegador simulado sin WebP | Opción desactivada, aviso mostrado y JPG seleccionado como alternativa. |
| Red | Ninguna petición `POST` ni ruta `/api/`; sin nodos `<canvas>` persistentes. |

La simulación sin WebP se hizo sustituyendo `HTMLCanvasElement.prototype.toDataURL` para
que devolviera PNG cuando se solicitaba WebP. La comprobación de red se apoyó en
`performance.getEntriesByType("resource")` y en los eventos `Network.*` de CDP. Las
descargas se validaron por extensión y firma de bytes, no solo por el nombre.

## Limitaciones conocidas

- **La compresión no garantiza un archivo más pequeño**; el porcentaje puede ser negativo.
- **WebP depende del navegador**. Si no puede codificarlo, la opción se desactiva; no se
  genera un PNG disfrazado de `.webp`.
- **Metadatos EXIF**: no se copian al resultado (cámara, fecha, GPS). La orientación EXIF
  se aplica al decodificar en navegadores actuales, pero no se conserva el bloque EXIF.
- **Memoria**: una imagen de decenas de megapíxeles puede agotar la memoria de un móvil
  aunque esté dentro del límite. Conviene reducir primero una copia más pequeña.
- **Ampliar no crea detalle**: el redimensionado interpola los píxeles existentes. Los
  presets en píxeles nunca amplían una imagen más pequeña.
- **Detección de transparencia muestreada** en imágenes de más de 4 MP (lado máximo de
  muestreo: 1024 px). Puede no ver una zona alfa diminuta; el JPG seguirá siendo opaco.
- **Una imagen por vez**, para controlar el uso de memoria; no hay procesamiento por lotes.
- **Sin animaciones**: GIF, AVIF y HEIC se rechazan; tampoco se aceptan SVG ni BMP.
- **Calidad de reescalado** dependiente del motor del navegador; no se aplica un filtro
  propio.
- **Sin API pública** para imágenes: es una decisión de privacidad, no una carencia.

## Privacidad

No hay `fetch`, `XMLHttpRequest` ni `FormData` en `image-tools.js` ni en `imagenes.js`, y
la plantilla no contiene formularios ni rutas `/api/`. Las pruebas de Python fallan si
aparece cualquiera de esos patrones. La imagen se decodifica desde una URL `blob:` local,
se procesa en un canvas y se descarga con un enlace `blob:`; el servidor solo entrega el
HTML, el CSS y el JavaScript.
