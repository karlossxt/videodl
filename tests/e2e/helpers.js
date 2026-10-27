const fs = require("node:fs");

const PDF_LIB = "/vendor/pdf/pdf-lib.esm.min.js";

// Los fixtures se generan a veces antes de navegar (about:blank), donde una URL
// relativa no se puede resolver. Calculamos el origen de la app desde Node.
function moduleUrlFor(page) {
  const current = page.url();
  const base =
    current.startsWith("http://") || current.startsWith("https://")
      ? new URL(current).origin
      : process.env.E2E_BASE_URL || `http://127.0.0.1:${process.env.E2E_PORT || 8010}`;
  return new URL(PDF_LIB, base).href;
}

async function buildPdf(page, options = {}) {
  const config = {
    pages: 1,
    width: 420,
    height: 600,
    sizes: null,
    withImage: false,
    label: "Pagina",
    ...options,
  };
  const base64 = await page.evaluate(
    async ({ moduleUrl, pages, width, height, sizes, withImage, label }) => {
      const { PDFDocument, StandardFonts, rgb } = await import(moduleUrl);
      const doc = await PDFDocument.create();
      const font = await doc.embedFont(StandardFonts.Helvetica);
      let jpg = null;

      if (withImage) {
        const canvas = document.createElement("canvas");
        canvas.width = 900;
        canvas.height = 1200;
        const context = canvas.getContext("2d");
        context.fillStyle = "#0e7490";
        context.fillRect(0, 0, canvas.width, canvas.height);
        for (let index = 0; index < 6000; index += 1) {
          context.fillStyle = `hsl(${(index * 37) % 360} 90% 55%)`;
          context.fillRect(Math.random() * 900, Math.random() * 1200, 8, 8);
        }
        const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
        const binary = atob(dataUrl.split(",")[1]);
        const data = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) {
          data[index] = binary.charCodeAt(index);
        }
        jpg = await doc.embedJpg(data);
      }

      for (let index = 0; index < pages; index += 1) {
        const [pageWidth, pageHeight] =
          sizes && sizes[index] ? sizes[index] : [width, height];
        const pdfPage = doc.addPage([pageWidth, pageHeight]);
        pdfPage.drawText(`${label} ${index + 1}`, {
          x: 40,
          y: pageHeight - 60,
          size: 24,
          font,
          color: rgb(0.1, 0.1, 0.1),
        });
        if (jpg) {
          pdfPage.drawImage(jpg, {
            x: 30,
            y: 60,
            width: pageWidth - 60,
            height: pageHeight - 150,
          });
        }
      }

      const bytes = await doc.save();
      let binary = "";
      for (let index = 0; index < bytes.length; index += 0x8000) {
        binary += String.fromCharCode.apply(null, bytes.subarray(index, index + 0x8000));
      }
      return btoa(binary);
    },
    { moduleUrl: moduleUrlFor(page), ...config }
  );
  return Buffer.from(base64, "base64");
}

async function buildImage(page, options = {}) {
  const config = {
    type: "image/png",
    width: 320,
    height: 240,
    color: "#22d3ee",
    ...options,
  };
  const dataUrl = await page.evaluate(({ type, width, height, color }) => {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    context.fillStyle = color;
    context.fillRect(0, 0, width, height);
    context.fillStyle = "#0f172a";
    context.font = "bold 36px sans-serif";
    context.fillText("FasTools", 24, height / 2);
    return canvas.toDataURL(type, 0.9);
  }, config);
  return Buffer.from(dataUrl.split(",")[1], "base64");
}

async function inspectPdf(page, buffer) {
  return page.evaluate(
    async ({ moduleUrl, base64 }) => {
      const binary = atob(base64);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) {
        bytes[index] = binary.charCodeAt(index);
      }
      const { PDFDocument } = await import(moduleUrl);
      const doc = await PDFDocument.load(bytes, { updateMetadata: false });
      return {
        pageCount: doc.getPageCount(),
        sizes: doc.getPages().map((pdfPage) => {
          const size = pdfPage.getSize();
          return [Math.round(size.width), Math.round(size.height)];
        }),
        producer: doc.getProducer() || null,
      };
    },
    { moduleUrl: moduleUrlFor(page), base64: buffer.toString("base64") }
  );
}

async function openTool(page, path) {
  const response = await page.goto(path);
  if (!response || !response.ok()) {
    throw new Error(`No se pudo abrir ${path}: ${response ? response.status() : "sin respuesta"}`);
  }
  await page.waitForFunction(
    () => {
      const status = document.querySelector("#library-status");
      return Boolean(status && status.textContent.includes("pdf-lib"));
    },
    null,
    { timeout: 30_000 }
  );
}

async function upload(page, files, options = {}) {
  const { waitForList = true } = options;
  await page.setInputFiles("#file-input", files);
  if (waitForList) {
    await page.locator("#files-section").waitFor({ state: "visible" });
  }
}

async function runAndDownload(page) {
  await page.locator("#process-btn").click();
  await page.locator("#result").waitFor({ state: "visible", timeout: 60_000 });
  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 60_000 }),
    page.locator("#download-btn").click(),
  ]);
  const filePath = await download.path();
  return {
    name: download.suggestedFilename(),
    buffer: fs.readFileSync(filePath),
  };
}

function zipEntryCount(buffer) {
  const signature = Buffer.from([0x50, 0x4b, 0x05, 0x06]);
  const offset = buffer.lastIndexOf(signature);
  if (offset < 0) return -1;
  return buffer.readUInt16LE(offset + 10);
}

module.exports = {
  buildPdf,
  buildImage,
  inspectPdf,
  openTool,
  upload,
  runAndDownload,
  zipEntryCount,
};
