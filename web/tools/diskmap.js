/* Инструмент «Карта диска» */

(function () {
  const SLICE_LIMIT = 10;
  const LEGEND_LIMIT = 260;

  const PALETTE = [
    "var(--pie-1)",
    "var(--pie-2)",
    "var(--pie-3)",
    "var(--pie-4)",
    "var(--pie-5)",
    "var(--pie-6)",
    "var(--pie-7)",
    "var(--pie-8)",
    "var(--pie-9)",
  ];

  const OPEN_ICON =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 5h5v5"/><path d="M19 5l-7.5 7.5"/><path d="M18 14.5v3A2.5 2.5 0 0 1 15.5 20h-9A2.5 2.5 0 0 1 4 17.5v-9A2.5 2.5 0 0 1 6.5 6h3"/></svg>';

  const TEMPLATE = `
    <section class="card picker">
      <div class="picker-head">
        <h2>Какую папку посчитать</h2>
        <span class="pill pill-quiet">круговая карта</span>
      </div>
      <div class="field-row">
        <div class="path-field">
          <svg class="path-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h3.2c.6 0 1.2.2 1.6.7l1 1.05c.2.2.5.35.8.35H18.5A2.5 2.5 0 0 1 21 9.6v7.9A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5z"/>
          </svg>
          <input id="diskFolder" type="text" spellcheck="false" autocomplete="off" aria-label="Путь к папке или диску">
        </div>
        <button class="btn ghost" id="diskBrowse" type="button">Обзор…</button>
        <button class="btn primary" id="diskScan" type="button">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 3.5v9M12 12l6.4 3.7"/><circle cx="12" cy="12" r="8.5"/>
          </svg>
          Построить
        </button>
        <button class="btn ghost hidden" id="diskCancel" type="button">Отменить расчёт</button>
      </div>
      <p class="hint hidden" id="diskProgress" aria-live="polite"></p>
      <p class="hint">Круг делится по размеру папок. Нажми на сектор — заглянешь внутрь и вернёшься по цепочке сверху.</p>
    </section>

    <div id="diskUndo" class="hidden" aria-live="polite"></div>

    <section class="disk-result hidden" id="diskResult">
      <div class="card disk-card">
        <div class="disk-top">
          <nav class="crumbs" id="diskCrumbs" aria-label="Путь по папкам"></nav>
          <div class="disk-actions">
            <button class="btn ghost small" id="diskUp" type="button">Наверх</button>
            <button class="btn ghost small" id="diskOpen" type="button">Открыть папку</button>
          </div>
        </div>

        <div class="disk-board">
          <div class="donut-wrap">
            <div class="donut" id="diskDonut"></div>
          </div>
          <div class="disk-legend" id="diskLegend"></div>
        </div>
        <section id="diskFiles" class="hidden" aria-label="Файлы в этой папке">
          <div class="disk-files-header">
            <div><h2>Файлы в этой папке</h2><p class="hint">От самых больших к маленьким. Корзина хаба позволяет вернуть файл.</p></div>
            <button class="btn ghost small" id="diskFilesClose" type="button">Скрыть файлы</button>
          </div>
          <div class="disk-file-list" id="diskFileList"></div>
          <p class="disk-file-more" id="diskFilesNote" aria-live="polite"></p>
          <button class="btn ghost small hidden" id="diskFilesMore" type="button">Показать ещё</button>
        </section>
      </div>

      <section class="stats" aria-live="polite">
        <div class="stat">
          <span class="stat-value" id="diskStatTotal">0 Б</span>
          <span class="stat-label">занимает папка</span>
        </div>
        <div class="stat">
          <span class="stat-value" id="diskStatDirs">0</span>
          <span class="stat-label" id="diskStatDirsLabel">папок</span>
        </div>
        <div class="stat">
          <span class="stat-value" id="diskStatFiles">0</span>
          <span class="stat-label" id="diskStatFilesLabel">файлов</span>
        </div>
      </section>

      <p class="disk-note" id="diskNote"></p>
    </section>

    <section class="empty-state" id="diskEmpty">
      <div class="empty-art" aria-hidden="true">
        <div class="empty-folder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="8.5"/>
            <path d="M12 12V3.5M12 12l7.3 4.2"/>
          </svg>
        </div>
        <span class="empty-chip c1">видео</span>
        <span class="empty-chip c2">кэш браузера</span>
        <span class="empty-chip c3">фото</span>
        <span class="empty-chip c4">игры</span>
      </div>
      <h2>Куда уходит место</h2>
      <p>Выбери папку или целый диск — покажу круговую диаграмму: какой кусок занимает каждая папка. Сектор можно нажать и заглянуть внутрь.</p>
      <div class="chips disk-quick" id="diskQuick"></div>
    </section>`;

  window.HubTools.diskmap = {
    mount(root) {
      root.innerHTML = TEMPLATE;

      const $ = (selector) => root.querySelector(selector);
      const escape = Hub.escapeHtml;
      const plural = Hub.plural;

      const state = {
        path: "",
        data: null,
        trail: [],
        busy: false,
        closed: false,
        scan: null,
        hover: null,
        files: [],
        filesVisible: false,
        fileLimit: 100,
        lastRun: null,
      };

      const folderInput = $("#diskFolder");
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
        const name = clean.slice(cut + 1);
        return name || clean || "Диск";
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

      function percentOf(size, total) {
        if (!total) return "0%";
        const value = (size / total) * 100;
        if (value > 0 && value < 1) return "<1%";
        return `${Math.round(value)}%`;
      }

      function filesLabel(count) {
        return `${count} ${plural(count, "файл", "файла", "файлов")}`;
      }

      function metaOf(entry) {
        if (entry.kind === "dir") return `папка · ${filesLabel(entry.count)}`;
        if (entry.kind === "files") return `${filesLabel(entry.count)} в корне`;
        return "остальные папки";
      }

      /* --- построение диаграммы --- */

      function chartEntries() {
        const entries = state.data ? state.data.entries : [];
        if (entries.length <= SLICE_LIMIT) return entries;

        const head = entries.slice(0, SLICE_LIMIT - 1);
        const tail = entries.slice(SLICE_LIMIT - 1);
        const size = tail.reduce((sum, entry) => sum + entry.size, 0);
        return [
          ...head,
          {
            name: `Ещё ${tail.length} ${plural(tail.length, "папка", "папки", "папок")}`,
            kind: "rest",
            size,
            count: 0,
            path: null,
            color: "var(--pie-rest)",
          },
        ];
      }

      function sliceMarkup(entry, index, total, sliceCount) {
        const radius = 38;
        const circumference = 2 * Math.PI * radius;
        const fraction = total > 0 ? entry.size / total : 0;
        const gap =
          sliceCount > 1 && fraction > 0 ? Math.min(1.6, fraction * circumference * 0.4) : 0;
        const length = Math.max(0, fraction * circumference - gap);
        const dash = `${length.toFixed(2)} ${(circumference - length).toFixed(2)}`;
        const start = state.segmentStart || 0;
        state.segmentStart = start + fraction * circumference;

        return `<circle class="donut-slice" data-i="${index}" cx="50" cy="50" r="${radius}"
          fill="none" stroke="${entry.color}" stroke-width="13"
          stroke-dasharray="${dash}" stroke-dashoffset="${(-start).toFixed(2)}"
          transform="rotate(-90 50 50)"></circle>`;
      }

      function renderDonut() {
        if (!state.data) {
          $("#diskDonut").innerHTML = "";
          return;
        }
        const entries = chartEntries();
        const total = entries.reduce((sum, entry) => sum + entry.size, 0);
        const slices = [];
        for (let index = 0; index < entries.length; index += 1) {
          slices.push(sliceMarkup(entries[index], index, total, entries.length));
        }

        const title = state.data.folder;
        $("#diskDonut").innerHTML = `
          <svg class="donut-svg" viewBox="0 0 100 100" role="img" aria-label="Размеры внутри ${escape(title)}">
            <circle cx="50" cy="50" r="31" fill="none" stroke="var(--border)" stroke-width="0.7"></circle>
            <g class="donut-slices">${slices.join("") || ""}</g>
          </svg>
          <div class="donut-center">
            <span class="donut-value" id="diskCenterValue">${Hub.fmtSize(total)}</span>
            <span class="donut-note" id="diskCenterNote">в этой папке</span>
          </div>`;

        const svg = $("#diskDonut .donut-svg");
        const nodes = svg.querySelectorAll(".donut-slice");

        nodes.forEach((node) => {
          const entry = entries[Number(node.dataset.i)];
          node.addEventListener("mouseenter", () => setHover(entry, node));
          node.addEventListener("mouseleave", () => setHover(null));
          if (entry.path && entry.kind === "dir") {
            node.addEventListener("click", () => drill(entry));
          }
        });
      }

      function renderCrumbs() {
        const crumbs = state.trail
          .map((item, index) => {
            const last = index === state.trail.length - 1;
            const label = escape(item.name || baseName(item.path));
            if (last) return `<span class="crumb is-here">${label}</span>`;
            return `<button class="crumb" type="button" data-i="${index}">${label}</button>`;
          })
          .join('<span class="crumb-sep" aria-hidden="true">›</span>');

        const host = $("#diskCrumbs");
        host.innerHTML = crumbs;
        host.scrollLeft = host.scrollWidth;
        $("#diskUp").disabled = state.trail.length <= 1;
      }

      function renderLegend() {
        if (!state.data) return;
        const entries = state.data.entries;
        const total = entries.reduce((sum, entry) => sum + entry.size, 0);
        const rows = entries.slice(0, LEGEND_LIMIT).map((entry, index) => {
          const go =
            entry.kind === "dir"
              ? '<span class="disk-go" aria-hidden="true">›</span>'
              : entry.kind === "files"
                ? `<span class="disk-go" aria-hidden="true">${OPEN_ICON}</span>`
                : "";
          return `
            <button class="disk-row" type="button" data-i="${index}" ${entry.kind === "rest" ? "disabled" : ""}>
              <span class="disk-dot" style="--c: ${entry.color}"></span>
              <span class="disk-row-main">
                <span class="disk-row-name">${escape(entry.name)}</span>
                <span class="disk-row-meta">${metaOf(entry)}</span>
              </span>
              <span class="disk-row-size">${Hub.fmtSize(entry.size)}</span>
              <span class="disk-row-share">${percentOf(entry.size, total)}</span>
              ${go}
            </button>`;
        });

        if (entries.length > LEGEND_LIMIT) {
          const rest = entries.length - LEGEND_LIMIT;
          rows.push(
            `<p class="disk-more">и ещё ${rest} ${plural(rest, "папка", "папки", "папок")} — открой папку побольше, чтобы увидеть их.</p>`,
          );
        }

        if (entries.length === 0) {
          rows.push('<p class="disk-more">Здесь нет ни файлов, ни папок.</p>');
        }

        $("#diskLegend").innerHTML = rows.join("");
        const legend = $("#diskLegend");
        legend.scrollTop = 0;
        legend.classList.toggle("is-scroll", legend.scrollHeight > legend.clientHeight + 4);
      }

      function renderStats() {
        const data = state.data;
        if (!data) return;
        $("#diskStatTotal").textContent = Hub.fmtSize(data.total);
        $("#diskStatDirs").textContent = data.dirs.toLocaleString("ru-RU");
        $("#diskStatDirsLabel").textContent = plural(data.dirs, "папка", "папки", "папок");
        $("#diskStatFiles").textContent = data.files.toLocaleString("ru-RU");
        $("#diskStatFilesLabel").textContent = plural(data.files, "файл", "файла", "файлов");

        const bits = [
          data.seconds < 0.15
            ? "Считалось мгновенно"
            : `Считалось ${data.seconds.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} с`,
        ];
        if (data.links) {
          bits.push(`${data.links} ${plural(data.links, "ссылка пропущена", "ссылки пропущены", "ссылок пропущено")}`);
        }
        const skipped = data.error_count ?? data.errors.length;
        if (skipped) bits.push(`пропущено записей: ${skipped}`);
        if (data.truncated) bits.push("слишком много файлов — часть не посчитана");
        $("#diskNote").textContent = bits.join(" · ");
      }

      function showEmptyState(title, text) {
        $("#diskEmpty").classList.remove("hidden");
        $("#diskEmpty").querySelector("h2").textContent = title;
        $("#diskEmpty").querySelector("p").textContent = text;
      }

      function render() {
        if (!state.data) return;
        state.segmentStart = 0;
        $("#diskEmpty").classList.add("hidden");
        $("#diskResult").classList.remove("hidden");
        renderCrumbs();
        renderDonut();
        renderLegend();
        renderStats();
        const donut = $("#diskDonut");
        if (donut) donut.classList.remove("is-hover");
      }

      function setHover(entry, node) {
        const donut = $("#diskDonut");
        const value = $("#diskCenterValue");
        const note = $("#diskCenterNote");
        if (!donut) return;

        if (!entry) {
          state.hover = null;
          donut.classList.remove("is-hover");
          donut.querySelectorAll(".donut-slice").forEach((item) => item.classList.remove("is-hot"));
          $("#diskLegend").querySelectorAll(".disk-row").forEach((row) => row.classList.remove("is-hot"));
          if (state.data) {
            const total = state.data.entries.reduce((sum, item) => sum + item.size, 0);
            value.textContent = Hub.fmtSize(total);
            note.textContent = "в этой папке";
          }
          return;
        }

        state.hover = entry;
        donut.classList.add("is-hover");
        if (node) {
          donut.querySelectorAll(".donut-slice").forEach((item) => item.classList.remove("is-hot"));
          node.classList.add("is-hot");
        }
        const index = state.data ? state.data.entries.indexOf(entry) : -1;
        $("#diskLegend").querySelectorAll(".disk-row").forEach((row) => {
          row.classList.toggle("is-hot", Number(row.dataset.i) === index);
        });

        value.textContent = Hub.fmtSize(entry.size);
        const total = state.data.entries.reduce((sum, item) => sum + item.size, 0);
        note.textContent = `${percentOf(entry.size, total)} · ${entry.name}`;
      }

      function renderUndo() {
        const host = $("#diskUndo");
        host.classList.toggle("hidden", !state.lastRun);
        host.innerHTML = state.lastRun ? `<div class="undo-banner"><span class="undo-banner-text">В корзине хаба: ${state.lastRun.count} ${plural(state.lastRun.count, "файл", "файла", "файлов")} · ${Hub.fmtSize(state.lastRun.size)}</span><button class="btn ghost small" type="button" data-undo>Вернуть</button></div>` : "";
      }

      function renderFiles() {
        $("#diskFiles").classList.toggle("hidden", !state.filesVisible);
        $("#diskFileList").innerHTML = state.files.slice(0, state.fileLimit).map((file, index) => `
          <div class="disk-file-row" style="--row-index:${Math.min(index, 12)}">
            <span class="disk-file-name" title="${escape(file.path)}">${escape(file.name)}</span>
            <span class="disk-row-size">${Hub.fmtSize(file.size)}</span>
            <button class="btn ghost small disk-delete" type="button" data-delete="${index}" aria-label="Удалить ${escape(file.name)}">Удалить</button>
          </div>`).join("");
        $("#diskFilesMore").classList.toggle("hidden", state.fileLimit >= state.files.length);
      }

      async function openFiles() {
        if (state.busy || !state.data || state.closed) return;
        if (state.data.read_only_root) {
          Hub.toast("Для списка файлов выбери подпапку.");
          return;
        }
        state.busy = true;
        Hub.setBusy(true, "Читаю файлы…");
        try {
          const data = await Hub.api("/api/diskmap/files", { folder: state.path });
          if (state.closed) return;
          state.files = data.files;
          state.filesVisible = true;
          state.fileLimit = 100;
          renderFiles();
          $("#diskFilesNote").textContent = [
            data.files.length ? `${data.files.length} ${plural(data.files.length, "файл", "файла", "файлов")}` : "В этой папке больше нет файлов.",
            data.truncated ? "Список неполный: достигнут предел сканирования." : "",
            data.errors?.length ? "Некоторые файлы недоступны." : "",
          ].filter(Boolean).join(" · ");
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          Hub.setBusy(false);
        }
      }

      async function deleteFile(index) {
        const file = state.files[index];
        if (!file || state.busy || state.closed) return;
        state.busy = true;
        let busyShown = false;
        let changed = false;
        try {
          const mode = await Hub.choose({
            title: "Что сделать с файлом?",
            text: `${file.name} · ${Hub.fmtSize(file.size)}. Корзина хаба — не корзина Windows: файл можно вернуть здесь. Перенос в неё не освобождает место на этом диске.`,
            choices: [
              { value: "trash", label: "В корзину хаба" },
              { value: "delete", label: "Удалить навсегда", danger: true },
            ],
          });
          if (!mode || state.closed) return;
          if (mode === "delete") {
            const confirmed = await Hub.confirm({title: "Удалить без возможности вернуть?", text: `Файл «${file.name}» будет удалён навсегда, без корзины. Отменить это действие нельзя.`, confirmText: "Удалить навсегда", danger: true});
            if (!confirmed || state.closed) return;
          }
          Hub.setBusy(true, mode === "trash" ? "Перемещаю в корзину…" : "Удаляю файл…");
          busyShown = true;
          const result = await Hub.api("/api/diskmap/remove", {path: file.path, mode, confirmed: mode === "delete"});
          if (state.closed) return;
          if (result.errors?.length) throw new Error(result.errors.map(item => item.reason).join("; "));
          changed = result.removed_count > 0;
          if (result.run_id) state.lastRun = {run_id: result.run_id, count: result.removed_count, size: result.removed_size};
          renderUndo();
          Hub.toast(mode === "trash" ? "Файл в корзине хаба — можно вернуть" : "Файл удалён навсегда");
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          if (busyShown) Hub.setBusy(false);
        }
        if (changed && !state.closed) {
          await load(state.path, state.trail);
          await openFiles();
        }
      }

      /* --- загрузка --- */

      function cancelScan() {
        if (!state.scan) return;
        state.scan.cancelled = true;
        if (!state.closed) {
          $("#diskCancel").disabled = true;
          $("#diskProgress").textContent = "Отменяю обход…";
        }
        if (state.scan.id && !state.scan.cancelRequest) {
          state.scan.cancelRequest = Hub.api("/api/diskmap/jobs/cancel", { id: state.scan.id }).catch(() => null);
        }
      }

      async function runScan(target) {
        if (!Hub.diskmapJobs) return Hub.api("/api/diskmap/scan", { folder: target });
        const current = state.scan = { cancelled: false, id: null };
        const progress = $("#diskProgress");
        const cancel = $("#diskCancel");
        progress.classList.remove("hidden");
        progress.textContent = "Считаю размеры…";
        cancel.classList.remove("hidden");
        cancel.disabled = false;
        let complete = false;
        let cancelling = false;
        try {
          const { id } = await Hub.api("/api/diskmap/jobs/start", { folder: target });
          current.id = id;
          while (!state.closed) {
            if (current.cancelled && !cancelling) {
              cancelScan();
              const response = await current.cancelRequest;
              if (!response || state.closed) return null;
              if (response.state === "cancelled") return { cancelled: true };
              cancelling = true;
            }
            const report = await Hub.api("/api/diskmap/jobs/status", { id });
            if (report.state === "done") {
              complete = true;
              return current.cancelled ? { cancelled: true } : report.result;
            }
            if (report.state === "failed" || report.state === "cancelled") {
              complete = true;
              if (!current.cancelled && report.error) throw new Error(report.error);
              return { cancelled: true };
            }
            if (!current.cancelled && !state.closed) {
              const prefix = report.warning ? "Сбой Rust Worker. Продолжаю в Python." : "Обход";
              progress.textContent = `${prefix} · записей: ${report.entries} · файлов: ${report.files} · ${Hub.fmtSize(report.bytes)}`;
            }
            await new Promise(resolve => setTimeout(resolve, 250));
          }
          return null;
        } finally {
          if (!complete) cancelScan();
          state.scan = null;
          if (!state.closed) {
            cancel.classList.add("hidden");
            progress.classList.add("hidden");
          }
        }
      }

      async function load(path, trailAfter = null) {
        if (state.busy) return;
        const input = String(path || "").trim();
        const target = /^[a-z]:$/i.test(input) ? `${input}\\` : input;
        if (!target) {
          Hub.toast("Сначала выбери папку");
          folderInput.focus();
          return;
        }

        state.busy = true;
        if (!Hub.diskmapJobs) Hub.setBusy(true, "Считаю размеры…");
        try {
          const data = await runScan(target);
          if (state.closed) return;
          if (!data) {
            Hub.toast("Отмена запрошена. Подтверждение от Hub не получено.");
            return;
          }
          if (data.cancelled) {
            Hub.toast("Расчёт отменён.");
            return;
          }
          if (data.fallback_reason) Hub.toast(`Сбой Rust Worker. Расчёт завершён в Python. ${data.fallback_reason}`);

          data.entries = data.entries.map((entry, index) => ({
            ...entry,
            color:
              index < SLICE_LIMIT - 1 || data.entries.length <= SLICE_LIMIT
                ? PALETTE[index % PALETTE.length]
                : "var(--pie-rest)",
          }));

          state.filesVisible = false;
          state.files = [];
          $("#diskFiles").classList.add("hidden");
          state.data = data;
          state.path = data.folder;
          state.trail = trailAfter || [{ path: data.folder, name: data.name || baseName(data.folder) }];
          folderInput.value = data.folder;
          state.hover = null;

          if (data.entries.length === 0) {
            showEmptyState("Здесь пусто", "В этой папке нет ни файлов, ни подпапок.");
            $("#diskResult").classList.add("hidden");
            return;
          }

          render();
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          if (!Hub.diskmapJobs && !state.closed) Hub.setBusy(false);
        }
      }

      function drill(entry) {
        if (!entry || entry.kind !== "dir" || !entry.path) return;
        if (state.busy) return;
        load(entry.path, [...state.trail, { path: entry.path, name: entry.name }]);
      }

      /* --- быстрые папки в пустом состоянии --- */

      function buildQuickChips() {
        const host = $("#diskQuick");
        const start = (Hub.defaultFolder || "").replace(/[\\/]+$/, "");
        if (!start) return;

        const chips = [];
        const add = (path, label) => {
          if (!path) return;
          if (chips.some((chip) => chip.path.toLowerCase() === path.toLowerCase())) return;
          chips.push({ path, label });
        };

        add(start, friendlyName(start));
        add(parentOf(start), friendlyName(parentOf(start) || ""));
        const drive = start.match(/^([A-Za-z]:)/);
        if (drive) add(`${drive[1]}\\`, `Диск ${drive[1]}`);

        host.innerHTML = chips
          .map(
            (chip) =>
              `<button class="chip" type="button" data-path="${escape(chip.path)}">${escape(chip.label)}</button>`,
          )
          .join("");
      }

      /* --- события --- */

      $("#diskScan").addEventListener("click", () => load(folderInput.value));
      $("#diskCancel").addEventListener("click", cancelScan);
      folderInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") load(folderInput.value);
      });

      $("#diskBrowse").addEventListener("click", async () => {
        const button = $("#diskBrowse");
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

      $("#diskQuick").addEventListener("click", (event) => {
        const chip = event.target.closest("[data-path]");
        if (!chip) return;
        folderInput.value = chip.dataset.path;
        load(chip.dataset.path);
      });

      $("#diskCrumbs").addEventListener("click", (event) => {
        const crumb = event.target.closest("[data-i]");
        if (!crumb) return;
        const index = Number(crumb.dataset.i);
        if (Number.isNaN(index) || index >= state.trail.length - 1) return;
        load(state.trail[index].path, state.trail.slice(0, index + 1));
      });

      $("#diskUp").addEventListener("click", () => {
        if (state.trail.length <= 1) return;
        const parent = state.trail[state.trail.length - 2];
        load(parent.path, state.trail.slice(0, -1));
      });

      $("#diskOpen").addEventListener("click", async () => {
        if (!state.data) return;
        try {
          await Hub.api("/api/open", { path: state.data.folder });
        } catch (error) {
          Hub.toast(error.message);
        }
      });

      $("#diskLegend").addEventListener("click", async (event) => {
        const row = event.target.closest(".disk-row");
        if (!row) return;
        const entry = state.data ? state.data.entries[Number(row.dataset.i)] : null;
        if (!entry) return;
        if (entry.kind === "dir") {
          drill(entry);
        } else if (entry.kind === "files") {
          await openFiles();
        }
      });

      $("#diskLegend").addEventListener("mouseover", (event) => {
        const row = event.target.closest(".disk-row");
        if (!row || !state.data) return;
        const entry = state.data.entries[Number(row.dataset.i)];
        if (!entry) return;
        const chartIndex = chartEntries().indexOf(entry);
        const node = chartIndex >= 0 ? $(`#diskDonut .donut-slice[data-i="${chartIndex}"]`) : null;
        setHover(entry, node);
      });

      $("#diskLegend").addEventListener("mouseleave", () => setHover(null));

      $("#diskFileList").addEventListener("click", async (event) => {
        const button = event.target.closest("[data-delete]");
        if (button) await deleteFile(Number(button.dataset.delete));
      });
      $("#diskFilesClose").addEventListener("click", () => {
        state.filesVisible = false;
        renderFiles();
      });
      $("#diskFilesMore").addEventListener("click", () => {
        state.fileLimit += 100;
        renderFiles();
      });
      $("#diskUndo").addEventListener("click", async (event) => {
        if (!event.target.closest("[data-undo]") || state.busy || !state.lastRun) return;
        state.busy = true;
        Hub.setBusy(true, "Возвращаю файл…");
        let restored = false;
        try {
          const result = await Hub.api("/api/diskmap/undo", {run_id: state.lastRun.run_id});
          if (state.closed) return;
          restored = result.restored_count > 0;
          const latest = await Hub.api("/api/diskmap/last-run");
          if (state.closed) return;
          state.lastRun = latest.last_run;
          renderUndo();
          Hub.toast(result.errors?.length ? result.errors.map(item => item.reason).join("; ") : "Файл возвращён на место");
        } catch (error) {
          if (!state.closed) Hub.toast(error.message);
        } finally {
          state.busy = false;
          Hub.setBusy(false);
        }
        if (restored && !state.closed && state.data) {
          await load(state.path, state.trail);
          await openFiles();
        }
      });

      Hub.api("/api/diskmap/last-run").then((data) => {
        if (state.closed || state.lastRun) return;
        state.lastRun = data.last_run;
        renderUndo();
      }).catch((error) => { if (!state.closed) Hub.toast(error.message); });
      buildQuickChips();

      return () => {
        if (state.busy && !Hub.diskmapJobs) Hub.setBusy(false);
        state.closed = true;
        cancelScan();
        Hub.dismissDialog();
      };
    },
  };
})();
