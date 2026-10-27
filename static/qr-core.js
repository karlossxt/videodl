/* Núcleo puro del generador de QR: construye el contenido y valida el estilo.
   Se puede requerir desde Node (`tests/qr-core.test.js`) sin DOM. */
(function (global) {
  "use strict";

  const MAX_PAYLOAD_BYTES = 1200;
  const MIN_CONTRAST = 3;
  const TYPES = ["text", "wifi", "email", "phone", "sms"];

  /** Usa window.t cuando common.js está cargado; en Node mantiene el texto base. */
  function translate(key, fallback, values) {
    const t = typeof global.t === "function" ? global.t : null;
    return t ? t(key, fallback, values) : fallback;
  }

  function escapeWifi(value) {
    // El formato WIFI: usa \ para escapar ; , : " y la propia barra.
    return String(value == null ? "" : value).replace(/([\\;,:"])/g, "\\$1");
  }

  function normalizePhone(value) {
    const raw = String(value == null ? "" : value).trim();
    const digits = raw.replace(/\D/g, "");
    if (!digits) return "";
    return (raw.startsWith("+") ? "+" : "") + digits;
  }

  function buildPayload(type, values) {
    const data = values || {};
    switch (type) {
      case "text": {
        return String(data.text || "").trim();
      }
      case "wifi": {
        const ssid = String(data.ssid || "").trim();
        if (!ssid) return "";
        const encryption = ["WPA", "WEP", "nopass"].includes(data.encryption)
          ? data.encryption
          : "WPA";
        let payload = `WIFI:T:${encryption};S:${escapeWifi(ssid)};`;
        if (encryption !== "nopass") {
          payload += `P:${escapeWifi(data.password || "")};`;
        }
        if (data.hidden) payload += "H:true;";
        return `${payload};`;
      }
      case "email": {
        const to = String(data.email || "").trim();
        if (!to) return "";
        const params = [];
        if (String(data.subject || "").trim()) {
          params.push(`subject=${encodeURIComponent(String(data.subject).trim())}`);
        }
        if (String(data.body || "").trim()) {
          params.push(`body=${encodeURIComponent(String(data.body).trim())}`);
        }
        return `mailto:${to}${params.length ? `?${params.join("&")}` : ""}`;
      }
      case "phone": {
        const phone = normalizePhone(data.phone);
        return phone ? `tel:${phone}` : "";
      }
      case "sms": {
        const phone = normalizePhone(data.phone);
        if (!phone) return "";
        const message = String(data.message || "").trim();
        return `SMSTO:${phone}:${message}`;
      }
      default:
        return "";
    }
  }

  function byteLength(text) {
    return new TextEncoder().encode(String(text || "")).length;
  }

  function validatePayload(type, payload) {
    if (!TYPES.includes(type)) {
      return {
        ok: false,
        message: translate("qr.coreInvalidType", "Tipo de QR no válido."),
      };
    }
    if (!payload) {
      return {
        ok: false,
        message: translate(
          "qr.coreEmpty",
          "Escribe el contenido que quieres convertir en QR."
        ),
      };
    }
    if (byteLength(payload) > MAX_PAYLOAD_BYTES) {
      return {
        ok: false,
        message: translate(
          "qr.coreTooLarge",
          `El contenido ocupa demasiado (${byteLength(payload)} bytes). El máximo es ${MAX_PAYLOAD_BYTES}.`,
          { bytes: byteLength(payload), max: MAX_PAYLOAD_BYTES }
        ),
      };
    }
    if (type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(payload).slice(7).split("?")[0])) {
      return {
        ok: false,
        message: translate(
          "qr.coreInvalidEmail",
          "El correo electrónico no parece válido."
        ),
      };
    }
    if ((type === "phone" || type === "sms") && normalizePhone(payload.replace(/^(tel:|SMSTO:)/, "").split(":")[0]).replace(/\D/g, "").length < 6) {
      return {
        ok: false,
        message: translate(
          "qr.coreInvalidPhone",
          "El número de teléfono no parece válido."
        ),
      };
    }
    return { ok: true, message: "" };
  }

  function channelLuminance(value) {
    const channel = value / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  }

  function relativeLuminance(hex) {
    if (!/^#[0-9a-fA-F]{6}$/.test(String(hex))) return NaN;
    const red = parseInt(hex.slice(1, 3), 16);
    const green = parseInt(hex.slice(3, 5), 16);
    const blue = parseInt(hex.slice(5, 7), 16);
    return (
      0.2126 * channelLuminance(red) +
      0.7152 * channelLuminance(green) +
      0.0722 * channelLuminance(blue)
    );
  }

  function contrastRatio(first, second) {
    const values = [relativeLuminance(first), relativeLuminance(second)];
    if (values.some(Number.isNaN)) return NaN;
    const [high, low] = values.sort((a, b) => b - a);
    return (high + 0.05) / (low + 0.05);
  }

  function styleProblem(dark, light) {
    const ratio = contrastRatio(dark, light);
    if (Number.isNaN(ratio)) {
      return translate(
        "qr.coreColorFormat",
        "Los colores deben tener el formato #rrggbb."
      );
    }
    if (relativeLuminance(dark) >= relativeLuminance(light)) {
      return translate(
        "qr.coreDarkModules",
        "Los módulos del QR deben ser más oscuros que el fondo."
      );
    }
    if (ratio < MIN_CONTRAST) {
      return translate(
        "qr.coreLowContrast",
        "El contraste es demasiado bajo. Usa colores más distintos para que se pueda escanear."
      );
    }
    return "";
  }

  const api = {
    MAX_PAYLOAD_BYTES,
    MIN_CONTRAST,
    TYPES,
    escapeWifi,
    normalizePhone,
    buildPayload,
    byteLength,
    validatePayload,
    relativeLuminance,
    contrastRatio,
    styleProblem,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  global.QRCore = api;
})(typeof window !== "undefined" ? window : globalThis);
