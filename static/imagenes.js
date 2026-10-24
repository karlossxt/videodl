/* Interfaz común de las tres herramientas de imagen.
   La lógica de archivos, validación, canvas y codificación vive en
   image-tools.js; aquí solo se conecta con el HTML de cada modo. */
(function () {
  "use strict";

  const { $, showToast, showError, clearError, formatBytes, triggerDownload } = window.VD;
  const ImageTools = window.VDImage;

  const MODE = document.body.dataset.imageTool;
  if (!MODE || !ImageTools) return;

  const {
    FORMATS,
    MIME,
    MAX_FILE_BYTES,
    MAX_SIDE,
    MAX_PIXELS,
    availableFormats,
    detectTransparency,
    formatInfo,
    formatLabel,
    imageDimensions,
    limitFor,
    loadImage,
    outputName,
    percentDimensions,
    proportionalHeight,
    proportionalWidth,
    reductionPercent,
    renderImage,
    supportsType,
    validateFile,
  } = ImageTools;

  const reverseBase = {
    compress: "-comprimida",
    convert: "-convertida",
    resize: "-redimensionada",
  }[MODE];

  const workingText = {
    compress: "Comprimiendo la imagen en tu navegador…",
    convert: "Convirtiendo la imagen en tu navegador…",
    resize: "Redimensionando la imagen en tu navegador…",
  }[MODE];

  const state = {
    file: null,
    image: null,
    sourceUrl: null,
    resultUrl: null,
    width: 0,
    height: 0,
    format: null,
    transparent: false,
    transparencySampled: false,
    result: null,
    downloadName: "",
    working: false,
    runId: 0,
  };

  // -------------------------------------------------------------------------
  // Referencias del DOM
  // -------------------------------------------------------------------------

  const dropzone = $("dropzone");
  const fileInput = $("file-input");
  const fileCard = $("file-card");
  const fileClear = $("file-clear");
  const fileName = $("file-name");
  const fileMeta = $("file-meta");
  const workspace = $("workspace");
  const controls = $("controls");
  const inputPreview = $("input-preview");
  const inputPreviewMeta = $("input-preview-meta");
  const outputPreview = $("output-preview");
  const outputPlaceholder = $("output-placeholder");
  const outputPreviewMeta = $("output-preview-meta");
  const processBtn = $("process-btn");
  const actionHint = $("action-hint");
  const working = $("working");
  const workingTextEl = $("working-text");
  const resultSection = $("result");
  const downloadBtn = $("download-btn");
  const againBtn = $("again-btn");
  const outBefore = $("out-before");
  const outAfter = $("out-after");
  const outBeforeDetail = $("out-before-detail");
  const outAfterDetail = $("out-after-detail");
  const outSaved = $("out-saved");
  const resultNote = $("result-note");
  const formatSupport = $("format-support");
  const qualityInput = $("quality");
  const qualityValue = $("quality-value");
  const qualityHint = $("quality-hint");
  const jpegBackgroundField = $("jpeg-background-field");
  const jpegBackground = $("jpeg-background");
  const transparencyWarning = $("transparency-warning");

  const formatSelect = $("compress-format") || $("convert-format");
  const sizeMode = $("size-mode");
  const pixelsFields = $("pixels-fields");
  const percentFields = $("percent-fields");
  const resizeWidth = $("resize-width");
  const resizeHeight = $("resize-height");
  const resizePercentWidth = $("resize-percent-width");
  const resizePercentHeight = $("resize-percent-height");
  const keepRatio = $("keep-ratio");
  const resizeSummary = $("resize-summary");
  const resizePresets = $("resize-presets");

  const limitHint = $("limit-hint");
  const limitHint2 = $("limit-hint-2");
  const maxMb = Math.round(MAX_FILE_BYTES / (1024 * 1024));

  // -------------------------------------------------------------------------
  // Utilidades de formato y estado
  // -------------------------------------------------------------------------

  const numberFormat = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 1 });

  function percentText(value) {
    const rounded = Math.abs(value) < 0.05 ? 0 : value;
    return `${numberFormat.format(rounded)} %`;
  }

  function dimensionText(width, height) {
    return `${numberFormat.format(width)} × ${numberFormat.format(height)} px`;
  }

  function safeRevoke(url) {
    if (url) {
      try {
        URL.revokeObjectURL(url);
      } catch (_) {
        /* La URL ya no existe: no hay nada que liberar. */
      }
    }
  }

  function selectedFormat() {
    if (MODE === "resize") return state.format;
    const value = formatSelect ? formatSelect.value : "";
    return value === "original" ? state.format : value;
  }

  function isLossy(mime) {
    const info = formatInfo(mime);
    return Boolean(info && info.lossy);
  }

  function targetIsJpeg() {
    return Boolean(state.image) && selectedFormat() === MIME.jpeg;
  }

  function markFormatOptions() {
    const available = new Set(availableFormats());
    if (formatSelect) {
      Array.from(formatSelect.options).forEach((option) => {
        const mime = option.dataset.mime;
        if (!mime) return;
        const supported = available.has(mime);
        option.disabled = !supported;
        if (!supported && !option.dataset.unsupported) {
          option.dataset.unsupported = "1";
          option.textContent = `${option.textContent.replace(/ · .*$/, "")} · no compatible con este navegador`;
        }
      });

      if (formatSelect.value !== "original" && !available.has(formatSelect.value)) {
        formatSelect.value =
          MODE === "convert" && available.has(MIME.webp) ? MIME.webp : MIME.jpeg;
      }
    }

    const missing = ["image/jpeg", "image/png", "image/webp"].filter(
      (mime) => !available.has(mime)
    );
    if (formatSupport) {
      if (!missing.length) {
        formatSupport.textContent = "JPG, PNG y WebP disponibles en este navegador.";
      } else {
        formatSupport.textContent = `Sin soporte de ${missing
          .map((mime) => formatLabel(mime))
          .join(", ")} en este navegador.`;
      }
    }
  }

  function refreshOptionUI() {
    const mime = selectedFormat();
    const lossy = isLossy(mime);

    if (qualityInput) {
      qualityInput.disabled = !lossy;
      if (qualityValue) qualityValue.textContent = `${qualityInput.value} %`;
      if (qualityHint) {
        if (!lossy) {
          qualityHint.textContent =
            "El PNG se guarda sin pérdida: el deslizador de calidad no cambia el resultado.";
        } else if (MODE === "compress") {
          qualityHint.textContent =
            "A mayor calidad, más peso. Para fotos, 75–85 % suele ser un buen equilibrio.";
        } else {
          qualityHint.textContent =
            "Solo se aplica a JPG y WebP. A mayor calidad, más peso y más detalle.";
        }
      }
    }

    const jpeg = mime === MIME.jpeg;
    if (jpegBackgroundField) jpegBackgroundField.classList.toggle("hidden", !jpeg);
    if (transparencyWarning) {
      transparencyWarning.classList.toggle("hidden", !(jpeg && state.transparent));
    }

    updateResizeSummary();
  }

  function updateActionState() {
    if (!processBtn) return;
    const ready = Boolean(state.image) && !state.working;
    processBtn.disabled = !ready;
    if (actionHint) {
      actionHint.textContent = state.working
        ? "Espera mientras se procesa la imagen."
        : state.image
          ? "La vista previa no modifica tu archivo original."
          : "Elige una imagen para activar la herramienta.";
    }
  }

  function setWorking(value) {
    state.working = value;
    if (working) working.classList.toggle("hidden", !value);
    if (workingTextEl) workingTextEl.textContent = workingText;
    if (processBtn) processBtn.setAttribute("aria-busy", String(value));
    updateActionState();
  }

  // -------------------------------------------------------------------------
  // Limpieza de URLs, canvas y estado
  // -------------------------------------------------------------------------

  function clearResult() {
    safeRevoke(state.resultUrl);
    state.resultUrl = null;
    state.result = null;
    state.downloadName = "";
    if (outputPreview) {
      outputPreview.removeAttribute("src");
      outputPreview.classList.add("hidden");
    }
    if (outputPlaceholder) outputPlaceholder.classList.remove("hidden");
    if (outputPreviewMeta) outputPreviewMeta.textContent = "Sin procesar";
    if (resultSection) resultSection.classList.add("hidden");
    if (downloadBtn) downloadBtn.disabled = true;
    if (outSaved) {
      outSaved.classList.remove("is-increase");
      outSaved.textContent = "";
    }
    if (resultNote) resultNote.textContent = "";
  }

  function clearSelection() {
    state.runId += 1;
    state.working = false;
    if (working) working.classList.add("hidden");
    if (processBtn) processBtn.setAttribute("aria-busy", "false");
    safeRevoke(state.sourceUrl);
    state.sourceUrl = null;
    if (inputPreview) {
      inputPreview.removeAttribute("src");
      inputPreview.alt = "Vista previa de la imagen original";
    }
    state.file = null;
    state.image = null;
    state.width = 0;
    state.height = 0;
    state.format = null;
    state.transparent = false;
    state.transparencySampled = false;
    if (fileCard) fileCard.classList.add("hidden");
    if (workspace) workspace.classList.add("hidden");
    if (controls) controls.classList.add("hidden");
    if (fileInput) fileInput.value = "";
    clearResult();
    updateActionState();
    if (resizeSummary) {
      resizeSummary.textContent = "El tamaño final aparecerá aquí.";
      resizeSummary.classList.remove("is-error");
    }
  }

  function resetAll() {
    clearSelection();
    clearError();
    if (formatSelect) formatSelect.value = MODE === "convert" ? MIME.webp : "original";
    if (resizeWidth) resizeWidth.value = "";
    if (resizeHeight) resizeHeight.value = "";
    if (resizePercentWidth) resizePercentWidth.value = "100";
    if (resizePercentHeight) resizePercentHeight.value = "100";
    if (keepRatio) keepRatio.checked = true;
    if (sizeMode) sizeMode.value = "pixels";
    if (pixelsFields) pixelsFields.classList.remove("hidden");
    if (percentFields) percentFields.classList.add("hidden");
    refreshOptionUI();
  }

  // -------------------------------------------------------------------------
  // Carga y validación del archivo
  // -------------------------------------------------------------------------

  function showDecodeError(mime) {
    if (mime === MIME.webp) {
      showError(
        "El archivo es un WebP, pero este navegador no puede decodificarlo. Prueba con JPG o PNG."
      );
    } else if (mime === MIME.jpeg) {
      showError("El JPG está dañado o incompleto y el navegador no puede leerlo.");
    } else {
      showError("El PNG está dañado o incompleto y el navegador no puede leerlo.");
    }
  }

  async function handleFile(file) {
    clearSelection();
    const runId = state.runId;
    clearError();

    let validation;
    try {
      validation = await validateFile(file);
    } catch (_) {
      if (runId === state.runId) {
        showError("No se pudo comprobar el archivo. Inténtalo de nuevo.");
      }
      return;
    }
    if (runId !== state.runId) return;
    if (!validation.ok) {
      showError(validation.error);
      return;
    }

    const url = URL.createObjectURL(file);
    let image;
    try {
      image = await loadImage(url);
    } catch (_) {
      safeRevoke(url);
      if (runId === state.runId) showDecodeError(validation.mime);
      return;
    }

    if (runId !== state.runId) {
      safeRevoke(url);
      return;
    }

    const dims = imageDimensions(image);
    const validSize = limitFor(dims.width, dims.height);
    if (!validSize) {
      safeRevoke(url);
      showError(
        `La imagen mide ${dimensionText(dims.width, dims.height)}. El límite es de ` +
          `${numberFormat.format(MAX_SIDE)} px por lado y ${numberFormat.format(
            MAX_PIXELS / 1000000
          )} megapíxeles.`
      );
      return;
    }

    const alpha = detectTransparency(image);
    if (runId !== state.runId) {
      safeRevoke(url);
      return;
    }

    state.file = file;
    state.image = image;
    state.sourceUrl = url;
    state.width = dims.width;
    state.height = dims.height;
    state.format = validation.mime;
    state.transparent = Boolean(alpha.transparent);
    state.transparencySampled = Boolean(alpha.sampled);

    if (inputPreview) {
      inputPreview.src = url;
      inputPreview.alt = `Vista previa de ${file.name || "la imagen original"}`;
    }
    if (inputPreviewMeta) {
      inputPreviewMeta.textContent = `${dimensionText(dims.width, dims.height)} · ${formatBytes(
        file.size
      )} · ${formatLabel(validation.mime)}`;
    }
    if (fileName) fileName.textContent = file.name || "Imagen sin nombre";
    if (fileMeta) {
      fileMeta.textContent = `${formatLabel(validation.mime)} · ${dimensionText(
        dims.width,
        dims.height
      )} · ${formatBytes(file.size)}`;
    }
    if (fileCard) fileCard.classList.remove("hidden");
    if (workspace) workspace.classList.remove("hidden");
    if (controls) controls.classList.remove("hidden");

    if (MODE === "resize") initResizeFields();
    markFormatOptions();
    refreshOptionUI();
    updateActionState();
  }

  // -------------------------------------------------------------------------
  // Redimensionado: píxeles, porcentaje y proporción
  // -------------------------------------------------------------------------

  function initResizeFields() {
    if (!resizeWidth || !resizeHeight) return;
    resizeWidth.value = String(state.width);
    resizeHeight.value = String(state.height);
    if (resizePercentWidth) resizePercentWidth.value = "100";
    if (resizePercentHeight) resizePercentHeight.value = "100";
    if (keepRatio) keepRatio.checked = true;
    if (sizeMode) sizeMode.value = "pixels";
    if (pixelsFields) pixelsFields.classList.remove("hidden");
    if (percentFields) percentFields.classList.add("hidden");
    updateResizeSummary();
  }

  function setPercentMode() {
    if (sizeMode) sizeMode.value = "percent";
    if (pixelsFields) pixelsFields.classList.add("hidden");
    if (percentFields) percentFields.classList.remove("hidden");
  }

  function setPixelMode() {
    if (sizeMode) sizeMode.value = "pixels";
    if (percentFields) percentFields.classList.add("hidden");
    if (pixelsFields) pixelsFields.classList.remove("hidden");
  }

  function syncResizeFromWidth() {
    if (!state.image || !resizeWidth || !resizeHeight) return;
    if (keepRatio && keepRatio.checked) {
      const next = Number(resizeWidth.value);
      if (next > 0) {
        resizeHeight.value = String(proportionalHeight(state.width, state.height, next));
      }
    }
    updateResizeSummary();
    clearResult();
  }

  function syncResizeFromHeight() {
    if (!state.image || !resizeWidth || !resizeHeight) return;
    if (keepRatio && keepRatio.checked) {
      const next = Number(resizeHeight.value);
      if (next > 0) {
        resizeWidth.value = String(proportionalWidth(state.width, state.height, next));
      }
    }
    updateResizeSummary();
    clearResult();
  }

  function readResizeTarget() {
    if (!state.image) return { ok: false, error: "Elige primero una imagen." };

    if (sizeMode && sizeMode.value === "percent") {
      const pw = Number(resizePercentWidth ? resizePercentWidth.value : 100);
      const ph = Number(keepRatio && keepRatio.checked ? pw : resizePercentHeight && resizePercentHeight.value);
      if (!Number.isFinite(pw) || !Number.isFinite(ph) || pw < 1 || ph < 1 || pw > 400 || ph > 400) {
        return {
          ok: false,
          error: "El porcentaje debe estar entre 1 % y 400 % en ambos lados.",
        };
      }
      const target = percentDimensions(state.width, state.height, pw, ph);
      if (!target) {
        return {
          ok: false,
          error: `El resultado supera el límite de ${numberFormat.format(
            MAX_SIDE
          )} px por lado o ${numberFormat.format(MAX_PIXELS / 1000000)} megapíxeles.`,
        };
      }
      return { ok: true, ...target };
    }

    const width = Number(resizeWidth ? resizeWidth.value : 0);
    const height = Number(resizeHeight ? resizeHeight.value : 0);
    if (
      !Number.isFinite(width) ||
      !Number.isFinite(height) ||
      !Number.isInteger(width) ||
      !Number.isInteger(height) ||
      width < 1 ||
      height < 1
    ) {
      return { ok: false, error: "El ancho y el alto deben ser números enteros mayores que 0." };
    }
    const target = limitFor(width, height);
    if (!target) {
      return {
        ok: false,
        error: `El resultado supera el límite de ${numberFormat.format(
          MAX_SIDE
        )} px por lado o ${numberFormat.format(MAX_PIXELS / 1000000)} megapíxeles.`,
      };
    }
    return { ok: true, ...target };
  }

  function updateResizeSummary() {
    if (!resizeSummary || MODE !== "resize") return;
    if (!state.image) {
      resizeSummary.textContent = "El tamaño final aparecerá aquí.";
      resizeSummary.classList.remove("is-error");
      return;
    }
    const target = readResizeTarget();
    if (!target.ok) {
      resizeSummary.textContent = target.error;
      resizeSummary.classList.add("is-error");
      return;
    }
    const same = target.width === state.width && target.height === state.height;
    resizeSummary.classList.remove("is-error");
    resizeSummary.textContent = same
      ? `Se mantiene en ${dimensionText(state.width, state.height)}.`
      : `De ${dimensionText(state.width, state.height)} a ${dimensionText(
          target.width,
          target.height
        )}.`;
  }

  // -------------------------------------------------------------------------
  // Procesamiento y resultado
  // -------------------------------------------------------------------------

  function resolveTarget() {
    const mime = selectedFormat();
    if (!formatInfo(mime)) {
      return { ok: false, error: "Elige un formato de salida válido." };
    }
    if (!supportsType(mime)) {
      return {
        ok: false,
        error: `Tu navegador no puede guardar imágenes en ${formatLabel(
          mime
        )}. Elige otro formato.`,
      };
    }

    let width = state.width;
    let height = state.height;
    let quality = qualityInput ? Number(qualityInput.value) : 90;

    if (MODE === "resize") {
      const target = readResizeTarget();
      if (!target.ok) return target;
      width = target.width;
      height = target.height;
      quality = 92;
    }

    return {
      ok: true,
      mime,
      width,
      height,
      quality,
      background: jpegBackground ? jpegBackground.value : "#ffffff",
    };
  }

  function showResult(blob, target) {
    state.resultUrl = URL.createObjectURL(blob);
    state.result = {
      blob,
      width: target.width,
      height: target.height,
      mime: target.mime,
    };
    state.downloadName = outputName(
      state.file ? state.file.name : "imagen",
      reverseBase,
      target.mime
    );

    if (outputPreview) {
      outputPreview.src = state.resultUrl;
      outputPreview.alt = `Vista previa de la imagen ${MODE === "resize" ? "redimensionada" : "resultante"}`;
      outputPreview.classList.remove("hidden");
    }
    if (outputPlaceholder) outputPlaceholder.classList.add("hidden");
    if (outputPreviewMeta) {
      outputPreviewMeta.textContent = `${dimensionText(
        target.width,
        target.height
      )} · ${formatBytes(blob.size)} · ${formatLabel(target.mime)}`;
    }

    const originalBytes = state.file ? state.file.size : 0;
    const reduction = reductionPercent(originalBytes, blob.size);
    const beforeLabel = formatLabel(state.format);
    const afterLabel = formatLabel(target.mime);

    if (outBefore) outBefore.textContent = formatBytes(originalBytes);
    if (outAfter) outAfter.textContent = formatBytes(blob.size);
    if (outBeforeDetail) {
      outBeforeDetail.textContent = `${dimensionText(state.width, state.height)} · ${beforeLabel}`;
    }
    if (outAfterDetail) {
      outAfterDetail.textContent = `${dimensionText(target.width, target.height)} · ${afterLabel}`;
    }

    if (outSaved && reduction !== null) {
      const abs = Math.abs(reduction);
      const basicallySame = abs < 0.05;
      outSaved.classList.toggle("is-increase", reduction < 0 && !basicallySame);
      outSaved.textContent = basicallySame
        ? "Prácticamente igual"
        : reduction > 0
          ? `${percentText(abs)} menos`
          : `${percentText(abs)} más`;
    }

    if (resultNote) {
      const notes = [];
      const quality =
        qualityInput && isLossy(target.mime) ? ` Calidad aplicada: ${qualityInput.value} %` : "";

      if (MODE === "compress") {
        if (reduction !== null && reduction < -0.05) {
          notes.push(
            `El archivo final pesa ${percentText(Math.abs(reduction))} más. La compresión no ` +
              "garantiza un archivo más pequeño: prueba una calidad menor o el formato WebP."
          );
        } else if (reduction !== null && reduction > 0.05) {
          notes.push(`El archivo final pesa ${percentText(reduction)} menos.${quality}`);
        } else {
          notes.push(
            "El tamaño es prácticamente el mismo. La compresión no garantiza que el archivo " +
              "resulte más pequeño, sobre todo si ya estaba optimizado."
          );
        }
      } else if (MODE === "convert") {
        notes.push(`Conversión de ${beforeLabel} a ${afterLabel}.${quality}`);
        if (reduction !== null && reduction < -0.05) {
          notes.push(
            `El nuevo formato pesa ${percentText(Math.abs(reduction))} más. Convertir no es ` +
              "lo mismo que comprimir; el porcentaje es el resultado real."
          );
        } else if (reduction !== null && reduction > 0.05) {
          notes.push(`El nuevo archivo pesa ${percentText(reduction)} menos.`);
        }
      } else {
        const grew = target.width > state.width || target.height > state.height;
        notes.push(
          `Redimensionada de ${dimensionText(state.width, state.height)} a ${dimensionText(
            target.width,
            target.height
          )}.`
        );
        if (grew) {
          notes.push("Se ha ampliado: la interpolación no crea detalle nuevo.");
        }
        if (reduction !== null) {
          notes.push(
            reduction > 0.05
              ? `El archivo final pesa ${percentText(reduction)} menos.`
              : reduction < -0.05
                ? `El archivo final pesa ${percentText(Math.abs(reduction))} más.`
                : "El peso final es prácticamente el mismo."
          );
        }
      }

      if (target.mime === MIME.jpeg && state.transparent) {
        notes.push(
          `Las zonas transparentes se rellenaron con el color ${
            jpegBackground ? jpegBackground.value : "#ffffff"
          }.`
        );
      }
      notes.push("Tu archivo original no se ha modificado.");
      resultNote.textContent = notes.join(" ");
    }

    if (resultSection) resultSection.classList.remove("hidden");
    if (downloadBtn) downloadBtn.disabled = false;
  }

  async function processImage() {
    if (!state.image || state.working) return;
    clearError();

    const target = resolveTarget();
    if (!target.ok) {
      showError(target.error);
      return;
    }

    const runId = ++state.runId;
    clearResult();
    setWorking(true);

    // Deja que el navegador pinte el indicador antes de bloquear con canvas.
    await new Promise((resolve) => {
      if (typeof requestAnimationFrame === "function") {
        requestAnimationFrame(() => setTimeout(resolve, 0));
      } else {
        setTimeout(resolve, 0);
      }
    });

    try {
      if (runId !== state.runId) return;
      const output = await renderImage({
        image: state.image,
        width: target.width,
        height: target.height,
        mime: target.mime,
        quality: target.quality,
        background: target.background,
      });
      if (runId !== state.runId) return;
      showResult(output.blob, output);
      showToast("Imagen procesada. Revisa el resultado antes de descargar.");
    } catch (err) {
      if (runId === state.runId) {
        showError(err && err.message ? err.message : "No se pudo procesar la imagen.");
      }
    } finally {
      if (runId === state.runId) setWorking(false);
    }
  }

  // -------------------------------------------------------------------------
  // Eventos
  // -------------------------------------------------------------------------

  $("error-close").addEventListener("click", clearError);

  if (dropzone && fileInput) {
    window.VD.linkDropzone(dropzone, fileInput, handleFile);
  }

  if (fileClear) {
    fileClear.addEventListener("click", () => {
      resetAll();
      if (dropzone) {
        dropzone.scrollIntoView({ behavior: "smooth", block: "center" });
        dropzone.focus({ preventScroll: true });
      }
    });
  }

  if (processBtn) processBtn.addEventListener("click", processImage);

  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      if (!state.resultUrl) {
        showToast("Primero procesa la imagen", { error: true });
        return;
      }
      triggerDownload(state.resultUrl, state.downloadName);
      showToast("Descargando la imagen…");
    });
  }

  if (againBtn) {
    againBtn.addEventListener("click", () => {
      resetAll();
      if (dropzone) dropzone.scrollIntoView({ behavior: "smooth", block: "center" });
      if (fileInput) fileInput.click();
    });
  }

  if (formatSelect) {
    formatSelect.addEventListener("change", () => {
      refreshOptionUI();
      clearResult();
      updateActionState();
    });
  }

  if (qualityInput) {
    qualityInput.addEventListener("input", () => {
      if (qualityValue) qualityValue.textContent = `${qualityInput.value} %`;
      clearResult();
      updateActionState();
    });
  }

  if (jpegBackground) {
    jpegBackground.addEventListener("input", () => {
      clearResult();
      updateActionState();
    });
  }

  if (sizeMode) {
    sizeMode.addEventListener("change", () => {
      if (!state.image) return;
      if (sizeMode.value === "percent") {
        const currentWidth = Math.max(1, Number(resizeWidth ? resizeWidth.value : state.width));
        const currentHeight = Math.max(1, Number(resizeHeight ? resizeHeight.value : state.height));
        const percentWidth = Math.min(
          400,
          Math.max(1, Math.round((currentWidth / state.width) * 100))
        );
        const percentHeight = Math.min(
          400,
          Math.max(1, Math.round((currentHeight / state.height) * 100))
        );
        if (resizePercentWidth) resizePercentWidth.value = String(percentWidth);
        if (resizePercentHeight) {
          resizePercentHeight.value = String(
            keepRatio && keepRatio.checked ? percentWidth : percentHeight
          );
        }
        setPercentMode();
      } else {
        const percentWidth = Number(resizePercentWidth ? resizePercentWidth.value : 100);
        const percentHeight = Number(resizePercentHeight ? resizePercentHeight.value : 100);
        const target = percentDimensions(
          state.width,
          state.height,
          percentWidth,
          keepRatio && keepRatio.checked ? percentWidth : percentHeight
        );
        if (target) {
          if (resizeWidth) resizeWidth.value = String(target.width);
          if (resizeHeight) resizeHeight.value = String(target.height);
        }
        setPixelMode();
      }
      updateResizeSummary();
      clearResult();
    });
  }

  if (resizeWidth) resizeWidth.addEventListener("input", syncResizeFromWidth);
  if (resizeHeight) resizeHeight.addEventListener("input", syncResizeFromHeight);

  if (resizePercentWidth) {
    resizePercentWidth.addEventListener("input", () => {
      if (keepRatio && keepRatio.checked && resizePercentHeight) {
        resizePercentHeight.value = resizePercentWidth.value;
      }
      updateResizeSummary();
      clearResult();
    });
  }

  if (resizePercentHeight) {
    resizePercentHeight.addEventListener("input", () => {
      if (keepRatio && keepRatio.checked && resizePercentWidth) {
        resizePercentWidth.value = resizePercentHeight.value;
      }
      updateResizeSummary();
      clearResult();
    });
  }

  if (keepRatio) {
    keepRatio.addEventListener("change", () => {
      if (!keepRatio.checked) {
        updateResizeSummary();
        return;
      }
      if (sizeMode && sizeMode.value === "percent") {
        if (resizePercentWidth && resizePercentHeight) {
          resizePercentHeight.value = resizePercentWidth.value;
        }
      } else if (resizeWidth && resizeHeight) {
        syncResizeFromWidth();
      }
      updateResizeSummary();
      clearResult();
    });
  }

  if (resizePresets) {
    resizePresets.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || !state.image) return;
      clearError();

      if (button.dataset.percent) {
        const percent = Number(button.dataset.percent);
        if (!Number.isFinite(percent) || percent < 1 || percent > 400) return;
        setPercentMode();
        if (keepRatio) keepRatio.checked = true;
        if (resizePercentWidth) resizePercentWidth.value = String(percent);
        if (resizePercentHeight) resizePercentHeight.value = String(percent);
      } else if (button.dataset.width) {
        const requested = Math.min(Number(button.dataset.width), state.width);
        setPixelMode();
        if (keepRatio) keepRatio.checked = true;
        if (resizeWidth) resizeWidth.value = String(requested);
        if (resizeHeight) {
          resizeHeight.value = String(proportionalHeight(state.width, state.height, requested));
        }
      }
      updateResizeSummary();
      clearResult();
    });
  }

  // -------------------------------------------------------------------------
  // Arranque
  // -------------------------------------------------------------------------

  function init() {
    if (limitHint) {
      limitHint.textContent = `Hasta ${maxMb} MB · ${numberFormat.format(
        MAX_SIDE
      )} px por lado · ${numberFormat.format(MAX_PIXELS / 1000000)} MP`;
    }
    if (limitHint2) limitHint2.textContent = `${maxMb} MB`;

    if (qualityInput) {
      qualityInput.value = MODE === "convert" ? "90" : "80";
      if (qualityValue) qualityValue.textContent = `${qualityInput.value} %`;
    }
    if (formatSelect && MODE === "convert") {
      formatSelect.value = MIME.webp;
    }
    if (resizeSummary) resizeSummary.setAttribute("aria-live", "polite");

    markFormatOptions();
    refreshOptionUI();
    updateActionState();
    updateResizeSummary();
  }

  window.addEventListener("pagehide", () => {
    state.runId += 1;
    safeRevoke(state.sourceUrl);
    safeRevoke(state.resultUrl);
    state.sourceUrl = null;
    state.resultUrl = null;
    if (state.image) {
      state.image = null;
    }
  });

  init();
})();
