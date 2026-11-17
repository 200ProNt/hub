/* Инструмент «Дубликаты» */

(function () {
  const IMAGE_EXT = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "avif"];

  const ICONS = {
    image: '<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="m4.5 17 4.4-4.2a1.6 1.6 0 0 1 2.2 0l3 2.9M14 15l1.6-1.5a1.6 1.6 0 0 1 2.2 0l2.7 2.6"/>',
    video: '<rect x="3" y="5" width="13" height="14" rx="3"/><path d="m16 10.4 3.6-2.1a1 1 0 0 1 1.4.9v5.6a1 1 0 0 1-1.4.9L16 13.6z"/>',
    audio: '<path d="M9 17.5V6.2a1 1 0 0 1 .8-1l8-1.6a1 1 0 0 1 1.2 1v10.9"/><circle cx="6.5" cy="18" r="2.6"/><circle cx="16.5" cy="16" r="2.6"/>',
    archive: '<path d="M4 7.5 12 4l8 3.5v9L12 20l-8-3.5z"/><path d="M4 7.5 12 11l8-3.5M12 11v9"/>',
    file: '<path d="M6 3.5h7.5L19 9v11.5H6z"/><path d="M13.5 3.5V9H19"/>',
  };

  const REVEAL_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/></svg>';
  const RESULT_ICONS = {
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 6.5v7"/><path d="M12 17.2v.1"/></svg>',
  };

  const TEMPLATE = `
    <section class="card picker">
      <div class="picker-head">
        <h2>Где ищем одинаковые файлы</h2>
        <span class="pill pill-quiet">по содержимому</span>
      </div>
      <div class="field-row">
        <div class="path-field">
          <svg class="path-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/>
          </svg>
          <input id="dupesFolder" type="text" spellcheck="false" autocomplete="off" aria-label="Путь к папке">
        </div>
        <button class="btn ghost" id="dupesBrowse" type="button">Обзор…</button>
        <button class="btn primary" id="dupesScan" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/>
          </svg>
          Найти
        </button>
      </div>
      <div class="dupe-options">
        <label class="switch">
          <input type="checkbox" id="dupesRecursive" checked>
          <span class="switch-track" aria-hidden="true"><span class="switch-thumb"></span></span>
          <span>смотреть и подпапки</span>
        </label>
        <span class="hint-inline">файлы меньше 1 КБ пропускаем</span>
      </div>
      <p class="hint">Сравниваем байты, а не имена: «отпуск.jpg» и «DSC_0421.jpg» с одинаковым содержимым попадут в одну группу. Служебные папки вроде <code>.venv</code> и <code>node_modules</code> не трогаем.</p>
      <div class="undo-banner hidden" id="dupesUndoBanner" role="status">
        <span class="undo-banner-text" id="dupesUndoText"></span>
        <button class="btn tiny" id="dupesUndoBtn" type="button">Вернуть</button>
      </div>
    </section>

    <section class="stats hidden" id="dupesStats" aria-live="polite">
      <div class="stat">
        <span class="stat-value" id="dupesStatGroups">0</span>
        <span class="stat-label" id="dupesStatGroupsLabel">групп</span>
      </div>
      <div class="stat">
        <span class="stat-value" id="dupesStatCopies">0</span>
        <span class="stat-label" id="dupesStatCopiesLabel">лишних копий</span>
      </div>
      <div class="stat">
        <span class="stat-value" id="dupesStatFree">0 Б</span>
        <span class="stat-label">можно освободить</span>
      </div>
    </section>

    <section class="preview hidden" id="dupesPreview" aria-label="Найденные дубликаты">
      <div class="toolbar">
        <div class="search">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/>
          </svg>
          <input id="dupesSearch" type="search" placeholder="Поиск по имени или папке…" autocomplete="off" aria-label="Поиск по найденным файлам">
        </div>
        <button class="btn ghost small" id="dupesMarkAll" type="button">Отметить лишние</button>
        <button class="btn ghost small" id="dupesReset" type="button" hidden>Сбросить поиск</button>
      </div>

      <div class="dupe-list" id="dupesList"></div>

      <div class="more-wrap">
        <button class="btn ghost" id="dupesMore" type="button" hidden></button>
      </div>

      <div class="list-empty hidden" id="dupesListEmpty">
        <p class="list-empty-title">По этому запросу ничего нет</p>
        <p class="list-empty-sub">Попробуй другое имя файла или папки.</p>
      </div>

      <div class="actionbar" id="dupesActionbar">
        <div class="selection">
          <span class="selection-dot" aria-hidden="true"></span>
          <span>
            <strong id="dupesSelCount">0</strong>
            <span id="dupesSelText">файлов</span>
            <span class="selection-sep">·</span>
            <span id="dupesSelSize">0 Б</span>
          </span>
        </div>
        <div class="actionbar-right">
          <button class="btn ghost small" id="dupesClear" type="button">Снять всё</button>
          <button class="btn primary large" id="dupesRemove" type="button" disabled>Убрать выбранные</button>
        </div>
      </div>
    </section>

    <section class="empty-state" id="dupesEmpty">
      <div class="empty-art" aria-hidden="true">
        <div class="empty-folder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="4.5" width="11" height="14" rx="2.5"/>
            <rect x="10" y="8.5" width="11" height="14" rx="2.5"/>
          </svg>
        </div>
        <span class="empty-chip c1">одно и то же фото</span>
        <span class="empty-chip c2">скачано дважды</span>
        <span class="empty-chip c3">копия папки</span>
        <span class="empty-chip c4">разные имена</span>
      </div>
      <h2>Одинаковые файлы, разные имена</h2>
      <p>Проверим папку и покажем группы файлов с одинаковым содержимым. Лишние копии можно убрать в корзину хаба — и вернуть обратно, если передумаешь.</p>
    </section>`;

  const MODAL_TEMPLATE = `
    <div class="modal hidden" id="dupesModal" role="dialog" aria-modal="true" aria-labelledby="dupesResultTitle">
      <div class="modal-card">
        <div class="result-icon" id="dupesResultIcon" aria-hidden="true"></div>
        <h2 id="dupesResultTitle">Готово</h2>
        <p class="result-text" id="dupesResultText"></p>
        <div class="result-errors hidden" id="dupesResultErrors"></div>
        <div class="modal-actions">
          <button class="btn ghost" id="dupesResultClose" type="button">Закрыть</button>
          <button class="btn ghost" id="dupesResultOpen" type="button">Открыть папку</button>
          <button class="btn primary" id="dupesResultUndo" type="button">Вернуть файлы</button>
        </div>
      </div>
    </div>`;

  const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

  window.HubTools.dupes = {
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
        groups: [],
        selected: new Set(),
        query: "",
        limit: 40,
        lastRun: null,
        resultRunId: null,
        busy: false,
        closed: false,
        errors: 0,
      };
      const PAGE = 40;

      const folderInput = $("#dupesFolder");
      folderInput.value = Hub.defaultFolder || "";
      state.folder = Hub.defaultFolder || "";

      /* --- помощники --- */

      function fmtDate(timestamp) {
        const date = new Date((Number(timestamp) || 0) * 1000);
        if (Number.isNaN(date.getTime())) return "";
        return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
      }

      function extOf(name) {
        const dot = name.lastIndexOf(".");
        return dot === -1 ? "" : name.slice(dot + 1).toLowerCase();
      }

      function iconKind(name) {
        const ext = extOf(name);
        if (IMAGE_EXT.includes(ext)) return "image";
        if (["mp4", "mkv", "mov", "avi", "webm"].includes(ext)) return "video";
        if (["mp3", "flac", "wav", "ogg", "m4a"].includes(ext)) return "audio";
        if (["zip", "rar", "7z", "tar", "gz"].includes(ext)) return "archive";
        return "file";
      }

      function thumbMarkup(item) {
        if (IMAGE_EXT.includes(extOf(item.name))) {
          const url = `/api/dupes/thumb?path=${encodeURIComponent(item.path)}`;
          return `<img src="${url}" alt="" loading="lazy" decoding="async">`;
        }
        return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${ICONS[iconKind(item.name)]}</svg>`;
      }

      function visibleGroups() {
        const query = state.query.trim().toLowerCase();
        if (!query) return state.groups;
        return state.groups
          .map((group) => ({
            ...group,
            files: group.files.filter(
              (item) =>
                item.name.toLowerCase().includes(query) || item.rel.toLowerCase().includes(query),
            ),
          }))
          .filter((group) => group.files.length > 0);
      }

      function groupSelectedCount(group) {
        return group.files.filter((item) => state.selected.has(item.path)).length;
      }

      /* --- рендер --- */

      function renderStats() {
        const groups = state.groups.length;
        const copies = state.groups.reduce((sum, group) => sum + group.count - 1, 0);
        const free = state.groups.reduce((sum, group) => sum + group.free, 0);
        $("#dupesStatGroups").textContent = String(groups);
        $("#dupesStatGroupsLabel").textContent = plural(groups, "группа", "группы", "групп");
        $("#dupesStatCopies").textContent = String(copies);
        $("#dupesStatCopiesLabel").textContent = plural(copies, "лишняя копия", "лишние копии", "лишних копий");
        $("#dupesStatFree").textContent = Hub.fmtSize(free);
      }

      function rowMarkup(item, group) {
        const picked = state.selected.has(item.path);
        return `
          <div class="dupe-row ${picked ? "is-picked" : ""}" data-path="${escape(item.path)}">
            <label class="dupe-pick">
              <span class="check">
                <input type="checkbox" ${picked ? "checked" : ""} aria-label="Убрать копию ${escape(item.name)}">
                <span class="box"></span>
              </span>
              <span class="dupe-thumb">${thumbMarkup(item)}</span>
              <span class="dupe-text">
                <span class="dupe-name">${escape(item.name)}</span>
                <span class="dupe-meta">${escape(item.dir || "в корне папки")} · ${fmtDate(item.mtime)}</span>
              </span>
            </label>
            <span class="dupe-size">${Hub.fmtSize(item.size)}</span>
            <button class="mini-btn" type="button" data-act="reveal" title="Показать в проводнике" aria-label="Показать в проводнике">${REVEAL_ICON}</button>
          </div>`;
      }

      function groupMarkup(group) {
        const selected = groupSelectedCount(group);
        const allExtras = group.count - 1;
        const markLabel = selected >= allExtras ? "Снять отметки" : "Отметить лишние";
        return `
          <article class="dupe-group" data-key="${escape(group.key)}">
            <header class="dupe-head">
              <div class="dupe-head-main">
                <span class="dupe-title">${group.count} ${plural(group.count, "копия", "копии", "копий")}</span>
                <span class="dupe-sub">по ${Hub.fmtSize(group.size)} · ${escape(extOf(group.files[0].name) || "без расширения")}</span>
              </div>
              <div class="dupe-head-side">
                <span class="dupe-free">освободит ${Hub.fmtSize(group.free)}</span>
                <button class="btn ghost tiny" type="button" data-act="mark-group">${markLabel}</button>
              </div>
            </header>
            <div class="dupe-files">
              ${group.files.map((item) => rowMarkup(item, group)).join("")}
            </div>
          </article>`;
      }

      function renderList() {
        const groups = visibleGroups();
        const list = $("#dupesList");
        list.innerHTML = groups.slice(0, state.limit).map(groupMarkup).join("");

        const empty = $("#dupesListEmpty");
        empty.classList.toggle("hidden", groups.length > 0);
        $("#dupesReset").hidden = state.query.trim() === "";

        const more = $("#dupesMore");
        const rest = groups.length - state.limit;
        more.hidden = rest <= 0;
        if (rest > 0) {
          more.textContent = `Показать ещё ${Math.min(PAGE, rest)} из ${rest}`;
        }

        syncBar();
      }

      function syncBar() {
        const picked = state.groups
          .flatMap((group) => group.files)
          .filter((item) => state.selected.has(item.path));
        const count = picked.length;
        const size = picked.reduce((sum, item) => sum + item.size, 0);

        $("#dupesSelCount").textContent = String(count);
        $("#dupesSelText").textContent = plural(count, "файл", "файла", "файлов");
        $("#dupesSelSize").textContent = Hub.fmtSize(size);

        const button = $("#dupesRemove");
        button.disabled = count === 0 || state.busy;
        button.textContent = count > 0 ? `Убрать выбранные (${count})` : "Убрать выбранные";

        const extrasTotal = state.groups.reduce((sum, group) => sum + group.count - 1, 0);
        const extrasSelected = state.groups.reduce(
          (sum, group) =>
            sum + group.files.slice(1).filter((item) => state.selected.has(item.path)).length,
          0,
        );
        const markAll = $("#dupesMarkAll");
        markAll.disabled = extrasTotal === 0 || state.busy;
        markAll.textContent =
          extrasTotal > 0 && extrasSelected === extrasTotal ? "Снять отметки" : "Отметить лишние";
      }

      function renderAll() {
        renderStats();
        renderList();
      }

      function showPreview() {
        $("#dupesStats").classList.remove("hidden");
        $("#dupesPreview").classList.remove("hidden");
        $("#dupesEmpty").classList.add("hidden");
      }

      function showEmptyState(title, text) {
        $("#dupesStats").classList.add("hidden");
        $("#dupesPreview").classList.add("hidden");
        const node = $("#dupesEmpty");
        node.classList.remove("hidden");
        if (title) node.querySelector("h2").textContent = title;
        if (text) node.querySelector("p").textContent = text;
      }

      function adoptScan(data) {
        state.folder = data.folder || state.folder;
        state.groups = data.groups || [];
        state.errors = (data.errors || []).length;
        state.skippedDirs = data.skipped_dirs || 0;
        folderInput.value = state.folder;

        state.selected = new Set();
        state.limit = PAGE;
        state.query = "";
        $("#dupesSearch").value = "";

        if (state.groups.length === 0) {
          showEmptyState(
            "Одинаковых файлов не нашлось",
            "В этой папке все файлы разные — либо копии меньше 1 КБ. Попробуй другую папку.",
          );
          return;
        }

        showPreview();
        renderAll();
      }

      async function scanFolder(silent = false) {
        const folder = folderInput.value.trim() || state.folder;
        if (!folder) {
          Hub.toast("Сначала выбери папку");
          folderInput.focus();
          return;
        }
        if (!silent) {
          Hub.setBusy(true, "Сравниваю файлы…");
          state.busy = true;
          syncBar();
        }
        try {
          const data = await Hub.api("/api/dupes/scan", {
            folder,
            recursive: $("#dupesRecursive").checked,
          });
          if (state.closed) return;
          adoptScan(data);
          if (!silent) {
            if (data.groups.length === 0) {
              Hub.toast("Одинаковых файлов нет");
            } else {
              Hub.toast(
                `Нашёл ${data.groups.length} ${plural(data.groups.length, "группу", "группы", "групп")} дубликатов`,
              );
            }
          }
        } catch (error) {
          Hub.toast(error.message);
        } finally {
          if (!silent) {
            state.busy = false;
            Hub.setBusy(false);
            syncBar();
          }
        }
      }

      /* --- удаление --- */

      function showResult(result) {
        const removed = result.removed_count || 0;
        const errors = result.errors || [];
        const icon = $("#dupesResultIcon");
        const title = $("#dupesResultTitle");
        const text = $("#dupesResultText");
        const warn = removed === 0 || errors.length > 0;

        icon.classList.toggle("warn", warn);
        icon.innerHTML = warn ? RESULT_ICONS.warn : RESULT_ICONS.check;

        if (removed > 0 && errors.length === 0) title.textContent = "Готово!";
        else if (removed > 0) title.textContent = "Почти всё получилось";
        else title.textContent = "Ничего не убрано";

        if (removed > 0) {
          text.textContent = `Убрано ${removed} ${plural(removed, "файл", "файла", "файлов")} · ${Hub.fmtSize(result.removed_size)}. Они лежат в корзине хаба — можно вернуть.`;
        } else {
          text.textContent = "Выбранные копии не удалось убрать.";
        }

        const errorsBox = $("#dupesResultErrors");
        if (errors.length > 0) {
          errorsBox.classList.remove("hidden");
          errorsBox.innerHTML = errors
            .slice(0, 30)
            .map((error) => `<div><b>${escape(error.path)}</b> — ${escape(error.reason)}</div>`)
            .join("");
        } else {
          errorsBox.classList.add("hidden");
          errorsBox.innerHTML = "";
        }

        state.resultRunId = result.run_id || null;
        $("#dupesResultUndo").classList.toggle("hidden", !result.run_id);
        modal.classList.remove("hidden");
      }

      function closeResult() {
        modal.classList.add("hidden");
      }

      async function removeSelected() {
        const paths = [...state.selected];
        if (paths.length === 0) return;

        const confirmed = await Hub.confirm({
          title: "Убрать лишние копии?",
          text: `Выбрано ${paths.length} ${plural(paths.length, "файл", "файла", "файлов")}. Они переедут в корзину хаба — оттуда их можно вернуть. В каждой группе останется хотя бы одна копия.`,
          confirmText: "Убрать",
        });
        if (!confirmed) return;

        Hub.setBusy(true, "Убираю копии…");
        state.busy = true;
        syncBar();
        try {
          const result = await Hub.api("/api/dupes/remove", {
            folder: state.folder,
            files: paths,
          });
          if (state.closed) return;
          showResult(result);
          await scanFolder(true);
          await loadLastRun();
        } catch (error) {
          Hub.toast(error.message);
        } finally {
          state.busy = false;
          Hub.setBusy(false);
          syncBar();
        }
      }

      async function doUndo(runId) {
        if (!runId) return;
        Hub.setBusy(true, "Возвращаю файлы…");
        try {
          const result = await Hub.api("/api/dupes/undo", { run_id: runId });
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
          Hub.setBusy(false);
        }
      }

      async function loadLastRun() {
        try {
          const data = await Hub.api("/api/dupes/last-run");
          state.lastRun = data.last_run || null;
        } catch {
          state.lastRun = null;
        }
        if (state.closed) return;

        const banner = $("#dupesUndoBanner");
        if (!state.lastRun) {
          banner.classList.add("hidden");
          return;
        }
        const count = state.lastRun.count;
        $("#dupesUndoText").textContent = `В корзине хаба: ${count} ${plural(count, "файл", "файла", "файлов")} · ${Hub.fmtSize(state.lastRun.size)} — можно вернуть.`;
        banner.classList.remove("hidden");
      }

      /* --- события --- */

      $("#dupesScan").addEventListener("click", () => scanFolder(false));
      folderInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") scanFolder(false);
      });

      $("#dupesBrowse").addEventListener("click", async () => {
        const button = $("#dupesBrowse");
        button.disabled = true;
        try {
          const result = await Hub.api("/api/pick-folder", { initial: folderInput.value.trim() });
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

      $("#dupesSearch").addEventListener("input", (event) => {
        state.query = event.target.value;
        renderList();
      });

      $("#dupesReset").addEventListener("click", () => {
        state.query = "";
        $("#dupesSearch").value = "";
        state.limit = PAGE;
        renderList();
      });

      $("#dupesMore").addEventListener("click", () => {
        state.limit += PAGE;
        renderList();
      });

      $("#dupesMarkAll").addEventListener("click", () => {
        const extras = state.groups.flatMap((group) =>
          group.files.slice(1).map((item) => item.path),
        );
        const allSelected = extras.length > 0 && extras.every((path) => state.selected.has(path));
        state.selected = allSelected ? new Set() : new Set(extras);
        renderList();
      });

      $("#dupesList").addEventListener("change", (event) => {
        const input = event.target.closest('input[type="checkbox"]');
        if (!input) return;
        const row = input.closest(".dupe-row");
        const card = input.closest(".dupe-group");
        if (!row || !card) return;

        const path = row.dataset.path;
        const group = state.groups.find((item) => item.key === card.dataset.key);
        if (!group) return;

        if (input.checked) {
          if (groupSelectedCount(group) >= group.count) {
            input.checked = false;
            Hub.toast("В каждой группе должна остаться хотя бы одна копия");
            return;
          }
          state.selected.add(path);
        } else {
          state.selected.delete(path);
        }
        row.classList.toggle("is-picked", input.checked);
        syncBar();
      });

      $("#dupesList").addEventListener("click", async (event) => {
        const mark = event.target.closest('[data-act="mark-group"]');
        if (mark) {
          const card = mark.closest(".dupe-group");
          const group = state.groups.find((item) => item.key === card.dataset.key);
          if (!group) return;
          const extras = group.files.slice(1).map((item) => item.path);
          const allSelected = extras.every((path) => state.selected.has(path));
          extras.forEach((path) => {
            if (allSelected) state.selected.delete(path);
            else state.selected.add(path);
          });
          renderList();
          return;
        }

        const button = event.target.closest('[data-act="reveal"]');
        if (!button) return;
        const row = button.closest(".dupe-row");
        if (!row) return;
        try {
          await Hub.api("/api/open", { path: row.dataset.path });
        } catch (error) {
          Hub.toast(error.message);
        }
      });

      $("#dupesClear").addEventListener("click", () => {
        state.selected.clear();
        renderList();
      });

      $("#dupesRemove").addEventListener("click", removeSelected);

      $("#dupesUndoBtn").addEventListener("click", () => {
        if (state.lastRun) doUndo(state.lastRun.run_id);
      });

      $("#dupesResultClose").addEventListener("click", closeResult);
      $("#dupesResultUndo").addEventListener("click", () => doUndo(state.resultRunId));
      $("#dupesResultOpen").addEventListener("click", async () => {
        try {
          await Hub.api("/api/open", { path: state.folder });
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
