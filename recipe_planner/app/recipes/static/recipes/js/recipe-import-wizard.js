document.addEventListener("DOMContentLoaded", () => {
  const panels = document.querySelectorAll("[data-wizard-panel]");
  const indicators = document.querySelectorAll("[data-step-indicator]");
  const connectors = document.querySelectorAll("[data-step-connector]");
  const totalSteps = panels.length;
  let currentStep = 1;

  function showStep(step) {
    panels.forEach(p => p.classList.toggle("active", parseInt(p.dataset.wizardPanel) === step));
    indicators.forEach(i => {
      const num = parseInt(i.dataset.stepIndicator);
      i.classList.toggle("active", num === step);
      i.classList.toggle("completed", num < step || num === step);
    });
    connectors.forEach(c => {
      c.classList.toggle("done", parseInt(c.dataset.stepConnector) < step);
    });
    document.getElementById("wizard-steps").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function validateStep(step) {
    const panel = document.querySelector(`[data-wizard-panel="${step}"]`);
    if (!panel) return true;
    if (step === 1) {
      const title = panel.querySelector("[name='title']");
      if (title && !title.value.trim()) {
        title.focus();
        title.reportValidity();
        return false;
      }
    }
    if (step === 2) {
      const ingredientRows = panel.querySelectorAll("[data-ingredient-rows] .ingredient-row:not(.header)");
      if (ingredientRows.length === 0) {
        alert("Add at least one ingredient.");
        return false;
      }
      let hasValid = false;
      ingredientRows.forEach(row => {
        const name = row.querySelector("[name='ingredient_name']");
        if (name && name.value.trim()) hasValid = true;
      });
      if (!hasValid) {
        alert("Add at least one ingredient with a name.");
        return false;
      }
    }
    if (step === 3) {
      const stepRows = panel.querySelectorAll("[data-step-rows] .step-row:not(.header)");
      if (stepRows.length === 0) {
        alert("Add at least one instruction step.");
        return false;
      }
      let hasValid = false;
      stepRows.forEach(row => {
        const text = row.querySelector("[name='step_text']");
        if (text && text.value.trim()) hasValid = true;
      });
      if (!hasValid) {
        alert("Add at least one step with a description.");
        return false;
      }
    }
    return true;
  }

  function buildSummary() {
    const title = document.querySelector("[name='title']").value;
    const servings = document.querySelector("[name='servings']").value;
    const prep = document.querySelector("[name='prep_minutes']").value;
    const cook = document.querySelector("[name='cook_minutes']").value;
    const tags = document.querySelector("[name='tags_text']").value;

    document.querySelector("[data-summary-title]").textContent = title;
    document.querySelector("[data-summary-servings]").textContent = servings || "—";
    document.querySelector("[data-summary-prep]").textContent = prep ? prep + " min" : "—";
    document.querySelector("[data-summary-cook]").textContent = cook ? cook + " min" : "—";
    document.querySelector("[data-summary-tags]").textContent = tags || "None";

    const ingredientRows = document.querySelectorAll("[data-ingredient-rows] .ingredient-row:not(.header)");
    const ingredientList = document.querySelector("[data-summary-ingredients]");
    ingredientList.innerHTML = "";
    let ingCount = 0;
    ingredientRows.forEach(row => {
      const name = row.querySelector("[name='ingredient_name']").value;
      if (!name.trim()) return;
      ingCount++;
      const qty = row.querySelector("[name='ingredient_quantity']").value;
      const unit = row.querySelector("[name='ingredient_unit']").value;
      const note = row.querySelector("[name='ingredient_note']").value;
      const group = row.querySelector("[name='ingredient_group']").value;
      let text = qty + " " + unit + " " + name;
      if (note) text += " (" + note + ")";
      if (group) text += " [" + group + "]";
      const li = document.createElement("li");
      li.textContent = text;
      ingredientList.appendChild(li);
    });
    document.querySelector("[data-summary-ingredient-count]").textContent = ingCount;

    const stepRows = document.querySelectorAll("[data-step-rows] .step-row:not(.header)");
    const stepList = document.querySelector("[data-summary-steps]");
    stepList.innerHTML = "";
    let stepCount = 0;
    stepRows.forEach(row => {
      const text = row.querySelector("[name='step_text']").value;
      if (!text.trim()) return;
      stepCount++;
      const dur = row.querySelector("[name='step_duration']").value;
      let stepText = text;
      if (dur) stepText += " (" + dur + " min)";
      const li = document.createElement("li");
      li.textContent = stepText;
      stepList.appendChild(li);
    });
    document.querySelector("[data-summary-step-count]").textContent = stepCount;
  }

  document.querySelectorAll("[data-wizard-next]").forEach(btn => {
    btn.addEventListener("click", () => {
      const panel = btn.closest("[data-wizard-panel]");
      if (!panel) return;
      const step = parseInt(panel.dataset.wizardPanel);
      if (!validateStep(step)) return;
      currentStep = step + 1;
      if (currentStep === totalSteps) {
        buildSummary();
      }
      showStep(currentStep);
    });
  });

  document.querySelectorAll("[data-wizard-prev]").forEach(btn => {
    btn.addEventListener("click", () => {
      const panel = btn.closest("[data-wizard-panel]");
      if (!panel) return;
      const step = parseInt(panel.dataset.wizardPanel);
      currentStep = step - 1;
      showStep(currentStep);
    });
  });

  indicators.forEach(indicator => {
    indicator.addEventListener("click", () => {
      if (!indicator.classList.contains("completed")) return;
      const step = parseInt(indicator.dataset.stepIndicator);
      currentStep = step;
      showStep(currentStep);
    });
  });

  // Ingredient row add/remove/reorder
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

  // Step row add/remove/reorder
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

  showStep(1);
});
