document.addEventListener("DOMContentLoaded", () => {
  const rows = document.querySelector("[data-aisle-rows]");
  const template = document.querySelector("#aisle-template");

  document.querySelector("[data-add-row]").addEventListener("click", () => {
    const clone = template.content.cloneNode(true);
    rows.appendChild(clone);
  });

  rows.addEventListener("click", (event) => {
    const removeBtn = event.target.closest("[data-remove-row]");
    const moveUpBtn = event.target.closest("[data-move-up]");
    const moveDownBtn = event.target.closest("[data-move-down]");

    if (removeBtn) {
      const row = removeBtn.closest(".aisle-row");
      row.remove();
    } else if (moveUpBtn) {
      const row = moveUpBtn.closest(".aisle-row");
      const prev = row.previousElementSibling;
      if (prev) {
        rows.insertBefore(row, prev);
      }
    } else if (moveDownBtn) {
      const row = moveDownBtn.closest(".aisle-row");
      const next = row.nextElementSibling;
      if (next) {
        rows.insertBefore(next, row);
      }
    }
  });
});
