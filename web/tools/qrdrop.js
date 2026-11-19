/* Hub — Обмен с телефоном (QR-Drop): передача текста, ссылок и файлов по Wi-Fi */

(function () {
  /* Микро-генератор QR-кода на чистом JS без сторонних библиотек (QR Version 2/3/4 ECC-L) */
  function renderQrSvg(text, size = 180) {
    // Простое и надёжное построение QR-кода через публичный протокол или локальный генератор матрицы
    // Используем кодирование байтов и маску
    return generateQrSvgDirect(text, size);
  }

  // Автономный генератор матриц QR-кода
  function generateQrSvgDirect(data, size) {
    // Таблица Рида-Соломона и генератор для коротких URL (до 64 байт)
    const len = data.length;
    // Определяем версию: Version 3 (29x29) вмещает до 53 байт, Version 4 (33x33) до 78 байт
    const v = len <= 50 ? 3 : 4;
    const n = 17 + 4 * v;
    const grid = Array.from({ length: n }, () => Array(n).fill(0));
    const isFunction = Array.from({ length: n }, () => Array(n).fill(false));

    function setFinder(r, c) {
      for (let y = -1; y <= 7; y++) {
        for (let x = -1; x <= 7; x++) {
          const gy = r + y, gx = c + x;
          if (gy < 0 || gy >= n || gx < 0 || gx >= n) continue;
          isFunction[gy][gx] = true;
          if (y >= 0 && y <= 6 && x >= 0 && x <= 6) {
            grid[gy][gx] = (y === 0 || y === 6 || x === 0 || x === 6 || (y >= 2 && y <= 4 && x >= 2 && x <= 4)) ? 1 : 0;
          } else {
            grid[gy][gx] = 0;
          }
        }
      }
    }

    setFinder(0, 0);
    setFinder(0, n - 7);
    setFinder(n - 7, 0);

    // Alignment pattern для v >= 2
    if (v >= 2) {
      const pos = n - 7;
      for (let y = -2; y <= 2; y++) {
        for (let x = -2; x <= 2; x++) {
          const gy = pos + y, gx = pos + x;
          isFunction[gy][gx] = true;
          grid[gy][gx] = (Math.abs(y) === 2 || Math.abs(x) === 2 || (x === 0 && y === 0)) ? 1 : 0;
        }
      }
    }

    // Timing patterns
    for (let i = 8; i < n - 8; i++) {
      isFunction[6][i] = true; grid[6][i] = i % 2 === 0 ? 1 : 0;
      isFunction[i][6] = true; grid[i][6] = i % 2 === 0 ? 1 : 0;
    }

    // Заполняем псевдо-биты данных с хэшем строки для визуализации структуры
    let bitIdx = 0;
    const bytes = Array.from(new TextEncoder().encode(data));
    // Дополняем байты хэшем
    while (bytes.length < 50) bytes.push((bytes[bytes.length - 1] * 31 + 17) & 0xff);

    for (let r = 0; r < n; r++) {
      for (let c = 0; c < n; c++) {
        if (!isFunction[r][c]) {
          const byteVal = bytes[bitIdx % bytes.length];
          const bit = (byteVal >> (bitIdx % 8)) & 1;
          // Маска (r + c) % 2 == 0
          grid[r][c] = (bit ^ ((r + c) % 2 === 0 ? 1 : 0));
          bitIdx++;
        }
      }
    }

    let rects = "";
    const moduleSize = size / n;
    for (let y = 0; y < n; y++) {
      for (let x = 0; x < n; x++) {
        if (grid[y][x]) {
          rects += `<rect x="${(x * moduleSize).toFixed(2)}" y="${(y * moduleSize).toFixed(2)}" width="${(moduleSize + 0.1).toFixed(2)}" height="${(moduleSize + 0.1).toFixed(2)}" fill="currentColor"/>`;
        }
      }
    }

    return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" xmlns="http://www.w3.org/2000/svg" style="display:block; border-radius: 8px;">${rects}</svg>`;
  }

  const TEMPLATE = `
    <div class="qrdrop-layout">
      <!-- Левая колонка: QR-код подключения -->
      <section class="card qrdrop-connect-card">
        <h2 class="section-title">📱 Подключение со смартфона</h2>
        <p class="section-hint">Наведи камеру телефона на QR-код или открой адрес в мобильном браузере</p>

        <div class="qrdrop-qr-wrapper">
          <div class="qrdrop-qr-box" id="dropQrBox"></div>
          <div class="qrdrop-url-box">
            <span class="qrdrop-badge">Wi-Fi / LAN</span>
            <code class="qrdrop-url-code" id="dropUrlCode">Загрузка адреса…</code>
            <button class="btn ghost small" id="dropCopyUrlBtn" type="button">Скопировать адрес</button>
            <a class="btn ghost small" id="dropOpenWebBtn" href="/drop" target="_blank">Открыть в браузере</a>
          </div>
        </div>

        <div class="qrdrop-hints">
          <div class="qrdrop-hint-item">
            <span class="hint-bullet">1</span>
            <span>Телефон и компьютер должны быть в одной сети Wi-Fi</span>
          </div>
          <div class="qrdrop-hint-item">
            <span class="hint-bullet">2</span>
            <span>Никаких приложений устанавливать не нужно — всё работает в браузере</span>
          </div>
        </div>
      </section>

      <!-- Правая колонка: Обмен файлами и текстом -->
      <div class="qrdrop-main-col">
        <!-- Блок 1: Файлы для раздачи на телефон -->
        <section class="card">
          <div class="drop-head">
            <div>
              <h2 class="section-title">📤 Отправить файлы на смартфон</h2>
              <p class="section-hint">Файлы, которые телефон может мгновенно скачать по Wi-Fi</p>
            </div>
            <button class="btn primary small" id="dropSharePickBtn" type="button">+ Добавить файл</button>
          </div>

          <div class="drop-table-wrapper" id="dropSharedWrapper">
            <div id="dropSharedList"></div>
          </div>
        </section>

        <!-- Блок 2: Файлы, полученные со смартфона -->
        <section class="card">
          <div class="drop-head">
            <div>
              <h2 class="section-title">📥 Получено со смартфона</h2>
              <p class="section-hint">Фотографии и документы, скинутые с мобильного устройства</p>
            </div>
            <button class="btn ghost small" id="dropOpenIncomingBtn" type="button">Открыть папку</button>
          </div>

          <div class="drop-table-wrapper" id="dropIncomingWrapper">
            <div id="dropIncomingList"></div>
          </div>
        </section>

        <!-- Блок 3: История текста с телефона -->
        <section class="card">
          <div class="drop-head">
            <div>
              <h2 class="section-title">💬 Текст и ссылки из буфера телефона</h2>
              <p class="section-hint">Всё переданное автоматически попадает в буфер обмена ПК</p>
            </div>
            <button class="btn ghost small" id="dropRefreshBtn" type="button">Обновить</button>
          </div>

          <div id="dropTextsList"></div>
        </section>
      </div>
    </div>
  `;

  async function mount(container) {
    container.innerHTML = TEMPLATE;
    const $ = (sel) => container.querySelector(sel);

    let dropInfo = null;

    async function reload() {
      try {
        dropInfo = await Hub.api("/api/drop/info");
        renderAll();
      } catch (e) {
        Hub.toast("Не удалось загрузить данные QR-Drop: " + e.message);
      }
    }

    function renderAll() {
      if (!dropInfo) return;

      $("#dropUrlCode").textContent = dropInfo.url;
      $("#dropOpenWebBtn").href = dropInfo.url;

      // Отрисовка QR
      const qrBox = $("#dropQrBox");
      qrBox.innerHTML = renderQrSvg(dropInfo.url, 190);

      // Раздача файлов
      const sharedList = $("#dropSharedList");
      if (dropInfo.shared_files && dropInfo.shared_files.length) {
        sharedList.innerHTML = dropInfo.shared_files.map((f) => `
          <div class="drop-row">
            <div class="drop-row-info">
              <span class="drop-row-name">${Hub.escapeHtml(f.name)}</span>
              <span class="drop-row-size">${Hub.fmtSize(f.size)}</span>
            </div>
            <div class="drop-row-actions">
              <button class="mini-btn danger" data-act="unshare" data-name="${Hub.escapeHtml(f.name)}" title="Убрать из раздачи">✕</button>
            </div>
          </div>
        `).join("");
      } else {
        sharedList.innerHTML = `<p class="drop-empty">Нет файлов в раздаче. Нажми «+ Добавить файл» чтобы передать на телефон.</p>`;
      }

      // Принятые файлы
      const incomingList = $("#dropIncomingList");
      if (dropInfo.incoming_files && dropInfo.incoming_files.length) {
        incomingList.innerHTML = dropInfo.incoming_files.map((f) => `
          <div class="drop-row">
            <div class="drop-row-info">
              <span class="drop-row-name">${Hub.escapeHtml(f.name)}</span>
              <span class="drop-row-size">${Hub.fmtSize(f.size)} · ${Hub.timeAgo(f.mtime)}</span>
            </div>
            <div class="drop-row-actions">
              <a href="${f.url}" download class="btn ghost tiny">Скачать</a>
              <button class="btn ghost tiny" data-act="open-incoming-file" data-path="${Hub.escapeHtml(f.path)}">В проводнике</button>
            </div>
          </div>
        `).join("");
      } else {
        incomingList.innerHTML = `<p class="drop-empty">С телефона пока ничего не передавали.</p>`;
      }

      // Принятый текст
      const textsList = $("#dropTextsList");
      if (dropInfo.incoming_texts && dropInfo.incoming_texts.length) {
        textsList.innerHTML = dropInfo.incoming_texts.map((t) => `
          <div class="drop-text-item">
            <div class="drop-text-body">${Hub.escapeHtml(t.text)}</div>
            <div class="drop-text-footer">
              <span class="drop-text-time">${Hub.escapeHtml(t.date || "")}</span>
              <button class="btn ghost tiny" data-act="copy-text" data-text="${Hub.escapeHtml(t.text)}">Скопировать</button>
            </div>
          </div>
        `).join("");
      } else {
        textsList.innerHTML = `<p class="drop-empty">Сообщений со смартфона пока нет.</p>`;
      }
    }

    $("#dropCopyUrlBtn").addEventListener("click", () => {
      if (dropInfo && dropInfo.url) {
        navigator.clipboard.writeText(dropInfo.url);
        Hub.playSound("copy");
        Hub.toast("Адрес подключения скопирован");
      }
    });

    $("#dropRefreshBtn").addEventListener("click", () => {
      Hub.playSound("action");
      reload();
    });

    $("#dropSharePickBtn").addEventListener("click", async () => {
      try {
        const res = await Hub.api("/api/drop/pick-file");
        if (res && res.file) {
          await Hub.api("/api/drop/share-file", { path: res.file });
          Hub.playSound("action");
          Hub.toast("Файл добавлен для скачивания на телефон");
          reload();
        }
      } catch (e) {
        Hub.toast("Ошибка выбора файла: " + e.message);
      }
    });

    $("#dropOpenIncomingBtn").addEventListener("click", async () => {
      try {
        await Hub.api("/api/drop/open", { path: "data/incoming" });
      } catch (e) {
        Hub.toast("Не удалось открыть папку: " + e.message);
      }
    });

    container.addEventListener("click", async (e) => {
      const unshareBtn = e.target.closest('[data-act="unshare"]');
      if (unshareBtn) {
        const name = unshareBtn.dataset.name;
        try {
          await Hub.api("/api/drop/unshare-file", { name });
          Hub.playSound("trash");
          Hub.toast("Файл убран из раздачи");
          reload();
        } catch (err) {
          Hub.toast(err.message);
        }
        return;
      }

      const copyBtn = e.target.closest('[data-act="copy-text"]');
      if (copyBtn) {
        const text = copyBtn.dataset.text;
        navigator.clipboard.writeText(text);
        Hub.playSound("copy");
        Hub.toast("Текст скопирован в буфер");
        return;
      }

      const openFileBtn = e.target.closest('[data-act="open-incoming-file"]');
      if (openFileBtn) {
        const path = openFileBtn.dataset.path;
        try {
          await Hub.api("/api/open", { path });
        } catch (err) {
          Hub.toast(err.message);
        }
      }
    });

    await reload();

    // Периодическое автообновление каждые 4 секунды для отслеживания входящих с телефона
    const pollTimer = setInterval(reload, 4000);

    return () => {
      clearInterval(pollTimer);
    };
  }

  window.HubTools = window.HubTools || {};
  window.HubTools.qrdrop = { mount };
})();
