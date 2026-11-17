/* Инструмент «Буфер обмена» */

(function () {
  const PIN_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4h6M12 4v6.2l3.5 3.4a1 1 0 0 1 .3.7V16H8.2v-1.7a1 1 0 0 1 .3-.7L12 10.2z"/><path d="M12 16v4.5"/></svg>';
  const TRASH_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 7h15M9.5 7V5.5A1.5 1.5 0 0 1 11 4h2a1.5 1.5 0 0 1 1.5 1.5V7"/><path d="M6.5 7l.8 11a2 2 0 0 0 2 1.9h5.4a2 2 0 0 0 2-1.9L17.5 7"/><path d="M10.5 11v5M13.5 11v5"/></svg>';
  const COPY_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="8.5" y="8.5" width="11" height="11" rx="2.2"/><path d="M15.5 5.5H6.6A2.1 2.1 0 0 0 4.5 7.6v8.9"/></svg>';
  const PAUSE_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9.5 5.5v13M14.5 5.5v13"/></svg>';
  const PLAY_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7.5 5.4 18 12 7.5 18.6z"/></svg>';

  function cardMarkup(item) {
    const escape = Hub.escapeHtml;
    const chars = `${item.chars} ${Hub.plural(item.chars, "символ", "символа", "символов")}`;
    return `
      <article class="clip ${item.pinned ? "is-pinned" : ""}" data-id="${escape(item.id)}">
        <button class="clip-body" type="button" data-act="copy" title="Скопировать снова">
          <span class="clip-text">${escape(item.preview)}</span>
          <span class="clip-meta">
            <span class="clip-time">${Hub.timeAgo(item.time)}</span>
            <span class="clip-dot">·</span>
            <span>${chars}</span>
            ${item.pinned ? '<span class="clip-badge">закреплено</span>' : ""}
          </span>
        </button>
        <div class="clip-tools">
          <button class="mini-btn" type="button" data-act="pin" aria-label="${item.pinned ? "Открепить" : "Закрепить"}" title="${item.pinned ? "Открепить" : "Закрепить"}">${PIN_ICON}</button>
          <button class="mini-btn" type="button" data-act="copy" aria-label="Скопировать" title="Скопировать">${COPY_ICON}</button>
          <button class="mini-btn danger" type="button" data-act="delete" aria-label="Удалить" title="Удалить">${TRASH_ICON}</button>
        </div>
      </article>`;
  }

  window.HubTools.clipboard = {
    mount(root) {
      root.innerHTML = `
        <section class="clip-toolbar">
          <div class="search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
              <circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/>
            </svg>
            <input id="clipSearch" type="search" placeholder="Поиск по скопированному…" autocomplete="off" aria-label="Поиск по истории буфера">
          </div>
          <button class="btn ghost small" id="clipPause" type="button" title="Перестать записывать новый текст">${PAUSE_ICON}<span>Пауза</span></button>
          <button class="btn ghost small" id="clipClear" type="button">Очистить</button>
        </section>

        <p class="clip-status" id="clipStatus"></p>

        <div class="clip-list" id="clipList"></div>

        <div class="clip-empty hidden" id="clipEmpty">
          <div class="empty-art clip-art" aria-hidden="true">
            <div class="empty-folder">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                <rect x="6" y="4.5" width="12" height="16" rx="2.5"/>
                <path d="M9.5 4.5V3.6A1.1 1.1 0 0 1 10.6 2.5h2.8a1.1 1.1 0 0 1 1.1 1.1v.9"/>
                <path d="M9 10h6M9 13.5h6M9 17h3.5"/>
              </svg>
            </div>
          </div>
          <h2 id="clipEmptyTitle">Пока пусто</h2>
          <p id="clipEmptyText">Скопируй любой текст — и он появится здесь. Всё хранится на этом компьютере.</p>
        </div>`;

      const list = root.querySelector("#clipList");
      const empty = root.querySelector("#clipEmpty");
      const status = root.querySelector("#clipStatus");
      const pauseButton = root.querySelector("#clipPause");
      const searchInput = root.querySelector("#clipSearch");

      let query = "";
      let paused = false;
      let items = [];
      let signature = "";
      let pollTimer = null;
      let searchTimer = null;
      let stopped = false;

      function render() {
        if (items.length === 0) {
          list.innerHTML = "";
          list.classList.add("hidden");
          empty.classList.remove("hidden");
          const hasQuery = query.trim() !== "";
          root.querySelector("#clipEmptyTitle").textContent = hasQuery ? "Ничего не нашлось" : "Пока пусто";
          root.querySelector("#clipEmptyText").textContent = hasQuery
            ? "Попробуй другой запрос — поиск идёт по тексту записей."
            : "Скопируй любой текст — и он появится здесь. Всё хранится на этом компьютере.";
          return;
        }
        empty.classList.add("hidden");
        list.classList.remove("hidden");
        list.innerHTML = items.map(cardMarkup).join("");
      }

      function renderStatus(total) {
        const records = `${total} ${Hub.plural(total, "запись", "записи", "записей")}`;
        status.textContent = paused
          ? `Запись на паузе · в истории ${records}`
          : `История: ${records} · обновляется автоматически`;
        status.classList.toggle("is-paused", paused);
      }

      async function refresh(force = false) {
        if (stopped) return;
        try {
          const data = await Hub.api(`/api/clipboard/items?limit=200&q=${encodeURIComponent(query)}`);
          paused = Boolean(data.paused);
          const nextSignature = JSON.stringify(data.items);
          if (force || nextSignature !== signature) {
            signature = nextSignature;
            items = data.items || [];
            render();
          }
          renderStatus(data.total || 0);
          syncPauseButton();
        } catch (error) {
          status.textContent = error.message;
          status.classList.add("is-paused");
        }
      }

      function syncPauseButton() {
        pauseButton.innerHTML = paused ? `${PLAY_ICON}<span>Продолжить</span>` : `${PAUSE_ICON}<span>Пауза</span>`;
        pauseButton.classList.toggle("is-active", paused);
      }

      async function act(action, id) {
        try {
          if (action === "copy") {
            await Hub.api("/api/clipboard/copy", { id });
            Hub.toast("Скопировано — можно вставлять");
          } else if (action === "pin") {
            await Hub.api("/api/clipboard/pin", { id });
          } else if (action === "delete") {
            await Hub.api("/api/clipboard/delete", { id });
          }
          await refresh(true);
        } catch (error) {
          Hub.toast(error.message);
        }
      }

      pauseButton.addEventListener("click", async () => {
        try {
          const next = !paused;
          await Hub.api("/api/clipboard/pause", { paused: next });
          paused = next;
          syncPauseButton();
          renderStatus(items.length);
          Hub.toast(next ? "Запись остановлена — новый текст не сохраняется" : "Запись снова включена");
          await refresh(true);
        } catch (error) {
          Hub.toast(error.message);
        }
      });

      root.querySelector("#clipClear").addEventListener("click", async () => {
        const confirmed = await Hub.confirm({
          title: "Очистить историю?",
          text: "Все записи, включая закреплённые, исчезнут с этого компьютера. Отменить это нельзя.",
          confirmText: "Очистить",
          danger: true,
        });
        if (!confirmed) return;
        try {
          await Hub.api("/api/clipboard/clear", {});
          Hub.toast("История очищена");
          await refresh(true);
        } catch (error) {
          Hub.toast(error.message);
        }
      });

      list.addEventListener("click", (event) => {
        const button = event.target.closest("[data-act]");
        if (!button) return;
        const card = button.closest(".clip");
        if (!card) return;
        act(button.dataset.act, card.dataset.id);
      });

      searchInput.addEventListener("input", () => {
        query = searchInput.value;
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => refresh(true), 180);
      });

      function schedule() {
        if (stopped) return;
        pollTimer = setTimeout(async () => {
          await refresh(false);
          schedule();
        }, 2000);
      }

      Hub.setSearchHook("clipboard", (value) => {
        query = value || "";
        searchInput.value = query;
        refresh(true);
        searchInput.focus();
        return true;
      });

      const pendingSearch = Hub.takeSearch("clipboard");
      if (pendingSearch) {
        query = pendingSearch;
        searchInput.value = pendingSearch;
      }

      refresh(true);
      schedule();

      return () => {
        stopped = true;
        clearTimeout(pollTimer);
        clearTimeout(searchTimer);
        Hub.clearSearchHook("clipboard");
      };
    },
  };
})();
