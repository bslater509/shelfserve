document.addEventListener('DOMContentLoaded', () => {
const modal = document.getElementById('recipe-selector-modal');
const modalClose = modal.querySelector('.modal-close-btn');
const modalBackdrop = modal.querySelector('.modal-backdrop');
const searchInput = document.getElementById('modal-search-field');
const modalCards = modal.querySelectorAll('.modal-recipe-card');
const noResults = document.getElementById('modal-no-results-msg');
const slotIndicator = document.getElementById('modal-slot-indicator');

let activeCell = null;

// Modal Open Trigger
document.querySelectorAll('.add-meal-trigger').forEach(btn => {
  btn.addEventListener('click', (e) => {
    activeCell = e.currentTarget.closest('.meal-cell-container');
    openModal();
  });
});

// Also open modal on clicking the recipe details inside occupied cells
document.querySelectorAll('.meal-card-thumb-container, .meal-card-title').forEach(el => {
  el.addEventListener('click', (e) => {
    activeCell = e.currentTarget.closest('.meal-cell-container');
    openModal();
  });
});

function openModal() {
  if (!activeCell) return;
  const day = activeCell.dataset.day;
  const slotLabel = activeCell.dataset.slotLabel;
  
  // Parse date for visual preview
  const parsedDate = new Date(day);
  const options = { weekday: 'long', day: 'numeric', month: 'short' };
  const dateStr = parsedDate.toLocaleDateString('en-GB', options);
  
  slotIndicator.textContent = `${slotLabel} \u2022 ${dateStr}`;
  
  modal.style.display = 'block';
  document.body.style.overflow = 'hidden';
  searchInput.value = '';
  filterRecipes('');
  setTimeout(() => {
    modal.classList.add('is-open');
    searchInput.focus();
  }, 10);
}

function closeModal() {
  modal.classList.remove('is-open');
  document.body.style.overflow = '';
  setTimeout(() => {
    modal.style.display = 'none';
    activeCell = null;
  }, 250);
}

modalClose.addEventListener('click', closeModal);
modalBackdrop.addEventListener('click', closeModal);

// Close on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && modal.style.display === 'block') {
    closeModal();
  }
});

// Modal recipe live search
searchInput.addEventListener('input', (e) => {
  filterRecipes(e.target.value);
});

function filterRecipes(query) {
  const cleanQuery = query.trim().toLowerCase();
  let visibleCount = 0;

  modalCards.forEach(card => {
    const title = card.dataset.title.toLowerCase();
    const tags = card.dataset.tags.toLowerCase();

    if (title.includes(cleanQuery) || tags.includes(cleanQuery)) {
      card.style.display = '';
      visibleCount++;
    } else {
      card.style.display = 'none';
    }
  });

  noResults.style.display = visibleCount === 0 ? 'flex' : 'none';
}

// Handle Recipe Selection
modalCards.forEach(card => {
  card.addEventListener('click', () => {
    if (!activeCell) return;
    
    const recipeId = card.dataset.id;
    const title = card.dataset.title;
    const servings = card.dataset.servings || '4';
    const imageUrl = card.dataset.image;

    // Update hidden inputs
    activeCell.querySelector('.recipe-id-input').value = recipeId;
    activeCell.querySelector('.recipe-servings-input').value = servings;
    activeCell.querySelector('.recipe-note-input').value = '';

    // Update UI components
    const filledState = activeCell.querySelector('.meal-state-filled');
    const emptyState = activeCell.querySelector('.meal-state-empty');

    // Update title
    filledState.querySelector('.meal-card-title').textContent = title;
    filledState.querySelector('.servings-count-display').textContent = servings;
    filledState.querySelector('.meal-note-field').value = '';

    // Update image
    const thumbContainer = filledState.querySelector('.meal-card-thumb-container');
    thumbContainer.innerHTML = '';
    if (imageUrl) {
      const img = document.createElement('img');
      img.src = imageUrl;
      img.className = 'meal-card-thumb';
      img.alt = '';
      thumbContainer.appendChild(img);
    } else {
      const placeholder = document.createElement('div');
      placeholder.className = 'meal-card-thumb-placeholder';
      placeholder.textContent = title.charAt(0);
      thumbContainer.appendChild(placeholder);
    }

    // Add click handlers on newly populated elements so user can click to change
    filledState.querySelector('.meal-card-thumb-container').onclick = (e) => {
      activeCell = e.currentTarget.closest('.meal-cell-container');
      openModal();
    };
    filledState.querySelector('.meal-card-title').onclick = (e) => {
      activeCell = e.currentTarget.closest('.meal-cell-container');
      openModal();
    };

    // Toggle views
    emptyState.style.display = 'none';
    filledState.style.display = 'block';

    closeModal();
  });
});

// Handle servings changes
document.querySelectorAll('.meal-cell-container').forEach(cell => {
  const servingsInput = cell.querySelector('.recipe-servings-input');
  const servingsDisplay = cell.querySelector('.servings-count-display');

  cell.querySelector('.btn-inc-servings').addEventListener('click', (e) => {
    e.stopPropagation();
    let val = parseInt(servingsInput.value) || 1;
    val++;
    servingsInput.value = val;
    servingsDisplay.textContent = val;
  });

  cell.querySelector('.btn-dec-servings').addEventListener('click', (e) => {
    e.stopPropagation();
    let val = parseInt(servingsInput.value) || 1;
    if (val > 1) {
      val--;
      servingsInput.value = val;
      servingsDisplay.textContent = val;
    }
  });

  // Handle Remove Action
  cell.querySelector('.btn-remove-meal-action').addEventListener('click', (e) => {
    e.stopPropagation();
    clearCell(cell);
  });

  const noteField = cell.querySelector('.meal-note-field');
  const noteInput = cell.querySelector('.recipe-note-input');
  noteField.addEventListener('input', () => {
    noteInput.value = noteField.value;
  });
});

function clearCell(cell) {
  cell.querySelector('.recipe-id-input').value = '';
  cell.querySelector('.recipe-servings-input').value = '1';
  cell.querySelector('.recipe-note-input').value = '';
  cell.querySelector('.meal-note-field').value = '';
  cell.querySelector('.meal-state-filled').style.display = 'none';
  cell.querySelector('.meal-state-empty').style.display = 'block';
}

// Clear Day Action
document.querySelectorAll('.btn-clear-day').forEach(btn => {
  btn.addEventListener('click', (e) => {
    const row = e.currentTarget.closest('.planner-day-row');
    row.querySelectorAll('.meal-cell-container').forEach(cell => {
      clearCell(cell);
    });
  });
});

// Clear Week Action
const btnClearWeek = document.getElementById('btn-clear-week');
if (btnClearWeek) {
  btnClearWeek.addEventListener('click', () => {
    if (confirm('Are you sure you want to clear all recipes planned for this week?')) {
      document.querySelectorAll('.meal-cell-container').forEach(cell => {
        clearCell(cell);
      });
    }
  });
}

// Random Auto-fill Action
const btnRandomFill = document.getElementById('btn-random-fill');
if (btnRandomFill) {
  btnRandomFill.addEventListener('click', () => {
    const emptyCells = Array.from(document.querySelectorAll('.meal-cell-container')).filter(cell => {
      return !cell.querySelector('.recipe-id-input').value;
    });

    if (emptyCells.length === 0) {
      alert('All slots are already filled!');
      return;
    }

    if (modalCards.length === 0) {
      alert('You do not have any recipes in your database to fill slots with. Create some first!');
      return;
    }

    emptyCells.forEach(cell => {
      // Pick a random recipe card from the modal cards
      const randIndex = Math.floor(Math.random() * modalCards.length);
      const card = modalCards[randIndex];
      
      const recipeId = card.dataset.id;
      const title = card.dataset.title;
      const servings = card.dataset.servings || '4';
      const imageUrl = card.dataset.image;

      // Apply to cell
      cell.querySelector('.recipe-id-input').value = recipeId;
      cell.querySelector('.recipe-servings-input').value = servings;
      cell.querySelector('.recipe-note-input').value = '';

      const filledState = cell.querySelector('.meal-state-filled');
      const emptyState = cell.querySelector('.meal-state-empty');

      filledState.querySelector('.meal-card-title').textContent = title;
      filledState.querySelector('.servings-count-display').textContent = servings;
      filledState.querySelector('.meal-note-field').value = '';

      const thumbContainer = filledState.querySelector('.meal-card-thumb-container');
      thumbContainer.innerHTML = '';
      if (imageUrl) {
        const img = document.createElement('img');
        img.src = imageUrl;
        img.className = 'meal-card-thumb';
        img.alt = '';
        thumbContainer.appendChild(img);
      } else {
        const placeholder = document.createElement('div');
        placeholder.className = 'meal-card-thumb-placeholder';
        placeholder.textContent = title.charAt(0);
        thumbContainer.appendChild(placeholder);
      }

      // Click to modify handlers
      filledState.querySelector('.meal-card-thumb-container').onclick = (e) => {
        activeCell = e.currentTarget.closest('.meal-cell-container');
        openModal();
      };
      filledState.querySelector('.meal-card-title').onclick = (e) => {
        activeCell = e.currentTarget.closest('.meal-cell-container');
        openModal();
      };

      emptyState.style.display = 'none';
      filledState.style.display = 'block';
    });
  });
}
});
