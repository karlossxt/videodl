/* Utilidades compartidas por todas las páginas de FasTools.
   Expone un único objeto global `VD` para evitar duplicar código entre
   app.js, comprimir.js y clips.js. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const ALLOWED_VIDEO = [
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
    ".mpg", ".mpeg", ".flv", ".ts", ".3gp", ".wmv",
  ];

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  // -------------------------------------------------------------------------
  // Avisos
  // -------------------------------------------------------------------------

  let toastTimer = null;
  function showToast(msg, opts = {}) {
    const el = $("toast");
    if (!el) return;
    const isError = opts.error === true;
    el.textContent = `${isError ? "⚠" : "✓"} ${msg}`;
    el.classList.toggle("toast-error", isError);
    el.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.add("hidden"), isError ? 4000 : 3000);
  }

  function showError(msg) {
    const box = $("error-box");
    const text = $("error-text");
    if (!box || !text) return;
    text.textContent = msg;
    box.classList.remove("hidden");
    box.setAttribute("role", "alert");
    // Llevar la vista al mensaje: puede estar fuera de pantalla.
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function clearError() {
    const box = $("error-box");
    if (box) box.classList.add("hidden");
  }

  // -------------------------------------------------------------------------
  // Formato de datos
  // -------------------------------------------------------------------------

  function formatBytes(bytes) {
    if (bytes === null || bytes === undefined || isNaN(bytes)) return "—";
    let n = Number(bytes);
    if (n < 1024) return `${Math.round(n)} B`;
    const units = ["KB", "MB", "GB", "TB"];
    let i = -1;
    do {
      n /= 1024;
      i++;
    } while (n >= 1024 && i < units.length - 1);
    return `${n.toFixed(n >= 100 ? 0 : 1)} ${units[i]}`;
  }

  /** Segundos -> m:ss o h:mm:ss. */
  function fmtClock(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = String(total % 60).padStart(2, "0");
    return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
  }

  // -------------------------------------------------------------------------
  // Red: fetch con timeout y errores legibles
  // -------------------------------------------------------------------------

  async function fetchWithTimeout(url, options = {}, timeoutMs = 60000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } catch (err) {
      if (err && err.name === "AbortError") {
        throw new Error("El servidor tardó demasiado en responder. Inténtalo de nuevo.");
      }
      throw new Error("No se pudo conectar con el servidor. Revisa tu conexión.");
    } finally {
      clearTimeout(timer);
    }
  }

  async function readJson(res) {
    try {
      return await res.json();
    } catch {
      return null;
    }
  }

  /** Error legible a partir de una respuesta, aunque el cuerpo no sea JSON. */
  async function errorFromResponse(res, fallback) {
    const data = await readJson(res);
    if (data && data.detail) return new Error(data.detail);
    return new Error(fallback || `Error ${res.status}`);
  }

  async function api(path, body, { timeoutMs = 60000 } = {}) {
    const res = await fetchWithTimeout(
      path,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
      timeoutMs
    );
    if (!res.ok) throw await errorFromResponse(res, "Error inesperado");
    return res;
  }

  /**
   * Sondea un trabajo hasta que termina.
   * Usa setTimeout (nunca setInterval) para no solapar peticiones y se rinde
   * tras `timeoutMs` en lugar de sondear para siempre.
   */
  function pollJob({ fetcher, onUpdate, intervalMs = 700, timeoutMs = 30 * 60 * 1000 }) {
    return new Promise((resolve, reject) => {
      const started = Date.now();
      const tick = async () => {
        let job;
        try {
          job = await fetcher();
        } catch (err) {
          if (Date.now() - started > timeoutMs) {
            return reject(new Error("El trabajo tardó demasiado. Inténtalo de nuevo."));
          }
          setTimeout(tick, intervalMs);
          return;
        }
        if (onUpdate) onUpdate(job);
        if (["finished", "error", "cancelled"].includes(job.status)) {
          return resolve(job);
        }
        if (Date.now() - started > timeoutMs) {
          return reject(new Error("El trabajo tardó demasiado. Inténtalo de nuevo."));
        }
        setTimeout(tick, intervalMs);
      };
      tick();
    });
  }

  // -------------------------------------------------------------------------
  // Descargas
  // -------------------------------------------------------------------------

  function triggerDownload(href, filename) {
    const a = document.createElement("a");
    a.href = href;
    if (filename) a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  /** Guarda una respuesta como archivo respetando Content-Disposition. */
  async function saveResponseAsFile(res, fallbackName) {
    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename\*=UTF-8''([^;]+)|filename="([^"]+)"/i);
    const filename = match ? (match[1] ? decodeURIComponent(match[1]) : match[2]) : fallbackName;

    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    triggerDownload(blobUrl, filename);
    // Se revoca con un pequeño margen para no cancelar la descarga en algunos navegadores.
    setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
    return filename;
  }

  // -------------------------------------------------------------------------
  // Zona de arrastre para archivos (accesible con teclado)
  // -------------------------------------------------------------------------

  function linkDropzone(zone, input, onFile) {
    if (!zone || !input) return;
    zone.addEventListener("click", (e) => {
      if (e.target !== input) input.click();
    });
    zone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        input.click();
      }
    });
    ["dragenter", "dragover"].forEach((ev) =>
      zone.addEventListener(ev, (e) => {
        e.preventDefault();
        zone.classList.add("dragover");
      })
    );
    ["dragleave", "drop"].forEach((ev) =>
      zone.addEventListener(ev, (e) => {
        e.preventDefault();
        zone.classList.remove("dragover");
      })
    );
    zone.addEventListener("drop", (e) => {
      const file = e.dataTransfer?.files?.[0];
      if (file) onFile(file);
    });
    input.addEventListener("change", () => {
      if (input.files && input.files[0]) onFile(input.files[0]);
    });
  }

  function isAllowedVideo(name) {
    const lower = (name || "").toLowerCase();
    return ALLOWED_VIDEO.some((ext) => lower.endsWith(ext));
  }

  window.VD = {
    $,
    escapeHtml,
    showToast,
    showError,
    clearError,
    formatBytes,
    fmtClock,
    fetchWithTimeout,
    readJson,
    errorFromResponse,
    api,
    pollJob,
    triggerDownload,
    saveResponseAsFile,
    linkDropzone,
    isAllowedVideo,
    ALLOWED_VIDEO,
  };
})();
