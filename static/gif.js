/* Convertidor de vídeo a GIF. Utilidades compartidas en common.js (window.VD). */

const {
  $,
  t,
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
  uploadWithProgress,
} = window.VD;

const dropzone = $("dropzone");
const fileInput = $("file-input");
const fileCard = $("file-card");
const gifBtn = $("gif-btn");
const actionHint = $("action-hint");
const progressBox = $("progress");
const resultSection = $("result");
const startInput = $("gif-start");
const endInput = $("gif-end");

let maxUploadMb = 200;
let maxSeconds = 15;
let selectedFile = null;
let videoDuration = 0;
let jobId = null;
let pollRunId = 0;
let outUrl = null;
let outName = t("gif.defaultName", "animacion.gif");
let localPreviewUrl = null;

$("error-close").addEventListener("click", clearError);

// ---------------------------------------------------------------------------
// Configuración desde el servidor
// ---------------------------------------------------------------------------

(async function loadConfig() {
  try {
    const res = await fetchWithTimeout("/api/gif/options", {}, 15000);
    if (!res.ok) return;
    const cfg = await res.json();
    if (cfg.max_upload_mb) {
      maxUploadMb = cfg.max_upload_mb;
      $("limit-hint").textContent = t("gif.limitHint", `Máximo ${maxUploadMb} MB por archivo`, {
        mb: maxUploadMb,
      });
      $("limit-hint-2").textContent = `${maxUploadMb} MB`;
    }
    if (cfg.max_seconds) {
      maxSeconds = cfg.max_seconds;
      updateRangeHint();
    }
  } catch {
    /* sin conexión: se usan los valores por defecto */
  }
})();

// ---------------------------------------------------------------------------
// Paso 1 · elegir el vídeo
// ---------------------------------------------------------------------------

linkDropzone(dropzone, fileInput, handleFile);

function handleFile(file) {
  clearError();

  if (!isAllowedVideo(file.name)) {
    showError(
      t("gif.unsupported", "Formato no compatible. Sube un vídeo MP4, MOV, MKV, WEBM, AVI…")
    );
    return;
  }
  if (file.size > maxUploadMb * 1024 * 1024) {
    showError(
      t("gif.tooHeavy", `El archivo pesa ${formatBytes(file.size)} y el máximo es ${maxUploadMb} MB.`, {
        size: formatBytes(file.size),
        max: maxUploadMb,
      })
    );
    return;
  }

  selectedFile = file;
  videoDuration = 0;
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
    if (preview.duration && isFinite(preview.duration)) {
      videoDuration = preview.duration;
      parts.push(fmtClock(preview.duration));
      startInput.value = "0";
      endInput.value = String(Math.round(Math.min(videoDuration, maxSeconds) * 10) / 10);
    }
    $("file-meta").textContent = parts.join(" · ");
    updateRangeHint();
  };

  fileCard.classList.remove("hidden");
  gifBtn.disabled = false;
  actionHint.textContent = t("gif.ready", "Ajusta el fragmento y pulsa «Crear GIF».");
}

function clearFile() {
  selectedFile = null;
  videoDuration = 0;
  fileInput.value = "";
  fileCard.classList.add("hidden");
  gifBtn.disabled = true;
  actionHint.textContent = t("gif.chooseFirst", "Elige primero un vídeo.");
  if (localPreviewUrl) {
    URL.revokeObjectURL(localPreviewUrl);
    localPreviewUrl = null;
  }
}

$("file-clear").addEventListener("click", clearFile);

// ---------------------------------------------------------------------------
// Paso 2 · fragmento
// ---------------------------------------------------------------------------

function readRange() {
  const start = Math.max(0, parseFloat(startInput.value) || 0);
  let end = parseFloat(endInput.value);
  if (!isFinite(end) || end <= 0) end = videoDuration || start + maxSeconds;
  if (videoDuration) end = Math.min(end, videoDuration);
  return { start, end };
}

function updateRangeHint() {
  const { start, end } = readRange();
  const seconds = Math.max(0, end - start);
  $("gif-hint").textContent = t(
    "gif.rangeHint",
    `Duración del GIF: ${seconds.toFixed(1)} s (máximo ${maxSeconds} s)`,
    { seconds: seconds.toFixed(1), max: maxSeconds }
  );
}

startInput.addEventListener("input", updateRangeHint);
endInput.addEventListener("input", updateRangeHint);

// ---------------------------------------------------------------------------
// Paso 3 · crear el GIF
// ---------------------------------------------------------------------------

gifBtn.addEventListener("click", async () => {
  if (!selectedFile) return;

  const { start, end } = readRange();
  if (end <= start) {
    showError(t("gif.badRange", "El final debe ser posterior al inicio."));
    return;
  }
  if (end - start > maxSeconds) {
    showError(
      t("gif.tooLong", `El GIF no puede durar más de ${maxSeconds} segundos.`, { max: maxSeconds })
    );
    return;
  }

  clearError();
  resetResult();
  gifBtn.disabled = true;
  progressBox.classList.remove("hidden");
  $("pr-fill").style.width = "0%";
  $("pr-track").setAttribute("aria-valuenow", "0");
  $("pr-percent").textContent = "0%";
  $("pr-status").textContent = t("gif.uploading", "Subiendo el vídeo…");
  $("pr-detail").textContent = formatBytes(selectedFile.size);

  const form = new FormData();
  form.append("file", selectedFile, selectedFile.name);
  form.append("start", String(start));
  form.append("end", String(end));
  form.append("width", $("gif-width").value);
  form.append("fps", $("gif-fps").value);

  try {
    const data = await uploadWithProgress("/api/gif/upload", form, {
      onProgress: (loaded, total) => {
        const pct = (loaded / total) * 100;
        $("pr-fill").style.width = `${pct}%`;
        $("pr-percent").textContent = `${pct.toFixed(0)}%`;
        $("pr-detail").textContent = `${formatBytes(loaded)} / ${formatBytes(total)}`;
      },
    });
    jobId = data.id;
    $("pr-status").textContent = t("gif.creating", "Creando el GIF…");
    $("pr-detail").textContent = t("gif.preparing", "Preparando la conversión");
    pollJob();
  } catch (err) {
    failJob(err.message);
  }
});

function failJob(msg) {
  progressBox.classList.add("hidden");
  gifBtn.disabled = !selectedFile;
  showError(msg);
}

async function pollJob() {
  const runId = ++pollRunId;
  try {
    const job = await pollJobBase({
      intervalMs: 700,
      fetcher: async () => {
        const res = await fetch(`/api/gif/${jobId}`);
        if (!res.ok) throw new Error("no disponible");
        return res.json();
      },
      onUpdate: (j) => {
        if (runId === pollRunId) updateProgress(j);
      },
    });
    if (runId !== pollRunId) return;

    if (job.status === "finished") {
      finishJob(job);
    } else if (job.status === "error") {
      failJob(job.error || t("gif.failed", "No se pudo crear el GIF."));
    } else if (job.status === "cancelled") {
      progressBox.classList.add("hidden");
      gifBtn.disabled = false;
      showToast(t("gif.cancelled", "Conversión cancelada"));
    }
  } catch (err) {
    if (runId !== pollRunId) return;
    failJob(err.message);
  }
}

function updateProgress(job) {
  const pct = Math.max(0, Math.min(100, Number(job.percent) || 0));
  $("pr-fill").style.width = `${pct}%`;
  $("pr-percent").textContent = `${pct.toFixed(0)}%`;
  $("pr-track").setAttribute("aria-valuenow", String(Math.round(pct)));
  $("pr-status").textContent = t("gif.progress", "Creando el GIF…");
}

$("pr-cancel").addEventListener("click", async () => {
  if (!jobId) return;
  $("pr-status").textContent = t("gif.cancelling", "Cancelando…");
  try {
    await fetch(`/api/gif/${jobId}/cancel`, { method: "POST" });
  } catch {
    /* el sondeo detectará el estado final */
  }
});

async function finishJob(job) {
  window.VD.track("tool_complete");
  outName = job.filename || t("gif.defaultName", "animacion.gif");

  let blob = null;
  try {
    const res = await fetchWithTimeout(`/api/gif/${job.id}/file`, {}, 60000);
    if (res.ok) blob = await res.blob();
  } catch {
    /* se intentará descargar directo */
  }

  progressBox.classList.add("hidden");
  gifBtn.disabled = false;

  if (!blob) {
    triggerDownload(`/api/gif/${job.id}/file`, outName);
    showToast(t("gif.downloadStarted", "Descarga iniciada"));
    return;
  }

  if (outUrl) URL.revokeObjectURL(outUrl);
  outUrl = URL.createObjectURL(blob);
  $("out-preview").src = outUrl;
  $("out-size").textContent = formatBytes(job.output_size || blob.size);
  $("out-duration").textContent = job.duration ? `${Number(job.duration).toFixed(1)} s` : "—";

  resultSection.classList.remove("hidden");
  resultSection.scrollIntoView({ behavior: "smooth", block: "center" });
  showToast(t("gif.readyToast", "¡GIF listo!"));
}

$("download-btn").addEventListener("click", () => {
  if (!outUrl) {
    showToast(t("gif.notReady", "La descarga aún no está lista"), { error: true });
    return;
  }
  triggerDownload(outUrl, outName);
  showToast(t("gif.downloading", "Descargando el GIF…"));
});

$("again-btn").addEventListener("click", () => {
  resetResult();
  clearFile();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

function resetResult() {
  pollRunId++;
  resultSection.classList.add("hidden");
  progressBox.classList.add("hidden");
  if (outUrl) {
    URL.revokeObjectURL(outUrl);
    outUrl = null;
  }
  $("out-preview").removeAttribute("src");
}
