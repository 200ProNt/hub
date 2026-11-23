/* Hub — стартовый экран и короткое обучение */

(function () {
  const SPLASH_MIN_MS = 1150;
  const SPLASH_OUT_MS = 400;
  const ONBOARDED_KEY = "hub-onboarded";

  const ICONS = {
    grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/>',
    list: '<path d="M4 7h16M4 12h16M4 17h10"/>',
    undo: '<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3"/><path d="M4 4.5V10h5.5"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4 4"/>',
    theme: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2.5 12h2M19.5 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  };

  // Первый экран — приветствие, дальше нумерованные шаги.
  const SCREENS = [
    {
      icon: "grid",
      title: "Привет, это Hub",
      text: "Локальные инструменты на каждый день. Покажу за четыре шага — это займёт полминуты.",
    },
    {
      icon: "list",
      title: "Все инструменты слева",
      text: "Буфер обмена, заметки, сортировка файлов, дубликаты, большие файлы, карта диска, сравнение папок, уборка, мониторинг и «О программе». Переключение — один клик.",
    },
    {
      icon: "undo",
      title: "Удаление можно вернуть",
      text: "Файлы и папки уходят в корзину хаба: внизу появляется кнопка «Вернуть». Совсем удалить тоже можно, но только отдельным подтверждением — на всякий случай.",
    },
    {
      icon: "search",
      title: "Поиск вместо листания",
      text: "В каждом инструменте есть поиск и фильтры. Введи часть имени файла или процесса — список сразу сузится.",
    },
    {
      icon: "theme",
      title: "Тема, анимации и приватность",
      text: "Открой настройки внизу слева, чтобы выбрать тему и настроить анимации. Данные хранятся в папке data/ на этом компьютере.",
    },
  ];

  const startedAt = Date.now();
  let splashGone = false;
  let appReady = false;
  let introShown = false;
  let activeIntro = null;
  let introSerial = 0;

  function motionOn() {
    return document.documentElement.dataset.motion !== "off";
  }

  function firstRun() {
    try {
      return (typeof HubPreferences !== "undefined" ? HubPreferences.get(ONBOARDED_KEY) : localStorage.getItem(ONBOARDED_KEY)) !== "1";
    } catch {
      return true;
    }
  }

  function rememberOnboarding() {
    try {
      if (typeof HubPreferences !== "undefined") HubPreferences.set(ONBOARDED_KEY, "1");
      else localStorage.setItem(ONBOARDED_KEY, "1");
    } catch {
      /* localStorage может быть недоступен */
    }
  }

  /* ---------- Стартовый экран ---------- */

  function removeSplash() {
    if (splashGone) return;
    splashGone = true;
    const node = document.getElementById("splash");
    if (!node) return;
    if (!motionOn()) {
      node.remove();
      return;
    }
    node.classList.add("is-done");
    window.setTimeout(() => node.remove(), SPLASH_OUT_MS);
  }

  function ready() {
    if (appReady) return;
    appReady = true;
    if (window.hubDesktopState) {
      document.getElementById("splash")?.remove();
      maybeOnboard();
      return;
    }
    const wait = motionOn()
      ? Math.max(0, SPLASH_MIN_MS - (Date.now() - startedAt))
      : 0;
    window.setTimeout(() => {
      removeSplash();
      window.setTimeout(maybeOnboard, motionOn() ? SPLASH_OUT_MS : 0);
    }, wait);
  }

  // Если основной скрипт упал, заставка не должна закрывать интерфейс навсегда.
  window.setTimeout(ready, 5000);

  function maybeOnboard() {
    if (introShown || !firstRun()) return;
    introShown = true;
    openIntro();
  }

  /* ---------- Обучение ---------- */

  function openIntro() {
    if (activeIntro) return;

    const shell = document.querySelector(".shell");
    const previousFocus = document.activeElement;
    const wasInert = shell ? shell.inert : false;
    const titleId = `intro-title-${++introSerial}`;
    let index = 0;
    let closing = false;
    let closed = false;

    const overlay = document.createElement("div");
    overlay.className = "intro";
    overlay.innerHTML = `
      <div class="intro-card" role="dialog" aria-modal="true" aria-labelledby="${titleId}">
        <button class="intro-skip" type="button" data-act="skip">Пропустить</button>
        <div class="intro-visual" data-intro="visual" aria-hidden="true"></div>
        <p class="intro-step" data-intro="step"></p>
        <h2 id="${titleId}" data-intro="title"></h2>
        <p class="intro-text" data-intro="text" aria-live="polite"></p>
        <div class="intro-dots" data-intro="dots" aria-hidden="true"></div>
        <div class="intro-actions">
          <button class="btn ghost" type="button" data-act="back">Назад</button>
          <button class="btn primary" type="button" data-act="next">Дальше</button>
        </div>
      </div>`;

    const visual = overlay.querySelector('[data-intro="visual"]');
    const stepNode = overlay.querySelector('[data-intro="step"]');
    const titleNode = overlay.querySelector('[data-intro="title"]');
    const textNode = overlay.querySelector('[data-intro="text"]');
    const dotsNode = overlay.querySelector('[data-intro="dots"]');
    const skipButton = overlay.querySelector('[data-act="skip"]');
    const backButton = overlay.querySelector('[data-act="back"]');
    const nextButton = overlay.querySelector('[data-act="next"]');

    const steps = SCREENS.length - 1;
  const CHIPS = ["всё локально", "без аккаунта", "MIT"];

    function render() {
      const screen = SCREENS[index];
      const isWelcome = index === 0;
      const isLast = index === SCREENS.length - 1;

      visual.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${ICONS[screen.icon] || ICONS.grid}</svg>`;
      titleNode.textContent = screen.title;
      textNode.textContent = screen.text;
      stepNode.textContent = isWelcome ? "Знакомство" : `Шаг ${index} из ${steps}`;
      stepNode.classList.toggle("is-welcome", isWelcome);

      dotsNode.classList.toggle("intro-chips", isWelcome);
      dotsNode.innerHTML = isWelcome
        ? CHIPS.map(label => `<span>${label}</span>`).join("")
        : Array.from({ length: steps }, (_, dot) => `<i class="${dot === index - 1 ? "is-active" : ""}"></i>`).join("");

      backButton.classList.toggle("hidden", isWelcome);
      skipButton.classList.toggle("hidden", false);
      nextButton.textContent = isWelcome ? "Показать, как пользоваться" : isLast ? "Начать" : "Дальше";
    }

    function next() {
      if (index >= SCREENS.length - 1) return close();
      index += 1;
      render();
      nextButton.focus();
    }

    function back() {
      if (index <= 0) return;
      index -= 1;
      render();
      (index === 0 ? nextButton : backButton).focus();
    }

    function finish() {
      if (closed) return;
      closed = true;
      overlay.remove();
      activeIntro = null;
      if (previousFocus?.isConnected) previousFocus.focus();
    }

    function close() {
      if (closing || closed) return;
      closing = true;
      rememberOnboarding();
      if (shell) shell.inert = Boolean(wasInert);
      document.removeEventListener("keydown", onKey);
      if (motionOn()) {
        overlay.classList.add("is-closing");
        window.setTimeout(finish, 180);
      } else {
        finish();
      }
    }

    function onKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        next();
        return;
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        back();
        return;
      }
      if (event.key !== "Tab") return;
      const buttons = overlay.querySelectorAll("button").filter(button => !button.disabled && !button.classList.contains("hidden"));
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
    }

    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) return;
      const button = event.target.closest("[data-act]");
      if (!button || button.disabled) return;
      if (button.dataset.act === "next") next();
      else if (button.dataset.act === "back") back();
      else if (button.dataset.act === "skip") close();
    });

    activeIntro = { close };
    if (shell) shell.inert = true;
    document.addEventListener("keydown", onKey);
    document.body.appendChild(overlay);
    render();
    nextButton.focus();
  }

  window.HubIntro = { ready, open: openIntro };
})();
