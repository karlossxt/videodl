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
    $("tab-video").classList.toggle("hidden", tab.dataset.tab !== "video");
    $("tab-audio").classList.toggle("hidden", tab.dataset.tab !== "audio");
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

  switchTab(qualities.length ? "video" : "audio");
  result.classList.remove("hidden");
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
// Descarga
// ---------------------------------------------------------------------------

async function startDownload(mode) {
  clearError();
  downloading.classList.remove("hidden");
  setButtonsDisabled(true);

  try {
    const res = await api("/api/download", {
      url: urlInput.value.trim(),
      mode,
      title: currentVideo?.title || null,
    });

    const disposition = res.headers.get("Content-Disposition") || "";
    const match = disposition.match(/filename\*=UTF-8''([^;]+)|filename="([^"]+)"/i);
    let filename = "video.mp4";
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

    showToast(`Descarga completada: ${filename}`);
  } catch (err) {
    showError(err.message);
  } finally {
    downloading.classList.add("hidden");
    setButtonsDisabled(false);
  }
}

function setButtonsDisabled(disabled) {
  document.querySelectorAll(".download-btn").forEach((b) => (b.disabled = disabled));
}
