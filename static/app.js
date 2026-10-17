/* Descargador universal de vídeo/audio.
   Las utilidades compartidas (avisos, fetch con timeout, sondeo…) viven en
   common.js y se exponen en window.VD. */

const {
  $,
  showToast,
  showError,
  clearError,
  formatBytes,
  fmtClock,
  api,
  errorFromResponse,
  pollJob: pollJobBase,
  triggerDownload,
  saveResponseAsFile,
} = window.VD;

const form = $("url-form");
const urlInput = $("url-input");
const analyzeBtn = $("analyze-btn");
const pasteBtn = $("paste-btn");
const clearBtn = $("clear-btn");
const loader = $("loader");
const result = $("result");
const downloading = $("downloading");

let currentVideo = null;

$("error-close").addEventListener("click", clearError);

// ---------------------------------------------------------------------------
// Utilidades propias de esta página
// ---------------------------------------------------------------------------

function formatViews(n) {
  if (!n) return "";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} M vistas`;
  if (n >= 1_000) return `${Math.round(n / 1_000)} mil vistas`;
  return `${n} vistas`;
}

/** Segundos -> "m min s s" (para la ETA). */
function formatTime(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m} min ${s % 60} s` : `${s} s`;
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
    showToast("El navegador no permitió leer el portapapeles", { error: true });
  }
});

$("copy-btn").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(urlInput.value.trim());
    showToast("Enlace copiado al portapapeles");
  } catch {
    showToast("No se pudo copiar el enlace", { error: true });
  }
});

// ---------------------------------------------------------------------------
// Recortador de fragmentos
// ---------------------------------------------------------------------------

const trimToggle = $("trim-toggle");
const trimPanel = $("trim-panel");
const trimStart = $("trim-start");
const trimEnd = $("trim-end");
const trimStartNum = $("trim-start-num");
const trimEndNum = $("trim-end-num");

let trimActive = false;
let videoDuration = 0;

function clamp(n, min, max) {
  return Math.min(Math.max(n, min), max);
}

/** Prepara el recortador cuando se analiza un video nuevo. */
function setupTrim(duration) {
  videoDuration = Math.floor(duration || 0);
  const hasDuration = videoDuration > 0;

  trimToggle.classList.toggle("hidden", !hasDuration);
  if (!hasDuration) {
    setTrimActive(false);
    return;
  }

  for (const el of [trimStart, trimEnd]) {
    el.min = "0";
    el.max = String(videoDuration);
  }
  for (const el of [trimStartNum, trimEndNum]) {
    el.min = "0";
    el.max = String(videoDuration);
  }
  resetTrim();
}

function setTrimActive(active) {
  trimActive = active;
  trimToggle.classList.toggle("active", active);
  trimToggle.setAttribute("aria-expanded", String(active));
  trimPanel.classList.toggle("hidden", !active);
}

function resetTrim() {
  trimStart.value = "0";
  trimEnd.value = String(videoDuration);
  trimStartNum.value = "0";
  trimEndNum.value = String(videoDuration);
  refreshTrim();
}

/** Lee inicio/fin actuales (ya acotados a la duración). */
function currentTrim() {
  const start = clamp(parseFloat(trimStartNum.value) || 0, 0, videoDuration);
  const end = clamp(parseFloat(trimEndNum.value) || 0, 0, videoDuration);
  return { start, end };
}

/** Actualiza etiquetas y validación; devuelve si el rango es válido. */
function refreshTrim() {
  const { start, end } = currentTrim();
  $("trim-range").textContent = `${fmtClock(start)} – ${fmtClock(end)}`;

  const valid = end - start >= 1;
  const hint = $("trim-hint");
  hint.classList.toggle("invalid", trimActive && !valid);
  hint.textContent = valid
    ? `Solo se descargará esa parte (dura ${fmtClock(end - start)}).`
    : "El fin debe ser mayor que el inicio (mínimo 1 segundo).";
  return valid;
}

trimToggle.addEventListener("click", () => {
  setTrimActive(!trimActive);
  if (trimActive) refreshTrim();
});

trimStart.addEventListener("input", () => {
  trimStartNum.value = trimStart.value;
  refreshTrim();
});
trimEnd.addEventListener("input", () => {
  trimEndNum.value = trimEnd.value;
  refreshTrim();
});
trimStartNum.addEventListener("input", () => {
  trimStart.value = trimStartNum.value;
  refreshTrim();
});
trimEndNum.addEventListener("input", () => {
  trimEnd.value = trimEndNum.value;
  refreshTrim();
});
$("trim-reset").addEventListener("click", resetTrim);

/** Devuelve {start, end} si hay un recorte real activo, o null. */
function activeTrim() {
  if (!trimActive) return null;
  const { start, end } = currentTrim();
  // Si cubre todo el video, no hace falta recortar
  if (start <= 0 && end >= videoDuration) return null;
  return { start, end };
}

// ---------------------------------------------------------------------------
// Pestañas Video / Audio / Extras (con soporte de teclado y ARIA)
// ---------------------------------------------------------------------------

const tabs = Array.from(document.querySelectorAll(".tab"));

function selectTab(tab) {
  for (const t of tabs) {
    const active = t === tab;
    t.classList.toggle("active", active);
    t.setAttribute("aria-selected", String(active));
    t.setAttribute("tabindex", active ? "0" : "-1");
  }
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
  const panel = $(`tab-${tab.dataset.tab}`);
  if (panel) panel.classList.remove("hidden");
}

tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => selectTab(tab));
  tab.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const dir = e.key === "ArrowRight" ? 1 : -1;
    const next = tabs[(index + dir + tabs.length) % tabs.length];
    next.focus();
    selectTab(next);
  });
});

function switchTab(name) {
  const tab = document.querySelector(`.tab[data-tab="${name}"]`);
  if (tab) selectTab(tab);
}

// ---------------------------------------------------------------------------
// Analizar URL
// ---------------------------------------------------------------------------

// Cada análisis incrementa el token; las respuestas que llegan tarde se ignoran
// (evita que el resultado de una URL antigua pise al de la actual).
let analyzeToken = 0;

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;

  const token = ++analyzeToken;

  clearError();
  result.classList.add("hidden");
  downloading.classList.add("hidden");

  analyzeBtn.disabled = true;
  loader.classList.remove("hidden");

  try {
    const res = await api("/api/info", { url }, { timeoutMs: 45000 });
    const data = await res.json();
    if (token !== analyzeToken) return; // llegó tarde: hay un análisis más nuevo
    currentVideo = data;
    renderResult(currentVideo);
    showToast("¡Video analizado con éxito! Elige tu formato.");
  } catch (err) {
    if (token !== analyzeToken) return;
    showError(err.message);
  } finally {
    if (token === analyzeToken) {
      analyzeBtn.disabled = false;
      loader.classList.add("hidden");
    }
  }
});

function renderResult(video) {
  $("thumb").src = video.thumbnail || "";
  $("thumb").alt = video.title ? `Miniatura de ${video.title}` : "";
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
    durationEl.textContent = fmtClock(video.duration);
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

  // ----- Recortador de fragmentos -----
  setupTrim(video.duration);

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
    name.textContent = sub.label || sub.lang;
    if (sub.auto) {
      const tag = document.createElement("span");
      tag.className = "sub-tag";
      tag.textContent = "Auto";
      name.appendChild(tag);
    }

    const actions = document.createElement("span");
    actions.className = "sub-actions";
    for (const format of ["srt", "vtt"]) {
      const btn = document.createElement("button");
      btn.className = "sub-btn";
      btn.type = "button";
      btn.textContent = `.${format.toUpperCase()}`;
      btn.setAttribute("aria-label", `Descargar subtítulos en formato ${format.toUpperCase()}`);
      btn.addEventListener("click", () => downloadSubtitle(sub.lang, format));
      actions.appendChild(btn);
    }

    row.append(name, actions);
    subsList.appendChild(row);
  }
}

/**
 * Construye una fila de calidad usando textContent.
 * (La versión anterior interpolaba la etiqueta en innerHTML: si el título o la
 * calidad traían HTML —por ejemplo una URL manipulada— se ejecutaba.)
 */
function formatRow({ icon, label, sub, badge, mode, isAudio }) {
  const row = document.createElement("div");
  row.className = "format-row" + (isAudio ? " audio" : "");

  const info = document.createElement("div");
  info.className = "format-info";

  const iconEl = document.createElement("div");
  iconEl.className = "format-icon";
  iconEl.setAttribute("aria-hidden", "true");
  iconEl.textContent = icon;

  const body = document.createElement("div");
  const labelEl = document.createElement("div");
  labelEl.className = "format-label";
  labelEl.textContent = label;
  if (badge) {
    const badgeEl = document.createElement("span");
    badgeEl.className = "format-badge";
    badgeEl.textContent = badge;
    labelEl.appendChild(badgeEl);
  }
  const subEl = document.createElement("div");
  subEl.className = "format-sub";
  subEl.textContent = sub || "";
  body.append(labelEl, subEl);
  info.append(iconEl, body);

  const btn = document.createElement("button");
  btn.className = "download-btn";
  btn.type = "button";
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
let pollRunId = 0;

async function startDownload(mode) {
  clearError();

  // Validar el recorte antes de lanzar nada
  if (trimActive && !refreshTrim()) {
    showError("Revisa el fragmento: el fin debe ser mayor que el inicio (mínimo 1 segundo).");
    return;
  }
  const trim = activeTrim();

  resetProgress();
  downloading.classList.remove("hidden");
  setButtonsDisabled(true);

  try {
    const res = await api("/api/jobs", {
      url: urlInput.value.trim(),
      mode,
      title: currentVideo?.title || null,
      start: trim ? trim.start : null,
      end: trim ? trim.end : null,
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

async function pollJob(jobId) {
  const runId = ++pollRunId;
  try {
    const job = await pollJobBase({
      intervalMs: POLL_INTERVAL_MS,
      fetcher: async () => {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) throw await errorFromResponse(res, "Trabajo no disponible");
        return res.json();
      },
      onUpdate: (j) => {
        if (runId === pollRunId) updateProgress(j);
      },
    });
    if (runId !== pollRunId) return;

    if (job.status === "finished") {
      finishDownload(jobId, job.filename);
    } else if (job.status === "error") {
      hideProgress();
      setButtonsDisabled(false);
      showError(job.error || "No se pudo completar la descarga.");
    } else if (job.status === "cancelled") {
      hideProgress();
      setButtonsDisabled(false);
      showToast("Descarga cancelada");
    }
  } catch (err) {
    if (runId !== pollRunId) return;
    hideProgress();
    setButtonsDisabled(false);
    showError(err.message);
  }
}

function updateProgress(job) {
  const pct = Math.max(0, Math.min(100, Number(job.percent) || 0));
  $("dl-fill").style.width = `${pct}%`;
  $("dl-percent").textContent = `${pct.toFixed(0)}%`;
  $("dl-track").setAttribute("aria-valuenow", String(Math.round(pct)));

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
  triggerDownload(`/api/jobs/${jobId}/file`, filename || "video.mp4");

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
  $("dl-track").setAttribute("aria-valuenow", "0");
  $("dl-status").textContent = "Iniciando descarga…";
  $("dl-speed").textContent = "—";
  $("dl-size").textContent = "—";
  $("dl-eta").textContent = "—";
}

function hideProgress() {
  downloading.classList.add("hidden");
  activeJobId = null;
  pollRunId++; // invalida cualquier sondeo en curso
}

// ---------------------------------------------------------------------------
// Cola de descargas en lote
// ---------------------------------------------------------------------------

const BATCH_STORAGE_KEY = "videodl_batch";

const batchSection = $("batch");
const batchList = $("batch-list");
const batchUrls = $("batch-urls");
const batchMode = $("batch-mode");

let batchItems = [];
let batchRunning = false;
const batchRefs = new Map();

function newId() {
  try {
    return crypto.randomUUID();
  } catch {
    return `b${Date.now()}${Math.floor(Math.random() * 1e6)}`;
  }
}

function loadBatch() {
  try {
    const raw = localStorage.getItem(BATCH_STORAGE_KEY);
    const saved = raw ? JSON.parse(raw) : [];
    batchItems = saved.map((it) => {
      const item = { ...it, id: it.id || newId() };
      // Los estados transitorios vuelven a un estado estable
      item.analyzed = Boolean(item.title);
      if (item.status === "downloading" || item.status === "analyzing") {
        item.status = item.analyzed ? "ready" : "pending";
      }
      if (item.status === "pending" && item.analyzed) item.status = "ready";
      item.percent = 0;
      item.phase = null;
      return item;
    });
  } catch {
    batchItems = [];
  }
  if (batchItems.length) showBatchSection();
  renderBatch();
}

function saveBatch() {
  try {
    const data = batchItems.map((it) => ({
      id: it.id,
      url: it.url,
      title: it.title,
      thumbnail: it.thumbnail,
      duration: it.duration,
      status: it.status,
      error: it.error,
      filename: it.filename,
    }));
    localStorage.setItem(BATCH_STORAGE_KEY, JSON.stringify(data));
  } catch {
    /* localStorage no disponible */
  }
}

function showBatchSection() {
  batchSection.classList.remove("hidden");
  $("batch-toggle").classList.add("active");
  $("batch-toggle").setAttribute("aria-expanded", "true");
}

$("batch-toggle").addEventListener("click", () => {
  const showing = !batchSection.classList.contains("hidden");
  batchSection.classList.toggle("hidden", showing);
  $("batch-toggle").classList.toggle("active", !showing);
  $("batch-toggle").setAttribute("aria-expanded", String(!showing));
  if (!showing) batchSection.scrollIntoView({ behavior: "smooth", block: "start" });
});

function renderBatch() {
  batchList.innerHTML = "";
  batchRefs.clear();

  if (!batchItems.length) {
    batchList.innerHTML = `<p class="empty-note">Aún no hay enlaces en la cola. Pega uno o varios enlaces arriba y pulsa "Añadir a la cola".</p>`;
  } else {
    for (const item of batchItems) batchList.appendChild(batchItemRow(item));
  }
  updateBatchCount();
}

function batchItemRow(item) {
  const row = document.createElement("div");
  row.className = "batch-item";

  const img = document.createElement("img");
  img.className = "batch-thumb";
  img.alt = "";
  if (item.thumbnail) img.src = item.thumbnail;

  const info = document.createElement("div");
  info.className = "batch-item-info";

  const title = document.createElement("div");
  title.className = "batch-item-title";
  title.textContent = item.title || item.url;

  const sub = document.createElement("div");
  sub.className = "batch-item-sub";

  const track = document.createElement("div");
  track.className = "batch-track hidden";
  const fill = document.createElement("div");
  fill.className = "batch-fill";
  track.appendChild(fill);

  info.append(title, sub, track);

  const badge = document.createElement("span");
  badge.className = "batch-badge pending";

  const remove = document.createElement("button");
  remove.className = "batch-remove";
  remove.type = "button";
  remove.textContent = "✕";
  remove.title = "Quitar de la cola";
  remove.setAttribute("aria-label", `Quitar ${item.title || item.url} de la cola`);
  remove.addEventListener("click", () => {
    if (batchRunning && item.status === "downloading") return;
    batchItems = batchItems.filter((i) => i.id !== item.id);
    saveBatch();
    renderBatch();
  });

  row.append(img, info, badge, remove);
  batchRefs.set(item.id, { title, sub, badge, fill, track, img });
  updateBatchItemUI(item);
  return row;
}

function updateBatchItemUI(item) {
  const ref = batchRefs.get(item.id);
  if (!ref) return;
  const { title, sub, badge, fill, track, img } = ref;

  const classMap = {
    pending: "pending",
    analyzing: "active",
    ready: "ready",
    downloading: "active",
    done: "done",
    error: "error",
  };
  const labelMap = {
    pending: "Pendiente",
    analyzing: "Analizando…",
    ready: "Listo",
    downloading: "Descargando…",
    done: "Completado",
    error: "Error",
  };

  title.textContent = item.title || item.url;
  badge.textContent = labelMap[item.status] || item.status;
  badge.className = `batch-badge ${classMap[item.status] || "pending"}`;
  if (item.thumbnail) img.src = item.thumbnail;

  if (item.status === "downloading") {
    track.classList.remove("hidden");
    const pct = Math.max(0, Math.min(100, item.percent || 0));
    fill.style.width = `${pct}%`;
    sub.textContent = `${pct.toFixed(0)}% · ${item.phase === "audio" ? "audio" : "video"}`;
  } else {
    track.classList.add("hidden");
    fill.style.width = "0%";
    if (item.status === "done") sub.textContent = item.filename || "Descargado";
    else if (item.status === "error") sub.textContent = item.error || "No se pudo descargar";
    else if (item.status === "ready") sub.textContent = item.duration ? `Duración ${fmtClock(item.duration)}` : "Listo para descargar";
    else if (item.status === "analyzing") sub.textContent = "Obteniendo información…";
    else sub.textContent = "Pendiente de análisis";
  }

  updateBatchCount();
}

function updateBatchCount() {
  const total = batchItems.length;
  const done = batchItems.filter((i) => i.status === "done").length;
  $("batch-count").textContent = total ? `${total} enlace(s) · ${done} completado(s)` : "";
}

// --- Añadir enlaces ---

$("batch-add").addEventListener("click", addBatchFromText);

async function addBatchFromText() {
  const lines = batchUrls.value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  const urls = [];
  for (const line of lines) {
    const found = line.match(/https?:\/\/[^\s"'<>]+/gi) || [];
    for (const u of found) urls.push(u);
  }

  const nuevos = urls.filter((u) => !batchItems.some((i) => i.url === u));
  if (!nuevos.length) {
    showToast(
      urls.length ? "Esos enlaces ya están en la cola" : "No se encontraron enlaces válidos",
      { error: !urls.length }
    );
    return;
  }

  showBatchSection();
  for (const url of nuevos) {
    batchItems.push({
      id: newId(),
      url,
      title: "",
      thumbnail: "",
      duration: 0,
      analyzed: false,
      status: "analyzing",
      error: null,
      filename: null,
      percent: 0,
      phase: null,
    });
  }
  batchUrls.value = "";
  saveBatch();
  renderBatch();

  // Analizar de uno en uno para no saturar las plataformas
  for (const item of batchItems.filter((i) => nuevos.includes(i.url))) {
    await analyzeBatchItem(item);
  }
}

async function analyzeBatchItem(item) {
  item.status = "analyzing";
  updateBatchItemUI(item);
  try {
    const res = await api("/api/info", { url: item.url }, { timeoutMs: 45000 });
    const info = await res.json();
    item.title = info.title || item.url;
    item.thumbnail = info.thumbnail || "";
    item.duration = info.duration || 0;
    item.analyzed = true;
    item.status = "ready";
    item.error = null;
  } catch (err) {
    item.analyzed = false;
    item.status = "error";
    item.error = err.message;
  }
  saveBatch();
  updateBatchItemUI(item);
}

// --- Descargar toda la cola ---

$("batch-start").addEventListener("click", startBatch);
$("batch-clear").addEventListener("click", () => {
  if (batchRunning) return;
  batchItems = [];
  saveBatch();
  renderBatch();
  showToast("Cola vaciada");
});

function setBatchRunning(running) {
  batchRunning = running;
  $("batch-add").disabled = running;
  $("batch-clear").disabled = running;
  batchMode.disabled = running;
  const startBtn = $("batch-start");
  startBtn.disabled = running;
  startBtn.textContent = running ? "⏳ Descargando…" : "⬇ Descargar todo";
}

async function startBatch() {
  if (batchRunning) return;
  const pendientes = batchItems.filter((i) => i.status !== "done");
  if (!pendientes.length) {
    showToast("No hay enlaces pendientes en la cola");
    return;
  }

  clearError();
  setBatchRunning(true);
  let ok = 0;
  let fail = 0;

  for (const item of pendientes) {
    if (!item.analyzed) {
      await analyzeBatchItem(item);
    }
    if (!item.analyzed) {
      fail++;
      continue;
    }
    const success = await runBatchItem(item);
    if (success) ok++;
    else fail++;
  }

  setBatchRunning(false);
  saveBatch();
  showToast(`Lote terminado: ${ok} descargado(s)${fail ? `, ${fail} con error` : ""}`);
}

async function runBatchItem(item) {
  const mode = batchMode.value;
  item.status = "downloading";
  item.error = null;
  item.percent = 0;
  item.phase = null;
  updateBatchItemUI(item);

  let jobId;
  try {
    const res = await api("/api/jobs", { url: item.url, mode, title: item.title || null });
    jobId = (await res.json()).id;
  } catch (err) {
    item.status = "error";
    item.error = err.message;
    updateBatchItemUI(item);
    return false;
  }

  let result;
  try {
    result = await waitForJob(jobId, (job) => {
      item.percent = job.percent || 0;
      item.phase = job.phase;
      updateBatchItemUI(item);
    });
  } catch (err) {
    item.status = "error";
    item.error = err.message;
    updateBatchItemUI(item);
    return false;
  }

  if (result.status === "finished") {
    triggerDownload(`/api/jobs/${jobId}/file`, result.filename || "video.mp4");
    item.status = "done";
    item.filename = result.filename || "video";
    updateBatchItemUI(item);
    return true;
  }

  item.status = "error";
  item.error =
    result.status === "cancelled" ? "Cancelado" : result.error || "No se pudo descargar";
  updateBatchItemUI(item);
  return false;
}

/** Espera a que un trabajo termine, avisando del progreso. */
function waitForJob(jobId, onUpdate) {
  return pollJobBase({
    intervalMs: POLL_INTERVAL_MS,
    fetcher: async () => {
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) throw await errorFromResponse(res, "Trabajo no disponible");
      return res.json();
    },
    onUpdate,
  });
}

// ---------------------------------------------------------------------------
// Subtítulos y miniatura
// ---------------------------------------------------------------------------

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
  triggerDownload(`/api/thumbnail?${params}`);
  showToast("Descargando miniatura…");
}

$("thumb-btn").addEventListener("click", downloadThumbnail);

function setButtonsDisabled(disabled) {
  document.querySelectorAll(".download-btn, .sub-btn").forEach((b) => (b.disabled = disabled));
}

// ---------------------------------------------------------------------------
// Arranque
// ---------------------------------------------------------------------------

loadBatch();
