/* Инструмент «Заметки» */

(function () {
  const TEMPLATE = `
    <section class="card notes-bar">
      <div class="notes-search">
        <svg class="path-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>
        </svg>
        <input id="notesQuery" type="search" placeholder="Найти по словам" spellcheck="false" autocomplete="off" aria-label="Поиск по заметкам">
      </div>
      <div class="notes-actions">
        <button class="btn ghost" id="notesExportAll" type="button" title="Экспортировать заметки">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Экспорт
        </button>
        <button class="btn primary" id="notesNew" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="M12 5.5v13M5.5 12h13"/>
          </svg>
          Новая заметка
        </button>
      </div>
    </section>

    <section class="card note-editor hidden" id="notesEditor" aria-labelledby="noteEditorTitle">
      <div class="note-editor-head">
        <h2 id="noteEditorTitle">Новая заметка</h2>
        <span class="pill pill-quiet" id="noteEditorCount">0 символов</span>
      </div>
      <input id="noteTitle" class="note-title-input" type="text" maxlength="120" placeholder="Заголовок — можно не заполнять" autocomplete="off">
      <textarea id="noteText" class="note-text-input" rows="6" placeholder="Что нужно запомнить"></textarea>
      <div class="note-editor-actions">
        <button class="btn ghost" id="noteCancel" type="button">Отмена</button>
        <button class="btn primary" id="noteSave" type="button">Сохранить</button>
      </div>
    </section>

    <div id="notesGrid" class="notes-grid"></div>

    <section class="empty-state" id="notesEmpty">
      <div class="empty-art" aria-hidden="true">
        <div class="empty-folder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <rect x="4.5" y="3.5" width="15" height="17" rx="3"/>
            <path d="M8 8.5h8M8 12h8M8 15.5h5"/>
          </svg>
        </div>
        <span class="empty-chip c1">список покупок</span>
        <span class="empty-chip c2">идея</span>
        <span class="empty-chip c3">пароль не сюда</span>
        <span class="empty-chip c4">домашка</span>
      </div>
      <h2>Короткие записи, которые не потеряются</h2>
      <p>Заметки лежат в одном файле на этом компьютере и никуда не отправляются. Заголовок не обязателен.</p>
    </section>`;

  const PIN_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3.5h6M12 3.5v6.2M12 9.7 6.5 15h11L12 9.7M12 15v5.5"/></svg>';
  const PIN_ON_ICON = '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3.5h6M12 3.5v6.2M12 9.7 6.5 15h11L12 9.7M12 15v5.5"/></svg>';
  const EDIT_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 19.5h4l9.4-9.4a2.2 2.2 0 0 0-3.1-3.1L5.4 16.4v3.1z"/></svg>';
  const EXPORT_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
  const TRASH_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 7h15M9.5 7V5.2A1.7 1.7 0 0 1 11.2 3.5h1.6a1.7 1.7 0 0 1 1.7 1.7V7M6.5 7l.8 12a1.8 1.8 0 0 0 1.8 1.7h5.8A1.8 1.8 0 0 0 16.7 19l.8-12"/></svg>';

  window.HubTools.notes = {
    mount(root) {
      root.innerHTML = TEMPLATE;

      const $ = (selector) => root.querySelector(selector);
      const escape = Hub.escapeHtml;
      const plural = Hub.plural;

      const state = {
        items: [],
        query: "",
        editing: null,
        busy: false,
        closed: false,
      };

      /* --- рендер --- */

      function fmtDate(timestamp) {
        const date = new Date((Number(timestamp) || 0) * 1000);
        if (Number.isNaN(date.getTime())) return "";
        const months = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
        return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
      }

      function visible() {
        const needle = state.query.trim().toLowerCase();
        if (!needle) return state.items;
        return state.items.filter(
          (note) => note.title.toLowerCase().includes(needle) || note.text.toLowerCase().includes(needle),
        );
      }

      function bodyMarkup(note) {
        if (!note.text) return '<p class="note-body is-empty">Без текста</p>';
        const short = note.text.length > 420 ? `${note.text.slice(0, 420)}…` : note.text;
        return `<p class="note-body">${escape(short)}</p>`;
      }

      function cardMarkup(note, index) {
        return `
          <article class="note ${note.pinned ? "is-pinned" : ""}" style="--row-index:${Math.min(index, 10)}" data-id="${escape(note.id)}">
            <header class="note-head">
              <h3 class="note-title">${escape(note.title || "Без заголовка")}</h3>
              <div class="note-tools">
                <button class="mini-btn ${note.pinned ? "is-on" : ""}" type="button" data-act="pin" title="${note.pinned ? "Открепить" : "Закрепить"}" aria-label="${note.pinned ? "Открепить заметку" : "Закрепить заметку"}" aria-pressed="${note.pinned}">${note.pinned ? PIN_ON_ICON : PIN_ICON}</button>
                <button class="mini-btn" type="button" data-act="edit" title="Изменить" aria-label="Изменить заметку">${EDIT_ICON}</button>
                <button class="mini-btn" type="button" data-act="export" title="Скачать (Markdown / TXT)" aria-label="Скачать заметку">${EXPORT_ICON}</button>
                <button class="mini-btn danger" type="button" data-act="delete" title="Удалить" aria-label="Удалить заметку">${TRASH_ICON}</button>
              </div>
            </header>
            ${bodyMarkup(note)}
            <footer class="note-foot">
              <span>${fmtDate(note.updated)}</span>
              ${note.chars ? `<span class="clip-dot" aria-hidden="true">·</span><span>${note.chars} ${plural(note.chars, "символ", "символа", "символов")}</span>` : ""}
            </footer>
          </article>`;
      }

      function render() {
        const items = visible();
        $("#notesGrid").innerHTML = items.map(cardMarkup).join("");
        const isEmpty = state.items.length === 0;
        const nothingFound = !isEmpty && items.length === 0;
        $("#notesEmpty").classList.toggle("hidden", !isEmpty && !nothingFound);
        if (nothingFound) {
          $("#notesEmpty").querySelector("h2").textContent = "Ничего не нашлось";
          $("#notesEmpty").querySelector("p").textContent = "Попробуй другое слово или очисти поиск.";
        } else if (isEmpty) {
          $("#notesEmpty").querySelector("h2").textContent = "Короткие записи, которые не потеряются";
          $("#notesEmpty").querySelector("p").textContent = "Заметки лежат в одном файле на этом компьютере и никуда не отправляются. Заголовок не обязателен.";
        }
      }

      function openEditor(note) {
        state.editing = note ? note.id : null;
        $("#notesEditor").classList.remove("hidden");
        $("#noteEditorTitle").textContent = note ? "Изменить заметку" : "Новая заметка";
        $("#noteTitle").value = note ? note.title : "";
        $("#noteText").value = note ? note.text : "";
        syncCount();
        $("#noteTitle").focus();
        $("#notesEditor").scrollIntoView({ behavior: "smooth", block: "nearest" });
      }

      function closeEditor() {
        state.editing = null;
        $("#notesEditor").classList.add("hidden");
        $("#noteTitle").value = "";
        $("#noteText").value = "";
      }

      function syncCount() {
        const chars = $("#noteText").value.length;
        $("#noteEditorCount").textContent = `${chars} ${plural(chars, "символ", "символа", "символов")}`;
        $("#noteSave").disabled = state.busy || (!chars && !$("#noteTitle").value.trim());
      }

      /* --- сеть --- */

      async function load() {
        try {
          const data = await Hub.api("/api/notes/items");
          if (state.closed) return;
          state.items = data.items;
          render();
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        }
      }

      async function save() {
        if (state.busy || state.closed) return;
        const title = $("#noteTitle").value.trim();
        const text = $("#noteText").value;
        if (!title && !text.trim()) {
          Hub.toast("Пустую заметку сохранять нечего");
          return;
        }
        state.busy = true;
        Hub.setBusy(true, "Сохраняю заметку…");
        try {
          const body = { title, text };
          const data = state.editing
            ? await Hub.api("/api/notes/update", { ...body, id: state.editing })
            : await Hub.api("/api/notes/create", body);
          if (state.closed) return;
          state.items = [
            data.item,
            ...state.items.filter((note) => note.id !== data.item.id),
          ];
          closeEditor();
          render();
          Hub.toast("Заметка сохранена");
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          Hub.setBusy(false);
          syncCount();
        }
      }

      async function togglePin(note) {
        if (state.busy || state.closed) return;
        state.busy = true;
        try {
          const data = await Hub.api("/api/notes/pin", { id: note.id });
          if (state.closed) return;
          state.items = state.items.map((item) => (item.id === note.id ? data.item : item));
          sortItems();
          render();
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
        }
      }

      function sortItems() {
        state.items.sort((one, two) => {
          if (one.pinned !== two.pinned) return one.pinned ? -1 : 1;
          return two.updated - one.updated;
        });
      }

      async function removeNote(note) {
        if (state.busy || state.closed) return;
        const confirmed = await Hub.confirm({
          title: "Удалить заметку?",
          text: note.title ? `«${note.title}» исчезнет навсегда.` : "Эта заметка исчезнет навсегда.",
          confirmText: "Удалить",
          danger: true,
        });
        if (!confirmed || state.closed) return;
        state.busy = true;
        try {
          await Hub.api("/api/notes/delete", { id: note.id });
          if (state.closed) return;
          state.items = state.items.filter((item) => item.id !== note.id);
          if (state.editing === note.id) closeEditor();
          render();
          Hub.toast("Заметка удалена");
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
        }
      }

      async function exportNote(note) {
        if (!note || state.closed) return;
        const choice = await Hub.choose({
          title: "Экспорт заметки",
          text: `В каком формате скачать «${escape(note.title || "Без заголовка")}»?`,
          actions: [
            { id: "md", label: "Markdown (.md)" },
            { id: "txt", label: "Текст (.txt)" },
            { id: "cancel", label: "Отмена" },
          ],
        });
        if (choice && choice !== "cancel") {
          window.location.href = `/api/notes/export?id=${encodeURIComponent(note.id)}&format=${choice}`;
        }
      }

      async function exportAll() {
        if (state.items.length === 0) {
          Hub.toast("Пока нет заметок для экспорта");
          return;
        }
        const choice = await Hub.choose({
          title: "Экспорт всех заметок",
          text: `Сохранить все ${state.items.length} ${plural(state.items.length, "заметку", "заметки", "заметок")} одним файлом?`,
          actions: [
            { id: "md", label: "Markdown (.md)" },
            { id: "txt", label: "Текст (.txt)" },
            { id: "cancel", label: "Отмена" },
          ],
        });
        if (choice && choice !== "cancel") {
          window.location.href = `/api/notes/export?format=${choice}`;
        }
      }

      /* --- события --- */

      $("#notesNew").addEventListener("click", () => openEditor(null));
      $("#notesExportAll").addEventListener("click", exportAll);
      $("#noteCancel").addEventListener("click", closeEditor);
      $("#noteSave").addEventListener("click", save);
      $("#noteText").addEventListener("input", syncCount);
      $("#noteTitle").addEventListener("input", syncCount);

      $("#notesEditor").addEventListener("keydown", (event) => {
        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
          event.preventDefault();
          save();
        }
        if (event.key === "Escape") {
          event.preventDefault();
          closeEditor();
        }
      });

      $("#notesQuery").addEventListener("input", (event) => {
        state.query = event.target.value;
        render();
      });

      $("#notesGrid").addEventListener("click", (event) => {
        const button = event.target.closest("[data-act]");
        if (!button) return;
        const card = button.closest(".note");
        const note = state.items.find((item) => item.id === card.dataset.id);
        if (!note) return;
        if (button.dataset.act === "pin") togglePin(note);
        else if (button.dataset.act === "edit") openEditor(note);
        else if (button.dataset.act === "export") exportNote(note);
        else if (button.dataset.act === "delete") removeNote(note);
      });

      Hub.setSearchHook("notes", (value) => {
        state.query = value || "";
        $("#notesQuery").value = state.query;
        render();
        $("#notesQuery").focus();
        return true;
      });

      const pendingSearch = Hub.takeSearch("notes");
      if (pendingSearch) {
        state.query = pendingSearch;
        $("#notesQuery").value = pendingSearch;
      }

      syncCount();
      load();

      return () => {
        state.closed = true;
        Hub.clearSearchHook("notes");
        Hub.dismissDialog();
      };
    },
  };
})();
