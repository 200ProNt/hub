/* Инструмент «Большие файлы» */

(function () {
  const OPEN_ICON =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 5h5v5"/><path d="M19 5l-7.5 7.5"/><path d="M18 14.5v3A2.5 2.5 0 0 1 15.5 20h-9A2.5 2.5 0 0 1 4 17.5v-9A2.5 2.5 0 0 1 6.5 6h3"/></svg>';

  const TEMPLATE = `
    <section class="card picker">
      <div class="picker-head">
        <h2>Где искать тяжёлые файлы</h2>
        <span class="pill pill-quiet">по размеру</span>
      </div>
      <div class="field-row">
        <div class="path-field">
          <svg class="path-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/>
          </svg>
          <input id="bigFolder" type="text" spellcheck="false" autocomplete="off" aria-label="Путь к папке">
        </div>
        <label class="select-field">
          <span>не меньше</span>
          <select id="bigMin" aria-label="Минимальный размер файла">
            <option value="5242880">5 МБ</option>
            <option value="20971520" selected>20 МБ</option>
            <option value="104857600">100 МБ</option>
            <option value="524288000">500 МБ</option>
            <option value="1073741824">1 ГБ</option>
          </select>
        </label>
        <button class="btn ghost" id="bigBrowse" type="button">Обзор…</button>
        <button class="btn primary" id="bigScan" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>
          </svg>
          Найти
        </button>
      </div>
      <p class="hint">Показываю самые тяжёлые файлы внутри выбранной папки, включая вложенные. Ссылки не разворачиваются.</p>
    </section>

    <div id="bigUndo" class="hidden" aria-live="polite"></div>

    <section class="big-result hidden" id="bigResult">
      <div class="card big-card">
        <div class="big-top">
          <div>
            <h2 class="big-folder" id="bigFolderName">Папка</h2>
            <p class="big-folder-path" id="bigFolderPath"></p>
          </div>
          <button class="btn ghost small" id="bigOpen" type="button">Открыть папку</button>
        </div>
        <div class="big-list" id="bigList"></div>
        <p class="big-note" id="bigNote"></p>
      </div>

      <section class="stats" aria-live="polite">
        <div class="stat">
          <span class="stat-value" id="bigStatCount">0</span>
          <span class="stat-label" id="bigStatCountLabel">файлов</span>
        </div>
        <div class="stat">
          <span class="stat-value" id="bigStatSize">0 Б</span>
          <span class="stat-label">занимают найденные</span>
        </div>
        <div class="stat">
          <span class="stat-value" id="bigStatScanned">0</span>
          <span class="stat-label" id="bigStatScannedLabel">файлов проверено</span>
        </div>
      </section>
    </section>

    <section class="empty-state" id="bigEmpty">
      <div class="empty-art" aria-hidden="true">
        <div class="empty-folder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 8.5h16v9A2.5 2.5 0 0 1 17.5 20h-11A2.5 2.5 0 0 1 4 17.5z"/>
            <path d="M7.5 8.5V6A1.5 1.5 0 0 1 9 4.5h4.5"/>
            <path d="M9 14h6"/>
          </svg>
        </div>
        <span class="empty-chip c1">видео</span>
        <span class="empty-chip c2">образ игры</span>
        <span class="empty-chip c3">архив</span>
        <span class="empty-chip c4">резервная копия</span>
      </div>
      <h2>Кто съел место</h2>
      <p>Выбери папку или диск — покажу список самых тяжёлых файлов. Отсюда их можно убрать в корзину хаба и вернуть, если передумаешь.</p>
      <div class="chips big-quick" id="bigQuick"></div>
    </section>`;

  window.HubTools.bigfiles = {
    mount(root) {
      root.innerHTML = TEMPLATE;

      const $ = (selector) => root.querySelector(selector);
      const escape = Hub.escapeHtml;
      const plural = Hub.plural;

      const state = {
        data: null,
        busy: false,
        closed: false,
        lastRun: null,
      };

      const folderInput = $("#bigFolder");
      folderInput.value = Hub.defaultFolder || "";

      /* --- помощники --- */

      function parentOf(path) {
        const clean = String(path || "").replace(/[\\/]+$/, "");
        const cut = Math.max(clean.lastIndexOf("\\"), clean.lastIndexOf("/"));
        if (cut <= 0) return null;
        const parent = clean.slice(0, cut);
        if (/^[A-Za-z]:$/.test(parent)) return `${parent}\\`;
        return parent;
      }

      function baseName(path) {
        const clean = String(path || "").replace(/[\\/]+$/, "");
        const cut = Math.max(clean.lastIndexOf("\\"), clean.lastIndexOf("/"));
        return clean.slice(cut + 1) || clean;
      }

      const FRIENDLY = {
        downloads: "Загрузки",
        desktop: "Рабочий стол",
        documents: "Документы",
        pictures: "Изображения",
        music: "Музыка",
        videos: "Видео",
      };

      function friendlyName(path) {
        const name = baseName(path);
        if (FRIENDLY[name.toLowerCase()]) return FRIENDLY[name.toLowerCase()];
        if (/^[A-Za-z]:[\\/]Users[\\/][^\\/]+$/i.test(String(path || ""))) return "Домашняя папка";
        return name;
      }

      function fmtDate(timestamp) {
        const date = new Date((Number(timestamp) || 0) * 1000);
        if (Number.isNaN(date.getTime())) return "";
        const months = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
        return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
      }

      function shortFolder(path) {
        const parent = parentOf(path) || "";
        return parent === state.data?.folder ? "в корне папки" : baseName(parent) || parent;
      }

      /* --- рендер --- */

      function renderList() {
        if (!state.data) return;
        const files = state.data.files;
        $("#bigList").innerHTML = files.length
          ? files.map((file, index) => `
              <article class="big-file" style="--row-index:${Math.min(index, 12)}" data-index="${index}">
                <span class="big-rank">${index + 1}</span>
                <div class="big-file-text">
                  <span class="big-file-name" title="${escape(file.path)}">${escape(file.name)}</span>
                  <span class="big-file-meta">${escape(shortFolder(file.path))} · изменён ${fmtDate(file.modified)}</span>
                </div>
                <span class="big-file-size">${Hub.fmtSize(file.size)}</span>
                <div class="big-file-tools">
                  <button class="mini-btn" type="button" data-act="reveal" title="Показать в проводнике" aria-label="Показать в проводнике">${OPEN_ICON}</button>
                  <button class="btn ghost tiny big-delete" type="button" data-act="delete">Удалить</button>
                </div>
              </article>`).join("")
          : '<p class="big-empty-row">Ни одного файла такого размера не нашлось. Попробуй снизить порог.</p>';
      }

      function renderStats() {
        const data = state.data;
        if (!data) return;
        $("#bigStatCount").textContent = data.files.length.toLocaleString("ru-RU");
        $("#bigStatCountLabel").textContent = plural(data.files.length, "файл", "файла", "файлов");
        $("#bigStatSize").textContent = Hub.fmtSize(data.matched_size);
        $("#bigStatScanned").textContent = data.scanned.toLocaleString("ru-RU");
        $("#bigStatScannedLabel").textContent = plural(data.scanned, "файл проверен", "файла проверено", "файлов проверено");

        const bits = [];
        bits.push(data.matched > data.files.length
          ? `Всего под условие подошло ${data.matched} ${plural(data.matched, "файл", "файла", "файлов")}`
          : `Под условие подошёл ${data.matched} ${plural(data.matched, "файл", "файла", "файлов")}`);
        if (data.links) bits.push(`${data.links} ${plural(data.links, "ссылка пропущена", "ссылки пропущены", "ссылок пропущено")}`);
        if (data.errors?.length) bits.push(`${data.errors.length} ${plural(data.errors.length, "ошибка", "ошибки", "ошибок")} доступа`);
        if (data.truncated) bits.push("папка очень большая — обход остановлен");
        bits.push(`Считалось ${data.seconds.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с`);
        $("#bigNote").textContent = bits.join(" · ");
      }

      function renderFolder() {
        const data = state.data;
        if (!data) return;
        $("#bigFolderName").textContent = friendlyName(data.folder);
        $("#bigFolderPath").textContent = data.folder;
      }

      function render() {
        if (!state.data) return;
        $("#bigEmpty").classList.add("hidden");
        $("#bigResult").classList.remove("hidden");
        renderFolder();
        renderList();
        renderStats();
      }

      function renderUndo() {
        const host = $("#bigUndo");
        host.classList.toggle("hidden", !state.lastRun);
        host.innerHTML = state.lastRun
          ? `<div class="undo-banner"><span class="undo-banner-text">В корзине хаба: ${state.lastRun.count} ${plural(state.lastRun.count, "файл", "файла", "файлов")} · ${Hub.fmtSize(state.lastRun.size)}</span><button class="btn ghost small" type="button" data-undo>Вернуть</button></div>`
          : "";
      }

      function showEmpty(title, text) {
        $("#bigResult").classList.add("hidden");
        $("#bigEmpty").classList.remove("hidden");
        $("#bigEmpty").querySelector("h2").textContent = title;
        $("#bigEmpty").querySelector("p").textContent = text;
      }

      /* --- действия --- */

      async function load(folder) {
        if (state.busy || state.closed) return;
        const target = String(folder || "").trim();
        if (!target) {
          Hub.toast("Сначала выбери папку");
          folderInput.focus();
          return;
        }
        state.busy = true;
        Hub.setBusy(true, "Ищу большие файлы…");
        try {
          const data = await Hub.api("/api/bigfiles/scan", {
            folder: target,
            min_size: Number($("#bigMin").value),
          });
          if (state.closed) return;
          state.data = data;
          folderInput.value = data.folder;
          if (!data.files.length) {
            showEmpty(
              "Крупных файлов не нашлось",
              `В этой папке нет файлов больше ${Hub.fmtSize(data.min_size)}. Попробуй меньший порог или другую папку.`,
            );
            return;
          }
          render();
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          Hub.setBusy(false);
        }
      }

      async function reveal(path) {
        try {
          await Hub.api("/api/open", { path });
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        }
      }

      async function remove(index) {
        const file = state.data?.files[index];
        if (!file || state.busy || state.closed) return;
        state.busy = true;
        let busyShown = false;
        let changed = false;
        try {
          const mode = await Hub.choose({
            title: "Что сделать с файлом?",
            text: `${file.name} · ${Hub.fmtSize(file.size)}. Корзина хаба — не корзина Windows: файл можно вернуть здесь. Перенос в неё не освобождает место на этом диске сразу.`,
            choices: [
              { value: "trash", label: "В корзину хаба" },
              { value: "delete", label: "Удалить навсегда", danger: true },
            ],
          });
          if (!mode || state.closed) return;
          if (mode === "delete") {
            const confirmed = await Hub.confirm({
              title: "Удалить без возможности вернуть?",
              text: `Файл «${file.name}» исчезнет навсегда, без корзины. Отменить это нельзя.`,
              confirmText: "Удалить навсегда",
              danger: true,
            });
            if (!confirmed || state.closed) return;
          }
          Hub.setBusy(true, mode === "trash" ? "Перемещаю в корзину…" : "Удаляю файл…");
          busyShown = true;
          const result = await Hub.api("/api/bigfiles/remove", { path: file.path, mode, confirmed: mode === "delete" });
          if (state.closed) return;
          if (result.errors?.length) throw new Error(result.errors.map((item) => item.reason).join("; "));
          changed = result.removed_count > 0;
          if (result.run_id) {
            state.lastRun = { run_id: result.run_id, count: result.removed_count, size: result.removed_size };
          }
          renderUndo();
          Hub.toast(mode === "trash" ? "Файл в корзине хаба — можно вернуть" : "Файл удалён навсегда");
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          busyShown && Hub.setBusy(false);
        }
        if (changed && !state.closed) await load(folderInput.value);
      }

      async function undo() {
        if (!state.lastRun || state.busy || state.closed) return;
        state.busy = true;
        Hub.setBusy(true, "Возвращаю файл…");
        let restored = false;
        try {
          const result = await Hub.api("/api/bigfiles/undo", { run_id: state.lastRun.run_id });
          if (state.closed) return;
          restored = result.restored_count > 0;
          const latest = await Hub.api("/api/bigfiles/last-run");
          if (state.closed) return;
          state.lastRun = latest.last_run;
          renderUndo();
          Hub.toast(result.errors?.length ? result.errors.map((item) => item.reason).join("; ") : "Файл возвращён на место");
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          Hub.setBusy(false);
        }
        if (restored && !state.closed && state.data) await load(folderInput.value);
      }

      /* --- быстрые папки --- */

      function buildQuickChips() {
        const host = $("#bigQuick");
        const start = (Hub.defaultFolder || "").replace(/[\\/]+$/, "");
        if (!start) return;
        const chips = [];
        const add = (path, label) => {
          if (!path) return;
          if (chips.some((chip) => chip.path.toLowerCase() === path.toLowerCase())) return;
          chips.push({ path, label });
        };
        add(start, friendlyName(start));
        const drive = start.match(/^([A-Za-z]:)/);
        if (drive) add(`${drive[1]}\\`, `Диск ${drive[1]}`);
        host.innerHTML = chips
          .map((chip) => `<button class="chip" type="button" data-path="${escape(chip.path)}">${escape(chip.label)}</button>`)
          .join("");
      }

      /* --- события --- */

      $("#bigScan").addEventListener("click", () => load(folderInput.value));
      folderInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") load(folderInput.value);
      });

      $("#bigBrowse").addEventListener("click", async () => {
        const button = $("#bigBrowse");
        button.disabled = true;
        try {
          const result = await Hub.api("/api/pick-folder", { initial: folderInput.value.trim() });
          if (result.folder) {
            folderInput.value = result.folder;
            load(result.folder);
          }
        } catch (error) {
          Hub.toast(error.message);
        } finally {
          button.disabled = false;
        }
      });

      $("#bigQuick").addEventListener("click", (event) => {
        const chip = event.target.closest("[data-path]");
        if (!chip) return;
        folderInput.value = chip.dataset.path;
        load(chip.dataset.path);
      });

      $("#bigOpen").addEventListener("click", () => {
        if (state.data) reveal(state.data.folder);
      });

      $("#bigList").addEventListener("click", async (event) => {
        const button = event.target.closest("[data-act]");
        if (!button) return;
        const card = button.closest("[data-index]");
        if (!card) return;
        const index = Number(card.dataset.index);
        if (button.dataset.act === "reveal") {
          const file = state.data?.files[index];
          if (file) reveal(file.path);
        } else if (button.dataset.act === "delete") {
          await remove(index);
        }
      });

      $("#bigUndo").addEventListener("click", (event) => {
        if (event.target.closest("[data-undo]")) undo();
      });

      Hub.api("/api/bigfiles/last-run")
        .then((data) => {
          if (state.closed || state.lastRun) return;
          state.lastRun = data.last_run;
          renderUndo();
        })
        .catch((error) => {
          if (!state.closed) Hub.toast(error.message);
        });

      buildQuickChips();

      return () => {
        state.closed = true;
        Hub.dismissDialog();
      };
    },
  };
})();
