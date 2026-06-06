document.addEventListener("DOMContentLoaded", () => {
  // ----------------------------------------------------
  // Servings Stepper Scaling Logic
  // ----------------------------------------------------
  const displayServings = document.getElementById("display-servings");
  const chkDecimalToggle = document.getElementById("chk-decimal-toggle");
  const btnServingsDec = document.getElementById("btn-servings-dec");
  const btnServingsInc = document.getElementById("btn-servings-inc");

  let currentServings = parseFloat(displayServings.dataset.current);
  const originalServings = parseFloat(displayServings.dataset.original);

  function updateServings(newVal) {
    if (newVal < 0.5) newVal = 0.5; // Avoid negative/zero servings
    currentServings = newVal;
    displayServings.textContent = formatQuantity(currentServings);
    displayServings.dataset.current = currentServings;
    
    // Scale ingredients
    scaleAllIngredients(currentServings, originalServings);
  }

  function scaleAllIngredients(current, original) {
    const ratio = current / original;
    
    // Scale main page ingredients
    document.querySelectorAll(".ingredient-row-item").forEach(item => {
      const qtySpan = item.querySelector(".ingredient-qty-display");
      if (qtySpan) {
        const originalQty = parseFloat(qtySpan.dataset.qty);
        if (!isNaN(originalQty)) {
          qtySpan.textContent = formatQuantity(originalQty * ratio);
        }
      }
    });

    // Scale Cook Mode ingredients
    document.querySelectorAll(".cook-mode-ingredient-item").forEach(item => {
      const qtySpan = item.querySelector(".cook-mode-ing-qty");
      if (qtySpan) {
        const originalQty = parseFloat(qtySpan.dataset.qty);
        if (!isNaN(originalQty)) {
          qtySpan.textContent = formatQuantity(originalQty * ratio);
        }
      }
    });
  }

  function formatQuantity(val) {
    let num = parseFloat(val);
    if (isNaN(num)) return val;
    if (num % 1 === 0) {
      return num.toFixed(0);
    }
    return parseFloat(num.toFixed(2)).toString();
  }

  btnServingsDec.addEventListener("click", () => {
    const step = chkDecimalToggle.checked ? 0.5 : 1.0;
    let nextVal = currentServings - step;
    // Snap to step
    if (!chkDecimalToggle.checked) {
      nextVal = Math.floor(nextVal);
    } else {
      nextVal = Math.floor(nextVal * 2) / 2;
    }
    updateServings(Math.max(0.5, nextVal));
  });

  btnServingsInc.addEventListener("click", () => {
    const step = chkDecimalToggle.checked ? 0.5 : 1.0;
    let nextVal = currentServings + step;
    // Snap to step
    if (!chkDecimalToggle.checked) {
      nextVal = Math.ceil(nextVal);
    } else {
      nextVal = Math.ceil(nextVal * 2) / 2;
    }
    updateServings(nextVal);
  });

  chkDecimalToggle.addEventListener("change", () => {
    // If we uncheck, snap currentServings to nearest integer
    if (!chkDecimalToggle.checked) {
      updateServings(Math.round(currentServings));
    }
  });

  // ----------------------------------------------------
  // Cook Mode Layout & Interaction
  // ----------------------------------------------------
  const cookModeOverlay = document.getElementById("cook-mode-overlay");
  const btnEnterCookMode = document.getElementById("btn-enter-cook-mode");
  const btnExitCookMode = document.getElementById("btn-exit-cook-mode");
  const btnCookModeIngredients = document.getElementById("btn-cook-mode-ingredients");
  const cookModeIngredientsDrawer = document.getElementById("cook-mode-ingredients-drawer");
  const btnCloseDrawer = document.getElementById("btn-close-drawer");
  const cookModeProgressText = document.getElementById("cook-mode-progress-text");
  const btnCookModeTheme = document.getElementById("btn-cook-mode-theme");
  const iconSun = document.getElementById("icon-sun");
  const iconMoon = document.getElementById("icon-moon");

  // Open Cook Mode
  btnEnterCookMode.addEventListener("click", () => {
    cookModeOverlay.classList.add("is-open");
    document.body.style.overflow = "hidden"; // Prevent background scroll
    updateProgress();
  });

  // Exit Cook Mode
  btnExitCookMode.addEventListener("click", () => {
    cookModeOverlay.classList.remove("is-open");
    document.body.style.overflow = "";
  });

  // Toggle Ingredients Drawer
  btnCookModeIngredients.addEventListener("click", () => {
    cookModeIngredientsDrawer.classList.toggle("is-open");
  });

  // Close Ingredients Drawer
  btnCloseDrawer.addEventListener("click", () => {
    cookModeIngredientsDrawer.classList.remove("is-open");
  });

  // Handle checkbox change in Cook Mode
  document.querySelectorAll(".cook-mode-step-checkbox").forEach(chk => {
    chk.addEventListener("change", (e) => {
      const card = e.target.closest(".cook-mode-step-card");
      if (e.target.checked) {
        card.classList.add("checked");
      } else {
        card.classList.remove("checked");
      }
      updateProgress();
    });
  });

  function updateProgress() {
    const total = document.querySelectorAll(".cook-mode-step-card").length;
    const checked = document.querySelectorAll(".cook-mode-step-checkbox:checked").length;
    cookModeProgressText.textContent = `${checked} of ${total} steps completed`;
  }

  // Cook Mode Dark Theme Initialization & Toggle
  if (localStorage.getItem("cook-mode-theme") === "dark") {
    cookModeOverlay.classList.add("cook-mode-dark");
    iconSun.style.display = "block";
    iconMoon.style.display = "none";
  }

  btnCookModeTheme.addEventListener("click", () => {
    const isDark = cookModeOverlay.classList.contains("cook-mode-dark");
    if (isDark) {
      cookModeOverlay.classList.remove("cook-mode-dark");
      iconSun.style.display = "none";
      iconMoon.style.display = "block";
      localStorage.setItem("cook-mode-theme", "light");
    } else {
      cookModeOverlay.classList.add("cook-mode-dark");
      iconSun.style.display = "block";
      iconMoon.style.display = "none";
      localStorage.setItem("cook-mode-theme", "dark");
    }
  });

  // ----------------------------------------------------
  // Synchronized Timer & Audio Buzzing Alarm Manager
  // ----------------------------------------------------
  let audioCtx = null;
  let alarmInterval = null;
  const timerRegistry = {}; // stepIndex -> { remainingSeconds, durationMinutes, status, intervalId }

  function initAudio() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
  }

  function playBeep() {
    if (!audioCtx) return;
    const osc = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();
    
    osc.connect(gainNode);
    gainNode.connect(audioCtx.destination);
    
    osc.type = "sine";
    osc.frequency.setValueAtTime(880, audioCtx.currentTime); // A5 note
    gainNode.gain.setValueAtTime(0, audioCtx.currentTime);
    gainNode.gain.linearRampToValueAtTime(0.5, audioCtx.currentTime + 0.05);
    gainNode.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.5);
    
    osc.start();
    osc.stop(audioCtx.currentTime + 0.5);
  }

  function startAlarmBuzzer() {
    initAudio();
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }
    if (!alarmInterval) {
      playBeep();
      alarmInterval = setInterval(playBeep, 1000);
    }
  }

  function stopAlarmBuzzer() {
    // Only stop if there are no active alarm timers left in registry
    let anyAlarm = false;
    for (const idx in timerRegistry) {
      if (timerRegistry[idx].status === "alarm") {
        anyAlarm = true;
        break;
      }
    }
    if (!anyAlarm && alarmInterval) {
      clearInterval(alarmInterval);
      alarmInterval = null;
    }
  }

  function getOrCreateTimerState(stepIndex, durationMinutes) {
    if (!timerRegistry[stepIndex]) {
      timerRegistry[stepIndex] = {
        durationMinutes: durationMinutes,
        remainingSeconds: durationMinutes * 60,
        status: "stopped",
        intervalId: null
      };
    }
    return timerRegistry[stepIndex];
  }

  document.addEventListener("click", (event) => {
    const target = event.target;
    
    // 1. Toggle Timer Widget Visibility
    const badge = target.closest(".timer-badge, .cook-mode-timer-badge");
    if (badge) {
      // Prevent event bubbling so it doesn't trigger parent label checks in Cook Mode
      event.preventDefault();
      event.stopPropagation();

      const stepCard = badge.closest(".step-item, .cook-mode-step-card");
      const stepIndex = stepCard.dataset.stepIndex || stepCard.dataset.stepId;
      const duration = parseInt(badge.dataset.duration || badge.closest("[data-duration]").dataset.duration, 10);
      
      // Find corresponding control widget
      const widget = stepCard.querySelector(".timer-widget, .cook-mode-timer-controls");
      if (widget) {
        const isHidden = widget.style.display === "none";
        widget.style.display = isHidden ? "flex" : "none";
        
        // Initialize if needed
        getOrCreateTimerState(stepIndex, duration);
        updateTimerUI(stepIndex);
      }
      return;
    }

    // 2. Timer Actions (Start, Pause, Reset)
    const btn = target.closest(".timer-btn, .cook-mode-timer-btn");
    if (btn) {
      event.preventDefault();
      event.stopPropagation();

      const stepCard = btn.closest(".step-item, .cook-mode-step-card");
      const stepIndex = stepCard.dataset.stepIndex || stepCard.dataset.stepId;
      const badge = stepCard.querySelector(".timer-badge, .cook-mode-timer-badge");
      const duration = parseInt(badge.dataset.duration || badge.closest("[data-duration]").dataset.duration, 10);
      const action = btn.dataset.timerAction;
      
      getOrCreateTimerState(stepIndex, duration);
      handleTimerAction(stepIndex, action);
    }
  });

  function handleTimerAction(stepIndex, action) {
    initAudio();
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume();
    }

    const state = timerRegistry[stepIndex];
    if (!state) return;

    if (action === "start") {
      if (state.status === "alarm") {
        state.status = "stopped";
        state.remainingSeconds = state.durationMinutes * 60;
        stopAlarmBuzzer();
        updateTimerUI(stepIndex);
        return;
      }

      state.status = "running";
      updateTimerUI(stepIndex);

      state.intervalId = setInterval(() => {
        if (state.remainingSeconds > 0) {
          state.remainingSeconds--;
          updateTimerUI(stepIndex);
        } else {
          clearInterval(state.intervalId);
          state.intervalId = null;
          state.status = "alarm";
          startAlarmBuzzer();
          updateTimerUI(stepIndex);
        }
      }, 1000);

    } else if (action === "pause") {
      state.status = "paused";
      if (state.intervalId) {
        clearInterval(state.intervalId);
        state.intervalId = null;
      }
      updateTimerUI(stepIndex);

    } else if (action === "reset") {
      if (state.intervalId) {
        clearInterval(state.intervalId);
        state.intervalId = null;
      }
      state.status = "stopped";
      state.remainingSeconds = state.durationMinutes * 60;
      stopAlarmBuzzer();
      updateTimerUI(stepIndex);
    }
  }

  function updateTimerUI(stepIndex) {
    const state = timerRegistry[stepIndex];
    if (!state) return;

    const m = Math.floor(state.remainingSeconds / 60);
    const s = state.remainingSeconds % 60;
    const timeStr = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;

    // Find all elements for this step in both panels
    const stepElements = document.querySelectorAll(`[data-step-index="${stepIndex}"], [data-step-id="${stepIndex}"]`);
    
    stepElements.forEach(el => {
      const badge = el.querySelector(".timer-badge, .cook-mode-timer-badge");
      const badgeText = el.querySelector(".timer-badge span, .timer-badge-text");
      const timeDisplay = el.querySelector(".timer-time, .cook-mode-timer-time");
      const startBtn = el.querySelector('[data-timer-action="start"]');
      const pauseBtn = el.querySelector('[data-timer-action="pause"]');

      if (timeDisplay) {
        timeDisplay.textContent = timeStr;
      }

      if (badge) {
        badge.classList.remove("active", "alarm");
        if (state.status === "running") {
          badge.classList.add("active");
          if (badgeText) badgeText.textContent = timeStr;
        } else if (state.status === "alarm") {
          badge.classList.add("alarm");
          if (badgeText) badgeText.textContent = "ALARM";
        } else {
          if (badgeText) badgeText.textContent = `${state.durationMinutes} min`;
        }
      }

      if (startBtn && pauseBtn) {
        if (state.status === "running") {
          startBtn.style.display = "none";
          pauseBtn.style.display = "inline-block";
        } else if (state.status === "alarm") {
          startBtn.textContent = "STOP";
          startBtn.classList.add("stop");
          startBtn.style.display = "inline-block";
          pauseBtn.style.display = "none";
        } else if (state.status === "paused") {
          startBtn.textContent = "Resume";
          startBtn.classList.remove("stop");
          startBtn.style.display = "inline-block";
          pauseBtn.style.display = "none";
        } else {
          // stopped
          startBtn.textContent = "Start";
          startBtn.classList.remove("stop");
          startBtn.style.display = "inline-block";
          pauseBtn.style.display = "none";
        }
      }
    });
  }
});
