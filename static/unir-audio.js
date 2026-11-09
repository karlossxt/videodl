/* Unir o cortar audio. Utilidades compartidas en common.js (window.VD). */

const {
  $,
  t,
  showToast,
  showError,
  clearError,
  formatBytes,
  fmtClock,
  escapeHtml,
  fetchWithTimeout,
  pollJob: pollJobBase,
  isAllowedAudio,
  triggerDownload,
  uploadWithProgress,
} = window.VD;

const dropzone = $("dropzone");
const fileInput = $("file-input");
const listEl = $("audio-list");
const audioBtn = $("audio-btn");
const actionHint = $("action-hint");
const progressBox = $("progress");
const resultSection = $("result");
const formatSel = $("audio-format");
const bitrateSel = $("audio-bitrate");
const startInput = $("trim-start");
const endInput = $("trim-end");

let maxUploadMb = 200;
let maxFiles = 10;
let files = [];
let startTracked = false;
let jobId = null;
let pollRunId = 0;
let outUrl = null;
let outName = t("audioEdit.defaultName", "audio-unido.mp3");

$("error-close").addEventListener("click", clearError);

(async function loadConfig() {
  try {
    const res = await fetchWithTimeout("/api/audio/options", {}, 15000);
    if (!res.ok) return;
    const cfg = await res.json();
    if (cfg.max_upload_mb) {
      maxUploadMb = cfg.max_upload_mb;
      $("limit-hint").textContent = t(
        "audioEdit.limitHint",
        `Máximo ${maxUploadMb} MB en total`,
        { mb: maxUploadMb }
      );
    }
    if (cfg.max_files) {
      maxFiles = cfg.max_files;
      $("max-files").textContent = String(maxFiles);
    }
  } catch {
    /* sin conexión: se usan los valores por defecto */
  }
})();

function syncBitrate() {
  $("bitrate-field").classList.toggle("hidden", formatSel.value === "wav");
}
formatSel.addEventListener("change", syncBitrate);
syncBitrate();

// ---------------------------------------------------------------------------
// Paso 1 · lista de audios
// ---------------------------------------------------------------------------

dropzone.addEventListener("click", (e) => {
  if (e.target !== fileInput) fileInput.click();
});
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    fileInput.click();
  }
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
dropzone.addEventListener("drop", (e) => addFiles(e.dataTransfer?.files));
fileInput.addEventListener("change", () => {
  addFiles(fileInput.files);
  fileInput.value = "";
});

function totalBytes() {
  return files.reduce((sum, f) => sum + f.size, 0);
}

function addFiles(fileList) {
  const incoming = Array.from(fileList || []);
  if (!incoming.length) return;
  clearError();
  resetResult();

  for (const file of incoming) {
    if (!isAllowedAudio(file.name)) {
      showError(
        t(
          "audioEdit.unsupported",
          "Formato no compatible. Sube archivos de audio (MP3, WAV, M4A, OGG, FLAC…)."
        )
      );
      return;
    }
    if (files.length >= maxFiles) {
      showError(
        t("audioEdit.tooMany", `Puedes unir hasta ${maxFiles} archivos a la vez.`, { max: maxFiles })
      );
      break;
    }
    if (totalBytes() + file.size > maxUploadMb * 1024 * 1024) {
      showError(
        t("audioEdit.tooHeavy", `Los archivos superan el límite de ${maxUploadMb} MB en total.`, {
          max: maxUploadMb,
        })
      );
      break;
    }
    files.push(file);
  }

  if (!startTracked && files.length) {
    startTracked = true;
    window.VD.track("tool_start", { file_count: files.length });
  }
  renderList();
}

function renderList() {
  listEl.classList.toggle("hidden", files.length === 0);
  listEl.innerHTML = "";
  files.forEach((file, index) => {
    const li = document.createElement("li");
    li.className = "audio-item";
    li.innerHTML =
      `<span class="audio-index">${index + 1}</span>` +
      `<span class="audio-name">${escapeHtml(file.name)}</span>` +
      `<span class="audio-size">${formatBytes(file.size)}</span>` +
      `<span class="audio-actions">` +
      `<button type="button" class="ghost-btn small" data-act="up" aria-label="${escapeHtml(
        t("audioEdit.moveUp", "Subir")
      )}" ${index === 0 ? "disabled" : ""}>↑</button>` +
      `<button type="button" class="ghost-btn small" data-act="down" aria-label="${escapeHtml(
        t("audioEdit.moveDown", "Bajar")
      )}" ${index === files.length - 1 ? "disabled" : ""}>↓</button>` +
      `<button type="button" class="ghost-btn small" data-act="remove" aria-label="${escapeHtml(
        t("audioEdit.remove", "Quitar")
      )}">✕</button>` +
      `</span>`;
    li.querySelectorAll("button").forEach((btn) =>
      btn.addEventListener("click", () => moveOrRemove(index, btn.dataset.act))
    );
    listEl.appendChild(li);
  });
  updateAction();
}

function moveOrRemove(index, action) {
  resetResult();
  if (action === "remove") files.splice(index, 1);
  else if (action === "up" && index > 0) [files[index - 1], files[index]] = [files[index], files[index - 1]];
  else if (action === "down" && index < files.length - 1)
    [files[index + 1], files[index]] = [files[index], files[index + 1]];
  renderList();
}

// ---------------------------------------------------------------------------
// Paso 2 y 3 · recorte y formato
// ---------------------------------------------------------------------------

function readTrim() {
  const start = Math.max(0, parseFloat(startInput.value) || 0);
  const rawEnd = parseFloat(endInput.value);
  const end = isFinite(rawEnd) && rawEnd > 0 ? rawEnd : 0;
  return { start, end };
}

function canRun() {
  const { start, end } = readTrim();
  return files.length >= 2 || (files.length === 1 && (start > 0 || end > 0));
}

function updateAction() {
  audioBtn.disabled = !canRun();
  if (!files.length) {
    actionHint.textContent = t("audioEdit.chooseFirst", "Elige al menos dos audios, o uno y un recorte.");
  } else if (canRun()) {
    actionHint.textContent =
      files.length > 1
        ? t("audioEdit.readyJoin", `Se unirán ${files.length} audios en el orden de la lista.`, {
            count: files.length,
          })
        : t("audioEdit.readyTrim", "Se recortará el audio.");
  } else {
    actionHint.textContent = t(
      "audioEdit.needMore",
      "Añade otro audio o indica un inicio o un final para recortar."
    );
  }
}

startInput.addEventListener("input", updateAction);
endInput.addEventListener("input", updateAction);

// ---------------------------------------------------------------------------
// Crear el audio
// ---------------------------------------------------------------------------

audioBtn.addEventListener("click", async () => {
  if (!canRun()) return;

  const { start, end } = readTrim();
  if (end > 0 && end <= start) {
    showError(t("audioEdit.badRange", "El final debe ser posterior al inicio."));
    return;
  }

  clearError();
  resetResult();
  audioBtn.disabled = true;
  progressBox.classList.remove("hidden");
  $("pr-fill").style.width = "0%";
  $("pr-track").setAttribute("aria-valuenow", "0");
  $("pr-percent").textContent = "0%";
  $("pr-status").textContent = t("audioEdit.uploading", "Subiendo los archivos…");
  $("pr-detail").textContent = formatBytes(totalBytes());

  const form = new FormData();
  files.forEach((file) => form.append("files", file, file.name));
  form.append("start", String(start));
  form.append("end", String(end));
  form.append("format", formatSel.value);
  form.append("bitrate", bitrateSel.value);

  try {
    const data = await uploadWithProgress("/api/audio/edit", form, {
      onProgress: (loaded, total) => {
        const pct = (loaded / total) * 100;
        $("pr-fill").style.width = `${pct}%`;
        $("pr-percent").textContent = `${pct.toFixed(0)}%`;
        $("pr-detail").textContent = `${formatBytes(loaded)} / ${formatBytes(total)}`;
      },
    });
    jobId = data.id;
    $("pr-status").textContent = t("audioEdit.processing", "Procesando el audio…");
    $("pr-detail").textContent = t("audioEdit.preparing", "Preparando el proceso");
    pollJob();
  } catch (err) {
    failJob(err.message);
  }
});

function failJob(msg) {
  progressBox.classList.add("hidden");
  updateAction();
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
      failJob(job.error || t("audioEdit.failed", "No se pudo procesar el audio."));
    } else if (job.status === "cancelled") {
      progressBox.classList.add("hidden");
      updateAction();
      showToast(t("audioEdit.cancelled", "Proceso cancelado"));
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
  $("pr-status").textContent = t("audioEdit.progress", "Procesando el audio…");
}

$("pr-cancel").addEventListener("click", async () => {
  if (!jobId) return;
  $("pr-status").textContent = t("audioEdit.cancelling", "Cancelando…");
  try {
    await fetch(`/api/audio/${jobId}/cancel`, { method: "POST" });
  } catch {
    /* el sondeo detectará el estado final */
  }
});

async function finishJob(job) {
  window.VD.track("tool_complete", {
    output_ext: formatSel.value,
    file_count: files.length,
  });
  outName = job.filename || t("audioEdit.defaultName", "audio-unido.mp3");

  let blob = null;
  try {
    const res = await fetchWithTimeout(`/api/audio/${job.id}/file`, {}, 60000);
    if (res.ok) blob = await res.blob();
  } catch {
    /* se intentará descargar directo */
  }

  progressBox.classList.add("hidden");
  updateAction();

  if (!blob) {
    triggerDownload(`/api/audio/${job.id}/file`, outName);
    showToast(t("audioEdit.downloadStarted", "Descarga iniciada"));
    return;
  }

  if (outUrl) URL.revokeObjectURL(outUrl);
  outUrl = URL.createObjectURL(blob);
  $("out-preview").src = outUrl;
  $("out-size").textContent = formatBytes(job.output_size || blob.size);
  $("out-duration").textContent = job.duration ? fmtClock(job.duration) : "—";

  resultSection.classList.remove("hidden");
  resultSection.scrollIntoView({ behavior: "smooth", block: "center" });
  showToast(t("audioEdit.readyToast", "¡Audio listo!"));
}

$("download-btn").addEventListener("click", () => {
  if (!outUrl) {
    showToast(t("audioEdit.notReady", "La descarga aún no está lista"), { error: true });
    return;
  }
  triggerDownload(outUrl, outName);
  showToast(t("audioEdit.downloading", "Descargando el audio…"));
});

$("again-btn").addEventListener("click", () => {
  resetResult();
  files = [];
  startInput.value = "";
  endInput.value = "";
  renderList();
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
