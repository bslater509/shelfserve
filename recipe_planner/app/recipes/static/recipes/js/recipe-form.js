document.addEventListener("DOMContentLoaded", () => {
  // 1. Ingredients handling
  const ingredientRows = document.querySelector("[data-ingredient-rows]");
  const ingredientTemplate = document.querySelector("#ingredient-template");
  
  document.querySelector("[data-add-row]").addEventListener("click", () => {
    ingredientRows.appendChild(ingredientTemplate.content.cloneNode(true));
  });
  
  ingredientRows.addEventListener("click", (event) => {
    const btn = event.target.closest("button");
    if (!btn) return;
    
    const row = btn.closest(".ingredient-row");
    if (!row || row.classList.contains("header")) return;
    
    if (btn.matches("[data-remove-row]")) {
      if (ingredientRows.querySelectorAll(".ingredient-row:not(.header)").length > 1) {
        row.remove();
      }
    } else if (btn.matches("[data-move-up]")) {
      const prev = row.previousElementSibling;
      if (prev && !prev.classList.contains("header")) {
        ingredientRows.insertBefore(row, prev);
      }
    } else if (btn.matches("[data-move-down]")) {
      const next = row.nextElementSibling;
      if (next) {
        ingredientRows.insertBefore(next, row);
      }
    }
  });

  // 2. Steps handling
  const stepRows = document.querySelector("[data-step-rows]");
  const stepTemplate = document.querySelector("#step-template");
  
  document.querySelector("[data-add-step]").addEventListener("click", () => {
    stepRows.appendChild(stepTemplate.content.cloneNode(true));
  });
  
  stepRows.addEventListener("click", (event) => {
    const btn = event.target.closest("button");
    if (!btn) return;
    
    const row = btn.closest(".step-row");
    if (!row || row.classList.contains("header")) return;
    
    if (btn.matches("[data-remove-step]")) {
      if (stepRows.querySelectorAll(".step-row:not(.header)").length > 1) {
        row.remove();
      }
    } else if (btn.matches("[data-move-up]")) {
      const prev = row.previousElementSibling;
      if (prev && !prev.classList.contains("header")) {
        stepRows.insertBefore(row, prev);
      }
    } else if (btn.matches("[data-move-down]")) {
      const next = row.nextElementSibling;
      if (next) {
        stepRows.insertBefore(next, row);
      }
    }
  });
});
