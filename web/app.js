/* Hub — оболочка: меню, тема, общие помощники */

window.HubTools = window.HubTools || {};

const TOOL_ICONS = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1.5 1.5 0 0 1-1.5 1.5h-5A1.5 1.5 0 0 1 13 20v-5h-2v5A1.5 1.5 0 0 1 9.5 21.5h-5A1.5 1.5 0 0 1 3 20z"/>',
  clipboard: '<rect x="6" y="4.5" width="12" height="16" rx="2.5"/><path d="M9.5 4.5V3.6A1.1 1.1 0 0 1 10.6 2.5h2.8a1.1 1.1 0 0 1 1.1 1.1v.9"/><path d="M9 10h6M9 13.5h6M9 17h3.5"/>',
  folder: '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/>',
  copies: '<rect x="3.5" y="4.5" width="10" height="13" rx="2.5"/><rect x="10.5" y="7.5" width="10" height="13" rx="2.5"/>',
  pie: '<circle cx="12" cy="12" r="8.5"/><path d="M12 12V3.5M12 12l7.3 4.2"/>',
  note: '<rect x="4.5" y="3.5" width="15" height="17" rx="3"/><path d="M8 8.5h8M8 12h8M8 15.5h5"/>',
  weight: '<path d="M6.5 8.5v7M17.5 8.5v7M3.5 10.5v3M20.5 10.5v3M6.5 12h11"/>',
  diff: '<rect x="3.5" y="5" width="7" height="14" rx="2"/><rect x="13.5" y="5" width="7" height="14" rx="2"/><path d="M8 12h8"/>',
  image: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="8.5" cy="9" r="1.5"/><path d="M20.5 15.5l-5-5-8 8M14.5 13.5l3.5 3.5"/>',
  broom: '<path d="M11.5 4.5l1.4 3.1 3.1 1.4-3.1 1.4-1.4 3.1-1.4-3.1-3.1-1.4 3.1-1.4z"/><path d="M17.5 13.8l.8 1.7 1.7.8-1.7.8-.8 1.7-.8-1.7-1.7-.8 1.7-.8z"/><path d="M6 15.8l.6 1.3 1.3.6-1.3.6L6 19.6l-.6-1.3-1.3-.6 1.3-.6z"/>',
  pulse: '<path d="M3 12.5h4l2.2-6 3.4 11 2.4-7.2 1.8 2.2H21"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 10.8v5.4"/><circle cx="12" cy="7.7" r="1" fill="currentColor" stroke="none"/>',
  undo: '<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3"/><path d="M4 4.5V10h5.5"/>',
  renamer: '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>',
  checksum: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><circle cx="12" cy="11" r="2.5"/><path d="M12 13.5v3"/>',
  qrdrop: '<rect x="5" y="2" width="14" height="20" rx="3"/><circle cx="12" cy="18" r="1" fill="currentColor"/><path d="M8.5 8.5a5 5 0 0 1 7 0M10 11.5a2.8 2.8 0 0 1 4 0"/>',
  dots: '<circle cx="5" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.6" fill="currentColor" stroke="none"/>',
};

const Hub = {
  tools: [],
  activeId: null,
  cleanup: null,
  busyCount: 0,
};

window.Hub = Hub;

/* ---------- Утилиты ---------- */

Hub.escapeHtml = function (value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
};

Hub.plural = function (count, one, few, many) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
};

Hub.fmtSize = function (bytes) {
  const value = Number(bytes) || 0;
  if (value <= 0) return "0 Б";
  const units = ["Б", "КБ", "МБ", "ГБ", "ТБ"];
  let index = 0;
  let size = value;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  const digits = size >= 100 || index === 0 ? 0 : 1;
  return `${size.toLocaleString("ru-RU", { maximumFractionDigits: digits })} ${units[index]}`;
};

Hub.timeAgo = function (timestamp) {
  const seconds = Math.max(0, Date.now() / 1000 - (Number(timestamp) || 0));
  if (seconds < 45) return "только что";
  if (seconds < 3600) {
    const minutes = Math.round(seconds / 60);
    return `${minutes} мин назад`;
  }
  if (seconds < 86400) {
    const hours = Math.round(seconds / 3600);
    return `${hours} ч назад`;
  }
  const days = Math.floor(seconds / 86400);
  if (days === 1) return "вчера";
  if (days < 7) return `${days} дн назад`;
  const date = new Date((Number(timestamp) || 0) * 1000);
  const months = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  return `${date.getDate()} ${months[date.getMonth()]}`;
};

Hub.api = async function (path, body) {
  const options = { method: "GET", headers: {} };
  if (body !== undefined) {
    options.method = "POST";
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch {
    throw new Error("Нет связи с программой. Проверь, что окно Hub открыто.");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.error) {
    throw new Error(data.error || `Ошибка ${response.status}`);
  }
  return data;
};

let toastTimer = null;

Hub.toast = function (message) {
  const node = document.getElementById("toast");
  node.textContent = message;
  node.classList.remove("hidden");
  node.style.animation = "none";
  void node.offsetWidth;
  node.style.animation = "";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.add("hidden"), 3400);

  const lower = String(message || "").toLowerCase();
  if (lower.includes("скопирован")) Hub.playSound("copy");
  else if (lower.includes("удален") || lower.includes("очищен")) Hub.playSound("trash");
  else if (lower.includes("сохранен") || lower.includes("выполнен") || lower.includes("создан")) Hub.playSound("check");
};

Hub.setBusy = function (active, text = "Работаю…") {
  if (active) {
    Hub.busyCount += 1;
    document.getElementById("busyText").textContent = text;
    document.getElementById("busy").classList.remove("hidden");
  } else {
    Hub.busyCount = Math.max(0, Hub.busyCount - 1);
    if (Hub.busyCount === 0) document.getElementById("busy").classList.add("hidden");
  }
};

const motionOn = () => document.documentElement.dataset.motion !== "off";
let activeDialog = null;
let dialogId = 0;

Hub.dismissDialog = function () {
  if (activeDialog) activeDialog.cancel();
};

Hub.choose = function ({ title, text, choices, cancelText = "Отмена" }) {
  Hub.dismissDialog();
  return new Promise((resolve) => {
    const previousFocus = document.activeElement;
    const shell = document.querySelector(".shell");
    const wasInert = shell ? shell.inert : false;
    const titleId = `hub-dialog-title-${++dialogId}`;
    const overlay = document.createElement("div");
    overlay.className = "modal";
    overlay.innerHTML = `
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="${titleId}">
        <h2 id="${titleId}">${Hub.escapeHtml(title)}</h2>
        <p class="result-text">${Hub.escapeHtml(text)}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" data-act="cancel">${Hub.escapeHtml(cancelText)}</button>
          ${choices.map((choice, index) => `<button class="btn ${choice.danger ? "danger" : "primary"}" type="button" data-choice="${index}">${Hub.escapeHtml(choice.label)}</button>`).join("")}
        </div>
      </div>`;

    let closing = false;
    let settled = false;
    let closeTimer = null;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      clearTimeout(closeTimer);
      overlay.remove();
      document.removeEventListener("keydown", onKey);
      if (shell) shell.inert = Boolean(wasInert);
      activeDialog = null;
      if (previousFocus?.isConnected) previousFocus.focus();
      resolve(value);
    };
    const close = (value) => {
      if (closing || settled) return;
      closing = true;
      overlay.classList.add("is-closing");
      overlay.querySelectorAll("button").forEach(button => { button.disabled = true; });
      if (!motionOn()) finish(value);
      else closeTimer = setTimeout(() => finish(value), 160);
    };
    const onKey = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close(null);
      }
      if (event.key !== "Tab") return;
      const buttons = [...overlay.querySelectorAll("button")].filter(button => !button.disabled);
      const first = buttons[0];
      const last = buttons[buttons.length - 1];
      if (!first) {
        event.preventDefault();
      } else if (!overlay.contains(document.activeElement) || (event.shiftKey && document.activeElement === first)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) return close(null);
      const button = event.target.closest("button");
      if (!button || button.disabled) return;
      if (button.dataset.act === "cancel") close(null);
      else if (button.dataset.choice !== undefined) close(choices[Number(button.dataset.choice)].value);
    });
    activeDialog = { cancel: () => finish(null) };
    if (shell) shell.inert = true;
    document.addEventListener("keydown", onKey);
    document.body.appendChild(overlay);
    const safeIndex = choices.findIndex(choice => !choice.danger);
    overlay.querySelector(safeIndex < 0 ? '[data-act="cancel"]' : `[data-choice="${safeIndex}"]`).focus();
  });
};

Hub.confirm = async function ({ title, text, confirmText = "Подтвердить", cancelText = "Отмена", danger = false }) {
  return (await Hub.choose({ title, text, cancelText, choices: [{ value: true, label: confirmText, danger }] })) === true;
};

/* ---------- Тема ---------- */

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.getElementById("themeLabel").textContent = theme === "dark" ? "Светлая тема" : "Тёмная тема";
  try {
    localStorage.setItem("hub-theme", theme);
  } catch {
    /* localStorage может быть недоступен */
  }
}

function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem("hub-theme");
  } catch {
    saved = null;
  }
  applyTheme(saved || "light");
}

/* ---------- Движение ---------- */

function applyMotion(enabled) {
  document.documentElement.dataset.motion = enabled ? "on" : "off";
  document.getElementById("motionLabel").textContent = enabled ? "Анимации включены" : "Анимации выключены";
  document.getElementById("motionBtn").setAttribute("aria-pressed", String(enabled));
  try {
    localStorage.setItem("hub-motion", enabled ? "on" : "off");
  } catch {
    /* localStorage может быть недоступен */
  }
}

function initMotion() {
  let saved = null;
  try {
    saved = localStorage.getItem("hub-motion");
  } catch {
    saved = null;
  }
  // Системная настройка «уменьшить движение» здесь намеренно не учитывается: в Windows
  // эффекты анимации часто отключены по умолчанию, и хаб выглядел бы совсем без движения.
  // Кому анимации мешают — выключает их этим переключателем, выбор запоминается.
  applyMotion(saved !== "off");
}

/* ---------- Микро-звуки Web Audio API ---------- */
let audioCtx = null;
let soundEnabled = true;

Hub.playSound = function (type) {
  if (!soundEnabled) return;
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    if (!audioCtx) audioCtx = new AudioContextClass();
    if (audioCtx.state === "suspended") audioCtx.resume();

    const t = audioCtx.currentTime;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);

    if (type === "copy") {
      // Приятный мягкий щелчок/колокольчик копирования
      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, t); // D5
      osc.frequency.exponentialRampToValueAtTime(880, t + 0.08); // A5
      gain.gain.setValueAtTime(0.08, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.12);
      osc.start(t);
      osc.stop(t + 0.12);
    } else if (type === "check") {
      // Аккорд завершения задачи (восходящий тон)
      osc.type = "sine";
      osc.frequency.setValueAtTime(523.25, t); // C5
      osc.frequency.exponentialRampToValueAtTime(659.25, t + 0.09); // E5
      gain.gain.setValueAtTime(0.09, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.16);
      osc.start(t);
      osc.stop(t + 0.16);
    } else if (type === "trash") {
      // Мягкий глухой стук удаления
      osc.type = "triangle";
      osc.frequency.setValueAtTime(180, t);
      osc.frequency.exponentialRampToValueAtTime(60, t + 0.12);
      gain.gain.setValueAtTime(0.12, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.14);
      osc.start(t);
      osc.stop(t + 0.14);
    } else if (type === "pop") {
      // Лёгкий тактильный щелчок переключения вкладок
      osc.type = "sine";
      osc.frequency.setValueAtTime(320, t);
      osc.frequency.exponentialRampToValueAtTime(440, t + 0.04);
      gain.gain.setValueAtTime(0.04, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.05);
      osc.start(t);
      osc.stop(t + 0.05);
    }
  } catch {
    /* Web Audio API может быть недоступен в некоторых средах */
  }
};

/* ---------- Акцентные цвета ---------- */
function applyAccent(name) {
  if (document.documentElement && document.documentElement.dataset) {
    if (name) {
      document.documentElement.dataset.accent = name;
    } else {
      delete document.documentElement.dataset.accent;
    }
  }
  try {
    if (name) localStorage.setItem("hub-accent", name);
    else localStorage.removeItem("hub-accent");
  } catch {
    /* localStorage может быть недоступен */
  }
  const dots = typeof document.querySelectorAll === "function" ? document.querySelectorAll("#accentBar .accent-dot") : [];
  if (dots && dots.forEach) {
    dots.forEach((dot) => {
      if (dot.classList && dot.classList.toggle) {
        dot.classList.toggle("is-active", (dot.dataset && dot.dataset.accent || "") === (name || ""));
      }
    });
  }
}

function initAccent() {
  let saved = null;
  try {
    saved = localStorage.getItem("hub-accent");
  } catch {
    saved = null;
  }
  applyAccent(saved || "");

  const bar = document.getElementById("accentBar");
  if (bar && bar.addEventListener) {
    bar.addEventListener("click", (e) => {
      const dot = e.target && e.target.closest ? e.target.closest(".accent-dot") : null;
      if (!dot) return;
      applyAccent(dot.dataset && dot.dataset.accent || "");
      Hub.playSound("pop");
    });
  }
}

/* ---------- Эффект стекла (Acrylic Blur) ---------- */
function applyGlass(enabled) {
  if (document.documentElement && document.documentElement.dataset) {
    document.documentElement.dataset.glass = enabled ? "on" : "off";
  }
  const label = document.getElementById("glassLabel");
  if (label) label.textContent = enabled ? "Стекло включено" : "Стекло выключено";
  const btn = document.getElementById("glassBtn");
  if (btn && btn.setAttribute) btn.setAttribute("aria-pressed", String(enabled));
  try {
    localStorage.setItem("hub-glass", enabled ? "on" : "off");
  } catch {
    /* localStorage может быть недоступен */
  }
}

function initGlass() {
  let saved = null;
  try {
    saved = localStorage.getItem("hub-glass");
  } catch {
    saved = null;
  }
  applyGlass(saved === "on");

  const btn = document.getElementById("glassBtn");
  if (btn && btn.addEventListener) {
    btn.addEventListener("click", () => {
      const next = document.documentElement && document.documentElement.dataset && document.documentElement.dataset.glass !== "on";
      applyGlass(next);
      Hub.playSound("pop");
    });
  }
}

/* ---------- Переключатель звука ---------- */
function applySound(enabled) {
  soundEnabled = enabled;
  const label = document.getElementById("soundLabel");
  if (label) label.textContent = enabled ? "Звуки включены" : "Звуки выключены";
  const btn = document.getElementById("soundBtn");
  if (btn && btn.setAttribute) btn.setAttribute("aria-pressed", String(enabled));
  try {
    localStorage.setItem("hub-sound", enabled ? "on" : "off");
  } catch {
    /* localStorage может быть недоступен */
  }
}

function initSound() {
  let saved = null;
  try {
    saved = localStorage.getItem("hub-sound");
  } catch {
    saved = null;
  }
  applySound(saved !== "off");

  const btn = document.getElementById("soundBtn");
  if (btn && btn.addEventListener) {
    btn.addEventListener("click", () => {
      applySound(!soundEnabled);
      if (soundEnabled) Hub.playSound("pop");
    });
  }
}

/* ---------- Окно настроек Hub (Settings) ---------- */
let previousSettingsFocus = null;

Hub.openSettings = function () {
  const modal = document.getElementById("settingsModal");
  if (!modal) return;
  previousSettingsFocus = document.activeElement;
  modal.classList.remove("hidden");
  Hub.playSound("pop");
  const firstBtn = modal.querySelector("button");
  if (firstBtn && firstBtn.focus) firstBtn.focus();
};

Hub.closeSettings = function () {
  const modal = document.getElementById("settingsModal");
  if (!modal || modal.classList.contains("hidden")) return;
  modal.classList.add("hidden");
  if (previousSettingsFocus && previousSettingsFocus.focus) {
    try {
      previousSettingsFocus.focus();
    } catch {
      /* элемент мог быть перемонтирован */
    }
  }
};

function initSettings() {
  const openBtn = document.getElementById("openSettingsBtn");
  if (openBtn && openBtn.addEventListener) {
    openBtn.addEventListener("click", () => Hub.openSettings());
  }

  const closeBtn = document.getElementById("closeSettingsBtn");
  if (closeBtn && closeBtn.addEventListener) {
    closeBtn.addEventListener("click", () => Hub.closeSettings());
  }

  const doneBtn = document.getElementById("settingsDoneBtn");
  if (doneBtn && doneBtn.addEventListener) {
    doneBtn.addEventListener("click", () => Hub.closeSettings());
  }

  const modal = document.getElementById("settingsModal");
  if (modal && modal.addEventListener) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) Hub.closeSettings();
    });
  }

  const testSound = document.getElementById("testSoundBtn");
  if (testSound && testSound.addEventListener) {
    testSound.addEventListener("click", () => {
      Hub.playSound("check");
    });
  }

  const desktopBtn = document.getElementById("settingsDesktopShortcutBtn");
  if (desktopBtn && desktopBtn.addEventListener) {
    desktopBtn.addEventListener("click", async () => {
      try {
        const res = await Hub.api("/api/shortcuts/desktop");
        Hub.toast(res.message || "Ярлык на Рабочем столе создан!");
      } catch (err) {
        Hub.toast(err.message);
      }
    });
  }

  const startBtn = document.getElementById("settingsStartmenuShortcutBtn");
  if (startBtn && startBtn.addEventListener) {
    startBtn.addEventListener("click", async () => {
      try {
        const res = await Hub.api("/api/shortcuts/startmenu");
        Hub.toast(res.message || "Ярлык в меню «Пуск» создан!");
      } catch (err) {
        Hub.toast(err.message);
      }
    });
  }

  const backupBtn = document.getElementById("settingsBackupBtn");
  if (backupBtn && backupBtn.addEventListener) {
    backupBtn.addEventListener("click", async () => {
      try {
        Hub.setBusy(true, "Создаю резервную копию…");
        const res = await Hub.api("/api/system/backup", {});
        Hub.toast(res.message || "Резервная копия создана!");
      } catch (err) {
        Hub.toast(err.message);
      } finally {
        Hub.setBusy(false);
      }
    });
  }

  if (typeof window.addEventListener === "function") {
    window.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "," || e.key === "б" || e.key === "Б")) {
        e.preventDefault();
        const m = document.getElementById("settingsModal");
        if (m && !m.classList.contains("hidden")) Hub.closeSettings();
        else Hub.openSettings();
      } else if (e.key === "Escape") {
        const m = document.getElementById("settingsModal");
        if (m && !m.classList.contains("hidden")) {
          e.preventDefault();
          Hub.closeSettings();
        }
      }
    });
  }
}

/* ---------- Переход к результату общего поиска ---------- */

Hub.pendingSearch = null;
Hub.searchHooks = {};

// Инструмент при монтировании забирает запрос, который для него оставил общий поиск.
Hub.takeSearch = function (toolId) {
  const pending = Hub.pendingSearch;
  if (!pending || pending.tool !== toolId) return "";
  Hub.pendingSearch = null;
  return pending.query;
};

Hub.setSearchHook = function (toolId, apply) {
  Hub.searchHooks[toolId] = apply;
};

Hub.clearSearchHook = function (toolId) {
  delete Hub.searchHooks[toolId];
};

// Открыть инструмент и сразу применить к нему поисковый запрос.
Hub.searchIn = function (toolId, query) {
  const hook = Hub.searchHooks[toolId];
  if (hook && hook(query)) return true;
  Hub.pendingSearch = { tool: toolId, query };
  if (Hub.activeId === toolId) {
    // Тот же инструмент уже открыт — принудительно перемонтируем его с запросом.
    const tool = Hub.tools.find((item) => item.id === toolId);
    if (tool) mountTool(tool);
  } else {
    location.hash = `#/${toolId}`;
  }
  return true;
};

/* ---------- Автозапуск ---------- */

function paintAutostart(state) {
  const button = document.getElementById("autostartBtn");
  if (!button) return;
  const enabled = Boolean(state && state.enabled);
  button.classList.remove("hidden");
  button.setAttribute("aria-pressed", String(enabled));
  button.title = enabled
    ? "Hub запускается вместе с Windows — выключить"
    : "Запускать Hub вместе с Windows — история буфера пишется всегда";
  const label = document.getElementById("autostartLabel");
  if (label) label.textContent = enabled ? "Автозапуск включён" : "Автозапуск выключен";
}

async function initAutostart() {
  const button = document.getElementById("autostartBtn");
  if (!button) return;
  let state;
  try {
    state = await Hub.api("/api/autostart");
  } catch {
    button.classList.add("hidden");
    return;
  }
  if (!state || !state.supported) {
    button.classList.add("hidden");
    return;
  }
  paintAutostart(state);
  button.addEventListener("click", async () => {
    const next = button.getAttribute("aria-pressed") !== "true";
    button.disabled = true;
    try {
      const updated = await Hub.api("/api/autostart", { enabled: next });
      paintAutostart(updated);
      Hub.toast(next ? "Hub будет запускаться вместе с Windows" : "Автозапуск выключен");
    } catch (error) {
      Hub.toast(error.message);
    } finally {
      button.disabled = false;
    }
  });
}

/* ---------- Трей Windows ---------- */

function paintTray(state) {
  const button = document.getElementById("trayToggleBtn");
  if (!button) return;
  const running = Boolean(state && state.running);
  button.setAttribute("aria-pressed", String(running));
  const label = document.getElementById("trayToggleLabel");
  if (label) label.textContent = running ? "Трей включён" : "Трей выключен";
}

async function initTray() {
  const button = document.getElementById("trayToggleBtn");
  if (!button) return;
  let state;
  try {
    state = await Hub.api("/api/tray/status");
  } catch {
    return;
  }
  if (!state || !state.supported) {
    if (typeof button.closest === "function") {
      button.closest(".settings-item")?.classList.add("hidden");
    } else {
      button.classList.add("hidden");
    }
    return;
  }
  paintTray(state);
  button.addEventListener("click", async () => {
    const next = button.getAttribute("aria-pressed") !== "true";
    button.disabled = true;
    try {
      const updated = await Hub.api("/api/tray/toggle", { enabled: next });
      paintTray(updated);
      Hub.playSound("action");
      Hub.toast(next ? "Значок в трее включён" : "Значок в трее скрыт");
    } catch (error) {
      Hub.toast(error.message);
    } finally {
      button.disabled = false;
    }
  });
}

/* ---------- Меню и переключение инструментов ---------- */

function navMarkup(tool) {
  const active = tool.id === Hub.activeId;
  return `
    <a class="nav-item ${active ? "is-active" : ""}" href="#/${tool.id}" data-id="${tool.id}" title="${Hub.escapeHtml(tool.hint || "")}">
      <span class="nav-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          ${TOOL_ICONS[tool.icon] || TOOL_ICONS.dots}
        </svg>
      </span>
      <span class="nav-name">${Hub.escapeHtml(tool.name)}</span>
    </a>`;
}

function renderNav() {
  document.getElementById("toolNav").innerHTML = Hub.tools.map(navMarkup).join("");
}

function mountTool(tool) {
  if (typeof Hub.cleanup === "function") {
    try {
      Hub.cleanup();
    } catch {
      /* инструмент мог уже убрать за собой */
    }
  }
  Hub.cleanup = null;
  Hub.activeId = tool.id;

  document.getElementById("toolTitle").textContent = tool.name;
  document.getElementById("toolHint").textContent = tool.hint || "";
  const root = document.getElementById("toolRoot");
  root.innerHTML = "";
  renderNav();

  const module = window.HubTools[tool.id];
  Hub.searchHooks = {};
  if (Hub.pendingSearch && Hub.pendingSearch.tool !== tool.id) Hub.pendingSearch = null;
  if (!module || typeof module.mount !== "function") {
    root.innerHTML = `
      <div class="soon">
        <p class="soon-title">Этот инструмент ещё в разработке</p>
        <p class="soon-text">Появится в следующем обновлении хаба.</p>
      </div>`;
    return;
  }

  Hub.cleanup = module.mount(root) || null;
  if (Hub.pendingSearch && Hub.pendingSearch.tool === tool.id) Hub.pendingSearch = null;
}

let routeTimer = null;
let routeVersion = 0;

function route() {
  const requested = location.hash.replace(/^#\/?/, "").trim();
  const tool = Hub.tools.find((item) => item.id === requested) || Hub.tools[0];
  if (!tool) return;
  const version = ++routeVersion;
  clearTimeout(routeTimer);
  Hub.dismissDialog();
  const root = document.getElementById("toolRoot");
  root.classList.remove("is-exiting", "is-entering");
  root.inert = false;
  root.removeAttribute("aria-busy");
  if (Hub.activeId === tool.id) return;
  if (Hub.activeId && Hub.activeId !== tool.id) {
    Hub.playSound("pop");
  }
  const enter = () => {
    if (version !== routeVersion) return;
    root.classList.remove("is-exiting");
    root.inert = false;
    root.removeAttribute("aria-busy");
    mountTool(tool);
    if (motionOn()) {
      void root.offsetWidth;
      root.classList.add("is-entering");
    }
  };
  if (!Hub.activeId || !motionOn()) {
    enter();
  } else {
    root.inert = true;
    root.setAttribute("aria-busy", "true");
    root.classList.add("is-exiting");
    routeTimer = setTimeout(enter, 150);
  }
}

/* ---------- Старт ---------- */

async function init() {
  initTheme();
  initAccent();
  initGlass();
  initSound();
  initMotion();
  initSettings();

  const themeBtn = document.getElementById("themeBtn");
  if (themeBtn && themeBtn.addEventListener) {
    themeBtn.addEventListener("click", () => {
      applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
    });
  }

  const motionBtn = document.getElementById("motionBtn");
  if (motionBtn && motionBtn.addEventListener) {
    motionBtn.addEventListener("click", () => {
      applyMotion(document.documentElement.dataset.motion === "off");
    });
  }

  if (typeof window.addEventListener === "function") {
    window.addEventListener("hashchange", route);
  }

  const fallbackTools = [
    { id: "home", name: "Главная", hint: "Сводка дня, виджеты и быстрые действия", icon: "home" },
    { id: "clipboard", name: "Буфер обмена", hint: "Всё, что копировал, — под рукой", icon: "clipboard" },
    { id: "notes", name: "Заметки", hint: "Быстрые записи на этом компьютере", icon: "note" },
    { id: "sorter", name: "Сортировка файлов", hint: "Разложить папку по категориям", icon: "folder" },
    { id: "dupes", name: "Дубликаты", hint: "Одинаковые файлы по содержимому", icon: "copies" },
    { id: "bigfiles", name: "Большие файлы", hint: "Что занимает больше всего места", icon: "weight" },
    { id: "diskmap", name: "Карта диска", hint: "Что сколько места занимает", icon: "pie" },
    { id: "compare", name: "Сравнение папок", hint: "Что появилось и что изменилось", icon: "diff" },
    { id: "images", name: "Сжатие картинок", hint: "Конвертация, сжатие и изменение размера", icon: "image" },
    { id: "cleanup", name: "Уборка", hint: "Старые файлы и пустые папки", icon: "broom" },
    { id: "trash", name: "Корзина", hint: "Что можно вернуть на место", icon: "undo" },
    { id: "monitor", name: "Мониторинг ПК", hint: "Что сейчас грузит компьютер", icon: "pulse" },
    { id: "about", name: "О программе", hint: "Версия, лицензия и исходный код", icon: "info" },
  ];

  try {
    const info = await Hub.api("/api/info");
    Hub.tools = Array.isArray(info.tools) && info.tools.length ? info.tools : fallbackTools;
    Hub.defaultFolder = info.default_folder || "";
    Hub.version = info.version || "";
  } catch (error) {
    Hub.tools = fallbackTools;
    Hub.defaultFolder = "";
    Hub.version = "";
    Hub.toast(error.message);
  }

  renderNav();
  route();
  initAutostart();
  initTray();

  if (window.HubPalette && typeof window.HubPalette.init === "function") window.HubPalette.init();

  // Первый инструмент уже на экране — можно убирать заставку и звать обучение.
  if (window.HubIntro && typeof window.HubIntro.ready === "function") window.HubIntro.ready();
}

init();
