/* Extraer audio de un vídeo (o convertir un audio). Utilidades en common.js (window.VD). */

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
  isAllowedAudio,
  triggerDownload,
  uploadWithProgress,
} = window.VD;

const dropzone = $("dropzone");
const fileInput = $("file-input");
const fileCard = $("file-card");
const audioBtn = $("audio-btn");
const actionHint = $("action-hint");
const progressBox = $("progress");
const resultSection = $("result");
const formatSel = $("audio-format");
const bitrateSel = $("audio-bitrate");

let maxUploadMb = 200;
let selectedFile = null;
let jobId = null;
let pollRunId = 0;
let outUrl = null;
let outName = t("audioExtract.defaultName", "audio.mp3");

$("error-close").addEventListener("click", clearError);

(async function loadConfig() {
  try {
    const res = await fetchWithTimeout("/api/audio/options", {}, 15000);
    if (!res.ok) return;
    const cfg = await res.json();
    if (cfg.max_upload_mb) {
      maxUploadMb = cfg.max_upload_mb;
      $("limit-hint").textContent = t(
        "audioExtract.limitHint",
        `Máximo ${maxUploadMb} MB por archivo`,
        { mb: maxUploadMb }
      );
      $("limit-hint-2").textContent = `${maxUploadMb} MB`;
    }
  } catch {
    /* sin conexión: se usan los valores por defecto */
  }
})();

// La calidad en kbps no aplica a WAV (sin compresión).
function syncBitrate() {
  $("bitrate-field").classList.toggle("hidden", formatSel.value === "wav");
}
formatSel.addEventListener("change", syncBitrate);
syncBitrate();

linkDropzone(dropzone, fileInput, handleFile);

function handleFile(file) {
  clearError();

  if (!isAllowedAudio(file.name)) {
    showError(
      t(
        "audioExtract.unsupported",
        "Formato no compatible. Sube un vídeo o un audio (MP4, MOV, MP3, WAV, M4A…)."
      )
    );
    return;
  }
  if (file.size > maxUploadMb * 1024 * 1024) {
    showError(
      t(
        "audioExtract.tooHeavy",
        `El archivo pesa ${formatBytes(file.size)} y el máximo es ${maxUploadMb} MB.`,
        { size: formatBytes(file.size), max: maxUploadMb }
      )
    );
    return;
  }

  selectedFile = file;
  resetResult();
  $("file-name").textContent = file.name;
  $("file-meta").textContent = formatBytes(file.size);
  fileCard.classList.remove("hidden");
  audioBtn.disabled = false;
  actionHint.textContent = t("audioExtract.ready", "Elige el formato y pulsa «Extraer audio».");
}

function clearFile() {
  selectedFile = null;
  fileInput.value = "";
  fileCard.classList.add("hidden");
  audioBtn.disabled = true;
  actionHint.textContent = t("audioExtract.chooseFirst", "Elige primero un archivo.");
}

$("file-clear").addEventListener("click", clearFile);

audioBtn.addEventListener("click", async () => {
  if (!selectedFile) return;

  clearError();
  resetResult();
  audioBtn.disabled = true;
  progressBox.classList.remove("hidden");
  $("pr-fill").style.width = "0%";
  $("pr-track").setAttribute("aria-valuenow", "0");
  $("pr-percent").textContent = "0%";
  $("pr-status").textContent = t("audioExtract.uploading", "Subiendo el archivo…");
  $("pr-detail").textContent = formatBytes(selectedFile.size);

  const form = new FormData();
  form.append("file", selectedFile, selectedFile.name);
  form.append("format", formatSel.value);
  form.append("bitrate", bitrateSel.value);

  try {
    const data = await uploadWithProgress("/api/audio/extract", form, {
      onProgress: (loaded, total) => {
        const pct = (loaded / total) * 100;
        $("pr-fill").style.width = `${pct}%`;
        $("pr-percent").textContent = `${pct.toFixed(0)}%`;
        $("pr-detail").textContent = `${formatBytes(loaded)} / ${formatBytes(total)}`;
      },
    });
    jobId = data.id;
    $("pr-status").textContent = t("audioExtract.extracting", "Extrayendo el audio…");
    $("pr-detail").textContent = t("audioExtract.preparing", "Preparando la conversión");
    pollJob();
  } catch (err) {
    failJob(err.message);
  }
});

function failJob(msg) {
  progressBox.classList.add("hidden");
  audioBtn.disabled = !selectedFile;
  showError(msg);
}

async function pollJob() {
  const runId = ++pollRunId;
  try {
    const job = await pollJobBase({
      intervalMs: 700,
      fetcher: async () => {
        const res = await fetch(`/api/audio/${jobId}`);
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
      failJob(job.error || t("audioExtract.failed", "No se pudo extraer el audio."));
    } else if (job.status === "cancelled") {
      progressBox.classList.add("hidden");
      audioBtn.disabled = false;
      showToast(t("audioExtract.cancelled", "Extracción cancelada"));
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
  $("pr-status").textContent = t("audioExtract.progress", "Extrayendo el audio…");
}

$("pr-cancel").addEventListener("click", async () => {
  if (!jobId) return;
  $("pr-status").textContent = t("audioExtract.cancelling", "Cancelando…");
  try {
    await fetch(`/api/audio/${jobId}/cancel`, { method: "POST" });
  } catch {
    /* el sondeo detectará el estado final */
  }
});

async function finishJob(job) {
  window.VD.track("tool_complete", { output_ext: formatSel.value });
  outName = job.filename || t("audioExtract.defaultName", "audio.mp3");

  let blob = null;
  try {
    const res = await fetchWithTimeout(`/api/audio/${job.id}/file`, {}, 60000);
    if (res.ok) blob = await res.blob();
  } catch {
    /* se intentará descargar directo */
  }

  progressBox.classList.add("hidden");
  audioBtn.disabled = false;

  if (!blob) {
    triggerDownload(`/api/audio/${job.id}/file`, outName);
    showToast(t("audioExtract.downloadStarted", "Descarga iniciada"));
    return;
  }

  if (outUrl) URL.revokeObjectURL(outUrl);
  outUrl = URL.createObjectURL(blob);
  $("out-preview").src = outUrl;
  $("out-size").textContent = formatBytes(job.output_size || blob.size);
  $("out-duration").textContent = job.duration ? fmtClock(job.duration) : "—";

  resultSection.classList.remove("hidden");
  resultSection.scrollIntoView({ behavior: "smooth", block: "center" });
  showToast(t("audioExtract.readyToast", "¡Audio listo!"));
}

$("download-btn").addEventListener("click", () => {
  if (!outUrl) {
    showToast(t("audioExtract.notReady", "La descarga aún no está lista"), { error: true });
    return;
  }
  triggerDownload(outUrl, outName);
  showToast(t("audioExtract.downloading", "Descargando el audio…"));
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
