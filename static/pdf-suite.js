/* Interfaz y procesamiento de la suite PDF.

   Todo ocurre en el navegador: pdf-lib reconstruye los documentos y PDF.js
   renderiza las páginas. La página nunca hace fetch de los archivos ni los
   envía a un servidor. Las utilidades puras viven en pdf-core.js. */

const core = window.VDPdfCore;
const ImageTools = window.VDImage;
const VD = window.VD;
const tr = (key, fallback, values) =>
  typeof window.t === "function" ? window.t(key, fallback, values) : fallback;

if (!core || !VD) {
  throw new Error(
    tr("pdf.missingCore", "No se cargaron las utilidades locales de la suite PDF.")
  );
}

const {
  $,
  showToast,
  showError,
  clearError,
  formatBytes,
  triggerDownload,
} = VD;

const MODE = document.body.dataset.pdfTool;
const MODES = {
  merge: {
    multiple: true,
    kind: "pdf",
    maxFiles: core.MAX_FILES,
    accept: "application/pdf,.pdf",
    action: tr("pdf.actionMerge", "Unir PDF"),
  },
  split: {
    multiple: false,
    kind: "pdf",
    maxFiles: 1,
    accept: "application/pdf,.pdf",
    action: tr("pdf.actionSplit", "Extraer páginas"),
  },
  compress: {
    multiple: false,
    kind: "pdf",
    maxFiles: 1,
    accept: "application/pdf,.pdf",
    action: tr("pdf.actionCompress", "Comprimir PDF"),
  },
  images: {
    multiple: true,
    kind: "image",
    maxFiles: core.MAX_IMAGES,
    accept: "image/jpeg,image/png,.jpg,.jpeg,.png",
    action: tr("pdf.actionImages", "Crear PDF"),
  },
  jpg: {
    multiple: false,
    kind: "pdf",
    maxFiles: 1,
    accept: "application/pdf,.pdf",
    action: tr("pdf.actionJpg", "Convertir a JPG"),
  },
};

const CONFIG = MODES[MODE];
if (!CONFIG) {
  throw new Error(tr("pdf.unknownMode", "Modo de herramienta PDF desconocido."));
}

const state = {
  items: [],
  busy: false,
  result: null,
  resultPreviewUrls: [],
  previewToken: 0,
  runId: 0,
  libsReady: false,
};

let itemSeq = 0;
let PDFDocument = null;
let getDocument = null;
let pdfjs = null;

// ---------------------------------------------------------------------------
// Referencias del DOM
// ---------------------------------------------------------------------------

const dropzone = $("dropzone");
const fileInput = $("file-input");
const filesSection = $("files-section");
const fileList = $("file-list");
const fileCount = $("file-count");
const clearAll = $("clear-all");
const sizeWarning = $("size-warning");
const workspace = $("workspace");
const previewGrid = $("preview-grid");
const previewHint = $("preview-hint");
const previewNote = $("preview-note");
const controls = $("controls");
const processBtn = $("process-btn");
const actionHint = $("action-hint");
const progressWrap = $("progress-wrap");
const progress = $("progress");
const progressLabel = $("progress-label");
const progressValue = $("progress-value");
const libraryStatus = $("library-status");
const resultSection = $("result");
const outBefore = $("out-before");
const outBeforeDetail = $("out-before-detail");
const outAfter = $("out-after");
const outAfterDetail = $("out-after-detail");
const outSaved = $("out-saved");
const resultPreviews = $("result-previews");
const resultNote = $("result-note");
const downloadBtn = $("download-btn");
const againBtn = $("again-btn");
const rangeInput = $("page-ranges");
const rangeSummary = $("range-summary");
const rangePresets = $("range-presets");
const pageSize = $("page-size");
const jpgQuality = $("jpg-quality");
const jpgQualityValue = $("jpg-quality-value");
const renderScale = $("render-scale");
const errorClose = $("error-close");

const isPdfMode = CONFIG.kind === "pdf";
const previewLimit = MODE === "jpg" || MODE === "compress" ? 8 : 24;

// ---------------------------------------------------------------------------
// Utilidades generales
// ---------------------------------------------------------------------------

function yieldToUi() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function safeRevoke(url) {
  if (!url) return;
  try {
    URL.revokeObjectURL(url);
  } catch (_) {
    /* La URL ya no existe. */
  }
}

function totalSize() {
  return state.items.reduce((sum, item) => sum + (item.size || 0), 0);
}

function totalPages() {
  return state.items.reduce((sum, item) => sum + (item.pageCount || 1), 0);
}

function fileLabel(count) {
  return count === 1
    ? tr("pdf.fileOne", "1 archivo")
    : tr("pdf.filesMany", `${count} archivos`, { count });
}

function pagesLabel(count) {
  return count === 1
    ? tr("pdf.pageOne", "1 página")
    : tr("pdf.pagesMany", `${count} páginas`, { count });
}

function imagesLabel(count) {
  return count === 1
    ? tr("pdf.imageOne", "1 imagen")
    : tr("pdf.imagesMany", `${count} imágenes`, { count });
}

function updateLimitHint() {
  const limitHint = $("limit-hint");
  if (!limitHint) return;
  if (MODE === "images") {
    limitHint.textContent = tr(
      "pdf.limitImages",
      `Hasta ${core.MAX_FILE_BYTES / (1024 * 1024)} MB por imagen · ${core.MAX_IMAGES} imágenes · ${core.MAX_IMAGE_PIXELS / 1_000_000} MP · ${core.MAX_TOTAL_BYTES / (1024 * 1024)} MB en total`,
      {
        mb: core.MAX_FILE_BYTES / (1024 * 1024),
        images: core.MAX_IMAGES,
        megapixels: core.MAX_IMAGE_PIXELS / 1_000_000,
        total: core.MAX_TOTAL_BYTES / (1024 * 1024),
      }
    );
  } else if (MODE === "jpg" || MODE === "compress") {
    limitHint.textContent = tr(
      "pdf.limitRender",
      `Hasta ${core.MAX_FILE_BYTES / (1024 * 1024)} MB · ${core.MAX_RENDER_PAGES} páginas por ${MODE === "jpg" ? "conversión" : "compresión"}`,
      {
        mb: core.MAX_FILE_BYTES / (1024 * 1024),
        pages: core.MAX_RENDER_PAGES,
        operation: MODE === "jpg" ? "conversión" : "compresión",
      }
    );
  } else {
    limitHint.textContent = tr(
      "pdf.limitPdf",
      `Hasta ${core.MAX_FILE_BYTES / (1024 * 1024)} MB por PDF · ${core.MAX_PDF_PAGES} ${MODE === "merge" ? "páginas combinadas" : "páginas"}`,
      {
        mb: core.MAX_FILE_BYTES / (1024 * 1024),
        pages: core.MAX_PDF_PAGES,
      }
    );
  }
}

function updateSizeWarning() {
  if (!sizeWarning) return;
  const total = totalSize();
  let text = "";
  if (total > core.MAX_TOTAL_BYTES) {
    text = tr(
      "pdf.warningTotal",
      "La selección supera el límite total. Quita algún archivo antes de continuar."
    );
  } else if (total > 30 * 1024 * 1024) {
    text = tr(
      "pdf.warningLarge",
      "La selección es grande. El procesamiento puede tardar y consumir bastante memoria, sobre todo en móviles. Si falla, prueba con menos archivos."
    );
  } else if (
    (MODE === "jpg" || MODE === "compress") &&
    state.items[0] &&
    state.items[0].pageCount > 40
  ) {
    text = tr(
      "pdf.warningPages",
      `Este PDF tiene ${state.items[0].pageCount} páginas. Procesarlas todas puede consumir mucha memoria; si el navegador falla, divide el documento y prueba por partes.`,
      { pages: state.items[0].pageCount }
    );
  } else if (state.items.some((item) => item.size > 10 * 1024 * 1024)) {
    text = tr(
      "pdf.warningBigFile",
      "Hay un archivo de más de 10 MB. El navegador lo cargará completo en memoria; cierra otras pestañas pesadas si notas que va lento."
    );
  }
  sizeWarning.textContent = text;
  sizeWarning.classList.toggle("hidden", !text);
}

function cleanupCanvases(container) {
  if (!container) return;
  container.querySelectorAll("canvas").forEach((canvas) => {
    canvas.width = 0;
    canvas.height = 0;
  });
  container.replaceChildren();
}

function clearResult() {
  cleanupCanvases(resultPreviews);
  if (state.result && state.result.url) safeRevoke(state.result.url);
  state.result = null;
  state.resultPreviewUrls.forEach(safeRevoke);
  state.resultPreviewUrls = [];
  if (resultSection) resultSection.classList.add("hidden");
  if (downloadBtn) {
    downloadBtn.disabled = true;
    downloadBtn.textContent = tr("pdf.downloadResult", "Descargar resultado");
  }
}

function resetAll() {
  if (state.busy) return;
  clearResult();
  clearError();
  state.items.forEach((item) => safeRevoke(item.thumbUrl));
  state.items = [];
  if (fileInput) fileInput.value = "";
  hideProgress();
  syncUI();
}

function setBusy(value) {
  state.busy = Boolean(value);
  if (processBtn) processBtn.disabled = state.busy || !canProcess();
  if (dropzone) {
    dropzone.classList.toggle("is-busy", state.busy);
    dropzone.setAttribute("aria-disabled", state.busy ? "true" : "false");
  }
  if (clearAll) clearAll.disabled = state.busy || state.items.length === 0;
  updateFileList();
}

function setProgress(percent, label) {
  if (!progressWrap || !progress) return;
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  progressWrap.classList.remove("hidden");
  progress.value = value;
  progress.textContent = `${Math.round(value)} %`;
  if (progressValue) progressValue.textContent = `${Math.round(value)} %`;
  if (label && progressLabel) progressLabel.textContent = label;
}

function hideProgress() {
  if (progressWrap) progressWrap.classList.add("hidden");
  if (progress) {
    progress.value = 0;
    progress.textContent = "0 %";
  }
  if (progressValue) progressValue.textContent = "0 %";
  if (progressLabel) {
    progressLabel.textContent = tr("pdf.preparing", "Preparando…");
  }
}

// ---------------------------------------------------------------------------
// Validación y carga de archivos
// ---------------------------------------------------------------------------

async function inspectPdf(file) {
  const check = await core.validatePdfFile(file);
  if (!check.ok) return check;

  let bytes;
  try {
    bytes = new Uint8Array(await file.arrayBuffer());
  } catch (_) {
    return {
      ok: false,
      code: "unreadable",
      error: tr(
        "pdf.unreadableFile",
        `No se pudo leer “${file.name}”. Comprueba que el archivo siga disponible.`,
        { name: file.name }
      ),
    };
  }

  let doc;
  try {
    doc = await PDFDocument.load(bytes, { updateMetadata: false });
  } catch (error) {
    const info = core.friendlyPdfError(error, file.name);
    return { ok: false, code: info.code, error: info.message };
  }

  const pageCount = doc.getPageCount();
  if (!pageCount) {
    return {
      ok: false,
      code: "empty-pdf",
      error: tr(
        "pdf.noReadablePages",
        `“${file.name}” no tiene páginas legibles.`,
        { name: file.name }
      ),
    };
  }

  if (MODE === "jpg" && pageCount > core.MAX_RENDER_PAGES) {
    return {
      ok: false,
      code: "too-many-pages",
      error: tr(
        "pdf.limitJpgPages",
        `"${file.name}" tiene ${pageCount} páginas y el límite para convertir a JPG es ${core.MAX_RENDER_PAGES}. Divide el PDF primero.`,
        { name: file.name, pages: pageCount, limit: core.MAX_RENDER_PAGES }
      ),
    };
  }

  if (MODE === "compress" && pageCount > core.MAX_RENDER_PAGES) {
    return {
      ok: false,
      code: "too-many-pages",
      error: tr(
        "pdf.limitCompressPages",
        `"${file.name}" tiene ${pageCount} páginas y el límite para comprimir es ${core.MAX_RENDER_PAGES}. Divide el PDF primero.`,
        { name: file.name, pages: pageCount, limit: core.MAX_RENDER_PAGES }
      ),
    };
  }

  if ((MODE === "split" || MODE === "merge") && pageCount > core.MAX_PDF_PAGES) {
    return {
      ok: false,
      code: "too-many-pages",
      error: tr(
        "pdf.limitPdfPages",
        `“${file.name}” tiene ${pageCount} páginas y el límite es ${core.MAX_PDF_PAGES}.`,
        { name: file.name, pages: pageCount, limit: core.MAX_PDF_PAGES }
      ),
    };
  }

  if (MODE === "merge" && totalPages() + pageCount > core.MAX_PDF_PAGES) {
    return {
      ok: false,
      code: "too-many-pages",
      error: tr(
        "pdf.limitMergeTotal",
        `La unión superaría el límite de ${core.MAX_PDF_PAGES} páginas. Quita algún documento o divide el PDF antes de unirlo.`,
        { limit: core.MAX_PDF_PAGES }
      ),
    };
  }

  return {
    ok: true,
    item: {
      id: `pdf-${(itemSeq += 1)}`,
      kind: "pdf",
      name: file.name,
      size: file.size,
      bytes,
      pageCount,
    },
  };
}

async function inspectImage(file) {
  if (!ImageTools) {
    return {
      ok: false,
      code: "no-image-engine",
      error: tr(
        "pdf.noImageEngine",
        "No se cargó el motor de imágenes. Recarga la página."
      ),
    };
  }

  const check = await ImageTools.validateFile(file);
  if (!check.ok) return check;

  if (check.mime === "image/webp") {
    return {
      ok: false,
      code: "unsupported",
      error: tr(
        "pdf.webpUnsupported",
        `“${file.name}” es WebP. Para crear un PDF acepta solo JPG o PNG; convierte la imagen primero si lo necesitas.`,
        { name: file.name }
      ),
    };
  }

  let bytes;
  try {
    bytes = new Uint8Array(await file.arrayBuffer());
  } catch (_) {
    return {
      ok: false,
      code: "unreadable",
      error: tr(
        "pdf.unreadableFile",
        `No se pudo leer “${file.name}”. Comprueba que el archivo siga disponible.`,
        { name: file.name }
      ),
    };
  }

  const thumbUrl = URL.createObjectURL(file);
  try {
    const image = await ImageTools.loadImage(thumbUrl);
    const dimensions = ImageTools.imageDimensions(image);
    if (!dimensions) {
      throw new Error(tr("pdf.invalidDimensions", "Dimensiones no válidas"));
    }
    const pixels = dimensions.width * dimensions.height;
    if (pixels > core.MAX_IMAGE_PIXELS) {
      safeRevoke(thumbUrl);
      const megapixels = (pixels / 1_000_000).toFixed(1);
      return {
        ok: false,
        code: "too-many-pixels",
        error: tr(
          "pdf.tooManyPixels",
          `“${file.name}” mide ${megapixels} MP y el límite es ${core.MAX_IMAGE_PIXELS / 1_000_000} MP por imagen. Redúcela antes de crear el PDF.`,
          {
            name: file.name,
            megapixels,
            limit: core.MAX_IMAGE_PIXELS / 1_000_000,
          }
        ),
      };
    }
    return {
      ok: true,
      item: {
        id: `img-${(itemSeq += 1)}`,
        kind: "image",
        name: file.name,
        size: file.size,
        bytes,
        mime: check.mime,
        width: dimensions.width,
        height: dimensions.height,
        thumbUrl,
      },
    };
  } catch (_) {
    safeRevoke(thumbUrl);
    return {
      ok: false,
      code: "unreadable-image",
      error: tr(
        "pdf.imageDecode",
        `“${file.name}” no se pudo decodificar como imagen JPG o PNG. El archivo puede estar dañado.`,
        { name: file.name }
      ),
    };
  }
}

async function handleFiles(fileListValue) {
  if (state.busy) return;
  const files = Array.from(fileListValue || []);
  if (!files.length) return;

  clearError();
  clearResult();

  let incoming = files;
  if (!CONFIG.multiple && incoming.length > 1) {
    showToast(
      tr(
        "pdf.oneFileOnly",
        "Esta herramienta procesa un archivo cada vez. Se usará el primero."
      ),
      { error: true }
    );
    incoming = incoming.slice(0, 1);
  }

  if (CONFIG.multiple) {
    const remaining = CONFIG.maxFiles - state.items.length;
    if (remaining <= 0) {
      showError(
        MODE === "images"
          ? tr(
              "pdf.maxImages",
              `Ya tienes ${core.MAX_IMAGES} imágenes. Quita alguna antes de añadir más.`,
              { limit: core.MAX_IMAGES }
            )
          : tr(
              "pdf.maxFiles",
              `Ya tienes ${core.MAX_FILES} PDF. Quita alguno antes de añadir más.`,
              { limit: core.MAX_FILES }
            )
      );
      return;
    }
    if (incoming.length > remaining) {
      showToast(
        tr(
          "pdf.remainingFiles",
          `Solo caben ${remaining} archivo(s) más en esta operación.`,
          { remaining }
        ),
        { error: true }
      );
      incoming = incoming.slice(0, remaining);
    }
  }

  const accepted = [];
  let firstError = null;
  const baseSize = CONFIG.multiple ? totalSize() : 0;
  const basePages = MODE === "merge" ? totalPages() : 0;

  for (const file of incoming) {
    let result;
    try {
      result = isPdfMode ? await inspectPdf(file) : await inspectImage(file);
    } catch (error) {
      result = {
        ok: false,
        code: "unexpected",
        error: `No se pudo inspeccionar “${file.name}”. ${error.message || ""}`.trim(),
      };
    }

    if (!result.ok) {
      if (!firstError) firstError = result.error;
      continue;
    }

    if (baseSize + accepted.reduce((sum, item) => sum + item.size, 0) + result.item.size >
      core.MAX_TOTAL_BYTES) {
      if (!firstError) {
        firstError = tr(
          "pdf.totalLimit",
          `La selección supera el límite de ${core.MAX_TOTAL_BYTES / (1024 * 1024)} MB en total. Quita algún archivo o usa documentos más pequeños.`,
          { limit: core.MAX_TOTAL_BYTES / (1024 * 1024) }
        );
      }
      if (result.item.thumbUrl) safeRevoke(result.item.thumbUrl);
      continue;
    }

    if (MODE === "merge" && basePages + accepted.reduce((sum, item) => sum + item.pageCount, 0) +
      result.item.pageCount > core.MAX_PDF_PAGES) {
      if (!firstError) {
        firstError = tr(
          "pdf.mergeLimit",
          `La unión supera el límite de ${core.MAX_PDF_PAGES} páginas. Quita algún documento o divide el PDF antes de unirlo.`,
          { limit: core.MAX_PDF_PAGES }
        );
      }
      continue;
    }

    accepted.push(result.item);
  }

  if (accepted.length) {
    if (!CONFIG.multiple) {
      state.items.forEach((item) => safeRevoke(item.thumbUrl));
      state.items = accepted;
    } else {
      state.items.push(...accepted);
    }
    if (MODE === "split" && rangeInput) {
      rangeInput.value = core.allPagesRange(state.items[0].pageCount);
    }
    syncUI();
  }

  if (firstError) {
    showError(firstError);
  } else if (accepted.length < incoming.length) {
    showToast(
      tr(
        "pdf.someFilesSkipped",
        "Algunos archivos no se añadieron. Revisa el aviso."
      ),
      { error: true }
    );
  }
}

// ---------------------------------------------------------------------------
// Lista de archivos
// ---------------------------------------------------------------------------

function makeActionButton(label, title, disabled, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "ghost-btn small pdf-file-action";
  button.textContent = label;
  button.title = title;
  button.setAttribute("aria-label", title);
  button.disabled = disabled || state.busy;
  button.addEventListener("click", onClick);
  return button;
}

function updateFileList() {
  if (!fileList) return;
  fileList.replaceChildren();

  state.items.forEach((item, index) => {
    const li = document.createElement("li");
    li.className = "pdf-file-item";
    li.dataset.id = item.id;

    const icon = document.createElement("span");
    icon.className = "pdf-file-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = item.kind === "pdf" ? "PDF" : "IMG";

    const info = document.createElement("div");
    info.className = "pdf-file-info";
    const name = document.createElement("span");
    name.className = "pdf-file-name";
    name.textContent = item.name;
    const meta = document.createElement("span");
    meta.className = "pdf-file-meta";
    if (item.kind === "pdf") {
      meta.textContent = `${formatBytes(item.size)} · ${pagesLabel(item.pageCount)}`;
    } else {
      meta.textContent =
        `${formatBytes(item.size)} · ${item.width} × ${item.height} px · ` +
        (item.mime === "image/png" ? "PNG" : "JPG");
    }
    info.append(name, meta);

    const actions = document.createElement("div");
    actions.className = "pdf-file-actions";

    if (CONFIG.multiple && state.items.length > 1) {
      actions.append(
        makeActionButton(
          "↑",
          tr("pdf.moveUp", "Subir archivo"),
          index === 0,
          () => moveItem(index, index - 1)
        ),
        makeActionButton(
          "↓",
          tr("pdf.moveDown", "Bajar archivo"),
          index === state.items.length - 1,
          () => moveItem(index, index + 1)
        )
      );
    }

    actions.append(
      makeActionButton(
        tr("pdf.remove", "Quitar"),
        tr("pdf.removeNamed", `Quitar ${item.name}`, { name: item.name }),
        false,
        () => removeItem(item.id)
      )
    );

    li.append(icon, info, actions);
    fileList.append(li);
  });

  if (filesSection) filesSection.classList.toggle("hidden", state.items.length === 0);
  if (fileCount) {
    const countLabel = MODE === "images" ? imagesLabel(state.items.length) : fileLabel(state.items.length);
    fileCount.textContent = state.items.length
      ? `${countLabel} · ${formatBytes(totalSize())}`
      : "";
  }
  if (clearAll) clearAll.disabled = state.busy || state.items.length === 0;
}

function moveItem(from, to) {
  if (state.busy) return;
  state.items = core.moveItem(state.items, from, to);
  clearResult();
  syncUI();
}

function removeItem(id) {
  if (state.busy) return;
  const index = state.items.findIndex((item) => item.id === id);
  if (index === -1) return;
  const [removed] = state.items.splice(index, 1);
  safeRevoke(removed.thumbUrl);
  clearResult();
  if (MODE === "split" && rangeInput && state.items[0]) {
    rangeInput.value = core.allPagesRange(state.items[0].pageCount);
  }
  syncUI();
}

// ---------------------------------------------------------------------------
// Vista previa
// ---------------------------------------------------------------------------

function pdfOptions(bytes) {
  const base = new URL("./vendor/pdf/", import.meta.url).href;
  return {
    data: bytes.slice(),
    standardFontDataUrl: `${base}standard_fonts/`,
    cMapUrl: `${base}cmaps/`,
    cMapPacked: true,
    wasmUrl: `${base}wasm/`,
    iccUrl: `${base}iccs/`,
    isEvalSupported: false,
  };
}

async function loadPdfJs(bytes) {
  const task = getDocument(pdfOptions(bytes));
  try {
    return await task.promise;
  } catch (error) {
    try {
      await task.destroy();
    } catch (_) {
      /* La tarea ya estaba destruida. */
    }
    throw error;
  }
}

async function renderPageToCanvas(pdf, pageNumber, targetWidth, maxHeight) {
  const page = await pdf.getPage(pageNumber);
  try {
    const base = page.getViewport({ scale: 1 });
    const maxPixels = 2_500_000;
    const pixelScale = Math.sqrt(maxPixels / (base.width * base.height));
    const scale = Math.min(
      targetWidth / base.width,
      maxHeight / base.height,
      pixelScale
    );
    const viewport = page.getViewport({ scale: Math.max(0.05, scale) });
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(viewport.width));
    canvas.height = Math.max(1, Math.round(viewport.height));
    canvas.className = "pdf-thumb-canvas";
    canvas.setAttribute("aria-hidden", "true");
    const context = canvas.getContext("2d", { alpha: false });
    if (context) {
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, canvas.width, canvas.height);
    }
    await page.render({ canvas, viewport, background: "#ffffff" }).promise;
    return canvas;
  } finally {
    page.cleanup();
  }
}

function previewFigure(canvas, title, meta) {
  const figure = document.createElement("figure");
  figure.className = "pdf-preview-card";
  const frame = document.createElement("div");
  frame.className = "pdf-preview-frame";
  frame.append(canvas);
  const caption = document.createElement("figcaption");
  const strong = document.createElement("strong");
  strong.textContent = title;
  const small = document.createElement("span");
  small.textContent = meta;
  caption.append(strong, small);
  figure.append(frame, caption);
  return figure;
}

function imagePreviewFigure(item) {
  const figure = document.createElement("figure");
  figure.className = "pdf-preview-card";
  const frame = document.createElement("div");
  frame.className = "pdf-preview-frame image-checker";
  const image = document.createElement("img");
  image.src = item.thumbUrl;
  image.alt = `Vista previa de ${item.name}`;
  image.loading = "lazy";
  frame.append(image);
  const caption = document.createElement("figcaption");
  const strong = document.createElement("strong");
  strong.textContent = item.name;
  const small = document.createElement("span");
  small.textContent = `${item.width} × ${item.height} px`;
  caption.append(strong, small);
  figure.append(frame, caption);
  return figure;
}

function noPreviewFigure(message) {
  const figure = document.createElement("figure");
  figure.className = "pdf-preview-card";
  const frame = document.createElement("div");
  frame.className = "pdf-preview-frame pdf-preview-empty";
  frame.textContent = message;
  const caption = document.createElement("figcaption");
  caption.textContent = tr("pdf.previewUnavailable", "Vista previa no disponible");
  figure.append(frame, caption);
  return figure;
}

async function renderPreview() {
  const token = ++state.previewToken;
  cleanupCanvases(previewGrid);
  previewNote.textContent = "";
  if (!state.items.length) {
    previewHint.textContent = "";
    return;
  }

  previewHint.textContent =
    MODE === "merge"
      ? tr(
          "pdf.previewMergeHint",
          "Primera página de cada documento, en el orden actual."
        )
      : MODE === "images"
        ? tr(
            "pdf.previewImagesHint",
            "Cada imagen será una página, en el orden actual."
          )
        : tr(
            "pdf.previewLimitHint",
            `Primeras ${previewLimit} páginas como referencia.`,
            { count: previewLimit }
          );

  if (MODE === "images") {
    state.items.forEach((item) => previewGrid.append(imagePreviewFigure(item)));
    previewNote.textContent = tr(
      "pdf.imagesToPages",
      `${imagesLabel(state.items.length)} → ${pagesLabel(state.items.length)} de PDF.`,
      {
        images: imagesLabel(state.items.length),
        pages: pagesLabel(state.items.length),
      }
    );
    return;
  }

  if (MODE === "merge") {
    for (const item of state.items) {
      if (token !== state.previewToken) return;
      let pdf;
      try {
        pdf = await loadPdfJs(item.bytes);
        if (token !== state.previewToken) {
          await pdf.destroy();
          return;
        }
        const canvas = await renderPageToCanvas(pdf, 1, 180, 250);
        if (token !== state.previewToken) return;
        previewGrid.append(
          previewFigure(canvas, item.name, `${pagesLabel(item.pageCount)} · ${formatBytes(item.size)}`)
        );
      } catch (_) {
        if (token === state.previewToken) {
          previewGrid.append(
            noPreviewFigure(
              tr("pdf.noPreviewItem", `Sin vista previa de ${item.name}`, {
                name: item.name,
              })
            )
          );
        }
      } finally {
        if (pdf) {
          try {
            await pdf.destroy();
          } catch (_) {
            /* Nada que liberar. */
          }
        }
      }
    }
    return;
  }

  const item = state.items[0];
  if (!item) return;
  let pdf;
  try {
    pdf = await loadPdfJs(item.bytes);
    const shown = Math.min(item.pageCount, previewLimit);
    for (let pageNumber = 1; pageNumber <= shown; pageNumber += 1) {
      if (token !== state.previewToken) return;
      const canvas = await renderPageToCanvas(pdf, pageNumber, 140, 210);
      if (token !== state.previewToken) return;
      previewGrid.append(
        previewFigure(
          canvas,
          tr("pdf.previewPage", `Página ${pageNumber}`, { page: pageNumber }),
          ""
        )
      );
      if (pageNumber % 4 === 0) await yieldToUi();
    }
    const allHint =
      MODE === "split"
        ? tr(
            "pdf.previewRangesAll",
            "Los rangos funcionan con todas las páginas."
          )
        : MODE === "compress"
          ? tr(
              "pdf.previewCompressAll",
              "La compresión procesará todas las páginas permitidas."
            )
          : tr(
              "pdf.previewConvertAll",
              "La conversión procesará todas las páginas permitidas."
            );
    previewNote.textContent =
      item.pageCount > shown
        ? tr(
            "pdf.previewPartial",
            `Vista previa de ${shown} de ${pagesLabel(item.pageCount)}. `,
            { shown, pages: pagesLabel(item.pageCount) }
          ) + allHint
        : tr(
            "pdf.previewAll",
            `${pagesLabel(item.pageCount)} en el documento.`,
            { pages: pagesLabel(item.pageCount) }
          );
  } catch (error) {
    if (token === state.previewToken) {
      const info = core.friendlyPdfError(error, item.name);
      previewGrid.append(noPreviewFigure(info.message));
    }
  } finally {
    if (pdf) {
      try {
        await pdf.destroy();
      } catch (_) {
        /* Nada que liberar. */
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Estado de la acción
// ---------------------------------------------------------------------------

function currentRange() {
  const item = state.items[0];
  if (MODE !== "split" || !item) {
    return {
      ok: false,
      pages: [],
      error: tr(
        "pdf.rangeNoPdf",
        "Selecciona un PDF para definir los rangos."
      ),
    };
  }
  return core.parsePageRanges(rangeInput ? rangeInput.value : "", item.pageCount);
}

function updateRangeSummary() {
  if (MODE !== "split" || !rangeSummary) return;
  const item = state.items[0];
  if (!item) {
    rangeSummary.textContent = tr(
      "pdf.selectPdf",
      "Selecciona un PDF para ver sus páginas."
    );
    rangeSummary.classList.remove("is-error");
    return;
  }
  const parsed = currentRange();
  if (!parsed.ok) {
    rangeSummary.textContent = parsed.error;
    rangeSummary.classList.add("is-error");
    return;
  }
  rangeSummary.classList.remove("is-error");
  const repeated = parsed.pages.length !== new Set(parsed.pages).size;
  const suffix = repeated
    ? tr("pdf.rangeRepeated", " (con repeticiones)")
    : "";
  rangeSummary.textContent =
    tr(
      "pdf.rangeSummary",
      `${parsed.pages.length} de ${pagesLabel(item.pageCount)}: `,
      { selected: parsed.pages.length, pages: pagesLabel(item.pageCount) }
    ) +
    core.pagesToRangeText(parsed.pages) +
    suffix;
}

function canProcess() {
  if (state.busy || !state.libsReady || !state.items.length) return false;
  if (MODE === "merge") return state.items.length >= 2;
  if (MODE === "split") return currentRange().ok;
  return true;
}

function updateActionHint() {
  if (!actionHint) return;
  actionHint.classList.remove("is-error");

  if (MODE === "merge") {
    if (state.items.length === 0) {
      actionHint.textContent = tr("pdf.addTwo", "Añade al menos dos PDF.");
    } else if (state.items.length === 1) {
      actionHint.textContent = tr(
        "pdf.addAnother",
        "Añade otro PDF para activar la unión."
      );
    } else {
      actionHint.textContent = tr(
        "pdf.mergeReady",
        `${state.items.length} documentos · ${pagesLabel(totalPages())}. El orden de la lista será el orden final.`,
        {
          documents: state.items.length,
          pages: pagesLabel(totalPages()),
        }
      );
    }
  } else if (MODE === "split") {
    const item = state.items[0];
    if (!item) {
      actionHint.textContent = tr(
        "pdf.selectPdfExtract",
        "Selecciona un PDF para activar la extracción."
      );
    } else {
      const parsed = currentRange();
      if (!parsed.ok) {
        actionHint.textContent = parsed.error;
        actionHint.classList.add("is-error");
      } else {
        actionHint.textContent = tr(
          "pdf.splitReady",
          `Selección: ${parsed.pages.length} de ${pagesLabel(item.pageCount)}.`,
          { selected: parsed.pages.length, pages: pagesLabel(item.pageCount) }
        );
      }
    }
  } else if (MODE === "images") {
    actionHint.textContent = state.items.length
      ? tr(
          "pdf.imagesToPages",
          `${imagesLabel(state.items.length)} → ${pagesLabel(state.items.length)} de PDF.`,
          {
            images: imagesLabel(state.items.length),
            pages: pagesLabel(state.items.length),
          }
        )
      : tr("pdf.imagesNeedOne", "Añade al menos una imagen JPG o PNG.");
  } else if (MODE === "jpg") {
    const item = state.items[0];
    actionHint.textContent = item
      ? tr(
          "pdf.jpgHint",
          `${pagesLabel(item.pageCount)} · el resultado se descargará como JPG o ZIP.`,
          { pages: pagesLabel(item.pageCount) }
        )
      : tr("pdf.jpgSelect", "Selecciona un PDF para activar la conversión.");
  } else if (MODE === "compress") {
    const item = state.items[0];
    actionHint.textContent = item
      ? tr(
          "pdf.compressHint",
          `${pagesLabel(item.pageCount)} · se rasterizarán a JPG y se reconstruirá el PDF.`,
          { pages: pagesLabel(item.pageCount) }
        )
      : tr(
          "pdf.compressSelect",
          "Selecciona un PDF para activar la compresión."
        );
  }

  if (processBtn) processBtn.disabled = state.busy || !canProcess();
}

function syncUI() {
  if (filesSection) filesSection.classList.toggle("hidden", state.items.length === 0);
  if (workspace) workspace.classList.toggle("hidden", state.items.length === 0);
  if (controls) controls.classList.toggle("hidden", state.items.length === 0);
  updateFileList();
  updateSizeWarning();
  updateRangeSummary();
  updateActionHint();
  renderPreview();
  if (state.items.length === 0) {
    previewHint.textContent = "";
    previewNote.textContent = "";
  }
}

// ---------------------------------------------------------------------------
// Resultados
// ---------------------------------------------------------------------------

function resultUrl(blob) {
  return URL.createObjectURL(blob);
}

function showPdfResult({ blob, name, beforeBytes, beforeDetail, afterDetail, note }) {
  const url = resultUrl(blob);
  state.result = {
    url,
    name,
    kind: "pdf",
    beforeBytes,
    afterBytes: blob.size,
  };
  if (outBefore) outBefore.textContent = formatBytes(beforeBytes);
  if (outBeforeDetail) outBeforeDetail.textContent = beforeDetail;
  if (outAfter) outAfter.textContent = formatBytes(blob.size);
  if (outAfterDetail) outAfterDetail.textContent = afterDetail;

  if (outSaved) {
    const diff = beforeBytes > 0 ? ((beforeBytes - blob.size) / beforeBytes) * 100 : 0;
    outSaved.classList.remove("is-increase");
    if (Math.abs(diff) < 0.05) {
      outSaved.textContent = tr("pdf.sameSize", "Mismo tamaño");
    } else if (diff > 0) {
      outSaved.textContent = tr("pdf.less", `${diff.toFixed(1)} % menos`, {
        value: diff.toFixed(1),
      });
    } else {
      outSaved.textContent = tr(
        "pdf.more",
        `${Math.abs(diff).toFixed(1)} % más`,
        { value: Math.abs(diff).toFixed(1) }
      );
      outSaved.classList.add("is-increase");
    }
  }

  if (resultNote) resultNote.textContent = note;
  if (downloadBtn) {
    downloadBtn.textContent = tr("pdf.downloadPdf", "Descargar PDF");
    downloadBtn.disabled = false;
  }
  if (resultSection) {
    resultSection.classList.remove("hidden");
    resultSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function showJpgResult({ blob, name, beforeBytes, pageCount, zip, previewItems, clamped }) {
  const url = resultUrl(blob);
  state.result = {
    url,
    name,
    kind: zip ? "zip" : "jpg",
    beforeBytes,
    afterBytes: blob.size,
  };

  if (outBefore) outBefore.textContent = formatBytes(beforeBytes);
  if (outBeforeDetail) {
    outBeforeDetail.textContent = tr(
      "pdf.pagesInput",
      `${pagesLabel(pageCount)} de entrada`,
      { pages: pagesLabel(pageCount) }
    );
  }
  if (outAfter) outAfter.textContent = formatBytes(blob.size);
  if (outAfterDetail) {
    outAfterDetail.textContent = zip
      ? tr(
          "pdf.jpgsInZip",
          `${previewItems.length} JPG en un ZIP`,
          { count: previewItems.length }
        )
      : previewItems[0]
        ? tr(
            "pdf.jpgDimensions",
            `${previewItems[0].width} × ${previewItems[0].height} px`,
            {
              width: previewItems[0].width,
              height: previewItems[0].height,
            }
          )
        : tr("pdf.oneJpg", "1 JPG");
  }
  if (outSaved) {
    const diff = beforeBytes > 0 ? ((beforeBytes - blob.size) / beforeBytes) * 100 : 0;
    outSaved.classList.remove("is-increase");
    if (Math.abs(diff) < 0.05) {
      outSaved.textContent = tr("pdf.sameSize", "Mismo tamaño");
    } else if (diff > 0) {
      outSaved.textContent = tr("pdf.less", `${diff.toFixed(1)} % menos`, {
        value: diff.toFixed(1),
      });
    }
    else {
      outSaved.textContent = tr(
        "pdf.more",
        `${Math.abs(diff).toFixed(1)} % más`,
        { value: Math.abs(diff).toFixed(1) }
      );
      outSaved.classList.add("is-increase");
    }
  }

  if (resultPreviews) {
    resultPreviews.replaceChildren();
    previewItems.forEach((item, index) => {
      const figure = document.createElement("figure");
      figure.className = "pdf-result-preview";
      const image = document.createElement("img");
      image.src = item.previewUrl;
      image.alt = tr(
        "pdf.jpgAlt",
        `Página ${index + 1} convertida a JPG`,
        { page: index + 1 }
      );
      image.loading = "lazy";
      const caption = document.createElement("figcaption");
      caption.textContent = tr(
        "pdf.jpgCaption",
        `Página ${index + 1} · ${item.width} × ${item.height} px`,
        { page: index + 1, width: item.width, height: item.height }
      );
      figure.append(image, caption);
      resultPreviews.append(figure);
    });
    resultPreviews.classList.toggle("hidden", previewItems.length === 0);
  }

  if (resultNote) {
    const clampedNote = clamped
      ? tr(
          "pdf.jpgZipClamped",
          "Algunas páginas se redujeron automáticamente para no superar el límite de píxeles. "
        )
      : "";
    resultNote.textContent = zip
      ? tr(
          "pdf.jpgZipNote",
          "Se generó un ZIP con un JPG por página. El ZIP no recomprime las imágenes. " +
            clampedNote +
            "Esta conversión no aplica OCR.",
          { clamped: clampedNote }
        )
      : tr(
          "pdf.jpgSingleNote",
          "Se generó un JPG con el aspecto renderizado de la página. No conserva texto seleccionable ni enlaces. El fondo se pintó en blanco."
        );
  }
  if (downloadBtn) {
    downloadBtn.textContent = zip
      ? tr("pdf.downloadZip", "Descargar ZIP")
      : tr("pdf.downloadJpg", "Descargar JPG");
    downloadBtn.disabled = false;
  }
  if (resultSection) {
    resultSection.classList.remove("hidden");
    resultSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

function operationError(error, filename) {
  if (error && error.userMessage) return error.userMessage;
  const info = core.friendlyPdfError(error, filename);
  if (info.code !== "unknown") return info.message;
  return tr(
    "pdf.operationFailed",
    `No se pudo completar la operación con “${filename}”. El archivo puede estar dañado o ser demasiado complejo para este navegador.`,
    { name: filename }
  );
}

// ---------------------------------------------------------------------------
// Operaciones
// ---------------------------------------------------------------------------

async function mergePdfs(items) {
  const out = await PDFDocument.create();
  out.setProducer("FasTools");
  out.setCreator("FasTools");
  const total = items.length;

  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    setProgress(
      5 + (index / total) * 85,
      tr(
        "pdf.readingDocument",
        `Leyendo ${index + 1} de ${total}: ${item.name}`,
        { current: index + 1, total, name: item.name }
      )
    );
    await yieldToUi();

    let source;
    try {
      source = await PDFDocument.load(item.bytes, { updateMetadata: false });
    } catch (error) {
      throw Object.assign(new Error("PDF ilegible"), {
        userMessage: operationError(error, item.name),
      });
    }

    const pages = await out.copyPages(source, source.getPageIndices());
    pages.forEach((page) => out.addPage(page));
    setProgress(
      5 + ((index + 1) / total) * 85,
      tr(
        "pdf.documentAdded",
        `Documento ${index + 1} de ${total} añadido`,
        { current: index + 1, total }
      )
    );
    await yieldToUi();
  }

  setProgress(94, tr("pdf.savingMerged", "Guardando el PDF unido…"));
  await yieldToUi();
  const bytes = await out.save({ useObjectStreams: true });
  const blob = new Blob([bytes], { type: "application/pdf" });
  setProgress(100, tr("pdf.mergedDone", "PDF unido"));
  return {
    blob,
    name: core.mergedPdfName(),
    beforeBytes: totalSize(),
    beforeDetail: `${fileLabel(items.length)} · ${pagesLabel(totalPages())}`,
    afterDetail: tr(
      "pdf.mergeFinalDetail",
      `${pagesLabel(totalPages())} en el documento final`,
      { pages: pagesLabel(totalPages()) }
    ),
    note: tr(
      "pdf.mergeNote",
      "Unir no comprime: el resultado puede pesar igual o más que la suma de los originales. Se copiaron las páginas visibles; formularios, marcadores, firmas y adjuntos pueden no conservarse. Revisa el PDF antes de usarlo en un trámite importante."
    ),
  };
}

async function splitPdf(item) {
  const parsed = currentRange();
  if (!parsed.ok) {
    throw Object.assign(new Error("Rango inválido"), { userMessage: parsed.error });
  }

  let source;
  try {
    source = await PDFDocument.load(item.bytes, { updateMetadata: false });
  } catch (error) {
    throw Object.assign(new Error("PDF ilegible"), {
      userMessage: operationError(error, item.name),
    });
  }

  const out = await PDFDocument.create();
  out.setProducer("FasTools");
  out.setCreator("FasTools");
  const total = parsed.pages.length;

  for (let index = 0; index < total; index += 1) {
    const pageNumber = parsed.pages[index];
    const [page] = await out.copyPages(source, [pageNumber - 1]);
    out.addPage(page);
    setProgress(
      5 + ((index + 1) / total) * 85,
      tr(
        "pdf.copyingPage",
        `Copiando página ${pageNumber} (${index + 1} de ${total})`,
        { page: pageNumber, current: index + 1, total }
      )
    );
    await yieldToUi();
  }

  setProgress(
    94,
    tr("pdf.savingSplit", "Guardando el PDF con las páginas elegidas…")
  );
  await yieldToUi();
  const bytes = await out.save({ useObjectStreams: true });
  const blob = new Blob([bytes], { type: "application/pdf" });
  setProgress(100, tr("pdf.splitDone", "Páginas extraídas"));
  return {
    blob,
    name: core.splitPdfName(item.name),
    beforeBytes: item.size,
    beforeDetail: tr(
      "pdf.splitBeforeDetail",
      `${pagesLabel(item.pageCount)} de origen · ${total} seleccionadas`,
      { pages: pagesLabel(item.pageCount), selected: total }
    ),
    afterDetail: tr(
      "pdf.splitAfterDetail",
      `${pagesLabel(total)} en el PDF final`,
      { pages: pagesLabel(total) }
    ),
    note: tr(
      "pdf.splitNote",
      "La extracción no recomprime las imágenes ni las fuentes: el peso baja porque hay menos páginas, no porque se aplique compresión. El orden sigue los rangos escritos. Marcadores, formularios y firmas pueden no conservarse."
    ),
  };
}

async function imagesToPdf(items) {
  const out = await PDFDocument.create();
  out.setProducer("FasTools");
  out.setCreator("FasTools");
  const total = items.length;
  const sizeMode = pageSize ? pageSize.value : "a4";

  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    setProgress(
      5 + (index / total) * 85,
      tr(
        "pdf.embeddingImage",
        `Incrustando ${index + 1} de ${total}: ${item.name}`,
        { current: index + 1, total, name: item.name }
      )
    );
    await yieldToUi();

    let embedded;
    try {
      embedded =
        item.mime === "image/png"
          ? await out.embedPng(item.bytes)
          : await out.embedJpg(item.bytes);
    } catch (error) {
      throw Object.assign(new Error("image not supported"), {
        userMessage: tr(
          "pdf.imageEmbedFailed",
          `“${item.name}” no se pudo incrustar en el PDF. El archivo puede usar una variante de PNG o JPG no compatible.`,
          { name: item.name }
        ),
      });
    }

    const plan = core.imagePagePlan(item.width, item.height, sizeMode, 24);
    if (!plan) {
      throw Object.assign(new Error("Dimensiones no válidas"), {
        userMessage: tr(
          "pdf.invalidDimensionsItem",
          `“${item.name}” no tiene dimensiones válidas.`,
          { name: item.name }
        ),
      });
    }

    const page = out.addPage([plan.pageWidth, plan.pageHeight]);
    page.drawImage(embedded, {
      x: plan.x,
      y: plan.y,
      width: plan.drawWidth,
      height: plan.drawHeight,
    });
    setProgress(
      5 + ((index + 1) / total) * 85,
      tr(
        "pdf.imagePlaced",
        `Imagen ${index + 1} de ${total} colocada`,
        { current: index + 1, total }
      )
    );
    await yieldToUi();
  }

  setProgress(94, tr("pdf.savingImagesPdf", "Guardando el PDF…"));
  await yieldToUi();
  const bytes = await out.save({ useObjectStreams: true });
  const blob = new Blob([bytes], { type: "application/pdf" });
  setProgress(100, tr("pdf.imagesPdfDone", "PDF creado"));
  const sizeLabel =
    sizeMode === "image"
      ? tr("pdf.sizeEachImage", "tamaño de cada imagen")
      : sizeMode === "a4-landscape"
        ? tr("pdf.sizeA4Landscape", "A4 horizontal")
        : tr("pdf.sizeA4Portrait", "A4 vertical");
  return {
    blob,
    name: core.imagesPdfName(items),
    beforeBytes: totalSize(),
    beforeDetail: `${imagesLabel(items.length)} · ${pagesLabel(items.length)}`,
    afterDetail: tr(
      "pdf.imagesPdfDetail",
      `${pagesLabel(items.length)} · ${sizeLabel}`,
      { pages: pagesLabel(items.length), size: sizeLabel }
    ),
    note: tr(
      "pdf.imagesNote",
      "Cada imagen se incrustó como JPG o PNG; no se recomprime a JPG. El PDF no incluye OCR, texto editable ni numeración. La transparencia del PNG se conserva, aunque el visor puede mostrarla sobre un fondo distinto."
    ),
  };
}

function canvasToBlob(canvas, type, quality) {
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), type, quality);
  });
}

async function pdfToJpg(item) {
  const requestedScale = Number(renderScale ? renderScale.value : 1.5) || 1.5;
  const quality = Math.max(0.6, Math.min(0.95, Number(jpgQuality ? jpgQuality.value : 85) / 100));
  let pdf;
  try {
    pdf = await loadPdfJs(item.bytes);
  } catch (error) {
    throw Object.assign(new Error("PDF ilegible"), {
      userMessage: operationError(error, item.name),
    });
  }

  const pageCount = pdf.numPages;
  if (pageCount > core.MAX_RENDER_PAGES) {
    await pdf.destroy();
    throw Object.assign(new Error("Demasiadas páginas"), {
      userMessage: tr(
        "pdf.jpgPageLimit",
        `“${item.name}” tiene ${pageCount} páginas y el límite es ${core.MAX_RENDER_PAGES}. Divide el documento antes de convertirlo.`,
        { name: item.name, pages: pageCount, limit: core.MAX_RENDER_PAGES }
      ),
    });
  }

  const files = [];
  const previewItems = [];
  let clamped = false;

  try {
    for (let pageNumber = 1; pageNumber <= pageCount; pageNumber += 1) {
      setProgress(
        5 + ((pageNumber - 1) / pageCount) * 85,
        tr(
          "pdf.renderingPage",
          `Renderizando página ${pageNumber} de ${pageCount}…`,
          { page: pageNumber, total: pageCount }
        )
      );
      await yieldToUi();

      const page = await pdf.getPage(pageNumber);
      let canvas = null;
      try {
        const base = page.getViewport({ scale: 1 });
        const plan = core.clampRenderScale(base.width, base.height, requestedScale);
        if (plan.clamped) clamped = true;
        const viewport = page.getViewport({ scale: plan.scale });
        canvas = document.createElement("canvas");
        canvas.width = plan.width;
        canvas.height = plan.height;
        const context = canvas.getContext("2d", { alpha: false });
        if (!context) {
          throw new Error(tr("pdf.canvasMissing", "Canvas no disponible"));
        }
        context.fillStyle = "#ffffff";
        context.fillRect(0, 0, canvas.width, canvas.height);
        await page.render({
          canvas,
          viewport,
          background: "#ffffff",
          intent: "display",
        }).promise;

        const blob = await canvasToBlob(canvas, "image/jpeg", quality);
        if (!blob) {
          throw new Error(
            tr("pdf.jpgEncode", "El navegador no pudo codificar el JPG")
          );
        }

        const name = core.jpgPageName(item.name, pageNumber, pageCount);
        const data = new Uint8Array(await blob.arrayBuffer());
        const previewUrl = URL.createObjectURL(blob);
        state.resultPreviewUrls.push(previewUrl);
        files.push({ name, data });
        previewItems.push({
          previewUrl,
          width: canvas.width,
          height: canvas.height,
        });
      } finally {
        if (page) page.cleanup();
        if (canvas) {
          canvas.width = 0;
          canvas.height = 0;
        }
      }

      setProgress(
        5 + (pageNumber / pageCount) * 85,
        tr(
          "pdf.pageConverted",
          `Página ${pageNumber} de ${pageCount} convertida`,
          { page: pageNumber, total: pageCount }
        )
      );
    }
  } finally {
    try {
      await pdf.destroy();
    } catch (_) {
      /* Nada que liberar. */
    }
  }

  setProgress(93, tr("pdf.preparingDownload", "Preparando la descarga…"));
  await yieldToUi();

  if (files.length === 1) {
    const blob = new Blob([files[0].data], { type: "image/jpeg" });
    setProgress(100, tr("pdf.jpgReady", "JPG listo"));
    return {
      blob,
      name: files[0].name,
      beforeBytes: item.size,
      pageCount,
      zip: false,
      previewItems,
      clamped,
    };
  }

  const zipBytes = core.zipStore(files);
  const blob = new Blob([zipBytes], { type: "application/zip" });
  setProgress(100, tr("pdf.zipReady", "ZIP listo"));
  return {
    blob,
    name: core.zipName(item.name),
    beforeBytes: item.size,
    pageCount,
    zip: true,
    previewItems,
    clamped,
  };
}

async function compressPdf(item) {
  const requestedScale = Number(renderScale ? renderScale.value : 1.5) || 1.5;
  const quality = Math.max(0.4, Math.min(0.95, Number(jpgQuality ? jpgQuality.value : 75) / 100));
  const qualityPercent = Math.round(quality * 100);

  let pdf;
  try {
    pdf = await loadPdfJs(item.bytes);
  } catch (error) {
    throw Object.assign(new Error("PDF ilegible"), {
      userMessage: operationError(error, item.name),
    });
  }

  const pageCount = pdf.numPages;
  if (pageCount > core.MAX_RENDER_PAGES) {
    await pdf.destroy();
    throw Object.assign(new Error("Demasiadas páginas"), {
      userMessage: tr(
        "pdf.compressPageLimit",
        `"${item.name}" tiene ${pageCount} páginas y el límite para comprimir es ${core.MAX_RENDER_PAGES}. Divide el documento antes de comprimirlo.`,
        { name: item.name, pages: pageCount, limit: core.MAX_RENDER_PAGES }
      ),
    });
  }

  const out = await PDFDocument.create();
  out.setProducer("FasTools");
  out.setCreator("FasTools");
  let clamped = false;

  try {
    for (let pageNumber = 1; pageNumber <= pageCount; pageNumber += 1) {
      setProgress(
        5 + ((pageNumber - 1) / pageCount) * 85,
        tr(
          "pdf.compressingPage",
          `Comprimiendo página ${pageNumber} de ${pageCount}.`,
          { page: pageNumber, total: pageCount }
        )
      );
      await yieldToUi();

      const page = await pdf.getPage(pageNumber);
      let canvas = null;
      try {
        const base = page.getViewport({ scale: 1 });
        const plan = core.clampRenderScale(base.width, base.height, requestedScale);
        if (plan.clamped) clamped = true;
        const viewport = page.getViewport({ scale: plan.scale });
        canvas = document.createElement("canvas");
        canvas.width = plan.width;
        canvas.height = plan.height;
        const context = canvas.getContext("2d", { alpha: false });
        if (!context) {
          throw new Error(tr("pdf.canvasMissing", "Canvas no disponible"));
        }
        context.fillStyle = "#ffffff";
        context.fillRect(0, 0, canvas.width, canvas.height);
        await page.render({
          canvas,
          viewport,
          background: "#ffffff",
          intent: "display",
        }).promise;

        const blob = await canvasToBlob(canvas, "image/jpeg", quality);
        if (!blob) {
          throw new Error(
            tr("pdf.jpgEncode", "El navegador no pudo codificar el JPG")
          );
        }
        const data = new Uint8Array(await blob.arrayBuffer());
        const embedded = await out.embedJpg(data);
        const outPage = out.addPage([base.width, base.height]);
        outPage.drawImage(embedded, {
          x: 0,
          y: 0,
          width: base.width,
          height: base.height,
        });
      } finally {
        if (page) page.cleanup();
        if (canvas) {
          canvas.width = 0;
          canvas.height = 0;
        }
      }

      setProgress(
        5 + (pageNumber / pageCount) * 85,
        tr(
          "pdf.pageCompressed",
          `Página ${pageNumber} de ${pageCount} comprimida`,
          { page: pageNumber, total: pageCount }
        )
      );
    }
  } finally {
    try {
      await pdf.destroy();
    } catch (_) {
      /* Nada que liberar. */
    }
  }

  setProgress(
    94,
    tr("pdf.savingCompressed", "Guardando el PDF comprimido.")
  );
  await yieldToUi();
  const bytes = await out.save({ useObjectStreams: true });
  const blob = new Blob([bytes], { type: "application/pdf" });
  setProgress(100, tr("pdf.compressDone", "PDF comprimido"));
  const clampedNote = clamped
    ? tr(
        "pdf.clampedNote",
        " Algunas páginas se redujeron para no superar el límite de píxeles."
      )
    : "";
  return {
    blob,
    name: core.compressedPdfName(item.name),
    beforeBytes: item.size,
    beforeDetail: tr(
      "pdf.compressOriginDetail",
      `${pagesLabel(pageCount)} de origen`,
      { pages: pagesLabel(pageCount) }
    ),
    afterDetail: tr(
      "pdf.compressDetail",
      `${pagesLabel(pageCount)} · JPG al ${qualityPercent} %`,
      { pages: pagesLabel(pageCount), quality: qualityPercent }
    ),
    note: tr(
      "pdf.compressNote",
      "Para reducir el peso, cada página se rasteriza a JPG y se reconstruye el PDF. Se pierden el texto seleccionable, los enlaces, los formularios y los metadatos. Si el resultado pesa más, baja la calidad o la resolución: los PDF que ya venían muy comprimidos apenas mejoran y pueden aumentar de tamaño." +
        clampedNote,
      { clamped: clampedNote }
    ),
  };
}

async function processFiles() {
  if (!canProcess()) return;
  clearError();
  clearResult();
  setBusy(true);
  hideProgress();
  setProgress(1, tr("pdf.preparing", "Preparando…"));

  const items = state.items.slice();
  const first = items[0];
  const runId = ++state.runId;
  await yieldToUi();

  try {
    let result;
    if (MODE === "merge") {
      result = await mergePdfs(items);
      if (runId !== state.runId) return;
      showPdfResult(result);
    } else if (MODE === "split") {
      result = await splitPdf(first);
      if (runId !== state.runId) return;
      showPdfResult(result);
    } else if (MODE === "images") {
      result = await imagesToPdf(items);
      if (runId !== state.runId) return;
      showPdfResult(result);
    } else if (MODE === "jpg") {
      result = await pdfToJpg(first);
      if (runId !== state.runId) return;
      showJpgResult(result);
    } else if (MODE === "compress") {
      result = await compressPdf(first);
      if (runId !== state.runId) return;
      showPdfResult(result);
    }
    if (runId === state.runId) {
      showToast(
        tr(
          "pdf.resultReady",
          "Resultado listo. La descarga no envía nada a internet."
        )
      );
    }
  } catch (error) {
    if (runId === state.runId) {
      showError(
        operationError(
          error,
          first ? first.name : tr("pdf.defaultDocument", "el documento")
        )
      );
      if (progressLabel) {
        progressLabel.textContent = tr(
          "pdf.notCompleted",
          "No se pudo completar"
        );
      }
      cleanupCanvases(resultPreviews);
      state.resultPreviewUrls.forEach(safeRevoke);
      state.resultPreviewUrls = [];
    }
  } finally {
    if (runId === state.runId) setBusy(false);
  }
}

// ---------------------------------------------------------------------------
// Eventos
// ---------------------------------------------------------------------------

function bindDropzone() {
  if (!dropzone || !fileInput) return;
  fileInput.accept = CONFIG.accept;
  fileInput.multiple = CONFIG.multiple;
  fileInput.toggleAttribute("multiple", CONFIG.multiple);

  dropzone.addEventListener("click", (event) => {
    if (event.target === fileInput || state.busy) return;
    fileInput.click();
  });
  dropzone.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    if (!state.busy) fileInput.click();
  });
  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      if (!state.busy) dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });
  dropzone.addEventListener("drop", (event) => {
    if (state.busy) return;
    const dropped = event.dataTransfer && event.dataTransfer.files;
    if (dropped && dropped.length) handleFiles(dropped);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length) handleFiles(fileInput.files);
    fileInput.value = "";
  });
}

function bindControls() {
  if (clearAll) clearAll.addEventListener("click", resetAll);
  if (againBtn) againBtn.addEventListener("click", resetAll);
  if (errorClose) {
    errorClose.addEventListener("click", () => {
      clearError();
    });
  }

  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      if (!state.result) return;
      triggerDownload(state.result.url, state.result.name);
      showToast(`Descargando ${state.result.name}`);
    });
  }

  if (processBtn) processBtn.addEventListener("click", processFiles);

  if (rangeInput) {
    rangeInput.addEventListener("input", () => {
      clearResult();
      updateRangeSummary();
      updateActionHint();
    });
  }

  if (rangePresets) {
    rangePresets.addEventListener("click", (event) => {
      const button = event.target.closest("[data-range]");
      if (!button || !rangeInput || !state.items[0]) return;
      const item = state.items[0];
      const value = button.dataset.range;
      let range = "";
      if (value === "all") range = core.allPagesRange(item.pageCount);
      else if (value === "odd") range = core.oddEvenRange(item.pageCount, "odd");
      else if (value === "even") range = core.oddEvenRange(item.pageCount, "even");
      else if (value === "first") range = "1";
      else if (value === "last") range = String(item.pageCount);
      if (!range) return;
      rangeInput.value = range;
      rangeInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  if (pageSize) pageSize.addEventListener("change", clearResult);
  if (renderScale) renderScale.addEventListener("change", clearResult);
  if (jpgQuality) {
    jpgQuality.addEventListener("input", () => {
      if (jpgQualityValue) jpgQualityValue.textContent = `${jpgQuality.value} %`;
      clearResult();
    });
  }

  window.addEventListener("pagehide", () => {
    state.runId += 1;
    clearResult();
    state.items.forEach((item) => safeRevoke(item.thumbUrl));
    state.items = [];
    cleanupCanvases(previewGrid);
  });
}

// ---------------------------------------------------------------------------
// Arranque
// ---------------------------------------------------------------------------

async function boot() {
  updateLimitHint();
  hideProgress();
  bindDropzone();
  bindControls();

  if (processBtn) processBtn.disabled = true;
  if (libraryStatus) {
    libraryStatus.textContent = tr("pdf.loadingLibs", "Cargando bibliotecas locales…");
  }

  try {
    const lib = await import("./vendor/pdf/pdf-lib.esm.min.js");
    PDFDocument = lib.PDFDocument;
    pdfjs = await import("./vendor/pdf/pdf.min.mjs");
    getDocument = pdfjs.getDocument;
    pdfjs.GlobalWorkerOptions.workerSrc = new URL(
      "./vendor/pdf/pdf.worker.min.mjs",
      import.meta.url
    ).href;
    if (!PDFDocument || !getDocument) {
      throw new Error(tr("pdf.exportsMissing", "Exportaciones no encontradas"));
    }
  } catch (_) {
    state.libsReady = false;
    if (libraryStatus) {
      libraryStatus.textContent = tr(
        "pdf.libsUnavailable",
        "Bibliotecas no disponibles"
      );
    }
    if (processBtn) processBtn.disabled = true;
    showError(
      tr(
        "pdf.libsLoadFailed",
        "No se pudieron cargar pdf-lib o PDF.js desde este sitio. Recarga la página; si el problema continúa, comprueba que las bibliotecas locales estén disponibles."
      )
    );
    return;
  }

  state.libsReady = true;
  if (libraryStatus) libraryStatus.textContent = "pdf-lib 1.17.1 · PDF.js 6.4.299 (local)";
  updateActionHint();
  syncUI();
}

boot().catch((error) => {
  if (libraryStatus) {
    libraryStatus.textContent = tr("pdf.initError", "Error de inicialización");
  }
  const detail = error && error.message ? error.message : "";
  showError(
    tr(
      "pdf.initFailed",
      `No se pudo iniciar la herramienta PDF. ${detail}`.trim(),
      { error: detail }
    )
  );
});
