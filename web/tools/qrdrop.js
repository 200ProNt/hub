/* Hub — Обмен с телефоном (QR-Drop): передача текста, ссылок и файлов по Wi-Fi */

(function () {
  const TEMPLATE = `
    <div class="qrdrop-layout">
      <!-- Левая колонка: QR-код подключения -->
      <section class="card qrdrop-connect-card">
        <h2 class="section-title">📱 Подключение со смартфона</h2>
        <p class="section-hint">Наведи камеру телефона на QR-код или открой адрес в мобильном браузере</p>

        <div class="qrdrop-qr-wrapper">
          <div class="qrdrop-qr-box" id="dropQrBox"><img src="/api/drop/qr.svg" width="190" height="190" alt="QR-код для открытия Hub на телефоне"></div>
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

  function mount(container) {
    let unmounted = false;
    container.innerHTML = TEMPLATE;
    const qrImage = container.querySelector("#dropQrBox img");
    qrImage?.addEventListener("error", () => qrImage.parentElement.classList.add("hidden"));
    const $ = (sel) => container.querySelector(sel);

    let dropInfo = null;

    async function reload() {
      if (unmounted || !container.isConnected) return;
      try {
        dropInfo = await Hub.api("/api/drop/info");
        if (unmounted || !container.isConnected) return;
        renderAll();
      } catch (e) {
        if (!unmounted && container.isConnected) {
          Hub.toast("Не удалось загрузить данные QR-Drop: " + e.message);
        }
      }
    }

    function renderAll() {
      if (unmounted || !container.isConnected || !dropInfo) return;

      const urlCode = $("#dropUrlCode");
      if (!urlCode) return;
      urlCode.textContent = dropInfo.url || "";

      const openWebBtn = $("#dropOpenWebBtn");
      if (openWebBtn) openWebBtn.href = dropInfo.url || "#";

      // Отрисовка QR

      // Раздача файлов
      const sharedList = $("#dropSharedList");
      if (sharedList) {
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
      }

      // Принятые файлы
      const incomingList = $("#dropIncomingList");
      if (incomingList) {
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
      }

      // Принятый текст
      const textsList = $("#dropTextsList");
      if (textsList) {
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
    }

    const copyBtn = $("#dropCopyUrlBtn");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        if (dropInfo && dropInfo.url) {
          navigator.clipboard.writeText(dropInfo.url);
          Hub.playSound("copy");
          Hub.toast("Адрес подключения скопирован");
        }
      });
    }

    const refreshBtn = $("#dropRefreshBtn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        Hub.playSound("action");
        reload();
      });
    }

    const pickBtn = $("#dropSharePickBtn");
    if (pickBtn) {
      pickBtn.addEventListener("click", async () => {
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
    }

    const incomingBtn = $("#dropOpenIncomingBtn");
    if (incomingBtn) {
      incomingBtn.addEventListener("click", async () => {
        try {
          await Hub.api("/api/drop/open", { path: "data/incoming" });
        } catch (e) {
          Hub.toast("Не удалось открыть папку: " + e.message);
        }
      });
    }

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

      const copyTextBtn = e.target.closest('[data-act="copy-text"]');
      if (copyTextBtn) {
        const text = copyTextBtn.dataset.text;
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

    reload();

    // Периодическое автообновление каждые 4 секунды для отслеживания входящих с телефона
    const pollTimer = setInterval(reload, 4000);

    return () => {
      unmounted = true;
      clearInterval(pollTimer);
    };
  }

  window.HubTools = window.HubTools || {};
  window.HubTools.qrdrop = { mount };
})();
