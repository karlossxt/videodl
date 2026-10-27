/* Pruebas del núcleo puro de la suite PDF.
   Se ejecutan con `node --test tests/pdf-tools.test.js` y no necesitan DOM:
   validan detección de PDF, rangos, orden, geometría, nombres y ZIP. */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const pdf = require("../static/pdf-core.js");

const PDF_HEADER = new TextEncoder().encode("%PDF-1.7\n1 0 obj\n<<>>\nendobj\n");
const PDF_HEADER_OFFSET = new TextEncoder().encode("basura\n%PDF-1.4\n");

function fakeFile(bytes, options = {}) {
  const data = Uint8Array.from(bytes);
  return {
    name: options.name || "documento.pdf",
    type: options.type || "application/pdf",
    size: options.size === undefined ? data.length : options.size,
    slice(start = 0, end = data.length) {
      const part = data.slice(start, end);
      return {
        arrayBuffer: async () =>
          part.buffer.slice(part.byteOffset, part.byteOffset + part.byteLength),
      };
    },
  };
}

test("detecta la firma PDF, incluso con bytes previos dentro de los primeros 1024", () => {
  assert.equal(pdf.sniffPdf(PDF_HEADER).ok, true);
  assert.equal(pdf.sniffPdf(PDF_HEADER).version, "1.7");
  assert.equal(pdf.sniffPdf(PDF_HEADER_OFFSET).ok, true);
  assert.equal(pdf.sniffPdf(PDF_HEADER_OFFSET).version, "1.4");
  assert.equal(pdf.sniffPdf(new TextEncoder().encode("no es un pdf")).ok, false);
});

test("acepta un PDF válido aunque el MIME declarado sea genérico", async () => {
  const result = await pdf.validatePdfFile(
    fakeFile(PDF_HEADER, { name: "informe.pdf", type: "application/octet-stream" })
  );
  assert.equal(result.ok, true);
  assert.equal(result.name, "informe.pdf");
});

test("rechaza archivos vacíos, grandes y con contenido que no es PDF", async () => {
  const empty = await pdf.validatePdfFile(fakeFile([], { size: 0 }));
  assert.equal(empty.ok, false);
  assert.equal(empty.code, "empty");

  const huge = await pdf.validatePdfFile(
    fakeFile(PDF_HEADER, { size: pdf.MAX_FILE_BYTES + 1 })
  );
  assert.equal(huge.ok, false);
  assert.equal(huge.code, "too-large");

  const corrupt = await pdf.validatePdfFile(
    fakeFile(new TextEncoder().encode("<html>no soy un pdf</html>"), { name: "falso.pdf" })
  );
  assert.equal(corrupt.ok, false);
  assert.equal(corrupt.code, "corrupt");
  assert.match(corrupt.error, /no parece un PDF válido/);
});

test("traduce errores de contraseña y corrupción a mensajes claros", () => {
  const encrypted = pdf.friendlyPdfError(
    Object.assign(new Error("Input document is encrypted"), { name: "PasswordException" }),
    "protegido.pdf"
  );
  assert.equal(encrypted.code, "encrypted");
  assert.match(encrypted.message, /protegido con contraseña/);
  assert.match(encrypted.message, /no puede descifrar/);

  const corrupt = pdf.friendlyPdfError(
    Object.assign(new Error("Invalid PDF structure"), { name: "InvalidPDFException" }),
    "roto.pdf"
  );
  assert.equal(corrupt.code, "corrupt");
  assert.match(corrupt.message, /dañado/);

  const parseError = pdf.friendlyPdfError(
    new TypeError("Cannot read properties of undefined (reading 'Pages')"),
    "roto.pdf"
  );
  assert.equal(parseError.code, "corrupt");

  const unknown = pdf.friendlyPdfError(new Error("otra cosa"), "x.pdf");
  assert.equal(unknown.code, "unknown");
  assert.match(unknown.message, /No se pudo procesar/);
});

test("interpreta rangos y conserva el orden escrito, incluidas repeticiones", () => {
  const basic = pdf.parsePageRanges("1-3, 5, 8-10", 10);
  assert.equal(basic.ok, true);
  assert.deepEqual(basic.pages, [1, 2, 3, 5, 8, 9, 10]);

  const ordered = pdf.parsePageRanges("3, 1, 2", 5);
  assert.deepEqual(ordered.pages, [3, 1, 2]);

  const repeated = pdf.parsePageRanges("2, 2, 4", 5);
  assert.deepEqual(repeated.pages, [2, 2, 4]);

  const reversed = pdf.parsePageRanges("4-2", 5);
  assert.deepEqual(reversed.pages, [2, 3, 4]);
});

test("rechaza rangos vacíos, fuera de límites o con sintaxis inválida", () => {
  assert.equal(pdf.parsePageRanges("", 10).ok, false);
  assert.equal(pdf.parsePageRanges("1,,3", 10).ok, true);
  assert.equal(pdf.parsePageRanges("0", 10).ok, false);
  assert.equal(pdf.parsePageRanges("11", 10).ok, false);
  assert.equal(pdf.parsePageRanges("1-11", 10).ok, false);
  assert.equal(pdf.parsePageRanges("a-b", 10).ok, false);
  assert.equal(pdf.parsePageRanges("1-3", 0).ok, false);
  assert.equal(pdf.parsePageRanges("1-10", 10, { maxPages: 5 }).ok, false);
});

test("comprime páginas a texto de rangos y genera selecciones rápidas", () => {
  assert.equal(pdf.pagesToRangeText([1, 2, 3, 5, 8, 9, 10]), "1-3, 5, 8-10");
  assert.equal(pdf.pagesToRangeText([3, 1, 2]), "1-3");
  assert.equal(pdf.pagesToRangeText([]), "");
  assert.equal(pdf.allPagesRange(1), "1");
  assert.equal(pdf.allPagesRange(7), "1-7");
  assert.equal(pdf.oddEvenRange(7, "odd"), "1, 3, 5, 7");
  assert.equal(pdf.oddEvenRange(7, "even"), "2, 4, 6");
});

test("mueve elementos sin mutar el array original y respeta los límites", () => {
  const original = ["a", "b", "c"];
  assert.deepEqual(pdf.moveItem(original, 0, 2), ["b", "c", "a"]);
  assert.deepEqual(pdf.moveItem(original, 2, 1), ["a", "c", "b"]);
  assert.deepEqual(pdf.moveItem(original, 1, 1), original);
  assert.deepEqual(pdf.moveItem(original, -1, 0), original);
  assert.deepEqual(pdf.moveBy(original, 1, -1), ["b", "a", "c"]);
  assert.deepEqual(original, ["a", "b", "c"]);
});

test("calcula el encaje de una imagen dentro de una caja", () => {
  assert.deepEqual(pdf.fitRect(100, 50, 200, 200), {
    width: 200,
    height: 100,
    x: 0,
    y: 50,
    scale: 2,
  });
  assert.deepEqual(pdf.fitRect(50, 100, 200, 200), {
    width: 100,
    height: 200,
    x: 50,
    y: 0,
    scale: 2,
  });
  assert.equal(pdf.fitRect(0, 100, 200, 200), null);
});

test("planifica páginas A4 y tamaño de imagen con márgenes", () => {
  const portrait = pdf.imagePagePlan(1000, 500, "a4", 24);
  assert.ok(portrait.pageHeight > portrait.pageWidth);
  assert.equal(portrait.pageWidth, pdf.A4.width);
  assert.equal(portrait.pageHeight, pdf.A4.height);

  const vertical = pdf.imagePagePlan(500, 1000, "a4", 24);
  assert.equal(vertical.pageWidth, pdf.A4.width);
  assert.equal(vertical.pageHeight, pdf.A4.height);
  assert.ok(vertical.drawWidth <= vertical.pageWidth - 48);
  assert.ok(vertical.drawHeight <= vertical.pageHeight - 48);

  const imageSize = pdf.imagePagePlan(960, 480, "image", 24);
  assert.equal(imageSize.pageWidth, 720);
  assert.equal(imageSize.pageHeight, 360);
  assert.equal(imageSize.drawWidth, 720);
  assert.equal(imageSize.x, 0);

  const huge = pdf.imagePagePlan(100000, 640, "image", 24);
  assert.ok(huge.pageWidth <= pdf.MAX_PAGE_POINTS);
  assert.ok(huge.pageHeight <= pdf.MAX_PAGE_POINTS);
  assert.ok(Math.abs(huge.pageWidth / huge.pageHeight - 100000 / 640) < 0.001);
  assert.equal(pdf.MAX_IMAGE_PIXELS, 64_000_000);
  assert.equal(pdf.MAX_PAGE_POINTS, 14400);
});

test("limita la escala de renderizado por lado y por píxeles", () => {
  const normal = pdf.clampRenderScale(600, 800, 1.5);
  assert.equal(normal.scale, 1.5);
  assert.equal(normal.clamped, false);

  const huge = pdf.clampRenderScale(20000, 20000, 2);
  assert.equal(huge.clamped, true);
  assert.ok(huge.width <= pdf.MAX_OUTPUT_SIDE);
  assert.ok(huge.height <= pdf.MAX_OUTPUT_SIDE);
  assert.ok(huge.width * huge.height <= pdf.MAX_OUTPUT_PIXELS);
});

test("genera nombres de salida seguros y con extensión correcta", () => {
  assert.equal(pdf.sanitizeBaseName("mi informe.final.pdf"), "mi informe.final");
  assert.equal(pdf.sanitizeBaseName('malo<>:"/\\|?*.pdf'), "malo---------");
  assert.equal(pdf.sanitizeBaseName(""), "documento");
  assert.equal(pdf.mergedPdfName(), "documento-unido.pdf");
  assert.equal(pdf.splitPdfName("informe.pdf"), "informe-paginas.pdf");
  assert.equal(pdf.compressedPdfName("informe.pdf"), "informe-comprimido.pdf");
  assert.equal(pdf.imagesPdfName([{ name: "foto.png" }]), "foto-imagenes.pdf");
  assert.equal(pdf.imagesPdfName([{ name: "a.png" }, { name: "b.png" }]), "imagenes-a-pdf.pdf");
  assert.equal(pdf.jpgPageName("informe.pdf", 3, 12), "informe-pagina-03.jpg");
  assert.equal(pdf.zipName("informe.pdf"), "informe-jpg.zip");
});

test("calcula CRC32 y construye un ZIP almacenado con nombres UTF-8", () => {
  const data = new TextEncoder().encode("123456789");
  assert.equal(pdf.crc32(data), 0xcbf43926);

  const zip = pdf.zipStore([
    { name: "página-01.jpg", data: Uint8Array.from([1, 2, 3]) },
    { name: "página-02.jpg", data: Uint8Array.from([4, 5, 6, 7]) },
  ]);
  const view = new DataView(zip.buffer, zip.byteOffset, zip.byteLength);
  assert.equal(view.getUint32(0, true), 0x04034b50);
  assert.equal(view.getUint32(zip.length - 22, true), 0x06054b50);
  const text = new TextDecoder().decode(zip);
  assert.match(text, /página-01\.jpg/);
  assert.match(text, /página-02\.jpg/);
  assert.equal(view.getUint16(zip.length - 12, true), 2);
});
