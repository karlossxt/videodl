/* Recortador de clips verticales (TikTok / Reels / Shorts) para Twitch, Kick, YouTube…
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

let mode = "url";          // url | file
let info = null;           // metadatos devueltos por /api/info
let posterUrl = null;      // imagen para la vista previa (miniatura o fotograma)
let localUrl = null;       // objectURL del archivo local
let selectedFile = null;
let duration = 0;          // duración total en segundos
let start = 0;
let end = 30;
let aspect = "vertical";
let quality = "media";

let jobId = null;
let pollRunId = 0;
let jobStartedAt = 0;
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
// Paso 1 · origen (enlace o archivo)
// ---------------------------------------------------------------------------

const srcTabs = Array.from(document.querySelectorAll(".clip-src-tabs .tab"));

function selectSrcTab(tab) {
  for (const t of srcTabs) {
    const active = t === tab;
    t.classList.toggle("active", active);
    t.setAttribute("aria-selected", String(active));
    t.setAttribute("tabindex", active ? "0" : "-1");
  }
  mode = tab.dataset.src;
  $("src-url-panel").classList.toggle("hidden", mode !== "url");
  $("src-file-panel").classList.toggle("hidden", mode !== "file");
  clearError();
  resetSource();
}

srcTabs.forEach((tab, index) => {
  tab.addEventListener("click", () => selectSrcTab(tab));
  tab.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const dir = e.key === "ArrowRight" ? 1 : -1;
    const next = srcTabs[(index + dir + srcTabs.length) % srcTabs.length];
    next.focus();
    selectSrcTab(next);
  });
});

function resetSource() {
  info = null;
  duration = 0;
  selectedFile = null;
  $("info-card").classList.add("hidden");
  $("clip-btn").disabled = true;
  $("clip-hint").textContent = "Elige primero un vídeo.";
}

$("clip-url-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = $("clip-url").value.trim();
  if (!url) return;

  clearError();
  resetResult();
  const btn = $("clip-analyze");
  btn.disabled = true;
  btn.textContent = "Analizando…";

  try {
    const res = await fetchWithTimeout(
      "/api/info",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      },
      45000
    );
    if (!res.ok) throw await errorFromResponse(res, "No se pudo analizar el enlace.");
    const data = await res.json();

    info = data;
    duration = Number(data.duration) || 0;
    if (!duration) throw new Error("Este vídeo es un directo sin duración conocida: usa un VOD o un clip.");

    showInfo(
      data.title || "Vídeo sin título",
      [data.uploader, data.extractor, fmtClock(duration)].filter(Boolean).join(" · "),
      data.thumbnail || null
    );
    setupTrim(duration, Math.min(30, duration));
    showToast("Enlace analizado");
  } catch (err) {
    showError(err.message || "No se pudo analizar el enlace.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Analizar →";
  }
});

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

  posterUrl = image;
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

  const len = end - start;
  if (len < 1) return showError("El clip debe durar al menos 1 segundo.");
  if (len > maxSeconds) return showError(`El clip no puede durar más de ${fmtClock(maxSeconds)}.`);

  $("progress").classList.remove("hidden");
  $("pr-fill").style.width = "0%";
  $("pr-fill").classList.remove("indeterminate");
  $("pr-track").setAttribute("aria-valuenow", "0");
  $("pr-percent").textContent = "0%";
  $("pr-status").textContent = mode === "file" ? "Subiendo el vídeo…" : "Analizando el enlace…";
  $("pr-detail").textContent = mode === "file" ? formatBytes(selectedFile.size) : "Preparando la descarga";
  $("clip-btn").disabled = true;
  jobStartedAt = Date.now();

  if (mode === "file") uploadClip();
  else createClipJob();
});

async function createClipJob() {
  try {
    const res = await fetchWithTimeout(
      "/api/clips",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: $("clip-url").value.trim(),
          start: Number(start.toFixed(2)),
          end: Number(end.toFixed(2)),
          aspect,
          quality,
          title: info?.title || null,
        }),
      },
      60000
    );
    if (!res.ok) throw await errorFromResponse(res, "No se pudo iniciar el clip.");
    const data = await res.json();
    jobId = data.id;
    pollJob();
  } catch (err) {
    failClip(err.message || "No se pudo iniciar el clip.");
  }
}

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
  const fill = $("pr-fill");
  $("pr-status").textContent = job.message || "Creando el clip…";

  // Cuando yt-dlp descarga un fragmento de un directo no siempre puede informar
  // del avance: en ese caso se muestra una barra animada con el tiempo transcurrido.
  if (job.status === "downloading" && pct < 0.5) {
    if (!fill.classList.contains("indeterminate")) {
      fill.classList.add("indeterminate");
      fill.style.width = "";
    }
    const elapsed = Math.max(0, Math.round((Date.now() - jobStartedAt) / 1000));
    $("pr-percent").textContent = "…";
    $("pr-detail").textContent =
      `${fmtClock(elapsed)} descargando el fragmento` +
      (elapsed > 20 ? " · en directos largos esta parte tarda un poco" : "");
  } else {
    fill.classList.remove("indeterminate");
    fill.style.width = `${pct}%`;
    $("pr-percent").textContent = `${pct.toFixed(0)}%`;
    $("pr-track").setAttribute("aria-valuenow", String(Math.round(pct)));

    if (job.status === "downloading") {
      const parts = [];
      if (job.downloaded) parts.push(`${formatBytes(job.downloaded)}${job.total ? ` / ${formatBytes(job.total)}` : ""}`);
      if (job.speed) parts.push(`${formatBytes(job.speed)}/s`);
      if (job.eta) parts.push(`faltan ${fmtClock(job.eta)}`);
      $("pr-detail").textContent = parts.join(" · ") || "Descargando solo el fragmento…";
    } else if (job.status === "transforming") {
      $("pr-detail").textContent = "Recodificando en vertical · esto es lo que más tarda";
    }
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
  if (mode === "file") {
    selectedFile = null;
    fileInput.value = "";
    resetSource();
    if (localUrl) {
      URL.revokeObjectURL(localUrl);
      localUrl = null;
    }
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
