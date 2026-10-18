/* Generador de enlaces de WhatsApp.
   El enlace se construye aquí (es texto plano, así se ve al instante y el
   número no sale del navegador). Del servidor solo se pide el código QR.
   Utilidades compartidas en common.js (window.VD). */

const { $, showToast, showError, clearError, api, errorFromResponse } = window.VD;

const countrySel = $("wa-country");
const prefixInput = $("wa-prefix");
const numberInput = $("wa-number");
const messageInput = $("wa-message");
const anyCheckbox = $("wa-any");
const linkInput = $("wa-link");
const statusEl = $("wa-status");
const counterEl = $("wa-counter");
const qrImg = $("wa-qr");
const qrEmpty = $("wa-qr-empty");
const qrHint = $("wa-qr-hint");

const MAX_MESSAGE = 700;
const MIN_DIGITS = 8;
const MAX_DIGITS = 15;
const QR_DEBOUNCE_MS = 700;

let qrUrl = null; // blob: del QR visible (hay que revocarlo al reemplazarlo)
let qrLink = null; // enlace que representa ese QR
let qrRunId = 0; // invalida respuestas antiguas si el enlace cambia mientras se genera
let qrTimer = null;

$("error-close").addEventListener("click", clearError);

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------

const digits = (value) => String(value || "").replace(/\D/g, "");

/** Número final en formato WhatsApp: prefijo + número, solo dígitos. */
function buildNumber() {
  const prefix = digits(prefixInput.value);
  let local = digits(numberInput.value);

  // Si pegan el número entero (con "00" o con el propio prefijo) no se duplica.
  if (local.startsWith("00")) local = local.slice(2);
  if (prefix && local.startsWith(prefix) && local.length > prefix.length + 5) {
    local = local.slice(prefix.length);
  }
  return prefix + local;
}

function buildLink() {
  const text = messageInput.value.trim();
  const query = text ? `?text=${encodeURIComponent(text)}` : "";
  if (anyCheckbox.checked) return `https://wa.me/${query}`;

  const number = buildNumber();
  if (number.length < MIN_DIGITS || number.length > MAX_DIGITS) return "";
  return `https://wa.me/${number}${query}`;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Reserva para navegadores sin permiso de portapapeles (o http sin TLS).
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    area.remove();
    return ok;
  }
}

function setActionsEnabled(enabled) {
  ["wa-copy", "wa-open", "wa-share", "wa-html"].forEach((id) => {
    $(id).disabled = !enabled;
  });
  $("wa-qr-download").disabled = !enabled || !qrUrl;
}

// ---------------------------------------------------------------------------
// Actualización del enlace (al instante, sin tocar el servidor)
// ---------------------------------------------------------------------------

function update() {
  clearError();

  const link = buildLink();
  linkInput.value = link;
  counterEl.textContent = `${messageInput.value.length} / ${MAX_MESSAGE}`;

  if (!link) {
    statusEl.textContent = anyCheckbox.checked
      ? "Sin número fijo"
      : "Escribe tu número";
    setActionsEnabled(false);
    clearQr();
    return;
  }

  setActionsEnabled(true);
  statusEl.textContent = "Enlace listo";
  scheduleQr(link);
}

// ---------------------------------------------------------------------------
// Código QR (servidor)
// ---------------------------------------------------------------------------

function scheduleQr(link) {
  if (link === qrLink) return;
  clearTimeout(qrTimer);
  qrTimer = setTimeout(() => refreshQr(link), QR_DEBOUNCE_MS);
}

function clearQr() {
  clearTimeout(qrTimer);
  qrRunId++;
  qrLink = null;
  if (qrUrl) {
    URL.revokeObjectURL(qrUrl);
    qrUrl = null;
  }
  qrImg.removeAttribute("src");
  qrImg.classList.add("hidden");
  qrEmpty.classList.remove("hidden");
  setActionsEnabled(false);
}

async function refreshQr(link) {
  const runId = ++qrRunId;
  qrHint.textContent = "Generando el código QR…";

  try {
    const res = await api("/api/whatsapp/qr", { link }, { timeoutMs: 20000 });
    const blob = await res.blob();
    if (runId !== qrRunId) return; // el enlace ya ha cambiado

    if (qrUrl) URL.revokeObjectURL(qrUrl);
    qrUrl = URL.createObjectURL(blob);
    qrLink = link;

    qrImg.src = qrUrl;
    qrImg.classList.remove("hidden");
    qrEmpty.classList.add("hidden");
    qrHint.textContent =
      link.length > 320
        ? "El mensaje es largo: el QR queda muy denso. Para imprimirlo, usa un texto más corto."
        : "El QR se genera en el servidor a partir del enlace y no se guarda.";
    setActionsEnabled(true);
  } catch (err) {
    if (runId !== qrRunId) return;
    qrHint.textContent = "No se pudo generar el código QR.";
    showError(err.message || "No se pudo generar el código QR.");
  }
}

// ---------------------------------------------------------------------------
// Entradas
// ---------------------------------------------------------------------------

countrySel.addEventListener("change", () => {
  prefixInput.value = countrySel.value;
  update();
});

prefixInput.addEventListener("input", () => {
  prefixInput.value = digits(prefixInput.value);
  update();
});

numberInput.addEventListener("input", update);

messageInput.addEventListener("input", update);

anyCheckbox.addEventListener("change", () => {
  numberInput.disabled = anyCheckbox.checked;
  prefixInput.disabled = anyCheckbox.checked;
  update();
});

$("wa-templates").addEventListener("click", (event) => {
  const chip = event.target.closest(".wa-chip");
  if (!chip) return;
  messageInput.value = chip.dataset.msg || "";
  messageInput.focus();
  update();
});

// ---------------------------------------------------------------------------
// Acciones sobre el enlace
// ---------------------------------------------------------------------------

$("wa-copy").addEventListener("click", async () => {
  if (await copyText(linkInput.value)) showToast("Enlace copiado");
  else showToast("No se pudo copiar el enlace", { error: true });
});

$("wa-open").addEventListener("click", () => {
  window.open(linkInput.value, "_blank", "noopener,noreferrer");
});

$("wa-share").addEventListener("click", async () => {
  const link = linkInput.value;
  const text = messageInput.value.trim();
  if (navigator.share) {
    try {
      await navigator.share({ title: "Escríbeme por WhatsApp", text, url: link });
      return;
    } catch {
      return; // el usuario ha cerrado el diálogo de compartir
    }
  }
  if (await copyText(link)) showToast("Enlace copiado (tu navegador no permite compartir)");
  else showToast("No se pudo compartir el enlace", { error: true });
});

$("wa-html").addEventListener("click", async () => {
  const snippet = `<a href="${linkInput.value}" target="_blank" rel="noopener">Escríbeme por WhatsApp</a>`;
  if (await copyText(snippet)) showToast("Botón HTML copiado");
  else showToast("No se pudo copiar el código", { error: true });
});

$("wa-qr-download").addEventListener("click", () => {
  if (!qrUrl) {
    showToast("El código QR aún no está listo", { error: true });
    return;
  }
  const a = document.createElement("a");
  a.href = qrUrl;
  a.download = "whatsapp-qr.png";
  document.body.appendChild(a);
  a.click();
  a.remove();
  showToast("Descargando el código QR…");
});

// Estado inicial.
setActionsEnabled(false);
update();
