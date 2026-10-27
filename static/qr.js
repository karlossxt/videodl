/* Generador de códigos QR.
   El contenido se construye en el navegador; solo se envía al servidor para
   dibujar la imagen (segno) y no se guarda. */
(function () {
  "use strict";

  const {
    $,
    t,
    showToast,
    showError,
    clearError,
    fetchWithTimeout,
    errorFromResponse,
    triggerDownload,
  } = window.VD;
  const Core = window.QRCore;

  const tabs = Array.from(document.querySelectorAll("[data-qr-type]"));
  const panels = Array.from(document.querySelectorAll("[data-qr-panel]"));
  const image = $("qr-image");
  const empty = $("qr-empty");
  const payloadEl = $("qr-payload");
  const statusEl = $("qr-status");
  const hintEl = $("qr-hint");
  const contrastEl = $("qr-contrast");
  const downloadBtn = $("qr-download");
  const copyBtn = $("qr-copy");

  const DEBOUNCE_MS = 450;
  let currentType = "text";
  let currentPayload = "";
  let currentFormat = "png";
  let qrUrl = null;
  let lastKey = "";
  let runId = 0;
  let timer = null;

  // -------------------------------------------------------------------------
  // Lectura del formulario
  // -------------------------------------------------------------------------

  function readPayload(type) {
    if (type === "text") {
      return Core.buildPayload("text", { text: $("qr-text").value });
    }
    if (type === "wifi") {
      return Core.buildPayload("wifi", {
        ssid: $("qr-wifi-ssid").value,
        password: $("qr-wifi-password").value,
        encryption: $("qr-wifi-encryption").value,
        hidden: $("qr-wifi-hidden").checked,
      });
    }
    if (type === "email") {
      return Core.buildPayload("email", {
        email: $("qr-email-to").value,
        subject: $("qr-email-subject").value,
        body: $("qr-email-body").value,
      });
    }
    if (type === "phone") {
      return Core.buildPayload("phone", { phone: $("qr-phone-number").value });
    }
    return Core.buildPayload("sms", {
      phone: $("qr-sms-number").value,
      message: $("qr-sms-message").value,
    });
  }

  function readStyle() {
    return {
      size: Number($("qr-size").value) || 512,
      margin: Number($("qr-margin").value) || 0,
      error: $("qr-error").value,
      dark: $("qr-dark").value,
      light: $("qr-light").value,
      format: $("qr-format").value,
    };
  }

  function requestKey(payload, style) {
    return JSON.stringify({ payload, ...style });
  }

  // -------------------------------------------------------------------------
  // Estado visual
  // -------------------------------------------------------------------------

  function setStatus(text) {
    statusEl.textContent = text;
  }

  function setEnabled(enabled) {
    downloadBtn.disabled = !enabled || !qrUrl;
    copyBtn.disabled = !enabled || !currentPayload;
  }

  function clearPreview() {
    clearTimeout(timer);
    runId += 1;
    lastKey = "";
    if (qrUrl) {
      URL.revokeObjectURL(qrUrl);
      qrUrl = null;
    }
    image.removeAttribute("src");
    image.classList.add("hidden");
    empty.classList.remove("hidden");
    payloadEl.textContent = "—";
    setEnabled(false);
  }

  function applyContrastWarning() {
    const style = readStyle();
    const problem = Core.styleProblem(style.dark, style.light);
    contrastEl.textContent = problem ? `⚠ ${problem}` : "";
    contrastEl.classList.toggle("hidden", !problem);
    return !problem;
  }

  // -------------------------------------------------------------------------
  // Generación en el servidor
  // -------------------------------------------------------------------------

  function schedule(payload, { immediate = false } = {}) {
    const style = readStyle();
    const key = requestKey(payload, style);
    if (key === lastKey) return;
    clearTimeout(timer);
    if (!applyContrastWarning()) {
      clearPreview();
      setStatus(t("qr.checkColors", "Revisa los colores"));
      return;
    }
    const run = () => generate(payload, style, key);
    if (immediate) run();
    else timer = setTimeout(run, DEBOUNCE_MS);
  }

  async function generate(payload, style, key) {
    const id = ++runId;
    currentPayload = payload;
    currentFormat = style.format;
    setStatus(t("qr.generating", "Generando…"));
    hintEl.textContent = t("qr.drawing", "Dibujando el código QR…");

    try {
      const res = await fetchWithTimeout(
        "/api/qr",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            data: payload,
            size: style.size,
            margin: style.margin,
            error: style.error,
            dark: style.dark,
            light: style.light,
            format: style.format,
          }),
        },
        20000
      );
      if (!res.ok) {
        throw await errorFromResponse(
          res,
          t("qr.generateFailed", "No se pudo generar el código QR.")
        );
      }
      const blob = await res.blob();
      if (id !== runId) return;

      if (qrUrl) URL.revokeObjectURL(qrUrl);
      qrUrl = URL.createObjectURL(blob);
      lastKey = key;

      image.src = qrUrl;
      image.classList.remove("hidden");
      empty.classList.add("hidden");
      payloadEl.textContent = payload;
      setStatus(t("qr.readyStatus", "QR listo"));
      hintEl.textContent = t(
        "qr.readyHint",
        `Vista previa en ${style.format.toUpperCase()}. Si vas a imprimirlo, usa un tamaño grande y deja margen alrededor.`,
        { format: style.format.toUpperCase() }
      );
      setEnabled(true);
      clearError();
    } catch (err) {
      if (id !== runId) return;
      clearPreview();
      setStatus(t("qr.failedStatus", "No se pudo generar"));
      hintEl.textContent = t(
        "qr.failedHint",
        "Prueba a acortar el contenido o a usar colores con más contraste."
      );
      showError(
        err.message || t("qr.generateFailed", "No se pudo generar el código QR.")
      );
    }
  }

  function refresh({ immediate = false } = {}) {
    clearError();
    const payload = readPayload(currentType);
    const validation = Core.validatePayload(currentType, payload);

    if (!validation.ok) {
      clearPreview();
      currentPayload = payload;
      payloadEl.textContent = payload || "—";
      setStatus(
        payload
          ? validation.message
          : t("qr.enterContent", "Escribe el contenido")
      );
      if (payload) hintEl.textContent = validation.message;
      else {
        hintEl.textContent = t(
          "qr.emptyHint",
          "El QR aparecerá aquí mientras escribes."
        );
      }
      setEnabled(false);
      return;
    }

    currentPayload = payload;
    payloadEl.textContent = payload;
    setStatus(t("qr.preparing", "Preparando vista previa…"));
    setEnabled(false);
    schedule(payload, { immediate });
  }

  // -------------------------------------------------------------------------
  // Pestañas y controles
  // -------------------------------------------------------------------------

  function setType(type) {
    currentType = type;
    tabs.forEach((tab) => {
      const active = tab.dataset.qrType === type;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    panels.forEach((panel) => {
      panel.classList.toggle("hidden", panel.dataset.qrPanel !== type);
    });
    clearError();
    refresh();
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => setType(tab.dataset.qrType));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const index = tabs.indexOf(tab);
      const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : (index - 1 + tabs.length) % tabs.length;
      tabs[next].focus();
      setType(tabs[next].dataset.qrType);
    });
  });

  document.querySelectorAll("[data-qr-field]").forEach((field) => {
    field.addEventListener("input", () => refresh());
    field.addEventListener("change", () => refresh());
  });

  ["qr-size", "qr-margin", "qr-error", "qr-format", "qr-dark", "qr-light"].forEach((id) => {
    $(id).addEventListener("change", () => refresh({ immediate: true }));
    $(id).addEventListener("input", () => refresh({ immediate: true }));
  });

  $("qr-reset-colors").addEventListener("click", () => {
    $("qr-dark").value = "#000000";
    $("qr-light").value = "#ffffff";
    refresh({ immediate: true });
  });

  $("qr-wifi-encryption").addEventListener("change", () => {
    const open = $("qr-wifi-encryption").value === "nopass";
    $("qr-wifi-password").disabled = open;
    if (open) $("qr-wifi-password").value = "";
    refresh();
  });

  // -------------------------------------------------------------------------
  // Acciones
  // -------------------------------------------------------------------------

  downloadBtn.addEventListener("click", () => {
    if (!qrUrl) {
      showToast(t("qr.notReady", "El código QR aún no está listo"), {
        error: true,
      });
      return;
    }
    const name = t("qr.downloadName", "codigo-qr");
    triggerDownload(qrUrl, `${name}.${currentFormat === "svg" ? "svg" : "png"}`);
    showToast(t("qr.downloading", "Descargando el código QR…"));
  });

  copyBtn.addEventListener("click", async () => {
    if (!currentPayload) return;
    try {
      await navigator.clipboard.writeText(currentPayload);
      showToast(t("qr.copied", "Contenido copiado"));
    } catch {
      showToast(t("qr.copyFailed", "No se pudo copiar el contenido"), {
        error: true,
      });
    }
  });

  // Estado inicial.
  setEnabled(false);
  applyContrastWarning();
  refresh();
})();
