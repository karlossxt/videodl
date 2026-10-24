/* Utilidades compartidas por /comprimir-imagen, /convertir-imagen y
   /redimensionar-imagen.

   Todo el procesamiento ocurre en el navegador: aquí no se usa fetch ni se
   envía ningún archivo a un servidor. El módulo también se puede requerir
   desde Node para probar la validación y los cálculos sin DOM. */
(function (global) {
  "use strict";

  const MAX_FILE_BYTES = 25 * 1024 * 1024;
  const MAX_SIDE = 16384;
  const MAX_PIXELS = 64 * 1000 * 1000;
  const ALPHA_SCAN_PIXELS = 4 * 1000 * 1000;
  const ALPHA_SCAN_MAX_SIDE = 1024;

  const MIME = {
    jpeg: "image/jpeg",
    png: "image/png",
    webp: "image/webp",
  };

  const FORMATS = {
    [MIME.jpeg]: { label: "JPG", extension: "jpg", lossy: true, alpha: false },
    [MIME.png]: { label: "PNG", extension: "png", lossy: false, alpha: true },
    [MIME.webp]: { label: "WebP", extension: "webp", lossy: true, alpha: true },
  };

  const SUPPORTED_MIMES = Object.keys(FORMATS);
  const SUPPORTED_EXTENSIONS = ["jpg", "jpeg", "jfif", "png", "webp"];

  function asBytes(value) {
    if (value instanceof Uint8Array) return value;
    if (value instanceof ArrayBuffer) return new Uint8Array(value);
    if (value && value.buffer instanceof ArrayBuffer) {
      return new Uint8Array(value.buffer, value.byteOffset || 0, value.byteLength);
    }
    return new Uint8Array(0);
  }

  function ascii(bytes, start, end) {
    let text = "";
    for (let i = start; i < end && i < bytes.length; i += 1) {
      text += String.fromCharCode(bytes[i]);
    }
    return text;
  }

  /**
   * Identifica el formato real por los primeros bytes, sin fiarse de la
   * extensión ni del MIME que declara el sistema operativo.
   */
  function sniffImage(value) {
    const bytes = asBytes(value);
    if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
      return { mime: MIME.jpeg, label: "JPG", supported: true };
    }
    if (
      bytes.length >= 8 &&
      bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47 &&
      bytes[4] === 0x0d && bytes[5] === 0x0a && bytes[6] === 0x1a && bytes[7] === 0x0a
    ) {
      return { mime: MIME.png, label: "PNG", supported: true };
    }
    if (
      bytes.length >= 12 &&
      ascii(bytes, 0, 4) === "RIFF" &&
      ascii(bytes, 8, 12) === "WEBP"
    ) {
      return { mime: MIME.webp, label: "WebP", supported: true };
    }

    const header = ascii(bytes, 0, Math.min(bytes.length, 64));
    if (header.startsWith("GIF87a") || header.startsWith("GIF89a")) {
      return { mime: "image/gif", label: "GIF", supported: false };
    }
    if (header.startsWith("BM")) {
      return { mime: "image/bmp", label: "BMP", supported: false };
    }
    if (bytes.length >= 12 && ascii(bytes, 4, 8) === "ftyp") {
      const brand = ascii(bytes, 8, 12);
      if (["avif", "avis"].includes(brand)) {
        return { mime: "image/avif", label: "AVIF", supported: false };
      }
      if (["heic", "heix", "hevc", "hevx", "mif1", "msf1"].includes(brand)) {
        return { mime: "image/heic", label: "HEIC/HEIF", supported: false };
      }
    }

    // SVG: es texto y puede llevar BOM, espacios o una declaración XML delante.
    const text = new TextDecoder("utf-8", { fatal: false })
      .decode(bytes)
      .replace(/^\uFEFF/, "")
      .trimStart()
      .toLowerCase();
    if (text.startsWith("<svg") || (text.startsWith("<?xml") && text.includes("<svg"))) {
      return { mime: "image/svg+xml", label: "SVG", supported: false };
    }

    return null;
  }

  function formatInfo(mime) {
    return FORMATS[mime] || null;
  }

  function formatLabel(mime, fallback = "—") {
    const info = formatInfo(mime);
    return info ? info.label : fallback;
  }

  function extensionFor(mime) {
    const info = formatInfo(mime);
    return info ? info.extension : "bin";
  }

  function describeSize(bytes, maxBytes) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB (máximo ${(maxBytes / (1024 * 1024)).toFixed(0)} MB)`;
  }

  /**
   * Valida un File/Blob: tamaño, contenido vacío, formato real y compatibilidad.
   * Devuelve siempre un objeto para que la interfaz pueda mostrar el motivo.
   */
  async function validateFile(file, options = {}) {
    const maxBytes = options.maxBytes || MAX_FILE_BYTES;

    if (!file) {
      return { ok: false, code: "missing", error: "No se ha seleccionado ningún archivo." };
    }
    if (!Number.isFinite(file.size) || file.size <= 0) {
      return { ok: false, code: "empty", error: "El archivo está vacío o no se puede leer." };
    }
    if (file.size > maxBytes) {
      return {
        ok: false,
        code: "too-large",
        error: `La imagen pesa ${describeSize(file.size, maxBytes)}. Usa una imagen más pequeña.`,
      };
    }

    let bytes;
    try {
      const slice = typeof file.slice === "function" ? file.slice(0, 512) : file;
      bytes = asBytes(await slice.arrayBuffer());
    } catch (_) {
      return {
        ok: false,
        code: "unreadable",
        error: "No se pudo leer el archivo. Comprueba que sigue disponible e inténtalo de nuevo.",
      };
    }

    const detected = sniffImage(bytes);
    if (!detected) {
      const name = String(file.name || "").toLowerCase();
      const ext = name.includes(".") ? name.split(".").pop() : "";
      if (ext && !SUPPORTED_EXTENSIONS.includes(ext)) {
        return {
          ok: false,
          code: "unsupported",
          error: `El formato «.${ext}» no es compatible. Acepta JPG, PNG o WebP.`,
        };
      }
      return {
        ok: false,
        code: "corrupt",
        error: "El archivo no parece una imagen JPG, PNG o WebP válida. Puede estar dañado.",
      };
    }

    if (!detected.supported) {
      return {
        ok: false,
        code: "unsupported",
        error: `El formato ${detected.label} no es compatible. Convierte la imagen a JPG, PNG o WebP.`,
      };
    }

    return {
      ok: true,
      mime: detected.mime,
      extension: extensionFor(detected.mime),
      label: detected.label,
      size: file.size,
    };
  }

  /** Carga una imagen desde una URL (normalmente un blob:) y espera a que decode. */
  function loadImage(url) {
    return new Promise((resolve, reject) => {
      if (typeof Image === "undefined") {
        reject(new Error("Este navegador no puede cargar imágenes."));
        return;
      }
      const image = new Image();
      image.decoding = "async";
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("La imagen no se pudo decodificar."));
      image.src = url;
    });
  }

  function imageDimensions(image) {
    return {
      width: Number(image.naturalWidth || image.width || 0),
      height: Number(image.naturalHeight || image.height || 0),
    };
  }

  function limitFor(imgWidth, imgHeight) {
    const width = Math.max(1, Math.round(Number(imgWidth)));
    const height = Math.max(1, Math.round(Number(imgHeight)));
    if (!Number.isFinite(width) || !Number.isFinite(height)) return null;
    if (width > MAX_SIDE || height > MAX_SIDE || width * height > MAX_PIXELS) return null;
    return { width, height };
  }

  function percentDimensions(width, height, percentWidth, percentHeight) {
    const pw = Number(percentWidth);
    const ph = Number(percentHeight);
    if (!Number.isFinite(pw) || !Number.isFinite(ph) || pw <= 0 || ph <= 0) return null;
    const nextWidth = Math.max(1, Math.round((Number(width) * pw) / 100));
    const nextHeight = Math.max(1, Math.round((Number(height) * ph) / 100));
    return limitFor(nextWidth, nextHeight);
  }

  function proportionalHeight(width, height, nextWidth) {
    const w = Number(width);
    const h = Number(height);
    const nw = Number(nextWidth);
    if (!w || !h || !Number.isFinite(nw) || nw <= 0) return 0;
    return Math.max(1, Math.round((nw * h) / w));
  }

  function proportionalWidth(width, height, nextHeight) {
    const w = Number(width);
    const h = Number(height);
    const nh = Number(nextHeight);
    if (!w || !h || !Number.isFinite(nh) || nh <= 0) return 0;
    return Math.max(1, Math.round((nh * w) / h));
  }

  function normalizeQuality(percent) {
    const value = Number(percent);
    if (!Number.isFinite(value)) return 0.8;
    return Math.min(1, Math.max(0.01, value / 100));
  }

  /** Porcentaje real de reducción. Positivo = pesa menos; negativo = pesa más. */
  function reductionPercent(originalBytes, finalBytes) {
    const original = Number(originalBytes);
    const final = Number(finalBytes);
    if (!Number.isFinite(original) || !Number.isFinite(final) || original <= 0 || final < 0) {
      return null;
    }
    return ((original - final) / original) * 100;
  }

  function fileBaseName(name) {
    const raw = String(name || "imagen");
    const withoutExtension = raw.replace(/\.[^./\\]+$/, "");
    const clean = withoutExtension
      .replace(/[\\/:*?"<>|\u0000-\u001f]+/g, "-")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/^[.\s-]+/, "")
      .slice(0, 80);
    return clean || "imagen";
  }

  function outputName(name, suffix, mime) {
    return `${fileBaseName(name)}${suffix || ""}.${extensionFor(mime)}`;
  }

  /** ¿El navegador puede codificar este formato con canvas.toDataURL? */
  function supportsType(mime) {
    if (typeof document === "undefined" || !document.createElement) return false;
    try {
      const canvas = document.createElement("canvas");
      canvas.width = 1;
      canvas.height = 1;
      const url = canvas.toDataURL(mime);
      canvas.width = 0;
      canvas.height = 0;
      return url.indexOf(`data:${mime}`) === 0;
    } catch (_) {
      return false;
    }
  }

  function availableFormats() {
    return SUPPORTED_MIMES.filter((mime) => supportsType(mime));
  }

  /**
   * Detecta transparencia real. Analiza todos los píxeles hasta 4 MP; en
   * imágenes mayores usa una muestra de hasta 1024 px por lado para no reservar
   * un ImageData gigantesco. El JPEG final siempre lleva un fondo opaco.
   */
  function detectTransparency(image) {
    if (typeof document === "undefined") {
      return { transparent: false, sampled: false, supported: false };
    }
    const { width, height } = imageDimensions(image);
    if (!width || !height) {
      return { transparent: false, sampled: false, supported: false };
    }

    const total = width * height;
    const sampled = total > ALPHA_SCAN_PIXELS;
    const scale = sampled
      ? Math.min(
          1,
          ALPHA_SCAN_MAX_SIDE / Math.max(width, height),
          Math.sqrt(ALPHA_SCAN_PIXELS / total)
        )
      : 1;
    const scanWidth = Math.max(1, Math.round(width * scale));
    const scanHeight = Math.max(1, Math.round(height * scale));

    let canvas;
    try {
      canvas = document.createElement("canvas");
      canvas.width = scanWidth;
      canvas.height = scanHeight;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      if (!ctx) return { transparent: false, sampled, supported: false };
      ctx.drawImage(image, 0, 0, scanWidth, scanHeight);
      const data = ctx.getImageData(0, 0, scanWidth, scanHeight).data;
      for (let i = 3; i < data.length; i += 4) {
        if (data[i] < 255) return { transparent: true, sampled, supported: true };
      }
      return { transparent: false, sampled, supported: true };
    } catch (_) {
      return { transparent: false, sampled, supported: false };
    } finally {
      if (canvas) {
        canvas.width = 0;
        canvas.height = 0;
      }
    }
  }

  function canvasToBlob(canvas, mime, quality) {
    return new Promise((resolve, reject) => {
      try {
        const args = mime === MIME.png ? [mime] : [mime, quality];
        canvas.toBlob((blob) => {
          if (!blob) {
            reject(new Error("El navegador no pudo generar el archivo final."));
            return;
          }
          if (blob.type && blob.type !== mime) {
            reject(
              new Error(
                `Tu navegador no puede guardar en ${formatLabel(mime)}. Prueba con otro formato.`
              )
            );
            return;
          }
          resolve(blob);
        }, ...args);
      } catch (_) {
        reject(new Error("El navegador no pudo procesar la imagen. Prueba con una más pequeña."));
      }
    });
  }

  /**
   * Dibuja la imagen en un canvas del tamaño pedido y la codifica. El canvas se
   * libera siempre al terminar para que el navegador recupere la memoria.
   */
  async function renderImage({ image, width, height, mime, quality, background }) {
    const target = limitFor(width, height);
    if (!target) {
      throw new Error(
        `La salida supera el límite de ${MAX_SIDE} px por lado o ${MAX_PIXELS / 1000000} megapíxeles.`
      );
    }
    if (!formatInfo(mime)) {
      throw new Error("El formato de salida no es compatible.");
    }

    const canvas = document.createElement("canvas");
    try {
      canvas.width = target.width;
      canvas.height = target.height;
      const ctx = canvas.getContext("2d", { alpha: mime !== MIME.jpeg });
      if (!ctx) throw new Error("No se pudo preparar el lienzo de la imagen.");

      // JPEG no admite alfa: se pinta un fondo opaco antes de dibujar.
      if (mime === MIME.jpeg) {
        ctx.fillStyle = background || "#ffffff";
        ctx.fillRect(0, 0, target.width, target.height);
      }
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      ctx.drawImage(image, 0, 0, target.width, target.height);

      const blob = await canvasToBlob(canvas, mime, normalizeQuality(quality));
      return { blob, width: target.width, height: target.height, mime };
    } finally {
      canvas.width = 0;
      canvas.height = 0;
    }
  }

  const api = {
    MAX_FILE_BYTES,
    MAX_SIDE,
    MAX_PIXELS,
    MIME,
    FORMATS,
    SUPPORTED_MIMES,
    SUPPORTED_EXTENSIONS,
    sniffImage,
    formatInfo,
    formatLabel,
    extensionFor,
    validateFile,
    loadImage,
    imageDimensions,
    limitFor,
    percentDimensions,
    proportionalHeight,
    proportionalWidth,
    normalizeQuality,
    reductionPercent,
    fileBaseName,
    outputName,
    supportsType,
    availableFormats,
    detectTransparency,
    canvasToBlob,
    renderImage,
  };

  if (typeof window !== "undefined") window.VDImage = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
