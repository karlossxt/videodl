/* Compresor de vídeo para WhatsApp / Discord / Telegram / email.
   Utilidades compartidas en common.js (window.VD). */

const {
  $,
  showToast,
  showError,
  clearError,
  formatBytes,
  fmtClock,
  fetchWithTimeout,
  pollJob: pollJobBase,
  linkDropzone,
  isAllowedVideo,
  triggerDownload,
} = window.VD;

const dropzone = $("dropzone");
const fileInput = $("file-input");
const fileCard = $("file-card");
const compressBtn = $("compress-btn");
const actionHint = $("action-hint");
const progressBox = $("progress");
const resultSection = $("result");
const maxHeightSel = $("max-height");
const qualitySel = $("quality-mode");

let maxUploadMb = 200;
let selectedFile = null;
let targetMb = 16;
let jobId = null;
let pollRunId = 0;
let outUrl = null;
let outName = "video-comprimido.mp4";
let localPreviewUrl = null;

$("error-close").addEventListener("click", clearError);

// ---------------------------------------------------------------------------
// Configuración desde el servidor (límite de subida real)
// ---------------------------------------------------------------------------

(async function loadConfig() {
  try {
    const res = await fetchWithTimeout("/api/compress/presets", {}, 15000);
    if (!res.ok) return;
    const cfg = await res.json();
    if (cfg.max_upload_mb) {
      maxUploadMb = cfg.max_upload_mb;
      $("limit-hint").textContent = `Máximo ${maxUploadMb} MB por archivo`;
      $("limit-hint-2").textContent = `${maxUploadMb} MB`;
    }
  } catch {
    /* sin conexión: se usan los valores por defecto */
  }
})();

// ---------------------------------------------------------------------------
// Paso 1 · elegir archivo
// ---------------------------------------------------------------------------

linkDropzone(dropzone, fileInput, handleFile);

function handleFile(file) {
  clearError();

  if (!isAllowedVideo(file.name)) {
    showError("Formato no compatible. Sube un vídeo MP4, MOV, MKV, WEBM, AVI…");
    return;
  }
  if (file.size > maxUploadMb * 1024 * 1024) {
    showError(`El archivo pesa ${formatBytes(file.size)} y el máximo es ${maxUploadMb} MB.`);
    return;
  }

  selectedFile = file;
  resetResult();

  const preview = $("file-preview");
  if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
  localPreviewUrl = URL.createObjectURL(file);
  preview.src = localPreviewUrl;

  $("file-name").textContent = file.name;
  $("file-meta").textContent = formatBytes(file.size);

  preview.onloadedmetadata = () => {
    const parts = [formatBytes(file.size)];
    if (preview.videoWidth) parts.push(`${preview.videoWidth}×${preview.videoHeight}`);
    if (preview.duration && isFinite(preview.duration)) parts.push(fmtClock(preview.duration));
    $("file-meta").textContent = parts.join(" · ");
  };

  fileCard.classList.remove("hidden");
  compressBtn.disabled = false;
  actionHint.textContent = `Objetivo: que quepa en ${targetMb} MB.`;
}

function clearFile() {
  selectedFile = null;
  fileInput.value = "";
  fileCard.classList.add("hidden");
  compressBtn.disabled = true;
  actionHint.textContent = "Elige primero un vídeo.";
  if (localPreviewUrl) {
    URL.revokeObjectURL(localPreviewUrl);
    localPreviewUrl = null;
  }
}

$("file-clear").addEventListener("click", clearFile);

// ---------------------------------------------------------------------------
// Paso 2 · tamaño objetivo
// ---------------------------------------------------------------------------

document.querySelectorAll(".preset").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".preset").forEach((b) => {
      b.classList.remove("active");
      b.setAttribute("aria-pressed", "false");
    });
    btn.classList.add("active");
    btn.setAttribute("aria-pressed", "true");

    targetMb =
      btn.dataset.mb === "custom"
        ? clampMb(parseFloat($("custom-mb").value))
        : clampMb(parseFloat(btn.dataset.mb));

    actionHint.textContent = selectedFile
      ? `Objetivo: que quepa en ${targetMb} MB.`
      : "Elige primero un vídeo.";
  });
});

$("custom-mb").addEventListener("input", () => {
  const custom = document.querySelector(".preset.custom");
  if (!custom.classList.contains("active")) return;
  targetMb = clampMb(parseFloat($("custom-mb").value));
  actionHint.textContent = selectedFile
    ? `Objetivo: que quepa en ${targetMb} MB.`
    : "Elige primero un vídeo.";
});

// Estado inicial de accesibilidad de los presets.
document.querySelectorAll(".preset").forEach((b) =>
  b.setAttribute("aria-pressed", b.classList.contains("active") ? "true" : "false")
);

function clampMb(value) {
  const n = Number(value);
  if (!isFinite(n) || n < 1) return 1;
  if (n > 200) return 200;
  return Math.round(n * 10) / 10;
}

// ---------------------------------------------------------------------------
// Paso 3 · comprimir
// ---------------------------------------------------------------------------

compressBtn.addEventListener("click", () => {
  if (!selectedFile) return;

  clearError();
  resetResult();
  compressBtn.disabled = true;
  progressBox.classList.remove("hidden");
  $("pr-fill").style.width = "0%";
  $("pr-track").setAttribute("aria-valuenow", "0");
  $("pr-percent").textContent = "0%";
  $("pr-status").textContent = "Subiendo el vídeo…";
  $("pr-detail").textContent = formatBytes(selectedFile.size);

  const form = new FormData();
  form.append("file", selectedFile, selectedFile.name);
  form.append("target_mb", String(targetMb));
  form.append("max_height", maxHeightSel.value);
  form.append("quality_mode", qualitySel.value);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/compress");
  // Tiempo máximo para subir + empezar a procesar. Evita un cuelgue silencioso.
  xhr.timeout = 10 * 60 * 1000;

  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const pct = (e.loaded / e.total) * 100;
    $("pr-fill").style.width = `${pct}%`;
    $("pr-percent").textContent = `${pct.toFixed(0)}%`;
    $("pr-detail").textContent = `${formatBytes(e.loaded)} / ${formatBytes(e.total)}`;
  };

  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      try {
        jobId = JSON.parse(xhr.responseText).id;
        $("pr-status").textContent = "Analizando el vídeo…";
        $("pr-detail").textContent = "Preparando la compresión";
        pollJob();
        return;
      } catch {
        /* respuesta ilegible */
      }
    }
    failCompress(extractError(xhr));
  };

  xhr.onerror = () => failCompress("No se pudo enviar el vídeo al servidor. Revisa tu conexión.");
  xhr.ontimeout = () => failCompress("La subida tardó demasiado. Prueba con un vídeo más pequeño.");
  xhr.send(form);
});

function extractError(xhr) {
  try {
    const data = JSON.parse(xhr.responseText);
    if (data.detail) return data.detail;
  } catch {
    /* sin cuerpo JSON */
  }
  if (xhr.status === 413) return `El archivo supera el límite de ${maxUploadMb} MB.`;
  return `No se pudo comprimir el vídeo (error ${xhr.status || "de red"}).`;
}

function failCompress(msg) {
  progressBox.classList.add("hidden");
  compressBtn.disabled = !selectedFile;
  showError(msg);
}

async function pollJob() {
  const runId = ++pollRunId;
  try {
    const job = await pollJobBase({
      intervalMs: 700,
      fetcher: async () => {
        const res = await fetch(`/api/compress/${jobId}`);
        if (!res.ok) throw new Error("no disponible");
        return res.json();
      },
      onUpdate: (j) => {
        if (runId === pollRunId) updateCompressProgress(j);
      },
    });
    if (runId !== pollRunId) return;

    if (job.status === "finished") finishCompress(job);
    else if (job.status === "error") {
      progressBox.classList.add("hidden");
      compressBtn.disabled = false;
      showError(job.error || "No se pudo comprimir el vídeo.");
    } else if (job.status === "cancelled") {
      progressBox.classList.add("hidden");
      compressBtn.disabled = false;
      showToast("Compresión cancelada");
    }
  } catch (err) {
    if (runId !== pollRunId) return;
    progressBox.classList.add("hidden");
    compressBtn.disabled = false;
    showError(err.message);
  }
}

function updateCompressProgress(job) {
  const pct = Math.max(0, Math.min(100, Number(job.percent) || 0));
  $("pr-fill").style.width = `${pct}%`;
  $("pr-percent").textContent = `${pct.toFixed(0)}%`;
  $("pr-track").setAttribute("aria-valuenow", String(Math.round(pct)));
  $("pr-status").textContent = job.message || "Comprimiendo…";
  if (job.status === "compressing") {
    $("pr-detail").textContent = `Objetivo: ${job.target_mb} MB`;
  }
}

$("pr-cancel").addEventListener("click", async () => {
  if (!jobId) return;
  $("pr-status").textContent = "Cancelando…";
  try {
    await fetch(`/api/compress/${jobId}/cancel`, { method: "POST" });
  } catch {
    /* el sondeo detectará el estado final */
  }
});

async function finishCompress(job) {
  outName = job.filename || "video-comprimido.mp4";

  // Se descarga el resultado como blob: así el servidor puede borrar el
  // archivo inmediatamente y el botón "Descargar" funciona al instante.
  let blob = null;
  try {
    const res = await fetchWithTimeout(`/api/compress/${job.id}/file`, {}, 60000);
    if (res.ok) blob = await res.blob();
  } catch {
    /* se intentará descargar directo */
  }

  progressBox.classList.add("hidden");
  compressBtn.disabled = false;

  if (!blob) {
    triggerDownload(`/api/compress/${job.id}/file`, outName);
    showToast("Descarga iniciada");
    return;
  }

  if (outUrl) URL.revokeObjectURL(outUrl);
  outUrl = URL.createObjectURL(blob);
  $("out-preview").src = outUrl;

  $("out-before").textContent = formatBytes(job.input_size);
  $("out-after").textContent = formatBytes(job.output_size);

  const saved = job.input_size > 0 ? (1 - job.output_size / job.input_size) * 100 : 0;
  $("out-saved").textContent =
    saved > 0
      ? `−${saved.toFixed(0)} % de tamaño (${formatBytes(job.input_size - job.output_size)} menos)`
      : "Sin cambios de tamaño";

  resultSection.classList.remove("hidden");
  resultSection.scrollIntoView({ behavior: "smooth", block: "center" });
  showToast("¡Vídeo comprimido listo!");
}

$("download-btn").addEventListener("click", () => {
  if (!outUrl) {
    showToast("La descarga aún no está lista", { error: true });
    return;
  }
  triggerDownload(outUrl, outName);
  showToast("Descargando el vídeo comprimido…");
});

$("again-btn").addEventListener("click", () => {
  clearFile();
  resetResult();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

function resetResult() {
  // Invalida cualquier sondeo en curso para que no siga consultando un trabajo viejo.
  pollRunId++;
  resultSection.classList.add("hidden");
  $("out-preview").removeAttribute("src");
  if (outUrl) {
    URL.revokeObjectURL(outUrl);
    outUrl = null;
  }
  jobId = null;
}
