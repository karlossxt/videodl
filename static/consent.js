/* Aviso de consentimiento publicitario.
   Sin decisión guardada se muestra un banner; la librería de Adcash solo se
   inyecta si la persona acepta. La decisión vive en el almacenamiento local
   (clave "ads-consent") y se puede retirar con el botón de la política de
   privacidad, que lleva el atributo data-consent-reset. */
(function () {
  "use strict";

  var KEY = "ads-consent";
  var config = window.__aclib || null;

  function tr(key, fallback) {
    var root = window.I18N_STRINGS || {};
    var value = key.split(".").reduce(function (current, part) {
      return current && typeof current === "object" ? current[part] : undefined;
    }, root);
    return typeof value === "string" && value ? value : fallback;
  }

  function stored() {
    try {
      return localStorage.getItem(KEY);
    } catch (_) {
      return null;
    }
  }

  function store(value) {
    try {
      localStorage.setItem(KEY, value);
    } catch (_) {
      /* Sin almacenamiento: la decisión vale solo para esta página. */
    }
  }

  function loadAds() {
    if (!config || !config.zoneId) return;
    if (document.getElementById("aclib")) return;

    var script = document.createElement("script");
    script.id = "aclib";
    script.type = "text/javascript";
    script.src = "//acscdn.com/script/aclib.js";
    script.async = false;
    script.addEventListener("load", function () {
      if (window.aclib && typeof window.aclib[config.call] === "function") {
        window.aclib[config.call]({ zoneId: config.zoneId });
      }
    });
    document.head.appendChild(script);
  }

  function decide(value, banner) {
    store(value);
    if (banner && banner.parentNode) banner.parentNode.removeChild(banner);
    if (value === "granted") loadAds();
  }

  function button(label, value, banner) {
    var element = document.createElement("button");
    element.type = "button";
    element.className = "consent-btn";
    element.textContent = label;
    element.addEventListener("click", function () {
      decide(value, banner);
    });
    return element;
  }

  function showBanner() {
    var banner = document.createElement("div");
    banner.className = "consent-banner";
    banner.setAttribute("role", "dialog");
    banner.setAttribute("aria-live", "polite");
    banner.setAttribute("aria-label", tr("js.consent.label", "Consentimiento de cookies"));

    var text = document.createElement("p");
    text.textContent = tr(
      "js.consent.message",
      "Usamos cookies de nuestros socios publicitarios para mostrar anuncios. " +
        "Puedes aceptar o rechazar; el sitio funciona igual."
    );

    var link = document.createElement("a");
    link.href = "/privacidad";
    link.textContent = tr("js.consent.more", "Más información");
    text.appendChild(document.createTextNode(" "));
    text.appendChild(link);

    var actions = document.createElement("div");
    actions.className = "consent-actions";
    actions.appendChild(
      button(tr("js.consent.reject", "Rechazar"), "denied", banner)
    );
    actions.appendChild(
      button(tr("js.consent.accept", "Aceptar"), "granted", banner)
    );

    banner.appendChild(text);
    banner.appendChild(actions);
    document.body.appendChild(banner);
  }

  function initReset() {
    var buttons = document.querySelectorAll("[data-consent-reset]");
    Array.prototype.forEach.call(buttons, function (element) {
      element.addEventListener("click", function () {
        try {
          localStorage.removeItem(KEY);
        } catch (_) {
          /* Nada que borrar. */
        }
        window.location.reload();
      });
    });
  }

  function init() {
    initReset();
    if (!config) return;
    var decision = stored();
    if (decision === "granted") {
      loadAds();
    } else if (decision !== "denied") {
      showBanner();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
