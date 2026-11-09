/* Acortador de enlaces. Utilidades compartidas en common.js (window.VD). */

const { $, t, showToast, showError, clearError, fetchWithTimeout, readJson } = window.VD;

const form = $("shorten-form");
const longInput = $("long-url");
const shortenBtn = $("shorten-btn");
const resultSection = $("result");
const shortInput = $("short-url");

const checkForm = $("check-form");
const checkInput = $("check-input");
const checkBtn = $("check-btn");
const checkResult = $("check-result");
const reportBtn = $("report-btn");

const STORAGE_KEY = "fastools.links";
const MAX_RECENT = 10;
let checkedCode = null;

$("error-close").addEventListener("click", clearError);

// ---------------------------------------------------------------------------
// Enlaces recientes (solo en el navegador)
// ---------------------------------------------------------------------------

function loadRecent() {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((r) => r && r.code && r.path) : [];
  } catch {
    return [];
  }
}

function saveRecent(list) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, MAX_RECENT)));
  } catch {
    /* almacenamiento bloqueado: la lista simplemente no se recuerda */
  }
}

function addRecent(entry) {
  const list = loadRecent().filter((r) => r.code !== entry.code);
  list.unshift(entry);
  saveRecent(list);
  renderRecent();
}

function fullUrl(path) {
  return `${location.origin}${path}`;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function renderRecent() {
  const list = loadRecent();
  const box = $("recent");
  const ul = $("recent-list");
  box.classList.toggle("hidden", list.length === 0);
  ul.innerHTML = "";
  list.forEach((item) => {
    const li = document.createElement("li");
    li.className = "link-item";

    const info = document.createElement("div");
    info.className = "link-item-info";
    const short = document.createElement("span");
    short.className = "link-item-short mono";
    short.textContent = fullUrl(item.path);
    const dest = document.createElement("span");
    dest.className = "link-item-dest";
    dest.textContent = item.host || "";
    info.append(short, dest);

    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "ghost-btn small";
    copy.textContent = t("shortener.copy", "Copiar");
    copy.addEventListener("click", async () => {
      showToast(
        (await copyText(fullUrl(item.path)))
          ? t("shortener.copied", "Enlace copiado")
          : t("shortener.copyFailed", "No se pudo copiar. Selecciónalo y cópialo a mano."),
        { error: false }
      );
    });

    li.append(info, copy);
    ul.appendChild(li);
  });
}

$("recent-clear").addEventListener("click", () => {
  saveRecent([]);
  renderRecent();
});

// ---------------------------------------------------------------------------
// Acortar
// ---------------------------------------------------------------------------

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError();

  const url = longInput.value.trim();
  if (!url) {
    showError(t("shortener.empty", "Escribe el enlace que quieres acortar."));
    longInput.focus();
    return;
  }

  shortenBtn.disabled = true;
  window.VD.track("tool_start");
  try {
    const res = await fetchWithTimeout(
      "/api/links",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      },
      20000
    );
    const data = await readJson(res);
    if (!res.ok || !data || !data.path) {
      throw new Error(
        (data && data.detail) ||
          t("shortener.failed", "No se pudo acortar el enlace. Inténtalo de nuevo.")
      );
    }

    window.VD.track("tool_complete");
    shortInput.value = fullUrl(data.path);
    $("result-dest").textContent = t("shortener.goesTo", `Lleva a: ${data.host}`, {
      host: data.host,
    });
    resultSection.classList.remove("hidden");
    resultSection.scrollIntoView({ behavior: "smooth", block: "center" });
    addRecent({ code: data.code, path: data.path, host: data.host, ts: Date.now() });
  } catch (err) {
    showError(err.message);
  } finally {
    shortenBtn.disabled = false;
  }
});

$("copy-btn").addEventListener("click", async () => {
  if (await copyText(shortInput.value)) {
    showToast(t("shortener.copied", "Enlace copiado"));
  } else {
    shortInput.select();
    showToast(t("shortener.copyFailed", "No se pudo copiar. Selecciónalo y cópialo a mano."), {
      error: true,
    });
  }
});

shortInput.addEventListener("focus", () => shortInput.select());

$("again-btn").addEventListener("click", () => {
  resultSection.classList.add("hidden");
  longInput.value = "";
  longInput.focus();
});

// ---------------------------------------------------------------------------
// Comprobar y reportar
// ---------------------------------------------------------------------------

/** Acepta un enlace corto completo o solo el código. */
function parseCode(text) {
  const m = String(text || "")
    .trim()
    .match(/(?:^|\/l\/)([A-Za-z0-9]{4,12})\/?(?:[?#].*)?$/);
  return m ? m[1] : null;
}

checkForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError();
  checkResult.classList.add("hidden");
  checkedCode = null;

  const code = parseCode(checkInput.value);
  if (!code) {
    showError(t("shortener.badCode", "Pega un enlace corto de este sitio o su código."));
    return;
  }

  checkBtn.disabled = true;
  try {
    const res = await fetchWithTimeout(`/api/links/${encodeURIComponent(code)}`, {}, 15000);
    const data = await readJson(res);
    if (!res.ok || !data || !data.url) {
      throw new Error(
        (data && data.detail) || t("shortener.notFound", "Ese enlace corto no existe.")
      );
    }

    checkedCode = code;
    $("check-url").textContent = data.url;
    $("check-meta").textContent = t(
      "shortener.checkMeta",
      `Sitio: ${data.host} · Visitas: ${data.clicks}`,
      { host: data.host, clicks: data.clicks }
    );
    const open = $("check-open");
    // El servidor ya solo admite http(s); se vuelve a comprobar por seguridad.
    if (/^https?:\/\//i.test(data.url)) {
      open.href = data.url;
      open.classList.remove("hidden");
    } else {
      open.removeAttribute("href");
      open.classList.add("hidden");
    }
    reportBtn.disabled = false;
    checkResult.classList.remove("hidden");
  } catch (err) {
    showError(err.message);
  } finally {
    checkBtn.disabled = false;
  }
});

reportBtn.addEventListener("click", async () => {
  if (!checkedCode) return;
  reportBtn.disabled = true;
  try {
    const res = await fetchWithTimeout(
      `/api/links/${encodeURIComponent(checkedCode)}/report`,
      { method: "POST" },
      15000
    );
    const data = await readJson(res);
    if (!res.ok) {
      throw new Error(
        (data && data.detail) || t("shortener.reportFailed", "No se pudo enviar el reporte.")
      );
    }
    showToast(
      data && data.status === "disabled"
        ? t("shortener.reportBlocked", "Gracias. El enlace quedó bloqueado.")
        : t("shortener.reported", "Gracias. Hemos registrado tu reporte.")
    );
  } catch (err) {
    reportBtn.disabled = false;
    showError(err.message);
  }
});

renderRecent();
