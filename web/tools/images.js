/* Инструмент «Сжатие картинок» */

(function () {
  const TEMPLATE = `
    <section class="card img-dropzone" id="imgDropZone" tabindex="0" role="button" aria-label="Зона загрузки картинок">
      <input type="file" id="imgFileInput" multiple accept="image/png,image/jpeg,image/webp,image/gif,image/bmp" class="hidden">
      <div class="img-drop-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/>
          <circle cx="8.5" cy="9" r="1.5"/>
          <path d="M20.5 15.5l-5-5-8 8M14.5 13.5l3.5 3.5"/>
        </svg>
      </div>
      <p class="img-drop-title">Перетащи картинки сюда или <span>выбери на диске</span></p>
      <p class="img-drop-hint">PNG, JPEG, WebP, GIF, BMP · Работает также вставка из буфера обмена (Ctrl + V)</p>
    </section>

    <section class="card img-settings">
      <div class="img-setting-group">
        <span class="img-setting-label">Формат:</span>
        <div class="clip-filters" id="imgFormatGroup" role="tablist">
          <button class="pill is-active" type="button" data-format="image/webp" data-ext="webp">WebP</button>
          <button class="pill" type="button" data-format="image/jpeg" data-ext="jpg">JPEG</button>
          <button class="pill" type="button" data-format="image/png" data-ext="png">PNG</button>
        </div>
      </div>

      <div class="img-setting-group" id="imgQualityGroup">
        <span class="img-setting-label">Качество: <b id="imgQualityVal">80%</b></span>
        <input type="range" id="imgQualitySlider" min="10" max="100" value="80" class="img-slider">
      </div>

      <div class="img-setting-group">
        <span class="img-setting-label">Размер:</span>
        <select id="imgResizeSelect" class="img-select">
          <option value="orig">Без изменений</option>
          <option value="1920">Full HD (до 1920 px)</option>
          <option value="1280">HD (до 1280 px)</option>
          <option value="800">Веб (до 800 px)</option>
          <option value="400">Иконка / Аватар (до 400 px)</option>
        </select>
      </div>
    </section>

    <section class="card img-batch-bar hidden" id="imgBatchBar">
      <div class="img-batch-info" id="imgBatchInfo">Готово</div>
      <div class="img-batch-actions">
        <button class="btn ghost small" id="imgSaveAll" type="button">Сохранить в папку…</button>
        <button class="btn primary small" id="imgDownloadAll" type="button">Скачать все</button>
        <button class="btn ghost small danger" id="imgClearAll" type="button">Очистить</button>
      </div>
    </section>

    <div class="img-grid" id="imgGrid"></div>

    <section class="empty-state" id="imgEmpty">
      <div class="empty-art" aria-hidden="true">
        <div class="empty-folder">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/>
            <circle cx="8.5" cy="9" r="1.5"/>
            <path d="M20.5 15.5l-5-5-8 8M14.5 13.5l3.5 3.5"/>
          </svg>
        </div>
      </div>
      <h2>Быстрое сжатие и конвертация без потери качества</h2>
      <p>Файлы обрабатываются прямо на компьютере: исходные файлы не перезаписываются.</p>
    </section>`;

  const DOWNLOAD_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>';
  const SAVE_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>';
  const TRASH_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 7h15M9.5 7V5.2A1.7 1.7 0 0 1 11.2 3.5h1.6a1.7 1.7 0 0 1 1.7 1.7V7M6.5 7l.8 12a1.8 1.8 0 0 0 1.8 1.7h5.8A1.8 1.8 0 0 0 16.7 19l.8-12"/></svg>';

  window.HubTools.images = {
    mount(root) {
      root.innerHTML = TEMPLATE;

      const $ = (selector) => root.querySelector(selector);
      const escape = Hub.escapeHtml;
      const fmtSize = Hub.fmtSize;

      const state = {
        items: [],
        format: "image/webp",
        ext: "webp",
        quality: 0.8,
        maxDim: "orig",
        closed: false,
      };

      /* --- Обработка изображений через Canvas --- */

      function processFile(file) {
        return new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onerror = () => reject(new Error("Не удалось прочитать файл"));
          reader.onload = () => {
            const img = new Image();
            img.onerror = () => reject(new Error("Не удалось декодировать изображение"));
            img.onload = () => {
              let width = img.naturalWidth || img.width;
              let height = img.naturalHeight || img.height;

              const maxLimit = state.maxDim === "orig" ? 0 : Number(state.maxDim) || 0;
              if (maxLimit > 0 && (width > maxLimit || height > maxLimit)) {
                if (width >= height) {
                  height = Math.round((height * maxLimit) / width);
                  width = maxLimit;
                } else {
                  width = Math.round((width * maxLimit) / height);
                  height = maxLimit;
                }
              }

              const canvas = document.createElement("canvas");
              canvas.width = Math.max(1, width);
              canvas.height = Math.max(1, height);
              const ctx = canvas.getContext("2d");
              ctx.imageSmoothingEnabled = true;
              ctx.imageSmoothingQuality = "high";
              ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

              const mime = state.format;
              const quality = mime === "image/png" ? undefined : state.quality;

              canvas.toBlob((blob) => {
                if (!blob) {
                  return reject(new Error("Ошибка конвертации"));
                }
                const originalName = file.name || "image.png";
                const baseName = originalName.replace(/\.[^.]+$/, "");
                const newName = `${baseName}.${state.ext}`;
                const thumbUrl = URL.createObjectURL(blob);

                const item = {
                  id: `img_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
                  originalName,
                  newName,
                  origSize: file.size,
                  newSize: blob.size,
                  origDims: `${img.naturalWidth || img.width}×${img.naturalHeight || img.height}`,
                  newDims: `${canvas.width}×${canvas.height}`,
                  blob,
                  thumbUrl,
                  format: state.ext.toUpperCase(),
                };
                resolve(item);
              }, mime, quality);
            };
            img.src = reader.result;
          };
          reader.readAsDataURL(file);
        });
      }

      async function handleFiles(fileList) {
        if (!fileList || !fileList.length) return;
        Hub.setBusy(true, "Сжимаю картинки…");
        try {
          for (const file of Array.from(fileList)) {
            if (!file.type.startsWith("image/") && !/\.(png|jpe?g|webp|gif|bmp)$/i.test(file.name)) {
              continue;
            }
            try {
              const item = await processFile(file);
              state.items.unshift(item);
            } catch (err) {
              Hub.toast(`Ошибка с ${file.name}: ${err.message}`);
            }
          }
          render();
        } finally {
          Hub.setBusy(false);
        }
      }

      function downloadItem(item) {
        const link = document.createElement("a");
        link.href = item.thumbUrl;
        link.download = item.newName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }

      async function saveItemToFolder(item) {
        try {
          Hub.setBusy(true, "Сохраняю на диск…");
          const info = await Hub.api("/api/info");
          const targetFolder = info.default_folder || "";
          
          // Конвертируем blob в base64
          const reader = new FileReader();
          reader.onloadend = async () => {
            try {
              const res = await Hub.api("/api/images/save", {
                folder: targetFolder,
                filename: item.newName,
                data: reader.result,
              });
              Hub.toast(`Сохранено: ${res.filename}`);
            } catch (err) {
              Hub.toast(`Ошибка сохранения: ${err.message}`);
            } finally {
              Hub.setBusy(false);
            }
          };
          reader.readAsDataURL(item.blob);
        } catch (err) {
          Hub.setBusy(false);
          Hub.toast(err.message);
        }
      }

      function render() {
        const grid = $("#imgGrid");
        const empty = $("#imgEmpty");
        const batchBar = $("#imgBatchBar");

        if (state.items.length === 0) {
          grid.innerHTML = "";
          empty.classList.remove("hidden");
          batchBar.classList.add("hidden");
          return;
        }

        empty.classList.add("hidden");
        batchBar.classList.remove("hidden");

        let totalOrig = 0;
        let totalNew = 0;
        state.items.forEach((item) => {
          totalOrig += item.origSize;
          totalNew += item.newSize;
        });
        const savedBytes = Math.max(0, totalOrig - totalNew);
        const percent = totalOrig > 0 ? Math.round((savedBytes / totalOrig) * 100) : 0;
        $("#imgBatchInfo").innerHTML = `Обработано: <b>${state.items.length}</b> · Было: <b>${fmtSize(totalOrig)}</b> ➔ Стало: <b>${fmtSize(totalNew)}</b> · Сэкономлено: <b class="img-saved-val">${fmtSize(savedBytes)} (-${percent}%)</b>`;

        grid.innerHTML = state.items
          .map((item) => {
            const saved = Math.max(0, item.origSize - item.newSize);
            const itemPercent = item.origSize > 0 ? Math.round((saved / item.origSize) * 100) : 0;
            const diffClass = item.newSize <= item.origSize ? "is-smaller" : "is-bigger";

            return `
              <article class="card img-card" data-id="${escape(item.id)}">
                <div class="img-preview">
                  <img src="${item.thumbUrl}" alt="${escape(item.newName)}" loading="lazy">
                </div>
                <div class="img-details">
                  <div class="img-details-head">
                    <span class="img-filename" title="${escape(item.newName)}">${escape(item.newName)}</span>
                    <span class="pill pill-quiet">${escape(item.format)}</span>
                  </div>
                  <div class="img-stats">
                    <span class="img-stat-dims">${escape(item.origDims)} ➔ ${escape(item.newDims)}</span>
                    <span class="img-stat-sizes ${diffClass}">
                      ${fmtSize(item.origSize)} ➔ <b>${fmtSize(item.newSize)}</b>
                      <span class="pill ${itemPercent > 0 ? "pill-good" : "pill-quiet"}">-${itemPercent}%</span>
                    </span>
                  </div>
                </div>
                <div class="img-card-actions">
                  <button class="mini-btn" type="button" data-act="download" title="Скачать">${DOWNLOAD_ICON}</button>
                  <button class="mini-btn" type="button" data-act="save" title="Сохранить в папку">${SAVE_ICON}</button>
                  <button class="mini-btn danger" type="button" data-act="delete" title="Удалить">${TRASH_ICON}</button>
                </div>
              </article>`;
          })
          .join("");
      }

      /* --- События и слушатели --- */

      const dropZone = $("#imgDropZone");
      const fileInput = $("#imgFileInput");

      dropZone.addEventListener("click", () => fileInput.click());
      dropZone.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          fileInput.click();
        }
      });

      fileInput.addEventListener("change", () => {
        if (fileInput.files.length) {
          handleFiles(fileInput.files);
          fileInput.value = "";
        }
      });

      dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("is-dragover");
      });

      dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("is-dragover");
      });

      dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("is-dragover");
        if (e.dataTransfer && e.dataTransfer.files.length) {
          handleFiles(e.dataTransfer.files);
        }
      });

      function handlePaste(e) {
        if (state.closed) return;
        if (e.clipboardData && e.clipboardData.files.length) {
          handleFiles(e.clipboardData.files);
        }
      }
      window.addEventListener("paste", handlePaste);

      // Формат
      $("#imgFormatGroup").addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-format]");
        if (!btn) return;
        $("#imgFormatGroup").querySelectorAll("button").forEach((b) => b.classList.remove("is-active"));
        btn.classList.add("is-active");
        state.format = btn.dataset.format;
        state.ext = btn.dataset.ext;
        $("#imgQualityGroup").style.display = state.format === "image/png" ? "none" : "";
      });

      // Качество
      $("#imgQualitySlider").addEventListener("input", (e) => {
        const val = Number(e.target.value) || 80;
        state.quality = val / 100;
        $("#imgQualityVal").textContent = `${val}%`;
      });

      // Размер
      $("#imgResizeSelect").addEventListener("change", (e) => {
        state.maxDim = e.target.value;
      });

      // Действия на карточках
      $("#imgGrid").addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-act]");
        if (!btn) return;
        const card = btn.closest(".img-card");
        if (!card) return;
        const item = state.items.find((i) => i.id === card.dataset.id);
        if (!item) return;

        const act = btn.dataset.act;
        if (act === "download") {
          downloadItem(item);
        } else if (act === "save") {
          saveItemToFolder(item);
        } else if (act === "delete") {
          URL.revokeObjectURL(item.thumbUrl);
          state.items = state.items.filter((i) => i.id !== item.id);
          render();
        }
      });

      // Массовые действия
      $("#imgDownloadAll").addEventListener("click", () => {
        state.items.forEach((item, idx) => {
          setTimeout(() => downloadItem(item), idx * 200);
        });
      });

      $("#imgSaveAll").addEventListener("click", async () => {
        for (const item of state.items) {
          await saveItemToFolder(item);
        }
      });

      $("#imgClearAll").addEventListener("click", () => {
        state.items.forEach((i) => URL.revokeObjectURL(i.thumbUrl));
        state.items = [];
        render();
      });

      render();

      return () => {
        state.closed = true;
        window.removeEventListener("paste", handlePaste);
        state.items.forEach((i) => URL.revokeObjectURL(i.thumbUrl));
      };
    },
  };
})();
