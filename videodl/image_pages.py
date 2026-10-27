"""Páginas de las herramientas de imagen.

Las tres utilidades comparten una sola plantilla HTML y un único motor de
procesamiento en el navegador. Este módulo solo aporta el texto y los controles
propios de cada modo; la cabecera, la navegación, las herramientas relacionadas
y el SEO técnico salen de ``views.py``.
"""

from __future__ import annotations

from . import views
from .paths import STATIC_DIR

# Debe coincidir con MAX_FILE_BYTES de static/image-tools.js (25 MB).
IMAGE_MAX_MB = 25

_TRANSPARENCY_WARNING = """<div id="transparency-warning" class="warning-box hidden" role="status">
  <strong>Esta imagen tiene zonas transparentes.</strong>
  <p>El JPG no admite transparencia: esas zonas se rellenarán con el color de fondo.
  Si necesitas conservarla, elige PNG o WebP.</p>
</div>"""

_BACKGROUND_FIELD = """<div id="jpeg-background-field" class="image-suboption hidden">
  <label for="jpeg-background">Color de fondo para JPG</label>
  <input type="color" id="jpeg-background" value="#ffffff" />
  <span class="muted-small">Se aplica a las zonas transparentes.</span>
</div>"""

_QUALITY_FIELD = """<div class="option-field image-quality-field">
  <label for="quality">Calidad <output id="quality-value" for="quality">80 %</output></label>
  <input type="range" id="quality" min="10" max="100" step="5" value="80" />
  <p class="field-hint" id="quality-hint">Ajusta el equilibrio entre peso y calidad visible.</p>
</div>"""

IMAGE_TOOL_CONTENT: dict[str, dict[str, str]] = {
    "comprimir-imagen": {
        "mode": "compress",
        "hero_title": "Comprimir imágenes sin subirlas a internet",
        "hero_sub": (
            "Reduce el peso de tus fotos JPG, PNG o WebP con la calidad que elijas. "
            "Todo ocurre dentro de tu navegador: la imagen nunca sale de tu equipo."
        ),
        "hero_badge": "Procesamiento local · vista previa antes y después",
        "action_label": "🗜️ Comprimir imagen",
        "action_hint": "Elige una imagen para activar la compresión.",
        "controls": f"""<div class="image-options">
  <label class="option-field" for="compress-format">
    <span>Formato de salida</span>
    <select id="compress-format">
      <option value="original" selected>Mantener el formato original</option>
      <option value="image/jpeg" data-mime="image/jpeg">JPG · más ligero, sin transparencia</option>
      <option value="image/png" data-mime="image/png">PNG · sin pérdida, conserva transparencia</option>
      <option value="image/webp" data-mime="image/webp">WebP · buen equilibrio</option>
    </select>
  </label>
  {_QUALITY_FIELD}
</div>
{_BACKGROUND_FIELD}
{_TRANSPARENCY_WARNING}
<p class="image-note"><strong>La compresión no garantiza que el archivo resulte más pequeño.</strong>
Si la imagen ya estaba muy optimizada, al volver a codificarla puede pesar igual o incluso
algo más. Lo verás en el porcentaje real antes de descargar y no se modifica tu archivo original.</p>""",
        "seo": """<h2>Cómo comprimir una imagen en el navegador</h2>
<ol class="steps">
  <li><strong>Elige la imagen</strong> con el selector o arrástrala a la zona de subida.</li>
  <li><strong>Ajusta la calidad</strong> y, si quieres cambiar de formato, elige JPG, PNG o WebP.</li>
  <li><strong>Pulsa «Comprimir imagen»</strong> y compara la vista previa y los tamaños reales.</li>
  <li><strong>Descarga el resultado</strong> si el peso te conviene; tu archivo original no se toca.</li>
</ol>

<h2>Qué formato conviene para cada imagen</h2>
<table class="limits-table">
  <thead><tr><th>Formato</th><th>Compresión</th><th>Transparencia</th><th>Cuándo usarlo</th></tr></thead>
  <tbody>
    <tr><td><strong>JPG</strong></td><td>Con pérdida</td><td>No</td><td>Fotos y fondos sin transparencia.</td></tr>
    <tr><td><strong>PNG</strong></td><td>Sin pérdida</td><td>Sí</td><td>Logos, capturas y gráficos con bordes nítidos.</td></tr>
    <tr><td><strong>WebP</strong></td><td>Con o sin pérdida</td><td>Sí</td><td>Web moderna: buen peso con buena calidad.</td></tr>
  </tbody>
</table>
<p>El control de calidad solo afecta a JPG y WebP. En PNG el navegador vuelve a codificar
sin pérdida y el deslizador no cambia el resultado, aunque sí puede eliminar metadatos.</p>

<h2>Cuándo baja el peso y cuándo no</h2>
<p>Una foto de cámara suele reducirse mucho con JPG o WebP. En cambio, un PNG ya optimizado
o una imagen pequeña pueden pesar lo mismo o más al recodificarse. Esta herramienta muestra
el tamaño original, el final y el porcentaje real, también cuando el resultado es negativo.</p>

<h2>Privacidad, memoria y límites</h2>
<p>La imagen se carga con una URL temporal del propio navegador y se dibuja en un
<code>&lt;canvas&gt;</code> local. No hay peticiones de subida ni servicios externos. Al quitar
la imagen o cambiar de archivo se liberan las URL temporales y el canvas. El límite es de
25 MB por archivo, 16 384 px por lado y 64 megapíxeles; en móviles con poca memoria conviene
usar imágenes más pequeñas.</p>

<h2>Compatibilidad de navegadores</h2>
<p>Funciona en versiones actuales de Chrome, Edge, Firefox, Safari y navegadores móviles con
canvas 2D. JPG y PNG se codifican en todos ellos; WebP depende del soporte del navegador y la
página desactiva la opción cuando no está disponible. El color de fondo para JPG también evita
que las zonas transparentes salgan negras.</p>

<h2>Preguntas frecuentes</h2>
<details class="faq">
  <summary>¿La imagen se sube a algún servidor?</summary>
  <p>No. La validación, el redimensionado y la codificación se hacen en tu navegador. No se
  envía la imagen a FasTools ni a terceros.</p>
</details>
<details class="faq">
  <summary>¿Siempre se reduce el tamaño del archivo?</summary>
  <p>No. Si el archivo ya estaba bien comprimido, recodificarlo puede aumentarlo. La frase
  «comprimir» describe el intento de reducir el peso, no una garantía matemática. Por eso
  mostramos el resultado real antes de que descargues.</p>
</details>
<details class="faq">
  <summary>¿Pierdo calidad al comprimir?</summary>
  <p>JPG y WebP usan compresión con pérdida: cuanto menor sea la calidad, más artefactos y
  menos detalle. PNG es sin pérdida. Para fotos, una calidad de 75–85 % suele ser un buen
  equilibrio; para texto y capturas, prueba PNG o WebP.</p>
</details>
<details class="faq">
  <summary>¿Qué pasa si la imagen es transparente y elijo JPG?</summary>
  <p>Se muestra un aviso y puedes escoger el color de fondo. El JPG resultante no tendrá
  transparencia. Si la necesitas, elige PNG o WebP.</p>
</details>
<details class="faq">
  <summary>¿Puedo comprimir varias imágenes a la vez?</summary>
  <p>Esta versión procesa una imagen por vez para controlar el uso de memoria. Puedes repetir
  el proceso con otra imagen al terminar.</p>
</details>

<p>¿Solo quieres cambiar de formato o de tamaño? Usa
<a href="/convertir-imagen">convertir imágenes</a> o
<a href="/redimensionar-imagen">redimensionar imágenes</a>.</p>""",
    },
    "convertir-imagen": {
        "mode": "convert",
        "hero_title": "Convertir imágenes entre JPG, PNG y WebP",
        "hero_sub": (
            "Cambia el formato de tus imágenes con control de calidad y transparencia. "
            "La conversión se hace en tu navegador, sin subir nada a internet."
        ),
        "hero_badge": "Sin servidores · transparencia bajo control",
        "action_label": "🔄 Convertir imagen",
        "action_hint": "Elige una imagen para activar la conversión.",
        "controls": f"""<div class="image-options">
  <label class="option-field" for="convert-format">
    <span>Convertir a</span>
    <select id="convert-format">
      <option value="image/webp" data-mime="image/webp" selected>WebP · ligero y con transparencia</option>
      <option value="image/jpeg" data-mime="image/jpeg">JPG · universal, sin transparencia</option>
      <option value="image/png" data-mime="image/png">PNG · sin pérdida y con transparencia</option>
    </select>
  </label>
  {_QUALITY_FIELD}
</div>
{_BACKGROUND_FIELD}
{_TRANSPARENCY_WARNING}
<p class="image-note">JPG no admite transparencia y se rellenará con el color de fondo.
PNG y WebP conservan el canal alfa. El control de calidad no se aplica a PNG porque su
compresión es sin pérdida.</p>""",
        "seo": """<h2>Cómo convertir una imagen de formato</h2>
<ol class="steps">
  <li><strong>Añade la imagen</strong> JPG, PNG o WebP desde tu equipo.</li>
  <li><strong>Elige el formato de salida</strong>: JPG, PNG o WebP según lo que necesites.</li>
  <li><strong>Revisa la transparencia</strong>: si vas a JPG y hay zonas transparentes, escoge el fondo.</li>
  <li><strong>Descarga el resultado</strong> con el nuevo formato y comprueba el peso final.</li>
</ol>

<h2>Diferencias entre JPG, PNG y WebP</h2>
<table class="limits-table">
  <thead><tr><th>Formato</th><th>Ventaja</th><th>Limitación</th></tr></thead>
  <tbody>
    <tr><td><strong>JPG</strong></td><td>Compatible con casi cualquier app y equipo.</td><td>Sin transparencia y con pérdida de calidad.</td></tr>
    <tr><td><strong>PNG</strong></td><td>Sin pérdida y conserva la transparencia.</td><td>Pesa más en fotografías.</td></tr>
    <tr><td><strong>WebP</strong></td><td>Buen peso, transparencia y calidad.</td><td>Algunas apps antiguas no lo abren.</td></tr>
  </tbody>
</table>

<h2>Transparencia: lo que debes saber</h2>
<p>Al convertir PNG o WebP con transparencia a JPG, las zonas transparentes no pueden
conservarse. La herramienta lo detecta, muestra un aviso y pinta un fondo opaco (blanco por
defecto, configurable) antes de codificar. Nunca se genera un JPG con transparencia simulada.</p>

<h2>Privacidad y límites técnicos</h2>
<p>La conversión usa la API canvas del navegador. No se sube la imagen ni se consulta un
servicio externo. Se admiten archivos de hasta 25 MB, 16 384 px por lado y 64 megapíxeles.
Los metadatos EXIF del original (incluida la fecha o la cámara) no se copian al archivo final.</p>

<h2>Compatibilidad de navegadores</h2>
<p>JPG y PNG se codifican en todos los navegadores modernos. WebP necesita soporte de
codificación: Chrome, Edge, Firefox y Safari actuales lo incluyen, pero la página comprueba
el soporte real y desactiva la opción si no está disponible. La orientación EXIF se aplica al
decodificar en los navegadores actuales; en navegadores muy antiguos una foto girada puede
aparecer con la orientación del píxel original.</p>

<h2>Preguntas frecuentes</h2>
<details class="faq">
  <summary>¿Convierte también imágenes AVIF, GIF o HEIC?</summary>
  <p>No. Esta herramienta acepta JPG, PNG y WebP. Formatos como GIF animado, SVG, AVIF o HEIC
  se rechazan con un mensaje claro para no generar archivos incompletos o animaciones
  convertidas en una sola imagen.</p>
</details>
<details class="faq">
  <summary>¿Se conserva la transparencia al convertir a PNG o WebP?</summary>
  <p>Sí. El canvas mantiene el canal alfa y el archivo final conserva las zonas transparentes.
  Puedes comprobarlo en la vista previa, que usa un fondo de cuadros.</p>
</details>
<details class="faq">
  <summary>¿La conversión siempre reduce el peso?</summary>
  <p>No. Convertir no es sinónimo de comprimir: un PNG puede pesar más que el JPG de origen y
  un JPG de alta calidad puede superar a un WebP. La página muestra el tamaño real y el
  porcentaje, positivo o negativo.</p>
</details>
<details class="faq">
  <summary>¿Se pierde calidad al convertir?</summary>
  <p>Depende del destino. JPG y WebP con pérdida pueden degradar detalles; PNG es sin pérdida.
  Cada conversión con pérdida parte del archivo que subes, no de una copia infinita, así que
  evita repetir el proceso muchas veces sobre el mismo resultado.</p>
</details>
<details class="faq">
  <summary>¿Puedo cambiar también el tamaño?</summary>
  <p>Sí. La conversión mantiene las dimensiones originales. Si además quieres escalar la
  imagen, usa <a href="/redimensionar-imagen">redimensionar imágenes</a>.</p>
</details>""",
    },
    "redimensionar-imagen": {
        "mode": "resize",
        "hero_title": "Redimensionar imágenes por píxeles o porcentaje",
        "hero_sub": (
            "Cambia el ancho y el alto de tus fotos manteniendo la proporción. "
            "Vista previa, tamaños exactos y descarga directa, todo en tu navegador."
        ),
        "hero_badge": "Píxeles o porcentaje · proporción opcional",
        "action_label": "📐 Redimensionar imagen",
        "action_hint": "Elige una imagen para activar el redimensionado.",
        "controls": """<div class="image-options">
  <label class="option-field" for="size-mode">
    <span>Medir el tamaño en</span>
    <select id="size-mode">
      <option value="pixels" selected>Píxeles</option>
      <option value="percent">Porcentaje del original</option>
    </select>
  </label>

  <div id="pixels-fields" class="option-field">
    <span>Nuevo tamaño</span>
    <div class="size-inputs">
      <label for="resize-width">Ancho
        <span class="size-input-wrap"><input type="number" id="resize-width" min="1" max="16384" step="1" inputmode="numeric" /> <span>px</span></span>
      </label>
      <span class="size-times" aria-hidden="true">×</span>
      <label for="resize-height">Alto
        <span class="size-input-wrap"><input type="number" id="resize-height" min="1" max="16384" step="1" inputmode="numeric" /> <span>px</span></span>
      </label>
    </div>
  </div>

  <div id="percent-fields" class="option-field hidden">
    <span>Porcentaje del original</span>
    <div class="size-inputs">
      <label for="resize-percent-width">Ancho
        <span class="size-input-wrap"><input type="number" id="resize-percent-width" min="1" max="400" step="1" inputmode="numeric" value="100" /> <span>%</span></span>
      </label>
      <span class="size-times" aria-hidden="true">×</span>
      <label for="resize-percent-height">Alto
        <span class="size-input-wrap"><input type="number" id="resize-percent-height" min="1" max="400" step="1" inputmode="numeric" value="100" /> <span>%</span></span>
      </label>
    </div>
  </div>
</div>

<label class="check-field">
  <input type="checkbox" id="keep-ratio" checked />
  <span>Mantener la proporción (no deformar la imagen)</span>
</label>

<div class="preset-row" id="resize-presets" role="group" aria-label="Tamaños rápidos">
  <button type="button" class="soft-btn" data-percent="25">25 %</button>
  <button type="button" class="soft-btn" data-percent="50">50 %</button>
  <button type="button" class="soft-btn" data-percent="75">75 %</button>
  <button type="button" class="soft-btn" data-percent="100">100 %</button>
  <button type="button" class="soft-btn" data-width="1920">1920 px</button>
  <button type="button" class="soft-btn" data-width="1080">1080 px</button>
  <button type="button" class="soft-btn" data-width="800">800 px</button>
</div>

<p id="resize-summary" class="image-note">El tamaño final aparecerá aquí.</p>
<p class="image-note">Ampliar una imagen no añade detalle: solo interpola los píxeles existentes.
Los presets en píxeles nunca amplían una imagen más pequeña. El formato original se conserva y
la calidad de salida de JPG/WebP se fija en un valor alto para evitar pérdidas innecesarias.</p>""",
        "seo": """<h2>Cómo redimensionar una imagen</h2>
<ol class="steps">
  <li><strong>Sube la imagen</strong> JPG, PNG o WebP.</li>
  <li><strong>Elige píxeles o porcentaje</strong> y escribe el nuevo ancho y alto.</li>
  <li><strong>Deja marcada la proporción</strong> si no quieres deformar la imagen.</li>
  <li><strong>Procesa y descarga</strong> el resultado con sus dimensiones y peso reales.</li>
</ol>

<h2>Píxeles frente a porcentaje</h2>
<table class="limits-table">
  <thead><tr><th>Modo</th><th>Cuándo usarlo</th><th>Ejemplo</th></tr></thead>
  <tbody>
    <tr><td><strong>Píxeles</strong></td><td>Una medida exacta para una web, un formulario o una impresión.</td><td>800 × 600 px</td></tr>
    <tr><td><strong>Porcentaje</strong></td><td>Reducir o ampliar sin calcular el tamaño final.</td><td>50 % de 4000 × 3000 = 2000 × 1500 px</td></tr>
  </tbody>
</table>
<p>Con la proporción bloqueada, al cambiar el ancho se recalcula el alto (y al revés) usando
las dimensiones originales. Si la desbloqueas, puedes introducir un tamaño distinto en cada
lado; la vista previa mostrará el resultado deformado antes de descargarlo.</p>

<h2>Calidad y transparencia</h2>
<p>El formato del archivo se conserva. JPG se vuelve a codificar con calidad alta y un fondo
blanco si detecta transparencia (el JPG no la admite); PNG y WebP mantienen el canal alfa.
El redimensionado no recupera detalle perdido: al ampliar, el navegador interpola los píxeles.</p>

<h2>Límites y memoria</h2>
<p>Se aceptan archivos de hasta 25 MB, con un máximo de 16 384 px por lado y 64 megapíxeles
en la salida. El porcentaje va de 1 % a 400 %. Cada imagen se procesa una vez en un canvas
temporal que se libera al terminar; las URL de vista previa se revocan al cambiar de archivo
o cerrar la página.</p>

<h2>Compatibilidad de navegadores</h2>
<p>Funciona en Chrome, Edge, Firefox, Safari y navegadores móviles actuales con canvas 2D.
La calidad del reescalado depende del motor del navegador. En equipos con poca memoria, una
imagen de decenas de megapíxeles puede tardar o fallar aunque esté dentro del límite: en ese
caso reduce primero el archivo con una versión más pequeña.</p>

<h2>Preguntas frecuentes</h2>
<details class="faq">
  <summary>¿Se puede ampliar una imagen?</summary>
  <p>Sí, hasta el 400 % o el límite de píxeles. Ampliar no crea detalle nuevo; solo interpola.
  Para impresión o pantallas grandes conviene partir de una foto con suficiente resolución.</p>
</details>
<details class="faq">
  <summary>¿Qué pasa si desbloqueo la proporción?</summary>
  <p>Puedes usar un ancho y un alto independientes. La imagen se estirará o comprimirá. La
  vista previa y el resumen muestran las dimensiones exactas antes de descargar.</p>
</details>
<details class="faq">
  <summary>¿Se sube la imagen al servidor?</summary>
  <p>No. El redimensionado se hace con canvas en tu navegador. No hay endpoints de subida ni
  servicios externos implicados.</p>
</details>
<details class="faq">
  <summary>¿Por qué el archivo final no siempre pesa menos?</summary>
  <p>Al reducir dimensiones suele bajar el peso, pero recodificar un JPG o WebP puede aumentar
  el tamaño si el original ya estaba muy optimizado. El resultado real se muestra antes de
  descargar y el original permanece intacto.</p>
</details>
<details class="faq">
  <summary>¿Mantiene la transparencia?</summary>
  <p>En PNG y WebP sí. En JPG no es posible: se avisa y se usa un fondo blanco. Si necesitas
  transparencia, mantén el formato PNG o WebP.</p>
</details>

<p>Si además quieres reducir el peso, prueba <a href="/comprimir-imagen">comprimir imágenes</a>
o <a href="/convertir-imagen">convertir imágenes</a>.</p>""",
    },
}


def render_image_page(key: str) -> str:
    """Renderiza una de las tres páginas compartidas de imagen."""
    meta = views.PAGE_META[key]
    content = IMAGE_TOOL_CONTENT[key]
    html_text = (STATIC_DIR / "imagen-tool.html").read_text(encoding="utf-8")

    replacements = {
        "<!-- HEAD -->": views.head_html(meta),
        "<!-- NAV -->": views.nav_html(meta.nav),
        "<!-- FOOTER -->": views.footer_html(),
        "<!-- RELATED -->": views.related_html(meta.tool_slug) if meta.tool_slug else "",
        "<!-- MODE -->": content["mode"],
        "<!-- HERO_TITLE -->": content["hero_title"],
        "<!-- HERO_SUB -->": content["hero_sub"],
        "<!-- HERO_BADGE -->": content["hero_badge"],
        "<!-- MAX_MB -->": str(IMAGE_MAX_MB),
        "<!-- CONTROLS -->": content["controls"],
        "<!-- ACTION_LABEL -->": content["action_label"],
        "<!-- ACTION_HINT -->": content["action_hint"],
        "<!-- SEO_CONTENT -->": content["seo"],
    }
    for marker, value in replacements.items():
        html_text = html_text.replace(marker, value)
    return html_text
