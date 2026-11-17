/* Инструмент «Сравнение папок» */

(function () {
  const TEMPLATE = `
    <section class="card picker">
      <div class="picker-head">
        <h2>Что с чем сравнить</h2>
        <span class="pill pill-quiet">только чтение</span>
      </div>
      <div class="compare-fields">
        <label class="compare-field">
          <span class="compare-label">Первая папка</span>
          <div class="path-field">
            <input id="cmpLeft" type="text" spellcheck="false" autocomplete="off" aria-label="Первая папка" placeholder="C:\\...">
            <button class="mini-btn" id="cmpLeftBrowse" type="button" title="Выбрать папку" aria-label="Выбрать первую папку">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/></svg>
            </button>
          </div>
        </label>
        <label class="compare-field">
          <span class="compare-label">Вторая папка</span>
          <div class="path-field">
            <input id="cmpRight" type="text" spellcheck="false" autocomplete="off" aria-label="Вторая папка" placeholder="C:\\...">
            <button class="mini-btn" id="cmpRightBrowse" type="button" title="Выбрать папку" aria-label="Выбрать вторую папку">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/></svg>
            </button>
          </div>
        </label>
      </div>
      <div class="compare-actions">
        <label class="switch">
          <input type="checkbox" id="cmpDeep">
          <span class="switch-track"><span class="switch-thumb"></span></span>
          <span class="switch-text">Сравнивать содержимое</span>
        </label>
        <button class="btn primary" id="cmpRun" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 7h7M4 17h7M13.5 7H20M13.5 17H20"/><path d="M9 4.5v5M9 14.5v5"/>
          </svg>
          Сравнить
        </button>
      </div>
      <p class="hint">Обычный режим смотрит на размер и тип. «Сравнивать содержимое» читает файлы и ловит правки того же размера — это медленнее.</p>
    </section>

    <section class="cmp-result hidden" id="cmpResult">
      <section class="stats stats-four" aria-live="polite">
        <div class="stat stat-added">
          <span class="stat-value" id="cmpStatAdded">0</span>
          <span class="stat-label">появилось</span>
        </div>
        <div class="stat stat-removed">
          <span class="stat-value" id="cmpStatRemoved">0</span>
          <span class="stat-label">пропало</span>
        </div>
        <div class="stat stat-changed">
          <span class="stat-value" id="cmpStatChanged">0</span>
          <span class="stat-label">изменилось</span>
        </div>
        <div class="stat">
          <span class="stat-value" id="cmpStatSame">0</span>
          <span class="stat-label">совпадает</span>
        </div>
      </section>

      <div class="card cmp-card">
        <nav class="chips cmp-chips" id="cmpChips" aria-label="Что показать"></nav>
        <div class="cmp-list" id="cmpList"></div>
        <p class="big-note" id="cmpNote"></p>
      </div>
    </section>

    <section class="empty-state" id="cmpEmpty">
      <div class="empty-art" aria-hidden="true">
        <div class="empty-folder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3.5" y="5" width="7" height="14" rx="2"/>
            <rect x="13.5" y="5" width="7" height="14" rx="2"/>
            <path d="M8 12h8"/>
          </svg>
        </div>
        <span class="empty-chip c1">до</span>
        <span class="empty-chip c2">после</span>
        <span class="empty-chip c3">флешка</span>
        <span class="empty-chip c4">копия</span>
      </div>
      <h2>Чем одна папка отличается от другой</h2>
      <p>Сравни копию с оригиналом, флешку с папкой или два снимка одной работы. Ничего не удаляется и не меняется — только чтение.</p>
    </section>`;

  window.HubTools.compare = {
    mount(root) {
      root.innerHTML = TEMPLATE;

      const $ = (selector) => root.querySelector(selector);
      const escape = Hub.escapeHtml;
      const plural = Hub.plural;

      const state = {
        data: null,
        filter: "all",
        busy: false,
        closed: false,
      };

      $("#cmpLeft").value = Hub.defaultFolder || "";

      /* --- помощники --- */

      function reasonText(item) {
        if (item.reason === "size") return `${Hub.fmtSize(item.left_size)} → ${Hub.fmtSize(item.right_size)}`;
        if (item.reason === "content") return "содержимое отличается";
        if (item.reason === "type") return "файл против папки";
        if (item.reason === "unreadable") return "не удалось прочитать";
        return "";
      }

      function rowsFor(filter) {
        const data = state.data;
        if (!data) return [];
        if (filter === "added") return data.added.map((item) => ({ ...item, group: "added" }));
        if (filter === "removed") return data.removed.map((item) => ({ ...item, group: "removed" }));
        if (filter === "changed") return data.changed.map((item) => ({ ...item, group: "changed" }));
        return [
          ...data.added.map((item) => ({ ...item, group: "added" })),
          ...data.removed.map((item) => ({ ...item, group: "removed" })),
          ...data.changed.map((item) => ({ ...item, group: "changed" })),
        ];
      }

      const GROUP_LABEL = {
        added: "появилось",
        removed: "пропало",
        changed: "изменилось",
      };

      function rowMarkup(item, index) {
        const meta = item.kind === "dir" ? "папка" : Hub.fmtSize(item.size ?? item.right_size ?? 0);
        return `
          <div class="cmp-row cmp-${item.group}" style="--row-index:${Math.min(index, 12)}">
            <span class="cmp-badge">${GROUP_LABEL[item.group]}</span>
            <span class="cmp-path" title="${escape(item.path)}">${escape(item.path)}</span>
            <span class="cmp-meta">${item.group === "changed" ? escape(reasonText(item)) : meta}</span>
          </div>`;
      }

      function chipMarkup(id, label, count, tone) {
        const active = state.filter === id;
        return `<button class="chip cmp-chip ${tone}" type="button" data-filter="${id}" aria-pressed="${active}">
          ${!tone ? '<span class="cmp-chip-label">Все отличия</span>' : `<span class="chip-dot"></span><span>${escape(label)}</span>`}
          <span class="chip-count">${count}</span>
        </button>`;
      }

      function renderChips() {
        const counts = state.data.counts;
        $("#cmpChips").innerHTML = [
          chipMarkup("all", "Все отличия", counts.added + counts.removed + counts.changed, ""),
          chipMarkup("added", "Появилось", counts.added, "tone-added"),
          chipMarkup("removed", "Пропало", counts.removed, "tone-removed"),
          chipMarkup("changed", "Изменилось", counts.changed, "tone-changed"),
        ].join("");
      }

      function render() {
        const data = state.data;
        if (!data) return;
        $("#cmpEmpty").classList.add("hidden");
        $("#cmpResult").classList.remove("hidden");

        $("#cmpStatAdded").textContent = String(data.counts.added);
        $("#cmpStatRemoved").textContent = String(data.counts.removed);
        $("#cmpStatChanged").textContent = String(data.counts.changed);
        $("#cmpStatSame").textContent = String(data.counts.same);

        renderChips();

        const rows = rowsFor(state.filter);
        const list = $("#cmpList");
        if (!rows.length) {
          list.innerHTML = state.filter === "all"
            ? '<p class="big-empty-row">Папки совпадают: ни одного отличия.</p>'
            : '<p class="big-empty-row">Здесь пусто.</p>';
        } else {
          list.innerHTML = rows.slice(0, 500).map(rowMarkup).join("");
        }

        const bits = [
          `Первая: ${data.left}`,
          `Вторая: ${data.right}`,
          data.deep ? "сравнивалось содержимое" : "сравнивались размер и тип",
          data.seconds < 0.15 ? "мгновенно" : `${data.seconds.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с`,
        ];
        if (data.errors?.length) bits.push(`${data.errors.length} ${plural(data.errors.length, "ошибка", "ошибки", "ошибок")} доступа`);
        if (data.truncated) bits.push("папки слишком большие — часть не сравнена");
        if (rows.length > 500) bits.push(`показаны первые 500 из ${rows.length}`);
        $("#cmpNote").textContent = bits.join(" · ");
      }

      /* --- сеть --- */

      async function run() {
        if (state.busy || state.closed) return;
        const left = $("#cmpLeft").value.trim();
        const right = $("#cmpRight").value.trim();
        if (!left || !right) {
          Hub.toast("Нужны обе папки");
          (!left ? $("#cmpLeft") : $("#cmpRight")).focus();
          return;
        }
        state.busy = true;
        Hub.setBusy(true, $("#cmpDeep").checked ? "Читаю и сравниваю файлы…" : "Сравниваю папки…");
        try {
          const data = await Hub.api("/api/compare/run", { left, right, deep: $("#cmpDeep").checked });
          if (state.closed) return;
          state.data = data;
          state.filter = "all";
          render();
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          Hub.setBusy(false);
        }
      }

      async function browse(input) {
        try {
          const result = await Hub.api("/api/pick-folder", { initial: input.value.trim() });
          if (result.folder) input.value = result.folder;
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        }
      }

      /* --- события --- */

      $("#cmpRun").addEventListener("click", run);
      [$("#cmpLeft"), $("#cmpRight")].forEach((input) => {
        input.addEventListener("keydown", (event) => {
          if (event.key === "Enter") run();
        });
      });

      $("#cmpLeftBrowse").addEventListener("click", () => browse($("#cmpLeft")));
      $("#cmpRightBrowse").addEventListener("click", () => browse($("#cmpRight")));

      $("#cmpChips").addEventListener("click", (event) => {
        const chip = event.target.closest("[data-filter]");
        if (!chip) return;
        state.filter = chip.dataset.filter;
        render();
      });

      $("#cmpDeep").addEventListener("change", () => {
        if (state.data) run();
      });

      return () => {
        state.closed = true;
        Hub.dismissDialog();
      };
    },
  };
})();
