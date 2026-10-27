/* Utilidades puras de la suite PDF: validación, rangos, orden, geometría,
   nombres de salida y un escritor ZIP sin compresión.

   No usa DOM ni red. Se puede requerir desde Node para ejecutar las pruebas
   unitarias y también se expone como `window.VDPdfCore` para la interfaz. */
(function (global) {
  "use strict";

  const MAX_FILE_BYTES = 25 * 1024 * 1024;
  const MAX_TOTAL_BYTES = 75 * 1024 * 1024;
  const MAX_FILES = 10;
  const MAX_IMAGES = 20;
  const MAX_PDF_PAGES = 300;
  const MAX_RENDER_PAGES = 80;
  const MAX_IMAGE_PIXELS = 64 * 1000 * 1000;
  const MAX_OUTPUT_PIXELS = 40 * 1000 * 1000;
  const MAX_OUTPUT_SIDE = 8192;
  const MAX_PAGE_POINTS = 14400;
  const A4 = { width: 595.28, height: 841.89 };

  const PDF_EXTENSIONS = ["pdf"];
  const IMAGE_MIMES = ["image/jpeg", "image/png"];

  function toBytes(value) {
    if (value instanceof Uint8Array) return value;
    if (value instanceof ArrayBuffer) return new Uint8Array(value);
    if (ArrayBuffer.isView(value)) {
      return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
    }
    return new Uint8Array(0);
  }

  // -------------------------------------------------------------------------
  // Validación de PDF
  // -------------------------------------------------------------------------

  function sniffPdf(bytes) {
    const data = toBytes(bytes);
    const limit = Math.min(data.length, 1024);
    for (let i = 0; i <= limit - 5; i += 1) {
      if (
        data[i] === 0x25 &&
        data[i + 1] === 0x50 &&
        data[i + 2] === 0x44 &&
        data[i + 3] === 0x46 &&
        data[i + 4] === 0x2d
      ) {
        let version = "";
        for (let j = i + 5; j < Math.min(data.length, i + 13); j += 1) {
          const char = String.fromCharCode(data[j]);
          if (!/[0-9.]/.test(char)) break;
          version += char;
        }
        return { ok: true, version: version || "desconocida" };
      }
    }
    return { ok: false, version: null };
  }

  async function validatePdfFile(file, options = {}) {
    const maxBytes = options.maxBytes || MAX_FILE_BYTES;
    if (!file) {
      return { ok: false, code: "empty", error: "No se ha seleccionado ningún archivo." };
    }
    const name = file.name || "documento.pdf";
    if (!file.size) {
      return { ok: false, code: "empty", error: `“${name}” está vacío.` };
    }
    if (file.size > maxBytes) {
      return {
        ok: false,
        code: "too-large",
        error: `“${name}” supera el límite de ${Math.round(maxBytes / (1024 * 1024))} MB.`,
      };
    }

    let header;
    try {
      const slice = file.slice(0, 1024);
      header = new Uint8Array(await slice.arrayBuffer());
    } catch (_) {
      return {
        ok: false,
        code: "unreadable",
        error: `No se pudo leer “${name}”. Comprueba que el archivo no esté dañado.`,
      };
    }

    if (!sniffPdf(header).ok) {
      return {
        ok: false,
        code: "corrupt",
        error: `“${name}” no parece un PDF válido. El contenido no coincide con la extensión.`,
      };
    }

    return { ok: true, code: null, error: null, name, size: file.size };
  }

  function friendlyPdfError(error, filename = "el documento") {
    const name = filename || "el documento";
    const errorName = error && error.name ? String(error.name) : "";
    const message = error && error.message ? String(error.message) : String(error || "");

    if (
      errorName === "PasswordException" ||
      /password|contraseña|encrypted|encryption|encriptad/i.test(message)
    ) {
      return {
        code: "encrypted",
        message:
          `“${name}” está protegido con contraseña o cifrado. ` +
          "Quita la protección con la aplicación con la que lo creaste y vuelve a intentarlo. " +
          "Esta herramienta no puede descifrar documentos.",
      };
    }

    if (
      errorName === "InvalidPDFException" ||
      errorName === "FormatError" ||
      /invalid pdf|invalidpdf|corrupt|malformed|no es un pdf|structure|failed to parse|expected instance|cannot read properties/i.test(
        message
      )
    ) {
      return {
        code: "corrupt",
        message:
          `“${name}” está dañado o no es un PDF legible. ` +
          "Prueba a abrirlo en tu visor habitual o vuelve a descargarlo desde el origen.",
      };
    }

    if (errorName === "MissingPDFException") {
      return {
        code: "missing",
        message: `No se encontró “${name}”. Vuelve a seleccionarlo.`,
      };
    }

    return {
      code: "unknown",
      message:
        `No se pudo procesar “${name}”. ` +
        "El archivo puede estar dañado o usar una protección no compatible.",
    };
  }

  // -------------------------------------------------------------------------
  // Rangos de páginas
  // -------------------------------------------------------------------------

  function parsePageRanges(input, pageCount, options = {}) {
    const maxPages = options.maxPages || MAX_PDF_PAGES;
    const total = Number(pageCount);
    if (!Number.isInteger(total) || total < 1) {
      return { ok: false, pages: [], error: "El documento no tiene páginas legibles." };
    }

    const raw = String(input || "").trim();
    if (!raw) {
      return { ok: false, pages: [], error: "Escribe al menos una página o un rango." };
    }

    const normalized = raw.replace(/[;]+/g, ",").replace(/\s+/g, " ");
    const tokens = normalized
      .split(",")
      .map((token) => token.trim())
      .filter(Boolean);

    if (!tokens.length) {
      return { ok: false, pages: [], error: "Escribe al menos una página o un rango." };
    }

    const pages = [];
    for (const token of tokens) {
      const match = /^(\d+)(?:\s*-\s*(\d+))?$/.exec(token);
      if (!match) {
        return {
          ok: false,
          pages: [],
          error: `“${token}” no es un rango válido. Usa el formato 1-3, 5 u 8-10.`,
        };
      }

      let start = Number(match[1]);
      let end = match[2] === undefined ? start : Number(match[2]);
      if (start > end) [start, end] = [end, start];

      if (start < 1 || end > total) {
        return {
          ok: false,
          pages: [],
          error: `Las páginas deben estar entre 1 y ${total}. Revisa “${token}”.`,
        };
      }

      for (let page = start; page <= end; page += 1) {
        pages.push(page);
        if (pages.length > maxPages) {
          return {
            ok: false,
            pages: [],
            error: `Puedes extraer como máximo ${maxPages} páginas en una sola operación.`,
          };
        }
      }
    }

    return { ok: true, pages, error: null };
  }

  function pagesToRangeText(pages) {
    const clean = Array.from(
      new Set(
        (pages || [])
          .map(Number)
          .filter((page) => Number.isInteger(page) && page > 0)
      )
    ).sort((a, b) => a - b);
    if (!clean.length) return "";

    const parts = [];
    let start = clean[0];
    let previous = clean[0];
    for (let i = 1; i <= clean.length; i += 1) {
      const page = clean[i];
      if (page === previous + 1) {
        previous = page;
        continue;
      }
      parts.push(start === previous ? String(start) : `${start}-${previous}`);
      start = page;
      previous = page;
    }
    return parts.join(", ");
  }

  function allPagesRange(pageCount) {
    const total = Number(pageCount);
    if (!Number.isInteger(total) || total < 1) return "";
    return total === 1 ? "1" : `1-${total}`;
  }

  function oddEvenRange(pageCount, parity) {
    const total = Number(pageCount);
    if (!Number.isInteger(total) || total < 1) return "";
    const pages = [];
    const offset = parity === "even" ? 2 : 1;
    for (let page = offset; page <= total; page += 2) pages.push(page);
    return pagesToRangeText(pages);
  }

  // -------------------------------------------------------------------------
  // Orden y geometría
  // -------------------------------------------------------------------------

  function moveItem(items, from, to) {
    const copy = Array.from(items || []);
    if (
      !Number.isInteger(from) ||
      !Number.isInteger(to) ||
      from < 0 ||
      to < 0 ||
      from >= copy.length ||
      to >= copy.length ||
      from === to
    ) {
      return copy;
    }
    const [moved] = copy.splice(from, 1);
    copy.splice(to, 0, moved);
    return copy;
  }

  function moveBy(items, index, delta) {
    return moveItem(items, index, Number(index) + Number(delta));
  }

  function clampNumber(value, min, max) {
    const number = Number(value);
    if (!Number.isFinite(number)) return min;
    return Math.min(max, Math.max(min, number));
  }

  function fitRect(imageWidth, imageHeight, boxWidth, boxHeight) {
    const iw = Number(imageWidth);
    const ih = Number(imageHeight);
    const bw = Number(boxWidth);
    const bh = Number(boxHeight);
    if (![iw, ih, bw, bh].every((value) => Number.isFinite(value) && value > 0)) {
      return null;
    }
    const scale = Math.min(bw / iw, bh / ih);
    const width = iw * scale;
    const height = ih * scale;
    return {
      width,
      height,
      x: (bw - width) / 2,
      y: (bh - height) / 2,
      scale,
    };
  }

  function imagePagePlan(imageWidth, imageHeight, sizeMode = "a4", margin = 24) {
    const iw = Number(imageWidth);
    const ih = Number(imageHeight);
    if (!Number.isFinite(iw) || !Number.isFinite(ih) || iw <= 0 || ih <= 0) {
      return null;
    }

    if (sizeMode === "image") {
      const width = (iw * 72) / 96;
      const height = (ih * 72) / 96;
      const fit = Math.min(1, MAX_PAGE_POINTS / width, MAX_PAGE_POINTS / height);
      const pageWidth = width * fit;
      const pageHeight = height * fit;
      return {
        pageWidth,
        pageHeight,
        x: 0,
        y: 0,
        drawWidth: pageWidth,
        drawHeight: pageHeight,
      };
    }

    const landscape = sizeMode === "a4-landscape";
    const pageWidth = landscape ? A4.height : A4.width;
    const pageHeight = landscape ? A4.width : A4.height;
    const safeMargin = clampNumber(margin, 0, Math.min(pageWidth, pageHeight) / 3);
    const boxWidth = pageWidth - safeMargin * 2;
    const boxHeight = pageHeight - safeMargin * 2;
    const rect = fitRect(iw, ih, boxWidth, boxHeight);
    return {
      pageWidth,
      pageHeight,
      x: safeMargin + (rect ? rect.x : 0),
      y: safeMargin + (rect ? rect.y : 0),
      drawWidth: rect ? rect.width : boxWidth,
      drawHeight: rect ? rect.height : boxHeight,
    };
  }

  function clampRenderScale(pageWidth, pageHeight, requestedScale, options = {}) {
    const width = Number(pageWidth);
    const height = Number(pageHeight);
    const requested = Number(requestedScale);
    if (![width, height, requested].every((value) => Number.isFinite(value) && value > 0)) {
      return { scale: 1, width: 1, height: 1, clamped: false };
    }
    const maxSide = options.maxSide || MAX_OUTPUT_SIDE;
    const maxPixels = options.maxPixels || MAX_OUTPUT_PIXELS;
    const sideScale = Math.min(maxSide / width, maxSide / height);
    const pixelScale = Math.sqrt(maxPixels / (width * height));
    const scale = Math.min(requested, sideScale, pixelScale);
    return {
      scale,
      width: Math.max(1, Math.floor(width * scale)),
      height: Math.max(1, Math.floor(height * scale)),
      clamped: scale + 0.0001 < requested,
    };
  }

  // -------------------------------------------------------------------------
  // Nombres de salida
  // -------------------------------------------------------------------------

  function sanitizeBaseName(name) {
    const withoutExtension = String(name || "")
      .replace(/\.[a-z0-9]{1,8}$/i, "")
      .replace(/[\\/:*?"<>|\u0000-\u001f]/g, "-")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/^[.\s]+|[.\s]+$/g, "");
    return (withoutExtension || "documento").slice(0, 80);
  }

  function outputName(name, suffix, extension) {
    return `${sanitizeBaseName(name)}${suffix || ""}.${extension || "pdf"}`;
  }

  function mergedPdfName() {
    return "documento-unido.pdf";
  }

  function splitPdfName(name) {
    return outputName(name, "-paginas", "pdf");
  }

  function compressedPdfName(name) {
    return outputName(name, "-comprimido", "pdf");
  }

  function imagesPdfName(items) {
    if (Array.isArray(items) && items.length === 1) {
      return outputName(items[0].name || items[0], "-imagenes", "pdf");
    }
    return "imagenes-a-pdf.pdf";
  }

  function jpgPageName(name, pageNumber, totalPages) {
    const digits = Math.max(2, String(totalPages || 1).length);
    const number = String(pageNumber).padStart(digits, "0");
    return `${sanitizeBaseName(name)}-pagina-${number}.jpg`;
  }

  function zipName(name) {
    return outputName(name, "-jpg", "zip");
  }

  // -------------------------------------------------------------------------
  // ZIP sin compresión (método 0): los JPG ya están comprimidos y así se evita
  // añadir otra dependencia al navegador.
  // -------------------------------------------------------------------------

  let crcTable = null;

  function crc32(bytes) {
    const data = toBytes(bytes);
    if (!crcTable) {
      crcTable = new Uint32Array(256);
      for (let n = 0; n < 256; n += 1) {
        let c = n;
        for (let k = 0; k < 8; k += 1) {
          c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
        }
        crcTable[n] = c >>> 0;
      }
    }
    let crc = 0xffffffff;
    for (let i = 0; i < data.length; i += 1) {
      crc = crcTable[(crc ^ data[i]) & 0xff] ^ (crc >>> 8);
    }
    return (crc ^ 0xffffffff) >>> 0;
  }

  function dosDateTime(date) {
    const value = date instanceof Date ? date : new Date();
    const year = Math.max(1980, Math.min(2107, value.getFullYear()));
    return {
      time:
        ((value.getHours() & 0x1f) << 11) |
        ((value.getMinutes() & 0x3f) << 5) |
        ((Math.floor(value.getSeconds() / 2) & 0x1f) << 0),
      date:
        (((year - 1980) & 0x7f) << 9) |
        (((value.getMonth() + 1) & 0x0f) << 5) |
        (value.getDate() & 0x1f),
    };
  }

  function safeZipName(name) {
    return String(name || "archivo")
      .replace(/\\/g, "/")
      .split("/")
      .filter((part) => part && part !== "." && part !== "..")
      .join("/")
      .replace(/^\/+/, "") || "archivo";
  }

  function zipStore(files, options = {}) {
    const entries = (files || []).map((file) => {
      const name = safeZipName(file.name);
      const nameBytes = new TextEncoder().encode(name);
      const data = toBytes(file.data);
      return { name, nameBytes, data, crc: crc32(data) };
    });
    const { time, date } = dosDateTime(options.date || new Date());
    const chunks = [];
    const central = [];
    let offset = 0;

    for (const entry of entries) {
      const header = new Uint8Array(30);
      const view = new DataView(header.buffer);
      view.setUint32(0, 0x04034b50, true);
      view.setUint16(4, 20, true);
      view.setUint16(6, 0x0800, true); // nombres en UTF-8
      view.setUint16(8, 0, true); // sin compresión
      view.setUint16(10, time, true);
      view.setUint16(12, date, true);
      view.setUint32(14, entry.crc, true);
      view.setUint32(18, entry.data.length, true);
      view.setUint32(22, entry.data.length, true);
      view.setUint16(26, entry.nameBytes.length, true);
      view.setUint16(28, 0, true);
      chunks.push(header, entry.nameBytes, entry.data);

      const centralHeader = new Uint8Array(46);
      const centralView = new DataView(centralHeader.buffer);
      centralView.setUint32(0, 0x02014b50, true);
      centralView.setUint16(4, 20, true);
      centralView.setUint16(6, 20, true);
      centralView.setUint16(8, 0x0800, true);
      centralView.setUint16(10, 0, true);
      centralView.setUint16(12, time, true);
      centralView.setUint16(14, date, true);
      centralView.setUint32(16, entry.crc, true);
      centralView.setUint32(20, entry.data.length, true);
      centralView.setUint32(24, entry.data.length, true);
      centralView.setUint16(28, entry.nameBytes.length, true);
      centralView.setUint16(30, 0, true);
      centralView.setUint16(32, 0, true);
      centralView.setUint16(34, 0, true);
      centralView.setUint16(36, 0, true);
      centralView.setUint32(38, 0, true);
      centralView.setUint32(42, offset, true);
      central.push(centralHeader, entry.nameBytes);

      offset += header.length + entry.nameBytes.length + entry.data.length;
    }

    const centralOffset = offset;
    let centralSize = 0;
    for (const chunk of central) centralSize += chunk.length;

    const end = new Uint8Array(22);
    const endView = new DataView(end.buffer);
    endView.setUint32(0, 0x06054b50, true);
    endView.setUint16(4, 0, true);
    endView.setUint16(6, 0, true);
    endView.setUint16(8, entries.length, true);
    endView.setUint16(10, entries.length, true);
    endView.setUint32(12, centralSize, true);
    endView.setUint32(16, centralOffset, true);
    endView.setUint16(20, 0, true);

    const all = chunks.concat(central, [end]);
    let total = 0;
    for (const chunk of all) total += chunk.length;
    const output = new Uint8Array(total);
    let cursor = 0;
    for (const chunk of all) {
      output.set(chunk, cursor);
      cursor += chunk.length;
    }
    return output;
  }

  const api = {
    MAX_FILE_BYTES,
    MAX_TOTAL_BYTES,
    MAX_FILES,
    MAX_IMAGES,
    MAX_PDF_PAGES,
    MAX_RENDER_PAGES,
    MAX_IMAGE_PIXELS,
    MAX_OUTPUT_PIXELS,
    MAX_OUTPUT_SIDE,
    MAX_PAGE_POINTS,
    A4,
    PDF_EXTENSIONS,
    IMAGE_MIMES,
    sniffPdf,
    validatePdfFile,
    friendlyPdfError,
    parsePageRanges,
    pagesToRangeText,
    allPagesRange,
    oddEvenRange,
    moveItem,
    moveBy,
    clampNumber,
    fitRect,
    imagePagePlan,
    clampRenderScale,
    sanitizeBaseName,
    outputName,
    mergedPdfName,
    splitPdfName,
    compressedPdfName,
    imagesPdfName,
    jpgPageName,
    zipName,
    crc32,
    zipStore,
  };

  if (typeof window !== "undefined") window.VDPdfCore = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
