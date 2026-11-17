/* Инструмент «Сортировка файлов» */

(function () {
  const CATEGORY_COLORS = {
    "Изображения": "#f09a12",
    "Видео": "#f2506e",
    "Музыка": "#8b5cf6",
    "Документы": "#3b82f6",
    "Архивы": "#10b981",
    "Программы": "#06b6d4",
    "Код": "#6366f1",
    "Другое": "#94a3b8",
  };

  const ICONS = {
    "Изображения": '<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="m4.5 17 4.4-4.2a1.6 1.6 0 0 1 2.2 0l3 2.9M14 15l1.6-1.5a1.6 1.6 0 0 1 2.2 0l2.7 2.6"/>',
    "Видео": '<rect x="3" y="5" width="13" height="14" rx="3"/><path d="m16 10.4 3.6-2.1a1 1 0 0 1 1.4.9v5.6a1 1 0 0 1-1.4.9L16 13.6z"/>',
    "Музыка": '<path d="M9 17.5V6.2a1 1 0 0 1 .8-1l8-1.6a1 1 0 0 1 1.2 1v10.9"/><circle cx="6.5" cy="18" r="2.6"/><circle cx="16.5" cy="16" r="2.6"/>',
    "Документы": '<path d="M6 3.5h7.5L19 9v11.5H6z"/><path d="M13.5 3.5V9H19"/><path d="M9 13h6M9 16.5h4.5"/>',
    "Архивы": '<path d="M4 7.5 12 4l8 3.5v9L12 20l-8-3.5z"/><path d="M4 7.5 12 11l8-3.5M12 11v9"/>',
    "Программы": '<rect x="3" y="4.5" width="18" height="15" rx="3"/><path d="M3 9h18"/><circle cx="6.2" cy="6.8" r=".6" fill="currentColor" stroke="none"/><circle cx="8.4" cy="6.8" r=".6" fill="currentColor" stroke="none"/>',
    "Код": '<path d="m9 8-4 4 4 4M15 8l4 4-4 4M13.5 5.5l-3 13"/>',
    "Другое": '<path d="M6 3.5h7.5L19 9v11.5H6z"/><path d="M13.5 3.5V9H19"/>',
  };

  const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

  const RESULT_ICONS = {
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 6.5v7"/><path d="M12 17.2v.1"/></svg>',
  };

  const TEMPLATE = `
    <section class="card picker">
      <div class="picker-head">
        <h2>Где наводим порядок</h2>
        <span class="pill pill-quiet">по типам файлов</span>
      </div>
      <div class="field-row">
        <div class="path-field">
          <svg class="path-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/>
          </svg>
          <input id="sorterFolder" type="text" spellcheck="false" autocomplete="off" aria-label="Путь к папке">
        </div>
        <button class="btn ghost" id="sorterBrowse" type="button">Обзор…</button>
        <button class="btn primary" id="sorterScan" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/>
          </svg>
          Проверить
        </button>
      </div>
      <p class="hint">Сначала покажем демо: что и куда переедет. Файлы двигаются только после твоего подтверждения.</p>
      <div class="undo-banner hidden" id="sorterUndoBanner" role="status">
        <span class="undo-banner-text" id="sorterUndoText"></span>
        <button class="btn tiny" id="sorterUndoBtn" type="button">Отменить</button>
      </div>
    </section>

    <section class="stats hidden" id="sorterStats" aria-live="polite">
      <div class="stat">
        <span class="stat-value" id="sorterStatFiles">0</span>
        <span class="stat-label" id="sorterStatFilesLabel">файлов</span>
      </div>
      <div class="stat">
        <span class="stat-value" id="sorterStatCats">0</span>
        <span class="stat-label" id="sorterStatCatsLabel">категорий</span>
      </div>
      <div class="stat">
        <span class="stat-value" id="sorterStatSize">0 Б</span>
        <span class="stat-label">общий объём</span>
      </div>
    </section>

    <section class="preview hidden" id="sorterPreview" aria-label="Предпросмотр сортировки">
      <div class="toolbar">
        <div class="search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/>
          </svg>
          <input id="sorterSearch" type="search" placeholder="Поиск по имени файла…" autocomplete="off" aria-label="Поиск по имени файла">
        </div>
        <button class="btn ghost small" id="sorterReset" type="button" hidden>Сбросить фильтры</button>
      </div>

      <div class="chips" id="sorterChips" role="group" aria-label="Фильтр по категориям"></div>

      <div class="list-card">
        <div class="list-head">
          <label class="check" title="Выбрать всё">
            <input type="checkbox" id="sorterSelectAll" aria-label="Выбрать все файлы">
            <span class="box"></span>
          </label>
          <span class="col-name">Файл</span>
          <span class="col-size">Размер</span>
          <span class="col-dest">Переедет в</span>
        </div>

        <div class="list" id="sorterList"></div>

        <div class="list-empty hidden" id="sorterListEmpty">
          <p class="list-empty-title">По этому фильтру ничего нет</p>
          <p class="list-empty-sub">Попробуй другой запрос или сбрось фильтры.</p>
        </div>
      </div>

      <div class="actionbar" id="sorterActionbar">
        <div class="selection">
          <span class="selection-dot" aria-hidden="true"></span>
          <span>
            <strong id="sorterSelCount">0</strong>
            <span id="sorterSelText">файлов</span>
            <span class="selection-sep">·</span>
            <span id="sorterSelSize">0 Б</span>
          </span>
        </div>
        <div class="actionbar-right">
          <button class="btn ghost small" id="sorterClear" type="button">Снять всё</button>
          <button class="btn primary large" id="sorterApply" type="button" disabled>Перенести выбранные</button>
        </div>
      </div>
    </section>

    <section class="empty-state" id="sorterEmpty">
      <div class="empty-art" aria-hidden="true">
        <div class="empty-folder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/>
          </svg>
        </div>
        <span class="empty-chip c1">Изображения</span>
        <span class="empty-chip c2">Документы</span>
        <span class="empty-chip c3">Музыка</span>
        <span class="empty-chip c4">Архивы</span>
      </div>
      <h2>Начни с папки «Загрузки»</h2>
      <p>Проверим, какие файлы там лежат, и покажем аккуратный план: что в какую папку переедет. Ты отметишь нужное — остальное останется на месте.</p>
    </section>`;

  const MODAL_TEMPLATE = `
    <div class="modal hidden" id="sorterModal" role="dialog" aria-modal="true" aria-labelledby="sorterResultTitle">
      <div class="modal-card">
        <div class="result-icon" id="sorterResultIcon" aria-hidden="true"></div>
        <h2 id="sorterResultTitle">Готово</h2>
        <p class="result-text" id="sorterResultText"></p>
        <div class="result-errors hidden" id="sorterResultErrors"></div>
        <div class="modal-actions">
          <button class="btn ghost" id="sorterResultClose" type="button">Закрыть</button>
          <button class="btn ghost" id="sorterResultOpen" type="button">Открыть папку</button>
          <button class="btn primary" id="sorterResultUndo" type="button">Отменить</button>
        </div>
      </div>
    </div>`;

  window.HubTools.sorter = {
    mount(root) {
      root.innerHTML = TEMPLATE;

      const modalHost = document.createElement("div");
      modalHost.innerHTML = MODAL_TEMPLATE;
      const modal = modalHost.firstElementChild;
      document.body.appendChild(modal);

      const $ = (selector) => root.querySelector(selector);
      const escape = Hub.escapeHtml;
      const plural = Hub.plural;

      const state = {
        folder: "",
        items: [],
        counts: {},
        totalSize: 0,
        selected: new Set(),
        filter: "all",
        query: "",
        lastRun: null,
        resultRunId: null,
        busy: false,
        closed: false,
      };

      const folderInput = $("#sorterFolder");
      folderInput.value = Hub.defaultFolder || "";
      state.folder = Hub.defaultFolder || "";

      /* --- помощники --- */

      function fmtDate(timestamp) {
        const date = new Date((Number(timestamp) || 0) * 1000);
        if (Number.isNaN(date.getTime())) return "";
        return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
      }

      function iconFor(category) {
        return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${ICONS[category] || ICONS["Другое"]}</svg>`;
      }

      function colorFor(category) {
        return CATEGORY_COLORS[category] || CATEGORY_COLORS["Другое"];
      }

      function setBusy(active, text) {
        state.busy = active;
        Hub.setBusy(active, text);
        syncSelectionUI();
      }

      /* --- рендер --- */

      function visibleItems() {
        const query = state.query.trim().toLowerCase();
        return state.items.filter((item) => {
          if (state.filter !== "all" && item.category !== state.filter) return false;
          if (query && !item.name.toLowerCase().includes(query)) return false;
          return true;
        });
      }

      function syncSelectionUI() {
        const count = state.selected.size;
        const size = state.items
          .filter((item) => state.selected.has(item.id))
          .reduce((sum, item) => sum + item.size, 0);

        $("#sorterSelCount").textContent = String(count);
        $("#sorterSelText").textContent = plural(count, "файл", "файла", "файлов");
        $("#sorterSelSize").textContent = Hub.fmtSize(size);

        const button = $("#sorterApply");
        button.disabled = count === 0 || state.busy;
        button.textContent = count > 0 ? `Перенести выбранные (${count})` : "Перенести выбранные";

        const visible = visibleItems();
        const visibleSelected = visible.filter((item) => state.selected.has(item.id)).length;
        const all = $("#sorterSelectAll");
        all.checked = visible.length > 0 && visibleSelected === visible.length;
        all.indeterminate = visibleSelected > 0 && visibleSelected < visible.length;
        all.disabled = visible.length === 0;
      }

      function renderStats() {
        $("#sorterStatFiles").textContent = String(state.items.length);
        $("#sorterStatFilesLabel").textContent = plural(state.items.length, "файл", "файла", "файлов");
        const categories = Object.keys(state.counts).length;
        $("#sorterStatCats").textContent = String(categories);
        $("#sorterStatCatsLabel").textContent = plural(categories, "категория", "категории", "категорий");
        $("#sorterStatSize").textContent = Hub.fmtSize(state.totalSize);
      }

      function renderChips() {
        const total = state.items.length;
        const parts = [
          `<button class="chip" type="button" data-cat="all" aria-pressed="${state.filter === "all"}" style="--dot:#8b93a5">
             Все <span class="chip-count">${total}</span>
           </button>`,
        ];

        Object.keys(state.counts)
          .sort((a, b) => state.counts[b] - state.counts[a])
          .forEach((category) => {
            parts.push(
              `<button class="chip" type="button" data-cat="${escape(category)}" aria-pressed="${state.filter === category}" style="--dot:${colorFor(category)}">
                 <span class="chip-dot"></span>${escape(category)}
                 <span class="chip-count">${state.counts[category]}</span>
               </button>`,
            );
          });

        $("#sorterChips").innerHTML = parts.join("");
      }

      function rowMarkup(item, index, animate) {
        const checked = state.selected.has(item.id);
        const color = colorFor(item.category);
        const delay = animate ? `--i:${Math.min(index, 24)}` : "";

        return `
          <label class="row ${checked ? "" : "is-off"}" data-id="${item.id}" style="--c:${color};${delay}" title="${escape(item.dest_rel)}">
            <span class="check">
              <input type="checkbox" ${checked ? "checked" : ""} aria-label="Выбрать ${escape(item.name)}">
              <span class="box"></span>
            </span>
            <span class="row-main">
              <span class="row-icon">${iconFor(item.category)}</span>
              <span class="row-text">
                <span class="row-name">${escape(item.name)}</span>
                <span class="row-meta">${fmtDate(item.mtime)}${item.renamed ? " · имя занято, добавим номер" : ""}</span>
              </span>
            </span>
            <span class="row-size">${Hub.fmtSize(item.size)}</span>
            <span class="row-dest">
              <span class="cat-tag" style="--c:${color}">${escape(item.category)}</span>
            </span>
          </label>`;
      }

      function renderList(animate = false) {
        const items = visibleItems();
        const list = $("#sorterList");
        list.classList.toggle("still", !animate);
        list.innerHTML = items.map((item, index) => rowMarkup(item, index, animate)).join("");

        const empty = $("#sorterListEmpty");
        empty.classList.toggle("hidden", items.length > 0);
        if (items.length === 0) {
          if (state.items.length === 0) {
            empty.querySelector(".list-empty-title").textContent = "В этой папке нет файлов";
            empty.querySelector(".list-empty-sub").textContent = "Выбери другую папку — например, «Загрузки».";
          } else {
            empty.querySelector(".list-empty-title").textContent = "По этому фильтру ничего нет";
            empty.querySelector(".list-empty-sub").textContent = "Попробуй другой запрос или сбрось фильтры.";
          }
        }

        const hasFilter = state.filter !== "all" || state.query.trim() !== "";
        $("#sorterReset").hidden = !hasFilter;

        syncSelectionUI();
      }

      function renderAll(animate = false) {
        renderStats();
        renderChips();
        renderList(animate);
      }

      function showPreview() {
        $("#sorterStats").classList.remove("hidden");
        $("#sorterPreview").classList.remove("hidden");
        $("#sorterEmpty").classList.add("hidden");
      }

      function showEmptyState(title, text) {
        $("#sorterStats").classList.add("hidden");
        $("#sorterPreview").classList.add("hidden");
        const node = $("#sorterEmpty");
        node.classList.remove("hidden");
        if (title) node.querySelector("h2").textContent = title;
        if (text) node.querySelector("p").textContent = text;
      }

      function adoptScan(data) {
        state.items = data.items || [];
        state.counts = data.counts || {};
        state.totalSize = data.total_size || 0;
        state.folder = data.folder || state.folder;
        state.selected = new Set(state.items.map((item) => item.id));
        state.filter = "all";
        state.query = "";
        $("#sorterSearch").value = "";
        folderInput.value = state.folder;

        if (state.items.length === 0) {
          showEmptyState(
            "Здесь пока нечего сортировать",
            "В этой папке нет файлов на верхнем уровне. Выбери другую папку — например, «Загрузки».",
          );
          return;
        }

        showPreview();
        renderAll(true);
      }

      async function scanFolder(silent = false) {
        const folder = folderInput.value.trim() || state.folder;
        if (!folder) {
          Hub.toast("Сначала выбери папку");
          folderInput.focus();
          return;
        }
        if (!silent) setBusy(true, "Читаю папку…");
        try {
          const data = await Hub.api("/api/sorter/scan", { folder });
          if (state.closed) return;
          adoptScan(data);
          if (!silent && data.items.length > 0) {
            Hub.toast(`Нашёл ${data.items.length} ${plural(data.items.length, "файл", "файла", "файлов")}`);
          }
        } catch (error) {
          Hub.toast(error.message);
        } finally {
          if (!silent) setBusy(false);
        }
      }

      /* --- перенос --- */

      function showResult(result) {
        const moved = result.moved_count || 0;
        const errors = result.errors || [];
        const icon = $("#sorterResultIcon");
        const title = $("#sorterResultTitle");
        const text = $("#sorterResultText");
        const warn = moved === 0 || errors.length > 0;

        icon.classList.toggle("warn", warn);
        icon.innerHTML = warn ? RESULT_ICONS.warn : RESULT_ICONS.check;

        if (moved > 0 && errors.length === 0) title.textContent = "Готово!";
        else if (moved > 0) title.textContent = "Почти всё получилось";
        else title.textContent = "Ничего не перенесено";

        if (moved > 0) {
          text.textContent = `Перенесено ${moved} ${plural(moved, "файл", "файла", "файлов")} · ${Hub.fmtSize(result.moved_size)}. Всё разложено по папкам категорий.`;
        } else {
          text.textContent = "Выбранные файлы не удалось перенести.";
        }

        const errorsBox = $("#sorterResultErrors");
        if (errors.length > 0) {
          errorsBox.classList.remove("hidden");
          errorsBox.innerHTML = errors
            .slice(0, 30)
            .map((error) => `<div><b>${escape(error.file)}</b> — ${escape(error.reason)}</div>`)
            .join("");
        } else {
          errorsBox.classList.add("hidden");
          errorsBox.innerHTML = "";
        }

        state.resultRunId = result.run_id || null;
        $("#sorterResultUndo").classList.toggle("hidden", !result.run_id);
        modal.classList.remove("hidden");
      }

      function closeResult() {
        modal.classList.add("hidden");
      }

      async function applySelected() {
        const files = state.items.filter((item) => state.selected.has(item.id)).map((item) => item.path);
        if (files.length === 0) return;

        setBusy(true, files.length > 6 ? "Переношу файлы…" : "Переношу…");
        try {
          const result = await Hub.api("/api/sorter/apply", { folder: state.folder, files });
          if (state.closed) return;
          showResult(result);
          await scanFolder(true);
          await loadLastRun();
        } catch (error) {
          Hub.toast(error.message);
        } finally {
          setBusy(false);
        }
      }

      async function doUndo(runId) {
        if (!runId) return;
        setBusy(true, "Возвращаю файлы…");
        try {
          const result = await Hub.api("/api/sorter/undo", { run_id: runId });
          closeResult();
          const count = result.restored_count || 0;
          Hub.toast(
            count > 0
              ? `Вернул ${count} ${plural(count, "файл", "файла", "файлов")} на место`
              : "Нечего возвращать",
          );
          await scanFolder(true);
          await loadLastRun();
        } catch (error) {
          Hub.toast(error.message);
        } finally {
          setBusy(false);
        }
      }

      async function loadLastRun() {
        try {
          const data = await Hub.api("/api/sorter/last-run");
          state.lastRun = data.last_run || null;
        } catch {
          state.lastRun = null;
        }
        if (state.closed) return;

        const banner = $("#sorterUndoBanner");
        if (!state.lastRun) {
          banner.classList.add("hidden");
          return;
        }
        const count = state.lastRun.count;
        $("#sorterUndoText").textContent = `Последний перенос: ${count} ${plural(count, "файл", "файла", "файлов")} · ${Hub.fmtSize(state.lastRun.size)} — можно вернуть как было.`;
        banner.classList.remove("hidden");
      }

      /* --- события --- */

      $("#sorterScan").addEventListener("click", () => scanFolder(false));
      folderInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") scanFolder(false);
      });

      $("#sorterBrowse").addEventListener("click", async () => {
        const button = $("#sorterBrowse");
        button.disabled = true;
        try {
          const result = await Hub.api("/api/sorter/pick-folder", { initial: folderInput.value.trim() });
          if (result.folder) {
            folderInput.value = result.folder;
            state.folder = result.folder;
            folderInput.focus();
          }
        } catch (error) {
          Hub.toast(error.message);
          folderInput.focus();
        } finally {
          button.disabled = false;
        }
      });

      $("#sorterSearch").addEventListener("input", (event) => {
        state.query = event.target.value;
        renderList(false);
      });

      $("#sorterChips").addEventListener("click", (event) => {
        const chip = event.target.closest(".chip");
        if (!chip) return;
        state.filter = chip.dataset.cat;
        renderChips();
        renderList(false);
      });

      $("#sorterReset").addEventListener("click", () => {
        state.filter = "all";
        state.query = "";
        $("#sorterSearch").value = "";
        renderChips();
        renderList(false);
      });

      $("#sorterSelectAll").addEventListener("change", (event) => {
        const checked = event.target.checked;
        visibleItems().forEach((item) => {
          if (checked) state.selected.add(item.id);
          else state.selected.delete(item.id);
        });
        renderList(false);
      });

      $("#sorterList").addEventListener("change", (event) => {
        const input = event.target.closest('input[type="checkbox"]');
        if (!input) return;
        const row = input.closest(".row");
        if (!row) return;
        const id = row.dataset.id;
        if (input.checked) state.selected.add(id);
        else state.selected.delete(id);
        row.classList.toggle("is-off", !input.checked);
        syncSelectionUI();
      });

      $("#sorterClear").addEventListener("click", () => {
        state.selected.clear();
        renderList(false);
      });

      $("#sorterApply").addEventListener("click", applySelected);

      $("#sorterUndoBtn").addEventListener("click", () => {
        if (state.lastRun) doUndo(state.lastRun.run_id);
      });

      $("#sorterResultClose").addEventListener("click", closeResult);
      $("#sorterResultUndo").addEventListener("click", () => doUndo(state.resultRunId));
      $("#sorterResultOpen").addEventListener("click", async () => {
        try {
          await Hub.api("/api/sorter/open", { path: state.folder });
        } catch (error) {
          Hub.toast(error.message);
        }
      });
      modal.addEventListener("click", (event) => {
        if (event.target === modal) closeResult();
      });

      const onKey = (event) => {
        if (event.key === "Escape") closeResult();
      };
      document.addEventListener("keydown", onKey);

      loadLastRun();

      return () => {
        state.closed = true;
        document.removeEventListener("keydown", onKey);
        modal.remove();
      };
    },
  };
})();
