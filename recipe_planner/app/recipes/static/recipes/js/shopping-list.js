document.addEventListener("DOMContentLoaded", () => {
  const listContainer = document.body;
  const toast = document.getElementById("ajax-toast");
  const hideCheckedToggle = document.getElementById("hide-checked-toggle");
  const shoppingFilter = document.getElementById("shopping-filter");
  const progressFill = document.getElementById("shopping-progress-fill");
  const emptyFilter = document.getElementById("shopping-empty-filter");
  const listMeta = document.querySelector("[data-shopping-list-id]");
    const storageKey = `shelfserve-hide-checked-${listMeta.dataset.shoppingListId}`;
  let toastTimeout;

  function showToast(message) {
    toast.textContent = message || "Failed to update item status. Please try again.";
    toast.style.display = "block";
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
      toast.style.display = "none";
    }, 4500);
  }

  function applyCheckedVisibility() {
    const shouldHide = hideCheckedToggle && hideCheckedToggle.checked;
    const term = shoppingFilter ? shoppingFilter.value.trim().toLowerCase() : "";
    let visibleRows = 0;

    document.querySelectorAll("[data-shopping-row]").forEach((item) => {
      const matchesText = item.dataset.filterText.toLowerCase().includes(term);
      const hiddenByChecked = shouldHide && item.classList.contains("checked");
      const shouldShow = matchesText && !hiddenByChecked;
      item.hidden = !shouldShow;
      if (shouldShow) {
        visibleRows += 1;
      }
    });

    document.querySelectorAll("[data-shopping-section]").forEach((section) => {
      const hasVisibleRows = Boolean(section.querySelector("[data-shopping-row]:not([hidden])"));
      section.hidden = !hasVisibleRows;
    });

    if (emptyFilter) {
      emptyFilter.classList.toggle("hidden", visibleRows !== 0 || (!term && !shouldHide));
    }
  }

  function updateProgress() {
    const rows = Array.from(document.querySelectorAll("[data-shopping-row]"));
    const checked = rows.filter((row) => row.classList.contains("checked")).length;
    const total = rows.length;
    const percent = total ? Math.round((checked / total) * 100) : 0;

    document.querySelectorAll("[data-checked-count]").forEach((element) => {
      element.textContent = checked;
    });
    document.querySelectorAll("[data-total-count]").forEach((element) => {
      element.textContent = total;
    });
    if (progressFill) {
      progressFill.style.width = `${percent}%`;
    }
  }

  if (hideCheckedToggle) {
    hideCheckedToggle.checked = localStorage.getItem(storageKey) === "1";
    hideCheckedToggle.addEventListener("change", () => {
      localStorage.setItem(storageKey, hideCheckedToggle.checked ? "1" : "0");
      applyCheckedVisibility();
    });
  }

  if (shoppingFilter) {
    shoppingFilter.addEventListener("input", applyCheckedVisibility);
  }

  listContainer.addEventListener("submit", (event) => {
    const form = event.target;
    if (!form.action || !form.action.includes("/toggle/")) {
      return;
    }

    event.preventDefault();

    const button = form.querySelector(".check-button");
    const li = form.closest("li");
    const isChecked = li.classList.contains("checked");

    li.classList.toggle("checked");
    button.innerHTML = isChecked ? "" : "&#10003;";
    updateProgress();
    applyCheckedVisibility();

    const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;
    fetch(form.action, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json"
      }
    })
    .then(response => {
      if (!response.ok) {
        throw new Error("HTTP error " + response.status);
      }
      return response.json();
    })
    .then(data => {
      if (data.checked) {
        li.classList.add("checked");
        button.innerHTML = "&#10003;";
      } else {
        li.classList.remove("checked");
        button.innerHTML = "";
      }
      updateProgress();
      applyCheckedVisibility();
    })
    .catch(error => {
      console.error("AJAX toggle failed:", error);
      showToast("Network error: failed to update item status.");
      if (isChecked) {
        li.classList.add("checked");
        button.innerHTML = "&#10003;";
      } else {
        li.classList.remove("checked");
        button.innerHTML = "";
      }
      updateProgress();
      applyCheckedVisibility();
    });
  });

  updateProgress();
  applyCheckedVisibility();
});
