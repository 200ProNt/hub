/* Инструмент «Уборка» */

(function () {
  const TEMPLATE = `
    <section class="card picker">
      <div class="picker-head">
        <h2>Что прибрать</h2>
        <div style="display:flex;gap:8px;align-items:center;">
          <button class="btn ghost small" id="cleanRulesBtn" type="button">Настроить правила</button>
          <span class="pill pill-quiet">корзина хаба</span>
        </div>
      </div>
      <div class="field-row">
        <div class="path-field">
          <svg class="path-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/>
          </svg>
          <input id="cleanFolder" type="text" spellcheck="false" autocomplete="off" aria-label="Путь к папке">
        </div>
        <label class="select-field">
          <span>не трогали</span>
          <select id="cleanAge" aria-label="Возраст файлов">
            <option value="90">3 месяца</option>
            <option value="180">полгода</option>
            <option value="365" selected>год</option>
            <option value="730">два года</option>
          </select>
        </label>
        <button class="btn ghost" id="cleanBrowse" type="button">Обзор…</button>
        <button class="btn primary" id="cleanScan" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 12.5 12 5l8 7.5"/><path d="M7.5 12v7.5h9V12"/>
          </svg>
          Проверить
        </button>
      </div>
      <label class="switch clean-switch">
        <input type="checkbox" id="cleanJunk" checked>
        <span class="switch-track"><span class="switch-thumb"></span></span>
        <span class="switch-text">Искать временные файлы и кэш</span>
      </label>
      <p class="hint">Показываю старые файлы, мусорные остатки и пустые папки. Ничего не удаляется, пока не отметишь. Выбранное уходит в корзину хаба.</p>
    </section>

    <section class="card rules-card hidden" id="cleanRulesCard">
      <div class="rules-head">
        <h3>Правила мусорных файлов</h3>
        <div class="rules-actions">
          <button class="btn ghost small" id="cleanRulesReset" type="button">По умолчанию</button>
          <button class="btn primary small" id="cleanRulesSave" type="button">Сохранить</button>
        </div>
      </div>
      <div class="rules-field">
        <label for="cleanRulesSuffixes">Расширения мусорных файлов (через запятую):</label>
        <input id="cleanRulesSuffixes" type="text" placeholder=".tmp, .bak, .old, .cache">
      </div>
      <div class="rules-field">
        <label for="cleanRulesNames">Имена мусорных файлов (через запятую):</label>
        <input id="cleanRulesNames" type="text" placeholder="thumbs.db, .ds_store">
      </div>
    </section>

    <div id="cleanUndo" class="hidden" aria-live="polite"></div>

    <section class="clean-result hidden" id="cleanResult">
      <div class="chips clean-chips" id="cleanChips" aria-label="Категории уборки"></div>

      <div class="card clean-card">
        <div class="clean-list" id="cleanList"></div>
      </div>

      <div class="actionbar" id="cleanBar">
        <div class="actionbar-left">
          <span class="actionbar-count"><b id="cleanSelCount">0</b> <span id="cleanSelText">файлов</span></span>
          <span class="actionbar-size" id="cleanSelSize">0 Б</span>
        </div>
        <div class="actionbar-right">
          <button class="btn ghost small" id="cleanMarkAll" type="button">Отметить всё</button>
          <button class="btn danger" id="cleanRemove" type="button" disabled>Убрать выбранное</button>
        </div>
      </div>

      <section class="stats" aria-live="polite">
        <div class="stat">
          <span class="stat-value" id="cleanStatOld">0 Б</span>
          <span class="stat-label">в старых файлах</span>
        </div>
        <div class="stat">
          <span class="stat-value" id="cleanStatJunk">0 Б</span>
          <span class="stat-label">в мусоре</span>
        </div>
        <div class="stat">
          <span class="stat-value" id="cleanStatEmpty">0</span>
          <span class="stat-label" id="cleanStatEmptyLabel">пустых папок</span>
        </div>
      </section>

      <p class="big-note" id="cleanNote"></p>
    </section>

    <section class="empty-state" id="cleanEmpty">
      <div class="empty-art" aria-hidden="true">
        <div class="empty-folder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 20V6a2 2 0 0 1 2-2h7.5L19 8.5V20"/>
            <path d="M8.5 12.5h7M8.5 16h4.5"/>
          </svg>
        </div>
        <span class="empty-chip c1">старые архивы</span>
        <span class="empty-chip c2">мусор</span>
        <span class="empty-chip c3">пустые папки</span>
        <span class="empty-chip c4">хвосты установок</span>
      </div>
      <h2>Тихо освободить папку</h2>
      <p>Проверю, что давно не открывали, что осталось от программ и где завелись пустые папки. Всё выбранное отправится в корзину хаба — вернуть можно одной кнопкой.</p>
      <div class="chips clean-quick" id="cleanQuick"></div>
    </section>`;

  const CHECK = '<span class="check"><input type="checkbox" %CHECK%><span class="box"></span></span>';

  window.HubTools.cleanup = {
    mount(root) {
      root.innerHTML = TEMPLATE;

      const $ = (selector) => root.querySelector(selector);
      const escape = Hub.escapeHtml;
      const plural = Hub.plural;

      const GROUPS = {
        old: { title: "Старые файлы", empty: "Старых файлов не нашлось." },
        junk: { title: "Мусор и кэш", empty: "Мусорных файлов не нашлось." },
        empty: { title: "Пустые папки", empty: "Пустых папок не нашлось." },
      };

      const state = {
        data: null,
        filter: "old",
        selected: new Set(),
        busy: false,
        closed: false,
        lastRun: null,
      };

      const folderInput = $("#cleanFolder");
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

      function fmtDate(timestamp) {
        const date = new Date((Number(timestamp) || 0) * 1000);
        if (Number.isNaN(date.getTime())) return "";
        const months = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
        return `${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
      }

      function itemsOf(group) {
        if (!state.data) return [];
        return state.data[group] || [];
      }

      function countOf(group) {
        return itemsOf(group).length;
      }

      function sizeOf(group) {
        if (!state.data) return 0;
        if (group === "old") return state.data.old_size;
        if (group === "junk") return state.data.junk_size;
        return 0;
      }

      /* --- рендер --- */

      function chip(group) {
        const active = state.filter === group;
        const count = countOf(group);
        const label = GROUPS[group].title;
        return `<button class="chip clean-chip tone-${group}" type="button" data-group="${group}" aria-pressed="${active}">
          <span class="chip-dot"></span><span>${escape(label)}</span><span class="chip-count">${count}</span>
        </button>`;
      }

      function renderChips() {
        $("#cleanChips").innerHTML = ["old", "junk", "empty"].map(chip).join("");
      }

      function rowMarkup(item, index) {
        const picked = state.selected.has(item.path);
        const meta = item.kind === "dir"
          ? "пустая папка"
          : `${Hub.fmtSize(item.size)} · изменён ${fmtDate(item.modified)}`;
        return `
          <label class="clean-row ${picked ? "is-picked" : ""}" style="--row-index:${Math.min(index, 12)}" data-path="${escape(item.path)}">
            ${CHECK.replace("%CHECK%", `${picked ? "checked" : ""} aria-label="Выбрать ${escape(item.name)}"`)}
            <span class="row-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                ${item.kind === "dir"
                  ? '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/>'
                  : '<path d="M6 3.5h7.5L19 9v11.5H6z"/><path d="M13.5 3.5V9H19"/>'}
              </svg>
            </span>
            <span class="clean-text">
              <span class="clean-name">${escape(item.name)}</span>
              <span class="clean-meta">${escape(meta)}</span>
            </span>
            ${item.kind === "file" ? `<span class="clean-size">${Hub.fmtSize(item.size)}</span>` : '<span class="clean-size">—</span>'}
          </label>`;
      }

      function renderList() {
        const items = itemsOf(state.filter);
        const list = $("#cleanList");
        list.innerHTML = items.length
          ? `<div class="clean-group-head"><h3>${escape(GROUPS[state.filter].title)}</h3><span>${items.length} ${plural(items.length, "штука", "штуки", "штук")}</span></div>` +
            items.slice(0, 500).map(rowMarkup).join("")
          : `<p class="big-empty-row">${escape(GROUPS[state.filter].empty)}</p>`;
        syncBar();
      }

      function syncBar() {
        const chosen = [...state.selected];
        const files = (state.data ? ["old", "junk"] : []).flatMap((group) => itemsOf(group));
        const size = files.filter((item) => state.selected.has(item.path)).reduce((sum, item) => sum + item.size, 0);
        $("#cleanSelCount").textContent = String(chosen.length);
        $("#cleanSelText").textContent = plural(chosen.length, "штука", "штуки", "штук");
        $("#cleanSelSize").textContent = size ? Hub.fmtSize(size) : "0 Б";
        const button = $("#cleanRemove");
        button.disabled = chosen.length === 0 || state.busy;
        button.textContent = chosen.length ? `Убрать выбранное (${chosen.length})` : "Убрать выбранное";

        const visible = itemsOf(state.filter);
        const allPicked = visible.length > 0 && visible.every((item) => state.selected.has(item.path));
        $("#cleanMarkAll").textContent = allPicked ? "Снять отметки" : "Отметить всё";
        $("#cleanMarkAll").disabled = visible.length === 0 || state.busy;
      }

      function render() {
        if (!state.data) return;
        $("#cleanEmpty").classList.add("hidden");
        $("#cleanResult").classList.remove("hidden");
        renderChips();
        renderList();

        $("#cleanStatOld").textContent = Hub.fmtSize(state.data.old_size);
        $("#cleanStatJunk").textContent = Hub.fmtSize(state.data.junk_size);
        $("#cleanStatEmpty").textContent = String(countOf("empty"));
        $("#cleanStatEmptyLabel").textContent = plural(countOf("empty"), "пустая папка", "пустые папки", "пустых папок");

        const bits = [`Проверено ${state.data.scanned.toLocaleString("ru-RU")} файлов`];
        if (state.data.links) bits.push(`${state.data.links} ${plural(state.data.links, "ссылка пропущена", "ссылки пропущены", "ссылок пропущено")}`);
        if (state.data.errors?.length) bits.push(`${state.data.errors.length} ${plural(state.data.errors.length, "ошибка", "ошибки", "ошибок")} доступа`);
        if (state.data.truncated) bits.push("папка очень большая — обход остановлен");
        bits.push(`Считалось ${state.data.seconds.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с`);
        $("#cleanNote").textContent = bits.join(" · ");
      }

      function renderUndo() {
        const host = $("#cleanUndo");
        host.classList.toggle("hidden", !state.lastRun);
        host.innerHTML = state.lastRun
          ? `<div class="undo-banner"><span class="undo-banner-text">В корзине хаба: ${state.lastRun.count} ${plural(state.lastRun.count, "штука", "штуки", "штук")} · ${Hub.fmtSize(state.lastRun.size)}</span><button class="btn ghost small" type="button" data-undo>Вернуть</button></div>`
          : "";
      }

      function resetSelection() {
        state.selected.clear();
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
        Hub.setBusy(true, "Ищу, что можно прибрать…");
        try {
          const data = await Hub.api("/api/cleanup/scan", {
            folder: target,
            age_days: Number($("#cleanAge").value),
            include_junk: $("#cleanJunk").checked,
          });
          if (state.closed) return;
          state.data = data;
          resetSelection();
          folderInput.value = data.folder;

          const first = ["old", "junk", "empty"].find((group) => (data[group] || []).length > 0);
          if (!first) {
            $("#cleanResult").classList.add("hidden");
            $("#cleanEmpty").classList.remove("hidden");
            $("#cleanEmpty").querySelector("h2").textContent = "Прибирать нечего";
            $("#cleanEmpty").querySelector("p").textContent =
              "В этой папке нет ни старых файлов, ни мусора, ни пустых папок. Попробуй другой срок или другую папку.";
            return;
          }
          state.filter = first;
          render();
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          Hub.setBusy(false);
        }
      }

      async function removeSelected() {
        const paths = [...state.selected];
        if (!paths.length || state.busy || state.closed) return;
        state.busy = true;
        let changed = false;
        try {
          const mode = await Hub.choose({
            title: "Куда убрать выбранное?",
            text: `${paths.length} ${plural(paths.length, "штука", "штуки", "штук")}. Корзина хаба — не корзина Windows: всё вернётся по кнопке «Вернуть». Удаление навсегда освобождает место сразу, но отменить его нельзя.`,
            choices: [
              { value: "trash", label: "В корзину хаба" },
              { value: "delete", label: "Удалить навсегда", danger: true },
            ],
          });
          if (!mode || state.closed) return;
          if (mode === "delete") {
            const confirmed = await Hub.confirm({
              title: "Удалить без возможности вернуть?",
              text: `Выбранное (${paths.length}) исчезнет навсегда, без корзины. Это действие нельзя отменить.`,
              confirmText: "Удалить навсегда",
              danger: true,
            });
            if (!confirmed || state.closed) return;
          }
          Hub.setBusy(true, mode === "trash" ? "Переношу в корзину…" : "Удаляю навсегда…");
          const result = await Hub.api("/api/cleanup/remove", {
            paths,
            mode,
            confirmed: mode === "delete",
            folder: state.data?.folder || "",
          });
          if (state.closed) return;
          if (result.run_id) {
            state.lastRun = { run_id: result.run_id, count: result.removed_count, size: result.removed_size };
            renderUndo();
          }
          changed = result.removed_count > 0;
          if (result.errors?.length) {
            Hub.toast(result.errors.map((item) => item.reason).join("; "));
          } else {
            Hub.toast(mode === "trash" ? "Убрано в корзину хаба" : "Удалено навсегда");
          }
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          Hub.setBusy(false);
        }
        if (changed && !state.closed) await load(folderInput.value);
      }

      async function undo() {
        if (!state.lastRun || state.busy || state.closed) return;
        state.busy = true;
        Hub.setBusy(true, "Возвращаю на место…");
        let restored = false;
        try {
          const result = await Hub.api("/api/cleanup/undo", { run_id: state.lastRun.run_id });
          if (state.closed) return;
          restored = result.restored_count > 0;
          const latest = await Hub.api("/api/cleanup/last-run");
          if (state.closed) return;
          state.lastRun = latest.last_run;
          renderUndo();
          Hub.toast(result.errors?.length ? result.errors.map((item) => item.reason).join("; ") : "Всё вернулось на место");
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          Hub.setBusy(false);
        }
        if (restored && !state.closed && state.data) await load(folderInput.value);
      }

      /* --- быстрые папки --- */

      const FRIENDLY = {
        downloads: "Загрузки",
        desktop: "Рабочий стол",
        documents: "Документы",
        pictures: "Изображения",
        music: "Музыка",
        videos: "Видео",
      };

      function buildQuickChips() {
        const host = $("#cleanQuick");
        const start = (Hub.defaultFolder || "").replace(/[\\/]+$/, "");
        if (!start) return;
        const chips = [];
        const add = (path, label) => {
          if (!path) return;
          if (chips.some((chip) => chip.path.toLowerCase() === path.toLowerCase())) return;
          chips.push({ path, label });
        };
        const label = (path) => {
          const name = baseName(path);
          return FRIENDLY[name.toLowerCase()] || name;
        };
        add(start, label(start));
        const drive = start.match(/^([A-Za-z]:)/);
        if (drive) add(`${drive[1]}\\`, `Диск ${drive[1]}`);
        host.innerHTML = chips
          .map((chip) => `<button class="chip" type="button" data-path="${escape(chip.path)}">${escape(chip.label)}</button>`)
          .join("");
      }

      /* --- события --- */

      async function openRules() {
        const card = $("#cleanRulesCard");
        const isHidden = card.classList.contains("hidden");
        if (isHidden) {
          try {
            const res = await Hub.api("/api/cleanup/rules");
            $("#cleanRulesSuffixes").value = (res.suffixes || []).join(", ");
            $("#cleanRulesNames").value = (res.names || []).join(", ");
            card.classList.remove("hidden");
          } catch (e) {
            Hub.toast(e.message);
          }
        } else {
          card.classList.add("hidden");
        }
      }

      $("#cleanRulesBtn").addEventListener("click", openRules);

      $("#cleanRulesReset").addEventListener("click", async () => {
        try {
          const res = await Hub.api("/api/cleanup/rules", { reset: true });
          $("#cleanRulesSuffixes").value = (res.suffixes || []).join(", ");
          $("#cleanRulesNames").value = (res.names || []).join(", ");
          Hub.toast("Правила мусора сброшены по умолчанию");
        } catch (e) {
          Hub.toast(e.message);
        }
      });

      $("#cleanRulesSave").addEventListener("click", async () => {
        const suffixes = $("#cleanRulesSuffixes").value.split(",").map((s) => s.trim()).filter(Boolean);
        const names = $("#cleanRulesNames").value.split(",").map((n) => n.trim()).filter(Boolean);
        try {
          const res = await Hub.api("/api/cleanup/rules", { rules: { suffixes, names } });
          $("#cleanRulesSuffixes").value = (res.suffixes || []).join(", ");
          $("#cleanRulesNames").value = (res.names || []).join(", ");
          Hub.toast("Правила мусора сохранены");
        } catch (e) {
          Hub.toast(e.message);
        }
      });

      $("#cleanScan").addEventListener("click", () => load(folderInput.value));
      folderInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") load(folderInput.value);
      });

      $("#cleanBrowse").addEventListener("click", async () => {
        const button = $("#cleanBrowse");
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

      $("#cleanQuick").addEventListener("click", (event) => {
        const chip = event.target.closest("[data-path]");
        if (!chip) return;
        folderInput.value = chip.dataset.path;
        load(chip.dataset.path);
      });

      $("#cleanChips").addEventListener("click", (event) => {
        const chip = event.target.closest("[data-group]");
        if (!chip) return;
        state.filter = chip.dataset.group;
        renderChips();
        renderList();
      });

      $("#cleanList").addEventListener("change", (event) => {
        const row = event.target.closest(".clean-row");
        if (!row) return;
        const path = row.dataset.path;
        if (event.target.checked) state.selected.add(path);
        else state.selected.delete(path);
        row.classList.toggle("is-picked", event.target.checked);
        syncBar();
      });

      $("#cleanMarkAll").addEventListener("click", () => {
        const items = itemsOf(state.filter);
        const allPicked = items.length > 0 && items.every((item) => state.selected.has(item.path));
        items.forEach((item) => {
          if (allPicked) state.selected.delete(item.path);
          else state.selected.add(item.path);
        });
        renderList();
      });

      $("#cleanRemove").addEventListener("click", removeSelected);

      $("#cleanUndo").addEventListener("click", (event) => {
        if (event.target.closest("[data-undo]")) undo();
      });

      Hub.api("/api/cleanup/last-run")
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
