"""Páginas de la suite PDF.

Las cinco utilidades comparten una sola plantilla y un único motor en el
navegador. Este módulo aporta el texto, los límites y los controles propios de
cada modo; la cabecera, el pie, las herramientas relacionadas y el SEO técnico
salen de ``views.py``.
"""

from __future__ import annotations

from . import i18n, views
from .paths import STATIC_DIR

# Deben coincidir con static/pdf-core.js.
PDF_MAX_MB = 25
PDF_MAX_TOTAL_MB = 75
PDF_MAX_FILES = 10
PDF_MAX_IMAGES = 20
PDF_MAX_PAGES = 300
PDF_MAX_RENDER_PAGES = 80
PDF_MAX_IMAGE_PIXELS = 64_000_000


_MERGE_CONTROLS = """<div class="pdf-options">
  <p class="pdf-note"><strong>El orden de la lista será el orden del PDF final.</strong>
  Usa las flechas de cada documento para subirlo o bajarlo. Unir no es comprimir:
  el resultado puede pesar parecido o incluso algo más que la suma de las partes.</p>
</div>"""

_SPLIT_CONTROLS = f"""<div class="pdf-options">
  <label class="option-field" for="page-ranges">
    <span>Páginas o rangos</span>
    <input type="text" id="page-ranges" inputmode="text" autocomplete="off"
      placeholder="1-3, 5, 8-10" aria-describedby="range-help" />
  </label>
  <div class="preset-row" id="range-presets" role="group" aria-label="Selecciones rápidas de páginas">
    <button type="button" class="soft-btn" data-range="all">Todas</button>
    <button type="button" class="soft-btn" data-range="odd">Impares</button>
    <button type="button" class="soft-btn" data-range="even">Pares</button>
    <button type="button" class="soft-btn" data-range="first">Primera</button>
    <button type="button" class="soft-btn" data-range="last">Última</button>
  </div>
  <p class="field-hint" id="range-help">Ejemplo: <code>1-3, 5, 8-10</code>. El orden de salida sigue el
  orden escrito, así que <code>3, 1</code> produce primero la página 3 y después la 1. Puedes
  repetir una página si la necesitas dos veces. Máximo {PDF_MAX_PAGES} páginas de salida.</p>
  <p id="range-summary" class="pdf-note">Selecciona un PDF para ver sus páginas.</p>
</div>"""

_IMAGES_CONTROLS = f"""<div class="pdf-options">
  <label class="option-field" for="page-size">
    <span>Tamaño de página</span>
    <select id="page-size">
      <option value="a4" selected>A4 vertical (ajustar imagen)</option>
      <option value="a4-landscape">A4 horizontal (ajustar imagen)</option>
      <option value="image">Tamaño de cada imagen</option>
    </select>
  </label>
  <p class="field-hint">A4 coloca cada imagen centrada con un margen de 24 puntos. La opción
  «Tamaño de cada imagen» usa una equivalencia de 96 píxeles por pulgada; el tamaño físico
  puede variar según la resolución con la que se creó la imagen. Se admiten JPG y PNG; la
  transparencia del PNG se conserva en el PDF. Máximo {PDF_MAX_IMAGE_PIXELS // 1_000_000} MP
  por imagen.</p>
  <p class="pdf-note">Puedes reordenar las imágenes con las flechas antes de crear el documento.
  Máximo {PDF_MAX_IMAGES} imágenes y {PDF_MAX_TOTAL_MB} MB en total por operación.</p>
</div>"""

_COMPRESS_CONTROLS = f"""<div class="pdf-options">
  <label class="option-field" for="jpg-quality">
    <span>Calidad JPG <output id="jpg-quality-value" for="jpg-quality">75 %</output></span>
    <input type="range" id="jpg-quality" min="40" max="95" step="5" value="75" />
  </label>
  <label class="option-field" for="render-scale">
    <span>Resolución de renderizado</span>
    <select id="render-scale">
      <option value="1">1&times; (72 ppp)</option>
      <option value="1.5" selected>1,5&times; (108 ppp)</option>
      <option value="2">2&times; (144 ppp)</option>
    </select>
  </label>
  <p class="field-hint">Para reducir el peso, cada página se convierte en una imagen JPG y se
  reconstruye el PDF. Una calidad y una resolución más bajas dan un archivo más pequeño, pero
  también menos nitidez. Se procesan como máximo {PDF_MAX_RENDER_PAGES} páginas por operación.</p>
  <p class="pdf-note">Esta compresión <strong>rasteriza</strong> el documento: se pierden el texto
  seleccionable, los enlaces, los formularios y los metadatos. Si el PDF ya venía muy comprimido,
  el resultado puede pesar igual o más; en ese caso prueba con una calidad menor.</p>
</div>"""

_JPG_CONTROLS = f"""<div class="pdf-options">
  <label class="option-field" for="jpg-quality">
    <span>Calidad JPG <output id="jpg-quality-value" for="jpg-quality">85 %</output></span>
    <input type="range" id="jpg-quality" min="60" max="95" step="5" value="85" />
  </label>
  <label class="option-field" for="render-scale">
    <span>Resolución de renderizado</span>
    <select id="render-scale">
      <option value="1">1&times; (72 ppp)</option>
      <option value="1.5" selected>1,5&times; (108 ppp)</option>
      <option value="2">2&times; (144 ppp)</option>
    </select>
  </label>
  <p class="field-hint">Una escala mayor produce imágenes más nítidas y pesadas. Si una página
  supera el máximo de píxeles, la herramienta reduce la escala automáticamente y lo indica.
  Se procesan como máximo {PDF_MAX_RENDER_PAGES} páginas por operación para no agotar la
  memoria del navegador.</p>
  <p class="pdf-note">Si el PDF tiene varias páginas, el resultado se descarga como un ZIP con
  un JPG por página. El fondo se pinta en blanco antes de codificar, porque JPG no admite
  transparencia. Esta conversión no aplica OCR ni reconstruye texto editable.</p>
</div>"""


PDF_TOOL_CONTENT: dict[str, dict[str, str]] = {
    "unir-pdf": {
        "mode": "merge",
        "step_one_title": "Elige los PDF",
        "hero_title": "Unir PDF en el orden que quieras",
        "hero_sub": (
            "Combina varios documentos en un solo archivo. Arrastra, ordena y descarga: "
            "todo se procesa en tu navegador y ningún PDF se envía a un servidor."
        ),
        "hero_badge": "Procesamiento local · orden editable · sin registro",
        "drop_aria": "Elegir o arrastrar varios archivos PDF para unirlos",
        "drop_icon": "&#128196;",
        "drop_title": "Arrastra tus PDF aquí o <span class=\"accent\">búscalos en tu equipo</span>",
        "drop_sub": (
            f"PDF hasta {PDF_MAX_MB} MB cada uno · máximo {PDF_MAX_FILES} documentos "
            f"y {PDF_MAX_TOTAL_MB} MB en total"
        ),
        "accept": "application/pdf,.pdf",
        "multiple": "multiple",
        "files_title": "Documentos que se van a unir",
        "controls": _MERGE_CONTROLS,
        "action_label": "Unir PDF",
        "action_hint": "Añade al menos dos PDF. El orden de la lista será el orden final.",
        "seo": f"""<h2>Cómo unir varios PDF en uno</h2>
<ol class="steps">
  <li><strong>Añade los documentos</strong> con el selector o arrastrándolos a la zona de subida.</li>
  <li><strong>Revisa el orden</strong> y usa las flechas para mover cada documento hacia arriba o hacia abajo.</li>
  <li><strong>Pulsa «Unir PDF»</strong> y espera a que termine el procesamiento local.</li>
  <li><strong>Descarga el resultado</strong> y comprueba que las páginas aparecen en el orden previsto.</li>
</ol>

<h2>Unir no es comprimir</h2>
<p>Esta herramienta copia las páginas de cada documento en un PDF nuevo. No vuelve a comprimir
las imágenes ni elimina fuentes, formularios o datos internos para reducir el peso. Por eso el
archivo final puede pesar prácticamente lo mismo que la suma de los originales, o incluso algo
más por la estructura añadida. Si necesitas reducir el tamaño, tendrás que usar un compresor
específico; aquí no se promete una reducción.</p>

<h2>Qué se conserva y qué puede cambiar</h2>
<p>Se conservan las páginas y su contenido visible, incluidas las imágenes y la mayoría de las
anotaciones que forman parte de la página. Sin embargo, los PDF son formatos complejos:
marcadores, formularios interactivos, capas, adjuntos, firmas digitales y algunas acciones
pueden no conservarse o dejar de funcionar al reconstruir el documento. Revisa siempre el
resultado antes de usarlo en un trámite importante.</p>

<h2>Privacidad, memoria y límites</h2>
<p>Los archivos se leen con la API <code>File</code> del navegador y se procesan con pdf-lib en
memoria. No hay peticiones de subida, cuentas ni servicios externos. El límite es de
{PDF_MAX_MB} MB por PDF, {PDF_MAX_TOTAL_MB} MB en total, {PDF_MAX_FILES} documentos y
{PDF_MAX_PAGES} páginas combinadas. En móviles con poca memoria conviene unir pocos documentos
grandes a la vez.</p>

<h2>PDF protegidos o dañados</h2>
<p>Si un documento está protegido con contraseña, la herramienta lo detecta y muestra un error
claro: no intenta descifrarlo. Tampoco repara archivos corruptos. Quita la protección con la
aplicación original o vuelve a descargar el PDF antes de unirlo.</p>

<h2>Compatibilidad de navegadores</h2>
<p>Funciona en versiones actuales de Chrome, Edge, Firefox y Safari con módulos JavaScript,
<code>File</code>, <code>Blob</code> y canvas. El procesamiento usa pdf-lib y PDF.js servidos
desde este mismo sitio; no se cargan bibliotecas desde CDN. Un navegador muy antiguo sin
soporte de módulos no podrá ejecutar la herramienta.</p>

<h2>Preguntas frecuentes</h2>
<details class="faq">
  <summary>¿Se suben los PDF a Fastools o a un tercero?</summary>
  <p>No. La unión se hace en tu navegador. El sitio solo entrega el HTML, el CSS y las
  bibliotecas; el contenido de tus documentos no viaja al servidor.</p>
</details>
<details class="faq">
  <summary>¿Puedo cambiar el orden después de añadirlos?</summary>
  <p>Sí. Cada documento tiene botones para subirlo o bajarlo. También puedes quitarlo y volver
  a añadirlo en la posición que quieras.</p>
</details>
<details class="faq">
  <summary>¿El PDF resultante pesa menos?</summary>
  <p>No necesariamente. Unir no comprime: puede pesar igual o más. La página muestra el tamaño
  real de entrada y salida para que lo compruebes antes de descargar.</p>
</details>
<details class="faq">
  <summary>¿Se conservan los formularios y los marcadores?</summary>
  <p>No se garantiza. pdf-lib copia las páginas, pero los formularios interactivos, marcadores,
  firmas y adjuntos pueden perderse. Para documentos complejos, revisa el archivo final.</p>
</details>
<details class="faq">
  <summary>¿Puedo unir un PDF protegido con contraseña?</summary>
  <p>No. La herramienta no descifra documentos. Debes quitar la contraseña primero desde la
  aplicación con la que lo creaste.</p>
</details>""",
    },
    "dividir-pdf": {
        "mode": "split",
        "step_one_title": "Elige el PDF",
        "hero_title": "Dividir un PDF y extraer páginas o rangos",
        "hero_sub": (
            "Selecciona un documento, escribe las páginas que quieres conservar y descarga un "
            "PDF nuevo. La vista previa y el procesamiento ocurren en tu navegador."
        ),
        "hero_badge": "Rangos flexibles · orden de salida editable · sin subidas",
        "drop_aria": "Elegir o arrastrar un archivo PDF para dividirlo",
        "drop_icon": "&#9986;",
        "drop_title": "Arrastra el PDF aquí o <span class=\"accent\">búscalo en tu equipo</span>",
        "drop_sub": f"Un PDF de hasta {PDF_MAX_MB} MB y {PDF_MAX_PAGES} páginas",
        "accept": "application/pdf,.pdf",
        "multiple": "",
        "files_title": "Documento de origen",
        "controls": _SPLIT_CONTROLS,
        "action_label": "Extraer páginas",
        "action_hint": "Escribe las páginas o rangos que quieres extraer.",
        "seo": f"""<h2>Cómo extraer páginas de un PDF</h2>
<ol class="steps">
  <li><strong>Añade el PDF</strong> y espera a que aparezca la vista previa de sus páginas.</li>
  <li><strong>Escribe los rangos</strong>, por ejemplo <code>1-3, 5, 8-10</code>, o usa los botones rápidos.</li>
  <li><strong>Pulsa «Extraer páginas»</strong> para crear un PDF nuevo con la selección.</li>
  <li><strong>Descarga el resultado</strong>. El documento original permanece intacto en tu equipo.</li>
</ol>

<h2>Orden, repetición y límites de los rangos</h2>
<p>El orden de salida sigue el orden en el que escribes los rangos. <code>3, 1</code> genera
primero la página 3 y después la página 1; <code>1-3</code> genera 1, 2 y 3. Puedes repetir una
página si la necesitas dos veces. Los números deben estar entre 1 y el total de páginas del
documento. Se admiten hasta {PDF_MAX_PAGES} páginas de salida por operación.</p>

<h2>Vista previa y páginas grandes</h2>
<p>La vista previa muestra las primeras páginas para que identifiques el documento, pero los
rangos funcionan con todas las páginas aunque no se muestren. En documentos de cientos de
páginas, dibujar cada miniatura consumiría demasiada memoria; por eso la vista previa es
limitada y se indica cuántas páginas se están mostrando.</p>

<h2>Qué se conserva y qué puede cambiar</h2>
<p>Se copian las páginas seleccionadas con su contenido visible. Los marcadores, formularios
interactivos, capas, adjuntos, firmas digitales y acciones del documento original pueden no
conservarse. Esta herramienta no hace OCR: si el PDF es un escaneo, las páginas siguen siendo
imágenes y el texto no se vuelve seleccionable.</p>

<h2>Privacidad, memoria y archivos protegidos</h2>
<p>El PDF se lee y se reconstruye en memoria con pdf-lib. No se envía a un servidor ni se
consulta un servicio externo. El límite es de {PDF_MAX_MB} MB y {PDF_MAX_PAGES} páginas. Si el
documento está cifrado o protegido con contraseña, se muestra un error y no se intenta
descifrar. Los PDF dañados también se rechazan con un mensaje claro.</p>

<h2>Compatibilidad de navegadores</h2>
<p>Necesitas un navegador actual con módulos JavaScript, <code>File</code>, <code>Blob</code> y
canvas: Chrome, Edge, Firefox o Safari recientes. PDF.js renderiza las miniaturas y pdf-lib
genera el archivo final, ambos servidos desde el propio sitio. No se usan CDN ni servicios de
conversión externos.</p>

<h2>Preguntas frecuentes</h2>
<details class="faq">
  <summary>¿Puedo extraer una sola página?</summary>
  <p>Sí. Escribe su número, por ejemplo <code>7</code>, y se generará un PDF de una página.</p>
</details>
<details class="faq">
  <summary>¿Puedo cambiar el orden de las páginas?</summary>
  <p>Sí. Escribe los números en el orden deseado: <code>5, 1, 3</code>. También puedes repetir
  una página si la necesitas más de una vez.</p>
</details>
<details class="faq">
  <summary>¿El PDF resultante es más pequeño?</summary>
  <p>No se garantiza. Al extraer páginas suele bajar el peso porque hay menos contenido, pero
  no se recomprimen las imágenes ni las fuentes. No es una herramienta de compresión.</p>
</details>
<details class="faq">
  <summary>¿Funciona con PDF escaneados?</summary>
  <p>Sí, se pueden extraer las páginas, pero no se aplica OCR. El texto de un escaneo sigue
  siendo una imagen y no se convierte en texto editable.</p>
</details>
<details class="faq">
  <summary>¿Qué pasa si el PDF tiene contraseña?</summary>
  <p>Se muestra un error y no se procesa. Quita la protección desde la aplicación original y
  vuelve a intentarlo.</p>
</details>""",
    },
    "imagenes-a-pdf": {
        "mode": "images",
        "step_one_title": "Elige las imágenes",
        "hero_title": "Convertir imágenes JPG y PNG en un PDF",
        "hero_sub": (
            "Ordena tus fotos o capturas y crea un documento PDF con una página por imagen. "
            "La conversión se hace en tu navegador, sin subir los archivos."
        ),
        "hero_badge": "JPG y PNG · orden editable · páginas A4 o tamaño original",
        "drop_aria": "Elegir o arrastrar imágenes JPG o PNG para crear un PDF",
        "drop_icon": "&#128444;",
        "drop_title": "Arrastra tus imágenes aquí o <span class=\"accent\">búscalas en tu equipo</span>",
        "drop_sub": (
            f"JPG o PNG hasta {PDF_MAX_MB} MB cada una · máximo {PDF_MAX_IMAGES} imágenes "
            f"y {PDF_MAX_TOTAL_MB} MB en total"
        ),
        "accept": "image/jpeg,image/png,.jpg,.jpeg,.png",
        "multiple": "multiple",
        "files_title": "Imágenes que se convertirán en páginas",
        "controls": _IMAGES_CONTROLS,
        "action_label": "Crear PDF",
        "action_hint": "Añade al menos una imagen JPG o PNG.",
        "seo": f"""<h2>Cómo crear un PDF con imágenes</h2>
<ol class="steps">
  <li><strong>Añade las imágenes</strong> JPG o PNG y revisa la vista previa.</li>
  <li><strong>Ordénalas</strong> con las flechas: cada imagen será una página en ese orden.</li>
  <li><strong>Elige el tamaño de página</strong>: A4 vertical, A4 horizontal o el tamaño de cada imagen.</li>
  <li><strong>Pulsa «Crear PDF»</strong> y descarga el documento resultante.</li>
</ol>

<h2>Qué formatos se admiten</h2>
<p>Se aceptan imágenes JPG/JPEG y PNG. El contenido se comprueba por sus bytes, no solo por la
extensión. WebP, GIF, HEIC, AVIF o SVG se rechazan para evitar generar un PDF incompleto o una
animación convertida en una sola página. La transparencia del PNG se conserva en el PDF; el JPG
no tiene canal alfa.</p>

<h2>Tamaño de página y calidad</h2>
<p>Con A4, cada imagen se escala para caber centrada con un margen de 24 puntos. Con «Tamaño de
cada imagen», la página adopta las dimensiones de la imagen usando 96 píxeles por pulgada; el
tamaño físico puede variar si la imagen tenía otra resolución. Las imágenes se incrustan como
JPEG o PNG, sin recomprimir a JPG, así que no se añade una pérdida extra de calidad por el
simple hecho de crear el PDF. El archivo puede pesar bastante si las fotos son grandes.</p>

<h2>Privacidad, memoria y límites</h2>
<p>La validación, la lectura y la creación del PDF se hacen en tu navegador con canvas y
pdf-lib. No hay subida al servidor ni servicios externos. El límite es de {PDF_MAX_MB} MB por
imagen, {PDF_MAX_TOTAL_MB} MB en total, {PDF_MAX_IMAGES} imágenes y
{PDF_MAX_IMAGE_PIXELS // 1_000_000} megapíxeles por imagen.
En móviles con poca memoria conviene convertir pocas fotos de gran tamaño a la vez.</p>

<h2>Qué no hace esta herramienta</h2>
<p>No aplica OCR, no convierte texto de las imágenes en texto editable, no comprime el PDF
resultante y no promete conservar metadatos EXIF de las fotos. Tampoco acepta documentos PDF de
entrada: para unir o dividir PDF, usa las otras herramientas de la suite.</p>

<h2>Compatibilidad de navegadores</h2>
<p>Funciona en Chrome, Edge, Firefox y Safari actuales con canvas 2D, <code>File</code>,
<code>Blob</code> y módulos JavaScript. pdf-lib se sirve desde este sitio, sin CDN. Un navegador
muy antiguo puede no soportar la decodificación de PNG o las APIs necesarias.</p>

<h2>Preguntas frecuentes</h2>
<details class="faq">
  <summary>¿Puedo cambiar el orden de las imágenes?</summary>
  <p>Sí. Cada imagen tiene botones para subirla o bajarla. Ese orden determina el orden de las
  páginas del PDF.</p>
</details>
<details class="faq">
  <summary>¿Se pierde calidad al crear el PDF?</summary>
  <p>Las imágenes JPEG y PNG se incrustan en el documento; no se recodifican como JPG. Aun así,
  el aumento de tamaño de página puede reescalar visualmente la imagen dentro del PDF. Revisa
  el resultado si la calidad es crítica.</p>
</details>
<details class="faq">
  <summary>¿Se conserva la transparencia de un PNG?</summary>
  <p>Sí, el PDF admite transparencia y pdf-lib conserva el canal alfa del PNG. El fondo del
  visor puede verse distinto según la aplicación con la que abras el archivo.</p>
</details>
<details class="faq">
  <summary>¿Puedo añadir texto o editar las páginas después?</summary>
  <p>Esta herramienta solo coloca imágenes en páginas. No añade texto, numeración, marcas de
  agua ni campos de formulario. Para eso necesitas un editor de PDF.</p>
</details>
<details class="faq">
  <summary>¿Se suben las fotos a internet?</summary>
  <p>No. Todo el proceso ocurre en tu navegador y las imágenes no se envían a Fastools ni a
  terceros.</p>
</details>""",
    },
    "pdf-a-jpg": {
        "mode": "jpg",
        "step_one_title": "Elige el PDF",
        "hero_title": "Convertir PDF a JPG página por página",
        "hero_sub": (
            "Convierte las páginas de un PDF en imágenes JPG con la calidad y la resolución que "
            "elijas. Si hay varias páginas, se descargan juntas en un ZIP."
        ),
        "hero_badge": "Vista previa · calidad ajustable · descarga en ZIP",
        "drop_aria": "Elegir o arrastrar un archivo PDF para convertirlo a JPG",
        "drop_icon": "&#128247;",
        "drop_title": "Arrastra el PDF aquí o <span class=\"accent\">búscalo en tu equipo</span>",
        "drop_sub": (
            f"Un PDF de hasta {PDF_MAX_MB} MB · máximo {PDF_MAX_RENDER_PAGES} páginas "
            "por conversión"
        ),
        "accept": "application/pdf,.pdf",
        "multiple": "",
        "files_title": "Documento de origen",
        "controls": _JPG_CONTROLS,
        "action_label": "Convertir a JPG",
        "action_hint": "Selecciona un PDF para activar la conversión.",
        "seo": f"""<h2>Cómo convertir un PDF a imágenes JPG</h2>
<ol class="steps">
  <li><strong>Añade el PDF</strong> y revisa la vista previa de las primeras páginas.</li>
  <li><strong>Ajusta la calidad</strong> y la resolución de renderizado según el uso que darás a las imágenes.</li>
  <li><strong>Pulsa «Convertir a JPG»</strong>. Verás el progreso real página a página.</li>
  <li><strong>Descarga el JPG</strong> si hay una página o el <strong>ZIP</strong> con todas las imágenes si hay varias.</li>
</ol>

<h2>Calidad, resolución y peso</h2>
<p>La calidad JPG controla el compromiso entre detalle y peso. La resolución se expresa como
múltiplo de 72 ppp: 1&times; son 72 ppp, 1,5&times; son 108 ppp y 2&times; son 144 ppp. Una escala
mayor genera imágenes más grandes y nítidas, pero también más pesadas y con más consumo de
memoria. El fondo se pinta en blanco antes de codificar porque el formato JPG no admite
transparencia.</p>

<h2>ZIP y descargas</h2>
<p>Si el PDF tiene una sola página, se descarga un único archivo JPG. Si tiene varias, se genera
un ZIP sin compresión adicional con un JPG por página. Los JPG ya están comprimidos, así que
volver a comprimir el ZIP apenas ahorraría espacio. Los nombres incluyen el nombre del PDF y el
número de página.</p>

<h2>Límites y memoria</h2>
<p>Se procesan como máximo {PDF_MAX_RENDER_PAGES} páginas por operación y {PDF_MAX_MB} MB de
entrada. Cada página se dibuja en un canvas temporal y se libera al terminar. Si una página es
enorme, la herramienta reduce automáticamente la escala para no superar el límite de píxeles y
lo indica en el progreso. En móviles con poca memoria, convierte documentos largos en varias
operaciones.</p>

<h2>Qué se conserva y qué no</h2>
<p>El JPG reproduce el aspecto renderizado de la página: texto, imágenes y la mayoría de las
anotaciones visibles. No se conservan enlaces, campos de formulario, capas interactivas ni texto
seleccionable. Esta herramienta no hace OCR: un PDF escaneado produce imágenes, no texto
editable. Los PDFs muy complejos pueden renderizarse de forma distinta a la de un visor
profesional.</p>

<h2>Privacidad y documentos protegidos</h2>
<p>El PDF se carga en memoria y se renderiza con PDF.js y canvas en tu navegador. No se envía a
un servidor. Si el documento está protegido con contraseña, se muestra un error claro y no se
intenta descifrar. Los archivos corruptos también se rechazan.</p>

<h2>Compatibilidad de navegadores</h2>
<p>Funciona en Chrome, Edge, Firefox y Safari actuales con canvas 2D, <code>File</code>,
<code>Blob</code> y módulos JavaScript. PDF.js y sus recursos (fuentes estándar, CMaps y
decodificadores WASM) se sirven desde este mismo sitio, sin CDN. La velocidad depende del
navegador y del tamaño de las páginas.</p>

<h2>Preguntas frecuentes</h2>
<details class="faq">
  <summary>¿Puedo elegir solo algunas páginas?</summary>
  <p>Esta versión convierte todas las páginas del PDF, hasta el límite indicado. Si necesitas
  solo una parte, primero puedes extraer las páginas con <a href="/dividir-pdf">Dividir PDF</a>
  y después convertir ese resultado.</p>
</details>
<details class="faq">
  <summary>¿Por qué se descarga un ZIP?</summary>
  <p>Porque un PDF de varias páginas produce varios JPG y el navegador no debe abrir decenas de
  descargas a la vez. El ZIP contiene todas las imágenes con nombres numerados.</p>
</details>
<details class="faq">
  <summary>¿El texto del JPG se puede seleccionar?</summary>
  <p>No. Un JPG es una imagen. Para conservar texto seleccionable necesitas el PDF original o
  un proceso de OCR externo que esta herramienta no ofrece.</p>
</details>
<details class="faq">
  <summary>¿Qué pasa con un PDF protegido?</summary>
  <p>Se detecta y se muestra un error. No se descifra ni se envía a ningún servicio. Quita la
  contraseña con la aplicación original y vuelve a intentarlo.</p>
</details>
<details class="faq">
  <summary>¿Las imágenes se suben al servidor?</summary>
  <p>No. La conversión se hace en tu navegador. El servidor solo entrega la página y las
  bibliotecas necesarias.</p>
</details>""",
    },
    "comprimir-pdf": {
        "mode": "compress",
        "step_one_title": "Elige el PDF",
        "hero_title": "Comprimir PDF sin subirlo a internet",
        "hero_sub": (
            "Reduce el peso de un documento con la calidad y la resolución que elijas. "
            "El PDF se procesa en tu navegador y no se envía a ningún servidor."
        ),
        "hero_badge": "Procesamiento local · calidad ajustable · sin registro",
        "drop_aria": "Elegir o arrastrar un archivo PDF para comprimirlo",
        "drop_icon": "&#128200;",
        "drop_title": "Arrastra tu PDF aquí o <span class=\"accent\">búscalo en tu equipo</span>",
        "drop_sub": (
            f"PDF hasta {PDF_MAX_MB} MB · máximo {PDF_MAX_RENDER_PAGES} páginas por compresión"
        ),
        "accept": "application/pdf,.pdf",
        "multiple": "",
        "files_title": "Documento que se va a comprimir",
        "controls": _COMPRESS_CONTROLS,
        "action_label": "Comprimir PDF",
        "action_hint": "Selecciona un PDF para activar la compresión.",
        "seo": f"""<h2>Cómo se reduce el peso de un PDF</h2>
<p>Esta herramienta no reescribe el texto ni elimina objetos internos: <strong>renderiza cada
página como una imagen JPG</strong> con la calidad y la resolución elegidas y construye un PDF
nuevo con esas imágenes. Es el método más efectivo en el navegador para documentos escaneados,
presentaciones con muchas fotos o PDF exportados desde móvil.</p>
<ol class="steps">
  <li><strong>Añade el PDF</strong> con el selector o arrastrándolo a la zona de subida.</li>
  <li><strong>Ajusta la calidad</strong> (40–95 %) y la resolución (1×, 1,5× o 2×).</li>
  <li><strong>Pulsa «Comprimir PDF»</strong> y espera a que termine el procesamiento local.</li>
  <li><strong>Compara el tamaño</strong> y descarga el resultado si te sirve.</li>
</ol>

<h2>Cuándo funciona bien y cuándo no</h2>
<p>Funciona especialmente bien con escaneos, capturas y documentos con imágenes grandes. En
cambio, un PDF que ya estaba comprimido o que solo contiene texto vectorial puede pesar lo mismo
o incluso más, porque cada página se sustituye por una imagen. Si eso ocurre, baja la calidad al
40–60 % o la resolución a 1×; si sigue sin mejorar, el documento no se beneficia de este método.</p>
<p>El límite es de {PDF_MAX_RENDER_PAGES} páginas por operación y {PDF_MAX_MB} MB de entrada. Para
documentos más largos, divide primero el PDF y comprime cada parte.</p>

<h2>Qué se conserva y qué se pierde</h2>
<p>Se conserva el aspecto visual de cada página y el tamaño original de la página. Se pierden el
texto seleccionable, los enlaces, los formularios interactivos, los marcadores, las capas y los
metadatos. Tampoco se aplica OCR: un escaneo sigue siendo una imagen. Revisa el resultado antes de
enviarlo si el documento es importante.</p>

<h2>Privacidad</h2>
<p>El archivo no se sube a Fastools ni a terceros. La lectura, el renderizado, la codificación JPG
y la reconstrucción del PDF ocurren dentro de tu navegador con bibliotecas servidas desde este
sitio. Al cerrar o recargar la página se liberan los datos en memoria.</p>

<h2>Preguntas frecuentes</h2>
<details class="faq">
  <summary>¿Se puede volver a editar el PDF comprimido?</summary>
  <p>Sí, pero su contenido será una imagen por página. No podrás seleccionar ni buscar el texto
  original, y un editor lo tratará como una imagen escaneada.</p>
</details>
<details class="faq">
  <summary>¿Por qué el archivo comprimido pesa más?</summary>
  <p>Porque el PDF original ya estaba optimizado o tenía muy poco contenido visual. Rasterizar
  añade una imagen por página. En esos casos no hay ganancia real: conserva el original.</p>
</details>
<details class="faq">
  <summary>¿Se sube mi documento a un servidor?</summary>
  <p>No. Todo el proceso es local en tu navegador. La página no envía el archivo por la red.</p>
</details>""",
    },
}


def render_pdf_page(key: str, lang: str = i18n.DEFAULT_LANG) -> str:
    """Renderiza una de las cinco páginas compartidas de la suite PDF."""
    normalized = i18n.normalize_lang(lang)
    meta = views.meta_for(key, normalized)
    content = PDF_TOOL_CONTENT[key]
    html_text = (STATIC_DIR / "pdf-tool.html").read_text(encoding="utf-8")

    replacements = {
        "<!-- HEAD -->": views.head_html(meta, normalized),
        "<!-- NAV -->": views.nav_html(meta.nav, normalized, meta.path),
        "<!-- FOOTER -->": views.footer_html(normalized),
        "<!-- RELATED -->": (
            views.related_html(meta.tool_slug, normalized) if meta.tool_slug else ""
        ),
        "<!-- MODE -->": content["mode"],
        "<!-- HERO_TITLE -->": content["hero_title"],
        "<!-- HERO_SUB -->": content["hero_sub"],
        "<!-- HERO_BADGE -->": content["hero_badge"],
        "<!-- STEP_ONE_TITLE -->": content["step_one_title"],
        "<!-- DROP_ARIA -->": content["drop_aria"],
        "<!-- DROP_ICON -->": content["drop_icon"],
        "<!-- DROP_TITLE -->": content["drop_title"],
        "<!-- DROP_SUB -->": content["drop_sub"],
        "<!-- ACCEPT -->": content["accept"],
        "<!-- MULTIPLE -->": content["multiple"],
        "<!-- FILES_TITLE -->": content["files_title"],
        "<!-- CONTROLS -->": content["controls"],
        "<!-- ACTION_LABEL -->": content["action_label"],
        "<!-- ACTION_HINT -->": content["action_hint"],
        "<!-- SEO_CONTENT -->": content["seo"],
    }
    for marker, value in replacements.items():
        html_text = html_text.replace(marker, value)
    html_text = html_text.replace('<html lang="es"', f'<html lang="{normalized}"', 1)
    return i18n.translate_html(html_text, normalized)
