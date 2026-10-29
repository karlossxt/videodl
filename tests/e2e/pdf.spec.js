const { test: base, expect } = require("@playwright/test");

const {
  buildPdf,
  buildImage,
  inspectPdf,
  openTool,
  upload,
  runAndDownload,
  zipEntryCount,
} = require("./helpers");

const PDF_PAGES = [
  "/unir-pdf",
  "/dividir-pdf",
  "/imagenes-a-pdf",
  "/pdf-a-jpg",
  "/comprimir-pdf",
];

const test = base.extend({
  // No descargar anuncios reales en CI: el HTML sí incluye AdSense, pero las
  // pruebas E2E se centran en el procesamiento local y deben ser deterministas.
  blockAdSense: [
    async ({ context }, use) => {
      await context.route(
        /^https:\/\/pagead\.googlesyndication\.com\//,
        (route) =>
          route.fulfill({
            status: 200,
            contentType: "application/javascript",
            body: "/* AdSense desactivado en las pruebas E2E */",
          })
      );
      await use();
    },
    { auto: true },
  ],
  errors: async ({ page }, use) => {
    const errors = [];
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    page.on("pageerror", (error) => errors.push(error.message));
    await use(errors);
  },
  requests: async ({ page }, use) => {
    const requests = [];
    page.on("request", (request) => {
      requests.push({ url: request.url(), method: request.method() });
    });
    await use(requests);
  },
});

function expectLocalOnly(requests, baseURL) {
  expect(requests.length).toBeGreaterThan(0);
  for (const request of requests) {
    expect(request.method, `${request.method} ${request.url}`).not.toBe("POST");
    expect(request.url, `Petición externa: ${request.url}`).not.toContain("/api/");
    // El cargador oficial de GTM es la única petición de terceros permitida.
    // Se limita al script del contenedor esperado; cualquier otro host sigue bloqueado.
    const allowedGtm =
      request.method === "GET" &&
      request.url === "https://www.googletagmanager.com/gtm.js?id=GTM-THCKMRK3";
    const allowedAdSenseLoader =
      request.method === "GET" &&
      request.url ===
        "https://pagead.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6317177060588245";
    const local =
      request.url.startsWith(baseURL) ||
      request.url.startsWith("blob:") ||
      request.url.startsWith("data:") ||
      allowedGtm ||
      allowedAdSenseLoader;
    expect(local, `Petición externa: ${request.url}`).toBe(true);
  }
}

test("las cinco páginas PDF cargan con las bibliotecas locales", async ({ page, errors }) => {
  for (const path of PDF_PAGES) {
    await openTool(page, path);
    await expect(page.locator("h1")).toBeVisible();
    await expect(page.locator("#process-btn")).toBeDisabled();
    await expect(page.locator("#library-status")).toContainText("PDF.js 6.4.299");
    await expect(page.locator("#library-status")).toContainText("local");
  }
  expect(errors).toEqual([]);
});

test("unir PDF conserva el orden elegido y valida las páginas", async ({ page, errors }) => {
  await openTool(page, "/unir-pdf");

  const first = await buildPdf(page, { pages: 2, width: 410, height: 610, label: "Primero" });
  const second = await buildPdf(page, { pages: 1, width: 310, height: 510, label: "Segundo" });

  await upload(page, [
    { name: "primero.pdf", mimeType: "application/pdf", buffer: first },
    { name: "segundo.pdf", mimeType: "application/pdf", buffer: second },
  ]);

  await expect(page.locator("#file-list li")).toHaveCount(2);
  await expect(page.locator("#file-list li").nth(0)).toContainText("primero.pdf");
  await expect(page.locator("#file-list li").nth(1)).toContainText("segundo.pdf");

  // Baja el primer documento para que el resultado empiece por el segundo.
  await page
    .locator("#file-list li")
    .nth(0)
    .getByRole("button", { name: "Bajar archivo" })
    .click();
  await expect(page.locator("#file-list li").nth(0)).toContainText("segundo.pdf");

  const { name, buffer } = await runAndDownload(page);
  expect(name).toBe("documento-unido.pdf");
  const info = await inspectPdf(page, buffer);
  expect(info.pageCount).toBe(3);
  expect(info.sizes).toEqual([
    [310, 510],
    [410, 610],
    [410, 610],
  ]);
  expect(info.producer).toContain("Fastools");
  expect(errors).toEqual([]);
});

test("dividir PDF respeta los rangos escritos", async ({ page, errors }) => {
  await openTool(page, "/dividir-pdf");

  const source = await buildPdf(page, {
    pages: 3,
    sizes: [
      [410, 610],
      [420, 620],
      [430, 630],
    ],
    label: "Original",
  });

  await upload(page, [{ name: "informe.pdf", mimeType: "application/pdf", buffer: source }]);
  await expect(page.locator("#file-list li")).toHaveCount(1);

  await page.locator("#page-ranges").fill("3, 1");
  await expect(page.locator("#range-summary")).toContainText("2 de 3");

  const { name, buffer } = await runAndDownload(page);
  expect(name).toBe("informe-paginas.pdf");
  const info = await inspectPdf(page, buffer);
  expect(info.pageCount).toBe(2);
  expect(info.sizes).toEqual([
    [430, 630],
    [410, 610],
  ]);
  expect(errors).toEqual([]);
});

test("imágenes a PDF crea una página por imagen", async ({ page, errors }) => {
  const png = await buildImage(page, { type: "image/png", width: 320, height: 240 });
  const jpg = await buildImage(page, {
    type: "image/jpeg",
    width: 300,
    height: 200,
    color: "#f59e0b",
  });

  await openTool(page, "/imagenes-a-pdf");
  await upload(page, [
    { name: "captura.png", mimeType: "image/png", buffer: png },
    { name: "foto.jpg", mimeType: "image/jpeg", buffer: jpg },
  ]);
  await expect(page.locator("#file-list li")).toHaveCount(2);
  await page.locator("#page-size").selectOption("a4-landscape");

  const { name, buffer } = await runAndDownload(page);
  expect(name).toBe("imagenes-a-pdf.pdf");
  const info = await inspectPdf(page, buffer);
  expect(info.pageCount).toBe(2);
  expect(info.sizes).toEqual([
    [842, 595],
    [842, 595],
  ]);
  expect(errors).toEqual([]);
});

test("PDF a JPG descarga un JPG o un ZIP válido", async ({ page, errors }) => {
  await openTool(page, "/pdf-a-jpg");

  const twoPages = await buildPdf(page, { pages: 2, width: 420, height: 600 });

  await upload(page, [{ name: "informe.pdf", mimeType: "application/pdf", buffer: twoPages }]);
  await expect(page.locator("#file-list li")).toHaveCount(1);

  const zipped = await runAndDownload(page);
  expect(zipped.name).toBe("informe-jpg.zip");
  expect(zipped.buffer.subarray(0, 4).toString("binary")).toBe("PK\u0003\u0004");
  expect(zipEntryCount(zipped.buffer)).toBe(2);

  await openTool(page, "/pdf-a-jpg");
  const onePage = await buildPdf(page, { pages: 1, width: 420, height: 600 });
  await upload(page, [{ name: "suelto.pdf", mimeType: "application/pdf", buffer: onePage }]);
  const single = await runAndDownload(page);
  expect(single.name).toBe("suelto-pagina-01.jpg");
  expect(single.buffer.subarray(0, 3).toString("binary")).toBe("\u00ff\u00d8\u00ff");
  expect(errors).toEqual([]);
});

test("comprimir PDF reduce el peso y conserva las páginas", async ({
  page,
  errors,
  requests,
  baseURL,
}) => {
  await openTool(page, "/comprimir-pdf");

  const source = await buildPdf(page, {
    pages: 2,
    width: 595,
    height: 842,
    withImage: true,
    label: "Escaneo",
  });

  await upload(page, [{ name: "escaneo.pdf", mimeType: "application/pdf", buffer: source }]);
  await expect(page.locator("#file-list li")).toHaveCount(1);

  await page.locator("#jpg-quality").evaluate((input) => {
    input.value = "40";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.locator("#render-scale").selectOption("1");
  await expect(page.locator("#jpg-quality-value")).toHaveText("40 %");

  const { name, buffer } = await runAndDownload(page);
  expect(name).toBe("escaneo-comprimido.pdf");
  const info = await inspectPdf(page, buffer);
  expect(info.pageCount).toBe(2);
  expect(info.sizes).toEqual([
    [595, 842],
    [595, 842],
  ]);
  expect(info.producer).toContain("Fastools");
  expect(buffer.length).toBeLessThan(source.length);
  await expect(page.locator("#out-saved")).toContainText("menos");

  expectLocalOnly(requests, baseURL);
  expect(errors).toEqual([]);
});

test("un PDF que no es válido muestra un error claro", async ({ page, errors }) => {
  await openTool(page, "/dividir-pdf");
  await upload(
    page,
    [
      {
        name: "falso.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("esto no es un documento PDF", "utf8"),
      },
    ],
    { waitForList: false }
  );

  await expect(page.locator("#error-box")).toBeVisible();
  await expect(page.locator("#error-text")).toContainText("PDF");
  expect(errors).toEqual([]);
});
