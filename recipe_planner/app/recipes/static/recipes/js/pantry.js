document.addEventListener("DOMContentLoaded", () => {
  const filter = document.getElementById("pantry-filter");
  const count = document.getElementById("pantry-count");
  const emptyFilter = document.getElementById("pantry-empty-filter");
  const rows = Array.from(document.querySelectorAll("[data-pantry-row]"));

  if (!filter || !count || rows.length === 0) {
    return;
  }

  function updatePantryFilter() {
    const term = filter.value.trim().toLowerCase();
    let shown = 0;
    rows.forEach((row) => {
      const matches = row.dataset.filterText.toLowerCase().includes(term);
      row.hidden = !matches;
      if (matches) {
        shown += 1;
      }
    });
    count.textContent = `${shown} ${shown === 1 ? "item" : "items"}`;
    emptyFilter.classList.toggle("hidden", shown !== 0 || term === "");
  }

  filter.addEventListener("input", updatePantryFilter);
});
