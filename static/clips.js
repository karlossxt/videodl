/* Recortador de clips verticales a partir de un archivo propio.
   Utilidades compartidas en common.js (window.VD). */

const {
  $,
  showToast,
  showError,
  clearError,
  formatBytes,
  fmtClock,
  fetchWithTimeout,
  errorFromResponse,
  pollJob: pollJobBase,
  linkDropzone,
  isAllowedVideo,
  triggerDownload,
} = window.VD;

let maxUploadMb = 200;
let maxSeconds = 300;

let selectedFile = null;
let localUrl = null;        // objectURL del archivo local
let duration = 0;           // duración total en segundos
let start = 0;
let end = 30;
let aspect = "vertical";
let quality = "media";

let jobId = null;
let pollRunId = 0;
let outUrl = null;
let outName = "clip-vertical.mp4";

const ASPECT_LABEL = {
  vertical: "9:16",
  "vertical-blur": "9:16 + fondo",
  square: "1:1",
  original: "original",
};

$("error-close").addEventListener("click", clearError);

// ---------------------------------------------------------------------------
// Configuración del servidor
// ---------------------------------------------------------------------------

(async function loadOptions() {
  try {
    const res = await fetchWithTimeout("/api/clips/options", {}, 15000);
    if (!res.ok) return;
    const cfg = await res.json();
    if (cfg.max_upload_mb) {
      maxUploadMb = cfg.max_upload_mb;
      $("limit-hint").textContent = `Máximo ${maxUploadMb} MB por archivo`;
      $("limit-hint-2").textContent = `${maxUploadMb} MB`;
      $("faq-upload").textContent = String(maxUploadMb);
    }
    if (cfg.max_seconds) {
      maxSeconds = cfg.max_seconds;
      $("faq-max").textContent = String(maxSeconds);
      $("clip-max-hint").textContent = `Hasta ${Math.round(maxSeconds / 60)} min de clip`;
    }
  } catch {
    /* sin conexión: valores por defecto */
  }
})();

// ---------------------------------------------------------------------------
// Paso 1 · archivo
// ---------------------------------------------------------------------------

const dropzone = $("clip-dropzone");
const fileInput = $("clip-file-input");

linkDropzone(dropzone, fileInput, handleFile);

function handleFile(file) {
  clearError();
  resetResult();

  if (!isAllowedVideo(file.name)) {
    showError("Formato no compatible. Sube un vídeo MP4, MOV, MKV, WEBM, AVI…");
    return;
  }
  if (file.size > maxUploadMb * 1024 * 1024) {
    showError(`El archivo pesa ${formatBytes(file.size)} y el máximo es ${maxUploadMb} MB.`);
    return;
  }

  selectedFile = file;
  if (localUrl) URL.revokeObjectURL(localUrl);
  localUrl = URL.createObjectURL(file);

  // Metadatos reales desde el propio navegador
  const probe = document.createElement("video");
  probe.preload = "metadata";
  probe.muted = true;
  probe.src = localUrl;
  probe.onerror = () => {
    showError("No se pudo leer el archivo. ¿Está dañado o en un formato que el navegador no entiende?");
  };
  probe.onloadedmetadata = () => {
    duration = isFinite(probe.duration) ? probe.duration : 0;
    if (!duration) {
      showError("No se pudo leer la duración del archivo.");
      return;
    }
    probe.currentTime = Math.min(duration / 2, 1);
  };
  probe.onseeked = () => {
    const poster = capturePoster(probe);
    showInfo(
      file.name,
      [formatBytes(file.size), `${probe.videoWidth}×${probe.videoHeight}`, fmtClock(duration)]
        .filter(Boolean)
        .join(" · "),
      poster
    );
    setupTrim(duration, Math.min(30, duration));
    showToast("Archivo listo");
  };
}

function capturePoster(video) {
  try {
    const canvas = document.createElement("canvas");
    const w = video.videoWidth || 640;
    const h = video.videoHeight || 360;
    const scale = Math.min(1, 640 / w);
    canvas.width = Math.round(w * scale);
    canvas.height = Math.round(h * scale);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.8);
  } catch {
    return null;
  }
}

function showInfo(title, meta, image) {
  $("info-title").textContent = title;
  $("info-meta").textContent = meta;

  const bg = $("pv-bg");
  const fg = $("pv-fg");
  if (image) {
    bg.src = image;
    fg.src = image;
    bg.style.visibility = "visible";
    fg.style.visibility = "visible";
  } else {
    bg.removeAttribute("src");
    fg.removeAttribute("src");
  }

  $("info-card").classList.remove("hidden");
  $("clip-btn").disabled = false;
  updateHint();
}

// ---------------------------------------------------------------------------
// Paso 2 · fragmento
// ---------------------------------------------------------------------------

const startRange = $("start-range");
const endRange = $("end-range");
const startNum = $("start-num");
const endNum = $("end-num");

function setupTrim(total, len) {
  start = 0;
  end = Math.max(1, Math.min(len, total));
  startRange.min = endRange.min = 0;
  startNum.min = endNum.min = 0;
  startRange.max = endRange.max = Math.max(1, Math.floor(total));
  startNum.max = endNum.max = Math.max(1, Math.floor(total));
  refreshTrim();
}

function refreshTrim() {
  startRange.value = Math.floor(start);
  endRange.value = Math.ceil(end);
  startNum.value = Math.floor(start);
  endNum.value = Math.ceil(end);
  $("trim-readout").textContent = `${fmtClock(start)} → ${fmtClock(end)}`;

  const len = end - start;
  const hint = $("trim-hint");
  if (len < 1) {
    hint.textContent = "El clip debe durar al menos 1 segundo.";
    hint.classList.add("invalid");
  } else if (len > maxSeconds) {
    hint.textContent = `El clip dura ${fmtClock(len)} y el máximo es ${fmtClock(maxSeconds)}.`;
    hint.classList.add("invalid");
  } else if (len > 90) {
    hint.textContent = `Dura ${fmtClock(len)}. En TikTok, Reels y Shorts funciona mejor entre 15 y 60 s.`;
    hint.classList.remove("invalid");
  } else {
    hint.textContent = `Dura ${fmtClock(len)}.`;
    hint.classList.remove("invalid");
  }
  updateHint();
}

function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

startRange.addEventListener("input", () => {
  start = clamp(Number(startRange.value), 0, end - 1);
  if (end - start > maxSeconds) end = start + maxSeconds;
  refreshTrim();
});

endRange.addEventListener("input", () => {
  end = clamp(Number(endRange.value), start + 1, duration || maxSeconds);
  refreshTrim();
});

startNum.addEventListener("change", () => {
  start = clamp(Number(startNum.value) || 0, 0, Math.max(0, end - 1));
  refreshTrim();
});

endNum.addEventListener("change", () => {
  end = clamp(Number(endNum.value) || 1, start + 1, duration || maxSeconds);
  refreshTrim();
});

document.querySelectorAll(".trim-actions .soft-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const q = btn.dataset.quick;
    if (q === "first") {
      start = 0;
      end = Math.min(30, duration);
    } else if (q === "last") {
      end = duration;
      start = Math.max(0, duration - 30);
    } else {
      start = 0;
      end = Math.min(duration, maxSeconds);
    }
    refreshTrim();
  });
});

// ---------------------------------------------------------------------------
// Paso 3 · formato y calidad
// ---------------------------------------------------------------------------

const ASPECT_SIZES = {
  alta: { v: [1080, 1920], sq: 1080, orig: 1080 },
  media: { v: [720, 1280], sq: 720, orig: 720 },
  baja: { v: [480, 854], sq: 480, orig: 480 },
};

document.querySelectorAll(".clip-aspects .preset").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".clip-aspects .preset").forEach((b) => {
      b.classList.remove("active");
      b.setAttribute("aria-pressed", "false");
    });
    btn.classList.add("active");
    btn.setAttribute("aria-pressed", "true");
    aspect = btn.dataset.aspect;
    updatePreviewBox();
    updateHint();
  });
});

$("clip-quality").addEventListener("change", () => {
  quality = $("clip-quality").value;
  updateHint();
});

function updatePreviewBox() {
  const box = $("clip-preview");
  box.classList.remove("vertical", "vertical-blur", "square", "original");
  box.classList.add(aspect);
  $("pv-badge").textContent = ASPECT_LABEL[aspect] || "";
  // En "original" no hay recorte: se muestra el encuadre completo.
  if (aspect === "original") $("pv-bg").style.visibility = "hidden";
  else $("pv-bg").style.visibility = "visible";
}

function updateHint() {
  if (!duration && !selectedFile) return;

  const sizes = ASPECT_SIZES[quality] || ASPECT_SIZES.media;
  let label;
  if (aspect === "vertical" || aspect === "vertical-blur") {
    label = `${sizes.v[0]} × ${sizes.v[1]} · 9:16`;
  } else if (aspect === "square") {
    label = `${sizes.sq} × ${sizes.sq} · 1:1`;
  } else {
    label = `hasta ${sizes.orig}p · original`;
  }
  $("out-size").textContent = label;

  const len = end - start;
  $("clip-hint").textContent =
    len >= 1 && len <= maxSeconds
      ? `Se generará un clip de ${fmtClock(len)}.`
      : "Revisa el fragmento seleccionado.";
}

// ---------------------------------------------------------------------------
// Crear el clip
// ---------------------------------------------------------------------------

$("clip-btn").addEventListener("click", () => {
  clearError();
  resetResult();

  if (!selectedFile) return showError("Elige primero un vídeo.");

  const len = end - start;
  if (len < 1) return showError("El clip debe durar al menos 1 segundo.");
  if (len > maxSeconds) return showError(`El clip no puede durar más de ${fmtClock(maxSeconds)}.`);

  $("progress").classList.remove("hidden");
  $("pr-fill").style.width = "0%";
  $("pr-track").setAttribute("aria-valuenow", "0");
  $("pr-percent").textContent = "0%";
  $("pr-status").textContent = "Subiendo el vídeo…";
  $("pr-detail").textContent = formatBytes(selectedFile.size);
  $("clip-btn").disabled = true;

  uploadClip();
});

function uploadClip() {
  const form = new FormData();
  form.append("file", selectedFile, selectedFile.name);
  form.append("start", String(Number(start.toFixed(2))));
  form.append("end", String(Number(end.toFixed(2))));
  form.append("aspect", aspect);
  form.append("quality", quality);
  form.append("duration", String(Number((duration || 0).toFixed(2))));

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/clips/upload");
  xhr.timeout = 10 * 60 * 1000;

  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const pct = (e.loaded / e.total) * 6; // la subida ocupa el 0–6 %
    $("pr-fill").style.width = `${pct}%`;
    $("pr-percent").textContent = `${pct.toFixed(0)}%`;
    $("pr-detail").textContent = `${formatBytes(e.loaded)} / ${formatBytes(e.total)}`;
  };

  xhr.onload = () => {
    if (xhr.status >= 200 && xhr.status < 300) {
      try {
        jobId = JSON.parse(xhr.responseText).id;
        $("pr-status").textContent = "Recortando y reencuadrando…";
        pollJob();
        return;
      } catch {
        /* respuesta ilegible */
      }
    }
    let msg = `No se pudo crear el clip (error ${xhr.status || "de red"}).`;
    try {
      const data = JSON.parse(xhr.responseText);
      if (data.detail) msg = data.detail;
    } catch {
      /* sin cuerpo JSON */
    }
    failClip(msg);
  };

  xhr.onerror = () => failClip("No se pudo enviar el vídeo al servidor. Revisa tu conexión.");
  xhr.ontimeout = () => failClip("La subida tardó demasiado. Prueba con un vídeo más pequeño.");
  xhr.send(form);
}

function failClip(msg) {
  $("progress").classList.add("hidden");
  $("clip-btn").disabled = false;
  showError(msg);
}

async function pollJob() {
  const runId = ++pollRunId;
  try {
    const job = await pollJobBase({
      intervalMs: 700,
      fetcher: async () => {
        const res = await fetch(`/api/clips/${jobId}`);
        if (!res.ok) throw new Error("no disponible");
        return res.json();
      },
      onUpdate: (j) => {
        if (runId === pollRunId) updateClipProgress(j);
      },
    });
    if (runId !== pollRunId) return;

    if (job.status === "finished") finishClip(job);
    else if (job.status === "error") {
      $("progress").classList.add("hidden");
      $("clip-btn").disabled = false;
      showError(job.error || "No se pudo crear el clip.");
    } else if (job.status === "cancelled") {
      $("progress").classList.add("hidden");
      $("clip-btn").disabled = false;
      showToast("Clip cancelado");
    }
  } catch (err) {
    if (runId !== pollRunId) return;
    $("progress").classList.add("hidden");
    $("clip-btn").disabled = false;
    showError(err.message);
  }
}

function updateClipProgress(job) {
  const pct = Math.max(0, Math.min(100, Number(job.percent) || 0));
  $("pr-status").textContent = job.message || "Creando el clip…";
  $("pr-fill").style.width = `${pct}%`;
  $("pr-percent").textContent = `${pct.toFixed(0)}%`;
  $("pr-track").setAttribute("aria-valuenow", String(Math.round(pct)));

  if (job.status === "transforming") {
    $("pr-detail").textContent = "Recodificando el clip · esto es lo que más tarda";
  }
}

$("pr-cancel").addEventListener("click", async () => {
  if (!jobId) return;
  $("pr-status").textContent = "Cancelando…";
  try {
    await fetch(`/api/clips/${jobId}/cancel`, { method: "POST" });
  } catch {
    /* el sondeo detectará el estado final */
  }
});

async function finishClip(job) {
  outName = job.filename || "clip-vertical.mp4";

  let blob = null;
  try {
    const res = await fetchWithTimeout(`/api/clips/${job.id}/file`, {}, 60000);
    if (res.ok) blob = await res.blob();
  } catch {
    /* se intentará descargar directo */
  }

  $("progress").classList.add("hidden");
  $("clip-btn").disabled = false;

  if (!blob) {
    triggerDownload(`/api/clips/${job.id}/file`, outName);
    showToast("Descarga iniciada");
    return;
  }

  if (outUrl) URL.revokeObjectURL(outUrl);
  outUrl = URL.createObjectURL(blob);
  $("out-preview").src = outUrl;

  $("out-dims").textContent = job.width && job.height ? `${job.width}×${job.height}` : "—";
  $("out-dur").textContent = job.duration ? fmtClock(job.duration) : "—";
  $("out-weight").textContent = formatBytes(job.output_size);
  $("out-note").textContent = "Listo para subir a TikTok, Reels o Shorts";

  $("result").classList.remove("hidden");
  $("result").scrollIntoView({ behavior: "smooth", block: "center" });
  showToast("¡Clip listo!");
}

$("download-btn").addEventListener("click", () => {
  if (!outUrl) {
    showToast("La descarga aún no está lista", { error: true });
    return;
  }
  triggerDownload(outUrl, outName);
  showToast("Descargando el clip…");
});

$("again-btn").addEventListener("click", () => {
  resetResult();
  selectedFile = null;
  fileInput.value = "";
  duration = 0;
  $("info-card").classList.add("hidden");
  $("clip-btn").disabled = true;
  $("clip-hint").textContent = "Elige primero un vídeo.";
  if (localUrl) {
    URL.revokeObjectURL(localUrl);
    localUrl = null;
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
});

function resetResult() {
  // Invalida cualquier sondeo en curso.
  pollRunId++;
  $("result").classList.add("hidden");
  $("out-preview").removeAttribute("src");
  if (outUrl) {
    URL.revokeObjectURL(outUrl);
    outUrl = null;
  }
  jobId = null;
}
