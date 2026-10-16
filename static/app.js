const $ = (id) => document.getElementById(id);

const form = $("url-form");
const urlInput = $("url-input");
const analyzeBtn = $("analyze-btn");
const pasteBtn = $("paste-btn");
const clearBtn = $("clear-btn");
const loader = $("loader");
const errorBox = $("error-box");
const errorText = $("error-text");
const result = $("result");
const downloading = $("downloading");
const toast = $("toast");

let currentVideo = null;

// ---------------------------------------------------------------------------
// Utilidades de UI
// ---------------------------------------------------------------------------

let toastTimer = null;
function showToast(msg) {
  toast.textContent = `✓ ${msg}`;
  toast.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add("hidden"), 3000);
}

function showError(msg) {
  errorText.textContent = msg;
  errorBox.classList.remove("hidden");
}

function clearError() {
  errorBox.classList.add("hidden");
}

$("error-close").addEventListener("click", clearError);

function formatViews(n) {
  if (!n) return "";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} M vistas`;
  if (n >= 1_000) return `${Math.round(n / 1_000)} mil vistas`;
  return `${n} vistas`;
}

function updateClearBtn() {
  clearBtn.classList.toggle("hidden", !urlInput.value);
}

urlInput.addEventListener("input", updateClearBtn);

clearBtn.addEventListener("click", () => {
  urlInput.value = "";
  updateClearBtn();
  urlInput.focus();
});

async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "Error inesperado";
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch { /* respuesta no JSON */ }
    throw new Error(detail);
  }
  return res;
}

// ---------------------------------------------------------------------------
// Botones del hero: Pegar / Copiar
// ---------------------------------------------------------------------------

pasteBtn.addEventListener("click", async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      urlInput.value = text.trim();
      updateClearBtn();
      showToast("Enlace pegado desde el portapapeles");
      form.requestSubmit();
    }
  } catch {
    showToast("El navegador no permitió leer el portapapeles");
  }
});

$("copy-btn").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(urlInput.value.trim());
    showToast("Enlace copiado al portapapeles");
  } catch {
    showToast("No se pudo copiar el enlace");
  }
});

// ---------------------------------------------------------------------------
// Pestañas Video / Audio
// ---------------------------------------------------------------------------

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    // Mostrar solo el panel correspondiente
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
    const panel = $(`tab-${tab.dataset.tab}`);
    if (panel) panel.classList.remove("hidden");
  });
});

function switchTab(name) {
  document.querySelector(`.tab[data-tab="${name}"]`).click();
}

// ---------------------------------------------------------------------------
// Analizar URL
// ---------------------------------------------------------------------------

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;

  clearError();
  result.classList.add("hidden");
  downloading.classList.add("hidden");

  analyzeBtn.disabled = true;
  loader.classList.remove("hidden");

  try {
    currentVideo = await (await api("/api/info", { url })).json();
    renderResult(currentVideo);
    showToast("¡Video analizado con éxito! Elige tu formato.");
  } catch (err) {
    showError(err.message);
  } finally {
    analyzeBtn.disabled = false;
    loader.classList.add("hidden");
  }
});

function renderResult(video) {
  $("thumb").src = video.thumbnail || "";
  $("thumb").alt = video.title || "";
  $("video-title").textContent = video.title || "Sin título";
  $("video-uploader").textContent = video.uploader || "Autor desconocido";
  $("video-platform").textContent = video.extractor || "Web";
  $("video-views").textContent = formatViews(video.view_count);

  const durationEl = $("duration");
  if (video.duration_string && video.duration_string.includes(":")) {
    // Formatos tipo "3:05" o "1:02:33" ya vienen listos
    durationEl.textContent = video.duration_string;
    durationEl.classList.remove("hidden");
  } else if (video.duration) {
    const total = Math.floor(video.duration);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = String(total % 60).padStart(2, "0");
    durationEl.textContent = h > 0 ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
    durationEl.classList.remove("hidden");
  } else {
    durationEl.classList.add("hidden");
  }

  // ----- Pestaña de video: filas por calidad -----
  const list = $("quality-list");
  list.innerHTML = "";

  const qualities = video.qualities || [];

  if (qualities.length) {
    // Fila "Máxima calidad" primero
    list.appendChild(
      formatRow({
        icon: "⭐",
        label: "Máxima calidad",
        sub: `La mejor disponible · hasta ${qualities[0].label}`,
        badge: "Recomendado",
        mode: "best",
      })
    );

    for (const q of qualities) {
      list.appendChild(
        formatRow({
          icon: "🎬",
          label: q.label,
          sub: [q.ext ? q.ext.toUpperCase() : null, q.size, q.fps >= 50 ? `${q.fps} fps` : null]
            .filter(Boolean)
            .join(" · "),
          mode: `video-${q.height}`,
        })
      );
    }
  } else {
    list.innerHTML = `<p class="empty-note">No se detectaron calidades de video para este enlace. Prueba la pestaña "Solo Audio".</p>`;
  }

  // ----- Pestaña de audio -----
  const audioList = $("audio-list");
  audioList.innerHTML = "";
  if (video.audio_available) {
    audioList.appendChild(
      formatRow({
        icon: "🎵",
        label: "Audio MP3",
        sub: "192 kbps · Compatible con todos los reproductores",
        mode: "audio",
        isAudio: true,
      })
    );
  } else {
    audioList.innerHTML = `<p class="empty-note">Este enlace no tiene pista de audio descargable.</p>`;
  }

  // ----- Pestaña de extras: miniatura y subtítulos -----
  renderAssets(video);

  switchTab(qualities.length ? "video" : "audio");
  result.classList.remove("hidden");
}

function renderAssets(video) {
  // Miniatura
  const thumbAsset = $("thumb-asset");
  thumbAsset.src = video.thumbnail || "";
  $("thumb-btn").disabled = !video.thumbnail;

  // Subtítulos
  const subsList = $("subs-list");
  subsList.innerHTML = "";
  const subs = video.subtitles || [];

  if (!subs.length) {
    subsList.innerHTML = `<p class="empty-note">Este video no tiene subtítulos disponibles.</p>`;
    return;
  }

  for (const sub of subs) {
    const row = document.createElement("div");
    row.className = "sub-row";

    const name = document.createElement("span");
    name.className = "sub-name";
    name.innerHTML = `${escapeHtml(sub.label)}${sub.auto ? `<span class="sub-tag">Auto</span>` : ""}`;

    const actions = document.createElement("span");
    actions.className = "sub-actions";
    for (const fmt of ["srt", "vtt"]) {
      const btn = document.createElement("button");
      btn.className = "sub-btn";
      btn.textContent = `.${fmt.toUpperCase()}`;
      btn.addEventListener("click", () => downloadSubtitle(sub.lang, fmt));
      actions.appendChild(btn);
    }

    row.append(name, actions);
    subsList.appendChild(row);
  }
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function formatRow({ icon, label, sub, badge, mode, isAudio }) {
  const row = document.createElement("div");
  row.className = "format-row" + (isAudio ? " audio" : "");

  const info = document.createElement("div");
  info.className = "format-info";
  info.innerHTML = `
    <div class="format-icon">${icon}</div>
    <div>
      <div class="format-label">${label}${badge ? `<span class="format-badge">${badge}</span>` : ""}</div>
      <div class="format-sub">${sub || ""}</div>
    </div>`;

  const btn = document.createElement("button");
  btn.className = "download-btn";
  btn.textContent = isAudio ? "⬇ Descargar Audio" : "⬇ Descargar";
  btn.addEventListener("click", () => startDownload(mode));

  row.append(info, btn);
  return row;
}

// ---------------------------------------------------------------------------
// Descarga con progreso real (trabajos en segundo plano)
// ---------------------------------------------------------------------------

const POLL_INTERVAL_MS = 600;

let activeJobId = null;
let pollTimer = null;

async function startDownload(mode) {
  clearError();
  resetProgress();
  downloading.classList.remove("hidden");
  setButtonsDisabled(true);

  try {
    const res = await api("/api/jobs", {
      url: urlInput.value.trim(),
      mode,
      title: currentVideo?.title || null,
    });
    const { id } = await res.json();
    activeJobId = id;
    pollJob(id);
  } catch (err) {
    hideProgress();
    setButtonsDisabled(false);
    showError(err.message);
  }
}

function pollJob(jobId) {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    let job;
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) throw new Error("no disponible");
      job = await res.json();
    } catch {
      return; // fallo puntual de red: reintentar en el siguiente ciclo
    }

    updateProgress(job);

    if (job.status === "finished") {
      clearInterval(pollTimer);
      finishDownload(jobId, job.filename);
    } else if (job.status === "error") {
      clearInterval(pollTimer);
      hideProgress();
      setButtonsDisabled(false);
      showError(job.error || "No se pudo completar la descarga.");
    } else if (job.status === "cancelled") {
      clearInterval(pollTimer);
      hideProgress();
      setButtonsDisabled(false);
      showToast("Descarga cancelada");
    }
  }, POLL_INTERVAL_MS);
}

function updateProgress(job) {
  const pct = Math.max(0, Math.min(100, Number(job.percent) || 0));
  $("dl-fill").style.width = `${pct}%`;
  $("dl-percent").textContent = `${pct.toFixed(0)}%`;

  const labels = {
    pending: "Iniciando descarga…",
    downloading: job.phase === "audio" ? "Descargando audio…" : "Descargando video…",
    processing: "Procesando (uniendo audio y video con ffmpeg)…",
    finished: "¡Listo! Guardando archivo…",
  };
  $("dl-status").textContent = labels[job.status] || "Descargando…";

  $("dl-speed").textContent = job.speed ? `${formatBytes(job.speed)}/s` : "—";
  $("dl-size").textContent = job.total
    ? `${formatBytes(job.downloaded)} / ${formatBytes(job.total)}`
    : formatBytes(job.downloaded);
  $("dl-eta").textContent = job.eta ? `Quedan ${formatTime(job.eta)}` : "—";
}

function finishDownload(jobId, filename) {
  // Descargar el archivo servido por el backend (respeta Content-Disposition)
  const a = document.createElement("a");
  a.href = `/api/jobs/${jobId}/file`;
  a.download = filename || "video.mp4";
  document.body.appendChild(a);
  a.click();
  a.remove();

  setTimeout(() => {
    hideProgress();
    setButtonsDisabled(false);
    showToast(`Descarga completada: ${filename || "video"}`);
  }, 800);
}

$("dl-cancel").addEventListener("click", async () => {
  if (!activeJobId) return;
  $("dl-status").textContent = "Cancelando…";
  try {
    await fetch(`/api/jobs/${activeJobId}/cancel`, { method: "POST" });
  } catch {
    /* el sondeo detectará el estado final */
  }
});

function resetProgress() {
  $("dl-fill").style.width = "0%";
  $("dl-percent").textContent = "0%";
  $("dl-status").textContent = "Iniciando descarga…";
  $("dl-speed").textContent = "—";
  $("dl-size").textContent = "—";
  $("dl-eta").textContent = "—";
}

function hideProgress() {
  downloading.classList.add("hidden");
  activeJobId = null;
  clearInterval(pollTimer);
}

// ---------------------------------------------------------------------------
// Formato de datos
// ---------------------------------------------------------------------------

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let n = Number(bytes);
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatTime(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m} min ${s % 60} s` : `${s} s`;
}

async function downloadSubtitle(lang, format) {
  clearError();
  setButtonsDisabled(true);
  showToast("Preparando subtítulos…");

  try {
    const res = await api("/api/subtitles", {
      url: urlInput.value.trim(),
      lang,
      format,
      title: currentVideo?.title || null,
    });
    const filename = await saveResponseAsFile(res, `subtitulos.${lang}.${format}`);
    showToast(`Subtítulos descargados: ${filename}`);
  } catch (err) {
    showError(err.message);
  } finally {
    setButtonsDisabled(false);
  }
}

function downloadThumbnail() {
  if (!currentVideo?.thumbnail) return;
  const params = new URLSearchParams({
    url: currentVideo.thumbnail,
    title: currentVideo.title || "miniatura",
  });
  const a = document.createElement("a");
  a.href = `/api/thumbnail?${params}`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
  showToast("Descargando miniatura…");
}

$("thumb-btn").addEventListener("click", downloadThumbnail);

/** Guarda la respuesta como archivo, respetando el nombre del header Content-Disposition. */
async function saveResponseAsFile(res, fallbackName) {
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename\*=UTF-8''([^;]+)|filename="([^"]+)"/i);
  let filename = fallbackName;
  if (match) filename = match[1] ? decodeURIComponent(match[1]) : match[2];

  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(blobUrl);
  return filename;
}

function setButtonsDisabled(disabled) {
  document.querySelectorAll(".download-btn, .sub-btn").forEach((b) => (b.disabled = disabled));
}
