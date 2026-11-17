/* Инструмент «Корзина»: что инструменты убрали с диска и что ещё можно вернуть */

(function () {
  const SOURCES = {
    cleanup: "Уборка",
    diskmap: "Карта диска",
    bigfiles: "Большие файлы",
    duplicates: "Дубликаты",
    // Журналы, созданные до 1.1, не писали источник; из инструментов это были дубликаты.
    "": "Дубликаты",
  };

  const ICONS = {
    file: '<path d="M6 3.5h7.5L19 9v11.5H6z"/><path d="M13.5 3.5V9H19"/>',
    dir: '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/>',
  };

  const TEMPLATE = `
    <section class="card trash-bar">
      <div class="picker-head">
        <h2>Корзина хаба</h2>
        <span class="pill pill-quiet" id="trashTotals">пусто</span>
      </div>
      <p class="hint">Здесь лежит всё, что инструменты убрали с диска. Это не корзина Windows: файлы целы, пока ты сам не очистишь корзину. Пока перенос здесь — его можно вернуть на место.</p>
      <div class="trash-actions">
        <button class="btn ghost small" id="trashReload" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M20 4.5V10h-5.5"/>
          </svg>
          Обновить
        </button>
        <button class="btn danger small" id="trashEmpty" type="button" disabled>Очистить корзину</button>
      </div>
    </section>

    <div class="trash-list" id="trashList" aria-live="polite"></div>

    <section class="empty-state hidden" id="trashBlank">
      <div class="empty-art" aria-hidden="true">
        <div class="empty-folder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 7h14l-1.2 12.2a1.8 1.8 0 0 1-1.8 1.6H8a1.8 1.8 0 0 1-1.8-1.6z"/>
            <path d="M9.5 7V5.4A1.4 1.4 0 0 1 10.9 4h2.2a1.4 1.4 0 0 1 1.4 1.4V7"/>
          </svg>
        </div>
      </div>
      <h2>Корзина пуста</h2>
      <p>Всё, что убирают инструменты хаба, попадает сюда. Пока тут ничего нет — возвращать нечего.</p>
    </section>`;

  window.HubTools.trash = {
    mount(root) {
      root.innerHTML = TEMPLATE;

      const $ = (selector) => root.querySelector(selector);
      const escape = Hub.escapeHtml;
      const plural = Hub.plural;

      const state = {
        runs: [],
        busy: false,
        closed: false,
      };

      /* --- помощники --- */

      function sourceName(run) {
        const key = String(run.source || "");
        return SOURCES[key] || "Удаление файлов";
      }

      function fmtWhen(timestamp) {
        const date = new Date((Number(timestamp) || 0) * 1000);
        if (Number.isNaN(date.getTime()) || !date.getTime()) return "";
        const time = date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
        const today = new Date();
        const dayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate());
        const runStart = new Date(date.getFullYear(), date.getMonth(), date.getDate());
        const days = Math.round((dayStart - runStart) / 86400000);
        if (days === 0) return `сегодня, ${time}`;
        if (days === 1) return `вчера, ${time}`;
        const day = date.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
        return `${day}, ${time}`;
      }

      function folderOf(run) {
        return String(run.folder || "").replace(/[\\/]+$/, "");
      }

      /* --- рендер --- */

      function itemMarkup(item) {
        const kind = item.kind === "dir" ? "dir" : "file";
        return `
          <li class="trash-item">
            <span class="trash-item-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                ${ICONS[kind]}
              </svg>
            </span>
            <span class="trash-item-name">${escape(item.name)}</span>
            <span class="trash-item-size">${item.kind === "dir" ? "папка" : Hub.fmtSize(item.size)}</span>
          </li>`;
      }

      function runMarkup(run, index) {
        const count = Number(run.count) || 0;
        const size = Number(run.size) || 0;
        const items = Array.isArray(run.items) ? run.items : [];
        const more = count - items.length;
        const folder = folderOf(run);
        return `
          <article class="card trash-run" data-run="${escape(run.run_id)}" style="--row-index:${Math.min(index, 8)}">
            <div class="trash-run-head">
              <span class="trash-source">${escape(sourceName(run))}</span>
              <span class="trash-when">${escape(fmtWhen(run.time))}</span>
              <span class="pill pill-quiet">${count} ${plural(count, "штука", "штуки", "штук")} · ${Hub.fmtSize(size)}</span>
            </div>
            ${folder ? `<p class="trash-folder" title="${escape(folder)}">${escape(folder)}</p>` : ""}
            <ul class="trash-items">
              ${items.map(itemMarkup).join("")}
              ${more > 0 ? `<li class="trash-more">и ещё ${more} ${plural(more, "штука", "штуки", "штук")}</li>` : ""}
            </ul>
            <div class="trash-run-actions">
              <button class="btn ghost small" type="button" data-restore>Вернуть на место</button>
              <button class="btn danger small" type="button" data-purge>Удалить навсегда</button>
            </div>
          </article>`;
      }

      function render(data) {
        state.runs = Array.isArray(data.runs) ? data.runs : [];
        const count = Number(data.total_count) || 0;
        const size = Number(data.total_size) || 0;

        $("#trashTotals").textContent = count
          ? `${count} ${plural(count, "штука", "штуки", "штук")} · ${Hub.fmtSize(size)}`
          : "пусто";
        $("#trashEmpty").disabled = state.runs.length === 0 || state.busy;

        const list = $("#trashList");
        const blank = $("#trashBlank");
        if (!state.runs.length) {
          list.innerHTML = "";
          blank.classList.remove("hidden");
          return;
        }
        blank.classList.add("hidden");
        list.innerHTML = state.runs.map(runMarkup).join("");
      }

      function toastErrors(errors) {
        if (!errors || !errors.length) return false;
        Hub.toast(errors.map((item) => item.reason || item.path || "").filter(Boolean).join("; "));
        return true;
      }

      /* --- действия --- */

      async function load() {
        if (state.busy || state.closed) return;
        state.busy = true;
        try {
          const data = await Hub.api("/api/trash/runs");
          if (!state.closed) render(data);
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          if (!state.closed) $("#trashEmpty").disabled = state.runs.length === 0;
        }
      }

      async function reloadAfter(work, busyText) {
        state.busy = true;
        Hub.setBusy(true, busyText);
        let result = null;
        try {
          result = await work();
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
          return null;
        } finally {
          state.busy = false;
          Hub.setBusy(false);
        }
        if (state.closed || !result) return result;
        toastErrors(result.errors);
        await load();
        return result;
      }

      const clean = (result) => result && !(result.errors || []).length;

      async function restore(runId) {
        if (state.busy || state.closed) return;
        const result = await reloadAfter(
          () => Hub.api("/api/trash/restore", { run_id: runId }),
          "Возвращаю на место…"
        );
        if (clean(result) && !state.closed) Hub.toast("Всё вернулось на место");
      }

      async function purge(runId, count) {
        if (state.busy || state.closed) return;
        const confirmed = await Hub.confirm({
          title: "Удалить без возможности вернуть?",
          text: `${count} ${plural(count, "штука", "штуки", "штук")} исчезнет навсегда, без корзины. Это действие нельзя отменить.`,
          confirmText: "Удалить навсегда",
          danger: true,
        });
        if (!confirmed || state.closed) return;
        const result = await reloadAfter(
          () => Hub.api("/api/trash/purge", { run_ids: [runId], confirmed: true }),
          "Удаляю навсегда…"
        );
        if (clean(result) && !state.closed) {
          const freed = Number(result.freed) || 0;
          Hub.toast(freed ? `Удалено навсегда · освободилось ${Hub.fmtSize(freed)}` : "Удалено навсегда");
        }
      }

      async function emptyTrash() {
        if (state.busy || state.closed) return;
        const totals = $("#trashTotals").textContent;
        const confirmed = await Hub.confirm({
          title: "Очистить корзину хаба?",
          text: `В корзине: ${totals}. Всё это исчезнет навсегда, вернуть файлы будет нельзя.`,
          confirmText: "Очистить навсегда",
          danger: true,
        });
        if (!confirmed || state.closed) return;
        const result = await reloadAfter(
          () => Hub.api("/api/trash/empty", { confirmed: true }),
          "Очищаю корзину…"
        );
        if (clean(result) && !state.closed) {
          const freed = Number(result.freed) || 0;
          Hub.toast(freed ? `Корзина пуста · освободилось ${Hub.fmtSize(freed)}` : "Корзина пуста");
        }
      }

      /* --- события --- */

      $("#trashList").addEventListener("click", (event) => {
        const button = event.target.closest("button");
        if (!button) return;
        const card = button.closest(".trash-run");
        if (!card) return;
        const run = state.runs.find((item) => item.run_id === card.dataset.run);
        if (!run) return;
        if (button.hasAttribute("data-restore")) restore(run.run_id);
        else if (button.hasAttribute("data-purge")) purge(run.run_id, Number(run.count) || 0);
      });

      $("#trashReload").addEventListener("click", load);
      $("#trashEmpty").addEventListener("click", emptyTrash);

      load();

      return () => {
        state.closed = true;
        Hub.dismissDialog();
      };
    },
  };
})();
