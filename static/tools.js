/* Búsqueda y filtros instantáneos del catálogo de herramientas. */
(function () {
  "use strict";

  const input = document.querySelector("[data-tool-search]");
  const grid = document.querySelector("[data-tools-grid]");
  if (!input || !grid) return;

  const cards = Array.from(grid.querySelectorAll("[data-tool-card]"));
  const chips = Array.from(document.querySelectorAll("[data-category]"));
  const count = document.querySelector("[data-tools-count]");
  const empty = document.querySelector("[data-tools-empty]");
  const categoryInput = document.querySelector("[data-category-input]");
  const activeChip = chips.find((chip) => chip.classList.contains("is-active"));
  let category = activeChip ? activeChip.dataset.category : "all";

  function normalize(value) {
    return String(value)
      .toLocaleLowerCase("es")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  function setActiveChip() {
    chips.forEach(function (chip) {
      const isActive = chip.dataset.category === category;
      chip.classList.toggle("is-active", isActive);
      if (isActive) {
        chip.setAttribute("aria-current", "true");
      } else {
        chip.removeAttribute("aria-current");
      }
    });
    if (categoryInput) categoryInput.value = category;
  }

  function apply() {
    const query = normalize(input.value.trim());
    let visible = 0;

    cards.forEach(function (card) {
      const inCategory =
        category === "all" || card.dataset.category === category;
      const inSearch =
        !query || normalize(card.dataset.search || "").includes(query);
      const show = inCategory && inSearch;
      card.hidden = !show;
      if (show) visible += 1;
    });

    if (count) {
      count.textContent =
        visible === 1 ? "1 herramienta" : visible + " herramientas";
    }
    if (empty) empty.hidden = visible !== 0;
    setActiveChip();
  }

  input.addEventListener("input", apply);
  input.addEventListener("search", apply);

  chips.forEach(function (chip) {
    chip.addEventListener("click", function (event) {
      // Con modificadores o botón secundario, el enlace funciona normalmente.
      if (
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey ||
        event.button !== 0
      ) {
        return;
      }
      event.preventDefault();
      category = chip.dataset.category;
      apply();

      const section = grid.closest(".tools-section");
      if (section) {
        const reduced = window.matchMedia(
          "(prefers-reduced-motion: reduce)"
        ).matches;
        section.scrollIntoView({
          behavior: reduced ? "auto" : "smooth",
          block: "start",
        });
      }
    });
  });

  apply();
})();
