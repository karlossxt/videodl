/* Tema claro/oscuro y navegación móvil compartida por todas las páginas.
   Se carga en <head> para aplicar el tema guardado antes del primer pintado. */
(function () {
  "use strict";

  const root = document.documentElement;
  // Marca que el JS está disponible. Sin esta clase, el menú móvil se muestra
  // desplegado y los controles que dependen de JS quedan ocultos.
  root.classList.add("js");
  const STORAGE_KEY = "videodl-theme";

  function storedTheme() {
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch (_) {
      return null;
    }
  }

  function applyTheme(theme) {
    root.dataset.theme = theme;
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (_) {
      /* Sin almacenamiento: el tema sigue funcionando durante esta visita. */
    }

    const isLight = theme === "light";
    const themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) {
      themeColor.setAttribute("content", isLight ? "#f4f7fb" : "#080c14");
    }

    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(isLight));
      button.setAttribute(
        "aria-label",
        isLight ? "Cambiar a modo oscuro" : "Cambiar a modo claro"
      );
      const icon = button.querySelector("[data-theme-icon]");
      if (icon) icon.textContent = isLight ? "☾" : "☀";
      const text = button.querySelector("[data-theme-text]");
      if (text) text.textContent = isLight ? "Modo oscuro" : "Modo claro";
    });
  }

  function initTheme() {
    const initial = root.dataset.theme === "light" ? "light" : "dark";
    applyTheme(initial);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.addEventListener("click", function () {
        applyTheme(root.dataset.theme === "light" ? "dark" : "light");
      });
    });
  }

  function initNav() {
    const toggle = document.querySelector("[data-nav-toggle]");
    const menu = document.getElementById("site-menu");
    if (!toggle || !menu) return;

    function setOpen(open) {
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute(
        "aria-label",
        open ? "Cerrar menú de navegación" : "Abrir menú de navegación"
      );
      menu.classList.toggle("is-open", open);
    }

    toggle.addEventListener("click", function () {
      setOpen(toggle.getAttribute("aria-expanded") !== "true");
    });

    menu.addEventListener("click", function (event) {
      if (event.target.closest("a")) setOpen(false);
    });

    document.addEventListener("keydown", function (event) {
      if (
        event.key === "Escape" &&
        toggle.getAttribute("aria-expanded") === "true"
      ) {
        setOpen(false);
        toggle.focus();
      }
    });

    window.addEventListener("resize", function () {
      if (window.innerWidth > 760) setOpen(false);
    });
  }

  const saved = storedTheme();
  if (saved) root.dataset.theme = saved;

  function init() {
    initTheme();
    initNav();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
