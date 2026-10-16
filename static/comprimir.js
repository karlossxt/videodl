/* Compresor de vídeo para WhatsApp / Discord / Telegram / email. */

const $ = (id) => document.getElementById(id);

const dropzone = $("dropzone");
const fileInput = $("file-input");
const fileCard = $("file-card");
const compressBtn = $("compress-btn");
const actionHint = $("action-hint");
const progressBox = $("progress");
const resultSection = $("result");
const maxHeightSel = $("max-height");
const qualitySel = $("quality-mode");

const ALLOWED = [".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".flv", ".ts", ".3gp", ".wmv"];

let maxUploadMb = 200;
let selectedFile = null;
let targetMb = 16;
let jobId = null;
let pollTimer = null;
let outUrl = null;
let outName = "video-comprimido.mp4";
let localPreviewUrl = null;

// ---------------------------------------------------------------------------
// Utilidades de UI
// ---------------------------------------------------------------------------

let toastTimer = null;
function showToast(msg) {
  $("toast").textContent = `✓ ${msg}`;
  $("toast").classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("toast").classList.add("hidden"), 3200);
}

function showError(msg) {
  $("error-text").textContent = msg;
  $("error-box").classList.remove("hidden");
}

function clearError() {
  $("error-box").classList.add("hidden");
}

$("error-close").addEventListener("click", clearError);

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined || isNaN(bytes)) return "—";
  let n = Number(bytes);
  if (n < 1024) return `${Math.round(n)} B`;
  const units = ["KB", "MB", "GB"];
  let i = -1;
  do { n /= 1024; i++; } while (n >= 1024 && i < units.length - 1);
  return `${n.toFixed(n >= 100 ? 0 : 1)} ${units[i]}`;
}

function fmtDuration(seconds) {
  const total = Math.max(0, Math.round(seconds || 0));
  const m = Math.floor(total / 60);
  const s = String(total % 60).padStart(2, "0");
  return `${m}:${s}`;
}

// ---------------------------------------------------------------------------
// Configuración desde el servidor (límite de subida real)
// ---------------------------------------------------------------------------

(async function loadConfig() {
  try {
    const res = await fetch("/api/compress/presets");
    if (res.ok) {
      const cfg = await res.json();
      if (cfg.max_upload_mb) {
        maxUploadMb = cfg.max_upload_mb;
        $("limit-hint").textContent = `Máximo ${maxUploadMb} MB por archivo`;
        $("limit-hint-2").textContent = `${maxUploadMb} MB`;
      }
    }
  } catch { /* sin conexión: se usan los valores por defecto */ }
})();

// ---------------------------------------------------------------------------
// Paso 1 · elegir archivo
// ---------------------------------------------------------------------------

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") fileInput.click();
});

fileInput.addEventListener("change", () => {
  if (fileInput.files && fileInput.files[0]) handleFile(fileInput.files[0]);
});

["dragenter", "dragover"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);

["dragleave", "drop"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);

dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer?.files?.[0];
  if (file) handleFile(file);
});

function handleFile(file) {
  clearError();

  const name = (file.name || "").toLowerCase();
  const okExt = ALLOWED.some((ext) => name.endsWith(ext));
  if (!okExt) {
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
    if (preview.duration && isFinite(preview.duration)) parts.push(fmtDuration(preview.duration));
    $("file-meta").textContent = parts.join(" · ");
  };

  fileCard.classList.remove("hidden");
  compressBtn.disabled = false;
  actionHint.textContent = `Objetivo: que quepa en ${targetMb} MB.`;
}

$("file-clear").addEventListener("click", () => {
  selectedFile = null;
  fileInput.value = "";
  fileCard.classList.add("hidden");
  compressBtn.disabled = true;
  actionHint.textContent = "Elige primero un vídeo.";
  if (localPreviewUrl) {
    URL.revokeObjectURL(localPreviewUrl);
    localPreviewUrl = null;
  }
});

// ---------------------------------------------------------------------------
// Paso 2 · tamaño objetivo
// ---------------------------------------------------------------------------

document.querySelectorAll(".preset").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".preset").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");

    if (btn.dataset.mb === "custom") {
      targetMb = clampMb(parseFloat($("custom-mb").value));
    } else {
      targetMb = clampMb(parseFloat(btn.dataset.mb));
    }
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

  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const pct = (e.loaded / e.total) * 100;
    $("pr-fill").style.width = `${pct}%`;
    $("pr-percent").textContent = `${pct.toFixed(0)}%`;
    $("pr-detail").textContent =
      `${formatBytes(e.loaded)} / ${formatBytes(e.total)}`;
  };

  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      try {
        const data = JSON.parse(xhr.responseText);
        jobId = data.id;
        $("pr-status").textContent = "Analizando el vídeo…";
        $("pr-detail").textContent = "Preparando la compresión";
        pollJob();
        return;
      } catch { /* respuesta ilegible */ }
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
  } catch { /* sin cuerpo JSON */ }
  if (xhr.status === 413) return `El archivo supera el límite de ${maxUploadMb} MB.`;
  return `No se pudo comprimir el vídeo (error ${xhr.status || "de red"}).`;
}

function failCompress(msg) {
  progressBox.classList.add("hidden");
  compressBtn.disabled = !selectedFile ? true : false;
  showError(msg);
}

function pollJob() {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    let job;
    try {
      const res = await fetch(`/api/compress/${jobId}`);
      if (!res.ok) throw new Error("no disponible");
      job = await res.json();
    } catch {
      return; // fallo puntual: se reintenta en el siguiente ciclo
    }

    const pct = Math.max(0, Math.min(100, Number(job.percent) || 0));
    $("pr-fill").style.width = `${pct}%`;
    $("pr-percent").textContent = `${pct.toFixed(0)}%`;
    $("pr-status").textContent = job.message || "Comprimiendo…";
    if (job.status === "compressing") {
      $("pr-detail").textContent = `Objetivo: ${job.target_mb} MB`;
    }

    if (job.status === "finished") {
      clearInterval(pollTimer);
      finishCompress(job);
    } else if (job.status === "error") {
      clearInterval(pollTimer);
      progressBox.classList.add("hidden");
      compressBtn.disabled = false;
      showError(job.error || "No se pudo comprimir el vídeo.");
    } else if (job.status === "cancelled") {
      clearInterval(pollTimer);
      progressBox.classList.add("hidden");
      compressBtn.disabled = false;
      showToast("Compresión cancelada");
    }
  }, 700);
}

$("pr-cancel").addEventListener("click", async () => {
  if (!jobId) return;
  $("pr-status").textContent = "Cancelando…";
  try {
    await fetch(`/api/compress/${jobId}/cancel`, { method: "POST" });
  } catch { /* el sondeo detectará el estado final */ }
});

async function finishCompress(job) {
  outName = job.filename || "video-comprimido.mp4";

  // Se descarga el resultado como blob: así el servidor puede borrar el
  // archivo inmediatamente y el botón "Descargar" funciona al instante.
  let blob = null;
  try {
    const res = await fetch(`/api/compress/${job.id}/file`);
    if (res.ok) blob = await res.blob();
  } catch { /* se intentará descargar directo */ }

  if (blob) {
    if (outUrl) URL.revokeObjectURL(outUrl);
    outUrl = URL.createObjectURL(blob);
    $("out-preview").src = outUrl;
  } else {
    const a = document.createElement("a");
    a.href = `/api/compress/${job.id}/file`;
    a.download = outName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    progressBox.classList.add("hidden");
    compressBtn.disabled = false;
    showToast("Descarga iniciada");
    return;
  }

  progressBox.classList.add("hidden");
  compressBtn.disabled = false;

  $("out-before").textContent = formatBytes(job.input_size);
  $("out-after").textContent = formatBytes(job.output_size);

  const saved = job.input_size > 0 ? (1 - job.output_size / job.input_size) * 100 : 0;
  $("out-saved").textContent =
    saved > 0 ? `−${saved.toFixed(0)} % de tamaño (${formatBytes(job.input_size - job.output_size)} menos)` : "Sin cambios de tamaño";

  resultSection.classList.remove("hidden");
  resultSection.scrollIntoView({ behavior: "smooth", block: "center" });
  showToast("¡Vídeo comprimido listo!");
}

$("download-btn").addEventListener("click", () => {
  const a = document.createElement("a");
  a.href = outUrl || "#";
  a.download = outName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  showToast("Descargando el vídeo comprimido…");
});

$("again-btn").addEventListener("click", () => {
  selectedFile = null;
  fileInput.value = "";
  fileCard.classList.add("hidden");
  compressBtn.disabled = true;
  actionHint.textContent = "Elige primero un vídeo.";
  if (localPreviewUrl) {
    URL.revokeObjectURL(localPreviewUrl);
    localPreviewUrl = null;
  }
  resetResult();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

function resetResult() {
  resultSection.classList.add("hidden");
  $("out-preview").removeAttribute("src");
  if (outUrl) {
    URL.revokeObjectURL(outUrl);
    outUrl = null;
  }
  jobId = null;
}
