/* Инструмент «Главная» — дашборд и сводка дня */

(function () {
  const TEMPLATE = `
    <section class="card home-hero">
      <div class="home-hero-info">
        <h2 id="homeGreeting">Добрый день!</h2>
        <p id="homeDate">Загрузка данных…</p>
      </div>
      <div class="home-hero-status">
        <span class="pill pill-good" id="homeStatusPill">● Всё работает штатно</span>
      </div>
    </section>

    <div class="home-grid">
      <!-- Виджет 1: Компьютер прямо сейчас -->
      <section class="card home-widget" id="homeWidgetMonitor">
        <div class="home-widget-head">
          <span class="home-widget-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 12.5h4l2.2-6 3.4 11 2.4-7.2 1.8 2.2H21"/></svg>
            Мониторинг ПК
          </span>
          <a class="home-link" href="#/monitor">Подробнее →</a>
        </div>
        <div class="home-vitals">
          <div class="home-vital-card">
            <span class="about-label">Процессор</span>
            <span class="home-vital-val" id="homeCpuVal">—</span>
            <span class="about-sub">текущая загрузка</span>
          </div>
          <div class="home-vital-card">
            <span class="about-label">Оперативная память</span>
            <span class="home-vital-val" id="homeRamVal">—</span>
            <span class="about-sub" id="homeRamSub">памяти занято</span>
          </div>
        </div>
      </section>

      <!-- Виджет 2: Быстрое действие -->
      <section class="card home-widget">
        <div class="home-widget-head">
          <span class="home-widget-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 5.5v13M5.5 12h13"/></svg>
            Быстрое действие
          </span>
        </div>
        <input type="text" id="homeQuickInput" class="home-quick-input" placeholder="Введи текст, заметку или ссылку…" autocomplete="off">
        <div class="home-quick-actions">
          <button class="btn primary small" id="homeBtnAddNote" type="button">Создать заметку</button>
          <button class="btn ghost small" id="homeBtnAddClip" type="button">Скопировать в буфер</button>
          <a class="btn ghost small" href="#/images">Сжать картинку →</a>
        </div>
      </section>

      <!-- Виджет 3: Дела и To-Do -->
      <section class="card home-widget" id="homeWidgetTodos">
        <div class="home-widget-head">
          <span class="home-widget-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="4.5" y="3.5" width="15" height="17" rx="3"/><path d="M8 8.5h8M8 12h8M8 15.5h5"/></svg>
            Задачи To-Do
          </span>
          <a class="home-link" href="#/notes">Все заметки →</a>
        </div>
        <div class="home-todo-list" id="homeTodoList">
          <p class="about-sub">Загрузка задач…</p>
        </div>
      </section>

      <!-- Виджет 4: Буфер обмена -->
      <section class="card home-widget" id="homeWidgetClip">
        <div class="home-widget-head">
          <span class="home-widget-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="6" y="4.5" width="12" height="16" rx="2.5"/><path d="M9.5 4.5V3.6A1.1 1.1 0 0 1 10.6 2.5h2.8a1.1 1.1 0 0 1 1.1 1.1v.9"/><path d="M9 10h6M9 13.5h6M9 17h3.5"/></svg>
            Недавнее в буфере
          </span>
          <a class="home-link" href="#/clipboard">История буфера →</a>
        </div>
        <div class="home-clip-list" id="homeClipList">
          <p class="about-sub">Загрузка истории…</p>
        </div>
      </section>
    </div>`;

  const COPY_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="8.5" y="8.5" width="11" height="11" rx="2.2"/><path d="M15.5 5.5H6.6A2.1 2.1 0 0 0 4.5 7.6v8.9"/></svg>';

  window.HubTools.home = {
    mount(root) {
      root.innerHTML = TEMPLATE;

      const $ = (selector) => root.querySelector(selector);
      const escape = Hub.escapeHtml;

      const state = {
        data: null,
        closed: false,
      };

      // Приветствие по времени суток
      const hour = new Date().getHours();
      let greeting = "Добрый день!";
      if (hour >= 5 && hour < 12) greeting = "Доброе утро!";
      else if (hour >= 18 && hour < 23) greeting = "Добрый вечер!";
      else if (hour >= 23 || hour < 5) greeting = "Доброй ночи!";
      $("#homeGreeting").textContent = greeting;

      const now = new Date();
      const options = { weekday: "long", year: "numeric", month: "long", day: "numeric" };
      const dateStr = now.toLocaleDateString("ru-RU", options);
      $("#homeDate").textContent = `${dateStr.charAt(0).toUpperCase() + dateStr.slice(1)} · Hub v${Hub.version || "1.3.0"}`;

      async function loadSummary() {
        try {
          const data = await Hub.api("/api/home/summary");
          if (state.closed) return;
          state.data = data;
          render(data);
        } catch {
          if (!state.closed) {
            $("#homeDate").textContent = "Локальный сайт готов к работе";
          }
        }
      }

      function render(data) {
        if (!data) return;

        // Мониторинг
        if (data.vitals) {
          const cpu = Math.round(data.vitals.cpu_percent || 0);
          const ram = Math.round(data.vitals.memory_percent || 0);
          $("#homeCpuVal").textContent = `${cpu}%`;
          $("#homeRamVal").textContent = `${ram}%`;
          if (data.vitals.memory_used_gb) {
            $("#homeRamSub").textContent = `${data.vitals.memory_used_gb} из ${data.vitals.memory_total_gb || "?"} ГБ`;
          }
        }

        // Задачи To-Do
        const todoList = $("#homeTodoList");
        if (Array.isArray(data.todos) && data.todos.length > 0) {
          todoList.innerHTML = data.todos
            .slice(0, 5)
            .map(
              (todo) => `
                <div class="home-todo-item" data-note-id="${escape(todo.note_id)}" data-line="${todo.line_idx}">
                  <input type="checkbox" data-act="check-todo" title="Отметить выполненным">
                  <span>${escape(todo.text)}</span>
                  <span class="home-todo-source">${escape(todo.note_title)}</span>
                </div>`,
            )
            .join("");
        } else {
          todoList.innerHTML = '<p class="about-sub">Все дела выполнены! Добавь список в «Заметках» через <code>- [ ] задача</code>.</p>';
        }

        // Буфер обмена
        const clipList = $("#homeClipList");
        if (Array.isArray(data.recent_clips) && data.recent_clips.length > 0) {
          clipList.innerHTML = data.recent_clips
            .slice(0, 3)
            .map(
              (item) => `
                <div class="home-clip-item" data-id="${escape(item.id)}">
                  <span class="home-clip-text" title="${escape(item.preview)}">${escape(item.preview)}</span>
                  <button class="mini-btn" type="button" data-act="copy-clip" title="Скопировать">${COPY_ICON}</button>
                </div>`,
            )
            .join("");
        } else {
          clipList.innerHTML = '<p class="about-sub">История буфера пуста. Скопируй любой текст.</p>';
        }
      }

      // Слушатели событий
      $("#homeTodoList").addEventListener("click", async (e) => {
        const checkbox = e.target.closest("input[data-act='check-todo']");
        if (!checkbox) return;
        const item = checkbox.closest(".home-todo-item");
        if (!item) return;

        const noteId = item.dataset.noteId;
        const lineIdx = Number(item.dataset.line);

        try {
          const notesData = await Hub.api("/api/notes/items");
          const note = (notesData.items || []).find((n) => n.id === noteId);
          if (note) {
            const lines = note.text.split("\n");
            if (lines[lineIdx] != null) {
              lines[lineIdx] = lines[lineIdx].replace(/^-\s+\[\s*\]/, "- [x]");
              await Hub.api("/api/notes/update", {
                id: note.id,
                title: note.title,
                text: lines.join("\n"),
              });
              if (Hub.playSound) Hub.playSound("check");
              Hub.toast("Задача выполнена!");
              loadSummary();
            }
          }
        } catch (err) {
          Hub.toast(err.message);
        }
      });

      $("#homeClipList").addEventListener("click", async (e) => {
        const btn = e.target.closest("button[data-act='copy-clip']");
        if (!btn) return;
        const item = btn.closest(".home-clip-item");
        if (!item) return;
        try {
          await Hub.api("/api/clipboard/copy", { id: item.dataset.id });
          if (Hub.playSound) Hub.playSound("copy");
          Hub.toast("Скопировано из буфера!");
        } catch (err) {
          Hub.toast(err.message);
        }
      });

      // Быстрое действие
      $("#homeBtnAddNote").addEventListener("click", async () => {
        const input = $("#homeQuickInput");
        const text = input.value.trim();
        if (!text) {
          Hub.toast("Введи текст для заметки");
          return;
        }
        try {
          await Hub.api("/api/notes/create", { title: "", text });
          input.value = "";
          if (Hub.playSound) Hub.playSound("check");
          Hub.toast("Заметка создана!");
          loadSummary();
        } catch (err) {
          Hub.toast(err.message);
        }
      });

      $("#homeBtnAddClip").addEventListener("click", async () => {
        const input = $("#homeQuickInput");
        const text = input.value.trim();
        if (!text) {
          Hub.toast("Введи текст");
          return;
        }
        try {
          await Hub.api("/api/clipboard/add", { text });
          input.value = "";
          if (Hub.playSound) Hub.playSound("copy");
          Hub.toast("Текст сохранён и скопирован!");
          loadSummary();
        } catch (err) {
          Hub.toast(err.message);
        }
      });

      loadSummary();

      return () => {
        state.closed = true;
      };
    },
  };
})();
