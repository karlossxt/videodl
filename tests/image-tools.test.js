/* Pruebas del motor compartido de las herramientas de imagen.
   Se ejecutan con `node --test tests/image-tools.test.js` y no necesitan DOM:
   validan la detección real de formatos, los límites y los cálculos. */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const img = require("../static/image-tools.js");

const PNG_HEADER = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const JPG_HEADER = Uint8Array.from([0xff, 0xd8, 0xff, 0xe0]);
const WEBP_HEADER = Uint8Array.from([
  0x52, 0x49, 0x46, 0x46, 0x10, 0x00, 0x00, 0x00, 0x57, 0x45, 0x42, 0x50,
]);
const GIF_HEADER = Uint8Array.from([0x47, 0x49, 0x46, 0x38, 0x39, 0x61]);
const AVIF_HEADER = Uint8Array.from([
  0x00, 0x00, 0x00, 0x20, 0x66, 0x74, 0x79, 0x70, 0x61, 0x76, 0x69, 0x66,
]);

function fakeFile(bytes, options = {}) {
  const data = Uint8Array.from(bytes);
  return {
    name: options.name || "imagen.png",
    type: options.type || "image/png",
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

test("detecta JPG, PNG y WebP por sus bytes reales", () => {
  assert.equal(img.sniffImage(JPG_HEADER).mime, "image/jpeg");
  assert.equal(img.sniffImage(PNG_HEADER).mime, "image/png");
  assert.equal(img.sniffImage(WEBP_HEADER).mime, "image/webp");
});

test("identifica formatos no compatibles con un nombre legible", () => {
  assert.deepEqual(img.sniffImage(GIF_HEADER), {
    mime: "image/gif",
    label: "GIF",
    supported: false,
  });
  assert.equal(img.sniffImage(AVIF_HEADER).label, "AVIF");
  assert.equal(img.sniffImage(Uint8Array.from([0x42, 0x4d, 0x00])).label, "BMP");
  assert.equal(img.sniffImage(new TextEncoder().encode('<?xml version="1.0"?><svg></svg>')).label, "SVG");
});

test("acepta una imagen válida aunque el MIME declarado sea genérico", async () => {
  const result = await img.validateFile(
    fakeFile(PNG_HEADER, { name: "foto.png", type: "application/octet-stream" })
  );
  assert.equal(result.ok, true);
  assert.equal(result.mime, "image/png");
  assert.equal(result.extension, "png");
});

test("el contenido manda sobre una extensión engañosa", async () => {
  const result = await img.validateFile(fakeFile(PNG_HEADER, { name: "foto.jpg", type: "image/jpeg" }));
  assert.equal(result.ok, true);
  assert.equal(result.mime, "image/png");
});

test("rechaza archivos vacíos, demasiado grandes y sin imagen real", async () => {
  const empty = await img.validateFile(fakeFile([], { name: "vacia.png", size: 0 }));
  assert.equal(empty.ok, false);
  assert.equal(empty.code, "empty");

  const huge = await img.validateFile(
    fakeFile(PNG_HEADER, { name: "enorme.png", size: img.MAX_FILE_BYTES + 1 })
  );
  assert.equal(huge.ok, false);
  assert.equal(huge.code, "too-large");

  const corrupt = await img.validateFile(
    fakeFile(new TextEncoder().encode("esto no es una imagen"), { name: "rota.png" })
  );
  assert.equal(corrupt.ok, false);
  assert.equal(corrupt.code, "corrupt");

  const unsupported = await img.validateFile(fakeFile(GIF_HEADER, { name: "animacion.gif" }));
  assert.equal(unsupported.ok, false);
  assert.equal(unsupported.code, "unsupported");
  assert.match(unsupported.error, /GIF/);

  const renamed = await img.validateFile(
    fakeFile(new TextEncoder().encode("<?xml?><svg></svg>"), { name: "dibujo.svg" })
  );
  assert.equal(renamed.ok, false);
  assert.equal(renamed.code, "unsupported");
});

test("un archivo sin firma conocida y con extensión no soportada se rechaza por formato", async () => {
  const result = await img.validateFile(
    fakeFile(new TextEncoder().encode("datos"), { name: "archivo.heic" })
  );
  assert.equal(result.ok, false);
  assert.equal(result.code, "unsupported");
  assert.match(result.error, /\.heic/);
});

test("calcula el porcentaje real de reducción, incluido el aumento", () => {
  assert.equal(img.reductionPercent(1000, 750), 25);
  assert.equal(img.reductionPercent(1000, 1200), -20);
  assert.equal(img.reductionPercent(1000, 1000), 0);
  assert.equal(img.reductionPercent(0, 10), null);
  assert.equal(img.reductionPercent(1000, Number.NaN), null);
});

test("convierte porcentajes y proporciones con redondeo seguro", () => {
  assert.deepEqual(img.percentDimensions(4000, 3000, 50, 50), { width: 2000, height: 1500 });
  assert.deepEqual(img.percentDimensions(1, 1, 1, 1), { width: 1, height: 1 });
  assert.equal(img.percentDimensions(4000, 3000, 400, 400), null);
  assert.equal(img.proportionalHeight(4000, 3000, 800), 600);
  assert.equal(img.proportionalWidth(4000, 3000, 600), 800);
  assert.equal(img.proportionalHeight(4000, 3000, 0), 0);
});

test("limita dimensiones por lado y por megapíxeles", () => {
  assert.deepEqual(img.limitFor(800, 600), { width: 800, height: 600 });
  assert.equal(img.limitFor(img.MAX_SIDE + 1, 10), null);
  assert.equal(img.limitFor(10000, 10000), null);
});

test("normaliza la calidad y genera nombres descargables seguros", () => {
  assert.equal(img.normalizeQuality(80), 0.8);
  assert.equal(img.normalizeQuality(0), 0.01);
  assert.equal(img.normalizeQuality(200), 1);
  assert.equal(img.outputName("mi foto (1).png", "-comprimida", "image/jpeg"), "mi foto (1)-comprimida.jpg");
  assert.equal(img.outputName("../../evil?.png", "-convertida", "image/webp"), "evil--convertida.webp");
  assert.equal(img.outputName("sin-extension", "-redimensionada", "image/png"), "sin-extension-redimensionada.png");
});

test("etiquetas y extensiones de los tres formatos", () => {
  assert.equal(img.formatLabel("image/jpeg"), "JPG");
  assert.equal(img.formatLabel("image/png"), "PNG");
  assert.equal(img.formatLabel("image/webp"), "WebP");
  assert.equal(img.formatLabel("image/gif"), "—");
  assert.equal(img.extensionFor("image/jpeg"), "jpg");
  assert.equal(img.extensionFor("image/webp"), "webp");
  assert.equal(img.formatInfo("image/png").lossy, false);
  assert.equal(img.formatInfo("image/jpeg").alpha, false);
});
