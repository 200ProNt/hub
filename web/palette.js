/* Общий поиск по хабу: Ctrl+K — инструменты, заметки и история буфера в одном окне */

(function () {
  const SEARCH_DELAY = 120;

  const ICONS = {
    tool: '<rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/>',
    note: '<rect x="4.5" y="3.5" width="15" height="17" rx="3"/><path d="M8 8.5h8M8 12h8M8 15.5h5"/>',
    clipboard: '<rect x="6" y="4.5" width="12" height="16" rx="2.5"/><path d="M9.5 4.5V3.6A1.1 1.1 0 0 1 10.6 2.5h2.8a1.1 1.1 0 0 1 1.1 1.1v.9"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  };

  let overlay = null;
  let input = null;
  let list = null;
  let opened = false;
  let groups = [];
  let items = [];
  let active = -1;
  let seq = 0;
  let timer = null;
  let lastQuery = "";
  let previousFocus = null;

  function icon(kind) {
    return `<span class="palette-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
        ${ICONS[kind] || ICONS.tool}
      </svg>
    </span>`;
  }

  function build() {
    overlay = document.createElement("div");
    overlay.className = "palette hidden";
    overlay.id = "hubPalette";
    overlay.innerHTML = `
      <div class="palette-card" role="dialog" aria-modal="true" aria-label="Поиск по хабу">
        <div class="palette-field">
          ${icon("search")}
          <input id="paletteInput" type="search" placeholder="Найти инструмент, заметку или запись из буфера" autocomplete="off" spellcheck="false" role="combobox" aria-expanded="true" aria-controls="paletteList" aria-autocomplete="list" aria-label="Поиск по хабу">
          <kbd>Esc</kbd>
        </div>
        <div class="palette-list" id="paletteList" role="listbox" aria-label="Результаты поиска"></div>
        <p class="palette-foot"><kbd>↑</kbd><kbd>↓</kbd> выбрать <span>·</span> <kbd>Enter</kbd> открыть <span>·</span> <kbd>Ctrl K</kbd> закрыть</p>
      </div>`;
    document.body.appendChild(overlay);

    input = overlay.querySelector("#paletteInput");
    list = overlay.querySelector("#paletteList");

    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) return close();
      const button = event.target.closest(".palette-item");
      if (button) activate(Number(button.dataset.index));
    });

    overlay.addEventListener("mousemove", (event) => {
      const button = event.target.closest(".palette-item");
      if (!button) return;
      const index = Number(button.dataset.index);
      if (index !== active) setActive(index);
    });

    input.addEventListener("input", () => schedule(input.value));
    input.addEventListener("keydown", (event) => {
      if (event.key === "Tab") {
        event.preventDefault();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        move(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        move(-1);
      } else if (event.key === "Enter") {
        event.preventDefault();
        if (active >= 0) activate(active);
        else if (items.length) activate(0);
      } else if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
    });
  }

  function toolEntries(query) {
    const needle = query.trim().toLowerCase();
    const list = (Hub.tools || [])
      .filter((tool) => !needle || `${tool.name} ${tool.hint || ""}`.toLowerCase().includes(needle))
      .map((tool) => ({ kind: "tool", tool }));

    const settingsWords = ["настройки", "параметры", "тема", "стекло", "звук", "акцент", "settings", "options"];
    if (!needle || settingsWords.some((w) => needle.includes(w) || w.includes(needle))) {
      list.push({
        kind: "settings",
        title: "Настройки Hub",
        hint: "Оформление, стекло Fluent, микро-звуки, автозапуск (Ctrl+,)",
      });
    }
    return list;
  }

  function setGroups(next) {
    groups = next.filter((group) => group.items.length > 0);
    items = groups.flatMap((group) => group.items);
    active = items.length ? 0 : -1;
    render();
  }

  function itemMarkup(item, index) {
    let title = "";
    let meta = "";
    let iconKind = item.kind;
    if (item.kind === "tool") {
      title = item.tool.name;
      meta = item.tool.hint || "";
    } else if (item.kind === "settings") {
      title = item.title;
      meta = item.hint || "";
      iconKind = "settings";
    } else if (item.kind === "note") {
      title = item.note.title || "Без заголовка";
      meta = item.note.snippet || "";
    } else {
      iconKind = "clipboard";
      title = item.clip.snippet || "";
      meta = item.clip.pinned ? "закреплено в буфере" : "из истории буфера";
    }
    return `
      <button class="palette-item" type="button" role="option" id="paletteItem${index}" aria-selected="false" data-index="${index}">
        ${icon(iconKind)}
        <span class="palette-text">
          <span class="palette-title">${Hub.escapeHtml(title)}</span>
          ${meta ? `<span class="palette-meta">${Hub.escapeHtml(meta)}</span>` : ""}
        </span>
      </button>`;
  }

  function render() {
    if (!items.length) {
      list.innerHTML = `<p class="palette-empty">${lastQuery.trim() ? "Ничего не нашлось. Попробуй другое слово." : "Начни печатать — поищу по инструментам, заметкам и буферу."}</p>`;
      input.removeAttribute("aria-activedescendant");
      return;
    }
    let index = 0;
    list.innerHTML = groups
      .map((group) => {
        const rows = group.items.map((item) => itemMarkup(item, index++)).join("");
        return `<p class="palette-group">${Hub.escapeHtml(group.title)}</p>${rows}`;
      })
      .join("");
    setActive(active);
  }

  function setActive(index) {
    active = index;
    const buttons = [...list.querySelectorAll(".palette-item")];
    buttons.forEach((button, position) => {
      const picked = position === index;
      button.classList.toggle("is-active", picked);
      button.setAttribute("aria-selected", String(picked));
    });
    const current = buttons[index];
    if (current) {
      input.setAttribute("aria-activedescendant", current.id);
      current.scrollIntoView({ block: "nearest" });
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function move(step) {
    if (!items.length) return;
    const next = (active + step + items.length) % items.length;
    setActive(next);
  }

  function activate(index) {
    const item = items[index];
    if (!item) return;
    const query = lastQuery.trim();
    close();
    if (item.kind === "tool") {
      location.hash = `#/${item.tool.id}`;
      return;
    }
    if (item.kind === "settings") {
      if (typeof Hub.openSettings === "function") Hub.openSettings();
      return;
    }
    if (item.kind === "note") Hub.searchIn("notes", query);
    else if (item.kind === "clip") Hub.searchIn("clipboard", query);
  }

  function schedule(query) {
    lastQuery = query;
    clearTimeout(timer);
    const needle = query.trim();
    if (!needle) {
      seq += 1;
      setGroups([{ title: "Инструменты", items: toolEntries("") }]);
      return;
    }
    setGroups([{ title: "Инструменты", items: toolEntries(needle) }]);
    timer = setTimeout(() => search(needle), SEARCH_DELAY);
  }

  async function search(needle) {
    const token = ++seq;
    let data;
    try {
      data = await Hub.api(`/api/search?q=${encodeURIComponent(needle)}`);
    } catch (error) {
      if (opened && token === seq) Hub.toast(error.message);
      return;
    }
    if (!opened || token !== seq || lastQuery.trim() !== needle) return;
    const toolHits = (data.tools || []).map((tool) => ({ kind: "tool", tool }));
    const noteHits = (data.notes || []).map((note) => ({ kind: "note", note }));
    const clipHits = (data.clipboard || []).map((clip) => ({ kind: "clip", clip }));
    setGroups([
      { title: "Инструменты", items: toolHits },
      { title: "Заметки", items: noteHits },
      { title: "Буфер обмена", items: clipHits },
    ]);
  }

  function open() {
    if (!overlay) build();
    if (opened) return;
    if (document.querySelector("#settingsModal")?.classList.contains("hidden") === false) Hub.closeSettings();
    if (document.querySelector(".shell")?.inert) return;
    opened = true;
    previousFocus = document.activeElement;
    overlay.classList.remove("hidden");
    const shell = document.querySelector(".shell");
    if (shell) shell.inert = true;
    input.value = "";
    lastQuery = "";
    seq += 1;
    setGroups([{ title: "Инструменты", items: toolEntries("") }]);
    input.focus();
  }

  function close() {
    if (!opened) return;
    opened = false;
    clearTimeout(timer);
    seq += 1;
    overlay.classList.add("hidden");
    const shell = document.querySelector(".shell");
    if (shell) shell.inert = false;
    if (previousFocus && previousFocus.isConnected) previousFocus.focus();
    previousFocus = null;
  }

  function toggle() {
    if (opened) close();
    else open();
  }

  function onKeydown(event) {
    const key = String(event.key || "").toLowerCase();
    if ((event.ctrlKey || event.metaKey) && !event.altKey && (key === "k" || event.code === "KeyK")) {
      event.preventDefault();
      toggle();
      return;
    }
    if (event.key === "Escape" && opened) {
      event.preventDefault();
      close();
    }
  }

  window.HubPalette = {
    init() {
      if (!overlay) build();
      document.addEventListener("keydown", onKeydown);
      return this;
    },
    open,
    close,
    toggle,
  };
})();
